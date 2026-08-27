from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / (
    "src/server/game/Bots/"
    "BotWorldPopulationMgrValidationRouteDestination.h"
)
RUNTIME = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteRuntime.cpp"


def test_manifest_transition_adopts_current_navigation_anchor_and_rejects_non_finite_input(
    tmp_path,
):
    source = tmp_path / "validation_route_destination.cpp"
    binary = tmp_path / "validation_route_destination"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrValidationRouteDestination.h"
#include <cassert>
#include <limits>
#include <string>

using namespace BotValidationRouteDestination;

int main()
{
    auto current = Resolve({669, -307.531f, -35.4375f, 211.815f});
    assert(current.Valid);
    assert(current.NextAction == Action::MoveToCurrentNavigationAnchor);
    assert(current.MapId == 669);
    assert(current.X == -307.531f);
    assert(current.Y == -35.4375f);
    assert(current.Z == 211.815f);
    assert(std::string(current.Reason)
        == "validation_route_manifest_navigation_anchor");

    auto invalid = Resolve({669, -307.531f,
        std::numeric_limits<float>::quiet_NaN(), 211.815f});
    assert(!invalid.Valid);
    assert(invalid.NextAction == Action::InvalidateStaleDestination);
    assert(std::string(invalid.Reason)
        == "validation_route_destination_invalid");
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


def test_route_runtime_seeds_destination_after_manifest_reset():
    source = RUNTIME.read_text(encoding="utf-8")
    helper = source.index(
        "BotValidationRouteDestination::Result const routeDestination"
    )
    reset = source.index(
        'ResetValidationRouteRuntimeState(reason ? reason : "manifest_route_apply");',
        helper,
    )
    seed = source.index("state.QuestRouteDestination.Valid = routeDestination.Valid", reset)
    assert helper < reset < seed
    assert "state.QuestRouteDestination.Reason = routeDestination.Reason" in source


def test_validation_route_destination_header_stays_small():
    assert len(HEADER.read_text(encoding="utf-8").splitlines()) < 1000
