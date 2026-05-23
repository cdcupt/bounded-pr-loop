# Architecture

## State machine

```text
                              ┌────────────────────┐
              issue labeled   │                    │
              claude-implement│                    │
              ─────────────►  │implementation_     │
                              │   created          │
                              └─────────┬──────────┘
                                        │ PR opened
                                        ▼
                              ┌────────────────────┐
                              │codex_review_       │
                              │   pending          │
                              └──┬──────────────┬──┘
                          PASS   │              │  FAIL
                                 ▼              ▼
                       ┌─────────────────┐ ┌─────────────────────┐
                       │codex_approved   │ │codex_changes_       │
                       └─┬───────────────┘ │   requested         │
                         │ ci_passed       └─────┬───────────────┘
                         ▼                       │ loop_count < 3
                  ┌─────────────────┐             ▼
                  │   auto_merged   │     ┌──────────────────┐
                  └─────────────────┘     │ claude_fixing    │
                                          └──┬───────────────┘
                                             │ new commit
                                             ▼ (back to codex_review_pending)
                                                
                                          loop_count >= 3
                                          OR sensitive_path
                                          OR cost_exceeded
                                             │
                                             ▼
                                          ┌──────────────────┐
                                          │failed_needs_human│
                                          └──────────────────┘
```

## Transition table (canonical)

| From | Event | Guards | To |
|---|---|---|---|
| `(none)` | `issues.labeled` `claude-implement` | issue is open | `implementation_created` |
| `implementation_created` | `pull_request.opened` | PR head matches issue | `codex_review_pending` |
| `codex_review_pending` | Codex run completes | verdict = PASS | `codex_approved` |
| `codex_review_pending` | Codex run completes | verdict = FAIL | `codex_changes_requested` |
| `codex_changes_requested` | label `codex-fail` applied | `loop_count < max` & no sensitive path & cost OK | `claude_fixing` |
| `codex_changes_requested` | label `codex-fail` applied | `loop_count >= max` OR sensitive path OR cost exceeded | `failed_needs_human` |
| `claude_fixing` | `push` to PR branch | — | `codex_review_pending` |
| `codex_approved` | `check_suite.completed` | all required checks green & not calibration_mode & no sensitive path | `auto_merged` |
| `codex_approved` | `check_suite.completed` | calibration_mode = true | `(stays — human merges)` |
| any | any | secret detected by gitleaks | `failed_needs_human` |
| any | any | PR modifies CODEOWNERS-protected path without owner review | `(blocked by branch protection)` |

State is encoded entirely as **labels on the PR** — no external database. The loop counter lives in a hidden HTML comment on the PR body, which `agent_loop_guard.py` reads and rewrites.

## Concurrency

`codex-review-gate.yml` uses `cancel-in-progress: true` so a new commit invalidates any stale review run:

```yaml
concurrency:
  group: codex-review-${{ github.event.pull_request.number }}
  cancel-in-progress: true
```

## File-level responsibility

| File | Responsibility |
|---|---|
| `claude-implement.yml` | Owns the issue→PR transition. Stateless beyond GitHub. |
| `codex-review-gate.yml` | Owns the review verdict. Writes labels and PR comment. |
| `claude-fix-from-codex.yml` | Owns the fix loop. Reads labels, checks guards, runs Claude. |
| `auto-merge.yml` | Owns the merge decision. Reads all labels + checks; takes no other action. |
| `agent_loop_guard.py` | The only writer of the loop-count marker comment. |
| `codex_review_gate.py` | The only writer of `codex-pass` / `codex-fail` labels. |

This separation means no two workflows ever fight for the same label.

## Why a 30-line stub per repo, not a 300-line monolith

Each consumer repo ships `.github/workflows/harness.yml`, which is just:

```yaml
name: Harness
on:
  issues: { types: [labeled] }
  pull_request: { types: [opened, synchronize] }
  pull_request_review: { types: [submitted] }
  check_suite: { types: [completed] }

jobs:
  implement:
    if: github.event_name == 'issues' && github.event.label.name == 'claude-implement'
    uses: cdcupt/bounded-pr-loop/.github/workflows/claude-implement.yml@v1
    secrets: inherit
    with:
      issue_number: ${{ github.event.issue.number }}

  review:
    if: github.event_name == 'pull_request'
    uses: cdcupt/bounded-pr-loop/.github/workflows/codex-review-gate.yml@v1
    secrets: inherit
    with:
      pr_number: ${{ github.event.pull_request.number }}

  fix:
    if: github.event_name == 'pull_request' && contains(github.event.pull_request.labels.*.name, 'codex-fail')
    uses: cdcupt/bounded-pr-loop/.github/workflows/claude-fix-from-codex.yml@v1
    secrets: inherit
    with:
      pr_number: ${{ github.event.pull_request.number }}

  merge:
    if: github.event_name == 'check_suite' || github.event_name == 'pull_request_review'
    uses: cdcupt/bounded-pr-loop/.github/workflows/auto-merge.yml@v1
    secrets: inherit
```

Upgrade path is `@v1` → `@v2` per repo. No code churn, no copy-paste drift.

## What happens to the original issue

Every Claude-generated PR body must include `Closes #<n>`. GitHub auto-closes the issue on merge. This is enforced in `CLAUDE.md.tmpl` and verified by the review gate.
