"""Where a content phase's gear comes from: loot maps, vendor costs and crafting recipes.

The shared player-acquisition index (``item_source_index.jsonl``) does not
resolve ``reference_loot_template``, and raid bosses drop their loot through
references (Magmaw: creature_loot 41570 -> reference 415700), so it cannot
tell a Tier 11 drop from a Dragon Soul one. A phase therefore reads its loot
from world-database rows: every creature and chest spawned on the phase's loot
maps (with their difficulty entries), their loot tables and every reference
they reach. Vendor rows are admitted by their ItemExtendedCost currencies and
required items; crafted items by a learnable primary-profession recipe that
creates them (SpellEffect 24 + SkillLineAbility + the recipe source index).

The builder never reads the database: ``extract_phase_gear_db`` pins exactly
these rows into a DVC-tracked extract, and ``world_sources_from_rows`` derives
the phase's sources from it with the same selection helpers the extract used.

Everything here fails closed: an empty loot table, a missing reference or a
missing DBC oracle raises instead of admitting a smaller or larger item set.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.bot_ml.build_validation_gear_profiles import load_wdb2, load_wdbc

ITEM_EXTENDED_COST_FMT = "n" + "i" * 30
SPELL_EFFECT_FMT = "nifiiiffiiiiiifiifiiiiiiiix"
SKILL_LINE_ABILITY_FMT = "niiiixxiiiiiii"
SPELL_EFFECT_CREATE_ITEM = 24
GAMEOBJECT_TYPE_CHEST = 3
MAX_REFERENCE_DEPTH = 8
DUNGEON_ENCOUNTER_FMT = "niixisxx"
ENCOUNTER_CREDIT_KILL_CREATURE = 0
DEFAULT_RECIPE_SOURCE_INDEX = Path("dataset/world_planner/recipe_source_index.jsonl")


class PhaseSourceError(ValueError):
    pass


# The pinned world-database row sets, in selection order (extract_phase_gear_db).
WORLD_TABLES = ("creature_spawns", "encounter_credits", "creature_templates", "difficulty_templates", "chests",
                "creature_loot", "gameobject_loot", "reference_loot", "npc_vendor")


def _digest(rows: list[Any]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def loot_maps(config: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    return {int(row["map_id"]): row for row in config["sources"].get("loot_maps") or []}


def spawn_maps(spawns: list[Mapping[str, Any]], credits: list[Mapping[str, Any]], encounters: Mapping[int, int],
               maps: Mapping[int, Any]) -> dict[int, int]:
    """Creature entry -> loot map: spawns on a loot map, then each loot map's encounter kill-credit creature
    (instance_encounters + DungeonEncounter.dbc): script-summoned bosses such as Nefarian have no spawn row."""
    spawn_map: dict[int, int] = {}
    for row in spawns:
        spawn_map.setdefault(int(row["id"]), int(row["map"]))
    for row in credits:
        map_id = encounters.get(int(row["entry"]))
        if map_id in maps and int(row["creditType"]) == ENCOUNTER_CREDIT_KILL_CREATURE and int(row["creditEntry"]):
            spawn_map.setdefault(int(row["creditEntry"]), int(map_id))
    return spawn_map


def template_bases(templates: list[Mapping[str, Any]]) -> dict[int, int]:
    """Creature entry -> its base entry (a difficulty entry maps to the entry that names it)."""
    base = {int(row["entry"]): int(row["entry"]) for row in templates}
    for row in templates:
        for field in ("difficulty_entry_1", "difficulty_entry_2", "difficulty_entry_3"):
            if int(row[field] or 0):
                base.setdefault(int(row[field]), int(row["entry"]))
    return base


def loot_owners(templates: list[Mapping[str, Any]], base: Mapping[int, int],
                spawn_map: Mapping[int, int]) -> dict[int, list[tuple[int, int]]]:
    """creature_loot_template entry -> [(creature entry, loot map)]."""
    owners: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for row in templates:
        if int(row["lootid"] or 0):
            entry = int(row["entry"])
            owners[int(row["lootid"])].append((entry, spawn_map[base[entry]]))
    return owners


def chest_owners(chests: list[Mapping[str, Any]]) -> dict[int, list[tuple[int, int]]]:
    """gameobject_loot_template entry -> [(chest entry, loot map)]."""
    owners: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for row in chests:
        owners[int(row["Data1"])].append((int(row["entry"]), int(row["map"])))
    return owners


def resolve_loot_rows(rows: list[dict[str, Any]], references: Mapping[int, list[dict[str, Any]]],
                      chain: tuple[int, ...] = ()) -> Iterable[tuple[int, tuple[int, ...]]]:
    """(item_id, reference chain) of every item a loot row list can yield, following references."""
    for row in rows:
        reference = int(row.get("Reference") or 0)
        if reference:
            if reference in chain:
                continue
            if len(chain) >= MAX_REFERENCE_DEPTH:
                raise PhaseSourceError(f"phase_loot_reference_too_deep:{chain + (reference,)}")
            if reference not in references:
                raise PhaseSourceError(f"phase_loot_reference_missing:{reference}")
            yield from resolve_loot_rows(references[reference], references, chain + (reference,))
        elif int(row.get("Item") or 0) > 0:
            yield int(row["Item"]), chain


def encounter_maps(dbc_dir: Path) -> dict[int, int]:
    """DungeonEncounter.dbc: encounter ID -> map ID."""
    path = Path(dbc_dir) / "DungeonEncounter.dbc"
    if not path.is_file():
        raise PhaseSourceError("phase_dungeon_encounter_oracle_missing")
    return {int(row["values"][0]): int(row["values"][1]) for row in load_wdbc(path, DUNGEON_ENCOUNTER_FMT)}


def world_sources_from_rows(tables: Mapping[str, list[Mapping[str, Any]]], config: Mapping[str, Any],
                            encounters: Mapping[int, int]) -> dict[str, Any]:
    """Loot of the phase maps and every vendor row, from the pinned world-database rows.

    ``tables`` holds the extract's WORLD_TABLES rows (``extract_phase_gear_db``
    selected them with these same helpers). Loot owners are the creatures
    spawned on a loot map plus every encounter kill-credit creature of a loot
    map, with their difficulty entries, and the chests spawned there.
    """
    missing = [name for name in WORLD_TABLES if name not in tables]
    if missing:
        raise PhaseSourceError(f"phase_world_rows_missing:{missing}")
    maps = loot_maps(config)
    loot: dict[int, list[dict[str, Any]]] = defaultdict(list)
    if maps:
        spawn_map = spawn_maps(tables["creature_spawns"], tables["encounter_credits"], encounters, maps)
        base = template_bases(tables["creature_templates"])
        creature_loot_ids = loot_owners([*tables["creature_templates"], *tables["difficulty_templates"]], base, spawn_map)
        chest_loot_ids = chest_owners(tables["chests"])
        if not tables["creature_loot"] or not tables["reference_loot"]:
            raise PhaseSourceError("phase_loot_tables_empty")
        references: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
        for row in tables["reference_loot"]:
            references[int(row["Entry"])].append(row)
        for kind, rows, owners in (("creature_loot", tables["creature_loot"], creature_loot_ids),
                                   ("gameobject_loot", tables["gameobject_loot"], chest_loot_ids)):
            for row in rows:
                if int(row["Entry"]) not in owners:
                    raise PhaseSourceError(f"phase_loot_row_without_owner:{kind}:{row['Entry']}")
                for item_id, chain in resolve_loot_rows([row], references):
                    for source_entry, map_id in owners[int(row["Entry"])]:
                        loot[item_id].append({"source_type": kind, "source_entry": source_entry,
                                              "loot_entry": int(row["Entry"]), "map_id": map_id,
                                              "map_name": maps[map_id]["name"], "reference_chain": list(chain)})
    if not tables["npc_vendor"]:
        raise PhaseSourceError("phase_vendor_table_empty")
    vendors: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in tables["npc_vendor"]:
        vendors[int(row["item"])].append({"vendor_entry": int(row["entry"]), "extended_cost": int(row["ExtendedCost"] or 0)})
    for rows in loot.values():
        rows.sort(key=lambda row: (row["map_id"], row["source_type"], row["source_entry"], row["loot_entry"]))
    digests = {name: _digest(list(tables[name])) for name in WORLD_TABLES}
    return {"loot": dict(loot), "vendor": dict(vendors), "row_digests": digests}


def load_extended_costs(dbc_dir: Path) -> dict[int, dict[str, Any]]:
    path = Path(dbc_dir) / "ItemExtendedCost.db2"
    if not path.is_file():
        raise PhaseSourceError("phase_extended_cost_oracle_missing")
    costs = {}
    for row in load_wdb2(path, ITEM_EXTENDED_COST_FMT):
        values = row["values"]
        costs[int(values[0])] = {
            "honor": int(values[1]), "arena_points": int(values[2]), "arena_slot": int(values[3]),
            "items": [int(item) for item in values[4:9] if int(item)],
            "personal_rating": int(values[14]),
            "currencies": [int(currency) for currency in values[16:21] if int(currency)],
        }
    return costs


def recipe_items_teaching(dbc_dir: Path) -> dict[int, set[int]]:
    """Recipe spell -> the items that teach it (Item-sparse spell with trigger 6, ITEM_SPELLTRIGGER_LEARN_SPELL_ID)."""
    from tools.bot_ml.build_validation_gear_profiles import ITEM_SPARSE_FMT

    teaching: dict[int, set[int]] = defaultdict(set)
    for row in load_wdb2(Path(dbc_dir) / "Item-sparse.db2", ITEM_SPARSE_FMT):
        values = row["values"]
        for spell, trigger in zip(values[68:73], values[73:78]):
            if int(trigger) == 6 and int(spell) > 0:
                teaching[int(spell)].add(int(values[0]))
    return teaching


def crafted_sources(dbc_dir: Path, recipe_index: Path, profession_skill_ids: Iterable[int],
                    item_source_index: Path | None = None) -> dict[int, list[dict[str, Any]]]:
    """Items a learnable primary-profession recipe creates (SpellEffect 24).

    A recipe spell is learnable when a trainer teaches it (recipe source
    index) or an obtainable recipe item teaches it: a vendor recipe item of
    the recipe source index, or an item with a direct loot/vendor source in
    the player acquisition index.
    """
    professions = {int(skill) for skill in profession_skill_ids}
    recipe_index = Path(recipe_index)
    if not recipe_index.is_file():
        raise PhaseSourceError(f"phase_recipe_index_missing:{recipe_index}")
    trainer_spells: set[int] = set()
    obtainable_items: set[int] = set()
    for line in recipe_index.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if not row.get("sources"):
            continue
        if int(row.get("recipe_spell_id") or 0) > 0:
            trainer_spells.add(int(row["recipe_spell_id"]))
        if int(row.get("item_id") or 0) > 0:
            obtainable_items.add(int(row["item_id"]))
    if item_source_index is not None:
        with Path(item_source_index).open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if int(row.get("item_id") or 0) > 0 and any(
                        int(source.get("reference") or 0) == 0 and int(source.get("source_entry") or 0) > 0
                        for source in row.get("sources") or []):
                    obtainable_items.add(int(row["item_id"]))
    teaching = recipe_items_teaching(dbc_dir)
    skill_by_spell: dict[int, int] = {}
    for row in load_wdbc(Path(dbc_dir) / "SkillLineAbility.dbc", SKILL_LINE_ABILITY_FMT):
        values = row["values"]
        if int(values[1]) in professions:
            skill_by_spell.setdefault(int(values[2]), int(values[1]))
    crafted: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in load_wdbc(Path(dbc_dir) / "SpellEffect.dbc", SPELL_EFFECT_FMT):
        values = row["values"]
        spell_id, item_id = int(values[24]), int(values[10])
        if int(values[1]) != SPELL_EFFECT_CREATE_ITEM or item_id <= 0 or spell_id not in skill_by_spell:
            continue
        recipe_items = sorted(teaching.get(spell_id, set()) & obtainable_items)
        if spell_id in trainer_spells or recipe_items:
            crafted[item_id].append({"source_type": "crafted", "recipe_spell_id": spell_id,
                                     "profession_skill_id": skill_by_spell[spell_id],
                                     "learned_from": "trainer" if spell_id in trainer_spells else "recipe_item",
                                     "recipe_item_ids": recipe_items[:3]})
    if not crafted:
        raise PhaseSourceError("phase_crafted_oracle_empty")
    return {item: sorted(rows, key=lambda row: row["recipe_spell_id"]) for item, rows in crafted.items()}


def vendor_cost_admitted(cost: Mapping[str, Any] | None, config: Mapping[str, Any], loot_items: set[int]) -> str | None:
    """None when the cost is phase-legal, otherwise the reason it is not."""
    sources = config["sources"]
    if cost is None:
        return "extended_cost_missing"
    if cost["honor"] or cost["arena_points"] or cost["arena_slot"] or cost["personal_rating"]:
        return "pvp_cost"
    allowed = {int(row["currency_id"]) for row in sources.get("vendor_currencies") or []}
    if any(currency not in allowed for currency in cost["currencies"]):
        return "currency_out_of_phase"
    if cost["items"]:
        if sources.get("vendor_required_items") != "loot_from_loot_maps":
            return "required_item_not_allowed"
        if any(item not in loot_items for item in cost["items"]):
            return "required_item_out_of_phase"
    if not cost["currencies"] and not cost["items"] and not sources.get("vendor_gold"):
        return "gold_not_allowed"
    return None


def admit_sources(item: Mapping[str, Any], world: Mapping[str, Any], crafted: Mapping[int, list[dict[str, Any]]],
                  costs: Mapping[int, Mapping[str, Any]], config: Mapping[str, Any],
                  loot_items: set[int], bonding: int) -> tuple[list[dict[str, Any]], list[str]]:
    """(admitted phase sources, rejection reasons) of one item."""
    item_id = int(item["ID"])
    admitted = [dict(row) for row in world["loot"].get(item_id, [])]
    reasons: list[str] = []
    for row in world["vendor"].get(item_id, []):
        extended = int(row["extended_cost"])
        cost = {"honor": 0, "arena_points": 0, "arena_slot": 0, "personal_rating": 0, "items": [], "currencies": []} \
            if not extended else costs.get(extended)
        reason = vendor_cost_admitted(cost, config, loot_items)
        if reason:
            reasons.append(f"vendor:{reason}")
            continue
        admitted.append({"source_type": "vendor", "source_entry": int(row["vendor_entry"]), "extended_cost": extended,
                         "currencies": list(cost["currencies"]), "required_items": list(cost["items"])})
    excluded_bonding = {int(value) for value in (config["sources"].get("crafted") or {}).get("excluded_bonding") or []}
    for row in crafted.get(item_id, []):
        if bonding in excluded_bonding:
            reasons.append("crafted:bind_on_pickup")
            continue
        admitted.append(dict(row))
    if not admitted and not reasons:
        reasons.append("no_phase_source")
    return admitted, reasons


def item_bonding_map(dbc_dir: Path) -> dict[int, int]:
    from tools.bot_ml.build_validation_gear_profiles import ITEM_SPARSE_FMT

    return {int(row["values"][0]): int(row["values"][98]) for row in load_wdb2(Path(dbc_dir) / "Item-sparse.db2", ITEM_SPARSE_FMT)}


def item_set_map(dbc_dir: Path) -> dict[int, int]:
    from tools.bot_ml.build_validation_gear_profiles import ITEM_SPARSE_FMT

    return {int(row["values"][0]): int(row["values"][113])
            for row in load_wdb2(Path(dbc_dir) / "Item-sparse.db2", ITEM_SPARSE_FMT) if int(row["values"][113])}


def item_set_names(dbc_dir: Path) -> dict[str, list[int]]:
    """ItemSet.dbc name -> set IDs (a name can repeat across expansions)."""
    names: dict[str, list[int]] = defaultdict(list)
    for row in load_wdbc(Path(dbc_dir) / "ItemSet.dbc", "dsiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii"):
        names[str(row["values"][1])].append(int(row["values"][0]))
    return dict(names)
