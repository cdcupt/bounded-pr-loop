---
name: bpl
description: Bounded PR Loop — implement, open PR, Codex reviews via local codex CLI, fix findings, merge. Use when the user asks to add a feature, fix a bug, modify code, or scaffold a new project inside (or about to be inside) a GitHub repository. The skill walks Claude through the 5-phase workflow using its own tools (Bash, Edit, Write); no external script needed.
origin: cdcupt/bounded-pr-loop
---

# BPL: Bounded PR Loop

You (Claude) follow this 5-phase workflow for any task-shaped code change in a real GitHub repository. **You are the implementer.** Local `codex` CLI is the reviewer. The user supervises and (by default) does the final merge.

## When to activate

Activate **immediately, without asking,** when the user says any of:

- "Add a feature / endpoint / screen / command…"
- "Fix this bug / error / failing test…"
- "Implement this TODO / spec / issue…"
- "Modify / change / update this behavior…"
- "Refactor this focused area…"
- "Create a new project that does X" *(see Phase 0 below — slight variant)*

Activate **after a one-line confirmation** when the request is task-shaped but you're not sure whether it fits in one PR.

Do **NOT** activate for:

- Design discussions, exploratory questions, or "how would I…" requests — just answer them.
- Local experimentation in an uncommitted state where the user hasn't asked for a permanent change.
- Multi-day refactors that obviously won't fit in one PR — propose breaking it into issues first.
- Repos with no GitHub remote (offer to `gh repo create` first).

## Pre-flight — always run, in order

```bash
git rev-parse --show-toplevel              # must be in a git repo
gh repo view --json nameWithOwner          # remote must be a GitHub repo you can push to
command -v claude codex gh                 # required CLIs
```

If any fails, tell the user concretely and stop.

Then load context Claude will need throughout the loop:

1. **`~/CLAUDE.md`** — the global agent guide. Your behavior rules live there.
2. **`./CLAUDE.md`** in the repo, if it exists — project-specific overrides.
3. **Review-guide composition** for Phase 3:
   - Base: `~/codes/github.com/bounded-pr-loop/templates/review-guide/BASE.md`
   - Language overlays: pick from `…/overlays/<lang>.md` for any language sentinel present (`go.mod` → `go`, `Package.swift` → `swift`, `tsconfig.json` → `typescript`, `pyproject.toml`/`requirements.txt`/`setup.py` → `python`).
   - Optional local: `./REVIEW_GUIDE.local.md`.
4. **`.bpl.yml`** if it exists — loop limit, sensitive paths, model overrides. Otherwise use defaults: `loop_count_max: 3`, sensitive `.github/workflows/**`, `**/auth/**`, `**/billing/**`, `**/migrations/**`, `**/secrets/**`.

## Phase 0 — only for "create a new project"

If the user asked to create a new project:

1. `gh repo create cdcupt/<name> --public --confirm`.
2. `git init -b main`, scaffold the minimum (README + LICENSE + language-appropriate config file).
3. `git push -u origin main` — initial scaffold goes **directly to main**, no PR. This is the only commit that bypasses BPL; from this point on every change goes through it.
4. Run `bpl-init` (`~/codes/github.com/bounded-pr-loop/bin/bpl-init`) to drop `.bpl.yml`.
5. Now proceed with Phase 1 for whatever feature the user actually asked for.

## Phase 1 — Implement

1. Compute a branch name: `agent/<short-slug>` (lowercase, hyphens, ≤40 chars from the task description). If there's a linked issue, use `agent/issue-<n>-<slug>`.
2. `git checkout -b <branch>`.
3. Make the **smallest change** that satisfies the task. Do not refactor adjacent code, even if it's tempting. If structural change is unavoidable, call it out in the PR description.
4. If the project has tests (look for `package.json` `test` script, `pytest`, `go test`, `swift test`, etc.), run them. **Do not proceed if they fail.** Either fix or stop and tell the user.
5. Commit:
   ```bash
   git commit -m "[agent] <type>: <one-line description>" \
              -m "Closes #<n>"   # only if there's a linked issue
   ```
   Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`.

## Phase 2 — Push & open PR

1. `git push -u origin <branch>`.
2. `gh pr create --title "[agent] <task title>" --body "<body>"`.
3. PR body should include `Closes #<n>` when applicable, plus a one-paragraph summary of what changed and why.
4. **Capture the PR URL and number** — both are needed in later phases.

## Phase 3 — Codex review

1. Compose the review prompt by concatenating, in this order:
   - `BASE.md` content
   - each detected language overlay's content
   - `REVIEW_GUIDE.local.md` if present
   - `---`
   - `## PR diff to review` heading
   - a fenced ` ```diff ` block containing `git diff main...<branch>` output

   Write it to `/tmp/bpl_review_prompt.md`. Bash heredoc pattern:
   ```bash
   {
     cat ~/codes/github.com/bounded-pr-loop/templates/review-guide/BASE.md
     # …append overlays + local guide here if applicable
     echo; echo "---"; echo
     echo "## PR diff to review"; echo
     echo '```diff'
     git diff main...<branch>
     echo '```'
   } > /tmp/bpl_review_prompt.md
   ```

2. **Run Codex non-interactively with `codex exec -` (literal `-` for stdin):**
   ```bash
   codex exec - < /tmp/bpl_review_prompt.md > /tmp/bpl_codex_out.txt 2>&1
   ```
   - Use `-` as the explicit prompt argument; pure shell redirection without `-` does not always reach the prompt parser.
   - **Do NOT use `codex exec review --base main` with a custom prompt** — `--base` and `[PROMPT]` are mutually exclusive at runtime despite what `--help` suggests. Use the manual-diff form above and Codex will see exactly the diff you give it.
   - The `--model` flag is optional; Codex picks a reasonable default. Only override (`-c model="o3"`) when a specific repo needs more rigor.
   - Codex may exit non-zero on FAIL verdicts — don't treat that as a script failure. Drop `|| true` from the pipeline only if you want to detect *crash* failures separately.

3. **Parse the verdict.** Look for a case-insensitive line matching `verdict:\s*(pass|fail)`. Use the **last** match. If no verdict is found, treat as FAIL with the meta-finding "Could not parse VERDICT line from Codex output."

4. **Extract findings.** From a `## Blocking findings` section, pull each bullet (`- ` or `* `) as a separate finding. The Codex stdout will also include the prompt echoed back and a `tokens used` footer — ignore both when parsing.

5. **Post the Codex review as a PR comment** so the audit trail is in GitHub, not just in `/tmp`. Prefix the comment body with `<!-- bpl-codex-review -->` so later phases can update the same comment instead of stacking them. Write the comment body to a file (don't try to inline it on the command line — it usually contains markdown that breaks shell quoting):
   ```bash
   gh pr comment <pr#> --body-file /tmp/bpl_pr_comment.md
   ```

## Phase 4 — Address findings

Look at the verdict from Phase 3.

- **PASS** → skip to Phase 5.

- **FAIL** and `loop_count < loop_count_max`:
  1. Increment loop_count (track this in your working memory for this session — no external state needed).
  2. Make Edit/Write changes targeting **only the listed blocking findings**. Do not expand scope; do not refactor adjacent code; do not add new functionality during a fix loop.
  3. Run tests again. If they fail, stop and tell the user — don't commit a broken fix.
  4. Commit:
     ```bash
     git commit -am "[agent] fix: address Codex blocking findings (loop <n>)"
     git push
     ```
  5. Go back to Phase 3.

- **FAIL** and `loop_count == loop_count_max`:
  1. `gh pr edit <pr#> --add-label needs-human` (create the label first if missing: `gh label create needs-human --color E99695 --description "Loop exhausted; human attention required"`).
  2. Tell the user: "Loop limit reached after N attempts. PR is at <url>. Latest blocking findings: …"
  3. Stop.

## Phase 5 — Merge

1. **Sensitive-path check.** Run `git diff --name-only main...HEAD` and compare against the sensitive list from pre-flight. If any file matches, **do not auto-merge** — tell the user the PR touches a protected path and needs their explicit OK.
2. **CI check.** If the repo has any GitHub Actions on PRs, wait for `gh pr checks <pr#> --watch` to come back green. If checks fail, treat as a FAIL outcome from Phase 3 and try one more repair if loops remain.
3. **Default behavior: do NOT auto-merge.** Print the PR URL and tell the user the loop succeeded; they merge when they're ready.
4. **Only auto-merge** when ALL of:
   - The user said "merge it" or "auto-merge" or `--auto-merge` up front in this session.
   - No sensitive paths touched.
   - CI green (if any).
   - Verdict is PASS.

   Then: `gh pr merge <pr#> --squash --delete-branch`.

## Safety rules (non-negotiable)

- **Never** commit secrets, API keys, tokens, private keys, or production credentials. If you find one in the diff, stop and tell the user.
- **Never** modify `.github/workflows/**`, `auth/**`, `billing/**`, `migrations/**`, `secrets/**` without explicit user confirmation in this session.
- **Maximum 3 fix loops per PR.** Beyond that, `needs-human` label and stop.
- **Every bot commit message starts with `[agent]`** so they're scannable in `git log`.
- **If the user interrupts or changes direction mid-loop**, stop immediately and ask.
- **One PR per task.** If a request grows during implementation, complete the current PR and propose a follow-up issue rather than expanding scope.

## Resources

- Canonical source: `~/codes/github.com/bounded-pr-loop/skills/bpl/SKILL.md` (this file).
- Active install: `~/.claude/skills/bpl/SKILL.md` (symlink to the canonical source — edits in either show up everywhere).
- Review-guide overlays: `~/codes/github.com/bounded-pr-loop/templates/review-guide/overlays/`.
- Fallback orchestrator for terminal use without Claude in a session: `~/codes/github.com/bounded-pr-loop/bin/bpl-run`.
- Memory note: `bounded-pr-loop` in `~/.claude/projects/-Users-erik/memory/`.

## Validation

End-to-end smoke-tested 2026-05-17 against `cdcupt/bpl-sandbox` PR #1 (add MIT LICENSE). All 5 phases ran; Codex returned `VERDICT: PASS` on first review; review posted to PR. `codex exec - < prompt.md` confirmed working with subscription auth. The `codex exec review --base` form was tried and rejected — see Phase 3 notes for why.

## Telling the user what's happening

Be terse in the chat. Don't narrate every `gh` call. The user wants:

1. "Implementing X on branch `agent/foo`…"
2. "Pushed; PR opened: <url>"
3. "Codex review: PASS" *or* "Codex review: FAIL with N findings; fixing…"
4. (If loop) "Fix attempt 2/3 pushed; re-reviewing…"
5. "Done. PR is ready: <url>. Merge when you're ready." *(or "Merged." if auto-merge was OK'd.)*

That's the whole user-facing footprint per task.
