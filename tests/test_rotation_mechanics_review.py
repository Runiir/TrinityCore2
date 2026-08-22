from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.bot_ml.review_rotation_mechanics import (
    build_review,
    compare_cast_mix,
    find_wowsims_apl,
    load_route_document,
    normalize_wowsims_apl,
    normalize_wowsims_result,
    normalize_runtime_report,
    trinity_profile_document_from_database_rows,
)


ROOT = Path(__file__).resolve().parents[1]


def _apl() -> dict:
    return {
        "type": "TypeAPL",
        "prepullActions": [
            {
                "action": {"castSpell": {"spellId": {"spellId": 48265}}},
                "doAtValue": {"const": {"val": "-20s"}},
            }
        ],
        "priorityList": [
            {
                "action": {
                    "condition": {
                        "cmp": {
                            "op": "OpGe",
                            "lhs": {"currentRunicPower": {}},
                            "rhs": {"const": {"val": "90"}},
                        }
                    },
                    "castSpell": {"spellId": {"spellId": 49143}},
                }
            },
            {
                "action": {
                    "condition": {
                        "and": {
                            "vals": [
                                {"auraIsActive": {"auraId": {"spellId": 51124}}},
                                {"allTrinketStatProcsActive": {"statType2": 6}},
                            ]
                        }
                    },
                    "strictSequence": {
                        "actions": [
                            {"castSpell": {"spellId": {"spellId": 49020}}},
                            {"castSpell": {"spellId": {"spellId": 49184}}},
                        ]
                    },
                }
            },
            {"action": {"wait": {"duration": {"const": {"val": "1s"}}}}},
        ],
    }


def _profile() -> dict:
    return {
        "ok": True,
        "snapshot_generation": 7,
        "snapshot_content_hash": "a" * 64,
        "profile": {"class_id": 6, "spec_tag": "frost_death_knight", "role": "dps"},
        "actions": [
            {
                "sort_order": 20,
                "spell_id": 49020,
                "category": "spender",
                "priority_bucket": 1,
                "weights": {"damage": 1.04, "movement": 0.0},
                "gates": {
                    "required_self_aura": 51124,
                    "min_ready_runes": 2,
                    "max_primary_power_pct": 0.7,
                },
            },
            {
                "sort_order": 10,
                "spell_id": 49143,
                "category": "spender",
                "priority_bucket": 2,
                "gates": {"min_primary_power_pct": 0.7},
            },
            {
                "sort_order": 30,
                "spell_id": 45462,
                "category": "debuff",
                "priority_bucket": 3,
                "gates": {"required_owned_target_aura": 55078},
            },
        ],
    }


def _compute_stats() -> dict:
    unit_stats = {
        "apiVersion": 5,
        "stats": [
            100, 200, 300, 8_000, 400, 1_700, 1_000, 3_000,
            0, 0, 0, 1_100, 500, 0, 12_500, 0, 0, 0, 0, 0, 0,
            0, 10_000, 0, 150_000, 140_000, 1_000,
        ],
        "pseudoStats": [
            0, 0, 0, 0, 0, 5, 1.1, 1.1, 1.05, 30, 30, 30,
            14, 17, 20, 25,
        ],
    }
    player = {
        key: json.loads(json.dumps(unit_stats))
        for key in (
            "baseStats",
            "gearStats",
            "talentsStats",
            "buffsStats",
            "consumesStats",
            "finalStats",
        )
    }
    return {"raidStats": {"parties": [{"players": [player]}]}}


def _gear_fixture() -> tuple[dict, list[dict]]:
    slot_map = [0, 1, 2, 14, 4, 8, 9, 5, 6, 7, 10, 11, 12, 13, 15, 16, 17]
    wowsims_items = [
        {} if index == 15 else {"id": 10_000 + index}
        for index in range(len(slot_map))
    ]
    runtime_items = [
        {
            "slot": slot_map[index],
            "item_id": item["id"],
            "enchant_id": 0,
            "reforge_id": 0,
            "gem_item_ids": [],
        }
        for index, item in enumerate(wowsims_items)
        if item
    ]
    request = {
        "raid": {
            "parties": [
                {
                    "players": [
                        {"equipment": {"items": wowsims_items}, "rotation": _apl()}
                    ]
                }
            ]
        }
    }
    return request, runtime_items


def _effective_stats_runtime(
    *, intellect: float = 8_000, drift_first_item: bool = False
) -> dict:
    _, gear_items = _gear_fixture()
    if drift_first_item:
        gear_items[0]["item_id"] += 1
    return {
        "combat_calibration": {
            "phase": "complete",
            "target_guid": 1306,
            "previous_window": {
                "bots": [
                    {
                        "guid": 1306,
                        "gear_profile_observation": {"items": gear_items},
                        "scoring_start_stats": {
                            "schema": "trinity_scoring_start_effective_stats_v1",
                            "player": {
                                "observed": True,
                                "intellect": intellect,
                                "hit_rating": 1_700,
                                "crit_rating": 1_000,
                                "haste_rating": 3_000,
                                "mastery_rating": 1_100,
                                "spell_power": 12_500,
                                "spell_hit_pct": 17,
                                "spell_crit_pct": 25,
                                "spell_speed_multiplier": 1.365,
                            },
                            "pet": {
                                "observed": True,
                                "strength": 453,
                                "spell_power": 6_923.55,
                            },
                        },
                    }
                ]
            },
        }
    }


def test_normalize_runtime_preserves_pre_scoring_pet_setup_blocker() -> None:
    normalized = normalize_runtime_report(
        {
            "combat_calibration": {
                "phase": "warmup",
                "bots": [
                    {
                        "guid": 1306,
                        "attempts": 0,
                        "movement_diagnostic": {
                            "last_recovery_result": "persistent_setup_preexisting_pet_without_native_receipt"
                        },
                        "persistent_setup": {
                            "pet_present": True,
                            "pet_spellbook_sha256": "a" * 64,
                            "pet_admission_spellbook_sha256": "",
                        },
                    }
                ],
            }
        }
    )
    assert normalized["calibration_phase"] == "warmup"
    assert normalized["pre_scoring_blockers"] == [
        {
            "bot_guid": 1306,
            "reason": "persistent_setup_preexisting_pet_without_native_receipt",
            "attempts": 0,
            "pet_present": True,
            "pet_spellbook_sha256": "a" * 64,
            "pet_admission_spellbook_sha256": "",
        }
    ]


def _debug_result_with_pet_stats() -> dict:
    return {
        "raidMetrics": {
            "parties": [
                {
                    "players": [
                        {
                            "name": "canary",
                            "actions": [],
                            "pets": [],
                            "auras": [],
                            "resources": [],
                        }
                    ]
                }
            ]
        },
        "iterationsDone": 1,
        "firstIterationDuration": 300,
        "avgIterationDuration": 300,
        "logs": (
            '[0.00] [canary (#1) - Felhunter] Pet stats: '
            '{"Strength":453.000,"SpellPower":6923.550,}\n'
            '[0.00] [canary (#1) - Felhunter] Pet inherited stats: '
            '{"SpellPower":6923.550,}\n'
            '[0.00] [canary (#1) - Felhunter] Pet summoned\n'
        ),
    }


def test_review_preserves_action_identity_order_and_unmapped_gaps():
    review = build_review(wowsims_apl=_apl(), trinity_profile=_profile())

    assert review["schema"] == "trinity_wowsims_rotation_mechanics_review_v1"
    assert review["wowsims"]["action_count"] == 5
    assert review["comparison"]["shared_spell_ids"] == [49020, 49143]
    assert review["comparison"]["wowsims_only_spell_ids"] == [49184]
    assert review["comparison"]["trinity_only_spell_ids"] == [45462]
    assert review["comparison"]["priority_inversions"] == [
        {
            "spell_a": 49020,
            "spell_b": 49143,
            "wowsims_order": [1, 0],
            "trinity_order": [0, 1],
            "trinity_order_basis": "priority_bucket",
        }
    ]
    link = next(
        item for item in review["comparison"]["action_links"] if item["spell_id"] == 49143
    )
    assert link["wowsims"][0]["path"] == "priorityList[0].castSpell"
    assert link["trinity"][0]["priority_bucket"] == 2
    assert review["trinity"]["actions"][0]["weights"]["damage"] == 1.04
    assert review["review_sha256"] == build_review(
        wowsims_apl=_apl(), trinity_profile=_profile()
    )["review_sha256"]


def test_condition_families_are_review_leads_not_equivalence_claims():
    review = build_review(wowsims_apl=_apl(), trinity_profile=_profile())
    gaps = {row["spell_id"]: row for row in review["comparison"]["condition_family_gaps"]}

    assert gaps[49020]["unrepresented_in_trinity"] == ["proc_state"]
    assert 49143 not in gaps
    assert "not semantic-equivalence" in review["comparison"]["interpretation"]


def test_effective_stat_parity_admits_tuning_only_after_owner_and_pet_match():
    request, _ = _gear_fixture()
    review = build_review(
        wowsims_apl=_apl(),
        wowsims_request=request,
        wowsims_compute_stats=_compute_stats(),
        wowsims_result=_debug_result_with_pet_stats(),
        runtime_report=_effective_stats_runtime(),
    )

    parity = review["effective_stat_parity"]
    assert parity["status"] == "match"
    assert parity["tuning_admitted"] is True
    assert parity["owner"]["status"] == "match"
    assert parity["pet"]["status"] == "match"
    assert parity["pet"]["wowsims_inherited_reference"]["stat_vector"] == {
        "spell_power": 6923.55
    }
    assert review["gear_parity"]["status"] == "match"
    assert review["dps_tuning_gate"] == {
        "status": "match",
        "tuning_admitted": True,
        "required": [
            "gear_parity.status=match",
            "effective_stat_parity.status=match",
        ],
        "first_broken_edge": None,
    }

    mismatch = build_review(
        wowsims_compute_stats=_compute_stats(),
        wowsims_result=_debug_result_with_pet_stats(),
        runtime_report=_effective_stats_runtime(intellect=7_000),
    )["effective_stat_parity"]
    assert mismatch["status"] == "mismatch"
    assert mismatch["tuning_admitted"] is False
    assert mismatch["first_broken_edge"] == (
        "effective_stat_application_before_rotation_execution"
    )

    gear_mismatch = build_review(
        wowsims_apl=_apl(),
        wowsims_request=request,
        wowsims_compute_stats=_compute_stats(),
        wowsims_result=_debug_result_with_pet_stats(),
        runtime_report=_effective_stats_runtime(drift_first_item=True),
    )
    assert gear_mismatch["gear_parity"]["status"] == "mismatch"
    assert gear_mismatch["dps_tuning_gate"]["tuning_admitted"] is False
    assert gear_mismatch["dps_tuning_gate"]["first_broken_edge"] == (
        "gear_identity_before_effective_stat_application"
    )


def test_self_provided_baseline_uses_debug_result_and_allows_favorable_stats():
    runtime = _effective_stats_runtime(intellect=9_000)
    player = runtime["combat_calibration"]["previous_window"]["bots"][0][
        "scoring_start_stats"
    ]["player"]
    player["spell_power"] = 13_500
    player["spell_crit_pct"] = 26
    player["spell_speed_multiplier"] = 1.4
    aggregate = {
        "raidMetrics": {
            "parties": [
                {"players": [{"name": "canary", "actions": [], "pets": []}]}
            ]
        },
        "iterationsDone": 1,
    }

    review = build_review(
        wowsims_compute_stats=_compute_stats(),
        wowsims_result=aggregate,
        wowsims_debug_result=_debug_result_with_pet_stats(),
        runtime_report=runtime,
        reference_class="self_provided_baseline",
    )

    parity = review["effective_stat_parity"]
    assert parity["status"] == "match"
    assert parity["tuning_admitted"] is True
    assert parity["comparison_mode"] == (
        "one_sided_minimum_for_monotonic_throughput_stats"
    )
    assert {
        row["stat"]
        for row in parity["owner"]["checks"]
        if row["status"] == "favorable"
    } == {
        "intellect",
        "spell_power",
        "spell_crit_pct",
        "spell_speed_multiplier",
    }
    assert review["wowsims_result"]["debug_log_present"] is False
    assert review["wowsims_debug_result"]["debug_log_present"] is True

    lower = _effective_stats_runtime(intellect=7_000)
    lower_review = build_review(
        wowsims_compute_stats=_compute_stats(),
        wowsims_debug_result=_debug_result_with_pet_stats(),
        runtime_report=lower,
        reference_class="self_provided_baseline",
    )
    assert lower_review["effective_stat_parity"]["status"] == "mismatch"
    intellect = next(
        row
        for row in lower_review["effective_stat_parity"]["owner"]["checks"]
        if row["stat"] == "intellect"
    )
    assert intellect["status"] == "mismatch"


def test_consumable_parity_requires_inventory_backed_native_uses() -> None:
    request, _ = _gear_fixture()
    request["raid"]["parties"][0]["players"][0]["consumes"] = {
        "flaskId": 58086,
        "foodId": 62671,
        "prepotId": 58091,
        "potId": 58091,
    }
    runtime = _effective_stats_runtime()
    bot = runtime["combat_calibration"]["previous_window"]["bots"][0]
    bot["consumable_execution_observation"] = {
        "schema": "trinity_consumable_execution_v1",
        "inventory_backed": True,
        "flask": {
            "item_id": 58086,
            "native_use_count": 1,
            "inventory_count_before": 1,
            "inventory_count_after": 0,
            "expected_aura_observed": True,
        },
        "food": {
            "item_id": 62671,
            "native_use_count": 1,
            "inventory_count_before": 1,
            "inventory_count_after": 0,
            "expected_aura_observed": True,
        },
        "prepot": {
            "item_id": 58091,
            "native_use_count": 1,
            "inventory_count_before": 2,
            "inventory_count_after": 1,
            "expected_aura_observed": True,
        },
        "combat_potion": {
            "item_id": 58091,
            "native_use_count": 1,
            "inventory_count_before": 1,
            "inventory_count_after": 0,
            "expected_aura_observed": True,
        },
    }
    review = build_review(
        wowsims_apl=_apl(),
        wowsims_request=request,
        wowsims_compute_stats=_compute_stats(),
        wowsims_result=_debug_result_with_pet_stats(),
        runtime_report=runtime,
        reference_class="self_provided_baseline",
    )
    assert review["reference_class"] == "self_provided_baseline"
    assert review["consumable_parity"]["status"] == "match"
    assert review["dps_tuning_gate"]["tuning_admitted"] is True
    assert review["total_dps_comparison_gate"]["comparison_admitted"] is True
    assert "consumable_parity.status=match" in review[
        "total_dps_comparison_gate"
    ]["required"]


def test_static_consumable_aura_does_not_count_as_item_use() -> None:
    request, _ = _gear_fixture()
    request["raid"]["parties"][0]["players"][0]["consumes"] = {
        "flaskId": 58086,
        "foodId": 62671,
        "prepotId": 58091,
        "potId": 58091,
    }
    runtime = _effective_stats_runtime()
    bot = runtime["combat_calibration"]["previous_window"]["bots"][0]
    bot["reference_condition_observation"] = {
        "configured": {
            "flask_item_id": 58086,
            "food_item_id": 62671,
        },
        "dynamic_disabled": {
            "prepot_item_id": 0,
            "prepot_use_count": 0,
            "combat_potion_item_id": 0,
            "combat_potion_use_count": 0,
        },
    }
    review = build_review(
        wowsims_apl=_apl(),
        wowsims_request=request,
        wowsims_compute_stats=_compute_stats(),
        wowsims_result=_debug_result_with_pet_stats(),
        runtime_report=runtime,
        reference_class="self_provided_baseline",
    )
    assert review["consumable_parity"]["status"] == "mismatch"
    assert review["consumable_parity"]["inventory_backed"] is False
    assert review["consumable_parity"]["first_broken_edge"] == (
        "consumable_inventory_flask"
    )
    assert review["dps_tuning_gate"]["tuning_admitted"] is True
    assert review["total_dps_comparison_gate"] == {
        "status": "mismatch",
        "comparison_admitted": False,
        "required": [
            "gear_parity.status=match",
            "effective_stat_parity.status=match",
            "consumable_parity.status=match",
        ],
        "first_broken_edge": "consumable_inventory_flask",
        "trace_only_signals_remain_usable": True,
    }


def test_review_preserves_zero_priority_bucket():
    profile = _profile()
    profile["actions"][0]["priority_bucket"] = 0
    review = build_review(wowsims_apl=_apl(), trinity_profile=profile)
    row = next(
        action
        for action in review["trinity"]["actions"]
        if action["identity"]["id"] == 49020
    )
    assert row["priority_bucket"] == 0


def test_affliction_runtime_profile_covers_the_pinned_apl_player_spells():
    request_catalog = json.loads(
        (ROOT / "experiments/configs/wowsims_cata_dps_reference_requests_v1.json").read_text()
    )
    request = next(
        row for row in request_catalog["requests"]
        if row["target_spec"] == "affliction_warlock"
    )
    native_request_path = request["result"]["artifacts"]["native_request"]["path"]
    if native_request_path is None:
        # The checked catalog is deliberately fail-closed until the refreshed
        # fixture is promoted.  Preserve the coverage assertion once a native
        # request exists, but make the pending state explicit rather than
        # treating it as a filesystem error.
        assert request["result"]["status"] == "requires_generation"
        return
    native_path = ROOT / native_request_path
    apl = find_wowsims_apl(json.loads(native_path.read_text()), player_index=0)
    normalized = normalize_wowsims_apl(apl)
    apl_spells = {
        int(action["identity"]["id"])
        for action in normalized["actions"]
        if action.get("identity", {}).get("kind") == "spell"
    }

    target_catalog = json.loads(
        (ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json").read_text()
    )
    target = next(
        row for row in target_catalog["targets"]
        if row["spec_target_id"] == "affliction_warlock"
    )
    assert apl_spells <= set(target["action_profile_spell_ids"])

    migration = (
        ROOT
        / "sql/custom/world/2026_08_16_01_affliction_warlock_apl_rotation.sql"
    ).read_text()
    for spell_id in apl_spells:
        assert f", {spell_id}," in migration
    assert "  348," not in migration
    assert "  17962," not in migration


def test_affliction_execute_priority_consumes_fel_flame_before_drain_soul():
    migration = (
        ROOT
        / "sql/custom/world/2026_08_17_00_affliction_execute_priority.sql"
    ).read_text()

    # The pinned default.apl.json has Fel Flame at priorityList[13] and Drain
    # Soul at priorityList[14].  In the live profile both are execute-capable,
    # so the lower Trinity bucket must belong to Fel Flame.  This migration is
    # deliberately limited to ordering; native proc/channel and health gates
    # remain defined by the existing profile rows and core Spell checks.
    fel_flame_start = migration.index("SET `action`.`priority_bucket` = 8")
    next_update = migration.index(
        "UPDATE `bot_rotation_action` AS `action`", fel_flame_start + 1
    )
    fel_flame = migration[fel_flame_start:next_update]
    drain_soul = migration[migration.index("SET `action`.`priority_bucket` = 9") :]
    assert "`action`.`sort_order` = 80" in fel_flame
    assert "`action`.`spell_id` = 77799" in fel_flame
    assert "`action`.`sort_order` = 90" in drain_soul
    assert "`action`.`spell_id` = 1120" in drain_soul


def test_runtime_report_keeps_selection_submission_landing_and_rejection_separate():
    runtime = {
        "trace": {
            "entries": [
                {
                    "bot_guid": 11,
                    "timestamp_ms": 100,
                    "combat_attempt": {
                        "recorded_at_ms": 100,
                        "action": {"spell_id": 49143},
                        "failure": {"result": "global_cooldown", "reason": "global_cooldown"},
                    },
                },
                {
                    "bot_guid": 11,
                    "timestamp_ms": 200,
                    "combat_attempt": {
                        "recorded_at_ms": 200,
                        "action": {"spell_id": 49020},
                        "failure": {"result": "ok", "reason": ""},
                    },
                },
            ]
        },
        "previous_window": {
            "bots": [
                {
                    "snapshot": {
                        "decision": {
                            "action": "move_to_validation_route_assist_target",
                            "result": "native_path_submitted",
                            "handler": "validation_route",
                        },
                        "movement": {
                            "is_moving": True,
                            "distance_moved_since_last_decision": 7.5,
                        },
                    },
                    "diagnosis": {
                        "diagnosis_code": "normal_combat",
                        "route_progress": {
                            "no_progress": {"reason": "route_target_combat_progress"}
                        },
                    },
                    "action_attempts": [
                        {"spell_id": 49143, "count": 9},
                        {"spell_id": 49020, "count": 4},
                    ],
                    "spell_damage": [{"spell_id": 49020, "damage": 1234}],
                    "last_chosen_action": {"spell_id": 49143},
                    "last_action_rejections": [
                        {"spell_id": 49184, "reason": "missing_self_aura"}
                    ],
                }
            ]
        },
    }
    normalized = normalize_runtime_report(runtime)

    assert normalized["attempt_counts_by_spell"] == {"49020": 4, "49143": 9}
    assert normalized["damage_by_spell"] == {"49020": 1234}
    assert normalized["chosen_counts_by_spell"] == {"49143": 1}
    assert normalized["result_counts"] == {"global_cooldown": 1, "ok": 1}
    assert normalized["rejection_reason_counts"] == {
        "global_cooldown": 1,
        "missing_self_aura": 1,
    }
    assert normalized["pipeline_edges"] == {
        "action_selected_observed": 1,
        "native_submission_observed": 1,
    }
    assert normalized["decision_observation"] == {
        "action_counts": {"move_to_validation_route_assist_target": 1},
        "result_counts": {"native_path_submitted": 1},
        "handler_counts": {"validation_route": 1},
        "diagnosis_code_counts": {"normal_combat": 1},
        "route_progress_reason_counts": {"route_target_combat_progress": 1},
    }
    assert normalized["movement_observation"] == {
        "sample_count": 1,
        "moving_sample_count": 1,
        "moving_sample_ratio": 1.0,
        "distance_moved_since_last_decision_total": 7.5,
        "distance_moved_since_last_decision_max": 7.5,
    }


def test_runtime_report_reads_completed_combat_calibration_window():
    runtime = {
        "combat_calibration": {
            "phase": "complete",
            "previous_window": {
                "bots": [
                    {
                        "guid": 1306,
                        "elapsed_seconds": 300.0,
                        "damage": 6339687,
                        "dps": 21132.29,
                        "pet_damage": 404927,
                        "action_attempts": [
                            {"spell_id": 686, "count": 85},
                            {"spell_id": 1120, "count": 4},
                        ],
                        "spell_damage": [
                            {"spell_id": 686, "damage": 1857836, "event_count": 85},
                            {"spell_id": 1120, "damage": 603362, "event_count": 4},
                        ],
                        "primary_pet_spell_damage": [
                            {"spell_id": 0, "damage": 416790, "event_count": 199},
                            {"spell_id": 54049, "damage": 1332284, "event_count": 50},
                        ],
                        "pet_execution_observation": {
                            "sample_count": 600,
                            "alive_samples": 600,
                            "alive_ratio": 1.0,
                            "attacking_samples": 598,
                            "attacking_ratio": 0.9966666667,
                            "target_match_samples": 598,
                            "target_match_ratio": 0.9966666667,
                            "command_attack_samples": 598,
                            "command_attack_ratio": 0.9966666667,
                            "last_victim_guid": 77,
                            "diagnostic_basis": "decision_timeline_pet_state",
                        },
                        "result_counts": {"ok": 148, "no_action": 389},
                        "quality_metrics": {
                            "active_uptime_ratio": 1.0,
                            "movement_range_loss_ratio": 0.0,
                        },
                        "decision_timeline": [
                            {
                                "elapsed_ms": 1000,
                                "spell_id": 686,
                                "result": "ok",
                                "health": 900,
                                "max_health": 1000,
                                "mana": 700,
                                "max_mana": 1000,
                                "current_generic_spell_id": 686,
                                "current_channeled_spell_id": 0,
                                "pet_health": 800,
                                "pet_max_health": 1000,
                                "pet_alive": True,
                                "pet_victim_guid": 77,
                                "pet_attacking": True,
                                "pet_command_state": 1,
                                "pet_command_attack": True,
                                "pet_current_generic_spell_id": 54049,
                                "pet_current_channeled_spell_id": 0,
                                "pet_current_autorepeat_spell_id": 0,
                                "target_distance": 15.0,
                                "alive": True,
                            },
                            {
                                "elapsed_ms": 250000,
                                "spell_id": 0,
                                "result": "dead",
                                "health": 0,
                                "max_health": 1000,
                                "mana": 100,
                                "max_mana": 1000,
                                "target_distance": 15.0,
                                "alive": False,
                            },
                        ],
                        "off_target_damage_events": [
                            {
                                "elapsed_ms": 2000,
                                "attacker_guid": 1306,
                                "victim_guid": 77,
                                "victim_entry": 123,
                                "victim_type_id": 3,
                                "victim_is_owner": False,
                                "spell_id": 109800,
                                "current_generic_spell_id": 0,
                                "current_channeled_spell_id": 755,
                                "damage": 42,
                                "periodic_health_aura_candidates": [
                                    {
                                        "spell_id": 755,
                                        "holder_guid": 99,
                                        "caster_guid": 1306,
                                        "effect_index": 0,
                                        "aura_type": 20,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        }
    }

    normalized = normalize_runtime_report(runtime)

    assert normalized["attempt_counts_by_spell"] == {"1120": 4, "686": 85}
    assert normalized["damage_by_spell"] == {"1120": 603362, "686": 1857836}
    assert normalized["damage_event_counts_by_spell"] == {"1120": 4, "686": 85}
    assert normalized["primary_pet_damage_by_spell"] == {"0": 416790, "54049": 1332284}
    assert normalized["primary_pet_damage_event_counts_by_spell"] == {
        "0": 199,
        "54049": 50,
    }
    assert normalized["pet_execution_observations"] == [
        {
            "bot_guid": 1306,
            "sample_count": 600,
            "alive_samples": 600,
            "alive_ratio": 1.0,
            "attacking_samples": 598,
            "attacking_ratio": 0.9966666667,
            "target_match_samples": 598,
            "target_match_ratio": 0.9966666667,
            "command_attack_samples": 598,
            "command_attack_ratio": 0.9966666667,
            "last_victim_guid": 77,
            "diagnostic_basis": "decision_timeline_pet_state",
        }
    ]
    assert normalized["decision_timeline"][0]["pet_victim_guid"] == 77
    assert normalized["decision_timeline"][0]["pet_current_generic_spell_id"] == 54049
    assert normalized["result_counts"] == {"no_action": 389, "ok": 148}
    assert normalized["calibration_windows"] == [
        {
            "guid": 1306,
            "elapsed_seconds": 300.0,
            "damage": 6339687,
            "dps": 21132.29,
            "pet_damage": 404927,
            "quality_metrics": {
                "active_uptime_ratio": 1.0,
                "movement_range_loss_ratio": 0.0,
            },
        }
    ]
    assert normalized["timeline_summary"] == {
        "sample_count": 2,
        "first_death_elapsed_ms": 250000,
        "minimum_observed_health_ratio": 0.0,
        "movement_range_events": 0,
        "off_target_event_count": 1,
        "off_target_damage": 42,
    }
    assert normalized["off_target_damage_events"][0]["victim_entry"] == 123
    assert normalized["off_target_damage_events"][0]["current_channeled_spell_id"] == 755
    assert normalized["off_target_damage_events"][0]["periodic_health_aura_candidates"] == [
        {
            "spell_id": 755,
            "holder_guid": 99,
            "caster_guid": 1306,
            "effect_index": 0,
            "aura_type": 20,
        }
    ]


def test_runtime_report_reads_nested_persistent_setup_pet_execution_observation():
    runtime = {
        "combat_calibration": {
            "phase": "complete",
            "previous_window": {
                "bots": [
                    {
                        "guid": 1306,
                        "persistent_setup": {
                            "pet_execution_observation": {
                                "sample_count": 600,
                                "alive_ratio": 1.0,
                                "target_match_ratio": 0.997,
                            }
                        },
                    }
                ]
            },
        }
    }

    normalized = normalize_runtime_report(runtime)

    assert normalized["pet_execution_observations"] == [
        {
            "bot_guid": 1306,
            "sample_count": 600,
            "alive_ratio": 1.0,
            "target_match_ratio": 0.997,
        }
    ]


def test_runtime_timeline_is_bounded_and_observation_only_in_native_source():
    header = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text()
    source = "\n".join(
        path.read_text()
        for path in sorted(
            (ROOT / "src/server/game/Bots").glob("BotWorldPopulationMgr*.cpp")
        )
    )

    assert "std::vector<DecisionTimelineEntry> DecisionTimeline;" in header
    assert "std::vector<OffTargetDamageEvent> OffTargetDamageEvents;" in header
    assert "struct EffectiveStatVector" in header
    assert "EffectiveStatVector ScoringStartPlayerStats;" in header
    assert "EffectiveStatVector ScoringStartPetStats;" in header
    assert "metrics.DecisionTimeline.size() < 4096" in source
    assert "calibration->second.OffTargetDamageEvents.size() < 128" in source
    assert '\\\"decision_timeline\\\"' in source
    assert '\\\"off_target_damage_events\\\"' in source
    assert '\\\"current_channeled_spell_id\\\"' in source
    assert '\\\"pet_health\\\"' in source
    assert '\\\"periodic_health_aura_candidates\\\"' in source
    assert '\\\"scoring_start_stats\\\"' in source
    assert "bot, startedMs, metrics.ScoringStartPlayerStats);" in source
    assert "bot->GetPet(), startedMs, metrics.ScoringStartPetStats);" in source
    assert "SPELL_AURA_PERIODIC_HEALTH_FUNNEL" in source
    assert "victim == owner" in source


def test_route_mechanic_obligations_are_normalized_without_execution():
    route = {
        "scenario_id": "stonecore_5n",
        "routes": [
            {
                "step": 1,
                "route_node_id": "node-1",
                "label": "Corborus",
                "node_kind": "boss",
                "source_entry": 43438,
                "completion_policy": "boss_kill",
                "descent_action": "native_walkable_descent",
                "mechanic_profile": "stonecore_corborus",
                "mechanic_families": ["hazard_avoidance"],
                "map_id": 725,
                "x": 123.0,
                "y": 456.0,
                "z": 78.0,
                "expected_bot_count": 5,
                "required_evidence": ["regrouping", "pulls"],
                "evidence_contract": [{"evidence": "pulls", "required": True}],
                "tank_positioning": {"required": True, "actions": ["tank_positioning"]},
                "interrupt_assignments": {"required": False, "actions": ["interrupt"]},
                "mechanic_contract": {"formation_family": "spread", "spacing_yards": 8},
            }
        ],
    }
    review = build_review(route_manifest=route)
    node = review["mechanics"]["nodes"][0]

    assert node["target_entries"] == [43438]
    assert node["descent_action"] == "native_walkable_descent"
    assert node["coordinates"]["destination"] == {
        "x": 123.0,
        "y": 456.0,
        "z": 78.0,
        "o": None,
    }
    assert node["expected_membership"]["expected_bot_count"] == 5
    assert node["required_evidence"] == ["pulls", "regrouping"]
    assert [item["kind"] for item in node["obligations"]] == [
        "tank_positioning",
        "interrupt_assignments",
        "mechanic_contract",
    ]
    assert node["obligations"][-1]["fields"] == ["formation_family", "spacing_yards"]


def test_cli_exported_raid_request_rotation_can_be_found():
    request = {
        "raid": {
            "parties": [
                {
                    "players": [
                        {
                            "rotation": json.dumps(_apl()),
                        }
                    ]
                }
            ]
        }
    }
    assert find_wowsims_apl(request)["type"] == "TypeAPL"


def test_native_protojson_raid_request_snake_case_is_normalized():
    request = {
        "raid": {
            "parties": [
                {
                    "players": [
                        {
                            "rotation": {
                                "prepull_actions": [],
                                "priority_list": [
                                    {
                                        "action": {
                                            "cast_spell": {
                                                "spell_id": {"spell_id": 49143}
                                            },
                                            "condition": {
                                                "current_runic_power": {}
                                            },
                                        }
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
    }

    apl = find_wowsims_apl(request)

    assert apl["priorityList"][0]["action"]["castSpell"]["spellId"] == {
        "spellId": 49143
    }
    assert normalize_wowsims_apl(apl)["actions"][0]["condition_families"] == [
        "primary_power"
    ]


def test_real_condition_concepts_keep_scope_resources_and_spec_state():
    apl = {
        "priorityList": [
            {
                "action": {
                    "condition": {
                        "and": {
                            "vals": [
                                {"spellCanCast": {"spellId": {"spellId": 53209}}},
                                {"cmp": {"lhs": {"currentFocus": {}}, "rhs": {"const": {"val": "50"}}}},
                                {"druidCurrentEclipsePhase": {"eclipsePhase": "NeutralPhase"}},
                                {
                                    "auraIsActive": {
                                        "sourceUnit": {"type": "CurrentTarget"},
                                        "auraId": {"spellId": 44457},
                                    }
                                },
                            ]
                        }
                    },
                    "castSpell": {"spellId": {"spellId": 53209}},
                }
            }
        ]
    }

    normalized = normalize_wowsims_apl(apl)
    row = normalized["actions"][0]

    assert row["condition_families"] == [
        "action_availability",
        "aura_state",
        "primary_power",
        "spec_resource_state",
        "target_scope",
    ]
    assert normalized["unmapped_condition_leaves"] == []


def test_channel_movement_and_special_actions_are_not_silently_dropped():
    apl = {
        "priorityList": [
            {
                "action": {
                    "channelSpell": {
                        "spellId": {"spellId": 740},
                        "interruptIf": {"cmp": {"lhs": {"currentTime": {}}, "rhs": {"const": {"val": "2s"}}}},
                    }
                }
            },
            {"action": {"move": {"rangeFromTarget": {"const": {"val": "9"}}}}},
            {"action": {"moveDuration": {"duration": {"const": {"val": "1s"}}}}},
            {"action": {"resetSequence": {"sequenceName": "fiend"}}},
            {"action": {"catOptimalRotationAction": {}}},
        ]
    }

    normalized = normalize_wowsims_apl(apl)

    assert [row["action_kind"] for row in normalized["actions"]] == [
        "channelSpell",
        "move",
        "moveDuration",
        "resetSequence",
        "catOptimalRotationAction",
    ]
    assert normalized["actions"][0]["identity"] == {
        "kind": "spell",
        "id": 740,
        "tag": None,
    }
    assert normalized["actions"][0]["condition_families"] == ["encounter_time"]


def test_prepull_timing_and_phase_mismatch_are_explicit():
    apl = {
        "prepullActions": [
            {
                "action": {"castSpell": {"spellId": {"spellId": 42650}}},
                "doAtValue": {"const": {"val": "-6s"}},
            }
        ],
        "priorityList": [],
    }
    profile = {
        "profile": {},
        "actions": [
            {
                "spell_id": 42650,
                "priority_bucket": 1,
                "sort_order": 1,
                "category": "cooldown",
                "gates": {},
            }
        ],
    }

    review = build_review(wowsims_apl=apl, trinity_profile=profile)

    assert review["comparison"]["wowsims_prepull_only_spell_ids"] == [42650]
    assert review["comparison"]["phase_mismatches"] == [
        {
            "spell_id": 42650,
            "wowsims_phase": "prepull_only",
            "trinity_phase": "combat_profile",
            "wowsims_entries": [
                {
                    "path": "prepullActions[0].castSpell",
                    "schedule": {"const": {"val": "-6s"}},
                    "schedule_sha256": review["wowsims"]["actions"][0][
                        "schedule_sha256"
                    ],
                }
            ],
        }
    ]


def test_canonical_route_jsonl_requires_and_applies_scenario_selection(tmp_path: Path):
    path = tmp_path / "validation_routes.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"scenario_id": "old", "step": 1, "route_node_id": "old-node"},
                {
                    "scenario_id": "stonecore_5h",
                    "step": 15,
                    "route_node_id": "descent-node",
                    "descent_action": "native_walkable_descent",
                },
            ]
        )
        + "\n"
    )

    selected = load_route_document(path, "stonecore_5h")

    assert selected["scenario_id"] == "stonecore_5h"
    assert [row["route_node_id"] for row in selected["routes"]] == ["descent-node"]


def test_profile_dump_contract_exposes_executable_gates_for_review():
    source = Path("src/server/game/Bots/BotClassSpecActionProfile.cpp").read_text()

    for token in (
        r'\"dump_schema\":\"bot_db_rotation_profile_dump_v2\"',
        r'\"min_primary_power_pct\"',
        r'\"max_primary_power_pct\"',
        r'\"maintain_aura_id\"',
        r'\"refresh_aura_below_ms\"',
        r'\"requires_melee_range\"',
        r'\"requires_moving\"',
    ):
        assert token in source


def test_read_only_database_profile_is_explicitly_not_a_runtime_snapshot():
    document = trinity_profile_document_from_database_rows(
        {
            "class_id": 6,
            "spec_tag": "frost_death_knight",
            "role": "dps",
            "range_band": "melee",
            "version": 11,
        },
        [
            {
                "sort_order": 52,
                "spell_id": 49143,
                "category": "spender",
                "priority_bucket": 2,
                "damage_weight": 1.06,
                "min_primary_power_pct": 0.70,
            }
        ],
    )

    assert document["source_authority"] == (
        "world_database_read_only_static_not_runtime_snapshot"
    )
    assert document["snapshot_generation"] is None
    assert document["snapshot_content_hash"] is None
    assert document["actions"][0]["weights"]["damage"] == 1.06
    assert document["actions"][0]["gates"]["min_primary_power_pct"] == 0.70
    assert build_review(trinity_profile=document)["trinity"]["identity_status"] == (
        "informational_only_identity_incomplete"
    )


def test_same_bucket_without_runtime_scores_is_uncertain_not_an_inversion():
    apl = {
        "priorityList": [
            {"action": {"castSpell": {"spellId": {"spellId": 100}}}},
            {"action": {"castSpell": {"spellId": {"spellId": 200}}}},
        ]
    }
    profile = {
        "profile": {},
        "actions": [
            {"spell_id": 200, "priority_bucket": 1, "sort_order": 1, "gates": {}},
            {"spell_id": 100, "priority_bucket": 1, "sort_order": 2, "gates": {}},
        ],
    }

    comparison = build_review(wowsims_apl=apl, trinity_profile=profile)["comparison"]

    assert comparison["priority_inversions"] == []
    assert comparison["priority_uncertain_pairs"] == [
        {
            "spell_a": 100,
            "spell_b": 200,
            "wowsims_order": [0, 1],
            "reason": "runtime_candidate_score_missing",
        }
    ]


def test_proc_timing_is_not_misclassified_as_encounter_time():
    apl = {
        "priorityList": [
            {
                "action": {
                    "condition": {
                        "cmp": {
                            "lhs": {"trinketProcsMinRemainingTime": {}},
                            "rhs": {"const": {"val": "3s"}},
                        }
                    },
                    "castSpell": {"spellId": {"spellId": 300}},
                }
            }
        ]
    }

    row = normalize_wowsims_apl(apl)["actions"][0]

    assert row["condition_families"] == ["proc_state"]


def _wowsims_result() -> dict:
    return {
        "raidMetrics": {
            "parties": [
                {
                    "players": [
                        {
                            "name": "Frost",
                            "dps": {"avg": 42000.0},
                            "actions": [
                                {
                                    "id": {"spellId": 49020, "tag": 1},
                                    "isMelee": True,
                                    "isPassive": False,
                                    "targets": [
                                        {
                                            "unitIndex": 0,
                                            "casts": 4,
                                            "hits": 3,
                                            "crits": 1,
                                            "damage": 400.0,
                                            "castTimeMs": 4000,
                                        }
                                    ],
                                },
                                {
                                    "id": {"spellId": 99999},
                                    "isPassive": True,
                                    "targets": [{"unitIndex": 0, "casts": 2, "damage": 50.0}],
                                },
                            ],
                            "auras": [
                                {
                                    "id": {"spellId": 51124},
                                    "uptimeSecondsAvg": 42.0,
                                    "procsAvg": 5.0,
                                }
                            ],
                            "resources": [
                                {
                                    "id": {"spellId": 49020},
                                    "type": "ResourceTypeRunicPower",
                                    "events": 4,
                                    "gain": -160.0,
                                    "actualGain": -160.0,
                                }
                            ],
                            "pets": [
                                {
                                    "name": "Ghoul",
                                    "actions": [
                                        {
                                            "id": {"spellId": 91776},
                                            "targets": [{"unitIndex": 0, "casts": 6, "damage": 80.0}],
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ]
        },
        "encounterMetrics": {"targets": []},
        "logs": "\n".join(
            [
                "[-6.00] [Frost (#1)] Casting {SpellID: 42650} (Cost = 0.000, Cast Time = 1s, Effective Time = 1s)",
                "[-5.00] [Frost (#1)] Completed cast {SpellID: 42650}",
                "[0.00] [Frost (#1)] Aura gained: {SpellID: 51124}",
                "[1.00] [Frost (#1)] Spent 40.000 runic power from {SpellID: 49020, Tag: 1} (100.000 --> 60.000) of 100 total.",
                "[1.00] [Frost (#1)] [Target 1] {SpellID: 49020, Tag: 1} Hit for 100.000 damage (SpellSchool: 16). (Threat: 100.000)",
                "[2.00] [Frost (#1)] [DEBUG] Moving to 2.0 yards",
            ]
        ),
        "firstIterationDuration": 300,
        "avgIterationDuration": 300,
        "error": None,
        "iterationsDone": 2,
    }


def test_wowsims_result_preserves_aggregate_actions_pets_and_timeline():
    normalized = normalize_wowsims_result(_wowsims_result())

    player_action = next(
        row for row in normalized["action_metrics"]
        if row["identity"] == {"kind": "spell", "id": 49020, "tag": 1}
    )
    assert player_action["per_iteration_target_metric_sums"]["casts"] == 2.0
    assert player_action["per_iteration_target_metric_sums"]["damage"] == 200.0
    assert any(row["source"]["kind"] == "pet" for row in normalized["action_metrics"])
    assert normalized["timeline"]["event_kind_counts"] == {
        "aura_gained": 1,
        "cast_completed": 1,
        "cast_started": 1,
        "landed_effect": 1,
        "movement": 1,
        "resource_changed": 1,
    }
    resource_event = next(
        row for row in normalized["timeline"]["events"]
        if row["kind"] == "resource_changed"
    )
    assert resource_event["resource"] == {
        "name": "runic power",
        "direction": "spent",
        "amount": 40.0,
        "before": 100.0,
        "after": 60.0,
    }
    assert resource_event["identity"] == {"kind": "spell", "id": 49020, "tag": 1}


def test_wowsims_result_links_apl_execution_to_native_runtime_without_claiming_equivalence():
    apl = {
        "priorityList": [
            {"action": {"castSpell": {"spellId": {"spellId": 49020, "tag": 1}}}}
        ]
    }
    runtime = {
        "previous_window": {
            "bots": [
                {
                    "action_attempts": [{"spell_id": 49020, "count": 3}],
                    "spell_damage": [{"spell_id": 49020, "damage": 300}],
                }
            ]
        }
    }

    review = build_review(
        wowsims_apl=apl,
        wowsims_result=_wowsims_result(),
        runtime_report=runtime,
    )

    apl_link = review["execution_comparison"]["apl_to_wowsims_result"]
    runtime_link = review["execution_comparison"][
        "wowsims_result_to_trinity_runtime"
    ]
    assert apl_link["apl_spell_ids_observed_as_player_actions"] == [49020]
    assert runtime_link["shared_observed_spell_ids"] == [49020]
    assert "per-iteration aggregates" in runtime_link["interpretation"]


def test_execution_review_exposes_spec_scope_timeline_and_rough_action_dps_impact():
    runtime = {
        "previous_window": {
            "bots": [
                {
                    "elapsed_seconds": 300.0,
                    "action_attempts": [{"spell_id": 49020, "count": 3}],
                    "spell_damage": [{"spell_id": 49020, "damage": 300}],
                }
            ]
        }
    }

    review = build_review(
        wowsims_apl=_apl(),
        wowsims_result=_wowsims_result(),
        trinity_profile=_profile(),
        runtime_report=runtime,
    )

    assert review["comparison"]["spec_identity"] == {
        "class_id": 6,
        "spec_tag": "frost_death_knight",
        "role": "dps",
    }
    assert review["comparison"]["mismatch_summary"]["priority_inversion_count"] == 1

    impact = review["execution_comparison"]["wowsims_result_to_trinity_runtime"]
    assert impact["rough_dps_impact"]["status"] == "estimated"
    action = next(
        row for row in impact["rough_dps_impact"]["action_impacts"]
        if row["spell_id"] == 49020
    )
    assert action["apl_paths"] == [
        "priorityList[1].strictSequence.actions[0].castSpell"
    ]
    assert action["wowsims_timeline"]["event_kind_counts"] == {
        "landed_effect": 1,
        "resource_changed": 1,
    }
    assert action["wowsims_per_iteration_casts"] == 2.0
    assert action["wowsims_damage_per_cast"] == 100.0
    assert action["expected_damage_at_trinity_cadence"] == 300.0
    assert action["rough_damage_model_dps_delta"] == 0.0
    assert action["rough_dps_delta_sim_minus_runtime"] == pytest.approx(-1 / 3)


def _cast_mix_apl() -> dict:
    return {
        "priorityList": [
            {"action": {"castSpell": {"spellId": {"spellId": 100}}}},
            {"action": {"castSpell": {"spellId": {"spellId": 200}}}},
        ]
    }


def _cast_mix_result(
    *, casts_100: int = 3, casts_200: int = 1, duration_seconds: float | None = None
) -> dict:
    def action(spell_id: int, casts: int, *, tag: int = 0, passive: bool = False) -> dict:
        return {
            "id": {"spellId": spell_id, "tag": tag},
            "isPassive": passive,
            "targets": [{"unitIndex": 0, "casts": casts}],
        }

    result = {
        "iterationsDone": 1,
        "raidMetrics": {
            "parties": [
                {
                    "players": [
                        {
                            "name": "CastMix",
                            "actions": [
                                action(100, casts_100),
                                action(200, casts_200),
                                action(100, 99, tag=9),
                                action(200, 88, passive=True),
                                action(300, 77),
                            ],
                            "pets": [{"actions": [action(100, 66)]}],
                        }
                    ]
                }
            ]
        },
        "logs": "\n".join(
            [
                "[0.00] [CastMix (#1)] Casting {SpellID: 100}",
                "[0.01] [CastMix (#1)] Casting {SpellID: 100, Tag: 9}",
                "[0.02] [CastMix (#1) - Pet (#2)] Casting {SpellID: 100}",
                "[0.03] [CastMix (#1)] Casting {SpellID: 200}",
            ]
        ),
    }
    if duration_seconds is not None:
        result["firstIterationDuration"] = duration_seconds
    return result


def _cast_mix_runtime(successes: list[tuple[int, str]]) -> dict:
    return {
        "combat_calibration": {
            "phase": "complete",
            "bots": [
                {
                    "guid": 7,
                    "action_attempts": [
                        {"spell_id": 100, "count": 999},
                        {"spell_id": 200, "count": 999},
                    ],
                    "decision_timeline": [
                        {"elapsed_ms": index * 500, "spell_id": spell_id, "result": result}
                        for index, (spell_id, result) in enumerate(successes)
                    ],
                }
            ],
        }
    }


def _cast_mix_runtime_with_duration(
    successes: list[tuple[int, str]], duration_seconds: float | None
) -> dict:
    runtime = _cast_mix_runtime(successes)
    if duration_seconds is not None:
        runtime["combat_calibration"]["bots"][0]["elapsed_seconds"] = duration_seconds
    return runtime


def test_cast_mix_exact_matching_distribution_uses_root_aggregate_metrics():
    review = build_review(
        wowsims_apl=_cast_mix_apl(),
        wowsims_result=_cast_mix_result(),
        runtime_report=_cast_mix_runtime([(100, "ok")] * 3 + [(200, "ok")]),
    )

    comparison = review["execution_comparison"]["cast_mix"]
    assert comparison["status"] == "ok"
    assert comparison["cast_mix_overlap"] == 1.0
    assert comparison["total_variation_distance"] == 0.0
    assert comparison["maximum_absolute_share_delta"] == 0.0
    assert [row["spell_id"] for row in comparison["per_spell"]] == [100, 200]
    assert comparison["per_spell"][0]["wowsims_identities"] == [
        {"kind": "spell", "id": 100, "tag": 0}
    ]


def test_cast_mix_mismatch_emits_exact_overlap_tv_and_max_delta():
    comparison = build_review(
        wowsims_apl=_cast_mix_apl(),
        wowsims_result=_cast_mix_result(),
        runtime_report=_cast_mix_runtime(
            [(100, "ok"), (200, "ok"), (200, "ok"), (300, "ok")]
        ),
    )["execution_comparison"]["cast_mix"]

    assert comparison["cast_mix_overlap"] == 0.5
    assert comparison["total_variation_distance"] == 0.5
    assert comparison["maximum_absolute_share_delta"] == 0.5
    assert comparison["maximum_absolute_share_delta_spell_ids"] == [100]
    assert comparison["shared_spell_ids"] == [100, 200]
    assert comparison["trinity_only_spell_ids"] == [300]


def test_cast_mix_excludes_tagged_children_pets_passives_and_failed_decisions():
    comparison = build_review(
        wowsims_apl=_cast_mix_apl(),
        wowsims_result=_cast_mix_result(),
        runtime_report=_cast_mix_runtime(
            [
                (100, "ok"),
                (100, "global_cooldown"),
                (100, "failed"),
                (200, "ok"),
                (0, "ok"),
            ]
        ),
    )["execution_comparison"]["cast_mix"]

    rows = {row["spell_id"]: row for row in comparison["per_spell"]}
    assert rows[100]["wowsims_count"] == 3.0
    assert rows[100]["trinity_count"] == 1
    assert rows[200]["wowsims_count"] == 1.0
    assert rows[200]["trinity_count"] == 1
    assert 300 not in rows
    assert comparison["wowsims_total_casts"] == 4.0
    assert comparison["trinity_total_casts"] == 2
    assert comparison["timeline_reconciliation"]["cast_started_count"] == 2
    assert comparison["timeline_reconciliation"]["counts_by_spell"] == {
        "100": 1,
        "200": 1,
    }


def test_cast_mix_fails_closed_without_successful_completed_timeline():
    comparison = build_review(
        wowsims_apl=_cast_mix_apl(),
        wowsims_result=_cast_mix_result(),
        runtime_report=_cast_mix_runtime(
            [(100, "global_cooldown"), (0, "ok"), (200, "failed")]
        ),
    )["execution_comparison"]["cast_mix"]

    assert comparison["status"] == "insufficient_data"
    assert comparison["reason"] == "missing_successful_trinity_timeline"
    assert comparison["trinity_total_casts"] == 0


def test_cast_mix_reports_cadence_even_when_distributions_match():
    comparison = build_review(
        wowsims_apl=_cast_mix_apl(),
        wowsims_result=_cast_mix_result(duration_seconds=100.0),
        runtime_report=_cast_mix_runtime_with_duration(
            [(100, "ok")] * 3 + [(200, "ok")], 200.0
        ),
    )["execution_comparison"]["cast_mix"]

    assert comparison["cast_mix_overlap"] == 1.0
    assert comparison["cast_cadence"] == {
        "status": "available",
        "wowsims_duration_seconds": 100.0,
        "trinity_duration_seconds": 200.0,
        "wowsims_casts_per_second": 0.04,
        "trinity_casts_per_second": 0.02,
        "trinity_to_wowsims_cadence_ratio": 0.5,
        "trinity_minus_wowsims_casts_per_second": -0.02,
    }


def test_cast_mix_keeps_share_comparison_usable_without_durations():
    comparison = build_review(
        wowsims_apl=_cast_mix_apl(),
        wowsims_result=_cast_mix_result(),
        runtime_report=_cast_mix_runtime([(100, "ok")] * 3 + [(200, "ok")]),
    )["execution_comparison"]["cast_mix"]

    assert comparison["status"] == "ok"
    assert comparison["cast_cadence"]["status"] == "insufficient_duration_data"
    assert comparison["cast_cadence"]["wowsims_casts_per_second"] is None
    assert comparison["cast_cadence"]["trinity_casts_per_second"] is None


def test_cast_cadence_separates_ordinary_starts_channel_starts_and_landed_events():
    apl = _cast_mix_apl()
    apl["priorityList"].append(
        {
            "action": {
                "channelSpell": {
                    "spellId": {"spellId": 1120},
                }
            }
        }
    )
    result = _cast_mix_result(duration_seconds=10.0)
    result["raidMetrics"]["parties"][0]["players"][0]["actions"].append(
        {
            "id": {"spellId": 1120, "tag": 0},
            "isPassive": False,
            "targets": [{"unitIndex": 0, "casts": 2, "ticks": 4}],
        }
    )
    runtime = _cast_mix_runtime_with_duration(
        [(100, "ok"), (100, "ok"), (100, "ok"), (1120, "ok"), (1120, "ok")],
        10.0,
    )
    runtime["combat_calibration"]["bots"][0]["spell_damage"] = [
        {"spell_id": 1120, "damage": 100, "event_count": 4}
    ]

    comparison = build_review(
        wowsims_apl=apl,
        wowsims_result=result,
        runtime_report=runtime,
    )["execution_comparison"]["cast_mix"]
    components = comparison["cast_cadence_components"]

    assert components["classification"] == {
        "ordinary_cast_spell_ids": [100, 200],
        "channel_spell_ids": [1120],
        "ambiguous_spell_ids": [],
        "non_comparable_apl_action_kinds": [],
    }
    assert components["ordinary_cast_starts"]["wowsims_count"] == 4.0
    assert components["ordinary_cast_starts"]["trinity_count"] == 3
    assert components["ordinary_cast_starts"]["wowsims_per_second"] == 0.4
    assert components["ordinary_cast_starts"]["trinity_per_second"] == 0.3
    assert components["channel_starts"]["wowsims_count"] == 2.0
    assert components["channel_starts"]["trinity_count"] == 2
    assert components["channel_landed_events"]["wowsims_count"] == 4.0
    assert components["channel_landed_events"]["trinity_count"] == 4
    assert (
        components["channel_landed_events"]["trinity_count_label"]
        == "runtime_spell_damage_event_count_not_proven_tick_equivalent"
    )
    # The old aggregate remains available, but is explicitly not the ordinary rate.
    assert comparison["cast_cadence"]["wowsims_casts_per_second"] == 0.6
    assert comparison["cast_cadence_limitations"]


def test_cast_cadence_excludes_special_actions_without_equating_them_to_casts():
    apl = _cast_mix_apl()
    apl["priorityList"].append(
        {"action": {"autocastOtherCooldowns": {}}}
    )
    comparison = build_review(
        wowsims_apl=apl,
        wowsims_result=_cast_mix_result(),
        runtime_report=_cast_mix_runtime([(100, "ok")]),
    )["execution_comparison"]["cast_mix"]

    components = comparison["cast_cadence_components"]
    assert components["non_comparable_actions"] == {
        "status": "excluded_from_cadence",
        "used_for_cadence": False,
        "apl_action_kinds": ["autocastOtherCooldowns"],
        "apl_action_count": 1,
        "apl_paths": ["priorityList[2].autocastOtherCooldowns"],
        "reason": (
            "WoWSims special/off-GCD/structural actions have no native cast-start "
            "or landed-event identity in this comparison."
        ),
    }
    assert components["classification"]["non_comparable_apl_action_kinds"] == [
        "autocastOtherCooldowns"
    ]


def test_cast_mix_direct_helper_requires_normalized_completed_calibration():
    result = compare_cast_mix(
        {"actions": [{"phase": "combat", "identity": {"kind": "spell", "id": 100, "tag": None}}]},
        {
            "action_metrics": [
                {
                    "source": {"kind": "player"},
                    "identity": {"kind": "spell", "id": 100, "tag": 0},
                    "is_passive": False,
                    "per_iteration_target_metric_sums": {"casts": 1.0},
                }
            ],
            "timeline": {"events": []},
        },
        {
            "calibration_complete": True,
            "decision_timeline": [{"spell_id": 100, "result": "ok"}],
        },
    )
    assert result["status"] == "ok"
