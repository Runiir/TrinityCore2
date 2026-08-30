from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


SCHEMA = "cata_raid_recurrence_admission_v1"
CHECKPOINT_SEAL_SCHEMA = "cata_raid_checkpoint_seal_v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GAMEPLAY_CANARY_PURPOSE = "gameplay_canary"
FIXTURE_EXPANSION_PURPOSE = "fixture_expansion_replay"
ADMISSION_PURPOSES = {GAMEPLAY_CANARY_PURPOSE, FIXTURE_EXPANSION_PURPOSE}
FIXTURE_STATE_FIELDS = (
    "invalidated_fixture_ids",
    "failing_fixture_ids",
    "missing_fixture_ids",
    "pending_fixture_ids",
    "stale_fixture_ids",
)
CHAINWIELDER_CHECKPOINT_FIXTURE_ID = (
    "chainwielder_pre_admission_rejection_isolation_v1"
)
CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX = (
    "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint"
)
PROFILE_MANIFEST_RELATIVE_PATH = Path("dataset/bot_runtime_profiles/profiles.json")


def _fixture_expansion_contract(
    value: dict[str, Any], *, label: str
) -> list[dict[str, Any]]:
    targets = value.get("fixture_expansion_target_ids")
    requests = value.get("fixture_expansion_requests", [])
    pending = value.get("pending_fixture_ids", [])
    if not isinstance(targets, list) or not targets or any(
        not isinstance(fixture_id, str) or not fixture_id for fixture_id in targets
    ):
        raise RecurrenceAdmissionError(f"{label}_target_invalid")
    if len(targets) != len(set(targets)):
        raise RecurrenceAdmissionError(f"{label}_target_duplicate")
    if not isinstance(pending, list) or any(
        not isinstance(fixture_id, str) or not fixture_id for fixture_id in pending
    ):
        raise RecurrenceAdmissionError(f"{label}_pending_invalid")
    if not isinstance(requests, list):
        raise RecurrenceAdmissionError(f"{label}_request_invalid")
    request_ids: list[str] = []
    for request in requests:
        if not isinstance(request, dict):
            raise RecurrenceAdmissionError(f"{label}_request_invalid")
        fixture_id = request.get("fixture_id")
        from_revision = request.get("from_revision")
        to_revision = request.get("to_revision")
        if (
            not isinstance(fixture_id, str)
            or not fixture_id
            or not isinstance(from_revision, int)
            or isinstance(from_revision, bool)
            or from_revision <= 0
            or not isinstance(to_revision, int)
            or isinstance(to_revision, bool)
            or to_revision != from_revision + 1
            or not isinstance(request.get("causal_signature"), str)
            or not request["causal_signature"].strip()
            or not isinstance(request.get("required_production_boundary"), str)
            or not request["required_production_boundary"].strip()
        ):
            raise RecurrenceAdmissionError(f"{label}_request_invalid")
        request_ids.append(fixture_id)
    if len(request_ids) != len(set(request_ids)):
        raise RecurrenceAdmissionError(f"{label}_request_duplicate")
    if set(targets) != set(pending) | set(request_ids):
        raise RecurrenceAdmissionError(f"{label}_request_target_mismatch")
    return requests


class RecurrenceAdmissionError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_object_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_runtime_profile_suffix_manifest(
    *, source_manifest: dict[str, Any], runtime_profile: str,
    route_manifest_path: Path,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Create a one-profile overlay while changing only its route path."""

    rows = source_manifest.get("profiles")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("runtime_profile_source_profiles_invalid")
    selected = [row for row in rows if row.get("name") == runtime_profile]
    if len(selected) != 1:
        raise ValueError("runtime_profile_source_selection_missing_or_duplicate")
    source_profile = json.loads(json.dumps(selected[0]))
    route = source_profile.get("validation_route")
    if not isinstance(route, dict) or not isinstance(route.get("manifest_path"), str) \
            or not route["manifest_path"]:
        raise ValueError("runtime_profile_source_route_manifest_missing")
    source_route_path = route["manifest_path"]
    runtime_profile_payload = json.loads(json.dumps(source_profile))
    runtime_profile_payload["validation_route"]["manifest_path"] = str(
        route_manifest_path.resolve()
    )
    envelope = {key: json.loads(json.dumps(value))
                for key, value in source_manifest.items() if key != "profiles"}
    runtime_manifest = {**envelope, "profiles": [runtime_profile_payload]}
    return runtime_manifest, {
        "runtime_profile_id": runtime_profile,
        "source_validation_route_manifest_path": source_route_path,
        "runtime_validation_route_manifest_path": str(route_manifest_path.resolve()),
        "source_selected_profile_sha256": _canonical_object_sha256(source_profile),
        "runtime_selected_profile_sha256": _canonical_object_sha256(
            runtime_profile_payload
        ),
        "profile_manifest_envelope_sha256": _canonical_object_sha256(envelope),
    }


def _verified_runtime_profile_overlay(
    *, worktree: Path, profile_manifest: Path, route_manifest: Path,
    overlay: object, atomic_bundle_roots: tuple[Path, Path] | None = None,
) -> dict[str, str]:
    if not isinstance(overlay, dict):
        raise RecurrenceAdmissionError("runtime_profile_overlay_missing")
    runtime_profile = overlay.get("runtime_profile_id")
    if not isinstance(runtime_profile, str) or not runtime_profile:
        raise RecurrenceAdmissionError("runtime_profile_overlay_profile_invalid")
    source_path = worktree.resolve() / PROFILE_MANIFEST_RELATIVE_PATH
    try:
        source_bytes = source_path.read_bytes()
        committed = _git(
            worktree, "show", f"HEAD:{PROFILE_MANIFEST_RELATIVE_PATH.as_posix()}",
            binary=True,
        )
        source = json.loads(source_bytes.decode("utf-8"))
        runtime_bytes = profile_manifest.read_bytes()
        runtime = json.loads(runtime_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, subprocess.SubprocessError) \
            as error:
        raise RecurrenceAdmissionError("runtime_profile_overlay_asset_invalid") from error
    if source_bytes != committed or not isinstance(source, dict):
        raise RecurrenceAdmissionError("source_profile_manifest_identity_mismatch")
    if not isinstance(runtime, dict):
        raise RecurrenceAdmissionError("runtime_profile_manifest_invalid")
    recorded_route = _atomic_recorded_path(route_manifest, atomic_bundle_roots)
    try:
        expected_manifest, expected = build_runtime_profile_suffix_manifest(
            source_manifest=source, runtime_profile=runtime_profile,
            route_manifest_path=recorded_route,
        )
    except ValueError as error:
        raise RecurrenceAdmissionError(str(error)) from error
    expected.update({
        "source_profile_manifest_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "runtime_profile_manifest_sha256": hashlib.sha256(runtime_bytes).hexdigest(),
        "runtime_route_manifest_sha256": sha256_file(route_manifest),
    })
    if overlay != expected:
        raise RecurrenceAdmissionError("runtime_profile_overlay_identity_mismatch")
    if runtime != expected_manifest:
        raise RecurrenceAdmissionError("runtime_profile_overlay_semantic_mismatch")
    return expected


def _git(worktree: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(worktree), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout if binary else result.stdout.decode().strip()


def _load(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise RecurrenceAdmissionError(f"{label}_missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RecurrenceAdmissionError(f"{label}_invalid") from error
    if not isinstance(value, dict):
        raise RecurrenceAdmissionError(f"{label}_invalid")
    return value


def _config_bool(path: Path, key: str, default: bool = False) -> bool:
    value = default
    pattern = re.compile(
        rf"^\s*{re.escape(key)}\s*=\s*(0|1|false|true)\s*(?:#.*)?$",
        re.IGNORECASE,
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            value = match.group(1).lower() in {"1", "true"}
    return value


def _config_string(path: Path, key: str, default: str = "") -> str:
    value = default
    pattern = re.compile(
        rf'^\s*{re.escape(key)}\s*=\s*"([^"\r\n]*)"\s*(?:#.*)?$'
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            value = match.group(1)
    return value


def chainwielder_checkpoint_seal(
    *,
    worktree: Path,
    binary: Path,
    build_receipt: Path,
    decision: Path,
    profile_manifest: Path | None = None,
    runtime_profile_overlay: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Return the immutable seal that must exist before config admission.

    The runtime config is deliberately absent from this payload. Its final
    bytes contain the resulting seal and are independently hash-bound by the
    recurrence admission created afterward.
    """

    worktree = worktree.resolve()
    head = str(_git(worktree, "rev-parse", "HEAD"))
    tree = str(_git(worktree, "rev-parse", "HEAD^{tree}"))
    payload = {
        "schema": CHECKPOINT_SEAL_SCHEMA,
        "fixture_id": CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        "purpose": FIXTURE_EXPANSION_PURPOSE,
        "source_commit": head,
        "source_tree": tree,
        "binary_sha256": sha256_file(binary.resolve()),
        "build_receipt_sha256": sha256_file(build_receipt.resolve()),
        "decision_sha256": sha256_file(decision.resolve()),
    }
    if (profile_manifest is None) != (runtime_profile_overlay is None):
        raise RecurrenceAdmissionError("checkpoint_profile_authority_incomplete")
    if profile_manifest is not None and runtime_profile_overlay is not None:
        payload.update({
            "profile_manifest_sha256": sha256_file(profile_manifest.resolve()),
            "runtime_profile_overlay_sha256": _canonical_object_sha256(
                runtime_profile_overlay
            ),
        })
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return {**payload, "seal_sha256": hashlib.sha256(canonical).hexdigest()}


def _verify_chainwielder_checkpoint_seal(
    *,
    seal: object,
    worktree: Path,
    binary: Path,
    build_receipt: Path,
    decision: Path,
    runtime_config: Path,
    profile_manifest: Path,
    runtime_profile_overlay: dict[str, Any],
) -> dict[str, str]:
    if not isinstance(seal, dict):
        raise RecurrenceAdmissionError("checkpoint_seal_missing")
    expected = chainwielder_checkpoint_seal(
        worktree=worktree,
        binary=binary,
        build_receipt=build_receipt,
        decision=decision,
        profile_manifest=profile_manifest,
        runtime_profile_overlay=runtime_profile_overlay,
    )
    if seal != expected:
        raise RecurrenceAdmissionError("checkpoint_seal_identity_mismatch")
    prefix = CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX
    if not _config_bool(runtime_config, f"{prefix}.Enable"):
        raise RecurrenceAdmissionError("checkpoint_config_disabled")
    if _config_string(runtime_config, f"{prefix}.FixtureId") != (
        CHAINWIELDER_CHECKPOINT_FIXTURE_ID
    ):
        raise RecurrenceAdmissionError("checkpoint_config_fixture_mismatch")
    config_seal = _config_string(runtime_config, f"{prefix}.SealSha256")
    if config_seal != expected["seal_sha256"]:
        raise RecurrenceAdmissionError("checkpoint_config_seal_mismatch")
    if _config_string(runtime_config, f"{prefix}.SourceCommit") != (
        expected["source_commit"]
    ):
        raise RecurrenceAdmissionError("checkpoint_config_source_mismatch")
    return expected


def _verify_binding(
    admission: dict[str, Any], name: str, actual_path: Path | None = None,
    *, atomic_bundle_roots: tuple[Path, Path] | None = None,
) -> Path:
    binding = (admission.get("bindings") or {}).get(name)
    if not isinstance(binding, dict):
        raise RecurrenceAdmissionError(f"{name}_binding_missing")
    raw_path = binding.get("path")
    expected_hash = binding.get("sha256")
    if not isinstance(raw_path, str) or not SHA256_RE.fullmatch(str(expected_hash or "")):
        raise RecurrenceAdmissionError(f"{name}_binding_invalid")
    path = Path(raw_path).resolve()
    expected_path = _atomic_recorded_path(actual_path, atomic_bundle_roots) \
        if actual_path is not None else None
    if expected_path is not None and path != expected_path:
        raise RecurrenceAdmissionError(f"{name}_path_mismatch")
    checked_path = _atomic_materialized_path(path, atomic_bundle_roots)
    if not checked_path.is_file():
        raise RecurrenceAdmissionError(f"{name}_missing")
    if sha256_file(checked_path) != expected_hash:
        raise RecurrenceAdmissionError(f"{name}_hash_mismatch")
    return checked_path


def _validated_atomic_bundle_roots(
    roots: tuple[Path, Path] | None,
) -> tuple[Path, Path] | None:
    if roots is None:
        return None
    final_root, staging_root = (path.resolve() for path in roots)
    if (
        final_root == staging_root
        or final_root.parent != staging_root.parent
        or not staging_root.name.startswith(f".{final_root.name}.staging-")
    ):
        raise RecurrenceAdmissionError("atomic_bundle_roots_invalid")
    return final_root, staging_root


def _atomic_recorded_path(
    path: Path, roots: tuple[Path, Path] | None,
) -> Path:
    validated = _validated_atomic_bundle_roots(roots)
    resolved = path.resolve()
    if validated is None:
        return resolved
    final_root, staging_root = validated
    try:
        relative = resolved.relative_to(staging_root)
    except ValueError:
        return resolved
    if relative == Path("."):
        raise RecurrenceAdmissionError("atomic_bundle_binding_invalid")
    return final_root / relative


def _atomic_materialized_path(
    path: Path, roots: tuple[Path, Path] | None,
) -> Path:
    validated = _validated_atomic_bundle_roots(roots)
    resolved = path.resolve()
    if validated is None:
        return resolved
    final_root, staging_root = validated
    try:
        relative = resolved.relative_to(final_root)
    except ValueError:
        return resolved
    if relative == Path("."):
        raise RecurrenceAdmissionError("atomic_bundle_binding_invalid")
    return staging_root / relative


def create_recurrence_admission(
    *,
    output: Path,
    worktree: Path,
    binary: Path,
    build_receipt: Path,
    runtime_config: Path,
    route_manifest: Path,
    ledger: Path,
    decision: Path,
    suite_receipt: Path,
    profile_manifest: Path | None = None,
    runtime_profile_overlay: dict[str, Any] | None = None,
    purpose: str = GAMEPLAY_CANARY_PURPOSE,
    atomic_bundle_roots: tuple[Path, Path] | None = None,
) -> dict[str, Any]:
    if output.exists():
        raise RecurrenceAdmissionError("admission_output_exists")
    worktree = worktree.resolve()
    head = str(_git(worktree, "rev-parse", "HEAD"))
    tree = str(_git(worktree, "rev-parse", "HEAD^{tree}"))
    porcelain = _git(worktree, "status", "--porcelain=v1", "-z", binary=True)
    assert isinstance(porcelain, bytes)
    if porcelain:
        raise RecurrenceAdmissionError("source_worktree_dirty")
    decision_value = _load(decision.resolve(), "decision")
    if purpose not in ADMISSION_PURPOSES:
        raise RecurrenceAdmissionError("admission_purpose_invalid")
    fixture_expansion = purpose == FIXTURE_EXPANSION_PURPOSE
    if fixture_expansion:
        if decision_value.get("fixture_expansion_admitted") is not True:
            raise RecurrenceAdmissionError("fixture_expansion_not_admitted")
        if decision_value.get("canary_admitted") is True:
            raise RecurrenceAdmissionError("fixture_expansion_gameplay_gate_open")
        expansion_requests = _fixture_expansion_contract(
            decision_value, label="fixture_expansion"
        )
        checkpoint_targeted = CHAINWIELDER_CHECKPOINT_FIXTURE_ID in (
            decision_value.get("fixture_expansion_target_ids") or []
        )
    else:
        expansion_requests = []
        checkpoint_targeted = False
    suite = _load(suite_receipt.resolve(), "suite_receipt")
    if suite.get("source_identity") != head:
        raise RecurrenceAdmissionError("suite_receipt_source_stale")
    verifications = suite.get("verifications")
    if not isinstance(verifications, list) or not verifications:
        raise RecurrenceAdmissionError("suite_receipt_empty")
    fixture_revisions: dict[str, int] = {}
    for row in verifications:
        if not isinstance(row, dict) or row.get("passed") is not True:
            raise RecurrenceAdmissionError("suite_fixture_failed")
        fixture_id = row.get("fixture_id")
        revision = row.get("fixture_revision")
        if not isinstance(fixture_id, str) or not isinstance(revision, int):
            raise RecurrenceAdmissionError("suite_fixture_identity_invalid")
        fixture_revisions[fixture_id] = revision
    checkpoint_seal = None
    verified_overlay: dict[str, str] | None = None
    if checkpoint_targeted:
        if profile_manifest is None or runtime_profile_overlay is None:
            raise RecurrenceAdmissionError("checkpoint_profile_authority_missing")
        profile_manifest = profile_manifest.resolve()
        verified_overlay = _verified_runtime_profile_overlay(
            worktree=worktree, profile_manifest=profile_manifest,
            route_manifest=route_manifest.resolve(),
            overlay=runtime_profile_overlay,
            atomic_bundle_roots=atomic_bundle_roots,
        )
        recorded_profile = _atomic_recorded_path(
            profile_manifest, atomic_bundle_roots
        )
        recorded_route = _atomic_recorded_path(
            route_manifest.resolve(), atomic_bundle_roots
        )
        if _config_string(runtime_config, "BotWorld.ProfileManifest") != str(
            recorded_profile
        ):
            raise RecurrenceAdmissionError("profile_manifest_not_bound_by_config")
        if _config_string(
            runtime_config, "BotWorld.ValidationRoute.ManifestPath"
        ) != str(recorded_route):
            raise RecurrenceAdmissionError("route_manifest_not_bound_by_config")
        if _config_string(runtime_config, "BotWorld.RuntimeProfile") != (
            verified_overlay["runtime_profile_id"]
        ):
            raise RecurrenceAdmissionError("runtime_profile_not_bound_by_config")
        checkpoint_seal = _verify_chainwielder_checkpoint_seal(
            seal=chainwielder_checkpoint_seal(
                worktree=worktree,
                binary=binary,
                build_receipt=build_receipt,
                decision=decision,
                profile_manifest=profile_manifest,
                runtime_profile_overlay=verified_overlay,
            ),
            worktree=worktree,
            binary=binary,
            build_receipt=build_receipt,
            decision=decision,
            runtime_config=runtime_config,
            profile_manifest=profile_manifest,
            runtime_profile_overlay=verified_overlay,
        )
    elif profile_manifest is not None or runtime_profile_overlay is not None:
        raise RecurrenceAdmissionError("profile_authority_unexpected")
    admission = {
        "schema": SCHEMA,
        "purpose": purpose,
        "build_admitted": decision_value.get("build_admitted") is True,
        "canary_admitted": decision_value.get("canary_admitted") is True,
        "fixture_expansion_admitted": (
            decision_value.get("fixture_expansion_admitted") is True
        ),
        "fixture_expansion_target_ids": decision_value.get(
            "fixture_expansion_target_ids"
        ) or [],
        "fixture_expansion_requests": expansion_requests,
        "gameplay_mutations_allowed": False if fixture_expansion else None,
        "checkpoint_seal": checkpoint_seal,
        "runtime_profile_overlay": verified_overlay,
        **{key: decision_value.get(key) for key in FIXTURE_STATE_FIELDS},
        "source": {
            "commit": head,
            "tree": tree,
            "porcelain_sha256": hashlib.sha256(porcelain).hexdigest(),
        },
        "bindings": {
            name: {
                "path": str(
                    _atomic_recorded_path(path, atomic_bundle_roots)
                ),
                "sha256": sha256_file(path.resolve()),
            }
            for name, path in {
                "binary": binary,
                "build_receipt": build_receipt,
                "runtime_config": runtime_config,
                "route_manifest": route_manifest,
                "ledger": ledger,
                "decision": decision,
                "suite_receipt": suite_receipt,
                **({"profile_manifest": profile_manifest}
                   if profile_manifest is not None else {}),
            }.items()
        },
        "fixture_revisions": fixture_revisions,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(admission, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return admission


def verify_recurrence_admission(
    *,
    admission_path: Path,
    expected_sha256: str,
    worktree: Path,
    binary: Path,
    build_receipt: Path,
    runtime_config: Path,
    profile_manifest: Path | None = None,
    required_purpose: str = GAMEPLAY_CANARY_PURPOSE,
    atomic_bundle_roots: tuple[Path, Path] | None = None,
) -> dict[str, Any]:
    """Verify the immutable Magmaw recurrence gate before process startup."""

    if not SHA256_RE.fullmatch(expected_sha256):
        raise RecurrenceAdmissionError("admission_sha256_invalid")
    admission_path = admission_path.resolve()
    admission = _load(admission_path, "admission")
    if sha256_file(admission_path) != expected_sha256:
        raise RecurrenceAdmissionError("admission_hash_mismatch")
    if admission.get("schema") != SCHEMA:
        raise RecurrenceAdmissionError("admission_schema_invalid")
    if required_purpose not in ADMISSION_PURPOSES:
        raise RecurrenceAdmissionError("required_purpose_invalid")
    if admission.get("purpose", GAMEPLAY_CANARY_PURPOSE) != required_purpose:
        raise RecurrenceAdmissionError("admission_purpose_mismatch")
    fixture_expansion = required_purpose == FIXTURE_EXPANSION_PURPOSE
    if fixture_expansion:
        if admission.get("fixture_expansion_admitted") is not True:
            raise RecurrenceAdmissionError("fixture_expansion_not_admitted")
        if admission.get("canary_admitted") is True:
            raise RecurrenceAdmissionError("fixture_expansion_gameplay_gate_open")
        if admission.get("gameplay_mutations_allowed") is not False:
            raise RecurrenceAdmissionError("fixture_expansion_gameplay_mutation_forbidden")
        expansion_requests = _fixture_expansion_contract(
            admission, label="fixture_expansion"
        )
        checkpoint_targeted = CHAINWIELDER_CHECKPOINT_FIXTURE_ID in (
            admission.get("fixture_expansion_target_ids") or []
        )
    else:
        if admission.get("build_admitted") is not True:
            raise RecurrenceAdmissionError("build_not_admitted")
        if admission.get("canary_admitted") is not True:
            raise RecurrenceAdmissionError("canary_not_admitted")
        for key in FIXTURE_STATE_FIELDS:
            if admission.get(key) != []:
                raise RecurrenceAdmissionError(f"{key}_present")
        checkpoint_targeted = False

    worktree = worktree.resolve()
    head = str(_git(worktree, "rev-parse", "HEAD"))
    tree = str(_git(worktree, "rev-parse", "HEAD^{tree}"))
    porcelain = _git(worktree, "status", "--porcelain=v1", "-z", binary=True)
    assert isinstance(porcelain, bytes)
    if porcelain:
        raise RecurrenceAdmissionError("source_worktree_dirty")
    source = admission.get("source") or {}
    if source.get("commit") != head or source.get("tree") != tree:
        raise RecurrenceAdmissionError("source_identity_stale")
    if source.get("porcelain_sha256") != hashlib.sha256(porcelain).hexdigest():
        raise RecurrenceAdmissionError("source_porcelain_mismatch")

    binary_path = _verify_binding(
        admission, "binary", binary, atomic_bundle_roots=atomic_bundle_roots,
    )
    build_receipt_path = _verify_binding(
        admission, "build_receipt", build_receipt,
        atomic_bundle_roots=atomic_bundle_roots,
    )
    _verify_binding(
        admission, "runtime_config", runtime_config,
        atomic_bundle_roots=atomic_bundle_roots,
    )
    route_path = _verify_binding(
        admission, "route_manifest", atomic_bundle_roots=atomic_bundle_roots,
    )
    verified_overlay: dict[str, str] | None = None
    profile_path: Path | None = None
    if checkpoint_targeted:
        if profile_manifest is None:
            raise RecurrenceAdmissionError("checkpoint_profile_authority_missing")
        profile_path = _verify_binding(
            admission, "profile_manifest", profile_manifest,
            atomic_bundle_roots=atomic_bundle_roots,
        )
        verified_overlay = _verified_runtime_profile_overlay(
            worktree=worktree, profile_manifest=profile_path,
            route_manifest=route_path,
            overlay=admission.get("runtime_profile_overlay"),
            atomic_bundle_roots=atomic_bundle_roots,
        )
        recorded_profile = str(
            ((admission.get("bindings") or {}).get("profile_manifest") or {}).get(
                "path"
            ) or ""
        )
        if _config_string(runtime_config, "BotWorld.ProfileManifest") != recorded_profile:
            raise RecurrenceAdmissionError("profile_manifest_not_bound_by_config")
        recorded_route = str(
            ((admission.get("bindings") or {}).get("route_manifest") or {}).get(
                "path"
            ) or ""
        )
        if _config_string(
            runtime_config, "BotWorld.ValidationRoute.ManifestPath"
        ) != recorded_route:
            raise RecurrenceAdmissionError("route_manifest_not_bound_by_config")
        if _config_string(runtime_config, "BotWorld.RuntimeProfile") != (
            verified_overlay["runtime_profile_id"]
        ):
            raise RecurrenceAdmissionError("runtime_profile_not_bound_by_config")
    elif (admission.get("runtime_profile_overlay") is not None
          or (admission.get("bindings") or {}).get("profile_manifest") is not None):
        raise RecurrenceAdmissionError("profile_authority_unexpected")
    ledger_path = _verify_binding(
        admission, "ledger", atomic_bundle_roots=atomic_bundle_roots,
    )
    decision_path = _verify_binding(
        admission, "decision", atomic_bundle_roots=atomic_bundle_roots,
    )
    suite_path = _verify_binding(
        admission, "suite_receipt", atomic_bundle_roots=atomic_bundle_roots,
    )

    config_text = runtime_config.read_text(encoding="utf-8")
    recorded_route_path = str(
        ((admission.get("bindings") or {}).get("route_manifest") or {}).get("path")
        or ""
    )
    if recorded_route_path not in config_text:
        raise RecurrenceAdmissionError("route_manifest_not_bound_by_config")
    decision = _load(decision_path, "decision")
    if fixture_expansion:
        if decision.get("fixture_expansion_admitted") is not True:
            raise RecurrenceAdmissionError("decision_fixture_expansion_not_admitted")
        if decision.get("canary_admitted") is True:
            raise RecurrenceAdmissionError("decision_fixture_expansion_gameplay_gate_open")
        if admission.get("fixture_expansion_target_ids") != decision.get(
            "fixture_expansion_target_ids"
        ):
            raise RecurrenceAdmissionError("fixture_expansion_target_mismatch")
        if expansion_requests != decision.get("fixture_expansion_requests", []):
            raise RecurrenceAdmissionError("fixture_expansion_request_mismatch")
        if not _config_bool(
            runtime_config, "BotWorld.ValidationRoute.PrepullCheckpointEnable"
        ):
            raise RecurrenceAdmissionError("fixture_expansion_checkpoint_disabled")
        route = _load(route_path, "route_manifest")
        if route.get("scenario_id") != "blackwing_descent_10n_magmaw_diagnostic":
            raise RecurrenceAdmissionError("fixture_expansion_route_mismatch")
    elif (
        decision.get("build_admitted") is not True
        or decision.get("canary_admitted") is not True
    ):
        raise RecurrenceAdmissionError("decision_not_admitted")
    for key in FIXTURE_STATE_FIELDS:
        if admission.get(key) != decision.get(key):
            raise RecurrenceAdmissionError(f"decision_{key}_mismatch")
    checkpoint_seal = admission.get("checkpoint_seal")
    if checkpoint_targeted:
        assert profile_path is not None and verified_overlay is not None
        checkpoint_seal = _verify_chainwielder_checkpoint_seal(
            seal=checkpoint_seal,
            worktree=worktree,
            binary=binary_path,
            build_receipt=build_receipt_path,
            decision=decision_path,
            runtime_config=runtime_config,
            profile_manifest=profile_path,
            runtime_profile_overlay=verified_overlay,
        )
    elif checkpoint_seal is not None:
        raise RecurrenceAdmissionError("checkpoint_seal_unexpected")

    suite = _load(suite_path, "suite_receipt")
    if suite.get("schema") != "trinity_raid_regression_suite_receipt_v1":
        raise RecurrenceAdmissionError("suite_receipt_schema_invalid")
    if suite.get("source_identity") != head:
        raise RecurrenceAdmissionError("suite_receipt_source_stale")
    verifications = suite.get("verifications")
    if not isinstance(verifications, list) or not verifications:
        raise RecurrenceAdmissionError("suite_receipt_empty")
    actual_revisions: dict[str, int] = {}
    for row in verifications:
        if not isinstance(row, dict) or row.get("passed") is not True:
            raise RecurrenceAdmissionError("suite_fixture_failed")
        fixture_id = row.get("fixture_id")
        revision = row.get("fixture_revision")
        if not isinstance(fixture_id, str) or not isinstance(revision, int):
            raise RecurrenceAdmissionError("suite_fixture_identity_invalid")
        actual_revisions[fixture_id] = revision
    if admission.get("fixture_revisions") != actual_revisions:
        raise RecurrenceAdmissionError("fixture_revision_map_mismatch")
    if fixture_expansion:
        for request in expansion_requests:
            if actual_revisions.get(request["fixture_id"]) != request["from_revision"]:
                raise RecurrenceAdmissionError(
                    "fixture_expansion_from_revision_mismatch"
                )

    # Loading the ledger is deliberate: its hash is already checked above, and
    # invalid JSON must not be accepted merely because a stale digest matches.
    _load(ledger_path, "ledger")
    build = _load(build_receipt_path, "build_receipt")
    if (
        build.get("classification") != "success"
        or build.get("exit_code") != 0
        or build.get("commit") != head
    ):
        raise RecurrenceAdmissionError("build_receipt_not_admitted")
    binary_hash = sha256_file(binary_path)
    artifacts = build.get("output_artifacts")
    if not any(
        isinstance(row, dict)
        and row.get("kind") == "worldserver_elf"
        and Path(str(row.get("path") or "")).resolve() == binary_path
        and row.get("sha256") == binary_hash
        and row.get("produced_by_ticket") is True
        for row in (artifacts if isinstance(artifacts, list) else [])
    ):
        raise RecurrenceAdmissionError("build_receipt_binary_identity_missing")
    return {
        "valid": True,
        "admission_sha256": expected_sha256,
        "source_commit": head,
        "source_tree": tree,
        "fixture_revisions": actual_revisions,
        "purpose": required_purpose,
        "fixture_expansion_target_ids": admission.get(
            "fixture_expansion_target_ids"
        ) or [],
        "fixture_expansion_requests": admission.get(
            "fixture_expansion_requests"
        ) or [],
        "checkpoint_seal_sha256": (
            checkpoint_seal["seal_sha256"]
            if isinstance(checkpoint_seal, dict) else None
        ),
        "bindings": {
            "route_manifest": (admission.get("bindings") or {})["route_manifest"],
            **({"profile_manifest": (admission.get("bindings") or {})[
                "profile_manifest"
            ]} if profile_path is not None else {}),
        },
        "runtime_profile_overlay": verified_overlay,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seal or verify a Magmaw recurrence admission.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    verify = subparsers.add_parser("verify")
    for command in (create, verify):
        command.add_argument("--worktree", type=Path, required=True)
        command.add_argument("--binary", type=Path, required=True)
        command.add_argument("--build-receipt", type=Path, required=True)
        command.add_argument("--runtime-config", type=Path, required=True)
    create.add_argument("--route-manifest", type=Path, required=True)
    create.add_argument("--ledger", type=Path, required=True)
    create.add_argument("--decision", type=Path, required=True)
    create.add_argument("--suite-receipt", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument(
        "--purpose", choices=sorted(ADMISSION_PURPOSES),
        default=GAMEPLAY_CANARY_PURPOSE,
    )
    verify.add_argument("--admission", type=Path, required=True)
    verify.add_argument("--sha256", required=True)
    verify.add_argument(
        "--purpose", choices=sorted(ADMISSION_PURPOSES),
        default=GAMEPLAY_CANARY_PURPOSE,
    )
    seal = subparsers.add_parser("checkpoint-seal")
    seal.add_argument("--worktree", type=Path, required=True)
    seal.add_argument("--binary", type=Path, required=True)
    seal.add_argument("--build-receipt", type=Path, required=True)
    seal.add_argument("--decision", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            result = create_recurrence_admission(
                output=args.output,
                worktree=args.worktree,
                binary=args.binary,
                build_receipt=args.build_receipt,
                runtime_config=args.runtime_config,
                route_manifest=args.route_manifest,
                ledger=args.ledger,
                decision=args.decision,
                suite_receipt=args.suite_receipt,
                purpose=args.purpose,
            )
            result = {
                "created": True,
                "path": str(args.output.resolve()),
                "sha256": sha256_file(args.output.resolve()),
                "source": result["source"],
            }
        elif args.command == "verify":
            result = verify_recurrence_admission(
                admission_path=args.admission,
                expected_sha256=args.sha256,
                worktree=args.worktree,
                binary=args.binary,
                build_receipt=args.build_receipt,
                runtime_config=args.runtime_config,
                required_purpose=args.purpose,
            )
        else:
            result = chainwielder_checkpoint_seal(
                worktree=args.worktree,
                binary=args.binary,
                build_receipt=args.build_receipt,
                decision=args.decision,
            )
    except RecurrenceAdmissionError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
