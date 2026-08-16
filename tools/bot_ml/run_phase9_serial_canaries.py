"""Run the Phase 9 Stonecore canaries through one serial session operator."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from .batch_evidence_lifecycle import (
    capture_batch,
    publish_batch,
    valid_reconstruction_receipt,
    verify_remote_reconstruction_and_evict,
)
from .build_phase9_evidence_identity_manifest import (
    PAIR_POLICY,
    TARGET_CATALOG,
)
from .live_validation_session import (
    canonical_sha256,
    git_head,
    sha256_file,
    verify_report_acceptance,
)
from .joined_campaign_evidence import (
    build_joined_campaign_closure,
    build_outer_bootstrap,
    reconstruct_outer_from_bootstrap,
    verify_joined_campaign_bootstrap,
    verify_hydrated_outer_closure,
    write_outer_bootstrap,
)
from .phase9_evidence_identity import (
    build_projection as phase9_build_projection,
    validate_manifest as validate_phase9_manifest,
)
from .phase8_evidence_identity import (
    build_projection as phase8_build_projection,
    validate_manifest as validate_phase8_manifest,
)
from .run_cata_raid_dps_acceptance import (
    run_child_process_group,
    verify_campaign_state as verify_dps_campaign,
)
from .run_live_bot_validation import validate_heroic_admission_receipt
from .verify_phase9_pairwise_matrix import verify as verify_phase9_matrix

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO_ROOT / "artifacts/all_spec_program/phase9_serial_canaries_20260728"
PHASE9_LOGICAL_SUCCESS_SLOTS = 14
STARTED_RECEIPT = "phase9_physical_try_started.json"
RESULT_RECEIPT = "phase9_physical_try_result.json"
LEDGER_FILE = "phase9_physical_try_ledger.jsonl"
CONTROLLER_LOCK = ".phase9_serial_controller.lock"
JOINED_BATCH_IDENTITY = "joined_campaign_batch_identity.json"
JOINED_PENDING_PROMOTION = "joined_campaign_promotion_pending.json"
JOINED_PROMOTION = "joined_campaign_promotion.json"
CHILD_TIMEOUT_GRACE_SECONDS = 30
CHILD_KILL_GRACE_SECONDS = 5


def campaign_identities_compatible(
    dps_identity: Mapping[str, Any], phase9_identity: Mapping[str, Any]
) -> bool:
    try:
        return phase8_build_projection(dps_identity) == phase9_build_projection(
            phase9_identity
        )
    except (TypeError, ValueError):
        return False


def require_current_phase9_source_binary(
    identity: Mapping[str, Any], attempts: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Fail closed if tracked source or the child worldserver changed."""
    expected = phase9_build_projection(identity)
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0 or status.stdout.strip():
        raise ValueError("Phase 9 requires the clean source tree bound by its identity")
    binary_values: set[Path] = set()
    for attempt in attempts:
        command = [str(value) for value in attempt.get("command") or []]
        if "--worldserver" in command:
            if command.index("--worldserver") + 1 >= len(command):
                raise ValueError("Phase 9 plan has an incomplete --worldserver option")
            binary_values.add(
                _resolve_plan_path(command[command.index("--worldserver") + 1])
            )
        else:
            binary_values.add(
                REPO_ROOT / "build/src/server/worldserver/worldserver"
            )
    if len(binary_values) != 1:
        raise ValueError("Phase 9 plan mixes worldserver binaries")
    binary = next(iter(binary_values)).resolve()
    if not binary.is_file():
        raise ValueError("Phase 9 worldserver binary is missing")
    observed = {
        **expected,
        "git_commit": git_head(REPO_ROOT).lower(),
        "source_tree_clean": True,
        "worldserver_binary_sha256": sha256_file(binary).lower(),
    }
    if observed != expected:
        raise ValueError("Phase 9 source or worldserver binary changed after identity capture")
    return observed


def phase9_campaign_root(plan: Mapping[str, Any]) -> Path:
    """Derive the only controller-lock root from immutable plan content."""
    if not str(plan.get("session_runtime_dir") or ""):
        raise ValueError("Phase 9 plan has no campaign runtime root")
    runtime_dir = _resolve_plan_path(str(plan["session_runtime_dir"]))
    root = runtime_dir.parent.resolve()
    attempt_dirs = [
        _resolve_plan_path(str(row.get("output_dir") or ""))
        for row in plan.get("attempts") or []
        if isinstance(row, Mapping)
    ]
    if not attempt_dirs:
        raise ValueError("Phase 9 plan has no attempt directories")
    try:
        for path in attempt_dirs:
            path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Phase 9 attempt escapes its immutable campaign root") from exc
    return root


def acquire_phase9_controller_lock(campaign_root: Path):
    campaign_root.mkdir(parents=True, exist_ok=True)
    lock_path = campaign_root / CONTROLLER_LOCK
    stream = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        stream.close()
        raise ValueError(
            f"Phase 9 campaign controller lock is already held: {lock_path}"
        ) from exc
    return stream


def run_phase9_child(
    command: Sequence[str],
    log_path: Path,
    *,
    outer_timeout_sec: float,
    termination_grace_sec: float = CHILD_TIMEOUT_GRACE_SECONDS,
    kill_grace_sec: float = CHILD_KILL_GRACE_SECONDS,
) -> tuple[dict[str, Any], BaseException | None]:
    """Run one isolated child and reap its process group on outer timeout."""
    if outer_timeout_sec <= 0 or termination_grace_sec <= 0 or kill_grace_sec <= 0:
        raise ValueError("Phase 9 child timeout bounds must be positive")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        outcome, pending_interruption = run_child_process_group(
            command,
            cwd=REPO_ROOT,
            env=os.environ.copy(),
            output_stream=log,
            timeout_sec=outer_timeout_sec,
            terminate_grace_sec=termination_grace_sec,
            kill_grace_sec=kill_grace_sec,
        )
    return (
        {
            **outcome,
            "outer_timeout_sec": outer_timeout_sec,
            "process_group_isolated": True,
            "process_exit_observed": outcome.get("returncode_observed") is True,
        },
        pending_interruption,
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _resolve_plan_path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def _plan_identity(plan: dict[str, Any]) -> str:
    identity = dict(plan)
    stored = str(identity.pop("plan_sha256", ""))
    if not stored or canonical_sha256(identity) != stored:
        raise ValueError("Phase 9 run plan identity mismatch")
    return stored


def _receipt_identity(payload: Mapping[str, Any], hash_key: str) -> str:
    identity = dict(payload)
    identity.pop(hash_key, None)
    return canonical_sha256(identity)


def phase9_physical_attempt(
    logical_attempt: Mapping[str, Any], physical_try_ordinal: int
) -> dict[str, Any]:
    """Create the prelaunch identity for one real Stonecore process run."""
    serial_index = int(logical_attempt.get("serial_index") or 0)
    logical_attempt_id = str(logical_attempt.get("attempt_id") or "")
    logical_cohort_id = str(logical_attempt.get("cohort_id") or "")
    composition_id = str(logical_attempt.get("composition_id") or "")
    success_ordinal = int(logical_attempt.get("clear_ordinal") or 0)
    if (
        serial_index not in range(1, PHASE9_LOGICAL_SUCCESS_SLOTS + 1)
        or physical_try_ordinal <= 0
        or not logical_attempt_id
        or not logical_cohort_id
        or not composition_id
        or success_ordinal not in {1, 2}
    ):
        raise ValueError("Phase 9 physical try identity is incomplete")
    physical = {
        **dict(logical_attempt),
        "logical_attempt_id": logical_attempt_id,
        "logical_cohort_id": logical_cohort_id,
        "success_ordinal": success_ordinal,
        "physical_try_ordinal": int(physical_try_ordinal),
        # First tries retain the plan's 1..14 scheduler indices.  Retries use
        # the next disjoint block so no two real child processes can claim the
        # same runtime attempt identity.
        "attempt_index": (
            (physical_try_ordinal - 1) * PHASE9_LOGICAL_SUCCESS_SLOTS
            + serial_index
        ),
        "attempt_id": f"{logical_attempt_id}/try-{physical_try_ordinal:02d}",
        "cohort_id": (
            f"{logical_cohort_id}-slot-{serial_index:02d}-"
            f"try-{physical_try_ordinal:02d}"
        ),
    }
    physical["physical_identity_sha256"] = canonical_sha256(physical)
    return physical


def phase9_physical_try_directory(
    base: Path, physical_try_ordinal: int
) -> Path:
    if physical_try_ordinal <= 0:
        raise ValueError("physical_try_ordinal must be positive")
    if physical_try_ordinal == 1:
        return base
    return base.parent / f"{base.name}-retry-{physical_try_ordinal - 1:02d}"


def phase9_physical_try_ordinal(base: Path, candidate: Path) -> int:
    if candidate.resolve() == base.resolve():
        return 1
    if candidate.parent.resolve() != base.parent.resolve():
        return 0
    prefix = f"{base.name}-retry-"
    if not candidate.name.startswith(prefix):
        return 0
    suffix = candidate.name.removeprefix(prefix)
    if not suffix.isdigit() or int(suffix) < 1:
        return 0
    return int(suffix) + 1


def phase9_physical_try_paths(base: Path) -> list[Path]:
    """Return every materialized physical try without hiding malformed extras."""
    candidates = attempt_directory_candidates(base)
    return sorted(
        candidates,
        key=lambda path: (
            phase9_physical_try_ordinal(base, path) or 2**31,
            path.name,
        ),
    )


def phase9_physical_command(
    logical_attempt: Mapping[str, Any],
    physical: Mapping[str, Any],
    output_dir: Path,
) -> list[str]:
    command = [str(value) for value in logical_attempt.get("command") or []]
    required = ("--output-dir", "--session-attempt-index", "--cohort-id")
    if any(value not in command for value in required):
        raise ValueError("Phase 9 child command is missing physical identity arguments")
    command[command.index("--output-dir") + 1] = str(output_dir)
    command[command.index("--session-attempt-index") + 1] = str(
        physical["attempt_index"]
    )
    command[command.index("--cohort-id") + 1] = str(physical["cohort_id"])
    if command and command[0] == "pixi":
        command[0] = str(Path.home() / ".pixi/bin/pixi")
    return command


def write_phase9_physical_try_started(
    attempt_dir: Path,
    logical_attempt: Mapping[str, Any],
    physical: Mapping[str, Any],
    command: Sequence[str],
) -> dict[str, Any]:
    path = attempt_dir / STARTED_RECEIPT
    if path.exists():
        raise ValueError(f"Phase 9 physical try start receipt is immutable: {path}")
    receipt = {
        "schema": "phase9_physical_try_started_v1",
        "started_at_unix": int(time.time()),
        "logical_attempt_id": logical_attempt.get("attempt_id"),
        "serial_index": int(logical_attempt.get("serial_index") or 0),
        "composition_id": logical_attempt.get("composition_id"),
        "success_ordinal": int(logical_attempt.get("clear_ordinal") or 0),
        "physical_try_ordinal": int(physical.get("physical_try_ordinal") or 0),
        "physical_attempt": dict(physical),
        "attempt_directory": str(attempt_dir.resolve().relative_to(REPO_ROOT)),
        "command": [str(value) for value in command],
    }
    receipt["command_sha256"] = canonical_sha256(receipt["command"])
    receipt["started_receipt_sha256"] = _receipt_identity(
        receipt, "started_receipt_sha256"
    )
    write_json(path, receipt)
    return receipt


def write_phase9_recovered_reservation(
    attempt_dir: Path,
    logical_attempt: Mapping[str, Any],
    physical: Mapping[str, Any],
) -> dict[str, Any]:
    """Consume a mkdir-only ordinal without pretending the child was launched."""
    path = attempt_dir / STARTED_RECEIPT
    if path.exists():
        raise ValueError(f"Phase 9 physical try reservation is immutable: {path}")
    command = phase9_physical_command(logical_attempt, physical, attempt_dir)
    receipt = {
        "schema": "phase9_physical_try_recovered_reservation_v1",
        "logical_attempt_id": logical_attempt.get("attempt_id"),
        "serial_index": int(logical_attempt.get("serial_index") or 0),
        "composition_id": logical_attempt.get("composition_id"),
        "success_ordinal": int(logical_attempt.get("clear_ordinal") or 0),
        "physical_try_ordinal": int(physical.get("physical_try_ordinal") or 0),
        "physical_attempt": dict(physical),
        "attempt_directory": str(attempt_dir.resolve().relative_to(REPO_ROOT)),
        "command": command,
        "recovered_missing_prelaunch_receipt": True,
        "child_launch_observation": "child_not_launched_or_observation_unknown",
    }
    receipt["command_sha256"] = canonical_sha256(command)
    receipt["started_receipt_sha256"] = _receipt_identity(
        receipt, "started_receipt_sha256"
    )
    write_json(path, receipt)
    return receipt


def load_phase9_physical_try_started(
    attempt_dir: Path,
    logical_attempt: Mapping[str, Any],
    physical: Mapping[str, Any],
) -> dict[str, Any]:
    receipt = read_json(attempt_dir / STARTED_RECEIPT)
    stored_hash = str(receipt.get("started_receipt_sha256") or "")
    expected_command = phase9_physical_command(logical_attempt, physical, attempt_dir)
    schema = str(receipt.get("schema") or "")
    schema_valid = bool(
        schema == "phase9_physical_try_started_v1"
        or (
            schema == "phase9_physical_try_recovered_reservation_v1"
            and receipt.get("recovered_missing_prelaunch_receipt") is True
            and receipt.get("child_launch_observation")
            == "child_not_launched_or_observation_unknown"
        )
    )
    if not (
        schema_valid
        and stored_hash
        and _receipt_identity(receipt, "started_receipt_sha256") == stored_hash
        and receipt.get("logical_attempt_id") == logical_attempt.get("attempt_id")
        and int(receipt.get("serial_index") or 0)
        == int(logical_attempt.get("serial_index") or 0)
        and receipt.get("composition_id") == logical_attempt.get("composition_id")
        and int(receipt.get("success_ordinal") or 0)
        == int(logical_attempt.get("clear_ordinal") or 0)
        and int(receipt.get("physical_try_ordinal") or 0)
        == int(physical.get("physical_try_ordinal") or 0)
        and receipt.get("physical_attempt") == dict(physical)
        and receipt.get("attempt_directory")
        == str(attempt_dir.resolve().relative_to(REPO_ROOT))
        and receipt.get("command") == expected_command
        and receipt.get("command_sha256") == canonical_sha256(expected_command)
    ):
        raise ValueError(f"invalid Phase 9 physical try start receipt: {attempt_dir}")
    return receipt


def phase9_reconstruction_identity(
    attempt: dict[str, Any], plan_sha256: str, identity_sha256: str
) -> str:
    return canonical_sha256(
        {
            "schema": "phase9_remote_full_clear_reconstruction_v1",
            "attempt_id": attempt.get("attempt_id"),
            "composition_sha256": attempt.get("composition_sha256"),
            "party_sha256": attempt.get("party_sha256"),
            "success_ordinal": attempt.get("success_ordinal"),
            "physical_try_ordinal": attempt.get("physical_try_ordinal"),
            "physical_identity_sha256": attempt.get("physical_identity_sha256"),
            "plan_sha256": plan_sha256,
            "identity_manifest_sha256": identity_sha256,
        }
    )


def phase9_compact_binding(report: dict[str, Any]) -> str:
    binding = {
        key: report.get(key)
        for key in (
            "returncode",
            "timed_out",
            "acceptable_final_evidence",
            "all_passed",
            "validation_context",
            "validation_route_manifest",
            "exact_party_pool_tag",
            "exact_party_class_specs",
            "exact_party_sha256",
            "evidence_envelope",
            "session",
            "acceptance_facts",
            "acceptance_verification",
        )
    }
    return canonical_sha256(binding)


def phase9_source_transport_verified(report: Mapping[str, Any]) -> bool:
    """Require source-typed child outcome facts; never default missing values."""
    return bool(
        type(report.get("returncode")) is int
        and report.get("returncode") == 0
        and report.get("timed_out") is False
        and report.get("acceptable_final_evidence") is True
        and report.get("all_passed") is True
    )


def verify_hydrated_phase9_attempt(
    batch_root: Path,
    attempt: dict[str, Any],
    identity: dict[str, Any],
) -> dict[str, Any]:
    source_path = batch_root / "raw" / "acceptance_source_report.json"
    report = read_json(source_path)
    verification = verify_report_acceptance(report)
    session = report.get("session") or {}
    envelope = report.get("evidence_envelope") or {}
    manifest = report.get("validation_route_manifest") or {}
    routes = [row for row in manifest.get("routes") or [] if isinstance(row, dict)]
    first_route = routes[0] if routes else {}
    expected_specs = [str(value) for value in attempt.get("ordered_party") or []]
    admission_status = session.get("admission_status") or {}
    heroic = validate_heroic_admission_receipt(
        admission_status,
        expected_class_specs=expected_specs,
        expected_map_id=int(first_route.get("bot_start_map_id") or 0),
        expected_start=(
            float(first_route.get("bot_start_x") or 0.0),
            float(first_route.get("bot_start_y") or 0.0),
            float(first_route.get("bot_start_z") or 0.0),
        ) if first_route else None,
        expected_route_manifest_sha256=str(
            (identity.get("artifact_hashes") or {}).get("route_manifest_sha256")
            or ""
        ),
        expected_recovery_entrance=(
            int(first_route.get("recovery_entrance_area_trigger_id") or 0),
            int(first_route.get("recovery_entrance_source_map_id") or 0),
            int(first_route.get("recovery_entrance_target_map_id") or 0),
        ) if first_route else None,
    )
    try:
        validate_phase9_manifest(identity, runtime_identity=session)
        runtime_identity_valid = True
    except (TypeError, ValueError):
        runtime_identity_valid = False
    cleanup = session.get("cleanup") or {}
    cleanup_complete = bool(
        cleanup.get("active") is False
        and cleanup.get("active_bots") == 0
        and cleanup.get("lease_count") == 0
        and cleanup.get("party_bot_count") == 0
    )
    exact_party_valid = bool(
        len(expected_specs) == 5
        and report.get("exact_party_pool_tag") == "all_spec_candidate_pool"
        and report.get("exact_party_class_specs") == expected_specs
        and report.get("exact_party_sha256") == canonical_sha256(expected_specs)
    )
    attempt_identity_valid = session.get("cohort_id") == attempt.get(
        "cohort_id"
    ) and int(session.get("attempt_index") or 0) == int(
        attempt.get("attempt_index") or 0
    )
    server_route_start_provisioned = bool(
        heroic.get("verified") is True
        and int(heroic.get("map_id") or 0) == 725
        and len(heroic.get("member_guids") or []) == 5
    )
    source_transport_verified = phase9_source_transport_verified(report)
    verified = bool(
        source_transport_verified
        and verification.get("accepted") is True
        and str((report.get("validation_context") or {}).get("scenario_id") or "")
        == "stonecore_5h"
        and len(routes) == 14
        and envelope.get("identity_complete") is True
        and envelope.get("identity_manifest_sha256") == identity.get("manifest_sha256")
        and runtime_identity_valid
        and attempt_identity_valid
        and exact_party_valid
        and heroic.get("verified") is True
        and server_route_start_provisioned
        and cleanup_complete
    )
    return {
        "schema": "phase9_remote_full_clear_verification_v1",
        "verified": verified,
        "attempt_id": attempt.get("attempt_id"),
        "source_report_sha256": sha256_file(source_path),
        "acceptance_verification_sha256": canonical_sha256(verification),
        "heroic_admission_receipt_sha256": heroic.get("receipt_sha256"),
        "runtime_identity_valid": runtime_identity_valid,
        "exact_party_valid": exact_party_valid,
        "attempt_identity_valid": attempt_identity_valid,
        "server_route_start_provisioned": server_route_start_provisioned,
        "cleanup_complete": cleanup_complete,
        "source_transport_verified": source_transport_verified,
        "acceptance": verification,
        "heroic_admission": heroic,
        "compact_binding_sha256": phase9_compact_binding(report),
    }


def exact_phase9_campaign_coverage(rows: list[dict[str, Any]]) -> bool:
    indexes = [int(row.get("serial_index") or 0) for row in rows]
    attempt_ids = [str(row.get("attempt_id") or "") for row in rows]
    logical_attempt_ids = [
        str(row.get("logical_attempt_id") or "") for row in rows
    ]
    physical_identities = [
        str(row.get("physical_identity_sha256") or "") for row in rows
    ]
    composition_ids = [str(row.get("composition_id") or "") for row in rows]
    reconstruction_receipts = [
        str(row.get("reconstruction_receipt_sha256") or "") for row in rows
    ]
    source_reports = [
        str(row.get("remote_source_report_sha256") or "") for row in rows
    ]
    clear_ordinals_by_composition: dict[str, set[int]] = {}
    for row in rows:
        clear_ordinals_by_composition.setdefault(
            str(row.get("composition_id") or ""), set()
        ).add(int(row.get("clear_ordinal") or 0))
    return bool(
        indexes == list(range(1, 15))
        and len(set(attempt_ids)) == 14
        and len(set(logical_attempt_ids)) == 14
        and len(set(physical_identities)) == 14
        and len(set(composition_ids)) == len(clear_ordinals_by_composition) == 7
        and all(ordinals == {1, 2} for ordinals in clear_ordinals_by_composition.values())
        and len(set(reconstruction_receipts)) == 14
        and len(set(source_reports)) == 14
        and "" not in attempt_ids
        and "" not in logical_attempt_ids
        and "" not in physical_identities
        and "" not in composition_ids
        and "" not in reconstruction_receipts
        and "" not in source_reports
        and all(phase9_attempt_accepted(row) for row in rows)
    )


def plan_matches_pinned_serial_canaries(
    plan: dict[str, Any], matrix: dict[str, Any]
) -> bool:
    pinned = [
        row for row in matrix.get("serial_canaries") or [] if isinstance(row, dict)
    ]
    attempts = [row for row in plan.get("attempts") or [] if isinstance(row, dict)]
    expected: list[dict[str, Any]] = []
    serial_index = 0
    for combination_index, composition in enumerate(pinned, start=1):
        for clear_ordinal in (1, 2):
            serial_index += 1
            expected.append(
                {
                    "serial_index": serial_index,
                    "combination_index": combination_index,
                    "clear_ordinal": clear_ordinal,
                    "composition_id": str(composition.get("composition_id") or ""),
                    "composition_sha256": str(
                        composition.get("composition_sha256") or ""
                    ),
                    "ordered_party": [
                        str(value) for value in composition.get("ordered_party") or []
                    ],
                }
            )
    observed = [
        {key: attempt.get(key) for key in expected_row}
        for attempt, expected_row in zip(attempts, expected, strict=False)
    ]
    return bool(
        len(pinned) == 7
        and len(attempts) == len(expected) == 14
        and observed == expected
    )


def attempt_directory_candidates(base: Path) -> list[Path]:
    retries = (
        sorted(base.parent.glob(f"{base.name}-retry-*"))
        if base.parent.is_dir()
        else []
    )
    return [path for path in (base, *retries) if path.is_dir()]


def next_attempt_directory(base: Path) -> Path:
    if not base.exists():
        return base
    retry = 1
    while (base.parent / f"{base.name}-retry-{retry:02d}").exists():
        retry += 1
    return base.parent / f"{base.name}-retry-{retry:02d}"


def attempt_directory_matches(base: Path, candidate: Path) -> bool:
    if candidate == base:
        return True
    prefix = f"{base.name}-retry-"
    suffix = candidate.name.removeprefix(prefix)
    return bool(
        candidate.parent == base.parent
        and candidate.name.startswith(prefix)
        and suffix.isdigit()
        and int(suffix) >= 1
    )


def reconstruct_phase9_attempt(
    output_dir: Path,
    attempt: dict[str, Any],
    plan_sha256: str,
    identity: dict[str, Any],
) -> tuple[bool, dict[str, Any], str]:
    domain_id = phase9_reconstruction_identity(
        attempt, plan_sha256, str(identity.get("manifest_sha256") or "")
    )
    error = ""
    try:
        verify_remote_reconstruction_and_evict(
            REPO_ROOT,
            output_dir / "batch",
            domain_verification_id=domain_id,
            verify_hydrated=lambda batch_root: verify_hydrated_phase9_attempt(
                batch_root, attempt, identity
            ),
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        error = f"{type(exc).__name__}:{exc}"
    valid, receipt = valid_reconstruction_receipt(
        output_dir / "batch",
        required_domain_verification_id=domain_id,
    )
    return bool(valid and (receipt.get("domain_verification") or {}).get("verified") is True), receipt, error


def phase9_attempt_accepted(result: Mapping[str, Any]) -> bool:
    return bool(
        result.get("child_returncode_observed") is True
        and type(result.get("returncode")) is int
        and result.get("returncode") == 0
        and result.get("transport_classification") == "child_exited"
        and result.get("outer_timed_out") is False
        and result.get("controller_interrupted") is False
        and result.get("process_group_gone") is True
        and type(result.get("report_returncode")) is int
        and result.get("report_returncode") == 0
        and result.get("timed_out") is False
        and result.get("remote_verified") is True
        and result.get("remote_reconstruction_verified") is True
        and result.get("remote_domain_verified") is True
        and result.get("remote_transport_verified") is True
        and result.get("targeted_eviction_complete") is True
        and result.get("exact_party_verified") is True
        and result.get("heroic_admission_verified") is True
        and bool(result.get("heroic_admission_receipt_sha256"))
        and result.get("server_route_start_provisioned") is True
        and result.get("identity_matches") is True
        and result.get("cleanup_complete") is True
    )


def classify_phase9_physical_try(result: Mapping[str, Any]) -> str:
    if phase9_attempt_accepted(result):
        return "accepted"
    if result.get("child_returncode_observed") is not True:
        return "infrastructure_failure"
    if result.get("outer_timed_out") is True or result.get("timed_out") is True:
        return "timeout"
    if (
        result.get("controller_interrupted") is True
        or result.get("transport_classification") != "child_exited"
        or result.get("process_group_gone") is not True
    ):
        return "infrastructure_failure"
    if result.get("returncode") != 0 or result.get("report_returncode") not in {
        0,
        None,
    }:
        return "process_failure"
    if result.get("remote_verified") is not True:
        return "publication_failure"
    if result.get("remote_reconstruction_verified") is not True:
        return "reconstruction_failure"
    return "qualification_failure"


def _phase9_report_transport(attempt_dir: Path) -> tuple[int | None, bool | None]:
    report_path = attempt_dir / "report.json"
    try:
        report = read_json(report_path) if report_path.is_file() else {}
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        report = {}
    return (
        report.get("returncode")
        if type(report.get("returncode")) is int
        else None,
        report.get("timed_out")
        if isinstance(report.get("timed_out"), bool)
        else None,
    )


def phase9_physical_result(
    *,
    logical_attempt: Mapping[str, Any],
    physical: Mapping[str, Any],
    output_dir: Path,
    log_path: Path,
    child_returncode: int | None,
    receipt: Mapping[str, Any],
    reconstruction_valid: bool,
    reconstruction: Mapping[str, Any],
    reconstruction_error: str,
    child_execution: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    remote = reconstruction.get("domain_verification") or {}
    report_returncode, report_timed_out = _phase9_report_transport(output_dir)
    child_execution = child_execution or {}
    outer_timed_out = child_execution.get("outer_timed_out") is True
    timed_out = True if outer_timed_out else report_timed_out
    raw_retained = (output_dir / "batch/raw").exists()
    compact_retained = (output_dir / "batch/compact").exists()
    batch_cache_retained = (output_dir / "batch/.batch-dvc-cache").exists()
    result = {
        "serial_index": int(logical_attempt.get("serial_index") or 0),
        "logical_attempt_id": logical_attempt.get("attempt_id"),
        "attempt_id": physical.get("attempt_id"),
        "cohort_id": physical.get("cohort_id"),
        "attempt_index": int(physical.get("attempt_index") or 0),
        "physical_identity_sha256": physical.get("physical_identity_sha256"),
        "composition_id": logical_attempt.get("composition_id"),
        "composition_sha256": logical_attempt.get("composition_sha256"),
        "party_sha256": logical_attempt.get("party_sha256"),
        "combination_index": int(logical_attempt.get("combination_index") or 0),
        "clear_ordinal": int(logical_attempt.get("clear_ordinal") or 0),
        "success_ordinal": int(logical_attempt.get("clear_ordinal") or 0),
        "physical_try_ordinal": int(physical.get("physical_try_ordinal") or 0),
        "output_dir": str(output_dir.resolve().relative_to(REPO_ROOT)),
        "log": str(log_path.resolve().relative_to(REPO_ROOT)),
        "status": "closed",
        "child_returncode_observed": type(child_returncode) is int,
        "returncode": child_returncode,
        "report_returncode": report_returncode,
        "timed_out": timed_out,
        "outer_timed_out": outer_timed_out,
        "outer_timeout_sec": child_execution.get("outer_timeout_sec"),
        "transport_classification": child_execution.get(
            "transport_classification"
        ),
        "controller_interrupted": child_execution.get(
            "controller_interrupted"
        )
        is True,
        "controller_signal": child_execution.get("controller_signal"),
        "process_group_isolated": child_execution.get(
            "process_group_isolated"
        ) is True,
        "process_group_id": int(child_execution.get("process_group_id") or 0),
        "process_group_terminate_sent": child_execution.get(
            "process_group_terminate_sent"
        ) is True,
        "process_group_kill_sent": child_execution.get(
            "process_group_kill_sent"
        ) is True,
        "process_group_gone": child_execution.get("process_group_gone") is True,
        "process_exit_observed": child_execution.get(
            "process_exit_observed"
        ) is True,
        "remote_verified": receipt.get("remote_verified"),
        "receipt_sha256": receipt.get("receipt_sha256"),
        "remote_reconstruction_verified": reconstruction_valid,
        "remote_domain_verified": remote.get("verified") is True,
        "remote_transport_verified": remote.get(
            "source_transport_verified"
        ) is True,
        "reconstruction_receipt_sha256": reconstruction.get("receipt_sha256"),
        "remote_source_report_sha256": remote.get("source_report_sha256"),
        "remote_compact_binding_sha256": remote.get("compact_binding_sha256"),
        "remote_acceptance_verification_sha256": remote.get(
            "acceptance_verification_sha256"
        ),
        "reconstruction_error": reconstruction_error,
        "raw_retained_locally": raw_retained,
        "compact_retained_locally": compact_retained,
        "batch_cache_retained_locally": batch_cache_retained,
        "exact_party_verified": remote.get("exact_party_valid") is True,
        "heroic_admission_verified": bool(
            (remote.get("heroic_admission") or {}).get("verified")
        ),
        "heroic_admission_receipt_sha256": remote.get(
            "heroic_admission_receipt_sha256"
        ),
        "server_route_start_provisioned": remote.get(
            "server_route_start_provisioned"
        ) is True,
        "cleanup_complete": remote.get("cleanup_complete") is True,
        "identity_matches": remote.get("runtime_identity_valid") is True,
        "targeted_eviction_complete": bool(
            reconstruction_valid
            and not raw_retained
            and not compact_retained
            and not batch_cache_retained
        ),
    }
    result["classification"] = classify_phase9_physical_try(result)
    result["passed"] = result["classification"] == "accepted"
    return result


def write_phase9_physical_try_result(
    attempt_dir: Path,
    started: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    path = attempt_dir / RESULT_RECEIPT
    if path.exists():
        raise ValueError(f"Phase 9 physical try result receipt is immutable: {path}")
    row = dict(result)
    row["classification"] = classify_phase9_physical_try(row)
    row["passed"] = row["classification"] == "accepted"
    receipt = {
        "schema": "phase9_physical_try_result_v1",
        "completed_at_unix": int(time.time()),
        "started_receipt_sha256": started.get("started_receipt_sha256"),
        "physical_identity_sha256": (
            (started.get("physical_attempt") or {}).get(
                "physical_identity_sha256"
            )
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


def load_phase9_physical_try_result(
    attempt_dir: Path,
    started: Mapping[str, Any],
    physical: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = read_json(attempt_dir / RESULT_RECEIPT)
    stored_hash = str(receipt.get("result_receipt_sha256") or "")
    result = receipt.get("result") or {}
    if not isinstance(result, Mapping):
        raise ValueError(f"invalid Phase 9 physical result payload: {attempt_dir}")
    result = dict(result)
    observed = receipt.get("child_returncode_observed") is True
    returncode = receipt.get("child_returncode")
    if not (
        receipt.get("schema") == "phase9_physical_try_result_v1"
        and stored_hash
        and _receipt_identity(receipt, "result_receipt_sha256") == stored_hash
        and receipt.get("started_receipt_sha256")
        == started.get("started_receipt_sha256")
        and receipt.get("physical_identity_sha256")
        == physical.get("physical_identity_sha256")
        and observed == (result.get("child_returncode_observed") is True)
        and (type(returncode) is int if observed else returncode is None)
        and result.get("returncode") == returncode
        and result.get("logical_attempt_id")
        == physical.get("logical_attempt_id")
        and result.get("attempt_id") == physical.get("attempt_id")
        and result.get("cohort_id") == physical.get("cohort_id")
        and int(result.get("attempt_index") or 0)
        == int(physical.get("attempt_index") or 0)
        and int(result.get("physical_try_ordinal") or 0)
        == int(physical.get("physical_try_ordinal") or 0)
        and result.get("composition_id") == physical.get("composition_id")
        and int(result.get("success_ordinal") or 0)
        == int(physical.get("success_ordinal") or 0)
        and result.get("physical_identity_sha256")
        == physical.get("physical_identity_sha256")
        and result.get("output_dir")
        == str(attempt_dir.resolve().relative_to(REPO_ROOT))
        and receipt.get("classification") == result.get("classification")
        and result.get("classification") == classify_phase9_physical_try(result)
        and (result.get("passed") is True) == phase9_attempt_accepted(result)
    ):
        raise ValueError(f"invalid Phase 9 physical try result receipt: {attempt_dir}")
    result["started_receipt_sha256"] = started.get("started_receipt_sha256")
    result["result_receipt_sha256"] = stored_hash
    return result, receipt


def phase9_physical_sequence_findings(
    rows: Sequence[Mapping[str, Any]], *, materialized_count: int
) -> list[str]:
    findings: list[str] = []
    ordinals = [int(row.get("physical_try_ordinal") or 0) for row in rows]
    if len(rows) != materialized_count:
        findings.append("materialized_try_not_classified")
    if ordinals != list(range(1, len(rows) + 1)):
        findings.append("physical_try_ordinals_not_contiguous")
    allowed = {
        "accepted",
        "infrastructure_failure",
        "timeout",
        "process_failure",
        "publication_failure",
        "reconstruction_failure",
        "qualification_failure",
    }
    if any(str(row.get("classification") or "") not in allowed for row in rows):
        findings.append("physical_try_unclassified")
    accepted_ordinals = [
        ordinal
        for ordinal, row in zip(ordinals, rows)
        if phase9_attempt_accepted(row)
    ]
    if len(accepted_ordinals) > 1:
        findings.append("multiple_successful_physical_tries")
    if accepted_ordinals and accepted_ordinals[0] != materialized_count:
        findings.append("physical_try_after_success")
    return list(dict.fromkeys(findings))


def scan_phase9_physical_ledger(
    attempts: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Rebuild the ledger from all immutable physical-try directories."""
    ledger: list[dict[str, Any]] = []
    findings: list[str] = []
    for logical in attempts:
        logical_id = str(logical.get("attempt_id") or "")
        base = _resolve_plan_path(str(logical.get("output_dir") or ""))
        paths = phase9_physical_try_paths(base)
        ordinals = [phase9_physical_try_ordinal(base, path) for path in paths]
        if ordinals != list(range(1, len(paths) + 1)):
            findings.append(f"{logical_id}:materialized_try_paths_not_contiguous")
        logical_rows: list[dict[str, Any]] = []
        for path, ordinal in zip(paths, ordinals):
            if ordinal <= 0:
                findings.append(f"{logical_id}:unexpected_physical_try_path:{path.name}")
                continue
            physical = phase9_physical_attempt(logical, ordinal)
            try:
                started = load_phase9_physical_try_started(
                    path, logical, physical
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                findings.append(
                    f"{logical_id}:invalid_physical_try_start:{ordinal}:"
                    f"{type(exc).__name__}"
                )
                continue
            if not (path / RESULT_RECEIPT).is_file():
                findings.append(
                    f"{logical_id}:materialized_try_not_classified:{ordinal}"
                )
                continue
            try:
                result, _receipt = load_phase9_physical_try_result(
                    path, started, physical
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                findings.append(
                    f"{logical_id}:invalid_physical_try_result:{ordinal}:"
                    f"{type(exc).__name__}"
                )
                continue
            logical_rows.append(result)
            ledger.append(result)
        findings.extend(
            f"{logical_id}:{finding}"
            for finding in phase9_physical_sequence_findings(
                logical_rows, materialized_count=len(paths)
            )
        )
    ledger.sort(
        key=lambda row: (
            int(row.get("serial_index") or 0),
            int(row.get("physical_try_ordinal") or 0),
        )
    )
    return ledger, list(dict.fromkeys(findings))


def _phase9_ledger_event_identity(event: Mapping[str, Any]) -> str:
    identity = dict(event)
    identity.pop("event_sha256", None)
    return canonical_sha256(identity)


def load_phase9_ledger_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    document = path.read_text(encoding="utf-8")
    if document and not document.endswith("\n"):
        raise ValueError("unterminated Phase 9 ledger tail")
    events: list[dict[str, Any]] = []
    previous = ""
    for line_number, line in enumerate(
        document.splitlines(), start=1
    ):
        if not line.strip():
            raise ValueError(f"blank Phase 9 ledger line: {line_number}")
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"invalid Phase 9 ledger row: {line_number}")
        stored_hash = str(payload.get("event_sha256") or "")
        if not (
            payload.get("schema") == "phase9_physical_try_ledger_event_v1"
            and int(payload.get("sequence") or 0) == line_number
            and str(payload.get("previous_event_sha256") or "") == previous
            and stored_hash
            and _phase9_ledger_event_identity(payload) == stored_hash
        ):
            raise ValueError(f"invalid Phase 9 ledger chain: {line_number}")
        events.append(payload)
        previous = stored_hash
    return events


def append_phase9_ledger_event(
    path: Path, payload: Mapping[str, Any]
) -> dict[str, Any]:
    events = load_phase9_ledger_events(path)
    event = {
        "schema": "phase9_physical_try_ledger_event_v1",
        "sequence": len(events) + 1,
        "previous_event_sha256": (
            events[-1]["event_sha256"] if events else ""
        ),
        **dict(payload),
    }
    event["event_sha256"] = _phase9_ledger_event_identity(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return event


def expected_phase9_ledger_payloads(
    attempts: Sequence[Mapping[str, Any]],
    *,
    plan_sha256: str,
    identity_manifest_sha256: str,
) -> dict[str, dict[str, Any]]:
    header_id = f"campaign:{plan_sha256}"
    expected: dict[str, dict[str, Any]] = {
        header_id: {
            "event_id": header_id,
            "event": "campaign_started",
            "run_plan_sha256": plan_sha256,
            "identity_manifest_sha256": identity_manifest_sha256,
            "logical_success_slot_count": PHASE9_LOGICAL_SUCCESS_SLOTS,
        }
    }
    for logical in attempts:
        base = _resolve_plan_path(str(logical.get("output_dir") or ""))
        paths = phase9_physical_try_paths(base)
        ordinals = [phase9_physical_try_ordinal(base, path) for path in paths]
        if ordinals != list(range(1, len(paths) + 1)):
            raise ValueError(
                f"cannot ledger malformed Phase 9 paths: {logical.get('attempt_id')}"
            )
        for path, ordinal in zip(paths, ordinals):
            physical = phase9_physical_attempt(logical, ordinal)
            started = load_phase9_physical_try_started(path, logical, physical)
            physical_sha = str(physical["physical_identity_sha256"])
            start_id = f"started:{physical_sha}"
            expected[start_id] = {
                "event_id": start_id,
                "event": "physical_try_started",
                "run_plan_sha256": plan_sha256,
                "identity_manifest_sha256": identity_manifest_sha256,
                "logical_attempt_id": physical["logical_attempt_id"],
                "attempt_id": physical["attempt_id"],
                "serial_index": physical["serial_index"],
                "composition_id": physical["composition_id"],
                "success_ordinal": physical["success_ordinal"],
                "physical_try_ordinal": physical["physical_try_ordinal"],
                "physical_identity_sha256": physical_sha,
                "started_receipt_sha256": started["started_receipt_sha256"],
            }
            if not (path / RESULT_RECEIPT).is_file():
                continue
            result, result_receipt = load_phase9_physical_try_result(
                path, started, physical
            )
            result_id = f"result:{physical_sha}"
            expected[result_id] = {
                "event_id": result_id,
                "event": "physical_try_result",
                "run_plan_sha256": plan_sha256,
                "identity_manifest_sha256": identity_manifest_sha256,
                "logical_attempt_id": physical["logical_attempt_id"],
                "attempt_id": physical["attempt_id"],
                "serial_index": physical["serial_index"],
                "composition_id": physical["composition_id"],
                "success_ordinal": physical["success_ordinal"],
                "physical_try_ordinal": physical["physical_try_ordinal"],
                "physical_identity_sha256": physical_sha,
                "started_receipt_sha256": started["started_receipt_sha256"],
                "result_receipt_sha256": result_receipt[
                    "result_receipt_sha256"
                ],
                "classification": result["classification"],
                "accepted": phase9_attempt_accepted(result),
                "child_returncode_observed": result.get(
                    "child_returncode_observed"
                ) is True,
                "child_returncode": result.get("returncode"),
                "timed_out": result.get("timed_out"),
                "publication_receipt_sha256": result.get("receipt_sha256"),
                "reconstruction_receipt_sha256": result.get(
                    "reconstruction_receipt_sha256"
                ),
            }
    return expected


def verify_phase9_append_ledger(
    path: Path,
    attempts: Sequence[Mapping[str, Any]],
    *,
    plan_sha256: str,
    identity_manifest_sha256: str,
) -> tuple[bool, dict[str, Any], list[str]]:
    findings: list[str] = []
    try:
        events = load_phase9_ledger_events(path)
        expected = expected_phase9_ledger_payloads(
            attempts,
            plan_sha256=plan_sha256,
            identity_manifest_sha256=identity_manifest_sha256,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return False, {}, [f"ledger_invalid:{type(exc).__name__}"]
    observed: dict[str, dict[str, Any]] = {}
    positions: dict[str, int] = {}
    for event in events:
        event_id = str(event.get("event_id") or "")
        comparable = {
            key: value
            for key, value in event.items()
            if key
            not in {
                "schema",
                "sequence",
                "previous_event_sha256",
                "event_sha256",
            }
        }
        if not event_id or event_id in observed:
            findings.append("duplicate_or_missing_ledger_event_id")
            continue
        observed[event_id] = comparable
        positions[event_id] = int(event["sequence"])
        if expected.get(event_id) != comparable:
            findings.append(f"ledger_event_does_not_match_receipt:{event_id}")
    if set(observed) != set(expected):
        findings.append("ledger_event_set_does_not_match_materialized_tries")
    for event_id, position in positions.items():
        if not event_id.startswith("result:"):
            continue
        start_id = "started:" + event_id.removeprefix("result:")
        if start_id not in positions or positions[start_id] >= position:
            findings.append(f"ledger_result_precedes_start:{event_id}")
    summary = {
        "path": str(path.resolve().relative_to(REPO_ROOT)),
        "event_count": len(events),
        "tail_sha256": events[-1]["event_sha256"] if events else "",
        "file_sha256": sha256_file(path) if path.is_file() else "",
    }
    return not findings, summary, list(dict.fromkeys(findings))


def reconcile_phase9_append_ledger(
    path: Path,
    attempts: Sequence[Mapping[str, Any]],
    *,
    plan_sha256: str,
    identity_manifest_sha256: str,
) -> dict[str, Any]:
    expected = expected_phase9_ledger_payloads(
        attempts,
        plan_sha256=plan_sha256,
        identity_manifest_sha256=identity_manifest_sha256,
    )
    events = load_phase9_ledger_events(path)
    observed_ids: set[str] = set()
    for event in events:
        event_id = str(event.get("event_id") or "")
        comparable = {
            key: value
            for key, value in event.items()
            if key
            not in {
                "schema",
                "sequence",
                "previous_event_sha256",
                "event_sha256",
            }
        }
        if not event_id or event_id in observed_ids or expected.get(event_id) != comparable:
            raise ValueError(f"Phase 9 append ledger conflicts with receipts: {event_id}")
        observed_ids.add(event_id)
    if any(event_id not in expected for event_id in observed_ids):
        raise ValueError("Phase 9 append ledger references a missing physical try")
    missing = [payload for key, payload in expected.items() if key not in observed_ids]
    missing.sort(
        key=lambda row: (
            0 if row["event"] == "campaign_started" else 1,
            int(row.get("serial_index") or 0),
            int(row.get("physical_try_ordinal") or 0),
            0 if row["event"] == "physical_try_started" else 1,
        )
    )
    for payload in missing:
        append_phase9_ledger_event(path, payload)
    valid, summary, findings = verify_phase9_append_ledger(
        path,
        attempts,
        plan_sha256=plan_sha256,
        identity_manifest_sha256=identity_manifest_sha256,
    )
    if not valid:
        raise ValueError("Phase 9 append ledger failed reconciliation: " + ",".join(findings))
    return summary


def verify_operator_state(state_path: Path) -> dict[str, Any]:
    """Recheck the joined 14-clear + 16-spec qualification state."""
    state_path = state_path.resolve()
    reasons: list[str] = []
    try:
        state = read_json(state_path)
        state_identity = dict(state)
        stored_state_hash = str(state_identity.pop("state_sha256", ""))
        run_plan_path = _resolve_plan_path(str(state.get("run_plan") or ""))
        plan = read_json(run_plan_path)
        plan_sha256 = _plan_identity(plan)
        identity_path = _resolve_plan_path(
            str(plan.get("evidence_identity_manifest_path") or "")
        )
        raw_identity = read_json(identity_path)
        matrix_path = _resolve_plan_path(str(plan.get("matrix_path") or ""))
        matrix = read_json(matrix_path)
        route_manifest_path = _resolve_plan_path(
            str((raw_identity.get("route_summary") or {}).get("route_manifest_path") or "")
        )
        identity = validate_phase9_manifest(
            raw_identity,
            artifact_hashes={
                "target_catalog_sha256": sha256_file(TARGET_CATALOG),
                "pair_policy_sha256": sha256_file(PAIR_POLICY),
                "pairwise_matrix_sha256": sha256_file(matrix_path),
                "route_manifest_sha256": sha256_file(route_manifest_path),
            },
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "schema": "phase9_joined_campaign_verification_v1",
            "passed": False,
            "failure_reasons": [f"campaign_inputs_invalid:{type(exc).__name__}"],
        }
    if (
        state.get("schema") != "phase9_serial_canary_operator_state_v3"
        or not stored_state_hash
        or canonical_sha256(state_identity) != stored_state_hash
        or state.get("run_plan_sha256") != plan_sha256
    ):
        reasons.append("phase9_operator_state_identity_invalid")
    ledger, ledger_findings = scan_phase9_physical_ledger(
        [row for row in plan.get("attempts") or [] if isinstance(row, dict)]
    )
    stored_ledger = [
        dict(row)
        for row in state.get("physical_try_ledger") or []
        if isinstance(row, dict)
    ]
    if ledger_findings or stored_ledger != ledger:
        reasons.append("phase9_physical_try_ledger_invalid")
    if int(state.get("physical_try_count") or 0) != len(ledger):
        reasons.append("phase9_physical_try_count_invalid")
    rows = [row for row in ledger if phase9_attempt_accepted(row)]
    if [dict(row) for row in state.get("attempts") or [] if isinstance(row, dict)] != rows:
        reasons.append("phase9_success_rows_do_not_match_physical_ledger")
    if not exact_phase9_campaign_coverage(rows):
        reasons.append("phase9_exact_seven_combinations_twice_missing")
    if not plan_matches_pinned_serial_canaries(plan, matrix):
        reasons.append("phase9_plan_not_pinned_seven_combinations_twice")
    expected_by_index = {
        int(row.get("serial_index") or 0): row
        for row in plan.get("attempts") or []
        if isinstance(row, dict)
    }
    verified_receipts = 0
    for row in rows:
        expected = expected_by_index.get(int(row.get("serial_index") or 0)) or {}
        base_output_dir = _resolve_plan_path(str(expected.get("output_dir") or ""))
        observed_output_dir = _resolve_plan_path(str(row.get("output_dir") or ""))
        physical_ordinal = int(row.get("physical_try_ordinal") or 0)
        try:
            expected_physical = phase9_physical_attempt(expected, physical_ordinal)
            expected_output_dir = phase9_physical_try_directory(
                base_output_dir, physical_ordinal
            )
        except ValueError:
            expected_physical = {}
            expected_output_dir = Path()
        if (
            row.get("logical_attempt_id") != expected.get("attempt_id")
            or row.get("attempt_id") != expected_physical.get("attempt_id")
            or row.get("physical_identity_sha256")
            != expected_physical.get("physical_identity_sha256")
            or row.get("composition_id") != expected.get("composition_id")
            or int(row.get("success_ordinal") or 0)
            != int(expected.get("clear_ordinal") or 0)
            or observed_output_dir != expected_output_dir
        ):
            reasons.append(f"phase9_attempt_mapping_mismatch:{row.get('serial_index')}")
            continue
        output_dir = observed_output_dir
        domain_id = phase9_reconstruction_identity(
            expected_physical,
            plan_sha256,
            str(identity.get("manifest_sha256") or ""),
        )
        valid, receipt = valid_reconstruction_receipt(
            output_dir / "batch",
            required_domain_verification_id=domain_id,
        )
        remote = receipt.get("domain_verification") or {}
        if not (
            valid
            and remote.get("verified") is True
            and row.get("reconstruction_receipt_sha256")
            == receipt.get("receipt_sha256")
            and row.get("remote_source_report_sha256")
            == remote.get("source_report_sha256")
            and row.get("remote_compact_binding_sha256")
            == remote.get("compact_binding_sha256")
        ):
            reasons.append(f"phase9_attempt_receipt_invalid:{row.get('serial_index')}")
            continue
        verified_receipts += 1
    dps_state_path = _resolve_plan_path(
        str(plan.get("dps_acceptance_state_path") or "")
    )
    if (
        not dps_state_path.is_file()
        or sha256_file(dps_state_path) != plan.get("dps_acceptance_state_sha256")
    ):
        reasons.append("joined_dps_state_identity_invalid")
        dps_verification: dict[str, Any] = {"passed": False}
    else:
        try:
            dps_identity = validate_phase8_manifest(
                read_json(dps_state_path.parent / "evidence_identity_manifest.json")
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            dps_identity = {}
        if not campaign_identities_compatible(dps_identity, identity):
            reasons.append("joined_database_or_profile_identity_mismatch")
        dps_verification = verify_dps_campaign(
            dps_state_path,
            required_git_head=str(plan.get("git_head") or ""),
            required_profile_content_hash=str(
                (identity.get("runtime_identity") or {}).get(
                    "profile_content_hash"
                )
                or ""
            ),
        )
        if dps_verification.get("passed") is not True:
            reasons.append("joined_16_spec_dps_gate_invalid")
    if not (
        state.get("status") == "passed"
        and state.get("promotion_gate_passed") is True
        and state.get("dps_acceptance_verified") is True
    ):
        reasons.append("joined_promotion_claim_invalid")
    unique_reasons = list(dict.fromkeys(reasons))
    verification = {
        "schema": "phase9_joined_campaign_verification_v1",
        "passed": not unique_reasons and verified_receipts == 14,
        "failure_reasons": unique_reasons,
        "verified_phase9_attempt_count": verified_receipts,
        "verified_dps_attempt_count": int(
            dps_verification.get("verified_attempt_count") or 0
        ),
        "phase9_state_sha256": stored_state_hash,
        "phase9_plan_sha256": plan_sha256,
        "dps_verification_sha256": dps_verification.get("verification_sha256"),
    }
    verification["verification_sha256"] = canonical_sha256(verification)
    return verification


def _write_immutable_json(path: Path, payload: Mapping[str, Any]) -> None:
    materialized = dict(payload)
    if path.is_file():
        if read_json(path) != materialized:
            raise ValueError(f"immutable joined campaign document conflicts: {path}")
        return
    write_json(path, materialized)


def _load_self_hashed_document(
    path: Path, *, schema: str, hash_key: str
) -> dict[str, Any]:
    payload = read_json(path)
    identity = dict(payload)
    stored = str(identity.pop(hash_key, ""))
    if (
        payload.get("schema") != schema
        or not stored
        or canonical_sha256(identity) != stored
    ):
        raise ValueError(f"invalid immutable joined campaign document: {path}")
    return payload


def _load_joined_publication(
    batch_root: Path, *, batch_id: str
) -> dict[str, Any]:
    manifest = _load_self_hashed_document(
        batch_root / "retained/final_manifest.json",
        schema="bot_immutable_batch_manifest_v1",
        hash_key="identity_sha256",
    )
    publication = _load_self_hashed_document(
        batch_root / "retained/publication_receipt.json",
        schema="bot_immutable_batch_publication_receipt_v1",
        hash_key="receipt_sha256",
    )
    if not (
        manifest.get("batch_id") == batch_id
        and publication.get("batch_id") == batch_id
        and publication.get("batch_identity_sha256")
        == manifest.get("identity_sha256")
        and publication.get("raw_bundle_sha256")
        == (manifest.get("raw") or {}).get("bundle_sha256")
        and publication.get("compact_bundle_sha256")
        == (manifest.get("compact") or {}).get("bundle_sha256")
        and publication.get("remote_verified") is True
    ):
        raise ValueError("existing joined campaign publication is incompatible")
    return publication


def _committed_bootstrap_head(repository: Path, bootstrap_path: Path) -> str:
    repository = repository.resolve()
    relative = bootstrap_path.resolve().relative_to(repository)
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repository,
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0 or status.stdout.strip():
        raise ValueError("joined promotion resume requires a clean Git checkout")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        text=True,
        capture_output=True,
        check=False,
    )
    committed = subprocess.run(
        ["git", "show", f"HEAD:{relative.as_posix()}"],
        cwd=repository,
        capture_output=True,
        check=False,
    )
    if (
        head.returncode != 0
        or committed.returncode != 0
        or committed.stdout != bootstrap_path.read_bytes()
    ):
        raise ValueError("exact joined bootstrap is not committed at Git HEAD")
    return head.stdout.strip().lower()


def audit_committed_joined_bootstrap(
    repository: Path, bootstrap_path: Path
) -> dict[str, Any]:
    """Prove the committed bootstrap from a separate clean Git worktree."""
    repository = repository.resolve()
    bootstrap_path = bootstrap_path.resolve()
    local_dvc_config = repository / ".dvc/config.local"
    if not local_dvc_config.is_file():
        raise ValueError(
            "fresh joined audit requires the repository's local DVC auth config"
        )
    local_dvc_config_bytes = local_dvc_config.read_bytes()
    if not local_dvc_config_bytes or len(local_dvc_config_bytes) > 1024 * 1024:
        raise ValueError("local DVC auth config is empty or unexpectedly large")
    bootstrap = read_json(bootstrap_path)
    bootstrap_verification = verify_joined_campaign_bootstrap(bootstrap)
    head = _committed_bootstrap_head(repository, bootstrap_path)
    relative = bootstrap_path.relative_to(repository)
    temporary_root = Path(tempfile.mkdtemp(prefix="phase9-joined-audit-"))
    checkout = temporary_root / "checkout"
    added = False
    try:
        added_result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(checkout), head],
            cwd=repository,
            text=True,
            capture_output=True,
            check=False,
        )
        if added_result.returncode != 0:
            raise ValueError("could not create fresh joined-audit worktree")
        added = True
        before = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=checkout,
            text=True,
            capture_output=True,
            check=False,
        )
        if before.returncode != 0 or before.stdout.strip():
            raise ValueError("fresh joined-audit worktree is not clean")
        destination_config = checkout / ".dvc/config.local"
        ignored = subprocess.run(
            [
                "git",
                "check-ignore",
                "-q",
                "--no-index",
                ".dvc/config.local",
            ],
            cwd=checkout,
            text=True,
            capture_output=True,
            check=False,
        )
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", ".dvc/config.local"],
            cwd=checkout,
            text=True,
            capture_output=True,
            check=False,
        )
        if ignored.returncode != 0 or tracked.returncode == 0:
            raise ValueError(
                "fresh checkout does not safely ignore local DVC auth config"
            )
        destination_config.parent.mkdir(parents=True, exist_ok=True)
        destination_config.write_bytes(local_dvc_config_bytes)
        destination_config.chmod(0o600)
        reconstruction = reconstruct_outer_from_bootstrap(
            checkout, checkout / relative
        )
        domain = reconstruction.get("domain_verification") or {}
        after = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=checkout,
            text=True,
            capture_output=True,
            check=False,
        )
        if not (
            reconstruction.get("remote_reconstructed") is True
            and reconstruction.get("targeted_eviction_complete") is True
            and domain.get("verified") is True
            and domain.get("closure_sha256")
            == bootstrap_verification["closure_sha256"]
            and int(domain.get("verified_dps_logical_qualifications") or 0) == 16
            and int(domain.get("verified_phase9_player_like_clears") or 0) == 14
            and int(domain.get("accepted_leaf_remote_reconstructions") or 0) == 30
            and domain.get("accepted_leaf_targeted_eviction_complete") is True
            and after.returncode == 0
            and not after.stdout.strip()
        ):
            raise ValueError("fresh joined-audit reconstruction did not pass")
        audit = {
            "schema": "phase9_joined_campaign_fresh_checkout_audit_v1",
            "git_head": head,
            "bootstrap_path": relative.as_posix(),
            "bootstrap_sha256": bootstrap_verification["bootstrap_sha256"],
            "closure_sha256": bootstrap_verification["closure_sha256"],
            "reconstruction_receipt_sha256": reconstruction.get(
                "receipt_sha256"
            ),
            "verified_dps_logical_qualifications": 16,
            "verified_phase9_player_like_clears": 14,
            "accepted_leaf_remote_reconstructions": 30,
            "targeted_eviction_complete": True,
            "fresh_checkout_clean_before_and_after": True,
        }
        audit["audit_sha256"] = canonical_sha256(audit)
        return audit
    finally:
        if added:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(checkout)],
                cwd=repository,
                text=True,
                capture_output=True,
                check=False,
            )
        shutil.rmtree(temporary_root, ignore_errors=True)


def publish_joined_campaign(
    state_path: Path,
    state: dict[str, Any],
    verification: dict[str, Any],
) -> dict[str, Any]:
    """Publish one canonical proof, then stop pending its Git checkpoint."""
    root = state_path.resolve().parent
    batch_root = root / "joined_campaign_promotion_batch"
    closure = build_joined_campaign_closure(
        REPO_ROOT, state_path, verification
    )
    closure_sha256 = str(closure["closure_sha256"])
    batch_id = f"phase9-joined-{state['state_sha256'][:16]}"
    domain_identity = {
        "schema": "phase9_joined_campaign_remote_reconstruction_v1",
        "state_sha256": state["state_sha256"],
        "verification_sha256": verification["verification_sha256"],
        "closure_sha256": closure_sha256,
    }
    domain_id = canonical_sha256(domain_identity)
    batch_identity = {
        "schema": "phase9_joined_campaign_batch_identity_v1",
        "batch_id": batch_id,
        "state_sha256": state["state_sha256"],
        "verification_sha256": verification["verification_sha256"],
        "closure_sha256": closure_sha256,
        "domain_verification_id": domain_id,
    }
    batch_identity["identity_sha256"] = canonical_sha256(batch_identity)
    identity_path = batch_root / "retained" / JOINED_BATCH_IDENTITY
    if batch_root.exists() and not identity_path.is_file():
        raise ValueError(
            "existing joined batch lacks its immutable resume identity"
        )
    _write_immutable_json(identity_path, batch_identity)
    acceptance_report = {
        "schema": "bot_live_validation_report_v1",
        "returncode": 0,
        "timed_out": False,
        "stages": [{"stage": "joined_14_clear_16_dps_gate", "missing": []}],
        "failure_labels": [],
        "validation_context": {"scenario_id": "stonecore_5h_joined_campaign"},
        "validation_route_manifest": {},
        "evidence": {},
        "watchdog_state": {},
        "joined_campaign_state": state,
        "joined_campaign_verification": verification,
        "joined_campaign_closure": closure,
    }
    manifest_path = batch_root / "retained/final_manifest.json"
    if not manifest_path.is_file():
        capture_batch(
            batch_root,
            batch_id=batch_id,
            raw_rows=[
                {
                    "event": "joined_campaign_state",
                    "state_sha256": state["state_sha256"],
                    "verification_sha256": verification["verification_sha256"],
                }
            ],
            compact_rows=[
                {
                    "phase9_attempt_count": 14,
                    "dps_attempt_count": 16,
                    "passed": True,
                }
            ],
            exact_manifests={
                "phase9_state_sha256": state["state_sha256"],
                "phase9_plan_sha256": state["run_plan_sha256"],
                "dps_acceptance_state_sha256": state[
                    "dps_acceptance_state_sha256"
                ],
                "joined_verification_sha256": verification[
                    "verification_sha256"
                ],
                "joined_closure_sha256": closure_sha256,
            },
            summary={
                "phase9_attempt_count": 14,
                "dps_attempt_count": 16,
                "passed": True,
            },
            acceptance_report=acceptance_report,
        )
    publication_path = batch_root / "retained/publication_receipt.json"
    publication = (
        _load_joined_publication(batch_root, batch_id=batch_id)
        if publication_path.is_file()
        else publish_batch(REPO_ROOT, batch_root)
    )

    def verify_hydrated_joined(batch: Path) -> dict[str, Any]:
        return verify_hydrated_outer_closure(
            batch,
            closure_sha256,
            repository=REPO_ROOT,
            recursively_verify_accepted_leaves=True,
        )

    valid_reconstruction, reconstruction = valid_reconstruction_receipt(
        batch_root, required_domain_verification_id=domain_id
    )
    if not valid_reconstruction:
        reconstruction = verify_remote_reconstruction_and_evict(
            REPO_ROOT,
            batch_root,
            domain_verification_id=domain_id,
            verify_hydrated=verify_hydrated_joined,
            force_reconstruct=True,
        )
    bootstrap = build_outer_bootstrap(
        REPO_ROOT, batch_root, closure_sha256, domain_identity
    )
    bootstrap_path = write_outer_bootstrap(REPO_ROOT, bootstrap)
    pending = {
        "schema": "phase9_joined_campaign_promotion_pending_v1",
        "passed": False,
        "status": "pending_committed_bootstrap_fresh_checkout_audit",
        "state_path": str(state_path.resolve().relative_to(REPO_ROOT)),
        "state_sha256": state["state_sha256"],
        "verification_sha256": verification["verification_sha256"],
        "closure_sha256": closure_sha256,
        "batch_path": str(batch_root.relative_to(REPO_ROOT)),
        "bootstrap_path": str(bootstrap_path.relative_to(REPO_ROOT)),
        "bootstrap_sha256": bootstrap["bootstrap_sha256"],
        "publication_receipt_sha256": publication["receipt_sha256"],
        "reconstruction_receipt_sha256": reconstruction["receipt_sha256"],
        "remote_reconstructed": reconstruction.get("remote_reconstructed") is True,
        "targeted_eviction_complete": reconstruction.get(
            "targeted_eviction_complete"
        ) is True,
        "checkpoint_commands": [
            f"git add {bootstrap_path.relative_to(REPO_ROOT)}",
            "git commit -m 'checkpoint joined campaign evidence bootstrap'",
            (
                "pixi run python -m tools.bot_ml.run_phase9_serial_canaries "
                f"--run-plan {state['run_plan']} --state-output "
                f"{state_path.resolve().relative_to(REPO_ROOT)} "
                "--resume-joined-promotion"
            ),
        ],
    }
    pending["pending_sha256"] = canonical_sha256(pending)
    _write_immutable_json(root / JOINED_PENDING_PROMOTION, pending)
    return pending


def resume_joined_campaign_promotion(state_path: Path) -> dict[str, Any]:
    """Promote only after a committed bootstrap passes a fresh checkout."""
    state_path = state_path.resolve()
    root = state_path.parent
    state = _load_self_hashed_document(
        state_path,
        schema="phase9_serial_canary_operator_state_v3",
        hash_key="state_sha256",
    )
    pending = _load_self_hashed_document(
        root / JOINED_PENDING_PROMOTION,
        schema="phase9_joined_campaign_promotion_pending_v1",
        hash_key="pending_sha256",
    )
    promotion_path = root / JOINED_PROMOTION
    if promotion_path.is_file():
        promotion = _load_self_hashed_document(
            promotion_path,
            schema="phase9_joined_campaign_promotion_v2",
            hash_key="promotion_sha256",
        )
        if promotion.get("pending_sha256") != pending.get("pending_sha256"):
            raise ValueError("existing joined promotion belongs to another proof")
        return promotion
    if not (
        pending.get("state_sha256") == state.get("state_sha256")
        and pending.get("status")
        == "pending_committed_bootstrap_fresh_checkout_audit"
        and pending.get("passed") is False
    ):
        raise ValueError("joined pending promotion does not match operator state")
    bootstrap_path = REPO_ROOT / str(pending.get("bootstrap_path") or "")
    bootstrap = read_json(bootstrap_path)
    bootstrap_verification = verify_joined_campaign_bootstrap(bootstrap)
    if (
        bootstrap_verification.get("bootstrap_sha256")
        != pending.get("bootstrap_sha256")
        or bootstrap_verification.get("closure_sha256")
        != pending.get("closure_sha256")
    ):
        raise ValueError("joined pending promotion bootstrap changed")
    audit = audit_committed_joined_bootstrap(REPO_ROOT, bootstrap_path)
    promotion = {
        "schema": "phase9_joined_campaign_promotion_v2",
        "passed": True,
        "status": "promoted_after_committed_fresh_checkout_audit",
        "state_path": pending["state_path"],
        "state_sha256": pending["state_sha256"],
        "verification_sha256": pending["verification_sha256"],
        "closure_sha256": pending["closure_sha256"],
        "batch_path": pending["batch_path"],
        "bootstrap_path": pending["bootstrap_path"],
        "bootstrap_sha256": pending["bootstrap_sha256"],
        "publication_receipt_sha256": pending[
            "publication_receipt_sha256"
        ],
        "reconstruction_receipt_sha256": pending[
            "reconstruction_receipt_sha256"
        ],
        "pending_sha256": pending["pending_sha256"],
        "fresh_checkout_audit": audit,
        "remote_reconstructed": True,
        "targeted_eviction_complete": True,
    }
    promotion["promotion_sha256"] = canonical_sha256(promotion)
    _write_immutable_json(promotion_path, promotion)
    return promotion


def build_phase9_operator_state(
    *,
    run_plan_path: Path,
    plan: Mapping[str, Any],
    plan_sha256: str,
    identity: Mapping[str, Any],
    dps_verification: Mapping[str, Any],
    ledger: Sequence[Mapping[str, Any]],
    append_ledger_summary: Mapping[str, Any],
    sequence_findings: Sequence[str],
    start_index: int,
    stop_index: int,
    active_attempt: Mapping[str, Any] | None,
    status: str,
) -> dict[str, Any]:
    ordered_ledger = sorted(
        (dict(row) for row in ledger),
        key=lambda row: (
            int(row.get("serial_index") or 0),
            int(row.get("physical_try_ordinal") or 0),
        ),
    )
    successes = [row for row in ordered_ledger if phase9_attempt_accepted(row)]
    histories: dict[str, list[dict[str, Any]]] = {}
    for row in ordered_ledger:
        histories.setdefault(str(row.get("logical_attempt_id") or ""), []).append(
            {
                "attempt_id": row.get("attempt_id"),
                "physical_try_ordinal": row.get("physical_try_ordinal"),
                "physical_identity_sha256": row.get("physical_identity_sha256"),
                "started_receipt_sha256": row.get("started_receipt_sha256"),
                "result_receipt_sha256": row.get("result_receipt_sha256"),
                "output_dir": row.get("output_dir"),
                "classification": row.get("classification"),
                "passed": row.get("passed") is True,
                "returncode": row.get("returncode"),
                "timed_out": row.get("timed_out"),
                "receipt_sha256": row.get("receipt_sha256"),
                "reconstruction_receipt_sha256": row.get(
                    "reconstruction_receipt_sha256"
                ),
            }
        )
    runtime = identity.get("runtime_identity") or {}
    exact_coverage = bool(
        not sequence_findings and exact_phase9_campaign_coverage(successes)
    )
    state = {
        "schema": "phase9_serial_canary_operator_state_v3",
        "run_plan": str(run_plan_path.resolve().relative_to(REPO_ROOT)),
        "run_plan_sha256": plan_sha256,
        "start_index": start_index,
        "stop_index": stop_index,
        "identity_manifest_sha256": identity.get("manifest_sha256"),
        "dps_acceptance_state_sha256": plan.get(
            "dps_acceptance_state_sha256"
        ),
        "dps_acceptance_verification_sha256": dps_verification.get(
            "verification_sha256"
        ),
        "expected_server_process_id": runtime.get("server_process_id"),
        "expected_server_epoch": runtime.get("server_epoch"),
        "expected_profile_generation": runtime.get("profile_generation"),
        "expected_profile_content_hash": str(
            runtime.get("profile_content_hash") or ""
        ).lower(),
        "logical_success_slot_count": PHASE9_LOGICAL_SUCCESS_SLOTS,
        "physical_try_count": len(ordered_ledger),
        "classified_physical_try_count": len(ordered_ledger),
        "physical_success_count": len(successes),
        "physical_failure_count": len(ordered_ledger) - len(successes),
        "append_ledger": dict(append_ledger_summary),
        "physical_try_ledger": ordered_ledger,
        # Compatibility: attempts means the one accepted physical try for
        # each logical clear slot, never all real process runs.
        "attempts": successes,
        "attempt_histories": histories,
        "sequence_findings": list(sequence_findings),
        "active_attempt": dict(active_attempt) if active_attempt else None,
        "exact_seven_combinations_twice_coverage": exact_coverage,
        "dps_acceptance_verified": dps_verification.get("passed") is True,
        "promotion_gate_passed": bool(
            exact_coverage
            and dps_verification.get("passed") is True
            and active_attempt is None
        ),
        "status": status,
    }
    if state["promotion_gate_passed"]:
        state["status"] = "passed"
    state["state_sha256"] = canonical_sha256(state)
    return state


def close_interrupted_phase9_tries(
    attempts: Sequence[Mapping[str, Any]],
    *,
    plan_sha256: str,
    identity: Mapping[str, Any],
) -> None:
    """Terminalize a crash without inventing the unobserved child return code."""
    for logical in attempts:
        base = _resolve_plan_path(str(logical.get("output_dir") or ""))
        paths = phase9_physical_try_paths(base)
        ordinals = [phase9_physical_try_ordinal(base, path) for path in paths]
        if ordinals != list(range(1, len(paths) + 1)):
            raise ValueError(
                f"non-contiguous or malformed Phase 9 physical tries: "
                f"{logical.get('attempt_id')}"
            )
        for path, ordinal in zip(paths, ordinals):
            physical = phase9_physical_attempt(logical, ordinal)
            recovered_missing_start = not (path / STARTED_RECEIPT).is_file()
            started = (
                write_phase9_recovered_reservation(path, logical, physical)
                if recovered_missing_start
                else load_phase9_physical_try_started(path, logical, physical)
            )
            if (path / RESULT_RECEIPT).is_file():
                load_phase9_physical_try_result(path, started, physical)
                continue
            receipt_path = path / "batch/retained/publication_receipt.json"
            receipt = read_json(receipt_path) if receipt_path.is_file() else {}
            reconstruction_valid, reconstruction, reconstruction_error = (
                reconstruct_phase9_attempt(
                    path, physical, plan_sha256, dict(identity)
                )
            )
            result = phase9_physical_result(
                logical_attempt=logical,
                physical=physical,
                output_dir=path,
                log_path=path / "phase9_runner.log",
                child_returncode=None,
                receipt=receipt,
                reconstruction_valid=reconstruction_valid,
                reconstruction=reconstruction,
                reconstruction_error=reconstruction_error,
            )
            result["resume_failure_reason"] = (
                "child_not_launched_or_observation_unknown"
                if recovered_missing_start
                else "controller_interrupted_before_child_returncode_was_recorded"
            )
            result["recovered_missing_prelaunch_receipt"] = recovered_missing_start
            write_phase9_physical_try_result(path, started, result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-plan", type=Path, default=DEFAULT_ROOT / "run_plan.json")
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--stop-index", type=int)
    parser.add_argument("--state-output", type=Path, default=DEFAULT_ROOT / "operator_state.json")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_ROOT / "operator_logs")
    parser.add_argument("--resume-joined-promotion", action="store_true")
    args = parser.parse_args()

    plan = read_json(args.run_plan.resolve())
    try:
        plan_sha256 = _plan_identity(plan)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    attempts = [row for row in plan.get("attempts") or [] if isinstance(row, dict)]
    serial_indexes = [int(attempt.get("serial_index") or 0) for attempt in attempts]
    attempt_ids = [str(attempt.get("attempt_id") or "") for attempt in attempts]
    composition_ids = [str(attempt.get("composition_id") or "") for attempt in attempts]
    try:
        campaign_root = phase9_campaign_root(plan)
        if args.state_output.resolve().parent != campaign_root:
            raise ValueError(
                "--state-output must live in the immutable Phase 9 campaign root"
            )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if not (
        plan.get("schema") == "all_spec_phase9_serial_run_plan_v1"
        and len(attempts) == int(plan.get("attempt_count") or 0) == 14
        and serial_indexes == list(range(1, 15))
        and len(set(attempt_ids)) == 14
        and len(set(composition_ids)) == 7
        and all(
            {
                int(attempt.get("clear_ordinal") or 0)
                for attempt in attempts
                if attempt.get("composition_id") == composition_id
            }
            == {1, 2}
            for composition_id in set(composition_ids)
        )
        and "" not in attempt_ids
        and "" not in composition_ids
        and all(len(attempt.get("ordered_party") or []) == 5 for attempt in attempts)
        and int(plan.get("target_union_count") or 0) == 24
        and float(plan.get("timeout_sec") or 0) > 0
        and plan.get("promotion_requires_dps_acceptance") is True
    ):
        raise SystemExit("Phase 9 plan must contain seven pinned combinations with two clears each")
    try:
        # Hold this plan-derived lock across scan/reservation/child/result/state.
        controller_lock_stream = acquire_phase9_controller_lock(campaign_root)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if args.resume_joined_promotion:
        try:
            promotion = resume_joined_campaign_promotion(
                args.state_output.resolve()
            )
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            raise SystemExit(f"joined promotion resume failed: {exc}") from exc
        print(json.dumps(promotion, sort_keys=True), flush=True)
        return 0 if promotion.get("passed") is True else 1
    stop_index = args.stop_index if args.stop_index is not None else max(
        (int(attempt["serial_index"]) for attempt in attempts), default=0
    )
    if plan.get("server_provisions_route_start_each_attempt") is not True:
        raise SystemExit("Phase 9 requires server-owned entrance provisioning before activation")
    matrix_path = _resolve_plan_path(str(plan.get("matrix_path") or ""))
    matrix_verification = verify_phase9_matrix(TARGET_CATALOG, PAIR_POLICY, matrix_path)
    matrix = read_json(matrix_path)
    if (
        matrix_verification.get("passed") is not True
        or sha256_file(matrix_path) != plan.get("matrix_file_sha256")
        or not plan_matches_pinned_serial_canaries(plan, matrix)
    ):
        raise SystemExit("Phase 9 pairwise matrix no longer matches the pinned plan")
    selected = [
        attempt
        for attempt in attempts
        if args.start_index <= int(attempt["serial_index"]) <= stop_index
    ]
    if not selected:
        raise SystemExit("no Phase 9 attempts selected")

    identity_path = _resolve_plan_path(
        str(plan.get("evidence_identity_manifest_path") or "")
    )
    route_manifest_path = Path()
    raw_identity = read_json(identity_path)
    route_manifest_path = _resolve_plan_path(
        str((raw_identity.get("route_summary") or {}).get("route_manifest_path") or "")
    )
    artifact_hashes = {
        "target_catalog_sha256": sha256_file(TARGET_CATALOG),
        "pair_policy_sha256": sha256_file(PAIR_POLICY),
        "pairwise_matrix_sha256": sha256_file(matrix_path),
        "route_manifest_sha256": sha256_file(route_manifest_path),
    }
    try:
        identity = validate_phase9_manifest(
            raw_identity, artifact_hashes=artifact_hashes
        )
        require_current_phase9_source_binary(identity, attempts)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"invalid Phase 9 evidence identity: {exc}") from exc
    expected_runtime = identity["runtime_identity"]
    expected_identity_argument = str(identity_path)
    if any(
        "--evidence-identity-manifest" not in (attempt.get("command") or [])
        or str(
            attempt["command"][
                attempt["command"].index("--evidence-identity-manifest") + 1
            ]
        )
        != expected_identity_argument
        for attempt in attempts
    ):
        raise SystemExit("Phase 9 attempts do not share the pinned identity manifest")
    if str(plan.get("git_head") or "") != git_head(REPO_ROOT):
        raise SystemExit("Phase 9 plan Git identity is stale")
    dps_state_path = _resolve_plan_path(
        str(plan.get("dps_acceptance_state_path") or "")
    )
    if sha256_file(dps_state_path) != plan.get("dps_acceptance_state_sha256"):
        raise SystemExit("pinned DPS acceptance state hash mismatch")
    try:
        dps_identity = validate_phase8_manifest(
            read_json(dps_state_path.parent / "evidence_identity_manifest.json")
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid DPS evidence identity: {exc}") from exc
    if not campaign_identities_compatible(dps_identity, identity):
        raise SystemExit(
            "Phase 9 and DPS qualification must share the exact validated build projection"
        )
    dps_verification = verify_dps_campaign(
        dps_state_path,
        required_git_head=str(plan.get("git_head") or ""),
        required_profile_content_hash=str(
            expected_runtime.get("profile_content_hash") or ""
        ),
    )
    if dps_verification.get("passed") is not True:
        raise SystemExit(
            "Phase 9 promotion requires the independently verified 16-spec DPS gate"
        )
    append_ledger_path = args.state_output.resolve().parent / LEDGER_FILE
    if args.state_output.resolve().is_file() and not append_ledger_path.is_file():
        raise SystemExit(
            "existing Phase 9 state is missing its append-only physical ledger"
        )
    try:
        close_interrupted_phase9_tries(
            attempts, plan_sha256=plan_sha256, identity=identity
        )
        append_ledger_summary = reconcile_phase9_append_ledger(
            append_ledger_path,
            attempts,
            plan_sha256=plan_sha256,
            identity_manifest_sha256=str(identity["manifest_sha256"]),
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid existing Phase 9 physical try ledger: {exc}") from exc
    ledger, sequence_findings = scan_phase9_physical_ledger(attempts)
    if sequence_findings:
        raise SystemExit(
            "invalid Phase 9 physical try sequence: "
            + ",".join(sequence_findings)
        )

    selected_indexes = {int(attempt["serial_index"]) for attempt in selected}
    for attempt in attempts:
        serial_index = int(attempt["serial_index"])
        logical_rows = [
            row
            for row in ledger
            if row.get("logical_attempt_id") == attempt.get("attempt_id")
        ]
        if any(phase9_attempt_accepted(row) for row in logical_rows):
            continue
        if serial_index not in selected_indexes:
            continue

        try:
            require_current_phase9_source_binary(identity, attempts)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

        physical_try_ordinal = len(logical_rows) + 1
        physical = phase9_physical_attempt(attempt, physical_try_ordinal)
        base_output_dir = _resolve_plan_path(str(attempt["output_dir"]))
        output_dir = phase9_physical_try_directory(
            base_output_dir, physical_try_ordinal
        )
        if output_dir.exists():
            raise SystemExit(f"refusing to overwrite Phase 9 physical try: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=False)
        command = phase9_physical_command(attempt, physical, output_dir)
        started = write_phase9_physical_try_started(
            output_dir, attempt, physical, command
        )
        append_ledger_summary = reconcile_phase9_append_ledger(
            append_ledger_path,
            attempts,
            plan_sha256=plan_sha256,
            identity_manifest_sha256=str(identity["manifest_sha256"]),
        )
        log_path = output_dir / "phase9_runner.log"
        state = build_phase9_operator_state(
            run_plan_path=args.run_plan,
            plan=plan,
            plan_sha256=plan_sha256,
            identity=identity,
            dps_verification=dps_verification,
            ledger=ledger,
            append_ledger_summary=append_ledger_summary,
            sequence_findings=sequence_findings,
            start_index=args.start_index,
            stop_index=stop_index,
            active_attempt=physical,
            status="running",
        )
        write_json(args.state_output.resolve(), state)
        print(
            json.dumps(
                {
                    "event": "physical_try_started",
                    "logical_attempt_id": attempt["attempt_id"],
                    "attempt_id": physical["attempt_id"],
                    "composition_id": physical["composition_id"],
                    "success_ordinal": physical["success_ordinal"],
                    "physical_try_ordinal": physical["physical_try_ordinal"],
                    "physical_identity_sha256": physical[
                        "physical_identity_sha256"
                    ],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        child_execution, pending_interruption = run_phase9_child(
            command,
            log_path,
            outer_timeout_sec=(
                float(plan.get("timeout_sec") or 0)
                + CHILD_TIMEOUT_GRACE_SECONDS
            ),
        )

        receipt_path = output_dir / "batch/retained/publication_receipt.json"
        receipt = read_json(receipt_path) if receipt_path.is_file() else {}
        reconstruction_valid, reconstruction, reconstruction_error = (
            reconstruct_phase9_attempt(
                output_dir, physical, plan_sha256, identity
            )
        )
        result = phase9_physical_result(
            logical_attempt=attempt,
            physical=physical,
            output_dir=output_dir,
            log_path=log_path,
            child_returncode=child_execution["returncode"],
            receipt=receipt,
            reconstruction_valid=reconstruction_valid,
            reconstruction=reconstruction,
            reconstruction_error=reconstruction_error,
            child_execution=child_execution,
        )
        # The remotely reconstructed batch contains the immutable child
        # command/output evidence.  Retain the small outer log on every
        # failure, and evict it only for a fully accepted physical success.
        if phase9_attempt_accepted(result):
            log_path.unlink(missing_ok=True)
            result["operator_log_evicted_after_publication"] = True
        else:
            result["operator_log_evicted_after_publication"] = False
        result_receipt = write_phase9_physical_try_result(
            output_dir, started, result
        )
        result = dict(result_receipt["result"])
        append_ledger_summary = reconcile_phase9_append_ledger(
            append_ledger_path,
            attempts,
            plan_sha256=plan_sha256,
            identity_manifest_sha256=str(identity["manifest_sha256"]),
        )
        ledger, sequence_findings = scan_phase9_physical_ledger(attempts)
        state = build_phase9_operator_state(
            run_plan_path=args.run_plan,
            plan=plan,
            plan_sha256=plan_sha256,
            identity=identity,
            dps_verification=dps_verification,
            ledger=ledger,
            append_ledger_summary=append_ledger_summary,
            sequence_findings=sequence_findings,
            start_index=args.start_index,
            stop_index=stop_index,
            active_attempt=None,
            status=("running" if result["passed"] else "needs_retry"),
        )
        write_json(args.state_output.resolve(), state)
        print(
            json.dumps(
                {
                    "event": "physical_try_closed",
                    "logical_attempt_id": attempt["attempt_id"],
                    "attempt_id": result["attempt_id"],
                    "physical_try_ordinal": result["physical_try_ordinal"],
                    "classification": result["classification"],
                    "passed": result["passed"],
                    "returncode": result["returncode"],
                    "timed_out": result["timed_out"],
                    "reconstruction_error": result["reconstruction_error"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if pending_interruption is not None:
            raise pending_interruption
        if not result["passed"]:
            return 1

    append_ledger_summary = reconcile_phase9_append_ledger(
        append_ledger_path,
        attempts,
        plan_sha256=plan_sha256,
        identity_manifest_sha256=str(identity["manifest_sha256"]),
    )
    ledger, sequence_findings = scan_phase9_physical_ledger(attempts)
    state = build_phase9_operator_state(
        run_plan_path=args.run_plan,
        plan=plan,
        plan_sha256=plan_sha256,
        identity=identity,
        dps_verification=dps_verification,
        ledger=ledger,
        append_ledger_summary=append_ledger_summary,
        sequence_findings=sequence_findings,
        start_index=args.start_index,
        stop_index=stop_index,
        active_attempt=None,
        status="partial",
    )
    write_json(args.state_output.resolve(), state)
    if state["status"] == "passed":
        verification = verify_operator_state(args.state_output.resolve())
        write_json(
            args.state_output.resolve().parent / "joined_campaign_verification.json",
            verification,
        )
        if verification.get("passed") is not True:
            return 1
        try:
            promotion = publish_joined_campaign(
                args.state_output.resolve(), state, verification
            )
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
            return 1
        print(json.dumps(promotion, sort_keys=True), flush=True)
        return 0 if promotion.get("passed") is True else 1
    return 0 if state["status"] == "partial" else 1


if __name__ == "__main__":
    raise SystemExit(main())
