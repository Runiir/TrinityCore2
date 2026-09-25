from __future__ import annotations

import json

import pytest

from tests.test_raid_shard_plan import _plan
from tools.raid_program import raid_shard_identity as ids
from tools.raid_program.raid_shard_preflight import (
    PreflightError,
    evaluate_preflight,
    execute_cohort_transactions,
    fetch_preflight_facts,
    order_cohorts,
    plan_reservation,
)

MAGMAW = "blackwing_descent_10n_magmaw_c0_diagnostic"
NEFARIAN = "blackwing_descent_10n_nefarian_c0_diagnostic"


@pytest.fixture(scope="module")
def plan() -> dict:
    return _plan()


def empty_facts(next_id: int = 1) -> dict:
    """A database whose allocators stand below the reservation and hold no plan rows."""
    return {
        "characters": {"rows": [], "next_allocator_id": next_id},
        "accounts": {"rows": [], "next_allocator_id": next_id},
        "pets": {"rows": [], "next_allocator_id": next_id, "orphan_spell_pet_ids": []},
        "items": {"rows": [], "next_allocator_id": next_id, "inventory_rows": [], "foreign_references": []},
    }


def anchored_facts(plan: dict) -> dict:
    """The anchor cohort is present and the allocators restarted above the reservation."""
    reservation = plan_reservation(plan)
    facts = empty_facts()
    for table, anchor in reservation["anchors"].items():
        facts[table]["rows"].append({"id": anchor["id"], "owner": anchor["owner"], "online": 0})
        facts[table]["next_allocator_id"] = anchor["id"] + 1
    return facts


def checks(report: dict) -> set[str]:
    return {row["check"] for row in report["refusals"]}


def test_reservation_spans_and_single_anchor_cohort(plan):
    reservation = plan_reservation(plan)
    assert reservation["anchor_scenario_id"] == NEFARIAN
    assert reservation["spans"]["characters"] == [11_000_001, 11_005_010]
    assert reservation["spans"]["accounts"] == [21_000_001, 21_005_010]
    assert reservation["spans"]["pets"] == [31_000_003, 31_005_003]
    top = reservation["anchors"]["characters"]["id"]
    assert reservation["spans"]["items"] == [ids.item_block_for_character(11_000_001),
                                             ids.item_block_for_character(top) + 99]
    assert reservation["anchors"]["items"] == {"id": ids.item_block_for_character(top) + 99, "owner": top}
    assert order_cohorts(reservation, [MAGMAW, NEFARIAN]) == [NEFARIAN, MAGMAW]
    assert order_cohorts(reservation, [MAGMAW]) == [MAGMAW]


def test_first_apply_passes_only_with_the_anchor_cohort(plan):
    assert evaluate_preflight(plan, empty_facts())["passed"] is True
    assert evaluate_preflight(plan, empty_facts(), [NEFARIAN, MAGMAW])["passed"] is True
    report = evaluate_preflight(plan, empty_facts(), [MAGMAW])
    assert report["passed"] is False
    refused = {row["table"] for row in report["refusals"] if row["check"] == "allocator_can_enter_reservation"}
    assert refused == {"characters", "accounts", "pets", "items"}
    assert all(NEFARIAN in row["remedy"] for row in report["refusals"])


def test_partial_apply_is_admitted_once_the_anchor_exists(plan):
    report = evaluate_preflight(plan, anchored_facts(plan), [MAGMAW])
    assert report["passed"] is True
    assert all(row["anchor_present"] for row in report["allocators"].values())


def test_rows_above_the_reservation_also_admit_a_partial_apply(plan):
    facts = empty_facts(next_id=40_000_000)
    facts["items"]["next_allocator_id"] = 2_000_000_000
    assert evaluate_preflight(plan, facts, [MAGMAW])["passed"] is True


def test_allocator_standing_inside_the_reservation_is_refused_without_the_anchor(plan):
    facts = anchored_facts(plan)
    facts["accounts"]["rows"] = []
    facts["accounts"]["next_allocator_id"] = 21_003_000  # AUTO_INCREMENT inside the account span
    report = evaluate_preflight(plan, facts, [MAGMAW])
    assert [row["table"] for row in report["refusals"]] == ["accounts"]
    assert evaluate_preflight(plan, facts, [MAGMAW, NEFARIAN])["passed"] is True


@pytest.mark.parametrize("table,row,check", [
    ("characters", {"id": 11_000_011, "owner": "Humanalt", "online": 0}, "foreign_row_in_reservation"),
    ("characters", {"id": 11_000_001, "owner": "Somebody", "online": 0}, "foreign_row_in_reservation"),
    ("characters", {"id": 40_000_000, "owner": "Bwmgwnba", "online": 0}, "plan_identity_at_foreign_id"),
    ("accounts", {"id": 21_000_050, "owner": "PLAYER"}, "foreign_row_in_reservation"),
    ("accounts", {"id": 5, "owner": "RS1000001"}, "plan_identity_at_foreign_id"),
    ("pets", {"id": 31_000_003, "owner": 11_000_001}, "foreign_row_in_reservation"),
    ("pets", {"id": 31_000_004, "owner": 11_000_004}, "foreign_row_in_reservation"),
    # A human (or core-created) character inside the span owns the matching item block.
    ("items", {"id": ids.item_block_for_character(11_000_011) + 5, "owner": 11_000_011}, "foreign_row_in_reservation"),
    ("items", {"id": ids.item_block_for_character(11_000_001) + 5, "owner": 11_000_002}, "foreign_row_in_reservation"),
])
def test_foreign_rows_inside_the_reservation_are_refused(plan, table, row, check):
    facts = anchored_facts(plan)
    facts[table]["rows"].append(row)
    report = evaluate_preflight(plan, facts)
    assert check in checks(report)
    assert report["passed"] is False


def test_own_rows_from_an_earlier_apply_are_admitted(plan):
    facts = anchored_facts(plan)
    magmaw = next(shard for shard in plan["shards"] if shard["scenario_id"] == MAGMAW)
    for bot in magmaw["bots"]:
        guid = bot["expected_character_guid"]
        facts["characters"]["rows"].append({"id": guid, "owner": bot["name"], "online": 0})
        facts["accounts"]["rows"].append({"id": bot["expected_account_id"], "owner": bot["account"].upper()})
        facts["items"]["rows"].append({"id": ids.item_block_for_character(guid) + 7, "owner": guid})
        facts["items"]["inventory_rows"].append({"item": ids.item_block_for_character(guid) + 7, "guid": guid})
        if bot.get("expected_pet_id"):
            facts["pets"]["rows"].append({"id": bot["expected_pet_id"], "owner": guid})
    assert evaluate_preflight(plan, facts, [MAGMAW])["passed"] is True


def test_item_references_orphan_pet_spells_and_online_characters_are_refused(plan):
    facts = anchored_facts(plan)
    item = ids.item_block_for_character(11_000_001) + 3
    facts["items"]["inventory_rows"].append({"item": item, "guid": 30_001})
    facts["items"]["foreign_references"].append({"table": "mail_items", "item": item})
    facts["pets"]["orphan_spell_pet_ids"].append(31_000_003)
    facts["characters"]["rows"].append({"id": 11_000_001, "owner": "Bwmgwnba", "online": 1})
    report = evaluate_preflight(plan, facts, [MAGMAW])
    assert {"foreign_inventory_reference", "item_referenced_outside_inventory",
            "orphan_pet_spell_in_reservation", "plan_character_online"} <= checks(report)


def test_unknown_cohort_selection_fails_closed(plan):
    with pytest.raises(PreflightError, match="unknown_plan_cohorts"):
        evaluate_preflight(plan, empty_facts(), ["blackwing_descent_10n_magmaw_diagnostic"])


def test_fact_fetch_is_read_only_and_bounded_by_the_reservation(plan):
    calls = []

    def query(sql, params):
        calls.append((sql, tuple(params)))
        return [{"next": 7}] if "`next`" in sql else []

    reservation = plan_reservation(plan)
    facts = fetch_preflight_facts(query, query, reservation)
    assert calls and all(sql.startswith("SELECT ") for sql, _params in calls)
    assert any("information_schema" in sql and "'account'" in sql for sql, _params in calls)
    item_span = reservation["spans"]["items"]
    assert any(f"BETWEEN {item_span[0]} AND {item_span[1]}" in sql and "`item_instance`" in sql for sql, _ in calls)
    assert any("`mail_items`" in sql for sql, _ in calls) and any("`guild_bank_item`" in sql for sql, _ in calls)
    assert facts["characters"]["next_allocator_id"] == 7 and facts["accounts"]["next_allocator_id"] == 7
    names = next(params for sql, params in calls if "FROM `characters`" in sql and "`name` IN" in sql)
    assert set(names) == set(reservation["characters"].values())


class FakeCursor:
    def __init__(self, log, fail_on):
        self.log, self.fail_on = log, fail_on

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement):
        if self.fail_on and self.fail_on in statement:
            raise RuntimeError("ERROR 1242 abort guard")
        self.log.append(("execute", statement))


class FakeConnection:
    def __init__(self, fail_on=None):
        self.log, self.fail_on = [], fail_on

    def begin(self):
        self.log.append(("begin",))

    def commit(self):
        self.log.append(("commit",))

    def rollback(self):
        self.log.append(("rollback",))

    def cursor(self):
        return FakeCursor(self.log, self.fail_on)


def test_each_cohort_commits_or_rolls_back_alone():
    cohorts = [("anchor", ["START TRANSACTION", "INSERT INTO `characters`.`characters` x", "INSERT INTO `auth`.`account` y", "COMMIT"]),
               ("second", ["START TRANSACTION", "SET @raid_shard_abort_foreign_item = boom", "INSERT z", "COMMIT"]),
               ("third", ["START TRANSACTION", "INSERT w", "COMMIT"])]
    connection = FakeConnection(fail_on="boom")
    result = execute_cohort_transactions(connection, cohorts, "characters_lane", "auth_lane")
    assert result["committed"] == ["anchor"] and result["failed"] == "second"
    assert connection.log[:5] == [("begin",), ("execute", "INSERT INTO `characters_lane`.`characters` x"),
                                  ("execute", "INSERT INTO `auth_lane`.`account` y"), ("commit",), ("begin",)]
    assert connection.log[-1] == ("rollback",)
    assert not any(entry == ("execute", "INSERT w") for entry in connection.log)
    assert not any("START TRANSACTION" in str(entry) or entry == ("execute", "COMMIT") for entry in connection.log)


def test_cli_apply_requires_the_no_worldserver_attestation(tmp_path, monkeypatch, plan):
    import sys
    from tools.raid_program import raid_shard_preflight

    class Connection:
        def cursor(self):
            connection = self

            class Cursor:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

                def execute(self, sql, params=()):
                    self.sql = sql

                def fetchall(self):
                    return [{"next": 1}] if "`next`" in self.sql else []
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr("tools.bot_ml.extract_world_knowledge.connect_mysql", lambda url: Connection())
    monkeypatch.setattr("tools.bot_ml.extract_world_knowledge.database_url_from_worldserver_conf",
                        lambda path, key: "mysql://u:p@h:1/" + ("auth" if key == "LoginDatabaseInfo" else "characters"))
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    output = tmp_path / "preflight.json"
    monkeypatch.setattr(sys, "argv", ["raid_shard_preflight", "--plan", str(plan_path), "--output", str(output), "--apply"])
    assert raid_shard_preflight.main() == 1
    report = json.loads(output.read_text())
    assert "apply_requires_no_worldserver_attestation" in {row["check"] for row in report["refusals"]}
    assert report["applied"] is None
    monkeypatch.setattr(sys, "argv", ["raid_shard_preflight", "--plan", str(plan_path), "--output", str(output),
                                      "--scenario-id", MAGMAW])
    assert raid_shard_preflight.main() == 1  # read-only run, refused: anchor absent and not selected
    assert json.loads(output.read_text())["anchor_scenario_id"] == NEFARIAN
