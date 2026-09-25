"""Database readback of two-spec loadouts: every talent/glyph group and bag.

Both provisioning readbacks (the strict verifier and the per-shard phase-1
capture) call `loadout_readback_failures` for bots that carry a `loadout`.
It checks talent group 1 and bag != 0 as strictly as group 0 and bag 0:
the exact talent and glyph rows of each group, the pre-login active group,
the container bag, and every item row with its owner and modifiers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from tools.bot_ml.build_validation_provisioning import (
    BONUS_ENCHANTMENT_FIELD_OFFSET,
    PRISMATIC_ENCHANTMENT_FIELD_OFFSET,
    SOCKET_ENCHANTMENT_FIELD_OFFSETS,
)
from tools.raid_program.raid_loadout import (
    expected_glyph_rows,
    expected_inventory,
    expected_talent_rows,
    expected_talent_tree,
)

MODIFIER_OFFSETS = (0, *SOCKET_ENCHANTMENT_FIELD_OFFSETS, BONUS_ENCHANTMENT_FIELD_OFFSET,
                    PRISMATIC_ENCHANTMENT_FIELD_OFFSET, 24)
INVENTORY_FIELDS = ("bag", "slot", "item_id", "count")


def _payload(text: Any) -> list[int]:
    try:
        return [int(token) for token in str(text or "").split()]
    except ValueError:
        return []


def fetch_runtime_loadouts(database_url: str, names: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Read every talent group, glyph group, spell and inventory row (all bags)."""
    from tools.bot_ml.extract_world_knowledge import connect_mysql

    names = sorted(set(names))
    if not names:
        return {}
    placeholders = ", ".join(["%s"] * len(names))
    state: dict[str, dict[str, Any]] = {}
    conn = connect_mysql(database_url)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT c.name, c.guid, c.talentGroupsCount, c.activeTalentGroup, c.talentTree "
                f"FROM characters c WHERE c.name IN ({placeholders})", tuple(names))
            for row in cursor.fetchall():
                state[str(row["name"])] = {
                    "guid": int(row["guid"]), "talent_groups_count": int(row["talentGroupsCount"]),
                    "active_talent_group": int(row["activeTalentGroup"]), "talent_tree": str(row["talentTree"] or ""),
                    "talents": {}, "glyphs": {}, "known_spells": [], "inventory": []}
            cursor.execute(
                "SELECT c.name, ct.spell, ct.talentGroup FROM characters c JOIN character_talent ct ON ct.guid = c.guid "
                f"WHERE c.name IN ({placeholders})", tuple(names))
            for row in cursor.fetchall():
                entry = state.get(str(row["name"]))
                if entry is not None:
                    entry["talents"].setdefault(int(row["talentGroup"]), []).append(int(row["spell"]))
            cursor.execute(
                "SELECT c.name, cg.talentGroup, cg.glyph1, cg.glyph2, cg.glyph3, cg.glyph4, cg.glyph5, cg.glyph6, "
                "cg.glyph7, cg.glyph8, cg.glyph9 FROM characters c JOIN character_glyphs cg ON cg.guid = c.guid "
                f"WHERE c.name IN ({placeholders})", tuple(names))
            for row in cursor.fetchall():
                entry = state.get(str(row["name"]))
                if entry is not None:
                    entry["glyphs"][int(row["talentGroup"])] = [int(row[f"glyph{i}"] or 0) for i in range(1, 10)]
            cursor.execute(
                "SELECT c.name, cs.spell FROM characters c JOIN character_spell cs ON cs.guid = c.guid "
                f"AND cs.active = 1 AND cs.disabled = 0 WHERE c.name IN ({placeholders})", tuple(names))
            for row in cursor.fetchall():
                entry = state.get(str(row["name"]))
                if entry is not None:
                    entry["known_spells"].append(int(row["spell"]))
            cursor.execute(
                "SELECT c.name, ci.bag, ci.slot, ci.item, ii.itemEntry, ii.owner_guid, ii.count, ii.enchantments "
                "FROM characters c JOIN character_inventory ci ON ci.guid = c.guid "
                "LEFT JOIN item_instance ii ON ii.guid = ci.item "
                f"WHERE c.name IN ({placeholders})", tuple(names))
            for row in cursor.fetchall():
                entry = state.get(str(row["name"]))
                if entry is not None:
                    entry["inventory"].append({
                        "item_guid": int(row["item"]), "bag": int(row["bag"]), "slot": int(row["slot"]),
                        "item_id": int(row.get("itemEntry") or 0), "owner_guid": int(row.get("owner_guid") or 0),
                        "count": int(row.get("count") or 0), "enchantments": str(row.get("enchantments") or "")})
    finally:
        conn.close()
    return state


def loadout_readback_failures(bot: dict[str, Any], observed: dict[str, Any],
                              default_consumables: list[dict[str, Any]],
                              gem_mapping: dict[int, int], dbc_dir: Path) -> list[dict[str, Any]]:
    """Exact comparison of one materialized loadout bot with its DB readback."""
    name = str(bot.get("name") or "")
    if not observed:
        return [{"check": "loadout_character_missing", "bot": name}]
    loadout = bot["loadout"]
    failures: list[dict[str, Any]] = []

    def fail(check: str, **details: Any) -> None:
        failures.append({"check": check, "bot": name, **details})

    guid = int(bot.get("expected_character_guid") or observed.get("guid") or 0)
    if int(observed.get("guid") or 0) != guid:
        fail("loadout_character_guid", expected=guid, actual=observed.get("guid"))
    if int(observed.get("talent_groups_count", -1)) != int(loadout["talent_groups_count"]):
        fail("loadout_talent_groups_count", expected=loadout["talent_groups_count"], actual=observed.get("talent_groups_count"))
    if int(observed.get("active_talent_group", -1)) != int(loadout["active_talent_group"]):
        fail("loadout_active_talent_group", expected=loadout["active_talent_group"], actual=observed.get("active_talent_group"))
    if str(observed.get("talent_tree", "")).split() != expected_talent_tree(bot).split():
        fail("loadout_talent_tree", expected=expected_talent_tree(bot), actual=observed.get("talent_tree"))
    expected_talents = expected_talent_rows(bot)
    actual_talents = {int(group): sorted(spells) for group, spells in (observed.get("talents") or {}).items()}
    for group in sorted(set(expected_talents) | set(actual_talents)):
        if expected_talents.get(group, []) != actual_talents.get(group, []):
            fail("loadout_talent_group_spells", talent_group=group,
                 missing=sorted(set(expected_talents.get(group, [])) - set(actual_talents.get(group, []))),
                 unexpected=sorted(set(actual_talents.get(group, [])) - set(expected_talents.get(group, []))))
    expected_glyphs = {group: slots for group, slots in expected_glyph_rows(bot).items() if any(slots)}
    actual_glyphs = {int(group): list(slots) for group, slots in (observed.get("glyphs") or {}).items()}
    for group in sorted(set(expected_glyphs) | set(actual_glyphs)):
        if expected_glyphs.get(group) != actual_glyphs.get(group):
            fail("loadout_glyph_group", talent_group=group, expected=expected_glyphs.get(group),
                 actual=actual_glyphs.get(group))
    known = set(observed.get("known_spells") or [])
    missing_spells = sorted(set(loadout["known_spell_ids"]) - known)
    if missing_spells:
        fail("loadout_known_spells_missing", missing=missing_spells)
    leaked = sorted(set(loadout["inactive_only_specialization_spell_ids"]) & known)
    if leaked:
        fail("loadout_inactive_group_spells_known", spells=leaked)
    expected_rows = {row["item_guid"]: row for row in expected_inventory(bot, default_consumables, gem_mapping, dbc_dir)}
    actual_rows = {int(row["item_guid"]): row for row in observed.get("inventory") or []}
    for item_guid in sorted(set(expected_rows) - set(actual_rows)):
        fail("loadout_inventory_missing", item_guid=item_guid, kind=expected_rows[item_guid]["kind"])
    for item_guid in sorted(set(actual_rows) - set(expected_rows)):
        fail("loadout_inventory_unexpected", item_guid=item_guid, bag=actual_rows[item_guid].get("bag"),
             slot=actual_rows[item_guid].get("slot"))
    for item_guid in sorted(set(expected_rows) & set(actual_rows)):
        expected, actual = expected_rows[item_guid], actual_rows[item_guid]
        wrong = [field for field in INVENTORY_FIELDS if int(actual.get(field) or 0) != int(expected[field])]
        if int(actual.get("owner_guid") or 0) != guid:
            wrong.append("owner_guid")
        if wrong:
            fail("loadout_inventory_mismatch", item_guid=item_guid, kind=expected["kind"], fields=wrong)
        if expected["kind"] in ("equipped", "bagged"):
            want, have = _payload(expected["enchantments"]), _payload(actual.get("enchantments"))
            offsets = [offset for offset in MODIFIER_OFFSETS
                       if (want[offset] if len(want) > offset else None) != (have[offset] if len(have) > offset else None)]
            if offsets:
                fail("loadout_item_modifiers", item_guid=item_guid, kind=expected["kind"], offsets=offsets)
    return failures


def loadout_readback_summary(bot: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    loadout = bot["loadout"]
    inventory = observed.get("inventory") or []
    return {
        "active_talent_group": {"expected": loadout["active_talent_group"], "actual": observed.get("active_talent_group")},
        "talent_groups_count": {"expected": loadout["talent_groups_count"], "actual": observed.get("talent_groups_count")},
        "talent_groups_observed": sorted(int(group) for group in (observed.get("talents") or {})),
        "glyph_groups_observed": sorted(int(group) for group in (observed.get("glyphs") or {})),
        "bagged_rows_observed": sum(1 for row in inventory if int(row.get("bag") or 0) != 0),
        "bagged_rows_expected": len(loadout["bag_contents"]),
    }
