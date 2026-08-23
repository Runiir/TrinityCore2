from pathlib import Path

from tools.bot_ml.review_rotation_mechanics import normalize_runtime_report


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationMetrics.h"
OBSERVATION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrWillOfUnbinding.cpp"
CALIBRATION_BOT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationBot.cpp"
COMBAT_NOTIFICATIONS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatNotifications.cpp"
JSON = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationBotJson.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_will_of_unbinding_observation_is_bounded_and_scored_only() -> None:
    assert len(OBSERVATION.read_text(encoding="utf-8").splitlines()) < 1000
    header = HEADER.read_text(encoding="utf-8")
    observation = OBSERVATION.read_text(encoding="utf-8")
    calibration_bot = CALIBRATION_BOT.read_text(encoding="utf-8")
    notifications = COMBAT_NOTIFICATIONS.read_text(encoding="utf-8")
    serialized = JSON.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert "BotWorldPopulationMgrWillOfUnbinding.cpp" in cmake
    assert "WillOfUnbindingStackTransition" in header
    assert "WillOfUnbindingObservation" in header
    assert "ObserveWillOfUnbinding(metrics, bot, observationNowMs);" in calibration_bot
    assert "ObserveWillOfUnbinding(calibration->second, owner, nowMs);" in notifications
    assert "MaximumWillOfUnbindingTransitions = 256" in observation
    assert "metrics.WindowStartedMs" in observation
    for field in (
        "stack_aura_spell_id",
        "proc_aura_spell_id",
        "stack_transition_count",
        "stack_increase_count",
        "stack_decrease_count",
        "proc_attempt_observation_available",
        "proc_acceptance_observation_available",
        "scoring_start_effective_intellect",
        "scoring_start_effective_spell_power",
        "stack_transitions",
        "effective_intellect",
        "effective_spell_power",
    ):
        assert field in serialized


def test_will_of_unbinding_normalization_keeps_order_and_proc_limit() -> None:
    runtime = {
        "combat_calibration": {
            "phase": "complete",
            "previous_window": {
                "bots": [
                    {
                        "guid": 1306,
                        "will_of_unbinding": {
                            "schema": "trinity_will_of_unbinding_observation_v1",
                            "stack_aura_spell_id": 109795,
                            "proc_aura_spell_id": 109796,
                            "observation_sample_count": 12,
                            "stack_transition_count": 2,
                            "stack_increase_count": 1,
                            "stack_decrease_count": 1,
                            "proc_attempt_observation_available": False,
                            "proc_acceptance_observation_available": False,
                            "proc_attempt_count": 0,
                            "proc_accepted_count": 0,
                            "proc_observation_basis": "stack_transitions_only",
                            "initial_stacks": 0,
                            "last_observed_stacks": 0,
                            "last_observed_at_ms": 303000,
                            "scoring_start_effective_intellect": 9065.0,
                            "scoring_start_effective_spell_power": 12479,
                            "stack_transitions": [
                                {
                                    "elapsed_ms": 2200,
                                    "previous_stacks": 1,
                                    "current_stacks": 0,
                                    "effective_intellect": 8121.0,
                                    "effective_spell_power": 11535,
                                },
                                {
                                    "elapsed_ms": 1100,
                                    "previous_stacks": 0,
                                    "current_stacks": 1,
                                    "effective_intellect": 9065.0,
                                    "effective_spell_power": 12479,
                                },
                            ],
                        },
                    }
                ]
            },
        }
    }

    normalized = normalize_runtime_report(runtime)

    assert normalized["will_of_unbinding_observations"] == [
        {
            "bot_guid": 1306,
            "schema": "trinity_will_of_unbinding_observation_v1",
            "stack_aura_spell_id": 109795,
            "proc_aura_spell_id": 109796,
            "observation_sample_count": 12,
            "stack_transition_count": 2,
            "stack_increase_count": 1,
            "stack_decrease_count": 1,
            "proc_attempt_observation_available": False,
            "proc_acceptance_observation_available": False,
            "proc_attempt_count": 0,
            "proc_accepted_count": 0,
            "proc_observation_basis": "stack_transitions_only",
            "initial_stacks": 0,
            "last_observed_stacks": 0,
            "last_observed_at_ms": 303000,
            "scoring_start_effective_intellect": 9065.0,
            "scoring_start_effective_spell_power": 12479,
            "stack_transitions": [
                {
                    "elapsed_ms": 1100,
                    "previous_stacks": 0,
                    "current_stacks": 1,
                    "effective_intellect": 9065.0,
                    "effective_spell_power": 12479,
                },
                {
                    "elapsed_ms": 2200,
                    "previous_stacks": 1,
                    "current_stacks": 0,
                    "effective_intellect": 8121.0,
                    "effective_spell_power": 11535,
                },
            ],
        }
    ]
