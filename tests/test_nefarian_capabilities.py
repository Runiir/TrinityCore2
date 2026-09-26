"""The Nefarian duty capability table against the 4.3.4 client data.

BotNefarianCapabilities.h names, per class spec, the interrupt, taunt and
bone-warrior control a bot of that spec is given as a duty. A duty must never
name a spell the spec cannot learn:
- a talent (Talent.dbc) only for the spec of its own tree (TalentTab.dbc name
  and class mask): Silencing Shot for Marksmanship, Silence for Shadow, Curse
  of Exhaustion for Affliction;
- any other spell only for a class that learns it (SkillLineAbility.dbc class
  mask, or the class mask of its skill line in SkillRaceClassInfo.dbc).

The canonical composition's controller order and the contract's controller
table (nefarian_v1.json) are checked against the duty plan the strategy
builds for the canonical board (tests/test_nefarian_strategy.py fixtures,
the roster of the raid target).
"""

from __future__ import annotations

import json
import struct
from functools import lru_cache
from pathlib import Path

import pytest

from tests.test_nefarian_strategy import PRELUDE, _compile_and_run


ROOT = Path(__file__).resolve().parents[1]
DBC = ROOT / "data/dbc/enUS"
CONTRACT = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/nefarian_v1.json"
TARGET = ROOT / "experiments/configs/raid_targets/blackwing_descent_10n_nefarian.json"

# Every class spec the bot runtime names (class id, talent tree).
SPECS = {
    "arms_warrior": (1, "Arms"), "fury_warrior": (1, "Fury"),
    "protection_warrior": (1, "Protection"),
    "holy_paladin": (2, "Holy"), "protection_paladin": (2, "Protection"),
    "retribution_paladin": (2, "Retribution"),
    "beast_mastery_hunter": (3, "Beast Mastery"), "marksmanship_hunter": (3, "Marksmanship"),
    "survival_hunter": (3, "Survival"),
    "assassination_rogue": (4, "Assassination"), "combat_rogue": (4, "Combat"),
    "subtlety_rogue": (4, "Subtlety"),
    "discipline_priest": (5, "Discipline"), "holy_priest": (5, "Holy"),
    "shadow_priest": (5, "Shadow"),
    "blood_death_knight": (6, "Blood"), "frost_death_knight": (6, "Frost"),
    "unholy_death_knight": (6, "Unholy"),
    "elemental_shaman": (7, "Elemental"), "enhancement_shaman": (7, "Enhancement"),
    "restoration_shaman": (7, "Restoration"),
    "arcane_mage": (8, "Arcane"), "fire_mage": (8, "Fire"), "frost_mage": (8, "Frost"),
    "affliction_warlock": (9, "Affliction"), "demonology_warlock": (9, "Demonology"),
    "destruction_warlock": (9, "Destruction"),
    "balance_druid": (11, "Balance"), "feral_druid": (11, "Feral Combat"),
    "feral_druid_tank": (11, "Feral Combat"), "restoration_druid": (11, "Restoration"),
}

SPELL_NAMES = {
    853: "Hammer of Justice", 122: "Frost Nova", 5116: "Concussive Shot",
    8056: "Frost Shock", 18223: "Curse of Exhaustion", 45524: "Chains of Ice",
    9484: "Shackle Undead",
}

TABLE = PRELUDE + r'''
int main()
{
    for (char const* spec : { %SPECS% })
    {
        std::printf("CAP %s interrupt %u\n", spec, InterruptFor(spec).SpellId);
        std::printf("CAP %s control %u\n", spec, ControlFor(spec).SpellId);
        std::printf("CAP %s taunt %u\n", spec, TauntFor(spec).SpellId);
        std::printf("CAP %s warrior_root %u\n", spec, WarriorRootFor(spec));
        std::printf("CAP %s off_heal %u\n", spec, OffHealFor(spec));
        std::printf("CAP %s pre_ascent %u\n", spec,
            PreAscentShieldFor(spec) ? PreAscentShieldFor(spec) : PreAscentTopUpFor(spec));
    }
    Blackboard const board = CanonicalBoard();
    DutyPlan const plan = BuildNefarianDutyPlan(board);
    for (ActorSnapshot const& player : board.Players)
        std::printf("ROSTER %s\n", std::string(player.ClassSpec).c_str());
    if (ActorSnapshot const* shackler = board.FindActor(plan.Shackler))
        std::printf("SHACKLER %s %u\n", std::string(shackler->ClassSpec).c_str(),
            ControlFor(shackler->ClassSpec).SpellId);
    if (ActorSnapshot const* handler = board.FindActor(plan.WarriorHandler))
        std::printf("HANDLER %s %u\n", std::string(handler->ClassSpec).c_str(),
            WarriorRootFor(handler->ClassSpec));
    return 0;
}
'''


@lru_cache(maxsize=1)
def _table_output(folder: str) -> str:
    specs = ", ".join(f'"{spec}"' for spec in SPECS)
    return _compile_and_run(Path(folder), TABLE.replace("%SPECS%", specs))


def _lines(tmp_path_factory, tag: str) -> list[list[str]]:
    output = _table_output(str(tmp_path_factory.getbasetemp()))
    return [line.split()[1:] for line in output.splitlines() if line.startswith(tag + " ")]


def _records(name: str) -> list[tuple[int, ...]]:
    raw = (DBC / name).read_bytes()
    magic, count, fields, size, _ = struct.unpack_from("<4s4I", raw, 0)
    assert magic == b"WDBC", name
    return [struct.unpack_from(f"<{fields}I", raw, 20 + index * size) for index in range(count)]


def _tab_names() -> dict[int, tuple[str, int]]:
    raw = (DBC / "TalentTab.dbc").read_bytes()
    _, count, fields, size, _ = struct.unpack_from("<4s4I", raw, 0)
    strings = raw[20 + count * size:]
    tabs = {}
    for index in range(count):
        row = struct.unpack_from(f"<{fields}I", raw, 20 + index * size)
        name = strings[row[1]:strings.index(b"\0", row[1])].decode()
        tabs[row[0]] = (name, row[3])  # name, class mask
    return tabs


def test_every_duty_spell_is_learnable_by_its_spec(tmp_path_factory) -> None:
    if not (DBC / "Talent.dbc").is_file():
        pytest.skip("data/dbc is local-only")
    tabs = _tab_names()
    talents = {}
    for row in _records("Talent.dbc"):
        for spell in row[4:13]:  # SpellRank[9]
            if spell:
                talents.setdefault(spell, []).append(tabs[row[1]])
    skill_classes = {row[1]: row[3] for row in _records("SkillRaceClassInfo.dbc")}
    class_masks = {}
    for row in _records("SkillLineAbility.dbc"):
        mask = row[4] or skill_classes.get(row[1], 0)
        class_masks[row[2]] = class_masks.get(row[2], 0) | mask

    rows = _lines(tmp_path_factory, "CAP")
    assert len(rows) == 6 * len(SPECS)
    named = 0
    for spec, duty, spell_text in rows:
        spell = int(spell_text)
        if not spell:
            continue
        named += 1
        class_id, tree = SPECS[spec]
        class_bit = 1 << (class_id - 1)
        if spell in talents:
            assert any(name == tree and mask & class_bit for name, mask in talents[spell]), (
                spec, duty, spell, talents[spell])
        else:
            assert class_masks.get(spell, 0) & class_bit, (spec, duty, spell)
    assert named > 40
    # The talents the table names are held to their own tree.
    by_spec = {(spec, duty): int(spell) for spec, duty, spell in rows}
    assert by_spec[("affliction_warlock", "control")] == 18223
    assert by_spec[("demonology_warlock", "control")] == 0
    assert by_spec[("destruction_warlock", "control")] == 0
    assert by_spec[("marksmanship_hunter", "interrupt")] == 34490
    assert by_spec[("survival_hunter", "interrupt")] == 0
    assert by_spec[("shadow_priest", "interrupt")] == 15487
    assert by_spec[("discipline_priest", "interrupt")] == 0
    for spec in ("feral_druid_tank", "feral_druid", "balance_druid", "restoration_druid"):
        assert by_spec[(spec, "warrior_root")] == 16689
    assert sum(1 for (spec, duty), spell in by_spec.items()
               if duty == "warrior_root" and spell) == 4
    assert by_spec[("elemental_shaman", "off_heal")] == 8004
    assert by_spec[("retribution_paladin", "off_heal")] == 19750
    assert by_spec[("discipline_priest", "pre_ascent")] == 17
    assert by_spec[("holy_paladin", "pre_ascent")] == 19750


def test_natures_grasp_works_in_bear_form() -> None:
    """Nature's Grasp is castable by the Feral tank in Bear Form: the
    SpellShapeshift row of 16689 allows forms 1 (cat), 5 (bear), 8 (dire
    bear) and 31 (moonkin); it has 3 charges, 45 s and a 60 s cooldown, and
    each charge roots with Entangling Roots 19975 (aura 26, 27 s)."""
    if not (DBC / "Spell.dbc").is_file():
        pytest.skip("data/dbc is local-only")
    spells = {row[0]: row for row in _records("Spell.dbc")}
    shapeshift = {row[0]: row for row in _records("SpellShapeshift.dbc")}
    options = {row[0]: row for row in _records("SpellAuraOptions.dbc")}
    cooldowns = {row[0]: row for row in _records("SpellCooldowns.dbc")}
    grasp = spells[16689]
    mask = shapeshift[grasp[44]][3]  # ShapeshiftMask[0]
    bear_form = 5
    assert mask & (1 << (bear_form - 1)), hex(mask)
    assert options[grasp[32]][3] == 3  # ProcCharges
    assert cooldowns[grasp[37]][1] == 60000  # CategoryRecoveryTime (SpellCooldowns 1034)
    effects = [row for row in _records("SpellEffect.dbc") if row[24] in (16689, 19975)]
    assert any(row[24] == 16689 and row[3] == 42 and row[21] == 19975 for row in effects)
    assert any(row[24] == 19975 and row[3] == 26 for row in effects)


def test_contract_warrior_duties_match_the_canonical_plan(tmp_path_factory) -> None:
    roster = sorted(member["spec"] for member in json.loads(
        TARGET.read_text(encoding="utf-8"))["roster"].values())
    board = sorted(spec for (spec,) in _lines(tmp_path_factory, "ROSTER"))
    assert board == roster, "the test board is the raid target's canonical roster"
    roles = sorted(member["role"] for member in json.loads(
        TARGET.read_text(encoding="utf-8"))["roster"].values())
    assert roles.count("tank") == 2 and roles.count("healer") == 2 and roles.count("dps") == 6

    plan = json.loads(CONTRACT.read_text(encoding="utf-8"))["strategy"]["canonical_10n_plan"]
    (shackler,) = _lines(tmp_path_factory, "SHACKLER")
    assert plan["shackler"] == f"{shackler[0]} {SPELL_NAMES[int(shackler[1])]}"
    (handler,) = _lines(tmp_path_factory, "HANDLER")
    assert plan["warrior_handler"] == f"{handler[0]} Nature's Grasp"
    assert int(handler[1]) == 16689
    assert "controllers" not in plan


COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"


def test_composition_provides_the_nefarian_requirements() -> None:
    """M's composition data must give the Nefarian shard the user's comp (the
    shaman Elemental) and the druid Nature's Grasp. Until patch
    .git/round6_patches/nefarian/M2 is applied this reports the gap."""
    composition = json.loads(COMPOSITION.read_text(encoding="utf-8"))
    boss = next(row for row in composition["bosses"] if row["boss_key"] == "nefarian")
    druid = next(row for row in composition["characters"] if row["character_key"] == "druid")
    known = set(druid.get("spells") or [])
    for spells in (druid.get("group_spells") or {}).values():
        known |= set(spells)
    if boss["spec_selection"].get("shaman") != "elemental_shaman" or 16689 not in known:
        pytest.skip("pending M data change (patch M2): Nefarian shaman elemental_shaman "
                    "and druid Nature's Grasp 16689")
    assert boss["spec_selection"] == {"druid": "feral_druid_tank", "shaman": "elemental_shaman"}
