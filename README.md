# bounded-pr-loop

A bounded, auditable PR-based loop where **Claude Code implements**, **Codex reviews**, and **GitHub Actions merges** — only when every gate is green.

Designed so any new repo of yours becomes harness-ready in **one command**.

```text
issue (label: claude-implement)
        │
        ▼
   Claude opens PR                   ┌──────────────────┐
        │                            │ ≤ 3 repair loops │
        ▼                            └──────────────────┘
   Codex reviews ──── FAIL ──► Claude fixes ──┐
        │                                     │
       PASS                                   │
        │     ◄───────────────────────────────┘
        ▼
   CI green + no sensitive paths + cost OK
        │
        ▼
   squash-merge
```

## Quickstart

In any repo you want under the harness:

```bash
# from inside your project
~/codes/github.com/bounded-pr-loop/bin/bpl-init
git add .github CLAUDE.md AGENTS.md CODEOWNERS .harness.yml
git commit -m "chore: enable bounded-pr-loop harness"
git push

# then for any task you want the loop to do:
gh issue create -l claude-implement -t "Add /healthz endpoint" -b "Description here"
```

That's the whole loop. Walk away; come back to a merged PR or a `needs-human` label.

## What it does

| Phase | Trigger | Actor | Output |
|---|---|---|---|
| Implement | Issue labeled `claude-implement` | Claude Code | Feature branch + PR |
| Review | PR opened / synced | Codex CLI | `codex-pass` or `codex-fail` label + finding comment |
| Fix | `codex-fail` label set | Claude Code | New commit on PR branch |
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
