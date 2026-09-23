"""Blood DK native fidelity: Dancing Rune Weapon scaling and Glyph of Death Strike.

Pins the 4.3.4 client facts, the guardian branch that applies the native rune
weapon scaling carriers, and replays the extracted native C++ (the creature
normalized weapon-damage path and the glyph math) with stub objects. The
fixtures do not model aura application, combat rolls or spell_script_names.
"""
from __future__ import annotations

import re
import struct
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DBC = ROOT / "data/dbc/enUS"
INIT = ROOT / "src/server/game/Entities/Pet/GuardianInitialization.cpp"
GUARDIAN_STATS = ROOT / "src/server/game/Entities/Unit/GuardianStatSystem.cpp"
CREATURE_STATS = ROOT / "src/server/game/Entities/Unit/CreatureStatSystem.cpp"
SUMMON_HEADER = ROOT / "src/server/game/Entities/Creature/TemporarySummon.h"
SPELLS = ROOT / "src/server/scripts/Spells"
GLYPHS = SPELLS / "spell_dk_glyphs.cpp"

RUNE_WEAPON_ENTRY = 27893
RUNE_WEAPON_SCALING_02 = 51906
DK_PET_SCALING_03 = 61697
DK_PET_SCALING_05 = 110474
GLYPH_OF_DEATH_STRIKE = 59336


def extract(source: str, signature: str) -> str:
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def compile_and_run(tmp_path: Path, name: str, code: str, *args: str) -> str:
    source = tmp_path / f"{name}.cpp"
    source.write_text(code)
    binary = tmp_path / name
    result = subprocess.run(["c++", "-std=c++17", str(source), "-o", str(binary)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(binary), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def _wdbc(name: str) -> tuple[list[tuple[int, ...]], bytes]:
    data = (DBC / name).read_bytes()
    magic, count, fields, size, _ = struct.unpack_from("<4s4i", data)
    assert magic == b"WDBC" and size == fields * 4
    return list(struct.iter_unpack(f"<{fields}i", data[20:20 + count * size])), data[20 + count * size:]


def _text(block: bytes, offset: int) -> str:
    return block[offset:block.index(b"\0", offset)].decode()


@pytest.mark.skipif(not (DBC / "Spell.dbc").exists(), reason="pinned DBC not extracted")
def test_native_client_facts_for_rune_weapon_and_glyph():
    wanted = {49028, 81256, RUNE_WEAPON_SCALING_02, DK_PET_SCALING_03, DK_PET_SCALING_05,
              GLYPH_OF_DEATH_STRIKE, 49998}
    rows, strings = _wdbc("Spell.dbc")
    spell = {r[0]: r for r in rows if r[0] in wanted}
    assert set(spell) == wanted
    effects: dict[int, dict[int, tuple[int, int, int, int]]] = {}
    for e in _wdbc("SpellEffect.dbc")[0]:
        if e[24] in wanted:
            # (effect, aura, base points, misc value) by effect index
            effects.setdefault(e[24], {})[e[25]] = (e[1], e[3], e[5], e[12])

    # 49028 summons the Rune Weapon guardian (creature 27893).
    assert effects[49028][0] == (28, 0, 1, RUNE_WEAPON_ENTRY)
    # 51906: MOD_DAMAGE_DONE physical, MELEE_SLOW, MOD_DAMAGE_PERCENT_DONE -50 all schools.
    assert _text(strings, spell[RUNE_WEAPON_SCALING_02][21]) == "Death Knight Rune Weapon Scaling 02"
    assert effects[RUNE_WEAPON_SCALING_02] == {0: (6, 13, 0, 1), 1: (6, 193, 0, 0), 2: (6, 79, -50, 127)}
    # The live 4.3.4 tooltip quotes that third effect as the copy's reduction.
    assert "doing the same attacks as the Death Knight but for $51906s3% reduced damage" in \
        _text(strings, spell[81256][23])
    # DK guardian hit (MOD_HIT_CHANCE, MOD_SPELL_HIT_CHANCE) and crit (MOD_CRIT_PCT) carriers.
    assert _text(strings, spell[DK_PET_SCALING_03][21]) == "Death Knight Pet Scaling 03"
    assert effects[DK_PET_SCALING_03][0][:2] == (6, 54) and effects[DK_PET_SCALING_03][1][:2] == (6, 55)
    assert _text(strings, spell[DK_PET_SCALING_05][21]) == "Death Knight Pet Scaling 05"
    assert effects[DK_PET_SCALING_05][0] == (6, 290, 0, 0)

    # Glyph of Death Strike: dummy +2 per step, dummy cap 40.
    assert _text(strings, spell[GLYPH_OF_DEATH_STRIKE][21]) == "Glyph of Death Strike"
    assert _text(strings, spell[GLYPH_OF_DEATH_STRIKE][23]) == (
        "Increases your Death Strike's damage by $59336s1% for every 5 Runic Power you currently "
        "have (up to a maximum of $59336s2%).  The Runic Power is not consumed by this effect.")
    assert effects[GLYPH_OF_DEATH_STRIKE] == {0: (6, 4, 2, 14), 1: (6, 4, 40, 0)}
    assert _text(strings, spell[49998][21]) == "Death Strike"
    glyphs = _wdbc("GlyphProperties.dbc")[0]
    assert any(g[1] == GLYPH_OF_DEATH_STRIKE for g in glyphs)


def test_rune_weapon_branch_applies_native_carriers_and_no_extra_half_or_ap():
    source = INIT.read_text()
    assert len(source.splitlines()) < 1000
    assert re.search(rf"ENTRY_RUNIC_WEAPON\s*=\s*{RUNE_WEAPON_ENTRY},", SUMMON_HEADER.read_text())
    for name, value in (("SPELL_DK_RUNE_WEAPON_SCALING_02", RUNE_WEAPON_SCALING_02),
                        ("SPELL_DK_PET_SCALING_03", DK_PET_SCALING_03),
                        ("SPELL_DK_PET_SCALING_05", DK_PET_SCALING_05)):
        assert len(re.findall(rf"\b{name}\s*=\s*{value}\b", source)) == 1
    branch = extract(source, "case ENTRY_RUNIC_WEAPON:")
    assert "SetBaseAttackTime(BASE_ATTACK, cinfo->BaseAttackTime);" in branch
    assert "SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, 0.0f);" in branch
    assert "SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, 0.0f);" in branch
    assert "AddAura(scaling, this);" in branch
    # The 0.5 lives in 51906 EFFECT_2; neither guardian file restates it, and the
    # stat system gives the rune weapon no owner attack power (already inside
    # 51906 EFFECT_0), so a copy is never double-scaled.
    assert not re.search(r"(?<![\d.])0?\.5f?\b", re.sub(r"//.*", "", branch))
    assert "ENTRY_RUNIC_WEAPON" not in GUARDIAN_STATS.read_text()
    assert source.count("ENTRY_RUNIC_WEAPON") == 1

    # The carriers' amount scripts that the branch relies on stay registered.
    pet = (SPELLS / "spell_pet.cpp").read_text()
    for script in ("spell_dk_rune_weapon_scaling_02", "spell_dk_pet_scaling_03", "spell_dk_pet_scaling_05"):
        assert f"RegisterSpellScript({script});" in pet
    rune = extract(pet, "class spell_dk_rune_weapon_scaling_02 : public AuraScript")
    damage = extract(rune, "void CalculateDamageDoneAmount(")
    assert "amount += owner->CalculateDamage(BASE_ATTACK, true, true);" in damage


def test_rune_weapon_branch_replay_is_idempotent(tmp_path):
    source = INIT.read_text()
    enum = extract(source, "enum RuneWeaponScaling : uint32") + ";"
    branch = extract(source, "case ENTRY_RUNIC_WEAPON:")
    code = r'''
#include <cassert>
#include <cstdint>
#include <vector>
#include <algorithm>
using uint32 = std::uint32_t;
constexpr int ENTRY_RUNIC_WEAPON = 27893, BASE_ATTACK = 0, MINDAMAGE = 0, MAXDAMAGE = 1;
''' + enum + r'''
struct CreatureTemplate { uint32 BaseAttackTime = 3500; };
struct Guardian {
    uint32 attackTime = 2000; float weapon[2] = { 64.f, 106.f }; std::vector<uint32> auras;
    void SetBaseAttackTime(int, uint32 v) { attackTime = v; }
    void SetBaseWeaponDamage(int, int k, float v) { weapon[k] = v; }
    bool HasAura(uint32 id) const { return std::find(auras.begin(), auras.end(), id) != auras.end(); }
    void AddAura(uint32 id, Guardian*) { auras.push_back(id); }
    void Init(CreatureTemplate const* cinfo) { switch (ENTRY_RUNIC_WEAPON) {
''' + branch + r'''
    } }
};
int main() {
    CreatureTemplate cinfo; Guardian weapon;
    weapon.Init(&cinfo); weapon.Init(&cinfo);
    assert(weapon.attackTime == 3500);
    assert(weapon.weapon[0] == 0.f && weapon.weapon[1] == 0.f);
    assert((weapon.auras == std::vector<uint32>{ 51906, 61697, 110474 }));
}
'''
    compile_and_run(tmp_path, "rune_weapon_branch", code)


def test_rune_weapon_normalized_strike_is_half_the_owner_weapon(tmp_path):
    """Replay Creature::CalculateMinMaxDamage (normalized specials) for the rune weapon.

    51906 EFFECT_0 lands in UNIT_MOD_DAMAGE_MAINHAND TOTAL_VALUE (the owner's
    normalized main-hand roll) and EFFECT_2 in TOTAL_PCT (0.5). Own weapon is 0
    and own attack power is the guardian's (22 - 20) * 2 = 4.
    """
    native = extract(CREATURE_STATS.read_text(),
                     "void Creature::CalculateMinMaxDamage(WeaponAttackType attType")
    code = r'''
#include <cassert>
#include <cstdio>
#include <initializer_list>
enum WeaponAttackType { BASE_ATTACK, OFF_ATTACK, RANGED_ATTACK };
enum UnitMods { UNIT_MOD_DAMAGE_MAINHAND, UNIT_MOD_DAMAGE_OFFHAND, UNIT_MOD_DAMAGE_RANGED };
enum { BASE_VALUE, TOTAL_VALUE }; enum { BASE_PCT, TOTAL_PCT }; enum { MINDAMAGE, MAXDAMAGE };
struct CreatureTemplate { float BaseVariance = 1.f, RangeVariance = 1.f, ModDamage = 1.f; };
struct Creature {
    CreatureTemplate tmpl; float weapon[2] = { 0.f, 0.f }, attackPower = 4.f, attackTime = 3500.f;
    float flat[2] = { 0.f, 0.f }, pct[2] = { 1.f, 1.f };
    CreatureTemplate const* GetCreatureTemplate() const { return &tmpl; }
    bool haveOffhandWeapon() const { return false; }
    bool CanUseAttackType(WeaponAttackType) const { return true; }
    float GetWeaponDamageRange(WeaponAttackType, int k) const { return weapon[k]; }
    float GetTotalAttackPowerValue(WeaponAttackType) const { return attackPower; }
    float GetAPMultiplier(WeaponAttackType, bool) const { return attackTime / 1000.f; }
    float GetFlatModifierValue(UnitMods, int k) const { return flat[k]; }
    float GetPctModifierValue(UnitMods, int k) const { return pct[k]; }
    void CalculateMinMaxDamage(WeaponAttackType attType, bool normalized, bool addTotalPct, float& minDamage, float& maxDamage) const;
};
''' + native + r'''
int main() {
    Creature rune;
    for (float ownerRoll : { 4321.f, 4871.f, 5421.f }) {
        rune.flat[TOTAL_VALUE] = ownerRoll;   // 51906 EFFECT_0
        rune.pct[TOTAL_PCT] = 0.5f;           // 51906 EFFECT_2
        float lo = 0, hi = 0;
        rune.CalculateMinMaxDamage(BASE_ATTACK, true, true, lo, hi);
        assert(lo == hi);
        std::printf("%.4f\n", lo / ownerRoll);
    }
}
'''
    ratios = [float(x) for x in compile_and_run(tmp_path, "rune_weapon_damage", code).split()]
    assert len(ratios) == 3
    for ratio in ratios:
        # 0.5 of the owner's weapon strike plus the rune weapon's own 4 AP (1 damage).
        assert 0.5 <= ratio < 0.5002


def test_glyph_script_registration_and_single_damage_only_handler():
    source = GLYPHS.read_text()
    assert len(source.splitlines()) < 1000
    assert re.search(rf"SPELL_DK_GLYPH_OF_DEATH_STRIKE\s*=\s*{GLYPH_OF_DEATH_STRIKE}\b", source)
    assert source.count("RegisterSpellScript(spell_dk_glyph_of_death_strike);") == 1
    assert "CalcDamage.Register(&spell_dk_glyph_of_death_strike::CalculateDamage);" in source
    handler = extract(source, "void CalculateDamage(")
    assert "GetSpellModOwner()" in handler
    assert "GetAuraEffect(SPELL_DK_GLYPH_OF_DEATH_STRIKE, EFFECT_0)" in handler
    assert "GetAuraEffect(SPELL_DK_GLYPH_OF_DEATH_STRIKE, EFFECT_1)" in handler
    assert "GetPower(POWER_RUNIC_POWER)" in handler
    assert "AddPct(pctMod, bonus);" in handler
    # Runic power is not consumed and the healing stays in spell_dk_death_strike.
    for forbidden in ("ModifyPower", "SetPower", "CastSpell", "Heal", "heal"):
        assert forbidden not in handler
    loader = (SPELLS / "spell_script_loader.cpp").read_text()
    assert loader.count("void AddSC_deathknight_glyph_spell_scripts();") == 1
    assert loader.count("    AddSC_deathknight_glyph_spell_scripts();") == 1
    dk = (SPELLS / "spell_dk.cpp").read_text()
    assert "59336" not in dk
    assert "RegisterSpellScript(spell_dk_death_strike);" in dk


@pytest.fixture(scope="module")
def glyph_binary(tmp_path_factory):
    source = GLYPHS.read_text()
    constants = "\n".join(re.findall(r"^constexpr int32 \w+ = \d+;$", source, re.M))
    assert "RUNIC_POWER_PER_DISPLAYED_POINT = 10;" in constants
    assert "GLYPH_OF_DEATH_STRIKE_RUNIC_POWER_STEP = 5;" in constants
    helper = extract(source, "int32 GlyphOfDeathStrikeBonusPct(")
    code = r'''
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
using int32 = std::int32_t;
''' + constants + "\n" + helper + r'''
int main(int argc, char** argv) {
    // argv: internal runic power, % per step, % cap
    std::printf("%d\n", GlyphOfDeathStrikeBonusPct(std::atoi(argv[1]), std::atoi(argv[2]), std::atoi(argv[3])));
}
'''
    tmp = tmp_path_factory.mktemp("glyph")
    (tmp / "glyph.cpp").write_text(code)
    binary = tmp / "glyph"
    result = subprocess.run(["c++", "-std=c++17", str(tmp / "glyph.cpp"), "-o", str(binary)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return binary


@pytest.mark.parametrize(("runic_power", "bonus_pct"), [
    (0, 0), (25, 10), (50, 20), (100, 40), (125, 40),
    # whole 5-point steps and the non-positive guard
    (4, 0), (49, 18), (-10, 0),
])
def test_glyph_of_death_strike_bonus_table(glyph_binary, runic_power, bonus_pct):
    # Displayed runic power is stored in tenths; client values: 2% per step, 40% cap.
    out = subprocess.run([str(glyph_binary), str(runic_power * 10), "2", "40"],
                         capture_output=True, text=True, check=True).stdout
    assert int(out) == bonus_pct
