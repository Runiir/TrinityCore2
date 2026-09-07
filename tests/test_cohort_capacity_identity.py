from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import pytest

from tools.bot_ml import build_phase8_evidence_identity_manifest as phase8_builder
from tools.bot_ml import build_phase9_evidence_identity_manifest as phase9_builder
from tools.bot_ml.cohort_capacity import (
    require_positive_cohort_capacity,
    validate_idle_cohort_registry,
)
from tools.bot_ml.live_validation_session import canonical_sha256
from tools.bot_ml.phase8_evidence_identity import (
    build_projection as phase8_build_projection,
    profile_generation_identity as phase8_profile_generation_identity,
    server_epoch_identity as phase8_server_epoch_identity,
    validate_manifest as validate_phase8_manifest,
)
from tools.bot_ml.phase9_evidence_identity import (
    build_projection as phase9_build_projection,
    profile_generation_identity as phase9_profile_generation_identity,
    server_epoch_identity as phase9_server_epoch_identity,
    validate_manifest as validate_phase9_manifest,
)


def _build_identity(profile_hash: str) -> dict[str, Any]:
    return {
        "git_commit": "d" * 40,
        "source_tree_clean": True,
        "worldserver_binary_sha256": "e" * 64,
        "database_snapshot_sha256": "a" * 64,
        "database_schema_sha256": "b" * 64,
        "profile_content_hash": profile_hash,
    }


def _phase8_manifest(capacity: int = 1) -> dict[str, Any]:
    build = _build_identity("c" * 64)
    server = phase8_server_epoch_identity(
        server_epoch=20,
        server_process_id=120,
        session_fingerprint="phase8-session",
        max_active_cohorts=capacity,
    )
    profile = phase8_profile_generation_identity(
        profile_generation=7,
        profile_content_hash=build["profile_content_hash"],
    )
    projection = phase8_build_projection({"build_identity": build})
    manifest: dict[str, Any] = {
        "schema": "all_spec_phase8_evidence_identity_manifest_v2",
        "component_hashes": {
            "source_identity_sha256": canonical_sha256(
                {"git_commit": build["git_commit"], "source_tree_clean": True}
            ),
            "worldserver_binary_sha256": build["worldserver_binary_sha256"],
            "database_snapshot_sha256": build["database_snapshot_sha256"],
            "database_schema_sha256": build["database_schema_sha256"],
            "server_epoch_sha256": canonical_sha256(server),
            "profile_generation_sha256": canonical_sha256(profile),
            "build_projection_sha256": canonical_sha256(projection),
        },
        "build_identity": build,
        "runtime_identity": {**server, **profile},
        "database_summary": {},
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def _phase9_manifest(capacity: int = 1) -> dict[str, Any]:
    build = _build_identity("c" * 64)
    server = phase9_server_epoch_identity(
        server_epoch=20,
        server_process_id=120,
        session_fingerprint="phase9-session",
        max_active_cohorts=capacity,
    )
    profile = phase9_profile_generation_identity(
        profile_generation=7,
        profile_content_hash=build["profile_content_hash"],
    )
    projection = phase9_build_projection({"build_identity": build})
    artifacts = {
        "target_catalog_sha256": "1" * 64,
        "pair_policy_sha256": "2" * 64,
        "pairwise_matrix_sha256": "3" * 64,
        "route_manifest_sha256": "4" * 64,
    }
    manifest: dict[str, Any] = {
        "schema": "all_spec_phase9_evidence_identity_manifest_v2",
        "component_hashes": {
            "source_identity_sha256": canonical_sha256(
                {"git_commit": build["git_commit"], "source_tree_clean": True}
            ),
            "worldserver_binary_sha256": build["worldserver_binary_sha256"],
            "database_snapshot_sha256": build["database_snapshot_sha256"],
            "database_schema_sha256": build["database_schema_sha256"],
            "server_epoch_sha256": canonical_sha256(server),
            "profile_generation_sha256": canonical_sha256(profile),
            "build_projection_sha256": canonical_sha256(projection),
        },
        "artifact_hashes": artifacts,
        "build_identity": build,
        "runtime_identity": {**server, **profile},
        "database_summary": {},
        "route_summary": {},
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def _registry(capacity: Any = 1, *, active_count: Any = 0) -> dict[str, Any]:
    return {
        "action": "botauto_cohorts",
        "ok": True,
        "server_epoch": 20,
        "server_process_id": 120,
        "max_active_cohorts": capacity,
        "active_cohort_count": active_count,
        "cohorts": [{"cohort_id": "default", "active": False}],
    }


@pytest.mark.parametrize("capacity", [1, 2, 7])
def test_manifest_capacity_is_exact_and_matching_runtime_is_valid(capacity: int) -> None:
    phase8 = _phase8_manifest(capacity)
    phase9 = _phase9_manifest(capacity)

    assert phase8["runtime_identity"]["max_active_cohorts"] == capacity
    assert phase9["runtime_identity"]["max_active_cohorts"] == capacity
    assert validate_phase8_manifest(
        phase8, runtime_identity=phase8["runtime_identity"]
    )["runtime_identity"]["max_active_cohorts"] == capacity
    assert validate_phase9_manifest(
        phase9,
        runtime_identity=phase9["runtime_identity"],
        artifact_hashes=phase9["artifact_hashes"],
    )["runtime_identity"]["max_active_cohorts"] == capacity


@pytest.mark.parametrize(
    ("identity_factory", "validator", "runtime_key"),
    [
        (phase8_server_epoch_identity, validate_phase8_manifest, "phase8"),
        (phase9_server_epoch_identity, validate_phase9_manifest, "phase9"),
    ],
)
def test_capacity_drift_fails_runtime_matching(identity_factory, validator, runtime_key):
    manifest = _phase8_manifest() if runtime_key == "phase8" else _phase9_manifest()
    runtime = copy.deepcopy(manifest["runtime_identity"])
    runtime["max_active_cohorts"] = 2
    with pytest.raises(ValueError, match="live runtime does not match"):
        if runtime_key == "phase8":
            validator(manifest, runtime_identity=runtime)
        else:
            validator(
                manifest,
                runtime_identity=runtime,
                artifact_hashes=manifest["artifact_hashes"],
            )

    with pytest.raises(ValueError, match="positive integer"):
        identity_factory(
            server_epoch=1,
            server_process_id=2,
            session_fingerprint="session",
            max_active_cohorts=True,
        )


@pytest.mark.parametrize("value", [False, 0, -1, 1.0, "2", None])
def test_capacity_rejects_non_positive_or_non_integer_values(value: Any) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        require_positive_cohort_capacity(value)


def test_idle_registry_accepts_real_capacity_one_and_two() -> None:
    assert validate_idle_cohort_registry(_registry(1)) == 1
    assert validate_idle_cohort_registry(_registry(2)) == 2


@pytest.mark.parametrize(
    "registry",
    [
        {},
        {"action": "unknown", "ok": True},
        {**_registry(), "ok": False},
        {**_registry(), "max_active_cohorts": True},
        {**_registry(), "max_active_cohorts": 0},
        {**_registry(), "active_cohort_count": False},
        {**_registry(), "active_cohort_count": 1},
        {**_registry(), "cohorts": []},
        {**_registry(), "cohorts": [{"cohort_id": "foreign", "active": True}]},
        {**_registry(), "cohorts": [{"cohort_id": "malformed"}]},
    ],
)
def test_idle_registry_rejects_unknown_malformed_or_active_registry(
    registry: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        validate_idle_cohort_registry(registry)


def test_phase8_builder_checks_actual_idle_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace(
        metadata=lambda: {"session_fingerprint": "phase8-session"}
    )
    action = SimpleNamespace(status=SimpleNamespace(properties={"MainPID": "120"}))
    monkeypatch.setattr(phase8_builder, "ensure_healthy_matching_session", lambda _: action)

    def payload(**kwargs: Any) -> dict[str, Any]:
        if kwargs["action"] == "botauto_cohorts":
            return _registry(2)
        return {"ok": True, "snapshot_generation": 7, "snapshot_content_hash": "c" * 64}

    monkeypatch.setattr(phase8_builder, "_soap_payload", payload)
    _, registry, dump = phase8_builder._capture_live_runtime_identity(
        session=session,
        soap_url="http://soap.invalid",
        soap_user="user",
        soap_password="password",
        target={"class_id": 1, "runtime_join_key": "spec", "role": "dps"},
    )
    assert registry["max_active_cohorts"] == 2
    assert dump["ok"] is True

    monkeypatch.setattr(
        phase8_builder,
        "_soap_payload",
        lambda **kwargs: {
            **_registry(2),
            "cohorts": [{"cohort_id": "foreign", "active": True}],
        }
        if kwargs["action"] == "botauto_cohorts"
        else {"ok": True},
    )
    with pytest.raises(RuntimeError, match="idle native cohort registry"):
        phase8_builder._capture_live_runtime_identity(
            session=session,
            soap_url="http://soap.invalid",
            soap_user="user",
            soap_password="password",
            target={"class_id": 1, "runtime_join_key": "spec", "role": "dps"},
        )


def test_phase9_builder_binds_idle_registry_gate() -> None:
    source = phase9_builder.__file__
    assert source is not None
    source_text = open(source, encoding="utf-8").read()
    assert "validate_idle_cohort_registry(cohort_payload)" in source_text
    assert "require_positive_cohort_capacity(" in source_text
