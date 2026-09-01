import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOVEMENT = ROOT / "src/server/game/Movement"
VALIDATION = ROOT / (
    "src/server/game/Bots/BotWorldPopulationMgrNativePathValidation.h"
)
JSON_SOURCE = ROOT / (
    "src/server/game/Bots/"
    "BotWorldPopulationMgrMovementPlannerDiagnosticsJson.cpp"
)
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_retained_endpoint_resolution_counterexample_and_negatives(tmp_path):
    source = tmp_path / "native_endpoint_resolution.cpp"
    binary = tmp_path / "native_endpoint_resolution"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrNativeFloor.h"

#include <cassert>
#include <cmath>
#include <cstring>
#include <initializer_list>

using namespace BotWorldMovement;

static NativePathProofObservation CompleteFloorValidProof()
{
    NativePathProofObservation proof;
    proof.Available = true;
    proof.Calculated = true;
    proof.PathType = 1; // PATHFIND_NORMAL.
    proof.Complete = true;
    proof.EndpointX = -305.600037f;
    proof.EndpointY = -34.9334412f;
    proof.EndpointZ = 210.521393f;
    proof.EndpointDistance = 4.40606976f;
    proof.EndpointHorizontalDistance = 4.38568068f;
    proof.EndpointVerticalDistance = 0.42338562f;
    proof.EndpointMatched = false;
    proof.EndpointFloorValid = true;
    proof.FloorObservation = MakeNativePathFloorObservation(
        NativePathFloorFailure::None, 0, 0, 0.0f, 0.0f, 0.0f, 0.0f,
        0.0f);
    return proof;
}

int main()
{
    // Retained replay: request=(-302.471405,-31.8600292,210.098007),
    // native actual=(-305.600037,-34.9334412,210.521393).
    NativePathProofObservation projected = CompleteFloorValidProof();
    assert(std::fabs(projected.EndpointDistance - 4.40606976f) < 0.00001f);
    RecordNativePathEndpointResolution(projected,
        PathEndpointResult::ReachedProjectedEndPoly, true, true,
        -305.600037f, -34.9334412f, 210.521393f, 0.0f, 0.0f);
    projected.Accepted = NativePathProofPassesAdmission(projected);
    assert(projected.EndpointResult
        == PathEndpointResult::ReachedProjectedEndPoly);
    assert(projected.CorridorReachedEndPoly);
    assert(projected.ResolvedEndpointAvailable);
    assert(projected.ActualEndpointMatchedResolved);
    // Observation does not turn native progress into requested completion.
    assert(!projected.EndpointMatched);
    assert(!projected.Accepted);

    NativePathProofObservation requested = CompleteFloorValidProof();
    requested.EndpointDistance = 0.0f;
    requested.EndpointHorizontalDistance = 0.0f;
    requested.EndpointVerticalDistance = 0.0f;
    requested.EndpointMatched = true;
    RecordNativePathEndpointResolution(requested,
        PathEndpointResult::ReachedRequested, true, true,
        requested.EndpointX, requested.EndpointY, requested.EndpointZ,
        0.0f, 0.0f);
    requested.Accepted = NativePathProofPassesAdmission(requested);
    assert(requested.Accepted);

    for (PathEndpointResult terminal : {
            PathEndpointResult::NoSteer,
            PathEndpointResult::CorridorExhausted,
            PathEndpointResult::Capacity,
            PathEndpointResult::Failure })
    {
        NativePathProofObservation stopped = CompleteFloorValidProof();
        RecordNativePathEndpointResolution(stopped, terminal, true, true,
            stopped.EndpointX, stopped.EndpointY, stopped.EndpointZ,
            0.0f, 0.0f);
        assert(stopped.EndpointResult == terminal);
        assert(std::strcmp(PathEndpointResultName(terminal), "unknown") != 0);
        assert(!stopped.EndpointMatched);
        assert(!NativePathProofPassesAdmission(stopped));
    }

    NativePathProofObservation projectionMismatch = projected;
    RecordNativePathEndpointResolution(projectionMismatch,
        PathEndpointResult::ReachedProjectedEndPoly, true, true,
        -305.600037f, -34.9334412f, 210.521393f, 0.75f, 0.0f);
    assert(!projectionMismatch.ActualEndpointMatchedResolved);

    NativePathProofObservation unavailable = projected;
    RecordNativePathEndpointResolution(unavailable,
        PathEndpointResult::ReachedProjectedEndPoly, true, false,
        0.0f, 0.0f, 0.0f, 0.0f, 0.0f);
    assert(!unavailable.ResolvedEndpointAvailable);
    assert(!unavailable.ActualEndpointMatchedResolved);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "src/server/game"),
            str(source), "-o", str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_path_generator_writes_typed_native_endpoint_observation():
    header = (MOVEMENT / "PathGenerator.h").read_text(encoding="utf-8")
    implementation = (MOVEMENT / "PathGeneratorSmooth.cpp").read_text(
        encoding="utf-8"
    )
    validation = VALIDATION.read_text(encoding="utf-8")
    diagnostics = JSON_SOURCE.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert "closestPointOnPolyBoundary" in implementation
    assert "MarkResolvedEndPositionReached();" in implementation
    for outcome in (
        "ReachedProjectedEndPoly", "NoSteer", "CorridorExhausted",
        "Capacity", "Failure",
    ):
        assert f"PathEndpointResult::{outcome}" in implementation
    assert "GetEndpointResult()" in header
    assert "CorridorReachedEndPoly()" in header
    assert "GetResolvedEndPosition()" in header
    assert "ObserveNativePathEndpointResolution" in validation
    assert "path.GetEndpointResult()" in validation
    assert "path.CorridorReachedEndPoly()" in validation
    assert "path.GetResolvedEndPosition()" in validation
    assert '\\"endpoint_resolution\\"' in diagnostics
    assert "PathEndpointResultName" in diagnostics
    assert "Movement/PathGeneratorSmooth.cpp" in cmake


def test_changed_cpp_files_stay_below_size_limit():
    for path in (
        MOVEMENT / "PathEndpoint.h",
        MOVEMENT / "PathGenerator.h",
        MOVEMENT / "PathGenerator.cpp",
        MOVEMENT / "PathGeneratorSmooth.cpp",
        VALIDATION,
        JSON_SOURCE,
    ):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000
