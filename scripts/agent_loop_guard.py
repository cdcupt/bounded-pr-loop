#!/usr/bin/env python3
"""agent_loop_guard.py — the single source of truth for loop state and merge-eligibility.

State is encoded on the PR itself:
  * Loop count: a hidden marker `<!-- loop_count: N -->` inside the PR body.
  * Phase    : labels (codex-pass, codex-fail, needs-human, harness-calibrating, ...).
  * Risk     : sensitive-path detection against the PR's changed files.

This script is the ONLY writer of the loop_count marker. Workflows must
call it through one of the subcommands below; do not edit the PR body
from other places, or you will desync the counter.

Subcommands:
  check           — Verify it is safe to enter another fix loop.
                    Exits 0 on go, non-zero (and posts a PR comment) on stop.
  increment       — Bump loop_count by 1 and rewrite the marker.
  merge-eligible  — Verify ALL conditions for auto-merge are satisfied.
                    Exits 0 on go, non-zero on stop.

Inputs (all subcommands):
  --pr     <number>
  --repo   <owner/name>
  --config <path to .harness.yml>  (defaults to ./.harness.yml)

The GitHub token is read from $GH_TOKEN (provided by the gh CLI in workflows).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MARKER_RE = re.compile(r"<!--\s*loop_count:\s*(\d+)\s*-->")
DEFAULT_LOOP_MAX = 3
DEFAULT_SENSITIVE = [
    ".github/workflows/**",
    "**/auth/**",
    "**/billing/**",
    "**/migrations/**",
    "**/secrets/**",
]
TERMINAL_LABELS = {"needs-human", "security-sensitive"}


@dataclass(frozen=True)
class HarnessConfig:
    loop_count_max: int
    sensitive_paths: tuple[str, ...]
    calibration_mode: bool
    cost_cap_per_pr_usd: float | None

    @classmethod
    def load(cls, path: Path) -> "HarnessConfig":
        if not path.exists():
            return cls(
                loop_count_max=DEFAULT_LOOP_MAX,
                sensitive_paths=tuple(DEFAULT_SENSITIVE),
                calibration_mode=True,
                cost_cap_per_pr_usd=None,
            )
        try:
            import yaml  # PyYAML is preinstalled on ubuntu-latest runners
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml"], check=True)
            import yaml  # noqa: WPS433
        data = yaml.safe_load(path.read_text()) or {}
        return cls(
            loop_count_max=int(data.get("loop_count_max", DEFAULT_LOOP_MAX)),
            sensitive_paths=tuple(data.get("sensitive_paths") or DEFAULT_SENSITIVE),
            calibration_mode=bool(data.get("calibration_mode", True)),
            cost_cap_per_pr_usd=data.get("cost_cap_per_pr_usd"),
        )


def gh(*args: str) -> str:
    """Run `gh` and return stdout. Raises on non-zero."""
    result = subprocess.run(
        ["gh", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def fetch_pr(repo: str, pr: int) -> dict[str, Any]:
    raw = gh(
        "pr", "view", str(pr),
        "--repo", repo,
        "--json", "number,title,body,labels,files,statusCheckRollup,reviewDecision",
    )
    return json.loads(raw)


def read_loop_count(body: str) -> int:
    match = MARKER_RE.search(body or "")
    return int(match.group(1)) if match else 0


def write_loop_count(body: str, new_count: int) -> str:
    marker = f"<!-- loop_count: {new_count} -->"
    if MARKER_RE.search(body):
        return MARKER_RE.sub(marker, body)
    return f"{body.rstrip()}\n\n{marker}\n"


def touched_sensitive_path(files: list[dict[str, Any]], patterns: tuple[str, ...]) -> str | None:
    for f in files:
        path = f["path"]
        for pattern in patterns:
            if fnmatch.fnmatch(path, pattern):
                return f"{path} matches {pattern}"
    return None


def comment(repo: str, pr: int, body: str) -> None:
    gh("pr", "comment", str(pr), "--repo", repo, "--body", body)


def label_add(repo: str, pr: int, label: str) -> None:
    gh("pr", "edit", str(pr), "--repo", repo, "--add-label", label)


def has_label(pr_json: dict[str, Any], name: str) -> bool:
    return any(lbl["name"] == name for lbl in pr_json.get("labels", []))


# ──────────────────── subcommands ────────────────────


def cmd_check(args: argparse.Namespace) -> int:
    cfg = HarnessConfig.load(Path(args.config))
    pr = fetch_pr(args.repo, args.pr)

    for terminal in TERMINAL_LABELS:
        if has_label(pr, terminal):
            print(f"Stop: PR already has terminal label `{terminal}`.")
            return 1

    count = read_loop_count(pr["body"] or "")
    if count >= cfg.loop_count_max:
        msg = (
            f"⛔ **Loop limit reached** ({count}/{cfg.loop_count_max}).\n\n"
            f"Adding `needs-human`. The harness will not attempt further automatic fixes."
        )
        comment(args.repo, args.pr, msg)
        label_add(args.repo, args.pr, "needs-human")
        return 1

    breach = touched_sensitive_path(pr["files"], cfg.sensitive_paths)
    if breach:
        msg = (
            f"⛔ **Sensitive path touched**: {breach}\n\n"
            f"Adding `security-sensitive`. Human review required before any further automation."
        )
        comment(args.repo, args.pr, msg)
        label_add(args.repo, args.pr, "security-sensitive")
        return 1

    print(f"OK: loop_count={count}/{cfg.loop_count_max}, no sensitive paths, no terminal labels.")
    return 0


def cmd_increment(args: argparse.Namespace) -> int:
    pr = fetch_pr(args.repo, args.pr)
    count = read_loop_count(pr["body"] or "")
    new_body = write_loop_count(pr["body"] or "", count + 1)
    # gh pr edit --body reads from a file when the body contains newlines safely
    body_file = Path("/tmp/_pr_body.txt")
    body_file.write_text(new_body)
    gh("pr", "edit", str(args.pr), "--repo", args.repo, "--body-file", str(body_file))
    print(f"loop_count: {count} → {count + 1}")
    return 0


def cmd_merge_eligible(args: argparse.Namespace) -> int:
    cfg = HarnessConfig.load(Path(args.config))
    pr = fetch_pr(args.repo, args.pr)

    if cfg.calibration_mode and has_label(pr, "harness-calibrating"):
        print("Stop: calibration_mode is on and `harness-calibrating` label is present.")
        return 1

    if not has_label(pr, "codex-pass"):
        print("Stop: PR does not have `codex-pass` label.")
        return 1

    for blocker in ("codex-fail", *TERMINAL_LABELS):
        if has_label(pr, blocker):
            print(f"Stop: PR has blocking label `{blocker}`.")
            return 1

    breach = touched_sensitive_path(pr["files"], cfg.sensitive_paths)
    if breach:
        print(f"Stop: sensitive path touched ({breach}); requires CODEOWNERS review.")
        return 1

    rollup = pr.get("statusCheckRollup") or []
    failing = [c for c in rollup if c.get("conclusion") not in ("SUCCESS", "NEUTRAL", "SKIPPED", None)]
    if failing:
        names = ", ".join(c.get("name", "?") for c in failing[:5])
        print(f"Stop: failing checks: {names}")
        return 1

    print("OK: PR is merge-eligible.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("check", "increment", "merge-eligible"):
        sp = sub.add_parser(name)
        sp.add_argument("--pr", type=int, required=True)
        sp.add_argument("--repo", required=True)
        sp.add_argument("--config", default=".harness.yml")

    args = parser.parse_args()
    dispatch = {
        "check": cmd_check,
        "increment": cmd_increment,
        "merge-eligible": cmd_merge_eligible,
    }
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
