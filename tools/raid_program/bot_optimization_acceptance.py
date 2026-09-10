"""Compare two matched raid timeline summaries without promoting a clear to performance.

The comparator consumes compact ``cata_raid_bot_timeline_summary_v1`` documents.
Setup equivalence and requested-repair evidence are separate explicit inputs so a
kill, fixture, or aggregate DPS value cannot silently satisfy another gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence


SUMMARY_SCHEMA = "cata_raid_bot_timeline_summary_v1"
SETUP_SCHEMA = "cata_raid_bot_optimization_setup_match_v1"
REPAIR_SCHEMA = "cata_raid_requested_repair_assertions_v1"
OUTPUT_SCHEMA = "cata_raid_bot_optimization_acceptance_v1"
REPORT_SOURCE_FIELDS = (
    "schema_version",
    "capture_id",
    "scenario_id",
    "started_at_utc",
    "source_identity",
    "binary_sha256",
    "config_sha256",
    "runtime_profile",
    "runtime_identity",
    "accepted_boss_identity",
    "raw_normalized_batch",
)

REQUIRED_SETUP_FIELDS = (
    "roster",
    "loadout",
    "route",
    "profile",
    "config",
    "encounter",
    "runtime_assets",
)
REPAIR_EVIDENCE_CLASSES = {
    "attributable_observation",
    "native_outcome",
    "native_trace",
}
SUPPORTED_SOURCE_CHANGE_FIELDS = (
    "source_commit",
    "source_tree",
    "binary_sha256",
    "config_sha256",
    "runtime_profile",
    "profile_content_hash",
)


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _timeline_source_sha256(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _number(value: object, *, positive: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0) or result < 0.0:
        return None
    return result


def _nonempty_strings(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def _sha256_string(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _hex_string(value: object, length: int) -> bool:
    if not isinstance(value, str) or len(value) != length:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _report_source_rejections(
    source: dict[str, Any], identity: dict[str, Any], label: str,
) -> list[str]:
    """Verify the noncircular projection emitted before capture finalization."""
    reasons: list[str] = []
    raw_sha256 = source.get("raw_sha256")
    if not _sha256_string(raw_sha256):
        reasons.append(f"{label}_source_raw_sha256_missing")

    report_sha256 = source.get("report_sha256")
    if report_sha256 is not None and not _sha256_string(report_sha256):
        reasons.append(f"{label}_source_report_sha256_invalid")

    projection = source.get("report_source")
    declared_projection_sha256 = source.get("report_source_sha256")
    if not isinstance(projection, dict):
        reasons.append(f"{label}_source_report_source_missing")
        return reasons
    if not _sha256_string(declared_projection_sha256):
        reasons.append(f"{label}_source_report_source_sha256_missing")
    elif declared_projection_sha256 != _timeline_source_sha256(projection):
        reasons.append(f"{label}_source_report_source_sha256_mismatch")

    for field in REPORT_SOURCE_FIELDS:
        if field not in projection:
            reasons.append(f"{label}_source_report_source_{field}_missing")

    if projection.get("schema_version") != 1:
        reasons.append(f"{label}_source_report_schema_version_unsupported")
    for field in ("capture_id", "scenario_id", "started_at_utc", "runtime_profile"):
        if not isinstance(projection.get(field), str) or not projection[field].strip():
            reasons.append(f"{label}_source_report_source_{field}_empty")
    for field in ("binary_sha256", "config_sha256"):
        if not _sha256_string(projection.get(field)):
            reasons.append(f"{label}_source_report_source_{field}_invalid")

    source_identity = projection.get("source_identity")
    if not isinstance(source_identity, dict):
        reasons.append(f"{label}_source_report_source_identity_missing")
    else:
        if not _hex_string(source_identity.get("head"), 40):
            reasons.append(f"{label}_source_commit_missing")
        if not _hex_string(source_identity.get("tree"), 40):
            reasons.append(f"{label}_source_tree_missing")
        if source_identity.get("clean") is not True:
            reasons.append(f"{label}_source_identity_not_clean")

    raw_batch = projection.get("raw_normalized_batch")
    if not isinstance(raw_batch, dict):
        reasons.append(f"{label}_source_raw_batch_identity_missing")
    else:
        if raw_batch.get("sha256") != raw_sha256:
            reasons.append(f"{label}_source_raw_batch_sha256_mismatch")
        row_count = raw_batch.get("row_count")
        if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count <= 0:
            reasons.append(f"{label}_source_raw_batch_row_count_missing")

    for field in ("capture_id", "scenario_id"):
        if projection.get(field) != identity.get(field):
            reasons.append(f"{label}_source_{field}_binding_mismatch")
    runtime = projection.get("runtime_identity")
    if not isinstance(runtime, dict):
        reasons.append(f"{label}_source_runtime_identity_missing")
    else:
        for field in (
            "server_epoch",
            "attempt_id",
            "profile_generation",
            "profile_content_hash",
        ):
            if runtime.get(field) is None:
                reasons.append(f"{label}_source_runtime_{field}_missing")
            elif runtime.get(field) != identity.get(field):
                reasons.append(f"{label}_source_runtime_{field}_binding_mismatch")
        for field in (
            "map_id",
            "instance_id",
            "group_guid",
            "expected_size",
            "expected_difficulty",
            "strategy_id",
        ):
            if runtime.get(field) is None or runtime.get(field) == "":
                reasons.append(f"{label}_source_runtime_{field}_missing")
        wipe_generation = runtime.get("wipe_generation")
        if (
            isinstance(wipe_generation, bool)
            or not isinstance(wipe_generation, int)
            or wipe_generation < 0
        ):
            reasons.append(f"{label}_source_runtime_wipe_generation_missing")

    accepted_boss = projection.get("accepted_boss_identity")
    if not isinstance(accepted_boss, dict) or not accepted_boss:
        reasons.append(f"{label}_source_accepted_boss_identity_missing")
    return reasons


def _identity_present(value: object) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        numeric = _number(value)
        return numeric is not None and numeric > 0.0
    if isinstance(value, list):
        return bool(value) and all(_identity_present(item) for item in value)
    if isinstance(value, dict):
        return bool(value) and all(
            isinstance(key, str) and bool(key.strip()) and _identity_present(item)
            for key, item in value.items()
        )
    return False


def _zeroish(value: object) -> bool:
    if value in (None, 0, False):
        return True
    if isinstance(value, (list, dict, str)):
        return len(value) == 0
    return False


def _close(left: float, right: float) -> bool:
    return abs(left - right) <= max(0.001, abs(left) * 1e-9)


def _clear_acceptance(summary: dict[str, Any]) -> tuple[bool, list[str]]:
    value = summary.get("clear_accepted")
    if not isinstance(value, bool):
        outcome = summary.get("outcome")
        value = outcome.get("clear_accepted") if isinstance(outcome, dict) else None
    if not isinstance(value, bool):
        return False, ["candidate_clear_acceptance_missing"]
    return value, ([] if value else ["candidate_clear_not_accepted"])


def _summary_source_field(summary: dict[str, Any] | None, field: object) -> object:
    if not isinstance(summary, dict) or not isinstance(field, str):
        return None
    identity = summary.get("identity")
    source = identity.get("source") if isinstance(identity, dict) else None
    projection = source.get("report_source") if isinstance(source, dict) else None
    if not isinstance(projection, dict):
        return None
    source_identity = projection.get("source_identity")
    runtime_identity = projection.get("runtime_identity")
    fields = {
        "source_commit": (
            source_identity.get("head") if isinstance(source_identity, dict) else None
        ),
        "source_tree": (
            source_identity.get("tree") if isinstance(source_identity, dict) else None
        ),
        "binary_sha256": projection.get("binary_sha256"),
        "config_sha256": projection.get("config_sha256"),
        "runtime_profile": projection.get("runtime_profile"),
        "profile_content_hash": (
            runtime_identity.get("profile_content_hash")
            if isinstance(runtime_identity, dict) else None
        ),
    }
    return fields.get(field)


def evaluate_setup_match(
    setup: dict[str, Any], *,
    baseline_summary: dict[str, Any] | None = None,
    candidate_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    comparisons: dict[str, Any] = {}
    if setup.get("schema") != SETUP_SCHEMA:
        reasons.append("setup_schema_mismatch")
    fields = setup.get("fields")
    if not isinstance(fields, dict):
        fields = {}
        reasons.append("setup_fields_missing")

    for field in REQUIRED_SETUP_FIELDS:
        row = fields.get(field)
        row_reasons: list[str] = []
        if not isinstance(row, dict):
            row_reasons.append("missing")
            baseline = candidate = None
        else:
            baseline = row.get("baseline")
            candidate = row.get("candidate")
            if "baseline" not in row or "candidate" not in row:
                row_reasons.append("identity_missing")
            elif not _identity_present(baseline) or not _identity_present(candidate):
                row_reasons.append("identity_empty")
            if not _nonempty_strings(row.get("evidence")):
                row_reasons.append("evidence_missing")
            if canonical_sha256(baseline) != canonical_sha256(candidate):
                row_reasons.append("mismatch")
        comparisons[field] = {
            "matched": not row_reasons,
            "baseline_sha256": canonical_sha256(baseline),
            "candidate_sha256": canonical_sha256(candidate),
            "reasons": row_reasons,
        }
        reasons.extend(f"setup_{field}_{reason}" for reason in row_reasons)

    changes = setup.get("intentional_source_changes")
    if not isinstance(changes, list):
        reasons.append("intentional_source_changes_missing")
        changes = []
    normalized_changes: list[dict[str, Any]] = []
    for index, row in enumerate(changes):
        row_reasons: list[str] = []
        if not isinstance(row, dict):
            row_reasons.append("invalid")
            row = {}
        for key in ("field", "baseline", "candidate", "reason"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                row_reasons.append(f"{key}_missing")
        if row.get("baseline") == row.get("candidate"):
            row_reasons.append("values_equal")
        if not _nonempty_strings(row.get("evidence")):
            row_reasons.append("evidence_missing")
        observed_baseline = _summary_source_field(baseline_summary, row.get("field"))
        observed_candidate = _summary_source_field(candidate_summary, row.get("field"))
        if observed_baseline is None or observed_candidate is None:
            row_reasons.append("summary_source_field_unavailable")
        else:
            if row.get("baseline") != observed_baseline:
                row_reasons.append("baseline_summary_binding_mismatch")
            if row.get("candidate") != observed_candidate:
                row_reasons.append("candidate_summary_binding_mismatch")
        reasons.extend(
            f"intentional_source_change_{index}_{reason}" for reason in row_reasons
        )
        normalized_changes.append(
            {
                "field": row.get("field"),
                "baseline": row.get("baseline"),
                "candidate": row.get("candidate"),
                "reason": row.get("reason"),
                "observed_baseline": observed_baseline,
                "observed_candidate": observed_candidate,
                "valid": not row_reasons,
                "reasons": row_reasons,
            }
        )

    for field in SUPPORTED_SOURCE_CHANGE_FIELDS:
        observed_baseline = _summary_source_field(baseline_summary, field)
        observed_candidate = _summary_source_field(candidate_summary, field)
        if (
            observed_baseline is None
            or observed_candidate is None
            or canonical_sha256(observed_baseline) == canonical_sha256(observed_candidate)
        ):
            continue
        valid_declarations = [
            row for row in normalized_changes
            if row["field"] == field
            and row["valid"]
            and row["observed_baseline"] == observed_baseline
            and row["observed_candidate"] == observed_candidate
        ]
        if not valid_declarations:
            reasons.append(f"intentional_source_change_{field}_undeclared")
        elif len(valid_declarations) > 1:
            reasons.append(f"intentional_source_change_{field}_duplicate")

    role_assertions = setup.get("actor_roles", {})
    normalized_roles: dict[str, Any] = {}
    if not isinstance(role_assertions, dict):
        reasons.append("setup_actor_roles_invalid")
        role_assertions = {}
    baseline_actors = (
        baseline_summary.get("actors") if isinstance(baseline_summary, dict) else {}
    )
    candidate_actors = (
        candidate_summary.get("actors") if isinstance(candidate_summary, dict) else {}
    )
    for guid, row in role_assertions.items():
        row_reasons: list[str] = []
        if not isinstance(guid, str) or not guid.strip() or not isinstance(row, dict):
            row_reasons.append("invalid")
            row = {}
        baseline_role = row.get("baseline")
        candidate_role = row.get("candidate")
        for label, role in (("baseline", baseline_role), ("candidate", candidate_role)):
            if role not in {"tank", "healer", "dps"}:
                row_reasons.append(f"{label}_invalid")
        if baseline_role != candidate_role:
            row_reasons.append("mismatch")
        if not _nonempty_strings(row.get("evidence")):
            row_reasons.append("evidence_missing")
        for label, actors, declared in (
            ("baseline", baseline_actors, baseline_role),
            ("candidate", candidate_actors, candidate_role),
        ):
            actor = actors.get(guid) if isinstance(actors, dict) else None
            if not isinstance(actor, dict):
                row_reasons.append(f"{label}_actor_missing")
                continue
            observed = actor.get("role")
            if isinstance(observed, str) and observed.strip() and observed != declared:
                row_reasons.append(f"{label}_summary_role_mismatch")
        reasons.extend(f"setup_actor_role_{guid}_{reason}" for reason in row_reasons)
        normalized_roles[guid] = {
            "baseline": baseline_role,
            "candidate": candidate_role,
            "accepted": not row_reasons,
            "basis": "explicit_reviewed_role_assertion_bound_to_summary_hashes",
            "evidence_pointer_contents_verified": False,
            "reasons": row_reasons,
        }

    summary_bindings: dict[str, Any] = {}
    for label, summary in (
        ("baseline", baseline_summary),
        ("candidate", candidate_summary),
    ):
        declared = setup.get(f"{label}_summary_sha256")
        observed = canonical_sha256(summary) if isinstance(summary, dict) else None
        valid = _sha256_string(declared) and declared == observed
        if not valid:
            reasons.append(f"setup_{label}_summary_binding_mismatch")
        summary_bindings[label] = {
            "declared_sha256": declared,
            "observed_sha256": observed,
            "verified": valid,
        }

    return {
        "accepted": not reasons,
        "basis": "explicit_reviewed_assertions_bound_to_summary_hashes",
        "evidence_pointer_contents_verified": False,
        "summary_bindings": summary_bindings,
        "comparisons": comparisons,
        "intentional_source_changes": normalized_changes,
        "actor_roles": normalized_roles,
        "reasons": list(dict.fromkeys(reasons)),
    }


def evaluate_repair_assertions(assertions: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if assertions.get("schema") != REPAIR_SCHEMA:
        reasons.append("repair_schema_mismatch")
    requested = assertions.get("requested") is True
    repair_id = assertions.get("repair_id")
    if requested and (not isinstance(repair_id, str) or not repair_id.strip()):
        reasons.append("repair_id_missing")
    rows = assertions.get("assertions")
    if requested and (not isinstance(rows, list) or not rows):
        reasons.append("repair_assertions_missing")
        rows = []
    elif not isinstance(rows, list):
        rows = []

    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        row_reasons: list[str] = []
        if not isinstance(row, dict):
            row_reasons.append("invalid")
            row = {}
        if not isinstance(row.get("id"), str) or not row["id"].strip():
            row_reasons.append("id_missing")
        evidence_class = row.get("evidence_class")
        if evidence_class not in REPAIR_EVIDENCE_CLASSES:
            row_reasons.append("evidence_class_not_attributable")
        if row.get("passed") is not True:
            row_reasons.append("outcome_not_passed")
        if not _nonempty_strings(row.get("evidence")):
            row_reasons.append("evidence_missing")
        reasons.extend(f"repair_assertion_{index}_{reason}" for reason in row_reasons)
        normalized.append(
            {
                "id": row.get("id"),
                "evidence_class": evidence_class,
                "passed": row.get("passed") is True,
                "accepted": not row_reasons,
                "reasons": row_reasons,
            }
        )

    accepted = requested and bool(normalized) and not reasons
    if not requested:
        reasons.append("repair_not_requested")
    return {
        "requested": requested,
        "repair_id": repair_id,
        "accepted": accepted,
        "basis": "explicit_reviewed_requested_repair_assertions",
        "evidence_pointer_contents_verified": False,
        "assertions": normalized,
        "reasons": list(dict.fromkeys(reasons)),
    }


def _timeline_rejections(summary: dict[str, Any], label: str) -> list[str]:
    reasons: list[str] = []
    if summary.get("schema") != SUMMARY_SCHEMA:
        reasons.append(f"{label}_summary_schema_mismatch")
    identity = summary.get("identity")
    if not isinstance(identity, dict):
        reasons.append(f"{label}_identity_missing")
    else:
        source = identity.get("source")
        if not isinstance(source, dict):
            reasons.append(f"{label}_source_evidence_identity_missing")
        else:
            reasons.extend(_report_source_rejections(source, identity, label))
    window = summary.get("window")
    if not isinstance(window, dict):
        reasons.append(f"{label}_window_missing")
    else:
        if window.get("complete") is not True:
            reasons.append(f"{label}_window_incomplete")
        if _number(window.get("elapsed_seconds"), positive=True) is None:
            reasons.append(f"{label}_elapsed_seconds_missing")
        if _number(window.get("first_hostile_at_ms")) is None:
            reasons.append(f"{label}_first_hostile_missing")
        if _number(window.get("native_boss_death_at_ms"), positive=True) is None:
            reasons.append(f"{label}_native_boss_death_missing")
    accounting = summary.get("accounting")
    if not isinstance(accounting, dict):
        reasons.append(f"{label}_accounting_missing")
    else:
        party_dps = _number(accounting.get("exact_party_dps"), positive=True)
        hostile_damage = _number(accounting.get("hostile_originated_damage"), positive=True)
        if party_dps is None:
            reasons.append(f"{label}_exact_party_dps_missing")
        if hostile_damage is None:
            reasons.append(f"{label}_hostile_originated_damage_missing")
        elapsed = _number(
            (window if isinstance(window, dict) else {}).get("elapsed_seconds"),
            positive=True,
        )
        if (
            party_dps is not None and hostile_damage is not None and elapsed is not None
            and not _close(party_dps, hostile_damage / elapsed)
        ):
            reasons.append(f"{label}_party_dps_accounting_mismatch")
    actors = summary.get("actors")
    if not isinstance(actors, dict) or not actors:
        reasons.append(f"{label}_actors_missing")
    phases = summary.get("phase_intervals")
    if not isinstance(phases, list) or not phases:
        reasons.append(f"{label}_phase_coverage_missing")
    else:
        for index, phase in enumerate(phases):
            if not isinstance(phase, dict):
                reasons.append(f"{label}_phase_{index}_invalid")
                continue
            if not isinstance(phase.get("phase"), str) or not phase["phase"]:
                reasons.append(f"{label}_phase_{index}_name_missing")
            start = _number(phase.get("start_at_ms", phase.get("start_ms")))
            end = _number(phase.get("end_at_ms", phase.get("end_ms")))
            if start is None or end is None or end < start:
                reasons.append(f"{label}_phase_{index}_bounds_missing")
            if not phase.get("boundary_provenance"):
                reasons.append(f"{label}_phase_{index}_provenance_missing")
            if phase.get("conflict") is True:
                reasons.append(f"{label}_phase_{index}_conflict")
    completeness = summary.get("completeness")
    if not isinstance(completeness, dict):
        reasons.append(f"{label}_completeness_missing")
    else:
        for field in ("raw_available", "report_available", "typed_attack_origin_available"):
            if completeness.get(field) is not True:
                reasons.append(f"{label}_{field}_false_or_missing")
        for field in ("combat_gaps", "trace_gaps", "identity_rejections"):
            if not _zeroish(completeness.get(field)):
                reasons.append(f"{label}_{field}_present")
        if completeness.get("absent_pre_failure_trace") is True:
            reasons.append(f"{label}_absent_pre_failure_trace")
    return reasons


def _latency_ms(actor: dict[str, Any]) -> float | None:
    value = actor.get("target_switch_latency_ms")
    direct = _number(value)
    if direct is not None:
        return direct
    if isinstance(value, list):
        observed = sorted(
            metric for row in value if isinstance(row, dict)
            if (metric := _number(row.get("latency_ms"))) is not None
        )
        if not observed:
            return None
        middle = len(observed) // 2
        return (
            observed[middle]
            if len(observed) % 2
            else (observed[middle - 1] + observed[middle]) / 2.0
        )
    if not isinstance(value, dict):
        return None
    for field in ("median", "median_ms", "observed"):
        result = _number(value.get(field))
        if result is not None:
            return result
    return None


def _target_damage(actor: dict[str, Any]) -> tuple[float | None, float | None]:
    aggregate = actor.get("target_damage")
    if isinstance(aggregate, dict):
        return _number(aggregate.get("boss")), _number(aggregate.get("add"))
    damage = actor.get("damage")
    if isinstance(damage, dict) and ("boss" in damage or "add" in damage):
        return _number(damage.get("boss")), _number(damage.get("add"))
    allocations = actor.get("target_allocations")
    rows = list(allocations.values()) if isinstance(allocations, dict) else allocations
    if not isinstance(rows, list):
        return None, None
    totals: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            return None, None
        target_class = row.get("target_class")
        value = _number(row.get("hostile_originated_damage"))
        if target_class not in {"boss", "add"} or value is None:
            return None, None
        totals[target_class] = totals.get(target_class, 0.0) + value
    return totals.get("boss"), totals.get("add")


def _actor_metrics(
    actor: dict[str, Any], elapsed_seconds: float, label: str, guid: str,
    *, role_override: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    damage = actor.get("damage")
    dps = actor.get("dps")
    activity = actor.get("activity")
    survival = actor.get("survival")
    observed_role = actor.get("role")
    role = (
        observed_role
        if isinstance(observed_role, str) and observed_role.strip()
        else role_override
    )
    hostile_damage = (
        _number(damage.get("hostile_originated")) if isinstance(damage, dict) else None
    )
    direct_damage = (
        _number(damage.get("direct")) if isinstance(damage, dict) else None
    )
    exact_dps = (
        _number(dps.get("hostile_originated")) if isinstance(dps, dict) else None
    )
    if exact_dps is None and isinstance(damage, dict):
        exact_dps = _number(damage.get("dps"))
    if hostile_damage is None:
        reasons.append(f"{label}_actor_{guid}_hostile_damage_missing")
    if exact_dps is None:
        reasons.append(f"{label}_actor_{guid}_exact_dps_missing")
    elif hostile_damage is not None and not _close(exact_dps, hostile_damage / elapsed_seconds):
        reasons.append(f"{label}_actor_{guid}_dps_accounting_mismatch")
    effective_healing = _number(actor.get("effective_healing"))
    exact_hps = _number(actor.get("effective_hps"))
    effective_role = role
    offensive_required = (
        effective_role in {"dps", "tank"}
        or (hostile_damage is not None and hostile_damage > 0.0)
    )
    healing_required = effective_role == "healer"
    if not isinstance(effective_role, str) or not effective_role.strip():
        reasons.append(f"{label}_actor_{guid}_role_missing")
    if offensive_required and direct_damage is None:
        reasons.append(f"{label}_actor_{guid}_direct_damage_missing")
    if healing_required:
        if effective_healing is None:
            reasons.append(f"{label}_actor_{guid}_effective_healing_missing")
        if exact_hps is None:
            reasons.append(f"{label}_actor_{guid}_exact_hps_missing")
        elif effective_healing is not None and not _close(
            exact_hps, effective_healing / elapsed_seconds
        ):
            reasons.append(f"{label}_actor_{guid}_hps_accounting_mismatch")
    active_seconds = (
        _number(activity.get("active_seconds")) if isinstance(activity, dict) else None
    )
    if active_seconds is None or active_seconds > elapsed_seconds:
        reasons.append(f"{label}_actor_{guid}_activity_missing")
        active_fraction = None
    else:
        active_fraction = active_seconds / elapsed_seconds
    attack_outage_ms = (
        _number(activity.get("longest_fresh_attack_outage_ms"))
        if isinstance(activity, dict) else None
    )
    if offensive_required and attack_outage_ms is None:
        reasons.append(f"{label}_actor_{guid}_attack_outage_missing")
    death_observed = survival.get("death_observed") if isinstance(survival, dict) else None
    if not isinstance(death_observed, bool) and isinstance(survival, dict):
        if _number(survival.get("death_observed_at_ms"), positive=True) is not None:
            death_observed = True
        elif survival.get("alive_at_end") is True:
            death_observed = False
    if not isinstance(death_observed, bool):
        reasons.append(f"{label}_actor_{guid}_survival_missing")
    boss_damage, add_damage = _target_damage(actor)
    if offensive_required and boss_damage is None:
        reasons.append(f"{label}_actor_{guid}_boss_damage_missing")
    if offensive_required and add_damage is None:
        reasons.append(f"{label}_actor_{guid}_add_damage_missing")
    if (
        offensive_required
        and hostile_damage is not None
        and boss_damage is not None
        and add_damage is not None
        and not _close(hostile_damage, boss_damage + add_damage)
    ):
        reasons.append(f"{label}_actor_{guid}_target_damage_accounting_mismatch")
    latency = _latency_ms(actor)
    switch_observation_complete = actor.get("target_switch_observation_complete")
    if offensive_required and latency is None and switch_observation_complete is not True:
        reasons.append(f"{label}_actor_{guid}_target_switch_latency_missing")
    return {
        "role": effective_role,
        "role_basis": (
            "summary_identity"
            if isinstance(observed_role, str) and observed_role.strip()
            else (
                "explicit_reviewed_setup_assertion"
                if role_override is not None else "missing"
            )
        ),
        "offensive_metrics_required": offensive_required,
        "healing_metrics_required": healing_required,
        "hostile_damage": hostile_damage,
        "exact_dps": exact_dps,
        "direct_damage": direct_damage,
        "direct_dps": direct_damage / elapsed_seconds if direct_damage is not None else None,
        "effective_healing": effective_healing,
        "exact_hps": exact_hps,
        "active_seconds": active_seconds,
        "active_fraction": active_fraction,
        "longest_fresh_attack_outage_ms": attack_outage_ms,
        "boss_damage": boss_damage,
        "boss_dps": boss_damage / elapsed_seconds if boss_damage is not None else None,
        "add_damage": add_damage,
        "add_dps": add_damage / elapsed_seconds if add_damage is not None else None,
        "death_observed": death_observed,
        "target_switch_latency_ms": latency,
        "target_switch_observation_complete": switch_observation_complete is True,
        "target_switch_opportunity_observed": latency is not None,
    }, reasons


def _decline_pct(baseline: float, candidate: float) -> float | None:
    if baseline <= 0.0:
        return None
    return (baseline - candidate) * 100.0 / baseline


def _increase_pct(baseline: float, candidate: float) -> float | None:
    if baseline <= 0.0:
        return None
    return (candidate - baseline) * 100.0 / baseline


def _phase_coverage(summary: dict[str, Any]) -> dict[str, Any]:
    phases: dict[str, float] = {}
    sequence: list[str] = []
    for row in summary.get("phase_intervals", []):
        phase = str(row["phase"])
        start = row.get("start_at_ms", row.get("start_ms"))
        end = row.get("end_at_ms", row.get("end_ms"))
        duration = (float(end) - float(start)) / 1000.0
        phases[phase] = phases.get(phase, 0.0) + duration
        sequence.append(phase)
    return {"sequence": sequence, "seconds_by_phase": phases}


def compare_optimization_acceptance(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    setup_match: dict[str, Any],
    repair_assertions: dict[str, Any],
    *,
    material_decline_threshold_pct: float = 5.0,
) -> dict[str, Any]:
    """Return independent clear, repair, and matched performance decisions."""

    threshold = _number(material_decline_threshold_pct, positive=True)
    if threshold is None or threshold >= 100.0:
        raise ValueError("material decline threshold must be greater than 0 and less than 100")

    clear_accepted, clear_reasons = _clear_acceptance(candidate)
    setup = evaluate_setup_match(
        setup_match,
        baseline_summary=baseline,
        candidate_summary=candidate,
    )
    repair = evaluate_repair_assertions(repair_assertions)
    sufficiency_reasons = [
        *_timeline_rejections(baseline, "baseline"),
        *_timeline_rejections(candidate, "candidate"),
    ]
    if not setup["accepted"]:
        sufficiency_reasons.extend(setup["reasons"])

    baseline_actors = baseline.get("actors") if isinstance(baseline.get("actors"), dict) else {}
    candidate_actors = candidate.get("actors") if isinstance(candidate.get("actors"), dict) else {}
    if set(baseline_actors) != set(candidate_actors):
        sufficiency_reasons.append("actor_identity_set_mismatch")

    baseline_elapsed = _number((baseline.get("window") or {}).get("elapsed_seconds"), positive=True)
    candidate_elapsed = _number((candidate.get("window") or {}).get("elapsed_seconds"), positive=True)
    actor_metrics: dict[str, Any] = {}
    reviewed_roles = setup.get("actor_roles", {})
    if baseline_elapsed is not None and candidate_elapsed is not None:
        for guid in sorted(set(baseline_actors) & set(candidate_actors), key=str):
            role_assertion = reviewed_roles.get(str(guid), {})
            if not isinstance(role_assertion, dict) or role_assertion.get("accepted") is not True:
                role_assertion = {}
            before, before_reasons = _actor_metrics(
                baseline_actors[guid], baseline_elapsed, "baseline", str(guid),
                role_override=role_assertion.get("baseline"),
            )
            after, after_reasons = _actor_metrics(
                candidate_actors[guid], candidate_elapsed, "candidate", str(guid),
                role_override=role_assertion.get("candidate"),
            )
            sufficiency_reasons.extend(before_reasons)
            sufficiency_reasons.extend(after_reasons)
            if before["role"] != after["role"]:
                sufficiency_reasons.append(f"actor_{guid}_role_mismatch")
            actor_metrics[str(guid)] = {"baseline": before, "candidate": after}

    sufficiency_reasons = list(dict.fromkeys(sufficiency_reasons))
    baseline_party_dps = _number((baseline.get("accounting") or {}).get("exact_party_dps"), positive=True)
    candidate_party_dps = _number((candidate.get("accounting") or {}).get("exact_party_dps"), positive=True)
    comparisons: dict[str, Any] = {
        "party": {
            "baseline_exact_dps": baseline_party_dps,
            "candidate_exact_dps": candidate_party_dps,
            "decline_pct": (
                _decline_pct(baseline_party_dps, candidate_party_dps)
                if baseline_party_dps is not None and candidate_party_dps is not None
                else None
            ),
        },
        "actors": {},
        "phase_coverage": {
            "baseline": _phase_coverage(baseline) if not _timeline_rejections(baseline, "baseline") else None,
            "candidate": _phase_coverage(candidate) if not _timeline_rejections(candidate, "candidate") else None,
        },
    }

    material_reasons: list[str] = []
    party_decline = comparisons["party"]["decline_pct"]
    if party_decline is not None and party_decline > threshold:
        material_reasons.append("party_exact_dps_material_decline")

    for guid, pair in actor_metrics.items():
        before = pair["baseline"]
        after = pair["candidate"]
        metrics = {
            "exact_dps_decline_pct": (
                _decline_pct(before["exact_dps"], after["exact_dps"])
                if before["exact_dps"] is not None and after["exact_dps"] is not None
                else None
            ),
            "direct_activity_decline_pct": (
                _decline_pct(before["active_fraction"], after["active_fraction"])
                if before["active_fraction"] is not None and after["active_fraction"] is not None
                else None
            ),
            "direct_damage_rate_decline_pct": (
                _decline_pct(before["direct_dps"], after["direct_dps"])
                if before["direct_dps"] is not None and after["direct_dps"] is not None
                else None
            ),
            "exact_hps_decline_pct": (
                _decline_pct(before["exact_hps"], after["exact_hps"])
                if before["healing_metrics_required"]
                and after["healing_metrics_required"]
                and before["exact_hps"] is not None
                and after["exact_hps"] is not None
                else None
            ),
            "boss_dps_decline_pct": (
                _decline_pct(before["boss_dps"], after["boss_dps"])
                if before["boss_dps"] is not None and after["boss_dps"] is not None
                else None
            ),
            "add_dps_decline_pct": (
                _decline_pct(before["add_dps"], after["add_dps"])
                if before["add_dps"] is not None and after["add_dps"] is not None
                else None
            ),
            "target_switch_latency_increase_pct": (
                _increase_pct(
                    before["target_switch_latency_ms"], after["target_switch_latency_ms"]
                )
                if before["target_switch_latency_ms"] is not None
                and after["target_switch_latency_ms"] is not None
                else None
            ),
            "fresh_attack_outage_increase_pct": (
                _increase_pct(
                    before["longest_fresh_attack_outage_ms"],
                    after["longest_fresh_attack_outage_ms"],
                )
                if before["longest_fresh_attack_outage_ms"] is not None
                and after["longest_fresh_attack_outage_ms"] is not None
                else None
            ),
            "survival_regression": (
                before["death_observed"] is False and after["death_observed"] is True
            ),
            "baseline": before,
            "candidate": after,
        }
        comparisons["actors"][guid] = metrics
        for name in (
            "exact_dps_decline_pct",
            "direct_activity_decline_pct",
            "direct_damage_rate_decline_pct",
            "boss_dps_decline_pct",
            "exact_hps_decline_pct",
        ):
            if metrics[name] is not None and metrics[name] > threshold:
                material_reasons.append(f"actor_{guid}_{name}_material")
        before_latency = before["target_switch_latency_ms"]
        after_latency = after["target_switch_latency_ms"]
        latency_increase = metrics["target_switch_latency_increase_pct"]
        if (
            latency_increase is not None and latency_increase > threshold
        ) or (before_latency == 0.0 and after_latency is not None and after_latency > 0.0):
            material_reasons.append(f"actor_{guid}_target_switch_latency_material")
        before_outage = before["longest_fresh_attack_outage_ms"]
        after_outage = after["longest_fresh_attack_outage_ms"]
        outage_increase = metrics["fresh_attack_outage_increase_pct"]
        if (
            outage_increase is not None and outage_increase > threshold
        ) or (before_outage == 0.0 and after_outage is not None and after_outage > 0.0):
            material_reasons.append(f"actor_{guid}_fresh_attack_outage_material")
        if metrics["survival_regression"]:
            material_reasons.append(f"actor_{guid}_survival_regression")

    if sufficiency_reasons:
        performance_verdict = "inconclusive"
    elif material_reasons:
        performance_verdict = "fail"
    else:
        performance_verdict = "pass"

    return {
        "schema": OUTPUT_SCHEMA,
        "baseline_summary_sha256": canonical_sha256(baseline),
        "candidate_summary_sha256": canonical_sha256(candidate),
        "setup_match_sha256": canonical_sha256(setup_match),
        "repair_assertions_sha256": canonical_sha256(repair_assertions),
        "material_decline_threshold_pct": threshold,
        "threshold_interpretation": "diagnostic_triage_not_scientific_significance",
        "allocation_metric_interpretation": (
            "boss_and_add_rates_are_informational_without_a_proven_mandatory_target_outcome"
        ),
        "target_switch_latency_statistic": "median_observed_ms",
        "single_pair_uncertainty": True,
        "clear_accepted": clear_accepted,
        "clear_reasons": clear_reasons,
        "repair_edge_accepted": repair["accepted"],
        "repair": repair,
        "setup_match_accepted": setup["accepted"],
        "setup_match": setup,
        "performance_verdict": performance_verdict,
        "performance_accepted": True if performance_verdict == "pass" else (
            False if performance_verdict == "fail" else None
        ),
        "diagnosis_required": performance_verdict == "fail",
        "sufficiency_reasons": sufficiency_reasons,
        "material_decline_reasons": list(dict.fromkeys(material_reasons)),
        "comparisons": comparisons,
        "fast_benchmark": setup_match.get("fast_benchmark"),
        "gate_independence": {
            "clear_does_not_imply_repair": True,
            "clear_does_not_imply_performance": True,
            "fixture_does_not_imply_repair": True,
            "repair_does_not_imply_performance": True,
        },
    }


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--baseline", type=Path, required=True)
    result.add_argument("--candidate", type=Path, required=True)
    result.add_argument("--matched-setup", type=Path, required=True)
    result.add_argument("--repair-assertions", type=Path, required=True)
    result.add_argument("--output", type=Path)
    result.add_argument("--material-decline-threshold-pct", type=float, default=5.0)
    return result


def main(arguments: Sequence[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    report = compare_optimization_acceptance(
        _load_json(args.baseline),
        _load_json(args.candidate),
        _load_json(args.matched_setup),
        _load_json(args.repair_assertions),
        material_decline_threshold_pct=args.material_decline_threshold_pct,
    )
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    return {"pass": 0, "fail": 1, "inconclusive": 2}[report["performance_verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
