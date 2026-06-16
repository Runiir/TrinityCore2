from __future__ import annotations

import json
from pathlib import Path

from ml.evaluation.evaluate_action_frequency import main as evaluate_main
from ml.group_roles.coordination import ReservationStore
from ml.group_roles.metrics import group_role_metrics
from ml.group_roles.policies import policy_for_role
from ml.raid.metrics import raid_metrics
from ml.raid.scheduler import RaidAssignmentScheduler
from tools.bot_ml.common import EXPORT_TABLES, numeric_features
from tools.bot_ml.build_decision_dataset import build_row, build_rows, index_semantic_stats
from tools.bot_ml.extract_world_knowledge import (
    build_quest_objectives,
    build_rewards,
    database_url_from_worldserver_conf,
    extract_world_knowledge,
    main as world_knowledge_main,
    parse_trinity_database_info,
    sanitize_database_url,
)
from tools.bot_ml.build_world_planner_manifests import build_planner_manifests
from tools.bot_ml.validate_world_planner import STAGED_GATES, validate_manifest_coverage
from tools.bot_ml.build_validation_scenario_manifests import build_manifests as build_validation_scenario_manifests
from tools.bot_ml.build_live_scenario_reports import build_reports as build_live_scenario_reports, build_reports_from_live_reports, main as live_scenario_reports_main
from tools.bot_ml.build_validation_run_plan import build_plan as build_validation_run_plan
from tools.bot_ml.build_validation_run_status import build_status as build_validation_run_status
from tools.bot_ml.run_live_bot_validation import build_bot_pool_reset_sql, command_script, live_validation_report, load_scenario_reports, main as live_validation_main, parse_json_objects, parse_soap_result, run_worldserver, split_sql_statements, trinity_config_bool
from tools.bot_ml.build_validation_gear_profiles import build_gem_catalog, build_profiles, build_report, fetch_items, load_gem_properties, load_spell_item_enchantments
from tools.bot_ml.build_validation_provisioning import apply_gear_profiles, build_account_insert_sql, main as provisioning_main, scenario_report, srp6_registration_data
from tools.bot_ml.validate_validation_provisioning import build_report as provisioning_verify_report
from tools.bot_ml.validate_validation_provisioning import main as provisioning_verify_main
from tools.bot_ml.validate_validation_provisioning import validate_database as validate_provisioning_database
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
    assert rows[0]["failure_label"] == ""
    assert rows[1]["imitate_teacher"] == 0
    assert rows[1]["teacher_action_quality"] == "candidate_unobserved"
    assert rows[0]["trace"]["candidate_activity"] == "quest"


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
        "dataset/live_validation_combined",
    ]:
        assert stage in dvc


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
    assert set(manifests) == {"quests", "quest_objectives", "npc_services", "item_sources", "recipe_sources", "material_sources", "travel", "zones"}
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

    assert {"areatrigger_teleport", "transport", "graveyard", "taxi_level"} <= {entry["type"] for entry in manifests["travel"]}
    assert manifests["zones"] == [{"map_id": 0, "zone_id": 12, "creature_spawns": 3, "gameobject_spawns": 1, "areas": [40, 41, 42]}]


def test_world_planner_builder_derives_hubs_clusters_services_and_travel(tmp_path, monkeypatch):
    fake_db = FakeWorldDb()
    monkeypatch.setattr("tools.bot_ml.extract_world_knowledge.connect_mysql", lambda _url: fake_db)
    world = extract_world_knowledge("mysql://example/world")
    world_dir = tmp_path / "world"
    for name, rows in world.items():
        write_jsonl(world_dir / f"{name}.jsonl", rows)

    planner = build_planner_manifests(world_dir)

    assert set(planner) == {"quest_hubs", "quest_chains", "objective_clusters", "service_index", "item_source_index", "recipe_source_index", "material_source_index", "travel_edges"}
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

    item_source = next(row for row in planner["item_source_index"] if row["item_id"] == 700)
    assert item_source["source_count"] == 2
    assert item_source["source_types"] == ["creature_loot", "vendor"]

    recipe_source = next(row for row in planner["recipe_source_index"] if row["recipe_spell_id"] == 600)
    assert recipe_source["source_count"] == 1
    assert recipe_source["profession_skill_ids"] == [185]
    assert recipe_source["source_types"] == ["trainer"]

    material_source = next(row for row in planner["material_source_index"] if row["item_id"] == 700)
    assert material_source["source_count"] == 2
    assert material_source["source_types"] == ["creature_loot", "vendor"]
    assert material_source["nearest_source"]["source_entry"] == 200

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
    report = validate_manifest_coverage(build_planner_manifests(world_dir), validation_manifests)
    gates = {gate["gate"]: gate for gate in report["gates"]}

    assert [gate["gate"] for gate in report["gates"]] == STAGED_GATES
    for gate in [
        "movement_smoke",
        "kill_quest",
        "collect_quest",
        "quest_hub_batching",
        "trainer_visit",
        "vendor_repair",
        "profession_recipe_acquisition",
        "material_farming",
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
        build_planner_manifests(world_dir),
        live_ready_manifests,
        {
            "stonecore_5n": {"scenario_id": "stonecore_5n", "prepared_group": True, "boss_kills": 4, "clear_complete": True, "teacher_label_quality": "medium"},
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
    assert scenarios["stonecore_5n"]["boss_count"] == 4
    assert scenarios["blackwing_descent_10n"]["boss_count"] == 6
    assert any(row["scenario_id"] == "stonecore_5n" and row["kind"] == "trash" for row in routes)
    assert any(row["scenario_id"] == "blackwing_descent_10n" and row["kind"] == "boss" and row["coordinates_valid"] is True and row["source_entry"] == 41570 for row in routes)
    assert any(row["scenario_id"] == "blackwing_descent_10n" and "raid_aoe" in row["families"] for row in mechanics)
    assert manifests["report"]["ready_scenarios"] == 2
    assert manifests["report"]["invalid_route_steps"] == []
    assert manifests["report"]["invalid_mechanic_profiles"] == []


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
    assert "stonecore_5n" in stonecore["live_validate_command"]
    assert "blackwing_descent_10n" in bwd["live_validate_command"]
    assert bwd["scenario_report_command"].count("--scenario-id") == 1
    assert "pixi" in stonecore["live_validate_shell"]


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

    assert bwd["segment_count"] == 6
    assert [segment["label"] for segment in bwd["segments"]][0] == "Magmaw"
    assert bwd["segments"][-1]["segment_id"] == "08_nefarian"
    assert bwd["scenario_report_command"].count("--live-report") == 6
    assert "dataset/live_validation_scenarios/blackwing_descent_10n/02_magmaw/report.json" in bwd["scenario_report_command"]
    first_command = bwd["segments"][0]["live_validate_command"]
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
                "scenario_report_shell": "pixi run bot-live-scenario-reports --scenario-id blackwing_descent_10n",
                "segments": [
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
                    "mechanic_profile": "magmaw",
                },
                "trace": {"entries": [{"action": "raid_boss_killed"}]},
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
    assert bwd["missing_segments"] == ["03_omnotron"]
    assert bwd["invalid_segments"] == []
    assert bwd["blockers"] == ["missing_segment_live_reports", "incomplete_segment_coverage", "scenario_clear_not_complete"]
    assert bwd["next_commands"][0] == "pixi run bot-live-validate --validation-segment-id 03_omnotron"
    assert bwd["next_commands"][-1].startswith("pixi run bot-live-scenario-reports")


def test_validation_run_status_reruns_invalid_existing_segment_reports(tmp_path):
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


def test_live_bot_validation_command_script_and_output_parser():
    script = command_script(selector="all", trace_limit=20, start=True, stop=True)

    assert script.splitlines() == [
        ".botauto start",
        ".botauto status",
        ".botauto diagnose all",
        ".botauto trace all 20",
        ".botexp summary",
        ".botauto stop",
        "server shutdown force 0",
    ]

    output = """
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

    assert len(payloads) == 4
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
    assert gates["movement_smoke"]["passed"] is True
    assert gates["kill_quest"]["passed"] is True
    assert gates["collect_quest"]["passed"] is True
    assert gates["quest_hub_batching"]["passed"] is True
    assert gates["full_stonecore_clear"]["passed"] is False
    assert "stonecore_live_clear_report" in gates["full_stonecore_clear"]["missing"]
    assert report["runtime_ml_control"] == "disabled_until_live_validation_passes"


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
        json.dumps({"scenario_id": "stonecore_5n", "prepared_group": True, "trash_pulls": 4, "boss_kills": 4, "clear_complete": True}),
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


def test_live_scenario_report_builder_derives_per_scenario_artifacts(tmp_path):
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
    assert reports["stonecore_5n"]["boss_kills"] == 4
    assert reports["stonecore_5n"]["clear_complete"] is True
    assert reports["stonecore_5n"]["scenario_evidence_mode"] == "generic_live_trace_inference"
    assert reports["stonecore_5n"]["teacher_label_quality"] == "weak"
    assert reports["stonecore_5n"]["ml_training_label"] == "weak_inferred_label"
    assert reports["blackwing_descent_10n"]["raid_boss_kills"] == 1
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
        [{"scenario_id": "stonecore_5n", "kind": "boss"} for _ in range(4)],
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
            }
        },
    }

    reports = build_live_scenario_reports(live_report, scenario_dir)
    stonecore = reports["stonecore_5n"]

    assert stonecore["clear_complete"] is True
    assert stonecore["source_scenario_report_attached"] is True
    assert stonecore["scenario_evidence_mode"] == "attached_scenario_report"
    assert stonecore["scenario_evidence_modes"] == ["attached_scenario_report"]
    assert stonecore["teacher_label_quality"] == "medium"
    assert stonecore["ml_training_label"] == "candidate_teacher_label"


def test_live_scenario_report_builder_aggregates_segmented_raid_progress(tmp_path):
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
                    "mechanic_profile": f"boss_{index}",
                },
                "trace_entries": 1,
                "trace": {"entries": [{"action": "raid_boss_killed", "situation": "raid_boss"}]},
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
    assert bwd["clear_complete"] is True
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
                "mechanic_profile": "boss_0",
            },
            "trace_entries": 1,
            "trace": {"entries": [{"action": "raid_boss_killed", "situation": "raid_boss"}]},
            "summary": {"raid_boss_kills": 1},
            "evidence": {"failures": 0},
            "stages": [{"stage": "raid_boss", "passed": True}],
        }
        for index in range(6)
    ]

    bwd = build_reports_from_live_reports(live_reports, scenario_dir)["blackwing_descent_10n"]

    assert bwd["raid_boss_kills"] == 6
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
        "    print('CMD ' + line.strip())\n"
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
        "    print('CMD ' + line.strip())\n"
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
                "label": "Magmaw",
                "kind": "boss",
                "mechanic_profile": "magmaw",
                "map_id": 669,
                "x": -302.467,
                "y": -31.7101,
                "z": 210.8483,
                "o": 4.118977,
                "source_entry": 41570,
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
    assert 'BotWorld.ValidationRoute.NodeId = "bwd_magmaw"' in generated_config
    assert "BotWorld.ValidationRoute.TargetEntry = 41570" in generated_config
    assert "BotProgression.AllowDungeons = 1" in generated_config


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
    assert "DELETE FROM `characters`.`character_queststatus`" in sql
    assert "DELETE FROM `characters`.`bot_memory_failed_paths`" in sql
    assert "bot_semantic_outcome_stats" not in sql
    assert statements[0].startswith("UPDATE `characters`.`character_bot_pool`")
    assert len(statements) >= 10


def test_live_bot_validation_dry_run_writes_reset_and_provisioning_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.bot_ml.run_live_bot_validation.database_url_from_worldserver_conf", lambda _path, key="WorldDatabaseInfo": f"mysql://trinity:secret@db.example:3306/{'auth' if key == 'LoginDatabaseInfo' else 'characters' if key == 'CharacterDatabaseInfo' else 'world'}")
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

    assert report["dry_run"] is True
    assert report["preparation"]["bot_pool_reset"]["applied"] is False
    assert report["preparation"]["bot_pool_reset"]["tags"] == ["test_account"]
    assert report["preparation"]["validation_provisioning"]["applied"] is False
    assert "UPDATE `characters`.`character_bot_pool`" in reset_sql
    assert "INSERT INTO `auth`.`account`" in account_sql
    assert "INSERT INTO `characters`.`characters`" in character_sql


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
    assert scenarios["blackwing_descent_10n"]["role_counts"] == {"tank": 2, "healer": 3, "dps": 5}
    assert scenarios["stonecore_5n"]["start_position"]["map_id"] == 725
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
    assert "account create BWDVALTKA validation" in commands
    assert "INSERT INTO `auth`.`account`" in account_sql
    assert "`salt`, `verifier`" in account_sql
    assert "ON DUPLICATE KEY UPDATE `expansion`" in account_sql
    assert "INSERT INTO `characters`.`characters`" in sql
    assert "INSERT INTO `characters`.`character_bot_pool`" in sql
    assert "INSERT INTO `characters`.`character_skills`" in sql
    assert "INSERT INTO `characters`.`character_glyphs`" in sql
    assert "DELETE FROM `characters`.`item_instance` WHERE `guid` >= 9700000" in sql
    assert manifest["schema"] == "bot_validation_provisioning_manifest_v1"
    assert manifest["bot_count"] == 15
    assert generated_report == report


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

    profiles = build_profiles(config, items)
    report = build_report(profiles, {"database": "hotfixes"})
    profile = profiles["protection_paladin"]

    assert profile["complete_equipment_slots"] is True
    assert profile["missing_slots"] == []
    assert {item["slot"] for item in profile["equipment"]} == set(inv_by_slot)
    assert report["all_equipment_slots_complete"] is True
    assert report["all_enchanted"] is False


def test_validation_gear_profiles_complete_from_local_db2_files():
    config = json.loads(Path("experiments/configs/validation_provisioning_cata_001.json").read_text(encoding="utf-8"))
    items = fetch_items("mysql://trinity:trinity@172.20.0.2:3306/hotfixes", Path("data/dbc/enUS"), min_item_level=1, max_required_level=85)
    enchantments = load_spell_item_enchantments(Path("data/dbc/enUS"))
    gems = build_gem_catalog(items, load_gem_properties(Path("data/dbc/enUS")), {int(enchantment["id"]): enchantment for enchantment in enchantments})
    profiles = build_profiles(config, items, enchantments, gems)
    report = build_report(profiles, {"database": "hotfixes"})

    assert report["profile_count"] == 13
    assert report["all_equipment_slots_complete"] is True
    assert report["all_gemmed"] is True
    assert report["all_enchanted"] is True
    assert report["source_counts"]["enchanted_items"] >= 13 * 16
    assert report["source_counts"]["gemmed_items"] == report["source_counts"]["socketed_items"]
    assert report["enchant_applicability_verified_by_server"] is False
    assert report["source_counts"]["client_db2_items"] >= 13 * 16
    assert all(not profile["missing_slots"] for profile in profiles.values())
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
            "equipment": [{"slot": slot, "item_id": 1000 + slot, "enchant_id": 0, "gem_item_ids": []} for slot in [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]]
        }
    }

    equipped = apply_gear_profiles(config, profiles)
    report = scenario_report(equipped)

    assert equipped["scenarios"][0]["bots"][0]["gear_profile"] == "protection_paladin"
    assert len(equipped["scenarios"][0]["bots"][0]["equipment"]) == 16
    assert report["scenarios"][0]["gear_missing_slots"]["Tank"] == []
    assert "complete_equipment_slots" not in report["scenarios"][0]["missing"]
    assert "enchants" in report["scenarios"][0]["missing"]


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
                    {"account": "SCVALTANK", "name": "ScValTank"},
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
                "characters": {"guid", "account", "name", "slot", "race", "class", "gender", "level", "xp", "money", "position_x", "position_y", "position_z", "map", "orientation", "taximask", "online", "cinematic", "totaltime", "leveltime", "logout_time", "health", "power1", "talentGroupsCount", "activeTalentGroup", "equipmentCache"},
                "item_instance": {"guid", "itemEntry", "owner_guid", "creatorGuid", "giftCreatorGuid", "count", "duration", "charges", "flags", "enchantments", "randomPropertyType", "randomPropertyId", "durability", "creationTime", "text"},
                "character_inventory": {"guid", "bag", "slot", "item"},
                "character_bot_pool": {"guid", "role", "class_spec", "enabled", "in_use", "experiment_tags", "notes"},
                "character_glyphs": {"guid", "talentGroup", "glyph1", "glyph2", "glyph3", "glyph4", "glyph5", "glyph6", "glyph7", "glyph8", "glyph9"},
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
