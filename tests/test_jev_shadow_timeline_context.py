import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

from tools.bot_ml import jev_shadow as shadow
from tools.bot_ml.shadow_timeline_context import join_timeline_context
from tools.raid_program.bot_timeline import _report_source


def _write_json(path: Path, value: dict) -> None:
    path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _fixture_files(tmp_path: Path) -> dict[str, Path]:
    report = {
        "schema_version": 1,
        "capture_id": "synthetic-capture",
        "scenario_id": "synthetic-magmaw",
        "started_at_utc": "2026-09-19T00:00:00Z",
        "identity": {"clean": True, "dirty": False, "head": "source-head"},
        "binary_sha256": "binary-hash",
        "config_sha256": "config-hash",
        "runtime_profile": "synthetic-profile",
        "accepted_raid_runtime": {
            "server_epoch": 7,
            "attempt_id": 3,
            "wipe_generation": 0,
            "profile_generation": 1,
            "profile_content_hash": "profile-content",
            "map_id": 669,
            "instance_id": 2,
            "group_guid": 11,
            "expected_size": 2,
            "expected_difficulty": 0,
            "strategy_id": "synthetic",
            "roster": [{"guid": 101}, {"guid": 102}],
        },
        "development_run": {
            "accepted_boss_identity": {
                "route_generation": 1,
                "route_node_id": "synthetic.node",
                "target_entry": 41570,
            }
        },
        "raw_normalized_batch": {"sha256": "raw-hash", "row_count": 2},
        "runtime_profile_assets": {"route_sha256": "route-hash"},
        "evidence_demux": {"canonical_roster_sha256": "roster-hash"},
        "report_sha256": "declared-canonical-report-digest",
    }
    report_path = tmp_path / "native-report.json"
    _write_json(report_path, report)
    report_file_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
    projection, projection_sha = _report_source(report)

    summary = {
        "schema": "cata_raid_bot_timeline_summary_v1",
        "clear_accepted": True,
        "identity": {
            "server_epoch": 7,
            "attempt_id": 3,
            "source": {
                "report_source": projection,
                "report_source_sha256": projection_sha,
            },
        },
        "window": {
            "complete": True,
            "basis": "native_trace_boss_death",
            "first_hostile_at_ms": 1000,
            "native_boss_death_at_ms": 4000,
            "elapsed_seconds": 3.0,
        },
        "actors": {
            "101": {
                "actor_guid": 101,
                "role": "dps",
                "class_spec": "survival_hunter",
                "damage": {
                    "hostile_originated": 1000,
                    "owned_source": 250,
                    "dps": 333.333333,
                },
                "effective_healing_through_death": 30,
                "native_elapsed_hps_through_death": 10,
                "activity": {
                    "active_seconds": 2,
                    "fresh_attack_active_seconds": 1,
                    "longest_fresh_attack_outage_ms": 500,
                    "metric_scope": "damage",
                },
                "survival": {
                    "alive_at_end": True,
                    "death_observed": False,
                    "scope": "synthetic-window",
                },
            },
            "102": {
                "actor_guid": 102,
                "role": "healer",
                "class_spec": "restoration_druid",
                "damage": {
                    "hostile_originated": 0,
                    "owned_source": 0,
                    # Deliberately omitted: missing is not a zero DPS value.
                },
                "effective_healing_through_death": 500,
                "native_elapsed_hps_through_death": 166.666667,
                "activity": {
                    "active_seconds": 3,
                    "metric_scope": "healing",
                },
                "survival": {
                    "alive_at_end": False,
                    "death_observed": True,
                    "death_observed_at_ms": 3900,
                    "scope": "synthetic-window",
                },
            },
        },
    }
    summary_path = tmp_path / "timeline-summary.json"
    _write_json(summary_path, summary)

    review = {
        "run_id": "synthetic-run",
        "source_sha256": report_file_sha,
        "jev_input": {
            "state": {
                "run_id": "synthetic-run",
                "segment_id": "magmaw:0",
                "boss_dps_review": {
                    "actor_identity": [
                        {
                            "bot_guid": 101,
                            "bot_name": "Dps-101",
                            "role": "dps",
                            "class_spec": "survival_hunter",
                        },
                        {
                            "bot_guid": 102,
                            "bot_name": "Healer-102",
                            "role": "healer",
                            "class_spec": "restoration_druid",
                        },
                    ],
                    "actor_loss_signals": [
                        {
                            "bot_guid": 101,
                            "class_spec": "survival_hunter",
                            "counterfactual_status": "eligible",
                            "timeline_signal": {
                                "dps_comparison_status": "stale-ledger-value",
                            },
                        }
                    ],
                },
            }
        },
    }
    review_path = tmp_path / "review.json"
    _write_json(review_path, review)

    identity = {
        "run_id": "synthetic-run",
        "server_epoch": 7,
        "attempt_id": 3,
        "source_commit": "source-head",
        "binary_sha256": "binary-hash",
        "config_sha256": "config-hash",
        "route_sha256": "route-hash",
        "roster_sha256": "roster-hash",
        "report_sha256": "declared-canonical-report-digest",
        "closed": True,
    }
    identity_path = tmp_path / "identity.json"
    _write_json(identity_path, identity)
    backend_path = tmp_path / "backend.json"
    _write_json(backend_path, {"provider": "test", "requested_model": "test-model"})
    return {
        "report": report_path,
        "summary": summary_path,
        "review": review_path,
        "identity": identity_path,
        "backend": backend_path,
    }


def _run_prepare(files: dict[str, Path], output: Path, monkeypatch, *, backend: str,
                 paired: bool = True) -> dict:
    argv = [
        "shadow",
        "--review", str(files["review"]),
        "--identity", str(files["identity"]),
        "--backend-receipt", str(files["backend"]),
        "--output", str(output),
        "--backend", backend,
        "--prepare-only",
    ]
    if paired:
        argv.extend(("--native-report", str(files["report"]),
                     "--timeline-summary", str(files["summary"])))
    monkeypatch.setattr(sys, "argv", argv)
    assert shadow.main() == 0
    return json.loads((output / "examples.jsonl").read_text().splitlines()[0])


def test_prepare_only_joins_same_bounded_projection_for_local_and_hosted(tmp_path, monkeypatch):
    files = _fixture_files(tmp_path)
    local = _run_prepare(files, tmp_path / "local", monkeypatch, backend="local")
    hosted = _run_prepare(files, tmp_path / "hosted", monkeypatch, backend="hosted")
    local_packet = json.loads(local["request_json"])
    hosted_packet = json.loads(hosted["request_json"])
    assert local_packet["state"] == hosted_packet["state"]

    dps = local_packet["state"]["actor_review"]
    assert dps["actor_identity"]["bot_guid"] == 101
    assert dps["native_metrics"]["dps"] == pytest.approx(333.333333)
    assert dps["native_metrics"]["damage"]["hostile"] == 1000
    assert dps["native_metrics"]["damage"]["owner"] == 750
    assert dps["native_metrics"]["damage"]["owned"] == 250
    assert "timeline_context" not in dps
    assert "owner_pet" not in dps
    assert dps["comparison"]["dps_comparison_status"] == "stale-ledger-value"

    # The second packet is role scoped and retains zero owned damage while its
    # omitted DPS is explicitly unknown.  Healing activity cannot become DPS
    # activity merely because the actor is a healer.
    rows = [json.loads(row) for row in (tmp_path / "local" / "examples.jsonl").read_text().splitlines()]
    healer = next(json.loads(row["request_json"]) for row in rows
                  if row["actor_guid"] == 102)["state"]["actor_review"]
    assert healer["native_metrics"]["damage"]["hostile"] == 0
    assert healer["native_metrics"]["dps"] == "unknown:death_window_dps_missing"
    assert healer["native_metrics"]["basis"] == "native_death_window"
    assert healer["native_metrics"]["activity"] == "unknown:healer_damage_activity_proxy_forbidden"
    assert healer["native_metrics"]["damage"]["owned"] == 0
    assert "overheal" in healer["native_metrics"]["unknown"]
    assert local["timeline_provenance"]["native_report_sha256"] != local["timeline_provenance"]["declared_report_sha256"]
    assert local["timeline_provenance"]["report_source_sha256"] != local["timeline_provenance"]["native_report_sha256"]
    assert local["action_authorized"] is False
    assert "provenance" not in local_packet["state"]
    assert "native_report_sha256" not in json.dumps(local_packet["state"])


@pytest.mark.parametrize("mutator,expected", [
    (lambda identity, review, summary: identity.update(server_epoch=8),
     "identity_server_epoch_mismatch"),
    (lambda identity, review, summary: identity.update(attempt_id=4),
     "identity_attempt_id_mismatch"),
    (lambda identity, review, summary: review.update(source_sha256="f" * 64),
     "review_source_sha256_mismatch_native_report_file"),
    (lambda identity, review, summary: summary["actors"].pop("102"),
     "timeline_summary_actor_guid_binding_mismatch"),
])
def test_stale_or_mismatched_inputs_reject_before_packet_join(
    tmp_path, mutator, expected
):
    files = _fixture_files(tmp_path)
    identity = json.loads(files["identity"].read_text())
    review = json.loads(files["review"].read_text())
    summary = json.loads(files["summary"].read_text())
    mutator(identity, review, summary)
    _write_json(files["identity"], identity)
    _write_json(files["review"], review)
    _write_json(files["summary"], summary)
    with pytest.raises(ValueError, match=expected):
        join_timeline_context(
            review,
            native_report=files["report"],
            timeline_summary=files["summary"],
            supplied_identity=identity,
        )


def test_invalid_cli_rejects_before_hosted_key_or_api(tmp_path, monkeypatch):
    files = _fixture_files(tmp_path)
    identity = json.loads(files["identity"].read_text())
    identity["attempt_id"] = 999
    _write_json(files["identity"], identity)
    monkeypatch.setattr(shadow.analyzer, "_jev_key", lambda *_: pytest.fail("key loaded"))
    monkeypatch.setattr(shadow.analyzer, "_call_jev", lambda *_: pytest.fail("API called"))
    monkeypatch.setattr(sys, "argv", [
        "shadow", "--review", str(files["review"]), "--identity", str(files["identity"]),
        "--backend-receipt", str(files["backend"]), "--output", str(tmp_path / "out"),
        "--backend", "hosted", "--native-report", str(files["report"]),
        "--timeline-summary", str(files["summary"]),
    ])
    with pytest.raises(SystemExit):
        shadow.main()


def test_absent_inputs_are_explicitly_unknown(tmp_path, monkeypatch):
    files = _fixture_files(tmp_path)
    row = _run_prepare(files, tmp_path / "unknown", monkeypatch, backend="local", paired=False)
    packet = json.loads(row["request_json"])
    actor = packet["state"]["actor_review"]
    assert actor["native_metrics"]["status"] == "unknown"
    assert row["timeline_provenance"] == {
        "schema": "shadow_timeline_context_v1",
        "status": "unknown",
        "reason": "native_report_and_timeline_summary_not_supplied",
    }


def test_partial_summary_keeps_missing_hps_unknown(tmp_path, monkeypatch):
    files = _fixture_files(tmp_path)
    summary = json.loads(files["summary"].read_text())
    summary["actors"]["102"].pop("native_elapsed_hps_through_death")
    _write_json(files["summary"], summary)
    row = _run_prepare(files, tmp_path / "partial", monkeypatch, backend="local")
    rows = [json.loads(value) for value in (tmp_path / "partial" / "examples.jsonl").read_text().splitlines()]
    healer = next(json.loads(value["request_json"]) for value in rows if value["actor_guid"] == 102)
    assert healer["state"]["actor_review"]["native_metrics"]["hps"] == "unknown:native_elapsed_hps_through_death_missing"


def test_unknown_shadow_context_never_promotes_legacy_native_values(tmp_path):
    files = _fixture_files(tmp_path)
    review = json.loads(files["review"].read_text())
    review["jev_input"]["state"]["boss_dps_review"]["timeline_comparison"] = {
        "actors": [{
            "bot_guid": 101,
            "damage": {"total_hostile_originated": 9999},
            "activity": {"active_seconds": 999},
        }]
    }
    identity = json.loads(files["identity"].read_text())
    joined, provenance = join_timeline_context(
        review,
        native_report=None,
        timeline_summary=None,
        supplied_identity=identity,
    )
    packet = shadow.laya_packets.actor_packets(joined)[0]
    actor = packet["state"]["actor_review"]
    assert provenance["status"] == "unknown"
    assert actor["native_metrics"]["status"] == "unknown"
    assert "9999" not in json.dumps(actor["native_metrics"])
    assert actor["comparison"]["dps_comparison_status"] == "stale-ledger-value"
