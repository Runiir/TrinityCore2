from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

EXPORT_TABLES = [
    "experiment_bot_runs",
    "experiment_bot_segments",
    "experiment_bot_events",
    "experiment_bot_decisions",
    "experiment_bot_activities",
    "experiment_bot_replay_records",
    "experiment_bot_clips",
    "experiment_bot_clip_frames",
    "bot_semantic_outcome_stats",
    "bot_memory_pois",
    "bot_memory_danger_zones",
    "bot_memory_failed_paths",
    "bot_memory_safe_positions",
    "bot_memory_objective_clusters",
    "bot_memory_recipe_sources",
    "bot_memory_material_sources",
    "bot_memory_daily_cooldowns",
    "bot_memory_transport_usage",
    "bot_memory_decision_fingerprints",
    "bot_policy_models",
    "bot_policy_evaluations",
]

LABELS = [
    "action_success",
    "expected_reward",
    "death_risk",
    "stuck_risk",
    "quest_completion_likelihood",
]

FEATURE_SCHEMA_VERSION = "bot_policy_features_v1"


def load_json(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
            count += 1
    return count


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_parquet_if_available(path: Path, rows: list[dict[str, Any]]) -> bool:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except Exception:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)
    return True


def table_path(root: Path, table: str) -> Path:
    return root / f"{table}.jsonl"


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return ""


def flatten_json(prefix: str, value: Any, out: dict[str, float], limit: int = 80) -> None:
    if len(out) >= limit:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            flatten_json(f"{prefix}.{key}" if prefix else str(key), child, out, limit)
    elif isinstance(value, list):
        out[f"{prefix}.count"] = float(len(value))
    elif isinstance(value, bool):
        out[prefix] = 1.0 if value else 0.0
    elif isinstance(value, (int, float)) and math.isfinite(float(value)):
        out[prefix] = float(value)


def numeric_features(row: dict[str, Any]) -> dict[str, float]:
    features: dict[str, float] = {}
    for key, value in row.items():
        if key in LABELS or key in {"split", "trace", "label_observed", "is_chosen", "reward_observed", "imitate_teacher", "imitation_weight"}:
            continue
        if isinstance(value, bool):
            features[key] = 1.0 if value else 0.0
        elif isinstance(value, (int, float)) and math.isfinite(float(value)):
            features[key] = float(value)
    return features


def split_by_run_ids(rows: list[dict[str, Any]], eval_fraction: float = 0.2) -> tuple[set[int], set[int]]:
    run_ids = sorted({int(row.get("run_id") or 0) for row in rows if row.get("run_id") is not None})
    if not run_ids:
        return set(), set()
    eval_count = max(1, int(round(len(run_ids) * eval_fraction))) if len(run_ids) > 1 else 1
    eval_ids = set(run_ids[-eval_count:])
    train_ids = set(run_ids) - eval_ids
    if not train_ids:
        train_ids = set(run_ids)
    return train_ids, eval_ids


def summarize_bad_groups(rows: list[dict[str, Any]], key: str, label: str) -> list[dict[str, Any]]:
    groups: dict[Any, Counter] = defaultdict(Counter)
    for row in rows:
        groups[row.get(key)][label] += int(float(row.get(label, 0.0)) > 0.5)
        groups[row.get(key)]["count"] += 1
    ranked = []
    for value, counts in groups.items():
        count = counts["count"]
        if value is None or count == 0:
            continue
        ranked.append({"value": value, "count": count, "rate": counts[label] / count})
    return sorted(ranked, key=lambda item: (-item["rate"], -item["count"]))[:20]


def add_common_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/bot_ml"))
    return parser
