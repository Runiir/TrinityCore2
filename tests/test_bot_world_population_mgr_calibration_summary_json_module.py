from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationSummaryJson.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_calibration_summary_json_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCalibrationSummaryJson.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::AppendCombatCalibrationSummaryJson" in text
    assert "AppendCombatCalibrationSummaryJson" in HEADER.read_text()


def test_calibration_summary_json_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "AppendCombatCalibrationSummaryJson(json, nowMs, writeBots);" in text
    assert 'json << "{\\"ok\\":"' not in text


def test_calibration_summary_json_keeps_window_contract():
    text = MODULE.read_text()
    for marker in (
        "botauto_calibrate_status",
        "fixture_target",
        "observed_at_provisioning",
        "scored_passive_observation",
        "execute_threshold_windows",
        "wowsims_cata_single_target_health_schedule_v1",
        "completed_windows",
        "best_windows",
    ):
        assert marker in text


def test_calibration_summary_json_emits_failure_reason_once():
    text = MODULE.read_text()

    assert text.count('\\"failure_reason\\":') == 1
