"""Run the current 25H DPS matrix with 75% hard and 85% optimization gates."""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .batch_evidence_lifecycle import (
    valid_reconstruction_receipt,
    verify_remote_reconstruction_and_evict,
)
from .build_phase8_evidence_identity_manifest import _clean_source_identity
from .common import write_json
from .live_validation_session import canonical_sha256, git_head, sha256_file, sha256_text
from .phase8_calibration_adapter import (
    DEFAULT_REFERENCES,
    DEFAULT_SCENARIOS,
    DEFAULT_TARGETS,
    evaluate_runtime_calibration,
)
from .phase8_evidence_identity import (
    build_projection as phase8_build_projection,
    validate_manifest as validate_evidence_manifest,
)
from .run_phase8_all_spec_calibration import (
    attempt_directory_candidates,
    compact_result,
    load_targets,
    valid_publication,
)
from .verify_cata_raid_dps_acceptance import verify as verify_acceptance


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "experiments/configs/cata_raid_dps_acceptance_v1.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts/all_spec_program/cata_raid_dps_acceptance"
MAX_PHYSICAL_TRIES = 2
DEFAULT_CHILD_OUTER_TIMEOUT_SEC = 1800
CHILD_TERMINATE_GRACE_SEC = 10.0
CHILD_KILL_GRACE_SEC = 5.0
STARTED_RECEIPT = "physical_try_started.json"
RESULT_RECEIPT = "physical_try_result.json"
CONTROLLER_LOCK = ".dps_acceptance_controller.lock"
FIXTURE_EVIDENCE_CLASS = "non_certifying_calibration_fixture"
FIXTURE_RUNTIME_MODE = "calibration_fixture"


class CampaignControllerLockHeld(RuntimeError):
    """Raised when another process owns this campaign's controller lease."""


class ControllerSignalInterruption(BaseException):
    """Convert a terminating controller signal into a cleanup opportunity."""

    def __init__(self, signal_number: int) -> None:
        super().__init__(f"controller received signal {signal_number}")
        self.signal_number = int(signal_number)


@contextmanager
def campaign_controller_lock(output_root: Path) -> Iterator[Path]:
    """Hold one nonblocking OS lock for the complete campaign transaction.

    The lock file is stable per resolved output root.  It deliberately lives
    outside attempt directories so publication/eviction cannot remove it.
    """
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    lock_path = output_root / CONTROLLER_LOCK
    lock_stream = lock_path.open("a+", encoding="utf-8")
    acquired = False
    try:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            raise CampaignControllerLockHeld(
                f"DPS acceptance campaign controller lock is already held: {lock_path}"
            ) from exc
        yield lock_path
    finally:
        if acquired:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
        lock_stream.close()


def fixture_provenance() -> dict[str, Any]:
    return {
        "evidence_class": FIXTURE_EVIDENCE_CLASS,
        "excluded_from_training_corpus": True,
        "runtime_mode": FIXTURE_RUNTIME_MODE,
        "non_certifying_assistance": True,
    }


def phase8_envelope_build_projection(
    evidence_manifest: Mapping[str, Any],
) -> dict[str, str]:
    """Project a validated Phase 8 v2 build into report-envelope names.

    The manifest and live envelope intentionally use different namespaces.
    This is the sole semantic mapping between them; process-local and artifact
    hashes are not build identity and therefore are not projected here.
    """
    manifest = validate_evidence_manifest(evidence_manifest)
    build = phase8_build_projection(manifest)
    manifest_components = manifest["component_hashes"]
    clean_dirty_state = canonical_sha256(
        {
            "porcelain_sha256": sha256_text(""),
            "binary_diff_sha256": sha256_text(""),
            "untracked": [],
        }
    )
    return {
        "git_commit_sha256": sha256_text(build["git_commit"]),
        "git_dirty_state_sha256": clean_dirty_state,
        "binary_sha256": build["worldserver_binary_sha256"],
        "database_snapshot_sha256": build["database_snapshot_sha256"],
        "database_schema_sha256": build["database_schema_sha256"],
        "server_epoch_sha256": str(manifest_components["server_epoch_sha256"]),
        "profile_generation_sha256": str(
            manifest_components["profile_generation_sha256"]
        ),
    }


def phase8_envelope_build_compatible(
    evidence_manifest: Mapping[str, Any],
    envelope_components: Mapping[str, Any],
) -> bool:
    try:
        expected = phase8_envelope_build_projection(evidence_manifest)
    except (KeyError, TypeError, ValueError):
        return False
    return all(envelope_components.get(name) == value for name, value in expected.items())


def require_current_phase8_source_identity(
    repository: Path,
    worldserver: Path,
    evidence_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail closed unless launch still uses the manifest's clean source build."""
    manifest = validate_evidence_manifest(evidence_manifest)
    expected = phase8_build_projection(manifest)
    try:
        observed = _clean_source_identity(repository.resolve(), worldserver.resolve())
    except RuntimeError as exc:
        raise SystemExit(f"Phase 8 launch requires a clean source tree: {exc}") from exc
    if (
        observed.get("source_tree_clean") is not True
        or str(observed.get("git_commit") or "").lower() != expected["git_commit"]
    ):
        raise SystemExit("Phase 8 launch source commit does not match its evidence manifest")
    if (
        str(observed.get("worldserver_binary_sha256") or "").lower()
        != expected["worldserver_binary_sha256"]
    ):
        raise SystemExit(
            "Phase 8 launch worldserver binary does not match its evidence manifest"
        )
    return observed


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_process_group_exit(
    process_group_id: int,
    timeout_sec: float,
    *,
    process: subprocess.Popen[Any] | None = None,
) -> bool:
    deadline = time.monotonic() + max(0.0, float(timeout_sec))
    while True:
        if process is not None:
            process.poll()
        if not _process_group_exists(process_group_id):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))


def _terminate_child_process_group(
    process: subprocess.Popen[Any],
    *,
    terminate_grace_sec: float,
    kill_grace_sec: float,
) -> dict[str, Any]:
    """Bounded TERM/KILL cleanup for a child started as its own session."""
    process_group_id = process.pid
    terminate_sent = False
    kill_sent = False
    if _process_group_exists(process_group_id):
        try:
            os.killpg(process_group_id, signal.SIGTERM)
            terminate_sent = True
        except ProcessLookupError:
            pass
    group_gone = _wait_for_process_group_exit(
        process_group_id, terminate_grace_sec, process=process
    )
    if not group_gone and _process_group_exists(process_group_id):
        try:
            os.killpg(process_group_id, signal.SIGKILL)
            kill_sent = True
        except ProcessLookupError:
            pass
        group_gone = _wait_for_process_group_exit(
            process_group_id, kill_grace_sec, process=process
        )
    try:
        returncode = process.wait(timeout=max(0.01, float(kill_grace_sec)))
    except subprocess.TimeoutExpired:
        returncode = None
    return {
        "process_group_id": process_group_id,
        "process_group_terminate_sent": terminate_sent,
        "process_group_kill_sent": kill_sent,
        "process_group_gone": group_gone,
        "returncode": returncode,
        "returncode_observed": type(returncode) is int,
    }


def run_child_process_group(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    output_stream: Any,
    timeout_sec: float,
    terminate_grace_sec: float = CHILD_TERMINATE_GRACE_SEC,
    kill_grace_sec: float = CHILD_KILL_GRACE_SEC,
) -> tuple[dict[str, Any], BaseException | None]:
    """Run one child with a bounded lifetime and no surviving descendants."""
    if float(timeout_sec) <= 0:
        raise ValueError("child outer timeout must be positive")
    process = subprocess.Popen(
        [str(value) for value in command],
        cwd=cwd,
        env=dict(env),
        stdout=output_stream,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    previous_signal_handlers: dict[int, Any] = {}

    def interrupt_for_signal(signal_number: int, _frame: Any) -> None:
        raise ControllerSignalInterruption(signal_number)

    for signal_number in (signal.SIGTERM, signal.SIGHUP):
        try:
            previous_signal_handlers[signal_number] = signal.getsignal(signal_number)
            signal.signal(signal_number, interrupt_for_signal)
        except ValueError:
            # Only the main thread may install handlers. KeyboardInterrupt and
            # exception cleanup remain active for non-main-thread test callers.
            previous_signal_handlers.clear()
            break
    try:
        returncode = process.wait(timeout=float(timeout_sec))
        group_gone = not _process_group_exists(process.pid)
        if not group_gone:
            cleanup = _terminate_child_process_group(
                process,
                terminate_grace_sec=terminate_grace_sec,
                kill_grace_sec=kill_grace_sec,
            )
            return (
                {
                    **cleanup,
                    "returncode": returncode,
                    "returncode_observed": True,
                    "transport_classification": (
                        "child_exited_with_lingering_descendants"
                    ),
                    "outer_timed_out": False,
                    "controller_interrupted": False,
                },
                None,
            )
        return (
            {
                "transport_classification": "child_exited",
                "outer_timed_out": False,
                "controller_interrupted": False,
                "process_group_id": process.pid,
                "process_group_terminate_sent": False,
                "process_group_kill_sent": False,
                "process_group_gone": True,
                "returncode": returncode,
                "returncode_observed": True,
            },
            None,
        )
    except subprocess.TimeoutExpired:
        cleanup = _terminate_child_process_group(
            process,
            terminate_grace_sec=terminate_grace_sec,
            kill_grace_sec=kill_grace_sec,
        )
        return (
            {
                **cleanup,
                "transport_classification": "outer_timeout",
                "outer_timed_out": True,
                "controller_interrupted": False,
            },
            None,
        )
    except (KeyboardInterrupt, SystemExit) as exc:
        cleanup = _terminate_child_process_group(
            process,
            terminate_grace_sec=terminate_grace_sec,
            kill_grace_sec=kill_grace_sec,
        )
        return (
            {
                **cleanup,
                "transport_classification": "controller_interrupted",
                "outer_timed_out": False,
                "controller_interrupted": True,
            },
            exc,
        )
    except ControllerSignalInterruption as exc:
        cleanup = _terminate_child_process_group(
            process,
            terminate_grace_sec=terminate_grace_sec,
            kill_grace_sec=kill_grace_sec,
        )
        return (
            {
                **cleanup,
                "transport_classification": "controller_interrupted",
                "outer_timed_out": False,
                "controller_interrupted": True,
                "controller_signal": exc.signal_number,
            },
            SystemExit(128 + exc.signal_number),
        )
    except BaseException:
        _terminate_child_process_group(
            process,
            terminate_grace_sec=terminate_grace_sec,
            kill_grace_sec=kill_grace_sec,
        )
        raise
    finally:
        for signal_number, previous_handler in previous_signal_handlers.items():
            signal.signal(signal_number, previous_handler)


def bind_child_transport_result(
    result: Mapping[str, Any], outcome: Mapping[str, Any], *, timeout_sec: float
) -> dict[str, Any]:
    """Persist the controller-observed process transport without inference."""
    row = dict(result)
    observed = outcome.get("returncode_observed") is True
    returncode = outcome.get("returncode") if observed else None
    row.update(
        {
            "child_returncode_observed": observed,
            "returncode": returncode,
            "outer_timeout_sec": float(timeout_sec),
            "outer_timed_out": outcome.get("outer_timed_out") is True,
            "controller_interrupted": outcome.get("controller_interrupted") is True,
            "controller_signal": int(outcome.get("controller_signal") or 0),
            "transport_classification": str(
                outcome.get("transport_classification") or "unobserved"
            ),
            "process_group_id": int(outcome.get("process_group_id") or 0),
            "process_group_terminate_sent": (
                outcome.get("process_group_terminate_sent") is True
            ),
            "process_group_kill_sent": outcome.get("process_group_kill_sent") is True,
            "process_group_gone": outcome.get("process_group_gone") is True,
        }
    )
    if row["outer_timed_out"]:
        row["timed_out"] = True
    return row


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _resolve(config_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def acceptance_targets(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_id = {
        str(row.get("spec_target_id") or ""): dict(row)
        for row in load_targets()
    }
    target_ids = [str(value) for value in config.get("dps_targets") or []]
    selected = [by_id[target_id] for target_id in target_ids if target_id in by_id]
    if len(selected) != len(target_ids) or any(row.get("role") != "dps" for row in selected):
        raise ValueError("DPS acceptance targets must resolve to canonical DPS rows")
    return selected


def campaign_attempts(
    targets: Sequence[Mapping[str, Any]],
    mode: str,
    seed: int,
) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for index, target in enumerate(targets, start=1):
        target_id = str(target["spec_target_id"])
        attempts.append(
            {
                "attempt_index": index,
                "attempt_id": f"qualification/{target_id}",
                "cohort_id": f"dps85-{target_id}".replace("_", "-"),
                "seed": int(seed),
                "spec_target_id": target_id,
                "runtime_join_key": str(target["runtime_join_key"]),
                "class_name": str(target["class_name"]),
                "role": "dps",
                "mode": str(mode),
            }
        )
    return attempts


def attempt_accepted(result: Mapping[str, Any]) -> bool:
    return bool(
        result.get("child_returncode_observed") is True
        and result.get("returncode") == 0
        and result.get("transport_classification") == "child_exited"
        and result.get("outer_timed_out") is False
        and result.get("controller_interrupted") is False
        and result.get("process_group_gone") is True
        and result.get("report_returncode") == 0
        and result.get("timed_out") is False
        and result.get("calibration_acceptance_passed") is True
        and result.get("acceptable_final_evidence") is True
        and result.get("all_passed") is True
        and result.get("remote_transport_verified") is True
        and result.get("remote_provenance_verified") is True
        and result.get("remote_evidence_class") == FIXTURE_EVIDENCE_CLASS
        and result.get("remote_excluded_from_training_corpus") is True
        and result.get("remote_runtime_mode") == FIXTURE_RUNTIME_MODE
        and result.get("remote_non_certifying_assistance") is True
        and result.get("published")
        and result.get("remote_reconstruction_verified")
        and result.get("passed")
        and result.get("hard_floor_passed")
        and result.get("optimization_target_met")
        and result.get("targeted_eviction_complete")
    )


def physical_attempt(
    logical_attempt: Mapping[str, Any], ordinal: int
) -> dict[str, Any]:
    """Bind one logical spec slot to one unique process/session identity."""
    if ordinal not in range(1, MAX_PHYSICAL_TRIES + 1):
        raise ValueError(f"physical try ordinal must be 1..{MAX_PHYSICAL_TRIES}")
    logical_index = int(logical_attempt.get("attempt_index") or 0)
    logical_id = str(logical_attempt.get("attempt_id") or "")
    logical_cohort_id = str(logical_attempt.get("cohort_id") or "")
    if logical_index <= 0 or not logical_id or not logical_cohort_id:
        raise ValueError("logical attempt identity is incomplete")
    physical = {
        **dict(logical_attempt),
        "logical_attempt_index": logical_index,
        "logical_attempt_id": logical_id,
        "logical_cohort_id": logical_cohort_id,
        "physical_try_ordinal": ordinal,
        "attempt_index": (logical_index - 1) * MAX_PHYSICAL_TRIES + ordinal,
        "attempt_id": f"{logical_id}/try-{ordinal}",
        "cohort_id": f"{logical_cohort_id}-try-{ordinal}",
    }
    physical["physical_identity_sha256"] = canonical_sha256(physical)
    return physical


def physical_try_dir(
    output_root: Path, logical_attempt: Mapping[str, Any], ordinal: int
) -> Path:
    """Map ordinals deterministically to the compatible base/retry-01 layout."""
    if ordinal not in range(1, MAX_PHYSICAL_TRIES + 1):
        raise ValueError(f"physical try ordinal must be 1..{MAX_PHYSICAL_TRIES}")
    base = attempt_directory_candidates(output_root, logical_attempt)[0]
    if ordinal == 1:
        return base
    return base.parent / f"{base.name}-retry-{ordinal - 1:02d}"


def discovered_physical_try_paths(
    output_root: Path, logical_attempt: Mapping[str, Any]
) -> list[Path]:
    """Return every path that claims to be a try, including forbidden extras."""
    return [
        path
        for path in attempt_directory_candidates(output_root, logical_attempt)
        if path.exists()
    ]


def targeted_eviction_complete(attempt_dir: Path) -> bool:
    batch = attempt_dir / "batch"
    return bool(
        (batch / "retained/publication_receipt.json").is_file()
        and not (batch / "raw").exists()
        and not (batch / "compact").exists()
        and not (batch / ".batch-dvc-cache").exists()
    )


def physical_try_dirs(
    output_root: Path, attempt: Mapping[str, Any]
) -> list[Path]:
    """Return materialized allowed tries in ordinal order."""
    return [
        physical_try_dir(output_root, attempt, ordinal)
        for ordinal in range(1, MAX_PHYSICAL_TRIES + 1)
        for path in [physical_try_dir(output_root, attempt, ordinal)]
        if path.is_dir()
    ]


def physical_try_ordinal(
    output_root: Path, attempt: Mapping[str, Any], attempt_dir: Path
) -> int:
    for ordinal in range(1, MAX_PHYSICAL_TRIES + 1):
        if attempt_dir.resolve() == physical_try_dir(
            output_root, attempt, ordinal
        ).resolve():
            return ordinal
    return 0


def _receipt_identity(payload: Mapping[str, Any], hash_key: str) -> str:
    identity = dict(payload)
    identity.pop(hash_key, None)
    return canonical_sha256(identity)


def write_physical_try_started(
    attempt_dir: Path,
    output_root: Path,
    logical_attempt: Mapping[str, Any],
    physical: Mapping[str, Any],
    command: Sequence[str],
) -> dict[str, Any]:
    path = attempt_dir / STARTED_RECEIPT
    if path.exists():
        raise ValueError(f"physical try start receipt is immutable: {path}")
    receipt = {
        "schema": "cata_raid_dps_physical_try_started_v1",
        "started_at_unix": int(time.time()),
        "reservation_recovered_on_resume": False,
        "launch_observation": "launch_reserved",
        "child_returncode_observed": False,
        "logical_attempt_id": logical_attempt.get("attempt_id"),
        "logical_attempt_index": logical_attempt.get("attempt_index"),
        "physical_attempt": dict(physical),
        "attempt_directory": str(attempt_dir.resolve().relative_to(output_root.resolve())),
        "command": [str(value) for value in command],
    }
    receipt["command_sha256"] = canonical_sha256(receipt["command"])
    receipt["started_receipt_sha256"] = _receipt_identity(
        receipt, "started_receipt_sha256"
    )
    write_json(path, receipt)
    return receipt


def write_recovered_physical_try_reservation(
    attempt_dir: Path,
    output_root: Path,
    logical_attempt: Mapping[str, Any],
    physical: Mapping[str, Any],
) -> dict[str, Any]:
    """Consume an unreceipted directory without claiming a child was observed."""
    path = attempt_dir / STARTED_RECEIPT
    if path.exists():
        raise ValueError(f"physical try reservation receipt is immutable: {path}")
    receipt = {
        "schema": "cata_raid_dps_physical_try_started_v1",
        "started_at_unix": None,
        "reservation_recovered_on_resume": True,
        "launch_observation": "child_not_launched_or_observation_unknown",
        "child_returncode_observed": False,
        "logical_attempt_id": logical_attempt.get("attempt_id"),
        "logical_attempt_index": logical_attempt.get("attempt_index"),
        "physical_attempt": dict(physical),
        "attempt_directory": str(
            attempt_dir.resolve().relative_to(output_root.resolve())
        ),
        "command": [],
    }
    receipt["command_sha256"] = canonical_sha256(receipt["command"])
    receipt["started_receipt_sha256"] = _receipt_identity(
        receipt, "started_receipt_sha256"
    )
    write_json(path, receipt)
    return receipt


def load_physical_try_started(
    attempt_dir: Path,
    output_root: Path,
    logical_attempt: Mapping[str, Any],
    physical: Mapping[str, Any],
) -> dict[str, Any]:
    receipt = _load(attempt_dir / STARTED_RECEIPT)
    stored_hash = str(receipt.get("started_receipt_sha256") or "")
    expected_directory = str(
        attempt_dir.resolve().relative_to(output_root.resolve())
    )
    recovered = receipt.get("reservation_recovered_on_resume") is True
    reservation_valid = bool(
        (
            recovered
            and receipt.get("started_at_unix") is None
            and receipt.get("launch_observation")
            == "child_not_launched_or_observation_unknown"
            and receipt.get("command") == []
        )
        or (
            not recovered
            and type(receipt.get("started_at_unix")) is int
            and int(receipt.get("started_at_unix") or 0) > 0
            and receipt.get("launch_observation") == "launch_reserved"
            and isinstance(receipt.get("command"), list)
            and bool(receipt.get("command"))
        )
    )
    if not (
        receipt.get("schema") == "cata_raid_dps_physical_try_started_v1"
        and reservation_valid
        and receipt.get("child_returncode_observed") is False
        and stored_hash
        and _receipt_identity(receipt, "started_receipt_sha256") == stored_hash
        and receipt.get("logical_attempt_id") == logical_attempt.get("attempt_id")
        and int(receipt.get("logical_attempt_index") or 0)
        == int(logical_attempt.get("attempt_index") or 0)
        and receipt.get("physical_attempt") == dict(physical)
        and receipt.get("attempt_directory") == expected_directory
        and receipt.get("command_sha256")
        == canonical_sha256(receipt.get("command") or [])
    ):
        raise ValueError(f"invalid physical try start receipt: {attempt_dir}")
    return receipt


def physical_sequence_findings(
    rows: Sequence[Mapping[str, Any]], *, materialized_count: int
) -> list[str]:
    """Validate stop-after-success and at-most-two ordering semantics."""
    findings: list[str] = []
    ordinals = [int(row.get("physical_try_ordinal") or 0) for row in rows]
    if materialized_count < 0 or materialized_count > MAX_PHYSICAL_TRIES:
        findings.append("physical_try_limit_exceeded")
    if len(rows) != materialized_count:
        findings.append("materialized_try_not_classified")
    if ordinals != list(range(1, len(rows) + 1)):
        findings.append("physical_try_ordinals_not_contiguous")
    classifications = [str(row.get("classification") or "") for row in rows]
    if any(
        value not in {"accepted", "qualification_failure", "infrastructure_failure"}
        for value in classifications
    ):
        findings.append("physical_try_unclassified")
    accepted_ordinals = [
        ordinal
        for ordinal, row in zip(ordinals, rows)
        if str(row.get("classification") or "") == "accepted"
        or attempt_accepted(row)
    ]
    if len(accepted_ordinals) > 1:
        findings.append("multiple_successful_physical_tries")
    if accepted_ordinals and accepted_ordinals[0] != len(rows):
        findings.append("physical_try_after_success")
    return list(dict.fromkeys(findings))


def calibration_reconstruction_identity(
    attempt: Mapping[str, Any],
    policy_path: Path,
    evidence_manifest: Mapping[str, Any],
) -> str:
    return canonical_sha256(
        {
            "schema": "cata_raid_dps_remote_calibration_reconstruction_v1",
            "attempt": dict(attempt),
            "policy_sha256": sha256_file(policy_path),
            "targets_sha256": sha256_file(DEFAULT_TARGETS),
            "references_sha256": sha256_file(DEFAULT_REFERENCES),
            "scenarios_sha256": sha256_file(DEFAULT_SCENARIOS),
            "evidence_identity_manifest_sha256": evidence_manifest.get(
                "manifest_sha256"
            ),
            "fixture_provenance": fixture_provenance(),
        }
    )


def dps_compact_binding(report: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {
            key: report.get(key)
            for key in (
                "requested_calibration",
                "calibration_acceptance",
                "role_calibration_record",
                "role_calibration_identity",
                "role_calibration_evaluation",
                "evidence_envelope",
                "session",
            )
        }
    )


def verify_hydrated_calibration(
    batch_root: Path,
    attempt: Mapping[str, Any],
    policy_path: Path,
    evidence_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    source_path = batch_root / "raw" / "acceptance_source_report.json"
    source = _load(source_path)
    requested = source.get("requested_calibration") or {}
    record, evaluation = evaluate_runtime_calibration(
        source.get("combat_calibration") or {},
        target_spec=str(attempt.get("runtime_join_key") or ""),
        mode=str(attempt.get("mode") or ""),
        policy_path=policy_path,
    )
    stored_record = source.get("role_calibration_record") or {}
    stored_evaluation = source.get("role_calibration_evaluation") or {}
    role_identity = record.get("identity") or {}
    session = source.get("session") or {}
    envelope = source.get("evidence_envelope") or {}
    calibration = source.get("combat_calibration") or {}
    calibration_acceptance = source.get("calibration_acceptance") or {}
    component_hashes = envelope.get("component_hashes") or {}
    provenance = {
        key: record.get(key)
        for key in (
            "evidence_class",
            "excluded_from_training_corpus",
            "runtime_mode",
            "non_certifying_assistance",
        )
    }
    provenance_verified = bool(
        provenance == fixture_provenance()
        and calibration.get("runtime_mode") == FIXTURE_RUNTIME_MODE
        and calibration.get("non_certifying_assistance") is True
    )
    transport_facts = {
        "returncode": (
            source.get("returncode")
            if type(source.get("returncode")) is int
            else None
        ),
        "timed_out": (
            source.get("timed_out")
            if type(source.get("timed_out")) is bool
            else None
        ),
        "calibration_acceptance_passed": (
            calibration_acceptance.get("passed")
            if isinstance(calibration_acceptance, Mapping)
            and type(calibration_acceptance.get("passed")) is bool
            else None
        ),
        "acceptable_final_evidence": (
            source.get("acceptable_final_evidence")
            if type(source.get("acceptable_final_evidence")) is bool
            else None
        ),
        "all_passed": (
            source.get("all_passed")
            if type(source.get("all_passed")) is bool
            else None
        ),
    }
    transport_verified = transport_facts == {
        "returncode": 0,
        "timed_out": False,
        "calibration_acceptance_passed": True,
        "acceptable_final_evidence": True,
        "all_passed": True,
    }
    try:
        validate_evidence_manifest(
            evidence_manifest,
            runtime_identity={
                **session,
                "profile_generation": role_identity.get("profile_generation"),
                "profile_content_hash": role_identity.get("profile_content_hash"),
            },
        )
        runtime_identity_valid = True
    except (TypeError, ValueError):
        runtime_identity_valid = False
    build_identity_compatible = phase8_envelope_build_compatible(
        evidence_manifest, component_hashes
    )
    verified = bool(
        requested.get("target_spec") == attempt.get("runtime_join_key")
        and requested.get("mode") == attempt.get("mode")
        and int(requested.get("seed") or 0) == int(attempt.get("seed") or 0)
        and canonical_sha256(stored_record) == canonical_sha256(record)
        and canonical_sha256(stored_evaluation) == canonical_sha256(evaluation)
        and provenance_verified
        and transport_verified
        and runtime_identity_valid
        and envelope.get("identity_complete") is True
        and envelope.get("identity_manifest_sha256")
        == evidence_manifest.get("manifest_sha256")
        and build_identity_compatible
        and session.get("cohort_id") == attempt.get("cohort_id")
        and int(session.get("attempt_index") or 0)
        == int(attempt.get("attempt_index") or 0)
    )
    return {
        "schema": "cata_raid_dps_remote_calibration_verification_v1",
        "verified": verified,
        "attempt_id": attempt.get("attempt_id"),
        "source_report_sha256": sha256_file(source_path),
        "record_sha256": canonical_sha256(record),
        "evaluation_sha256": canonical_sha256(evaluation),
        "evaluation": evaluation,
        **provenance,
        "provenance_verified": provenance_verified,
        "source_transport_facts": transport_facts,
        "source_transport_verified": transport_verified,
        "requested_calibration": dict(requested),
        "role_calibration_identity": dict(role_identity),
        "session_identity": {
            key: session.get(key)
            for key in (
                "cohort_id",
                "attempt_index",
                "server_epoch",
                "server_process_id",
                "session_fingerprint",
                "max_active_cohorts",
                "profile_generation",
                "profile_content_hash",
            )
        },
        "evidence_identity_manifest_sha256": envelope.get(
            "identity_manifest_sha256"
        ),
        "evidence_component_hashes": dict(component_hashes),
        "evidence_build_identity_compatible": build_identity_compatible,
        "evidence_scope_ids": dict(envelope.get("scope_ids") or {}),
        "compact_binding_sha256": dps_compact_binding(source),
    }


def reconstruct_remote_calibration(
    attempt_dir: Path,
    attempt: Mapping[str, Any],
    policy_path: Path,
    evidence_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    domain_id = calibration_reconstruction_identity(
        attempt, policy_path, evidence_manifest
    )
    return verify_remote_reconstruction_and_evict(
        REPO_ROOT,
        attempt_dir / "batch",
        domain_verification_id=domain_id,
        verify_hydrated=lambda batch_root: verify_hydrated_calibration(
            batch_root, attempt, policy_path, evidence_manifest
        ),
    )


def compact_acceptance_result(
    attempt: Mapping[str, Any],
    attempt_dir: Path,
    returncode: int | None,
    policy_path: Path,
    evidence_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        result = compact_result(attempt, attempt_dir, returncode)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        result = {
            **dict(attempt),
            "returncode": returncode,
            "published": False,
            "passed": False,
            "hard_floor_passed": False,
            "optimization_target_met": False,
            "reference_ratio": 0.0,
            "failure_reasons": ["invalid_or_incomplete_attempt_report"],
            "record_sha256": None,
            "receipt_sha256": None,
            "report_path": "",
        }
    domain_id = calibration_reconstruction_identity(
        attempt, policy_path, evidence_manifest
    )
    reconstruction_valid, reconstruction = valid_reconstruction_receipt(
        attempt_dir / "batch",
        required_domain_verification_id=domain_id,
    )
    report_path = attempt_dir / "report.json"
    try:
        report = _load(report_path) if report_path.is_file() else {}
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        report = {}
    envelope = report.get("evidence_envelope") or {}
    role_identity = report.get("role_calibration_identity") or {}
    session = report.get("session") or {}
    calibration_acceptance = report.get("calibration_acceptance") or {}
    result["child_returncode_observed"] = isinstance(returncode, int)
    result["returncode"] = returncode
    result["report_returncode"] = (
        report.get("returncode")
        if isinstance(report.get("returncode"), int)
        else None
    )
    result["timed_out"] = (
        report.get("timed_out") if isinstance(report.get("timed_out"), bool) else None
    )
    result["calibration_acceptance_passed"] = (
        calibration_acceptance.get("passed") is True
    )
    result["acceptable_final_evidence"] = (
        report.get("acceptable_final_evidence") is True
    )
    result["all_passed"] = report.get("all_passed") is True
    result["remote_reconstruction_verified"] = reconstruction_valid
    result["reconstruction_receipt_sha256"] = reconstruction.get("receipt_sha256")
    domain_verification = reconstruction.get("domain_verification") or {}
    result["remote_evaluation_sha256"] = domain_verification.get(
        "evaluation_sha256"
    )
    result["remote_source_report_sha256"] = domain_verification.get(
        "source_report_sha256"
    )
    result["remote_compact_binding_sha256"] = domain_verification.get(
        "compact_binding_sha256"
    )
    result["remote_transport_verified"] = (
        domain_verification.get("source_transport_verified") is True
    )
    result["remote_provenance_verified"] = (
        domain_verification.get("provenance_verified") is True
    )
    result["remote_evidence_class"] = domain_verification.get("evidence_class")
    result["remote_excluded_from_training_corpus"] = domain_verification.get(
        "excluded_from_training_corpus"
    )
    result["remote_runtime_mode"] = domain_verification.get("runtime_mode")
    result["remote_non_certifying_assistance"] = domain_verification.get(
        "non_certifying_assistance"
    )
    result["identity_manifest_sha256"] = envelope.get("identity_manifest_sha256")
    result["git_commit_sha256"] = (envelope.get("component_hashes") or {}).get(
        "git_commit_sha256"
    )
    result["profile_generation"] = int(
        role_identity.get("profile_generation")
        or session.get("profile_generation")
        or 0
    )
    result["profile_content_hash"] = str(
        role_identity.get("profile_content_hash")
        or session.get("profile_content_hash")
        or ""
    ).lower()
    result["targeted_eviction_complete"] = targeted_eviction_complete(attempt_dir)
    result["physical_try_ordinal"] = int(
        attempt.get("physical_try_ordinal") or 0
    )
    result["accepted"] = attempt_accepted(result)
    return result


def classify_physical_try(result: Mapping[str, Any]) -> str:
    if attempt_accepted(result):
        return "accepted"
    has_terminal_qualification = bool(
        result.get("child_returncode_observed") is True
        and result.get("transport_classification") == "child_exited"
        and result.get("outer_timed_out") is False
        and result.get("controller_interrupted") is False
        and result.get("process_group_gone") is True
        and result.get("timed_out") is False
        and result.get("published") is True
        and result.get("remote_reconstruction_verified") is True
        and result.get("targeted_eviction_complete") is True
        and (
            result.get("calibration_acceptance_passed") is False
            or result.get("passed") is False
            or result.get("hard_floor_passed") is False
            or result.get("optimization_target_met") is False
            or result.get("acceptable_final_evidence") is False
            or result.get("all_passed") is False
        )
    )
    return "qualification_failure" if has_terminal_qualification else "infrastructure_failure"


def write_physical_try_result(
    attempt_dir: Path,
    started: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    path = attempt_dir / RESULT_RECEIPT
    if path.exists():
        raise ValueError(f"physical try result receipt is immutable: {path}")
    row = dict(result)
    row["started_receipt_sha256"] = started.get("started_receipt_sha256")
    row["attempt_directory"] = started.get("attempt_directory")
    row["reservation_recovered_on_resume"] = (
        started.get("reservation_recovered_on_resume") is True
    )
    row["launch_observation"] = started.get("launch_observation")
    row["classification"] = classify_physical_try(row)
    row["accepted"] = row["classification"] == "accepted"
    receipt = {
        "schema": "cata_raid_dps_physical_try_result_v1",
        "completed_at_unix": int(time.time()),
        "started_receipt_sha256": started.get("started_receipt_sha256"),
        "physical_identity_sha256": (
            (started.get("physical_attempt") or {}).get("physical_identity_sha256")
        ),
        "child_returncode_observed": row.get("child_returncode_observed") is True,
        "child_returncode": row.get("returncode"),
        "classification": row["classification"],
        "result": row,
    }
    receipt["result_receipt_sha256"] = _receipt_identity(
        receipt, "result_receipt_sha256"
    )
    write_json(path, receipt)
    return receipt


def load_physical_try_result(
    attempt_dir: Path,
    started: Mapping[str, Any],
    physical: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = _load(attempt_dir / RESULT_RECEIPT)
    stored_hash = str(receipt.get("result_receipt_sha256") or "")
    result = receipt.get("result") or {}
    if not isinstance(result, Mapping):
        raise ValueError(f"invalid physical try result payload: {attempt_dir}")
    result = dict(result)
    observed = receipt.get("child_returncode_observed") is True
    returncode = receipt.get("child_returncode")
    expected_classification = classify_physical_try(result)
    if not (
        receipt.get("schema") == "cata_raid_dps_physical_try_result_v1"
        and stored_hash
        and _receipt_identity(receipt, "result_receipt_sha256") == stored_hash
        and receipt.get("started_receipt_sha256")
        == started.get("started_receipt_sha256")
        and receipt.get("physical_identity_sha256")
        == physical.get("physical_identity_sha256")
        and observed == (result.get("child_returncode_observed") is True)
        and (isinstance(returncode, int) if observed else returncode is None)
        and result.get("returncode") == returncode
        and result.get("attempt_id") == physical.get("attempt_id")
        and result.get("cohort_id") == physical.get("cohort_id")
        and int(result.get("attempt_index") or 0)
        == int(physical.get("attempt_index") or 0)
        and int(result.get("physical_try_ordinal") or 0)
        == int(physical.get("physical_try_ordinal") or 0)
        and result.get("physical_identity_sha256")
        == physical.get("physical_identity_sha256")
        and result.get("started_receipt_sha256")
        == started.get("started_receipt_sha256")
        and result.get("attempt_directory") == started.get("attempt_directory")
        and result.get("reservation_recovered_on_resume")
        is (started.get("reservation_recovered_on_resume") is True)
        and result.get("launch_observation") == started.get("launch_observation")
        and receipt.get("classification") == result.get("classification")
        and result.get("classification") == expected_classification
        and result.get("accepted") is attempt_accepted(result)
    ):
        raise ValueError(f"invalid physical try result receipt: {attempt_dir}")
    return result, receipt


def write_campaign_state(
    output_root: Path,
    attempts: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    *,
    active_attempt: Mapping[str, Any] | None,
    config_path: Path,
    policy_path: Path,
    verification: Mapping[str, Any],
    plan: Mapping[str, Any],
    evidence_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    logical_order = {
        str(attempt.get("attempt_id") or ""): index
        for index, attempt in enumerate(attempts)
    }
    ordered_results = sorted(
        (dict(row) for row in results),
        key=lambda row: (
            logical_order.get(str(row.get("logical_attempt_id") or ""), len(attempts)),
            int(row.get("physical_try_ordinal") or 0),
            str(row.get("attempt_id") or ""),
        ),
    )
    physical_ids = [str(row.get("attempt_id") or "") for row in ordered_results]
    duplicate_physical_ids = len(physical_ids) != len(set(physical_ids))
    unexpected_try_paths: list[str] = []
    materialized_count = 0
    all_sequence_findings: list[str] = []
    logical_success_count = 0
    target_rows = []
    for logical in attempts:
        target_id = str(logical["spec_target_id"])
        logical_id = str(logical["attempt_id"])
        rows = [
            row
            for row in ordered_results
            if row.get("logical_attempt_id") == logical_id
        ]
        discovered = discovered_physical_try_paths(output_root, logical)
        expected_paths = {
            physical_try_dir(output_root, logical, ordinal).resolve()
            for ordinal in range(1, MAX_PHYSICAL_TRIES + 1)
        }
        unexpected_try_paths.extend(
            str(path.relative_to(output_root))
            for path in discovered
            if path.resolve() not in expected_paths
        )
        materialized = physical_try_dirs(output_root, logical)
        materialized_count += len(materialized)
        findings = physical_sequence_findings(
            rows, materialized_count=len(materialized)
        )
        all_sequence_findings.extend(f"{target_id}:{value}" for value in findings)
        accepted_rows = [row for row in rows if attempt_accepted(row)]
        logical_success_count += len(accepted_rows) == 1
        accepted_row = accepted_rows[0] if len(accepted_rows) == 1 else {}
        target_rows.append(
            {
                "spec_target_id": target_id,
                "logical_attempt_id": logical_id,
                "physical_try_count": len(rows),
                "classified_physical_try_count": sum(
                    str(row.get("classification") or "")
                    in {
                        "accepted",
                        "qualification_failure",
                        "infrastructure_failure",
                    }
                    for row in rows
                ),
                "accepted_physical_try_count": len(accepted_rows),
                "accepted_physical_try_ordinal": int(
                    accepted_row.get("physical_try_ordinal") or 0
                ),
                "minimum_reference_ratio": min(
                    (float(row.get("reference_ratio") or 0.0) for row in rows),
                    default=0.0,
                ),
                "hard_floor_passed": accepted_row.get("hard_floor_passed") is True,
                "optimization_target_met": (
                    accepted_row.get("optimization_target_met") is True
                ),
                "remote_verified_and_evicted": bool(
                    accepted_row.get("published")
                    and accepted_row.get("remote_reconstruction_verified")
                    and accepted_row.get("targeted_eviction_complete")
                ),
                "terminal": bool(
                    accepted_rows or len(materialized) == MAX_PHYSICAL_TRIES
                ),
                "sequence_findings": findings,
            }
        )
    state = {
        "schema": "cata_raid_dps_acceptance_campaign_state_v2",
        "generated_at_unix": int(time.time()),
        "config_path": str(config_path.relative_to(REPO_ROOT)),
        "config_sha256": sha256_file(config_path),
        "policy_path": str(policy_path.relative_to(REPO_ROOT)),
        "policy_sha256": sha256_file(policy_path),
        "verification_sha256": verification.get("verification_sha256"),
        "verification_input_hashes": dict(verification.get("input_hashes") or {}),
        "campaign_plan_sha256": plan.get("plan_sha256"),
        "git_head": plan.get("git_head"),
        "git_commit_sha256": sha256_text(str(plan.get("git_head") or "")),
        "evidence_identity_manifest_sha256": evidence_manifest.get("manifest_sha256"),
        "profile_generation": int(
            (evidence_manifest.get("runtime_identity") or {}).get(
                "profile_generation"
            )
            or 0
        ),
        "profile_content_hash": str(
            (evidence_manifest.get("runtime_identity") or {}).get(
                "profile_content_hash"
            )
            or ""
        ).lower(),
        "hard_reference_ratio": 0.75,
        "optimization_reference_ratio": 0.85,
        **fixture_provenance(),
        "max_tries_per_dps_spec": int(plan.get("max_tries_per_dps_spec") or 0),
        "child_outer_timeout_sec": int(plan.get("child_outer_timeout_sec") or 0),
        "physical_try_count": materialized_count,
        "classified_physical_try_count": len(ordered_results),
        "physical_success_count": sum(attempt_accepted(row) for row in ordered_results),
        "logical_attempt_count": len(attempts),
        "logical_success_count": logical_success_count,
        "target_count": len(target_rows),
        # Compatibility fields remain logical, never physical.
        "attempt_count": len(attempts),
        "accepted_attempt_count": logical_success_count,
        "remaining_attempt_count": len(attempts) - logical_success_count,
        "active_attempt": dict(active_attempt) if active_attempt else None,
        "target_rows": target_rows,
        "results": ordered_results,
        "physical_try_ledger": ordered_results,
        "unexpected_try_paths": unexpected_try_paths,
        "sequence_findings": all_sequence_findings,
        "duplicate_physical_attempt_ids": duplicate_physical_ids,
    }
    expected_physical_by_id = {
        str(physical["attempt_id"]): physical
        for logical in attempts
        for ordinal in range(1, MAX_PHYSICAL_TRIES + 1)
        for physical in [physical_attempt(logical, ordinal)]
    }
    state["all_attempt_identities_match"] = bool(ordered_results) and all(
        (
            expected := expected_physical_by_id.get(
                str(row.get("attempt_id") or "")
            )
        )
        is not None
        and row.get("physical_identity_sha256")
        == expected.get("physical_identity_sha256")
        and row.get("cohort_id") == expected.get("cohort_id")
        and int(row.get("attempt_index") or 0)
        == int(expected.get("attempt_index") or 0)
        and (
            str(row.get("classification") or "") == "infrastructure_failure"
            or (
                row.get("identity_manifest_sha256")
                == state["evidence_identity_manifest_sha256"]
                and row.get("git_commit_sha256") == state["git_commit_sha256"]
                and int(row.get("profile_generation") or 0)
                == state["profile_generation"]
                and str(row.get("profile_content_hash") or "").lower()
                == state["profile_content_hash"]
            )
        )
        for row in ordered_results
    )
    state["passed"] = bool(
        state["logical_attempt_count"] == state["logical_success_count"] == 16
        and state["physical_success_count"] == 16
        and state["physical_try_count"] == state["classified_physical_try_count"]
        and 16 <= state["physical_try_count"] <= 32
        and state["target_count"] == 16
        and all(row["hard_floor_passed"] for row in target_rows)
        and all(row["optimization_target_met"] for row in target_rows)
        and all(row["remote_verified_and_evicted"] for row in target_rows)
        and state["max_tries_per_dps_spec"] == 2
        and state["child_outer_timeout_sec"] > 0
        and all(
            float(row.get("outer_timeout_sec") or 0.0)
            == float(state["child_outer_timeout_sec"])
            for row in ordered_results
            if attempt_accepted(row)
        )
        and all(state.get(key) == value for key, value in fixture_provenance().items())
        and not state["unexpected_try_paths"]
        and not state["sequence_findings"]
        and not state["duplicate_physical_attempt_ids"]
        and state["active_attempt"] is None
        and state["all_attempt_identities_match"]
    )
    state["state_sha256"] = canonical_sha256(state)
    write_json(output_root / "campaign_state.json", state)
    return state


def verify_campaign_state(
    state_path: Path,
    *,
    required_git_head: str = "",
    required_profile_content_hash: str = "",
) -> dict[str, Any]:
    """Independently reconstruct one qualification for each unique DPS spec."""
    state_path = state_path.resolve()
    output_root = state_path.parent
    reasons: list[str] = []
    try:
        state = _load(state_path)
        plan = _load(output_root / "campaign_plan.json")
        manifest = validate_evidence_manifest(
            _load(output_root / "evidence_identity_manifest.json")
        )
        config_path = _resolve(
            state_path,
            str(state.get("config_path") or DEFAULT_CONFIG.relative_to(REPO_ROOT)),
        ).resolve()
        verification = verify_acceptance(config_path)
        config = _load(config_path)
        policy_path = _resolve(
            config_path, str(config["role_calibration_policy"])
        ).resolve()
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {
            "schema": "cata_raid_dps_acceptance_campaign_verification_v2",
            "passed": False,
            "failure_reasons": [f"campaign_inputs_invalid:{type(exc).__name__}"],
        }

    state_identity = dict(state)
    stored_state_sha256 = str(state_identity.pop("state_sha256", ""))
    if (
        state.get("schema") != "cata_raid_dps_acceptance_campaign_state_v2"
        or not stored_state_sha256
        or canonical_sha256(state_identity) != stored_state_sha256
    ):
        reasons.append("campaign_state_identity_invalid")
    plan_identity = dict(plan)
    stored_plan_sha256 = str(plan_identity.pop("plan_sha256", ""))
    if (
        plan.get("schema") != "cata_raid_dps_acceptance_campaign_plan_v1"
        or not stored_plan_sha256
        or canonical_sha256(plan_identity) != stored_plan_sha256
    ):
        reasons.append("campaign_plan_identity_invalid")
    expected_child_outer_timeout_sec = int(
        plan.get("child_outer_timeout_sec") or 0
    )
    if (
        expected_child_outer_timeout_sec <= 0
        or int(state.get("child_outer_timeout_sec") or 0)
        != expected_child_outer_timeout_sec
    ):
        reasons.append("campaign_child_outer_timeout_invalid")

    expected_attempts = campaign_attempts(
        acceptance_targets(config),
        str(config.get("qualification_mode") or ""),
        int(config.get("qualification_seed") or 0),
    )
    if (
        len(expected_attempts) != 16
        or len({row["spec_target_id"] for row in expected_attempts}) != 16
        or plan.get("attempts") != expected_attempts
    ):
        reasons.append("campaign_plan_not_exact_16_spec_qualification")
    if (
        verification.get("passed") is not True
        or state.get("verification_sha256") != verification.get("verification_sha256")
        or plan.get("verification_sha256") != verification.get("verification_sha256")
        or state.get("verification_input_hashes") != verification.get("input_hashes")
        or plan.get("verification_input_hashes") != verification.get("input_hashes")
    ):
        reasons.append("current_dps_reference_contract_mismatch")
    if any(
        plan.get(key) != value or state.get(key) != value
        for key, value in fixture_provenance().items()
    ):
        reasons.append("campaign_fixture_provenance_mismatch")

    expected_git_head = str(required_git_head or git_head(REPO_ROOT))
    expected_git_sha256 = sha256_text(expected_git_head) if expected_git_head else ""
    expected_profile_generation = int(
        (manifest.get("runtime_identity") or {}).get("profile_generation") or 0
    )
    expected_profile_hash = str(
        required_profile_content_hash
        or (manifest.get("runtime_identity") or {}).get("profile_content_hash")
        or ""
    ).lower()
    if (
        not expected_git_head
        or plan.get("git_head") != expected_git_head
        or state.get("git_head") != expected_git_head
        or state.get("git_commit_sha256") != expected_git_sha256
    ):
        reasons.append("campaign_git_identity_mismatch")
    if (
        plan.get("evidence_identity_manifest_sha256") != manifest.get("manifest_sha256")
        or state.get("evidence_identity_manifest_sha256") != manifest.get("manifest_sha256")
        or int(plan.get("profile_generation") or 0) != expected_profile_generation
        or int(state.get("profile_generation") or 0) != expected_profile_generation
        or str(plan.get("profile_content_hash") or "").lower() != expected_profile_hash
        or str(state.get("profile_content_hash") or "").lower() != expected_profile_hash
    ):
        reasons.append("campaign_profile_or_manifest_identity_mismatch")

    results = [dict(row) for row in state.get("results") or [] if isinstance(row, Mapping)]
    ledger = [
        dict(row)
        for row in state.get("physical_try_ledger") or []
        if isinstance(row, Mapping)
    ]
    result_ids = [str(row.get("attempt_id") or "") for row in results]
    result_by_id = dict(zip(result_ids, results))
    if (
        results != ledger
        or len(results) != len(result_by_id)
        or "" in result_by_id
        or not 16 <= len(results) <= 32
    ):
        reasons.append("physical_try_ledger_invalid")

    verified_attempts = 0
    verified_physical_tries = 0
    receipt_hashes: list[str] = []
    reconstruction_hashes: list[str] = []
    for logical in expected_attempts:
        logical_id = str(logical["attempt_id"])
        discovered = discovered_physical_try_paths(output_root, logical)
        expected_paths = [
            physical_try_dir(output_root, logical, ordinal)
            for ordinal in range(1, MAX_PHYSICAL_TRIES + 1)
        ]
        materialized = [path for path in expected_paths if path.is_dir()]
        extras = [path for path in discovered if path.resolve() not in {value.resolve() for value in expected_paths}]
        if extras:
            reasons.append(f"unexpected_physical_try_path:{logical_id}")
        if (
            not 1 <= len(materialized) <= MAX_PHYSICAL_TRIES
            or materialized != expected_paths[: len(materialized)]
        ):
            reasons.append(f"physical_try_layout_invalid:{logical_id}")

        rows: list[dict[str, Any]] = []
        for ordinal, attempt_dir in enumerate(materialized, start=1):
            physical = physical_attempt(logical, ordinal)
            try:
                started = load_physical_try_started(
                    attempt_dir, output_root, logical, physical
                )
                result, result_receipt = load_physical_try_result(
                    attempt_dir, started, physical
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                reasons.append(f"physical_try_receipt_invalid:{physical['attempt_id']}")
                continue
            rows.append(result)
            if result_by_id.get(str(physical["attempt_id"])) != result:
                reasons.append(f"physical_try_state_binding_invalid:{physical['attempt_id']}")
                continue
            verified_physical_tries += 1
            if not attempt_accepted(result):
                continue

            report_path = attempt_dir / "report.json"
            try:
                report = _load(report_path)
            except (OSError, ValueError, json.JSONDecodeError):
                reasons.append(f"attempt_report_invalid:{physical['attempt_id']}")
                continue
            expected_report_path = str(report_path.resolve().relative_to(REPO_ROOT))
            publication_valid = valid_publication(attempt_dir, physical)
            domain_id = calibration_reconstruction_identity(
                physical, policy_path, manifest
            )
            reconstruction_valid, reconstruction = valid_reconstruction_receipt(
                attempt_dir / "batch",
                required_domain_verification_id=domain_id,
            )
            remote_verification = reconstruction.get("domain_verification") or {}
            remote_evaluation = remote_verification.get("evaluation") or {}
            remote_requested = remote_verification.get("requested_calibration") or {}
            remote_identity = remote_verification.get("role_calibration_identity") or {}
            remote_session = remote_verification.get("session_identity") or {}
            remote_components = remote_verification.get("evidence_component_hashes") or {}
            evaluation = report.get("role_calibration_evaluation") or {}
            envelope = report.get("evidence_envelope") or {}
            components = envelope.get("component_hashes") or {}
            identity = report.get("role_calibration_identity") or {}
            session = report.get("session") or {}
            remote_expected_identity = bool(
                remote_requested.get("mode") == physical.get("mode")
                and remote_requested.get("target_spec") == physical.get("runtime_join_key")
                and int(remote_requested.get("seed") or 0) == int(physical.get("seed") or 0)
                and remote_identity.get("spec_target_id") == physical.get("spec_target_id")
                and remote_identity.get("runtime_join_key") == physical.get("runtime_join_key")
                and int(remote_identity.get("seed") or 0) == int(physical.get("seed") or 0)
                and remote_session.get("cohort_id") == physical.get("cohort_id")
                and int(remote_session.get("attempt_index") or 0) == int(physical.get("attempt_index") or 0)
                and remote_verification.get("evidence_identity_manifest_sha256") == manifest.get("manifest_sha256")
                and remote_verification.get("source_transport_verified") is True
                and remote_verification.get("provenance_verified") is True
                and all(
                    remote_verification.get(key) == value
                    for key, value in fixture_provenance().items()
                )
                and phase8_envelope_build_compatible(manifest, remote_components)
            )
            local_binding_valid = bool(
                dps_compact_binding(report) == remote_verification.get("compact_binding_sha256")
                and result.get("remote_compact_binding_sha256") == remote_verification.get("compact_binding_sha256")
            )
            local_expected_identity = bool(
                result.get("report_path") == expected_report_path
                and result.get("attempt_index") == physical.get("attempt_index")
                and result.get("attempt_id") == physical.get("attempt_id")
                and result.get("cohort_id") == physical.get("cohort_id")
                and result.get("logical_attempt_id") == logical_id
                and result.get("spec_target_id") == physical.get("spec_target_id")
                and result.get("runtime_join_key") == physical.get("runtime_join_key")
                and result.get("mode") == physical.get("mode")
                and int(result.get("seed") or 0) == int(physical.get("seed") or 0)
                and float(result.get("outer_timeout_sec") or 0.0)
                == float(expected_child_outer_timeout_sec)
                and identity.get("spec_target_id") == physical.get("spec_target_id")
                and identity.get("runtime_join_key") == physical.get("runtime_join_key")
                and int(identity.get("seed") or 0) == int(physical.get("seed") or 0)
                and session.get("cohort_id") == physical.get("cohort_id")
                and int(session.get("attempt_index") or 0) == int(physical.get("attempt_index") or 0)
            )
            evidence_identity = bool(
                envelope.get("identity_complete") is True
                and envelope.get("identity_manifest_sha256") == manifest.get("manifest_sha256")
                and phase8_envelope_build_compatible(manifest, components)
                and components.get("git_commit_sha256") == expected_git_sha256
                and int(identity.get("profile_generation") or session.get("profile_generation") or 0) == expected_profile_generation
                and str(identity.get("profile_content_hash") or session.get("profile_content_hash") or "").lower() == expected_profile_hash
            )
            evaluation_valid = bool(
                remote_verification.get("verified") is True
                and canonical_sha256(evaluation) == canonical_sha256(remote_evaluation)
                and result.get("remote_evaluation_sha256") == remote_verification.get("evaluation_sha256")
                and result.get("remote_source_report_sha256") == remote_verification.get("source_report_sha256")
                and evaluation.get("passed") is True
                and evaluation.get("hard_floor_passed") is True
                and evaluation.get("optimization_target_met") is True
                and float(evaluation.get("reference_ratio") or 0.0) >= 0.85
                and not evaluation.get("failure_reasons")
                and attempt_accepted(result)
            )
            if not (
                publication_valid
                and reconstruction_valid
                and targeted_eviction_complete(attempt_dir)
                and remote_expected_identity
                and local_expected_identity
                and local_binding_valid
                and evidence_identity
                and evaluation_valid
            ):
                reasons.append(f"attempt_verification_failed:{physical['attempt_id']}")
                continue
            receipt_hashes.append(str(result.get("receipt_sha256") or ""))
            reconstruction_hashes.append(str(reconstruction.get("receipt_sha256") or ""))

        findings = physical_sequence_findings(
            rows, materialized_count=len(materialized)
        )
        reasons.extend(f"{finding}:{logical_id}" for finding in findings)
        if sum(attempt_accepted(row) for row in rows) == 1:
            verified_attempts += 1

    if set(result_by_id) != {
        physical_attempt(logical, ordinal)["attempt_id"]
        for logical in expected_attempts
        for ordinal in range(1, MAX_PHYSICAL_TRIES + 1)
        if physical_try_dir(output_root, logical, ordinal).is_dir()
    }:
        reasons.append("physical_try_ledger_does_not_match_materialized_tries")

    if (
        state.get("passed") is not True
        or state.get("all_attempt_identities_match") is not True
        or int(state.get("logical_attempt_count") or 0) != 16
        or int(state.get("logical_success_count") or 0) != 16
        or int(state.get("physical_success_count") or 0) != 16
        or int(state.get("physical_try_count") or 0) != len(results)
        or int(state.get("classified_physical_try_count") or 0) != len(results)
        or int(state.get("attempt_count") or 0) != 16
        or int(state.get("accepted_attempt_count") or 0) != 16
        or int(state.get("target_count") or 0) != 16
        or int(state.get("max_tries_per_dps_spec") or 0) != 2
    ):
        reasons.append("campaign_aggregate_claim_invalid")
    unique_reasons = list(dict.fromkeys(reasons))
    report = {
        "schema": "cata_raid_dps_acceptance_campaign_verification_v2",
        "passed": not unique_reasons and verified_attempts == 16,
        "failure_reasons": unique_reasons,
        "verified_attempt_count": verified_attempts,
        "verified_logical_success_count": verified_attempts,
        "verified_physical_try_count": verified_physical_tries,
        "expected_attempt_count": 16,
        "target_count": 16,
        "hard_reference_ratio": 0.75,
        "optimization_reference_ratio": 0.85,
        **fixture_provenance(),
        "git_head": expected_git_head,
        "profile_generation": expected_profile_generation,
        "profile_content_hash": expected_profile_hash,
        "evidence_identity_manifest_sha256": manifest.get("manifest_sha256"),
        "campaign_state_sha256": stored_state_sha256,
        "campaign_plan_sha256": stored_plan_sha256,
        "publication_receipts_sha256": canonical_sha256(sorted(receipt_hashes)),
        "reconstruction_receipts_sha256": canonical_sha256(
            sorted(reconstruction_hashes)
        ),
    }
    report["verification_sha256"] = canonical_sha256(report)
    return report


def child_command(
    args: argparse.Namespace,
    attempt: Mapping[str, Any],
    attempt_dir: Path,
    policy_path: Path,
    manifest_path: Path,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "tools.bot_ml.run_live_bot_validation",
        "--transport",
        "session",
        "--worldserver",
        str(args.worldserver),
        "--config",
        str(args.worldserver_config),
        "--output-dir",
        str(attempt_dir),
        "--duration-policy",
        "completion-watchdog",
        "--timeout-sec",
        str(args.timeout_sec),
        "--heartbeat-sec",
        str(args.heartbeat_sec),
        "--session-transition-timeout-sec",
        str(args.session_transition_timeout_sec),
        "--session-environment",
        args.session_environment,
        "--session-profile",
        "phase8_calibration",
        "--cohort-id",
        str(attempt["cohort_id"]),
        "--session-attempt-index",
        str(attempt["attempt_index"]),
        "--calibration-only",
        "--calibration-reference-conditions",
        "--calibration-mode",
        str(attempt["mode"]),
        "--calibration-target-spec",
        str(attempt["runtime_join_key"]),
        "--calibration-seed",
        str(attempt["seed"]),
        "--role-calibration-policy",
        str(policy_path),
        "--bot-pool-tag",
        "all_spec_candidate_pool",
        "--publish-batch",
        "--evidence-identity-manifest",
        str(manifest_path),
    ]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--worldserver", type=Path, default=Path("build/src/server/worldserver/worldserver")
    )
    parser.add_argument(
        "--worldserver-config", type=Path, default=Path("trinity-worldserver-test.conf")
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--session-environment", default="cata-raid-dps85")
    parser.add_argument("--evidence-identity-manifest", type=Path)
    parser.add_argument("--timeout-sec", type=int, default=900)
    parser.add_argument(
        "--child-outer-timeout-sec",
        type=int,
        default=DEFAULT_CHILD_OUTER_TIMEOUT_SEC,
        help="Hard wall-clock limit for each qualification child process.",
    )
    parser.add_argument("--heartbeat-sec", type=int, default=30)
    parser.add_argument("--session-transition-timeout-sec", type=int, default=360)
    parser.add_argument(
        "--limit", type=int, default=0, help="Run at most this many pending attempts; zero runs all."
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def run_campaign(args: argparse.Namespace) -> int:

    config_path = args.acceptance_config.resolve()
    verification = verify_acceptance(config_path)
    if not verification["passed"]:
        raise SystemExit("DPS acceptance contract verification failed")
    config = _load(config_path)
    acceptance = config.get("acceptance") or {}
    if acceptance.get("evict_after_remote_verification") is not True or acceptance.get(
        "retain_published_batch"
    ) is not False:
        raise SystemExit("DPS acceptance must use verified targeted eviction")

    policy_path = _resolve(config_path, str(config["role_calibration_policy"])).resolve()
    targets = acceptance_targets(config)
    qualification_mode = str(config.get("qualification_mode") or "")
    qualification_seed = int(config.get("qualification_seed") or 0)
    max_tries = int(config.get("max_tries_per_dps_spec") or 0)
    if max_tries != 2:
        raise SystemExit("DPS acceptance permits exactly one initial try and one retry")
    if int(args.child_outer_timeout_sec) <= 0:
        raise SystemExit("--child-outer-timeout-sec must be positive")
    attempts = campaign_attempts(targets, qualification_mode, qualification_seed)
    output_root = args.output_root.resolve()
    plan = {
        "schema": "cata_raid_dps_acceptance_campaign_plan_v1",
        "verification_sha256": verification["verification_sha256"],
        "verification_input_hashes": verification["input_hashes"],
        "git_head": git_head(REPO_ROOT),
        "target_count": len(targets),
        "attempt_count": len(attempts),
        "hard_reference_ratio": 0.75,
        "optimization_reference_ratio": 0.85,
        "qualification_mode": qualification_mode,
        "qualification_seed": qualification_seed,
        "max_tries_per_dps_spec": max_tries,
        "child_outer_timeout_sec": int(args.child_outer_timeout_sec),
        **fixture_provenance(),
        "publish_batch": True,
        "retain_published_batch": False,
        "attempts": attempts,
    }
    if args.dry_run:
        plan["plan_sha256"] = canonical_sha256(plan)
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    if not args.evidence_identity_manifest:
        raise SystemExit("--evidence-identity-manifest is required for live DPS acceptance")
    try:
        manifest = validate_evidence_manifest(
            _load(args.evidence_identity_manifest.resolve())
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid --evidence-identity-manifest: {exc}") from exc
    require_current_phase8_source_identity(REPO_ROOT, args.worldserver, manifest)
    plan["evidence_identity_manifest_sha256"] = manifest["manifest_sha256"]
    plan["profile_generation"] = int(manifest["runtime_identity"]["profile_generation"])
    plan["profile_content_hash"] = str(
        manifest["runtime_identity"]["profile_content_hash"]
    ).lower()
    plan["plan_sha256"] = canonical_sha256(plan)

    output_root.mkdir(parents=True, exist_ok=True)
    plan_path = output_root / "campaign_plan.json"
    if plan_path.is_file():
        if _load(plan_path) != plan:
            raise SystemExit(
                "campaign plan is immutable; use a new output root for changed inputs"
            )
    else:
        write_json(plan_path, plan)
    write_json(output_root / "acceptance_verification.json", verification)

    campaign_manifest_path = output_root / "evidence_identity_manifest.json"
    if campaign_manifest_path.is_file():
        existing = validate_evidence_manifest(_load(campaign_manifest_path))
        if existing["manifest_sha256"] != manifest["manifest_sha256"]:
            raise SystemExit("campaign evidence manifest cannot change while resuming")
    else:
        write_json(campaign_manifest_path, manifest)

    if not os.environ.get("TRINITY_SOAP_USER") or not os.environ.get("TRINITY_SOAP_PASSWORD"):
        raise SystemExit("TRINITY_SOAP_USER and TRINITY_SOAP_PASSWORD are required")

    results: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for logical in attempts:
        expected_paths = {
            physical_try_dir(output_root, logical, ordinal).resolve()
            for ordinal in range(1, max_tries + 1)
        }
        extras = [
            path
            for path in discovered_physical_try_paths(output_root, logical)
            if path.resolve() not in expected_paths
        ]
        if extras:
            raise SystemExit(
                f"unexpected DPS physical try paths for {logical['spec_target_id']}: "
                + ",".join(str(path) for path in extras)
            )
        materialized = physical_try_dirs(output_root, logical)
        expected_prefix = [
            physical_try_dir(output_root, logical, ordinal)
            for ordinal in range(1, len(materialized) + 1)
        ]
        if materialized != expected_prefix:
            raise SystemExit(
                f"non-contiguous DPS physical tries: {logical['spec_target_id']}"
            )
        logical_results: list[dict[str, Any]] = []
        for ordinal, attempt_dir in enumerate(materialized, start=1):
            physical = physical_attempt(logical, ordinal)
            started_path = attempt_dir / STARTED_RECEIPT
            if not started_path.is_file():
                # mkdir is the reservation boundary. A crash between mkdir and
                # the ordinary start receipt permanently consumes this ordinal.
                started = write_recovered_physical_try_reservation(
                    attempt_dir, output_root, logical, physical
                )
                unlaunched = compact_acceptance_result(
                    physical, attempt_dir, None, policy_path, manifest
                )
                unlaunched["runner_log_evicted_after_publication"] = False
                unlaunched["resume_failure_reason"] = (
                    "child_not_launched_or_observation_unknown"
                )
                unlaunched["reconstruction_error"] = ""
                write_physical_try_result(attempt_dir, started, unlaunched)
            try:
                started = load_physical_try_started(
                    attempt_dir, output_root, logical, physical
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise SystemExit(
                    f"cannot resume unbound DPS try {physical['attempt_id']}: {exc}"
                ) from exc
            result_path = attempt_dir / RESULT_RECEIPT
            if not result_path.is_file():
                # The controller did not durably observe the process return code.
                # Preserve that fact as an infrastructure failure; never infer 0
                # from a report or publication left behind by the interrupted run.
                reconstruction_error = ""
                if valid_publication(attempt_dir, physical):
                    try:
                        reconstruct_remote_calibration(
                            attempt_dir, physical, policy_path, manifest
                        )
                    except (OSError, RuntimeError, TypeError, ValueError) as exc:
                        reconstruction_error = (
                            f"remote_reconstruction_failed:{type(exc).__name__}"
                        )
                interrupted = compact_acceptance_result(
                    physical, attempt_dir, None, policy_path, manifest
                )
                interrupted["runner_log_evicted_after_publication"] = False
                interrupted["resume_failure_reason"] = (
                    "controller_interrupted_before_child_returncode_was_recorded"
                )
                interrupted["reconstruction_error"] = reconstruction_error
                write_physical_try_result(attempt_dir, started, interrupted)
            try:
                result, _result_receipt = load_physical_try_result(
                    attempt_dir, started, physical
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise SystemExit(
                    f"invalid immutable DPS result {physical['attempt_id']}: {exc}"
                ) from exc
            logical_results.append(result)
            results.append(result)
        findings = physical_sequence_findings(
            logical_results, materialized_count=len(materialized)
        )
        if findings:
            raise SystemExit(
                f"invalid DPS try sequence for {logical['spec_target_id']}: "
                + ",".join(findings)
            )
        if not any(attempt_accepted(row) for row in logical_results) and len(materialized) < max_tries:
            pending.append(logical)
    if args.limit > 0:
        pending = pending[: args.limit]
    write_campaign_state(
        output_root,
        attempts,
        results,
        active_attempt=None,
        config_path=config_path,
        policy_path=policy_path,
        verification=verification,
        plan=plan,
        evidence_manifest=manifest,
    )

    for logical in pending:
        accepted = False
        while len(physical_try_dirs(output_root, logical)) < max_tries:
            # Recheck immediately before consuming an ordinal.  The campaign
            # controller lock prevents another controller from racing this
            # observation with reservation or child execution.
            require_current_phase8_source_identity(
                REPO_ROOT, args.worldserver, manifest
            )
            ordinal = len(physical_try_dirs(output_root, logical)) + 1
            physical = physical_attempt(logical, ordinal)
            attempt_dir = physical_try_dir(output_root, logical, ordinal)
            attempt_dir.mkdir(parents=True, exist_ok=False)
            command = child_command(
                args, physical, attempt_dir, policy_path, campaign_manifest_path
            )
            started = write_physical_try_started(
                attempt_dir, output_root, logical, physical, command
            )
            write_campaign_state(
                output_root,
                attempts,
                results,
                active_attempt=physical,
                config_path=config_path,
                policy_path=policy_path,
                verification=verification,
                plan=plan,
                evidence_manifest=manifest,
            )
            runner_log = attempt_dir / "runner.log"
            with runner_log.open("w", encoding="utf-8") as stream:
                outcome, interruption = run_child_process_group(
                    command,
                    cwd=REPO_ROOT,
                    env=os.environ.copy(),
                    output_stream=stream,
                    timeout_sec=args.child_outer_timeout_sec,
                )
            reconstruction_error = ""
            if valid_publication(attempt_dir, physical):
                try:
                    reconstruct_remote_calibration(
                        attempt_dir, physical, policy_path, manifest
                    )
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    reconstruction_error = (
                        f"remote_reconstruction_failed:{type(exc).__name__}"
                    )
            result = compact_acceptance_result(
                physical,
                attempt_dir,
                outcome.get("returncode")
                if outcome.get("returncode_observed") is True
                else None,
                policy_path,
                manifest,
            )
            result = bind_child_transport_result(
                result, outcome, timeout_sec=args.child_outer_timeout_sec
            )
            result["reconstruction_error"] = reconstruction_error
            if result["published"] and result["targeted_eviction_complete"]:
                runner_log.unlink(missing_ok=True)
                result["runner_log_evicted_after_publication"] = True
            else:
                result["runner_log_evicted_after_publication"] = False
            result_receipt = write_physical_try_result(
                attempt_dir, started, result
            )
            result = dict(result_receipt["result"])
            results.append(result)
            write_campaign_state(
                output_root,
                attempts,
                results,
                active_attempt=None,
                config_path=config_path,
                policy_path=policy_path,
                verification=verification,
                plan=plan,
                evidence_manifest=manifest,
            )
            if outcome.get("process_group_gone") is not True:
                raise SystemExit(
                    "DPS qualification child process group cleanup could not be confirmed"
                )
            if interruption is not None:
                raise interruption
            print(
                json.dumps(
                    {
                        "attempt_id": physical["attempt_id"],
                        "logical_attempt_id": logical["attempt_id"],
                        "physical_try_ordinal": result["physical_try_ordinal"],
                        "classification": result["classification"],
                        "accepted": result["accepted"],
                        "published": result["published"],
                        "targeted_eviction_complete": result[
                            "targeted_eviction_complete"
                        ],
                        "reference_ratio": result["reference_ratio"],
                        "failure_reasons": result["failure_reasons"],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            if result["accepted"]:
                accepted = True
                break
        logical_results = [
            row
            for row in results
            if row.get("logical_attempt_id") == logical.get("attempt_id")
        ]
        findings = physical_sequence_findings(
            logical_results,
            materialized_count=len(physical_try_dirs(output_root, logical)),
        )
        if findings:
            raise SystemExit(
                f"invalid DPS try sequence for {logical['spec_target_id']}: "
                + ",".join(findings)
            )
        if not accepted:
            return 1

    state = write_campaign_state(
        output_root,
        attempts,
        results,
        active_attempt=None,
        config_path=config_path,
        policy_path=policy_path,
        verification=verification,
        plan=plan,
        evidence_manifest=manifest,
    )
    campaign_verification = verify_campaign_state(output_root / "campaign_state.json")
    write_json(output_root / "campaign_verification.json", campaign_verification)
    return 0 if state["passed"] and campaign_verification["passed"] else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.dry_run:
        return run_campaign(args)
    try:
        # This lease spans every campaign mutation: existing-ledger scan,
        # ordinal reservation/start receipt, child lifetime, immutable result,
        # and campaign-state publication.  A contending controller therefore
        # cannot mistake a still-running child for an interrupted one.
        with campaign_controller_lock(args.output_root):
            return run_campaign(args)
    except CampaignControllerLockHeld as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
