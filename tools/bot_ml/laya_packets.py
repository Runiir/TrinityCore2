"""Compact per-actor packets for the local Laya typed-decision backend.

The normal Qwen shadow packet is intentionally verbose because it is also used
for the older local experiment.  Laya has a smaller prompt budget, so this
module projects the same deterministic actor evidence into one bounded packet.
The projection is diagnostic only: absent source fields stay absent and no
action authority is added by this adapter.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


MODEL = "convaiinnovations/laya-typed-decisions"

# Keep the option text short enough for the Laya head budget.  Insertion order
# is part of the request contract and is intentionally stable.
ACTOR_OPTIONS = {
    "no_material_action": "No material gap.",
    "movement_recovery": "Movement/range/uptime.",
    "uptime_cadence": "Eligible idle/cadence.",
    "rotation_profile": "Profile/resource.",
    "target_lease": "Target ownership/churn.",
    "shared_arbitration": "Native failure.",
    "encounter_assignment": "Required duty incomplete.",
    "collect_more_canaries": "Mixed/unmatched evidence.",
}
ROLE_OPTIONS = {
    "native_action_review": "Observed actor native failure.",
    "insufficient_role_evidence": "Role evidence is insufficient.",
    "collect_more_canaries": "Collect actor-scoped role rows.",
}

_IDENTITY_FIELDS = ("bot_guid", "bot_name", "role", "class_spec", "class_name")
_OBSERVED_FIELDS = (
    "encounter_dps",
    "encounter_dps_basis",
    "wcl_observed_dps",
    "encounter_dps_gap_vs_wcl",
            "active_seconds",
    "damage_uptime",
    "idle_fraction",
    "moving_fraction",
    "distance_avg",
)
_NATIVE_FIELDS = (
    "native_outcome_count",
    "native_actionable_failure_count",
    "native_actionable_failure_ratio",
    "native_outcome_counts",
    "candidate_scan_count",
    "candidate_gate_counts",
)
_DUTY_FIELDS = (
    "assignment_damage_event_count",
    "assignment_landed_damage",
    "mechanic_duty_scope",
)
_COUNTERFACTUAL_FIELDS = (
    "damage_cadence_capture",
    "damage_gap_max_seconds",
    "damage_gap_count_ge_3_seconds",
    "counterfactual_status",
)
_PET_FIELDS = (
    "damage",
    "pet_damage",
    "pet_damage_share",
    "raw_event_pet_damage",
    "raw_event_pet_damage_share",
    "pet_active_seconds",
    "pet_uptime",
)


def _present(source: Any, fields: Iterable[str]) -> dict[str, Any]:
    """Copy only source-present fields, retaining explicit null/zero values."""
    if not isinstance(source, Mapping):
        return {}
    return {field: source[field] for field in fields if field in source}


def _guid(value: Any) -> int | str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value else None
    if isinstance(value, str) and value.strip():
        try:
            parsed = int(value)
        except ValueError:
            return value
        return parsed if parsed else None
    return None


def _same_guid(value: Any, guid: int | str | None) -> bool:
    if guid is None:
        return False
    left = _guid(value)
    if left is None:
        return False
    return str(left) == str(guid)


def _row_for_guid(rows: Any, guid: int | str | None) -> dict[str, Any] | None:
    if isinstance(rows, Mapping):
        direct = rows.get(str(guid))
        if isinstance(direct, Mapping):
            return dict(direct)
        direct = rows.get(guid)
        if isinstance(direct, Mapping):
            return dict(direct)
        iterable = rows.values()
    elif isinstance(rows, list):
        iterable = rows
    else:
        return None
    for row in iterable:
        if not isinstance(row, Mapping):
            continue
        if _same_guid(row.get("bot_guid", row.get("actor_guid")), guid):
            return dict(row)
    return None


def _identity_for_guid(boss: Mapping[str, Any], guid: int | str | None) -> dict[str, Any]:
    identity = _row_for_guid(boss.get("actor_identity"), guid)
    return _present(identity, _IDENTITY_FIELDS) if identity else {}


def _identity_rows(value: Any) -> list[dict[str, Any]]:
    """Return roster identity rows in producer order without inventing rows."""
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    if isinstance(value, Mapping):
        rows: list[dict[str, Any]] = []
        for key, value_row in value.items():
            if not isinstance(value_row, Mapping):
                continue
            row = dict(value_row)
            if "bot_guid" not in row and "actor_guid" not in row:
                row["bot_guid"] = key
            rows.append(row)
        return rows
    return []


def _metrics_actor(boss: Mapping[str, Any], state: Mapping[str, Any], guid: int | str | None) -> dict[str, Any] | None:
    """Find the full actor ledger when the report retained one.

    Current canonical reports usually expose only actor_loss_signals.  Older
    reports and focused fixtures may retain the full combat actor row, which is
    where owner/pet attribution lives.
    """
    candidates: list[Any] = []
    for container in (
        boss.get("combat_metrics"),
        state.get("combat_metrics"),
        boss.get("actor_metrics"),
    ):
        if isinstance(container, Mapping):
            candidates.append(container.get("actors"))
    for rows in candidates:
        row = _row_for_guid(rows, guid)
        if row is not None:
            return row
    return None


def _timeline_for_guid(boss: Mapping[str, Any], guid: int | str | None) -> dict[str, Any] | None:
    timeline = boss.get("timeline_comparison")
    if not isinstance(timeline, Mapping):
        return None
    return _row_for_guid(timeline.get("actors"), guid)


def _bounded_rows(value: Any, fields: Iterable[str], limit: int) -> Any:
    """Keep a deterministic small sample while stating its scope.

    These rows are supporting evidence, not an aggregate denominator.  The
    count/omitted fields make the bounded projection explicit to the model.
    """
    if not isinstance(value, list):
        return value
    rows = [dict(row) if isinstance(row, Mapping) else row for row in value]
    shown = [_present(row, fields) if isinstance(row, Mapping) else row for row in rows[:limit]]
    result: dict[str, Any] = {"observed_count": len(rows), "shown": shown}
    if len(rows) > limit:
        result["omitted_count"] = len(rows) - limit
    return result


def _compact_native(actor: Mapping[str, Any]) -> dict[str, Any]:
    result = _present(actor, _NATIVE_FIELDS)
    if isinstance(result.get("native_outcome_counts"), Mapping):
        # Outcome kinds are normally few. Preserve all of them when small; a
        # bounded count is explicit when a legacy report has many kinds.
        counts = result["native_outcome_counts"]
        failure_kinds = {
            key: counts[key]
            for key in (
                "cast_failed",
                "no_action",
                "out_of_range",
                "no_line_of_sight",
                "action_rejected",
            )
            if key in counts
        }
        result["native_outcome_counts"] = failure_kinds
        if len(counts) > len(failure_kinds):
            result["native_outcome_kinds"] = len(counts)
    gates = result.get("candidate_gate_counts")
    if isinstance(gates, Mapping) and len(gates) > 2:
        items = sorted(gates.items(), key=lambda item: (-int(item[1]), str(item[0])))
        result["candidate_gate_counts"] = dict(items[:2])
        result["candidate_gate_kinds"] = len(gates)
    return result


def _compact_gap(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return _present(
        value,
        ("gap_sec", "from_t", "to_t", "from_ability", "to_ability", "evidence_precision"),
    ) or None


def _compact_overlap(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _present(
        value,
        (
            "status",
            "evidence_precision",
        ),
    )
    gaps = value.get("gaps_considered")
    if isinstance(gaps, list):
        if gaps and isinstance(gaps[0], Mapping):
            result["first_gap"] = _present(
                gaps[0],
                (
                    "actionable_failure_count",
                    "movement_or_range_rejection_count",
                ),
            )
    return result or None


def _compact_timeline(timeline: Mapping[str, Any] | None, actor: Mapping[str, Any]) -> dict[str, Any]:
    source = timeline if isinstance(timeline, Mapping) else {}
    # actor_loss_signals.timeline_signal is the normalized per-actor join. A
    # raw timeline row remains a useful fallback for legacy reports/fixtures.
    result = _present(
        source,
        (
            "comparison_status",
            "bot_event_input_status",
            "wcl_common_window_dps",
            "dps_comparison_status",
        ),
    )
    if "comparison_status" not in result and "comparison_status" in actor:
        result["comparison_status"] = actor["comparison_status"]

    largest = source.get("largest_direct_gap")
    if largest is None:
        gaps = source.get("bot_largest_direct_gaps")
        if isinstance(gaps, list) and gaps:
            largest = gaps[0]
    compact_largest = _compact_gap(largest)
    if compact_largest is not None:
        for key in ("from_t", "to_t", "from_ability", "to_ability", "evidence_precision"):
            compact_largest.pop(key, None)
        result["largest_direct_gap"] = compact_largest

    overlap = source.get("gap_overlap_evidence")
    compact_overlap = _compact_overlap(overlap)
    if compact_overlap is not None:
        result["gap_overlap_evidence"] = compact_overlap

    # Raw timeline rows carry nested cadence objects instead of the normalized
    # signal names. Pull only their event counts/gaps when available.
    for nested, prefix in (
        ("wcl_completed_cast_cadence", "wcl"),
        ("bot_landed_damage_cadence", "bot"),
        ("bot_direct_or_unknown_cadence", "bot_direct"),
    ):
        cadence = source.get(nested)
        if not isinstance(cadence, Mapping):
            continue
        for source_key, target_key in (
            ("event_count", f"{prefix}_event_count"),
            ("max_gap_sec", f"{prefix}_max_gap_sec"),
        ):
            if source_key in cadence and target_key not in result:
                result[target_key] = cadence[source_key]
    if not result:
        result["comparison_status"] = "missing_actor_timeline"
    return result


def _compact_outcome(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _present(
        value,
        (
            "status",
            "certification_status",
            "native_clear",
            "clear",
            "outcome",
            "completion_reason",
            "failure_reason",
            "terminal_reason",
            "available",
        ),
    )
    return result or None


def _role_native_rows(
    source: Any,
    guid: int | str | None,
    fields: Iterable[str],
    source_name: str,
) -> dict[str, Any]:
    """Project only rows explicitly attributed to one non-DPS actor."""
    if not isinstance(source, list):
        return {"status": "unavailable", "reason": f"{source_name}_source_missing"}
    rows = [
        row for row in source
        if isinstance(row, Mapping)
        and _same_guid(row.get("bot_guid", row.get("actor_guid")), guid)
    ]
    if not rows:
        return {"status": "unavailable", "reason": "no_actor_scoped_rows"}
    compact = _bounded_rows(rows, fields, 3)
    return {"status": "observed", "rows": compact}


def _first_list(source: Mapping[str, Any], names: Iterable[str]) -> list[Any] | None:
    empty: list[Any] | None = None
    for name in names:
        value = source.get(name)
        if isinstance(value, list):
            if value:
                return value
            if empty is None:
                empty = value
    return empty


def _role_actor_state(
    state: Mapping[str, Any],
    boss: Mapping[str, Any],
    identity: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Build a role packet without borrowing DPS or party-level totals."""
    guid = _guid(identity.get("bot_guid", identity.get("actor_guid")))
    role = str(identity.get("role") or "unknown")
    actor_identity = _present(identity, _IDENTITY_FIELDS)
    action_rows = _first_list(
        boss,
        ("action_outcomes", "native_action_outcomes", "action_outcome_rows"),
    )
    candidate_rows = _first_list(
        boss,
        ("candidate_rejections", "native_candidate_rejections", "candidate_rejection_rows"),
    )
    native = {
        "action_outcomes": _role_native_rows(
            action_rows,
            guid,
            ("action_name", "outcome", "reason_code", "count"),
            "action_outcomes",
        ),
        "candidate_rejections": _role_native_rows(
            candidate_rows,
            guid,
            ("action_category", "action_categories", "reason", "count"),
            "candidate_rejections",
        ),
    }
    has_native_rows = any(item.get("status") == "observed" for item in native.values())
    actor_review: dict[str, Any] = {
        "bot_guid": guid,
        "role": role,
        "actor_identity": actor_identity,
        "counterfactual_status": "unavailable",
        "observed": {
            "damage": {"status": "unavailable", "reason": "role_metric_not_in_review"},
            "healing": {"status": "unavailable", "reason": "role_metric_not_in_review"},
            "threat": {"status": "unavailable", "reason": "role_metric_not_in_review"},
            "mitigation": {"status": "unavailable", "reason": "role_metric_not_in_review"},
        },
        "native": native,
        "role_scope": "actor_scoped_role_evidence_only",
    }
    actor_review.update(_present(identity, ("bot_name", "class_spec", "class_name")))
    result: dict[str, Any] = {
        "task": "role_diagnostic",
        "authority": "shadow_advisory_only",
        "detail_scope": "role rows only; missing observations stay unavailable",
        "actor_review": actor_review,
        "limitations": [
            "No DPS baseline for this role.",
            "Damage/healing/threat/mitigation are unavailable.",
            "Shared totals are not actor evidence.",
            "Only actor-scoped native rows are admissible.",
        ],
    }
    for key in ("run_id", "segment_id"):
        if key in state:
            result[key] = state[key]
    outcome = _compact_outcome(state.get("native_gameplay_outcome"))
    if outcome is not None:
        result["native_gameplay_outcome"] = outcome
    return result, has_native_rows


def _compact_actor_state(
    state: Mapping[str, Any],
    boss: Mapping[str, Any],
    actor: Mapping[str, Any],
    timeline: Mapping[str, Any] | None,
) -> dict[str, Any]:
    guid = _guid(actor.get("bot_guid", actor.get("actor_guid")))
    identity = _identity_for_guid(boss, guid)
    full_actor = _metrics_actor(boss, state, guid)

    # Keep the old actor_review key because review_prediction and row identity
    # consumers intentionally read it.  Its nested sections are the bounded
    # Laya projection rather than the unbounded source actor row.
    actor_review: dict[str, Any] = {}
    actor_review.update(_present(actor, ("bot_guid", "class_spec")))
    actor_review.update(
        _present(
            actor,
            (
                "duty_explains_idle",
                "required_assignment_active",
                "assignment_id",
                "assignment_status",
                "assignment_counterfactual_status",
                "counterfactual_status",
            ),
        )
    )
    if identity:
        actor_review["actor_identity"] = identity
    actor_review["observed"] = _present(actor, _OBSERVED_FIELDS)
    actor_review["native"] = _compact_native(actor)
    actor_review["duty"] = _present(
        actor,
        tuple(field for field in _DUTY_FIELDS if field not in {
            "duty_explains_idle", "required_assignment_active", "assignment_status"
        }),
    )
    actor_review["counterfactual"] = _present(
        actor,
        tuple(field for field in _COUNTERFACTUAL_FIELDS if field != "counterfactual_status"),
    )

    pet_source = full_actor or actor
    owner_pet = _present(pet_source, _PET_FIELDS)
    if owner_pet:
        actor_review["owner_pet"] = owner_pet
    else:
        actor_review["owner_pet_evidence"] = "unavailable"

    actor_review["timeline_signal"] = _compact_timeline(
        actor.get("timeline_signal") if isinstance(actor.get("timeline_signal"), Mapping) else timeline,
        actor,
    )

    result: dict[str, Any] = {
        "task": "actor_diagnostic",
        "authority": "shadow_advisory_only",
        "detail_scope": "bounded summaries; omitted rows stay unknown",
        "actor_review": actor_review,
        "limitations": [
            "WCL unmatched is context only.",
            "Landed effects != completed casts.",
            "Owner gaps exclude pets; unknown stays unknown.",
            "Duty overlap blocks repair.",
            "Repair requires eligible counterfactual.",
            "Candidate scans != native failures.",
        ],
    }
    for key in ("run_id", "segment_id"):
        if key in state:
            result[key] = state[key]
    outcome = _compact_outcome(state.get("native_gameplay_outcome"))
    if outcome is not None:
        result["native_gameplay_outcome"] = outcome
    return result


def _actor_question(guid: int | str | None) -> dict[str, Any]:
    return {
        "type": "choice",
        "instructions": "Choose one diagnosis. Unknown stays unknown; advisory only.",
        "criteria": dict(ACTOR_OPTIONS),
    }


def _role_question(guid: int | str | None, has_native_rows: bool) -> dict[str, Any]:
    criteria = (
        {
            "native_action_review": ROLE_OPTIONS["native_action_review"],
            "insufficient_role_evidence": ROLE_OPTIONS["insufficient_role_evidence"],
            "collect_more_canaries": ROLE_OPTIONS["collect_more_canaries"],
        }
        if has_native_rows
        else {
            "insufficient_role_evidence": ROLE_OPTIONS["insufficient_role_evidence"],
            "collect_more_canaries": ROLE_OPTIONS["collect_more_canaries"],
        }
    )
    return {
        "type": "choice",
        "instructions": (
            "Choose only from actor-scoped role evidence. "
            "Missing data stays unavailable; advisory only."
        ),
        "criteria": criteria,
    }


def actor_packets(review: Mapping[str, Any], model: str = MODEL) -> list[dict[str, Any]]:
    """Build one compact Laya diagnostic packet per actor."""
    input_section = review.get("jev_input")
    state = input_section.get("state") if isinstance(input_section, Mapping) else None
    if not isinstance(state, Mapping):
        return []
    boss = state.get("boss_dps_review")
    if not isinstance(boss, Mapping):
        return []
    timeline = boss.get("timeline_comparison")
    timeline = timeline if isinstance(timeline, Mapping) else {}
    packets: list[dict[str, Any]] = []
    seen: set[str] = set()
    loss_signals = boss.get("actor_loss_signals")
    loss_signals = loss_signals if isinstance(loss_signals, list) else []
    identity_rows = _identity_rows(boss.get("actor_identity"))
    roster_rows = identity_rows or [
        row for row in loss_signals if isinstance(row, Mapping)
    ]
    for identity_row in roster_rows:
        if not isinstance(identity_row, Mapping):
            continue
        guid = _guid(identity_row.get("bot_guid", identity_row.get("actor_guid")))
        if guid is None or str(guid) in seen:
            continue
        seen.add(str(guid))
        actor = _row_for_guid(loss_signals, guid)
        role = str(identity_row.get("role") or "").lower()
        if actor is not None and role in {"", "dps"}:
            timeline_actor = _row_for_guid(timeline.get("actors"), guid)
            state_projection = _compact_actor_state(state, boss, actor, timeline_actor)
            question = _actor_question(guid)
        else:
            state_projection, has_native_rows = _role_actor_state(state, boss, identity_row)
            question = _role_question(guid, has_native_rows)
        packets.append(
            {
                "model": model,
                "state": state_projection,
                "questions": {f"actor_action_{guid}": question},
            }
        )
    return packets


def estimated_tokens(value: Any) -> int:
    """Heuristic budget estimate used by focused tests.

    The production server tokenizer and receipt remain authoritative; this is
    only a local early warning for unexpectedly large projections.
    """
    import json

    text = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return max(1, (len(text) + 2) // 3)


__all__ = [
    "MODEL",
    "ACTOR_OPTIONS",
    "ROLE_OPTIONS",
    "actor_packets",
    "estimated_tokens",
]
