from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
CALIBRATION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationBot.cpp"
HELPER = ROOT / "src/server/game/Bots/BotCalibrationActionGroupCoverage.h"


def test_selected_action_groups_compile_and_preserve_outcome_sensitivity(
    tmp_path: Path,
) -> None:
    source = CALIBRATION.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")

    assert '#include "Bots/BotCalibrationActionGroupCoverage.h"' in source
    assert "BotClassSpecActionProfileStore::BuildCandidates" not in source
    resolver = source.index("ResolvedCombatAction action = ResolveProfileCombatAction(")
    movement = source.index("if ((action.MinRange", resolver)
    preview_expected = source.index("RecordExpectedActionGroup(", movement)
    assert resolver < preview_expected < movement + 360
    execution = source.index("BotActionResult result = ExecuteProfileCombatAction(")
    final_category = source.index("observedActionCategory", execution)
    final_expected = source.index("RecordExpectedActionGroup(", execution)
    observed = source.index("RecordObservedActionGroup(", execution)
    assert final_category < final_expected < observed
    assert "actionGroup = observedActionCategory" in source[final_category : final_expected]
    assert "result == BotActionResult::Ok" in source[observed : observed + 240]
    assert "metrics.ActionGroups.insert(actionGroup.empty()" not in source

    replay = tmp_path / "calibration_action_group_coverage.cpp"
    replay.write_text(
        r'''
#include "Bots/BotCalibrationActionGroupCoverage.h"

#include <cassert>
#include <set>
#include <string>

enum class Outcome
{
    Ok,
    Failed,
    Casting,
};

struct ActionState
{
    bool Valid;
    std::string Category;
    std::string Type;
};

void ReplayProductionMeasurement(
    std::set<std::string>& expected,
    std::set<std::string>& observed,
    bool scored,
    ActionState const& preview,
    ActionState const& finalAction,
    Outcome outcome,
    bool movementReturn)
{
    std::string actionGroup = preview.Category;
    if (movementReturn)
    {
        BotCalibrationActionGroupCoverage::RecordExpectedActionGroup(
            expected, scored, preview.Valid, actionGroup, preview.Type);
        return;
    }

    // ExecuteProfileCombatAction mutates actionOut and LastActionCategoryByBot
    // when it performs its final resolver pass. The caller re-reads that final
    // category before recording normal execution outcomes.
    actionGroup = finalAction.Category;
    if (finalAction.Valid)
    {
        BotCalibrationActionGroupCoverage::RecordExpectedActionGroup(
            expected, scored, finalAction.Valid, actionGroup, finalAction.Type);
        BotCalibrationActionGroupCoverage::RecordObservedActionGroup(
            observed, scored, finalAction.Valid, outcome == Outcome::Ok,
            actionGroup, finalAction.Type);
    }
}

int main()
{
    std::set<std::string> expected;
    std::set<std::string> observed;

    // The preferred cleave is selected and succeeds; only that selected group
    // contributes to the denominator and numerator.
    ReplayProductionMeasurement(
        expected, observed, true, {true, "cleave", "cast"},
        {true, "cleave", "cast"}, Outcome::Ok, false);
    assert(expected.size() == 1 && expected.count("cleave") == 1);
    assert(observed.size() == 1 && observed.count("cleave") == 1);

    // A later successful builder adds the second selected group; coverage is
    // now complete for both groups.
    ReplayProductionMeasurement(
        expected, observed, true, {true, "builder", "cast"},
        {true, "builder", "cast"}, Outcome::Ok, false);
    assert(expected.size() == 2);
    assert(expected.count("builder") == 1 && expected.count("cleave") == 1);
    assert(observed.size() == 2);
    assert(observed.count("builder") == 1 && observed.count("cleave") == 1);

    // A failed builder is still expected, but cannot count as observed.
    std::set<std::string> failedExpected;
    std::set<std::string> failedObserved;
    ReplayProductionMeasurement(
        failedExpected, failedObserved, true, {true, "builder", "cast"},
        {true, "builder", "cast"}, Outcome::Failed, false);
    assert(failedExpected.size() == 1 && failedExpected.count("builder") == 1);
    assert(failedObserved.empty());

    // Movement-only Casting follows the same failed-observation boundary.
    std::set<std::string> movingExpected;
    std::set<std::string> movingObserved;
    ReplayProductionMeasurement(
        movingExpected, movingObserved, true, {true, "builder", "cast"},
        {true, "builder", "cast"}, Outcome::Casting, true);
    assert(movingExpected.size() == 1 && movingExpected.count("builder") == 1);
    assert(movingObserved.empty());

    // If execution re-resolves, both expected and observed use the final
    // category rather than crediting the preview category.
    std::set<std::string> reroutedExpected;
    std::set<std::string> reroutedObserved;
    ReplayProductionMeasurement(
        reroutedExpected, reroutedObserved, true, {true, "cleave", "cast"},
        {true, "builder", "cast"}, Outcome::Ok, false);
    assert(reroutedExpected.size() == 1 && reroutedExpected.count("builder") == 1);
    assert(reroutedObserved.size() == 1 && reroutedObserved.count("builder") == 1);

    // Invalid actions and warmup/unscored observations do not create groups.
    std::set<std::string> suppressedExpected;
    std::set<std::string> suppressedObserved;
    ReplayProductionMeasurement(
        suppressedExpected, suppressedObserved, true, {false, "wait", "wait"},
        {false, "wait", "wait"}, Outcome::Ok, false);
    ReplayProductionMeasurement(
        suppressedExpected, suppressedObserved, false, {true, "builder", "cast"},
        {true, "builder", "cast"}, Outcome::Ok, false);
    assert(suppressedExpected.empty());
    assert(suppressedObserved.empty());

    return 0;
}
''',
        encoding="utf-8",
    )
    binary = tmp_path / "calibration_action_group_coverage"
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-I",
            str(ROOT / "src/server/game"),
            str(replay),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)

    assert "RecordExpectedActionGroup" in helper
    assert "RecordObservedActionGroup" in helper
