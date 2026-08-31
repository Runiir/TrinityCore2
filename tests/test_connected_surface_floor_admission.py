from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / (
    "src/server/game/Bots/BotWorldPopulationMgrConnectedSurfacePath.h"
)
PLANNER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementPlanner.cpp"
PATH_GENERATOR = ROOT / "src/server/game/Movement/PathGenerator.h"


def test_connected_surface_floor_counterexample_and_adjacent_negatives(tmp_path):
    source = tmp_path / "connected_surface_floor.cpp"
    binary = tmp_path / "connected_surface_floor"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrConnectedSurfacePath.h"

#include <cassert>
#include <cmath>
#include <vector>

struct Point
{
    float x;
    float y;
    float z;
};

using namespace BotWorldMovement;

static NativePathProofObservation ConnectedProof(Point const& request)
{
    NativePathProofObservation proof;
    proof.Available = true;
    proof.Calculated = true;
    proof.PathType = 1; // PATHFIND_NORMAL in the production PathGenerator.
    proof.Complete = true;
    proof.EndpointX = request.x;
    proof.EndpointY = request.y;
    proof.EndpointZ = request.z;
    proof.EndpointMatched = true;
    proof.EndpointFloorValid = false;
    proof.FloorObservation = MakeNativePathFloorObservation(
        NativePathFloorFailure::SampleFloorGap, 3, 9,
        request.x, request.y, request.z, -106.245819f, request.z);
    proof.FloorObservationConflict = true;
    proof.Accepted = NativePathProofPassesAdmission(proof);
    return proof;
}

int main()
{
    Point const actor{ -345.872009f, -224.343994f, 193.126999f };
    Point const request{ -302.471405f, -31.8600292f, 210.098007f };
    float const unrelatedLowerGeometry = -106.245819f;
    assert(std::fabs(unrelatedLowerGeometry - request.z) > 316.343f);

    NativePathProofObservation connected = ConnectedProof(request);
    assert(!connected.Accepted);
    assert(ClassifyNativePrimaryEndpointAdmission(
        connected, true, false, true, false)
        == NativePrimaryEndpointAdmission::ConnectedSurface);

    // a506 receipt 561 remains rejected even if represented as complete and
    // normal: an actor-anchored vertical jump is not continuous topology.
    Point const crossFloorActor{ -311.394684f, -48.4652405f, 227.12999f };
    Point const crossFloorRequest{ -300.079803f, -27.1645069f, 210.948013f };
    NativePathProofObservation crossFloor = ConnectedProof(crossFloorRequest);
    crossFloor.PathType = 1; // Complete PATHFIND_NORMAL wrong-floor jump.
    assert(crossFloorActor.z != crossFloorRequest.z);
    assert(ClassifyNativePrimaryEndpointAdmission(
        crossFloor, true, false, false, false)
        == NativePrimaryEndpointAdmission::Rejected);

    // A forged multi-control vertical staircase remains rejected: copied
    // controls cannot provide PathGenerator's private polygon-corridor proof.
    Point const staircaseRequest{ actor.x, actor.y, request.z };
    NativePathProofObservation staircase = ConnectedProof(staircaseRequest);
    std::vector<Point> forgedStaircase;
    for (unsigned step = 0; step <= 8; ++step)
        forgedStaircase.push_back({ actor.x, actor.y,
            actor.z + (staircaseRequest.z - actor.z) * float(step) / 8.0f });
    assert(forgedStaircase.size() > 2);
    assert(forgedStaircase.front().z == actor.z);
    assert(forgedStaircase.back().z == staircaseRequest.z);
    assert(ClassifyNativePrimaryEndpointAdmission(
        staircase, true, false, false, false)
        == NativePrimaryEndpointAdmission::Rejected);

    // a506 receipt 556 remains fail-closed when mmap was not used.
    NativePathProofObservation missingMmap = connected;
    missingMmap.PathType = 16; // PATHFIND_NOT_USING_PATH.
    missingMmap.Accepted = true; // Flags remain independently authoritative.
    assert(ClassifyNativePrimaryEndpointAdmission(
        missingMmap, true, true, false, false)
        == NativePrimaryEndpointAdmission::Rejected);

    NativePathProofObservation incomplete = connected;
    incomplete.PathType = 4; // PATHFIND_INCOMPLETE.
    incomplete.Complete = false;
    assert(ClassifyNativePrimaryEndpointAdmission(
        incomplete, true, false, true, false)
        == NativePrimaryEndpointAdmission::Rejected);

    // Missing height evidence never becomes connected-surface proof.
    NativePathProofObservation missingHeight = connected;
    missingHeight.FloorObservation = MakeNativePathFloorObservation(
        NativePathFloorFailure::SampleFloorUnavailable, 3, 9,
        request.x, request.y, request.z, -100000.0f, request.z);
    missingHeight.FloorObservationConflict = true;
    missingHeight.Accepted = true; // Missing evidence still fails closed.
    assert(ClassifyNativePrimaryEndpointAdmission(
        missingHeight, true, false, true, false)
        == NativePrimaryEndpointAdmission::Rejected);

    // A valid request-level sample cannot use a conflict discovered later
    // along the path as positive admission evidence.
    assert(ClassifyNativePrimaryEndpointAdmission(
        connected, false, false, true, false)
        == NativePrimaryEndpointAdmission::Rejected);

    // Missing topology proof cannot be replaced by otherwise plausible
    // endpoint and floor-conflict values.
    assert(ClassifyNativePrimaryEndpointAdmission(
        connected, true, false, false, false)
        == NativePrimaryEndpointAdmission::Rejected);

    NativePathProofObservation endpointMismatch = connected;
    endpointMismatch.EndpointMatched = false;
    assert(ClassifyNativePrimaryEndpointAdmission(
        endpointMismatch, true, false, true, false)
        == NativePrimaryEndpointAdmission::Rejected);

    NativePathProofObservation noConflict = connected;
    noConflict.FloorObservationConflict = false;
    assert(ClassifyNativePrimaryEndpointAdmission(
        noConflict, true, false, true, false)
        == NativePrimaryEndpointAdmission::Rejected);
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


def test_planner_defers_request_height_rejection_to_native_topology():
    planner = PLANNER.read_text(encoding="utf-8")
    native_path = planner.index("PathGenerator path(bot)")
    connected_proof = planner.index(
        "ClassifyNativePrimaryEndpointAdmission", native_path
    )
    target_floor_rejection = planner.index(
        'reject("route_destination_invalid_floor", "target_floor")',
        connected_proof,
    )
    target_z_rejection = planner.index(
        'reject("route_destination_invalid_z_transition",', connected_proof
    )

    assert "route_destination_invalid_floor" not in planner[:native_path]
    assert "route_destination_invalid_z_transition" not in planner[:native_path]
    assert native_path < connected_proof < target_floor_rejection
    assert native_path < connected_proof < target_z_rejection
    assert "targetFloorRequiresNativeProof" in planner
    assert "targetZTransitionRequiresNativeProof" in planner
    assert "connectedPolyCorridor = path.HasConnectedPolyCorridor()" in planner
    assert 'traversalMode = "native_connected_surface_path"' in planner
    assert "segmentZ = verifiedMainEndpoint.z" in planner
    for forbidden in ("TeleportTo(", "NearTeleportTo(", "MoveJump("):
        assert forbidden not in planner


def test_connected_surface_files_stay_below_cpp_size_limit():
    path_generator = PATH_GENERATOR.read_text(encoding="utf-8")
    assert "bool HasConnectedPolyCorridor() const" in path_generator
    assert "if (!_navMesh || !_polyLength)" in path_generator
    assert "_pathPolyRefs[i] == INVALID_POLYREF" in path_generator
    assert len(HEADER.read_text(encoding="utf-8").splitlines()) < 1000
    assert len(PLANNER.read_text(encoding="utf-8").splitlines()) < 1000
    assert len(path_generator.splitlines()) < 1000
