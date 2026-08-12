"""Independently verify raw synthetic Phase 1 generic-mechanic evidence.

The verifier intentionally does not consume the compact report, any stored
``passed`` field, or a stored gate field.  It reconstructs the fixture adapter,
frozen provisioning identity, foundation assignments, and deterministic state
outcomes from the raw evidence envelope.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import json
from math import dist, isfinite
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.raid.foundation import (  # noqa: E402
    RaidMember,
    compile_mechanic_contract,
    form_raid,
    formation_points,
    generic_assignment_smoke,
    validate_evidence_demultiplex,
)
from tools.raid_program.capture_phase1_raid_foundation import (  # noqa: E402
    _expected_identity_by_slot,
    _provisioned_bwd_10n_bots,
    expected_bwd_10n_roster,
)


DEFAULT_CONFIG = ROOT / "experiments/configs/cata_raid_phase1_generic_mechanic_smoke_v1.json"
DEFAULT_RAW = Path("phase1_generic_mechanic_smoke.raw.json")
GROUP_GUID = 77
LEADER_GUID = 1001
INSTANCE_ID = 42
LOCKOUT_SAVE_ID = 42
SERVER_EPOCH = 88
ATTEMPT_ID = 1
MAP_ID = 669
DIFFICULTY = "10n"
TARGET_CONTROL_MAP = {
    "focus_fire": "focus_fire",
    "multidot": "multidot",
    "do_not_damage": "do_not_damage",
    "controlled_aoe": "controlled_aoe",
    "kill_sync": "kill_synchronization",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _commit_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _load_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fixture_not_object")
    if payload.get("schema") != "cata_raid_generic_mechanic_smoke_v1":
        raise ValueError("fixture_schema_mismatch")
    if payload.get("authority") != "synthetic_test_only_not_boss_fidelity":
        raise ValueError("fixture_authority_mismatch")
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError("fixture_routes_missing")
    return payload


def _contract_payload(route: dict[str, Any]) -> dict[str, Any]:
    source = route.get("mechanic_contract")
    if not isinstance(source, dict):
        raise ValueError(f"route_contract_missing:{route.get('route_node_id', '')}")
    formation = str(source.get("formation_family") or "")
    target_control = str(source.get("target_control") or "")
    distance = source.get("spacing_yards", source.get("radius_yards"))
    if not formation or target_control not in TARGET_CONTROL_MAP:
        raise ValueError(f"route_contract_shape_invalid:{route.get('route_node_id', '')}")
    if source.get("formation_anchor") != "route_anchor" or source.get("formation_orientation") != "route":
        raise ValueError(f"route_formation_metadata_invalid:{route.get('route_node_id', '')}")
    if not isinstance(distance, (int, float)) or isinstance(distance, bool) or distance <= 0:
        raise ValueError(f"route_geometry_missing:{route.get('route_node_id', '')}")
    if not isinstance(source.get("allow_area_damage"), bool):
        raise ValueError(f"route_area_damage_invalid:{route.get('route_node_id', '')}")
    return {
        "strategy_id": str(source.get("id") or route.get("route_node_id") or ""),
        "formation": formation,
        "anchor_scope": "raid",
        "minimum_distance": float(distance),
        "target_control": TARGET_CONTROL_MAP[target_control],
    }


def _roster() -> tuple[dict[str, Any], ...]:
    slots = expected_bwd_10n_roster()
    expected = _expected_identity_by_slot()
    bots = _provisioned_bwd_10n_bots()
    if len(slots) != 10 or len(bots) != 10:
        raise ValueError("frozen_bwd_roster_size_mismatch")
    rows: list[dict[str, Any]] = []
    role_counts: Counter[str] = Counter()
    for index, (bot, slot_info) in enumerate(zip(bots, slots, strict=True)):
        slot_id, role, class_id, class_spec = slot_info
        role_counts[role] += 1
        identity = expected[slot_id]
        gear = [
            {
                "slot": item["slot"],
                "entry": item["entry"],
                "enchant_id": item["enchant_id"],
                "gem_item_ids": list(item["gem_item_ids"]),
                "reforge_id": item["reforge_id"],
            }
            for item in identity["gear"]
        ]
        row = {
            "roster_slot_id": slot_id,
            "lease_role_slot": slot_id,
            "guid": LEADER_GUID + index,
            "role": role,
            "class_id": class_id,
            "class_spec": class_spec,
            "account": str(bot.get("account") or "").upper(),
            "name": str(bot.get("name") or ""),
            "talents": list(identity["talents"]),
            "glyphs": list(identity["glyphs"]),
            "gear_manifest": gear,
            "slot": index,
            "subgroup": index // 5,
            "active": True,
            "lease_owned": True,
        }
        if (
            identity["role"] != role
            or identity["class_id"] != class_id
            or identity["class_spec"] != class_spec
            or identity["account"] != row["account"]
            or identity["name"] != row["name"]
        ):
            raise ValueError(f"frozen_member_identity_mismatch:{slot_id}")
        rows.append(row)
    if role_counts != Counter({"tank": 2, "healer": 3, "dps": 5}):
        raise ValueError("frozen_bwd_roster_composition_mismatch")
    return tuple(rows)


def _foundation(roster: tuple[dict[str, Any], ...]):
    return form_raid(
        [
            RaidMember(
                row["guid"],
                row["role"],
                roster_slot_id=row["roster_slot_id"],
                active=row["active"],
                lease_owned=row["lease_owned"],
            )
            for row in roster
        ],
        difficulty=DIFFICULTY,
        group_guid=GROUP_GUID,
        leader_guid=LEADER_GUID,
        map_id=MAP_ID,
        instance_id=INSTANCE_ID,
        lockout_save_id=LOCKOUT_SAVE_ID,
        server_epoch=SERVER_EPOCH,
        attempt_id=ATTEMPT_ID,
        strategy_id="blackwing_descent_10n",
    )


def _identity(foundation: Any) -> dict[str, Any]:
    return {
        "group_guid": foundation.identity.group_guid,
        "leader_guid": foundation.identity.leader_guid,
        "raid_size": foundation.identity.raid_size,
        "difficulty_name": foundation.identity.difficulty_name,
        "difficulty_id": foundation.identity.difficulty_id,
        "map_id": foundation.identity.map_id,
        "instance_id": foundation.identity.instance_id,
        "lockout_save_id": foundation.identity.lockout_save_id,
        "server_epoch": foundation.identity.server_epoch,
        "attempt_id": foundation.identity.attempt_id,
        "strategy_id": foundation.identity.strategy_id,
    }


def _normalize_events(events: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            **event,
            "formation_point": tuple(event["formation_point"]),
        }
        for event in events
    )


def _expected_outcomes(route: dict[str, Any], assignments: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    """Independent duplicate of the deterministic fixture state machine."""

    source = route["mechanic_contract"]
    target_control = TARGET_CONTROL_MAP[source["target_control"]]
    sequence = max(event["evidence_sequence"] for event in assignments) + 1
    expected: list[dict[str, Any]] = []

    def add(kind: str, state: str, **fields: Any) -> None:
        nonlocal sequence
        expected.append({
            "evidence_sequence": sequence,
            "route_node_id": route["route_node_id"],
            "kind": kind,
            "state": state,
            "target_control": target_control,
            **fields,
        })
        sequence += 1

    add("state_transition", "ready", accepted=True)
    add("state_transition", "assigned", accepted=True, assignment_generation=assignments[0]["assignment_generation"], member_count=10)
    targets = [int(value) for value in source["target_entries"]]
    if target_control == "do_not_damage":
        add("outcome", "target_hold", case="do_not_damage_hold", target_entry=targets[0], damage_allowed=False, decision="hold", accepted=True)
        add("counterexample", "target_hold", case="do_not_damage_wrong_target", target_entry=max(targets) + 1, damage_allowed=True, decision="reject", accepted=False, reason="undeclared_target_damage_rejected")
    elif target_control == "focus_fire":
        add("outcome", "focus_authority", case="focus_authority", focus_target_entry=targets[0], attacker_target_entry=targets[0], damage_allowed=True, decision="attack", accepted=True)
        add("counterexample", "focus_authority", case="focus_wrong_attacker_target", focus_target_entry=targets[0], attacker_target_entry=max(targets) + 1, damage_allowed=True, decision="reject", accepted=False, reason="focus_authority_rejected_wrong_target")
    elif target_control == "controlled_aoe":
        minimum = int(source["controlled_aoe_minimum_targets"])
        add("outcome", "controlled_aoe_threshold_closed", case="controlled_aoe_threshold_below", declared_target_entries=targets, observed_declared_targets=minimum - 1, minimum_targets=minimum, area_damage_allowed=False, decision="hold", accepted=True)
        add("outcome", "controlled_aoe_threshold_open", case="controlled_aoe_threshold_met", declared_target_entries=targets, observed_declared_targets=minimum, minimum_targets=minimum, area_damage_allowed=True, decision="release", accepted=True)
        add("counterexample", "controlled_aoe_fail_closed", case="controlled_aoe_undeclared_hostile", declared_target_entries=targets, undeclared_hostile_entry=max(targets) + 1, observed_declared_targets=minimum, minimum_targets=minimum, area_damage_allowed=False, decision="fail_close", accepted=False, reason="undeclared_hostile_fail_closed")
    elif target_control == "kill_synchronization":
        floor = float(source["kill_sync_execution_floor_pct"])
        tolerance = float(source["kill_sync_tolerance_pct"])
        alternate = [int(value) for value in route["alternate_target_entries"]]
        add("outcome", "kill_sync_selection", case="kill_sync_selection", selected_target_entries=targets, alternate_target_entries=alternate, accepted=True)
        add("outcome", "kill_sync_hold", case="kill_sync_hold", lowest_health_pct=floor, peer_health_pct=floor + tolerance, execution_floor_pct=floor, decision="hold_low_target", accepted=True)
        add("outcome", "kill_sync_release", case="kill_sync_release", lowest_health_pct=floor, peer_health_pct=floor, execution_floor_pct=floor, decision="release", accepted=True)
        add("counterexample", "kill_sync_hold", case="kill_sync_release_peer_above_floor", lowest_health_pct=floor, peer_health_pct=floor + tolerance, execution_floor_pct=floor, decision="hold", accepted=False, reason="kill_sync_release_rejected_peer_above_floor")
    else:
        raise ValueError(f"synthetic_target_control_unhandled:{target_control}")
    if "soak_roster_slots" in source:
        slots = [int(value) for value in source["soak_roster_slots"]]
        radius = float(source["soak_radius_yards"])
        minimum = int(source["soak_minimum_count"])
        add("outcome", "soak_valid", case="soak_membership_radius_count", soak_roster_slots=slots, soak_radius_yards=radius, observed_count=len(slots), minimum_count=minimum, members_in_radius=True, accepted=True)
        add("counterexample", "soak_rejected", case="soak_out_of_radius", soak_roster_slots=slots[:-1], soak_radius_yards=radius, observed_count=len(slots) - 1, minimum_count=minimum, members_in_radius=False, accepted=False, reason="soak_membership_radius_or_count_rejected")
    if "dispel_owner_slot" in source:
        aura = int(source["dispel_aura_id"])
        owner = int(source["dispel_owner_slot"])
        backup = int(source["dispel_backup_slot"])
        add("outcome", "dispel_primary", case="dispel_owner_then_backup", aura_id=aura, owner_slot=owner, backup_slot=backup, selected_slot=owner, owner_available=True, accepted=True)
        add("outcome", "dispel_backup", case="dispel_owner_then_backup", aura_id=aura, owner_slot=owner, backup_slot=backup, selected_slot=backup, owner_available=False, accepted=True)
        add("counterexample", "dispel_rejected", case="dispel_unknown_owner", aura_id=aura, owner_slot=owner, backup_slot=backup, selected_slot=backup + 1, owner_available=False, accepted=False, reason="dispel_owner_or_backup_rejected")
    if "cooldown_owner_slot" in source:
        category = str(source["cooldown_category"])
        trigger = int(source["cooldown_trigger_spell_id"])
        owner = int(source["cooldown_owner_slot"])
        add("outcome", "cooldown_triggered", case="cooldown_trigger_owner", category=category, trigger_spell_id=trigger, owner_slot=owner, triggered=True, accepted=True)
        add("counterexample", "cooldown_rejected", case="cooldown_wrong_trigger_or_owner", category=category, trigger_spell_id=trigger + 1, owner_slot=owner + 1, triggered=False, accepted=False, reason="cooldown_trigger_or_owner_rejected")
    add("state_transition", "complete", accepted=True, undeclared_primitives_exercised=[])
    return expected


def _failures_for_raw(config_path: Path, raw: dict[str, Any]) -> list[str]:
    fixture = _load_fixture(config_path)
    roster = _roster()
    foundation = _foundation(roster)
    failures: list[str] = []
    if raw.get("schema") != "cata_raid_phase1_generic_mechanic_smoke_raw_v1":
        failures.append("raw_schema")
    if raw.get("authority") != fixture["authority"]:
        failures.append("raw_authority")
    if raw.get("fixture_schema") != fixture["schema"] or raw.get("scenario_id") != fixture["scenario_id"]:
        failures.append("raw_fixture_identity")
    provenance = raw.get("provenance")
    if not isinstance(provenance, dict):
        failures.append("raw_provenance_missing")
        provenance = {}
    expected_fixture_sha = _sha256_file(config_path)
    if provenance.get("fixture_sha256") != expected_fixture_sha:
        failures.append("fixture_sha256")
    runner_path = ROOT / "tools/raid_program/run_phase1_generic_mechanic_smoke.py"
    if provenance.get("runner_sha256") != _sha256_file(runner_path):
        failures.append("runner_sha256")
    if provenance.get("commit_sha") != _commit_sha():
        failures.append("commit_sha")
    if raw.get("identity") != _identity(foundation):
        failures.append("foundation_identity")
    expected_roster = list(roster)
    if raw.get("roster") != expected_roster:
        failures.append("exact_member_identity")
    if provenance.get("roster_sha256") != _canonical_sha256(expected_roster):
        failures.append("roster_sha256")
    if provenance.get("provisioning_sha256") != _canonical_sha256(_provisioned_bwd_10n_bots()):
        failures.append("provisioning_sha256")
    routes = raw.get("routes")
    if not isinstance(routes, list):
        failures.append("raw_routes_missing")
        return failures
    fixture_by_id = {route["route_node_id"]: route for route in fixture["routes"]}
    if len(routes) != len(fixture_by_id) or {row.get("route_node_id") for row in routes} != set(fixture_by_id):
        failures.append("raw_route_identity")
    for raw_route in routes:
        route_id = raw_route.get("route_node_id")
        route = fixture_by_id.get(route_id)
        if route is None:
            continue
        try:
            expected_contract = compile_mechanic_contract(_contract_payload(route), allow_undeclared=True)
            generation = fixture["routes"].index(route) + 1
            assignments = raw_route.get("assignment_events")
            if raw_route.get("contract_id") != expected_contract.strategy_id or raw_route.get("assignment_generation") != generation:
                raise ValueError("route_contract_or_generation")
            if not isinstance(assignments, list) or len(assignments) != 10:
                raise ValueError("assignment_event_count")
            normalized = _normalize_events(assignments)
            expected_assignments = generic_assignment_smoke(foundation, expected_contract, assignment_generation=generation)
            if normalized != expected_assignments:
                raise ValueError("assignment_events_recomputed_mismatch")
            validate_evidence_demultiplex(
                normalized,
                replace(foundation.identity, strategy_id=expected_contract.strategy_id),
                foundation.members,
            )
            outcomes = raw_route.get("outcome_events")
            if not isinstance(outcomes, list) or outcomes != _expected_outcomes(route, normalized):
                raise ValueError("outcome_events_recomputed_mismatch")
            if any(outcome.get("route_node_id") != route_id for outcome in outcomes):
                raise ValueError("outcome_route_identity")
        except (KeyError, TypeError, ValueError) as error:
            failures.append(f"{route_id}:{error}")
    return failures


def verify_raw_evidence(
    config_path: Path = DEFAULT_CONFIG,
    raw_evidence: Path | dict[str, Any] = DEFAULT_RAW,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    if isinstance(raw_evidence, Path):
        raw_path = raw_evidence.resolve()
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        raw_bytes_sha256 = _sha256_file(raw_path)
        raw_path_value: str | None = str(raw_path)
    else:
        raw = raw_evidence
        raw_bytes_sha256 = hashlib.sha256(_canonical_bytes(raw) + b"\n").hexdigest()
        raw_path_value = None
    failures = _failures_for_raw(config_path, raw)
    return {
        "schema": "cata_raid_phase1_generic_mechanic_smoke_verification_v1",
        "authority": "synthetic_test_only_not_boss_fidelity",
        "synthetic_test_only": True,
        "canonical_live_capture_replacement": False,
        "fixture_sha256": _sha256_file(config_path),
        "raw_evidence_sha256": raw_bytes_sha256,
        "raw_evidence_path": raw_path_value,
        "failures": failures,
        "verification_gate_passed": not failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = verify_raw_evidence(args.config, args.raw)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        report = {
            "schema": "cata_raid_phase1_generic_mechanic_smoke_verification_v1",
            "authority": "synthetic_test_only_not_boss_fidelity",
            "synthetic_test_only": True,
            "canonical_live_capture_replacement": False,
            "failures": [str(error)],
            "verification_gate_passed": False,
        }
    if args.output:
        output = args.output.resolve()
        if output.exists():
            raise SystemExit("output already exists; verification reports are immutable")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as handle:
            handle.write(_canonical_bytes(report) + b"\n")
    print(json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0 if report["verification_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
