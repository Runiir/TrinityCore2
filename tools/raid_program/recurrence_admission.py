from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from tools.raid_program.build_control_compatibility import (
    compatibility_projection,
    verify_build_control_compatibility,
)

from tools.raid_program.recurrence_checkpoint_seals import (
    ADMISSION_PURPOSES,
    CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX,
    CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
    CHECKPOINT_SEAL_SCHEMA,
    FIXTURE_EXPANSION_PURPOSE,
    GAMEPLAY_CANARY_PURPOSE,
    MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID,
    MAGMAW_TRANSFER_CHECKPOINT_AUTHORITY,
    MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
    MAGMAW_TRANSFER_CHECKPOINT_CONFIG_PREFIX,
    MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
    MAGMAW_TRANSFER_CHECKPOINT_PROBE,
    NATIVE_PATH_CHECKPOINT_CONFIG_PREFIX,
    NATIVE_PATH_CHECKPOINT_FIXTURE_ID,
    NATIVE_PATH_CHECKPOINT_REQUIRED_PENDING_FIXTURE_IDS,
    NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS,
    PROFILE_COMBAT_RANGE_CHECKPOINT_AUTHORITY,
    PROFILE_COMBAT_RANGE_CHECKPOINT_CONFIG_PREFIX,
    PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
    RecurrenceAdmissionError,
    SHA256_RE,
    build_case_checkpoint_seal,
    build_chainwielder_checkpoint_seal,
    build_profile_combat_range_checkpoint_seal,
    canonical_object_sha256 as _canonical_object_sha256,
    config_bool as _config_bool,
    config_string as _config_string,
    fixture_expansion_contract as _fixture_expansion_contract,
    git_value as _git,
    load_object as _load,
    magmaw_transfer_checkpoint_contract as _magmaw_transfer_checkpoint_contract,
    magmaw_transfer_checkpoint_requested as _magmaw_transfer_checkpoint_requested,
    native_path_checkpoint_request_contract as _native_path_checkpoint_request_contract,
    native_path_checkpoint_requested as _native_path_checkpoint_requested,
    profile_combat_range_checkpoint_contract as _profile_combat_range_checkpoint_contract,
    profile_combat_range_checkpoint_requested as _profile_combat_range_checkpoint_requested,
    sha256_file,
    verify_case_checkpoint_config,
)

SCHEMA = "cata_raid_recurrence_admission_v1"
FIXTURE_STATE_FIELDS = (
    "invalidated_fixture_ids",
    "failing_fixture_ids",
    "missing_fixture_ids",
    "pending_fixture_ids",
    "stale_fixture_ids",
)
QUARANTINE_STATE_FIELDS = (
    "quarantined_fixture_ids",
    "blocking_invalidated_fixture_ids",
)
PROFILE_MANIFEST_RELATIVE_PATH = Path("dataset/bot_runtime_profiles/profiles.json")
CHECKPOINT_FIXTURE_IDS = {
    CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
    MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
    NATIVE_PATH_CHECKPOINT_FIXTURE_ID,
    PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
}


def _checkpoint_fixture_selection(
    value: dict[str, Any], explicit_fixture_id: str | None, *, label: str,
) -> str | None:
    """Resolve one checkpoint dialect without using target ordering as priority."""

    candidates: list[str] = []
    targets = value.get("fixture_expansion_target_ids")
    if isinstance(targets, list):
        if CHAINWIELDER_CHECKPOINT_FIXTURE_ID in targets:
            candidates.append(CHAINWIELDER_CHECKPOINT_FIXTURE_ID)
        if _magmaw_transfer_checkpoint_requested(value):
            candidates.append(MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID)
        if _native_path_checkpoint_requested(value):
            candidates.append(NATIVE_PATH_CHECKPOINT_FIXTURE_ID)
        if _profile_combat_range_checkpoint_requested(value):
            candidates.append(PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID)
    if explicit_fixture_id is not None and (
        not isinstance(explicit_fixture_id, str)
        or explicit_fixture_id not in CHECKPOINT_FIXTURE_IDS
    ):
        raise RecurrenceAdmissionError(f"{label}_checkpoint_fixture_invalid")
    if explicit_fixture_id is None:
        if len(candidates) > 1:
            raise RecurrenceAdmissionError(
                f"{label}_checkpoint_fixture_selection_required"
            )
        selected = candidates[0] if candidates else None
    else:
        auxiliary_chainwielder = (
            explicit_fixture_id == CHAINWIELDER_CHECKPOINT_FIXTURE_ID
            and not candidates
        )
        if explicit_fixture_id not in candidates and not auxiliary_chainwielder:
            raise RecurrenceAdmissionError(
                f"{label}_checkpoint_fixture_ineligible"
            )
        selected = explicit_fixture_id
    if selected == MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID:
        _magmaw_transfer_checkpoint_contract(
            value, label="magmaw_transfer_checkpoint"
        )
    elif selected == NATIVE_PATH_CHECKPOINT_FIXTURE_ID:
        _native_path_checkpoint_request_contract(
            value, label="native_path_checkpoint"
        )
    elif selected == PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID:
        _profile_combat_range_checkpoint_contract(
            value, label="profile_combat_range_checkpoint"
        )
    return selected


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
    overlay: object, expected_runtime_profile_id: str,
    atomic_bundle_roots: tuple[Path, Path] | None = None,
) -> dict[str, str]:
    if not expected_runtime_profile_id:
        raise RecurrenceAdmissionError("expected_runtime_profile_invalid")
    if not isinstance(overlay, dict):
        raise RecurrenceAdmissionError("runtime_profile_overlay_missing")
    runtime_profile = overlay.get("runtime_profile_id")
    if runtime_profile != expected_runtime_profile_id:
        raise RecurrenceAdmissionError("expected_runtime_profile_mismatch")
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


def chainwielder_checkpoint_seal(
    *,
    worktree: Path,
    binary: Path,
    build_receipt: Path,
    decision: Path,
    profile_manifest: Path | None = None,
    runtime_profile_overlay: dict[str, Any] | None = None,
    expected_runtime_profile_id: str | None = None,
) -> dict[str, str]:
    return build_chainwielder_checkpoint_seal(
        worktree=worktree, binary=binary, build_receipt=build_receipt,
        decision=decision, profile_manifest=profile_manifest,
        runtime_profile_overlay=runtime_profile_overlay,
        expected_runtime_profile_id=expected_runtime_profile_id,
        git_fn=_git,
    )


def native_path_checkpoint_seal(
    *, worktree: Path, binary: Path, build_receipt: Path, decision: Path,
    case_id: str, profile_manifest: Path,
    runtime_profile_overlay: dict[str, Any],
    expected_runtime_profile_id: str,
) -> dict[str, str]:
    decision_value = _load(decision.resolve(), "decision")
    requests = _native_path_checkpoint_request_contract(
        decision_value, label="native_path_checkpoint"
    )
    return build_case_checkpoint_seal(
        fixture_id=NATIVE_PATH_CHECKPOINT_FIXTURE_ID, case_id=case_id,
        label="native_path_checkpoint", worktree=worktree, binary=binary,
        build_receipt=build_receipt, decision=decision,
        profile_manifest=profile_manifest,
        runtime_profile_overlay=runtime_profile_overlay,
        expected_runtime_profile_id=expected_runtime_profile_id,
        requests=requests, git_fn=_git,
    )


def profile_combat_range_checkpoint_seal(
    *, worktree: Path, binary: Path, build_receipt: Path, decision: Path,
    case_id: str, actor_guid: int, target_guid: int, profile_manifest: Path,
    runtime_profile_overlay: dict[str, Any],
    expected_runtime_profile_id: str,
) -> dict[str, str]:
    decision_value = _load(decision.resolve(), "decision")
    requests = _profile_combat_range_checkpoint_contract(
        decision_value, label="profile_combat_range_checkpoint"
    )
    if requests:
        raise RecurrenceAdmissionError(
            "profile_combat_range_checkpoint_request_contract_mismatch"
        )
    seal = build_profile_combat_range_checkpoint_seal(
        worktree=worktree, binary=binary, build_receipt=build_receipt,
        decision=decision, case_id=case_id, actor_guid=actor_guid,
        target_guid=target_guid, profile_manifest=profile_manifest,
        runtime_profile_overlay=runtime_profile_overlay,
        expected_runtime_profile_id=expected_runtime_profile_id,
        git_fn=_git,
    )
    return seal


def _config_number(path: Path, key: str) -> int:
    pattern = re.compile(
        rf'^\s*{re.escape(key)}\s*=\s*"?(\d+)"?\s*(?:#.*)?$'
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            return int(match.group(1))
    return 0


def _verify_profile_combat_range_checkpoint_seal(
    *, seal: object, worktree: Path, binary: Path, build_receipt: Path,
    decision: Path, runtime_config: Path, profile_manifest: Path,
    runtime_profile_overlay: dict[str, Any],
    expected_runtime_profile_id: str,
) -> dict[str, str]:
    if not isinstance(seal, dict) or not isinstance(seal.get("case_id"), str):
        raise RecurrenceAdmissionError(
            "profile_combat_range_checkpoint_seal_missing"
        )
    actor_guid = seal.get("actor_guid")
    target_guid = seal.get("target_guid")
    if (
        not isinstance(actor_guid, int) or isinstance(actor_guid, bool)
        or actor_guid <= 0
        or not isinstance(target_guid, int) or isinstance(target_guid, bool)
        or target_guid <= 0
    ):
        raise RecurrenceAdmissionError(
            "profile_combat_range_checkpoint_identity_invalid"
        )
    expected = profile_combat_range_checkpoint_seal(
        worktree=worktree, binary=binary, build_receipt=build_receipt,
        decision=decision, case_id=seal["case_id"], actor_guid=actor_guid,
        target_guid=target_guid, profile_manifest=profile_manifest,
        runtime_profile_overlay=runtime_profile_overlay,
        expected_runtime_profile_id=expected_runtime_profile_id,
    )
    verify_case_checkpoint_config(
        seal=seal, expected=expected, runtime_config=runtime_config,
        prefix=PROFILE_COMBAT_RANGE_CHECKPOINT_CONFIG_PREFIX,
        label="profile_combat_range_checkpoint",
        fixture_id=PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
    )
    if (
        _config_number(
            runtime_config,
            f"{PROFILE_COMBAT_RANGE_CHECKPOINT_CONFIG_PREFIX}.ActorGuid",
        ) != actor_guid
        or _config_number(
            runtime_config,
            f"{PROFILE_COMBAT_RANGE_CHECKPOINT_CONFIG_PREFIX}.TargetGuid",
        ) != target_guid
        or expected.get("authority") != PROFILE_COMBAT_RANGE_CHECKPOINT_AUTHORITY
    ):
        raise RecurrenceAdmissionError(
            "profile_combat_range_checkpoint_config_identity_mismatch"
        )
    return expected


def _verify_native_path_checkpoint_seal(
    *, seal: object, worktree: Path, binary: Path, build_receipt: Path,
    decision: Path, runtime_config: Path, profile_manifest: Path,
    runtime_profile_overlay: dict[str, Any],
    expected_runtime_profile_id: str,
) -> dict[str, str]:
    if not isinstance(seal, dict) or not isinstance(seal.get("case_id"), str):
        raise RecurrenceAdmissionError("native_path_checkpoint_seal_missing")
    expected = native_path_checkpoint_seal(
        worktree=worktree, binary=binary, build_receipt=build_receipt,
        decision=decision, case_id=seal["case_id"],
        profile_manifest=profile_manifest,
        runtime_profile_overlay=runtime_profile_overlay,
        expected_runtime_profile_id=expected_runtime_profile_id,
    )
    return verify_case_checkpoint_config(
        seal=seal, expected=expected, runtime_config=runtime_config,
        prefix=NATIVE_PATH_CHECKPOINT_CONFIG_PREFIX,
        label="native_path_checkpoint",
        fixture_id=NATIVE_PATH_CHECKPOINT_FIXTURE_ID,
    )


def magmaw_transfer_checkpoint_seal(
    *, worktree: Path, binary: Path, build_receipt: Path, decision: Path,
    case_id: str, profile_manifest: Path,
    runtime_profile_overlay: dict[str, Any],
    expected_runtime_profile_id: str,
) -> dict[str, str]:
    """Seal the one compiled map-bound authority-off transfer-lane case."""

    decision_value = _load(decision.resolve(), "decision")
    requests = _magmaw_transfer_checkpoint_contract(
        decision_value, label="magmaw_transfer_checkpoint"
    )
    if case_id != MAGMAW_TRANSFER_CHECKPOINT_CASE_ID:
        raise RecurrenceAdmissionError("magmaw_transfer_checkpoint_case_invalid")
    return build_case_checkpoint_seal(
        fixture_id=MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID, case_id=case_id,
        label="magmaw_transfer_checkpoint", worktree=worktree,
        binary=binary, build_receipt=build_receipt, decision=decision,
        profile_manifest=profile_manifest,
        runtime_profile_overlay=runtime_profile_overlay,
        expected_runtime_profile_id=expected_runtime_profile_id,
        requests=requests, git_fn=_git,
        probe_receipt=worktree.resolve() / MAGMAW_TRANSFER_CHECKPOINT_PROBE,
    )


def _verify_magmaw_transfer_checkpoint_seal(
    *, seal: object, worktree: Path, binary: Path, build_receipt: Path,
    decision: Path, runtime_config: Path, profile_manifest: Path,
    runtime_profile_overlay: dict[str, Any],
    expected_runtime_profile_id: str,
) -> dict[str, str]:
    if not isinstance(seal, dict) or not isinstance(seal.get("case_id"), str):
        raise RecurrenceAdmissionError("magmaw_transfer_checkpoint_seal_missing")
    expected = magmaw_transfer_checkpoint_seal(
        worktree=worktree, binary=binary, build_receipt=build_receipt,
        decision=decision, case_id=seal["case_id"],
        profile_manifest=profile_manifest,
        runtime_profile_overlay=runtime_profile_overlay,
        expected_runtime_profile_id=expected_runtime_profile_id,
    )
    return verify_case_checkpoint_config(
        seal=seal, expected=expected, runtime_config=runtime_config,
        prefix=MAGMAW_TRANSFER_CHECKPOINT_CONFIG_PREFIX,
        label="magmaw_transfer_checkpoint",
        fixture_id=MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
        require_authority_off=True,
    )


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
    expected_runtime_profile_id: str,
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
        expected_runtime_profile_id=expected_runtime_profile_id,
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
    expected_runtime_profile_id: str | None = None,
    checkpoint_fixture_id: str | None = None,
    purpose: str = GAMEPLAY_CANARY_PURPOSE,
    atomic_bundle_roots: tuple[Path, Path] | None = None,
    build_control_authority: Path | None = None,
    build_control_authority_sha256: str | None = None,
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
    build = _load(build_receipt.resolve(), "build_receipt")
    source_compatibility = verify_build_control_compatibility(
        worktree=worktree, receipt=build,
        authority_path=build_control_authority,
        authority_sha256=build_control_authority_sha256,
    )
    if not source_compatibility["valid"]:
        raise RecurrenceAdmissionError(
            "build_source_incompatible:" + source_compatibility["rejections"][0]
        )
    decision_value = _load(decision.resolve(), "decision")
    if purpose not in ADMISSION_PURPOSES:
        raise RecurrenceAdmissionError("admission_purpose_invalid")
    fixture_expansion = purpose == FIXTURE_EXPANSION_PURPOSE
    profile_authority_supplied = any(
        value is not None for value in (
            profile_manifest, runtime_profile_overlay,
            expected_runtime_profile_id,
        )
    )
    if fixture_expansion:
        if decision_value.get("fixture_expansion_admitted") is not True:
            raise RecurrenceAdmissionError("fixture_expansion_not_admitted")
        if decision_value.get("canary_admitted") is True:
            raise RecurrenceAdmissionError("fixture_expansion_gameplay_gate_open")
        expansion_requests = _fixture_expansion_contract(
            decision_value, label="fixture_expansion"
        )
        selected_checkpoint_fixture_id = _checkpoint_fixture_selection(
            decision_value, checkpoint_fixture_id, label="fixture_expansion"
        )
        if selected_checkpoint_fixture_id is None and profile_authority_supplied:
            # Preserve the established auxiliary Chainwielder seal for an
            # otherwise checkpoint-free fixture replay.
            selected_checkpoint_fixture_id = CHAINWIELDER_CHECKPOINT_FIXTURE_ID
        checkpoint_targeted = selected_checkpoint_fixture_id is not None
        chainwielder_checkpoint_targeted = selected_checkpoint_fixture_id == (
            CHAINWIELDER_CHECKPOINT_FIXTURE_ID
        )
        magmaw_transfer_checkpoint_targeted = selected_checkpoint_fixture_id == (
            MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID
        )
        native_path_checkpoint_targeted = selected_checkpoint_fixture_id == (
            NATIVE_PATH_CHECKPOINT_FIXTURE_ID
        )
        profile_combat_range_checkpoint_targeted = (
            selected_checkpoint_fixture_id
            == PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID
        )
    else:
        if checkpoint_fixture_id is not None:
            raise RecurrenceAdmissionError("checkpoint_fixture_unexpected")
        expansion_requests = []
        selected_checkpoint_fixture_id = None
        checkpoint_targeted = False
        chainwielder_checkpoint_targeted = False
        magmaw_transfer_checkpoint_targeted = False
        native_path_checkpoint_targeted = False
        profile_combat_range_checkpoint_targeted = False
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
    if checkpoint_targeted or profile_authority_supplied:
        if profile_manifest is None or runtime_profile_overlay is None \
                or expected_runtime_profile_id is None:
            raise RecurrenceAdmissionError("checkpoint_profile_authority_missing")
        profile_manifest = profile_manifest.resolve()
        verified_overlay = _verified_runtime_profile_overlay(
            worktree=worktree, profile_manifest=profile_manifest,
            route_manifest=route_manifest.resolve(),
            overlay=runtime_profile_overlay,
            expected_runtime_profile_id=expected_runtime_profile_id,
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
        if magmaw_transfer_checkpoint_targeted:
            case_id = _config_string(
                runtime_config,
                f"{MAGMAW_TRANSFER_CHECKPOINT_CONFIG_PREFIX}.CaseId",
            )
            checkpoint_seal = _verify_magmaw_transfer_checkpoint_seal(
                seal=magmaw_transfer_checkpoint_seal(
                    worktree=worktree, binary=binary,
                    build_receipt=build_receipt, decision=decision,
                    case_id=case_id, profile_manifest=profile_manifest,
                    runtime_profile_overlay=verified_overlay,
                    expected_runtime_profile_id=expected_runtime_profile_id,
                ),
                worktree=worktree, binary=binary,
                build_receipt=build_receipt, decision=decision,
                runtime_config=runtime_config,
                profile_manifest=profile_manifest,
                runtime_profile_overlay=verified_overlay,
                expected_runtime_profile_id=expected_runtime_profile_id,
            )
        elif native_path_checkpoint_targeted:
            case_id = _config_string(
                runtime_config,
                f"{NATIVE_PATH_CHECKPOINT_CONFIG_PREFIX}.CaseId",
            )
            checkpoint_seal = _verify_native_path_checkpoint_seal(
                seal=native_path_checkpoint_seal(
                    worktree=worktree, binary=binary,
                    build_receipt=build_receipt, decision=decision,
                    case_id=case_id, profile_manifest=profile_manifest,
                    runtime_profile_overlay=verified_overlay,
                    expected_runtime_profile_id=expected_runtime_profile_id,
                ),
                worktree=worktree, binary=binary,
                build_receipt=build_receipt, decision=decision,
                runtime_config=runtime_config,
                profile_manifest=profile_manifest,
                runtime_profile_overlay=verified_overlay,
                expected_runtime_profile_id=expected_runtime_profile_id,
            )
        elif profile_combat_range_checkpoint_targeted:
            case_id = _config_string(
                runtime_config,
                f"{PROFILE_COMBAT_RANGE_CHECKPOINT_CONFIG_PREFIX}.CaseId",
            )
            actor_guid = _config_number(
                runtime_config,
                f"{PROFILE_COMBAT_RANGE_CHECKPOINT_CONFIG_PREFIX}.ActorGuid",
            )
            target_guid = _config_number(
                runtime_config,
                f"{PROFILE_COMBAT_RANGE_CHECKPOINT_CONFIG_PREFIX}.TargetGuid",
            )
            checkpoint_seal = _verify_profile_combat_range_checkpoint_seal(
                seal=profile_combat_range_checkpoint_seal(
                    worktree=worktree, binary=binary,
                    build_receipt=build_receipt, decision=decision,
                    case_id=case_id, actor_guid=actor_guid,
                    target_guid=target_guid, profile_manifest=profile_manifest,
                    runtime_profile_overlay=verified_overlay,
                    expected_runtime_profile_id=expected_runtime_profile_id,
                ),
                worktree=worktree, binary=binary,
                build_receipt=build_receipt, decision=decision,
                runtime_config=runtime_config,
                profile_manifest=profile_manifest,
                runtime_profile_overlay=verified_overlay,
                expected_runtime_profile_id=expected_runtime_profile_id,
            )
        else:
            checkpoint_seal = _verify_chainwielder_checkpoint_seal(
                seal=chainwielder_checkpoint_seal(
                    worktree=worktree,
                    binary=binary,
                    build_receipt=build_receipt,
                    decision=decision,
                    profile_manifest=profile_manifest,
                    runtime_profile_overlay=verified_overlay,
                    expected_runtime_profile_id=expected_runtime_profile_id,
                ),
                worktree=worktree,
                binary=binary,
                build_receipt=build_receipt,
                decision=decision,
                runtime_config=runtime_config,
                profile_manifest=profile_manifest,
                runtime_profile_overlay=verified_overlay,
                expected_runtime_profile_id=expected_runtime_profile_id,
            )
        if checkpoint_seal.get("fixture_id") != selected_checkpoint_fixture_id:
            raise RecurrenceAdmissionError("checkpoint_seal_identity_mismatch")
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
        "checkpoint_fixture_id": selected_checkpoint_fixture_id,
        "runtime_profile_overlay": verified_overlay,
        "expected_runtime_profile_id": expected_runtime_profile_id,
        **{key: decision_value.get(key) for key in FIXTURE_STATE_FIELDS},
        **{
            key: decision_value.get(key) or []
            for key in QUARANTINE_STATE_FIELDS
        },
        "source": {
            "commit": head,
            "tree": tree,
            "porcelain_sha256": hashlib.sha256(porcelain).hexdigest(),
        },
        "build_control_compatibility": compatibility_projection(
            source_compatibility
        ),
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
                **({"build_control_authority": build_control_authority}
                   if build_control_authority is not None else {}),
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
    expected_runtime_profile_id: str | None = None,
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
    profile_authority_recorded = (
        admission.get("runtime_profile_overlay") is not None
        or (admission.get("bindings") or {}).get("profile_manifest") is not None
        or admission.get("expected_runtime_profile_id") is not None
    )
    authority_projection = (
        (admission.get("build_control_compatibility") or {}).get(
            "layered_authority"
        )
    )
    authority_binding_recorded = (
        (admission.get("bindings") or {}).get("build_control_authority")
    )
    if (authority_projection is None) != (authority_binding_recorded is None):
        raise RecurrenceAdmissionError("build_control_authority_binding_mismatch")
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
        selected_checkpoint_fixture_id = _checkpoint_fixture_selection(
            admission, admission.get("checkpoint_fixture_id"),
            label="fixture_expansion",
        )
        if selected_checkpoint_fixture_id is None and profile_authority_recorded:
            selected_checkpoint_fixture_id = CHAINWIELDER_CHECKPOINT_FIXTURE_ID
        checkpoint_targeted = selected_checkpoint_fixture_id is not None
        chainwielder_checkpoint_targeted = selected_checkpoint_fixture_id == (
            CHAINWIELDER_CHECKPOINT_FIXTURE_ID
        )
        magmaw_transfer_checkpoint_targeted = selected_checkpoint_fixture_id == (
            MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID
        )
        native_path_checkpoint_targeted = selected_checkpoint_fixture_id == (
            NATIVE_PATH_CHECKPOINT_FIXTURE_ID
        )
        profile_combat_range_checkpoint_targeted = (
            selected_checkpoint_fixture_id
            == PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID
        )
    else:
        if admission.get("build_admitted") is not True:
            raise RecurrenceAdmissionError("build_not_admitted")
        if admission.get("canary_admitted") is not True:
            raise RecurrenceAdmissionError("canary_not_admitted")
        quarantined_rows = admission.get("quarantined_fixture_ids", [])
        if (
            not isinstance(quarantined_rows, list)
            or any(
                not isinstance(fixture_id, str) or not fixture_id
                for fixture_id in quarantined_rows
            )
            or len(quarantined_rows) != len(set(quarantined_rows))
        ):
            raise RecurrenceAdmissionError("quarantined_fixture_ids_invalid")
        quarantined = set(quarantined_rows)
        for key in FIXTURE_STATE_FIELDS:
            rows = admission.get(key)
            if (
                not isinstance(rows, list)
                or any(
                    not isinstance(fixture_id, str) or not fixture_id
                    for fixture_id in rows
                )
                or len(rows) != len(set(rows))
            ):
                raise RecurrenceAdmissionError(f"{key}_invalid")
            if set(rows) - quarantined:
                raise RecurrenceAdmissionError(f"{key}_present")
        expected_blocking_invalidated = sorted(
            set(admission.get("invalidated_fixture_ids") or []) - quarantined
        )
        if admission.get(
            "blocking_invalidated_fixture_ids", expected_blocking_invalidated
        ) != expected_blocking_invalidated:
            raise RecurrenceAdmissionError(
                "blocking_invalidated_fixture_ids_mismatch"
            )
        checkpoint_targeted = False
        selected_checkpoint_fixture_id = None
        chainwielder_checkpoint_targeted = False
        magmaw_transfer_checkpoint_targeted = False
        native_path_checkpoint_targeted = False
        profile_combat_range_checkpoint_targeted = False

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
    if checkpoint_targeted or profile_authority_recorded:
        if profile_manifest is None or expected_runtime_profile_id is None:
            raise RecurrenceAdmissionError("checkpoint_profile_authority_missing")
        if admission.get("expected_runtime_profile_id") != expected_runtime_profile_id:
            raise RecurrenceAdmissionError("expected_runtime_profile_mismatch")
        profile_path = _verify_binding(
            admission, "profile_manifest", profile_manifest,
            atomic_bundle_roots=atomic_bundle_roots,
        )
        verified_overlay = _verified_runtime_profile_overlay(
            worktree=worktree, profile_manifest=profile_path,
            route_manifest=route_path,
            overlay=admission.get("runtime_profile_overlay"),
            expected_runtime_profile_id=expected_runtime_profile_id,
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
            expected_runtime_profile_id
        ):
            raise RecurrenceAdmissionError("runtime_profile_not_bound_by_config")
    elif expected_runtime_profile_id is not None or profile_manifest is not None:
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
    authority_path: Path | None = None
    authority_sha256: str | None = None
    if authority_projection is not None:
        authority_path = _verify_binding(
            admission, "build_control_authority",
            atomic_bundle_roots=atomic_bundle_roots,
        )
        authority_sha256 = str(authority_binding_recorded.get("sha256") or "")

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
    for key in QUARANTINE_STATE_FIELDS:
        if admission.get(key, []) != decision.get(key, []):
            raise RecurrenceAdmissionError(f"decision_{key}_mismatch")
    checkpoint_seal = admission.get("checkpoint_seal")
    if checkpoint_targeted or profile_authority_recorded:
        assert profile_path is not None and verified_overlay is not None
        if (
            not isinstance(checkpoint_seal, dict)
            or checkpoint_seal.get("fixture_id")
                != selected_checkpoint_fixture_id
        ):
            raise RecurrenceAdmissionError("checkpoint_seal_identity_mismatch")
        if magmaw_transfer_checkpoint_targeted:
            checkpoint_seal = _verify_magmaw_transfer_checkpoint_seal(
                seal=checkpoint_seal, worktree=worktree,
                binary=binary_path, build_receipt=build_receipt_path,
                decision=decision_path, runtime_config=runtime_config,
                profile_manifest=profile_path,
                runtime_profile_overlay=verified_overlay,
                expected_runtime_profile_id=expected_runtime_profile_id,
            )
        elif native_path_checkpoint_targeted:
            checkpoint_seal = _verify_native_path_checkpoint_seal(
                seal=checkpoint_seal, worktree=worktree,
                binary=binary_path, build_receipt=build_receipt_path,
                decision=decision_path, runtime_config=runtime_config,
                profile_manifest=profile_path,
                runtime_profile_overlay=verified_overlay,
                expected_runtime_profile_id=expected_runtime_profile_id,
            )
        elif profile_combat_range_checkpoint_targeted:
            checkpoint_seal = _verify_profile_combat_range_checkpoint_seal(
                seal=checkpoint_seal, worktree=worktree,
                binary=binary_path, build_receipt=build_receipt_path,
                decision=decision_path, runtime_config=runtime_config,
                profile_manifest=profile_path,
                runtime_profile_overlay=verified_overlay,
                expected_runtime_profile_id=expected_runtime_profile_id,
            )
        else:
            checkpoint_seal = _verify_chainwielder_checkpoint_seal(
                seal=checkpoint_seal,
                worktree=worktree,
                binary=binary_path,
                build_receipt=build_receipt_path,
                decision=decision_path,
                runtime_config=runtime_config,
                profile_manifest=profile_path,
                runtime_profile_overlay=verified_overlay,
                expected_runtime_profile_id=expected_runtime_profile_id,
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
    source_compatibility = verify_build_control_compatibility(
        worktree=worktree, receipt=build,
        authority_path=authority_path,
        authority_sha256=authority_sha256,
    )
    if not source_compatibility["valid"]:
        raise RecurrenceAdmissionError(
            "build_source_incompatible:" + source_compatibility["rejections"][0]
        )
    if admission.get("build_control_compatibility") != compatibility_projection(
        source_compatibility
    ):
        raise RecurrenceAdmissionError("build_control_compatibility_mismatch")
    if (
        build.get("classification") != "success"
        or build.get("exit_code") != 0
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
        "control_commit": source_compatibility["control_commit"],
        "build_source_commit": source_compatibility["build_source_commit"],
        "build_source_tree": source_compatibility["build_source_tree"],
        "build_control_relationship": source_compatibility["relationship"],
        "build_control_compatibility": compatibility_projection(
            source_compatibility
        ),
        "fixture_revisions": actual_revisions,
        "purpose": required_purpose,
        "fixture_expansion_target_ids": admission.get(
            "fixture_expansion_target_ids"
        ) or [],
        "fixture_expansion_requests": admission.get(
            "fixture_expansion_requests"
        ) or [],
        "pending_fixture_ids": admission.get("pending_fixture_ids") or [],
        "quarantined_fixture_ids": admission.get(
            "quarantined_fixture_ids"
        ) or [],
        "blocking_invalidated_fixture_ids": admission.get(
            "blocking_invalidated_fixture_ids"
        ) or [],
        "checkpoint_seal_sha256": (
            checkpoint_seal["seal_sha256"]
            if isinstance(checkpoint_seal, dict) else None
        ),
        "checkpoint_fixture_id": (
            selected_checkpoint_fixture_id
        ),
        "checkpoint_case_id": (
            checkpoint_seal.get("case_id")
            if isinstance(checkpoint_seal, dict) else None
        ),
        "checkpoint_actor_guid": (
            checkpoint_seal.get("actor_guid")
            if isinstance(checkpoint_seal, dict) else None
        ),
        "checkpoint_target_guid": (
            checkpoint_seal.get("target_guid")
            if isinstance(checkpoint_seal, dict) else None
        ),
        "bindings": {
            "route_manifest": (admission.get("bindings") or {})["route_manifest"],
            **({"build_control_authority": authority_binding_recorded}
               if authority_binding_recorded is not None else {}),
            **({"profile_manifest": (admission.get("bindings") or {})[
                "profile_manifest"
            ]} if profile_path is not None else {}),
        },
        "runtime_profile_overlay": verified_overlay,
        "expected_runtime_profile_id": expected_runtime_profile_id,
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
    create.add_argument("--build-control-authority", type=Path)
    create.add_argument("--build-control-authority-sha256")
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
                build_control_authority=args.build_control_authority,
                build_control_authority_sha256=(
                    args.build_control_authority_sha256
                ),
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
