"""Recovery rides need death evidence (round 5, package T).

Round 4 BWD batch (/tmp/blackwing_descent_10n-r04-b1-20260926T052011Z, DVC
artifacts/cata_raid_program/round4_batch1_20260926.tar.gz), shard
blackwing_descent_10n_nefarian_c0: with no wipe and no death (wipe generation
0, alive 10) the lower-wing recovery ride engaged at bwd.nefarian.descent
(route 8/9) and held every member ("route_recovery_waiting_for_party") until
route_recovery_requires_transport:bwd.transit.lower_wing_elevator:
native_transport_timeout, 240 s later.

The level test was right: the ledge (z 41.10), the orb room (63.35), the
landing (8.51) and the Nefarian platform (7.11) all lie nearer the ride's exit
level (76.82) than its boarding level (190.16). The trigger was the "in
flight" test: any native fall counted, so the member whose Nefarian ledge drop
was in the air (it kept MOVEMENTFLAG_FALLING 0x800 in every snapshot from
then on, because the ride took it over before its landing was reported)
"needed" the lower-wing ride, whose approach then walked it around the pit.

Now a member is in flight for a ride only while that ride runs its own
approach (known to its runtime), and the boarding end counts only for a
member resurrected after a release in this attempt.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
INCLUDES = ["src/server/game", "src/common"]

# The lower-wing elevator contract, verbatim (composition node set).
ELEVATOR = (
    '{"entry": 203716, "spawn_id": 235178, "board_transport_z": 186.551, '
    '"exit_transport_z": 73.8806, "level_tolerance_yards": 0.75, '
    '"approach": {"mode": "surface_walk", "start_point": [-251.0, -224.605, 190.163]}, '
    '"board_point": [-247.349, -224.605, 190.028], '
    '"disembark_point": [-241.349, -224.605, 77.087], '
    '"exit_point": [-224.0, -224.605, 76.8211], "arrival_tolerance_yards": 1.5, '
    '"floor_tolerance_yards": 0.5, "timeout_ms": 240000}'
)


def _compile_and_run(tmp_path: Path, program: str) -> str:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    return subprocess.run([str(binary)], check=True, cwd=ROOT, capture_output=True, text=True).stdout


def _code(text: str) -> str:
    import re

    text = re.sub(r"//.*", "", text)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _source(name: str) -> str:
    return (BOTS / name).read_text(encoding="utf-8")


REPLAY = r'''
#include "Bots/BotValidationRouteNativeContract.h"
#include "Bots/BotValidationRouteNativeRecovery.h"
#include <cstdio>
#include <string>
#include <vector>

using namespace BotValidationRouteNative;
static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

static RecoveryMemberView Member(std::uint64_t guid, float z, bool released = false)
{
    RecoveryMemberView view;
    view.Guid = guid;
    view.Alive = true;
    view.OnRouteInstance = true;
    view.Released = released;
    view.Z = z;
    return view;
}

int main()
{
    Json value;
    std::vector<RecoveryTransit> rides;
    CHECK(!ParseArrayText("[{\"node_id\": \"bwd.transit.lower_wing_elevator\", \"contract\": "
        + std::string(ELEVATOR) + "}]", value));
    CHECK(!ParseRecoveryTransports(value, rides));
    TransportContract const& ride = rides[0].Transport;
    float boardZ = 0.0f, exitZ = 0.0f;
    CHECK(RecoveryLevels(ride, boardZ, exitZ));
    CHECK(boardZ > 190.16f && boardZ < 190.17f && exitZ > 76.82f && exitZ < 76.83f);

    // The level test with the real Nefarian coordinates: every place of the
    // descent lies on the ride's exit side (only the upper wing is above).
    for (float z : { 41.1044f,     // ledge / approach start (-158.8, -224.62)
                     41.3544f,     // step-off point
                     63.3548f,     // orb room (-19.8029, -220.85)
                     8.51f,        // landing on the platform
                     7.1075f,      // platform board point (-132.2132, -224.6203)
                     8.47252f,     // b6 walking the pit (-167.4, -230.6)
                     2.77129f })   // lowest point b6 reached
        CHECK(SideOf(z, boardZ, exitZ) == RecoverySide::Exit);
    for (float z : { 190.096f, 193.127f, 214.159f })   // lip, entrance, Omnotron
        CHECK(SideOf(z, boardZ, exitZ) == RecoverySide::Board);
    // The descent node's anchor (-132.2132, -224.6203, 7.1075) lies across it.
    bool const applies = RecoveryApplies(ride, 7.1075f);
    CHECK(applies);

    // Round 4 replay (wipe generation 0, alive 10, no release): nine at the
    // ledge, b6 falling (its landing never reported). Before: any native fall
    // was "in flight" for the ride -> engaged, held everyone 240 s.
    std::vector<RecoveryMemberView> party;
    for (std::uint64_t guid = 11005001; guid <= 11005010; ++guid)
        party.push_back(Member(guid, 41.1044f));
    RecoveryMemberView& b6 = party[5];                        // 11005006, Retribution
    CHECK(b6.Guid == 11005006);
    b6.Z = 8.47252f;
    RecoveryMemberView before = b6;
    before.InFlight = true;                                   // the old test
    std::vector<RecoveryMemberView> old = party;
    old[5] = before;
    CHECK(RideNeeded(old, boardZ, exitZ));
    CHECK(DecideRecoveryRide(applies, false, true, RecoveryMayEngage(old, boardZ, exitZ))
        == RecoveryStep::Engage);
    // Now: the drop is the descent's own, not this ride's (unknown to its
    // runtime), so nobody is in flight for it and nobody needs it.
    b6.InFlight = RecoveryMemberInFlight(false, false, true);
    CHECK(!b6.InFlight);
    CHECK(!RideNeeded(party, boardZ, exitZ));
    CHECK(DecideRecoveryRide(applies, false, false) == RecoveryStep::Idle);
    // Even a member back on the upper side without dying does not engage it
    // (no death evidence), whereas one resurrected after a release does.
    party[0].Z = 190.096f;
    CHECK(!RideNeeded(party, boardZ, exitZ));
    party[0].Released = true;
    CHECK(RideNeeded(party, boardZ, exitZ));
    CHECK(DecideRecoveryRide(applies, false, true, RecoveryMayEngage(party, boardZ, exitZ))
        == RecoveryStep::Engage);

    // A rider of this ride stays in flight during its own approach: a walk
    // onto the car, or a native fall while it is known to the ride.
    CHECK(RecoveryMemberInFlight(true, true, false));
    CHECK(RecoveryMemberInFlight(true, false, true));
    CHECK(!RecoveryMemberInFlight(true, false, false));
    CHECK(!RecoveryMemberInFlight(false, true, true));

    // After a wipe everyone released: the lip needs the ride as before, a
    // member aboard needs it regardless, and a released member already below
    // (resurrected at its corpse) does not.
    std::vector<RecoveryMemberView> wiped;
    for (std::uint64_t guid = 11005001; guid <= 11005010; ++guid)
        wiped.push_back(Member(guid, 190.096f, true));
    CHECK(RideNeeded(wiped, boardZ, exitZ));
    RecoveryMemberView aboard = Member(1, 120.0f);
    aboard.Aboard = true;
    CHECK(MemberNeedsRide(aboard, boardZ, exitZ));
    CHECK(!MemberNeedsRide(Member(2, 8.51f, true), boardZ, exitZ));
    return failures ? 1 : 0;
}
'''


def test_nefarian_descent_never_engages_the_lower_wing_ride_without_a_death(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, REPLAY.replace("ELEVATOR", 'R"J(' + ELEVATOR + ')J"'))


def test_runtime_reads_release_evidence_and_the_ride_s_own_flight() -> None:
    recovery = _code(_source("BotWorldPopulationMgrValidationRouteNativeRecovery.cpp"))
    views = recovery[recovery.index("std::vector<RecoveryMemberView> RecoveryViews("):]
    views = views[:views.index("return views;")]
    for marker in (
        "view.InFlight = RecoveryMemberInFlight(known,\n"
        "            known && ApproachPhaseInFlight(state->second.Approach),\n"
        "            BotValidationRouteBoardingAction::NativeFallSplineActive(bot));",
        "view.Released = member.ReleasedThisAttempt;",
    ):
        assert marker in views, marker
    header = _code(_source("BotValidationRouteNativeRecovery.h"))
    needs = header[header.index("inline bool MemberNeedsRide("):]
    needs = needs[:needs.index("inline bool RideNeeded(")]
    assert ("if (SideOf(member.Z, boardZ, exitZ) == RecoverySide::Board)\n"
            "        return member.Released;") in needs
    assert "return knownToRide && (approachInFlight || nativeFall);" in header
    runtime = _code(_source("BotWorldPopulationMgrValidationRouteNativeRuntime.h"))
    assert "bool ReleasedThisAttempt = false;" in runtime
    kernel = _code(_source("BotWorldPopulationMgrUpdateBotKernelPreparation.cpp"))
    # Legacy .botexp start leaves AttemptId 0, which every default flag equals.
    assert ("Cohort().AttemptId\n"
            "                                    && cohortState.ValidationReleasedAttemptId\n"
            "                                        == Cohort().AttemptId });") in kernel
    preparation = _code(_source("BotWorldPopulationMgrUpdateBotPreparation.cpp"))
    released = preparation.index("context.State.ValidationReleasedAttemptId = Cohort().AttemptId;")
    # The runback worldport (native corpse resurrection at the entrance)
    # clears NativeReleaseRequested before the first living tick; the proven
    # graveyard landing is the release evidence that survives until here
    # (round 4 atramedes_c0: eight releases, the return never armed).
    guard = preparation.index("if (BotValidationRouteRecoveryReturn::ReleasedResurrection(\n"
                              "                context.State.NativeReleaseRequested,\n"
                              "                context.State.NativeReleaseLandingObserved,\n"
                              "                context.State.NativeRecoveryEpisodeStartedMs != 0))")
    assert guard < released < preparation.index("context.ArmValidationRecoveryReturn();")
    assert released < preparation.index("context.State.NativeReleaseLandingObserved = false;")
    lifecycle = _code(_source("BotWorldPopulationMgrValidationLifecycle.cpp"))
    runback = lifecycle[lifecycle.index("else if (nativeValidationRunbackWorldport)"):]
    runback = runback[:runback.index("}")]
    assert "state.NativeReleaseRequested = false;" in runback
    assert "NativeReleaseLandingObserved" not in runback
    state = _code(_source("BotWorldPopulationMgrBotState.h"))
    assert "uint64 ValidationReleasedAttemptId = 0;" in state
    for name in ("BotValidationRouteNativeRecovery.h", "BotWorldPopulationMgrValidationRouteNativeRecovery.cpp",
                 "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp", "BotWorldPopulationMgrBotState.h",
                 "BotWorldPopulationMgrUpdateBotPreparation.cpp"):
        assert len(_source(name).splitlines()) < 1000, name


# ---------------------------------------------------------------------------
# Atramedes requests (.git/round5_patches/atramedes/recovery_requests.md)
# ---------------------------------------------------------------------------
ATRAMEDES_REPLAY = r"""
#include "Bots/BotValidationRouteRecoveryReturn.h"
#include <cmath>
#include <cstdio>

using namespace BotValidationRouteRecoveryReturn;
static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

static float Dist(float ax, float ay, float az, float bx, float by, float bz)
{
    return std::sqrt((ax - bx) * (ax - bx) + (ay - by) * (ay - by) + (az - bz) * (az - bz));
}

int main()
{
    // B: the release flags of one member of the round 4 wipe. Release:
    // requested. Graveyard landing: proven. Runback worldport through the
    // instance entrance (native corpse resurrection): request cleared. First
    // living tick: only the landing is left, and it arms.
    bool requested = true, landing = false;
    CHECK(ReleasedResurrection(requested, landing, true));
    landing = true;
    requested = false;                                  // ValidationLifecycle.cpp
    CHECK(ReleasedResurrection(requested, landing, true));
    CHECK(!ReleasedResurrection(requested, landing, false));   // no episode
    CHECK(!ReleasedResurrection(false, false, true));           // battle res at the corpse

    // A: the central-hall north patrol, 275 yd from the Atramedes anchor,
    // attacking the returning raid, is trash on the way; the boss room is not.
    float const patrol = Dist(-48.0f, -162.0f, 63.7f, 220.0347f, -224.3125f, 74.88777f);
    CHECK(patrol > 270.0f && patrol < 280.0f);
    CHECK(ReturnTrashAdmitted(true, true, patrol));
    CHECK(!ReturnTrashAdmitted(false, true, patrol));        // not walking back
    CHECK(!ReturnTrashAdmitted(true, false, patrol));        // not attacking the raid
    CHECK(!ReturnTrashAdmitted(true, true, 60.0f));          // the boss room stays closed
    CHECK(!ReturnTrashAdmitted(true, true, ReturnTrashMinAnchorYards));
    CHECK(ReturnTrashMinAnchorYards > HandOffYards);

    // Combat alone never pauses the no-progress clock (a released member in
    // the boss's zone-wide combat, an evading or unreachable hostile).
    auto fresh = [&]()
    {
        Memory memory;
        Arm(memory, 1, 7);
        return memory;
    };
    Input input;
    input.AttemptId = 1;
    input.RouteGeneration = 7;
    input.Eligible = true;
    input.Alive = true;
    input.InRouteInstance = true;
    input.DistanceToAnchor = patrol;
    Memory combat = fresh();
    input.NowMs = 1000;
    CHECK(Decide(combat, input).Step == Verdict::Returning);
    for (input.NowMs = 2000; input.NowMs < 1000 + NoProgressMs; input.NowMs += 1000)
        CHECK(Decide(combat, input).Step == Verdict::Returning);
    CHECK(Decide(combat, input).Step == Verdict::Unreachable);

    // Fighting admitted return trash pauses it while a gate admitted some in
    // the last 2 s, and for at most 180 s per return: an unkillable admitted
    // hostile still fails typed after 180 + 120 s.
    Memory fight = fresh();
    input.NowMs = 1000;
    CHECK(Decide(fight, input).Step == Verdict::Returning);
    std::uint64_t t = 2000;
    for (; t < 1000 + ReturnTrashPauseCapMs + NoProgressMs; t += 1000)
    {
        AdmitReturnTrash(fight, 250120, t - 500);               // admitted each tick
        input.NowMs = t;
        CHECK(Decide(fight, input).Step == Verdict::Returning);
    }
    CHECK(fight.TrashPausedMs == ReturnTrashPauseCapMs);
    AdmitReturnTrash(fight, 250120, t - 500);
    input.NowMs = t;
    CHECK(Decide(fight, input).Step == Verdict::Unreachable);

    // Admissions older than 2 s do not pause it.
    Memory stale = fresh();
    input.NowMs = 1000;
    CHECK(Decide(stale, input).Step == Verdict::Returning);
    AdmitReturnTrash(stale, 250120, 1000);
    for (t = 2000; t < 1000 + NoProgressMs; t += 1000)
    {
        input.NowMs = t;
        CHECK(Decide(stale, input).Step == Verdict::Returning);
    }
    CHECK(stale.TrashPausedMs == ReturnTrashFreshMs);
    input.NowMs = 1000 + NoProgressMs + ReturnTrashFreshMs;
    CHECK(Decide(stale, input).Step == Verdict::Unreachable);

    // A patrol straddling the 100 yd line (anchor at the origin): A at 104 yd
    // is admitted, B at 97 yd is admitted as its pack mate; a lone hostile at
    // 97 yd is not, nor a pack mate inside 85 yd (the boss room).
    Memory patrolMemory = fresh();
    patrolMemory.Returning = true;
    CHECK(ReturnTrashAdmitted(true, true, 104.0f));
    CHECK(!ReturnTrashAdmitted(true, true, 97.0f, ReturnTrashPackMate(patrolMemory, 97.0f, 3.0f, 0.0f)));
    // Tick 1: B scanned first (not admitted: left out), A admitted; the block
    // does not reject (one admitted engaged) and fights A.
    CHECK(BossTrashBlockRejects(true, 1, true, true) == false);
    AdmitReturnTrash(patrolMemory, 1, 1000, 104.0f, 0.0f, 0.0f);
    // Tick 2: B is A's pack mate and is admitted too.
    CHECK(ReturnTrashAdmitted(true, true, 97.0f, ReturnTrashPackMate(patrolMemory, 97.0f, 3.0f, 0.0f)));
    CHECK(!ReturnTrashAdmitted(true, true, 80.0f, ReturnTrashPackMate(patrolMemory, 95.0f, 0.0f, 0.0f)));
    CHECK(!ReturnTrashPackMate(patrolMemory, 60.0f, 0.0f, 0.0f));
    // Nothing admitted engaged: the block rejects (only then).
    CHECK(BossTrashBlockRejects(true, 0, false, true));
    CHECK(!BossTrashBlockRejects(true, 0, false, false));
    // Not returning: exactly as before (any engaged area target).
    CHECK(BossTrashBlockRejects(false, 2, true, false));
    CHECK(BossTrashBlockRejects(false, 2, true, true));
    CHECK(!BossTrashBlockRejects(false, 0, false, true));
    CHECK(!BossTrashBlockRejects(false, 2, false, false));

    // Admitted hostiles are remembered until the return ends.
    Memory remembered = fresh();
    CHECK(!RememberedReturnTrash(remembered, 250120));
    AdmitReturnTrash(remembered, 250120, 5000);
    AdmitReturnTrash(remembered, 250120, 6000);
    CHECK(RememberedReturnTrash(remembered, 250120) && remembered.AdmittedHostiles.size() == 1);
    CHECK(remembered.ReturnTrashAtMs == 6000);
    Input home = input;
    home.DistanceToAnchor = 20.0f;
    home.NowMs = 7000;
    CHECK(Decide(remembered, home).Step == Verdict::Arrived);
    CHECK(!RememberedReturnTrash(remembered, 250120));
    return failures ? 1 : 0;
}
"""


def test_atramedes_release_arms_and_trash_on_the_way_is_fought(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, ATRAMEDES_REPLAY)


def test_boss_node_trash_gates_admit_only_return_trash() -> None:
    adapter = _code(_source("BotWorldPopulationMgrValidationRouteReturnTrash.h"))
    for marker in ("if (!memory.Returning || !bot || !hostile)",
                   "bool admitted = RememberedReturnTrash(memory, guid) && hostile->IsAlive()\n"
                   "        && hostile->IsInCombat();",
                   "victim->GetCharmerOrOwnerPlayerOrPlayerItself()",
                   "attacked && (attacked == bot || attacked->IsInSameRaidWith(bot))",
                   "hostile->GetExactDist(memory.AnchorX, memory.AnchorY, memory.AnchorZ)",
                   "ReturnTrashPackMate(memory, hostile->GetPositionX(), hostile->GetPositionY(),",
                   "AdmitReturnTrash(memory, guid, BotWorldPopulationMgrSpellSemantics::NowMs(),\n"
                   "            hostile->GetPositionX(), hostile->GetPositionY(), hostile->GetPositionZ());"):
        assert marker in adapter, marker
    trash = _code(_source("BotWorldPopulationMgrValidationRouteTrashThreatControl.cpp"))
    # While returning, a non-admitted hostile is left out of every choice
    # (skipped before it is counted); the block rejects only when nothing
    # admitted remains. Not returning, it rejects exactly as before.
    scan = trash[trash.index("bool const returning = state.ValidationRecoveryReturn.Returning;"):]
    skip = scan.index('if (returning && Cohort().Config.ValidationRouteKind == "boss"\n'
                      "                && !BotValidationRouteRecoveryReturn::AdmitsReturnTrash(\n"
                      "                    state.ValidationRecoveryReturn, bot, creature))\n"
                      "            {\n"
                      "                if (!returnTrashRejected)\n"
                      "                    returnTrashRejected = creature;\n"
                      "                continue;\n"
                      "            }\n"
                      "            ++trashThreatControl.EngagedCount;")
    assert skip < scan.index("trashThreatControl.AreaTarget = creature;")
    assert skip < scan.index("trashThreatControl.TankOwnedTargets.push_back(creature);")
    assert skip < scan.index("trashThreatControl.HealerOwnedTargets.push_back(creature);")
    for marker in ('if (Cohort().Config.ValidationRouteKind == "boss"\n'
                   "        && BotValidationRouteRecoveryReturn::BossTrashBlockRejects(returning,\n"
                   "            trashThreatControl.EngagedCount, trashThreatControl.AreaTarget != nullptr,\n"
                   "            returnTrashRejected != nullptr))",
                   "Unit* rejected = returning ? returnTrashRejected : trashThreatControl.AreaTarget;",
                   # Return trash is raid trash: the native 1.3x rule, not the
                   # dungeon 2000 / 2.5x floor that starved raid damage.
                   "bool secureThreat = bot->GetMap() && bot->GetMap()->IsRaid()\n"
                   '                && (Cohort().Config.ValidationRouteKind != "boss" || returning)\n'
                   "                ? tankThreat > 0.0f && tankThreat >= highestPartyThreat * 1.3f"):
        assert marker in trash, marker
    focus = _code(_source("BotWorldPopulationMgrValidationRouteTankFocusAssist.cpp"))
    assert ("if (!tankFocusIsRouteTarget\n"
            "                && !BotValidationRouteRecoveryReturn::AdmitsReturnTrash(\n"
            "                    state.ValidationRecoveryReturn, bot, tankFocusTarget))") in focus
    ret = _code(_source("BotWorldPopulationMgrValidationRouteRecoveryReturn.cpp"))
    for marker in ("memory.Returning = decision.Step == Return::Verdict::Returning;",
                   "memory.AnchorX = node->NavigationAnchorX;"):
        assert marker in ret, marker
    assert "InCombat" not in _code(_source("BotValidationRouteRecoveryReturn.h"))
    assert "IsInCombat" not in ret[ret.index("bool BotWorldPopulationMgr::BotUpdateContext::ObserveValidationRecoveryReturn()"):
                                   ret.index("void BotWorldPopulationMgr::BotUpdateContext::YieldEncounterOwnershipForRecoveryReturn()")]
    for name in ("BotWorldPopulationMgrValidationRouteTrashThreatControl.cpp",
                 "BotWorldPopulationMgrValidationRouteTankFocusAssist.cpp",
                 "BotValidationRouteRecoveryReturn.h"):
        assert len(_source(name).splitlines()) < 1000, name


BELL = ('{"action": "gameobject_use", "entry": 204276, "spawn_id": 235153, "owner_role": "dps", '
        '"max_attempts": 3, "retry_interval_ms": 3000, "timeout_ms": 60000, "gather": true, '
        '"gather_radius_yards": 12.0}')
BELL_DONE = '{"kind": "boss_summoned", "entry": 41442}'
BELL_READY = '{"kind": "gameobject_selectable", "entry": 204276, "spawn_id": 235153}'

WAKE_READY = r"""
#include "Bots/BotValidationRouteNativeContract.h"
#include "Bots/BotValidationRouteNativeRecovery.h"
#include <cstdio>
#include <string>
#include <vector>

using namespace BotValidationRouteNative;
static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

static ParseError Wakes(std::string const& text, std::vector<RecoveryInteraction>& out)
{
    Json value;
    if (ParseError error = ParseArrayText(text, value))
        return error;
    return ParseRecoveryInteractions(value, out);
}

int main()
{
    std::string const row = std::string("[{\"node_id\": \"bwd.atramedes.bell\", \"interaction\": ")
        + BELL + ", \"completion\": " + DONE;
    std::vector<RecoveryInteraction> wakes;
    CHECK(!Wakes(row + ", \"ready\": " + READY + "}]", wakes));
    CHECK(wakes.size() == 1 && wakes[0].Ready.Declared);
    CHECK(wakes[0].Ready.Kind == CompletionKind::GameObjectSelectable && wakes[0].Ready.Entry == 204276);
    CHECK(!Wakes(row + "}]", wakes) && !wakes[0].Ready.Declared);    // Chimaeron: no gate
    CHECK(Wakes(row + ", \"ready\": {\"kind\": \"gameobject_selectable\", \"entry\": 204276, "
        "\"timeout_ms\": 180000}}]", wakes).Detail == "recovery_interaction_ready_timeout_unsupported");
    // Only the gameobject turning selectable gates a wake (as the builder emits).
    CHECK(Wakes(row + ", \"ready\": {\"kind\": \"creature_summoned\", \"entry\": 41442}}]", wakes).Detail
        == "recovery_interaction_ready_kind_unsupported");

    // After his intro the bell is not selectable: the settled wake never
    // rings it and waits (bounded) for the native respawn, which satisfies
    // its completion and retires the trigger.
    bool const assembled = true, ready = false;
    CHECK(DecideRecoveryWake(true, false, false, false, assembled && ready) == RecoveryWakeStep::Idle);
    CHECK(DecideRecoveryWake(true, false, false, false, assembled && true) == RecoveryWakeStep::Engage);
    RecoveryBaseline baseline;
    RuntimeScope const scope{ 1, 1, 7 };
    RetireRecoveryTrigger(baseline, scope, 0, RecoveryTrigger::Triggered, RecoveryWakeStep::Idle,
        true, false);
    CHECK(baseline.Scope == scope && baseline.TriggeredAtMs == 0);
    return failures ? 1 : 0;
}
"""


def test_atramedes_bell_wake_is_gated_on_the_bell_being_usable(tmp_path: Path) -> None:
    program = (WAKE_READY.replace("BELL + ", 'std::string(R"J(' + BELL + ')J") + ')
               .replace("+ DONE;", '+ R"J(' + BELL_DONE + ')J";')
               .replace("+ READY +", '+ R"J(' + BELL_READY + ')J" +'))
    _compile_and_run(tmp_path, program)
    recovery = _code(_source("BotWorldPopulationMgrValidationRouteNativeRecovery.cpp"))
    for marker in ("bool const ready = !wake.Ready.Declared || (evaluator && Facts::EvaluateCompletion(\n"
                   "            wake.Ready, evaluator, input.Members, election.Owner, wake.ReadyMemory).Satisfied);",
                   "&& (!assembled || !ready);",
                   'RecoveryWakeHolder{ 0, "target_not_ready" }',
                   "satisfied, assembled && ready);"):
        assert marker in recovery, marker


def test_builder_gates_the_bell_wake_on_bell_ready_only() -> None:
    import json
    import sys

    sys.path.insert(0, str(ROOT))
    from tools.bot_ml import build_validation_scenario_manifests as builder

    config = json.loads((ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text())
    rows = list(config.get("scenarios") or []) + list(config.get("diagnostic_scenarios") or [])
    scenarios = {str(row["id"]): row for row in rows if isinstance(row, dict) and row.get("id")}
    checked = 0
    for scenario_id, scenario in scenarios.items():
        parent = scenarios.get(str(scenario.get("diagnostic_parent_scenario_id") or ""), {})
        wakes = builder.recovery_wakes(scenario.get("route") or [], parent.get("route") or [])
        for node_id in {str(step.get("node_id")) for step in scenario.get("route") or []}:
            for wake in wakes.get(node_id) or []:
                if wake["node_id"] == "bwd.atramedes.bell":
                    assert wake["ready"] == {"kind": "gameobject_selectable", "entry": 204276,
                                             "spawn_id": 235153}, (scenario_id, node_id)
                    checked += 1
                else:
                    assert "ready" not in wake, (scenario_id, node_id)
    assert checked >= 6
    # Only a wait row for the interaction's gameobject to become selectable
    # gates the wake; any other wait row does not.
    route = [
        {"node_id": "x.wait", "kind": "interaction",
         "completion_contract": {"kind": "creature_summoned", "entry": 1, "timeout_ms": 1000}},
        {"node_id": "x.use", "kind": "interaction",
         "interaction_contract": {"action": "gameobject_use", "entry": 2},
         "completion_contract": {"kind": "boss_summoned", "entry": 3}},
        {"node_id": "x.boss", "kind": "boss"},
    ]
    assert "ready" not in builder.recovery_wakes(route)["x.boss"][0]
    route[0]["completion_contract"] = {"kind": "gameobject_selectable", "entry": 2, "timeout_ms": 1000}
    assert builder.recovery_wakes(route)["x.boss"][0]["ready"] == {"kind": "gameobject_selectable", "entry": 2}
    types = _source("BotValidationRouteNativeTypes.h")
    assert "CompletionContract Ready; CompletionMemory ReadyMemory;" in types
    assert len(types.splitlines()) < 300
