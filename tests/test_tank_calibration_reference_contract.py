from __future__ import annotations

from pathlib import Path

from tools.bot_ml.role_calibration_harness import evaluate_calibration, load_policy


def _record(*, compatible: bool) -> dict:
    return {
        "schema": "all_spec_role_calibration_record_v1",
        "mode": "tank_threat_300",
        "role": "tank",
        "target_spec": "blood_death_knight",
        "identity": {
            "target_sha256": "a" * 64,
            "conditions_sha256": "b" * 64,
            "profile_generation": 1,
            "profile_content_hash": "c" * 64,
            "runtime_authority": "explicit_sql_rule_profiles",
            "generic_ml_runtime_authority": False,
        },
        "window": {
            "warmup_seconds": 15,
            "warmup_ended_at_ms": 1000,
            "scored_started_at_ms": 1000,
            "scored_ended_at_ms": 301000,
            "scored_duration_seconds": 300,
            "reset_applied": True,
            "reset_id": "blood-test",
            "cross_window_event_count": 0,
        },
        "metrics": {
            "reference_value": 50_000,
            "measured_value": 50_000,
            "active_dps": 50_000,
            "threat_per_second": 100,
            "target_count": 6,
            "tank_stance_form_presence_active": True,
            "snap_threat_success_ratio": 1.0,
            "add_threat_success_ratio": 1.0,
            "all_hostile_retention_ratio": 1.0,
            "threat_aura_uptime_ratio": 1.0,
            "healer_exposure_ratio": 0.0,
            "mitigation_uptime_ratio": 1.0,
            "maximum_damage_spike_ratio": 0.1,
            "death_count": 0,
            "health_floor_ratio": 1.0,
            "interrupt_success_ratio": 1.0,
            "defensive_coverage": {"defensive_action_count": 1},
            "illegal_action_count": 0,
        },
        "reference_condition_compatibility": {
            "target_spec": "blood_death_knight",
            "conditions_compatible": compatible,
            "reasons": [] if compatible else ["runtime_reference_condition_observation_valid"],
        },
    }


def test_incompatible_tank_reference_is_not_classified_as_throughput_failure():
    policy = load_policy(Path("experiments/configs/all_spec_role_calibration_policy_v3.json"))

    result = evaluate_calibration(_record(compatible=False), policy)

    assert result["passed"] is False
    assert result["hard_floor_applicable"] is False
    assert result["optimization_target_applicable"] is False
    assert result["optimization_target_met"] is False
    assert result["checks"]["reference_comparison_eligible"] is False
    assert "reference_conditions_not_comparable" in result["failure_reasons"]
    assert "reference_hard_floor" not in result["failure_reasons"]
    assert all(
        result["checks"][name]
        for name in (
            "tank_stance_form_presence",
            "tank_dps_recorded",
            "tank_tps_recorded",
            "snap_threat",
            "add_threat",
            "all_hostile_retention",
            "mitigation_coverage",
            "survival",
            "interrupt_coverage",
        )
    )


def test_comparable_tank_reference_keeps_the_numerical_floor():
    policy = load_policy(Path("experiments/configs/all_spec_role_calibration_policy_v3.json"))

    result = evaluate_calibration(_record(compatible=True), policy)

    assert result["passed"] is True
    assert result["hard_floor_applicable"] is True
    assert result["hard_floor_passed"] is True
    assert result["checks"]["reference_comparison_eligible"] is True
