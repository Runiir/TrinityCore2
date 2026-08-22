"""Derive Phase 8 WoWSims comparability from raw server reference facts."""

from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE_REQUESTS = (
    REPO_ROOT
    / "experiments/configs/wowsims_cata_dps_reference_requests_v1.json"
)
REFERENCE_REQUEST_SCHEMA = "wowsims_cata_dps_reference_requests_v1"


EXPECTED_REFERENCE_CONDITIONS = {
    "level": 85,
    "raid_buffs": "full_simulator_reference_live_conditions_recorded_separately",
    "consumables": "simulator_enabled_live_clone_capabilities_recorded",
    "aoe": "separate_mode_not_mixed_with_single_target",
}

MANA_SPECS = frozenset(
    {
        "affliction_warlock",
        "arcane_mage",
        "balance_druid",
        "demonology_warlock",
        "destruction_warlock",
        "discipline_priest",
        "elemental_shaman",
        "enhancement_shaman",
        "fire_mage",
        "frost_mage",
        "holy_paladin",
        "holy_priest",
        "protection_paladin",
        "restoration_druid",
        "restoration_shaman",
        "retribution_paladin",
        "shadow_priest",
    }
)

PALADIN_SPECS = frozenset(
    {"holy_paladin", "protection_paladin", "retribution_paladin"}
)

INTELLECT_FLASK_SPECS = frozenset(
    {
        "affliction_warlock",
        "arcane_mage",
        "balance_druid",
        "demonology_warlock",
        "destruction_warlock",
        "discipline_priest",
        "elemental_shaman",
        "fire_mage",
        "frost_mage",
        "holy_paladin",
        "holy_priest",
        "restoration_druid",
        "restoration_shaman",
        "shadow_priest",
    }
)

AGILITY_FLASK_SPECS = frozenset(
    {
        "assassination_rogue",
        "beast_mastery_hunter",
        "combat_rogue",
        "enhancement_shaman",
        "feral_druid_dps",
        "feral_druid_tank",
        "marksmanship_hunter",
        "subtlety_rogue",
        "survival_hunter",
    }
)

STRENGTH_FLASK_SPECS = frozenset(
    {
        "arms_warrior",
        "blood_death_knight",
        "frost_death_knight",
        "fury_warrior",
        "protection_paladin",
        "protection_warrior",
        "retribution_paladin",
        "unholy_death_knight",
    }
)

SUPPORTED_REFERENCE_SPECS = frozenset(
    MANA_SPECS | AGILITY_FLASK_SPECS | STRENGTH_FLASK_SPECS
)

BASE_BUFF_AURAS = (
    "53646",  # Demonic Pact
    "79058",  # Arcane Brilliance
    "24932",  # Leader of the Pack
    "2895",   # Wrath of Air
    "8515",   # Windfury
    "8076",   # Strength of Earth
    "82930",  # Arcane Tactics
    "kings_or_mark",
)

RAID_REQUIRED_PLAYER_AURA_IDS = (53646, 79058, 24932, 2895, 8515, 8076, 82930)
PRIMARY_STAT_AURA_IDS = (20217, 79063, 1126, 79061)
REPLENISHMENT_AURA_ID = 57669
NON_PALADIN_MIGHT_AURA_ID = 79102
FLASK_ITEM_BY_AURA = {79470: 58086, 79471: 58087, 79472: 58088}
FOOD_ITEMS_BY_AURA = {
    87545: frozenset({62670}),
    87546: frozenset({62669}),
    87547: frozenset({62290, 62671}),
}
RACE_NAME_BY_ID = {
    1: "human",
    2: "orc",
    3: "dwarf",
    4: "night_elf",
    8: "troll",
    11: "draenei",
}
REQUIRED_TARGET_DEBUFF_AURA_IDS = (1490, 22959, 81326)
SUNDER_ARMOR_AURA_ID = 58567
EXTERNAL_BLEED_AURA_IDS = (16511, 33876, 46857)

COMPARISON_MANIFEST_SCHEMA = "phase8_wowsims_reference_setup_manifest_v1"
ACCEPTABLE_RESULT_STATUSES = frozenset(
    {"generated_verified"}
)
REQUIRED_CONDITION_CLASSES = frozenset(
    {
        "gear_source_manifest",
        "race",
        "talents_glyphs",
        "consumes_prepot_tinker_racial",
        "buffs_debuffs",
        "duration_execute",
        "form_presence_pet",
    }
)
REQUIRED_REQUIREMENT_CLASSES = {
    "gear_manifest": "gear_source_manifest",
    "item_swap": "gear_source_manifest",
    "race": "race",
    "talents": "talents_glyphs",
    "glyphs": "talents_glyphs",
    "flask": "consumes_prepot_tinker_racial",
    "food": "consumes_prepot_tinker_racial",
    "prepot": "consumes_prepot_tinker_racial",
    "combat_potion": "consumes_prepot_tinker_racial",
    "tinker": "consumes_prepot_tinker_racial",
    "racial": "consumes_prepot_tinker_racial",
    "raid_buffs": "buffs_debuffs",
    "target_debuffs": "buffs_debuffs",
    "heroism": "buffs_debuffs",
    "duration": "duration_execute",
    "execute": "duration_execute",
    "fixture_target": "duration_execute",
    "target_distance": "duration_execute",
    "initial_resources": "form_presence_pet",
    "form_presence": "form_presence_pet",
    "pet_setup": "form_presence_pet",
    "prepull_setup": "consumes_prepot_tinker_racial",
}
REQUIRED_RUNTIME_PATH_PREFIXES = {
    "gear_manifest": ("runtime.reference_gear_manifest_sha256",),
    "item_swap": ("runtime.item_swap_projection",),
    "race": ("target.race_id",),
    "talents": ("target.active_talent_spell_ids",),
    "glyphs": ("runtime.glyph_identity",),
    "flask": ("runtime.flask_projection",),
    "food": ("runtime.food_projection",),
    "prepot": ("runtime.prepot_projection",),
    "combat_potion": ("runtime.combat_potion_projection",),
    "tinker": ("runtime.tinker_projection",),
    "racial": ("runtime.racial_projection",),
    "raid_buffs": ("runtime.raid_buffs_projection",),
    "target_debuffs": ("runtime.target_debuffs_projection",),
    "heroism": ("runtime.heroism_projection",),
    "duration": ("runtime.duration_projection",),
    "execute": ("runtime.execute_projection",),
    "fixture_target": ("runtime.fixture_target_projection",),
    "target_distance": ("runtime.target_distance_projection",),
    "initial_resources": ("runtime.initial_resources_projection",),
    "form_presence": ("runtime.prepull_setup_projection.form_presence",),
    "pet_setup": ("runtime.pet_setup_projection",),
    "prepull_setup": ("runtime.prepull_setup_projection",),
}
REQUIRED_SOURCE_SETUP_KEYS = frozenset(
    {
        "race",
        "gear",
        "talents",
        "glyphs",
        "consumes",
        "spec_options",
        "rotation",
        "raid_buffs",
        "target_debuffs",
        "target_distance_yards",
        "encounter",
    }
)
_ALLOWED_FACT_ROOTS = frozenset(
    {"calibration", "normalization", "reference_setup", "runtime", "target"}
)
_ALLOWED_PLANNED_ROOTS = frozenset({"fixture", "reference", "target"})
MAX_RUNTIME_OBSERVATION_GAP_MS = 2_000
MIN_FULL_WINDOW_OBSERVATION_SAMPLES = 151

# Simulator options are request semantics, not an opaque live observation.
# Every leaf must either name an independently observed runtime fact or remain
# part of the content-addressed reference execution policy.  In particular,
# this table must never be used to synthesize ``runtime.*_projection`` values.
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
SIMULATOR_OPTION_REFERENCE_EXECUTION_POLICY = frozenset(
    {
        "class_options.detonate_seed",
        "class_options.thrown_poison",
        "class_options.time_to_trap_weave_ms",
        "class_options.totems.air",
        "class_options.totems.earth",
        "class_options.totems.fire",
        "class_options.totems.fire_elemental",
        "class_options.totems.water",
    }
)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _full_window_sampling_valid(
    *, sample_count: Any, maximum_gap_ms: Any, duration_ms: int = 300_000
) -> bool:
    """Check that an aggregate cadence can mathematically span both edges."""
    if type(sample_count) is not int or type(maximum_gap_ms) is not int:
        return False
    return bool(
        sample_count >= MIN_FULL_WINDOW_OBSERVATION_SAMPLES
        and 0 < maximum_gap_ms <= MAX_RUNTIME_OBSERVATION_GAP_MS
        and (sample_count - 1) * maximum_gap_ms >= duration_ms
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def classify_simulator_option_leaves(options: Any) -> dict[str, Any]:
    """Classify native simulator-option leaves without fabricating live facts.

    Atomic entries point at the existing independently reconstructed runtime
    requirement.  Strategy-only entries remain covered by the byte-exact
    request/result execution policy.  Any new leaf is intentionally a static
    preflight blocker until it receives an explicit classification.
    """
    row = options if isinstance(options, Mapping) else {}
    leaves = sorted(_mapping_leaf_paths(row))
    atomic = {
        path: SIMULATOR_OPTION_ATOMIC_RUNTIME_REQUIREMENTS[path]
        for path in leaves
        if path in SIMULATOR_OPTION_ATOMIC_RUNTIME_REQUIREMENTS
    }
    reference_policy = [
        path
        for path in leaves
        if path in SIMULATOR_OPTION_REFERENCE_EXECUTION_POLICY
    ]
    classified = set(atomic) | set(reference_policy)
    unclassified = [path for path in leaves if path not in classified]
    valid = bool(
        isinstance(options, Mapping)
        and set(row) == {
            "class_options",
            "starting_distance_yards",
            "target_auto_attacks",
        }
        and isinstance(row.get("class_options"), Mapping)
        and not unclassified
        and len(classified) == len(leaves)
    )
    return {
        "schema": "phase8_simulator_option_leaf_classification_v1",
        "valid": valid,
        "atomic_runtime_requirements": atomic,
        "reference_execution_policy": reference_policy,
        "unclassified": unclassified,
    }


@lru_cache(maxsize=1)
def glyph_translation_authority() -> dict[str, Any]:
    """Reconstruct the item -> property -> aura bridge from pinned local DBC."""
    try:
        from .build_validation_provisioning import (
            DEFAULT_DBC_DIR,
            glyph_item_to_property_map,
            load_wdbc_values,
        )
    except ImportError:
        from build_validation_provisioning import (  # type: ignore[no-redef]
            DEFAULT_DBC_DIR,
            glyph_item_to_property_map,
            load_wdbc_values,
        )

    dbc_dir = DEFAULT_DBC_DIR.resolve()
    source_files = {
        name: _file_sha256(dbc_dir / name)
        for name in ("Item-sparse.db2", "SpellEffect.dbc", "GlyphProperties.dbc")
    }
    property_to_aura = {
        int(row[0]): int(row[1])
        for row in load_wdbc_values(dbc_dir / "GlyphProperties.dbc", "niii")
    }
    return {
        "schema": "trinity_cata_glyph_item_property_aura_v1",
        "source_file_sha256": source_files,
        "item_to_property": glyph_item_to_property_map(dbc_dir),
        "property_to_aura": property_to_aura,
    }


def expected_glyph_runtime_identity(glyph_item_ids: Any) -> dict[str, list[int]]:
    item_ids = glyph_item_ids if isinstance(glyph_item_ids, list) else []
    authority = glyph_translation_authority()
    item_to_property = authority["item_to_property"]
    property_to_aura = authority["property_to_aura"]
    try:
        property_ids = sorted({item_to_property[int(item_id)] for item_id in item_ids})
        aura_spell_ids = sorted(
            property_to_aura[property_id] for property_id in property_ids
        )
    except (KeyError, TypeError, ValueError):
        return {"property_ids": [], "aura_spell_ids": []}
    return {
        "property_ids": property_ids,
        "aura_spell_ids": aura_spell_ids,
    }


def _glyph_requirement_translation_valid(requirements: list[Any]) -> bool:
    glyph_rows = [
        row
        for row in requirements
        if isinstance(row, Mapping) and row.get("id") == "glyphs"
    ]
    if len(glyph_rows) != 1:
        return False
    row = glyph_rows[0]
    authority = glyph_translation_authority()
    declared_authority = row.get("translation_authority")
    expected_authority = {
        "schema": authority["schema"],
        "source_file_sha256": authority["source_file_sha256"],
    }
    return bool(
        declared_authority == expected_authority
        and row.get("equals")
        == expected_glyph_runtime_identity(row.get("planned_equals"))
        and row.get("equals", {}).get("property_ids")
    )


def observed_gear_manifest_sha256(target_observation: Any) -> str:
    """Hash the canonical equipped manifest directly from raw target facts."""
    target = target_observation if isinstance(target_observation, Mapping) else {}
    gear = target.get("gear_profile_observation")
    gear = gear if isinstance(gear, Mapping) else {}
    items = gear.get("items")
    if not isinstance(items, list):
        return ""
    rows: list[dict[str, Any]] = []
    slots: set[int] = set()
    for item in items:
        if not isinstance(item, Mapping):
            return ""
        try:
            slot = int(item.get("slot", -1))
            item_id = int(item.get("item_id") or 0)
            gems = [int(value or 0) for value in item.get("gem_item_ids") or []]
            enchant_id = int(item.get("enchant_id") or 0)
            reforge_id = int(item.get("reforge_id") or 0)
        except (TypeError, ValueError):
            return ""
        if slot < 0 or slot > 18 or slot in slots or item_id <= 0:
            return ""
        slots.add(slot)
        while gems and gems[-1] == 0:
            gems.pop()
        rows.append(
            {
                "slot": slot,
                "item_id": item_id,
                "enchant_id": enchant_id,
                "reforge_id": reforge_id,
                "gem_item_ids": gems,
            }
        )
    return _canonical_sha256(sorted(rows, key=lambda row: row["slot"])) if rows else ""


def _fact_at_path(
    facts: Mapping[str, Any], path: str, *, allowed_roots: frozenset[str] = _ALLOWED_FACT_ROOTS
) -> tuple[bool, Any]:
    parts = path.split(".")
    if not parts or parts[0] not in allowed_roots:
        return False, None
    value: Any = facts
    for part in parts:
        if not isinstance(value, Mapping) or part not in value:
            return False, None
        value = value[part]
    return True, value


def _positive_numbers_equal(left: Any, right: Any) -> bool:
    try:
        return float(left) > 0.0 and float(left) == float(right)
    except (TypeError, ValueError):
        return False


def _numbers_equal(left: Any, right: Any) -> bool:
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return False


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


_EXPECTED_EXECUTE_WINDOWS = (
    ("above_90", 0, 30_000, 95, 90, False, 100, True),
    ("between_35_90", 30_000, 195_000, 50, 35, False, 90, True),
    ("between_25_35", 195_000, 225_000, 30, 25, False, 35, True),
    ("between_20_25", 225_000, 240_000, 22, 20, False, 25, True),
    ("below_20", 240_000, 300_000, 19, 0, True, 20, False),
)


def _health_within_bounds(
    health: int,
    maximum_health: int,
    *,
    lower: int,
    lower_inclusive: bool,
    upper: int,
    upper_inclusive: bool,
) -> bool:
    if health <= 0 or maximum_health <= 0 or health > maximum_health:
        return False
    lower_comparison = health * 100 - lower * maximum_health
    upper_comparison = health * 100 - upper * maximum_health
    return (
        lower_comparison >= 0 if lower_inclusive else lower_comparison > 0
    ) and (
        upper_comparison <= 0 if upper_inclusive else upper_comparison < 0
    )


def execute_schedule_projection(value: Any) -> tuple[dict[str, Any], bool]:
    """Project deterministic execute settings and validate their raw samples."""
    schedule = value if isinstance(value, Mapping) else {}
    windows = schedule.get("windows")
    windows = windows if isinstance(windows, list) else []
    projection: dict[str, Any] = {
        "schema": schedule.get("schema"),
        "source_authority": schedule.get("source_authority"),
        "source_duration_ms": schedule.get("source_duration_ms"),
        "source_duration_variation_ms": schedule.get(
            "source_duration_variation_ms"
        ),
        "source_execute_proportions": schedule.get(
            "source_execute_proportions"
        ),
        "interval_semantics": schedule.get("interval_semantics"),
        "fixture_only": schedule.get("fixture_only"),
        "non_certifying": schedule.get("non_certifying"),
        "windows": [],
    }
    valid = bool(
        schedule.get("schema")
        == "wowsims_cata_single_target_health_schedule_v1"
        and schedule.get("source_authority")
        == "pinned_wowsims_cata_core_test_utils_make_single_target_encounter"
        and schedule.get("source_duration_ms") == 300_000
        and schedule.get("source_duration_variation_ms") == 0
        and schedule.get("source_execute_proportions")
        == {"90": 0.9, "35": 0.35, "25": 0.25, "20": 0.2}
        and schedule.get("interval_semantics")
        == "start_inclusive_end_exclusive"
        and schedule.get("fixture_only") is True
        and schedule.get("non_certifying") is True
        and len(windows) == len(_EXPECTED_EXECUTE_WINDOWS)
    )
    fields = (
        "phase",
        "start_ms",
        "end_ms",
        "configured_target_health_pct",
        "health_pct_lower_bound",
        "lower_bound_inclusive",
        "health_pct_upper_bound",
        "upper_bound_inclusive",
    )
    for index, expected in enumerate(_EXPECTED_EXECUTE_WINDOWS):
        row = windows[index] if index < len(windows) else {}
        row = row if isinstance(row, Mapping) else {}
        projected_row = {field: row.get(field) for field in fields}
        projection["windows"].append(projected_row)
        valid = valid and tuple(projected_row.values()) == expected
        observation = row.get("observation")
        observation = observation if isinstance(observation, Mapping) else {}
        sample_count = _integer(observation.get("sample_count"))
        first_elapsed_ms = _integer(observation.get("first_elapsed_ms"))
        last_elapsed_ms = _integer(observation.get("last_elapsed_ms"))
        minimum_health = _integer(observation.get("minimum_observed_health"))
        maximum_health = _integer(observation.get("maximum_observed_health"))
        minimum_max_health = _integer(
            observation.get("minimum_observed_max_health")
        )
        maximum_max_health = _integer(
            observation.get("maximum_observed_max_health")
        )
        damage_event_sample_count = _integer(
            observation.get("damage_event_sample_count")
        )
        first_damage_event_elapsed_ms = _integer(
            observation.get("first_damage_event_elapsed_ms")
        )
        last_damage_event_elapsed_ms = _integer(
            observation.get("last_damage_event_elapsed_ms")
        )
        minimum_pre_damage_health = _integer(
            observation.get("minimum_pre_damage_health")
        )
        maximum_pre_damage_health = _integer(
            observation.get("maximum_pre_damage_health")
        )
        minimum_projected_post_damage_health = _integer(
            observation.get("minimum_projected_post_damage_health")
        )
        maximum_projected_post_damage_health = _integer(
            observation.get("maximum_projected_post_damage_health")
        )
        minimum_damage_event_max_health = _integer(
            observation.get("minimum_damage_event_max_health")
        )
        maximum_damage_event_max_health = _integer(
            observation.get("maximum_damage_event_max_health")
        )
        maximum_damage_event = _integer(observation.get("maximum_damage_event"))
        start_ms, end_ms = expected[1], expected[2]
        lower, lower_inclusive = expected[4], expected[5]
        upper, upper_inclusive = expected[6], expected[7]
        exact_configured_health = max(
            1, maximum_max_health * expected[3] // 100
        )
        valid = valid and bool(
            sample_count > 0
            and start_ms <= first_elapsed_ms <= last_elapsed_ms < end_ms
            and minimum_max_health == 1_000_000_000
            and minimum_max_health == maximum_max_health
            and minimum_health == exact_configured_health
            and maximum_health == exact_configured_health
            and _health_within_bounds(
                minimum_health,
                minimum_max_health,
                lower=lower,
                lower_inclusive=lower_inclusive,
                upper=upper,
                upper_inclusive=upper_inclusive,
            )
            and _health_within_bounds(
                maximum_health,
                maximum_max_health,
                lower=lower,
                lower_inclusive=lower_inclusive,
                upper=upper,
                upper_inclusive=upper_inclusive,
            )
            and damage_event_sample_count > 0
            and start_ms
            <= first_damage_event_elapsed_ms
            <= last_damage_event_elapsed_ms
            < end_ms
            and minimum_damage_event_max_health == 1_000_000_000
            and minimum_damage_event_max_health
            == maximum_damage_event_max_health
            and 0 < minimum_pre_damage_health <= maximum_pre_damage_health
            <= maximum_damage_event_max_health
            and 0
            < minimum_projected_post_damage_health
            <= maximum_projected_post_damage_health
            <= maximum_pre_damage_health
            and minimum_projected_post_damage_health
            <= minimum_pre_damage_health
            and 0 < maximum_damage_event <= maximum_damage_event_max_health
            and _health_within_bounds(
                minimum_pre_damage_health,
                minimum_damage_event_max_health,
                lower=lower,
                lower_inclusive=lower_inclusive,
                upper=upper,
                upper_inclusive=upper_inclusive,
            )
            and _health_within_bounds(
                maximum_pre_damage_health,
                maximum_damage_event_max_health,
                lower=lower,
                lower_inclusive=lower_inclusive,
                upper=upper,
                upper_inclusive=upper_inclusive,
            )
            and _health_within_bounds(
                minimum_projected_post_damage_health,
                minimum_damage_event_max_health,
                lower=lower,
                lower_inclusive=lower_inclusive,
                upper=upper,
                upper_inclusive=upper_inclusive,
            )
            and _health_within_bounds(
                maximum_projected_post_damage_health,
                maximum_damage_event_max_health,
                lower=lower,
                lower_inclusive=lower_inclusive,
                upper=upper,
                upper_inclusive=upper_inclusive,
            )
            and (
                minimum_projected_post_damage_health * 100
                >= lower * minimum_damage_event_max_health
                if lower_inclusive
                else minimum_projected_post_damage_health * 100
                > lower * minimum_damage_event_max_health
            )
        )
    return projection, valid


def _receipt_timestamps_valid(
    *, submitted_at_ms: Any, observed_at_ms: Any, scored_started_at_ms: Any
) -> bool:
    submitted = _integer(submitted_at_ms)
    observed = _integer(observed_at_ms)
    scored = _integer(scored_started_at_ms)
    return bool(0 < submitted <= observed <= scored)


def pet_setup_projection(
    target_observation: Any,
    *,
    expected: Any = None,
    scored_started_at_ms: Any,
    scored_ended_at_ms: Any,
) -> tuple[dict[str, Any], bool]:
    target = target_observation if isinstance(target_observation, Mapping) else {}
    setup = target.get("persistent_setup")
    setup = setup if isinstance(setup, Mapping) else {}
    target_guid = _integer(target.get("guid"))
    started_at_ms = _integer(scored_started_at_ms)
    ended_at_ms = _integer(scored_ended_at_ms)
    observation_ticks = _integer(setup.get("pet_observation_ticks"))
    ready_ticks = _integer(setup.get("pet_ready_ticks"))
    expected_row = expected if isinstance(expected, Mapping) else {}
    continuity_fields_exact = all(
        type(setup.get(key)) is int
        for key in (
            "pet_observed_owner_guid",
            "pet_observation_window_started_at_ms",
            "pet_observation_window_ended_at_ms",
            "pet_first_observation_at_ms",
            "pet_last_observation_at_ms",
            "pet_first_observed_guid",
            "pet_last_observed_guid",
            "pet_guid_mismatch_sample_count",
            "pet_identity_mismatch_sample_count",
            "pet_ready_ticks",
            "pet_observation_ticks",
            "pet_maximum_observation_gap_ms",
        )
    )
    observation_window_valid = bool(
        continuity_fields_exact
        and target_guid > 0
        and _integer(setup.get("pet_observed_owner_guid")) == target_guid
        and started_at_ms > 0
        and ended_at_ms - started_at_ms == 300_000
        and _integer(setup.get("pet_observation_window_started_at_ms"))
        == started_at_ms
        and _integer(setup.get("pet_observation_window_ended_at_ms"))
        == ended_at_ms
        and _integer(setup.get("pet_first_observation_at_ms"))
        == started_at_ms
        and _integer(setup.get("pet_last_observation_at_ms"))
        == ended_at_ms
        and _full_window_sampling_valid(
            sample_count=observation_ticks,
            maximum_gap_ms=setup.get("pet_maximum_observation_gap_ms"),
        )
        and ready_ticks == observation_ticks
        and _integer(setup.get("pet_identity_mismatch_sample_count")) == 0
    )
    if expected_row.get("schema") == "hunter_admission_pet_identity_v1":
        raw_admission_spellbook = setup.get("pet_admission_spellbook")
        raw_admission_spellbook = (
            raw_admission_spellbook
            if isinstance(raw_admission_spellbook, list)
            else []
        )
        admission_spellbook: list[dict[str, int]] = []
        admission_spellbook_valid = True
        for row in raw_admission_spellbook:
            if not isinstance(row, Mapping):
                admission_spellbook_valid = False
                continue
            admission_spellbook.append(
                {
                    "spell_id": _integer(row.get("spell_id")),
                    "active": _integer(row.get("active")),
                }
            )
        admission_canonical = ";".join(
            f"{row['spell_id']}:{row['active']}"
            for row in admission_spellbook
        )
        admission_sha256 = hashlib.sha256(
            admission_canonical.encode("utf-8")
        ).hexdigest()
        raw_full_spellbook = setup.get("pet_spellbook")
        raw_full_spellbook = (
            raw_full_spellbook if isinstance(raw_full_spellbook, list) else []
        )
        full_spellbook: list[dict[str, int]] = []
        full_spellbook_valid = True
        for row in raw_full_spellbook:
            if not isinstance(row, Mapping):
                full_spellbook_valid = False
                continue
            full_spellbook.append(
                {
                    "spell_id": _integer(row.get("spell_id")),
                    "active": _integer(row.get("active")),
                    "type": _integer(row.get("type")),
                }
            )
        full_canonical = ";".join(
            f"{row['spell_id']}:{row['active']}:{row['type']}"
            for row in full_spellbook
        )
        full_sha256 = hashlib.sha256(full_canonical.encode("utf-8")).hexdigest()
        raw_autocasts = setup.get("pet_autocast_spell_ids")
        raw_autocasts = raw_autocasts if isinstance(raw_autocasts, list) else []
        autocasts = [_integer(value) for value in raw_autocasts]
        try:
            uptime = float(setup.get("pet_uptime_ratio"))
        except (TypeError, ValueError):
            uptime = -1.0
        projection = {
            "schema": "hunter_admission_pet_identity_v1",
            "required": True,
            "runtime_projection_complete": True,
            "pet_id": _integer(setup.get("pet_id")),
            "creature_entry": _integer(setup.get("pet_entry")),
            "uptime": uptime,
            "spellbook": admission_spellbook,
            "spellbook_sha256": setup.get("pet_admission_spellbook_sha256"),
            "autocast_spell_ids": autocasts,
            "power": {
                "power_type": _integer(setup.get("pet_power_type")),
                "mode": "maximum",
            },
        }
        valid = bool(
            observation_window_valid
            and _integer(setup.get("required_pet_spell_id")) == 0
            and _integer(setup.get("required_pet_entry")) == 0
            and _integer(setup.get("pet_guid")) > 0
            and _integer(setup.get("pet_first_observed_guid"))
            == _integer(setup.get("pet_guid"))
            and _integer(setup.get("pet_last_observed_guid"))
            == _integer(setup.get("pet_guid"))
            and _integer(setup.get("pet_guid_mismatch_sample_count")) == 0
            and projection["pet_id"] > 0
            and projection["creature_entry"] > 0
            and all(
                setup.get(key) is True
                for key in (
                    "pet_present",
                    "pet_in_world",
                    "pet_alive",
                    "pet_owned",
                    "pet_permanent",
                )
            )
            and _integer(setup.get("pet_type")) == 1
            and _integer(setup.get("pet_health")) > 0
            and _integer(setup.get("pet_max_health"))
            >= _integer(setup.get("pet_health"))
            and projection["power"]["power_type"] == 2
            and _integer(setup.get("pet_max_power")) > 0
            and 0
            <= _integer(setup.get("pet_power"))
            <= _integer(setup.get("pet_max_power"))
            and admission_spellbook_valid
            and bool(admission_spellbook)
            and admission_spellbook
            == sorted(
                admission_spellbook,
                key=lambda row: (row["spell_id"], row["active"]),
            )
            and all(row["spell_id"] > 0 for row in admission_spellbook)
            and _hex_sha256(projection["spellbook_sha256"])
            and projection["spellbook_sha256"] == admission_sha256
            and full_spellbook_valid
            and bool(full_spellbook)
            and full_spellbook
            == sorted(
                full_spellbook,
                key=lambda row: (row["spell_id"], row["active"], row["type"]),
            )
            and _hex_sha256(setup.get("pet_spellbook_sha256"))
            and setup.get("pet_spellbook_sha256") == full_sha256
            and autocasts == sorted(set(autocasts))
            and all(spell_id > 0 for spell_id in autocasts)
            and uptime == 1.0
            and projection == expected_row
        )
        return projection, valid
    required_spell_id = _integer(setup.get("required_pet_spell_id"))
    if required_spell_id <= 0:
        try:
            absent_uptime = float(setup.get("pet_uptime_ratio"))
        except (TypeError, ValueError):
            absent_uptime = -1.0
        projection = {
            "schema": "phase8_absent_pet_at_scoring_start_v1",
            "required": False,
            "runtime_projection_complete": True,
            "present": False,
        }
        return projection, bool(
            setup
            and observation_window_valid
            and setup.get("pet_present") is False
            and _integer(setup.get("pet_guid")) == 0
            and _integer(setup.get("pet_entry")) == 0
            and _integer(setup.get("pet_first_observed_guid")) == 0
            and _integer(setup.get("pet_last_observed_guid")) == 0
            and _integer(setup.get("pet_guid_mismatch_sample_count")) == 0
            and absent_uptime == 1.0
        )
    raw_spellbook = setup.get("pet_spellbook")
    raw_spellbook = raw_spellbook if isinstance(raw_spellbook, list) else []
    spellbook: list[dict[str, int]] = []
    spellbook_valid = True
    for row in raw_spellbook:
        if not isinstance(row, Mapping):
            spellbook_valid = False
            continue
        spellbook.append(
            {
                "spell_id": _integer(row.get("spell_id")),
                "active": _integer(row.get("active")),
                "type": _integer(row.get("type")),
            }
        )
    canonical_spellbook = ";".join(
        f"{row['spell_id']}:{row['active']}:{row['type']}" for row in spellbook
    )
    spellbook_sha256 = hashlib.sha256(
        canonical_spellbook.encode("utf-8")
    ).hexdigest()
    raw_autocasts = setup.get("pet_autocast_spell_ids")
    raw_autocasts = raw_autocasts if isinstance(raw_autocasts, list) else []
    autocasts = [_integer(value) for value in raw_autocasts]
    derived_uptime = (
        ready_ticks / observation_ticks
        if observation_ticks > 0
        else -1.0
    )
    try:
        serialized_uptime = float(setup.get("pet_uptime_ratio"))
    except (TypeError, ValueError):
        serialized_uptime = -1.0
    projection = {
        "schema": "phase8_native_summoned_pet_identity_v1",
        "required": True,
        "runtime_projection_complete": True,
        "required_pet_spell_id": required_spell_id,
        "required_pet_entry": _integer(setup.get("required_pet_entry")),
        "required_pet_family_id": _integer(setup.get("required_pet_family_id")),
        "required_pet_created_by_spell_id": _integer(
            setup.get("required_pet_created_by_spell_id")
            or required_spell_id
        ),
        "required_pet_type": _integer(setup.get("required_pet_type")),
        "required_pet_power_type": _integer(
            setup.get("required_pet_power_type")
        ),
        "pet_spell_known": setup.get("pet_spell_known"),
        "pet_native_cast_submitted": setup.get("pet_native_cast_submitted"),
        "pet_native_cast_finished": setup.get("pet_native_cast_finished"),
        "pet_native_cast_observed": setup.get("pet_native_cast_observed"),
        "pet_entry": _integer(setup.get("pet_entry")),
        "pet_family_id": _integer(setup.get("pet_family_id")),
        "pet_created_by_spell_id": _integer(
            setup.get("pet_created_by_spell_id")
        ),
        "pet_present": setup.get("pet_present"),
        "pet_in_world": setup.get("pet_in_world"),
        "pet_alive": setup.get("pet_alive"),
        "pet_owned": setup.get("pet_owned"),
        "pet_permanent": setup.get("pet_permanent"),
        "pet_type": _integer(setup.get("pet_type")),
        "pet_power_type": _integer(setup.get("pet_power_type")),
        "pet_spellbook_sha256": setup.get("pet_spellbook_sha256"),
        "pet_spellbook": spellbook,
        "pet_autocast_spell_ids": autocasts,
        "uptime": derived_uptime,
    }
    submitted_at = setup.get("pet_native_cast_submitted_at_ms")
    finished_at = _integer(setup.get("pet_native_cast_finished_at_ms"))
    observed_at = setup.get("pet_native_cast_observed_at_ms")
    valid = bool(
        setup.get("ready") is True
        and observation_window_valid
        and projection["required_pet_entry"] > 0
        and _integer(setup.get("pet_guid")) > 0
        and _integer(setup.get("pet_first_observed_guid"))
        == _integer(setup.get("pet_guid"))
        and _integer(setup.get("pet_last_observed_guid"))
        == _integer(setup.get("pet_guid"))
        and _integer(setup.get("pet_guid_mismatch_sample_count")) == 0
        and "required_pet_family_id" in setup
        and "required_pet_type" in setup
        and "required_pet_power_type" in setup
        and projection["pet_spell_known"] is True
        and projection["pet_native_cast_submitted"] is True
        and projection["pet_native_cast_finished"] is True
        and projection["pet_native_cast_observed"] is True
        and _receipt_timestamps_valid(
            submitted_at_ms=submitted_at,
            observed_at_ms=observed_at,
            scored_started_at_ms=scored_started_at_ms,
        )
        and _integer(submitted_at) <= finished_at <= _integer(observed_at)
        and projection["pet_entry"] == projection["required_pet_entry"]
        and projection["pet_family_id"] == projection["required_pet_family_id"]
        and projection["pet_created_by_spell_id"]
        == projection["required_pet_created_by_spell_id"]
        and all(
            projection[key] is True
            for key in (
                "pet_present",
                "pet_in_world",
                "pet_alive",
                "pet_owned",
                "pet_permanent",
            )
        )
        and projection["pet_type"] == projection["required_pet_type"]
        and projection["pet_power_type"]
        == projection["required_pet_power_type"]
        and _integer(setup.get("pet_health")) > 0
        and _integer(setup.get("pet_max_health"))
        >= _integer(setup.get("pet_health"))
        and _integer(setup.get("pet_max_power")) > 0
        and 0 <= _integer(setup.get("pet_power"))
        <= _integer(setup.get("pet_max_power"))
        and _hex_sha256(projection["pet_spellbook_sha256"])
        and projection["pet_spellbook_sha256"] == spellbook_sha256
        and spellbook_valid
        and bool(spellbook)
        and spellbook
        == sorted(
            spellbook,
            key=lambda row: (row["spell_id"], row["active"], row["type"]),
        )
        and all(row["spell_id"] > 0 for row in spellbook)
        and autocasts == sorted(set(autocasts))
        and all(spell_id > 0 for spell_id in autocasts)
        and derived_uptime == 1.0
        and abs(serialized_uptime - derived_uptime) <= 1e-9
    )
    return projection, valid


def prepull_setup_projection(
    target_observation: Any, *, scored_started_at_ms: Any
) -> tuple[dict[str, Any], bool]:
    target = target_observation if isinstance(target_observation, Mapping) else {}
    setup = target.get("persistent_setup")
    setup = setup if isinstance(setup, Mapping) else {}
    required_presence_spell_id = _integer(
        setup.get("required_presence_spell_id")
    )
    if required_presence_spell_id > 0:
        required_presence_aura_id = _integer(
            setup.get("required_presence_aura_id")
        )
        presence = {"required_aura_spell_ids": [required_presence_aura_id]}
        presence_valid = bool(
            required_presence_aura_id > 0
            and all(
                setup.get(key) is True
                for key in (
                    "presence_spell_known",
                    "presence_aura_active",
                    "presence_native_cast_submitted",
                    "presence_native_cast_observed",
                )
            )
            and _receipt_timestamps_valid(
                submitted_at_ms=setup.get("presence_native_cast_submitted_at_ms"),
                observed_at_ms=setup.get("presence_native_cast_observed_at_ms"),
                scored_started_at_ms=scored_started_at_ms,
            )
        )
    else:
        presence = {"required_aura_spell_ids": []}
        presence_valid = bool(setup)

    poison_required = setup.get("poison_setup_required") is True
    if poison_required:
        gear = target.get("gear_profile_observation")
        gear = gear if isinstance(gear, Mapping) else {}
        equipped_items = gear.get("items")
        equipped_items = equipped_items if isinstance(equipped_items, list) else []
        equipped_by_slot = {
            _integer(item.get("slot")): _integer(item.get("item_id"))
            for item in equipped_items
            if isinstance(item, Mapping)
        }
        raw_poisons = setup.get("poisons")
        raw_poisons = raw_poisons if isinstance(raw_poisons, Mapping) else {}
        weapon_imbues: list[dict[str, Any]] = []
        poison_valid = True
        for hand in ("mainhand", "offhand"):
            row = raw_poisons.get(hand)
            row = row if isinstance(row, Mapping) else {}
            required_item_entry = _integer(row.get("required_item_entry"))
            required_spell_id = _integer(row.get("required_spell_id"))
            required_enchant_id = _integer(row.get("required_enchant_id"))
            expected_equipment_slot = 15 if hand == "mainhand" else 16
            submitted_item_guid = _integer(row.get("submitted_item_guid"))
            submitted_weapon_guid = _integer(row.get("submitted_weapon_guid"))
            weapon_imbues.append(
                {
                    "slot": hand,
                    "item_id": required_item_entry,
                    "use_spell_id": required_spell_id,
                    "temp_enchant_id": required_enchant_id,
                }
            )
            poison_valid = poison_valid and bool(
                required_item_entry > 0
                and required_spell_id > 0
                and required_enchant_id > 0
                and _integer(row.get("equipment_slot"))
                == expected_equipment_slot
                and row.get("item_available") is True
                and row.get("spell_available") is True
                and row.get("native_use_submitted") is True
                and row.get("native_use_finished") is True
                and row.get("enchant_observed") is True
                and submitted_item_guid > 0
                and submitted_weapon_guid > 0
                and _integer(row.get("native_use_finished_item_guid"))
                == submitted_item_guid
                and _integer(row.get("native_use_finished_weapon_guid"))
                == submitted_weapon_guid
                and _integer(row.get("observed_weapon_guid"))
                == submitted_weapon_guid
                and _integer(row.get("observed_weapon_item_entry"))
                == equipped_by_slot.get(expected_equipment_slot, 0)
                and _integer(row.get("observed_enchant_id"))
                == required_enchant_id
                and _integer(row.get("observed_enchant_duration_ms"))
                >= 900_000
                and _receipt_timestamps_valid(
                    submitted_at_ms=row.get("native_use_submitted_at_ms"),
                    observed_at_ms=row.get("enchant_observed_at_ms"),
                    scored_started_at_ms=scored_started_at_ms,
                )
                and _integer(row.get("native_use_submitted_at_ms"))
                <= _integer(row.get("native_use_finished_at_ms"))
                <= _integer(row.get("enchant_observed_at_ms"))
            )
    else:
        weapon_imbues = []
        poison_valid = bool(setup)
    projection: dict[str, Any] = {"form_presence": presence}
    if weapon_imbues:
        projection["weapon_imbues"] = weapon_imbues
    return projection, bool(setup.get("ready") is True and presence_valid and poison_valid)


def _continuous_aura_rows(
    value: Any,
    *,
    sample_count: int,
    target_guid: int | None = None,
) -> tuple[dict[int, Mapping[str, Any]], bool]:
    rows = value if isinstance(value, list) else []
    by_spell: dict[int, Mapping[str, Any]] = {}
    valid = isinstance(value, list)
    prior_spell_id = 0
    for row in rows:
        if not isinstance(row, Mapping):
            valid = False
            continue
        spell_id = _integer(row.get("spell_id"))
        active = row.get("active_samples")
        inactive = row.get("inactive_samples")
        valid = bool(
            valid
            and spell_id > prior_spell_id
            and type(active) is int
            and type(inactive) is int
            and active >= 0
            and inactive >= 0
            and active + inactive == sample_count
        )
        if target_guid is not None:
            caster_guid = _integer(row.get("caster_guid"))
            owner_match_samples = _integer(row.get("owner_match_samples"))
            owner_mismatch_samples = _integer(
                row.get("owner_mismatch_samples")
            )
            valid = bool(
                valid
                and type(row.get("caster_guid")) is int
                and type(row.get("owner_match_samples")) is int
                and type(row.get("owner_mismatch_samples")) is int
                and owner_mismatch_samples == 0
                and (
                    (
                        active == 0
                        and caster_guid == 0
                        and owner_match_samples == 0
                    )
                    or (
                        active > 0
                        and caster_guid == target_guid
                        and owner_match_samples == active
                    )
                )
            )
        if spell_id in by_spell:
            valid = False
        by_spell[spell_id] = row
        prior_spell_id = spell_id
    return by_spell, valid


def _reconcile_legacy_tinker_use_count(
    dynamic: Mapping[str, Any],
) -> tuple[int, bool]:
    """Remove independently attributed item uses from the legacy aggregate.

    Older reference telemetry puts ``ScoredTinkerOrOtherItemUseCount`` and
    ``ScoredTinkerSpellUseCount`` in one ``tinker_use_count`` field.  Newer
    payloads also retain the per-item rows needed to identify the ordinary
    item-use portion.  Reconcile that portion only when every row and count
    agrees.  An absent pair keeps the legacy behavior; a partial or malformed
    pair fails closed and leaves the aggregate untouched.
    """
    raw_count = dynamic.get("tinker_use_count")
    if type(raw_count) is not int or raw_count < 0:
        return _integer(raw_count), False

    has_other_item_fields = (
        "other_item_use_count" in dynamic or "other_item_uses" in dynamic
    )
    if not has_other_item_fields:
        return raw_count, True

    other_item_count = dynamic.get("other_item_use_count")
    other_item_rows = dynamic.get("other_item_uses")
    if (
        type(other_item_count) is not int
        or other_item_count < 0
        or not isinstance(other_item_rows, list)
    ):
        return raw_count, False

    total_row_count = 0
    seen_rows: set[tuple[int, int]] = set()
    for row in other_item_rows:
        if not isinstance(row, Mapping):
            return raw_count, False
        spell_id = row.get("spell_id")
        item_entry = row.get("item_entry")
        use_count = row.get("count")
        if any(
            type(value) is not int or value <= 0
            for value in (spell_id, item_entry, use_count)
        ):
            return raw_count, False
        identity = (spell_id, item_entry)
        if identity in seen_rows:
            return raw_count, False
        seen_rows.add(identity)
        total_row_count += use_count

    if total_row_count != other_item_count or other_item_count > raw_count:
        return raw_count, False
    return raw_count - other_item_count, True


def reference_condition_projections(
    target_spec: str,
    target_observation: Any,
    *,
    fixture_target_guid: Any,
    fixture_contract_sha256: Any,
    scored_started_at_ms: Any,
    scored_ended_at_ms: Any,
) -> tuple[dict[str, Any], bool]:
    """Reconstruct fixed reference conditions from full-window raw samples."""
    target = target_observation if isinstance(target_observation, Mapping) else {}
    raw = target.get("reference_condition_observation")
    raw = raw if isinstance(raw, Mapping) else {}
    configured = raw.get("configured")
    configured = configured if isinstance(configured, Mapping) else {}
    dynamic = raw.get("dynamic_disabled")
    dynamic = dynamic if isinstance(dynamic, Mapping) else {}
    self_provided = raw.get("reference_class") == "self_provided_baseline"
    player_guid = _integer(target.get("guid"))
    target_guid = _integer(fixture_target_guid)
    started_at_ms = _integer(scored_started_at_ms)
    ended_at_ms = _integer(scored_ended_at_ms)
    sample_count = _integer(raw.get("sample_count"))
    exact_top_level_integers = all(
        type(raw.get(key)) is int
        for key in (
            "player_guid",
            "fixture_target_guid",
            "window_started_at_ms",
            "window_ended_at_ms",
            "first_sample_at_ms",
            "last_sample_at_ms",
            "maximum_sample_gap_ms",
            "sample_count",
        )
    )
    player_auras, player_rows_valid = _continuous_aura_rows(
        raw.get("player_auras"), sample_count=sample_count
    )
    target_auras, target_rows_valid = _continuous_aura_rows(
        raw.get("target_auras"),
        sample_count=sample_count,
        target_guid=player_guid,
    )

    def continuously_active(rows: Mapping[int, Mapping[str, Any]], spell_id: int) -> bool:
        row = rows.get(spell_id)
        return bool(
            row
            and _integer(row.get("active_samples")) == sample_count
            and _integer(row.get("inactive_samples")) == 0
        )

    def continuously_inactive(rows: Mapping[int, Mapping[str, Any]], spell_id: int) -> bool:
        row = rows.get(spell_id)
        return bool(
            row
            and _integer(row.get("active_samples")) == 0
            and _integer(row.get("inactive_samples")) == sample_count
        )

    configured_integer_keys = (
        "flask_item_id",
        "flask_item_spell_id",
        "flask_aura_spell_id",
        "food_item_id",
        "food_item_spell_id",
        "food_aura_spell_id",
        "prepot_item_spell_id",
        "prepot_aura_spell_id",
        "combat_potion_item_spell_id",
        "combat_potion_aura_spell_id",
    )
    configured_integers_valid = all(
        type(configured.get(key)) is int for key in configured_integer_keys
    )
    setup_aura_ids = configured.get("required_setup_aura_spell_ids")
    setup_aura_ids = setup_aura_ids if isinstance(setup_aura_ids, list) else []
    setup_aura_ids_valid = bool(
        isinstance(configured.get("required_setup_aura_spell_ids"), list)
        and all(type(spell_id) is int and spell_id > 0 for spell_id in setup_aura_ids)
        and setup_aura_ids == sorted(set(setup_aura_ids))
        and all(continuously_active(player_auras, spell_id) for spell_id in setup_aura_ids)
    )
    flask_item_id = _integer(configured.get("flask_item_id"))
    flask_item_spell_id = _integer(configured.get("flask_item_spell_id"))
    flask_aura_id = _integer(configured.get("flask_aura_spell_id"))
    flask_valid = bool(
        flask_aura_id in FLASK_ITEM_BY_AURA
        and FLASK_ITEM_BY_AURA[flask_aura_id] == flask_item_id
        and continuously_active(player_auras, flask_aura_id)
        and all(
            aura_id == flask_aura_id
            or continuously_inactive(player_auras, aura_id)
            for aura_id in FLASK_ITEM_BY_AURA
        )
    )
    food_item_id = _integer(configured.get("food_item_id"))
    food_item_spell_id = _integer(configured.get("food_item_spell_id"))
    food_aura_id = _integer(configured.get("food_aura_spell_id"))
    if food_aura_id == 0:
        food_valid = bool(
            food_item_id == 0
            and all(
                continuously_inactive(player_auras, aura_id)
                for aura_id in FOOD_ITEMS_BY_AURA
            )
        )
    else:
        food_valid = bool(
            food_aura_id in FOOD_ITEMS_BY_AURA
            and food_item_id in FOOD_ITEMS_BY_AURA[food_aura_id]
            and continuously_active(player_auras, food_aura_id)
        )

    normalized_tinker_use_count, other_item_reconciliation_valid = (
        _reconcile_legacy_tinker_use_count(dynamic)
    )

    raid_required_valid = all(
        continuously_inactive(player_auras, spell_id)
        if self_provided else continuously_active(player_auras, spell_id)
        for spell_id in RAID_REQUIRED_PLAYER_AURA_IDS
    )
    primary_states_valid = all(
        continuously_inactive(player_auras, spell_id)
        if self_provided else (
            continuously_active(player_auras, spell_id)
            or continuously_inactive(player_auras, spell_id)
        )
        for spell_id in PRIMARY_STAT_AURA_IDS
    )
    primary_active_count = sum(
        continuously_active(player_auras, spell_id)
        for spell_id in PRIMARY_STAT_AURA_IDS
    )
    replenishment_active = continuously_active(
        player_auras, REPLENISHMENT_AURA_ID
    )
    replenishment_inactive = continuously_inactive(
        player_auras, REPLENISHMENT_AURA_ID
    )
    might_active = continuously_active(
        player_auras, NON_PALADIN_MIGHT_AURA_ID
    )
    might_inactive = continuously_inactive(
        player_auras, NON_PALADIN_MIGHT_AURA_ID
    )
    raid_buffs_valid = bool(
        raid_required_valid
        and primary_states_valid
        and (primary_active_count == 0 if self_provided else primary_active_count == 1)
        and (replenishment_inactive if self_provided else (replenishment_active or replenishment_inactive))
        and (might_inactive if self_provided else (might_active or might_inactive))
    )
    raid_buffs = {
        "mana_player_aura_spell_ids": [] if self_provided else (
            [REPLENISHMENT_AURA_ID] if replenishment_active else []
        ),
        "non_paladin_player_aura_spell_ids": [] if self_provided else (
            [NON_PALADIN_MIGHT_AURA_ID] if might_active else []
        ),
        "primary_stat_aura_any_of_spell_ids": [] if self_provided else list(PRIMARY_STAT_AURA_IDS),
        "required_player_aura_spell_ids": [] if self_provided else list(RAID_REQUIRED_PLAYER_AURA_IDS),
    }

    target_required_valid = all(
        continuously_inactive(target_auras, spell_id)
        if self_provided else continuously_active(target_auras, spell_id)
        for spell_id in REQUIRED_TARGET_DEBUFF_AURA_IDS
    )
    stacked_rows = raw.get("target_stacked_auras")
    stacked_rows = stacked_rows if isinstance(stacked_rows, list) else []
    sunder_rows = [
        row
        for row in stacked_rows
        if isinstance(row, Mapping)
        and _integer(row.get("spell_id")) == SUNDER_ARMOR_AURA_ID
    ]
    sunder = sunder_rows[0] if len(sunder_rows) == 1 else {}
    sunder_valid = bool(
        isinstance(raw.get("target_stacked_auras"), list)
        and len(stacked_rows) == 1
        and all(
            type(sunder.get(key)) is int
            for key in (
                "spell_id",
                "required_stacks",
                "matching_samples",
                "mismatch_samples",
                "minimum_observed_stacks",
                "maximum_observed_stacks",
                "caster_guid",
                "owner_match_samples",
                "owner_mismatch_samples",
            )
        )
        and _integer(sunder.get("required_stacks")) == 3
        and _integer(sunder.get("matching_samples")) == (0 if self_provided else sample_count)
        and _integer(sunder.get("mismatch_samples")) == (sample_count if self_provided else 0)
        and _integer(sunder.get("minimum_observed_stacks")) == (0 if self_provided else 3)
        and _integer(sunder.get("maximum_observed_stacks")) == (0 if self_provided else 3)
        and _integer(sunder.get("caster_guid")) == (0 if self_provided else player_guid)
        and _integer(sunder.get("owner_match_samples")) == (0 if self_provided else sample_count)
        and _integer(sunder.get("owner_mismatch_samples")) == 0
    )
    bleed_ids = raw.get("external_bleed_aura_spell_ids")
    bleed_ids = bleed_ids if isinstance(bleed_ids, list) else []
    bleed_valid = bool(
        isinstance(raw.get("external_bleed_aura_spell_ids"), list)
        and bleed_ids == list(EXTERNAL_BLEED_AURA_IDS)
        and type(raw.get("unexpected_external_bleed_active_samples")) is int
        and _integer(raw.get("unexpected_external_bleed_active_samples")) == 0
        and all(spell_id in target_auras for spell_id in bleed_ids)
    )
    target_debuffs: dict[str, Any] = (
        {"required_aura_spell_ids": [], "required_stacked_auras": []}
        if self_provided
        else {
            "required_aura_spell_ids": list(REQUIRED_TARGET_DEBUFF_AURA_IDS),
            "required_stacked_auras": [
                {"spell_id": SUNDER_ARMOR_AURA_ID, "stacks": 3}
            ],
        }
    )
    if target_spec == "feral_druid_dps":
        target_debuffs["external_bleed_active"] = False

    dynamic_keys = (
        "prepot_item_id",
        "prepot_use_count",
        "combat_potion_item_id",
        "combat_potion_use_count",
        "tinker_item_id",
        "tinker_spell_id",
        "tinker_use_count",
        "racial_spell_id",
        "racial_use_count",
        "last_potion_id_nonzero_samples",
        "unexpected_dynamic_aura_active_samples",
    )
    dynamic_valid = bool(
        all(type(dynamic.get(key)) is int for key in dynamic_keys)
        and (
            (
                _integer(dynamic.get("prepot_item_id")) == 0
                and _integer(dynamic.get("prepot_use_count")) == 0
            )
            or (
                _integer(dynamic.get("prepot_item_id")) > 0
                and _integer(dynamic.get("prepot_use_count")) == 1
            )
        )
        and (
            (
                _integer(dynamic.get("combat_potion_item_id")) == 0
                and _integer(dynamic.get("combat_potion_use_count")) == 0
            )
            or (
                _integer(dynamic.get("combat_potion_item_id")) > 0
                and _integer(dynamic.get("combat_potion_use_count")) == 1
            )
        )
        and all(
            _integer(
                normalized_tinker_use_count
                if key == "tinker_use_count"
                else dynamic.get(key)
            )
            == 0
            for key in (
                "tinker_item_id",
                "tinker_spell_id",
                "tinker_use_count",
                "racial_spell_id",
                "racial_use_count",
                "unexpected_dynamic_aura_active_samples",
            )
        )
        and other_item_reconciliation_valid
        and _integer(dynamic.get("last_potion_id_nonzero_samples")) >= 0
    )
    race_id = _integer(target.get("race_id"))
    pre_score = target.get("pre_score_state")
    pre_score = pre_score if isinstance(pre_score, Mapping) else {}
    bleed_valid = bool(
        bleed_valid
        and pre_score.get("schema")
        == "phase8_pre_score_state_observation_v1"
        and pre_score.get("external_bleed_auras_absent") is True
        and 0 < _integer(pre_score.get("observed_at_ms")) <= started_at_ms
    )
    racial = {
        "race": RACE_NAME_BY_ID.get(race_id, ""),
        "race_id": race_id,
        "spell_id": _integer(dynamic.get("racial_spell_id")),
        "use_count": _integer(dynamic.get("racial_use_count")),
    }
    projections = {
        "flask": {
            "item_id": flask_item_id,
            "item_spell_id": flask_item_spell_id,
            "observed_aura_spell_id": flask_aura_id,
        },
        "food": {
            "item_id": food_item_id,
            "item_spell_id": food_item_spell_id,
            "observed_aura_spell_id": food_aura_id,
        },
        "prepot": {
            "item_id": _integer(dynamic.get("prepot_item_id")),
            "item_spell_id": _integer(configured.get("prepot_item_spell_id")),
            "observed_aura_spell_id": _integer(
                configured.get("prepot_aura_spell_id")
            ),
            "use_count": _integer(dynamic.get("prepot_use_count")),
        },
        "combat_potion": {
            "item_id": _integer(dynamic.get("combat_potion_item_id")),
            "item_spell_id": _integer(
                configured.get("combat_potion_item_spell_id")
            ),
            "observed_aura_spell_id": _integer(
                configured.get("combat_potion_aura_spell_id")
            ),
            "use_count": _integer(dynamic.get("combat_potion_use_count")),
        },
        "tinker": {
            "item_id": _integer(dynamic.get("tinker_item_id")),
            "use_count": normalized_tinker_use_count,
        },
        "racial": racial,
        "raid_buffs": raid_buffs,
        "target_debuffs": target_debuffs,
        "form_presence": {"required_aura_spell_ids": setup_aura_ids},
    }
    sniper_training_valid = True
    if target_spec == "survival_hunter":
        talents = target.get("active_talent_spell_ids")
        talents = talents if isinstance(talents, list) else []
        sniper_training_valid = bool(
            53304 in talents
            and 64420 in setup_aura_ids
            and continuously_active(player_auras, 64420)
        )
        projections["sniper_training"] = {
            "authority": "trinity_spell_hun_sniper_training_owned_rank_v1",
            "native_setup": "stationary_warmup_observation_only",
            "observed_aura_spell_id": 64420,
            "required_at_scoring_start": True,
            "required_continuous_uptime": 1.0,
            "talent_rank": 3,
            "talent_spell_id": 53304,
        }
    valid = bool(
        raw.get("schema") == "phase8_reference_condition_observation_v1"
        and raw.get("fixture_contract_sha256") == fixture_contract_sha256
        and _hex_sha256(fixture_contract_sha256)
        and exact_top_level_integers
        and player_guid > 0
        and target_guid > 0
        and _integer(raw.get("player_guid")) == player_guid
        and _integer(raw.get("fixture_target_guid")) == target_guid
        and started_at_ms > 0
        and ended_at_ms - started_at_ms == 300_000
        and _integer(raw.get("window_started_at_ms")) == started_at_ms
        and _integer(raw.get("window_ended_at_ms")) == ended_at_ms
        and _integer(raw.get("first_sample_at_ms")) == started_at_ms
        and _integer(raw.get("last_sample_at_ms")) == ended_at_ms
        and _full_window_sampling_valid(
            sample_count=raw.get("sample_count"),
            maximum_gap_ms=raw.get("maximum_sample_gap_ms"),
        )
        and player_rows_valid
        and target_rows_valid
        and configured_integers_valid
        and setup_aura_ids_valid
        and flask_valid
        and food_valid
        and raid_buffs_valid
        and target_required_valid
        and sunder_valid
        and bleed_valid
        and dynamic_valid
        and (
            not self_provided
            or (
                type(raw.get("unexpected_player_aura_active_samples")) is int
                and type(raw.get("unexpected_target_aura_active_samples")) is int
                and _integer(raw.get("unexpected_player_aura_active_samples")) == 0
                and _integer(raw.get("unexpected_target_aura_active_samples")) == 0
            )
        )
        and sniper_training_valid
        and bool(racial["race"])
    )
    return projections, valid


def compose_prepull_setup_projection(
    target_spec: str,
    native_setup: Any,
    condition_projections: Any,
    *,
    item_swap_projection: Any,
    external_windows_projection: Any,
) -> dict[str, Any]:
    """Join independently validated raw projections into prepull semantics."""
    native = native_setup if isinstance(native_setup, Mapping) else {}
    conditions = (
        condition_projections
        if isinstance(condition_projections, Mapping)
        else {}
    )
    item_swap = (
        item_swap_projection
        if isinstance(item_swap_projection, Mapping)
        else {}
    )
    external = (
        external_windows_projection
        if isinstance(external_windows_projection, Mapping)
        else {}
    )
    projection: dict[str, Any] = {
        "combat_potion": {
            key: (conditions.get("combat_potion") or {}).get(key)
            for key in ("item_id", "item_spell_id", "observed_aura_spell_id")
        },
        "external_windows": dict(external),
        "flask": dict(conditions.get("flask") or {}),
        "food": dict(conditions.get("food") or {}),
        "form_presence": dict(conditions.get("form_presence") or {}),
        "heroism": {"authority": "reference_environment"},
        "item_swap": dict(item_swap),
        "prepot": {
            key: (conditions.get("prepot") or {}).get(key)
            for key in ("item_id", "item_spell_id", "observed_aura_spell_id")
        },
        "racial": {
            key: (conditions.get("racial") or {}).get(key)
            for key in ("race", "race_id", "spell_id")
        },
        "raid_buffs": {"authority": "reference_environment"},
        "target_debuffs": {
            "authority": "reference_environment",
            **(
                {"external_bleed_active": False}
                if target_spec == "feral_druid_dps"
                else {}
            ),
        },
        "tinker": {
            "item_id": (conditions.get("tinker") or {}).get("item_id")
        },
    }
    if isinstance(native.get("weapon_imbues"), list):
        projection["weapon_imbues"] = list(native["weapon_imbues"])
    if isinstance(conditions.get("sniper_training"), Mapping):
        projection["sniper_training"] = dict(conditions["sniper_training"])
    return projection


def _requirement_equals(manifest: Mapping[str, Any], requirement_id: str) -> Any:
    requirements = manifest.get("requirements")
    requirements = requirements if isinstance(requirements, list) else []
    rows = [
        row
        for row in requirements
        if isinstance(row, Mapping) and row.get("id") == requirement_id
    ]
    return rows[0].get("equals") if len(rows) == 1 else None


def initial_resources_projection(
    target_observation: Any,
    *,
    expected: Any,
    fixture_contract_sha256: Any,
    scored_started_at_ms: Any,
) -> tuple[dict[str, Any], bool]:
    """Reconstruct the simulator initial-state semantic from raw reset reads."""
    target = target_observation if isinstance(target_observation, Mapping) else {}
    raw = target.get("initial_resources")
    raw = raw if isinstance(raw, Mapping) else {}
    expected_row = expected if isinstance(expected, Mapping) else {}
    powers = raw.get("powers")
    powers = powers if isinstance(powers, list) else []
    player_powers: list[dict[str, Any]] = []
    pet_power: dict[str, Any] | None = None
    powers_valid = bool(powers)
    target_guid = _integer(target.get("guid"))
    persistent_setup = target.get("persistent_setup")
    persistent_setup = (
        persistent_setup if isinstance(persistent_setup, Mapping) else {}
    )
    pet_guid = _integer(persistent_setup.get("pet_guid"))
    for power in powers:
        if not isinstance(power, Mapping):
            powers_valid = False
            continue
        mode = str(power.get("expected_mode") or "")
        unit_kind = str(power.get("unit_kind") or "")
        expected_native = _integer(power.get("expected_native_value"))
        expected_display = _integer(power.get("expected_display_value"))
        observed_native = _integer(power.get("observed_native_value"))
        observed_display = _integer(power.get("observed_display_value"))
        observed_maximum = _integer(power.get("observed_maximum_native_value"))
        semantic: dict[str, Any] = {
            "mode": mode,
            "name": str(power.get("name") or ""),
            "power_type": _integer(power.get("power_type")),
        }
        if mode == "exact":
            semantic.update(
                {
                    "display_value": expected_display,
                    "native_value": expected_native,
                }
            )
        powers_valid = powers_valid and bool(
            unit_kind in {"player", "pet"}
            and target_guid > 0
            and _integer(power.get("unit_guid"))
            == (target_guid if unit_kind == "player" else pet_guid)
            and (unit_kind != "pet" or pet_guid > 0)
            and mode in {"exact", "maximum"}
            and semantic["name"]
            and power.get("matches_contract") is True
            and expected_native == observed_native
            and expected_display == observed_display
            and observed_maximum > 0
            and (mode != "maximum" or expected_native == observed_maximum)
            and (mode != "exact" or expected_native <= observed_maximum)
        )
        if unit_kind == "pet":
            if pet_power is not None:
                powers_valid = False
            pet_power = semantic
        else:
            player_powers.append(semantic)

    runes = raw.get("runes")
    runes = runes if isinstance(runes, Mapping) else {}
    combo = raw.get("combo_points")
    combo = combo if isinstance(combo, Mapping) else {}
    eclipse = raw.get("neutral_eclipse")
    eclipse = eclipse if isinstance(eclipse, Mapping) else {}
    pet_resource = raw.get("pet_resource")
    pet_resource = pet_resource if isinstance(pet_resource, Mapping) else {}
    runes_ready_mask = (
        _integer(runes.get("expected_ready_mask"))
        if runes.get("required") is True
        else None
    )
    combo_points = (
        _integer(combo.get("expected"))
        if combo.get("required") is True
        else None
    )
    required_absent_auras = (
        [48517, 48518] if eclipse.get("required") is True else []
    )
    projection = {
        "authority": expected_row.get("authority"),
        "combo_points": combo_points,
        "pet_power": pet_power,
        "persistent_setup_at_scoring_start": expected_row.get(
            "persistent_setup_at_scoring_start"
        ),
        "player_powers": player_powers,
        "required_absent_auras": required_absent_auras,
        "runes_ready_mask": runes_ready_mask,
        "simulator_representation": expected_row.get("simulator_representation"),
    }
    fixture = target.get("fixture_contract")
    fixture = fixture if isinstance(fixture, Mapping) else {}
    observed_at_ms = _integer(raw.get("observed_at_ms"))
    scored_at_ms = _integer(scored_started_at_ms)
    pre_score = target.get("pre_score_state")
    pre_score = pre_score if isinstance(pre_score, Mapping) else {}
    pre_score_observed_at_ms = _integer(pre_score.get("observed_at_ms"))
    valid = bool(
        raw.get("schema") == "phase8_initial_resources_observation_v1"
        and _hex_sha256(fixture_contract_sha256)
        and fixture.get("schema") == "phase8_calibration_fixture_contract_v1"
        and fixture.get("content_sha256") == fixture_contract_sha256
        and raw.get("source_contract_sha256") == fixture_contract_sha256
        and raw.get("reset_applied") is True
        and raw.get("matches_contract") is True
        and raw.get("observed_before_scoring") is True
        and 0 < observed_at_ms <= scored_at_ms
        and pre_score.get("schema") == "phase8_pre_score_state_observation_v1"
        and pre_score.get("observed_before_scoring") is True
        and 0 < pre_score_observed_at_ms <= scored_at_ms
        and pre_score.get("persistent_setup_ready") is True
        and pre_score.get("no_active_cast") is True
        and pre_score.get("no_combat") is True
        and pre_score.get("global_cooldown_clear") is True
        and pre_score.get("cooldown_reset_applied") is True
        and pre_score.get("warmup_profile_actions_suppressed") is True
        and powers_valid
        and player_powers
        and runes.get("required") is (expected_row.get("runes_ready_mask") is not None)
        and (
            runes.get("required") is not True
            or (
                runes_ready_mask > 0
                and _integer(runes.get("observed_ready_mask"))
                == runes_ready_mask
            )
        )
        and combo.get("required") is (expected_row.get("combo_points") is not None)
        and (
            combo.get("required") is not True
            or _integer(combo.get("observed")) == combo_points
        )
        and eclipse.get("required")
        is bool(expected_row.get("required_absent_auras"))
        and (
            eclipse.get("required") is not True
            or eclipse.get("observed") is True
        )
        and pet_resource.get("required") is (expected_row.get("pet_power") is not None)
        and (
            pet_resource.get("required") is not True
            or pet_resource.get("observed") is True
        )
        and projection == expected_row
    )
    return projection, valid


def item_swap_projection(
    target_observation: Any,
    *,
    reference_gear_manifest_sha256: Any,
    scored_started_at_ms: Any = None,
    scored_ended_at_ms: Any = None,
) -> tuple[dict[str, Any], bool]:
    """Prove that the scored window continuously retained one gear identity."""
    target = target_observation if isinstance(target_observation, Mapping) else {}
    raw = target.get("item_swap_observation")
    raw = raw if isinstance(raw, Mapping) else {}
    initial_sha = str(raw.get("initial_gear_manifest_sha256") or "")
    current_sha = str(raw.get("current_gear_manifest_sha256") or "")
    observed_sha = observed_gear_manifest_sha256(target)
    target_guid = _integer(target.get("guid"))
    window_started_at_ms = _integer(raw.get("window_started_at_ms"))
    window_ended_at_ms = _integer(raw.get("window_ended_at_ms"))
    first_sample_at_ms = _integer(raw.get("first_sample_at_ms"))
    last_sample_at_ms = _integer(raw.get("last_sample_at_ms"))
    expected_started_at_ms = _integer(scored_started_at_ms)
    expected_ended_at_ms = _integer(scored_ended_at_ms)
    projection = {"enabled": bool(raw.get("enabled")), "items": []}
    valid = bool(
        raw.get("schema") == "phase8_no_item_swap_observation_v1"
        and raw.get("enabled") is False
        and target_guid > 0
        and _integer(raw.get("target_guid")) == target_guid
        and expected_started_at_ms > 0
        and expected_ended_at_ms - expected_started_at_ms == 300_000
        and window_started_at_ms == expected_started_at_ms
        and window_ended_at_ms == expected_ended_at_ms
        and first_sample_at_ms == window_started_at_ms
        and last_sample_at_ms == window_ended_at_ms
        and _full_window_sampling_valid(
            sample_count=raw.get("sample_count"),
            maximum_gap_ms=raw.get("maximum_sample_gap_ms"),
        )
        and _hex_sha256(initial_sha)
        and initial_sha == current_sha == observed_sha
        and initial_sha == reference_gear_manifest_sha256
        and _integer(raw.get("mismatch_sample_count")) == 0
        and raw.get("no_drift") is True
    )
    return projection, valid


def _exact_windows_ms(value: Any) -> tuple[list[list[int]], bool]:
    rows = value if isinstance(value, list) else []
    projected: list[list[int]] = []
    valid = isinstance(value, list)
    prior_end = -1
    for row in rows:
        if not isinstance(row, list) or len(row) != 2:
            valid = False
            continue
        start, end = row
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
        ):
            valid = False
            continue
        projected.append([start, end])
        valid = bool(valid and 0 <= start < end <= 300_000 and start >= prior_end)
        prior_end = end
    return projected, valid


def external_windows_projection(
    target_observation: Any,
    *,
    scored_started_at_ms: Any,
    scored_ended_at_ms: Any,
) -> tuple[dict[str, Any], bool]:
    """Prove temporal external auras remained absent for the scored window."""
    target = target_observation if isinstance(target_observation, Mapping) else {}
    raw = target.get("external_window_observation")
    raw = raw if isinstance(raw, Mapping) else {}
    pre_score = target.get("pre_score_state")
    pre_score = pre_score if isinstance(pre_score, Mapping) else {}
    heroism = raw.get("heroism")
    heroism = heroism if isinstance(heroism, Mapping) else {}
    power_infusion = raw.get("power_infusion")
    power_infusion = (
        power_infusion if isinstance(power_infusion, Mapping) else {}
    )
    dark_intent = raw.get("dark_intent_proc")
    dark_intent = dark_intent if isinstance(dark_intent, Mapping) else {}
    synapse = raw.get("synapse_springs")
    synapse = synapse if isinstance(synapse, Mapping) else {}
    heroism_windows, heroism_windows_valid = _exact_windows_ms(
        heroism.get("windows_ms")
    )
    power_infusion_windows, power_infusion_windows_valid = _exact_windows_ms(
        power_infusion.get("windows_ms")
    )
    synapse_windows, synapse_windows_valid = _exact_windows_ms(
        synapse.get("expected_windows_ms")
    )
    sample_count = _integer(raw.get("sample_count"))
    target_guid = _integer(target.get("guid"))
    started_at_ms = _integer(scored_started_at_ms)
    ended_at_ms = _integer(scored_ended_at_ms)
    exact_integer_fields = (
        raw.get("target_guid"),
        raw.get("window_started_at_ms"),
        raw.get("window_ended_at_ms"),
        raw.get("first_sample_at_ms"),
        raw.get("last_sample_at_ms"),
        raw.get("maximum_sample_gap_ms"),
        raw.get("sample_count"),
        heroism.get("source_count"),
        heroism.get("spell_id"),
        heroism.get("expected_active_samples"),
        heroism.get("observed_active_samples"),
        heroism.get("mismatch_samples"),
        power_infusion.get("source_count"),
        power_infusion.get("spell_id"),
        power_infusion.get("expected_active_samples"),
        power_infusion.get("observed_active_samples"),
        power_infusion.get("mismatch_samples"),
        dark_intent.get("base_spell_id"),
        dark_intent.get("unexpected_base_active_samples"),
        dark_intent.get("proc_spell_id"),
        dark_intent.get("uptime_pct"),
        dark_intent.get("expected_uptime_pct"),
        dark_intent.get("unexpected_active_samples"),
        synapse.get("spell_id"),
        synapse.get("unexpected_active_samples"),
    )
    projection = {
        "schema": (
            "phase8_external_windows_v1"
            if raw.get("schema") == "phase8_external_windows_observation_v1"
            else raw.get("schema")
        ),
        "heroism": {
            "source_count": _integer(heroism.get("source_count")),
            "spell_id": _integer(heroism.get("spell_id")),
            "windows_ms": heroism_windows,
        },
        "power_infusion": {
            "source_count": _integer(power_infusion.get("source_count")),
            "spell_id": _integer(power_infusion.get("spell_id")),
            "windows_ms": power_infusion_windows,
        },
        "dark_intent_proc": {
            "base_spell_id": _integer(dark_intent.get("base_spell_id")),
            "base_enabled": dark_intent.get("base_enabled"),
            "proc_spell_id": _integer(dark_intent.get("proc_spell_id")),
            "uptime_pct": _integer(dark_intent.get("expected_uptime_pct")),
        },
        "synapse_springs": {
            "spell_id": _integer(synapse.get("spell_id")),
            "windows_ms": synapse_windows,
        },
    }
    valid = bool(
        raw.get("schema") == "phase8_external_windows_observation_v1"
        and all(type(value) is int for value in exact_integer_fields)
        and target_guid > 0
        and _integer(raw.get("target_guid")) == target_guid
        and started_at_ms > 0
        and ended_at_ms - started_at_ms == 300_000
        and pre_score.get("schema")
        == "phase8_pre_score_state_observation_v1"
        and pre_score.get("temporal_external_auras_absent") is True
        and pre_score.get("heroism_ready") is False
        and 0 < _integer(pre_score.get("observed_at_ms")) <= started_at_ms
        and _integer(raw.get("window_started_at_ms")) == started_at_ms
        and _integer(raw.get("window_ended_at_ms")) == ended_at_ms
        and _integer(raw.get("first_sample_at_ms")) == started_at_ms
        and _integer(raw.get("last_sample_at_ms")) == ended_at_ms
        and _full_window_sampling_valid(
            sample_count=raw.get("sample_count"),
            maximum_gap_ms=raw.get("maximum_sample_gap_ms"),
        )
        and heroism_windows_valid
        and not heroism_windows
        and projection["heroism"]["source_count"] == 0
        and projection["heroism"]["spell_id"] == 2825
        and _integer(heroism.get("expected_active_samples")) == 0
        and _integer(heroism.get("observed_active_samples")) == 0
        and _integer(heroism.get("mismatch_samples")) == 0
        and power_infusion_windows_valid
        and not power_infusion_windows
        and projection["power_infusion"]["source_count"] == 0
        and projection["power_infusion"]["spell_id"] == 10060
        and _integer(power_infusion.get("expected_active_samples")) == 0
        and _integer(power_infusion.get("observed_active_samples")) == 0
        and _integer(power_infusion.get("mismatch_samples")) == 0
        and projection["dark_intent_proc"]["base_spell_id"] == 85767
        and projection["dark_intent_proc"]["base_enabled"] is False
        and _integer(dark_intent.get("unexpected_base_active_samples")) == 0
        and projection["dark_intent_proc"]["proc_spell_id"] == 85759
        and projection["dark_intent_proc"]["uptime_pct"] == 0
        and _integer(dark_intent.get("uptime_pct")) == 0
        and _integer(dark_intent.get("unexpected_active_samples")) == 0
        and synapse_windows_valid
        and not synapse_windows
        and synapse.get("windows_ms") == []
        and projection["synapse_springs"]["spell_id"] == 96230
        and _integer(synapse.get("unexpected_active_samples")) == 0
    )
    return projection, valid


def fixture_target_projections(
    calibration: Any,
    *,
    expected_target: Any,
    expected_distance: Any,
    fixture_contract_sha256: Any,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Validate live target identity and placement against the fixture hash."""
    row = calibration if isinstance(calibration, Mapping) else {}
    fixture_contract = row.get("fixture_contract")
    fixture_contract = (
        fixture_contract if isinstance(fixture_contract, Mapping) else {}
    )
    fixture = row.get("fixture_target")
    fixture = fixture if isinstance(fixture, Mapping) else {}
    declared = fixture.get("expected")
    declared = declared if isinstance(declared, Mapping) else {}
    provisioned = fixture.get("observed_at_provisioning")
    provisioned = provisioned if isinstance(provisioned, Mapping) else {}
    before = fixture.get("observed_before_scoring")
    before = before if isinstance(before, Mapping) else {}
    passive = fixture.get("scored_passive_observation")
    passive = passive if isinstance(passive, Mapping) else {}
    target_expected = (
        expected_target if isinstance(expected_target, Mapping) else {}
    )
    distance_expected = (
        expected_distance if isinstance(expected_distance, Mapping) else {}
    )
    expected_live = {
        "entry": _integer(target_expected.get("entry")),
        "level": _integer(target_expected.get("level")),
        "armor": _integer(target_expected.get("armor")),
        "creature_type": _integer(target_expected.get("creature_type")),
        "max_health": _integer(target_expected.get("live_max_health")),
        "passive": target_expected.get("live_target_attacks") is False,
        "runtime_min_distance_yards": distance_expected.get(
            "runtime_min_yards"
        ),
        "runtime_max_distance_yards": distance_expected.get(
            "runtime_max_yards"
        ),
    }
    scored_at_ms = _integer(row.get("scored_started_at_ms"))
    provisioned_at_ms = _integer(provisioned.get("observed_at_ms"))
    before_at_ms = _integer(before.get("observed_at_ms"))
    expected_type_mask = (
        1 << (expected_live["creature_type"] - 1)
        if expected_live["creature_type"] > 0
        else 0
    )
    try:
        provisioned_xyz = tuple(
            float(provisioned.get(key)) for key in ("x", "y", "z")
        )
        before_xyz = tuple(float(before.get(key)) for key in ("x", "y", "z"))
        observed_distance = float(before.get("bot_target_distance"))
        flat_distance = float(fixture.get("bot_target_distance"))
        minimum_distance = float(distance_expected.get("runtime_min_yards"))
        maximum_distance = float(distance_expected.get("runtime_max_yards"))
    except (TypeError, ValueError):
        provisioned_xyz = before_xyz = (math.nan, math.nan, math.nan)
        observed_distance = flat_distance = minimum_distance = maximum_distance = math.nan
    observations_match = all(
        _integer(observation.get(key)) == expected_live[key]
        for observation in (provisioned, before)
        for key in ("entry", "level", "armor", "creature_type", "max_health")
    )
    distance_projection = dict(distance_expected)
    target_projection = dict(target_expected)
    valid = bool(
        fixture_contract.get("schema")
        == "phase8_calibration_fixture_contract_v1"
        and fixture_contract.get("content_sha256") == fixture_contract_sha256
        and _hex_sha256(fixture_contract_sha256)
        and fixture.get("isolated_single_target") is True
        and declared == expected_live
        and target_expected.get("creature_type_name") == "mechanical"
        and target_expected.get("simulator_mob_type") == 7
        and observations_match
        and _integer(provisioned.get("guid")) > 0
        and _integer(before.get("guid")) == _integer(provisioned.get("guid"))
        and _integer(provisioned.get("creature_type_mask")) == expected_type_mask
        and _integer(before.get("creature_type_mask")) == expected_type_mask
        and _integer(before.get("map_id")) == _integer(provisioned.get("map_id"))
        and all(math.isfinite(value) for value in (*provisioned_xyz, *before_xyz))
        and all(abs(left - right) <= 1e-4 for left, right in zip(provisioned_xyz, before_xyz))
        and 0 < provisioned_at_ms <= before_at_ms <= scored_at_ms
        and before.get("before_scoring") is True
        and before.get("in_combat") is False
        and before.get("has_victim") is False
        and math.isfinite(observed_distance)
        and minimum_distance <= observed_distance <= maximum_distance
        and abs(flat_distance - observed_distance) <= 1e-3
        and fixture.get("runtime_guid") == provisioned.get("guid")
        and fixture.get("map_id") == provisioned.get("map_id")
        and fixture.get("geometry_validated") is True
        and fixture.get("native_line_of_sight") is True
        and fixture.get("native_path_reachable") is True
        and fixture.get("native_dry_land") is True
        and _integer(fixture.get("target_attack_observation_sample_count"))
        == _integer(passive.get("sample_count"))
        and _integer(fixture.get("target_attack_event_count")) == 0
        and _integer(passive.get("target_attack_event_count")) == 0
        and _integer(passive.get("victim_observation_sample_count")) == 0
        and passive.get("passive") is True
        and _integer(passive.get("target_guid"))
        == _integer(fixture.get("runtime_guid"))
        and _integer(passive.get("window_started_at_ms")) == scored_at_ms
        and _integer(passive.get("window_ended_at_ms"))
        == _integer(row.get("scored_ended_at_ms"))
        and _integer(passive.get("first_sample_at_ms")) == scored_at_ms
        and _integer(passive.get("last_sample_at_ms"))
        == _integer(row.get("scored_ended_at_ms"))
        and _full_window_sampling_valid(
            sample_count=passive.get("sample_count"),
            maximum_gap_ms=passive.get("maximum_sample_gap_ms"),
        )
    )
    return target_projection, distance_projection, valid


def comparison_manifest(reference_row: Any) -> Mapping[str, Any]:
    reference = reference_row if isinstance(reference_row, Mapping) else {}
    direct_manifest = reference.get("comparison_manifest")
    if isinstance(direct_manifest, Mapping):
        return direct_manifest
    conditions = reference.get("reference_conditions")
    conditions = conditions if isinstance(conditions, Mapping) else {}
    manifest = conditions.get("comparison_manifest")
    return manifest if isinstance(manifest, Mapping) else {}


def _hex_sha256(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "")))


def _repo_relative_file_sha256(value: Any) -> str:
    raw_path = str(value or "")
    candidate = Path(raw_path)
    if not raw_path or candidate.is_absolute() or ".." in candidate.parts:
        return ""
    resolved = (REPO_ROOT / candidate).resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return ""
    return _file_sha256(resolved) if resolved.is_file() else ""


def _repo_relative_fixture_contract_sha256(value: Any) -> str:
    """Validate/materialize the shared fixture and return its canonical hash."""
    raw_path = str(value or "")
    candidate = Path(raw_path)
    if not raw_path or candidate.is_absolute() or ".." in candidate.parts:
        return ""
    resolved = (REPO_ROOT / candidate).resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return ""
    try:
        from .phase8_fixture_contract import load_fixture_contract
    except (ImportError, ModuleNotFoundError):
        try:
            from phase8_fixture_contract import (  # type: ignore[no-redef]
                load_fixture_contract,
            )
        except (ImportError, ModuleNotFoundError):
            return ""
    try:
        _contract, content_sha256 = load_fixture_contract(resolved)
    except (OSError, ValueError, json.JSONDecodeError):
        return ""
    return content_sha256


def _artifact_descriptor_valid(value: Any) -> bool:
    artifact = value if isinstance(value, Mapping) else {}
    path = str(artifact.get("path") or "")
    expected_sha256 = str(artifact.get("sha256") or "")
    candidate = Path(path)
    if (
        not path
        or candidate.is_absolute()
        or ".." in candidate.parts
        or not _hex_sha256(expected_sha256)
    ):
        return False
    resolved = (REPO_ROOT / candidate).resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return False
    return bool(
        resolved.is_file()
        and resolved.stat().st_size == _integer(artifact.get("byte_count"))
        and _file_sha256(resolved) == expected_sha256
    )


def load_reference_request_binding(
    target_spec: str,
    path: Path = DEFAULT_REFERENCE_REQUESTS,
) -> dict[str, Any]:
    """Load and independently hash-check one generated-request contract."""
    checks: dict[str, bool] = {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    payload = payload if isinstance(payload, Mapping) else {}
    try:
        from .build_wowsims_reference_requests import validate_manifest
    except (ImportError, ModuleNotFoundError):
        try:
            from build_wowsims_reference_requests import (  # type: ignore[no-redef]
                validate_manifest,
            )
        except (ImportError, ModuleNotFoundError):
            validate_manifest = None  # type: ignore[assignment]
    try:
        if validate_manifest is None:
            raise ValueError("reference_request_validator_missing")
        validate_manifest(payload, root=REPO_ROOT, verify_generated_artifacts=True)
        independent_validation_passed = True
    except (OSError, ValueError, json.JSONDecodeError):
        independent_validation_passed = False
    checks["reference_request_catalog_schema"] = (
        payload.get("schema") == REFERENCE_REQUEST_SCHEMA
    )
    checks["reference_request_catalog_independently_validated"] = (
        independent_validation_passed
    )
    provider_revision = str(payload.get("provider_revision") or "")
    checks["reference_request_provider_revision_pinned"] = bool(
        re.fullmatch(r"[0-9a-f]{40}", provider_revision)
        or re.fullmatch(r"[0-9a-f]{64}", provider_revision)
    )
    catalog_fixture_sha256 = str(payload.get("fixture_contract_sha256") or "")
    checks["catalog_fixture_contract_content_hash"] = bool(
        _hex_sha256(catalog_fixture_sha256)
        and _repo_relative_fixture_contract_sha256(
            payload.get("fixture_contract_path")
        )
        == catalog_fixture_sha256
    )
    requests = payload.get("requests")
    requests = requests if isinstance(requests, list) else []
    rows = [
        row
        for row in requests
        if isinstance(row, Mapping) and row.get("target_spec") == target_spec
    ]
    checks["reference_request_unique_target"] = len(rows) == 1
    row = rows[0] if len(rows) == 1 else {}
    source_contract = row.get("source_contract")
    source_contract = (
        source_contract if isinstance(source_contract, Mapping) else {}
    )
    request = row.get("request")
    request = request if isinstance(request, Mapping) else {}
    result = row.get("result")
    result = result if isinstance(result, Mapping) else {}
    manifest = comparison_manifest(row)
    source_setup = manifest.get("source_setup")
    source_setup = source_setup if isinstance(source_setup, Mapping) else {}
    source_contract_sha256 = str(row.get("source_contract_sha256") or "")
    request_sha256 = str(row.get("request_sha256") or "")
    source_setup_sha256 = str(manifest.get("source_setup_sha256") or "")
    checks["source_contract_content_hash"] = bool(
        _hex_sha256(source_contract_sha256)
        and source_contract_sha256 == _canonical_sha256(source_contract)
        and manifest.get("source_contract_sha256") == source_contract_sha256
    )
    checks["request_content_hash"] = bool(
        _hex_sha256(request_sha256)
        and request_sha256 == _canonical_sha256(request)
        and manifest.get("request_sha256") == request_sha256
    )
    checks["source_setup_content_hash"] = bool(
        _hex_sha256(source_setup_sha256)
        and source_setup_sha256 == _canonical_sha256(source_setup)
    )
    checks["request_schema"] = (
        request.get("schema") == "wowsims_live_compatible_request_contract_v1"
    )
    checks["request_target_spec"] = request.get("target_spec") == target_spec
    checks["source_provider_revision_matches_catalog"] = (
        source_contract.get("provider_revision") == provider_revision
    )
    upstream_test = source_contract.get("upstream_test")
    upstream_test = upstream_test if isinstance(upstream_test, Mapping) else {}
    checks["upstream_test_snapshot_content_hash"] = bool(
        _hex_sha256(upstream_test.get("sha256"))
        and _repo_relative_file_sha256(upstream_test.get("snapshot_path"))
        == upstream_test.get("sha256")
    )
    fixture_contract_sha256 = str(request.get("fixture_contract_sha256") or "")
    checks["fixture_contract_hash_bound"] = bool(
        _hex_sha256(fixture_contract_sha256)
        and fixture_contract_sha256 == catalog_fixture_sha256
        and manifest.get("fixture_contract_sha256")
        == fixture_contract_sha256
    )
    result_status = result.get("status")
    result_key = result.get("result_key")
    result_dps = result.get("dps")
    artifacts = result.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, Mapping) else {}
    checks["generated_result_verified"] = result_status in ACCEPTABLE_RESULT_STATUSES
    checks["generated_result_projection_matches"] = bool(
        manifest.get("result_status") == result_status
        and manifest.get("reference_result_key") == result_key
        and _positive_numbers_equal(manifest.get("reference_dps"), result_dps)
    )
    checks["generated_result_artifacts_bound"] = bool(
        artifacts.get("request_contract_sha256") == request_sha256
        and all(
            _artifact_descriptor_valid(artifacts.get(key))
            for key in (
                "native_request",
                "native_result",
                "build_receipt",
                "generation_receipt",
                "dvc_reconstruction_receipt",
            )
        )
    )
    reasons = [name for name, passed in checks.items() if not passed]
    return {
        "schema": "phase8_reference_request_binding_v1",
        "target_spec": target_spec,
        "path": str(path.resolve()),
        "valid": not reasons,
        "reasons": reasons,
        "checks": checks,
        "catalog_sha256": _canonical_sha256(payload) if payload else "",
        "provider_revision": provider_revision,
        "row": dict(row),
        "comparison_manifest": dict(manifest),
    }


def verified_reference_request_runtime_facts(binding: Any) -> dict[str, Any]:
    """Project runtime comparison authority only from a verified request row."""
    bound = binding if isinstance(binding, Mapping) else {}
    row = bound.get("row")
    row = row if isinstance(row, Mapping) else {}
    request = row.get("request")
    request = request if isinstance(request, Mapping) else {}
    player = request.get("player")
    player = player if isinstance(player, Mapping) else {}
    gear = player.get("gear")
    gear = gear if isinstance(gear, Mapping) else {}
    manifest = bound.get("comparison_manifest")
    manifest = manifest if isinstance(manifest, Mapping) else {}
    verified = bound.get("valid") is True
    return {
        "gear_source_sha256": gear.get("source_sha256") if verified else None,
        "reference_gear_manifest_sha256": (
            gear.get("transformed_manifest_sha256") if verified else None
        ),
        "gear_transform_schema": gear.get("transform_schema") if verified else None,
        "gear_transform_authority": (
            gear.get("applicability_authority") if verified else None
        ),
        "reference_result_key": (
            manifest.get("reference_result_key") if verified else None
        ),
        "reference_value": manifest.get("reference_dps") if verified else None,
        "source_contract_sha256": (
            manifest.get("source_contract_sha256") if verified else None
        ),
        "request_sha256": manifest.get("request_sha256") if verified else None,
        "fixture_contract_sha256": (
            manifest.get("fixture_contract_sha256") if verified else None
        ),
        "result_status": manifest.get("result_status") if verified else None,
        "reference_request_binding_valid": verified,
        "reference_request_catalog_sha256": (
            bound.get("catalog_sha256") if verified else None
        ),
    }


def load_fixture_contract_binding(target_spec: str) -> dict[str, Any]:
    """Load the fixture authority shared by WoWSims generation and C++."""
    try:
        from .phase8_fixture_contract import load_fixture_contract
    except (ImportError, ModuleNotFoundError):
        try:
            from phase8_fixture_contract import (  # type: ignore[no-redef]
                load_fixture_contract,
            )
        except (ImportError, ModuleNotFoundError):
            load_fixture_contract = None  # type: ignore[assignment]
    reasons: list[str] = []
    try:
        if load_fixture_contract is None:
            raise ValueError("fixture_contract_loader_missing")
        contract, content_sha256 = load_fixture_contract()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        contract, content_sha256 = {}, ""
        reasons.append(f"fixture_contract_invalid:{type(exc).__name__}")
    specs = contract.get("specs") if isinstance(contract, Mapping) else {}
    specs = specs if isinstance(specs, Mapping) else {}
    spec = specs.get(target_spec)
    spec = spec if isinstance(spec, Mapping) else {}
    distances = contract.get("distance_contracts") if isinstance(contract, Mapping) else {}
    distances = distances if isinstance(distances, Mapping) else {}
    lane = str(spec.get("lane") or "")
    distance = distances.get(lane)
    distance = distance if isinstance(distance, Mapping) else {}
    target_contract = contract.get("target") if isinstance(contract, Mapping) else {}
    target_contract = target_contract if isinstance(target_contract, Mapping) else {}
    encounter = contract.get("encounter") if isinstance(contract, Mapping) else {}
    encounter = encounter if isinstance(encounter, Mapping) else {}
    prepull = spec.get("prepull_setup")
    prepull = prepull if isinstance(prepull, Mapping) else {}
    runtime_expected = spec.get("runtime_expected")
    runtime_expected = (
        runtime_expected if isinstance(runtime_expected, Mapping) else {}
    )
    simulator_options = spec.get("simulator_options")
    option_classification = classify_simulator_option_leaves(
        simulator_options
    )
    declared_option_classification = spec.get(
        "simulator_option_leaf_classification"
    )
    derived_declared_shape = {
        key: value
        for key, value in option_classification.items()
        if key != "valid"
    }
    execute_windows: list[dict[str, Any]] = []
    for row in encounter.get("health_windows") or []:
        if not isinstance(row, Mapping):
            continue
        lower = _integer(row.get("lower_pct"))
        upper = _integer(row.get("upper_pct"))
        execute_windows.append(
            {
                "phase": row.get("phase"),
                "start_ms": row.get("start_ms"),
                "end_ms": row.get("end_ms"),
                "configured_target_health_pct": row.get("target_health_pct"),
                "health_pct_lower_bound": lower,
                "lower_bound_inclusive": lower == 0,
                "health_pct_upper_bound": upper,
                "upper_bound_inclusive": upper != 20,
            }
        )
    execute = {
        "schema": "wowsims_cata_single_target_health_schedule_v1",
        "source_authority": (
            "pinned_wowsims_cata_core_test_utils_make_single_target_encounter"
        ),
        "source_duration_ms": _integer(encounter.get("duration_seconds")) * 1_000,
        "source_duration_variation_ms": _integer(
            encounter.get("duration_variation_seconds")
        )
        * 1_000,
        "source_execute_proportions": dict(
            encounter.get("execute_proportions") or {}
        ),
        "interval_semantics": "start_inclusive_end_exclusive",
        "fixture_only": True,
        "non_certifying": True,
        "windows": execute_windows,
    }
    powers = {
        "player_powers": list(spec.get("player_powers") or []),
        "pet_power": spec.get("pet_power"),
        "runes_ready_mask": spec.get("runes_ready_mask"),
        "combo_points": spec.get("combo_points"),
        "required_absent_auras": list(spec.get("required_absent_auras") or []),
    }
    if not _hex_sha256(content_sha256):
        reasons.append("fixture_contract_hash_missing")
    if not spec:
        reasons.append("fixture_contract_spec_missing")
    if not distance:
        reasons.append("fixture_contract_distance_missing")
    if not runtime_expected:
        reasons.append("fixture_contract_runtime_expected_missing")
    if option_classification.get("valid") is not True:
        reasons.append("fixture_contract_simulator_options_unclassified")
    if declared_option_classification != derived_declared_shape:
        reasons.append("fixture_contract_simulator_option_classification_mismatch")
    projection = {
        "schema": contract.get("schema") if isinstance(contract, Mapping) else None,
        "content_sha256": content_sha256,
        "authority": dict(contract.get("authority") or {})
        if isinstance(contract, Mapping)
        else {},
        "target": dict(target_contract),
        "encounter": dict(encounter),
        "distance": dict(distance),
        "spec": dict(spec),
        "runtime_expected": dict(runtime_expected),
        "fixture_target": dict(target_contract),
        "target_distance": {"lane": lane, **dict(distance)},
        "initial_resources": powers,
        "simulator_options": dict(simulator_options or {}),
        "simulator_option_classification": option_classification,
        "pet_setup": dict(spec.get("pet_setup") or {}),
        "prepull_setup": dict(prepull),
        "execute": execute,
        "duration": _integer(encounter.get("duration_seconds")),
    }
    for key, value in prepull.items():
        projection.setdefault(str(key), value)
    for key, value in runtime_expected.items():
        projection[str(key)] = value
    return {
        "schema": "phase8_fixture_contract_binding_v1",
        "target_spec": target_spec,
        "valid": not reasons,
        "reasons": reasons,
        "content_sha256": content_sha256,
        "projection": projection,
    }


def preflight_reference_condition_compatibility(
    *,
    target_spec: str,
    target_row: Any,
    reference_row: Any,
    request_binding: Any = None,
    fixture_contract: Any = None,
) -> dict[str, Any]:
    """Validate static simulator/live compatibility before reserving a try."""
    target = target_row if isinstance(target_row, Mapping) else {}
    reference = reference_row if isinstance(reference_row, Mapping) else {}
    binding = (
        request_binding
        if isinstance(request_binding, Mapping)
        else load_reference_request_binding(target_spec)
    )
    manifest = binding.get("comparison_manifest")
    manifest = manifest if isinstance(manifest, Mapping) else {}
    fixture_binding = (
        fixture_contract
        if isinstance(fixture_contract, Mapping)
        else load_fixture_contract_binding(target_spec)
    )
    fixture = fixture_binding.get("projection")
    fixture = fixture if isinstance(fixture, Mapping) else {}
    requirements = manifest.get("requirements")
    requirements = requirements if isinstance(requirements, list) else []
    checks: dict[str, bool] = {
        "supported_target_spec": target_spec in SUPPORTED_REFERENCE_SPECS,
        "target_identity_matches": (
            target.get("spec_target_id") == target_spec
            and target.get("runtime_join_key") == target_spec
        ),
        "reference_identity_matches": (
            reference.get("spec_target_id") == target_spec
            and bool(reference.get("reference_id"))
            and bool(reference.get("provider_revision"))
        ),
        "comparison_manifest_present": bool(manifest),
        "comparison_manifest_schema": (
            manifest.get("schema") == COMPARISON_MANIFEST_SCHEMA
        ),
        "comparison_manifest_target_spec": (
            manifest.get("target_spec") == target_spec
        ),
        "reference_request_binding_valid": binding.get("valid") is True,
        "fixture_contract_binding_valid": fixture_binding.get("valid") is True,
        "fixture_contract_matches_request": bool(
            _hex_sha256(fixture_binding.get("content_sha256"))
            and fixture_binding.get("content_sha256")
            == manifest.get("fixture_contract_sha256")
        ),
    }
    source_setup = manifest.get("source_setup")
    source_setup = source_setup if isinstance(source_setup, Mapping) else {}
    checks["exact_settings_result_key_pinned"] = bool(
        manifest.get("reference_result_key")
        and binding.get("valid") is True
    )
    checks["source_contract_hash_pinned"] = len(
        str(manifest.get("source_contract_sha256") or "")
    ) == 64
    checks["reference_result_status_acceptable"] = (
        manifest.get("result_status") in ACCEPTABLE_RESULT_STATUSES
    )
    checks["exact_settings_reference_value_pinned"] = bool(
        binding.get("valid") is True
        and _positive_numbers_equal(
            manifest.get("reference_dps"), manifest.get("reference_dps")
        )
    )
    checks["source_setup_complete"] = REQUIRED_SOURCE_SETUP_KEYS.issubset(
        source_setup
    )
    checks["source_setup_sha256_valid"] = (
        len(str(manifest.get("source_setup_sha256") or "")) == 64
        and manifest.get("source_setup_sha256") == _canonical_sha256(source_setup)
    )

    gear = reference.get("gear")
    gear = gear if isinstance(gear, Mapping) else {}
    checks["reference_gear_source_pinned"] = len(
        str(gear.get("source_sha256") or "")
    ) == 64
    checks["reference_gear_manifest_pinned"] = len(
        str(gear.get("transformed_manifest_sha256") or "")
    ) == 64
    checks["reference_gear_transform_schema_pinned"] = (
        gear.get("transform_schema") == "wowsims_cata_equipment_manifest_v1"
    )
    checks["reference_gear_transform_authority_pinned"] = (
        gear.get("permanent_enchant_applicability_authority")
        == "pinned_wowsims_preset_exact"
    )

    declared_classes = {
        str(row.get("condition_class") or "")
        for row in requirements
        if isinstance(row, Mapping)
    }
    checks["comparison_manifest_condition_class_coverage"] = (
        declared_classes == REQUIRED_CONDITION_CLASSES
    )
    requirement_classes_by_id = {
        str(row.get("id") or ""): str(row.get("condition_class") or "")
        for row in requirements
        if isinstance(row, Mapping)
    }
    checks["comparison_manifest_required_fact_coverage"] = all(
        requirement_classes_by_id.get(requirement_id) == condition_class
        for requirement_id, condition_class in REQUIRED_REQUIREMENT_CLASSES.items()
    )
    checks["glyph_item_property_aura_translation_pinned"] = (
        _glyph_requirement_translation_valid(requirements)
    )
    planned_facts = {
        "target": target,
        "reference": reference,
        "fixture": fixture,
    }
    seen_ids: set[str] = set()
    for index, row in enumerate(requirements):
        if not isinstance(row, Mapping):
            checks[f"planned_requirement_{index}_valid"] = False
            continue
        requirement_id = str(row.get("id") or "")
        condition_class = str(row.get("condition_class") or "")
        planned_path = str(row.get("planned_path") or "")
        static_verifiability = str(row.get("static_verifiability") or "")
        planned_path_allowed = bool(
            (
                static_verifiability == "target_capability"
                and planned_path.startswith("target.")
            )
            or (
                static_verifiability == "catalog_exact"
                and condition_class
                in {"gear_source_manifest", "race", "talents_glyphs"}
                and planned_path.startswith(("target.", "reference."))
            )
            or (
                static_verifiability == "fixture_contract_exact"
                and bool(fixture)
                and planned_path.startswith("fixture.")
            )
        )
        valid = bool(
            requirement_id
            and requirement_id not in seen_ids
            and condition_class in REQUIRED_CONDITION_CLASSES
            and "equals" in row
            and "planned_equals" in row
            and planned_path_allowed
        )
        if requirement_id:
            seen_ids.add(requirement_id)
        found, observed = (
            _fact_at_path(
                planned_facts,
                planned_path,
                allowed_roots=_ALLOWED_PLANNED_ROOTS,
            )
            if valid
            else (False, None)
        )
        checks[f"planned_requirement:{requirement_id or index}"] = bool(
            found and observed == row.get("planned_equals")
        )

    reasons = [name for name, passed in checks.items() if not passed]
    return {
        "schema": "phase8_reference_condition_preflight_v1",
        "target_spec": target_spec,
        "conditions_compatible": not reasons,
        "reasons": reasons,
        "checks": checks,
        "expected_manifest_sha256": _canonical_sha256(manifest) if manifest else "",
        "reference_request_catalog_sha256": binding.get("catalog_sha256"),
        "reference_request_binding_reasons": list(binding.get("reasons") or []),
        "fixture_contract_binding_reasons": list(
            fixture_binding.get("reasons") or []
        ),
    }


def spec_uses_mana(target_spec: str) -> bool:
    return target_spec in MANA_SPECS


def expected_flask_aura(target_spec: str) -> str:
    if target_spec in INTELLECT_FLASK_SPECS:
        return "79470"
    if target_spec in AGILITY_FLASK_SPECS:
        return "79471"
    if target_spec in STRENGTH_FLASK_SPECS:
        return "79472"
    return ""


def required_buff_auras(target_spec: str) -> list[str]:
    """Return only the shared FullRaidBuffs observations.

    Consumable auras and spec-only external effects are intentionally not
    inferred here. Their exact presence *or absence* is selected by the
    content-hashed per-spec comparison manifest.
    """
    required = list(BASE_BUFF_AURAS)
    if spec_uses_mana(target_spec):
        required.append("57669")
    if target_spec not in PALADIN_SPECS:
        required.append("79102")
    return required


def derive_reference_condition_compatibility(
    *,
    target_spec: str,
    reference_setup: Any,
    reference_conditions: Any,
    calibration: Any = None,
    runtime_normalization: Any = None,
    target_observation: Any = None,
    runtime_facts: Any = None,
    expected_manifest: Any = None,
    reference_class: Any = None,
) -> dict[str, Any]:
    """Recompute comparability; never trust a reported compatibility boolean.

    Generic catalog prose is insufficient. A run can pass only when a pinned,
    per-spec manifest covers every required scientific condition class and all
    of its exact expectations match raw server facts.
    """
    setup = reference_setup if isinstance(reference_setup, Mapping) else {}
    conditions = reference_conditions if isinstance(reference_conditions, Mapping) else {}
    calibration_row = calibration if isinstance(calibration, Mapping) else {}
    normalization = (
        runtime_normalization if isinstance(runtime_normalization, Mapping) else {}
    )
    target = target_observation if isinstance(target_observation, Mapping) else {}
    supplied_runtime = runtime_facts if isinstance(runtime_facts, Mapping) else {}
    manifest = expected_manifest if isinstance(expected_manifest, Mapping) else {}
    self_provided_baseline = (
        str(reference_class) == "self_provided_baseline"
        or str(normalization.get("buff_basis")) == "self_provided_consumables"
    )
    runtime = {
        key: supplied_runtime.get(key)
        for key in (
            "gear_source_sha256",
            "reference_gear_manifest_sha256",
            "observed_gear_manifest_sha256",
            "gear_transform_schema",
            "gear_transform_authority",
            "reference_result_key",
            "reference_value",
            "source_contract_sha256",
            "request_sha256",
            "fixture_contract_sha256",
            "fixture_contract_binding_valid",
            "result_status",
            "reference_request_binding_valid",
            "reference_request_catalog_sha256",
        )
    }
    runtime["observed_gear_manifest_sha256"] = observed_gear_manifest_sha256(
        target
    )
    execute_projection, execute_observations_valid = execute_schedule_projection(
        normalization.get("execute_threshold_windows")
    )
    runtime["execute_schedule_projection"] = execute_projection
    runtime["execute_projection"] = (
        dict(execute_projection.get("source_execute_proportions") or {})
        if execute_observations_valid
        else {}
    )
    pet_projection, pet_observation_valid = pet_setup_projection(
        target,
        expected=_requirement_equals(manifest, "pet_setup"),
        scored_started_at_ms=calibration_row.get("scored_started_at_ms"),
        scored_ended_at_ms=calibration_row.get("scored_ended_at_ms"),
    )
    prepull_projection, prepull_observation_valid = prepull_setup_projection(
        target,
        scored_started_at_ms=calibration_row.get("scored_started_at_ms"),
    )
    runtime["pet_setup_projection"] = pet_projection
    runtime["prepull_setup_projection"] = prepull_projection
    runtime["glyph_identity"] = {
        "property_ids": target.get("glyph_property_ids"),
        "aura_spell_ids": target.get("glyph_aura_spell_ids"),
    }
    initial_projection, initial_resources_valid = initial_resources_projection(
        target,
        expected=_requirement_equals(manifest, "initial_resources"),
        fixture_contract_sha256=runtime.get("fixture_contract_sha256"),
        scored_started_at_ms=calibration_row.get("scored_started_at_ms"),
    )
    no_swap_projection, item_swap_observation_valid = item_swap_projection(
        target,
        reference_gear_manifest_sha256=runtime.get(
            "reference_gear_manifest_sha256"
        ),
        scored_started_at_ms=calibration_row.get("scored_started_at_ms"),
        scored_ended_at_ms=calibration_row.get("scored_ended_at_ms"),
    )
    runtime["initial_resources_projection"] = initial_projection
    runtime["item_swap_projection"] = no_swap_projection
    (
        fixture_target_projection,
        target_distance_projection,
        fixture_target_observation_valid,
    ) = fixture_target_projections(
        calibration_row,
        expected_target=_requirement_equals(manifest, "fixture_target"),
        expected_distance=_requirement_equals(manifest, "target_distance"),
        fixture_contract_sha256=runtime.get("fixture_contract_sha256"),
    )
    runtime["fixture_target_projection"] = fixture_target_projection
    runtime["target_distance_projection"] = target_distance_projection
    condition_projections, reference_condition_observation_valid = (
        reference_condition_projections(
            target_spec,
            target,
            fixture_target_guid=(
                (calibration_row.get("fixture_target") or {}).get(
                    "runtime_guid"
                )
                if isinstance(calibration_row.get("fixture_target"), Mapping)
                else None
            ),
            fixture_contract_sha256=runtime.get("fixture_contract_sha256"),
            scored_started_at_ms=calibration_row.get("scored_started_at_ms"),
            scored_ended_at_ms=calibration_row.get("scored_ended_at_ms"),
        )
    )
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
        runtime[f"{requirement_id}_projection"] = dict(
            condition_projections.get(requirement_id) or {}
        )
    external_projection, external_windows_observation_valid = (
        external_windows_projection(
            target,
            scored_started_at_ms=calibration_row.get("scored_started_at_ms"),
            scored_ended_at_ms=calibration_row.get("scored_ended_at_ms"),
        )
    )
    runtime["external_windows_projection"] = external_projection
    prepull_projection = compose_prepull_setup_projection(
        target_spec,
        prepull_projection,
        condition_projections,
        item_swap_projection=no_swap_projection,
        external_windows_projection=external_projection,
    )
    prepull_observation_valid = bool(
        prepull_observation_valid
        and reference_condition_observation_valid
        and external_windows_observation_valid
        and item_swap_observation_valid
    )
    runtime["prepull_setup_projection"] = prepull_projection
    runtime["heroism_projection"] = (
        {
            "windows_ms": list(
                (external_projection.get("heroism") or {}).get(
                    "windows_ms"
                )
            )
        }
        if external_windows_observation_valid
        else {}
    )
    scored_started_at_ms = _integer(calibration_row.get("scored_started_at_ms"))
    scored_ended_at_ms = _integer(calibration_row.get("scored_ended_at_ms"))
    try:
        scored_seconds = float(calibration_row.get("scored_seconds"))
    except (TypeError, ValueError):
        scored_seconds = -1.0
    duration_observation_valid = bool(
        calibration_row.get("window_complete") is True
        and scored_started_at_ms > 0
        and scored_ended_at_ms - scored_started_at_ms == 300_000
        and scored_seconds == 300.0
    )
    runtime["duration_projection"] = (
        {"duration_seconds": 300, "duration_variation_seconds": 0}
        if duration_observation_valid
        else {}
    )
    # Heroism is independently reconstructed by the temporal-external absence
    # receipt above. No expected manifest values are copied into runtime facts.
    runtime.setdefault("heroism_projection", {})
    raid_buffs_projection = condition_projections.get("raid_buffs")
    raid_buffs_projection = (
        raid_buffs_projection
        if isinstance(raid_buffs_projection, Mapping)
        else {}
    )
    required_player_auras = {
        _integer(spell_id)
        for spell_id in (
            raid_buffs_projection.get("required_player_aura_spell_ids") or []
        )
    }
    mana_player_auras = {
        _integer(spell_id)
        for spell_id in (
            raid_buffs_projection.get("mana_player_aura_spell_ids") or []
        )
    }
    non_paladin_player_auras = {
        _integer(spell_id)
        for spell_id in (
            raid_buffs_projection.get("non_paladin_player_aura_spell_ids") or []
        )
    }
    primary_stat_aura_any_of = tuple(
        _integer(spell_id)
        for spell_id in (
            raid_buffs_projection.get("primary_stat_aura_any_of_spell_ids") or []
        )
    )
    checks: dict[str, bool] = {}

    checks["supported_target_spec"] = target_spec in SUPPORTED_REFERENCE_SPECS
    checks["replenishment_requirement_matches_spec"] = (
        setup.get("replenishment_required") is spec_uses_mana(target_spec)
    )
    if not self_provided_baseline:
        # Full-raid reference conditions only exist for controlled baselines.
        # A self-provided baseline owns its own consumables and must not be
        # rejected for the absence of a raid-buff environment it never had.
        checks["reference_setup_enabled"] = setup.get("enabled") is True
        for key, expected in EXPECTED_REFERENCE_CONDITIONS.items():
            checks[f"reference_{key}_matches"] = conditions.get(key) == expected
        for aura in required_buff_auras(target_spec):
            if aura == "kings_or_mark":
                observed = primary_stat_aura_any_of == PRIMARY_STAT_AURA_IDS
            else:
                spell_id = int(aura)
                observed = spell_id in required_player_auras
                if spell_id == REPLENISHMENT_AURA_ID:
                    observed = spell_id in mana_player_auras
                elif spell_id == NON_PALADIN_MIGHT_AURA_ID:
                    observed = spell_id in non_paladin_player_auras
            checks[f"required_buff_aura_{aura}"] = bool(
                reference_condition_observation_valid and observed
            )
        checks["runtime_reference_conditions_enabled"] = (
            normalization.get("reference_conditions") is True
        )
    checks["runtime_reference_not_declared_mismatched"] = (
        normalization.get("external_reference_mode")
        != "informational_only_conditions_mismatched"
    )
    checks["runtime_execute_threshold_windows_valid"] = (
        execute_observations_valid
    )
    checks["runtime_duration_observation_valid"] = duration_observation_valid
    checks["runtime_initial_resources_observation_valid"] = (
        initial_resources_valid
    )
    checks["runtime_item_swap_observation_valid"] = (
        item_swap_observation_valid
    )
    checks["runtime_fixture_target_observation_valid"] = (
        fixture_target_observation_valid
    )
    checks["runtime_external_windows_observation_valid"] = (
        external_windows_observation_valid
    )
    if not self_provided_baseline:
        # Raid-buff observation validity is undefined when the baseline class
        # never provisions a raid-buff environment.
        checks["runtime_reference_condition_observation_valid"] = (
            reference_condition_observation_valid
        )
    checks["runtime_pet_setup_receipts_valid"] = pet_observation_valid
    checks["runtime_prepull_setup_receipts_valid"] = prepull_observation_valid
    reference_gear_sha256 = str(runtime.get("reference_gear_manifest_sha256") or "")
    observed_gear_sha256 = str(runtime.get("observed_gear_manifest_sha256") or "")
    raw_observed_gear_sha256 = str(runtime["observed_gear_manifest_sha256"] or "")
    checks["reference_gear_source_pinned"] = len(
        str(runtime.get("gear_source_sha256") or "")
    ) == 64
    checks["reference_gear_transform_schema_pinned"] = (
        runtime.get("gear_transform_schema")
        == "wowsims_cata_equipment_manifest_v1"
    )
    checks["reference_gear_transform_authority_pinned"] = (
        runtime.get("gear_transform_authority")
        == "pinned_wowsims_preset_exact"
    )
    checks["runtime_gear_manifest_matches_reference"] = bool(
        len(reference_gear_sha256) == 64
        and reference_gear_sha256 == observed_gear_sha256
        and observed_gear_sha256 == raw_observed_gear_sha256
    )
    source_setup = manifest.get("source_setup")
    source_setup = source_setup if isinstance(source_setup, Mapping) else {}
    checks["exact_settings_result_key_matches_reference"] = bool(
        manifest.get("reference_result_key")
        and manifest.get("reference_result_key")
        == runtime.get("reference_result_key")
    )
    checks["source_contract_hash_matches_reference"] = bool(
        len(str(manifest.get("source_contract_sha256") or "")) == 64
        and manifest.get("source_contract_sha256")
        == runtime.get("source_contract_sha256")
    )
    checks["request_hash_matches_reference"] = bool(
        _hex_sha256(manifest.get("request_sha256"))
        and manifest.get("request_sha256") == runtime.get("request_sha256")
    )
    checks["fixture_contract_hash_matches_reference"] = bool(
        _hex_sha256(manifest.get("fixture_contract_sha256"))
        and manifest.get("fixture_contract_sha256")
        == runtime.get("fixture_contract_sha256")
        and runtime.get("fixture_contract_binding_valid") is True
    )
    checks["reference_request_binding_valid"] = bool(
        runtime.get("reference_request_binding_valid") is True
        and _hex_sha256(runtime.get("reference_request_catalog_sha256"))
    )
    checks["reference_result_status_acceptable"] = bool(
        manifest.get("result_status") in ACCEPTABLE_RESULT_STATUSES
        and manifest.get("result_status") == runtime.get("result_status")
    )
    checks["exact_settings_reference_value_matches"] = _positive_numbers_equal(
        manifest.get("reference_dps"), runtime.get("reference_value")
    )
    checks["source_setup_complete"] = REQUIRED_SOURCE_SETUP_KEYS.issubset(
        source_setup
    )
    checks["source_setup_sha256_valid"] = (
        len(str(manifest.get("source_setup_sha256") or "")) == 64
        and manifest.get("source_setup_sha256") == _canonical_sha256(source_setup)
    )

    checks["runtime_race_observed"] = _integer(target.get("race_id")) > 0
    checks["runtime_talents_observed"] = bool(
        isinstance(target.get("active_talent_spell_ids"), list)
        and target.get("active_talent_spell_ids")
    )
    checks["runtime_glyphs_observed"] = isinstance(
        target.get("glyph_property_ids"), list
    )
    checks["runtime_form_presence_pet_observed"] = isinstance(
        target.get("persistent_setup"), Mapping
    )
    checks["comparison_manifest_present"] = bool(manifest)
    checks["comparison_manifest_schema"] = (
        manifest.get("schema") == COMPARISON_MANIFEST_SCHEMA
    )
    checks["comparison_manifest_target_spec"] = (
        manifest.get("target_spec") == target_spec
    )
    requirements = manifest.get("requirements")
    requirements = requirements if isinstance(requirements, list) else []
    declared_classes = {
        str(row.get("condition_class") or "")
        for row in requirements
        if isinstance(row, Mapping)
    }
    checks["comparison_manifest_condition_class_coverage"] = (
        declared_classes == REQUIRED_CONDITION_CLASSES
    )
    requirement_classes_by_id = {
        str(row.get("id") or ""): str(row.get("condition_class") or "")
        for row in requirements
        if isinstance(row, Mapping)
    }
    checks["comparison_manifest_required_fact_coverage"] = all(
        requirement_classes_by_id.get(requirement_id) == condition_class
        for requirement_id, condition_class in REQUIRED_REQUIREMENT_CLASSES.items()
    )
    checks["glyph_item_property_aura_translation_pinned"] = (
        _glyph_requirement_translation_valid(requirements)
    )

    raw_facts = {
        "calibration": calibration_row,
        "normalization": normalization,
        "reference_setup": setup,
        "runtime": runtime,
        "target": target,
    }
    observed_manifest_values: dict[str, Any] = {}
    seen_ids: set[str] = set()
    for index, row in enumerate(requirements):
        if not isinstance(row, Mapping):
            checks[f"manifest_requirement_{index}_valid"] = False
            continue
        requirement_id = str(row.get("id") or "")
        condition_class = str(row.get("condition_class") or "")
        path = str(row.get("path") or "")
        expected_prefixes = REQUIRED_RUNTIME_PATH_PREFIXES.get(
            requirement_id, ()
        )
        valid = bool(
            requirement_id
            and requirement_id not in seen_ids
            and condition_class in REQUIRED_CONDITION_CLASSES
            and "equals" in row
            and "planned_equals" in row
            and any(path.startswith(prefix) for prefix in expected_prefixes)
            and row.get("static_verifiability")
            in {
                "target_capability",
                "catalog_exact",
                "fixture_contract_exact",
            }
        )
        if requirement_id:
            seen_ids.add(requirement_id)
        found, observed = _fact_at_path(raw_facts, path) if valid else (False, None)
        check_name = f"manifest_requirement:{requirement_id or index}"
        checks[check_name] = bool(found and observed == row.get("equals"))
        observed_manifest_values[requirement_id or str(index)] = {
            "path": path,
            "found": found,
            "observed": observed,
        }

    reasons = [name for name, passed in checks.items() if not passed]
    return {
        "schema": "phase8_reference_condition_compatibility_v1",
        "target_spec": target_spec,
        "conditions_compatible": not reasons,
        "reasons": reasons,
        "checks": checks,
        "requires_replenishment": spec_uses_mana(target_spec),
        "required_buff_auras": required_buff_auras(target_spec),
        "required_condition_classes": sorted(REQUIRED_CONDITION_CLASSES),
        "expected_manifest": dict(manifest),
        "expected_manifest_sha256": _canonical_sha256(manifest) if manifest else "",
        "observed_manifest_values": observed_manifest_values,
        "reference_conditions": dict(conditions),
        "runtime_reference_facts": dict(runtime),
    }
