from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from dvclive import Live

try:
    from .common import DATASET_CONTRACT_VERSION, FEATURE_SCHEMA_VERSION, LABELS, git_commit, numeric_features, read_jsonl, split_by_run_ids, stable_hash, write_json
    from .model_artifacts import BINARY_LABELS, RANKING_LABELS, feature_vector
except ImportError:
    from common import DATASET_CONTRACT_VERSION, FEATURE_SCHEMA_VERSION, LABELS, git_commit, numeric_features, read_jsonl, split_by_run_ids, stable_hash, write_json
    from model_artifacts import BINARY_LABELS, RANKING_LABELS, feature_vector


def fit_baseline(rows: list[dict[str, Any]], features: list[str]) -> dict[str, Any]:
    train = [row for row in rows if row.get("split") != "eval" and int(row.get("label_observed", 1) or 0)]
    if not train:
        train = [row for row in rows if int(row.get("label_observed", 1) or 0)] or rows
    means = {label: sum(float(row.get(label, 0.0)) for row in train) / max(1, len(train)) for label in LABELS}
    weights = {label: {feature: 0.0 for feature in features[:256]} for label in LABELS}
    row_features = [numeric_features(row) for row in train]
    for label in LABELS:
        label_mean = means[label]
        for feature in features[:256]:
            values = [items.get(feature, 0.0) for items in row_features]
            if not values:
                continue
            feature_mean = sum(values) / len(values)
            denom = sum((value - feature_mean) ** 2 for value in values) or 1.0
            numer = sum((items.get(feature, 0.0) - feature_mean) * (float(row.get(label, 0.0)) - label_mean) for row, items in zip(train, row_features))
            weights[label][feature] = numer / denom
    return {"backend": "linear_baseline", "features": features[:256], "labels": LABELS, "means": means, "weights": weights}


def label_schema() -> dict[str, Any]:
    return {
        "labels": LABELS,
        "binary_labels": BINARY_LABELS,
        "ranking_labels": RANKING_LABELS,
        "regression_labels": ["expected_reward"],
        "version": "bot_policy_labels_v2_time_window",
    }


def split_ids_from_rows(rows: list[dict[str, Any]]) -> tuple[set[int], set[int]]:
    train_ids = {int(row.get("run_id") or 0) for row in rows if row.get("split") == "train"}
    eval_ids = {int(row.get("run_id") or 0) for row in rows if row.get("split") == "eval"}
    if train_ids or eval_ids:
        return train_ids, eval_ids
    return split_by_run_ids(rows)


def portable_feature_name(name: str, features: list[str]) -> str:
    if name.startswith("f") and name[1:].isdigit():
        index = int(name[1:])
        if 0 <= index < len(features):
            return features[index]
    return name


def flatten_xgb_node(node: dict[str, Any], out: list[dict[str, Any]], features: list[str]) -> None:
    if "leaf" in node:
        out.append({"id": int(node["nodeid"]), "leaf": float(node["leaf"])})
        return
    out.append(
        {
            "id": int(node["nodeid"]),
            "feature": portable_feature_name(str(node.get("split", "")), features),
            "threshold": float(node.get("split_condition", 0.0)),
            "yes": int(node.get("yes", 0)),
            "no": int(node.get("no", 0)),
            "missing": int(node.get("missing", node.get("yes", 0))),
        }
    )
    for child in node.get("children", []) or []:
        flatten_xgb_node(child, out, features)


def parse_booster_base_score(booster: Any, objective: str) -> float:
    try:
        config = json.loads(booster.save_config())
        raw = str(config.get("learner", {}).get("learner_model_param", {}).get("base_score", "0"))
        raw = raw.strip("[]")
        value = float(raw)
    except Exception:
        value = 0.5 if objective == "binary:logistic" else 0.0
    if objective == "binary:logistic":
        value = min(max(value, 1e-9), 1.0 - 1e-9)
        return math.log(value / (1.0 - value))
    return value


def booster_to_portable_trees(booster: Any, objective: str, features: list[str]) -> dict[str, Any]:
    trees = []
    for dumped in booster.get_dump(dump_format="json"):
        nodes: list[dict[str, Any]] = []
        flatten_xgb_node(json.loads(dumped), nodes, features)
        trees.append({"nodes": nodes})
    return {"objective": objective, "base_score": parse_booster_base_score(booster, objective), "trees": trees}


def teacher_choice_training_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    imitable_decisions = {
        int(row.get("decision_id") or 0)
        for row in rows
        if row.get("split") != "eval" and int(row.get("is_chosen") or 0) and int(row.get("imitate_teacher") or 0)
    }
    return [
        row
        for row in rows
        if row.get("split") != "eval"
        and int(row.get("decision_id") or 0) in imitable_decisions
        and int(row.get("candidate_allowed", 1) or 0)
    ]


def compact_fallback_payload(model_version: str, backend: str, features: list[str], fallback: dict[str, Any], xgb_paths: dict[str, str], portable_trees: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_format": "bot_policy_portable_v1",
        "model_version": model_version,
        "model_type": "supervised_xgboost_policy" if backend == "xgboost" else "supervised_linear_baseline",
        "backend": backend,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "dataset_contract_version": DATASET_CONTRACT_VERSION,
        "features": features,
        "labels": label_schema(),
        "tree_ensembles": portable_trees,
        "native_artifact_paths": xgb_paths,
        "fallback": fallback,
        "ranking_labels": RANKING_LABELS,
        "base_score": fallback.get("means", {}),
        "objective": {
            "action_success": "binary:logistic",
            "expected_reward": "reg:squarederror",
            "death_risk": "binary:logistic",
            "stuck_risk": "binary:logistic",
            "quest_completion_likelihood": "binary:logistic",
            "teacher_choice": "binary:logistic",
        },
    }


def train_xgboost(rows: list[dict[str, Any]], features: list[str], args: argparse.Namespace, model_dir: Path) -> tuple[str, dict[str, str], dict[str, Any], dict[str, list[dict[str, Any]]]]:
    import xgboost as xgb

    train = [row for row in rows if row.get("split") != "eval" and int(row.get("label_observed", 1) or 0)]
    if not train:
        train = [row for row in rows if int(row.get("label_observed", 1) or 0)] or rows
    x_train = [feature_vector(row, features) for row in train]
    paths: dict[str, str] = {}
    portable_trees: dict[str, Any] = {}
    importance: dict[str, list[dict[str, Any]]] = {}
    for label in LABELS:
        y_train = [float(row.get(label, 0.0)) for row in train]
        sample_weight: list[float] | None = None
        if label in BINARY_LABELS:
            classes = {int(value > 0.5) for value in y_train}
            if len(classes) < 2:
                observed_class = next(iter(classes)) if classes else 0
                x_train_label = list(x_train) + [[0.0 for _ in features]]
                y_train_label = list(y_train) + [0.0 if observed_class else 1.0]
                sample_weight = [1.0 for _ in y_train] + [1e-6]
            else:
                x_train_label = x_train
                y_train_label = y_train
            model = xgb.XGBClassifier(
                objective="binary:logistic",
                eval_metric="logloss",
                max_depth=args.max_depth,
                n_estimators=args.n_estimators,
                learning_rate=args.learning_rate,
                subsample=args.subsample,
                colsample_bytree=args.colsample_bytree,
                random_state=args.random_seed,
                n_jobs=1,
            )
        else:
            x_train_label = x_train
            y_train_label = y_train
            model = xgb.XGBRegressor(
                objective="reg:squarederror",
                max_depth=args.max_depth,
                n_estimators=args.n_estimators,
                learning_rate=args.learning_rate,
                subsample=args.subsample,
                colsample_bytree=args.colsample_bytree,
                random_state=args.random_seed,
                n_jobs=1,
            )
        model.fit(x_train_label, y_train_label, sample_weight=sample_weight)
        artifact = model_dir / f"{label}.ubj"
        model.save_model(artifact)
        paths[label] = artifact.name
        objective = "binary:logistic" if label in BINARY_LABELS else "reg:squarederror"
        portable_trees[label] = booster_to_portable_trees(model.get_booster(), objective, features)
        scores = model.get_booster().get_score(importance_type="gain")
        importance[label] = sorted(
            [{"feature": key, "importance": float(value)} for key, value in scores.items()],
            key=lambda item: -item["importance"],
        )
    choice_train = teacher_choice_training_rows(rows)
    if choice_train:
        x_choice = [feature_vector(row, features) for row in choice_train]
        y_choice = [float(int(row.get("is_chosen") or 0)) for row in choice_train]
        positives = sum(1 for value in y_choice if value > 0.5)
        negatives = len(y_choice) - positives
        sample_weight = [(negatives / max(1, positives)) if value > 0.5 else 1.0 for value in y_choice]
        model = xgb.XGBClassifier(
            objective="binary:logistic",
            eval_metric="logloss",
            max_depth=args.max_depth,
            n_estimators=args.n_estimators,
            learning_rate=args.learning_rate,
            subsample=args.subsample,
            colsample_bytree=args.colsample_bytree,
            random_state=args.random_seed,
            n_jobs=1,
        )
        model.fit(x_choice, y_choice, sample_weight=sample_weight)
        artifact = model_dir / "teacher_choice.ubj"
        model.save_model(artifact)
        paths["teacher_choice"] = artifact.name
        portable_trees["teacher_choice"] = booster_to_portable_trees(model.get_booster(), "binary:logistic", features)
        scores = model.get_booster().get_score(importance_type="gain")
        importance["teacher_choice"] = sorted(
            [{"feature": key, "importance": float(value)} for key, value in scores.items()],
            key=lambda item: -item["importance"],
        )
    return "xgboost", paths, portable_trees, importance


def main() -> int:
    parser = argparse.ArgumentParser(description="Train supervised autonomous bot policy models.")
    parser.add_argument("--dataset", type=Path, default=Path("dataset/bot_ml/decision_dataset.jsonl"))
    parser.add_argument("--model-dir", type=Path, default=Path("models/bot_policy"))
    parser.add_argument("--model", type=Path, default=None, help="Compatibility alias for the portable model JSON output path.")
    parser.add_argument("--model-version", default="")
    parser.add_argument("--backend", choices=["xgboost", "linear_baseline"], default="xgboost")
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--n-estimators", type=int, default=120)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--subsample", type=float, default=0.9)
    parser.add_argument("--colsample-bytree", type=float, default=0.9)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--live-dir", type=Path, default=Path("dvclive/bot_policy"))
    args = parser.parse_args()

    rows = read_jsonl(args.dataset)
    if not rows:
        raise SystemExit("decision dataset is empty")
    observed_rows = [row for row in rows if int(row.get("label_observed", 1) or 0)]
    if not observed_rows:
        raise SystemExit("decision dataset has no observed labels")

    train_ids, eval_ids = split_ids_from_rows(rows)
    model_version = args.model_version or f"policy_{git_commit()[:12] or 'local'}"
    model_root = args.model_dir / model_version if args.model_dir.name != model_version else args.model_dir
    model_root.mkdir(parents=True, exist_ok=True)
    features = sorted({key for row in observed_rows for key in numeric_features(row)})[:512]
    fallback = fit_baseline(rows, features)

    backend = args.backend
    xgb_paths: dict[str, str] = {}
    portable_trees: dict[str, Any] = {}
    feature_importance: dict[str, list[dict[str, Any]]] = {"linear_baseline": []}
    if backend == "xgboost":
        backend, xgb_paths, portable_trees, feature_importance = train_xgboost(rows, features, args, model_root)

    portable = compact_fallback_payload(model_version, backend, features, fallback, xgb_paths, portable_trees)
    portable.update(
        {
            "git_commit": git_commit(),
            "dataset_path": str(args.dataset),
            "train_run_ids": sorted(train_ids),
            "eval_run_ids": sorted(eval_ids),
            "runtime_ml_control": "disabled_until_shadow_assist_replay_validation_beats_teacher",
            "control_eligible": False,
        }
    )
    portable_path = args.model or (model_root / "model.json")
    write_json(portable_path, portable)
    if portable_path != model_root / "model.json":
        write_json(model_root / "model.json", portable)

    feature_schema = {"version": FEATURE_SCHEMA_VERSION, "features": features, "feature_hash": stable_hash(features)}
    manifest = {
        "model_version": model_version,
        "model_type": portable["model_type"],
        "backend": backend,
        "git_commit": git_commit(),
        "dataset_path": str(args.dataset),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "dataset_contract_version": DATASET_CONTRACT_VERSION,
        "label_schema": label_schema(),
        "ranking_labels": RANKING_LABELS,
        "train_run_ids": sorted(train_ids),
        "eval_run_ids": sorted(eval_ids),
        "artifact_paths": {"portable": "model.json", **xgb_paths},
        "features": features,
    }
    summary = {
        "model_version": model_version,
        "backend": backend,
        "dataset_rows": len(rows),
        "observed_label_rows": len(observed_rows),
        "imitable_teacher_rows": sum(1 for row in observed_rows if int(row.get("imitate_teacher") or 0)),
        "filtered_teacher_rows": sum(1 for row in observed_rows if not int(row.get("imitate_teacher") or 0)),
        "teacher_choice_train_rows": len(teacher_choice_training_rows(rows)),
        "train_run_ids": sorted(train_ids),
        "eval_run_ids": sorted(eval_ids),
        "runtime_ml_control": "disabled_until_shadow_assist_replay_validation_beats_teacher",
        "control_eligible": False,
        "label_means": {label: sum(float(row.get(label, 0.0)) for row in observed_rows) / max(1, len(observed_rows)) for label in LABELS},
    }
    write_json(model_root / "model_manifest.json", manifest)
    write_json(model_root / "feature_schema.json", feature_schema)
    write_json(model_root / "label_schema.json", label_schema())
    write_json(model_root / "training_summary.json", summary)
    write_json(model_root / "feature_importance.json", feature_importance)

    with Live(str(args.live_dir), save_dvc_exp=False, dvcyaml=False, monitor_system=False) as live:
        live.log_metric("dataset_rows", len(rows))
        live.log_metric("observed_label_rows", len(observed_rows))
        live.log_param("model_version", model_version)
        live.log_param("backend", backend)

    print(json.dumps({"model_dir": str(model_root), "model": str(model_root / "model.json"), "model_version": model_version, "backend": backend}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
