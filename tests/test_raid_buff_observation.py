"""Round 6: diagnose observes the raid buff auras the runtime applies.

The round 5 batch looked as if Blessing of Might never landed: no report or
snapshot listed 79101/79102 and paladin_blessing_ready was false on every bot.
The characters database saved at each clear shows 79102 on all ten bots of all
six shards. paladin_blessing_ready looked for Blessing of Kings 20217 and Mark
of the Wild 1126, dummy spells that no bot ever carries, so it could never be
true. These tests pin the observation to the auras the spells really apply.
"""
from __future__ import annotations

import re
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
DBC = ROOT / "data/dbc/enUS"
DIAGNOSIS = BOTS / "BotWorldPopulationMgrDiagnosis.cpp"
OBSERVATION = BOTS / "BotRaidBuffObservation.h"
INCLUDES = ["src/server/game", "src/server/shared", "src/common", "src/common/Utilities",
            "dep/recastnavigation/Detour/Include"]
# SPELL_EFFECT_APPLY_AURA, PERSISTENT_AREA_AURA, APPLY_AREA_AURA_PARTY/RAID/PET/FRIEND/ENEMY/OWNER.
AURA_EFFECTS = {6, 27, 35, 65, 119, 128, 129, 143}
# The raid buffs whose spell is a dummy that casts base points (single) or base + 1 (raid).
DUMMY_RAID_BUFFS = {1126: "mark_of_the_wild", 20217: "blessing_of_kings", 19740: "blessing_of_might",
                    21562: "power_word_fortitude", 1459: "arcane_brilliance"}


def _run(tmp_path: Path, name: str, program: str) -> str:
    source = tmp_path / f"{name}.cpp"
    binary = tmp_path / name
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    return subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout


def _effects() -> dict[int, list[tuple[int, int, int]]]:
    assert (DBC / "SpellEffect.dbc").is_file(), "extract the client DBCs"
    blob = (DBC / "SpellEffect.dbc").read_bytes()
    count, fields, size, _ = struct.unpack_from("<4I", blob, 4)
    records = blob[20:20 + count * size]
    effects: dict[int, list[tuple[int, int, int]]] = {}
    for index in range(count):
        values = struct.unpack_from(f"<{fields}I", records, index * size)
        base = struct.unpack_from("<i", records, index * size + 5 * 4)[0]
        # Effect 1, EffectAura 3, BasePoints 5, SpellID 24.
        effects.setdefault(values[24], []).append((values[1], values[3], base))
    return effects


def _applies_aura(effects: dict, spell: int) -> bool:
    return any(effect in AURA_EFFECTS and aura for effect, aura, _ in effects.get(spell, []))


def _header_ids(name: str) -> list[int]:
    text = OBSERVATION.read_text()
    body = text[text.index(name):]
    body = body[:body.index("};")]
    return [int(value) for value in re.findall(r"\b(\d{3,6})\b", body)]


def _tracked() -> dict[int, str]:
    text = OBSERVATION.read_text()
    body = text[text.index("RaidBuffAuras[] ="):]
    body = body[:body.index("};")]
    return {int(aura): name for aura, name in re.findall(r'\{ (\d+), "([a-z_]+)" \}', body)}


def test_every_observed_id_is_an_applied_aura_never_the_dummy_that_casts_it() -> None:
    effects = _effects()
    tracked = _tracked()
    blessings = _header_ids("BlessingAuras[]")
    auras = _header_ids("PaladinAuras[]")
    assert tracked and blessings == [79062, 79063, 79101, 79102]
    assert auras == [465, 7294, 19746, 19891, 32223]
    for spell in [*tracked, *blessings, *auras]:
        assert _applies_aura(effects, spell), spell
    # The round 5 predicate {20217, 1126}: dummies, never an aura on anyone.
    for dummy, name in DUMMY_RAID_BUFFS.items():
        assert not _applies_aura(effects, dummy), dummy
        single = next(base for effect, _, base in effects[dummy] if effect == 3)  # SPELL_EFFECT_DUMMY
        assert tracked[single] == name and tracked[single + 1] == name + "_raid", dummy


def test_diagnose_checks_applied_auras() -> None:
    effects = _effects()
    source = DIAGNOSIS.read_text()
    assert '#include "Bots/BotRaidBuffObservation.h"' in source
    assert "paladinReady({ 20217, 1126 })" not in source and "paladinReady({ 465 })" not in source
    assert ('"{\\"name\\":\\"paladin_blessing_ready\\",\\"value\\":" << (isPaladin && '
            'BotRaidBuffObservation::AnyOf(BotRaidBuffObservation::BlessingAuras, hasAura)') in source
    assert ('"{\\"name\\":\\"paladin_aura_ready\\",\\"value\\":" << (isPaladin && '
            'BotRaidBuffObservation::AnyOf(BotRaidBuffObservation::PaladinAuras, hasOwnAura)') in source
    assert '"{\\"name\\":\\"raid_buff_auras\\",\\"value\\":" << BotRaidBuffObservation::Json(hasAura)' in source
    assert "auto hasOwnAura = [bot](uint32 auraId) { return bot && bot->HasAura(auraId, bot->GetGUID()); };" in source
    # The remaining paladin predicates name applied auras too.
    for ids in re.findall(r"paladinReady\(\{ ([0-9, ]+) \}\)", source):
        for spell in (int(value) for value in ids.split(",")):
            assert _applies_aura(effects, spell), spell
    assert len(source.splitlines()) < 1000


def test_every_raid_buff_the_persistent_contract_casts_is_observed(tmp_path: Path) -> None:
    """The check that would have caught round 5: each applied aura of a raid-wide row is tracked."""
    out = _run(tmp_path, "rows", r'''
#include "Bots/BotRaidPersistentBuffs.h"
#include <cstdio>
namespace C = BotPersistentSelfBuffContract;
namespace R = BotRaidPersistentBuffs;
int main() {
    for (bool mark : { false, true })
        for (uint8 cls : { uint8(CLASS_PALADIN), uint8(CLASS_PRIEST), uint8(CLASS_DRUID), uint8(CLASS_MAGE) })
            for (C::SelfBuff const& row : R::Contract(C::Buffs, true, cls,
                     [mark] { return mark; }, [](uint32) { return true; }))
                std::printf("%u %u %u %u\n", unsigned(row.ClassId), row.SpellId, row.AuraId, row.AlternateAuraId);
}
''')
    effects = _effects()
    tracked = _tracked()
    rows = {tuple(int(value) for value in line.split()) for line in out.splitlines()}
    raid_rows = [row for row in rows if row[1] in DUMMY_RAID_BUFFS or row[1] in (465, 7294)]
    assert {row[1] for row in raid_rows} == set(DUMMY_RAID_BUFFS) | {465, 7294}
    for _, spell, aura, alternate in raid_rows:
        applied = [candidate for candidate in (aura, alternate) if candidate and _applies_aura(effects, candidate)]
        assert applied, spell
        assert all(candidate in tracked for candidate in applied), (spell, applied)


def test_observation_helpers(tmp_path: Path) -> None:
    out = _run(tmp_path, "observe", r'''
#include "Bots/BotRaidBuffObservation.h"
#include <cassert>
#include <cstdio>
#include <set>
int main() {
    namespace O = BotRaidBuffObservation;
    std::set<uint32> carried = { 79102, 79105, 79061, 7294 };
    auto has = [&carried](uint32 aura) { return carried.count(aura) > 0; };
    assert(O::Json(has) == "[79061,79102,79105,7294]");
    assert(O::AnyOf(O::BlessingAuras, has) && O::AnyOf(O::PaladinAuras, has));
    carried = { 20217, 1126, 21562, 19740 };  // the dummies: never observed
    assert(O::Json(has) == "[]" && !O::AnyOf(O::BlessingAuras, has) && !O::AnyOf(O::PaladinAuras, has));
    std::puts("ok");
}
''')
    assert out.strip() == "ok"
