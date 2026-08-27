from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path

from tools.bot_ml.run_live_bot_validation import write_validation_config

from tools.bot_ml.build_validation_scenario_manifests import (
    build_manifests,
    drudge_split_geometry_status,
    patrol_pull_contract_status,
)
from tools.bot_ml.build_live_scenario_reports import build_reports


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
PROFILE_MANIFEST = ROOT / "dataset/bot_runtime_profiles/profiles.json"
SHARD_FIXTURE = ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"

CANONICAL_ID = "blackwing_descent_10n"
DIAGNOSTIC_IDS = {
    "magmaw": "blackwing_descent_10n_magmaw_diagnostic",
    "omnotron": "blackwing_descent_10n_omnotron_diagnostic",
    "maloriak": "blackwing_descent_10n_maloriak_diagnostic",
    "atramedes": "blackwing_descent_10n_atramedes_diagnostic",
    "chimaeron": "blackwing_descent_10n_chimaeron_diagnostic",
    "nefarian": "blackwing_descent_10n_nefarian_diagnostic",
}


def _config() -> dict:
    return json.loads(SCENARIO_CONFIG.read_text(encoding="utf-8"))


def _manifests() -> dict:
    return build_manifests(
        _config(),
        {
            "all_ready": True,
            "scenarios": [
                {
                    "scenario_id": "stonecore_5n",
                    "role_counts": {"tank": 1, "healer": 1, "dps": 3},
                },
                {
                    "scenario_id": CANONICAL_ID,
                    "role_counts": {"tank": 2, "healer": 3, "dps": 5},
                },
            ],
        },
        {"all_passed": True},
        json.loads(SHARD_FIXTURE.read_text(encoding="utf-8")),
    )


def _routes(manifests: dict, scenario_id: str) -> list[dict]:
    return [row for row in manifests["validation_routes"] if row["scenario_id"] == scenario_id]


def test_drudge_combat_anchor_geometry_is_sql_bound_and_requires_native_chase_margin():
    config = _config()
    canonical = next(row for row in config["scenarios"] if row["id"] == CANONICAL_ID)
    drudges = next(
        row for row in canonical["route"]
        if row.get("mechanic_profile") == "trash_two_tank_charge_lanes"
    )
    magmaw = canonical["route"][canonical["route"].index(drudges) + 1]
    assert drudge_split_geometry_status(drudges, magmaw) == (True, "")
    assert drudges["split_seed_roster_slots"] == [8, 6]
    assert drudges["split_healer_roster_slots"] == [3, 4, 5]
    assert drudges["split_seed_max_range_yards"] == 35.0
    assert drudges["split_tank_threat_headroom_multiplier"] == 2.5
    recovery_by_slot = {
        row["roster_slot"]: row for row in drudges["split_tank_recovery_anchors"]
    }
    assert recovery_by_slot == {
        1: {"roster_slot": 1, "x": -330.0, "y": -88.0, "z": 214.0},
        2: {"roster_slot": 2, "x": -348.0, "y": -120.0, "z": 214.0},
    }
    member_by_slot = {
        row["roster_slot"]: row for row in drudges["split_member_anchors"]
    }
    assert member_by_slot[3] == {
        "roster_slot": 3, "x": -296.0, "y": -69.9, "z": 213.485,
    }
    assert member_by_slot[4] == {
        "roster_slot": 4, "x": -298.8, "y": -71.5, "z": 213.461,
    }
    assert member_by_slot[5] == {
        "roster_slot": 5, "x": -311.5, "y": -71.3, "z": 213.292,
    }
    assert member_by_slot[7] == {
        "roster_slot": 7, "x": -292.5, "y": -69.1, "z": 214.024,
    }
    # Slot 6 is the source-250141 seed.  It must be farther than the adjacent
    # healer at the declared formation while retaining its 35-yard hostile
    # action envelope; native SMART_TARGET_FARTHEST remains untouched.
    source_1 = (-314.887329, -48.970574, 212.2623)
    seed_distance = math.dist(
        tuple(member_by_slot[6][axis] for axis in ("x", "y", "z")), source_1,
    )
    healer_distance = math.dist(
        tuple(member_by_slot[4][axis] for axis in ("x", "y", "z")), source_1,
    )
    assert seed_distance > healer_distance
    assert seed_distance + drudges["split_arrival_tolerance_yards"] <= 35.0

    # Slot 8 is the source-250140 initial seed. Keep it near the verified
    # lane-B floor while leaving a large margin from
    # the opposite tank's native combat anchor. Runtime still reconstructs
    # native threat-list eligibility/farthest selection and requires a strict
    # return path.
    source_0 = (-295.608573, -52.851976, 212.2983)
    slot_8 = tuple(member_by_slot[8][axis] for axis in ("x", "y", "z"))
    assert slot_8 == (-311.5, -78.0, 213.5)
    assert math.dist(slot_8, source_0) + drudges["split_arrival_tolerance_yards"] <= 35.0
    restored_source_1 = (-314.887329, -48.970574, 212.2623)
    assert (
        math.dist(slot_8, restored_source_1)
        - drudges["split_arrival_tolerance_yards"]
        - drudges["split_tank_arrival_tolerance_yards"]
        >= drudges["minimum_distance_yards"]
    )
    # Run9 showed that the live source-250141 return to the slot-2 combat
    # anchor can approach the old slot-8 point within the 15-yard guard. The
    # replacement point retains the hostile range contract and leaves a
    # materially larger two-arrival-disk margin from that native position.
    opposite_combat_anchor = (-322.858002, -48.286201)
    opposite_margin = (
        math.hypot(slot_8[0] - opposite_combat_anchor[0],
                   slot_8[1] - opposite_combat_anchor[1])
        - drudges["split_arrival_tolerance_yards"]
        - drudges["split_tank_arrival_tolerance_yards"]
    )
    assert opposite_margin >= drudges["minimum_distance_yards"] + 10.0
    recovery_member_by_slot = {
        row["roster_slot"]: row
        for row in drudges["split_recovery_member_anchors"]
    }
    assert set(recovery_member_by_slot) == set(range(1, 11))
    assert recovery_member_by_slot[1] == recovery_by_slot[1]
    assert recovery_member_by_slot[2] == recovery_by_slot[2]

    # After the first native Rush, target selection is diagnostic. The compact
    # entrance hold is instead proven by the recovery clearance, lane-side,
    # healing-range, and future-Magmaw checks below.
    # A returning Rush can approach the tank from any direction.  Prove the
    # full melee-stop and arrival disks, rather than the initial radial chase.
    worst_source_radius = (
        drudges["split_native_melee_stop_yards"]
        + drudges["split_tank_arrival_tolerance_yards"]
    )
    recovery_points = {
        slot: (row["x"], row["y"])
        for slot, row in recovery_by_slot.items()
    }
    assert (
        math.dist(recovery_points[1], recovery_points[2])
        - 2.0 * worst_source_radius
        >= drudges["split_minimum_separation_yards"]
        + drudges["split_navigation_margin_yards"]
    )
    required_member_clearance = (
        drudges["minimum_distance_yards"]
        + drudges["split_native_melee_stop_yards"]
        + drudges["split_arrival_tolerance_yards"]
        + drudges["split_tank_arrival_tolerance_yards"]
    )
    for slot, anchor in recovery_member_by_slot.items():
        if slot in (1, 2):
            continue
        point = (anchor["x"], anchor["y"])
        assert all(
            math.dist(point, recovery) >= required_member_clearance
            for recovery in recovery_points.values()
        )

    unsafe = deepcopy(drudges)
    unsafe["split_tank_combat_anchors"] = [
        {"roster_slot": 1, "x": -294.904, "y": -50.6863, "z": 212.232},
        {"roster_slot": 2, "x": -311.842, "y": -49.2321, "z": 212.129},
    ]
    assert drudge_split_geometry_status(unsafe) == (
        False,
        "split_combat_anchor_insufficient_native_chase",
    )

    wrong_oracle = deepcopy(drudges)
    wrong_oracle["split_source_home_anchors"][0]["x"] += 1.0
    assert drudge_split_geometry_status(wrong_oracle) == (
        False,
        "split_source_home_oracle",
    )

    unsafe_member = deepcopy(drudges)
    unsafe_member["split_member_anchors"][2].update(
        unsafe_member["split_source_home_anchors"][0]
    )
    unsafe_member["split_member_anchors"][2]["roster_slot"] = 3
    unsafe_member["split_member_anchors"][2].pop("source_guid", None)
    assert drudge_split_geometry_status(unsafe_member) == (
        False,
        "split_member_anchor_source_unsafe",
    )

    unsafe_member_high_z = deepcopy(unsafe_member)
    unsafe_member_high_z["split_member_anchors"][2]["z"] += 100.0
    assert drudge_split_geometry_status(unsafe_member_high_z) == (
        False,
        "split_member_anchor_source_unsafe",
    )

    unsafe_navigation = deepcopy(drudges)
    unsafe_navigation["split_tank_navigation_anchors"] = [
        {"roster_slot": 1, "x": -291.7762, "y": -56.0799, "z": 212.9},
        {"roster_slot": 2, "x": -319.8744, "y": -48.5998, "z": 212.0},
    ]
    assert drudge_split_geometry_status(unsafe_navigation) == (
        False,
        "split_navigation_anchor_native_chase_unsafe",
    )

    inward_arrival_envelope = deepcopy(drudges)
    inward_arrival_envelope["split_arrival_tolerance_yards"] = 2.0
    inward_arrival_envelope["split_tank_arrival_tolerance_yards"] = 2.0
    assert drudge_split_geometry_status(inward_arrival_envelope) == (
        False,
        "split_navigation_anchor_native_chase_unsafe",
    )

    unsafe_recovery_pair = deepcopy(drudges)
    unsafe_recovery_pair["split_tank_recovery_anchors"][1].update(
        x=-300.0, y=-86.0, z=214.15,
    )
    unsafe_recovery_pair["split_recovery_member_anchors"][1].update(
        x=-300.0, y=-86.0, z=214.15,
    )
    assert drudge_split_geometry_status(unsafe_recovery_pair) == (
        False,
        "split_tank_recovery_source_separation_unsafe",
    )

    mismatched_recovery_tank = deepcopy(drudges)
    mismatched_recovery_tank["split_tank_recovery_anchors"][0]["x"] += 1.0
    assert drudge_split_geometry_status(mismatched_recovery_tank) == (
        False,
        "split_recovery_member_tank_mismatch",
    )

    old_future_unsafe_recovery = deepcopy(drudges)
    old_tank_recovery = (
        (-288.8, -43.0, 212.301),
        (-321.5, -30.0, 211.283429),
    )
    for index, point in enumerate(old_tank_recovery):
        old_future_unsafe_recovery["split_tank_recovery_anchors"][index].update(
            x=point[0], y=point[1], z=point[2]
        )
        old_future_unsafe_recovery["split_recovery_member_anchors"][index].update(
            x=point[0], y=point[1], z=point[2]
        )
    assert drudge_split_geometry_status(old_future_unsafe_recovery, magmaw) == (
        False,
        "split_recovery_future_encounter_unsafe",
    )

    unsafe_recovery_member = deepcopy(drudges)
    unsafe_recovery_member["split_recovery_member_anchors"][2].update(
        x=-330.0, y=-100.0, z=214.0,
    )
    assert drudge_split_geometry_status(unsafe_recovery_member) == (
        False,
        "split_tank_recovery_member_unsafe",
    )

    seed_out_of_range = deepcopy(drudges)
    seed_out_of_range["split_member_anchors"][7]["x"] -= 20.0
    assert drudge_split_geometry_status(seed_out_of_range) == (
        False,
        "split_seed_candidate_range_unsafe",
    )

    seed_inside_source = deepcopy(drudges)
    seed_inside_source["split_member_anchors"][7].update(
        x=-314.887329, y=-48.970574
    )
    assert drudge_split_geometry_status(seed_inside_source) == (
        False,
        "split_member_anchor_source_unsafe",
    )

    old_repeat_geometry = deepcopy(drudges)
    old_repeat_geometry["split_member_anchors"][4].update(
        x=-343.508, y=-44.4466, z=211.947,
    )
    old_repeat_geometry["split_member_anchors"][6].update(
        x=-295.0, y=-82.0, z=213.8,
    )
    assert drudge_split_geometry_status(old_repeat_geometry) == (
        False,
        "split_initial_native_farthest_unsafe",
    )

    weak_native_threat_headroom = deepcopy(drudges)
    weak_native_threat_headroom["split_tank_threat_headroom_multiplier"] = 1.29
    assert drudge_split_geometry_status(weak_native_threat_headroom) == (
        False,
        "split_seed_candidate_contract",
    )


def test_compact_recovery_anchors_are_shared_and_bounded_in_both_drudge_routes():
    config = _config()
    expected_recovery = [
        {"roster_slot": 1, "x": -330.0, "y": -88.0, "z": 214.0},
        {"roster_slot": 2, "x": -348.0, "y": -120.0, "z": 214.0},
        {"roster_slot": 3, "x": -324.0, "y": -113.0, "z": 214.0},
        {"roster_slot": 4, "x": -318.0, "y": -116.0, "z": 214.0},
        {"roster_slot": 5, "x": -321.0, "y": -115.0, "z": 214.0},
        {"roster_slot": 6, "x": -312.0, "y": -119.0, "z": 214.0},
        {"roster_slot": 7, "x": -320.0, "y": -120.0, "z": 214.0},
        {"roster_slot": 8, "x": -315.0, "y": -118.0, "z": 214.0},
        {"roster_slot": 9, "x": -309.0, "y": -121.0, "z": 214.0},
        {"roster_slot": 10, "x": -316.0, "y": -123.0, "z": 214.0},
    ]
    scenarios = config["scenarios"] + config["diagnostic_scenarios"]
    selected = [
        next(row for row in scenarios if row["id"] == scenario_id)
        for scenario_id in (CANONICAL_ID, DIAGNOSTIC_IDS["magmaw"])
    ]
    for scenario in selected:
        drudges = next(
            row for row in scenario["route"]
            if row.get("mechanic_profile") == "trash_two_tank_charge_lanes"
        )
        magmaw = scenario["route"][scenario["route"].index(drudges) + 1]
        assert drudge_split_geometry_status(drudges, magmaw) == (True, "")
        assert drudges["split_recovery_member_anchors"] == expected_recovery

        tank_by_slot = {
            row["roster_slot"]: (row["x"], row["y"])
            for row in drudges["split_tank_recovery_anchors"]
        }
        recovery_by_slot = {
            row["roster_slot"]: (row["x"], row["y"])
            for row in expected_recovery
        }
        lane_a = {3, 4, 6, 7}
        lane_b = {5, 8, 9, 10}
        for slot in lane_a | lane_b:
            point = recovery_by_slot[slot]
            assert all(
                math.dist(point, tank) >= 25.0
                for tank in tank_by_slot.values()
            )
            assigned_tank = tank_by_slot[1 if slot in lane_a else 2]
            assert math.dist(point, assigned_tank) <= 40.0
        for lane in (lane_a, lane_b):
            assert min(
                math.dist(recovery_by_slot[left], recovery_by_slot[right])
                for index, left in enumerate(sorted(lane))
                for right in sorted(lane)[index + 1:]
            ) >= 3.0

        magmaw_point = (magmaw["x"], magmaw["y"])
        combat_safe_distance = min(
            math.dist(magmaw_point, (row["x"], row["y"]))
            for row in drudges["split_tank_combat_anchors"]
        )
        assert all(
            math.dist(magmaw_point, point) > combat_safe_distance
            for point in recovery_by_slot.values()
        )


def test_slot_eight_seed_anchor_is_bound_in_canonical_and_magmaw_diagnostic_routes():
    config = _config()
    expected = {"roster_slot": 8, "x": -311.5, "y": -78.0, "z": 213.5}
    for scenario_id in (CANONICAL_ID, DIAGNOSTIC_IDS["magmaw"]):
        scenario_pool = config["scenarios"] + config["diagnostic_scenarios"]
        scenario = next(row for row in scenario_pool if row["id"] == scenario_id)
        drudges = next(
            row for row in scenario["route"]
            if row.get("mechanic_profile") == "trash_two_tank_charge_lanes"
        )
        member_by_slot = {
            row["roster_slot"]: row for row in drudges["split_member_anchors"]
        }
        assert member_by_slot[8] == expected
        assert drudge_split_geometry_status(drudges) == (True, "")


def test_chainwielder_wait_anchor_and_pull_guard_are_outside_future_drudge_pack():
    config = _config()
    for scenario in [
        next(row for row in config["scenarios"] if row["id"] == CANONICAL_ID),
        next(
            row for row in config["diagnostic_scenarios"]
            if row["id"] == DIAGNOSTIC_IDS["magmaw"]
        ),
    ]:
        chain = next(
            row for row in scenario["route"] if row.get("source_entry") == 42649
        )
        drudges = next(
            row for row in scenario["route"]
            if row.get("mechanic_profile") == "trash_two_tank_charge_lanes"
        )
        guard = float(chain["cluster_radius_yards"])
        assert chain["patrol_pull_policy"] == "ranged_patrol_to_anchor"
        assert chain["patrol_pull_owner_roster_slot"] == 9
        assert chain["patrol_wait_anchor"] == {
            "x": -346.5827,
            "y": -83.71657,
            "z": 213.9893,
        }
        assert patrol_pull_contract_status(chain, scenario["route"]) == (True, "")
        assert all(
            math.hypot(chain["x"] - source["x"], chain["y"] - source["y"])
            > guard
            for source in drudges["split_source_home_anchors"]
        )

        unsafe_wait = deepcopy(chain)
        unsafe_wait["patrol_wait_anchor"] = {
            "x": drudges["split_source_home_anchors"][0]["x"],
            "y": drudges["split_source_home_anchors"][0]["y"],
            "z": drudges["split_source_home_anchors"][0]["z"],
        }
        mutated_route = [
            unsafe_wait if row is chain else row for row in scenario["route"]
        ]
        assert patrol_pull_contract_status(unsafe_wait, mutated_route) == (
            False,
            "patrol_chase_future_guard",
        )

        generated = next(
            row for row in _routes(_manifests(), scenario["id"])
            if row["source_guid"] == "250050"
        )
        assert generated["patrol_pull_policy"] == "ranged_patrol_to_anchor"
        assert generated["patrol_pull_owner_roster_slot"] == 9
        assert generated["patrol_wait_tolerance_yards"] == 3.0
        assert generated["patrol_anchor_tolerance_yards"] == 8.0
        assert generated["patrol_engage_radius_yards"] == 30.0
        assert generated["patrol_future_guard_margin_yards"] == 2.0


def test_canonical_bwd_route_is_the_ordered_native_prerequisite_union():
    routes = _routes(_manifests(), CANONICAL_ID)
    assert [row["route_node_id"] for row in routes] == [
        "bwd.entry.regroup",
        "bwd.magmaw.chainwielder",
        "bwd.magmaw.drudges",
        "bwd.magmaw.encounter",
        "bwd.omnotron.sentries",
        "bwd.omnotron.encounter",
        "bwd.maloriak.lab_trash",
        "bwd.maloriak.encounter",
        "bwd.atramedes.north_spirits",
        "bwd.atramedes.south_spirits",
        "bwd.atramedes.bell_ready",
        "bwd.atramedes.bell",
        "bwd.atramedes.intro_wait",
        "bwd.atramedes.encounter",
        "bwd.chimaeron.regroup",
        "bwd.chimaeron.finkle",
        "bwd.chimaeron.wake_wait",
        "bwd.chimaeron.encounter",
        "bwd.nefarian.orb_regroup",
        "bwd.nefarian.orb_gossip",
        "bwd.nefarian.intro_wait",
        "bwd.nefarian.descent",
        "bwd.nefarian.encounter",
    ]
    assert [row["step"] for row in routes] == list(range(1, 24))
    assert all(row["diagnostic_only"] is False for row in routes)
    assert all(row["runtime_profile_id"] == CANONICAL_ID for row in routes)


def test_each_bwd_diagnostic_shard_has_exact_local_membership_and_unique_profile():
    manifests = _manifests()
    expected = {
        "magmaw": ["bwd.entry.regroup", "bwd.magmaw.chainwielder", "bwd.magmaw.drudges", "bwd.magmaw.encounter"],
        "omnotron": ["bwd.omnotron.regroup", "bwd.omnotron.sentries", "bwd.omnotron.encounter"],
        "maloriak": ["bwd.maloriak.regroup", "bwd.maloriak.lab_trash", "bwd.maloriak.encounter"],
        "atramedes": ["bwd.atramedes.north_spirits", "bwd.atramedes.south_spirits", "bwd.atramedes.bell_ready", "bwd.atramedes.bell", "bwd.atramedes.intro_wait", "bwd.atramedes.regroup", "bwd.atramedes.encounter"],
        "chimaeron": ["bwd.chimaeron.regroup", "bwd.chimaeron.finkle", "bwd.chimaeron.wake_wait", "bwd.chimaeron.encounter"],
        "nefarian": ["bwd.nefarian.orb_regroup", "bwd.nefarian.orb_gossip", "bwd.nefarian.intro_wait", "bwd.nefarian.descent", "bwd.nefarian.encounter"],
    }
    for boss, scenario_id in DIAGNOSTIC_IDS.items():
        routes = _routes(manifests, scenario_id)
        assert [row["route_node_id"] for row in routes] == expected[boss]
        assert [row["step"] for row in routes] == list(range(1, len(routes) + 1))
        assert all(row["diagnostic_only"] is True for row in routes)
        assert all(row["runtime_profile_id"] == scenario_id for row in routes)
        assert all(row["diagnostic_parent_scenario_id"] == CANONICAL_ID for row in routes)
        assert all(row["diagnostic_prerequisite_state"]["certifies_predecessors"] is False for row in routes)
        assert all(len(row["roster_identity"]) == 10 for row in routes)
        assert all(len({member["guid"] for member in row["roster_identity"]}) == 10 for row in routes)
        assert all({member["roster_slot_id"] for member in row["roster_identity"]} == {
            "raid_tank_1", "raid_tank_2", "raid_healer_1", "raid_healer_2", "raid_healer_3",
            "raid_dps_1", "raid_dps_2", "raid_dps_3", "raid_dps_4", "raid_dps_5",
        } for row in routes)
        assert routes[-1]["kind"] == "boss"


def test_magmaw_shard_excludes_omnotron_and_later_route_nodes():
    routes = _routes(_manifests(), DIAGNOSTIC_IDS["magmaw"])
    assert [row["source_entry"] for row in routes] == [0, 42649, 42362, 41570]
    assert not any("Omnotron" in row["label"] for row in routes)
    assert not any(row["source_entry"] in {42166, 41378, 41442, 43296, 41376} for row in routes)


def test_diagnostic_prerequisites_are_explicitly_non_certifying():
    scenarios = {row["scenario_id"]: row for row in _manifests()["validation_scenarios"]}
    assert set(DIAGNOSTIC_IDS.values()).issubset(scenarios)
    assert scenarios[CANONICAL_ID]["diagnostic_only"] is False
    assert scenarios[CANONICAL_ID]["prerequisite_contract"] == {}
    assert scenarios[DIAGNOSTIC_IDS["omnotron"]]["prerequisite_contract"]["precompleted_boss_entries"] == []
    for boss in ("maloriak", "atramedes", "chimaeron"):
        assert scenarios[DIAGNOSTIC_IDS[boss]]["prerequisite_contract"]["precompleted_boss_entries"] == [41570, 42166]
    assert scenarios[DIAGNOSTIC_IDS["nefarian"]]["prerequisite_contract"]["precompleted_boss_entries"] == [41570, 42166, 41378, 41442, 43296]
    for scenario_id in DIAGNOSTIC_IDS.values():
        row = scenarios[scenario_id]
        assert row["certifies_predecessors"] is False
        assert row["diagnostic_parent_scenario_id"] == CANONICAL_ID


def test_nefarian_shard_uses_native_orb_intro_and_player_descent():
    routes = _routes(_manifests(), DIAGNOSTIC_IDS["nefarian"])
    preparation, orb, intro, descent, boss = routes
    assert preparation["source_entry"] == 203254
    assert (preparation["x"], preparation["y"], preparation["z"]) == (-27.84375, -224.4774, 63.30268)
    assert orb["interaction_contract"] == {"action": "gossip_select", "entry": 203254, "menu": 11492, "option": 0}
    assert intro["completion_contract"]["kind"] == "intro_complete_and_elevator_ready"
    assert descent["node_kind"] == "descent"
    assert descent["descent_action"] == "native_walk_jump_or_fall"
    assert descent["completion_contract"] == {"kind": "player_in_nefarian_arena"}
    assert boss["label"] == "Nefarian"
    assert [row["kind"] for row in routes] == ["regroup", "interaction", "interaction", "descent", "boss"]


def test_atramedes_and_chimaeron_prerequisites_are_native_interactions():
    manifests = _manifests()
    atramedes = {row["route_node_id"]: row for row in _routes(manifests, DIAGNOSTIC_IDS["atramedes"])}
    assert atramedes["bwd.atramedes.north_spirits"]["pack_target_entries"] == [43122, 43125, 43128, 43129]
    assert atramedes["bwd.atramedes.south_spirits"]["pack_target_entries"] == [43119, 43126, 43127, 43130]
    assert atramedes["bwd.atramedes.bell"]["interaction_contract"] == {
        "action": "gameobject_use",
        "entry": 204276,
    }
    assert atramedes["bwd.atramedes.intro_wait"]["completion_contract"]["kind"] == "creature_grounded_aggressive_or_engaged"

    chimaeron = {row["route_node_id"]: row for row in _routes(manifests, DIAGNOSTIC_IDS["chimaeron"])}
    assert chimaeron["bwd.chimaeron.finkle"]["interaction_contract"] == {
        "action": "gossip_select_sequence",
        "entry": 44202,
        "menus": [11812, 11834, 11835, 11836, 11837],
        "option": 0,
    }
    assert chimaeron["bwd.chimaeron.finkle"]["completion_contract"] == {
        "kind": "aura_present",
        "entry": 44418,
        "spell_id": 82705,
    }
    assert chimaeron["bwd.chimaeron.wake_wait"]["completion_contract"]["kind"] == "creature_aggressive_with_victim"


def test_declared_route_node_ids_are_strict_and_fail_closed():
    config = _config()
    canonical = next(row for row in config["scenarios"] if row["id"] == CANONICAL_ID)
    canonical["route"][0]["node_id"] = "BWD invalid node"
    try:
        build_manifests(
            config,
            {"all_ready": True, "scenarios": []},
            {"all_passed": True},
            json.loads(SHARD_FIXTURE.read_text(encoding="utf-8")),
        )
    except ValueError as exc:
        assert "route_node_id_invalid" in str(exc)
    else:
        raise AssertionError("malformed node id was accepted")


def test_runtime_profiles_select_only_the_matching_diagnostic_scenario():
    payload = json.loads(PROFILE_MANIFEST.read_text(encoding="utf-8"))
    profiles = {row["name"]: row for row in payload["profiles"]}
    for scenario_id in DIAGNOSTIC_IDS.values():
        profile = profiles[scenario_id]
        route = profile["validation_route"]
        assert route["scenario_id"] == scenario_id
        assert route["manifest_path"] == "dataset/validation_scenarios/validation_routes.jsonl"
        assert profile["pool_tag_filter"] == scenario_id
        assert profile["diagnostic_only"] is True
        assert profile["diagnostic_parent_scenario_id"] == CANONICAL_ID
        assert profile["prerequisite_contract"]["certifies_predecessors"] is False
    assert len({profiles[scenario_id]["pool_tag_filter"] for scenario_id in DIAGNOSTIC_IDS.values()}) == 6


def test_manifest_config_selects_exact_magmaw_profile_instead_of_base_stonecore(tmp_path: Path):
    route = _routes(_manifests(), DIAGNOSTIC_IDS["magmaw"])[0]
    base = tmp_path / "worldserver.conf"
    base.write_text('BotWorld.AutoStart = 1\nBotWorld.RuntimeProfile = "stonecore_5n"\n', encoding="utf-8")
    manifest = tmp_path / "validation_route_manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    generated = write_validation_config(
        base,
        tmp_path / "run",
        pool_tag=DIAGNOSTIC_IDS["magmaw"],
        validation_route=route,
        validation_route_manifest_path=manifest,
    )
    text = generated.read_text(encoding="utf-8")
    assert f'BotWorld.RuntimeProfile = "{DIAGNOSTIC_IDS["magmaw"]}"' in text
    assert 'BotWorld.RuntimeProfile = "stonecore_5n"' not in text


def test_manifest_config_cannot_override_empty_calibration_controller(tmp_path: Path):
    route = _routes(_manifests(), DIAGNOSTIC_IDS["magmaw"])[0]
    base = tmp_path / "worldserver.conf"
    base.write_text(
        'BotWorld.AutoStart = 0\nBotWorld.RuntimeProfile = "stonecore_5n"\n'
        "BotWorld.TargetPopulation = 5\nBotWorld.ValidationRoute.Enable = 1\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "validation_route_manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    generated = write_validation_config(
        base,
        tmp_path / "run",
        pool_tag=DIAGNOSTIC_IDS["magmaw"],
        validation_route=route,
        validation_route_manifest_path=manifest,
        calibration_only=True,
    )
    text = generated.read_text(encoding="utf-8")
    assert 'BotWorld.RuntimeProfile = ""' in text
    assert f'BotWorld.RuntimeProfile = "{DIAGNOSTIC_IDS["magmaw"]}"' not in text
    assert "BotWorld.TargetPopulation = 0" in text
    assert "BotWorld.ValidationRoute.Enable = 0" in text
    assert "BotWorld.ValidationRoute.ManifestPath" not in text


def test_manifest_config_preserves_disabled_autostart_for_preparation(tmp_path: Path):
    route = _routes(_manifests(), DIAGNOSTIC_IDS["magmaw"])[0]
    base = tmp_path / "worldserver.conf"
    base.write_text('BotWorld.AutoStart = 1\nBotWorld.RuntimeProfile = "stonecore_5n"\n', encoding="utf-8")
    manifest = tmp_path / "validation_route_manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    generated = write_validation_config(
        base,
        tmp_path / "run",
        pool_tag=DIAGNOSTIC_IDS["magmaw"],
        validation_route=route,
        validation_route_manifest_path=manifest,
        autostart=False,
    )
    text = generated.read_text(encoding="utf-8")
    assert "BotWorld.AutoStart = 0" in text
    assert f'BotWorld.RuntimeProfile = "{DIAGNOSTIC_IDS["magmaw"]}"' in text

def test_live_report_builder_keeps_all_seven_bwd_route_partitions_distinct(tmp_path: Path):
    manifests = _manifests()
    bwd_ids = [CANONICAL_ID, *DIAGNOSTIC_IDS.values()]
    scenario_dir = tmp_path / "validation_scenarios"
    scenario_dir.mkdir()
    scenarios = [row for row in manifests["validation_scenarios"] if row["scenario_id"] in bwd_ids]
    routes = [row for row in manifests["validation_routes"] if row["scenario_id"] in bwd_ids]
    (scenario_dir / "validation_scenarios.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in scenarios),
        encoding="utf-8",
    )
    (scenario_dir / "validation_routes.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in routes),
        encoding="utf-8",
    )
    (scenario_dir / "validation_mechanics.jsonl").write_text("", encoding="utf-8")

    # A context-free report is intentionally reused as a smoke input for every
    # selected scenario; the builder must still derive each route partition
    # from its own scenario ID and never merge the seven contracts.
    reports = build_reports(
        {
            "schema": "bot_live_validation_report_v1",
            "validation_context": {},
            "trace": {},
            "evidence": {},
            "stages": [],
        },
        scenario_dir,
    )
    assert set(reports) == set(bwd_ids)
    assert reports[CANONICAL_ID]["expected_bosses"] == 6
    assert reports[CANONICAL_ID]["diagnostic_only"] is False
    for scenario_id in DIAGNOSTIC_IDS.values():
        report = reports[scenario_id]
        assert report["diagnostic_only"] is True
        assert report["runtime_profile_id"] == scenario_id
        assert report["diagnostic_parent_scenario_id"] == CANONICAL_ID
        assert report["certifies_predecessors"] is False
        assert report["expected_bosses"] == 1
        assert all(
            str(row["route_node_id"]) in {str(route["route_node_id"]) for route in routes if route["scenario_id"] == scenario_id}
            for row in report["expected_route_evidence"]
        )
