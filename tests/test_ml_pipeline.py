from __future__ import annotations

import json
from pathlib import Path

from ml.evaluation.evaluate_action_frequency import main as evaluate_main
from ml.group_roles.coordination import ReservationStore
from ml.group_roles.metrics import group_role_metrics
from ml.group_roles.policies import policy_for_role
from ml.raid.metrics import raid_metrics
from ml.raid.scheduler import RaidAssignmentScheduler
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
