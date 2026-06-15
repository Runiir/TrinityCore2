from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .common import read_jsonl, write_json
except ImportError:
    from common import read_jsonl, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Explain decisions and failures for a recorded bot run.")
    parser.add_argument("--dataset", type=Path, default=Path("dataset/bot_ml/decision_dataset.jsonl"))
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--output", type=Path, default=Path("evaluations/bot_policy/run_explain.json"))
    args = parser.parse_args()
    rows = [row for row in read_jsonl(args.dataset) if int(row.get("run_id") or 0) == args.run_id]
    observed = [row for row in rows if int(row.get("label_observed", 1) or 0)]
    decision_ids = {row.get("decision_id") for row in rows}
    report = {
        "run_id": args.run_id,
        "decision_count": len(decision_ids),
        "candidate_row_count": len(rows),
        "observed_label_rows": len(observed),
        "failures": [row.get("trace", {}) for row in observed if float(row.get("action_success", 1.0)) < 0.5],
        "deaths": [row.get("trace", {}) for row in observed if float(row.get("death_risk", 0.0)) > 0.5],
        "stucks": [row.get("trace", {}) for row in observed if float(row.get("stuck_risk", 0.0)) > 0.5],
        "low_confidence": [row.get("trace", {}) for row in observed if float(row.get("confidence", 0.0)) < 0.25],
        "candidate_rows": [
            {
                "trace": row.get("trace", {}),
                "activity": row.get("current_activity"),
                "candidate_activity": row.get("candidate_activity"),
                "is_chosen": bool(row.get("is_chosen")),
                "utility_score": row.get("utility_score"),
                "learned_score": row.get("learned_score"),
                "danger_score": row.get("danger_score"),
                "confidence": row.get("confidence"),
                "labels": {
                    "action_success": row.get("action_success"),
                    "death_risk": row.get("death_risk"),
                    "stuck_risk": row.get("stuck_risk"),
                    "quest_completion_likelihood": row.get("quest_completion_likelihood"),
                },
            }
            for row in rows[:500]
        ],
    }
    write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "decision_count": len(decision_ids), "candidate_row_count": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
