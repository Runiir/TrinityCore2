from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

import tools.raid_program.chainwielder_prestart_bundle as bundle
from tools.raid_program.blocker_recurrence_ledger import (
    _canonical_config_identity,
    _command_sha256,
    _manifest_sha256,
    _result_sha256,
    _sha256,
)
from tools.raid_program.prestart_bundle_dialects import (
    MAGMAW_TRANSFER_FIXTURE_COMMAND,
    MAGMAW_TRANSFER_FIXTURE_REVISION,
    MAGMAW_TRANSFER_LEDGER_RELATIVE_PATH,
    MAGMAW_TRANSFER_ROUTE_NODE_IDS,
)
from tools.raid_program.recurrence_admission import (
    MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID,
    MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
    MAGMAW_TRANSFER_CHECKPOINT_CONFIG_PREFIX,
    MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
    MAGMAW_TRANSFER_CHECKPOINT_PROBE,
    sha256_file,
)
from tests.test_chainwielder_prestart_bundle import (
    _create,
    _fixture,
    _git,
    _restage_base_runtime_config,
    _write_json,
)


@pytest.fixture(autouse=True)
def _stub_build_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bundle,
        "_verify_gate_bearing_build_receipt",
        lambda _receipt, _policy: {"valid": True, "gate_bearing": True},
    )


def _mutate_transfer_ledger(value: dict[str, object], mutation: str) -> None:
    bank = value["regression_bank"]
    assert isinstance(bank, dict)
    fixture_rows = bank["fixtures"]
    assert isinstance(fixture_rows, list)
    fixture_row = fixture_rows[0]
    assert isinstance(fixture_row, dict)
    runs = value["runs"]
    assert isinstance(runs, list)
    if mutation == "stale_revision":
        fixture_row["revision"] = 1
    elif mutation == "altered_command":
        fixture_row["command"] = MAGMAW_TRANSFER_FIXTURE_COMMAND[:-1]
    elif mutation == "missing_first_run":
        value["runs"] = runs[1:]
    elif mutation == "reordered_runs":
        runs.reverse()
    elif mutation == "forged_retained_run":
        retained = runs[1]
        assert isinstance(retained, dict)
        admission = retained["admission"]
        assert isinstance(admission, dict)
        admission["source_identity"] = "forged"
    elif mutation == "wrong_fixture":
        fixture_row["fixture_id"] = "foreign_fixture"
    elif mutation == "extra_fixture":
        fixture_rows.append(dict(fixture_row))
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(mutation)


def _transfer_fixture(
    tmp_path: Path, *, ledger_mutation: str | None = None,
    historical_snapshot: bool = True,
) -> dict[str, object]:
    fixture = _fixture(tmp_path)
    root = fixture["root"]
    probe = root / MAGMAW_TRANSFER_CHECKPOINT_PROBE
    probe.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        Path(__file__).resolve().parents[1] / MAGMAW_TRANSFER_CHECKPOINT_PROBE,
        probe,
    )
    ledger = root / MAGMAW_TRANSFER_LEDGER_RELATIVE_PATH
    shutil.copyfile(
        Path(__file__).resolve().parents[1]
        / MAGMAW_TRANSFER_LEDGER_RELATIVE_PATH,
        ledger,
    )
    if historical_snapshot:
        ledger_value = json.loads(ledger.read_text(encoding="utf-8"))
        fixture_row = ledger_value["regression_bank"]["fixtures"][0]
        fixture_row["evidence_boundary"] = "observation_only"
        fixture_row["verification_status"] = (
            "recorded_terrain_projection_counterexample_passes_hardened_"
            "value_verifier_postfix_live_boundary_pending"
        )
        fixture_row.pop("production_evidence", None)
        ledger_value["regression_bank"]["verifications"] = []
        ledger_value["causal_signatures"][
            "magmaw_transfer_lane_map_bound_checkpoint_missing"
        ]["fixture_status"] = "observation_only_production_boundary_pending"
        ledger_value["runs"] = ledger_value["runs"][:2]
        _write_json(ledger, ledger_value)
    if ledger_mutation is not None:
        ledger_value = json.loads(ledger.read_text(encoding="utf-8"))
        _mutate_transfer_ledger(ledger_value, ledger_mutation)
        _write_json(ledger, ledger_value)
    _git(root, "add", MAGMAW_TRANSFER_CHECKPOINT_PROBE.as_posix())
    _git(root, "add", MAGMAW_TRANSFER_LEDGER_RELATIVE_PATH.as_posix())
    _git(root, "commit", "-m", "track transfer inputs")
    fixture["paths"]["ledger"] = ledger

    decision = fixture["paths"]["decision"]
    _write_json(decision, {
        "build_admitted": False,
        "canary_admitted": False,
        "fixture_expansion_admitted": True,
        "fixture_expansion_target_ids": [MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID],
        "fixture_expansion_requests": [],
        "invalidated_fixture_ids": [],
        "failing_fixture_ids": [],
        "missing_fixture_ids": [],
        "pending_fixture_ids": [MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID],
        "stale_fixture_ids": [],
    })
    suite = fixture["paths"]["suite_receipt"]
    ledger_value = json.loads(ledger.read_text(encoding="utf-8"))
    command = ledger_value["regression_bank"]["fixtures"][0]["command"]
    source_identity = _git(root, "rev-parse", "HEAD")
    config_identity = _canonical_config_identity()
    stdout_sha256 = _sha256("transfer checkpoint suite passed\n")
    stderr_sha256 = _sha256("")
    _write_json(suite, {
        "schema": "trinity_raid_regression_suite_receipt_v1",
        "source_identity": source_identity,
        "config_identity": config_identity,
        "manifest_sha256": _manifest_sha256(ledger_value["regression_bank"]),
        "fixture_ids": [MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID],
        "verifications": [{
            "fixture_id": MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
            "fixture_revision": MAGMAW_TRANSFER_FIXTURE_REVISION,
            "passed": True,
            "returncode": 0,
            "timed_out": False,
            "command_sha256": _command_sha256(command),
            "stdout_sha256": stdout_sha256,
            "stderr_sha256": stderr_sha256,
            "result_sha256": _result_sha256(
                0, False, stdout_sha256, stderr_sha256,
            ),
            "source_identity": source_identity,
            "config_identity": config_identity,
            "passed_after_run_id": ledger_value["runs"][-1]["run_id"],
        }],
    })
    fixture["kwargs"].update({
        "source_commit": _git(root, "rev-parse", "HEAD"),
        "source_tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "actor_guid": MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID,
        "checkpoint_fixture_id": MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
        "checkpoint_case_id": MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
        "ledger": ledger,
        "ledger_sha256": sha256_file(ledger),
        "decision_sha256": sha256_file(decision),
        "suite_receipt_sha256": sha256_file(suite),
    })
    receipt = fixture["paths"]["build_receipt"]
    receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
    receipt_value["commit"] = fixture["kwargs"]["source_commit"]
    source_snapshot = {
        "commit": fixture["kwargs"]["source_commit"],
        "tree": fixture["kwargs"]["source_tree"],
        "clean": True,
        "dirty": False,
        "porcelain_sha256": _sha256(""),
    }
    receipt_value["source_identity"] = {
        stage: dict(source_snapshot)
        for stage in ("request", "admission", "completion")
    }
    _write_json(receipt, receipt_value)
    suite_value = json.loads(suite.read_text(encoding="utf-8"))
    suite_value["source_identity"] = fixture["kwargs"]["source_commit"]
    _write_json(suite, suite_value)
    fixture["kwargs"]["build_receipt_sha256"] = sha256_file(receipt)
    fixture["kwargs"]["suite_receipt_sha256"] = sha256_file(suite)
    _restage_base_runtime_config(fixture)
    return fixture


def test_promoted_canonical_ledger_is_rejected_by_retired_expansion_path(
    tmp_path: Path,
) -> None:
    fixture = _transfer_fixture(tmp_path, historical_snapshot=False)
    with pytest.raises(
        bundle.BundleError, match="magmaw_transfer_ledger_manifest_mismatch",
    ):
        _create(fixture)
    assert not fixture["output"].exists()


def test_exact_transfer_dialect_composes_and_verifies_atomically(
    tmp_path: Path,
) -> None:
    fixture = _transfer_fixture(tmp_path)
    result = _create(fixture)
    assert result["valid"] is True
    assert result["pre_rename_verified"] is True

    output = fixture["output"]
    route = json.loads(
        (output / bundle.BUNDLE_NAMES["route_manifest"]).read_text(encoding="utf-8")
    )
    assert tuple(row["route_node_id"] for row in route["routes"]) == (
        MAGMAW_TRANSFER_ROUTE_NODE_IDS
    )
    assert [row["step"] for row in route["routes"]] == [1, 2, 3, 4]

    launch = json.loads(
        (output / bundle.BUNDLE_NAMES["launch_contract"]).read_text(encoding="utf-8")
    )
    assert launch["identity"] == {
        "scenario_id": bundle.SCENARIO_ID,
        "runtime_profile_id": bundle.SCENARIO_ID,
        "pool_tag": bundle.SCENARIO_ID,
        "actor_guid": 30007,
        "map_id": 669,
        "checkpoint_fixture_id": MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
        "checkpoint_case_id": MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
        "task_authority_enabled": False,
    }
    option = launch["launch_argv"].index(
        "--magmaw-transfer-checkpoint-actor-guid"
    )
    assert launch["launch_argv"][option + 1] == "30007"
    assert "--chainwielder-checkpoint-actor-guid" not in launch["launch_argv"]

    config = (
        output / bundle.BUNDLE_NAMES["runtime_config"]
    ).read_text(encoding="utf-8")
    prefix = MAGMAW_TRANSFER_CHECKPOINT_CONFIG_PREFIX
    expected_keys = {
        f"{prefix}.Enable",
        f"{prefix}.FixtureId",
        f"{prefix}.CaseId",
        f"{prefix}.SealSha256",
        f"{prefix}.SourceCommit",
    }
    actual_keys = {
        line.split("=", 1)[0].strip()
        for line in config.splitlines()
        if line.strip().startswith(prefix + ".")
    }
    assert actual_keys == expected_keys
    assert config.count("BotWorld.Magmaw.TransferLaneTaskAuthority = 0") == 1
    assert f'BotWorld.ValidationRoute.NodeId = "bwd.entry.regroup"' in config
    admission = json.loads(
        (output / bundle.BUNDLE_NAMES["admission"]).read_text(encoding="utf-8")
    )
    assert admission["fixture_expansion_target_ids"] == [
        MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID
    ]
    assert admission["pending_fixture_ids"] == [
        MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID
    ]
    assert admission["fixture_expansion_requests"] == []
    assert admission["checkpoint_seal"]["case_id"] == (
        MAGMAW_TRANSFER_CHECKPOINT_CASE_ID
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("actor_guid", 30008),
        ("checkpoint_fixture_id", "chainwielder_pre_admission_rejection_isolation_v1"),
        ("checkpoint_case_id", "entrance_polygon_short_lane_v2"),
    ],
)
def test_transfer_tuple_drift_fails_before_bundle_exposure(
    tmp_path: Path, field: str, value: object,
) -> None:
    fixture = _transfer_fixture(tmp_path)
    fixture["kwargs"][field] = value
    with pytest.raises(bundle.BundleError, match="identity_input_mismatch"):
        _create(fixture)
    assert not fixture["output"].exists()


def test_transfer_route_suffix_substitution_fails_closed(tmp_path: Path) -> None:
    fixture = _transfer_fixture(tmp_path)
    route_path = fixture["paths"]["route_manifest"]
    route = json.loads(route_path.read_text(encoding="utf-8"))
    route["routes"][1]["route_node_id"] = "bwd.magmaw.chainwielder.substitute"
    _write_json(route_path, route)
    fixture["kwargs"]["route_manifest_sha256"] = sha256_file(route_path)
    with pytest.raises(
        bundle.BundleError, match="magmaw_transfer_route_semantic_mismatch"
    ):
        _create(fixture)
    assert not fixture["output"].exists()


def test_transfer_rejects_noncanonical_ledger_source(tmp_path: Path) -> None:
    fixture = _transfer_fixture(tmp_path)
    rogue = fixture["external"] / "rogue-transfer-ledger.json"
    shutil.copyfile(fixture["paths"]["ledger"], rogue)
    fixture["kwargs"]["ledger"] = rogue
    fixture["kwargs"]["ledger_sha256"] = sha256_file(rogue)
    with pytest.raises(
        bundle.BundleError, match="magmaw_transfer_ledger_source_path_mismatch",
    ):
        _create(fixture)
    assert not fixture["output"].exists()


def test_transfer_rejects_partial_or_extra_suite_receipt(tmp_path: Path) -> None:
    fixture = _transfer_fixture(tmp_path)
    suite = fixture["paths"]["suite_receipt"]
    value = json.loads(suite.read_text(encoding="utf-8"))
    value["fixture_ids"].append("foreign_fixture")
    _write_json(suite, value)
    fixture["kwargs"]["suite_receipt_sha256"] = sha256_file(suite)
    with pytest.raises(
        bundle.BundleError, match="magmaw_transfer_suite_receipt_mismatch",
    ):
        _create(fixture)
    assert not fixture["output"].exists()


def test_transfer_rejects_minimal_hand_authored_suite_receipt(
    tmp_path: Path,
) -> None:
    fixture = _transfer_fixture(tmp_path)
    suite = fixture["paths"]["suite_receipt"]
    receipt = json.loads(suite.read_text(encoding="utf-8"))
    receipt["verifications"] = [{
        "fixture_id": MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
        "fixture_revision": MAGMAW_TRANSFER_FIXTURE_REVISION,
        "passed": True,
    }]
    _write_json(suite, receipt)
    fixture["kwargs"]["suite_receipt_sha256"] = sha256_file(suite)
    with pytest.raises(
        bundle.BundleError, match="magmaw_transfer_suite_receipt_mismatch",
    ):
        _create(fixture)
    assert not fixture["output"].exists()


@pytest.mark.parametrize(
    ("mutation"),
    [
        "stale_revision",
        "altered_command",
        "missing_first_run",
        "reordered_runs",
        "forged_retained_run",
        "wrong_fixture",
        "extra_fixture",
    ],
)
def test_transfer_rejects_revision_two_manifest_drift(
    tmp_path: Path, mutation: str,
) -> None:
    fixture = _transfer_fixture(tmp_path, ledger_mutation=mutation)
    with pytest.raises(
        bundle.BundleError, match="magmaw_transfer_ledger_manifest_mismatch",
    ):
        _create(fixture)
    assert not fixture["output"].exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("config_identity", "forged-config"),
        ("manifest_sha256", "0" * 64),
    ],
)
def test_transfer_rejects_forged_suite_identity(
    tmp_path: Path, field: str, value: str,
) -> None:
    fixture = _transfer_fixture(tmp_path)
    suite = fixture["paths"]["suite_receipt"]
    receipt = json.loads(suite.read_text(encoding="utf-8"))
    receipt[field] = value
    _write_json(suite, receipt)
    fixture["kwargs"]["suite_receipt_sha256"] = sha256_file(suite)
    with pytest.raises(
        bundle.BundleError, match="magmaw_transfer_suite_receipt_mismatch",
    ):
        _create(fixture)
    assert not fixture["output"].exists()


@pytest.mark.parametrize(
    ("row_index", "field", "value"),
    [
        (0, "map_id", 670),
        (3, "map_id", 670),
        (0, "kind", "trash"),
    ],
)
def test_transfer_rejects_coherent_full_route_semantic_drift(
    tmp_path: Path, row_index: int, field: str, value: object,
) -> None:
    fixture = _transfer_fixture(tmp_path)
    route_path = fixture["paths"]["route_manifest"]
    route = json.loads(route_path.read_text(encoding="utf-8"))
    route["routes"][row_index][field] = value
    _write_json(route_path, route)
    fixture["kwargs"]["route_manifest_sha256"] = sha256_file(route_path)
    expected_reason = (
        "route_checkpoint_identity_mismatch"
        if row_index == 0 and field == "map_id"
        else "magmaw_transfer_route_semantic_mismatch"
    )
    with pytest.raises(bundle.BundleError, match=expected_reason):
        _create(fixture)
    assert not fixture["output"].exists()


@pytest.mark.parametrize("target", ["config", "seal", "profile", "partial"])
def test_transfer_bundle_tamper_and_partial_overlay_fail_closed(
    tmp_path: Path, target: str,
) -> None:
    fixture = _transfer_fixture(tmp_path)
    _create(fixture)
    output = fixture["output"]
    if target == "partial":
        (output / bundle.BUNDLE_NAMES["profile_manifest"]).unlink()
    else:
        name = {
            "config": "runtime_config",
            "seal": "checkpoint_seal",
            "profile": "profile_manifest",
        }[target]
        path = output / bundle.BUNDLE_NAMES[name]
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(bundle.BundleError):
        bundle.verify_bundle(output)
