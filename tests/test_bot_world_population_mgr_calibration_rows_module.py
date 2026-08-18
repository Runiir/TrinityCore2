from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationRows.cpp"
IDENTITY = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationIdentity.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_calibration_rows_module_is_bounded_and_registered():
    text = MODULE.read_text()
    cmake = CMAKE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCalibrationRows.cpp" in cmake
    assert "BotWorldPopulationMgrCalibrationIdentity.cpp" in cmake
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::AppendCombatCalibrationBotRowsJson" in text
    assert "AppendCombatCalibrationBotRowsJson" in HEADER.read_text()


def test_calibration_report_is_not_left_in_monolith():
    source = SOURCE.read_text()
    assert "AppendCombatCalibrationBotRowsJson" in source
    assert 'json << "{\\\"ok\\\":"' not in source
    assert '#include "BotWorldPopulationMgrCalibrationRows.cpp"' not in source


def test_calibration_identity_helpers_have_a_single_extracted_definition():
    rows = MODULE.read_text()
    identity = IDENTITY.read_text()
    assert "ObserveOrdinaryPetSetup" not in SOURCE.read_text()
    assert "OrdinaryPetSetupSnapshot ObserveOrdinaryPetSetup" not in rows
    assert "ObserveOrdinaryPetSetup" in identity
    assert "ObserveActiveOrdinaryHunterPet" in identity
