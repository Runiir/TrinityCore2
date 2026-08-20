#!/usr/bin/env python3
"""Validate and generate the shared Phase 8 calibration-fixture contract."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from tools.bot_ml.cata_dps_consumables import (
    CONTROLLED_DPS_SPECS,
    validate_controlled_consumable_profile,
)


ROOT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""}:
    # Keep the checked-in direct invocation reproducible as well as the normal
    # `python -m tools.bot_ml.phase8_fixture_contract` form.
    sys.path.insert(0, str(ROOT))
DEFAULT_AUTHORED_CONTRACT_PATH = (
    ROOT / "experiments/configs/phase8_calibration_fixture_contract_v1.json"
)
DEFAULT_MATERIALIZED_CONTRACT_PATH = (
    ROOT
    / "experiments/configs/phase8_calibration_fixture_contract_v1.materialized.json"
)
# Consumers intentionally default to the checked-in, self-contained bytes.
# Ambient target-catalog/DBC reads are reserved for --write/--check-materialized.
DEFAULT_CONTRACT_PATH = DEFAULT_MATERIALIZED_CONTRACT_PATH
DEFAULT_TARGET_CATALOG_PATH = (
    ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
)
DEFAULT_HEADER_PATH = (
    ROOT / "src/server/game/Bots/BotCalibrationFixtureContractGenerated.h"
)
EXPECTED_SPECS = {
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
POWER_NAMES = {
    0: "mana",
    1: "rage",
    2: "focus",
    3: "energy",
    6: "runic_power",
    7: "soul_shards",
    8: "eclipse",
    9: "holy_power",
}
LIFECYCLE_REQUIRES_GENERATION = "requires_generation"
LIFECYCLE_FINAL_FOR_OFFLINE_REFERENCE_GENERATION = (
    "final_for_offline_reference_generation"
)
LIFECYCLE_STATUSES = {
    LIFECYCLE_REQUIRES_GENERATION,
    LIFECYCLE_FINAL_FOR_OFFLINE_REFERENCE_GENERATION,
}

# Exhaustive classification of every semantic simulator-option leaf. Atomic
# rows must be proven by an independently observed live requirement; strategy
# rows are simulator-only choices covered by the byte-exact request execution
# policy. Materialization rejects every unclassified future leaf.
SIMULATOR_OPTION_ATOMIC_RUNTIME_REQUIREMENTS = {
    "starting_distance_yards": "target_distance",
    "target_auto_attacks": "fixture_target",
    "class_options.starting_rage": "initial_resources",
    "class_options.starting_runic_power": "initial_resources",
    "class_options.summon": "pet_setup",
    "class_options.pet_type": "pet_setup",
    "class_options.pet_uptime": "pet_setup",
    "class_options.mainhand_poison": "prepull_setup",
    "class_options.offhand_poison": "prepull_setup",
    "class_options.shield": "form_presence",
    "class_options.armor": "form_presence",
    "class_options.aura": "form_presence",
    "class_options.seal": "form_presence",
    "class_options.assume_external_bleed_active": "target_debuffs",
    "class_options.sniper_training_uptime": "prepull_setup",
}
SIMULATOR_OPTION_REFERENCE_EXECUTION_POLICY = {
    "class_options.detonate_seed",
    "class_options.thrown_poison",
    "class_options.time_to_trap_weave_ms",
    "class_options.totems.air",
    "class_options.totems.earth",
    "class_options.totems.fire",
    "class_options.totems.fire_elemental",
    "class_options.totems.water",
}

NATIVE_PLAYER_SPEC_KEYS = {
    "affliction_warlock": "affliction_warlock",
    "arms_warrior": "arms_warrior",
    "assassination_rogue": "assassination_rogue",
    "balance_druid": "balance_druid",
    "combat_rogue": "combat_rogue",
    "demonology_warlock": "demonology_warlock",
    "elemental_shaman": "elemental_shaman",
    "feral_druid_dps": "feral_druid",
    "fire_mage": "fire_mage",
    "frost_death_knight": "frost_death_knight",
    "fury_warrior": "fury_warrior",
    "marksmanship_hunter": "marksmanship_hunter",
    "retribution_paladin": "retribution_paladin",
    "shadow_priest": "shadow_priest",
    "survival_hunter": "survival_hunter",
    "unholy_death_knight": "unholy_death_knight",
}

MANA_RESOURCE_SPECS = {
    "affliction_warlock",
    "balance_druid",
    "demonology_warlock",
    "elemental_shaman",
    "fire_mage",
    "retribution_paladin",
    "shadow_priest",
}

# Exact, retained non-consumable rows from the selected upstream APLs. Setup
# represented natively by the player spec options (paladin seal/aura, shaman
# shield/imbue, warlock/DK pet options, and implicit druid/priest form state)
# is recorded separately in initial_state and must not be double-cast here.
NATIVE_ROTATION_PREPULL_CASTS: dict[str, tuple[tuple[int, str], ...]] = {
    "arms_warrior": ((2457, "-4s"),),
    "feral_druid_dps": ((768, "-1.5s"),),
    "fire_mage": ((30482, "-30s"),),
    "frost_death_knight": ((48265, "-20s"),),
    "fury_warrior": ((2458, "-160s"),),
    "marksmanship_hunter": ((13165, "-10s"),),
    "survival_hunter": ((13165, "-10s"),),
    "unholy_death_knight": ((48265, "-20s"),),
}

# The controlled live fixture provisions flask, food, and a two-use potion
# stack for every DPS spec. Profession and racial throughput actions remain
# disabled until their native runtime contracts exist.
APL_TRANSFORM_POLICY = {
    "schema": "phase8_forbidden_dynamic_actions_transform_v1",
    "policy": "recursive_remove_matching_action",
    "matching_semantics": "exact_native_field_and_canonical_full_payload",
    "combat_tree_policy": "preserve_allowed_nodes_and_order",
    "preserve_surviving_action_order": True,
    "forbidden_action_kinds": [],
    "forbidden_generic_operations": [
        {
            "semantic_name": "autocastOtherCooldowns",
            "native_field": "autocast_other_cooldowns",
        },
        {
            "semantic_name": "castAllStatBuffCooldowns",
            "native_field": "cast_all_stat_buff_cooldowns",
        },
        {
            "semantic_name": "activate_all_stat_buff_proc_auras",
            "native_field": "activate_all_stat_buff_proc_auras",
        },
        {"semantic_name": "item_swap", "native_field": "item_swap"},
        {"semantic_name": "activateAura", "native_field": "activate_aura"},
        {
            "semantic_name": "activateAuraWithStacks",
            "native_field": "activate_aura_with_stacks",
        },
        {"semantic_name": "triggerIcd", "native_field": "trigger_icd"},
        {"semantic_name": "cancelAura", "native_field": "cancel_aura"},
    ],
    "forbidden_state_mutation_instances": [
        {"native_field": "activate_aura", "spell_id": 1784},
        {"native_field": "activate_aura", "spell_id": 74221, "tag": 2},
        {
            "native_field": "activate_aura_with_stacks",
            "spell_id": 96929,
            "stacks": 5,
        },
        {"native_field": "trigger_icd", "spell_id": 97125},
        {"native_field": "cancel_aura", "spell_id": 45529},
    ],
    "unlisted_state_mutation_instance_policy": "reject",
    "forbidden_cast_spell_ids": [
        2825,  # Bloodlust / Heroism fixture external
        10060,  # Power Infusion fixture external
        20572,  # Blood Fury (attack power)
        26297,  # Berserking
        28730,  # Arcane Torrent
        33697,  # Blood Fury (spell power)
        33702,  # Blood Fury variant
        57933,  # Tricks of the Trade has no live friendly fixture target
        58984,  # Shadowmeld racial
        69041,  # Rocket Barrage
        82174,  # Synapse Springs item spell
    ],
    "forbidden_cast_item_ids": [
        36799,
        59461,
        62464,
        62469,
        68972,
        69002,
        69113,
        70142,
        77116,
    ],
    "allowed_cast_item_ids": [],
    "unlisted_cast_item_policy": "reject",
    "unknown_generic_operation_policy": "reject",
    "empty_node_policy": "remove_empty_sequence_or_strict_sequence_parent_recursively",
    "prepull_replacement_policy": {
        "mode": "replace_entire_source_with_fixture_exact_list",
        "source_prepull_policy": "record_and_remove_all",
        "replacement_source_field": "native_request.rotation_prepull_actions",
        "replacement_order_policy": "preserve_declared_order",
        "replacement_reason": "live_native_persistent_setup_then_resource_cooldown_clean_edge",
        "pet_or_option_setup_policy": "represent_at_start_and_do_not_recast",
        "source_provenance": "hash_bytes_count_and_action_identities",
    },
    "condition_rewrite_policy": {
        "schema": "phase8_exact_native_condition_payload_rewrite_v2",
        "authority": "materialized_live_fixture_absence",
        "matching_semantics": "canonical_full_native_payload_equality",
        "unavailable_condition_leaves": [
            {
                "native_field": "aura_is_active",
                "payloads": [
                    {"aura_id": {"item_id": 62464}},
                    {"aura_id": {"item_id": 69002}},
                    {"aura_id": {"item_id": 77116}},
                    {"aura_id": {"spell_id": 26297}},
                    {"aura_id": {"spell_id": 33697}},
                    {"aura_id": {"spell_id": 96229}},
                    {"aura_id": {"spell_id": 96929}},
                    {"aura_id": {"spell_id": 98971}},
                    {"aura_id": {"spell_id": 99049}},
                    {"aura_id": {"spell_id": 99234}},
                    {"aura_id": {"spell_id": 2825, "tag": -1}},
                    {
                        "aura_id": {"spell_id": 16511},
                        "source_unit": {"type": "CurrentTarget"},
                    },
                    {
                        "aura_id": {"spell_id": 29859},
                        "source_unit": {"type": "CurrentTarget"},
                    },
                    {
                        "aura_id": {"spell_id": 33876},
                        "source_unit": {"type": "CurrentTarget"},
                    },
                    {
                        "aura_id": {"spell_id": 57386},
                        "source_unit": {"type": "CurrentTarget"},
                    },
                ],
                "replacement": False,
            },
            {
                "native_field": "aura_is_known",
                "payloads": [
                    {"aura_id": {"item_id": 62464}},
                    {"aura_id": {"item_id": 69002}},
                    {"aura_id": {"item_id": 77114}},
                    {"aura_id": {"item_id": 77116}},
                    {"aura_id": {"spell_id": 26297}},
                    {"aura_id": {"spell_id": 96923}},
                    {"aura_id": {"spell_id": 99116}},
                    {"aura_id": {"spell_id": 107970}},
                    {"aura_id": {"spell_id": 109793}},
                ],
                "replacement": False,
            },
            {
                "native_field": "aura_remaining_time",
                "payloads": [
                    {"aura_id": {"spell_id": 26297}},
                    {"aura_id": {"spell_id": 96229}},
                    {"aura_id": {"spell_id": 96230}},
                    {"aura_id": {"spell_id": 109844}},
                    {"aura_id": {"spell_id": 2825, "tag": -1}},
                ],
                "replacement": 0,
                "replacement_type": "number",
            },
            {
                "native_field": "dot_is_active",
                "payloads": [{"spell_id": {"spell_id": 98957}}],
                "replacement": False,
            },
            {
                "native_field": "spell_time_to_ready",
                "payloads": [
                    {"spell_id": {"item_id": 62464}},
                    {"spell_id": {"item_id": 69002}},
                    {"spell_id": {"item_id": 77114}},
                    {"spell_id": {"item_id": 77116}},
                    {"spell_id": {"spell_id": 33697}},
                    {"spell_id": {"spell_id": 82174}},
                ],
                "replacement": 0,
                "replacement_type": "number",
            },
            {
                "native_field": "spell_is_ready",
                "payloads": [
                    {"spell_id": {"item_id": 68972}},
                    {"spell_id": {"item_id": 69113}},
                ],
                "replacement": False,
            },
            {
                "native_field": "spell_is_known",
                "payloads": [
                    {"spell_id": {"item_id": 68972}},
                    {"spell_id": {"item_id": 69113}},
                ],
                "replacement": False,
            },
        ],
        "forbidden_executable_cast_spell_ids": [57933, 58984],
        "unsupported_target_references": [
            {
                "type": "Target",
                "index": 1,
                "replacement": False,
                "row_policy": "remove_after_false_fold",
            }
        ],
        "preserved_target_references": [
            {"type": "Pet", "owner": "Self", "index": 1}
        ],
        "single_target_numeric_rewrites": [
            {
                "native_action_field": "multidot",
                "field": "max_dots",
                "source_value": 2,
                "replacement": 1,
            }
        ],
        "single_target_predicate_rewrites": [
            {
                "native_value_field": "number_targets",
                "operator": "OpEq",
                "constant": 2,
                "observed_target_count": 1,
                "replacement": False,
                "reason": "fixture_has_exactly_one_hostile_target",
            }
        ],
        "boolean_folding": "deterministic_recursive_not_and_or_constant_fold",
        "numeric_folding": "deterministic_recursive_arithmetic_and_comparison_constant_fold",
        "false_row_policy": "remove_action_row",
        "true_condition_policy": "remove_condition_field",
        "unknown_condition_leaf_policy": "reject",
        "unresolved_target_reference_policy": "reject",
        "compute_stats_warning_or_error_policy": "reject",
        "provenance_policy": "record_path_before_after_reason_and_hashes",
    },
    "provenance_policy": "hash_input_output_removed_and_added_actions",
}

POTION_ITEM_IDS = frozenset({58091, 58145, 58146})

REFERENCE_EXECUTION_POLICY = {
    "reaction_time_ms": 10,
    "channel_clip_delay_ms": 0,
    "in_front_of_target": False,
    "cooldowns": {},
    "bonus_stats": {"stats": [], "pseudo_stats": []},
    "healing_model": {},
    "database": {},
    "raid_topology": {
        "party_count": 1,
        "players_per_party": [1],
        "num_active_parties": 1,
        "tanks": [],
        "stagger_stormstrikes": False,
        "target_dummies": 0,
    },
    "target_flags": {
        "dual_wield": False,
        "dual_wield_penalty": False,
        "parry_haste": False,
        "suppress_dodge": False,
        "tank_index": -1,
        "second_tank_index": -1,
        "disabled_at_start": False,
        "target_inputs": [],
    },
}


class Phase8FixtureContractError(ValueError):
    pass


def canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise Phase8FixtureContractError(reason)


def _mapping_leaf_paths(value: Mapping[str, Any], prefix: str = "") -> list[str]:
    paths: list[str] = []
    for raw_key, child in value.items():
        key = str(raw_key)
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, Mapping):
            paths.extend(_mapping_leaf_paths(child, path))
        else:
            paths.append(path)
    return paths


def _simulator_option_leaf_classification(
    options: Mapping[str, Any],
) -> dict[str, Any]:
    leaves = sorted(_mapping_leaf_paths(options))
    atomic = {
        path: SIMULATOR_OPTION_ATOMIC_RUNTIME_REQUIREMENTS[path]
        for path in leaves
        if path in SIMULATOR_OPTION_ATOMIC_RUNTIME_REQUIREMENTS
    }
    reference = [
        path
        for path in leaves
        if path in SIMULATOR_OPTION_REFERENCE_EXECUTION_POLICY
    ]
    unclassified = [
        path for path in leaves if path not in atomic and path not in reference
    ]
    _require(not unclassified, "simulator_options:unclassified_leaf")
    return {
        "schema": "phase8_simulator_option_leaf_classification_v1",
        "atomic_runtime_requirements": atomic,
        "reference_execution_policy": reference,
        "unclassified": [],
    }


def _validate_power(row: Mapping[str, Any], *, label: str) -> None:
    power_type = int(row.get("power_type", -1))
    mode = str(row.get("mode") or "")
    _require(POWER_NAMES.get(power_type) == str(row.get("name") or ""), f"{label}:power_identity")
    _require(mode in {"exact", "maximum"}, f"{label}:power_mode")
    if mode == "exact":
        display = int(row.get("display_value", -1))
        native = int(row.get("native_value", -1))
        expected_native = display * 10 if power_type in {1, 6} else display
        _require(display >= 0 and native == expected_native, f"{label}:power_units")
    else:
        _require("display_value" not in row and "native_value" not in row, f"{label}:maximum_has_value")


def _native_player_spec(spec: str, row: Mapping[str, Any]) -> dict[str, Any]:
    options: dict[str, Any]
    if spec == "affliction_warlock":
        options = {"class_options": {"summon": 4, "detonate_seed": False}}
    elif spec == "demonology_warlock":
        options = {"class_options": {"summon": 5, "detonate_seed": False}}
    elif spec in {"arms_warrior", "fury_warrior"}:
        options = {"class_options": {"starting_rage": 0}}
    elif spec in {"assassination_rogue", "combat_rogue"}:
        options = {
            "class_options": {
                "mh_imbue": 2,
                "oh_imbue": 1,
                "th_imbue": 2,
                "starting_combo_points": 0,
            }
        }
    elif spec == "balance_druid":
        options = {"class_options": {}}
    elif spec == "feral_druid_dps":
        options = {"class_options": {}, "assume_bleed_active": False}
    elif spec == "elemental_shaman":
        standard_totems = {"earth": 2, "air": 3, "fire": 2, "water": 1}
        options = {
            "class_options": {
                "shield": 2,
                "imbue_mh": 2,
                "totems": {
                    "elements": standard_totems,
                    "ancestors": {"earth": 4, "fire": 4},
                    "spirits": standard_totems,
                    **standard_totems,
                },
            }
        }
    elif spec == "fire_mage":
        options = {"class_options": {}}
    elif spec == "frost_death_knight":
        options = {"class_options": {"starting_runic_power": 0}}
    elif spec == "unholy_death_knight":
        options = {"class_options": {"starting_runic_power": 100, "pet_uptime": 1.0}}
    elif spec in {"marksmanship_hunter", "survival_hunter"}:
        talents = row["pet_setup"]["talents"]
        options = {
            "class_options": {
                "pet_type": 31,
                "pet_talents": copy.deepcopy(talents),
                "pet_uptime": 1.0,
                "time_to_trap_weave_ms": 0,
            }
        }
        if spec == "survival_hunter":
            options["sniper_training_uptime"] = 1.0
    elif spec == "retribution_paladin":
        options = {
            "class_options": {"seal": 0, "aura": 1},
            "starting_holy_power": 0,
        }
    elif spec == "shadow_priest":
        options = {"class_options": {"armor": 1}}
    else:  # pragma: no cover - guarded by EXPECTED_SPECS
        raise Phase8FixtureContractError(f"{spec}:native_player_spec")
    return {"options": options}


def _target_catalog_rows(
    path: Path = DEFAULT_TARGET_CATALOG_PATH,
) -> tuple[dict[str, Mapping[str, Any]], str]:
    payload = path.read_bytes()
    document = json.loads(payload)
    rows = {
        str(row.get("spec_target_id") or ""): row
        for row in document.get("targets") or []
        if isinstance(row, Mapping)
    }
    return rows, hashlib.sha256(payload).hexdigest()


def _hunter_pet_projection(
    provisioning: Mapping[str, Any], pet_setup: Mapping[str, Any]
) -> dict[str, Any]:
    pet = provisioning.get("pet") or {}
    spellbook: list[dict[str, int]] = []
    for raw in pet.get("spells") or []:
        if isinstance(raw, int) and not isinstance(raw, bool):
            spellbook.append({"spell_id": raw, "active": 1})
        elif isinstance(raw, Mapping):
            spellbook.append(
                {"spell_id": int(raw["id"]), "active": int(raw.get("active", 1))}
            )
    spellbook.sort(key=lambda entry: (entry["spell_id"], entry["active"]))
    canonical = ";".join(
        f"{entry['spell_id']}:{entry['active']}" for entry in spellbook
    )
    return {
        "schema": "hunter_admission_pet_identity_v1",
        "required": True,
        "runtime_projection_complete": True,
        "pet_id": 8_700_000 + int(pet["id_offset"]),
        "creature_entry": int(pet["entry"]),
        "model_id": int(pet["modelid"]),
        "created_by_spell_id": int(pet["created_by_spell"]),
        "level": int(pet["level"]),
        "slot": int(pet["slot"]),
        "active": int(pet["active"]),
        "uptime": 1.0,
        "talents": copy.deepcopy(pet_setup["talents"]),
        "spellbook": spellbook,
        "spellbook_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "autocast_spell_ids": [23145, 53401, 53434],
        "power": {"power_type": 2, "mode": "maximum"},
    }


def _native_summoned_pet_projection(
    pet_setup: Mapping[str, Any], pet_power: Mapping[str, Any]
) -> dict[str, Any]:
    spellbook = [dict(row) for row in pet_setup.get("spellbook") or []]
    spellbook.sort(
        key=lambda row: (
            int(row.get("spell_id", 0)),
            int(row.get("active", 0)),
            int(row.get("type", 0)),
        )
    )
    canonical = ";".join(
        f"{int(row['spell_id'])}:{int(row['active'])}:{int(row['type'])}"
        for row in spellbook
    )
    spellbook_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    _require(
        spellbook_sha256 == pet_setup.get("spellbook_sha256"),
        "native_pet:spellbook_sha256",
    )
    autocasts = sorted({int(value) for value in pet_setup["required_autocast_spell_ids"]})
    return {
        "schema": "phase8_native_summoned_pet_identity_v1",
        "required": True,
        "runtime_projection_complete": True,
        "required_pet_spell_id": int(pet_setup["summon_spell_id"]),
        "required_pet_entry": int(pet_setup["creature_entry"]),
        "required_pet_family_id": int(pet_setup["family_id"]),
        "required_pet_created_by_spell_id": int(
            pet_setup["created_by_spell_id"]
        ),
        "required_pet_type": int(pet_setup["pet_type"]),
        "required_pet_power_type": int(pet_power["power_type"]),
        "pet_spell_known": True,
        "pet_native_cast_submitted": True,
        "pet_native_cast_finished": True,
        "pet_native_cast_observed": True,
        "pet_entry": int(pet_setup["creature_entry"]),
        "pet_family_id": int(pet_setup["family_id"]),
        "pet_created_by_spell_id": int(pet_setup["created_by_spell_id"]),
        "pet_present": True,
        "pet_in_world": True,
        "pet_alive": True,
        "pet_owned": True,
        "pet_permanent": True,
        "pet_type": int(pet_setup["pet_type"]),
        "pet_power_type": int(pet_power["power_type"]),
        "pet_spellbook_sha256": spellbook_sha256,
        "pet_spellbook": spellbook,
        "pet_autocast_spell_ids": autocasts,
        "uptime": float(pet_setup["uptime"]),
    }


def _survival_sniper_training_projection(
    provisioning: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive the native stationary buff from the pinned owned talent rank.

    Trinity's -53302 aura script selects 64418/64419/64420 using the
    learned talent SpellInfo rank.  The selected target owns rank 3 (53304),
    so the generated contract can bind 64420 without trusting a hand-copied
    runtime constant.
    """
    rank_to_buff = {53302: 64418, 53303: 64419, 53304: 64420}
    owned = [
        int(row.get("spell_id", 0))
        for row in provisioning.get("talents") or []
        if int(row.get("spell_id", 0)) in rank_to_buff
    ]
    _require(len(owned) == 1, "survival_hunter:sniper_training_owned_rank")
    talent_spell_id = owned[0]
    return {
        "authority": "trinity_spell_hun_sniper_training_owned_rank_v1",
        "talent_spell_id": talent_spell_id,
        "talent_rank": (53302, 53303, 53304).index(talent_spell_id) + 1,
        "observed_aura_spell_id": rank_to_buff[talent_spell_id],
        "required_at_scoring_start": True,
        "required_continuous_uptime": 1.0,
        "native_setup": "stationary_warmup_observation_only",
    }


def _glyph_identity(
    authority: Mapping[str, Any], glyph_item_ids: list[int]
) -> dict[str, list[int]]:
    item_to_property = authority["item_to_property"]
    property_to_aura = authority["property_to_aura"]
    def lookup(mapping: Mapping[Any, Any], key: int) -> Any:
        return mapping[key] if key in mapping else mapping[str(key)]

    try:
        property_ids = sorted(
            {
                int(lookup(item_to_property, int(item_id)))
                for item_id in glyph_item_ids
            }
        )
        aura_spell_ids = sorted(
            int(lookup(property_to_aura, property_id))
            for property_id in property_ids
        )
    except (KeyError, TypeError, ValueError):
        return {"property_ids": [], "aura_spell_ids": []}
    return {
        "property_ids": property_ids,
        "aura_spell_ids": aura_spell_ids,
    }


def _rotation_prepull_actions(spec: str) -> list[dict[str, Any]]:
    actions = [
        {
            "action": {
                "cast_spell": {"spell_id": {"spell_id": spell_id}}
            },
            "do_at_value": {"const": {"val": at_value}},
        }
        for spell_id, at_value in NATIVE_ROTATION_PREPULL_CASTS.get(spec, ())
    ]
    actions.append(
        {
            "action": {
                "cast_spell": {
                    "spell_id": {"other_id": "OtherActionPotion"}
                }
            },
            "do_at_value": {"const": {"val": "-1s"}},
        }
    )
    return actions


def _apl_transform_policy(
    consume_profile: Mapping[str, Any],
) -> dict[str, Any]:
    policy = copy.deepcopy(APL_TRANSFORM_POLICY)
    potion_item_id = int(consume_profile["combat_potion"]["item_id"])
    _require(potion_item_id in POTION_ITEM_IDS, "controlled_potion_item_id")
    policy["allowed_cast_item_ids"] = [potion_item_id]
    policy["forbidden_cast_item_ids"] = sorted(
        {
            int(value) for value in policy["forbidden_cast_item_ids"]
        }
        | (set(POTION_ITEM_IDS) - {potion_item_id})
    )
    return policy


def materialize_fixture_contract(
    raw_contract: Mapping[str, Any],
    *,
    authored_contract_bytes: bytes | None = None,
    target_catalog_path: Path = DEFAULT_TARGET_CATALOG_PATH,
) -> dict[str, Any]:
    """Add mechanically-derived native request and raw-runtime projections.

    The returned structure, rather than ad-hoc defaults in either engine, is
    the object content-addressed by :func:`load_fixture_contract`.
    """
    contract = copy.deepcopy(dict(raw_contract))
    self_provided = contract.get("reference_class") == "self_provided_baseline"
    target_catalog_path = target_catalog_path.resolve()
    target_rows, targets_sha256 = _target_catalog_rows(target_catalog_path)
    contract["authority"]["live_target_catalog_path"] = (
        "experiments/configs/all_spec_targets_cata_p4_v1.json"
    )
    contract["authority"]["live_target_catalog_sha256"] = targets_sha256
    reference = contract["reference_environment"]
    simulator_reference = reference["simulator_request_projection"]
    target = contract["target"]
    encounter = contract["encounter"]
    distances = contract["distance_contracts"]

    try:
        from .phase8_reference_conditions import glyph_translation_authority
    except ImportError:
        from tools.bot_ml.phase8_reference_conditions import (  # type: ignore[no-redef]
            glyph_translation_authority,
        )
    glyph_authority = glyph_translation_authority()
    selected_target_rows = {
        spec: copy.deepcopy(target_rows.get(spec) or {})
        for spec in sorted(contract["specs"])
    }
    contract["materialization"] = {
        "schema": "phase8_calibration_fixture_materialization_v1",
        "authored_contract": {
            "logical_path": (
                "experiments/configs/phase8_calibration_fixture_contract_v1.json"
            ),
            "sha256": hashlib.sha256(
                authored_contract_bytes
                if authored_contract_bytes is not None
                else json.dumps(
                    raw_contract, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest(),
        },
        "live_target_catalog": {
            "logical_path": (
                "experiments/configs/all_spec_targets_cata_p4_v1.json"
            ),
            "sha256": targets_sha256,
            "selected_rows": selected_target_rows,
        },
        "glyph_translation_authority": copy.deepcopy(glyph_authority),
    }

    for spec, row in contract["specs"].items():
        target_row = target_rows.get(spec) or {}
        provisioning = target_row.get("provisioning_bot") or {}
        consume_profile = provisioning.get("controlled_consumable_profile")
        _require(
            spec in CONTROLLED_DPS_SPECS and isinstance(consume_profile, Mapping),
            f"{spec}:controlled_consumable_profile_missing",
        )
        validate_controlled_consumable_profile(spec, consume_profile)
        glyph_item_ids = list(provisioning.get("glyphs") or [])
        glyph_identity = _glyph_identity(glyph_authority, glyph_item_ids)
        prepull = row["prepull_setup"]
        prepull["flask"] = {
            "item_id": int(consume_profile["flask"]["item_id"]),
            "item_spell_id": int(
                consume_profile["flask"]["item_spell_id"]
            ),
            "observed_aura_spell_id": int(
                consume_profile["flask"]["observed_aura_spell_id"]
            ),
        }
        prepull["food"] = {
            "item_id": int(consume_profile["food"]["item_id"]),
            "item_spell_id": int(
                consume_profile["food"]["item_spell_id"]
            ),
            "observed_aura_spell_id": int(
                consume_profile["food"]["observed_aura_spell_id"]
            ),
        }
        prepull["prepot"] = {
            "item_id": int(consume_profile["prepot"]["item_id"]),
            "item_spell_id": int(
                consume_profile["prepot"]["item_spell_id"]
            ),
            "observed_aura_spell_id": int(
                consume_profile["prepot"]["observed_aura_spell_id"]
            ),
        }
        prepull["combat_potion"] = {
            "item_id": int(consume_profile["combat_potion"]["item_id"]),
            "item_spell_id": int(
                consume_profile["combat_potion"]["item_spell_id"]
            ),
            "observed_aura_spell_id": int(
                consume_profile["combat_potion"]["observed_aura_spell_id"]
            ),
        }
        prepull["form_presence"]["required_aura_spell_ids"] = sorted(
            {
                int(spell_id)
                for spell_id in prepull["form_presence"][
                    "required_aura_spell_ids"
                ]
            }
        )
        if spec == "survival_hunter":
            sniper_training = _survival_sniper_training_projection(
                provisioning
            )
            required_auras = prepull["form_presence"][
                "required_aura_spell_ids"
            ]
            required_auras.append(
                int(sniper_training["observed_aura_spell_id"])
            )
            required_auras.sort()
            prepull["sniper_training"] = sniper_training
        lane = row["lane"]
        shadow_external = reference["shadow_priest_external_windows"]
        disabled_external_spell_ids = reference[
            "disabled_external_observation_spell_ids"
        ]
        external_windows = {
            "schema": "phase8_external_windows_v1",
            "heroism": {
                "source_count": 0,
                "spell_id": 2825,
                "windows_ms": copy.deepcopy(reference["heroism_windows_ms"]),
            },
            "power_infusion": {
                "source_count": 0,
                "spell_id": int(shadow_external["power_infusion_spell_id"]),
                "windows_ms": [],
            },
            "dark_intent_proc": {
                "base_spell_id": int(
                    shadow_external["dark_intent_base_spell_id"]
                ),
                "base_enabled": False,
                "proc_spell_id": int(
                    disabled_external_spell_ids["dark_intent_proc"]
                ),
                "uptime_pct": int(
                    shadow_external["dark_intent_proc_uptime_pct"]
                    if spec == "shadow_priest"
                    else 0
                )
            },
            "synapse_springs": {
                "spell_id": int(
                    disabled_external_spell_ids["synapse_springs"]
                ),
                "windows_ms": [],
            },
        }
        prepull["external_windows"] = copy.deepcopy(external_windows)

        raid_buffs = copy.deepcopy(simulator_reference["raid_buffs"])
        if not self_provided and spec != "retribution_paladin":
            raid_buffs["blessing_of_might"] = True
        individual_buffs = (
            {}
            if self_provided
            else copy.deepcopy(
                simulator_reference["individual_buffs_by_spec"].get(spec, {})
            )
        )
        native_consumables = {
            "prepot_id": int(prepull["prepot"]["item_id"]),
            "pot_id": int(prepull["combat_potion"]["item_id"]),
            "flask_id": int(prepull["flask"]["item_id"]),
            "battle_elixir_id": 0,
            "guardian_elixir_id": 0,
            "food_id": int(prepull["food"]["item_id"]),
            "explosive_id": 0,
            "conjured_id": 0,
            "tinker_id": int(prepull["tinker"]["item_id"]),
        }
        initial_state = {
            "authority": "phase8_fixture_explicit_reset_v1",
            "player_powers": copy.deepcopy(row["player_powers"]),
            "pet_power": copy.deepcopy(row.get("pet_power")),
            "runes_ready_mask": row.get("runes_ready_mask"),
            "combo_points": row.get("combo_points"),
            "required_absent_auras": copy.deepcopy(
                row.get("required_absent_auras", [])
            ),
            "persistent_setup_at_scoring_start": {
                "form_presence": copy.deepcopy(prepull["form_presence"]),
                "pet_setup": copy.deepcopy(row["pet_setup"]),
                "authority": "fixture_native_setup_then_resource_reset_v1",
            },
            "simulator_representation": {
                "maximum_resources": "pinned_engine_default_at_reset",
                "explicit_options": copy.deepcopy(
                    _native_player_spec(spec, row)["options"]
                ),
            },
        }
        native_request = {
            "player_spec_key": NATIVE_PLAYER_SPEC_KEYS[spec],
            "player_spec": _native_player_spec(spec, row),
            "race_id": int(prepull["racial"]["race_id"]),
            "professions": ["ProfessionUnknown", "ProfessionUnknown"],
            "player_fields": {
                "dark_intent_uptime": 0.0,
            },
            "glyph_item_ids": glyph_item_ids,
            "glyph_property_ids": glyph_identity["property_ids"],
            "glyph_aura_spell_ids": glyph_identity["aura_spell_ids"],
            "consumables": native_consumables,
            "raid_buffs": raid_buffs,
            "party_buffs": copy.deepcopy(simulator_reference["party_buffs"]),
            "individual_buffs": individual_buffs,
            "target_debuffs": copy.deepcopy(
                simulator_reference["target_debuffs"]
            ),
            "rotation_prepull_actions": _rotation_prepull_actions(spec),
            "apl_transform_policy": _apl_transform_policy(consume_profile),
            "reference_execution_policy": copy.deepcopy(
                REFERENCE_EXECUTION_POLICY
            ),
            "external_windows": copy.deepcopy(external_windows),
            "initial_state": initial_state,
        }
        row["native_request"] = native_request
        row["initial_state"] = copy.deepcopy(initial_state)
        row["simulator_option_leaf_classification"] = (
            _simulator_option_leaf_classification(row["simulator_options"])
        )

        pet_setup = row["pet_setup"]
        if spec in {"marksmanship_hunter", "survival_hunter"}:
            pet_runtime = _hunter_pet_projection(provisioning, pet_setup)
        elif pet_setup["required"]:
            pet_runtime = _native_summoned_pet_projection(
                pet_setup, row["pet_power"]
            )
        else:
            pet_runtime = {
                "schema": "phase8_absent_pet_at_scoring_start_v1",
                "required": False,
                "runtime_projection_complete": True,
                "present": False,
            }
        row["runtime_expected"] = {
            "item_swap": copy.deepcopy(row["item_swap"]),
            "flask": copy.deepcopy(prepull["flask"]),
            "food": copy.deepcopy(prepull["food"]),
            "prepot": {
                **copy.deepcopy(prepull["prepot"]),
                "use_count": 1,
            },
            "combat_potion": {
                **copy.deepcopy(prepull["combat_potion"]),
                "use_count": 1,
            },
            "tinker": {"item_id": 0, "use_count": 0},
            "racial": {**copy.deepcopy(prepull["racial"]), "use_count": 0},
            "raid_buffs": {
                "required_player_aura_spell_ids": copy.deepcopy(
                    [] if self_provided else reference["common_player_aura_spell_ids"]
                ),
                "mana_player_aura_spell_ids": copy.deepcopy(
                    reference["mana_player_aura_spell_ids"]
                    if not self_provided and spec in MANA_RESOURCE_SPECS
                    else []
                ),
                "primary_stat_aura_any_of_spell_ids": copy.deepcopy(
                    [] if self_provided else reference["primary_stat_aura_any_of_spell_ids"]
                ),
                "non_paladin_player_aura_spell_ids": copy.deepcopy(
                    reference["non_paladin_player_aura_spell_ids"]
                    if not self_provided and spec != "retribution_paladin"
                    else []
                ),
            },
            "target_debuffs": {
                "required_aura_spell_ids": copy.deepcopy(
                    [] if self_provided else reference["target_aura_spell_ids"]
                ),
                "required_stacked_auras": copy.deepcopy(
                    [] if self_provided else reference["target_stacked_auras"]
                ),
                **(
                    {"external_bleed_active": False}
                    if spec == "feral_druid_dps"
                    else {}
                ),
            },
            "heroism": {"windows_ms": copy.deepcopy(reference["heroism_windows_ms"])},
            "external_windows": copy.deepcopy(external_windows),
            "duration": {
                "duration_seconds": encounter["duration_seconds"],
                "duration_variation_seconds": encounter[
                    "duration_variation_seconds"
                ],
            },
            "execute": copy.deepcopy(encounter["execute_proportions"]),
            "fixture_target": copy.deepcopy(target),
            "target_distance": copy.deepcopy(distances[lane]),
            "initial_resources": copy.deepcopy(initial_state),
            "form_presence": copy.deepcopy(prepull["form_presence"]),
            "pet_setup": pet_runtime,
            "simulator_options": copy.deepcopy(row["simulator_options"]),
            "prepull_setup": copy.deepcopy(prepull),
        }
    return contract


def validate_fixture_contract(contract: Mapping[str, Any]) -> None:
    _require(contract.get("schema") == "phase8_calibration_fixture_contract_v1", "schema")
    _require(
        contract.get("reference_class") == "self_provided_baseline",
        "reference_class",
    )
    authority = contract.get("authority") or {}
    _require(
        authority.get("lifecycle_status") in LIFECYCLE_STATUSES,
        "authority:lifecycle_status",
    )
    _require(
        authority.get("promotion_requires_live_clean_state_receipt") is True,
        "authority:promotion_requires_live_clean_state_receipt",
    )
    _require(
        authority.get("promotion_receipt_contract")
        == {
            "owner": "phase8_raw_evidence_binding",
            "raw_path": "previous_window.bots[].pre_score_state",
            "projection_path": "runtime.pre_score_state_projection",
            "required": True,
        },
        "authority:promotion_receipt_contract",
    )
    _require(len(str(authority.get("revision") or "")) == 40, "authority_revision")
    _require(len(str(authority.get("default_target_source_sha256") or "")) == 64, "target_source_sha")
    materialization = contract.get("materialization") or {}
    _require(
        materialization.get("schema")
        == "phase8_calibration_fixture_materialization_v1",
        "materialization:schema",
    )
    authored_source = materialization.get("authored_contract") or {}
    _require(len(str(authored_source.get("sha256") or "")) == 64,
             "materialization:authored_sha")
    target_source = materialization.get("live_target_catalog") or {}
    _require(
        target_source.get("logical_path")
        == authority.get("live_target_catalog_path"),
        "materialization:target_path",
    )
    _require(
        target_source.get("sha256")
        == authority.get("live_target_catalog_sha256"),
        "materialization:target_sha",
    )
    target_rows = target_source.get("selected_rows") or {}
    _require(set(target_rows) == EXPECTED_SPECS,
             "materialization:target_rows")
    glyph_authority = materialization.get("glyph_translation_authority") or {}
    _require(
        glyph_authority.get("schema")
        == "trinity_cata_glyph_item_property_aura_v1",
        "materialization:glyph_schema",
    )
    _require(
        set((glyph_authority.get("source_file_sha256") or {}))
        == {"Item-sparse.db2", "SpellEffect.dbc", "GlyphProperties.dbc"},
        "materialization:glyph_sources",
    )
    for digest in (glyph_authority.get("source_file_sha256") or {}).values():
        _require(len(str(digest)) == 64, "materialization:glyph_source_sha")

    target = contract.get("target") or {}
    expected_target = {
        "entry": 44548,
        "level": 88,
        "armor": 11977,
        "creature_type": 9,
        "simulator_mob_type": 7,
        "live_max_health": 1_000_000_000,
    }
    for key, value in expected_target.items():
        _require(target.get(key) == value, f"target_{key}")
    _require(target.get("live_target_attacks") is False, "target_must_be_passive")
    for key in (
        "simulator_attack_power",
        "simulator_swing_speed_seconds",
        "simulator_min_base_damage",
        "simulator_damage_spread",
    ):
        _require(float(target.get(key, -1)) == 0.0, f"passive_{key}")

    encounter = contract.get("encounter") or {}
    _require(encounter.get("duration_seconds") == 300, "duration")
    _require(encounter.get("duration_variation_seconds") == 0, "duration_variation")
    windows = list(encounter.get("health_windows") or [])
    _require(len(windows) == 5, "health_window_count")
    previous_end = 0
    for index, row in enumerate(windows):
        _require(int(row.get("start_ms", -1)) == previous_end, f"health_window_{index}_start")
        previous_end = int(row.get("end_ms", -1))
        _require(
            int(row.get("lower_pct", -1)) < int(row.get("target_health_pct", -1))
            <= int(row.get("upper_pct", -1)),
            f"health_window_{index}_band",
        )
    _require(previous_end == 300_000, "health_window_duration")
    proportions = encounter.get("execute_proportions") or {}
    for threshold in (90, 35, 25, 20):
        start = next(int(row["start_ms"]) for row in windows if int(row["upper_pct"]) == threshold)
        observed = (300_000 - start) / 300_000
        _require(abs(observed - float(proportions[str(threshold)])) < 1e-12, f"execute_{threshold}")
    narrowest_margin = min(
        int(row["target_health_pct"]) - int(row["lower_pct"])
        for row in windows
        if int(row["lower_pct"]) > 0
    )
    _require(
        int(target["live_max_health"]) * narrowest_margin // 100 >= 20_000_000,
        "inter_reset_health_margin",
    )

    distances = contract.get("distance_contracts") or {}
    expected_distance_lanes = {
        "melee": 2.0,
        "short_ranged": 8.0,
        "ranged": 15.0,
    }
    _require(set(distances) == set(expected_distance_lanes), "distance_lanes")
    for lane, simulator_yards in expected_distance_lanes.items():
        row = distances[lane]
        _require(float(row.get("simulator_yards", -1)) == simulator_yards, f"{lane}_sim_distance")
        _require(
            float(row.get("runtime_min_yards", -1)) <= simulator_yards
            <= float(row.get("runtime_max_yards", -1)),
            f"{lane}_runtime_distance",
        )

    reference_environment = contract.get("reference_environment") or {}
    projection = reference_environment.get("simulator_request_projection") or {}
    for key in (
        "inherit_full_raid_buffs",
        "inherit_full_party_buffs",
        "inherit_full_individual_buffs",
        "inherit_full_target_debuffs",
    ):
        _require(projection.get(key) is False, f"reference_environment:{key}")
    _require(bool(projection.get("raid_buffs")), "reference_environment:raid_buffs")
    _require(projection.get("party_buffs") == {}, "reference_environment:party_buffs")
    _require(bool(projection.get("target_debuffs")), "reference_environment:target_debuffs")
    _require(
        not any(bool(value) for value in projection["raid_buffs"].values()),
        "reference_environment:external_raid_buff_enabled",
    )
    _require(
        projection.get("individual_buffs") == {}
        and projection.get("individual_buffs_by_spec") == {},
        "reference_environment:external_individual_buff_enabled",
    )
    _require(
        not any(bool(value) for value in projection["target_debuffs"].values()),
        "reference_environment:target_debuff_enabled",
    )
    _require(reference_environment.get("heroism_windows_ms") == [], "reference_environment:heroism")
    shadow_external = reference_environment.get("shadow_priest_external_windows") or {}
    _require(
        reference_environment.get("disabled_external_observation_spell_ids")
        == {"dark_intent_proc": 85759, "synapse_springs": 96230},
        "reference_environment:disabled_external_spell_ids",
    )
    _require(shadow_external.get("dark_intent_proc_uptime_pct") == 0, "reference_environment:dark_intent_proc")
    _require(shadow_external.get("dark_intent_base_enabled") is False, "reference_environment:dark_intent_base")
    _require(shadow_external.get("power_infusion_source_count") == 0, "reference_environment:power_infusion_sources")
    _require(
        shadow_external.get("power_infusion_windows_ms") == [],
        "reference_environment:power_infusion_windows",
    )
    _require("synapse_springs_spell_id" not in shadow_external, "reference_environment:synapse_spell")
    _require("synapse_springs_windows_ms" not in shadow_external, "reference_environment:synapse_windows")

    specs = contract.get("specs") or {}
    _require(set(specs) == EXPECTED_SPECS, "spec_set")
    for spec, row in specs.items():
        lane = str(row.get("lane") or "")
        _require(lane in distances, f"{spec}:lane")
        simulator_options = row.get("simulator_options") or {}
        _require(
            row.get("simulator_option_leaf_classification")
            == _simulator_option_leaf_classification(simulator_options),
            f"{spec}:simulator_option_leaf_classification",
        )
        _require(simulator_options.get("target_auto_attacks") is False, f"{spec}:target_auto_attacks")
        _require(
            float(simulator_options.get("starting_distance_yards", -1))
            == float(distances[lane]["simulator_yards"]),
            f"{spec}:starting_distance",
        )
        _require(isinstance(simulator_options.get("class_options"), Mapping), f"{spec}:class_options")
        if spec == "feral_druid_dps":
            _require(
                simulator_options["class_options"].get(
                    "assume_external_bleed_active"
                ) is False,
                "feral_druid_dps:external_bleed_disabled",
            )
        if spec == "survival_hunter":
            sniper = (row.get("prepull_setup") or {}).get(
                "sniper_training"
            ) or {}
            _require(
                simulator_options["class_options"].get(
                    "sniper_training_uptime"
                ) == 1.0,
                "survival_hunter:sniper_training_uptime",
            )
            _require(
                sniper.get("talent_spell_id") == 53304
                and sniper.get("talent_rank") == 3
                and sniper.get("observed_aura_spell_id") == 64420
                and sniper.get("required_at_scoring_start") is True
                and sniper.get("required_continuous_uptime") == 1.0
                and 64420
                in (row.get("prepull_setup") or {})
                .get("form_presence", {})
                .get("required_aura_spell_ids", []),
                "survival_hunter:sniper_training_runtime_contract",
            )

        pet_setup = row.get("pet_setup") or {}
        _require(isinstance(pet_setup.get("required"), bool), f"{spec}:pet_required")
        _require(isinstance(pet_setup.get("kind"), str), f"{spec}:pet_kind")
        _require(isinstance(pet_setup.get("required_autocast_spell_ids"), list), f"{spec}:pet_autocast")
        if pet_setup["required"]:
            _require(int(pet_setup.get("creature_entry", 0)) > 0, f"{spec}:pet_entry")
            _require(float(pet_setup.get("uptime", 0)) > 0, f"{spec}:pet_uptime")
            _require(row.get("pet_power") is not None, f"{spec}:pet_power_contract")
        else:
            _require(pet_setup.get("kind") == "none", f"{spec}:unexpected_pet_kind")

        prepull_setup = row.get("prepull_setup") or {}
        required_prepull_keys = {
            "flask",
            "food",
            "prepot",
            "combat_potion",
            "tinker",
            "racial",
            "raid_buffs",
            "target_debuffs",
            "heroism",
            "external_windows",
            "form_presence",
            "item_swap",
        }
        _require(required_prepull_keys.issubset(prepull_setup), f"{spec}:prepull_keys")
        for key in ("flask", "food", "prepot", "combat_potion", "tinker"):
            _require(int((prepull_setup.get(key) or {}).get("item_id", -1)) >= 0, f"{spec}:{key}")
        for key in ("prepot", "combat_potion"):
            _require(int(prepull_setup[key]["item_id"]) > 0, f"{spec}:{key}_required")
        _require(int(prepull_setup["tinker"]["item_id"]) == 0, f"{spec}:tinker_must_be_disabled")
        _require(isinstance((prepull_setup.get("racial") or {}).get("race"), str), f"{spec}:race")
        _require(int((prepull_setup.get("racial") or {}).get("spell_id", -1)) == 0, f"{spec}:racial_disabled")
        live_provisioning = (target_rows.get(spec) or {}).get("provisioning_bot") or {}
        _require(
            int((prepull_setup.get("racial") or {}).get("race_id", -1))
            == int(live_provisioning.get("race", -2)),
            f"{spec}:live_race",
        )
        _require((prepull_setup.get("raid_buffs") or {}).get("authority") == "reference_environment", f"{spec}:raid_buffs")
        _require((prepull_setup.get("target_debuffs") or {}).get("authority") == "reference_environment", f"{spec}:target_debuffs")
        _require((prepull_setup.get("heroism") or {}).get("authority") == "reference_environment", f"{spec}:heroism")
        _require(isinstance((prepull_setup.get("form_presence") or {}).get("required_aura_spell_ids"), list), f"{spec}:form_presence")

        item_swap = row.get("item_swap") or {}
        _require(item_swap == {"enabled": False, "items": []}, f"{spec}:item_swap")
        _require(prepull_setup.get("item_swap") == item_swap, f"{spec}:prepull_item_swap")
        _require("consumables" not in prepull_setup, f"{spec}:aggregate_consumables_forbidden")
        native_request = row.get("native_request") or {}
        _require(
            set(native_request)
            == {
                "player_spec_key",
                "player_spec",
                "race_id",
                "professions",
                "player_fields",
                "glyph_item_ids",
                "glyph_property_ids",
                "glyph_aura_spell_ids",
                "consumables",
                "raid_buffs",
                "party_buffs",
                "individual_buffs",
                "target_debuffs",
                "rotation_prepull_actions",
                "apl_transform_policy",
                "reference_execution_policy",
                "external_windows",
                "initial_state",
            },
            f"{spec}:native_request_keys",
        )
        _require(
            native_request.get("player_spec_key")
            == NATIVE_PLAYER_SPEC_KEYS[spec],
            f"{spec}:native_player_spec_key",
        )
        _require(
            native_request.get("race_id") == prepull_setup["racial"]["race_id"],
            f"{spec}:native_race",
        )
        _require(
            native_request.get("professions")
            == ["ProfessionUnknown", "ProfessionUnknown"],
            f"{spec}:native_professions",
        )
        _require(
            {
                "property_ids": native_request.get("glyph_property_ids"),
                "aura_spell_ids": native_request.get("glyph_aura_spell_ids"),
            }
            == _glyph_identity(
                glyph_authority,
                list(native_request.get("glyph_item_ids") or []),
            ),
            f"{spec}:native_glyph_identity",
        )
        _require(
            native_request.get("player_fields")
            == {"dark_intent_uptime": 0.0},
            f"{spec}:native_player_fields",
        )
        _require(
            native_request.get("rotation_prepull_actions")
            == _rotation_prepull_actions(spec),
            f"{spec}:native_rotation_prepull",
        )
        _require(
            native_request.get("apl_transform_policy")
            == _apl_transform_policy(
                (live_provisioning.get("controlled_consumable_profile") or {})
            ),
            f"{spec}:native_apl_transform_policy",
        )
        _require(
            native_request.get("reference_execution_policy")
            == REFERENCE_EXECUTION_POLICY,
            f"{spec}:native_reference_execution_policy",
        )
        _require(
            native_request.get("external_windows")
            == prepull_setup.get("external_windows"),
            f"{spec}:native_external_windows",
        )
        consumes = native_request.get("consumables") or {}
        _require(
            int(consumes.get("prepot_id", 0))
            == int(prepull_setup["prepot"]["item_id"]),
            f"{spec}:native_prepot_id",
        )
        _require(
            int(consumes.get("pot_id", 0))
            == int(prepull_setup["combat_potion"]["item_id"]),
            f"{spec}:native_pot_id",
        )
        for key in ("tinker_id", "explosive_id", "conjured_id"):
            _require(int(consumes.get(key, -1)) == 0, f"{spec}:native_{key}")
        _require(row.get("initial_state") == native_request.get("initial_state"), f"{spec}:initial_state")
        runtime_expected = row.get("runtime_expected") or {}
        _require(
            {
                "item_swap",
                "flask",
                "food",
                "prepot",
                "combat_potion",
                "tinker",
                "racial",
                "raid_buffs",
                "target_debuffs",
                "heroism",
                "external_windows",
                "duration",
                "execute",
                "fixture_target",
                "target_distance",
                "initial_resources",
                "form_presence",
                "pet_setup",
                "simulator_options",
                "prepull_setup",
            }
            == set(runtime_expected),
            f"{spec}:runtime_expected_keys",
        )
        _require(
            len(str(row.get("source_test_sha256") or "")) == 64,
            f"{spec}:source_sha",
        )
        powers = list(row.get("player_powers") or [])
        _require(bool(powers), f"{spec}:player_power_missing")
        for index, power in enumerate(powers):
            _validate_power(power, label=f"{spec}:player:{index}")
        pet_power = row.get("pet_power")
        if pet_power is not None:
            _validate_power(pet_power, label=f"{spec}:pet")
        if "runes_ready_mask" in row:
            _require(int(row["runes_ready_mask"]) == 63, f"{spec}:runes")
        if "combo_points" in row:
            _require(int(row["combo_points"]) == 0, f"{spec}:combo_points")
        if "required_absent_auras" in row:
            _require(row["required_absent_auras"] == [48517, 48518], f"{spec}:absent_auras")


def canonical_materialized_bytes(contract: Mapping[str, Any]) -> bytes:
    return json.dumps(
        contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def build_materialized_fixture_contract(
    authored_path: Path = DEFAULT_AUTHORED_CONTRACT_PATH,
    *,
    target_catalog_path: Path = DEFAULT_TARGET_CATALOG_PATH,
) -> dict[str, Any]:
    authored_bytes = authored_path.read_bytes()
    contract = materialize_fixture_contract(
        json.loads(authored_bytes),
        authored_contract_bytes=authored_bytes,
        target_catalog_path=target_catalog_path,
    )
    validate_fixture_contract(contract)
    return contract


def load_materialized_fixture_contract(
    path: Path = DEFAULT_CONTRACT_PATH,
) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    contract = json.loads(payload)
    validate_fixture_contract(contract)
    _require(payload == canonical_materialized_bytes(contract),
             "materialized_contract_not_canonical_bytes")
    return contract, hashlib.sha256(payload).hexdigest()


def load_fixture_contract(
    path: Path = DEFAULT_CONTRACT_PATH,
) -> tuple[dict[str, Any], str]:
    """Backward-compatible name for strict materialized-byte consumption."""
    return load_materialized_fixture_contract(path)


def _cpp_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def render_generated_header(contract: Mapping[str, Any], content_sha256: str) -> str:
    target = contract["target"]
    encounter = contract["encounter"]
    distances = contract["distance_contracts"]
    specs = contract["specs"]
    power_rows: list[tuple[str, str, Mapping[str, Any]]] = []
    setup_aura_rows: list[tuple[str, int]] = []
    spec_rows: list[dict[str, Any]] = []
    for spec in sorted(specs):
        row = specs[spec]
        offset = len(power_rows)
        power_rows.extend((spec, "player", power) for power in row["player_powers"])
        if row.get("pet_power") is not None:
            power_rows.append((spec, "pet", row["pet_power"]))
        setup_aura_offset = len(setup_aura_rows)
        setup_aura_rows.extend(
            (spec, int(spell_id))
            for spell_id in row["prepull_setup"]["form_presence"][
                "required_aura_spell_ids"
            ]
        )
        spec_rows.append(
            {
                "spec": spec,
                "lane": row["lane"],
                "source_sha": row["source_test_sha256"],
                "offset": offset,
                "count": len(power_rows) - offset,
                "runes": int(row.get("runes_ready_mask", 0)),
                "combo": int(row.get("combo_points", 255)),
                "neutral_eclipse": row.get("required_absent_auras") == [48517, 48518],
                "pet_required": row.get("pet_power") is not None,
                "setup_aura_offset": setup_aura_offset,
                "setup_aura_count": len(setup_aura_rows) - setup_aura_offset,
                "flask_aura": int(
                    row["prepull_setup"]["flask"]["observed_aura_spell_id"]
                ),
                "flask_item_spell": int(
                    row["prepull_setup"]["flask"]["item_spell_id"]
                ),
                "flask_item": int(
                    row["prepull_setup"]["flask"]["item_id"]
                ),
                "food_aura": int(
                    row["prepull_setup"]["food"]["observed_aura_spell_id"]
                ),
                "food_item_spell": int(
                    row["prepull_setup"]["food"]["item_spell_id"]
                ),
                "food_item": int(
                    row["prepull_setup"]["food"]["item_id"]
                ),
                "prepot_item": int(
                    row["prepull_setup"]["prepot"]["item_id"]
                ),
                "prepot_item_spell": int(
                    row["prepull_setup"]["prepot"]["item_spell_id"]
                ),
                "prepot_aura": int(
                    row["prepull_setup"]["prepot"]["observed_aura_spell_id"]
                ),
                "combat_potion_item": int(
                    row["prepull_setup"]["combat_potion"]["item_id"]
                ),
                "combat_potion_item_spell": int(
                    row["prepull_setup"]["combat_potion"]["item_spell_id"]
                ),
                "combat_potion_aura": int(
                    row["prepull_setup"]["combat_potion"]["observed_aura_spell_id"]
                ),
                "pet_runtime_projection_complete": bool(
                    row["runtime_expected"]["pet_setup"][
                        "runtime_projection_complete"
                    ]
                ),
                "runtime_min_distance": float(
                    distances[row["lane"]]["runtime_min_yards"]
                ),
                "runtime_max_distance": float(
                    distances[row["lane"]]["runtime_max_yards"]
                ),
            }
        )

    lines = [
        "// Generated by tools/bot_ml/phase8_fixture_contract.py. Do not edit.",
        "#ifndef BOT_CALIBRATION_FIXTURE_CONTRACT_GENERATED_H",
        "#define BOT_CALIBRATION_FIXTURE_CONTRACT_GENERATED_H",
        "",
        "#include <array>",
        "#include <cstdint>",
        "#include <string_view>",
        "",
        "namespace BotCalibrationFixtureContractGenerated",
        "{",
        f"inline constexpr char Schema[] = {_cpp_string(contract['schema'])};",
        f"inline constexpr char ReferenceClass[] = {_cpp_string(contract['reference_class'])};",
        f"inline constexpr char ContentSha256[] = {_cpp_string(content_sha256)};",
        f"inline constexpr char UpstreamRevision[] = {_cpp_string(contract['authority']['revision'])};",
        f"inline constexpr uint32_t TargetEntry = {int(target['entry'])};",
        f"inline constexpr uint8_t TargetLevel = {int(target['level'])};",
        f"inline constexpr uint32_t TargetArmor = {int(target['armor'])};",
        f"inline constexpr uint32_t TargetCreatureType = {int(target['creature_type'])};",
        f"inline constexpr uint32_t TargetMaxHealth = {int(target['live_max_health'])};",
        f"inline constexpr uint32_t DurationMs = {int(encounter['duration_seconds']) * 1000};",
        f"inline constexpr float MeleeDistanceYards = {float(distances['melee']['simulator_yards']):.1f}f;",
        f"inline constexpr float RangedDistanceYards = {float(distances['ranged']['simulator_yards']):.1f}f;",
        "",
        "struct PowerContract",
        "{",
        "    char const* Spec;",
        "    char const* UnitKind;",
        "    char const* Name;",
        "    uint8_t PowerType;",
        "    bool Maximum;",
        "    uint32_t ExactNativeValue;",
        "};",
        "",
        "struct SpecContract",
        "{",
        "    char const* Spec;",
        "    char const* Lane;",
        "    char const* SourceTestSha256;",
        "    uint16_t PowerOffset;",
        "    uint8_t PowerCount;",
        "    uint8_t RunesReadyMask;",
        "    uint8_t ComboPoints;",
        "    bool NeutralEclipse;",
        "    bool PetResourceRequired;",
        "    uint16_t SetupAuraOffset;",
        "    uint8_t SetupAuraCount;",
        "    uint32_t FlaskItemId;",
        "    uint32_t FlaskItemSpellId;",
        "    uint32_t FlaskAuraSpellId;",
        "    uint32_t FoodItemId;",
        "    uint32_t FoodItemSpellId;",
        "    uint32_t FoodAuraSpellId;",
        "    uint32_t PrepotItemId;",
        "    uint32_t PrepotItemSpellId;",
        "    uint32_t PrepotAuraSpellId;",
        "    uint32_t CombatPotionItemId;",
        "    uint32_t CombatPotionItemSpellId;",
        "    uint32_t CombatPotionAuraSpellId;",
        "    bool PetRuntimeProjectionComplete;",
        "    float RuntimeMinimumDistanceYards;",
        "    float RuntimeMaximumDistanceYards;",
        "};",
        "",
        f"inline constexpr std::array<PowerContract, {len(power_rows)}> PowerContracts = {{{{",
    ]
    for spec, unit_kind, row in power_rows:
        lines.append(
            "    { "
            f"{_cpp_string(spec)}, {_cpp_string(unit_kind)}, {_cpp_string(row['name'])}, "
            f"{int(row['power_type'])}, {'true' if row['mode'] == 'maximum' else 'false'}, "
            f"{int(row.get('native_value', 0))} }} ,"
        )
    lines.extend(
        [
            "}};",
            "",
            f"inline constexpr std::array<uint32_t, {len(setup_aura_rows)}> RequiredSetupAuraSpellIds = {{{{",
        ]
    )
    for _spec, spell_id in setup_aura_rows:
        lines.append(f"    {spell_id},")
    lines.extend(
        [
            "}};",
            "",
            f"inline constexpr std::array<SpecContract, {len(spec_rows)}> SpecContracts = {{{{",
        ]
    )
    for row in spec_rows:
        lines.append(
            "    { "
            f"{_cpp_string(row['spec'])}, {_cpp_string(row['lane'])}, {_cpp_string(row['source_sha'])}, "
            f"{row['offset']}, {row['count']}, {row['runes']}, {row['combo']}, "
            f"{'true' if row['neutral_eclipse'] else 'false'}, "
            f"{'true' if row['pet_required'] else 'false'}, "
            f"{row['setup_aura_offset']}, {row['setup_aura_count']}, "
            f"{row['flask_item']}, {row['flask_item_spell']}, {row['flask_aura']}, "
            f"{row['food_item']}, {row['food_item_spell']}, {row['food_aura']}, "
            f"{row['prepot_item']}, {row['prepot_item_spell']}, {row['prepot_aura']}, "
            f"{row['combat_potion_item']}, {row['combat_potion_item_spell']}, "
            f"{row['combat_potion_aura']}, "
            f"{'true' if row['pet_runtime_projection_complete'] else 'false'}, "
            f"{row['runtime_min_distance']:.1f}f, "
            f"{row['runtime_max_distance']:.1f}f }} ,"
        )
    lines.extend(
        [
            "}};",
            "",
            "inline SpecContract const* FindSpec(std::string_view spec)",
            "{",
            "    for (SpecContract const& row : SpecContracts)",
            "        if (spec == row.Spec)",
            "            return &row;",
            "    return nullptr;",
            "}",
            "}",
            "",
            "#endif",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument(
        "--authored-contract", type=Path,
        default=DEFAULT_AUTHORED_CONTRACT_PATH,
    )
    parser.add_argument(
        "--target-catalog", type=Path,
        default=DEFAULT_TARGET_CATALOG_PATH,
    )
    parser.add_argument("--header", type=Path, default=DEFAULT_HEADER_PATH)
    parser.add_argument("--write-materialized", action="store_true")
    parser.add_argument("--check-materialized", action="store_true")
    parser.add_argument("--write-header", action="store_true")
    parser.add_argument("--check-header", action="store_true")
    args = parser.parse_args()
    if args.write_materialized or args.check_materialized:
        materialized = build_materialized_fixture_contract(
            args.authored_contract,
            target_catalog_path=args.target_catalog,
        )
        expected_payload = canonical_materialized_bytes(materialized)
        if args.write_materialized:
            args.contract.write_bytes(expected_payload)
        if args.check_materialized:
            _require(args.contract.is_file(), "materialized_contract_missing")
            _require(
                args.contract.read_bytes() == expected_payload,
                "materialized_contract_stale",
            )
    contract, digest = load_fixture_contract(args.contract)
    rendered = render_generated_header(contract, digest)
    if args.write_header:
        args.header.write_text(rendered, encoding="utf-8")
    if args.check_header:
        _require(args.header.is_file(), "generated_header_missing")
        _require(args.header.read_text(encoding="utf-8") == rendered, "generated_header_stale")
    print(json.dumps({"ok": True, "content_sha256": digest, "spec_count": len(contract["specs"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
