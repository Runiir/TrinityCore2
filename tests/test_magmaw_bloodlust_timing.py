from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
MAGMAW = BOTS / "Content/Raids/BlackwingDescent/Encounters/Magmaw"
TIMING = MAGMAW / "BotMagmawBloodlustTiming.h"
MODULE = BOTS / "BotWorldPopulationMgrMagmawBloodlust.cpp"
BLACKBOARD = BOTS / "BotWorldPopulationMgrEncounterBlackboard.cpp"
SCRIPTS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent"
WCL = (
    ROOT
    / "experiments/configs/cata_raid_encounters/blackwing_descent"
    / "magmaw_wcl_cast_timelines_v1.json"
)
LUST_ABILITIES = {"Bloodlust", "Heroism", "Time Warp", "Ancient Hysteria"}


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def constant(name: str) -> int:
    match = re.search(rf"constexpr uint32 {name} = (\d+);", text(TIMING))
    assert match, name
    return int(match.group(1))


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


def test_lead_is_the_matched_wcl_lust_before_the_native_first_mangle() -> None:
    timeline = json.loads(text(WCL))
    lusts = [
        (cast["ability"], cast["t"])
        for actor in timeline["actors"]
        for cast in actor["casts"]
        if cast["ability"] in LUST_ABILITIES
    ]
    # The matched reference spends exactly one raid lust.
    assert lusts == [("Time Warp", 78.169)]
    assert timeline["reference_id"] == "Y8ajQ7dbmKMG1RZy-fight22"
    assert timeline["mode"] == "10N"
    assert constant("WclReferenceLustAfterPullMs") == round(lusts[0][1] * 1000)
    evidence = text(TIMING)
    assert "Y8ajQ7dbmKMG1RZy_fight22_time_warp_78169ms" in evidence

    # The native clock the lead is anchored to: first Mangle 90 s after pull,
    # published as the Massive Crash mechanic timer.
    boss = text(SCRIPTS / "boss_magmaw.cpp")
    engage = function_body(boss, "void JustEngagedWith(Unit* who)")
    assert "events.ScheduleEvent(EVENT_MANGLE, 1min + 30s, 0, PHASE_COMBAT);" in engage
    assert constant("NativeFirstMangleAfterPullMs") == 90000
    timer = function_body(boss, "uint32 GetTimeUntilEncounterMechanic(")
    assert "spellId != SPELL_MASSIVE_CRASH" in timer
    assert "return events.GetTimeUntilEvent(EVENT_MANGLE);" in timer
    assert "SPELL_MASSIVE_CRASH                         = 88253," in text(
        SCRIPTS / "boss_magmaw_shared.h"
    )
    assert constant("MassiveCrashSpell") == 88253
    appended = function_body(text(BLACKBOARD), "void AppendNativeMechanicTimers(")
    assert 'route.NodeId != "bwd.magmaw.encounter"' in appended
    assert "remainingMs == 0, BotEncounter::FactSource::NativeInstanceState" in appended


def test_pre_mangle_window_is_exact_single_boss_and_never_trash(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_bloodlust_timing.cpp"
    binary = tmp_path / "magmaw_bloodlust_timing"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlustTiming.h"

#include <cassert>
#include <cstring>
#include <string>

using namespace BotEncounter;
using namespace BotEncounter::MagmawBloodlust;

static ObjectGuid const BossGuid(HighGuid::Unit, BossEntry, uint32(41));
static ObjectGuid const HeadGuid(HighGuid::Unit, ExposedHeadEntry, uint32(76));

static ActorSnapshot Boss(uint32 remainingMs, bool sequenceActive = false)
{
    ActorSnapshot boss;
    boss.Guid = BossGuid;
    boss.Entry = BossEntry;
    boss.Kind = ActorKind::Hostile;
    boss.Alive = true;
    boss.Attackable = true;
    boss.Selectable = true;
    boss.InCombat = true;
    boss.MechanicTimers.push_back({ MassiveCrashSpell, remainingMs,
        sequenceActive, FactSource::NativeInstanceState });
    return boss;
}

static Blackboard Encounter(ActorSnapshot const& boss)
{
    Blackboard board;
    board.Route.NodeId = std::string(EncounterNode);
    board.NativeBossState = "in_progress";
    board.Hostiles = { boss };
    return board;
}

static ActorSnapshot ExposedHead()
{
    ActorSnapshot head;
    head.Guid = HeadGuid;
    head.Entry = ExposedHeadEntry;
    head.Kind = ActorKind::Summon;
    head.Alive = true;
    head.Attackable = true;
    head.Selectable = true;
    head.InCombat = true;
    return head;
}

int main()
{
    static_assert(PreMangleLustLeadMs == 11831, "WCL lead");

    // Too early: the full lead is still ahead of the native Mangle.
    assert(!ObservePreMangleLustWindow(
        Encounter(Boss(NativeFirstMangleAfterPullMs))));
    assert(!ObservePreMangleLustWindow(
        Encounter(Boss(PreMangleLustLeadMs + 1))));

    // At the lead and through the Mangle -> Massive Crash sequence.
    auto const lead = ObservePreMangleLustWindow(
        Encounter(Boss(PreMangleLustLeadMs)));
    assert(lead && lead->Trigger == LustTrigger::PreMangleLead);
    assert(lead->BossGuid == BossGuid && lead->TargetGuid == BossGuid);
    assert(ObservePreMangleLustWindow(Encounter(Boss(0, true))));

    // On a native pull clock the first eligible sample is the WCL moment.
    uint32 firstEligibleMs = 0;
    for (uint32 elapsedMs = 0; elapsedMs <= NativeFirstMangleAfterPullMs;
         elapsedMs += 1)
        if (ObservePreMangleLustWindow(Encounter(
                Boss(NativeFirstMangleAfterPullMs - elapsedMs))))
        {
            firstEligibleMs = elapsedMs;
            break;
        }
    assert(firstEligibleMs == WclReferenceLustAfterPullMs);

    // Never on trash, before pull, after a reset/evade, from a non-native
    // timer, for a dead or different creature, or for another mechanic.
    {
        Blackboard trash = Encounter(Boss(0, true));
        trash.Route.NodeId = "bwd.magmaw.drudges";
        assert(!ObservePreMangleLustWindow(trash));
    }
    {
        Blackboard idle = Encounter(Boss(0, true));
        idle.NativeBossState = "not_in_progress";
        assert(!ObservePreMangleLustWindow(idle));
    }
    {
        ActorSnapshot boss = Boss(0, true);
        boss.MechanicTimers.clear();
        assert(!ObservePreMangleLustWindow(Encounter(boss)));
    }
    {
        ActorSnapshot boss = Boss(0, true);
        boss.InCombat = false;
        assert(!ObservePreMangleLustWindow(Encounter(boss)));
    }
    {
        ActorSnapshot boss = Boss(0, true);
        boss.Alive = false;
        assert(!ObservePreMangleLustWindow(Encounter(boss)));
    }
    {
        ActorSnapshot boss = Boss(0, true);
        boss.MechanicTimers.front().Source = FactSource::VisibleCast;
        assert(!ObservePreMangleLustWindow(Encounter(boss)));
    }
    {
        ActorSnapshot drudge = Boss(0, true);
        drudge.Entry = 42362;
        assert(!ObservePreMangleLustWindow(Encounter(drudge)));
    }
    {
        ActorSnapshot boss = Boss(0, true);
        boss.MechanicTimers.front().SpellId = 89773;
        assert(!ObservePreMangleLustWindow(Encounter(boss)));
    }

    // The latched first exposed head keeps its trigger; without it the
    // WCL-timed lead is the only other window.
    Blackboard withHead = Encounter(Boss(NativeFirstMangleAfterPullMs));
    withHead.Summons = { ExposedHead() };
    std::optional<HeadWindow> const head = ObserveFirstHeadWindow(withHead);
    assert(head && head->HeadGuid == HeadGuid);
    auto const headChoice = SelectLustWindow(withHead, head);
    assert(headChoice && headChoice->Trigger == LustTrigger::FirstExposedHead);
    assert(headChoice->TargetGuid == HeadGuid);
    assert(headChoice->BossGuid == BossGuid);
    assert(!SelectLustWindow(withHead, std::nullopt));
    auto const leadChoice = SelectLustWindow(Encounter(Boss(1000)), std::nullopt);
    assert(leadChoice && leadChoice->Trigger == LustTrigger::PreMangleLead);

    assert(std::strcmp(LustTriggerName(LustTrigger::PreMangleLead),
        "pre_mangle_lead") == 0);
    assert(std::strcmp(LustTriggerName(LustTrigger::FirstExposedHead),
        "first_exposed_head") == 0);
    return 0;
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            "-I",
            str(ROOT / "src/server/shared"),
            "-I",
            str(ROOT / "src/common"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_candidate_uses_one_latched_native_cast_for_either_window() -> None:
    module = text(MODULE)
    body = function_body(module, "SubmitMagmawBloodlustCandidate(")
    assert (
        '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/'
        'BotMagmawBloodlustTiming.h"'
    ) in module

    # Exact boss node, admitted scenario and 10-slot roster gates are kept.
    assert "cohort->Config.ValidationRouteNodeId != EncounterNode" in body
    assert 'cohort->Config.ValidationRouteKind != "boss"' in body
    assert "raid->ExpectedSize != 10" in body

    # One latch per attempt/wipe/route: a submitted cast only observes auras.
    submitted = body.index("if (raid->MagmawBloodlustSubmitted)\n    {")
    selection = body.index("SelectLustWindow(board, headWindow)")
    assert submitted < selection
    assert "headWindow.reset();" in body
    assert (
        "if (lustWindow->Trigger == LustTrigger::FirstExposedHead)\n"
        "        raid->MagmawBloodlustHeadGuid = lustWindow->TargetGuid;"
    ) in body

    attempt = body[body.index("bloodlust.Attempt =") :]
    assert "targetGuid, trigger, ownerGuid = *owner" in attempt
    assert "target->GetEntry() != ExposedHeadEntry" in attempt
    assert "target->GetEntry() != BossEntry || !target->IsInCombat()" in attempt
    assert 'block("boss_not_engaged")' in attempt
    # Window proof, then raid Sated/Exhaustion/active-lust lockouts, then the
    # native spellbook, cooldown and GCD gates inside TryCastFriendlySpell.
    order = [
        attempt.index('block("boss_not_engaged")'),
        attempt.index("FindRaidLockout(*encounterSnapshot)"),
        attempt.index("findNativeRaidLockout()"),
        attempt.index('block("spell_not_in_shaman_spellbook")'),
        attempt.index("TryCastFriendlySpell("),
        attempt.index("raid->MagmawBloodlustSubmitted = true"),
    ]
    assert order == sorted(order)
    assert "+ LustTriggerName(trigger);" in attempt
    assert "Cohort()" not in attempt and "Party()" not in attempt

    for path in (TIMING, MODULE):
        assert len(text(path).splitlines()) < 1000, path
