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


def test_mechanic_timer_helper_matches_eventmap_semantics(tmp_path: Path) -> None:
    """TimeUntilScheduledEvent against the production EventMap: remaining time,
    0 when due or held by a cast, uint32 max when unscheduled or cancelled;
    and why phase two must cancel the unphased vial events explicitly."""
    source = tmp_path / "timers.cpp"
    binary = tmp_path / "timers"
    source.write_text(
        r'''
#include "boss_maloriak_shared.h"
#include "EventMap.h"
#include <cstdio>
#include <limits>

uint32 urand(uint32 min, uint32) { return min; }

using namespace BlackwingDescent::Maloriak;

int main()
{
    int failures = 0;
    auto expect = [&failures](bool ok, char const* label) { if (!ok) { std::puts(label); ++failures; } };
    constexpr uint32 Unscheduled = std::numeric_limits<uint32>::max();
    enum { EVENT_A = 1, EVENT_B = 2, EVENT_VIAL = 3 };
    EventMap events;
    events.SetPhase(1);
    events.ScheduleEvent(EVENT_A, 15s, 0, 1);
    expect(TimeUntilScheduledEvent(events, EVENT_A) == 15000, "fresh event");
    expect(TimeUntilScheduledEvent(events, EVENT_B) == Unscheduled, "unscheduled");
    events.Update(10000);
    expect(TimeUntilScheduledEvent(events, EVENT_A) == 5000, "after 10 s");
    // A cast holds UpdateAI's ExecuteEvent: the event stays due, never wraps.
    events.Update(7000);
    expect(TimeUntilScheduledEvent(events, EVENT_A) == 0, "overdue while casting");
    expect(events.ExecuteEvent() == EVENT_A, "executes once released");
    expect(TimeUntilScheduledEvent(events, EVENT_A) == Unscheduled, "consumed");
    // Unphased vial steps still execute after SetPhase(2); only an explicit
    // CancelEvent (CancelVialVisitEvents) stops them.
    events.ScheduleEvent(EVENT_VIAL, 1s);
    events.SetPhase(2);
    events.Update(1000);
    expect(events.ExecuteEvent() == EVENT_VIAL, "unphased event survives phase two");
    events.ScheduleEvent(EVENT_VIAL, 1s);
    events.CancelEvent(EVENT_VIAL);
    expect(TimeUntilScheduledEvent(events, EVENT_VIAL) == Unscheduled, "cancelled");
    events.Update(2000);
    expect(events.ExecuteEvent() == 0, "cancelled event never runs");
    return failures;
}
''',
        encoding="utf-8",
    )
    command = [
        "g++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
        "-I", str(SCRIPTS), "-I", str(ROOT / "src/common"), "-I", str(ROOT / "src/common/Utilities"),
        str(source), str(ROOT / "src/common/Utilities/EventMap.cpp"), "-o", str(binary),
    ]
    subprocess.run(command, check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
    boss = text(BOSS)
    assert "return TimeUntilScheduledEvent(events, eventId);" in boss


def test_reset_comment_states_the_real_respawn_path() -> None:
    boss = text(BOSS)
    reset = function_body(boss, "void Reset() override")
    assert "Default Group without compatibility mode" in reset
    assert "The former VIAL_RED start" in boss


def test_consuming_flames_only_grows_from_other_magic_damage() -> None:
    """Round 4: CheckProc existed but was never registered, so every tick fed
    50% of itself back into the aura (r03 10N: 4500, 6322, 8598, 12467, 17454,
    25308, 36697, 41803, 58733 raw with no other damage taken)."""
    source = text(SPELLS)
    start = source.index("class spell_maloriak_consuming_flames")
    body = source[start:source.index("};", start)]
    assert "eventInfo.GetSpellInfo()->Id == GetId()" in body
    assert "DmgClass != SPELL_DAMAGE_CLASS_MAGIC" in body
    assert "DoCheckProc.Register(&spell_maloriak_consuming_flames::CheckProc);" in body
    assert "CalculatePct(eventInfo.GetDamageInfo()->GetDamage(), 50)" in body


def test_phase_two_cadence_follows_the_wcl_kills_on_10n_only() -> None:
    """Magma Jets, Acid Nova and Absolute Zero repeat at the 10N WCL cadence
    (MxFq7TRbvnjGY1hJ fight 34, VL3fW9wNm2PRJDYt fight 13) on 10N only; the
    evidence is 10N, so 25N/10H/25H keep the old 8.4 s first Absolute Zero and 6/20/7 s repeats."""
    source = text(BOSS)
    assert "bool IsTenNormal() const { return GetDifficulty() == RAID_DIFFICULTY_10MAN_NORMAL; }" in source
    mix = source[source.index("case EVENT_UNSTABLE_MIX:"):source.index("case EVENT_MAGMA_JETS:")]
    assert "ScheduleEvent(EVENT_MAGMA_JETS, 3s + 500ms, 0, PHASE_TWO)" in mix
    assert "ScheduleEvent(EVENT_ACID_NOVA, 8s + 400ms, 0, PHASE_TWO)" in mix
    assert ("ScheduleEvent(EVENT_ABSOLUTE_ZERO,\n                        IsTenNormal() ? Milliseconds(11s + 300ms)"
            " : Milliseconds(8s + 400ms), 0, PHASE_TWO)") in mix
    for event, ten, other in (("EVENT_MAGMA_JETS", "11s + 800ms", "6s"), ("EVENT_ACID_NOVA", "30s + 700ms", "20s"),
                              ("EVENT_ABSOLUTE_ZERO", "11s + 300ms", "7s")):
        start = source.index(f"case {event}:")
        body = source[start:source.index("break;", start)]
        assert f"events.Repeat(IsTenNormal() ? Milliseconds({ten}) : Milliseconds({other}));" in body, event


def test_pre_vial_arcane_storm_and_phase_two_remedy_on_10n_only() -> None:
    """10N WCL (eight kills, ledger pre_vial_casts / phase_two_remedy): an Arcane Storm before
    the first vial (median 14.3 s) and a phase-two Remedy about 19.4 s after Unstable Mix."""
    source = text(BOSS)
    engage = function_body(source, "void JustEngagedWith(Unit* who) override")
    assert engage.index("EVENT_FACE_TO_CAULDRON, 15s + 500ms") < engage.index(
        "if (IsTenNormal())\n            events.ScheduleEvent(EVENT_ARCANE_STORM, 14s + 300ms, 0, PHASE_ONE);")
    face = source[source.index("case EVENT_FACE_TO_CAULDRON:"):source.index("case EVENT_THROW_VIAL:")]
    assert "events.Reset();" in face  # drops the pre-vial storm's repeat
    enter = source[source.index("case EVENT_ENTER_PHASE_TWO:"):source.index("case EVENT_DRINK_ALL_BOTTLES:")]
    assert "events.CancelEvent(EVENT_REMEDY);" in enter
    mix = source[source.index("case EVENT_UNSTABLE_MIX:"):source.index("case EVENT_MAGMA_JETS:")]
    assert "if (IsTenNormal())\n                        events.ScheduleEvent(EVENT_REMEDY, 19s + 400ms, 0, PHASE_TWO);" in mix
    remedy = source[source.index("case EVENT_REMEDY:"):source.index("break;", source.index("case EVENT_REMEDY:"))]
    assert "events.Repeat(24s);" in remedy  # Repeat keeps the scheduled phase
    assert "return phaseTwo && !IsTenNormal() ? Unscheduled : untilEvent(EVENT_REMEDY);" in source

