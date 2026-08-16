from __future__ import annotations

import argparse
import json
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .common import DATASET_CONTRACT_VERSION, FEATURE_SCHEMA_VERSION, LABELS, flatten_json, load_json, read_jsonl, split_by_run_ids, stable_hash, table_path, write_json, write_jsonl, write_parquet_if_available
except ImportError:
    from common import DATASET_CONTRACT_VERSION, FEATURE_SCHEMA_VERSION, LABELS, flatten_json, load_json, read_jsonl, split_by_run_ids, stable_hash, table_path, write_json, write_jsonl, write_parquet_if_available


POSITIVE_EVENTS = {"quest_completed", "objective_progress", "mob_killed", "boss_killed", "loot_received", "gear_upgrade", "level_up"}
NEGATIVE_EVENTS = {
    "bad_loot",
    "death",
    "death_recovery_failed",
    "failed_path",
    "interrupt_failed",
    "loot_empty",
    "objective_failed",
    "objective_no_progress",
    "path_failed",
    "quest_abandoned",
    "raid_wipe",
    "repeated_death",
    "stuck_detected",
    "timeout",
    "unstuck",
}
DEATH_EVENTS = {"death", "repeated_death", "death_recovery_failed"}
STUCK_EVENTS = {"stuck_detected", "path_failed", "failed_path", "unstuck", "death_recovery_failed"}
QUEST_EVENTS = {"quest_completed"}
LOOP_FAILURE_LABELS = {"repeated_decision_loop", "repeated_failed_decision_loop"}
DEFAULT_LOOP_REPEAT_THRESHOLD = 3
RUN_TERMINAL_EVENT_BOT_GUID = -1
ROUTE_TERMINAL_EVENTS = {"validation_route_manifest_complete"}
ROUTE_TERMINAL_ACTIONS = {"validation_route_complete"}
CERTIFYING_RUNTIME_MODES = {"always_on_autonomy", "manual_experiment"}


def player_like_training_run_ids(runs: list[dict[str, Any]]) -> set[int]:
    """Select only ordinary, non-fixture runs for the training flywheel."""
    accepted: set[int] = set()
    for run in runs:
        run_id = int(run.get("id") or 0)
        config = load_json(run.get("config_json"), {})
        if not run_id or not isinstance(config, dict):
            continue
        if str(config.get("runtime_mode") or "") not in CERTIFYING_RUNTIME_MODES:
            continue
        if config.get("non_certifying_assistance") is not False:
            continue
        accepted.add(run_id)
    return accepted


def parse_ts(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    return 0.0


def index_semantic_stats(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    indexed: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        entity_type = str(row.get("entity_type") or "")
        entity_key = int(row.get("entity_key") or 0)
        if entity_type and entity_key:
            indexed[(entity_type, entity_key)] = row
    return indexed


def index_future_events(events: list[dict[str, Any]]) -> dict[tuple[int, int], tuple[list[float], list[dict[str, Any]]]]:
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        row = dict(event)
        row["_ts_epoch"] = parse_ts(event.get("ts"))
        run_id = int(event.get("run_id") or 0)
        grouped[(run_id, int(event.get("bot_guid") or 0))].append(row)
        if str(event.get("event_type") or "") in ROUTE_TERMINAL_EVENTS:
            grouped[(run_id, RUN_TERMINAL_EVENT_BOT_GUID)].append(row)
    indexed = {}
    for key, rows in grouped.items():
        rows.sort(key=lambda item: (item.get("_ts_epoch", 0.0), int(item.get("id") or 0)))
        indexed[key] = ([float(row.get("_ts_epoch") or 0.0) for row in rows], rows)
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
    for key in ["samples", "successes", "failures", "deaths", "avg_reward", "avg_power_delta", "danger_score", "progression_value"]:
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
    return str(payload.get("activity") or payload.get("action") or payload.get("name") or payload.get("action_category") or "")


def domain_name(decision: dict[str, Any], raw: dict[str, Any], semantic: dict[str, Any], chosen: dict[str, Any], candidate: dict[str, Any] | None = None) -> str:
    payload = candidate or {}
    return str(
        payload.get("domain")
        or chosen.get("domain")
        or decision.get("domain")
        or semantic.get("domain")
        or raw.get("domain")
        or decision.get("situation_type")
        or "unknown"
    )


def candidate_mask(candidate: dict[str, Any], chosen: dict[str, Any]) -> dict[str, Any]:
    mask = load_json(candidate.get("mask") or candidate.get("action_mask") or candidate.get("mask_json"), {})
    if not isinstance(mask, dict):
        mask = {}
    reason = str(candidate.get("mask_reason") or candidate.get("invalid_reason") or candidate.get("reject_reason") or mask.get("reason") or "")
    allowed = candidate.get("allowed", candidate.get("valid", candidate.get("available", chosen.get("allowed", chosen.get("valid", not reason)))))
    mask.setdefault("allowed", bool(allowed))
    mask.setdefault("reason", reason)
    return mask


def candidate_rows(candidates: Any, chosen: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(candidates, list) and candidates:
        return [candidate for candidate in candidates if isinstance(candidate, dict)]
    if isinstance(candidates, dict):
        rows: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates.get("activity_candidates") or []):
            if isinstance(candidate, dict):
                row = dict(candidate)
                row.setdefault("candidate_id", f"activity:{row.get('activity') or index}")
                row.setdefault("domain", "activity_selection")
                rows.append(row)
        combat_mask = candidates.get("combat_action_mask") if isinstance(candidates.get("combat_action_mask"), dict) else {}
        for index, action in enumerate(combat_mask.get("actions") or []):
            if isinstance(action, dict):
                row = dict(action)
                row.setdefault("candidate_id", f"action:{row.get('action_id') or row.get('spell_id') or index}")
                row.setdefault("domain", "combat_action")
                rows.append(row)
        if rows:
            return rows
    return [chosen]


def candidate_key(payload: dict[str, Any]) -> str:
    structured = payload.get("structured_action") if isinstance(payload.get("structured_action"), dict) else {}
    action_id = structured.get("action_id") or payload.get("action_id")
    if action_id:
        return f"action:{action_id}"
    return str(payload.get("candidate_id") or payload.get("id") or "")


def chosen_candidate_index(candidates: list[dict[str, Any]], chosen: dict[str, Any], chosen_activity: str) -> int:
    chosen_key = candidate_key(chosen)
    if chosen_key:
        for index, candidate in enumerate(candidates):
            if candidate_key(candidate) == chosen_key:
                return index
    for index, candidate in enumerate(candidates):
        if activity_name(candidate) == chosen_activity or (not activity_name(candidate) and not chosen_activity and index == 0):
            return index
    return 0 if candidates else -1


def index_decision_fingerprints(rows: list[dict[str, Any]]) -> dict[tuple[int, int], dict[str, Any]]:
    indexed: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        bot_guid = int(row.get("bot_guid") or 0)
        fingerprint_hash = int(row.get("fingerprint_hash") or row.get("decision_fingerprint_hash") or 0)
        if bot_guid and fingerprint_hash:
            indexed[(bot_guid, fingerprint_hash)] = row
    return indexed


def window_events(indexed: dict[tuple[int, int], tuple[list[float], list[dict[str, Any]]]], run_id: int, bot_guid: int, ts: float, window_sec: int) -> list[dict[str, Any]]:
    stamps, rows = indexed.get((run_id, bot_guid), ([], []))
    start = bisect_right(stamps, ts)
    end = bisect_right(stamps, ts + window_sec)
    return rows[start:end]


def filter_rows_by_map(rows: list[dict[str, Any]], map_ids: set[int]) -> list[dict[str, Any]]:
    if not map_ids:
        return rows
    return [row for row in rows if int(row.get("map_id") or 0) in map_ids]


def event_reward(event: dict[str, Any]) -> float:
    event_type = str(event.get("event_type") or "")
    value = float(event.get("value_float") or 0.0)
    reward = 0.0
    if event_type == "quest_completed":
        reward += 8.0
    elif event_type == "objective_progress":
        reward += 3.0
    elif event_type in {"mob_killed", "boss_killed"}:
        reward += 1.5
    elif event_type == "loot_received":
        reward += 0.5
    elif event_type == "gear_upgrade":
        reward += 2.0 + max(0.0, value)
    elif event_type == "level_up":
        reward += 6.0
    if value > 0:
        reward += min(5.0, value * 0.25)
    if event_type == "death":
        reward -= 8.0
    elif event_type == "repeated_death":
        reward -= 12.0
    elif event_type in STUCK_EVENTS:
        reward -= 4.0
    elif event_type in {"timeout", "objective_failed", "quest_abandoned", "interrupt_failed"}:
        reward -= 5.0
    if event_type in {"path_failed", "failed_path"}:
        reward -= 2.0
    if value < 0:
        reward += value
    return reward


def event_polarity(event: dict[str, Any]) -> tuple[bool, bool]:
    event_type = str(event.get("event_type") or "")
    value = float(event.get("value_float") or 0.0)
    result = str(event.get("result") or "").lower()
    negative = event_type in NEGATIVE_EVENTS or value < 0 or result in {"failed", "timeout", "bad_loot"}
    positive = not negative and (event_type in POSITIVE_EVENTS or value > 0)
    return positive, negative


def label_decision(decision: dict[str, Any], indexed_events: dict[tuple[int, int], tuple[list[float], list[dict[str, Any]]]], windows: dict[str, int]) -> dict[str, Any]:
    run_id = int(decision.get("run_id") or 0)
    bot_guid = int(decision.get("bot_guid") or 0)
    ts = parse_ts(decision.get("ts"))
    outcome_events = window_events(indexed_events, run_id, bot_guid, ts, windows["outcome"])
    reward_events = window_events(indexed_events, run_id, bot_guid, ts, windows["reward"])
    death_events = window_events(indexed_events, run_id, bot_guid, ts, windows["death"])
    stuck_events = window_events(indexed_events, run_id, bot_guid, ts, windows["stuck"])
    quest_events = window_events(indexed_events, run_id, bot_guid, ts, windows["quest"])
    used_events = {int(event.get("id") or 0) for event in (outcome_events + reward_events + death_events + stuck_events + quest_events) if event.get("id") is not None}

    first_positive: dict[str, Any] | None = None
    first_negative: dict[str, Any] | None = None
    for event in outcome_events:
        positive, negative = event_polarity(event)
        if positive and first_positive is None:
            first_positive = event
        if negative and first_negative is None:
            first_negative = event
        if first_positive is not None and first_negative is not None:
            break

    chosen = load_json(decision.get("chosen_action_json"), {})
    chosen_action = str(chosen.get("action") or activity_name(chosen))
    situation = str(decision.get("situation_type") or "")
    route_terminal_decision = chosen_action in ROUTE_TERMINAL_ACTIONS or situation.startswith("validation_route") or situation == "dungeon_boss"
    terminal_decision_evidence = False
    if not first_positive and not first_negative and route_terminal_decision:
        route_terminal_events = window_events(indexed_events, run_id, RUN_TERMINAL_EVENT_BOT_GUID, ts, windows["outcome"])
        if route_terminal_events:
            first_positive = route_terminal_events[0]
            used_events.update(int(event.get("id") or 0) for event in route_terminal_events if event.get("id") is not None)
        elif chosen_action in ROUTE_TERMINAL_ACTIONS:
            terminal_decision_evidence = True

    if first_positive and (not first_negative or float(first_positive["_ts_epoch"]) <= float(first_negative["_ts_epoch"])):
        action_success = 1.0
        reason = f"positive_progress:{first_positive.get('event_type')}"
        time_to_outcome = float(first_positive["_ts_epoch"]) - ts
    elif terminal_decision_evidence:
        action_success = 1.0
        reason = f"positive_progress:{chosen_action}"
        time_to_outcome = 0.0
    elif first_negative:
        action_success = 0.0
        reason = f"negative_outcome:{first_negative.get('event_type')}"
        time_to_outcome = float(first_negative["_ts_epoch"]) - ts
    else:
        action_success = 0.0
        reason = "no_future_outcome"
        time_to_outcome = None

    if first_positive and (not first_negative or float(first_positive["_ts_epoch"]) <= float(first_negative["_ts_epoch"])):
        risk_events = [event for event in death_events + stuck_events if float(event.get("_ts_epoch") or 0.0) <= float(first_positive["_ts_epoch"])]
    else:
        risk_events = death_events + stuck_events
    expected_reward = sum(event_reward(event) for event in reward_events)
    return {
        "action_success": action_success,
        "expected_reward": expected_reward,
        "death_risk": 1.0 if any(str(event.get("event_type") or "") in DEATH_EVENTS for event in risk_events) else 0.0,
        "stuck_risk": 1.0 if any(str(event.get("event_type") or "") in STUCK_EVENTS for event in risk_events) else 0.0,
        "quest_completion_likelihood": 1.0 if any(str(event.get("event_type") or "") in QUEST_EVENTS for event in quest_events) else 0.0,
        "event_ids_used_for_label": sorted(used_events),
        "label_window_json": json.dumps(windows, sort_keys=True),
        "label_reason": reason,
        "time_to_outcome_sec": time_to_outcome,
        "no_future_events": not used_events and not terminal_decision_evidence,
        "ambiguous_label": bool(first_positive and first_negative and float(first_positive["_ts_epoch"]) == float(first_negative["_ts_epoch"])),
    }


def default_labels(decision: dict[str, Any], labels: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(labels or {})
    reward = float(decision.get("reward") or decision.get("reward_observed") or 0.0)
    has_decision_outcome = bool(reward) or bool(int(decision.get("is_failure") or 0))
    defaults = {
        "action_success": 1.0 if reward > 0.0 and not int(decision.get("is_failure") or 0) else 0.0,
        "expected_reward": reward,
        "death_risk": 0.0,
        "stuck_risk": 0.0,
        "quest_completion_likelihood": 0.0,
        "event_ids_used_for_label": [],
        "label_window_json": "{}",
        "label_reason": "provided_labels" if labels else "decision_reward_fallback",
        "time_to_outcome_sec": None,
        "no_future_events": not has_decision_outcome,
        "ambiguous_label": False,
    }
    for key, value in defaults.items():
        merged.setdefault(key, value)
    for label in LABELS:
        merged.setdefault(label, defaults.get(label, 0.0))
    return merged


def teacher_filter_labels(labels: dict[str, Any], is_chosen: bool) -> dict[str, Any]:
    if not is_chosen:
        return {
            "imitate_teacher": 0,
            "imitation_weight": 0.0,
            "teacher_action_quality": "candidate_unobserved",
            "failure_label": "",
        }
    death_risk = float(labels.get("death_risk") or 0.0) > 0.0
    stuck_risk = float(labels.get("stuck_risk") or 0.0) > 0.0
    action_success = float(labels.get("action_success") or 0.0) > 0.5
    no_future_events = bool(labels.get("no_future_events"))
    ambiguous = bool(labels.get("ambiguous_label"))
    label_reason = str(labels.get("label_reason") or "")
    if label_reason in LOOP_FAILURE_LABELS:
        quality = "looping_teacher_action"
        failure_label = label_reason
    elif death_risk:
        quality = "unsafe_teacher_action"
        failure_label = "death_outcome"
    elif stuck_risk:
        quality = "unsafe_teacher_action"
        failure_label = "stuck_or_path_failure"
    elif ambiguous:
        quality = "ambiguous_teacher_action"
        failure_label = "ambiguous_outcome"
    elif no_future_events:
        quality = "unverified_teacher_action"
        failure_label = "no_future_outcome"
    elif not action_success:
        quality = "failed_teacher_action"
        failure_label = label_reason or "negative_outcome"
    else:
        quality = "verified_teacher_action"
        failure_label = ""
    imitate = quality == "verified_teacher_action"
    return {
        "imitate_teacher": 1 if imitate else 0,
        "imitation_weight": 1.0 if imitate else 0.0,
        "teacher_action_quality": quality,
        "failure_label": failure_label,
    }


def build_row(decision: dict[str, Any], labels: dict[str, Any] | None = None, semantic_stats: dict[tuple[str, int], dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = build_rows(decision, labels, semantic_stats)
    return rows[0] if rows else {}


def build_rows(
    decision: dict[str, Any],
    labels: dict[str, Any] | None = None,
    semantic_stats: dict[tuple[str, int], dict[str, Any]] | None = None,
    decision_fingerprints: dict[tuple[int, int], dict[str, Any]] | None = None,
    loop_repeat_threshold: int = DEFAULT_LOOP_REPEAT_THRESHOLD,
) -> list[dict[str, Any]]:
    labels = default_labels(decision, labels)
    raw = load_json(decision.get("raw_state_json"), {})
    semantic = load_json(decision.get("semantic_state_json"), {})
    candidates = load_json(decision.get("candidate_actions_json"), [])
    chosen = load_json(decision.get("chosen_action_json"), {})
    outcome = load_json(decision.get("outcome_json"), {})
    fingerprint_hash = int(
        decision.get("decision_fingerprint_hash")
        or decision.get("fingerprint_hash")
        or nested_int(raw, ("decision_fingerprint_hash",))
        or nested_int(raw, ("decision", "fingerprint_hash"))
        or nested_int(semantic, ("decision_fingerprint_hash",))
        or nested_int(semantic, ("decision", "fingerprint_hash"))
        or 0
    )
    fingerprint = (decision_fingerprints or {}).get((int(decision.get("bot_guid") or 0), fingerprint_hash), {})
    fingerprint_repeat_count = int(decision.get("decision_fingerprint_repeat_count") or fingerprint.get("repeat_count") or 0)
    fingerprint_failure_count = int(decision.get("decision_fingerprint_failure_count") or fingerprint.get("failure_count") or 0)
    if fingerprint_hash and (fingerprint_repeat_count >= loop_repeat_threshold or fingerprint_failure_count > 0):
        labels["action_success"] = 0.0
        labels["expected_reward"] = min(float(labels.get("expected_reward") or 0.0), -4.0 if fingerprint_failure_count else -2.0)
        labels["stuck_risk"] = max(float(labels.get("stuck_risk") or 0.0), 1.0 if fingerprint_failure_count else 0.0)
        labels["label_reason"] = "repeated_failed_decision_loop" if fingerprint_failure_count else "repeated_decision_loop"
        labels["no_future_events"] = False
    features: dict[str, float] = {}
    flatten_json("raw", raw, features)
    flatten_json("semantic", semantic, features)
    flatten_json("chosen", chosen, features)
    flatten_json("outcome", outcome, features)
    chosen_activity = activity_name(chosen) or str(decision.get("current_activity") or "")
    normalized_candidates = candidate_rows(candidates, chosen)
    chosen_index = chosen_candidate_index(normalized_candidates, chosen, chosen_activity)
    base: dict[str, Any] = {
        "run_id": int(decision.get("run_id") or 0),
        "decision_id": int(decision.get("id") or 0),
        "event_ids_used_for_label": labels["event_ids_used_for_label"],
        "clip_id": int(decision.get("clip_id") or 0),
        "replay_id": int(decision.get("replay_key") or 0),
        "bot_guid": int(decision.get("bot_guid") or 0),
        "brain_version": decision.get("brain_version") or "",
        "model_version": chosen.get("policy_model", {}).get("model_version", decision.get("model_version") or ""),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "dataset_contract_version": DATASET_CONTRACT_VERSION,
        "label_window_json": labels["label_window_json"],
        "label_reason": labels["label_reason"],
        "time_to_outcome_sec": labels["time_to_outcome_sec"],
        "no_future_events": 1 if labels["no_future_events"] else 0,
        "ambiguous_label": 1 if labels["ambiguous_label"] else 0,
        "runtime_feature_schema_version": decision.get("feature_schema_version") or chosen.get("policy_model", {}).get("feature_schema_version", ""),
        "runtime_model_score": float(decision.get("model_score") or chosen.get("policy_model", {}).get("model_score", 0.0) or 0.0),
        "runtime_model_rank": int(decision.get("model_rank") or chosen.get("policy_model", {}).get("model_rank", 0) or 0),
        "runtime_model_features_hash": int(decision.get("model_features_hash") or chosen.get("policy_model", {}).get("model_features_hash", 0) or 0),
        "situation_type": decision.get("situation_type") or "",
        "current_activity": decision.get("current_activity") or chosen_activity,
        "chosen_activity": chosen_activity,
        "decision_domain": domain_name(decision, raw, semantic, chosen),
        "map_id": int(decision.get("map_id") or 0),
        "zone_id": int(decision.get("zone_id") or 0),
        "area_id": int(decision.get("area_id") or nested_int(raw, ("area_id",)) or 0),
        "candidate_count": len(normalized_candidates),
        "reward_observed": float(decision.get("reward") or 0.0),
        "decision_fingerprint_hash": fingerprint_hash,
        "decision_fingerprint_repeat_count": fingerprint_repeat_count,
        "decision_fingerprint_failure_count": fingerprint_failure_count,
    }
    base.update({f"json_{key.replace('.', '_')}": value for key, value in features.items()})
    stats = semantic_stats or {}
    add_semantic_stat_features(base, "area", stats.get(("area", int(base["area_id"]) or nested_int(semantic, ("embedding_features", "area", "entity_key")))))
    add_semantic_stat_features(base, "mob", stats.get(("mob", nested_int(raw, ("target_entry",)) or nested_int(semantic, ("embedding_features", "mob", "entity_key")))))
    add_semantic_stat_features(base, "spell", stats.get(("spell", nested_int(raw, ("target_cast_spell_id",)) or nested_int(semantic, ("embedding_features", "spell", "entity_key")))))
    add_semantic_stat_features(base, "mechanic", stats.get(("mechanic", infer_mechanic_key(decision, raw, semantic))))

    rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(normalized_candidates):
        row = dict(base)
        candidate_activity = activity_name(candidate)
        is_chosen = index == chosen_index
        candidate_features: dict[str, float] = {}
        flatten_json("candidate", candidate, candidate_features)
        row.update({f"json_{key.replace('.', '_')}": value for key, value in candidate_features.items()})
        row.update(
            {
                "candidate_index": index,
                "candidate_id": str(candidate.get("candidate_id") or candidate.get("id") or ""),
                "candidate_domain": domain_name(decision, raw, semantic, chosen, candidate),
                "candidate_activity": candidate_activity,
                "candidate_action_hash": stable_hash(candidate),
                "candidate_mask": candidate_mask(candidate, chosen),
                "candidate_allowed": 1 if candidate_mask(candidate, chosen).get("allowed") else 0,
                "candidate_mask_reason": str(candidate_mask(candidate, chosen).get("reason") or ""),
                "is_chosen": 1 if is_chosen else 0,
                "label_observed": 1 if is_chosen else 0,
                "learned_score": float(candidate.get("learned_score", chosen.get("learned_score", 0.0)) or 0.0),
                "learned_penalty": float(candidate.get("learned_penalty", chosen.get("learned_penalty", 0.0)) or 0.0),
                "danger_score": float(candidate.get("danger_score", chosen.get("danger_score", 0.0)) or 0.0),
                "progression_value": float(candidate.get("progression_value", chosen.get("progression_value", 0.0)) or 0.0),
                "confidence": float(candidate.get("confidence", chosen.get("confidence", 0.0)) or 0.0),
                "utility_score": float(candidate.get("score", candidate.get("activity_score", chosen.get("activity_score", outcome.get("expected_value", 0.0)))) or 0.0),
            }
        )
        row.update(teacher_filter_labels(labels, is_chosen))
        for label in LABELS:
            row[label] = float(labels[label]) if is_chosen else 0.0
        row["features_hash"] = stable_hash({key: row[key] for key in sorted(row) if key.startswith(("json_", "stat_", "learned_", "danger_", "progression_", "confidence", "utility_", "candidate_"))})
        row["trace"] = {key: row.get(key) for key in ["run_id", "decision_id", "event_ids_used_for_label", "clip_id", "replay_id", "bot_guid", "brain_version", "model_version", "feature_schema_version", "dataset_contract_version", "candidate_index", "candidate_id", "candidate_activity", "candidate_domain", "is_chosen", "failure_label"]}
        rows.append(row)
    return rows


def label_diagnostics(rows: list[dict[str, Any]], decisions: list[dict[str, Any]], train_ids: set[int], eval_ids: set[int]) -> dict[str, Any]:
    observed = [row for row in rows if row.get("label_observed")]
    imitable = [row for row in observed if int(row.get("imitate_teacher") or 0)]
    filtered = [row for row in observed if not int(row.get("imitate_teacher") or 0)]
    positives = {label: sum(float(row.get(label, 0.0)) > 0.5 for row in observed) for label in LABELS if label != "expected_reward"}
    time_values = [float(row["time_to_outcome_sec"]) for row in observed if row.get("time_to_outcome_sec") is not None]
    run_counts = Counter(int(row.get("run_id") or 0) for row in observed)
    return {
        "dataset_contract_version": DATASET_CONTRACT_VERSION,
        "label_rates": {
            label: {
                "positive_rate": positives.get(label, 0) / max(1, len(observed)),
                "negative_rate": 1.0 - positives.get(label, 0) / max(1, len(observed)),
            }
            for label in LABELS
            if label != "expected_reward"
        },
        "expected_reward_mean": sum(float(row.get("expected_reward", 0.0)) for row in observed) / max(1, len(observed)),
        "rows_with_no_future_events": sum(1 for row in observed if row.get("no_future_events")),
        "average_time_to_outcome": sum(time_values) / max(1, len(time_values)),
        "ambiguous_labels": sum(1 for row in observed if row.get("ambiguous_label")),
        "imitable_teacher_rows": len(imitable),
        "filtered_teacher_rows": len(filtered),
        "teacher_action_quality": dict(Counter(str(row.get("teacher_action_quality") or "") for row in observed)),
        "failure_labels": dict(Counter(str(row.get("failure_label") or "") for row in filtered if row.get("failure_label"))),
        "loop_filtered_teacher_rows": sum(1 for row in filtered if str(row.get("failure_label") or "") in LOOP_FAILURE_LABELS),
        "run_level_split_info": {
            "train_run_ids": sorted(train_ids),
            "eval_run_ids": sorted(eval_ids),
            "observed_rows_by_run": dict(run_counts),
        },
        "leakage_checks": {
            "run_split_overlap": sorted(set(train_ids) & set(eval_ids)),
            "eval_decisions": sum(1 for row in observed if row.get("run_id") in eval_ids),
            "train_decisions": sum(1 for row in observed if row.get("run_id") in train_ids),
            "candidate_rows_have_observed_labels_only_for_chosen": all((row.get("label_observed") == row.get("is_chosen")) for row in rows),
        },
        "decision_rows": len(decisions),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build model-ready candidate decision rows from exported bot telemetry.")
    parser.add_argument("--input-dir", type=Path, default=Path("dataset/bot_ml/raw"))
    parser.add_argument("--output", type=Path, default=Path("dataset/bot_ml/decision_dataset.jsonl"))
    parser.add_argument("--manifest", type=Path, default=Path("dataset/bot_ml/decision_dataset_manifest.json"))
    parser.add_argument("--eval-fraction", type=float, default=0.2)
    parser.add_argument("--outcome-window-sec", type=int, default=180)
    parser.add_argument("--death-window-sec", type=int, default=180)
    parser.add_argument("--stuck-window-sec", type=int, default=180)
    parser.add_argument("--quest-window-sec", type=int, default=600)
    parser.add_argument("--reward-window-sec", type=int, default=300)
    parser.add_argument("--loop-repeat-threshold", type=int, default=DEFAULT_LOOP_REPEAT_THRESHOLD)
    parser.add_argument("--include-map-id", type=int, action="append", default=[])
    args = parser.parse_args()
    windows = {"outcome": args.outcome_window_sec, "death": args.death_window_sec, "stuck": args.stuck_window_sec, "quest": args.quest_window_sec, "reward": args.reward_window_sec}
    include_map_ids = set(args.include_map_id)
    all_runs = read_jsonl(table_path(args.input_dir, "experiment_bot_runs"))
    eligible_run_ids = player_like_training_run_ids(all_runs)
    all_decisions = read_jsonl(table_path(args.input_dir, "experiment_bot_decisions"))
    all_events = read_jsonl(table_path(args.input_dir, "experiment_bot_events"))
    decisions = filter_rows_by_map(
        [row for row in all_decisions if int(row.get("run_id") or 0) in eligible_run_ids],
        include_map_ids,
    )
    events = filter_rows_by_map(
        [row for row in all_events if int(row.get("run_id") or 0) in eligible_run_ids],
        include_map_ids,
    )
    semantic_stats = index_semantic_stats(read_jsonl(table_path(args.input_dir, "bot_semantic_outcome_stats")))
    decision_fingerprints = index_decision_fingerprints(read_jsonl(table_path(args.input_dir, "bot_memory_decision_fingerprints")))
    indexed_events = index_future_events(events)
    rows = [
        row
        for decision in decisions
        for row in build_rows(decision, label_decision(decision, indexed_events, windows), semantic_stats, decision_fingerprints, args.loop_repeat_threshold)
    ]
    train_ids, eval_ids = split_by_run_ids(rows, args.eval_fraction)
    for row in rows:
        row["split"] = "eval" if row["run_id"] in eval_ids else "train"
    count = write_jsonl(args.output, rows)
    parquet = args.output.with_suffix(".parquet")
    diagnostics = label_diagnostics(rows, decisions, train_ids, eval_ids)
    manifest = {
        "rows": count,
        "decision_rows": len(decisions),
        "source_decision_rows": len(all_decisions),
        "source_event_rows": len(all_events),
        "source_filter": {
            "include_map_ids": sorted(include_map_ids),
            "evidence_class": "player_like_non_fixture",
            "eligible_run_ids": sorted(eligible_run_ids),
            "excluded_non_certifying_run_count": len(all_runs) - len(eligible_run_ids),
        },
        "candidate_rows": count,
        "observed_label_rows": sum(1 for row in rows if row.get("label_observed")),
        "jsonl": str(args.output),
        "parquet": str(parquet) if write_parquet_if_available(parquet, rows) else None,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "dataset_contract_version": DATASET_CONTRACT_VERSION,
        "label_window_sec": windows,
        "loop_repeat_threshold": args.loop_repeat_threshold,
        "train_run_ids": sorted(train_ids),
        "eval_run_ids": sorted(eval_ids),
        "semantic_stats_rows": len(semantic_stats),
        "decision_fingerprint_rows": len(decision_fingerprints),
        "label_diagnostics": diagnostics,
    }
    write_json(args.manifest, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
