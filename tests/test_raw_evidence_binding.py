from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from tools.bot_ml import batch_evidence_lifecycle as lifecycle
from tools.bot_ml.generate_bot_admission_identities import source_content_sha256
from tools.bot_ml.run_live_bot_validation import run_reusable_validation_session


def _report_base() -> dict:
    return {
        "schema": "bot_live_validation_report_v1",
        "returncode": 0,
        "timed_out": False,
        "stages": [{"stage": "focused-test", "missing": []}],
        "failure_labels": [],
        "validation_context": {},
        "evidence": {},
        "validation_route_manifest": {},
        "watchdog_state": {},
        "session": {
            "inactive_after_attempt": True,
            "cleanup": {
                "active": False,
                "active_bots": 0,
                "lease_count": 0,
                "party_bot_count": 0,
                "server_epoch": 77,
            },
        },
    }


def _cleanup_payloads(cohort_id: str = "cohort-a") -> list[dict]:
    return [
        {
            "action": "botauto_calibrate_stop",
            "cohort_id": cohort_id,
            "fixture_target_found": True,
            "fixture_cleanup_submitted_or_absent": True,
        },
        {
            "action": "botauto_status",
            "cohort_id": cohort_id,
            "active": False,
            "active_bots": 0,
            "target_bots": 0,
            "lease_count": 0,
        },
        {
            "action": "botauto_cohorts",
            "server_epoch": 77,
            "cohorts": [
                {
                    "cohort_id": cohort_id,
                    "active": False,
                    "lease_count": 0,
                    "party_bot_count": 0,
                }
            ],
        },
    ]


def _raw_output(payloads: list[dict]) -> str:
    return "".join(f"TC> {json.dumps(payload, sort_keys=True)}\n" for payload in payloads)


def _raw_rows(batch_id: str, payloads: list[dict]) -> list[dict]:
    return [
        {
            "batch_id": batch_id,
            "cohort_id": "cohort-a",
            "attempt_index": 1,
            "sequence": sequence,
            "payload": payload,
        }
        for sequence, payload in enumerate(payloads)
    ]


def _calibration_payload() -> dict:
    return {
        "action": "botauto_calibrate_status",
        "active": True,
        "phase": "complete",
        "mode": "single_target_300",
        "target_spec": "fire_mage",
        "seed": 3,
        "target_guid": 501,
        "window_complete": True,
        "runtime_authority": "explicit_sql_rule_profiles",
        "runtime_mode": "calibration_fixture",
        "non_certifying_assistance": True,
        "generic_ml_runtime_authority": False,
        "reset_applied": True,
        "reset_id": "reset-1",
        "cross_window_event_count": 0,
        "scored_seconds": 300.0,
        "scored_started_at_ms": 1_000,
        "scored_ended_at_ms": 301_000,
        "profile_generation": 8,
        "profile_content_hash": "a" * 64,
        "fixture_target": {
            "isolated_single_target": True,
            "entry": 44548,
            "runtime_guid": 9001,
            "map_id": 0,
            "x": -9060.0,
            "y": 520.0,
            "z": 75.8,
            "nearest_other_hostile_clearance": 46.7,
            "provisioned_at_ms": 500,
            "provisioned_before_scoring": True,
        },
        "previous_window": {
            "mode": "single_target_300",
            "bots": [
                {
                    "guid": 501,
                    "name": "Firemage",
                    "class_id": 8,
                    "role": "dps",
                    "elapsed_seconds": 300.0,
                    "damage": 13_500_000,
                    "pet_damage": 0,
                    "primary_target_guid": 9001,
                    "primary_target_damage": 13_500_000,
                    "off_target_damage": 0,
                    "observed_distinct_damage_targets": 1,
                    "dps": 45_000.0,
                    "target_count": 1,
                    "attempts": 100,
                    "successes": 95,
                    "quality_metrics": {
                        "active_uptime_ratio": 0.9,
                        "cast_failure_ratio": 0.05,
                        "resource_capped_ratio": 0.0,
                        "resource_starved_ratio": 0.0,
                        "movement_range_loss_ratio": 0.0,
                        "pet_damage_ratio": 0.0,
                        "illegal_action_count": 0,
                        "rotation_group_coverage": 1.0,
                    },
                    "result_counts": {"ok": 95, "cast_failed_range": 5},
                    "action_attempts": [
                        {"spell_id": 133, "spell_name": "Fireball", "count": 70},
                        {"spell_id": 11366, "spell_name": "Pyroblast", "count": 30},
                    ],
                    "spell_damage": [
                        {
                            "spell_id": 133,
                            "spell_name": "Fireball",
                            "damage": 9_000_000,
                            "event_count": 70,
                        },
                        {
                            "spell_id": 11366,
                            "spell_name": "Pyroblast",
                            "damage": 4_500_000,
                            "event_count": 25,
                        },
                    ],
                }
            ],
        },
    }


def _attach_role_scoring(report: dict, calibration: dict) -> None:
    record = {
        "schema": "all_spec_role_calibration_record_v1",
        "mode": "single_target_300",
        "role": "dps",
        "identity": {"reference_id": "wowsims-cata-p4-fire-mage"},
        "window": {"scored_duration_seconds": 300.0},
        "metrics": {
            "reference_value": 50_000.0,
            "reference_basis": "pinned_cata_phase4_simulator_dps",
            "measured_value": 45_000.0,
            "elapsed_dps": 45_000.0,
            "active_dps": 50_000.0,
        },
        "raw_runtime_status": copy.deepcopy(calibration),
    }
    report["role_calibration_record"] = record
    report["role_calibration_evaluation"] = {
        "schema": "all_spec_role_calibration_evaluation_v1",
        "reference_ratio": 0.9,
        "hard_floor_passed": True,
        "optimization_target_met": True,
        "record_sha256": lifecycle.canonical_sha256(record),
        "policy_sha256": "d" * 64,
    }


def _calibration_report(calibration: dict) -> dict:
    report = _report_base()
    report.update(
        {
            "calibration_only": True,
            "requested_calibration": {
                "mode": "single_target_300",
                "target_spec": "fire_mage",
                "seed": 3,
            },
            "combat_calibration": calibration,
        }
    )
    _attach_role_scoring(report, calibration)
    return report


def _capture_calibration(tmp_path: Path, report: dict, payloads: list[dict]):
    report["session"]["cleanup"].update(
        {
            "fixture_cleanup_required": True,
            "fixture_cleanup_submitted_or_absent": True,
        }
    )
    output = _raw_output(payloads)
    return lifecycle.capture_batch(
        tmp_path / "batch",
        batch_id="calibration-1",
        raw_rows=_raw_rows("calibration-1", payloads),
        compact_rows=[{"all_passed": True}],
        exact_manifests={},
        summary={"closed": True},
        acceptance_report=report,
        raw_transport_output=output,
        transport_outcome={"returncode": 0, "timed_out": False},
        semantic_evidence_kind="dps_calibration",
    )


def test_calibration_leaf_binds_raw_transport_report_and_parquet(tmp_path: Path):
    calibration = _calibration_payload()
    report = _calibration_report(calibration)
    manifest = _capture_calibration(
        tmp_path, report, [calibration, *_cleanup_payloads()]
    )

    assert manifest["semantic_binding"]["evidence_kind"] == "dps_calibration"
    assert lifecycle.validate_capture(tmp_path / "batch") == manifest
    compact = pq.read_table(tmp_path / "batch/compact/evidence.parquet").to_pylist()
    assert compact[0]["semantic_decisive_projection_sha256"] == manifest[
        "semantic_binding"
    ]["decisive_projection_sha256"]
    assert compact[0]["semantic_transport_returncode"] == 0
    assert compact[0]["semantic_transport_timed_out"] is False
    projection = json.loads(
        (tmp_path / "batch/raw/decisive_projection.json").read_text()
    )
    scoring = projection["decisive"]["selected_target_scoring"]
    assert scoring["damage"] == 13_500_000
    assert scoring["elapsed_dps"] == 45_000.0
    assert scoring["active_seconds"] == 270.0
    assert scoring["active_dps"] == 50_000.0
    assert scoring["reference_ratio"] == 0.9
    assert scoring["hard_floor_passed"] is True
    assert scoring["optimization_target_met"] is True
    assert scoring["result_counts"] == {"cast_failed_range": 5, "ok": 95}
    assert compact[0]["semantic_decisive_projection_sha256"] == lifecycle.canonical_sha256(
        {
            "schema": "bot_acceptance_source_decisive_projection_v1",
            "evidence_kind": "dps_calibration",
            "transport": projection["transport"],
            "decisive": projection["decisive"],
        }
    )


def test_tampered_calibration_report_cannot_disagree_with_raw_fixture_mode(
    tmp_path: Path,
):
    calibration = _calibration_payload()
    report_calibration = copy.deepcopy(calibration)
    report_calibration["runtime_mode"] = "always_on_autonomy"
    report_calibration["non_certifying_assistance"] = False
    report = _calibration_report(report_calibration)

    with pytest.raises(
        lifecycle.BatchLifecycleError,
        match="raw semantic binding failed",
    ):
        _capture_calibration(tmp_path, report, [calibration, *_cleanup_payloads()])


def test_validation_rejects_resigned_report_that_disagrees_with_raw_telemetry(
    tmp_path: Path,
):
    calibration = _calibration_payload()
    report = _calibration_report(calibration)
    manifest = _capture_calibration(
        tmp_path, report, [calibration, *_cleanup_payloads()]
    )
    batch = tmp_path / "batch"
    source_path = batch / "raw/acceptance_source_report.json"
    tampered = json.loads(source_path.read_text())
    tampered["combat_calibration"]["runtime_mode"] = "always_on_autonomy"
    tampered["combat_calibration"]["non_certifying_assistance"] = False
    source_path.write_text(json.dumps(tampered, sort_keys=True) + "\n")

    # Re-sign the ordinary content hashes to prove the semantic verifier is
    # what rejects the forged report, rather than relying on a stale file hash.
    manifest["raw"]["files"] = lifecycle._tree_manifest(batch / "raw")
    manifest["raw"]["bundle_sha256"] = lifecycle._manifest_hash(
        manifest["raw"]["files"]
    )
    manifest.pop("identity_sha256")
    manifest["identity_sha256"] = lifecycle.canonical_sha256(manifest)
    (batch / "retained/final_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n"
    )

    with pytest.raises(
        lifecycle.BatchLifecycleError,
        match="raw semantic binding failed",
    ):
        lifecycle.validate_capture(batch)


def test_claimed_cleanup_requires_raw_stop_status_and_registry_receipt(tmp_path: Path):
    calibration = _calibration_payload()
    report = _calibration_report(calibration)

    with pytest.raises(
        lifecycle.BatchLifecycleError,
        match="raw semantic binding failed",
    ):
        _capture_calibration(tmp_path, report, [calibration])


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        ("damage", 1),
        ("pet_damage", 9_999),
        ("dps", 49_999.0),
        ("elapsed_seconds", 250.0),
        ("attempts", 1),
        ("successes", 1),
        ("result_counts", {"ok": 100}),
        ("action_attempts", []),
        ("spell_damage", []),
    ],
)
def test_report_cannot_mutate_any_selected_target_measurement(
    tmp_path: Path, field: str, tampered_value: object
):
    raw_calibration = _calibration_payload()
    report_calibration = copy.deepcopy(raw_calibration)
    report = _calibration_report(report_calibration)
    report_calibration["previous_window"]["bots"][0][field] = tampered_value

    with pytest.raises(
        lifecycle.BatchLifecycleError,
        match="raw semantic binding failed",
    ):
        _capture_calibration(
            tmp_path, report, [raw_calibration, *_cleanup_payloads()]
        )


def test_inconsistent_server_dps_is_rejected_before_ratio_scoring(tmp_path: Path):
    calibration = _calibration_payload()
    calibration["previous_window"]["bots"][0]["dps"] = 49_999.0
    report = _calibration_report(calibration)

    with pytest.raises(
        lifecycle.BatchLifecycleError,
        match="target DPS does not equal damage / elapsed_seconds",
    ):
        _capture_calibration(
            tmp_path, report, [calibration, *_cleanup_payloads()]
        )


def test_two_decimal_server_dps_rounding_contract_is_deterministic(tmp_path: Path):
    calibration = _calibration_payload()
    target = calibration["previous_window"]["bots"][0]
    target.update(
        {
            "damage": 10,
            "primary_target_damage": 10,
            "elapsed_seconds": 3.0,
            "dps": 3.33,
        }
    )
    report = _report_base()
    report.update(
        {
            "calibration_only": True,
            "requested_calibration": {
                "mode": "single_target_300",
                "target_spec": "fire_mage",
                "seed": 3,
            },
            "combat_calibration": calibration,
            "role_calibration_record": None,
            "role_calibration_evaluation": {
                "reference_ratio": 0.0,
                "hard_floor_passed": False,
                "optimization_target_met": False,
                "record_sha256": None,
                "policy_sha256": None,
            },
        }
    )

    _capture_calibration(tmp_path, report, [calibration, *_cleanup_payloads()])
    projection = json.loads(
        (tmp_path / "batch/raw/decisive_projection.json").read_text()
    )
    scoring = projection["decisive"]["selected_target_scoring"]
    assert scoring["unrounded_damage_over_elapsed_dps"] == pytest.approx(10 / 3)
    assert scoring["elapsed_dps"] == pytest.approx(10 / 3)
    assert scoring["serialized_elapsed_dps"] == 3.33
    assert scoring["exact_elapsed_dps"] == {"numerator": 10, "denominator": 3}
    assert scoring["dps_absolute_error"] < 0.005000001
    assert scoring["dps_arithmetic_contract"] == {
        "formula": "damage / elapsed_seconds",
        "serialized_decimal_places": 2,
        "absolute_tolerance": 0.005000001,
        "validated": True,
    }


def test_serialized_dps_rounding_cannot_promote_exact_ratio_over_85_percent(
    tmp_path: Path,
):
    calibration = _calibration_payload()
    target = calibration["previous_window"]["bots"][0]
    target.update(
        {
            "damage": 13_799_675,
            "primary_target_damage": 13_799_675,
            "elapsed_seconds": 300.0,
            "dps": 45_998.92,
        }
    )
    target["quality_metrics"]["active_uptime_ratio"] = 1.0
    report = _calibration_report(calibration)
    metrics = report["role_calibration_record"]["metrics"]
    metrics.update(
        {
            "reference_value": 54_116.37374,
            "measured_value": 45_998.92,
            "elapsed_dps": 45_998.92,
            "active_dps": 13_799_675 / 300,
        }
    )
    evaluation = report["role_calibration_evaluation"]
    evaluation.update(
        {
            "reference_ratio": 0.85,
            "hard_floor_passed": True,
            # Rounded emitted DPS is above 85%; exact damage/time is below it.
            "optimization_target_met": True,
            "record_sha256": lifecycle.canonical_sha256(
                report["role_calibration_record"]
            ),
        }
    )

    with pytest.raises(
        lifecycle.BatchLifecycleError,
        match="optimization_target_met does not match exact DPS ratio",
    ):
        _capture_calibration(
            tmp_path, report, [calibration, *_cleanup_payloads()]
        )

    evaluation["optimization_target_met"] = False
    _capture_calibration(
        tmp_path / "accepted", report, [calibration, *_cleanup_payloads()]
    )
    projection = json.loads(
        (tmp_path / "accepted/batch/raw/decisive_projection.json").read_text()
    )
    scoring = projection["decisive"]["selected_target_scoring"]
    assert scoring["serialized_elapsed_dps"] == 45_998.92
    assert scoring["elapsed_dps"] == pytest.approx(45_998.916666666664)
    assert scoring["reference_ratio"] == 0.85
    assert scoring["optimization_target_met"] is False
    assert scoring["reference_ratio_arithmetic_contract"][
        "threshold_comparison"
    ] == "exact_rational_before_serialization"


def test_inconsistent_reported_active_dps_is_rejected(tmp_path: Path):
    calibration = _calibration_payload()
    report = _calibration_report(calibration)
    report["role_calibration_record"]["metrics"]["active_dps"] = 49_000.0
    report["role_calibration_evaluation"]["record_sha256"] = lifecycle.canonical_sha256(
        report["role_calibration_record"]
    )

    with pytest.raises(
        lifecycle.BatchLifecycleError,
        match="active_dps does not equal exact damage / elapsed_seconds",
    ):
        _capture_calibration(
            tmp_path, report, [calibration, *_cleanup_payloads()]
        )


def test_report_cannot_mutate_active_uptime_or_reference_scoring(tmp_path: Path):
    raw_calibration = _calibration_payload()
    report_calibration = copy.deepcopy(raw_calibration)
    report = _calibration_report(report_calibration)
    report_calibration["previous_window"]["bots"][0]["quality_metrics"][
        "active_uptime_ratio"
    ] = 0.5
    report["role_calibration_record"]["metrics"]["measured_value"] = 49_000.0
    report["role_calibration_evaluation"]["record_sha256"] = lifecycle.canonical_sha256(
        report["role_calibration_record"]
    )
    report["role_calibration_evaluation"]["reference_ratio"] = 0.98
    report["role_calibration_evaluation"]["hard_floor_passed"] = False
    report["role_calibration_evaluation"]["optimization_target_met"] = False

    with pytest.raises(
        lifecycle.BatchLifecycleError,
        match="raw semantic binding failed",
    ):
        _capture_calibration(
            tmp_path, report, [raw_calibration, *_cleanup_payloads()]
        )


def test_failed_dps_normalization_still_retains_the_raw_measurement(tmp_path: Path):
    calibration = _calibration_payload()
    report = _report_base()
    report.update(
        {
            "calibration_only": True,
            "requested_calibration": {
                "mode": "single_target_300",
                "target_spec": "fire_mage",
                "seed": 3,
            },
            "combat_calibration": calibration,
            "role_calibration_record": None,
            "role_calibration_evaluation": {
                "reference_ratio": 0.0,
                "hard_floor_passed": False,
                "optimization_target_met": False,
                "record_sha256": None,
                "policy_sha256": None,
            },
        }
    )

    manifest = _capture_calibration(
        tmp_path, report, [calibration, *_cleanup_payloads()]
    )
    projection = json.loads(
        (tmp_path / "batch/raw/decisive_projection.json").read_text()
    )
    scoring = projection["decisive"]["selected_target_scoring"]
    assert scoring["damage"] == 13_500_000
    assert scoring["elapsed_dps"] == 45_000.0
    assert scoring["reference_value"] == 0.0
    assert scoring["hard_floor_passed"] is False
    assert manifest["semantic_binding"]["evidence_kind"] == "dps_calibration"


def test_off_target_damage_is_retained_as_failed_fixture_evidence(tmp_path: Path):
    calibration = _calibration_payload()
    target = calibration["previous_window"]["bots"][0]
    target["off_target_damage"] = 250
    target["observed_distinct_damage_targets"] = 2
    target["target_count"] = 2
    report = _report_base()
    report.update(
        {
            "calibration_only": True,
            "requested_calibration": {
                "mode": "single_target_300",
                "target_spec": "fire_mage",
                "seed": 3,
            },
            "combat_calibration": calibration,
            "role_calibration_record": None,
            "role_calibration_evaluation": {
                "reference_ratio": 0.0,
                "hard_floor_passed": False,
                "optimization_target_met": False,
                "record_sha256": None,
                "policy_sha256": None,
            },
        }
    )

    _capture_calibration(tmp_path, report, [calibration, *_cleanup_payloads()])
    projection = json.loads(
        (tmp_path / "batch/raw/decisive_projection.json").read_text()
    )
    evaluation = projection["decisive"]["selected_target_scoring"][
        "isolated_fixture_evaluation"
    ]
    assert evaluation["passed"] is False
    assert "zero_off_target_damage" in evaluation["reasons"]
    assert "one_observed_damage_target" in evaluation["reasons"]
    assert "one_scored_target" in evaluation["reasons"]


def test_unpinned_fixture_coordinates_are_retained_but_fail_evaluation(
    tmp_path: Path,
):
    calibration = _calibration_payload()
    calibration["fixture_target"].update({"x": 123.0, "y": 456.0, "z": -100.0})
    report = _report_base()
    report.update(
        {
            "calibration_only": True,
            "requested_calibration": {
                "mode": "single_target_300",
                "target_spec": "fire_mage",
                "seed": 3,
            },
            "combat_calibration": calibration,
            "role_calibration_record": None,
            "role_calibration_evaluation": {
                "reference_ratio": 0.0,
                "hard_floor_passed": False,
                "optimization_target_met": False,
                "record_sha256": None,
                "policy_sha256": None,
            },
        }
    )

    _capture_calibration(tmp_path, report, [calibration, *_cleanup_payloads()])
    projection = json.loads(
        (tmp_path / "batch/raw/decisive_projection.json").read_text()
    )
    evaluation = projection["decisive"]["selected_target_scoring"][
        "isolated_fixture_evaluation"
    ]
    assert evaluation["passed"] is False
    assert set(evaluation["reasons"]) >= {
        "fixture_x_pinned",
        "fixture_y_pinned",
        "fixture_z_bounded",
    }


def test_false_fixture_cleanup_receipt_rejects_calibration_capture(
    tmp_path: Path,
):
    calibration = _calibration_payload()
    report = _calibration_report(calibration)
    cleanup = _cleanup_payloads()
    cleanup[0]["fixture_cleanup_submitted_or_absent"] = False

    with pytest.raises(
        lifecycle.BatchLifecycleError,
        match="acceptance source report decisive facts do not match raw telemetry",
    ):
        _capture_calibration(tmp_path, report, [calibration, *cleanup])


def test_reusable_session_returns_output_only_after_cleanup_telemetry_is_appended():
    source = inspect.getsource(run_reusable_validation_session)
    assert source.count('return "".join(output_parts)') == 1
    assert 'executor.calibration("stop")' in source
    assert '"fixture_cleanup_submitted_or_absent"' in source
    assert source.index('executor.calibration("stop")') < source.rindex(
        "executor.stop()"
    )
    assert source.index('write_json(args.output_dir / "session.json", lifecycle)') < source.index(
        'return "".join(output_parts)'
    )


def _stonecore_manifest() -> dict:
    return {
        "schema": "bot_live_validation_route_manifest_v1",
        "scenario_id": "stonecore_5h",
        "routes": [
            {
                "route_node_id": "trash-1",
                "route_generation": 1,
                "kind": "trash",
            },
            {
                "route_node_id": "boss-1",
                "route_generation": 2,
                "kind": "boss",
            },
        ],
    }


def _admission_status() -> dict:
    specs = [
        "protection_paladin",
        "restoration_shaman",
        "fire_mage",
        "combat_rogue",
        "survival_hunter",
    ]
    slots = [
        "party_tank_1",
        "party_healer_1",
        "party_dps_1",
        "party_dps_2",
        "party_dps_3",
    ]
    roles = ["tank", "healer", "dps", "dps", "dps"]
    members = []
    for guid, (slot, role, spec) in enumerate(zip(slots, roles, specs), 1001):
        gear_manifest = [
            {
                "slot": equipment_slot,
                "item_id": 60_000 + (guid * 20) + equipment_slot,
                "enchant_id": 0,
                "reforge_id": 0,
                "gem_item_ids": [],
            }
            for equipment_slot in range(16)
        ]
        gear_manifest_sha256 = lifecycle.canonical_sha256(gear_manifest)
        members.append(
            {
                "guid": guid,
                "roster_slot_id": slot,
                "role": role,
                "class_spec": spec,
                "class_id": 2 if role == "tank" else 7 if role == "healer" else 8,
                "active_spec_index": 0,
                "primary_talent_tree_id": 839 if role == "tank" else 262 if role == "healer" else 851,
                "active_talent_count": 1,
                "active_talent_spell_ids": [20_000 + guid],
                "gear_profile_id": spec,
                "gear_item_count": len(gear_manifest),
                "gear_manifest": gear_manifest,
                "gear_manifest_sha256": gear_manifest_sha256,
                "current_gear_manifest_sha256": gear_manifest_sha256,
                "gear_identity_current_matches_admission": True,
                "group_guid": 901,
                "leader_guid": 1001,
                "map_id": 725,
                "instance_id": 902,
                "expected_difficulty": 1,
                "player_difficulty": 1,
                "map_difficulty": 1,
                "spawn_x": 1152.4,
                "spawn_y": 878.1,
                "spawn_z": 284.9,
                "server_provisioned": True,
                "initial_baseline_normalized": True,
                "initial_alive_state_verified": True,
            }
        )
    return {
        "action": "botauto_status",
        "cohort_id": "cohort-a",
        "active": True,
        "active_bots": 5,
        "target_bots": 5,
        "bots": 5,
        "lease_count": 5,
        "attempt_id": 9,
        "profile_generation": 4,
        "profile_content_hash": "b" * 64,
        "pool_tag_filter": "stonecore-phase9",
        "exact_party_class_specs": specs,
        "raid_runtime": {
            "admission_phase": "active",
            "server_provisioning_complete": True,
            "bot_actions_enabled": True,
            "difficulty_matches": True,
            "expected_difficulty": 1,
            "group_difficulty": 1,
            "map_difficulty": 1,
            "expected_size": 5,
            "group_guid": 901,
            "leader_guid": 1001,
            "instance_id": 902,
            "admission_receipt": {
                "attempt_id": 9,
                "scenario_id": "stonecore_5h",
                "runtime_profile": "stonecore_5h",
                "identity_catalog_source_sha256": source_content_sha256(),
                "profile_generation": 4,
                "profile_content_hash": "b" * 64,
                "route_manifest_sha256": "c" * 64,
                "entrance_map_id": 725,
                "entrance_x": 1152.4,
                "entrance_y": 878.1,
                "entrance_z": 284.9,
                "recovery_entrance_area_trigger_id": 6196,
                "recovery_entrance_source_map_id": 646,
                "recovery_entrance_target_map_id": 725,
                "bot_actions_enabled_at_commit": True,
                "all_current_gear_matches_admission": True,
                "members": members,
            },
        },
    }


def _stonecore_report(admission: dict, manifest: dict) -> dict:
    report = _report_base()
    report["validation_context"] = {"scenario_id": "stonecore_5h"}
    report["validation_route_manifest"] = manifest
    report["evidence"] = {
        "route_terminal_evidence": [
            {"route_node_id": "trash-1", "route_generation": 1},
            {"route_node_id": "boss-1", "route_generation": 2},
        ],
        "real_boss_kill_evidence": [
            {"route_node_id": "boss-1", "route_generation": 2}
        ],
        "manifest_completion_evidence": [
            {"route_node_id": "boss-1", "route_generation": 2}
        ],
        "forbidden_completion_assists": [],
    }
    report["session"].update(
        {
            "admission_status": admission,
            "heroic_admission_verified": True,
            "exact_party_verified": True,
        }
    )
    return report


def test_stonecore_leaf_reconstructs_route_boss_admission_and_no_assist(
    tmp_path: Path,
):
    manifest = _stonecore_manifest()
    admission = _admission_status()
    payloads = [
        admission,
        {
            "trace_schema_version": 1,
            "entries": [
                {
                    "action": "validation_route_terminal",
                    "route_node_id": "trash-1",
                    "route_generation": 1,
                },
                {
                    "action": "boss_killed",
                    "result": "confirmed_unit_death",
                    "target_id": 43438,
                    "route_node_id": "boss-1",
                    "route_generation": 2,
                },
                {
                    "action": "validation_route_terminal",
                    "route_node_id": "boss-1",
                    "route_generation": 2,
                },
                {
                    "action": "validation_route_manifest_complete",
                    "route_node_id": "boss-1",
                    "route_generation": 2,
                },
            ],
        },
        *_cleanup_payloads(),
    ]
    report = _stonecore_report(admission, manifest)
    output = _raw_output(payloads)
    captured = lifecycle.capture_batch(
        tmp_path / "stonecore",
        batch_id="stonecore-1",
        raw_rows=_raw_rows("stonecore-1", payloads),
        compact_rows=[{"all_passed": True}],
        exact_manifests={"validation_route_manifest": manifest},
        summary={"closed": True},
        acceptance_report=report,
        raw_transport_output=output,
        transport_outcome={"returncode": 0, "timed_out": False},
        semantic_evidence_kind="stonecore_5h",
    )

    assert lifecycle.validate_capture(tmp_path / "stonecore") == captured
    projection = json.loads(
        (tmp_path / "stonecore/raw/decisive_projection.json").read_text()
    )
    decisive = projection["decisive"]
    assert decisive["missing_terminal_route_nodes"] == []
    assert decisive["missing_boss_route_nodes"] == []
    assert decisive["forbidden_completion_assists"] == []
    assert decisive["heroic_admission_verified"] is True
    assert decisive["cleanup"]["inactive_after_attempt"] is True


def test_stonecore_report_cannot_invent_a_boss_death(tmp_path: Path):
    manifest = _stonecore_manifest()
    admission = _admission_status()
    payloads = [
        admission,
        {
            "trace_schema_version": 1,
            "entries": [
                {
                    "action": "validation_route_terminal",
                    "route_node_id": "trash-1",
                    "route_generation": 1,
                }
            ],
        },
        *_cleanup_payloads(),
    ]
    report = _stonecore_report(admission, manifest)

    with pytest.raises(
        lifecycle.BatchLifecycleError,
        match="acceptance source report decisive facts do not match raw telemetry",
    ):
        lifecycle.capture_batch(
            tmp_path / "stonecore",
            batch_id="stonecore-1",
            raw_rows=_raw_rows("stonecore-1", payloads),
            compact_rows=[{"all_passed": True}],
            exact_manifests={"validation_route_manifest": manifest},
            summary={"closed": True},
            acceptance_report=report,
            raw_transport_output=_raw_output(payloads),
            transport_outcome={"returncode": 0, "timed_out": False},
            semantic_evidence_kind="stonecore_5h",
        )


def test_stonecore_raw_binding_rejects_post_admission_gear_drift(
    tmp_path: Path,
) -> None:
    manifest = _stonecore_manifest()
    admission = _admission_status()
    drifted = copy.deepcopy(admission)
    drifted["raid_runtime"]["admission_phase"] = "terminal"
    drifted["raid_runtime"]["server_provisioning_complete"] = False
    drifted["raid_runtime"]["bot_actions_enabled"] = False
    drifted_receipt = drifted["raid_runtime"]["admission_receipt"]
    drifted_receipt["all_current_gear_matches_admission"] = False
    drifted_member = drifted_receipt["members"][0]
    drifted_member["current_gear_manifest_sha256"] = "f" * 64
    drifted_member["gear_identity_current_matches_admission"] = False
    payloads = [admission, drifted, *_cleanup_payloads()]
    report = _stonecore_report(admission, manifest)

    with pytest.raises(
        lifecycle.BatchLifecycleError,
        match="acceptance source report decisive facts do not match raw telemetry",
    ):
        lifecycle.capture_batch(
            tmp_path / "stonecore-drift",
            batch_id="stonecore-drift-1",
            raw_rows=_raw_rows("stonecore-drift-1", payloads),
            compact_rows=[{"all_passed": True}],
            exact_manifests={"validation_route_manifest": manifest},
            summary={"closed": True},
            acceptance_report=report,
            raw_transport_output=_raw_output(payloads),
            transport_outcome={"returncode": 0, "timed_out": False},
            semantic_evidence_kind="stonecore_5h",
        )
