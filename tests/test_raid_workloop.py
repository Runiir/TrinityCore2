from __future__ import annotations

import pytest

from tools.raid_program import raid_workloop as workloop


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
    assert status["current_candidate_count"] == 16
    assert status["accepted_reference_count"] == 16
    assert status["promotion_states"] == {"locally_reconstructed_current": 16}


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
    assert self_baseline["state"] == "ready"
    assert self_baseline["catalog_classification"] == "current_accepted"
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
    assert self_reference_work["state"] == "satisfied"
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
    else:
        assert unit["benchmark"]["state"] == "blocked_exact_reference"
        assert unit["benchmark"]["accepted_dps"] is None
        assert unit["benchmark"]["next_action"] == (
            "run_trace_only_diagnostic_and_handoff_exact_reference"
        )


def test_boss_work_units_distinguish_existing_and_missing_scripts() -> None:
    magmaw = workloop.build_boss_work_unit(
        "blackwing_descent", "magmaw", "25H"
    )
    sinestra = workloop.build_boss_work_unit(
        "bastion_of_twilight", "sinestra", "25H"
    )

    assert magmaw["task_kind"] == "audit_and_validate_existing_boss_script"
    assert magmaw["source_present"] is True
    assert sinestra["task_kind"] == "implement_missing_boss_script"
    assert sinestra["source_present"] is False
    assert sinestra["diagnostic_shard_allowed_after_static_gates"] is False


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
