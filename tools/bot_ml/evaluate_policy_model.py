from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from dvclive import Live

try:
    from .common import LABELS, read_jsonl, summarize_bad_groups, write_json
    from .model_artifacts import BINARY_LABELS, attach_base_dir, load_model_artifact, predict_artifact
except ImportError:
    from common import LABELS, read_jsonl, summarize_bad_groups, write_json
    from model_artifacts import BINARY_LABELS, attach_base_dir, load_model_artifact, predict_artifact


def auc_score(y_true: list[int], y_score: list[float]) -> float | None:
    pairs = sorted(zip(y_score, y_true), key=lambda item: item[0])
    pos = sum(y_true)
    neg = len(y_true) - pos
    if pos == 0 or neg == 0:
        return None
    rank_sum = sum(rank for rank, (_, label) in enumerate(pairs, start=1) if label == 1)
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def binary_metrics(rows: list[dict[str, Any]], preds: dict[int, dict[str, float]], label: str) -> dict[str, Any]:
    y_true = [1 if float(row.get(label, 0.0)) > 0.5 else 0 for row in rows]
    y_score = [float(preds[id(row)][label]) for row in rows]
    y_hat = [1 if score >= 0.5 else 0 for score in y_score]
    tp = sum(1 for a, b in zip(y_true, y_hat) if a == 1 and b == 1)
    tn = sum(1 for a, b in zip(y_true, y_hat) if a == 0 and b == 0)
    fp = sum(1 for a, b in zip(y_true, y_hat) if a == 0 and b == 1)
    fn = sum(1 for a, b in zip(y_true, y_hat) if a == 1 and b == 0)
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(1e-9, precision + recall)
    return {
        "auc": auc_score(y_true, y_score),
        "accuracy": (tp + tn) / max(1, len(rows)),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "positive_rate": sum(y_true) / max(1, len(y_true)),
    }


def reward_metrics(rows: list[dict[str, Any]], preds: dict[int, dict[str, float]]) -> dict[str, float]:
    errors = [float(preds[id(row)]["expected_reward"]) - float(row.get("expected_reward", 0.0)) for row in rows]
    return {
        "mae": sum(abs(error) for error in errors) / max(1, len(errors)),
        "rmse": math.sqrt(sum(error * error for error in errors) / max(1, len(errors))),
    }


def policy_score(pred: dict[str, float]) -> float:
    return pred.get("expected_reward", 0.0) + pred.get("action_success", 0.0) + pred.get("quest_completion_likelihood", 0.0) - pred.get("death_risk", 0.0) - pred.get("stuck_risk", 0.0)


def ranking_metrics(rows: list[dict[str, Any]], preds: dict[int, dict[str, float]]) -> dict[str, Any]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row.get("decision_id") or 0)].append(row)
    top1 = 0
    top3 = 0
    changed = 0
    bad = 0
    ranked_traces = []
    total = 0
    for decision_id, items in grouped.items():
        if not items:
            continue
        ranked = sorted(items, key=lambda row: policy_score(preds[id(row)]), reverse=True)
        chosen_index = next((index for index, row in enumerate(ranked) if row.get("is_chosen")), None)
        if chosen_index is None:
            continue
        total += 1
        top1 += int(chosen_index == 0)
        top3 += int(chosen_index < 3)
        changed += int(chosen_index != 0)
        top_pred = preds[id(ranked[0])]
        bad += int(top_pred.get("death_risk", 0.0) >= 0.5 or top_pred.get("stuck_risk", 0.0) >= 0.5 or top_pred.get("action_success", 0.0) < 0.5)
        ranked_traces.append({"decision_id": decision_id, "chosen_rank": chosen_index + 1, "trace": ranked[chosen_index].get("trace", {}), "top_prediction": top_pred})
    return {
        "top_1_candidate_ranking_accuracy": top1 / max(1, total),
        "top_3_candidate_ranking_accuracy": top3 / max(1, total),
        "bad_action_rate": bad / max(1, total),
        "model_changed_activity_rate": changed / max(1, total),
        "ranked_traces": ranked_traces[:500],
    }


def calibration(rows: list[dict[str, Any]], preds: dict[int, dict[str, float]], label: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        pred = float(preds[id(row)][label])
        bucket = f"{min(9, int(pred * 10)) / 10:.1f}-{(min(9, int(pred * 10)) + 1) / 10:.1f}"
        buckets[bucket].append((pred, float(row.get(label, 0.0))))
    return [
        {"bucket": bucket, "count": len(values), "predicted_mean": sum(v[0] for v in values) / len(values), "observed_rate": sum(v[1] for v in values) / len(values)}
        for bucket, values in sorted(buckets.items())
        if values
    ]


def confidence_bucket(row: dict[str, Any]) -> str:
    value = float(row.get("confidence", 0.0))
    if value < 0.25:
        return "0.00-0.25"
    if value < 0.5:
        return "0.25-0.50"
    if value < 0.75:
        return "0.50-0.75"
    return "0.75-1.00"


def grouped_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    enriched = []
    for row in rows:
        copy = dict(row)
        copy["level_bracket"] = int(float(row.get("json_raw_level", row.get("level", 0)) or 0) // 10 * 10)
        copy["confidence_bucket"] = confidence_bucket(row)
        enriched.append(copy)
    return {
        "by_area": summarize_bad_groups(enriched, "area_id", "death_risk"),
        "by_zone": summarize_bad_groups(enriched, "zone_id", "death_risk"),
        "by_mob": summarize_bad_groups(enriched, "json_raw_target_entry", "death_risk"),
        "by_quest": summarize_bad_groups(enriched, "json_raw_quest_id", "quest_completion_likelihood"),
        "by_activity": summarize_bad_groups(enriched, "current_activity", "action_success"),
        "by_class": summarize_bad_groups(enriched, "json_raw_class", "action_success"),
        "by_level_bracket": summarize_bad_groups(enriched, "level_bracket", "death_risk"),
        "by_confidence_bucket": summarize_bad_groups(enriched, "confidence_bucket", "action_success"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a bot policy model on held-out run IDs.")
    parser.add_argument("--dataset", type=Path, default=Path("dataset/bot_ml/decision_dataset.jsonl"))
    parser.add_argument("--model", type=Path, default=Path("models/bot_policy/policy_model.json"))
    parser.add_argument("--metrics", type=Path, default=Path("evaluations/bot_policy/metrics.json"))
    parser.add_argument("--diagnostics", type=Path, default=Path("evaluations/bot_policy/diagnostics.json"))
    parser.add_argument("--live-dir", type=Path, default=Path("dvclive/bot_policy_eval"))
    parser.add_argument("--accept", action="store_true")
    parser.add_argument("--baseline-metrics", type=Path)
    parser.add_argument("--min-eval-rows", type=int, default=100)
    parser.add_argument("--max-death-rate", type=float, default=0.0)
    parser.add_argument("--max-stuck-rate", type=float, default=0.0)
    parser.add_argument("--max-failure-rate", type=float, default=0.0)
    args = parser.parse_args()

    all_rows = read_jsonl(args.dataset)
    rows = [row for row in all_rows if row.get("split") == "eval"] or all_rows
    observed_rows = [row for row in rows if int(row.get("label_observed", 1) or 0)]
    metric_rows = observed_rows or rows
    model = attach_base_dir(load_model_artifact(args.model), args.model)
    preds = {id(row): predict_artifact(model, row) for row in rows}
    observed_preds = {id(row): preds[id(row)] for row in metric_rows}

    binary = {label: binary_metrics(metric_rows, observed_preds, label) for label in BINARY_LABELS}
    reward = reward_metrics(metric_rows, observed_preds)
    ranking = ranking_metrics(rows, preds)
    baseline = json.loads(args.baseline_metrics.read_text(encoding="utf-8")) if args.baseline_metrics and args.baseline_metrics.exists() else {}
    acceptance_reasons = []
    if len(metric_rows) < args.min_eval_rows:
        acceptance_reasons.append("insufficient_eval_rows")
    death_rate = sum(float(row.get("death_risk", 0.0)) for row in metric_rows) / max(1, len(metric_rows))
    stuck_rate = sum(float(row.get("stuck_risk", 0.0)) for row in metric_rows) / max(1, len(metric_rows))
    failure_rate = sum(1.0 - float(row.get("action_success", 0.0)) for row in metric_rows) / max(1, len(metric_rows))
    if baseline:
        for key, value in [("death_rate", death_rate), ("stuck_rate", stuck_rate), ("failure_rate", failure_rate)]:
            if key in baseline and value > float(baseline[key]):
                acceptance_reasons.append(f"{key}_regression")
    if death_rate > args.max_death_rate:
        acceptance_reasons.append("death_rate_above_limit")
    if stuck_rate > args.max_stuck_rate:
        acceptance_reasons.append("stuck_rate_above_limit")
    if failure_rate > args.max_failure_rate:
        acceptance_reasons.append("failure_rate_above_limit")
    accepted = bool(args.accept) and not acceptance_reasons

    control_eligible = False
    runtime_ml_control = "disabled_until_shadow_assist_replay_validation_beats_teacher"
    metrics = {
        "model_version": model.get("model_version", ""),
        "backend": model.get("backend", ""),
        "eval_rows": len(metric_rows),
        "candidate_eval_rows": len(rows),
        "observed_eval_rows": len(metric_rows),
        "accepted": accepted,
        "control_eligible": control_eligible,
        "runtime_ml_control": runtime_ml_control,
        "acceptance_reasons": acceptance_reasons,
        "binary": binary,
        "expected_reward": reward,
        "ranking": {key: value for key, value in ranking.items() if key != "ranked_traces"},
        "death_rate": death_rate,
        "stuck_rate": stuck_rate,
        "failure_rate": failure_rate,
        "acceptance_thresholds": {
            "min_eval_rows": args.min_eval_rows,
            "max_death_rate": args.max_death_rate,
            "max_stuck_rate": args.max_stuck_rate,
            "max_failure_rate": args.max_failure_rate,
        },
    }
    diagnostics = {
        "traceability_fields": ["run_id", "decision_id", "event_ids_used_for_label", "clip_id", "replay_id", "bot_guid", "brain_version", "model_version", "feature_schema_version"],
        "death_risk_calibration": calibration(metric_rows, observed_preds, "death_risk"),
        "stuck_risk_calibration": calibration(metric_rows, observed_preds, "stuck_risk"),
        "quest_completion_calibration": calibration(metric_rows, observed_preds, "quest_completion_likelihood"),
        "grouped": grouped_diagnostics(metric_rows),
        "ranked_traces": ranking["ranked_traces"],
        "runtime_ml_control": runtime_ml_control,
        "control_eligible": control_eligible,
        "predictions": [{"trace": row.get("trace", {}), "prediction": preds[id(row)]} for row in rows[:500]],
    }
    write_json(args.metrics, metrics)
    write_json(args.diagnostics, diagnostics)
    with Live(str(args.live_dir), save_dvc_exp=False, dvcyaml=False, monitor_system=False) as live:
        live.log_metric("eval_rows", len(metric_rows))
        live.log_metric("accepted", int(accepted))
        live.log_metric("expected_reward_mae", reward["mae"])
        live.log_metric("top_1_candidate_ranking_accuracy", metrics["ranking"]["top_1_candidate_ranking_accuracy"])
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
