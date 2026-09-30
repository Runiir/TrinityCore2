"""A refused or failed spline launch leaves the unit's current spline in its own frame.

Round-3 v4 review (P2, packet movement_v4): MoveSplineInit::Launch assigned
`move_spline.onTransport = transport` before it validated the arguments and
before ProvePassengerEffectSpline could refuse a passenger's fall or jump. A
refusal stops the unit (Unit::StopMoving -> Unit::UpdateSplinePosition), which
reads onTransport to decide whether the old spline's points are transport
offsets: a live WORLD-frame spline (the unit boarded a transport while it ran)
read as offsets moved the unit off the deck, (101, 202, 12) to (201, 402, 22)
on a transport at (100, 200, 10). A failed Validate left the same wrong flag on
the old spline for the next update.

Now every proof and the validation come first and the frame flag changes only
as the spline is initialized, so on any refusal the unit is exactly where it
was.

The program runs the real Movement::MoveSpline (MoveSpline.cpp, Spline.cpp and
MovementUtil.cpp) and the verbatim text of Unit::UpdateSplinePosition
(UnitSplinePosition.cpp) against a stand-in unit and transport. Which stage of
Launch has already assigned onTransport when it fails is read from the order of
the real Launch source, so the program's outcome follows the code it pins.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from tests.test_bot_native_fall_spline_state import STUB_CREATURE, STUB_LOG


ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "src/server/game"
LAUNCH = GAME / "Movement/Spline/MoveSplineInit.cpp"
SPLINE_POSITION = GAME / "Entities/Unit/UnitSplinePosition.cpp"

PROGRAM = r'''
#include "MoveSpline.h"
#include "MoveSplineInitArgs.h"
#include <G3D/Matrix4.h>
#include <G3D/Vector3.h>
#include <G3D/Vector4.h>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <string>

namespace Trinity
{
void Assert(char const*, int, char const*, char const*) { std::abort(); }
void Assert(char const*, int, char const*, char const*, char const*, ...) { std::abort(); }
void Abort(char const*, int, char const*) { std::abort(); }
void Abort(char const*, int, char const*, char const*, ...) { std::abort(); }
}
G3D::Matrix4::Matrix4(float, float, float, float, float, float, float, float,
    float, float, float, float, float, float, float, float) { }
G3D::Vector4 G3D::Vector4::operator*(const G3D::Matrix4&) const { return G3D::Vector4(); }

static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL %d %s\n", __LINE__, #c); ++failures; } } while (0)

// Stand-ins for what Unit::UpdateSplinePosition touches.
constexpr std::uint32_t UNIT_STATE_CANNOT_TURN = 0x00020000;
struct Position
{
    float m_positionX = 0.0f, m_positionY = 0.0f, m_positionZ = 0.0f, Orientation = 0.0f;
    void SetOrientation(float o) { Orientation = o; }
};
// An unrotated transport at `Origin`: passenger offset + origin = world.
struct TransportBase
{
    G3D::Vector3 Origin;
    void CalculatePassengerPosition(float& x, float& y, float& z, float* = nullptr) const
    {
        x += Origin.x;
        y += Origin.y;
        z += Origin.z;
    }
};
struct Unit
{
    struct Info { struct Carried { Position pos; } transport; } m_movementInfo;
    std::unique_ptr<Movement::MoveSpline> movespline = std::make_unique<Movement::MoveSpline>();
    TransportBase* Carrier = nullptr;
    G3D::Vector3 World;
    int Relocations = 0;
    TransportBase* GetDirectTransport() const { return Carrier; }
    bool HasUnitState(std::uint32_t) const { return false; }
    float GetOrientation() const { return 0.0f; }
    void UpdatePosition(float x, float y, float z, float)
    {
        World = G3D::Vector3(x, y, z);
        ++Relocations;
    }
    void UpdateSplinePosition();
};
namespace
{
bool TryGetBotCastFacing(Unit const&, Movement::Location const&, float&) { return false; }
}

// ---- the function under test, verbatim from UnitSplinePosition.cpp
@UPDATE_SPLINE_POSITION@
// ----

// A unit whose current spline runs from (100, 200, 10) to (105, 210, 20) in
// `frame` coordinates, 20 % of the way along (101, 202, 12).
static void Start(Unit& unit, TransportBase& transport, bool transportFrame)
{
    unit.Carrier = &transport;
    Movement::MoveSplineInitArgs args;
    args.path = { G3D::Vector3(100, 200, 10), G3D::Vector3(105, 210, 20) };
    args.velocity = 7.5f;
    unit.movespline->Initialize(args);
    unit.movespline->onTransport = transportFrame;
    unit.movespline->updateState(int32(0.2f * float(unit.movespline->Duration())));
    CHECK(unit.movespline->HasStarted() && !unit.movespline->Finalized());
    unit.UpdateSplinePosition();
}

int main(int argc, char** argv)
{
    // argv[1..3]: has Launch already assigned onTransport when the walk clip,
    // the validation and the effect proof refuse or fail?
    if (argc < 4)
        return 2;
    bool const assigned[3] = { argv[1][0] == '1', argv[2][0] == '1', argv[3][0] == '1' };
    char const* const stage[3] = { "walk", "validate", "effect" };
    TransportBase transport;
    transport.Origin = G3D::Vector3(100, 200, 10);

    // A world-frame spline, the unit then standing where it is on it; the
    // transport sits at (100, 200, 10), as the review's reproduction.
    for (int s = 0; s < 3; ++s)
    {
        Unit unit;
        Start(unit, transport, false);
        G3D::Vector3 const before = unit.World;
        Position const offsets = unit.m_movementInfo.transport.pos;
        // The failed launch: whatever it assigned before failing, then the
        // unit's update (StopMoving of a refusal, or the next update).
        if (assigned[s])
            unit.movespline->onTransport = true;
        unit.UpdateSplinePosition();
        std::printf("world_frame %s assigned=%d before=(%.3f, %.3f, %.3f) after=(%.3f, %.3f, %.3f) offsets_written=%d\n",
            stage[s], assigned[s], before.x, before.y, before.z, unit.World.x, unit.World.y, unit.World.z,
            unit.m_movementInfo.transport.pos.m_positionX != offsets.m_positionX);
        CHECK(std::fabs(before.x - 101.0f) < 1e-3f && std::fabs(before.y - 202.0f) < 1e-3f
            && std::fabs(before.z - 12.0f) < 1e-3f);
    }
    // A transport-frame spline (the unit rides it): a refusal keeps it, in its
    // own frame, exactly where it is.
    for (int s = 0; s < 3; ++s)
    {
        Unit unit;
        Start(unit, transport, true);
        G3D::Vector3 const before = unit.World;
        unit.UpdateSplinePosition();
        std::printf("transport_frame %s before=(%.3f, %.3f, %.3f) after=(%.3f, %.3f, %.3f)\n", stage[s],
            before.x, before.y, before.z, unit.World.x, unit.World.y, unit.World.z);
        CHECK((unit.World - before).length() < 1e-3f);
        CHECK(std::fabs(before.x - 201.0f) < 1e-3f && std::fabs(before.z - 22.0f) < 1e-3f);
    }
    std::printf("failures=%d\n", failures);
    return failures ? 1 : 0;
}
'''


def _update_spline_position() -> str:
    text = SPLINE_POSITION.read_text(encoding="utf-8")
    start = text.index("void Unit::UpdateSplinePosition()")
    return text[start:text.index("\n}\n", start) + 3]


def _launch_body(path: Path = LAUNCH) -> str:
    text = re.sub(r"//[^\n]*", "", path.read_text(encoding="utf-8"))
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return text[text.index("int32 MoveSplineInit::Launch()"):text.index("void MoveSplineInit::Stop()")]


def _assigned_before_each_failure(path: Path = LAUNCH) -> str:
    """'1' per failing stage (walk clip, validation, effect proof) that comes after the onTransport assignment."""
    body = _launch_body(path)
    assign = body.index("move_spline.onTransport = transport;")
    stages = [body.index("if (transport && ClipPassengerSpline(unit, args) == PassengerClip::Refused)"),
              body.index("if (!args.Validate(unit))"),
              body.index("if (transport && ProvePassengerEffectSpline(unit, args) == PassengerClip::Refused)")]
    return " ".join("1" if assign < stage else "0" for stage in stages)


def _compile_and_run(tmp_path: Path, flags: str) -> str:
    stub = tmp_path / "stub"
    stub.mkdir(exist_ok=True)
    (stub / "Log.h").write_text(STUB_LOG)
    (stub / "Creature.h").write_text(STUB_CREATURE)
    source = tmp_path / "program.cpp"
    source.write_text(PROGRAM.replace("@UPDATE_SPLINE_POSITION@", _update_spline_position()))
    binary = tmp_path / "program"
    includes = [stub, GAME, GAME / "Movement/Spline", GAME / "Entities/Object",
                GAME / "Entities/Object/Updates", ROOT / "src/common", ROOT / "src/common/Utilities",
                ROOT / "src/common/Debugging", ROOT / "src/common/Logging",
                ROOT / "dep/g3dlite/include", ROOT / "dep/fmt/include"]
    command = ["g++", "-std=c++20", "-O1", "-Wall", "-Wextra", "-ffunction-sections", "-fdata-sections"]
    for include in includes:
        command += ["-I", str(include)]
    command += [str(source)] + [str(GAME / "Movement/Spline" / name)
                                for name in ("MoveSpline.cpp", "Spline.cpp", "MovementUtil.cpp")]
    subprocess.run(command + ["-Wl,--gc-sections", "-o", str(binary)], check=True, cwd=ROOT)
    run = subprocess.run([str(binary)] + flags.split(), cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    return run.stdout


def test_a_refused_or_failed_launch_does_not_move_a_unit_on_a_live_world_frame_spline(tmp_path: Path) -> None:
    flags = _assigned_before_each_failure()
    # No stage assigns the frame before it can fail.
    assert flags == "0 0 0", flags
    out = _compile_and_run(tmp_path, flags)
    for stage in ("walk", "validate", "effect"):
        match = re.search(rf"world_frame {stage} assigned=0 before=\((\S+), (\S+), (\S+)\) after=\((\S+), (\S+), (\S+)\) "
                          r"offsets_written=0", out)
        assert match, out
        assert [float(v) for v in match.groups()[:3]] == [float(v) for v in match.groups()[3:]] == [101.0, 202.0, 12.0]
    assert len(re.findall(r"transport_frame \w+ before=\((\S+), (\S+), (\S+)\) after=\(\1, \2, \3\)", out)) == 3, out
    assert "failures=0" in out, out


def test_the_unit_moved_when_the_frame_was_assigned_before_the_refusal(tmp_path: Path) -> None:
    # The review's reproduction: what the launch did before (every stage after
    # the assignment) read the world spline as offsets on the transport.
    out = _compile_and_run(tmp_path, "1 1 1")
    assert len(re.findall(r"world_frame \w+ assigned=1 before=\(101\.000, 202\.000, 12\.000\) "
                          r"after=\(201\.000, 402\.000, 22\.000\)", out)) == 3, out


def test_launch_changes_the_splines_state_only_after_every_proof_and_the_validation() -> None:
    body = _launch_body()
    # One assignment, directly before the spline's initialization, after the
    # walk clip, the validation and the passenger effect proof.
    assert body.count("move_spline.onTransport = transport;") == 1
    order = [body.index("if (transport && ClipPassengerSpline(unit, args) == PassengerClip::Refused)"),
             body.index("if (!args.Validate(unit))"),
             body.index("if (transport && ProvePassengerEffectSpline(unit, args) == PassengerClip::Refused)"),
             body.index("move_spline.onTransport = transport;"),
             body.index("unit->m_movementInfo.SetMovementFlags(moveFlags);"),
             body.index("move_spline.Initialize(args);")]
    assert order == sorted(order)
    # Nothing before the last refusal changes the unit's spline or movement
    # state (the refusals stop the unit in the spline's own frame).
    before = body[:order[3]]
    assert not re.search(r"onTransport\s*=(?!=)", before)
    for mutation in ("move_spline.Initialize(", "SetMovementFlags(", "AddUnitMovementFlag(",
                     "RemoveUnitMovementFlag(", "SetFall("):
        assert mutation not in before, mutation
    # Each refusal stops the unit and records the failed launch.
    for refusal in (order[0], order[2]):
        refused = body[refusal:body.index("return 0;", refusal)]
        assert "unit->StopMoving();" in refused and "recordLaunch(false);" in refused
    # Unit::UpdateSplinePosition reads the frame of the spline it is given.
    text = _update_spline_position()
    assert "if (movespline->onTransport)" in text and "m_movementInfo.transport.pos" in text
