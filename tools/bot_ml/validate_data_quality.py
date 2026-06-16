from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

try:
    from .common import LABELS, read_jsonl, write_json
except ImportError:
    from common import LABELS, read_jsonl, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate autonomous bot ML dataset quality.")
    parser.add_argument("--dataset", type=Path, default=Path("dataset/bot_ml/decision_dataset.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("dataset/bot_ml/data_quality.json"))
    args = parser.parse_args()
    rows = read_jsonl(args.dataset)
    required = {"run_id", "decision_id", "bot_guid", "brain_version", "feature_schema_version", "candidate_index", "is_chosen", "label_observed", "imitate_teacher", "imitation_weight", "teacher_action_quality", *LABELS}
    missing = {key: 0 for key in required}
    for row in rows:
        for key in required:
            if key not in row or row[key] in (None, ""):
                missing[key] += 1
    run_ids = {row.get("run_id") for row in rows}
    observed_rows = [row for row in rows if int(row.get("label_observed") or 0)]
    imitable_rows = [row for row in observed_rows if int(row.get("imitate_teacher") or 0)]
    filtered_rows = [row for row in observed_rows if not int(row.get("imitate_teacher") or 0)]
    report = {
        "rows": len(rows),
        "candidate_rows": len(rows),
        "observed_label_rows": len(observed_rows),
        "imitable_teacher_rows": len(imitable_rows),
        "filtered_teacher_rows": len(filtered_rows),
        "teacher_action_quality": dict(Counter(str(row.get("teacher_action_quality") or "") for row in observed_rows)),
        "failure_labels": dict(Counter(str(row.get("failure_label") or "") for row in filtered_rows if row.get("failure_label"))),
        "run_count": len(run_ids),
        "missing": missing,
        "ok": bool(rows) and bool(observed_rows) and all(value == 0 for value in missing.values()) and len(run_ids) >= 1,
        "leakage_guard": "split is by run_id; train/eval rows should not share run_id",
    }
    train_ids = {row.get("run_id") for row in rows if row.get("split") == "train"}
    eval_ids = {row.get("run_id") for row in rows if row.get("split") == "eval"}
    report["train_eval_run_overlap"] = sorted(train_ids & eval_ids)
    write_json(args.report, report)
    return 0 if report["ok"] and not report["train_eval_run_overlap"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
