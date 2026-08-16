"""Fail-closed identity and local-legality checks for pinned WoWSims gear."""

from __future__ import annotations

import csv
import functools
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .build_validation_gear_profiles import (
    INVENTORY_TO_EQUIPMENT_SLOTS,
    SPELL_ITEM_ENCHANTMENT_FMT,
    armor_allowed,
    class_allowed,
    item_player_accessible,
    load_db2_item_rows,
    load_wdbc,
    weapon_slot_allowed,
)
from .build_validation_provisioning import (
    gem_item_enchant_map,
    load_wdbc_values,
)


WOWSIMS_REPOSITORY = "https://github.com/wowsims/cata"
TRANSFORM_SCHEMA = "wowsims_cata_equipment_manifest_v1"
ENCHANT_APPLICABILITY_AUTHORITY = "pinned_wowsims_preset_exact"
REPO_ROOT = Path(__file__).resolve().parents[2]
HOTFIX_ITEM_TEMPLATE_SOURCE = (
    REPO_ROOT
    / "sql/old/4.3.4/TDB00_to_TDB01_updates/world/096_item_template.sql"
)
PRIMARY_GEAR_SET_PATTERN = re.compile(
    r'GearSet:\s*core\.GetGearSet\(\s*"[^"]+",\s*"([^"]+)"\s*\)'
)

# These player-obtainable items are supplied by Trinity's checked-in 4.3.4
# hotfix rows rather than the client Item.db2 snapshot.  Keep this small and
# attributable to the exact SQL rows; never infer missing item metadata.
HOTFIX_ITEM_ROWS: dict[int, dict[str, Any]] = {
    71086: {
        "ID": 71086,
        "ClassID": 2,
        "SubclassID": 10,
        "InventoryType": 17,
        "Display": "Dragonwrath, Tarecgosa's Rest",
        "ItemLevel": 397,
        "RequiredLevel": 85,
        "AllowableClass": 0,
    },
    77949: {
        "ID": 77949,
        "ClassID": 2,
        "SubclassID": 15,
        "InventoryType": 21,
        "Display": "Golad, Twilight of Aspects",
        "ItemLevel": 416,
        "RequiredLevel": 85,
        "AllowableClass": 0,
    },
    77950: {
        "ID": 77950,
        "ClassID": 2,
        "SubclassID": 15,
        "InventoryType": 22,
        "Display": "Tiriosh, Nightmare of Ages",
        "ItemLevel": 416,
        "RequiredLevel": 85,
        "AllowableClass": 0,
    },
    78369: {
        "ID": 78369,
        "ClassID": 2,
        "SubclassID": 16,
        "InventoryType": 25,
        "Display": "Razor Saronite Chip",
        "ItemLevel": 410,
        "RequiredLevel": 85,
        "AllowableClass": 1535,
    },
}


@functools.lru_cache(maxsize=1)
def validated_hotfix_item_rows() -> dict[int, dict[str, Any]]:
    """Load the small client-DB2 gap from Trinity's exact SQL item rows."""
    rows: dict[int, dict[str, Any]] = {}
    for line in HOTFIX_ITEM_TEMPLATE_SOURCE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("(") or ")," not in stripped:
            continue
        values = next(
            csv.reader(
                [stripped[1 : stripped.rfind("),")]],
                delimiter=",",
                quotechar="'",
                doublequote=True,
                skipinitialspace=True,
            )
        )
        try:
            item_id = int(values[0])
        except (IndexError, ValueError):
            continue
        if item_id not in HOTFIX_ITEM_ROWS:
            continue
        rows[item_id] = {
            "ID": item_id,
            "ClassID": int(values[1]),
            "SubclassID": int(values[2]),
            "Display": values[4],
            "InventoryType": int(values[14]),
            "AllowableClass": int(values[15]),
            "ItemLevel": int(values[17]),
            "RequiredLevel": int(values[18]),
        }
    if rows != HOTFIX_ITEM_ROWS:
        raise ValueError("checked_in_hotfix_item_catalog_identity_mismatch")
    return {item_id: dict(row) for item_id, row in rows.items()}


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_wowsims_manifest(
    profile: Mapping[str, Any], slot_map: list[int]
) -> list[dict[str, Any]]:
    """Transform a WoWSims item array into the runtime admission identity."""
    items = profile.get("items")
    if not isinstance(items, list) or len(items) > len(slot_map):
        raise ValueError("invalid_wowsims_items")
    manifest: list[dict[str, Any]] = []
    occupied_slots: set[int] = set()
    for index, raw in enumerate(items):
        if not raw:
            continue
        if not isinstance(raw, Mapping):
            raise ValueError("invalid_wowsims_item")
        unsupported_fields = set(raw) - {"id", "enchant", "gems", "reforging"}
        if unsupported_fields:
            raise ValueError(
                f"unbound_wowsims_item_fields:{','.join(sorted(unsupported_fields))}"
            )
        item_id = int(raw.get("id") or 0)
        slot = int(slot_map[index])
        if item_id <= 0 or slot in occupied_slots:
            raise ValueError("invalid_wowsims_item_identity")
        occupied_slots.add(slot)
        gem_item_ids = [int(value or 0) for value in raw.get("gems") or []]
        while gem_item_ids and gem_item_ids[-1] == 0:
            gem_item_ids.pop()
        manifest.append(
            {
                "slot": slot,
                "item_id": item_id,
                "enchant_id": int(raw.get("enchant") or 0),
                "reforge_id": int(raw.get("reforging") or 0),
                "gem_item_ids": gem_item_ids,
            }
        )
    return sorted(manifest, key=lambda row: row["slot"])


def preset_source_asset(
    reference: Mapping[str, Any], source_url: str
) -> Mapping[str, Any]:
    matches = [
        row
        for row in reference.get("source_assets") or []
        if isinstance(row, Mapping) and str(row.get("url") or "") == source_url
    ]
    if len(matches) != 1:
        raise ValueError("pinned_gear_source_asset_not_unique")
    return matches[0]


def selected_numeric_fixture_gear_label(
    reference: Mapping[str, Any], test_source: str
) -> str:
    """Resolve the gear variant that produced the pinned numeric result."""
    result_key = str(
        ((reference.get("expected_output") or {}).get("result_key") or "")
    )
    preset_path = str(
        (((reference.get("gear") or {}).get("simulator_preset") or {}).get("path") or "")
    )
    preset_name = Path(preset_path).name
    preset_label = (
        preset_name[: -len(".gear.json")]
        if preset_name.endswith(".gear.json")
        else ""
    )
    if "-Settings-" in result_key:
        return preset_label if preset_label and f"-{preset_label}-" in result_key else ""
    if result_key.endswith("-Average-Default"):
        match = PRIMARY_GEAR_SET_PATTERN.search(test_source)
        return match.group(1) if match else ""
    return ""


def validate_numeric_fixture_gear_binding(
    reference: Mapping[str, Any], preset_label: str
) -> dict[str, bool]:
    """Return legacy upstream-row provenance checks.

    These fields explain which checked-in upstream test row was originally
    inspected. They do not qualify a generated live-compatible denominator;
    generated requests are bound separately below.
    """
    gear = reference.get("gear") or {}
    revision = str(reference.get("provider_revision") or "")
    test_path = str(reference.get("test") or "")
    test_url = (
        f"https://raw.githubusercontent.com/wowsims/cata/{revision}/{test_path}"
    )
    asset = preset_source_asset(reference, test_url)
    snapshot_value = str(gear.get("numeric_fixture_test_snapshot") or "")
    snapshot_path = REPO_ROOT / snapshot_value
    snapshot_bytes = snapshot_path.read_bytes() if snapshot_path.is_file() else b""
    snapshot_sha256 = (
        hashlib.sha256(snapshot_bytes).hexdigest() if snapshot_bytes else ""
    )
    try:
        test_source = snapshot_bytes.decode("utf-8")
    except UnicodeDecodeError:
        test_source = ""
    selected_label = selected_numeric_fixture_gear_label(reference, test_source)
    return {
        "numeric_fixture_test_snapshot": bool(snapshot_value)
        and snapshot_path.is_file(),
        "numeric_fixture_test_source_sha256": (
            len(str(asset.get("sha256") or "")) == 64
            and snapshot_sha256 == asset.get("sha256")
            and gear.get("numeric_fixture_test_source_sha256")
            == asset.get("sha256")
        ),
        "numeric_fixture_result_selects_preset": bool(selected_label)
        and selected_label == preset_label
        and gear.get("numeric_fixture_gear_label") == selected_label,
    }


def validate_generated_request_gear_binding(
    reference: Mapping[str, Any],
    *,
    gear_profile_id: str,
    source_sha256: str,
    transformed_manifest_sha256: str,
) -> dict[str, Any]:
    """Bind a generated numeric request to the canonical gear transform.

    Upstream aggregate/settings rows remain useful provenance, but the
    qualifying denominator is generated from the exact live-compatible
    request. When a row declares ``generated_verified``, require both its
    semantic gear requirement and its source setup to name the immutable
    checked-in source/transform identity.
    """
    conditions = reference.get("reference_conditions") or {}
    manifest = (
        conditions.get("comparison_manifest")
        if isinstance(conditions, Mapping)
        else None
    )
    manifest = manifest if isinstance(manifest, Mapping) else {}
    if manifest.get("result_status") != "generated_verified":
        return {"required": False, "passed": True, "checks": {}}

    requirements = manifest.get("requirements")
    requirements = requirements if isinstance(requirements, list) else []
    gear_requirements = [
        row
        for row in requirements
        if isinstance(row, Mapping) and row.get("id") == "gear_manifest"
    ]
    source_setup = manifest.get("source_setup")
    source_setup = source_setup if isinstance(source_setup, Mapping) else {}
    request_gear = source_setup.get("gear")
    request_gear = request_gear if isinstance(request_gear, Mapping) else {}
    checks = {
        "generated_request_gear_requirement_unique": len(gear_requirements) == 1,
        "generated_request_gear_requirement_matches_transform": (
            len(gear_requirements) == 1
            and gear_requirements[0].get("equals")
            == transformed_manifest_sha256
        ),
        "generated_request_gear_planned_requirement_matches_transform": (
            len(gear_requirements) == 1
            and gear_requirements[0].get("planned_equals")
            == transformed_manifest_sha256
        ),
        "generated_request_gear_profile_id": (
            request_gear.get("gear_profile_id") == gear_profile_id
        ),
        "generated_request_gear_source_sha256": (
            request_gear.get("source_sha256") == source_sha256
        ),
        "generated_request_gear_transform_schema": (
            request_gear.get("transform_schema") == TRANSFORM_SCHEMA
        ),
        "generated_request_gear_transformed_manifest_sha256": (
            request_gear.get("transformed_manifest_sha256")
            == transformed_manifest_sha256
        ),
        "generated_request_gear_transform_authority": (
            request_gear.get("applicability_authority")
            == ENCHANT_APPLICABILITY_AUTHORITY
        ),
    }
    return {"required": True, "passed": all(checks.values()), "checks": checks}


def validate_profile_source_binding(
    *,
    profile: Mapping[str, Any],
    reference: Mapping[str, Any],
    slot_map: list[int],
) -> dict[str, Any]:
    """Bind one overlay transform to its content-addressed reference preset."""
    gear = reference.get("gear") or {}
    preset = gear.get("simulator_preset") or {}
    source = profile.get("source") or {}
    repository = str(reference.get("repository") or "")
    revision = str(reference.get("provider_revision") or "")
    path = str(preset.get("path") or "")
    preset_name = Path(path).name
    preset_label = (
        preset_name[: -len(".gear.json")]
        if preset_name.endswith(".gear.json")
        else ""
    )
    source_url = (
        f"https://raw.githubusercontent.com/wowsims/cata/{revision}/{path}"
    )
    asset = preset_source_asset(reference, source_url)
    snapshot_value = str(source.get("snapshot") or "")
    snapshot_path = REPO_ROOT / snapshot_value
    snapshot_bytes = snapshot_path.read_bytes() if snapshot_path.is_file() else b""
    snapshot_sha256 = (
        hashlib.sha256(snapshot_bytes).hexdigest() if snapshot_bytes else ""
    )
    try:
        snapshot_document = json.loads(snapshot_bytes) if snapshot_bytes else {}
    except json.JSONDecodeError:
        snapshot_document = {}
    snapshot_profile = {
        "items": snapshot_document.get("items")
        if isinstance(snapshot_document, Mapping)
        else None
    }
    try:
        source_manifest = canonical_wowsims_manifest(snapshot_profile, slot_map)
    except ValueError:
        source_manifest = []
    manifest = canonical_wowsims_manifest(profile, slot_map)
    transformed_sha256 = canonical_sha256(source_manifest) if source_manifest else ""
    generated_request = validate_generated_request_gear_binding(
        reference,
        gear_profile_id=str(gear.get("gear_profile_id") or ""),
        source_sha256=str(asset.get("sha256") or ""),
        transformed_manifest_sha256=transformed_sha256,
    )
    checks = {
        "source_repository": repository == WOWSIMS_REPOSITORY
        and source.get("repository") == repository,
        "source_commit": bool(revision) and source.get("commit") == revision,
        "source_path": bool(path) and source.get("path") == path,
        "source_sha256": len(str(asset.get("sha256") or "")) == 64
        and source.get("sha256") == asset.get("sha256")
        and gear.get("source_sha256") == asset.get("sha256")
        and snapshot_sha256 == asset.get("sha256"),
        "source_snapshot": bool(snapshot_value)
        and gear.get("source_snapshot") == snapshot_value
        and snapshot_path.is_file(),
        "source_payload_transform": bool(source_manifest)
        and manifest == source_manifest,
        "transform_schema": gear.get("transform_schema") == TRANSFORM_SCHEMA,
        "transformed_manifest_sha256": (
            profile.get("transformed_manifest_sha256") == transformed_sha256
            and gear.get("transformed_manifest_sha256") == transformed_sha256
        ),
        "permanent_enchant_applicability_authority": (
            profile.get("permanent_enchant_applicability_authority")
            == ENCHANT_APPLICABILITY_AUTHORITY
            and gear.get("permanent_enchant_applicability_authority")
            == ENCHANT_APPLICABILITY_AUTHORITY
        ),
        "complete_source_equipment": len(source_manifest) >= 16,
        **generated_request["checks"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "informational_checks": validate_numeric_fixture_gear_binding(
            reference, preset_label
        ),
        "generated_request_gear_binding_required": generated_request["required"],
        "source_url": source_url,
        "source_sha256": str(asset.get("sha256") or ""),
        "transformed_manifest_sha256": transformed_sha256,
        "manifest": manifest,
    }


def validate_profile_local_legality(
    *,
    profile: Mapping[str, Any],
    target: Mapping[str, Any],
    slot_map: list[int],
    dbc_dir: Path,
) -> dict[str, Any]:
    """Apply every deterministic player-legality oracle available locally.

    SpellItemEnchantment.dbc does not encode inventory-slot applicability.
    That claim therefore remains explicitly attributed to the exact pinned
    WoWSims preset instead of being mislabeled as a DBC validation.
    """
    required_files = [
        dbc_dir / "Item.db2",
        dbc_dir / "Item-sparse.db2",
        dbc_dir / "SpellItemEnchantment.dbc",
        dbc_dir / "GemProperties.dbc",
        dbc_dir / "ItemReforge.dbc",
    ]
    if not all(path.is_file() for path in required_files):
        return {
            "passed": False,
            "failure_reasons": ["local_gear_legality_oracle_missing"],
            "checks": {},
        }
    items_by_id, enchant_ids, reforge_ids, gem_enchants = _local_oracles(
        dbc_dir.resolve()
    )
    inventory_types = {
        int(slot): int(value)
        for slot, value in (profile.get("inventory_types") or {}).items()
    }
    provisioning = target.get("provisioning_bot") or {}
    bot = {
        "class": int(target.get("class_id") or provisioning.get("class") or 0),
        "class_spec": str(target.get("spec_target_id") or ""),
    }
    reasons: list[str] = []
    for row in canonical_wowsims_manifest(profile, slot_map):
        slot = int(row["slot"])
        item_id = int(row["item_id"])
        item = items_by_id.get(item_id)
        if item is None:
            reasons.append(f"item_missing_from_local_catalog:{slot}:{item_id}")
            continue
        inventory_type = int(item.get("InventoryType") or 0)
        if inventory_types.get(slot) != inventory_type:
            reasons.append(f"inventory_type_mismatch:{slot}:{item_id}")
        if not item_player_accessible(item):
            reasons.append(f"item_not_player_accessible:{slot}:{item_id}")
        if not class_allowed(item, bot["class"]):
            reasons.append(f"item_class_restricted:{slot}:{item_id}")
        if not armor_allowed(item, bot["class"]):
            reasons.append(f"item_armor_or_weapon_restricted:{slot}:{item_id}")
        if slot not in INVENTORY_TO_EQUIPMENT_SLOTS.get(inventory_type, []):
            reasons.append(f"item_slot_incompatible:{slot}:{item_id}")
        if not weapon_slot_allowed(bot, item, slot):
            reasons.append(f"weapon_slot_incompatible:{slot}:{item_id}")
        enchant_id = int(row["enchant_id"])
        if enchant_id and enchant_id not in enchant_ids:
            reasons.append(f"permanent_enchant_missing_from_dbc:{slot}:{enchant_id}")
        reforge_id = int(row["reforge_id"])
        if reforge_id and reforge_id not in reforge_ids:
            reasons.append(f"reforge_missing_from_dbc:{slot}:{reforge_id}")
        for gem_item_id in row["gem_item_ids"]:
            if gem_item_id and gem_item_id not in gem_enchants:
                reasons.append(f"gem_missing_from_dbc:{slot}:{gem_item_id}")
    checks = {
        "item_catalog_identity_and_accessibility": not any(
            reason.startswith(("item_", "inventory_type_", "weapon_"))
            for reason in reasons
        ),
        "permanent_enchant_ids_exist": not any(
            reason.startswith("permanent_enchant_") for reason in reasons
        ),
        "reforge_ids_exist": not any(
            reason.startswith("reforge_") for reason in reasons
        ),
        "gem_items_have_dbc_enchantments": not any(
            reason.startswith("gem_") for reason in reasons
        ),
        "permanent_enchant_applicability_is_explicitly_upstream": (
            profile.get("permanent_enchant_applicability_authority")
            == ENCHANT_APPLICABILITY_AUTHORITY
        ),
    }
    return {
        "passed": not reasons and all(checks.values()),
        "failure_reasons": reasons,
        "checks": checks,
    }


@functools.lru_cache(maxsize=4)
def _local_oracles(
    dbc_dir: Path,
) -> tuple[dict[int, dict[str, Any]], set[int], set[int], dict[int, int]]:
    items_by_id = {int(row["ID"]): row for row in load_db2_item_rows(dbc_dir)}
    items_by_id.update(validated_hotfix_item_rows())
    enchant_ids = {
        int(row["values"][0])
        for row in load_wdbc(
            dbc_dir / "SpellItemEnchantment.dbc", SPELL_ITEM_ENCHANTMENT_FMT
        )
    }
    reforge_ids = {
        int(row[0])
        for row in load_wdbc_values(dbc_dir / "ItemReforge.dbc", "nifif")
    }
    return items_by_id, enchant_ids, reforge_ids, gem_item_enchant_map(dbc_dir)
