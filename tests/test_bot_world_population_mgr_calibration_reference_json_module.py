from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationReferenceJson.cpp"
REPORT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationRows.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_calibration_reference_json_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCalibrationReferenceJson.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::AppendCalibrationReferenceConditionJson" in text
    assert "AppendCalibrationReferenceConditionJson" in HEADER.read_text()


def test_calibration_reference_json_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "AppendCalibrationReferenceConditionJson(json, state, metrics, fixtureSpecContract);" in REPORT.read_text()
    assert 'json << ",\\"reference_condition_observation\\"' not in text


def test_calibration_reference_json_keeps_condition_contract():
    text = MODULE.read_text()
    for marker in (
        "fixture_contract_sha256",
        "required_setup_aura_spell_ids",
        "player_auras",
        "target_auras",
        "target_stacked_auras",
        "external_bleed_aura_spell_ids",
        "dynamic_disabled",
    ):
        assert marker in text


def test_calibration_reference_json_attributes_other_item_uses_without_changing_tinker_count():
    text = MODULE.read_text()
    header = HEADER.read_text()

    assert (
        '\\"tinker_use_count\\":"\n'
        "                 << (metrics ? metrics->ScoredTinkerOrOtherItemUseCount\n"
        "                        + metrics->ScoredTinkerSpellUseCount : 0)" in text
    )
    assert '\\"other_item_use_count\\":"' in text
    assert "(metrics ? metrics->ScoredOtherItemUseCount : 0)" in text
    assert '\\"other_item_uses\\":[' in text
    for marker in (
        '{\\"spell_id\\":" << otherUse.SpellId',
        ',\\"item_entry\\":" << otherUse.ItemEntry',
        ',\\"count\\":" << otherUse.UseCount',
    ):
        assert marker in text
    assert "struct ScoredOtherItemUse" in header
    assert "std::array<ScoredOtherItemUse, 8> ScoredOtherItemUses;" in header
