"""Route anchors must not stand inside a later pack: a data check for every raid and dungeon scenario.

Round 2 provisioned the Omnotron c0 raid on Golem Sentry spawn 250049 (the next node's pack) and the
Atramedes shards inside the north spirit pack, so both fights started at login. This check keeps every
scenario of experiments/configs/validation_scenarios_cata_001.json (legacy, c0 and full rows alike) clear
of that class of defect:

- anchors: the scenario `start_position`, the position of every `regroup` node, and every node's
  `patrol_wait_anchor` (a hold point);
- hostiles: every spawn on the scenario's map of a creature whose entry is a pack or target entry
  (`source_entry`, `pack_target_entries`, `add_target_entries`, `alternate_target_entries`,
  `opener_target_entry`) of the anchor's node or any later node of the scenario, and whose faction
  template is hostile to players (FactionTemplate.dbc EnemyGroup player/Alliance/Horde bits). Spawns
  come from the world DB creature table as extracted into dataset/world_knowledge/npcs.jsonl. Creatures
  that scripts summon (Atramedes, Nefarian, Onyxia, the Omnotron golems, Slabhide, Corborus) have no
  spawn row and are listed as `entries_without_db_spawn`, not as failures;
- rule: the 3D distance is at least MIN_CLEARANCE_YARDS. Creature::GetAttackDistance gives a creature
  of level 85 or more `15 - CombatReach` yards against a level-85 player (the expansion cap removes the
  level bonus), so 30 yards keeps at least 15 yards of margin.

An anchor may stand closer only with an explicit exemption (EXEMPTIONS) that names the node anchor,
the creature entry and the reason, e.g. the Chimaeron nodes stand on the passive sleeping boss by design.
Accepted rows (Magmaw, Stonecore) are never moved by this check; a finding there is exempted and reported.

    pixi run python -m tools.raid_program.raid_shard_anchor_clearance
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_CONFIG = REPO_ROOT / "experiments/configs/validation_scenarios_cata_001.json"
# Every creature entry with spawns (mobs.jsonl drops gossip humanoids such as High Priestess Azil).
CREATURES = REPO_ROOT / "dataset/world_knowledge/npcs.jsonl"
FACTION_TEMPLATE_DBC = REPO_ROOT / "data/dbc/enUS/FactionTemplate.dbc"
FACTION_TEMPLATE_FMT = "niiiiiiiiiiiii"
FACTION_GROUP_PLAYER_MASKS = 1 | 2 | 4  # FACTION_GROUP_MASK_PLAYER, _ALLIANCE, _HORDE
MIN_CLEARANCE_YARDS = 30.0
SPAWN_LIST_CAP = 64  # extract_world_knowledge keeps at most 64 spawns per entry
# Entries whose extracted spawn list hit the cap, so only 64 spawns are checked (known and reviewed).
KNOWN_TRUNCATED_ENTRIES = {
    42428: "Devout Follower (Stonecore, High Priestess Azil's adds): the 64 extracted spawns are all 82 yd "
           "or more from every Stonecore anchor.",
}
ENTRY_FIELDS = ("source_entry", "opener_target_entry")
ENTRY_LIST_FIELDS = ("pack_target_entries", "add_target_entries", "alternate_target_entries")
HOLD_ANCHOR_FIELDS = ("patrol_wait_anchor",)
# Node kinds whose `source_entry` is a creature the raid fights. Interaction, transport and descent
# nodes name gameobjects, gossip NPCs or scripted event creatures instead.
FIGHT_KINDS = {"trash", "boss"}


@dataclass(frozen=True)
class Exemption:
    """A reviewed anchor that may stand closer to one creature entry: valid only at the recorded point."""
    anchor: str
    entry: int
    point: tuple[float, float, float]
    reason: str
    scenarios: tuple[str, ...] = ()  # empty: every scenario with this anchor


ACCEPTED_ROW_NOTE = "Accepted row, kept byte-identical by policy; reported to the coordinator instead of moved."
EXEMPTIONS: tuple[Exemption, ...] = (
    Exemption("bwd.magmaw.chainwielder:patrol_wait_anchor", 42649, (-346.5827, -83.71657, 213.9893),
              "The patrol wait anchor is where the tank intercepts this node's own Drakonid Chainwielder patrol "
              "(18.7 yd from its spawn), by design. " + ACCEPTED_ROW_NOTE),
    Exemption("step10", 42808, (1412.931, 1170.2, 231.5103),
              "Stonecore east descent shelf regroup: the point is a Stonecore Flayer spawn itself (a second "
              "Flayer spawns 6.1 yd away). " + ACCEPTED_ROW_NOTE,
              ("stonecore_5n", "stonecore_5h")),
    Exemption("start_position", 43122, (150.0, -224.5, 75.0),
              "Round-3 Atramedes start (the proven-walkable bwd.atramedes.regroup floor point) is 27.4 yd from "
              "the Spirit of Corehammer spawn: outside its native aggro radius (Creature::GetAttackDistance: "
              "15 - CombatReach for level 85+ against level 85) but inside the 30 yd policy. Pending review: "
              "(140.0, -224.5, 75.0) clears every spirit spawn by 32.8 yd once its navmesh is confirmed.",
              ("blackwing_descent_10n_atramedes_diagnostic", "blackwing_descent_10n_atramedes_c0_diagnostic")),
    Exemption("start_position", 43130, (150.0, -224.5, 75.0),
              "Round-3 Atramedes start is 26.0 yd from the Spirit of Burningeye spawn; see Spirit of Corehammer.",
              ("blackwing_descent_10n_atramedes_diagnostic", "blackwing_descent_10n_atramedes_c0_diagnostic")),
    Exemption("bwd.chimaeron.regroup", 43296, (-104.738, 20.592, 72.14094),
              "Chimaeron (43296) sleeps passive until Finkle Einhorn's gossip starts the encounter; the regroup, "
              "wake-wait and encounter nodes stand at the boss by design (route_template of the accepted "
              "Chimaeron shard)."),
    Exemption("start_position", 43296, (-104.738, 20.592, 72.14094),
              "The Chimaeron shards start at the passive sleeping boss by design (see bwd.chimaeron.regroup).",
              ("blackwing_descent_10n_chimaeron_diagnostic", "blackwing_descent_10n_chimaeron_c0_diagnostic")),
)


def anchor_key(node_id: str, field: str) -> str:
    return node_id if field == "regroup" else f"{node_id}:{field}"


def hostile_faction_templates(dbc_path: Path = FACTION_TEMPLATE_DBC) -> set[int]:
    from tools.bot_ml.build_validation_provisioning import load_wdbc_values

    return {int(row[0]) for row in load_wdbc_values(Path(dbc_path), FACTION_TEMPLATE_FMT)
            if int(row[5]) & FACTION_GROUP_PLAYER_MASKS}


def load_creatures(path: Path = CREATURES, entries: Iterable[int] | None = None) -> dict[int, dict[str, Any]]:
    wanted = set(entries) if entries is not None else None
    mobs: dict[int, dict[str, Any]] = {}
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            entry = int(row["entry"])
            if wanted is None or entry in wanted:
                mobs[entry] = row
    return mobs


def scenarios(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list(config.get("scenarios") or []) + list(config.get("diagnostic_scenarios") or [])


def node_entries(step: Mapping[str, Any]) -> set[int]:
    entries = {int(step[field]) for field in ENTRY_FIELDS
               if step.get(field) and (field != "source_entry" or step.get("kind") in FIGHT_KINDS)}
    for field in ENTRY_LIST_FIELDS:
        entries.update(int(value) for value in step.get(field) or [] if int(value) > 0)
    return entries


def scenario_anchors(scenario: Mapping[str, Any]) -> list[tuple[str, int, dict[str, float]]]:
    """(anchor key, route index the hostiles start from, point) for every anchor of the scenario."""
    anchors: list[tuple[str, int, dict[str, float]]] = []
    start = scenario.get("start_position")
    if isinstance(start, Mapping) and "x" in start:
        anchors.append(("start_position", 0, dict(start)))
    for index, step in enumerate(scenario.get("route") or []):
        node = str(step.get("node_id") or f"step{step.get('step')}")
        if step.get("kind") == "regroup" and "x" in step:
            anchors.append((anchor_key(node, "regroup"), index, {axis: step[axis] for axis in ("x", "y", "z")}))
        for field in HOLD_ANCHOR_FIELDS:
            if isinstance(step.get(field), Mapping):
                anchors.append((anchor_key(node, field), index, dict(step[field])))
    return anchors


def distance(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    return math.dist([float(left[axis]) for axis in ("x", "y", "z")],
                     [float(right[axis]) for axis in ("x", "y", "z")])


def exemption_for(scenario_id: str, anchor: str, entry: int, point: Mapping[str, Any],
                  exemptions: Iterable[Exemption]) -> Exemption | None:
    """The exemption reviewed for exactly this anchor point; a moved anchor must be reviewed again."""
    at = tuple(float(point[axis]) for axis in ("x", "y", "z"))
    for exemption in exemptions:
        if (exemption.anchor == anchor and exemption.entry == entry
                and all(abs(left - right) <= 0.01 for left, right in zip(at, exemption.point))
                and (not exemption.scenarios or scenario_id in exemption.scenarios)):
            return exemption
    return None


def check_anchor_clearance(config: Mapping[str, Any], mobs: Mapping[int, Mapping[str, Any]],
                           hostile_factions: set[int], *, min_yards: float = MIN_CLEARANCE_YARDS,
                           exemptions: Iterable[Exemption] = EXEMPTIONS) -> dict[str, Any]:
    exemptions = tuple(exemptions)
    violations: list[dict[str, Any]] = []
    exempted: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    no_spawn: set[int] = set()
    used: set[Exemption] = set()
    checked = 0
    for scenario in scenarios(config):
        scenario_id = str(scenario.get("id"))
        map_id = int(scenario.get("map_id") or (scenario.get("start_position") or {}).get("map_id") or 0)
        route = list(scenario.get("route") or [])
        for anchor, first_index, point in scenario_anchors(scenario):
            checked += 1
            entries: dict[int, str] = {}
            for step in route[first_index:]:
                for entry in sorted(node_entries(step)):
                    entries.setdefault(entry, str(step.get("node_id") or step.get("step")))
            for entry, node in sorted(entries.items()):
                mob = mobs.get(entry)
                if mob is None:
                    no_spawn.add(entry)
                    continue
                if int(mob.get("faction") or 0) not in hostile_factions:
                    continue
                spawns = [spawn for spawn in mob.get("spawns") or [] if int(spawn.get("map_id", -1)) == map_id]
                if len(mob.get("spawns") or []) >= SPAWN_LIST_CAP:
                    missing.append({"scenario_id": scenario_id, "anchor": anchor, "entry": entry, "node": node,
                                    "reason": "spawn_list_truncated"})
                for spawn in spawns:
                    yards = distance(point, spawn)
                    if yards >= min_yards:
                        continue
                    finding = {"scenario_id": scenario_id, "anchor": anchor, "entry": entry,
                               "name": mob.get("name"), "node": node, "yards": round(yards, 2),
                               "anchor_point": {axis: point[axis] for axis in ("x", "y", "z")},
                               "spawn": {axis: spawn[axis] for axis in ("x", "y", "z")}}
                    exemption = exemption_for(scenario_id, anchor, entry, point, exemptions)
                    if exemption is None:
                        violations.append(finding)
                    else:
                        used.add(exemption)
                        exempted.append({**finding, "reason": exemption.reason})
    unused = [{**exemption.__dict__, "point": list(exemption.point), "scenarios": list(exemption.scenarios)}
              for exemption in exemptions if exemption not in used]
    return {"schema": "route_anchor_clearance_v1", "min_yards": min_yards, "anchors_checked": checked,
            "all_passed": not violations and not unused
            and all(row["entry"] in KNOWN_TRUNCATED_ENTRIES for row in missing), "violations": violations, "exempted": exempted,
            "unused_exemptions": unused, "truncated_spawn_lists": missing,
            "entries_without_db_spawn": sorted(no_spawn)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--config", type=Path, default=SCENARIO_CONFIG)
    parser.add_argument("--creatures", type=Path, default=CREATURES)
    parser.add_argument("--faction-template-dbc", type=Path, default=FACTION_TEMPLATE_DBC)
    parser.add_argument("--min-yards", type=float, default=MIN_CLEARANCE_YARDS)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = check_anchor_clearance(config, load_creatures(args.creatures), hostile_faction_templates(args.faction_template_dbc),
                                    min_yards=args.min_yards)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
