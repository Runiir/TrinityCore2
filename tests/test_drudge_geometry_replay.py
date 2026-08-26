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
    // by periodic seed threat, ownership loss, and a bad first native target.
    // The assigned tank must sustain ordinary threat until the first Rush
    // actually exists; afterward a secure source no longer needs this special
    // pre-Rush action, while an insecure source still does.
    assert(BotRaidDrudgeNativeRush::ShouldBuildTankThreat(false, ready));
    assert(!BotRaidDrudgeNativeRush::ShouldBuildTankThreat(true, ready));
    assert(BotRaidDrudgeNativeRush::ShouldBuildTankThreat(true, rejected855));
    assert(BotRaidDrudgeNativeRush::AuthorityReady(false, ready));
    assert(BotRaidDrudgeNativeRush::AuthorityReady(true, ready));
    // After an exact native Rush, a scoped exact tank victim is enough even
    // when the live headroom and seed-distance predicates are no longer true.
    // A pending, same-scope observation must not unlock that post-Rush path;
    // only the native landed edge may set the authority input.
    struct ScopedRushObservation
    {
        bool SameScope;
        bool Landed;
    };
    auto hasLandedScopedRush = [](ScopedRushObservation const& observation)
    {
        return observation.SameScope && observation.Landed;
    };
    assert(!BotRaidDrudgeNativeRush::AuthorityReady(
        hasLandedScopedRush({true, false}), rejected855));
    assert(BotRaidDrudgeNativeRush::AuthorityReady(
        hasLandedScopedRush({true, true}), rejected855));
    readyRush.SeedDistance = 33.0f;
    auto recoveredRoster = BotRaidDrudgeNativeRush::Evaluate(readyRush);
    assert(!recoveredRoster.SeedIsUniqueFarthest);
    assert(!BotRaidDrudgeNativeRush::AuthorityReady(false, recoveredRoster));
    assert(BotRaidDrudgeNativeRush::AuthorityReady(true, recoveredRoster));
    BotRaidDrudgeNativeRush::SourceInput wrongVictim = readyRush;
    wrongVictim.ExactTankVictim = false;
    auto wrongVictimReadiness = BotRaidDrudgeNativeRush::Evaluate(wrongVictim);
    assert(!BotRaidDrudgeNativeRush::AuthorityReady(true, wrongVictimReadiness));
    assert(BotRaidDrudgeNativeRush::LaneOwnershipSafe(true, true, true, false));
    assert(!BotRaidDrudgeNativeRush::LaneOwnershipSafe(true, false, true, true));
    assert(!BotRaidDrudgeNativeRush::LaneOwnershipSafe(false, true, true, false));
    assert(BotRaidDrudgeNativeRush::LaneOwnershipSafe(true, true, false, false));

    assert(SelectMemberRecoveryAction(true, false, true)
        == MemberRecoveryAction::RecoverFormation);
    assert(SelectMemberRecoveryAction(true, true, true)
        == MemberRecoveryAction::PreferFriendlySupport);
    assert(SelectMemberRecoveryAction(false, false, true)
        == MemberRecoveryAction::PreferFriendlySupport);
    assert(SelectMemberRecoveryAction(false, false, false)
        == MemberRecoveryAction::Continue);

    // A safe member may reach the existing threat/evidence phase during a
    // landed Rush. Formation still owns unsafe members, pair-too-close
    // geometry, and every tank constraint before that handoff.
    assert(ShouldContinueToThreatAndEvidenceAfterLandedRush(
        true, false, true, true, false, false, true, true));
    assert(!ShouldContinueToThreatAndEvidenceAfterLandedRush(
        true, false, true, false, false, false, true, true));
    assert(!ShouldContinueToThreatAndEvidenceAfterLandedRush(
        true, false, true, true, false, true, true, true));
    assert(!ShouldContinueToThreatAndEvidenceAfterLandedRush(
        true, false, true, true, false, false, false, true));
    assert(!ShouldContinueToThreatAndEvidenceAfterLandedRush(
        true, false, true, true, false, false, true, false));
    assert(!ShouldContinueToThreatAndEvidenceAfterLandedRush(
        false, false, true, true, false, false, true, true));
    assert(!ShouldContinueToThreatAndEvidenceAfterLandedRush(
        true, true, true, true, false, false, true, true));
    assert(!ShouldContinueToThreatAndEvidenceAfterLandedRush(
        true, false, false, true, false, false, true, true));
    assert(!ShouldContinueToThreatAndEvidenceAfterLandedRush(
        true, false, true, true, false, false, true, true, false));

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
    assert "RecoveryFormationActive = IsRecoveryFormationActive();" in actions
    assert "drudge_tank_combat_anchor_return_started" not in actions
    assert '"drudge_native_charge_reseparation_wait"' in actions
    assert actions.index("LandedRushRecoveryComplete") < actions.index(
        '"drudge_native_charge_reseparation_complete"'
    )
    assert "drudge_lane_native_taunt" in actions
    assert "drudge_pre_first_rush_threat_seed" in seed
    assert "drudge_native_charge_reseparation_complete" in actions
    assert "if (TryMinimumDistance(true))" not in lanes
    assert '&& !currentScopeHasNativeRush && Role == "dps"' in actions
    scope_start = actions.index("bool const currentScopeHasNativeRush")
    scope_end = actions.index("bool const nativeRushAuthorityReady", scope_start)
    scope_scan = actions[scope_start:scope_end]
    assert "std::any_of" in scope_scan
    for field in (
        "candidate.Landed",
        "candidate.AttemptId == Manager.Cohort().AttemptId",
        "candidate.WipeGeneration == Manager.Cohort().Raid.WipeGeneration",
        "candidate.RouteGeneration == Manager.Party().ValidationRouteGeneration",
    ):
        assert field in scope_scan
    assert "return candidate.Landed &&" in " ".join(scope_scan.split())


def test_safe_landed_rush_member_reaches_threat_phase_before_global_closure():
    actions = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
               "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp").read_text(
                   encoding="utf-8")
    normalized = " ".join(actions.split())
    assert "&& !ExactRosterReSeparated() && !ContinueToThreatAndEvidence" in normalized
    assert normalized.index("!ExactRosterReSeparated()") < normalized.index(
        "!ContinueToThreatAndEvidence", normalized.index("!ExactRosterReSeparated()"))
    assert normalized.index("ShouldContinueToThreatAndEvidenceAfterLandedRush") < normalized.index(
        "DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunThreatAndEvidenceActions")


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

    assert "RecoveryTankReturnBarrierOpen() && RecoveryAnchorReachedFor" not in geometry
    assert "RecoveryTankAnchorPending(slot)" in geometry
    assert "AdvanceRecoveryTankReturnBarrier" in recovery
    assert "RecoveryTankReturnBarrierOpened" in route_state
    assert "RecoveryTankReturnBarrierOpen()" in lanes

    actions = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeActions.cpp").read_text(
        encoding="utf-8"
    )
    assert "RecoveryFormationActive && RecoveryTankReturnBarrierOpen()" in actions
    assert "recoveryAnchorsReachedBeforeTick" in actions


def test_established_pull_stays_on_entrance_recovery_anchors_with_exact_xyz():
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
            "split_recovery_member_anchors",
            "split_tank_navigation_anchors",
            "split_tank_recovery_anchors",
            "split_tank_combat_anchors",
        )
    }

    # The initial tank approach remains near the Drudges so both tanks can take
    # native ownership. Once both lane sources have their assigned tank, the
    # only legal combat endpoint is the proven entrance-side recovery anchor.
    def expected_anchor(slot, entrance_pull_established):
        if not entrance_pull_established:
            return anchors["split_tank_navigation_anchors"][slot]
        return anchors["split_tank_recovery_anchors"][slot]

    assert expected_anchor(1, False) == (-289.289093, -57.7575, 212.932236)
    assert expected_anchor(1, True) == (-288.8, -86.483, 214.154)
    assert expected_anchor(2, True) == (-338.018, -64.932, 212.751)
    assert expected_anchor(1, True) != anchors["split_tank_combat_anchors"][1]
    assert expected_anchor(2, True) != anchors["split_tank_combat_anchors"][2]

    selector_start = geometry.index("for (size_t candidateIndex = 0;")
    selector_end = geometry.index(
        "State.ValidationRouteDrudgeAnchorX =", selector_start
    )
    selector = geometry[selector_start:selector_end]
    assert "IsRecoveryFormationActive()" in selector
    assert "DeclaredRecoveryTankAnchorFor(OneBasedSlot)" in selector
    assert "DeclaredCombatTankAnchorFor(OneBasedSlot)" not in selector
    assert "candidateAnchor->Z" in selector

    unique_anchor_start = geometry.index("UniqueGroupAnchor =")
    unique_anchor_end = geometry.index("AnchorCandidatesFor =", unique_anchor_start)
    unique_anchor = geometry[unique_anchor_start:unique_anchor_end]
    assert "IsRecoveryFormationActive()" in unique_anchor
    assert "DeclaredCombatTankAnchorFor(slot)" not in unique_anchor
    assert "DeclaredRecoveryTankAnchorFor(slot)" in unique_anchor
    assert "DeclaredRecoveryMemberAnchorFor(slot)" in unique_anchor
    assert "IsDynamicGroupRecoveryActive()" not in unique_anchor
    assert "DeclaredCombatTankAnchorFor" in lanes  # initial taunt geometry only
    assert "drudge_anchor_future_encounter_contract_unresolved" in geometry
    assert "drudge_anchor_future_encounter_path_unsafe" in geometry
    assert "ValidationRouteSplitTankCombatAnchors" in geometry

    recovery_members = anchors["split_recovery_member_anchors"]
    assert recovery_members[3] == (-297.339, -115.904, 214.552)
    assert recovery_members[8] == (-311.5, -123.0, 214.034)


def test_entrance_recovery_never_offers_a_magmaw_side_return_candidate():
    geometry_path = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
    lanes_path = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp"
    probe = (ROOT / "tools/raid_program/drudge_navmesh_recovery_probe.cpp").read_text(
        encoding="utf-8"
    )
    geometry = geometry_path.read_text(encoding="utf-8")
    lanes = lanes_path.read_text(encoding="utf-8")

    # Combat and navigation coordinates are retained for the initial native
    # ownership transition. They must not be offered after the entrance
    # formation activates.
    assert '"tank1_combat_anchor"' in probe
    assert '"tank2_combat_anchor"' in probe
    candidates = geometry[geometry.index("AnchorCandidatesFor ="):geometry.index(
        "AnchorCacheMatchesGeneration =", geometry.index("AnchorCandidatesFor =")
    )]
    assert "candidates.emplace_back(navigation->X, navigation->Y)" in candidates
    assert "RecoveryTankReturnBarrierOpen() && RecoveryAnchorReachedFor(slot)" not in candidates
    selector = geometry[geometry.index("for (size_t candidateIndex = 0;"):geometry.index(
        "State.ValidationRouteDrudgeAnchorX =", geometry.index("for (size_t candidateIndex = 0;")
    )]
    dynamic_branch = selector[selector.index("bool const dynamicRecovery"):selector.index(
        "if (!candidateAnchor)", selector.index("bool const dynamicRecovery")
    )]
    assert "DeclaredRecoveryTankAnchorFor(OneBasedSlot)" in dynamic_branch
    assert "DeclaredCombatTankAnchorFor(OneBasedSlot)" not in dynamic_branch
    assert "candidateIndex + 1 == candidates.size()" in selector
    assert "ValidationRouteDrudgeAnchorCandidateIndex > 1" in lanes
    assert "bool const combatCandidate" in lanes


def test_drudge_reseparation_requires_live_safety_and_recovery_anchor_arrival():
    geometry = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp").read_text(
        encoding="utf-8"
    )
    group_safety = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGroupSafety.cpp").read_text(
        encoding="utf-8"
    )
    actions = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeActions.cpp").read_text(
        encoding="utf-8"
    )
    spacing = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeSpacing.cpp").read_text(
        encoding="utf-8"
    )

    group = group_safety[group_safety.index("ComputeGroupPositionSafe"):]
    assert "source0Safe" in group
    assert "source1Safe" in group
    assert "sameLaneSpacingSafe" in group
    assert "DynamicGroupPositionSafe" in group
    assert "prepullStaged && IsDynamicGroupRecoveryActive()" not in group
    assert "CachedAnchorSafe(*memberState, member)" in group
    assert "explicitRecoveryFormation || sameLaneSpacingSafe" in group
    recovery_source = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeRecovery.cpp").read_text(
        encoding="utf-8"
    )
    assert "DeclaredRecoveryMemberAnchorFor(OneBasedSlot)" in recovery_source
    assert "Distance2d(x, y, declared->X, declared->Y) <= 0.01f" in recovery_source
    wrapper_start = geometry.index("GroupPositionSafe =")
    wrapper_end = geometry.index("ExactRosterPrepullStaged =", wrapper_start)
    assert "ComputeGroupPositionSafe(member)" in geometry[wrapper_start:wrapper_end]
    recovery_start = spacing.index(
        "bool DrudgeLaneContext::IsRecoveryFormationActive() const"
    )
    recovery = spacing[recovery_start:]
    assert "IsEntrancePullEstablished() || IsLandedRushPending()" in recovery
    assert "ValidationRouteDrudgeChargeObservations" not in recovery

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


def test_canary39_unsafe_healer_replays_native_recovery_before_same_tick_support():
    actions = (
        ROOT
        / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
        "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp"
    ).read_text(encoding="utf-8")
    normalized = " ".join(actions.split())
    recovery_start = normalized.index("bool const formationRecoveryBeforeSupport")
    recovery_end = normalized.index("char const* result", recovery_start)
    recovery = normalized[recovery_start:recovery_end]

    # Canary39's healer was unsafe against the live Drudge source geometry,
    # but support selection returned PreferFriendlySupport before this route
    # could reach the existing native movement submission.  The repair admits
    # the set-and-forget movement first and keeps the instant heal in the same
    # tick.
    assert (
        "MemberRecoveryAction::PreferFriendlySupport && !alreadySafe" in recovery
    )
    formation_before_support = recovery.index(
        "if (formationRecoveryBeforeSupport) tryFormationRecovery();"
    )
    support = recovery.index("Callbacks.TryGroupHeal")
    fallback_formation = recovery.index(
        "if (!formationRecoveryBeforeSupport) tryFormationRecovery();"
    )
    assert formation_before_support < support < fallback_formation

    # The first call still travels through the dynamic source-relative
    # candidate and native submission edge rather than writing position state.
    lambda_start = normalized.index("auto tryFormationRecovery =")
    recovery_lambda = normalized[lambda_start:recovery_start]
    assert "SelectPathableDrudgeAnchor(AssignedTank)" in recovery_lambda
    assert "GroupPositionSafe(Bot)" in recovery_lambda
    assert "MoveBotToPointWithReferenceFloor" in recovery_lambda

    # Deterministic replay of the attributable Canary39 state.  Thunderclap's
    # 15-yard exclusion is violated at the measured 13.2548-yard live-source
    # distance, while NativeChargePending is false and healer support exists.
    thunderclap_radius = 15.0
    nearest_live_drudge_distance = 13.2548
    member_geometry_safe = nearest_live_drudge_distance >= thunderclap_radius
    native_charge_pending = False
    support_available = True
    selected_action = (
        "RecoverFormation"
        if native_charge_pending and not member_geometry_safe
        else "PreferFriendlySupport"
        if support_available
        else "Continue"
    )
    assert selected_action == "PreferFriendlySupport"
    events = []
    formation_recovery_before_support = (
        selected_action == "RecoverFormation"
        or (selected_action == "PreferFriendlySupport" and not member_geometry_safe)
    )
    if formation_recovery_before_support:
        events.append("native_formation_submission")
    if selected_action == "PreferFriendlySupport":
        events.append("same_tick_friendly_support")
    if not formation_recovery_before_support:
        events.append("native_formation_submission")
    assert events == ["native_formation_submission", "same_tick_friendly_support"]


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
