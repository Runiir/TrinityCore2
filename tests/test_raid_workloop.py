from __future__ import annotations

from typing import Any

import pytest

from tools.raid_program import raid_workloop as workloop
from tools.raid_program.spec_canary_contract import build_canary_pipeline


def _reference_artifacts(*, debug: bool = False) -> dict[str, Any]:
    artifacts = {
        "generation_receipt": "artifacts/generation-receipt.json",
        "raid_sim_request": "artifacts/native-request.json",
        "raid_sim_result": "artifacts/native-result.json",
        "compute_stats": "artifacts/compute-stats.json",
    }
    if debug:
        artifacts["debug_raid_sim_request"] = "artifacts/debug-request.json"
        artifacts["debug_raid_sim_result"] = "artifacts/debug-result.json"
    return artifacts


def test_canary_runner_binds_identity_manifest_pool_tag() -> None:
    pipeline = build_canary_pipeline("affliction_warlock", _reference_artifacts())
    flags = pipeline["capture"]["required_runner_flags"]

    assert "--bot-pool-tag all_spec_candidate_pool" in flags


def test_affliction_canary_runner_requires_named_session_profile() -> None:
    pipeline = build_canary_pipeline("affliction_warlock", _reference_artifacts())
    flags = pipeline["capture"]["required_runner_flags"]

    assert "--session-profile affliction_canary" in flags


def test_rotation_review_command_carries_exact_reference_artifacts() -> None:
    artifacts = _reference_artifacts(debug=True)
    pipeline = build_canary_pipeline("affliction_warlock", artifacts)

    assert pipeline["state"] == "ready_for_capture"
    review = pipeline["rotation_review"]
    assert review["required_simulator_artifacts"] == [
        "generation_receipt",
        "raid_sim_request",
        "raid_sim_result",
        "compute_stats",
    ]
    argv = review["argv"]
    assert argv[argv.index("--wowsims-apl") + 1] == artifacts["raid_sim_request"]
    assert argv[argv.index("--wowsims-result") + 1] == artifacts["raid_sim_result"]
    assert (
        argv[argv.index("--wowsims-compute-stats") + 1]
        == artifacts["compute_stats"]
    )
    assert (
        argv[argv.index("--wowsims-debug-result") + 1]
        == artifacts["debug_raid_sim_result"]
    )
    assert "--wowsims-compute-stats artifacts/compute-stats.json" in review[
        "command"
    ]


def test_embedded_compute_stats_descriptor_is_not_reported_missing() -> None:
    artifacts = _reference_artifacts()
    artifacts["compute_stats"] = {"path": artifacts["compute_stats"]}

    pipeline = build_canary_pipeline("affliction_warlock", artifacts)

    assert pipeline["state"] == "ready_for_capture"
    assert pipeline["rotation_review"]["compute_stats_input"] == (
        "artifacts/compute-stats.json"
    )


def test_missing_compute_stats_blocks_capture_and_routes_reference_repair() -> None:
    artifacts = _reference_artifacts()
    artifacts["compute_stats"] = ""

    pipeline = build_canary_pipeline("affliction_warlock", artifacts)

    assert pipeline["state"] == "blocked_missing_rotation_review_artifacts"
    assert pipeline["missing_required_simulator_artifacts"] == ["compute_stats"]
    assert pipeline["blocked_before_gameplay_tuning"] is True
    assert pipeline["capture"]["admitted"] is False
    assert pipeline["routing"] == {
        "owner_skill": "raid-wowsims-reference",
        "first_broken_edge": "wowsims_compute_stats_reference",
    }


def test_frozen_roster_shape_and_dps_universe_are_explicit() -> None:
    status = workloop.roster_status()

    assert status["ready"] is True
    assert status["slot_count"] == 25
    assert status["role_counts"] == {
        "healer": 6,
        "melee_dps": 5,
        "ranged_dps": 12,
        "tank": 2,
    }
    assert status["supported_mode_count"] == 24
    assert status["required_mode_count"] == 23
    assert status["optional_modes"] == ["feral_druid_tank"]
    assert status["dps_target_count"] == 16


def test_wowsims_gate_never_promotes_stale_candidates() -> None:
    status = workloop.wowsims_status()

    assert status["request_target_count"] == 16
    assert len(status["request_catalog_canonical_sha256"]) == 64
    assert len(status["request_catalog_file_sha256"]) == 64
    assert status["accepted_reference_count"] <= 16
    assert status["reference_class"] in {
        "self_provided_baseline",
        "controlled_live_parity",
        "upstream_full_throughput",
    }
    if status["accepted_reference_count"] != 16:
        assert status["ready"] is False
        assert "current_promoted_references_incomplete" in status["issues"]


def test_promoted_catalog_uses_pending_identity_for_current_receipts() -> None:
    requests = workloop._load_json(workloop.ROOT / workloop.WOWSIMS_REQUESTS_PATH)
    pending = workloop._canonical_sha256(
        workloop.pending_catalog_projection(requests)
    )
    promoted_file_sha256 = workloop._file_sha256(
        workloop.ROOT / workloop.WOWSIMS_REQUESTS_PATH
    )
    assert pending != workloop._canonical_sha256(requests)

    status = workloop.wowsims_status()

    assert status["request_catalog_canonical_sha256"] == pending
    assert status["request_catalog_file_sha256"] == promoted_file_sha256
    if status["workspace_state"] == "locally_verified":
        assert status["current_candidate_count"] == 16
        assert status["accepted_reference_count"] == 16
        assert status["promotion_states"] == {"locally_reconstructed_current": 16}
        assert status["required_hydration_work_unit"] is None
    else:
        assert status["workspace_state"] == "remote_requires_hydration"
        assert status["current_candidate_count"] == 0
        assert status["accepted_reference_count"] == 0
        assert status["promotion_states"] == {
            "current_remote_requires_hydration": 16
        }
        hydration = status["required_hydration_work_unit"]
        assert hydration["owner_skill"] == "raid-wowsims-reference"
        assert hydration["target_count"] == 16
        assert "wowsims_reference_workspace hydrate" in hydration["commands"][
            "hydrate_and_verify"
        ]


def test_dps_work_unit_binds_all_duplicate_roster_slots() -> None:
    unit = workloop.build_spec_work_unit("fire_mage")

    assert unit["work_unit"] == "spec:fire_mage"
    assert unit["role"] == "dps"
    assert unit["roster_slots"] == ["ranged_1", "ranged_2", "ranged_3"]
    assert "wowsims_apl" not in unit["source_paths"]
    assert unit["source_paths"]["wowsims_source_relative_apl"].startswith("ui/")
    reference_work = unit["benchmark"]["required_reference_work_unit"]
    self_reference_work = unit["benchmark"][
        "required_self_provided_reference_work_unit"
    ]
    reference_policy = unit["benchmark"]["reference_class_policy"]
    diagnostic = unit["benchmark"]["diagnostic_policy"]
    assert unit["benchmark"]["state_scope"] == "dps_acceptance_and_promotion_only"
    assert unit["benchmark"]["accepted_dps_reference_class"] == (
        "self_provided_baseline"
    )
    assert unit["benchmark"]["accepted_dps_status_authority"] == (
        "current_work_unit_catalog_projection_overrides_embedded_run_metadata"
    )
    assert reference_policy["selected_acceptance_reference_class"] == (
        "self_provided_baseline"
    )
    self_baseline = reference_policy["classes"]["self_provided_baseline"]
    assert self_baseline["pass_rule"] == (
        "runtime_dps_greater_than_or_equal_to_reference"
    )
    assert self_baseline["state"] in {
        "ready",
        "current_remote_requires_hydration",
    }
    assert self_baseline["catalog_classification"] in {
        "current_accepted",
        "current_remote_requires_hydration",
    }
    assert self_baseline["accepted_dps"] == unit["benchmark"]["accepted_dps"]
    assert self_baseline["upper_rejection_bound"] is None
    assert self_baseline["overtuned_is_failure"] is False
    assert self_baseline["external_raid_buffs"] is False
    assert self_baseline["preapplied_target_debuffs"] is False
    assert self_baseline["consumables"] == {
        "item_ids": "per_spec_exact",
        "inventory_provisioning_required": True,
        "flask": "native_use_before_scoring",
        "food": "native_use_before_scoring",
        "prepot": "one_native_use_before_combat",
        "combat_potion": "one_native_use_during_combat",
        "static_aura_is_use_receipt": False,
    }
    assert diagnostic["state"] == "ready_trace_only"
    assert diagnostic["max_implementation_hypotheses"] == 1
    assert diagnostic["parameter_mismatch"] == (
        "compare_unaffected_signals_and_isolate_sensitive_actions"
    )
    assert "pet_execution" in diagnostic["allowed_signals"]
    assert "simulator_dps_ratio" in diagnostic["forbidden_claims"]
    assert reference_work["owner_skill"] == "raid-wowsims-reference"
    assert reference_work["work_unit"] == (
        "wowsims:self_provided_baseline:cata_raid_dps_reference_cohort_v1"
    )
    assert reference_work["reference_class"] == "self_provided_baseline"
    assert reference_work["atomic_promotion_required"] is True
    assert reference_work["target_count"] == 16
    assert "fire_mage" in reference_work["target_specs"]
    assert reference_work["request_catalog_canonical_sha256"] == (
        workloop.wowsims_status()["request_catalog_canonical_sha256"]
    )
    assert self_reference_work["reference_class"] == "self_provided_baseline"
    assert self_reference_work["state"] in {
        "satisfied",
        "current_remote_requires_hydration",
    }
    assert self_reference_work["atomic_promotion_required"] is True
    assert self_reference_work["duration_seconds"] == 300
    assert self_reference_work["duration_variation_seconds"] == 0
    assert self_reference_work["scope"] == "simulator_reference_generation_only"
    assert self_reference_work[
        "simulator_per_spec_consumable_item_ids_required"
    ] is True
    assert self_reference_work["runtime_receipts_are_not_reference_owner_output"] is True
    runtime_consumables = unit["benchmark"][
        "downstream_runtime_consumable_work_units"
    ]
    assert [row["owner_skill"] for row in runtime_consumables] == [
        "raid-shard-architecture",
        "raid-role-implementation",
    ]
    assert runtime_consumables[1]["depends_on"] == (
        "consumable_inventory_provisioning"
    )
    assert runtime_consumables[1]["static_aura_is_use_receipt"] is False
    if unit["benchmark"]["state"] == "ready":
        assert unit["benchmark"]["accepted_dps"] > 0
        assert unit["benchmark"]["next_action"] == (
            "run_self_provided_consumable_canary"
        )
        pipeline = unit["benchmark"]["canary_pipeline"]
        assert pipeline["state"] == "ready_for_capture"
        assert pipeline["fixed_order"] == [
            "capture",
            "rotation_review",
            "acceptance_decision",
        ]
        assert pipeline["capture"]["owner_skill"] == "raid-shard-architecture"
        assert pipeline["capture"]["validation_clock"] == {
            "policy": "isolated_training_dummy_scoring_window",
            "duration_seconds": 300,
            "duration_variation_seconds": 0,
        }
        flags = pipeline["capture"]["required_runner_flags"]
        assert "--calibration-self-provided-baseline" in flags
        assert "--preserve-worldserver" in flags
        assert "--bot-pool-tag all_spec_candidate_pool" in flags
        assert "--profile-target-spec fire_mage" in pipeline["capture"][
            "identity_manifest_command"
        ]
        assert "--profile-output <canary>/identity/rotation-profile.json" in pipeline[
            "capture"
        ]["identity_manifest_command"]
        assert "--session-runtime-dir <owned-session-runtime-dir>" in pipeline[
            "capture"
        ]["identity_manifest_command"]
        assert pipeline["capture"]["directory_contract"] == {
            "identity_dir": "<canary>/identity",
            "runner_output_dir": "<canary>/run",
            "runner_output_dir_must_be_new_or_empty": True,
            "identity_files_must_not_be_written_to_runner_output_dir": True,
        }
        assert "--output-dir <canary>/run" in flags
        assert pipeline["rotation_review"]["runtime_inputs"] == {
            "trinity_profile": "<canary>/identity/rotation-profile.json",
            "runtime_report": "<canary>/run/report.json",
        }
        assert pipeline["rotation_review"]["owner_skill"] == (
            "raid-rotation-review"
        )
        artifacts = pipeline["rotation_review"]["simulator_artifacts"]
        for name in (
            "generation_receipt",
            "raid_sim_request",
            "raid_sim_result",
            "compute_stats",
        ):
            assert artifacts[name]
        assert pipeline["acceptance_decision"]["max_capture_attempts"] == 1
        assert pipeline["acceptance_decision"]["max_fix_attempts"] == 1
    elif unit["benchmark"]["state"] == "hydrate_exact_reference":
        assert unit["benchmark"]["accepted_dps"] is None
        assert unit["benchmark"]["next_action"] == (
            "hydrate_current_reference_cohort"
        )
        assert unit["benchmark"]["required_hydration_work_unit"][
            "target_count"
        ] == 16
    else:
        assert unit["benchmark"]["state"] == "blocked_exact_reference"
        assert unit["benchmark"]["accepted_dps"] is None
        assert unit["benchmark"]["next_action"] == (
            "run_trace_only_diagnostic_and_handoff_exact_reference"
        )


def test_boss_work_units_distinguish_existing_and_missing_scripts() -> None:
    magmaw = workloop.build_boss_work_unit(
        "blackwing_descent", "magmaw", "10N"
    )
    magmaw_25h = workloop.build_boss_work_unit(
        "blackwing_descent", "magmaw", "25H"
    )
    sinestra = workloop.build_boss_work_unit(
        "bastion_of_twilight", "sinestra", "25H"
    )

    assert magmaw["task_kind"] == "audit_and_validate_existing_boss_script"
    assert magmaw["source_present"] is True
    assert magmaw["validation_clock"]["policy"] == "completion_watchdog"
    assert magmaw["validation_clock"]["fixed_success_timer_seconds"] is None
    active = magmaw["active_program_work_unit"]
    assert active["work_unit"] == (
        "boss:blackwing_descent:magmaw:10N:"
        "drudge_safe_member_role_concurrency_live_verification"
    )
    assert magmaw_25h["active_program_work_unit"] is None
    assert active["owner_skill"] == "raid-shard-architecture"
    assert active["first_broken_edge"] == (
        "landed_drudge_recovery_keeps_safe_members_in_route_handled_offense_"
        "hold_until_the_next_20s_rush_reopens_the_queue_so_no_trained_single_"
        "target_action_executes_and_healers_attrition_die"
    )
    evidence = active["decisive_evidence"]
    assert evidence["source_commit"] == (
        "c7c6bb9f7f0c51265f1ae20ab96ef01a59af467a"
    )
    assert evidence["binary_sha256"] == (
        "5208fd31a5179bec965f3ff64393bb17beade82cd0dc50b6a99ca7904475f990"
    )
    assert evidence["report_sha256"] == (
        "180d60ed29a7cd87a7e199aafd0b9d45fbf45e4c667d8a790ecd0f19e2648a7c"
    )
    assert evidence["report_file_sha256"] == (
        "90a5837ba49be4f6a9032ac48acdc7d8772c93ab231320102653fb9d35f16b41"
    )
    assert (
        evidence["route_generation"],
        evidence["route_node_index"],
        evidence["route_node_id"],
    ) == (3, 2, "bwd.magmaw.drudges")
    assert evidence["diagnostic_difficulty"] == "10N"
    assert evidence["kills"] == 1
    assert evidence["death_loop_count"] == 3
    assert evidence["dead_roster_guids"] == [30003, 30004, 30005]
    assert evidence["landed_charge_count"] == 20
    assert evidence["last_complete_reseparation_sequence"] == 14
    assert evidence["first_missing_reseparation_sequence"] == 15
    assert evidence["trained_single_target_action_count"] == 0
    assert evidence["maximum_observed_recovery_repeat_count"] == 1323
    assert evidence["prior_displaced_origin_repair_verified"] is True
    assert evidence["boss_reached"] is False
    assert evidence["forbidden_assistance_observed"] is False
    assert evidence["cleanup_passed"] is True
    assert evidence["worldserver_exit_code"] == 0
    assert evidence["evidence_demux_gate_passed"] is True
    assert active["implementation_budget"] == {
        "hypotheses": 1,
        "matched_live_verification_runs": 0,
    }
    assert active["repair_scope"]["status"] == (
        "implemented_pending_live_verification"
    )
    assert "one_completion_watchdog_canary" in (
        active["repair_scope"]["allowed"]
    )
    assert active["implemented_repair"]["commit"] == (
        "53c1d427d27a4b58d9f0c0425f9cba210edac71f"
    )
    assert active["implemented_repair"]["source_line_limit_passed"] is True
    assert active["validation_clock"]["fixed_success_timer_seconds"] is None
    assert active["live_verification_owner_skill"] == "raid-shard-architecture"
    assert "do not teleport" in active["next_action"].lower()
    assert sinestra["task_kind"] == "implement_missing_boss_script"
    assert sinestra["source_present"] is False
    assert sinestra["diagnostic_shard_allowed_after_static_gates"] is False


def test_magmaw_handoff_retains_cedeb_and_902_runs() -> None:
    handoff = (
        workloop.ROOT
        / "experiments/configs/cata_raid_magmaw_convergence_handoff.md"
    ).read_text(encoding="utf-8")

    assert "All fourteen retained runs" in handoff
    assert "| `cedeb5c933` | gameplay failure |" in handoff
    assert "`native_repath_lease_expiry_predicate` are consumed" in handoff
    assert "`cedeb5c933eacbae180b239d5058417b8b30c225`" in handoff
    assert (
        "b8ca0dc6df346fac11452560c56c2e67322a1704a2763af8bb1be4c3689eb8a0"
        in handoff
    )
    assert (
        "artifacts/cata_raid_program/phase1_foundation_cedeb5c933_magmaw_run01_20260822.dvc"
        in handoff
    )
    assert (
        "003421776435fd8b77101ea3860b5a4886d6648df0c0b4d6610d989c0c125383"
        in handoff
    )
    assert (
        "6c7ca3cabfac8a037c746b26d955ec61fab979714e59d49eb4c828aada665f88"
        in handoff
    )
    assert "902710a4ef" in handoff
    assert "Exact 10N diagnostic" in handoff
    assert "67 unique" in handoff
    assert "eight deaths and two alive" in handoff
    assert "gameplay_failure_with_evidence_demux_classification_defect" in handoff
    assert "evidence_demux_required_action_missing:botauto_readycheck" in handoff
    assert "f23b29f0f5a08f21e5044c16275ff235ed4d96a9" in handoff
    assert "fac4cbf944036b2d86b28aef00c08b73035963f8" in handoff
    assert "d190177ccba42dd44cce825994dc60be361d4dd1" in handoff
    assert "contains the required" in handoff
    assert "do not treat" in handoff
    assert "exact 10N completion-watchdog verification" in handoff
    assert "not a new implementation" in handoff
    assert "not a 25H" in handoff


def test_hagara_catalog_alias_joins_script_readiness() -> None:
    unit = workloop.build_boss_work_unit(
        "dragon_soul", "hagara", "25H"
    )

    assert unit["script_status"] == "missing_dedicated_implementation"


def test_outside_roster_spec_fails_closed() -> None:
    with pytest.raises(
        workloop.WorkloopError, match="spec_outside_frozen_roster"
    ):
        workloop.build_spec_work_unit("arcane_mage")


def test_role_harnesses_do_not_inherit_the_dps_300_second_clock() -> None:
    tank = workloop.build_spec_work_unit("blood_death_knight")
    healer = workloop.build_spec_work_unit("restoration_druid")

    assert tank["benchmark"]["next_action"] == "run_tank_threat_role_harness"
    assert healer["benchmark"]["next_action"] == (
        "run_healer_controlled_damage_role_harness"
    )
    for unit in (tank, healer):
        assert unit["benchmark"]["validation_clock"] == {
            "policy": "role_harness_contract",
            "fixed_success_timer_seconds": None,
        }


def test_affliction_canary_exposes_pet_debug_reference_artifacts() -> None:
    unit = workloop.build_spec_work_unit("affliction_warlock")

    if unit["benchmark"]["state"] != "ready":
        pytest.skip("exact promoted WoWSims workspace is not hydrated")
    artifacts = unit["benchmark"]["canary_pipeline"]["rotation_review"][
        "simulator_artifacts"
    ]
    assert artifacts["debug_raid_sim_request"]
    assert artifacts["debug_raid_sim_result"]


def test_status_uses_hash_bound_active_work_unit_not_legacy_prose() -> None:
    status = workloop.build_status()

    assert status["active_work_unit"]["descriptor_valid"] is True
    assert status["active_work_unit"]["ready_for_bounded_repair"] is False
    assert status["active_work_unit"]["ready_for_live_verification"] is True
    assert status["active_work_unit"]["first_broken_edge"] == (
        "landed_drudge_recovery_keeps_safe_members_in_route_handled_offense_"
        "hold_until_the_next_20s_rush_reopens_the_queue_so_no_trained_single_"
        "target_action_executes_and_healers_attrition_die"
    )
    assert status["active_work_unit"]["source_handoff"]["sha256"] == (
        workloop._file_sha256(
            workloop.ROOT
            / "experiments/configs/"
            "cata_raid_magmaw_canary29_safe_member_offense_handoff_20260826.md"
        )
    )
    assert status["required_next_work_unit"]["work_unit"] == (
        "boss:blackwing_descent:magmaw:10N:"
        "drudge_safe_member_role_concurrency_live_verification"
    )
    assert status["required_next_work_unit"]["owner_skill"] == (
        "raid-shard-architecture"
    )
    assert status["current_program_next_action"] == status["active_work_unit"][
        "next_action"
    ]
    assert "do not teleport" in status["active_work_unit"]["next_action"].lower()
    assert "legacy_program_next_action" not in status


def test_script_readiness_uses_source_tree_identity() -> None:
    status = workloop.encounter_status()

    assert len(status["script_readiness_source_tree_sha256"]) == 64
    assert status["script_readiness_source_tree_sha256"] == (
        status["script_readiness_recorded_source_tree_sha256"]
    )
    assert status["script_readiness_audit_current"] is True
