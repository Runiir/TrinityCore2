"""Evaluate deterministic 300-second role-calibration evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .common import write_json
from .live_validation_session import canonical_sha256, sha256_file


MODES = {
    "single_target_300",
    "aoe_300",
    "tank_threat_300",
    "healer_controlled_damage_300",
}
FAULTS = {
    "missing_damage_delivery",
    "duration_mismatch",
    "one_target_spam",
    "missed_dispels",
    "missing_tank_stance",
    "threat_loss",
    "illegal_actions",
    "cross_window_contamination",
}

RANGED_CALIBRATION_PROFILE_SPECS = frozenset(
    {
        "affliction_warlock",
        "arcane_mage",
        "balance_druid",
        "beast_mastery_hunter",
        "demonology_warlock",
        "destruction_warlock",
        "elemental_shaman",
        "fire_mage",
        "frost_mage",
        "marksmanship_hunter",
        "shadow_priest",
        "survival_hunter",
    }
)


def expected_calibration_profile_lane(target_spec: str) -> str:
    """Mirror the server's immutable calibration lane classification."""
    if not target_spec:
        return ""
    return (
        "ranged"
        if target_spec in RANGED_CALIBRATION_PROFILE_SPECS
        else "melee"
    )


def single_target_fixture_geometry_valid(
    fixture: Mapping[str, Any], target_spec: str
) -> bool:
    """Recompute geometry facts instead of trusting server summary booleans."""
    expected_lane = expected_calibration_profile_lane(target_spec)
    if not expected_lane:
        return False
    try:
        target = tuple(float(fixture[name]) for name in ("x", "y", "z"))
        spawn = tuple(
            float(fixture[name])
            for name in ("bot_spawn_x", "bot_spawn_y", "bot_spawn_z")
        )
        reported_distance = float(fixture["bot_target_distance"])
    except (KeyError, TypeError, ValueError):
        return False
    if not all(math.isfinite(value) for value in (*target, *spawn, reported_distance)):
        return False
    computed_distance = math.dist(target, spawn)
    return (
        str(fixture.get("profile_lane") or "") == expected_lane
        and abs(computed_distance - reported_distance) <= 0.01
        and 0.0 < computed_distance <= 40.0
        and -100_000.0 < spawn[2] < 10_000.0
        and fixture.get("geometry_validated") is True
        and fixture.get("native_line_of_sight") is True
        and fixture.get("native_path_reachable") is True
        and (
            expected_lane != "melee"
            or fixture.get("native_melee_reachable") is True
        )
    )


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else 0.0


def _check(checks: dict[str, bool], reasons: list[str], name: str, passed: bool) -> None:
    checks[name] = bool(passed)
    if not passed:
        reasons.append(name)


def _policy_mode(policy: Mapping[str, Any], mode: str) -> Mapping[str, Any]:
    modes = policy.get("modes") or {}
    selected = modes.get(mode)
    if not isinstance(selected, Mapping):
        raise ValueError(f"calibration policy does not define mode: {mode}")
    return selected


def evaluate_calibration(
    record: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently recompute one role-calibration acceptance decision."""
    mode = str(record.get("mode") or "")
    role = str(record.get("role") or "")
    if mode not in MODES:
        raise ValueError(f"unsupported calibration mode: {mode}")
    mode_policy = _policy_mode(policy, mode)
    identity = record.get("identity") or {}
    window = record.get("window") or {}
    metrics = record.get("metrics") or {}
    checks: dict[str, bool] = {}
    reasons: list[str] = []

    duration = float(window.get("scored_duration_seconds") or 0.0)
    expected_duration = float(policy["scored_window_seconds"])
    tolerance = float(policy["duration_tolerance_seconds"])
    reference_value = float(metrics.get("reference_value") or 0.0)
    measured_value = float(metrics.get("measured_value") or 0.0)
    reference_ratio = _ratio(measured_value, reference_value)

    _check(checks, reasons, "role_allowed_for_mode", role in set(mode_policy.get("roles") or []))
    _check(
        checks,
        reasons,
        "separate_warmup_complete",
        float(window.get("warmup_seconds") or 0.0) >= float(policy["minimum_warmup_seconds"])
        and int(window.get("warmup_ended_at_ms") or 0) <= int(window.get("scored_started_at_ms") or 0),
    )
    _check(checks, reasons, "scored_duration_within_tolerance", abs(duration - expected_duration) <= tolerance)
    _check(checks, reasons, "deterministic_reset_applied", bool(window.get("reset_applied")) and bool(window.get("reset_id")))
    _check(checks, reasons, "no_cross_window_contamination", int(window.get("cross_window_event_count") or 0) == 0)
    _check(checks, reasons, "declared_target_hash", len(str(identity.get("target_sha256") or "")) == 64)
    _check(checks, reasons, "declared_buff_debuff_consumable_hash", len(str(identity.get("conditions_sha256") or "")) == 64)
    _check(checks, reasons, "declared_profile_snapshot", int(identity.get("profile_generation") or 0) > 0 and len(str(identity.get("profile_content_hash") or "")) == 64)
    _check(checks, reasons, "explicit_rule_runtime_authority", str(identity.get("runtime_authority") or "") == "explicit_sql_rule_profiles")
    _check(checks, reasons, "generic_ml_shadow_only", identity.get("generic_ml_runtime_authority") is False)
    _check(checks, reasons, "reference_value_positive", reference_value > 0)
    if (
        record.get("runtime_mode") == "calibration_fixture"
        or record.get("evidence_class") == "non_certifying_calibration_fixture"
    ) and record.get("role") == "dps" and record.get("mode") == "single_target_300":
        compatibility = record.get("reference_condition_compatibility")
        compatibility = (
            compatibility if isinstance(compatibility, Mapping) else {}
        )
        _check(
            checks,
            reasons,
            "reference_conditions_compatible",
            compatibility.get("conditions_compatible") is True
            and compatibility.get("target_spec")
            == str(record.get("target_spec") or "")
            and not compatibility.get("reasons"),
        )
    _check(checks, reasons, "reference_hard_floor", reference_ratio >= float(policy["hard_reference_ratio"]))
    _check(checks, reasons, "no_illegal_actions", int(metrics.get("illegal_action_count") or 0) == 0)

    if mode in {"single_target_300", "aoe_300"}:
        target_count = int(metrics.get("target_count") or 0)
        if mode == "single_target_300":
            _check(checks, reasons, "single_target_only", target_count == int(mode_policy["target_count"]))
            fixture = metrics.get("isolated_fixture_target") or {}
            target_spec = str(
                record.get("target_spec")
                or (record.get("raw_runtime_status") or {}).get("target_spec")
                or ""
            )
            scored_damage = int(metrics.get("scored_damage") or 0)
            _check(
                checks,
                reasons,
                "isolated_single_target_fixture",
                isinstance(fixture, dict)
                and fixture.get("isolated_single_target") is True
                and int(fixture.get("entry") or 0) == 44548
                and int(fixture.get("runtime_guid") or 0)
                    == int(metrics.get("primary_target_guid") or 0)
                and fixture.get("map_id") == 0
                and abs(float(fixture.get("x") or 0.0) - (-9060.0)) <= 0.01
                and abs(float(fixture.get("y") or 0.0) - 520.0) <= 0.01
                and 65.0 <= float(fixture.get("z") or 0.0) <= 85.0
                and float(fixture.get("nearest_other_hostile_clearance") or 0.0)
                    >= 45.0
                and int(fixture.get("provisioned_at_ms") or 0) > 0
                and fixture.get("provisioned_before_scoring") is True
                and single_target_fixture_geometry_valid(fixture, target_spec),
            )
            _check(
                checks,
                reasons,
                "single_target_damage_isolated",
                scored_damage > 0
                and int(metrics.get("primary_target_damage") or 0) == scored_damage
                and int(metrics.get("off_target_damage") or 0) == 0
                and int(metrics.get("observed_distinct_damage_targets") or 0) == 1,
            )
        else:
            _check(checks, reasons, "aoe_target_count", target_count >= int(mode_policy["minimum_target_count"]))
        _check(checks, reasons, "active_dps_recorded", float(metrics.get("active_dps") or 0.0) > 0)
        _check(checks, reasons, "elapsed_dps_recorded", float(metrics.get("elapsed_dps") or 0.0) > 0)
        _check(checks, reasons, "ability_mix_present", len(metrics.get("ability_mix") or {}) >= 2)
        _check(checks, reasons, "rotation_group_coverage", float(metrics.get("rotation_group_coverage") or 0.0) >= float(mode_policy["minimum_rotation_group_coverage"]))
        _check(checks, reasons, "cast_failure_ratio", float(metrics.get("cast_failure_ratio") or 0.0) <= float(mode_policy["maximum_cast_failure_ratio"]))
        _check(checks, reasons, "resource_capping", float(metrics.get("resource_capped_ratio") or 0.0) <= float(mode_policy["maximum_resource_capped_ratio"]))
        _check(checks, reasons, "resource_starvation", float(metrics.get("resource_starved_ratio") or 0.0) <= float(mode_policy["maximum_resource_starved_ratio"]))
        _check(checks, reasons, "active_uptime", float(metrics.get("active_uptime_ratio") or 0.0) >= float(mode_policy["minimum_active_uptime_ratio"]))
        _check(checks, reasons, "movement_range_loss", float(metrics.get("movement_range_loss_ratio") or 0.0) <= float(mode_policy["maximum_movement_range_loss_ratio"]))
        _check(checks, reasons, "pet_contribution_declared", "pet_damage_ratio" in metrics)

    elif mode == "tank_threat_300":
        _check(checks, reasons, "tank_stance_form_presence", bool(metrics.get("tank_stance_form_presence_active")))
        _check(checks, reasons, "tank_dps_recorded", float(metrics.get("active_dps") or 0.0) > 0)
        _check(checks, reasons, "tank_tps_recorded", float(metrics.get("threat_per_second") or 0.0) > 0)
        _check(checks, reasons, "snap_threat", float(metrics.get("snap_threat_success_ratio") or 0.0) >= float(mode_policy["minimum_snap_threat_success_ratio"]))
        _check(checks, reasons, "add_threat", float(metrics.get("add_threat_success_ratio") or 0.0) >= float(mode_policy["minimum_add_threat_success_ratio"]))
        _check(checks, reasons, "all_hostile_retention", float(metrics.get("all_hostile_retention_ratio") or 0.0) >= float(mode_policy["minimum_all_hostile_retention_ratio"]))
        _check(checks, reasons, "threat_aura_uptime", float(metrics.get("threat_aura_uptime_ratio") or 0.0) >= float(mode_policy["minimum_threat_aura_uptime_ratio"]))
        _check(checks, reasons, "healer_exposure", float(metrics.get("healer_exposure_ratio") or 0.0) <= float(mode_policy["maximum_healer_exposure_ratio"]))
        _check(checks, reasons, "mitigation_coverage", float(metrics.get("mitigation_uptime_ratio") or 0.0) >= float(mode_policy["minimum_mitigation_uptime_ratio"]))
        _check(checks, reasons, "damage_smoothing", float(metrics.get("maximum_damage_spike_ratio") or 1.0) <= float(mode_policy["maximum_damage_spike_ratio"]))
        _check(checks, reasons, "survival", int(metrics.get("death_count") or 0) == 0 and float(metrics.get("health_floor_ratio") or 0.0) > 0)
        _check(checks, reasons, "interrupt_coverage", float(metrics.get("interrupt_success_ratio") or 0.0) >= float(mode_policy["minimum_interrupt_success_ratio"]))
        _check(checks, reasons, "defensive_coverage_declared", bool(metrics.get("defensive_coverage")))

    else:
        required_phases = set(mode_policy.get("required_phases") or [])
        scheduled = set(metrics.get("scheduled_phases") or [])
        delivered = set(metrics.get("delivered_phases") or [])
        _check(checks, reasons, "all_damage_phases_scheduled", required_phases <= scheduled)
        _check(checks, reasons, "all_damage_phases_delivered", required_phases <= delivered)
        _check(checks, reasons, "scheduled_delivery_counts_match", int(metrics.get("scheduled_event_count") or 0) == int(metrics.get("delivered_event_count") or -1) and int(metrics.get("delivered_event_count") or 0) > 0)
        _check(checks, reasons, "effective_hps_recorded", float(metrics.get("effective_hps") or 0.0) > 0)
        _check(checks, reasons, "no_party_deaths", int(metrics.get("death_count") or 0) == 0)
        _check(checks, reasons, "health_floor", float(metrics.get("health_floor_ratio") or 0.0) >= float(mode_policy["minimum_health_floor_ratio"]))
        _check(checks, reasons, "overheal", float(metrics.get("overheal_ratio") if metrics.get("overheal_ratio") is not None else 1.0) <= float(mode_policy["maximum_overheal_ratio"]))
        _check(checks, reasons, "absorbs_declared", "absorb_amount" in metrics)
        _check(checks, reasons, "mana_endurance", float(metrics.get("remaining_mana_ratio") or 0.0) >= float(mode_policy["minimum_remaining_mana_ratio"]) and float(metrics.get("time_to_oom_seconds") or 0.0) >= expected_duration)
        _check(checks, reasons, "response_latency", float(metrics.get("response_latency_p95_ms") if metrics.get("response_latency_p95_ms") is not None else 999999.0) <= float(mode_policy["maximum_response_latency_ms"]))
        _check(checks, reasons, "target_selection", float(metrics.get("target_selection_accuracy") or 0.0) >= float(mode_policy["minimum_target_selection_accuracy"]))
        _check(checks, reasons, "dispels", float(metrics.get("dispel_success_ratio") or 0.0) >= float(mode_policy["minimum_dispel_success_ratio"]))
        _check(checks, reasons, "cooldown_required_periods", float(metrics.get("cooldown_success_ratio") or 0.0) >= float(mode_policy["minimum_cooldown_success_ratio"]))
        _check(checks, reasons, "idle_under_demand", float(metrics.get("idle_ratio_under_demand") if metrics.get("idle_ratio_under_demand") is not None else 1.0) <= float(mode_policy["maximum_idle_ratio_under_demand"]))
        _check(checks, reasons, "cast_failure_ratio", float(metrics.get("cast_failure_ratio") if metrics.get("cast_failure_ratio") is not None else 1.0) <= float(mode_policy["maximum_cast_failure_ratio"]))
        triage = metrics.get("triage_target_counts") or {}
        _check(checks, reasons, "unequal_health_triage_not_one_target_spam", len([value for value in triage.values() if int(value) > 0]) >= 3)

    return {
        "schema": "all_spec_role_calibration_evaluation_v1",
        "mode": mode,
        "role": role,
        "reference_ratio": round(reference_ratio, 6),
        "hard_floor_passed": reference_ratio >= float(policy["hard_reference_ratio"]),
        "optimization_target_met": reference_ratio >= float(policy["optimization_reference_ratio"]),
        "checks": checks,
        "failure_reasons": reasons,
        "passed": all(checks.values()),
        "record_sha256": canonical_sha256(record),
        "policy_sha256": canonical_sha256(policy),
    }


def inject_fault(record: Mapping[str, Any], fault: str) -> dict[str, Any]:
    """Return a deep-copied record with exactly one deliberate harness fault."""
    if fault not in FAULTS:
        raise ValueError(f"unsupported calibration fault: {fault}")
    mutated = json.loads(json.dumps(record))
    metrics = mutated["metrics"]
    window = mutated["window"]
    if fault == "missing_damage_delivery":
        metrics["delivered_phases"] = []
        metrics["delivered_event_count"] = 0
    elif fault == "duration_mismatch":
        window["scored_duration_seconds"] = 280
    elif fault == "one_target_spam":
        metrics["triage_target_counts"] = {"tank": 40, "dps_1": 0, "dps_2": 0, "dps_3": 0}
    elif fault == "missed_dispels":
        metrics["dispel_success_ratio"] = 0.0
    elif fault == "missing_tank_stance":
        metrics["tank_stance_form_presence_active"] = False
    elif fault == "threat_loss":
        metrics["all_hostile_retention_ratio"] = 0.5
    elif fault == "illegal_actions":
        metrics["illegal_action_count"] = 1
    elif fault == "cross_window_contamination":
        window["cross_window_event_count"] = 1
    return mutated


def load_policy(path: Path) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("runtime_authority") != "explicit_sql_rule_profiles" or policy.get("generic_ml_runtime_authority") is not False:
        raise ValueError("calibration policy must keep explicit rules authoritative and ML shadow-only")
    return policy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=Path("experiments/configs/all_spec_role_calibration_policy_v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = json.loads(args.input.read_text(encoding="utf-8"))
    policy = load_policy(args.policy)
    result = evaluate_calibration(record, policy)
    result["policy_file_sha256"] = sha256_file(args.policy)
    write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
