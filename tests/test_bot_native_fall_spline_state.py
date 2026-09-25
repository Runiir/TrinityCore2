"""A native fall stopped mid-air still owes its landing (review of patch 1).

Unit::StopMoving -> MoveSplineInit::Stop -> MoveSpline::Initialize with Done
clears the spline: Initialized() is false, Finalized() true, and
FinalDestination() an empty Vector3, while MOVEMENTFLAG_FALLING stays set. A
stun, a root or a Survival cast mid-fall does exactly that. The landing
predicate must still report the landing as owed, and the landing step must
not compare the member against an empty spline's end.

The predicates are run against the REAL Movement::MoveSpline (MoveSpline.cpp,
Spline.cpp and MovementUtil.cpp compiled as they are), put into the stop state
by the same Initialize call MoveSplineInit::Stop makes. Only the logging, the
Creature facade and two G3D matrix members the linear spline never evaluates
are stubbed.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "src/server/game"
BOTS = GAME / "Bots"

STUB_LOG = """#pragma once
#define TC_LOG_DEBUG(...) do { } while (0)
#define TC_LOG_ERROR(...) do { } while (0)
"""
STUB_CREATURE = """#pragma once
#include "ObjectGuid.h"
class Creature;
class Unit
{
public:
    TypeID GetTypeId() const { return TYPEID_UNIT; }
    ObjectGuid GetGUID() const { return ObjectGuid::Empty; }
    Creature const* ToCreature() const { return nullptr; }
    uint32 GetEntry() const { return 0; }
};
class Creature : public Unit { public: uint32 GetSpawnId() const { return 0; } };
"""
PROGRAM = r'''
#include "Bots/BotValidationRouteNativeFallSpline.h"
#include "Errors.h"
#include <G3D/Matrix4.h>
#include <G3D/Vector4.h>
#include <cstdio>
#include <cstdlib>

// Link stubs: assertions abort; the Catmull-Rom/Bezier matrices are built at
// static initialization but never evaluated by a linear fall spline.
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

namespace Fall = BotValidationRouteNativeFall;
static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL %d %s\n", __LINE__, #c); ++failures; } } while (0)

int main()
{
    Movement::MoveSpline spline;
    // MotionMaster::MoveFall: a falling spline from the lip to the platform.
    Movement::MoveSplineInitArgs fall;
    fall.path.push_back(G3D::Vector3(-157.05f, -224.62f, 41.104f));
    fall.path.push_back(G3D::Vector3(-157.05f, -224.62f, 8.519f));
    fall.velocity = 7.0f;
    fall.flags.Falling = true;
    spline.Initialize(fall);
    CHECK(spline.Initialized() && !spline.Finalized() && spline.isFalling());
    CHECK(Fall::SplineActive(spline));
    CHECK(!Fall::LandingPending(true, spline));
    CHECK(Fall::EndpointKnown(spline));
    CHECK(Fall::ReportedFallTimeMs(spline) > 0);

    // A stun, root or cast mid-air: Unit::StopMoving -> MoveSplineInit::Stop,
    // which initializes the unit's spline with args.flags = Done.
    Movement::MoveSplineInitArgs stop;
    stop.flags = Movement::MoveSplineFlagEnum::Done;
    spline.Initialize(stop);
    CHECK(!spline.Initialized() && spline.Finalized());
    CHECK(!Fall::SplineActive(spline));
    // MOVEMENTFLAG_FALLING is still set: the landing is owed...
    CHECK(Fall::LandingPending(true, spline));
    // ...and there is no end to compare, nor a duration to read.
    CHECK(!Fall::EndpointKnown(spline));
    CHECK(Fall::ReportedFallTimeMs(spline) == 0);
    // Without the falling flags (landed and reported) nothing is owed.
    CHECK(!Fall::LandingPending(false, spline));
    return failures ? 1 : 0;
}
'''


def test_the_real_move_spline_after_a_stop_still_owes_the_landing(tmp_path: Path) -> None:
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "Log.h").write_text(STUB_LOG)
    (stub / "Creature.h").write_text(STUB_CREATURE)
    source = tmp_path / "program.cpp"
    source.write_text(PROGRAM)
    binary = tmp_path / "program"
    includes = [stub, GAME, GAME / "Movement/Spline", GAME / "Entities/Object",
                GAME / "Entities/Object/Updates", ROOT / "src/common", ROOT / "src/common/Utilities",
                ROOT / "src/common/Debugging", ROOT / "src/common/Logging",
                ROOT / "dep/g3dlite/include", ROOT / "dep/fmt/include"]
    command = ["g++", "-std=c++20", "-O0", "-ffunction-sections", "-fdata-sections"]
    for include in includes:
        command += ["-I", str(include)]
    command += [str(source)] + [str(GAME / "Movement/Spline" / name)
                                for name in ("MoveSpline.cpp", "Spline.cpp", "MovementUtil.cpp")]
    subprocess.run(command + ["-Wl,--gc-sections", "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def _code(text: str) -> str:
    text = re.sub(r"//.*", "", text)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_the_stop_and_the_landing_step_are_wired_as_replayed() -> None:
    # The replay above initializes the spline exactly as MoveSplineInit::Stop.
    init = _code((GAME / "Movement/Spline/MoveSplineInit.cpp").read_text(encoding="utf-8"))
    stop = init[init.index("void MoveSplineInit::Stop()"):]
    stop = stop[:stop.index("\n    }\n")]
    assert "args.flags = MoveSplineFlagEnum::Done;" in stop
    assert "move_spline.Initialize(args);" in stop
    boarding = _code((BOTS / "BotWorldPopulationMgrValidationRouteBoardingAction.cpp").read_text(encoding="utf-8"))
    assert "BotValidationRouteNativeFall::SplineActive(*bot->movespline)" in boarding
    assert "BotValidationRouteNativeFall::LandingPending(\n        bot->HasUnitMovementFlag(MOVEMENTFLAG_FALLING | MOVEMENTFLAG_FALLING_FAR)," in boarding
    surface = _code((BOTS / "BotWorldPopulationMgrNativePathTransportSurface.cpp").read_text(encoding="utf-8"))
    land = surface[surface.index("Outcome ExecuteLand("):surface.index("namespace BotTransportSurfaceMovement")]
    assert land.index("if (BotValidationRouteNativeFall::EndpointKnown(*bot->movespline))") < land.index(
        '"native_ledge_drop_land_not_at_fall_end"')
    assert "BotValidationRouteNativeFall::ReportedFallTimeMs(*bot->movespline)" in land
    assert "movespline->Duration()" not in land
