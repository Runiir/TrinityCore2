from __future__ import annotations

import json
from typing import Any


REQUIRED_FIELDS = (
    "actor_guid",
    "scope_key",
    "route_node_id",
    "route_generation",
    "board_revision",
    "observed_at_ms",
    "facts_authoritative",
    "authority_gap_mask",
    "personal_threat_present",
    "personal_threat_guid",
    "prior_episode_open",
    "new_episode_open",
    "edge",
    "parent_wave_generation",
    "parent_generation_authoritative",
    "prior_task_generation",
    "new_task_generation",
    "prior_candidate_generation",
    "new_candidate_generation",
)


def _integer(value: Any, *, positive: bool = False) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= (1 if positive else 0)
    )


def _actor_guid(bot_row: dict[str, Any]) -> int | None:
    identity = bot_row.get("identity")
    value = identity.get("bot_guid") if isinstance(identity, dict) else bot_row.get("bot_guid")
    return int(value) if _integer(value, positive=True) else None


def _record_rejections(record: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    if missing:
        return ["magmaw_personal_threat_episode_record_missing_fields"]
    positive_integer_fields = (
        "actor_guid",
        "route_generation",
        "board_revision",
        "observed_at_ms",
        "parent_wave_generation",
        "prior_task_generation",
        "new_task_generation",
        "prior_candidate_generation",
        "new_candidate_generation",
    )
    if any(not _integer(record.get(field), positive=True) for field in positive_integer_fields):
        reasons.append("magmaw_personal_threat_episode_record_integer_invalid")
    if not _integer(record.get("authority_gap_mask")):
        reasons.append("magmaw_personal_threat_episode_record_authority_mask_invalid")
    for field in (
        "facts_authoritative",
        "personal_threat_present",
        "prior_episode_open",
        "new_episode_open",
        "parent_generation_authoritative",
    ):
        if not isinstance(record.get(field), bool):
            reasons.append("magmaw_personal_threat_episode_record_boolean_invalid")
            break
    if not isinstance(record.get("scope_key"), str) or not record.get("scope_key"):
        reasons.append("magmaw_personal_threat_episode_record_scope_invalid")
    if not isinstance(record.get("route_node_id"), str) or not record.get("route_node_id"):
        reasons.append("magmaw_personal_threat_episode_record_route_node_invalid")
    if record.get("edge") not in {"falling", "rising"}:
        reasons.append("magmaw_personal_threat_episode_record_edge_invalid")
    present = record.get("personal_threat_present")
    threat_guid = record.get("personal_threat_guid")
    if not _integer(threat_guid) or (present is True) != bool(threat_guid):
        reasons.append("magmaw_personal_threat_episode_record_threat_contradiction")
    if record.get("facts_authoritative") is not True or record.get("authority_gap_mask") != 0:
        reasons.append("magmaw_personal_threat_episode_record_non_authoritative")
    return list(dict.fromkeys(reasons))


def _transition_records(
    rows: list[dict[str, Any]], target_actor: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    reasons: list[str] = []
    seen: set[str] = set()
    for row in rows:
        payload = row.get("payload") if isinstance(row, dict) else None
        if not isinstance(payload, dict) or payload.get("action") != "botauto_diagnose":
            continue
        bot_rows = payload.get("bots")
        if not isinstance(bot_rows, list):
            continue
        for bot_row in bot_rows:
            if not isinstance(bot_row, dict):
                continue
            enclosing_actor = _actor_guid(bot_row)
            diagnosis = bot_row.get("diagnosis")
            escape = diagnosis.get("magmaw_personal_parasite_escape") \
                if isinstance(diagnosis, dict) else None
            transitions = escape.get("personal_threat_episode_transitions") \
                if isinstance(escape, dict) else None
            if transitions is None:
                if enclosing_actor == target_actor:
                    reasons.append("magmaw_personal_threat_episode_records_missing")
                continue
            if not isinstance(transitions, list):
                if enclosing_actor == target_actor:
                    reasons.append("magmaw_personal_threat_episode_records_malformed")
                continue
            for record in transitions:
                record_actor = record.get("actor_guid") if isinstance(record, dict) else None
                if enclosing_actor != target_actor and record_actor != target_actor:
                    continue
                if not isinstance(record, dict):
                    reasons.append("magmaw_personal_threat_episode_record_malformed")
                    continue
                if enclosing_actor != target_actor or record_actor != target_actor:
                    reasons.append("magmaw_personal_threat_episode_cross_actor")
                    continue
                annotated = dict(record)
                annotated["capture_sequence"] = row.get("capture_sequence")
                key = json.dumps(record, sort_keys=True, separators=(",", ":"))
                if key not in seen:
                    seen.add(key)
                    records.append(annotated)
    return records, reasons


def personal_threat_episode_join_report(
    rows: list[dict[str, Any]], *, target: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate one requested actor-local falling/rising evidence join.

    The transition pair is retained in the ordinary diagnosis payload. Trace
    deltas remain useful for surrounding decisions, but ring pressure cannot
    erase this requested causal record.
    """

    if target is None:
        return {
            "requested": False,
            "records": [],
            "rejections": [],
            "gate_passed": True,
        }
    reasons: list[str] = []
    actor = target.get("actor_guid") if isinstance(target, dict) else None
    if not _integer(actor, positive=True):
        return {
            "requested": True,
            "records": [],
            "rejections": ["magmaw_personal_threat_episode_target_actor_invalid"],
            "gate_passed": False,
        }
    records, extraction_reasons = _transition_records(rows, int(actor))
    reasons.extend(extraction_reasons)
    for record in records:
        reasons.extend(_record_rejections(record))
        if "scope_key" in target and record.get("scope_key") != target.get("scope_key"):
            reasons.append("magmaw_personal_threat_episode_cross_scope")
        if any(
            field in target and record.get(field) != target.get(field)
            for field in ("route_node_id", "route_generation")
        ):
            reasons.append("magmaw_personal_threat_episode_cross_route")
        if (
            "parent_wave_generation" in target
            and record.get("parent_wave_generation") != target.get("parent_wave_generation")
        ):
            reasons.append("magmaw_personal_threat_episode_cross_parent")
        if (
            "parent_generation_authoritative" in target
            and record.get("parent_generation_authoritative")
            != target.get("parent_generation_authoritative")
        ):
            reasons.append("magmaw_personal_threat_episode_cross_parent")

    by_edge: dict[str, list[dict[str, Any]]] = {"falling": [], "rising": []}
    for record in records:
        edge = record.get("edge")
        if edge in by_edge:
            by_edge[edge].append(record)
    if len(by_edge["falling"]) != 1 or len(by_edge["rising"]) != 1:
        reasons.append("magmaw_personal_threat_episode_complete_sequence_missing")
    else:
        falling = by_edge["falling"][0]
        rising = by_edge["rising"][0]
        if not (
            falling.get("personal_threat_present") is False
            and falling.get("personal_threat_guid") == 0
            and falling.get("prior_episode_open") is True
            and falling.get("new_episode_open") is False
            and falling.get("prior_task_generation") == falling.get("new_task_generation")
            and falling.get("prior_candidate_generation")
            == falling.get("new_candidate_generation")
        ):
            reasons.append("magmaw_personal_threat_episode_falling_contradiction")
        if not (
            rising.get("personal_threat_present") is True
            and _integer(rising.get("personal_threat_guid"), positive=True)
            and rising.get("prior_episode_open") is False
            and rising.get("new_episode_open") is True
            and _integer(rising.get("prior_task_generation"), positive=True)
            and rising.get("new_task_generation")
            == rising.get("prior_task_generation") + 1
            and _integer(rising.get("prior_candidate_generation"), positive=True)
            and _integer(rising.get("new_candidate_generation"), positive=True)
            and rising.get("new_candidate_generation")
            > rising.get("prior_candidate_generation")
        ):
            reasons.append("magmaw_personal_threat_episode_rising_contradiction")
        identity_fields = (
            "actor_guid",
            "scope_key",
            "route_node_id",
            "route_generation",
            "parent_wave_generation",
            "parent_generation_authoritative",
        )
        if any(falling.get(field) != rising.get(field) for field in identity_fields):
            reasons.append("magmaw_personal_threat_episode_identity_drift")
        if (
            falling.get("new_task_generation") != rising.get("prior_task_generation")
            or falling.get("new_candidate_generation")
            != rising.get("prior_candidate_generation")
        ):
            reasons.append("magmaw_personal_threat_episode_generation_discontinuity")
        if not (
            _integer(falling.get("board_revision"), positive=True)
            and _integer(rising.get("board_revision"), positive=True)
            and rising.get("board_revision") > falling.get("board_revision")
            and _integer(falling.get("observed_at_ms"), positive=True)
            and _integer(rising.get("observed_at_ms"), positive=True)
            and rising.get("observed_at_ms") > falling.get("observed_at_ms")
        ):
            reasons.append("magmaw_personal_threat_episode_nonmonotonic")

    unique_reasons = list(dict.fromkeys(reasons))
    return {
        "requested": True,
        "target": dict(target),
        "records": records,
        "falling_count": len(by_edge["falling"]),
        "rising_count": len(by_edge["rising"]),
        "rejections": unique_reasons,
        "gate_passed": not unique_reasons,
    }
