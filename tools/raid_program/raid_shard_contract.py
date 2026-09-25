"""Raid-generic shard identity contract shared by every shard generator.

`bwd_shard_fixtures` (the accepted legacy BWD layout) and `raid_shard_plan`
(raid x boss x copies) both validate their rosters with these helpers:
native backpack consumable slots, native player names, duplicate identities,
catalog spec sources and the runtime-only live identity readback.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]

# Player::GetItemByPos(INVENTORY_SLOT_BAG_0, slot) and the native consumable
# scanner cover the 16 base-backpack slots [23, 39).  The validation roster
# keeps its three deterministic stacks in otherwise-unused slots 26-28.  Bank
# slots 39+ are not a legal substitute: they can be written to
# character_inventory but are invisible to the player-like use-item path.
NATIVE_BACKPACK_SLOT_START = 23
NATIVE_BACKPACK_SLOT_END = 39
VALIDATION_CONSUMABLE_SLOTS = (26, 27, 28)
LIVE_IDENTITY_FIELDS = ("group_id", "map_instance_id", "save_id", "attempt_id", "strategy_id", "assignment_generation")
READBACK_IDENTITY_FIELDS = ("account_id", "character_guid", "account", "pool_tag", "roster_slot_id",
                            "runtime_profile_id", "evidence_namespace")
# The accepted legacy BWD fixture always reads back on map 669, normal 10-man.
LEGACY_BWD_FIXTURE_SCHEMA = "cata_raid_bwd_diagnostic_shard_fixture_v1"
LEGACY_BWD_INSTANCE = (669, "normal_10man")
RAID_SHARD_PLAN_SCHEMA = "raid_shard_plan_v1"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def duplicates(values: Iterable[Any]) -> list[Any]:
    seen: set[Any] = set()
    result: list[Any] = []
    for value in values:
        if value in seen and value not in result:
            result.append(value)
        seen.add(value)
    return result


def valid_native_name(name: str) -> bool:
    """TrinityCore stores first-letter-uppercase ASCII names; digits force AT_LOGIN_RENAME."""
    return bool(re.fullmatch(r"[A-Z][a-z]{1,11}", name)) and name == name[:1].upper() + name[1:].lower()


def consumable_slot_failures(rows: Any, path: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return [{"path": path, "reason": "must_be_list"}]
    failures: list[dict[str, Any]] = []
    seen_slots: set[int] = set()
    for index, row in enumerate(rows):
        row_path = f"{path}[{index}]"
        if not isinstance(row, dict):
            failures.append({"path": row_path, "reason": "must_be_object"})
            continue
        raw_slot = row.get("slot")
        if isinstance(raw_slot, bool):
            failures.append({"path": row_path, "reason": "slot_must_be_integer", "slot": raw_slot})
            continue
        try:
            slot = int(raw_slot)
        except (TypeError, ValueError):
            failures.append({"path": row_path, "reason": "slot_must_be_integer", "slot": raw_slot})
            continue
        if slot < NATIVE_BACKPACK_SLOT_START or slot >= NATIVE_BACKPACK_SLOT_END:
            failures.append({
                "path": row_path,
                "reason": "slot_outside_native_backpack",
                "slot": slot,
                "allowed": {
                    "start_inclusive": NATIVE_BACKPACK_SLOT_START,
                    "end_exclusive": NATIVE_BACKPACK_SLOT_END,
                },
            })
        if slot in seen_slots:
            failures.append({"path": row_path, "reason": "duplicate_slot", "slot": slot})
        seen_slots.add(slot)
    return failures


def validate_native_consumable_slots(config: dict[str, Any]) -> dict[str, Any]:
    """Reject validation items that native player inventory cannot discover."""
    failures: list[dict[str, Any]] = []
    validated_rows = 0
    if "default_consumables" in config:
        defaults = config.get("default_consumables")
        failures.extend(consumable_slot_failures(defaults, "default_consumables"))
        if isinstance(defaults, list):
            validated_rows += len(defaults)
    for scenario_index, scenario in enumerate(config.get("scenarios", [])):
        if not isinstance(scenario, dict):
            continue
        scenario_id = str(scenario.get("id") or scenario_index)
        defaults = config.get("default_consumables", [])
        for bot_index, bot in enumerate(scenario.get("bots", [])):
            if not isinstance(bot, dict):
                continue
            rows = bot.get("consumables", defaults)
            path = f"scenarios[{scenario_index}:{scenario_id}].bots[{bot_index}:{bot.get('name', bot_index)}].consumables"
            failures.extend(consumable_slot_failures(rows, path))
            if isinstance(rows, list):
                validated_rows += len(rows)
    if failures:
        raise ValueError(json.dumps({
            "check": "native_backpack_consumable_slots",
            "failures": failures,
        }, sort_keys=True))
    return {
        "all_passed": True,
        "validated_rows": validated_rows,
        "native_backpack_slots": [NATIVE_BACKPACK_SLOT_START, NATIVE_BACKPACK_SLOT_END],
        "preferred_slots": list(VALIDATION_CONSUMABLE_SLOTS),
    }


def live_requirements() -> dict[str, Any]:
    return {
        "fields": list(LIVE_IDENTITY_FIELDS),
        "must_be_positive": True,
        "must_be_distinct_across_shards": True,
        "assigned_at": "live_setup_only",
        "fixture_values": None,
        "forbidden_provisioning_fields": list(LIVE_IDENTITY_FIELDS),
    }


def catalog_source(config: dict[str, Any], spec: str) -> dict[str, Any]:
    """The exact provisioning bot of one `catalog:<spec>` roster source."""
    reference = str(config.get("canonical_target_catalog") or "")
    if not reference:
        raise ValueError("diagnostic_catalog_source_missing")
    catalog = read_json(REPO_ROOT / reference)
    matches = [row for row in catalog.get("targets", []) if row.get("spec_target_id") == spec]
    if len(matches) != 1:
        raise ValueError(f"diagnostic_catalog_source_not_unique:{spec}")
    row = matches[0]
    bot = copy.deepcopy(row["provisioning_bot"])
    if (bot.get("class_spec") != spec or not row.get("gear_profile_id")
            or bot.get("gear_profile_id") != row["gear_profile_id"]
            or bot.get("gear_profile") != row["gear_profile_id"]):
        raise ValueError(f"diagnostic_catalog_source_identity_invalid:{spec}")
    return bot


def validate_shard_readback(fixture: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Check complete DB/console readback of every shard and require distinct live IDs.

    The legacy BWD fixture keeps its explicit map 669 / normal_10man check;
    only raid_shard_plan_v1 shards take map and difficulty from shard data.
    """
    schema = fixture.get("schema")
    if schema not in (LEGACY_BWD_FIXTURE_SCHEMA, RAID_SHARD_PLAN_SCHEMA):
        raise ValueError(f"readback_fixture_schema:{schema}")
    expected = {(str(shard["shard_id"]), str(bot["name"])): (shard, bot)
                for shard in fixture["shards"] for bot in shard["bots"]}
    failures: list[dict[str, Any]] = []
    keys = [(str(row.get("shard_id")), str(row.get("name"))) for row in rows]
    if len(rows) != len(expected):
        failures.append({"check": "readback_row_count", "expected": len(expected), "actual": len(rows)})
    if duplicates(keys):
        failures.append({"check": "readback_duplicate_rows"})
    live: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("shard_id")), str(row.get("name")))
        source = expected.get(key)
        if source is None:
            failures.append({"check": "unexpected_readback_identity", "key": key})
            continue
        shard, bot = source
        for field in READBACK_IDENTITY_FIELDS:
            if row.get(field) != bot.get(field):
                failures.append({"check": "readback_identity", "field": field, "key": key})
        map_id, difficulty = (LEGACY_BWD_INSTANCE if schema == LEGACY_BWD_FIXTURE_SCHEMA
                              else (int(shard.get("map_id") or 0), str(shard.get("difficulty") or "")))
        if int(row.get("map_id") or 0) != map_id or str(row.get("difficulty") or "") != difficulty:
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
    return {"all_passed": not failures, "failure_count": len(failures), "failures": failures,
            "readback_rows": len(rows), "shards": len(live)}
