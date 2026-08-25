import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_production_drudge_geometry_transition_replays_charge_edges_and_pull_order(tmp_path):
    source = tmp_path / "drudge_geometry_replay.cpp"
    binary = tmp_path / "drudge_geometry_replay"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeNativeRushState.h"
#include <cassert>
#include <cmath>

using namespace BotRaidDrudgeGeometry;

int main()
{
    // Exact 855 live counterexample: the seeded mage was only 7.45609 yards
    // away while same-lane DPS 30010 was 46.7208 yards away, and tank threat
    // (38105) was below the 2.5x headroom over the seed (85968). Production
    // must keep ordinary offense suppressed without changing native target or
    // threat state.
    BotRaidDrudgeNativeRush::SourceInput live855;
    live855.ExactTankVictim = true;
    live855.IntendedSeedPresent = true;
    live855.FarthestIsIntendedSeed = false;
    live855.TankThreat = 38105.0f;
    live855.HighestOtherThreat = 85968.0f;
    live855.SeedDistance = 7.45609f;
    live855.SecondFarthestDistance = 36.023f;
    live855.ThreatHeadroomMultiplier = 2.5f;
    live855.FarthestDistanceMargin = 2.0f;
    live855.FarthestGuid = 30010;
    auto rejected855 = BotRaidDrudgeNativeRush::Evaluate(live855);
    assert(!rejected855.TankThreatSecure);
    assert(!rejected855.SeedIsUniqueFarthest);
    assert(!rejected855.Ready);

    BotRaidDrudgeNativeRush::SourceInput readyRush = live855;
    readyRush.FarthestIsIntendedSeed = true;
    readyRush.TankThreat = 250000.0f;
    readyRush.HighestOtherThreat = 90000.0f;
    readyRush.SeedDistance = 34.0f;
    readyRush.SecondFarthestDistance = 31.5f;
    readyRush.FarthestGuid = 30006;
    auto ready = BotRaidDrudgeNativeRush::Evaluate(readyRush);
    assert(ready.TankThreatSecure);
    assert(ready.SeedIsUniqueFarthest);
    assert(ready.Ready);
    // Exact dc381 live counterexample: a one-tick secure snapshot was followed
    // by periodic seed threat, ownership loss, and a bad native target.
    // The assigned tank must sustain ordinary threat until the first Rush,
    // and every later Rush must still retain the intended opposite tank as
    // unique farthest.
    assert(BotRaidDrudgeNativeRush::ShouldBuildTankThreat(false, ready));
    assert(!BotRaidDrudgeNativeRush::ShouldBuildTankThreat(true, ready));
    assert(BotRaidDrudgeNativeRush::ShouldBuildTankThreat(true, rejected855));
    assert(BotRaidDrudgeNativeRush::AuthorityReady(false, ready));
    assert(BotRaidDrudgeNativeRush::AuthorityReady(true, ready));
    readyRush.SeedDistance = 33.0f;
    auto recoveredRoster = BotRaidDrudgeNativeRush::Evaluate(readyRush);
    assert(!recoveredRoster.SeedIsUniqueFarthest);
    assert(!BotRaidDrudgeNativeRush::AuthorityReady(false, recoveredRoster));
    assert(!BotRaidDrudgeNativeRush::AuthorityReady(true, recoveredRoster));
    assert(!BotRaidDrudgeNativeRush::AuthorityReady(true, rejected855));

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
    assert(!ExactDrudgeLaneOwnsGroupMovement(false, true));
    assert(!ExactDrudgeLaneOwnsGroupMovement(true, false));
    assert(ExactDrudgeLaneOwnsGroupMovement(true, true));
    assert(!DynamicGroupRecoveryActive(false, true, true));
    assert(!DynamicGroupRecoveryActive(true, false, false));
    assert(DynamicGroupRecoveryActive(true, true, false));
    assert(DynamicGroupRecoveryActive(true, false, true));
    assert(ShouldInvalidateAnchorAfterPathRejection(
        "route_destination_path_floor_gap",
        "route_destination_path_floor_gap"));
    assert(ShouldInvalidateAnchorAfterPathRejection(
        "drudge_anchor_path_floor_gap", "drudge_anchor_path_floor_gap"));
    assert(!ShouldInvalidateAnchorAfterPathRejection(
        "route_destination_path_floor_gap", "higher_priority_movement_active"));
    assert(!ShouldInvalidateAnchorAfterPathRejection(
        "route_destination_unreachable", "route_destination_unreachable"));

    // Prepull staging and post-Rush reseparation share the same strict live
    // source, lane, and peer-spacing contract.  Only the prepull path adds
    // the exact cached-anchor arrival proof.
    assert(DynamicGroupPositionSafe(true, true, true, true));
    assert(!DynamicGroupPositionSafe(false, true, true, true));
    assert(!DynamicGroupPositionSafe(true, false, true, true));
    assert(!DynamicGroupPositionSafe(true, true, false, true));
    assert(!DynamicGroupPositionSafe(true, true, true, false));

    // Run11's tank-2 recovery point is intentionally 23.8237 yards from its
    // source, while the declared navigation/combat point is exactly 15 yards.
    // The recovery leg must complete first, and the native return plus the
    // existing roster contract must all be present before offense can reopen.
    constexpr float sourceX = -307.913f;
    constexpr float sourceY = -49.5694f;
    constexpr float recoveryX = -321.5f;
    constexpr float recoveryY = -30.0f;
    constexpr float combatX = -322.858002f;
    constexpr float combatY = -48.286201f;
    assert(std::hypot(recoveryX - sourceX, recoveryY - sourceY) > 15.0f);
    assert(std::hypot(combatX - sourceX, combatY - sourceY) <= 15.01f);
    assert(!LandedRushRecoveryComplete(true, false, true, true, true));
    assert(!LandedRushRecoveryComplete(true, true, false, true, true));
    assert(!LandedRushRecoveryComplete(true, true, true, false, true));
    assert(!LandedRushRecoveryComplete(true, true, true, true, false));
    assert(LandedRushRecoveryComplete(true, true, true, true, true));

    // The first tank reaching its recovery anchor must not open the combat
    // return for itself.  The selector may switch both tanks only after the
    // exact scoped pair has reached recovery.
    assert(!RecoveryTankReturnBarrierOpen(true, false));
    assert(RecoveryTankReturnBarrierOpen(true, true));
    assert(RecoveryTankReturnBarrierOpen(false, false));
    assert(RecoveryTankReturnBarrierOpen(false, true));
    bool recoveryBarrierOpened = false;
    assert(!AdvanceRecoveryTankReturnBarrier(recoveryBarrierOpened, true, false));
    assert(AdvanceRecoveryTankReturnBarrier(recoveryBarrierOpened, true, true));
    // The first tank may now begin its combat return.  Its state change makes
    // a fresh all-recovery observation false, but the same landed observation
    // must keep the pair barrier open for the second tank's next tick.
    assert(AdvanceRecoveryTankReturnBarrier(recoveryBarrierOpened, true, false));
    assert(!LandedRushRecoveryComplete(true, recoveryBarrierOpened, true, false, true));
    assert(!LandedRushRecoveryComplete(true, recoveryBarrierOpened, true, true, false));
    assert(LandedRushRecoveryComplete(true, recoveryBarrierOpened, true, true, true));

    // A landed Rush can occupy the sealed anchor for many ticks. Dynamic
    // source/spacing blocks never arm or preserve the expensive path retry;
    // the first safe edge must attempt the native path immediately.
    AnchorPathSearchDecision sourceBlocked = SelectAnchorPathSearch(
        9000, 5000, false, true);
    assert(sourceBlocked.SourceBlocked);
    assert(!sourceBlocked.SpacingBlocked);
    assert(!sourceBlocked.NativePathSearchDue);
    assert(sourceBlocked.RetryAfterMs == 0);
    AnchorPathSearchDecision repeatedSourceBlock = SelectAnchorPathSearch(
        sourceBlocked.RetryAfterMs, 6000, false, true);
    assert(repeatedSourceBlock.RetryAfterMs == 0);
    assert(!repeatedSourceBlock.NativePathSearchDue);
    AnchorPathSearchDecision spacingBlocked = SelectAnchorPathSearch(
        9000, 6000, true, false);
    assert(!spacingBlocked.SourceBlocked);
    assert(spacingBlocked.SpacingBlocked);
    assert(spacingBlocked.RetryAfterMs == 0);
    AnchorPathSearchDecision firstSafeEdge = SelectAnchorPathSearch(
        repeatedSourceBlock.RetryAfterMs, 6001, true, true);
    assert(!firstSafeEdge.SourceBlocked);
    assert(!firstSafeEdge.SpacingBlocked);
    assert(firstSafeEdge.NativePathSearchDue);
    AnchorPathSearchDecision realPathCooldown = SelectAnchorPathSearch(
        11000, 6001, true, true);
    assert(!realPathCooldown.NativePathSearchDue);
    assert(realPathCooldown.RetryAfterMs == 11000);

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

    // An in-flight observation is not yet a displacement edge. It must keep
    // the queue blocked without invalidating the prepull anchor proof.
    input.ChargePending = true;
    input.ChargeQueueIdle = false;
    input.ChargeLanded = false;
    input.ChargeSequence = 41;
    result.Next.PriorPathProofAvailable = true;
    Result awaitingLanding = Advance(result.Next, input);
    assert(!awaitingLanding.InvalidateAnchor);
    assert(awaitingLanding.Next.LastChargeSequenceObserved == 0);
    assert(awaitingLanding.Next.PriorPathProofAvailable);

    // The first landed tick owns the one-shot invalidation edge. Repeated bot
    // ticks for the same landed observation must not invalidate it again.
    input.ChargeLanded = true;
    result = Advance(awaitingLanding.Next, input);
    assert(result.InvalidateAnchor);
    assert(result.Next.LastChargeSequenceObserved == 41);
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


def test_drudge_rush_releases_only_one_matching_mechanic_lease(tmp_path):
    source = tmp_path / "drudge_movement_lease_replay.cpp"
    binary = tmp_path / "drudge_movement_lease_replay"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeMovementLease.h"
#include <cassert>
#include <initializer_list>

int main()
{
    using namespace BotMovementArbitration;
    using BotRaidDrudgeMovement::ReleaseInvalidatedMechanicLease;
    Scope scope{7, 2, 9, 669, 41};
    Lease mechanic{Owner::Mechanic, Priority::Mechanic, 1300, scope,
        1.0f, 2.0f, 3.0f};
    assert(ReleaseInvalidatedMechanicLease(mechanic, scope));
    assert(mechanic.MovementOwner == Owner::None);
    assert(!ReleaseInvalidatedMechanicLease(mechanic, scope));

    for (auto const owner : {Owner::Route, Owner::CombatRange,
             Owner::Hazard, Owner::Recovery})
    {
        Lease otherOwner{owner, Priority::Recovery, 1300, scope,
            4.0f, 5.0f, 6.0f};
        assert(!ReleaseInvalidatedMechanicLease(otherOwner, scope));
        assert(otherOwner.MovementOwner == owner);
    }

    Lease elevatedMechanic{Owner::Mechanic, Priority::Recovery, 1300, scope,
        4.0f, 5.0f, 6.0f};
    assert(!ReleaseInvalidatedMechanicLease(elevatedMechanic, scope));
    assert(elevatedMechanic.MovementOwner == Owner::Mechanic);

    Scope differentScope = scope;
    differentScope.RouteGeneration++;
    Lease different{Owner::Mechanic, Priority::Mechanic, 1300,
        differentScope, 7.0f, 8.0f, 9.0f};
    assert(!ReleaseInvalidatedMechanicLease(different, scope));
    assert(different.MovementOwner == Owner::Mechanic);
    assert(different.MovementScope.RouteGeneration
        == differentScope.RouteGeneration);
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


def test_native_ownership_waits_for_both_combat_tanks_to_reach_their_anchors():
    production = (
        ROOT
        / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
        "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
    ).read_text(encoding="utf-8")
    binding = production.split("ExactCombatTankAnchorsSafe = [this]", 1)[1]
    binding = binding.split("};", 1)[0]
    assert "return ComputeExactCombatTankAnchorsReached();" in binding
    assert "ComputeExactCombatTankPathsProven" not in binding


def test_worldserver_uses_geometry_transition_for_edge_and_combat_anchor_barrier():
    implementation = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    geometry = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp").read_text(
        encoding="utf-8"
    )
    recovery = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeRecovery.cpp").read_text(
        encoding="utf-8"
    )
    lanes = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp").read_text(
        encoding="utf-8"
    )
    actions = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeActions.cpp").read_text(
        encoding="utf-8"
    )
    seed = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeSeed.cpp").read_text(
        encoding="utf-8"
    )

    assert "TryValidationRouteDrudgeMinimumDistance" in implementation
    assert "TryValidationRouteDrudgeChargeLanes" in implementation
    assert "SelectMinimumDistanceOwner" in geometry
    assert "MinimumDistanceOwner::LandedRushRecovery" in geometry
    assert "RecoveryPathPreservesTankSeparation" in recovery
    assert "ValidationRouteDrudgeAnchorSource0Identity" in geometry
    assert "ExactRosterPrepullStaged" in geometry
    assert "ValidationRouteSplitSourceGuids" in lanes
    assert "ValidationRouteSplitLaneARosterSlots" in lanes
    assert "SetAllOffenseSuppressed" in actions
    assert "SelectMemberRecoveryAction" in actions
    assert "RecoveryAnchorReachedFor" in geometry
    assert "RecoveryTankReturnBarrierOpen" in actions
    assert "ExactCombatTankAnchorsReached" in actions
    assert "LandedRushRecoveryComplete" in actions
    assert "drudge_tank_recovery_anchor_reached" in actions
    assert "drudge_tank_combat_anchor_return_started" in actions
    assert '"drudge_native_charge_reseparation_wait"' in actions
    assert actions.index("LandedRushRecoveryComplete") < actions.index(
        '"drudge_native_charge_reseparation_complete"'
    )
    assert "drudge_lane_native_taunt" in actions
    assert "drudge_pre_first_rush_threat_seed" in seed
    assert "drudge_native_charge_reseparation_complete" in actions
    assert "if (TryMinimumDistance(true))" not in lanes
    assert '&& Role != "tank"' in actions


def test_landed_rush_recovery_latches_the_scoped_two_tank_return_barrier():
    geometry = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp").read_text(
        encoding="utf-8"
    )
    recovery = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeRecovery.cpp").read_text(
        encoding="utf-8"
    )
    lanes = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp").read_text(
        encoding="utf-8"
    )
    route_state = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrRouteState.h").read_text(
        encoding="utf-8"
    )

    assert "RecoveryTankReturnBarrierOpen()" in geometry
    assert "RecoveryTankAnchorPending(slot)" in geometry
    assert "AdvanceRecoveryTankReturnBarrier" in recovery
    assert "RecoveryTankReturnBarrierOpened" in route_state
    assert "RecoveryTankReturnBarrierOpen()" in lanes

    actions = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeActions.cpp").read_text(
        encoding="utf-8"
    )
    assert "RecoveryFormationActive && RecoveryTankReturnBarrierOpen()" in actions
    assert "recoveryAnchorsReachedBeforeTick" in actions


def test_post_rush_recovery_replays_combat_anchor_transition_with_exact_xyz():
    geometry_path = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
    lanes_path = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp"
    geometry = geometry_path.read_text(encoding="utf-8")
    lanes = lanes_path.read_text(encoding="utf-8")
    route = next(
        json.loads(line)
        for line in (ROOT / "dataset/validation_scenarios/validation_routes.jsonl")
        .read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("route_node_id") == "bwd.magmaw.drudges"
    )
    anchors = {
        key: {
            row["roster_slot"]: (row["x"], row["y"], row["z"])
            for row in route[key]
        }
        for key in (
            "split_tank_navigation_anchors",
            "split_tank_recovery_anchors",
            "split_tank_combat_anchors",
        )
    }

    # Run15's mixed-Z trace was the signature of selecting the recovery X/Y
    # while retaining a later anchor's Z.  Replay the three legal phases from
    # the sealed route data, then require the production selector to contain
    # the same state transition.
    def expected_anchor(slot, landed, recovery_reached):
        if not landed:
            return anchors["split_tank_navigation_anchors"][slot]
        if not recovery_reached:
            return anchors["split_tank_recovery_anchors"][slot]
        return anchors["split_tank_combat_anchors"][slot]

    assert expected_anchor(1, False, False) == (-289.289093, -57.7575, 212.932236)
    assert expected_anchor(1, True, False) == (-288.8, -43.0, 212.301)
    assert expected_anchor(1, True, True) == (-286.5, -58.0, 212.2983)
    assert expected_anchor(2, True, True) == (-322.858, -48.2862, 212.2623)
    assert expected_anchor(1, True, False)[2] != expected_anchor(1, True, True)[2]

    selector_start = geometry.index("for (size_t candidateIndex = 0;")
    selector_end = geometry.index(
        "State.ValidationRouteDrudgeAnchorX =", selector_start
    )
    selector = geometry[selector_start:selector_end]
    assert "RecoveryAnchorReachedFor(OneBasedSlot)" in selector
    assert selector.index("DeclaredCombatTankAnchorFor(OneBasedSlot)") < selector.index(
        "DeclaredRecoveryTankAnchorFor(OneBasedSlot)"
    )
    assert "candidateAnchor->Z" in selector

    unique_anchor_start = geometry.index("UniqueGroupAnchor =")
    unique_anchor_end = geometry.index("AnchorCandidatesFor =", unique_anchor_start)
    unique_anchor = geometry[unique_anchor_start:unique_anchor_end]
    assert "RecoveryAnchorReachedFor(slot)" in unique_anchor
    assert "DeclaredCombatTankAnchorFor(slot)" in unique_anchor
    assert "DeclaredRecoveryTankAnchorFor(slot)" in unique_anchor
    assert "DeclaredCombatTankAnchorFor" in lanes


def test_post_rush_invalid_combat_projection_uses_nav_fallback_without_cooldown():
    geometry_path = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
    lanes_path = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp"
    probe = (ROOT / "tools/raid_program/drudge_navmesh_recovery_probe.cpp").read_text(
        encoding="utf-8"
    )
    geometry = geometry_path.read_text(encoding="utf-8")
    lanes = lanes_path.read_text(encoding="utf-8")

    # The sealed Detour replay projects tank 1's combat point back to its
    # navigation point by 2.79962 yards.  Candidate 1 is therefore the
    # already-preflighted navigation anchor; a failed candidate 0 must not
    # arm the five-second retry before candidate 1 is attempted.
    assert '"tank1_combat_anchor"' in probe
    assert '"tank2_combat_anchor"' in probe
    candidates = geometry[geometry.index("AnchorCandidatesFor ="):geometry.index(
        "AnchorCacheMatchesGeneration =", geometry.index("AnchorCandidatesFor =")
    )]
    assert "candidates.emplace_back(navigation->X, navigation->Y)" in candidates
    selector = geometry[geometry.index("for (size_t candidateIndex = 0;"):geometry.index(
        "State.ValidationRouteDrudgeAnchorX =", geometry.index("for (size_t candidateIndex = 0;")
    )]
    assert "candidateIndex ? DeclaredNavigationTankAnchorFor" in selector
    assert "candidateIndex + 1 == candidates.size()" in selector
    assert "ValidationRouteDrudgeAnchorCandidateIndex > 1" in lanes
    assert "bool const combatCandidate" in lanes


def test_drudge_reseparation_switches_from_cached_anchor_to_live_safety():
    geometry = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp").read_text(
        encoding="utf-8"
    )
    spacing = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeSpacing.cpp").read_text(
        encoding="utf-8"
    )
    actions = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeActions.cpp").read_text(
        encoding="utf-8"
    )

    group_start = geometry.index("GroupPositionSafe =")
    group_end = geometry.index("ExactRosterPrepullStaged =", group_start)
    group = geometry[group_start:group_end]
    assert "source0Safe" in group
    assert "source1Safe" in group
    assert "sameLaneSpacingSafe" in group
    assert "DynamicGroupPositionSafe" in group
    assert "prepullStaged && IsDynamicGroupRecoveryActive()" in group
    recovery_gate = group.index(
        "if (prepullStaged && IsDynamicGroupRecoveryActive())"
    )
    exact_cache = group.index("CachedAnchorSafe", recovery_gate)
    assert recovery_gate < exact_cache
    recovery_start = spacing.index(
        "bool DrudgeLaneContext::IsRecoveryFormationActive() const"
    )
    recovery = spacing[recovery_start:]
    assert "observation.Landed" in recovery
    assert "observation.ReseparationRecorded" not in recovery

    minimum_distance_start = geometry.index(
        "bool DrudgeLaneContext::TryMinimumDistance"
    )
    minimum_distance_end = geometry.index(
        "DrudgeLaneContext::PhaseResult DrudgeLaneContext::BuildAnchorPolicies",
        minimum_distance_start,
    )
    minimum_distance = geometry[minimum_distance_start:minimum_distance_end]
    assert "ExactDrudgeLaneOwnsGroupMovement" in minimum_distance
    assert "return false;" in minimum_distance

    # Formation, taunt approach, and the specialized safety exit retain an
    # explicit mechanic lease instead of falling through to combat movement.
    assert actions.count("BotMovementArbitration::Owner::Mechanic") >= 2
    assert actions.count("BotMovementArbitration::Priority::Mechanic") >= 2
    assert geometry.count("BotMovementArbitration::Owner::Mechanic") >= 1
    assert geometry.count("BotMovementArbitration::Priority::Mechanic") >= 1


def test_native_farthest_geometry_runs_only_after_sources_are_resolved():
    lanes = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp").read_text(
        encoding="utf-8"
    )

    run = lanes[lanes.index("bool DrudgeLaneContext::Run()"):
                lanes.index("DrudgeLaneContext::PhaseResult DrudgeLaneContext::BuildContract()")]
    assert run.index("ResolveSources()") < run.index("BuildAnchorPolicies()")
    contract = lanes[lanes.index("DrudgeLaneContext::PhaseResult DrudgeLaneContext::BuildContract()"):
                     lanes.index("DrudgeLaneContext::PhaseResult DrudgeLaneContext::ResolveSources()")]
    assert "Sources[sourceIndex]" not in contract
    sources = lanes[lanes.index("DrudgeLaneContext::PhaseResult DrudgeLaneContext::ResolveSources()") :]
    assert sources.index("Sources.push_back(source)") < sources.index(
        '"drudge_tank_farthest_geometry_unresolved"'
    )


def test_future_encounter_contamination_is_attempt_terminal_not_a_transient_hold():
    implementation = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    start = implementation.index("Creature* prematureNextEncounter = nullptr;")
    end = implementation.index("ValidationRoutePackContext pack", start)
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


def test_second_same_source_rush_retains_diagnostic_without_terminalizing_pull():
    implementation = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatLog.cpp").read_text(
        encoding="utf-8"
    )
    start = implementation.index(
        "uint64 BotWorldPopulationMgr::NotifyNativeCreatureSpellStarted"
    )
    end = implementation.index(
        "void BotWorldPopulationMgr::NotifyNativeCreatureSpellLanded", start
    )
    callback = implementation[start:end]
    assert "drudge_reseparation_deadline_missed" not in callback
    assert "Cohort().ValidationAttemptFailureReason" not in callback
    assert "unclosed re-separation observation remains useful diagnostic evidence" in callback
    assert "Party().ValidationRouteDrudgeChargeObservations.push_back" in callback
