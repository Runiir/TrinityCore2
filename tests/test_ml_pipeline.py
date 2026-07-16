from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ml.evaluation.evaluate_action_frequency import main as evaluate_main
from ml.group_roles.coordination import ReservationStore
from ml.group_roles.metrics import group_role_metrics
from ml.group_roles.policies import policy_for_role
from ml.raid.metrics import raid_metrics
from ml.raid.scheduler import RaidAssignmentScheduler
from tools.bot_ml.common import DATASET_CONTRACT_VERSION, EXPORT_TABLES, numeric_features, split_by_run_ids
from tools.bot_ml import orchestrator_daemon as daemon
from tools.bot_ml.build_autonomy_master_checklist import refresh_checklist_from_evidence
from tools.bot_ml.build_decision_dataset import build_row, build_rows, filter_rows_by_map, index_decision_fingerprints, index_future_events, index_semantic_stats, label_decision
from tools.bot_ml.extract_world_knowledge import (
    REQUIRED_NONEMPTY_WORLD_MANIFESTS,
    WORLD_MANIFEST_NAMES,
    build_quest_objectives,
    build_rewards,
    database_url_from_worldserver_conf,
    extract_world_knowledge,
    load_existing_world_manifests,
    main as world_knowledge_main,
    parse_trinity_database_info,
    sanitize_database_url,
)
from tools.bot_ml.build_world_planner_manifests import build_planner_manifests, main as world_planner_main
from tools.bot_ml.build_quest_profession_reports import build_report as build_quest_profession_report
from tools.bot_ml.validate_world_planner import STAGED_GATES, main as world_planner_validate_main, validate_manifest_coverage
from tools.bot_ml.build_validation_scenario_manifests import build_manifests as build_validation_scenario_manifests
from tools.bot_ml.build_live_scenario_reports import build_reports as build_live_scenario_reports, build_reports_from_live_reports, main as live_scenario_reports_main
from tools.bot_ml.build_validation_run_plan import build_plan as build_validation_run_plan
from tools.bot_ml.build_validation_run_plan import main as validation_run_plan_main
from tools.bot_ml.build_validation_run_status import build_status as build_validation_run_status
from tools.bot_ml.live_validation_session import (
    LiveValidationSessionError,
    dvc_lock_path,
    dvc_repository_lock,
    ensure_healthy_matching_session,
    build_session,
    inspect_session,
    live_validation_lock,
    sha256_file,
    systemd_transient_command,
)
from tools.bot_ml.run_live_bot_validation import apply_calibration_only_acceptance, boss_route_health_progress, bot_status_snapshot, bounded_console_deadline, build_bot_pool_reset_sql, command_script, heartbeat_commands_from_script, live_validation_report, load_scenario_reports, load_validation_route, main as live_validation_main, parse_json_objects, parse_soap_result, poll_bot_status, read_until_console_prompt, route_segment_complete, run_reusable_validation_session, run_transport_completion_watchdog, run_worldserver, run_worldserver_completion_watchdog, scripted_activation_wait_pending, split_sql_statements, supersede_transient_route_failures, trace_after, trinity_config_bool, unresolved_route_death_loop_count, unresolved_route_stuck_count, upsert_trinity_config, wait_for_bot_status_state, watchdog_state, write_validation_config
from tools.bot_ml.orchestrator_daemon import codex_command, detect_rate_limit, handle_rate_limit, initial_state, run_one_cycle, sleep_until_resume
from tools.bot_ml.generate_lane_configs import write_lane_config
from tools.bot_ml.promote_live_validation_artifact import promote
from tools.bot_ml.build_validation_gear_profiles import SHIELD_CLASSES, build_gem_catalog, build_profiles, build_report, fetch_items, load_gem_properties, load_spell_item_enchantments
from tools.bot_ml.build_validation_provisioning import apply_gear_profiles, bot_known_spell_ids, bot_primary_tree_spell_ids, bot_spell_ids, bot_talent_spell_ids, build_account_insert_sql, build_character_insert_sql, equipment_cache, glyph_item_to_property_map, glyph_property_type_map, load_config as load_validation_provisioning_config, load_gear_profiles, main as provisioning_main, normalized_glyph_slots, normalized_glyphs, runtime_safe_enchantments, scenario_report, srp6_registration_data, talent_point_count, validate_talent_manifest
from tools.bot_ml.validate_validation_provisioning import build_report as provisioning_verify_report
from tools.bot_ml.validate_validation_provisioning import main as provisioning_verify_main
from tools.bot_ml.validate_validation_provisioning import validate_database as validate_provisioning_database
from tools.bot_ml.validation_profile_manifests import load_action_profile_manifest, load_combat_loot_profile_manifest
from tools.bot_ml.validate_data_quality import validate_rows as validate_data_quality_rows
from tools.bot_ml.bt_masked_ga_combined import run as run_bt_masked_ga_combined
from tools.bot_ml.evaluate_policy_model import policy_score, ranking_metrics
from tools.bot_ml.train_policy_model import add_synthetic_binary_class, balanced_binary_weights, teacher_choice_training_rows
from ml.preprocessing.preprocess_frames import main as preprocess_main
from ml.training.train_action_frequency import main as train_main
from experiments.run_experiment import autonomous_metrics, dungeon_route_metrics, load_config, make_adapter, movement_metrics, profession_metrics, quest_metrics, run_experiment, solo_combat_metrics
from ml.autonomous.selector import observe_state, select_task
from ml.autonomous.tasks import FAILURE_HANDLERS, load_tasks
from ml.dungeon.inference import RolePolicyInferenceAdapter
from ml.dungeon.labels import future_labels
from ml.dungeon.planners import DPSPlanner, HealerPlanner, TankPlanner


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.rows = self.conn.query(sql, params)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class ChunkedConsoleProcess:
    class Stdout:
        def fileno(self):
            return 42

    def __init__(self, chunks: list[str]):
        self.chunks = [chunk.encode() for chunk in chunks]
        self.stdout = self.Stdout()

    def poll(self):
        return None if self.chunks else 0


class FakeWorldDb:
    def __init__(self):
        self.closed = False
        self.tables = {
            "quest_template_addon",
            "areatrigger_teleport",
            "transports",
            "graveyard_zone",
            "taxi_level_data",
        }

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True

    def query(self, sql, params=None):
        if sql.startswith("SHOW TABLES LIKE"):
            return [{"table": params[0]}] if params and params[0] in self.tables else []
        if "FROM creature c LEFT JOIN creature_template" in sql:
            return [
                {"guid": 10, "entry": 100, "map_id": 0, "zone_id": 12, "area_id": 40, "x": 1.0, "y": 2.0, "z": 3.0, "o": 0.1, "name": "Questgiver", "subname": "", "npcflag": 2, "type": 7, "rank": 0, "faction": 35},
                {"guid": 11, "entry": 200, "map_id": 0, "zone_id": 12, "area_id": 41, "x": 4.0, "y": 5.0, "z": 6.0, "o": 0.2, "name": "Wolf", "subname": "", "npcflag": 0, "type": 1, "rank": 0, "faction": 14},
                {"guid": 12, "entry": 300, "map_id": 0, "zone_id": 12, "area_id": 40, "x": 7.0, "y": 8.0, "z": 9.0, "o": 0.3, "name": "Trainer", "subname": "", "npcflag": 48, "type": 7, "rank": 0, "faction": 35},
                {"guid": 13, "entry": 301, "map_id": 0, "zone_id": 12, "area_id": 40, "x": 8.0, "y": 9.0, "z": 10.0, "o": 0.4, "name": "Repairer", "subname": "", "npcflag": 4096, "type": 7, "rank": 0, "faction": 35},
            ]
        if "FROM gameobject g LEFT JOIN gameobject_template" in sql:
            return [
                {"guid": 20, "entry": 400, "map_id": 0, "zone_id": 12, "area_id": 42, "x": 10.0, "y": 11.0, "z": 12.0, "o": 0.4, "name": "Quest Chest", "type": 3}
            ]
        if sql == "SELECT * FROM quest_template":
            return [
                {
                    "ID": 9001,
                    "LogTitle": "Wolves and Chests",
                    "QuestLevel": 5,
                    "MinLevel": 4,
                    "QuestSortID": 12,
                    "SuggestedGroupNum": 0,
                    "RequiredFactionId1": 72,
                    "RequiredFactionValue1": 3000,
                    "RequiredFactionId2": 0,
                    "RequiredFactionValue2": 0,
                    "RewardNextQuest": 9002,
                    "POIContinent": 0,
                    "POIx": 4.0,
                    "POIy": 5.0,
                    "POIPriority": 1,
                    "RequiredNpcOrGo1": 200,
                    "RequiredNpcOrGoCount1": 6,
                    "RequiredNpcOrGo2": -400,
                    "RequiredNpcOrGoCount2": 1,
                    "RequiredNpcOrGo3": 0,
                    "RequiredNpcOrGoCount3": 0,
                    "RequiredNpcOrGo4": 0,
                    "RequiredNpcOrGoCount4": 0,
                    "RequiredItemId1": 700,
                    "RequiredItemCount1": 3,
                    "RequiredItemId2": 0,
                    "RequiredItemCount2": 0,
                    "RequiredItemId3": 0,
                    "RequiredItemCount3": 0,
                    "RequiredItemId4": 0,
                    "RequiredItemCount4": 0,
                    "RequiredItemId5": 0,
                    "RequiredItemCount5": 0,
                    "RequiredItemId6": 0,
                    "RequiredItemCount6": 0,
                    "RequiredSpell": 12345,
                    "ObjectiveText1": "Kill wolves",
                    "ObjectiveText2": "Open chest",
                    "ObjectiveText3": "",
                    "ObjectiveText4": "",
                    "RewardItem1": 800,
                    "RewardAmount1": 1,
                    "RewardItem2": 0,
                    "RewardAmount2": 0,
                    "RewardItem3": 0,
                    "RewardAmount3": 0,
                    "RewardItem4": 0,
                    "RewardAmount4": 0,
                    "RewardChoiceItemID1": 801,
                    "RewardChoiceItemQuantity1": 1,
                    "RewardChoiceItemID2": 0,
                    "RewardChoiceItemQuantity2": 0,
                    "RewardChoiceItemID3": 0,
                    "RewardChoiceItemQuantity3": 0,
                    "RewardChoiceItemID4": 0,
                    "RewardChoiceItemQuantity4": 0,
                    "RewardChoiceItemID5": 0,
                    "RewardChoiceItemQuantity5": 0,
                    "RewardChoiceItemID6": 0,
                    "RewardChoiceItemQuantity6": 0,
                }
            ]
        if sql == "SELECT * FROM quest_template_addon":
            return [{"ID": 9001, "PrevQuestID": 9000, "NextQuestID": 9002, "BreadcrumbForQuestId": 0}]
        if "FROM creature_queststarter" in sql:
            return [{"entry": 100, "quest": 9001}]
        if "FROM creature_questender" in sql:
            return [{"entry": 100, "quest": 9001}]
        if "FROM gameobject_queststarter" in sql or "FROM gameobject_questender" in sql:
            return []
        if "FROM npc_vendor" in sql:
            return [{"entry": 300, "item": 700, "maxcount": 0, "incrtime": 0, "ExtendedCost": 0, "type": 1, "PlayerConditionID": 0}]
        if "FROM trainer t LEFT JOIN trainer_spell" in sql:
            return [{"trainer_id": 500, "trainer_type": 2, "spell_id": 600, "money_cost": 100, "req_skill_line": 185, "req_skill_rank": 1, "req_ability1": 0, "req_level": 5}]
        if "FROM creature_trainer" in sql:
            return [{"entry": 300, "trainer_id": 500, "menu_id": 1, "option_id": 1}]
        if "FROM creature_loot_template" in sql:
            return [{"source_entry": 200, "item_id": 700, "reference": 0, "chance": 75.0, "quest_required": 1, "min_count": 1, "max_count": 1}]
        if "FROM gameobject_loot_template" in sql:
            return [{"source_entry": 400, "item_id": 701, "reference": 0, "chance": 100.0, "quest_required": 1, "min_count": 1, "max_count": 1}]
        if sql == "SELECT * FROM areatrigger_teleport":
            return [{"ID": 1, "Name": "Portal", "target_map": 1, "target_position_x": 2.0, "target_position_y": 3.0, "target_position_z": 4.0, "target_orientation": 0.5}]
        if sql == "SELECT * FROM transports":
            return [{"guid": 1, "entry": 2, "name": "Boat"}]
        if sql == "SELECT * FROM graveyard_zone":
            return [{"ID": 1, "GhostZone": 12, "Faction": 0, "Comment": "Elwynn"}]
        if sql == "SELECT * FROM taxi_level_data":
            return [{"ID": 1, "Level": 1}]
        raise AssertionError(sql)


def test_preprocess_train_evaluate_pipeline(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    processed = tmp_path / "processed" / "frames.jsonl"
    manifest = tmp_path / "processed" / "manifest.json"
    model = tmp_path / "models" / "action_frequency_model.json"
    metrics = tmp_path / "evaluations" / "metrics.json"
    report = tmp_path / "evaluations" / "report.json"

    write_jsonl(raw_dir / "run_000001" / "frames.jsonl", [
        {
            "episode_id": "run_000001",
            "frame_id": 1,
            "domain": "system_smoke",
            "trigger": "task_change",
            "resolved_action": {"command": "playerbot status"},
        }
    ])

    monkeypatch.setattr("sys.argv", ["preprocess", "--raw-dir", str(raw_dir), "--output", str(processed), "--manifest", str(manifest)])
    assert preprocess_main() == 0

    monkeypatch.setattr("sys.argv", ["train", "--frames", str(processed), "--model", str(model)])
    assert train_main() == 0

    monkeypatch.setattr("sys.argv", ["evaluate", "--frames", str(processed), "--model", str(model), "--metrics", str(metrics), "--report", str(report)])
    assert evaluate_main() == 0

    loaded_metrics = json.loads(metrics.read_text(encoding="utf-8"))
    assert loaded_metrics["frame_count"] == 1
    assert loaded_metrics["known_action_rate"] == 1.0
    assert loaded_metrics["unique_actions"] == 1


def test_preprocess_normalizes_autonomy_sidecar_events(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    processed = tmp_path / "processed" / "frames.jsonl"
    manifest = tmp_path / "processed" / "manifest.json"
    write_jsonl(
        raw_dir / "run_000001" / "autonomy_decisions_auto_smoke_000001.jsonl",
        [
            {
                "session_id": "auto_smoke_000001",
                "event_type": "autonomy_decision",
                "bot_guid": 50101,
                "execution_mode": "headless_ra_soap",
                "live_client_present": False,
                "persona": {"role": "tank"},
                "context_summary": {"map": 0},
                "group_context": {"members": 1},
                "candidates": [{"candidate_id": "quest_28808_kill", "domain": "questing", "intent": "complete_nearby_quest_objective", "score": 1.7}],
                "chosen": {"candidate_id": "quest_28808_kill", "domain": "questing", "intent": "complete_nearby_quest_objective"},
                "score_components": {"quest": 0.78},
                "t": 1.5,
            }
        ],
    )
    write_jsonl(
        raw_dir / "run_000001" / "progression_events_auto_smoke_000001.jsonl",
        [{"session_id": "auto_smoke_000001", "event_type": "autonomy_progress", "bot_guid": 50101, "domain": "questing", "result": "failed", "tick": 3}],
    )

    monkeypatch.setattr("sys.argv", ["preprocess", "--raw-dir", str(raw_dir), "--output", str(processed), "--manifest", str(manifest)])
    assert preprocess_main() == 0
    rows = [json.loads(line) for line in processed.read_text(encoding="utf-8").splitlines()]
    loaded_manifest = json.loads(manifest.read_text(encoding="utf-8"))

    assert loaded_manifest["frame_count"] == 2
    assert rows[0]["episode_id"] == "auto_smoke_000001"
    assert rows[0]["domain"] == "questing"
    assert rows[0]["trigger"] == "autonomy_decision"
    assert rows[0]["actor"]["guid"] == 50101
    assert rows[0]["resolved_action"]["candidate_id"] == "quest_28808_kill"
    assert rows[1]["outcome"]["result"] == "failed"


def test_bot_ml_export_table_contract_covers_learning_loop_tables():
    assert EXPORT_TABLES == [
        "experiment_bot_runs",
        "experiment_bot_segments",
        "experiment_bot_events",
        "experiment_bot_decisions",
        "experiment_bot_activities",
        "experiment_bot_replay_records",
        "experiment_bot_clips",
        "experiment_bot_clip_frames",
        "bot_semantic_outcome_stats",
        "bot_memory_pois",
        "bot_memory_danger_zones",
        "bot_memory_failed_paths",
        "bot_memory_safe_positions",
        "bot_memory_objective_clusters",
        "bot_memory_recipe_sources",
        "bot_memory_material_sources",
        "bot_memory_daily_cooldowns",
        "bot_memory_transport_usage",
        "bot_memory_decision_fingerprints",
        "bot_policy_models",
        "bot_policy_evaluations",
    ]


def test_bot_ml_decision_builder_adds_semantic_outcome_stat_features():
    stats = index_semantic_stats([
        {"entity_type": "area", "entity_key": 44, "samples": 10, "failures": 1, "deaths": 0, "avg_reward": 1.5, "danger_score": 0.2, "progression_value": 0.8},
        {"entity_type": "mob", "entity_key": 123, "samples": 5, "failures": 2, "deaths": 1, "avg_reward": -0.5, "danger_score": 0.7, "progression_value": 0.1},
        {"entity_type": "spell", "entity_key": 987, "samples": 3, "failures": 1, "deaths": 1, "avg_reward": -1.0, "danger_score": 0.9, "progression_value": 0.0},
        {"entity_type": "mechanic", "entity_key": 11, "samples": 8, "failures": 3, "deaths": 2, "avg_reward": -0.8, "danger_score": 0.6, "progression_value": 0.2},
    ])
    row = build_row(
        {
            "id": 1,
            "run_id": 7,
            "bot_guid": 99,
            "brain_version": "utility_v1",
            "situation_type": "raid_boss",
            "raw_state_json": json.dumps({"area_id": 44, "target_entry": 123, "target_cast_spell_id": 987}),
            "semantic_state_json": "{}",
            "candidate_actions_json": "[]",
            "chosen_action_json": json.dumps({"activity_score": 1.0}),
            "outcome_json": "{}",
        },
        {},
        stats,
    )

    assert row["stat_area_samples"] == 10
    assert row["stat_mob_deaths"] == 1
    assert row["stat_spell_danger_score"] == 0.9
    assert row["stat_mechanic_failures"] == 3
    assert row["features_hash"]


def test_bot_ml_decision_builder_emits_candidate_rows_with_observed_chosen_label():
    rows = build_rows(
        {
            "id": 1,
            "run_id": 7,
            "bot_guid": 99,
            "brain_version": "utility_v1",
            "candidate_actions_json": json.dumps([
                {"activity": "quest", "score": 1.5, "learned_score": 0.2, "confidence": 0.8},
                {"activity": "grind", "score": 0.5, "learned_score": 0.1, "confidence": 0.4},
            ]),
            "chosen_action_json": json.dumps({"activity": "quest", "activity_score": 1.5}),
            "raw_state_json": "{}",
            "semantic_state_json": "{}",
            "outcome_json": "{}",
            "reward": 1.0,
            "is_failure": 0,
        },
        {},
        {},
    )

    assert len(rows) == 2
    assert [row["candidate_activity"] for row in rows] == ["quest", "grind"]
    assert [row["label_observed"] for row in rows] == [1, 0]
    assert rows[0]["expected_reward"] == 1.0
    assert rows[1]["expected_reward"] == 0.0
    assert rows[0]["imitate_teacher"] == 1
    assert rows[0]["imitation_weight"] == 1.0
    assert rows[0]["teacher_action_quality"] == "verified_teacher_action"
    assert rows[0]["dataset_contract_version"] == DATASET_CONTRACT_VERSION
    assert rows[0]["candidate_mask"] == {"allowed": True, "reason": ""}
    assert rows[0]["candidate_allowed"] == 1
    assert rows[0]["candidate_domain"] == "unknown"
    assert rows[0]["failure_label"] == ""
    assert rows[1]["imitate_teacher"] == 0
    assert rows[1]["teacher_action_quality"] == "candidate_unobserved"
    assert rows[0]["trace"]["candidate_activity"] == "quest"
    assert rows[0]["trace"]["dataset_contract_version"] == DATASET_CONTRACT_VERSION


def test_bot_ml_decision_builder_materializes_structured_mask_candidates():
    rows = build_rows(
        {
            "id": 1,
            "run_id": 7,
            "bot_guid": 99,
            "brain_version": "utility_v1",
            "candidate_actions_json": json.dumps(
                {
                    "schema": "bot_decision_mask_v2",
                    "activity_candidates": [
                        {"activity": "heroic_raid", "score": -2.0},
                        {"activity": "experiment_exploration", "score": -1.0},
                    ],
                    "combat_action_mask": {
                        "actions": [
                            {"action_id": 954428, "spell_id": 54428, "action_category": "buff", "score": 0.7, "reject_reason": ""},
                            {"action_id": 1962124, "spell_id": 62124, "action_category": "taunt", "score": 1.27, "reject_reason": "out_of_range"},
                        ]
                    },
                }
            ),
            "chosen_action_json": json.dumps(
                {
                    "action": "validation_route_stuck",
                    "activity": "experiment_exploration",
                    "activity_score": -1.0,
                    "structured_action": {"action_id": 954428, "spell_id": 54428, "action_category": "buff"},
                }
            ),
            "raw_state_json": "{}",
            "semantic_state_json": "{}",
            "outcome_json": "{}",
            "reward": 1.0,
        },
        {},
        {},
    )

    assert len(rows) == 4
    assert {row["candidate_domain"] for row in rows} == {"activity_selection", "combat_action"}
    assert [row["candidate_allowed"] for row in rows] == [1, 1, 1, 0]
    assert rows[2]["candidate_activity"] == "buff"
    assert rows[2]["is_chosen"] == 1
    assert rows[2]["label_observed"] == 1
    assert rows[3]["candidate_mask"] == {"allowed": False, "reason": "out_of_range"}


def test_bot_ml_decision_builder_filters_teacher_source_by_map():
    rows = [
        {"id": 1, "map_id": 725},
        {"id": 2, "map_id": 1},
        {"id": 3, "map_id": 725},
    ]

    assert [row["id"] for row in filter_rows_by_map(rows, {725})] == [1, 3]
    assert filter_rows_by_map(rows, set()) == rows


def test_bt_masked_ga_combined_writes_offline_artifacts_and_baseline_comparison(tmp_path):
    dataset = tmp_path / "decision_dataset.jsonl"
    output_dir = tmp_path / "artifacts" / "ml_strategy_eval" / "bt_masked_ga_combined"
    baseline = tmp_path / "stonecore" / "report.json"
    write_jsonl(
        dataset,
        [
            {
                "run_id": 101,
                "decision_id": 10,
                "bot_guid": 1001,
                "candidate_domain": "stonecore",
                "candidate_activity": "boss_assist",
                "candidate_allowed": 1,
                "candidate_mask": {"allowed": True, "reason": ""},
                "is_chosen": 1,
                "label_observed": 1,
                "imitate_teacher": 1,
                "candidate_score": 0.3,
                "utility_score": 0.4,
                "learned_score": 0.2,
                "confidence": 0.8,
                "action_success": 1.0,
                "expected_reward": 2.0,
                "death_risk": 0.0,
                "stuck_risk": 0.0,
                "quest_completion_likelihood": 0.2,
            },
            {
                "run_id": 101,
                "decision_id": 10,
                "bot_guid": 1001,
                "candidate_domain": "stonecore",
                "candidate_activity": "invalid_pull",
                "candidate_allowed": 0,
                "candidate_mask": {"allowed": False, "reason": "server_valid_action_mask"},
                "is_chosen": 0,
                "label_observed": 0,
                "imitate_teacher": 0,
                "candidate_score": 99.0,
                "utility_score": 9.0,
                "learned_score": 9.0,
                "confidence": 1.0,
                "action_success": 1.0,
                "expected_reward": 10.0,
                "death_risk": 0.5,
                "stuck_risk": 0.5,
            },
            {
                "run_id": 102,
                "decision_id": 11,
                "bot_guid": 1001,
                "candidate_domain": "route",
                "candidate_activity": "wait_regroup",
                "candidate_allowed": 1,
                "candidate_mask": {"allowed": True, "reason": ""},
                "is_chosen": 1,
                "label_observed": 1,
                "imitate_teacher": 1,
                "candidate_score": 0.1,
                "utility_score": 0.2,
                "learned_score": 0.1,
                "confidence": 0.6,
                "action_success": 1.0,
                "expected_reward": 1.0,
                "death_risk": 0.0,
                "stuck_risk": 0.1,
                "quest_completion_likelihood": 0.0,
            },
        ],
    )
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(
        json.dumps(
            {
                "acceptable_final_evidence": True,
                "completion_reason": "validation_route_manifest_complete",
                "failure_labels": [],
                "active_bots": 5,
                "diagnosis": {"diagnosis": {"blocker": "all_routes_complete"}},
            }
        ),
        encoding="utf-8",
    )

    report = run_bt_masked_ga_combined(dataset, output_dir, baseline, population_size=6, generations=3, seed=13)

    assert report["artifact_format"] == "bt_masked_ga_combined_v1"
    assert report["metrics"]["uses_server_valid_action_masks"] is True
    assert report["metrics"]["masked_out_candidate_rows"] == 1
    assert report["metrics"]["cpp_runtime_files_changed"] == 0
    assert report["acceptance_gate"]["ready_for_cpp_runtime_integration"] is False
    assert report["stonecore_baseline_comparison"]["stonecore_regression"] is False
    assert json.loads((output_dir / "diagnostics.json").read_text(encoding="utf-8"))["traces"][0]["masked_candidates"] == 1
    assert (output_dir / "dvclive" / "metrics.json").exists()


def test_bot_ml_decision_builder_counts_fallback_candidate_and_disambiguates_duplicates():
    fallback_rows = build_rows(
        {
            "id": 1,
            "run_id": 7,
            "bot_guid": 99,
            "brain_version": "utility_v1",
            "candidate_actions_json": "[]",
            "chosen_action_json": json.dumps({"activity": "wait", "activity_score": 0.1}),
            "raw_state_json": "{}",
            "semantic_state_json": "{}",
            "outcome_json": "{}",
        },
        {},
        {},
    )
    duplicate_rows = build_rows(
        {
            "id": 2,
            "run_id": 7,
            "bot_guid": 99,
            "brain_version": "utility_v1",
            "candidate_actions_json": json.dumps([
                {"candidate_id": "quest_low", "activity": "quest", "score": 0.5},
                {"candidate_id": "quest_high", "activity": "quest", "score": 1.5},
            ]),
            "chosen_action_json": json.dumps({"candidate_id": "quest_high", "activity": "quest", "activity_score": 1.5}),
            "raw_state_json": "{}",
            "semantic_state_json": "{}",
            "outcome_json": "{}",
            "reward": 1.0,
        },
        {},
        {},
    )

    assert len(fallback_rows) == 1
    assert fallback_rows[0]["candidate_count"] == 1
    assert fallback_rows[0]["is_chosen"] == 1
    assert [row["is_chosen"] for row in duplicate_rows] == [0, 1]
    assert [row["label_observed"] for row in duplicate_rows] == [0, 1]


def test_bot_ml_decision_builder_filters_bad_teacher_behavior_from_imitation():
    death_rows = build_rows(
        {
            "id": 1,
            "run_id": 7,
            "bot_guid": 99,
            "brain_version": "utility_v1",
            "candidate_actions_json": json.dumps([{"activity": "pull_boss", "score": 1.0}]),
            "chosen_action_json": json.dumps({"activity": "pull_boss", "activity_score": 1.0}),
            "raw_state_json": "{}",
            "semantic_state_json": "{}",
            "outcome_json": "{}",
        },
        {
            "action_success": 0.0,
            "expected_reward": -8.0,
            "death_risk": 1.0,
            "stuck_risk": 0.0,
            "quest_completion_likelihood": 0.0,
            "event_ids_used_for_label": [10],
            "label_window_json": "{}",
            "label_reason": "negative_outcome:death",
            "time_to_outcome_sec": 3.0,
            "no_future_events": False,
            "ambiguous_label": False,
        },
        {},
    )
    unresolved_rows = build_rows(
        {
            "id": 2,
            "run_id": 7,
            "bot_guid": 99,
            "brain_version": "utility_v1",
            "candidate_actions_json": json.dumps([{"activity": "wait", "score": 0.1}]),
            "chosen_action_json": json.dumps({"activity": "wait", "activity_score": 0.1}),
            "raw_state_json": "{}",
            "semantic_state_json": "{}",
            "outcome_json": "{}",
        },
        {},
        {},
    )

    assert death_rows[0]["label_observed"] == 1
    assert death_rows[0]["death_risk"] == 1.0
    assert death_rows[0]["imitate_teacher"] == 0
    assert death_rows[0]["imitation_weight"] == 0.0
    assert death_rows[0]["teacher_action_quality"] == "unsafe_teacher_action"
    assert death_rows[0]["failure_label"] == "death_outcome"
    assert unresolved_rows[0]["label_observed"] == 1
    assert unresolved_rows[0]["imitate_teacher"] == 0
    assert unresolved_rows[0]["teacher_action_quality"] == "unverified_teacher_action"
    assert unresolved_rows[0]["failure_label"] == "no_future_outcome"


def test_bot_ml_decision_labels_negative_events_before_positive_values():
    indexed_events = index_future_events(
        [
            {
                "id": 10,
                "run_id": 7,
                "bot_guid": 99,
                "ts": "2026-06-05 18:40:10",
                "event_type": "stuck_detected",
                "result": "repath",
                "value_float": 1.0,
            },
            {
                "id": 11,
                "run_id": 7,
                "bot_guid": 99,
                "ts": "2026-06-05 18:40:11",
                "event_type": "repeated_death",
                "result": "danger_zone",
                "value_float": 1.0,
            },
            {
                "id": 12,
                "run_id": 7,
                "bot_guid": 99,
                "ts": "2026-06-05 18:40:12",
                "event_type": "raid_wipe",
                "result": "wipe",
                "value_float": 1.0,
            },
        ]
    )

    labels = label_decision(
        {"run_id": 7, "bot_guid": 99, "ts": "2026-06-05 18:40:00"},
        indexed_events,
        {"outcome": 30, "reward": 30, "death": 30, "stuck": 30, "quest": 30},
    )

    assert labels["action_success"] == 0.0
    assert labels["label_reason"] == "negative_outcome:stuck_detected"
    assert labels["stuck_risk"] == 1.0
    assert labels["death_risk"] == 1.0


def test_bot_ml_decision_labels_first_positive_outcome_before_later_risk():
    indexed_events = index_future_events(
        [
            {
                "id": 20,
                "run_id": 7,
                "bot_guid": 99,
                "ts": "2026-06-05 18:40:05",
                "event_type": "validation_route_move",
                "result": "progress",
                "value_float": 1.0,
            },
            {
                "id": 21,
                "run_id": 7,
                "bot_guid": 99,
                "ts": "2026-06-05 18:40:08",
                "event_type": "stuck_detected",
                "result": "repath",
                "value_float": 1.0,
            },
            {
                "id": 22,
                "run_id": 7,
                "bot_guid": 99,
                "ts": "2026-06-05 18:40:35",
                "event_type": "death",
                "result": "failed",
                "value_float": 1.0,
            },
        ]
    )

    labels = label_decision(
        {"run_id": 7, "bot_guid": 99, "ts": "2026-06-05 18:40:00"},
        indexed_events,
        {"outcome": 60, "reward": 60, "death": 60, "stuck": 60, "quest": 60},
    )
    rows = build_rows(
        {
            "id": 1,
            "run_id": 7,
            "bot_guid": 99,
            "brain_version": "utility_v1",
            "candidate_actions_json": json.dumps([{"activity": "route_move", "score": 1.0}]),
            "chosen_action_json": json.dumps({"activity": "route_move", "activity_score": 1.0}),
            "raw_state_json": "{}",
            "semantic_state_json": "{}",
            "outcome_json": "{}",
        },
        labels,
        {},
    )

    assert labels["action_success"] == 1.0
    assert labels["label_reason"] == "positive_progress:validation_route_move"
    assert labels["stuck_risk"] == 0.0
    assert labels["death_risk"] == 0.0
    assert rows[0]["teacher_action_quality"] == "verified_teacher_action"
    assert rows[0]["failure_label"] == ""


def test_bot_ml_decision_labels_terminal_route_complete_action_without_future_events():
    labels = label_decision(
        {
            "run_id": 7,
            "bot_guid": 99,
            "ts": "2026-06-05 18:40:00",
            "situation_type": "validation_route_manifest",
            "chosen_action_json": json.dumps({"action": "validation_route_complete"}),
        },
        index_future_events([]),
        {"outcome": 30, "reward": 30, "death": 30, "stuck": 30, "quest": 30},
    )
    rows = build_rows(
        {
            "id": 1,
            "run_id": 7,
            "bot_guid": 99,
            "brain_version": "utility_v1",
            "candidate_actions_json": json.dumps([{"activity": "validation_route_complete", "score": 1.0}]),
            "chosen_action_json": json.dumps({"action": "validation_route_complete", "activity_score": 1.0}),
            "raw_state_json": "{}",
            "semantic_state_json": "{}",
            "outcome_json": "{}",
        },
        labels,
        {},
    )

    assert labels["action_success"] == 1.0
    assert labels["label_reason"] == "positive_progress:validation_route_complete"
    assert labels["no_future_events"] is False
    assert rows[0]["teacher_action_quality"] == "verified_teacher_action"


def test_bot_ml_decision_labels_route_terminal_event_from_run_context():
    indexed_events = index_future_events(
        [
            {
                "id": 30,
                "run_id": 7,
                "bot_guid": 100,
                "ts": "2026-06-05 18:40:05",
                "event_type": "validation_route_manifest_complete",
                "result": "boss_killed",
                "value_float": 16.0,
            }
        ]
    )

    labels = label_decision(
        {
            "run_id": 7,
            "bot_guid": 99,
            "ts": "2026-06-05 18:40:00",
            "situation_type": "validation_route_mechanic",
            "chosen_action_json": json.dumps({"action": "movement_check_jump"}),
        },
        indexed_events,
        {"outcome": 30, "reward": 30, "death": 30, "stuck": 30, "quest": 30},
    )

    assert labels["action_success"] == 1.0
    assert labels["label_reason"] == "positive_progress:validation_route_manifest_complete"
    assert labels["event_ids_used_for_label"] == [30]
    assert labels["no_future_events"] is False


def test_bot_ml_decision_builder_filters_repeated_decision_loops_from_imitation():
    fingerprints = index_decision_fingerprints([
        {"bot_guid": 99, "fingerprint_hash": 123456, "repeat_count": 4, "failure_count": 1}
    ])
    rows = build_rows(
        {
            "id": 1,
            "run_id": 7,
            "bot_guid": 99,
            "brain_version": "utility_v1",
            "candidate_actions_json": json.dumps([
                {"activity": "route_retry", "score": 0.2, "domain": "movement", "mask": {"allowed": True, "reason": ""}},
                {"activity": "wait", "score": 0.1, "domain": "movement", "mask": {"allowed": True, "reason": ""}},
            ]),
            "chosen_action_json": json.dumps({"activity": "route_retry", "activity_score": 0.2, "domain": "movement"}),
            "raw_state_json": json.dumps({"decision_fingerprint_hash": 123456}),
            "semantic_state_json": "{}",
            "outcome_json": "{}",
        },
        {
            "action_success": 1.0,
            "expected_reward": 1.0,
            "death_risk": 0.0,
            "stuck_risk": 0.0,
            "quest_completion_likelihood": 0.0,
            "event_ids_used_for_label": [10],
            "label_window_json": "{}",
            "label_reason": "positive_progress:objective_progress",
            "time_to_outcome_sec": 4.0,
            "no_future_events": False,
            "ambiguous_label": False,
        },
        {},
        fingerprints,
    )

    assert rows[0]["label_observed"] == 1
    assert rows[0]["decision_fingerprint_hash"] == 123456
    assert rows[0]["decision_fingerprint_repeat_count"] == 4
    assert rows[0]["decision_fingerprint_failure_count"] == 1
    assert rows[0]["action_success"] == 0.0
    assert rows[0]["stuck_risk"] == 1.0
    assert rows[0]["imitate_teacher"] == 0
    assert rows[0]["teacher_action_quality"] == "looping_teacher_action"
    assert rows[0]["failure_label"] == "repeated_failed_decision_loop"
    assert rows[1]["teacher_action_quality"] == "candidate_unobserved"


def test_bot_ml_data_quality_enforces_traceability_and_teacher_contracts():
    success_rows = build_rows(
        {
            "id": 1,
            "run_id": 7,
            "bot_guid": 99,
            "brain_version": "utility_v1",
            "candidate_actions_json": json.dumps([
                {"activity": "quest", "score": 1.5},
                {"activity": "grind", "score": 0.5},
            ]),
            "chosen_action_json": json.dumps({"activity": "quest", "activity_score": 1.5}),
            "raw_state_json": "{}",
            "semantic_state_json": "{}",
            "outcome_json": "{}",
        },
        {
            "action_success": 1.0,
            "expected_reward": 8.0,
            "death_risk": 0.0,
            "stuck_risk": 0.0,
            "quest_completion_likelihood": 1.0,
            "event_ids_used_for_label": [10],
            "label_window_json": json.dumps({"outcome": 180, "reward": 300}),
            "label_reason": "positive_progress:quest_completed",
            "time_to_outcome_sec": 12.0,
            "no_future_events": False,
            "ambiguous_label": False,
        },
        {},
    )
    failed_rows = build_rows(
        {
            "id": 2,
            "run_id": 8,
            "bot_guid": 99,
            "brain_version": "utility_v1",
            "candidate_actions_json": json.dumps([{"activity": "wait", "score": 0.1}]),
            "chosen_action_json": json.dumps({"activity": "wait", "activity_score": 0.1}),
            "raw_state_json": "{}",
            "semantic_state_json": "{}",
            "outcome_json": "{}",
        },
        {},
        {},
    )
    for row in success_rows:
        row["split"] = "train"
    for row in failed_rows:
        row["split"] = "eval"

    report = validate_data_quality_rows(success_rows + failed_rows)

    assert report["ok"] is True
    assert report["decision_count"] == 2
    assert report["chosen_rows"] == 2
    assert report["imitable_teacher_rows"] == 1
    assert report["filtered_teacher_rows"] == 1
    assert report["failure_labels"] == {"no_future_outcome": 1}
    assert report["dataset_contract_version"] == DATASET_CONTRACT_VERSION
    assert all(value == 0 for value in report["contract_errors"].values())


def test_bot_ml_data_quality_rejects_broken_candidate_and_filter_contracts():
    rows = build_rows(
        {
            "id": 1,
            "run_id": 7,
            "bot_guid": 99,
            "brain_version": "utility_v1",
            "candidate_actions_json": json.dumps([
                {"activity": "quest", "score": 1.5},
                {"activity": "grind", "score": 0.5},
            ]),
            "chosen_action_json": json.dumps({"activity": "quest", "activity_score": 1.5}),
            "raw_state_json": "{}",
            "semantic_state_json": "{}",
            "outcome_json": "{}",
        },
        {
            "action_success": 1.0,
            "expected_reward": 8.0,
            "death_risk": 0.0,
            "stuck_risk": 0.0,
            "quest_completion_likelihood": 1.0,
            "event_ids_used_for_label": [10],
            "label_window_json": "{}",
            "label_reason": "positive_progress:quest_completed",
            "time_to_outcome_sec": 12.0,
            "no_future_events": False,
            "ambiguous_label": False,
        },
        {},
    )
    for row in rows:
        row["split"] = "train"
    rows[0]["trace"] = {}
    rows[0]["candidate_count"] = 3
    rows[0]["teacher_action_quality"] = "unsafe_teacher_action"
    rows[0]["imitate_teacher"] = 0
    rows[0]["imitation_weight"] = 0.0
    rows[0]["failure_label"] = ""
    rows[1]["action_success"] = 1.0

    report = validate_data_quality_rows(rows)

    assert report["ok"] is False
    assert report["traceability_contract"]["missing_trace_fields"] == 1
    assert report["decision_contract"]["candidate_count_mismatch"] == 1
    assert report["decision_contract"]["unchosen_rows_with_nonzero_labels"] == 1
    assert report["teacher_filter_contract"]["filtered_chosen_rows_without_failure_label"] == 1
    assert report["leakage_contract"]["missing_eval_split"] is True


def test_bot_ml_numeric_features_exclude_observed_outcome_leakage():
    features = numeric_features({
        "reward_observed": 10.0,
        "expected_reward": 10.0,
        "action_success": 1.0,
        "death_risk": 0.0,
        "stuck_risk": 0.0,
        "quest_completion_likelihood": 1.0,
        "label_observed": 1,
        "is_chosen": 1,
        "imitate_teacher": 1,
        "imitation_weight": 1.0,
        "utility_score": 1.5,
    })

    assert "reward_observed" not in features
    assert "expected_reward" not in features
    assert "action_success" not in features
    assert "label_observed" not in features
    assert "is_chosen" not in features
    assert "imitate_teacher" not in features
    assert "imitation_weight" not in features
    assert features["utility_score"] == 1.5


def test_bot_ml_run_split_stratifies_activity_and_outcomes():
    rows = []
    for run_id, activity, success, death, stuck in [
        (1, "questing", 0.0, 0.0, 0.0),
        (2, "questing", 0.0, 0.0, 0.0),
        (3, "questing", 1.0, 0.0, 0.0),
        (4, "questing", 1.0, 0.0, 0.0),
        (5, "normal_dungeon", 1.0, 1.0, 0.0),
        (6, "normal_dungeon", 1.0, 1.0, 0.0),
    ]:
        rows.append(
            {
                "run_id": run_id,
                "label_observed": 1,
                "current_activity": activity,
                "action_success": success,
                "death_risk": death,
                "stuck_risk": stuck,
            }
        )

    train_ids, eval_ids = split_by_run_ids(rows, eval_fraction=0.5)
    train_profiles = {(row["current_activity"], row["action_success"], row["death_risk"], row["stuck_risk"]) for row in rows if row["run_id"] in train_ids}
    eval_profiles = {(row["current_activity"], row["action_success"], row["death_risk"], row["stuck_risk"]) for row in rows if row["run_id"] in eval_ids}

    assert train_ids.isdisjoint(eval_ids)
    assert eval_profiles == train_profiles


def test_bot_ml_teacher_choice_training_rows_use_imitable_allowed_candidates():
    rows = [
        {"split": "train", "decision_id": 1, "is_chosen": 1, "imitate_teacher": 1, "candidate_allowed": 1},
        {"split": "train", "decision_id": 1, "is_chosen": 0, "imitate_teacher": 0, "candidate_allowed": 1},
        {"split": "train", "decision_id": 1, "is_chosen": 0, "imitate_teacher": 0, "candidate_allowed": 0},
        {"split": "train", "decision_id": 2, "is_chosen": 1, "imitate_teacher": 0, "candidate_allowed": 1},
        {"split": "eval", "decision_id": 3, "is_chosen": 1, "imitate_teacher": 1, "candidate_allowed": 1},
    ]

    choice_rows = teacher_choice_training_rows(rows)

    assert [row["decision_id"] for row in choice_rows] == [1, 1]
    assert [row["is_chosen"] for row in choice_rows] == [1, 0]


def test_bot_ml_binary_weights_balance_sparse_positive_labels():
    weights = balanced_binary_weights([1.0, 0.0, 0.0, 0.0])

    assert weights == [3.0, 1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]
    assert balanced_binary_weights([0.0, 0.0]) == [1.0, 1.0]


def test_bot_ml_binary_training_adds_low_weight_missing_class():
    x_train, y_train, weights = add_synthetic_binary_class([[0.4], [0.8]], [1.0, 1.0], ["score"])

    assert x_train == [[0.4], [0.8], [0.0]]
    assert y_train == [1.0, 1.0, 0.0]
    assert weights == [1.0, 1.0, 1e-6]


def test_bot_policy_ranking_uses_teacher_choice_and_hard_candidate_mask():
    chosen = {"decision_id": 7, "candidate_allowed": 1, "is_chosen": 1, "trace": {"candidate_id": "chosen"}}
    masked = {"decision_id": 7, "candidate_allowed": 0, "is_chosen": 0, "trace": {"candidate_id": "masked"}}
    preds = {
        id(chosen): {"action_success": 0.8, "expected_reward": 0.0, "death_risk": 0.0, "stuck_risk": 0.0, "quest_completion_likelihood": 0.0, "teacher_choice": 0.9},
        id(masked): {"action_success": 1.0, "expected_reward": 50.0, "death_risk": 0.0, "stuck_risk": 0.0, "quest_completion_likelihood": 0.0, "teacher_choice": 0.0},
    }

    metrics = ranking_metrics([chosen, masked], preds)

    assert policy_score(preds[id(chosen)]) > policy_score({**preds[id(chosen)], "teacher_choice": 0.0})
    assert metrics["ranked_decisions"] == 1
    assert metrics["masked_candidate_rows"] == 1
    assert metrics["top_1_candidate_ranking_accuracy"] == 1.0
    assert metrics["top_choice_predicted_teacher_choice"] == 0.9


def test_bot_ml_workflow_has_pixi_tasks_and_documented_dvc_steps():
    pixi = Path("pixi.toml").read_text(encoding="utf-8")
    dvc = Path("dvc.yaml").read_text(encoding="utf-8")
    readme = Path("tools/bot_ml/README.md").read_text(encoding="utf-8")
    register_script = Path("tools/bot_ml/register_policy_model.py").read_text(encoding="utf-8")
    evaluate_script = Path("tools/bot_ml/evaluate_policy_model.py").read_text(encoding="utf-8")

    for task in [
        "bot-world-knowledge",
        "bot-world-planner",
        "bot-world-validate",
        "bot-validation-gear",
        "bot-validation-provisioning",
        "bot-validation-provisioning-verify",
        "bot-validation-scenarios",
        "bot-validation-run-plan",
        "bot-validation-run-status",
        "bot-live-scenario-reports",
        "bot-live-validate",
        "bot-ml-export",
        "bot-ml-build-decisions",
        "bot-ml-validate",
        "bot-ml-train",
        "bot-ml-evaluate",
        "bot-ml-explain",
        "bot-ml-compare",
        "bot-ml-register",
    ]:
        assert f"{task} =" in pixi
        assert f"pixi run {task}" in readme

    for required in [
        "BotWorld.AutoStart = 1",
        "BotWorld.AutoStartRecording = 1",
        "WorldDatabaseInfo",
        "world_planner_validate",
        "validation_provisioning",
        "validation_provisioning_verify",
        "validation_scenarios",
        "live_scenario_reports",
        "validation_run_plan",
        "validation_run_status",
        "live_validation_combined",
        "validation_gear",
        "complete_equipment_slots",
        "full Stonecore and Blackwing Descent gates failing",
        "run-id train/eval split",
        "candidate-level",
        "teacher_policy_candidate_v1",
        "repeated_decision_loop",
        "control_eligible=false",
        "pixi run dvc status",
        "pixi run dvc push",
        "DVC-managed",
        "Shadow deployment",
        "Assist deployment",
    ]:
        assert required in readme

    assert "--sql-output\", \"--output-sql\"" in register_script
    assert '"accepted": bool(payload["accepted"])' in register_script
    assert 'live.log_metric("accepted", int(accepted))' in evaluate_script
    for stage in [
        "world_knowledge:",
        "world_planner:",
        "world_planner_validate:",
        "dataset/world_knowledge",
        "dataset/world_planner",
        "dataset/world_validation/planner_report.json",
        "validation_gear:",
        "dataset/validation_gear_profiles",
        "validation_provisioning:",
        "dataset/validation_provisioning",
        "validation_provisioning_verify:",
        "dataset/validation_provisioning_verification/report.json",
        "validation_scenarios:",
        "dataset/validation_scenarios",
        "live_scenario_reports:",
        "dataset/live_validation_scenario_reports_built",
        "validation_run_plan:",
        "dataset/validation_run_plan",
        "validation_run_status:",
        "dataset/validation_run_status",
        "live_validation_combined:",
        "bot_ml_build_decisions:",
        "--include-map-id ${bot_ml.teacher_map_id}",
        "bot_ml_validate:",
        "bot_ml_train:",
        "bot_ml_evaluate:",
        "bot_ml_register:",
        "dataset/bot_ml/decision_dataset.jsonl",
        "dataset/bot_ml/data_quality.json",
        "evaluations/bot_policy/metrics.json",
        "dataset/live_validation_combined",
    ]:
        assert stage in dvc

    for segment_report in [
        "dataset/live_validation_scenarios/stonecore_5n/report.json",
        "dataset/live_validation_scenarios/stonecore_5n/02_corborus/report.json",
        "dataset/live_validation_scenarios/stonecore_5n/04_slabhide/report.json",
        "dataset/live_validation_scenarios/stonecore_5n/05_stonecore_sentry_gauntlet/report.json",
        "dataset/live_validation_scenarios/stonecore_5n/06_ozruk/report.json",
        "dataset/live_validation_scenarios/stonecore_5n/07_twilight_flayer_packs/report.json",
        "dataset/live_validation_scenarios/stonecore_5n/08_high_priestess_azil/report.json",
    ]:
        assert segment_report in dvc
    assert dvc.count("--live-report") >= 9
    assert "dataset/live_validation_scenario_reports/report.json" not in dvc


def test_world_knowledge_can_read_database_url_from_worldserver_conf(tmp_path):
    conf = tmp_path / "worldserver.conf"
    conf.write_text(
        '\nWorldDatabaseInfo = "172.20.0.2;3306;trinity;secret;world"\n',
        encoding="utf-8",
    )

    info = parse_trinity_database_info('"127.0.0.1;3306;user;pass;world"')
    url = database_url_from_worldserver_conf(conf)
    sanitized = sanitize_database_url(url)

    assert info == {"host": "127.0.0.1", "port": 3306, "user": "user", "password": "pass", "database": "world"}
    assert url == "mysql://trinity:secret@172.20.0.2:3306/world"
    assert sanitized == {"scheme": "mysql", "host": "172.20.0.2", "port": 3306, "database": "world", "user": "trinity"}


def test_world_knowledge_cli_writes_sanitized_source_database(tmp_path, monkeypatch):
    fake_db = FakeWorldDb()
    conf = tmp_path / "worldserver.conf"
    output_dir = tmp_path / "world_knowledge"
    conf.write_text('WorldDatabaseInfo = "db.example;3306;trinity;secret;world"\n', encoding="utf-8")
    monkeypatch.setattr("tools.bot_ml.extract_world_knowledge.connect_mysql", lambda _url: fake_db)
    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-world-knowledge",
            "--worldserver-conf",
            str(conf),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert world_knowledge_main() == 0
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["source_database"] == {
        "scheme": "mysql",
        "host": "db.example",
        "port": 3306,
        "database": "world",
        "user": "trinity",
    }
    assert "secret" not in json.dumps(manifest)


def test_world_knowledge_objective_and_reward_parsing_contract():
    quest = {
        "RequiredNpcOrGo1": 123,
        "RequiredNpcOrGoCount1": 4,
        "ObjectiveText1": "Kill wolves",
        "RequiredNpcOrGo2": -456,
        "RequiredNpcOrGoCount2": 1,
        "ObjectiveText2": "Open crate",
        "RequiredNpcOrGo3": 0,
        "RequiredNpcOrGoCount3": 0,
        "ObjectiveText3": "",
        "RequiredNpcOrGo4": 0,
        "RequiredNpcOrGoCount4": 0,
        "ObjectiveText4": "",
        "RequiredItemId1": 700,
        "RequiredItemCount1": 2,
        "RequiredSpell": 900,
        "RewardItem1": 800,
        "RewardAmount1": 1,
        "RewardChoiceItemID1": 801,
        "RewardChoiceItemQuantity1": 1,
    }

    for slot in range(2, 7):
        quest.setdefault(f"RequiredItemId{slot}", 0)
        quest.setdefault(f"RequiredItemCount{slot}", 0)
        quest.setdefault(f"RewardChoiceItemID{slot}", 0)
        quest.setdefault(f"RewardChoiceItemQuantity{slot}", 0)
    for slot in range(2, 5):
        quest.setdefault(f"RewardItem{slot}", 0)
        quest.setdefault(f"RewardAmount{slot}", 0)

    objectives = build_quest_objectives(quest)
    rewards = build_rewards(quest)

    assert objectives == [
        {"slot": 1, "type": "creature", "entry": 123, "required_count": 4, "text": "Kill wolves"},
        {"slot": 2, "type": "gameobject", "entry": 456, "required_count": 1, "text": "Open crate"},
        {"slot": 1, "type": "item", "item_id": 700, "required_count": 2},
        {"slot": 0, "type": "spell", "spell_id": 900},
    ]
    assert rewards == [
        {"slot": 1, "mode": "fixed", "item_id": 800, "quantity": 1},
        {"slot": 1, "mode": "choice", "item_id": 801, "quantity": 1},
    ]


def test_world_knowledge_extractor_emits_planner_manifests(monkeypatch):
    fake_db = FakeWorldDb()
    monkeypatch.setattr("tools.bot_ml.extract_world_knowledge.connect_mysql", lambda _url: fake_db)

    manifests = extract_world_knowledge("mysql://example/world")

    assert fake_db.closed is True
    assert set(manifests) == {
        "quests",
        "quest_objectives",
        "npcs",
        "mobs",
        "npc_services",
        "trainers",
        "vendors",
        "item_sources",
        "recipe_sources",
        "material_sources",
        "gathering_nodes",
        "travel",
        "graveyards",
        "instance_entrances",
        "repair_points",
        "faction_restrictions",
        "map_zone_relationships",
        "zones",
    }
    quest = manifests["quests"][0]
    assert quest["quest_id"] == 9001
    assert quest["prev_quest_id"] == 9000
    assert quest["next_quest_id"] == 9002
    assert quest["required_factions"] == [{"faction_id": 72, "value": 3000}, {"faction_id": 0, "value": 0}]
    assert quest["givers"][0]["entry"] == 100
    assert quest["givers"][0]["spawns"][0]["area_id"] == 40
    assert quest["turnins"][0]["entry"] == 100
    assert quest["support_class"] == "supported_simple"

    objectives = manifests["quest_objectives"]
    assert {objective["type"] for objective in objectives} == {"creature", "gameobject", "item", "spell"}
    assert next(objective for objective in objectives if objective["type"] == "creature")["spawns"][0]["x"] == 4.0
    assert next(objective for objective in objectives if objective["type"] == "gameobject")["spawns"][0]["x"] == 10.0

    service = manifests["npc_services"][0]
    assert service["entry"] == 300
    assert service["service_types"] == ["trainer", "vendor"]
    assert service["vendor_items"][0]["item"] == 700
    assert service["trainer_spells"][0]["spell_id"] == 600
    assert manifests["npcs"][0]["service_types"] == ["questgiver"]
    assert manifests["mobs"][0]["entry"] == 200
    assert manifests["trainers"][0]["entry"] == 300
    assert manifests["vendors"][0]["entry"] == 300
    assert manifests["repair_points"][0]["entry"] == 301

    item_sources = manifests["item_sources"]
    assert {"creature_loot", "gameobject_loot", "vendor"} <= {source["source_type"] for source in item_sources}
    assert any(source["item_id"] == 700 and source["source_type"] == "creature_loot" for source in item_sources)
    assert any(source["item_id"] == 700 and source["source_type"] == "vendor" for source in item_sources)

    recipe_sources = manifests["recipe_sources"]
    assert {"trainer", "vendor_item"} <= {source["source_type"] for source in recipe_sources}
    assert any(source["recipe_spell_id"] == 600 and source["profession_skill_id"] == 185 for source in recipe_sources)
    assert any(source["item_id"] == 700 and source["source_entry"] == 300 for source in recipe_sources)

    material_sources = manifests["material_sources"]
    assert {"creature_loot", "gameobject_loot", "vendor"} <= {source["source_type"] for source in material_sources}
    assert next(source for source in material_sources if source["source_type"] == "creature_loot")["spawns"][0]["x"] == 4.0
    assert manifests["gathering_nodes"][0]["entry"] == 400

    assert {"areatrigger_teleport", "transport", "graveyard", "taxi_level"} <= {entry["type"] for entry in manifests["travel"]}
    assert manifests["graveyards"][0]["GhostZone"] == 12
    assert manifests["instance_entrances"][0]["id"] == 1
    assert any(row["source_type"] == "quest" and row["faction_id"] == 72 for row in manifests["faction_restrictions"])
    assert manifests["map_zone_relationships"] == [{"map_id": 0, "zone_id": 12, "creature_spawns": 4, "gameobject_spawns": 1, "areas": [40, 41, 42]}]
    assert manifests["zones"] == [{"map_id": 0, "zone_id": 12, "creature_spawns": 4, "gameobject_spawns": 1, "areas": [40, 41, 42]}]


def test_world_planner_builder_derives_hubs_clusters_services_and_travel(tmp_path, monkeypatch):
    fake_db = FakeWorldDb()
    monkeypatch.setattr("tools.bot_ml.extract_world_knowledge.connect_mysql", lambda _url: fake_db)
    world = extract_world_knowledge("mysql://example/world")
    world_dir = tmp_path / "world"
    for name, rows in world.items():
        write_jsonl(world_dir / f"{name}.jsonl", rows)

    planner = build_planner_manifests(world_dir)

    assert set(planner) == {
        "quest_hubs",
        "quest_chains",
        "quest_batches",
        "unsupported_quest_fallbacks",
        "quest_route_edges",
        "objective_clusters",
        "npc_index",
        "mob_index",
        "service_index",
        "service_visit_plans",
        "trainer_index",
        "vendor_index",
        "item_source_index",
        "recipe_source_index",
        "recipe_acquisition_plans",
        "material_source_index",
        "material_plans",
        "crafting_surfaces",
        "gathering_node_index",
        "travel_edges",
        "graveyard_index",
        "instance_entrance_index",
        "repair_point_index",
        "faction_restriction_index",
        "map_zone_index",
    }
    assert planner["quest_hubs"] == [
        {
            "hub_id": planner["quest_hubs"][0]["hub_id"],
            "giver_type": "creature",
            "giver_entry": 100,
            "map_id": 0,
            "zone_id": 12,
            "area_id": 40,
            "x": 1.0,
            "y": 2.0,
            "z": 3.0,
            "quests": [9001],
        }
    ]
    assert planner["quest_chains"] == [
        {
            "quest_id": 9001,
            "prev_quest_id": 9000,
            "next_quest_id": 9002,
            "breadcrumb_for_quest_id": 0,
            "prev_known": False,
            "next_known": False,
            "breadcrumb_known": False,
        }
    ]
    assert planner["quest_batches"][0]["quest_ids"] == [9001]
    assert planner["quest_batches"][0]["objective_cluster_count"] == 1
    assert planner["quest_batches"][0]["route_policy"] == "batch_pickup_then_cluster_sweep_then_turnin"
    assert planner["unsupported_quest_fallbacks"] == []
    assert planner["quest_route_edges"][0]["quest_id"] == 9001
    assert planner["quest_route_edges"][0]["from_kind"] == "quest_hub"
    assert planner["quest_route_edges"][0]["to_kind"] == "objective_cluster"
    assert len(planner["objective_clusters"]) == 1
    cluster = planner["objective_clusters"][0]
    assert cluster["quests"] == [9001]
    assert cluster["objective_count"] == 4
    assert {objective["type"] for objective in cluster["objectives"]} == {"creature", "gameobject", "item", "spell"}

    service = planner["service_index"][0]
    assert service["entry"] == 300
    assert service["service_types"] == ["trainer", "vendor"]
    assert service["vendor_items"] == [700]
    assert service["trainer_spells"] == [600]
    assert planner["npc_index"][0]["entry"] == 100
    assert planner["mob_index"][0]["entry"] == 200
    assert planner["trainer_index"][0]["entry"] == 300
    assert planner["vendor_index"][0]["entry"] == 300
    assert planner["repair_point_index"][0]["entry"] == 301
    visit = planner["service_visit_plans"][0]
    assert visit["visit_kinds"] == ["profession_trainer", "trainer", "vendor"]
    assert visit["profession_skill_ids"] == [185]

    item_source = next(row for row in planner["item_source_index"] if row["item_id"] == 700)
    assert item_source["source_count"] == 2
    assert item_source["source_types"] == ["creature_loot", "vendor"]

    recipe_source = next(row for row in planner["recipe_source_index"] if row["recipe_spell_id"] == 600)
    assert recipe_source["source_count"] == 1
    assert recipe_source["profession_skill_ids"] == [185]
    assert recipe_source["source_types"] == ["trainer"]
    recipe_plan = next(row for row in planner["recipe_acquisition_plans"] if row["recipe_spell_id"] == 600)
    assert recipe_plan["acquisition_policy"] == "train_or_buy_recipe_before_crafting"
    assert recipe_plan["acquisition_steps"][0]["source_entry"] == 300

    material_source = next(row for row in planner["material_source_index"] if row["item_id"] == 700)
    assert material_source["source_count"] == 2
    assert material_source["source_types"] == ["creature_loot", "vendor"]
    assert material_source["nearest_source"]["source_entry"] == 200
    material_plan = next(row for row in planner["material_plans"] if row["material_item_id"] == 700)
    assert material_plan["planning_strategy"] == "buy_then_farm_shortfall"
    crafting_surface = next(row for row in planner["crafting_surfaces"] if row["profession_skill_id"] == 185)
    assert crafting_surface["recipe_count"] == 1
    assert planner["gathering_node_index"][0]["entry"] == 400
    assert planner["graveyard_index"][0]["ghost_zone"] == 12
    assert planner["instance_entrance_index"][0]["entrance_id"] == 1
    assert any(row["source_type"] == "quest" and row["faction_id"] == 72 for row in planner["faction_restriction_index"])
    assert planner["map_zone_index"][0]["areas"] == [40, 41, 42]

    assert {"portal_or_instance_entrance", "transport", "graveyard", "taxi_level"} <= {edge["edge_type"] for edge in planner["travel_edges"]}


def test_world_planner_validation_report_marks_covered_and_missing_gates(tmp_path, monkeypatch):
    fake_db = FakeWorldDb()
    monkeypatch.setattr("tools.bot_ml.extract_world_knowledge.connect_mysql", lambda _url: fake_db)
    world = extract_world_knowledge("mysql://example/world")
    world_dir = tmp_path / "world"
    for name, rows in world.items():
        write_jsonl(world_dir / f"{name}.jsonl", rows)

    validation_manifests = {
        "validation_scenarios": [
            {"scenario_id": "stonecore_5n", "provisioning_ready": True},
            {"scenario_id": "blackwing_descent_10n", "provisioning_ready": True},
        ],
        "validation_routes": [
            {"scenario_id": "stonecore_5n", "kind": "trash"},
            {"scenario_id": "stonecore_5n", "kind": "boss", "coordinates_valid": False},
            {"scenario_id": "blackwing_descent_10n", "kind": "trash"},
            {"scenario_id": "blackwing_descent_10n", "kind": "boss", "coordinates_valid": False},
        ],
        "validation_mechanics": [
            {"scenario_id": "stonecore_5n", "families": ["ground_danger"], "valid": True},
            {"scenario_id": "blackwing_descent_10n", "families": ["raid_aoe"], "valid": True},
        ],
    }
    planner_manifests = build_planner_manifests(world_dir)
    planner_manifests["quest_route_edges"] = [
        {**row, "to_zone_id": 13, "cross_zone": True}
        for row in planner_manifests["quest_route_edges"]
    ]
    planner_manifests["service_visit_plans"] = [
        {**row, "visit_kinds": sorted(set(row.get("visit_kinds") or []) | {"class_skill_trainer"}), "class_skill_spell_ids": [133]}
        for row in planner_manifests["service_visit_plans"]
    ]
    report = validate_manifest_coverage(planner_manifests, validation_manifests)
    gates = {gate["gate"]: gate for gate in report["gates"]}

    assert [gate["gate"] for gate in report["gates"]] == STAGED_GATES
    for gate in [
        "movement_smoke",
        "kill_quest",
        "collect_quest",
        "quest_hub_batching",
        "quest_chain_routing",
        "unsupported_quest_fallback",
        "cross_zone_routing",
        "trainer_visit",
        "vendor_repair",
        "class_skill_visit",
        "profession_recipe_acquisition",
        "all_profession_recipe_acquisition",
        "material_farming",
        "material_planning",
        "crafting_surface",
        "smart_loot",
        "normal_dungeon_trash",
        "dungeon_boss",
        "raid_trash",
    ]:
        assert gates[gate]["passed"], gate

    assert gates["full_stonecore_clear"]["passed"] is False
    assert gates["raid_boss"]["passed"] is False
    assert gates["full_blackwing_descent_clear"]["passed"] is False
    assert gates["full_stonecore_clear"]["missing"] == ["stonecore_route_manifest_coordinates", "stonecore_live_clear_report"]
    assert gates["raid_boss"]["missing"] == ["blackwing_descent_route_manifest_coordinates", "blackwing_descent_live_boss_report"]
    assert gates["full_blackwing_descent_clear"]["missing"] == ["blackwing_descent_route_manifest_coordinates", "blackwing_descent_live_clear_report"]
    assert report["all_passed"] is False
    assert report["runtime_ml_control"] == "disabled_until_shadow_assist_replay_validation_passes"

    vendor_only_manifests = {name: [dict(row) for row in rows] for name, rows in planner_manifests.items()}
    vendor_only_manifests["repair_point_index"] = []
    vendor_only_manifests["service_index"] = [
        {**row, "service_types": [service for service in row.get("service_types", []) if service != "repair"]}
        for row in vendor_only_manifests["service_index"]
    ]
    vendor_only_report = validate_manifest_coverage(vendor_only_manifests, validation_manifests)
    vendor_only_gates = {gate["gate"]: gate for gate in vendor_only_report["gates"]}
    assert vendor_only_gates["vendor_repair"]["passed"] is False
    assert vendor_only_gates["vendor_repair"]["missing"] == ["repair_service"]

    same_zone_manifests = {name: [dict(row) for row in rows] for name, rows in planner_manifests.items()}
    same_zone_manifests["quest_route_edges"] = [
        {**row, "to_map_id": row.get("from_map_id"), "to_zone_id": row.get("from_zone_id"), "cross_map": False, "cross_zone": False}
        for row in same_zone_manifests["quest_route_edges"]
    ]
    same_zone_report = validate_manifest_coverage(same_zone_manifests, validation_manifests)
    same_zone_gates = {gate["gate"]: gate for gate in same_zone_report["gates"]}
    assert same_zone_gates["cross_zone_routing"]["passed"] is False
    assert same_zone_gates["cross_zone_routing"]["missing"] == ["cross_zone_quest_route_edge"]

    profession_only_manifests = {name: [dict(row) for row in rows] for name, rows in planner_manifests.items()}
    profession_only_manifests["service_visit_plans"] = [
        {
            **row,
            "visit_kinds": [kind for kind in row.get("visit_kinds", []) if kind != "class_skill_trainer"],
            "class_skill_spell_ids": [],
        }
        for row in profession_only_manifests["service_visit_plans"]
    ]
    profession_only_report = validate_manifest_coverage(profession_only_manifests, validation_manifests)
    profession_only_gates = {gate["gate"]: gate for gate in profession_only_report["gates"]}
    assert profession_only_gates["class_skill_visit"]["passed"] is False
    assert profession_only_gates["class_skill_visit"]["missing"] == ["class_skill_trainer_visit"]

    live_ready_manifests = {
        **validation_manifests,
        "validation_routes": [
            {"scenario_id": "stonecore_5n", "kind": "trash", "coordinates_valid": True},
            {"scenario_id": "stonecore_5n", "kind": "boss", "coordinates_valid": True},
            {"scenario_id": "blackwing_descent_10n", "kind": "trash", "coordinates_valid": True},
            {"scenario_id": "blackwing_descent_10n", "kind": "boss", "coordinates_valid": True},
        ],
    }
    live_report = validate_manifest_coverage(
        planner_manifests,
        live_ready_manifests,
        {
            "stonecore_5n": {
                "scenario_id": "stonecore_5n",
                "prepared_group": True,
                "boss_kills": 4,
                "clear_complete": True,
                "completion_claim_valid": True,
                "completion_evidence_mode": "uninterrupted_live_clear",
                "teacher_label_quality": "medium",
            },
            "blackwing_descent_10n": {"scenario_id": "blackwing_descent_10n", "prepared_group": True, "raid_boss_kills": 1, "clear_complete": False, "teacher_label_quality": "medium"},
        },
    )
    live_gates = {gate["gate"]: gate for gate in live_report["gates"]}

    assert live_gates["full_stonecore_clear"]["passed"] is True
    assert live_gates["raid_boss"]["passed"] is True
    assert live_gates["full_blackwing_descent_clear"]["passed"] is False
    assert live_gates["full_blackwing_descent_clear"]["missing"] == ["blackwing_descent_live_clear_report"]
    assert live_report["evidence"]["live_scenario_ids"] == ["blackwing_descent_10n", "stonecore_5n"]
    assert live_report["evidence"]["live_scenario_label_quality"]["stonecore_5n"] == "medium"


def test_world_knowledge_existing_manifest_fallback_requires_complete_schema(tmp_path):
    write_jsonl(tmp_path / "quests.jsonl", [{"quest_id": 1}])

    assert load_existing_world_manifests(tmp_path) is None


def test_world_knowledge_cli_rejects_empty_offline_fallback(tmp_path, monkeypatch):
    conf = tmp_path / "worldserver.conf"
    output_dir = tmp_path / "world_knowledge"
    conf.write_text('WorldDatabaseInfo = "db.example;3306;trinity;secret;world"\n', encoding="utf-8")
    for name in WORLD_MANIFEST_NAMES:
        write_jsonl(output_dir / f"{name}.jsonl", [])
    monkeypatch.setattr("tools.bot_ml.extract_world_knowledge.connect_mysql", lambda _url: (_ for _ in ()).throw(RuntimeError("db offline")))
    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-world-knowledge",
            "--worldserver-conf",
            str(conf),
            "--output-dir",
            str(output_dir),
            "--allow-offline-reuse",
        ],
    )

    with pytest.raises(SystemExit, match="offline world knowledge fallback produced empty required DB-backed manifests"):
        world_knowledge_main()


def test_world_knowledge_cli_rejects_db_failure_without_explicit_offline_fallback(tmp_path, monkeypatch):
    conf = tmp_path / "worldserver.conf"
    output_dir = tmp_path / "world_knowledge"
    conf.write_text('WorldDatabaseInfo = "db.example;3306;trinity;secret;world"\n', encoding="utf-8")
    monkeypatch.setattr("tools.bot_ml.extract_world_knowledge.connect_mysql", lambda _url: (_ for _ in ()).throw(RuntimeError("db offline")))
    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-world-knowledge",
            "--worldserver-conf",
            str(conf),
            "--output-dir",
            str(output_dir),
        ],
    )

    with pytest.raises(SystemExit, match="world knowledge extraction failed and offline fallback is disabled"):
        world_knowledge_main()
    assert not (output_dir / "manifest.json").exists()


def test_world_knowledge_cli_allows_explicit_nonempty_offline_fallback(tmp_path, monkeypatch):
    conf = tmp_path / "worldserver.conf"
    output_dir = tmp_path / "world_knowledge"
    conf.write_text('WorldDatabaseInfo = "db.example;3306;trinity;secret;world"\n', encoding="utf-8")
    for name in WORLD_MANIFEST_NAMES:
        rows = [{"source": name}] if name in REQUIRED_NONEMPTY_WORLD_MANIFESTS else []
        write_jsonl(output_dir / f"{name}.jsonl", rows)
    monkeypatch.setattr("tools.bot_ml.extract_world_knowledge.connect_mysql", lambda _url: (_ for _ in ()).throw(RuntimeError("db offline")))
    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-world-knowledge",
            "--worldserver-conf",
            str(conf),
            "--output-dir",
            str(output_dir),
            "--allow-offline-reuse",
        ],
    )

    assert world_knowledge_main() == 0
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["extraction_status"]["mode"] == "existing_generated_files"
    assert manifest["extraction_status"]["ok"] is True
    assert manifest["files"]["quests"]["rows"] == 1


def test_world_planner_cli_rejects_empty_db_backed_inputs(tmp_path, monkeypatch):
    world_dir = tmp_path / "world_knowledge"
    planner_dir = tmp_path / "world_planner"
    for name in WORLD_MANIFEST_NAMES:
        write_jsonl(world_dir / f"{name}.jsonl", [])
    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-world-planner",
            "--world-dir",
            str(world_dir),
            "--output-dir",
            str(planner_dir),
        ],
    )

    with pytest.raises(SystemExit, match="world input .* has empty required DB-backed manifests"):
        world_planner_main()


def test_world_planner_validation_cli_rejects_empty_planner_inputs(tmp_path, monkeypatch):
    planner_dir = tmp_path / "world_planner"
    validation_dir = tmp_path / "validation_scenarios"
    report = tmp_path / "planner_report.json"
    planner = {
        name: []
        for name in [
            "quest_hubs",
            "quest_chains",
            "quest_batches",
            "unsupported_quest_fallbacks",
            "quest_route_edges",
            "objective_clusters",
            "npc_index",
            "mob_index",
            "service_index",
            "service_visit_plans",
            "trainer_index",
            "vendor_index",
            "item_source_index",
            "recipe_source_index",
            "recipe_acquisition_plans",
            "material_source_index",
            "material_plans",
            "crafting_surfaces",
            "gathering_node_index",
            "travel_edges",
            "graveyard_index",
            "instance_entrance_index",
            "repair_point_index",
            "faction_restriction_index",
            "map_zone_index",
        ]
    }
    for name, rows in planner.items():
        write_jsonl(planner_dir / f"{name}.jsonl", rows)
    for name in ["validation_scenarios", "validation_routes", "validation_mechanics"]:
        write_jsonl(validation_dir / f"{name}.jsonl", [])
    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-world-planner-validate",
            "--planner-dir",
            str(planner_dir),
            "--validation-scenario-dir",
            str(validation_dir),
            "--report",
            str(report),
        ],
    )

    assert world_planner_validate_main() == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["all_passed"] is False
    assert payload["input_contract"]["ok"] is False
    assert "quest_hubs" in payload["input_contract"]["empty_required_db_backed_planner_manifests"]
    assert payload["dataset_inputs"]["planner"]["files"]["quest_hubs"]["rows"] == 0


def test_quest_profession_report_builds_without_live_server(tmp_path, monkeypatch):
    fake_db = FakeWorldDb()
    monkeypatch.setattr("tools.bot_ml.extract_world_knowledge.connect_mysql", lambda _url: fake_db)
    world = extract_world_knowledge("mysql://example/world")
    world_dir = tmp_path / "world"
    planner_dir = tmp_path / "planner"
    for name, rows in world.items():
        write_jsonl(world_dir / f"{name}.jsonl", rows)

    planner = build_planner_manifests(world_dir)
    planner["quest_route_edges"] = [
        {**row, "to_zone_id": 13, "cross_zone": True}
        for row in planner["quest_route_edges"]
    ]
    planner["service_visit_plans"] = [
        {**row, "visit_kinds": sorted(set(row.get("visit_kinds") or []) | {"class_skill_trainer"}), "class_skill_spell_ids": [133]}
        for row in planner["service_visit_plans"]
    ]
    for name, rows in planner.items():
        write_jsonl(planner_dir / f"{name}.jsonl", rows)

    report = build_quest_profession_report(planner_dir)
    stages = {stage["gate"]: stage for stage in report["stages"]}

    assert report["schema"] == "bot_quest_profession_report_v1"
    assert report["all_passed"] is True
    assert stages["quest_hub_batching"]["passed"] is True
    assert stages["cross_zone_routing"]["passed"] is True
    assert stages["class_skill_visit"]["passed"] is True
    assert stages["all_profession_recipe_acquisition"]["passed"] is True
    assert stages["material_planning"]["passed"] is True
    assert stages["crafting_surface"]["passed"] is True


def test_validation_scenario_manifests_link_routes_mechanics_and_provisioning():
    config = json.loads(Path("experiments/configs/validation_scenarios_cata_001.json").read_text(encoding="utf-8"))
    provisioning_report = {
        "all_ready": True,
        "scenarios": [
            {"scenario_id": "stonecore_5n", "ready": True, "missing": [], "role_counts": {"tank": 1, "healer": 1, "dps": 3}},
            {"scenario_id": "blackwing_descent_10n", "ready": True, "missing": [], "role_counts": {"tank": 2, "healer": 3, "dps": 5}},
        ],
    }
    verification_report = {"all_passed": True}

    manifests = build_validation_scenario_manifests(config, provisioning_report, verification_report)
    scenarios = {row["scenario_id"]: row for row in manifests["validation_scenarios"]}
    routes = manifests["validation_routes"]
    mechanics = manifests["validation_mechanics"]

    assert scenarios["stonecore_5n"]["provisioning_ready"] is True
    assert scenarios["blackwing_descent_10n"]["provisioning_ready"] is True
    assert scenarios["stonecore_5n"]["route_coordinates_ready"] is True
    assert scenarios["blackwing_descent_10n"]["route_coordinates_ready"] is True
    assert scenarios["stonecore_5n"]["expected_bot_count"] == 5
    assert scenarios["blackwing_descent_10n"]["expected_bot_count"] == 10
    assert scenarios["stonecore_5n"]["group_kind"] == "party"
    assert scenarios["blackwing_descent_10n"]["group_kind"] == "raid"
    assert "role_assignments" in scenarios["stonecore_5n"]["required_evidence"]
    assert "party_formation" in scenarios["stonecore_5n"]["required_evidence"]
    assert "instance_reset" not in scenarios["stonecore_5n"]["required_evidence"]
    assert "raid_formation" in scenarios["blackwing_descent_10n"]["required_evidence"]
    assert "instance_reset" in scenarios["blackwing_descent_10n"]["required_evidence"]
    assert scenarios["blackwing_descent_10n"]["role_assignment"]["assignments"][0] == {
        "role": "tank",
        "required": 2,
        "provisioned": 2,
        "evidence_actions": ["role_assignment", "validation_role_assignment", "tank_assigned", "healer_assigned", "raid_role_assignment"],
    }
    assert scenarios["stonecore_5n"]["boss_count"] == 4
    assert scenarios["blackwing_descent_10n"]["boss_count"] == 6
    assert any(row["scenario_id"] == "stonecore_5n" and row["kind"] == "trash" for row in routes)
    assert any(row["scenario_id"] == "blackwing_descent_10n" and row["kind"] == "boss" and row["coordinates_valid"] is True and row["source_entry"] == 41570 for row in routes)
    bwd_boss_entries = {row["source_entry"] for row in routes if row["scenario_id"] == "blackwing_descent_10n" and row["kind"] == "boss"}
    assert {41570, 42166, 41378, 41442, 43296, 41376}.issubset(bwd_boss_entries)
    assert 49801 not in bwd_boss_entries
    assert 48964 not in bwd_boss_entries
    atramedes = next(row for row in routes if row["scenario_id"] == "blackwing_descent_10n" and row["label"] == "Atramedes")
    omnotron = next(row for row in routes if row["scenario_id"] == "blackwing_descent_10n" and row["label"] == "Omnotron Defense System")
    corborus_approach_corridor = next(row for row in routes if row["scenario_id"] == "stonecore_5n" and row["label"] == "Corborus approach corridor")
    stonecore_sentry_gauntlet = next(row for row in routes if row["scenario_id"] == "stonecore_5n" and row["label"] == "stonecore sentry gauntlet")
    ozruk_approach_clearance = next(row for row in routes if row["scenario_id"] == "stonecore_5n" and row["label"] == "Ozruk approach clearance")
    post_slabhide_regroup = next(row for row in routes if row["scenario_id"] == "stonecore_5n" and row["label"] == "post-Slabhide regroup")
    stonecore_descent_regroup = next(row for row in routes if row["scenario_id"] == "stonecore_5n" and row["label"] == "stonecore descent regroup")
    stonecore_east_descent_shelf_regroup = next(row for row in routes if row["scenario_id"] == "stonecore_5n" and row["label"] == "stonecore east descent shelf regroup")
    lower_stonecore_regroup = next(row for row in routes if row["scenario_id"] == "stonecore_5n" and row["label"] == "lower stonecore approach regroup")
    post_ozruk_flayer_regroup = next(row for row in routes if row["scenario_id"] == "stonecore_5n" and row["label"] == "post-Ozruk flayer approach regroup")
    twilight_flayer_packs = next(row for row in routes if row["scenario_id"] == "stonecore_5n" and row["label"] == "twilight flayer packs")
    corborus = next(row for row in routes if row["scenario_id"] == "stonecore_5n" and row["label"] == "Corborus")
    slabhide = next(row for row in routes if row["scenario_id"] == "stonecore_5n" and row["label"] == "Slabhide")
    ozruk = next(row for row in routes if row["scenario_id"] == "stonecore_5n" and row["label"] == "Ozruk")
    azil = next(row for row in routes if row["scenario_id"] == "stonecore_5n" and row["label"] == "High Priestess Azil")
    nefarian = next(row for row in routes if row["scenario_id"] == "blackwing_descent_10n" and row["label"] == "Nefarian")
    assert atramedes["expected_bot_count"] == 10
    assert omnotron["source_entry"] == 42166
    assert omnotron["alternate_target_entries"] == [42166, 42178, 42179, 42180]
    assert omnotron["activation_action_entry"] == 42186
    assert omnotron["activation_action_id"] == 1
    assert omnotron["target_priority"]["alternate_target_entries"] == [42166, 42178, 42179, 42180]
    assert "interrupts" in omnotron["required_evidence"]
    assert slabhide["x"] == 1292.352
    assert slabhide["activation_data_id"] == 10
    assert slabhide["activation_data_value"] == 2
    assert slabhide["activation_summon_entry"] == 0
    assert corborus_approach_corridor["bot_start_map_id"] == 725
    assert corborus_approach_corridor["bot_start_x"] == 851.052
    assert corborus_approach_corridor["bot_start_z"] == 317.266
    assert corborus["x"] == 1103.9
    assert corborus["y"] == 864.733
    assert corborus["z"] == 287.98
    assert corborus["o"] == 0.25
    assert corborus["cluster_center"] == [1103.9, 864.733, 287.98]
    assert corborus["bot_start_x"] == 1103.9
    assert corborus["bot_start_y"] == 864.733
    assert corborus["bot_start_z"] == 287.98
    assert corborus["bot_start_o"] == 0.25
    assert corborus["activation_data_id"] == 10
    assert corborus["activation_data_value"] == 1
    assert corborus["activation_summon_entry"] == 0
    assert slabhide["bot_start_x"] == 1292.352
    assert slabhide["bot_start_z"] == 247.6368
    assert post_slabhide_regroup["step"] == 8
    assert post_slabhide_regroup["kind"] == "regroup"
    assert post_slabhide_regroup["node_kind"] == "regroup"
    assert post_slabhide_regroup["source_entry"] == 0
    assert post_slabhide_regroup["completion_policy"] == "arrival"
    assert post_slabhide_regroup["required_evidence"] == ["regrouping"]
    assert stonecore_descent_regroup["step"] == 9
    assert stonecore_descent_regroup["kind"] == "regroup"
    assert stonecore_descent_regroup["completion_policy"] == "arrival"
    assert stonecore_east_descent_shelf_regroup["step"] == 10
    assert stonecore_east_descent_shelf_regroup["kind"] == "regroup"
    assert stonecore_east_descent_shelf_regroup["x"] == 1412.931
    assert stonecore_east_descent_shelf_regroup["z"] == 231.5103
    assert stonecore_east_descent_shelf_regroup["completion_policy"] == "arrival"
    assert lower_stonecore_regroup["step"] == 11
    assert lower_stonecore_regroup["kind"] == "descent"
    assert lower_stonecore_regroup["node_kind"] == "descent"
    assert lower_stonecore_regroup["completion_policy"] == "arrival"
    assert lower_stonecore_regroup["required_evidence"] == ["regrouping"]
    assert stonecore_sentry_gauntlet["step"] == 12
    assert stonecore_sentry_gauntlet["bot_start_x"] == 1364.55
    assert stonecore_sentry_gauntlet["bot_start_z"] == 214.4
    assert ozruk_approach_clearance["step"] == 13
    assert ozruk_approach_clearance["kind"] == "regroup"
    assert ozruk_approach_clearance["node_kind"] == "regroup"
    assert ozruk_approach_clearance["source_entry"] == 0
    assert ozruk_approach_clearance["pack_target_entries"] == []
    assert ozruk_approach_clearance["cluster_radius_yards"] == 0.0
    assert ozruk_approach_clearance["completion_policy"] == "arrival"
    assert ozruk_approach_clearance["required_evidence"] == ["regrouping"]
    assert ozruk["step"] == 14
    assert ozruk["bot_start_x"] == 1507.859
    assert ozruk["bot_start_z"] == 217.3286
    assert post_ozruk_flayer_regroup["step"] == 15
    assert post_ozruk_flayer_regroup["kind"] == "descent"
    assert post_ozruk_flayer_regroup["node_kind"] == "descent"
    assert post_ozruk_flayer_regroup["x"] == 1329.93
    assert post_ozruk_flayer_regroup["z"] == 207.804
    assert post_ozruk_flayer_regroup["completion_policy"] == "arrival"
    assert post_ozruk_flayer_regroup["required_evidence"] == ["regrouping"]
    assert twilight_flayer_packs["step"] == 16
    assert twilight_flayer_packs["source_entry"] == 42808
    assert twilight_flayer_packs["source_guid"] == "340762"
    assert twilight_flayer_packs["pack_target_entries"] == [42808]
    assert twilight_flayer_packs["cluster_radius_yards"] == 100.0
    assert twilight_flayer_packs["bot_start_x"] == 1380.19
    assert twilight_flayer_packs["bot_start_z"] == 212.862
    assert azil["step"] == 17
    assert azil["x"] == 1337.3
    assert azil["y"] == 964.894
    assert azil["z"] == 214.2383
    assert azil["navigation_anchor_x"] == 1329.93
    assert azil["navigation_anchor_y"] == 985.712
    assert azil["navigation_anchor_z"] == 207.804
    assert azil["bot_start_x"] == 1329.93
    assert azil["bot_start_z"] == 207.804
    assert azil["source_entry"] == 42333
    assert azil["add_target_entries"] == [42428]
    assert azil["completion_policy"] == "boss_kill"
    assert corborus_approach_corridor["node_kind"] == "discovery_leg"
    assert corborus_approach_corridor["cluster_center"] == [1103.9, 864.733, 287.98]
    assert corborus_approach_corridor["cluster_radius_yards"] == 0.0
    assert corborus_approach_corridor["source_entry"] == 0
    assert corborus_approach_corridor["source_guid"] == ""
    assert corborus_approach_corridor["pack_target_entries"] == []
    assert "expected_alive_count" not in corborus_approach_corridor
    assert corborus_approach_corridor["expected_alive_count_semantics"] == "descriptive_only"
    assert corborus_approach_corridor["completion_policy"] == "corridor_clear_after_engagement"
    assert corborus_approach_corridor["scripted_event_entries"] == [43391]
    assert corborus_approach_corridor["scripted_event_transition_aura_ids"] == [81216]
    assert corborus_approach_corridor["scripted_event_require_passive"] is True
    assert 42810 not in corborus_approach_corridor["pack_target_entries"]
    assert slabhide["node_kind"] == "boss"
    assert slabhide["completion_policy"] == "boss_kill"
    assert nefarian["expected_bot_count"] == 10
    assert atramedes["activation_data_id"] == 10
    assert nefarian["activation_data_id"] == 35
    assert nefarian["activation_spawn_group_id"] == 0
    assert nefarian["activation_action_entry"] == 0
    assert nefarian["activation_action_id"] == 0
    assert nefarian["activation_summon_entry"] == 41376
    assert nefarian["activation_summon_z"] == 40.48163
    assert nefarian["opener_target_entry"] == 41270
    assert nefarian["opener_summon_entry"] == 0
    assert nefarian["bot_start_map_id"] == 669
    assert nefarian["bot_start_z"] == 6.57143
    assert "pulls" in nefarian["required_evidence"]
    assert "target_priority" in nefarian["required_evidence"]
    assert "tank_positioning" in nefarian["required_evidence"]
    assert nefarian["pull_contract"]["required"] is True
    assert nefarian["target_priority"]["required"] is True
    assert nefarian["healer_assignments"]["required"] is True
    assert nefarian["tank_positioning"]["required"] is True
    assert any(row["scenario_id"] == "blackwing_descent_10n" and "raid_aoe" in row["families"] for row in mechanics)
    chimaeron_mechanics = next(row for row in mechanics if row["scenario_id"] == "blackwing_descent_10n" and row["mechanic_profile"] == "raid_aoe_healer_assignment")
    assert {"healer_assignments", "recovery", "instance_reset"}.issubset(set(chimaeron_mechanics["required_evidence"]))
    assert manifests["report"]["ready_scenarios"] == 2
    assert "interrupts" in manifests["report"]["evidence_surfaces"]
    assert manifests["report"]["invalid_route_steps"] == []
    assert manifests["report"]["invalid_mechanic_profiles"] == []


def test_validation_scenario_manifest_rejects_partial_navigation_anchor():
    config = {
        "scenarios": [
            {
                "id": "anchor_validation",
                "map_id": 725,
                "difficulty": "normal_5man",
                "required_roles": {},
                "route": [
                    {
                        "step": 1,
                        "kind": "boss",
                        "label": "partial anchor",
                        "x": 1.0,
                        "y": 2.0,
                        "z": 3.0,
                        "navigation_anchor": {"x": 4.0, "y": 5.0},
                    }
                ],
            }
        ]
    }

    manifests = build_validation_scenario_manifests(config, {"scenarios": []}, {"all_passed": True})

    scenario = manifests["validation_scenarios"][0]
    assert scenario["route_coordinates_ready"] is False
    assert scenario["invalid_route_steps"][0]["reason"] == "navigation_anchor_missing_xyz"


def test_validation_route_bosses_are_scripted_encounter_targets():
    config = json.loads(Path("experiments/configs/validation_scenarios_cata_001.json").read_text(encoding="utf-8"))
    manifests = build_validation_scenario_manifests(
        config,
        {
            "all_ready": True,
            "scenarios": [
                {"scenario_id": "stonecore_5n", "ready": True, "missing": [], "role_counts": {"tank": 1, "healer": 1, "dps": 3}},
                {"scenario_id": "blackwing_descent_10n", "ready": True, "missing": [], "role_counts": {"tank": 2, "healer": 3, "dps": 5}},
            ],
        },
        {"all_passed": True},
    )
    routes = {
        (row["scenario_id"], row["label"]): row
        for row in manifests["validation_routes"]
        if row["kind"] == "boss"
    }

    scripted_bosses = {
        ("stonecore_5n", "Corborus"): (43438, "src/server/scripts/Maelstrom/maelstrom_script_loader.cpp", "AddSC_boss_corborus", "src/server/scripts/Maelstrom/Stonecore/boss_corborus.cpp", "boss_corborus"),
        ("stonecore_5n", "Slabhide"): (43214, "src/server/scripts/Maelstrom/maelstrom_script_loader.cpp", "AddSC_boss_slabhide", "src/server/scripts/Maelstrom/Stonecore/boss_slabhide.cpp", "boss_slabhide"),
        ("stonecore_5n", "Ozruk"): (42188, "src/server/scripts/Maelstrom/maelstrom_script_loader.cpp", "AddSC_boss_ozruk", "src/server/scripts/Maelstrom/Stonecore/boss_ozruk.cpp", "boss_ozruk"),
        ("stonecore_5n", "High Priestess Azil"): (42333, "src/server/scripts/Maelstrom/maelstrom_script_loader.cpp", "AddSC_boss_high_priestess_azil", "src/server/scripts/Maelstrom/Stonecore/boss_high_priestess_azil.cpp", "boss_high_priestess_azil"),
        ("blackwing_descent_10n", "Magmaw"): (41570, "src/server/scripts/EasternKingdoms/eastern_kingdoms_script_loader.cpp", "AddSC_boss_magmaw", "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_magmaw.cpp", "boss_magmaw"),
        ("blackwing_descent_10n", "Omnotron Defense System"): (42166, "src/server/scripts/EasternKingdoms/eastern_kingdoms_script_loader.cpp", "AddSC_boss_omnotron_defense_system", "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_omnotron_defense_system.cpp", "boss_omnotron_defense_system"),
        ("blackwing_descent_10n", "Maloriak"): (41378, "src/server/scripts/EasternKingdoms/eastern_kingdoms_script_loader.cpp", "AddSC_boss_maloriak", "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_maloriak.cpp", "boss_maloriak"),
        ("blackwing_descent_10n", "Atramedes"): (41442, "src/server/scripts/EasternKingdoms/eastern_kingdoms_script_loader.cpp", "AddSC_boss_atramedes", "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_atramedes.cpp", "boss_atramedes"),
        ("blackwing_descent_10n", "Chimaeron"): (43296, "src/server/scripts/EasternKingdoms/eastern_kingdoms_script_loader.cpp", "AddSC_boss_chimaeron", "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_chimaeron.cpp", "boss_chimaeron"),
        ("blackwing_descent_10n", "Nefarian"): (41376, "src/server/scripts/EasternKingdoms/eastern_kingdoms_script_loader.cpp", "AddSC_boss_nefarians_end", "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_nefarians_end.cpp", "boss_nefarians_end"),
    }

    assert set(scripted_bosses).issubset(routes)
    for key, (entry, loader_path, addsc, script_path, script_symbol) in scripted_bosses.items():
        assert routes[key]["source_entry"] == entry
        if key == ("blackwing_descent_10n", "Omnotron Defense System"):
            assert routes[key]["activation_action_entry"] == 42186
        assert addsc in Path(loader_path).read_text(encoding="utf-8")
        script = Path(script_path).read_text(encoding="utf-8")
        assert script_symbol in script
        assert "BossAI" in script


def test_validation_run_plan_preserves_instance_positions_and_tags():
    scenarios = [
        {"scenario_id": "stonecore_5n", "instance": "The Stonecore", "map_id": 725, "difficulty": "normal_5man", "required_roles": {"tank": 1, "healer": 1, "dps": 3}},
        {"scenario_id": "blackwing_descent_10n", "instance": "Blackwing Descent", "map_id": 669, "difficulty": "normal_10man", "required_roles": {"tank": 2, "healer": 3, "dps": 5}},
    ]

    plan = build_validation_run_plan(scenarios, Path("dataset/live_validation_scenarios"), Path("dataset/live_validation_scenario_reports_built"), Path("dataset/validation_scenarios"), 300, 900)
    rows = {row["scenario_id"]: row for row in plan["scenarios"]}
    stonecore = rows["stonecore_5n"]
    bwd = rows["blackwing_descent_10n"]

    assert plan["schema"] == "bot_validation_run_plan_v1"
    assert stonecore["preserve_start_position"] is True
    assert "--keep-bot-pool-position" in stonecore["live_validate_command"]
    assert "--bot-pool-tag" in stonecore["live_validate_command"]
    assert "--validation-scenario-id" in stonecore["live_validate_command"]
    assert "stonecore_5n" in stonecore["live_validate_command"]
    assert "blackwing_descent_10n" in bwd["live_validate_command"]
    assert bwd["scenario_report_command"].count("--scenario-id") == 1
    assert "pixi" in stonecore["live_validate_shell"]
    assert plan["duration_policy"] == "completion-watchdog"
    assert "--duration-policy" in stonecore["live_validate_command"]
    assert "completion-watchdog" in stonecore["live_validate_command"]
    assert "--observe-sec" not in stonecore["live_validate_command"]
    assert "--timeout-sec" not in stonecore["live_validate_command"]


def test_validation_run_plan_reusable_session_cli_flag(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "validation_scenarios"
    output_dir = tmp_path / "validation_run_plan"
    write_jsonl(scenarios_dir / "validation_scenarios.jsonl", [{"scenario_id": "stonecore_5n"}])
    write_jsonl(scenarios_dir / "validation_routes.jsonl", [])
    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-validation-run-plan",
            "--validation-scenario-dir",
            str(scenarios_dir),
            "--output-dir",
            str(output_dir),
            "--live-output-root",
            str(tmp_path / "live"),
            "--scenario-report-root",
            str(tmp_path / "reports"),
            "--timeout-sec",
            "2400",
            "--reusable-session",
        ],
    )

    assert validation_run_plan_main() == 0
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["reusable_session"]["enabled"] is True
    command = manifest["scenarios"][0]["live_validate_command"]
    assert command[command.index("--transport") + 1] == "session"
    assert command[command.index("--timeout-sec") + 1] == "2400"


def test_validation_run_plan_reusable_session_isolates_full_clear_output_and_timeout():
    scenarios = [
        {"scenario_id": "stonecore_5n", "instance": "The Stonecore", "map_id": 725, "difficulty": "normal_5man", "required_roles": {"tank": 1, "healer": 1, "dps": 3}},
    ]
    routes_by_scenario = {
        "stonecore_5n": [
            {"scenario_id": "stonecore_5n", "route_node_id": "stonecore_corborus", "step": 2, "kind": "boss", "label": "Corborus"},
        ],
    }

    plan = build_validation_run_plan(
        scenarios,
        Path("dataset/live_validation_scenarios"),
        Path("dataset/live_validation_scenario_reports_built"),
        Path("dataset/validation_scenarios"),
        300,
        2400,
        routes_by_scenario,
        reusable_session=True,
    )
    stonecore = plan["scenarios"][0]
    full_command = stonecore["live_validate_command"]
    segment_command = stonecore["segments"][0]["live_validate_command"]

    assert plan["reusable_session"] == {
        "enabled": True,
        "transport": "session",
        "full_clear_output_dir_template": "{scenario_id}_reusable_session_full_clear",
        "preserves_existing_report_paths": True,
    }
    assert stonecore["reusable_session"]["enabled"] is True
    assert stonecore["reusable_session"]["emergency_timeout_sec"] == 2400
    assert full_command[full_command.index("--transport") + 1] == "session"
    assert full_command[full_command.index("--timeout-sec") + 1] == "2400"
    assert full_command[full_command.index("--output-dir") + 1] == "dataset/live_validation_scenarios/stonecore_5n_reusable_session_full_clear"
    assert "dataset/live_validation_scenarios/stonecore_5n_reusable_session_full_clear/report.json" in stonecore["scenario_report_command"]
    assert "--transport" not in segment_command
    assert "--timeout-sec" not in segment_command


def test_validation_run_plan_reusable_session_keeps_fixed_window_segment_defaults():
    scenarios = [{"scenario_id": "stonecore_5n"}]
    routes_by_scenario = {
        "stonecore_5n": [
            {"scenario_id": "stonecore_5n", "route_node_id": "stonecore_corborus", "step": 2, "kind": "boss", "label": "Corborus"},
        ],
    }

    plan = build_validation_run_plan(
        scenarios,
        Path("dataset/live_validation_scenarios"),
        Path("dataset/live_validation_scenario_reports_built"),
        Path("dataset/validation_scenarios"),
        300,
        2400,
        routes_by_scenario,
        duration_policy="fixed-window",
        reusable_session=True,
    )
    stonecore = plan["scenarios"][0]

    assert stonecore["live_validate_command"][stonecore["live_validate_command"].index("--timeout-sec") + 1] == "2400"
    segment_command = stonecore["segments"][0]["live_validate_command"]
    assert "--transport" not in segment_command
    assert segment_command[segment_command.index("--timeout-sec") + 1] == "2400"


def test_validation_run_plan_segments_boss_routes_for_aggregate_reports():
    scenarios = [
        {"scenario_id": "blackwing_descent_10n", "instance": "Blackwing Descent", "map_id": 669, "difficulty": "normal_10man", "required_roles": {"tank": 2, "healer": 3, "dps": 5}},
    ]
    routes_by_scenario = {
        "blackwing_descent_10n": [
            {"scenario_id": "blackwing_descent_10n", "route_node_id": "bwd_trash_entry", "step": 1, "kind": "trash", "label": "entry trash"},
            {"scenario_id": "blackwing_descent_10n", "route_node_id": "bwd_magmaw", "step": 2, "kind": "boss", "label": "Magmaw", "mechanic_profile": "magmaw"},
            {"scenario_id": "blackwing_descent_10n", "route_node_id": "bwd_omnotron", "step": 3, "kind": "boss", "label": "Omnotron Defense System", "mechanic_profile": "omnotron"},
            {"scenario_id": "blackwing_descent_10n", "route_node_id": "bwd_maloriak", "step": 5, "kind": "boss", "label": "Maloriak", "mechanic_profile": "maloriak"},
            {"scenario_id": "blackwing_descent_10n", "route_node_id": "bwd_atramedes", "step": 6, "kind": "boss", "label": "Atramedes", "mechanic_profile": "atramedes"},
            {"scenario_id": "blackwing_descent_10n", "route_node_id": "bwd_chimaeron", "step": 7, "kind": "boss", "label": "Chimaeron", "mechanic_profile": "chimaeron"},
            {"scenario_id": "blackwing_descent_10n", "route_node_id": "bwd_nefarian", "step": 8, "kind": "boss", "label": "Nefarian", "mechanic_profile": "nefarian"},
        ],
    }

    plan = build_validation_run_plan(
        scenarios,
        Path("dataset/live_validation_scenarios"),
        Path("dataset/live_validation_scenario_reports_built"),
        Path("dataset/validation_scenarios"),
        300,
        900,
        routes_by_scenario,
    )
    bwd = plan["scenarios"][0]

    assert bwd["segment_count"] == 7
    assert [segment["label"] for segment in bwd["segments"]][0] == "entry trash"
    assert bwd["segments"][-1]["segment_id"] == "08_nefarian"
    assert bwd["scenario_report_command"].count("--live-report") == 8
    assert "dataset/live_validation_scenarios/blackwing_descent_10n/report.json" in bwd["scenario_report_command"]
    assert "dataset/live_validation_scenarios/blackwing_descent_10n/01_entry_trash/report.json" in bwd["scenario_report_command"]
    assert "dataset/live_validation_scenarios/blackwing_descent_10n/02_magmaw/report.json" in bwd["scenario_report_command"]
    full_command = bwd["live_validate_command"]
    assert "--validation-route-manifest" in full_command
    assert "--validation-route-node-id" not in full_command
    assert "--validation-route-kind" not in full_command
    assert "--validation-segment-id" not in full_command
    assert full_command[full_command.index("--output-dir") + 1] == "dataset/live_validation_scenarios/blackwing_descent_10n"
    first_command = bwd["segments"][1]["live_validate_command"]
    assert "--validation-scenario-id" in first_command
    assert first_command[first_command.index("--validation-scenario-id") + 1] == "blackwing_descent_10n"
    assert first_command[first_command.index("--validation-segment-id") + 1] == "02_magmaw"
    assert first_command[first_command.index("--validation-route-node-id") + 1] == "bwd_magmaw"
    assert first_command[first_command.index("--validation-route-label") + 1] == "Magmaw"
    assert first_command[first_command.index("--validation-route-kind") + 1] == "boss"
    assert first_command[first_command.index("--validation-route-step") + 1] == "2"
    assert first_command[first_command.index("--validation-mechanic-profile") + 1] == "magmaw"
    for segment in bwd["segments"]:
        assert "--keep-bot-pool-position" in segment["live_validate_command"]
        assert "blackwing_descent_10n" in segment["live_validate_command"]
    assert bwd["segments"][0]["kind"] == "trash"


def test_validation_run_plan_preserves_required_evidence_contracts():
    scenarios = [
        {
            "scenario_id": "stonecore_5n",
            "instance": "The Stonecore",
            "map_id": 725,
            "difficulty": "normal_5man",
            "required_roles": {"tank": 1, "healer": 1, "dps": 3},
            "group_kind": "party",
            "required_evidence": ["role_assignments", "party_formation"],
            "role_assignment": {"required_roles": {"tank": 1, "healer": 1, "dps": 3}},
        },
    ]
    routes_by_scenario = {
        "stonecore_5n": [
            {
                "scenario_id": "stonecore_5n",
                "route_node_id": "stonecore_azil",
                "step": 8,
                "kind": "boss",
                "label": "High Priestess Azil",
                "mechanic_profile": "adds_ground_danger_interrupts",
                "required_evidence": ["pulls", "target_priority", "interrupts", "tank_positioning"],
                "evidence_contract": [{"evidence": "interrupts", "required": True}],
            }
        ],
    }

    plan = build_validation_run_plan(
        scenarios,
        Path("dataset/live_validation_scenarios"),
        Path("dataset/live_validation_scenario_reports_built"),
        Path("dataset/validation_scenarios"),
        300,
        900,
        routes_by_scenario,
    )
    stonecore = plan["scenarios"][0]
    segment = stonecore["segments"][0]

    assert stonecore["group_kind"] == "party"
    assert stonecore["required_evidence"] == ["role_assignments", "party_formation"]
    assert segment["required_evidence"] == ["pulls", "target_priority", "interrupts", "tank_positioning"]
    assert segment["evidence_contract"] == [{"evidence": "interrupts", "required": True}]


def test_validation_run_plan_marks_segments_without_coordinates_non_executable(tmp_path):
    scenarios = [
        {"scenario_id": "blackwing_descent_10n", "instance": "Blackwing Descent", "map_id": 669, "difficulty": "normal_10man", "required_roles": {"tank": 2, "healer": 3, "dps": 5}},
    ]
    routes_by_scenario = {
        "blackwing_descent_10n": [
            {"scenario_id": "blackwing_descent_10n", "route_node_id": "bwd_magmaw", "step": 2, "kind": "boss", "label": "Magmaw", "coordinates_valid": False, "coordinate_missing_reason": "missing_xyz"},
        ],
    }

    plan = build_validation_run_plan(
        scenarios,
        Path("dataset/live_validation_scenarios"),
        Path("dataset/live_validation_scenario_reports_built"),
        Path("dataset/validation_scenarios"),
        300,
        900,
        routes_by_scenario,
    )
    script = tmp_path / "run.sh"
    from tools.bot_ml.build_validation_run_plan import write_shell_script

    write_shell_script(script, plan)
    shell = script.read_text(encoding="utf-8")
    bwd = plan["scenarios"][0]

    assert bwd["segment_count"] == 1
    assert bwd["executable_segment_count"] == 0
    assert bwd["invalid_segment_count"] == 1
    assert bwd["segments"][0]["executable"] is False
    assert bwd["segments"][0]["skip_reason"] == "missing_route_coordinates"
    assert bwd["scenario_report_command"].count("--live-report") == 1
    assert "dataset/live_validation_scenarios/blackwing_descent_10n/report.json" in bwd["scenario_report_command"]
    assert "Skipping non-executable validation segment 02_magmaw" in shell


def test_validation_run_status_reports_missing_segments_and_next_commands(tmp_path):
    live_root = tmp_path / "live_validation_scenarios"
    report_root = tmp_path / "scenario_reports"
    plan = {
        "scenarios": [
            {
                "scenario_id": "blackwing_descent_10n",
                "instance": "Blackwing Descent",
                "difficulty": "normal_10man",
                "live_validate_shell": "pixi run bot-live-validate --validation-scenario-id blackwing_descent_10n",
                "scenario_report_shell": "pixi run bot-live-scenario-reports --scenario-id blackwing_descent_10n",
                "segments": [
                    {
                        "segment_id": "01_entry_trash",
                        "route_node_id": "bwd_entry_trash",
                        "kind": "trash",
                        "label": "entry trash",
                        "mechanic_profile": "",
                        "executable": True,
                        "live_output_dir": str(live_root / "blackwing_descent_10n" / "01_entry_trash"),
                        "live_validate_command": ["pixi", "run", "bot-live-validate", "--validation-segment-id", "01_entry_trash"],
                        "live_validate_shell": "pixi run bot-live-validate --validation-segment-id 01_entry_trash",
                    },
                    {
                        "segment_id": "02_magmaw",
                        "route_node_id": "bwd_magmaw",
                        "kind": "boss",
                        "label": "Magmaw",
                        "mechanic_profile": "magmaw",
                        "executable": True,
                        "live_output_dir": str(live_root / "blackwing_descent_10n" / "02_magmaw"),
                        "live_validate_command": ["pixi", "run", "bot-live-validate", "--validation-segment-id", "02_magmaw"],
                        "live_validate_shell": "pixi run bot-live-validate --validation-segment-id 02_magmaw",
                    },
                    {
                        "segment_id": "03_omnotron",
                        "route_node_id": "bwd_omnotron",
                        "kind": "boss",
                        "label": "Omnotron",
                        "mechanic_profile": "omnotron",
                        "executable": True,
                        "live_output_dir": str(live_root / "blackwing_descent_10n" / "03_omnotron"),
                        "live_validate_command": ["pixi", "run", "bot-live-validate", "--validation-segment-id", "03_omnotron"],
                        "live_validate_shell": "pixi run bot-live-validate --validation-segment-id 03_omnotron",
                    },
                ],
            }
        ]
    }
    present_report = live_root / "blackwing_descent_10n" / "02_magmaw" / "report.json"
    present_report.parent.mkdir(parents=True)
    present_report.write_text(
        json.dumps(
            {
                "schema": "bot_live_validation_report_v1",
                "returncode": 0,
                "timed_out": False,
                "validation_context": {
                    "scenario_id": "blackwing_descent_10n",
                    "segment_id": "02_magmaw",
                    "route_node_id": "bwd_magmaw",
                    "route_kind": "boss",
                    "route_generation": 2,
                    "mechanic_profile": "magmaw",
                },
                "trace": {
                    "entries": [
                        {"action": "raid_boss_killed", "result": "ok", "target_id": 41570, "route_node_id": "bwd_magmaw", "route_generation": 2},
                        {"action": "validation_route_terminal", "result": "boss_killed", "route_node_id": "bwd_magmaw", "route_generation": 2},
                    ]
                },
                "summary": {"raid_boss_kills": 1},
            }
        ),
        encoding="utf-8",
    )
    report_root.mkdir()
    (report_root / "blackwing_descent_10n.json").write_text(
        json.dumps({"scenario_id": "blackwing_descent_10n", "clear_complete": False, "complete_segment_coverage": False}),
        encoding="utf-8",
    )

    status = build_validation_run_status(plan, report_root)
    bwd = status["scenarios"][0]

    assert status["all_ready"] is False
    assert bwd["present_segments"] == ["02_magmaw"]
    assert bwd["existing_segments"] == ["02_magmaw"]
    assert bwd["missing_segments"] == ["01_entry_trash", "03_omnotron"]
    assert bwd["invalid_segments"] == []
    assert bwd["blockers"] == ["missing_segment_live_reports", "incomplete_segment_coverage", "scenario_clear_not_complete"]
    assert bwd["next_commands"][0] == "pixi run bot-live-validate --validation-segment-id 01_entry_trash"
    assert bwd["next_commands"][1] == "pixi run bot-live-validate --validation-segment-id 03_omnotron"
    assert bwd["next_commands"][2] == "pixi run bot-live-validate --validation-scenario-id blackwing_descent_10n"
    assert bwd["next_commands"][-1].startswith("pixi run bot-live-scenario-reports")
    assert bwd["validation_next_commands"]["segment_reruns"] == [
        "pixi run bot-live-validate --validation-segment-id 01_entry_trash",
        "pixi run bot-live-validate --validation-segment-id 03_omnotron",
    ]
    assert bwd["validation_next_commands"]["uninterrupted_full_clear"] == "pixi run bot-live-validate --validation-scenario-id blackwing_descent_10n"
    assert bwd["validation_next_commands"]["scenario_report_rebuild"].startswith("pixi run bot-live-scenario-reports")


def test_validation_run_status_reruns_invalid_existing_segment_reports(tmp_path):
    live_root = tmp_path / "live_validation_scenarios"
    report_root = tmp_path / "scenario_reports"
    plan = {
        "scenarios": [
            {
                "scenario_id": "stonecore_5n",
                "instance": "The Stonecore",
                "difficulty": "normal_5man",
                "live_validate_shell": "pixi run bot-live-validate --validation-scenario-id stonecore_5n",
                "scenario_report_shell": "pixi run bot-live-scenario-reports --scenario-id stonecore_5n",
                "segments": [
                    {
                        "segment_id": "02_corborus",
                        "route_node_id": "stonecore_corborus",
                        "kind": "boss",
                        "label": "Corborus",
                        "mechanic_profile": "corborus",
                        "executable": True,
                        "live_output_dir": str(live_root / "stonecore_5n" / "02_corborus"),
                        "live_validate_shell": "pixi run bot-live-validate --validation-segment-id 02_corborus",
                    }
                ],
            }
        ]
    }
    bad_report = live_root / "stonecore_5n" / "02_corborus" / "report.json"
    bad_report.parent.mkdir(parents=True)
    bad_report.write_text(
        json.dumps(
            {
                "schema": "bot_live_validation_report_v1",
                "returncode": 0,
                "timed_out": False,
                "validation_context": {
                    "scenario_id": "stonecore_5n",
                    "segment_id": "wrong_segment",
                    "route_node_id": "stonecore_corborus",
                    "route_kind": "boss",
                    "mechanic_profile": "corborus",
                },
                "trace": {"entries": [{"action": "move"}]},
            }
        ),
        encoding="utf-8",
    )
    report_root.mkdir()
    (report_root / "stonecore_5n.json").write_text(
        json.dumps({"scenario_id": "stonecore_5n", "clear_complete": False, "complete_segment_coverage": False}),
        encoding="utf-8",
    )

    status = build_validation_run_status(plan, report_root)
    stonecore = status["scenarios"][0]
    report_row = stonecore["segment_reports"][0]

    assert stonecore["present_segments"] == []
    assert stonecore["existing_segments"] == ["02_corborus"]
    assert stonecore["missing_segments"] == []
    assert stonecore["invalid_segments"] == ["02_corborus"]
    assert "invalid_segment_live_reports" in stonecore["blockers"]
    assert "segment_id_mismatch" in report_row["invalid_reasons"]
    assert "missing_boss_kill_evidence" in report_row["invalid_reasons"]
    assert stonecore["next_commands"][0] == "pixi run bot-live-validate --validation-segment-id 02_corborus"
    assert stonecore["next_commands"][1] == "pixi run bot-live-validate --validation-scenario-id stonecore_5n"
    assert stonecore["validation_next_commands"]["uninterrupted_full_clear"] == "pixi run bot-live-validate --validation-scenario-id stonecore_5n"


def test_validation_run_status_requires_node_scoped_segment_evidence_for_full_clear(tmp_path):
    live_root = tmp_path / "live_validation_scenarios"
    report_root = tmp_path / "scenario_reports"
    plan = {
        "scenarios": [
            {
                "scenario_id": "stonecore_5n",
                "instance": "The Stonecore",
                "difficulty": "normal_5man",
                "live_validate_shell": "pixi run bot-live-validate --validation-scenario-id stonecore_5n",
                "scenario_report_shell": "pixi run bot-live-scenario-reports --scenario-id stonecore_5n",
                "segments": [
                    {
                        "segment_id": "01_entrance_packs",
                        "route_node_id": "stonecore_trash",
                        "kind": "trash",
                        "label": "entrance packs",
                        "mechanic_profile": "",
                        "executable": True,
                        "live_output_dir": str(live_root / "stonecore_5n" / "01_entrance_packs"),
                        "live_validate_shell": "pixi run bot-live-validate --validation-segment-id 01_entrance_packs",
                    },
                    {
                        "segment_id": "02_corborus",
                        "route_node_id": "stonecore_corborus",
                        "kind": "boss",
                        "label": "Corborus",
                        "mechanic_profile": "burrow_adds_ground_danger",
                        "executable": True,
                        "live_output_dir": str(live_root / "stonecore_5n" / "02_corborus"),
                        "live_validate_shell": "pixi run bot-live-validate --validation-segment-id 02_corborus",
                    },
                ],
            }
        ]
    }
    report_root.mkdir()
    (report_root / "stonecore_5n.json").write_text(
        json.dumps(
            {
                "scenario_id": "stonecore_5n",
                "clear_complete": True,
                "completion_claim_valid": True,
                "completion_evidence_mode": "uninterrupted_live_clear",
                "natural_full_clear_evidence": True,
                "complete_segment_coverage": True,
                "source_segments": ["01_entrance_packs", "02_corborus"],
                "strict_completion_evidence": True,
                "missing_terminal_route_nodes": [],
                "missing_boss_route_nodes": [],
                "forbidden_completion_assists": [],
                "route_terminal_evidence": [
                    {"route_node_id": "stonecore_trash", "route_generation": 1},
                    {"route_node_id": "stonecore_corborus", "route_generation": 2},
                ],
                "real_boss_kill_evidence": [{"route_node_id": "stonecore_corborus", "route_generation": 2}],
                "segment_results": [
                    {
                        "segment_id": "01_entrance_packs",
                        "route_node_id": "stonecore_trash",
                        "route_generation": 1,
                        "route_kind": "trash",
                        "mechanic_profile": "",
                        "trash_pulls": 1,
                        "evidence_counts": {"pulls": 1},
                        "terminal_evidence": True,
                        "failure_labels": [],
                        "failure_reason": "",
                    },
                    {
                        "segment_id": "02_corborus",
                        "route_node_id": "stonecore_corborus",
                        "route_generation": 2,
                        "route_kind": "boss",
                        "mechanic_profile": "burrow_adds_ground_danger",
                        "real_boss_kill_evidence": True,
                        "terminal_evidence": True,
                        "failure_labels": [],
                        "failure_reason": "",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    status = build_validation_run_status(plan, report_root)
    stonecore = status["scenarios"][0]

    assert status["all_ready"] is True
    assert stonecore["full_clear_ready"] is True
    assert stonecore["present_segments"] == ["01_entrance_packs", "02_corborus"]
    assert stonecore["missing_segments"] == []
    assert stonecore["invalid_segments"] == []
    assert stonecore["blockers"] == []
    assert stonecore["next_commands"] == []
    assert {row["evidence_source"] for row in stonecore["segment_reports"]} == {"scenario_segment_result"}


def test_validation_run_status_accepts_scoped_real_boss_kill_evidence(tmp_path):
    live_root = tmp_path / "live_validation_scenarios"
    report_root = tmp_path / "scenario_reports"
    plan = {
        "scenarios": [
            {
                "scenario_id": "stonecore_5n",
                "instance": "The Stonecore",
                "difficulty": "normal_5man",
                "segments": [
                    {
                        "segment_id": "02_corborus",
                        "route_node_id": "stonecore_corborus",
                        "kind": "boss",
                        "label": "Corborus",
                        "mechanic_profile": "corborus",
                        "executable": True,
                        "live_output_dir": str(live_root / "stonecore_5n" / "02_corborus"),
                        "live_validate_shell": "pixi run bot-live-validate --validation-segment-id 02_corborus",
                    }
                ],
            }
        ]
    }
    report = live_root / "stonecore_5n" / "02_corborus" / "report.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "schema": "bot_live_validation_report_v1",
                "returncode": 0,
                "timed_out": False,
                "validation_context": {
                    "scenario_id": "stonecore_5n",
                    "segment_id": "02_corborus",
                    "route_node_id": "stonecore_corborus",
                    "route_kind": "boss",
                    "route_generation": 1,
                    "mechanic_profile": "corborus",
                },
                "trace": {
                    "entries": [
                        {"action": "boss_killed", "result": "ok", "target_id": 43438, "route_node_id": "stonecore_corborus", "route_generation": 1},
                        {"action": "validation_route_terminal", "result": "boss_killed", "route_node_id": "stonecore_corborus", "route_generation": 1},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    report_root.mkdir()
    (report_root / "stonecore_5n.json").write_text(
        json.dumps(
            {
                "scenario_id": "stonecore_5n",
                "clear_complete": True,
                "completion_claim_valid": True,
                "completion_evidence_mode": "uninterrupted_live_clear",
                "complete_segment_coverage": True,
                "strict_completion_evidence": True,
                "missing_terminal_route_nodes": [],
                "missing_boss_route_nodes": [],
                "forbidden_completion_assists": [],
            }
        ),
        encoding="utf-8",
    )

    status = build_validation_run_status(plan, report_root)
    stonecore = status["scenarios"][0]
    report_row = stonecore["segment_reports"][0]

    assert stonecore["present_segments"] == ["02_corborus"]
    assert stonecore["invalid_segments"] == []
    assert report_row["boss_evidence_ready"] is True
    assert report_row["evidence_source"] == "segment_report"


def test_validation_run_status_rejects_live_segment_with_route_node_drift(tmp_path):
    live_root = tmp_path / "live_validation_scenarios"
    report_root = tmp_path / "scenario_reports"
    plan = {
        "scenarios": [
            {
                "scenario_id": "stonecore_5n",
                "instance": "The Stonecore",
                "difficulty": "normal_5man",
                "scenario_report_shell": "pixi run bot-live-scenario-reports --scenario-id stonecore_5n",
                "segments": [
                    {
                        "segment_id": "02_corborus",
                        "route_node_id": "current_corborus_route",
                        "kind": "boss",
                        "label": "Corborus",
                        "mechanic_profile": "corborus",
                        "executable": True,
                        "live_output_dir": str(live_root / "stonecore_5n" / "02_corborus"),
                        "live_validate_shell": "pixi run bot-live-validate --validation-segment-id 02_corborus",
                    }
                ],
            }
        ]
    }
    report = live_root / "stonecore_5n" / "02_corborus" / "report.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "schema": "bot_live_validation_report_v1",
                "returncode": 0,
                "timed_out": False,
                "validation_context": {
                    "scenario_id": "stonecore_5n",
                    "segment_id": "02_corborus",
                    "route_node_id": "old_corborus_route",
                    "route_kind": "boss",
                    "mechanic_profile": "corborus",
                },
                "summary": {"boss_kills": 1},
            }
        ),
        encoding="utf-8",
    )
    report_root.mkdir()
    (report_root / "stonecore_5n.json").write_text(
        json.dumps({"scenario_id": "stonecore_5n", "clear_complete": False, "complete_segment_coverage": True}),
        encoding="utf-8",
    )

    status = build_validation_run_status(plan, report_root)
    stonecore = status["scenarios"][0]
    report_row = stonecore["segment_reports"][0]

    assert stonecore["present_segments"] == []
    assert stonecore["invalid_segments"] == ["02_corborus"]
    assert report_row["validation_context_matches"] is False
    assert report_row["warnings"] == []
    assert "route_node_id_mismatch" in report_row["invalid_reasons"]
    assert stonecore["next_commands"][0] == "pixi run bot-live-validate --validation-segment-id 02_corborus"


def test_validation_run_status_accepts_trash_segment_evidence(tmp_path):
    live_root = tmp_path / "live_validation_scenarios"
    report_root = tmp_path / "scenario_reports"
    plan = {
        "scenarios": [
            {
                "scenario_id": "stonecore_5n",
                "instance": "The Stonecore",
                "difficulty": "normal_5man",
                "segments": [
                    {
                        "segment_id": "01_entrance_packs",
                        "route_node_id": "stonecore_entrance_trash",
                        "kind": "trash",
                        "label": "entrance packs",
                        "mechanic_profile": "",
                        "executable": True,
                        "live_output_dir": str(live_root / "stonecore_5n" / "01_entrance_packs"),
                        "live_validate_shell": "pixi run bot-live-validate --validation-segment-id 01_entrance_packs",
                    }
                ],
            }
        ]
    }
    report = live_root / "stonecore_5n" / "01_entrance_packs" / "report.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "schema": "bot_live_validation_report_v1",
                "returncode": 0,
                "timed_out": False,
                "validation_context": {
                    "scenario_id": "stonecore_5n",
                    "segment_id": "01_entrance_packs",
                    "route_node_id": "stonecore_entrance_trash",
                    "route_kind": "trash",
                    "route_generation": 1,
                    "mechanic_profile": "",
                },
                "summary": {"trash_pulls": 2},
                "trace": {
                    "entries": [
                        {"action": "trash_action", "situation": "normal_dungeon_trash", "route_node_id": "stonecore_entrance_trash", "route_generation": 1},
                        {"action": "validation_route_terminal", "result": "trash_cluster_cleared", "route_node_id": "stonecore_entrance_trash", "route_generation": 1},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    report_root.mkdir()
    (report_root / "stonecore_5n.json").write_text(
        json.dumps(
            {
                "scenario_id": "stonecore_5n",
                "clear_complete": True,
                "completion_claim_valid": True,
                "completion_evidence_mode": "uninterrupted_live_clear",
                "complete_segment_coverage": True,
                "strict_completion_evidence": True,
                "missing_terminal_route_nodes": [],
                "missing_boss_route_nodes": [],
                "forbidden_completion_assists": [],
                "route_terminal_evidence": [{"route_node_id": "stonecore_entrance_trash", "route_generation": 1}],
                "real_boss_kill_evidence": [],
            }
        ),
        encoding="utf-8",
    )

    status = build_validation_run_status(plan, report_root)
    stonecore = status["scenarios"][0]
    report_row = stonecore["segment_reports"][0]

    assert status["all_ready"] is True
    assert stonecore["present_segments"] == ["01_entrance_packs"]
    assert report_row["trash_evidence_ready"] is True
    assert report_row["segment_ready"] is True


def test_validation_run_status_blocks_missing_required_mechanic_evidence(tmp_path):
    live_root = tmp_path / "live_validation_scenarios"
    report_root = tmp_path / "scenario_reports"
    plan = {
        "scenarios": [
            {
                "scenario_id": "stonecore_5n",
                "instance": "The Stonecore",
                "difficulty": "normal_5man",
                "segments": [
                    {
                        "segment_id": "08_high_priestess_azil",
                        "route_node_id": "stonecore_azil",
                        "kind": "boss",
                        "label": "High Priestess Azil",
                        "mechanic_profile": "adds_ground_danger_interrupts",
                        "required_evidence": ["pulls", "target_priority", "interrupts"],
                        "executable": True,
                        "live_output_dir": str(live_root / "stonecore_5n" / "08_high_priestess_azil"),
                        "live_validate_shell": "pixi run bot-live-validate --validation-segment-id 08_high_priestess_azil",
                    }
                ],
            }
        ]
    }
    report = live_root / "stonecore_5n" / "08_high_priestess_azil" / "report.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "schema": "bot_live_validation_report_v1",
                "returncode": 0,
                "timed_out": False,
                "validation_context": {
                    "scenario_id": "stonecore_5n",
                    "segment_id": "08_high_priestess_azil",
                    "route_node_id": "stonecore_azil",
                    "route_kind": "boss",
                    "route_generation": 1,
                    "mechanic_profile": "adds_ground_danger_interrupts",
                },
                "summary": {"boss_kills": 1},
                "trace": {
                    "entries": [
                        {"action": "boss_killed", "situation": "dungeon_boss", "result": "ok", "target_id": 42333, "route_node_id": "stonecore_azil", "route_generation": 1},
                        {"action": "validation_route_terminal", "result": "boss_killed", "route_node_id": "stonecore_azil", "route_generation": 1},
                        {"action": "boss_started", "route_node_id": "stonecore_azil", "route_generation": 1},
                    ]
                },
                "evidence": {"boss_kill_evidence": 1, "validation_evidence_counts": {"pulls": 1}},
            }
        ),
        encoding="utf-8",
    )
    report_root.mkdir()
    (report_root / "stonecore_5n.json").write_text(
        json.dumps(
            {
                "scenario_id": "stonecore_5n",
                "clear_complete": True,
                "completion_claim_valid": True,
                "completion_evidence_mode": "uninterrupted_live_clear",
                "complete_segment_coverage": True,
            }
        ),
        encoding="utf-8",
    )

    status = build_validation_run_status(plan, report_root)
    stonecore = status["scenarios"][0]
    report_row = stonecore["segment_reports"][0]

    assert status["all_ready"] is False
    assert report_row["missing_evidence"] == ["target_priority", "interrupts"]
    assert "missing_target_priority_evidence" in report_row["invalid_reasons"]
    assert "missing_segment_required_evidence" in stonecore["blockers"]
    assert stonecore["next_commands"] == ["pixi run bot-live-validate --validation-segment-id 08_high_priestess_azil"]


def test_validation_run_status_accepts_scenario_segment_result_for_noncanonical_report(tmp_path):
    live_root = tmp_path / "live_validation_scenarios"
    report_root = tmp_path / "scenario_reports"
    plan = {
        "scenarios": [
            {
                "scenario_id": "blackwing_descent_10n",
                "instance": "Blackwing Descent",
                "difficulty": "normal_10man",
                "segments": [
                    {
                        "segment_id": "08_nefarian",
                        "route_node_id": "bwd_nefarian_current",
                        "kind": "boss",
                        "label": "Nefarian",
                        "mechanic_profile": "nefarian",
                        "executable": True,
                        "live_output_dir": str(live_root / "blackwing_descent_10n" / "08_nefarian"),
                        "live_validate_shell": "pixi run bot-live-validate --validation-segment-id 08_nefarian",
                    }
                ],
            }
        ]
    }
    stale_report = live_root / "blackwing_descent_10n" / "08_nefarian" / "report.json"
    stale_report.parent.mkdir(parents=True)
    stale_report.write_text(
        json.dumps(
            {
                "schema": "bot_live_validation_report_v1",
                "returncode": 0,
                "timed_out": False,
                "validation_context": {
                    "scenario_id": "blackwing_descent_10n",
                    "segment_id": "08_nefarian",
                    "route_node_id": "old_route_node",
                    "route_kind": "boss",
                    "mechanic_profile": "nefarian",
                },
                "failure_reason": "boss_attempt_no_kill",
                "evidence": {"boss_kill_evidence": 0},
            }
        ),
        encoding="utf-8",
    )
    good_report = live_root / "blackwing_descent_10n" / "08_nefarian_final" / "report.json"
    good_report.parent.mkdir(parents=True)
    good_report.write_text("{}", encoding="utf-8")
    report_root.mkdir()
    (report_root / "blackwing_descent_10n.json").write_text(
        json.dumps(
            {
                "scenario_id": "blackwing_descent_10n",
                "clear_complete": True,
                "completion_claim_valid": True,
                "completion_evidence_mode": "uninterrupted_live_clear",
                "complete_segment_coverage": True,
                "route_terminal_evidence": [{"route_node_id": "bwd_nefarian_current", "route_generation": 1}],
                "real_boss_kill_evidence": [{"route_node_id": "bwd_nefarian_current", "route_generation": 1}],
                "segment_results": [
                    {
                        "segment_id": "08_nefarian",
                        "route_node_id": "bwd_nefarian_current",
                        "route_generation": 1,
                        "route_kind": "boss",
                        "mechanic_profile": "nefarian",
                        "real_boss_kill_evidence": True,
                        "terminal_evidence": True,
                        "failure_labels": [],
                        "failure_reason": "",
                        "source_live_report": str(good_report),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = build_validation_run_status(plan, report_root)
    bwd = status["scenarios"][0]
    report_row = bwd["segment_reports"][0]

    assert bwd["present_segments"] == ["08_nefarian"]
    assert bwd["invalid_segments"] == []
    assert report_row["evidence_source"] == "scenario_segment_result"
    assert report_row["report"] == str(good_report)


def test_validation_run_status_rejects_scenario_segment_result_with_route_node_drift(tmp_path):
    live_root = tmp_path / "live_validation_scenarios"
    report_root = tmp_path / "scenario_reports"
    plan = {
        "scenarios": [
            {
                "scenario_id": "blackwing_descent_10n",
                "instance": "Blackwing Descent",
                "difficulty": "normal_10man",
                "scenario_report_shell": "pixi run bot-live-scenario-reports --scenario-id blackwing_descent_10n",
                "segments": [
                    {
                        "segment_id": "02_magmaw",
                        "route_node_id": "current_magmaw_route",
                        "kind": "boss",
                        "label": "Magmaw",
                        "mechanic_profile": "tank_swap_adds_raid_aoe",
                        "required_evidence": ["pulls"],
                        "executable": True,
                        "live_output_dir": str(live_root / "blackwing_descent_10n" / "02_magmaw"),
                        "live_validate_shell": "pixi run bot-live-validate --validation-segment-id 02_magmaw",
                    }
                ],
            }
        ]
    }
    stale_report = live_root / "blackwing_descent_10n" / "02_magmaw" / "report.json"
    stale_report.parent.mkdir(parents=True)
    stale_report.write_text(
        json.dumps(
            {
                "schema": "bot_live_validation_report_v1",
                "returncode": 0,
                "timed_out": False,
                "validation_context": {
                    "scenario_id": "blackwing_descent_10n",
                    "segment_id": "02_magmaw",
                    "route_node_id": "old_magmaw_route",
                    "route_kind": "boss",
                    "mechanic_profile": "tank_swap_adds_raid_aoe",
                },
                "failure_reason": "missing_required_evidence",
            }
        ),
        encoding="utf-8",
    )
    report_root.mkdir()
    (report_root / "blackwing_descent_10n.json").write_text(
        json.dumps(
            {
                "scenario_id": "blackwing_descent_10n",
                "clear_complete": False,
                "complete_segment_coverage": True,
                "segment_results": [
                    {
                        "segment_id": "02_magmaw",
                        "route_node_id": "old_magmaw_route",
                        "route_generation": 1,
                        "route_label": "Magmaw",
                        "route_kind": "boss",
                        "mechanic_profile": "tank_swap_adds_raid_aoe",
                        "real_boss_kill_evidence": True,
                        "terminal_evidence": True,
                        "failure_labels": [],
                        "failure_reason": "",
                        "required_evidence": ["pulls"],
                        "evidence_counts": {"pulls": 1},
                        "source_live_report": str(stale_report),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = build_validation_run_status(plan, report_root)
    bwd = status["scenarios"][0]
    report_row = bwd["segment_reports"][0]

    assert bwd["present_segments"] == []
    assert bwd["invalid_segments"] == ["02_magmaw"]
    assert report_row["evidence_source"] == "segment_report"
    assert report_row["warnings"] == []
    assert "route_node_id_mismatch" in report_row["invalid_reasons"]
    assert bwd["next_commands"][0] == "pixi run bot-live-validate --validation-segment-id 02_magmaw"


def test_validation_run_status_rejects_open_world_kills_as_dungeon_boss_evidence(tmp_path):
    live_root = tmp_path / "live_validation_scenarios"
    report_root = tmp_path / "scenario_reports"
    plan = {
        "scenarios": [
            {
                "scenario_id": "stonecore_5n",
                "instance": "The Stonecore",
                "difficulty": "normal_5man",
                "scenario_report_shell": "pixi run bot-live-scenario-reports --scenario-id stonecore_5n",
                "segments": [
                    {
                        "segment_id": "02_corborus",
                        "route_node_id": "stonecore_corborus",
                        "kind": "boss",
                        "label": "Corborus",
                        "mechanic_profile": "corborus",
                        "executable": True,
                        "live_output_dir": str(live_root / "stonecore_5n" / "02_corborus"),
                        "live_validate_shell": "pixi run bot-live-validate --validation-segment-id 02_corborus",
                    }
                ],
            }
        ]
    }
    report = live_root / "stonecore_5n" / "02_corborus" / "report.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "schema": "bot_live_validation_report_v1",
                "returncode": 0,
                "timed_out": False,
                "validation_context": {
                    "scenario_id": "stonecore_5n",
                    "segment_id": "02_corborus",
                    "route_node_id": "stonecore_corborus",
                    "route_kind": "boss",
                    "mechanic_profile": "corborus",
                },
                "trace": {"entries": [{"action": "mob_killed", "situation": "open_world_combat"}]},
                "summary": {"total_kills": 3},
                "evidence": {"kills": 3, "kill_evidence": 3},
                "stages": [{"stage": "dungeon_boss", "passed": False, "missing": ["stonecore_live_clear_report"]}],
            }
        ),
        encoding="utf-8",
    )
    report_root.mkdir()
    (report_root / "stonecore_5n.json").write_text(
        json.dumps({"scenario_id": "stonecore_5n", "clear_complete": False, "complete_segment_coverage": False}),
        encoding="utf-8",
    )

    status = build_validation_run_status(plan, report_root)
    stonecore = status["scenarios"][0]
    report_row = stonecore["segment_reports"][0]

    assert stonecore["present_segments"] == []
    assert stonecore["existing_segments"] == ["02_corborus"]
    assert stonecore["invalid_segments"] == ["02_corborus"]
    assert report_row["boss_evidence_ready"] is False
    assert "missing_boss_kill_evidence" in report_row["invalid_reasons"]
    assert stonecore["next_commands"][0] == "pixi run bot-live-validate --validation-segment-id 02_corborus"


def test_live_bot_validation_status_snapshot_and_poll_preserve_inactive_state():
    inactive = '{"action":"botauto_status","active":false,"active_bots":0,"target_bots":5}'
    calls: list[str] = []

    def execute(command: str, _timeout: int):
        calls.append(command)
        return inactive, 0, False

    output, status, returncode, timed_out = poll_bot_status(execute, time.monotonic() + 1)

    assert bot_status_snapshot(inactive) == {
        "active": False,
        "active_bots": 0,
        "target_bots": 5,
        "payload": json.loads(inactive),
    }
    assert calls == [".botauto status"]
    assert "$ .botauto status" in output
    assert status and status["active"] is False
    assert returncode == 0
    assert timed_out is False


def test_wait_for_bot_status_state_requires_explicit_zero_bot_inactive_state():
    outputs = iter([
        '{"active":true,"active_bots":1,"target_bots":5}',
        '{"active":false,"active_bots":1,"target_bots":5}',
        '{"active":false,"active_bots":0,"target_bots":5}',
    ])

    def execute(_command, _remaining):
        return next(outputs), 0, False

    output, status = wait_for_bot_status_state(execute, False, time.monotonic() + 2, poll_sec=0, sleep=lambda _value: None)
    assert output.count("$ .botauto status") == 3
    assert status == {"active": False, "active_bots": 0, "target_bots": 5, "payload": {"active": False, "active_bots": 0, "target_bots": 5}}


def test_transport_completion_watchdog_never_sends_server_shutdown(tmp_path):
    commands: list[str] = []
    output = '\n'.join(
        [
            '{"action":"botauto_status","active":true,"active_bots":1,"target_bots":1,"decisions":1}',
            '{"trace_schema_version":1,"entries":[{"action":"mob_killed"}]}',
            '{"duration_minutes":1,"total_kills":1}',
        ]
    )

    def execute(command: str, _timeout: int):
        commands.append(command)
        return output, 0, False

    result, returncode, timed_out, command = run_transport_completion_watchdog(
        execute,
        ["session"],
        2,
        command_script(start=False, stop=True, exit_server=False),
        tmp_path,
        {},
        {},
        heartbeat_sec=1,
        sleep=lambda _seconds: None,
    )

    assert "server shutdown" not in commands
    assert commands.count(".botauto stop") == 1
    assert commands[-1] == ".botauto stop"
    assert command == ["session"]
    assert returncode == 0
    assert timed_out is False
    assert "$ .botauto status" in result


def test_transport_completion_watchdog_stops_manifest_semantic_plateau(tmp_path, monkeypatch):
    commands: list[str] = []
    output = "\n".join(
        [
            '{"action":"botauto_status","active":true,"active_bots":5,"target_bots":5,"decisions":500,"kills":15}',
            '{"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"validation_route_hold_anchor"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}',
            '{"trace_schema_version":1,"entries":[{"action":"validation_route_recovery","result":"no_recovery_mode_succeeded"}]}',
            '{"duration_minutes":8,"total_kills":15}',
        ]
    )
    clock = iter(index * 0.5 for index in range(100))
    monkeypatch.setattr("tools.bot_ml.run_live_bot_validation.time.monotonic", lambda: next(clock))

    def execute(command: str, _timeout: int):
        commands.append(command)
        return output, 0, False

    _result, returncode, timed_out, _command = run_transport_completion_watchdog(
        execute,
        ["session"],
        10,
        command_script(start=False, exit_server=False),
        tmp_path,
        {},
        {"scenario_id": "stonecore_5n"},
        validation_route_manifest={"schema": "bot_live_validation_route_manifest_v1", "route_count": 13},
        heartbeat_sec=1,
        no_progress_window_sec=2,
        sleep=lambda _seconds: None,
    )
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))

    assert returncode == 0
    assert timed_out is False
    assert report["completion_reason"] == "semantic_progress_plateau_watchdog"
    assert report["watchdog_state"]["semantic_progress_plateau"] is True
    assert "semantic_progress_plateau" in report["failure_labels"]
    assert len([command for command in commands if command == ".botauto status"]) == 2


def test_live_bot_validation_command_script_and_output_parser():
    script = command_script(selector="all", trace_limit=20, start=True, stop=True)

    assert script.splitlines() == [
        ".botauto start",
        ".botauto status",
        ".botauto diagnose all",
        ".botauto trace all 20",
        ".botauto combatlog",
        ".botexp summary",
        ".botauto stop",
        "server shutdown force 0",
    ]
    startup, heartbeat, cleanup = heartbeat_commands_from_script(script)
    assert startup == [".botauto start"]
    assert heartbeat == [".botauto status", ".botauto diagnose all", ".botauto trace all 20", ".botexp summary"]
    assert cleanup == [".botauto combatlog", ".botauto stop"]

    output = """
TC> {"active_bots":0,"target_bots":2,"action":"botauto_status","decisions":0,"kills":0,"quests_accepted":0,"quest_objective_progress":0}
TC> {"active_bots":2,"target_bots":2,"action":"botauto_status","decisions":3,"kills":1,"quests_accepted":2,"quest_objective_progress":1}
TC> {"diagnosis_schema_version":"bot_diagnosis_v1","diagnoses":[{"bot_guid":1},{"bot_guid":2}]}
TC> {"trace_schema_version":"bot_trace_v1","entries":[{"action":"move"},{"action":"accept_hub_quests"},{"action":"quest"}]}
TC> {"summary_schema_version":"bot_summary_v1","duration_minutes":1,"quests_completed":0,"raid_boss_kills":0}
$ .botauto diagnose all
There is no such subcommand
"""
    payloads = parse_json_objects(output)
    report = live_validation_report(output, returncode=0, timed_out=False, command=["worldserver"])
    gates = {stage["stage"]: stage for stage in report["stages"]}

    assert len(payloads) == 5
    assert report["active_bots"] == 2
    assert report["target_bots"] == 2
    assert report["diagnosis_count"] == 2
    assert report["trace_entries"] == 3
    assert report["evidence"]["decisions"] == 3
    assert report["evidence"]["active_decision_evidence"] is True
    assert report["evidence"]["hub_acceptance_actions"] == 1
    assert report["evidence"]["teacher_assisted_kills"] == 0
    assert report["evidence"]["kill_evidence"] == 1
    assert report["summary"]["quests_completed"] == 0
    assert report["command_errors"] == [{"command": ".botauto diagnose all", "error": "no_such_subcommand"}]
    assert report["failure_labels"] == ["bot_command_error"]
    assert report["failure_reason"] == "bot_command_error"
    assert gates["movement_smoke"]["passed"] is True
    assert gates["kill_quest"]["passed"] is True
    assert gates["collect_quest"]["passed"] is True
    assert gates["quest_hub_batching"]["passed"] is True
    assert gates["full_stonecore_clear"]["passed"] is False
    assert "stonecore_live_clear_report" in gates["full_stonecore_clear"]["missing"]
    assert report["runtime_ml_control"] == "offline_shadow_only"
    assert report["control_eligible"] is False


def test_live_bot_validation_parallel_combat_calibration_commands_and_report():
    script = command_script(
        selector="all",
        trace_limit=20,
        start=True,
        stop=True,
        combat_calibration=True,
    )
    startup, heartbeat, cleanup = heartbeat_commands_from_script(script)

    assert startup == [".botauto start", ".botauto calibrate start"]
    assert ".botauto calibrate status" in heartbeat
    assert cleanup == [".botauto combatlog", ".botauto calibrate stop", ".botauto stop"]

    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":3}
TC> {"ok":true,"action":"botauto_calibrate_status","active":true,"phase":"single_target","bots":[{"name":"Calibmage","dps":12345.0}]}
"""
    report = live_validation_report(output)

    assert report["active_bots"] == 5
    assert report["combat_calibration"]["active"] is True
    assert report["combat_calibration"]["bots"][0]["dps"] == 12345.0


def test_live_bot_validation_attaches_condition_labeled_wowsims_reference():
    output = """
TC> {"ok":true,"action":"botauto_calibrate_status","active":true,"normalization":{"external_bis_target_configured":false},"best_windows":{"single_target":[{"name":"Calibmage","class_id":8,"dps":25529.7}],"aoe":[]},"bots":[]}
"""
    report = live_validation_report(output)
    calibration = report["combat_calibration"]

    assert calibration["normalization"]["external_bis_target_configured"] is True
    assert calibration["normalization"]["external_reference_mode"] == "informational_only_conditions_mismatched"
    assert calibration["external_reference"]["source"]["name"] == "WoWSims Cataclysm"
    assert calibration["external_reference_comparisons"] == [
        {
            "name": "Calibmage",
            "spec": "fire_mage",
            "live_dps": 25529.7,
            "reference_dps": 51059.39,
            "reference_ratio": 0.5,
            "directly_comparable": False,
        }
    ]


def test_calibration_only_acceptance_uses_capture_integrity_not_dungeon_gates():
    bots = [
        {
            "class_id": class_id,
            "elapsed_seconds": 120,
            "dps": 10000,
            "attempts": 10,
            "persistent_setup": {"ready": True},
        }
        for class_id in (2, 3, 7, 8)
    ]
    report = {
        "returncode": 0,
        "timed_out": False,
        "combat_calibration": {
            "completed_windows": {"single_target": 1, "aoe": 1},
            "best_windows": {"single_target": bots, "aoe": bots},
        },
        "stages": [{"stage": "full_stonecore_clear", "passed": False}],
    }

    apply_calibration_only_acceptance(report)

    assert report["all_passed"] is True
    assert report["acceptable_final_evidence"] is True
    assert report["completion_reason"] == "combat_calibration_complete"
    assert report["stages"] == [{"stage": "combat_calibration", "passed": True, "missing": []}]
    assert report["calibration_acceptance"]["performance_threshold_applied"] is False


def test_live_bot_validation_counts_labeled_teacher_assist_as_kill_quest_evidence():
    output = """
TC> {"active_bots":1,"target_bots":1,"action":"botauto_status","decisions":2,"kills":0,"quests_accepted":1,"quest_objective_progress":1}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"collect_quest_item"},"movement":{"is_moving":false,"distance_moved_since_last_decision":3}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"teacher_kill_assist","situation":"teacher_kill_assist","result":"simple_open_world_quest_mob_target"},{"action":"collect_quest_item","situation":"quest_objective","result":"ok"}]}
TC> {"duration_minutes":1,"decisions":2,"total_kills":0,"quests_completed":0}
"""
    report = live_validation_report(output)
    gates = {stage["stage"]: stage for stage in report["stages"]}

    assert report["evidence"]["kills"] == 0
    assert report["evidence"]["teacher_assisted_kills"] == 1
    assert report["evidence"]["kill_evidence"] == 1
    assert gates["kill_quest"]["passed"] is True


def test_live_bot_validation_route_lookup_rejects_stale_node_id(tmp_path: Path):
    scenario_dir = tmp_path / "validation_scenarios"
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [
            {
                "scenario_id": "blackwing_descent_10n",
                "route_node_id": "current_magmaw_id",
                "step": 2,
                "kind": "boss",
                "label": "Magmaw",
                "mechanic_profile": "tank_swap_adds_raid_aoe",
                "source_entry": 41570,
            },
            {
                "scenario_id": "blackwing_descent_10n",
                "route_node_id": "omnotron_id",
                "step": 3,
                "kind": "boss",
                "label": "Omnotron Defense System",
                "mechanic_profile": "target_switch_interrupt_spread",
                "source_entry": 42186,
            },
        ],
    )
    route = load_validation_route(
        scenario_dir,
        {
            "scenario_id": "blackwing_descent_10n",
            "route_node_id": "stale_magmaw_id",
            "route_step": 2,
            "route_kind": "boss",
            "route_label": "Magmaw",
            "mechanic_profile": "tank_swap_adds_raid_aoe",
        },
    )

    assert route == {}


def test_live_bot_validation_labels_failed_validation_route_boss_attempt():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":35,"kills":0,"quests_accepted":0,"quest_objective_progress":0}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"validation_route_tank_boss"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"action":"validation_route_activation","situation":"validation_route_activation","result":"target_not_found"},{"action":"validation_route_target_search","situation":"validation_route_target_search","result":"activation_applied_no_visible_target"},{"action":"boss_started","situation":"raid_boss","result":"ok"},{"action":"boss_action","situation":"raid_boss","result":"ok"},{"action":"validation_route_tank_boss","situation":"raid_boss","result":"ok"}]},{"bot_guid":2,"entries":[{"action":"validation_route_prerequisite","situation":"validation_route_prerequisite","result":"force_tank_focus"},{"action":"move_to_validation_route_assist_target","situation":"validation_route_prerequisite","result":"ok"},{"action":"validation_route_prerequisite","situation":"validation_route_prerequisite","result":"force_tank_focus"},{"action":"validation_route_prerequisite","situation":"validation_route_prerequisite","result":"force_tank_focus"},{"action":"validation_route_prerequisite","situation":"validation_route_prerequisite","result":"force_tank_focus"}]}]}
TC> {"duration_minutes":1.3,"decisions":35,"total_kills":0,"quests_completed":0,"raid_boss_kills":0}
"""
    report = live_validation_report(output)

    assert report["evidence"]["boss_kill_evidence"] == 0
    assert report["evidence"]["boss_engagement_actions"] == 3
    assert report["evidence"]["validation_route_prerequisite_repeats"] == 4
    assert report["failure_reason"] == "boss_attempt_no_kill"
    assert report["failure_labels"] == [
        "boss_attempt_no_kill",
        "validation_route_prerequisite_loop",
        "no_progress_observed",
    ]


def test_live_bot_validation_preserves_boss_engagement_across_trace_heartbeats():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":55,"kills":3}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"sequence":1,"timestamp_ms":1000,"action":"boss_started","situation":"dungeon_boss","result":"ok","target_id":43438},{"sequence":2,"timestamp_ms":1001,"action":"boss_action","situation":"dungeon_boss","result":"ok","target_id":43438}]}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"sequence":3,"timestamp_ms":2000,"action":"validation_route_regroup","situation":"validation_route_regroup","result":"hold_anchor_no_focus","target_id":0}]}]}
TC> {"duration_minutes":2.0,"decisions":55,"total_kills":3,"quests_completed":0}
"""
    report = live_validation_report(output, validation_context={"route_kind": "boss"})

    assert report["trace_entries"] == 3
    assert report["evidence"]["boss_engagement_actions"] == 2
    assert report["evidence"]["kill_evidence"] == 3


def test_live_bot_validation_counts_assist_target_movement_as_tank_positioning():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":20}
TC> {"trace_schema_version":1,"entries":[{"action":"move_to_validation_route_assist_target","result":"assist_tank_focus"},{"action":"validation_route_regroup","result":"follow_last_known_tank_focus"}]}
TC> {"duration_minutes":1.0,"decisions":20}
"""
    report = live_validation_report(output, validation_context={"route_kind": "boss"})

    assert report["evidence"]["tank_positioning_evidence"] == 2
    assert report["evidence"]["validation_evidence_ready"]["tank_positioning"] is True


def test_live_bot_validation_counts_route_priority_and_healer_assignment_evidence():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":25}
TC> {"trace_schema_version":1,"entries":[{"action":"validation_target_priority","result":"assist_tank_focus"}]}
TC> {"duration_minutes":1.0,"decisions":25}
"""
    report = live_validation_report(output, validation_context={"route_kind": "boss"})

    assert report["evidence"]["target_priority_evidence"] == 1
    assert report["evidence"]["healer_assignment_evidence"] == 1
    assert report["evidence"]["validation_evidence_ready"]["target_priority"] is True
    assert report["evidence"]["validation_evidence_ready"]["healer_assignments"] is True


def test_live_bot_validation_counts_trash_route_action_as_progress_not_boss_failure():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":12,"kills":0,"quests_accepted":0,"quest_objective_progress":0}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"validation_route_trash_action"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"action":"validation_route_target_search","situation":"validation_route","result":"approach_target"},{"action":"trash_action","situation":"normal_dungeon_trash","result":"ok"},{"action":"validation_route_trash_action","situation":"normal_dungeon_trash","result":"ok"}]}]}
TC> {"duration_minutes":1.0,"decisions":12,"total_kills":0,"quests_completed":0}
"""
    report = live_validation_report(output)

    assert report["evidence"]["trash_action_evidence"] == 2
    assert report["evidence"]["trash_pulls"] == 2
    assert report["evidence"]["trash_route_actions"] == 2
    assert "boss_attempt_no_kill" not in report["failure_labels"]
    assert "no_progress_observed" not in report["failure_labels"]
    assert report["failure_labels"] == []


def test_live_bot_validation_keeps_route_progress_diagnosis_error_nonterminal():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":20,"kills":0,"quests_accepted":0,"quest_objective_progress":0}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"diagnosis":{"diagnosis_code":"blocked_no_fallback","severity":"error"},"snapshot":{"decision":{"action":"validation_route_prerequisite_assist"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"action":"validation_route_prerequisite","situation":"validation_route_prerequisite","result":"force_tank_focus"},{"action":"trash_action","situation":"normal_dungeon_trash","result":"ok"},{"action":"validation_route_trash_action","situation":"normal_dungeon_trash","result":"ok"}]}]}
TC> {"duration_minutes":1.0,"decisions":20,"total_kills":0,"quests_completed":0}
"""
    report = live_validation_report(output)

    assert report["evidence"]["error_diagnoses"] == 1
    assert report["evidence"]["trash_pulls"] == 2
    assert "bot_diagnosis_error" not in report["failure_labels"]
    assert report["completion_reason"] == "no_progress_observed"


def test_live_bot_validation_counts_trace_mob_killed_as_kill_evidence():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":12,"kills":0,"quests_accepted":0,"quest_objective_progress":0}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"validation_route_trash_action"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"action":"trash_action","situation":"normal_dungeon_trash","result":"ok"},{"action":"mob_killed","situation":"normal_dungeon_trash","result":"validation_route_recovery"}]}]}
TC> {"duration_minutes":1.0,"decisions":12,"total_kills":0,"quests_completed":0}
"""
    report = live_validation_report(output)
    gates = {stage["stage"]: stage for stage in report["stages"]}

    assert report["evidence"]["kills"] == 1
    assert report["evidence"]["kill_evidence"] == 1
    assert gates["kill_quest"]["passed"] is True


def test_live_bot_validation_counts_route_mob_killed_as_trash_engagement():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":84,"kills":0,"quests_accepted":0,"quest_objective_progress":0}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"validation_route_prerequisite_assist"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"action":"validation_route_prerequisite","situation":"validation_route_prerequisite","result":"force_tank_focus"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"force_tank_focus_no_health_progress"},{"action":"mob_killed","situation":"mob_killed","result":"validation_route_recovery"},{"action":"validation_route_prerequisite_assist","situation":"validation_route_prerequisite","result":"ok"},{"action":"validation_route_prerequisite","situation":"validation_route_prerequisite","result":"force_tank_focus"},{"action":"move_to_validation_route_assist_target","situation":"validation_route_prerequisite","result":"ok"}]}]}
TC> {"duration_minutes":3.4,"decisions":84,"total_kills":0,"quests_completed":0}
"""
    report = live_validation_report(output)

    assert report["evidence"]["kills"] == 1
    assert report["evidence"]["trash_pulls"] == 1
    assert report["evidence"]["validation_evidence_ready"]["pulls"] is True
    assert "validation_route_no_engagement" not in report["failure_labels"]
    assert "validation_route_prerequisite_loop" not in report["failure_labels"]
    assert "validation_route_assist_focus_loop" not in report["failure_labels"]


def test_live_bot_validation_counts_route_summary_kills_as_trash_engagement_when_trace_rolls_off():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":143,"kills":4,"quests_accepted":0,"quest_objective_progress":0}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"move_to_validation_route_anchor"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"action":"validation_route_regroup","situation":"validation_route_regroup","result":"follow_anchor_no_focus"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_safe_memory"},{"action":"move_to_validation_route_anchor","situation":"validation_route_regroup","result":"ok"}]}]}
TC> {"duration_minutes":6.0,"decisions":143,"total_kills":4,"quests_completed":0}
"""
    report = live_validation_report(output, validation_context={"route_kind": "trash"})

    assert report["evidence"]["kills"] == 4
    assert report["evidence"]["trash_pulls"] == 4
    assert report["evidence"]["validation_evidence_ready"]["pulls"] is True
    assert "validation_route_no_engagement" not in report["failure_labels"]
    assert "no_progress_observed" not in report["failure_labels"]


def test_live_bot_validation_labels_stuck_heavy_trash_route_as_failure():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":30,"kills":0,"quests_accepted":0,"quest_objective_progress":0,"stuck":12}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"validation_route_trash_action"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"action":"trash_action","situation":"normal_dungeon_trash","result":"ok"},{"action":"validation_route_trash_action","situation":"normal_dungeon_trash","result":"ok"},{"action":"stuck_detected","situation":"stuck_detected","result":"repath"},{"action":"unstuck","situation":"stuck_recovery","result":"failed"},{"action":"stuck_detected","situation":"stuck_detected","result":"repath"},{"action":"unstuck","situation":"stuck_recovery","result":"failed"},{"action":"stuck_detected","situation":"stuck_detected","result":"repath"},{"action":"unstuck","situation":"stuck_recovery","result":"failed"}]}]}
TC> {"duration_minutes":5.0,"decisions":30,"total_kills":0,"quests_completed":0,"stuck_events":12}
"""
    report = live_validation_report(output)

    assert report["evidence"]["trash_action_evidence"] == 2
    assert report["evidence"]["stuck_events"] >= 12
    assert report["evidence"]["unstuck_failures"] == 3
    assert "validation_route_stuck_loop" in report["failure_labels"]


def test_live_bot_validation_rejects_recovery_without_post_failure_progress():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":40,"kills":1,"quests_accepted":0,"quest_objective_progress":0,"stuck":13}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"move_to_validation_route_assist_target"},"movement":{"is_moving":false,"distance_moved_since_last_decision":33.9},"recovery":{"last_recovery_mode":"validation_route_stuck_repath","last_recovery_result":"repath_issued"}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"sequence":1,"timestamp_ms":1000,"action":"trash_action","situation":"normal_dungeon_trash","result":"ok"},{"sequence":2,"timestamp_ms":1001,"action":"validation_route_trash_action","situation":"normal_dungeon_trash","result":"ok"},{"sequence":3,"timestamp_ms":1002,"action":"mob_killed","situation":"normal_dungeon_trash","result":"ok"},{"sequence":4,"timestamp_ms":1003,"action":"stuck_detected","situation":"stuck_detected","result":"validation_route_stuck_safe_memory"},{"sequence":5,"timestamp_ms":1004,"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_safe_memory"},{"sequence":6,"timestamp_ms":1005,"action":"guardrail_repath","situation":"runtime_recovery","result":"repath"},{"sequence":7,"timestamp_ms":1006,"action":"guardrail_repath","situation":"runtime_recovery","result":"repath"},{"sequence":8,"timestamp_ms":1007,"action":"guardrail_repath","situation":"runtime_recovery","result":"repath"},{"sequence":9,"timestamp_ms":1008,"action":"guardrail_repath","situation":"runtime_recovery","result":"repath"},{"sequence":10,"timestamp_ms":1009,"action":"guardrail_repath","situation":"runtime_recovery","result":"repath"},{"sequence":11,"timestamp_ms":1010,"action":"guardrail_repath","situation":"runtime_recovery","result":"repath"},{"sequence":12,"timestamp_ms":1011,"action":"guardrail_repath","situation":"runtime_recovery","result":"repath"},{"sequence":13,"timestamp_ms":1012,"action":"guardrail_repath","situation":"runtime_recovery","result":"repath"},{"sequence":14,"timestamp_ms":1013,"action":"trash_action","situation":"normal_dungeon_trash","result":"ok"},{"sequence":15,"timestamp_ms":1014,"action":"validation_route_trash_action","situation":"normal_dungeon_trash","result":"ok"},{"sequence":16,"timestamp_ms":1015,"action":"validation_route_complete","situation":"normal_dungeon_trash","result":"ok"}]}]}
TC> {"duration_minutes":5.0,"decisions":40,"total_kills":1,"quests_completed":0,"stuck_events":13}
"""
    report = live_validation_report(output)

    assert report["evidence"]["kill_evidence"] == 1
    assert report["evidence"]["unresolved_route_stuck_events"] >= 8
    assert report["evidence"]["unstuck_failures"] == 0
    assert report["evidence"]["validation_route_actions"] > 0
    assert report["evidence"]["post_failure_progress"] is False
    assert "validation_route_stuck_loop" in report["failure_labels"]


def test_live_bot_validation_rejects_movement_without_ordered_post_failure_progress():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":480,"kills":4,"quests_accepted":0,"quest_objective_progress":0,"stuck":8}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"diagnosis":{"route_progress":{"no_progress":{"count":0,"reason":"route_target_path_no_progress","threshold":2},"route":{"kind":"boss"},"target":{"entry":43438,"guid":434,"hp_pct":1,"best_hp_pct":1}}},"snapshot":{"decision":{"action":"move_to_validation_route_assist_target"},"movement":{"is_moving":true,"distance_moved_since_last_decision":20.8}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"action":"trash_action","situation":"normal_dungeon_trash","result":"ok"},{"action":"validation_route_trash_action","situation":"normal_dungeon_trash","result":"ok"},{"action":"stuck_detected","situation":"stuck_detected","result":"repath"},{"action":"validation_route_target_search","situation":"dungeon_boss","result":"assist_tank_focus"},{"action":"move_to_validation_route_assist_target","situation":"dungeon_boss","result":"ok"}]}]}
TC> {"duration_minutes":3.0,"decisions":480,"total_kills":4,"quests_completed":0,"stuck_events":8}
"""
    report = live_validation_report(output)

    assert report["evidence"]["stuck_events"] >= 8
    assert report["evidence"]["moved_diagnoses"] == 1
    assert report["evidence"]["validation_route_actions"] > 0
    assert report["evidence"]["validation_route_no_progress_diagnoses"] == 0
    assert report["evidence"]["post_failure_progress"] is False
    assert "validation_route_stuck_loop" in report["failure_labels"]


def test_live_bot_validation_rejects_unordered_combat_as_post_failure_progress():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":640,"kills":6,"quests_accepted":0,"quest_objective_progress":0,"stuck":8}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"diagnosis":{"diagnosis_code":"normal_combat","route_progress":{"no_progress":{"count":0,"reason":"route_target_combat_progress","threshold":20},"route":{"kind":"trash"},"target":{"entry":42810,"guid":106,"hp_pct":0.42,"best_hp_pct":0.42}}},"snapshot":{"decision":{"action":"validation_route_trash_action"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"action":"stuck_detected","situation":"stuck_detected","result":"validation_route_stuck_no_fallback"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_no_fallback"},{"action":"trash_action","situation":"validation_route","result":"ok"},{"action":"validation_route_trash_action","situation":"validation_route","result":"ok"},{"action":"mob_killed","situation":"normal_dungeon_trash","result":"stale_target_seen_dead"}]}]}
TC> {"duration_minutes":4.0,"decisions":640,"total_kills":6,"quests_completed":0,"stuck_events":8}
"""
    report = live_validation_report(output, validation_context={"route_kind": "trash"})

    assert report["evidence"]["stuck_events"] >= 8
    assert report["evidence"]["kill_evidence"] == 6
    assert report["evidence"]["validation_route_no_progress_diagnoses"] == 0
    assert report["evidence"]["diagnosis_codes"]["normal_combat"] == 1
    assert report["evidence"]["post_failure_progress"] is False
    assert "validation_route_stuck_loop" in report["failure_labels"]


def test_live_bot_validation_rejects_diagnosis_only_progress_after_repath_loop():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":1109,"kills":9,"quests_accepted":0,"quest_objective_progress":0,"stuck":20}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"diagnosis":{"diagnosis_code":"normal_combat","route_progress":{"no_progress":{"count":0,"reason":"route_target_combat_progress","threshold":20},"route":{"kind":"trash","node_id":"1a5e5160e80934e5"},"target":{"entry":42692,"guid":133,"hp_pct":0.546085,"best_hp_pct":0.546085}}},"snapshot":{"decision":{"action":"validation_route_trash_action"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"action":"stuck_detected","situation":"stuck_detected","result":"validation_route_stuck_no_fallback"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_no_fallback"},{"action":"stuck_detected","situation":"stuck_detected","result":"validation_route_stuck_no_fallback"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_no_fallback"},{"action":"stuck_detected","situation":"stuck_detected","result":"validation_route_stuck_no_fallback"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_no_fallback"},{"action":"stuck_detected","situation":"stuck_detected","result":"validation_route_stuck_no_fallback"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_no_fallback"},{"action":"stuck_detected","situation":"stuck_detected","result":"validation_route_stuck_no_fallback"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_no_fallback"},{"action":"stuck_detected","situation":"stuck_detected","result":"validation_route_stuck_no_fallback"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_no_fallback"},{"action":"stuck_detected","situation":"stuck_detected","result":"validation_route_stuck_no_fallback"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_no_fallback"},{"action":"stuck_detected","situation":"stuck_detected","result":"validation_route_stuck_no_fallback"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_no_fallback"},{"action":"trash_action","situation":"validation_route","result":"ok"},{"action":"validation_route_trash_action","situation":"validation_route","result":"ok"}]}]}
TC> {"duration_minutes":7.0,"decisions":1109,"total_kills":9,"quests_completed":0,"stuck_events":20}
"""
    report = live_validation_report(output, validation_context={"route_kind": "trash"})

    assert report["evidence"]["unresolved_route_stuck_events"] >= 8
    assert report["evidence"]["validation_route_combat_progress_diagnoses"] == 0
    assert report["evidence"]["validation_route_no_progress_diagnoses"] == 0
    assert report["evidence"]["post_failure_progress"] is False
    assert "validation_route_stuck_loop" in report["failure_labels"]


def test_live_bot_validation_rejects_unordered_trace_progress_after_stuck_loop():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":1422,"kills":19,"quests_accepted":0,"quest_objective_progress":0,"stuck":25}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"diagnosis":{"diagnosis_code":"waiting_decision_tick"},"snapshot":{"decision":{"action":"validation_route_hold_anchor"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"action":"stuck_detected","situation":"stuck_detected","result":"validation_route_stuck_no_fallback"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_no_fallback"},{"action":"stuck_detected","situation":"stuck_detected","result":"validation_route_stuck_no_fallback"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_no_fallback"},{"action":"stuck_detected","situation":"stuck_detected","result":"validation_route_stuck_no_fallback"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_no_fallback"},{"action":"stuck_detected","situation":"stuck_detected","result":"validation_route_stuck_no_fallback"},{"action":"validation_route_recovery","situation":"validation_route_recovery","result":"validation_route_stuck_no_fallback"},{"action":"trash_action","situation":"validation_route","result":"ok","route_progress":{"route":{"node_id":"1a5e5160e80934e5","kind":"trash"},"target":{"guid":144,"entry":42428,"hp_pct":0.66,"best_hp_pct":0.66},"no_progress":{"count":0,"threshold":20,"reason":"route_target_combat_progress"}}},{"action":"validation_route_trash_action","situation":"validation_route","result":"ok","route_progress":{"route":{"node_id":"1a5e5160e80934e5","kind":"trash"},"target":{"guid":144,"entry":42428,"hp_pct":0.66,"best_hp_pct":0.66},"no_progress":{"count":0,"threshold":20,"reason":"route_target_combat_progress"}}},{"action":"mob_killed","situation":"normal_dungeon_trash","result":"stale_target_seen_dead"},{"action":"validation_route_target_search","situation":"validation_route_target_search","result":"trash_route_target_killed_cluster_still_alive"},{"action":"validation_route_regroup","situation":"validation_route_regroup","result":"hold_anchor_no_focus"},{"action":"validation_route_hold_anchor","situation":"validation_route_regroup","result":"hold_anchor_no_focus"}]}]}
TC> {"duration_minutes":7.0,"decisions":1422,"total_kills":19,"quests_completed":0,"stuck_events":15}
"""
    report = live_validation_report(output, validation_context={"route_kind": "trash"})

    assert report["evidence"]["validation_route_combat_progress_diagnoses"] == 0
    assert report["evidence"]["validation_route_no_progress_diagnoses"] == 0
    assert report["evidence"]["kill_evidence"] == 19
    assert report["evidence"]["trash_route_actions"] > 0
    assert report["evidence"]["post_failure_progress"] is False
    assert "validation_route_stuck_loop" in report["failure_labels"]


def test_live_bot_validation_labels_bot_not_loaded_diagnosis_as_lifecycle_failure():
    output = """
TC> {"active_bots":2,"target_bots":2,"action":"botauto_status","decisions":20,"kills":0,"quests_accepted":0,"quest_objective_progress":0}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1,"bot_name":""},"diagnosis":{"diagnosis_code":"bot_not_loaded","severity":"error"},"snapshot":{"decision":{"action":"validation_route_trash_action"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}},{"identity":{"bot_guid":2,"bot_name":""},"diagnosis":{"diagnosis_code":"bot_not_loaded","severity":"error"},"snapshot":{"decision":{"action":"validation_route_trash_action"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"action":"trash_action","situation":"normal_dungeon_trash","result":"ok"},{"action":"validation_route_trash_action","situation":"normal_dungeon_trash","result":"ok"}]}]}
TC> {"duration_minutes":5.0,"decisions":20,"total_kills":0,"quests_completed":0}
"""
    report = live_validation_report(output)

    assert report["evidence"]["diagnosis_codes"] == {"bot_not_loaded": 2}
    assert report["evidence"]["bot_not_loaded_diagnoses"] == 2
    assert "bot_lifecycle_not_loaded" in report["failure_labels"]


def test_live_bot_validation_labels_route_search_without_trash_engagement():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":12,"kills":0,"quests_accepted":0,"quest_objective_progress":0}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"search_validation_route_target"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"action":"validation_route_target_search","situation":"validation_route","result":"target_not_found"}]}]}
TC> {"duration_minutes":1.0,"decisions":12,"total_kills":0,"quests_completed":0}
"""
    report = live_validation_report(output)

    assert report["evidence"]["trash_action_evidence"] == 0
    assert report["evidence"]["trash_route_actions"] == 0
    assert report["failure_reason"] == "validation_route_no_engagement"
    assert "no_progress_observed" in report["failure_labels"]


def test_live_bot_validation_counts_group_mechanic_evidence():
    output = """
TC> {"active_bots":10,"target_bots":10,"action":"botauto_status","decisions":40}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"validation_role_assignment"},"movement":{"is_moving":true,"distance_moved_since_last_decision":2}}},{"identity":{"bot_guid":2},"snapshot":{"decision":{"action":"validation_route_tank_boss","result":"force_tank_focus"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"raid_formed"},{"action":"boss_started"},{"action":"target_switch"},{"action":"assigned_interrupt_success"},{"action":"validation_route_group_heal"},{"action":"validation_route_regroup"},{"action":"validation_route_recovery"}]}
TC> {"duration_minutes":5,"decisions":40,"raid_boss_kills":1,"interrupt_success":1}
"""
    report = live_validation_report(output)
    evidence = report["evidence"]

    assert evidence["validation_evidence_counts"]["raid_formation"] == 1
    assert evidence["validation_evidence_counts"]["role_assignments"] == 1
    assert evidence["validation_evidence_counts"]["pulls"] >= 1
    assert evidence["validation_evidence_counts"]["target_priority"] == 1
    assert evidence["validation_evidence_counts"]["interrupts"] == 1
    assert evidence["validation_evidence_counts"]["healer_assignments"] == 1
    assert evidence["validation_evidence_counts"]["tank_positioning"] >= 1
    assert evidence["validation_evidence_counts"]["regrouping"] == 1
    assert evidence["validation_evidence_counts"]["instance_reset"] == 0


def test_live_bot_validation_counts_summary_only_raid_evidence_after_trace_rolloff():
    output = """
TC> {"active_bots":10,"target_bots":10,"action":"botauto_status","decisions":420}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"validation_route_complete"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"validation_route_complete","situation":"validation_route_manifest","result":"all_routes_complete"}]}
TC> {"duration_minutes":12,"decisions":420,"raid_boss_kills":6,"role_assignments":10,"group_formations":10,"raid_formations":10,"target_priority_decisions":18,"interrupt_success":3,"assigned_interrupt_success":3,"healer_assignments":11,"tank_positioning":20,"regroups":14,"recovery_events":1,"instance_resets":1}
"""
    report = live_validation_report(output)
    counts = report["evidence"]["validation_evidence_counts"]

    assert counts["raid_formation"] == 10
    assert counts["role_assignments"] == 10
    assert counts["target_priority"] == 18
    assert counts["interrupts"] == 3
    assert counts["healer_assignments"] == 11
    assert counts["tank_positioning"] == 20
    assert counts["regrouping"] == 14
    assert counts["recovery"] == 1
    assert counts["instance_reset"] == 1


def test_live_bot_validation_counts_route_complete_as_regrouping_evidence():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":66,"kills":1}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"validation_route_complete"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"boss_started","situation":"dungeon_boss","result":"ok"},{"action":"boss_killed","situation":"boss_killed","result":"ok","target_id":43438,"route_node_id":"stonecore_corborus","route_generation":1},{"action":"validation_route_terminal","situation":"validation_route_manifest","result":"boss_killed","route_node_id":"stonecore_corborus","route_generation":1},{"action":"validation_route_complete","situation":"validation_route_manifest","result":"boss_killed"}]}
TC> {"duration_minutes":0.5,"decisions":66,"total_kills":1,"target_priority_decisions":1,"healer_assignments":1,"tank_positioning":1}
"""
    report = live_validation_report(output, validation_context={"route_kind": "boss", "route_node_id": "stonecore_corborus", "route_generation": 1})
    counts = report["evidence"]["validation_evidence_counts"]

    assert report["evidence"]["boss_kill_evidence"] == 1
    assert counts["regrouping"] == 1


def test_live_bot_validation_rejects_boss_killed_diagnosis_as_real_boss_evidence():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":69,"kills":1}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"diagnosis":{"diagnosis_code":"validation_route_terminal","blocker":"boss_killed"},"snapshot":{"decision":{"action":"validation_route_complete"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"boss_started","situation":"dungeon_boss","result":"ok"},{"action":"boss_action","situation":"dungeon_boss","result":"ok"},{"action":"validation_route_complete","situation":"validation_route_manifest","result":"ok"}]}
TC> {"duration_minutes":0.5,"decisions":69,"total_kills":1,"target_priority_decisions":1,"healer_assignments":1,"tank_positioning":1}
"""
    report = live_validation_report(output, validation_context={"route_kind": "boss"})

    assert report["evidence"]["boss_kill_evidence"] == 0
    assert report["progress_counters"]["boss_kill_evidence"] == 0


def test_live_bot_validation_accepts_confirmed_unit_death_as_scoped_boss_evidence():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":120,"kills":4}
TC> {"trace_schema_version":1,"entries":[{"action":"boss_killed","result":"confirmed_unit_death","target_id":392,"route_node_id":"azil","route_generation":2},{"action":"validation_route_terminal","result":"boss_killed","target_id":392,"route_node_id":"azil","route_generation":2},{"action":"validation_route_manifest_complete","result":"boss_killed","route_node_id":"azil","route_generation":2}]}
TC> {"duration_minutes":9.0,"decisions":120,"total_kills":4}
"""
    manifest = {
        "advance_mode": "terminal",
        "routes": [
            {"route_node_id": "corborus", "route_generation": 1, "kind": "boss"},
            {"route_node_id": "azil", "route_generation": 2, "kind": "boss"},
        ],
    }

    report = live_validation_report(
        output,
        validation_context={"scenario_id": "stonecore_5n"},
        validation_route_manifest=manifest,
    )

    assert report["evidence"]["boss_kill_evidence"] == 1
    assert report["evidence"]["manifest_completion_evidence"] == [
        {"route_node_id": "azil", "route_generation": 2}
    ]
    assert "missing_node_terminal_evidence" in report["final_evidence_rejections"]
    assert "missing_real_boss_kill_evidence" in report["final_evidence_rejections"]


def test_live_bot_validation_rejects_unmatched_manifest_completion_scope():
    evidence = {
        "route_terminal_evidence": [],
        "real_boss_kill_evidence": [],
        "manifest_completion_evidence": [{"route_node_id": "wrong", "route_generation": 2}],
    }
    manifest = {
        "advance_mode": "terminal",
        "routes": [{"route_node_id": "azil", "route_generation": 2, "kind": "boss"}],
    }

    strict = strict_manifest_evidence(evidence, manifest)

    assert strict["missing_terminal_route_nodes"] == ["azil"]
    assert strict["missing_boss_route_nodes"] == ["azil"]


def test_live_bot_validation_rejects_raw_manifest_complete_without_scoped_evidence():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":120,"kills":10}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"validation_route_complete"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"boss_started","situation":"dungeon_boss","result":"ok"},{"action":"boss_killed","situation":"boss_killed","result":"ok"},{"action":"validation_route_complete","situation":"validation_route_manifest","result":"all_routes_complete"}]}
TC> {"trace_schema_version":1,"bots":[{"bot_guid":1,"entries":[{"action":"validation_route_manifest_complete","situation":"validation_route_manifest_complete","result":"boss_killed"}]}]$ .botexp summary
TC> {"duration_minutes":9.0,"decisions":120,"total_kills":10,"quests_completed":0}
"""
    report = live_validation_report(output, validation_context={"scenario_id": "stonecore_5n"})

    assert report["evidence"]["validation_route_manifest_complete"] == 1
    assert report["completion_reason"] == "validation_route_manifest_complete"
    assert report["acceptable_final_evidence"] is False
    assert "missing_validation_route_manifest" in report["final_evidence_rejections"]


def test_live_bot_validation_uses_scenario_reports_for_dungeon_and_raid_gates(tmp_path):
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":4,"kills":0,"quests_accepted":0,"quest_objective_progress":0}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"dungeon_boss"},"movement":{"is_moving":true,"distance_moved_since_last_decision":8}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"boss_killed","situation":"dungeon_boss"},{"action":"raid_boss_killed","situation":"raid_boss"}]}
TC> {"duration_minutes":3,"decisions":4,"total_kills":0,"quests_completed":0}
"""
    scenario_dir = tmp_path / "scenario_reports"
    scenario_dir.mkdir()
    (scenario_dir / "stonecore_5n.json").write_text(
        json.dumps(
            {
                "scenario_id": "stonecore_5n",
                "prepared_group": True,
                "trash_pulls": 4,
                "boss_kills": 4,
                "clear_complete": True,
                "completion_claim_valid": True,
                "completion_evidence_mode": "uninterrupted_live_clear",
            }
        ),
        encoding="utf-8",
    )
    (scenario_dir / "blackwing_descent_10n.json").write_text(
        json.dumps({"scenario_id": "blackwing_descent_10n", "prepared_group": True, "trash_pulls": 2, "raid_boss_kills": 1, "clear_complete": False}),
        encoding="utf-8",
    )
    (scenario_dir / "manifest.json").write_text(json.dumps({"schema": "not_a_scenario_report"}), encoding="utf-8")

    report = live_validation_report(output, scenario_reports=load_scenario_reports(scenario_dir))
    gates = {stage["stage"]: stage for stage in report["stages"]}

    assert gates["normal_dungeon_trash"]["passed"] is True
    assert gates["dungeon_boss"]["passed"] is True
    assert gates["full_stonecore_clear"]["passed"] is True
    assert gates["raid_trash"]["passed"] is True
    assert gates["raid_boss"]["passed"] is True
    assert gates["full_blackwing_descent_clear"]["passed"] is False
    assert gates["full_blackwing_descent_clear"]["missing"] == ["blackwing_descent_full_clear_evidence"]
    assert sorted(report["scenario_reports"]) == ["blackwing_descent_10n", "stonecore_5n"]


def test_live_scenario_report_builder_rejects_unscoped_cross_scenario_kills(tmp_path):
    scenario_dir = tmp_path / "validation_scenarios"
    write_jsonl(
        scenario_dir / "validation_scenarios.jsonl",
        [
            {"scenario_id": "stonecore_5n", "instance": "The Stonecore", "map_id": 725, "difficulty": "normal_5man", "provisioning_ready": True, "boss_count": 4},
            {"scenario_id": "blackwing_descent_10n", "instance": "Blackwing Descent", "map_id": 669, "difficulty": "normal_10man", "provisioning_ready": True, "boss_count": 6},
        ],
    )
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [
            {"scenario_id": "stonecore_5n", "kind": "boss"},
            {"scenario_id": "stonecore_5n", "kind": "boss"},
            {"scenario_id": "stonecore_5n", "kind": "boss"},
            {"scenario_id": "stonecore_5n", "kind": "boss"},
            {"scenario_id": "blackwing_descent_10n", "kind": "boss"},
        ],
    )
    live_report = {
        "trace_entries": 4,
        "trace": {"entries": [{"action": "boss_killed"}, {"action": "boss_killed"}, {"action": "boss_killed"}, {"action": "boss_killed"}, {"action": "raid_boss_killed"}]},
        "summary": {"raid_boss_kills": 1},
        "evidence": {"failures": 0},
        "stages": [
            {"stage": "normal_dungeon_trash", "passed": True},
            {"stage": "dungeon_boss", "passed": True},
            {"stage": "full_stonecore_clear", "passed": True},
            {"stage": "raid_boss", "passed": True},
        ],
    }

    reports = build_live_scenario_reports(live_report, scenario_dir)

    assert reports["stonecore_5n"]["prepared_group"] is True
    assert reports["stonecore_5n"]["boss_kills"] == 0
    assert reports["stonecore_5n"]["clear_complete"] is False
    assert reports["stonecore_5n"]["scenario_evidence_mode"] == "generic_live_trace_inference"
    assert reports["stonecore_5n"]["teacher_label_quality"] == "weak"
    assert reports["stonecore_5n"]["ml_training_label"] == "weak_inferred_label"
    assert reports["blackwing_descent_10n"]["raid_boss_kills"] == 0
    assert reports["blackwing_descent_10n"]["boss_stage_passed"] is True
    assert reports["blackwing_descent_10n"]["clear_complete"] is False


def test_live_scenario_report_builder_labels_attached_scenario_reports_medium_quality(tmp_path):
    scenario_dir = tmp_path / "validation_scenarios"
    write_jsonl(
        scenario_dir / "validation_scenarios.jsonl",
        [{"scenario_id": "stonecore_5n", "instance": "The Stonecore", "map_id": 725, "difficulty": "normal_5man", "provisioning_ready": True, "boss_count": 4}],
    )
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [
            {"scenario_id": "stonecore_5n", "kind": "boss", "step": index, "label": f"Boss {index}", "route_node_id": f"stonecore_boss_{index}"}
            for index in range(1, 5)
        ],
    )
    live_report = {
        "trace_entries": 2,
        "trace": {"entries": [{"action": "boss_killed", "situation": "dungeon_boss"}]},
        "scenario_reports": {
            "stonecore_5n": {
                "scenario_id": "stonecore_5n",
                "prepared_group": True,
                "trash_pulls": 4,
                "boss_kills": 4,
                "clear_complete": True,
                "completion_claim_valid": True,
                "completion_evidence_mode": "uninterrupted_live_clear",
                "expected_segments": [f"{index:02d}_boss_{index}" for index in range(1, 5)],
                "route_terminal_evidence": [{"route_node_id": f"stonecore_boss_{index}", "route_generation": index} for index in range(1, 5)],
                "real_boss_kill_evidence": [{"route_node_id": f"stonecore_boss_{index}", "route_generation": index} for index in range(1, 5)],
                "segment_results": [
                    {
                        "route_node_id": f"stonecore_boss_{index}",
                        "route_generation": index,
                        "terminal_evidence": True,
                        "real_boss_kill_evidence": True,
                        "evidence_counts": {},
                    }
                    for index in range(1, 5)
                ],
                "forbidden_completion_assists": [],
            }
        },
    }

    reports = build_live_scenario_reports(live_report, scenario_dir)
    stonecore = reports["stonecore_5n"]

    assert stonecore["clear_complete"] is True
    assert stonecore["completion_evidence_mode"] == "attached_uninterrupted_live_clear"
    assert stonecore["source_scenario_report_attached"] is True
    assert stonecore["scenario_evidence_mode"] == "attached_scenario_report"
    assert stonecore["scenario_evidence_modes"] == ["attached_scenario_report"]
    assert stonecore["teacher_label_quality"] == "medium"
    assert stonecore["ml_training_label"] == "candidate_teacher_label"


def test_live_scenario_report_builder_propagates_failed_teacher_labels(tmp_path):
    scenario_dir = tmp_path / "validation_scenarios"
    write_jsonl(
        scenario_dir / "validation_scenarios.jsonl",
        [{"scenario_id": "blackwing_descent_10n", "instance": "Blackwing Descent", "map_id": 669, "difficulty": "normal_10man", "provisioning_ready": True, "boss_count": 6}],
    )
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [{"scenario_id": "blackwing_descent_10n", "kind": "boss", "step": 8, "label": "Nefarian", "route_node_id": "bwd_nefarian"}],
    )
    live_report = {
        "source_live_report": "nefarian_failed.json",
        "validation_context": {
            "scenario_id": "blackwing_descent_10n",
            "segment_id": "08_nefarian",
            "route_node_id": "bwd_nefarian",
            "route_label": "Nefarian",
            "route_kind": "boss",
            "route_step": 8,
            "mechanic_profile": "tank_swap_adds_raid_aoe",
        },
        "trace_entries": 8,
        "trace": {"entries": [{"action": "boss_started"}, {"action": "boss_action"}, {"action": "validation_route_tank_boss"}]},
        "summary": {"raid_boss_kills": 0},
        "evidence": {"failures": 0},
        "failure_labels": ["boss_attempt_no_kill", "no_progress_observed"],
        "failure_reason": "boss_attempt_no_kill",
        "stages": [{"stage": "raid_boss", "passed": False}],
    }

    bwd = build_live_scenario_reports(live_report, scenario_dir)["blackwing_descent_10n"]

    assert bwd["boss_stage_passed"] is False
    assert bwd["failure_labels"] == ["boss_attempt_no_kill", "no_progress_observed"]
    assert bwd["failure_reason"] == "boss_attempt_no_kill"
    assert bwd["ml_training_label"] == "failed_teacher_attempt"
    assert bwd["segment_results"] == []


def test_live_scenario_report_builder_propagates_required_evidence(tmp_path):
    scenario_dir = tmp_path / "validation_scenarios"
    write_jsonl(
        scenario_dir / "validation_scenarios.jsonl",
        [
            {
                "scenario_id": "stonecore_5n",
                "instance": "The Stonecore",
                "map_id": 725,
                "difficulty": "normal_5man",
                "provisioning_ready": True,
                "boss_count": 1,
                "required_evidence": ["role_assignments", "party_formation"],
            }
        ],
    )
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [
            {
                "scenario_id": "stonecore_5n",
                "kind": "boss",
                "step": 8,
                "label": "High Priestess Azil",
                "route_node_id": "stonecore_azil",
                "required_evidence": ["pulls", "target_priority", "interrupts"],
            }
        ],
    )
    live_report = {
        "source_live_report": "azil.json",
        "validation_context": {
            "scenario_id": "stonecore_5n",
            "segment_id": "08_high_priestess_azil",
            "route_node_id": "stonecore_azil",
            "route_label": "High Priestess Azil",
            "route_kind": "boss",
            "route_step": 8,
            "route_generation": 1,
            "mechanic_profile": "adds_ground_danger_interrupts",
        },
        "trace_entries": 4,
        "trace": {
            "entries": [
                {"action": "boss_killed", "situation": "dungeon_boss", "result": "ok", "target_id": 42333, "route_node_id": "stonecore_azil", "route_generation": 1},
                {"action": "validation_route_terminal", "result": "boss_killed", "route_node_id": "stonecore_azil", "route_generation": 1},
                {"action": "boss_started", "route_node_id": "stonecore_azil", "route_generation": 1},
                {"action": "target_switch", "route_node_id": "stonecore_azil", "route_generation": 1},
            ]
        },
        "summary": {"boss_kills": 1},
        "evidence": {"failures": 0, "boss_kill_evidence": 1, "validation_evidence_counts": {"pulls": 1, "target_priority": 1}},
        "stages": [{"stage": "dungeon_boss", "passed": True}],
    }

    stonecore = build_live_scenario_reports(live_report, scenario_dir)["stonecore_5n"]
    segment = stonecore["segment_results"][0]

    assert segment["required_evidence"] == ["pulls", "target_priority", "interrupts"]
    assert segment["missing_evidence"] == ["interrupts"]
    assert segment["evidence_complete"] is False
    assert stonecore["required_evidence"] == ["role_assignments", "party_formation", "pulls", "target_priority", "interrupts"]
    assert stonecore["missing_evidence"] == ["role_assignments", "party_formation", "interrupts"]
    assert stonecore["clear_complete"] is False
    assert stonecore["teacher_label_quality"] == "weak"
    assert stonecore["ml_training_label"] == "weak_inferred_label"


def test_live_scenario_report_builder_ignores_summary_boss_kill_counter(tmp_path):
    scenario_dir = tmp_path / "validation_scenarios"
    write_jsonl(
        scenario_dir / "validation_scenarios.jsonl",
        [{"scenario_id": "stonecore_5n", "instance": "The Stonecore", "map_id": 725, "difficulty": "normal_5man", "provisioning_ready": True, "boss_count": 4}],
    )
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [{"scenario_id": "stonecore_5n", "kind": "boss"} for _ in range(4)],
    )
    live_report = {
        "trace_entries": 1,
        "trace": {"entries": [{"action": "boss_started"}]},
        "summary": {"boss_kills": 4},
        "evidence": {"failures": 0},
        "stages": [{"stage": "dungeon_boss", "passed": True}],
    }

    stonecore = build_live_scenario_reports(live_report, scenario_dir)["stonecore_5n"]

    assert stonecore["boss_kills"] == 0
    assert stonecore["clear_complete"] is False
    assert "missing_required_boss_kills" in stonecore["clear_complete_blockers"]


def test_live_scenario_report_builder_counts_scoped_real_boss_kill_evidence(tmp_path):
    scenario_dir = tmp_path / "validation_scenarios"
    write_jsonl(
        scenario_dir / "validation_scenarios.jsonl",
        [{"scenario_id": "stonecore_5n", "instance": "The Stonecore", "map_id": 725, "difficulty": "normal_5man", "provisioning_ready": True, "boss_count": 4}],
    )
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [
            {
                "scenario_id": "stonecore_5n",
                "kind": "boss",
                "step": 6,
                "label": "Ozruk",
                "route_node_id": "ozruk",
                "required_evidence": ["pulls", "tank_positioning", "healer_assignments", "regrouping"],
            }
        ],
    )
    live_report = {
        "validation_context": {
            "scenario_id": "stonecore_5n",
            "segment_id": "06_ozruk",
            "route_node_id": "ozruk",
            "route_label": "Ozruk",
            "route_kind": "boss",
            "route_step": 6,
            "route_generation": 1,
        },
        "trace_entries": 4,
        "trace": {
            "entries": [
                {"action": "boss_started"},
                {"action": "boss_action"},
                {"action": "boss_killed", "result": "ok", "target_id": 42188, "route_node_id": "ozruk", "route_generation": 1},
                {"action": "validation_route_terminal", "result": "boss_killed", "route_node_id": "ozruk", "route_generation": 1},
            ]
        },
        "summary": {"total_kills": 1},
        "evidence": {
            "failures": 0,
            "boss_kill_evidence": 1,
            "validation_evidence_counts": {"pulls": 1, "tank_positioning": 1, "healer_assignments": 1, "regrouping": 1},
        },
        "progress_counters": {"boss_kill_evidence": 1},
    }

    stonecore = build_live_scenario_reports(live_report, scenario_dir)["stonecore_5n"]
    segment = stonecore["segment_results"][0]

    assert segment["boss_kills"] == 1
    assert stonecore["boss_kills"] == 1


def test_live_scenario_report_builder_accepts_manifest_backed_uninterrupted_clear(tmp_path):
    scenario_dir = tmp_path / "validation_scenarios"
    write_jsonl(
        scenario_dir / "validation_scenarios.jsonl",
        [
            {
                "scenario_id": "stonecore_5n",
                "instance": "The Stonecore",
                "map_id": 725,
                "difficulty": "normal_5man",
                "provisioning_ready": True,
                "boss_count": 1,
                "required_evidence": ["party_formation", "pulls"],
            }
        ],
    )
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [
            {"scenario_id": "stonecore_5n", "kind": "trash", "step": 1, "label": "entrance packs", "route_node_id": "stonecore_trash"},
            {"scenario_id": "stonecore_5n", "kind": "boss", "step": 2, "label": "Corborus", "route_node_id": "stonecore_corborus"},
        ],
    )
    live_report = {
        "source_live_report": "stonecore_uninterrupted.json",
        "validation_context": {"scenario_id": "stonecore_5n"},
        "completion_reason": "validation_route_manifest_complete",
        "acceptable_final_evidence": True,
        "final_evidence_rejections": [],
        "validation_route_manifest": {
            "schema": "bot_live_validation_route_manifest_v1",
            "scenario_id": "stonecore_5n",
            "route_count": 2,
            "expected_segments": ["01_entrance_packs", "02_corborus"],
            "routes": [
                {"scenario_id": "stonecore_5n", "kind": "trash", "step": 1, "label": "entrance packs", "route_node_id": "stonecore_trash", "route_generation": 1},
                {"scenario_id": "stonecore_5n", "kind": "boss", "step": 2, "label": "Corborus", "route_node_id": "stonecore_corborus", "route_generation": 2},
            ],
        },
        "trace_entries": 6,
        "trace": {
            "entries": [
                {"action": "trash_action", "route_node_id": "stonecore_trash", "route_generation": 1},
                {"action": "validation_route_terminal", "result": "trash_cluster_cleared", "route_node_id": "stonecore_trash", "route_generation": 1},
                {"action": "boss_started"},
                {"action": "boss_killed", "result": "ok", "target_id": 43438, "route_node_id": "stonecore_corborus", "route_generation": 2},
                {"action": "validation_route_terminal", "result": "boss_killed", "route_node_id": "stonecore_corborus", "route_generation": 2},
            ]
        },
        "summary": {"boss_kills": 1, "trash_pulls": 1},
        "evidence": {
            "failures": 0,
            "boss_kill_evidence": 1,
            "trash_pulls": 1,
            "validation_evidence_counts": {"party_formation": 1, "pulls": 2},
        },
        "failure_labels": [],
        "failure_reason": None,
    }

    stonecore = build_live_scenario_reports(live_report, scenario_dir)["stonecore_5n"]

    assert stonecore["clear_complete"] is True
    assert stonecore["completion_evidence_mode"] == "uninterrupted_live_clear"
    assert stonecore["completion_claim_valid"] is True
    assert stonecore["observed_uninterrupted_full_clear_signal"] is True
    assert stonecore["source_segments"] == ["01_entrance_packs", "02_corborus"]
    assert stonecore["missing_segments"] == []
    assert stonecore["complete_segment_coverage"] is True
    assert stonecore["scenario_evidence_mode"] == "generic_live_trace_inference"


def test_live_scenario_report_builder_rejects_manifest_clear_without_real_boss_kills(tmp_path):
    scenario_dir = tmp_path / "validation_scenarios"
    write_jsonl(
        scenario_dir / "validation_scenarios.jsonl",
        [{"scenario_id": "stonecore_5n", "instance": "The Stonecore", "map_id": 725, "difficulty": "normal_5man", "provisioning_ready": True, "boss_count": 4}],
    )
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [
            {"scenario_id": "stonecore_5n", "kind": "trash", "step": 1, "label": "entrance packs", "route_node_id": "stonecore_trash", "required_evidence": ["pulls"]},
            {"scenario_id": "stonecore_5n", "kind": "boss", "step": 2, "label": "Corborus", "route_node_id": "stonecore_corborus", "required_evidence": ["pulls", "healer_assignments"]},
            {"scenario_id": "stonecore_5n", "kind": "boss", "step": 3, "label": "Slabhide", "route_node_id": "stonecore_slabhide", "required_evidence": ["pulls"]},
            {"scenario_id": "stonecore_5n", "kind": "boss", "step": 4, "label": "Ozruk", "route_node_id": "stonecore_ozruk", "required_evidence": ["pulls"]},
            {"scenario_id": "stonecore_5n", "kind": "boss", "step": 5, "label": "High Priestess Azil", "route_node_id": "stonecore_azil", "required_evidence": ["pulls", "interrupts"]},
        ],
    )
    live_report = {
        "source_live_report": "stonecore_uninterrupted_r12.json",
        "validation_context": {"scenario_id": "stonecore_5n"},
        "completion_reason": "validation_route_manifest_complete",
        "acceptable_final_evidence": True,
        "final_evidence_rejections": [],
        "validation_route_manifest": {
            "schema": "bot_live_validation_route_manifest_v1",
            "scenario_id": "stonecore_5n",
            "route_count": 5,
            "expected_segments": ["01_entrance_packs", "02_corborus", "03_slabhide", "04_ozruk", "05_high_priestess_azil"],
        },
        "trace_entries": 10,
        "trace": {"entries": [{"action": "validation_route_manifest_complete"}, {"action": "trash_action"}]},
        "summary": {"total_kills": 4},
        "evidence": {
            "failures": 12,
            "boss_kill_evidence": 0,
            "trash_pulls": 92,
            "validation_evidence_counts": {"pulls": 92, "tank_positioning": 183, "target_priority": 89, "regrouping": 53},
        },
        "failure_labels": [],
        "failure_reason": "",
    }

    stonecore = build_live_scenario_reports(live_report, scenario_dir)["stonecore_5n"]

    assert stonecore["clear_complete"] is False
    assert stonecore["boss_kills"] == 0
    assert stonecore["completion_evidence_mode"] == "incomplete_or_smoke_only"
    assert stonecore["missing_boss_route_nodes"] == ["stonecore_corborus", "stonecore_slabhide", "stonecore_ozruk", "stonecore_azil"]
    assert stonecore["complete_segment_coverage"] is False


def test_live_scenario_report_builder_aggregates_segmented_raid_progress_without_full_clear(tmp_path):
    scenario_dir = tmp_path / "validation_scenarios"
    write_jsonl(
        scenario_dir / "validation_scenarios.jsonl",
        [{"scenario_id": "blackwing_descent_10n", "instance": "Blackwing Descent", "map_id": 669, "difficulty": "normal_10man", "provisioning_ready": True, "boss_count": 6}],
    )
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [
            {"scenario_id": "blackwing_descent_10n", "kind": "boss", "step": index + 1, "label": f"Boss {index}", "route_node_id": f"bwd_boss_{index}"}
            for index in range(6)
        ],
    )
    live_reports = []
    for index in range(6):
        live_reports.append(
            {
                "source_live_report": f"run_{index}.json",
                "validation_context": {
                    "scenario_id": "blackwing_descent_10n",
                    "segment_id": f"{index + 1:02d}_boss_{index}",
                    "route_node_id": f"bwd_boss_{index}",
                    "route_label": f"Boss {index}",
                    "route_kind": "boss",
                    "route_step": index + 1,
                    "route_generation": index + 1,
                    "mechanic_profile": f"boss_{index}",
                },
                "trace_entries": 2,
                "trace": {
                    "entries": [
                        {"action": "raid_boss_killed", "situation": "raid_boss", "result": "ok", "target_id": 41000 + index, "route_node_id": f"bwd_boss_{index}", "route_generation": index + 1},
                        {"action": "validation_route_terminal", "result": "boss_killed", "route_node_id": f"bwd_boss_{index}", "route_generation": index + 1},
                    ]
                },
                "summary": {"raid_boss_kills": 1},
                "evidence": {"failures": 0},
                "stages": [{"stage": "raid_boss", "passed": True}],
            }
        )

    reports = build_reports_from_live_reports(live_reports, scenario_dir)
    bwd = reports["blackwing_descent_10n"]

    assert bwd["prepared_group"] is True
    assert bwd["raid_boss_kills"] == 6
    assert bwd["expected_bosses"] == 6
    assert bwd["clear_complete"] is False
    assert bwd["completion_evidence_mode"] == "segment_debug_only"
    assert bwd["clear_complete_blockers"] == ["segment_evidence_debug_only", "missing_uninterrupted_full_clear_report"]
    assert bwd["expected_segments"] == [f"{index + 1:02d}_boss_{index}" for index in range(6)]
    assert bwd["missing_segments"] == []
    assert bwd["complete_segment_coverage"] is True
    assert len(bwd["source_live_reports"]) == 6
    assert len(bwd["source_segments"]) == 6
    assert bwd["source_segments"][0] == "01_boss_0"
    assert "Boss 5" in bwd["source_route_labels"]
    assert len(bwd["segment_results"]) == 6
    assert bwd["segment_results"][0]["route_node_id"] == "bwd_boss_0"
    assert bwd["scenario_evidence_mode"] == "route_segment_context"
    assert bwd["scenario_evidence_modes"] == ["route_segment_context"]
    assert bwd["teacher_label_quality"] == "strong"
    assert bwd["ml_training_label"] == "candidate_teacher_label"


def test_live_scenario_report_builder_requires_trash_segment_coverage_for_full_clear(tmp_path):
    scenario_dir = tmp_path / "validation_scenarios"
    write_jsonl(
        scenario_dir / "validation_scenarios.jsonl",
        [{"scenario_id": "stonecore_5n", "instance": "The Stonecore", "map_id": 725, "difficulty": "normal_5man", "provisioning_ready": True, "boss_count": 1}],
    )
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [
            {"scenario_id": "stonecore_5n", "kind": "trash", "step": 1, "label": "entrance packs", "route_node_id": "stonecore_trash_0"},
            {"scenario_id": "stonecore_5n", "kind": "boss", "step": 2, "label": "Corborus", "route_node_id": "stonecore_boss_0"},
        ],
    )
    boss_report = {
        "source_live_report": "corborus.json",
        "validation_context": {
            "scenario_id": "stonecore_5n",
            "segment_id": "02_corborus",
            "route_node_id": "stonecore_boss_0",
            "route_label": "Corborus",
            "route_kind": "boss",
            "route_step": 2,
            "route_generation": 2,
            "mechanic_profile": "burrow_adds_ground_danger",
        },
        "trace_entries": 2,
        "trace": {
            "entries": [
                {"action": "boss_killed", "situation": "dungeon_boss", "result": "ok", "target_id": 43438, "route_node_id": "stonecore_boss_0", "route_generation": 2},
                {"action": "validation_route_terminal", "result": "boss_killed", "route_node_id": "stonecore_boss_0", "route_generation": 2},
            ]
        },
        "summary": {"boss_kills": 1},
        "evidence": {"failures": 0, "boss_kill_evidence": 1},
        "stages": [{"stage": "dungeon_boss", "passed": True}],
    }

    stonecore = build_reports_from_live_reports([boss_report], scenario_dir)["stonecore_5n"]

    assert stonecore["boss_kills"] == 1
    assert stonecore["expected_segments"] == ["01_entrance_packs", "02_corborus"]
    assert stonecore["source_segments"] == ["02_corborus"]
    assert stonecore["missing_segments"] == ["01_entrance_packs"]
    assert stonecore["complete_segment_coverage"] is False
    assert stonecore["clear_complete"] is False
    assert stonecore["teacher_label_quality"] == "medium"


def test_live_scenario_report_builder_rejects_duplicate_segment_as_full_clear(tmp_path):
    scenario_dir = tmp_path / "validation_scenarios"
    write_jsonl(
        scenario_dir / "validation_scenarios.jsonl",
        [{"scenario_id": "blackwing_descent_10n", "instance": "Blackwing Descent", "map_id": 669, "difficulty": "normal_10man", "provisioning_ready": True, "boss_count": 6}],
    )
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [
            {"scenario_id": "blackwing_descent_10n", "kind": "boss", "step": index + 1, "label": f"Boss {index}", "route_node_id": f"bwd_boss_{index}"}
            for index in range(6)
        ],
    )
    live_reports = [
        {
            "source_live_report": f"duplicate_magmaw_{index}.json",
            "validation_context": {
                "scenario_id": "blackwing_descent_10n",
                "segment_id": "01_boss_0",
                "route_node_id": "bwd_boss_0",
                "route_label": "Boss 0",
                "route_kind": "boss",
                "route_step": 1,
                "route_generation": 1,
                "mechanic_profile": "boss_0",
            },
            "trace_entries": 2,
            "trace": {
                "entries": [
                    {"action": "raid_boss_killed", "situation": "raid_boss", "result": "ok", "target_id": 41570, "route_node_id": "bwd_boss_0", "route_generation": 1},
                    {"action": "validation_route_terminal", "result": "boss_killed", "route_node_id": "bwd_boss_0", "route_generation": 1},
                ]
            },
            "summary": {"raid_boss_kills": 1},
            "evidence": {"failures": 0},
            "stages": [{"stage": "raid_boss", "passed": True}],
        }
        for index in range(6)
    ]

    bwd = build_reports_from_live_reports(live_reports, scenario_dir)["blackwing_descent_10n"]

    assert bwd["raid_boss_kills"] == 1
    assert bwd["source_segments"] == ["01_boss_0"]
    assert bwd["missing_segments"] == [f"{index + 1:02d}_boss_{index}" for index in range(1, 6)]
    assert bwd["complete_segment_coverage"] is False
    assert bwd["clear_complete"] is False
    assert bwd["teacher_label_quality"] == "medium"


def test_live_scenario_report_cli_skips_missing_inputs_and_removes_stale_report(tmp_path, monkeypatch):
    scenario_dir = tmp_path / "validation_scenarios"
    output_dir = tmp_path / "scenario_reports"
    write_jsonl(
        scenario_dir / "validation_scenarios.jsonl",
        [{"scenario_id": "blackwing_descent_10n", "instance": "Blackwing Descent", "map_id": 669, "difficulty": "normal_10man", "provisioning_ready": True, "boss_count": 6}],
    )
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [{"scenario_id": "blackwing_descent_10n", "kind": "boss", "step": 2, "label": "Magmaw", "route_node_id": "bwd_magmaw"}],
    )
    output_dir.mkdir()
    stale_report = output_dir / "blackwing_descent_10n.json"
    stale_report.write_text(json.dumps({"scenario_id": "blackwing_descent_10n", "clear_complete": True}), encoding="utf-8")
    missing_report = tmp_path / "live_validation_scenarios" / "blackwing_descent_10n" / "02_magmaw" / "report.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-live-scenario-reports",
            "--live-report",
            str(missing_report),
            "--validation-scenario-dir",
            str(scenario_dir),
            "--scenario-id",
            "blackwing_descent_10n",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert live_scenario_reports_main() == 0
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert stale_report.exists() is False
    assert manifest["scenario_count"] == 0
    assert manifest["source_live_reports"] == []
    assert manifest["invalid_live_report_count"] == 1
    assert manifest["invalid_live_reports"][0]["invalid_reason"] == "missing_live_report"


def test_live_bot_validation_soap_script_does_not_exit_server():
    script = command_script(selector="all", trace_limit=5, start=False, stop=False, exit_server=False)
    payload = "<SOAP-ENV:Envelope><SOAP-ENV:Body><ns1:executeCommandResponse><result>TC&gt; {&quot;active_bots&quot;:1}</result></ns1:executeCommandResponse></SOAP-ENV:Body></SOAP-ENV:Envelope>"

    assert script.splitlines() == [
        ".botauto status",
        ".botauto diagnose all",
        ".botauto trace all 5",
        ".botauto combatlog",
        ".botexp summary",
    ]
    assert "server shutdown" not in script
    assert parse_json_objects(parse_soap_result(payload)) == [{"active_bots": 1}]


def test_live_bot_validation_process_mode_observes_after_start(tmp_path, monkeypatch):
    fake_worldserver = tmp_path / "fake_worldserver.py"
    fake_worldserver.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('ARGS ' + ' '.join(sys.argv[1:]))\n"
        "print('TC> ', flush=True)\n"
        "for line in sys.stdin:\n"
        "    command = line.strip()\n"
        "    print('CMD ' + command)\n"
        "    if command == '.botauto status': print('{\"active_bots\": 1, \"target_bots\": 1}')\n"
        "    if command.startswith('.botauto diagnose'): print('{\"diagnosis_schema_version\": 1}')\n"
        "    if command.startswith('.botauto trace'): print('{\"trace_schema_version\": 1}')\n"
        "    if command == '.botexp summary': print('{\"duration_minutes\": 1}')\n"
        "    print('TC> ', flush=True)\n",
        encoding="utf-8",
    )
    fake_worldserver.chmod(0o755)
    config = tmp_path / "worldserver.conf"
    config.write_text("", encoding="utf-8")
    sleeps = []
    monkeypatch.setattr("tools.bot_ml.run_live_bot_validation.time.sleep", lambda seconds: sleeps.append(seconds))

    output, returncode, timed_out, command = run_worldserver(
        fake_worldserver,
        config,
        5,
        command_script(selector="all", trace_limit=5, start=True, stop=False),
        observe_sec=17,
    )

    assert returncode == 0
    assert timed_out is False
    assert command == [str(fake_worldserver), "--config", str(config)]
    assert sleeps[0] == 17
    assert "TC>" in output
    assert "CMD .botauto start" in output
    assert "CMD .botauto diagnose all" in output
    assert "CMD server shutdown force 0" in output


def test_live_bot_validation_process_mode_observes_before_diagnose_without_start(tmp_path, monkeypatch):
    fake_worldserver = tmp_path / "fake_worldserver.py"
    fake_worldserver.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('ARGS ' + ' '.join(sys.argv[1:]))\n"
        "print('TC> ', flush=True)\n"
        "for line in sys.stdin:\n"
        "    command = line.strip()\n"
        "    print('CMD ' + command)\n"
        "    if command == '.botauto status': print('{\"active_bots\": 1, \"target_bots\": 1}')\n"
        "    if command.startswith('.botauto diagnose'): print('{\"diagnosis_schema_version\": 1}')\n"
        "    if command.startswith('.botauto trace'): print('{\"trace_schema_version\": 1}')\n"
        "    if command == '.botexp summary': print('{\"duration_minutes\": 1}')\n"
        "    print('TC> ', flush=True)\n",
        encoding="utf-8",
    )
    fake_worldserver.chmod(0o755)
    config = tmp_path / "worldserver.conf"
    config.write_text("", encoding="utf-8")
    sleeps = []
    monkeypatch.setattr("tools.bot_ml.run_live_bot_validation.time.sleep", lambda seconds: sleeps.append(seconds))

    output, returncode, timed_out, command = run_worldserver(
        fake_worldserver,
        config,
        5,
        command_script(selector="all", trace_limit=5, start=False, stop=False),
        observe_sec=23,
    )

    assert returncode == 0
    assert timed_out is False
    assert command == [str(fake_worldserver), "--config", str(config)]
    assert sleeps[0] == 23
    assert "TC>" in output
    assert "CMD .botauto start" not in output
    assert "CMD .botauto status" in output
    assert "CMD .botauto diagnose all" in output
    assert "CMD server shutdown force 0" in output


def test_live_bot_validation_process_mode_calibration_only_observes_once(tmp_path, monkeypatch):
    fake_worldserver = tmp_path / "fake_worldserver.py"
    fake_worldserver.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('TC> ', flush=True)\n"
        "for line in sys.stdin:\n"
        "    command = line.strip()\n"
        "    print('CMD ' + command)\n"
        "    if command == '.botauto calibrate start': print('{\"ok\": true, \"action\": \"botauto_calibrate_start\"}')\n"
        "    if command == '.botauto calibrate status': print('{\"ok\": true, \"action\": \"botauto_calibrate_status\", \"active\": true}')\n"
        "    if command.startswith('server shutdown'): break\n"
        "    print('TC> ', flush=True)\n",
        encoding="utf-8",
    )
    fake_worldserver.chmod(0o755)
    config = tmp_path / "worldserver.conf"
    config.write_text("", encoding="utf-8")
    sleeps = []
    monkeypatch.setattr("tools.bot_ml.run_live_bot_validation.time.sleep", lambda seconds: sleeps.append(seconds))

    output, returncode, timed_out, _ = run_worldserver(
        fake_worldserver,
        config,
        5,
        command_script(selector="all", trace_limit=5, start=False, stop=False, combat_calibration=True),
        observe_sec=31,
    )

    assert returncode == 0
    assert timed_out is False
    assert sleeps.count(31) == 1
    assert "CMD .botauto start" not in output
    assert "CMD .botauto calibrate start" in output
    assert "CMD .botauto calibrate status" in output


def test_live_bot_validation_boss_routes_default_to_long_observation_window(tmp_path, monkeypatch, capsys):
    output_dir = tmp_path / "live_validation"
    config = tmp_path / "worldserver.conf"
    config.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_live_bot_validation.py",
            "--dry-run",
            "--config",
            str(config),
            "--output-dir",
            str(output_dir),
            "--validation-route-kind",
            "boss",
            "--validation-scenario-id",
            "stonecore_5n",
            "--validation-segment-id",
            "02_corborus",
        ],
    )

    assert live_validation_main() == 0
    capsys.readouterr()
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))

    assert report["timeout_sec"] == 900
    assert report["duration_policy"] == "completion-watchdog"
    assert report["observe_sec"] == 30
    assert report["heartbeat_sec"] == 30
    assert report["validation_context"]["route_kind"] == "boss"


def test_live_bot_validation_rejects_timeout_segment_and_teacher_only_final_evidence():
    output = """
TC> {"active_bots":5,"target_bots":5,"decisions":5}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"teacher_quest_mob_assist"},"movement":{"is_moving":true,"distance_moved_since_last_decision":3}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"teacher_kill_assist","result":"simple_open_world_quest_mob_target"},{"action":"accept_hub_quests"}]}
TC> {"duration_minutes":2,"decisions":5}
"""
    report = live_validation_report(
        output,
        stages=["movement_smoke"],
        timed_out=True,
        validation_context={"scenario_id": "stonecore_5n", "segment_id": "02_corborus"},
    )

    assert report["all_passed"] is True
    assert report["acceptable_final_evidence"] is False
    assert "timeout_is_not_final_evidence" in report["final_evidence_rejections"]
    assert "segment_or_route_context_is_debug_only" in report["final_evidence_rejections"]
    assert "teacher_assisted_only_evidence" in report["final_evidence_rejections"]
    assert report["completion_reason"] == "emergency_wall_clock_timeout"
    assert report["watchdog_state"]["progress_counters"]["teacher_assisted_kills"] == 1

def test_live_validation_session_hashes_inputs_and_builds_bounded_systemd_command(tmp_path):
    (tmp_path / ".git").mkdir()
    binary = tmp_path / "worldserver"
    binary.write_bytes(b"worldserver-v1")
    config = tmp_path / "worldserver.conf"
    config.write_text("BotWorld.AutoStart = 1\n", encoding="utf-8")

    def runner(command):
        assert command[:4] == ["git", "-C", str(tmp_path), "rev-parse"]
        return subprocess.CompletedProcess(command, 0, "a" * 40 + "\n", "")

    session = build_session(tmp_path, "production/token=secret", binary, config, command_runner=runner)
    command = systemd_transient_command(session)

    assert session.git_head == "a" * 40
    assert session.binary_sha256 == sha256_file(binary)
    assert session.environment not in session.metadata().values()
    assert "secret" not in str(session.metadata())
    assert command == [
        "systemd-run", "--user", "--quiet", "--collect", f"--unit={session.unit_name}", "--service-type=exec",
        "--property=MemoryMax=8G", "--property=MemorySwapMax=2G", "--property=CPUQuota=300%",
        f"--working-directory={tmp_path}", str(binary), "--config", str(config),
    ]


def test_live_validation_session_inspects_and_restarts_only_matching_unit(tmp_path):
    (tmp_path / ".git").mkdir()
    binary = tmp_path / "worldserver"
    binary.write_bytes(b"binary")
    config = tmp_path / "worldserver.conf"
    config.write_text("config", encoding="utf-8")
    commands = []
    states = iter([
        "LoadState=loaded\nActiveState=failed\nSubState=failed\nResult=exit-code\nMainPID=0\n",
        "LoadState=loaded\nActiveState=failed\nSubState=failed\nResult=exit-code\nMainPID=0\n",
        "LoadState=not-found\nActiveState=inactive\nSubState=dead\nResult=success\nMainPID=0\n",
        "LoadState=not-found\nActiveState=inactive\nSubState=dead\nResult=success\nMainPID=0\n",
        "LoadState=loaded\nActiveState=active\nSubState=running\nResult=success\nMainPID=123\n",
    ])

    def runner(command):
        commands.append(list(command))
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 0, "b" * 40 + "\n", "")
        if command[:3] == ["systemctl", "--user", "show"]:
            return subprocess.CompletedProcess(command, 0, next(states), "")
        return subprocess.CompletedProcess(command, 0, "", "")

    session = build_session(tmp_path, "staging", binary, config, command_runner=runner)
    result = ensure_healthy_matching_session(session, command_runner=runner)

    assert result.action == "started"
    assert result.status.healthy is True
    assert ["systemctl", "--user", "stop", session.unit_name] in commands
    assert systemd_transient_command(session) in commands


def test_live_validation_session_fails_closed_and_locks_are_repository_scoped(tmp_path):
    (tmp_path / ".git").mkdir()
    binary = tmp_path / "worldserver"
    binary.write_bytes(b"binary")
    config = tmp_path / "worldserver.conf"
    config.write_text("config", encoding="utf-8")

    def git_runner(command):
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 0, "c" * 40 + "\n", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    session = build_session(tmp_path, "staging", binary, config, command_runner=git_runner)
    with pytest.raises(LiveValidationSessionError):
        ensure_healthy_matching_session(session, command_runner=lambda command: subprocess.CompletedProcess(command, 1, "", "no systemd"))
    assert dvc_lock_path(tmp_path).parent == tmp_path / ".dvc" / "tmp" / "locks"
    assert inspect_session(session, command_runner=lambda command: subprocess.CompletedProcess(command, 1, "", "Unit does not exist")).exists is False
    with live_validation_lock(tmp_path, "staging"):
        with pytest.raises(Exception):
            with live_validation_lock(tmp_path, "staging"):
                pass
    with dvc_repository_lock(tmp_path) as lock_path:
        assert lock_path == dvc_lock_path(tmp_path)


def test_bot_autonomy_daemon_detects_rate_limit_retry_after():
    rate_limit = detect_rate_limit(
        events=[{"type": "turn.failed", "error": {"message": "429 rate limit retry-after: 120 seconds"}}],
        stdout_text="",
        stderr_text="",
        returncode=1,
        default_sleep_sec=3600,
        max_sleep_sec=86400,
        current_time=1_700_000_000,
    )

    assert rate_limit is not None
    assert rate_limit["resume_at_unix"] == 1_700_000_120
    assert rate_limit["sleep_sec"] == 120
    assert rate_limit["signature"] == "rate_limit_or_quota"


def test_bot_autonomy_daemon_default_models_and_reasoning_effort():
    assert daemon.DEFAULT_CONFIG["orchestrator_model"] == "gpt-5.6-sol"
    assert daemon.DEFAULT_CONFIG["worker_model"] == "gpt-5.6-terra"
    assert daemon.DEFAULT_CONFIG["reviewer_model"] == "gpt-5.6-sol"
    assert daemon.DEFAULT_CONFIG["orchestrator_reasoning_effort"] == "high"
    assert daemon.DEFAULT_CONFIG["worker_reasoning_effort"] == "medium"
    assert daemon.DEFAULT_CONFIG["reviewer_reasoning_effort"] == "medium"
    assert daemon.DEFAULT_CONFIG["worker_model_tiers"] == {
        "simple": {"model": "gpt-5.3-codex-spark", "reasoning_effort": "low"},
        "medium": {"model": "gpt-5.6-terra", "reasoning_effort": "medium"},
        "large": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
    }


def test_orchestrator_daemon_normalizes_worker_task_complexity_aliases():
    assert daemon.normalize_task_complexity("quick") == "simple"
    assert daemon.normalize_task_complexity("standard") == "medium"
    assert daemon.normalize_task_complexity("complex") == "large"
    assert daemon.normalize_task_complexity("unknown") == "medium"
    assert daemon.normalize_task_complexity(None, default="large") == "large"


def test_orchestrator_daemon_selects_simple_worker_model_tier():
    tier = daemon.select_worker_model_tier(daemon.DEFAULT_CONFIG, "simple")

    assert tier == {
        "complexity": "simple",
        "source": "worker_model_tiers",
        "model": "gpt-5.3-codex-spark",
        "reasoning_effort": "low",
    }


def test_orchestrator_daemon_selects_large_worker_model_tier():
    tier = daemon.select_worker_model_tier(daemon.DEFAULT_CONFIG, "large")

    assert tier == {
        "complexity": "large",
        "source": "worker_model_tiers",
        "model": "gpt-5.6-sol",
        "reasoning_effort": "high",
    }


def test_orchestrator_daemon_missing_worker_model_tier_falls_back_to_legacy_keys():
    config = dict(daemon.DEFAULT_CONFIG)
    config["worker_model"] = "legacy-worker"
    config["worker_reasoning_effort"] = "legacy-effort"
    config["worker_model_tiers"] = {"simple": {"model": "spark", "reasoning_effort": "low"}}

    tier = daemon.select_worker_model_tier(config, "large")

    assert tier == {
        "complexity": "large",
        "source": "fallback",
        "model": "legacy-worker",
        "reasoning_effort": "legacy-effort",
    }


def test_orchestrator_daemon_invalid_worker_model_tier_falls_back_to_legacy_keys():
    config = dict(daemon.DEFAULT_CONFIG)
    config["worker_model"] = "legacy-worker"
    config["worker_reasoning_effort"] = "legacy-effort"
    config["worker_model_tiers"] = {"medium": {"model": "", "reasoning_effort": ""}}

    tier = daemon.select_worker_model_tier(config, "unknown")

    assert tier == {
        "complexity": "medium",
        "source": "fallback",
        "model": "legacy-worker",
        "reasoning_effort": "legacy-effort",
    }


def test_orchestrator_daemon_worker_command_template_uses_selected_tier(tmp_path):
    command = daemon.render_worker_codex_command_template(daemon.DEFAULT_CONFIG, tmp_path, "simple")

    assert "codex exec --json -m gpt-5.3-codex-spark" in command
    assert 'model_reasoning_effort="low"' in command
    assert f"-C {tmp_path}" in command
    assert "> <jsonl_path> 2> <stderr_path>" in command


def test_orchestrator_daemon_activity_parser_summarizes_codex_jsonl_events(tmp_path):
    events = [
        {"type": "session", "thread_id": "thread-visible"},
        {"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": "I am checking the daemon."}},
        {
            "type": "item.started",
            "created_at_unix": 100,
            "item": {"id": "cmd1", "type": "command_execution", "command": "pixi run pytest -q", "status": "in_progress"},
        },
        {
            "type": "item.completed",
            "created_at_unix": 106,
            "item": {
                "id": "cmd1",
                "type": "command_execution",
                "command": "pixi run pytest -q",
                "status": "completed",
                "exit_code": 0,
                "aggregated_output": "line 1\nline 2\n",
            },
        },
        {"type": "item.completed", "item": {"id": "f1", "type": "file_change", "path": "tools/bot_ml/orchestrator_daemon.py"}},
        {"type": "item.completed", "item": {"id": "w1", "type": "web_search", "query": "codex exec json"}},
        {
            "type": "item.completed",
            "item": {
                "id": "cmd2",
                "type": "command_execution",
                "command": "false",
                "status": "failed",
                "exit_code": 1,
                "aggregated_output": "failed\n",
            },
        },
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
    ]

    activity = daemon.activity_summary_from_events(events, role="orchestrator", generated_at_unix=110)

    assert activity["schema"] == daemon.ACTIVITY_SCHEMA
    assert activity["thread_id"] == "thread-visible"
    assert activity["latest_message"] == "I am checking the daemon."
    assert activity["last_completed_command"]["command"] == "false"
    assert activity["last_failed_command"]["exit_code"] == 1
    assert activity["recent_commands"][0]["duration_sec"] == 6
    assert activity["recent_file_events"][0]["path"] == "tools/bot_ml/orchestrator_daemon.py"
    assert activity["recent_web_searches"][0]["query"] == "codex exec json"
    assert activity["token_usage"] == {"input_tokens": 10, "output_tokens": 5}


def test_bot_autonomy_daemon_codex_command_includes_reasoning_effort(tmp_path):
    command, stdin_text = codex_command(
        role="orchestrator",
        prompt="run pass",
        model="gpt-5.5",
        reasoning_effort="high",
        repo=tmp_path,
        sandbox="danger-full-access",
        jsonl_path=tmp_path / "orchestrator.jsonl",
        last_message_path=tmp_path / "last.md",
    )

    assert command[:5] == ["codex", "exec", "--json", "-m", "gpt-5.5"]
    assert command[5:7] == ["-c", 'model_reasoning_effort="high"']
    assert "--sandbox" in command
    assert stdin_text == "run pass"


def test_bot_autonomy_daemon_rate_limit_fallback_and_resume_command_omits_cd(tmp_path):
    fallback = detect_rate_limit(
        events=[],
        stdout_text="",
        stderr_text="quota exceeded; try again later",
        returncode=1,
        default_sleep_sec=3600,
        max_sleep_sec=7200,
        current_time=10,
    )
    command, stdin_text = codex_command(
        role="worker",
        prompt="continue",
        model="gpt-5.5",
        reasoning_effort="medium",
        repo=tmp_path,
        sandbox="danger-full-access",
        jsonl_path=tmp_path / "worker.jsonl",
        last_message_path=tmp_path / "last.md",
        thread_id="thread-123",
    )

    assert fallback is not None
    assert fallback["resume_at_unix"] == 3610
    assert command[:4] == ["codex", "exec", "resume", "--json"]
    assert command[6:8] == ["-c", 'model_reasoning_effort="medium"']
    assert "-C" not in command
    assert "thread-123" in command
    assert stdin_text == "continue"


def test_bot_autonomy_daemon_rate_limit_detector_ignores_state_dumps_with_rate_limit_text():
    rate_limit = detect_rate_limit(
        events=[
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "aggregated_output": json.dumps({"status": "paused_rate_limit", "rate_limit": {"signature": "rate_limit_or_quota"}}),
                },
            }
        ],
        stdout_text='{"type":"item.completed","item":{"aggregated_output":"rate_limit"}}',
        stderr_text="",
        returncode=0,
        default_sleep_sec=3600,
        max_sleep_sec=86400,
        current_time=10,
    )

    assert rate_limit is None


def test_bot_autonomy_daemon_pause_sleep_resume_transition(tmp_path, monkeypatch):
    state = initial_state()
    state_path = tmp_path / "daemon_state.json"
    stop_path = tmp_path / "daemon.stop"
    handle_rate_limit(
        state,
        {
            "agent_role": "reviewer",
            "thread_id": "thread-123",
            "resume_at_unix": 100,
            "jsonl_path": "reviewer.jsonl",
            "stderr_path": "reviewer.stderr",
        },
        state_path,
    )
    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.now_unix", lambda: 101)

    assert state["status"] == "paused_rate_limit"
    assert sleep_until_resume(state, stop_path, state_path) is True


def test_orchestrator_daemon_stop_during_rate_limit_sleep_marks_stopped(tmp_path, monkeypatch):
    state = initial_state()
    state_path = tmp_path / "daemon_state.json"
    stop_path = tmp_path / "daemon.stop"
    stop_path.write_text("stop", encoding="utf-8")
    handle_rate_limit(
        state,
        {
            "agent_role": "orchestrator",
            "thread_id": "thread-456",
            "resume_at_unix": 200,
        },
        state_path,
    )
    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.now_unix", lambda: 100)

    assert sleep_until_resume(state, stop_path, state_path) is False
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["status"] == "stopped"
    assert saved["phase"] == "stop_requested"
    assert saved["rate_limit"] == {}


def test_orchestrator_daemon_status_does_not_report_rate_limit_sleep_when_stopped(tmp_path, monkeypatch):
    config_path = tmp_path / "daemon_config.json"
    state_path = tmp_path / "daemon_state.json"
    checklist_path = tmp_path / "master_checklist.json"
    config_path.write_text(json.dumps({}), encoding="utf-8")
    checklist_path.write_text(json.dumps({"deliverables": []}), encoding="utf-8")
    state = initial_state()
    state.update(
        {
            "status": "stopped",
            "phase": "stop_requested",
            "rate_limit": {"resume_at_unix": 200},
        }
    )
    state_path.write_text(json.dumps(state), encoding="utf-8")
    args = daemon.build_parser().parse_args(
        [
            "--config",
            str(config_path),
            "--state",
            str(state_path),
            "--checklist",
            str(checklist_path),
            "--lock",
            str(tmp_path / "daemon.lock"),
            "--pid",
            str(tmp_path / "daemon.pid"),
            "--stop-file",
            str(tmp_path / "daemon.stop"),
            "--log",
            str(tmp_path / "daemon.log"),
            "status",
        ]
    )
    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.now_unix", lambda: 100)

    payload = daemon.status_payload(args)

    assert payload["state"]["status"] == "stopped"
    assert payload["rate_limit_sleep_remaining_sec"] == 0


def test_bot_autonomy_daemon_starts_fresh_orchestrator_after_rate_limit_pause(tmp_path, monkeypatch):
    checklist = {
        "deliverables": [
            {"deliverable": "movement_smoke", "status": "needs_followup", "evidence_artifact": ""},
        ]
    }
    state = initial_state()
    state.update(
        {
            "status": "paused_rate_limit",
            "cycle_id": 4,
            "rate_limit": {
                "agent_role": "orchestrator",
                "thread_id": "thread-123",
                "prompt": "continue orchestrator",
            },
        }
    )
    calls = []
    last_message = tmp_path / "last.md"

    def fake_run_codex_role(**kwargs):
        calls.append(kwargs)
        last_message.write_text(json.dumps({"status": "continue", "summary": "resumed", "progress_artifacts": []}), encoding="utf-8")
        return {
            "rate_limit": None,
            "returncode": 0,
            "thread_id": "new-thread",
            "jsonl_path": tmp_path / "orchestrator.jsonl",
            "stderr_path": tmp_path / "orchestrator.stderr",
            "last_message_path": last_message,
        }

    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.load_checklist", lambda path=None: checklist)
    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.run_codex_role", fake_run_codex_role)

    result = run_one_cycle(
        state,
        {
            "repo": str(tmp_path),
            "orchestrator_model": "gpt-5",
            "worker_model": "gpt-5-worker",
            "reviewer_model": "gpt-5-reviewer",
            "sandbox": "danger-full-access",
            "runs_dir": str(tmp_path / "runs"),
        },
        tmp_path / "state.json",
    )

    assert result == {"done": False, "status": "continue"}
    assert calls[0]["role"] == "orchestrator"
    assert calls[0].get("thread_id", "") == ""
    assert calls[0]["model"] == "gpt-5"
    assert state["rate_limit"] == {}
    assert state["previous_rate_limit"]["thread_id"] == "thread-123"


def test_orchestrator_daemon_new_cycle_moves_stale_latest_result_to_previous(tmp_path, monkeypatch):
    state = initial_state()
    state.update(
        {
            "cycle_id": 8,
            "latest_orchestrator_result": {
                "status": "failure",
                "error": "orchestrator_resume_failed",
                "returncode": 2,
            },
        }
    )
    last_message = tmp_path / "last.md"

    def fake_run_codex_role(**_kwargs):
        last_message.write_text(json.dumps({"status": "continue", "summary": "fresh", "progress_artifacts": []}), encoding="utf-8")
        return {
            "rate_limit": None,
            "returncode": 0,
            "thread_id": "fresh-thread",
            "jsonl_path": tmp_path / "orchestrator.jsonl",
            "stderr_path": tmp_path / "orchestrator.stderr",
            "last_message_path": last_message,
        }

    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.load_checklist", lambda path=None: {"deliverables": []})
    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.run_codex_role", fake_run_codex_role)

    result = run_one_cycle(
        state,
        {
            "repo": str(tmp_path),
            "orchestrator_model": "gpt-5",
            "sandbox": "danger-full-access",
            "runs_dir": str(tmp_path / "runs"),
        },
        tmp_path / "state.json",
    )

    assert result == {"done": False, "status": "continue"}
    assert state["cycle_id"] == 9
    assert state["previous_orchestrator_result"]["error"] == "orchestrator_resume_failed"
    assert state["latest_orchestrator_result"]["summary"] == "fresh"


def test_bot_autonomy_daemon_prompt_file_precedence(tmp_path):
    config_prompt = tmp_path / "config_prompt.md"
    cli_prompt = tmp_path / "cli_prompt.md"
    config_prompt.write_text("config prompt", encoding="utf-8")
    cli_prompt.write_text("cli prompt", encoding="utf-8")

    config = {"prompt_file": str(config_prompt)}
    config_args = daemon.build_parser().parse_args(["run", "--once"])
    global_cli_args = daemon.build_parser().parse_args(["--prompt-file", str(cli_prompt), "run", "--once"])
    command_cli_args = daemon.build_parser().parse_args(["run", "--prompt-file", str(cli_prompt), "--once"])

    assert daemon.effective_prompt_file(config, config_args) == config_prompt
    assert daemon.effective_prompt_file(config, global_cli_args) == cli_prompt
    assert daemon.effective_prompt_file(config, command_cli_args) == cli_prompt


def test_orchestrator_daemon_named_instance_paths_and_checklist_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "ORCHESTRATOR_INSTANCES_DIR", tmp_path / "instances")
    monkeypatch.setattr(daemon, "ORCHESTRATOR_WORKTREES_DIR", tmp_path / "worktrees")
    checklist_source = tmp_path / "source_checklist.json"
    checklist_source.write_text(json.dumps({"deliverables": [{"deliverable": "stonecore"}]}), encoding="utf-8")

    args = daemon.build_parser().parse_args(["--instance", "Stone Core", "--checklist", str(checklist_source), "status"])
    daemon.apply_instance_paths(args)

    assert args.instance_id == "stone-core"
    assert args.instance_dir == tmp_path / "instances" / "stone-core"
    assert args.state == args.instance_dir / "daemon_state.json"
    assert args.lock == args.instance_dir / "daemon.lock"
    assert args.pid == args.instance_dir / "daemon.pid"
    assert args.stop_file == args.instance_dir / "daemon.stop"
    assert args.log == args.instance_dir / "daemon.log"
    assert args.runs_dir == args.instance_dir / "runs"
    assert args.checklist == args.instance_dir / "master_checklist.json"
    assert args.worktree_path == tmp_path / "worktrees" / "stone-core"
    assert json.loads(args.checklist.read_text(encoding="utf-8"))["deliverables"][0]["deliverable"] == "stonecore"

    checklist_source.write_text(json.dumps({"deliverables": [{"deliverable": "overwritten"}]}), encoding="utf-8")
    second_args = daemon.build_parser().parse_args(["--instance", "Stone Core", "--checklist", str(checklist_source), "status"])
    daemon.apply_instance_paths(second_args)

    assert json.loads(second_args.checklist.read_text(encoding="utf-8"))["deliverables"][0]["deliverable"] == "stonecore"


def test_orchestrator_daemon_legacy_paths_are_preserved():
    args = daemon.build_parser().parse_args(["status"])
    daemon.apply_instance_paths(args)

    assert args.instance_id == daemon.LEGACY_INSTANCE_ID
    assert args.state == daemon.DEFAULT_STATE_PATH
    assert args.lock == daemon.DEFAULT_LOCK_PATH
    assert args.pid == daemon.DEFAULT_PID_PATH
    assert args.stop_file == daemon.DEFAULT_STOP_PATH
    assert args.log == daemon.DEFAULT_LOG_PATH
    assert args.runs_dir == daemon.DEFAULT_RUNS_DIR


def test_orchestrator_daemon_two_instances_are_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "ORCHESTRATOR_INSTANCES_DIR", tmp_path / "instances")
    monkeypatch.setattr(daemon, "ORCHESTRATOR_WORKTREES_DIR", tmp_path / "worktrees")

    first = daemon.build_parser().parse_args(["--instance", "stonecore", "status"])
    second = daemon.build_parser().parse_args(["--instance", "bwd", "status"])
    daemon.apply_instance_paths(first)
    daemon.apply_instance_paths(second)

    assert first.state != second.state
    assert first.lock != second.lock
    assert first.pid != second.pid
    assert first.stop_file != second.stop_file
    assert first.log != second.log
    assert first.runs_dir != second.runs_dir
    assert first.checklist != second.checklist
    assert first.worktree_path != second.worktree_path
    assert daemon.instance_branch(first.instance_id) == "orchestrator/stonecore"
    assert daemon.instance_branch(second.instance_id) == "orchestrator/bwd"


def test_orchestrator_daemon_start_uses_new_module_and_compat_pixi_alias(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "ORCHESTRATOR_INSTANCES_DIR", tmp_path / "instances")
    monkeypatch.setattr(daemon, "ORCHESTRATOR_WORKTREES_DIR", tmp_path / "worktrees")
    captured = {}

    class FakeProcess:
        pid = 12345

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(daemon.subprocess, "Popen", fake_popen)
    args = daemon.build_parser().parse_args(["--instance", "stonecore", "start"])
    daemon.apply_instance_paths(args)

    assert daemon.start_daemon(args) == 0
    assert captured["command"][:3] == [sys.executable, "-m", "tools.bot_ml.orchestrator_daemon"]
    assert captured["command"][3:5] == ["--instance", "stonecore"]
    assert (args.pid).read_text(encoding="utf-8") == "12345"
    pixi_tasks = Path("pixi.toml").read_text(encoding="utf-8")
    assert 'orchestrator-daemon = "python -m tools.bot_ml.orchestrator_daemon"' in pixi_tasks
    assert 'bot-autonomy-daemon = "python -m tools.bot_ml.orchestrator_daemon"' in pixi_tasks


def test_orchestrator_daemon_named_run_uses_instance_worktree(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "ORCHESTRATOR_INSTANCES_DIR", tmp_path / "instances")
    monkeypatch.setattr(daemon, "ORCHESTRATOR_WORKTREES_DIR", tmp_path / "worktrees")
    config_path = tmp_path / "daemon_config.json"
    worktree = tmp_path / "worktrees" / "stonecore"
    calls = []

    def fake_ensure_instance_worktree(repo, instance_id):
        assert repo == daemon.REPO_ROOT
        assert instance_id == "stonecore"
        worktree.mkdir(parents=True)
        return worktree

    def fake_run_one_cycle(state, config, state_path):
        calls.append((state, config, state_path))
        return {"done": True, "status": "complete"}

    monkeypatch.setattr(daemon, "ensure_instance_worktree", fake_ensure_instance_worktree)
    monkeypatch.setattr(daemon, "run_one_cycle", fake_run_one_cycle)
    args = daemon.build_parser().parse_args(["--instance", "stonecore", "--config", str(config_path), "run", "--once"])
    daemon.apply_instance_paths(args)

    assert daemon.run_daemon(args) == 0
    assert calls[0][1]["repo"] == str(worktree)
    assert calls[0][1]["runs_dir"] == str(tmp_path / "instances" / "stonecore" / "runs")
    state = json.loads(args.state.read_text(encoding="utf-8"))
    assert state["schema"] == "orchestrator_daemon_state_v1"
    assert state["instance_id"] == "stonecore"
    assert state["worktree_path"] == str(worktree)


def init_merge_back_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    return repo


def merge_back_args(tmp_path: Path, repo: Path, worktree: Path, instance_id: str = "stone") -> object:
    instance_root = tmp_path / "instances" / instance_id
    instance_root.mkdir(parents=True, exist_ok=True)
    state_path = instance_root / "daemon_state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema": "orchestrator_daemon_state_v1",
                "status": "complete",
                "instance_id": instance_id,
                "instance_dir": str(instance_root),
                "worktree_path": str(worktree),
            }
        ),
        encoding="utf-8",
    )
    args = daemon.build_parser().parse_args(
        [
            "--instance",
            instance_id,
            "--state",
            str(state_path),
            "--checklist",
            str(instance_root / "master_checklist.json"),
            "status",
        ]
    )
    args.instance_id = instance_id
    args.instance_dir = instance_root
    args.state = state_path
    args.lock = instance_root / "daemon.lock"
    args.pid = instance_root / "daemon.pid"
    args.stop_file = instance_root / "daemon.stop"
    args.log = instance_root / "daemon.log"
    args.runs_dir = instance_root / "runs"
    args.worktree_path = worktree
    return args


def merge_back_config(tmp_path: Path, repo: Path) -> dict[str, object]:
    config = dict(daemon.DEFAULT_CONFIG)
    config["repo"] = str(repo)
    config["runs_dir"] = str(tmp_path / "runs")
    return config


def add_instance_worktree(repo: Path, tmp_path: Path, instance_id: str = "stone") -> Path:
    branch = daemon.instance_branch(instance_id)
    subprocess.run(["git", "branch", branch], cwd=repo, check=True)
    worktree = tmp_path / "worktrees" / instance_id
    subprocess.run(["git", "worktree", "add", str(worktree), branch], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=worktree, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=worktree, check=True)
    return worktree


def commit_file(repo: Path, relative: str, text: str, message: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", relative], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)


def ok_merge_verification(repo: Path, config: dict[str, object]) -> dict[str, object]:
    return {"schema": "orchestrator_merge_back_verification_v1", "ok": True, "steps": []}


def test_orchestrator_daemon_legacy_run_does_not_attempt_merge_back(tmp_path, monkeypatch):
    config_path = tmp_path / "daemon_config.json"
    state_path = tmp_path / "daemon_state.json"
    lock_path = tmp_path / "daemon.lock"
    pid_path = tmp_path / "daemon.pid"
    stop_path = tmp_path / "daemon.stop"

    def fake_run_one_cycle(state, config, state_path_arg):
        state.update({"status": "complete", "phase": "complete"})
        daemon.save_state(state, state_path_arg)
        return {"done": True, "status": "complete"}

    def fail_finalize(args, config):
        raise AssertionError("legacy runs must not attempt merge-back")

    monkeypatch.setattr(daemon, "run_one_cycle", fake_run_one_cycle)
    monkeypatch.setattr(daemon, "finalize_named_instance_merge_back", fail_finalize)
    args = daemon.build_parser().parse_args(
        [
            "--config",
            str(config_path),
            "--state",
            str(state_path),
            "--lock",
            str(lock_path),
            "--pid",
            str(pid_path),
            "--stop-file",
            str(stop_path),
            "run",
            "--once",
        ]
    )
    daemon.apply_instance_paths(args)

    assert daemon.run_daemon(args) == 0
    assert not lock_path.exists()


def test_orchestrator_daemon_named_clean_stop_triggers_merge_back(tmp_path, monkeypatch):
    config_path = tmp_path / "daemon_config.json"
    called = []

    def fake_run_one_cycle(state, config, state_path):
        state.update({"status": "complete", "phase": "complete"})
        daemon.save_state(state, state_path)
        return {"done": True, "status": "complete"}

    def fake_finalize(args, config):
        called.append((args.instance_id, config["repo"]))
        return {"status": "skipped"}

    monkeypatch.setattr(daemon, "ORCHESTRATOR_INSTANCES_DIR", tmp_path / "instances")
    monkeypatch.setattr(daemon, "ORCHESTRATOR_WORKTREES_DIR", tmp_path / "worktrees")
    monkeypatch.setattr(daemon, "ensure_instance_worktree", lambda repo, instance_id: tmp_path / "worktrees" / instance_id)
    monkeypatch.setattr(daemon, "run_one_cycle", fake_run_one_cycle)
    monkeypatch.setattr(daemon, "finalize_named_instance_merge_back", fake_finalize)
    args = daemon.build_parser().parse_args(["--instance", "stone", "--config", str(config_path), "run", "--once"])
    daemon.apply_instance_paths(args)

    assert daemon.run_daemon(args) == 0
    assert called == [("stone", str(tmp_path / "worktrees" / "stone"))]


def test_orchestrator_daemon_dirty_instance_worktree_blocks_merge_back(tmp_path, monkeypatch):
    repo = init_merge_back_repo(tmp_path)
    worktree = add_instance_worktree(repo, tmp_path)
    (worktree / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
    args = merge_back_args(tmp_path, repo, worktree)
    monkeypatch.setattr(daemon, "REPO_ROOT", repo)

    report = daemon.finalize_named_instance_merge_back(args, merge_back_config(tmp_path, repo))

    assert report["status"] == "failed"
    assert report["failure_reason"] == "instance_worktree_dirty"


def test_orchestrator_daemon_empty_instance_branch_skips_merge_back(tmp_path, monkeypatch):
    repo = init_merge_back_repo(tmp_path)
    worktree = add_instance_worktree(repo, tmp_path)
    args = merge_back_args(tmp_path, repo, worktree)
    monkeypatch.setattr(daemon, "REPO_ROOT", repo)

    report = daemon.finalize_named_instance_merge_back(args, merge_back_config(tmp_path, repo))

    assert report["status"] == "skipped"
    assert report["reason"] == "instance_branch_already_reachable"


def test_orchestrator_daemon_clean_merge_back_records_no_ff_commit(tmp_path, monkeypatch):
    repo = init_merge_back_repo(tmp_path)
    worktree = add_instance_worktree(repo, tmp_path)
    commit_file(worktree, "instance.txt", "instance\n", "instance change")
    args = merge_back_args(tmp_path, repo, worktree)
    monkeypatch.setattr(daemon, "REPO_ROOT", repo)
    monkeypatch.setattr(daemon, "run_merge_back_verification", ok_merge_verification)

    report = daemon.finalize_named_instance_merge_back(args, merge_back_config(tmp_path, repo))

    assert report["status"] == "merged"
    assert report["merge_commit"]
    subject = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
    assert subject == "Merge orchestrator instance stone"
    parents = subprocess.run(["git", "rev-list", "--parents", "-n", "1", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.split()
    assert len(parents) == 3
    assert (repo / "instance.txt").read_text(encoding="utf-8") == "instance\n"


def test_orchestrator_daemon_dirty_main_invokes_codex_preflight_before_merge(tmp_path, monkeypatch):
    repo = init_merge_back_repo(tmp_path)
    worktree = add_instance_worktree(repo, tmp_path)
    commit_file(worktree, "instance.txt", "instance\n", "instance change")
    (repo / "main.txt").write_text("main dirty\n", encoding="utf-8")
    args = merge_back_args(tmp_path, repo, worktree)
    calls = []

    def fake_codex_pass(**kwargs):
        calls.append(kwargs["role"])
        subprocess.run(["git", "add", "main.txt"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "preflight main changes"], cwd=repo, check=True, capture_output=True)
        return {"returncode": 0, "jsonl_path": "", "stderr_path": "", "last_message_path": ""}

    monkeypatch.setattr(daemon, "REPO_ROOT", repo)
    monkeypatch.setattr(daemon, "run_merge_back_codex_pass", fake_codex_pass)
    monkeypatch.setattr(daemon, "run_merge_back_verification", ok_merge_verification)

    report = daemon.finalize_named_instance_merge_back(args, merge_back_config(tmp_path, repo))

    assert calls == ["merge_back_preflight"]
    assert report["status"] == "merged"
    assert report["preflight_commit"]


def test_orchestrator_daemon_merge_conflict_invokes_codex_resolver(tmp_path, monkeypatch):
    repo = init_merge_back_repo(tmp_path)
    worktree = add_instance_worktree(repo, tmp_path)
    commit_file(worktree, "base.txt", "base from instance\n", "instance edit")
    commit_file(repo, "base.txt", "base from main\n", "main edit")
    args = merge_back_args(tmp_path, repo, worktree)
    calls = []

    def fake_codex_pass(**kwargs):
        calls.append(kwargs["role"])
        (repo / "base.txt").write_text("base from main\nbase from instance\n", encoding="utf-8")
        subprocess.run(["git", "add", "base.txt"], cwd=repo, check=True)
        return {"returncode": 0, "jsonl_path": "", "stderr_path": "", "last_message_path": ""}

    monkeypatch.setattr(daemon, "REPO_ROOT", repo)
    monkeypatch.setattr(daemon, "run_merge_back_codex_pass", fake_codex_pass)
    monkeypatch.setattr(daemon, "run_merge_back_verification", ok_merge_verification)

    report = daemon.finalize_named_instance_merge_back(args, merge_back_config(tmp_path, repo))

    assert calls == ["merge_back_conflict_resolver"]
    assert report["status"] == "merged"
    assert report["conflict_files"] == ["base.txt"]
    assert (repo / "base.txt").read_text(encoding="utf-8") == "base from main\nbase from instance\n"


def test_orchestrator_daemon_resolver_failure_aborts_merge_and_leaves_main_clean(tmp_path, monkeypatch):
    repo = init_merge_back_repo(tmp_path)
    worktree = add_instance_worktree(repo, tmp_path)
    commit_file(worktree, "base.txt", "base from instance\n", "instance edit")
    commit_file(repo, "base.txt", "base from main\n", "main edit")
    args = merge_back_args(tmp_path, repo, worktree)

    def fake_codex_pass(**kwargs):
        return {"returncode": 1, "jsonl_path": "", "stderr_path": "", "last_message_path": ""}

    monkeypatch.setattr(daemon, "REPO_ROOT", repo)
    monkeypatch.setattr(daemon, "run_merge_back_codex_pass", fake_codex_pass)

    report = daemon.finalize_named_instance_merge_back(args, merge_back_config(tmp_path, repo))

    assert report["status"] == "failed"
    assert report["failure_reason"] == "conflict_resolver_failed"
    assert daemon.git_status_porcelain(repo) == ""
    assert (repo / "base.txt").read_text(encoding="utf-8") == "base from main\n"


def test_orchestrator_daemon_instances_payload_summarizes_known_instances(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "AUTO_BOTS_DIR", tmp_path / "legacy")
    monkeypatch.setattr(daemon, "ORCHESTRATOR_INSTANCES_DIR", tmp_path / "instances")
    monkeypatch.setattr(daemon, "ORCHESTRATOR_WORKTREES_DIR", tmp_path / "worktrees")
    legacy_state = tmp_path / "legacy" / "daemon_state.json"
    named_state = tmp_path / "instances" / "stonecore" / "daemon_state.json"
    legacy_state.parent.mkdir(parents=True)
    named_state.parent.mkdir(parents=True)
    legacy_state.write_text(json.dumps({"status": "running", "cycle_id": 3, "prompt_file": "legacy.md"}), encoding="utf-8")
    named_state.write_text(
        json.dumps(
            {
                "status": "complete",
                "cycle_id": 7,
                "prompt_file": "stonecore.md",
                "latest_orchestrator_result": {"status": "complete"},
                "merge_back": {"status": "merged", "merge_commit": "abc123"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "instances" / "stonecore" / "daemon.lock").write_text("123", encoding="utf-8")

    payload = daemon.instances_payload(daemon.build_parser().parse_args(["instances"]))

    assert payload["schema"] == "orchestrator_daemon_instances_v1"
    rows = {row["instance_id"]: row for row in payload["instances"]}
    assert rows["legacy"]["status"] == "running"
    assert rows["legacy"]["cycle_id"] == 3
    assert rows["stonecore"]["status"] == "complete"
    assert rows["stonecore"]["lock_exists"] is True
    assert rows["stonecore"]["worktree_path"] == str(tmp_path / "worktrees" / "stonecore")
    assert rows["stonecore"]["merge_back"]["status"] == "merged"


def test_orchestrator_daemon_status_payload_exposes_merge_back(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "ORCHESTRATOR_INSTANCES_DIR", tmp_path / "instances")
    monkeypatch.setattr(daemon, "ORCHESTRATOR_WORKTREES_DIR", tmp_path / "worktrees")
    args = daemon.build_parser().parse_args(["--instance", "stone", "status"])
    daemon.apply_instance_paths(args)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps({"status": "complete", "merge_back": {"status": "merged"}}), encoding="utf-8")

    payload = daemon.status_payload(args)

    assert payload["merge_back"]["status"] == "merged"


def test_orchestrator_daemon_diagnostics_flags_stale_codex_child_without_output(tmp_path, monkeypatch):
    config_path = tmp_path / "daemon_config.json"
    state_path = tmp_path / "daemon_state.json"
    checklist_path = tmp_path / "master_checklist.json"
    lock_path = tmp_path / "daemon.lock"
    pid_path = tmp_path / "daemon.pid"
    stop_path = tmp_path / "daemon.stop"
    log_path = tmp_path / "daemon.log"
    config_path.write_text(json.dumps({"heartbeat_sec": 10, "no_progress_window_sec": 30}), encoding="utf-8")
    checklist_path.write_text(json.dumps({"deliverables": []}), encoding="utf-8")
    lock_path.write_text("10", encoding="utf-8")
    pid_path.write_text("10", encoding="utf-8")
    state = initial_state()
    state.update(
        {
            "status": "running",
            "phase": "codex_orchestrator",
            "updated_at_unix": 1000,
            "latest_jsonl_path": str(tmp_path / "missing.jsonl"),
            "latest_stderr_path": str(tmp_path / "missing.stderr"),
            "latest_last_message_path": str(tmp_path / "missing.last_message.md"),
        }
    )
    state_path.write_text(json.dumps(state), encoding="utf-8")
    args = daemon.build_parser().parse_args(
        [
            "--config",
            str(config_path),
            "--state",
            str(state_path),
            "--checklist",
            str(checklist_path),
            "--lock",
            str(lock_path),
            "--pid",
            str(pid_path),
            "--stop-file",
            str(stop_path),
            "--log",
            str(log_path),
            "debug",
        ]
    )
    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.now_unix", lambda: 1100)
    table = {
        10: {"pid": 10, "ppid": 1, "state": "S", "elapsed_sec": 100, "command": "python -m tools.bot_ml.orchestrator_daemon run"},
        11: {"pid": 11, "ppid": 10, "state": "S", "elapsed_sec": 45, "command": "node codex exec --json -m gpt-5.5"},
    }

    diagnostics = daemon.daemon_diagnostics(args, state, table=table)

    assert diagnostics["healthy"] is False
    assert "daemon_state_not_heartbeating_while_codex_active" in diagnostics["suspicions"]
    assert "active_codex_no_output_over_no_progress_window" in diagnostics["suspicions"]
    assert diagnostics["active_codex_processes"][0]["pid"] == 11


def test_orchestrator_daemon_run_codex_role_streams_artifacts_and_heartbeats(tmp_path, monkeypatch):
    state = initial_state()
    state_path = tmp_path / "daemon_state.json"

    def fake_codex_command(**_kwargs):
        script = (
            "import json, sys; "
            "sys.stdin.read(); "
            "print(json.dumps({'type': 'session', 'thread_id': 'thread-streamed'})); "
            "sys.stderr.write('diagnostic stderr\\n')"
        )
        return [sys.executable, "-c", script], "prompt"

    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.codex_command", fake_codex_command)

    result = daemon.run_codex_role(
        role="orchestrator",
        prompt="prompt",
        model="gpt-test",
        repo=tmp_path,
        sandbox="danger-full-access",
        cycle_id=1,
        state=state,
        config={"runs_dir": str(tmp_path / "runs"), "heartbeat_sec": 1, "no_progress_window_sec": 30},
        state_path=state_path,
    )

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert result["returncode"] == 0
    assert result["thread_id"] == "thread-streamed"
    assert result["jsonl_path"].read_text(encoding="utf-8").strip()
    assert result["stderr_path"].read_text(encoding="utf-8") == "diagnostic stderr\n"
    assert result["activity_path"].name == "activity.json"
    activity = json.loads(result["activity_path"].read_text(encoding="utf-8"))
    assert activity["latest_message"] == ""
    assert activity["thread_id"] == "thread-streamed"
    assert saved["active_process"]["status"] == "exited"
    assert saved["active_process"]["stdout_bytes"] > 0
    assert saved["active_process"]["stderr_bytes"] > 0
    assert saved["latest_activity_path"] == str(result["activity_path"])


def test_orchestrator_daemon_run_codex_role_writes_live_activity_snapshot(tmp_path, monkeypatch):
    state = initial_state()
    state_path = tmp_path / "daemon_state.json"

    def fake_codex_command(**_kwargs):
        script = (
            "import json, sys; "
            "sys.stdin.read(); "
            "print(json.dumps({'type': 'item.completed', 'item': {'id': 'm1', 'type': 'agent_message', 'text': 'live message'}}), flush=True); "
            "print(json.dumps({'type': 'item.started', 'item': {'id': 'cmd1', 'type': 'command_execution', 'command': 'pixi run pytest -q', 'status': 'in_progress'}}), flush=True); "
            "print(json.dumps({'type': 'item.completed', 'item': {'id': 'cmd1', 'type': 'command_execution', 'command': 'pixi run pytest -q', 'status': 'completed', 'exit_code': 0, 'aggregated_output': 'ok\\\\n'}}), flush=True)"
        )
        return [sys.executable, "-c", script], "prompt"

    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.codex_command", fake_codex_command)

    result = daemon.run_codex_role(
        role="orchestrator",
        prompt="prompt",
        model="gpt-test",
        repo=tmp_path,
        sandbox="danger-full-access",
        cycle_id=1,
        state=state,
        config={"runs_dir": str(tmp_path / "runs"), "heartbeat_sec": 1, "no_progress_window_sec": 30},
        state_path=state_path,
    )

    activity = json.loads(result["activity_path"].read_text(encoding="utf-8"))
    assert activity["latest_message"] == "live message"
    assert activity["last_completed_command"]["command"] == "pixi run pytest -q"
    assert activity["last_completed_command"]["exit_code"] == 0


def test_orchestrator_daemon_watch_once_reads_activity_and_agent_registry(tmp_path, capsys):
    run_dir = tmp_path / "runs" / "000001"
    run_dir.mkdir(parents=True)
    orchestrator_jsonl = run_dir / "orchestrator.jsonl"
    orchestrator_jsonl.write_text(
        json.dumps({"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": "orchestrator visible"}}) + "\n",
        encoding="utf-8",
    )
    worker_jsonl = run_dir / "worker-1.jsonl"
    worker_jsonl.write_text(
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "cmd1",
                    "type": "command_execution",
                    "command": "pixi run pytest -q",
                    "status": "failed",
                    "exit_code": 1,
                    "aggregated_output": "boom\n",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "agent_registry.json").write_text(
        json.dumps(
            {
                "schema": daemon.AGENT_REGISTRY_SCHEMA,
                "agents": [
                    {
                        "id": "worker-1",
                        "role": "worker",
                        "status": "failed",
                        "jsonl_path": "worker-1.jsonl",
                        "stderr_path": "worker-1.stderr",
                        "last_message_path": "worker-1.last_message.md",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "daemon_state.json"
    config_path = tmp_path / "daemon_config.json"
    checklist_path = tmp_path / "master_checklist.json"
    config_path.write_text(json.dumps({"no_progress_window_sec": 30}), encoding="utf-8")
    checklist_path.write_text(json.dumps({"deliverables": []}), encoding="utf-8")
    state = initial_state()
    state.update({"status": "running", "phase": "codex_orchestrator", "cycle_id": 1, "latest_jsonl_path": str(orchestrator_jsonl)})
    state_path.write_text(json.dumps(state), encoding="utf-8")
    args = daemon.build_parser().parse_args(
        [
            "--config",
            str(config_path),
            "--state",
            str(state_path),
            "--checklist",
            str(checklist_path),
            "--lock",
            str(tmp_path / "daemon.lock"),
            "--pid",
            str(tmp_path / "daemon.pid"),
            "--stop-file",
            str(tmp_path / "daemon.stop"),
            "--log",
            str(tmp_path / "daemon.log"),
            "watch",
            "--once",
            "--raw-tail",
            "1",
        ]
    )

    assert daemon.watch_daemon(args) == 0
    output = capsys.readouterr().out
    assert "orchestrator visible" in output
    assert "worker-1" in output
    assert "last failure: rc=1 pixi run pytest -q" in output


def test_orchestrator_daemon_status_and_debug_include_activity(tmp_path):
    run_dir = tmp_path / "runs" / "000001"
    run_dir.mkdir(parents=True)
    jsonl_path = run_dir / "orchestrator.jsonl"
    jsonl_path.write_text(
        json.dumps({"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": "status activity"}}) + "\n",
        encoding="utf-8",
    )
    state_path = tmp_path / "daemon_state.json"
    config_path = tmp_path / "daemon_config.json"
    checklist_path = tmp_path / "master_checklist.json"
    config_path.write_text(json.dumps({"no_progress_window_sec": 30}), encoding="utf-8")
    checklist_path.write_text(json.dumps({"deliverables": []}), encoding="utf-8")
    state = initial_state()
    state.update({"latest_jsonl_path": str(jsonl_path), "latest_activity_path": str(run_dir / "activity.json")})
    state_path.write_text(json.dumps(state), encoding="utf-8")
    args = daemon.build_parser().parse_args(
        [
            "--config",
            str(config_path),
            "--state",
            str(state_path),
            "--checklist",
            str(checklist_path),
            "--lock",
            str(tmp_path / "daemon.lock"),
            "--pid",
            str(tmp_path / "daemon.pid"),
            "--stop-file",
            str(tmp_path / "daemon.stop"),
            "--log",
            str(tmp_path / "daemon.log"),
            "status",
        ]
    )

    status = daemon.status_payload(args)
    debug = daemon.debug_payload(args)

    assert status["activity"]["latest_message"] == "status activity"
    assert "last_event_age_sec" in status["activity"]
    assert debug["activity"]["latest_message"] == "status activity"


def test_bot_autonomy_daemon_compat_import_uses_orchestrator_daemon():
    from tools.bot_ml import bot_autonomy_daemon as compat_daemon

    assert compat_daemon.codex_command is daemon.codex_command


def test_bot_autonomy_daemon_copies_prompt_snapshot_and_prompts_orchestrator(tmp_path, monkeypatch):
    prompt_file = tmp_path / "goal.md"
    prompt_file.write_text("Original user goal: validate Stonecore.", encoding="utf-8")
    state = initial_state()
    calls = []
    last_message = tmp_path / "orchestrator.last_message.md"

    def fake_run_codex_role(**kwargs):
        calls.append(kwargs)
        last_message.write_text(
            json.dumps({"status": "continue", "summary": "made progress", "progress_artifacts": ["progress.json"]}),
            encoding="utf-8",
        )
        return {
            "rate_limit": None,
            "returncode": 0,
            "thread_id": "thread-1",
            "jsonl_path": tmp_path / "orchestrator.jsonl",
            "stderr_path": tmp_path / "orchestrator.stderr",
            "last_message_path": last_message,
        }

    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.load_checklist", lambda path=None: {"deliverables": []})
    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.run_codex_role", fake_run_codex_role)

    result = run_one_cycle(
        state,
        {
            "repo": str(tmp_path),
            "orchestrator_model": "gpt-5",
            "sandbox": "danger-full-access",
            "prompt_file": str(prompt_file),
            "runs_dir": str(tmp_path / "runs"),
        },
        tmp_path / "state.json",
    )

    snapshot = tmp_path / "runs" / "000001" / "orchestrator_prompt.md"
    assert result == {"done": False, "status": "continue"}
    assert snapshot.read_text(encoding="utf-8") == "Original user goal: validate Stonecore."
    assert state["prompt_file"] == str(prompt_file)
    assert state["prompt_snapshot_path"] == str(snapshot)
    assert state["prompt_hash"]
    assert "Original user goal: validate Stonecore." in calls[0]["prompt"]
    assert "Previous run artifacts" in calls[0]["prompt"]
    assert "Checklist summary" in calls[0]["prompt"]
    assert "Worktree cleanup requirement" in calls[0]["prompt"]
    assert "Commit useful finished changes" in calls[0]["prompt"]
    assert "Discard only changes you made in this pass" in calls[0]["prompt"]
    assert "Starting git status snapshot" in calls[0]["prompt"]
    assert "Worker model routing requirement" in calls[0]["prompt"]
    assert "assign the worker task complexity as simple, medium, or large" in calls[0]["prompt"]
    assert "Worker model catalog" in calls[0]["prompt"]
    assert "Worker model tier defaults" in calls[0]["prompt"]
    assert "gpt-5.3-codex-spark" in calls[0]["prompt"]
    assert "gpt-5.6-sol" in calls[0]["prompt"]
    assert "gpt-5.6-terra" in calls[0]["prompt"]
    assert "gpt-5.6-luna" in calls[0]["prompt"]
    assert "model_reasoning_effort" in calls[0]["prompt"]
    assert "record the chosen complexity, model, and reasoning effort" in calls[0]["prompt"]


def test_bot_autonomy_daemon_complete_result_marks_goal_complete(tmp_path, monkeypatch):
    state = initial_state()
    last_message = tmp_path / "orchestrator.last_message.md"

    def fake_run_codex_role(**kwargs):
        last_message.write_text(
            json.dumps({"status": "complete", "summary": "done", "progress_artifacts": ["final.json"]}),
            encoding="utf-8",
        )
        return {
            "rate_limit": None,
            "returncode": 0,
            "thread_id": "thread-complete",
            "jsonl_path": tmp_path / "orchestrator.jsonl",
            "stderr_path": tmp_path / "orchestrator.stderr",
            "last_message_path": last_message,
        }

    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.load_checklist", lambda path=None: {"deliverables": []})
    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.run_codex_role", fake_run_codex_role)

    result = run_one_cycle(
        state,
        {
            "repo": str(tmp_path),
            "orchestrator_model": "gpt-5",
            "sandbox": "danger-full-access",
            "runs_dir": str(tmp_path / "runs"),
        },
        tmp_path / "state.json",
    )

    assert result == {"done": True, "status": "complete"}
    assert state["status"] == "complete"
    assert state["goal_complete"] is True
    assert state["latest_orchestrator_result"]["status"] == "complete"
    assert state["last_completed_cycle_id"] == 1


def test_bot_autonomy_daemon_continue_does_not_run_deprecated_validation(tmp_path, monkeypatch):
    state = initial_state()
    last_message = tmp_path / "orchestrator.last_message.md"

    def fake_run_codex_role(**kwargs):
        last_message.write_text(
            json.dumps({"status": "continue", "summary": "workers handled it", "progress_artifacts": ["worker.marker"]}),
            encoding="utf-8",
        )
        return {
            "rate_limit": None,
            "returncode": 0,
            "thread_id": "thread-continue",
            "jsonl_path": tmp_path / "orchestrator.jsonl",
            "stderr_path": tmp_path / "orchestrator.stderr",
            "last_message_path": last_message,
        }

    def fail_validation(*args, **kwargs):
        raise AssertionError("daemon must not run validation commands")

    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.load_checklist", lambda path=None: {"deliverables": []})
    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.run_codex_role", fake_run_codex_role)
    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.run_validation_cycle", fail_validation)

    result = run_one_cycle(
        state,
        {
            "repo": str(tmp_path),
            "orchestrator_model": "gpt-5",
            "sandbox": "danger-full-access",
            "runs_dir": str(tmp_path / "runs"),
            "validation_command": "false",
            "validation_plan_command": "false",
            "scenario_report_command": "false",
        },
        tmp_path / "state.json",
    )

    assert result == {"done": False, "status": "continue"}
    assert state["latest_orchestrator_result"]["progress_artifacts"] == ["worker.marker"]


def test_bot_autonomy_daemon_non_rate_orchestrator_failure_is_recorded(tmp_path, monkeypatch):
    state = initial_state()

    def fake_run_codex_role(**kwargs):
        return {
            "rate_limit": None,
            "returncode": 2,
            "thread_id": "thread-failed",
            "jsonl_path": tmp_path / "orchestrator.jsonl",
            "stderr_path": tmp_path / "orchestrator.stderr",
            "last_message_path": tmp_path / "orchestrator.last_message.md",
        }

    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.load_checklist", lambda path=None: {"deliverables": []})
    monkeypatch.setattr("tools.bot_ml.orchestrator_daemon.run_codex_role", fake_run_codex_role)

    result = run_one_cycle(
        state,
        {
            "repo": str(tmp_path),
            "orchestrator_model": "gpt-5",
            "sandbox": "danger-full-access",
            "runs_dir": str(tmp_path / "runs"),
        },
        tmp_path / "state.json",
    )

    assert result == {"done": False, "error": "orchestrator_failed", "returncode": 2}
    assert state["status"] == "running"
    assert state["phase"] == "orchestrator_failed"
    assert state["latest_orchestrator_result"]["returncode"] == 2
    assert state["consecutive_orchestrator_failures"] == 1


def test_live_bot_validation_completion_watchdog_writes_heartbeats(tmp_path):
    fake_worldserver = tmp_path / "fake_worldserver.py"
    fake_worldserver.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('TC> ', flush=True)\n"
        "for line in sys.stdin:\n"
        "    cmd = line.strip()\n"
        "    print('CMD ' + cmd)\n"
        "    if cmd == '.botauto status':\n"
        "        print('{\"active_bots\":1,\"target_bots\":1,\"decisions\":1}')\n"
        "    elif cmd.startswith('.botauto diagnose'):\n"
        "        print('{\"diagnosis_schema_version\":1,\"bots\":[{\"identity\":{\"bot_guid\":1},\"snapshot\":{\"decision\":{\"action\":\"wait\"},\"movement\":{\"is_moving\":false,\"distance_moved_since_last_decision\":0}}}]}')\n"
        "    elif cmd.startswith('.botauto trace'):\n"
        "        print('{\"trace_schema_version\":1,\"entries\":[{\"action\":\"repeated_decision\"},{\"action\":\"repeated_decision\"}]}')\n"
        "    elif cmd == '.botexp summary':\n"
        "        print('{\"duration_minutes\":1,\"decisions\":1}')\n"
        "    elif cmd.startswith('server shutdown'):\n"
        "        break\n"
        "    print('TC> ', flush=True)\n",
        encoding="utf-8",
    )
    fake_worldserver.chmod(0o755)
    config = tmp_path / "worldserver.conf"
    config.write_text("", encoding="utf-8")

    output, returncode, timed_out, command = run_worldserver_completion_watchdog(
        fake_worldserver,
        config,
        5,
        command_script(selector="all", trace_limit=5, start=False, stop=False),
        tmp_path / "validation",
        {},
        {},
        heartbeat_sec=1,
        no_progress_window_sec=1,
        max_repeated_decisions=2,
    )
    report = json.loads((tmp_path / "validation" / "report.json").read_text(encoding="utf-8"))

    assert returncode == 0
    assert timed_out is False
    assert command == [str(fake_worldserver), "--config", str(config)]
    assert "CMD .botauto status" in output
    assert (tmp_path / "validation" / "heartbeat_events.jsonl").exists()
    assert list((tmp_path / "validation" / "heartbeats").glob("*.json"))
    assert report["duration_policy"] == "completion-watchdog"
    assert report["completion_reason"] == "repeated_decision_watchdog"


def test_completion_watchdog_does_not_stop_manifest_run_on_first_route_segment(tmp_path):
    fake_worldserver = tmp_path / "fake_worldserver.py"
    fake_worldserver.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('TC> ', flush=True)\n"
        "for line in sys.stdin:\n"
        "    cmd = line.strip()\n"
        "    print('CMD ' + cmd)\n"
        "    if cmd == '.botauto status':\n"
        "        print('{\"active_bots\":5,\"target_bots\":5,\"decisions\":20}')\n"
        "    elif cmd.startswith('.botauto diagnose'):\n"
        "        print('{\"diagnosis_schema_version\":1,\"bots\":[{\"identity\":{\"bot_guid\":1},\"snapshot\":{\"decision\":{\"action\":\"validation_route_trash_action\"},\"movement\":{\"is_moving\":false,\"distance_moved_since_last_decision\":2}}}]}')\n"
        "    elif cmd.startswith('.botauto trace'):\n"
        "        print('{\"trace_schema_version\":1,\"entries\":[{\"action\":\"trash_action\"},{\"action\":\"validation_route_trash_action\"}]}')\n"
        "    elif cmd == '.botexp summary':\n"
        "        print('{\"duration_minutes\":1,\"decisions\":20}')\n"
        "    elif cmd.startswith('server shutdown'):\n"
        "        break\n"
        "    print('TC> ', flush=True)\n",
        encoding="utf-8",
    )
    fake_worldserver.chmod(0o755)
    config = tmp_path / "worldserver.conf"
    config.write_text("", encoding="utf-8")
    route = {"kind": "trash", "required_evidence": ["pulls"]}

    run_worldserver_completion_watchdog(
        fake_worldserver,
        config,
        5,
        command_script(selector="all", trace_limit=5, start=False, stop=False),
        tmp_path / "validation",
        {},
        {"scenario_id": "stonecore_5n"},
        heartbeat_sec=1,
        no_progress_window_sec=1,
        validation_route=route,
        validation_route_manifest={"schema": "bot_live_validation_route_manifest_v1", "route_count": 2},
    )
    report = json.loads((tmp_path / "validation" / "report.json").read_text(encoding="utf-8"))

    assert report["evidence"]["validation_route_actions"] > 0
    assert report["evidence"]["trash_pulls"] > 0
    assert report["completion_reason"] != "route_segment_complete"
    assert report.get("route_segment_complete") is not True


def test_completion_watchdog_stops_manifest_run_on_semantic_progress_plateau(tmp_path):
    fake_worldserver = tmp_path / "fake_worldserver.py"
    fake_worldserver.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('TC> ', flush=True)\n"
        "for line in sys.stdin:\n"
        "    cmd = line.strip()\n"
        "    print('CMD ' + cmd)\n"
        "    if cmd == '.botauto status':\n"
        "        print('{\"active_bots\":5,\"target_bots\":5,\"decisions\":120,\"kills\":4}')\n"
        "    elif cmd.startswith('.botauto diagnose'):\n"
        "        print('{\"diagnosis_schema_version\":1,\"bots\":[{\"identity\":{\"bot_guid\":1},\"diagnosis\":{\"route_progress\":{\"route\":{\"kind\":\"trash\",\"node_id\":\"stonecore_entry\"},\"target\":{\"entry\":42696,\"guid\":56,\"hp_pct\":0.5},\"no_progress\":{\"count\":0,\"threshold\":20,\"reason\":\"route_target_combat_progress\"}}},\"snapshot\":{\"decision\":{\"action\":\"validation_route_failed\"},\"movement\":{\"is_moving\":false,\"distance_moved_since_last_decision\":0}}}]}')\n"
        "    elif cmd.startswith('.botauto trace'):\n"
        "        print('{\"trace_schema_version\":1,\"entries\":[{\"action\":\"validation_route_failed\",\"result\":\"route_destination_unreachable\"},{\"action\":\"validation_route_failed\",\"result\":\"route_destination_unreachable\"}]}')\n"
        "    elif cmd == '.botexp summary':\n"
        "        print('{\"duration_minutes\":1,\"decisions\":120,\"total_kills\":4}')\n"
        "    elif cmd.startswith('server shutdown'):\n"
        "        break\n"
        "    print('TC> ', flush=True)\n",
        encoding="utf-8",
    )
    fake_worldserver.chmod(0o755)
    config = tmp_path / "worldserver.conf"
    config.write_text("", encoding="utf-8")

    run_worldserver_completion_watchdog(
        fake_worldserver,
        config,
        5,
        command_script(selector="all", trace_limit=5, start=False, stop=False),
        tmp_path / "validation",
        {},
        {"scenario_id": "stonecore_5n"},
        heartbeat_sec=1,
        no_progress_window_sec=1,
        validation_route_manifest={"schema": "bot_live_validation_route_manifest_v1", "route_count": 2},
    )
    report = json.loads((tmp_path / "validation" / "report.json").read_text(encoding="utf-8"))

    assert report["completion_reason"] == "semantic_progress_plateau_watchdog"
    assert report["watchdog_state"]["semantic_progress_plateau"] is True
    assert "semantic_progress_plateau" in report["failure_labels"]
    assert report["all_passed"] is False
    assert report["watchdog_state"]["progress_total"] == 4
    assert report["evidence"]["validation_route_combat_progress_diagnoses"] == 0
    assert report["evidence"]["validation_route_actions"] > 0


def test_completion_watchdog_keeps_manifest_run_alive_while_party_is_moving(tmp_path):
    fake_worldserver = tmp_path / "fake_worldserver.py"
    fake_worldserver.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('TC> ', flush=True)\n"
        "for line in sys.stdin:\n"
        "    cmd = line.strip()\n"
        "    print('CMD ' + cmd)\n"
        "    if cmd == '.botauto status':\n"
        "        print('{\"active_bots\":5,\"target_bots\":5,\"decisions\":120,\"kills\":4}')\n"
        "    elif cmd.startswith('.botauto diagnose'):\n"
        "        print('{\"diagnosis_schema_version\":1,\"bots\":[{\"identity\":{\"bot_guid\":1},\"diagnosis\":{\"route_progress\":{}},\"snapshot\":{\"decision\":{\"action\":\"move_to_validation_route\"},\"movement\":{\"is_moving\":true,\"distance_moved_since_last_decision\":7}}}]}')\n"
        "    elif cmd.startswith('.botauto trace'):\n"
        "        print('{\"trace_schema_version\":1,\"entries\":[{\"action\":\"move_to_validation_route\",\"result\":\"ok\"}]}')\n"
        "    elif cmd == '.botexp summary':\n"
        "        print('{\"duration_minutes\":1,\"decisions\":120,\"total_kills\":4}')\n"
        "    elif cmd.startswith('server shutdown'):\n"
        "        break\n"
        "    print('TC> ', flush=True)\n",
        encoding="utf-8",
    )
    fake_worldserver.chmod(0o755)
    config = tmp_path / "worldserver.conf"
    config.write_text("", encoding="utf-8")

    run_worldserver_completion_watchdog(
        fake_worldserver,
        config,
        3,
        command_script(selector="all", trace_limit=5, start=False, stop=False),
        tmp_path / "validation",
        {},
        {"scenario_id": "stonecore_5n"},
        heartbeat_sec=1,
        no_progress_window_sec=1,
        validation_route_manifest={"schema": "bot_live_validation_route_manifest_v1", "route_count": 2},
    )
    report = json.loads((tmp_path / "validation" / "report.json").read_text(encoding="utf-8"))

    assert report["completion_reason"] != "semantic_progress_plateau_watchdog"
    assert report["watchdog_state"]["progress_counters"]["moved_diagnoses"] > 0


def test_bounded_console_deadline_caps_command_read_to_heartbeat_window():
    long_deadline = time.monotonic() + 120
    bounded = bounded_console_deadline(long_deadline, 2)

    remaining = bounded - time.monotonic()
    assert 0 < remaining <= 2.5
    assert bounded < long_deadline


def test_live_bot_validation_main_preserves_watchdog_report(tmp_path, monkeypatch, capsys):
    fake_worldserver = tmp_path / "fake_worldserver.py"
    fake_worldserver.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('TC> ', flush=True)\n"
        "for line in sys.stdin:\n"
        "    cmd = line.strip()\n"
        "    print('CMD ' + cmd)\n"
        "    if cmd == '.botauto status':\n"
        "        print('{\"active_bots\":1,\"target_bots\":1,\"decisions\":1}')\n"
        "    elif cmd.startswith('.botauto diagnose'):\n"
        "        print('{\"diagnosis_schema_version\":1,\"bots\":[{\"identity\":{\"bot_guid\":1},\"snapshot\":{\"decision\":{\"action\":\"validation_route_hold_anchor\"},\"movement\":{\"is_moving\":false,\"distance_moved_since_last_decision\":0}}}]}')\n"
        "    elif cmd.startswith('.botauto trace'):\n"
        "        print('{\"trace_schema_version\":1,\"entries\":[{\"action\":\"validation_route_regroup\"},{\"action\":\"validation_route_prerequisite\"}]}')\n"
        "    elif cmd == '.botexp summary':\n"
        "        print('{\"duration_minutes\":1,\"decisions\":1}')\n"
        "    elif cmd.startswith('server shutdown'):\n"
        "        break\n"
        "    print('TC> ', flush=True)\n",
        encoding="utf-8",
    )
    fake_worldserver.chmod(0o755)
    config = tmp_path / "worldserver.conf"
    config.write_text("BotWorld.AutoStart = 1\n", encoding="utf-8")
    scenario_dir = tmp_path / "validation_scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "validation_routes.jsonl").write_text(
        json.dumps(
            {
                "scenario_id": "stonecore_5n",
                "route_node_id": "stonecore_entry",
                "label": "entrance packs",
                "kind": "trash",
                "map_id": 725,
                "x": 903.255,
                "y": 985.352,
                "z": 317.198,
                "source_entry": 42696,
                "expected_bot_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "live"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bot-live-validate",
            "--worldserver",
            str(fake_worldserver),
            "--config",
            str(config),
            "--duration-policy",
            "completion-watchdog",
            "--heartbeat-sec",
            "1",
            "--no-progress-window-sec",
            "1",
            "--timeout-sec",
            "5",
            "--validation-scenario-dir",
            str(scenario_dir),
            "--validation-scenario-id",
            "stonecore_5n",
            "--validation-route-node-id",
            "stonecore_entry",
            "--validation-route-kind",
            "trash",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert live_validation_main() == 0
    capsys.readouterr()
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))

    assert report["heartbeat_index"] >= 1
    assert report["evidence"]["validation_route_actions"] > 0
    assert report["config"].endswith("worldserver.validation.conf")
    assert report["base_config"] == str(config)
    assert report["validation_context"]["route_node_id"] == "stonecore_entry"
    assert report["validation_route"]["source_entry"] == 42696


def test_route_segment_complete_accepts_terminal_trash_evidence():
    route = {"kind": "trash", "route_node_id": "stonecore_entry", "route_generation": 1, "required_evidence": ["pulls"]}
    report = {
        "failure_labels": [],
        "evidence": {
            "validation_route_actions": 4,
            "trash_pulls": 1,
            "validation_evidence_counts": {"pulls": 1},
            "route_terminal_evidence": [{"route_node_id": "stonecore_entry", "route_generation": 1}],
        },
        "trace": {"entries": [{"action": "trash_action", "route_node_id": "stonecore_entry", "route_generation": 1}]},
        "progress_counters": {"validation_route_actions": 4, "trash_pulls": 1, "kills": 1},
    }

    assert route_segment_complete(report, route) is True


def test_route_segment_complete_counts_boss_kill_as_pull_evidence():
    output = """
TC> {"active_bots":5,"target_bots":5,"decisions":88}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"move_to_validation_route_assist_target"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"boss_started","result":"ok","route_node_id":"stonecore_corborus","route_generation":1},{"action":"boss_killed","result":"ok","target_id":43438,"route_node_id":"stonecore_corborus","route_generation":1},{"action":"validation_route_terminal","result":"boss_killed","route_node_id":"stonecore_corborus","route_generation":1},{"action":"validation_route_group_heal","result":"assigned_lowest_ally","route_node_id":"stonecore_corborus","route_generation":1},{"action":"validation_target_priority","result":"assist_tank_focus","route_node_id":"stonecore_corborus","route_generation":1},{"action":"move_to_validation_route_assist_target","result":"ok","route_node_id":"stonecore_corborus","route_generation":1}]}
TC> {"duration_minutes":2,"decisions":88}
"""
    report = live_validation_report(output, validation_context={"route_kind": "boss", "route_node_id": "stonecore_corborus", "route_generation": 1})
    route = {"kind": "boss", "route_node_id": "stonecore_corborus", "route_generation": 1, "required_evidence": ["pulls", "tank_positioning", "healer_assignments", "target_priority"]}

    assert report["evidence"]["boss_kill_evidence"] == 1
    assert report["evidence"]["validation_evidence_counts"]["pulls"] >= 1
    assert route_segment_complete(report, route) is True


def test_route_segment_complete_ignores_transient_failure_after_exact_boss_terminal():
    route = {"kind": "boss", "route_node_id": "stonecore_corborus", "route_generation": 2, "required_evidence": []}
    report = {
        "failure_labels": ["no_progress_observed"],
        "evidence": {
            "route_terminal_evidence": [{"route_node_id": "stonecore_corborus", "route_generation": 2}],
            "real_boss_kill_evidence": [{"route_node_id": "stonecore_corborus", "route_generation": 2}],
        },
        "trace": {"entries": []},
    }

    assert route_segment_complete(report, route) is True


def test_exact_route_terminal_supersedes_transient_failure_labels():
    report = {
        "failure_labels": ["no_progress_observed", "semantic_progress_plateau"],
        "superseded_failure_labels": ["boss_attempt_no_kill"],
        "failure_reason": "no_progress_observed",
    }

    supersede_transient_route_failures(report)

    assert report["failure_labels"] == []
    assert report["superseded_failure_labels"] == [
        "boss_attempt_no_kill",
        "no_progress_observed",
        "semantic_progress_plateau",
    ]
    assert report["failure_reason"] is None


def test_watchdog_state_calls_route_actions_without_route_progress_no_progress():
    state = watchdog_state(
        {
            "decisions": 85,
            "validation_route_actions": 16,
            "action_counts": {"validation_route_regroup": 9, "validation_route_hold_anchor": 7},
        },
        ["validation_route_no_engagement", "no_progress_observed"],
        no_progress_window_sec=60,
    )

    assert state["progress_total"] == 0
    assert state["no_progress"] is True
    assert (
        live_validation_report(
            """
TC> {"active_bots":1,"target_bots":5,"action":"botauto_status","decisions":85}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"validation_route_trash_action"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"validation_route_trash_action","result":"ok"}]}
TC> {"duration_minutes":2,"decisions":85}
"""
        )["completion_reason"]
        == "no_progress_observed"
    )


def test_watchdog_state_counts_active_boss_engagement_as_progress():
    state = watchdog_state(
        {
            "decisions": 900,
            "kills": 40,
            "boss_engagement_actions": 75,
            "validation_route_actions": 600,
            "validation_route_combat_progress_diagnoses": 12,
        },
        [],
        no_progress_window_sec=180,
    )

    assert state["progress_total"] == 127
    assert state["semantic_progress_plateau"] is False


def test_watchdog_state_calls_post_segment_route_plateau_no_progress():
    state = watchdog_state(
        {
            "decisions": 1151,
            "kills": 4,
            "validation_route_actions": 932,
            "action_counts": {"validation_route_failed": 198},
        },
        [],
        no_progress_window_sec=180,
    )

    assert state["progress_total"] == 4
    assert state["semantic_progress_plateau"] is True
    assert state["no_progress"] is False


def test_watchdog_state_does_not_count_a_combat_health_baseline_as_progress():
    report = live_validation_report(
        """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":480,"kills":3}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"diagnosis":{"diagnosis_code":"normal_combat","route_progress":{"route":{"kind":"trash","node_id":"crystalspawn_corridor"},"target":{"entry":42810,"hp_pct":0.515305,"best_hp_pct":0.515305},"no_progress":{"count":0,"threshold":20,"reason":"route_target_combat_progress"}}},"snapshot":{"decision":{"action":"validation_route_trash_action"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0},"route_progress":{"route":{"kind":"trash","node_id":"crystalspawn_corridor"},"target":{"entry":42810,"hp_pct":0.515305,"best_hp_pct":0.515305},"no_progress":{"count":0,"threshold":20,"reason":"route_target_combat_progress"}}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"validation_route_trash_action","result":"ok"}]}
TC> {"duration_minutes":3,"decisions":480,"total_kills":3}
"""
    )

    assert report["evidence"]["validation_route_combat_progress_diagnoses"] == 0
    assert report["watchdog_state"]["progress_total"] == 3
    assert report["watchdog_state"]["semantic_progress_plateau"] is True
    assert "validation_route_stuck_loop" not in report["failure_labels"]


def boss_health_entry(sequence, health, *, guid=85, node="corborus", generation=2, bot_guid=1):
    return {
        "sequence": sequence,
        "bot_guid": bot_guid,
        "route_progress": {
            "route": {"kind": "boss", "node_id": node, "generation": generation},
            "target": {"entry": 43438, "guid": guid, "hp_pct": health},
            "no_progress": {"reason": "boss_route_no_health_progress"},
        },
    }


def test_boss_health_progress_counts_party_shared_strict_minima_only():
    entries = [boss_health_entry(1, 1.0, bot_guid=bot) for bot in range(1, 6)]
    entries += [boss_health_entry(10 + bot, 0.8, bot_guid=bot) for bot in range(1, 6)]
    entries += [boss_health_entry(20, 0.85), boss_health_entry(21, 0.8), boss_health_entry(22, 0.7)]

    assert boss_route_health_progress(entries) == 2


def test_boss_health_progress_resets_only_for_same_scope_attempt_failures():
    entries = [
        boss_health_entry(1, 1.0),
        boss_health_entry(2, 0.8),
        {"sequence": 3, "action": "raid_wipe", "route_node_id": "other", "route_generation": 2},
        boss_health_entry(4, 0.75),
        {"sequence": 5, "action": "death", "route_node_id": "corborus", "route_generation": 2},
        boss_health_entry(6, 1.0),
        boss_health_entry(7, 0.7),
    ]

    assert boss_route_health_progress(entries) == 3


@pytest.mark.parametrize("action", ["stuck_detected", "guardrail_repath", "objective_target_lost"])
def test_boss_health_progress_does_not_reset_for_ordinary_route_failure(action):
    entries = [
        boss_health_entry(1, 1.0),
        boss_health_entry(2, 0.8),
        {"sequence": 3, "action": action, "route_node_id": "corborus", "route_generation": 2},
        boss_health_entry(4, 0.9),
        boss_health_entry(5, 0.8),
    ]

    assert boss_route_health_progress(entries) == 1


@pytest.mark.parametrize("action", ["death", "repeated_death", "raid_wipe", "instance_reset"])
def test_boss_health_progress_starts_new_attempt_for_explicit_reset(action):
    entries = [
        boss_health_entry(1, 1.0),
        boss_health_entry(2, 0.8),
        {"sequence": 3, "action": action, "route_node_id": "corborus", "route_generation": 2},
        boss_health_entry(4, 0.9),
        boss_health_entry(5, 0.8),
    ]

    assert boss_route_health_progress(entries) == 2


def test_boss_health_progress_handles_safe_full_reset_and_new_target_attempts():
    entries = [
        boss_health_entry(1, 1.0),
        boss_health_entry(2, 0.8),
        boss_health_entry(3, 0.98),
        boss_health_entry(4, 0.7),
        boss_health_entry(5, 1.0, guid=551),
        boss_health_entry(6, 0.6, guid=551),
    ]

    assert boss_route_health_progress(entries) == 3


def test_boss_health_progress_does_not_compare_partial_order_clock_domains():
    timestamp_baseline = boss_health_entry(1, 1.0)
    timestamp_baseline["timestamp_ms"] = 100
    timestamp_baseline.pop("sequence")

    assert boss_route_health_progress([timestamp_baseline, boss_health_entry(2, 0.5)]) == 0


def test_run037_boss_health_regression_preserves_progress_across_wipe_and_new_spawn():
    entries = [
        boss_health_entry(1, 0.98),
        boss_health_entry(2, 0.92),
        boss_health_entry(3, 0.64),
        boss_health_entry(4, 0.586),
        {"sequence": 5, "action": "raid_wipe", "route_node_id": "corborus", "route_generation": 2},
        boss_health_entry(6, 1.0, guid=551),
        boss_health_entry(7, 0.739, guid=551),
        boss_health_entry(8, 0.665, guid=551),
    ]
    output = "\n".join(
        [
            'TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":628,"kills":20}',
            "TC> " + json.dumps({"trace_schema_version": 1, "entries": entries}),
            'TC> {"duration_minutes":15,"decisions":628,"total_kills":20}',
        ]
    )

    report = live_validation_report(output)

    assert report["evidence"]["validation_route_combat_progress_diagnoses"] == 5
    assert report["watchdog_state"]["semantic_progress_plateau"] is False


def route_death_loop_entry(sequence, *, action="repeated_death", node="corborus", generation=2, bot_guid=1):
    return {
        "sequence": sequence,
        "bot_guid": bot_guid,
        "action": action,
        "route_node_id": node,
        "route_generation": generation,
    }


def test_unresolved_route_death_loop_requires_durable_progress_not_resurrection():
    entries = []
    for sequence in (1, 3, 5):
        entries.extend(
            [
                route_death_loop_entry(sequence),
                route_death_loop_entry(sequence + 1, action="resurrected"),
            ]
        )

    assert unresolved_route_death_loop_count(entries) == 3


def test_unsequenced_repeated_deaths_remain_distinct_and_fail_closed():
    repeated = {
        "bot_guid": 1,
        "action": "repeated_death",
        "route_node_id": "corborus",
        "route_generation": 2,
    }
    entries = [dict(repeated), dict(repeated), dict(repeated)]
    output = "\n".join(
        [
            'TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":20}',
            'TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"validation_route_hold_anchor"},"movement":{"is_moving":false}}}]}',
            "TC> " + json.dumps({"trace_schema_version": 1, "entries": [{"action": "validation_route_regroup", "route_node_id": "corborus", "route_generation": 2}, *entries]}),
            'TC> {"duration_minutes":1,"decisions":20}',
        ]
    )

    report = live_validation_report(output)

    assert unresolved_route_death_loop_count(entries) == 3
    assert report["evidence"]["unresolved_route_death_loop_events"] == 3
    assert "validation_route_death_loop" in report["failure_labels"]
    assert report["watchdog_state"]["death_loop"] is True


@pytest.mark.parametrize("action", ["boss_add_killed", "mob_killed", "validation_route_pack_terminal", "validation_route_terminal", "validation_route_segment_advance"])
def test_scoped_route_progress_resolves_repeated_death_loop(action):
    entries = [route_death_loop_entry(sequence) for sequence in (1, 2, 3)]
    entries.append(route_death_loop_entry(4, action=action))

    assert unresolved_route_death_loop_count(entries) == 0


def test_strict_boss_health_progress_resolves_repeated_death_loop():
    entries = [route_death_loop_entry(sequence) for sequence in (1, 2, 3)]
    entries += [boss_health_entry(4, 0.5), boss_health_entry(5, 0.4)]

    assert unresolved_route_death_loop_count(entries) == 0


def test_wrong_scope_and_incomparable_progress_do_not_resolve_death_loop():
    entries = [route_death_loop_entry(sequence) for sequence in (1, 2, 3)]
    entries.append(route_death_loop_entry(4, action="boss_add_killed", node="slabhide"))
    timestamp_baseline = boss_health_entry(0, 0.5)
    timestamp_progress = boss_health_entry(0, 0.4)
    timestamp_baseline.update(timestamp_ms=10)
    timestamp_progress.update(timestamp_ms=20)
    entries += [timestamp_baseline, timestamp_progress]

    assert unresolved_route_death_loop_count(entries) == 3


def test_run040_resolved_historical_deaths_do_not_stop_active_boss_attempt():
    entries = [boss_health_entry(1, 0.544041)]
    entries += [route_death_loop_entry(sequence, action="death", bot_guid=sequence) for sequence in range(2, 6)]
    entries += [route_death_loop_entry(sequence, action="resurrected", bot_guid=sequence - 4) for sequence in range(6, 10)]
    entries += [boss_health_entry(10, 0.4), boss_health_entry(11, 0.2), boss_health_entry(12, 0.0462236)]
    entries += [route_death_loop_entry(sequence, action="death", bot_guid=sequence - 12) for sequence in range(13, 18)]
    entries.append(route_death_loop_entry(18, bot_guid=1))
    entries += [route_death_loop_entry(sequence, action="resurrected", bot_guid=sequence - 18) for sequence in range(19, 24)]
    for entry in entries:
        if entry.get("route_progress"):
            entry["action"] = "validation_route_boss_action"
    output = "\n".join(
        [
            'TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":2348,"kills":23,"deaths":9}',
            'TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"validation_route_group_heal"},"movement":{"is_moving":false}}}]}',
            "TC> " + json.dumps({"trace_schema_version": 1, "entries": entries}),
            'TC> {"duration_minutes":8,"decisions":2348,"total_kills":23,"total_deaths":9}',
        ]
    )

    report = live_validation_report(output)

    assert report["evidence"]["unresolved_route_death_loop_events"] == 1
    assert report["watchdog_state"]["progress_counters"]["death_loop_events"] == 1
    assert report["watchdog_state"]["death_loop"] is False
    assert "validation_route_death_loop" not in report["failure_labels"]
    assert report["completion_reason"] != "machine_failure_predicate"


def test_live_bot_validation_treats_terminal_route_no_progress_diagnosis_as_watchdog_failure():
    output = """
TC> {"active_bots":5,"target_bots":5,"action":"botauto_status","decisions":517,"kills":0,"quests_accepted":0,"quest_objective_progress":0}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"diagnosis":{"diagnosis_code":"repeated_decision_loop","route_progress":{"route":{"kind":"trash","node_id":"stonecore_entry"},"target":{"entry":42696,"hp_pct":0.00664742,"best_hp_pct":0.00664742},"no_progress":{"count":20,"threshold":20,"reason":"validation_trash_no_progress"}}},"snapshot":{"decision":{"action":"validation_route_failed"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0},"route_progress":{"route":{"kind":"trash","node_id":"stonecore_entry"},"target":{"entry":42696,"hp_pct":0.00664742,"best_hp_pct":0.00664742},"no_progress":{"count":20,"threshold":20,"reason":"validation_trash_no_progress"}}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"trash_action","result":"ok"},{"action":"validation_route_trash_action","result":"ok"},{"action":"validation_route_failed","result":"validation_trash_no_progress"}]}
TC> {"duration_minutes":5,"decisions":517,"total_kills":0,"quests_completed":0}
"""
    report = live_validation_report(output)

    assert report["evidence"]["validation_route_no_progress_diagnoses"] == 1
    assert "no_progress_observed" in report["failure_labels"]
    assert report["watchdog_state"]["progress_total"] == 0
    assert report["watchdog_state"]["no_progress"] is True


def test_live_bot_validation_keeps_route_progress_incomplete_until_watchdog_expires():
    output = """
TC> {"active_bots":5,"target_bots":5,"decisions":25}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"move_to_validation_route"},"movement":{"is_moving":true,"distance_moved_since_last_decision":91}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"move_to_validation_route","result":"ok"},{"action":"validation_route_regroup","result":"advance_to_boss_route_no_focus"}]}
TC> {"duration_minutes":1,"decisions":25}
"""
    report = live_validation_report(output, validation_context={"route_kind": "boss"})

    assert "validation_route_no_engagement" in report["failure_labels"]
    assert report["watchdog_state"]["progress_total"] == 0
    assert report["watchdog_state"]["no_progress"] is False
    assert report["completion_reason"] == "incomplete_evidence"


def test_live_bot_validation_keeps_moving_assist_focus_loop_incomplete():
    output = """
TC> {"active_bots":5,"target_bots":5,"decisions":44}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"move_to_validation_route_assist_target"},"movement":{"is_moving":true,"distance_moved_since_last_decision":70}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"validation_route_target_search","result":"assist_tank_focus"},{"action":"validation_target_priority","result":"assist_tank_focus"},{"action":"validation_route_prerequisite_rejected","result":"force_tank_focus"},{"action":"move_to_validation_route_assist_target","result":"ok"},{"action":"validation_route_target_search","result":"assist_tank_focus"},{"action":"validation_target_priority","result":"assist_tank_focus"},{"action":"validation_route_prerequisite_rejected","result":"force_tank_focus"},{"action":"move_to_validation_route_assist_target","result":"ok"},{"action":"validation_route_target_search","result":"assist_tank_focus"},{"action":"validation_target_priority","result":"assist_tank_focus"},{"action":"validation_route_prerequisite_rejected","result":"force_tank_focus"},{"action":"move_to_validation_route_assist_target","result":"ok"},{"action":"validation_route_target_search","result":"assist_tank_focus"},{"action":"validation_target_priority","result":"assist_tank_focus"},{"action":"validation_route_prerequisite_rejected","result":"force_tank_focus"},{"action":"move_to_validation_route_assist_target","result":"ok"}]}
TC> {"duration_minutes":1,"decisions":44}
"""
    report = live_validation_report(output, validation_context={"route_kind": "trash"})

    assert "validation_route_assist_focus_loop" in report["failure_labels"]
    assert report["watchdog_state"]["no_progress"] is False
    assert report["completion_reason"] == "incomplete_evidence"


def test_watchdog_state_treats_boss_engagement_without_kill_as_no_progress():
    state = watchdog_state(
        {
            "decisions": 60,
            "moved_diagnoses": 1,
            "validation_route_actions": 12,
            "boss_engagement_actions": 8,
            "action_counts": {"boss_action": 4, "boss_started": 4},
        },
        ["boss_attempt_no_kill", "no_progress_observed"],
        no_progress_window_sec=60,
    )

    assert state["progress_total"] == 0
    assert state["no_progress"] is True


def test_live_bot_validation_route_sequence_dry_run_writes_ordered_child_commands(tmp_path, monkeypatch, capsys):
    scenario_dir = tmp_path / "validation_scenarios"
    scenario_dir.mkdir()
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [
            {
                "scenario_id": "stonecore_5n",
                "route_node_id": "stonecore_entry",
                "step": 1,
                "kind": "trash",
                "label": "entrance packs",
                "coordinates_valid": True,
            },
            {
                "scenario_id": "stonecore_5n",
                "route_node_id": "stonecore_corborus",
                "step": 2,
                "kind": "boss",
                "label": "Corborus",
                "mechanic_profile": "burrow_adds_ground_danger",
                "coordinates_valid": True,
            },
            {
                "scenario_id": "stonecore_5n",
                "route_node_id": "stonecore_missing",
                "step": 3,
                "kind": "boss",
                "label": "missing",
                "coordinates_valid": False,
            },
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bot-live-validate",
            "--dry-run",
            "--validation-route-sequence",
            "--validation-scenario-id",
            "stonecore_5n",
            "--validation-scenario-dir",
            str(scenario_dir),
            "--output-dir",
            str(tmp_path / "live"),
        ],
    )

    assert live_validation_main() == 0
    capsys.readouterr()
    report = json.loads((tmp_path / "live" / "report.json").read_text(encoding="utf-8"))
    commands = (tmp_path / "live" / "commands.txt").read_text(encoding="utf-8")

    assert report["route_sequence"]["route_count"] == 2
    assert report["route_sequence"]["expected_segments"] == ["01_entrance_packs", "02_corborus"]
    assert "--validation-segment-id' '01_entrance_packs" in commands
    assert "--validation-route-node-id' 'stonecore_corborus" in commands
    assert "stonecore_missing" not in commands


def test_live_bot_validation_config_writes_alternate_route_targets(tmp_path):
    base_config = tmp_path / "worldserver.conf"
    base_config.write_text("BotWorld.AutoStart = 0\n", encoding="utf-8")
    generated = write_validation_config(
        base_config,
        tmp_path / "live",
        validation_route={
            "scenario_id": "blackwing_descent_10n",
            "route_node_id": "bwd_omnotron",
            "kind": "boss",
            "label": "Omnotron Defense System",
            "mechanic_profile": "target_switch_interrupt_spread",
            "map_id": 669,
            "x": -324.807,
            "y": -418.783,
            "z": 227.6403,
            "source_entry": 42186,
            "alternate_target_entries": [42166, 42178, 42179, 42180, 42166, 0],
            "add_target_entries": [42362, 0],
            "pack_target_entries": [42166],
            "hazard_source_entry": 42187,
            "hazard_detection_spell_id": 79888,
            "hazard_damage_spell_id": 79889,
            "hazard_shape": "radial",
            "hazard_radius_yards": 6.0,
            "hazard_safety_margin_yards": 2.5,
            "cluster_radius_yards": 80.0,
            "expected_bot_count": 10,
        },
    )

    config_text = generated.read_text(encoding="utf-8")
    assert 'BotWorld.RuntimeProfile = ""' in config_text
    assert "BotWorld.ValidationRoute.TargetEntry = 42186" in config_text
    assert 'BotWorld.ValidationRoute.AlternateTargetEntries = "42166,42178,42179,42180"' in config_text
    assert 'BotWorld.ValidationRoute.AddTargetEntries = "42362"' in config_text
    assert 'BotWorld.ValidationRoute.PackTargetEntries = "42166"' in config_text
    assert "BotWorld.ValidationRoute.HazardSourceEntry = 42187" in config_text
    assert "BotWorld.ValidationRoute.HazardDetectionSpellId = 79888" in config_text
    assert "BotWorld.ValidationRoute.HazardDamageSpellId = 79889" in config_text
    assert 'BotWorld.ValidationRoute.HazardShape = "radial"' in config_text
    assert "BotWorld.ValidationRoute.HazardRadiusYards = 6.0" in config_text
    assert "BotWorld.ValidationRoute.HazardSafetyMarginYards = 2.5" in config_text
    assert "BotWorld.ValidationRoute.ClusterRadiusYards = 80.0" in config_text
    assert "BotProgression.AllowDungeons = 1" in config_text


def test_live_bot_validation_config_can_disable_autostart_for_calibration_only(tmp_path):
    base_config = tmp_path / "worldserver.conf"
    base_config.write_text("BotWorld.AutoStart = 1\n", encoding="utf-8")

    generated = write_validation_config(
        base_config,
        tmp_path / "live",
        pool_tag="combat_calibration",
        autostart=False,
    )

    config_text = generated.read_text(encoding="utf-8")
    assert "BotWorld.AutoStart = 0" in config_text
    assert 'BotWorld.PoolTagFilter = "combat_calibration"' in config_text


def test_live_bot_validation_config_calibration_only_starts_empty_controller(tmp_path):
    base_config = tmp_path / "worldserver.conf"
    base_config.write_text(
        'BotWorld.AutoStart = 0\nBotWorld.RuntimeProfile = "stonecore_5n"\n'
        "BotWorld.TargetPopulation = 5\nBotWorld.ValidationRoute.Enable = 1\n",
        encoding="utf-8",
    )

    generated = write_validation_config(
        base_config,
        tmp_path / "live",
        pool_tag="combat_calibration",
        calibration_only=True,
    )

    config_text = generated.read_text(encoding="utf-8")
    assert "BotWorld.AutoStart = 1" in config_text
    assert 'BotWorld.RuntimeProfile = ""' in config_text
    assert "BotWorld.TargetPopulation = 0" in config_text
    assert "BotWorld.ValidationRoute.Enable = 0" in config_text
    assert 'BotWorld.PoolTagFilter = "combat_calibration"' in config_text


def test_live_bot_validation_route_manifest_dry_run_writes_scenario_scoped_config(tmp_path, monkeypatch, capsys):
    scenario_dir = tmp_path / "validation_scenarios"
    scenario_dir.mkdir()
    write_jsonl(
        scenario_dir / "validation_routes.jsonl",
        [
            {
                "scenario_id": "stonecore_5n",
                "route_node_id": "stonecore_entry",
                "step": 1,
                "kind": "trash",
                "label": "entrance packs",
                "map_id": 725,
                "x": 903.255,
                "y": 985.352,
                "z": 317.198,
                "source_entry": 42696,
                "coordinates_valid": True,
                "expected_bot_count": 5,
            },
            {
                "scenario_id": "stonecore_5n",
                "route_node_id": "stonecore_corborus",
                "step": 2,
                "kind": "boss",
                "label": "Corborus",
                "map_id": 725,
                "x": 1120.0,
                "y": 882.0,
                "z": 300.0,
                "source_entry": 43438,
                "coordinates_valid": True,
            },
            {
                "scenario_id": "stonecore_5n",
                "route_node_id": "stonecore_regroup",
                "step": 3,
                "kind": "regroup",
                "label": "post-Slabhide regroup",
                "map_id": 725,
                "x": 1282.7,
                "y": 1229.77,
                "z": 247.155,
                "source_entry": 0,
                "coordinates_valid": True,
                "completion_policy": "arrival",
            },
            {
                "scenario_id": "stonecore_5n",
                "route_node_id": "stonecore_descent",
                "step": 4,
                "kind": "descent",
                "label": "lower stonecore approach regroup",
                "map_id": 725,
                "x": 1339.84,
                "y": 1131.04,
                "z": 214.056,
                "source_entry": 0,
                "coordinates_valid": True,
                "completion_policy": "arrival",
            },
        ],
    )
    base_config = tmp_path / "worldserver.conf"
    base_config.write_text("BotWorld.AutoStart = 1\n", encoding="utf-8")
    output_dir = tmp_path / "live"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bot-live-validate",
            "--dry-run",
            "--config",
            str(base_config),
            "--validation-route-manifest",
            "--validation-scenario-id",
            "stonecore_5n",
            "--validation-scenario-dir",
            str(scenario_dir),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert live_validation_main() == 0
    capsys.readouterr()
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    generated_config = (output_dir / "worldserver.validation.conf").read_text(encoding="utf-8")

    assert report["validation_context"] == {"scenario_id": "stonecore_5n"}
    assert report["validation_route"]["route_node_id"] == "stonecore_entry"
    assert report["validation_route_manifest"]["route_count"] == 4
    assert report["validation_route_manifest"]["expected_segments"] == ["01_entrance_packs", "02_corborus", "03_post_slabhide_regroup", "04_lower_stonecore_approach_regroup"]
    assert report["validation_route_manifest"]["routes"][2]["kind"] == "regroup"
    assert report["validation_route_manifest"]["routes"][2]["completion_policy"] == "arrival"
    assert report["validation_route_manifest"]["routes"][3]["kind"] == "descent"
    assert report["validation_route_manifest"]["routes"][3]["completion_policy"] == "arrival"
    assert Path(report["validation_route_manifest_path"]).name == "validation_route_manifest.json"
    assert "BotWorld.ValidationRoute.ManifestPath" in generated_config
    assert 'BotWorld.RuntimeProfile = ""' not in generated_config
    assert 'BotWorld.ValidationRoute.AdvanceMode = "terminal"' in generated_config
    assert 'BotWorld.ValidationRoute.NodeId = "stonecore_entry"' in generated_config
    assert "BotWorld.TargetPopulation = 5" in generated_config


def test_lane_config_generates_per_lane_db_clones(tmp_path):
    world_template = tmp_path / "worldserver.conf"
    auth_template = tmp_path / "authserver.conf"
    world_template.write_text(
        'LoginDatabaseInfo = "127.0.0.1;3306;trinity;trinity;auth"\n'
        'WorldDatabaseInfo = "127.0.0.1;3306;trinity;trinity;world"\n'
        'CharacterDatabaseInfo = "127.0.0.1;3306;trinity;trinity;characters"\n'
        'HotfixDatabaseInfo = "127.0.0.1;3306;trinity;trinity;hotfixes"\n',
        encoding="utf-8",
    )
    auth_template.write_text("", encoding="utf-8")

    manifest = write_lane_config(
        0,
        tmp_path / "lanes",
        world_template,
        auth_template,
        dry_run=False,
        name_override="stonecore full clear r1",
        db_isolation="per-lane-clone",
    )
    config = Path(manifest["configs"]["worldserver"]).read_text(encoding="utf-8")

    assert manifest["lane_name"] == "stonecore_full_clear_r1"
    assert manifest["databases"]["auth"]["database"] == "auth_lane_stonecore_full_clear_r1"
    assert manifest["databases"]["characters"]["database"] == "characters_lane_stonecore_full_clear_r1"
    assert manifest["databases"]["world"]["database"] == "world_lane_stonecore_full_clear_r1"
    assert manifest["databases"]["hotfixes"]["database"] == "hotfixes_lane_stonecore_full_clear_r1"
    assert 'LoginDatabaseInfo = "127.0.0.1;3306;trinity;trinity;auth_lane_stonecore_full_clear_r1"' in config
    assert 'BotWorld.PoolTagFilter = "bot_autonomy_stonecore_full_clear_r1"' in config
    assert manifest["cleanup_command"]


def test_live_artifact_promotion_requires_accepted_evidence(tmp_path):
    source = tmp_path / "lane" / "report.json"
    canonical = tmp_path / "canonical" / "report.json"
    manifest = tmp_path / "promotion.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"all_passed": False, "acceptable_final_evidence": False}), encoding="utf-8")

    with pytest.raises(SystemExit):
        promote(source, canonical, manifest)

    failed_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    assert failed_manifest["accepted"] is False
    assert not canonical.exists()

    source.write_text(json.dumps({"all_passed": True, "acceptable_final_evidence": True}), encoding="utf-8")
    accepted = promote(source, canonical, manifest)

    assert accepted["accepted"] is True
    assert json.loads(canonical.read_text(encoding="utf-8"))["all_passed"] is True


def test_autonomy_checklist_refreshes_from_stage_and_scenario_evidence(tmp_path):
    lower_report = tmp_path / "artifacts" / "live_validation_quest_mob_assist_150s" / "report.json"
    lower_report.parent.mkdir(parents=True)
    lower_report.write_text(
        json.dumps(
            {
                "schema": "bot_live_validation_report_v1",
                "stages": [
                    {"stage": "movement_smoke", "passed": True, "missing": []},
                    {"stage": "kill_quest", "passed": True, "missing": []},
                    {"stage": "collect_quest", "passed": True, "missing": []},
                    {"stage": "quest_hub_batching", "passed": True, "missing": []},
                    {"stage": "trainer_visit", "passed": True, "missing": []},
                    {"stage": "vendor_repair", "passed": True, "missing": []},
                    {"stage": "profession_recipe_acquisition", "passed": True, "missing": []},
                    {"stage": "material_farming", "passed": True, "missing": []},
                    {"stage": "smart_loot", "passed": True, "missing": []},
                    {"stage": "full_stonecore_clear", "passed": False, "missing": ["stonecore_live_clear_report"]},
                ],
            }
        ),
        encoding="utf-8",
    )
    scenario_root = tmp_path / "scenario_reports"
    scenario_root.mkdir()
    (scenario_root / "stonecore_5n.json").write_text(
        json.dumps(
            {
                "scenario_id": "stonecore_5n",
                "difficulty": "normal_5man",
                "trash_cleared": True,
                "trash_pulls": 8,
                "boss_kills": 4,
                "clear_complete": False,
                "clear_complete_blockers": ["segment_evidence_debug_only", "missing_uninterrupted_full_clear_report"],
            }
        ),
        encoding="utf-8",
    )
    status_path = tmp_path / "validation_run_status" / "manifest.json"
    status_path.parent.mkdir()
    status_path.write_text(
        json.dumps(
            {
                "scenarios": [
                    {
                        "scenario_id": "stonecore_5n",
                        "full_clear_ready": False,
                        "blockers": ["invalid_segment_live_reports", "scenario_clear_not_complete"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    checklist = refresh_checklist_from_evidence(
        evidence_reports=[lower_report],
        validation_status=status_path,
        scenario_report_root=scenario_root,
    )
    rows = {row["deliverable"]: row for row in checklist["deliverables"]}

    assert rows["movement_smoke"]["status"] == "accepted"
    assert rows["smart_loot"]["status"] == "accepted"
    assert rows["normal_dungeon_trash"]["status"] == "review"
    assert rows["normal_dungeon_trash"]["evidence_artifact"] == str(scenario_root / "stonecore_5n.json")
    assert rows["dungeon_boss"]["status"] == "review"
    assert rows["full_stonecore_clear"]["status"] == "needs_followup"
    assert rows["full_stonecore_clear"]["failure_label"] == "segment_evidence_debug_only,missing_uninterrupted_full_clear_report"
    assert checklist["all_passed"] is False


def test_live_bot_validation_requires_activity_evidence_for_smoke_gates():
    output = """
TC> {"active_bots":5,"target_bots":5,"decisions":0,"quests_accepted":0,"quest_objective_progress":0}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"wait"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"entries":[{"action":"bot_spawned","situation":"bot_spawned"}]}
TC> {"duration_minutes":0,"decisions":0,"total_kills":0,"quests_completed":0}
"""
    report = live_validation_report(output)
    gates = {stage["stage"]: stage for stage in report["stages"]}

    assert report["evidence"]["active_decision_evidence"] is False
    assert gates["movement_smoke"]["passed"] is False
    assert "active_decision_or_movement_evidence" in gates["movement_smoke"]["missing"]
    assert "kill_evidence" in gates["kill_quest"]["missing"]
    assert "quest_progress_evidence" in gates["collect_quest"]["missing"]


def test_live_bot_validation_labels_route_death_loop():
    output = """
TC> {"active_bots":10,"target_bots":10,"decisions":20,"deaths":12}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"diagnosis":{"diagnosis_code":"dead_recovery","severity":"warning"},"snapshot":{"decision":{"action":"validation_route_hold_anchor"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"entries":[{"sequence":1,"action":"validation_route_regroup","route_node_id":"boss","route_generation":1},{"sequence":2,"action":"death","route_node_id":"boss","route_generation":1},{"sequence":3,"action":"repeated_death","route_node_id":"boss","route_generation":1},{"sequence":4,"action":"resurrected","route_node_id":"boss","route_generation":1},{"sequence":5,"action":"repeated_death","route_node_id":"boss","route_generation":1},{"sequence":6,"action":"resurrected","route_node_id":"boss","route_generation":1},{"sequence":7,"action":"death_loop","route_node_id":"boss","route_generation":1}]}
TC> {"duration_minutes":5,"decisions":20,"total_kills":0,"total_deaths":12}
"""
    report = live_validation_report(output)

    assert "validation_route_death_loop" in report["failure_labels"]
    assert report["evidence"]["unresolved_route_death_loop_events"] == 3
    assert report["watchdog_state"]["progress_counters"]["death_loop_events"] == 3
    assert report["watchdog_state"]["death_loop"] is True
    assert report["completion_reason"] == "death_loop_watchdog"


def test_live_bot_validation_counts_multi_bot_trace_entries():
    output = """
TC> {"active_bots":2,"target_bots":2,"decisions":0,"quests_accepted":0,"quest_objective_progress":0}
TC> {"diagnosis_schema_version":1,"bots":[{"identity":{"bot_guid":1},"snapshot":{"decision":{"action":"travel_to_quest_hub"},"movement":{"is_moving":true,"distance_moved_since_last_decision":4.5}}},{"identity":{"bot_guid":2},"snapshot":{"decision":{"action":"use_quest_object"},"movement":{"is_moving":false,"distance_moved_since_last_decision":0}}}]}
TC> {"trace_schema_version":1,"selector":"all","bots":[{"bot_guid":1,"entries":[{"action":"bot_spawned","situation":"bot_spawned"},{"action":"travel_to_quest_hub","situation":"quest_pickup_search"},{"action":"accept_hub_quests","situation":"quest_hub_sweep"},{"action":"accept_quest_db_fallback","situation":"quest_pickup_search"},{"action":"complete_quest_db_fallback","situation":"quest_turn_in"}]},{"bot_guid":2,"entries":[{"action":"use_quest_object","situation":"quest_objective","result":"failed"}]}]}
TC> {"duration_minutes":1,"decisions":0,"total_kills":0,"quests_completed":0}
"""
    report = live_validation_report(output)
    gates = {stage["stage"]: stage for stage in report["stages"]}

    assert report["trace_entries"] == 6
    assert report["evidence"]["non_spawn_trace_entries"] == 5
    assert report["evidence"]["quests_accepted"] == 2
    assert report["evidence"]["hub_acceptance_actions"] == 1
    assert report["evidence"]["quests_completed"] == 1
    assert report["evidence"]["active_decision_evidence"] is True
    assert "accept_quest_db_fallback" in report["evidence"]["action_names"]
    assert "complete_quest_db_fallback" in report["evidence"]["action_names"]
    assert "travel_to_quest_hub" in report["evidence"]["action_names"]
    assert "use_quest_object" in report["evidence"]["action_names"]
    assert gates["movement_smoke"]["passed"] is True
    assert gates["collect_quest"]["passed"] is True
    assert gates["quest_hub_batching"]["passed"] is True


def test_live_bot_validation_dry_run_writes_command_file(tmp_path, monkeypatch):
    scenario_dir = tmp_path / "validation_scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "validation_routes.jsonl").write_text(
        json.dumps(
            {
                "scenario_id": "blackwing_descent_10n",
                "route_node_id": "bwd_magmaw",
                "step": 2,
                "label": "Magmaw",
                "kind": "boss",
                "mechanic_profile": "magmaw",
                "map_id": 669,
                "x": -302.467,
                "y": -31.7101,
                "z": 210.8483,
                "o": 4.118977,
                "navigation_anchor_x": -305.0,
                "navigation_anchor_y": -30.0,
                "navigation_anchor_z": 211.0,
                "navigation_anchor_o": 4.0,
                "source_entry": 41570,
                "expected_bot_count": 10,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-live-validate",
            "--dry-run",
            "--selector",
            "all",
            "--trace-limit",
            "7",
            "--validation-scenario-id",
            "blackwing_descent_10n",
            "--validation-segment-id",
            "02_magmaw",
            "--validation-route-node-id",
            "bwd_magmaw",
            "--validation-route-label",
            "Magmaw",
            "--validation-route-kind",
            "boss",
            "--validation-route-step",
            "2",
            "--validation-mechanic-profile",
            "magmaw",
            "--validation-scenario-dir",
            str(scenario_dir),
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert live_validation_main() == 0
    commands = (tmp_path / "commands.txt").read_text(encoding="utf-8")
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))

    assert ".botauto diagnose all" in commands
    assert ".botauto trace all 7" in commands
    assert ".botauto start" not in commands
    assert "server shutdown force 0" in commands
    assert report["dry_run"] is True
    assert report["command_script"] == commands
    assert report["validation_context"] == {
        "scenario_id": "blackwing_descent_10n",
        "segment_id": "02_magmaw",
        "route_node_id": "bwd_magmaw",
        "route_label": "Magmaw",
        "route_kind": "boss",
        "route_step": 2,
        "route_generation": 1,
        "mechanic_profile": "magmaw",
    }
    assert report["config_autostart"] is True
    assert report["start_command"] is False
    assert report["pool_tag_filter"] == "blackwing_descent_10n"
    assert report["validation_route"]["route_node_id"] == "bwd_magmaw"
    assert report["validation_route"]["source_entry"] == 41570
    assert report["config"].endswith("worldserver.validation.conf")
    generated_config = (tmp_path / "worldserver.validation.conf").read_text(encoding="utf-8")
    assert 'BotWorld.PoolTagFilter = "blackwing_descent_10n"' in generated_config
    assert "BotWorld.ValidationRoute.Enable = 1" in generated_config
    assert "BotWorld.TargetPopulation = 10" in generated_config
    assert 'BotWorld.ValidationRoute.NodeId = "bwd_magmaw"' in generated_config
    assert "BotWorld.ValidationRoute.X = -305.0" in generated_config
    assert "BotWorld.ValidationRoute.Y = -30.0" in generated_config
    assert "BotWorld.ValidationRoute.Z = 211.0" in generated_config
    assert "BotWorld.ValidationRoute.O = 4.0" in generated_config
    assert "BotWorld.ValidationRoute.TargetEntry = 41570" in generated_config
    assert "BotWorld.ValidationRoute.OpenerTargetEntry = 0" in generated_config
    assert "BotWorld.ValidationRoute.ActivationSpawnGroupId = 0" in generated_config
    assert "BotWorld.ValidationRoute.ActivationActionEntry = 0" in generated_config
    assert "BotWorld.ValidationRoute.ActivationActionId = 0" in generated_config
    assert "BotWorld.ValidationRoute.OpenerSummonEntry = 0" in generated_config
    assert "BotWorld.SafePositionMemorySec = 900" in generated_config
    assert "BotProgression.AllowDungeons = 1" in generated_config


def test_upsert_trinity_config_normalizes_literal_newline_fragments():
    text = 'BotWorld.DeathRecoveryMode = "safe_local"\\nBotWorld.RespawnMode = "safe_local"\n'

    generated = upsert_trinity_config(text, "BotWorld.ValidationRoute.Enable", "1")

    assert "\\n" not in generated
    assert 'BotWorld.DeathRecoveryMode = "safe_local"\nBotWorld.RespawnMode = "safe_local"' in generated
    assert "BotWorld.ValidationRoute.Enable = 1" in generated


def test_read_until_console_prompt_waits_for_prompt_after_required_marker(monkeypatch):
    process = ChunkedConsoleProcess(["TC> ", 'CMD .botauto status\n{"target_bots": 1}\n', "TC> "])
    module_globals = read_until_console_prompt.__globals__
    monkeypatch.setattr(module_globals["select"], "select", lambda fds, *_args: (fds if process.chunks else [], [], []))
    monkeypatch.setattr(module_globals["os"], "read", lambda _fd, _size: process.chunks.pop(0))

    output = read_until_console_prompt(process, time.monotonic() + 1, '"target_bots"')

    assert output.endswith("TC> ")


def test_read_until_console_prompt_does_not_complete_on_required_marker_alone(monkeypatch):
    process = ChunkedConsoleProcess(['{"target_bots": 1}\n', "more command output\n"])
    module_globals = read_until_console_prompt.__globals__
    monkeypatch.setattr(module_globals["select"], "select", lambda fds, *_args: (fds if process.chunks else [], [], []))
    monkeypatch.setattr(module_globals["os"], "read", lambda _fd, _size: process.chunks.pop(0))

    output = read_until_console_prompt(process, time.monotonic() + 1, '"target_bots"')

    assert output.endswith("more command output\n")


def test_read_until_console_prompt_completes_at_later_prompt(monkeypatch):
    process = ChunkedConsoleProcess(['{"target_bots": 1}\n', "TC> ", "next command output\n"])
    module_globals = read_until_console_prompt.__globals__
    monkeypatch.setattr(module_globals["select"], "select", lambda fds, *_args: (fds if process.chunks else [], [], []))
    monkeypatch.setattr(module_globals["os"], "read", lambda _fd, _size: process.chunks.pop(0))

    output = read_until_console_prompt(process, time.monotonic() + 1, '"target_bots"')

    assert output == '{"target_bots": 1}\nTC> '


def test_live_bot_validation_force_start_overrides_config_autostart(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-live-validate",
            "--dry-run",
            "--force-start-command",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert live_validation_main() == 0
    commands = (tmp_path / "commands.txt").read_text(encoding="utf-8")
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))

    assert ".botauto start" in commands
    assert ".botauto trace all 128" in commands
    assert report["config_autostart"] is True
    assert report["start_command"] is True


def test_live_bot_validation_reads_trinity_bool_config(tmp_path):
    conf = tmp_path / "worldserver.conf"
    conf.write_text('BotWorld.AutoStart = 1\nBotWorld.Enable = "false"\n', encoding="utf-8")

    assert trinity_config_bool(conf, "BotWorld.AutoStart") is True
    assert trinity_config_bool(conf, "BotWorld.Enable", True) is False
    assert trinity_config_bool(conf, "Missing.Flag", True) is True


def test_live_bot_validation_bot_pool_reset_sql_is_scoped_to_tags():
    sql = build_bot_pool_reset_sql(["test_account"], world_database="world")
    statements = split_sql_statements(sql)

    assert "p.`experiment_tags` LIKE '%test_account%'" in sql
    assert "JOIN `world`.`playercreateinfo`" in sql
    assert "DELETE FROM `characters`.`character_instance`" in sql
    assert "DELETE gi FROM `characters`.`group_instance`" in sql
    assert "DELETE gm FROM `characters`.`group_member`" in sql
    assert "DELETE g FROM `characters`.`groups`" in sql
    assert "DELETE ps FROM `characters`.`pet_spell`" in sql
    assert "DELETE pa FROM `characters`.`pet_aura`" in sql
    assert "DELETE pc FROM `characters`.`pet_spell_cooldown`" in sql
    assert "DELETE FROM `characters`.`mail_items`" in sql
    assert "DELETE FROM `characters`.`mail`" in sql
    assert "DELETE FROM `characters`.`character_queststatus`" in sql
    assert "DELETE FROM `characters`.`bot_memory_failed_paths`" in sql
    assert "bot_semantic_outcome_stats" not in sql
    assert statements[0].startswith("UPDATE `characters`.`character_bot_pool`")
    assert len(statements) >= 10


def test_live_bot_validation_dry_run_writes_reset_and_provisioning_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.bot_ml.run_live_bot_validation.database_url_from_worldserver_conf", lambda _path, key="WorldDatabaseInfo": f"mysql://trinity:secret@db.example:3306/{'auth_lane' if key == 'LoginDatabaseInfo' else 'characters_lane' if key == 'CharacterDatabaseInfo' else 'world_lane'}")
    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-live-validate",
            "--dry-run",
            "--reset-bot-pool",
            "--bot-pool-tag",
            "test_account",
            "--apply-validation-provisioning",
            "--gear-profiles",
            str(tmp_path / "missing_profiles.json"),
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert live_validation_main() == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    reset_sql = (tmp_path / "bot_pool_reset" / "reset_bot_pool.sql").read_text(encoding="utf-8")
    account_sql = (tmp_path / "validation_provisioning_apply" / "provision_accounts.sql").read_text(encoding="utf-8")
    character_sql = (tmp_path / "validation_provisioning_apply" / "provision_characters.sql").read_text(encoding="utf-8")
    worldserver_config = (tmp_path / "worldserver.validation.conf").read_text(encoding="utf-8")

    assert report["dry_run"] is True
    assert report["preparation"]["bot_pool_reset"]["applied"] is False
    assert report["preparation"]["bot_pool_reset"]["tags"] == ["test_account"]
    assert report["preparation"]["validation_provisioning"]["applied"] is False
    assert "UPDATE `characters_lane`.`character_bot_pool`" in reset_sql
    assert "JOIN `world_lane`.`playercreateinfo`" in reset_sql
    assert "INSERT INTO `auth_lane`.`account`" in account_sql
    assert "INSERT INTO `characters_lane`.`characters`" in character_sql
    assert f'BotWorld.ValidationProvisionAccountsSql = "{(tmp_path / "validation_provisioning_apply" / "provision_accounts.sql").resolve()}"' in worldserver_config
    assert f'BotWorld.ValidationProvisionCharactersSql = "{(tmp_path / "validation_provisioning_apply" / "provision_characters.sql").resolve()}"' in worldserver_config


def test_live_bot_validation_soap_dry_run_writes_non_exit_command_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-live-validate",
            "--dry-run",
            "--transport",
            "soap",
            "--no-start",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert live_validation_main() == 0
    commands = (tmp_path / "commands.txt").read_text(encoding="utf-8")
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))

    assert "server shutdown" not in commands
    assert ".botauto start" not in commands
    assert report["transport"] == "soap"


def test_validation_provisioning_generates_reproducible_sql_and_readiness(tmp_path, monkeypatch):
    config_path = Path("experiments/configs/validation_provisioning_cata_001.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    report = scenario_report(config)

    assert report["all_ready"] is False
    scenarios = {scenario["scenario_id"]: scenario for scenario in report["scenarios"]}
    assert scenarios["stonecore_5n"]["role_counts"] == {"tank": 1, "healer": 1, "dps": 3}
    assert scenarios["combat_calibration"]["role_counts"] == {"tank": 1, "healer": 0, "dps": 3}
    assert scenarios["blackwing_descent_10n"]["role_counts"] == {"tank": 2, "healer": 3, "dps": 5}
    assert scenarios["stonecore_5n"]["start_position"]["map_id"] == 725
    assert scenarios["combat_calibration"]["start_position"]["map_id"] == 0
    assert scenarios["blackwing_descent_10n"]["start_position"]["map_id"] == 669
    assert "complete_equipment_slots" in scenarios["stonecore_5n"]["missing"]

    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-validation-provisioning",
            "--config",
            str(config_path),
            "--gear-profiles",
            str(tmp_path / "missing_profiles.json"),
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert provisioning_main() == 0

    commands = (tmp_path / "account_commands.txt").read_text(encoding="utf-8")
    account_sql = (tmp_path / "provision_accounts.sql").read_text(encoding="utf-8")
    sql = (tmp_path / "provision_characters.sql").read_text(encoding="utf-8")
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    generated_report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))

    assert "account create SCVALTANK validation" in commands
    assert "account create CALIBTANK validation" in commands
    assert "account create BWDVALTKA validation" in commands
    assert "INSERT INTO `auth`.`account`" in account_sql
    assert "`salt`, `verifier`" in account_sql
    assert "ON DUPLICATE KEY UPDATE `expansion`" in account_sql
    assert "INSERT INTO `characters`.`characters`" in sql
    assert "INSERT INTO `characters`.`character_bot_pool`" in sql
    assert "INSERT INTO `characters`.`character_skills`" in sql
    assert "DELETE FROM `characters`.`character_spell`" in sql
    assert "INSERT INTO `characters`.`character_spell`" in sql
    assert "SELECT c.`guid`, 2061, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvalheal'" in sql
    assert "SELECT c.`guid`, 2050, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvalheal'" in sql
    assert "SELECT c.`guid`, 750, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvaltank'" in sql
    assert "SELECT c.`guid`, 9116, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvaltank'" in sql
    assert "INSERT INTO `characters`.`character_glyphs`" in sql
    assert "DELETE FROM `characters`.`character_talent`" in sql
    assert "SELECT c.`guid`, 47788, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvalheal'" in sql
    assert "SELECT c.`guid`, 14751, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvalheal'" in sql
    assert "SELECT c.`guid`, 34861, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvalheal'" in sql
    assert "SELECT c.`guid`, 14751, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvalheal'" in sql
    assert "SELECT c.`guid`, 47788, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvalheal'" in sql
    assert "SELECT c.`guid`, 88625, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvalheal'" in sql
    assert "SELECT c.`guid`, 87336, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvalheal'" in sql
    assert "SELECT c.`guid`, 95861, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvalheal'" in sql
    assert "SELECT c.`guid`, 33167, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvalheal'" in sql
    assert "SELECT c.`guid`, 64843, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvalheal'" in sql
    assert "SELECT c.`guid`, 64901, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvalheal'" in sql
    assert "SELECT c.`guid`, 586, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = 'Scvalheal'" in sql
    assert "SELECT c.`guid`, 0, 251, 0, 0, 0, 0, 0, 264, 709, 0" in sql
    assert "DELETE FROM `characters`.`item_instance` WHERE `guid` >= 9700000" in sql
    assert manifest["schema"] == "bot_validation_provisioning_manifest_v1"
    assert manifest["bot_count"] == 19
    assert generated_report == report


def test_cata_action_profile_manifest_drives_validation_spells(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manifest = load_action_profile_manifest()
    priest = {"class": 5, "spells": [12345]}
    paladin = {"class": 2, "spells": []}
    hunter = {"class": 3, "spells": []}
    shaman = {"class": 7, "spells": []}
    mage = {"class": 8, "spells": []}
    warrior = {"class": 1, "spells": []}
    death_knight = {"class": 6, "spells": []}
    warlock = {"class": 9, "spells": []}
    druid = {"class": 11, "spells": []}

    assert manifest["schema"] == "bot_cata_434_action_profiles_v2"
    assert 2061 in bot_spell_ids(priest, manifest)
    assert 2050 in bot_spell_ids(priest, manifest)
    assert 2006 in bot_spell_ids(priest, manifest)
    assert 750 in bot_spell_ids(paladin, manifest)
    assert 9116 in bot_spell_ids(paladin, manifest)
    assert {53595, 31935, 26573, 53600}.issubset(set(bot_spell_ids(paladin, manifest)))
    assert {6673, 469, 355, 2565}.issubset(set(bot_spell_ids(warrior, manifest)))
    assert {25780, 31801, 465, 20217, 19740, 54428}.issubset(set(bot_spell_ids(paladin, manifest)))
    assert {56641, 2643, 77767, 883, 982, 1130, 13165, 34477}.issubset(set(bot_spell_ids(hunter, manifest)))
    assert {79104, 79106}.issubset(set(bot_spell_ids(priest, manifest)))
    assert {48263, 49222, 48792, 55233, 49998, 57330, 56222, 45477}.issubset(set(bot_spell_ids(death_knight, manifest)))
    assert 674 in bot_spell_ids(shaman, manifest)
    assert 2008 in bot_spell_ids(shaman, manifest)
    assert {324, 8024, 8232, 8075, 3599, 5394, 8512, 3738, 8227, 66842}.issubset(set(bot_spell_ids(shaman, manifest)))
    assert {1459, 30482, 79057}.issubset(set(bot_spell_ids(mage, manifest)))
    assert 85767 in bot_spell_ids(warlock, manifest)
    assert 79060 in bot_spell_ids(druid, manifest)
    assert {8042, 17364, 60103, 421}.issubset(set(bot_spell_ids(shaman, manifest)))
    assert {2120, 1449}.issubset(set(bot_spell_ids(mage, manifest)))
    assert 12345 in bot_spell_ids(priest, manifest)


def test_validation_provisioning_generates_trinity_srp6_account_sql():
    config = {
        "account_password": "validation",
        "scenarios": [{"bots": [{"account": "ScValTank"}]}],
    }
    salt, verifier = srp6_registration_data("SCVALTANK", "validation")
    sql = build_account_insert_sql(config)

    assert len(salt) == 32
    assert len(verifier) == 32
    assert salt.hex() in sql
    assert verifier.hex() in sql
    assert "SCVALTANK" in sql
    assert "`salt` = VALUES" not in sql
    assert "`verifier` = VALUES" not in sql


def test_validation_provisioning_rejects_mixed_case_player_names(tmp_path, monkeypatch):
    config_path = tmp_path / "bad_names.json"
    config_path.write_text(
        json.dumps(
            {
                "schema": "bot_validation_provisioning_config_v1",
                "scenarios": [
                    {
                        "id": "stonecore_5n",
                        "start_position": {"map_id": 725, "x": 0, "y": 0, "z": 0},
                        "bots": [{"account": "SCVALDPSB", "name": "ScValDpsB", "role": "dps", "class": 3}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-validation-provisioning",
            "--config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    with pytest.raises(ValueError, match="Scvaldpsb"):
        provisioning_main()


def test_validation_gear_profiles_can_complete_slots_from_item_rows():
    config = {
        "scenarios": [
            {
                "id": "stonecore_5n",
                "start_position": {"map_id": 725, "x": 0, "y": 0, "z": 0},
                "bots": [
                    {"name": "Tank", "role": "tank", "class_spec": "protection_paladin", "class": 2},
                ],
            }
        ]
    }
    inv_by_slot = {
        0: 1,
        1: 2,
        2: 3,
        4: 5,
        5: 6,
        6: 7,
        7: 8,
        8: 9,
        9: 10,
        10: 11,
        11: 11,
        12: 12,
        13: 12,
            14: 16,
            15: 21,
            16: 14,
            17: 28,
    }
    items = []
    for offset, (slot, inventory_type) in enumerate(inv_by_slot.items(), start=1):
        items.append(
            {
                "ID": 100000 + offset,
                "Display": f"Validation Item {slot}",
                "ClassID": 4 if inventory_type not in {21, 14} else 2,
                "SubclassID": 4,
                "InventoryType": inventory_type,
                "Quality": 4,
                "ItemLevel": 359 + offset,
                "RequiredLevel": 85,
                "AllowableClass": -1,
                "ItemStatType1": 7,
                "ItemStatValue1": 100,
                "ItemStatType2": 4,
                "ItemStatValue2": 80,
            }
        )
    items.append(
        {
            "ID": 199999,
            "Display": "Rejected Two Hand",
            "ClassID": 2,
            "SubclassID": 5,
            "InventoryType": 17,
            "Quality": 4,
            "ItemLevel": 500,
            "RequiredLevel": 85,
            "AllowableClass": -1,
            "ItemStatType1": 7,
            "ItemStatValue1": 500,
        }
    )

    profiles = build_profiles(config, items)
    report = build_report(profiles, {"database": "hotfixes"})
    profile = profiles["protection_paladin"]

    assert profile["complete_equipment_slots"] is True
    assert profile["missing_slots"] == []
    assert {item["slot"] for item in profile["equipment"]} == set(inv_by_slot)
    assert next(item for item in profile["equipment"] if item["slot"] == 15)["inventory_type"] == 21
    assert report["all_equipment_slots_complete"] is True
    assert report["all_enchanted"] is False
    assert profile["stat_weight_manifest"]["schema"] == "bot_cata_434_combat_loot_profiles_v1"
    assert profile["stat_weights"]["stamina"] == 2.0
    assert len(profile["bis_source_report"]) == len(profile["equipment"])
    assert report["smart_loot_validation_surface"]["selected_equipment_count"] == len(profile["equipment"])


def test_combat_loot_profile_manifest_externalizes_stat_weights_and_reporting(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manifest = load_combat_loot_profile_manifest()

    assert manifest["schema"] == "bot_cata_434_combat_loot_profiles_v1"
    assert manifest["class_spec_archetypes"]["fire_mage"] == "dps_intellect"
    assert manifest["stat_weights_by_archetype"]["dps_intellect"]["spell_power"] == 1.2
    assert "stat_weights" in manifest["loot_validation"]["smart_loot_upgrade_surface"]


def test_validation_gear_profiles_complete_from_local_db2_files():
    config = json.loads(Path("experiments/configs/validation_provisioning_cata_001.json").read_text(encoding="utf-8"))
    items = fetch_items("mysql://trinity:trinity@172.20.0.2:3306/hotfixes", Path("data/dbc/enUS"), min_item_level=1, max_required_level=85)
    enchantments = load_spell_item_enchantments(Path("data/dbc/enUS"))
    gems = build_gem_catalog(items, load_gem_properties(Path("data/dbc/enUS")), {int(enchantment["id"]): enchantment for enchantment in enchantments})
    profiles = build_profiles(config, items, enchantments, gems)
    report = build_report(profiles, {"database": "hotfixes"})

    assert report["profile_count"] == 14
    assert report["all_equipment_slots_complete"] is True
    assert report["all_gemmed"] is True
    assert report["all_enchanted"] is True
    assert report["source_counts"]["enchanted_items"] >= 14 * 16
    assert report["source_counts"]["gemmed_items"] == report["source_counts"]["socketed_items"]
    assert report["enchant_applicability_verified_by_server"] is False
    assert report["profile_manifest"]["schema"] == "bot_cata_434_combat_loot_profiles_v1"
    assert report["smart_loot_validation_surface"]["ready_for_upgrade_scoring"] is True
    assert report["smart_loot_validation_surface"]["selected_equipment_count"] >= 14 * 16
    assert "dps_intellect" in report["stat_weight_archetypes"]
    assert report["source_counts"]["client_db2_items"] >= 14 * 16
    assert all(not profile["missing_slots"] for profile in profiles.values())
    assert next(item for item in profiles["blood_death_knight"]["equipment"] if item["slot"] == 15)["name"] == "Gurthalak, Voice of the Deeps"
    assert next(item for item in profiles["marksmanship_hunter"]["equipment"] if item["slot"] == 15)["name"] == "Kiril, Fury of Beasts"
    assert next(item for item in profiles["marksmanship_hunter"]["equipment"] if item["slot"] == 17)["name"] == "Vishanka, Jaws of the Earth"
    assert next(item for item in profiles["survival_hunter"]["equipment"] if item["slot"] == 15)["name"] == "Kiril, Fury of Beasts"
    assert next(item for item in profiles["survival_hunter"]["equipment"] if item["slot"] == 17)["name"] == "Vishanka, Jaws of the Earth"
    assert 16 not in {item["slot"] for item in profiles["blood_death_knight"]["equipment"]}
    assert all(
        next(item for item in profile["equipment"] if item["slot"] == 16)["inventory_type"] != 14
        for profile in profiles.values()
        if profile["class_id"] not in SHIELD_CLASSES and 16 in {item["slot"] for item in profile["equipment"]}
    )
    shaman_mainhands = [
        next(item for item in profile["equipment"] if item["slot"] == 15)
        for name, profile in profiles.items()
        if "shaman" in name
    ]
    assert all(item["subclass"] in {0, 1, 4, 5, 10, 13, 15} for item in shaman_mainhands)
    assert all(item["enchantments"].split()[0] == str(item["enchant_id"]) for profile in profiles.values() for item in profile["equipment"])
    assert all(len(item["enchantments"].split()) == 45 for profile in profiles.values() for item in profile["equipment"])


def test_validation_provisioning_applies_gear_profiles_to_bots():
    config = {
        "max_level": 85,
        "default_skills": [{"id": 185}],
        "default_consumables": [{"item_id": 58085, "slot": 40}],
        "scenarios": [
            {
                "id": "stonecore_5n",
                "start_position": {"map_id": 725, "x": 0, "y": 0, "z": 0},
                "bots": [
                    {"account": "A", "name": "Tank", "role": "tank", "class_spec": "protection_paladin", "race": 1, "class": 2, "level": 85, "glyphs": [1, 2, 3]},
                ],
            }
        ],
    }
    profiles = {
        "protection_paladin": {
            "equipment": [{"slot": slot, "item_id": 1000 + slot, "enchant_id": 0, "gem_item_ids": []} for slot in [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]]
        }
    }

    equipped = apply_gear_profiles(config, profiles)
    report = scenario_report(equipped)

    assert equipped["scenarios"][0]["bots"][0]["gear_profile"] == "protection_paladin"
    assert len(equipped["scenarios"][0]["bots"][0]["equipment"]) == 17
    assert report["scenarios"][0]["gear_missing_slots"]["Tank"] == []
    assert "complete_equipment_slots" not in report["scenarios"][0]["missing"]
    assert "enchants" in report["scenarios"][0]["missing"]


def test_validation_provisioning_writes_equipment_cache_and_filters_glyphs():
    bot = {"glyphs": [42739, 0, -3, 42743, 42743, 42753], "equipment": [{"slot": 15, "item_id": 5000, "enchant_id": 2673}, {"slot": 17, "item_id": 6000, "enchant_id": 0}]}
    config = {
        "scenarios": [
            {
                "id": "stonecore_5n",
                "start_position": {"map_id": 725, "x": 1, "y": 2, "z": 3},
                "bots": [{"account": "A", "name": "Hunter", "role": "dps", "class_spec": "marksmanship_hunter", "race": 1, "class": 3, "level": 85, **bot}],
            }
        ]
    }

    sql = build_character_insert_sql(config)
    cache = equipment_cache(bot["equipment"])

    assert normalized_glyphs(bot) == [316, 320, 330]
    assert cache.split()[30] == "5000"
    assert cache.split()[31] == "2673"
    assert cache.split()[34] == "6000"
    assert cache in sql
    assert " 0, -3," not in sql


def test_validation_provisioning_writes_configured_hunter_pet():
    config = {
        "pet_guid_base": 8700000,
        "scenarios": [
            {
                "id": "stonecore_5n",
                "start_position": {"map_id": 725, "x": 1, "y": 2, "z": 3},
                "bots": [
                    {
                        "account": "A",
                        "name": "Hunter",
                        "role": "dps",
                        "class_spec": "marksmanship_hunter",
                        "race": 1,
                        "class": 3,
                        "level": 85,
                        "glyphs": [42909, 42902, 42915],
                        "pet": {"id_offset": 7, "entry": 8959, "modelid": 4124, "created_by_spell": 0, "name": "Testwolf", "level": 85, "slot": 0, "active": 1, "spells": [2649, 17253]},
                    }
                ],
            }
        ],
    }

    sql = build_character_insert_sql(config)

    assert "DELETE ps FROM `characters`.`pet_spell`" in sql
    assert "DELETE FROM `characters`.`character_pet`" in sql
    assert "INSERT INTO `characters`.`character_pet`" in sql
    assert "SELECT 8700007, 8959, c.`guid`, 4124, 0, 1, 85" in sql
    assert "'Testwolf'" in sql
    assert "VALUES (8700007, 2649, 1)" in sql
    assert "VALUES (8700007, 17253, 1)" in sql


def test_validation_provisioning_maps_glyph_items_to_glyph_properties():
    glyph_map = glyph_item_to_property_map()

    assert glyph_map[42739] == 316
    assert normalized_glyphs({"glyphs": [42739, 42743, 42753]}, glyph_map) == [316, 320, 330]


def test_holy_priest_manifest_is_legal_and_drives_talents_and_glyph_slots():
    config = json.loads(Path("experiments/configs/validation_provisioning_cata_001.json").read_text(encoding="utf-8"))
    priest = next(bot for scenario in config["scenarios"] for bot in scenario["bots"] if bot["class_spec"] == "holy_priest")

    validate_talent_manifest(priest)
    assert len(bot_talent_spell_ids(priest)) == 23
    assert sum({15020: 2, 33160: 3, 18533: 3, 19236: 1, 88690: 2, 15362: 2, 63542: 2, 34859: 2, 724: 1, 81625: 2, 95649: 1, 20711: 1, 63733: 2, 64129: 2, 14751: 1, 88627: 1, 33145: 2, 47560: 3, 34861: 1, 47788: 1, 14768: 2, 47588: 3, 14520: 1}.values()) == 41
    assert set(priest["primary_tree_spells"]) == {88625, 87336, 95861, 33167}
    assert {586, 34433, 64843, 64901}.issubset(set(bot_spell_ids(priest)))
    assert {14751, 34861, 47788}.isdisjoint(set(bot_spell_ids(priest)))
    assert set(bot_primary_tree_spell_ids(priest)) == {88625, 87336, 95861, 33167}
    assert {14751, 34861, 47788, 88625, 88684, 87336, 95861, 33167}.issubset(set(bot_known_spell_ids(priest)))
    assert normalized_glyph_slots(priest) == [251, 0, 0, 0, 0, 0, 264, 709, 0]
    assert {251: 0, 264: 2, 709: 2}.items() <= glyph_property_type_map().items()


def test_stonecore_role_specs_inherit_complete_dbc_legal_talent_and_action_profiles():
    config = load_validation_provisioning_config(Path("experiments/configs/validation_provisioning_cata_001.json"))
    action_profiles = load_action_profile_manifest()
    required = {
        "protection_paladin": {53595, 26573, 31935, 53600, 62124, 1022},
        "fire_mage": {133, 2948, 44457, 92315, 11129},
        "marksmanship_hunter": {1978, 53209, 56641, 19434, 3045, 34490},
        "survival_hunter": {1978, 53301, 3674, 77767, 2643, 34477, 3045},
        "enhancement_shaman": {17364, 60103, 8050, 73680, 403, 421, 51533},
    }

    for scenario in config["scenarios"]:
        for bot in scenario["bots"]:
            class_spec = bot["class_spec"]
            if class_spec not in required:
                continue
            validate_talent_manifest(bot)
            assert talent_point_count(bot) == 41
            assert required[class_spec] <= set(bot_known_spell_ids(bot, action_profiles))

    assert action_profiles["schema"] == "bot_cata_434_action_profiles_v2"


def test_provisioning_does_not_learn_unselected_cross_spec_talents():
    config = load_validation_provisioning_config(Path("experiments/configs/validation_provisioning_cata_001.json"))
    hunter = next(
        bot
        for scenario in config["scenarios"]
        for bot in scenario["bots"]
        if bot["class_spec"] == "survival_hunter"
    )
    action_profiles = load_action_profile_manifest()

    ordinary_spells = set(bot_spell_ids(hunter, action_profiles))
    known_spells = set(bot_known_spell_ids(hunter, action_profiles))
    assert 53209 not in ordinary_spells  # unselected Marksmanship Chimera Shot talent
    assert 19434 not in ordinary_spells  # unselected Marksmanship primary-tree spell
    assert {3674, 53301} <= known_spells

    sql = build_character_insert_sql({"scenarios": [{"id": "stonecore_5n", "start_position": {"map_id": 725, "x": 1, "y": 2, "z": 3}, "bots": [hunter]}]}, action_profiles)
    assert "SELECT c.`guid`, 53209, 1, 0" not in sql
    assert "SELECT c.`guid`, 19434, 1, 0" not in sql
    assert "SELECT c.`guid`, 3674, 1, 0" in sql
    assert "SELECT c.`guid`, 53301, 1, 0" in sql


def test_stonecore_hazard_geometry_is_emitted_in_route_manifest():
    config = json.loads(Path("experiments/configs/validation_scenarios_cata_001.json").read_text(encoding="utf-8"))
    manifests = build_validation_scenario_manifests(config, {"scenarios": []}, {"all_passed": True})
    routes = [row for row in manifests["validation_routes"] if row["scenario_id"] == "stonecore_5n"]
    corridor = next(row for row in routes if row["label"] == "crystalspawn corridor")
    slabhide = next(row for row in routes if row["label"] == "Slabhide")
    sentry = next(row for row in routes if row["label"] == "stonecore sentry gauntlet")
    flayers = next(row for row in routes if row["label"] == "twilight flayer packs")
    azil = next(row for row in routes if row["label"] == "High Priestess Azil")

    assert (corridor["hazard_source_entry"], corridor["hazard_detection_spell_id"], corridor["hazard_shape"]) == (42808, 79922, "radial")
    assert (slabhide["hazard_source_entry"], slabhide["hazard_damage_spell_id"], slabhide["hazard_shape"], slabhide["hazard_radius_yards"]) == (43242, 80801, "radial", 5.0)
    assert (sentry["hazard_source_entry"], sentry["hazard_detection_spell_id"], sentry["hazard_shape"]) == (42808, 79922, "radial")
    assert (flayers["hazard_source_entry"], flayers["hazard_detection_spell_id"], flayers["hazard_shape"], flayers["hazard_radius_yards"]) == (42808, 79922, "radial", 4.0)
    assert (azil["hazard_source_entry"], azil["hazard_detection_spell_id"], azil["hazard_damage_spell_id"], azil["hazard_shape"], azil["hazard_radius_yards"]) == (42499, 79244, 79249, "radial", 6.0)
    assert flayers["source_entry"] == 42808
    assert flayers["pack_target_entries"] == [42808]


def test_validation_provisioning_strips_socket_gem_enchantments_for_runtime_load():
    item = {"enchant_id": 2673, "enchantments": "2673 0 0 0 0 0 3996 0 0 3996 0 0 3996 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0"}

    fields = runtime_safe_enchantments(item).split()

    assert len(fields) == 45
    assert fields[0] == "2673"
    assert fields[6] == "0"
    assert fields[9] == "0"
    assert fields[12] == "0"


def test_validation_provisioning_preserves_verified_wowsims_gems_and_reforge():
    fields = runtime_safe_enchantments(
        {
            "enchant_id": 4207,
            "gem_enchant_ids": [4253, 4331],
            "reforge_id": 151,
            "preserve_socket_enchantments": True,
        }
    ).split()

    assert fields[0] == "4207"
    assert fields[6] == "4253"
    assert fields[9] == "4331"
    assert fields[24] == "151"


def test_validation_provisioning_loads_exact_wowsims_calibration_overlays():
    profiles = load_gear_profiles(Path("dataset/validation_gear_profiles/profiles.json"))

    fire = profiles["wowsims_cata_p4_fire_mage"]
    hunter = profiles["wowsims_cata_p4_survival_hunter"]
    shaman = profiles["wowsims_cata_p4_enhancement_shaman"]
    assert next(item for item in fire["equipment"] if item["slot"] == 15)["item_id"] == 71086
    assert next(item for item in hunter["equipment"] if item["slot"] == 17)["item_id"] == 78471
    assert [item["item_id"] for item in shaman["equipment"] if item["slot"] in {15, 16}] == [78472, 78472]


def test_validation_provisioning_runtime_gear_verification_fails_missing_hunter_ranged(monkeypatch, tmp_path):
    conf = tmp_path / "worldserver.conf"
    conf.write_text(
        'LoginDatabaseInfo = "db.example;3306;trinity;secret;auth"\n'
        'CharacterDatabaseInfo = "db.example;3306;trinity;secret;characters"\n',
        encoding="utf-8",
    )
    equipment = [
        {"slot": slot, "item_id": 5000 + slot, "inventory_type": 1, "durability": 100}
        for slot in [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    ] + [{"slot": 15, "item_id": 5000, "inventory_type": 17, "durability": 100}, {"slot": 17, "item_id": 6000, "inventory_type": 26, "durability": 100}]
    config = {"scenarios": [{"id": "stonecore_5n", "bots": [{"account": "A", "name": "Hunter", "class": 3, "glyphs": [1, 2, 3], "equipment": equipment}]}]}

    monkeypatch.setattr("tools.bot_ml.validate_validation_provisioning.fetch_columns", lambda _url, table: {"id", "username"} if table == "account" else {"guid", "account", "name", "slot", "race", "class", "gender", "level", "xp", "money", "position_x", "position_y", "position_z", "map", "orientation", "taximask", "online", "cinematic", "totaltime", "leveltime", "logout_time", "health", "power1", "talentGroupsCount", "activeTalentGroup", "talentTree", "equipmentCache"} if table == "characters" else {"guid", "bag", "slot", "item", "itemEntry", "durability", "owner_guid", "creatorGuid", "giftCreatorGuid", "count", "duration", "charges", "flags", "enchantments", "randomPropertyType", "randomPropertyId", "creationTime", "text", "role", "class_spec", "enabled", "in_use", "experiment_tags", "notes", "talentGroup", "glyph1", "glyph2", "glyph3", "glyph4", "glyph5", "glyph6", "glyph7", "glyph8", "glyph9", "skill", "value", "max", "spell"})
    monkeypatch.setattr("tools.bot_ml.validate_validation_provisioning.fetch_existing_values", lambda _url, _table, _column, values: set(values))
    monkeypatch.setattr(
        "tools.bot_ml.validate_validation_provisioning.fetch_runtime_gear",
        lambda _url, _names: {"Hunter": {"guid": 1, "equipmentCache": equipment_cache([item for item in equipment if item["slot"] != 17]), "items": {item["slot"]: {"item_id": item["item_id"], "durability": 100} for item in equipment if item["slot"] != 17}, "glyphs": [1, 2, 3, 0, 0, 0, 0, 0, 0]}},
    )

    failures, evidence = validate_provisioning_database(config, conf, require_applied=True)

    assert {"check": "runtime_equipment_slots", "bot": "Hunter", "missing_slots": [17]} in failures
    assert evidence["runtime_gear"]["Hunter"]["visible_missing_slots"] == [17]


def test_validation_provisioning_runtime_gear_verification_fails_stale_cache_and_zero_glyphs(monkeypatch, tmp_path):
    conf = tmp_path / "worldserver.conf"
    conf.write_text(
        'LoginDatabaseInfo = "db.example;3306;trinity;secret;auth"\n'
        'CharacterDatabaseInfo = "db.example;3306;trinity;secret;characters"\n',
        encoding="utf-8",
    )
    slots = [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
    equipment = [{"slot": slot, "item_id": 7000 + slot, "inventory_type": 1, "durability": 100} for slot in slots]
    config = {"scenarios": [{"id": "stonecore_5n", "bots": [{"account": "A", "name": "Mage", "class": 8, "glyphs": [42739, 42743, 42753], "equipment": equipment}]}]}

    monkeypatch.setattr("tools.bot_ml.validate_validation_provisioning.fetch_columns", lambda _url, table: {"id", "username"} if table == "account" else {"guid", "account", "name", "slot", "race", "class", "gender", "level", "xp", "money", "position_x", "position_y", "position_z", "map", "orientation", "taximask", "online", "cinematic", "totaltime", "leveltime", "logout_time", "health", "power1", "talentGroupsCount", "activeTalentGroup", "talentTree", "equipmentCache"} if table == "characters" else {"guid", "bag", "slot", "item", "itemEntry", "durability", "owner_guid", "creatorGuid", "giftCreatorGuid", "count", "duration", "charges", "flags", "enchantments", "randomPropertyType", "randomPropertyId", "creationTime", "text", "role", "class_spec", "enabled", "in_use", "experiment_tags", "notes", "talentGroup", "glyph1", "glyph2", "glyph3", "glyph4", "glyph5", "glyph6", "glyph7", "glyph8", "glyph9", "skill", "value", "max", "spell"})
    monkeypatch.setattr("tools.bot_ml.validate_validation_provisioning.fetch_existing_values", lambda _url, _table, _column, values: set(values))
    monkeypatch.setattr(
        "tools.bot_ml.validate_validation_provisioning.fetch_runtime_gear",
        lambda _url, _names: {"Mage": {"guid": 1, "equipmentCache": "", "items": {item["slot"]: {"item_id": item["item_id"], "durability": 100} for item in equipment}, "glyphs": [0] * 9}},
    )

    failures, evidence = validate_provisioning_database(config, conf, require_applied=True)

    checks = {failure["check"] for failure in failures}
    assert "runtime_equipment_cache" in checks
    assert "runtime_glyphs" in checks
    assert evidence["runtime_gear"]["Mage"]["glyphs_missing"] == [316, 320, 330]


def test_validation_provisioning_runtime_verifies_talent_tree_talents_and_known_spells(monkeypatch, tmp_path):
    conf = tmp_path / "worldserver.conf"
    conf.write_text(
        'LoginDatabaseInfo = "db.example;3306;trinity;secret;auth"\n'
        'CharacterDatabaseInfo = "db.example;3306;trinity;secret;characters"\n',
        encoding="utf-8",
    )
    config = {"scenarios": [{"id": "stonecore_5n", "bots": [{"account": "A", "name": "Holy", "class": 5, "primary_talent_tree_id": 813, "talents": [{"spell_id": 34861}]}]}]}

    monkeypatch.setattr("tools.bot_ml.validate_validation_provisioning.fetch_columns", lambda _url, _table: set())
    monkeypatch.setattr("tools.bot_ml.validate_validation_provisioning.fetch_existing_values", lambda _url, _table, _column, values: set(values))
    monkeypatch.setattr(
        "tools.bot_ml.validate_validation_provisioning.fetch_runtime_gear",
        lambda _url, _names: {"Holy": {"guid": 1, "talentTree": "0 0", "equipmentCache": "", "items": {}, "glyphs": [], "talent_spells": set(), "known_spells": set()}},
    )

    failures, evidence = validate_provisioning_database(config, conf, require_applied=True)

    assert {failure["check"] for failure in failures} >= {"runtime_talent_tree", "runtime_character_talent", "runtime_character_spell"}
    assert evidence["runtime_gear"]["Holy"]["talent_tree"] == {"expected": 813, "actual": 0}
    assert evidence["runtime_gear"]["Holy"]["missing_talent_spells"] == [34861]
    assert {34861, 88625, 87336, 95861, 33167}.issubset(evidence["runtime_gear"]["Holy"]["missing_known_spells"])


def test_validation_provisioning_verifier_accepts_generated_payloads(tmp_path, monkeypatch):
    output = tmp_path / "verification" / "report.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "bot-validation-provisioning-verify",
            "--config",
            "experiments/configs/validation_provisioning_cata_001.json",
            "--gear-profiles",
            "dataset/validation_gear_profiles/profiles.json",
            "--provisioning-report",
            "dataset/validation_provisioning/report.json",
            "--output",
            str(output),
        ],
    )

    assert provisioning_verify_main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))

    assert report["schema"] == "bot_validation_provisioning_verifier_report_v1"
    assert report["all_passed"] is True
    assert report["payload_valid"] is True
    assert report["failure_count"] == 0
    assert report["payload_evidence"]["enchantment_count"] > 0
    assert report["payload_evidence"]["gem_property_count"] > 0


def test_validation_provisioning_database_preflight_reports_missing_accounts(tmp_path, monkeypatch):
    conf = tmp_path / "worldserver.conf"
    conf.write_text(
        '\nLoginDatabaseInfo = "db.example;3306;trinity;secret;auth"\n'
        'CharacterDatabaseInfo = "db.example;3306;trinity;secret;characters"\n',
        encoding="utf-8",
    )
    config = {
        "scenarios": [
            {
                "id": "stonecore_5n",
                "bots": [
                    {"account": "SCVALTANK", "name": "Scvaltank"},
                ],
            }
        ]
    }

    def fake_columns(_url, table):
        for tables in [
            {
                "account": {"id", "username"},
            },
            {
                "characters": {"guid", "account", "name", "slot", "race", "class", "gender", "level", "xp", "money", "position_x", "position_y", "position_z", "map", "orientation", "taximask", "online", "cinematic", "totaltime", "leveltime", "logout_time", "health", "power1", "talentGroupsCount", "activeTalentGroup", "talentTree", "equipmentCache"},
                "item_instance": {"guid", "itemEntry", "owner_guid", "creatorGuid", "giftCreatorGuid", "count", "duration", "charges", "flags", "enchantments", "randomPropertyType", "randomPropertyId", "durability", "creationTime", "text"},
                "character_inventory": {"guid", "bag", "slot", "item"},
                "character_bot_pool": {"guid", "role", "class_spec", "enabled", "in_use", "experiment_tags", "notes"},
                "character_glyphs": {"guid", "talentGroup", "glyph1", "glyph2", "glyph3", "glyph4", "glyph5", "glyph6", "glyph7", "glyph8", "glyph9"},
                "character_talent": {"guid", "spell", "talentGroup"},
                "character_spell": {"guid", "spell", "active", "disabled"},
                "character_skills": {"guid", "skill", "value", "max"},
            },
        ]:
            if table in tables:
                return tables[table]
        return set()

    monkeypatch.setattr("tools.bot_ml.validate_validation_provisioning.fetch_columns", fake_columns)
    monkeypatch.setattr("tools.bot_ml.validate_validation_provisioning.fetch_existing_values", lambda _url, _table, _column, _values: set())

    failures, evidence = validate_provisioning_database(config, conf)
    report = provisioning_verify_report(config, {"all_ready": True}, [], {"enchantment_count": 1, "gem_property_count": 1}, failures, evidence)

    assert report["all_passed"] is False
    assert report["database_valid"] is False
    assert failures == [{"check": "validation_accounts", "missing_accounts": ["SCVALTANK"], "recovery": "apply generated provision_accounts.sql or run account_commands.txt in the worldserver console"}]
    assert evidence["expected_accounts"] == 1
    assert evidence["existing_accounts"] == 0


def test_headless_movement_smoke_records_metrics(tmp_path):
    config = load_config(Path("experiments/configs/headless_movement_smoke_001.json"))
    adapter = make_adapter(config, force_local=True)

    summary = run_experiment(config, adapter, tmp_path / "runs", tmp_path / "raw")

    assert summary["result"] == "success"
    metrics_path = tmp_path / summary["paths"]["movement_metrics"]
    frames_path = tmp_path / summary["paths"]["frames"]
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    recomputed = movement_metrics(frames_path)

    assert metrics["movement_frame_count"] >= 6
    assert metrics["return_to_group_success"] is True
    assert metrics["movement_command_invalid_rate"] == 0.0
    assert recomputed == metrics


def test_headless_solo_combat_smoke_records_metrics(tmp_path):
    config = load_config(Path("experiments/configs/headless_solo_combat_smoke_001.json"))
    adapter = make_adapter(config, force_local=True)

    summary = run_experiment(config, adapter, tmp_path / "runs", tmp_path / "raw")

    assert summary["result"] == "success"
    metrics_path = tmp_path / summary["paths"]["solo_combat_metrics"]
    frames_path = tmp_path / summary["paths"]["frames"]
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    recomputed = solo_combat_metrics(frames_path)

    assert metrics["combat_frame_count"] >= 4
    assert metrics["kill_success_rate"] == 1.0
    assert metrics["death_rate"] == 0.0
    assert metrics["loot_success"] is True
    assert metrics["invalid_action_rate"] == 0.0
    assert recomputed == metrics


def test_headless_simple_kill_quest_smoke_records_metrics(tmp_path):
    config = load_config(Path("experiments/configs/headless_simple_kill_quest_smoke_001.json"))
    adapter = make_adapter(config, force_local=True)

    summary = run_experiment(config, adapter, tmp_path / "runs", tmp_path / "raw")

    assert summary["result"] == "success"
    metrics_path = tmp_path / summary["paths"]["quest_metrics"]
    frames_path = tmp_path / summary["paths"]["frames"]
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    recomputed = quest_metrics(frames_path)

    assert metrics["quest_frame_count"] >= 2
    assert metrics["quest_completion_success"] is True
    assert metrics["deaths_per_quest"] == 0
    assert metrics["invalid_action_rate"] == 0.0
    assert recomputed == metrics


def test_headless_profession_cooking_smoke_records_metrics(tmp_path):
    config = load_config(Path("experiments/configs/headless_profession_cooking_smoke_001.json"))
    adapter = make_adapter(config, force_local=True)

    summary = run_experiment(config, adapter, tmp_path / "runs", tmp_path / "raw")

    assert summary["result"] == "success"
    metrics_path = tmp_path / summary["paths"]["profession_metrics"]
    frames_path = tmp_path / summary["paths"]["frames"]
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    recomputed = profession_metrics(frames_path)

    assert metrics["profession_frame_count"] >= 4
    assert metrics["craft_attempts"] == 1
    assert metrics["craft_success_rate"] == 1.0
    assert metrics["skill_delta"] == 2
    assert metrics["gear_eval_items"] >= 1
    assert metrics["invalid_action_rate"] == 0.0
    assert recomputed == metrics


def test_headless_autonomous_loop_smoke_records_frames_and_metrics(tmp_path):
    config = load_config(Path("experiments/configs/headless_autonomous_loop_smoke_001.json"))
    adapter = make_adapter(config, force_local=True)

    tasks = load_tasks(config)
    state = observe_state(config, adapter, completed=set(), failed={})
    selected, policy = select_task(tasks, state, completed=set(), failed={}, min_bag_slots=2, min_durability_pct=0.5)

    assert selected is not None
    assert selected.task_type == "repair_and_restock"
    assert policy["mode"] == "prepare_then_run_task"

    summary = run_experiment(config, adapter, tmp_path / "runs", tmp_path / "raw")

    assert summary["result"] == "success"
    frames_path = tmp_path / summary["paths"]["frames"]
    metrics_path = tmp_path / summary["paths"]["autonomous_metrics"]
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    recomputed = autonomous_metrics(frames_path)

    assert Path("ml/schemas/autonomous_task.schema.json").exists()
    assert "gear_broken" in FAILURE_HANDLERS
    assert metrics["autonomous_frame_count"] >= 4
    assert metrics["tasks_completed"] >= 4
    assert set(metrics["domain_tasks_invoked"]) >= {"quest", "profession", "dungeon"}
    assert metrics["dataset_frames_generated_per_domain"]["autonomous_loop"] >= 4
    assert metrics["manual_intervention_count"] == 0
    assert (tmp_path / summary["paths"]["autonomous_frames"]).exists()
    assert recomputed == metrics


def test_group_role_reservation_store_expires_assignments():
    store = ReservationStore()
    store.reserve("interrupt", 50103, target_enemy_slot=0, spell_id=900201, expires_in=1.2)

    assert store.active("interrupt")[0].as_frame_value()["assigned_to_guid"] == 50103

    store.tick(0.7)
    assert store.active("interrupt")[0].expires_in == 0.5

    store.tick(0.6)
    assert store.active("interrupt") == []


def test_group_role_policies_cover_phase05_modes():
    assert policy_for_role("tank", {"tick": 0})["mode"] == "pull_setup"
    assert policy_for_role("healer", {"mechanic_family": "group_aoe"})["mode"] == "prepare_group_aoe"
    assert policy_for_role("melee_dps", {"mechanic_family": "interrupt"})["mode"] == "interrupt_duty"
    assert policy_for_role("ranged_dps", {"mechanic_family": "cc_required"})["mode"] == "cc_duty"


def test_phase05_mechanic_metadata_contains_required_files_and_families():
    required_files = [
        "mechanic_families.json",
        "spell_mechanics.json",
        "role_responses.json",
        "boss_timelines.json",
        "embedding_vocab.json",
    ]
    for filename in required_files:
        assert (Path("dataset/metadata") / filename).exists()

    families = json.loads(Path("dataset/metadata/mechanic_families.json").read_text(encoding="utf-8"))["mechanic_families"]
    for family in ["tank_buster", "group_aoe", "dispel", "interrupt", "cc_required"]:
        assert family in families


def test_full_party_trash_pull_smoke_records_role_and_group_metrics(tmp_path):
    config = load_config(Path("experiments/configs/full_party_trash_pull_001.json"))
    adapter = make_adapter(config, force_local=True)

    summary = run_experiment(config, adapter, tmp_path / "runs", tmp_path / "raw")

    assert summary["result"] == "success"
    assert len(json.loads((tmp_path / summary["paths"]["metadata"]).read_text(encoding="utf-8"))["bots"]) == 5
    frames_path = tmp_path / summary["paths"]["frames"]
    metrics_path = tmp_path / summary["paths"]["group_role_metrics"]
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    recomputed = group_role_metrics(frames_path)

    assert metrics["success"] is True
    assert metrics["group_role_frame_count"] == 40
    assert metrics["group_coordination_frame_count"] >= 8
    assert set(metrics["role_frame_counts"]) == {"tank", "healer", "melee_dps", "ranged_dps"}
    assert metrics["role_frame_counts"] == {"tank": 8, "healer": 8, "melee_dps": 8, "ranged_dps": 16}
    assert metrics["missed_interrupts"] == 0
    assert metrics["missed_dispels"] == 0
    assert (tmp_path / summary["paths"]["role_frames"]).exists()
    assert (tmp_path / summary["paths"]["tank_frames"]).exists()
    assert (tmp_path / summary["paths"]["healer_frames"]).exists()
    assert (tmp_path / summary["paths"]["melee_dps_frames"]).exists()
    assert (tmp_path / summary["paths"]["ranged_dps_frames"]).exists()
    assert (tmp_path / summary["paths"]["group_coordination"]).exists()
    assert recomputed == metrics


def test_phase07_dungeon_segment_records_route_labels_and_comparisons(tmp_path):
    config = load_config(Path("experiments/configs/dungeon_segment_tot_basic_001.json"))
    adapter = make_adapter(config, force_local=True)

    summary = run_experiment(config, adapter, tmp_path / "runs", tmp_path / "raw")

    assert summary["result"] == "success"
    frames_path = tmp_path / summary["paths"]["frames"]
    metrics_path = tmp_path / summary["paths"]["dungeon_route_metrics"]
    comparison_path = tmp_path / summary["paths"]["comparison_metrics"]
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    assert summary["paths"]["dungeon_route"].endswith(".jsonl")
    assert metrics["route_steps_completed"] == 4
    assert metrics["future_label_frame_count"] >= 5
    assert set(metrics["planner_roles"]) == {"healer", "melee_dps", "ranged_dps", "tank"}
    assert dungeon_route_metrics(frames_path) == metrics
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    assert comparison["scripted_baseline"]["route_completed"] is True
    assert comparison["group_coordination_on"]["success"] is True


def test_phase07_planners_labels_and_inference_stub():
    state = {"mechanic_family": "tank_buster", "expected_damage": 0.2, "tank_hp_pct": 0.5, "lowest_party_hp_pct": 0.8}

    assert TankPlanner().plan(state)["mode"] == "defensive_timing"
    assert HealerPlanner().plan({"mechanic_family": "group_aoe", "lowest_party_hp_pct": 0.8})["mode"] == "prepare"
    assert DPSPlanner().plan({"mechanic_family": "interrupt"})["mode"] == "interrupt_assignment"
    labels = future_labels(state)
    assert labels["party_damage_next_2s"] > 0
    assert labels["tank_burst_risk"] == 0.85
    prediction = RolePolicyInferenceAdapter().predict("tank", {"policy_output": {"mode": "hold_threat", "intent": "hold_threat"}})
    assert prediction["adapter"] == "scripted_stub"


def test_phase08_raid_metadata_schema_and_scheduler():
    assert Path("ml/schemas/raid_module.schema.json").exists()

    families = json.loads(Path("dataset/metadata/mechanic_families.json").read_text(encoding="utf-8"))["mechanic_families"]
    for family in [
        "tank_swap",
        "raid_wide_aoe",
        "stack",
        "spread",
        "soak",
        "assigned_soak",
        "interrupt_rotation",
        "dispel_rotation",
        "healer_cooldown_assignment",
        "burn_phase",
        "add_wave",
        "boss_immunity",
        "phase_transition",
        "enrage_timer",
    ]:
        assert family in families

    scheduler = RaidAssignmentScheduler([
        {"guid": 50101, "role": "tank"},
        {"guid": 50102, "role": "tank"},
        {"guid": 50103, "role": "healer"},
        {"guid": 50104, "role": "melee_dps"},
        {"guid": 50105, "role": "ranged_dps"},
    ])
    first = scheduler.next_tank("swap_1", "tank_swap", 3.0)
    second = scheduler.next_tank("swap_2", "tank_swap", 8.0)
    interrupt = scheduler.next_interrupt("kick_1", "interrupt_rotation", 2.0, 80001)

    assert first.assigned_to_guid == 50101
    assert second.assigned_to_guid == 50102
    assert interrupt.target_enemy_guid == 80001
    assert len(scheduler.frame_state()["assignments"]) == 3


def test_phase08_raid_smoke_configs_record_frames_and_metrics(tmp_path):
    config_names = [
        "raid_tank_swap_basic.json",
        "raid_aoe_cooldown_rotation.json",
        "raid_interrupt_rotation.json",
        "raid_stack_spread_basic.json",
        "raid_add_wave_target_switch.json",
    ]

    for config_name in config_names:
        config = load_config(Path("experiments/configs") / config_name)
        adapter = make_adapter(config, force_local=True)

        summary = run_experiment(config, adapter, tmp_path / "runs", tmp_path / "raw")

        assert summary["result"] == "success"
        frames_path = tmp_path / summary["paths"]["frames"]
        metrics_path = tmp_path / summary["paths"]["raid_metrics"]
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        recomputed = raid_metrics(frames_path)

        assert summary["paths"]["raid_modules"].endswith(".jsonl")
        assert metrics["raid_frame_count"] >= int(config["run"]["module_ticks"])
        assert metrics["mechanic_survival"] == 1.0
        assert metrics["avoidable_raid_damage"] >= 0.0
        assert recomputed == metrics


def test_phase08_server_raid_telemetry_surface():
    header = Path("src/server/game/Bots/BotWorldPopulationMgr.h").read_text(encoding="utf-8")
    impl = Path("src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")
    conf = Path("src/server/worldserver/worldserver.conf.dist").read_text(encoding="utf-8")

    for symbol in [
        "RaidRoleAssignment",
        "RaidPositioningAnchors",
        "RaidMechanicAdapter",
        "RaidGearTargetPlan",
        "HeroicRaidProgression",
        "RecordRaidTelemetry",
    ]:
        assert symbol in header

    for event_type in [
        "raid_role_assignment",
        "raid_mechanic",
        "raid_interrupt",
        "raid_add_wave",
        "raid_position_anchor",
        "raid_boss_action",
        "raid_boss_killed",
        "raid_wipe",
    ]:
        assert event_type in impl

    for counter_name in [
        "role_assignments",
        "group_formations",
        "raid_formations",
        "target_priority_decisions",
        "healer_assignments",
        "tank_positioning",
        "regroups",
        "recovery_events",
        "instance_resets",
    ]:
        assert counter_name in impl

    for semantic_key in [
        "raid_role_assignment",
        "raid_positioning_anchors",
        "raid_mechanic_adapter",
        "raid_gear_target_plan",
        "heroic_raid_progression",
        "gear_target_plan",
    ]:
        assert semantic_key in impl

    assert "BotProgression.TrackHeroicRaidProgression = 1" in conf


def test_phase12_bot_telemetry_importance_policy_surface():
    header = Path("src/server/game/Bots/BotTelemetryPolicy.h").read_text(encoding="utf-8")
    impl = Path("src/server/game/Bots/BotTelemetryPolicy.cpp").read_text(encoding="utf-8")
    mgr_header = Path("src/server/game/Bots/BotWorldPopulationMgr.h").read_text(encoding="utf-8")
    mgr_impl = Path("src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")
    conf = Path("src/server/worldserver/worldserver.conf.dist").read_text(encoding="utf-8")
    cmake = Path("src/server/game/CMakeLists.txt").read_text(encoding="utf-8")

    for symbol in [
        "enum class BotTelemetryImportance",
        "BotTelemetryPolicyInput",
        "BotTelemetryPolicyDecision",
        "BotTelemetryPolicyConfig",
        "DecideEvent",
        "DecideDecision",
    ]:
        assert symbol in header

    for importance in ["Drop", "Sample", "Keep", "Clip", "Replay"]:
        assert importance in header

    for policy_rule in [
        "death",
        "resurrected",
        "stuck_detected",
        "objective_failed",
        "quest_completed",
        "quest_accepted",
        "boss_killed",
        "raid_wipe",
        "interrupt_failed",
        "loot_received",
        "gear_upgrade",
        "level_up",
        "spell_cast",
        "move_started",
        "reward_blocked",
        "out_of_range_loot",
    ]:
        assert policy_rule in impl

    for config_key in [
        "BotExperiment.AlwaysRecordFailures",
        "BotExperiment.AlwaysRecordInterventions",
        "BotExperiment.AlwaysRecordRareStates",
        "BotExperiment.NormalEventSampleRate",
        "BotExperiment.NormalDecisionSampleRate",
        "BotExperiment.MinClipImportance",
        "BotExperiment.MinReplayImportance",
    ]:
        assert config_key in conf
        assert config_key in mgr_impl

    for config_field in [
        "AlwaysRecordFailures",
        "AlwaysRecordInterventions",
        "AlwaysRecordRareStates",
        "NormalEventSampleRate",
        "NormalDecisionSampleRate",
        "MinClipImportance",
        "MinReplayImportance",
    ]:
        assert config_field in mgr_header

    for call_site in [
        "RecordEvent(WorldBotState& state",
        "RecordQuestEvent(WorldBotState& state",
        "RecordRaidTelemetry",
        "RecordDecision",
        "BotTelemetryPolicy::DecideEvent",
        "BotTelemetryPolicy::DecideDecision",
        "RecordPolicyReplay",
        "MaybeCaptureTelemetryClip(bot, target, policyInput, policy",
        "MaybeCaptureTelemetryClip(bot, boss, policyInput, policy",
    ]:
        assert call_site in mgr_impl

    assert "BotTelemetryPolicy.cpp" in cmake


def test_phase13_triggered_experiment_segments_surface():
    header = Path("src/server/game/Bots/BotExperimentCoordinator.h").read_text(encoding="utf-8")
    impl = Path("src/server/game/Bots/BotExperimentCoordinator.cpp").read_text(encoding="utf-8")
    mgr_header = Path("src/server/game/Bots/BotWorldPopulationMgr.h").read_text(encoding="utf-8")
    mgr_impl = Path("src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")
    commands = Path("src/server/scripts/Commands/cs_healerbot.cpp").read_text(encoding="utf-8")
    cmake = Path("src/server/game/CMakeLists.txt").read_text(encoding="utf-8")
    schema = Path("sql/updates/characters/4.3.4/2026_06_12_01_characters_bot_experiment_segments.sql").read_text(encoding="utf-8")

    for symbol in [
        "BotExperimentDefinition",
        "BotExperimentTrigger",
        "BotExperimentSegment",
        "BotExperimentSegmentStatus",
        "HandleTelemetryEvent",
    ]:
        assert symbol in header

    for experiment in [
        "autonomous_exploration_v1",
        "quest_discovery_v1",
        "quest_execution_v1",
        "combat_survival_v1",
        "death_recovery_v1",
        "stuck_recovery_v1",
    ]:
        assert experiment in impl

    for event_type in ["quest_accepted", "quest_completed", "death", "resurrected", "combat_started", "stuck_detected"]:
        assert event_type in impl

    assert "CREATE TABLE IF NOT EXISTS `experiment_bot_segments`" in schema
    for column in [
        "`parent_run_id` bigint unsigned NULL",
        "`experiment_name` varchar(128) NOT NULL",
        "`trigger_event_id` bigint unsigned NULL",
        "`clip_id` bigint unsigned NULL",
        "`bot_guid` int unsigned NOT NULL",
        "`brain_version` varchar(64) NULL",
        "`status` varchar(32) NOT NULL DEFAULT 'running'",
        "`result` varchar(64) NULL",
        "`started_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "`ended_at` timestamp NULL DEFAULT NULL",
        "`map_id` int unsigned NULL",
        "`zone_id` int unsigned NULL",
        "`area_id` int unsigned NULL",
        "`x` float NULL",
        "`y` float NULL",
        "`z` float NULL",
        "`trigger_json` text NULL",
        "`summary_json` text NULL",
    ]:
        assert column in schema

    assert "BotExperimentCoordinator _experimentCoordinator" in mgr_header
    assert "RecordExperimentSegmentEvent" in mgr_header
    assert "RecordExperimentSegmentEvent(bot, eventType, result, questId" in mgr_impl
    assert "RecordExperimentSegmentEvent(bot, eventType, result, 0" in mgr_impl
    assert "segment_counts" in mgr_impl
    assert "experiment_bot_segments" in commands
    assert "experiment_bot_clips" in commands
    assert "experiment_bot_clip_frames" in commands
    assert "BotExperimentCoordinator.cpp" in cmake


def test_phase14_telemetry_clip_storage_surface():
    schema = Path("sql/updates/characters/4.3.4/2026_06_12_00_characters_bot_telemetry_clips.sql").read_text(encoding="utf-8")
    buffer_header = Path("src/server/game/Bots/BotTelemetryBuffer.h").read_text(encoding="utf-8")
    buffer_impl = Path("src/server/game/Bots/BotTelemetryBuffer.cpp").read_text(encoding="utf-8")
    commands = Path("src/server/scripts/Commands/cs_healerbot.cpp").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS `experiment_bot_clips`" in schema
    for column in [
        "`experiment_id` bigint unsigned NULL",
        "`run_id` bigint unsigned NULL",
        "`segment_id` bigint unsigned NULL",
        "`bot_guid` int unsigned NOT NULL",
        "`trigger_event_id` bigint unsigned NULL",
        "`trigger_type` varchar(64) NOT NULL",
        "`importance_score` float NOT NULL DEFAULT '0'",
        "`reason` varchar(128) NOT NULL DEFAULT ''",
        "`brain_version` varchar(64) NOT NULL DEFAULT ''",
        "`started_at` datetime NOT NULL",
        "`ended_at` datetime NULL",
        "`status` varchar(32) NOT NULL DEFAULT 'open'",
        "`summary_json` mediumtext NULL",
        "KEY `idx_bot_id` (`bot_guid`, `id`)",
        "KEY `idx_trigger_id` (`trigger_type`, `id`)",
        "KEY `idx_segment_id` (`segment_id`)",
    ]:
        assert column in schema

    assert "CREATE TABLE IF NOT EXISTS `experiment_bot_clip_frames`" in schema
    for column in [
        "`clip_id` bigint unsigned NOT NULL",
        "`frame_offset_ms` int NOT NULL",
        "`target_guid` bigint unsigned NOT NULL DEFAULT '0'",
        "`quest_id` int unsigned NOT NULL DEFAULT '0'",
        "`raw_json` mediumtext NULL",
        "`semantic_json` mediumtext NULL",
        "KEY `idx_clip_frame` (`clip_id`, `id`)",
    ]:
        assert column in schema

    assert "experiment_bot_clips" in commands
    assert "experiment_bot_clip_frames" in commands
    assert "experiment_bot_telemetry_clips" not in commands
    assert "experiment_bot_telemetry_frames" not in commands
    assert "persisted_pre_frames" in buffer_header
    assert "persisted_post_frames" in buffer_header
    assert "decision.reason.c_str()" in Path("src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")
    assert "INSERT INTO experiment_bot_clips" in buffer_impl
    assert "INSERT INTO experiment_bot_clip_frames" in buffer_impl
    assert "InsertFrameRows(clip.clip_id, clip.trigger_time_ms, clip.pre_frames, 0)" in buffer_impl


def strict_stonecore_report(routes: list[dict], entries: list[dict]) -> dict:
    return {
        "source_live_report": "stonecore_strict.json",
        "validation_context": {"scenario_id": "stonecore_5n"},
        "completion_reason": "validation_route_manifest_complete",
        "acceptable_final_evidence": True,
        "validation_route_manifest": {
            "schema": "bot_live_validation_route_manifest_v1",
            "scenario_id": "stonecore_5n",
            "route_count": len(routes),
            "expected_segments": [f"{int(route['step']):02d}_{route['label'].lower()}" for route in routes],
            "routes": routes,
        },
        "trace": {"entries": entries},
        "summary": {"trash_pulls": 1},
        "evidence": {"failures": 0, "trash_pulls": 1},
        "failure_labels": [],
        "failure_reason": "",
    }


def strict_stonecore_scenario(tmp_path: Path, routes: list[dict]) -> Path:
    scenario_dir = tmp_path / "validation_scenarios"
    write_jsonl(
        scenario_dir / "validation_scenarios.jsonl",
        [{"scenario_id": "stonecore_5n", "instance": "The Stonecore", "map_id": 725, "difficulty": "normal_5man", "boss_count": sum(route["kind"] == "boss" for route in routes)}],
    )
    write_jsonl(scenario_dir / "validation_routes.jsonl", [{"scenario_id": "stonecore_5n", **route} for route in routes])
    return scenario_dir


def test_strict_full_clear_rejects_stale_terminal_evidence(tmp_path):
    routes = [
        {"step": 1, "kind": "trash", "label": "trash", "route_node_id": "stonecore_trash"},
        {"step": 2, "kind": "boss", "label": "boss", "route_node_id": "stonecore_boss"},
    ]
    scenario_dir = strict_stonecore_scenario(tmp_path, routes)
    report = strict_stonecore_report(
        routes,
        [
            {"action": "trash_action", "result": "ok", "route_node_id": "stonecore_trash", "route_generation": 1},
            {"action": "validation_route_terminal", "result": "trash_cluster_cleared", "route_node_id": "stonecore_trash", "route_generation": 1},
            {"action": "validation_route_terminal", "result": "trash_cluster_cleared", "route_node_id": "stonecore_boss", "route_generation": 1},
            {"action": "boss_killed", "result": "ok", "target_id": 42, "route_node_id": "stonecore_boss", "route_generation": 2},
        ],
    )

    stonecore = build_live_scenario_reports(report, scenario_dir)["stonecore_5n"]

    assert stonecore["clear_complete"] is False
    assert stonecore["missing_terminal_route_nodes"] == ["stonecore_boss"]
    assert stonecore["missing_segments"] == ["02_boss"]


def test_strict_full_clear_requires_real_kill_for_each_boss(tmp_path):
    routes = [
        {"step": 1, "kind": "boss", "label": "boss_one", "route_node_id": "boss_one"},
        {"step": 2, "kind": "boss", "label": "boss_two", "route_node_id": "boss_two"},
    ]
    scenario_dir = strict_stonecore_scenario(tmp_path, routes)
    report = strict_stonecore_report(
        routes,
        [
            {"action": "validation_route_terminal", "result": "boss_killed", "route_node_id": "boss_one", "route_generation": 1},
            {"action": "boss_killed", "result": "ok", "target_id": 11, "route_node_id": "boss_one", "route_generation": 1},
            {"action": "validation_route_terminal", "result": "boss_killed", "route_node_id": "boss_two", "route_generation": 2},
        ],
    )

    stonecore = build_live_scenario_reports(report, scenario_dir)["stonecore_5n"]

    assert stonecore["clear_complete"] is False
    assert stonecore["boss_kills"] == 1
    assert stonecore["missing_boss_route_nodes"] == ["boss_two"]


def test_strict_full_clear_rejects_teacher_or_forced_kill(tmp_path):
    routes = [{"step": 1, "kind": "boss", "label": "boss", "route_node_id": "stonecore_boss"}]
    scenario_dir = strict_stonecore_scenario(tmp_path, routes)
    report = strict_stonecore_report(
        routes,
        [
            {"action": "validation_route_teacher_assist", "result": "boss_route_no_health_progress", "route_node_id": "stonecore_boss", "route_generation": 1},
            {"action": "boss_killed", "result": "ok", "target_id": 9, "route_node_id": "stonecore_boss", "route_generation": 1},
            {"action": "validation_route_terminal", "result": "boss_killed", "route_node_id": "stonecore_boss", "route_generation": 1},
        ],
    )

    stonecore = build_live_scenario_reports(report, scenario_dir)["stonecore_5n"]

    assert stonecore["clear_complete"] is False
    assert stonecore["strict_completion_evidence"] is False
    assert stonecore["forbidden_completion_assists"] == [{"action": "validation_route_teacher_assist", "result": "boss_route_no_health_progress"}]


def test_stuck_recovery_requires_progress_after_latest_failure():
    base_entries = [
        {"action": "mob_killed", "result": "ok", "sequence": 1},
        {"action": "validation_route_recovery", "result": "validation_route_stuck_safe_memory", "sequence": 10},
        *[{"action": "stuck_detected", "result": "repath", "sequence": 11 + index} for index in range(8)],
    ]
    output_before_only = "\n".join(
        [
            'TC> {"active_bots":1,"target_bots":1,"decisions":20}',
            "TC> " + json.dumps({"trace_schema_version": 1, "entries": base_entries}),
        ]
    )
    output_with_post_progress = "\n".join(
        [
            'TC> {"active_bots":1,"target_bots":1,"decisions":21}',
            "TC> " + json.dumps({"trace_schema_version": 1, "entries": [*base_entries, {"action": "validation_route_terminal", "result": "trash_cluster_cleared", "sequence": 21, "route_node_id": "trash", "route_generation": 1}]}),
        ]
    )

    before_only = live_validation_report(output_before_only)
    with_post_progress = live_validation_report(output_with_post_progress)

    assert before_only["evidence"]["post_failure_progress"] is False
    assert "validation_route_stuck_loop" in before_only["failure_labels"]
    assert with_post_progress["evidence"]["post_failure_progress"] is True
    assert "validation_route_stuck_loop" not in with_post_progress["failure_labels"]


def test_stuck_recovery_ignores_historical_block_resolution():
    entries = [
        {"sequence": 1, "route_node_id": "trash", "route_generation": 1, "blocked_current_reason": "", "blocked_resolved_by": "movement_progress"},
        {"action": "validation_route_recovery", "result": "validation_route_stuck_safe_memory", "sequence": 2, "route_node_id": "trash", "route_generation": 1},
        *[{"action": "stuck_detected", "result": "repath", "sequence": 10 + index, "route_node_id": "trash", "route_generation": 1} for index in range(8)],
    ]
    report = live_validation_report('TC> {"active_bots":1,"target_bots":1,"decisions":20}\nTC> ' + json.dumps({"trace_schema_version": 1, "entries": entries}))

    assert report["evidence"]["post_failure_progress"] is False
    assert "validation_route_stuck_loop" in report["failure_labels"]


def test_stuck_recovery_accepts_later_same_scope_movement_resolution():
    entries = [
        {"action": "validation_route_recovery", "result": "validation_route_stuck_safe_memory", "sequence": 2, "route_node_id": "trash", "route_generation": 1},
        *[{"action": "stuck_detected", "result": "repath", "sequence": 10 + index, "route_node_id": "trash", "route_generation": 1} for index in range(8)],
        {"sequence": 20, "route_node_id": "trash", "route_generation": 1, "blocked_current_reason": "", "blocked_resolved_by": "movement_progress"},
    ]
    report = live_validation_report('TC> {"active_bots":1,"target_bots":1,"decisions":20}\nTC> ' + json.dumps({"trace_schema_version": 1, "entries": entries}))

    assert report["evidence"]["post_failure_progress"] is True
    assert "validation_route_stuck_loop" not in report["failure_labels"]


def test_stuck_recovery_rejects_wrong_scope_block_resolution():
    entries = [
        {"action": "validation_route_recovery", "result": "validation_route_stuck_safe_memory", "sequence": 2, "route_node_id": "trash", "route_generation": 1},
        *[{"action": "stuck_detected", "result": "repath", "sequence": 10 + index, "route_node_id": "trash", "route_generation": 1} for index in range(8)],
        {"sequence": 20, "route_node_id": "boss", "route_generation": 2, "blocked_current_reason": "", "blocked_resolved_by": "route_target_combat_progress"},
    ]
    report = live_validation_report('TC> {"active_bots":1,"target_bots":1,"decisions":20}\nTC> ' + json.dumps({"trace_schema_version": 1, "entries": entries}))

    assert report["evidence"]["post_failure_progress"] is False
    assert "validation_route_stuck_loop" in report["failure_labels"]


def test_unresolved_route_stuck_count_resets_recovered_history_at_pack_terminal():
    scope = {"route_node_id": "corridor", "route_generation": 1}
    entries = [
        *[{"action": "stuck_detected", "sequence": index, **scope} for index in range(1, 9)],
        {"action": "validation_route_pack_terminal", "sequence": 9, **scope},
        {"action": "stuck_detected", "sequence": 10, **scope},
    ]

    assert unresolved_route_stuck_count(entries) == 1


def test_unresolved_route_stuck_count_reaches_threshold_after_latest_progress():
    scope = {"route_node_id": "corridor", "route_generation": 1}
    entries = [
        {"action": "validation_route_pack_terminal", "sequence": 1, **scope},
        *[{"action": "stuck_detected", "sequence": index, **scope} for index in range(2, 10)],
    ]

    assert unresolved_route_stuck_count(entries) == 8


def test_unresolved_route_stuck_count_ignores_wrong_scope_terminal():
    scope = {"route_node_id": "corridor", "route_generation": 1}
    entries = [
        *[{"action": "stuck_detected", "sequence": index, **scope} for index in range(1, 9)],
        {"action": "validation_route_terminal", "sequence": 9, "route_node_id": "boss", "route_generation": 2},
    ]

    assert unresolved_route_stuck_count(entries) == 8


def test_unresolved_route_stuck_count_rejects_script_activation_without_later_progress():
    scope = {"route_node_id": "boss", "route_generation": 4}
    failures = [{"action": "stuck_detected", "sequence": index, **scope} for index in range(1, 9)]

    assert unresolved_route_stuck_count([
        *failures,
        {"action": "validation_route_activation", "result": "boss_route_early_activation", "sequence": 9, **scope},
    ]) == 8
    assert unresolved_route_stuck_count([
        *failures,
        {"action": "validation_route_activation", "result": "target_not_found", "sequence": 9, **scope},
    ]) == 8


def test_scripted_activation_wait_requires_recent_real_same_scope_target_search():
    scope = {"route_node_id": "boss", "route_generation": 4}
    failures = [{"action": "stuck_detected", "timestamp_ms": 1000 + index, **scope} for index in range(8)]
    activation = {"action": "validation_route_activation", "result": "boss_route_early_activation", "timestamp_ms": 2000, **scope}
    target = {"action": "validation_route_target_search", "result": "target_seen_not_attackable", "target_id": 86, "timestamp_ms": 3000, **scope}

    assert scripted_activation_wait_pending([*failures, activation], 3000) is False
    assert scripted_activation_wait_pending([*failures, activation, target], 3001) is True
    assert scripted_activation_wait_pending([*failures, activation, {**target, "target_id": 0}], 3001) is False
    assert scripted_activation_wait_pending([*failures, activation, {**target, "action": "unrelated"}], 3001) is False
    assert scripted_activation_wait_pending([*failures, activation, target], 32001) is False
    assert scripted_activation_wait_pending([
        *failures, activation,
        {**target, "route_node_id": "other", "route_generation": 5},
    ], 3001) is False


def test_scripted_activation_wait_does_not_hide_another_max_stuck_scope():
    scope_a = {"route_node_id": "a", "route_generation": 1}
    scope_b = {"route_node_id": "b", "route_generation": 2}
    entries = [
        *[{"action": "stuck_detected", "timestamp_ms": 1000 + index, **scope_a} for index in range(8)],
        *[{"action": "stuck_detected", "timestamp_ms": 2000 + index, **scope_b} for index in range(8)],
        {"action": "validation_route_activation", "timestamp_ms": 3000, **scope_b},
        {"action": "validation_route_target_search", "result": "target_seen_not_attackable", "target_id": 86, "timestamp_ms": 3001, **scope_b},
    ]

    assert scripted_activation_wait_pending(entries, 3001) is False


def test_scripted_activation_wait_does_not_hide_larger_unscoped_stuck_history():
    scope = {"route_node_id": "boss", "route_generation": 4}
    entries = [
        *[{"action": "stuck_detected", "timestamp_ms": 1000 + index} for index in range(12)],
        *[{"action": "stuck_detected", "timestamp_ms": 2000 + index, **scope} for index in range(8)],
        {"action": "validation_route_activation", "timestamp_ms": 3000, **scope},
        {"action": "validation_route_target_search", "result": "target_seen_not_attackable", "target_id": 86, "timestamp_ms": 3001, **scope},
    ]

    assert scripted_activation_wait_pending(entries, 3001) is False


def test_unresolved_route_stuck_count_accepts_same_scope_movement_resolution():
    scope = {"route_node_id": "corridor", "route_generation": 1}
    entries = [
        *[{"action": "stuck_detected", "sequence": index, **scope} for index in range(1, 9)],
        {"sequence": 9, "blocked_current_reason": "", "blocked_resolved_by": "movement_progress", **scope},
    ]

    assert unresolved_route_stuck_count(entries) == 0


def test_trace_order_rejects_sequence_progress_against_timestamp_failure():
    failure = {"action": "stuck_detected", "timestamp_ms": 1000}
    progress = {"action": "validation_route_pack_terminal", "sequence": 9999}

    assert trace_after(progress, failure) is False
    assert unresolved_route_stuck_count([failure, progress]) == 1


def test_trace_order_rejects_timestamp_progress_against_sequence_failure():
    failure = {"action": "stuck_detected", "sequence": 10}
    progress = {"action": "validation_route_pack_terminal", "timestamp_ms": 999999}

    assert trace_after(progress, failure) is False
    assert unresolved_route_stuck_count([failure, progress]) == 1


def test_mixed_order_progress_cannot_hide_reviewer_stuck_repro():
    scope = {"route_node_id": "corridor", "route_generation": 1}
    failures = [{"action": "stuck_detected", "timestamp_ms": 1000 + index, **scope} for index in range(8)]
    sequence_only_terminal = {"action": "validation_route_pack_terminal", "sequence": 5000, **scope}
    entries = [*failures, sequence_only_terminal, {"action": "validation_route_trash_action", "sequence": 5001, **scope}]
    output = 'TC> {"active_bots":1,"target_bots":1,"decisions":20}\nTC> ' + json.dumps({"trace_schema_version": 1, "entries": entries})

    report = live_validation_report(output)

    assert report["evidence"]["post_failure_progress"] is False
    assert report["evidence"]["unresolved_route_stuck_events"] == 8
    assert "validation_route_stuck_loop" in report["failure_labels"]


def test_live_validation_deduplicates_redundant_stuck_counter_views():
    entries = [{"action": "stuck_detected", "sequence": index} for index in range(1, 9)]
    output = "\n".join([
        'TC> {"active_bots":1,"target_bots":1,"decisions":20,"stuck":12}',
        "TC> " + json.dumps({"trace_schema_version": 1, "entries": entries}),
        'TC> {"duration_minutes":1,"decisions":20,"stuck_events":12}',
    ])

    report = live_validation_report(output)

    assert report["evidence"]["stuck_events"] == 12
    assert report["evidence"]["unresolved_route_stuck_events"] == 12


def test_stuck_loop_uses_only_failures_unresolved_since_pack_terminal():
    scope = {"route_node_id": "corridor", "route_generation": 1}
    recovered = [
        {"action": "validation_route_trash_action", "sequence": 1, **scope},
        *[{"action": "stuck_detected", "sequence": index, **scope} for index in range(2, 10)],
        {"action": "validation_route_pack_terminal", "sequence": 10, **scope},
        {"action": "stuck_detected", "sequence": 11, **scope},
    ]
    unresolved = [
        {"action": "validation_route_trash_action", "sequence": 1, **scope},
        {"action": "validation_route_pack_terminal", "sequence": 2, **scope},
        *[{"action": "stuck_detected", "sequence": index, **scope} for index in range(3, 11)],
    ]
    def report(entries):
        return live_validation_report('TC> {"active_bots":1,"target_bots":1,"decisions":20}\nTC> ' + json.dumps({"trace_schema_version": 1, "entries": entries}))

    recovered_report = report(recovered)
    unresolved_report = report(unresolved)

    assert recovered_report["evidence"]["unresolved_route_stuck_events"] == 1
    assert "validation_route_stuck_loop" not in recovered_report["failure_labels"]
    assert unresolved_report["evidence"]["unresolved_route_stuck_events"] == 8
    assert "validation_route_stuck_loop" in unresolved_report["failure_labels"]


def test_validation_status_requires_exact_scoped_terminal_and_boss_evidence(tmp_path):
    routes = [
        {"step": 1, "kind": "trash", "label": "trash", "route_node_id": "stonecore_trash"},
        {"step": 2, "kind": "boss", "label": "boss", "route_node_id": "stonecore_boss"},
    ]
    scenario_dir = strict_stonecore_scenario(tmp_path, routes)
    report = strict_stonecore_report(
        routes,
        [
            {"action": "trash_action", "result": "ok", "route_node_id": "stonecore_trash", "route_generation": 1},
            {"action": "validation_route_terminal", "result": "trash_cluster_cleared", "route_node_id": "stonecore_trash", "route_generation": 1},
            {"action": "boss_killed", "result": "ok", "target_id": 9, "route_node_id": "stonecore_boss", "route_generation": 2},
            {"action": "validation_route_terminal", "result": "boss_killed", "route_node_id": "stonecore_boss", "route_generation": 2},
        ],
    )
    scenario_report = build_live_scenario_reports(report, scenario_dir)["stonecore_5n"]
    report_root = tmp_path / "scenario_reports"
    report_root.mkdir()
    (report_root / "stonecore_5n.json").write_text(json.dumps(scenario_report), encoding="utf-8")
    plan = {
        "scenarios": [
            {
                "scenario_id": "stonecore_5n",
                "instance": "The Stonecore",
                "difficulty": "normal_5man",
                "segments": [
                    {"segment_id": "01_trash", "route_node_id": "stonecore_trash", "kind": "trash", "label": "trash", "mechanic_profile": "", "live_output_dir": str(tmp_path / "missing-trash")},
                    {"segment_id": "02_boss", "route_node_id": "stonecore_boss", "kind": "boss", "label": "boss", "mechanic_profile": "", "live_output_dir": str(tmp_path / "missing-boss")},
                ],
            }
        ]
    }

    status = build_validation_run_status(plan, report_root)

    assert status["all_ready"] is True
    assert status["scenarios"][0]["present_segments"] == ["01_trash", "02_boss"]
    assert {row["evidence_source"] for row in status["scenarios"][0]["segment_reports"]} == {"scenario_segment_result"}
