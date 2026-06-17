from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from .common import LABELS, read_jsonl, write_json
except ImportError:
    from common import LABELS, read_jsonl, write_json


TRACEABILITY_FIELDS = [
    "run_id",
    "decision_id",
    "event_ids_used_for_label",
    "clip_id",
    "replay_id",
    "bot_guid",
    "brain_version",
    "model_version",
    "feature_schema_version",
]

REQUIRED_FIELDS = {
    "run_id",
    "decision_id",
    "bot_guid",
    "brain_version",
    "feature_schema_version",
    "candidate_index",
    "candidate_count",
    "candidate_activity",
    "candidate_action_hash",
    "features_hash",
    "split",
    "is_chosen",
    "label_observed",
    "label_window_json",
    "label_reason",
    "event_ids_used_for_label",
    "trace",
    "imitate_teacher",
    "imitation_weight",
    "teacher_action_quality",
    *LABELS,
}

ALLOWED_TEACHER_QUALITIES = {
    "verified_teacher_action",
    "candidate_unobserved",
    "unsafe_teacher_action",
    "ambiguous_teacher_action",
    "unverified_teacher_action",
    "failed_teacher_action",
}


def nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value != ""
    return True


def parse_json_object(value: Any) -> bool:
    if isinstance(value, dict):
        return True
    if isinstance(value, str) and value:
        try:
            return isinstance(json.loads(value), dict)
        except json.JSONDecodeError:
            return False
    return False


def is_event_id_list(value: Any) -> bool:
    if isinstance(value, list):
        return all(isinstance(item, int) for item in value)
    return False


def group_by_decision(rows: list[dict[str, Any]]) -> dict[tuple[Any, Any, Any], list[dict[str, Any]]]:
    grouped: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row.get("run_id"), row.get("bot_guid"), row.get("decision_id"))
        grouped.setdefault(key, []).append(row)
    return grouped


def validate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    required = REQUIRED_FIELDS
    missing = {key: 0 for key in sorted(required)}
    for row in rows:
        for key in required:
            if key not in row or not nonempty(row[key]):
                missing[key] += 1

    grouped = group_by_decision(rows)
    observed_rows = [row for row in rows if int(row.get("label_observed") or 0)]
    chosen_rows = [row for row in rows if int(row.get("is_chosen") or 0)]
    imitable_rows = [row for row in observed_rows if int(row.get("imitate_teacher") or 0)]
    filtered_rows = [row for row in observed_rows if not int(row.get("imitate_teacher") or 0)]
    train_ids = {row.get("run_id") for row in rows if row.get("split") == "train"}
    eval_ids = {row.get("run_id") for row in rows if row.get("split") == "eval"}
    train_eval_run_overlap = sorted(train_ids & eval_ids)

    decision_errors = {
        "decisions_without_exactly_one_chosen": 0,
        "decisions_without_exactly_one_observed_label": 0,
        "candidate_count_mismatch": 0,
        "unchosen_rows_with_nonzero_labels": 0,
    }
    for decision_rows in grouped.values():
        if sum(int(row.get("is_chosen") or 0) for row in decision_rows) != 1:
            decision_errors["decisions_without_exactly_one_chosen"] += 1
        if sum(int(row.get("label_observed") or 0) for row in decision_rows) != 1:
            decision_errors["decisions_without_exactly_one_observed_label"] += 1
        expected_count = len(decision_rows)
        if any(int(row.get("candidate_count") or 0) != expected_count for row in decision_rows):
            decision_errors["candidate_count_mismatch"] += 1
        for row in decision_rows:
            if int(row.get("is_chosen") or 0):
                continue
            if any(float(row.get(label) or 0.0) != 0.0 for label in LABELS):
                decision_errors["unchosen_rows_with_nonzero_labels"] += 1
                break

    traceability_errors = {
        "missing_trace_fields": 0,
        "invalid_event_ids": 0,
        "invalid_label_window_json": 0,
        "empty_features_hash": 0,
        "empty_candidate_hash": 0,
    }
    for row in rows:
        trace = row.get("trace") if isinstance(row.get("trace"), dict) else {}
        if any(field not in trace for field in TRACEABILITY_FIELDS):
            traceability_errors["missing_trace_fields"] += 1
        if not is_event_id_list(row.get("event_ids_used_for_label")):
            traceability_errors["invalid_event_ids"] += 1
        if not parse_json_object(row.get("label_window_json")):
            traceability_errors["invalid_label_window_json"] += 1
        if not nonempty(row.get("features_hash")):
            traceability_errors["empty_features_hash"] += 1
        if not nonempty(row.get("candidate_action_hash")):
            traceability_errors["empty_candidate_hash"] += 1

    teacher_contract_errors = {
        "imitable_rows_not_verified": 0,
        "verified_rows_not_imitable": 0,
        "filtered_chosen_rows_without_failure_label": 0,
        "unobserved_rows_marked_imitable": 0,
        "invalid_teacher_quality": 0,
    }
    for row in rows:
        quality = str(row.get("teacher_action_quality") or "")
        if quality not in ALLOWED_TEACHER_QUALITIES:
            teacher_contract_errors["invalid_teacher_quality"] += 1
        if int(row.get("imitate_teacher") or 0) and quality != "verified_teacher_action":
            teacher_contract_errors["imitable_rows_not_verified"] += 1
        if quality == "verified_teacher_action" and int(row.get("label_observed") or 0) and not int(row.get("imitate_teacher") or 0):
            teacher_contract_errors["verified_rows_not_imitable"] += 1
        if not int(row.get("label_observed") or 0) and int(row.get("imitate_teacher") or 0):
            teacher_contract_errors["unobserved_rows_marked_imitable"] += 1
        if int(row.get("label_observed") or 0) and not int(row.get("imitate_teacher") or 0) and quality != "candidate_unobserved" and not str(row.get("failure_label") or ""):
            teacher_contract_errors["filtered_chosen_rows_without_failure_label"] += 1

    leakage_errors = {
        "train_eval_run_overlap": train_eval_run_overlap,
        "missing_train_split": not bool(train_ids),
        "missing_eval_split": not bool(eval_ids),
    }
    contract_errors = {
        **decision_errors,
        **traceability_errors,
        **teacher_contract_errors,
        "train_eval_run_overlap": len(train_eval_run_overlap),
        "missing_train_split": int(leakage_errors["missing_train_split"]),
        "missing_eval_split": int(leakage_errors["missing_eval_split"]),
    }
    report = {
        "rows": len(rows),
        "candidate_rows": len(rows),
        "decision_count": len(grouped),
        "observed_label_rows": len(observed_rows),
        "chosen_rows": len(chosen_rows),
        "imitable_teacher_rows": len(imitable_rows),
        "filtered_teacher_rows": len(filtered_rows),
        "teacher_action_quality": dict(Counter(str(row.get("teacher_action_quality") or "") for row in observed_rows)),
        "failure_labels": dict(Counter(str(row.get("failure_label") or "") for row in filtered_rows if row.get("failure_label"))),
        "run_count": len({row.get("run_id") for row in rows}),
        "missing": missing,
        "decision_contract": decision_errors,
        "traceability_contract": traceability_errors,
        "teacher_filter_contract": teacher_contract_errors,
        "leakage_contract": leakage_errors,
        "contract_errors": contract_errors,
        "ok": bool(rows)
        and bool(observed_rows)
        and all(value == 0 for value in missing.values())
        and all(value == 0 for key, value in contract_errors.items() if key != "train_eval_run_overlap")
        and not train_eval_run_overlap,
        "leakage_guard": "split is by run_id; train/eval rows should not share run_id",
        "runtime_ml_control": "disabled_until_shadow_assist_replay_validation_passes",
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate autonomous bot ML dataset quality.")
    parser.add_argument("--dataset", type=Path, default=Path("dataset/bot_ml/decision_dataset.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("dataset/bot_ml/data_quality.json"))
    args = parser.parse_args()
    rows = read_jsonl(args.dataset)
    report = validate_rows(rows)
    write_json(args.report, report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
