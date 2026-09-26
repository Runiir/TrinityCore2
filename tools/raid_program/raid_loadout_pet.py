"""Lawful hunter pets for a raid composition, from the client DBCs and the TDB world dump.

A composition may declare its hunter's active pet (raid_shard_plan.character_pet). This module checks
such a pet the way the 4.3.4 server builds and loads one:

- family: CreatureFamily.dbc (skill lines, PetTalentType, CategoryEnumID). The creature template
  (world.creature_template) must be a tameable beast of that family (type 1, type_flags 0x1). An exotic
  template (type_flags 0x10000) needs Beast Mastery's Beast Mastery talent 53270 (Player::CanTameExoticPets),
  so a non-Beast-Mastery hunter may not own one.
- level-up spells: the family's SkillLineAbility rows with AcquireMethod 2 (AutomaticCharLevel) and a
  SpellLevel, learned up to the pet's level (SpellMgr::LoadPetLevelupSpellMap, Pet::InitLevelupSpellsForLevel).
- talents: the pet talent tab whose CategoryEnumID holds bit PetTalentType (Player::LearnPetTalent).
  One rank per talent; a talent with a CategoryMask must name the family's CategoryEnumID bit (the Dash
  and Dive variants); every lower tier holds MAX_PET_TALENT_RANK (3) points per tier level; the
  prerequisite talent holds its rank; the rank costs (DBCManager::GetTalentSpellCost: rank + 1) stay
  within Pet::GetMaxTalentPointsForLevel ((level - 16) / 4 at level 20 or more).
- autocast state: a passive spell is persisted ACT_PASSIVE (1), any other ACT_ENABLED (193) or
  ACT_DISABLED (129), as Pet::_SaveSpells writes them.

Every other pet spell must be one of the family's automatically acquired (AcquireMethod 2) skill-line
spells at or below the pet's level. Skill line 270 (Pet - Hunter) is shared by all families and lists
the talents of all three trees, so another tree's talent is refused by tab, not accepted by skill line.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.bot_ml.build_validation_provisioning import load_wdbc_values

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DBC_DIR = REPO_ROOT / "data/dbc/enUS"
TDB_WORLD = REPO_ROOT / "data/TDB_full_434.22011_2022_01_09/TDB_full_world_434.22011_2022_01_09.sql"
CREATURE_FAMILY_FMT = "nfifiiiiiisi"  # CreatureFamilyfmt with CategoryEnumID (9) and Name (10) read
SKILL_LINE_ABILITY_FMT = "n" + "i" * 13
SPELL_FMT = "niiiiiiiiiiiiiiifiiiissxxiixxifiiiiiiixiiiiiiiii"  # SpellEntryfmt
SPELL_LEVELS_FMT = "niii"
TALENT_FMT = "n" + "i" * 18  # TalentEntryfmt with Flags, RequiredSpellID and CategoryMask[2] read
TALENT_TAB_FMT = "nsiiiissiii"
SPELL_EFFECT_FMT = "nifiiiffiiiiiifiifiiiiiiiix"
ACQUIRE_AUTOMATIC_CHAR_LEVEL = 2
SPELL_ATTR0_PASSIVE = 0x40
ACT_PASSIVE, ACT_DISABLED, ACT_ENABLED = 0x01, 0x81, 0xC1
MAX_PET_TALENT_RANK = 3
CREATURE_TYPE_BEAST = 1
TYPE_FLAG_TAMEABLE, TYPE_FLAG_EXOTIC = 0x1, 0x10000
_CACHE: dict[tuple[str, Path], Any] = {}


def _cached(name: str, dbc_dir: Path, build):
    key = (name, Path(dbc_dir).resolve())
    if key not in _CACHE:
        _CACHE[key] = build(Path(dbc_dir))
    return _CACHE[key]


def families(dbc_dir: Path = DEFAULT_DBC_DIR) -> dict[int, dict[str, Any]]:
    return _cached("families", dbc_dir, lambda d: {
        int(row[0]): {"name": row[10], "skill_lines": [int(row[5]), int(row[6])],
                      "talent_type": int(row[8]), "category": int(row[9])}
        for row in load_wdbc_values(d / "CreatureFamily.dbc", CREATURE_FAMILY_FMT)})


def spells(dbc_dir: Path = DEFAULT_DBC_DIR) -> dict[int, dict[str, Any]]:
    def build(d: Path) -> dict[int, dict[str, Any]]:
        levels = {int(row[0]): int(row[3]) for row in load_wdbc_values(d / "SpellLevels.dbc", SPELL_LEVELS_FMT)}
        return {int(row[0]): {"name": row[21], "rank": row[22], "passive": bool(int(row[1]) & SPELL_ATTR0_PASSIVE),
                              "level": levels.get(int(row[41]), 0)}
                for row in load_wdbc_values(d / "Spell.dbc", SPELL_FMT)}
    return _cached("spells", dbc_dir, build)


def skill_line_spells(dbc_dir: Path = DEFAULT_DBC_DIR) -> dict[int, list[tuple[int, int]]]:
    """skill line -> [(spell, acquire method)] of SkillLineAbility.dbc."""
    def build(d: Path) -> dict[int, list[tuple[int, int]]]:
        lines: dict[int, list[tuple[int, int]]] = {}
        for row in load_wdbc_values(d / "SkillLineAbility.dbc", SKILL_LINE_ABILITY_FMT):
            lines.setdefault(int(row[1]), []).append((int(row[2]), int(row[9])))
        return lines
    return _cached("skill_lines", dbc_dir, build)


def aura_signatures(dbc_dir: Path = DEFAULT_DBC_DIR) -> dict[int, list[tuple[int, int, int, int]]]:
    """spell -> [(aura, misc value, base points, triggered spell)] of SpellEffect.dbc."""
    def build(d: Path) -> dict[int, list[tuple[int, int, int, int]]]:
        effects: dict[int, list[tuple[int, int, int, int]]] = {}
        for row in load_wdbc_values(d / "SpellEffect.dbc", SPELL_EFFECT_FMT):
            effects.setdefault(int(row[24]), []).append((int(row[3]), int(row[12]), int(row[5]), int(row[21])))
        return effects
    return _cached("aura_signatures", dbc_dir, build)


def spell_auras(spell: int, dbc_dir: Path = DEFAULT_DBC_DIR, seen: set[int] | None = None) -> set[tuple[int, int, int]]:
    """(aura, misc value, base points) a spell applies, following triggered spells."""
    seen = set() if seen is None else seen
    if spell in seen:
        return set()
    seen.add(spell)
    auras: set[tuple[int, int, int]] = set()
    for aura, misc, points, trigger in aura_signatures(dbc_dir).get(spell, []):
        if aura:
            auras.add((aura, misc, points))
        if trigger:
            auras |= spell_auras(trigger, dbc_dir, seen)
    return auras


def family_spells(family_id: int, dbc_dir: Path = DEFAULT_DBC_DIR, acquire: int | None = None) -> set[int]:
    """Spells of the family's skill lines, optionally only those with this AcquireMethod.

    Skill line 270 (Pet - Hunter) is shared by every family and holds the talents of all three pet trees,
    so a talent is judged by its talent tab (validate_hunter_pet), never by skill-line membership.
    """
    lines = skill_line_spells(dbc_dir)
    return {spell for line in families(dbc_dir)[family_id]["skill_lines"] if line
            for spell, method in lines.get(line, []) if acquire is None or method == acquire}


def levelup_spells(family_id: int, level: int, dbc_dir: Path = DEFAULT_DBC_DIR) -> set[int]:
    """The family's level-up spells a pet of this level knows (SpellMgr::LoadPetLevelupSpellMap)."""
    known = spells(dbc_dir)
    lines = skill_line_spells(dbc_dir)
    return {spell for line in families(dbc_dir)[family_id]["skill_lines"] if line
            for spell, acquire in lines.get(line, [])
            if acquire == ACQUIRE_AUTOMATIC_CHAR_LEVEL and spell in known
            and 0 < known[spell]["level"] <= level}


@dataclass(frozen=True)
class Talent:
    talent_id: int
    tab: int
    tier: int
    ranks: tuple[int, ...]
    prereq: int
    prereq_rank: int
    category_mask: int


def talent_tab(family_id: int, dbc_dir: Path = DEFAULT_DBC_DIR) -> int:
    """The pet talent tab of a family: CategoryEnumID holds bit PetTalentType (Player::LearnPetTalent)."""
    talent_type = families(dbc_dir)[family_id]["talent_type"]
    if talent_type < 0:
        raise ValueError(f"family {family_id} is not a hunter pet family")
    (tab,) = [tab for tab, mask in pet_tabs(dbc_dir) if mask & (1 << talent_type)]
    return tab


def pet_tabs(dbc_dir: Path = DEFAULT_DBC_DIR) -> list[tuple[int, int]]:
    """(tab, CategoryEnumID) of the hunter pet talent tabs (no class mask): Ferocity, Tenacity, Cunning."""
    return _cached("pet_tabs", dbc_dir, lambda d: [
        (int(row[0]), int(row[4])) for row in load_wdbc_values(d / "TalentTab.dbc", TALENT_TAB_FMT)
        if int(row[3]) == 0 and int(row[4])])


def talents(dbc_dir: Path = DEFAULT_DBC_DIR) -> list[Talent]:
    return _cached("talents", dbc_dir, lambda d: [
        Talent(int(row[0]), int(row[1]), int(row[2]), tuple(int(value) for value in row[4:9] if int(value)),
               int(row[9]), int(row[12]), (int(row[17]) & 0xFFFFFFFF) | ((int(row[18]) & 0xFFFFFFFF) << 32))
        for row in load_wdbc_values(d / "Talent.dbc", TALENT_FMT)])


def max_talent_points(level: int) -> int:
    """Pet::GetMaxTalentPointsForLevel without owner auras (only Beast Mastery adds points)."""
    return (level - 16) // 4 if level >= 20 else 0


def pet_spell_rows(pet: Mapping[str, Any]) -> list[tuple[int, int]]:
    return [(int(row["id"]), int(row.get("active", 1))) if isinstance(row, Mapping) else (int(row), 1)
            for row in pet.get("spells") or []]


def creature_templates(entries: Iterable[int] = (), families: Iterable[int] = (),
                       path: Path = TDB_WORLD) -> dict[int, dict[str, Any]]:
    """name, family, type, type_flags and modelid1 of world.creature_template rows, by entry or family."""
    from tools.raid_program.raid_shard_anchor_clearance import _sql_values

    wanted, wanted_families = {int(entry) for entry in entries}, {int(family) for family in families}
    columns: list[str] = []
    rows: list[list[str]] = []
    creating = False
    with Path(path).open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("CREATE TABLE `creature_template`"):
                creating = True
            elif creating and line.startswith("  `"):
                columns.append(line.split("`")[1])
            elif creating and line.startswith(")"):
                creating = False
            elif line.startswith("INSERT INTO `creature_template` "):
                rows.extend(_sql_values(line))
    templates = {}
    for row in rows:
        record = dict(zip(columns, row))
        if int(record["entry"]) not in wanted and int(record["family"]) not in wanted_families:
            continue
        templates[int(record["entry"])] = {"name": record["name"], "family": int(record["family"]),
                                           "type": int(record["type"]), "type_flags": int(record["type_flags"]),
                                           "modelid1": int(record["modelid1"])}
    return templates


def validate_hunter_pet(pet: Mapping[str, Any], family_id: int, dbc_dir: Path = DEFAULT_DBC_DIR,
                        template: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Failures (empty when lawful) and the pet's talent summary."""
    failures: list[str] = []
    family = families(dbc_dir)[family_id]
    level = int(pet.get("level") or 0)
    rows = pet_spell_rows(pet)
    known = dict(rows)
    catalog = spells(dbc_dir)
    if template is not None:
        if template.get("family") != family_id:
            failures.append("template_family")
        if template.get("type") != CREATURE_TYPE_BEAST or not template.get("type_flags", 0) & TYPE_FLAG_TAMEABLE:
            failures.append("template_not_tameable")
        if template.get("type_flags", 0) & TYPE_FLAG_EXOTIC:
            failures.append("template_exotic")
    for spell in sorted(levelup_spells(family_id, level, dbc_dir) - set(known)):
        failures.append(f"levelup_spell_missing:{spell}")
    tab = talent_tab(family_id, dbc_dir)
    by_spell = {spell: talent for talent in talents(dbc_dir) if talent.tab == tab for spell in talent.ranks}
    other_trees = {spell for talent in talents(dbc_dir) for spell in talent.ranks
                   if talent.tab != tab and talent.tab in {pet_tab for pet_tab, _mask in pet_tabs(dbc_dir)}}
    auto_acquired = family_spells(family_id, dbc_dir, ACQUIRE_AUTOMATIC_CHAR_LEVEL)
    chosen: dict[int, tuple[Talent, int]] = {}
    for spell, active in rows:
        if spell not in catalog:
            failures.append(f"spell_unknown:{spell}")
            continue
        expected = (ACT_PASSIVE,) if catalog[spell]["passive"] else (ACT_ENABLED, ACT_DISABLED)
        if active not in expected:
            failures.append(f"active_state:{spell}:{active}")
        talent = by_spell.get(spell)
        if talent is None:
            # Not a talent of the family's tree: another tree's talent, or a family spell the pet learns
            # only by level (AcquireMethod 2); everything else is out of reach of this pet.
            if spell in other_trees:
                failures.append(f"talent_of_other_tree:{spell}")
            elif spell not in auto_acquired:
                failures.append(f"spell_not_auto_acquired:{spell}")
            elif catalog[spell]["level"] > level:
                failures.append(f"spell_above_level:{spell}")
            continue
        if talent.category_mask and not talent.category_mask & (1 << family["category"]):
            failures.append(f"talent_not_for_family:{spell}")
        if talent.talent_id in chosen:
            failures.append(f"talent_two_ranks:{talent.talent_id}")
        chosen[talent.talent_id] = (talent, talent.ranks.index(spell) + 1)
    points_by_tier: dict[int, int] = {}
    for talent, rank in chosen.values():
        points_by_tier[talent.tier] = points_by_tier.get(talent.tier, 0) + rank
    for talent, rank in chosen.values():
        below = sum(points for tier, points in points_by_tier.items() if tier < talent.tier)
        if below < talent.tier * MAX_PET_TALENT_RANK:
            failures.append(f"talent_tier_locked:{talent.talent_id}")
        if talent.prereq:
            prereq = chosen.get(talent.prereq)
            if prereq is None or prereq[1] < talent.prereq_rank + 1:
                failures.append(f"talent_prereq:{talent.talent_id}")
    spent = sum(points_by_tier.values())
    if spent > max_talent_points(level):
        failures.append(f"talent_points:{spent}>{max_talent_points(level)}")
    bar = [int(value) for value in str(pet.get("actionbar") or "").split()]
    for state, value in zip(bar[0::2], bar[1::2]):
        if state in (ACT_ENABLED, ACT_DISABLED) and value not in known:
            failures.append(f"actionbar_spell_unknown:{value}")
    return {"failures": failures, "family": family["name"], "talent_tab": tab, "talent_points": spent,
            "max_talent_points": max_talent_points(level),
            "talents": sorted((talent.talent_id, rank) for talent, rank in chosen.values())}
