"""Crash logical anchor floors compose with unchanged native admission."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_crash_anchor_floor_admits_recorded_native_endpoints(tmp_path):
    source = tmp_path / "crash_floor.cpp"
    binary = tmp_path / "crash_floor"
    source.write_text(r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawCrashSideMovement.h"
#include "Bots/BotWorldPopulationMgrNativeFloor.h"
#include <cassert>
using namespace BotEncounter;
using namespace BotWorldMovement;

static bool Admit(Vector3 requested, Vector3 actual, bool floorValid = true)
{
    NativePathProofObservation p;
    p.Available = p.Calculated = p.Complete = true;
    p.PathType = 1;
    p.EndpointX = actual.X;
    p.EndpointY = actual.Y;
    p.EndpointZ = actual.Z;
    p.EndpointHorizontalDistance = std::hypot(actual.X-requested.X, actual.Y-requested.Y);
    p.EndpointVerticalDistance = std::fabs(actual.Z-requested.Z);
    p.EndpointMatched = NativePathEndpointComponentsMatch(
        p.EndpointHorizontalDistance, p.EndpointVerticalDistance);
    p.EndpointFloorValid = floorValid;
    RecordNativePathEndpointResolution(p, PathEndpointResult::ReachedRequested,
        true, true, requested.X, requested.Y, requested.Z,
        p.EndpointHorizontalDistance, p.EndpointVerticalDistance);
    return NativePathProofPassesAdmission(p);
}
int main()
{
    Vector3 left{-340.854675f,-30.1652412f,211.815002f};
    Vector3 right{-312.400757f,-68.8223724f,211.815002f};
    Vector3 support{-307.531f,-35.4375f,211.815002f};
    Vector3 nativeLeft{left.X,left.Y,211.313324f};
    // Recorded retained request heights for receipts 560 and 584.
    for (float height : {212.957855f,212.895218f,210.0f,215.0f})
    {
        Vector3 actor{-330.415771f,-74.4841461f,height};
        auto fixed = ResolveMagmawCrashSideMovement(actor,right,support,left,right,true,16.0f);
        assert(fixed.Resolved && fixed.ActorUnsafe);
        assert(fixed.Destination.X == left.X && fixed.Destination.Y == left.Y);
        assert(Admit(fixed.Destination,nativeLeft));
        assert(fixed.Destination.Z == left.Z);
        assert(!Admit(fixed.Destination,{left.X,left.Y,190.0f}));
        assert(!Admit(fixed.Destination,nativeLeft,false));
        auto ordinary = ResolveMagmawCrashSideMovement(actor,right,support,left,right,false,16.0f);
        assert(ordinary.Resolved && ordinary.ActorUnsafe);
        assert(ordinary.Destination.Z == support.Z);
        assert(std::fabs(std::hypot(ordinary.Destination.X-support.X,
            ordinary.Destination.Y-support.Y)-16.0f) < 0.001f);
        assert(Admit(ordinary.Destination,ordinary.Destination));
        assert(!Admit(ordinary.Destination,{ordinary.Destination.X,
            ordinary.Destination.Y,190.0f}));
    }
    // Reverse side and already-safe actor retain the existing decisions.
    auto reverse = ResolveMagmawCrashSideMovement(left,left,support,left,right,true,16.0f);
    assert(reverse.ActorUnsafe && reverse.Destination.X == right.X);
    assert(reverse.Destination.Z == right.Z);
    auto safe = ResolveMagmawCrashSideMovement(left,right,support,left,right,true,16.0f);
    assert(safe.Resolved && !safe.ActorUnsafe);
}
''', encoding="utf-8")
    includes = ["src/server/game", "src/server/game/Entities/Object", "src/common",
                "src/common/Utilities", "src/common/Logging"]
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    *[arg for path in includes for arg in ("-I", str(ROOT / path))],
                    str(source), "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)
