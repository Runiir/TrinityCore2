"""Scenario rows and runtime profiles that activate raid-shard plan cohorts.

A raid_shard_plan_v1 shard (tools.raid_program.raid_shard_plan) runs only when
two tracked rows exist for its scenario ID `<raid>_<size><diff>_<boss>_c<copy>_diagnostic`:

- a diagnostic scenario in experiments/configs/validation_scenarios_cata_001.json
  (`diagnostic_scenarios`, after the six legacy BWD shards). Its route rows are
  cloned from the boss's route template (the plan's `route_template_scenario_id`,
  the legacy `<raid>_<size><diff>_<boss>_diagnostic` shard). Node IDs, labels,
  geometry and contracts are kept verbatim, because strategies look nodes up
  by ID; only fields that name a 1-based roster slot are remapped onto the
  canonical roster (the same class_spec, else the same class and role);
- a runtime profile in dataset/bot_runtime_profiles/profiles.json equal to the
  plan's `runtime_profile` row.

A composition's end-to-end cohort (`full_raid`, e.g. `blackwing_descent_10n_full_c0`)
is not diagnostic: its row sits in `scenarios`, is cloned from the full-raid
route (`blackwing_descent_10n`), carries no roster_identity (the plan supplies
the roster) and no predecessor metadata. Its roster slots are remapped one to
one; a legacy slot whose class the composition lacks takes a free slot of the
same role (e.g. the Protection Paladin tank slot becomes the Feral druid).

Where each boss's rows live, for patch requests from boss agents: the scenario
object whose `id` is the cohort's scenario ID (e.g.
`blackwing_descent_10n_maloriak_c0_diagnostic`), its `route` list (one row per
node, `node_id` is the stable key) and its `mechanic_profiles`. A cloned row is
authoritative once committed: a boss agent's change edits that row. A forwarded
boss fix may also edit the legacy template when the legacy row itself is wrong
(round 2 moved the legacy Maloriak diagnostic start and route and the Omnotron
diagnostic encounter, and the full route with them); such an edit then needs
validation_provisioning reproduced for the moved legacy characters. Byte
neutrality is pinned only for the accepted Magmaw and Stonecore rows and their
provisioning SQL. `validate_raid_shard_scenarios` checks the identity every row
must keep.

The start position of a row is checked against its source, never against
itself: the plan's `start_position_source` when that is another row, else the
row's own explicit `start_position_source`, else its route template.

    pixi run python -m tools.raid_program.raid_shard_scenarios --check
    pixi run python -m tools.raid_program.raid_shard_scenarios --write-missing
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Iterable

from tools.raid_program.raid_composition import COMPOSITION_DIR, REPO_ROOT, read_json

SPEC_CATALOG = REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
SCENARIO_CONFIG = REPO_ROOT / "experiments/configs/validation_scenarios_cata_001.json"
RUNTIME_PROFILES = REPO_ROOT / "dataset/bot_runtime_profiles/profiles.json"
LEGACY_BWD_FIXTURE = REPO_ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"
DIAGNOSTIC_SECTION = "diagnostic_scenarios"
SCENARIO_SECTION = "scenarios"
FULL_RAID_KIND = "full_raid"
# Route-step fields that name one 1-based roster slot (SlotIndex + 1 at runtime),
# lists of slots, anchor lists keyed by `roster_slot`, and contract slots.
STEP_SLOT_FIELDS = ("patrol_pull_owner_roster_slot",)
STEP_SLOT_LIST_FIELDS = ("split_lane_a_roster_slots", "split_lane_b_roster_slots", "split_lane_tank_slots",
                         "split_healer_roster_slots", "split_seed_roster_slots")
STEP_SLOT_ANCHOR_FIELDS = ("split_member_anchors", "split_recovery_member_anchors", "split_tank_combat_anchors",
                           "split_tank_navigation_anchors", "split_tank_recovery_anchors")
CONTRACT_SLOT_FIELDS = ("main_tank_roster_slot", "off_tank_roster_slot")
SCENARIO_KEY_ORDER = ("id", "description", "instance", "map_id", "recovery_entrance", "difficulty",
                      "provisioning_scenario_id", "runtime_profile_id", "cohort_id", "composition_id",
                      "route_template_scenario_id", "diagnostic_only", "diagnostic_parent_scenario_id",
                      "diagnostic_target_boss", "prerequisite_contract", "start_position", "required_roles",
                      "route", "mechanic_profiles")


class RaidShardScenarioError(ValueError):
    pass


def configured_scenarios(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = list(config.get("scenarios") or []) + list(config.get(DIAGNOSTIC_SECTION) or [])
    return {str(row.get("id")): row for row in rows}


def spec_classes(path: Path = SPEC_CATALOG) -> dict[str, int]:
    """class_spec -> class ID from the pinned all-spec catalog."""
    if not Path(path).is_file():
        return {}
    return {str(row["spec_target_id"]): int(row["provisioning_bot"]["class"]) for row in read_json(path).get("targets", [])}


def legacy_rosters(fixture: dict[str, Any] | None, config: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Template scenario -> its roster in route order (the runtime SlotIndex order).

    Legacy diagnostic shards take their roster from the BWD fixture; a
    non-diagnostic template (the full-raid route) from its `roster_identity`,
    with each member's class resolved from the spec catalog.
    """
    rosters = {str(shard["scenario_id"]): list(shard.get("bots") or []) for shard in (fixture or {}).get("shards", [])}
    classes = spec_classes() if config else {}
    for scenario_id, row in configured_scenarios(config or {}).items():
        if scenario_id not in rosters and row.get("roster_identity"):
            rosters[scenario_id] = [{**member, "class": classes.get(str(member.get("class_spec")))}
                                    for member in row["roster_identity"]]
    return rosters


def slot_mapping(template_roster: list[dict[str, Any]], plan_bots: list[dict[str, Any]]) -> dict[int, int]:
    """Legacy 1-based slot -> canonical 1-based slot, one-to-one.

    First the same class_spec, then the same class and role (both only when
    unique), then any remaining slot of the same role, in roster order.
    """
    mapping: dict[int, int] = {}
    for keys in (("class_spec",), ("class", "role")):
        for index, legacy in enumerate(template_roster, 1):
            if index in mapping:
                continue
            taken = set(mapping.values())
            matches = [position for position, bot in enumerate(plan_bots, 1) if position not in taken
                       and all(legacy.get(key) is not None and str(bot.get(key)) == str(legacy.get(key)) for key in keys)]
            if len(matches) == 1:
                mapping[index] = matches[0]
    for index, legacy in enumerate(template_roster, 1):
        if index in mapping:
            continue
        taken = set(mapping.values())
        remaining = [position for position, bot in enumerate(plan_bots, 1)
                     if position not in taken and bot.get("role") == legacy.get("role")]
        if remaining:
            mapping[index] = remaining[0]
    return mapping


def _remap(value: Any, mapping: dict[int, int], where: str) -> int:
    slot = int(value)
    if slot not in mapping:
        raise RaidShardScenarioError(f"roster_slot_unmappable:{where}:{slot}")
    return mapping[slot]


def remap_route(route: list[dict[str, Any]], mapping: dict[int, int], scenario_id: str) -> list[dict[str, Any]]:
    """Clone route rows verbatim except the fields that name roster slots."""
    rows = copy.deepcopy(route)
    for row in rows:
        where = f"{scenario_id}:{row.get('node_id') or row.get('step')}"
        for field in STEP_SLOT_FIELDS:
            if row.get(field):
                row[field] = _remap(row[field], mapping, f"{where}:{field}")
        for field in STEP_SLOT_LIST_FIELDS:
            if row.get(field):
                row[field] = [_remap(value, mapping, f"{where}:{field}") for value in row[field]]
        for field in STEP_SLOT_ANCHOR_FIELDS:
            for anchor in row.get(field) or []:
                if anchor.get("roster_slot"):
                    anchor["roster_slot"] = _remap(anchor["roster_slot"], mapping, f"{where}:{field}")
        contract = row.get("mechanic_contract")
        if isinstance(contract, dict):
            for field in CONTRACT_SLOT_FIELDS:
                if contract.get(field):
                    contract[field] = _remap(contract[field], mapping, f"{where}:mechanic_contract.{field}")
    return rows


def prerequisite_contract(shard: dict[str, Any]) -> dict[str, Any]:
    lockout = shard["lockout"]
    seeded = bool(lockout["precompleted_boss_keys"])
    return {
        "state_source": ("raid_shard_lockout_seed:" + str(lockout["state_source"]) if seeded
                         else "native_instance_start_and_tracked_route_nodes"),
        "precompleted_boss_keys": list(lockout["precompleted_boss_keys"]),
        "precompleted_boss_entries": list(lockout["precompleted_creature_entries"]),
        "certifies_predecessors": False,
        "fixture_kind": "raid_shard_seeded_lockout" if seeded else "boss_shard_route",
    }


def required_roles(shard: dict[str, Any]) -> dict[str, int]:
    counts = shard["role_counts"]
    return {role: int(counts[role]) for role in ("tank", "healer", "dps")}


def clone_scenario(template: dict[str, Any], shard: dict[str, Any], template_roster: list[dict[str, Any]],
                   composition_id: str) -> dict[str, Any]:
    scenario_id = str(shard["scenario_id"])
    mapping = slot_mapping(template_roster, shard["bots"])
    if shard.get("shard_kind") == FULL_RAID_KIND:
        # The end-to-end cohort's own copy of the full-raid route: natural kills
        # only, so no diagnostic or predecessor metadata; its roster comes from
        # the plan (build_validation_scenario_manifests), never roster_identity.
        return {
            "id": scenario_id,
            "description": (f"Canonical-composition end-to-end cohort ({composition_id}) on the full raid route; "
                            f"route rows cloned from {template['id']} with node IDs kept and roster slots "
                            "remapped onto the canonical roster. Every kill is natural."),
            "instance": template["instance"],
            "map_id": int(shard["map_id"]),
            "recovery_entrance": copy.deepcopy(template.get("recovery_entrance") or {}),
            "difficulty": str(shard["difficulty"]),
            "provisioning_scenario_id": scenario_id,
            "runtime_profile_id": str(shard["runtime_profile_id"]),
            "cohort_id": str(shard["cohort_id"]),
            "composition_id": composition_id,
            "route_template_scenario_id": str(template["id"]),
            "start_position": copy.deepcopy(shard["start_position"] or template.get("start_position") or {}),
            "required_roles": required_roles(shard),
            "route": remap_route(template.get("route") or [], mapping, scenario_id),
            "mechanic_profiles": copy.deepcopy(template.get("mechanic_profiles") or {}),
        }
    row = {
        "id": scenario_id,
        "description": (f"Canonical-composition {template.get('diagnostic_target_boss') or shard['boss_key']} shard "
                        f"(cohort {shard['cohort_id']}, {composition_id}); route rows cloned from "
                        f"{template['id']} with node IDs kept. Seeded predecessors are diagnostic assistance "
                        "and never certify kills."),
        "instance": template["instance"],
        "map_id": int(shard["map_id"]),
        "recovery_entrance": copy.deepcopy(template.get("recovery_entrance") or {}),
        "difficulty": str(shard["difficulty"]),
        "provisioning_scenario_id": scenario_id,
        "runtime_profile_id": str(shard["runtime_profile_id"]),
        "cohort_id": str(shard["cohort_id"]),
        "composition_id": composition_id,
        "route_template_scenario_id": str(template["id"]),
        "diagnostic_only": True,
        "diagnostic_parent_scenario_id": str(shard["diagnostic_parent_scenario_id"]),
        "diagnostic_target_boss": str(template.get("diagnostic_target_boss") or shard["boss_key"]),
        "prerequisite_contract": prerequisite_contract(shard),
        "start_position": copy.deepcopy(shard["start_position"] or template.get("start_position") or {}),
        "required_roles": required_roles(shard),
        "route": remap_route(template.get("route") or [], mapping, scenario_id),
        "mechanic_profiles": copy.deepcopy(template.get("mechanic_profiles") or {}),
    }
    return row


def plan_scenario_rows(plan: dict[str, Any], config: dict[str, Any],
                       fixture: dict[str, Any] | None) -> list[dict[str, Any]]:
    """A fresh clone for every plan shard (existing rows are not consulted)."""
    scenarios = configured_scenarios(config)
    rosters = legacy_rosters(fixture, config)
    rows = []
    for shard in plan["shards"]:
        template_id = str(shard.get("route_template_scenario_id") or "")
        template = scenarios.get(template_id)
        if template is None or template_id == shard["scenario_id"]:
            raise RaidShardScenarioError(f"route_template_missing:{shard['scenario_id']}:{template_id}")
        rows.append(clone_scenario(template, shard, rosters.get(template_id, []), str(plan["composition_id"])))
    return rows


def plan_profile_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [copy.deepcopy(shard["runtime_profile"]) for shard in plan["shards"]]


def _slot_references(route: list[dict[str, Any]]) -> list[tuple[str, int]]:
    references = []
    for row in route:
        node = str(row.get("node_id") or row.get("step"))
        references += [(f"{node}:{field}", int(row[field])) for field in STEP_SLOT_FIELDS if row.get(field)]
        references += [(f"{node}:{field}[{index}]", int(value)) for field in STEP_SLOT_LIST_FIELDS
                       for index, value in enumerate(row.get(field) or [])]
        references += [(f"{node}:{field}[{index}]", int(anchor["roster_slot"])) for field in STEP_SLOT_ANCHOR_FIELDS
                       for index, anchor in enumerate(row.get(field) or []) if anchor.get("roster_slot")]
        contract = row.get("mechanic_contract") if isinstance(row.get("mechanic_contract"), dict) else {}
        references += [(f"{node}:mechanic_contract.{field}", int(contract[field]))
                       for field in CONTRACT_SLOT_FIELDS if contract.get(field)]
    return references


def start_reference(shard: dict[str, Any], row: dict[str, Any],
                    scenarios: dict[str, dict[str, Any]]) -> tuple[str | None, dict[str, Any] | None]:
    """(source scenario ID, start) a cohort row's start must equal; (None, None) when the source is absent.

    The plan copies a row's start from the row itself once the row exists
    (raid_shard_plan `start_position_source`), so comparing the two would pass
    any start. Then the reference is the row's explicit `start_position_source`
    or its route template.
    """
    planned = str(shard.get("start_position_source") or "")
    if planned and planned != str(shard["scenario_id"]):
        return planned, shard.get("start_position")
    source = str(row.get("start_position_source") or shard.get("route_template_scenario_id") or "")
    if source == str(shard["scenario_id"]) or source not in scenarios:
        return None, None
    return source, scenarios[source].get("start_position")


def validate_raid_shard_scenarios(plan: dict[str, Any], config: dict[str, Any],
                                  profiles: dict[str, Any] | None = None,
                                  fixture: dict[str, Any] | None = None,
                                  require_all: bool = True) -> dict[str, Any]:
    """Fail-closed identity checks of every plan cohort's scenario row and runtime profile.

    Route contents belong to the boss owner once cloned; this checks only what
    binds a row to its cohort: IDs, difficulty, roles, the lockout contract,
    the start position, the boss's encounter node, roster-slot references
    (in range, and the class the template's slot had), and the profile row.
    """
    scenarios = configured_scenarios(config)
    profile_rows = {str(row.get("name")): row for row in (profiles or {}).get("profiles", [])} if profiles else None
    rosters = legacy_rosters(fixture, config)
    failures: list[dict[str, Any]] = []
    missing: list[str] = []
    checked: list[str] = []
    for shard in plan["shards"]:
        scenario_id = str(shard["scenario_id"])
        row = scenarios.get(scenario_id)
        if row is None:
            missing.append(scenario_id)
            continue
        checked.append(scenario_id)

        def fail(check: str, **details: Any) -> None:
            failures.append({"check": check, "scenario_id": scenario_id, **details})

        expected = {"provisioning_scenario_id": scenario_id, "runtime_profile_id": shard["runtime_profile_id"],
                    "cohort_id": shard["cohort_id"], "difficulty": shard["difficulty"], "map_id": shard["map_id"],
                    "required_roles": required_roles(shard)}
        if shard.get("shard_kind") == FULL_RAID_KIND:
            expected.update({"diagnostic_only": None, "diagnostic_parent_scenario_id": None,
                             "prerequisite_contract": None, "roster_identity": None})
        else:
            expected.update({"diagnostic_only": True,
                             "diagnostic_parent_scenario_id": shard["diagnostic_parent_scenario_id"],
                             "prerequisite_contract": prerequisite_contract(shard)})
        for field, value in expected.items():
            if row.get(field) != value:
                fail("scenario_identity", field=field, expected=value, actual=row.get(field))
        start_source, expected_start = start_reference(shard, row, scenarios)
        if start_source is None:
            fail("scenario_start_position_source_missing",
                 source=row.get("start_position_source") or shard.get("route_template_scenario_id"))
        elif expected_start and row.get("start_position") != expected_start:
            fail("scenario_start_position", source=start_source, expected=expected_start,
                 actual=row.get("start_position"))
        template = scenarios.get(str(shard.get("route_template_scenario_id") or ""))
        route = row.get("route") or []
        node_ids = [str(step.get("node_id") or "") for step in route]
        if len(set(node_ids)) != len(node_ids) or not all(node_ids):
            fail("route_node_ids_missing_or_duplicated", node_ids=node_ids)
        boss_nodes = [str(step.get("node_id")) for step in (template or {}).get("route", []) if step.get("kind") == "boss"]
        if template is None or not boss_nodes or not set(boss_nodes) <= set(node_ids):
            fail("route_template_boss_node_missing", template=shard.get("route_template_scenario_id"),
                 boss_nodes=boss_nodes)
        bots = shard["bots"]
        template_roster = rosters.get(str(shard.get("route_template_scenario_id") or ""), [])
        mapping = slot_mapping(template_roster, bots)
        template_slots = {where: slot for where, slot in _slot_references((template or {}).get("route") or [])}
        for where, slot in _slot_references(route):
            if not 1 <= slot <= len(bots):
                fail("roster_slot_out_of_range", field=where, slot=slot)
                continue
            if where in template_slots and mapping.get(template_slots[where]) not in (None, slot):
                wanted = template_roster[template_slots[where] - 1] if template_slots[where] <= len(template_roster) else {}
                if int(bots[slot - 1].get("class") or 0) != int(wanted.get("class") or -1):
                    fail("roster_slot_class_changed", field=where, slot=slot,
                         expected_class=wanted.get("class"), actual_class=bots[slot - 1].get("class"))
        if profile_rows is not None:
            profile = profile_rows.get(str(shard["runtime_profile_id"]))
            if profile != shard["runtime_profile"]:
                fail("runtime_profile_row", expected=shard["runtime_profile"], actual=profile)
    if require_all and missing:
        failures.append({"check": "raid_shard_scenario_rows_missing", "scenario_ids": missing})
    return {"schema": "raid_shard_scenario_rows_check_v1", "all_passed": not failures, "failures": failures,
            "checked": checked, "missing": missing}


# ---------------------------------------------------------------- tracked-file writers


def _inline(value: Any) -> str:
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(key)}: {_inline(item)}" for key, item in value.items()) + " }"
    if isinstance(value, list) and any(isinstance(item, (dict, list)) for item in value):
        return "[" + ", ".join(_inline(item) for item in value) + "]"
    return json.dumps(value)


def render_scenario(row: dict[str, Any]) -> str:
    """One scenario in the config's hand layout: scalar fields per line, one route row per line."""
    keys = [key for key in SCENARIO_KEY_ORDER if key in row] + [key for key in row if key not in SCENARIO_KEY_ORDER]
    lines = []
    for key in keys:
        value = row[key]
        if key == "route":
            steps = ",\n".join("        " + _inline(step) for step in value)
            lines.append(f'      "route": [\n{steps}\n      ]')
        elif key == "mechanic_profiles":
            items = ",\n".join(f"        {json.dumps(name)}: {json.dumps(families)}" for name, families in value.items())
            lines.append(f'      "mechanic_profiles": {{\n{items}\n      }}' if value else '      "mechanic_profiles": {}')
        elif key == "prerequisite_contract":
            items = ",\n".join(f"        {json.dumps(name)}: {json.dumps(item)}" for name, item in value.items())
            lines.append(f'      "prerequisite_contract": {{\n{items}\n      }}')
        else:
            lines.append(f"      {json.dumps(key)}: {_inline(value)}")
    return "    {\n" + ",\n".join(lines) + "\n    }"


def render_profile(row: dict[str, Any]) -> str:
    text = json.dumps(row, indent=2)
    return "\n".join("    " + line for line in text.splitlines())


def append_to_array(text: str, rendered: Iterable[str], key: str) -> str:
    """Append objects to the document's top-level array `key`, keeping every other byte."""
    rendered = list(rendered)
    if not rendered:
        return text
    document = json.loads(text)
    keys = list(document)
    if key not in keys or not isinstance(document[key], list) or not document[key]:
        raise RaidShardScenarioError(f"array_missing_or_empty:{key}")
    index = keys.index(key)
    closing = "\n  ]\n}\n" if index == len(keys) - 1 else "\n  ],\n  " + json.dumps(keys[index + 1]) + ":"
    if text.count(closing) != 1 or (index == len(keys) - 1 and not text.endswith(closing)):
        raise RaidShardScenarioError(f"unexpected_array_layout:{key}")
    at = text.index(closing)
    new_text = text[:at] + ",\n" + ",\n".join(rendered) + text[at:]
    after = json.loads(new_text)
    appended = [json.loads(item) for item in rendered]
    if after[key][:len(document[key])] != document[key] or after[key][len(document[key]):] != appended:
        raise RaidShardScenarioError(f"append_changed_other_content:{key}")
    if list(after) != keys or {name: value for name, value in after.items() if name != key} != {
            name: value for name, value in document.items() if name != key}:
        raise RaidShardScenarioError(f"append_changed_other_content:{key}")
    return new_text


def scenario_section(row: dict[str, Any]) -> str:
    """Boss shards join the diagnostic shards; an end-to-end cohort is an ordinary scenario."""
    return DIAGNOSTIC_SECTION if row.get("diagnostic_only") else SCENARIO_SECTION


def build_plan(composition_path: Path) -> dict[str, Any]:
    """The plan without SQL materialization (IDs, rosters, lockouts and profiles only)."""
    from tools.raid_program.raid_shard_plan import build_shard_plan, load_plan_inputs

    composition, prerequisites, defaults, starts, sources = load_plan_inputs(composition_path)
    return build_shard_plan(composition, prerequisites, starts=starts, provisioning_defaults=defaults,
                            sources=sources)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or add raid-shard cohort scenario rows and runtime profiles.")
    parser.add_argument("--composition", type=Path, action="append",
                        help="Composition JSON; defaults to every file in experiments/configs/raid_compositions.")
    parser.add_argument("--plan", type=Path, help="Use a generated plan.json instead of building the plan.")
    parser.add_argument("--scenario-config", type=Path, default=SCENARIO_CONFIG)
    parser.add_argument("--runtime-profiles", type=Path, default=RUNTIME_PROFILES)
    parser.add_argument("--legacy-fixture", type=Path, default=LEGACY_BWD_FIXTURE)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="exit 1 unless every cohort row and profile validates")
    mode.add_argument("--write-missing", action="store_true",
                      help="clone rows and profiles for cohorts that have none; never rewrite existing rows")
    args = parser.parse_args(argv)

    plans = ([read_json(args.plan)] if args.plan
             else [build_plan(path) for path in (args.composition or sorted(COMPOSITION_DIR.glob("*.json")))])
    fixture = read_json(args.legacy_fixture) if args.legacy_fixture.is_file() else None
    reports = []
    for plan in plans:
        if args.write_missing:
            config_text = args.scenario_config.read_text(encoding="utf-8")
            profiles_text = args.runtime_profiles.read_text(encoding="utf-8")
            config, profiles = json.loads(config_text), json.loads(profiles_text)
            present = set(configured_scenarios(config))
            names = {str(row.get("name")) for row in profiles.get("profiles", [])}
            rows = [row for row in plan_scenario_rows(plan, config, fixture) if row["id"] not in present]
            profile_rows = [row for row in plan_profile_rows(plan) if row["name"] not in names]
            for section in (SCENARIO_SECTION, DIAGNOSTIC_SECTION):
                config_text = append_to_array(
                    config_text, [render_scenario(row) for row in rows if scenario_section(row) == section], section)
            args.scenario_config.write_text(config_text, encoding="utf-8")
            args.runtime_profiles.write_text(
                append_to_array(profiles_text, map(render_profile, profile_rows), "profiles"), encoding="utf-8")
        report = validate_raid_shard_scenarios(plan, read_json(args.scenario_config),
                                               read_json(args.runtime_profiles), fixture)
        reports.append({"composition_id": plan["composition_id"], **report})
    print(json.dumps(reports, indent=2, sort_keys=True))
    return 0 if all(report["all_passed"] for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
