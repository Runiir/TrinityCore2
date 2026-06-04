#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a tiny role-policy BC baseline by action frequency.")
    parser.add_argument("--role", required=True, choices=["tank", "healer", "melee_dps", "ranged_dps"])
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    counts: Counter[str] = Counter()
    rows = 0
    with args.frames.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            label = row.get("label", {})
            counts[str(label.get("mode", "hold"))] += 1
            rows += 1
    args.model.parent.mkdir(parents=True, exist_ok=True)
    args.model.write_text(json.dumps({"kind": "role_action_frequency", "role": args.role, "rows": rows, "mode_counts": dict(counts), "default_mode": counts.most_common(1)[0][0] if counts else "hold"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
