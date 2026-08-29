from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tools.raid_program.blocker_recurrence_ledger import (
    _command_sha256,
    _canonical_config_identity,
    _evaluate_regression_bank,
    _ledger_with_suite_receipt,
    _manifest_sha256,
    _result_sha256,
    _run_suite,
    _sha256,
    _verify_clean_source_identity,
    evaluate_ledger,
)


CANONICAL_CONFIG_IDENTITY = _canonical_config_identity()


def _ledger(
    runs: list[dict], *, limit: int = 10, signatures: dict | None = None
) -> dict:
    ledger = {
        "schema": "trinity_raid_blocker_recurrence_v1",
        "occurrence_limit": limit,
        "clear_streak_required": 2,
        "runs": runs,
    }
    if signatures is not None:
        ledger["causal_signatures"] = signatures
    return ledger


def _bank_ledger(
    runs: list[dict],
    *,
    fixtures: list[dict],
    verifications: list[dict],
    history: list[str] | None = None,
    source: str = "source-current",
    config: str = CANONICAL_CONFIG_IDENTITY,
    signatures: dict | None = None,
) -> dict:
    ledger = _ledger(runs, signatures=signatures or {"edge": {}})
    ledger["route"] = "route"
    ledger["regression_bank"] = {
        "schema": "trinity_raid_regression_bank_v1",
        "route": "route",
        "current_identity": {"source": source, "config": config},
        "fixture_history": history if history is not None else [
            row["fixture_id"] for row in fixtures
        ],
        "fixtures": fixtures,
        "verifications": verifications,
    }
    return ledger


def _fixture(fixture_id: str, signature: str = "edge") -> dict:
    return {
        "fixture_id": fixture_id,
        "revision": 1,
        "causal_signature": signature,
        "command": ["pixi", "run", "pytest", "-q", f"tests/{fixture_id}.py"],
    }


def _pass(fixture_id: str, run_id: str, revision: int = 1, **identity: str) -> dict:
    return {
        "fixture_id": fixture_id,
        "fixture_revision": revision,
        "status": "passed",
        "passed_before_run_id": run_id,
        "source": identity.get("source", "source-current"),
        "config": identity.get("config", CANONICAL_CONFIG_IDENTITY),
        "evidence": f"tests/{fixture_id}.py",
    }


def test_intervening_absence_does_not_erase_recurring_blocker() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "101", "route_completed": False, "blockers": {"drudge_contamination": "occurred"}},
                {"run_id": "102", "route_completed": False, "blockers": {"drudge_contamination": "absent"}},
                {"run_id": "103", "route_completed": False, "blockers": {"drudge_contamination": "occurred"}},
            ]
        )
    )

    blocker = decision["blockers"][0]
    assert blocker["occurrence_count"] == 2
    assert blocker["occurrence_run_ids"] == ["101", "103"]
    assert blocker["open"] is True
    assert decision["acceptance_admitted"] is False


def test_only_two_completed_clean_routes_close_open_blocker() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "101", "route_completed": False, "blockers": {"hazard_path": "occurred"}},
                {"run_id": "102", "route_completed": False, "blockers": {"hazard_path": "absent"}},
                {"run_id": "103", "route_completed": True, "blockers": {"hazard_path": "absent"}},
                {"run_id": "104", "route_completed": True, "blockers": {"hazard_path": "absent"}},
            ]
        )
    )

    assert decision["blockers"][0]["clean_full_clear_streak"] == 2
    assert decision["blockers"][0]["open"] is False
    assert decision["acceptance_admitted"] is True


def test_tenth_interleaved_occurrence_requires_stop() -> None:
    runs = []
    for index in range(19):
        runs.append(
            {
                "run_id": str(index + 1),
                "route_completed": False,
                "blockers": {
                    "parasite_lane_oscillation": (
                        "occurred" if index % 2 == 0 else "absent"
                    )
                },
            }
        )
    decision = evaluate_ledger(_ledger(runs))

    assert decision["blockers"][0]["occurrence_count"] == 10
    assert decision["stop_required"] is True
    assert decision["required_next_action"] == "stop_and_summarize_last_ten_occurrences"


def test_unassessed_signature_cannot_count_as_clean() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "101", "route_completed": False, "blockers": {"pet_autocast_spam": "occurred"}},
                {"run_id": "102", "route_completed": True, "blockers": {}},
                {"run_id": "103", "route_completed": True, "blockers": {"pet_autocast_spam": "absent"}},
            ]
        )
    )

    assert decision["blockers"][0]["clean_full_clear_streak"] == 1
    assert decision["acceptance_admitted"] is False


def test_next_signature_prefers_most_recurrent_edge() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "101", "blockers": {"rare_edge": "occurred", "recurring_edge": "occurred"}},
                {"run_id": "102", "blockers": {"rare_edge": "absent", "recurring_edge": "occurred"}},
                {"run_id": "103", "blockers": {"rare_edge": "occurred", "recurring_edge": "occurred"}},
            ]
        )
    )

    assert decision["next_causal_signature"] == "recurring_edge"


def test_latest_absent_open_signature_does_not_steal_repair_priority() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "101", "blockers": {"old_edge": "occurred"}},
                {"run_id": "102", "blockers": {"old_edge": "occurred"}},
                {
                    "run_id": "103",
                    "blockers": {"old_edge": "absent", "live_edge": "occurred"},
                },
            ]
        )
    )

    old_edge = next(
        row for row in decision["blockers"]
        if row["causal_signature"] == "old_edge"
    )
    assert old_edge["open"] is True
    assert old_edge["last_observed_state"] == "absent"
    assert decision["next_causal_signature"] == "live_edge"
    assert decision["required_next_action"] == "repair_latest_recurring_causal_signature"


def test_open_signatures_latest_absent_require_clean_full_clear_not_repair() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "101", "blockers": {"intermittent_edge": "occurred"}},
                {"run_id": "102", "blockers": {"intermittent_edge": "absent"}},
            ]
        )
    )

    blocker = decision["blockers"][0]
    assert blocker["open"] is True
    assert blocker["last_observed_run_id"] == "102"
    assert blocker["last_observed_state"] == "absent"
    assert decision["next_causal_signature"] is None
    assert decision["required_next_action"] == "run_clean_full_clear"


def test_rejects_duplicate_run_identity_and_unknown_state() -> None:
    with pytest.raises(ValueError, match="duplicate run_id"):
        evaluate_ledger(
            _ledger(
                [
                    {"run_id": "same", "blockers": {}},
                    {"run_id": "same", "blockers": {}},
                ]
            )
        )
    with pytest.raises(ValueError, match="invalid state"):
        evaluate_ledger(
            _ledger(
                [{"run_id": "one", "blockers": {"edge": "fixed"}}]
            )
        )


def test_child_recurrence_rolls_up_to_parent_once_per_run() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {
                    "run_id": "101",
                    "blockers": {"floor_probe": "occurred", "endpoint_z": "occurred"},
                },
                {"run_id": "102", "blockers": {"endpoint_z": "occurred"}},
            ],
            signatures={
                "native_path_proof": {},
                "floor_probe": {"parent": "native_path_proof"},
                "endpoint_z": {"parent": "native_path_proof"},
            },
        )
    )

    parent = next(
        row for row in decision["blockers"]
        if row["causal_signature"] == "native_path_proof"
    )
    assert parent["occurrence_count"] == 2
    assert parent["occurrence_run_ids"] == ["101", "102"]


def test_completed_architecture_review_preserves_history_but_reopens_budget() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": str(index), "blockers": {"shared_edge": "occurred"}}
                for index in range(1, 12)
            ],
            signatures={
                "shared_edge": {
                    "architecture_reviewed_through_occurrence_count": 10,
                }
            },
        )
    )

    blocker = decision["blockers"][0]
    assert blocker["occurrence_count"] == 11
    assert blocker["architecture_reviewed_through_occurrence_count"] == 10
    assert blocker["unreviewed_occurrence_count"] == 1
    assert blocker["stop_required"] is False
    assert blocker["open"] is True


def test_live_recurrence_after_fixture_pass_stops_repairs_and_canaries() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "109", "blockers": {"parasite": "occurred"}},
                {"run_id": "110", "blockers": {"parasite": "occurred"}},
            ],
            signatures={
                "parasite": {
                    "architecture_reviewed_through_occurrence_count": 1,
                    "fixture_verifications": [
                        {
                            "passed_before_run_id": "110",
                            "evidence": "tests/parasite_replay.cpp::full_sequence",
                        }
                    ],
                }
            },
        )
    )

    blocker = decision["blockers"][0]
    assert blocker["unreviewed_occurrence_count"] == 1
    assert blocker["recurrence_limit_stop"] is False
    assert blocker["retained_fixture_invalidated"] is True
    assert blocker["live_occurrences_after_fixture"] == ["110"]
    assert decision["stop_required"] is True
    assert decision["next_causal_signature"] == "parasite"
    assert decision["required_next_action"] == "expand_invalid_retained_fixture"


def test_fixture_verification_must_reference_a_known_run_and_evidence() -> None:
    with pytest.raises(ValueError, match="unknown boundary run_id"):
        evaluate_ledger(
            _ledger(
                [{"run_id": "110", "blockers": {"parasite": "occurred"}}],
                signatures={
                    "parasite": {
                        "fixture_verifications": [
                            {
                                "passed_before_run_id": "missing",
                                "evidence": "tests/parasite_replay.cpp",
                            }
                        ]
                    }
                },
            )
        )


def test_expanded_fixture_after_recurrence_reopens_only_clean_canary_gate() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "109", "blockers": {"parasite": "occurred"}},
                {"run_id": "110", "blockers": {"parasite": "occurred"}},
            ],
            signatures={
                "parasite": {
                    "fixture_verifications": [
                        {
                            "passed_before_run_id": "110",
                            "evidence": "tests/endpoint_only.cpp",
                        },
                        {
                            "passed_after_run_id": "110",
                            "evidence": "tests/full_integration.cpp",
                        },
                    ]
                }
            },
        )
    )

    blocker = decision["blockers"][0]
    assert blocker["retained_fixture_invalidated"] is False
    assert blocker["fixture_verified_after_latest_occurrence"] is True
    assert decision["stop_required"] is False
    assert decision["next_causal_signature"] is None
    assert decision["required_next_action"] == "run_clean_full_clear"


def test_declared_signature_cannot_be_omitted_from_the_decision() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "101", "route_completed": True, "blockers": {}},
                {"run_id": "102", "route_completed": True, "blockers": {}},
            ],
            signatures={"earlier_edge": {}},
        )
    )

    assert [row["causal_signature"] for row in decision["blockers"]] == [
        "earlier_edge"
    ]
    assert decision["blockers"][0]["last_observed_state"] == "not_exercised"


def test_accumulated_bank_reports_fixture_omitted_by_later_repair() -> None:
    decision = evaluate_ledger(
        _bank_ledger(
            [
                {"run_id": "101", "route_completed": True, "blockers": {"edge": "absent"}},
                {"run_id": "102", "route_completed": True, "blockers": {"edge": "absent"}},
            ],
            fixtures=[_fixture("original"), _fixture("later_repair")],
            history=["original", "later_repair"],
            verifications=[_pass("later_repair", "101")],
        ),
        current_identity={"source_identity": "source-current", "config_identity": CANONICAL_CONFIG_IDENTITY},
        suite_receipt_verified=True,
    )

    assert decision["missing_fixture_ids"] == ["original"]
    assert decision["regression_bank"]["expected_fixture_ids"] == [
        "later_repair",
        "original",
    ]
    assert decision["canary_admitted"] is False
    assert decision["build_admitted"] is False


def test_bank_requires_fixture_coverage_for_every_occurred_signature() -> None:
    decision = evaluate_ledger(
        _bank_ledger(
            [
                {
                    "run_id": "101",
                    "route_completed": False,
                    "blockers": {"edge": "occurred", "uncovered_edge": "occurred"},
                },
            ],
            fixtures=[_fixture("original")],
            verifications=[_pass("original", "101")],
            signatures={"edge": {}, "uncovered_edge": {}},
        ),
        current_identity={"source_identity": "source-current", "config_identity": CANONICAL_CONFIG_IDENTITY},
        suite_receipt_verified=True,
    )

    assert decision["missing_causal_signature_ids"] == ["uncovered_edge"]
    assert decision["regression_bank"]["admitted"] is False
    assert decision["canary_admitted"] is False


def test_bank_rejects_pass_tied_to_stale_source_or_config_identity() -> None:
    decision = evaluate_ledger(
        _bank_ledger(
            [
                {"run_id": "101", "route_completed": True, "blockers": {"edge": "absent"}},
                {"run_id": "102", "route_completed": True, "blockers": {"edge": "absent"}},
            ],
            fixtures=[_fixture("original")],
            verifications=[
                _pass("original", "101", source="source-old", config="config-old")
            ],
        ),
        current_identity={"source_identity": "source-current", "config_identity": CANONICAL_CONFIG_IDENTITY},
        suite_receipt_verified=True,
    )

    assert decision["stale_fixture_ids"] == ["original"]
    assert decision["missing_fixture_ids"] == []
    assert decision["regression_bank"]["admitted"] is False
    assert decision["canary_admitted"] is False


def test_enabled_bank_requires_external_identity_instead_of_ledger_identity() -> None:
    decision = evaluate_ledger(
        _bank_ledger(
            [
                {"run_id": "101", "route_completed": True, "blockers": {"edge": "absent"}},
                {"run_id": "102", "route_completed": True, "blockers": {"edge": "absent"}},
            ],
            fixtures=[_fixture("original")],
            verifications=[_pass("original", "101")],
        )
    )

    assert decision["regression_bank"]["admitted"] is False
    assert "current_identity_external_required" in decision["regression_bank"]["route_failures"]
    assert decision["canary_admitted"] is False


def test_external_source_identity_does_not_require_a_self_referential_ledger_sha() -> None:
    ledger = _bank_ledger(
        [
            {"run_id": "101", "route_completed": True, "blockers": {"edge": "absent"}},
            {"run_id": "102", "route_completed": True, "blockers": {"edge": "absent"}},
        ],
        fixtures=[_fixture("original")],
        verifications=[_pass("original", "101", source="external-clean-head")],
    )
    ledger["regression_bank"]["current_identity"].pop("source")
    identity = {"source_identity": "external-clean-head", "config_identity": CANONICAL_CONFIG_IDENTITY}

    decision = evaluate_ledger(
        ledger, current_identity=identity, suite_receipt_verified=True
    )
    assert decision["regression_bank"]["admitted"] is True


def test_enabled_bank_direct_api_requires_explicit_suite_verification() -> None:
    ledger = _bank_ledger(
        [
            {"run_id": "101", "route_completed": True, "blockers": {"edge": "absent"}},
            {"run_id": "102", "route_completed": True, "blockers": {"edge": "absent"}},
        ],
        fixtures=[_fixture("original")],
        verifications=[_pass("original", "101")],
    )
    identity = {
        "source_identity": "source-current",
        "config_identity": CANONICAL_CONFIG_IDENTITY,
    }

    decision = evaluate_ledger(ledger, current_identity=identity)

    assert decision["regression_bank"]["admitted"] is False
    assert "suite_receipt_verification_required" in decision["regression_bank"]["route_failures"]
    assert decision["build_admitted"] is False


def test_direct_regression_bank_api_requires_explicit_suite_verification() -> None:
    ledger = _bank_ledger(
        [
            {"run_id": "101", "route_completed": True, "blockers": {"edge": "absent"}},
            {"run_id": "102", "route_completed": True, "blockers": {"edge": "absent"}},
        ],
        fixtures=[_fixture("original")],
        verifications=[_pass("original", "101")],
    )
    result = _evaluate_regression_bank(
        ledger,
        {"edge": {}},
        ledger["runs"],
        {"101": 0, "102": 1},
        supplied_identity={
            "source_identity": "source-current",
            "config_identity": CANONICAL_CONFIG_IDENTITY,
        },
    )

    assert result["admitted"] is False
    assert "suite_receipt_verification_required" in result["route_failures"]


def test_direct_api_rejects_arbitrary_config_identity() -> None:
    ledger = _bank_ledger(
        [
            {"run_id": "101", "route_completed": True, "blockers": {"edge": "absent"}},
            {"run_id": "102", "route_completed": True, "blockers": {"edge": "absent"}},
        ],
        fixtures=[_fixture("original")],
        verifications=[_pass("original", "101", config="forged-config")],
        config="forged-config",
    )
    identity = {
        "source_identity": "source-current",
        "config_identity": "forged-config",
    }

    decision = evaluate_ledger(
        ledger,
        current_identity=identity,
        suite_receipt_verified=True,
    )

    assert decision["regression_bank"]["admitted"] is False
    assert "current_identity_config_not_canonical" in decision["regression_bank"]["route_failures"]


def test_source_identity_requires_exact_clean_tracked_checkout(tmp_path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Regression Test"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("clean\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    _verify_clean_source_identity(tmp_path, head)
    (tmp_path / "untracked.txt").write_text("ignored\n")
    _verify_clean_source_identity(tmp_path, head)
    with pytest.raises(ValueError, match="does not match current HEAD"):
        _verify_clean_source_identity(tmp_path, "stale-source")

    tracked.write_text("dirty\n")
    with pytest.raises(ValueError, match="tracked worktree is dirty"):
        _verify_clean_source_identity(tmp_path, head)


def test_suite_receipt_is_bound_to_manifest_and_current_identity(tmp_path) -> None:
    ledger = _bank_ledger(
        [
            {"run_id": "101", "route_completed": True, "blockers": {"edge": "absent"}},
            {"run_id": "102", "route_completed": True, "blockers": {"edge": "absent"}},
        ],
        fixtures=[_fixture("original")],
        verifications=[],
    )
    identity = {"source_identity": "source-current", "config_identity": CANONICAL_CONFIG_IDENTITY}
    fixture = ledger["regression_bank"]["fixtures"][0]
    fixture["command"] = [sys.executable, "-c", "print('fixture-pass')"]
    receipt_path = tmp_path / "suite-receipt.json"
    _run_suite(ledger, identity, "101", "after", receipt_path)
    receipt = json.loads(receipt_path.read_text())

    effective = _ledger_with_suite_receipt(ledger, receipt_path, identity)
    decision = evaluate_ledger(
        effective, current_identity=identity, suite_receipt_verified=True
    )
    assert decision["regression_bank"]["admitted"] is True

    forged = json.loads(receipt_path.read_text())
    forged_row = forged["verifications"][0]
    forged_row["stdout_sha256"] = _sha256("forged-output\n")
    forged_row["result_sha256"] = _result_sha256(
        forged_row["returncode"],
        forged_row["timed_out"],
        forged_row["stdout_sha256"],
        forged_row["stderr_sha256"],
    )
    forged_path = tmp_path / "forged-output-receipt.json"
    forged_path.write_text(json.dumps(forged))
    forged_effective = _ledger_with_suite_receipt(ledger, forged_path, identity)
    verified = forged_effective["regression_bank"]["verifications"][-1]
    assert verified["stdout_sha256"] == _sha256("fixture-pass\n")
    assert verified["stdout_sha256"] != forged_row["stdout_sha256"]

    wrong_source = dict(receipt)
    wrong_source["source_identity"] = "source-other"
    wrong_source_path = tmp_path / "wrong-source-receipt.json"
    wrong_source_path.write_text(json.dumps(wrong_source))
    with pytest.raises(ValueError, match="source identity mismatch"):
        _ledger_with_suite_receipt(ledger, wrong_source_path, identity)

    ledger["regression_bank"]["fixtures"][0]["command"] = ["changed"]
    with pytest.raises(ValueError, match="manifest identity mismatch"):
        _ledger_with_suite_receipt(ledger, receipt_path, identity)


def test_external_receipt_cannot_forge_a_failing_fixture_pass(tmp_path) -> None:
    fixture = _fixture("original")
    fixture["command"] = [sys.executable, "-c", "raise SystemExit(7)"]
    ledger = _bank_ledger(
        [{"run_id": "101", "route_completed": False, "blockers": {"edge": "occurred"}}],
        fixtures=[fixture],
        verifications=[],
    )
    identity = {
        "source_identity": "source-current",
        "config_identity": CANONICAL_CONFIG_IDENTITY,
    }
    receipt_path = tmp_path / "failing-receipt.json"
    _run_suite(ledger, identity, "101", "after", receipt_path)
    forged = json.loads(receipt_path.read_text())
    row = forged["verifications"][0]
    row.update({
        "passed": True,
        "returncode": 0,
        "timed_out": False,
        "stdout_sha256": _sha256("forged-pass"),
        "stderr_sha256": _sha256(""),
    })
    row["result_sha256"] = _result_sha256(
        row["returncode"], row["timed_out"], row["stdout_sha256"], row["stderr_sha256"]
    )
    receipt_path.write_text(json.dumps(forged))

    effective = _ledger_with_suite_receipt(ledger, receipt_path, identity)
    verified = effective["regression_bank"]["verifications"][-1]
    decision = evaluate_ledger(
        effective, current_identity=identity, suite_receipt_verified=True
    )

    assert verified["passed"] is False
    assert verified["returncode"] == 7
    assert decision["regression_bank"]["admitted"] is False


def test_run_suite_executes_fixed_argv_and_emits_verifiable_receipt(tmp_path) -> None:
    fixture = _fixture("original")
    fixture["command"] = [sys.executable, "-c", "print('fixture-pass')"]
    ledger = _bank_ledger(
        [
            {"run_id": "101", "route_completed": True, "blockers": {"edge": "absent"}},
            {"run_id": "102", "route_completed": True, "blockers": {"edge": "absent"}},
        ],
        fixtures=[fixture],
        verifications=[],
    )
    identity = {"source_identity": "source-current", "config_identity": CANONICAL_CONFIG_IDENTITY}
    receipt_path = tmp_path / "suite-receipt.json"

    _run_suite(ledger, identity, "101", "after", receipt_path)
    receipt = json.loads(receipt_path.read_text())
    assert receipt["fixture_ids"] == ["original"]
    assert receipt["verifications"][0]["passed"] is True
    effective = _ledger_with_suite_receipt(ledger, receipt_path, identity)
    assert evaluate_ledger(
        effective, current_identity=identity, suite_receipt_verified=True
    )["canary_admitted"] is True


def test_post_occurrence_suite_pass_admits_next_canary_before_two_clears() -> None:
    verification = _pass("original", "101", revision=2)
    verification.pop("passed_before_run_id")
    verification["passed_after_run_id"] = "102"
    ledger = _bank_ledger(
        [
            {"run_id": "101", "route_completed": False, "blockers": {"edge": "occurred"}},
            {"run_id": "102", "route_completed": False, "blockers": {"edge": "occurred"}},
        ],
        fixtures=[{**_fixture("original"), "revision": 2}],
        verifications=[verification],
    )
    identity = {"source_identity": "source-current", "config_identity": CANONICAL_CONFIG_IDENTITY}

    provisional = evaluate_ledger(
        ledger, current_identity=identity, suite_receipt_verified=True
    )
    assert provisional["build_admitted"] is True
    assert provisional["canary_admitted"] is True
    assert provisional["acceptance_admitted"] is False

    ledger["runs"].extend(
        [
            {"run_id": "103", "route_completed": True, "blockers": {"edge": "absent"}},
            {"run_id": "104", "route_completed": True, "blockers": {"edge": "absent"}},
        ]
    )
    final = evaluate_ledger(
        ledger, current_identity=identity, suite_receipt_verified=True
    )
    assert final["canary_admitted"] is True
    assert final["acceptance_admitted"] is True


def test_unchanged_fixture_rerun_after_recurrence_does_not_admit_canary() -> None:
    before = _pass("original", "101")
    after = _pass("original", "102")
    after.pop("passed_before_run_id")
    after["passed_after_run_id"] = "102"
    decision = evaluate_ledger(
        _bank_ledger(
            [
                {"run_id": "101", "route_completed": False,
                 "blockers": {"edge": "occurred"}},
                {"run_id": "102", "route_completed": False,
                 "blockers": {"edge": "occurred"}},
            ],
            fixtures=[_fixture("original")],
            verifications=[before, after],
        ),
        current_identity={
            "source_identity": "source-current",
            "config_identity": CANONICAL_CONFIG_IDENTITY,
        },
        suite_receipt_verified=True,
    )

    assert decision["canary_admitted"] is False
    assert decision["invalidated_fixture_ids"] == ["original"]
    assert decision["required_next_action"] == "expand_invalid_retained_fixture"


@pytest.mark.parametrize(
    ("verification_boundary", "expected_action"),
    [
        ({"passed_before_run_id": "102"}, "expand_invalid_retained_fixture"),
        ({"passed_after_run_id": "102"}, "run_clean_full_clear"),
    ],
)
def test_same_run_recurrence_is_invalidated_only_before_expanded_pass(
    verification_boundary: dict[str, str], expected_action: str
) -> None:
    verification = _pass("original", "101")
    verification.pop("passed_before_run_id")
    verification.update(verification_boundary)
    if "passed_after_run_id" in verification_boundary:
        verification = [
            _pass("original", "101"),
            {**verification, "fixture_revision": 2},
        ]
    else:
        verification = [verification]
    decision = evaluate_ledger(
        _bank_ledger(
            [
                {"run_id": "101", "route_completed": False, "blockers": {"edge": "occurred"}},
                {"run_id": "102", "route_completed": False, "blockers": {"edge": "occurred"}},
            ],
            fixtures=[{
                **_fixture("original"),
                "revision": 2 if "passed_after_run_id" in verification_boundary else 1,
            }],
            verifications=verification,
        ),
        current_identity={
            "source_identity": "source-current",
            "config_identity": CANONICAL_CONFIG_IDENTITY,
        },
        suite_receipt_verified=True,
    )

    if "passed_before_run_id" in verification_boundary:
        assert decision["invalidated_fixture_ids"] == ["original"]
        assert decision["required_next_action"] == expected_action
    else:
        assert decision["invalidated_fixture_ids"] == []
        assert decision["regression_bank"]["admitted"] is True


def test_later_recurrence_invalidates_the_latest_retained_fixture_pass() -> None:
    decision = evaluate_ledger(
        _bank_ledger(
            [
                {"run_id": "101", "route_completed": False, "blockers": {"edge": "occurred"}},
                {"run_id": "102", "route_completed": False, "blockers": {"edge": "absent"}},
                {"run_id": "103", "route_completed": False, "blockers": {"edge": "occurred"}},
            ],
            fixtures=[_fixture("original")],
            verifications=[
                {
                    **{
                        key: value
                        for key, value in _pass("original", "101").items()
                        if key != "passed_before_run_id"
                    },
                    "passed_after_run_id": "102",
                }
            ],
        ),
        current_identity={
            "source_identity": "source-current",
            "config_identity": CANONICAL_CONFIG_IDENTITY,
        },
        suite_receipt_verified=True,
    )

    assert decision["invalidated_fixture_ids"] == ["original"]
    assert decision["regression_bank"]["invalidation_run_ids"] == {
        "original": ["103"]
    }
    assert decision["canary_admitted"] is False


def test_all_accumulated_fixtures_pass_for_current_identity_before_canary() -> None:
    decision = evaluate_ledger(
        _bank_ledger(
            [
                {"run_id": "101", "route_completed": True, "blockers": {"edge": "absent"}},
                {"run_id": "102", "route_completed": True, "blockers": {"edge": "absent"}},
            ],
            fixtures=[_fixture("original"), _fixture("later_repair")],
            verifications=[_pass("original", "101"), _pass("later_repair", "101")],
        ),
        current_identity={
            "source_identity": "source-current",
            "config_identity": CANONICAL_CONFIG_IDENTITY,
        },
        suite_receipt_verified=True,
    )

    assert decision["regression_bank"]["suite_verified_fixture_ids"] == [
        "later_repair",
        "original",
    ]
    assert decision["regression_bank"]["admitted"] is True
    assert decision["build_admitted"] is True
    assert decision["canary_admitted"] is True
    assert decision["acceptance_admitted"] is True
