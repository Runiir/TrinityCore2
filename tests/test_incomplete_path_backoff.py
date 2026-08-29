from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HEADER = (
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementPathSelection.h"
)
PLANNER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementPlanner.cpp"


def test_incomplete_path_backoff_is_deterministic_and_skips_edge(tmp_path):
    source = tmp_path / "incomplete_path_backoff.cpp"
    binary = tmp_path / "incomplete_path_backoff"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrMovementPathSelection.h"
#include <cassert>
#include <vector>

struct Point
{
    float x;
    float y;
    float z;
};

int main()
{
    using BotWorldMovement::SelectIncompletePathBackoffCandidate;
    std::vector<Point> const path{
        { 0.0f, 0.0f, 0.0f },
        { 4.0f, 0.0f, 0.0f },
        { 8.0f, 0.0f, 0.0f },
        { 10.0f, 0.0f, 0.0f },
    };
    Point const edge{ 10.0f, 0.0f, 0.0f };

    Point selected{};
    unsigned visits = 0;
    bool const found = SelectIncompletePathBackoffCandidate(
        path, edge, 3.0f,
        [&](Point const& point, float pathClearance, float directClearance)
        {
            ++visits;
            assert(pathClearance >= 3.0f);
            assert(directClearance >= 3.0f);
            selected = point;
            return true;
        });
    assert(found);
    assert(visits == 1);
    assert(selected.x == 4.0f);
    assert(selected.x != edge.x);

    Point second{};
    bool const deterministic = SelectIncompletePathBackoffCandidate(
        path, edge, 3.0f,
        [&](Point const& point, float, float)
        {
            second = point;
            return true;
        });
    assert(deterministic && second.x == selected.x);

    unsigned rejectedVisits = 0;
    bool const fallback = SelectIncompletePathBackoffCandidate(
        path, edge, 3.0f,
        [&](Point const& point, float, float)
        {
            ++rejectedVisits;
            if (point.x == 4.0f)
                return false;
            selected = point;
            return true;
        });
    assert(fallback);
    assert(rejectedVisits == 2);
    assert(selected.x == 0.0f);

    std::vector<Point> const shortPath{
        { 8.5f, 0.0f, 0.0f }, { 10.0f, 0.0f, 0.0f }
    };
    assert(!SelectIncompletePathBackoffCandidate(
        shortPath, edge, 3.0f,
        [](Point const&, float, float) { return true; }));
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


def test_planner_requires_complete_native_proof_for_backoff_segments():
    planner = PLANNER.read_text(encoding="utf-8")
    assert "SelectIncompletePathBackoffCandidate" in planner
    assert "completeNativePathToPoint" in planner
    assert "diagnoseCompleteNativePath" in planner
    assert "DiagnoseCompleteNativePathProof" in planner
    assert "NativePathFloorObservationBlocksCompleteProof" in planner
    assert '"native_partial_path_backoff"' in planner
    assert '"native_walkable_step_backoff"' in planner
    assert "PATHFIND_INCOMPLETE" in planner
    assert "TeleportTo(" not in planner
    assert "NearTeleportTo(" not in planner
    assert "MoveJump(" not in planner
    assert len(planner.splitlines()) <= 1000
    assert len(HEADER.read_text(encoding="utf-8").splitlines()) <= 1000
