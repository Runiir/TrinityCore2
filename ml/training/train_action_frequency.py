#!/usr/bin/env python3
"""Train a deterministic action-frequency baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_frames(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()

    frames = load_frames(args.frames)
    counts: dict[str, int] = {}
    for frame in frames:
        command = frame.get("resolved_action", {}).get("command") or "unknown"
        counts[str(command)] = counts.get(str(command), 0) + 1

    total = sum(counts.values())
    model = {
        "model_type": "action_frequency_baseline",
        "frame_count": len(frames),
        "action_counts": counts,
        "action_probabilities": {key: value / total for key, value in sorted(counts.items())} if total else {},
    }
    args.model.parent.mkdir(parents=True, exist_ok=True)
    with args.model.open("w", encoding="utf-8") as handle:
        json.dump(model, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
