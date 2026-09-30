"""Content-phase gear profiles for canonical raid compositions.

A composition may declare ``gear_phase`` (for example Blackwing Descent is
bound to ``cata_t11``). Its characters then wear the phase profile
``<phase_id>/<class_spec>`` built by ``build_phase_gear_profiles`` into
``dataset/raid_phase_gear_profiles/profiles.json`` instead of the catalog's
shared profile. The shared validation gear profiles (Stonecore, Phase-8 dummy
calibration, legacy Magmaw) are never rewritten: phase profiles live in their
own DVC output and in their own ``/``-namespaced profile IDs, which no catalog
profile ID can collide with.

Every loader that resolves a plan's ``gear_profile_id`` merges the phase
profiles through ``merge_phase_gear_profiles``. A missing phase output merges
nothing, so a plan that names a phase profile fails closed with
``gear_profile_missing`` instead of silently wearing another phase's gear.
"""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE_CONFIG_DIR = REPO_ROOT / "experiments/configs/raid_gear_phases"
DEFAULT_PHASE_GEAR_PROFILES = REPO_ROOT / "dataset/raid_phase_gear_profiles/profiles.json"
# Scratch/test override only: the plan records the sha256 of the file actually
# read (raid_loadout_sql.materialization_inputs), so a plan built against one
# file is refused against another.
PHASE_GEAR_PROFILES_ENV = "TRINITY_PHASE_GEAR_PROFILES"
PHASE_CONFIG_SCHEMA = "raid_gear_phase_v1"
PHASE_PROFILES_SCHEMA = "raid_phase_gear_profiles_v1"
PHASE_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
PROFILE_SEPARATOR = "/"


class PhaseGearError(ValueError):
    pass


def phase_gear_profiles_path() -> Path:
    override = os.environ.get(PHASE_GEAR_PROFILES_ENV, "").strip()
    return Path(override) if override else DEFAULT_PHASE_GEAR_PROFILES


def phase_profile_id(phase_id: str, class_spec: str) -> str:
    if not PHASE_ID_PATTERN.fullmatch(str(phase_id)) or not re.fullmatch(r"[a-z0-9_]+", str(class_spec)):
        raise PhaseGearError(f"phase_profile_id_invalid:{phase_id}:{class_spec}")
    return f"{phase_id}{PROFILE_SEPARATOR}{class_spec}"


def is_phase_profile_id(profile_id: str) -> bool:
    return PROFILE_SEPARATOR in str(profile_id)


def repo_path(reference: str) -> Path:
    path = Path(reference)
    return path if path.is_absolute() else REPO_ROOT / path


def load_phase_config(path: Path) -> dict[str, Any]:
    """One phase declaration; fails closed on a malformed or unbounded phase."""
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PhaseGearError(f"phase_config_unreadable:{path}:{error}") from error
    if config.get("schema") != PHASE_CONFIG_SCHEMA:
        raise PhaseGearError(f"phase_config_schema:{path}")
    phase_id = str(config.get("phase_id") or "")
    if not PHASE_ID_PATTERN.fullmatch(phase_id) or config.get("profile_namespace") != phase_id:
        raise PhaseGearError(f"phase_config_id:{path}")
    policy = config.get("item_policy") or {}
    cap = policy.get("max_item_level")
    if isinstance(cap, bool) or not isinstance(cap, int) or cap <= 0:
        raise PhaseGearError(f"phase_config_item_level_cap:{phase_id}")
    sources = config.get("sources") or {}
    if not sources.get("loot_maps") and not sources.get("vendor_currencies") and not sources.get("vendor_gold"):
        raise PhaseGearError(f"phase_config_sources_empty:{phase_id}")
    tiers = config.get("tier_sets_by_spec")
    if not isinstance(tiers, dict):
        raise PhaseGearError(f"phase_config_tier_sets:{phase_id}")
    return config


def composition_gear_phase(composition: Mapping[str, Any]) -> dict[str, Any] | None:
    """The composition's declared content phase, or None for a composition without one."""
    declared = composition.get("gear_phase")
    if declared is None:
        return None
    if not isinstance(declared, Mapping):
        raise PhaseGearError(f"composition_gear_phase_invalid:{composition.get('composition_id')}")
    phase_id = str(declared.get("phase_id") or "")
    config_path = repo_path(str(declared.get("config") or ""))
    if not PHASE_ID_PATTERN.fullmatch(phase_id) or not config_path.is_file():
        raise PhaseGearError(f"composition_gear_phase_invalid:{composition.get('composition_id')}")
    config = load_phase_config(config_path)
    if config["phase_id"] != phase_id:
        raise PhaseGearError(f"composition_gear_phase_mismatch:{composition.get('composition_id')}:{phase_id}")
    return {"phase_id": phase_id, "config": config_path, "phase_config": config}


def composition_gear_profile_id(composition: Mapping[str, Any], class_spec: str, catalog_profile_id: str) -> str:
    """The gear profile a composition character wears for one spec."""
    phase = composition_gear_phase(composition)
    return phase_profile_id(phase["phase_id"], class_spec) if phase else str(catalog_profile_id)


def load_phase_profiles(path: Path | None = None) -> dict[str, Any]:
    """Phase profiles by namespaced ID; {} when the DVC output is absent."""
    path = Path(path) if path is not None else phase_gear_profiles_path()
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != PHASE_PROFILES_SCHEMA:
        raise PhaseGearError(f"phase_profiles_schema:{path}")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or any(not is_phase_profile_id(key) for key in profiles):
        raise PhaseGearError(f"phase_profiles_ids:{path}")
    for key, profile in profiles.items():
        if not isinstance(profile, dict) or not profile.get("equipment") or not profile.get("complete_equipment_slots"):
            raise PhaseGearError(f"phase_profile_incomplete:{key}")
    return profiles


def merge_phase_gear_profiles(profiles: Mapping[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Add the phase profiles to a loaded profile map without touching any existing profile."""
    merged = dict(profiles)
    for key, profile in load_phase_profiles(path).items():
        if key in merged:
            raise PhaseGearError(f"phase_profile_id_collision:{key}")
        merged[key] = copy.deepcopy(profile)
    return merged
