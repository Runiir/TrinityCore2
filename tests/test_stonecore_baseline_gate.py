from __future__ import annotations

import json
from pathlib import Path

from tools.bot_ml.bt_masked_ga_combined import stonecore_baseline_gate, stonecore_comparison
from tools.bot_ml.live_validation_session import (
    acceptance_facts_from_report,
    AGGREGATION_SCOPE_IDS,
    build_live_validation_standard_marker,
    canonical_sha256,
    evaluate_acceptance,
)


ROOT = Path(__file__).resolve().parents[1]
R12_REPORT = ROOT / "artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r12/report.json"
HISTORICAL_REPORT = ROOT / "artifacts/all_spec_program/phase9_serial_canaries_20260809_rerun173/phase9_serial_02_stonecore_phase9_006_6893daf98698/report.json"


def _scope(node_id: str, generation: int) -> dict[str, object]:
    return {"route_node_id": node_id, "route_generation": generation}


def _current_stonecore_report(
    *,
    route_count: int = 14,
    exact_specs: list[str] | None = None,
) -> dict[str, object]:
    routes = [
        {
            "scenario_id": "stonecore_5n",
            "route_node_id": f"node-{generation}",
            "route_generation": generation,
            "kind": "boss" if generation > route_count - 4 else "trash",
            "expected_bot_count": 5,
        }
        for generation in range(1, route_count + 1)
    ]
    terminal = [_scope(route["route_node_id"], route["route_generation"]) for route in routes]
    bosses = [row for row in routes if row["kind"] == "boss"]
    boss_evidence = [_scope(row["route_node_id"], row["route_generation"]) for row in bosses]
    exact_specs = exact_specs or ["feral_druid_tank", "disc", "fury", "mm", "ret"]
    exact_party_sha256 = canonical_sha256(exact_specs)
    report: dict[str, object] = {
        "schema": "bot_live_validation_report_v1",
        "command": ["current-controller", "--validation-scenario", "stonecore_5n"],
        "generated_at_unix": 1787500000,
        "returncode": 0,
        "timed_out": False,
        "completion_reason": "validation_route_manifest_complete",
        "validation_context": {"scenario_id": "stonecore_5n"},
        "validation_route_manifest": {
            "schema": "bot_live_validation_route_manifest_v1",
            "scenario_id": "stonecore_5n",
            "route_count": route_count,
            "expected_segments": [f"{generation:02d}_segment" for generation in range(1, route_count + 1)],
            "routes": routes,
        },
        "stages": [{"stage": "full_stonecore_clear", "missing": []}],
        "evidence": {
            "manifest_completion_evidence": [terminal[-1]],
            "route_terminal_evidence": terminal,
            "real_boss_kill_evidence": boss_evidence,
            "boss_kill_evidence": 4,
            "deaths": 3,
            "forbidden_completion_assists": [],
            "failures": 0,
        },
        "watchdog_state": {
            "policy": "completion-watchdog",
            "death_loop": False,
            "repeated_decision_loop": False,
            "no_progress": False,
            "semantic_progress_plateau": False,
            "progress_counters": {"validation_route_manifest_complete": 1},
        },
        "evidence_envelope": {
            "schema": "bot_live_evidence_envelope_v1",
            "freshness": "current",
            "identity_complete": True,
            "identity_manifest_sha256": "a" * 64,
            "attempt_identity_sha256": "b" * 64,
            "aggregation_identity_sha256": "c" * 64,
            "component_hashes": {"binary_sha256": "d" * 64},
            "artifact_hashes": {"raw_artifact_sha256": "e" * 64},
            "scope_ids": {
                "batch_id": "stonecore-batch",
                "cohort_id": "stonecore-cohort",
                "composition_id": exact_party_sha256,
                "party_id": exact_party_sha256,
                "instance_id": "stonecore_5n",
                "attempt_id": "stonecore-attempt",
                "measurement_window_id": "observe:300:timeout:2100",
                "repeat_id": "full",
            },
            "superseded_by": None,
        },
        "session": {
                "schema": "bot_live_validation_session_v2",
                "profile": "stonecore_5n",
                "cohort_id": "stonecore-cohort",
                "exact_party_verified": True,
                "exact_party_class_specs": exact_specs,
                "exact_party_pool_tag": "stonecore_5n",
                "exact_party_sha256": exact_party_sha256,
            "binary_sha256": "1" * 64,
            "config_sha256": "2" * 64,
            "repository_fingerprint": "3" * 64,
            "input_sha256": "4" * 64,
            "git_head": "5" * 40,
            "inactive_after_attempt": True,
            "watchdog_completed": True,
            "server_process_identity_verified": True,
        },
    }
    report["live_validation_standard"] = build_live_validation_standard_marker(report, report["session"])
    report["evidence_envelope"]["live_validation_standard"] = report["live_validation_standard"]
    envelope = report["evidence_envelope"]
    compatibility_payload = {
        "component_hashes": envelope["component_hashes"],
        "scope_ids": {key: envelope["scope_ids"][key] for key in AGGREGATION_SCOPE_IDS},
        "live_validation_standard": report["live_validation_standard"],
    }
    envelope["aggregation_identity_sha256"] = canonical_sha256(compatibility_payload)
    envelope["attempt_identity_sha256"] = canonical_sha256(
        {
            **compatibility_payload,
            "scope_ids": envelope["scope_ids"],
            "artifact_hashes": envelope["artifact_hashes"],
            "live_validation_standard": report["live_validation_standard"],
            "freshness": envelope["freshness"],
            "superseded_by": envelope["superseded_by"],
        }
    )
    facts = acceptance_facts_from_report(report, identity_required=True, session_required=True)
    report["acceptance_facts"] = facts
    report["acceptance_verification"] = evaluate_acceptance(facts)
    report["acceptable_final_evidence"] = True
    return report


def test_materialized_stonecore_r12_cannot_be_used_as_an_accepted_baseline() -> None:
    report = (
        json.loads(R12_REPORT.read_text(encoding="utf-8"))
        if R12_REPORT.exists()
        else {
            "schema": "bot_live_validation_report_v1",
            "acceptable_final_evidence": True,
            "validation_context": {"scenario_id": "stonecore_5n"},
            "completion_reason": "validation_route_manifest_complete",
        }
    )
    gate = stonecore_baseline_gate(report)

    assert gate["accepted"] is False
    assert gate["functional_clear"] is False
    assert "missing_current_acceptance_facts" in gate["rejections"]
    assert "missing_current_evidence_envelope" in gate["rejections"]
    if R12_REPORT.exists():
        assert stonecore_comparison(R12_REPORT)["accepted_stonecore_baseline"] is False


def test_current_stonecore_baseline_requires_and_accepts_reconstructible_native_evidence() -> None:
    report = _current_stonecore_report()

    gate = stonecore_baseline_gate(report)

    assert gate["accepted"] is True
    assert gate["rejections"] == []
    assert all(gate["requirements"].values())


def test_historical_stonecore_clear_remains_behavioral_evidence_but_not_current_baseline() -> None:
    if HISTORICAL_REPORT.exists():
        report = json.loads(HISTORICAL_REPORT.read_text(encoding="utf-8"))
    else:
        report = _current_stonecore_report()
        report.pop("live_validation_standard", None)
        report["acceptance_facts"].pop("live_validation_standard", None)
        report["evidence_envelope"].pop("live_validation_standard", None)

    gate = stonecore_baseline_gate(report)

    assert gate["functional_clear"] is True
    assert gate["accepted"] is False
    assert "missing_live_validation_standard_marker" in gate["rejections"]
    if HISTORICAL_REPORT.exists():
        comparison = stonecore_comparison(HISTORICAL_REPORT)
        assert comparison["functional_stonecore_clear"] is True
        assert comparison["quality_accepted_stonecore_baseline"] is False


def test_functional_stonecore_clear_is_retained_when_role_quality_fails() -> None:
    # Mirrors the archived Phase 9 rerun93 canary-2 proof: 14/14 nodes, four
    # native boss kills, exact five-player roster, and advisory Feral quality
    # failures.  It must remain a functional clear without becoming promotable.
    report = _current_stonecore_report()
    report["completion_reason"] = "stonecore_role_quality_audit_failed"
    facts = report["acceptance_facts"]
    facts["role_quality_audit_failed"] = True
    facts["failure_labels"] = [
        "role_quality:Feraltank:threat_retention",
        "role_quality:Feraltank:healer_target_exposure",
        "role_quality:Feraltank:healer_target_dwell",
    ]
    report["acceptance_verification"] = evaluate_acceptance(facts)

    gate = stonecore_baseline_gate(report)

    assert gate["functional_clear"] is True
    assert gate["quality_accepted"] is False
    assert gate["accepted"] is False
    assert "stonecore_role_quality_audit_failed" in gate["quality_rejections"]


def test_historical_thirteen_node_clear_with_distinct_party_stays_functional_only() -> None:
    rerun93_party = _current_stonecore_report()["session"]["exact_party_class_specs"]
    report = _current_stonecore_report(
        route_count=13,
        exact_specs=["prot_paladin_tank", "holy_priest", "fire_mage", "mm_hunter", "enh_shaman"],
    )
    assert report["session"]["exact_party_class_specs"] != rerun93_party
    report.pop("live_validation_standard", None)
    report["acceptance_facts"].pop("live_validation_standard", None)
    report["evidence_envelope"].pop("live_validation_standard", None)

    gate = stonecore_baseline_gate(report)

    assert gate["functional_clear"] is True
    assert gate["quality_accepted"] is False
    assert gate["promotable"] is False
    assert "noncanonical_stonecore_route_manifest" in gate["quality_rejections"]
    assert "missing_live_validation_standard_marker" in gate["quality_rejections"]


def test_current_stonecore_baseline_rejects_route_only_completion() -> None:
    report = _current_stonecore_report()
    evidence = report["evidence"]
    evidence["real_boss_kill_evidence"] = []
    evidence["boss_kill_evidence"] = 0
    report["acceptance_facts"] = acceptance_facts_from_report(report, identity_required=True, session_required=True)
    report["acceptance_verification"] = evaluate_acceptance(report["acceptance_facts"])

    gate = stonecore_baseline_gate(report)

    assert gate["accepted"] is False
    assert "native_boss_kill_evidence_incomplete" in gate["rejections"]
