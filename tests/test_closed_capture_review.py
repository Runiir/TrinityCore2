from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest

from tools.bot_ml.closed_capture_inputs import load_canonical_capture
from tools.bot_ml import analyze_magmaw_trace as analyzer
from tools.raid_program.capture_finalization import normalized_batch_payload
from tools.raid_program.capture_runtime_identity import (
    _roster_binding_identity,
    _runtime_identity,
)
from tools.raid_program.capture_value_types import _canonical_object_sha256


def _runtime() -> dict:
    roster = []
    members = []
    for slot in range(10):
        guid = 30000 + slot
        role = "tank" if slot == 0 else ("healer" if slot < 3 else "dps")
        class_spec = "blood_death_knight" if slot == 0 else f"spec_{slot}"
        roster.append({
            "roster_slot_id": f"slot_{slot}",
            "lease_role_slot": f"slot_{slot}",
            "slot": slot,
            "guid": guid,
            "subgroup": slot // 5,
            "role": role,
            "class_id": 1 + slot,
            "class_spec": class_spec,
            "gear_identity": f"gear_{slot}",
            "active": True,
            "lease_owned": True,
            "account_id": 40000 + slot,
            "account": f"account_{slot}",
            "name": f"Bot{slot}",
            "talents": [],
            "glyphs": [],
            "gear_identity_manifest": {"items": []},
        })
        members.append({
            "guid": guid,
            "name": f"Bot{slot}",
            "role": role,
            "class_spec": class_spec,
            "class_id": 1 + slot,
        })
    return {
        "active": True,
        "group_guid": 77,
        "leader_guid": 30000,
        "expected_size": 10,
        "expected_difficulty": 0,
        "group_difficulty": 0,
        "map_difficulty": 0,
        "map_id": 669,
        "instance_id": 42,
        "lockout_save_id": 42,
        "server_epoch": 88,
        "attempt_id": 1,
        "profile_generation": 1,
        "profile_content_hash": "fixture-profile-sha256",
        "assignment_generation": 1,
        "strategy_id": "blackwing_descent_10n",
        "roster": roster,
        "admission_receipt": {
            "server_epoch": 88,
            "attempt_id": 1,
            "members": members,
        },
    }


def _combat_payload(*, include_foreign: bool) -> dict:
    def ability(guid: int, amount: int) -> dict:
        return {
            "route_generation": 1,
            "route_node_id": "bwd.magmaw.encounter",
            "route_label": "Magmaw",
            "perspective": "damage_done",
            "actor_guid": guid,
            "actor_name": "Bot0" if guid == 30000 else "Foreign",
            "actor_role": "dps",
            "actor_class_id": 8,
            "source_entry": 0,
            "source_name": "Bot0" if guid == 30000 else "Foreign",
            "source_is_pet": False,
            "spell_id": 133,
            "spell_name": "Fireball",
            "target_entry": 41570,
            "target_name": "Magmaw",
            "first_at_ms": 1000,
            "last_at_ms": 2000,
            "event_count": 3 if guid == 30000 else 9,
            "amount": amount,
            "originated_amount": amount,
            "moving_events": 0,
            "distance_avg": 10,
        }

    def bucket(guid: int, amount: int) -> dict:
        return {
            "route_generation": 1,
            "perspective": "damage_done",
            "actor_guid": guid,
            "source_is_pet": False,
            "second": 1 if guid == 30000 else 2,
            "amount": amount,
            "originated_amount": amount,
        }

    def action_outcome(guid: int) -> dict:
        return {
            "route_generation": 1,
            "route_node_id": "bwd.magmaw.encounter",
            "actor_guid": guid,
            "actor_name": "Bot0" if guid == 30000 else "Foreign",
            "actor_role": "dps",
            "actor_class_id": 8,
            "phase": "combat",
            "action_type": "spell",
            "action_name": "Fireball",
            "spell_id": 133,
            "result": "cast",
            "count": 1,
        }

    def candidate_rejection(guid: int) -> dict:
        return {
            "route_generation": 1,
            "route_node_id": "bwd.magmaw.encounter",
            "actor_guid": guid,
            "actor_name": "Bot0" if guid == 30000 else "Foreign",
            "actor_role": "dps",
            "actor_class_id": 8,
            "phase": "combat",
            "spell_id": 133,
            "action_category": "builder",
            "reason": "max_range_exceeded",
            "count": 1,
        }

    foreign_rows = [
        ability(99999, 999999),
        bucket(99999, 999999),
        action_outcome(99999),
        candidate_rejection(99999),
        {
            "event_sequence": 2,
            "actor_guid": 99999,
            "source_guid": 99999,
            "kind": "damage",
            "amount": 999999,
        },
    ] if include_foreign else []
    return {
        "ok": True,
        "action": "botauto_combatlog",
        "combat_log_schema_version": 5,
        "damage_attribution_schema": "originated_amount_v2_friendly_split",
        "cohort_id": "default",
        "server_epoch": 88,
        "attempt_id": 1,
        "combat_log_epoch": 1,
        "profile_generation": 1,
        "profile_content_hash": "fixture-profile-sha256",
        "event_count": 12 if include_foreign else 3,
        "aggregate_count": 2 if include_foreign else 1,
        "second_bucket_count": 2 if include_foreign else 1,
        "recent_events_dropped": 0,
        "abilities": [ability(30000, 300), *([foreign_rows[0]] if include_foreign else [])],
        "second_buckets": [bucket(30000, 300), *([foreign_rows[1]] if include_foreign else [])],
        "action_outcomes": [action_outcome(30000), *([foreign_rows[2]] if include_foreign else [])],
        "candidate_rejections": [candidate_rejection(30000), *([foreign_rows[3]] if include_foreign else [])],
        "recent_events": [
            {
                "event_sequence": 1,
                "actor_guid": 30000,
                "source_guid": 30000,
                "kind": "damage",
                "amount": 300,
            },
            *([foreign_rows[4]] if include_foreign else []),
        ],
        "failure_reason": None,
    }


def _combat_transport_payloads(payload: dict) -> list[dict]:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return [
        {
            "ok": True,
            "action": "botauto_combatlog_chunk",
            "cohort_id": "default",
            "combat_log_chunk_schema_version": 1,
            "sequence": 0,
            "chunk_count": 1,
            "encoding": "base64",
            "data": base64.b64encode(raw).decode(),
        },
        {
            "ok": True,
            "action": "botauto_combatlog_complete",
            "cohort_id": "default",
            "combat_log_chunk_schema_version": 1,
            "chunk_count": 1,
            "total_bytes": len(raw),
        },
    ]


def _producer_rows(*, combat_payload: dict | None = None) -> tuple[list[dict], dict]:
    runtime = _runtime()
    payloads = [
        {
            "ok": True,
            "action": "botauto_status",
            "cohort_id": "default",
            "bots": 10,
            "lease_count": 10,
            "raid_runtime": runtime,
        },
        {
            "ok": True,
            "action": "botauto_diagnose",
            "cohort_id": "default",
            "raid_runtime": copy.deepcopy(runtime),
            "bots": [{"bot_guid": 30000 + slot} for slot in range(10)],
        },
        {
            "ok": True,
            "action": "botauto_trace",
            "cohort_id": "default",
            "raid_runtime": copy.deepcopy(runtime),
            "bots": [
                {
                    "bot_guid": 30000 + slot,
                    "entries": [],
                    "delta": True,
                    "gap": False,
                }
                for slot in range(10)
            ],
        },
    ]
    if combat_payload is not None:
        payloads.extend(_combat_transport_payloads(combat_payload))
    rows = normalized_batch_payload(
        b"".join(json.dumps(payload).encode() + b"\n" for payload in payloads),
        profile_name="blackwing_descent_10n",
    )
    return rows, runtime


def _report(tmp_path: Path, *, rows: list[dict], runtime: dict) -> dict:
    raw = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for row in rows
    )
    (tmp_path / "report.raw.jsonl").write_bytes(raw)
    roster_identity = _roster_binding_identity(runtime["roster"])
    assert roster_identity is not None
    runtime_identity = _runtime_identity(runtime, include_strategy=False)
    assert runtime_identity is not None
    canonical_hash = _canonical_object_sha256({
        "cohort_id": "default",
        "runtime_identity": runtime_identity,
        "roster_sha256": _canonical_object_sha256(roster_identity),
    })
    report = {
        "schema_version": 1,
        "capture_id": "cata_raid_phase1_test_v1",
        "accepted_raid_runtime": copy.deepcopy(runtime),
        "development_run": {"requested": True, "native_boss_death_accepted": True},
        "capture_success": False,
        "combat_analysis": {},
        "raw_normalized_batch": {
            "path": "/evicted/original/report.raw.jsonl",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "row_count": len(rows),
        },
        "evidence_demux": {
            "normalized_schema_version": 2,
            "retained_rows": len(rows),
            "bound_rows": len(rows),
            "rejected_rows": 0,
            "unchecked_rows": 0,
            "canonical_identity_sha256": canonical_hash,
            "gate_passed": True,
        },
        "artifact_inventory": [
            {
                "kind": "capture_report",
                "path": str(tmp_path / "report.json"),
                "sha256": None,
                "bytes": 0,
                "immutable": True,
            },
        ],
        "report_sha256": None,
    }
    for _ in range(8):
        encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        report["artifact_inventory"][0]["bytes"] = len(encoded)
        basis = copy.deepcopy(report)
        basis["report_sha256"] = None
        basis["artifact_inventory"][0]["sha256"] = None
        digest = hashlib.sha256(
            json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        report["report_sha256"] = digest
        report["artifact_inventory"][0]["sha256"] = digest
        final = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        if report["artifact_inventory"][0]["bytes"] == len(final):
            break
    (tmp_path / "report.json").write_bytes(final)
    return report


def _capture(tmp_path: Path, *, combat_payload: dict | None = None) -> tuple[dict, list[dict]]:
    rows, runtime = _producer_rows(combat_payload=combat_payload)
    return _report(tmp_path, rows=rows, runtime=runtime), rows


def _rewrite_raw_and_report(tmp_path: Path, report: dict, rows: list[dict]) -> dict:
    return _report(tmp_path, rows=rows, runtime=report["accepted_raid_runtime"])


def test_canonical_review_joins_bound_raw_and_keeps_clear_separate(tmp_path):
    report, rows = _capture(tmp_path)
    inputs = load_canonical_capture(tmp_path, report)
    assert inputs["combat_log"] == {}
    assert len(inputs["payloads"]) == 3
    review = analyzer.analyze(
        tmp_path,
        env_file=tmp_path / "no-key",
        expected_route=(),
        run_id="canonical-test",
        segment_id="magmaw",
        change_id="test",
        change_note="",
        baseline_path=None,
        combat_analysis_path=None,
        prepare_only=True,
    )
    outcome = review["jev_input"]["state"]["native_gameplay_outcome"]
    assert outcome["native_clear"] is True
    assert outcome["capture_success"] is False
    assert outcome["certification_status"] == "uncertified"
    assert analyzer._actor_identity([report, *inputs["payloads"]])["30000"]["class_spec"] == "blood_death_knight"


def test_canonical_review_ignores_hostile_sibling_derived_artifacts(tmp_path):
    report, _ = _capture(tmp_path)
    kwargs = {
        "env_file": tmp_path / "no-key",
        "expected_route": (),
        "run_id": "canonical-precedence-test",
        "segment_id": "magmaw",
        "change_id": "test",
        "change_note": "",
        "baseline_path": None,
        "combat_analysis_path": None,
        "prepare_only": True,
    }
    baseline = analyzer.analyze(tmp_path, **kwargs)
    (tmp_path / "combat_analysis.json").write_text(json.dumps({
        "encounters": [{
            "route_node_id": "bwd.magmaw.encounter",
            "party_dps": 999999999,
            "actors": [{"actor_guid": 99999, "actor_role": "dps", "damage": 999999999}],
        }],
        "diagnostics": [{"actor_guid": 99999, "amount": 999999999}],
    }))
    (tmp_path / "combat_log.json").write_text(json.dumps({
        "recent_events": [{
            "kind": "damage", "actor_guid": 99999,
            "target_entry": 41570, "originated_amount": 999999999,
        }],
        "event_count": 1,
    }))
    sibling_ignored = analyzer.analyze(tmp_path, **kwargs)
    assert sibling_ignored == baseline
    with pytest.raises(ValueError, match="explicit overrides"):
        analyzer.analyze(
            tmp_path,
            **{**kwargs, "combat_analysis_path": tmp_path / "combat_analysis.json"},
        )


@pytest.mark.parametrize("mutation", ["action", "schema", "sequence"])
def test_canonical_capture_rejects_invalid_producer_wrapper(tmp_path, mutation):
    report, rows = _capture(tmp_path)
    broken = copy.deepcopy(rows)
    if mutation == "action":
        broken[1]["action"] = "botauto_trace"
    elif mutation == "schema":
        broken[1]["normalized_schema_version"] = 1
    else:
        broken[1]["capture_sequence"] = 4
    _rewrite_raw_and_report(tmp_path, report, broken)
    with pytest.raises(ValueError):
        load_canonical_capture(tmp_path, json.loads((tmp_path / "report.json").read_text()))


def test_canonical_capture_rejects_stale_raw(tmp_path):
    report, _ = _capture(tmp_path)
    (tmp_path / "report.raw.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_canonical_capture(tmp_path, report)


def test_canonical_capture_rejects_tampered_report(tmp_path):
    report, _ = _capture(tmp_path)
    report["accepted_raid_runtime"]["attempt_id"] = 99
    with pytest.raises(ValueError, match="self-hash"):
        load_canonical_capture(tmp_path, report)


def test_rejected_actor_binding_and_foreign_actor_cannot_change_trace_identity(tmp_path):
    report, rows = _capture(tmp_path)
    broken = copy.deepcopy(rows)
    rejected = broken[2]["payload"]["bots"][0]
    rejected["identity_binding"]["state"] = "rejected"
    foreign = broken[1]["payload"]["bots"][1]
    foreign["bot_guid"] = 99999
    _rewrite_raw_and_report(tmp_path, report, broken)
    loaded = load_canonical_capture(tmp_path, json.loads((tmp_path / "report.json").read_text()))
    trace = next(payload for payload in loaded["payloads"] if payload["action"] == "botauto_trace")
    assert {bot["bot_guid"] for bot in trace["bots"]} == set(range(30001, 30010))
    assert analyzer._actor_identity([report, *loaded["payloads"]]) == loaded["actor_identity"]


def test_foreign_actor_rows_cannot_change_canonical_combat_metrics(tmp_path):
    trusted_report, _ = _capture(
        tmp_path,
        combat_payload=_combat_payload(include_foreign=False),
    )
    trusted = load_canonical_capture(tmp_path, trusted_report)
    trusted_analysis = trusted["combat_analysis"]
    trusted_log = trusted["combat_log"]

    foreign_report, _ = _capture(
        tmp_path,
        combat_payload=_combat_payload(include_foreign=True),
    )
    foreign = load_canonical_capture(tmp_path, foreign_report)
    filtered_log = foreign["combat_log"]
    filtered_analysis = foreign["combat_analysis"]

    assert filtered_analysis["encounters"] == trusted_analysis["encounters"]
    assert trusted_log["event_count"] == 3
    assert "event_count" not in filtered_log
    assert filtered_analysis["tracked_event_count"] is None
    assert filtered_analysis["recent_events_dropped"] is None
    assert filtered_analysis["event_counters_available"] is False
    assert filtered_log["aggregate_count"] == trusted_log["aggregate_count"] == 1
    assert filtered_log["second_bucket_count"] == trusted_log["second_bucket_count"] == 1
    for field in (
        "recent_events",
        "abilities",
        "second_buckets",
        "action_outcomes",
        "candidate_rejections",
    ):
        assert all(
            row.get("actor_guid") != 99999
            for row in filtered_log.get(field, [])
            if isinstance(row, dict)
        )
    encounter = filtered_analysis["encounters"][0]
    assert [actor["actor_guid"] for actor in encounter["actors"]] == [30000]
    assert encounter["party_damage"] == 300
    assert encounter["action_outcome_count"] == 1
    assert encounter["candidate_rejection_count"] == 1

    compacted = analyzer._compact_metrics(
        {
            "available": True,
            "party_damage": 999999,
            "party_dps": 999999,
            "combat_seconds": 1,
            "duration_sec": 1,
            "actors": [
                {"actor_guid": 30000, "damage": 300},
                {"actor_guid": 99999, "damage": 999999},
            ],
            "action_outcomes": _combat_payload(include_foreign=True)["action_outcomes"],
            "candidate_rejections": _combat_payload(include_foreign=True)["candidate_rejections"],
        },
        {"30000": {"role": "dps"}},
        authoritative_identity=True,
    )
    assert [actor["bot_guid"] for actor in compacted["actors"]] == [30000]
    assert compacted["party_damage"] == 300
    assert compacted["party_dps"] == 300
    assert compacted["action_outcome_count"] == 1
    assert compacted["candidate_rejection_count"] == 1


def test_missing_bound_active_status_makes_combat_unavailable(tmp_path):
    report, rows = _capture(tmp_path)
    broken = copy.deepcopy(rows)
    broken[0]["identity_binding"]["state"] = "rejected"
    _rewrite_raw_and_report(tmp_path, report, broken)
    loaded = load_canonical_capture(tmp_path, json.loads((tmp_path / "report.json").read_text()))
    assert loaded["combat_log"] == {}
    assert loaded["combat_analysis"] == {}


def test_native_mushroom_probe_packet_has_typed_radii(tmp_path):
    path = tmp_path / "native.log"
    path.write_text(
        "MagmawWildMushroomNative event=nearby_targets "
        "destination=1.000,2.000,3.000 probe_radius=12.000 "
        "native_radius=6.000 target_count=2\n"
    )
    row, = analyzer._native_mushroom_diagnostics(path)
    assert row["probe_radius"] == 12
    assert row["native_radius"] == 6
    packet = analyzer._compact_jev_native_mushroom_diagnostics([row])
    snapshot = packet["nearby_target_snapshots"][0]
    assert snapshot["probe_radius"] == 12
    assert snapshot["native_radius"] == 6
    assert "radius" not in snapshot


def test_canonical_compact_rates_use_active_duration_above_one_second():
    result = analyzer._compact_metrics(
        {"party_damage": 300, "party_dps": 30, "party_healing": 100,
         "party_hps": 10, "combat_duration_sec": 10, "duration_sec": 10,
         "actors": [{"actor_guid": 30000, "damage": 300, "healing": 100}]},
        {"30000": {"role": "dps"}}, authoritative_identity=True,
    )
    assert result["party_dps"] == 30
    assert result["party_hps"] == 10


def test_clean_combat_sequence_count_is_not_sum_of_ability_perspectives():
    from tools.bot_ml.closed_capture_inputs import _filter_combat_log
    payload = {"event_count": 3, "recent_events_dropped": 0,
               "recent_events": [
                   {"actor_guid": 30000, "event_sequence": 1, "kind": "damage"},
                   {"actor_guid": 30000, "event_sequence": 2, "kind": "melee_resolution"},
                   {"actor_guid": 30000, "event_sequence": 3, "kind": "melee_resolution"}],
               "abilities": [
                   {"actor_guid": 30000, "kind": "damage_done", "event_count": 1},
                   {"actor_guid": 30001, "kind": "damage_taken", "event_count": 1}]}
    filtered = _filter_combat_log(payload, {30000, 30001})
    assert filtered["event_count"] == 3
    assert filtered["recent_events_dropped"] == 0
    assert "actor_filter" not in filtered
