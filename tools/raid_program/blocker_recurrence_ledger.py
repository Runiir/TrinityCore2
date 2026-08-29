#!/usr/bin/env python3
"""Evaluate recurring causal blockers across deterministic raid canaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping


VALID_STATES = {"occurred", "absent", "not_exercised"}
REGRESSION_BANK_SCHEMA = "trinity_raid_regression_bank_v1"
SUITE_RECEIPT_SCHEMA = "trinity_raid_regression_suite_receipt_v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _identity(row: Any) -> tuple[Any, Any]:
    if not isinstance(row, Mapping):
        return (None, None)
    return (
        row.get("source_identity", row.get("source")),
        row.get("config_identity", row.get("config")),
    )


def _same(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":"), default=str) == json.dumps(
        right, sort_keys=True, separators=(",", ":"), default=str
    )


def _boundary(
    row: Mapping[str, Any], positions: Mapping[str, int]
) -> tuple[float | None, str | None]:
    before = row.get("passed_before_run_id")
    after = row.get("passed_after_run_id")
    if before and after:
        return None, "multiple_boundary_run_ids"
    value = before or after or row.get("run_id")
    if not value:
        return None, "missing_boundary_run_id"
    run_id = str(value).strip()
    if run_id not in positions:
        return None, f"unknown_boundary_run_id:{run_id}"
    position = float(positions[run_id])
    if before:
        return position - 0.5, None
    if after:
        return position + 0.5, None
    kind = str(row.get("boundary") or "after").lower()
    if kind in {"before", "pre"}:
        return position - 0.5, None
    if kind in {"after", "post"}:
        return position + 0.5, None
    return None, f"invalid_boundary:{kind}"


def _passed(row: Mapping[str, Any]) -> bool:
    if "passed" in row:
        return row["passed"] is True
    status = str(row.get("status") or "").strip().lower()
    if status:
        return status in {"pass", "passed", "success", "ok"}
    # Compatibility with the original fixture_verifications shape.
    return bool(row.get("passed_before_run_id") or row.get("passed_after_run_id"))


def _failed(row: Mapping[str, Any]) -> bool:
    if "passed" in row:
        return row["passed"] is not True
    return str(row.get("status") or "").strip().lower() in {"fail", "failed", "error"}


def _executable(row: Mapping[str, Any]) -> bool:
    command = row.get("command", row.get("test_command"))
    return isinstance(command, list) and bool(command) and all(
        isinstance(part, str) and part.strip() for part in command
    )


def _command_argv(row: Mapping[str, Any]) -> list[str]:
    command = row.get("command")
    _require(
        isinstance(command, list) and bool(command) and all(isinstance(part, str) and part.strip() for part in command),
        "fixture command must be a non-empty argv list",
    )
    return list(command)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _command_sha256(command: list[str]) -> str:
    return _sha256(json.dumps(command, separators=(",", ":")))


def _result_sha256(returncode: int, timed_out: bool, stdout_sha256: str, stderr_sha256: str) -> str:
    return _sha256(
        json.dumps(
            {
                "returncode": returncode,
                "timed_out": timed_out,
                "stdout_sha256": stdout_sha256,
                "stderr_sha256": stderr_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _execute_argv(command: list[str], cwd: Path) -> dict[str, Any]:
    """Execute one manifest argv and return independently observed results."""

    def output_text(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode(errors="replace")
        return str(value or "")

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        stdout = output_text(result.stdout)
        stderr = output_text(result.stderr)
        returncode = result.returncode
        timed_out = False
    except subprocess.TimeoutExpired as error:
        stdout = output_text(error.stdout)
        stderr = output_text(error.stderr)
        returncode = 124
        timed_out = True
    except OSError as error:
        stdout = ""
        stderr = str(error)
        returncode = 127
        timed_out = False

    stdout_sha256 = _sha256(stdout)
    stderr_sha256 = _sha256(stderr)
    return {
        "returncode": returncode,
        "timed_out": timed_out,
        "stdout_sha256": stdout_sha256,
        "stderr_sha256": stderr_sha256,
        "result_sha256": _result_sha256(
            returncode, timed_out, stdout_sha256, stderr_sha256
        ),
    }


def _manifest_sha256(bank: Mapping[str, Any]) -> str:
    payload = {
        "schema": bank.get("schema", REGRESSION_BANK_SCHEMA),
        "route": bank.get("route"),
        "fixture_history": bank.get("fixture_history", bank.get("retained_fixture_ids")),
        "fixtures": bank.get("fixtures", bank.get("fixture_manifest")),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _derived_config_identity(repo_root: Path) -> str:
    scenario_data = json.loads(
        (repo_root / "experiments/configs/validation_scenarios_cata_001.json").read_text()
    )
    shard_data = json.loads(
        (repo_root / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json").read_text()
    )
    scenario = next(row for row in scenario_data["scenarios"] if row.get("id") == "blackwing_descent_10n")
    shard = next(row for row in shard_data["shards"] if row.get("shard_id") == "bwd_magmaw_diagnostic_10n")
    payload = {
        "validation_scenario": scenario,
        "bwd_diagnostic_shard": {
            "schema": shard_data["schema"],
            "canonical_roster": shard_data["canonical_roster"],
            "diagnostic_bot_count": shard_data["diagnostic_bot_count"],
            "instance_identity_policy": shard_data["instance_identity_policy"],
            "shard": shard,
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{_sha256(encoded)}"


def _canonical_config_identity() -> str:
    """Derive the active route identity from checked-in canonical inputs.

    The caller may supply the source commit identity, but it must never be
    allowed to choose the route/config digest.  Keeping the root anchored to
    this module also makes the direct Python API use the same authority as the
    command-line gate.
    """

    return _derived_config_identity(Path(__file__).resolve().parents[2])


def _verify_clean_source_identity(repo_root: Path, supplied: str) -> None:
    """Require the receipt identity to name this exact clean tracked checkout."""

    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tracked_status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("cannot verify clean source identity") from error
    _require(supplied == head, "source identity does not match current HEAD")
    _require(not tracked_status, "tracked worktree is dirty")


def _evaluate_regression_bank(
    ledger: Mapping[str, Any],
    contracts: Mapping[str, Mapping[str, Any]],
    runs: list[dict[str, Any]],
    positions: Mapping[str, int],
    *,
    supplied_identity: Mapping[str, Any] | None = None,
    suite_receipt_verified: bool | None = None,
) -> dict[str, Any]:
    """Evaluate the active route's append-only fixture bank.

    The field is opt-in so ledgers written before this gate retain compatibility.
    Once present, every fixture in the manifest/history must have a current
    source/config-bound pass in the accumulated verification list.
    """

    bank = ledger.get("regression_bank", ledger.get("permanent_regression_bank"))
    empty = {
        "enabled": False,
        "schema": REGRESSION_BANK_SCHEMA,
        "admitted": True,
        "canary_admitted": True,
        "expected_fixture_ids": [],
        "verified_fixture_ids": [],
        "suite_verified_fixture_ids": [],
        "missing_fixture_ids": [],
        "stale_fixture_ids": [],
        "failing_fixture_ids": [],
        "invalidated_fixture_ids": [],
        "missing_causal_signature_ids": [],
        "invalidated_causal_signatures": {},
        "verified_after_latest_occurrence_signatures": [],
        "unknown_fixture_ids": [],
        "renamed_fixture_ids": [],
        "route_failures": [],
        "required_next_action": "not_enabled_for_legacy_ledger",
        "manifest_sha256": None,
    }
    if bank is None:
        return empty
    if not isinstance(bank, Mapping):
        empty.update(
            enabled=True,
            admitted=False,
            canary_admitted=False,
            failing_fixture_ids=["<regression_bank>"],
            route_failures=["manifest_not_object"],
            required_next_action="verify_accumulated_regression_bank",
        )
        return empty

    route = str(bank.get("route") or ledger.get("route") or "").strip()
    route_failures: list[str] = []
    if not route:
        route_failures.append("route_missing")
    if suite_receipt_verified is None:
        route_failures.append("suite_receipt_verification_required")
    elif suite_receipt_verified is not True:
        route_failures.append("suite_receipt_external_required")
    if bank.get("schema", REGRESSION_BANK_SCHEMA) != REGRESSION_BANK_SCHEMA:
        route_failures.append(f"schema:{bank.get('schema')}")
    if bank.get("route") and ledger.get("route") and bank["route"] != ledger["route"]:
        route_failures.append(f"route:{bank['route']}")
    declared = _identity(bank.get("current_identity"))
    current = _identity(supplied_identity)
    if supplied_identity is None:
        route_failures.append("current_identity_external_required")
    if current[0] in (None, "") or current[1] in (None, ""):
        route_failures.append("current_identity_missing_source_or_config")
    if declared[1] in (None, ""):
        route_failures.append("declared_current_config_identity_missing")
    elif current[1] not in (None, "") and not _same(declared[1], current[1]):
        route_failures.append("current_identity_declared_mismatch")
    if current[1] not in (None, ""):
        try:
            canonical_config = _canonical_config_identity()
        except (OSError, KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError):
            route_failures.append("canonical_config_identity_unavailable")
        else:
            if not _same(current[1], canonical_config):
                route_failures.append("current_identity_config_not_canonical")

    raw_fixtures = bank.get("fixtures", bank.get("fixture_manifest"))
    if not isinstance(raw_fixtures, list):
        route_failures.append("fixture_manifest_missing")
        raw_fixtures = []
    fixtures: dict[str, dict[str, Any]] = {}
    for index, raw_fixture in enumerate(raw_fixtures):
        if not isinstance(raw_fixture, Mapping):
            route_failures.append(f"fixture:{index}:not_object")
            continue
        fixture = dict(raw_fixture)
        fixture_id = str(fixture.get("fixture_id") or "").strip()
        if not fixture_id:
            route_failures.append(f"fixture:{index}:missing_fixture_id")
            continue
        if fixture_id in fixtures:
            route_failures.append(f"fixture:{fixture_id}:duplicate_fixture_id")
            continue
        fixtures[fixture_id] = fixture

    if "fixture_history" not in bank and "retained_fixture_ids" not in bank:
        route_failures.append("fixture_history_missing")
    history = bank.get("fixture_history", bank.get("retained_fixture_ids")) or []
    if not isinstance(history, list):
        route_failures.append("fixture_history_not_list")
        history = []
    history_ids: set[str] = set()
    for index, row in enumerate(history):
        fixture_id = str(row.get("fixture_id") if isinstance(row, Mapping) else row).strip()
        if not fixture_id:
            route_failures.append(f"fixture_history:{index}:missing_fixture_id")
        elif fixture_id in history_ids:
            route_failures.append(f"fixture_history:{fixture_id}:duplicate_fixture_id")
        else:
            history_ids.add(fixture_id)
    expected = set(fixtures) | history_ids
    missing: set[str] = history_ids - set(fixtures)
    route_failures.extend(
        f"fixture_not_in_history:{fixture_id}"
        for fixture_id in set(fixtures) - history_ids
    )
    occurred_signatures = {
        signature
        for run in runs
        for signature, state in run["blockers"].items()
        if state == "occurred"
    }
    fixture_signatures = {
        str(fixture.get("causal_signature") or "").strip()
        for fixture in fixtures.values()
    }
    missing_causal_signatures = sorted(occurred_signatures - fixture_signatures)
    route_failures.extend(
        f"missing_fixture_for_causal_signature:{signature}"
        for signature in missing_causal_signatures
    )
    manifest_stale: set[str] = set()
    renamed: set[str] = set()
    for fixture_id, fixture in fixtures.items():
        if not _executable(fixture):
            route_failures.append(f"fixture:{fixture_id}:missing_command")
        signature = str(fixture.get("causal_signature") or "").strip()
        if signature not in contracts:
            route_failures.append(f"fixture:{fixture_id}:unknown_causal_signature")
        fixture_route = str(fixture.get("route") or route).strip()
        if route and fixture_route != route:
            route_failures.append(f"fixture:{fixture_id}:route_mismatch")
        fixture_source, fixture_config = _identity(fixture)
        if fixture_source not in (None, "") and not _same(fixture_source, current[0]):
            manifest_stale.add(fixture_id)
        if fixture_config not in (None, "") and not _same(fixture_config, current[1]):
            manifest_stale.add(fixture_id)

    verifications: list[dict[str, Any]] = []
    raw_verifications = bank.get("verifications", [])
    if not isinstance(raw_verifications, list):
        route_failures.append("verifications_not_list")
        raw_verifications = []
    for index, row in enumerate(raw_verifications):
        if not isinstance(row, Mapping):
            route_failures.append(f"verification:{index}:not_object")
        else:
            verifications.append(dict(row))
    # A suite verification is just one append-only record expanded to every
    # listed fixture; exact set equality prevents silently omitting old cases.
    for suite in bank.get("suite_verifications", []) or []:
        if not isinstance(suite, Mapping):
            route_failures.append("suite_verification_not_object")
            continue
        for fixture_id in suite.get("fixture_ids") or []:
            row = dict(suite)
            row["fixture_id"] = str(fixture_id).strip()
            verifications.append(row)
        if "fixture_ids" not in suite:
            route_failures.append("suite_missing_fixture_ids")

    by_signature: dict[str, list[str]] = {}
    for fixture_id, fixture in fixtures.items():
        by_signature.setdefault(str(fixture.get("causal_signature") or ""), []).append(fixture_id)
    # Preserve old per-signature fixture_verifications while requiring an
    # explicit ID whenever a signature has more than one retained fixture.
    for signature, contract in contracts.items():
        for row in contract.get("fixture_verifications") or []:
            if not isinstance(row, Mapping):
                continue
            child = dict(row)
            candidates = by_signature.get(signature, [])
            child.setdefault("fixture_id", candidates[0] if len(candidates) == 1 else "")
            verifications.append(child)

    by_fixture: dict[str, list[dict[str, Any]]] = {}
    unknown: set[str] = set()
    for row in verifications:
        fixture_id = str(row.get("fixture_id") or "").strip()
        if fixture_id not in fixtures:
            unknown.add(fixture_id or "<unbound_fixture>")
        else:
            by_fixture.setdefault(fixture_id, []).append(row)
    renamed.update(unknown)

    missing_ids = set(missing)
    stale: set[str] = set(manifest_stale)
    failing: set[str] = set()
    invalidated: set[str] = set()
    verified: set[str] = set()
    current_pass: set[str] = set()
    invalidation_runs: dict[str, list[str]] = {}
    invalidated_signatures: dict[str, list[str]] = {}
    verified_after_occurrence: set[str] = set()
    for fixture_id in sorted(expected):
        fixture = fixtures.get(fixture_id)
        records = by_fixture.get(fixture_id, [])
        if fixture is None or not records:
            missing_ids.add(fixture_id)
            continue
        latest: tuple[float, Mapping[str, Any]] | None = None
        latest_pass: tuple[float, Mapping[str, Any]] | None = None
        for record in records:
            boundary, error = _boundary(record, positions)
            if error:
                stale.add(fixture_id)
                continue
            # Ledger history may append an older compatibility row after a
            # newer suite receipt; choose by route boundary, never list order.
            if latest is None or boundary >= latest[0]:
                latest = (boundary, record)
            if _passed(record) and (latest_pass is None or boundary >= latest_pass[0]):
                latest_pass = (boundary, record)
        if latest is not None and _failed(latest[1]):
            failing.add(fixture_id)
        if latest_pass is None:
            if fixture_id not in failing:
                missing_ids.add(fixture_id)
            continue
        verified.add(fixture_id)
        pass_boundary, pass_record = latest_pass
        source, config = _identity(pass_record)
        if (
            source in (None, "")
            or config in (None, "")
            or not _same(source, current[0])
            or not _same(config, current[1])
        ):
            stale.add(fixture_id)
        else:
            current_pass.add(fixture_id)
        signature = str(fixture.get("causal_signature") or "")
        occurrences = [
            run["run_id"]
            for index, run in enumerate(runs)
            if index > pass_boundary and run["blockers"].get(signature) == "occurred"
        ]
        if occurrences:
            invalidated.add(fixture_id)
            failing.add(fixture_id)
            invalidation_runs[fixture_id] = occurrences
            invalidated_signatures.setdefault(signature, []).append(fixture_id)
        else:
            last_occurrence = max(
                (index for index, run in enumerate(runs) if run["blockers"].get(signature) == "occurred"),
                default=-1,
            )
            if fixture_id in current_pass and pass_boundary > float(last_occurrence):
                verified_after_occurrence.add(signature)

    usable_passes = current_pass - stale - failing - invalidated
    suite_ids = usable_passes if usable_passes == expected else set()
    missing_ids.update(expected - current_pass - stale - failing - invalidated)
    if not expected:
        route_failures.append("fixture_manifest_missing")
    admitted = not (
        route_failures
        or missing_ids
        or stale
        or failing
        or invalidated
        or unknown
        or missing_causal_signatures
        or suite_ids != expected
    )
    return {
        "enabled": True,
        "schema": bank.get("schema", REGRESSION_BANK_SCHEMA),
        "manifest_sha256": _manifest_sha256(bank),
        "route": route or None,
        "current_identity": {"source": current[0], "config": current[1]},
        "admitted": admitted,
        "canary_admitted": admitted,
        "expected_fixture_ids": sorted(expected),
        "verified_fixture_ids": sorted(verified),
        "suite_verified_fixture_ids": sorted(suite_ids),
        "missing_fixture_ids": sorted(missing_ids),
        "stale_fixture_ids": sorted(stale),
        "failing_fixture_ids": sorted(failing),
        "invalidated_fixture_ids": sorted(invalidated),
        "missing_causal_signature_ids": missing_causal_signatures,
        "invalidated_causal_signatures": {
            signature: sorted(ids)
            for signature, ids in sorted(invalidated_signatures.items())
        },
        "verified_after_latest_occurrence_signatures": sorted(verified_after_occurrence),
        "invalidation_run_ids": {
            fixture_id: invalidation_runs[fixture_id]
            for fixture_id in sorted(invalidation_runs)
        },
        "unknown_fixture_ids": sorted(unknown),
        "renamed_fixture_ids": sorted(renamed),
        "route_failures": sorted(route_failures),
        "required_next_action": (
            "accept"
            if admitted
            else "expand_invalid_retained_fixture"
            if invalidated
            else "verify_accumulated_regression_bank"
        ),
    }


def evaluate_ledger(
    ledger: Mapping[str, Any],
    *,
    current_identity: Mapping[str, Any] | None = None,
    suite_receipt_verified: bool | None = None,
) -> dict[str, Any]:
    """Return the fail-closed recurrence and acceptance decision."""

    _require(
        ledger.get("schema") == "trinity_raid_blocker_recurrence_v1",
        "unsupported blocker recurrence ledger schema",
    )
    occurrence_limit = int(ledger.get("occurrence_limit", 10))
    clear_streak_required = int(ledger.get("clear_streak_required", 2))
    _require(occurrence_limit > 0, "occurrence_limit must be positive")
    _require(clear_streak_required > 0, "clear_streak_required must be positive")

    raw_contracts = dict(ledger.get("causal_signatures") or {})
    contracts: dict[str, Mapping[str, Any]] = {}
    for raw_signature, contract in raw_contracts.items():
        signature = str(raw_signature)
        _require(isinstance(contract, Mapping), f"signature {signature} contract must be an object")
        contracts[signature] = contract
    parents: dict[str, str] = {}
    for signature, contract in contracts.items():
        parent = str(contract.get("parent") or "").strip()
        if parent:
            _require(parent != signature, f"signature {signature} cannot parent itself")
            _require(parent in contracts, f"signature {signature} has unknown parent {parent}")
            parents[signature] = parent

    def ancestors(signature: str) -> list[str]:
        result: list[str] = []
        seen = {signature}
        while signature in parents:
            signature = parents[signature]
            _require(signature not in seen, f"causal signature parent cycle at {signature}")
            seen.add(signature)
            result.append(signature)
        return result

    runs = list(ledger.get("runs") or [])
    seen_run_ids: set[str] = set()
    signatures: set[str] = set(contracts)
    normalized_runs: list[dict[str, Any]] = []
    for index, run in enumerate(runs):
        _require(isinstance(run, Mapping), f"run {index} must be an object")
        run_id = str(run.get("run_id") or "").strip()
        _require(bool(run_id), f"run {index} is missing run_id")
        _require(run_id not in seen_run_ids, f"duplicate run_id: {run_id}")
        seen_run_ids.add(run_id)
        observations: dict[str, str] = {}
        for raw_signature, state in dict(run.get("blockers") or {}).items():
            signature = str(raw_signature).strip()
            _require(bool(signature), f"run {run_id} has empty signature")
            _require(state in VALID_STATES, f"run {run_id} signature {signature} has invalid state {state!r}")
            observations[signature] = state
            signatures.add(signature)
        for signature, state in list(observations.items()):
            if state == "occurred":
                for parent in ancestors(signature):
                    observations[parent] = "occurred"
                    signatures.add(parent)
        normalized_runs.append(
            {
                "run_id": run_id,
                "route_completed": run.get("route_completed") is True,
                "blockers": observations,
            }
        )

    positions = {run["run_id"]: index for index, run in enumerate(normalized_runs)}
    blocker_rows: list[dict[str, Any]] = []
    stop_signatures: list[str] = []
    open_signatures: list[str] = []
    for signature in sorted(signatures):
        occurrences = [
            run["run_id"] for run in normalized_runs
            if run["blockers"].get(signature) == "occurred"
        ]
        clean_clear_streak = 0
        for run in reversed(normalized_runs):
            if run["route_completed"] and run["blockers"].get(signature, "not_exercised") == "absent":
                clean_clear_streak += 1
                continue
            break
        last_observed_run_id = None
        last_observed_state = "not_exercised"
        for run in reversed(normalized_runs):
            if signature in run["blockers"]:
                last_observed_run_id = run["run_id"]
                last_observed_state = run["blockers"][signature]
                break
        contract = contracts.get(signature, {})
        reviewed_through = int(contract.get("architecture_reviewed_through_occurrence_count", 0))
        _require(0 <= reviewed_through <= len(occurrences), f"signature {signature} has invalid architecture review count")
        unreviewed = len(occurrences) - reviewed_through
        fixture_verifications = list(contract.get("fixture_verifications") or [])
        latest_fixture_verification: Mapping[str, Any] | None = None
        latest_fixture_boundary = -1.0
        for verification_index, verification in enumerate(fixture_verifications):
            _require(isinstance(verification, Mapping), f"signature {signature} fixture verification {verification_index} must be an object")
            before = str(verification.get("passed_before_run_id") or "").strip()
            after = str(verification.get("passed_after_run_id") or "").strip()
            _require(bool(before) != bool(after), f"signature {signature} fixture verification {verification_index} must declare exactly one of passed_before_run_id or passed_after_run_id")
            boundary_id = before or after
            _require(boundary_id in positions, f"signature {signature} fixture verification {verification_index} has unknown boundary run_id {boundary_id!r}")
            _require(bool(str(verification.get("evidence") or "").strip()), f"signature {signature} fixture verification {verification_index} is missing evidence")
            boundary = float(positions[boundary_id]) + (0.5 if after else -0.5)
            _require(boundary >= latest_fixture_boundary, f"signature {signature} fixture verifications are not chronological")
            latest_fixture_boundary = boundary
            latest_fixture_verification = verification
        live_occurrences_after_fixture = [
            run["run_id"] for index, run in enumerate(normalized_runs)
            if latest_fixture_verification is not None
            and float(index) > latest_fixture_boundary
            and run["blockers"].get(signature) == "occurred"
        ]
        fixture_invalidated = bool(live_occurrences_after_fixture)
        last_occurrence_position = positions[occurrences[-1]] if occurrences else -1
        fixture_verified_after_latest_occurrence = latest_fixture_verification is not None and latest_fixture_boundary > float(last_occurrence_position)
        recurrence_limit_stop = unreviewed >= occurrence_limit
        stop_required = recurrence_limit_stop or fixture_invalidated
        if occurrences and clean_clear_streak < clear_streak_required:
            open_signatures.append(signature)
        if stop_required:
            stop_signatures.append(signature)
        blocker_rows.append(
            {
                "causal_signature": signature,
                "occurrence_count": len(occurrences),
                "occurrence_run_ids": occurrences,
                "last_occurrence_run_id": occurrences[-1] if occurrences else None,
                "last_observed_run_id": last_observed_run_id,
                "last_observed_state": last_observed_state,
                "architecture_reviewed_through_occurrence_count": reviewed_through,
                "unreviewed_occurrence_count": unreviewed,
                "clean_full_clear_streak": clean_clear_streak,
                "latest_fixture_verification": dict(latest_fixture_verification) if latest_fixture_verification else None,
                "live_occurrences_after_fixture": live_occurrences_after_fixture,
                "retained_fixture_invalidated": fixture_invalidated,
                "fixture_verified_after_latest_occurrence": fixture_verified_after_latest_occurrence,
                "recurrence_limit_stop": recurrence_limit_stop,
                "open": bool(occurrences and clean_clear_streak < clear_streak_required),
                "stop_required": stop_required,
            }
        )

    regression_bank = _evaluate_regression_bank(
        ledger,
        contracts,
        normalized_runs,
        positions,
        supplied_identity=current_identity,
        suite_receipt_verified=suite_receipt_verified,
    )
    last_runs = normalized_runs[-clear_streak_required:]
    open_rows = [row for row in blocker_rows if row["open"]]
    repair_rows = [
        row for row in open_rows
        if row["last_observed_state"] == "occurred"
        and not row["fixture_verified_after_latest_occurrence"]
        and row["causal_signature"] not in regression_bank["verified_after_latest_occurrence_signatures"]
    ]
    next_signature = None
    if repair_rows:
        next_signature = max(
            repair_rows,
            key=lambda row: (positions.get(row["last_occurrence_run_id"], -1), row["occurrence_count"]),
        )["causal_signature"]
    bank_verified_after = set(regression_bank["verified_after_latest_occurrence_signatures"])
    invalid_fixture_rows = [
        row
        for row in blocker_rows
        if row["retained_fixture_invalidated"]
        and row["causal_signature"] not in bank_verified_after
    ]
    effective_stop_signatures = [
        signature
        for signature in stop_signatures
        if any(
            row["causal_signature"] == signature
            and (
                row["recurrence_limit_stop"]
                or signature not in bank_verified_after
            )
            for row in blocker_rows
        )
    ]
    if invalid_fixture_rows:
        next_signature = max(
            invalid_fixture_rows,
            key=lambda row: positions.get(row["live_occurrences_after_fixture"][-1], -1),
        )["causal_signature"]
    for signature in regression_bank["invalidated_causal_signatures"]:
        rows = [row for row in blocker_rows if row["causal_signature"] == signature]
        if rows:
            next_signature = max(rows, key=lambda row: positions.get(row["last_occurrence_run_id"], -1))["causal_signature"]
    latest_occurrence_row = max(
        (row for row in blocker_rows if row["occurrence_count"]),
        key=lambda row: positions.get(row["last_occurrence_run_id"], -1),
        default=None,
    )
    latest_occurrence_repaired = latest_occurrence_row is None or (
        latest_occurrence_row["causal_signature"] in bank_verified_after
        or latest_occurrence_row["fixture_verified_after_latest_occurrence"]
    )
    canary_recurrence = not effective_stop_signatures and latest_occurrence_repaired
    recurrence_acceptance = (
        len(last_runs) == clear_streak_required
        and all(run["route_completed"] for run in last_runs)
        and not open_signatures
        and not effective_stop_signatures
    )
    build_admitted = regression_bank["admitted"]
    canary = canary_recurrence and build_admitted
    acceptance = recurrence_acceptance and build_admitted
    if invalid_fixture_rows or regression_bank["invalidated_fixture_ids"]:
        required_next_action = "expand_invalid_retained_fixture"
    elif effective_stop_signatures:
        required_next_action = "stop_and_summarize_last_ten_occurrences"
    elif not regression_bank["admitted"]:
        required_next_action = regression_bank["required_next_action"]
    elif repair_rows:
        required_next_action = "repair_latest_recurring_causal_signature"
    elif not acceptance:
        required_next_action = "run_clean_full_clear"
    else:
        required_next_action = "accept"
    return {
        "schema": "trinity_raid_blocker_recurrence_decision_v1",
        "run_count": len(normalized_runs),
        "occurrence_limit": occurrence_limit,
        "clear_streak_required": clear_streak_required,
        "blockers": blocker_rows,
        "open_causal_signatures": open_signatures,
        "stop_required": bool(effective_stop_signatures),
        "stop_causal_signatures": effective_stop_signatures,
        "next_causal_signature": next_signature,
        "recurrence_acceptance_admitted": recurrence_acceptance,
        "canary_recurrence_admitted": canary_recurrence,
        "regression_bank": regression_bank,
        "regression_bank_admitted": regression_bank["admitted"],
        "missing_fixture_ids": regression_bank["missing_fixture_ids"],
        "stale_fixture_ids": regression_bank["stale_fixture_ids"],
        "failing_fixture_ids": regression_bank["failing_fixture_ids"],
        "invalidated_fixture_ids": regression_bank["invalidated_fixture_ids"],
        "missing_causal_signature_ids": regression_bank["missing_causal_signature_ids"],
        "build_admitted": build_admitted,
        "canary_admitted": canary,
        "acceptance_admitted": acceptance,
        "required_next_action": required_next_action,
    }


def _ledger_with_suite_receipt(
    ledger: Mapping[str, Any], receipt_path: Path, identity: Mapping[str, Any]
) -> dict[str, Any]:
    bank_key = "regression_bank" if "regression_bank" in ledger else "permanent_regression_bank"
    bank = ledger.get(bank_key)
    _require(isinstance(bank, Mapping), "regression bank must be an object")
    receipt = json.loads(receipt_path.read_text())
    _require(isinstance(receipt, Mapping), "suite receipt must be an object")
    _require(receipt.get("schema") == SUITE_RECEIPT_SCHEMA, "unsupported suite receipt schema")
    _require(
        receipt.get("manifest_sha256") == _manifest_sha256(bank),
        "suite receipt manifest identity mismatch",
    )
    receipt_source, receipt_config = _identity(receipt)
    source, config = _identity(identity)
    _require(_same(receipt_source, source), "suite receipt source identity mismatch")
    _require(_same(receipt_config, config), "suite receipt config identity mismatch")
    try:
        canonical_config = _canonical_config_identity()
    except (OSError, KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("canonical config identity unavailable") from error
    _require(
        _same(config, canonical_config),
        "suite receipt config identity is not derived from canonical route inputs",
    )
    rows = receipt.get("verifications")
    fixtures = bank.get("fixtures")
    _require(isinstance(fixtures, list), "ledger fixture manifest must be a list")
    fixture_map = {
        str(row.get("fixture_id") or "").strip(): row
        for row in fixtures
        if isinstance(row, Mapping) and str(row.get("fixture_id") or "").strip()
    }
    expected = set(fixture_map)
    declared_ids = receipt.get("fixture_ids")
    _require(
        isinstance(declared_ids, list)
        and len(declared_ids) == len(expected)
        and {str(value).strip() for value in declared_ids} == expected,
        "suite receipt fixture set is not exact",
    )
    _require(
        isinstance(rows, list)
        and len(rows) == len(expected)
        and all(isinstance(row, Mapping) for row in rows),
        "suite receipt fixture set is incomplete",
    )
    runs = ledger.get("runs")
    _require(isinstance(runs, list) and runs, "suite receipt requires ledger runs")
    latest_run = runs[-1]
    _require(isinstance(latest_run, Mapping), "latest ledger run must be an object")
    verification_run_id = str(latest_run.get("run_id") or "").strip()
    _require(verification_run_id, "latest ledger run_id is missing")
    observed: set[str] = set()
    verified_rows: list[dict[str, Any]] = []
    for row in rows:
        fixture_id = str(row.get("fixture_id") or "").strip()
        _require(fixture_id in expected and fixture_id not in observed, "suite receipt fixture set is not exact")
        observed.add(fixture_id)
        _require(isinstance(row.get("passed"), bool), f"suite receipt fixture {fixture_id} has invalid pass result")
        row_source, row_config = _identity(row)
        _require(_same(row_source, source) and _same(row_config, config), f"suite receipt fixture {fixture_id} identity mismatch")
        command = _command_argv(fixture_map[fixture_id])
        _require(row.get("command_sha256") == _command_sha256(command), f"suite receipt fixture {fixture_id} command identity mismatch")
        returncode = row.get("returncode")
        _require(isinstance(row.get("timed_out"), bool), f"suite receipt fixture {fixture_id} has invalid timeout result")
        timed_out = row["timed_out"]
        _require(isinstance(returncode, int) and not isinstance(returncode, bool), f"suite receipt fixture {fixture_id} has invalid return code")
        stdout_sha256 = row.get("stdout_sha256")
        stderr_sha256 = row.get("stderr_sha256")
        _require(isinstance(stdout_sha256, str) and isinstance(stderr_sha256, str), f"suite receipt fixture {fixture_id} result hashes missing")
        _require(
            row.get("result_sha256") == _result_sha256(returncode, timed_out, stdout_sha256, stderr_sha256),
            f"suite receipt fixture {fixture_id} result identity mismatch",
        )
        _require(row["passed"] is (returncode == 0 and not timed_out), f"suite receipt fixture {fixture_id} pass result mismatch")
        # A receipt identifies the immutable suite, but its claimed result is
        # never admission authority. Re-run the fixed argv and bind the gate to
        # that new observation. This both defeats forged result hashes and
        # avoids requiring byte-identical pytest timing text across valid runs.
        actual_result = _execute_argv(command, Path(__file__).resolve().parents[2])
        verified_rows.append({
            "fixture_id": fixture_id,
            "passed": actual_result["returncode"] == 0 and not actual_result["timed_out"],
            **actual_result,
            "command_sha256": _command_sha256(command),
            "source_identity": source,
            "config_identity": config,
            "passed_after_run_id": verification_run_id,
        })
    _require(observed == expected, "suite receipt fixture set is not exact")
    existing = bank.get("verifications", [])
    _require(isinstance(existing, list), "ledger verifications must be a list")
    effective = dict(ledger)
    effective_bank = dict(bank)
    effective_bank["verifications"] = [*existing, *verified_rows]
    effective[bank_key] = effective_bank
    return effective


def _run_suite(
    ledger: Mapping[str, Any],
    identity: Mapping[str, Any],
    boundary_run_id: str,
    boundary: str,
    receipt_path: Path,
) -> None:
    bank = ledger.get("regression_bank", ledger.get("permanent_regression_bank"))
    _require(isinstance(bank, Mapping), "regression bank must be an object")
    fixtures = bank.get("fixtures")
    _require(isinstance(fixtures, list) and fixtures, "fixture manifest must be a non-empty list")
    source, config = _identity(identity)
    _require(source not in (None, "") and config not in (None, ""), "suite identity must include source and config")
    try:
        canonical_config = _canonical_config_identity()
    except (OSError, KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("canonical config identity unavailable") from error
    _require(
        _same(config, canonical_config),
        "suite identity config must be derived from canonical route inputs",
    )
    _require(boundary in {"before", "after"}, "suite boundary must be before or after")
    _require(boundary_run_id in {str(run.get("run_id") or "") for run in ledger.get("runs") or []}, "suite boundary run_id is unknown")
    rows: list[dict[str, Any]] = []
    for fixture in fixtures:
        _require(isinstance(fixture, Mapping), "fixture manifest row must be an object")
        fixture_id = str(fixture.get("fixture_id") or "").strip()
        command = _command_argv(fixture)
        observed = _execute_argv(command, Path(__file__).resolve().parents[2])
        returncode = observed["returncode"]
        timed_out = observed["timed_out"]
        stdout_sha256 = observed["stdout_sha256"]
        stderr_sha256 = observed["stderr_sha256"]
        row = {
            "fixture_id": fixture_id,
            "passed": returncode == 0 and not timed_out,
            "returncode": returncode,
            "timed_out": timed_out,
            "command_sha256": _command_sha256(command),
            "stdout_sha256": stdout_sha256,
            "stderr_sha256": stderr_sha256,
            "result_sha256": observed["result_sha256"],
            "source_identity": source,
            "config_identity": config,
            f"passed_{boundary}_run_id": boundary_run_id,
        }
        rows.append(row)
    receipt = {
        "schema": SUITE_RECEIPT_SCHEMA,
        "manifest_sha256": _manifest_sha256(bank),
        "source_identity": source,
        "config_identity": config,
        "fixture_ids": [str(row.get("fixture_id") or "").strip() for row in fixtures],
        "verifications": rows,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-identity")
    parser.add_argument("--config-identity")
    parser.add_argument("--suite-receipt", type=Path)
    parser.add_argument("--run-suite", type=Path, help="run the fixed fixture argv and write this receipt")
    parser.add_argument("--boundary-run-id")
    parser.add_argument("--boundary", choices=("before", "after"), default="after")
    parser.add_argument("--gate", choices=("build", "canary", "acceptance"), default="canary")
    args = parser.parse_args()

    ledger = json.loads(args.ledger.read_text())
    bank_enabled = "regression_bank" in ledger or "permanent_regression_bank" in ledger
    identity = None
    repo_root = Path(__file__).resolve().parents[2]
    canonical_config_identity = None
    if args.source_identity:
        _verify_clean_source_identity(repo_root, args.source_identity)
        try:
            canonical_config_identity = _canonical_config_identity()
        except (OSError, KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("canonical config identity unavailable") from error
        if args.config_identity is not None:
            _require(
                _same(args.config_identity, canonical_config_identity),
                "config identity does not match canonical route inputs",
            )
        identity = {
            "source_identity": args.source_identity,
            "config_identity": canonical_config_identity,
        }
    elif args.config_identity is not None:
        parser.error("--config-identity requires --source-identity")
    receipt_verified = None
    if bank_enabled:
        receipt_verified = False
    if args.suite_receipt is not None and args.run_suite is not None:
        parser.error("use only one of --suite-receipt or --run-suite")
    if args.run_suite is not None:
        if not bank_enabled:
            parser.error("--run-suite requires an enabled regression bank")
        if identity is None or not args.boundary_run_id:
            parser.error("--run-suite requires --source-identity and --boundary-run-id")
        _run_suite(ledger, identity, args.boundary_run_id, args.boundary, args.run_suite)
        args.suite_receipt = args.run_suite
    if bank_enabled and identity is not None and args.suite_receipt is not None:
        ledger = _ledger_with_suite_receipt(ledger, args.suite_receipt, identity or {})
        receipt_verified = True
    decision = evaluate_ledger(
        ledger,
        current_identity=identity,
        suite_receipt_verified=receipt_verified,
    )
    rendered = json.dumps(decision, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0 if not bank_enabled or decision[f"{args.gate}_admitted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
