from __future__ import annotations

import copy
import hashlib
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.bot_ml.run_wowsims_exact_references import (
    WowsimsGenerationError,
    apl_action_variants_from_pinned_proto,
    apl_condition_variants_from_pinned_proto,
    canonical_sha256,
    canonical_json_bytes,
    decode_talent_spell_ids,
    glyph_slots_from_pinned_proto,
    load_slot_map,
    parse_compute_stats_validation,
    parse_dvc_pointer,
    parse_fresh_build_log_identity,
    parse_native_result,
    project_native_request_conditions,
    store_content_addressed_bytes,
    transform_apl_rotation,
    validate_exact_native_request_bytes,
    validate_dvc_bundle_pre_pull,
    validate_native_request_projection,
    validate_projection_against_request_contract,
    verify_artifact,
    verify_process_evidence,
)
from tools.bot_ml import run_wowsims_exact_references as exact_runner
from tools.bot_ml.build_wowsims_reference_requests import load_manifest, request_by_spec
from tools.bot_ml.phase8_fixture_contract import load_fixture_contract


def _condition_variants() -> set[str]:
    """Minimal pinned-proto-shaped APLValue oneof used by transform unit tests."""
    return {
        "const",
        "and",
        "or",
        "not",
        "cmp",
        "math",
        "number_targets",
        "aura_is_active",
        "aura_is_known",
        "aura_remaining_time",
        "dot_is_active",
        "spell_time_to_ready",
        "current_mana_percent",
    }


def fixture_contract() -> dict:
    canonical_fixture, _ = load_fixture_contract()
    canonical_native = canonical_fixture["specs"]["frost_death_knight"][
        "native_request"
    ]
    return {
        "target": {
            "level": 88,
            "armor": 11977,
            "live_target_attacks": False,
        },
        "encounter": {
            "duration_seconds": 300,
            "duration_variation_seconds": 0,
            "execute_proportions": {
                "90": 0.9,
                "35": 0.35,
                "25": 0.25,
                "20": 0.2,
            },
        },
        "distance_contracts": {
            "melee": {"simulator_yards": 2.0},
            "ranged": {"simulator_yards": 15.0},
        },
        "specs": {
            "frost_death_knight": {
                "lane": "melee",
                "simulator_options": {
                    "options": {
                        "class_options": {"pet_uptime": 1.0},
                    }
                },
                "pet_setup": {"required": False, "kind": "none"},
                "prepull_setup": {
                    "form_presence": {"required_aura_spell_ids": [48265]}
                },
                "initial_state": {
                    "player_powers": [
                        {
                            "name": "runic_power",
                            "power_type": 6,
                            "mode": "exact",
                            "display_value": 0,
                            "native_value": 0,
                        }
                    ],
                    "runes_ready_mask": 63,
                },
                "native_request": {
                    "player_spec_key": "frost_death_knight",
                    "player_spec": {
                        "options": {
                            "class_options": {"pet_uptime": 1.0},
                        }
                    },
                    "race_id": 1,
                    "professions": ["ProfessionUnknown", "ProfessionUnknown"],
                    "player_fields": {"dark_intent_uptime": 0.0},
                    "glyph_item_ids": [
                        43543,
                        43547,
                        45806,
                        43548,
                        43826,
                        68793,
                    ],
                    "glyph_property_ids": [521, 525, 526, 557, 773, 945],
                    "consumables": {},
                    "individual_buffs": {
                        "dark_intent": False,
                        "power_infusion_count": 0,
                    },
                    "raid_buffs": {"bloodlust": False},
                    "party_buffs": {},
                    "target_debuffs": {},
                    "rotation_prepull_actions": [],
                    "apl_transform_policy": canonical_native[
                        "apl_transform_policy"
                    ],
                    "reference_execution_policy": canonical_native[
                        "reference_execution_policy"
                    ],
                    "external_windows": canonical_native["external_windows"],
                    "initial_state": {
                        "player_powers": [
                            {
                                "name": "runic_power",
                                "power_type": 6,
                                "mode": "exact",
                                "display_value": 0,
                                "native_value": 0,
                            }
                        ],
                        "runes_ready_mask": 63,
                    },
                },
                "runtime_expected": {
                    "pet_setup": {"runtime_projection_complete": True}
                },
            }
        },
    }


def native_request() -> dict:
    stats = [0] * 27
    stats[22] = 11977
    return {
        "sim_options": {
            "iterations": 2000,
            "random_seed": "101",
            "debug": False,
            "is_test": True,
        },
        "raid": {
            "num_active_parties": 1,
            "stagger_stormstrikes": False,
            "tanks": [],
            "target_dummies": 0,
            "parties": [
                {
                    "players": [
                        {
                            "race": "RaceHuman",
                            "class": "ClassDeathKnight",
                            "equipment": {
                                "items": [
                                    {
                                        "id": 78687,
                                        "random_suffix": 0,
                                        "enchant": 4208,
                                        "gems": [68779, 71883],
                                        "reforging": 161,
                                        "upgrade_step": "Base",
                                    }
                                ]
                            },
                            "talents_string": "2032-30330012233112012301-03",
                            "glyphs": {
                                "prime1": 43543,
                                "prime2": 43547,
                                "prime3": 45806,
                                "major1": 43548,
                                "major2": 43826,
                                "major3": 68793,
                                "minor1": 0,
                                "minor2": 0,
                                "minor3": 0,
                            },
                            "profession1": "ProfessionUnknown",
                            "profession2": "ProfessionUnknown",
                            "dark_intent_uptime": 0.0,
                            "distance_from_target": 2.0,
                            "consumables": {},
                            "buffs": {
                                "dark_intent": False,
                                "power_infusion_count": 0,
                            },
                            "enable_item_swap": False,
                            "item_swap": {
                                "mh_item": None,
                                "oh_item": None,
                                "ranged_item": None,
                                "items": [],
                                "prepull_bonus_stats": None,
                            },
                            "frost_death_knight": {
                                "options": {
                                    "class_options": {"pet_uptime": 1.0},
                                }
                            },
                            "rotation": {"prepull_actions": []},
                            "reaction_time_ms": 10,
                            "channel_clip_delay_ms": 0,
                            "in_front_of_target": False,
                            "cooldowns": {},
                            "bonus_stats": {"stats": [], "pseudo_stats": []},
                            "healing_model": {},
                            "database": {},
                        }
                    ],
                    "buffs": {},
                }
            ],
            "buffs": {"bloodlust": False},
            "debuffs": {},
        },
        "encounter": {
            "duration": 300,
            "duration_variation": 0,
            "execute_proportion_90": 0.9,
            "execute_proportion_35": 0.35,
            "execute_proportion_25": 0.25,
            "execute_proportion_20": 0.2,
            "targets": [
                {
                    "level": 88,
                    "mob_type": "MobTypeMechanical",
                    "stats": stats,
                    "swing_speed": 0,
                    "min_base_damage": 0,
                    "damage_spread": 0,
                    "parry_haste": False,
                    "dual_wield": False,
                    "dual_wield_penalty": False,
                    "suppress_dodge": False,
                    "tank_index": -1,
                    "second_tank_index": -1,
                    "disabled_at_start": False,
                    "target_inputs": [],
                }
            ],
        },
    }


def native_result(dps: float = 52_000.25) -> dict:
    return {
        "raidMetrics": {
            "dps": {"avg": dps},
            "parties": [{"players": [{"dps": {"avg": dps}}]}],
        },
        "encounterMetrics": {},
        "logs": "",
        "firstIterationDuration": 300,
        "avgIterationDuration": 300,
        "error": None,
        "iterationsDone": 2000,
    }


def compute_stats_result(*, validation: dict | None = None) -> dict:
    active = {
        "rotationStats": {
            "prepullActions": [],
            "priorityList": [
                {"validations": [] if validation is None else [validation]}
            ],
        },
        "metadata": {
            "spells": [
                {"id": {"spellId": 100, "tag": 0}, "isCastable": True}
            ]
        },
    }
    inactive = {"rotationStats": None, "metadata": None}
    return {
        "raidStats": {
            "parties": [{"players": [active, *[copy.deepcopy(inactive) for _ in range(4)]]}]
        },
        "errorResult": "",
    }


def test_content_addressed_artifact_is_relative_and_tamper_evident(
    tmp_path: Path,
) -> None:
    record = store_content_addressed_bytes(
        tmp_path, "native_requests", b"{}", suffix=".json"
    )
    assert not Path(record["path"]).is_absolute()
    path = verify_artifact(record, artifact_root=tmp_path, label="request")
    assert path.read_bytes() == b"{}"
    path.write_bytes(b"forged")
    with pytest.raises(WowsimsGenerationError, match="request:hash_mismatch"):
        verify_artifact(record, artifact_root=tmp_path, label="request")


def test_content_addressed_artifact_rejects_parent_path(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    record = {
        "path": "../outside.json",
        "sha256": "0" * 64,
        "byte_count": 2,
    }
    with pytest.raises(WowsimsGenerationError, match="unsafe_path"):
        verify_artifact(record, artifact_root=tmp_path, label="request")


def test_content_addressed_artifact_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_bytes(b"{}")
    link = tmp_path / "native_results" / "result.json"
    link.parent.mkdir()
    link.symlink_to(outside)
    record = {
        "path": "native_results/result.json",
        "sha256": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        "byte_count": 2,
    }
    with pytest.raises(WowsimsGenerationError, match="request:symlink"):
        verify_artifact(record, artifact_root=tmp_path, label="request")


def test_process_evidence_binds_transport_to_retained_log(tmp_path: Path) -> None:
    payload = b"validator output\n"
    record = store_content_addressed_bytes(
        tmp_path, "process_logs", payload, suffix=".log"
    )
    transport = {
        "transport_classification": "child_exited",
        "returncode_observed": True,
        "returncode": 0,
        "outer_timed_out": False,
        "controller_interrupted": False,
        "process_group_gone": True,
        "output_sha256": hashlib.sha256(payload).hexdigest(),
        "output_byte_count": len(payload),
    }
    assert (
        verify_process_evidence(
            transport,
            record,
            artifact_root=tmp_path,
            label="test_process",
        ).read_bytes()
        == payload
    )
    with pytest.raises(WowsimsGenerationError, match="process_output_identity"):
        verify_process_evidence(
            {**transport, "output_byte_count": len(payload) + 1},
            record,
            artifact_root=tmp_path,
            label="test_process",
        )


def test_talent_decoder_selects_exact_rank_spell() -> None:
    trees = [
        {
            "talents": [
                {"maxPoints": 2, "spellIds": [101, 102]},
                {"maxPoints": 3, "spellIds": [201, 202, 203]},
            ]
        }
    ]
    assert decode_talent_spell_ids("23", trees) == [102, 203]
    with pytest.raises(WowsimsGenerationError, match="talents:rank"):
        decode_talent_spell_ids("24", trees)


def test_glyph_slots_are_derived_from_pinned_proto_enum_item_ids() -> None:
    source = """
enum DeathKnightPrimeGlyph { NonePrime = 0; A = 43543; }
enum DeathKnightMajorGlyph { NoneMajor = 0; B = 43548; }
enum DeathKnightMinorGlyph { NoneMinor = 0; C = 43673; }
"""
    assert glyph_slots_from_pinned_proto([43543, 43548, 43673], source) == {
        "prime1": 43543,
        "major1": 43548,
        "minor1": 43673,
    }


def test_apl_transform_recursively_removes_forbidden_actions_only() -> None:
    fixture, _ = load_fixture_contract()
    policy = fixture["specs"]["shadow_priest"]["native_request"][
        "apl_transform_policy"
    ]
    action_variants = {
        "cast_spell",
        "strict_sequence",
        "autocast_other_cooldowns",
        "cast_all_stat_buff_cooldowns",
        "activate_all_stat_buff_proc_auras",
        "item_swap",
        "activate_aura",
        "activate_aura_with_stacks",
        "trigger_icd",
        "cancel_aura",
    }
    rotation = {
        "prepull_actions": [
            {"action": {"cast_spell": {"spell_id": {"spell_id": 6673}}}},
            {"action": {"item_swap": {"swap_set": "Swap1"}}},
            {"action": {"activate_all_stat_buff_proc_auras": {}}},
            {"action": {"cast_spell": {"spell_id": {"other_id": "OtherActionPotion"}}}},
        ],
        "priority_list": [
            {"action": {"cast_spell": {"spell_id": {"spell_id": 100}}}},
            {"action": {"autocast_other_cooldowns": {}}},
            {"action": {"cast_all_stat_buff_cooldowns": {}}},
            {"action": {"cast_spell": {"spell_id": {"item_id": 70142}}}},
            {"action": {"cancel_aura": {"aura_id": {"spell_id": 45529}}}},
            {
                "action": {
                    "strict_sequence": {
                        "actions": [
                            {"cast_spell": {"spell_id": {"spell_id": 26297}}},
                            {"cast_spell": {"spell_id": {"spell_id": 200}}},
                        ]
                    }
                }
            },
        ],
    }
    prepull = [
        {
            "action": {"cast_spell": {"spell_id": {"spell_id": 48265}}},
            "do_at_value": {"const": {"val": "-20s"}},
        }
    ]
    transformed, observed = transform_apl_rotation(
        rotation,
        policy,
        prepull_actions=prepull,
        action_variants=action_variants,
        condition_variants=_condition_variants(),
        equipped_item_ids=set(),
    )
    assert transformed["prepull_actions"] == prepull
    assert len(transformed["priority_list"]) == 2
    assert transformed["priority_list"][1]["action"]["strict_sequence"]["actions"] == [
        {"cast_spell": {"spell_id": {"spell_id": 200}}}
    ]
    assert observed["removed_action_count"] == 9
    assert observed["removed_source_prepull_action_count"] == 4
    assert observed["replacement_prepull_action_count"] == 1


def test_apl_transform_rejects_unknown_native_action_shape() -> None:
    fixture, _ = load_fixture_contract()
    policy = fixture["specs"]["shadow_priest"]["native_request"][
        "apl_transform_policy"
    ]
    with pytest.raises(WowsimsGenerationError, match="unknown_action_field"):
        transform_apl_rotation(
            {"priority_list": [{"action": {"invented_cooldown": {}}}]},
            policy,
            prepull_actions=[],
            action_variants={
                "cast_spell",
                "autocast_other_cooldowns",
                "cast_all_stat_buff_cooldowns",
                "activate_all_stat_buff_proc_auras",
                "item_swap",
                "activate_aura",
                "activate_aura_with_stacks",
                "trigger_icd",
                "cancel_aura",
            },
            condition_variants=_condition_variants(),
            equipped_item_ids=set(),
        )


def test_apl_transform_rejects_unlisted_item_action() -> None:
    fixture, _ = load_fixture_contract()
    policy = fixture["specs"]["shadow_priest"]["native_request"][
        "apl_transform_policy"
    ]
    with pytest.raises(WowsimsGenerationError, match="unlisted_item_id:99999"):
        transform_apl_rotation(
            {
                "priority_list": [
                    {"action": {"cast_spell": {"spell_id": {"item_id": 99999}}}}
                ]
            },
            policy,
            prepull_actions=[],
            action_variants={
                "cast_spell",
                "autocast_other_cooldowns",
                "cast_all_stat_buff_cooldowns",
                "activate_all_stat_buff_proc_auras",
                "item_swap",
                "activate_aura",
                "activate_aura_with_stacks",
                "trigger_icd",
                "cancel_aura",
            },
            condition_variants=_condition_variants(),
            equipped_item_ids=set(),
        )


def test_apl_transform_rejects_unlisted_state_mutation() -> None:
    fixture, _ = load_fixture_contract()
    policy = fixture["specs"]["shadow_priest"]["native_request"][
        "apl_transform_policy"
    ]
    with pytest.raises(WowsimsGenerationError, match="unlisted_state_mutation"):
        transform_apl_rotation(
            {
                "priority_list": [
                    {"action": {"activate_aura": {"aura_id": {"spell_id": 99999}}}}
                ]
            },
            policy,
            prepull_actions=[],
            action_variants={
                "cast_spell",
                "autocast_other_cooldowns",
                "cast_all_stat_buff_cooldowns",
                "activate_all_stat_buff_proc_auras",
                "item_swap",
                "activate_aura",
                "activate_aura_with_stacks",
                "trigger_icd",
                "cancel_aura",
            },
            condition_variants=_condition_variants(),
            equipped_item_ids=set(),
        )


def test_apl_transform_rewrites_only_fixture_absent_conditions_and_folds() -> None:
    fixture, _ = load_fixture_contract()
    policy = fixture["specs"]["shadow_priest"]["native_request"][
        "apl_transform_policy"
    ]
    variants = {
        "cast_spell",
        "multidot",
        "autocast_other_cooldowns",
        "cast_all_stat_buff_cooldowns",
        "activate_all_stat_buff_proc_auras",
        "item_swap",
        "activate_aura",
        "activate_aura_with_stacks",
        "trigger_icd",
        "cancel_aura",
    }
    rotation = {
        "priority_list": [
            {
                "action": {
                    "condition": {
                        "and": {
                            "vals": [
                                {
                                        "aura_is_active": {
                                            "aura_id": {"spell_id": 2825, "tag": -1}
                                    }
                                },
                                {"current_mana_percent": {}},
                            ]
                        }
                    },
                    "cast_spell": {"spell_id": {"spell_id": 100}},
                }
            },
            {
                "action": {
                    "condition": {
                        "not": {
                            "val": {
                                "aura_is_active": {
                                    "aura_id": {"spell_id": 2825, "tag": -1}
                                }
                            }
                        }
                    },
                    "cast_spell": {"spell_id": {"spell_id": 200}},
                }
            },
            {
                "action": {
                    "condition": {
                        "cmp": {
                            "op": "OpLe",
                            "lhs": {
                                    "aura_remaining_time": {
                                        "aura_id": {"spell_id": 2825, "tag": -1}
                                }
                            },
                            "rhs": {"const": {"val": "3s"}},
                        }
                    },
                    "cast_spell": {"spell_id": {"spell_id": 250}},
                }
            },
            {
                "action": {
                    "multidot": {
                        "spell_id": {"spell_id": 300},
                        "max_dots": 2,
                    }
                }
            },
            {
                "action": {
                    "cast_spell": {"spell_id": {"spell_id": 58984}}
                }
            },
        ]
    }
    transformed, observed = transform_apl_rotation(
        rotation,
        policy,
        prepull_actions=[],
        action_variants=variants,
        condition_variants=_condition_variants(),
        equipped_item_ids=set(),
    )
    assert len(transformed["priority_list"]) == 3
    assert "condition" not in transformed["priority_list"][0]["action"]
    assert "condition" not in transformed["priority_list"][1]["action"]
    assert transformed["priority_list"][2]["action"]["multidot"]["max_dots"] == 1
    assert observed["removed_false_row_count"] == 1
    assert observed["numeric_rewrite_count"] == 1
    assert observed["condition_rewrite_count"] >= 3
    assert {row.get("spell_id") for row in observed["removed_actions"]} >= {58984}


def test_apl_action_variants_are_read_from_pinned_proto_shape() -> None:
    source = """
message APLAction {
  oneof action {
    APLActionCastSpell cast_spell = 3;
    APLActionAutocastOtherCooldowns autocast_other_cooldowns = 7;
    APLActionCastAllStatBuffCooldowns cast_all_stat_buff_cooldowns = 23;
    APLActionActivateAllStatBuffProcAuras activate_all_stat_buff_proc_auras = 25;
    APLActionItemSwap item_swap = 17;
    APLActionActivateAura activate_aura = 13;
    APLActionActivateAuraWithStacks activate_aura_with_stacks = 24;
    APLActionTriggerICD trigger_icd = 11;
    APLActionCancelAura cancel_aura = 10;
  }
}
"""
    assert apl_action_variants_from_pinned_proto(source) == {
        "cast_spell",
        "autocast_other_cooldowns",
        "cast_all_stat_buff_cooldowns",
        "activate_all_stat_buff_proc_auras",
        "item_swap",
        "activate_aura",
        "activate_aura_with_stacks",
        "trigger_icd",
        "cancel_aura",
    }


def test_apl_condition_variants_are_read_from_pinned_proto_shape() -> None:
    source = """
message APLValue {
  oneof value {
    APLValueConst const = 1;
    APLValueAnd and = 2;
    APLValueOr or = 3;
    APLValueNot not = 4;
    APLValueCompare cmp = 5;
    APLValueMath math = 6;
    APLValueNumberTargets number_targets = 7;
    APLValueAuraIsActive aura_is_active = 8;
    APLValueAuraIsKnown aura_is_known = 9;
    APLValueAuraRemainingTime aura_remaining_time = 10;
    APLValueDotIsActive dot_is_active = 11;
    APLValueSpellTimeToReady spell_time_to_ready = 12;
  }
}
"""
    assert apl_condition_variants_from_pinned_proto(source) == {
        "const",
        "and",
        "or",
        "not",
        "cmp",
        "math",
        "number_targets",
        "aura_is_active",
        "aura_is_known",
        "aura_remaining_time",
        "dot_is_active",
        "spell_time_to_ready",
    }


def test_apl_transform_rejects_malformed_condition_oneof() -> None:
    fixture, _ = load_fixture_contract()
    policy = fixture["specs"]["shadow_priest"]["native_request"][
        "apl_transform_policy"
    ]
    with pytest.raises(WowsimsGenerationError, match="condition_oneof"):
        transform_apl_rotation(
            {
                "priority_list": [
                    {
                        "action": {
                            "condition": {
                                "aura_is_active": {
                                    "aura_id": {"spell_id": 2825}
                                },
                                "aura_is_known": {
                                    "aura_id": {"spell_id": 2825}
                                },
                            },
                            "cast_spell": {"spell_id": {"spell_id": 100}},
                        }
                    }
                ]
            },
            policy,
            prepull_actions=[],
            action_variants={
                "cast_spell",
                "autocast_other_cooldowns",
                "cast_all_stat_buff_cooldowns",
                "activate_all_stat_buff_proc_auras",
                "item_swap",
                "activate_aura",
                "activate_aura_with_stacks",
                "trigger_icd",
                "cancel_aura",
            },
            condition_variants=_condition_variants(),
            equipped_item_ids=set(),
        )


def test_apl_transform_rejects_unlisted_condition_payload_scope() -> None:
    fixture, _ = load_fixture_contract()
    policy = fixture["specs"]["shadow_priest"]["native_request"][
        "apl_transform_policy"
    ]
    with pytest.raises(WowsimsGenerationError, match="unlisted_condition_payload"):
        transform_apl_rotation(
            {
                "priority_list": [
                    {
                        "action": {
                            "condition": {
                                "aura_is_active": {
                                    "aura_id": {"spell_id": 2825}
                                }
                            },
                            "cast_spell": {"spell_id": {"spell_id": 100}},
                        }
                    }
                ]
            },
            policy,
            prepull_actions=[],
            action_variants={
                "cast_spell",
                "autocast_other_cooldowns",
                "cast_all_stat_buff_cooldowns",
                "activate_all_stat_buff_proc_auras",
                "item_swap",
                "activate_aura",
                "activate_aura_with_stacks",
                "trigger_icd",
                "cancel_aura",
            },
            condition_variants=_condition_variants(),
            equipped_item_ids=set(),
        )


def test_checked_in_catalog_validates_through_actual_cli() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.bot_ml.run_wowsims_exact_references",
            "validate-catalog",
        ],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    output = json.loads(completed.stdout)
    assert output["ok"] is True
    assert output["request_count"] == 16


def test_native_request_projection_is_derived_from_proto_bytes() -> None:
    request = native_request()
    fixture = fixture_contract()
    projection = project_native_request_conditions(
        json.loads(canonical_json_bytes(request)),
        target_spec="frost_death_knight",
        fixture_contract=fixture,
        fixture_sha256="f" * 64,
        slot_map=[0],
    )
    validate_native_request_projection(projection, fixture)
    assert projection["target"]["attack_power"] == 0
    assert projection["target"]["swing_speed_seconds"] == 0.0
    assert projection["player"]["item_swap_empty"] is True
    assert projection["player"]["gear_manifest"] == [
        {
            "slot": 0,
            "item_id": 78687,
            "enchant_id": 4208,
            "reforge_id": 161,
            "gem_item_ids": [68779, 71883],
        }
    ]


def test_native_request_conditions_must_match_request_and_fixture() -> None:
    manifest = load_manifest()
    row = request_by_spec(manifest, "frost_death_knight")
    fixture, fixture_sha256 = load_fixture_contract()
    contract = row["request"]
    contract_player = contract["player"]
    native_contract = contract["native_request"]
    request = native_request()
    player = request["raid"]["parties"][0]["players"][0]
    player["equipment"]["items"] = copy.deepcopy(
        contract_player["gear"]["wowsims_items"]
    )
    player["talents_string"] = contract_player["talents"]["talent_string"]
    glyph_ids = contract_player["glyphs"]["item_ids"]
    player["glyphs"] = {
        **{f"prime{i + 1}": value for i, value in enumerate(glyph_ids[:3])},
        **{f"major{i + 1}": value for i, value in enumerate(glyph_ids[3:6])},
        **{f"minor{i + 1}": value for i, value in enumerate(glyph_ids[6:9])},
    }
    del player["frost_death_knight"]
    player[native_contract["player_spec_key"]] = copy.deepcopy(
        native_contract["player_spec"]
    )
    player["consumables"] = copy.deepcopy(native_contract["consumables"])
    player["buffs"] = copy.deepcopy(native_contract["individual_buffs"])
    player["rotation"]["prepull_actions"] = copy.deepcopy(
        native_contract["rotation_prepull_actions"]
    )
    player["distance_from_target"] = contract["target_distance"]["simulator_yards"]
    request["raid"]["parties"][0]["buffs"] = copy.deepcopy(
        native_contract["party_buffs"]
    )
    request["raid"]["buffs"] = copy.deepcopy(native_contract["raid_buffs"])
    request["raid"]["debuffs"] = copy.deepcopy(
        native_contract["target_debuffs"]
    )
    projection = project_native_request_conditions(
        request,
        target_spec="frost_death_knight",
        fixture_contract=fixture,
        fixture_sha256=fixture_sha256,
        slot_map=load_slot_map(),
        apl_transform_observation={
            "policy_sha256": canonical_sha256(
                native_contract["apl_transform_policy"]
            )
        },
    )
    projection["talent_semantics"] = {
        "decoded_active_spell_ids": contract_player["talents"]["active_spell_ids"]
    }
    validate_native_request_projection(projection, fixture)
    validate_projection_against_request_contract(projection, row, fixture)

    request["raid"]["buffs"]["bloodlust"] = True
    changed = project_native_request_conditions(
        request,
        target_spec="frost_death_knight",
        fixture_contract=fixture,
        fixture_sha256=fixture_sha256,
        slot_map=load_slot_map(),
        apl_transform_observation=projection["apl_transform_observation"],
    )
    changed["talent_semantics"] = projection["talent_semantics"]
    with pytest.raises(
        WowsimsGenerationError,
        match="fixture_native_request:raid_buffs",
    ):
        validate_projection_against_request_contract(changed, row, fixture)


def test_native_request_rejects_inherited_attacking_target() -> None:
    request = native_request()
    request["encounter"]["targets"][0]["swing_speed"] = 2.5
    request["encounter"]["targets"][0]["min_base_damage"] = 210000
    projection = project_native_request_conditions(
        request,
        target_spec="frost_death_knight",
        fixture_contract=fixture_contract(),
        fixture_sha256="f" * 64,
        slot_map=[0],
    )
    with pytest.raises(WowsimsGenerationError, match="request_passive_target_swing"):
        validate_native_request_projection(projection, fixture_contract())


def test_native_request_rejects_missing_explicit_empty_item_swap() -> None:
    request = native_request()
    del request["raid"]["parties"][0]["players"][0]["item_swap"]
    projection = project_native_request_conditions(
        request,
        target_spec="frost_death_knight",
        fixture_contract=fixture_contract(),
        fixture_sha256="f" * 64,
        slot_map=[0],
    )
    with pytest.raises(WowsimsGenerationError, match="request_item_swap"):
        validate_native_request_projection(projection, fixture_contract())


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("raid", "parties", 0, "players", 0, "bonus_stats", "stats"), [1]),
        (("raid", "parties", 0, "players", 0, "cooldowns", "cooldowns"), [{}]),
        (("raid", "parties", 0, "players", 0, "reaction_time_ms"), 99),
        (("raid", "parties", 0, "players", 0, "channel_clip_delay_ms"), 99),
        (("raid", "parties", 0, "players", 0, "in_front_of_target"), True),
        (("raid", "num_active_parties"), 2),
        (("encounter", "duration"), 299),
        (("sim_options", "iterations"), 1999),
    ],
)
def test_exact_native_request_rematerialization_rejects_unprojected_mutations(
    path: tuple[object, ...], value: object
) -> None:
    expected = native_request()
    actual = copy.deepcopy(expected)
    cursor: object = actual
    for key in path[:-1]:
        cursor = cursor[key]  # type: ignore[index]
    cursor[path[-1]] = value  # type: ignore[index]
    with pytest.raises(WowsimsGenerationError, match="not_exact_rematerialization"):
        validate_exact_native_request_bytes(actual, expected)


def test_native_result_dps_is_parsed_and_cross_checked() -> None:
    parsed = parse_native_result(native_result())
    assert parsed["dps"] == 52_000.25
    forged = native_result()
    forged["raidMetrics"]["parties"][0]["players"][0]["dps"]["avg"] = 1
    with pytest.raises(WowsimsGenerationError, match="dps_disagreement"):
        parse_native_result(forged)


def test_native_result_rejects_temporal_external_activity() -> None:
    result = native_result()
    result["raidMetrics"]["parties"][0]["players"][0]["actions"] = [
        {"id": {"spellId": 2825}, "casts": {"avg": 1}}
    ]
    with pytest.raises(WowsimsGenerationError, match="temporal_external_activity"):
        parse_native_result(result)


def test_native_result_allows_registered_zero_activity_temporal_external_metrics() -> None:
    result = native_result()
    player = result["raidMetrics"]["parties"][0]["players"][0]
    player["actions"] = [
        {
            "id": {"spellId": 2825},
            "targets": [{"casts": 0, "hits": 0, "damage": 0, "castTimeMs": 0}],
        }
    ]
    player["auras"] = [
        {"id": {"spellId": 2825}, "uptimeSecondsAvg": 0, "procsAvg": 0}
    ]
    parsed = parse_native_result(result)
    assert parsed["temporal_external_spell_ids_observed"] == []


def test_native_result_rejects_temporal_external_aura_uptime() -> None:
    result = native_result()
    result["raidMetrics"]["parties"][0]["players"][0]["auras"] = [
        {"id": {"spellId": 10060}, "uptimeSecondsAvg": 15, "procsAvg": 1}
    ]
    with pytest.raises(WowsimsGenerationError, match="temporal_external_activity"):
        parse_native_result(result)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("iterationsDone", 1999, "native_result:iterations"),
        ("error", {"message": "failed"}, "native_result:simulator_error"),
        ("avgIterationDuration", 299.5, "native_result:duration"),
    ],
)
def test_native_result_fails_closed_on_incomplete_execution(
    field: str, value: object, reason: str
) -> None:
    result = native_result()
    result[field] = value
    with pytest.raises(WowsimsGenerationError, match=reason):
        parse_native_result(result)


def test_compute_stats_requires_all_surviving_spell_actions_to_resolve() -> None:
    rotation = {
        "priority_list": [
            {"action": {"cast_spell": {"spell_id": {"spell_id": 100}}}}
        ]
    }
    observed = parse_compute_stats_validation(
        compute_stats_result(), rotation=rotation
    )
    assert observed["required_spell_actions"] == [{"spell_id": 100, "tag": 0}]
    assert observed["warning_or_error_count"] == 0

    missing = compute_stats_result()
    missing["raidStats"]["parties"][0]["players"][0]["metadata"]["spells"] = []
    with pytest.raises(WowsimsGenerationError, match="missing_spells"):
        parse_compute_stats_validation(missing, rotation=rotation)

    uncastable = compute_stats_result()
    uncastable["raidStats"]["parties"][0]["players"][0]["metadata"]["spells"][0][
        "isCastable"
    ] = False
    with pytest.raises(WowsimsGenerationError, match="uncastable_spells"):
        parse_compute_stats_validation(uncastable, rotation=rotation)


def test_compute_stats_rejects_any_apl_warning() -> None:
    result = compute_stats_result(
        validation={
            "logLevel": "Warning",
            "validation": "No aura found for unavailable item",
        }
    )
    with pytest.raises(WowsimsGenerationError, match="apl_validation"):
        parse_compute_stats_validation(result, rotation={"priority_list": []})


def test_dvc_pointer_must_bind_exact_bundle_output() -> None:
    pointer = b"outs:\n- md5: 0123456789abcdef0123456789abcdef.dir\n  size: 42\n  nfiles: 3\n  path: exact-reference-bundle\n"
    observed = parse_dvc_pointer(
        pointer,
        pointer_relative_path="experiments/exact-reference-bundle.dvc",
        expected_bundle_root="experiments/exact-reference-bundle",
    )
    assert observed["sha256"] == hashlib.sha256(pointer).hexdigest()
    with pytest.raises(WowsimsGenerationError, match="bundle_root"):
        parse_dvc_pointer(
            pointer,
            pointer_relative_path="experiments/exact-reference-bundle.dvc",
            expected_bundle_root="experiments/unrelated-output",
        )


def test_dvc_bundle_pre_pull_rejects_force_tracked_out(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("reference_bundle/\n", encoding="utf-8")
    observation = validate_dvc_bundle_pre_pull(
        tmp_path, bundle_relative=Path("reference_bundle")
    )
    assert observation["absent"] is True

    tracked = tmp_path / "reference_bundle" / "sentinel.json"
    tracked.parent.mkdir()
    tracked.write_text("{}", encoding="utf-8")
    subprocess.run(
        ["git", "add", "-f", "reference_bundle/sentinel.json"],
        cwd=tmp_path,
        check=True,
    )
    tracked.unlink()
    tracked.parent.rmdir()
    with pytest.raises(WowsimsGenerationError, match="absent_untracked_ignored"):
        validate_dvc_bundle_pre_pull(
            tmp_path, bundle_relative=Path("reference_bundle")
        )


def test_fresh_build_log_identity_rejects_relabelled_receipt() -> None:
    identity = {
        "schema": exact_runner.BUILD_RECEIPT_SCHEMA,
        "provider_revision": "a" * 40,
        "binary_sha256": "b" * 64,
    }
    receipt = {
        **identity,
        "receipt_sha256": exact_runner.canonical_sha256(identity),
    }
    receipt_bytes = canonical_json_bytes(receipt)
    build_log = {
        **receipt,
        "artifact": {
            "path": "build_receipts/receipt.json",
            "sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "byte_count": len(receipt_bytes),
        },
    }
    _, observed = parse_fresh_build_log_identity(canonical_json_bytes(build_log))
    assert observed["binary_sha256"] == "b" * 64

    forged = copy.deepcopy(build_log)
    forged["binary_sha256"] = "c" * 64
    with pytest.raises(WowsimsGenerationError, match="fresh_rebuild_log:identity"):
        parse_fresh_build_log_identity(canonical_json_bytes(forged))


def test_unpublished_generation_requires_final_fixture_lifecycle() -> None:
    with pytest.raises(WowsimsGenerationError, match="generation_fixture_not_final"):
        exact_runner._require_fixture_final_for_generation(
            {"authority": {"lifecycle_status": "requires_generation"}}
        )
    exact_runner._require_fixture_final_for_generation(
        {
            "authority": {
                "lifecycle_status": "final_for_offline_reference_generation"
            }
        }
    )


def test_dvc_reconstruction_rejects_receipt_cycle_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    revision = "a" * 40
    repository = tmp_path / "repository"
    bundle = repository / "experiments" / "exact-reference-bundle"
    bundle.mkdir(parents=True)
    pointer = b"outs:\n- md5: 0123456789abcdef0123456789abcdef.dir\n  size: 42\n  nfiles: 3\n  path: exact-reference-bundle\n"

    def fake_git_output(_root: Path, arguments: list[str]) -> str:
        if arguments[:2] == ["rev-parse", "HEAD"]:
            return revision
        if arguments[0] == "status":
            return ""
        if arguments[:2] == ["remote", "get-url"]:
            return "https://example.invalid/evidence.git"
        raise AssertionError(arguments)

    monkeypatch.setattr(exact_runner, "_git_output", fake_git_output)
    monkeypatch.setattr(exact_runner, "_checked_source_bytes", lambda *args, **kwargs: pointer)
    with pytest.raises(WowsimsGenerationError, match="receipt_cycle"):
        exact_runner.reconstruct_generation_with_dvc(
            repository_url="https://example.invalid/evidence.git",
            repository_revision=revision,
            dvc_target="experiments/exact-reference-bundle.dvc",
            bundle_root="experiments/exact-reference-bundle",
            generation_receipt_relative_paths=[
                f"experiments/exact-reference-bundle/generation_receipts/{index}.json"
                for index in range(16)
            ],
            original_repository_root=repository,
            output_root=bundle / "control-plane-receipts",
            dvc_binary=tmp_path / "dvc",
            go_binary=tmp_path / "go",
            protoc_binary=tmp_path / "protoc",
            protoc_gen_go_binary=tmp_path / "protoc-gen-go",
        )


def test_dvc_cache_read_uses_supported_config_query_syntax() -> None:
    source = inspect.getsource(exact_runner.reconstruct_generation_with_dvc)
    assert '[str(dvc_binary.resolve()), "config", "--local", "cache.dir"]' in source
    assert '"--get", "cache.dir"' not in source


@pytest.mark.parametrize(
    "output",
    [
        b"",
        b"Data and pipelines are up to date.\n",
        b"Cache and remote 'object' are in sync.\n",
    ],
)
def test_dvc_cloud_status_accepts_only_known_clean_output(output: bytes) -> None:
    assert exact_runner.classify_clean_dvc_cloud_status(output) == (
        "clean_no_remote_divergence"
    )


def test_dvc_cloud_status_rejects_remote_divergence() -> None:
    with pytest.raises(WowsimsGenerationError, match="cloud_status_not_clean"):
        exact_runner.classify_clean_dvc_cloud_status(
            b"new: artifacts/all_spec_program/wowsims_exact_reference_bundle_v1\n"
        )


def test_dvc_receipt_rejects_publication_domain_relabel(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    receipt_path = repository / "control-plane" / "reconstruction.json"
    receipt_path.parent.mkdir(parents=True)
    identity = {
        "schema": exact_runner.DVC_RECONSTRUCTION_SCHEMA,
        "status": "published_and_freshly_reconstructed",
        "fresh_recursive_reconstruction_verified": True,
        "repository_url": "https://example.invalid/relabelled.git",
        "repository_revision": "a" * 40,
        "dvc_target": "experiments/exact-reference-bundle.dvc",
        "bundle_root": "experiments/exact-reference-bundle",
        "generation_receipts": [],
    }
    receipt = {
        **identity,
        "receipt_sha256": exact_runner.canonical_sha256(identity),
    }
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    with pytest.raises(WowsimsGenerationError, match="publication_domain"):
        exact_runner.validate_dvc_reconstruction_receipt(
            receipt_path,
            expected_generation_receipt_paths=[
                repository / "experiments" / "exact-reference-bundle" / f"{index}.json"
                for index in range(16)
            ],
            expected_repository_root=repository,
            expected_repository_url="https://example.invalid/admitted.git",
            expected_repository_revision="a" * 40,
            expected_dvc_pointer_path="experiments/exact-reference-bundle.dvc",
            expected_bundle_root="experiments/exact-reference-bundle",
        )
