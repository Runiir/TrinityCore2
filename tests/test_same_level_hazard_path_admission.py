import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
MOVEMENT = BOT_DIR / "BotWorldPopulationMgrMovement.h"
PLANNER = BOT_DIR / "BotWorldPopulationMgrMovementPlanner.cpp"


HARNESS = r"""
#include "Bots/BotWorldPopulationMgrMovement.h"

#include <cassert>

using BotMovementArbitration::Owner;

int main()
{
    using BotWorldMovement::AllowsSameLevelLocalMechanicProgress;

    assert(AllowsSameLevelLocalMechanicProgress(
        Owner::Hazard, true, 14.24f, false, false));
    assert(AllowsSameLevelLocalMechanicProgress(
        Owner::Mechanic, true, 1.15f, false, false));

    assert(!AllowsSameLevelLocalMechanicProgress(
        Owner::Hazard, false, 14.24f, false, false));
    assert(!AllowsSameLevelLocalMechanicProgress(
        Owner::Hazard, true, 20.01f, false, false));
    assert(!AllowsSameLevelLocalMechanicProgress(
        Owner::Hazard, true, 14.24f, true, false));
    assert(!AllowsSameLevelLocalMechanicProgress(
        Owner::Recovery, true, 14.24f, false, false));
    assert(!AllowsSameLevelLocalMechanicProgress(
        Owner::Route, true, 14.24f, false, false));
    assert(!AllowsSameLevelLocalMechanicProgress(
        Owner::CombatRange, true, 14.24f, false, false));
}
"""


def test_same_level_mechanic_admission_contract(tmp_path: Path) -> None:
    harness = tmp_path / "same_level_mechanic_admission.cpp"
    binary = tmp_path / "same_level_mechanic_admission"
    harness.write_text(HARNESS, encoding="utf-8")
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
            str(harness),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_planner_reuses_validated_backoff_without_broad_owner_bypass() -> None:
    planner = PLANNER.read_text(encoding="utf-8")
    movement = MOVEMENT.read_text(encoding="utf-8")

    assert "AllowsSameLevelLocalMechanicProgress" in movement
    assert "progressivePathAdmission = progressiveStaticRoute" in planner
    assert "|| sameLevelLocalMechanicProgress" in planner
    assert "!strictNativeDescent && progressivePathAdmission" in planner
    assert "if (!segmentSelected && progressivePathAdmission" in planner
    assert "[bot, &pathReferenceFloorZ]" in planner
    assert "*pathReferenceFloorZ, true" in planner


def test_changed_native_files_remain_bounded() -> None:
    for path in (MOVEMENT, PLANNER):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000
