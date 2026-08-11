"""Safely manage isolated systemd sessions for live bot validation.

This module deliberately does not launch a validation itself.  It owns the
narrow lifecycle boundary around a versioned worldserver process so callers can
refuse to reuse a session built from different inputs.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence


MEMORY_MAX = "8G"
MEMORY_SWAP_MAX = "2G"
CPU_QUOTA = "300%"
_UNIT_PREFIX = "trinity-live-validation-"
_SAFE_UNIT = re.compile(r"[^a-z0-9-]+")
_SHA256 = re.compile(r"[0-9a-f]{64}")

EVIDENCE_HASH_COMPONENTS = (
    "git_commit_sha256",
    "git_dirty_state_sha256",
    "binary_sha256",
    "config_sha256",
    "database_snapshot_sha256",
    "database_schema_sha256",
    "process_session_sha256",
    "server_epoch_sha256",
    "spec_catalog_sha256",
    "provisioning_sha256",
    "gear_sha256",
    "profile_generation_sha256",
    "reference_sha256",
    "policy_sha256",
    "scenario_sha256",
    "route_sha256",
)
EVIDENCE_SCOPE_IDS = (
    "batch_id",
    "cohort_id",
    "composition_id",
    "party_id",
    "instance_id",
    "attempt_id",
    "repeat_id",
    "measurement_window_id",
)
EVIDENCE_ARTIFACT_HASHES = (
    "raw_artifact_sha256",
    "compact_artifact_sha256",
    "dvc_pointer_sha256",
    "remote_verification_receipt_sha256",
)
# Record-local IDs and artifact hashes prove uniqueness and publication state but
# are intentionally excluded from the compatibility key used to aggregate
# repeated observations under the same immutable execution conditions.
AGGREGATION_SCOPE_IDS = ("batch_id", "cohort_id", "composition_id", "party_id")


class LiveValidationSessionError(RuntimeError):
    """Raised when a live-validation session cannot be safely managed."""


class SessionLockError(LiveValidationSessionError):
    """Raised when another process owns the repository validation lock."""


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class LiveValidationSession:
    """Immutable, versioned identity for a systemd live-validation session."""

    repository: Path
    environment: str
    binary: Path
    config: Path
    git_head: str
    git_dirty_state_sha256: str
    binary_sha256: str
    config_sha256: str
    input_sha256: str
    restart_components_sha256: str
    repository_fingerprint: str
    environment_fingerprint: str
    fingerprint: str
    unit_name: str

    def metadata(self) -> dict[str, str]:
        """Return non-secret data suitable for a validation artifact."""
        return {
            "schema": "bot_live_validation_session_v2",
            "session_fingerprint": self.fingerprint,
            "unit_name": self.unit_name,
            "repository_fingerprint": self.repository_fingerprint,
            "environment_fingerprint": self.environment_fingerprint,
            "git_head": self.git_head,
            "git_dirty_state_sha256": self.git_dirty_state_sha256,
            "binary_sha256": self.binary_sha256,
            "config_sha256": self.config_sha256,
            "input_sha256": self.input_sha256,
            "restart_components_sha256": self.restart_components_sha256,
        }


@dataclass(frozen=True)
class SessionStatus:
    """The systemd state of exactly one versioned live-validation unit."""

    session: LiveValidationSession
    exists: bool
    healthy: bool
    properties: Mapping[str, str]
    returncode: int


@dataclass(frozen=True)
class SessionAction:
    """The outcome of a lifecycle operation."""

    session: LiveValidationSession
    action: str
    status: SessionStatus


def _default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(list(command), check=False, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as exc:
        raise LiveValidationSessionError(f"session lifecycle command timed out: {command[0]}") from exc


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise LiveValidationSessionError(f"required file is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return sha256_text(encoded)


def _completed_text(
    command: Sequence[str],
    *,
    command_runner: CommandRunner,
    description: str,
) -> str:
    completed = command_runner(command)
    if completed.returncode != 0:
        raise LiveValidationSessionError(f"unable to determine {description}")
    return completed.stdout


def git_dirty_state_sha256(
    repository: Path,
    *,
    command_runner: CommandRunner = _default_runner,
) -> str:
    """Hash relevant tracked and untracked state without exposing its contents."""
    pathspec = (
        "--",
        ".",
        ":(exclude)dvc.lock",
        ":(exclude)experiments/configs/all_spec_stonecore_program_status_v1.json",
        ":(exclude)artifacts/all_spec_program",
        ":(exclude)dataset",
    )
    porcelain = _completed_text(
        ["git", "-C", str(repository), "status", "--porcelain=v1", "--untracked-files=all", "-z", *pathspec],
        command_runner=command_runner,
        description="Git dirty state",
    )
    binary_diff = _completed_text(
        ["git", "-C", str(repository), "diff", "--binary", "HEAD", *pathspec],
        command_runner=command_runner,
        description="Git tracked diff",
    )
    untracked_text = _completed_text(
        ["git", "-C", str(repository), "ls-files", "--others", "--exclude-standard", "-z", *pathspec],
        command_runner=command_runner,
        description="Git untracked files",
    )
    untracked_rows = []
    for relative in sorted(value for value in untracked_text.split("\0") if value):
        candidate = (repository / relative).resolve(strict=False)
        try:
            candidate.relative_to(repository)
            metadata = candidate.lstat()
        except (OSError, ValueError):
            untracked_rows.append({"path_sha256": sha256_text(relative), "entry_type": "unreadable"})
            continue
        if stat.S_ISREG(metadata.st_mode):
            content_hash = sha256_file(candidate)
            entry_type = "regular_file"
        elif stat.S_ISLNK(metadata.st_mode):
            content_hash = sha256_text(os.readlink(candidate))
            entry_type = "symlink"
        else:
            content_hash = sha256_text(str(metadata.st_mode))
            entry_type = "unsupported"
        untracked_rows.append(
            {
                "path_sha256": sha256_text(relative),
                "entry_type": entry_type,
                "content_sha256": content_hash,
            }
        )
    return canonical_sha256(
        {
            "porcelain_sha256": sha256_text(porcelain),
            "binary_diff_sha256": sha256_text(binary_diff),
            "untracked": untracked_rows,
        }
    )


def _validated_environment(environment: str) -> str:
    normalized = environment.strip()
    if not normalized:
        raise LiveValidationSessionError("environment identity must not be empty")
    return normalized


def _repository_root(repository: Path) -> Path:
    root = repository.resolve()
    if not root.is_dir() or not (root / ".git").exists():
        raise LiveValidationSessionError(f"repository is not a Git worktree: {root}")
    return root


def git_head(repository: Path, *, command_runner: CommandRunner = _default_runner) -> str:
    completed = command_runner(["git", "-C", str(repository), "rev-parse", "HEAD"])
    head = completed.stdout.strip()
    if completed.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40,64}", head):
        raise LiveValidationSessionError("unable to determine an exact Git HEAD")
    return head


def build_session(
    repository: Path,
    environment: str,
    binary: Path,
    config: Path,
    *,
    fingerprint_paths: Sequence[Path] = (),
    restart_components: Mapping[str, str] | None = None,
    command_runner: CommandRunner = _default_runner,
) -> LiveValidationSession:
    """Build a session identity from immutable validation inputs.

    All user-controlled identity values are only represented by SHA256
    fingerprints in the resulting metadata, preventing accidental disclosure
    of environment names or local checkout paths.
    """
    root = _repository_root(repository)
    normalized_environment = _validated_environment(environment)
    resolved_binary = binary.resolve()
    resolved_config = config.resolve()
    head = git_head(root, command_runner=command_runner)
    dirty_digest = git_dirty_state_sha256(root, command_runner=command_runner)
    binary_digest = sha256_file(resolved_binary)
    config_digest = sha256_file(resolved_config)
    input_digest = canonical_sha256([sha256_file(path.resolve()) for path in fingerprint_paths])
    normalized_restart_components = {
        str(key): str(value)
        for key, value in sorted((restart_components or {}).items())
    }
    restart_components_digest = canonical_sha256(normalized_restart_components)
    repository_fingerprint = sha256_text(str(root))
    environment_fingerprint = sha256_text(normalized_environment)
    fingerprint = canonical_sha256(
        {
            "repository_fingerprint": repository_fingerprint,
            "environment_fingerprint": environment_fingerprint,
            "git_head": head,
            "git_dirty_state_sha256": dirty_digest,
            "binary_sha256": binary_digest,
            "config_sha256": config_digest,
            "input_sha256": input_digest,
            "restart_components_sha256": restart_components_digest,
        }
    )
    unit_key = sha256_text(f"{repository_fingerprint}\0{environment_fingerprint}")
    unit_fragment = _SAFE_UNIT.sub("-", f"{_UNIT_PREFIX}{unit_key[:24]}").strip("-")
    return LiveValidationSession(
        repository=root,
        environment=normalized_environment,
        binary=resolved_binary,
        config=resolved_config,
        git_head=head,
        git_dirty_state_sha256=dirty_digest,
        binary_sha256=binary_digest,
        config_sha256=config_digest,
        input_sha256=input_digest,
        restart_components_sha256=restart_components_digest,
        repository_fingerprint=repository_fingerprint,
        environment_fingerprint=environment_fingerprint,
        fingerprint=fingerprint,
        unit_name=unit_fragment,
    )


def live_validation_lock_path(repository: Path, environment: str) -> Path:
    """Return the single live-server ownership lock for a repository."""
    root = _repository_root(repository)
    _validated_environment(environment)
    repository_fingerprint = sha256_text(str(root))
    return root / ".dvc" / "tmp" / "locks" / f"live-validation-{repository_fingerprint}.lock"


def dvc_lock_path(repository: Path) -> Path:
    """Return one DVC mutation lock location for a repository."""
    root = _repository_root(repository)
    return root / ".dvc" / "tmp" / "locks" / f"live-validation-dvc-{sha256_text(str(root))}.lock"


@contextlib.contextmanager
def _file_lock(lock_path: Path) -> Iterator[Path]:
    lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SessionLockError(f"live validation lock is already held: {lock_path.name}") from exc
        try:
            yield lock_path
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def live_validation_lock(repository: Path, environment: str) -> Iterator[Path]:
    """Acquire the non-blocking lock for an environment/repository session."""
    with _file_lock(live_validation_lock_path(repository, environment)) as lock_path:
        yield lock_path


@contextlib.contextmanager
def dvc_repository_lock(repository: Path) -> Iterator[Path]:
    """Acquire a non-blocking lock for DVC-affecting work in one repository.

    A contention error is intentional: live validation must fail closed rather
    than let concurrent processes mutate shared DVC state.
    """
    with _file_lock(dvc_lock_path(repository)) as lock_path:
        yield lock_path


def session_metadata_path(session: LiveValidationSession) -> Path:
    return session.repository / ".dvc" / "tmp" / "locks" / f"{session.unit_name}.json"


def write_session_metadata(session: LiveValidationSession) -> None:
    path = session_metadata_path(session)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(session.metadata(), sort_keys=True) + "\n", encoding="utf-8")


def matching_session_metadata(session: LiveValidationSession) -> bool:
    path = session_metadata_path(session)
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("session_fingerprint") == session.fingerprint


def active_conflicting_session_units(
    session: LiveValidationSession,
    *,
    command_runner: CommandRunner = _default_runner,
) -> list[str]:
    """Find other managed worldservers that can own the shared live ports."""
    metadata_root = session.repository / ".dvc" / "tmp" / "locks"
    conflicts: list[str] = []
    for path in sorted(metadata_root.glob(f"{_UNIT_PREFIX}*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        unit_name = str(payload.get("unit_name") or "")
        if (
            payload.get("repository_fingerprint") != session.repository_fingerprint
            or unit_name == session.unit_name
            or not unit_name.startswith(_UNIT_PREFIX)
        ):
            continue
        completed = command_runner(
            [
                "systemctl",
                "--user",
                "show",
                "--no-pager",
                "--property=LoadState",
                "--property=ActiveState",
                "--property=SubState",
                "--property=MainPID",
                unit_name,
            ]
        )
        if completed.returncode != 0 or _unit_is_missing(completed):
            continue
        properties = _parse_systemctl_properties(completed.stdout)
        if (
            properties.get("LoadState") == "loaded"
            and properties.get("ActiveState") == "active"
            and properties.get("SubState") == "running"
            and int(properties.get("MainPID") or 0) > 0
        ):
            conflicts.append(unit_name)
    return conflicts


def systemd_transient_command(session: LiveValidationSession) -> list[str]:
    """Construct the deterministic, bounded command for this exact session."""
    return [
        "systemd-run",
        "--user",
        "--quiet",
        "--collect",
        f"--unit={session.unit_name}",
        "--service-type=exec",
        f"--property=MemoryMax={MEMORY_MAX}",
        f"--property=MemorySwapMax={MEMORY_SWAP_MAX}",
        f"--property=CPUQuota={CPU_QUOTA}",
        f"--working-directory={session.repository}",
        str(session.binary),
        "--config",
        str(session.config),
    ]


def _parse_systemctl_properties(output: str) -> dict[str, str]:
    properties: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator and key:
            properties[key] = value
    return properties


def _unit_is_missing(completed: subprocess.CompletedProcess[str]) -> bool:
    message = f"{completed.stdout}\n{completed.stderr}".lower()
    return "could not be found" in message or "not found" in message or "does not exist" in message


def inspect_session(
    session: LiveValidationSession,
    *,
    command_runner: CommandRunner = _default_runner,
) -> SessionStatus:
    """Inspect only the unit named by the exact session fingerprint."""
    completed = command_runner(
        [
            "systemctl",
            "--user",
            "show",
            "--no-pager",
            "--property=LoadState",
            "--property=ActiveState",
            "--property=SubState",
            "--property=Result",
            "--property=MainPID",
            session.unit_name,
        ]
    )
    properties = _parse_systemctl_properties(completed.stdout)
    missing = _unit_is_missing(completed) or properties.get("LoadState") == "not-found"
    if completed.returncode != 0 and not missing:
        raise LiveValidationSessionError("unable to inspect live validation session")
    exists = not missing and properties.get("LoadState") == "loaded"
    healthy = (
        exists
        and properties.get("ActiveState") == "active"
        and properties.get("SubState") == "running"
        and properties.get("MainPID", "0").isdigit()
        and int(properties.get("MainPID", "0")) > 0
    )
    return SessionStatus(session, exists, healthy, properties, completed.returncode)


def start_session(
    session: LiveValidationSession,
    *,
    command_runner: CommandRunner = _default_runner,
) -> SessionAction:
    """Start the exact session, refusing to overwrite an existing unit."""
    before = inspect_session(session, command_runner=command_runner)
    if before.healthy:
        return SessionAction(session, "already_healthy", before)
    if before.exists:
        raise LiveValidationSessionError("refusing to replace an existing unhealthy validation session")
    completed = command_runner(systemd_transient_command(session))
    if completed.returncode != 0:
        raise LiveValidationSessionError("systemd failed to start live validation session")
    action = SessionAction(session, "started", inspect_session(session, command_runner=command_runner))
    if not action.status.healthy:
        raise LiveValidationSessionError("live validation session did not become healthy")
    write_session_metadata(session)
    return action


def stop_session(
    session: LiveValidationSession,
    *,
    command_runner: CommandRunner = _default_runner,
) -> SessionAction:
    """Stop the exact session. A missing unit is treated as already stopped."""
    before = inspect_session(session, command_runner=command_runner)
    if not before.exists:
        return SessionAction(session, "already_stopped", before)
    completed = command_runner(["systemctl", "--user", "stop", session.unit_name])
    if completed.returncode != 0:
        raise LiveValidationSessionError("systemd failed to stop live validation session")
    return SessionAction(session, "stopped", inspect_session(session, command_runner=command_runner))


def restart_session(
    session: LiveValidationSession,
    *,
    command_runner: CommandRunner = _default_runner,
) -> SessionAction:
    """Stop then start the exact session; never reuse another fingerprint."""
    stop_session(session, command_runner=command_runner)
    return start_session(session, command_runner=command_runner)


def ensure_healthy_matching_session(
    session: LiveValidationSession,
    *,
    command_runner: CommandRunner = _default_runner,
) -> SessionAction:
    """Return a healthy matching session or create/recreate exactly that unit."""
    conflicts = active_conflicting_session_units(session, command_runner=command_runner)
    if conflicts:
        raise LiveValidationSessionError(
            "another managed worldserver owns the shared live ports: "
            + ", ".join(conflicts)
        )
    status = inspect_session(session, command_runner=command_runner)
    if status.healthy and matching_session_metadata(session):
        return SessionAction(session, "already_healthy", status)
    if status.exists:
        return restart_session(session, command_runner=command_runner)
    return start_session(session, command_runner=command_runner)


def _validated_hashes(values: Mapping[str, str], required: Sequence[str], label: str) -> dict[str, str]:
    normalized = {str(key): str(value) for key, value in values.items()}
    missing = [key for key in required if not _SHA256.fullmatch(normalized.get(key, ""))]
    extras = sorted(set(normalized) - set(required))
    if missing or extras:
        detail = []
        if missing:
            detail.append(f"missing or invalid: {', '.join(missing)}")
        if extras:
            detail.append(f"unexpected: {', '.join(extras)}")
        raise LiveValidationSessionError(f"invalid {label} ({'; '.join(detail)})")
    return {key: normalized[key] for key in required}


def _validated_scope_ids(values: Mapping[str, str]) -> dict[str, str]:
    normalized = {str(key): str(value).strip() for key, value in values.items()}
    missing = [key for key in EVIDENCE_SCOPE_IDS if not normalized.get(key)]
    extras = sorted(set(normalized) - set(EVIDENCE_SCOPE_IDS))
    if missing or extras:
        detail = []
        if missing:
            detail.append(f"missing: {', '.join(missing)}")
        if extras:
            detail.append(f"unexpected: {', '.join(extras)}")
        raise LiveValidationSessionError(f"invalid evidence scope IDs ({'; '.join(detail)})")
    return {key: normalized[key] for key in EVIDENCE_SCOPE_IDS}


def build_evidence_envelope(
    component_hashes: Mapping[str, str],
    scope_ids: Mapping[str, str],
    artifact_hashes: Mapping[str, str],
    *,
    freshness: str = "current",
    superseded_by: str | None = None,
) -> dict[str, Any]:
    """Build the shared immutable identity used by runners, reports, and publishers."""
    components = _validated_hashes(component_hashes, EVIDENCE_HASH_COMPONENTS, "evidence component hashes")
    scopes = _validated_scope_ids(scope_ids)
    artifacts = _validated_hashes(artifact_hashes, EVIDENCE_ARTIFACT_HASHES, "evidence artifact hashes")
    if freshness not in {"current", "stale", "superseded", "current_unpublished"}:
        raise LiveValidationSessionError(f"invalid evidence freshness state: {freshness}")
    compatibility_payload = {
        "component_hashes": components,
        "scope_ids": {key: scopes[key] for key in AGGREGATION_SCOPE_IDS},
    }
    record_payload = {
        **compatibility_payload,
        "scope_ids": scopes,
        "artifact_hashes": artifacts,
        "freshness": freshness,
        "superseded_by": superseded_by,
    }
    return {
        "schema": "bot_live_evidence_envelope_v1",
        "component_hashes": components,
        "scope_ids": scopes,
        "artifact_hashes": artifacts,
        "aggregation_identity_sha256": canonical_sha256(compatibility_payload),
        "attempt_identity_sha256": canonical_sha256(record_payload),
        "freshness": freshness,
        "superseded_by": superseded_by,
        "identity_complete": True,
    }


def evidence_compatible_for_aggregation(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Return true only for current envelopes with identical aggregation identity."""
    return (
        left.get("schema") == "bot_live_evidence_envelope_v1"
        and right.get("schema") == "bot_live_evidence_envelope_v1"
        and left.get("identity_complete") is True
        and right.get("identity_complete") is True
        and left.get("freshness") in {"current", "current_unpublished"}
        and right.get("freshness") in {"current", "current_unpublished"}
        and bool(left.get("aggregation_identity_sha256"))
        and left.get("aggregation_identity_sha256") == right.get("aggregation_identity_sha256")
    )


def classify_evidence_freshness(
    envelopes: Sequence[Mapping[str, Any]],
    current_envelope: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Mark incompatible older evidence stale without deleting or rewriting it."""
    current_aggregation = str(current_envelope.get("aggregation_identity_sha256") or "")
    current_attempt = str(current_envelope.get("attempt_identity_sha256") or "")
    rows = []
    for envelope in envelopes:
        row = dict(envelope)
        if str(row.get("aggregation_identity_sha256") or "") == current_aggregation:
            row["freshness"] = "current"
            row["superseded_by"] = None
        else:
            row["freshness"] = "superseded"
            row["superseded_by"] = current_attempt
        rows.append(row)
    return rows


def advance_evidence_epoch(
    previous: Mapping[str, Any] | None,
    *,
    restart_identity_sha256: str,
    profile_content_sha256: str,
    open_attempt_count: int = 0,
) -> dict[str, Any]:
    """Advance immutable server/logical epochs and profile generations.

    A profile rollback is another generation, never reuse of an older ID. Any
    transition while an attempt is open fails closed so attempts cannot cross an
    epoch or generation boundary.
    """
    if not _SHA256.fullmatch(restart_identity_sha256) or not _SHA256.fullmatch(profile_content_sha256):
        raise LiveValidationSessionError("epoch identities must be SHA256 values")
    prior = dict(previous or {})
    same_restart = prior.get("restart_identity_sha256") == restart_identity_sha256
    same_profile = prior.get("profile_content_sha256") == profile_content_sha256
    transition = "unchanged" if prior and same_restart and same_profile else (
        "initialized" if not prior else ("process_restart" if not same_restart else "profile_generation")
    )
    if transition not in {"unchanged", "initialized"} and open_attempt_count > 0:
        raise LiveValidationSessionError("open attempts must drain before an evidence epoch transition")
    if transition == "unchanged":
        return {**prior, "transition": transition, "restart_required": False}

    server_sequence = int(prior.get("server_epoch_sequence") or 0)
    logical_sequence = int(prior.get("logical_epoch_sequence") or 0)
    profile_sequence = int(prior.get("profile_generation_sequence") or 0)
    if not prior or not same_restart:
        server_sequence += 1
    logical_sequence += 1
    if not prior or not same_profile:
        profile_sequence += 1
    prior_profile_generation = str(prior.get("profile_generation_id") or "")
    profile_generation_id = prior_profile_generation if prior and same_profile else canonical_sha256(
        {
            "sequence": profile_sequence,
            "profile_content_sha256": profile_content_sha256,
            "previous_profile_generation_id": prior_profile_generation,
        }
    )
    prior_server_epoch = str(prior.get("server_epoch_id") or "")
    server_epoch_id = prior_server_epoch if prior and same_restart else canonical_sha256(
        {
            "sequence": server_sequence,
            "restart_identity_sha256": restart_identity_sha256,
            "previous_server_epoch_id": prior_server_epoch,
        }
    )
    logical_epoch_id = canonical_sha256(
        {
            "sequence": logical_sequence,
            "server_epoch_id": server_epoch_id,
            "profile_generation_id": profile_generation_id,
            "previous_logical_epoch_id": str(prior.get("logical_epoch_id") or ""),
        }
    )
    return {
        "schema": "bot_live_evidence_epoch_v1",
        "restart_identity_sha256": restart_identity_sha256,
        "profile_content_sha256": profile_content_sha256,
        "server_epoch_sequence": server_sequence,
        "logical_epoch_sequence": logical_sequence,
        "profile_generation_sequence": profile_sequence,
        "server_epoch_id": server_epoch_id,
        "logical_epoch_id": logical_epoch_id,
        "profile_generation_id": profile_generation_id,
        "transition": transition,
        "restart_required": transition == "process_restart",
    }


def acceptance_facts_from_report(
    report: Mapping[str, Any],
    *,
    identity_required: bool = False,
    session_required: bool = False,
) -> dict[str, Any]:
    """Extract acceptance inputs while intentionally ignoring stored claim booleans."""
    stages = []
    for row in report.get("stages") or []:
        if not isinstance(row, Mapping):
            continue
        missing = sorted(str(value) for value in (row.get("missing") or []) if value)
        if "missing" not in row:
            missing.append("missing_stage_evidence_facts")
        stages.append(
            {
                "stage": str(row.get("stage") or ""),
                "missing": missing,
            }
        )
    context = report.get("validation_context") if isinstance(report.get("validation_context"), Mapping) else {}
    evidence = report.get("evidence") if isinstance(report.get("evidence"), Mapping) else {}
    manifest = report.get("validation_route_manifest") if isinstance(report.get("validation_route_manifest"), Mapping) else {}
    watchdog = report.get("watchdog_state") if isinstance(report.get("watchdog_state"), Mapping) else {}
    envelope = report.get("evidence_envelope") if isinstance(report.get("evidence_envelope"), Mapping) else {}
    session = report.get("session") if isinstance(report.get("session"), Mapping) else {}
    calibration = report.get("calibration_acceptance") if isinstance(report.get("calibration_acceptance"), Mapping) else {}
    role_audit = report.get("role_efficiency_audit") if isinstance(report.get("role_efficiency_audit"), Mapping) else {}
    return {
        "schema": "bot_live_acceptance_facts_v1",
        "returncode": int(report.get("returncode") or 0),
        "timed_out": bool(report.get("timed_out")),
        "stages": stages,
        "failure_labels": sorted(str(value) for value in (report.get("failure_labels") or []) if value),
        "validation_context": dict(context),
        "evidence": dict(evidence),
        "validation_route_manifest": dict(manifest),
        "watchdog_state": dict(watchdog),
        "completion_reason": str(report.get("completion_reason") or ""),
        "acceptance_mode": "calibration" if calibration else "standard",
        "calibration_rejections": sorted(str(value) for value in (calibration.get("rejections") or []) if value),
        "role_quality_audit_failed": bool(role_audit) and role_audit.get("passed") is not True,
        "identity_required": identity_required,
        "identity_complete": envelope.get("identity_complete") is True,
        "session_required": session_required,
        "session_closed": session.get("inactive_after_attempt") is True,
    }


def _scope_set(rows: Any) -> set[tuple[str, int]]:
    return {
        (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        for row in (rows or [])
        if isinstance(row, Mapping) and row.get("route_node_id")
    }


def evaluate_acceptance(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Purely recompute acceptance from facts and canonical manifests."""
    if facts.get("schema") != "bot_live_acceptance_facts_v1":
        raise LiveValidationSessionError("unexpected acceptance facts schema")
    stages = [row for row in (facts.get("stages") or []) if isinstance(row, Mapping)]
    stage_passes = [not [value for value in (row.get("missing") or []) if value] for row in stages]
    passed_count = sum(stage_passes)
    failure_labels = [str(value) for value in (facts.get("failure_labels") or []) if value]
    context = facts.get("validation_context") if isinstance(facts.get("validation_context"), Mapping) else {}
    evidence = facts.get("evidence") if isinstance(facts.get("evidence"), Mapping) else {}
    manifest = facts.get("validation_route_manifest") if isinstance(facts.get("validation_route_manifest"), Mapping) else {}
    watchdog = facts.get("watchdog_state") if isinstance(facts.get("watchdog_state"), Mapping) else {}
    routes = [row for row in (manifest.get("routes") or []) if isinstance(row, Mapping)]
    expected_scopes = {
        (str(route.get("route_node_id") or ""), int(route.get("route_generation") or index))
        for index, route in enumerate(routes, 1)
        if route.get("route_node_id")
    }
    expected_boss_scopes = {
        (str(route.get("route_node_id") or ""), int(route.get("route_generation") or index))
        for index, route in enumerate(routes, 1)
        if route.get("route_node_id") and str(route.get("kind") or "") == "boss"
    }
    terminal_scopes = _scope_set(evidence.get("route_terminal_evidence"))
    boss_scopes = _scope_set(evidence.get("real_boss_kill_evidence"))
    manifest_complete = bool(evidence.get("manifest_completion_evidence"))
    authoritative_stonecore_boss_clear = (
        context.get("scenario_id") == "stonecore_5n"
        and not context.get("segment_id")
        and not context.get("route_node_id")
        and len(routes) == 14
        and len(expected_boss_scopes) == 4
        and manifest_complete
        and not (expected_scopes - terminal_scopes)
        and not (expected_boss_scopes - boss_scopes)
        and not evidence.get("forbidden_completion_assists")
        and not bool(facts.get("timed_out"))
        and int(facts.get("returncode") or 0) == 0
        and not watchdog.get("death_loop")
        and not watchdog.get("repeated_decision_loop")
        and str(facts.get("completion_reason") or "") != "no_progress_watchdog"
    )

    rejections = []
    if not stages:
        rejections.append("missing_stage_facts")
    if stages and passed_count != len(stages) and not manifest_complete:
        rejections.append("not_all_stages_passed")
    if bool(facts.get("timed_out")):
        rejections.append("timeout_is_not_final_evidence")
    if int(facts.get("returncode") or 0) != 0:
        rejections.append("nonzero_return_is_not_final_evidence")
    if failure_labels:
        if facts.get("acceptance_mode") == "calibration":
            rejections.extend(str(value) for value in (facts.get("calibration_rejections") or []) if value)
        else:
            rejections.append("failure_labels_present")
    if facts.get("role_quality_audit_failed") and not authoritative_stonecore_boss_clear:
        rejections.append("stonecore_role_quality_audit_failed")
    if context.get("segment_id") or context.get("route_node_id"):
        rejections.append("segment_or_route_context_is_debug_only")
    if (
        bool(facts.get("timed_out"))
        or watchdog.get("death_loop")
        or watchdog.get("repeated_decision_loop")
        or str(facts.get("completion_reason") or "") == "no_progress_watchdog"
    ):
        rejections.append("watchdog_failure_is_not_final_evidence")
    forbidden_assists = evidence.get("forbidden_completion_assists") or []
    if forbidden_assists:
        rejections.append("forced_or_teacher_kill_evidence")
        if int(evidence.get("teacher_assisted_kills") or 0) > 0 and not evidence.get("real_boss_kill_evidence"):
            rejections.append("teacher_assisted_only_evidence")
    if evidence.get("manifest_completion_evidence"):
        if not routes:
            rejections.append("missing_validation_route_manifest")
        else:
            if expected_scopes - terminal_scopes:
                rejections.append("missing_node_terminal_evidence")
            if expected_boss_scopes - boss_scopes:
                rejections.append("missing_real_boss_kill_evidence")
    if facts.get("identity_required") and not facts.get("identity_complete"):
        rejections.append("incomplete_evidence_identity")
    if facts.get("session_required") and not facts.get("session_closed"):
        rejections.append("session_not_closed")
    rejections = list(dict.fromkeys(rejections))
    summary = {
        "schema": "bot_live_acceptance_result_v1",
        "accepted": not rejections,
        "all_stages_passed": bool(stages) and passed_count == len(stages),
        "manifest_complete": manifest_complete,
        "authoritative_stonecore_boss_clear": authoritative_stonecore_boss_clear,
        "role_quality_advisory": bool(facts.get("role_quality_audit_failed")) and authoritative_stonecore_boss_clear,
        "passed_count": passed_count,
        "failed_count": max(0, len(stages) - passed_count),
        "rejections": rejections,
    }
    summary["facts_sha256"] = canonical_sha256(facts)
    summary["result_sha256"] = canonical_sha256(summary)
    return summary


def acceptance_summary_discrepancies(
    report: Mapping[str, Any],
    result: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Compare legacy stored summaries with independently recomputed results."""
    expected = {
        "acceptable_final_evidence": bool(result.get("accepted")),
        "all_passed": bool(result.get("all_stages_passed")),
        "passed": int(result.get("passed_count") or 0),
        "failed": int(result.get("failed_count") or 0),
        "final_evidence_rejections": list(result.get("rejections") or []),
    }
    discrepancies = []
    for field, expected_value in expected.items():
        if field in report and report.get(field) != expected_value:
            discrepancies.append({"field": field, "stored": report.get(field), "recomputed": expected_value})
    return discrepancies


def apply_acceptance_evaluation(
    report: dict[str, Any],
    *,
    identity_required: bool = False,
    session_required: bool = False,
) -> dict[str, Any]:
    facts = acceptance_facts_from_report(
        report,
        identity_required=identity_required,
        session_required=session_required,
    )
    result = evaluate_acceptance(facts)
    stored_facts = report.get("acceptance_facts") if isinstance(report.get("acceptance_facts"), Mapping) else {}
    same_fact_basis = not stored_facts or canonical_sha256(stored_facts) == canonical_sha256(facts)
    discrepancies = acceptance_summary_discrepancies(report, result) if same_fact_basis else []
    if discrepancies:
        result = dict(result)
        result["accepted"] = False
        result["rejections"] = list(dict.fromkeys([*(result.get("rejections") or []), "stored_summary_discrepancy"]))
        result["result_sha256"] = canonical_sha256({key: value for key, value in result.items() if key != "result_sha256"})
    report["acceptance_facts"] = facts
    report["acceptance_verification"] = {**result, "stored_summary_discrepancies": discrepancies}
    report["acceptable_final_evidence"] = bool(result["accepted"])
    report["all_passed"] = bool(result["all_stages_passed"])
    report["passed"] = int(result["passed_count"])
    report["failed"] = int(result["failed_count"])
    report["final_evidence_rejections"] = list(result["rejections"])
    return report


def verify_report_acceptance(report: Mapping[str, Any]) -> dict[str, Any]:
    stored_facts = report.get("acceptance_facts") if isinstance(report.get("acceptance_facts"), Mapping) else {}
    facts = acceptance_facts_from_report(
        report,
        identity_required=bool(stored_facts.get("identity_required")) or isinstance(report.get("evidence_envelope"), Mapping),
        session_required=bool(stored_facts.get("session_required")),
    )
    result = evaluate_acceptance(facts)
    discrepancies = acceptance_summary_discrepancies(report, result)
    return {
        "schema": "bot_live_acceptance_verification_v1",
        "accepted": bool(result.get("accepted")) and not discrepancies,
        "recomputed": result,
        "discrepancies": discrepancies,
        "fail_closed": bool(discrepancies),
    }


def phase2_contract() -> dict[str, Any]:
    components = {name: sha256_text(f"component:{name}:v1") for name in EVIDENCE_HASH_COMPONENTS}
    scopes = {name: f"scope:{name}:v1" for name in EVIDENCE_SCOPE_IDS}
    artifacts = {name: sha256_text(f"artifact:{name}:v1") for name in EVIDENCE_ARTIFACT_HASHES}
    baseline = build_evidence_envelope(components, scopes, artifacts)
    changed_components = {}
    for name in EVIDENCE_HASH_COMPONENTS:
        changed = dict(components)
        changed[name] = sha256_text(f"component:{name}:v2")
        changed_envelope = build_evidence_envelope(changed, scopes, artifacts)
        changed_components[name] = not evidence_compatible_for_aggregation(baseline, changed_envelope)
    changed_scopes = {}
    for name in AGGREGATION_SCOPE_IDS:
        changed = dict(scopes)
        changed[name] = f"scope:{name}:v2"
        changed_envelope = build_evidence_envelope(components, changed, artifacts)
        changed_scopes[name] = not evidence_compatible_for_aggregation(baseline, changed_envelope)

    first_epoch = advance_evidence_epoch(
        None,
        restart_identity_sha256=sha256_text("restart:v1"),
        profile_content_sha256=sha256_text("profile:v1"),
    )
    profile_reload = advance_evidence_epoch(
        first_epoch,
        restart_identity_sha256=sha256_text("restart:v1"),
        profile_content_sha256=sha256_text("profile:v2"),
    )
    rollback = advance_evidence_epoch(
        profile_reload,
        restart_identity_sha256=sha256_text("restart:v1"),
        profile_content_sha256=sha256_text("profile:v1"),
    )
    open_attempt_blocked = False
    try:
        advance_evidence_epoch(
            rollback,
            restart_identity_sha256=sha256_text("restart:v2"),
            profile_content_sha256=sha256_text("profile:v1"),
            open_attempt_count=1,
        )
    except LiveValidationSessionError:
        open_attempt_blocked = True

    facts = {
        "schema": "bot_live_acceptance_facts_v1",
        "returncode": 0,
        "timed_out": False,
        "stages": [{"stage": "phase2_contract", "missing": []}],
        "failure_labels": [],
        "validation_context": {},
        "evidence": {},
        "validation_route_manifest": {},
        "watchdog_state": {},
        "identity_required": True,
        "identity_complete": True,
        "session_required": False,
        "session_closed": False,
    }
    acceptance = evaluate_acceptance(facts)
    tampered_report = {
        "returncode": 0,
        "timed_out": False,
        "stages": [{"stage": "phase2_contract", "missing": []}],
        "failure_labels": [],
        "validation_context": {},
        "evidence": {},
        "validation_route_manifest": {},
        "watchdog_state": {},
        "acceptable_final_evidence": False,
        "all_passed": False,
        "passed": 0,
        "failed": 1,
        "final_evidence_rejections": ["stored_only_claim"],
    }
    tampered_verification = verify_report_acceptance(tampered_report)
    booleans_only_verification = verify_report_acceptance(
        {"acceptable_final_evidence": True, "all_passed": True}
    )
    gate_passed = (
        all(changed_components.values())
        and all(changed_scopes.values())
        and first_epoch["logical_epoch_id"] != profile_reload["logical_epoch_id"] != rollback["logical_epoch_id"]
        and first_epoch["profile_generation_id"] != rollback["profile_generation_id"]
        and open_attempt_blocked
        and acceptance["accepted"]
        and not tampered_verification["accepted"]
        and tampered_verification["fail_closed"]
        and not booleans_only_verification["accepted"]
    )
    return {
        "schema": "all_spec_phase2_evidence_contract_v1",
        "gate_passed": gate_passed,
        "required_hash_components": list(EVIDENCE_HASH_COMPONENTS),
        "required_scope_ids": list(EVIDENCE_SCOPE_IDS),
        "required_artifact_hashes": list(EVIDENCE_ARTIFACT_HASHES),
        "aggregation_scope_ids": list(AGGREGATION_SCOPE_IDS),
        "identity_change_blocks_aggregation": {**changed_components, **changed_scopes},
        "epoch_proof": {
            "initial": first_epoch,
            "profile_reload": profile_reload,
            "rollback": rollback,
            "open_attempt_transition_blocked": open_attempt_blocked,
        },
        "acceptance_proof": {
            "canonical_acceptance": acceptance,
            "tampered_stored_summary": tampered_verification,
            "booleans_only_report": booleans_only_verification,
        },
    }


def write_phase2_contract(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = phase2_contract()
    (output_dir / "contract.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema": "all_spec_phase2_evidence_contract_manifest_v1",
        "gate_passed": bool(payload["gate_passed"]),
        "contract_sha256": sha256_file(output_dir / "contract.json"),
        "component_count": len(EVIDENCE_HASH_COMPONENTS),
        "scope_id_count": len(EVIDENCE_SCOPE_IDS),
        "artifact_hash_count": len(EVIDENCE_ARTIFACT_HASHES),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Phase 2 composite evidence identity contract")
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/all_spec_phase2_evidence_contract"))
    args = parser.parse_args()
    manifest = write_phase2_contract(args.output_dir)
    print(json.dumps(manifest, sort_keys=True))
    return 0 if manifest["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
