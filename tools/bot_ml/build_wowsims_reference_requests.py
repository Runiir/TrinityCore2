#!/usr/bin/env python3
"""Build content-addressed live-compatible WoWSims DPS requests.

This module deliberately does not run WoWSims.  It joins the checked-in
target/reference/gear catalogs to the calibration fixture shared with the
worldserver and emits immutable request contracts.  A separate executor may
atomically promote the complete 16-spec cohort from ``requires_generation``
to ``generated_verified`` only after independently verifying every native
request, result, build, transport, and DVC reconstruction receipt.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_ACCEPTANCE_PATH = ROOT / "experiments/configs/cata_raid_dps_acceptance_v1.json"
DEFAULT_FIXTURE_PATH = (
    ROOT
    / "experiments/configs/phase8_calibration_fixture_contract_v1.materialized.json"
)
DEFAULT_OUTPUT_PATH = ROOT / "experiments/configs/wowsims_cata_dps_reference_requests_v1.json"
DEFAULT_GEAR_PATH = ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json"
TALENT_DBC_SNAPSHOT_DIR = (
    ROOT / "experiments/configs/wowsims_cata_p4_talent_sources"
)

CATALOG_SCHEMA = "wowsims_cata_dps_reference_requests_v1"
REQUEST_SCHEMA = "wowsims_live_compatible_request_contract_v1"
SOURCE_CONTRACT_SCHEMA = "wowsims_cata_reference_source_contract_v1"
COMPARISON_SCHEMA = "phase8_wowsims_reference_setup_manifest_v1"
RESULT_PENDING = "requires_generation"
RESULT_ACCEPTED = "generated_verified"
EXPECTED_ITERATIONS = 2_000
EXPECTED_RANDOM_SEED = 101
FIXED_FOOD_SPECS = frozenset({"balance_druid", "shadow_priest"})

REQUIRED_REQUIREMENTS = {
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

RUNTIME_PATHS = {
    "gear_manifest": "runtime.reference_gear_manifest_sha256",
    "item_swap": "runtime.item_swap_projection",
    "race": "target.race_id",
    "talents": "target.active_talent_spell_ids",
    "glyphs": "runtime.glyph_identity",
    "flask": "runtime.flask_projection",
    "food": "runtime.food_projection",
    "prepot": "runtime.prepot_projection",
    "combat_potion": "runtime.combat_potion_projection",
    "tinker": "runtime.tinker_projection",
    "racial": "runtime.racial_projection",
    "raid_buffs": "runtime.raid_buffs_projection",
    "target_debuffs": "runtime.target_debuffs_projection",
    "heroism": "runtime.heroism_projection",
    "duration": "runtime.duration_projection",
    "execute": "runtime.execute_projection",
    "fixture_target": "runtime.fixture_target_projection",
    "target_distance": "runtime.target_distance_projection",
    "initial_resources": "runtime.initial_resources_projection",
    "form_presence": "runtime.prepull_setup_projection.form_presence",
    "pet_setup": "runtime.pet_setup_projection",
    "prepull_setup": "runtime.prepull_setup_projection",
}


class ReferenceRequestError(ValueError):
    """A request catalog or one of its immutable inputs is invalid."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ReferenceRequestError(reason)


def _hex_sha256(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "")))


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReferenceRequestError(f"invalid_json:{path}") from exc
    _require(isinstance(value, dict), f"json_object_required:{path}")
    return value


def _absolute(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _repo_file(root: Path, value: Any, label: str) -> Path:
    """Resolve one ordinary repo-relative file without following symlinks."""
    raw = str(value or "")
    relative = Path(raw)
    _require(
        bool(raw)
        and not relative.is_absolute()
        and ".." not in relative.parts,
        f"{label}_path_unsafe",
    )
    resolved_root = root.resolve()
    cursor = resolved_root
    for part in relative.parts:
        cursor /= part
        _require(not cursor.is_symlink(), f"{label}_symlink_forbidden")
    try:
        resolved = cursor.resolve(strict=True)
    except OSError as exc:
        raise ReferenceRequestError(f"{label}_missing:{raw}") from exc
    _require(resolved.is_relative_to(resolved_root), f"{label}_path_escape")
    _require(resolved.is_file(), f"{label}_missing:{raw}")
    return resolved


def _unique_rows(rows: Any, key: str, *, label: str) -> dict[str, Mapping[str, Any]]:
    _require(isinstance(rows, list), f"{label}_must_be_list")
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        _require(isinstance(row, Mapping), f"{label}_row_invalid")
        identity = str(row.get(key) or "")
        _require(identity and identity not in indexed, f"{label}_duplicate:{identity}")
        indexed[identity] = row
    return indexed


def _asset_for_path(reference: Mapping[str, Any], path: str) -> Mapping[str, Any]:
    suffix = f"/{path}"
    matches = [
        row
        for row in reference.get("source_assets") or []
        if isinstance(row, Mapping) and str(row.get("url") or "").endswith(suffix)
    ]
    _require(len(matches) == 1, f"source_asset_not_unique:{path}")
    _require(_hex_sha256(matches[0].get("sha256")), f"source_asset_sha:{path}")
    return matches[0]


def _balanced_go_struct(source: str, marker: str) -> str:
    marker_offset = source.find(marker)
    _require(marker_offset >= 0, "character_suite_config_missing")
    brace = source.find("{", marker_offset + len(marker))
    _require(brace >= 0, "character_suite_config_open_brace_missing")
    depth = 0
    in_string = False
    escaped = False
    for index in range(brace, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[marker_offset : index + 1]
    raise ReferenceRequestError("character_suite_config_unbalanced")


def parse_upstream_suite(source: str) -> dict[str, Any]:
    """Extract only an auditable selector from a checked upstream test.

    Parsed upstream fields are provenance, not live-condition defaults.  The
    generated request obtains setup/options/pet facts from the shared fixture.
    """
    marker = "core.CharacterSuiteConfig"
    block = _balanced_go_struct(source, marker)
    block_offset = source.find(block)
    test_names = re.findall(r"func\s+(Test[A-Za-z0-9_]+)\s*\(", source[:block_offset])
    _require(bool(test_names), "upstream_suite_name_missing")

    def expression(field: str) -> str:
        match = re.search(rf"(?m)^\s*{re.escape(field)}:\s*([^,\n]+)", block)
        return match.group(1).strip() if match else ""

    gear = re.search(r'GearSet:\s*core\.GetGearSet\([^\n]*,\s*"([^"]+)"\s*\)', block)
    rotation = re.search(
        r'Rotation:\s*core\.GetAplRotation\([^\n]*,\s*"([^"]+)"\s*\)', block
    )
    label = re.search(r'SpecOptions:.*?Label:\s*"([^"]+)"', block, re.DOTALL)
    return {
        "suite_name": test_names[-1],
        "character_suite_config_sha256": hashlib.sha256(block.encode("utf-8")).hexdigest(),
        "legacy_tokens": {
            "race_expression": expression("Race"),
            "talents_expression": expression("Talents"),
            "glyphs_expression": expression("Glyphs"),
            "consumables_expression": expression("Consumables"),
            "spec_options_label": label.group(1) if label else "",
            "gear_label": gear.group(1) if gear else "",
            "rotation_label": rotation.group(1) if rotation else "",
            "starting_distance_expression": expression("StartingDistance"),
        },
    }


def _execute_contract(encounter: Mapping[str, Any]) -> dict[str, Any]:
    windows = []
    for row in encounter.get("health_windows") or []:
        _require(isinstance(row, Mapping), "fixture_health_window_invalid")
        lower = int(row.get("lower_pct", -1))
        upper = int(row.get("upper_pct", -1))
        windows.append(
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
    return {
        "schema": "wowsims_cata_single_target_health_schedule_v1",
        "source_authority": "pinned_wowsims_cata_core_test_utils_make_single_target_encounter",
        "source_duration_ms": int(encounter.get("duration_seconds", 0)) * 1_000,
        "source_duration_variation_ms": int(
            encounter.get("duration_variation_seconds", -1)
        )
        * 1_000,
        "source_execute_proportions": dict(encounter.get("execute_proportions") or {}),
        "interval_semantics": "start_inclusive_end_exclusive",
        "fixture_only": True,
        "non_certifying": True,
        "windows": windows,
    }


def _option_leaf_paths(value: Any, prefix: str = "") -> set[str]:
    if isinstance(value, Mapping):
        paths: set[str] = set()
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            paths.update(_option_leaf_paths(child, path))
        return paths
    _require(bool(prefix), "simulator_option_leaf_path_empty")
    return {prefix}


def _fixture_values(
    fixture: Mapping[str, Any], fixture_sha256: str, target_spec: str
) -> dict[str, Any]:
    specs = fixture.get("specs")
    specs = specs if isinstance(specs, Mapping) else {}
    spec = specs.get(target_spec)
    _require(isinstance(spec, Mapping), f"fixture_spec_missing:{target_spec}")
    for key in ("simulator_options", "pet_setup", "prepull_setup"):
        _require(isinstance(spec.get(key), Mapping), f"fixture_{key}_missing:{target_spec}")
    option_classification = spec.get("simulator_option_leaf_classification")
    _require(
        isinstance(option_classification, Mapping)
        and option_classification.get("schema")
        == "phase8_simulator_option_leaf_classification_v1",
        f"fixture_simulator_option_classification_missing:{target_spec}",
    )
    atomic_options = option_classification.get("atomic_runtime_requirements")
    reference_options = option_classification.get("reference_execution_policy")
    unclassified_options = option_classification.get("unclassified")
    _require(
        isinstance(atomic_options, Mapping)
        and isinstance(reference_options, list)
        and unclassified_options == []
        and all(
            isinstance(path, str) and requirement_id in REQUIRED_REQUIREMENTS
            for path, requirement_id in atomic_options.items()
        )
        and all(isinstance(path, str) for path in reference_options)
        and len(reference_options) == len(set(reference_options))
        and not (set(atomic_options) & set(reference_options))
        and set(atomic_options) | set(reference_options)
        == _option_leaf_paths(spec["simulator_options"]),
        f"fixture_simulator_option_classification_invalid:{target_spec}",
    )
    native_request = spec.get("native_request")
    runtime_expected = spec.get("runtime_expected")
    _require(isinstance(native_request, Mapping), f"fixture_native_request_missing:{target_spec}")
    _require(isinstance(runtime_expected, Mapping), f"fixture_runtime_expected_missing:{target_spec}")
    fixture_requirement_ids = set(REQUIRED_REQUIREMENTS) - {
        "gear_manifest",
        "race",
        "talents",
        "glyphs",
    }
    _require(
        fixture_requirement_ids <= set(runtime_expected),
        f"fixture_runtime_expected_incomplete:{target_spec}",
    )
    lane = str(spec.get("lane") or "")
    distances = fixture.get("distance_contracts")
    distances = distances if isinstance(distances, Mapping) else {}
    distance = distances.get(lane)
    _require(isinstance(distance, Mapping), f"fixture_distance_missing:{target_spec}")
    prepull = dict(spec["prepull_setup"])
    required_prepull = {
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
    missing = sorted(required_prepull - set(prepull))
    _require(not missing, f"fixture_prepull_fields_missing:{target_spec}:{','.join(missing)}")
    powers = {
        "player_powers": list(spec.get("player_powers") or []),
        "pet_power": spec.get("pet_power"),
        "runes_ready_mask": spec.get("runes_ready_mask"),
        "combo_points": spec.get("combo_points"),
        "required_absent_auras": list(spec.get("required_absent_auras") or []),
    }
    return {
        "fixture_contract_sha256": fixture_sha256,
        "fixture_target": dict(fixture.get("target") or {}),
        "encounter": dict(fixture.get("encounter") or {}),
        "execute": _execute_contract(dict(fixture.get("encounter") or {})),
        "target_distance": {"lane": lane, **dict(distance)},
        "initial_resources": powers,
        "simulator_options": dict(spec["simulator_options"]),
        "simulator_option_leaf_classification": dict(option_classification),
        "pet_setup": dict(spec["pet_setup"]),
        "prepull_setup": prepull,
        "native_request": dict(native_request),
        "runtime_expected": dict(runtime_expected),
    }


def _glyph_identity(glyph_item_ids: list[int]) -> tuple[dict[str, Any], dict[str, Any]]:
    from tools.bot_ml.phase8_reference_conditions import (
        expected_glyph_runtime_identity,
        glyph_translation_authority,
    )
    authority = glyph_translation_authority()
    public_authority = {
        "schema": authority["schema"],
        "source_file_sha256": authority["source_file_sha256"],
    }
    identity = expected_glyph_runtime_identity(glyph_item_ids)
    _require(bool(identity.get("property_ids")), "glyph_translation_empty")
    return identity, public_authority


@lru_cache(maxsize=1)
def talent_translation_authority() -> dict[str, Any]:
    dbc_dir = TALENT_DBC_SNAPSHOT_DIR.resolve()
    sources = {
        name: file_sha256(dbc_dir / name)
        for name in (
            "Talent.dbc",
            "TalentTab.dbc",
            "TalentTreePrimarySpells.dbc",
        )
    }
    return {
        "schema": "trinity_cata_talent_string_dbc_roundtrip_v1",
        "ordering": "TalentTab.OrderIndex_then_Talent.TierID_ColumnIndex",
        "source_file_sha256": sources,
    }


def decode_talent_string(talent_string: str, class_id: int) -> dict[str, Any]:
    """Decode and round-trip a WoWSims talent string through pinned DBC rows."""
    from tools.bot_ml.build_validation_provisioning import (
        load_wdbc_values,
        talent_data,
    )

    dbc_dir = TALENT_DBC_SNAPSHOT_DIR.resolve()
    _require(bool(re.fullmatch(r"[0-5]*-[0-5]*-[0-5]*", talent_string)), "talent_string_shape")
    talent_tabs = [
        row
        for row in load_wdbc_values(dbc_dir / "TalentTab.dbc", "nxxiiixxxii")
        if int(row[3]) & (1 << (class_id - 1))
    ]
    talent_tabs.sort(key=lambda row: int(row[5]))
    _require(len(talent_tabs) == 3, f"talent_tab_count:{class_id}")
    talents, primary_spells = talent_data(dbc_dir)
    talents_by_tab: dict[int, list[list[Any]]] = {}
    for row in talents.values():
        talents_by_tab.setdefault(int(row[1]), []).append(row)
    segments = talent_string.split("-")
    selected: list[dict[str, int]] = []
    roundtrip_segments: list[str] = []
    points_by_tree: dict[int, int] = {}
    for segment, tab in zip(segments, talent_tabs):
        tab_id = int(tab[0])
        ordered = sorted(
            talents_by_tab.get(tab_id, []),
            key=lambda row: (int(row[2]), int(row[3]), int(row[0])),
        )
        _require(len(segment) <= len(ordered), f"talent_segment_length:{class_id}:{tab_id}")
        digits = [0] * len(ordered)
        for index, character in enumerate(segment):
            rank = int(character)
            row = ordered[index]
            rank_spells = [int(value) for value in row[4:9] if int(value)]
            _require(rank <= len(rank_spells), f"talent_rank:{class_id}:{int(row[0])}")
            digits[index] = rank
            if rank:
                selected.append(
                    {
                        "talent_id": int(row[0]),
                        "rank": rank,
                        "spell_id": rank_spells[rank - 1],
                    }
                )
                points_by_tree[tab_id] = points_by_tree.get(tab_id, 0) + rank
        roundtrip_segments.append("".join(str(value) for value in digits).rstrip("0"))
    normalized_input = "-".join(segment.rstrip("0") for segment in segments)
    roundtrip = "-".join(roundtrip_segments)
    _require(roundtrip == normalized_input, f"talent_string_roundtrip:{class_id}")
    _require(sum(row["rank"] for row in selected) == 41, f"talent_point_count:{class_id}")
    primary_tree_id = max(points_by_tree, key=points_by_tree.get)
    return {
        "talent_string": talent_string,
        "normalized_talent_string": roundtrip,
        "class_id": class_id,
        "primary_talent_tree_id": primary_tree_id,
        "primary_tree_spells": sorted(int(value) for value in primary_spells[primary_tree_id]),
        "selected_talents": sorted(selected, key=lambda row: row["talent_id"]),
        "authority": talent_translation_authority(),
    }


def _requirement(
    requirement_id: str,
    *,
    planned_path: str,
    planned_equals: Any,
    equals: Any,
    static_verifiability: str,
    translation_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "id": requirement_id,
        "condition_class": REQUIRED_REQUIREMENTS[requirement_id],
        "static_verifiability": static_verifiability,
        "planned_path": planned_path,
        "planned_equals": planned_equals,
        "path": RUNTIME_PATHS[requirement_id],
        "equals": equals,
    }
    if translation_authority is not None:
        row["translation_authority"] = dict(translation_authority)
    return row


def request_condition_projection(request: Mapping[str, Any]) -> dict[str, Any]:
    """Project comparison inputs from the request contract itself.

    Generation must additionally project the materialized native protojson and
    prove it equals this object.  Keeping this projection singular prevents a
    request from being paired with a separately authored, more favorable
    comparison manifest.
    """
    player = request.get("player")
    _require(isinstance(player, Mapping), "projection_player_missing")
    prepull = player.get("prepull_setup")
    _require(isinstance(prepull, Mapping), "projection_prepull_missing")
    for key in (
        "flask",
        "food",
        "prepot",
        "combat_potion",
        "tinker",
        "racial",
        "raid_buffs",
        "target_debuffs",
        "heroism",
        "form_presence",
        "item_swap",
    ):
        _require(key in prepull, f"projection_prepull_field_missing:{key}")
    talents = player.get("talents")
    glyphs = player.get("glyphs")
    gear = player.get("gear")
    _require(isinstance(talents, Mapping), "projection_talents_missing")
    _require(isinstance(glyphs, Mapping), "projection_glyphs_missing")
    _require(isinstance(gear, Mapping), "projection_gear_missing")
    encounter = request.get("encounter")
    _require(isinstance(encounter, Mapping), "projection_encounter_missing")
    native_request = request.get("native_request")
    runtime_expected = request.get("runtime_expected")
    _require(isinstance(native_request, Mapping), "projection_native_request_missing")
    _require(isinstance(runtime_expected, Mapping), "projection_runtime_expected_missing")
    gear_identity = {
        key: gear.get(key)
        for key in (
            "gear_profile_id",
            "source_sha256",
            "transform_schema",
            "transformed_manifest_sha256",
            "applicability_authority",
        )
    }
    source_setup = {
        "race": player.get("race_id"),
        "gear": gear_identity,
        "talents": dict(talents),
        "glyphs": dict(glyphs),
        "consumes": native_request.get("consumables"),
        "spec_options": native_request.get("player_spec"),
        "rotation": request.get("rotation"),
        "raid_buffs": native_request.get("raid_buffs"),
        "target_debuffs": native_request.get("target_debuffs"),
        "target_distance_yards": request.get("target_distance"),
        "encounter": dict(encounter),
        "initial_resources": player.get("initial_resources"),
        "item_swap": request.get("item_swap"),
        "fixture_target": request.get("fixture_target"),
        "pet_setup": player.get("pet_setup"),
        "simulator_option_leaf_classification": player.get(
            "simulator_option_leaf_classification"
        ),
        "prepull_setup": dict(prepull),
        "native_request": dict(native_request),
    }
    runtime_equals = {
        "gear_manifest": gear.get("transformed_manifest_sha256"),
        "item_swap": runtime_expected.get("item_swap"),
        "race": player.get("race_id"),
        "talents": sorted(int(value) for value in talents.get("active_spell_ids") or []),
        "glyphs": glyphs.get("runtime_identity"),
        **{
            requirement_id: runtime_expected.get(requirement_id)
            for requirement_id in set(REQUIRED_REQUIREMENTS)
            - {"gear_manifest", "race", "talents", "glyphs", "item_swap"}
        },
    }
    return {
        "source_setup": source_setup,
        "runtime_equals": runtime_equals,
        "projection_sha256": canonical_sha256(
            {"source_setup": source_setup, "runtime_equals": runtime_equals}
        ),
    }


def _source_contract(
    *,
    root: Path,
    target_spec: str,
    reference: Mapping[str, Any],
    fixture_sha256: str,
) -> dict[str, Any]:
    revision = str(reference.get("provider_revision") or "")
    _require(bool(re.fullmatch(r"[0-9a-f]{40}", revision)), f"provider_revision:{target_spec}")
    test_path = str(reference.get("test") or "")
    result_path = str(reference.get("results") or "")
    gear = reference.get("gear")
    gear = gear if isinstance(gear, Mapping) else {}
    snapshot_value = str(gear.get("numeric_fixture_test_snapshot") or "")
    snapshot_path = _repo_file(root, snapshot_value, f"test_snapshot:{target_spec}")
    test_asset = _asset_for_path(reference, test_path)
    result_asset = _asset_for_path(reference, result_path)
    snapshot_sha = file_sha256(snapshot_path)
    _require(snapshot_sha == test_asset.get("sha256"), f"test_snapshot_sha:{target_spec}")
    try:
        source = snapshot_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ReferenceRequestError(f"test_snapshot_utf8:{target_spec}") from exc
    parsed = parse_upstream_suite(source)
    expected_output = reference.get("expected_output")
    expected_output = expected_output if isinstance(expected_output, Mapping) else {}
    legacy_result_key = str(expected_output.get("result_key") or "")
    _require(bool(legacy_result_key), f"legacy_result_key_missing:{target_spec}")
    return {
        "schema": SOURCE_CONTRACT_SCHEMA,
        "target_spec": target_spec,
        "repository": str(reference.get("repository") or ""),
        "provider_revision": revision,
        "fixture_contract_sha256": fixture_sha256,
        "upstream_test": {
            "path": test_path,
            "snapshot_path": snapshot_value,
            "sha256": snapshot_sha,
            **parsed,
        },
        "upstream_results": {
            "path": result_path,
            "sha256": result_asset["sha256"],
            "legacy_result_key": legacy_result_key,
            "usage": "provenance_only_not_an_acceptance_denominator",
        },
    }


def _build_row(
    *,
    root: Path,
    target_spec: str,
    target: Mapping[str, Any],
    reference: Mapping[str, Any],
    gear_profile: Mapping[str, Any],
    slot_map: list[int],
    fixture: Mapping[str, Any],
    fixture_sha256: str,
) -> dict[str, Any]:
    _require(target.get("spec_target_id") == target_spec, f"target_identity:{target_spec}")
    _require(reference.get("spec_target_id") == target_spec, f"reference_identity:{target_spec}")
    provisioning = target.get("provisioning_bot")
    provisioning = provisioning if isinstance(provisioning, Mapping) else {}
    gear = reference.get("gear")
    gear = gear if isinstance(gear, Mapping) else {}
    profile_source = gear_profile.get("source")
    profile_source = profile_source if isinstance(profile_source, Mapping) else {}
    gear_profile_id = str(target.get("gear_profile_id") or "")
    _require(gear_profile_id == gear.get("gear_profile_id"), f"gear_profile_join:{target_spec}")
    _require(profile_source.get("sha256") == gear.get("source_sha256"), f"gear_source_join:{target_spec}")
    transformed_sha = str(gear_profile.get("transformed_manifest_sha256") or "")
    _require(
        _hex_sha256(transformed_sha)
        and transformed_sha == gear.get("transformed_manifest_sha256"),
        f"gear_transform_join:{target_spec}",
    )
    fixture_values = _fixture_values(fixture, fixture_sha256, target_spec)
    source_contract = _source_contract(
        root=root,
        target_spec=target_spec,
        reference=reference,
        fixture_sha256=fixture_sha256,
    )
    source_contract_sha = canonical_sha256(source_contract)
    glyph_item_ids = [int(value) for value in target.get("glyph_item_ids") or []]
    glyph_runtime, glyph_authority = _glyph_identity(glyph_item_ids)
    talents = reference.get("talents")
    talents = talents if isinstance(talents, Mapping) else {}
    talent_rows = list((target.get("talent_build") or {}).get("talents") or [])
    active_talent_spell_ids = sorted(int(row["spell_id"]) for row in talent_rows)
    _require(bool(talents.get("talent_string")), f"talent_string_missing:{target_spec}")
    talent_identity = decode_talent_string(
        str(talents.get("talent_string") or ""), int(target.get("class_id") or 0)
    )
    decoded_target_projection = [
        {"talent_id": row["talent_id"], "spell_id": row["spell_id"]}
        for row in talent_identity["selected_talents"]
    ]
    target_talent_build = target.get("talent_build") or {}
    _require(
        decoded_target_projection == sorted(talent_rows, key=lambda row: row["talent_id"])
        and talent_identity["primary_talent_tree_id"]
        == target_talent_build.get("primary_talent_tree_id")
        and talent_identity["primary_tree_spells"]
        == sorted(int(value) for value in target_talent_build.get("primary_tree_spells") or []),
        f"talent_string_target_roundtrip:{target_spec}",
    )
    rotation_path = str((reference.get("apl") or {}).get("path") or "")
    rotation_asset = _asset_for_path(reference, rotation_path)
    gear_identity = {
        "gear_profile_id": gear_profile_id,
        "source_sha256": str(profile_source.get("sha256") or ""),
        "source_path": str(profile_source.get("path") or ""),
        "source_snapshot": str(profile_source.get("snapshot") or ""),
        "transform_schema": str(gear.get("transform_schema") or ""),
        "transformed_manifest_sha256": transformed_sha,
        "applicability_authority": str(
            gear.get("permanent_enchant_applicability_authority") or ""
        ),
    }
    prepull = fixture_values["prepull_setup"]
    racial = prepull["racial"]
    _require(
        isinstance(racial, Mapping)
        and int(racial.get("race_id") or 0) == int(provisioning.get("race") or 0),
        f"fixture_race_mismatch:{target_spec}",
    )
    _require(
        int((prepull["prepot"] or {}).get("item_id") or 0) == 0
        and int((prepull["combat_potion"] or {}).get("item_id") or 0) == 0
        and int((prepull["tinker"] or {}).get("item_id") or 0) == 0
        and int(racial.get("spell_id") or 0) == 0,
        f"unsupported_dynamic_consume_enabled:{target_spec}",
    )
    flask = prepull["flask"]
    food = prepull["food"]
    _require(
        int((flask or {}).get("item_id") or 0) > 0
        and int((flask or {}).get("observed_aura_spell_id") or 0) > 0,
        f"fixed_flask_incomplete:{target_spec}",
    )
    food_enabled = target_spec in FIXED_FOOD_SPECS
    _require(
        (int((food or {}).get("item_id") or 0) > 0) is food_enabled
        and (int((food or {}).get("observed_aura_spell_id") or 0) > 0)
        is food_enabled,
        f"fixed_food_policy:{target_spec}",
    )
    request = {
        "schema": REQUEST_SCHEMA,
        "target_spec": target_spec,
        "fixture_contract_sha256": fixture_sha256,
        "source_contract_sha256": source_contract_sha,
        "source_selector": {
            "test_path": source_contract["upstream_test"]["path"],
            "suite_name": source_contract["upstream_test"]["suite_name"],
            "legacy_result_key": source_contract["upstream_results"]["legacy_result_key"],
            "usage": "materialization_scaffold_only_all_live_conditions_overridden",
        },
        "sim_options": {
            "iterations": EXPECTED_ITERATIONS,
            "random_seed": EXPECTED_RANDOM_SEED,
            "debug": False,
            "is_test": True,
        },
        "player": {
            "level": 85,
            "class_id": int(target.get("class_id") or 0),
            "race_id": int(provisioning.get("race") or 0),
            "talents": {
                "talent_string": str(talents.get("talent_string") or ""),
                "active_spell_ids": active_talent_spell_ids,
                "decoded_talents": talent_identity["selected_talents"],
                "primary_talent_tree_id": talent_identity["primary_talent_tree_id"],
                "primary_tree_spells": talent_identity["primary_tree_spells"],
                "translation_authority": talent_identity["authority"],
            },
            "glyphs": {
                "item_ids": glyph_item_ids,
                "runtime_identity": glyph_runtime,
                "translation_authority": glyph_authority,
            },
            "gear": {
                **gear_identity,
                "slot_map": slot_map,
                "wowsims_items": list(gear_profile.get("items") or []),
            },
            "simulator_options": fixture_values["simulator_options"],
            "simulator_option_leaf_classification": fixture_values[
                "simulator_option_leaf_classification"
            ],
            "pet_setup": fixture_values["pet_setup"],
            "initial_resources": fixture_values["initial_resources"],
            "prepull_setup": prepull,
        },
        "rotation": {
            "path": rotation_path,
            "sha256": rotation_asset["sha256"],
            "policy": "pinned_upstream_apl_benchmark_policy",
        },
        "raid_buffs": fixture_values["native_request"]["raid_buffs"],
        "target_debuffs": fixture_values["native_request"]["target_debuffs"],
        "encounter": fixture_values["encounter"],
        "fixture_target": fixture_values["fixture_target"],
        "target_distance": fixture_values["target_distance"],
        "item_swap": prepull["item_swap"],
        "native_request": fixture_values["native_request"],
        "runtime_expected": fixture_values["runtime_expected"],
    }
    request_sha = canonical_sha256(request)
    projection = request_condition_projection(request)
    source_setup = projection["source_setup"]
    planned_talent_rows = list((target.get("talent_build") or {}).get("talents") or [])
    requirement_values = projection["runtime_equals"]
    requirements = []
    for requirement_id in REQUIRED_REQUIREMENTS:
        if requirement_id == "gear_manifest":
            planned_path = "reference.gear.transformed_manifest_sha256"
            planned_equals = transformed_sha
            verifiability = "catalog_exact"
        elif requirement_id == "race":
            planned_path = "target.provisioning_bot.race"
            planned_equals = request["player"]["race_id"]
            verifiability = "catalog_exact"
        elif requirement_id == "talents":
            planned_path = "target.talent_build.talents"
            planned_equals = planned_talent_rows
            verifiability = "catalog_exact"
        elif requirement_id == "glyphs":
            planned_path = "target.glyph_item_ids"
            planned_equals = glyph_item_ids
            verifiability = "catalog_exact"
        else:
            planned_path = f"fixture.runtime_expected.{requirement_id}"
            planned_equals = fixture_values["runtime_expected"][requirement_id]
            verifiability = "fixture_contract_exact"
        requirements.append(
            _requirement(
                requirement_id,
                planned_path=planned_path,
                planned_equals=planned_equals,
                equals=requirement_values[requirement_id],
                static_verifiability=verifiability,
                translation_authority=(
                    glyph_authority
                    if requirement_id == "glyphs"
                    else talent_identity["authority"]
                    if requirement_id == "talents"
                    else None
                ),
            )
        )
    source_setup_sha = canonical_sha256(source_setup)
    comparison = {
        "schema": COMPARISON_SCHEMA,
        "target_spec": target_spec,
        "result_status": RESULT_PENDING,
        "reference_result_key": None,
        "reference_dps": None,
        "source_contract_sha256": source_contract_sha,
        "request_sha256": request_sha,
        "fixture_contract_sha256": fixture_sha256,
        "source_setup": source_setup,
        "source_setup_sha256": source_setup_sha,
        "request_condition_projection_sha256": projection["projection_sha256"],
        "requirements": requirements,
    }
    return {
        "target_spec": target_spec,
        "source_contract": source_contract,
        "source_contract_sha256": source_contract_sha,
        "request": request,
        "request_sha256": request_sha,
        "result": {
            "status": RESULT_PENDING,
            "result_key": None,
            "dps": None,
            "artifacts": {
                "request_contract_sha256": request_sha,
                "native_request": {"path": None, "sha256": None, "byte_count": None},
                "native_result": {"path": None, "sha256": None, "byte_count": None},
                "build_receipt": {"path": None, "sha256": None, "byte_count": None},
                "generation_receipt": {"path": None, "sha256": None, "byte_count": None},
                "dvc_reconstruction_receipt": {
                    "path": None,
                    "sha256": None,
                    "byte_count": None,
                },
            },
        },
        "comparison_manifest": comparison,
    }


def build_manifest(
    *,
    root: Path = ROOT,
    acceptance_path: Path | None = None,
    fixture_path: Path | None = None,
    gear_path: Path | None = None,
) -> dict[str, Any]:
    acceptance_path = acceptance_path or root / DEFAULT_ACCEPTANCE_PATH.relative_to(ROOT)
    fixture_path = fixture_path or root / DEFAULT_FIXTURE_PATH.relative_to(ROOT)
    gear_path = gear_path or root / DEFAULT_GEAR_PATH.relative_to(ROOT)
    acceptance = _load_json(acceptance_path)
    target_catalog = _load_json(_absolute(root, str(acceptance.get("target_catalog") or "")))
    reference_catalog = _load_json(
        _absolute(root, str(acceptance.get("reference_catalog") or ""))
    )
    gear_catalog = _load_json(gear_path)
    from tools.bot_ml.phase8_fixture_contract import load_fixture_contract

    fixture, fixture_sha256 = load_fixture_contract(fixture_path)
    targets = _unique_rows(target_catalog.get("targets"), "spec_target_id", label="targets")
    references = _unique_rows(
        reference_catalog.get("references"), "spec_target_id", label="references"
    )
    profiles = gear_catalog.get("profiles")
    _require(isinstance(profiles, Mapping), "gear_profiles_invalid")
    raw_slot_map = gear_catalog.get("slot_map")
    _require(isinstance(raw_slot_map, list), "gear_slot_map_invalid")
    slot_map = [int(value) for value in raw_slot_map]
    target_specs = list(acceptance.get("dps_targets") or [])
    _require(
        len(target_specs) == int(acceptance.get("supported_dps_spec_count") or 0)
        and len(target_specs) == len(set(target_specs)) == 16,
        "acceptance_dps_spec_set_invalid",
    )
    rows = []
    for target_spec in sorted(str(value) for value in target_specs):
        _require(target_spec in targets, f"target_missing:{target_spec}")
        _require(target_spec in references, f"reference_missing:{target_spec}")
        profile_id = str(targets[target_spec].get("gear_profile_id") or "")
        profile = profiles.get(profile_id)
        _require(isinstance(profile, Mapping), f"gear_profile_missing:{target_spec}")
        rows.append(
            _build_row(
                root=root,
                target_spec=target_spec,
                target=targets[target_spec],
                reference=references[target_spec],
                gear_profile=profile,
                slot_map=slot_map,
                fixture=fixture,
                fixture_sha256=fixture_sha256,
            )
        )
    manifest = {
        "schema": CATALOG_SCHEMA,
        "provider": "WoWSims",
        "provider_repository": "https://github.com/wowsims/cata",
        "provider_revision": rows[0]["source_contract"]["provider_revision"],
        "fixture_contract_path": str(fixture_path.relative_to(root)),
        "fixture_contract_sha256": fixture_sha256,
        "request_count": len(rows),
        "requests": rows,
    }
    validate_manifest(manifest, root=root, verify_generated_artifacts=False)
    return manifest


def _read_hashed_json(root: Path, artifact: Any, label: str) -> Any:
    artifact = artifact if isinstance(artifact, Mapping) else {}
    path_value = artifact.get("path")
    expected_sha = artifact.get("sha256")
    _require(isinstance(path_value, str) and bool(path_value), f"{label}_path_missing")
    path = _repo_file(root, path_value, label)
    _require(file_sha256(path) == expected_sha, f"{label}_sha256")
    if "byte_count" in artifact:
        _require(path.stat().st_size == artifact.get("byte_count"), f"{label}_byte_count")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReferenceRequestError(f"{label}_json") from exc


def _validate_generated_result(
    row: Mapping[str, Any], *, root: Path
) -> dict[str, Any]:
    """Reject a generated result unless its immutable evidence is hydrated.

    The execution tool owns the native schemas.  This validator nevertheless
    opens every claimed file and checks the cross-document transport facts;
    embedded hashes or DPS values are never sufficient by themselves.
    """
    request = row["request"]
    result = row["result"]
    artifacts = result.get("artifacts") or {}
    generation_receipt = _read_hashed_json(
        root, artifacts.get("generation_receipt"), "generation_receipt"
    )
    _require(canonical_sha256(request) == row.get("request_sha256"), "request_hash_drift")
    from tools.bot_ml.run_wowsims_exact_references import (
        validate_generation_receipt,
    )
    generation_receipt_path = _repo_file(
        root,
        (artifacts.get("generation_receipt") or {}).get("path"),
        "generation_receipt",
    )
    verified_receipt = validate_generation_receipt(
        generation_receipt_path,
        require_dvc_reconstruction=False,
    )
    reconstruction = _read_hashed_json(
        root,
        artifacts.get("dvc_reconstruction_receipt"),
        "dvc_reconstruction_receipt",
    )
    reconstruction_path = _repo_file(
        root,
        (artifacts.get("dvc_reconstruction_receipt") or {}).get("path"),
        "dvc_reconstruction_receipt",
    )
    generation_root = generation_receipt_path.resolve().parent.parent

    def nested_artifact_matches(name: str) -> bool:
        receipt_artifact = verified_receipt.get(name) or {}
        promoted_artifact = artifacts.get(name) or {}
        receipt_path = generation_root / str(receipt_artifact.get("path") or "")
        promoted_path = _repo_file(
            root, promoted_artifact.get("path"), f"generated_{name}"
        )
        return (
            receipt_path.resolve() == promoted_path.resolve()
            and file_sha256(promoted_path)
            == receipt_artifact.get("sha256")
            == promoted_artifact.get("sha256")
            and promoted_path.stat().st_size
            == receipt_artifact.get("byte_count")
            == promoted_artifact.get("byte_count")
        )

    _require(
        verified_receipt == generation_receipt
        and verified_receipt.get("request_contract_sha256")
        == row.get("request_sha256")
        and verified_receipt.get("source_revision")
        == row["source_contract"].get("provider_revision")
        and nested_artifact_matches("native_request")
        and nested_artifact_matches("native_result")
        and nested_artifact_matches("build_receipt"),
        "generated_receipt_identity",
    )
    observation = verified_receipt.get("result_observation") or {}
    native_dps = observation.get("dps")
    _require(
        isinstance(native_dps, (int, float))
        and math.isfinite(float(native_dps))
        and float(native_dps) > 0
        and float(native_dps) == float(result.get("dps") or 0),
        "generated_dps_not_native",
    )
    return {
        "target_spec": row.get("target_spec"),
        "generation_receipt_path": generation_receipt_path,
        "dvc_reconstruction_receipt_path": reconstruction_path,
        "dvc_reconstruction_receipt": reconstruction,
        "publication_domain": result.get("publication_domain"),
    }


def pending_catalog_projection(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct the exact all-pending catalog identity before promotion."""
    pending = copy.deepcopy(dict(manifest))
    for row in pending.get("requests") or []:
        request_sha = row.get("request_sha256")
        row["result"] = {
            "status": RESULT_PENDING,
            "result_key": None,
            "dps": None,
            "artifacts": {
                "request_contract_sha256": request_sha,
                "native_request": {"path": None, "sha256": None, "byte_count": None},
                "native_result": {"path": None, "sha256": None, "byte_count": None},
                "build_receipt": {"path": None, "sha256": None, "byte_count": None},
                "generation_receipt": {
                    "path": None,
                    "sha256": None,
                    "byte_count": None,
                },
                "dvc_reconstruction_receipt": {
                    "path": None,
                    "sha256": None,
                    "byte_count": None,
                },
            },
        }
        comparison = row.get("comparison_manifest") or {}
        comparison["result_status"] = RESULT_PENDING
        comparison["reference_result_key"] = None
        comparison["reference_dps"] = None
    return pending


def validate_manifest(
    manifest: Mapping[str, Any],
    *,
    root: Path = ROOT,
    verify_generated_artifacts: bool = True,
) -> None:
    _require(manifest.get("schema") == CATALOG_SCHEMA, "catalog_schema")
    revision = str(manifest.get("provider_revision") or "")
    _require(bool(re.fullmatch(r"[0-9a-f]{40}", revision)), "catalog_provider_revision")
    fixture_sha = str(manifest.get("fixture_contract_sha256") or "")
    _require(_hex_sha256(fixture_sha), "catalog_fixture_hash")
    fixture_path_value = str(manifest.get("fixture_contract_path") or "")
    fixture_path = _repo_file(root, fixture_path_value, "catalog_fixture")
    from tools.bot_ml.phase8_fixture_contract import load_fixture_contract

    fixture_document, actual_fixture_sha = load_fixture_contract(fixture_path)
    _require(actual_fixture_sha == fixture_sha, "catalog_fixture_bytes")
    requests = manifest.get("requests")
    _require(isinstance(requests, list), "requests_must_be_list")
    _require(len(requests) == manifest.get("request_count") == 16, "request_count")
    seen: set[str] = set()
    result_statuses: set[str] = set()
    generated_evidence: list[dict[str, Any]] = []
    for row in requests:
        _require(isinstance(row, Mapping), "request_row_invalid")
        target_spec = str(row.get("target_spec") or "")
        _require(target_spec and target_spec not in seen, f"request_duplicate:{target_spec}")
        seen.add(target_spec)
        source = row.get("source_contract")
        request = row.get("request")
        result = row.get("result")
        comparison = row.get("comparison_manifest")
        _require(isinstance(source, Mapping), f"source_contract:{target_spec}")
        _require(isinstance(request, Mapping), f"request:{target_spec}")
        _require(isinstance(result, Mapping), f"result:{target_spec}")
        _require(isinstance(comparison, Mapping), f"comparison:{target_spec}")
        source_sha = canonical_sha256(source)
        request_sha = canonical_sha256(request)
        _require(source_sha == row.get("source_contract_sha256"), f"source_hash:{target_spec}")
        _require(request_sha == row.get("request_sha256"), f"request_hash:{target_spec}")
        _require(source.get("provider_revision") == revision, f"source_revision:{target_spec}")
        _require(source.get("target_spec") == target_spec, f"source_spec:{target_spec}")
        upstream_test = source.get("upstream_test")
        _require(isinstance(upstream_test, Mapping), f"upstream_test:{target_spec}")
        snapshot_value = str(upstream_test.get("snapshot_path") or "")
        snapshot_path = _repo_file(
            root, snapshot_value, f"upstream_test:{target_spec}"
        )
        _require(
            file_sha256(snapshot_path) == upstream_test.get("sha256"),
            f"upstream_test_sha:{target_spec}",
        )
        parsed_suite = parse_upstream_suite(snapshot_path.read_text(encoding="utf-8"))
        _require(
            parsed_suite["suite_name"] == upstream_test.get("suite_name")
            and parsed_suite["character_suite_config_sha256"]
            == upstream_test.get("character_suite_config_sha256"),
            f"upstream_test_selector:{target_spec}",
        )
        _require(request.get("schema") == REQUEST_SCHEMA, f"request_schema:{target_spec}")
        _require(request.get("target_spec") == target_spec, f"request_spec:{target_spec}")
        _require(request.get("fixture_contract_sha256") == fixture_sha, f"request_fixture:{target_spec}")
        _require(request.get("source_contract_sha256") == source_sha, f"request_source:{target_spec}")
        fixture_specs = fixture_document.get("specs")
        fixture_specs = fixture_specs if isinstance(fixture_specs, Mapping) else {}
        fixture_spec = fixture_specs.get(target_spec)
        _require(isinstance(fixture_spec, Mapping), f"fixture_spec:{target_spec}")
        fixture_lane = str(fixture_spec.get("lane") or "")
        fixture_distances = fixture_document.get("distance_contracts") or {}
        _require(
            request.get("native_request") == fixture_spec.get("native_request")
            and request.get("runtime_expected") == fixture_spec.get("runtime_expected")
            and request.get("encounter") == fixture_document.get("encounter")
            and request.get("fixture_target") == fixture_document.get("target")
            and request.get("target_distance")
            == {"lane": fixture_lane, **dict(fixture_distances.get(fixture_lane) or {})},
            f"request_fixture_projection:{target_spec}",
        )
        sim_options = request.get("sim_options")
        _require(
            isinstance(sim_options, Mapping)
            and sim_options.get("iterations") == EXPECTED_ITERATIONS
            and sim_options.get("random_seed") == EXPECTED_RANDOM_SEED,
            f"request_sim_options:{target_spec}",
        )
        _require(request.get("item_swap") == {"enabled": False, "items": []}, f"item_swap:{target_spec}")
        player = request.get("player")
        _require(isinstance(player, Mapping), f"request_player:{target_spec}")
        _require(isinstance(player.get("simulator_options"), Mapping), f"simulator_options:{target_spec}")
        _require(
            isinstance(player.get("simulator_option_leaf_classification"), Mapping),
            f"simulator_option_classification:{target_spec}",
        )
        _require(isinstance(player.get("pet_setup"), Mapping), f"pet_setup:{target_spec}")
        _require(
            player.get("simulator_options") == fixture_spec.get("simulator_options")
            and player.get("simulator_option_leaf_classification")
            == fixture_spec.get("simulator_option_leaf_classification")
            and player.get("pet_setup") == fixture_spec.get("pet_setup")
            and player.get("prepull_setup") == fixture_spec.get("prepull_setup"),
            f"request_fixture_player_projection:{target_spec}",
        )
        request_talents = player.get("talents")
        _require(isinstance(request_talents, Mapping), f"request_talents:{target_spec}")
        decoded_talents = decode_talent_string(
            str(request_talents.get("talent_string") or ""),
            int(player.get("class_id") or 0),
        )
        _require(
            request_talents.get("decoded_talents")
            == decoded_talents["selected_talents"]
            and request_talents.get("active_spell_ids")
            == sorted(
                row["spell_id"] for row in decoded_talents["selected_talents"]
            )
            and request_talents.get("primary_talent_tree_id")
            == decoded_talents["primary_talent_tree_id"]
            and request_talents.get("primary_tree_spells")
            == decoded_talents["primary_tree_spells"]
            and request_talents.get("translation_authority")
            == decoded_talents["authority"],
            f"request_talent_roundtrip:{target_spec}",
        )
        request_gear = player.get("gear")
        _require(isinstance(request_gear, Mapping), f"request_gear:{target_spec}")
        gear_snapshot_value = str(request_gear.get("source_snapshot") or "")
        gear_snapshot_path = _repo_file(
            root, gear_snapshot_value, f"request_gear_snapshot:{target_spec}"
        )
        _require(
            file_sha256(gear_snapshot_path) == request_gear.get("source_sha256"),
            f"request_gear_snapshot_sha:{target_spec}",
        )
        gear_snapshot = _load_json(gear_snapshot_path)
        _require(
            gear_snapshot.get("items") == request_gear.get("wowsims_items"),
            f"request_gear_items:{target_spec}",
        )
        from tools.bot_ml.wowsims_gear_binding import canonical_wowsims_manifest
        canonical_gear = canonical_wowsims_manifest(
            {"items": request_gear.get("wowsims_items")},
            [int(value) for value in request_gear.get("slot_map") or []],
        )
        _require(
            canonical_sha256(canonical_gear)
            == request_gear.get("transformed_manifest_sha256"),
            f"request_gear_transform:{target_spec}",
        )
        _require(comparison.get("schema") == COMPARISON_SCHEMA, f"comparison_schema:{target_spec}")
        _require(comparison.get("target_spec") == target_spec, f"comparison_spec:{target_spec}")
        _require(comparison.get("source_contract_sha256") == source_sha, f"comparison_source:{target_spec}")
        _require(comparison.get("request_sha256") == request_sha, f"comparison_request:{target_spec}")
        _require(comparison.get("fixture_contract_sha256") == fixture_sha, f"comparison_fixture:{target_spec}")
        source_setup = comparison.get("source_setup")
        _require(isinstance(source_setup, Mapping), f"source_setup:{target_spec}")
        _require(
            canonical_sha256(source_setup) == comparison.get("source_setup_sha256"),
            f"source_setup_hash:{target_spec}",
        )
        projected = request_condition_projection(request)
        _require(
            source_setup == projected["source_setup"]
            and comparison.get("request_condition_projection_sha256")
            == projected["projection_sha256"],
            f"request_comparison_projection:{target_spec}",
        )
        requirements = comparison.get("requirements")
        _require(isinstance(requirements, list), f"requirements:{target_spec}")
        by_id = {
            row.get("id"): row for row in requirements if isinstance(row, Mapping)
        }
        _require(set(by_id) == set(REQUIRED_REQUIREMENTS), f"requirement_coverage:{target_spec}")
        _require(len(by_id) == len(requirements), f"requirement_duplicates:{target_spec}")
        for requirement_id, condition_class in REQUIRED_REQUIREMENTS.items():
            requirement = by_id[requirement_id]
            _require(
                requirement.get("condition_class") == condition_class
                and "planned_equals" in requirement
                and "equals" in requirement
                and requirement.get("path") == RUNTIME_PATHS[requirement_id]
                and requirement.get("static_verifiability")
                in {"catalog_exact", "target_capability", "fixture_contract_exact"},
                f"requirement_invalid:{target_spec}:{requirement_id}",
            )
            _require(
                requirement.get("equals")
                == projected["runtime_equals"][requirement_id],
                f"requirement_not_projected:{target_spec}:{requirement_id}",
            )
        result_status = result.get("status")
        _require(result_status in {RESULT_PENDING, RESULT_ACCEPTED}, f"result_status:{target_spec}")
        result_statuses.add(str(result_status))
        _require(comparison.get("result_status") == result_status, f"result_projection:{target_spec}")
        artifacts = result.get("artifacts")
        _require(isinstance(artifacts, Mapping), f"result_artifacts:{target_spec}")
        _require(
            artifacts.get("request_contract_sha256") == request_sha,
            f"result_request_hash:{target_spec}",
        )
        if result_status == RESULT_PENDING:
            _require(
                result.get("result_key") is None
                and result.get("dps") is None
                and comparison.get("reference_result_key") is None
                and comparison.get("reference_dps") is None,
                f"pending_result_has_values:{target_spec}",
            )
        else:
            _require(
                isinstance(result.get("result_key"), str)
                and bool(result.get("result_key"))
                and isinstance(result.get("dps"), (int, float))
                and float(result["dps"]) > 0
                and comparison.get("reference_result_key") == result.get("result_key")
                and comparison.get("reference_dps") == result.get("dps"),
                f"generated_result_projection:{target_spec}",
            )
            _require(
                result.get("authority_scope") == "offline_denominator_only"
                and result.get("live_fixture_join_status")
                == "pending_physical_raw_capture",
                f"generated_result_scope:{target_spec}",
            )
            if verify_generated_artifacts:
                generated_evidence.append(_validate_generated_result(row, root=root))
    _require(
        len(result_statuses) == 1,
        "mixed_pending_and_generated_reference_cohort_forbidden",
    )
    if result_statuses == {RESULT_ACCEPTED} and verify_generated_artifacts:
        _require(len(generated_evidence) == 16, "generated_evidence_cohort_count")
        publication_domains = [row.get("publication_domain") for row in generated_evidence]
        _require(
            all(isinstance(value, Mapping) for value in publication_domains)
            and all(value == publication_domains[0] for value in publication_domains),
            "generated_publication_domain_mismatch",
        )
        publication = publication_domains[0]
        _require(
            set(publication)
            == {
                "repository_url",
                "repository_revision",
                "dvc_pointer_path",
                "bundle_root",
                "pending_request_catalog_sha256",
                "control_plane_policy",
            }
            and publication.get("control_plane_policy")
            == "commit_a_pointer_then_commit_b_reconstruction_receipt_and_promotion"
            and publication.get("pending_request_catalog_sha256")
            == canonical_sha256(pending_catalog_projection(manifest)),
            "generated_publication_domain_invalid",
        )
        reconstruction_paths = {
            row["dvc_reconstruction_receipt_path"].resolve()
            for row in generated_evidence
        }
        reconstruction_payloads = [
            row["dvc_reconstruction_receipt"] for row in generated_evidence
        ]
        _require(
            len(reconstruction_paths) == 1
            and all(value == reconstruction_payloads[0] for value in reconstruction_payloads),
            "generated_dvc_reconstruction_not_common",
        )
        from tools.bot_ml.run_wowsims_exact_references import (
            validate_dvc_reconstruction_receipt,
        )

        verified_reconstruction = validate_dvc_reconstruction_receipt(
            next(iter(reconstruction_paths)),
            expected_generation_receipt_paths=[
                row["generation_receipt_path"]
                for row in sorted(
                    generated_evidence, key=lambda value: str(value["target_spec"])
                )
            ],
            expected_repository_root=root,
            expected_repository_url=str(publication["repository_url"]),
            expected_repository_revision=str(publication["repository_revision"]),
            expected_dvc_pointer_path=str(publication["dvc_pointer_path"]),
            expected_bundle_root=str(publication["bundle_root"]),
        )
        _require(
            verified_reconstruction == reconstruction_payloads[0],
            "dvc_reconstruction_identity",
        )


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or DEFAULT_OUTPUT_PATH
    manifest = _load_json(manifest_path)
    validate_manifest(manifest, root=ROOT)
    return manifest


def request_by_spec(manifest: Mapping[str, Any], target_spec: str) -> dict[str, Any]:
    validate_manifest(manifest, verify_generated_artifacts=False)
    rows = [row for row in manifest["requests"] if row.get("target_spec") == target_spec]
    _require(len(rows) == 1, f"request_not_unique:{target_spec}")
    return dict(rows[0])


def _render(manifest: Mapping[str, Any]) -> str:
    return json.dumps(manifest, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    manifest = build_manifest()
    rendered = _render(manifest)
    if args.check:
        try:
            existing = args.output.read_text(encoding="utf-8")
        except OSError as exc:
            raise SystemExit(f"missing generated manifest: {args.output}") from exc
        if existing != rendered:
            raise SystemExit(f"generated manifest is stale: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
