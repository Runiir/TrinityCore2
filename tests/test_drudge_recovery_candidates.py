from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DRUDGE = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge"
GEOMETRY = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
RECOVERY = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeRecovery.cpp"
HEADER = DRUDGE / "BotRaidDrudgeRecoveryCandidates.h"
NATIVE_ANCHOR = DRUDGE / "BotRaidDrudgeNativeAnchor.h"
ACTIONS = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp"


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


def test_recovery_candidate_contract_is_landed_non_tank_only_and_native_strict():
    geometry = GEOMETRY.read_text(encoding="utf-8")
    recovery = RECOVERY.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    actions = ACTIONS.read_text(encoding="utf-8")

    candidates = geometry[geometry.index("AnchorCandidatesFor ="):geometry.index(
        "AnchorCacheMatchesGeneration =", geometry.index("AnchorCandidatesFor =")
    )]
    assert "!tankSlot && IsDynamicGroupRecoveryActive()" in candidates
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

    assert "ComputeStrictTankRecoveryPath" in recovery
    assert "RecoveryPathPreservesTankSeparation" in recovery
    assert "ValidationRouteSplitNavigationMarginYards" in recovery
    assert "ValidationRouteSplitArrivalToleranceYards" in recovery
    assert "urand" not in header
    assert len(GEOMETRY.read_text(encoding="utf-8").splitlines()) <= 999
    assert len(recovery.splitlines()) <= 1000


def test_dynamic_fan_candidate_is_grounded_before_exact_native_path_admission():
    geometry = GEOMETRY.read_text(encoding="utf-8")
    native_anchor = NATIVE_ANCHOR.read_text(encoding="utf-8")
    selector = geometry[geometry.index("for (size_t candidateIndex = 0;"):geometry.index(
        "State.ValidationRouteDrudgeAnchorX =", geometry.index(
            "for (size_t candidateIndex = 0;"
        )
    )]

    assert "ResolveDynamicCandidateZ" in selector
    assert "!tank && IsDynamicGroupRecoveryActive() && candidateIndex > 0" in selector
    assert "StrictNativePath(candidatePoint.X, candidatePoint.Y, candidateZ" in selector
    assert "float candidateZ = candidateAnchor->Z;" in selector
    assert "State.ValidationRouteDrudgeAnchorZ = candidateZ" in geometry
    assert "candidateAnchor->Z, &candidateZ" in selector
    assert "drudge_anchor_floor_rejected" in selector
    assert "std::fabs(*candidateZ - declaredZ) <= 4.0f" in native_anchor
    assert "hintZ + 2.0f" in native_anchor
    assert "GetHeight(phaseShift, x, y" in native_anchor
    assert "std::isfinite(resolved)" in native_anchor
