from __future__ import annotations

import json
from pathlib import Path

from tools.bot_ml.review_rotation_mechanics import (
    build_review,
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


def test_affliction_runtime_profile_covers_the_pinned_apl_player_spells():
    request_catalog = json.loads(
        (ROOT / "experiments/configs/wowsims_cata_dps_reference_requests_v1.json").read_text()
    )
    request = next(
        row for row in request_catalog["requests"]
        if row["target_spec"] == "affliction_warlock"
    )
    native_path = ROOT / request["result"]["artifacts"]["native_request"]["path"]
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
