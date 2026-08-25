import json
from math import hypot
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DRUDGE = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge"
GEOMETRY = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
RECOVERY = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeRecovery.cpp"
HEADER = DRUDGE / "BotRaidDrudgeRecoveryCandidates.h"
NATIVE_ANCHOR = DRUDGE / "BotRaidDrudgeNativeAnchor.h"
ACTIONS = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp"
PLANNER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementPlanner.cpp"
PATH_VALIDATION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativePathValidation.h"
SCENARIO = ROOT / "experiments/configs/validation_scenarios_cata_001.json"


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

    Constraints wrongLane = safeConstraints;
    wrongLane.LaneSign = 1.0f;
    bool laneSafeCandidate = false;
    for (Candidate const& candidate : fixedSafe)
        laneSafeCandidate = laneSafeCandidate
            || LaneSafe(candidate.Point, wrongLane);
    assert(!laneSafeCandidate);

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


def test_prepull_latch_keeps_combat_anchor_phase_after_exact_member_stage(tmp_path):
    source = tmp_path / "drudge_prepull_stage_replay.cpp"
    binary = tmp_path / "drudge_prepull_stage_replay"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"
#include <cassert>

using namespace BotRaidDrudgeGeometry;

int main()
{
    assert(!CombatTankStageLatched(false));
    assert(CombatTankStageLatched(true));

    Scope scope{7, 0, 3, 669, 14, 250140, 250141};
    State state;
    Input sourceCombatBeforeLatch;
    sourceCombatBeforeLatch.Identity = scope;
    sourceCombatBeforeLatch.SourceCombatStarted = true;
    sourceCombatBeforeLatch.BothCombatTankPathsProven = true;
    sourceCombatBeforeLatch.BothCombatTankAnchorsSafe = true;
    sourceCombatBeforeLatch.ChargeQueueIdle = true;
    sourceCombatBeforeLatch.SourcesAlive = true;
    sourceCombatBeforeLatch.SourcesSeparated = true;
    sourceCombatBeforeLatch.SourcesOnFrozenLanes = true;
    sourceCombatBeforeLatch.TanksOnFrozenLanes = true;
    sourceCombatBeforeLatch.BoundTankSourceGeometrySafe = true;
    sourceCombatBeforeLatch.NativeMeleeStopBounded = true;
    auto held = Advance(state, sourceCombatBeforeLatch);
    assert(held.NextDecision == Decision::AwaitExactPrepull);
    assert(!held.SupportAllowed);
    assert(!held.TankMovementAllowed);
    assert(!held.NativeOwnershipAllowed);
    assert(!held.NativeEngagementAllowed);
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

    geometry = GEOMETRY.read_text(encoding="utf-8")
    staging = geometry[
        geometry.index("CombatTankStagingActive =") : geometry.index(
            "StrictNativePath =", geometry.index("CombatTankStagingActive =")
        )
    ]
    assert "CombatTankStageLatched" in staging
    assert "SourceCombatStarted" not in staging
    assert "ValidationRouteDrudgePrepullAttemptId" in staging
    assert "ValidationRouteDrudgePrepullWipeGeneration" in staging
    assert "ValidationRouteDrudgePrepullRouteGeneration" in staging


def test_recovery_candidate_contract_is_landed_and_native_strict_for_tanks_and_members():
    geometry = GEOMETRY.read_text(encoding="utf-8")
    recovery = RECOVERY.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    actions = ACTIONS.read_text(encoding="utf-8")
    planner = PLANNER.read_text(encoding="utf-8")
    path_validation = PATH_VALIDATION.read_text(encoding="utf-8")

    candidates = geometry[geometry.index("AnchorCandidatesFor ="):geometry.index(
        "AnchorCacheMatchesGeneration =", geometry.index("AnchorCandidatesFor =")
    )]
    assert "bool const landedTankRecovery = tankSlot && IsLandedRushPending()" in candidates
    assert "(!tankSlot || landedTankRecovery)" in candidates
    assert "!tankSlot && !CombatTankStagingActive()" in candidates
    assert "BotRaidDrudgeRecoveryCandidates::BuildCandidates" in candidates
    assert candidates.index("BuildCandidates") < candidates.index(
        "RecoveryAnchorReachedFor(slot)"
    )

    selector = geometry[geometry.index("SelectPathableDrudgeAnchor ="):geometry.index(
        "ExactRosterReSeparated =", geometry.index("SelectPathableDrudgeAnchor =")
    )]
    assert "drudge_anchor_source_unsafe" in selector
    assert "drudge_anchor_spacing_unsafe" in selector
    assert "drudge_anchor_lane_unsafe" in selector
    assert "StrictNativePath" in selector
    assert "tank || IsDynamicGroupRecoveryActive()" in selector
    assert "IsRecoveryCandidateSpacingSafe" in selector

    cache = selector[selector.index("auto cacheUsable"):selector.index(
        "if (cacheUsable())", selector.index("auto cacheUsable")
    )]
    assert "activeDynamicRecovery" in cache
    assert "SourceSafe" in cache
    assert "LaneSafe" in cache
    assert "IsRecoveryCandidateSpacingSafe" in cache
    assert "CandidateIndex >= candidates.size()" in cache
    assert "!activeDynamicRecovery" in cache

    assert "State.LastPathRejectReason.empty()" in actions
    assert '"drudge_lane_native_path_rejected" : State.LastPathRejectReason' in actions
    assert "ShouldInvalidateAnchorAfterPathRejection" in actions
    assert "NativePathFloorsValid(Bot, path)" in geometry
    assert "NativePathIsComplete(pathOk, path)" in geometry
    assert "BotWorldPopulationMgrNativePathValidation.h" in planner
    assert "NativePathFloorsValid(bot, candidatePath)" in planner
    assert "NativePathIsComplete(pathOk, path)" in planner
    assert "NativePathPointFloorValid" in path_validation
    assert "NativePathFloorsValid" in path_validation

    assert "ComputeStrictTankRecoveryPath" in recovery
    assert "ComputeRecoveryAnchorReached" in recovery
    assert "RecoveryPathPreservesTankSeparation" in recovery
    assert "ValidationRouteSplitNavigationMarginYards" in recovery
    assert "ValidationRouteSplitArrivalToleranceYards" in recovery
    assert "urand" not in header
    assert len(GEOMETRY.read_text(encoding="utf-8").splitlines()) <= 999
    assert len(recovery.splitlines()) <= 1000


def test_prepull_tank_fallback_keeps_declared_then_navigation_anchor_contract():
    geometry = GEOMETRY.read_text(encoding="utf-8")
    candidates = geometry[geometry.index("AnchorCandidatesFor ="):geometry.index(
        "AnchorCacheMatchesGeneration =", geometry.index("AnchorCandidatesFor =")
    )]
    selector = geometry[geometry.index("SelectPathableDrudgeAnchor ="):geometry.index(
        "ExactRosterReSeparated =", geometry.index("SelectPathableDrudgeAnchor =")
    )]
    assert "if (tankSlot && !CombatTankStagingActive())" in candidates
    assert candidates.index("candidates.emplace_back(navigation->X, navigation->Y)") \
        < candidates.index("RecoveryAnchorReachedFor(slot)")
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
    assert "landedTankRecovery" in selector
    assert "StrictTankRecoveryPath(candidatePoint.X, candidatePoint.Y, candidateZ)" in selector
    assert '"drudge_anchor_tank_path_geometry_rejected"' in selector
    assert "StrictNativePath(candidatePoint.X, candidatePoint.Y, candidateZ" in selector
    assert "float candidateZ = candidateAnchor->Z;" in selector
    assert "State.ValidationRouteDrudgeAnchorZ = candidateZ" in geometry
    assert "candidateAnchor->Z, &candidateZ" in selector
    assert "drudge_anchor_floor_rejected" in selector
    assert "std::fabs(*candidateZ - declaredZ) <= 4.0f" in native_anchor
    assert "hintZ + 2.0f" in native_anchor
    assert "GetHeight(phaseShift, x, y" in native_anchor
    assert "std::isfinite(resolved)" in native_anchor
