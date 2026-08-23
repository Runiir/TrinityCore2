from __future__ import annotations

from pathlib import Path

from tools.bot_ml.review_rotation_mechanics import (
    _compare_affliction_landed_events,
    normalize_runtime_report,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrAfflictionLandedEvent.cpp"
METRICS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationMetrics.h"
NOTIFICATIONS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatNotifications.cpp"
CALIBRATION_BOT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationBot.cpp"
JSON = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationBotJson.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_affliction_landed_event_module_is_bounded_and_calibration_only() -> None:
    module = MODULE.read_text(encoding="utf-8")
    metrics = METRICS.read_text(encoding="utf-8")
    notifications = NOTIFICATIONS.read_text(encoding="utf-8")
    calibration_bot = CALIBRATION_BOT.read_text(encoding="utf-8")
    serialized = JSON.read_text(encoding="utf-8")

    assert len(module.splitlines()) < 1000
    assert "BotWorldPopulationMgrAfflictionLandedEvent.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    assert "struct AfflictionLandedEvent" in metrics
    assert "std::vector<AfflictionLandedEvent> AfflictionLandedEvents;" in metrics
    assert "ObserveAfflictionLandedEvent(calibration->second" in notifications
    assert "criticalOutcomeAvailable" in notifications
    assert "metrics.AfflictionLandedEvents.size() >= MaxAfflictionLandedEvents" in module
    assert "ProcSnapshotAvailable = false" in module
    assert "native_damage_callback_has_no_attributable_proc_context" in module
    assert "AppendAfflictionLandedEventJson(metrics)" in serialized
    assert "affliction_landed_events" in module
    assert "affliction_soulburn_decisions" in module
    assert "ObserveAfflictionSoulburnDecision" in calibration_bot
    assert "POWER_SOUL_SHARDS" in calibration_bot


def test_normalize_affliction_events_preserves_identity_damage_and_availability() -> None:
    runtime = {
        "combat_calibration": {
            "phase": "complete",
            "previous_window": {
                "bots": [
                    {
                        "guid": 1306,
                        "affliction_landed_events": [
                            {
                                "elapsed_ms": 2200,
                                "event_spell_id": 172,
                                "actor_guid": 1306,
                                "owner_guid": 1306,
                                "target_guid": 77,
                                "root_spell_id": 0,
                                "root_spell_identity_available": False,
                                "child_spell_id": 0,
                                "child_spell_identity_available": False,
                                "is_periodic": True,
                                "raw_damage": 347,
                                "raw_damage_available": True,
                                "final_damage": 321,
                                "final_damage_available": True,
                                "measured_damage": 321,
                                "measured_damage_available": True,
                                "critical": True,
                                "critical_outcome_available": True,
                                "crit_chance_pct": 12.5,
                                "crit_chance_available": True,
                                "actor_spell_power": 812,
                                "actor_stat_snapshot_available": True,
                                "aura_snapshot_available": True,
                                "proc_snapshot_available": False,
                            },
                            {
                                "elapsed_ms": 1100,
                                "event_spell_id": 686,
                                "actor_guid": 1306,
                                "owner_guid": 1306,
                                "target_guid": 77,
                                "root_spell_id": 0,
                                "root_spell_identity_available": False,
                                "child_spell_id": 0,
                                "child_spell_identity_available": False,
                                "is_periodic": False,
                                "raw_damage": 250,
                                "raw_damage_available": True,
                                "final_damage": 200,
                                "final_damage_available": True,
                                "measured_damage": 200,
                                "measured_damage_available": True,
                                "critical": False,
                                "critical_outcome_available": False,
                                "crit_chance_available": False,
                                "actor_stat_snapshot_available": True,
                                "aura_snapshot_available": True,
                                "proc_snapshot_available": False,
                            },
                        ],
                        "affliction_soulburn_decisions": [
                            {
                                "elapsed_ms": 1000,
                                "chosen_spell_id": 74434,
                                "soulburn_power_before": 3,
                                "soulburn_power_after": 2,
                                "soulburn_power_available": True,
                                "soulburn_power_changed": True,
                                "candidate_observation_available": True,
                                "result": "ok",
                                "candidate_rejections": '[{"spell_id":6353,"reason":"missing_self_aura"}]',
                            }
                        ],
                    }
                ]
            },
        }
    }

    normalized = normalize_runtime_report(runtime)

    assert [event["event_spell_id"] for event in normalized["affliction_landed_events"]] == [
        686,
        172,
    ]
    periodic = normalized["affliction_landed_event_summary"]["1306:172:periodic"]
    assert periodic["event_count"] == 1
    assert periodic["raw_damage"] == 347
    assert periodic["final_damage"] == 321
    assert periodic["critical_outcome_count"] == 1
    assert periodic["critical_count"] == 1
    direct = normalized["affliction_landed_event_summary"]["1306:686:direct"]
    assert direct["critical_outcome_count"] == 0
    assert direct["root_identity_available_count"] == 0
    assert direct["child_identity_available_count"] == 0
    assert normalized["affliction_soulburn_decisions"][0][
        "candidate_rejections"
    ] == [{"spell_id": 6353, "reason": "missing_self_aura"}]


def test_affliction_landed_review_compares_cadence_and_damage_per_event() -> None:
    runtime = normalize_runtime_report(
        {
            "combat_calibration": {
                "phase": "complete",
                "previous_window": {
                    "bots": [
                        {
                            "guid": 1306,
                            "affliction_landed_events": [
                                {
                                    "event_spell_id": 172,
                                    "is_periodic": True,
                                    "measured_damage": 300,
                                    "final_damage": 300,
                                    "raw_damage": 330,
                                    "critical_outcome_available": True,
                                    "critical": False,
                                }
                            ],
                        }
                    ]
                },
            }
        }
    )
    comparison = _compare_affliction_landed_events(
        {
            "first_iteration_duration_seconds": 300.0,
            "action_metrics": [
                {
                    "identity": {"kind": "spell", "id": 172},
                    "is_passive": False,
                    "per_iteration_target_metric_sums": {
                        "ticks": 2.0,
                        "crit_ticks": 1.0,
                        "damage": 900.0,
                    },
                }
            ],
        },
        runtime,
    )

    record = comparison["records"][0]
    assert record["wowsims_event_count"] == 3.0
    assert record["runtime_event_count"] == 1
    assert record["wowsims_damage_per_event"] == 300.0
    assert record["runtime_damage_per_event"] == 300.0
