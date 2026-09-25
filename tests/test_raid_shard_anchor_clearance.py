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


def _check(config: dict, creatures: dict, hostile: set[int]) -> dict:
    return clearance.check_anchor_clearance(config, creatures, hostile)


def _scenario(config: dict, scenario_id: str) -> dict:
    return next(row for row in clearance.scenarios(config) if row["id"] == scenario_id)


def _node(scenario: dict, node_id: str) -> dict:
    return next(step for step in scenario["route"] if step.get("node_id") == node_id)


def _spawn(creatures: dict, entry: int, map_id: int = 669) -> dict:
    spawn = next(row for row in creatures[entry]["spawns"] if row["map_id"] == map_id)
    return {"map_id": map_id, "x": spawn["x"], "y": spawn["y"], "z": spawn["z"], "o": 0.0}


def test_every_current_anchor_is_clear_or_explicitly_exempted(creatures, hostile):
    report = _check(CONFIG, creatures, hostile)
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
    assert anchors == {"start_position": 0, "bwd.omnotron.regroup": 0}
