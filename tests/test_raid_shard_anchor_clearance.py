"""Route anchors stand clear of later packs in every scenario (round 3, universal for raids and dungeons)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.raid_program import raid_shard_anchor_clearance as clearance

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text(encoding="utf-8"))
ACCEPTED_ROWS = {"blackwing_descent_10n_magmaw_diagnostic", "stonecore_5n", "stonecore_5h"}

pytestmark = pytest.mark.skipif(
    not clearance.CREATURES.is_file() or not clearance.FACTION_TEMPLATE_DBC.is_file(),
    reason="world knowledge or client DBCs not hydrated")


@pytest.fixture(scope="module")
def creatures() -> dict:
    return clearance.load_creatures()


@pytest.fixture(scope="module")
def hostile() -> set[int]:
    return clearance.hostile_faction_templates()


@pytest.fixture(scope="module")
def world() -> dict | None:
    return clearance.load_world() if clearance.TDB_WORLD.is_file() else None


def _check(config: dict, creatures: dict, hostile: set[int], world: dict | None = None) -> dict:
    return clearance.check_anchor_clearance(config, creatures, hostile, world=world)


def _scenario(config: dict, scenario_id: str) -> dict:
    return next(row for row in clearance.scenarios(config) if row["id"] == scenario_id)


def _node(scenario: dict, node_id: str) -> dict:
    return next(step for step in scenario["route"] if step.get("node_id") == node_id)


def _spawn(creatures: dict, entry: int, map_id: int = 669) -> dict:
    spawn = next(row for row in creatures[entry]["spawns"] if row["map_id"] == map_id)
    return {"map_id": map_id, "x": spawn["x"], "y": spawn["y"], "z": spawn["z"], "o": 0.0}


def test_every_current_anchor_is_clear_or_explicitly_exempted(creatures, hostile, world):
    report = _check(CONFIG, creatures, hostile, world)
    assert report["all_passed"], report["violations"] or report["unused_exemptions"]
    assert report["violations"] == [] and report["unused_exemptions"] == []
    assert report["anchors_checked"] >= 50
    # Every scenario is covered, c0 and full-raid rows included.
    covered = {row["scenario_id"] for row in report["exempted"]} | {row["id"] for row in clearance.scenarios(CONFIG)}
    assert {"blackwing_descent_10n_full_c0", "blackwing_descent_10n_omnotron_c0_diagnostic"} <= covered
    # Every exemption has a reason; accepted-row findings are reported, never moved.
    assert all(row["reason"] for row in report["exempted"])
    accepted = {(row["scenario_id"], row["anchor"], row["entry"]) for row in report["exempted"]
                if row["scenario_id"] in ACCEPTED_ROWS}
    assert accepted == {
        ("blackwing_descent_10n_magmaw_diagnostic", "bwd.magmaw.chainwielder:patrol_wait_anchor", 42649),
        ("stonecore_5n", "step10", 42808), ("stonecore_5h", "step10", 42808)}
    assert all(clearance.ACCEPTED_ROW_NOTE in row["reason"] for row in report["exempted"]
               if row["scenario_id"] in ACCEPTED_ROWS)
    # Script-summoned creatures have no spawn row to check against.
    assert {41442, 41376, 41270, 42180, 43214} <= set(report["entries_without_db_spawn"])


@pytest.mark.parametrize("scenario_id,edit,entry", [
    # Round 2: the Omnotron c0 raid was provisioned on Golem Sentry spawn 250049.
    ("blackwing_descent_10n_omnotron_c0_diagnostic", "start_on:42800", 42800),
    ("blackwing_descent_10n_omnotron_diagnostic", "regroup_on:bwd.omnotron.regroup:42800", 42800),
    # Round 2: the Atramedes shards started inside the north spirit pack.
    ("blackwing_descent_10n_atramedes_c0_diagnostic", "start_on:43128", 43128),
    # Round 1: the legacy Maloriak regroup stood on a Drakeadon Mongrel.
    ("blackwing_descent_10n_maloriak_c0_diagnostic", "regroup_on:bwd.maloriak.regroup:42803", 42803),
    # A dungeon row is held to the same rule.
    ("stonecore_5h", "start_on_map725:42808", 42808),
])
def test_an_anchor_inside_a_later_pack_is_refused(creatures, hostile, scenario_id, edit, entry):
    config = copy.deepcopy(CONFIG)
    scenario = _scenario(config, scenario_id)
    kind, *rest = edit.split(":")
    if kind == "start_on":
        scenario["start_position"] = _spawn(creatures, int(rest[0]))
    elif kind == "start_on_map725":
        scenario["start_position"] = _spawn(creatures, int(rest[0]), 725)
    else:
        node, target = rest
        _node(scenario, node).update({axis: value for axis, value in _spawn(creatures, int(target)).items()
                                      if axis in ("x", "y", "z")})
    report = _check(config, creatures, hostile)
    assert not report["all_passed"]
    assert any(row["scenario_id"] == scenario_id and row["entry"] == entry and row["yards"] < 1.0
               for row in report["violations"])


def test_an_exemption_holds_only_at_its_reviewed_point(creatures, hostile):
    config = copy.deepcopy(CONFIG)
    regroup = _node(_scenario(config, "blackwing_descent_10n_chimaeron_c0_diagnostic"), "bwd.chimaeron.regroup")
    regroup["x"] = float(regroup["x"]) + 1.0
    report = _check(config, creatures, hostile)
    assert any(row["scenario_id"] == "blackwing_descent_10n_chimaeron_c0_diagnostic"
               and row["anchor"] == "bwd.chimaeron.regroup" and row["entry"] == 43296
               for row in report["violations"])


def test_only_hostile_pack_and_target_entries_count(creatures, hostile):
    # Gameobjects (the Atramedes gong 204276) and friendly gossip NPCs (Finkle Einhorn 44202) are never packs.
    atramedes = _scenario(CONFIG, "blackwing_descent_10n_atramedes_c0_diagnostic")
    entries = set().union(*(clearance.node_entries(step) for step in atramedes["route"]))
    assert 204276 not in entries and 43119 in entries and 41442 in entries
    chimaeron = _scenario(CONFIG, "blackwing_descent_10n_chimaeron_c0_diagnostic")
    assert 44202 not in set().union(*(clearance.node_entries(step) for step in chimaeron["route"]))
    assert int(creatures[42800]["faction"]) in hostile
    # Anchors of a node only answer to that node and the ones after it.
    omnotron = _scenario(CONFIG, "blackwing_descent_10n_omnotron_c0_diagnostic")
    anchors = {key: first for key, first, _point in clearance.scenario_anchors(omnotron)}
    # A staging anchor (navigation_anchor) stands before its node's fight: later nodes only.
    assert anchors == {"start_position": 0, "bwd.omnotron.regroup": 0, "bwd.omnotron.encounter:navigation_anchor": 3}


NEFARIAN_C0 = "blackwing_descent_10n_nefarian_c0_diagnostic"
ORB = {"map_id": 669, "x": -27.84375, "y": -224.4774, "z": 63.30268, "o": 6.265733}
IVOROC, NORTH_PATROL, LAB_PATROL = 250108, 250116, 250117


def _needs_world(world):
    if world is None:
        pytest.skip("TDB world dump not hydrated")


def test_the_round2_nefarian_orb_start_is_refused_by_the_non_target_rule(creatures, hostile, world):
    """Round 3 (T): the c0 raid spawned at the Orb inside Ivoroc's wander and two patrol turnarounds."""
    _needs_world(world)
    config = copy.deepcopy(CONFIG)
    nefarian = _scenario(config, NEFARIAN_C0)
    nefarian["start_position"] = dict(ORB)
    nefarian["route"] = [step for step in nefarian["route"]
                         if not step["node_id"].startswith(("bwd.maloriak.", "bwd.lower_hall."))]
    report = _check(config, creatures, hostile, world)
    found = {(row["anchor"], row["guid"]): row["yards"] for row in report["violations"]
             if row["rule"] == "non_target_hostile" and row["scenario_id"] == NEFARIAN_C0}
    assert {("start_position", IVOROC), ("start_position", NORTH_PATROL), ("start_position", LAB_PATROL),
            ("bwd.nefarian.orb_regroup", IVOROC)} <= set(found)
    assert found[("start_position", IVOROC)] < 10.0  # 15.1 yd from the Orb, wandering 10 yd
    assert 15.0 < found[("start_position", NORTH_PATROL)] < 17.0  # its path turns 16.3 yd from the Orb
    # Rule 1 alone could not see it: none of these creatures is a node target.
    assert not any(row["scenario_id"] == NEFARIAN_C0 for row in _check(config, creatures, hostile)["violations"])


def test_a_node_that_clears_the_pack_first_satisfies_the_non_target_rule(creatures, hostile, world):
    _needs_world(world)
    config = copy.deepcopy(CONFIG)
    full = _scenario(config, "blackwing_descent_10n")
    full["route"] = [step for step in full["route"] if not step["node_id"].startswith("bwd.lower_hall.")]
    report = _check(config, creatures, hostile, world)
    guids = {row["guid"] for row in report["violations"]
             if row["scenario_id"] == "blackwing_descent_10n" and row["anchor"] == "bwd.nefarian.orb_regroup"}
    # bwd.maloriak.lab_trash clears the laboratory patrol (source and formation) long before the Orb.
    assert IVOROC in guids and NORTH_PATROL in guids and LAB_PATROL not in guids
    assert 250120 in guids  # a formation member walks its leader's path


def test_world_reach_and_aggro_filters(world, hostile):
    _needs_world(world)
    spawns = {spawn.guid: spawn for spawn in world["spawns"]}
    north, member, ivoroc = spawns[NORTH_PATROL], spawns[250120], spawns[IVOROC]
    assert len(north.reach) == 13 and member.leader == NORTH_PATROL and member.reach[1:] == north.reach[1:]
    assert ivoroc.slack == 10.0 and len(ivoroc.reach) == 1
    stalker = next(spawn for spawn in world["spawns"] if spawn.entry == 35592)
    assert not clearance.can_aggro_players(stalker, world["templates"][35592], hostile)
    assert clearance.can_aggro_players(ivoroc, world["templates"][42767], hostile)
    lab_trash = _node(_scenario(CONFIG, "blackwing_descent_10n"), "bwd.maloriak.lab_trash")
    assert clearance.cleared_by(lab_trash, spawns[LAB_PATROL]) and clearance.cleared_by(lab_trash, spawns[250118])
    assert not clearance.cleared_by(lab_trash, north)


def _full(config: dict, scenario_id: str = "blackwing_descent_10n") -> dict:
    return _scenario(config, scenario_id)


@pytest.mark.parametrize("scenario_id", ["blackwing_descent_10n", "blackwing_descent_10n_full_c0"])
def test_the_full_route_clears_the_hall_before_crossing_it(creatures, hostile, world, scenario_id):
    _needs_world(world)
    nodes = [step["node_id"] for step in _full(CONFIG, scenario_id)["route"]]
    maloriak = nodes.index("bwd.maloriak.encounter")
    assert nodes[maloriak + 1] == HALL and nodes.index(HALL) < nodes.index("bwd.atramedes.north_spirits")
    report = _check(CONFIG, creatures, hostile, world)
    assert report["path_violations"] == [] and report["path_segments_checked"] >= 100
    assert {row["to"] for row in report["path_exempted"]} == {
        "bwd.chimaeron.regroup", "bwd.chimaeron.finkle", "bwd.chimaeron.wake_wait"}
    assert set(report["path_unchecked_scenarios"]["scenarios"]) == {"stonecore_5n", "stonecore_5h"}


HALL = "bwd.lower_hall.central_hall"
# The round-3/4 split of the hall node: Ivoroc alone at his spawn, and the north patrol keyed on its Mongrel.
SPLIT_IVOROC = {"node_id": "bwd.lower_hall.ivoroc", "kind": "trash", "x": -17.5573, "y": -224.347, "z": 74.2971,
                "source_entry": 42767, "source_guid": "250108", "pack_target_entries": [42767],
                "cluster_radius_yards": 20.0}
SPLIT_NORTH_PATROL = {"node_id": "bwd.lower_hall.north_patrol", "kind": "trash", "x": -65.1896, "y": -150.167,
                      "z": 64.1058, "source_entry": 46083, "source_guid": "250120", "pack_target_entries": [46083],
                      "cluster_radius_yards": 40.0}


@pytest.mark.parametrize("order", ["ivoroc_first", "after_chimaeron"])
def test_a_walk_past_a_live_patrol_is_refused(hostile, world, order):
    """Split into Ivoroc and the north patrol, a walk to Ivoroc first passes the patrol's turn 8 yd from him."""
    _needs_world(world)
    config = copy.deepcopy(CONFIG)
    full = _full(config)
    rows = [row for row in full["route"] if row["node_id"] != HALL]
    split = [dict(SPLIT_IVOROC), dict(SPLIT_NORTH_PATROL)]
    if order == "ivoroc_first":
        maloriak = next(index for index, row in enumerate(rows) if row["node_id"] == "bwd.maloriak.encounter")
        full["route"] = rows[:maloriak + 1] + split + rows[maloriak + 1:]
    else:  # round-3 first cut: the hall nodes just before the Orb, Ivoroc first
        orb = next(index for index, row in enumerate(rows) if row["node_id"] == "bwd.nefarian.orb_regroup")
        full["route"] = rows[:orb] + split + rows[orb:]
    report = clearance.check_route_paths({"scenarios": [full]}, world, hostile)
    walked_past = {(row["to"], row["guid"]) for row in report["path_violations"]}
    assert ("bwd.lower_hall.ivoroc", NORTH_PATROL) in walked_past  # its path turns 8 yd from Ivoroc


def test_patrols_are_measured_to_their_walked_segments_including_the_closing_leg(world):
    _needs_world(world)
    north = next(spawn for spawn in world["spawns"] if spawn.guid == NORTH_PATROL)
    waypoints = north.reach[1:]
    assert north.segments[0] == (north.point, waypoints[0])
    assert north.segments[-1] == (waypoints[-1], waypoints[0])  # the loop closes back to its first point
    start, end = north.segments[-1]
    middle = tuple((start[axis] + end[axis]) / 2 for axis in range(3))
    assert clearance.spawn_distance(middle, north) < 0.01
    assert min(clearance.math.dist(middle, place) for place in north.reach) > 5.0  # vertices alone miss it
    # Creature::CanStartAttack adds the player's reach; half a sampling step covers the sample gap.
    assert clearance.PATH_AGGRO_YARDS >= 15.0 + 1.5 + clearance.PATH_SAMPLE_YARDS / 2


def test_the_atramedes_start_clears_every_spirit_without_an_exemption(creatures, hostile, world):
    starts = {row["id"]: row["start_position"] for row in clearance.scenarios(CONFIG) if "atramedes" in row["id"]}
    assert starts["blackwing_descent_10n_atramedes_c0_diagnostic"] == starts["blackwing_descent_10n_atramedes_diagnostic"]
    assert (starts["blackwing_descent_10n_atramedes_c0_diagnostic"]["x"],
            starts["blackwing_descent_10n_atramedes_c0_diagnostic"]["y"]) == (140.0, -224.5)
    assert not any(row.anchor == "start_position" and row.entry in (43122, 43130) for row in clearance.EXEMPTIONS)
    report = _check(CONFIG, creatures, hostile, world)
    assert not [row for row in report["violations"] + report["exempted"]
                if "atramedes" in row["scenario_id"] and row["anchor"] == "start_position"]


ROUND3_NORTH_PATROL = {"x": -58.5521, "y": -146.793, "z": 63.6199, "o": 1.41372, "source_entry": 42802,
                       "source_guid": "250116", "pack_target_entries": [42802, 46083, 42767]}


def _round3_north_patrol(config: dict, scenario_id: str) -> None:
    _node(_scenario(config, scenario_id), HALL).update(copy.deepcopy(ROUND3_NORTH_PATROL))


@pytest.mark.parametrize("scenario_id", [NEFARIAN_C0, "blackwing_descent_10n_nefarian_diagnostic",
                                         "blackwing_descent_10n", "blackwing_descent_10n_full_c0"])
def test_the_round3_north_patrol_key_is_refused_by_the_future_guard_rule(scenario_id):
    """Round 3: a later node named the lab patrol Slayer's entry, so the guard froze bwd.maloriak.lab_trash."""
    config = copy.deepcopy(CONFIG)
    _round3_north_patrol(config, scenario_id)
    report = clearance.check_future_guard(config)
    assert {"rule": "future_guard_overlap", "scenario_id": scenario_id, "node": "bwd.maloriak.lab_trash",
            "later_node": HALL, "entry": 42802} in report["guard_violations"]
    assert clearance.check_future_guard(CONFIG)["guard_violations"] == []


def test_the_future_guard_rule_mirrors_the_runtime_fields():
    step = {"kind": "boss", "source_entry": 1, "opener_target_entry": 2, "alternate_target_entries": [3],
            "add_target_entries": [4], "pack_target_entries": [5], "scripted_event_entries": [6],
            "mechanic_contract": {"target_entries": [7]}, "source_guid": "8", "split_source_guids": [9]}
    assert clearance.guard_entries(step) == {1, 2, 3, 4, 5, 6, 7}
    assert clearance.guard_spawns(step) == {8, 9}
    assert clearance.guard_entries({**step, "kind": "interaction"}) == set()
    route = [{"kind": "trash", "node_id": "a", "source_entry": 10, "source_guid": "8"},
             {"kind": "regroup", "node_id": "b", "source_entry": 10},
             dict(step, node_id="c")]
    found = clearance.check_future_guard({"scenarios": [{"id": "s", "route": route}]})["guard_violations"]
    assert found == [{"rule": "future_guard_overlap", "scenario_id": "s", "node": "a", "later_node": "c", "spawn": 8}]
    # A boss node as the current node is not guarded; a regroup naming an entry protects nothing.
    route = [dict(step, node_id="boss"), {"kind": "trash", "node_id": "t", "source_entry": 1}]
    assert clearance.check_future_guard({"scenarios": [{"id": "s", "route": route}]})["guard_violations"] == []


def test_the_future_guard_rule_counts_the_formation_its_source_pulls(world):
    """Keyed on Mongrel 250120, the hall node still fights Slayer 250116: a later 42802 node is refused."""
    _needs_world(world)
    config = copy.deepcopy(CONFIG)
    nefarian = _scenario(config, NEFARIAN_C0)
    _node(nefarian, "bwd.nefarian.encounter")["alternate_target_entries"] = [42802]
    assert clearance.check_future_guard(config)["guard_violations"] == [
        {"rule": "future_guard_overlap", "scenario_id": NEFARIAN_C0, "node": "bwd.maloriak.lab_trash",
         "later_node": "bwd.nefarian.encounter", "entry": 42802}]
    found = clearance.check_future_guard(config, world)["guard_violations"]
    assert {"rule": "future_guard_overlap", "scenario_id": NEFARIAN_C0, "node": HALL,
            "later_node": "bwd.nefarian.encounter", "entry": 42802} in found


def _formation(guid: int, leader: int, group_ai: int) -> clearance.WorldSpawn:
    return clearance.WorldSpawn(guid=guid, entry=guid, map_id=669, point=(0.0, 0.0, 0.0), reach=((0.0, 0.0, 0.0),),
                                slack=0.0, leader=leader, unit_flags=0, group_ai=group_ai)


def test_formation_engagement_follows_creature_group_ai():
    leader, member, other = _formation(1, 1, 515), _formation(2, 1, 515), _formation(3, 1, 515)
    loner = _formation(4, 4, 0)
    # GroupAI 515 reads as uint8 3: every member assists every member.
    assert all(clearance.formation_engages(pulled, spawn)
               for pulled in (leader, member) for spawn in (leader, member, other))
    assert not clearance.formation_engages(member, loner) and clearance.formation_engages(loner, loner)
    leader_only = _formation(2, 1, clearance.FORMATION_LEADER_ASSISTS_MEMBER)
    assert clearance.formation_engages(leader_only, leader) and not clearance.formation_engages(leader_only, other)
    assert not clearance.formation_engages(_formation(2, 1, clearance.FORMATION_MEMBERS_ASSIST_LEADER), leader)
    assert not clearance.formation_engages(_formation(1, 1, 0x200), member)  # idle-in-formation only


def test_the_central_hall_node_clears_the_north_patrol_and_ivoroc_together(world):
    """Round 5 (r04 Nefarian c0): a straggler walking to the north patrol passed under Ivoroc and pulled him.
    One node now owns both; it is keyed on Mongrel 250120 so no later node names the Slayer entry 42802."""
    _needs_world(world)
    spawns = world["by_guid"]
    for scenario_id in (NEFARIAN_C0, "blackwing_descent_10n_nefarian_diagnostic", "blackwing_descent_10n",
                        "blackwing_descent_10n_full_c0"):
        route = _scenario(CONFIG, scenario_id)["route"]
        assert not any(step["node_id"] in ("bwd.lower_hall.north_patrol", "bwd.lower_hall.ivoroc") for step in route)
        hall = _node(_scenario(CONFIG, scenario_id), HALL)
        assert (hall["source_entry"], hall["source_guid"], hall["pack_target_entries"]) == (46083, "250120", [46083, 42767])
        assert (hall["x"], hall["y"], hall["z"]) == (-33.0668, -223.2, 63.4878)  # the corridor corner under Ivoroc
        assert all(clearance.cleared_by(hall, spawns[guid], world) for guid in (NORTH_PATROL, 250120, 250121, IVOROC))
        assert not clearance.cleared_by(hall, spawns[NORTH_PATROL])  # the entry alone does not cover the Slayer
        assert clearance.math.dist((hall["x"], hall["y"], hall["z"]), spawns[IVOROC].point) < 20.0
        assert clearance.spawn_distance((hall["x"], hall["y"], hall["z"]), spawns[NORTH_PATROL]) < hall["cluster_radius_yards"]


DRAKE_REACH_3D = 16.5
PYRECRAW, PYRECRAW_ENTRY, MAIMGOR, MAIMGOR_ENTRY = 250107, 42764, 250109, 42768
FULL_ROUTES = ("blackwing_descent_10n", "blackwing_descent_10n_full_c0")
NEFARIAN_ROUTES = ("blackwing_descent_10n_nefarian_diagnostic", NEFARIAN_C0)
DRAKE_ROUTES = FULL_ROUTES + NEFARIAN_ROUTES
# node, guid, entry, the node after it (Maimgor's: the Atramedes wing in the full raid, the Orb in the Nefarian shard).
DRAKE_NODES = (
    ("bwd.north_corridor.pyrecraw", PYRECRAW, PYRECRAW_ENTRY, {route: "bwd.south_corridor.maimgor" for route in DRAKE_ROUTES}),
    ("bwd.south_corridor.maimgor", MAIMGOR, MAIMGOR_ENTRY,
     # Round 10: the canonical full raid switches the druid to Balance before the Atramedes wing, at Maimgor's anchor.
     {"blackwing_descent_10n": "bwd.atramedes.north_spirits",
      "blackwing_descent_10n_full_c0": "bwd.spec_switch.atramedes",
      **{route: "bwd.nefarian.orb_regroup" for route in NEFARIAN_ROUTES}}),
)


def test_the_hovering_drakes_are_cleared_right_after_the_central_hall_wherever_a_walk_passes_them(hostile, world):
    """Round 5 review: the Atramedes-to-Chimaeron walk passed the hovering Pyrecraw, whom no node cleared. Round 6
    (r05 Nefarian c0): the descent approach from the central hall runs through his corridor and he engaged the
    hunter at the descent; from the Orb point it runs 8.6 yd under Maimgor instead. The full routes and the
    Nefarian shard clear Pyrecraw and then Maimgor right after the central hall, each from the floor inside his
    reach, so the Orb, Nefarian's intro, either descent approach and the Atramedes wing see no live drake. The
    Chimaeron shard's walks stay 145 yd from Pyrecraw, and the other boss shards never walk past either."""
    _needs_world(world)
    for node_id, guid, entry, following in DRAKE_NODES:
        spawn = world["by_guid"][guid]
        rows = []
        for scenario_id in DRAKE_ROUTES:
            route = _scenario(CONFIG, scenario_id)["route"]
            ids = [step["node_id"] for step in route]
            index = ids.index(node_id)
            assert ids[index + 1] == following[scenario_id]
            assert ids.index("bwd.lower_hall.central_hall") < ids.index("bwd.north_corridor.pyrecraw") == \
                ids.index("bwd.south_corridor.maimgor") - 1
            assert all(not step["node_id"].startswith(("bwd.atramedes.", "bwd.chimaeron.", "bwd.nefarian."))
                       for step in route[:index])
            node = route[index]
            rows.append({key: value for key, value in node.items() if key != "step"})
            assert (node["source_entry"], node["source_guid"], node["pack_target_entries"]) == (entry, str(guid), [entry])
            assert node["completion_policy"] == "cluster_clear_after_pull" and node["cluster_radius_yards"] >= 25.0
            anchor = (node["x"], node["y"], node["z"])
            # On the floor under him: arrival is inside his reach wherever his random movement took him.
            horizontal = clearance.math.dist(anchor[:2], spawn.point[:2]) + spawn.slack
            assert clearance.math.hypot(horizontal, spawn.point[2] - anchor[2]) < DRAKE_REACH_3D
            assert node["cluster_radius_yards"] >= spawn.slack + 15.0
            assert clearance.cleared_by(node, spawn, world)
            others = [other.guid for other in world["spawns"] if other.map_id == 669 and other.guid != guid
                      and clearance.can_aggro_players(other, world["templates"].get(other.entry) or {}, hostile)
                      and clearance.spawn_distance(anchor, other) < node["cluster_radius_yards"]]
            assert others == []
        assert all(row == rows[0] for row in rows)  # one row: the composer takes the full raid's from the Nefarian shard
        for row in clearance.scenarios(CONFIG):
            if row["id"].startswith("blackwing_descent_10n") and row["id"] not in DRAKE_ROUTES:
                assert not any(step.get("source_guid") == str(guid)
                               or entry in (step.get("pack_target_entries") or []) for step in row["route"])
    assert world["by_guid"][MAIMGOR].slack == 0.0 and world["by_guid"][PYRECRAW].slack == 10.0  # static, wanders


OMNOTRON_C0 = "blackwing_descent_10n_omnotron_c0_diagnostic"
OMNOTRON_STAGING = {"x": -336.08, "y": -356.46, "z": 213.871, "o": 4.972}


def test_every_staging_anchor_is_checked(creatures, hostile, world):
    """Round 4 review: the Omnotron staging navigation_anchor answers to the anchor rules too."""
    staged = {(row["id"], key) for row in clearance.scenarios(CONFIG)
              for key, _first, _point in clearance.scenario_anchors(row) if key.endswith(":navigation_anchor")}
    assert {(scenario_id, "bwd.omnotron.encounter:navigation_anchor") for scenario_id in (
        OMNOTRON_C0, "blackwing_descent_10n_omnotron_diagnostic", "blackwing_descent_10n",
        "blackwing_descent_10n_full_c0")} <= staged
    assert ("stonecore_5n", "step17:navigation_anchor") in staged
    encounter = _node(_scenario(CONFIG, OMNOTRON_C0), "bwd.omnotron.encounter")
    assert encounter["navigation_anchor"] == OMNOTRON_STAGING
    report = _check(CONFIG, creatures, hostile, world)
    assert report["all_passed"] and report["anchors_checked"] >= 60


def test_a_staging_anchor_on_a_live_hostile_is_refused(creatures, hostile, world):
    _needs_world(world)
    config = copy.deepcopy(CONFIG)
    encounter = _node(_scenario(config, OMNOTRON_C0), "bwd.omnotron.encounter")
    encounter["navigation_anchor"] = {"x": -17.5573, "y": -224.347, "z": 74.2971, "o": 0.0}  # on Ivoroc
    found = {(row["anchor"], row["guid"]) for row in _check(config, creatures, hostile, world)["violations"]
             if row["scenario_id"] == OMNOTRON_C0 and row["rule"] == "non_target_hostile"}
    assert ("bwd.omnotron.encounter:navigation_anchor", IVOROC) in found
