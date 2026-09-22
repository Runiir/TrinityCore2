"""Apply hash-bound, slot-specific permanent-enchant overlays to gear."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OVERLAYS = REPO_ROOT / "experiments/configs/cata_blood_permanent_enchant_overlays_v1.json"
ENCHANTMENT_FIELD_COUNT = 45


class PermanentEnchantOverlayError(ValueError):
    """Raised when an overlay would not be a fail-closed enchant-only change."""


def load_overlay_document(path: Path = DEFAULT_OVERLAYS) -> dict[str, Any]:
    if not path.is_file():
        raise PermanentEnchantOverlayError(f"missing_overlay_document:{path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != "bot_permanent_enchant_overlays_v1":
        raise PermanentEnchantOverlayError("unexpected_overlay_schema")
    authority = document.get("authority")
    required_authority = {
        "provider": "WoWSims",
        "repository": "https://github.com/wowsims/cata",
        "applicability": "pinned_wowsims_preset_exact",
        "scope": "permanent_enchant_applicability_only",
    }
    if not isinstance(authority, Mapping) or any(
        authority.get(key) != value for key, value in required_authority.items()
    ):
        raise PermanentEnchantOverlayError("overlay_authority_is_not_pinned")
    if not str(authority.get("revision") or "") or not str(authority.get("path") or ""):
        raise PermanentEnchantOverlayError("overlay_authority_source_missing")
    if len(str(authority.get("source_sha256") or "")) != 64:
        raise PermanentEnchantOverlayError("overlay_authority_hash_missing")
    profiles = document.get("profiles")
    if not isinstance(profiles, Mapping) or not profiles:
        raise PermanentEnchantOverlayError("overlay_profiles_missing")
    return document


def _enchantment_fields(value: Any) -> list[int]:
    if value is None or value == "":
        return [0] * ENCHANTMENT_FIELD_COUNT
    if isinstance(value, str):
        raw = value.split()
    elif isinstance(value, list):
        raw = value
    else:
        raise PermanentEnchantOverlayError("invalid_enchantment_fields")
    if len(raw) != ENCHANTMENT_FIELD_COUNT:
        raise PermanentEnchantOverlayError("enchantment_field_count_changed")
    try:
        return [int(item) for item in raw]
    except (TypeError, ValueError) as exc:
        raise PermanentEnchantOverlayError("invalid_enchantment_field_value") from exc


def apply_permanent_enchant_overlays(
    profiles: Mapping[str, Any],
    path: Path = DEFAULT_OVERLAYS,
) -> dict[str, Any]:
    """Merge only declared permanent enchants into existing equipment rows.

    Item identity, gems, reforges, temporary enchants and every unrelated
    profile field are copied unchanged.  A missing base profile or slot is a
    hard error rather than an implicit fallback.
    """
    document = load_overlay_document(path)
    merged = copy.deepcopy(dict(profiles))
    authority = copy.deepcopy(document["authority"])
    for profile_id, definition in document["profiles"].items():
        if profile_id not in merged:
            continue
        if not isinstance(definition, Mapping):
            raise PermanentEnchantOverlayError(f"invalid_overlay_profile:{profile_id}")
        if definition.get("base_profile_id") != profile_id:
            raise PermanentEnchantOverlayError(f"overlay_base_profile_mismatch:{profile_id}")
        profile = merged[profile_id]
        equipment = profile.get("equipment") if isinstance(profile, Mapping) else None
        if not isinstance(equipment, list):
            raise PermanentEnchantOverlayError(f"missing_base_equipment:{profile_id}")
        rows_by_slot: dict[int, dict[str, Any]] = {}
        for row in equipment:
            if not isinstance(row, Mapping):
                raise PermanentEnchantOverlayError(f"invalid_base_equipment:{profile_id}")
            slot = int(row.get("slot", -1))
            if slot in rows_by_slot or slot < 0:
                raise PermanentEnchantOverlayError(f"duplicate_base_slot:{profile_id}:{slot}")
            rows_by_slot[slot] = row
        enchants = definition.get("permanent_enchants_by_slot")
        if not isinstance(enchants, Mapping) or not enchants:
            raise PermanentEnchantOverlayError(f"overlay_enchants_missing:{profile_id}")
        for raw_slot, raw_enchant in enchants.items():
            slot = int(raw_slot)
            enchant_id = int(raw_enchant)
            if enchant_id <= 0 or slot not in rows_by_slot:
                raise PermanentEnchantOverlayError(f"overlay_slot_unavailable:{profile_id}:{slot}")
            row = dict(rows_by_slot[slot])
            fields = _enchantment_fields(row.get("enchantments"))
            fields[0] = enchant_id
            row["enchant_id"] = enchant_id
            row["enchantments"] = " ".join(str(value) for value in fields)
            rows_by_slot[slot] = row
        merged_profile = dict(profile)
        merged_profile["equipment"] = [
            rows_by_slot[int(row["slot"])] for row in equipment
        ]
        merged_profile["permanent_enchant_overlay"] = {
            "profile_id": profile_id,
            "authority": authority,
            "excluded_source_enchants": copy.deepcopy(
                definition.get("excluded_source_enchants") or []
            ),
        }
        merged_profile["enchant_selection_mode"] = "pinned_wowsims_slot_overlay"
        merged_profile["enchanted"] = True
        merged[profile_id] = merged_profile
    return merged
