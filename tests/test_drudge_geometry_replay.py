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
    readyRush.SeedDistance = 33.0f;
    assert(!BotRaidDrudgeNativeRush::Evaluate(readyRush).SeedIsUniqueFarthest);

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
    geometry = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp").read_text(
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
    assert "ValidationRouteDrudgeChargeObservations" in geometry
    assert "RecoveryPathPreservesTankSeparation" in geometry
    assert "ValidationRouteDrudgeAnchorSource0Identity" in geometry
    assert "ExactRosterPrepullStaged" in geometry
    assert "ValidationRouteSplitSourceGuids" in lanes
    assert "ValidationRouteSplitLaneARosterSlots" in lanes
    assert "SetAllOffenseSuppressed" in actions
    assert "SelectMemberRecoveryAction" in actions
    assert "RecoveryAnchorReachedFor" in geometry
    assert "ExactRecoveryTankAnchorsReached" in actions
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


def test_drudge_reseparation_switches_from_cached_anchor_to_live_safety():
    geometry = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp").read_text(
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
    assert "prepullStaged && IsRecoveryFormationActive()" in group
    recovery_gate = group.index(
        "if (prepullStaged && IsRecoveryFormationActive())"
    )
    exact_cache = group.index("CachedAnchorSafe", recovery_gate)
    assert recovery_gate < exact_cache
    recovery_start = geometry.index(
        "bool DrudgeLaneContext::IsRecoveryFormationActive() const"
    )
    recovery_end = geometry.index(
        "bool DrudgeLaneContext::TryMinimumDistance", recovery_start
    )
    recovery = geometry[recovery_start:recovery_end]
    assert "observation.Landed" in recovery
    assert "observation.ReseparationRecorded" not in recovery

    # Formation, taunt approach, and the specialized safety exit retain an
    # explicit mechanic lease instead of falling through to combat movement.
    assert actions.count("BotMovementArbitration::Owner::Mechanic") >= 2
    assert actions.count("BotMovementArbitration::Priority::Mechanic") >= 2
    assert geometry.count("BotMovementArbitration::Owner::Mechanic") >= 1
    assert geometry.count("BotMovementArbitration::Priority::Mechanic") >= 1


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
