from __future__ import annotations

from copy import deepcopy

from tools.bot_ml.spec_canary_gate import evaluate_canary


def _policy() -> dict:
    return {
        "schema": "trinity_spec_canary_acceptance_v1",
        "max_capture_attempts": 1,
        "max_fix_attempts": 1,
        "required_duration_seconds": 300,
        "thresholds": {
            "cast_cadence_ratio": {"minimum": 0.85, "maximum": 1.15},
            "cast_mix_total_variation_distance_maximum": 0.08,
            "cast_share_absolute_delta_maximum": 0.05,
            "total_dps_ratio": {"minimum": 0.9, "maximum": 1.1},
            "pet_alive_ratio_minimum": 0.95,
            "pet_target_match_ratio_minimum": 0.95,
            "pet_landed_event_cadence_ratio": {"minimum": 0.85, "maximum": 1.15},
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
            "player_dps": {"avg": 1_000},
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


def test_matching_pet_cadence_with_low_damage_routes_native_mechanics() -> None:
    review = _review()
    review["runtime"]["calibration_windows"][0]["dps"] = 700
    review["runtime"]["primary_pet_damage_by_spell"] = {"0": 10_000, "54049": 20_000}
    decision = _evaluate(review)
    assert decision["signals"]["primary_pet"]["landed_event_cadence_ratio"] == 1.0
    assert decision["signals"]["primary_pet"]["damage_per_event_ratio"] == 0.5
    assert decision["first_broken_edge"] == "native_pet_damage_model"
    assert decision["owner_skill"] == "raid-class-mechanics-implementation"


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
