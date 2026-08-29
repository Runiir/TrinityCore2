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
    assert "float const declaredReferenceZ = z;" in geometry
    assert "DiagnoseNativePathFloors(Bot, path,\n                declaredReferenceZ, true)" in geometry
    assert "NativePathFloorFailure::SampleFloorGap" in validation
    assert "NativePathFloorFailure::ActorReferenceGap" in validation
    assert "NativePathFloorObservationBlocksCompleteProof" in validation
    assert "case NativePathFloorFailure::SampleFloorUnavailable:" in validation
    assert "case NativePathFloorFailure::SampleFloorGap:" in validation


def test_planner_same_level_fallback_still_requires_native_path_proof():
    planner = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementPlanner.cpp"
    ).read_text(encoding="utf-8")
    validation = PATH_VALIDATION.read_text(encoding="utf-8")
    movement = (
        ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrValidationRouteMovementCheck.cpp"
    ).read_text(encoding="utf-8")

    assert "AdmitSameLevelDeclaredFloorFallback" in planner
    assert "&& !sameLevelDeclaredFloorFallback" in planner
    assert "NativePathPointFloorValid(bot," in planner
    assert "*pathReferenceFloorZ,\n                true" in planner
    assert "DiagnoseNativePathFloors(bot," in planner
    assert "NativePathFloorObservationBlocksCompleteProof" in planner
    assert "FloorObservationConflict" in validation
    assert "EndpointMatched" in validation
    assert 'action = "hold_hazard_exit_retry_backoff"' in movement
    assert '== "hazard_exit_no_union_safe_native_path"' in movement


def test_native_path_floor_diagnostic_header_stays_small():
    assert len(FLOOR.read_text(encoding="utf-8").splitlines()) < 1000
    assert len(PATH_VALIDATION.read_text(encoding="utf-8").splitlines()) < 1000


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
