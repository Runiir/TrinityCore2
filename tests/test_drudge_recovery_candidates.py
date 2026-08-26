import json
from math import hypot
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DRUDGE = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge"
GEOMETRY = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
ESCAPE = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeEscape.cpp"
RECOVERY = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeRecovery.cpp"
SPACING = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeSpacing.cpp"
HEADER = DRUDGE / "BotRaidDrudgeRecoveryCandidates.h"
NATIVE_ANCHOR = DRUDGE / "BotRaidDrudgeNativeAnchor.h"
NATIVE_FLOOR = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativeFloor.h"
ACTIONS = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp"
PLANNER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementPlanner.cpp"
PATH_VALIDATION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativePathValidation.h"
SCENARIO = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
LANE_SELECTION = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp"


def test_recovery_candidates_replay_prefers_fixed_safe_and_stays_deterministic(tmp_path):
    source = tmp_path / "drudge_recovery_candidates_replay.cpp"
    binary = tmp_path / "drudge_recovery_candidates_replay"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeRecoveryCandidates.h"
#include <cassert>
#include <cmath>

using namespace BotRaidDrudgeRecoveryCandidates;

int main()
{
    Point2d const declared{ -20.0f, 0.0f };
    Point2d const source0{ 0.0f, 0.0f };
    Point2d const source1{ 8.0f, 0.0f };
    auto fixedSafe = BuildCandidates(
        declared, source0, source1, { 1.0f, 0.0f }, -1.0f, 15.0f);
    assert(!fixedSafe.empty());
    assert(fixedSafe.front().FanIndex == 0);
    assert(NearlyEqual(fixedSafe.front().Point, declared));
    Constraints safeConstraints{
        source0, source1, { 4.0f, 0.0f }, { 1.0f, 0.0f },
        15.0f, -1.0f, 3.0f };
    assert(SourceSafe(fixedSafe.front().Point, safeConstraints));
    assert(LaneSafe(fixedSafe.front().Point, safeConstraints));

    auto fixedSafeAgain = BuildCandidates(
        declared, source0, source1, { 1.0f, 0.0f }, -1.0f, 15.0f);
    assert(fixedSafeAgain.size() == fixedSafe.size());
    for (std::size_t index = 0; index < fixedSafe.size(); ++index)
    {
        assert(fixedSafe[index].FanIndex == fixedSafeAgain[index].FanIndex);
        assert(NearlyEqual(fixedSafe[index].Point, fixedSafeAgain[index].Point));
    }

    Point2d const overlapping{ 0.0f, 0.0f };
    auto overlapFan = BuildCandidates(
        overlapping, overlapping, overlapping, { 1.0f, 0.0f }, -1.0f, 15.0f);
    assert(overlapFan.size() > 1);
    Constraints overlapConstraints{
        overlapping, overlapping, { 0.0f, 0.0f }, { 1.0f, 0.0f },
        15.0f, -1.0f, 0.0f };
    assert(!SourceSafe(overlapFan.front().Point, overlapConstraints));
    for (std::size_t index = 1; index < overlapFan.size(); ++index)
        assert(SourceSafe(overlapFan[index].Point, overlapConstraints));

    Point2d const source0Home{ 0.0f, 20.0f };
    Point2d const source1Home{ 8.0f, 20.0f };
    assert(!SourceSafeAgainstUnion({ 0.0f, 10.0f }, safeConstraints,
        source0Home, source1Home));
    auto unionFan = BuildCandidates(
        declared, source0, source1, source0Home, source1Home,
        { 1.0f, 0.0f }, -1.0f, 15.0f);
    assert(!unionFan.empty());
    for (Candidate const& candidate : unionFan)
        assert(SourceSafeAgainstUnion(candidate.Point, safeConstraints,
            source0Home, source1Home));

    Constraints wrongLane = safeConstraints;
    wrongLane.LaneSign = 1.0f;
    bool laneSafeCandidate = false;
    for (Candidate const& candidate : fixedSafe)
        laneSafeCandidate = laneSafeCandidate
            || LaneSafe(candidate.Point, wrongLane);
    assert(!laneSafeCandidate);

    assert(std::fabs(PathDistanceFloor(7.0f, 15.0f) - 6.75f) < 0.001f);
    assert(std::fabs(PathDistanceFloor(20.0f, 15.0f) - 14.75f) < 0.001f);
    assert(PathPointPreservesSourceDistance(
        { 6.8f, 0.0f }, { 0.0f, 0.0f }, 7.0f, 15.0f));
    assert(!PathPointPreservesSourceDistance(
        { 6.0f, 0.0f }, { 0.0f, 0.0f }, 7.0f, 15.0f));
    assert(PathPointPreservesSourceDistance(
        { 14.8f, 0.0f }, { 0.0f, 0.0f }, 20.0f, 15.0f));
    assert(!PathPointPreservesSourceDistance(
        { 14.0f, 0.0f }, { 0.0f, 0.0f }, 20.0f, 15.0f));

    Point2d const escapeStart{ -5.0f, 0.0f };
    Point2d const escapeEndpoint{ -5.5f, 0.0f };
    assert(EscapeEndpointProgresses(escapeStart, escapeEndpoint,
        source0, source1, 15.0f));
    assert(!EscapeEndpointProgresses(escapeStart, { -5.49f, 0.0f },
        source0, source1, 15.0f));
    assert(!EscapeEndpointProgresses(escapeStart, { -4.5f, 0.0f },
        source0, source1, 15.0f));
    assert(BoundedEndpointMiss({ -6.478f, 0.0f }, escapeEndpoint, 2.0f));
    assert(BoundedEndpointMiss({ -7.375f, 0.0f }, escapeEndpoint, 2.0f));
    assert(!BoundedEndpointMiss({ -7.501f, 0.0f }, escapeEndpoint, 2.0f));
    assert(!BoundedEndpointMiss({ -5.75f, 0.0f }, escapeEndpoint, 2.0f));
    assert(PreferEscapeEndpoint(false, 0.0f, 5.5f));
    assert(PreferEscapeEndpoint(true, 5.0f, 5.5f));
    assert(!PreferEscapeEndpoint(true, 5.5f, 5.5f));
    assert(!PreferEscapeEndpoint(true, 6.0f, 5.5f));
    assert(IsEscapeCandidateIndex(EscapeCandidateIndex(3)));

    // Canary28 exact slot-8 replay. The landed Rush displaced the member
    // inside source 0 while its declared anchor remained stale.
    Point2d const slot8Declared{ -311.5f, -78.0f };
    Point2d const slot8Current{ -341.301f, -79.0869f };
    Point2d const slot8Source0{ -328.567f, -74.655f };
    Point2d const slot8Source1{ -297.355f, -80.0307f };
    Point2d const slot8Home0{ -298.833f, -50.349f };
    Point2d const slot8Home1{ -307.913f, -49.5694f };
    Point2d const slot8Axis = Normalize({
        slot8Home1.X - slot8Home0.X, slot8Home1.Y - slot8Home0.Y });
    Point2d const slot8Midpoint{
        (slot8Home0.X + slot8Home1.X) * 0.5f,
        (slot8Home0.Y + slot8Home1.Y) * 0.5f };
    Constraints const slot8Constraints{
        slot8Source0, slot8Source1, slot8Midpoint, slot8Axis,
        15.0f, 1.0f, 17.0f * 0.25f };
    auto slot8UnionSafe = [&](Point2d const& point)
    {
        return SourceSafeAgainstUnion(point, slot8Constraints,
            slot8Home0, slot8Home1);
    };
    auto slot8LaneSafe = [&](Point2d const& point)
    {
        return LaneSafe(point, slot8Constraints);
    };
    assert(!slot8UnionSafe(slot8Current));
    assert(NearlyEqual(SelectOrigin(slot8Declared, slot8Current,
        false, true, false), slot8Current));
    Point2d const safeMember{ -350.0f, -79.0f };
    assert(slot8UnionSafe(safeMember));
    assert(NearlyEqual(SelectOrigin(slot8Declared, safeMember,
        false, true, true), slot8Declared));
    assert(NearlyEqual(SelectOrigin(slot8Declared, slot8Current,
        false, false, false), slot8Declared));
    assert(NearlyEqual(SelectOrigin(slot8Declared, slot8Current,
        true, true, false), slot8Declared));

    auto currentSlot8Fan = BuildCandidates(
        SelectOrigin(slot8Declared, slot8Current, false, true, false),
        slot8Source0, slot8Source1, slot8Home0, slot8Home1,
        slot8Axis, 1.0f, 15.0f);
    // The current-origin fan must include an outward, same-lane safe exit.
    bool currentOriginHasSafeLaneExit = false;
    for (Candidate const& candidate : currentSlot8Fan)
        currentOriginHasSafeLaneExit = currentOriginHasSafeLaneExit
            || (candidate.FanIndex > 0
                && slot8UnionSafe(candidate.Point)
                && slot8LaneSafe(candidate.Point));
    assert(currentOriginHasSafeLaneExit);

    // Rebuild from the stale declared origin to prove the old failure. The
    // only declared-origin candidate that is both union-safe and same-lane is
    // fan 5; its direct path immediately violates the recorded floor.
    auto declaredSlot8Fan = BuildCandidates(
        slot8Declared, slot8Source0, slot8Source1,
        slot8Home0, slot8Home1, slot8Axis, 1.0f, 15.0f);
    Candidate const* staleSafeCandidate = nullptr;
    for (Candidate const& candidate : declaredSlot8Fan)
        if (candidate.FanIndex == 5)
            staleSafeCandidate = &candidate;
    assert(staleSafeCandidate);
    assert(slot8UnionSafe(staleSafeCandidate->Point));
    assert(slot8LaneSafe(staleSafeCandidate->Point));
    Point2d const firstStalePathPoint{
        slot8Current.X + (staleSafeCandidate->Point.X - slot8Current.X) * 0.01f,
        slot8Current.Y + (staleSafeCandidate->Point.Y - slot8Current.Y) * 0.01f };
    float const slot8StartDistance = std::sqrt(
        DistanceSquared(slot8Current, slot8Source0));
    assert(!PathPointPreservesSourceDistance(firstStalePathPoint,
        slot8Source0, slot8StartDistance, 15.0f));

    bool noSafeCandidate = false;
    for (Candidate const& candidate : overlapFan)
        noSafeCandidate = noSafeCandidate
            || (SourceSafe(candidate.Point, wrongLane)
                && LaneSafe(candidate.Point, wrongLane));
    assert(!noSafeCandidate);
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


def test_recovery_tank_proof_uses_recovery_members_and_keeps_stale_cache_guard():
    lane_selection = LANE_SELECTION.read_text(encoding="utf-8")
    proof_start = lane_selection.index(
        "bool DrudgeLaneContext::ComputeExactRecoveryTankPathsProven() const"
    )
    proof_end = lane_selection.index(
        "bool DrudgeLaneContext::ComputeExactRecoveryTankAnchorsReached() const",
        proof_start,
    )
    proof = lane_selection[proof_start:proof_end]

    # Normal and recovery member formations are intentionally different. The
    # recovery clearance proof must inspect the active recovery formation, not
    # accidentally bless the normal pull anchors.
    scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
    drudges = next(
        step
        for scenario_row in scenario["scenarios"]
        if scenario_row["id"] == "blackwing_descent_10n"
        for step in scenario_row["route"]
        if step.get("mechanic_profile") == "trash_two_tank_charge_lanes"
    )
    normal_members = {
        anchor["roster_slot"]: anchor for anchor in drudges["split_member_anchors"]
    }
    recovery_members = {
        anchor["roster_slot"]: anchor
        for anchor in drudges["split_recovery_member_anchors"]
    }
    assert set(normal_members) == set(recovery_members) == set(range(1, 11))
    assert normal_members[3] != recovery_members[3]
    assert "for (MemberAnchor const& anchor : config.ValidationRouteSplitRecoveryMemberAnchors)" in proof
    assert "ValidationRouteSplitMemberAnchors" not in proof

    geometry = GEOMETRY.read_text(encoding="utf-8")
    selector_start = geometry.index("SelectPathableDrudgeAnchor =")
    cache_start = geometry.index("auto cacheUsable", selector_start)
    cache_end = geometry.index("if (cacheUsable())", cache_start)
    cache = geometry[cache_start:cache_end]
    # Commit 08c549's tankRecovery exception keeps stale candidate-index
    # validation active for tank recovery while preserving dynamic retries.
    assert "if ((!activeDynamicRecovery || tankRecovery)" in cache
    assert "State.ValidationRouteDrudgeAnchorCandidateIndex >= candidates.size()" in cache


def test_recovery_candidate_contract_is_persistent_and_native_strict_for_tanks_and_members():
    geometry = GEOMETRY.read_text(encoding="utf-8")
    recovery = RECOVERY.read_text(encoding="utf-8")
    spacing = SPACING.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    actions = ACTIONS.read_text(encoding="utf-8")
    planner = PLANNER.read_text(encoding="utf-8")
    path_validation = PATH_VALIDATION.read_text(encoding="utf-8")

    candidates = geometry[geometry.index("AnchorCandidatesFor ="):geometry.index(
        "AnchorCacheMatchesGeneration =", geometry.index("AnchorCandidatesFor =")
    )]
    assert "bool const tankRecovery = tankSlot && IsRecoveryFormationActive()" in candidates
    assert "(!tankSlot || tankRecovery)" in candidates
    assert "!tankSlot && !CombatTankStagingActive()" in candidates
    assert "SelectOrigin" in candidates
    assert "currentSourceUnionSafe" in candidates
    assert "IsLandedRushPending()" in candidates
    assert "BotRaidDrudgeRecoveryCandidates::BuildCandidates" in candidates
    assert "RecoveryAnchorReachedFor(slot)" not in candidates
    assert "RecoveryTankReturnBarrierOpen() && RecoveryAnchorReachedFor(slot)" not in candidates

    selector = geometry[geometry.index("SelectPathableDrudgeAnchor ="):geometry.index(
        "ExactRosterReSeparated =", geometry.index("SelectPathableDrudgeAnchor =")
    )]
    assert "drudge_anchor_source_unsafe" in selector
    assert "drudge_anchor_spacing_unsafe" in selector
    assert "drudge_anchor_lane_unsafe" in selector
    assert "StrictNativePath" in selector
    assert "tank || IsDynamicGroupRecoveryActive()" in selector
    assert "IsRecoveryCandidateSpacingSafe" in selector
    assert "bool const tankRecovery = tank && IsRecoveryFormationActive()" in selector

    cache = selector[selector.index("auto cacheUsable"):selector.index(
        "if (cacheUsable())", selector.index("auto cacheUsable")
    )]
    assert "activeDynamicRecovery" in cache
    assert "(!activeDynamicRecovery || tankRecovery)" in cache
    assert "SourceUnionSafe" in cache
    assert "LaneSafe" in cache
    assert "IsRecoveryCandidateSpacingSafe" in cache
    assert "CandidateIndex >= candidates.size()" in cache
    assert "!activeDynamicRecovery" in cache

    assert "State.LastPathRejectReason.empty()" in actions
    assert '"drudge_lane_native_path_rejected" : State.LastPathRejectReason' in actions
    assert "ShouldInvalidateAnchorAfterPathRejection" in actions
    assert "NativePathFloorsValid(Bot, path, z, true)" in geometry
    assert "SourceUnionPathSafe(path)" in geometry
    assert "dynamicCandidate && !tank" in selector
    assert "NativePathIsComplete(pathOk, path)" in geometry
    assert "BotWorldPopulationMgrNativePathValidation.h" in planner
    assert "NativePathFloorsValid(bot, candidatePath)" in planner
    assert "NativePathIsComplete(pathOk, path)" in planner
    assert "NativePathPointFloorValid" in path_validation
    assert "NativePathFloorsValid" in path_validation
    assert "SourceUnionSafeAt" in spacing
    assert "SourceUnionSafe" in spacing

    entrance = spacing[spacing.index("IsEntrancePullEstablished"):spacing.index(
        "IsRecoveryFormationActive", spacing.index("IsEntrancePullEstablished")
    )]
    assert "member.Active && member.LeaseOwned && member.Role == \"tank\"" in entrance
    assert "ValidationRouteDrudgeOwnershipRosterGuids" in entrance
    assert "!owners.count(guid)" in entrance
    assert "exactTanks == 2" in entrance
    assert "owners.size() == exactTanks" in entrance

    assert "ComputeStrictTankRecoveryPath" in recovery
    assert "ComputeRecoveryAnchorReached" in recovery
    assert "RecoveryPathPreservesTankSeparation" in recovery
    assert "ValidationRouteSplitNavigationMarginYards" in recovery
    assert "ValidationRouteSplitArrivalToleranceYards" in recovery
    assert "urand" not in header
    assert len(GEOMETRY.read_text(encoding="utf-8").splitlines()) <= 999
    assert len(recovery.splitlines()) <= 1000


def test_progressive_escape_uses_only_bounded_complete_native_endpoints():
    geometry = GEOMETRY.read_text(encoding="utf-8")
    escape = ESCAPE.read_text(encoding="utf-8")

    assert "SelectProgressiveDrudgeEscape(nowMs)" in geometry
    assert geometry.index("for (size_t candidateIndex = 0;") \
        < geometry.index("SelectProgressiveDrudgeEscape(nowMs)")
    assert "nativeSearchDueAtEntry" in geometry
    assert "IsEscapeCandidateIndex" in geometry
    for marker in (
        "!Bot || AssignedTank",
        "IsDynamicGroupRecoveryActive()",
        "SourceUnionSafe(Bot->GetPositionX(), Bot->GetPositionY())",
        "NativePathIsComplete(pathOk, path)",
        "NativePathFloorsValid(",
        "BoundedEndpointMiss(",
        "EscapeEndpointProgresses(",
        "PreservesUnionDistanceFloors(",
        "EvaluateAndRecordCandidateSpacing(escapeIndex",
        "endpointSpacing.LaneSafe",
        "endpointSpacing.Spacing.Safe",
        "SeedCombatEnvelopeSafe(",
        "MinimumLiveSourceDistance(",
        "PreferEscapeEndpoint(",
        "State.ValidationRouteDrudgeAnchorX = bestEndpoint.X",
        "State.ValidationRouteDrudgeAnchorY = bestEndpoint.Y",
        "State.ValidationRouteDrudgeAnchorZ = bestZ",
        '"selected_progressive_path_proven"',
        "ObserveReseparationCandidate(",
    ):
        assert marker in escape
    assert "PATHFIND_NOPATH" not in escape
    assert "MovePoint" not in escape
    assert "MotionMaster" not in escape
    assert len(escape.splitlines()) <= 999


def test_prepull_tank_fallback_keeps_declared_then_navigation_anchor_contract():
    geometry = GEOMETRY.read_text(encoding="utf-8")
    candidates = geometry[geometry.index("AnchorCandidatesFor ="):geometry.index(
        "AnchorCacheMatchesGeneration =", geometry.index("AnchorCandidatesFor =")
    )]
    selector = geometry[geometry.index("SelectPathableDrudgeAnchor ="):geometry.index(
        "ExactRosterReSeparated =", geometry.index("SelectPathableDrudgeAnchor =")
    )]
    assert "if (tankSlot && !CombatTankStagingActive())" in candidates
    assert candidates.count("candidates.emplace_back(navigation->X, navigation->Y)") == 1
    assert "RecoveryAnchorReachedFor(slot)" not in candidates
    assert "bool const prepullTankFallback = tank && !CombatTankStagingActive();" in selector
    assert "prepullTankFallback && candidateIndex" in selector
    assert "dynamicCandidate || prepullTankFallback || !CombatTankStagingActive()" in selector
    assert "!CombatTankStagingActive() && candidateIndex > 0" in selector
    assert "State.ValidationRouteDrudgeAnchorCandidateIndex > 0" in selector
    assert "ResolveDynamicCandidateZ" in selector
    assert "StrictNativePath(candidatePoint.X, candidatePoint.Y, candidateZ" in selector

    scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
    drudges = next(
        step for step in next(
            scenario_row for scenario_row in scenario["scenarios"]
            if scenario_row["id"] == "blackwing_descent_10n"
        )["route"]
        if step.get("mechanic_profile") == "trash_two_tank_charge_lanes"
    )
    homes = drudges["split_source_home_anchors"]
    axis_x = homes[1]["x"] - homes[0]["x"]
    axis_y = homes[1]["y"] - homes[0]["y"]
    axis_length = hypot(axis_x, axis_y)
    axis_x /= axis_length
    axis_y /= axis_length
    midpoint_x = (homes[0]["x"] + homes[1]["x"]) * 0.5
    midpoint_y = (homes[0]["y"] + homes[1]["y"]) * 0.5
    minimum = drudges["split_minimum_separation_yards"]
    lane_separation = minimum + drudges["split_navigation_margin_yards"]
    tanks = {
        anchor["roster_slot"]: anchor
        for anchor in drudges["split_tank_navigation_anchors"]
    }
    for slot, source_index, lane_sign in ((1, 0, -1.0), (2, 1, 1.0)):
        anchor = tanks[slot]
        distance = hypot(anchor["x"] - homes[source_index]["x"],
                         anchor["y"] - homes[source_index]["y"])
        projection = ((anchor["x"] - midpoint_x) * axis_x
                      + (anchor["y"] - midpoint_y) * axis_y)
        assert distance <= minimum
        assert lane_sign * projection >= lane_separation * 0.25


def test_dynamic_fan_candidate_is_grounded_before_exact_native_path_admission():
    geometry = GEOMETRY.read_text(encoding="utf-8")
    native_anchor = NATIVE_ANCHOR.read_text(encoding="utf-8")
    selector = geometry[geometry.index("for (size_t candidateIndex = 0;"):geometry.index(
        "State.ValidationRouteDrudgeAnchorX =", geometry.index(
            "for (size_t candidateIndex = 0;"
        )
    )]

    assert "ResolveDynamicCandidateZ" in selector
    assert "dynamicCandidate && candidateIndex > 0" in selector
    assert "tankRecovery" in selector
    assert "StrictTankRecoveryPath(candidatePoint.X, candidatePoint.Y, candidateZ)" in selector
    assert '"drudge_anchor_tank_path_geometry_rejected"' in selector
    assert "StrictNativePath(candidatePoint.X, candidatePoint.Y, candidateZ" in selector
    assert "float candidateZ = candidateAnchor->Z;" in selector
    assert "State.ValidationRouteDrudgeAnchorZ = candidateZ" in geometry
    assert "candidateAnchor->Z, &candidateZ" in selector
    assert "drudge_anchor_floor_rejected" in selector
    assert "AdmitResolvedHeight(*candidateZ, declaredZ)" in native_anchor
    assert "hintZ + 2.0f" in native_anchor
    assert "GetHeight(phaseShift, x, y" in native_anchor
    assert "std::isfinite(resolved)" in native_anchor


def test_stacked_floor_admission_requires_declared_native_path_evidence(tmp_path):
    source = tmp_path / "drudge_native_floor_replay.cpp"
    binary = tmp_path / "drudge_native_floor_replay"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrNativeFloor.h"
#include <cassert>
#include <limits>

using namespace BotWorldMovement;

int main()
{
    NativeFloorResult const near = AdmitResolvedHeight(214.4f, 214.0f);
    assert(near.Accepted());
    assert(!near.UsesDeclaredFallback());
    assert(near.Z == 214.4f);

    NativeFloorResult const stacked = AdmitResolvedHeight(-138.287f, 214.0f);
    assert(stacked.Accepted());
    assert(stacked.UsesDeclaredFallback());
    assert(stacked.Z == 214.0f);

    assert(AdmitNativePathPoint(-138.287f, 214.2f, 214.0f, true));
    assert(!AdmitNativePathPoint(-138.287f, 204.0f, 214.0f, true));
    assert(!AdmitNativePathPoint(-138.287f, 214.2f, 214.0f, false));
    // A near-resolved endpoint must still admit a remote intermediate sample
    // through the declared/reference-floor envelope.
    assert(AdmitNativePathPoint(-138.287f, near.Z, 214.0f, true));
    assert(!AdmitNativePathPoint(-138.287f, 218.01f, 214.0f, true));
    assert(NativePathReferenceFloorValid(218.0f, 214.0f));
    assert(!NativePathReferenceFloorValid(218.01f, 214.0f));
    assert(!NativePathReferenceFloorValid(
        std::numeric_limits<float>::quiet_NaN(), 214.0f));
    assert(!AdmitNativePathPoint(std::numeric_limits<float>::quiet_NaN(),
        214.0f, 214.0f, true));
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
