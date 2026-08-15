import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_production_drudge_geometry_transition_replays_charge_edges_and_pull_order(tmp_path):
    source = tmp_path / "drudge_geometry_replay.cpp"
    binary = tmp_path / "drudge_geometry_replay"
    source.write_text(
        r'''
#include "Bots/BotRaidDrudgeGeometryState.h"
#include <cassert>

using namespace BotRaidDrudgeGeometry;

int main()
{
    assert(SelectMemberRecoveryAction(true, false, true)
        == MemberRecoveryAction::RecoverFormation);
    assert(SelectMemberRecoveryAction(true, true, true)
        == MemberRecoveryAction::PreferFriendlySupport);
    assert(SelectMemberRecoveryAction(false, false, true)
        == MemberRecoveryAction::PreferFriendlySupport);
    assert(SelectMemberRecoveryAction(false, false, false)
        == MemberRecoveryAction::Continue);

    assert(SelectMinimumDistanceOwner(false, false)
        == MinimumDistanceOwner::GenericRouteSafety);
    assert(SelectMinimumDistanceOwner(false, true)
        == MinimumDistanceOwner::GenericRouteSafety);
    assert(SelectMinimumDistanceOwner(true, false)
        == MinimumDistanceOwner::GenericRouteSafety);
    assert(SelectMinimumDistanceOwner(true, true)
        == MinimumDistanceOwner::LandedRushRecovery);

    std::vector<Point2d> safeRecoveryPath{
        {-11.0f, 0.0f}, {-9.0f, 1.0f}, {-8.0f, 2.0f}
    };
    assert(RecoveryPathPreservesTankSeparation(
        safeRecoveryPath, 0.0f, 0.0f, 1.0f, 0.0f, -1.0f, 8.0f, 15.0f));
    std::vector<Point2d> crossedRecoveryPath = safeRecoveryPath;
    crossedRecoveryPath.push_back({-7.0f, 2.0f});
    assert(!RecoveryPathPreservesTankSeparation(
        crossedRecoveryPath, 0.0f, 0.0f, 1.0f, 0.0f, -1.0f, 8.0f, 15.0f));
    assert(!RecoveryPathPreservesTankSeparation(
        safeRecoveryPath, 0.0f, 0.0f, 1.0f, 0.0f, -1.0f, 7.0f, 15.0f));

    Scope scope{7, 0, 3, 669, 14, 250140, 250141};
    State state;

    // Exact prep is not permission to pull from the prep tank points. Both
    // tanks must first establish native-path proofs at the combat anchors.
    Input input;
    input.Identity = scope;
    input.ExactPrepullStaged = true;
    input.ChargeQueueIdle = true;
    input.SourcesAlive = true;
    input.SourcesSeparated = true;
    input.SourcesOnFrozenLanes = true;
    input.TanksOnFrozenLanes = true;
    input.BoundTankSourceGeometrySafe = true;
    input.NativeMeleeStopBounded = true;
    Result result = Advance(state, input);
    assert(result.ScopeReset);
    assert(result.NextDecision == Decision::StageCombatTanks);
    assert(!result.TankMovementAllowed);
    assert(!result.NativeOwnershipAllowed);
    assert(!result.NativeEngagementAllowed);

    // A single tank proof is intentionally not representable as movement
    // authority. Production freezes both exact proofs before setting this
    // shared input on a subsequent tick.
    input.BothCombatTankPathsProven = true;
    result = Advance(result.Next, input);
    assert(result.NextDecision == Decision::StageCombatTanks);
    assert(result.TankMovementAllowed);
    assert(!result.NativeOwnershipAllowed);
    assert(!result.NativeEngagementAllowed);

    // If native combat starts out of order, recovery still stages the same
    // declared anchors and never grants taunt/pull authority early.
    input.SourceCombatStarted = true;
    result = Advance(result.Next, input);
    assert(result.NextDecision == Decision::RecoverCombatAtTankAnchors);
    assert(result.SupportAllowed);
    assert(result.TankMovementAllowed);
    assert(!result.NativeOwnershipAllowed);
    assert(!result.NativeEngagementAllowed);

    input.BothCombatTankAnchorsSafe = true;
    result = Advance(result.Next, input);
    assert(result.NextDecision == Decision::AllowNativeEngagement);
    assert(result.SupportAllowed);
    assert(result.NativeOwnershipAllowed);
    assert(result.NativeEngagementAllowed);

    // Initial source separation is produced by native threat ownership. Once
    // both sealed tank anchors are safe, a real tank taunt is allowed while
    // ordinary offense and threat seeding remain held until the sources have
    // actually followed their tanks far enough apart.
    Input ownership = input;
    ownership.SourcesSeparated = false;
    ownership.BoundTankSourceGeometrySafe = false;
    Result ownershipOnly = Advance(result.Next, ownership);
    assert(ownershipOnly.NativeOwnershipAllowed);
    assert(!ownershipOnly.NativeEngagementAllowed);

    // An in-flight Rush still denies ownership. Once that exact authoritative
    // observation lands, only the assigned tanks regain native taunt
    // authority so they can split the sources. Ordinary engagement/offense
    // remains denied until the queue is retired by exact-roster reseparation.
    Input unsafe = input;
    unsafe.ChargeQueueIdle = false;
    unsafe.ChargePending = true;
    Result pending = Advance(result.Next, unsafe);
    assert(!pending.NativeOwnershipAllowed);
    assert(!pending.NativeEngagementAllowed);
    unsafe.ChargeLanded = true;
    Result landed = Advance(result.Next, unsafe);
    assert(landed.NativeOwnershipAllowed);
    assert(!landed.NativeEngagementAllowed);
    unsafe.BothCombatTankAnchorsSafe = false;
    Result displacedTank = Advance(result.Next, unsafe);
    assert(displacedTank.NativeOwnershipAllowed);
    unsafe.TanksOnFrozenLanes = false;
    Result crossedRecoveryTank = Advance(result.Next, unsafe);
    assert(!crossedRecoveryTank.NativeOwnershipAllowed);
    unsafe = input;
    unsafe.SourcesSeparated = false;
    Result tooClose = Advance(result.Next, unsafe);
    assert(!tooClose.NativeEngagementAllowed);
    unsafe = input;
    unsafe.SourcesOnFrozenLanes = false;
    Result crossed = Advance(result.Next, unsafe);
    assert(crossed.NativeOwnershipAllowed);
    assert(!crossed.NativeEngagementAllowed);
    unsafe = input;
    unsafe.SourcesAlive = false;
    Result deadSource = Advance(result.Next, unsafe);
    assert(!deadSource.NativeOwnershipAllowed);
    assert(!deadSource.NativeEngagementAllowed);
    unsafe = input;
    unsafe.TanksOnFrozenLanes = false;
    Result crossedTanks = Advance(result.Next, unsafe);
    assert(!crossedTanks.NativeOwnershipAllowed);
    assert(!crossedTanks.NativeEngagementAllowed);
    unsafe = input;
    unsafe.BoundTankSourceGeometrySafe = false;
    Result wrongTankGeometry = Advance(result.Next, unsafe);
    assert(wrongTankGeometry.NativeOwnershipAllowed);
    assert(!wrongTankGeometry.NativeEngagementAllowed);
    unsafe = input;
    unsafe.NativeMeleeStopBounded = false;
    Result oversizedNativeReach = Advance(result.Next, unsafe);
    assert(!oversizedNativeReach.NativeOwnershipAllowed);
    assert(!oversizedNativeReach.NativeEngagementAllowed);

    // A native Rush invalidates the pre-Rush anchor proof once. Repeated bot
    // ticks for the same pending observation preserve a successful reproof.
    input.ChargePending = true;
    input.ChargeSequence = 41;
    result.Next.PriorPathProofAvailable = true;
    result = Advance(result.Next, input);
    assert(result.InvalidateAnchor);
    assert(result.Next.PriorPathProofAvailable);

    // The Rush did not move this tank/member. The exact scoped candidate is
    // unchanged and every dynamic predicate still passes, so production can
    // reactivate the prior strict proof without asking PathGenerator for a
    // zero-length path.
    Input proof = input;
    proof.EvaluatePriorPathProof = true;
    proof.PriorProofScopeMatches = true;
    proof.PriorProofCandidateMatches = true;
    proof.MemberAtProvenAnchor = true;
    proof.DynamicLaneSafe = true;
    proof.DynamicSourceSafe = true;
    proof.DynamicSpacingSafe = true;
    result = Advance(result.Next, proof);
    assert(result.ReactivatePriorPathProof);
    assert(result.Next.PriorPathProofAvailable);

    State reproved = result.Next;
    for (unsigned tick = 0; tick < 100; ++tick)
    {
        Result repeated = Advance(reproved, input);
        assert(!repeated.InvalidateAnchor);
        assert(repeated.Next.LastChargeSequenceObserved == 41);
        reproved = repeated.Next;
    }

    // Displacement cannot borrow the old path proof. A subsequent selector
    // must run a fresh strict path from the bot's new polygon.
    Input moved = proof;
    moved.MemberAtProvenAnchor = false;
    Result displaced = Advance(reproved, moved);
    assert(!displaced.ReactivatePriorPathProof);
    assert(!displaced.Next.PriorPathProofAvailable);

    // Candidate identity changes (including prep -> combat tank anchors) also
    // discard the proof instead of blessing a different point.
    Input changed = proof;
    changed.PriorProofCandidateMatches = false;
    Result candidateChanged = Advance(reproved, changed);
    assert(!candidateChanged.ReactivatePriorPathProof);
    assert(!candidateChanged.Next.PriorPathProofAvailable);

    // A genuinely newer native observation owns a new invalidation edge.
    input.ChargeSequence = 42;
    result = Advance(reproved, input);
    assert(result.InvalidateAnchor);
    Result duplicate = Advance(result.Next, input);
    assert(!duplicate.InvalidateAnchor);

    // Wipe/route scope changes cannot inherit the prior sequence cursor.
    input.Identity = Scope{7, 1, 3, 669, 14, 250140, 250141};
    result = Advance(duplicate.Next, input);
    assert(result.ScopeReset);
    assert(result.InvalidateAnchor);
    assert(result.Next.LastChargeSequenceObserved == 42);

    // Equal attempt/wipe/route and equal coordinates are insufficient across
    // instance boundaries: the durable native-path proof is scoped to the
    // exact live map instance and frozen source identities.
    State instanceProof = reproved;
    Input otherInstance = proof;
    otherInstance.Identity = Scope{7, 0, 3, 669, 15, 250140, 250141};
    Result instanceChanged = Advance(instanceProof, otherInstance);
    assert(instanceChanged.ScopeReset);
    assert(!instanceChanged.ReactivatePriorPathProof);
    assert(!instanceChanged.Next.PriorPathProofAvailable);

    Input noInstance = proof;
    noInstance.Identity = Scope{7, 0, 3, 669, 0, 250140, 250141};
    Result invalidInstance = Advance(instanceProof, noInstance);
    assert(!invalidInstance.ReactivatePriorPathProof);
    assert(!invalidInstance.NativeEngagementAllowed);

    Input replacedSource = proof;
    replacedSource.Identity = Scope{7, 0, 3, 669, 14, 250140, 350141};
    Result sourceChanged = Advance(instanceProof, replacedSource);
    assert(sourceChanged.ScopeReset);
    assert(!sourceChanged.ReactivatePriorPathProof);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_worldserver_uses_geometry_transition_for_edge_and_combat_anchor_barrier():
    implementation = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    lane = implementation[
        implementation.index("auto tryValidationRouteDrudgeChargeLanes") :
        implementation.index("if (tryValidationRouteDrudgeChargeLanes())")
    ]

    assert '#include "Bots/BotRaidDrudgeGeometryState.h"' in implementation
    assert "rushGeometry.InvalidateAnchor" in lane
    assert "proofTransition.ReactivatePriorPathProof" in lane
    assert "ValidationRouteDrudgeAnchorPathProven" in lane
    assert "MemberAtProvenAnchor" in lane
    assert "DynamicSpacingSafe" in lane
    assert "LastValidationRouteDrudgeChargeGenerationObserved" in lane
    assert (
        "LastValidationRouteDrudgeChargeGenerationHandled != chargeObservation->Sequence"
        not in lane
    )
    assert "combatTankStagingActive()" in lane
    assert "exactCombatTankAnchorsSafe" in lane
    assert "!tankStage.NativeEngagementAllowed" in lane
    assert "tankStageInput.ChargeQueueIdle" in lane
    assert "tankStageInput.ChargeLanded = nativeChargePending" in lane
    assert "landedChargeRecovery" in lane
    assert "drudge_lane_native_taunt_approach" in lane
    assert 'candidate.RejectReason == "out_of_range"' in lane
    assert "auto strictTankRecoveryPath" in lane
    assert "path.GetActualEndPosition()" in lane
    assert "RecoveryPathPreservesTankSeparation" in lane
    assert "ValidationRouteSplitMinimumSeparationYards" in lane
    assert "* 0.5f" in lane
    assert lane.count("strictTankRecoveryPath(") == 2
    return_guard = lane.index("!assignedTank || !nativeChargePending")
    return_move = lane.index("moved = MoveBotToPoint", return_guard)
    assert return_guard < lane.index("strictTankRecoveryPath(", return_guard) < return_move
    assert "tankStageInput.SourcesAlive" in lane
    assert "tankStageInput.SourcesSeparated" in lane
    assert "tankStageInput.SourcesOnFrozenLanes" in lane
    assert "tankStageInput.TanksOnFrozenLanes" in lane
    assert "tankStageInput.BoundTankSourceGeometrySafe" in lane
    assert "tankStageInput.NativeMeleeStopBounded" in lane
    assert "GetMeleeRange" in lane
    assert "tankStage.SupportAllowed" in lane
    assert "tryRouteGroupHeal(bot, laneSource, false)" in lane
    assert "SelectMemberRecoveryAction" in lane
    assert "if (tryValidationRouteMinimumDistance(true))" in lane
    assert "drudge_anchor_source_unsafe" in lane
    assert "drudge_anchor_spacing_unsafe" in lane
    assert "drudge_anchor_native_path_rejected:path_type=" in lane
    assert "drudge_anchor_native_end_rejected:end2d=" in lane
    assert "bot->GetInstanceId() != 0" in lane
    assert "ValidationRouteDrudgeAnchorSource0Identity" in lane

    barrier = lane.index("!tankStage.NativeEngagementAllowed || formationRequiredMutable")
    exact_reseparation = lane.index("if (nativeChargePending && exactRosterReSeparated())")
    specialized_escape = lane.index("if (tryValidationRouteMinimumDistance(true))")
    recovery_choice = lane.index("SelectMemberRecoveryAction", barrier)
    recovery_move = lane.index("tryFormationRecovery();", recovery_choice)
    support = lane.index("drudge_staging_support")
    first_taunt = lane.index("drudge_lane_native_taunt")
    assert exact_reseparation < specialized_escape < barrier
    assert barrier < recovery_choice < recovery_move < support
    assert first_taunt < barrier
    assert "assignedTank && tankStage.NativeOwnershipAllowed" in lane[first_taunt - 1200:first_taunt]

    source_unsafe = lane.index('"drudge_anchor_source_unsafe"')
    cooldown = lane.index("nowMs < state.ValidationRouteDrudgeAnchorSearchCooldownUntilMs")
    strict_path = lane.index("if (!strictNativePath", cooldown)
    assert source_unsafe < cooldown < strict_path

    minimum = implementation[
        implementation.index("auto drudgeLandedRushPending") :
        implementation.index("auto tryValidationRouteDrudgeChargeLanes")
    ]
    assert "SelectMinimumDistanceOwner" in minimum
    assert "MinimumDistanceOwner::LandedRushRecovery" in minimum


def test_future_encounter_contamination_is_attempt_terminal_not_a_transient_hold():
    implementation = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    start = implementation.index("Creature* prematureNextEncounter = nullptr;")
    end = implementation.index("auto validationPartyHasActiveCombat", start)
    hold = implementation[start:end]

    latch = hold.index(
        'Cohort().ValidationAttemptFailureReason =\n'
        '                "validation_route_future_encounter_contamination";'
    )
    event = hold.index(
        'RecordEvent(state, bot, "validation_route_future_encounter_contamination"'
    )
    assert latch < event < hold.index("return true;", event)
    assert "ValidationAttemptFailureAttemptId = Cohort().AttemptId" in hold
    assert "ValidationAttemptFailureRouteGeneration" in hold


def test_second_same_source_rush_terminalizes_an_unclosed_native_reseparation():
    implementation = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    start = implementation.index(
        "uint64 BotWorldPopulationMgr::NotifyNativeCreatureSpellStarted"
    )
    end = implementation.index(
        "void BotWorldPopulationMgr::NotifyNativeCreatureSpellLanded", start
    )
    callback = implementation[start:end]
    assert "observation.SourceSpawnId == sourceSpawnId" in callback
    assert "observation.Landed && !observation.ReseparationRecorded" in callback
    latch = callback.index(
        'Cohort().ValidationAttemptFailureReason =\n'
        '            "drudge_reseparation_deadline_missed";'
    )
    append = callback.index(
        "Party().ValidationRouteDrudgeChargeObservations.push_back"
    )
    assert latch < append
