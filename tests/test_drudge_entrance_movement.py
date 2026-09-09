from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = (
    ROOT
    / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
    "BotWorldPopulationMgrValidationRouteDrudgeEntranceMovement.h"
)
PULL_SOURCE = (
    ROOT
    / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
    "BotWorldPopulationMgrValidationRouteDrudgeEntrancePull.cpp"
)
MOVEMENT_SOURCE = (
    ROOT
    / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
    "BotWorldPopulationMgrValidationRouteDrudgeEntranceMovement.cpp"
)


def test_drudge_entrance_movement_outcomes_are_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "drudge_entrance_movement.cpp"
    binary = tmp_path / "drudge_entrance_movement"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeEntranceMovement.h"
#include <cassert>
#include <cmath>
#include <string>

using namespace BotRaidDrudgeEntranceMovement;

int main()
{
    DestinationObservation destination;
    destination.Tank = true;
    assert(SelectLogicalDestination(destination)
        == LogicalDestination::Canonical);

    destination = {};
    destination.CanonicalSafe = true;
    destination.RecoveryAvailable = true;
    destination.RecoverySafe = true;
    assert(SelectLogicalDestination(destination)
        == LogicalDestination::Canonical);

    // Both Drudges reached the occupied fixed anchors. Fire30007 and
    // Affliction30008 must select their existing per-slot recovery anchors,
    // which are distinct points and ordinary native movement requests.
    float const source59X = -329.383f;
    float const source59Y = -96.494f;
    float const source60X = -327.234f;
    float const source60Y = -95.920f;
    struct Replay
    {
        float StartX;
        float StartY;
        float RecoveryX;
        float RecoveryY;
    };
    Replay const replays[] = {
        { -327.0f, -99.0f, -320.0f, -120.0f },
        { -329.0f, -99.0f, -315.0f, -118.0f },
    };
    for (Replay const& replay : replays)
    {
        assert(std::hypot(replay.StartX - source59X,
            replay.StartY - source59Y) < 18.0f);
        assert(std::hypot(replay.StartX - source60X,
            replay.StartY - source60Y) < 18.0f);
        assert(std::hypot(replay.RecoveryX - source59X,
            replay.RecoveryY - source59Y) >= 18.0f);
        assert(std::hypot(replay.RecoveryX - source60X,
            replay.RecoveryY - source60Y) >= 18.0f);

        destination = {};
        destination.RecoveryAvailable = true;
        destination.RecoverySafe = true;
        assert(SelectLogicalDestination(destination)
            == LogicalDestination::Recovery);
        float const distance = std::hypot(
            replay.RecoveryX - replay.StartX,
            replay.RecoveryY - replay.StartY);
        assert(ShouldSubmitNativeMovement(false, false, distance));
    }

    // A matching escape remains sticky when the canonical anchor becomes
    // safe during travel, then returns to the canonical assignment after
    // arrival. Repeated ticks at an unsafe canonical point do not select it.
    destination.CanonicalSafe = true;
    destination.MatchingRecoveryPathActive = true;
    destination.RecoveryArrived = false;
    assert(SelectLogicalDestination(destination)
        == LogicalDestination::Recovery);
    destination.RecoveryArrived = true;
    assert(SelectLogicalDestination(destination)
        == LogicalDestination::Canonical);
    destination.CanonicalSafe = false;
    assert(SelectLogicalDestination(destination)
        == LogicalDestination::Recovery);
    assert(!ShouldSubmitNativeMovement(true, false, 0.0f));

    destination = {};
    assert(SelectLogicalDestination(destination)
        == LogicalDestination::Unavailable);
    destination.RecoveryAvailable = true;
    assert(SelectLogicalDestination(destination)
        == LogicalDestination::Unavailable);

    Observation arrived;
    arrived.Arrived = true;
    assert(Classify(arrived) == Outcome::Arrived);

    Observation retained;
    retained.ActivePathRetained = true;
    retained.MeaningfulDistance = true;
    assert(Classify(retained) == Outcome::ActivePathRetained);
    retained.NativeMovementSubmitted = true;
    assert(Classify(retained) == Outcome::ActivePathRetained);

    Observation submitted;
    submitted.NativeMovementSubmitted = true;
    submitted.MeaningfulDistance = true;
    assert(Classify(submitted) == Outcome::Submitted);

    Observation higherPriority;
    higherPriority.HigherPriorityMovementActive = true;
    higherPriority.MeaningfulDistance = true;
    assert(Classify(higherPriority) == Outcome::HigherPriorityPending);
    // Preserve the arbitration receipt even if the request is at the same
    // point. It must never be relabeled as a native submission.
    higherPriority.MeaningfulDistance = false;
    assert(Classify(higherPriority) == Outcome::HigherPriorityPending);

    Observation rejected;
    rejected.MeaningfulDistance = true;
    assert(Classify(rejected) == Outcome::Rejected);

    Observation noProgress;
    noProgress.NoProgress = true;
    assert(Classify(noProgress) == Outcome::NoProgress);
    assert(Classify(Observation{}) == Outcome::NoProgress);
    noProgress.NativeMovementSubmitted = true;
    assert(Classify(noProgress) == Outcome::NoProgress);

    assert(std::string(Name(Outcome::HigherPriorityPending))
        == "higher_priority_movement_active");
    assert(std::string(Name(Outcome::NoProgress)) == "no_progress");
    assert(std::string(TraceResult(Outcome::Arrived, "move", "wait"))
        == "wait");
    assert(std::string(TraceResult(Outcome::Submitted, "move", "wait"))
        == "move");
    assert(std::string(TraceResult(Outcome::ActivePathRetained,
        "move", "wait")) == "drudge_entrance_native_path_retained");

    assert(!ShouldSubmitNativeMovement(false, true, 40.0f));
    assert(ShouldSubmitNativeMovement(false, false, 40.0f));
    // Canary83 was only 0.17 yd from its anchor but repeatedly resubmitted a
    // native path. Treat that observed tolerance as no progress.
    assert(!ShouldSubmitNativeMovement(false, false, 0.17f));
    assert(!ShouldSubmitNativeMovement(false, false, 0.1f));
    assert(!ShouldSubmitNativeMovement(false, false, 0.0f));

    assert(RequiresSourceUnionPath(false, true,
        "drudge_entrance_backline_escape_move"));
    assert(RequiresSourceUnionPath(false, false,
        "drudge_entrance_return_move"));
    assert(!RequiresSourceUnionPath(true, false,
        "drudge_entrance_return_move"));
    assert(!RequiresSourceUnionPath(false, false,
        "drudge_entrance_stage_move"));

    assert(IsExactDrudgePositionHold(
        "drudge_entrance_exact_roster_stage_wait"));
    assert(IsExactDrudgePositionHold("drudge_entrance_pull_owner_wait"));
    assert(!IsExactDrudgePositionHold("drudge_entrance_stage_wait"));
    assert(!IsExactDrudgePositionHold("drudge_entrance_native_path_rejected"));

    assert(ContinuePackCombat(Outcome::Arrived, true));
    assert(ContinuePackCombat(Outcome::ActivePathRetained, true));
    assert(ContinuePackCombat(Outcome::Submitted, true));
    assert(ContinuePackCombat(Outcome::HigherPriorityPending, true));
    assert(!ContinuePackCombat(Outcome::Rejected, true));
    // Only an explicitly safe logical arrival can admit no-progress combat.
    assert(ContinuePackCombat(Outcome::NoProgress, true, true));
    assert(!ContinuePackCombat(Outcome::NoProgress, true, false));
    assert(!ContinuePackCombat(Outcome::Rejected, true, true));
    assert(!ContinuePackCombat(Outcome::Submitted, false));
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


def test_recorded_backline_escape_preserves_source_union_path_floor(
    tmp_path: Path,
) -> None:
    source = tmp_path / "drudge_backline_egress.cpp"
    binary = tmp_path / "drudge_backline_egress"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeRecoveryCandidates.h"
#include <array>
#include <cassert>
#include <cmath>

using namespace BotRaidDrudgeRecoveryCandidates;

template <std::size_t PointCount>
bool PathAdmitted(Point2d const& start, Point2d const& end,
    std::array<Point2d, 4> const& sourceUnion,
    std::array<Point2d, PointCount> const& path, float minimum)
{
    std::array<float, 4> startDistances{};
    for (std::size_t source = 0; source < sourceUnion.size(); ++source)
        startDistances[source] = std::sqrt(
            DistanceSquared(start, sourceUnion[source]));

    std::size_t firstPoint = NearlyEqual(path.front(), start) ? 1 : 0;
    for (std::size_t pointIndex = firstPoint;
        pointIndex < path.size(); ++pointIndex)
        for (std::size_t source = 0; source < sourceUnion.size(); ++source)
            if (!PathPointPreservesSourceDistance(path[pointIndex],
                    sourceUnion[source], startDistances[source], minimum))
                return false;
    for (Point2d const& source : sourceUnion)
        if (std::sqrt(DistanceSquared(end, source)) < minimum)
            return false;
    return true;
}

int main()
{
    std::array<Point2d, 4> const sourceUnion{{
        { -329.383f, -96.494f },
        { -327.234f, -95.920f },
        { -298.833f, -50.349f },
        { -307.913f, -49.5694f },
    }};
    std::array<Point2d, 21> fireEgress{};
    std::array<Point2d, 21> afflictionEgress{};
    for (std::size_t step = 0; step < fireEgress.size(); ++step)
    {
        float const t = float(step) / 20.0f;
        fireEgress[step] = { -327.0f + 7.0f * t,
            -99.0f - 21.0f * t };
        afflictionEgress[step] = { -329.0f + 14.0f * t,
            -99.0f - 19.0f * t };
    }
    assert(PathAdmitted({ -327.0f, -99.0f },
        { -320.0f, -120.0f }, sourceUnion, fireEgress, 15.0f));
    assert(PathAdmitted({ -329.0f, -99.0f },
        { -315.0f, -118.0f }, sourceUnion, afflictionEgress, 15.0f));

    // Both return endpoints can satisfy the 18-yard policy check while a
    // native path bends through a live Drudge. The shared path-point gate,
    // now required on the return direction too, rejects that counterexample.
    std::array<Point2d, 4> const crossingUnion{{
        { -310.0f, -105.0f },
        { -350.0f, -80.0f },
        { -360.0f, -60.0f },
        { -370.0f, -50.0f },
    }};
    Point2d const recovery{ -320.0f, -120.0f };
    Point2d const canonical{ -327.0f, -99.0f };
    assert(std::sqrt(DistanceSquared(recovery, crossingUnion[0]))
        >= 18.0f);
    assert(std::sqrt(DistanceSquared(canonical, crossingUnion[0]))
        >= 18.0f);
    std::array<Point2d, 3> const crossingPath{{
        recovery, crossingUnion[0], canonical } };
    assert(!PathAdmitted(recovery, canonical, crossingUnion,
        crossingPath, 15.0f));
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

    pull_text = PULL_SOURCE.read_text(encoding="utf-8")
    movement_text = MOVEMENT_SOURCE.read_text(encoding="utf-8")
    assert "DeclaredRecoveryMemberAnchorFor(OneBasedSlot)" in pull_text
    assert "matchingRecoveryPathActive" in pull_text
    assert "true, sourceUnionRequired, &rejection" in movement_text
    assert "RequiresSourceUnionPath(" in movement_text
    assert '"drudge_entrance_backline_escape"' in movement_text
    assert "MoveBotToPointWithReferenceFloor" in movement_text
