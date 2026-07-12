"""Safely manage isolated systemd sessions for live bot validation.

This module deliberately does not launch a validation itself.  It owns the
narrow lifecycle boundary around a versioned worldserver process so callers can
refuse to reuse a session built from different inputs.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Mapping, Sequence


MEMORY_MAX = "8G"
MEMORY_SWAP_MAX = "2G"
CPU_QUOTA = "300%"
_UNIT_PREFIX = "trinity-live-validation-"
_SAFE_UNIT = re.compile(r"[^a-z0-9-]+")


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
    binary_sha256: str
    config_sha256: str
    input_sha256: str
    repository_fingerprint: str
    environment_fingerprint: str
    fingerprint: str
    unit_name: str

    def metadata(self) -> dict[str, str]:
        """Return non-secret data suitable for a validation artifact."""
        return {
            "schema": "bot_live_validation_session_v1",
            "session_fingerprint": self.fingerprint,
            "unit_name": self.unit_name,
            "repository_fingerprint": self.repository_fingerprint,
            "environment_fingerprint": self.environment_fingerprint,
            "git_head": self.git_head,
            "binary_sha256": self.binary_sha256,
            "config_sha256": self.config_sha256,
            "input_sha256": self.input_sha256,
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
    binary_digest = sha256_file(resolved_binary)
    config_digest = sha256_file(resolved_config)
    input_digest = sha256_text("\0".join(sha256_file(path.resolve()) for path in fingerprint_paths))
    repository_fingerprint = sha256_text(str(root))
    environment_fingerprint = sha256_text(normalized_environment)
    fingerprint = sha256_text(
        "\0".join((repository_fingerprint, environment_fingerprint, head, binary_digest, config_digest, input_digest))
    )
    unit_key = sha256_text(f"{repository_fingerprint}\0{environment_fingerprint}")
    unit_fragment = _SAFE_UNIT.sub("-", f"{_UNIT_PREFIX}{unit_key[:24]}").strip("-")
    return LiveValidationSession(
        repository=root,
        environment=normalized_environment,
        binary=resolved_binary,
        config=resolved_config,
        git_head=head,
        binary_sha256=binary_digest,
        config_sha256=config_digest,
        input_sha256=input_digest,
        repository_fingerprint=repository_fingerprint,
        environment_fingerprint=environment_fingerprint,
        fingerprint=fingerprint,
        unit_name=unit_fragment,
    )


def live_validation_lock_path(repository: Path, environment: str) -> Path:
    """Return the session lock location keyed by repository and environment."""
    root = _repository_root(repository)
    environment_fingerprint = sha256_text(_validated_environment(environment))
    repository_fingerprint = sha256_text(str(root))
    lock_key = sha256_text(f"{repository_fingerprint}\0{environment_fingerprint}")
    return root / ".dvc" / "tmp" / "locks" / f"live-validation-{lock_key}.lock"


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
    status = inspect_session(session, command_runner=command_runner)
    if status.healthy and matching_session_metadata(session):
        return SessionAction(session, "already_healthy", status)
    if status.exists:
        return restart_session(session, command_runner=command_runner)
    return start_session(session, command_runner=command_runner)
