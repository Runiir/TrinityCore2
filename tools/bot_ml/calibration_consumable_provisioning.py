from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

try:
    from .cata_dps_consumables import validate_controlled_consumable_profile
    from .extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf
except ImportError:
    from cata_dps_consumables import validate_controlled_consumable_profile
    from extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf


CALIBRATION_CONSUMABLE_SLOTS = (26, 27, 28)
CALIBRATION_CONSUMABLE_REQUIRED_USES = {
    "flask": 1,
    "food": 1,
    "prepot": 1,
    "combat_potion": 1,
}


def database_name(database_url: str) -> str:
    return (urlparse(database_url).path or "/").lstrip("/")


def _split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    uncommented = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    for char in uncommented:
        current.append(char)
        if escaped:
            escaped = False
            continue
        if quote and char == "\\":
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        elif char == ";" and quote is None:
            statement = "".join(current).strip().rstrip(";").strip()
            if statement and not statement.startswith("--"):
                statements.append(statement)
            current = []
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _execute_sql_text(database_url: str, sql: str) -> int:
    statements = _split_sql_statements(sql)
    conn = connect_mysql(database_url)
    try:
        with conn.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        conn.commit()
    finally:
        conn.close()
    return len(statements)


def load_calibration_consumable_contract(
    target_spec: str,
    target_catalog_path: Path,
) -> dict[str, Any]:
    """Load one target's ordinary inventory contract from the canonical catalog."""
    catalog = json.loads(target_catalog_path.read_text(encoding="utf-8"))
    target = next(
        (
            row for row in catalog.get("targets", [])
            if isinstance(row, dict)
            and str(row.get("spec_target_id") or "") == target_spec
        ),
        None,
    )
    if not isinstance(target, dict):
        raise RuntimeError(f"calibration target is not in canonical catalog: {target_spec}")
    provisioning = target.get("provisioning_bot")
    if not isinstance(provisioning, dict):
        raise RuntimeError(f"{target_spec}: canonical provisioning bot is missing")
    profile = provisioning.get("controlled_consumable_profile")
    if not isinstance(profile, dict):
        raise RuntimeError(f"{target_spec}: controlled consumable profile is missing")
    try:
        validate_controlled_consumable_profile(target_spec, profile)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    inventory = profile.get("inventory")
    if not isinstance(inventory, list) or len(inventory) != len(CALIBRATION_CONSUMABLE_SLOTS):
        raise RuntimeError(f"{target_spec}: controlled consumable inventory is incomplete")
    normalized_inventory = []
    seen_slots: set[int] = set()
    for row in inventory:
        if not isinstance(row, dict):
            raise RuntimeError(f"{target_spec}: controlled consumable inventory row is invalid")
        slot = int(row.get("slot") or 0)
        item_id = int(row.get("item_id") or 0)
        count = int(row.get("count") or 0)
        if slot not in CALIBRATION_CONSUMABLE_SLOTS or slot in seen_slots or item_id <= 0 or count <= 0:
            raise RuntimeError(f"{target_spec}: controlled consumable inventory identity is invalid")
        seen_slots.add(slot)
        normalized_inventory.append({"slot": slot, "item_id": item_id, "count": count})
    if tuple(sorted(seen_slots)) != CALIBRATION_CONSUMABLE_SLOTS:
        raise RuntimeError(f"{target_spec}: controlled consumable inventory slots drifted")
    if list(provisioning.get("consumables") or []) != list(profile["inventory"]):
        raise RuntimeError(f"{target_spec}: provisioning consumables differ from controlled profile")
    return {
        "schema": "cata_calibration_consumable_restock_v1",
        "target_spec": target_spec,
        "character_name": str(provisioning.get("name") or ""),
        "class_spec": str(provisioning.get("class_spec") or ""),
        "pool_tag": "all_spec_candidate_pool",
        "inventory": sorted(normalized_inventory, key=lambda row: row["slot"]),
        "required_uses": dict(CALIBRATION_CONSUMABLE_REQUIRED_USES),
    }


def calibration_consumable_inventory_mismatches(
    character_guid: int,
    expected_inventory: list[dict[str, int]],
    actual_inventory: Mapping[int, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    for expected in expected_inventory:
        slot = int(expected["slot"])
        actual = actual_inventory.get(slot, {})
        expected_identity = {
            "bag": 0,
            "slot": slot,
            "item_id": int(expected["item_id"]),
            "owner_guid": int(character_guid),
            "count": int(expected["count"]),
        }
        actual_identity = {
            key: int(actual.get(key) or 0)
            for key in expected_identity
        }
        wrong_fields = [
            key for key, value in expected_identity.items()
            if actual_identity[key] != value
        ]
        if wrong_fields:
            mismatches.append({
                "slot": slot,
                "wrong_fields": wrong_fields,
                "expected": expected_identity,
                "actual": actual_identity,
            })
    return mismatches


def build_calibration_consumable_restock_sql(
    character_database: str,
    character_guid: int,
    expected_inventory: list[dict[str, int]],
    old_item_guids: list[int],
    new_item_guids: list[int],
) -> str:
    """Replace only the target's consumable slots before native calibration."""
    if len(expected_inventory) != len(new_item_guids) or len(expected_inventory) != len(CALIBRATION_CONSUMABLE_SLOTS):
        raise ValueError("calibration consumable restock requires exactly three inventory rows")
    if len(set(new_item_guids)) != len(new_item_guids) or any(guid <= 0 for guid in new_item_guids):
        raise ValueError("calibration consumable restock item GUIDs must be unique and positive")
    table = f"`{character_database.replace('`', '``')}`"
    old_guids = ", ".join(str(int(guid)) for guid in sorted(set(old_item_guids)) if int(guid) > 0)
    lines = [
        "-- Generated by tools.bot_ml.calibration_consumable_provisioning.",
        "-- Restocks only the selected all-spec calibration character's ordinary item inventory.",
        "START TRANSACTION;",
        f"DELETE FROM {table}.`character_inventory` WHERE `guid` = {int(character_guid)} AND `bag` = 0 AND `slot` IN ({', '.join(str(slot) for slot in CALIBRATION_CONSUMABLE_SLOTS)});",
    ]
    if old_guids:
        lines.append(
            f"DELETE FROM {table}.`item_instance` WHERE `owner_guid` = {int(character_guid)} AND `guid` IN ({old_guids});"
        )
    for row, item_guid in zip(sorted(expected_inventory, key=lambda value: value["slot"]), new_item_guids):
        lines.append(
            f"INSERT INTO {table}.`item_instance` (`guid`, `itemEntry`, `owner_guid`, `creatorGuid`, `giftCreatorGuid`, `count`, `duration`, `charges`, `flags`, `enchantments`, `randomPropertyType`, `randomPropertyId`, `durability`, `creationTime`, `text`) VALUES ({int(item_guid)}, {int(row['item_id'])}, {int(character_guid)}, 0, 0, {int(row['count'])}, 0, '', 0, '', 0, 0, 1, UNIX_TIMESTAMP(), '');"
        )
        lines.append(
            f"INSERT INTO {table}.`character_inventory` (`guid`, `bag`, `slot`, `item`) VALUES ({int(character_guid)}, 0, {int(row['slot'])}, {int(item_guid)});"
        )
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


def prepare_calibration_consumables(
    output_dir: Path,
    worldserver_conf: Path,
    target_spec: str,
    target_catalog_path: Path,
    apply: bool = False,
    *,
    connect_mysql_fn: Callable[..., Any] = connect_mysql,
    database_name_fn: Callable[[str], str] = database_name,
    database_url_from_conf_fn: Callable[[Path, str], str] = database_url_from_worldserver_conf,
    execute_sql_text_fn: Callable[[str, str], int] = _execute_sql_text,
) -> dict[str, Any]:
    """Provision and read back one isolated target before its cohort starts."""
    contract = load_calibration_consumable_contract(target_spec, target_catalog_path)
    if not apply:
        return {
            "schema": "bot_live_validation_calibration_consumable_restock_v1",
            "target_spec": target_spec,
            "character_name": contract["character_name"],
            "pool_tag": contract["pool_tag"],
            "expected_inventory": contract["inventory"],
            "required_uses": contract["required_uses"],
            "applied": False,
            "preflight": "deferred_until_database_apply",
        }
    character_url = database_url_from_conf_fn(worldserver_conf, "CharacterDatabaseInfo")
    character_db = database_name_fn(character_url)
    conn = connect_mysql_fn(character_url)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT c.guid, c.name, cbp.class_spec, cbp.experiment_tags, cbp.enabled, cbp.in_use "
                "FROM characters c JOIN character_bot_pool cbp ON cbp.guid = c.guid "
                "WHERE c.name = %s AND cbp.class_spec = %s AND cbp.experiment_tags = %s",
                (contract["character_name"], contract["class_spec"], contract["pool_tag"]),
            )
            candidates = cursor.fetchall()
            if len(candidates) != 1:
                raise RuntimeError(f"{target_spec}: expected one canonical calibration pool row, found {len(candidates)}")
            candidate = candidates[0]
            if not bool(candidate.get("enabled")) or bool(candidate.get("in_use")):
                raise RuntimeError(f"{target_spec}: canonical calibration pool row is not idle and enabled")
            character_guid = int(candidate["guid"])
            cursor.execute(
                "SELECT ci.bag, ci.slot, ci.item, ii.itemEntry, ii.owner_guid, ii.count "
                "FROM character_inventory ci LEFT JOIN item_instance ii ON ii.guid = ci.item "
                "WHERE ci.guid = %s AND ci.bag = 0 AND ci.slot IN (%s, %s, %s)",
                (character_guid, *CALIBRATION_CONSUMABLE_SLOTS),
            )
            rows = cursor.fetchall()
            old_item_guids = [int(row.get("item") or 0) for row in rows]
            cursor.execute("SELECT COALESCE(MAX(guid), 0) AS max_guid FROM item_instance")
            max_guid = int((cursor.fetchone() or {}).get("max_guid") or 0)
    finally:
        conn.close()

    new_item_guids = [max_guid + index + 1 for index in range(len(contract["inventory"]))]
    if any(guid <= 0 or guid >= 4_294_967_295 for guid in new_item_guids):
        raise RuntimeError(f"{target_spec}: item GUID space is exhausted")
    sql = build_calibration_consumable_restock_sql(
        character_db,
        character_guid,
        contract["inventory"],
        old_item_guids,
        new_item_guids,
    )
    restock_dir = output_dir / "calibration_consumable_restock"
    restock_dir.mkdir(parents=True, exist_ok=True)
    sql_path = restock_dir / f"{target_spec}.sql"
    sql_path.write_text(sql, encoding="utf-8")
    report: dict[str, Any] = {
        "schema": "bot_live_validation_calibration_consumable_restock_v1",
        "target_spec": target_spec,
        "character_name": contract["character_name"],
        "character_guid": character_guid,
        "pool_tag": contract["pool_tag"],
        "expected_inventory": contract["inventory"],
        "required_uses": contract["required_uses"],
        "old_item_guids": sorted(set(old_item_guids)),
        "new_item_guids": new_item_guids,
        "sql": str(sql_path),
        "applied": bool(apply),
    }
    report["executed_statements"] = execute_sql_text_fn(character_url, sql)
    conn = connect_mysql_fn(character_url)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT ci.bag, ci.slot, ii.itemEntry AS item_id, ii.owner_guid, ii.count "
                "FROM character_inventory ci JOIN item_instance ii ON ii.guid = ci.item "
                "WHERE ci.guid = %s AND ci.bag = 0 AND ci.slot IN (%s, %s, %s)",
                (character_guid, *CALIBRATION_CONSUMABLE_SLOTS),
            )
            actual = {int(row["slot"]): row for row in cursor.fetchall()}
    finally:
        conn.close()
    mismatches = calibration_consumable_inventory_mismatches(
        character_guid, contract["inventory"], actual
    )
    report["readback"] = {
        "observed_slots": sorted(actual),
        "mismatches": mismatches,
        "passed": not mismatches,
    }
    if mismatches:
        raise RuntimeError(
            f"{target_spec}: calibration consumable inventory readback failed: {mismatches}"
        )
    return report
