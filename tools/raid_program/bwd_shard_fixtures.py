"""Accepted legacy BWD 10N diagnostic-shard layout (thin wrapper).

This module only keeps the frozen legacy layout that the accepted Magmaw 10N
roster (GUIDs 30001-30010) and the other five 301xx-305xx pools depend on:
their shard definitions, overrides, names and GUID formula. Every generic
check lives in `raid_shard_contract`; new raid x boss x copies shards come
from `raid_shard_plan`. The tracked output
`experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json` must stay
byte-identical. Its `precompleted_boss_entries` are legacy metadata that no
consumer reads; seeded lockouts use the package-A prerequisite graph.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from tools.raid_program.raid_shard_contract import (
    LIVE_IDENTITY_FIELDS,
    NATIVE_BACKPACK_SLOT_END,
    NATIVE_BACKPACK_SLOT_START,
    VALIDATION_CONSUMABLE_SLOTS,
    catalog_source,
    consumable_slot_failures as _consumable_slot_failures,
    duplicates as _duplicates,
    live_requirements as _live_requirements,
    read_json as _read,
    valid_native_name,
    validate_native_consumable_slots,
    validate_shard_readback,
)

__all__ = [
    "CANONICAL_ROSTER_SLOT_IDS", "CANONICAL_SCENARIO_ID", "LIVE_IDENTITY_FIELDS",
    "NATIVE_BACKPACK_SLOT_END", "NATIVE_BACKPACK_SLOT_START", "SHARD_DEFINITIONS",
    "SHARD_ROSTER_SOURCE_OVERRIDES", "VALIDATION_CONSUMABLE_SLOTS",
    "build_diagnostic_provisioning_config", "build_shard_fixture", "validate_native_consumable_slots",
    "validate_readback", "validate_shard_fixture",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SCENARIO_ID = "blackwing_descent_10n"
SCENARIO_CONFIG_PATH = REPO_ROOT / "experiments/configs/validation_scenarios_cata_001.json"
RUNTIME_PROFILE_PATH = REPO_ROOT / "dataset/bot_runtime_profiles/profiles.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"
FIXTURE_SCHEMA = "cata_raid_bwd_diagnostic_shard_fixture_v1"
LEGACY_MAP_ID = 669
LEGACY_DIFFICULTY = "normal_10man"

CANONICAL_ROSTER_SLOT_IDS = (
    "raid_tank_1", "raid_tank_2", "raid_healer_1", "raid_healer_2", "raid_healer_3",
    "raid_dps_1", "raid_dps_2", "raid_dps_3", "raid_dps_4", "raid_dps_5",
)
LEGACY_BOTS_PER_SHARD = len(CANONICAL_ROSTER_SLOT_IDS)

SHARD_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {"boss_key": "magmaw", "profile_id": "blackwing_descent_10n_magmaw_diagnostic", "name_code": "Mgw", "precompleted_boss_entries": [], "upper_ledge_start": False, "requires_native_descent_before_engagement": False},
    {"boss_key": "omnotron", "profile_id": "blackwing_descent_10n_omnotron_diagnostic", "name_code": "Omn", "precompleted_boss_entries": [41570], "upper_ledge_start": False, "requires_native_descent_before_engagement": False},
    {"boss_key": "maloriak", "profile_id": "blackwing_descent_10n_maloriak_diagnostic", "name_code": "Mal", "precompleted_boss_entries": [41570, 42166], "upper_ledge_start": False, "requires_native_descent_before_engagement": False},
    {"boss_key": "atramedes", "profile_id": "blackwing_descent_10n_atramedes_diagnostic", "name_code": "Atr", "precompleted_boss_entries": [41570, 42166, 41378], "upper_ledge_start": False, "requires_native_descent_before_engagement": False},
    {"boss_key": "chimaeron", "profile_id": "blackwing_descent_10n_chimaeron_diagnostic", "name_code": "Chi", "precompleted_boss_entries": [41570, 42166, 41378, 41442], "upper_ledge_start": False, "requires_native_descent_before_engagement": False},
    {"boss_key": "nefarian", "profile_id": "blackwing_descent_10n_nefarian_diagnostic", "name_code": "Nef", "precompleted_boss_entries": [41570, 42166, 41378, 41442, 43296], "upper_ledge_start": True, "requires_native_descent_before_engagement": True},
)
# Magmaw uses a diagnostic one-tank roster with the exact catalog Balance Druid
# setup replacing the former Protection Paladin. The original Rogue slot also
# uses Fire Mage for ranged execution; GUID30009 uses exact catalog Survival. Canonical and other shard rosters stay
# unchanged; canonical_roster_slot_id preserves stable slot/GUID ownership.
SHARD_ROSTER_SOURCE_OVERRIDES: dict[str, dict[str, str]] = {
    "magmaw": {"raid_tank_1": "catalog:balance_druid", "raid_dps_2": "raid_dps_1", "raid_dps_4": "catalog:survival_hunter"},
}


def _canonical(config: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in config.get("scenarios", []) if str(row.get("id")) == CANONICAL_SCENARIO_ID]
    if len(rows) != 1 or not isinstance(rows[0].get("bots"), list) or len(rows[0]["bots"]) != LEGACY_BOTS_PER_SHARD:
        raise ValueError("canonical_bwd_roster_must_have_exactly_10_bots")
    return rows[0]


def _slots(scenario: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {slot: dict(copy.deepcopy(bot), roster_slot_id=slot) for slot, bot in zip(CANONICAL_ROSTER_SLOT_IDS, scenario["bots"], strict=True)}


def _roster_source(config: dict[str, Any], slots: dict[str, dict[str, Any]], source_id: str) -> dict[str, Any]:
    if not source_id.startswith("catalog:"):
        return slots[source_id]
    return catalog_source(config, source_id.removeprefix("catalog:"))


def _starts() -> dict[str, dict[str, Any]]:
    payload = _read(SCENARIO_CONFIG_PATH)
    return {str(row["id"]): copy.deepcopy(row.get("start_position", {})) for row in payload.get("diagnostic_scenarios", [])}


def _profiles() -> dict[str, dict[str, Any]]:
    return {str(row.get("name")): row for row in _read(RUNTIME_PROFILE_PATH).get("profiles", [])}


def _name(code: str, slot: str) -> str:
    role, number = slot.rsplit("_", 1)
    kind = {"raid_tank": "tank", "raid_healer": "heal", "raid_dps": "dps"}[role]
    # TrinityCore normalizes player names as first-letter uppercase and the
    # remaining ASCII letters lowercase. Digits cause CheckPlayerName to set
    # AT_LOGIN_RENAME and make Player::LoadFromDB fail.
    suffix = chr(ord("a") + int(number) - 1)
    return f"{code[0].upper()}{code[1:].lower()}{kind}{suffix}"


def _legacy_digit_name(code: str, slot: str) -> str:
    """Return the pre-native-validation shard name for cleanup only."""
    role, number = slot.rsplit("_", 1)
    kind = {"raid_tank": "tank", "raid_healer": "heal", "raid_dps": "dps"}[role]
    return f"{code[0].upper()}{code[1:].lower()}{kind}{number}"


def _account(code: str, index: int) -> str:
    return f"BWD{code.upper()}A{index:02d}"


def _namespace(boss: str) -> str:
    return f"cata_raid/bwd/diagnostic/{boss}"


def build_shard_fixture(config: dict[str, Any]) -> dict[str, Any]:
    """Clone the canonical roster into the legacy disjoint pools with explicit spec overrides."""
    validate_native_consumable_slots(config)
    scenario = _canonical(config)
    slots = _slots(scenario)
    starts = _starts()
    profiles = _profiles()
    shards: list[dict[str, Any]] = []
    for shard_index, definition in enumerate(SHARD_DEFINITIONS):
        profile_id = str(definition["profile_id"])
        if profile_id not in profiles:
            raise ValueError(f"runtime_profile_missing:{profile_id}")
        namespace = _namespace(str(definition["boss_key"]))
        bots: list[dict[str, Any]] = []
        source_overrides = SHARD_ROSTER_SOURCE_OVERRIDES.get(
            str(definition["boss_key"]), {}
        )
        for slot_index, slot_id in enumerate(slots, 1):
            source_slot_id = source_overrides.get(slot_id, slot_id)
            source = _roster_source(config, slots, source_slot_id)
            account_id = 20000 + shard_index * 100 + slot_index
            guid = 30000 + shard_index * 100 + slot_index
            bot = copy.deepcopy(source)
            bot.update({
                "canonical_roster_slot_id": slot_id,
                "roster_source_slot_id": source_slot_id,
                "roster_slot_id": f"{profile_id}:{slot_id}",
                "account_id": account_id,
                "expected_account_id": account_id,
                "account": _account(str(definition["name_code"]), slot_index),
                "character_guid": guid,
                "expected_character_guid": guid,
                "name": _name(str(definition["name_code"]), slot_id),
                # The first diagnostic provisioning draft used a numeric
                # suffix. TrinityCore marks those rows AT_LOGIN_RENAME and
                # refuses to load them. Keep the old selector strictly as a
                # cleanup alias so fixed-GUID reprovisioning is idempotent.
                "legacy_names": [_legacy_digit_name(str(definition["name_code"]), slot_id)],
                "pool_tag": profile_id,
                "runtime_profile_id": profile_id,
                "action_profile_id": str(source.get("class_spec") or ""),
                "canonical_setup": {
                    "class_spec": str(source.get("class_spec") or ""),
                    "talent_build_id": str(source.get("class_spec") or ""),
                    "gear_profile_id": str(source.get("gear_profile") or source.get("class_spec") or ""),
                    "glyph_ids": list(source.get("glyphs") or []),
                    "action_profile_id": str(source.get("class_spec") or ""),
                    "source_config": (str(config["canonical_target_catalog"]) if source_slot_id.startswith("catalog:")
                                      else "experiments/configs/validation_provisioning_cata_001.json"),
                    "action_profile_manifest": "experiments/configs/cata_434_action_profiles.json",
                },
                "evidence_namespace": f"{namespace}/roster/{slot_id}",
            })
            if bot.get("pet"):
                pet = copy.deepcopy(bot["pet"])
                pet["id_offset"] = shard_index * 100 + slot_index
                suffix = chr(ord("a") + slot_index - 1)
                pet["name"] = f"{str(definition['name_code']).lower()}wolf{suffix}"
                bot["pet"] = pet
                bot["expected_pet_id"] = 8700000 + int(pet["id_offset"])
            bots.append(bot)
        predecessor = {
            "state_source": "instance_blackwing_descent_native_boss_state_fixture",
            "precompleted_boss_entries": list(definition["precompleted_boss_entries"]),
            "certifies_predecessors": False,
            "upper_ledge_start": bool(definition["upper_ledge_start"]),
            "requires_native_descent_before_engagement": bool(definition["requires_native_descent_before_engagement"]),
        }
        shards.append({
            "shard_id": f"bwd_{definition['boss_key']}_diagnostic_10n",
            "boss_key": definition["boss_key"],
            "scenario_id": profile_id,
            "pool_tag": profile_id,
            "runtime_profile_id": profile_id,
            "evidence_namespace": namespace,
            "required_bot_count": LEGACY_BOTS_PER_SHARD,
            "role_counts": {role: sum(bot["role"] == role for bot in bots)
                            for role in ("tank", "healer", "dps")},
            "start_position": starts.get(profile_id, {}),
            "diagnostic_only": True,
            "diagnostic_parent_scenario_id": CANONICAL_SCENARIO_ID,
            "predecessor_state": predecessor,
            "live_identity_requirements": _live_requirements(),
            "bots": bots,
        })
    fixture = {
        "schema": FIXTURE_SCHEMA,
        "source": {"provisioning_config": "experiments/configs/validation_provisioning_cata_001.json", "canonical_scenario_id": CANONICAL_SCENARIO_ID, "runtime_profile_manifest": "dataset/bot_runtime_profiles/profiles.json", "scenario_manifest": "experiments/configs/validation_scenarios_cata_001.json"},
        "canonical_roster": [{"roster_slot_id": slot, "name": bot["name"], "account": bot["account"], "role": bot["role"], "class": bot["class"], "class_spec": bot["class_spec"]} for slot, bot in slots.items()],
        "diagnostic_bot_count": len(SHARD_DEFINITIONS) * LEGACY_BOTS_PER_SHARD,
        "shard_count": len(SHARD_DEFINITIONS),
        "instance_identity_policy": {"map_id": LEGACY_MAP_ID, "difficulty": LEGACY_DIFFICULTY, "no_instance_or_save_ids_in_provisioning": True, "live_identity_fields": list(LIVE_IDENTITY_FIELDS)},
        "shards": shards,
    }
    validate_shard_fixture(fixture, config)
    return fixture


def build_diagnostic_provisioning_config(config: dict[str, Any], fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    """Append diagnostic scenarios to a copy; never mutate canonical input."""
    validate_native_consumable_slots(config)
    fixture = fixture or build_shard_fixture(config)
    validate_shard_fixture(fixture, config)
    merged = copy.deepcopy(config)
    if not any(str(row.get("id")) == CANONICAL_SCENARIO_ID for row in merged.get("scenarios", [])):
        raise ValueError("canonical_bwd_scenario_missing_from_provisioning_config")
    canonical_slots = _slots(_canonical(config))
    talent_builds = merged.get("talent_builds_by_spec", {})
    for shard in fixture["shards"]:
        bots = copy.deepcopy(shard["bots"])
        for bot in bots:
            class_spec = str(bot.get("class_spec") or "")
            source_slot = str(bot.get("roster_source_slot_id") or "")
            source = _roster_source(config, canonical_slots, source_slot)
            if not source or not source.get("consumables"):
                raise ValueError(
                    f"diagnostic_consumables_missing:{shard['boss_key']}:{source_slot}"
                )
            bot["consumables"] = copy.deepcopy(source["consumables"])
            build = talent_builds.get(class_spec, {})
            for key in ("primary_talent_tree_id", "talents", "primary_tree_spells"):
                if key not in bot and key in build:
                    bot[key] = copy.deepcopy(build[key])
        merged["scenarios"].append({
            "id": shard["scenario_id"], "instance": "Blackwing Descent", "map_id": LEGACY_MAP_ID, "difficulty": LEGACY_DIFFICULTY,
            "provisioning_scenario_id": CANONICAL_SCENARIO_ID, "start_position": copy.deepcopy(shard["start_position"]),
            "required_roles": copy.deepcopy(shard["role_counts"]), "bots": bots,
            "diagnostic_only": True, "diagnostic_parent_scenario_id": CANONICAL_SCENARIO_ID,
            "runtime_profile_id": shard["runtime_profile_id"], "pool_tag": shard["pool_tag"],
            "predecessor_state": copy.deepcopy(shard["predecessor_state"]),
            "live_identity_requirements": copy.deepcopy(shard["live_identity_requirements"]),
        })
    return merged


def validate_shard_fixture(fixture: dict[str, Any], canonical_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate all immutable identities and the non-certifying prerequisite contract."""
    if canonical_config is not None:
        validate_native_consumable_slots(canonical_config)
    failures: list[dict[str, Any]] = []
    if fixture.get("schema") != FIXTURE_SCHEMA:
        failures.append({"check": "schema"})
    shards = fixture.get("shards") if isinstance(fixture.get("shards"), list) else []
    expected_shards = len(SHARD_DEFINITIONS)
    expected_bots = expected_shards * LEGACY_BOTS_PER_SHARD
    if len(shards) != expected_shards:
        failures.append({"check": "shard_count", "expected": expected_shards, "actual": len(shards)})
    definitions = {str(row["boss_key"]): row for row in SHARD_DEFINITIONS}
    all_bots = [bot for shard in shards for bot in shard.get("bots", []) if isinstance(bot, dict)]
    for field in ("account_id", "account", "character_guid", "name", "roster_slot_id", "evidence_namespace"):
        if _duplicates(bot.get(field) for bot in all_bots):
            failures.append({"check": f"duplicate_{field}"})
    if _duplicates(shard.get("pool_tag") for shard in shards):
        failures.append({"check": "duplicate_pool_tag"})
    profiles = _profiles()
    for shard in shards:
        boss = str(shard.get("boss_key") or "")
        definition = definitions.get(boss)
        if definition is None:
            failures.append({"check": "unknown_boss", "boss_key": boss})
            continue
        profile_id = str(definition["profile_id"])
        if any(shard.get(field) != value for field, value in (("scenario_id", profile_id), ("pool_tag", profile_id), ("runtime_profile_id", profile_id), ("diagnostic_parent_scenario_id", CANONICAL_SCENARIO_ID))):
            failures.append({"check": "shard_profile_binding", "boss_key": boss})
        if shard.get("diagnostic_only") is not True:
            failures.append({"check": "diagnostic_only_required", "boss_key": boss})
        predecessor = shard.get("predecessor_state") or {}
        if predecessor.get("certifies_predecessors") is not False or list(predecessor.get("precompleted_boss_entries") or []) != list(definition["precompleted_boss_entries"]):
            failures.append({"check": "predecessor_contract", "boss_key": boss})
        if bool(predecessor.get("upper_ledge_start")) != bool(definition["upper_ledge_start"]) or bool(predecessor.get("requires_native_descent_before_engagement")) != bool(definition["requires_native_descent_before_engagement"]):
            failures.append({"check": "nefarian_ledge_contract", "boss_key": boss})
        requirements = shard.get("live_identity_requirements") or {}
        if requirements.get("fixture_values") is not None or set(requirements.get("fields") or []) != set(LIVE_IDENTITY_FIELDS):
            failures.append({"check": "live_identity_must_be_runtime_only", "boss_key": boss})
        profile = profiles.get(profile_id)
        if not profile or profile.get("pool_tag_filter") != profile_id or profile.get("validation_route", {}).get("scenario_id") != profile_id or profile.get("diagnostic_only") is not True:
            failures.append({"check": "runtime_profile_binding", "profile_id": profile_id})
        bots = shard.get("bots") if isinstance(shard.get("bots"), list) else []
        if len(bots) != LEGACY_BOTS_PER_SHARD:
            failures.append({"check": "shard_bot_count", "boss_key": boss, "actual": len(bots)})
        if {str(bot.get("canonical_roster_slot_id")) for bot in bots} != set(CANONICAL_ROSTER_SLOT_IDS):
            failures.append({"check": "roster_slot_coverage", "boss_key": boss})
        for bot in bots:
            consumables = bot.get("consumables")
            if consumables is not None:
                for failure in _consumable_slot_failures(
                    consumables,
                    f"shards[{boss}].bots[{bot.get('name', '')}].consumables",
                ):
                    failures.append({"check": "native_backpack_consumable_slots", **failure})
            for field in ("account_id", "character_guid"):
                value = bot.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    failures.append({"check": f"positive_{field}", "boss_key": boss})
            if bot.get("expected_account_id") != bot.get("account_id"):
                failures.append({"check": "account_id_expectation_drift", "boss_key": boss, "name": bot.get("name")})
            if bot.get("expected_character_guid") != bot.get("character_guid"):
                failures.append({"check": "character_guid_expectation_drift", "boss_key": boss, "name": bot.get("name")})
            name = str(bot.get("name") or "")
            if not valid_native_name(name):
                failures.append({"check": "character_name", "boss_key": boss, "name": name})
            if bot.get("pool_tag") != profile_id or bot.get("runtime_profile_id") != profile_id:
                failures.append({"check": "bot_profile_binding", "boss_key": boss, "name": name})
    if canonical_config is not None:
        slots = _slots(_canonical(canonical_config))
        actual = {str(row.get("roster_slot_id")): row for row in fixture.get("canonical_roster", [])}
        if set(actual) != set(CANONICAL_ROSTER_SLOT_IDS):
            failures.append({"check": "canonical_roster_contract"})
        for slot, source in slots.items():
            row = actual.get(slot, {})
            if any(row.get(field) != source.get(field) for field in ("name", "account", "role", "class", "class_spec")):
                failures.append({"check": "canonical_roster_drift", "roster_slot_id": slot})
    if int(fixture.get("diagnostic_bot_count") or 0) != expected_bots or len(all_bots) != expected_bots:
        failures.append({"check": "diagnostic_bot_count", "expected": expected_bots, "actual": len(all_bots)})
    if failures:
        raise ValueError(json.dumps({"schema": fixture.get("schema"), "failures": failures}, sort_keys=True))
    return {"all_passed": True, "diagnostic_bot_count": len(all_bots), "shard_count": len(shards)}


def validate_readback(fixture: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Check complete DB/console readback and require distinct live IDs."""
    validate_shard_fixture(fixture)
    return validate_shard_readback(fixture, rows)


build_bwd_shard_fixture = build_shard_fixture
validate_bwd_shard_fixture = validate_shard_fixture
validate_bwd_shard_readback = validate_readback


def main() -> int:
    parser = argparse.ArgumentParser(description="Build tracked BWD diagnostic shard fixture.")
    parser.add_argument("--canonical-config", type=Path, default=REPO_ROOT / "experiments/configs/validation_provisioning_cata_001.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    fixture = build_shard_fixture(_read(args.canonical_config))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "diagnostic_bot_count": fixture["diagnostic_bot_count"],
                      "shard_count": fixture["shard_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
