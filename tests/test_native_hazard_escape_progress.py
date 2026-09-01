from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_native_hazard_escape_progress_predicate_counterexamples(tmp_path):
    source = tmp_path / "native_hazard_escape_progress.cpp"
    binary = tmp_path / "native_hazard_escape_progress"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrNativePathAdmission.h"

#include <cassert>

using namespace BotWorldMovement;
using BotMovementArbitration::Owner;

static NativePathProofObservation CompleteProjectedEndpoint()
{
    NativePathProofObservation proof;
    proof.Available = true;
    proof.Calculated = true;
    proof.PathType = 1; // PATHFIND_NORMAL.
    proof.Complete = true;
    proof.EndpointResult = PathEndpointResult::ReachedProjectedEndPoly;
    proof.CorridorReachedEndPoly = true;
    proof.ResolvedEndpointAvailable = true;
    proof.ActualEndpointMatchedResolved = true;
    proof.EndpointMatched = false;
    proof.EndpointFloorValid = true;
    proof.FloorObservation = {};
    return proof;
}

int main()
{
    NativePathProofObservation const complete = CompleteProjectedEndpoint();
    HazardEscapeBasis const behind{ 9001, -5.0f, 0.0f, 210.0f };

    // A complete native projection on the same surface is useful when its
    // actual endpoint increases clearance from the exact bound hazard.
    HazardEscapeProgressObservation away = ObserveHazardEscapeProgress(
        behind, 0.0f, 0.0f, 8.0f, 0.0f, 210.4f);
    assert(away.Available);
    assert(away.HazardGuid == 9001);
    assert(away.ClearanceProgress == 8.0f);
    assert(NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, false, complete, away));

    // Goal-directed progress is not hazard progress. This endpoint could be
    // closer to an arbitrary request while moving directly toward the source.
    HazardEscapeBasis const ahead{ 9001, 10.0f, 0.0f, 210.0f };
    HazardEscapeProgressObservation closer = ObserveHazardEscapeProgress(
        ahead, 0.0f, 0.0f, 7.5f, 0.0f, 210.4f);
    assert(closer.ClearanceProgress < 0.0f);
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, false, complete, closer));

    HazardEscapeProgressObservation tooSmall = ObserveHazardEscapeProgress(
        behind, 0.0f, 0.0f, 0.5f, 0.0f, 210.0f);
    assert(tooSmall.ClearanceProgress > 0.0f);
    assert(tooSmall.ClearanceProgress
        < NativeHazardEscapeMinimumClearanceProgress);
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, false, complete, tooSmall));

    NativePathProofObservation wrongFloor = complete;
    wrongFloor.EndpointFloorValid = false;
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, false, wrongFloor, away));
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, false, true, false, complete, away));

    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, true, complete, away));

    NativePathProofObservation noPath = complete;
    noPath.Calculated = false;
    noPath.Complete = false;
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, false, false, noPath, away));

    HazardEscapeBasis const missing{};
    HazardEscapeProgressObservation unavailable = ObserveHazardEscapeProgress(
        missing, 0.0f, 0.0f, 8.0f, 0.0f, 210.0f);
    assert(!unavailable.Available);
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Hazard, true, true, false, complete, unavailable));

    // The semantic proof cannot widen ordinary movement admission.
    assert(!NativePathProvesSameSurfaceHazardEscape(
        Owner::Formation, true, true, false, complete, away));
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


def test_hazard_basis_reaches_native_planner_diagnostics_without_admission():
    native_action = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrNativeAction.cpp").read_text(encoding="utf-8")
    movement = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrMovement.cpp").read_text(encoding="utf-8")
    planner = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrMovementPlanner.cpp").read_text(encoding="utf-8")
    diagnostics = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrMovementPlannerDiagnosticsJson.cpp").read_text(
            encoding="utf-8")
    parasite = (ROOT / "src/server/game/Bots/Content/Raids/"
        "BlackwingDescent/Encounters/Magmaw/"
        "BotAdaptiveMagmawParasitePolicy.h").read_text(encoding="utf-8")

    assert "action.HazardEscape" in native_action
    assert "intent.HazardEscape = hazardEscape;" in movement
    assert "ObserveHazardEscapeProgress(" in planner
    assert "NativePathProvesSameSurfaceHazardEscape(" in planner
    assert '\\"hazard_escape_progress\\"' in diagnostics
    assert '\\"resolved_endpoint\\"' in diagnostics
    assert "hazardState->Begin(danger.Guid, danger.Position" in parasite
    assert "move->HazardEscape = BotWorldMovement::HazardEscapeBasis" in parasite

    # The live artifact lacks the exact geometry required to authorize this
    # proof. Keep it diagnostic-only until a receipt-bound replay captures it.
    admission_block = planner[planner.index("plan.HazardEscapeProgress ="):]
    admission_block = admission_block[:admission_block.index(
        "bool const connectedPolyCorridor")]
    assert "segmentSelected = true" not in admission_block


def test_touched_native_headers_remain_below_repository_limit():
    for relative in (
        "src/server/game/Bots/BotHazardEscapeEvidence.h",
        "src/server/game/Bots/BotWorldPopulationMgrMovement.h",
        "src/server/game/Bots/BotWorldPopulationMgrNativePathAdmission.h",
        "src/server/game/Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h",
        "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/"
        "Magmaw/BotMagmawLaneTransition.h",
        "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/"
        "Magmaw/BotAdaptiveMagmawParasitePolicy.h",
    ):
        assert len((ROOT / relative).read_text(encoding="utf-8").splitlines()) < 1000
