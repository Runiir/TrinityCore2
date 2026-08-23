from __future__ import annotations

from copy import deepcopy

import pytest

from tools.bot_ml.spec_canary_gate import evaluate_canary


def _policy() -> dict:
    return {
        "schema": "trinity_spec_canary_acceptance_v1",
        "max_capture_attempts": 1,
        "max_fix_attempts": 1,
        "required_duration_seconds": 300,
        "default_reference_class": "self_provided_baseline",
        "reference_classes": {
            "self_provided_baseline": {
                "requires_consumable_parity": True,
                "total_dps_ratio": {"minimum": 1.0},
                "single_sample_dps_ratio": {"minimum": 0.98, "maximum": 1.02},
                "overtuned_is_failure": False,
            },
            "controlled_live_parity": {
                "requires_consumable_parity": True,
                "total_dps_ratio": {"minimum": 0.9, "maximum": 1.1},
            },
        },
        "thresholds": {
            "cast_cadence_ratio": {"minimum": 0.85, "maximum": 1.15},
            "cast_mix_total_variation_distance_maximum": 0.08,
            "cast_share_absolute_delta_maximum": 0.05,
            "total_dps_ratio": {"minimum": 0.9, "maximum": 1.1},
            "pet_alive_ratio_minimum": 0.95,
            "pet_target_match_ratio_minimum": 0.95,
            "pet_landed_event_cadence_ratio": {"minimum": 0.85},
            "pet_damage_per_event_ratio": {"minimum": 0.9, "maximum": 1.1},
        },
        "specs": {
            "affliction_warlock": {
                "pet_required": True,
                "wowsims_primary_pet_names": ["Felhunter"],
                "trinity_primary_pet_spell_ids": [0, 54049],
            }
        },
    }


def _review() -> dict:
    return {
        "gear_parity": {"status": "match"},
        "effective_stat_parity": {"status": "match"},
        "dps_tuning_gate": {"tuning_admitted": True},
        "reference_class": "self_provided_baseline",
        "consumable_parity": {
            "status": "match",
            "inventory_backed": True,
            "flask_native_use_before_scoring": 1,
            "food_native_use_before_scoring": 1,
            "prepot_native_use_before_combat": 1,
            "combat_potion_native_use_during_combat": 1,
        },
        "execution_comparison": {
            "cast_mix": {
                "cast_mix_overlap": 0.96,
                "maximum_absolute_share_delta": 0.03,
                "cast_cadence": {"trinity_to_wowsims_cadence_ratio": 1.0},
            }
        },
        "runtime": {
            "calibration_complete": True,
            "calibration_windows": [
                {"elapsed_seconds": 300, "damage": 300_000, "pet_damage": 60_000, "dps": 1_000}
            ],
            "primary_pet_damage_by_spell": {"0": 20_000, "54049": 40_000},
            "primary_pet_damage_event_counts_by_spell": {"0": 20, "54049": 40},
            "pet_execution_observations": [
                {"alive_ratio": 1.0, "target_match_ratio": 1.0}
            ],
        },
        "wowsims_result": {
            "avg_iteration_duration_seconds": 300,
            "iterations_done": 2_000,
            "player_dps": {
                "avg": 1_000,
                "stdev": 25,
                "min": 900,
                "max": 1_100,
                "aggregatorData": {"n": 2_000},
            },
            "action_metrics": [
                {
                    "source": {"kind": "player", "name": "Affliction"},
                    "per_iteration_target_metric_sums": {
                        "damage": 240_000, "casts": 100, "hits": 100,
                        "crits": 0, "ticks": 0, "crit_ticks": 0,
                    },
                },
                {
                    "source": {"kind": "pet", "name": "Felhunter"},
                    "per_iteration_target_metric_sums": {
                        "damage": 60_000, "casts": 60, "hits": 60,
                        "crits": 0, "ticks": 0, "crit_ticks": 0,
                    },
                },
            ],
        },
        "wowsims_debug_result": {
            "avg_iteration_duration_seconds": 300,
            "first_iteration_duration_seconds": 300,
            "iterations_done": 1,
            "debug_log_present": True,
            "player_dps": {
                "avg": 1_000,
                "aggregatorData": {"n": 1},
            },
        },
    }


def _evaluate(review: dict, *, fixes_used: int = 0, capture_attempts_used: int = 0) -> dict:
    return evaluate_canary(
        review, _policy(), spec="affliction_warlock",
        review_sha256="a" * 64, policy_sha256="b" * 64,
        fixes_used=fixes_used, capture_attempts_used=capture_attempts_used,
    )


def test_passes_a_complete_matched_baseline() -> None:
    decision = _evaluate(_review())
    assert decision["status"] == "passed"
    assert decision["terminal_reason"] == "baseline_within_policy"
    assert decision["next_work_unit"] is None


def test_self_provided_baseline_has_no_upper_dps_rejection() -> None:
    review = _review()
    review["runtime"]["calibration_windows"][0]["dps"] = 1_350
    decision = _evaluate(review)
    assert decision["status"] == "passed"
    assert decision["reference_class"] == "self_provided_baseline"
    assert decision["signals"]["total_dps_ratio"] == 1.35


@pytest.mark.parametrize("runtime_dps", [29_465.74, 29_650.52666666667])
def test_current_affliction_canaries_use_the_pinned_debug_sample(
    runtime_dps: float,
) -> None:
    review = _review()
    review["runtime"]["calibration_windows"][0]["dps"] = runtime_dps
    review["wowsims_result"]["player_dps"] = {
        "avg": 31_312.966894306235,
        "stdev": 788.1759348903284,
        "min": 29_143.19682362893,
        "max": 33_998.228820330674,
        "aggregatorData": {"n": 2_000},
    }
    review["wowsims_debug_result"]["player_dps"] = {
        "avg": 29_623.938524220404,
        "aggregatorData": {"n": 1},
    }

    decision = _evaluate(review)

    assert decision["status"] == "passed"
    assert decision["first_broken_edge"] is None
    assert decision["signals"]["wowsims_aggregate_dps"] == {
        "mean": 31_312.966894306235,
        "stdev": 788.1759348903284,
        "minimum": 29_143.19682362893,
        "maximum": 33_998.228820330674,
        "iterations": 2_000,
    }
    comparison = decision["signals"]["dps_comparison"]
    assert comparison["denominator"] == "wowsims_debug_result.player_dps.avg"
    assert comparison["debug_value"] == 29_623.938524220404
    assert comparison["parity_band"] == {"minimum": 0.98, "maximum": 1.02}
    assert comparison["upper_bound_enforced"] is False


def test_real_affliction_canary_accepts_favorable_pet_damage_per_event() -> None:
    """The 762e5444d4 canary is above the pet DPE diagnostic ceiling."""
    review = _review()
    review["runtime"]["calibration_windows"][0].update(
        {"dps": 29_032.05, "pet_damage": 1_806_482}
    )
    review["runtime"]["primary_pet_damage_by_spell"] = {
        "0": 1_806_482,
    }
    review["runtime"]["primary_pet_damage_event_counts_by_spell"] = {
        "0": 224,
    }
    review["runtime"]["pet_execution_observations"] = [
        {"alive_ratio": 1.0, "target_match_ratio": 0.999}
    ]
    review["execution_comparison"]["cast_mix"] = {
        "cast_mix_overlap": 0.961653542412,
        "maximum_absolute_share_delta": 0.021531339354,
        "cast_cadence": {"trinity_to_wowsims_cadence_ratio": 0.936095856215},
    }
    review["wowsims_result"]["player_dps"] = {
        "avg": 31_312.966894306235,
        "stdev": 788.1759348903284,
        "min": 29_143.19682362893,
        "max": 33_998.228820330674,
        "aggregatorData": {"n": 2_000},
    }
    review["wowsims_result"]["action_metrics"][1][
        "per_iteration_target_metric_sums"
    ] = {
        "damage": 1_724_145.1296967766,
        "casts": 237,
        "hits": 237,
        "crits": 0,
        "ticks": 0,
        "crit_ticks": 0,
    }
    review["wowsims_debug_result"]["player_dps"] = {
        "avg": 29_623.938524220404,
        "aggregatorData": {"n": 1},
    }

    decision = _evaluate(review, fixes_used=1)

    assert decision["status"] == "passed"
    assert decision["terminal_reason"] == "verified_after_single_fix"
    assert decision["first_broken_edge"] is None
    pet_signal = decision["signals"]["primary_pet"]
    assert pet_signal["damage_per_event_ratio"] == pytest.approx(1.108562405967778)
    assert pet_signal["total_damage_ratio"] == pytest.approx(1.047755185387267)
    pet_gate = next(
        gate for gate in decision["gates"]
        if gate["name"] == "pet_damage_per_event_ratio"
    )
    assert pet_gate["status"] == "pass"
    assert pet_gate["expected"] == {
        "minimum": 0.9,
        "maximum": 1.1,
        "upper_bound_enforced": False,
    }


def test_single_sample_more_than_two_percent_low_fails_throughput_gate() -> None:
    review = _review()
    review["runtime"]["calibration_windows"][0]["dps"] = 979
    decision = _evaluate(review)

    assert decision["status"] == "failed"
    assert decision["first_broken_edge"] == "native_owner_damage_model"
    assert decision["signals"]["total_dps_ratio"] == pytest.approx(0.979)
    total_gate = next(gate for gate in decision["gates"] if gate["name"] == "total_dps_ratio")
    assert total_gate["status"] == "fail"
    assert total_gate["expected"]["denominator"] == "wowsims_debug_result.player_dps.avg"


def test_missing_debug_dps_reference_is_insufficient_data() -> None:
    review = _review()
    review.pop("wowsims_debug_result")

    decision = _evaluate(review)

    assert decision["status"] == "insufficient_data"
    assert decision["first_broken_edge"] == "wowsims_debug_dps_reference"
    assert decision["owner_skill"] == "raid-rotation-review"
    assert decision["signals"]["wowsims_debug_dps"] is None
    total_gate = next(gate for gate in decision["gates"] if gate["name"] == "total_dps_ratio")
    assert total_gate["status"] == "insufficient_data"


def test_multi_iteration_debug_dps_reference_is_insufficient_data() -> None:
    review = _review()
    review["wowsims_debug_result"]["iterations_done"] = 2
    review["wowsims_debug_result"]["player_dps"]["aggregatorData"]["n"] = 2

    decision = _evaluate(review)

    assert decision["status"] == "insufficient_data"
    assert decision["first_broken_edge"] == "wowsims_debug_dps_reference"
    assert decision["signals"]["dps_comparison"]["debug_reference_valid"] is False


def test_missing_native_prepot_routes_to_role_owner() -> None:
    review = _review()
    review["consumable_parity"] = {
        "status": "mismatch",
        "first_broken_edge": "prepot_native_execution",
        "prepot_native_use_before_combat": 0,
    }
    decision = _evaluate(review)
    assert decision["status"] == "failed"
    assert decision["first_broken_edge"] == "prepot_native_execution"
    assert decision["owner_skill"] == "raid-role-implementation"


def test_missing_consumable_inventory_routes_to_provisioning_owner() -> None:
    review = _review()
    review["consumable_parity"] = {
        "status": "mismatch",
        "first_broken_edge": "consumable_inventory_missing",
    }
    decision = _evaluate(review)
    assert decision["first_broken_edge"] == "consumable_inventory_missing"
    assert decision["owner_skill"] == "raid-shard-architecture"


def test_routes_missing_scoring_start_stats_to_one_capture() -> None:
    review = _review()
    review["effective_stat_parity"] = {
        "status": "insufficient_data",
        "reason": "missing_trinity_scoring_start_stats",
    }
    review["dps_tuning_gate"] = {"tuning_admitted": False}
    decision = _evaluate(review)
    assert decision["status"] == "insufficient_data"
    assert decision["first_broken_edge"] == "trinity_scoring_start_stat_observation"
    assert decision["next_work_unit"]["specialist_skill"] == "raid-shard-architecture"
    assert decision["next_work_unit"]["mode"] == "capture_only"


def test_routes_cast_cadence_to_role_policy_owner() -> None:
    review = _review()
    review["execution_comparison"]["cast_mix"]["cast_cadence"][
        "trinity_to_wowsims_cadence_ratio"
    ] = 0.8
    decision = _evaluate(review)
    assert decision["status"] == "failed"
    assert decision["first_broken_edge"] == "priority_action_cadence"
    assert decision["owner_skill"] == "raid-role-implementation"


def test_pre_scoring_pet_setup_blocker_precedes_missing_stats() -> None:
    review = _review()
    review["runtime"]["calibration_complete"] = False
    review["runtime"]["calibration_windows"] = []
    review["runtime"]["pre_scoring_blockers"] = [
        {
            "bot_guid": 1306,
            "reason": "persistent_setup_preexisting_pet_without_native_receipt",
            "attempts": 0,
            "pet_present": True,
            "pet_spellbook_sha256": "a" * 64,
            "pet_admission_spellbook_sha256": "",
        }
    ]
    review["effective_stat_parity"] = {
        "status": "insufficient_data",
        "reason": "missing_trinity_scoring_start_stats",
    }
    review["dps_tuning_gate"] = {"tuning_admitted": False}
    decision = _evaluate(review)
    assert decision["status"] == "failed"
    assert decision["first_broken_edge"] == "persistent_setup_preexisting_pet_without_native_receipt"
    assert decision["owner_skill"] == "raid-role-implementation"
    assert decision["next_work_unit"]["mode"] == "single_fix"


def test_partial_successful_movement_routes_to_capture_before_stat_or_dps_tuning() -> None:
    review = _review()
    review["runtime"]["calibration_complete"] = False
    review["runtime"]["calibration_windows"] = [
        {
            "elapsed_seconds": 10.973,
            "damage": 128591,
            "pet_damage": 45685,
            "dps": 11718.86,
        }
    ]
    review["runtime"]["pre_scoring_blockers"] = []
    review["effective_stat_parity"] = {
        "status": "mismatch",
        "first_broken_edge": "owner_effective_stat_application_before_rotation_execution",
    }
    decision = _evaluate(review)

    assert decision["status"] == "insufficient_data"
    assert decision["first_broken_edge"] == "calibration_pre_scoring_liveness"
    assert decision["owner_skill"] == "raid-shard-architecture"
    assert decision["next_work_unit"]["mode"] == "capture_only"
    assert decision["next_work_unit"]["expected_metric"] == (
        "one completed deterministic calibration window"
    )
    liveness_gate = next(
        gate for gate in decision["gates"]
        if gate["name"] == "calibration_pre_scoring_liveness"
    )
    assert liveness_gate["status"] == "insufficient_data"


def test_runtime_pet_resource_terminal_precedes_missing_scoring_stats() -> None:
    review = _review()
    review["runtime"]["calibration_complete"] = True
    review["runtime"]["calibration_windows"] = []
    review["runtime"]["calibration_terminal"] = {
        "reason": "calibration_initial_resource_contract_mismatch",
        "initial_resource_failures": [
            {
                "bot_guid": 1306,
                "power_mismatches": [
                    {
                        "unit_kind": "pet",
                        "matches_contract": False,
                        "observed_native_value": 23422,
                        "observed_maximum_native_value": 127669,
                    }
                ],
            }
        ],
    }
    review["effective_stat_parity"] = {
        "status": "insufficient_data",
        "reason": "missing_trinity_scoring_start_stats",
    }
    review["dps_tuning_gate"] = {"tuning_admitted": False}

    decision = _evaluate(review)

    assert decision["status"] == "failed"
    assert decision["first_broken_edge"] == (
        "calibration_initial_resource_contract_mismatch"
    )
    assert decision["owner_skill"] == "raid-role-implementation"
    assert decision["next_work_unit"]["mode"] == "single_fix"


def test_matching_pet_cadence_with_low_damage_routes_native_mechanics() -> None:
    review = _review()
    review["runtime"]["calibration_windows"][0]["dps"] = 700
    review["runtime"]["primary_pet_damage_by_spell"] = {"0": 10_000, "54049": 20_000}
    decision = _evaluate(review)
    assert decision["signals"]["primary_pet"]["landed_event_cadence_ratio"] == 1.0
    assert decision["signals"]["primary_pet"]["damage_per_event_ratio"] == 0.5
    assert decision["first_broken_edge"] == "native_pet_damage_model"
    assert decision["owner_skill"] == "raid-class-mechanics-implementation"
    pet_gate = next(
        gate for gate in decision["gates"]
        if gate["name"] == "pet_damage_per_event_ratio"
    )
    assert pet_gate["status"] == "fail"


def test_overtuned_pet_does_not_hide_attributable_owner_damage_deficit() -> None:
    review = _review()
    review["runtime"]["calibration_windows"][0]["dps"] = 900
    review["runtime"]["primary_pet_damage_by_spell"] = {
        "0": 24_000,
        "54049": 48_000,
    }

    decision = _evaluate(review)

    assert decision["signals"]["primary_pet"]["damage_per_event_ratio"] == 1.2
    assert decision["signals"]["primary_pet"]["total_damage_ratio"] == 1.2
    assert decision["signals"]["total_dps_ratio"] == 0.9
    assert decision["first_broken_edge"] == "native_owner_damage_model"
    assert decision["owner_skill"] == "raid-class-mechanics-implementation"


def test_pet_landed_events_include_glancing_melee_outcomes() -> None:
    review = _review()
    pet_metrics = review["wowsims_result"]["action_metrics"][1][
        "per_iteration_target_metric_sums"
    ]
    pet_metrics["glances"] = 40
    review["runtime"]["primary_pet_damage_by_spell"] = {
        "0": 36_000,
        "54049": 24_000,
    }
    review["runtime"]["primary_pet_damage_event_counts_by_spell"] = {
        "0": 60,
        "54049": 40,
    }

    decision = _evaluate(review)

    assert decision["status"] == "passed"
    assert decision["signals"]["primary_pet"]["wowsims_landed_events"] == 100.0
    assert decision["signals"]["primary_pet"]["runtime_landed_events"] == 100.0
    assert decision["signals"]["primary_pet"]["landed_event_cadence_ratio"] == 1.0


def test_favorable_above_pet_cadence_passes_minimum_only_gate() -> None:
    review = _review()
    review["runtime"]["primary_pet_damage_by_spell"] = {
        "0": 33_333.3333333333,
        "54049": 66_666.6666666667,
    }
    review["runtime"]["primary_pet_damage_event_counts_by_spell"] = {
        "0": 60,
        "54049": 40,
    }

    decision = _evaluate(review)

    assert decision["status"] == "passed"
    assert decision["signals"]["primary_pet"]["landed_event_cadence_ratio"] == 100 / 60


def test_low_pet_cadence_remains_fail_closed() -> None:
    review = _review()
    review["runtime"]["primary_pet_damage_by_spell"] = {
        "0": 16_666.6666666667,
        "54049": 33_333.3333333333,
    }
    review["runtime"]["primary_pet_damage_event_counts_by_spell"] = {
        "0": 30,
        "54049": 20,
    }

    decision = _evaluate(review)

    assert decision["status"] == "failed"
    assert decision["first_broken_edge"] == "primary_pet_policy_execution"
    assert decision["owner_skill"] == "raid-role-implementation"
    assert decision["signals"]["primary_pet"]["landed_event_cadence_ratio"] == 50 / 60


def test_missing_pet_attribution_is_not_misclassified_as_tuning() -> None:
    review = _review()
    review["runtime"]["primary_pet_damage_by_spell"] = {}
    review["runtime"]["primary_pet_damage_event_counts_by_spell"] = {}
    review["runtime"]["pet_execution_observations"] = []
    decision = _evaluate(review)
    assert decision["status"] == "insufficient_data"
    assert decision["first_broken_edge"] == "primary_pet_runtime_attribution"
    assert decision["owner_skill"] == "raid-shard-architecture"


def test_failed_verification_stops_after_one_fix() -> None:
    review = deepcopy(_review())
    review["execution_comparison"]["cast_mix"]["cast_cadence"][
        "trinity_to_wowsims_cadence_ratio"
    ] = 0.8
    decision = _evaluate(review, fixes_used=1)
    assert decision["status"] == "failed"
    assert decision["terminal_reason"] == "fix_budget_exhausted"
    assert decision["next_work_unit"] is None
