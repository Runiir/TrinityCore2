"""Blood tank pre-empts Magmaw's Mangle with its own native defensives.

The window is read from Magmaw's native Mangle timer (published under Massive
Crash 88253, the same timer the pre-Mangle lust uses). Icebound Fortitude is
the strongest defensive and gets a 1.5 s lead; Bone Shield gets a 6 s lead and
is refreshed below 3 charges. Vampiric Blood takes Icebound's place at the same
1.5 s lead only when Icebound cannot cover the Mangle (TANK-003,
b3-0dbce440-k1: Icebound spent 30 s earlier, no cooldown at the seize, tank
dead). Its 15% health is taken back on expiry, but never the last point
(AuraEffect::HandleAuraModIncreaseHealth).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
MAGMAW = BOTS / "Content/Raids/BlackwingDescent/Encounters/Magmaw"
HEADER = MAGMAW / "BotMagmawMangleDefensive.h"
MODULE = MAGMAW / "BotWorldPopulationMgrMagmawMangleDefensive.cpp"
CALL_SITE = BOTS / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp"
MANAGER = BOTS / "BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
BOSS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_magmaw.cpp"
DBC = ROOT / "data/dbc/enUS"


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
                return source[brace + 1:index]
    raise AssertionError(f"unterminated function: {signature}")


def test_window_and_selection_follow_the_native_mangle_timer(tmp_path: Path) -> None:
    source = tmp_path / "mangle_defensive.cpp"
    binary = tmp_path / "mangle_defensive"
    source.write_text(r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMangleDefensive.h"

#include <cassert>
#include <cstring>

using namespace BotEncounter;
using namespace BotEncounter::MagmawMangleDefensive;

static ObjectGuid const BossGuid(HighGuid::Unit, BossEntry, uint32(41));
static ObjectGuid const TankGuid(HighGuid::Player, uint32(30002));
static ObjectGuid const DpsGuid(HighGuid::Player, uint32(30001));

static Blackboard Encounter(uint32 remainingMs, bool sequenceActive = false,
    ObjectGuid victim = TankGuid)
{
    ActorSnapshot boss;
    boss.Guid = BossGuid;
    boss.Entry = BossEntry;
    boss.Alive = boss.Attackable = boss.Selectable = boss.InCombat = true;
    boss.VictimGuid = victim;
    boss.MechanicTimers.push_back({ MassiveCrashSpell, remainingMs,
        sequenceActive, FactSource::NativeInstanceState });
    ActorSnapshot tank;
    tank.Guid = TankGuid;
    tank.Kind = ActorKind::Player;
    tank.Role = "tank";
    tank.Alive = tank.InCombat = true;
    Blackboard board;
    board.Route.NodeId = std::string(EncounterNode);
    board.NativeBossState = "in_progress";
    board.Hostiles = { boss };
    board.Players = { tank };
    return board;
}

using States = DefensiveStates;
static States Ready(bool ibfReady = true, bool boneReady = true,
    bool ibfActive = false, bool boneActive = false,
    bool vbReady = true, bool vbActive = false)
{
    return { DefensiveReadiness{ IceboundFortitudeSpell, true, ibfReady, ibfActive },
        DefensiveReadiness{ VampiricBloodSpell, true, vbReady, vbActive },
        DefensiveReadiness{ BoneShieldSpell, true, boneReady, boneActive } };
}

int main()
{
    static_assert(DefensivePriority[0] == IceboundFortitudeSpell, "strongest first");
    static_assert(DefensivePriority[1] == VampiricBloodSpell, "Icebound's stand-in");
    static_assert(DefensivePriority[2] == BoneShieldSpell, "then Bone Shield");
    static_assert(PreMangleIceboundLeadMs == 1500 && PreMangleBoneShieldLeadMs == 6000, "leads");
    assert(PreMangleLeadMs(VampiricBloodSpell) == PreMangleIceboundLeadMs);
    assert(PreMangleLeadMs(BoneShieldSpell) == PreMangleBoneShieldLeadMs);
    static_assert(BoneShieldRefreshBelowCharges == 3, "refresh below 3 charges");
    assert(!BoneShieldCovers(false, 0) && !BoneShieldCovers(true, 2));
    assert(BoneShieldCovers(true, 3) && BoneShieldCovers(true, 6));

    // Outside the longest lead: nothing.
    assert(!ObserveMangleDefensiveWindow(Encounter(6001), TankGuid));
    assert(!ObserveMangleDefensiveWindow(Encounter(90000), TankGuid));

    // 6 s out: only Bone Shield is inside its lead, whatever Icebound's
    // state; Vampiric Blood waits for the 1.5 s pre-cast point.
    auto early = ObserveMangleDefensiveWindow(Encounter(6000), TankGuid);
    assert(early && early->Trigger == DefensiveTrigger::PreMangleLead);
    assert(early->RemainingMs == 6000 && early->BossGuid == BossGuid);
    assert(SelectDefensive(*early, Ready()) == BoneShieldSpell);
    assert(SelectDefensive(*early, Ready(false)) == BoneShieldSpell);
    assert(!SelectDefensive(*early, Ready(true, true, false, true)));
    assert(!SelectDefensive(*early, Ready(false, true, false, true)));

    // 1.5 s out: Icebound Fortitude first.  Icebound running: it covers the
    // hit, so Bone Shield (if not covering) and never Vampiric Blood.
    auto late = ObserveMangleDefensiveWindow(Encounter(1500), TankGuid);
    assert(late && SelectDefensive(*late, Ready()) == IceboundFortitudeSpell);
    assert(SelectDefensive(*late, Ready(true, true, true)) == BoneShieldSpell);
    assert(!SelectDefensive(*late, Ready(true, true, true, true)));
    assert(!SelectDefensive(*late, Ready(true, false, true)));
    // TANK-003: Icebound on cooldown at the pre-cast point -> Vampiric Blood,
    // then Bone Shield if it does not cover.
    assert(SelectDefensive(*late, Ready(false)) == VampiricBloodSpell);
    assert(SelectDefensive(*late, Ready(false, false)) == VampiricBloodSpell);
    assert(SelectDefensive(*late, Ready(false, true, false, false, true, true)) == BoneShieldSpell);
    assert(SelectDefensive(*late, Ready(false, true, false, false, false)) == BoneShieldSpell);
    assert(!SelectDefensive(*late, Ready(false, true, false, true, false)));
    assert(!SelectDefensive(*late, Ready(false, false, false, false, false)));
    States unknown = Ready();
    unknown[0].Known = false;
    assert(SelectDefensive(*late, unknown) == VampiricBloodSpell);
    States noBlood = Ready(false);
    noBlood[1].Known = false;
    assert(SelectDefensive(*late, noBlood) == BoneShieldSpell);
    // Between the leads (2 s out) Vampiric Blood is not yet due.
    auto between = ObserveMangleDefensiveWindow(Encounter(2000), TankGuid);
    assert(between && SelectDefensive(*between, Ready(false)) == BoneShieldSpell);
    assert(!SelectDefensive(*between, Ready(false, true, false, true)));

    // An overdue Mangle or the running Mangle -> Crash sequence publishes 0.
    auto overdue = ObserveMangleDefensiveWindow(Encounter(0, true), TankGuid);
    assert(overdue && overdue->RemainingMs == 0);
    assert(SelectDefensive(*overdue, Ready()) == IceboundFortitudeSpell);

    // A live Mangle timer never exceeds the 95 s repeat. A larger value is
    // an overdue event's wrapped uint32 subtraction: due now, not closed.
    static_assert(NativeMangleRepeatMs == 95000, "EVENT_MANGLE repeat");
    for (uint32 wrapped : { 4294967295u - 1u, 4294966000u, 95001u })
    {
        auto due = ObserveMangleDefensiveWindow(Encounter(wrapped), TankGuid);
        assert(due && due->RemainingMs == 0);
        assert(SelectDefensive(*due, Ready()) == IceboundFortitudeSpell);
    }
    assert(MangleDueInMs(95000) == 95000 && MangleDueInMs(1500) == 1500);
    assert(!ObserveMangleDefensiveWindow(Encounter(95000), TankGuid));

    // Mangle lands on the victim: another victim, another bot, no window.
    assert(!ObserveMangleDefensiveWindow(Encounter(1000, false, DpsGuid), TankGuid));
    assert(!ObserveMangleDefensiveWindow(Encounter(1000), DpsGuid));

    // Already seized (any mode's Mangle aura or the seat aura): the window is
    // open whatever the timer says, and the threat wipe does not close it.
    // Seized without Icebound (on cooldown, or expired mid-seize): Vampiric
    // Blood covers the rest of the hold.
    for (uint32 aura : MangleAuras)
    {
        Blackboard seized = Encounter(95000, false, DpsGuid);
        seized.Players.front().Auras.push_back({ aura, BossGuid, 1, 0 });
        auto window = ObserveMangleDefensiveWindow(seized, TankGuid);
        assert(window && window->Trigger == DefensiveTrigger::Mangled);
        assert(SelectDefensive(*window, Ready()) == IceboundFortitudeSpell);
        assert(SelectDefensive(*window, Ready(false, false, false, true)) == VampiricBloodSpell);
        assert(!SelectDefensive(*window, Ready(false, false, true, true)));
    }

    // The cooldown plan's timer: open for the whole engaged fight, due time
    // from the native publication, in progress at 0 or once seized.
    {
        auto running = ObserveMangleTimer(Encounter(39800), TankGuid);
        assert(running && running->DueInMs == 39800 && !running->HitInProgress);
        auto sequence = ObserveMangleTimer(Encounter(30000, true), TankGuid);
        assert(sequence && sequence->DueInMs == 0 && sequence->HitInProgress);
        auto wrapped = ObserveMangleTimer(Encounter(4294966000u), TankGuid);
        assert(wrapped && wrapped->DueInMs == 0 && wrapped->HitInProgress);
        // Another victim does not close the plan's timer.
        auto offTank = ObserveMangleTimer(Encounter(39800, false, DpsGuid), TankGuid);
        assert(offTank && offTank->DueInMs == 39800);
        Blackboard seized = Encounter(86500);
        seized.Players.front().Auras.push_back({ MangleAuras.back(), BossGuid, 1, 0 });
        auto held = ObserveMangleTimer(seized, TankGuid);
        assert(held && held->DueInMs == 86500 && held->HitInProgress);
        Blackboard trash = Encounter(39800);
        trash.Route.NodeId = "bwd.magmaw.drudges";
        assert(!ObserveMangleTimer(trash, TankGuid));
        Blackboard visible = Encounter(39800);
        visible.Hostiles.front().MechanicTimers.front().Source = FactSource::VisibleCast;
        assert(!ObserveMangleTimer(visible, TankGuid));
        Blackboard idle = Encounter(39800);
        idle.NativeBossState = "not_in_progress";
        assert(!ObserveMangleTimer(idle, TankGuid));
        assert(!ObserveMangleTimer(Encounter(39800), ObjectGuid()));
    }

    // Never on trash, before pull, after reset, for a dead tank, for a
    // non-native timer or without the boss in combat.
    {
        Blackboard trash = Encounter(1000);
        trash.Route.NodeId = "bwd.magmaw.drudges";
        assert(!ObserveMangleDefensiveWindow(trash, TankGuid));
    }
    {
        Blackboard idle = Encounter(1000);
        idle.NativeBossState = "not_in_progress";
        assert(!ObserveMangleDefensiveWindow(idle, TankGuid));
    }
    {
        Blackboard dead = Encounter(1000);
        dead.Players.front().Alive = false;
        assert(!ObserveMangleDefensiveWindow(dead, TankGuid));
    }
    {
        Blackboard visible = Encounter(1000);
        visible.Hostiles.front().MechanicTimers.front().Source = FactSource::VisibleCast;
        assert(!ObserveMangleDefensiveWindow(visible, TankGuid));
    }
    {
        Blackboard calm = Encounter(1000);
        calm.Hostiles.front().InCombat = false;
        assert(!ObserveMangleDefensiveWindow(calm, TankGuid));
    }
    {
        Blackboard none = Encounter(1000);
        none.Hostiles.front().MechanicTimers.clear();
        assert(!ObserveMangleDefensiveWindow(none, TankGuid));
    }

    assert(std::strcmp(DefensiveTriggerName(DefensiveTrigger::Mangled), "mangled") == 0);
    assert(std::strcmp(DefensiveTriggerName(DefensiveTrigger::PreMangleLead), "pre_mangle_lead") == 0);
    return 0;
}
''', encoding="utf-8")
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-I", str(ROOT / "src/server/game"),
         "-I", str(ROOT / "src/server/game/Entities/Object"),
         "-I", str(ROOT / "src/server/shared"),
         "-I", str(ROOT / "src/common"),
         str(source), "-o", str(binary)],
        check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_vampiric_blood_only_stands_in_for_icebound() -> None:
    header = text(HEADER)
    priority = header[header.index("DefensivePriority = {"):]
    priority = priority[:priority.index("};")]
    assert "IceboundFortitudeSpell, VampiricBloodSpell, BoneShieldSpell" in priority
    assert "constexpr uint32 VampiricBloodSpell = 55233;" in header
    select = function_body(header, "inline std::optional<uint32> SelectDefensive(")
    assert "spellId == VampiricBloodSpell && iceboundCovers" in select
    covers = function_body(header, "inline bool IceboundCovers(")
    assert "return state.Active || (state.Known && state.Ready);" in covers
    # The expiry health loss never takes the last point (the header's claim).
    effects = text(ROOT / "src/server/game/Spells/Auras/SpellAuraEffects.cpp")
    handler = function_body(effects, "void AuraEffect::HandleAuraModIncreaseHealth(")
    assert "int32 value = std::min<int32>(target->GetHealth() - 1, GetAmount());" in handler
    # Vampiric Blood's 15% is a share of maximum health (the spell script).
    dk = text(ROOT / "src/server/scripts/Spells/spell_dk.cpp")
    vb = dk[dk.index("class spell_dk_vampiric_blood"):dk.index("// Updated 4.3.4\n// -52284")]
    assert "amount = GetUnitOwner()->CountPctFromMaxHealth(amount);" in vb


def test_candidate_reproves_the_window_natively_and_casts_only_known_ready_spells() -> None:
    module = text(MODULE)
    body = function_body(module, "void BotWorldPopulationMgr::SubmitMagmawMangleDefensiveCandidate(")
    # Exact boss node and the admitted raid tank only.
    assert "cohort->Config.ValidationRouteNodeId != EncounterNode" in body
    assert 'cohort->Config.ValidationRouteKind != "boss"' in body
    assert 'row->second.Role != "tank"' in body
    assert "BotActionArbitration::Priority::Survival" in body

    # Readiness is native: spellbook, spell history cooldown and own aura;
    # Bone Shield's "covers" also reads its native charges.
    readiness = function_body(module, "Readiness NativeReadiness(Player const* bot)")
    assert "bot->HasSpell(spellId)" in readiness
    assert "NativelyKnownAndReady(bot, spellId)" in readiness
    assert "bot->HasAura(spellId)" in readiness
    assert "spellId == BoneShieldSpell\n            ? NativeBoneShieldCovers(bot)" in readiness
    ready = function_body(module, "bool NativelyKnownAndReady(Player const* bot, uint32 spellId)")
    assert "bot->HasSpell(spellId)" in ready
    assert "bot->GetSpellHistory()->IsReady(spellInfo)" in ready
    bone = function_body(module, "bool NativeBoneShieldCovers(Player const* bot)")
    assert "bot->GetAura(BoneShieldSpell)" in bone and "boneShield->GetCharges()" in bone

    # At attempt time the live boss's own timer and victim are re-read.
    native = function_body(module, "std::optional<DefensiveWindow> NativeWindow(")
    assert "GetTimeUntilEncounterMechanic(MassiveCrashSpell)" in native
    # No timer stays closed; a wrapped overdue value is due now.
    assert "publishedMs == std::numeric_limits<uint32>::max()" in native
    assert "uint32 const remainingMs = MangleDueInMs(publishedMs);" in native
    assert "MangleDueInMs(mangle->RemainingMs)" in text(HEADER)
    assert "boss->GetVictim() != bot" in native
    assert "boss->GetEntry() != BossEntry" in native and "!boss->IsInCombat()" in native

    attempt = body[body.index("defensive.Attempt ="):]
    order = [
        attempt.index("magmaw_mangle_defensive_stale_context"),
        attempt.index("NativeWindow(bot, bossGuid)"),
        attempt.index("SelectDefensive(*native, NativeReadiness(bot)) != spellId"),
        attempt.index("TryCastFriendlySpell(bot, bot, spellId, &failureReason)"),
        attempt.index('"magmaw_mangle_defensive_submitted_native"'),
    ]
    assert order == sorted(order)

    # The helper reads the same native timer as the pre-Mangle lust.
    boss = text(BOSS)
    timer = function_body(boss, "uint32 GetTimeUntilEncounterMechanic(")
    assert "return events.GetTimeUntilEvent(EVENT_MANGLE);" in timer
    assert "if (mangleAt && mangleAt <= events.GetTimer())\n            return 0;" in timer
    mangle_event = boss[boss.index("case EVENT_MANGLE:"):boss.index("case EVENT_PREPARE_MASSIVE_CRASH:")]
    assert "events.Repeat(1min + 35s);" in mangle_event

    # Wiring: declared, submitted next to the lust candidate, built.
    assert "void SubmitMagmawMangleDefensiveCandidate(BotUpdateContext& context);" in text(MANAGER)
    call_site = text(CALL_SITE)
    assert re.search(r"SubmitMagmawBloodlustCandidate\(context\);\s*"
                     r"SubmitMagmawMangleDefensiveCandidate\(context\);", call_site)
    assert ("Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/"
            "BotWorldPopulationMgrMagmawMangleDefensive.cpp") in text(CMAKE)

    for path in (HEADER, MODULE, CALL_SITE, MANAGER, BOSS):
        assert len(text(path).splitlines()) < 1000, path


@pytest.mark.skipif(not (DBC / "Spell.dbc").exists(), reason="pinned DBC not extracted")
def test_client_data_behind_the_leads() -> None:
    sys.path.insert(0, str(ROOT))
    from tools.bot_ml.build_validation_provisioning import load_wdbc_values

    spells = {r[0]: r for r in load_wdbc_values(
        DBC / "Spell.dbc", "niiiiiiiiiiiiiiifiiiissxxiixxifiiiiiiixiiiiiiiii")}
    durations = {r[0]: r[1] for r in load_wdbc_values(DBC / "SpellDuration.dbc", "niii")}
    cooldowns = {r[0]: r for r in load_wdbc_values(DBC / "SpellCooldowns.dbc", "diii")}
    effects: dict[int, list[list[int]]] = {}
    for row in load_wdbc_values(DBC / "SpellEffect.dbc", "nifiiiffiiiiiifiifiiiiiiiix"):
        effects.setdefault(row[24], []).append(row)

    def timing(spell_id: int) -> tuple[int, int, int]:
        row = spells[spell_id]
        cooldown = cooldowns[row[37]]
        return durations[row[13]], cooldown[2], cooldown[3]

    # Icebound Fortitude: 12 s, 3 min, off the GCD; -20% damage taken (aura 87).
    assert timing(48792) == (12000, 180000, 0)
    assert any(e[3] == 87 and e[5] == -20 for e in effects[48792])
    # Sanguine Fortitude rank 1 (provisioned for Mgwtankb) adds -15% to it.
    assert any(e[3] == 107 and e[5] == -15 for e in effects[81125])
    # Bone Shield: 5 min aura, 1 min cooldown, 1.5 s GCD; -20% damage taken.
    assert timing(49222) == (300000, 60000, 1500)
    assert any(e[3] == 87 and e[5] == -20 for e in effects[49222])
    # Vampiric Blood: 10 s, +15% health (aura 34) and +25% healing (aura 118).
    assert timing(55233) == (10000, 60000, 0)
    assert {(e[3], e[5]) for e in effects[55233]} == {(118, 25), (34, 15)}
