#!/usr/bin/env python3
"""codex_review_gate.py — parse Codex CLI output into a PASS/FAIL verdict and
post a structured comment + label on the PR.

The review prompt instructs Codex to end its response with a line of the form:

    VERDICT: PASS
    or
    VERDICT: FAIL

…followed by a markdown section titled `## Blocking findings` containing one
bullet per finding. We tolerate small deviations (case, surrounding whitespace,
optional code-fence wrapping). If the verdict cannot be parsed at all, we
treat that as FAIL with a meta-finding so the loop never silently passes.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

COMMENT_MARKER = "<!-- codex-review -->"
VERDICT_RE = re.compile(r"verdict\s*:\s*(pass|fail)", re.IGNORECASE)


def gh(*args: str, body: str | None = None) -> str:
    cmd = ["gh", *args]
    result = subprocess.run(cmd, input=body, capture_output=True, text=True, check=True)
    return result.stdout


def parse_verdict(text: str) -> tuple[str, list[str]]:
    """Return ('PASS'|'FAIL', findings)."""
    matches = VERDICT_RE.findall(text)
    if not matches:
        return "FAIL", [
            "Could not parse a `VERDICT:` line from Codex output. "
            "Treating as FAIL by default."
        ]
    verdict = matches[-1].upper()  # last match wins

    findings: list[str] = []
    in_findings = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^#+\s*Blocking findings", stripped, re.IGNORECASE):
            in_findings = True
            continue
        if in_findings:
            if stripped.startswith("#"):
                in_findings = False  # next heading ends the section
                continue
            if re.match(r"^[-*]\s+", stripped):
                findings.append(stripped.lstrip("-* ").strip())

    if verdict == "FAIL" and not findings:
        findings = ["Codex returned FAIL but listed no specific findings."]
    return verdict, findings


def build_comment(verdict: str, findings: list[str], raw_excerpt: str) -> str:
    icon = "✅" if verdict == "PASS" else "❌"
    body = [
        COMMENT_MARKER,
        f"## {icon} Codex Review Gate: **{verdict}**",
        "",
    ]
    if verdict == "FAIL":
        body.append("### Blocking findings")
        for f in findings:
            body.append(f"- {f}")
        body.append("")
        body.append(
            "When this comment is updated, the harness will run **one** repair "
            "loop and re-review. If `loop_count` reaches its limit, the PR is "
            "labeled `needs-human`."
        )
    else:
        body.append("No blocking findings. Auto-merge will fire once CI is green "
                    "and `harness-calibrating` is removed.")
    body.append("")
    body.append("<details><summary>Raw Codex output (truncated)</summary>")
    body.append("")
    body.append("```")
    body.append(raw_excerpt[:4000])
    body.append("```")
    body.append("</details>")
    return "\n".join(body)


def upsert_comment(repo: str, pr: int, body: str) -> None:
    """Replace any prior codex-review comment, or create one if absent."""
    raw = gh("api", f"repos/{repo}/issues/{pr}/comments")
    comments = json.loads(raw)
    existing = [c for c in comments if c.get("body", "").startswith(COMMENT_MARKER)]
    body_file = Path("/tmp/_codex_comment.md")
    body_file.write_text(body)
    if existing:
        comment_id = existing[-1]["id"]
        gh("api", "--method", "PATCH",
           f"repos/{repo}/issues/comments/{comment_id}",
           "-F", f"body=@{body_file}")
    else:
        gh("pr", "comment", str(pr), "--repo", repo, "--body-file", str(body_file))


def set_labels(repo: str, pr: int, verdict: str) -> None:
    add = "codex-pass" if verdict == "PASS" else "codex-fail"
    remove = "codex-fail" if verdict == "PASS" else "codex-pass"
    gh("pr", "edit", str(pr), "--repo", repo,
       "--add-label", add, "--remove-label", remove)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--output", required=True, help="Path to Codex stdout")
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()

    raw = Path(args.output).read_text()
    verdict, findings = parse_verdict(raw)
    body = build_comment(verdict, findings, raw)
    upsert_comment(args.repo, args.pr, body)
    set_labels(args.repo, args.pr, verdict)
    print(f"Posted review: verdict={verdict}, {len(findings)} finding(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
