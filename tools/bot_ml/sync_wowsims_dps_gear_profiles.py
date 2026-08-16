"""Refresh/check exact WoWSims equipment for the selected numeric DPS gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from .build_validation_gear_profiles import load_db2_item_rows
from .build_validation_provisioning import gem_item_enchant_map
from .wowsims_gear_binding import (
    ENCHANT_APPLICABILITY_AUTHORITY,
    TRANSFORM_SCHEMA,
    canonical_sha256,
    canonical_wowsims_manifest,
    selected_numeric_fixture_gear_label,
    validated_hotfix_item_rows,
    validate_profile_local_legality,
    validate_profile_source_binding,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE_PATH = REPO_ROOT / "experiments/configs/cata_raid_dps_acceptance_v1.json"
TARGETS_PATH = REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
REFERENCES_PATH = REPO_ROOT / "experiments/configs/all_spec_references_cata_p4_v1.json"
PROFILES_PATH = REPO_ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json"
SOURCES_DIR = REPO_ROOT / "experiments/configs/wowsims_cata_p4_gear_sources"
DBC_DIR = REPO_ROOT / "data/dbc/enUS"
SLOT_MAP = [0, 1, 2, 14, 4, 8, 9, 5, 6, 7, 10, 11, 12, 13, 15, 16, 17]


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _source_asset(reference: Mapping[str, Any], url: str) -> Mapping[str, Any]:
    matches = [
        row
        for row in reference.get("source_assets") or []
        if isinstance(row, Mapping) and str(row.get("url") or "") == url
    ]
    if len(matches) != 1:
        raise ValueError(
            f"{reference.get('spec_target_id')}: gear source asset is not unique"
        )
    return matches[0]


def refresh() -> None:
    acceptance = _load(ACCEPTANCE_PATH)
    targets_document = _load(TARGETS_PATH)
    references_document = _load(REFERENCES_PATH)
    old_document = _load(PROFILES_PATH)
    targets = {
        str(row["spec_target_id"]): row for row in targets_document["targets"]
    }
    references = {
        str(row["spec_target_id"]): row
        for row in references_document["references"]
    }
    profile_to_target = {
        str(row["gear_profile_id"]): str(row["spec_target_id"])
        for row in targets.values()
    }
    selected = [str(value) for value in acceptance.get("dps_targets") or []]
    # Preserve the existing exact Enhancement profile even though it is not in
    # the current 16-spec numeric gate.
    refresh_targets = list(selected)
    for profile_id in (old_document.get("profiles") or {}):
        target_id = profile_to_target.get(str(profile_id))
        if target_id and target_id not in refresh_targets:
            refresh_targets.append(target_id)

    item_rows = {int(row["ID"]): row for row in load_db2_item_rows(DBC_DIR)}
    item_rows.update(validated_hotfix_item_rows())
    gem_mapping = gem_item_enchant_map(DBC_DIR)
    new_profiles: dict[str, Any] = {}
    used_gems: set[int] = set()
    for target_id in refresh_targets:
        target = targets[target_id]
        reference = references[target_id]
        gear = reference.get("gear") or {}
        preset = gear.get("simulator_preset") or {}
        revision = str(reference.get("provider_revision") or "")
        path = str(preset.get("path") or "")
        url = f"https://raw.githubusercontent.com/wowsims/cata/{revision}/{path}"
        with urllib.request.urlopen(url, timeout=30) as response:
            source_bytes = response.read()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        asset = _source_asset(reference, url)
        if source_sha256 != asset.get("sha256"):
            raise ValueError(f"{target_id}: pinned gear source SHA mismatch")
        source_document = json.loads(source_bytes)
        source_items = source_document.get("items")
        if not isinstance(source_items, list):
            raise ValueError(f"{target_id}: pinned gear source has no items")
        profile_id = str(target["gear_profile_id"])
        test_path = str(reference.get("test") or "")
        test_url = (
            f"https://raw.githubusercontent.com/wowsims/cata/{revision}/{test_path}"
        )
        with urllib.request.urlopen(test_url, timeout=30) as response:
            test_source_bytes = response.read()
        test_source_sha256 = hashlib.sha256(test_source_bytes).hexdigest()
        test_asset = _source_asset(reference, test_url)
        if test_source_sha256 != test_asset.get("sha256"):
            raise ValueError(f"{target_id}: pinned numeric test source SHA mismatch")
        snapshot_path = SOURCES_DIR / f"{profile_id}.gear.json"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_bytes(source_bytes)
        snapshot_value = str(snapshot_path.relative_to(REPO_ROOT))
        test_snapshot_path = SOURCES_DIR / f"{profile_id}.test.go"
        test_snapshot_path.write_bytes(test_source_bytes)
        test_snapshot_value = str(test_snapshot_path.relative_to(REPO_ROOT))
        items: list[dict[str, Any]] = []
        inventory_types: dict[str, int] = {}
        for index, raw in enumerate(source_items):
            if not raw:
                items.append({})
                continue
            item = dict(raw)
            items.append(item)
            item_id = int(item.get("id") or 0)
            item_row = item_rows.get(item_id)
            if item_row is None:
                raise ValueError(
                    f"{target_id}: item {item_id} is absent from client and hotfix catalogs"
                )
            inventory_types[str(SLOT_MAP[index])] = int(
                item_row.get("InventoryType") or 0
            )
            used_gems.update(int(gem) for gem in item.get("gems") or [] if gem)
        profile: dict[str, Any] = {
            "source": {
                "repository": str(reference.get("repository") or ""),
                "commit": revision,
                "path": path,
                "sha256": source_sha256,
                "snapshot": snapshot_value,
            },
            "transformed_manifest_sha256": "",
            "permanent_enchant_applicability_authority": (
                ENCHANT_APPLICABILITY_AUTHORITY
            ),
            "inventory_types": inventory_types,
            "items": items,
        }
        profile["transformed_manifest_sha256"] = canonical_sha256(
            canonical_wowsims_manifest(profile, SLOT_MAP)
        )
        new_profiles[profile_id] = profile
        gear["runtime_manifest"] = str(PROFILES_PATH.relative_to(REPO_ROOT))
        gear["source_sha256"] = source_sha256
        gear["source_snapshot"] = snapshot_value
        gear["numeric_fixture_test_source_sha256"] = test_source_sha256
        gear["numeric_fixture_test_snapshot"] = test_snapshot_value
        gear["numeric_fixture_gear_label"] = selected_numeric_fixture_gear_label(
            reference, test_source_bytes.decode("utf-8")
        )
        gear["transform_schema"] = TRANSFORM_SCHEMA
        gear["transformed_manifest_sha256"] = profile[
            "transformed_manifest_sha256"
        ]
        gear["permanent_enchant_applicability_authority"] = (
            ENCHANT_APPLICABILITY_AUTHORITY
        )

    missing_gem_mappings = sorted(gem for gem in used_gems if gem not in gem_mapping)
    if missing_gem_mappings:
        raise ValueError(f"missing local gem mappings: {missing_gem_mappings}")
    new_document = {
        "schema": "bot_wowsims_cata_gear_profiles_v2",
        "transform_schema": TRANSFORM_SCHEMA,
        "slot_map": SLOT_MAP,
        "gem_enchantments": {
            str(gem): int(gem_mapping[gem]) for gem in sorted(used_gems)
        },
        "profiles": new_profiles,
    }
    _write(PROFILES_PATH, new_document)
    _write(REFERENCES_PATH, references_document)
    check()


def check() -> None:
    acceptance = _load(ACCEPTANCE_PATH)
    targets = {
        str(row["spec_target_id"]): row for row in _load(TARGETS_PATH)["targets"]
    }
    references = {
        str(row["spec_target_id"]): row
        for row in _load(REFERENCES_PATH)["references"]
    }
    document = _load(PROFILES_PATH)
    if document.get("schema") != "bot_wowsims_cata_gear_profiles_v2":
        raise ValueError("unexpected WoWSims gear profile schema")
    if document.get("transform_schema") != TRANSFORM_SCHEMA:
        raise ValueError("unexpected WoWSims gear transform schema")
    slot_map = [int(value) for value in document.get("slot_map") or []]
    if slot_map != SLOT_MAP:
        raise ValueError("unexpected WoWSims slot map")
    profiles = document.get("profiles") or {}
    for target_id in acceptance.get("dps_targets") or []:
        target = targets[str(target_id)]
        reference = references[str(target_id)]
        profile_id = str(target.get("gear_profile_id") or "")
        profile = profiles.get(profile_id)
        if not isinstance(profile, Mapping):
            raise ValueError(f"{target_id}: exact WoWSims gear profile missing")
        source = validate_profile_source_binding(
            profile=profile, reference=reference, slot_map=slot_map
        )
        if not source["passed"]:
            raise ValueError(
                f"{target_id}: source binding failed: "
                f"{[key for key, value in source['checks'].items() if not value]}"
            )
        legality = validate_profile_local_legality(
            profile=profile, target=target, slot_map=slot_map, dbc_dir=DBC_DIR
        )
        if not legality["passed"]:
            raise ValueError(
                f"{target_id}: local legality failed: {legality['failure_reasons']}"
            )
    print(
        json.dumps(
            {
                "passed": True,
                "selected_dps_profile_count": len(
                    acceptance.get("dps_targets") or []
                ),
                "profile_count": len(profiles),
            },
            sort_keys=True,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if args.refresh:
        refresh()
    else:
        check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
