from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .common import stable_hash
except ImportError:
    from common import stable_hash


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ACTION_PROFILE_MANIFEST = REPO_ROOT / "experiments/configs/cata_434_action_profiles.json"
DEFAULT_COMBAT_LOOT_PROFILE_MANIFEST = REPO_ROOT / "experiments/configs/cata_434_combat_loot_profiles.json"


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def int_keyed_spell_map(payload: dict[str, Any], key: str) -> dict[int, list[int]]:
    return {
        int(class_id): sorted({int(spell_id) for spell_id in spells if int(spell_id) > 0})
        for class_id, spells in payload.get(key, {}).items()
    }


def load_action_profile_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or DEFAULT_ACTION_PROFILE_MANIFEST
    payload = load_manifest(manifest_path)
    return {
        "path": str(manifest_path),
        "schema": payload.get("schema", ""),
        "hash": stable_hash(payload),
        "action_profile_spells_by_class": int_keyed_spell_map(payload, "action_profile_spells_by_class"),
        "action_profile_spells_by_spec": {
            str(class_spec): sorted({int(spell_id) for spell_id in spells if int(spell_id) > 0})
            for class_spec, spells in payload.get("action_profile_spells_by_spec", {}).items()
        },
        "proficiency_spells_by_class": int_keyed_spell_map(payload, "proficiency_spells_by_class"),
        "raw": payload,
    }


def load_combat_loot_profile_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or DEFAULT_COMBAT_LOOT_PROFILE_MANIFEST
    payload = load_manifest(manifest_path)
    weights = {
        str(archetype): {str(stat): float(value) for stat, value in values.items()}
        for archetype, values in payload.get("stat_weights_by_archetype", {}).items()
    }
    return {
        "path": str(manifest_path),
        "schema": payload.get("schema", ""),
        "hash": stable_hash(payload),
        "stat_weights_by_archetype": weights,
        "class_spec_archetypes": {str(key): str(value) for key, value in payload.get("class_spec_archetypes", {}).items()},
        "loot_validation": payload.get("loot_validation", {}),
        "consumable_profiles": payload.get("consumable_profiles", {}),
        "glyph_source": payload.get("glyph_source", ""),
        "raw": payload,
    }
