"""Read-only preflight and guarded apply for raid-shard plan provisioning.

The plan's fixed identities sit above the core's MAX+1 allocators
(characters and items: ObjectMgr::SetHighestGuids; pets: LoadPetNumber;
auth.account: AUTO_INCREMENT). A write is admitted only when it cannot
collide now or later:

1. Ownership: no row inside the plan's reservation (per table, the span of
   IDs the plan uses) belongs to anything but the plan row expected at that
   exact ID, and no plan name/username exists at another ID. Items are keyed
   by the owning character's block, the same block the human tool uses.
2. Allocator: after the apply every allocator must stand above the
   reservation. That holds when the plan's anchor rows (the highest ID of
   every table, all in one anchor cohort) are already present, when the apply
   writes the anchor cohort first, or when rows above the reservation already
   exist. Otherwise the next allocator ID lies at or below the reservation top
   and could later enter an unwritten block, so the apply is refused.
3. No plan character is online.

The in-memory allocators of a running worldserver are invisible to SQL, so an
apply also requires the operator to attest that no worldserver is running.
Every cohort is written in its own transaction whose SQL guards repeat
checks 1-3 for that cohort before its first write.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from tools.raid_program import raid_shard_identity as ids

SCHEMA = "raid_shard_preflight_v1"
TABLES = ("characters", "accounts", "pets", "items")
ITEM_REFERENCE_TABLES = (("mail_items", "item_guid"), ("auctionhouse", "itemguid"), ("guild_bank_item", "item_guid"))
PRECONDITION = "no worldserver running: its in-memory GUID, item, pet and account allocators are not visible to SQL"
Query = Callable[[str, Sequence[Any]], list[dict[str, Any]]]


class PreflightError(ValueError):
    pass


def plan_reservation(plan: dict[str, Any]) -> dict[str, Any]:
    """Expected owners, per-table ID spans, the anchor cohort and its anchor rows."""
    characters: dict[int, str] = {}
    accounts: dict[int, str] = {}
    pets: dict[int, int] = {}
    item_blocks: dict[int, list[int]] = {}
    cohorts: dict[str, dict[str, Any]] = {}
    owner_cohort: dict[str, dict[int, str]] = {table: {} for table in TABLES}
    for shard in plan["shards"]:
        scenario = str(shard["scenario_id"])
        cohort = cohorts.setdefault(scenario, {"characters": [], "accounts": [], "pets": [], "item_blocks": []})
        for bot in shard["bots"]:
            guid = int(bot["expected_character_guid"])
            account = int(bot["expected_account_id"])
            base = int(bot["loadout"]["item_guid_base"])
            if base != ids.item_block_for_character(guid):
                raise PreflightError(f"item_block_not_keyed_by_character:{bot['name']}")
            characters[guid] = str(bot["name"])
            accounts[account] = str(bot["account"]).upper()
            item_blocks[guid] = [base, base + ids.ITEMS_PER_CHARACTER - 1]
            cohort["characters"].append([guid, str(bot["name"])])
            cohort["accounts"].append([account, str(bot["account"]).upper()])
            cohort["item_blocks"].append([guid, base, base + ids.ITEMS_PER_CHARACTER - 1])
            owner_cohort["characters"][guid] = scenario
            owner_cohort["accounts"][account] = scenario
            owner_cohort["items"][base + ids.ITEMS_PER_CHARACTER - 1] = scenario
            if bot.get("expected_pet_id"):
                pets[int(bot["expected_pet_id"])] = guid
                cohort["pets"].append([int(bot["expected_pet_id"]), guid])
                owner_cohort["pets"][int(bot["expected_pet_id"])] = scenario
    if not characters:
        raise PreflightError("plan_has_no_characters")
    spans = {
        "characters": [min(characters), max(characters)],
        "accounts": [min(accounts), max(accounts)],
        "pets": [min(pets), max(pets)] if pets else None,
        "items": [min(block[0] for block in item_blocks.values()), max(block[1] for block in item_blocks.values())],
    }
    top_guid = spans["characters"][1]
    anchors = {
        "characters": {"id": top_guid, "owner": characters[top_guid]},
        "accounts": {"id": spans["accounts"][1], "owner": accounts[spans["accounts"][1]]},
        "items": {"id": spans["items"][1], "owner": top_guid},
    }
    if pets:
        anchors["pets"] = {"id": spans["pets"][1], "owner": pets[spans["pets"][1]]}
    anchor_cohorts = {owner_cohort[table][anchor["id"]] for table, anchor in anchors.items()}
    if len(anchor_cohorts) != 1:
        raise PreflightError(f"anchor_rows_span_several_cohorts:{sorted(anchor_cohorts)}")
    return {
        "characters": characters, "accounts": accounts, "pets": pets, "item_blocks": item_blocks,
        "spans": spans, "anchors": anchors, "anchor_scenario_id": anchor_cohorts.pop(), "cohorts": cohorts,
    }


def _between(column: str, span: Sequence[int]) -> str:
    return f"`{column}` BETWEEN {int(span[0])} AND {int(span[1])}"


def fetch_preflight_facts(query_characters: Query, query_auth: Query, reservation: dict[str, Any]) -> dict[str, Any]:
    """Read-only SELECTs over exactly the plan's reservation and names."""
    spans = reservation["spans"]
    names = sorted(reservation["characters"].values())
    usernames = sorted(reservation["accounts"].values())
    name_marks = ", ".join(["%s"] * len(names))
    user_marks = ", ".join(["%s"] * len(usernames))

    def next_id(query: Query, table: str, column: str) -> int:
        rows = query(f"SELECT COALESCE(MAX(`{column}`), 0) + 1 AS `next` FROM `{table}`", ())
        return int(rows[0]["next"]) if rows else 1

    characters = {
        "rows": [{"id": int(r["guid"]), "owner": str(r["name"]), "online": int(r.get("online") or 0)}
                 for r in query_characters(
                     f"SELECT `guid`, `name`, `online` FROM `characters` WHERE {_between('guid', spans['characters'])} "
                     f"OR `name` IN ({name_marks})", tuple(names))],
        "next_allocator_id": next_id(query_characters, "characters", "guid"),
    }
    auto_increment = query_auth(
        "SELECT `AUTO_INCREMENT` AS `next` FROM information_schema.`TABLES` "
        "WHERE `TABLE_SCHEMA` = DATABASE() AND `TABLE_NAME` = 'account'", ())
    accounts = {
        "rows": [{"id": int(r["id"]), "owner": str(r["username"]).upper()}
                 for r in query_auth(
                     f"SELECT `id`, `username` FROM `account` WHERE {_between('id', spans['accounts'])} "
                     f"OR `username` IN ({user_marks})", tuple(usernames))],
        "next_allocator_id": max(next_id(query_auth, "account", "id"),
                                 int((auto_increment[0] if auto_increment else {}).get("next") or 0)),
    }
    pets: dict[str, Any] = {"rows": [], "next_allocator_id": next_id(query_characters, "character_pet", "id"),
                            "orphan_spell_pet_ids": []}
    if spans["pets"]:
        pets["rows"] = [{"id": int(r["id"]), "owner": int(r["owner"])} for r in query_characters(
            f"SELECT `id`, `owner` FROM `character_pet` WHERE {_between('id', spans['pets'])}", ())]
        pets["orphan_spell_pet_ids"] = sorted({int(r["guid"]) for r in query_characters(
            "SELECT DISTINCT ps.`guid` FROM `pet_spell` ps LEFT JOIN `character_pet` cp ON cp.`id` = ps.`guid` "
            f"WHERE ps.{_between('guid', spans['pets'])} AND cp.`id` IS NULL", ())})
    items = {
        "rows": [{"id": int(r["guid"]), "owner": int(r["owner_guid"])} for r in query_characters(
            f"SELECT `guid`, `owner_guid` FROM `item_instance` WHERE {_between('guid', spans['items'])}", ())],
        "next_allocator_id": next_id(query_characters, "item_instance", "guid"),
        "inventory_rows": [{"item": int(r["item"]), "guid": int(r["guid"])} for r in query_characters(
            f"SELECT `item`, `guid` FROM `character_inventory` WHERE {_between('item', spans['items'])}", ())],
        "foreign_references": [{"table": table, "item": int(r["item"])}
                               for table, column in ITEM_REFERENCE_TABLES
                               for r in query_characters(
                                   f"SELECT `{column}` AS `item` FROM `{table}` WHERE {_between(column, spans['items'])}", ())],
    }
    return {"characters": characters, "accounts": accounts, "pets": pets, "items": items}


def _expected_owner(reservation: dict[str, Any], table: str, row_id: int) -> Any:
    if table == "items":
        owner = ids.item_block_owner(row_id)
        return owner if owner in reservation["item_blocks"] else None
    return reservation[table].get(row_id)


def evaluate_preflight(plan: dict[str, Any], facts: dict[str, Any],
                       scenario_ids: Iterable[str] = ()) -> dict[str, Any]:
    reservation = plan_reservation(plan)
    selected = list(scenario_ids) or list(reservation["cohorts"])
    unknown = sorted(set(selected) - set(reservation["cohorts"]))
    if unknown:
        raise PreflightError(f"unknown_plan_cohorts:{unknown}")
    anchor_selected = reservation["anchor_scenario_id"] in selected
    refusals: list[dict[str, Any]] = []
    allocators: dict[str, Any] = {}
    for table in TABLES:
        span = reservation["spans"][table]
        if span is None:
            continue
        rows = (facts.get(table) or {}).get("rows") or []
        by_owner = {value: key for key, value in reservation[table].items()} if table in ("characters", "accounts") else {}
        for row in rows:
            row_id, owner = int(row["id"]), row["owner"]
            if span[0] <= row_id <= span[1]:
                expected = _expected_owner(reservation, table, row_id)
                if expected is None or owner != expected:
                    refusals.append({"check": "foreign_row_in_reservation", "table": table, "id": row_id,
                                     "owner": owner, "expected_owner": expected})
            if owner in by_owner and by_owner[owner] != row_id:
                refusals.append({"check": "plan_identity_at_foreign_id", "table": table, "id": row_id,
                                 "owner": owner, "expected_id": by_owner[owner]})
        anchor = reservation["anchors"][table]
        anchor_present = any(int(row["id"]) == anchor["id"] and row["owner"] == anchor["owner"] for row in rows)
        next_id = int((facts.get(table) or {}).get("next_allocator_id") or 0)
        allocators[table] = {"span": span, "next_allocator_id": next_id, "anchor": anchor,
                             "anchor_present": anchor_present}
        if not (anchor_present or anchor_selected) and next_id <= span[1]:
            refusals.append({"check": "allocator_can_enter_reservation", "table": table,
                             "next_allocator_id": next_id, "span": span,
                             "remedy": f"apply the anchor cohort {reservation['anchor_scenario_id']} first"})
    items = facts.get("items") or {}
    for row in items.get("inventory_rows") or []:
        if row["guid"] != ids.item_block_owner(row["item"]):
            refusals.append({"check": "foreign_inventory_reference", "item": row["item"], "character": row["guid"]})
    for row in items.get("foreign_references") or []:
        refusals.append({"check": "item_referenced_outside_inventory", **row})
    for pet_id in (facts.get("pets") or {}).get("orphan_spell_pet_ids") or []:
        refusals.append({"check": "orphan_pet_spell_in_reservation", "pet_id": pet_id})
    selected_guids = {guid for scenario in selected for guid, _name in reservation["cohorts"][scenario]["characters"]}
    for row in (facts.get("characters") or {}).get("rows") or []:
        if row.get("online") and int(row["id"]) in selected_guids:
            refusals.append({"check": "plan_character_online", "id": row["id"], "name": row["owner"]})
    return {
        "schema": SCHEMA, "composition_id": plan.get("composition_id"), "passed": not refusals,
        "refusals": refusals, "selected_scenario_ids": selected, "anchor_scenario_id": reservation["anchor_scenario_id"],
        "anchor_selected": anchor_selected, "allocators": allocators, "precondition": PRECONDITION,
    }


def order_cohorts(reservation: dict[str, Any], scenario_ids: Iterable[str]) -> list[str]:
    """Selected cohorts with the anchor cohort first, so later cohorts sit below the allocators."""
    selected = list(scenario_ids) or list(reservation["cohorts"])
    anchor = reservation["anchor_scenario_id"]
    return ([anchor] if anchor in selected else []) + [sid for sid in selected if sid != anchor]


def _database_name(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url).path or "/").lstrip("/")


def _qualify(statement: str, characters_db: str, auth_db: str) -> str:
    return (statement.replace("`characters`.", f"`{characters_db.replace('`', '``')}`.")
            .replace("`auth`.", f"`{auth_db.replace('`', '``')}`."))


def execute_cohort_transactions(connection: Any, cohorts: list[tuple[str, list[str]]],
                                characters_db: str, auth_db: str) -> dict[str, Any]:
    """Run each cohort in its own transaction; stop at the first failure (rolled back)."""
    committed: list[str] = []
    for scenario_id, statements in cohorts:
        try:
            connection.begin()
            with connection.cursor() as cursor:
                for statement in statements:
                    if statement in ("START TRANSACTION", "COMMIT"):
                        continue
                    cursor.execute(_qualify(statement, characters_db, auth_db))
            connection.commit()
            committed.append(scenario_id)
        except Exception as exc:  # the failed cohort is rolled back, earlier ones stay committed
            connection.rollback()
            return {"committed": committed, "failed": scenario_id, "error": f"{type(exc).__name__}: {exc}"}
    return {"committed": committed, "failed": None, "error": None}


def main() -> int:
    from tools.bot_ml.extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf
    from tools.raid_program.raid_loadout_sql import cohort_statements

    parser = argparse.ArgumentParser(description="Read-only raid-shard preflight; optionally apply per-cohort transactions.")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--scenario-id", action="append", default=[])
    parser.add_argument("--worldserver-conf", type=Path, default=Path("trinity-worldserver-test.conf"))
    parser.add_argument("--gear-profiles", type=Path, default=Path("dataset/validation_gear_profiles/profiles.json"))
    parser.add_argument("--dbc-dir", type=Path, default=Path("data/dbc/enUS"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--attest-no-worldserver-running", action="store_true")
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    character_url = database_url_from_worldserver_conf(args.worldserver_conf, "CharacterDatabaseInfo")
    auth_url = database_url_from_worldserver_conf(args.worldserver_conf, "LoginDatabaseInfo")

    def reader(url: str) -> Query:
        def query(sql: str, params: Sequence[Any]) -> list[dict[str, Any]]:
            connection = connect_mysql(url)
            try:
                with connection.cursor() as cursor:
                    cursor.execute(sql, tuple(params))
                    return [dict(row) for row in cursor.fetchall()]
            finally:
                connection.close()
        return query

    reservation = plan_reservation(plan)
    report = evaluate_preflight(plan, fetch_preflight_facts(reader(character_url), reader(auth_url), reservation),
                                args.scenario_id)
    report["applied"] = None
    if args.apply:
        if not args.attest_no_worldserver_running:
            report["passed"] = False
            report["refusals"].append({"check": "apply_requires_no_worldserver_attestation"})
        elif report["passed"]:
            statements = cohort_statements(plan, order_cohorts(reservation, args.scenario_id),
                                           args.gear_profiles, args.dbc_dir)
            connection = connect_mysql(character_url)
            try:
                report["applied"] = execute_cohort_transactions(
                    connection, statements, _database_name(character_url), _database_name(auth_url))
            finally:
                connection.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "refusals": len(report["refusals"]),
                      "applied": report["applied"]}, sort_keys=True))
    applied_ok = report["applied"] is None or not report["applied"]["failed"]
    return 0 if report["passed"] and applied_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
