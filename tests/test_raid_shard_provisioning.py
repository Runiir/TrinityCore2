"""Guarded plan-cohort provisioning for shard runs (tools.raid_program.raid_shard_provisioning)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.test_raid_shard_plan import _plan
from tests.test_raid_shard_preflight import anchored_facts, empty_facts
from tools.raid_program import raid_shard_provisioning as rsp

ROOT = Path(__file__).resolve().parents[1]
GEAR = ROOT / "dataset/validation_gear_profiles/profiles.json"
DBC = ROOT / "data/dbc/enUS"
MAGMAW = "blackwing_descent_10n_magmaw_c0_diagnostic"
MALORIAK = "blackwing_descent_10n_maloriak_c0_diagnostic"
NEFARIAN = "blackwing_descent_10n_nefarian_c0_diagnostic"
CHARACTERS = "mysql://trinity:pw@127.0.0.1:3306/characters"
AUTH = "mysql://trinity:pw@127.0.0.1:3306/auth"


class FakeConnection:
    def __init__(self, fail_on: str = ""):
        self.events: list[str] = []
        self.fail_on = fail_on
        self.closed = False

    def begin(self):
        self.events.append("begin")

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")

    def close(self):
        self.closed = True

    def cursor(self):
        connection = self

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, statement):
                if connection.fail_on and connection.fail_on in statement:
                    raise RuntimeError("ERROR 1242")
                connection.events.append(statement)
        return Cursor()


@pytest.fixture()
def plan_path(tmp_path) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(_plan()), encoding="utf-8")
    return path


def _run(plan_path, monkeypatch, *, selected, facts, pgrep_code=1, connection=None, readback_passed=True,
         apply=True, output=None):
    calls = {"facts": 0, "statements": None}
    sequence = list(facts)

    def fetch(_characters, _auth, _reservation):
        calls["facts"] += 1
        return copy.deepcopy(sequence.pop(0) if len(sequence) > 1 else sequence[0])

    def statements(_plan, order, *_args):
        calls["statements"] = list(order)
        return [(scenario_id, ["START TRANSACTION", f"INSERT {scenario_id}", "COMMIT"]) for scenario_id in order]

    monkeypatch.setattr(rsp, "fetch_preflight_facts", fetch)
    monkeypatch.setattr(rsp, "_loadout_readback", lambda *args: {"characters": 10, "failures": [],
                                                                "passed": readback_passed})
    connection = connection or FakeConnection()
    report = rsp.provision_plan_cohorts(
        plan_path, selected, character_url=CHARACTERS, auth_url=AUTH, gear_profiles=GEAR, apply=apply,
        output=output, readers=(lambda *a: [], lambda *a: []), connect=lambda url: connection,
        pgrep=lambda: {"command": "pgrep -x worldserver", "returncode": pgrep_code, "pids": [] if pgrep_code == 1 else [7]},
        statements=statements)
    return report, calls, connection


def test_first_apply_adds_the_anchor_cohort_and_writes_it_first(plan_path, monkeypatch, tmp_path):
    plan = json.loads(plan_path.read_text())
    report, calls, connection = _run(plan_path, monkeypatch, selected=[MAGMAW],
                                     facts=[empty_facts(), empty_facts(), anchored_facts(plan)],
                                     output=tmp_path / "prep" / "raid_shard_provisioning.json")
    assert report["passed"] and report["anchor_added"] == NEFARIAN
    assert report["apply_scenario_ids"] == calls["statements"] == [NEFARIAN, MAGMAW]
    # One transaction per cohort, anchor first; START/COMMIT come from execute_cohort_transactions.
    assert connection.events == ["begin", f"INSERT {NEFARIAN}", "commit", "begin", f"INSERT {MAGMAW}", "commit"]
    assert connection.closed and report["applied"] == {"committed": [NEFARIAN, MAGMAW], "failed": None, "error": None}
    assert report["readback_preflight"]["passed"] and report["loadout_readback"]["passed"]
    written = json.loads((tmp_path / "prep" / "raid_shard_provisioning.json").read_text())
    assert written["passed"] is True and written["selected_scenario_ids"] == [MAGMAW]


def test_present_anchor_is_not_rewritten(plan_path, monkeypatch):
    plan = json.loads(plan_path.read_text())
    report, calls, _ = _run(plan_path, monkeypatch, selected=[MAGMAW, MALORIAK], facts=[anchored_facts(plan)])
    assert "anchor_added" not in report and calls["statements"] == [MAGMAW, MALORIAK]


def test_six_shard_selection_orders_the_anchor_first(plan_path, monkeypatch):
    plan = json.loads(plan_path.read_text())
    everything = [shard["scenario_id"] for shard in plan["shards"]]
    report, calls, _ = _run(plan_path, monkeypatch, selected=everything,
                            facts=[empty_facts(), anchored_facts(plan)])
    assert calls["statements"][0] == NEFARIAN and sorted(calls["statements"]) == sorted(everything)
    assert "anchor_added" not in report


def test_a_running_worldserver_refuses_before_any_write(plan_path, monkeypatch):
    with pytest.raises(rsp.RaidShardProvisioningError, match="apply_refused:worldserver_process_running_or_unknown") as error:
        _run(plan_path, monkeypatch, selected=[NEFARIAN], facts=[empty_facts()], pgrep_code=0)
    assert error.value.report["applied"] is None


def test_split_database_servers_are_refused(plan_path, monkeypatch):
    monkeypatch.setattr(rsp, "fetch_preflight_facts", lambda *a: empty_facts())
    with pytest.raises(rsp.RaidShardProvisioningError, match="auth_and_characters_on_different_servers"):
        rsp.provision_plan_cohorts(plan_path, [NEFARIAN], character_url=CHARACTERS,
                                   auth_url="mysql://trinity:pw@10.0.0.9:3306/auth", gear_profiles=GEAR,
                                   readers=(lambda *a: [], lambda *a: []), pgrep=lambda: {"returncode": 1},
                                   connect=lambda url: pytest.fail("no write may happen"))


def test_foreign_rows_refuse_the_preflight(plan_path, monkeypatch):
    plan = json.loads(plan_path.read_text())
    facts = anchored_facts(plan)
    facts["characters"]["rows"].append({"id": 11_000_001, "owner": "Somebody", "online": 0})
    with pytest.raises(rsp.RaidShardProvisioningError, match="preflight_refused") as error:
        _run(plan_path, monkeypatch, selected=[MAGMAW], facts=[facts])
    assert "foreign_row_at_plan_identity" in {row["check"] for row in error.value.report["preflight"]["refusals"]}


def test_a_failed_cohort_transaction_stops_the_run(plan_path, monkeypatch):
    plan = json.loads(plan_path.read_text())
    connection = FakeConnection(fail_on=f"INSERT {MAGMAW}")
    with pytest.raises(rsp.RaidShardProvisioningError, match=f"cohort_apply_failed:{MAGMAW}") as error:
        _run(plan_path, monkeypatch, selected=[MAGMAW], facts=[anchored_facts(plan)], connection=connection)
    assert connection.events[-1] == "rollback"
    assert error.value.report["applied"]["committed"] == []


def test_readback_without_the_anchor_or_with_wrong_loadouts_is_refused(plan_path, monkeypatch):
    with pytest.raises(rsp.RaidShardProvisioningError, match="readback_refused"):
        _run(plan_path, monkeypatch, selected=[NEFARIAN], facts=[empty_facts(), empty_facts()])
    plan = json.loads(plan_path.read_text())
    with pytest.raises(rsp.RaidShardProvisioningError, match="loadout_readback_failed"):
        _run(plan_path, monkeypatch, selected=[MAGMAW], facts=[anchored_facts(plan)], readback_passed=False)


def test_unrecorded_or_unknown_plans_are_refused(plan_path, monkeypatch, tmp_path):
    stale = json.loads(plan_path.read_text())
    stale["sources"] = {"composition": {"path": "x", "sha256": "0" * 64}}
    stale_path = tmp_path / "stale.json"
    stale_path.write_text(json.dumps(stale))
    with pytest.raises(rsp.RaidShardProvisioningError, match="plan_source_unrecorded"):
        _run(stale_path, monkeypatch, selected=[MAGMAW], facts=[empty_facts()])
    with pytest.raises(rsp.RaidShardProvisioningError, match="unknown_plan_cohorts"):
        _run(plan_path, monkeypatch, selected=["blackwing_descent_10n_magmaw_c1_diagnostic"], facts=[empty_facts()])
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"schema": "raid_shard_run_plan_v1", "shards": []}))
    with pytest.raises(rsp.RaidShardProvisioningError, match="source_plan_schema"):
        rsp.load_source_plan(other)


def test_prepare_only_checks_without_writing(plan_path, monkeypatch):
    report, calls, connection = _run(plan_path, monkeypatch, selected=[NEFARIAN], facts=[empty_facts()], apply=False)
    assert report["passed"] and report["applied"] is None and calls["statements"] is None
    assert connection.events == []


@pytest.mark.skipif(not GEAR.is_file() or not (DBC / "Item-sparse.db2").is_file(),
                    reason="DVC gear profiles or client DBCs not hydrated")
def test_loadout_readback_compares_every_group_and_bag(plan_path):
    from tools.bot_ml.build_validation_provisioning import gem_item_enchant_map
    from tools.raid_program.raid_loadout import (
        expected_glyph_rows, expected_inventory, expected_talent_rows, expected_talent_tree)
    from tools.raid_program.raid_loadout_sql import prepare_config

    plan = json.loads(plan_path.read_text())
    config = prepare_config(plan, GEAR, DBC, [MAGMAW])
    gems = gem_item_enchant_map(DBC)
    observed = {}
    for bot in config["scenarios"][0]["bots"]:
        loadout = bot["loadout"]
        observed[bot["name"]] = {
            "guid": bot["expected_character_guid"], "talent_groups_count": loadout["talent_groups_count"],
            "active_talent_group": loadout["active_talent_group"], "talent_tree": expected_talent_tree(bot),
            "talents": expected_talent_rows(bot), "glyphs": expected_glyph_rows(bot),
            "known_spells": loadout["known_spell_ids"] + loadout["dual_spec_switch_spell_ids"],
            "inventory": [{**row, "owner_guid": bot["expected_character_guid"]}
                          for row in expected_inventory(bot, config.get("default_consumables", []), gems, DBC)]}
    trainers = ROOT / "dataset/world_knowledge/trainers.jsonl"
    result = rsp._loadout_readback(plan, [MAGMAW], CHARACTERS, GEAR, DBC, trainers, lambda url, names: observed)
    assert result == {"characters": 10, "failures": [], "passed": True}
    druid = next(bot for bot in config["scenarios"][0]["bots"] if bot["character_key"] == "druid")
    observed[druid["name"]]["active_talent_group"] = 1 - druid["loadout"]["active_talent_group"]
    observed[druid["name"]]["inventory"] = [row for row in observed[druid["name"]]["inventory"] if row["bag"] == 0]
    result = rsp._loadout_readback(plan, [MAGMAW], CHARACTERS, GEAR, DBC, trainers, lambda url, names: observed)
    assert {row["check"] for row in result["failures"]} >= {"loadout_active_talent_group", "loadout_inventory_missing"}
    assert result["passed"] is False


def test_run_plan_identity_drift_is_named():
    shard = next(row for row in _plan()["shards"] if row["scenario_id"] == MALORIAK)
    base = dict(cohort_id=shard["cohort_id"], profile=MALORIAK, scenario_id=MALORIAK, pool_tag=MALORIAK,
                boss_key="maloriak", precompleted=["omnotron", "magmaw"])
    assert rsp.run_shard_identity_failures(shard, **base) == []
    assert rsp.run_shard_identity_failures(shard, **{**base, "precompleted": None}) == [
        "lockout_fresh_but_plan_has_predecessors"]
    assert rsp.run_shard_identity_failures(shard, **{**base, "precompleted": ["magmaw"]}) == [
        "lockout_precompleted_boss_keys"]
    assert rsp.run_shard_identity_failures(shard, **{**base, "profile": "blackwing_descent_10n_maloriak_diagnostic"}) == [
        "runtime_profile_id"]
