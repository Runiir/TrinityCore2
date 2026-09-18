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


def test_progress_summary_closes_boss_tail_from_boss_death_receipt() -> None:
    entries = [
        {
            **_entry(
                sequence,
                "bwd.magmaw.encounter",
                "wait_for_candidate_backoff",
                route_generation=4,
                fingerprint_repeat_count=25,
                consecutive_same_decision_count=12,
            ),
            "_bot_guid": 10,
        }
        for sequence in range(1, 4)
    ]

    summary = analyzer._progress_summary(
        entries,
        analyzer.DEFAULT_EXPECTED_ROUTE,
        [
            {
                "payload": {
                    "boss_death_evidence": [
                        {
                            "result": "confirmed_unit_death",
                            "route_generation": 4,
                            "route_node_id": "bwd.magmaw.encounter",
                        }
                    ]
                }
            }
        ],
    )

    assert summary["active_stuck_behavior_counts"] == {}
    assert summary["resolved_stuck_behavior_counts"]["repeated_decision_loop"] == 3
    assert summary["route_terminal_generations"]["bwd.magmaw.encounter"] == 4


def test_report_rows_preserve_real_boss_death_as_terminal_evidence() -> None:
    rows = analyzer._report_rows(
        {
            "trace": {"entries": []},
            "evidence": {
                "real_boss_kill_evidence": [
                    {"route_generation": 4, "route_node_id": "bwd.magmaw.encounter"}
                ]
            },
            "status": {
                "validation_route": {
                    "boss_death_evidence": [
                        {
                            "result": "confirmed_unit_death",
                            "route_generation": 4,
                            "route_node_id": "bwd.magmaw.encounter",
                        }
                    ]
                }
            },
        }
    )

    status = rows[-1]["payload"]
    assert status["real_boss_kill_evidence"] == [
        {"route_generation": 4, "route_node_id": "bwd.magmaw.encounter"}
    ]
    assert status["boss_death_evidence"] == [
        {"route_generation": 4, "route_node_id": "bwd.magmaw.encounter"}
    ]
    assert status["evidence"]["boss_death_evidence"] == status["boss_death_evidence"]


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
    calls: list[set[str]] = []

    def fake_call(state: dict[str, object], key: str, questions: dict[str, object]) -> dict[str, object]:
        assert key == "test-key"
        assert state["authority"] == "native TrinityCore bot runtime; Jev is shadow analysis only"
        calls.append(set(questions))
        if "next_fix" in questions:
            assert set(questions) == {"next_fix"}
            assert "prior_judgments" in state
        else:
            assert {"path_consistency", "stuck_behavior", "dps_loss_area", "canary_safe_to_promote"} <= set(questions)
            assert "route_review" in state
            assert "boss_dps_review" in state
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
    assert len(calls) == 2
    assert report["jev"]["question_ids"][-1] == "stuck_behavior"
    assert report["jev"]["answers"]["next_fix"]["choice"] == "collect_more_canaries"
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
        assert state["route_review"]["run_gate"]["failure_reason"] == "bot_pool_underfilled"
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


def test_compact_metrics_preserves_spec_cadence_and_wcl_comparison() -> None:
    metrics = analyzer._compact_metrics(
        {
            "available": True,
            "party_damage": 100000.0,
            "party_dps": 25000.0,
            "elapsed_party_dps": 20000.0,
            "duration_sec": 5.0,
            "combat_duration_sec": 4.0,
            "actors": [
                {
                    "actor_guid": 10,
                    "actor_name": "Roostertours",
                    "actor_role": "dps",
                    "damage": 80000.0,
                    "active_dps": 20000.0,
                    "elapsed_dps": 16000.0,
                    "active_seconds": 4.0,
                    "damage_uptime": 0.8,
                    "distance_avg": 14.2,
                    "moving_fraction": 0.2,
                    "abilities": [
                        {"spell_id": 403, "spell_name": "Lightning Bolt", "events": 10, "damage": 80000.0}
                    ],
                }
            ],
        },
        {"10": {"class_spec": "elemental_shaman", "bot_name": "Roostertours"}},
    )

    actor = metrics["actors"][0]
    assert actor["class_spec"] == "elemental_shaman"
    assert actor["elapsed_dps"] == 16000.0
    assert actor["active_dps"] == 20000.0
    assert actor["abilities"][0]["spell_id"] == 403
    assert metrics["elapsed_party_dps"] == 20000.0
    assert metrics["party_dps_basis"] == "active_damage_seconds"

    annotated = analyzer._annotate_wcl_deltas(
        metrics,
        {
            "primary": {"actor_dps": {"elemental_shaman": 41866.0}},
            "supplemental": [],
        },
    )
    assert annotated["actors"][0]["wcl_observed_dps"] == 41866.0
    assert annotated["actors"][0]["elapsed_dps_delta_vs_wcl"] == -25866.0


def test_compact_metrics_prefers_full_window_native_action_outcomes() -> None:
    metrics = analyzer._compact_metrics(
        {
            "available": True,
            "route_node_id": "bwd.magmaw.encounter",
            "action_outcomes": [
                {
                    "route_node_id": "bwd.magmaw.encounter",
                    "actor_guid": 10,
                    "actor_name": "Firemake",
                    "actor_role": "dps",
                    "actor_class_id": 8,
                    "phase": "profile_resolve",
                    "action_type": "wait",
                    "action_name": "no_valid_profile_action",
                    "result": "no_action",
                    "reason": "no_valid_profile_action",
                    "retry_reason": "no_valid_profile_action",
                    "first_at_ms": 1000,
                    "last_at_ms": 9000,
                    "count": 40,
                }
            ],
        },
        {"10": {"class_spec": "fire_mage", "role": "dps"}},
    )

    assert metrics["action_outcome_count"] == 1
    outcome = metrics["action_outcomes"][0]
    assert outcome["class_spec"] == "fire_mage"
    assert outcome["outcome"] == "no_action"
    assert outcome["reason_code"] == "no_valid_profile_action"
    assert outcome["count"] == 40


def test_native_action_outcome_normalization_is_idempotent() -> None:
    compacted = analyzer._compact_native_action_outcomes(
        [
            {
                "bot_guid": 10,
                "class_spec": "fire_mage",
                "action_category": "wait",
                "action_name": "already_casting",
                "outcome": "casting",
                "reason_code": "already_casting",
                "count": 12,
            }
        ],
        {"10": {"class_spec": "fire_mage", "role": "dps"}},
    )

    assert compacted[0]["action_category"] == "wait"
    assert compacted[0]["outcome"] == "casting"
    assert compacted[0]["reason_code"] == "already_casting"


def test_compact_metrics_preserves_full_window_candidate_rejections() -> None:
    metrics = analyzer._compact_metrics(
        {
            "available": True,
            "candidate_rejections": [
                {
                    "route_node_id": "bwd.magmaw.encounter",
                    "actor_guid": 10,
                    "actor_role": "dps",
                    "actor_name": "Firemake",
                    "actor_class_id": 8,
                    "phase": "profile_resolve",
                    "spell_id": 133,
                    "action_category": "builder",
                    "reason": "max_range_exceeded",
                    "count": 12,
                }
            ],
        },
        {"10": {"class_spec": "fire_mage", "role": "dps"}},
    )

    assert metrics["candidate_rejection_count"] == 1
    rejection = metrics["candidate_rejections"][0]
    assert rejection["class_spec"] == "fire_mage"
    assert rejection["reason"] == "max_range_exceeded"
    assert rejection["count"] == 12


def test_jev_candidate_rejection_summary_groups_spell_rows_and_keeps_movement() -> None:
    summary = analyzer._summarize_jev_candidate_rejections(
        [
            {
                "bot_guid": 10,
                "class_spec": "fire_mage",
                "action_category": "builder",
                "reason": "max_range_exceeded",
                "spell_id": 133,
                "count": 4,
            },
            {
                "bot_guid": 10,
                "class_spec": "fire_mage",
                "action_category": "spender",
                "reason": "max_range_exceeded",
                "spell_id": 2136,
                "count": 3,
            },
        ]
    )

    assert summary == [
        {
            "bot_guid": 10,
            "class_spec": "fire_mage",
            "reason": "max_range_exceeded",
            "count": 7,
            "action_categories": ["builder", "spender"],
            "spell_ids": [133, 2136],
        }
    ]


def test_candidate_rejection_signal_separates_expected_waits_from_actionable_gates() -> None:
    signal = analyzer._candidate_rejection_signal(
        [
            {
                "bot_guid": 10,
                "class_spec": "fire_mage",
                "action_category": "builder",
                "reason": "already_casting",
                "spell_id": 133,
                "count": 400,
            },
            {
                "bot_guid": 10,
                "class_spec": "fire_mage",
                "action_category": "builder",
                "reason": "global_cooldown",
                "spell_id": 133,
                "count": 100,
            },
            {
                "bot_guid": 10,
                "class_spec": "fire_mage",
                "action_category": "builder",
                "reason": "max_range_exceeded",
                "spell_id": 133,
                "count": 7,
            },
        ]
    )

    assert signal["candidate_scan_count"] == 507
    assert signal["expected_profile_wait_count"] == 500
    assert signal["actionable_candidate_count"] == 7
    assert signal["actionable_candidate_groups"] == [
        {
            "bot_guid": 10,
            "class_spec": "fire_mage",
            "reason": "max_range_exceeded",
            "count": 7,
            "action_categories": ["builder"],
            "spell_ids": [133],
        }
    ]


def test_jev_action_outcome_summary_counts_native_failures_separately() -> None:
    summary = analyzer._summarize_jev_action_outcomes(
        [
            {"bot_guid": 10, "class_spec": "fire_mage", "outcome": "casting", "count": 40},
            {"bot_guid": 10, "class_spec": "fire_mage", "outcome": "global_cooldown", "count": 8},
            {"bot_guid": 10, "class_spec": "fire_mage", "outcome": "no_action", "count": 2},
            {"bot_guid": 10, "class_spec": "fire_mage", "outcome": "cast_failed", "count": 1},
        ]
    )

    assert summary == [
        {
            "bot_guid": 10,
            "class_spec": "fire_mage",
            "outcome_counts": {
                "casting": 40,
                "global_cooldown": 8,
                "no_action": 2,
                "cast_failed": 1,
            },
            "outcome_count": 51,
            "actionable_failure_count": 3,
            "actionable_failure_ratio": 0.058824,
            "expected_wait_count": 48,
        }
    ]


def test_boss_trace_window_excludes_teardown_and_post_terminal_rows() -> None:
    entries = [
        {
            **_entry(1, "bwd.magmaw.encounter", "cast_combat_spell"),
            "timestamp_ms": 2000,
            "_bot_guid": 10,
        },
        {
            **_entry(2, "bwd.magmaw.encounter", "cast_combat_spell"),
            "timestamp_ms": 3000,
            "action_result": "rejected",
            "action_rejection_reason": "global_cooldown",
            "_bot_guid": 10,
        },
        {
            **_entry(3, "bwd.magmaw.encounter", "wait"),
            "timestamp_ms": 4000,
            "action_result": "callback_instance_unavailable",
            "_bot_guid": 10,
        },
        {
            **_entry(4, "bwd.magmaw.encounter", "boss_killed"),
            "timestamp_ms": 5000,
            "_bot_guid": 10,
        },
        {
            **_entry(5, "bwd.magmaw.encounter", "validation_route_terminal"),
            "timestamp_ms": 6000,
            "_bot_guid": 10,
        },
    ]

    retained, capture = analyzer._boss_trace_window(
        entries,
        {"first_at_ms": 1000, "last_at_ms": 9000},
    )

    assert [entry["sequence"] for entry in retained] == [1, 2]
    assert capture["trace_is_retained_tail"] is True
    assert capture["terminal_at_ms"] == 5000
    assert capture["excluded_after_terminal_rows"] == 1
    assert capture["excluded_terminal_rows"] == 1
    assert capture["excluded_teardown_reason_counts"] == {
        "callback_instance_unavailable": 1,
    }


def test_decision_receipts_are_normalized_and_limited_to_boss_window() -> None:
    report = {
        "decision_receipts": [
            {
                "actor_guid": 10,
                "count": 2,
                "first_timestamp_ms": 2000,
                "last_timestamp_ms": 3000,
                "route_node_id": "bwd.magmaw.encounter",
                "gate": "planner_admission",
                "outcome_reason": "global_cooldown",
                "reason": "spell_cast",
                "reason_type": "combat_action",
                "result": "rejected",
            },
            {
                "actor_guid": 10,
                "count": 4,
                "first_timestamp_ms": 6000,
                "last_timestamp_ms": 7000,
                "route_node_id": "bwd.magmaw.encounter",
                "gate": "planner_admission",
                "outcome_reason": "after_boss_kill",
                "reason": "spell_cast",
                "reason_type": "combat_action",
                "result": "rejected",
            },
        ]
    }

    outcomes = analyzer._compact_decision_receipts(
        report,
        "bwd.magmaw.encounter",
        {"10": {"role": "dps", "class_spec": "fire_mage"}},
        {"dps"},
        window_start_ms=1000,
        window_end_ms=5000,
        terminal_at_ms=5000,
    )

    assert len(outcomes) == 1
    assert outcomes[0]["bot_guid"] == 10
    assert outcomes[0]["class_spec"] == "fire_mage"
    assert outcomes[0]["outcome"] == "rejected"
    assert outcomes[0]["reason_code"] == "global_cooldown"
    assert outcomes[0]["count"] == 2
