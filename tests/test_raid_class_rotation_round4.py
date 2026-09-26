"""Round 4 class items: canonical-only Survival fix and the raid air totem.

Scope rules (user, 2026-09-25): accepted Stonecore, Phase 8 calibration and
the legacy accepted Magmaw 10N scenario stay exactly reproducible. The legacy
Magmaw hunter 30009 is an Orc Survival hunter, the same spec the canonical
roster now uses, so a Survival fix is scoped to canonical-composition cohorts
(BotCanonicalRaidScope.h) rather than to every raid. The air-totem change only
affects a non-Elemental shaman, and the legacy Magmaw shaman is Elemental, so
raid scope is enough there.
"""
from __future__ import annotations

import json
import struct
import subprocess
from pathlib import Path

import pytest

from tests.combat_resolver_source import combat_resolver_source

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
DBC = ROOT / "data/dbc/enUS"
INCLUDES = ["-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common")]
SCENARIOS = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
LEGACY_SHARDS = ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"


def _run(tmp_path: Path, name: str, program: str) -> str:
    source = tmp_path / f"{name}.cpp"
    binary = tmp_path / name
    source.write_text(program)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES,
                    str(source), "-o", str(binary)], check=True)
    return subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout


def _scenario_rows() -> list[dict]:
    config = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    return list(config.get("scenarios") or []) + list(config.get("diagnostic_scenarios") or [])


def test_canonical_scope_is_exactly_the_composition_cohorts(tmp_path: Path) -> None:
    rows = _scenario_rows()
    cases = [(row["id"], "composition_id" in row) for row in rows]
    # Stonecore, calibration-style and malformed ids are never canonical.
    cases += [("stonecore_5n", False), ("", False), ("blackwing_descent_10n_magmaw_c_diagnostic", False),
              ("blackwing_descent_10n_magmaw_cx_diagnostic", False), ("_diagnostic", False),
              ("blackwing_descent_10n_magmaw_c12_diagnostic", True), ("bastion_of_twilight_25h_full_c3", True)]
    assert any(expected for _, expected in cases) and any(not expected for _, expected in cases)
    assert ("blackwing_descent_10n_magmaw_diagnostic", False) in cases
    checks = "\n".join(
        f'    assert(IsCanonicalCompositionScenario("{scenario}") == {"true" if expected else "false"});'
        for scenario, expected in cases)
    _run(tmp_path, "scope", r'''
#include "Bots/BotCanonicalRaidScope.h"
#include <cassert>
int main() {
    using BotCanonicalRaidScope::IsCanonicalCompositionScenario;
''' + checks + "\n}\n")


def test_legacy_magmaw_hunter_and_shaman_are_the_specs_the_scopes_protect() -> None:
    roster = {}

    def walk(node):
        if isinstance(node, dict):
            guid = node.get("character_guid")
            if isinstance(guid, int) and 30001 <= guid <= 30010:
                roster[guid] = (node.get("class_spec"), node.get("race"))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(LEGACY_SHARDS.read_text(encoding="utf-8")))
    # Survival hunter, Orc (Blood Fury 20572): the canonical-only scope.
    assert roster[30009] == ("survival_hunter", 2)
    # Elemental shaman: the air-totem change never applies to it.
    assert roster[30010][0] == "elemental_shaman"


def test_survival_blood_fury_ceiling_lifts_only_through_apply_canonical(tmp_path: Path) -> None:
    out = _run(tmp_path, "survival", r'''
#include "Bots/BotRaidRotationOverrides.h"
#include <cassert>
#include <string>
BotActionProfileSpell row(uint32 id, uint8 maxEnemies, char const* tags) {
    BotActionProfileSpell s; s.SpellId = id; s.MaxEnemies = maxEnemies; s.MechanicTags = tags; return s;
}
BotClassSpecActionProfile survival(char const* role = "dps", char const* spec = "survival", uint8 cls = 3) {
    BotClassSpecActionProfile p; p.ClassId = cls; p.SpecTag = spec; p.Role = role;
    p.Spells = { row(20572, 1, "blood_fury,self,orc_fixture,autocast_other_cooldowns"),
                 row(3045, 0, "rapid_fire,opener,cooldown,heroism_burst"),
                 row(13813, 1, "explosive_trap,single_target,scored_opener,lock_and_load"),
                 row(53301, 0, "explosive_shot") };
    return p;
}
int main() {
    auto p = survival();
    // The round 3 raid overrides never touch Survival.
    assert(BotRaidRotationOverrides::Apply(p) == 0);
    assert(BotRaidRotationOverrides::ApplyCanonical(p) == 1);
    assert(p.Spells[0].MaxEnemies == 0);
    assert(p.Spells[0].MechanicTags == "blood_fury,self,orc_fixture,autocast_other_cooldowns,canonical_raid_rotation_20260926");
    for (size_t i = 1; i < p.Spells.size(); ++i)
        assert(p.Spells[i].MechanicTags.find("canonical_raid_rotation") == std::string::npos);
    assert(p.Spells[2].MaxEnemies == 1); // the scored-opener trap is left alone
    assert(BotRaidRotationOverrides::ApplyCanonical(p) == 0); // idempotent
    // A changed DB row wins; other specs, roles and classes are untouched.
    auto drifted = survival(); drifted.Spells[0].MaxEnemies = 2;
    assert(BotRaidRotationOverrides::ApplyCanonical(drifted) == 0 && drifted.Spells[0].MaxEnemies == 2);
    for (auto other : { survival("tank"), survival("dps", "marksmanship"), survival("dps", "survival", 4) })
        assert(BotRaidRotationOverrides::ApplyCanonical(other) == 0);
    std::puts("ok");
}
''')
    assert out.strip() == "ok"


def test_resolver_applies_the_survival_fix_only_in_canonical_raid_scope() -> None:
    resolver = combat_resolver_source()
    assert '#include "Bots/BotCanonicalRaidScope.h"' in resolver
    wiring = ("    if (raidRotationScope)\n"
              "        BotRaidRotationOverrides::Apply(profile);\n")
    canonical = ("    if (raidRotationScope && BotCanonicalRaidScope::IsCanonicalCompositionScenario(\n"
                 "            Cohort().Config.ValidationRouteScenarioId))\n"
                 "        BotRaidRotationOverrides::ApplyCanonical(profile);\n")
    assert wiring in resolver and canonical in resolver
    assert resolver.index(wiring) < resolver.index(canonical) < resolver.index("BuildCandidates(bot, target, profile")
    callers = [path for path in (ROOT / "src").rglob("*.cpp")
               if "BotRaidRotationOverrides::ApplyCanonical(" in path.read_text(errors="replace")]
    assert callers == [BOTS / "BotWorldPopulationMgrCombatResolver.cpp"]


def test_raid_air_totem_policy_truth_table(tmp_path: Path) -> None:
    _run(tmp_path, "totem", r'''
#include "Bots/BotRaidShamanTotems.h"
#include <cassert>
int main() {
    using BotRaidShamanTotems::PreferWrathOfAir;
    int probes = 0;
    auto provider = [&probes]() { ++probes; return true; };
    auto none = [&probes]() { ++probes; return false; };
    assert(PreferWrathOfAir(true, false, true, provider));
    assert(!PreferWrathOfAir(true, false, true, none));
    // Outside a raid, for Elemental (already Wrath of Air), or without the
    // spell (the totem loop refuses unknown totems), nothing changes and the
    // group is never walked.
    assert(!PreferWrathOfAir(false, false, true, provider));
    assert(!PreferWrathOfAir(true, true, true, provider));
    assert(!PreferWrathOfAir(true, false, false, provider));
    assert(probes == 2);
    static_assert(BotRaidShamanTotems::WrathOfAirTotem == 3738);
    static_assert(BotRaidShamanTotems::WindfuryTotem == 8512);
}
''')


def test_totem_wiring_reduces_to_the_old_choice_outside_the_raid_preference() -> None:
    source = (BOTS / "BotWorldPopulationMgrCombatExecution.cpp").read_text(encoding="utf-8")
    assert '#include "Bots/BotRaidShamanTotems.h"' in source
    assert ("    bool const raidWrathOfAir = BotRaidShamanTotems::PreferWrathOfAir(\n"
            "        Cohort().Raid.RaidInstance && bot->GetMap() && bot->GetMap()->IsRaid(),\n"
            "        isElemental, bot->HasSpell(BotRaidShamanTotems::WrathOfAirTotem),\n"
            "        otherMeleeHasteProvider);\n") in source
    # With raidWrathOfAir false the air choice and the ready check are the
    # pre-round-4 expressions (isElemental ? 3738 : 8512 and !isElemental || ...).
    assert "    uint32 const desiredAirTotemSpell = isElemental || raidWrathOfAir ? 3738 : 8512;\n" in source
    assert ("            && ((!isElemental && !(raidWrathOfAir && slot == SUMMON_SLOT_TOTEM_AIR))\n"
            "                || slot == SUMMON_SLOT_TOTEM_FIRE\n"
            "                || totem->GetUInt32Value(UNIT_CREATED_BY_SPELL) == spellId);") in source
    probe = source[source.index("auto otherMeleeHasteProvider"):source.index("bool const raidWrathOfAir")]
    assert "member != bot" in probe and "member->IsAlive()" in probe and "member->IsInMap(bot)" in probe
    # The provider's own passive is the fact: a raid area aura that the stack
    # rules keep off a Windfury-buffed shaman would otherwise hide it.
    assert "member->HasAura(provider, member->GetGUID())" in probe
    assert len(source.splitlines()) < 1000


def test_melee_haste_providers_are_raid_area_auras_matching_windfury() -> None:
    if not (DBC / "SpellEffect.dbc").is_file():
        pytest.skip("client DBCs not hydrated")
    blob = (DBC / "SpellEffect.dbc").read_bytes()
    count, fields, size, _strings = struct.unpack_from("<4I", blob, 4)
    records = blob[20:20 + count * size]
    effects = {}
    for index in range(count):
        values = struct.unpack_from(f"<{fields}I", records, index * size)
        base = struct.unpack_from("<i", records, index * size + 5 * 4)[0]
        # SpellEffectEntry: Effect 1, EffectAura 3, EffectBasePoints 5, SpellID 24.
        if values[24] in (53290, 55610, 8515):
            effects.setdefault(values[24], set()).add((values[1], values[3], base))
    haste = {(65, 319, 10), (65, 320, 10)}  # APPLY_AREA_AURA_RAID, melee/ranged haste 10%
    for spell in (53290, 55610, 8515):
        assert haste <= effects[spell], (spell, effects.get(spell))
