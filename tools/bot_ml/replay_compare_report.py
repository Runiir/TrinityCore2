from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .common import load_json, read_jsonl, table_path, write_json
except ImportError:
    from common import load_json, read_jsonl, table_path, write_json


def chosen_rows_by_decision(rows: list[dict]) -> dict[int, dict]:
    chosen: dict[int, dict] = {}
    for row in rows:
        decision_id = int(row.get("decision_id") or 0)
        if not decision_id:
            continue
        if decision_id not in chosen or int(row.get("is_chosen") or 0):
            chosen[decision_id] = row
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare shadow/assist model preferences against baseline decisions.")
    parser.add_argument("--raw-dir", type=Path, default=Path("dataset/bot_ml/raw"))
    parser.add_argument("--decision-dataset", type=Path, default=Path("dataset/bot_ml/decision_dataset.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("evaluations/bot_policy/replay_compare.json"))
    args = parser.parse_args()
    decisions = read_jsonl(table_path(args.raw_dir, "experiment_bot_decisions"))
    dataset = chosen_rows_by_decision(read_jsonl(args.decision_dataset))
    comparisons = []
    changed = 0
    for decision in decisions:
        chosen = load_json(decision.get("chosen_action_json"), {})
        trace = chosen.get("policy_model", {})
        alternatives = trace.get("top_alternatives") or []
        baseline = chosen.get("activity") or decision.get("current_activity")
        model_top = alternatives[0].get("activity") if alternatives else baseline
        if model_top and model_top != baseline:
            changed += 1
        row = dataset.get(int(decision.get("id") or 0), {})
        comparisons.append(
            {
                "trace": row.get("trace", {
                    "run_id": decision.get("run_id"),
                    "decision_id": decision.get("id"),
                    "clip_id": decision.get("clip_id"),
                    "replay_id": decision.get("replay_key"),
                    "bot_guid": decision.get("bot_guid"),
                    "brain_version": decision.get("brain_version"),
                    "model_version": trace.get("model_version"),
                    "feature_schema_version": trace.get("feature_schema_version"),
                }),
                "baseline_activity": baseline,
                "model_top_activity": model_top,
                "model_rank": trace.get("model_rank"),
                "model_score": trace.get("model_score"),
                "top_alternatives": alternatives[:3],
            }
        )
    report = {
        "decision_count": len(comparisons),
        "model_changed_activity_count": changed,
        "model_changed_activity_rate": changed / max(1, len(comparisons)),
        "comparisons": comparisons[:1000],
    }
    write_json(args.output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
