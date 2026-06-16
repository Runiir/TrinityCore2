#!/usr/bin/env python3
"""Validate raw frame JSONL files and write a normalized processed dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def iter_frames(raw_dir: Path):
    for path in sorted(raw_dir.rglob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                frame = json.loads(line)
                frame.setdefault("source_path", str(path))
                frame.setdefault("source_line", line_number)
                yield frame


def normalize_frame(frame: dict[str, Any]) -> dict[str, Any]:
    if "seq" in frame and "action" in frame:
        return {
            "episode_id": frame.get("experiment_id") or "legacy_playerbot",
            "frame_id": frame["seq"],
            "domain": "playerbot",
            "subdomain": "healer",
            "trigger": "legacy_record",
            "execution_mode": "unknown",
            "live_client_present": False,
            "actor": {
                "guid": frame.get("bot"),
                "is_bot": True,
                "role": frame.get("role"),
                "class_id": None,
                "spec_id": None,
            },
            "task": {"intent": frame.get("intent")},
            "state": {
                "map": frame.get("map"),
                "instance": frame.get("instance"),
                "bot_hp": frame.get("bot_hp"),
                "bot_mana": frame.get("bot_mana"),
                "party": frame.get("party", []),
            },
            "resolved_action": {
                "command": frame.get("action"),
                "spell": frame.get("spell"),
                "result": frame.get("result"),
            },
            "outcome": {"result": frame.get("result")},
        }
    if frame.get("event_type") or frame.get("session_id"):
        event_type = str(frame.get("event_type") or Path(str(frame.get("source_path") or "autonomy_sidecar")).stem)
        chosen = frame.get("chosen") if isinstance(frame.get("chosen"), dict) else {}
        return {
            "episode_id": frame.get("episode_id") or frame.get("session_id") or Path(str(frame.get("source_path") or "unknown")).parent.name,
            "frame_id": frame.get("frame_id") or frame.get("tick") or frame.get("source_line") or 0,
            "domain": frame.get("domain") or chosen.get("domain") or "autonomy_sidecar",
            "subdomain": frame.get("subdomain") or event_type,
            "trigger": event_type,
            "execution_mode": frame.get("execution_mode"),
            "live_client_present": bool(frame.get("live_client_present", False)),
            "actor": {
                "guid": frame.get("bot_guid"),
                "is_bot": frame.get("bot_guid") is not None,
                "role": (frame.get("persona") or {}).get("role") if isinstance(frame.get("persona"), dict) else None,
                "class_id": None,
                "spec_id": None,
            },
            "task": {
                "intent": frame.get("intent") or chosen.get("intent"),
                "domain": frame.get("domain") or chosen.get("domain"),
                "intention_id": frame.get("intention_id"),
                "candidate_id": frame.get("chosen_candidate") or chosen.get("candidate_id"),
            },
            "state": {
                "context_summary": frame.get("context_summary"),
                "group_context": frame.get("group_context"),
                "memory": frame.get("memory"),
                "persona": frame.get("persona"),
                "raw_event": frame,
            },
            "resolved_action": {
                "chosen": chosen,
                "candidate_id": frame.get("chosen_candidate") or chosen.get("candidate_id"),
                "result": frame.get("result"),
                "valid": frame.get("result") not in {"failed", "error"},
            },
            "outcome": {
                "result": frame.get("result"),
                "event_type": event_type,
                "metrics": {key: value for key, value in frame.items() if key not in {"source_path", "source_line"}},
            },
        }
    required = ["episode_id", "frame_id", "domain", "trigger"]
    missing = [field for field in required if field not in frame]
    if missing:
        raise ValueError(f"frame missing required fields: {', '.join(missing)}")
    return {
        "episode_id": frame["episode_id"],
        "frame_id": frame["frame_id"],
        "domain": frame["domain"],
        "subdomain": frame.get("subdomain"),
        "trigger": frame["trigger"],
        "execution_mode": frame.get("execution_mode"),
        "live_client_present": bool(frame.get("live_client_present", False)),
        "actor": frame.get("actor", {}),
        "task": frame.get("task", {}),
        "state": frame.get("state", {}),
        "resolved_action": frame.get("resolved_action", {}),
        "outcome": frame.get("outcome", {}),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    episodes: set[str] = set()
    frame_count = 0
    trigger_counts: dict[str, int] = {}

    with args.output.open("w", encoding="utf-8") as output:
        for frame in iter_frames(args.raw_dir):
            normalized = normalize_frame(frame)
            episodes.add(str(normalized["episode_id"]))
            frame_count += 1
            trigger = str(normalized["trigger"])
            trigger_counts[trigger] = trigger_counts.get(trigger, 0) + 1
            output.write(json.dumps(normalized, sort_keys=True, separators=(",", ":")) + "\n")

    if frame_count == 0:
        raise ValueError(f"no frames found under {args.raw_dir}")

    write_json(args.manifest, {
        "frame_count": frame_count,
        "episode_count": len(episodes),
        "episodes": sorted(episodes),
        "trigger_counts": trigger_counts,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
