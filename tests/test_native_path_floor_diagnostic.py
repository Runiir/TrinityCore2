from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
FLOOR = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativeFloor.h"
PATH_VALIDATION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativePathValidation.h"
GEOMETRY = ROOT / (
    "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
    "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
)
DIAGNOSIS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrDiagnosis.cpp"
STATUS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrStatus.cpp"
DECISION_TRACE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrDecisionTrace.cpp"
BOT_STATE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBotState.h"


def test_native_path_floor_observation_preserves_first_failure_values(tmp_path):
    source = tmp_path / "native_path_floor_observation.cpp"
    binary = tmp_path / "native_path_floor_observation"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrNativeFloor.h"
#include <cassert>
#include <cstring>

using namespace BotWorldMovement;

int main()
{
    auto sample = MakeNativePathFloorObservation(
        NativePathFloorFailure::SampleFloorGap, 4, 7,
        -345.5f, -112.25f, 216.75f, 219.1f, 214.0f);
    assert(!sample.Accepted());
    assert(std::strcmp(NativePathFloorFailureName(sample.Failure),
        "sample_floor_gap") == 0);
    assert(sample.SegmentIndex == 4);
    assert(sample.SampleIndex == 7);
    assert(sample.X == -345.5f);
    assert(sample.Y == -112.25f);
    assert(sample.Z == 216.75f);
    assert(sample.ResolvedFloorZ == 219.1f);
    assert(sample.ReferenceZ == 214.0f);

    auto actorGap = MakeNativePathFloorObservation(
        NativePathFloorFailure::ActorReferenceGap, 0, 0,
        -348.172f, -111.319f, 215.259f, 215.259f, 214.0f);
    assert(!actorGap.Accepted());
    assert(std::strcmp(NativePathFloorFailureName(actorGap.Failure),
        "actor_reference_gap") == 0);
    assert(NativePathFloorObservation{}.Accepted());

    // Canary90: actor and request are on the upper room level while a VMAP
    // query resolves an unrelated floor far below.
    assert(AdmitSameLevelDeclaredFloorFallback(
        213.939f, 213.665f, -91.5379f));
    // A genuine cross-floor request remains ineligible for this fallback.
    assert(!AdmitSameLevelDeclaredFloorFallback(
        213.939f, -91.5379f, -91.5379f));
    // A normal valid native sample does not need declared fallback.
    assert(!AdmitSameLevelDeclaredFloorFallback(
        213.939f, 213.665f, 213.7f));

    // Canary119 seq3376: the first Magmaw hazard rejection kept a same-room
    // request at z=211.581 while the candidate floor probe returned the
    // unrelated lower floor at z=-103.448. Local-step admission must retain
    // the declared actor level for that bounded fallback.
    NativeFloorResult const canary119 =
        AdmitSameLevelLocalStepFloor(211.581f, 211.581f, -103.448f);
    assert(canary119.Accepted());
    assert(canary119.UsesDeclaredFallback());
    assert(canary119.Z == 211.581f);
    assert(!NativePathEndpointComponentsMatch(1.58586f, 1.24123f));
    NativeFloorResult const massiveCrash =
        AdmitSameLevelLocalStepFloor(211.813f, 211.813f, -111.843f);
    assert(massiveCrash.Accepted());
    assert(massiveCrash.UsesDeclaredFallback());
    assert(massiveCrash.Z == 211.813f);
    NativeFloorResult const nearby =
        AdmitSameLevelLocalStepFloor(211.581f, 211.581f, 211.92f);
    assert(nearby.Accepted());
    assert(!nearby.UsesDeclaredFallback());
    assert(nearby.Z == 211.92f);
    // A genuine cross-floor request cannot inherit the actor's transient Z.
    assert(!AdmitSameLevelLocalStepFloor(211.581f, -103.448f,
        -103.448f).Accepted());

    // Canary107: MMAP kept the requested X/Y and normalized the endpoint to
    // its walkable Z.  This is the same destination, not an endpoint miss.
    assert(NativePathEndpointComponentsMatch(0.0f, 0.882904f));
    assert(NativePathEndpointComponentsMatch(0.0f, 0.811676f));
    // A horizontal miss or a cross-level endpoint remains rejected.
    assert(!NativePathEndpointComponentsMatch(0.5001f, 0.0f));
    assert(!NativePathEndpointComponentsMatch(0.0f, 1.5001f));
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


def test_drudge_uses_declared_floor_as_reference_after_endpoint_resolution():
    geometry = GEOMETRY.read_text(encoding="utf-8")
    validation = PATH_VALIDATION.read_text(encoding="utf-8")
    floor = FLOOR.read_text(encoding="utf-8")
    assert "float const declaredReferenceZ = z;" in geometry
    assert "DiagnoseNativePathFloors(Bot, path,\n                declaredReferenceZ, true)" in geometry
    assert "NativePathFloorFailure::SampleFloorGap" in validation
    assert "NativePathFloorFailure::ActorReferenceGap" in validation
    assert "NativePathFloorObservationBlocksCompleteProof" in floor
    assert "case NativePathFloorFailure::SampleFloorUnavailable:" in floor
    assert "case NativePathFloorFailure::SampleFloorGap:" in floor


def test_native_path_endpoint_z_normalization_preserves_horizontal_identity(tmp_path):
    source = tmp_path / "native_path_endpoint_identity.cpp"
    binary = tmp_path / "native_path_endpoint_identity"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrNativeFloor.h"
#include <cassert>

int main()
{
    assert(BotWorldMovement::NativePathEndpointComponentsMatch(0.0f, 0.882904f));
    assert(BotWorldMovement::NativePathEndpointComponentsMatch(0.0f, 0.811676f));
    assert(!BotWorldMovement::NativePathEndpointComponentsMatch(0.5001f, 0.0f));
    assert(!BotWorldMovement::NativePathEndpointComponentsMatch(0.0f, 1.5001f));
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


def test_planner_same_level_fallback_still_requires_native_path_proof():
    planner = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementPlanner.cpp"
    ).read_text(encoding="utf-8")
    validation = PATH_VALIDATION.read_text(encoding="utf-8")
    floor = FLOOR.read_text(encoding="utf-8")
    admission = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrNativePathAdmission.h").read_text(
            encoding="utf-8")
    movement = (
        ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrValidationRouteMovementCheck.cpp"
    ).read_text(encoding="utf-8")

    assert "AdmitSameLevelDeclaredFloorFallback" in planner
    assert "AdmitSameLevelLocalStepFloor" in planner
    assert "&& !sameLevelDeclaredFloorFallback" in planner
    assert "NativePathPointFloorValid(bot," in planner
    assert "*pathReferenceFloorZ,\n                true" in planner
    assert "DiagnoseNativePathFloors(bot," in planner
    assert "NativePathFloorObservationBlocksCompleteProof" in planner
    assert '#include "BotMovementArbiter.h"' not in floor
    assert "FloorObservationConflict" in validation
    assert "EndpointMatched" in validation
    assert "NativePathEndpointComponentsMatch" in validation
    assert "NativePathAllowsBoundedSameLevelMechanicProgress" in admission
    assert "if (targetFloorValid && nativeProof.Calculated" in planner
    assert "&& nativeProof.Complete)" in planner
    assert "native_bounded_same_level_mechanic_endpoint" in planner
    assert 'action = "hold_hazard_exit_retry_backoff"' in movement
    assert '== "hazard_exit_no_union_safe_native_path"' in movement


def test_canary119_bounded_complete_mechanic_endpoint_selection(tmp_path):
    source = tmp_path / "canary119_mechanic_endpoint.cpp"
    binary = tmp_path / "canary119_mechanic_endpoint"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrNativePathAdmission.h"

#include <cassert>

using namespace BotWorldMovement;
using BotMovementArbitration::Owner;

static NativePathProofObservation Canary119Proof()
{
    NativePathProofObservation proof;
    proof.Available = true;
    proof.Calculated = true;
    proof.PathType = 1; // PATHFIND_NORMAL, kept lightweight for this fixture.
    proof.Complete = true;
    proof.EndpointX = -309.333f;
    proof.EndpointY = -33.6001f;
    proof.EndpointZ = 210.339f;
    proof.EndpointDistance = 2.01385f;
    proof.EndpointHorizontalDistance = 1.58586f;
    proof.EndpointVerticalDistance = 1.24123f;
    proof.EndpointMatched = false;
    proof.EndpointFloorValid = true;
    proof.FloorObservation = MakeNativePathFloorObservation(
        NativePathFloorFailure::None, 0, 0, -309.333f, -33.6001f,
        210.339f, 210.339f, 211.581f);
    proof.Accepted = NativePathProofPassesAdmission(proof);
    return proof;
}

int main()
{
    NativePathProofObservation const canary = Canary119Proof();
    // Before the scoped closure, the shared endpoint identity proof fails on
    // the recorded 1.58586-yard horizontal miss.
    assert(!canary.Accepted);
    assert(!NativePathEndpointComponentsMatch(1.58586f, 1.24123f));

    // Actor=(-308.91,-36.4524,211.581), request=(-308.477,-32.2655,211.581)
    // gives currentGoalDistance=4.2092304. The native endpoint is a 3.1396
    // yard actor travel and leaves endpointGoalDistance=2.01385, so progress
    // is approximately 2.195 yards.
    bool const selected = canary.Accepted
        || NativePathAllowsBoundedSameLevelMechanicProgress(
            Owner::Hazard, true, true, true, false, canary, 3.1396f,
            4.2092304f, 2.01385f);
    assert(selected);
    assert(NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Mechanic, true, true, true, false, canary, 3.1396f,
        4.2092304f, 2.01385f));

    // A lower-floor/cross-floor request has no same-level declaration.
    NativePathProofObservation lowerFloor = canary;
    lowerFloor.FloorObservation = MakeNativePathFloorObservation(
        NativePathFloorFailure::SampleFloorGap, 0, 1, -309.333f, -33.6001f,
        211.581f, -103.448f, 211.581f);
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, false, true, true, false, lowerFloor, 3.1396f,
        4.2092304f, 2.01385f));

    // The endpoint must make the existing two-yard progress margin.
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, true, true, false, canary, 3.1396f, 4.0f,
        2.01385f));
    // The minimum is inclusive; the small epsilon absorbs trace float noise.
    assert(NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, true, true, false, canary, 3.1396f, 4.01385f,
        2.01385f));
    // A stationary native endpoint is not a movement result.
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, true, true, false, canary, 1.499f,
        4.2092304f, 2.01385f));

    // Incomplete and forbidden native paths never qualify as complete proof.
    NativePathProofObservation incomplete = canary;
    incomplete.Complete = false;
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, true, false, false, incomplete, 3.1396f,
        4.2092304f, 2.01385f));
    NativePathProofObservation forbidden = canary;
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, true, true, true, forbidden, 3.1396f,
        4.2092304f, 2.01385f));

    // Ordinary formation movement cannot use the local mechanic exception.
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Formation, true, true, true, false, canary, 3.1396f,
        4.2092304f, 2.01385f));
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
            "-I",
            str(ROOT / "src/common"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_native_path_floor_diagnostic_header_stays_small():
    assert len(FLOOR.read_text(encoding="utf-8").splitlines()) < 1000
    assert len(PATH_VALIDATION.read_text(encoding="utf-8").splitlines()) < 1000
    admission = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrNativePathAdmission.h").read_text(
            encoding="utf-8")
    assert len(admission.splitlines()) < 1000


def test_native_path_floor_observation_reaches_diagnose_and_trace_json():
    diagnosis = DIAGNOSIS.read_text(encoding="utf-8")
    status = STATUS.read_text(encoding="utf-8")
    decision_trace = DECISION_TRACE.read_text(encoding="utf-8")
    bot_state = BOT_STATE.read_text(encoding="utf-8")

    assert "LastNativePathFloorObservation" in bot_state
    assert "entry.NativePathFloor = state.LastNativePathFloorObservation" in decision_trace
    for source in (diagnosis, status):
        assert '\\"native_path_floor\\"' in source
        assert '\\"failure\\"' in source
        assert '\\"segment_index\\"' in source
        assert '\\"sample_index\\"' in source
        assert '\\"resolved_floor_z\\"' in source
        assert '\\"reference_z\\"' in source
