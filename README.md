# bounded-pr-loop

A bounded, auditable loop where **Claude implements**, **Codex reviews**, and you merge only when both agree. Two modes:

- **Local** *(default, recommended)* — runs on your Mac via your Claude Code + Codex **subscriptions**. No API keys, no recurring cost. One `~/CLAUDE.md` is the global source of truth; no per-project CLAUDE.md needed.
- **CI** — same loop, running in GitHub Actions. Requires `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` (or an OpenRouter key routed via `*_BASE_URL` overrides). Pay-per-call.

```text
                        ┌──────────────────┐
                        │ ≤ 3 repair loops │
                        └──────────────────┘
issue → Claude implements → Codex reviews ──FAIL──► Claude fixes ──┐
                                  │                                 │
                                 PASS  ◄──────────────────────────  ┘
                                  │
                                  ▼
                       open PR ─► you (or CI) merge
```

## Quickstart — local mode

```bash
# one-time setup of a repo:
cd ~/codes/github.com/<your-repo>
~/codes/github.com/bounded-pr-loop/bin/bpl-init     # drops .bpl.yml only

# for any task:
gh issue create -t "Add /healthz endpoint" -b "Description here"
~/codes/github.com/bounded-pr-loop/bin/bpl-run <issue-number>
```

`bpl-run` reads `~/CLAUDE.md` (global) + optional `./CLAUDE.md` (project-specific only if you need it), runs `claude` then `codex`, loops up to 3 times, opens a PR. Costs $0 above your existing subscriptions.

## Quickstart — CI mode (only if you want unattended GitHub-Actions-driven runs)

```bash
gh secret set ANTHROPIC_API_KEY --user
gh secret set OPENAI_API_KEY    --user

cd ~/codes/github.com/<your-repo>
~/codes/github.com/bounded-pr-loop/bin/bpl-init --ci
git add .github CLAUDE.md AGENTS.md CODEOWNERS .harness.yml
git commit -m "chore: enable bounded-pr-loop (CI mode)"
git push

gh issue create -l claude-implement -t "Add /healthz" -b "..."
# walk away; the workflow opens, reviews, and merges the PR
```

CI mode burns API-rate dollars even though you have subscriptions, because GitHub Actions runners can't OAuth into your accounts. If you only have an OpenRouter key, set:

```bash
gh secret set ANTHROPIC_BASE_URL --user --body "https://openrouter.ai/api/v1"
gh secret set OPENAI_BASE_URL    --user --body "https://openrouter.ai/api/v1"
gh secret set ANTHROPIC_API_KEY  --user --body "<your-openrouter-key>"
gh secret set OPENAI_API_KEY     --user --body "<your-openrouter-key>"
```

Both SDKs respect the base-URL override, so one key powers both agents through OpenRouter's proxy.

## What it does

In **local mode** (default):

| Phase | Actor | Output |
|---|---|---|
| Implement | `claude -p --dangerously-skip-permissions` | New branch, commit |
| Review | `codex exec` against the diff | Inline PASS/FAIL printed; loop continues or halts |
| Fix | `claude` again, scoped to blocking findings only | New commit on the branch |
| Open PR | `gh pr create` | PR with verdict in description; `needs-human` label if exhausted |
| Merge | You (or `--auto-merge` once you trust the loop) | Squash, issue auto-closes via `Closes #N` |

In **CI mode**:

| Phase | Trigger | Actor | Output |
|---|---|---|---|
| Implement | Issue labeled `claude-implement` | Claude Code Action | Feature branch + PR |
| Review | PR opened / synced | Codex CLI | `codex-pass` or `codex-fail` label + finding comment |
| Fix | `codex-fail` label set | Claude Code Action | New commit on PR branch |
| Merge | All gates green | GitHub | Squash-merge, issue auto-closes |
| Halt | Loop limit, sensitive path, secret leak | Loop guard | `needs-human` label, no merge |

## When **not** to use the harness

- **Local quick fixes** — just run `claude` or `codex` in your terminal.
- **Spikes / throwaway prototypes** — overhead > value.
- **Large refactors crossing >10 files** — bounded loop will exhaust before finishing. Plan in CLI, then issue-chunk it.
- **Anything touching production secrets** — already excluded by sensitive-path defaults, but worth saying explicitly.

Rule of thumb: **harness for task-shaped work, CLI for thinking-shaped work.**

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the state machine, transition table, and sequence diagrams.

## Safety rails (all enforced by code, not policy)

- Max 3 Claude ↔ Codex repair loops per PR (configurable per repo).
- Sensitive paths (`auth/**`, `billing/**`, `migrations/**`, `.github/workflows/**`, `secrets/**`) require human review via CODEOWNERS.
- `gitleaks` runs as a required check (`secret-scan` job) before merge — deterministic, not LLM-based.
- New repos open in **calibration mode** — auto-merge blocked until you remove the `harness-calibrating` label.
- All bot commits prefixed `[agent]` so they're scannable in `git log`.

## Language overlays (auto-selected, no config needed)

`detect_languages.sh` sniffs the repo and the PR diff, then composes the
Codex review prompt as `BASE.md + matching overlays + your REVIEW_GUIDE.local.md`.
Currently bundled:

| Overlay | Triggers on |
|---|---|
| `go.md` | `go.mod` or any `*.go` |
| `swift.md` | `Package.swift` or any `*.swift` |
| `typescript.md` | `tsconfig.json` or any `*.ts` / `*.tsx` |
| `python.md` | `pyproject.toml` / `requirements.txt` / `setup.py` or any `*.py` |

Adding a new language is one file in `templates/review-guide/overlays/`.

## ⚠️ Cost cap is currently disabled by default

Your initial install uses `cost_cap_per_pr_usd: null`, which means spend is **logged but never blocked**. Every API call is appended to `.harness/spend.jsonl` in each consumer repo for retroactive audit.

To enforce a hard ceiling, edit `.harness.yml` in any project:

```yaml
cost_cap_per_pr_usd: 2.00
cost_cap_per_day_usd: 20.00
```

See [docs/COST_CONTROL.md](docs/COST_CONTROL.md) for how this is computed.

## Calibration: don't trust the loop on day one

Every project starts with `calibration_mode: true` in `.harness.yml`. While that's on, **auto-merge is disabled even when all gates pass** — you still merge manually. Use this to:

1. Tune `REVIEW_GUIDE.local.md` to your project's quirks.
2. Watch for false PASS / false FAIL from Codex.
3. Build trust over ~10 PRs.

Then flip `calibration_mode: false` and let it run.

See [docs/CALIBRATION.md](docs/CALIBRATION.md).

## Required secrets (set once at the user level)

```bash
gh secret set ANTHROPIC_API_KEY --user
gh secret set OPENAI_API_KEY    --user
```

Every personal repo that opts in via `bpl-init` will inherit these — no per-repo setup.

## Versioning

Consumer repos pin to a tag:

```yaml
uses: cdcupt/bounded-pr-loop/.github/workflows/codex-review-gate.yml@v1
```

Upgrade a single project by bumping its `@v1` → `@v2`. Roll out gradually.

## License

MIT. See [LICENSE](LICENSE).
