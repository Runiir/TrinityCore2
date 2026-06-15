from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from .common import FEATURE_SCHEMA_VERSION, flatten_json, load_json, read_jsonl, split_by_run_ids, stable_hash, table_path, write_json, write_jsonl, write_parquet_if_available
except ImportError:
    from common import FEATURE_SCHEMA_VERSION, flatten_json, load_json, read_jsonl, split_by_run_ids, stable_hash, table_path, write_json, write_jsonl, write_parquet_if_available


def future_outcomes(events: list[dict[str, Any]]) -> dict[tuple[int, int], dict[str, float]]:
    by_bot: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_bot[(int(event.get("run_id") or 0), int(event.get("bot_guid") or 0))].append(event)
    labels: dict[tuple[int, int], dict[str, float]] = {}
    for key, rows in by_bot.items():
        rows.sort(key=lambda row: str(row.get("ts", "")))
        death_count = sum(1 for row in rows if row.get("event_type") == "death")
        stuck_count = sum(1 for row in rows if row.get("event_type") == "stuck_detected")
        quest_done = sum(1 for row in rows if row.get("event_type") == "quest_completed")
        labels[key] = {
            "future_deaths": float(death_count),
            "future_stucks": float(stuck_count),
            "future_quest_completions": float(quest_done),
        }
    return labels


def index_semantic_stats(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    indexed: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        entity_type = str(row.get("entity_type") or "")
        entity_key = int(row.get("entity_key") or 0)
        if entity_type and entity_key:
            indexed[(entity_type, entity_key)] = row
    return indexed


def nested_int(payload: Any, path: tuple[str, ...], default: int = 0) -> int:
    value = payload
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def add_semantic_stat_features(row: dict[str, Any], prefix: str, stats: dict[str, Any] | None) -> None:
    numeric = [
        "samples",
        "successes",
        "failures",
        "deaths",
        "avg_reward",
        "avg_power_delta",
        "danger_score",
        "progression_value",
    ]
    for key in numeric:
        row[f"stat_{prefix}_{key}"] = float((stats or {}).get(key) or 0.0)
    if stats:
        derived: dict[str, float] = {}
        flatten_json(f"stat_{prefix}_features", load_json(stats.get("features_json"), {}), derived, limit=32)
        flatten_json(f"stat_{prefix}_embedding", load_json(stats.get("embedding_json"), {}), derived, limit=32)
        row.update({key.replace(".", "_"): value for key, value in derived.items()})


def infer_mechanic_key(decision: dict[str, Any], raw: dict[str, Any], semantic: dict[str, Any]) -> int:
    explicit = nested_int(semantic, ("embedding_features", "mechanic", "entity_key")) or nested_int(raw, ("mechanic_key",))
    if explicit:
        return explicit
    situation = str(decision.get("situation_type") or semantic.get("situation_type") or "")
    if "boss" in situation:
        return 11
    if "dungeon_trash" in situation:
        return 10
    return 0


def activity_name(payload: dict[str, Any]) -> str:
    return str(payload.get("activity") or payload.get("action") or payload.get("name") or "")


def candidate_rows(candidates: Any, chosen: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(candidates, list) and candidates:
        return [candidate for candidate in candidates if isinstance(candidate, dict)]
    return [chosen]


def build_rows(decision: dict[str, Any], outcomes: dict[tuple[int, int], dict[str, float]], semantic_stats: dict[tuple[str, int], dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    raw = load_json(decision.get("raw_state_json"), {})
    semantic = load_json(decision.get("semantic_state_json"), {})
    candidates = load_json(decision.get("candidate_actions_json"), [])
    chosen = load_json(decision.get("chosen_action_json"), {})
    outcome = load_json(decision.get("outcome_json"), {})
    run_id = int(decision.get("run_id") or 0)
    bot_guid = int(decision.get("bot_guid") or 0)
    future = outcomes.get((run_id, bot_guid), {})
    features: dict[str, float] = {}
    flatten_json("raw", raw, features)
    flatten_json("semantic", semantic, features)
    flatten_json("chosen", chosen, features)
    flatten_json("outcome", outcome, features)
    chosen_activity = activity_name(chosen) or str(decision.get("current_activity") or "")
    base: dict[str, Any] = {
        "run_id": run_id,
        "decision_id": int(decision.get("id") or 0),
        "clip_id": int(decision.get("clip_id") or 0),
        "replay_id": int(decision.get("replay_key") or 0),
        "bot_guid": bot_guid,
        "brain_version": decision.get("brain_version") or "",
        "model_version": chosen.get("policy_model", {}).get("model_version", decision.get("model_version") or ""),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "runtime_feature_schema_version": decision.get("feature_schema_version") or chosen.get("policy_model", {}).get("feature_schema_version", ""),
        "runtime_model_score": float(decision.get("model_score") or chosen.get("policy_model", {}).get("model_score", 0.0) or 0.0),
        "runtime_model_rank": int(decision.get("model_rank") or chosen.get("policy_model", {}).get("model_rank", 0) or 0),
        "runtime_model_features_hash": int(decision.get("model_features_hash") or chosen.get("policy_model", {}).get("model_features_hash", 0) or 0),
        "situation_type": decision.get("situation_type") or "",
        "current_activity": decision.get("current_activity") or chosen_activity,
        "chosen_activity": chosen_activity,
        "map_id": int(decision.get("map_id") or 0),
        "zone_id": int(decision.get("zone_id") or 0),
        "area_id": int(decision.get("area_id") or nested_int(raw, ("area_id",)) or 0),
        "candidate_count": len(candidates) if isinstance(candidates, list) else 0,
        "reward_observed": float(decision.get("reward") or 0.0),
    }
    base.update({f"json_{key.replace('.', '_')}": value for key, value in features.items()})
    stats = semantic_stats or {}
    add_semantic_stat_features(base, "area", stats.get(("area", int(base["area_id"]) or nested_int(semantic, ("embedding_features", "area", "entity_key")))))
    add_semantic_stat_features(base, "mob", stats.get(("mob", nested_int(raw, ("target_entry",)) or nested_int(semantic, ("embedding_features", "mob", "entity_key")))))
    add_semantic_stat_features(base, "spell", stats.get(("spell", nested_int(raw, ("target_cast_spell_id",)) or nested_int(semantic, ("embedding_features", "spell", "entity_key")))))
    add_semantic_stat_features(base, "mechanic", stats.get(("mechanic", infer_mechanic_key(decision, raw, semantic))))

    rows: list[dict[str, Any]] = []
    candidates_list = candidate_rows(candidates, chosen)
    for index, candidate in enumerate(candidates_list):
        row = dict(base)
        candidate_activity = activity_name(candidate)
        is_chosen = candidate_activity == chosen_activity or (not candidate_activity and index == 0)
        candidate_features: dict[str, float] = {}
        flatten_json("candidate", candidate, candidate_features)
        row.update({f"json_{key.replace('.', '_')}": value for key, value in candidate_features.items()})
        row.update(
            {
                "candidate_index": index,
                "candidate_activity": candidate_activity,
                "candidate_action_hash": stable_hash(candidate),
                "is_chosen": 1 if is_chosen else 0,
                "label_observed": 1 if is_chosen else 0,
                "learned_score": float(candidate.get("learned_score", chosen.get("learned_score", 0.0)) or 0.0),
                "learned_penalty": float(candidate.get("learned_penalty", chosen.get("learned_penalty", 0.0)) or 0.0),
                "danger_score": float(candidate.get("danger_score", chosen.get("danger_score", 0.0)) or 0.0),
                "progression_value": float(candidate.get("progression_value", chosen.get("progression_value", 0.0)) or 0.0),
                "confidence": float(candidate.get("confidence", chosen.get("confidence", 0.0)) or 0.0),
                "utility_score": float(candidate.get("score", candidate.get("activity_score", chosen.get("activity_score", outcome.get("expected_value", 0.0)))) or 0.0),
                "action_success": 0.0 if is_chosen and int(decision.get("is_failure") or 0) else (1.0 if is_chosen else 0.0),
                "expected_reward": float(decision.get("reward") or 0.0) if is_chosen else 0.0,
                "death_risk": 1.0 if is_chosen and future.get("future_deaths", 0.0) > 0 else 0.0,
                "stuck_risk": 1.0 if is_chosen and future.get("future_stucks", 0.0) > 0 else 0.0,
                "quest_completion_likelihood": 1.0 if is_chosen and future.get("future_quest_completions", 0.0) > 0 else 0.0,
            }
        )
        row["features_hash"] = stable_hash({key: row[key] for key in sorted(row) if key.startswith(("json_", "stat_", "learned_", "danger_", "progression_", "confidence", "utility_", "candidate_"))})
        row["trace"] = {
            "run_id": row["run_id"],
            "decision_id": row["decision_id"],
            "clip_id": row["clip_id"],
            "replay_id": row["replay_id"],
            "bot_guid": row["bot_guid"],
            "brain_version": row["brain_version"],
            "model_version": row["model_version"],
            "feature_schema_version": row["feature_schema_version"],
            "candidate_index": row["candidate_index"],
            "candidate_activity": row["candidate_activity"],
            "is_chosen": bool(row["is_chosen"]),
        }
        rows.append(row)
    return rows


def build_row(decision: dict[str, Any], outcomes: dict[tuple[int, int], dict[str, float]], semantic_stats: dict[tuple[str, int], dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = build_rows(decision, outcomes, semantic_stats)
    return next((row for row in rows if row.get("is_chosen")), rows[0])


def main() -> int:
    parser = argparse.ArgumentParser(description="Build model-ready candidate decision rows from exported bot telemetry.")
    parser.add_argument("--input-dir", type=Path, default=Path("dataset/bot_ml/raw"))
    parser.add_argument("--output", type=Path, default=Path("dataset/bot_ml/decision_dataset.jsonl"))
    parser.add_argument("--manifest", type=Path, default=Path("dataset/bot_ml/decision_dataset_manifest.json"))
    parser.add_argument("--eval-fraction", type=float, default=0.2)
    args = parser.parse_args()
    decisions = read_jsonl(table_path(args.input_dir, "experiment_bot_decisions"))
    events = read_jsonl(table_path(args.input_dir, "experiment_bot_events"))
    semantic_stats = index_semantic_stats(read_jsonl(table_path(args.input_dir, "bot_semantic_outcome_stats")))
    outcomes = future_outcomes(events)
    rows = [row for decision in decisions for row in build_rows(decision, outcomes, semantic_stats)]
    train_ids, eval_ids = split_by_run_ids(rows, args.eval_fraction)
    for row in rows:
        row["split"] = "eval" if row["run_id"] in eval_ids else "train"
    count = write_jsonl(args.output, rows)
    parquet = args.output.with_suffix(".parquet")
    manifest = {
        "rows": count,
        "decision_rows": len(decisions),
        "candidate_rows": count,
        "observed_label_rows": sum(1 for row in rows if row.get("label_observed")),
        "jsonl": str(args.output),
        "parquet": str(parquet) if write_parquet_if_available(parquet, rows) else None,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "train_run_ids": sorted(train_ids),
        "eval_run_ids": sorted(eval_ids),
        "semantic_stats_rows": len(semantic_stats),
    }
    write_json(args.manifest, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
