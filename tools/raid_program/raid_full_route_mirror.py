"""The end-to-end cohort's route, mirrored from the composition's own boss shards.

A canonical composition's full raid (`<raid>_<size><diff>_full_c<copy>`) runs the
same characters as its boss shards, and a boss shard can pick another talent
group for a member (the BWD druid is Balance on Magmaw and Atramedes and the
Feral tank elsewhere; the shaman is Elemental or Restoration). So the full raid
does not reuse the legacy full-raid route: for every node set of the raid's
route composition (experiments/configs/raid_route_compositions/, the same order
the legacy route uses) it takes the rows of the boss shard that owns the set
(the plan shard whose route template is the set's source, same copy), exactly as
committed, and only renumbers the roster slots from that shard's roster onto the
full raid's (the same character). Inline composition rows (the elevator transit)
are kept; the legacy variants (two-tank Drudge lanes, the Magmaw tank swap) are
not, because the shard rows already match the shard's composition.

Before a node set whose owning shard runs another talent group for any member,
the route gets one spec-switch regroup node (`<prefix>.spec_switch.<set id>`),
and the route starts with one: every member switches, out of combat and with the
native Activate Primary/Secondary Spec spell, to the shard's talent group, equips
that group's gear set, and takes that group's role and class spec
(`spec_contract`, one row per roster slot with both talent groups' identities).
The node stands at the last walkable node the raid already cleared (the route
start for the first), never on a boss spawn or a transport.

    pixi run python -m tools.raid_program.raid_shard_scenarios --check
    pixi run python -m tools.raid_program.raid_shard_scenarios --write-full-routes
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from tools.raid_program.raid_composition import REPO_ROOT, read_json

ROUTE_COMPOSITION_DIR = REPO_ROOT / "experiments/configs/raid_route_compositions"
SPEC_SWITCH_SEGMENT = "spec_switch"
# Rows the switch node may stand on: walkable ground the raid already cleared.
ANCHOR_KINDS = ("regroup", "travel", "trash", "interaction")


class FullRouteMirrorError(ValueError):
    pass


class FullRouteMirrorIncomplete(FullRouteMirrorError):
    """A node set's owner shard or its scenario row is absent (a partial plan, or rows not cloned yet)."""


def route_composition(template_scenario_id: str, directory: Path = ROUTE_COMPOSITION_DIR) -> dict[str, Any]:
    for path in sorted(Path(directory).glob("*.json")):
        document = read_json(path)
        if document.get("scenario_id") == template_scenario_id:
            return document
    raise FullRouteMirrorError(f"route_composition_missing:{template_scenario_id}")


def _slot_map(source_bots: list[dict[str, Any]], target_bots: list[dict[str, Any]], where: str) -> dict[int, int]:
    """Source 1-based slot -> target 1-based slot of the same character."""
    target = {str(bot["character_key"]): index for index, bot in enumerate(target_bots, 1)}
    mapping = {}
    for index, bot in enumerate(source_bots, 1):
        key = str(bot["character_key"])
        if key not in target:
            raise FullRouteMirrorError(f"character_missing_in_full_roster:{where}:{key}")
        mapping[index] = target[key]
    return mapping


def _identity(bot: dict[str, Any]) -> tuple[int, str, str]:
    return int(bot["loadout"]["active_talent_group"]), str(bot["class_spec"]), str(bot["role"])


def spec_contract(full_bots: list[dict[str, Any]], shard_bots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per full-raid slot: the owning shard's talent group, class spec and role for that character,
    and every talent group's identity (the runtime resolves identity from the active group)."""
    wanted = {str(bot["character_key"]): _identity(bot) for bot in shard_bots}
    rows = []
    for slot, bot in enumerate(full_bots, 1):
        key = str(bot["character_key"])
        group, class_spec, role = wanted[key]
        groups = [{"talent_group": int(row["talent_group"]), "class_spec": str(row["class_spec"]),
                   "role": str(row["role"])} for row in bot["loadout"]["groups"]]
        declared = next((row for row in groups if row["talent_group"] == group), None)
        if declared is None or (declared["class_spec"], declared["role"]) != (class_spec, role):
            raise FullRouteMirrorError(f"spec_contract_group_mismatch:{key}:{group}:{class_spec}")
        rows.append({"roster_slot": slot, "character_key": key, "talent_group": group, "class_spec": class_spec,
                     "role": role, "talent_groups": groups})
    return rows


def _node_prefix(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        node_id = str(row.get("node_id") or "")
        if "." in node_id:
            return node_id.split(".", 1)[0]
    raise FullRouteMirrorError("node_prefix_missing")


def _anchor(previous: list[dict[str, Any]], start: dict[str, Any] | None) -> dict[str, float]:
    for row in reversed(previous):
        if row.get("kind") in ANCHOR_KINDS and not row.get("transport_contract"):
            return {key: float(row.get(key) or 0.0) for key in ("x", "y", "z", "o")}
    if not start:
        raise FullRouteMirrorError("spec_switch_anchor_missing")
    return {key: float(start.get(key) or 0.0) for key in ("x", "y", "z", "o")}


def mirror_full_route(plan: dict[str, Any], full: dict[str, Any], config_scenarios: dict[str, dict[str, Any]],
                      composition: dict[str, Any] | None = None) -> dict[str, Any]:
    """{"route": [...], "mechanic_profiles": {...}, "node_sets": [...], "duplicates": [...]} for the full shard."""
    composition = composition or route_composition(str(full["route_template_scenario_id"]))
    owners = {(str(shard.get("route_template_scenario_id")), int(shard.get("copy") or 0)): shard
              for shard in plan["shards"] if shard is not full and shard.get("shard_kind") != full.get("shard_kind")}
    full_bots = full["bots"]
    current = {str(bot["character_key"]): _identity(bot) for bot in full_bots}
    rows: list[dict[str, Any]] = []
    origins: dict[str, str] = {}
    profiles: dict[str, list[str]] = {}
    duplicates: list[dict[str, str]] = []
    node_sets: list[dict[str, Any]] = []
    first_switch = True
    for node_set in composition.get("node_sets") or []:
        set_id = str(node_set["id"])
        if node_set.get("rows") is not None:
            source_rows, origin, owner = [copy.deepcopy(row) for row in node_set["rows"]], f"composition:{set_id}", None
        else:
            owner = owners.get((str(node_set["source_scenario_id"]), int(full.get("copy") or 0)))
            if owner is None:
                raise FullRouteMirrorIncomplete(f"node_set_owner_shard_missing:{set_id}:{node_set['source_scenario_id']}")
            scenario = config_scenarios.get(str(owner["scenario_id"]))
            if scenario is None:
                raise FullRouteMirrorIncomplete(f"owner_scenario_row_missing:{owner['scenario_id']}")
            origin = str(owner["scenario_id"])
            source_rows = sorted(scenario.get("route") or [], key=lambda row: int(row.get("step") or 0))
            wanted = node_set.get("node_ids")
            if wanted is not None:
                by_id = {str(row.get("node_id")): row for row in source_rows}
                missing = [node_id for node_id in wanted if node_id not in by_id]
                if missing:
                    raise FullRouteMirrorError(f"node_set_node_missing:{set_id}:{missing[0]}")
                source_rows = [by_id[node_id] for node_id in wanted]
            from tools.raid_program.raid_shard_scenarios import remap_route

            source_rows = remap_route(source_rows, _slot_map(owner["bots"], full_bots, origin), str(full["scenario_id"]))
            for name, families in (scenario.get("mechanic_profiles") or {}).items():
                if name in profiles and profiles[name] != list(families):
                    raise FullRouteMirrorError(f"mechanic_profile_conflict:{name}:{origin}")
                profiles.setdefault(name, list(families))
            wanted_identity = {str(bot["character_key"]): _identity(bot) for bot in owner["bots"]}
            if first_switch or wanted_identity != current:
                switch = {
                    "node_id": f"{_node_prefix(source_rows)}.{SPEC_SWITCH_SEGMENT}.{set_id}",
                    "kind": "regroup", "node_kind": "regroup",
                    "label": f"talent groups for the {set_id} node set (as {origin})",
                    **_anchor(rows, full.get("start_position")),
                    "completion_policy": "arrival",
                    "spec_contract_source": origin,
                    "spec_contract": spec_contract(full_bots, owner["bots"]),
                }
                if switch["node_id"] in origins:
                    raise FullRouteMirrorError(f"spec_switch_node_duplicate:{switch['node_id']}")
                origins[switch["node_id"]] = f"spec_switch:{set_id}"
                rows.append(switch)
                current, first_switch = wanted_identity, False
        emitted = []
        for source_row in source_rows:
            row = {key: copy.deepcopy(value) for key, value in source_row.items() if key != "step"}
            node_id = str(row.get("node_id") or "")
            if node_id in origins:
                previous = next(item for item in rows if item["node_id"] == node_id)
                if previous != row:
                    raise FullRouteMirrorError(f"conflicting_rows:{node_id}:{origins[node_id]}:{origin}")
                duplicates.append({"node_id": node_id, "kept_from": origins[node_id], "duplicate_in": origin})
                continue
            origins[node_id] = origin
            rows.append(row)
            emitted.append(node_id)
        node_sets.append({"id": set_id, "source": origin, "node_ids": emitted})
    # The composition's own profiles (for its inline rows) merge like the shards', conflicts refused.
    for name, families in (composition.get("mechanic_profiles") or {}).items():
        if name in profiles and profiles[name] != list(families):
            raise FullRouteMirrorError(f"mechanic_profile_conflict:{name}:composition")
        profiles.setdefault(name, list(families))
    referenced = []
    for row in rows:
        name = str(row.get("mechanic_profile") or "")
        if name and name not in referenced:
            referenced.append(name)
    missing = [name for name in referenced if name not in profiles]
    if missing:
        raise FullRouteMirrorError(f"mechanic_profile_missing:{missing[0]}")
    return {"route": [{"step": index, **row} for index, row in enumerate(rows, 1)],
            "mechanic_profiles": {name: profiles[name] for name in referenced},
            "node_sets": node_sets, "duplicates": duplicates}


def mirror_drift(scenario: dict[str, Any], mirrored: dict[str, Any]) -> list[dict[str, Any]]:
    """Node-level differences between a materialized full-raid row and its mirror."""
    have = [str(row.get("node_id")) for row in scenario.get("route") or []]
    want = [str(row.get("node_id")) for row in mirrored["route"]]
    drift: list[dict[str, Any]] = []
    if have != want:
        drift.append({"kind": "node_order", "materialized": have, "mirrored": want})
    by_id = {str(row.get("node_id")): row for row in scenario.get("route") or []}
    for row in mirrored["route"]:
        other = by_id.get(str(row["node_id"]))
        if other is not None and other != row:
            drift.append({"kind": "node_fields", "node_id": row["node_id"],
                          "fields": sorted(key for key in set(row) | set(other) if row.get(key) != other.get(key))})
    if (scenario.get("mechanic_profiles") or {}) != mirrored["mechanic_profiles"]:
        drift.append({"kind": "mechanic_profiles"})
    return drift
