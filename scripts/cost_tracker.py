#!/usr/bin/env python3
"""cost_tracker.py — append per-call spend to .harness/spend.jsonl.

Currently log-only because `cost_cap_per_pr_usd: null` is the default. When
caps are set in .harness.yml, the merge-eligibility check should also consult
this file. (Not yet wired in v0.1 — see roadmap in README.)

Parses token-count lines emitted by Codex / Claude Code Action stdout. Token
counts are best-effort; if missing, we log a zero entry rather than crashing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

# Lightweight per-1k-token prices (USD). Update as model pricing changes.
PRICE_TABLE = {
    "claude-opus-4-7":     {"in": 0.015, "out": 0.075},
    "claude-sonnet-4-6":   {"in": 0.003, "out": 0.015},
    "claude-haiku-4-5":    {"in": 0.001, "out": 0.005},
    "o4-mini":             {"in": 0.001, "out": 0.004},
    "gpt-4o":              {"in": 0.005, "out": 0.015},
}

TOKEN_RE = re.compile(r"(input|prompt|output|completion)\s*tokens?\s*[:=]\s*(\d+)", re.IGNORECASE)
MODEL_RE = re.compile(r"model\s*[:=]\s*([A-Za-z0-9._-]+)", re.IGNORECASE)


def extract(text: str) -> dict[str, int | str]:
    counts = {"input": 0, "output": 0, "model": "unknown"}
    for kind, n in TOKEN_RE.findall(text):
        bucket = "input" if kind.lower() in {"input", "prompt"} else "output"
        counts[bucket] += int(n)
    m = MODEL_RE.search(text)
    if m:
        counts["model"] = m.group(1)
    return counts


def estimate_usd(model: str, in_tok: int, out_tok: int) -> float:
    price = PRICE_TABLE.get(model)
    if not price:
        return 0.0
    return (in_tok / 1000.0) * price["in"] + (out_tok / 1000.0) * price["out"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--source", required=True, choices=["claude", "codex"])
    p.add_argument("--input", required=True, help="Path to source stdout")
    args = p.parse_args()

    text = Path(args.input).read_text(errors="replace")
    counts = extract(text)
    usd = estimate_usd(counts["model"], counts["input"], counts["output"])

    log_dir = Path(".harness")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "spend.jsonl"
    entry = {
        "ts":     dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "pr":     args.pr,
        "source": args.source,
        "model":  counts["model"],
        "input_tokens":  counts["input"],
        "output_tokens": counts["output"],
        "usd_estimate":  round(usd, 6),
        "enforcement":   "log-only",
    }
    with log_file.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")
    print(f"Logged spend: ${usd:.4f} ({counts['model']}, in={counts['input']}, out={counts['output']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
