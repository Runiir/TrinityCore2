from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

try:
    from .common import LABELS, numeric_features
except ImportError:
    from common import LABELS, numeric_features


BINARY_LABELS = [label for label in LABELS if label != "expected_reward"]
RANKING_LABELS = ["teacher_choice"]


def prediction_labels(model: dict[str, Any]) -> list[str]:
    labels = list(LABELS)
    for label in model.get("ranking_labels", []):
        if label not in labels:
            labels.append(str(label))
    return labels


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def feature_vector(row: dict[str, Any], features: list[str]) -> list[float]:
    values = numeric_features(row)
    return [float(values.get(feature, 0.0)) for feature in features]


def baseline_predict(model: dict[str, Any], row: dict[str, Any]) -> dict[str, float]:
    values = numeric_features(row)
    preds: dict[str, float] = {}
    fallback = model.get("fallback", model)
    for label in prediction_labels(model):
        value = float(fallback.get("means", {}).get(label, 0.0))
        for feature, weight in fallback.get("weights", {}).get(label, {}).items():
            value += values.get(feature, 0.0) * float(weight)
        if label != "expected_reward":
            value = max(0.0, min(1.0, value))
        preds[label] = value
    return preds


def eval_tree(tree: dict[str, Any], features: dict[str, float]) -> float:
    nodes = {int(node.get("id", 0)): node for node in tree.get("nodes", [])}
    node_id = 0
    for _ in range(1024):
        node = nodes.get(node_id)
        if not node:
            return 0.0
        if "leaf" in node:
            return float(node.get("leaf", 0.0))
        feature = str(node.get("feature", ""))
        value = features.get(feature)
        if value is None or not math.isfinite(float(value)):
            node_id = int(node.get("missing", node.get("yes", 0)))
        elif float(value) < float(node.get("threshold", 0.0)):
            node_id = int(node.get("yes", 0))
        else:
            node_id = int(node.get("no", 0))
    return 0.0


def portable_tree_predict(model: dict[str, Any], row: dict[str, Any]) -> dict[str, float] | None:
    ensembles = model.get("tree_ensembles")
    if not isinstance(ensembles, dict) or not ensembles:
        return None
    features = numeric_features(row)
    preds: dict[str, float] = {}
    for label in prediction_labels(model):
        ensemble = ensembles.get(label)
        if not isinstance(ensemble, dict):
            return None
        value = float(ensemble.get("base_score", 0.0))
        for tree in ensemble.get("trees", []) or []:
            if isinstance(tree, dict):
                value += eval_tree(tree, features)
        if ensemble.get("objective") == "binary:logistic":
            value = sigmoid(value)
        preds[label] = value
    return preds


def load_model_artifact(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "artifact_format" in payload or "fallback" in payload or "weights" in payload:
        return payload
    manifest = payload
    compact = manifest.get("portable_artifact_path") or manifest.get("artifact_paths", {}).get("portable")
    if compact:
        compact_path = Path(compact)
        if not compact_path.is_absolute():
            compact_path = path.parent / compact_path
        if compact_path.exists():
            return json.loads(compact_path.read_text(encoding="utf-8"))
    return payload


def predict_artifact(model: dict[str, Any], row: dict[str, Any]) -> dict[str, float]:
    backend = model.get("backend", "")
    if backend != "xgboost":
        return baseline_predict(model, row)
    try:
        import xgboost as xgb
    except Exception:
        portable = portable_tree_predict(model, row)
        return portable if portable is not None else baseline_predict(model, row)

    features = list(model.get("features") or model.get("feature_list") or [])
    paths = model.get("native_artifact_paths") or model.get("artifact_paths", {})
    base_dir = Path(str(model.get("_base_dir", ".")))
    preds: dict[str, float] = {}
    vector = feature_vector(row, features)
    dmatrix = xgb.DMatrix([vector], feature_names=features)
    for label in prediction_labels(model):
        model_path = paths.get(label)
        if not model_path:
            portable = portable_tree_predict(model, row)
            return portable if portable is not None else baseline_predict(model, row)
        path = Path(model_path)
        if not path.is_absolute():
            path = base_dir / path
        if not path.exists():
            portable = portable_tree_predict(model, row)
            return portable if portable is not None else baseline_predict(model, row)
        booster = xgb.Booster()
        booster.load_model(str(path))
        preds[label] = float(booster.predict(dmatrix)[0])
    return preds


def attach_base_dir(model: dict[str, Any], path: Path) -> dict[str, Any]:
    model["_base_dir"] = str(path.parent)
    return model
