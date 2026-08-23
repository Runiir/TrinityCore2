from pathlib import Path

from tools.bot_ml.review_rotation_mechanics import normalize_runtime_report


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
SPELL_AURA_EFFECTS = ROOT / "src/server/game/Spells/Auras/SpellAuraEffects.cpp"
MODULE = BOT_DIR / "BotWorldPopulationMgrDragonwrath.cpp"
METRICS = BOT_DIR / "BotWorldPopulationMgrCalibrationMetrics.h"
CALIBRATION_JSON = BOT_DIR / "BotWorldPopulationMgrCalibrationBotJson.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_native_diagnostic_is_bounded_registered_and_scoped_to_the_scored_bot():
    module = MODULE.read_text(encoding="utf-8")
    header = (BOT_DIR / "BotWorldPopulationMgr.h").read_text(encoding="utf-8")
    aura = SPELL_AURA_EFFECTS.read_text(encoding="utf-8")

    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrDragonwrath.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    assert "NotifyDragonwrathCopyProcAttempt" in header
    assert "GetId() == DragonwrathAuraSpellId" in aura
    assert "triggeredSpellInfo->Id" in aura
    assert "castResult == SPELL_CAST_OK" in aura
    for marker in (
        'Cohort().CalibrationMode != "single_target_300"',
        "Cohort().CalibrationScoredStartedMs",
        "Cohort().CalibrationWindowComplete",
        "caster->ToPlayer()",
        "bot->HasAura(DragonwrathAuraSpellId)",
        "CalibrationMetricsByGuid.find",
        "DragonwrathCopyProcs[originalSpellId]",
    ):
        assert marker in module
    reset = (BOT_DIR / "BotWorldPopulationMgrCalibrationReset.cpp").read_text(
        encoding="utf-8"
    )
    assert "metrics.DragonwrathCopyProcs.clear()" in reset


def test_calibration_json_exposes_attempt_acceptance_and_landed_limit():
    metrics = METRICS.read_text(encoding="utf-8")
    rendered = CALIBRATION_JSON.read_text(encoding="utf-8")

    for marker in (
        "DragonwrathCopyProcObservation",
        "DragonwrathCopyProcs",
        "aura_spell_id",
        "original_spell_id",
        "attempt_count",
        "accepted_count",
        "rejected_count",
        'landed_damage_attribution_available',
        "spell_context_not_carried_into_notify_combat_damage",
    ):
        assert marker in metrics or marker in rendered


def test_runtime_normalization_keeps_dragonwrath_rows_bound_to_each_bot():
    report = {
        "combat_calibration": {
            "phase": "complete",
            "previous_window": {
                "bots": [
                    {
                        "guid": 101,
                        "dragonwrath_copy_proc": {
                            "aura_spell_id": 101056,
                            "copy_spell_id_semantics": "original_triggering_spell_id",
                            "landed_damage_attribution_available": False,
                            "landed_damage_attribution_limitation": "spell_context_not_carried_into_notify_combat_damage",
                            "attempts": [
                                {
                                    "original_spell_id": 47897,
                                    "attempt_count": 3,
                                    "accepted_count": 2,
                                    "rejected_count": 1,
                                    "last_cast_result": 6,
                                }
                            ],
                        },
                    },
                    {
                        "guid": 202,
                        "dragonwrath_copy_proc": {
                            "aura_spell_id": 101056,
                            "copy_spell_id_semantics": "original_triggering_spell_id",
                            "landed_damage_attribution_available": False,
                            "landed_damage_attribution_limitation": "spell_context_not_carried_into_notify_combat_damage",
                            "attempts": [],
                        },
                    },
                ]
            },
        }
    }

    normalized = normalize_runtime_report(report)

    assert normalized["dragonwrath_copy_proc_observations"] == [
        {
            "bot_guid": 101,
            "aura_spell_id": 101056,
            "copy_spell_id_semantics": "original_triggering_spell_id",
            "landed_damage_attribution_available": False,
            "landed_damage_attribution_limitation": "spell_context_not_carried_into_notify_combat_damage",
            "attempts": [
                {
                    "original_spell_id": 47897,
                    "attempt_count": 3,
                    "accepted_count": 2,
                    "rejected_count": 1,
                    "last_cast_result": 6,
                }
            ],
        },
        {
            "bot_guid": 202,
            "aura_spell_id": 101056,
            "copy_spell_id_semantics": "original_triggering_spell_id",
            "landed_damage_attribution_available": False,
            "landed_damage_attribution_limitation": "spell_context_not_carried_into_notify_combat_damage",
            "attempts": [],
        },
    ]
