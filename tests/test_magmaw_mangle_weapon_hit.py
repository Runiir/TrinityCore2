"""Mangle's weapon hit is 150% of a Magmaw swing, as the 4.3.4 client says.

SpellMgrCorrectionsPart04.cpp used to set 89773/91912/94616/94617 effect 2 to
100%, citing an unverifiable sniff. The pinned 4.3.4 client has 150, and the
historical 10N WCL initial hit fits 150% of an ordinary Magmaw roll at the
calibrated DamageModifier while 100% does not.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPELLS = ROOT / "src/server/game/Spells"
LEDGER = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/magmaw_ledger_v1.json"
CALIBRATION = ROOT / "experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json"
DBC = ROOT / "data/dbc/enUS"
MANGLE = (89773, 91912, 94616, 94617)


def test_no_correction_overrides_the_mangle_weapon_percent() -> None:
    for path in sorted(SPELLS.glob("SpellMgrCorrections*.cpp")):
        source = path.read_text(encoding="utf-8")
        for block in re.findall(r"ApplySpellFix\(\{(.*?)\}", source, re.S):
            ids = {int(token) for token in re.findall(r"\d+", block)}
            assert not ids & set(MANGLE), (path, block)


def test_wcl_initial_hit_fits_150_percent_not_100() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    mangle = next(v for v in ledger["values"] if v["key"] == "mangle")
    hit = mangle["observed_10n_damage"]["initial_hit"]["wcl_unmitigated_estimate"]
    assert hit == 240338
    magmaw = json.loads(CALIBRATION.read_text(encoding="utf-8"))["creatures"]["41570"]
    roll = magmaw["evidence"]["native_roll_at_modifier_1"]
    bounds = magmaw["evidence"]["bounds"]
    # 89773 has SPELL_ATTR3_IGNORE_CASTER_MODIFIERS: U = roll * modifier * pct.
    for modifier in (bounds["lower"], magmaw["damage_modifier"], bounds["upper"]):
        at_150 = hit / (modifier * 1.5)
        at_100 = hit / modifier
        assert roll["min"] <= at_150 <= roll["max"]
        assert at_100 > roll["max"]


@pytest.mark.skipif(not (DBC / "Spell.dbc").exists(), reason="pinned DBC not extracted")
def test_client_weapon_percent_is_150_in_every_mode() -> None:
    sys.path.insert(0, str(ROOT))
    from tools.bot_ml.build_validation_provisioning import load_wdbc_values

    spells = {r[0]: r for r in load_wdbc_values(
        DBC / "Spell.dbc", "niiiiiiiiiiiiiiifiiiissxxiixxifiiiiiiixiiiiiiiii")}
    effects: dict[int, list[list[int]]] = {}
    for row in load_wdbc_values(DBC / "SpellEffect.dbc", "nifiiiffiiiiiifiifiiiiiiiix"):
        effects.setdefault(row[24], []).append(row)
    for spell_id in MANGLE:
        weapon = next(e for e in effects[spell_id] if e[25] == 2)
        # SPELL_EFFECT_WEAPON_PERCENT_DAMAGE 31, 150%, no die.
        assert (weapon[1], weapon[5], weapon[9]) == (31, 150, 0)
        attributes3 = spells[spell_id][4]
        assert attributes3 & 0x20000000  # SPELL_ATTR3_IGNORE_CASTER_MODIFIERS
        assert attributes3 & 0x00040000  # SPELL_ATTR3_ALWAYS_HIT
