from __future__ import annotations

import argparse
import json
from pathlib import Path

from dvclive import Live

try:
    from .common import FEATURE_SCHEMA_VERSION, LABELS, git_commit, numeric_features, read_jsonl, split_by_run_ids, write_json
except ImportError:
    from common import FEATURE_SCHEMA_VERSION, LABELS, git_commit, numeric_features, read_jsonl, split_by_run_ids, write_json


def fit_baseline(rows: list[dict]) -> dict:
    train = [row for row in rows if row.get("split") != "eval" and int(row.get("label_observed", 1) or 0)]
    if not train:
        train = [row for row in rows if int(row.get("label_observed", 1) or 0)] or rows
    features = sorted({key for row in train for key in numeric_features(row)})
    means = {label: sum(float(row.get(label, 0.0)) for row in train) / max(1, len(train)) for label in LABELS}
    weights = {label: {feature: 0.0 for feature in features[:256]} for label in LABELS}
    for label in LABELS:
        label_mean = means[label]
        for feature in features[:256]:
            values = [numeric_features(row).get(feature, 0.0) for row in train]
            if not values:
                continue
            feature_mean = sum(values) / len(values)
            denom = sum((value - feature_mean) ** 2 for value in values) or 1.0
            numer = sum((numeric_features(row).get(feature, 0.0) - feature_mean) * (float(row.get(label, 0.0)) - label_mean) for row in train)
            weights[label][feature] = numer / denom
    return {"backend": "linear_baseline", "features": features[:256], "labels": LABELS, "means": means, "weights": weights}


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the first supervised autonomous bot policy model.")
    parser.add_argument("--dataset", type=Path, default=Path("dataset/bot_ml/decision_dataset.jsonl"))
    parser.add_argument("--model", type=Path, default=Path("models/bot_policy/policy_model.json"))
    parser.add_argument("--model-version", default="")
    parser.add_argument("--live-dir", type=Path, default=Path("dvclive/bot_policy"))
    args = parser.parse_args()
    rows = read_jsonl(args.dataset)
    if not rows:
        raise SystemExit("decision dataset is empty")
    observed_rows = [row for row in rows if int(row.get("label_observed", 1) or 0)]
    if not observed_rows:
        raise SystemExit("decision dataset has no observed labels")
    train_ids, eval_ids = split_by_run_ids(rows)
    model = fit_baseline(rows)
    model_version = args.model_version or f"bot_policy_{git_commit()[:12] or 'local'}"
    model.update(
        {
            "model_version": model_version,
            "model_type": "supervised_linear_baseline",
            "git_commit": git_commit(),
            "dataset_path": str(args.dataset),
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "label_schema": LABELS,
            "train_run_ids": sorted(train_ids),
            "eval_run_ids": sorted(eval_ids),
        }
    )
    write_json(args.model, model)
    with Live(str(args.live_dir), save_dvc_exp=False, dvcyaml=False, monitor_system=False) as live:
        live.log_metric("dataset_rows", len(rows))
        live.log_metric("observed_label_rows", len(observed_rows))
        live.log_param("model_version", model_version)
        live.log_param("model_type", model["model_type"])
    print(json.dumps({"model": str(args.model), "model_version": model_version}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
