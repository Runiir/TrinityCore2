import hashlib
import json
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
TACTICAL_REPLAY_SUMMARY = ROOT / (
    "experiments/configs/"
    "cata_raid_magmaw_748d63431c_tactical_replay_lite_summary_v1.json"
)
TACTICAL_REPLAY_SUMMARY_SHA256 = (
    "f3f54e4d2da2b17747fba8db885fc72b3920b72a44c4f642e41243a3193508bc"
)
CONSUMED_LAUNCH_SUMMARY = ROOT / (
    "experiments/configs/"
    "cata_raid_magmaw_748d63431c_receipt_tagged_progress_replay_summary_v1.json"
)
CONSUMED_LAUNCH_SUMMARY_SHA256 = (
    "3e3dac61dcd39c6af8c76abe9c17eb505802acf83cec617e67c33f6d6d9fbebd"
)


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


def test_planner_same_level_fallback_still_requires_native_path_proof(tmp_path):
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
    normalized_movement = " ".join(movement.split())

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
    assert "NativePrimaryPathAllowsProgressiveLocalFallback" in admission
    assert "SelectProgressiveLocalMechanicCandidate" in planner
    guard = planner.index("NativePrimaryPathAllowsProgressiveLocalFallback")
    local_fallback = planner.index(
        "selectProgressiveLocalMechanicEndpoint();", guard
    )
    walkable_fallback = planner.index(
        "float const baseAngle = bot->GetAngle", local_fallback
    )
    terminal_rejection = planner.index("if (!segmentSelected)", walkable_fallback)
    assert guard < local_fallback < walkable_fallback < terminal_rejection
    assert "completeNativePathToPoint(candidatePoint" in planner
    assert "native_bounded_same_level_local_step" in planner
    assert "NativeLocalMechanicEndpointMinimumTravel" in planner
    assert "if (targetFloorValid && nativeProof.Calculated" in planner
    assert "&& nativeProof.Complete)" in planner
    assert "native_bounded_same_level_mechanic_endpoint" in planner
    assert 'action = "hold_hazard_exit_retry_backoff"' in movement
    assert (
        "HasArmedRouteHazardRetry( configuredHazard, "
        "matchingRouteHazardRetry, state.ValidationRouteDodgeUntilMs, "
        "nowMs, state.ActivePathValid, state.LastPathRejectReason)"
        in normalized_movement
    )

    source = tmp_path / "route_hazard_retry_reason.cpp"
    binary = tmp_path / "route_hazard_retry_reason"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrBotState.h"

#include <cassert>

using BotWorldPopulationMgrBotState::MovementRejectionIsolation::
    HasArmedRouteHazardRetry;

int main()
{
    assert(HasArmedRouteHazardRetry(
        true, true, 1500, 1000, false,
        "hazard_exit_no_union_safe_native_path"));
    assert(!HasArmedRouteHazardRetry(
        true, true, 1500, 1000, false,
        "route_destination_future_pack_unsafe"));
    assert(!HasArmedRouteHazardRetry(
        true, true, 1500, 1000, true,
        "hazard_exit_no_union_safe_native_path"));
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
            str(ROOT / "src/server/game/Entities/Object"),
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "dep/g3dlite/include"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


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

    // The near-arrival exception cannot relax endpoint identity for a long
    // mechanic path whose actor is still far from the requested destination.
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, false, true, false, canary, 20.0f,
        20.0f, 1.41703f, true));
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
    NativePathProofObservation primaryProof;
    primaryProof.Available = true;
    primaryProof.Calculated = true;
    primaryProof.Complete = primaryPathComplete;
    assert(NativePrimaryPathAllowsProgressiveLocalFallback(primaryProof));
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


def test_receipt519_complete_cross_floor_path_skips_progressive_fallbacks(
    tmp_path,
):
    source = tmp_path / "receipt519_progressive_fallback_gate.cpp"
    binary = tmp_path / "receipt519_progressive_fallback_gate"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrMovementPathSelection.h"
#include "Bots/BotWorldPopulationMgrNativePathAdmission.h"

#include <cassert>

struct Point
{
    float x;
    float y;
    float z;
};

using namespace BotWorldMovement;
using BotMovementArbitration::Owner;

int main()
{
    // a842 receipt 519: the primary path was complete, but its native endpoint
    // resolved from requested z=211.313324 to lower geometry z=-87.556740.
    // The old planner then selected and launched a shorter walkable point.
    NativePathProofObservation receipt519;
    receipt519.Available = true;
    receipt519.Calculated = true;
    receipt519.PathType = 1; // PATHFIND_NORMAL.
    receipt519.Complete = true;
    receipt519.EndpointX = -353.645538f;
    receipt519.EndpointY = -51.6406975f;
    receipt519.EndpointZ = -87.5567398f;
    receipt519.EndpointDistance = 298.870056f;
    receipt519.EndpointHorizontalDistance = 0.0f;
    receipt519.EndpointVerticalDistance = 298.870056f;
    receipt519.EndpointMatched = false;
    receipt519.EndpointFloorValid = true;
    receipt519.FloorObservation = MakeNativePathFloorObservation(
        NativePathFloorFailure::SampleFloorGap, 2, 6,
        -353.396790f, -51.2230797f, 207.974640f,
        -87.4923706f, 212.235764f);
    receipt519.Accepted = NativePathProofPassesAdmission(receipt519);
    assert(!receipt519.Accepted);
    assert(!NativePrimaryPathAllowsProgressiveLocalFallback(receipt519));
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, true, true, false, receipt519,
        20.0f, 25.0f, 4.5f, true));

    Point const actor{ -340.854675f, -30.1652412f, 211.313324f };
    Point const destination{ -353.645538f, -51.6406975f, 211.313324f };
    unsigned localAttempts = 0;
    bool selected = false;
    if (NativePrimaryPathAllowsProgressiveLocalFallback(receipt519))
        selected = SelectProgressiveLocalMechanicCandidate(actor, destination,
            [&](Point const&, float)
            {
                ++localAttempts;
                return true;
            });
    assert(!selected);
    assert(localAttempts == 0);

    // A genuinely incomplete primary path retains local-progress eligibility.
    NativePathProofObservation incomplete = receipt519;
    incomplete.Complete = false;
    assert(NativePrimaryPathAllowsProgressiveLocalFallback(incomplete));
    selected = SelectProgressiveLocalMechanicCandidate(actor, destination,
        [&](Point const&, float fraction)
        {
            ++localAttempts;
            return fraction == 0.5f;
        });
    assert(selected);
    assert(localAttempts == 2);

    // A valid bounded complete endpoint is admitted by the primary-path gate;
    // it does not need or enter progressive fallback.
    NativePathProofObservation bounded = receipt519;
    bounded.EndpointZ = 210.268f;
    bounded.EndpointDistance = 1.41703f;
    bounded.EndpointHorizontalDistance = 0.533746f;
    bounded.EndpointVerticalDistance = 1.31267f;
    bounded.EndpointFloorValid = true;
    bounded.FloorObservation = {};
    assert(NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, false, true, false, bounded,
        1.0f, 1.41703f, 1.41703f, true));
    assert(!NativePrimaryPathAllowsProgressiveLocalFallback(bounded));

    // A genuine cross-floor request is neither a bounded complete endpoint nor
    // eligible for local progressive repair.
    NativePathProofObservation crossFloor = receipt519;
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, false, true, true, false, crossFloor,
        20.0f, 25.0f, 4.5f, false));
    assert(!NativePrimaryPathAllowsProgressiveLocalFallback(crossFloor));
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


def test_canary121_near_arrival_endpoint_is_not_rejected(tmp_path):
    source = tmp_path / "canary121_near_arrival_endpoint.cpp"
    binary = tmp_path / "canary121_near_arrival_endpoint"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrNativePathAdmission.h"

#include <cassert>

using namespace BotWorldMovement;
using BotMovementArbitration::Owner;

int main()
{
    NativePathProofObservation canary;
    canary.Available = true;
    canary.Calculated = true;
    canary.PathType = 1; // PATHFIND_NORMAL.
    canary.Complete = true;
    canary.EndpointX = -309.6f;
    canary.EndpointY = -30.9334f;
    canary.EndpointZ = 210.268f;
    canary.EndpointDistance = 1.41703f;
    canary.EndpointHorizontalDistance = 0.533746f;
    canary.EndpointVerticalDistance = 1.31267f;
    canary.EndpointMatched = false;
    canary.EndpointFloorValid = true;
    canary.FloorObservation = MakeNativePathFloorObservation(
        NativePathFloorFailure::None, 0, 0, -309.6f, -30.9334f,
        210.268f, 210.268f, 211.581f);
    canary.Accepted = NativePathProofPassesAdmission(canary);

    // Canary121 1788013525204, bot 30007: request=(-309.457,-31.4478,
    // 211.581), actual=(-309.6,-30.9334,210.268). The complete native
    // endpoint is floor-valid and near enough to be arrival, but the old
    // progressive proof rejects it because it did not travel 1.5 yards and
    // did not prove two yards of goal reduction.
    assert(!canary.Accepted);
    assert(NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, true, false, true, false, canary, 1.0f,
        1.41703f, 1.41703f, true));

    // The ordinary owner remains strict even when the endpoint is close.
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Formation, true, false, true, false, canary, 1.0f,
        1.41703f, 1.41703f, true));
    // A real cross-floor request cannot opt into arrival merely because its
    // endpoint is near the requested point.
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, false, false, true, false, canary, 1.0f,
        1.41703f, 1.41703f, false));

    NativePathProofObservation crossFloor = canary;
    crossFloor.EndpointVerticalDistance = 8.0f;
    crossFloor.EndpointDistance = 8.0f;
    assert(!NativePathAllowsBoundedSameLevelMechanicProgress(
        Owner::Hazard, false, false, true, false, crossFloor, 1.0f,
        8.0f, 8.0f, true));
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


def test_v71_canary122_production_boundary_remains_explicitly_unclosed():
    tactical_bytes = TACTICAL_REPLAY_SUMMARY.read_bytes()
    assert hashlib.sha256(tactical_bytes).hexdigest() == (
        TACTICAL_REPLAY_SUMMARY_SHA256
    )
    tactical = json.loads(tactical_bytes)
    suspected = tactical["causal_assessment"]["suspected_upstream_receipt"]
    assert suspected == {
        "receipt_id": 598,
        "intent_reason": "ranged_formation_restore",
        "spline_id": 6780,
        "floor_observation_conflict": True,
        "floor_observation_failure": "sample_floor_gap",
        "launched_at_ms": 1788031506261,
        "last_receipt_tagged_sample_at_ms": 1788031506663,
        "sampling_gap_to_state_infection_ms": 3553,
    }
    assert tactical["causal_assessment"]["correlation"] == (
        "same_actor_temporal_predecessor_only"
    )
    assert tactical["causal_assessment"]["exact_missing_field"] == (
        "continuous_receipt_tagged_actor_position_and_spline_identity_from_"
        "receipt_598_last_sample_until_terminal_outcome_or_supersession"
    )

    consumed_bytes = CONSUMED_LAUNCH_SUMMARY.read_bytes()
    assert hashlib.sha256(consumed_bytes).hexdigest() == (
        CONSUMED_LAUNCH_SUMMARY_SHA256
    )
    consumed = json.loads(consumed_bytes)
    receipt = consumed["target_observation"]
    assert receipt["receipt_id"] == 620
    assert receipt["intent_reason"] == "ranged_formation_restore"
    assert receipt["planner_complete"] is True
    assert receipt["planner_path_type"] == 1
    assert receipt["floor_observation_conflict"] is False
    assert receipt["same_receipt_id_in_all_samples"] is True
    assert receipt["same_spline_id_in_all_samples"] is True
    assert receipt["terminal_outcome"] == "selected_endpoint_reached"
    assert receipt["selected_platform_compatible_all_samples"] is True
    assert "canary122_exact_floor_conflicting_seq745_mechanism_recurred" in (
        consumed["claims"]["unproven"]
    )

    # Receipt 598 contains the recorded floor-conflict shape but loses the
    # identity-bound native outcome. Receipt 620 closes the native outcome but
    # contains neither a floor conflict nor a Hazard-owner complete/incomplete
    # counterexample. No one production receipt therefore verifies the three
    # invalidated shared-planner fixture contracts.
    assert suspected["floor_observation_conflict"] is True
    assert tactical["causal_assessment"]["status"] == (
        "localized_not_causally_closed"
    )
    assert receipt["floor_observation_conflict"] is False
