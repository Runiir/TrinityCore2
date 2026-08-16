from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from tools.bot_ml.batch_evidence_lifecycle import canonical_sha256
from tools.bot_ml.build_wowsims_reference_requests import build_manifest
from tools.bot_ml.phase8_reference_conditions import (
    COMPARISON_MANIFEST_SCHEMA,
    EXTERNAL_BLEED_AURA_IDS,
    EXPECTED_REFERENCE_CONDITIONS,
    FLASK_ITEM_BY_AURA,
    FOOD_ITEMS_BY_AURA,
    NON_PALADIN_MIGHT_AURA_ID,
    PRIMARY_STAT_AURA_IDS,
    RAID_REQUIRED_PLAYER_AURA_IDS,
    REPLENISHMENT_AURA_ID,
    REQUIRED_REQUIREMENT_CLASSES,
    REQUIRED_SOURCE_SETUP_KEYS,
    REQUIRED_TARGET_DEBUFF_AURA_IDS,
    SUNDER_ARMOR_AURA_ID,
    classify_simulator_option_leaves,
    compose_prepull_setup_projection,
    derive_reference_condition_compatibility,
    execute_schedule_projection,
    external_windows_projection,
    fixture_target_projections,
    glyph_translation_authority,
    initial_resources_projection,
    item_swap_projection,
    load_fixture_contract_binding,
    observed_gear_manifest_sha256,
    preflight_reference_condition_compatibility,
    prepull_setup_projection,
    pet_setup_projection,
    reference_condition_projections,
    required_buff_auras,
)
from tools.bot_ml.role_calibration_harness import evaluate_calibration, load_policy


def _execute_schedule() -> dict:
    windows = []
    for phase, start, end, health_pct, lower, lower_inclusive, upper, upper_inclusive in (
        ("above_90", 0, 30_000, 95, 90, False, 100, True),
        ("between_35_90", 30_000, 195_000, 50, 35, False, 90, True),
        ("between_25_35", 195_000, 225_000, 30, 25, False, 35, True),
        ("between_20_25", 225_000, 240_000, 22, 20, False, 25, True),
        ("below_20", 240_000, 300_000, 19, 0, True, 20, False),
    ):
        health = health_pct * 10_000_000
        windows.append(
            {
                "phase": phase,
                "start_ms": start,
                "end_ms": end,
                "configured_target_health_pct": health_pct,
                "health_pct_lower_bound": lower,
                "lower_bound_inclusive": lower_inclusive,
                "health_pct_upper_bound": upper,
                "upper_bound_inclusive": upper_inclusive,
                "observation": {
                    "sample_count": 10,
                    "first_elapsed_ms": start,
                    "last_elapsed_ms": end - 1,
                    "minimum_observed_health": health,
                    "maximum_observed_health": health,
                    "minimum_observed_max_health": 1_000_000_000,
                    "maximum_observed_max_health": 1_000_000_000,
                    "damage_event_sample_count": 10,
                    "first_damage_event_elapsed_ms": start,
                    "last_damage_event_elapsed_ms": end - 1,
                    "minimum_pre_damage_health": health,
                    "maximum_pre_damage_health": health,
                    "minimum_projected_post_damage_health": health - 1_000,
                    "maximum_projected_post_damage_health": health - 1_000,
                    "minimum_damage_event_max_health": 1_000_000_000,
                    "maximum_damage_event_max_health": 1_000_000_000,
                    "maximum_damage_event": 1_000,
                },
            }
        )
    return {
        "schema": "wowsims_cata_single_target_health_schedule_v1",
        "source_authority": (
            "pinned_wowsims_cata_core_test_utils_make_single_target_encounter"
        ),
        "source_duration_ms": 300_000,
        "source_duration_variation_ms": 0,
        "source_execute_proportions": {
            "90": 0.9,
            "35": 0.35,
            "25": 0.25,
            "20": 0.2,
        },
        "interval_semantics": "start_inclusive_end_exclusive",
        "fixture_only": True,
        "non_certifying": True,
        "windows": windows,
    }


def _compatible_fixture() -> tuple[dict, dict, dict, dict, dict]:
    target_spec = "arms_warrior"
    items = [
        {
            "slot": 0,
            "item_id": 1,
            "enchant_id": 2,
            "reforge_id": 3,
            "random_property_type": 0,
            "random_property_id": 0,
            "gem_item_ids": [4, 0, 0],
        }
    ]
    persistent_setup = {
        "form_presence": "battle_stance",
        "ready": True,
        "pet_present": False,
        "pet_guid": 0,
        "pet_entry": 0,
        "pet_observed_owner_guid": 10,
        "pet_observation_window_started_at_ms": 1_000,
        "pet_observation_window_ended_at_ms": 301_000,
        "pet_first_observation_at_ms": 1_000,
        "pet_last_observation_at_ms": 301_000,
        "pet_first_observed_guid": 0,
        "pet_last_observed_guid": 0,
        "pet_guid_mismatch_sample_count": 0,
        "pet_identity_mismatch_sample_count": 0,
        "pet_maximum_observation_gap_ms": 500,
        "pet_ready_ticks": 601,
        "pet_observation_ticks": 601,
        "pet_uptime_ratio": 1.0,
    }
    target = {
        "guid": 10,
        "race_id": 1,
        "active_talent_spell_ids": [100, 200],
        "glyph_property_ids": [521],
        "glyph_aura_spell_ids": [58647],
        "gear_profile_observation": {"items": items},
        "persistent_setup": persistent_setup,
        "simulator_options_observation": {"starting_distance_yards": 5.0},
        "initial_resources": {
            "power_type": "rage",
            "current": 0,
            "maximum": 1000,
        },
        "item_swap_observation": {
            "start_manifest_sha256": "c" * 64,
            "end_manifest_sha256": "c" * 64,
            "changed": False,
        },
        "pre_score_state": {
            "schema": "phase8_pre_score_state_observation_v1",
            "observed_at_ms": 900,
            "heroism_ready": False,
            "temporal_external_auras_absent": True,
        },
        "external_window_observation": _external_window_observation(
            shadow=False
        )["external_window_observation"],
    }
    auras = {aura: True for aura in required_buff_auras(target_spec)}
    setup = {
        "enabled": True,
        "buffs_ready": False,  # Aggregate self-report is not authoritative.
        "replenishment_required": False,
        "buff_auras": auras,
        "flask_aura_id": 79472,
        "target_debuffs_ready": True,
        "target_debuff_auras": {"critical_mass": True},
        "heroism_window_observed": True,
        "heroism_windows_ms": [[0, 40_000]],
    }
    normalization = {
        "flask": True,
        "potions": True,
        "prepot_item_id": 58146,
        "combat_potion_item_id": 58146,
        "consumables": True,
        "food_buff_spell_id": 87545,
        "tinker_windows_ms": [],
        "racial_windows_ms": [],
        "target_debuffs": True,
        "reference_conditions": True,
        "execute_threshold_windows": _execute_schedule(),
    }
    fixture_target = {
        "expected": {"level": 88, "armor": 11977, "creature_type": "mechanical"},
        "observed_before_scoring": {
            "level": 88,
            "armor": 11977,
            "creature_type": "mechanical",
            "distance_yards": 5.0,
        },
    }
    calibration = {
        "scored_seconds": 300.0,
        "scored_started_at_ms": 1_000,
        "scored_ended_at_ms": 301_000,
        "normalization": normalization,
        "fixture_target": fixture_target,
    }
    gear_sha256 = observed_gear_manifest_sha256(target)
    runtime = {
        "gear_source_sha256": "a" * 64,
        "reference_gear_manifest_sha256": gear_sha256,
        "observed_gear_manifest_sha256": gear_sha256,
        "gear_transform_schema": "wowsims_cata_equipment_manifest_v1",
        "gear_transform_authority": "pinned_wowsims_preset_exact",
        "reference_result_key": "TestArms-Average-Default",
        "reference_value": 50_000.0,
        "source_contract_sha256": "b" * 64,
        "request_sha256": "d" * 64,
        "fixture_contract_sha256": "e" * 64,
        "fixture_contract_binding_valid": True,
        "result_status": "generated_verified",
        "reference_request_binding_valid": True,
        "reference_request_catalog_sha256": "f" * 64,
    }
    execute_projection, execute_valid = execute_schedule_projection(
        normalization["execute_threshold_windows"]
    )
    assert execute_valid is True
    runtime_paths = {
        "gear_manifest": ("runtime.reference_gear_manifest_sha256", gear_sha256),
        "item_swap": (
            "target.item_swap_observation",
            target["item_swap_observation"],
        ),
        "race": ("target.race_id", 1),
        "talents": ("target.active_talent_spell_ids", [100, 200]),
        "glyphs": (
            "runtime.glyph_identity",
            {"property_ids": [521], "aura_spell_ids": [58647]},
        ),
        "flask": ("reference_setup.flask_aura_id", 79472),
        "food": ("normalization.food_buff_spell_id", 87545),
        "prepot": ("normalization.prepot_item_id", 58146),
        "combat_potion": ("normalization.combat_potion_item_id", 58146),
        "tinker": ("normalization.tinker_windows_ms", []),
        "racial": ("normalization.racial_windows_ms", []),
        "raid_buffs": ("reference_setup.buff_auras", auras),
        "target_debuffs": (
            "reference_setup.target_debuff_auras",
            {"critical_mass": True},
        ),
        "heroism": ("reference_setup.heroism_windows_ms", [[0, 40_000]]),
        "duration": ("calibration.scored_seconds", 300.0),
        "execute": ("runtime.execute_schedule_projection", execute_projection),
        "fixture_target": ("calibration.fixture_target", fixture_target),
        "target_distance": (
            "calibration.fixture_target.observed_before_scoring",
            fixture_target["observed_before_scoring"],
        ),
        "initial_resources": ("target.initial_resources", target["initial_resources"]),
        "form_presence": (
            "runtime.prepull_setup_projection.form_presence",
            {"required_aura_spell_ids": []},
        ),
        "pet_setup": (
            "runtime.pet_setup_projection",
            {
                "schema": "phase8_absent_pet_at_scoring_start_v1",
                "required": False,
                "runtime_projection_complete": True,
                "present": False,
            },
        ),
        "prepull_setup": (
            "runtime.prepull_setup_projection",
            {
                "form_presence": {"required_aura_spell_ids": []},
            },
        ),
        "simulator_options": (
            "target.simulator_options_observation",
            target["simulator_options_observation"],
        ),
    }
    source_setup = {key: f"pinned:{key}" for key in REQUIRED_SOURCE_SETUP_KEYS}
    manifest = {
        "schema": COMPARISON_MANIFEST_SCHEMA,
        "target_spec": target_spec,
        "reference_result_key": runtime["reference_result_key"],
        "reference_dps": runtime["reference_value"],
        "source_contract_sha256": runtime["source_contract_sha256"],
        "request_sha256": runtime["request_sha256"],
        "fixture_contract_sha256": runtime["fixture_contract_sha256"],
        "result_status": runtime["result_status"],
        "source_setup": source_setup,
        "source_setup_sha256": canonical_sha256(source_setup),
        "requirements": [
            {
                "id": requirement_id,
                "condition_class": REQUIRED_REQUIREMENT_CLASSES[requirement_id],
                "path": runtime_paths[requirement_id][0],
                "planned_path": f"target.planned.{requirement_id}",
                "equals": runtime_paths[requirement_id][1],
                "planned_equals": (
                    [43543]
                    if requirement_id == "glyphs"
                    else runtime_paths[requirement_id][1]
                ),
                "static_verifiability": "target_capability",
                **(
                    {
                        "translation_authority": {
                            "schema": glyph_translation_authority()["schema"],
                            "source_file_sha256": glyph_translation_authority()[
                                "source_file_sha256"
                            ],
                        }
                    }
                    if requirement_id == "glyphs"
                    else {}
                ),
            }
            for requirement_id in REQUIRED_REQUIREMENT_CLASSES
        ],
    }
    target["planned"] = {
        requirement_id: (
            [43543]
            if requirement_id == "glyphs"
            else runtime_paths[requirement_id][1]
        )
        for requirement_id in REQUIRED_REQUIREMENT_CLASSES
    }
    return calibration, target, setup, runtime, manifest


def test_nonmana_reference_compatibility_does_not_require_replenishment() -> None:
    calibration, target, setup, runtime, manifest = _compatible_fixture()
    compatibility = derive_reference_condition_compatibility(
        target_spec="arms_warrior",
        reference_setup=setup,
        reference_conditions=EXPECTED_REFERENCE_CONDITIONS,
        calibration=calibration,
        runtime_normalization=calibration["normalization"],
        target_observation=target,
        runtime_facts=runtime,
        expected_manifest=manifest,
    )

    assert "57669" not in compatibility["required_buff_auras"]
    assert compatibility["requires_replenishment"] is False
    assert compatibility["checks"]["replenishment_requirement_matches_spec"] is True
    # The synthetic fixture intentionally lacks the new exact native
    # consume/target/resource observations, so the scientific gate stays shut.
    assert compatibility["conditions_compatible"] is False


def test_mana_spec_missing_replenishment_is_incompatible() -> None:
    calibration, target, setup, runtime, manifest = _compatible_fixture()
    setup = copy.deepcopy(setup)
    setup["replenishment_required"] = True
    setup["buff_auras"]["79470"] = True
    manifest = copy.deepcopy(manifest)
    manifest["target_spec"] = "fire_mage"

    compatibility = derive_reference_condition_compatibility(
        target_spec="fire_mage",
        reference_setup=setup,
        reference_conditions=EXPECTED_REFERENCE_CONDITIONS,
        calibration=calibration,
        runtime_normalization=calibration["normalization"],
        target_observation=target,
        runtime_facts=runtime,
        expected_manifest=manifest,
    )

    assert "57669" in compatibility["required_buff_auras"]
    assert compatibility["conditions_compatible"] is False
    assert "required_buff_aura_57669" in compatibility["reasons"]


def test_missing_or_spoofed_manifest_cannot_claim_compatibility() -> None:
    calibration, target, setup, runtime, _manifest = _compatible_fixture()
    setup = {**setup, "conditions_compatible": True, "reasons": []}

    compatibility = derive_reference_condition_compatibility(
        target_spec="arms_warrior",
        reference_setup=setup,
        reference_conditions=EXPECTED_REFERENCE_CONDITIONS,
        calibration=calibration,
        runtime_normalization=calibration["normalization"],
        target_observation=target,
        runtime_facts=runtime,
        expected_manifest=None,
    )

    assert compatibility["conditions_compatible"] is False
    assert "comparison_manifest_present" in compatibility["reasons"]


def test_inconsistent_execute_observations_fail_closed() -> None:
    calibration, target, setup, runtime, manifest = _compatible_fixture()
    calibration = copy.deepcopy(calibration)
    calibration["normalization"]["execute_threshold_windows"]["windows"][4][
        "observation"
    ]["maximum_observed_health"] = 180_000_000

    compatibility = derive_reference_condition_compatibility(
        target_spec="arms_warrior",
        reference_setup=setup,
        reference_conditions=EXPECTED_REFERENCE_CONDITIONS,
        calibration=calibration,
        runtime_normalization=calibration["normalization"],
        target_observation=target,
        runtime_facts=runtime,
        expected_manifest=manifest,
    )

    assert compatibility["conditions_compatible"] is False
    assert "runtime_execute_threshold_windows_valid" in compatibility["reasons"]


def test_execute_damage_event_lower_gate_leak_fails_closed() -> None:
    calibration, target, setup, runtime, manifest = _compatible_fixture()
    calibration = copy.deepcopy(calibration)
    calibration["normalization"]["execute_threshold_windows"]["windows"][1][
        "observation"
    ]["minimum_projected_post_damage_health"] = 350_000_000

    compatibility = derive_reference_condition_compatibility(
        target_spec="arms_warrior",
        reference_setup=setup,
        reference_conditions=EXPECTED_REFERENCE_CONDITIONS,
        calibration=calibration,
        runtime_normalization=calibration["normalization"],
        target_observation=target,
        runtime_facts=runtime,
        expected_manifest=manifest,
    )

    assert compatibility["conditions_compatible"] is False
    assert "runtime_execute_threshold_windows_valid" in compatibility["reasons"]


def test_execute_damage_event_upper_gate_leak_fails_closed() -> None:
    calibration, target, setup, runtime, manifest = _compatible_fixture()
    calibration = copy.deepcopy(calibration)
    observation = calibration["normalization"]["execute_threshold_windows"][
        "windows"
    ][1]["observation"]
    observation["minimum_pre_damage_health"] = 950_000_000
    observation["maximum_pre_damage_health"] = 950_000_000
    observation["minimum_projected_post_damage_health"] = 949_999_000
    observation["maximum_projected_post_damage_health"] = 949_999_000

    compatibility = derive_reference_condition_compatibility(
        target_spec="arms_warrior",
        reference_setup=setup,
        reference_conditions=EXPECTED_REFERENCE_CONDITIONS,
        calibration=calibration,
        runtime_normalization=calibration["normalization"],
        target_observation=target,
        runtime_facts=runtime,
        expected_manifest=manifest,
    )

    assert compatibility["conditions_compatible"] is False
    assert "runtime_execute_threshold_windows_valid" in compatibility["reasons"]


def test_unverified_or_spoofed_source_result_fails_closed() -> None:
    calibration, target, setup, runtime, manifest = _compatible_fixture()
    manifest = copy.deepcopy(manifest)
    manifest["result_status"] = "requires_generation"
    runtime = {**runtime, "result_status": "requires_generation"}

    compatibility = derive_reference_condition_compatibility(
        target_spec="arms_warrior",
        reference_setup=setup,
        reference_conditions=EXPECTED_REFERENCE_CONDITIONS,
        calibration=calibration,
        runtime_normalization=calibration["normalization"],
        target_observation=target,
        runtime_facts=runtime,
        expected_manifest=manifest,
    )

    assert compatibility["conditions_compatible"] is False
    assert "reference_result_status_acceptable" in compatibility["reasons"]


def test_runtime_glyph_identity_cannot_spoof_catalog_item_ids() -> None:
    calibration, target, setup, runtime, manifest = _compatible_fixture()
    target = copy.deepcopy(target)
    target["glyph_property_ids"] = [43543]  # Item ID, not GlyphProperties ID.

    compatibility = derive_reference_condition_compatibility(
        target_spec="arms_warrior",
        reference_setup=setup,
        reference_conditions=EXPECTED_REFERENCE_CONDITIONS,
        calibration=calibration,
        runtime_normalization=calibration["normalization"],
        target_observation=target,
        runtime_facts=runtime,
        expected_manifest=manifest,
    )

    assert compatibility["conditions_compatible"] is False
    assert "manifest_requirement:glyphs" in compatibility["reasons"]


def test_tampered_glyph_translation_authority_fails_closed() -> None:
    calibration, target, setup, runtime, manifest = _compatible_fixture()
    manifest = copy.deepcopy(manifest)
    glyph_requirement = next(
        row for row in manifest["requirements"] if row["id"] == "glyphs"
    )
    glyph_requirement["translation_authority"]["source_file_sha256"][
        "GlyphProperties.dbc"
    ] = "0" * 64

    compatibility = derive_reference_condition_compatibility(
        target_spec="arms_warrior",
        reference_setup=setup,
        reference_conditions=EXPECTED_REFERENCE_CONDITIONS,
        calibration=calibration,
        runtime_normalization=calibration["normalization"],
        target_observation=target,
        runtime_facts=runtime,
        expected_manifest=manifest,
    )

    assert compatibility["conditions_compatible"] is False
    assert (
        "glyph_item_property_aura_translation_pinned"
        in compatibility["reasons"]
    )


def test_frost_presence_requires_native_receipt_before_scoring() -> None:
    setup = {
        "ready": True,
        "required_presence_spell_id": 48265,
        "required_presence_aura_id": 48265,
        "presence_spell_known": True,
        "presence_aura_active": True,
        "presence_native_cast_submitted": True,
        "presence_native_cast_observed": True,
        "presence_native_cast_submitted_at_ms": 100,
        "presence_native_cast_observed_at_ms": 200,
        "poison_setup_required": False,
    }

    projection, valid = prepull_setup_projection(
        {"persistent_setup": setup}, scored_started_at_ms=300
    )
    assert valid is True
    assert projection["form_presence"] == {
        "required_aura_spell_ids": [48265]
    }

    setup["presence_native_cast_observed_at_ms"] = 301
    _projection, valid = prepull_setup_projection(
        {"persistent_setup": setup}, scored_started_at_ms=300
    )
    assert valid is False


def test_rogue_poison_projection_rejects_weapon_guid_swap() -> None:
    def poison(
        hand: str, item_id: int, spell_id: int, enchant_id: int, weapon_guid: int
    ) -> dict:
        return {
            "equipment_slot": 15 if hand == "mainhand" else 16,
            "required_item_entry": item_id,
            "required_spell_id": spell_id,
            "required_enchant_id": enchant_id,
            "item_available": True,
            "spell_available": True,
            "native_use_submitted": True,
            "native_use_finished": True,
            "enchant_observed": True,
            "native_use_submitted_at_ms": 100,
            "native_use_finished_at_ms": 150,
            "enchant_observed_at_ms": 200,
            "submitted_item_guid": item_id + 1_000,
            "submitted_weapon_guid": weapon_guid,
            "native_use_finished_item_guid": item_id + 1_000,
            "native_use_finished_weapon_guid": weapon_guid,
            "observed_weapon_guid": weapon_guid,
            "observed_weapon_item_entry": weapon_guid + 10,
            "observed_enchant_id": enchant_id,
            "observed_enchant_duration_ms": 3_600_000,
        }

    setup = {
        "ready": True,
        "poison_setup_required": True,
        "required_presence_spell_id": 0,
        "poisons": {
            "mainhand": poison("mainhand", 43233, 2823, 7, 10),
            "offhand": poison("offhand", 43231, 8679, 323, 20),
        },
    }
    target = {
        "persistent_setup": setup,
        "gear_profile_observation": {
            "items": [
                {"slot": 15, "item_id": 20},
                {"slot": 16, "item_id": 30},
            ]
        },
    }
    projection, valid = prepull_setup_projection(target, scored_started_at_ms=300)
    assert valid is True
    assert projection["weapon_imbues"][0] == {
        "slot": "mainhand",
        "item_id": 43233,
        "use_spell_id": 2823,
        "temp_enchant_id": 7,
    }

    setup["poisons"]["offhand"]["observed_weapon_guid"] = 21
    _projection, valid = prepull_setup_projection(
        target, scored_started_at_ms=300
    )
    assert valid is False

    setup["poisons"]["offhand"]["observed_weapon_guid"] = 20
    setup["poisons"]["offhand"]["native_use_finished_item_guid"] = 999
    _projection, valid = prepull_setup_projection(
        target, scored_started_at_ms=300
    )
    assert valid is False

    setup["poisons"]["offhand"]["native_use_finished_item_guid"] = 44_231
    setup["poisons"]["offhand"]["observed_enchant_duration_ms"] = 899_999
    _projection, valid = prepull_setup_projection(
        target, scored_started_at_ms=300
    )
    assert valid is False


def test_warlock_pet_projection_recomputes_spellbook_and_uptime() -> None:
    spellbook = [{"spell_id": 54049, "active": 1, "type": 0}]
    spellbook_hash = canonical_sha256(spellbook)  # Deliberately wrong format.
    setup = {
        "ready": True,
        "required_pet_spell_id": 691,
        "required_pet_entry": 417,
        "required_pet_family_id": 15,
        "required_pet_type": 0,
        "required_pet_power_type": 0,
        "pet_spell_known": True,
        "pet_native_cast_submitted": True,
        "pet_native_cast_finished": True,
        "pet_native_cast_observed": True,
        "pet_native_cast_submitted_at_ms": 100,
        "pet_native_cast_finished_at_ms": 150,
        "pet_native_cast_observed_at_ms": 200,
        "pet_entry": 417,
        "pet_family_id": 15,
        "pet_created_by_spell_id": 691,
        "pet_present": True,
        "pet_in_world": True,
        "pet_alive": True,
        "pet_owned": True,
        "pet_permanent": True,
        "pet_type": 0,
        "pet_health": 10,
        "pet_max_health": 10,
        "pet_power_type": 0,
        "pet_power": 40,
        "pet_max_power": 100,
        "pet_spellbook_sha256": spellbook_hash,
        "pet_spellbook": spellbook,
        "pet_autocast_spell_ids": [],
        "pet_observed_owner_guid": 10,
        "pet_observation_window_started_at_ms": 300,
        "pet_observation_window_ended_at_ms": 300_300,
        "pet_first_observation_at_ms": 300,
        "pet_last_observation_at_ms": 300_300,
        "pet_first_observed_guid": 20,
        "pet_last_observed_guid": 20,
        "pet_guid_mismatch_sample_count": 0,
        "pet_identity_mismatch_sample_count": 0,
        "pet_maximum_observation_gap_ms": 500,
        "pet_guid": 20,
        "pet_ready_ticks": 601,
        "pet_observation_ticks": 601,
        "pet_uptime_ratio": 1.0,
    }
    _projection, valid = pet_setup_projection(
        {"guid": 10, "persistent_setup": setup},
        scored_started_at_ms=300,
        scored_ended_at_ms=300_300,
    )
    assert valid is False
    setup["pet_last_observation_at_ms"] = 300_300
    setup["pet_last_observed_guid"] = 21
    setup["pet_guid_mismatch_sample_count"] = 1
    _projection, valid = pet_setup_projection(
        {"guid": 10, "persistent_setup": setup},
        scored_started_at_ms=300,
        scored_ended_at_ms=300_300,
    )
    assert valid is False
    setup["pet_last_observed_guid"] = 20
    setup["pet_guid_mismatch_sample_count"] = 0
    setup["pet_maximum_observation_gap_ms"] = 2_001
    _projection, valid = pet_setup_projection(
        {"guid": 10, "persistent_setup": setup},
        scored_started_at_ms=300,
        scored_ended_at_ms=300_300,
    )
    assert valid is False

    import hashlib

    setup["pet_maximum_observation_gap_ms"] = 500
    setup["pet_spellbook_sha256"] = hashlib.sha256(
        b"54049:1:0"
    ).hexdigest()
    projection, valid = pet_setup_projection(
        {"guid": 10, "persistent_setup": setup},
        scored_started_at_ms=300,
        scored_ended_at_ms=300_300,
    )
    assert valid is True
    assert projection["uptime"] == 1.0

    setup["pet_observed_owner_guid"] = 11
    _projection, valid = pet_setup_projection(
        {"guid": 10, "persistent_setup": setup},
        scored_started_at_ms=300,
        scored_ended_at_ms=300_300,
    )
    assert valid is False
    setup["pet_observed_owner_guid"] = 10
    setup["pet_last_observation_at_ms"] = 300_299
    _projection, valid = pet_setup_projection(
        {"guid": 10, "persistent_setup": setup},
        scored_started_at_ms=300,
        scored_ended_at_ms=300_300,
    )
    assert valid is False


def test_absent_pet_requires_full_scored_window_identity() -> None:
    setup = {
        "ready": True,
        "required_pet_spell_id": 0,
        "pet_present": False,
        "pet_guid": 0,
        "pet_entry": 0,
        "pet_observed_owner_guid": 10,
        "pet_observation_window_started_at_ms": 1_000,
        "pet_observation_window_ended_at_ms": 301_000,
        "pet_first_observation_at_ms": 1_000,
        "pet_last_observation_at_ms": 301_000,
        "pet_first_observed_guid": 0,
        "pet_last_observed_guid": 0,
        "pet_guid_mismatch_sample_count": 0,
        "pet_identity_mismatch_sample_count": 0,
        "pet_maximum_observation_gap_ms": 500,
        "pet_ready_ticks": 601,
        "pet_observation_ticks": 601,
        "pet_uptime_ratio": 1.0,
    }
    projection, valid = pet_setup_projection(
        {"guid": 10, "persistent_setup": setup},
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )
    assert valid is True
    assert projection["present"] is False

    setup["pet_ready_ticks"] = 151
    setup["pet_observation_ticks"] = 151
    setup["pet_maximum_observation_gap_ms"] = 1_999
    _projection, valid = pet_setup_projection(
        {"guid": 10, "persistent_setup": setup},
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )
    assert valid is False

    setup["pet_ready_ticks"] = 601
    setup["pet_observation_ticks"] = 601
    setup["pet_maximum_observation_gap_ms"] = 500
    setup["pet_ready_ticks"] = 600
    _projection, valid = pet_setup_projection(
        {"guid": 10, "persistent_setup": setup},
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )
    assert valid is False


def test_provisioned_hunter_pet_binds_admission_identity_without_summon_receipt() -> None:
    import hashlib

    admission_spellbook = [
        {"spell_id": 2649, "active": 1},
        {"spell_id": 53401, "active": 193},
    ]
    full_spellbook = [
        {"spell_id": 2649, "active": 1, "type": 0},
        {"spell_id": 53401, "active": 193, "type": 0},
    ]
    admission_sha = hashlib.sha256(b"2649:1;53401:193").hexdigest()
    full_sha = hashlib.sha256(b"2649:1:0;53401:193:0").hexdigest()
    expected = {
        "schema": "hunter_admission_pet_identity_v1",
        "required": True,
        "runtime_projection_complete": True,
        "pet_id": 8_700_114,
        "creature_entry": 8_959,
        "uptime": 1.0,
        "spellbook": admission_spellbook,
        "spellbook_sha256": admission_sha,
        "autocast_spell_ids": [53_401],
        "power": {"power_type": 2, "mode": "maximum"},
    }
    setup = {
        "required_pet_spell_id": 0,
        "required_pet_entry": 0,
        "pet_guid": 20,
        "pet_id": 8_700_114,
        "pet_entry": 8_959,
        "pet_present": True,
        "pet_in_world": True,
        "pet_alive": True,
        "pet_owned": True,
        "pet_permanent": True,
        "pet_type": 1,
        "pet_health": 100,
        "pet_max_health": 100,
        "pet_power_type": 2,
        "pet_power": 40,
        "pet_max_power": 100,
        "pet_admission_spellbook": admission_spellbook,
        "pet_admission_spellbook_sha256": admission_sha,
        "pet_spellbook": full_spellbook,
        "pet_spellbook_sha256": full_sha,
        "pet_autocast_spell_ids": [53_401],
        "pet_observed_owner_guid": 10,
        "pet_observation_window_started_at_ms": 1_000,
        "pet_observation_window_ended_at_ms": 301_000,
        "pet_first_observation_at_ms": 1_000,
        "pet_last_observation_at_ms": 301_000,
        "pet_first_observed_guid": 20,
        "pet_last_observed_guid": 20,
        "pet_guid_mismatch_sample_count": 0,
        "pet_identity_mismatch_sample_count": 0,
        "pet_maximum_observation_gap_ms": 500,
        "pet_ready_ticks": 601,
        "pet_observation_ticks": 601,
        "pet_uptime_ratio": 1.0,
    }
    projection, valid = pet_setup_projection(
        {"guid": 10, "persistent_setup": setup},
        expected=expected,
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )
    assert valid is True
    assert projection == expected

    setup["pet_id"] += 1
    _projection, valid = pet_setup_projection(
        {"guid": 10, "persistent_setup": setup},
        expected=expected,
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )
    assert valid is False


def test_unholy_pet_projection_allows_family_none_and_derived_created_spell() -> None:
    import hashlib

    setup = {
        "ready": True,
        "required_pet_spell_id": 46584,
        "required_pet_entry": 26125,
        "required_pet_family_id": 0,
        "required_pet_created_by_spell_id": 52150,
        "required_pet_type": 0,
        "required_pet_power_type": 3,
        "pet_spell_known": True,
        "pet_native_cast_submitted": True,
        "pet_native_cast_finished": True,
        "pet_native_cast_observed": True,
        "pet_native_cast_submitted_at_ms": 100,
        "pet_native_cast_finished_at_ms": 150,
        "pet_native_cast_observed_at_ms": 200,
        "pet_entry": 26125,
        "pet_family_id": 0,
        "pet_created_by_spell_id": 52150,
        "pet_present": True,
        "pet_in_world": True,
        "pet_alive": True,
        "pet_owned": True,
        "pet_permanent": True,
        "pet_type": 0,
        "pet_health": 10,
        "pet_max_health": 10,
        "pet_power_type": 3,
        "pet_power": 100,
        "pet_max_power": 100,
        "pet_spellbook_sha256": hashlib.sha256(b"47468:1:0").hexdigest(),
        "pet_spellbook": [{"spell_id": 47468, "active": 1, "type": 0}],
        "pet_autocast_spell_ids": [],
        "pet_observed_owner_guid": 10,
        "pet_observation_window_started_at_ms": 300,
        "pet_observation_window_ended_at_ms": 300_300,
        "pet_first_observation_at_ms": 300,
        "pet_last_observation_at_ms": 300_300,
        "pet_first_observed_guid": 20,
        "pet_last_observed_guid": 20,
        "pet_guid_mismatch_sample_count": 0,
        "pet_identity_mismatch_sample_count": 0,
        "pet_maximum_observation_gap_ms": 500,
        "pet_guid": 20,
        "pet_ready_ticks": 601,
        "pet_observation_ticks": 601,
        "pet_uptime_ratio": 1.0,
    }
    projection, valid = pet_setup_projection(
        {"guid": 10, "persistent_setup": setup},
        scored_started_at_ms=300,
        scored_ended_at_ms=300_300,
    )
    assert valid is True
    assert projection["required_pet_family_id"] == 0
    assert projection["required_pet_created_by_spell_id"] == 52150


def test_initial_resource_and_no_item_swap_projections_recompute_raw_facts() -> None:
    fixture = load_fixture_contract_binding("frost_death_knight")
    assert fixture["valid"] is True
    expected = fixture["projection"]["runtime_expected"]["initial_resources"]
    fixture_sha = fixture["content_sha256"]
    target = {
        "guid": 10,
        "fixture_contract": {
            "schema": "phase8_calibration_fixture_contract_v1",
            "content_sha256": fixture_sha,
        },
        "persistent_setup": {"pet_guid": 0},
        "initial_resources": {
            "schema": "phase8_initial_resources_observation_v1",
            "source_contract_sha256": fixture_sha,
            "reset_applied": True,
            "matches_contract": True,
            "observed_at_ms": 900,
            "observed_before_scoring": True,
            "powers": [
                {
                    "unit_kind": "player",
                    "unit_guid": 10,
                    "name": "runic_power",
                    "power_type": 6,
                    "expected_mode": "exact",
                    "expected_native_value": 0,
                    "expected_display_value": 0,
                    "observed_native_value": 0,
                    "observed_display_value": 0,
                    "observed_maximum_native_value": 1_000,
                    "matches_contract": True,
                }
            ],
            "runes": {
                "required": True,
                "expected_ready_mask": 63,
                "observed_ready_mask": 63,
            },
            "combo_points": {"required": False, "expected": 0, "observed": 0},
            "neutral_eclipse": {"required": False, "observed": False},
            "pet_resource": {"required": False, "observed": True},
        },
        "pre_score_state": {
            "schema": "phase8_pre_score_state_observation_v1",
            "observed_at_ms": 950,
            "observed_before_scoring": True,
            "persistent_setup_ready": True,
            "reference_buffs_ready": True,
            "reference_target_debuffs_ready": True,
            "heroism_ready": True,
            "no_active_cast": True,
            "no_combat": True,
            "global_cooldown_clear": True,
            "cooldown_reset_applied": True,
            "warmup_profile_actions_suppressed": True,
        },
        "gear_profile_observation": {
            "items": [
                {
                    "slot": 0,
                    "item_id": 1,
                    "enchant_id": 0,
                    "reforge_id": 0,
                    "gem_item_ids": [],
                }
            ]
        },
    }
    gear_sha = observed_gear_manifest_sha256(target)
    target["item_swap_observation"] = {
        "schema": "phase8_no_item_swap_observation_v1",
        "enabled": False,
        "target_guid": 10,
        "window_started_at_ms": 1_000,
        "window_ended_at_ms": 301_000,
        "first_sample_at_ms": 1_000,
        "last_sample_at_ms": 301_000,
        "maximum_sample_gap_ms": 500,
        "initial_gear_manifest_sha256": gear_sha,
        "current_gear_manifest_sha256": gear_sha,
        "sample_count": 601,
        "mismatch_sample_count": 0,
        "no_drift": True,
    }

    projection, valid = initial_resources_projection(
        target,
        expected=expected,
        fixture_contract_sha256=fixture_sha,
        scored_started_at_ms=1_000,
    )
    assert valid is True
    assert projection == expected
    swap_projection, valid = item_swap_projection(
        target,
        reference_gear_manifest_sha256=gear_sha,
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )
    assert valid is True
    assert swap_projection == {"enabled": False, "items": []}

    target["item_swap_observation"]["sample_count"] = 151
    target["item_swap_observation"]["maximum_sample_gap_ms"] = 1_999
    _projection, valid = item_swap_projection(
        target,
        reference_gear_manifest_sha256=gear_sha,
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )
    assert valid is False
    target["item_swap_observation"]["sample_count"] = 601
    target["item_swap_observation"]["maximum_sample_gap_ms"] = 500

    target["initial_resources"]["powers"][0]["observed_native_value"] = 1
    _projection, valid = initial_resources_projection(
        target,
        expected=expected,
        fixture_contract_sha256=fixture_sha,
        scored_started_at_ms=1_000,
    )
    assert valid is False
    target["initial_resources"]["powers"][0]["observed_native_value"] = 0
    target["initial_resources"]["powers"][0]["unit_guid"] = 11
    _projection, valid = initial_resources_projection(
        target,
        expected=expected,
        fixture_contract_sha256=fixture_sha,
        scored_started_at_ms=1_000,
    )
    assert valid is False
    target["item_swap_observation"]["mismatch_sample_count"] = 1
    _projection, valid = item_swap_projection(
        target,
        reference_gear_manifest_sha256=gear_sha,
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )
    assert valid is False

    target["item_swap_observation"]["mismatch_sample_count"] = 0
    target["item_swap_observation"]["first_sample_at_ms"] = 999
    _projection, valid = item_swap_projection(
        target,
        reference_gear_manifest_sha256=gear_sha,
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )
    assert valid is False

    target["item_swap_observation"]["first_sample_at_ms"] = 1_000
    target["item_swap_observation"]["maximum_sample_gap_ms"] = 2_001
    _projection, valid = item_swap_projection(
        target,
        reference_gear_manifest_sha256=gear_sha,
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )
    assert valid is False

    target["item_swap_observation"]["maximum_sample_gap_ms"] = 500
    target["item_swap_observation"]["sample_count"] = 1
    target["item_swap_observation"]["last_sample_at_ms"] = 1_000
    _projection, valid = item_swap_projection(
        target,
        reference_gear_manifest_sha256=gear_sha,
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )
    assert valid is False


def test_fixture_target_projection_binds_two_observations_and_passive_window() -> None:
    fixture = load_fixture_contract_binding("frost_death_knight")
    expected = fixture["projection"]["runtime_expected"]
    target = expected["fixture_target"]
    distance = expected["target_distance"]
    live = {
        "entry": target["entry"],
        "level": target["level"],
        "armor": target["armor"],
        "creature_type": target["creature_type"],
        "max_health": target["live_max_health"],
    }
    calibration = {
        "scored_started_at_ms": 1_000,
        "scored_ended_at_ms": 301_000,
        "fixture_contract": {
            "schema": "phase8_calibration_fixture_contract_v1",
            "content_sha256": fixture["content_sha256"],
        },
        "fixture_target": {
            "isolated_single_target": True,
            "expected": {
                **live,
                "passive": True,
                "runtime_min_distance_yards": distance["runtime_min_yards"],
                "runtime_max_distance_yards": distance["runtime_max_yards"],
            },
            "observed_at_provisioning": {
                "observed_at_ms": 500,
                **live,
                "guid": 90,
                "creature_type_mask": 256,
                "map_id": 0,
                "x": 10.0,
                "y": 20.0,
                "z": 30.0,
            },
            "observed_before_scoring": {
                "observed_at_ms": 900,
                "before_scoring": True,
                **live,
                "guid": 90,
                "creature_type_mask": 256,
                "map_id": 0,
                "x": 10.0,
                "y": 20.0,
                "z": 30.0,
                "bot_target_distance": 2.0,
                "in_combat": False,
                "has_victim": False,
            },
            "runtime_guid": 90,
            "map_id": 0,
            "bot_target_distance": 2.0,
            "geometry_validated": True,
            "native_line_of_sight": True,
            "native_path_reachable": True,
            "target_attack_observation_sample_count": 601,
            "target_attack_event_count": 0,
            "scored_passive_observation": {
                "target_guid": 90,
                "window_started_at_ms": 1_000,
                "window_ended_at_ms": 301_000,
                "first_sample_at_ms": 1_000,
                "last_sample_at_ms": 301_000,
                "maximum_sample_gap_ms": 500,
                "sample_count": 601,
                "victim_observation_sample_count": 0,
                "target_attack_event_count": 0,
                "passive": True,
            },
        },
    }
    target_projection, distance_projection, valid = fixture_target_projections(
        calibration,
        expected_target=target,
        expected_distance=distance,
        fixture_contract_sha256=fixture["content_sha256"],
    )
    assert valid is True
    assert target_projection == target
    assert distance_projection == distance

    passive = calibration["fixture_target"]["scored_passive_observation"]
    passive["first_sample_at_ms"] = 999
    _target, _distance, valid = fixture_target_projections(
        calibration,
        expected_target=target,
        expected_distance=distance,
        fixture_contract_sha256=fixture["content_sha256"],
    )
    assert valid is False
    passive["first_sample_at_ms"] = 1_000
    passive["sample_count"] = 151
    passive["maximum_sample_gap_ms"] = 1_999
    calibration["fixture_target"][
        "target_attack_observation_sample_count"
    ] = 151
    _target, _distance, valid = fixture_target_projections(
        calibration,
        expected_target=target,
        expected_distance=distance,
        fixture_contract_sha256=fixture["content_sha256"],
    )
    assert valid is False
    passive["sample_count"] = 601
    passive["maximum_sample_gap_ms"] = 500
    calibration["fixture_target"][
        "target_attack_observation_sample_count"
    ] = 601

    calibration["fixture_target"]["target_attack_event_count"] = 1
    _target, _distance, valid = fixture_target_projections(
        calibration,
        expected_target=target,
        expected_distance=distance,
        fixture_contract_sha256=fixture["content_sha256"],
    )
    assert valid is False

    calibration["fixture_target"]["target_attack_event_count"] = 0
    calibration["fixture_target"]["scored_passive_observation"][
        "last_sample_at_ms"
    ] = 300_999
    _target, _distance, valid = fixture_target_projections(
        calibration,
        expected_target=target,
        expected_distance=distance,
        fixture_contract_sha256=fixture["content_sha256"],
    )
    assert valid is False
    calibration["fixture_target"]["scored_passive_observation"][
        "last_sample_at_ms"
    ] = 301_000
    calibration["fixture_target"]["scored_passive_observation"][
        "maximum_sample_gap_ms"
    ] = 2_001
    _target, _distance, valid = fixture_target_projections(
        calibration,
        expected_target=target,
        expected_distance=distance,
        fixture_contract_sha256=fixture["content_sha256"],
    )
    assert valid is False


def test_static_preflight_blocks_missing_manifest_before_runtime() -> None:
    result = preflight_reference_condition_compatibility(
        target_spec="arms_warrior",
        target_row={
            "spec_target_id": "arms_warrior",
            "runtime_join_key": "arms_warrior",
        },
        reference_row={
            "spec_target_id": "arms_warrior",
            "reference_id": "cata_p4:arms_warrior",
            "provider_revision": "a" * 40,
            "reference_conditions": dict(EXPECTED_REFERENCE_CONDITIONS),
        },
        request_binding={
            "valid": False,
            "reasons": ["test_missing_request_binding"],
            "comparison_manifest": {},
        },
    )

    assert result["conditions_compatible"] is False
    assert "comparison_manifest_present" in result["reasons"]
    assert "comparison_manifest_required_fact_coverage" in result["reasons"]


def test_all_fixture_simulator_option_leaves_are_explicitly_classified() -> None:
    expected_specs = {
        "affliction_warlock",
        "arms_warrior",
        "assassination_rogue",
        "balance_druid",
        "combat_rogue",
        "demonology_warlock",
        "elemental_shaman",
        "feral_druid_dps",
        "fire_mage",
        "frost_death_knight",
        "fury_warrior",
        "marksmanship_hunter",
        "retribution_paladin",
        "shadow_priest",
        "survival_hunter",
        "unholy_death_knight",
    }
    observed_specs: set[str] = set()
    for target_spec in sorted(expected_specs):
        binding = load_fixture_contract_binding(target_spec)
        observed_specs.add(binding["target_spec"])
        classification = binding["projection"][
            "simulator_option_classification"
        ]
        assert classification["valid"] is True
        assert classification["unclassified"] == []
        assert binding["projection"]["spec"][
            "simulator_option_leaf_classification"
        ] == {
            key: value
            for key, value in classification.items()
            if key != "valid"
        }
        assert (
            set(classification["atomic_runtime_requirements"].values())
            <= set(REQUIRED_REQUIREMENT_CLASSES)
        )

    assert observed_specs == expected_specs


def test_cpp_reference_aura_universe_covers_every_fixture_setup_aura() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
    ).read_text(encoding="utf-8")
    match = re.search(
        r"std::array<uint32,\s*(\d+)>\s+PlayerAuraUniverse\s*=\s*\{(.*?)\};",
        source,
        flags=re.DOTALL,
    )
    assert match is not None
    body_without_comments = re.sub(r"//[^\n]*", "", match.group(2))
    producer_ids = [
        int(value) for value in re.findall(r"\b\d+\b", body_without_comments)
    ]
    assert len(producer_ids) == int(match.group(1))
    assert all(spell_id > 0 for spell_id in producer_ids)
    assert len(producer_ids) == len(set(producer_ids))

    required_setup_ids: set[int] = set()
    for target_spec in (
        "affliction_warlock",
        "arms_warrior",
        "assassination_rogue",
        "balance_druid",
        "combat_rogue",
        "demonology_warlock",
        "elemental_shaman",
        "feral_druid_dps",
        "fire_mage",
        "frost_death_knight",
        "fury_warrior",
        "marksmanship_hunter",
        "retribution_paladin",
        "shadow_priest",
        "survival_hunter",
        "unholy_death_knight",
    ):
        required_setup_ids.update(
            load_fixture_contract_binding(target_spec)["projection"][
                "runtime_expected"
            ]["form_presence"]["required_aura_spell_ids"]
        )
    expected_player_ids = (
        required_setup_ids
        | set(RAID_REQUIRED_PLAYER_AURA_IDS)
        | set(PRIMARY_STAT_AURA_IDS)
        | {REPLENISHMENT_AURA_ID, NON_PALADIN_MIGHT_AURA_ID}
        | set(FLASK_ITEM_BY_AURA)
        | set(FOOD_ITEMS_BY_AURA)
    )
    assert expected_player_ids <= set(producer_ids)

    target_match = re.search(
        r"std::array<uint32,\s*(\d+)>\s+TargetAuraUniverse\s*=\s*\{(.*?)\};",
        source,
        flags=re.DOTALL,
    )
    assert target_match is not None
    target_body = re.sub(r"//[^\n]*", "", target_match.group(2))
    producer_target_ids = [
        int(value) for value in re.findall(r"\b\d+\b", target_body)
    ]
    assert len(producer_target_ids) == int(target_match.group(1))
    assert set(REQUIRED_TARGET_DEBUFF_AURA_IDS) | {
        SUNDER_ARMOR_AURA_ID
    } | set(EXTERNAL_BLEED_AURA_IDS) <= set(producer_target_ids)


def test_all_16_reference_condition_projections_match_raw_fixture_observations() -> None:
    target_specs = {
        "affliction_warlock",
        "arms_warrior",
        "assassination_rogue",
        "balance_druid",
        "combat_rogue",
        "demonology_warlock",
        "elemental_shaman",
        "feral_druid_dps",
        "fire_mage",
        "frost_death_knight",
        "fury_warrior",
        "marksmanship_hunter",
        "retribution_paladin",
        "shadow_priest",
        "survival_hunter",
        "unholy_death_knight",
    }
    for target_spec in sorted(target_specs):
        binding = load_fixture_contract_binding(target_spec)
        expected = binding["projection"]["runtime_expected"]
        target = _reference_condition_observation()
        target["race_id"] = expected["racial"]["race_id"]
        target["active_talent_spell_ids"] = (
            [53304] if target_spec == "survival_hunter" else [100]
        )
        raw = target["reference_condition_observation"]
        raw["fixture_contract_sha256"] = binding["content_sha256"]
        raw["configured"] = {
            "flask_item_id": expected["flask"]["item_id"],
            "flask_aura_spell_id": expected["flask"][
                "observed_aura_spell_id"
            ],
            "food_item_id": expected["food"]["item_id"],
            "food_aura_spell_id": expected["food"][
                "observed_aura_spell_id"
            ],
            "required_setup_aura_spell_ids": expected["form_presence"][
                "required_aura_spell_ids"
            ],
        }
        active_ids = set(expected["raid_buffs"]["required_player_aura_spell_ids"])
        active_ids.add(79061)
        active_ids.update(expected["raid_buffs"]["mana_player_aura_spell_ids"])
        active_ids.update(
            expected["raid_buffs"]["non_paladin_player_aura_spell_ids"]
        )
        active_ids.add(expected["flask"]["observed_aura_spell_id"])
        if expected["food"]["observed_aura_spell_id"]:
            active_ids.add(expected["food"]["observed_aura_spell_id"])
        active_ids.update(expected["form_presence"]["required_aura_spell_ids"])
        player_universe = {
            row["spell_id"] for row in raw["player_auras"]
        } | active_ids
        raw["player_auras"] = [
            {
                "spell_id": spell_id,
                "active_samples": 601 if spell_id in active_ids else 0,
                "inactive_samples": 0 if spell_id in active_ids else 601,
            }
            for spell_id in sorted(player_universe)
        ]

        projections, valid = reference_condition_projections(
            target_spec,
            target,
            fixture_target_guid=90,
            fixture_contract_sha256=binding["content_sha256"],
            scored_started_at_ms=1_000,
            scored_ended_at_ms=301_000,
        )

        assert valid is True, target_spec
        for requirement_id in (
            "flask",
            "food",
            "prepot",
            "combat_potion",
            "tinker",
            "racial",
            "raid_buffs",
            "target_debuffs",
        ):
            assert projections[requirement_id] == expected[requirement_id], (
                target_spec,
                requirement_id,
            )
        assert projections["form_presence"] == expected["form_presence"]
        native_setup = {
            "weapon_imbues": expected["prepull_setup"]["weapon_imbues"]
        } if "weapon_imbues" in expected["prepull_setup"] else {}
        prepull = compose_prepull_setup_projection(
            target_spec,
            native_setup,
            projections,
            item_swap_projection=expected["item_swap"],
            external_windows_projection=expected["prepull_setup"][
                "external_windows"
            ],
        )
        assert prepull == expected["prepull_setup"], target_spec


def test_all_16_static_preflights_are_blocked_only_by_pending_generation() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = build_manifest(root=root)
    targets = {
        row["spec_target_id"]: row
        for row in json.loads(
            (root / "experiments/configs/all_spec_targets_cata_p4_v1.json")
            .read_text(encoding="utf-8")
        )["targets"]
    }
    references = {
        row["spec_target_id"]: row
        for row in json.loads(
            (root / "experiments/configs/all_spec_references_cata_p4_v1.json")
            .read_text(encoding="utf-8")
        )["references"]
    }
    expected_pending_reasons = {
        "reference_request_binding_valid",
        "exact_settings_result_key_pinned",
        "reference_result_status_acceptable",
        "exact_settings_reference_value_pinned",
    }
    observed_specs: set[str] = set()
    for row in manifest["requests"]:
        target_spec = row["target_spec"]
        observed_specs.add(target_spec)
        fixture_binding = load_fixture_contract_binding(target_spec)
        assert row["request"]["fixture_contract_sha256"] == fixture_binding[
            "content_sha256"
        ]
        heroism_requirement = next(
            requirement
            for requirement in row["comparison_manifest"]["requirements"]
            if requirement["id"] == "heroism"
        )
        assert heroism_requirement["equals"] == {"windows_ms": []}
        result = preflight_reference_condition_compatibility(
            target_spec=target_spec,
            target_row=targets[target_spec],
            reference_row=references[target_spec],
            request_binding={
                "valid": False,
                "reasons": ["generated_result_pending"],
                "catalog_sha256": canonical_sha256(manifest),
                "comparison_manifest": row["comparison_manifest"],
            },
            fixture_contract=fixture_binding,
        )

        assert set(result["reasons"]) == expected_pending_reasons, target_spec

    assert len(observed_specs) == 16


def test_unknown_simulator_option_leaf_fails_closed() -> None:
    classification = classify_simulator_option_leaves(
        {
            "class_options": {"unobserved_future_toggle": True},
            "starting_distance_yards": 2.0,
            "target_auto_attacks": False,
        }
    )

    assert classification["valid"] is False
    assert classification["unclassified"] == [
        "class_options.unobserved_future_toggle"
    ]


def _external_window_observation(*, shadow: bool = True) -> dict:
    del shadow  # V1 base comparison deliberately disables every temporal external.
    return {
        "guid": 10,
        "pre_score_state": {
            "schema": "phase8_pre_score_state_observation_v1",
            "observed_at_ms": 900,
            "heroism_ready": False,
            "temporal_external_auras_absent": True,
        },
        "external_window_observation": {
            "schema": "phase8_external_windows_observation_v1",
            "target_guid": 10,
            "window_started_at_ms": 1_000,
            "window_ended_at_ms": 301_000,
            "first_sample_at_ms": 1_000,
            "last_sample_at_ms": 301_000,
            "maximum_sample_gap_ms": 500,
            "sample_count": 6_000,
            "heroism": {
                "source_count": 0,
                "spell_id": 2825,
                "windows_ms": [],
                "expected_active_samples": 0,
                "observed_active_samples": 0,
                "mismatch_samples": 0,
            },
            "power_infusion": {
                "source_count": 0,
                "spell_id": 10060,
                "windows_ms": [],
                "expected_active_samples": 0,
                "observed_active_samples": 0,
                "mismatch_samples": 0,
            },
            "dark_intent_proc": {
                "base_spell_id": 85767,
                "base_enabled": False,
                "unexpected_base_active_samples": 0,
                "proc_spell_id": 85759,
                "uptime_pct": 0,
                "expected_uptime_pct": 0,
                "unexpected_active_samples": 0,
            },
            "synapse_springs": {
                "spell_id": 96230,
                "windows_ms": [],
                "expected_windows_ms": [],
                "unexpected_active_samples": 0,
            },
        }
    }


def _reference_condition_observation() -> dict:
    sample_count = 601
    active_player = {
        53646,
        79058,
        24932,
        2895,
        8515,
        8076,
        82930,
        79061,
        79102,
        79472,
        2457,
    }
    player_universe = active_player | {
        57669,
        20217,
        79063,
        1126,
        79470,
        79471,
        87547,
    }
    required_target = {1490, 22959, 81326, 58567}
    bleed_universe = {16511, 33876, 46857}

    def player_row(spell_id: int) -> dict:
        active = sample_count if spell_id in active_player else 0
        return {
            "spell_id": spell_id,
            "active_samples": active,
            "inactive_samples": sample_count - active,
        }

    def target_row(spell_id: int) -> dict:
        active = sample_count if spell_id in required_target else 0
        return {
            "spell_id": spell_id,
            "active_samples": active,
            "inactive_samples": sample_count - active,
            "caster_guid": 10 if active else 0,
            "owner_match_samples": active,
            "owner_mismatch_samples": 0,
        }

    return {
        "guid": 10,
        "race_id": 1,
        "pre_score_state": {
            "schema": "phase8_pre_score_state_observation_v1",
            "observed_at_ms": 900,
            "external_bleed_auras_absent": True,
        },
        "reference_condition_observation": {
            "schema": "phase8_reference_condition_observation_v1",
            "fixture_contract_sha256": "e" * 64,
            "player_guid": 10,
            "fixture_target_guid": 90,
            "window_started_at_ms": 1_000,
            "window_ended_at_ms": 301_000,
            "first_sample_at_ms": 1_000,
            "last_sample_at_ms": 301_000,
            "maximum_sample_gap_ms": 500,
            "sample_count": sample_count,
            "configured": {
                "flask_item_id": 58088,
                "flask_aura_spell_id": 79472,
                "food_item_id": 0,
                "food_aura_spell_id": 0,
                "required_setup_aura_spell_ids": [2457],
            },
            "player_auras": [
                player_row(spell_id) for spell_id in sorted(player_universe)
            ],
            "target_auras": [
                target_row(spell_id)
                for spell_id in sorted(required_target | bleed_universe)
            ],
            "target_stacked_auras": [
                {
                    "spell_id": 58567,
                    "required_stacks": 3,
                    "matching_samples": sample_count,
                    "mismatch_samples": 0,
                    "minimum_observed_stacks": 3,
                    "maximum_observed_stacks": 3,
                    "caster_guid": 10,
                    "owner_match_samples": sample_count,
                    "owner_mismatch_samples": 0,
                }
            ],
            "external_bleed_aura_spell_ids": sorted(bleed_universe),
            "unexpected_external_bleed_active_samples": 0,
            "dynamic_disabled": {
                "prepot_item_id": 0,
                "prepot_use_count": 0,
                "combat_potion_item_id": 0,
                "combat_potion_use_count": 0,
                "tinker_item_id": 0,
                "tinker_spell_id": 0,
                "tinker_use_count": 0,
                "racial_spell_id": 0,
                "racial_use_count": 0,
                "last_potion_id_nonzero_samples": 0,
                "unexpected_dynamic_aura_active_samples": 0,
            },
        },
    }


def test_reference_condition_projections_reconstruct_full_window_raw_facts() -> None:
    projection, valid = reference_condition_projections(
        "arms_warrior",
        _reference_condition_observation(),
        fixture_target_guid=90,
        fixture_contract_sha256="e" * 64,
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )

    assert valid is True
    assert projection["flask"] == {
        "item_id": 58088,
        "observed_aura_spell_id": 79472,
    }
    assert projection["food"] == {"item_id": 0, "observed_aura_spell_id": 0}
    assert projection["prepot"] == {"item_id": 0, "use_count": 0}
    assert projection["combat_potion"] == {"item_id": 0, "use_count": 0}
    assert projection["tinker"] == {"item_id": 0, "use_count": 0}
    assert projection["racial"] == {
        "race": "human",
        "race_id": 1,
        "spell_id": 0,
        "use_count": 0,
    }
    assert projection["raid_buffs"]["mana_player_aura_spell_ids"] == []
    assert projection["raid_buffs"]["non_paladin_player_aura_spell_ids"] == [
        79102
    ]
    assert projection["form_presence"] == {
        "required_aura_spell_ids": [2457]
    }


def test_reference_condition_projections_reject_raw_identity_and_condition_tamper() -> None:
    mutations = {
        "fixture_hash": lambda raw: raw.update(
            fixture_contract_sha256="f" * 64
        ),
        "player_guid": lambda raw: raw.update(player_guid=11),
        "target_guid": lambda raw: raw.update(fixture_target_guid=91),
        "first_sample": lambda raw: raw.update(first_sample_at_ms=1_001),
        "sample_gap": lambda raw: raw.update(maximum_sample_gap_ms=2_001),
        "flask_item": lambda raw: raw["configured"].update(flask_item_id=58086),
        "dynamic_use": lambda raw: raw["dynamic_disabled"].update(
            combat_potion_use_count=1
        ),
        "bleed": lambda raw: raw.update(
            unexpected_external_bleed_active_samples=1
        ),
        "sunder": lambda raw: raw["target_stacked_auras"][0].update(
            minimum_observed_stacks=2
        ),
        "owner": lambda raw: raw["target_auras"][0].update(
            owner_mismatch_samples=1
        ),
        "double_primary_stat": lambda raw: next(
            row for row in raw["player_auras"] if row["spell_id"] == 20217
        ).update(active_samples=601, inactive_samples=0),
    }
    for mutate in mutations.values():
        target = _reference_condition_observation()
        mutate(target["reference_condition_observation"])
        _projection, valid = reference_condition_projections(
            "arms_warrior",
            target,
            fixture_target_guid=90,
            fixture_contract_sha256="e" * 64,
            scored_started_at_ms=1_000,
            scored_ended_at_ms=301_000,
        )
        assert valid is False

    target = _reference_condition_observation()
    raw = target["reference_condition_observation"]
    raw["sample_count"] = 151
    raw["maximum_sample_gap_ms"] = 1_999
    for row in raw["player_auras"]:
        active = row["active_samples"] > 0
        row["active_samples"] = 151 if active else 0
        row["inactive_samples"] = 0 if active else 151
    for row in raw["target_auras"]:
        active = row["active_samples"] > 0
        row["active_samples"] = 151 if active else 0
        row["inactive_samples"] = 0 if active else 151
        row["owner_match_samples"] = 151 if active else 0
    raw["target_stacked_auras"][0]["matching_samples"] = 151
    raw["target_stacked_auras"][0]["owner_match_samples"] = 151
    _projection, valid = reference_condition_projections(
        "arms_warrior",
        target,
        fixture_target_guid=90,
        fixture_contract_sha256="e" * 64,
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )
    assert valid is False


def test_night_elf_shadowmeld_success_cannot_certify_disabled_racial_use() -> None:
    target = _reference_condition_observation()
    target["race_id"] = 4
    dynamic = target["reference_condition_observation"]["dynamic_disabled"]
    dynamic["racial_spell_id"] = 58984
    dynamic["racial_use_count"] = 1

    projection, valid = reference_condition_projections(
        "balance_druid",
        target,
        fixture_target_guid=90,
        fixture_contract_sha256="e" * 64,
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )

    assert projection["racial"] == {
        "race_id": 4,
        "race": "night_elf",
        "spell_id": 58984,
        "use_count": 1,
    }
    assert valid is False


def test_feral_owned_bleed_is_allowed_but_external_bleed_is_rejected() -> None:
    target = _reference_condition_observation()
    bleed = next(
        row
        for row in target["reference_condition_observation"]["target_auras"]
        if row["spell_id"] == 33876
    )
    bleed.update(
        active_samples=601,
        inactive_samples=0,
        caster_guid=10,
        owner_match_samples=601,
    )
    projection, valid = reference_condition_projections(
        "feral_druid_dps",
        target,
        fixture_target_guid=90,
        fixture_contract_sha256="e" * 64,
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )
    assert valid is True
    assert projection["target_debuffs"]["external_bleed_active"] is False

    bleed.update(caster_guid=11, owner_match_samples=0, owner_mismatch_samples=601)
    target["reference_condition_observation"][
        "unexpected_external_bleed_active_samples"
    ] = 601
    _projection, valid = reference_condition_projections(
        "feral_druid_dps",
        target,
        fixture_target_guid=90,
        fixture_contract_sha256="e" * 64,
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )
    assert valid is False


def test_external_window_projection_proves_full_window_absence() -> None:
    projection, valid = external_windows_projection(
        _external_window_observation(),
        scored_started_at_ms=1_000,
        scored_ended_at_ms=301_000,
    )

    assert valid is True
    assert projection == {
        "schema": "phase8_external_windows_v1",
        "heroism": {
            "source_count": 0,
            "spell_id": 2825,
            "windows_ms": [],
        },
        "power_infusion": {
            "source_count": 0,
            "spell_id": 10060,
            "windows_ms": [],
        },
        "dark_intent_proc": {
            "base_spell_id": 85767,
            "base_enabled": False,
            "proc_spell_id": 85759,
            "uptime_pct": 0,
        },
        "synapse_springs": {"spell_id": 96230, "windows_ms": []},
    }


def test_external_window_projection_rejects_presence_or_identity_drift() -> None:
    for mutate in (
        "heroism",
        "power_infusion",
        "dark_intent_base",
        "dark_intent_proc",
        "synapse",
        "spell",
        "boolean_count",
        "target_guid",
        "window_end",
        "sample_gap",
        "impossible_cadence",
    ):
        target = _external_window_observation()
        observation = target["external_window_observation"]
        if mutate == "heroism":
            observation["heroism"]["observed_active_samples"] = 1
        elif mutate == "power_infusion":
            observation["power_infusion"]["mismatch_samples"] = 1
        elif mutate == "dark_intent_base":
            observation["dark_intent_proc"][
                "unexpected_base_active_samples"
            ] = 1
        elif mutate == "dark_intent_proc":
            observation["dark_intent_proc"]["unexpected_active_samples"] = 1
        elif mutate == "synapse":
            observation["synapse_springs"]["unexpected_active_samples"] = 1
        elif mutate == "boolean_count":
            observation["sample_count"] = True
        elif mutate == "target_guid":
            observation["target_guid"] = 11
        elif mutate == "window_end":
            observation["last_sample_at_ms"] = 300_999
        elif mutate == "sample_gap":
            observation["maximum_sample_gap_ms"] = 2_001
        elif mutate == "impossible_cadence":
            observation["sample_count"] = 151
            observation["maximum_sample_gap_ms"] = 1_999
        else:
            observation["power_infusion"]["spell_id"] = 1

        _projection, valid = external_windows_projection(
            target,
            scored_started_at_ms=1_000,
            scored_ended_at_ms=301_000,
        )
        assert valid is False


def test_external_absence_is_folded_into_prepull_and_heroism_projection() -> None:
    calibration, target, setup, runtime, manifest = _compatible_fixture()
    exact = derive_reference_condition_compatibility(
        target_spec="arms_warrior",
        reference_setup=setup,
        reference_conditions=EXPECTED_REFERENCE_CONDITIONS,
        calibration=calibration,
        runtime_normalization=calibration["normalization"],
        target_observation=target,
        runtime_facts=runtime,
        expected_manifest=manifest,
    )
    assert exact["checks"]["runtime_external_windows_observation_valid"] is True
    assert exact["runtime_reference_facts"]["heroism_projection"] == {
        "windows_ms": []
    }
    assert exact["runtime_reference_facts"]["prepull_setup_projection"][
        "external_windows"
    ] == exact["runtime_reference_facts"]["external_windows_projection"]

    target = copy.deepcopy(target)
    target["external_window_observation"]["heroism"][
        "observed_active_samples"
    ] = 1
    drifted = derive_reference_condition_compatibility(
        target_spec="arms_warrior",
        reference_setup=setup,
        reference_conditions=EXPECTED_REFERENCE_CONDITIONS,
        calibration=calibration,
        runtime_normalization=calibration["normalization"],
        target_observation=target,
        runtime_facts=runtime,
        expected_manifest=manifest,
    )
    assert drifted["checks"]["runtime_external_windows_observation_valid"] is False
    assert drifted["checks"]["runtime_prepull_setup_receipts_valid"] is False


def test_static_preflight_accepts_only_verified_fixture_root() -> None:
    _calibration, target, _setup, runtime, manifest = _compatible_fixture()
    target = {
        **target,
        "spec_target_id": "arms_warrior",
        "runtime_join_key": "arms_warrior",
    }
    fixture_requirement = next(
        row for row in manifest["requirements"] if row["id"] == "fixture_target"
    )
    fixture_requirement["static_verifiability"] = "fixture_contract_exact"
    fixture_requirement["planned_path"] = "fixture.fixture_target"
    fixture_requirement["planned_equals"] = {"level": 88, "armor": 11977}
    reference = {
        "spec_target_id": "arms_warrior",
        "reference_id": "cata_p4:arms_warrior",
        "provider_revision": "a" * 40,
        "expected_output": {
            "result_key": runtime["reference_result_key"],
            # Legacy catalog result is provenance-only; the verified request
            # binding is the sole denominator authority.
            "metrics": {"dps": runtime["reference_value"] * 99},
        },
        "gear": {
            "source_sha256": "1" * 64,
            "transformed_manifest_sha256": runtime[
                "reference_gear_manifest_sha256"
            ],
            "transform_schema": "wowsims_cata_equipment_manifest_v1",
            "permanent_enchant_applicability_authority": (
                "pinned_wowsims_preset_exact"
            ),
        },
    }
    request_binding = {
        "valid": True,
        "reasons": [],
        "catalog_sha256": "2" * 64,
        "comparison_manifest": manifest,
    }
    fixture_binding = {
        "valid": True,
        "reasons": [],
        "content_sha256": runtime["fixture_contract_sha256"],
        "projection": {"fixture_target": {"level": 88, "armor": 11977}},
    }

    result = preflight_reference_condition_compatibility(
        target_spec="arms_warrior",
        target_row=target,
        reference_row=reference,
        request_binding=request_binding,
        fixture_contract=fixture_binding,
    )

    assert result["conditions_compatible"] is True
    assert result["reasons"] == []

    fixture_requirement["planned_path"] = "source_contract.fixture_target"
    rejected = preflight_reference_condition_compatibility(
        target_spec="arms_warrior",
        target_row=target,
        reference_row=reference,
        request_binding=request_binding,
        fixture_contract=fixture_binding,
    )
    assert rejected["conditions_compatible"] is False
    assert "planned_requirement:fixture_target" in rejected["reasons"]


def test_role_gate_keeps_compatibility_and_ordinary_failures() -> None:
    record = {
        "schema": "all_spec_role_calibration_record_v1",
        "evidence_class": "non_certifying_calibration_fixture",
        "runtime_mode": "calibration_fixture",
        "mode": "single_target_300",
        "role": "dps",
        "target_spec": "arms_warrior",
        "identity": {},
        "window": {},
        "metrics": {
            "reference_value": 50_000.0,
            "measured_value": 1.0,
        },
        "reference_condition_compatibility": {
            "target_spec": "arms_warrior",
            "conditions_compatible": False,
            "reasons": ["runtime_prepot_observed"],
        },
    }
    policy = load_policy(
        Path("experiments/configs/all_spec_role_calibration_policy_v2.json")
    )

    evaluation = evaluate_calibration(record, policy)

    assert evaluation["passed"] is False
    assert "reference_conditions_compatible" in evaluation["failure_reasons"]
    assert "reference_hard_floor" in evaluation["failure_reasons"]
