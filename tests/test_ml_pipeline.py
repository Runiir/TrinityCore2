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
