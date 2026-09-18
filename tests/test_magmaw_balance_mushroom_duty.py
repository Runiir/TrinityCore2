from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / (
    "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/"
    "Magmaw/BotMagmawBalanceMushroomDuty.h"
)
SQL = ROOT / "sql/custom/world/2026_09_18_01_magmaw_balance_lava_mushrooms.sql"
ROLLBACK_SQL = ROOT / (
    "sql/custom/rollback/world/"
    "2026_09_18_01_magmaw_balance_lava_mushrooms_rollback.sql"
)
RESOLVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
EXECUTOR = ROOT / "src/server/game/Bots/BotActionExecutor.cpp"
DUTY_SOURCE = HEADER.with_suffix(".cpp")


def test_magmaw_balance_duty_is_closed_and_counted(tmp_path: Path):
    source = tmp_path / "magmaw_balance_mushroom_duty.cpp"
    binary = tmp_path / "magmaw_balance_mushroom_duty"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBalanceMushroomDuty.h"
#include <cassert>

int main()
{
    using Duty = BotEncounter::MagmawBalanceMushroomDuty;
    assert(Duty::IsActive(true, "bwd.magmaw.encounter", "balance_druid", 41806));
    assert(Duty::IsActive(true, "bwd.magmaw.encounter", "balance_druid", 42321));
    assert(Duty::PillarOfFlameEntry == 41843);
    assert(!Duty::IsActive(false, "bwd.magmaw.encounter", "balance_druid", 41806));
    assert(!Duty::IsActive(true, "bwd.magmaw.drudges", "balance_druid", 41806));
    assert(!Duty::IsActive(true, "bwd.magmaw.encounter", "fire", 41806));
    assert(!Duty::IsActive(true, "bwd.magmaw.encounter", "balance_druid", 41570));
    assert(Duty::NeedsPlacement(0));
    assert(Duty::NeedsPlacement(2));
    assert(!Duty::NeedsPlacement(3));
    assert(!Duty::ReadyToDetonate(2));
    assert(Duty::ReadyToDetonate(3));
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-Isrc/server/game", "-Isrc/common", str(source), "-o", str(binary)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    subprocess.run([str(binary)], cwd=tmp_path, check=True)


def test_sql_and_native_path_keep_the_exception_narrow():
    sql = SQL.read_text(encoding="utf-8")
    rollback_sql = ROLLBACK_SQL.read_text(encoding="utf-8")
    resolver = RESOLVER.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")
    duty_source = DUTY_SOURCE.read_text(encoding="utf-8")

    assert "target_selector` = 'ground_enemy'" in sql
    assert "requires_ground_target` = 1" in sql
    assert "target_selector` = 'self'" in sql
    assert "magmaw_lava_parasite_add_duty" in sql
    assert "wild_mushroom,prepull,pinned_apl" in rollback_sql
    assert "target_selector` = 'enemy'" in rollback_sql
    assert "NeedsPlacement" in duty_source
    assert "ReadyToDetonate" in duty_source
    assert "live floor position" in duty_source
    assert "GetHomePosition" not in duty_source
    assert "PillarOfFlameEntry" in duty_source
    assert "FindNearestCreature" in duty_source
    assert "lateralX" in duty_source
    assert "GetHeight" in duty_source
    assert "hintZ + 2.0f" in duty_source
    assert "IsWithinLOS" in duty_source
    assert "ModelIgnoreFlags::M2" in duty_source
    assert "AllowMagmawBalanceMushroomSplash" in executor
    assert "prepull_only" in duty_source
