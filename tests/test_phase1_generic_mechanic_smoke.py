import json
from pathlib import Path

from tools.raid_program.run_phase1_generic_mechanic_smoke import (
    build_raw_evidence,
    run_smoke,
)
from tools.raid_program.verify_phase1_generic_mechanic_smoke import verify_raw_evidence


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "experiments/configs/cata_raid_phase1_generic_mechanic_smoke_v1.json"


def test_generic_smoke_executes_every_fixture_contract_and_reconstructs_identity():
    report = run_smoke(FIXTURE)

    assert report["gate_passed"] is True
    assert report["independent_verification"]["verification_gate_passed"] is True
    assert report["synthetic_test_only"] is True
    assert report["canonical_live_capture_replacement"] is False
    assert report["foundation"]["composition"] == {"tank": 2, "healer": 3, "dps": 5}
    assert report["foundation"]["member_count"] == 10
    assert [row["route_node_id"] for row in report["routes"]] == [
        "pair_damage_hold",
        "lane_controlled_aoe",
        "quadrant_kill_sync",
        "ring_native_actions",
        "cone_soak_rotation",
    ]
    assert all(row["passed"] for row in report["routes"])
    assert all(len(row["per_member"]) == 10 for row in report["routes"])
    assert all(
        member["identity_ok"]
        and member["assignment_generation"] == route["assignment_generation"]
        and member["geometry_ok"]
        and member["target_control_ok"]
        and member["rotation_ok"]
        and member["interaction_ok"]
        for route in report["routes"]
        for member in route["per_member"]
    )


def test_generic_smoke_reconstructs_route_specific_target_and_rotation_fields():
    report = run_smoke(FIXTURE)
    by_route = {row["route_node_id"]: row for row in report["routes"]}

    assert by_route["lane_controlled_aoe"]["source_specific"] == {
        "allow_area_damage": True,
        "controlled_aoe_minimum_targets": 3,
        "controlled_aoe_ok": True,
        "target_entries": [1, 2, 3],
    }
    assert by_route["quadrant_kill_sync"]["source_specific"] == {
        "allow_area_damage": False,
        "alternate_target_entries": [1, 2],
        "kill_sync_ok": True,
        "target_entries": [1, 2],
    }
    assert by_route["cone_soak_rotation"]["source_specific"] == {
        "allow_area_damage": False,
        "cooldown_ok": True,
        "dispel_ok": True,
        "soak_ok": True,
        "target_entries": [1],
    }
    assert all(
        row["interaction"] == {
            "declared_fields": [],
            "not_exercised": [
                "interaction_kind",
                "movement_link",
                "platform_policy",
                "recovery_policy",
            ],
            "ok": True,
        }
        for row in report["routes"]
    )


def test_generic_smoke_fails_closed_on_fixture_contract_corruption(tmp_path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["routes"][0]["mechanic_contract"]["target_control"] = "not_a_target_control"
    corrupted = tmp_path / "corrupted.json"
    corrupted.write_text(json.dumps(fixture), encoding="utf-8")

    report = run_smoke(corrupted)

    assert report["gate_passed"] is False
    assert report["routes"][0]["passed"] is False
    assert "route_target_control_unknown" in report["failures"][0]


def test_raw_evidence_and_independent_verifier_cover_outcomes_and_exact_identity(tmp_path):
    raw = build_raw_evidence(FIXTURE)
    raw_path = tmp_path / "phase1.raw.json"
    raw_path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")

    verification = verify_raw_evidence(FIXTURE, raw_path)

    assert verification["verification_gate_passed"] is True
    assert len(raw["roster"]) == 10
    assert all(
        {"roster_slot_id", "role", "class_id", "class_spec", "account", "name", "talents", "glyphs", "gear_manifest"}
        <= row.keys()
        for row in raw["roster"]
    )
    outcomes = [event for route in raw["routes"] for event in route["outcome_events"]]
    cases = {event["case"] for event in outcomes if "case" in event}
    assert {
        "do_not_damage_hold",
        "focus_authority",
        "controlled_aoe_threshold_below",
        "controlled_aoe_threshold_met",
        "controlled_aoe_undeclared_hostile",
        "kill_sync_selection",
        "kill_sync_hold",
        "kill_sync_release",
        "kill_sync_release_peer_above_floor",
        "soak_membership_radius_count",
        "soak_out_of_radius",
        "dispel_owner_then_backup",
        "dispel_unknown_owner",
        "cooldown_trigger_owner",
        "cooldown_wrong_trigger_or_owner",
    } <= cases
    assert all(
        event["kind"] == "counterexample" and event["accepted"] is False
        for event in outcomes
        if event["kind"] == "counterexample"
    )


def test_independent_verifier_rejects_tampered_raw_event_even_if_pass_fields_are_true(tmp_path):
    raw = build_raw_evidence(FIXTURE)
    raw["routes"][0]["assignment_events"][0]["member_guid"] = 1010
    raw["routes"][0]["assignment_events"][0]["passed"] = True
    raw_path = tmp_path / "tampered.raw.json"
    raw_path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")

    verification = verify_raw_evidence(FIXTURE, raw_path)

    assert verification["verification_gate_passed"] is False
    assert any("assignment_events_recomputed_mismatch" in reason for reason in verification["failures"])


def test_run_gate_consumes_independent_outcome_verification(monkeypatch):
    monkeypatch.setattr(
        "tools.raid_program.run_phase1_generic_mechanic_smoke._synthetic_outcome_events",
        lambda route, assignments: [{"kind": "outcome", "state": "bogus", "accepted": True}],
    )
    report = run_smoke(FIXTURE)
    assert report["gate_passed"] is False
    assert report["independent_verification"]["verification_gate_passed"] is False
    assert any("outcome_events_recomputed_mismatch" in reason for reason in report["failures"])


def test_immutable_raw_output_guard_rejects_reuse(tmp_path):
    raw_path = tmp_path / "immutable.raw.json"
    run_smoke(FIXTURE, raw_output=raw_path)
    assert raw_path.is_file()

    try:
        run_smoke(FIXTURE, raw_output=raw_path)
    except ValueError as error:
        assert "immutable_output_exists" in str(error)
    else:
        raise AssertionError("raw output reuse was not rejected")
