"""Deterministic BWD diagnostic-shard identities and live readback contract."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SCENARIO_ID = "blackwing_descent_10n"
SCENARIO_CONFIG_PATH = REPO_ROOT / "experiments/configs/validation_scenarios_cata_001.json"
RUNTIME_PROFILE_PATH = REPO_ROOT / "dataset/bot_runtime_profiles/profiles.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"

CANONICAL_ROSTER_SLOT_IDS = (
    "raid_tank_1", "raid_tank_2", "raid_healer_1", "raid_healer_2", "raid_healer_3",
    "raid_dps_1", "raid_dps_2", "raid_dps_3", "raid_dps_4", "raid_dps_5",
)

SHARD_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {"boss_key": "magmaw", "profile_id": "blackwing_descent_10n_magmaw_diagnostic", "name_code": "Mgw", "precompleted_boss_entries": [], "upper_ledge_start": False, "requires_native_descent_before_engagement": False},
    {"boss_key": "omnotron", "profile_id": "blackwing_descent_10n_omnotron_diagnostic", "name_code": "Omn", "precompleted_boss_entries": [41570], "upper_ledge_start": False, "requires_native_descent_before_engagement": False},
    {"boss_key": "maloriak", "profile_id": "blackwing_descent_10n_maloriak_diagnostic", "name_code": "Mal", "precompleted_boss_entries": [41570, 42166], "upper_ledge_start": False, "requires_native_descent_before_engagement": False},
    {"boss_key": "atramedes", "profile_id": "blackwing_descent_10n_atramedes_diagnostic", "name_code": "Atr", "precompleted_boss_entries": [41570, 42166, 41378], "upper_ledge_start": False, "requires_native_descent_before_engagement": False},
    {"boss_key": "chimaeron", "profile_id": "blackwing_descent_10n_chimaeron_diagnostic", "name_code": "Chi", "precompleted_boss_entries": [41570, 42166, 41378, 41442], "upper_ledge_start": False, "requires_native_descent_before_engagement": False},
    {"boss_key": "nefarian", "profile_id": "blackwing_descent_10n_nefarian_diagnostic", "name_code": "Nef", "precompleted_boss_entries": [41570, 42166, 41378, 41442, 43296], "upper_ledge_start": True, "requires_native_descent_before_engagement": True},
)
LIVE_IDENTITY_FIELDS = ("group_id", "map_instance_id", "save_id", "attempt_id", "strategy_id", "assignment_generation")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(config: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in config.get("scenarios", []) if str(row.get("id")) == CANONICAL_SCENARIO_ID]
    if len(rows) != 1 or not isinstance(rows[0].get("bots"), list) or len(rows[0]["bots"]) != 10:
        raise ValueError("canonical_bwd_roster_must_have_exactly_10_bots")
    return rows[0]


def _slots(scenario: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {slot: dict(copy.deepcopy(bot), roster_slot_id=slot) for slot, bot in zip(CANONICAL_ROSTER_SLOT_IDS, scenario["bots"], strict=True)}


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


def _live_requirements() -> dict[str, Any]:
    return {
        "fields": list(LIVE_IDENTITY_FIELDS),
        "must_be_positive": True,
        "must_be_distinct_across_shards": True,
        "assigned_at": "live_setup_only",
        "fixture_values": None,
        "forbidden_provisioning_fields": list(LIVE_IDENTITY_FIELDS),
    }


def build_shard_fixture(config: dict[str, Any]) -> dict[str, Any]:
    """Clone the canonical 2/3/5 roster into six disjoint 10-bot pools."""
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
        for slot_index, (slot_id, source) in enumerate(slots.items(), 1):
            account_id = 20000 + shard_index * 100 + slot_index
            guid = 30000 + shard_index * 100 + slot_index
            bot = copy.deepcopy(source)
            bot.update({
                "canonical_roster_slot_id": slot_id,
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
                    "source_config": "experiments/configs/validation_provisioning_cata_001.json",
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
            "required_bot_count": 10,
            "role_counts": {"tank": 2, "healer": 3, "dps": 5},
            "start_position": starts.get(profile_id, {}),
            "diagnostic_only": True,
            "diagnostic_parent_scenario_id": CANONICAL_SCENARIO_ID,
            "predecessor_state": predecessor,
            "live_identity_requirements": _live_requirements(),
            "bots": bots,
        })
    fixture = {
        "schema": "cata_raid_bwd_diagnostic_shard_fixture_v1",
        "source": {"provisioning_config": "experiments/configs/validation_provisioning_cata_001.json", "canonical_scenario_id": CANONICAL_SCENARIO_ID, "runtime_profile_manifest": "dataset/bot_runtime_profiles/profiles.json", "scenario_manifest": "experiments/configs/validation_scenarios_cata_001.json"},
        "canonical_roster": [{"roster_slot_id": slot, "name": bot["name"], "account": bot["account"], "role": bot["role"], "class": bot["class"], "class_spec": bot["class_spec"]} for slot, bot in slots.items()],
        "diagnostic_bot_count": 60,
        "shard_count": 6,
        "instance_identity_policy": {"map_id": 669, "difficulty": "normal_10man", "no_instance_or_save_ids_in_provisioning": True, "live_identity_fields": list(LIVE_IDENTITY_FIELDS)},
        "shards": shards,
    }
    validate_shard_fixture(fixture, config)
    return fixture


def build_diagnostic_provisioning_config(config: dict[str, Any], fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    """Append diagnostic scenarios to a copy; never mutate canonical input."""
    fixture = fixture or build_shard_fixture(config)
    validate_shard_fixture(fixture, config)
    merged = copy.deepcopy(config)
    if not any(str(row.get("id")) == CANONICAL_SCENARIO_ID for row in merged.get("scenarios", [])):
        raise ValueError("canonical_bwd_scenario_missing_from_provisioning_config")
    talent_builds = merged.get("talent_builds_by_spec", {})
    for shard in fixture["shards"]:
        bots = copy.deepcopy(shard["bots"])
        for bot in bots:
            class_spec = str(bot.get("class_spec") or "")
            build = talent_builds.get(class_spec, {})
            for key in ("primary_talent_tree_id", "talents", "primary_tree_spells"):
                if key not in bot and key in build:
                    bot[key] = copy.deepcopy(build[key])
        merged["scenarios"].append({
            "id": shard["scenario_id"], "instance": "Blackwing Descent", "map_id": 669, "difficulty": "normal_10man",
            "provisioning_scenario_id": CANONICAL_SCENARIO_ID, "start_position": copy.deepcopy(shard["start_position"]),
            "required_roles": copy.deepcopy(shard["role_counts"]), "bots": bots,
            "diagnostic_only": True, "diagnostic_parent_scenario_id": CANONICAL_SCENARIO_ID,
            "runtime_profile_id": shard["runtime_profile_id"], "pool_tag": shard["pool_tag"],
            "predecessor_state": copy.deepcopy(shard["predecessor_state"]),
            "live_identity_requirements": copy.deepcopy(shard["live_identity_requirements"]),
        })
    return merged


def _duplicates(values: Iterable[Any]) -> list[Any]:
    seen: set[Any] = set()
    duplicates: list[Any] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def validate_shard_fixture(fixture: dict[str, Any], canonical_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate all immutable identities and the non-certifying prerequisite contract."""
    failures: list[dict[str, Any]] = []
    if fixture.get("schema") != "cata_raid_bwd_diagnostic_shard_fixture_v1":
        failures.append({"check": "schema"})
    shards = fixture.get("shards") if isinstance(fixture.get("shards"), list) else []
    if len(shards) != 6:
        failures.append({"check": "shard_count", "expected": 6, "actual": len(shards)})
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
        if len(bots) != 10:
            failures.append({"check": "shard_bot_count", "boss_key": boss, "actual": len(bots)})
        if {str(bot.get("canonical_roster_slot_id")) for bot in bots} != set(CANONICAL_ROSTER_SLOT_IDS):
            failures.append({"check": "roster_slot_coverage", "boss_key": boss})
        for bot in bots:
            for field in ("account_id", "character_guid"):
                value = bot.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    failures.append({"check": f"positive_{field}", "boss_key": boss})
            if bot.get("expected_account_id") != bot.get("account_id"):
                failures.append({"check": "account_id_expectation_drift", "boss_key": boss, "name": bot.get("name")})
            if bot.get("expected_character_guid") != bot.get("character_guid"):
                failures.append({"check": "character_guid_expectation_drift", "boss_key": boss, "name": bot.get("name")})
            name = str(bot.get("name") or "")
            if (not re.fullmatch(r"[A-Z][a-z]{1,11}", name)
                    or name != name[:1].upper() + name[1:].lower()):
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
    if int(fixture.get("diagnostic_bot_count") or 0) != 60 or len(all_bots) != 60:
        failures.append({"check": "diagnostic_bot_count", "expected": 60, "actual": len(all_bots)})
    if failures:
        raise ValueError(json.dumps({"schema": fixture.get("schema"), "failures": failures}, sort_keys=True))
    return {"all_passed": True, "diagnostic_bot_count": len(all_bots), "shard_count": len(shards)}


def validate_readback(fixture: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Check complete DB/console readback and require distinct live IDs."""
    validate_shard_fixture(fixture)
    expected = {(str(shard["shard_id"]), str(bot["name"])): (shard, bot) for shard in fixture["shards"] for bot in shard["bots"]}
    failures: list[dict[str, Any]] = []
    keys = [(str(row.get("shard_id")), str(row.get("name"))) for row in rows]
    if len(rows) != len(expected):
        failures.append({"check": "readback_row_count", "expected": len(expected), "actual": len(rows)})
    if _duplicates(keys):
        failures.append({"check": "readback_duplicate_rows"})
    live: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("shard_id")), str(row.get("name")))
        source = expected.get(key)
        if source is None:
            failures.append({"check": "unexpected_readback_identity", "key": key})
            continue
        shard, bot = source
        for field in ("account_id", "character_guid", "account", "pool_tag", "roster_slot_id", "runtime_profile_id", "evidence_namespace"):
            if row.get(field) != bot.get(field):
                failures.append({"check": "readback_identity", "field": field, "key": key})
        if int(row.get("map_id") or 0) != 669 or str(row.get("difficulty") or "") != "normal_10man":
            failures.append({"check": "readback_instance", "key": key})
        if row.get("certifies_predecessors") is True or row.get("predecessor_certifies") is True:
            failures.append({"check": "readback_predecessor_certification", "key": key})
        identities = row.get("live_identities")
        if identities is not None:
            if str(row.get("shard_id")) in live and live[str(row.get("shard_id"))] != identities:
                failures.append({"check": "inconsistent_live_identities", "shard_id": row.get("shard_id")})
            live[str(row.get("shard_id"))] = dict(identities)
    for shard in fixture["shards"]:
        shard_id = str(shard["shard_id"])
        identity = live.get(shard_id)
        if identity is None:
            failures.append({"check": "missing_live_identities", "shard_id": shard_id})
            continue
        for field in LIVE_IDENTITY_FIELDS:
            value = identity.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                failures.append({"check": "live_identity_positive", "shard_id": shard_id, "field": field})
    for field in LIVE_IDENTITY_FIELDS:
        values = [identity.get(field) for identity in live.values()]
        if len(values) != len(set(values)):
            failures.append({"check": "live_identity_not_distinct", "field": field})
    return {"all_passed": not failures, "failure_count": len(failures), "failures": failures, "readback_rows": len(rows), "shards": len(live)}


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
    print(json.dumps({"output": str(args.output), "diagnostic_bot_count": 60, "shard_count": 6}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
