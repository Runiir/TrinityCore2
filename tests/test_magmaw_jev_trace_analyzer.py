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


def test_native_clear_is_not_classified_as_wipe_when_identity_is_incomplete() -> None:
    outcome = analyzer._native_gameplay_outcome(
        {
            "completion_reason": "validation_route_manifest_complete",
            "acceptable_final_evidence": False,
            "active_bots": 10,
            "final_evidence_rejections": ["incomplete_evidence_identity"],
            "acceptance_verification": {
                "accepted": False,
                "manifest_complete": True,
                "rejections": ["incomplete_evidence_identity"],
            },
            "evidence": {
                "manifest_completion_evidence": [
                    {"route_node_id": "bwd.magmaw.encounter", "route_generation": 4}
                ],
                "real_boss_kill_evidence": [
                    {"route_node_id": "bwd.magmaw.encounter", "route_generation": 4}
                ],
                "cohort_all_dead_wiped": False,
            },
            "watchdog_state": {
                "all_dead_wiped": False,
                "death_loop": False,
                "no_progress": False,
                "repeated_decision_loop": False,
            },
        }
    )

    assert outcome["status"] == "clear"
    assert outcome["native_clear"] is True
    assert outcome["certification_status"] == "uncertified"
    assert outcome["certification_rejections"] == ["incomplete_evidence_identity"]


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
                    "dps": 20000.0,
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
    assert annotated["actors"][0]["dps_delta_vs_wcl"] == -21866.0
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


def test_actor_loss_signals_separate_idle_movement_and_policy_hypotheses() -> None:
    signals = analyzer._actor_loss_signals(
        {
            "combat_duration_sec": 100,
            "actors": [
                {
                    "bot_guid": 10,
                    "role": "dps",
                    "class_spec": "balance_druid",
                    "active_dps": 38000,
                    "elapsed_dps": 23000,
                    "wcl_observed_dps": 41000,
                    "active_dps_delta_vs_wcl": -3000,
                    "elapsed_dps_delta_vs_wcl": -18000,
                    "active_seconds": 60,
                    "damage_uptime": 0.60,
                    "moving_fraction": 0.01,
                    "distance_avg": 8.4,
                    "abilities": [],
                }
            ],
        },
        [
            {
                "bot_guid": 10,
                "class_spec": "balance_druid",
                "outcome_count": 100,
                "actionable_failure_count": 2,
                "actionable_failure_ratio": 0.02,
                "outcome_counts": {"casting": 80, "ok": 18, "cast_failed": 2},
            }
        ],
        [
            {"bot_guid": 10, "reason": "already_casting", "count": 100},
            {"bot_guid": 10, "reason": "movement_requires_instant_action", "count": 5},
            {"bot_guid": 10, "reason": "declarative_area_damage_semantics_forbidden", "count": 120},
        ],
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal["candidate_actions"] == [
        {
            "action": "uptime_cadence",
            "evidence": [
                "idle_fraction_material",
                "moving_fraction_low",
                "native_failure_rate_low",
            ],
            "contradictions": [],
            "evidence_strength": "attributable_idle",
        }
    ]
    assert signal["policy_hypotheses"][0]["action"] == "rotation_profile"
    assert signal["candidate_gate_counts"]["profile_policy"] == 120


def test_actor_loss_signals_do_not_use_wall_clock_gap_as_wcl_loss() -> None:
    signals = analyzer._actor_loss_signals(
        {
            "combat_duration_sec": 100,
            "actors": [
                {
                    "bot_guid": 10,
                    "role": "dps",
                    "class_spec": "fire_mage",
                    "dps": 40000,
                    "active_dps": 52000,
                    "elapsed_dps": 32000,
                    "wcl_observed_dps": 40000,
                    "active_seconds": 64,
                    "damage_uptime": 0.64,
                    "moving_fraction": 0.01,
                    "abilities": [],
                }
            ],
        },
        [
            {
                "bot_guid": 10,
                "class_spec": "fire_mage",
                "outcome_count": 100,
                "actionable_failure_count": 2,
                "outcome_counts": {"casting": 80, "ok": 18, "cast_failed": 2},
            }
        ],
        [],
    )

    signal = signals[0]
    assert signal["active_dps_gap_vs_wcl"] is False
    assert signal["elapsed_dps_gap_vs_wcl"] is True
    assert signal["encounter_dps_gap_vs_wcl"] is False
    assert signal["candidate_actions"] == [
        {
            "action": "collect_more_canaries",
            "evidence": ["no_single_causal_signal_clears_the_screen"],
            "contradictions": [],
            "evidence_strength": "insufficient",
        }
    ]
    assert signal["policy_hypotheses"] == []


def test_target_duty_context_aligns_failure_windows_with_required_work() -> None:
    context = analyzer._target_duty_context(
        {
            "abilities": [
                {
                    "actor_guid": 10,
                    "actor_role": "dps",
                    "perspective": "damage_done",
                    "route_node_id": "bwd.magmaw.encounter",
                    "target_entry": 41570,
                    "target_name": "Magmaw",
                    "event_count": 20,
                    "amount": 100000,
                    "originated_amount": 100000,
                    "first_at_ms": 1000,
                    "last_at_ms": 3000,
                },
                {
                    "actor_guid": 10,
                    "actor_role": "dps",
                    "perspective": "damage_done",
                    "route_node_id": "bwd.magmaw.encounter",
                    "target_entry": 41806,
                    "target_name": "Lava Parasite",
                    "event_count": 2,
                    "amount": 60000,
                    "originated_amount": 60000,
                    "first_at_ms": 1400,
                    "last_at_ms": 1600,
                },
            ],
            "recent_events": [
                {
                    "kind": "damage",
                    "route_node_id": "bwd.magmaw.encounter",
                    "source_guid": 10,
                    "source_moving": True,
                    "timestamp_ms": 1500,
                }
            ],
            "recent_event_capacity": 1,
            "recent_events_dropped": 4,
        },
        {"actors": [{"bot_guid": 10, "role": "dps"}]},
        [
            {
                "bot_guid": 10,
                "action_name": "builder",
                "outcome": "cast_failed",
                "reason_code": "spell_cast_result_49",
                "first_at_ms": 1400,
                "last_at_ms": 1600,
            }
        ],
    )

    actor = context["actors"][0]
    assert actor["mechanic_target_originated_damage_share"] == 0.375
    assert actor["duty_correlated_native_failure_window_count"] == 1
    assert actor["duty_explains_idle"] is True
    assert actor["counterfactual_status"] == "partial_recent_capture"
    assert actor["counterfactual_eligible"] is False


def test_target_duty_context_keeps_incidental_add_damage_counterfactual_clean() -> None:
    context = analyzer._target_duty_context(
        {
            "abilities": [
                {
                    "actor_guid": 10,
                    "actor_role": "dps",
                    "perspective": "damage_done",
                    "route_node_id": "bwd.magmaw.encounter",
                    "target_entry": 41570,
                    "target_name": "Magmaw",
                    "event_count": 100,
                    "amount": 3000000,
                    "originated_amount": 3000000,
                    "first_at_ms": 1000,
                    "last_at_ms": 11000,
                },
                {
                    "actor_guid": 10,
                    "actor_role": "dps",
                    "perspective": "damage_done",
                    "route_node_id": "bwd.magmaw.encounter",
                    "target_entry": 41806,
                    "target_name": "Lava Parasite",
                    "event_count": 2,
                    "amount": 60000,
                    "originated_amount": 60000,
                    "first_at_ms": 1400,
                    "last_at_ms": 1600,
                },
            ],
            "recent_events": [
                {
                    "kind": "damage",
                    "route_node_id": "bwd.magmaw.encounter",
                    "source_guid": 10,
                    "source_moving": True,
                    "target_entry": 41806,
                    "target_name": "Lava Parasite",
                    "timestamp_ms": 1500,
                }
            ],
            "recent_event_capacity": 16384,
            "recent_events_dropped": 0,
        },
        {"actors": [{"bot_guid": 10, "role": "dps"}]},
        [
            {
                "bot_guid": 10,
                "action_name": "builder",
                "outcome": "cast_failed",
                "reason_code": "spell_cast_result_49",
                "first_at_ms": 1400,
                "last_at_ms": 1600,
            }
        ],
    )

    actor = context["actors"][0]
    assert actor["mechanic_duty_scope"] == "incidental"
    assert actor["mechanic_target_originated_damage_share"] < 0.05
    assert actor["duty_moving_damage_event_count"] == 1
    assert actor["duty_explains_idle"] is False
    assert actor["counterfactual_status"] == "eligible"
    assert actor["counterfactual_eligible"] is True


def test_target_duty_context_records_balance_mushroom_assignment_execution() -> None:
    context = analyzer._target_duty_context(
        {
            "abilities": [
                {
                    "actor_guid": 10,
                    "actor_role": "dps",
                    "perspective": "damage_done",
                    "route_node_id": "bwd.magmaw.encounter",
                    "target_entry": 41570,
                    "target_name": "Magmaw",
                    "event_count": 20,
                    "originated_amount": 1000000,
                    "first_at_ms": 1000,
                    "last_at_ms": 11000,
                },
                {
                    "actor_guid": 10,
                    "actor_role": "dps",
                    "perspective": "damage_done",
                    "route_node_id": "bwd.magmaw.encounter",
                    "target_entry": 41806,
                    "target_name": "Lava Parasite",
                    "spell_id": 78777,
                    "event_count": 3,
                    "originated_damage": 60000,
                    "first_at_ms": 4000,
                    "last_at_ms": 5000,
                },
            ],
            "recent_events": [],
            "recent_event_capacity": 16384,
            "recent_events_dropped": 0,
        },
        {
            "actors": [
                {
                    "bot_guid": 10,
                    "role": "dps",
                    "class_spec": "balance_druid",
                }
            ]
        },
        [
            {
                "bot_guid": 10,
                "class_spec": "balance_druid",
                "spell_id": 88747,
                "outcome": "ok",
                "reason_code": "global_cooldown",
                "count": 3,
            },
            {
                "bot_guid": 10,
                "class_spec": "balance_druid",
                "spell_id": 88751,
                "outcome": "ok",
                "reason_code": "cooldown",
                "count": 1,
            },
        ],
    )

    actor = context["actors"][0]
    assert actor["assignment_id"] == "magmaw_balance_mushroom_add_control"
    assert actor["assignment_status"] == "executed"
    assert actor["assignment_detonation_count"] == 1
    assert actor["assignment_placement_decision_count"] == 3
    assert actor["assignment_damage_event_count"] == 3
    assert actor["assignment_landed_damage"] == 60000
    assert actor["mechanic_duty_scope"] == "required_assignment"
    assert actor["duty_explains_idle"] is True
    assert actor["counterfactual_status"] == "required_assignment_observed"
    assert actor["counterfactual_eligible"] is False


def test_actor_loss_signal_routes_incomplete_balance_assignment_to_encounter_work() -> None:
    signals = analyzer._actor_loss_signals(
        {
            "combat_duration_sec": 100,
            "actors": [
                {
                    "bot_guid": 10,
                    "role": "dps",
                    "class_spec": "balance_druid",
                    "dps": 25000,
                    "active_dps": 35000,
                    "elapsed_dps": 22000,
                    "wcl_observed_dps": 41000,
                    "active_seconds": 65,
                    "damage_uptime": 0.65,
                    "moving_fraction": 0.01,
                    "abilities": [],
                }
            ],
        },
        [
            {
                "bot_guid": 10,
                "class_spec": "balance_druid",
                "outcome_count": 80,
                "actionable_failure_count": 1,
                "outcome_counts": {"casting": 79, "cast_failed": 1},
            }
        ],
        [],
        {
            "available": True,
            "actors": [
                {
                    "bot_guid": 10,
                    "required_assignment_active": True,
                    "assignment_id": "magmaw_balance_mushroom_add_control",
                    "assignment_status": "incomplete",
                    "assignment_counterfactual_status": "required_assignment_incomplete",
                    "duty_explains_idle": False,
                    "counterfactual_status": "required_assignment_incomplete",
                }
            ],
        },
    )

    signal = signals[0]
    assert signal["required_assignment_active"] is True
    assert signal["assignment_status"] == "incomplete"
    assert signal["candidate_actions"] == [
        {
            "action": "encounter_assignment",
            "evidence": [
                "required_assignment_observed",
                "required_assignment_landed_cycle_incomplete",
            ],
            "contradictions": ["rotation_and_movement_are_not_counterfactual_clean"],
            "evidence_strength": "direct_assignment",
        }
    ]


def test_jev_questions_add_assignment_judgment_for_required_duty() -> None:
    questions = analyzer._jev_questions(
        False,
        actor_specs=[
            {
                "bot_guid": 10,
                "class_spec": "balance_druid",
                "required_assignment_active": True,
                "assignment_id": "magmaw_balance_mushroom_add_control",
            }
        ],
    )

    assert questions["actor_assignment_10"]["type"] == "choice"
    assert set(questions["actor_assignment_10"]["criteria"]) == {
        "assignment_executed",
        "assignment_incomplete",
        "assignment_unobserved",
    }


def test_target_duty_context_marks_only_lowest_guid_fire_mage_as_baiter() -> None:
    context = analyzer._target_duty_context(
        {
            "abilities": [],
            "recent_events": [],
            "recent_event_capacity": 16384,
            "recent_events_dropped": 0,
        },
        {
            "actors": [
                {"bot_guid": 10, "role": "dps", "class_spec": "fire_mage"},
                {"bot_guid": 11, "role": "dps", "class_spec": "fire_mage"},
            ]
        },
        [],
    )

    assignments = {
        actor["bot_guid"]: actor
        for actor in context["actors"]
    }
    assert assignments[10]["assignment_id"] == "magmaw_fixed_pillar_baiter"
    assert assignments[10]["assignment_role"] == "fire_mage_pillar_baiter"
    assert assignments[10]["assignment_status"] == "identity_assigned"
    assert assignments[11]["assignment_status"] == "not_required"
    assert assignments[11]["assignment_counterfactual_status"] == "eligible"


def test_normal_target_eligibility_gates_do_not_create_target_lease_candidate() -> None:
    signals = analyzer._actor_loss_signals(
        {
            "combat_duration_sec": 100,
            "actors": [
                {
                    "bot_guid": 10,
                    "role": "dps",
                    "class_spec": "elemental_shaman",
                    "dps": 25000,
                    "active_dps": 35000,
                    "elapsed_dps": 22000,
                    "wcl_observed_dps": 41000,
                    "active_seconds": 65,
                    "damage_uptime": 0.65,
                    "moving_fraction": 0.01,
                    "abilities": [],
                }
            ],
        },
        [
            {
                "bot_guid": 10,
                "outcome_count": 80,
                "actionable_failure_count": 1,
                "outcome_counts": {"casting": 79, "cast_failed": 1},
            }
        ],
        [
            {"bot_guid": 10, "reason": "forbidden_target_aura_active", "count": 1423},
            {"bot_guid": 10, "reason": "missing_required_target_aura", "count": 679},
            {"bot_guid": 10, "reason": "target_not_interruptible", "count": 240},
        ],
    )

    actions = {candidate["action"] for candidate in signals[0]["candidate_actions"]}
    assert "target_lease" not in actions
    assert "uptime_cadence" in actions


def test_actor_loss_signal_blocks_cadence_fix_when_duty_explains_idle() -> None:
    signals = analyzer._actor_loss_signals(
        {
            "combat_duration_sec": 100,
            "actors": [
                {
                    "bot_guid": 10,
                    "role": "dps",
                    "class_spec": "balance_druid",
                    "active_dps": 38000,
                    "elapsed_dps": 23000,
                    "wcl_observed_dps": 41000,
                    "active_seconds": 60,
                    "damage_uptime": 0.60,
                    "moving_fraction": 0.01,
                    "abilities": [],
                }
            ],
        },
        [
            {
                "bot_guid": 10,
                "outcome_count": 100,
                "actionable_failure_count": 2,
                "outcome_counts": {"casting": 98, "cast_failed": 2},
            }
        ],
        [],
        {
            "available": True,
            "actors": [
                {
                    "bot_guid": 10,
                    "duty_explains_idle": True,
                    "counterfactual_status": "partial_recent_capture",
                }
            ],
        },
    )

    assert signals[0]["candidate_actions"][0]["action"] == "collect_more_canaries"
    assert "required_target_duty_overlaps_loss_window" in signals[0]["candidate_actions"][0]["evidence"]
    assert signals[0]["duty_explains_idle"] is True
    assert signals[0]["counterfactual_status"] == "partial_recent_capture"


def test_jev_action_outcome_slice_excludes_expected_waits() -> None:
    sliced = analyzer._jev_action_outcome_slice(
        [
            {
                "bot_guid": 10,
                "class_spec": "fire_mage",
                "action_category": "wait",
                "action_name": "already_casting",
                "outcome": "casting",
                "count": 500,
            },
            {
                "bot_guid": 10,
                "class_spec": "fire_mage",
                "action_category": "cast",
                "action_name": "fireball",
                "outcome": "cast_failed",
                "reason_code": "spell_cast_result_49",
                "count": 2,
            },
        ]
    )

    assert len(sliced) == 1
    assert sliced[0]["outcome"] == "cast_failed"
    assert sliced[0]["count"] == 2


def test_actor_action_gate_preserves_high_confidence_advice_and_uncertainty() -> None:
    gate = analyzer._actor_action_gate(
        {
            "actor_action_10": {
                "choice": "uptime_cadence",
                "confidence": 0.75,
            },
            "actor_action_11": {
                "choice": "collect_more_canaries",
                "confidence": 0.92,
            },
            "actor_action_12": {
                "choice": "movement_recovery",
                "confidence": 0.41,
            },
        }
    )

    assert gate["actor_action_10"]["status"] == "advisory_action"
    assert gate["actor_action_11"]["status"] == "advisory_collect_more"
    assert gate["actor_action_12"]["status"] == "review_required"


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
