from __future__ import annotations

import json
from pathlib import Path

from tools.raid_program.bot_optimization_acceptance import (
    OUTPUT_SCHEMA,
    canonical_sha256,
    compare_optimization_acceptance,
    main,
)
from tools.raid_program.capture_timeline_artifacts import write_capture_timeline


def _actor(
    *, dps: float, active_fraction: float = 0.9, boss_dps: float | None = None,
    add_dps: float = 5.0, death: bool = False, latency_ms: float = 100.0,
    elapsed: float = 100.0,
) -> dict[str, object]:
    boss_dps = dps - add_dps if boss_dps is None else boss_dps
    return {
        "name": "bot",
        "role": "dps",
        "class_id": 8,
        "damage": {
            "hostile_originated": dps * elapsed,
            "direct": dps * elapsed * 0.8,
            "periodic": dps * elapsed * 0.2,
            "owner": dps * elapsed,
            "owned_source": 0,
            "unknown_origin": 0,
        },
        "dps": {"hostile_originated": dps},
        "activity": {
            "intervals": [],
            "active_seconds": active_fraction * elapsed,
            "longest_fresh_attack_outage_ms": 750,
        },
        "survival": {
            "first_activity_at_ms": 1000,
            "last_activity_at_ms": 101000,
            "death_observed": death,
        },
        "target_damage": {
            "boss": boss_dps * elapsed,
            "add": add_dps * elapsed,
        },
        "target_allocations": {},
        "target_switch_latency_ms": latency_ms,
    }


def _nonattacking_healer(*, hps: float, elapsed: float = 100.0) -> dict[str, object]:
    return {
        "name": "healer",
        "role": "healer",
        "class_id": 2,
        "damage": {"hostile_originated": 0, "dps": 0.0},
        "activity": {"intervals": [], "active_seconds": elapsed * 0.8},
        "survival": {"death_observed": False},
        "effective_healing": hps * elapsed,
        "effective_hps": hps,
        "target_damage": {"boss": 0, "add": 0},
        "target_allocations": [],
        "target_switch_latency_ms": [],
        "target_switch_observation_complete": True,
    }


def _summary(
    *, party_dps: float, actors: dict[str, dict[str, object]] | None = None,
    clear: bool = True, elapsed: float = 100.0, source_commit: str = "1" * 40,
) -> dict[str, object]:
    capture_id = "cata_raid_phase1_magmaw_v1"
    scenario_id = "blackwing_descent_10n_magmaw_diagnostic"
    raw_sha256 = "b" * 64
    report_source = {
        "schema_version": 1,
        "capture_id": capture_id,
        "scenario_id": scenario_id,
        "started_at_utc": "2026-09-10T12:00:00Z",
        "source_identity": {
            "clean": True,
            "head": source_commit,
            "tree": "2" * 40,
        },
        "binary_sha256": "3" * 64,
        "config_sha256": "4" * 64,
        "runtime_profile": "magmaw_10n",
        "runtime_identity": {
            "server_epoch": 1,
            "attempt_id": 1,
            "wipe_generation": 0,
            "profile_generation": 1,
            "profile_content_hash": "a" * 64,
            "map_id": 669,
            "instance_id": 7,
            "group_guid": 99,
            "expected_size": 10,
            "expected_difficulty": 3,
            "strategy_id": "magmaw_10n",
        },
        "accepted_boss_identity": {"target_entry": 41570, "route_generation": 3},
        "raw_normalized_batch": {"sha256": raw_sha256, "row_count": 100},
    }
    return {
        "schema": "cata_raid_bot_timeline_summary_v1",
        "clear_accepted": clear,
        "identity": {
            "cohort_id": "raid:1",
            "server_epoch": 1,
            "attempt_id": 1,
            "combat_log_epoch": 1,
            "profile_generation": 1,
            "profile_content_hash": "a" * 64,
            "scenario_id": scenario_id,
            "capture_id": capture_id,
            "source": {
                "raw_sha256": raw_sha256,
                "report_sha256": "c" * 64,
                "report_source": report_source,
                "report_source_sha256": canonical_sha256(report_source),
            },
        },
        "window": {
            "first_hostile_at_ms": 1000,
            "native_boss_death_at_ms": 101000,
            "elapsed_seconds": elapsed,
            "complete": True,
            "basis": "first_hostile_to_native_boss_death",
        },
        "accounting": {
            "hostile_originated_damage": party_dps * elapsed,
            "exact_party_dps": party_dps,
            "excluded_friendly_damage": 0,
            "excluded_spell_79010_damage": 0,
            "owner_damage": party_dps * elapsed,
            "owned_source_damage": 0,
            "unknown_source_damage": 0,
        },
        "actors": actors or {"30006": _actor(dps=party_dps, elapsed=elapsed)},
        "phase_intervals": [
            {
                "phase": "body",
                "start_at_ms": 1000,
                "end_at_ms": 51000,
                "boundary_provenance": "typed_native",
            },
            {
                "phase": "head",
                "start_at_ms": 51000,
                "end_at_ms": 101000,
                "boundary_provenance": "typed_native",
            },
        ],
        "completeness": {
            "raw_available": True,
            "report_available": True,
            "trace_gaps": 0,
            "combat_gaps": 0,
            "identity_rejections": [],
            "legacy_historical_metadata_warning": False,
            "typed_attack_origin_available": True,
            "absent_pre_failure_trace": False,
        },
    }


def _auto_report_source() -> dict[str, object]:
    return {
        "schema_version": 1,
        "capture_id": "cata_raid_phase1_magmaw_v1",
        "scenario_id": "blackwing_descent_10n_magmaw_diagnostic",
        "started_at_utc": "2026-09-10T12:00:00Z",
        "identity": {"clean": True, "head": "1" * 40, "tree": "2" * 40},
        "binary_sha256": "3" * 64,
        "config_sha256": "4" * 64,
        "runtime_profile": "magmaw_10n",
        "accepted_raid_runtime": {
            "cohort_id": "raid:1",
            "server_epoch": 1,
            "attempt_id": 1,
            "wipe_generation": 0,
            "profile_generation": 1,
            "profile_content_hash": "a" * 64,
            "map_id": 669,
            "instance_id": 7,
            "group_guid": 99,
            "expected_size": 10,
            "expected_difficulty": 3,
            "strategy_id": "magmaw_10n",
        },
        "combat_log_event_stream": {
            "identity": {
                "cohort_id": "raid:1",
                "server_epoch": 1,
                "attempt_id": 1,
                "combat_log_epoch": 1,
            },
            "profile_context": {
                "profile_generation": 1,
                "profile_content_hash": "a" * 64,
            },
        },
        "development_run": {
            "accepted_boss_identity": {
                "target_entry": 41570,
                "route_generation": 3,
            },
        },
        "raw_normalized_batch": {"sha256": "b" * 64, "row_count": 1},
    }


def _setup(
    baseline: dict[str, object], candidate: dict[str, object]
) -> dict[str, object]:
    baseline_source = baseline["identity"]["source"]["report_source"]
    candidate_source = candidate["identity"]["source"]["report_source"]
    baseline_commit = baseline_source["source_identity"]["head"]
    candidate_commit = candidate_source["source_identity"]["head"]
    return {
        "schema": "cata_raid_bot_optimization_setup_match_v1",
        "baseline_summary_sha256": canonical_sha256(baseline),
        "candidate_summary_sha256": canonical_sha256(candidate),
        "fields": {
            field: {
                "baseline": f"{field}-sha256",
                "candidate": f"{field}-sha256",
                "evidence": [f"retained/{field}.json"],
            }
            for field in (
                "roster",
                "loadout",
                "route",
                "profile",
                "config",
                "encounter",
                "runtime_assets",
            )
        },
        "intentional_source_changes": ([{
                "field": "source_commit",
                "baseline": baseline_commit,
                "candidate": candidate_commit,
                "reason": "candidate gameplay repair under comparison",
                "evidence": ["build_receipt.json"],
            }] if baseline_commit != candidate_commit else []),
        "fast_benchmark": {
            "source_commit": "4b24d7242f81aadeb53149d5fe2f6e9c284afefd",
            "exact_party_dps": 200864.383,
            "matched_baseline": False,
        },
    }


def _repair(*, requested: bool = False, evidence_class: str = "native_trace") -> dict[str, object]:
    return {
        "schema": "cata_raid_requested_repair_assertions_v1",
        "requested": requested,
        "repair_id": "ENC-003" if requested else None,
        "assertions": [
            {
                "id": "legal_optional_target_or_eligible_fallback",
                "evidence_class": evidence_class,
                "passed": True,
                "evidence": ["diagnosis/target-admission.json"],
            }
        ] if requested else [],
    }


def test_clear_with_thirty_percent_decline_fails_performance_independently() -> None:
    baseline = _summary(party_dps=100.0)
    candidate = _summary(party_dps=70.0, actors={"30006": _actor(dps=70.0)})
    report = compare_optimization_acceptance(
        baseline,
        candidate,
        _setup(baseline, candidate),
        _repair(requested=True),
    )

    assert report["clear_accepted"] is True
    assert report["repair_edge_accepted"] is True
    assert report["performance_verdict"] == "fail"
    assert report["performance_accepted"] is False
    assert report["diagnosis_required"] is True
    assert "party_exact_dps_material_decline" in report["material_decline_reasons"]
    assert report["single_pair_uncertainty"] is True


def test_setup_mismatch_is_inconclusive() -> None:
    baseline = _summary(party_dps=100.0)
    candidate = _summary(party_dps=101.0, actors={"30006": _actor(dps=101.0)})
    setup = _setup(baseline, candidate)
    setup["fields"]["route"]["candidate"] = "different-route"

    report = compare_optimization_acceptance(
        baseline,
        candidate,
        setup,
        _repair(),
    )

    assert report["setup_match_accepted"] is False
    assert report["performance_verdict"] == "inconclusive"
    assert report["performance_accepted"] is None
    assert "setup_route_mismatch" in report["sufficiency_reasons"]


def test_conflicting_phase_facts_are_inconclusive() -> None:
    baseline = _summary(party_dps=100.0)
    candidate = _summary(party_dps=100.0)
    candidate["phase_intervals"][0]["conflict"] = True

    report = compare_optimization_acceptance(
        baseline, candidate, _setup(baseline, candidate), _repair()
    )

    assert report["performance_verdict"] == "inconclusive"
    assert "candidate_phase_0_conflict" in report["sufficiency_reasons"]


def test_equal_empty_setup_identities_are_rejected() -> None:
    baseline = _summary(party_dps=100.0)
    candidate = _summary(party_dps=100.0)
    setup = _setup(baseline, candidate)
    setup["fields"]["loadout"]["baseline"] = None
    setup["fields"]["loadout"]["candidate"] = None

    report = compare_optimization_acceptance(
        baseline, candidate, setup, _repair()
    )

    assert report["performance_verdict"] == "inconclusive"
    assert "setup_loadout_identity_empty" in report["sufficiency_reasons"]
    assert report["setup_match"]["evidence_pointer_contents_verified"] is False


def test_legitimate_zero_inside_setup_identity_is_not_empty() -> None:
    baseline = _summary(party_dps=100.0)
    candidate = _summary(party_dps=100.0)
    setup = _setup(baseline, candidate)
    setup["fields"]["encounter"]["baseline"] = {"difficulty": 0, "map_id": 669}
    setup["fields"]["encounter"]["candidate"] = {"difficulty": 0, "map_id": 669}

    report = compare_optimization_acceptance(
        baseline, candidate, setup, _repair()
    )

    assert report["performance_verdict"] == "pass"


def test_missing_direct_activity_is_inconclusive_not_zero() -> None:
    baseline = _summary(party_dps=100.0)
    candidate = _summary(party_dps=100.0)
    del candidate["actors"]["30006"]["activity"]["active_seconds"]

    report = compare_optimization_acceptance(
        baseline, candidate, _setup(baseline, candidate), _repair()
    )

    assert report["performance_verdict"] == "inconclusive"
    assert report["comparisons"]["actors"]["30006"]["candidate"]["active_fraction"] is None
    assert "candidate_actor_30006_activity_missing" in report["sufficiency_reasons"]


def test_nonattacking_healer_uses_hps_activity_and_survival_metrics() -> None:
    baseline = _summary(
        party_dps=100.0,
        actors={
            "30004": _nonattacking_healer(hps=50.0),
            "30006": _actor(dps=100.0),
        },
    )
    candidate = _summary(
        party_dps=100.0,
        actors={
            "30004": _nonattacking_healer(hps=49.0),
            "30006": _actor(dps=100.0),
        },
    )

    report = compare_optimization_acceptance(
        baseline, candidate, _setup(baseline, candidate), _repair()
    )

    healer = report["comparisons"]["actors"]["30004"]
    assert report["performance_verdict"] == "pass"
    assert healer["exact_hps_decline_pct"] == 2.0
    assert healer["baseline"]["offensive_metrics_required"] is False
    assert healer["baseline"]["target_switch_latency_ms"] is None


def test_blank_role_requires_reviewed_matched_setup_role_assertion() -> None:
    baseline_actors = {
        "30004": _nonattacking_healer(hps=50.0),
        "30006": _actor(dps=100.0),
    }
    candidate_actors = {
        "30004": _nonattacking_healer(hps=49.0),
        "30006": _actor(dps=100.0),
    }
    baseline_actors["30004"]["role"] = ""
    candidate_actors["30004"]["role"] = ""
    baseline = _summary(party_dps=100.0, actors=baseline_actors)
    candidate = _summary(party_dps=100.0, actors=candidate_actors)
    setup = _setup(baseline, candidate)

    without_role = compare_optimization_acceptance(
        baseline, candidate, setup, _repair()
    )
    assert without_role["performance_verdict"] == "inconclusive"
    assert "baseline_actor_30004_role_missing" in without_role["sufficiency_reasons"]

    setup["actor_roles"] = {
        "30004": {
            "baseline": "healer",
            "candidate": "healer",
            "evidence": ["loadout_database_readback.json#actor-30004"],
        }
    }
    with_role = compare_optimization_acceptance(
        baseline, candidate, setup, _repair()
    )
    assert with_role["performance_verdict"] == "pass"
    assert with_role["comparisons"]["actors"]["30004"]["baseline"][
        "role_basis"
    ] == "explicit_reviewed_setup_assertion"


def test_complete_no_target_switch_is_not_a_synthetic_zero_or_missing() -> None:
    baseline = _summary(party_dps=100.0)
    candidate = _summary(party_dps=100.0)
    for summary in (baseline, candidate):
        actor = summary["actors"]["30006"]
        actor["target_switch_latency_ms"] = []
        actor["target_switch_observation_complete"] = True

    report = compare_optimization_acceptance(
        baseline, candidate, _setup(baseline, candidate), _repair()
    )

    metric = report["comparisons"]["actors"]["30006"]
    assert report["performance_verdict"] == "pass"
    assert metric["baseline"]["target_switch_latency_ms"] is None
    assert metric["baseline"]["target_switch_opportunity_observed"] is False


def test_incomplete_target_switch_observation_remains_inconclusive() -> None:
    baseline = _summary(party_dps=100.0)
    candidate = _summary(party_dps=100.0)
    candidate["actors"]["30006"]["target_switch_latency_ms"] = []
    candidate["actors"]["30006"]["target_switch_observation_complete"] = False

    report = compare_optimization_acceptance(
        baseline, candidate, _setup(baseline, candidate), _repair()
    )

    assert report["performance_verdict"] == "inconclusive"
    assert "candidate_actor_30006_target_switch_latency_missing" in report[
        "sufficiency_reasons"
    ]


def test_missing_required_healer_hps_remains_inconclusive() -> None:
    actors = {
        "30004": _nonattacking_healer(hps=50.0),
        "30006": _actor(dps=100.0),
    }
    baseline = _summary(party_dps=100.0, actors=actors)
    candidate_actors = {
        "30004": _nonattacking_healer(hps=50.0),
        "30006": _actor(dps=100.0),
    }
    del candidate_actors["30004"]["effective_hps"]
    candidate = _summary(party_dps=100.0, actors=candidate_actors)

    report = compare_optimization_acceptance(
        baseline, candidate, _setup(baseline, candidate), _repair()
    )

    assert report["performance_verdict"] == "inconclusive"
    assert "candidate_actor_30004_exact_hps_missing" in report[
        "sufficiency_reasons"
    ]


def test_nominal_matched_pair_passes_with_single_pair_uncertainty() -> None:
    baseline = _summary(party_dps=100.0)
    candidate = _summary(
        party_dps=98.0,
        actors={
            "30006": _actor(
                dps=98.0,
                active_fraction=0.88,
                boss_dps=93.0,
                add_dps=5.0,
                latency_ms=102.0,
            )
        },
    )
    report = compare_optimization_acceptance(
        baseline,
        candidate,
        _setup(baseline, candidate),
        _repair(),
    )

    assert report["schema"] == OUTPUT_SCHEMA
    assert report["performance_verdict"] == "pass"
    assert report["performance_accepted"] is True
    assert report["diagnosis_required"] is False
    assert report["repair_edge_accepted"] is False
    assert report["fast_benchmark"]["matched_baseline"] is False
    assert report["threshold_interpretation"] == "diagnostic_triage_not_scientific_significance"


def test_prefinalization_report_source_is_verified_without_full_report_hash(
    tmp_path: Path,
) -> None:
    writer_report = _auto_report_source()
    write_capture_timeline(
        [{"evidence_channel": "other", "identity_binding": {"state": "bound"}}],
        writer_report,
        tmp_path / "capture.json",
        raw_sha256="b" * 64,
    )
    writer_summary = json.loads(
        (tmp_path / "capture.timeline-summary.json").read_text(encoding="utf-8")
    )
    assert writer_summary["identity"]["source"]["report_sha256"] is None

    baseline = _summary(party_dps=100.0)
    candidate = _summary(party_dps=99.0, actors={"30006": _actor(dps=99.0)})
    for summary in (baseline, candidate):
        summary["identity"]["source"] = writer_summary["identity"]["source"]

    report = compare_optimization_acceptance(
        baseline, candidate, _setup(baseline, candidate), _repair()
    )

    assert report["performance_verdict"] == "pass"
    assert not [
        reason for reason in report["sufficiency_reasons"]
        if "report_source" in reason or "raw_batch" in reason
    ]


def test_tampered_report_source_hash_is_inconclusive() -> None:
    baseline = _summary(party_dps=100.0)
    candidate = _summary(party_dps=100.0)
    candidate["identity"]["source"]["report_source"]["config_sha256"] = "5" * 64

    report = compare_optimization_acceptance(
        baseline, candidate, _setup(baseline, candidate), _repair()
    )

    assert report["performance_verdict"] == "inconclusive"
    assert "candidate_source_report_source_sha256_mismatch" in report["sufficiency_reasons"]


def test_intentional_source_change_is_bound_to_summary_identity() -> None:
    baseline = _summary(party_dps=100.0, source_commit="1" * 40)
    candidate = _summary(party_dps=100.0, source_commit="5" * 40)
    setup = _setup(baseline, candidate)
    setup["intentional_source_changes"][0]["candidate"] = "6" * 40

    report = compare_optimization_acceptance(
        baseline, candidate, setup, _repair()
    )

    assert report["performance_verdict"] == "inconclusive"
    assert (
        "intentional_source_change_0_candidate_summary_binding_mismatch"
        in report["sufficiency_reasons"]
    )


def test_undeclared_observed_source_change_is_inconclusive() -> None:
    baseline = _summary(party_dps=100.0, source_commit="1" * 40)
    candidate = _summary(party_dps=100.0, source_commit="5" * 40)
    setup = _setup(baseline, candidate)
    setup["intentional_source_changes"] = []

    report = compare_optimization_acceptance(
        baseline, candidate, setup, _repair()
    )

    assert report["performance_verdict"] == "inconclusive"
    assert "intentional_source_change_source_commit_undeclared" in report[
        "sufficiency_reasons"
    ]


def test_current_timeline_field_shapes_are_consumed() -> None:
    baseline = _summary(party_dps=100.0)
    candidate = _summary(party_dps=99.0, actors={"30006": _actor(dps=99.0)})
    for summary, latency in ((baseline, 100.0), (candidate, 103.0)):
        actor = summary["actors"]["30006"]
        actor["damage"]["dps"] = actor.pop("dps")["hostile_originated"]
        actor["target_switch_latency_ms"] = [
            {
                "start_ms": 50000,
                "end_ms": 50000 + latency,
                "latency_ms": latency,
                "boundary_provenance": "observed_target_transition_to_observed_landed",
            }
        ]
        actor["survival"] = {
            "first_activity_at_ms": 1000,
            "last_activity_at_ms": 101000,
            "death_observed_at_ms": None,
            "alive_at_end": True,
        }
        for phase in summary["phase_intervals"]:
            phase["start_ms"] = phase.pop("start_at_ms")
            phase["end_ms"] = phase.pop("end_at_ms")

    report = compare_optimization_acceptance(
        baseline, candidate, _setup(baseline, candidate), _repair()
    )

    assert report["performance_verdict"] == "pass"
    assert report["comparisons"]["actors"]["30006"][
        "target_switch_latency_increase_pct"
    ] == 3.0


def test_per_actor_loss_masked_by_party_gain_requires_diagnosis() -> None:
    baseline = _summary(
        party_dps=200.0,
        actors={
            "30006": _actor(dps=100.0),
            "30007": _actor(dps=100.0),
        },
    )
    candidate = _summary(
        party_dps=210.0,
        actors={
            "30006": _actor(dps=80.0, boss_dps=75.0),
            "30007": _actor(dps=130.0, boss_dps=125.0),
        },
    )

    report = compare_optimization_acceptance(
        baseline, candidate, _setup(baseline, candidate), _repair()
    )

    assert report["comparisons"]["party"]["decline_pct"] == -5.0
    assert report["performance_verdict"] == "fail"
    assert report["diagnosis_required"] is True
    assert "actor_30006_exact_dps_decline_pct_material" in report["material_decline_reasons"]


def test_lower_add_rate_alone_does_not_incentivize_damage_padding() -> None:
    baseline = _summary(
        party_dps=100.0,
        actors={"30006": _actor(dps=100.0, boss_dps=80.0, add_dps=20.0)},
    )
    candidate = _summary(
        party_dps=101.0,
        actors={"30006": _actor(dps=101.0, boss_dps=100.0, add_dps=1.0)},
    )

    report = compare_optimization_acceptance(
        baseline, candidate, _setup(baseline, candidate), _repair()
    )

    assert report["comparisons"]["actors"]["30006"]["add_dps_decline_pct"] == 95.0
    assert report["performance_verdict"] == "pass"
    assert not [
        reason for reason in report["material_decline_reasons"] if "add_dps" in reason
    ]


def test_add_gain_cannot_mask_material_boss_output_loss() -> None:
    baseline = _summary(
        party_dps=100.0,
        actors={"30006": _actor(dps=100.0, boss_dps=80.0, add_dps=20.0)},
    )
    candidate = _summary(
        party_dps=110.0,
        actors={"30006": _actor(dps=110.0, boss_dps=64.0, add_dps=46.0)},
    )

    report = compare_optimization_acceptance(
        baseline, candidate, _setup(baseline, candidate), _repair()
    )

    actor = report["comparisons"]["actors"]["30006"]
    assert actor["exact_dps_decline_pct"] == -10.0
    assert actor["boss_dps_decline_pct"] == 20.0
    assert actor["add_dps_decline_pct"] == -130.0
    assert report["performance_verdict"] == "fail"
    assert "actor_30006_boss_dps_decline_pct_material" in report[
        "material_decline_reasons"
    ]


def test_fixture_only_assertion_cannot_accept_repair() -> None:
    baseline = _summary(party_dps=100.0)
    candidate = _summary(party_dps=100.0)
    report = compare_optimization_acceptance(
        baseline,
        candidate,
        _setup(baseline, candidate),
        _repair(requested=True, evidence_class="fixture"),
    )

    assert report["clear_accepted"] is True
    assert report["repair_edge_accepted"] is False
    assert report["performance_verdict"] == "pass"
    assert "repair_assertion_0_evidence_class_not_attributable" in report["repair"]["reasons"]


def test_cli_writes_report_and_returns_performance_exit_code(tmp_path: Path) -> None:
    baseline = _summary(party_dps=100.0)
    candidate = _summary(party_dps=99.0, actors={"30006": _actor(dps=99.0)})
    inputs = {
        "baseline": baseline,
        "candidate": candidate,
        "setup": _setup(baseline, candidate),
        "repair": _repair(),
    }
    paths: dict[str, Path] = {}
    for name, value in inputs.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path
    output = tmp_path / "acceptance.json"

    exit_code = main(
        [
            "--baseline", str(paths["baseline"]),
            "--candidate", str(paths["candidate"]),
            "--matched-setup", str(paths["setup"]),
            "--repair-assertions", str(paths["repair"]),
            "--output", str(output),
        ]
    )

    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["performance_verdict"] == "pass"
    assert report["clear_accepted"] is True
