"""Maloriak native script: vial order helper replay and static invariants."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent"
BOSS = SCRIPTS / "boss_maloriak.cpp"
SPELLS = SCRIPTS / "boss_maloriak_spells.cpp"
SHARED = SCRIPTS / "boss_maloriak_shared.h"
LOADER = ROOT / "src/server/scripts/EasternKingdoms/eastern_kingdoms_script_loader.cpp"
HISTORICAL_BINDINGS = (
    ROOT / "sql/old/custom/world/34_2020_02_21/custom_2019_08_20_00_world_updatepack.sql",
    ROOT / "sql/old/4.3.4/world/20051_2020_09_22/2020_07_06_00_world.sql",
)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : index]
    raise AssertionError(f"unterminated function: {signature}")


def test_vial_order_matches_the_researched_cycles(tmp_path: Path) -> None:
    source = tmp_path / "vials.cpp"
    binary = tmp_path / "vials"
    source.write_text(
        r'''
#include "boss_maloriak_shared.h"
#include <cstdio>
#include <string>

using namespace BlackwingDescent::Maloriak;

// Replays EVENT_FACE_TO_CAULDRON from the Reset state. The random branch is
// resolved with the given Red/Blue pick, exactly like urand in the script.
static std::string Cycle(bool heroic, uint8 perCycle, uint8 const* picks, int count)
{
    uint8 current = VIAL_GREEN;
    uint8 used = 0;
    std::string order;
    int pick = 0;
    for (int visit = 0; visit < count; ++visit)
    {
        uint8 const next = SelectNextVial(current, used, perCycle, heroic);
        current = next == VIAL_RANDOM_RED_OR_BLUE ? picks[pick++] : next;
        used = AdvanceUsedVials(used, perCycle);
        order += "RBGK"[current];
    }
    return order;
}

int main()
{
    int failures = 0;
    uint8 const redFirst[] = { VIAL_RED, VIAL_BLUE, VIAL_RED };
    uint8 const blueFirst[] = { VIAL_BLUE, VIAL_RED, VIAL_BLUE };
    // Normal: random Red/Blue, the other color, Green, repeat.
    if (Cycle(false, 2, redFirst, 7) != "RBGBRGR") { std::puts("normal red first"); ++failures; }
    if (Cycle(false, 2, blueFirst, 6) != "BRGRBG") { std::puts("normal blue first"); ++failures; }
    // Heroic: Black, random Red/Blue, the other color, Green, repeat.
    if (Cycle(true, 3, redFirst, 8) != "KRBGKBRG") { std::puts("heroic"); ++failures; }
    // The first normal vial is the random branch (was always Blue before
    // the reset fix, because the counters started at VIAL_RED).
    if (SelectNextVial(VIAL_GREEN, 0, 2, false) != VIAL_RANDOM_RED_OR_BLUE) { std::puts("first random"); ++failures; }
    if (SelectNextVial(VIAL_RED, 0, 2, false) != VIAL_BLUE) { std::puts("legacy start"); ++failures; }
    return failures;
}
''',
        encoding="utf-8",
    )
    command = [
        "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
        "-I", str(SCRIPTS), "-I", str(ROOT / "src/common"),
        str(source), "-o", str(binary),
    ]
    subprocess.run(command, check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


def test_split_files_stay_below_the_module_size_limit() -> None:
    for path in (BOSS, SPELLS, SHARED):
        assert len(text(path).splitlines()) < 1000, path.name


def test_reset_starts_a_fresh_cycle_and_release_reserve() -> None:
    reset = function_body(text(BOSS), "void Reset() override")
    for statement in (
        "_currentVial = VIAL_GREEN;",
        "_usedVialsCount = 0;",
        "_releasedAberrationsCount = 0;",
        "_vialSequenceActive = false;",
        "me->MakeInterruptable(false);",
    ):
        assert statement in reset


def test_phase_two_cancels_the_unphased_vial_pipeline() -> None:
    boss = text(BOSS)
    cancel = function_body(boss, "void CancelVialVisitEvents()")
    for event in ("EVENT_MOVE_TO_CAULDRON", "EVENT_DRINK_BOTTLE", "EVENT_IMBUED_BUFF",
                  "EVENT_EXPLODE_CAULDRON", "EVENT_ATTACK_PLAYERS"):
        assert event in cancel
    assert "events.CancelEvent(vialEvent)" in cancel
    damage = function_body(boss, "void DamageTaken(Unit* /*attacker*/, uint32& damage) override")
    assert damage.index("events.SetPhase(PHASE_TWO)") < damage.index("CancelVialVisitEvents()")
    update = function_body(boss, "void UpdateAI(uint32 diff) override")
    enter = update[update.index("case EVENT_ENTER_PHASE_TWO:"):update.index("case EVENT_DRINK_ALL_BOTTLES:")]
    assert "CancelVialVisitEvents();" in enter
    assert "GetCurrentMovementGeneratorType() == POINT_MOTION_TYPE" in enter
    schedule = function_body(boss, "void DoAction(int32 action) override")
    assert schedule.index("if (events.IsInPhase(PHASE_TWO))") < schedule.index("EVENT_ATTACK_PLAYERS")
    inform = function_body(boss, "void MovementInform(uint32 motionType, uint32 pointId) override")
    assert "if (!events.IsInPhase(PHASE_TWO))" in inform


def test_mechanic_timers_are_read_only_observations() -> None:
    body = function_body(text(BOSS), "uint32 GetTimeUntilEncounterMechanic(uint32 spellId) const override")
    for spell in ("SPELL_ARCANE_STORM", "SPELL_RELEASE_ABERRATIONS", "SPELL_REMEDY",
                  "SPELL_SCORCHING_BLAST", "SPELL_FLASH_FREEZE_TARGETING", "SPELL_MAGMA_JETS_SCRIPT_EFFECT",
                  "SPELL_ACID_NOVA", "SPELL_ABSOLUTE_ZERO", "SPELL_THROW_GREEN_BOTTLE"):
        assert f"case {spell}:" in body
    for mutation in ("ScheduleEvent", "CancelEvent", "SetReactState", "CastSpell", "DoCast", "_currentVial =",
                     "_usedVialsCount ="):
        assert mutation not in body
    face = function_body(text(BOSS), "void UpdateAI(uint32 diff) override")
    assert "SelectNextVial(_currentVial, _usedVialsCount, _vialsPerCycle, IsHeroic())" in face
    assert "AdvanceUsedVials(_usedVialsCount, _vialsPerCycle)" in face


def test_spell_scripts_keep_their_names_and_registration_path() -> None:
    boss, spells = text(BOSS), text(SPELLS)
    registered = set(re.findall(r"RegisterSpellScript\((\w+)\);", spells))
    assert len(registered) == 12
    assert not re.search(r"RegisterSpellScript\(", boss)
    assert "AddSC_boss_maloriak_spells();" in function_body(boss, "void AddSC_boss_maloriak()")
    assert "void AddSC_boss_maloriak_spells();" in text(SHARED)
    # The loader still owns a single Maloriak entry point.
    loader = text(LOADER)
    assert loader.count("void AddSC_boss_maloriak();") == 1
    assert loader.count("    AddSC_boss_maloriak();") == 1
    assert "AddSC_boss_maloriak_spells" not in loader
    bound = {
        name
        for path in HISTORICAL_BINDINGS
        for name in re.findall(r"'(spell_maloriak_[a-z_]+)'", text(path))
    }
    assert registered == bound
    creatures = set(re.findall(r"RegisterBlackwingDescentCreatureAI\((\w+)\);", boss))
    assert creatures == {
        "boss_maloriak", "npc_maloriak_flash_freeze", "npc_maloriak_experiment",
        "npc_maloriak_magma_jet", "npc_maloriak_lord_victor_nefarius", "npc_maloriak_vile_swill",
    }
