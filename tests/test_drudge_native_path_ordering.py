from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DRUDGE_GEOMETRY = ROOT / (
    "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
    "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
)
DRUDGE_DECISION = ROOT / (
    "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
    "BotRaidDrudgeNativePathDecision.h"
)
PATH_VALIDATION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativePathValidation.h"


def test_strict_native_path_keeps_complete_floor_gates_before_ordered_post_floor_diagnostics():
    source = DRUDGE_GEOMETRY.read_text(encoding="utf-8")
    strict_path = source[source.index("StrictNativePath ="):source.index(
        "StrictTankRecoveryPath =", source.index("StrictNativePath =")
    )]

    complete = strict_path.index("NativePathIsComplete(pathOk, path)")
    floor = strict_path.index("DiagnoseNativePathFloors(Bot, path,")
    endpoint = strict_path.index("EvaluatePostFloor")
    source_union = strict_path.index("SourceUnionPathSafe(path)")
    assert complete < floor < endpoint < source_union
    assert "BotRaidDrudgeNativePathDecision.h" in source
    assert "PATHFIND_INCOMPLETE" in PATH_VALIDATION.read_text(encoding="utf-8")


def test_post_floor_diagnostics_are_lazy_and_intermediate_path_rejection_is_deterministic(tmp_path):
    source = tmp_path / "drudge_native_path_ordering.cpp"
    binary = tmp_path / "drudge_native_path_ordering"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeNativePathDecision.h"
#include <cassert>

using namespace BotRaidDrudgeNativePath;

int main()
{
    bool sourceUnionConsulted = false;
    auto endpointMiss = EvaluatePostFloor(
        true, true, 0.26f, 0.0f,
        [&sourceUnionConsulted]()
        {
            sourceUnionConsulted = true;
            return false;
        });
    assert(endpointMiss == PostFloorDecision::NativeEndpointRejected);
    assert(!sourceUnionConsulted);

    auto unsafeIntermediate = EvaluatePostFloor(
        true, true, 0.0f, 0.0f,
        [&sourceUnionConsulted]()
        {
            sourceUnionConsulted = true;
            return false;
        });
    assert(unsafeIntermediate == PostFloorDecision::SourceUnionRejected);
    assert(sourceUnionConsulted);

    auto exactAndSafe = EvaluatePostFloor(
        true, true, 0.25f, 1.0f,
        []() { return true; });
    assert(exactAndSafe == PostFloorDecision::Accepted);

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


def test_native_path_decision_header_stays_small():
    assert len(DRUDGE_DECISION.read_text(encoding="utf-8").splitlines()) < 1000
