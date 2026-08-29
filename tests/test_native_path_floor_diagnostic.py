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
    assert "SelectProgressiveLocalMechanicCandidate" in planner
    assert "completeNativePathToPoint(candidatePoint" in planner
    assert "native_bounded_same_level_local_step" in planner
    assert "NativeLocalMechanicEndpointMinimumTravel" in planner
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


def test_canary120_bounded_complete_mechanic_endpoint_selection(tmp_path):
    source = tmp_path / "canary120_mechanic_endpoint.cpp"
    binary = tmp_path / "canary120_mechanic_endpoint"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrNativePathAdmission.h"

#include <cassert>

using namespace BotWorldMovement;
using BotMovementArbitration::Owner;

static NativePathProofObservation Canary120Proof()
{
    NativePathProofObservation proof;
    proof.Available = true;
    proof.Calculated = true;
    proof.PathType = 1; // PATHFIND_NORMAL, kept lightweight for this fixture.
    proof.Complete = true;
    proof.EndpointX = -297.067f;
    proof.EndpointY = -38.9334f;
    proof.EndpointZ = 210.978f;
    proof.EndpointDistance = 2.68444f;
    proof.EndpointHorizontalDistance = 2.57139f;
    proof.EndpointVerticalDistance = 0.770798f;
    proof.EndpointMatched = false;
    proof.EndpointFloorValid = true;
    proof.FloorObservation = MakeNativePathFloorObservation(
        NativePathFloorFailure::None, 0, 0, -297.067f, -38.9334f,
        210.978f, 210.978f, 211.749f);
    proof.Accepted = NativePathProofPassesAdmission(proof);
    return proof;
}

int main()
{
    NativePathProofObservation const canary = Canary120Proof();
    // The exact request-level probe was 325.293 yards below the declared
    // room floor; only the same-level actor/request declaration can turn it
    // into a reference for later native proof.
    assert(AdmitSameLevelDeclaredFloorFallback(
        211.749f, 211.749f, -113.545f));
    // A later 211.815 -> 160.34 request is a real floor transition, even
    // though its local probe resolves near the requested 157.447 floor.
    assert(!AdmitSameLevelDeclaredFloorFallback(
        211.815f, 160.34f, 157.447f));

    // The generic endpoint identity proof remains strict and fails on the
    // recorded 2.57139-yard horizontal normalization.
    assert(!canary.Accepted);
    assert(!NativePathEndpointComponentsMatch(2.57139f, 0.770798f));

    // Actor=(-299.652,-40.1528,211.749), request=(-295.332,-37.0355,211.749)
    // gives currentGoalDistance=5.32728. The complete native endpoint makes
    // 2.96034 yards of actor travel and leaves 2.68444 yards to the goal, so
    // the bounded local escape makes 2.64276 yards of measurable progress.
    assert(NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, true, true, false, canary, 2.96034f,
        5.32728f, 2.68444f));

    // A lower-floor/cross-floor request has no same-level declaration.
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, false, true, true, false, canary, 2.96034f,
        5.32728f, 2.68444f));

    // The exception remains native-path-backed and progress-bounded.
    NativePathProofObservation incomplete = canary;
    incomplete.Complete = false;
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, true, false, false, incomplete, 2.96034f,
        5.32728f, 2.68444f));
    NativePathProofObservation noFloor = canary;
    noFloor.EndpointFloorValid = false;
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, true, true, false, noFloor, 2.96034f,
        5.32728f, 2.68444f));
    NativePathProofObservation forbidden = canary;
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, true, true, true, forbidden, 2.96034f,
        5.32728f, 2.68444f));
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Formation, true, true, true, false, canary, 2.96034f,
        5.32728f, 2.68444f));
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, true, true, false, canary, 1.499f,
        5.32728f, 2.68444f));
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


def test_canary120_incomplete_path_selects_fresh_complete_local_step(tmp_path):
    source = tmp_path / "canary120_incomplete_local_step.cpp"
    binary = tmp_path / "canary120_incomplete_local_step"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrNativePathAdmission.h"
#include "Bots/BotWorldPopulationMgrMovementPathSelection.h"

#include <cassert>
#include <cmath>

struct Point
{
    float x;
    float y;
    float z;
};

using namespace BotWorldMovement;
using BotMovementArbitration::Owner;

static float Distance(Point const& left, Point const& right)
{
    float const dx = left.x - right.x;
    float const dy = left.y - right.y;
    float const dz = left.z - right.z;
    return std::sqrt(dx * dx + dy * dy + dz * dz);
}

int main()
{
    // Canary120 seq542: the original request had PATHFIND_INCOMPLETE and
    // repeatedly reached the same no-path/unreachable decision family.
    Point const actor{ -289.507f, -42.9803f, 211.882f };
    Point const request{ -295.145f, -29.8647f, 211.882f };
    float const lowerFloor = -108.409f;
    bool const primaryPathComplete = false;
    bool const primaryPathForbidden = true; // no-path equivalence member.
    assert(!primaryPathComplete && primaryPathForbidden);
    assert(AdmitSameLevelDeclaredFloorFallback(
        actor.z, request.z, lowerFloor));

    float const currentGoalDistance = Distance(actor, request);
    Point selected{};
    float selectedFraction = 0.0f;
    unsigned attempts = 0;
    bool const found = SelectProgressiveLocalMechanicCandidate(
        actor, request,
        [&](Point const& candidate, float fraction)
        {
            ++attempts;
            NativeFloorResult const floor = AdmitSameLevelLocalStepFloor(
                actor.z, request.z, lowerFloor);
            assert(floor.Accepted());
            assert(floor.UsesDeclaredFallback());

            // The first shorter point still has no complete native proof;
            // the next point is re-planned and gets a fresh complete proof.
            if (fraction > 0.5f)
                return false;
            Point const endpoint{
                candidate.x - 0.5f, candidate.y - 1.0f,
                candidate.z - 0.770798f
            };
            NativePathProofObservation proof;
            proof.Available = true;
            proof.Calculated = true;
            proof.PathType = 1; // fresh PATHFIND_NORMAL proof.
            proof.Complete = true;
            proof.EndpointX = endpoint.x;
            proof.EndpointY = endpoint.y;
            proof.EndpointZ = endpoint.z;
            // DiagnoseCompleteNativePathProof measures endpoint identity
            // against the freshly requested candidate, not the original
            // hazard destination.  Goal progress below remains relative to
            // the original request.
            proof.EndpointDistance = Distance(endpoint, candidate);
            proof.EndpointHorizontalDistance = std::hypot(
                endpoint.x - candidate.x, endpoint.y - candidate.y);
            proof.EndpointVerticalDistance = std::fabs(
                endpoint.z - candidate.z);
            proof.EndpointMatched = false;
            proof.EndpointFloorValid = true;
            proof.FloorObservation = MakeNativePathFloorObservation(
                NativePathFloorFailure::None, 0, 0, endpoint.x, endpoint.y,
                endpoint.z, endpoint.z, actor.z);
            proof.Accepted = NativePathProofPassesAdmission(proof);
            assert(!proof.Accepted);
            float const endpointTravel = Distance(actor, endpoint);
            float const endpointGoalDistance = Distance(endpoint, request);
            if (!NativePathAllowsBoundedSameLevelMechanicProgress(
                    Owner::Hazard, true, true, proof.Complete, false, proof,
                    endpointTravel, currentGoalDistance,
                    endpointGoalDistance))
                return false;
            assert(endpointTravel >= NativeLocalMechanicEndpointMinimumTravel);
            assert(currentGoalDistance - endpointGoalDistance >= 2.0f);
            selected = endpoint;
            selectedFraction = fraction;
            return true;
        });
    assert(found);
    assert(attempts == 2);
    assert(selectedFraction == 0.5f);
    assert(selected.x != request.x || selected.y != request.y);
    assert(Distance(selected, request) < currentGoalDistance - 2.0f);

    unsigned noCandidateAttempts = 0;
    assert(!SelectProgressiveLocalMechanicCandidate(
        actor, request,
        [&](Point const&, float)
        {
            ++noCandidateAttempts;
            return false;
        }));
    assert(noCandidateAttempts == 4);

    // The declaration cannot turn this into cross-floor or Formation
    // movement, and no incomplete proof can be submitted directly.
    assert(!AdmitSameLevelLocalStepFloor(
        actor.z, 160.34f, 157.447f).Accepted());
    NativePathProofObservation incomplete;
    incomplete.Available = true;
    incomplete.Calculated = true;
    incomplete.Complete = false;
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, true, false, false, incomplete, 8.0f,
        currentGoalDistance, 2.0f));
    NativePathProofObservation formationProof;
    formationProof.Available = true;
    formationProof.Calculated = true;
    formationProof.Complete = true;
    formationProof.EndpointFloorValid = true;
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Formation, true, true, true, false,
        formationProof, 8.0f, currentGoalDistance, 2.0f));
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
