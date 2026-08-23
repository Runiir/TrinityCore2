from __future__ import annotations

import inspect
from pathlib import Path
import sys

import pytest
import tools.bot_ml.calibration_consumable_provisioning as provisioning
import tools.bot_ml.run_live_bot_validation as live_validation


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"


class _Cursor:
    def __init__(self, rows: list[list[dict]], *, one: dict | None = None) -> None:
        self.rows = rows
        self.one = one
        self.calls: list[tuple[str, tuple]] = []

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: tuple = ()) -> None:
        self.calls.append((query, params))

    def fetchall(self) -> list[dict]:
        return self.rows.pop(0) if self.rows else []

    def fetchone(self) -> dict:
        return self.one or {}


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_value = cursor

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> _Cursor:
        return self.cursor_value

    def close(self) -> None:
        return None


def test_contract_uses_target_profile_and_two_potion_uses() -> None:
    contract = provisioning.load_calibration_consumable_contract(
        "affliction_warlock", TARGETS
    )

    assert contract["character_name"] == "Afflock"
    assert contract["class_spec"] == "affliction_warlock"
    assert contract["required_uses"] == {
        "flask": 1,
        "food": 1,
        "prepot": 1,
        "combat_potion": 1,
    }
    assert contract["inventory"] == [
        {"slot": 26, "item_id": 58086, "count": 20},
        {"slot": 27, "item_id": 62671, "count": 20},
        {"slot": 28, "item_id": 58091, "count": 20},
    ]


def test_restock_sql_changes_only_ordinary_inventory_slots() -> None:
    contract = provisioning.load_calibration_consumable_contract(
        "affliction_warlock", TARGETS
    )
    sql = provisioning.build_calibration_consumable_restock_sql(
        "characters",
        42,
        contract["inventory"],
        [900, 901],
        [1000, 1001, 1002],
    )

    assert "START TRANSACTION;" in sql
    assert "slot` IN (26, 27, 28)" in sql
    assert "itemEntry`" in sql
    assert "VALUES (1000, 58086, 42" in sql
    assert "VALUES (1001, 62671, 42" in sql
    assert "VALUES (1002, 58091, 42" in sql
    assert "aura" not in sql.lower()
    assert "spell" not in sql.lower()


def test_inventory_readback_fails_closed_on_missing_or_wrong_stack() -> None:
    expected = [
        {"slot": 26, "item_id": 58086, "count": 20},
        {"slot": 27, "item_id": 62671, "count": 20},
        {"slot": 28, "item_id": 58091, "count": 20},
    ]
    mismatches = provisioning.calibration_consumable_inventory_mismatches(
        42,
        expected,
        {
            26: {"bag": 0, "slot": 26, "item_id": 58086, "owner_guid": 42, "count": 20},
            27: {"bag": 0, "slot": 27, "item_id": 62671, "owner_guid": 42, "count": 0},
        },
    )

    assert [row["slot"] for row in mismatches] == [27, 28]
    assert "count" in mismatches[0]["wrong_fields"]


def test_applied_restock_reads_back_before_calibration(tmp_path, monkeypatch) -> None:
    config = tmp_path / "worldserver.conf"
    config.write_text(
        'CharacterDatabaseInfo = "127.0.0.1;3306;user;password;characters"\n',
        encoding="utf-8",
    )
    before = _Cursor(
        [[
            {"guid": 42, "name": "Afflock", "class_spec": "affliction_warlock", "experiment_tags": "all_spec_candidate_pool", "enabled": 1, "in_use": 0},
        ], [
            {"bag": 0, "slot": 26, "item": 900, "itemEntry": 58086, "owner_guid": 42, "count": 0},
            {"bag": 0, "slot": 27, "item": 901, "itemEntry": 62671, "owner_guid": 42, "count": 0},
        ]],
    )
    before.one = {"max_guid": 1000}
    after = _Cursor(
        [[
            {"bag": 0, "slot": 26, "item_id": 58086, "owner_guid": 42, "count": 20},
            {"bag": 0, "slot": 27, "item_id": 62671, "owner_guid": 42, "count": 20},
            {"bag": 0, "slot": 28, "item_id": 58091, "owner_guid": 42, "count": 20},
        ]]
    )
    connections = iter([_Connection(before), _Connection(after)])
    monkeypatch.setattr(live_validation, "connect_mysql", lambda _url: next(connections))
    executed: list[str] = []
    monkeypatch.setattr(
        live_validation,
        "execute_sql_text",
        lambda _url, sql: executed.append(sql) or 10,
    )

    report = live_validation.prepare_calibration_consumables(
        tmp_path,
        config,
        "affliction_warlock",
        TARGETS,
        apply=True,
    )

    assert report["readback"]["passed"] is True
    assert report["new_item_guids"] == [1001, 1002, 1003]
    assert len(executed) == 1


def test_self_provided_baseline_requires_per_attempt_pool_reset(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bot-live-validate",
            "--calibration-only",
            "--calibration-self-provided-baseline",
        ],
    )

    with pytest.raises(SystemExit, match="requires --reset-bot-pool"):
        live_validation.main()


def test_session_restock_runs_inactive_after_provisioning_before_start() -> None:
    source = inspect.getsource(live_validation.run_reusable_validation_session)

    inactive = source.index('lifecycle["inactive_before_preparation"] = True')
    provisioning = source.index('owner.provision_once(')
    reset = source.index('prepare_bot_pool_reset(', provisioning)
    restock = source.index('prepare_calibration_consumables(', reset)
    start = source.index('executor.start()', restock)

    assert inactive < provisioning < reset < restock < start
