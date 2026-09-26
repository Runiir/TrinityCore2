"""The swimmer's transport stages (Float, Swim, Hop, Emerge).

Nefarian's End phase 2 sinks GO 207834's floor 10 yards under the magma while
its pillar tops stay 0.29 yards above it; the raid swims up and hops onto the
pillar tops (user raid experience 2026-09-26). These checks cover the pure
jump and depth rules (BotValidationRouteNativeLiquid.h) and keep the executor
lawful: it submits only the client's own movement reports, a swim spline and
the client's jump, and never moves a unit itself.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
EXECUTOR = BOTS / "BotWorldPopulationMgrNativePathTransportLiquid.cpp"

PROGRAM = r'''
#include "Bots/BotValidationRouteNativeLiquid.h"
#include <cstdio>
using namespace BotValidationRouteNativeLiquid;
static int failures = 0;
#define CHECK(c, m) do { if (!(c)) { std::fprintf(stderr, "FAIL %d: %s\n", __LINE__, m); ++failures; } } while (0)
int main()
{
    CHECK(std::fabs(JumpApexYards() - 1.6405f) < 0.001f, "the client's jump apex");
    JumpPlan const hop = PlanJump(2.6f, 1.25f, 7.0f);
    CHECK(hop.Ok && hop.SpeedXY <= 7.0f, "a 1.25-yard rise over 2.6 yards is a jump");
    CHECK(std::fabs(JumpFeetZ(0.0f, hop.AirTimeSeconds) - 1.25f) < 1e-3f, "it lands at the rise");
    CHECK(!PlanJump(2.0f, 1.7f, 7.0f).Ok
        && PlanJump(2.0f, 1.7f, 7.0f).Reason == "liquid_hop_rise_beyond_jump_apex",
        "no jump above the apex");
    CHECK(!PlanJump(6.0f, 1.25f, 7.0f).Ok
        && PlanJump(6.0f, 1.25f, 7.0f).Reason == "liquid_hop_distance_beyond_run_speed",
        "no jump faster than the run speed");
    CHECK(FloatDepthReached(2.7713f, 2.7713f - 1.2f, 1.2f), "1.2 yards deep floats");
    CHECK(!FloatDepthReached(2.7713f, 2.7713f - 0.8f, 1.2f), "0.8 yards deep wades");
    CHECK(InLiquid(0x04) && InLiquid(0x08) && !InLiquid(0x01) && !InLiquid(0x02),
        "in or under the liquid, not above it or walking on it");
    return failures ? 1 : 0;
}
'''


def test_liquid_rules(tmp_path: Path) -> None:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(PROGRAM)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common"),
                    str(source), "-o", str(binary)], check=True)
    result = subprocess.run([str(binary)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


TRAJECTORY = r'''
#include "Bots/BotValidationRouteNativeLiquid.h"
#include <cmath>
#include <cstdio>
using namespace BotValidationRouteNativeLiquid;
static int failures = 0;
#define CHECK(c, m) do { if (!(c)) { std::fprintf(stderr, "FAIL %d: %s\n", __LINE__, m); ++failures; } } while (0)

// Movement::MoveSpline, written out independently from its source (the test
// below pins those source lines): the duration of one linear segment, and
// the position at time t (ms) of a parabolic spline with the vertical
// acceleration MoveJumpWithGravity sets.
static int32 MoveSplineDuration(float x0, float y0, float z0, float x1, float y1, float z1,
    float velocity)
{
    float const segLength = std::sqrt((x1 - x0) * (x1 - x0) + (y1 - y0) * (y1 - y0)
        + (z1 - z0) * (z1 - z0));              // SplineBase::SegLengthLinear
    float const velocityInv = 1000.f / velocity; // CommonInitializer
    int32 time = 1;                             // minimal_duration
    time += (segLength * velocityInv);
    return time;
}

static float MoveSplineZ(float z0, float z1, int32 duration, int32 timePoint, float gravity)
{
    float const u = float(timePoint) / float(duration);  // evaluate_percent, one segment
    float el = z0 + (z1 - z0) * u;
    float const passed = float(timePoint) / 1000.f;
    float const total = float(duration) / 1000.f;
    el += (total - passed) * 0.5f * gravity * passed;    // computeParabolicElevation
    return el;
}

int main()
{
    // The review's case: 2.6 yards out, 1.25 up.
    SplineJump const review = PlanSplineJump(2.6f, 1.25f, 7.0f);
    CHECK(review.Ok, "the review's hop is a jump");
    CHECK(review.DurationMs == 613 || review.DurationMs == 614, "its duration is the air time");
    CHECK(review.LaunchVerticalSpeed <= JumpVelocity + 1e-3f
        && review.LaunchVerticalSpeed > JumpVelocity - 0.05f, "launched at the client's speed");
    int checked = 0;
    for (float h = 0.5f; h <= 4.5f; h += 0.25f)
        for (float rise = -1.0f; rise <= 1.6f; rise += 0.1f)
        {
            SplineJump const jump = PlanSplineJump(h, rise, 7.0f);
            if (!jump.Ok)
                continue;
            ++checked;
            // MoveSpline computes the same duration from the 3D segment.
            int32 const duration = MoveSplineDuration(0.f, 0.f, 0.f, h, 0.f, rise, jump.Velocity);
            CHECK(duration == jump.DurationMs, "MoveSpline's duration is the planned one");
            JumpPlan const ballistic = PlanJump(h, rise, 1000.f);
            CHECK(duration <= int32(std::ceil(ballistic.AirTimeSeconds * 1000.f)), "no longer than the jump");
            CHECK(jump.LaunchVerticalSpeed <= JumpVelocity + 1e-3f, "never faster than the client's jump");
            CHECK(jump.SpeedXY <= 7.0f, "never faster than the run speed");
            // The arc the executor sweeps is the arc MoveSpline runs.
            for (int32 t = 0; t <= duration; t += 7)
            {
                float const executed = MoveSplineZ(0.f, rise, duration, t, JumpGravity);
                float const planned = SplineJumpFeetZ(0.f, rise, jump.DurationSeconds, float(t) / 1000.f);
                CHECK(std::fabs(executed - planned) < 1e-3f, "the checked arc is the executed arc");
            }
            // And it is the client's jump launched at most at JumpVelocity:
            // never above the ballistic arc of the same launch time.
            float const early = MoveSplineZ(0.f, rise, duration, 50, JumpGravity);
            CHECK(early <= JumpFeetZ(0.f, 0.05f) + 1e-3f, "not above the client's arc");
        }
    CHECK(checked > 200, "a grid of hops");
    CHECK(!PlanSplineJump(2.0f, 1.7f, 7.0f).Ok, "no jump above the apex");
    return failures ? 1 : 0;
}
'''


def test_hop_spline_is_the_checked_trajectory(tmp_path: Path) -> None:
    source = tmp_path / "trajectory.cpp"
    binary = tmp_path / "trajectory"
    source.write_text(TRAJECTORY)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common"),
                    str(source), "-o", str(binary)], check=True)
    result = subprocess.run([str(binary)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_movespline_formulas_the_mirror_depends_on() -> None:
    spline = ROOT / "src/server/game/Movement/Spline"
    move = (spline / "MoveSpline.cpp").read_text()
    assert "minimal_duration = 1" in move
    assert "CommonInitializer(float _velocity) : velocityInv(1000.f/_velocity), time(minimal_duration) { }" in move
    assert "time += (s.SegLength(i) * velocityInv);" in move
    assert "el += (t_durationf - t_passedf) * 0.5f * vertical_acceleration * t_passedf;" in move
    assert "vertical_acceleration = args.vertical_acceleration;" in move
    assert "return (points[index] - points[index+1]).length();" in (spline / "Spline.cpp").read_text()
    motion = (ROOT / "src/server/game/Movement/MotionMaster.cpp").read_text()
    body = motion[motion.index("void MotionMaster::MoveJumpWithGravity("):]
    body = body[:body.index("\n}\n")]
    assert "init.SetParabolicVerticalAcceleration(gravity, 0);" in body
    assert "init.SetVelocity(speedXY);" in body
    executor = EXECUTOR.read_text()
    assert "Liquid::PlanSplineJump(" in executor
    assert "jump.Velocity, Liquid::JumpGravity)" in executor
    assert "Liquid::SplineJumpFeetZ(" in executor
    assert "bot->movespline->Duration() != jump.DurationMs" in executor


def test_surface_executor_routes_the_swimmer_stages() -> None:
    surface = (BOTS / "BotWorldPopulationMgrNativePathTransportSurface.cpp").read_text()
    for stage in ("Float", "Swim", "Hop", "Emerge"):
        assert f"TransportSurfaceMove::Stage::{stage}" in surface
    assert "BotTransportLiquidMovement::Execute(bot, action)" in surface
    intent = (BOTS / "BotNativeActionIntent.h").read_text()
    assert "enum class Stage : uint8 { Walk, StepOff, Fall, Land, Float, Swim, Hop, Emerge };" in intent
    cmake = (ROOT / "src/server/game/CMakeLists.txt").read_text()
    assert "Bots/BotWorldPopulationMgrNativePathTransportLiquid.cpp" in cmake


def test_liquid_executor_is_lawful() -> None:
    text = EXECUTOR.read_text()
    code = re.sub(r"//[^\n]*", "", text)
    for forbidden in ("Relocate(", "NearTeleportTo", "TeleportTo", "UpdatePosition(",
                      "SetPosition", "AddPassenger", "RemovePassenger", "CastSpell",
                      "AddAura", "DealDamage", "SetHealth"):
        assert forbidden not in code, forbidden
    # Its only side effects: client reports, a swim spline, the client's jump.
    assert code.count("ReportSwimState(") == 2
    assert code.count("LaunchMoveSpline(") == 1
    assert code.count("MoveJumpWithGravity(") == 1
    assert "Liquid::JumpGravity" in code and "bot->GetSpeed(MOVE_RUN)" in code
    boarding = (BOTS / "BotWorldPopulationMgrValidationRouteBoardingAction.cpp").read_text()
    body = boarding[boarding.index("bool ReportSwimState("):]
    body = body[:body.index("\n}\n")]
    assert "HandleMovementOpcode(" in body and "MSG_MOVE_START_SWIM" in body
    assert "MSG_MOVE_STOP_SWIM" in body and "Relocate(x, y, z, o)" in body


def test_hop_in_flight_keeps_its_lanes() -> None:
    """A submitted hop in the air answers its own stage (Hop) and a landing
    report (Emerge) with progress, a committed outcome, so the arbitration
    keeps the hop's movement, GCD and cast lanes: no heal in the same tick
    reaches TryCastFriendlySpell, which stops a member before a cast-time
    spell and would end the jump over the magma."""
    code = re.sub(r"//[^\n]*", "", EXECUTOR.read_text())
    assert "bot->movespline->isParabolic()" in code
    hop = code[code.index("Outcome ExecuteHop("):code.index("Outcome ExecuteEmerge(")]
    assert hop.index("HopInFlight(bot)") < hop.index("Busy(bot)")
    assert 'Outcome::Progressed("native_liquid_hop_in_flight")' in hop
    emerge = code[code.index("Outcome ExecuteEmerge("):]
    assert emerge.index("HopInFlight(bot)") < emerge.index("Busy(bot)")
    assert 'Outcome::Progressed("native_liquid_emerge_hop_in_flight")' in emerge
    arbiter = (BOTS / "BotActionArbiter.h").read_text()
    assert "return { Disposition::Committed, std::string(reason), Phase::Progressed, 0 };" in arbiter
    assert "_lastResolution.ClaimedResources |= candidate.RequiredResources;" in arbiter



def test_emerge_reports_the_actual_position() -> None:
    """The emerge report is made where the swimmer is (third re-review): no
    height of its own, no lift onto a floor that passed the feet. Nothing
    native moves a unit that is not a registered passenger, so the report
    must not either."""
    code = re.sub(r"//[^\n]*", "", EXECUTOR.read_text())
    emerge = code[code.index("Outcome ExecuteEmerge("):]
    assert "ReportSwimState(bot, submerged, transport)" in emerge
    assert "floorZ" not in emerge and "std::max(" not in emerge
    boarding = (BOTS / "BotWorldPopulationMgrValidationRouteBoardingAction.cpp").read_text()
    body = boarding[boarding.index("bool ReportSwimState("):]
    body = body[:body.index("\n}\n")]
    assert "MovementInfo report = CurrentPositionReport(bot);" in body
    assert "m_positionZ" not in body and "Relocate(bot" not in body
    assert "float z = bot->GetPositionZ();" in body
