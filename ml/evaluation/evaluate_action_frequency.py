#!/usr/bin/env python3
"""Evaluate the deterministic action-frequency baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_frames(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    frames = load_frames(args.frames)
    model = load_json(args.model)
    actions = model.get("action_counts", {})
    known = sum(1 for frame in frames if str(frame.get("resolved_action", {}).get("command") or "unknown") in actions)
    frame_count = len(frames)
    metrics = {
        "frame_count": frame_count,
        "known_action_rate": known / frame_count if frame_count else 0.0,
        "unique_actions": len(actions),
    }
    write_json(args.metrics, metrics)
    write_json(args.report, {
        "metrics": metrics,
        "model_type": model.get("model_type"),
        "top_actions": sorted(actions.items(), key=lambda item: item[1], reverse=True)[:10],
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
