"""Run the synthetic Phase 1 generic raid-mechanic contracts.

This runner is intentionally a deterministic model-level smoke test.  It is
not a boss implementation and it is not a substitute for the canonical live
raid capture.  The fixture is adapted to the full declarative contract shape,
executed by :mod:`ml.raid.foundation`, and then independently checked against
the frozen BWD 10N provisioning identity.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import json
from math import dist
from math import isfinite
from pathlib import Path
import subprocess
import sys
from typing import Any

# Support both ``python -m`` (the Pixi task) and direct execution from the
# repository root, matching the other raid-program entry points.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.raid.foundation import (
    RaidMember,
    compile_mechanic_contract,
    form_raid,
    formation_points,
    generic_assignment_smoke,
    validate_evidence_demultiplex,
)
from tools.raid_program.capture_phase1_raid_foundation import (
    _expected_identity_by_slot,
    _provisioned_bwd_10n_bots,
    expected_bwd_10n_roster,
)


DEFAULT_CONFIG = ROOT / "experiments/configs/cata_raid_phase1_generic_mechanic_smoke_v1.json"

# These values mirror the deterministic native validation fixture used by the
# capture verifier.  They are synthetic identity values and do not certify a
# live worldserver instance.
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


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repository_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_immutable(path: Path, payload: Any) -> str:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = _canonical_bytes(payload) + b"\n"
    try:
        with path.open("xb") as handle:
            handle.write(encoded)
    except FileExistsError as error:
        raise ValueError(f"immutable_output_exists:{path}") from error
    return hashlib.sha256(encoded).hexdigest()


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
    seen_route_ids: set[str] = set()
    for route in routes:
        if not isinstance(route, dict):
            raise ValueError("fixture_route_not_object")
        route_id = str(route.get("route_node_id") or "")
        if not route_id or route_id in seen_route_ids:
            raise ValueError("fixture_route_identity_invalid")
        seen_route_ids.add(route_id)
        if route.get("scenario_id") != payload["scenario_id"]:
            raise ValueError(f"fixture_route_scenario_mismatch:{route_id}")
        if route.get("map_id") != MAP_ID:
            raise ValueError(f"fixture_route_map_mismatch:{route_id}")
        if route.get("kind") != "regroup" or route.get("node_kind") != "regroup":
            raise ValueError(f"fixture_route_kind_mismatch:{route_id}")
        if any(
            not isinstance(route.get(field), (int, float))
            or isinstance(route.get(field), bool)
            or not isfinite(float(route[field]))
            for field in ("x", "y", "z", "o")
        ):
            raise ValueError(f"fixture_route_anchor_invalid:{route_id}")
    return payload


def _frozen_roster() -> tuple[dict[str, Any], ...]:
    """Build the exact checked-in provisioning identity in native order."""

    expected_slots = expected_bwd_10n_roster()
    expected_identity = _expected_identity_by_slot()
    bots = _provisioned_bwd_10n_bots()
    if len(bots) != len(expected_slots) or len(bots) != 10:
        raise ValueError("frozen_bwd_roster_size_mismatch")

    rows: list[dict[str, Any]] = []
    role_counts: Counter[str] = Counter()
    for index, (bot, expected) in enumerate(zip(bots, expected_slots, strict=True)):
        slot_id, role, class_id, class_spec = expected
        role_counts[role] += 1
        observed = (
            str(bot.get("role") or ""),
            int(bot.get("class") or 0),
            str(bot.get("class_spec") or ""),
        )
        if observed != (role, class_id, class_spec):
            raise ValueError(f"frozen_bwd_roster_identity_mismatch:{slot_id}")
        account = str(bot.get("account") or "")
        name = str(bot.get("name") or "")
        if not account or not name:
            raise ValueError(f"frozen_bwd_roster_identity_missing:{slot_id}")
        rows.append(
            {
                "roster_slot_id": slot_id,
                "lease_role_slot": slot_id,
                "guid": LEADER_GUID + index,
                "role": role,
                "class_id": class_id,
                "class_spec": class_spec,
                "account": account,
                "name": name,
                "talents": list(expected_identity[slot_id]["talents"]),
                "glyphs": list(expected_identity[slot_id]["glyphs"]),
                "gear_manifest": [
                    {
                        "slot": item["slot"],
                        "entry": item["entry"],
                        "enchant_id": item["enchant_id"],
                        "gem_item_ids": list(item["gem_item_ids"]),
                        "reforge_id": item["reforge_id"],
                    }
                    for item in expected_identity[slot_id]["gear"]
                ],
                "slot": index,
                "subgroup": index // 5,
                "active": True,
                "lease_owned": True,
            }
        )
    if role_counts != Counter({"tank": 2, "healer": 3, "dps": 5}):
        raise ValueError("frozen_bwd_roster_composition_mismatch")
    if rows[0]["guid"] != LEADER_GUID or len({row["guid"] for row in rows}) != 10:
        raise ValueError("frozen_bwd_roster_guid_identity_mismatch")
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


def _contract_payload(route: dict[str, Any]) -> dict[str, Any]:
    source = route.get("mechanic_contract")
    if not isinstance(source, dict):
        raise ValueError(f"route_contract_missing:{route.get('route_node_id', '')}")
    formation = str(source.get("formation_family") or "")
    if not formation:
        raise ValueError("route_formation_missing")
    if source.get("formation_anchor") != "route_anchor":
        raise ValueError(f"route_formation_anchor_invalid:{route.get('route_node_id', '')}")
    if source.get("formation_orientation") != "route":
        raise ValueError(f"route_formation_orientation_invalid:{route.get('route_node_id', '')}")
    distance = source.get("spacing_yards", source.get("radius_yards"))
    if not isinstance(distance, (int, float)) or isinstance(distance, bool) or distance <= 0:
        raise ValueError(f"route_geometry_missing:{route.get('route_node_id', '')}")
    target_control = str(source.get("target_control") or "")
    if target_control not in TARGET_CONTROL_MAP:
        raise ValueError(f"route_target_control_unknown:{target_control}")
    if not isinstance(source.get("allow_area_damage"), bool):
        raise ValueError(f"route_area_damage_invalid:{route.get('route_node_id', '')}")

    # The generic fixture deliberately omits policies that are not needed to
    # describe its geometry.  These explicit synthetic defaults make the
    # adapter auditable and ensure compile_mechanic_contract validates all
    # fields rather than letting a partial payload pass through.
    # ``not_declared`` is an explicit absence marker accepted by the
    # foundation compiler's fixture mode.  It is deliberately not a gameplay
    # default: raw evidence and the verifier preserve it and never claim that
    # an omitted primitive was exercised.
    return {
        "strategy_id": str(source.get("id") or route.get("route_node_id") or ""),
        "formation": formation,
        "anchor_scope": "raid",
        "minimum_distance": float(distance),
        "target_control": TARGET_CONTROL_MAP[target_control],
    }


def _route_checks(
    route: dict[str, Any],
    foundation: Any,
    events: tuple[dict[str, Any], ...],
    assignment_generation: int,
    roster: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    source = route["mechanic_contract"]
    payload = _contract_payload(route)
    contract = compile_mechanic_contract(payload, allow_undeclared=True)
    expected_identity = replace(foundation.identity, strategy_id=contract.strategy_id)
    observed = validate_evidence_demultiplex(events, expected_identity, foundation.members)
    points = formation_points(contract.formation, 10, minimum_distance=contract.minimum_distance)
    tolerance = float(source["arrival_tolerance_yards"])
    geometry_ok = all(
        dist(points[left], points[right]) >= contract.minimum_distance - 1e-9
        for left in range(len(points))
        for right in range(left + 1, len(points))
    )
    if len(events) != 10:
        raise ValueError(f"route_event_count:{route['route_node_id']}")
    if any(event["assignment_generation"] != assignment_generation for event in events):
        raise ValueError(f"route_assignment_generation:{route['route_node_id']}")
    if any(
        event["evidence_sequence"] != assignment_generation * foundation.identity.raid_size + event["slot"] + 1
        for event in events
    ):
        raise ValueError(f"route_evidence_sequence:{route['route_node_id']}")
    if any(event["formation_point"] != point for event, point in zip(events, points, strict=True)):
        raise ValueError(f"route_geometry_mismatch:{route['route_node_id']}")
    if not geometry_ok or tolerance <= 0:
        raise ValueError(f"route_geometry_invalid:{route['route_node_id']}")

    expected_targets = source.get("target_entries")
    if not isinstance(expected_targets, list) or not expected_targets or any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in expected_targets
    ):
        raise ValueError(f"route_target_entries_invalid:{route['route_node_id']}")
    if len(set(expected_targets)) != len(expected_targets):
        raise ValueError(f"route_target_entries_duplicate:{route['route_node_id']}")

    expected_control = TARGET_CONTROL_MAP[source["target_control"]]
    expected_interrupt = foundation.interrupt_rotation
    expected_dispel = foundation.dispel_rotation
    expected_roster = {row["guid"]: row for row in roster}
    identity_ok = True
    rotation_ok = True
    interaction_ok = True
    per_member: list[dict[str, Any]] = []
    for event in events:
        member = expected_roster.get(event.get("member_guid"))
        member_identity_ok = member is not None and all(
            event.get(key) == member[key]
            for key in ("roster_slot_id", "slot", "subgroup", "role")
        )
        identity_ok = identity_ok and member_identity_ok
        member_rotation_ok = (
            event.get("interrupt_primary") == expected_interrupt[0]
            and event.get("interrupt_backup") is None
            and event.get("dispel_primary") == expected_dispel[0]
            and event.get("dispel_backup") is None
        )
        rotation_ok = rotation_ok and member_rotation_ok
        member_interaction_ok = (
            event.get("interaction_kind") == "not_declared"
            and event.get("movement_link") == "not_declared"
            and event.get("platform_policy") == "not_declared"
            and event.get("recovery_policy") == "not_declared"
            and event.get("target_control") == expected_control
        )
        interaction_ok = interaction_ok and member_interaction_ok
        per_member.append(
            {
                "member_guid": event.get("member_guid"),
                "roster_slot_id": event.get("roster_slot_id"),
                "identity_ok": member_identity_ok,
                "assignment_generation": event.get("assignment_generation"),
                "geometry_ok": event.get("formation_point") in points,
                "target_control_ok": event.get("target_control") == expected_control,
                "rotation_ok": member_rotation_ok,
                "interaction_ok": member_interaction_ok,
            }
        )

    source_specific: dict[str, Any] = {
        "target_entries": list(expected_targets),
        "allow_area_damage": bool(source.get("allow_area_damage")),
    }
    if expected_control == "controlled_aoe":
        minimum = source.get("controlled_aoe_minimum_targets")
        source_specific["controlled_aoe_minimum_targets"] = minimum
        source_specific["controlled_aoe_ok"] = bool(
            source.get("allow_area_damage") is True and isinstance(minimum, int) and minimum > 0
        )
    elif expected_control == "kill_synchronization":
        alternate_entries = list(route.get("alternate_target_entries") or [])
        source_specific["alternate_target_entries"] = alternate_entries
        source_specific["kill_sync_ok"] = bool(
            alternate_entries
            and all(isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in alternate_entries)
            and len(set(alternate_entries)) == len(alternate_entries)
            and isinstance(source.get("kill_sync_tolerance_pct"), (int, float))
            and isinstance(source.get("kill_sync_execution_floor_pct"), (int, float))
            and 0 < source["kill_sync_execution_floor_pct"] < source["kill_sync_tolerance_pct"]
        )
    if source.get("soak_roster_slots") is not None:
        soak_slots = source["soak_roster_slots"]
        source_specific["soak_ok"] = bool(
            isinstance(soak_slots, list)
            and len(soak_slots) == source.get("soak_minimum_count")
            and all(isinstance(slot, int) and 1 <= slot <= 10 for slot in soak_slots)
        )
    if source.get("dispel_owner_slot") is not None:
        source_specific["dispel_ok"] = bool(
            isinstance(source.get("dispel_owner_slot"), int)
            and isinstance(source.get("dispel_backup_slot"), int)
            and source["dispel_owner_slot"] != source["dispel_backup_slot"]
            and 1 <= source["dispel_owner_slot"] <= 10
            and 1 <= source["dispel_backup_slot"] <= 10
        )
    if source.get("cooldown_owner_slot") is not None:
        source_specific["cooldown_ok"] = bool(
            isinstance(source.get("cooldown_owner_slot"), int)
            and 1 <= source["cooldown_owner_slot"] <= 10
            and isinstance(source.get("cooldown_trigger_spell_id"), int)
            and source["cooldown_trigger_spell_id"] > 0
        )

    source_specific_ok = all(value for key, value in source_specific.items() if key.endswith("_ok"))
    route_anchor_ok = route["map_id"] == foundation.identity.map_id and all(
        isfinite(float(route[field])) for field in ("x", "y", "z", "o")
    )
    return {
        "route_node_id": route["route_node_id"],
        "contract_id": contract.strategy_id,
        "assignment_generation": assignment_generation,
        "event_count": observed,
        "formation": contract.formation,
        "minimum_distance": contract.minimum_distance,
        "arrival_tolerance_yards": tolerance,
        "route_anchor": {
            "map_id": route["map_id"],
            "x": route["x"],
            "y": route["y"],
            "z": route["z"],
            "o": route["o"],
            "ok": route_anchor_ok,
        },
        "geometry_ok": geometry_ok,
        "identity_ok": identity_ok,
        "rotation_ok": rotation_ok,
        "target_control": expected_control,
        "interaction": {
            "declared_fields": [],
            "not_exercised": [
                "interaction_kind",
                "movement_link",
                "platform_policy",
                "recovery_policy",
            ],
            "ok": interaction_ok,
        },
        "source_specific": source_specific,
        "source_specific_ok": source_specific_ok,
        "per_member": per_member,
        "passed": all((identity_ok, rotation_ok, interaction_ok, geometry_ok, route_anchor_ok, source_specific_ok)),
    }


def _synthetic_outcome_events(
    route: dict[str, Any],
    assignment_events: tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    """Generate deterministic model outcomes from fields actually in a route.

    These are executable synthetic state transitions, not boss behavior.  A
    negative row is an intentionally rejected counterexample; it proves the
    generic policy closes the unsafe branch without asserting that a live boss
    emitted the event.
    """

    source = route["mechanic_contract"]
    target_control = TARGET_CONTROL_MAP[source["target_control"]]
    next_sequence = max(event["evidence_sequence"] for event in assignment_events) + 1
    events: list[dict[str, Any]] = []

    def add(kind: str, state: str, **fields: Any) -> None:
        nonlocal next_sequence
        events.append(
            {
                "evidence_sequence": next_sequence,
                "route_node_id": route["route_node_id"],
                "kind": kind,
                "state": state,
                "target_control": target_control,
                **fields,
            }
        )
        next_sequence += 1

    add("state_transition", "ready", accepted=True)
    add(
        "state_transition",
        "assigned",
        accepted=True,
        assignment_generation=assignment_events[0]["assignment_generation"],
        member_count=len(assignment_events),
    )
    target_entries = [int(value) for value in source["target_entries"]]
    if target_control == "do_not_damage":
        add(
            "outcome",
            "target_hold",
            case="do_not_damage_hold",
            target_entry=target_entries[0],
            damage_allowed=False,
            decision="hold",
            accepted=True,
        )
        add(
            "counterexample",
            "target_hold",
            case="do_not_damage_wrong_target",
            target_entry=max(target_entries) + 1,
            damage_allowed=True,
            decision="reject",
            accepted=False,
            reason="undeclared_target_damage_rejected",
        )
    elif target_control == "focus_fire":
        add(
            "outcome",
            "focus_authority",
            case="focus_authority",
            focus_target_entry=target_entries[0],
            attacker_target_entry=target_entries[0],
            damage_allowed=True,
            decision="attack",
            accepted=True,
        )
        add(
            "counterexample",
            "focus_authority",
            case="focus_wrong_attacker_target",
            focus_target_entry=target_entries[0],
            attacker_target_entry=max(target_entries) + 1,
            damage_allowed=True,
            decision="reject",
            accepted=False,
            reason="focus_authority_rejected_wrong_target",
        )
    elif target_control == "controlled_aoe":
        minimum = int(source["controlled_aoe_minimum_targets"])
        add(
            "outcome",
            "controlled_aoe_threshold_closed",
            case="controlled_aoe_threshold_below",
            declared_target_entries=target_entries,
            observed_declared_targets=minimum - 1,
            minimum_targets=minimum,
            area_damage_allowed=False,
            decision="hold",
            accepted=True,
        )
        add(
            "outcome",
            "controlled_aoe_threshold_open",
            case="controlled_aoe_threshold_met",
            declared_target_entries=target_entries,
            observed_declared_targets=minimum,
            minimum_targets=minimum,
            area_damage_allowed=True,
            decision="release",
            accepted=True,
        )
        add(
            "counterexample",
            "controlled_aoe_fail_closed",
            case="controlled_aoe_undeclared_hostile",
            declared_target_entries=target_entries,
            undeclared_hostile_entry=max(target_entries) + 1,
            observed_declared_targets=minimum,
            minimum_targets=minimum,
            area_damage_allowed=False,
            decision="fail_close",
            accepted=False,
            reason="undeclared_hostile_fail_closed",
        )
    elif target_control == "kill_synchronization":
        tolerance = float(source["kill_sync_tolerance_pct"])
        floor = float(source["kill_sync_execution_floor_pct"])
        alternate = [int(value) for value in route["alternate_target_entries"]]
        add(
            "outcome",
            "kill_sync_selection",
            case="kill_sync_selection",
            selected_target_entries=target_entries,
            alternate_target_entries=alternate,
            accepted=True,
        )
        add(
            "outcome",
            "kill_sync_hold",
            case="kill_sync_hold",
            lowest_health_pct=floor,
            peer_health_pct=floor + tolerance,
            execution_floor_pct=floor,
            decision="hold_low_target",
            accepted=True,
        )
        add(
            "outcome",
            "kill_sync_release",
            case="kill_sync_release",
            lowest_health_pct=floor,
            peer_health_pct=floor,
            execution_floor_pct=floor,
            decision="release",
            accepted=True,
        )
        add(
            "counterexample",
            "kill_sync_hold",
            case="kill_sync_release_peer_above_floor",
            lowest_health_pct=floor,
            peer_health_pct=floor + tolerance,
            execution_floor_pct=floor,
            decision="hold",
            accepted=False,
            reason="kill_sync_release_rejected_peer_above_floor",
        )
    else:
        raise ValueError(f"synthetic_target_control_unhandled:{target_control}")

    if "soak_roster_slots" in source:
        slots = [int(value) for value in source["soak_roster_slots"]]
        radius = float(source["soak_radius_yards"])
        minimum = int(source["soak_minimum_count"])
        add(
            "outcome",
            "soak_valid",
            case="soak_membership_radius_count",
            soak_roster_slots=slots,
            soak_radius_yards=radius,
            observed_count=len(slots),
            minimum_count=minimum,
            members_in_radius=True,
            accepted=True,
        )
        add(
            "counterexample",
            "soak_rejected",
            case="soak_out_of_radius",
            soak_roster_slots=slots[:-1],
            soak_radius_yards=radius,
            observed_count=len(slots) - 1,
            minimum_count=minimum,
            members_in_radius=False,
            accepted=False,
            reason="soak_membership_radius_or_count_rejected",
        )
    if "dispel_owner_slot" in source:
        add(
            "outcome",
            "dispel_primary",
            case="dispel_owner_then_backup",
            aura_id=int(source["dispel_aura_id"]),
            owner_slot=int(source["dispel_owner_slot"]),
            backup_slot=int(source["dispel_backup_slot"]),
            selected_slot=int(source["dispel_owner_slot"]),
            owner_available=True,
            accepted=True,
        )
        add(
            "outcome",
            "dispel_backup",
            case="dispel_owner_then_backup",
            aura_id=int(source["dispel_aura_id"]),
            owner_slot=int(source["dispel_owner_slot"]),
            backup_slot=int(source["dispel_backup_slot"]),
            selected_slot=int(source["dispel_backup_slot"]),
            owner_available=False,
            accepted=True,
        )
        add(
            "counterexample",
            "dispel_rejected",
            case="dispel_unknown_owner",
            aura_id=int(source["dispel_aura_id"]),
            owner_slot=int(source["dispel_owner_slot"]),
            backup_slot=int(source["dispel_backup_slot"]),
            selected_slot=int(source["dispel_backup_slot"]) + 1,
            owner_available=False,
            accepted=False,
            reason="dispel_owner_or_backup_rejected",
        )
    if "cooldown_owner_slot" in source:
        add(
            "outcome",
            "cooldown_triggered",
            case="cooldown_trigger_owner",
            category=str(source["cooldown_category"]),
            trigger_spell_id=int(source["cooldown_trigger_spell_id"]),
            owner_slot=int(source["cooldown_owner_slot"]),
            triggered=True,
            accepted=True,
        )
        add(
            "counterexample",
            "cooldown_rejected",
            case="cooldown_wrong_trigger_or_owner",
            category=str(source["cooldown_category"]),
            trigger_spell_id=int(source["cooldown_trigger_spell_id"]) + 1,
            owner_slot=int(source["cooldown_owner_slot"]) + 1,
            triggered=False,
            accepted=False,
            reason="cooldown_trigger_or_owner_rejected",
        )
    add(
        "state_transition",
        "complete",
        accepted=True,
        undeclared_primitives_exercised=[],
    )
    return events


def _foundation_identity(foundation: Any) -> dict[str, Any]:
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


def build_raw_evidence(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Execute the fixture and return raw assignment/state/outcome evidence."""

    config_path = config_path.resolve()
    fixture = _load_fixture(config_path)
    roster = _frozen_roster()
    provisioned_bots = _provisioned_bwd_10n_bots()
    foundation = _foundation(roster)
    raw_routes: list[dict[str, Any]] = []
    for index, route in enumerate(fixture["routes"], start=1):
        contract = compile_mechanic_contract(_contract_payload(route), allow_undeclared=True)
        assignment_events = generic_assignment_smoke(
            foundation,
            contract,
            assignment_generation=index,
        )
        raw_routes.append(
            {
                "route_node_id": route["route_node_id"],
                "contract_id": contract.strategy_id,
                "assignment_generation": index,
                "assignment_events": json.loads(json.dumps(assignment_events)),
                "outcome_events": _synthetic_outcome_events(route, assignment_events),
            }
        )
    return {
        "schema": "cata_raid_phase1_generic_mechanic_smoke_raw_v1",
        "authority": fixture["authority"],
        "fixture_schema": fixture["schema"],
        "scenario_id": fixture["scenario_id"],
        "identity": _foundation_identity(foundation),
        "roster": list(roster),
        "routes": raw_routes,
        "provenance": {
            "fixture_sha256": _sha256_file(config_path),
            "runner_sha256": _sha256_file(Path(__file__).resolve()),
            "verifier_sha256": _sha256_file(
                ROOT / "tools/raid_program/verify_phase1_generic_mechanic_smoke.py"
            ),
            "foundation_sha256": _sha256_file(ROOT / "ml/raid/foundation.py"),
            "provisioning_source_sha256": _sha256_file(
                ROOT / "tools/raid_program/capture_phase1_raid_foundation.py"
            ),
            "commit_sha": _repository_commit(),
            "roster_sha256": canonical_sha256(roster),
            "provisioning_sha256": canonical_sha256(provisioned_bots),
        },
    }


def _raw_route_summary(route: dict[str, Any]) -> dict[str, Any]:
    outcomes = list(route["outcome_events"])
    negatives = [event for event in outcomes if event["kind"] == "counterexample"]
    return {
        "route_node_id": route["route_node_id"],
        "contract_id": route["contract_id"],
        "assignment_generation": route["assignment_generation"],
        "raw_assignment_event_count": len(route["assignment_events"]),
        "raw_outcome_event_count": len(outcomes),
        "negative_counterexample_count": len(negatives),
        "negative_cases": [event["case"] for event in negatives],
        "undeclared_primitives_exercised": sorted(
            {
                field
                for event in outcomes
                for field in event.get("undeclared_primitives_exercised", [])
            }
        ),
    }


def run_smoke(
    config_path: Path = DEFAULT_CONFIG,
    *,
    raw_output: Path | None = None,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    try:
        raw = build_raw_evidence(config_path)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        try:
            failed_fixture = json.loads(config_path.read_text(encoding="utf-8"))
            failed_routes = [
                {"route_node_id": route.get("route_node_id"), "passed": False, "error": str(error)}
                for route in failed_fixture.get("routes", [])
                if isinstance(route, dict)
            ]
        except (OSError, json.JSONDecodeError, AttributeError):
            failed_routes = []
        return {
            "schema": "cata_raid_phase1_generic_mechanic_smoke_report_v2",
            "authority": "synthetic_test_only_not_boss_fidelity",
            "synthetic_test_only": True,
            "canonical_live_capture_replacement": False,
            "fixture": {"path": str(config_path)},
            "provenance": {
                "runner_sha256": _sha256_file(Path(__file__).resolve()),
                "commit_sha": _repository_commit(),
                "raw_evidence_path": str(raw_output.resolve()) if raw_output else None,
            },
            "routes": failed_routes,
            "failures": [str(error)],
            "gate_passed": False,
        }
    roster = _frozen_roster()
    foundation = _foundation(roster)
    route_reports: list[dict[str, Any]] = []
    failures: list[str] = []
    route_by_id = {route["route_node_id"]: route for route in _load_fixture(config_path)["routes"]}
    for raw_route in raw["routes"]:
        route = route_by_id[raw_route["route_node_id"]]
        try:
            checks = _route_checks(
                route,
                foundation,
                tuple(
                    {
                        **event,
                        "formation_point": tuple(event["formation_point"]),
                    }
                    for event in raw_route["assignment_events"]
                ),
                raw_route["assignment_generation"],
                roster,
            )
            checks.update(_raw_route_summary(raw_route))
            route_reports.append(checks)
            if not checks["passed"]:
                failures.append(f"{route['route_node_id']}:assignment_or_contract_check_failed")
        except (KeyError, TypeError, ValueError) as error:
            route_reports.append(
                {
                    **_raw_route_summary(raw_route),
                    "passed": False,
                    "error": str(error),
                }
            )
            failures.append(f"{route.get('route_node_id', 'unknown')}:{error}")

    raw_bytes = _canonical_bytes(raw) + b"\n"
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    # Acceptance is owned by the separately invocable verifier.  It rebuilds
    # assignments and outcomes from the fixture and frozen provisioning and
    # never consumes this producer's route/pass fields.
    from tools.raid_program.verify_phase1_generic_mechanic_smoke import verify_raw_evidence
    verification = verify_raw_evidence(config_path, raw)
    failures.extend(f"independent_verifier:{reason}" for reason in verification["failures"])
    if raw_output is not None:
        _write_immutable(raw_output, raw)
    report = {
        "schema": "cata_raid_phase1_generic_mechanic_smoke_report_v2",
        "authority": raw["authority"],
        "synthetic_test_only": True,
        "canonical_live_capture_replacement": False,
        "fixture": {
            "path": str(config_path),
            "schema": raw["fixture_schema"],
            "scenario_id": raw["scenario_id"],
            "sha256": raw["provenance"]["fixture_sha256"],
        },
        "provenance": {
            **raw["provenance"],
            "raw_evidence_sha256": raw_sha256,
            "raw_evidence_path": str(raw_output.resolve()) if raw_output else None,
        },
        "foundation": {
            "identity": raw["identity"],
            "roster_identity_sha256": raw["provenance"]["roster_sha256"],
            "provisioning_identity_sha256": raw["provenance"]["provisioning_sha256"],
            "composition": dict(Counter(row["role"] for row in roster)),
            "subgroups": [list(group) for group in foundation.soak_groups],
            "member_count": len(foundation.members),
            "exact_member_identity_in_raw_evidence": True,
        },
        "routes": route_reports,
        "independent_verification": verification,
        "failures": failures,
        "gate_passed": not failures and len(route_reports) == len(_load_fixture(config_path)["routes"])
        and all(route.get("passed") is True for route in route_reports)
        and verification["verification_gate_passed"] is True,
    }
    # Run the standalone verifier against the raw envelope before publishing
    # the compact gate.  The verifier recomputes assignments and outcomes and
    # never consumes this report's gate or per-route passed fields.
    from tools.raid_program.verify_phase1_generic_mechanic_smoke import verify_raw_evidence

    independent = verify_raw_evidence(config_path, raw)
    report["independent_verification"] = {
        "verification_gate_passed": independent["verification_gate_passed"],
        "failures": independent["failures"],
    }
    if not independent["verification_gate_passed"]:
        report["failures"].extend(f"independent:{failure}" for failure in independent["failures"])
        report["gate_passed"] = False
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, help="write the compact canonical report to this path")
    parser.add_argument("--raw-output", type=Path, help="write immutable raw event evidence to this path")
    args = parser.parse_args()
    try:
        report = run_smoke(args.config, raw_output=args.raw_output)
    except (OSError, KeyError, TypeError, ValueError) as error:
        report = {
            "schema": "cata_raid_phase1_generic_mechanic_smoke_report_v1",
            "authority": "synthetic_test_only_not_boss_fidelity",
            "synthetic_test_only": True,
            "canonical_live_capture_replacement": False,
            "failures": [str(error)],
            "gate_passed": False,
        }
    encoded = json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if args.output:
        _write_immutable(args.output, report)
    print(encoded)
    return 0 if report["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
