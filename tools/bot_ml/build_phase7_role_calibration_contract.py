"""Build the Phase 7 deterministic role-calibration harness contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .common import write_json
from .live_validation_session import canonical_sha256, sha256_file
from .role_calibration_harness import evaluate_calibration, inject_fault, load_policy


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = REPO_ROOT / "experiments/configs/all_spec_role_calibration_policy_v1.json"
HARNESS = REPO_ROOT / "tools/bot_ml/role_calibration_harness.py"


def _identity(mode: str) -> dict[str, Any]:
    return {
        "target_sha256": canonical_sha256({"mode": mode, "targets": 1 if mode == "single_target_300" else 4}),
        "conditions_sha256": canonical_sha256({
            "mode": mode,
            "buffs": "declared",
            "debuffs": "declared",
            "consumables": "declared",
        }),
        "profile_generation": 7,
        "profile_content_hash": "a" * 64,
        "runtime_authority": "explicit_sql_rule_profiles",
        "generic_ml_runtime_authority": False,
    }


def _window(mode: str) -> dict[str, Any]:
    return {
        "warmup_seconds": 20,
        "warmup_ended_at_ms": 20_000,
        "scored_started_at_ms": 21_000,
        "scored_ended_at_ms": 321_000,
        "scored_duration_seconds": 300,
        "reset_applied": True,
        "reset_id": f"phase7-{mode}-reset-1",
        "cross_window_event_count": 0,
    }


def _damage_metrics(target_count: int) -> dict[str, Any]:
    metrics = {
        "reference_value": 10_000,
        "measured_value": 8_200,
        "active_dps": 8_400,
        "elapsed_dps": 8_200,
        "target_count": target_count,
        "ability_mix": {"primary": 0.55, "secondary": 0.30, "other": 0.15},
        "rotation_group_coverage": 0.9,
        "cast_failure_ratio": 0.01,
        "resource_capped_ratio": 0.05,
        "resource_starved_ratio": 0.05,
        "active_uptime_ratio": 0.96,
        "movement_range_loss_ratio": 0.02,
        "pet_damage_ratio": 0.0,
        "illegal_action_count": 0,
    }
    if target_count == 1:
        metrics.update(
            {
                "scored_damage": 2_460_000,
                "primary_target_guid": 9001,
                "primary_target_damage": 2_460_000,
                "off_target_damage": 0,
                "observed_distinct_damage_targets": 1,
                "isolated_fixture_target": {
                    "isolated_single_target": True,
                    "entry": 44548,
                    "runtime_guid": 9001,
                    "map_id": 0,
                    "x": -9140.0,
                    "y": 520.0,
                    "z": 68.3695,
                    "nearest_other_hostile_clearance": 46.7,
                    "provisioned_at_ms": 500,
                    "provisioned_before_scoring": True,
                    "profile_lane": "ranged",
                    "bot_spawn_x": -9045.0,
                    "bot_spawn_y": 520.0,
                    "bot_spawn_z": 68.0,
                    "bot_target_distance": 15.0,
                    "native_line_of_sight": True,
                    "native_path_reachable": True,
                    "native_dry_land": True,
                    "native_melee_reachable": False,
                    "geometry_validated": True,
                },
            }
        )
    return metrics


def _tank_metrics() -> dict[str, Any]:
    return {
        "reference_value": 7_000,
        "measured_value": 5_600,
        "active_dps": 5_600,
        "threat_per_second": 18_000,
        "target_count": 4,
        "tank_stance_form_presence_active": True,
        "snap_threat_success_ratio": 1.0,
        "add_threat_success_ratio": 1.0,
        "all_hostile_retention_ratio": 0.99,
        "threat_aura_uptime_ratio": 1.0,
        "healer_exposure_ratio": 0.0,
        "mitigation_uptime_ratio": 0.75,
        "defensive_coverage": {"minor": 3, "major": 1},
        "maximum_damage_spike_ratio": 0.30,
        "death_count": 0,
        "health_floor_ratio": 0.35,
        "interrupt_success_ratio": 1.0,
        "illegal_action_count": 0,
    }


def _healer_metrics(required_phases: list[str]) -> dict[str, Any]:
    return {
        "reference_value": 12_000,
        "measured_value": 9_600,
        "effective_hps": 9_600,
        "scheduled_phases": required_phases,
        "delivered_phases": required_phases,
        "scheduled_event_count": 120,
        "delivered_event_count": 120,
        "death_count": 0,
        "health_floor_ratio": 0.38,
        "overheal_ratio": 0.25,
        "absorb_amount": 50_000,
        "remaining_mana_ratio": 0.22,
        "time_to_oom_seconds": 450,
        "response_latency_p95_ms": 900,
        "target_selection_accuracy": 0.96,
        "dispel_success_ratio": 1.0,
        "cooldown_success_ratio": 1.0,
        "idle_ratio_under_demand": 0.03,
        "cast_failure_ratio": 0.01,
        "triage_target_counts": {"tank": 30, "dps_1": 12, "dps_2": 14, "dps_3": 11},
        "illegal_action_count": 0,
    }


def baseline_records(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    required_phases = list(policy["modes"]["healer_controlled_damage_300"]["required_phases"])
    return {
        "single_target_300": {
            "schema": "all_spec_role_calibration_record_v1",
            "mode": "single_target_300",
            "target_spec": "fire_mage",
            "role": "dps",
            "identity": _identity("single_target_300"),
            "window": _window("single_target_300"),
            "metrics": _damage_metrics(1),
        },
        "aoe_300": {
            "schema": "all_spec_role_calibration_record_v1",
            "mode": "aoe_300",
            "role": "dps",
            "identity": _identity("aoe_300"),
            "window": _window("aoe_300"),
            "metrics": _damage_metrics(4),
        },
        "tank_threat_300": {
            "schema": "all_spec_role_calibration_record_v1",
            "mode": "tank_threat_300",
            "role": "tank",
            "identity": _identity("tank_threat_300"),
            "window": _window("tank_threat_300"),
            "metrics": _tank_metrics(),
        },
        "healer_controlled_damage_300": {
            "schema": "all_spec_role_calibration_record_v1",
            "mode": "healer_controlled_damage_300",
            "role": "healer",
            "identity": _identity("healer_controlled_damage_300"),
            "window": _window("healer_controlled_damage_300"),
            "metrics": _healer_metrics(required_phases),
        },
    }


def build_contract(policy_path: Path) -> dict[str, Any]:
    policy = load_policy(policy_path)
    records = baseline_records(policy)
    passing = {
        mode: evaluate_calibration(record, policy)
        for mode, record in records.items()
    }
    fault_sources = {
        "missing_damage_delivery": "healer_controlled_damage_300",
        "duration_mismatch": "single_target_300",
        "one_target_spam": "healer_controlled_damage_300",
        "missed_dispels": "healer_controlled_damage_300",
        "missing_tank_stance": "tank_threat_300",
        "threat_loss": "tank_threat_300",
        "illegal_actions": "aoe_300",
        "cross_window_contamination": "single_target_300",
    }
    faults: dict[str, Any] = {}
    for fault, mode in fault_sources.items():
        mutated = inject_fault(records[mode], fault)
        evaluation = evaluate_calibration(mutated, policy)
        faults[fault] = {
            "source_mode": mode,
            "detected": not evaluation["passed"],
            "failure_reasons": evaluation["failure_reasons"],
            "record_sha256": evaluation["record_sha256"],
        }

    deterministic = all(
        evaluate_calibration(records[mode], policy) == passing[mode]
        for mode in records
    )
    checks = {
        "four_explicit_modes_present": set(records) == {
            "single_target_300",
            "aoe_300",
            "tank_threat_300",
            "healer_controlled_damage_300",
        },
        "all_success_fixtures_pass": all(row["passed"] for row in passing.values()),
        "all_deliberate_faults_detected": all(row["detected"] for row in faults.values()),
        "fixed_300_second_window": policy["scored_window_seconds"] == 300,
        "duration_tolerance_five_seconds": policy["duration_tolerance_seconds"] == 5,
        "separate_warmup_required": policy["minimum_warmup_seconds"] > 0,
        "hard_floor_75_percent": policy["hard_reference_ratio"] == 0.75,
        "optimization_target_80_percent": policy["optimization_reference_ratio"] == 0.8,
        "explicit_rules_authoritative": policy["runtime_authority"] == "explicit_sql_rule_profiles",
        "generic_ml_shadow_only": policy["generic_ml_runtime_authority"] is False,
        "deterministic_recomputation": deterministic,
    }
    contract = {
        "schema": "all_spec_phase7_role_calibration_contract_v1",
        "policy_sha256": sha256_file(policy_path),
        "policy_content_sha256": canonical_sha256(policy),
        "harness_sha256": sha256_file(HARNESS),
        "checks": checks,
        "passing_modes": passing,
        "fault_injection": faults,
        "gate_passed": all(checks.values()),
    }
    contract["contract_sha256"] = canonical_sha256(contract)
    return contract


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/all_spec_phase7_role_calibration_contract"))
    args = parser.parse_args()
    contract = build_contract(args.policy.resolve())
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "contract.json", contract)
    manifest = {
        "schema": "all_spec_phase7_role_calibration_contract_manifest_v1",
        "contract_sha256": contract["contract_sha256"],
        "contract_file_sha256": sha256_file(output_dir / "contract.json"),
        "gate_passed": contract["gate_passed"],
    }
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if contract["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
