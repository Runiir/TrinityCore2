"""Round 2 (BWD 10N, Nefarian): a transport passenger's range/LOS recovery
endpoint must stand on a floor.

r01 receipt 10826 (bot 11005009) launched a combat-range point spline from a
pillar top to an endpoint with a floor 168 yd below
(selected_platform_compatible=false). MoveBotToProfileRange's single endpoint
funnel (moveProfilePoint) now asks
BotTransportSurfaceMovement::PassengerEndpointHasFloor first; a passenger's
endpoint over the void gets no Move intent. Non-passengers are unaffected.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.test_nefarian_strategy import INCLUDES, ROOT

COMBAT_MOVEMENT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatMovement.cpp"
SURFACE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativePathTransportSurface.cpp"

PROGRAM = r'''
#include "Bots/BotPassengerEndpointFloor.h"
#include <cstdio>
#include <limits>

static int failures = 0;
#define CHECK(condition, message) do { if (!(condition)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, message); ++failures; } } while (0)

using BotPassengerEndpointFloor::Admit;
using BotPassengerEndpointFloor::Probe;

// The movement intents a range recovery would submit for one endpoint.
static int MoveIntents(Probe const& probe, float endpointZ)
{
    return Admit(probe, endpointZ) ? 1 : 0;
}

int main()
{
    float const pillarTopZ = 640.0f;
    // Receipt 10826: a passenger, endpoint over the void, floor 168 yd below
    // (outside the search band, so Map::GetHeight finds nothing).
    Probe voidProbe;
    voidProbe.Passenger = true;
    CHECK(MoveIntents(voidProbe, pillarTopZ) == 0, "endpoint over the void: no Move intent");
    // The same with a floor reported far below.
    Probe farFloor = voidProbe;
    farFloor.FloorFound = true;
    farFloor.FloorZ = pillarTopZ - 168.0f;
    CHECK(MoveIntents(farFloor, pillarTopZ) == 0, "floor 168 yd below: no Move intent");
    // A floor just outside the planner tolerance.
    Probe outside = voidProbe;
    outside.FloorFound = true;
    outside.FloorZ = pillarTopZ - (BotWorldMovement::NativeFloorTolerance + 0.1f);
    CHECK(MoveIntents(outside, pillarTopZ) == 0, "floor outside tolerance");
    // Same pillar top: the transport's own model, or any floor in tolerance.
    Probe onPlatform = voidProbe;
    onPlatform.TransportFloor = true;
    CHECK(MoveIntents(onPlatform, pillarTopZ) == 1, "own transport floor admits");
    Probe staticFloor = voidProbe;
    staticFloor.FloorFound = true;
    staticFloor.FloorZ = pillarTopZ - 1.0f;
    CHECK(MoveIntents(staticFloor, pillarTopZ) == 1, "floor within tolerance admits");
    // Non-passengers keep the ordinary planner, whatever the probe says.
    Probe ground;
    CHECK(MoveIntents(ground, pillarTopZ) == 1, "non-passenger unaffected");
    // A non-finite endpoint is refused for a passenger.
    Probe nan = onPlatform;
    CHECK(MoveIntents(nan, std::numeric_limits<float>::quiet_NaN()) == 0, "non-finite endpoint");
    return failures ? 1 : 0;
}
'''


def test_passenger_endpoint_over_the_void_gets_no_move_intent(tmp_path: Path) -> None:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(PROGRAM)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-3000:]


def test_every_profile_range_endpoint_passes_the_passenger_floor_gate() -> None:
    text = COMBAT_MOVEMENT.read_text(encoding="utf-8")
    body = text[text.index("bool BotWorldPopulationMgr::MoveBotToProfileRange("):]
    mover = body[body.index("auto moveProfilePoint = [&](float x, float y, float z)"):]
    mover = mover[:mover.index("};")]
    gate = mover.index("BotTransportSurfaceMovement::PassengerEndpointHasFloor(bot, x, y, z)")
    assert gate < mover.index("MoveBotToPoint(")
    # Terrain-projected points reach MoveBotToPoint only through moveProfilePoint.
    projected = body[body.index("auto moveToTerrainProjectedPoint"):]
    projected = projected[:projected.index("};")]
    assert "moveProfilePoint(x, y, floorZ)" in projected and "MoveBotToPoint(" not in projected
    # Only the melee dynamic chase calls MoveBotToPoint directly (not an endpoint recovery).
    direct = body[body.index("auto moveToTerrainProjectedPoint"):].count("MoveBotToPoint(")
    assert direct == 1

    surface = SURFACE.read_text(encoding="utf-8")
    probe = surface[surface.index("bool PassengerEndpointHasFloor("):]
    assert "bot->GetTransport()" in probe
    assert "BotWorldMovement::NativeFloorTolerance" in probe
    assert "TransportFloorAt(bot, transport, x, y, z, tolerance)" in probe
    assert "BotPassengerEndpointFloor::Admit(probe, z, tolerance)" in probe
