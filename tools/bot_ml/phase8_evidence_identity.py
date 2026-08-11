"""Validate the immutable Phase 8 database and live runtime identity binding."""

from __future__ import annotations

from typing import Any, Mapping

from .live_validation_session import canonical_sha256


SCHEMA = "all_spec_phase8_evidence_identity_manifest_v1"
REQUIRED_COMPONENTS = (
    "database_snapshot_sha256",
    "database_schema_sha256",
    "server_epoch_sha256",
    "profile_generation_sha256",
)


def server_epoch_identity(
    *,
    server_epoch: int,
    server_process_id: int,
    session_fingerprint: str,
    max_active_cohorts: int = 1,
) -> dict[str, Any]:
    return {
        "server_epoch": int(server_epoch),
        "server_process_id": int(server_process_id),
        "session_fingerprint": str(session_fingerprint),
        "max_active_cohorts": int(max_active_cohorts),
    }


def profile_generation_identity(
    *,
    profile_generation: int,
    profile_content_hash: str,
) -> dict[str, Any]:
    return {
        "profile_generation": int(profile_generation),
        "profile_content_hash": str(profile_content_hash).lower(),
    }


def validate_manifest(
    payload: Mapping[str, Any],
    *,
    runtime_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = dict(payload)
    if manifest.get("schema") != SCHEMA:
        raise ValueError("unexpected Phase 8 evidence identity manifest schema")
    stored_hash = str(manifest.pop("manifest_sha256", ""))
    if len(stored_hash) != 64 or canonical_sha256(manifest) != stored_hash:
        raise ValueError("Phase 8 evidence identity manifest hash mismatch")
    components = manifest.get("component_hashes")
    bound_runtime = manifest.get("runtime_identity")
    if not isinstance(components, Mapping) or not isinstance(bound_runtime, Mapping):
        raise ValueError("Phase 8 evidence identity manifest is incomplete")
    if any(
        len(str(components.get(name) or "")) != 64
        or any(
            character not in "0123456789abcdef"
            for character in str(components.get(name) or "")
        )
        for name in REQUIRED_COMPONENTS
    ):
        raise ValueError("Phase 8 evidence identity manifest has invalid component hashes")
    expected_server = server_epoch_identity(
        server_epoch=int(bound_runtime.get("server_epoch") or 0),
        server_process_id=int(bound_runtime.get("server_process_id") or 0),
        session_fingerprint=str(bound_runtime.get("session_fingerprint") or ""),
        max_active_cohorts=int(bound_runtime.get("max_active_cohorts") or 0),
    )
    expected_profile = profile_generation_identity(
        profile_generation=int(bound_runtime.get("profile_generation") or 0),
        profile_content_hash=str(bound_runtime.get("profile_content_hash") or ""),
    )
    if (
        expected_server["server_epoch"] <= 0
        or expected_server["server_process_id"] <= 0
        or not expected_server["session_fingerprint"]
        or expected_server["max_active_cohorts"] != 1
        or expected_profile["profile_generation"] <= 0
        or len(expected_profile["profile_content_hash"]) != 64
        or canonical_sha256(expected_server) != components["server_epoch_sha256"]
        or canonical_sha256(expected_profile) != components["profile_generation_sha256"]
    ):
        raise ValueError("Phase 8 evidence identity runtime binding is invalid")
    if runtime_identity is not None:
        observed_server = server_epoch_identity(
            server_epoch=int(runtime_identity.get("server_epoch") or 0),
            server_process_id=int(
                runtime_identity.get("server_process_id")
                or runtime_identity.get("server_pid")
                or 0
            ),
            session_fingerprint=str(runtime_identity.get("session_fingerprint") or ""),
            max_active_cohorts=int(runtime_identity.get("max_active_cohorts") or 0),
        )
        observed_profile = profile_generation_identity(
            profile_generation=int(runtime_identity.get("profile_generation") or 0),
            profile_content_hash=str(runtime_identity.get("profile_content_hash") or ""),
        )
        if observed_server != expected_server or observed_profile != expected_profile:
            raise ValueError("live runtime does not match Phase 8 evidence identity manifest")
    return {**manifest, "manifest_sha256": stored_hash}
