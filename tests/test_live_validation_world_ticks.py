"""The harness merges native world-tick rows from every status read."""
from __future__ import annotations

import json
from copy import deepcopy

from tools.bot_ml import run_live_bot_validation as live
from tools.bot_ml.live_validation_world_ticks import (
    WORLD_TICK_LEDGER_FILE,
    WorldTickLedger,
    load_world_tick_ledger,
)

MANIFEST = {"routes": [
    {"route_node_id": "trash", "route_generation": 1, "kind": "trash"},
    {"route_node_id": "boss", "route_generation": 2, "kind": "boss"},
]}


def world_update(stall_count: int, *, capacity: int = 2, now_ms: int = 5_000) -> dict:
    rows = [
        {"sequence": sequence, "at_ms": 1_000 * sequence, "diff_ms": 500 + sequence}
        for sequence in range(1, stall_count + 1)
    ][-capacity:]
    return {
        "schema": "bot_world_update_ticks_v1",
        "now_ms": now_ms,
        "threshold_ms": 500,
        "capacity": capacity,
        "update_count": 100 + stall_count,
        "first_update_at_ms": 10,
        "max_diff_ms": 500 + stall_count,
        "max_diff_at_ms": 1_000 * stall_count,
        "stall_count": stall_count,
        "dropped_count": max(0, stall_count - capacity),
        "stalls": rows,
    }


def test_ledger_merges_rings_by_sequence_and_reports_lost_rows():
    ledger = WorldTickLedger()
    assert ledger.observe(world_update(2, now_ms=3_000))
    assert ledger.observe(world_update(4, now_ms=6_000))  # rows 1-2 left the ring
    assert not ledger.observe({"unrelated": True})
    snapshot = ledger.snapshot()
    assert [row["sequence"] for row in snapshot["stalls"]] == [1, 2, 3, 4]
    assert snapshot["missing_sequences"] == []
    assert snapshot["reads"] == 2 and snapshot["now_ms"] == 6_000
    # An older snapshot never rolls the latest counters back.
    ledger.observe(world_update(1, now_ms=2_000))
    assert ledger.snapshot()["stall_count"] == 4
    skipped = WorldTickLedger()
    skipped.observe(world_update(5, now_ms=9_000))
    assert skipped.snapshot()["missing_sequences"] == [1, 2, 3]


def status_payload(stall_count: int, now_ms: int) -> dict:
    return {
        "ok": True,
        "action": "botauto_status",
        "active": True,
        "bots": 10,
        "active_bots": 10,
        "target_bots": 10,
        "lease_count": 10,
        "kills": 2,
        "decisions": 3,
        "validation_route": {
            "kind": "boss", "node_id": "boss", "generation": 2, "manifest_complete": True,
            "terminal_evidence": [
                {"route_node_id": "trash", "route_generation": 1},
                {"route_node_id": "boss", "route_generation": 2},
            ],
            "boss_death_evidence": [{"route_node_id": "boss", "route_generation": 2, "result": "ok", "target_id": 39}],
        },
        "world_update": world_update(stall_count, now_ms=now_ms),
    }


def test_transport_reads_world_ticks_each_heartbeat_and_at_cleanup(tmp_path):
    commands: list[str] = []
    status_reads = {"count": 0}

    def execute(command: str, _timeout: int):
        commands.append(command)
        if command.startswith(".botauto status"):
            status_reads["count"] += 1
            return json.dumps(status_payload(2 * status_reads["count"], 1_000 * status_reads["count"])), 0, False
        if command.startswith(".botauto combatlog"):
            return '{"ok":true,"action":"botauto_combatlog_complete","chunk_count":0}', 0, False
        return json.dumps({"ok": True, "action": "other"}), 0, False

    script = live.command_script(start=False, stop=True, exit_server=False, trace_delta=True, trace_limit=128)
    live.run_transport_completion_watchdog(
        execute, ["SOAP"], 30, script, tmp_path, {}, {},
        validation_route_manifest=deepcopy(MANIFEST), heartbeat_sec=1,
        sleep=lambda _seconds: None,
    )
    # One heartbeat status (the clear), then one cleanup status read before
    # the export and the stop.
    assert commands.count(".botauto status") == 2
    assert commands.index(".botauto status", 1) < commands.index(".botauto combatlog")
    ledger = json.loads((tmp_path / WORLD_TICK_LEDGER_FILE).read_text(encoding="utf-8"))
    assert ledger["reads"] == 2
    assert [row["sequence"] for row in ledger["stalls"]] == [1, 2, 3, 4]
    assert ledger["missing_sequences"] == []
    timings = [json.loads(line) for line in (tmp_path / "heartbeat_command_timings.jsonl").read_text().splitlines()]
    assert [row["phase"] for row in timings if row["command"] == ".botauto status"] == ["heartbeat", "cleanup_status"]


FAKE_WORLDSERVER = """#!/usr/bin/env python3
import json, sys
config = json.load(open(sys.argv[-1]))
reads = 0
print('TC> ', flush=True)
for line in sys.stdin:
    cmd = line.strip()
    if cmd.startswith('server shutdown'):
        break
    if cmd.startswith('.botauto status'):
        reads += 1
        payload = dict(config['status'])
        payload['world_update'] = dict(config['world_update'], stall_count=reads, now_ms=1000 * reads,
            stalls=[{'sequence': reads, 'at_ms': 1000 * reads, 'diff_ms': 600}])
    elif cmd.startswith('.botauto combatlog'):
        payload = {'ok': True, 'action': 'botauto_combatlog_complete', 'chunk_count': 0}
    elif cmd.startswith('.botauto diagnose'):
        payload = {'ok': True, 'action': 'botauto_diagnose', 'diagnosis_schema_version': 1, 'bots': []}
    elif cmd.startswith('.botauto trace'):
        payload = {'ok': True, 'action': 'botauto_trace', 'trace_schema_version': 1, 'bots': []}
    else:
        payload = {'duration_minutes': 1, 'total_kills': 2}
    print(json.dumps(payload, separators=(',', ':')))
    print('TC> ', flush=True)
"""


def test_process_reads_world_ticks_each_heartbeat_and_at_cleanup(tmp_path):
    config = tmp_path / "fake.json"
    status = status_payload(0, 0)
    status.pop("world_update")
    config.write_text(json.dumps({"status": status, "world_update": world_update(0)}), encoding="utf-8")
    binary = tmp_path / "fake_worldserver.py"
    binary.write_text(FAKE_WORLDSERVER, encoding="utf-8")
    binary.chmod(0o755)
    output_dir = tmp_path / "run"
    live.run_worldserver_completion_watchdog(
        binary, config, 30,
        live.command_script(start=False, trace_delta=True, trace_limit=128),
        output_dir, {}, {}, heartbeat_sec=1, validation_route_manifest=deepcopy(MANIFEST),
    )
    ledger = load_world_tick_ledger(output_dir)
    assert ledger is not None
    # Each read returned only its own newest row; the ledger keeps both.
    assert ledger["reads"] == 2
    assert [row["sequence"] for row in ledger["stalls"]] == [1, 2]
    assert ledger["missing_sequences"] == []
