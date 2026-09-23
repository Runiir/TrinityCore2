from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRUDGE = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge"
MINIMUM = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeMinimumDistance.cpp"
GEOMETRY = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
EXIT_HEADER = DRUDGE / "BotRaidDrudgeMinimumDistanceExit.h"


def compile_and_run(tmp_path: Path, name: str, body: str) -> None:
    source = tmp_path / f"{name}.cpp"
    binary = tmp_path / name
    source.write_text(body, encoding="utf-8")
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-I", str(ROOT / "src/server/game"), str(source), "-o", str(binary)],
        check=True, cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_single_source_exit_tries_both_perpendicular_fallbacks(tmp_path: Path) -> None:
    # sq2: Mgwdpsb stood 1.5 yd from the last, enraged Drudge for four
    # Whirlwind ticks with no move and no cast.  With one source the exit
    # tried exactly one direction, and one rejected path meant a hold.
    compile_and_run(tmp_path, "single_source", r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeMinimumDistanceExit.h"
#include <cassert>
#include <cmath>

using namespace BotRaidDrudgeMinimumDistanceExit;

bool Near(float left, float right) { return std::fabs(left - right) < 0.001f; }

int main()
{
    Point const mage{ -327.8f, -102.9f };
    Point const drudge{ -327.2f, -101.6f };
    size_t primary = 99;
    std::vector<Direction> const directions = CandidateDirections(mage, { drudge }, &primary);
    assert(directions.size() == 3);
    // Only straight-away is original; both sideways exits are fallbacks.
    assert(primary == 1);
    float const length = std::hypot(mage.X - drudge.X, mage.Y - drudge.Y);
    float const awayX = (mage.X - drudge.X) / length;
    float const awayY = (mage.Y - drudge.Y) / length;
    // Straight away from the source is still preferred.
    assert(Near(directions[0].first, awayX) && Near(directions[0].second, awayY));
    // Then both sideways exits, perpendicular to the bot-source axis.
    for (size_t index = 1; index < 3; ++index)
    {
        assert(Near(std::hypot(directions[index].first, directions[index].second), 1.0f));
        assert(Near(directions[index].first * awayX + directions[index].second * awayY, 0.0f));
    }
    assert(Near(directions[1].first, -directions[2].first));
    assert(Near(directions[1].second, -directions[2].second));

    // A bot exactly on its only source has no axis: try the map axes.
    std::vector<Direction> const onTop = CandidateDirections(drudge, { drudge }, &primary);
    assert(onTop.size() == 4);
    assert(primary == 0);
    assert(CandidateDirections(mage, {}).empty());
}
''')


def test_multi_source_exit_directions_are_unchanged(tmp_path: Path) -> None:
    # The legacy inline generator, copied from the pre-split module.  Two or
    # more sources must produce exactly the same directions in the same order.
    compile_and_run(tmp_path, "multi_source", r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeMinimumDistanceExit.h"
#include <cassert>
#include <cmath>

using namespace BotRaidDrudgeMinimumDistanceExit;

std::vector<Direction> Legacy(Point bot, std::vector<Point> const& sources)
{
    std::vector<std::pair<float, float>> directions;
    auto addDirection = [&directions](float x, float y)
    {
        float length = std::hypot(x, y);
        if (length <= 0.001f)
            return;
        x /= length;
        y /= length;
        for (auto const& direction : directions)
            if (direction.first * x + direction.second * y >= 0.999f)
                return;
        directions.emplace_back(x, y);
    };
    float centroidX = 0.0f;
    float centroidY = 0.0f;
    for (Point const& source : sources)
    {
        centroidX += source.X;
        centroidY += source.Y;
        addDirection(bot.X - source.X, bot.Y - source.Y);
    }
    centroidX /= float(sources.size());
    centroidY /= float(sources.size());
    addDirection(bot.X - centroidX, bot.Y - centroidY);
    for (size_t left = 0; left < sources.size(); ++left)
        for (size_t right = left + 1; right < sources.size(); ++right)
        {
            float pairX = sources[right].X - sources[left].X;
            float pairY = sources[right].Y - sources[left].Y;
            addDirection(-pairY, pairX);
            addDirection(pairY, -pairX);
        }
    return directions;
}

int main()
{
    std::vector<std::vector<Point>> const packs = {
        { { -318.0f, -78.8f }, { -311.7f, -65.4f } },
        { { -318.0f, -78.8f }, { -318.0f, -78.8f } },
        { { 0.0f, 0.0f }, { 10.0f, 0.0f }, { 5.0f, 8.0f } },
    };
    std::vector<Point> const bots = { { -318.7f, -80.1f }, { -305.7f, -73.1f }, { 5.0f, 1.0f } };
    for (auto const& pack : packs)
        for (Point const& bot : bots)
        {
            size_t primary = 0;
            std::vector<Direction> const current = CandidateDirections(bot, pack, &primary);
            std::vector<Direction> const legacy = Legacy(bot, pack);
            assert(current.size() == legacy.size());
            // With two or more sources nothing is a fallback.
            assert(primary == legacy.size());
            for (size_t index = 0; index < legacy.size(); ++index)
                assert(current[index] == legacy[index]);
        }
}
''')


def test_exit_attempt_names_every_rejection(tmp_path: Path) -> None:
    compile_and_run(tmp_path, "exit_attempt", r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeMinimumDistanceExit.h"
#include <cassert>

using namespace BotRaidDrudgeMinimumDistanceExit;

int main()
{
    Attempt attempt;
    attempt.Sources = 1;
    attempt.Directions = 3;
    attempt.Tried = 3;
    attempt.LastPathType = 0x20;
    attempt.Reject(Rejection::PathType);
    attempt.Reject(Rejection::EndpointMismatch);
    attempt.Reject(Rejection::UnsafePath);
    assert(attempt.Rejected() == 3);
    attempt.Reject(Rejection::LaneUnsafe);
    attempt.Reject(Rejection::PathFloorGap);
    assert(attempt.Rejected() == 5);
    assert(attempt.ToString(false) == "exit_failed:sources=1,directions=3,tried=3,"
        "path_type=1,endpoint_mismatch=1,unsafe_path=1,lane_unsafe=1,"
        "path_floor_gap=1,lease_refused=0,move_rejected=0,last_path_type=32");

    attempt.Reject(Rejection::LeaseRefused);
    attempt.LeaseOwner = 6;
    attempt.LeasePriority = 120;
    attempt.Reject(Rejection::MoveRejected);
    assert(attempt.Rejected() == 7);
    std::string const text = attempt.ToString(true);
    assert(text.rfind("exit_started:", 0) == 0);
    assert(text.find(",lease_refused=1,move_rejected=1,") != std::string::npos);
    assert(text.find(",lease_owner=6,lease_priority=120") != std::string::npos);
}
''')


def test_fallback_exit_keeps_drudge_home_lanes_and_the_next_encounter(tmp_path: Path) -> None:
    compile_and_run(tmp_path, "fallback_lane", r"""
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeMinimumDistanceExit.h"
#include <cassert>

using namespace BotRaidDrudgeMinimumDistanceExit;

FallbackLaneInput Lane(Point end)
{
    FallbackLaneInput lane;
    lane.Start = { 0.0f, 0.0f };
    lane.End = end;
    lane.Path = { { 0.0f, 0.0f }, { end.X / 2.0f, end.Y / 2.0f }, end };
    lane.MinimumDistance = 15.0f;
    return lane;
}

int main()
{
    // A sideways exit far from every Drudge home and no next boss: safe.
    FallbackLaneInput lane = Lane({ 0.0f, 17.0f });
    lane.SourceHomes = { { 40.0f, 0.0f } };
    assert(EvaluateFallbackLane(lane) == FallbackLane::Safe);

    // Ending inside a Drudge home radius is the charge lane: unsafe, like
    // StrictNativePath's SourceUnionSafe endpoint check.
    lane = Lane({ 0.0f, 17.0f });
    lane.SourceHomes = { { 0.0f, 25.0f } };
    assert(EvaluateFallbackLane(lane) == FallbackLane::SourceHomeUnsafe);

    // A path that cuts through the home radius on its way out is unsafe too.
    lane = Lane({ 30.0f, 0.0f });
    lane.Path = { { 0.0f, 0.0f }, { 15.0f, 20.0f }, { 30.0f, 0.0f } };
    lane.SourceHomes = { { 15.0f, 28.0f } };
    assert(EvaluateFallbackLane(lane) == FallbackLane::SourceHomeUnsafe);

    // Never approach the next encounter's boss; moving away is fine.
    lane = Lane({ 0.0f, 17.0f });
    lane.NextBossKnown = true;
    lane.NextBoss = { 0.0f, 80.0f };
    assert(EvaluateFallbackLane(lane) == FallbackLane::NextEncounterUnsafe);
    lane = Lane({ 0.0f, -17.0f });
    lane.NextBossKnown = true;
    lane.NextBoss = { 0.0f, 80.0f };
    assert(EvaluateFallbackLane(lane) == FallbackLane::Safe);
}
""")


def test_admitted_exit_keeps_its_move_until_the_safe_distance(tmp_path: Path) -> None:
    # Review of this batch: once past the radius the exit returned false, the
    # next cast-time spell stopped the move and parked the bot at the edge.
    compile_and_run(tmp_path, "exit_progress", r"""
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeMinimumDistanceExit.h"
#include <cassert>

using namespace BotRaidDrudgeMinimumDistanceExit;

int main()
{
    ExitProgress progress;
    progress.MechanicLease = true;
    progress.Moving = true;
    progress.BotSourceDistance = 15.4f;
    progress.DestinationSourceDistance = 17.5f;
    progress.SafeDistance = 17.0f;
    assert(ContinueAdmittedExit(progress));
    // Arrived within the tolerance of the safe distance.
    progress.BotSourceDistance = 16.6f;
    assert(!ContinueAdmittedExit(progress));
    progress.BotSourceDistance = 15.4f;
    // Stopped, another owner, or a destination the Drudge has since reached.
    progress.Moving = false;
    assert(!ContinueAdmittedExit(progress));
    progress.Moving = true;
    progress.MechanicLease = false;
    assert(!ContinueAdmittedExit(progress));
    progress.MechanicLease = true;
    progress.DestinationSourceDistance = 12.0f;
    assert(!ContinueAdmittedExit(progress));
}
""")


def test_rotation_yields_instead_of_stopping_a_protected_move(tmp_path: Path) -> None:
    source = tmp_path / "protected_move.cpp"
    binary = tmp_path / "protected_move"
    source.write_text(r"""
#include "Bots/BotCastWhileMoving.h"
#include <cassert>

class SpellInfo
{
};

struct Caster
{
    bool Covered = false;
    bool HasAuraTypeWithAffectMask(AuraType, SpellInfo const*) const { return Covered; }
};

int main()
{
    SpellInfo fireball;
    Caster uncovered;
    Caster covered{ true };
    // A protected move yields an uncovered cast-time spell instead of stopping.
    assert(BotCastWhileMoving::YieldsToProtectedMovement(&uncovered, &fireball, true, true, true));
    // Ordinary combat movement keeps the executor's stop-and-cast.
    assert(!BotCastWhileMoving::YieldsToProtectedMovement(&uncovered, &fireball, true, true, false));
    // Instants, standing bots and native cast-while-moving are unaffected.
    assert(!BotCastWhileMoving::YieldsToProtectedMovement(&uncovered, &fireball, false, true, true));
    assert(!BotCastWhileMoving::YieldsToProtectedMovement(&uncovered, &fireball, true, false, true));
    assert(!BotCastWhileMoving::YieldsToProtectedMovement(&covered, &fireball, true, true, true));
}
""", encoding="utf-8")
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-I", str(ROOT / "src/server/game"),
         "-I", str(ROOT / "src/server/game/Spells/Auras"),
         "-I", str(ROOT / "src/common"),
         "-I", str(ROOT / "src/common/Utilities"),
         "-I", str(ROOT / "src/server/game/Entities/Object"),
         str(source), "-o", str(binary)],
        check=True, cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_minimum_distance_exit_is_its_own_module_and_traces_rejections() -> None:
    minimum = MINIMUM.read_text(encoding="utf-8")
    geometry = GEOMETRY.read_text(encoding="utf-8")
    for module in (MINIMUM, GEOMETRY, EXIT_HEADER):
        assert len(module.read_text(encoding="utf-8").splitlines()) < 1000
    assert "bool DrudgeLaneContext::TryMinimumDistance(" in minimum
    assert "bool DrudgeLaneContext::TryMinimumDistance(" not in geometry
    assert "DrudgeLaneContext::PhaseResult DrudgeLaneContext::BuildAnchorPolicies()" in geometry

    assert "BotRaidDrudgeMinimumDistanceExit::CandidateDirections(" in minimum
    assert "addDirection" not in minimum
    loop = minimum[minimum.index("for (size_t directionIndex = 0; directionIndex < directions.size(); ++directionIndex)"):]
    for rejection in ("PathType", "EndpointMismatch", "UnsafePath", "LaneUnsafe",
                      "PathFloorGap", "LeaseRefused", "MoveRejected"):
        assert f"attempt.Reject(Rejection::{rejection});" in loop
    # Only fallback directions take the extra lane and floor checks, before
    # any movement is submitted.
    fallback = loop.index("if (directionIndex >= primaryDirections)")
    assert fallback < loop.index("Manager.MoveBotToPoint")
    fallback_checks = loop[fallback:loop.index("Manager.MoveBotToPoint")]
    assert "BotWorldMovement::NativePathFloorsValid(Bot, path, candidateZ, true)" in fallback_checks
    assert "EvaluateFallbackLane(lane)" in fallback_checks
    assert "GetHomePosition()" in minimum
    assert 'route[nextRouteIndex].Kind == "boss"' in minimum
    # A kept lease refuses every direction alike: stop searching.
    refused = loop[loop.index("attempt.Reject(Rejection::LeaseRefused);"):]
    assert refused.index("break;") < refused.index("attempt.Reject(Rejection::MoveRejected);")
    # A kept lease is recognised from this submission only, and the earlier
    # diagnostic survives when the executor does not replace it.
    submit = loop[loop.index("previousRecoveryResult"):loop.index("if (moved)\n            break;")]
    assert "State.LastRecoveryResult.clear();" in submit
    assert '"higher_priority_movement_active"' in submit
    assert "State.LastRecoveryResult = previousRecoveryResult;" in submit
    assert "State.MovementLease.MovementOwner" in loop
    # The summary reaches the trace through the recovery fields before the
    # event that records the trace entry; the event results are unchanged.
    publish = minimum.index('State.LastRecoveryMode = "minimum_distance_exit";')
    assert publish < minimum.index('"validation_route_mechanic", source,')
    assert "State.LastRecoveryResult = attempt.ToString(moved);" in minimum
    assert '"minimum_distance_exit_started" : "minimum_distance_exit_failed"' in minimum
    assert '"move_to_minimum_distance" : "hold_minimum_distance_exit_failed"' in minimum
    # Past the radius the exit still owns its move until the safe distance,
    # refreshing the same Mechanic destination, then yields to the rotation.
    outside = minimum[minimum.index("if (sourceDistance >= minimumDistance)"):]
    outside = outside[:outside.index("return false;")]
    assert "ContinueAdmittedExit(progress)" in outside
    assert "Manager.MoveBotToPoint(State, Bot, lease.X, lease.Y, lease.Z," in outside
    assert "BotMovementArbitration::Owner::Mechanic" in outside
    # The rotation never stops a protected lease to submit a cast-time spell.
    execution = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatExecution.cpp").read_text()
    guard = execution.index("BotCastWhileMoving::YieldsToProtectedMovement(")
    assert guard < execution.index("executor.ExecuteCombat(bot, bot, action)")
    assert "HasProtectedMovementLease(state, bot, NowMs())" in execution[guard:guard + 400]
    assert ">= uint8(BotMovementArbitration::Priority::Mechanic)" in execution
    # Movement ownership and path admission are unchanged by the split.
    assert "BotMovementArbitration::Priority::Mechanic" in minimum
    assert "path.SetUseStraightPath(true)" in minimum
    assert "DrudgeMinimumDistanceEndpointToleranceYards" in minimum
    assert "std::min(startDistance, minimumDistance) - 0.25f" in minimum
