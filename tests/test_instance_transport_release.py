"""Round 2 (BWD 10N, Nefarian): no in-place revive on a raid transport, and
native death/resurrection edges counted per bot.

Run 6bf52232 recorded 1103 lethal combat-log events in Nefarian's boss window
while every native signal said 0 deaths and alive_count stayed 10: a bot that
released on the elevator (GO 207834) was revived at 50% where it stood by
Player::RepopAtGraveyard's `|| GetTransport()` clause (its cross-map teleport
to the graveyard is refused for a living bot session).

1. instance_transport_release.cpp detaches a releasing passenger from a static
   raid elevator (GAMEOBJECT_TYPE_TRANSPORT) during an encounter in
   OnPlayerRepop (end of BuildPlayerRepop, before RepopAtGraveyard), so the
   ordinary ghost path runs. Moving ships, zeppelins and gunships, dungeons
   and out-of-encounter raid elevators keep the clause.
2. BotNativeLifeEvents counts every alive/dead edge on UpdateBot entry and
   exit, at the native lethal hit (before Unit::Kill; an unobserved revive is
   proven by the next death) and after a caster's resurrection acceptance has
   run the delayed resurrection, scoped per process-unique cohort lifecycle
   (begun by ResetCombatLog, so not per recording window, and never shared by
   two cohorts),
   so a revive and the next death between two of the target's updates are
   both counted (native_recovery.members native_death_count /
   native_resurrection_count).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from tests.test_nefarian_strategy import INCLUDES, ROOT

SCRIPT = ROOT / "src/server/scripts/World/instance_transport_release.cpp"
HELPER = ROOT / "src/server/scripts/World/instance_transport_release.h"
LOADER = ROOT / "src/server/scripts/World/world_script_loader.cpp"
PLAYER = ROOT / "src/server/game/Entities/Player/Player.cpp"
MISC = ROOT / "src/server/game/Handlers/MiscHandler.cpp"
NATIVE_ACTION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativeAction.cpp"
UPDATE_BOT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBot.cpp"
RAID_RUNTIME = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRaidRuntime.cpp"
NOTIFICATIONS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatNotifications.cpp"


def _run(tmp_path: Path, program: str) -> str:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
               "-I", str(HELPER.parent)]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return result.stdout


RELEASE_PROGRAM = r'''
#include "instance_transport_release.h"
#include <cstdio>

static int failures = 0;
#define CHECK(condition, message) do { if (!(condition)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, message); ++failures; } } while (0)

// Player::RepopAtGraveyard's revive predicate after the OnPlayerRepop hook
// ran (a detached passenger has no transport any more).
struct Releasing
{
    bool OnTransport;
    bool StaticElevator;
    bool RaidMap;
    bool EncounterInProgress;
    bool NoGhostZone = false;
    bool BelowMinHeight = false;
};

static bool RevivedInPlace(Releasing const& player)
{
    InstanceTransportRelease::Observation observation;
    observation.OnTransport = player.OnTransport;
    observation.StaticElevator = player.StaticElevator;
    observation.RaidMap = player.RaidMap;
    observation.EncounterInProgress = player.EncounterInProgress;
    bool const stillPassenger = player.OnTransport
        && !InstanceTransportRelease::DetachBeforeGraveyard(observation);
    return player.NoGhostZone || stillPassenger || player.BelowMinHeight;
}

int main()
{
    // Nefarian's elevator (GO 207834, GAMEOBJECT_TYPE_TRANSPORT) during the
    // encounter: a ghost, never revived.
    CHECK(!RevivedInPlace({ true, true, true, true }),
        "a dead passenger on a raid elevator during an encounter must not be revived in place");
    // The Icecrown gunship (GAMEOBJECT_TYPE_MO_TRANSPORT) during its encounter: vanilla.
    CHECK(RevivedInPlace({ true, false, true, true }), "a moving map transport keeps the native clause");
    // Unchanged native behaviour elsewhere.
    CHECK(RevivedInPlace({ true, false, false, false }), "open-world ship/zeppelin keeps the native revive");
    CHECK(RevivedInPlace({ true, true, false, true }), "dungeon elevator keeps the native clause");
    CHECK(RevivedInPlace({ true, true, true, false }), "raid elevator outside an encounter keeps the native clause");
    CHECK(!RevivedInPlace({ false, false, true, true }), "no transport: ordinary ghost release");
    // The other native clauses still apply to a detached passenger.
    Releasing noGhost{ true, true, true, true };
    noGhost.NoGhostZone = true;
    CHECK(RevivedInPlace(noGhost), "a no-ghost zone still revives");
    Releasing belowMap{ true, true, true, true };
    belowMap.BelowMinHeight = true;
    CHECK(RevivedInPlace(belowMap), "below the map minimum still revives");
    return failures ? 1 : 0;
}
'''


LIFE_PROGRAM = r'''
#include "Bots/BotNativeLifeEvents.h"
#include <cstdio>
#include <string>

static int failures = 0;
#define CHECK(condition, message) do { if (!(condition)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, message); ++failures; } } while (0)

using namespace BotNativeLifeEvents;

struct Bot
{
    uint32 Guid;
    bool Alive = true;
};

// Scope = { process-unique lifecycle id, AttemptId }.  ResetCombatLog (a true
// start) calls BeginLifecycle; a recording-window rotation does not.
static Scope Lifecycle1;
static Scope Lifecycle2;

// The runtime's observation sites.
static void UpdateEntry(Bot const& bot, Scope const& scope, uint64 now) { Observe(bot.Guid, scope, bot.Alive, now); }
static void UpdateExit(Bot const& bot, Scope const& scope, uint64 now) { Observe(bot.Guid, scope, bot.Alive, now); }
// NotifyCombatDamage: a lethal landed hit, just before Unit::Kill sets JUST_DIED.
static void LethalHit(Bot& bot, Scope const& scope, uint64 now) { ObserveLethal(bot.Guid, scope, now); bot.Alive = false; }
// BotNativeAction::CombatResAccept inside the caster's update.  The native
// response only schedules DELAYED_RESURRECT_PLAYER; the teleport
// acknowledgement (when the caster can send it) runs the resurrection.
static void CasterAcceptsResurrection(Bot& target, Scope const& scope, uint64 now, bool nearTeleportAck)
{
    Observe(target.Guid, scope, target.Alive, now);  // before the response: dead
    // HandleResurrectResponseOpcode: teleport scheduled, still dead here.
    if (nearTeleportAck)
        target.Alive = true;                         // HandleMoveTeleportAck -> ProcessDelayedOperations
    Observe(target.Guid, scope, target.Alive, now);  // after the acknowledgement
}

int main()
{
    BeginLifecycle("bwd_c0");
    Lifecycle1 = LifecycleScope("bwd_c0", 1);
    uint64 now = 1000;
    // 1. Release-revive inside the bot's own update, then a death before its next update.
    Bot bot{ 11005009 };
    UpdateEntry(bot, Lifecycle1, now); UpdateExit(bot, Lifecycle1, now);
    CHECK(Get(bot.Guid, Lifecycle1).Deaths == 0, "baseline counts nothing");
    LethalHit(bot, Lifecycle1, now += 50);
    UpdateEntry(bot, Lifecycle1, now += 50);         // seen dead: same death
    bot.Alive = true;                                // released and revived in place
    UpdateExit(bot, Lifecycle1, now += 1);
    LethalHit(bot, Lifecycle1, now += 50);           // killed again before its next update
    CHECK(Get(bot.Guid, Lifecycle1).Deaths == 2 && Get(bot.Guid, Lifecycle1).Resurrections == 1,
        "own-update revive counted");

    // 2. Astra probe, delayed path: a battle resurrection completed by the
    //    caster's teleport acknowledgement, then a death before the target's
    //    next update.
    Bot target{ 11005003 };
    UpdateEntry(target, Lifecycle1, now); UpdateExit(target, Lifecycle1, now);
    LethalHit(target, Lifecycle1, now += 10);
    CasterAcceptsResurrection(target, Lifecycle1, now += 10, true);
    LethalHit(target, Lifecycle1, now += 10);
    UpdateEntry(target, Lifecycle1, now += 10);
    Counts const probe = Get(target.Guid, Lifecycle1);
    CHECK(probe.Deaths == 2, "both deaths counted");
    CHECK(probe.Resurrections == 1, "the delayed caster-side resurrection counted");
    CHECK(probe.Dead, "currently dead");
    std::string const fields = MemberJsonFields(target.Guid, Lifecycle1);
    CHECK(fields.find(",\"native_death_count\":2,\"native_resurrection_count\":1,") == 0, "member json fields");
    CHECK(fields.find("\"native_dead\":true") != std::string::npos, "member json dead flag");

    // 3. A resurrection no observation site saw (a far teleport completing
    //    later, any other native path): the next lethal hit proves it.
    Bot far{ 11005007 };
    UpdateEntry(far, Lifecycle1, now);
    LethalHit(far, Lifecycle1, now += 10);
    CasterAcceptsResurrection(far, Lifecycle1, now += 10, false);  // still dead after the response
    far.Alive = true;                                               // resurrected elsewhere, unobserved
    LethalHit(far, Lifecycle1, now += 10);
    CHECK(Get(far.Guid, Lifecycle1).Deaths == 2 && Get(far.Guid, Lifecycle1).Resurrections == 1,
        "an unobserved resurrection is counted at the next death");

    // 4. A recording-window rotation (RecordRunStart, no ResetCombatLog) keeps
    //    the lifecycle scope: counts continue.
    CHECK(LifecycleScope("bwd_c0", 1) == Lifecycle1, "rotation keeps the scope");
    UpdateEntry(target, LifecycleScope("bwd_c0", 1), now += 60000);
    CHECK(Get(target.Guid, Lifecycle1).Deaths == 2, "counts survive a recording-window rotation");

    // 4b. Astra v3: cohort A stops after a death; cohort B, whose own
    //     CombatLogEpoch/AttemptId coincide with A's ({1,1} each), leases the
    //     same bot GUID and is provisioned alive.  B inherits nothing.
    BeginLifecycle("cohort_a");
    Scope const cohortA = LifecycleScope("cohort_a", 1);
    Bot reused{ 11009001 };
    UpdateEntry(reused, cohortA, now);
    LethalHit(reused, cohortA, now += 10);
    CHECK(Get(reused.Guid, cohortA).Deaths == 1, "cohort A's death");
    BeginLifecycle("cohort_b");
    Scope const cohortB = LifecycleScope("cohort_b", 1);
    CHECK(!(cohortA == cohortB), "equal per-cohort counters never share a scope");
    CHECK(!Get(reused.Guid, cohortB).Observed, "cohort B reads nothing of cohort A");
    reused.Alive = true;                              // provisioning revives the leased bot
    UpdateEntry(reused, cohortB, now += 10);
    UpdateExit(reused, cohortB, now);
    CHECK(Get(reused.Guid, cohortB).Deaths == 0 && Get(reused.Guid, cohortB).Resurrections == 0,
        "no inherited death, no provisioning resurrection");
    // A cohort recreated under the same id also gets a new lifecycle.
    BeginLifecycle("cohort_a");
    CHECK(!(LifecycleScope("cohort_a", 1) == cohortA), "a restarted cohort id gets a new lifecycle");

    // 5. A true restart (new epoch/attempt) starts from a fresh baseline; the
    //    old lifecycle's counts are not exported under the new one, and
    //    another cohort's bot still in its lifecycle is untouched.
    BeginLifecycle("bwd_c0");
    Lifecycle2 = LifecycleScope("bwd_c0", 2);
    CHECK(!Get(target.Guid, Lifecycle2).Observed, "new lifecycle reads nothing before observing");
    UpdateEntry(target, Lifecycle2, now += 100);
    CHECK(Get(target.Guid, Lifecycle2).Deaths == 0, "new lifecycle baseline inherits nothing");
    CHECK(!Get(target.Guid, Lifecycle1).Observed, "old lifecycle no longer readable");
    CHECK(Get(bot.Guid, Lifecycle1).Deaths == 2, "other cohort's counts are kept");
    return failures ? 1 : 0;
}
'''


def test_raid_transport_release_does_not_revive_in_place(tmp_path: Path) -> None:
    _run(tmp_path, RELEASE_PROGRAM)


def test_release_hook_is_wired_before_repop_at_graveyard() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert "void OnPlayerRepop(Player* player) override" in script
    assert "DetachBeforeGraveyard(observation)" in script
    assert "transport->RemovePassenger(player);" in script
    assert "observation.RaidMap = map && map->IsRaid();" in script
    assert "object->GetGoType() == GAMEOBJECT_TYPE_TRANSPORT" in script
    assert "instance->IsEncounterInProgress()" in script
    loader = LOADER.read_text(encoding="utf-8")
    assert "void AddSC_instance_transport_release();" in loader
    assert re.search(r"void AddWorldScripts\(\)\n\{[^}]*AddSC_instance_transport_release\(\);", loader)

    # The hook runs after the body became a ghost and before the revive clause.
    player = PLAYER.read_text(encoding="utf-8")
    repop = player[player.index("void Player::BuildPlayerRepop()"):]
    repop = repop[:repop.index("\n}\n")]
    assert repop.index("setDeathState(DEAD);") < repop.index("sScriptMgr->OnPlayerRepop(this);")
    graveyard = player[player.index("void Player::RepopAtGraveyard()"):]
    assert "|| GetTransport() ||" in graveyard[:graveyard.index("\n}\n")]
    # Human and bot releases both call BuildPlayerRepop, then RepopAtGraveyard.
    misc = MISC.read_text(encoding="utf-8")
    assert "GetPlayer()->BuildPlayerRepop();\n    GetPlayer()->RepopAtGraveyard();" in misc
    assert "HandleRepopRequestOpcode(repop);" in NATIVE_ACTION.read_text(encoding="utf-8")


def test_native_life_edges_count_every_death_and_revive(tmp_path: Path) -> None:
    _run(tmp_path, LIFE_PROGRAM)


def test_life_edges_observed_on_update_entry_and_exit_and_exported() -> None:
    update = UPDATE_BOT.read_text(encoding="utf-8")
    body = update[update.index("void BotWorldPopulationMgr::UpdateBot("):]
    assert ("BotNativeLifeEvents::Scope const lifeScope = BotNativeLifeEvents::LifecycleScope(Cohort().Id, "
            "Cohort().AttemptId);") in body
    entry = body.index("BotNativeLifeEvents::Observe(lifeGuid, lifeScope, bot->IsAlive()")
    exit_guard = body.index("ReconcileOnScopeExit lifeEdgeObserve")
    prepare = body.index("PrepareBotUpdate(context)")
    assert entry < exit_guard < prepare
    runtime = RAID_RUNTIME.read_text(encoding="utf-8")
    assert ('",\\"resurrection_sequence\\":" << signal.ResurrectionSequence'
            ' << BotNativeLifeEvents::MemberJsonFields(guid, BotNativeLifeEvents::LifecycleScope(Cohort().Id, '
            'Cohort().AttemptId)) << "}";') in runtime
    # The caster-side resurrection acceptance observes the target around the native response.
    action = NATIVE_ACTION.read_text(encoding="utf-8")
    accept = action[action.index("BotNativeAction::CombatResAccept>)"):]
    response = accept.index("target->GetSession()->HandleResurrectResponseOpcode(response);")
    ack = accept.index("target->GetSession()->HandleMoveTeleportAck(ack);")
    before = accept.index("BotNativeLifeEvents::Observe(target->GetGUID().GetCounter(), lifeScope,")
    after = accept.index("BotNativeLifeEvents::Observe(target->GetGUID().GetCounter(), lifeScope,", response)
    assert before < response < ack < after
    # The native death edge in DealDamage's bot callback, before Unit::Kill.
    notify = NOTIFICATIONS.read_text(encoding="utf-8")
    body = notify[notify.index("void BotWorldPopulationMgr::NotifyCombatDamage("):]
    assert body.index("if (!Cohort().Active") < body.index("BotNativeLifeEvents::ObserveLethal(") \
        < body.index("if (!attacker)")
    assert "damage >= victimPlayer->GetHealth()" in body
    unit = (ROOT / "src/server/game/Entities/Unit/Unit.cpp").read_text(encoding="utf-8")
    deal = unit[unit.index("sBotWorldPopulationMgr->NotifyCombatDamage("):]
    assert deal.index("uint32(damagetype)") < deal.index("Unit::Kill(attacker, victim, durabilityLoss);")
    # The lifecycle epoch advances on a true start only: the recording-window rotation keeps it.
    rotation = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrRecordingWindow.cpp").read_text(encoding="utf-8")
    assert "ResetCombatLog()" not in rotation and "RecordRunStart();" in rotation
    combat_log = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatLog.cpp").read_text(encoding="utf-8")
    reset = combat_log[combat_log.index("void BotWorldPopulationMgr::ResetCombatLog()"):]
    reset = reset[:reset.index("\n}\n")]
    assert "BotNativeLifeEvents::BeginLifecycle(Cohort().Id);" in reset
    for name in ("BotNativeLifeEvents.h", "BotWorldPopulationMgrUpdateBot.cpp", "BotWorldPopulationMgrNativeAction.cpp",
                 "BotWorldPopulationMgrCombatNotifications.cpp", "BotWorldPopulationMgrRaidRuntime.cpp"):
        text = (ROOT / "src/server/game/Bots" / name).read_text(encoding="utf-8")
        assert "Cohort().RunId" not in text and "{ Cohort().CombatLogEpoch" not in text, name
