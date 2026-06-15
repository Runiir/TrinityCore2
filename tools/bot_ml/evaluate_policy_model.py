from __future__ import annotations

import argparse
import json
from pathlib import Path

from dvclive import Live

try:
    from .common import LABELS, numeric_features, read_jsonl, summarize_bad_groups, write_json
except ImportError:
    from common import LABELS, numeric_features, read_jsonl, summarize_bad_groups, write_json


def predict(model: dict, row: dict) -> dict[str, float]:
    features = numeric_features(row)
    preds = {}
    for label in LABELS:
        value = float(model.get("means", {}).get(label, 0.0))
        for feature, weight in model.get("weights", {}).get(label, {}).items():
            value += features.get(feature, 0.0) * float(weight)
        if label != "expected_reward":
            value = max(0.0, min(1.0, value))
        preds[label] = value
    return preds


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a bot policy model on held-out run IDs.")
    parser.add_argument("--dataset", type=Path, default=Path("dataset/bot_ml/decision_dataset.jsonl"))
    parser.add_argument("--model", type=Path, default=Path("models/bot_policy/policy_model.json"))
    parser.add_argument("--metrics", type=Path, default=Path("evaluations/bot_policy/metrics.json"))
    parser.add_argument("--diagnostics", type=Path, default=Path("evaluations/bot_policy/diagnostics.json"))
    parser.add_argument("--live-dir", type=Path, default=Path("dvclive/bot_policy_eval"))
    parser.add_argument("--accept", action="store_true")
    parser.add_argument("--baseline-metrics", type=Path, help="Optional prior metrics JSON for regression comparison.")
    parser.add_argument("--min-eval-rows", type=int, default=100)
    parser.add_argument("--max-death-rate", type=float, default=0.0)
    parser.add_argument("--max-stuck-rate", type=float, default=0.0)
    parser.add_argument("--max-failure-rate", type=float, default=0.0)
    args = parser.parse_args()
    all_rows = read_jsonl(args.dataset)
    rows = [row for row in all_rows if row.get("split") == "eval"] or all_rows
    observed_rows = [row for row in rows if int(row.get("label_observed", 1) or 0)]
    metric_rows = observed_rows or rows
    model = json.loads(args.model.read_text(encoding="utf-8"))
    errors = {label: [] for label in LABELS}
    predictions = []
    for row in rows:
        pred = predict(model, row)
        predictions.append({"trace": row.get("trace", {}), "prediction": pred})
        if int(row.get("label_observed", 1) or 0):
            for label in LABELS:
                errors[label].append(abs(pred[label] - float(row.get(label, 0.0))))
    baseline = json.loads(args.baseline_metrics.read_text(encoding="utf-8")) if args.baseline_metrics and args.baseline_metrics.exists() else {}
    accepted = bool(args.accept)
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
    accepted = accepted and not acceptance_reasons

    metrics = {
        "model_version": model.get("model_version", ""),
        "eval_rows": len(metric_rows),
        "candidate_eval_rows": len(rows),
        "observed_eval_rows": len(metric_rows),
        "accepted": accepted,
        "acceptance_reasons": acceptance_reasons,
        "mae": {label: sum(values) / max(1, len(values)) for label, values in errors.items()},
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
        "deaths": summarize_bad_groups(metric_rows, "current_activity", "death_risk"),
        "stucks": summarize_bad_groups(metric_rows, "current_activity", "stuck_risk"),
        "quest_failures": summarize_bad_groups([row for row in metric_rows if float(row.get("quest_completion_likelihood", 0.0)) <= 0.0], "current_activity", "action_success"),
        "bad_areas": summarize_bad_groups(metric_rows, "zone_id", "death_risk"),
        "risky_mobs": summarize_bad_groups(metric_rows, "json_raw_target_entry", "death_risk"),
        "bad_paths": summarize_bad_groups(metric_rows, "map_id", "stuck_risk"),
        "low_confidence_decisions": [row.get("trace", {}) for row in metric_rows if float(row.get("confidence", 0.0)) < 0.25][:100],
        "candidate_rankings": predictions[:500],
        "model_regressions": [item for item in predictions if item["prediction"].get("death_risk", 0.0) > 0.5][:100],
        "feature_importance": sorted(
            [{"feature": feature, "importance": abs(weight), "label": label} for label, weights in model.get("weights", {}).items() for feature, weight in weights.items()],
            key=lambda item: -item["importance"],
        )[:50],
        "predictions": predictions[:500],
    }
    write_json(args.metrics, metrics)
    write_json(args.diagnostics, diagnostics)
    with Live(str(args.live_dir), save_dvc_exp=False, dvcyaml=False, monitor_system=False) as live:
        for key, value in metrics["mae"].items():
            live.log_metric(f"mae/{key}", value)
        live.log_metric("eval_rows", len(rows))
        live.log_metric("observed_eval_rows", len(metric_rows))
        live.log_metric("accepted", int(accepted))
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
