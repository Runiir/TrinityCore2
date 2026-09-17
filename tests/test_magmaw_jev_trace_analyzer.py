from __future__ import annotations

import json
from pathlib import Path

from tools.bot_ml import analyze_magmaw_trace as analyzer


def _entry(sequence: int, route: str, action: str, **extra: object) -> dict[str, object]:
    value: dict[str, object] = {
        "sequence": sequence,
        "timestamp_ms": sequence * 1000,
        "route_node_id": route,
        "situation": "validation_route",
        "action": action,
        "reason_code": "",
        "fingerprint_repeat_count": 0,
        "consecutive_same_decision_count": 0,
        "idle_decision_repeat_count": 0,
        "target_churn_count": 0,
        "loop_guardrail_action": "",
        "loop_guardrail_reason": "",
        "blocked_episode_id": 0,
        "recovery_mode": "",
    }
    value.update(extra)
    return value


def test_progress_summary_tracks_paths_stuck_behaviors_and_dps() -> None:
    entries = [
        {**_entry(1, "bwd.magmaw.chainwielder", "trash_action"), "_bot_guid": 10},
        {**_entry(2, "bwd.magmaw.drudges", "trash_action"), "_bot_guid": 10},
        {
            **_entry(
                3,
                "bwd.magmaw.encounter",
                "wait_for_candidate_backoff",
                fingerprint_repeat_count=22,
                consecutive_same_decision_count=11,
                target_churn_count=8,
                reason_code="decision_failure",
            ),
            "_bot_guid": 10,
        },
        {
            **_entry(4, "bwd.magmaw.encounter", "cast_combat_spell", encounter_path="magmaw.hook"),
            "_bot_guid": 10,
        },
    ]
    rows = [
        {
            "payload": {
                "action": "botauto_status",
                "kills": 0,
                "raid_runtime": {"route_progress": {"generation": 1, "node_index": 2}},
            }
        },
        {
            "payload": {
                "action": "botauto_diagnose",
                "bots": [
                    {
                        "diagnosis": {
                            "diagnosis_code": "repeated_decision_loop",
                            "magmaw_transfer_lane_intent_comparison": {"outcome": "Equivalent"},
                        }
                    }
                ],
            }
        },
        {"payload": {"action": "botauto_diagnose", "combat_metrics": {
            "available": True,
            "party_dps": 12345.0,
            "combat_seconds": 42,
            "actors": [{"bot_guid": 10, "role": "dps", "dps": 12345.0}],
        }}},
    ]

    summary = analyzer._progress_summary(
        entries,
        analyzer.DEFAULT_EXPECTED_ROUTE,
        rows,
    )

    assert summary["route_nodes_observed"] == [
        "bwd.magmaw.chainwielder",
        "bwd.magmaw.drudges",
        "bwd.magmaw.encounter",
    ]
    assert summary["route_status"] == "complete"
    assert summary["path_counts"]["magmaw.trash"] == 2
    assert summary["path_counts"]["magmaw.hook"] == 1
    assert summary["stuck_behavior_counts"]["repeated_decision_loop"] == 1
    assert summary["stuck_behavior_counts"]["target_churn_loop"] == 1
    assert summary["active_stuck_behavior_counts"]["repeated_decision_loop"] == 1
    assert summary["diagnosis_codes"]["repeated_decision_loop"] == 1
    assert summary["transfer_lane_outcomes"]["Equivalent"] == 1
    assert summary["latest_combat_metrics"]["party_dps"] == 12345.0


def test_progress_summary_can_scope_a_boss_out_of_a_combined_trace() -> None:
    entries = [
        {**_entry(1, "bwd.magmaw.encounter", "attack"), "_bot_guid": 10},
        {**_entry(2, "bwd.omnotron.encounter", "attack"), "_bot_guid": 10},
    ]
    rows = [
        {"payload": {"combat_metrics": {
            "available": True,
            "route_node_id": "bwd.magmaw.encounter",
            "party_dps": 100.0,
        }}},
        {"payload": {"combat_metrics": {
            "available": True,
            "route_node_id": "bwd.omnotron.encounter",
            "party_dps": 900.0,
        }}},
    ]

    summary = analyzer._progress_summary(
        entries,
        ("bwd.magmaw.encounter",),
        rows,
        scope_route_prefix="bwd.magmaw.encounter",
    )

    assert summary["route_nodes_observed"] == ["bwd.magmaw.encounter"]
    assert summary["latest_combat_metrics"]["party_dps"] == 100.0
    assert summary["scope_route_prefix"] == "bwd.magmaw.encounter"


def test_progress_summary_uses_route_generations_and_native_terminals() -> None:
    entries = [
        {
            **_entry(
                sequence,
                route,
                "trash_action" if route.endswith("drudges") else "attack",
                route_generation=generation,
            ),
            "_bot_guid": 10,
        }
        for sequence, (route, generation) in enumerate(
            [
                *[("bwd.magmaw.drudges", 3)] * 40,
                *[("bwd.magmaw.encounter", 4)] * 40,
            ],
            start=1,
        )
    ]
    entries[0]["fingerprint_repeat_count"] = 22
    rows = [
        {
            "payload": {
                "route_terminal_evidence": [
                    {"route_node_id": "bwd.magmaw.chainwielder", "route_generation": 2},
                    {"route_node_id": "bwd.magmaw.drudges", "route_generation": 3},
                    {"route_node_id": "bwd.magmaw.encounter", "route_generation": 4},
                ],
            }
        }
    ]

    summary = analyzer._progress_summary(
        entries,
        analyzer.DEFAULT_EXPECTED_ROUTE,
        rows,
    )

    assert summary["route_status"] == "complete"
    assert summary["route_missing_expected"] == []
    assert summary["route_repeated_nodes"] == []
    assert summary["route_terminal_nodes"] == [
        "bwd.magmaw.chainwielder",
        "bwd.magmaw.drudges",
        "bwd.magmaw.encounter",
    ]
    assert summary["route_terminal_generations"] == {
        "bwd.magmaw.chainwielder": 2,
        "bwd.magmaw.drudges": 3,
        "bwd.magmaw.encounter": 4,
    }
    assert summary["stuck_behavior_counts"]["repeated_decision_loop"] == 1
    assert summary["active_stuck_behavior_counts"] == {}
    assert summary["resolved_stuck_behavior_counts"]["repeated_decision_loop"] == 1


def test_analyze_requires_jev_and_records_typed_answers_and_ledger(
    tmp_path: Path, monkeypatch
) -> None:
    raw = tmp_path / "raw.jsonl"
    raw.write_text(
        json.dumps({
            "payload": {
                "action": "botauto_trace",
                "bots": [{
                    "bot_guid": 10,
                    "bot_name": "canary",
                    "entries": [_entry(1, "bwd.magmaw.encounter", "attack")],
                }],
            }
        }) + "\n",
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text("JEV=test-key\n", encoding="utf-8")
    ledger = tmp_path / "ledger.json"

    def fake_call(state: dict[str, object], key: str, questions: dict[str, object]) -> dict[str, object]:
        assert key == "test-key"
        assert state["authority"] == "native TrinityCore bot runtime; Jev is shadow analysis only"
        assert {"path_consistency", "stuck_behavior", "dps_loss_area", "next_fix", "canary_safe_to_promote"} <= set(questions)
        return {
            "model": "jev-latest",
            "answers": {
                question_id: (
                    {"type": "noul", "noul": 0.2}
                    if question["type"] == "noul"
                    else {"type": "choice", "choice": next(iter(question["criteria"])), "probabilities": {}, "confidence": 0.91}
                )
                for question_id, question in questions.items()
            },
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }

    monkeypatch.setattr(analyzer, "_call_jev", fake_call)
    report = analyzer.analyze(
        raw,
        env_file=env_file,
        expected_route=("bwd.magmaw.encounter",),
        run_id="canary-1",
        segment_id="02_magmaw",
        change_id="telemetry-v1",
        change_note="add path telemetry",
        baseline_path=None,
        combat_analysis_path=None,
    )
    analyzer._append_ledger(ledger, report)

    assert report["jev"]["model"] == "jev-latest"
    assert report["jev"]["answers"]["path_consistency"]["choice"] == "aligned"
    assert report["progress"]["fix_tracking"]["change_id"] == "telemetry-v1"
    stored = json.loads(ledger.read_text(encoding="utf-8"))
    assert stored["runs"][0]["run_id"] == "canary-1"
    assert stored["runs"][0]["party_dps"] is None


def test_analyze_accepts_closed_live_report_without_raw_trace(
    tmp_path: Path, monkeypatch
) -> None:
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    (live_dir / "report.json").write_text(
        json.dumps({
            "completion_reason": "machine_failure_predicate",
            "failure_reason": "bot_pool_underfilled",
            "failure_labels": ["bot_pool_underfilled"],
            "passed": 0,
            "all_passed": False,
            "acceptable_final_evidence": False,
            "active_bots": 0,
            "target_bots": 10,
            "trace_entries": 0,
            "diagnosis_count": 1,
            "validation_context": {
                "scenario_id": "blackwing_descent_10n_magmaw_diagnostic",
                "segment_id": "04_magmaw",
                "route_node_id": "bwd.magmaw.encounter",
                "route_generation": 4,
                "route_kind": "boss",
            },
            "diagnosis": {
                "failure_reason": "validation_admission_incomplete_batch:no_available_pool_candidate_for_tag",
                "combat_metrics": {
                    "available": False,
                    "route_node_id": "bwd.magmaw.encounter",
                    "party_dps": 0.0,
                },
                "raid_runtime": {"active": False, "admission_phase": "terminal"},
            },
            "summary": {"bots": 0, "decisions": 0, "stuck_events": 0},
            "preparation": {"bot_pool_reset": {"applied": True}},
            "trace": {"entries": [], "trace_schema_version": 1},
        }) + "\n",
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text("JEV=test-key\n", encoding="utf-8")

    def fake_call(state: dict[str, object], key: str, questions: dict[str, object]) -> dict[str, object]:
        assert key == "test-key"
        assert state["deterministic"]["live_report"]["failure_reason"] == "bot_pool_underfilled"
        return {
            "model": "jev-latest",
            "answers": {
                question_id: (
                    {"type": "noul", "noul": 0.99}
                    if question["type"] == "noul"
                    else {"type": "choice", "choice": next(iter(question["criteria"])), "probabilities": {}, "confidence": 0.91}
                )
                for question_id, question in questions.items()
            },
        }

    monkeypatch.setattr(analyzer, "_call_jev", fake_call)
    report = analyzer.analyze(
        live_dir,
        env_file=env_file,
        expected_route=("bwd.magmaw.encounter",),
        run_id="live-report-1",
        segment_id="04_magmaw",
        change_id="telemetry-v1",
        change_note="add path telemetry",
        baseline_path=None,
        combat_analysis_path=None,
        scope_route_prefix="bwd.magmaw.encounter",
    )

    assert report["source"]["path"].endswith("/report.json")
    assert report["deterministic"]["trace_rows"] == 0
    assert report["deterministic"]["live_report"]["failure_labels"] == ["bot_pool_underfilled"]
