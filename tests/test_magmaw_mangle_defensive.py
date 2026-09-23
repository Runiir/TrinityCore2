"""Blood tank pre-empts Magmaw's Mangle with its own native defensives.

The window is read from Magmaw's native Mangle timer (published under Massive
Crash 88253, the same timer the pre-Mangle lust uses). Icebound Fortitude is
the strongest defensive and gets a 1.5 s lead; Bone Shield gets a 6 s lead.
Vampiric Blood stays with the profile's reactive 70% row: its 15% health is
taken back on expiry, which the replay of base-0891a99 / bundle1-b8a539b kills
showed lands mid-Mangle when it is pre-cast.
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

using States = std::array<DefensiveReadiness, DefensivePriority.size()>;
static States Ready(bool ibfReady = true, bool boneReady = true,
    bool ibfActive = false, bool boneActive = false)
{
    return { DefensiveReadiness{ IceboundFortitudeSpell, true, ibfReady, ibfActive },
        DefensiveReadiness{ BoneShieldSpell, true, boneReady, boneActive } };
}

int main()
{
    static_assert(DefensivePriority[0] == IceboundFortitudeSpell, "strongest first");
    static_assert(PreMangleIceboundLeadMs == 1500 && PreMangleBoneShieldLeadMs == 6000, "leads");

    // Outside the longest lead: nothing.
    assert(!ObserveMangleDefensiveWindow(Encounter(6001), TankGuid));
    assert(!ObserveMangleDefensiveWindow(Encounter(90000), TankGuid));

    // 6 s out: only Bone Shield is inside its lead.
    auto early = ObserveMangleDefensiveWindow(Encounter(6000), TankGuid);
    assert(early && early->Trigger == DefensiveTrigger::PreMangleLead);
    assert(early->RemainingMs == 6000 && early->BossGuid == BossGuid);
    assert(SelectDefensive(*early, Ready()) == BoneShieldSpell);
    assert(!SelectDefensive(*early, Ready(true, true, false, true)));

    // 1.5 s out: Icebound Fortitude first; Bone Shield if IBF is on cooldown
    // or already running; nothing if both are covered.
    auto late = ObserveMangleDefensiveWindow(Encounter(1500), TankGuid);
    assert(late && SelectDefensive(*late, Ready()) == IceboundFortitudeSpell);
    assert(SelectDefensive(*late, Ready(false)) == BoneShieldSpell);
    assert(SelectDefensive(*late, Ready(true, true, true)) == BoneShieldSpell);
    assert(!SelectDefensive(*late, Ready(false, false)));
    assert(!SelectDefensive(*late, Ready(true, true, true, true)));
    States unknown = Ready();
    unknown[0].Known = false;
    assert(SelectDefensive(*late, unknown) == BoneShieldSpell);

    // An overdue Mangle or the running Mangle -> Crash sequence publishes 0.
    auto overdue = ObserveMangleDefensiveWindow(Encounter(0, true), TankGuid);
    assert(overdue && overdue->RemainingMs == 0);
    assert(SelectDefensive(*overdue, Ready()) == IceboundFortitudeSpell);

    // Mangle lands on the victim: another victim, another bot, no window.
    assert(!ObserveMangleDefensiveWindow(Encounter(1000, false, DpsGuid), TankGuid));
    assert(!ObserveMangleDefensiveWindow(Encounter(1000), DpsGuid));

    // Already seized (any mode's Mangle aura or the seat aura): the window is
    // open whatever the timer says, and the threat wipe does not close it.
    for (uint32 aura : MangleAuras)
    {
        Blackboard seized = Encounter(95000, false, DpsGuid);
        seized.Players.front().Auras.push_back({ aura, BossGuid, 1, 0 });
        auto window = ObserveMangleDefensiveWindow(seized, TankGuid);
        assert(window && window->Trigger == DefensiveTrigger::Mangled);
        assert(SelectDefensive(*window, Ready()) == IceboundFortitudeSpell);
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


def test_vampiric_blood_stays_reactive() -> None:
    header = text(HEADER)
    priority = header[header.index("DefensivePriority = {"):]
    priority = priority[:priority.index("};")]
    assert "IceboundFortitudeSpell, BoneShieldSpell" in priority
    assert "55233" not in header and "VampiricBlood" not in priority


def test_candidate_reproves_the_window_natively_and_casts_only_known_ready_spells() -> None:
    module = text(MODULE)
    body = function_body(module, "void BotWorldPopulationMgr::SubmitMagmawMangleDefensiveCandidate(")
    # Exact boss node and the admitted raid tank only.
    assert "cohort->Config.ValidationRouteNodeId != EncounterNode" in body
    assert 'cohort->Config.ValidationRouteKind != "boss"' in body
    assert 'row->second.Role != "tank"' in body
    assert "BotActionArbitration::Priority::Survival" in body

    # Readiness is native: spellbook, spell history cooldown and own aura.
    readiness = function_body(module, "Readiness NativeReadiness(Player const* bot)")
    assert "bot->HasSpell(spellId)" in readiness
    assert "bot->GetSpellHistory()->IsReady(spellInfo)" in readiness
    assert "bot->HasAura(spellId)" in readiness

    # At attempt time the live boss's own timer and victim are re-read.
    native = function_body(module, "std::optional<DefensiveWindow> NativeWindow(")
    assert "GetTimeUntilEncounterMechanic(MassiveCrashSpell)" in native
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
