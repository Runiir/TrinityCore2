"""Maloriak native script: vial order helper replay and static invariants."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent"
BOSS = SCRIPTS / "boss_maloriak.cpp"
SPELLS = SCRIPTS / "boss_maloriak_spells.cpp"
MINIONS = SCRIPTS / "boss_maloriak_minions.cpp"
REMEDY_RAMP_SQL = ROOT / "sql/custom/world/2026_09_30_21_maloriak_remedy_ramp.sql"
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
        "-I", str(SCRIPTS), "-I", str(ROOT / "src/common"), "-I", str(ROOT / "src/common/Utilities"),
        str(source), "-o", str(binary),
    ]
    subprocess.run(command, check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


def test_split_files_stay_below_the_module_size_limit() -> None:
    for path in (BOSS, SPELLS, MINIONS, SHARED):
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
    assert len(registered) == 13
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
    # Round 3: spell_maloriak_remedy is bound by the Remedy ramp migration (promoted to sql/custom/world 2026-09-30).
    staged = text(REMEDY_RAMP_SQL)
    assert registered == bound | set(re.findall(r"'(spell_maloriak_[a-z_]+)'\)", staged))
    # Round 3: the helper creature AIs moved to boss_maloriak_minions.cpp; the boss entry point
    # registers them, so the loader is unchanged.
    minions = text(MINIONS)
    assert set(re.findall(r"RegisterBlackwingDescentCreatureAI\((\w+)\);", boss)) == {"boss_maloriak"}
    assert "AddSC_boss_maloriak_minions();" in function_body(boss, "void AddSC_boss_maloriak()")
    assert "void AddSC_boss_maloriak_minions();" in text(SHARED)
    assert "AddSC_boss_maloriak_minions" not in loader
    assert set(re.findall(r"RegisterBlackwingDescentCreatureAI\((\w+)\);", minions)) == {
        "npc_maloriak_flash_freeze", "npc_maloriak_experiment",
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
    # Round 3: the 10N storm time is drawn from the observed begin times and the first vial
    # follows the pre-vial decision; the other modes keep the 15.5 s cauldron face.
    assert "_preVialOpening = IsTenNormal();" in engage
    assert "SelectRandomContainerElement(\n                PRE_VIAL_STORM_BEGIN_MS)" in engage
    assert "else\n            events.ScheduleEvent(EVENT_FACE_TO_CAULDRON, 15s + 500ms, 0, PHASE_ONE);" in engage
    face = source[source.index("case EVENT_FACE_TO_CAULDRON:"):source.index("case EVENT_THROW_VIAL:")]
    assert "events.Reset();" in face  # drops the pre-vial storm's repeat
    enter = source[source.index("case EVENT_ENTER_PHASE_TWO:"):source.index("case EVENT_DRINK_ALL_BOTTLES:")]
    assert "events.CancelEvent(EVENT_REMEDY);" in enter
    mix = source[source.index("case EVENT_UNSTABLE_MIX:"):source.index("case EVENT_MAGMA_JETS:")]
    assert "if (IsTenNormal())\n                        events.ScheduleEvent(EVENT_REMEDY, 19s + 400ms, 0, PHASE_TWO);" in mix
    remedy = source[source.index("case EVENT_REMEDY:"):source.index("break;", source.index("case EVENT_REMEDY:"))]
    assert "events.Repeat(24s);" in remedy  # Repeat keeps the scheduled phase
    assert "return phaseTwo && !IsTenNormal() ? Unscheduled : untilEvent(EVENT_REMEDY);" in source



def test_biting_chill_picks_a_melee_range_target_on_10n() -> None:
    """Round 3, 10N WCL (ledger biting_chill_targets_10N): every Biting Chill landed on one player in
    melee range (tanks, Retribution, Assassination). 77760 has a 10-yd range, so the old 60-yd pick
    failed the cast on a ranged player. 25N/10H/25H keep the old pick (no same-mode evidence)."""
    source = text(BOSS)
    start = source.index("case EVENT_BITING_CHILL:")
    body = source[start:source.index("break;", start)]
    assert "SelectTarget(SELECT_TARGET_RANDOM, 0, IsTenNormal() ? 10.0f : 60.0f, true)" in body
    assert "events.Repeat(11s);" in body


def test_debilitating_slime_strips_growth_catalyst_then_survivors_recast() -> None:
    """Round 3, WCL 10N VL3fW9wNm2PRJDYt fight 13: every Growth Catalyst (own ones included) was
    removed at the slime; a surviving Aberration's own aura returned 5.2 s later."""
    boss, spells, shared = text(BOSS), text(SPELLS), text(SHARED)
    green = boss[boss.index("case VIAL_GREEN:\n                        if (Creature* cauldron"):
                 boss.index("case VIAL_BLACK:", boss.index("case VIAL_GREEN:\n                        if (Creature* cauldron"))]
    assert green.index("SPELL_DEBILITATING_SLIME_DEBUFF") < green.index(
        "if (IsTenNormal())\n                            StripGrowthCatalystForSlime(me);")
    assert "constexpr uint32 GROWTH_CATALYST_SLIME_RECAST_MS = 5200;" in shared
    assert "void StripGrowthCatalystForSlime(Creature* source);" in shared
    body = function_body(spells, "void StripGrowthCatalystForSlime(Creature* source)")
    assert "{ uint32(NPC_ABERRATION), uint32(NPC_PRIME_SUBJECT) }" in body
    assert "GetSpellIdForDifficulty(SPELL_GROWTH_CATALYST, source)" in body
    assert body.index("RemoveAurasDueToSpell(catalyst)") < body.index("AddEventAtOffset")
    assert "experiment->IsAlive() && experiment->IsInCombat()" in body
    assert "Milliseconds(GROWTH_CATALYST_SLIME_RECAST_MS)" in body


# 10N WCL openings (storm begin s, first action after the storm): VL3fW9wNm2PRJDYt 13, MxFq7TRbvnjGY1hJ 34,
# the six round-2 kills, QfJR9AZw13G6kzXP 14 and the round-3 census (ledger pre_vial_opening_10N).
PRE_VIAL_OPENINGS = (
    (10.9, "release"), (11.117, "release"), (11.195, "release"), (12.548, "remedy"), (12.6, "release"),
    (12.614, "remedy"), (13.1, "remedy"), (13.206, "remedy"), (14.193, "release"), (14.3, "vial"),
    (14.357, "vial"), (14.4, "remedy"), (14.4, "vial"), (14.485, "vial"), (14.551, "remedy"),
    (14.565, "vial"), (14.773, "vial"), (14.8, "remedy"), (14.9, "vial"),
)


def test_pre_vial_opening_rule_replays_every_observed_10n_opening(tmp_path: Path) -> None:
    import collections

    source = tmp_path / "previal.cpp"
    binary = tmp_path / "previal"
    source.write_text(
        r'''
#include "boss_maloriak_shared.h"
#include <cstdio>
#include <cstdlib>

using namespace BlackwingDescent::Maloriak;

int main(int argc, char** argv)
{
    // argv: slot ms; prints the action for every roll 0..7 as V/L/R (vial, release, remedy).
    uint32 const slot = uint32(std::strtoul(argv[argc - 1], nullptr, 10));
    for (uint32 roll = 0; roll < 8; ++roll)
    {
        PreVialAction const action = ChoosePreVialAction(slot, roll);
        std::putchar(action == PreVialAction::Vial ? 'V' : action == PreVialAction::ReleaseAberrations ? 'L' : 'R');
    }
    std::putchar('\n');
    return 0;
}
''',
        encoding="utf-8",
    )
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(SCRIPTS),
                    "-I", str(ROOT / "src/common"), "-I", str(ROOT / "src/common/Utilities"),
                    str(source), "-o", str(binary)], check=True, cwd=ROOT)

    def outcomes(slot_ms: int) -> str:
        return subprocess.run([str(binary), str(slot_ms)], capture_output=True, text=True, check=True).stdout.strip()

    letter = {"vial": "V", "release": "L", "remedy": "R"}
    early, late = collections.Counter(), collections.Counter()
    for storm_s, action in PRE_VIAL_OPENINGS:
        slot_ms = round(storm_s * 1000) + 3200
        assert letter[action] in outcomes(slot_ms), (storm_s, action)  # every observed opening is reachable
        (early if slot_ms < 17000 else late)[action] += 1
    assert outcomes(16999) == "LLLLRRRR" and outcomes(17000) == "LRRVVVVV"
    assert early == {"release": 4, "remedy": 4} and late == {"vial": 7, "remedy": 3, "release": 1}
    shared = text(SHARED)
    begins = sorted(round(storm_s * 1000) for storm_s, _ in PRE_VIAL_OPENINGS)
    listed = shared[shared.index("PRE_VIAL_STORM_BEGIN_MS[] = {"):shared.index("};", shared.index("PRE_VIAL_STORM_BEGIN_MS"))]
    assert [int(value) for value in re.findall(r"\d{5}", listed)] == begins
    boss = text(BOSS)
    update = function_body(boss, "void UpdateAI(uint32 diff) override")
    storm = update[update.index("case EVENT_ARCANE_STORM:"):update.index("case EVENT_PRE_VIAL_ACTION:")]
    assert "if (_preVialOpening)" in storm and "PRE_VIAL_SLOT_AFTER_STORM_MS - PRE_VIAL_FACE_LEAD_MS" in storm
    decision = update[update.index("case EVENT_PRE_VIAL_ACTION:"):update.index("case EVENT_REMEDY:")]
    assert "_preVialOpening = false;" in decision
    assert "std::max(slotMs, PRE_VIAL_EARLIEST_CAST_MS)" in decision
    assert "ChoosePreVialAction(slotMs, urand(0, 7))" in decision
    assert "_preVialOpening = false;" in function_body(boss, "void Reset() override")


def test_berserk_at_seven_minutes_on_10n_only() -> None:
    """Round 3, WCL 10N cDQCyb4B71Wj9dV8 fight 15 (7:06 kill): Berserk 64238 at 7:02.6 of the fight
    (historical guide: 7 min normal). A plain countdown, because FACE_TO_CAULDRON resets the event map."""
    boss, shared = text(BOSS), text(SHARED)
    assert "SPELL_BERSERK                       = 64238," in shared
    assert "constexpr uint32 BERSERK_10N_MS = 7 * 60 * 1000;" in shared
    engage = function_body(boss, "void JustEngagedWith(Unit* who) override")
    assert "_berserkTimerMs = IsTenNormal() ? BERSERK_10N_MS : 0;" in engage
    assert "_berserkTimerMs = 0;" in function_body(boss, "void Reset() override")
    update = function_body(boss, "void UpdateAI(uint32 diff) override")
    assert update.index("if (!UpdateVictim())") < update.index("DoCastSelf(SPELL_BERSERK, true);") < update.index(
        "events.Update(diff);")


def test_remedy_heal_grows_by_its_base_value_every_tick() -> None:
    """Round 3, WCL 10N VL3fW9wNm2PRJDYt fight 13: Remedy ticks 22,500, 45,000 ... 250,000
    (25,000 x tick, x 0.9 under a healing debuff); the client row is a flat 25,000 per second."""
    spells = text(SPELLS)
    start = spells.index("class spell_maloriak_remedy : public AuraScript")
    body = spells[start:spells.index("};", start)]
    assert "aurEff->SetAmount(aurEff->GetBaseAmount() * int32(std::max<uint32>(aurEff->GetTickNumber(), 1)));" in body
    assert "OnEffectUpdatePeriodic.Register(&spell_maloriak_remedy::RampHeal, EFFECT_0, SPELL_AURA_PERIODIC_HEAL);" in body
    sql = "\n".join(line for line in text(REMEDY_RAMP_SQL).splitlines() if not line.startswith("--"))
    # 10N only: the variants 92965-92967 (25N/10H/25H) stay unbound.
    assert re.findall(r"\((\d+), 'spell_maloriak_remedy'\)", sql) == ["77912"]
    assert "DELETE FROM `spell_script_names` WHERE `spell_id` = 77912" in sql


def test_prime_subjects_cast_rend_on_10n_only() -> None:
    """Round 3, WCL 10N (VL3fW9wNm2PRJDYt 13, MxFq7TRbvnjGY1hJ 34): Prime Subjects cast Rend 78034 on their
    victim 14.1-16.5 s after landing, then 9.7-16.2 s apart. The native script had no Rend."""
    minions, shared = text(MINIONS), text(SHARED)
    assert "SPELL_REND                          = 78034," in shared
    ground = minions[minions.index("case POINT_GROUND:"):minions.index("break;", minions.index("case POINT_GROUND:"))]
    assert ("if (me->GetEntry() == NPC_PRIME_SUBJECT && GetDifficulty() == RAID_DIFFICULTY_10MAN_NORMAL)\n"
            "                    _events.ScheduleEvent(EVENT_REND, 14s + 100ms, 16s + 500ms);") in ground
    rend = minions[minions.index("case EVENT_REND:"):minions.index("break;", minions.index("case EVENT_REND:"))]
    assert "DoCastVictim(SPELL_REND);" in rend and "_events.Repeat(9s + 700ms, 16s + 200ms);" in rend


def test_flash_freeze_prefers_ranged_players_on_10n() -> None:
    """Round 3, 10N WCL (ledger flash_freeze_targets_10N): every Flash Freeze froze a ranged damage dealer or
    a healer. The victim and players fighting an Aberration stay excluded; players beyond 10 yd are preferred."""
    spells, shared = text(SPELLS), text(SHARED)
    assert "constexpr float FLASH_FREEZE_MIN_RANGE_10N = 10.0f;" in shared
    body = function_body(spells, "void FilterTargets(std::list<WorldObject*>& targets)")  # the first: Flash Freeze
    assert body.index("IsVictimOf(GetCaster())") < body.index("FLASH_FREEZE_MIN_RANGE_10N") < body.index("RandomResize")
    assert "caster->GetMap()->GetDifficulty() == RAID_DIFFICULTY_10MAN_NORMAL" in body
    assert "if (!ranged.empty())\n                targets.swap(ranged);" in body


def test_colored_vial_offsets_follow_the_10n_kills() -> None:
    """Round 3, 10N WCL (ledger vial_offsets_10N): after a Red or Blue imbue, Arcane Storm and Release come
    in a random order (first at 11.3 s; then Release 14.6 s or Storm 16.2 s); Remedy 17.8-21.0 s (Red),
    16.2-19.4 s (Blue). Other modes keep the old schedule. The 10N Green schedule is drawn over the
    observed ranges (test_green_phase_*)."""
    boss = text(BOSS)
    helper = function_body(boss, "bool ScheduleTenNormalColorVial(Milliseconds remedyMin, Milliseconds remedyMax)")
    assert helper.index("if (!IsTenNormal())\n            return false;") < helper.index("urand(0, 1)")
    assert "stormFirst ? 11s + 300ms : 16s + 200ms" in helper
    assert "stormFirst ? 14s + 600ms : 11s + 300ms" in helper
    assert "events.ScheduleEvent(EVENT_REMEDY, remedyMin, remedyMax, 0, PHASE_ONE);" in helper
    action = function_body(boss, "void DoAction(int32 action) override")
    red = action[action.index("case VIAL_RED:"):action.index("case VIAL_BLUE:")]
    blue = action[action.index("case VIAL_BLUE:"):action.index("case VIAL_GREEN:")]
    green = action[action.index("case VIAL_GREEN:"):action.index("case VIAL_BLACK:")]
    assert "ScheduleTenNormalColorVial(Milliseconds(17800), Milliseconds(21000))" in red
    assert "EVENT_ARCANE_STORM, 15s + 500ms" in red  # the other modes' schedule is unchanged
    assert "ScheduleTenNormalColorVial(Milliseconds(16200), Milliseconds(19400))" in blue
    assert "EVENT_ARCANE_STORM, 6s, 0, PHASE_ONE" in blue
    assert ("ScheduleGreenPhaseCasts(events, IsTenNormal(), EVENT_ARCANE_STORM, EVENT_REMEDY,\n"
            "                            EVENT_RELEASE_ABERRATIONS, PHASE_ONE);") in green
    # No inline Green storm/Remedy/Release schedule is left beside the helper call.
    assert "ScheduleEvent(EVENT_ARCANE_STORM" not in green and "Milliseconds(4000)" not in green
    assert "ScheduleEvent(EVENT_REMEDY" not in green and "ScheduleEvent(EVENT_RELEASE_ABERRATIONS" not in green


# Round-3 fix, packet maloriak_green_timer: the base revision holding the pre-fix Green schedule.
GREEN_BASE_REVISION = "c8e8bfe85b"
SCRIPT_RELATIVE = "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_maloriak.cpp"

TIMELINES = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/maloriak_wcl_boss_timelines_round2_v1.json"

# Green (Slime Imbued) offsets observed on 10N, seconds after the imbue (ledger green_phase_10N and
# target_era_corroboration_10N). A native event fires when its cast begins, so every value is compared as a
# begin: a Cast row of a spell with a cast time is converted first. Each row below names its WCL row type.
# Pre-cutoff: Arcane Storm BEGIN 3.6-4.4 (six phases); Remedy CAST 7.3-10.9 (instant).
# Post-cutoff (five kills after 2025-02-20, Cast rows only): Arcane Storm CAST 3.66 / 4.69 / 5.34 / 6.18 / 6.57;
# Remedy CAST 7.29 / 8.02 / 8.06 / 14.15. The Release begins, canceled ones included, are in
# test_maloriak_green_release_begin.py (ledger green_release_begins_10N).
GREEN_STORM_BEGIN_PRE_S = (3.6, 4.4)
GREEN_STORM_CAST_POST_S = (3.66, 4.69, 5.34, 6.18, 6.57)
GREEN_REMEDY_CAST_S = (7.3, 10.9, 7.29, 8.02, 8.06, 14.15)


def timeline_rows() -> list[tuple[str, str, str, float]]:
    """(report/fight, type, ability, t) of every pre-cutoff boss cast row (round-2 capture, Begin Casts included)."""
    document = json.loads(TIMELINES.read_text(encoding="utf-8"))
    return [(f"{fight['report']}-{fight['fight']}", event["type"], event["ability"], event["t"])
            for fight in document["fights"] for event in fight["events"]]


def arcane_storm_begin_to_cast_offsets_s() -> list[float]:
    """Seconds from each Arcane Storm Begin Cast to its Cast row, over every pre-cutoff pair."""
    begins: dict[str, float] = {}
    offsets = []
    for fight, kind, ability, moment in timeline_rows():
        if ability != "Arcane Storm":
            continue
        if kind == "Begin Cast":
            begins[fight] = moment
        elif fight in begins:
            offsets.append(round(moment - begins.pop(fight), 3))
    return offsets


def round2_green_storm_begins_s() -> list[float]:
    """Arcane Storm Begin Cast seconds after Slime Imbued in the pre-cutoff kills that reached Green."""
    rows = timeline_rows()
    begins = []
    for fight in {row[0] for row in rows}:
        events = [row for row in rows if row[0] == fight]
        for imbue in (row[3] for row in events if row[2] == "Slime Imbued"):
            begins += [round(row[3] - imbue, 3) for row in events
                       if row[1] == "Begin Cast" and row[2] == "Arcane Storm" and imbue < row[3] < imbue + 16]
    return sorted(begins)


def shared_constant(name: str) -> int:
    match = re.search(rf"constexpr uint32 {name} = (\d+);", text(SHARED))
    assert match, name
    return int(match.group(1))


def base_green_schedule() -> dict[str, str]:
    """The Green branch of the base revision: event name -> its fixed delay expression."""
    shown = subprocess.run(["git", "show", f"{GREEN_BASE_REVISION}:{SCRIPT_RELATIVE}"], cwd=ROOT,
                           capture_output=True, text=True)
    assert shown.returncode == 0, shown.stderr
    source = shown.stdout
    start = source.index("case VIAL_GREEN:\n                        if (Creature* cauldron")
    branch = source[start:source.index("case VIAL_BLACK:", start)]
    return dict(re.findall(r"events\.ScheduleEvent\((EVENT_\w+), ([^,]+), 0, PHASE_ONE\);", branch))


def test_green_ranges_cover_every_observed_green_offset() -> None:
    """The draw ranges are the combined pre- and post-cutoff observations (10N ledger) in the time each native
    event fires at (the cast begin): the storm 3.1-6.1 s and Remedy 7.3-14.2 s after Slime Imbued, the Remedy
    never before the storm; the Release begin range is pinned against every Release row (canceled begins included)
    in test_maloriak_green_release_begin.py."""
    storm_min, storm_max = shared_constant("GREEN_STORM_10N_MIN_MS"), shared_constant("GREEN_STORM_10N_MAX_MS")
    remedy_min, remedy_max = shared_constant("GREEN_REMEDY_10N_MIN_MS"), shared_constant("GREEN_REMEDY_10N_MAX_MS")
    assert (storm_min, storm_max, remedy_min, remedy_max) == (3100, 6100, 7300, 14200)
    release_min, release_max = shared_constant("GREEN_RELEASE_10N_MIN_MS"), shared_constant("GREEN_RELEASE_10N_MAX_MS")
    assert (release_min, release_max) == (6415, 10505)
    assert storm_max < release_min  # Release follows the storm on every draw

    # Arcane Storm: a 0.5 s cast, so the post-cutoff Cast rows become begins first.
    offsets = arcane_storm_begin_to_cast_offsets_s()
    assert len(offsets) == 31 and (min(offsets), max(offsets)) == (0.474, 0.531)
    round2_begins = round2_green_storm_begins_s()
    assert round2_begins == [3.626, 4.047, 4.421]
    assert GREEN_STORM_BEGIN_PRE_S[0] <= round2_begins[0] and round2_begins[-1] <= GREEN_STORM_BEGIN_PRE_S[1] + 0.05
    post_begins = [(cast - max(offsets), cast - min(offsets)) for cast in GREEN_STORM_CAST_POST_S]
    span = (min(GREEN_STORM_BEGIN_PRE_S[0], min(low for low, _ in post_begins)),
            max(GREEN_STORM_BEGIN_PRE_S[1], max(high for _, high in post_begins)))
    assert tuple(round(value, 3) for value in span) == (3.129, 6.096)
    # The constants are that begin span stated to 0.1 s (an observation may sit up to 50 ms outside) and not the
    # Cast-row span, which would be 0.47-0.53 s later.
    assert (storm_min, storm_max) == (round(span[0] * 10) * 100, round(span[1] * 10) * 100)
    assert all(storm_min - 50 <= round(low * 1000) and round(high * 1000) <= storm_max + 50 for low, high in post_begins)
    assert storm_max < round(max(GREEN_STORM_CAST_POST_S) * 1000) and storm_min < round(min(GREEN_STORM_CAST_POST_S) * 1000)

    # Remedy: instant, so its Cast rows are its fire times and need no shift.
    rows = timeline_rows()
    assert sum(1 for row in rows if row[2] == "Remedy" and row[1] == "Begin Cast") == 0
    assert sum(1 for row in rows if row[2] == "Remedy" and row[1] == "Cast") >= 20
    # The capture logs every Begin Cast: each Arcane Storm Cast has its own Begin Cast row (one more Begin is an
    # interrupted storm), so the missing Remedy rows mean an instant cast, not a gap in the capture.
    storm_kinds = [row[1] for row in rows if row[2] == "Arcane Storm"]
    assert storm_kinds.count("Cast") == len(offsets) <= storm_kinds.count("Begin Cast")
    remedy = [round(value * 1000) for value in GREEN_REMEDY_CAST_S]
    assert remedy_min - 50 <= min(remedy) and max(remedy) <= remedy_max + 50
    assert abs(min(remedy) - remedy_min) <= 50 and abs(max(remedy) - remedy_max) <= 50
    assert storm_max < remedy_min  # Remedy follows the storm on every draw

    # Release and Remedy overlap on purpose: only the storm is ordered before them.
    shared = text(SHARED)
    assert release_min < remedy_max and remedy_min < release_max
    assert "GREEN_REMEDY_10N_MAX_MS < GREEN_RELEASE" not in shared and "GREEN_RELEASE_10N_MAX_MS < GREEN_REMEDY" not in shared

    # The ledger's native item states the same ranges and their time base.
    ledger = json.loads((ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/"
                         "maloriak_ledger_v1.json").read_text(encoding="utf-8"))
    item = next(row for row in ledger["native_fidelity_items"] if row["key"] == "green_arcane_storm_offset_10N")
    assert "3.1-6.1 s (storm, begin time)" in item["native"] and "7.3-14.2 s (instant Remedy)" in item["native"]
    assert "6.415-10.505 s (Release begin" in item["native"] and "Release stays 9 s" not in item["native"]
    corroboration = next(row for row in ledger["values"] if row["key"] == "target_era_corroboration_10N")
    storm_row = next(row for row in corroboration["mechanics"] if row["mechanic"] == "green_arcane_storm_offset")
    assert "0.474-0.531 s" in storm_row["note"] and "3.13-6.10 s" in storm_row["note"] and "instant cast" in storm_row["note"]


def test_green_phase_10n_draws_the_ranges_and_other_modes_keep_the_fixed_values(tmp_path: Path) -> None:
    """ScheduleGreenPhaseCasts against the production EventMap with a recording urand: 10N draws the storm over
    3.1-6.1 s, Remedy over 7.3-14.2 s and the Release begin over 6.415-10.505 s; every other mode schedules the
    base revision's fixed 5 / 7.5 / 9 s and draws nothing from the RNG."""
    source = tmp_path / "green.cpp"
    binary = tmp_path / "green"
    source.write_text(
        r"""
#include "boss_maloriak_shared.h"
#include "EventMap.h"
#include <cstdio>
#include <utility>
#include <vector>

// One pick per draw, in call order: true takes the range maximum, false the minimum.
static std::vector<std::pair<uint32, uint32>> g_draws;
static bool g_picks[3] = { false, false, false };
uint32 urand(uint32 min, uint32 max)
{
    size_t const index = g_draws.size();
    g_draws.emplace_back(min, max);
    return index < 3 && g_picks[index] ? max : min;
}

using namespace BlackwingDescent::Maloriak;

enum { EVENT_STORM = 1, EVENT_REMEDY = 2, EVENT_RELEASE = 3, PHASE = 1 };

struct Times { uint32 storm, remedy, release; };

static void Pick(bool storm, bool remedy, bool release)
{
    g_picks[0] = storm;
    g_picks[1] = remedy;
    g_picks[2] = release;
}

static Times Schedule(bool tenNormal)
{
    g_draws.clear();
    EventMap events;
    events.SetPhase(PHASE);
    ScheduleGreenPhaseCasts(events, tenNormal, EVENT_STORM, EVENT_REMEDY, EVENT_RELEASE, PHASE);
    return { TimeUntilScheduledEvent(events, EVENT_STORM), TimeUntilScheduledEvent(events, EVENT_REMEDY),
             TimeUntilScheduledEvent(events, EVENT_RELEASE) };
}

int main()
{
    int failures = 0;
    auto expect = [&failures](bool ok, char const* label) { if (!ok) { std::puts(label); ++failures; } };
    auto is = [](Times t, uint32 storm, uint32 remedy, uint32 release)
    { return t.storm == storm && t.remedy == remedy && t.release == release; };

    Pick(false, false, false);
    Times low = Schedule(true);
    expect(is(low, 3100, 7300, 6415), "10N low draw");
    expect(g_draws.size() == 3 && g_draws[0] == std::make_pair(3100u, 6100u)
        && g_draws[1] == std::make_pair(7300u, 14200u) && g_draws[2] == std::make_pair(6415u, 10505u),
        "10N draws exactly the storm, Remedy and Release ranges, in that order");
    Pick(true, true, true);
    Times high = Schedule(true);
    expect(is(high, 6100, 14200, 10505), "10N high draw");
    expect(g_draws.size() == 3, "10N high draws three times");

    // Off 10N nothing is drawn, whatever the picks say.
    for (bool pickHigh : { false, true })
    {
        Pick(pickHigh, pickHigh, pickHigh);
        Times other = Schedule(false);
        expect(is(other, 5000, 7500, 9000), "other modes keep 5 / 7.5 / 9 s");
        expect(g_draws.empty(), "other modes draw nothing");
    }

    // Every low/high combination: the storm runs first, Release and Remedy both run and follow the drawn order
    // (either may come first), and the events carry the phase (a phase change drops them).
    int releaseFirst = 0, remedyFirst = 0;
    for (int mask = 0; mask < 8; ++mask)
    {
        Pick(mask & 1, mask & 2, mask & 4);
        g_draws.clear();
        EventMap events;
        events.SetPhase(PHASE);
        ScheduleGreenPhaseCasts(events, true, EVENT_STORM, EVENT_REMEDY, EVENT_RELEASE, PHASE);
        uint32 const remedyAt = TimeUntilScheduledEvent(events, EVENT_REMEDY);
        uint32 const releaseAt = TimeUntilScheduledEvent(events, EVENT_RELEASE);
        events.Update(30000);
        uint32 const first = events.ExecuteEvent();
        uint32 const second = events.ExecuteEvent();
        uint32 const third = events.ExecuteEvent();
        expect(first == EVENT_STORM, "the storm runs first");
        expect(events.ExecuteEvent() == 0, "exactly three Green events");
        expect((second == EVENT_REMEDY && third == EVENT_RELEASE) || (second == EVENT_RELEASE && third == EVENT_REMEDY),
            "Release and Remedy both run");
        if (remedyAt != releaseAt)
            expect(second == (remedyAt < releaseAt ? EVENT_REMEDY : EVENT_RELEASE), "Release and Remedy run in their drawn order");
        (releaseAt < remedyAt ? releaseFirst : remedyFirst)++;

        EventMap dropped;
        dropped.SetPhase(PHASE);
        ScheduleGreenPhaseCasts(dropped, true, EVENT_STORM, EVENT_REMEDY, EVENT_RELEASE, PHASE);
        dropped.SetPhase(2);
        dropped.Update(30000);
        expect(dropped.ExecuteEvent() == 0, "phase two drops the Green events");
    }
    expect(releaseFirst > 0 && remedyFirst > 0, "the ranges allow Release before Remedy and Remedy before Release");
    return failures;
}
""",
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

    # Off 10N the helper schedules the base revision's own values, event for event.
    base = base_green_schedule()
    assert base == {"EVENT_ARCANE_STORM": "5s", "EVENT_REMEDY": "7s + 500ms", "EVENT_RELEASE_ABERRATIONS": "9s"}
    shared = text(SHARED)
    helper = function_body(shared, "void ScheduleGreenPhaseCasts(EventMapT& events, bool tenNormal,")
    other_modes = helper[helper.index("else"):]
    scheduled = dict(re.findall(r"events\.ScheduleEvent\((\w+Event), ([^,]+), 0, phase\);", other_modes))
    assert scheduled == {"stormEvent": base["EVENT_ARCANE_STORM"], "remedyEvent": base["EVENT_REMEDY"],
                         "releaseEvent": base["EVENT_RELEASE_ABERRATIONS"]}
    # 10N is the only mode that draws: its branch is the only place a range is scheduled.
    ten_branch = helper[helper.index("if (tenNormal)"):helper.index("else")]
    for name in ("GREEN_STORM_10N_MIN_MS", "GREEN_REMEDY_10N_MAX_MS", "GREEN_RELEASE_10N_MIN_MS", "GREEN_RELEASE_10N_MAX_MS"):
        assert name in ten_branch, name
    assert "releaseEvent, 9s" not in ten_branch  # no fixed 9 s Release is left on 10N
    assert "GREEN_" not in other_modes
    call = function_body(text(BOSS), "void DoAction(int32 action) override")
    assert call.count("ScheduleGreenPhaseCasts(events, IsTenNormal(),") == 1
    assert "Milliseconds(4000)" not in text(BOSS)
