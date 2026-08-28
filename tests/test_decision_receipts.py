from __future__ import annotations

import json

import tools.bot_ml.run_live_bot_validation as validation


def _movement_row(
    *,
    timestamp_ms: int,
    intent_reason: str = "pincer_preposition",
    actor_guid: int = 30006,
) -> dict:
    return {
        "timestamp_ms": timestamp_ms,
        "bot_guid": actor_guid,
        "route_generation": 4,
        "route_node_id": "bwd.magmaw.encounter",
        "movement_planner": {
            "intent_reason": intent_reason,
            "gate": "native_path_submission",
            "result": "submitted",
            "reason": "native_movement_submitted",
        },
    }


def _report(entries: list[dict]) -> dict:
    return {
        "schema": "bot_live_validation_report_v1",
        "trace": {"trace_schema_version": 1, "entries": entries},
        "diagnosis": {},
        "failure_labels": [],
        "progress_counters": {},
        "completion_reason": "running",
    }


def _rolling(output_dir, heartbeat_index: int) -> dict:
    return validation.rolling_heartbeat_report(
        output_dir,
        heartbeat_index,
        "",
        0,
        False,
        [],
        {},
        {},
        "completion-watchdog",
        30,
        180,
        20,
        3,
    )


def test_earlier_movement_intent_survives_later_snapshot_without_it(
    tmp_path, monkeypatch
):
    reports = [
        _report([_movement_row(timestamp_ms=1000)]),
        _report([_movement_row(timestamp_ms=2000, intent_reason="")]),
    ]
    monkeypatch.setattr(validation, "live_validation_report", lambda *args, **kwargs: reports.pop(0))

    _rolling(tmp_path, 1)
    final = _rolling(tmp_path, 2)

    receipts = final["decision_receipts"]
    assert receipts == [
        {
            "actor_guid": 30006,
            "count": 1,
            "first_timestamp_ms": 1000,
            "gate": "native_path_submission",
            "last_timestamp_ms": 1000,
            "outcome_reason": "native_movement_submitted",
            "reason": "pincer_preposition",
            "reason_type": "movement_intent",
            "result": "submitted",
            "route_generation": 4,
            "route_node_id": "bwd.magmaw.encounter",
        }
    ]
    assert json.loads((tmp_path / "report.json").read_text())["decision_receipts"] == receipts
    assert validation.compact_published_report(final)["decision_receipts"] == receipts
    stream = [json.loads(line) for line in (tmp_path / "heartbeat_events.jsonl").read_text().splitlines()]
    assert len(stream[0]["decision_receipts"]) == 1
    assert "decision_receipts" not in stream[1]
    assert "snapshot" not in json.dumps(stream)


def test_duplicate_movement_intents_aggregate_across_heartbeat_deltas(
    tmp_path, monkeypatch
):
    reports = [
        _report([_movement_row(timestamp_ms=1000), _movement_row(timestamp_ms=1100)]),
        _report([_movement_row(timestamp_ms=2000)]),
    ]
    monkeypatch.setattr(validation, "live_validation_report", lambda *args, **kwargs: reports.pop(0))

    _rolling(tmp_path, 1)
    final = _rolling(tmp_path, 2)

    receipt = final["decision_receipts"][0]
    assert receipt["count"] == 3
    assert receipt["first_timestamp_ms"] == 1000
    assert receipt["last_timestamp_ms"] == 2000
    stream = [json.loads(line) for line in (tmp_path / "heartbeat_events.jsonl").read_text().splitlines()]
    assert stream[0]["decision_receipts"][0]["count"] == 2
    assert stream[1]["decision_receipts"][0]["count"] == 1


def test_movement_receipts_have_a_hard_cardinality_bound():
    report = _report(
        [
            _movement_row(
                timestamp_ms=index + 1,
                intent_reason=f"typed_intent_{index}",
                actor_guid=30000 + index,
            )
            for index in range(validation.DECISION_RECEIPT_LIMIT + 8)
        ]
    )

    receipts = validation.compact_decision_receipts(report)

    assert len(receipts) == validation.DECISION_RECEIPT_LIMIT
