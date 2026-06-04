#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build role-policy behavior cloning rows from dungeon/group frames.")
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    writers = {}
    counts: dict[str, int] = {}
    try:
        with args.frames.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                frame = json.loads(line)
                role = str(frame.get("actor", {}).get("role", "unknown"))
                if frame.get("domain") not in {"group_roles", "dungeon"} or role not in {"tank", "healer", "melee_dps", "ranged_dps"}:
                    continue
                row = {
                    "episode_id": frame.get("episode_id"),
                    "role": role,
                    "state": frame.get("state", {}),
                    "mechanic": frame.get("state", {}).get("mechanic", {}),
                    "label": frame.get("policy_output", {}),
                    "future_labels": frame.get("future_labels", {}),
                }
                path = args.output_dir / f"{role}_bc.jsonl"
                if role not in writers:
                    writers[role] = path.open("w", encoding="utf-8")
                writers[role].write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
                counts[role] = counts.get(role, 0) + 1
    finally:
        for writer in writers.values():
            writer.close()
    (args.output_dir / "manifest.json").write_text(json.dumps({"rows": counts}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
