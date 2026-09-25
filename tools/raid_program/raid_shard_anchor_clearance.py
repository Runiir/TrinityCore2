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

A second rule covers hostiles that no node targets (round 3: the Nefarian orb anchor stood 15 yd from
Ivoroc and 16 yd from two patrol turnarounds, none of them in the route). Every hostile creature that can
aggro players (not a trigger, not non-attackable, not immune to players, not unselectable) and that is
neither a pack/target entry of the anchor's node or a later node nor cleared by an earlier node must stay
NON_TARGET_CLEARANCE_YARDS (native aggro 15 plus a 10 yd margin) away from the anchor. Its reach is its
spawn, its waypoint path (a formation member follows its leader's path) and its random-movement radius,
read from the TDB world dump (creature, creature_addon, waypoint_data, creature_formations,
creature_template). An earlier node clears a spawn of one of its entries when the spawn is the node's
source_guid, a member of that spawn's formation, or within the node's cluster radius.

A third, path-level rule samples the walk between consecutive route anchors (the start, then every node
position) every PATH_SAMPLE_YARDS on the straight segment. No creature still alive on that walk (not
cleared by an earlier node and not the destination node's own pack) may come within native aggro
(PATH_AGGRO_YARDS) of it, counting its patrol path and wander. The rule runs on PATH_CHECK_MAPS only, where
consecutive anchors share a floor or a short ramp; segments into a transport or descent node are the
transport's own movement and are skipped. Navmesh paths would replace the straight segments (round 4).

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
TDB_WORLD = REPO_ROOT / "data/TDB_full_434.22011_2022_01_09/TDB_full_world_434.22011_2022_01_09.sql"
NATIVE_AGGRO_MAX_YARDS = 15.0
NON_TARGET_MARGIN_YARDS = 10.0
NON_TARGET_CLEARANCE_YARDS = NATIVE_AGGRO_MAX_YARDS + NON_TARGET_MARGIN_YARDS
DEFAULT_CLUSTER_RADIUS_YARDS = 40.0
UNIT_FLAG_NON_ATTACKABLE = 0x2
UNIT_FLAG_IMMUNE_TO_PC = 0x100
UNIT_FLAG_NOT_SELECTABLE = 0x2000000
CREATURE_FLAG_EXTRA_TRIGGER = 0x80
MOVEMENT_RANDOM, MOVEMENT_WAYPOINT = 1, 2
PATH_AGGRO_YARDS = NATIVE_AGGRO_MAX_YARDS
PATH_SAMPLE_YARDS = 2.0
PATH_SKIP_KINDS = {"transport", "descent"}
PATH_CHECK_MAPS = {
    669: "Blackwing Descent: consecutive anchors share a floor or a short ramp, so the straight segment "
         "approximates the walked path.",
}
PATH_UNCHECKED_NOTE = ("Straight segments do not approximate this map's route (Stonecore crosses levels and "
                       "clears long corridors by cluster); navmesh paths are a round-4 item.")
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


@dataclass(frozen=True)
class PathExemption:
    """A reviewed walk into `to_node` that may pass one creature entry closely, with the reason."""
    to_node: str
    entry: int
    reason: str


PATH_EXEMPTIONS: tuple[PathExemption, ...] = tuple(
    PathExemption(node, 43296, "Chimaeron (43296) sleeps passive until Finkle Einhorn's gossip starts the "
                               "encounter; the raid walks up to him by design.")
    for node in ("bwd.chimaeron.regroup", "bwd.chimaeron.finkle", "bwd.chimaeron.wake_wait"))


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


@dataclass(frozen=True)
class WorldSpawn:
    guid: int
    entry: int
    map_id: int
    point: tuple[float, float, float]
    reach: tuple[tuple[float, float, float], ...]  # the spawn and every waypoint it walks
    slack: float  # random-movement radius or formation follow distance
    leader: int
    unit_flags: int


def _sql_values(line: str) -> list[list[str]]:
    """Value tuples of one `INSERT INTO ... VALUES (...),(...);` line of a mysqldump."""
    rows: list[list[str]] = []
    current: list[str] = []
    buffer: list[str] = []
    quoted = escaped = False
    depth = 0
    for char in line[line.index("VALUES") + 6:]:
        if quoted:
            if escaped:
                buffer.append(char)
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "'":
                quoted = False
            else:
                buffer.append(char)
        elif char == "'":
            quoted = True
        elif char == "(" and depth == 0:
            depth, current, buffer = 1, [], []
        elif char == ")" and depth == 1:
            current.append("".join(buffer))
            rows.append(current)
            depth = 0
        elif depth == 1 and char == ",":
            current.append("".join(buffer))
            buffer = []
        elif depth == 1:
            buffer.append(char)
    return rows


def load_world(path: Path = TDB_WORLD, maps: Iterable[int] = (669, 725)) -> dict[str, Any]:
    """Creature spawns of the given maps with their reach, and every creature template, from a TDB dump."""
    maps = {int(value) for value in maps}
    tables = {"creature", "creature_template", "creature_addon", "waypoint_data", "creature_formations"}
    columns: dict[str, list[str]] = {}
    rows: dict[str, list[list[str]]] = {name: [] for name in tables}
    creating = None
    with Path(path).open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("CREATE TABLE `"):
                creating = line.split("`")[1]
                columns[creating] = []
            elif creating and line.startswith("  `"):
                columns[creating].append(line.split("`")[1])
            elif creating and line.startswith(")"):
                creating = None
            elif line.startswith("INSERT INTO `"):
                name = line.split("`")[1]
                if name in tables:
                    rows[name].extend(_sql_values(line))

    def records(name: str) -> list[dict[str, str]]:
        return [dict(zip(columns[name], row)) for row in rows[name]]

    templates = {int(row["entry"]): {"name": row["name"], "faction": int(row["faction"]),
                                     "unit_flags": int(row["unit_flags"]), "flags_extra": int(row["flags_extra"])}
                 for row in records("creature_template")}
    creatures = [row for row in records("creature") if int(row["map"]) in maps]
    guids = {int(row["guid"]) for row in creatures}
    path_of = {int(row["guid"]): int(row["waypointPathId"]) for row in records("creature_addon")
               if int(row["guid"]) in guids and int(row["waypointPathId"])}
    paths: dict[int, list[tuple[int, tuple[float, float, float]]]] = {}
    wanted_paths = set(path_of.values())
    for row in records("waypoint_data"):
        if int(row["id"]) in wanted_paths:
            paths.setdefault(int(row["id"]), []).append(
                (int(row["point"]), (float(row["position_x"]), float(row["position_y"]), float(row["position_z"]))))
    formation = {int(row["MemberGUID"]): (int(row["LeaderGUID"]), float(row["FollowDistance"]))
                 for row in records("creature_formations") if int(row["MemberGUID"]) in guids}
    by_guid = {int(row["guid"]): row for row in creatures}

    def walked(guid: int) -> list[tuple[float, float, float]]:
        row = by_guid.get(guid)
        if row is None or int(row["MovementType"]) != MOVEMENT_WAYPOINT or guid not in path_of:
            return []
        return [point for _, point in sorted(paths.get(path_of[guid], []))]

    spawns = []
    for guid, row in sorted(by_guid.items()):
        point = (float(row["position_x"]), float(row["position_y"]), float(row["position_z"]))
        leader, follow = formation.get(guid, (guid, 0.0))
        reach = [point] + walked(guid) + (walked(leader) if leader != guid else [])
        slack = float(row["spawndist"]) if int(row["MovementType"]) == MOVEMENT_RANDOM else 0.0
        spawns.append(WorldSpawn(guid=guid, entry=int(row["id"]), map_id=int(row["map"]), point=point,
                                 reach=tuple(reach), slack=max(slack, follow if leader != guid else 0.0),
                                 leader=leader, unit_flags=int(row["unit_flags"])))
    return {"spawns": spawns, "templates": templates, "source": str(path)}


def can_aggro_players(spawn: WorldSpawn, template: Mapping[str, Any], hostile_factions: set[int]) -> bool:
    flags = int(template.get("unit_flags") or 0) | spawn.unit_flags
    return (int(template.get("faction") or 0) in hostile_factions
            and not flags & (UNIT_FLAG_NON_ATTACKABLE | UNIT_FLAG_IMMUNE_TO_PC | UNIT_FLAG_NOT_SELECTABLE)
            and not int(template.get("flags_extra") or 0) & CREATURE_FLAG_EXTRA_TRIGGER)


def cleared_by(step: Mapping[str, Any], spawn: WorldSpawn) -> bool:
    """True when this fight node kills the spawn: its source, that source's formation, or its cluster."""
    if step.get("kind") not in FIGHT_KINDS or spawn.entry not in node_entries(step):
        return False
    source = str(step.get("source_guid") or "")
    if source.isdigit() and int(source) in (spawn.guid, spawn.leader):
        return True
    radius = float(step.get("cluster_radius_yards") or DEFAULT_CLUSTER_RADIUS_YARDS)
    return "x" in step and math.dist((float(step["x"]), float(step["y"]), float(step["z"])), spawn.point) <= radius


def reach_distance(point: Mapping[str, Any], spawn: WorldSpawn) -> float:
    at = (float(point["x"]), float(point["y"]), float(point["z"]))
    return min(math.dist(at, place) for place in spawn.reach) - spawn.slack


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
                           exemptions: Iterable[Exemption] = EXEMPTIONS,
                           world: Mapping[str, Any] | None = None,
                           non_target_yards: float = NON_TARGET_CLEARANCE_YARDS) -> dict[str, Any]:
    """Rule 1 (later packs, `min_yards` from their spawns) always; rule 2 (hostiles no node targets) with `world`."""
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
                    finding = {"rule": "later_pack", "scenario_id": scenario_id, "anchor": anchor, "entry": entry,
                               "name": mob.get("name"), "node": node, "yards": round(yards, 2),
                               "anchor_point": {axis: point[axis] for axis in ("x", "y", "z")},
                               "spawn": {axis: spawn[axis] for axis in ("x", "y", "z")}}
                    exemption = exemption_for(scenario_id, anchor, entry, point, exemptions)
                    if exemption is None:
                        violations.append(finding)
                    else:
                        used.add(exemption)
                        exempted.append({**finding, "reason": exemption.reason})
            if world is None:
                continue
            later = set().union(*(node_entries(step) for step in route[first_index:])) if route[first_index:] else set()
            for spawn in world["spawns"]:
                template = world["templates"].get(spawn.entry) or {}
                if (spawn.map_id != map_id or spawn.entry in later
                        or not can_aggro_players(spawn, template, hostile_factions)
                        or any(cleared_by(step, spawn) for step in route[:first_index])):
                    continue
                yards = reach_distance(point, spawn)
                if yards >= non_target_yards:
                    continue
                finding = {"rule": "non_target_hostile", "scenario_id": scenario_id, "anchor": anchor,
                           "entry": spawn.entry, "guid": spawn.guid, "name": template.get("name"),
                           "yards": round(yards, 2), "moves": len(spawn.reach) > 1 or spawn.slack > 0,
                           "anchor_point": {axis: point[axis] for axis in ("x", "y", "z")},
                           "spawn": dict(zip(("x", "y", "z"), spawn.point))}
                exemption = exemption_for(scenario_id, anchor, spawn.entry, point, exemptions)
                if exemption is None:
                    violations.append(finding)
                else:
                    used.add(exemption)
                    exempted.append({**finding, "reason": exemption.reason})
    unused = [{**exemption.__dict__, "point": list(exemption.point), "scenarios": list(exemption.scenarios)}
              for exemption in exemptions if exemption not in used]
    paths = check_route_paths(config, world, hostile_factions) if world is not None else {}
    return {"schema": "route_anchor_clearance_v1", "min_yards": min_yards, "anchors_checked": checked,
            "non_target_yards": non_target_yards if world is not None else None,
            "all_passed": not violations and not unused
            and all(row["entry"] in KNOWN_TRUNCATED_ENTRIES for row in missing)
            and not paths.get("path_violations") and not paths.get("path_unused_exemptions"),
            **paths, "violations": violations, "exempted": exempted,
            "unused_exemptions": unused, "truncated_spawn_lists": missing,
            "entries_without_db_spawn": sorted(no_spawn)}


def route_points(scenario: Mapping[str, Any]) -> list[tuple[str, str, tuple[float, float, float]]]:
    """(label, kind, point) of the start and every route node, in walking order."""
    start = scenario.get("start_position") or {}
    points = [("start_position", "start", (float(start["x"]), float(start["y"]), float(start["z"])))]
    for step in scenario.get("route") or []:
        label = str(step.get("node_id") or f"step{step.get('step')}")
        points.append((label, str(step.get("kind") or ""), (float(step["x"]), float(step["y"]), float(step["z"]))))
    return points


def check_route_paths(config: Mapping[str, Any], world: Mapping[str, Any], hostile_factions: set[int], *,
                      yards: float = PATH_AGGRO_YARDS,
                      exemptions: Iterable[PathExemption] = PATH_EXEMPTIONS) -> dict[str, Any]:
    exemptions = tuple(exemptions)
    violations: list[dict[str, Any]] = []
    exempted: list[dict[str, Any]] = []
    unchecked: list[str] = []
    used: set[PathExemption] = set()
    segments = 0
    for scenario in scenarios(config):
        scenario_id = str(scenario.get("id"))
        map_id = int(scenario.get("map_id") or 0)
        if map_id not in PATH_CHECK_MAPS:
            unchecked.append(scenario_id)
            continue
        route = list(scenario.get("route") or [])
        candidates = [spawn for spawn in world["spawns"] if spawn.map_id == map_id
                      and can_aggro_players(spawn, world["templates"].get(spawn.entry) or {}, hostile_factions)]
        points = route_points(scenario)
        for index in range(len(points) - 1):
            (source, _, begin), (target, target_kind, end) = points[index], points[index + 1]
            if target_kind in PATH_SKIP_KINDS:
                continue
            segments += 1
            destination = route[index]
            count = max(1, int(math.dist(begin, end) / PATH_SAMPLE_YARDS))
            samples = [tuple(begin[axis] + (end[axis] - begin[axis]) * part / count for axis in range(3))
                       for part in range(count + 1)]
            for spawn in candidates:
                if cleared_by(destination, spawn) or any(cleared_by(step, spawn) for step in route[:index]):
                    continue
                closest = min(math.dist(sample, place) for sample in samples for place in spawn.reach) - spawn.slack
                if closest >= yards:
                    continue
                finding = {"rule": "route_path", "scenario_id": scenario_id, "from": source, "to": target,
                           "entry": spawn.entry, "guid": spawn.guid,
                           "name": (world["templates"].get(spawn.entry) or {}).get("name"),
                           "yards": round(closest, 2)}
                exemption = next((row for row in exemptions
                                  if row.to_node == target and row.entry == spawn.entry), None)
                if exemption is None:
                    violations.append(finding)
                else:
                    used.add(exemption)
                    exempted.append({**finding, "reason": exemption.reason})
    unused = [row.__dict__ for row in exemptions if row not in used]
    return {"path_yards": yards, "path_segments_checked": segments, "path_violations": violations,
            "path_exempted": exempted, "path_unused_exemptions": unused,
            "path_unchecked_scenarios": {"scenarios": unchecked, "reason": PATH_UNCHECKED_NOTE} if unchecked else {}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--config", type=Path, default=SCENARIO_CONFIG)
    parser.add_argument("--creatures", type=Path, default=CREATURES)
    parser.add_argument("--faction-template-dbc", type=Path, default=FACTION_TEMPLATE_DBC)
    parser.add_argument("--min-yards", type=float, default=MIN_CLEARANCE_YARDS)
    parser.add_argument("--tdb-world", type=Path, default=TDB_WORLD,
                        help="TDB world dump for the non-target rule (skipped when absent)")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    maps = {int(row.get("map_id") or 0) for row in scenarios(config)}
    world = load_world(args.tdb_world, maps) if args.tdb_world.is_file() else None
    report = check_anchor_clearance(config, load_creatures(args.creatures), hostile_faction_templates(args.faction_template_dbc),
                                    min_yards=args.min_yards, world=world)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
