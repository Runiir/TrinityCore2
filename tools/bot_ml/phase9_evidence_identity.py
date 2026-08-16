"""Validate the immutable Phase 9 database and live runtime identity binding."""

from __future__ import annotations

from typing import Any, Mapping

from .live_validation_session import canonical_sha256


SCHEMA = "all_spec_phase9_evidence_identity_manifest_v2"
REQUIRED_COMPONENTS = (
    "source_identity_sha256",
    "worldserver_binary_sha256",
    "database_snapshot_sha256",
    "database_schema_sha256",
    "server_epoch_sha256",
    "profile_generation_sha256",
    "build_projection_sha256",
)
REQUIRED_ARTIFACTS = (
    "target_catalog_sha256",
    "pair_policy_sha256",
    "pairwise_matrix_sha256",
    "route_manifest_sha256",
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


def _valid_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def build_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the cross-campaign identity, excluding per-process runtime state."""
    bound_build = payload.get("build_identity")
    if not isinstance(bound_build, Mapping):
        raise ValueError("Phase 9 evidence identity manifest is missing build identity")
    projection = {
        "git_commit": str(bound_build.get("git_commit") or "").lower(),
        "source_tree_clean": bound_build.get("source_tree_clean"),
        "worldserver_binary_sha256": str(
            bound_build.get("worldserver_binary_sha256") or ""
        ).lower(),
        "database_snapshot_sha256": str(
            bound_build.get("database_snapshot_sha256") or ""
        ).lower(),
        "database_schema_sha256": str(
            bound_build.get("database_schema_sha256") or ""
        ).lower(),
        "profile_content_hash": str(
            bound_build.get("profile_content_hash") or ""
        ).lower(),
    }
    if (
        len(projection["git_commit"]) not in (40, 64)
        or any(character not in "0123456789abcdef" for character in projection["git_commit"])
        or projection["source_tree_clean"] is not True
        or any(
            not _valid_sha256(projection[name])
            for name in (
                "worldserver_binary_sha256",
                "database_snapshot_sha256",
                "database_schema_sha256",
                "profile_content_hash",
            )
        )
    ):
        raise ValueError("Phase 9 evidence identity build projection is invalid")
    return projection


build_compatibility_projection = build_projection


def validate_manifest(
    payload: Mapping[str, Any],
    *,
    runtime_identity: Mapping[str, Any] | None = None,
    artifact_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    manifest = dict(payload)
    if manifest.get("schema") != SCHEMA:
        raise ValueError("unexpected Phase 9 evidence identity manifest schema")
    stored_hash = str(manifest.pop("manifest_sha256", ""))
    if not _valid_sha256(stored_hash) or canonical_sha256(manifest) != stored_hash:
        raise ValueError("Phase 9 evidence identity manifest hash mismatch")
    components = manifest.get("component_hashes")
    bound_runtime = manifest.get("runtime_identity")
    bound_artifacts = manifest.get("artifact_hashes")
    if not isinstance(components, Mapping) or not isinstance(bound_runtime, Mapping) or not isinstance(bound_artifacts, Mapping):
        raise ValueError("Phase 9 evidence identity manifest is incomplete")
    if any(not _valid_sha256(components.get(name)) for name in REQUIRED_COMPONENTS):
        raise ValueError("Phase 9 evidence identity manifest has invalid component hashes")
    if any(not _valid_sha256(bound_artifacts.get(name)) for name in REQUIRED_ARTIFACTS):
        raise ValueError("Phase 9 evidence identity manifest has invalid artifact hashes")

    projection = build_projection(manifest)
    source_identity = {
        "git_commit": projection["git_commit"],
        "source_tree_clean": True,
    }
    if (
        canonical_sha256(source_identity) != components["source_identity_sha256"]
        or projection["worldserver_binary_sha256"] != components["worldserver_binary_sha256"]
        or projection["database_snapshot_sha256"] != components["database_snapshot_sha256"]
        or projection["database_schema_sha256"] != components["database_schema_sha256"]
        or canonical_sha256(projection) != components["build_projection_sha256"]
    ):
        raise ValueError("Phase 9 evidence identity build binding is invalid")

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
        or not _valid_sha256(expected_profile["profile_content_hash"])
        or projection["profile_content_hash"] != expected_profile["profile_content_hash"]
        or canonical_sha256(expected_server) != components["server_epoch_sha256"]
        or canonical_sha256(expected_profile) != components["profile_generation_sha256"]
    ):
        raise ValueError("Phase 9 evidence identity runtime binding is invalid")

    if artifact_hashes is not None:
        observed_artifacts = {name: str(artifact_hashes.get(name) or "") for name in REQUIRED_ARTIFACTS}
        expected_artifacts = {name: str(bound_artifacts.get(name) or "") for name in REQUIRED_ARTIFACTS}
        if observed_artifacts != expected_artifacts:
            raise ValueError("current Phase 9 matrix, policy, catalog, or route manifest does not match the evidence identity")

    if runtime_identity is not None:
        observed_server = server_epoch_identity(
            server_epoch=int(runtime_identity.get("server_epoch") or 0),
            server_process_id=int(runtime_identity.get("server_process_id") or runtime_identity.get("server_pid") or 0),
            session_fingerprint=str(runtime_identity.get("session_fingerprint") or ""),
            max_active_cohorts=int(runtime_identity.get("max_active_cohorts") or 0),
        )
        observed_profile = profile_generation_identity(
            profile_generation=int(runtime_identity.get("profile_generation") or 0),
            profile_content_hash=str(runtime_identity.get("profile_content_hash") or ""),
        )
        if observed_server != expected_server or observed_profile != expected_profile:
            raise ValueError("live runtime does not match Phase 9 evidence identity manifest")

    return {**manifest, "manifest_sha256": stored_hash}
