"""Exact fixture-expansion contracts and immutable checkpoint seals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Callable


CHECKPOINT_SEAL_SCHEMA = "cata_raid_checkpoint_seal_v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GAMEPLAY_CANARY_PURPOSE = "gameplay_canary"
FIXTURE_EXPANSION_PURPOSE = "fixture_expansion_replay"
ADMISSION_PURPOSES = {GAMEPLAY_CANARY_PURPOSE, FIXTURE_EXPANSION_PURPOSE}
CHAINWIELDER_CHECKPOINT_FIXTURE_ID = (
    "chainwielder_pre_admission_rejection_isolation_v1"
)
CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX = (
    "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint"
)
NATIVE_PATH_CHECKPOINT_FIXTURE_ID = "map669_native_path_production_boundary_v1"
NATIVE_PATH_CHECKPOINT_CONFIG_PREFIX = (
    "BotWorld.ValidationFixture.NativePathCheckpoint"
)
NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS = {
    "same_level_floor_observation_v1": (4, 5),
    "same_level_hazard_path_admission_v1": (4, 5),
    "same_level_native_path_proof_v1": (4, 5),
}
NATIVE_PATH_CHECKPOINT_REQUIRED_PENDING_FIXTURE_IDS = (
    "same_level_hazard_path_admission_v1",
    "same_level_native_path_proof_v1",
)
MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID = (
    "map669_magmaw_transfer_lane_authority_off_v1"
)
MAGMAW_TRANSFER_CHECKPOINT_CASE_ID = "entrance_polygon_short_lane_v1"
MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID = 30007
MAGMAW_TRANSFER_CHECKPOINT_AUTHORITY = (
    "sealed_map669_transfer_lane_fixture_authority_off"
)
MAGMAW_TRANSFER_CHECKPOINT_CONFIG_PREFIX = (
    "BotWorld.ValidationFixture.MagmawTransferLaneCheckpoint"
)
MAGMAW_TRANSFER_CHECKPOINT_PROBE = Path(
    "experiments/configs/map669_magmaw_transfer_lane_entrance_probe_v1.json"
)


class RecurrenceAdmissionError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_object_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def git_value(worktree: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(worktree), *args], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return result.stdout if binary else result.stdout.decode().strip()


def load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise RecurrenceAdmissionError(f"{label}_missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RecurrenceAdmissionError(f"{label}_invalid") from error
    if not isinstance(value, dict):
        raise RecurrenceAdmissionError(f"{label}_invalid")
    return value


def config_bool(path: Path, key: str, default: bool = False) -> bool:
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


def config_string(path: Path, key: str, default: str = "") -> str:
    value = default
    pattern = re.compile(
        rf'^\s*{re.escape(key)}\s*=\s*"([^"\r\n]*)"\s*(?:#.*)?$'
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            value = match.group(1)
    return value


def fixture_expansion_contract(
    value: dict[str, Any], *, label: str,
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
            not isinstance(fixture_id, str) or not fixture_id
            or not isinstance(from_revision, int) or isinstance(from_revision, bool)
            or from_revision <= 0
            or not isinstance(to_revision, int) or isinstance(to_revision, bool)
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
    quarantined = value.get("quarantined_fixture_ids", [])
    if not isinstance(quarantined, list) or any(
        not isinstance(fixture_id, str) or not fixture_id
        for fixture_id in quarantined
    ):
        raise RecurrenceAdmissionError(f"{label}_quarantined_invalid")
    if set(targets) != (set(pending) - set(quarantined)) | set(request_ids):
        raise RecurrenceAdmissionError(f"{label}_request_target_mismatch")
    return requests


def native_path_checkpoint_request_contract(
    value: dict[str, Any], *, label: str,
) -> list[dict[str, Any]]:
    requests = fixture_expansion_contract(value, label=label)
    expected_pending = set(NATIVE_PATH_CHECKPOINT_REQUIRED_PENDING_FIXTURE_IDS)
    contract = {
        row["fixture_id"]: (row["from_revision"], row["to_revision"])
        for row in requests
    }
    pending = value.get("pending_fixture_ids", [])
    if (
        set(value["fixture_expansion_target_ids"])
            != set(NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS)
        or len(pending) != len(expected_pending)
        or set(pending) != expected_pending
        or contract != NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS
    ):
        raise RecurrenceAdmissionError(f"{label}_request_contract_mismatch")
    return requests


def native_path_checkpoint_requested(value: dict[str, Any]) -> bool:
    targets = value.get("fixture_expansion_target_ids")
    return isinstance(targets, list) and bool(
        set(targets) & set(NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS)
    )


def magmaw_transfer_checkpoint_contract(
    value: dict[str, Any], *, label: str,
) -> list[dict[str, Any]]:
    requests = fixture_expansion_contract(value, label=label)
    if (
        value.get("fixture_expansion_target_ids")
            != [MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID]
        or value.get("pending_fixture_ids")
            != [MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID]
        or requests != []
    ):
        raise RecurrenceAdmissionError(f"{label}_request_contract_mismatch")
    return requests


def magmaw_transfer_checkpoint_requested(value: dict[str, Any]) -> bool:
    targets = value.get("fixture_expansion_target_ids")
    return isinstance(targets, list) and (
        MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID in targets
    )


def _seal_payload(payload: dict[str, Any]) -> dict[str, str]:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return {**payload, "seal_sha256": hashlib.sha256(canonical).hexdigest()}


def build_chainwielder_checkpoint_seal(
    *, worktree: Path, binary: Path, build_receipt: Path, decision: Path,
    profile_manifest: Path | None, runtime_profile_overlay: dict[str, Any] | None,
    expected_runtime_profile_id: str | None,
    git_fn: Callable[..., str | bytes],
) -> dict[str, str]:
    worktree = worktree.resolve()
    payload: dict[str, Any] = {
        "schema": CHECKPOINT_SEAL_SCHEMA,
        "fixture_id": CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        "purpose": FIXTURE_EXPANSION_PURPOSE,
        "source_commit": str(git_fn(worktree, "rev-parse", "HEAD")),
        "source_tree": str(git_fn(worktree, "rev-parse", "HEAD^{tree}")),
        "binary_sha256": sha256_file(binary.resolve()),
        "build_receipt_sha256": sha256_file(build_receipt.resolve()),
        "decision_sha256": sha256_file(decision.resolve()),
    }
    authority = (
        profile_manifest is not None,
        runtime_profile_overlay is not None,
        expected_runtime_profile_id is not None,
    )
    if any(authority) and not all(authority):
        raise RecurrenceAdmissionError("checkpoint_profile_authority_incomplete")
    if all(authority):
        assert profile_manifest is not None
        assert runtime_profile_overlay is not None
        assert expected_runtime_profile_id is not None
        if not expected_runtime_profile_id:
            raise RecurrenceAdmissionError("expected_runtime_profile_invalid")
        payload.update({
            "profile_manifest_sha256": sha256_file(profile_manifest.resolve()),
            "expected_runtime_profile_id": expected_runtime_profile_id,
            "runtime_profile_overlay_sha256": canonical_object_sha256(
                runtime_profile_overlay
            ),
        })
    return _seal_payload(payload)


def build_case_checkpoint_seal(
    *, fixture_id: str, case_id: str, label: str,
    worktree: Path, binary: Path, build_receipt: Path, decision: Path,
    profile_manifest: Path, runtime_profile_overlay: dict[str, Any],
    expected_runtime_profile_id: str, requests: list[dict[str, Any]],
    git_fn: Callable[..., str | bytes],
    probe_receipt: Path | None = None,
) -> dict[str, str]:
    if not isinstance(case_id, str) or not case_id.strip():
        raise RecurrenceAdmissionError(f"{label}_case_invalid")
    worktree = worktree.resolve()
    payload: dict[str, Any] = {
        "schema": CHECKPOINT_SEAL_SCHEMA,
        "fixture_id": fixture_id,
        "case_id": case_id,
        "purpose": FIXTURE_EXPANSION_PURPOSE,
        "source_commit": str(git_fn(worktree, "rev-parse", "HEAD")),
        "source_tree": str(git_fn(worktree, "rev-parse", "HEAD^{tree}")),
        "binary_sha256": sha256_file(binary.resolve()),
        "build_receipt_sha256": sha256_file(build_receipt.resolve()),
        "decision_sha256": sha256_file(decision.resolve()),
        "fixture_expansion_requests_sha256": canonical_object_sha256(requests),
        "profile_manifest_sha256": sha256_file(profile_manifest.resolve()),
        "expected_runtime_profile_id": expected_runtime_profile_id,
        "runtime_profile_overlay_sha256": canonical_object_sha256(
            runtime_profile_overlay
        ),
    }
    if probe_receipt is not None:
        payload["probe_receipt_sha256"] = sha256_file(probe_receipt.resolve())
    return _seal_payload(payload)


def verify_case_checkpoint_config(
    *, seal: object, expected: dict[str, str], runtime_config: Path,
    prefix: str, label: str, fixture_id: str,
    require_authority_off: bool = False,
) -> dict[str, str]:
    if seal != expected:
        raise RecurrenceAdmissionError(f"{label}_seal_identity_mismatch")
    expected_config = {
        "FixtureId": fixture_id,
        "CaseId": expected["case_id"],
        "SealSha256": expected["seal_sha256"],
        "SourceCommit": expected["source_commit"],
    }
    if not config_bool(runtime_config, f"{prefix}.Enable"):
        raise RecurrenceAdmissionError(f"{label}_config_disabled")
    if not config_bool(runtime_config, "BotWorld.ValidationRoute.Enable"):
        raise RecurrenceAdmissionError(f"{label}_progress_sampling_disabled")
    if require_authority_off and config_bool(
        runtime_config, "BotWorld.Magmaw.TransferLaneTaskAuthority"
    ):
        raise RecurrenceAdmissionError(f"{label}_task_authority_enabled")
    if any(
        config_string(runtime_config, f"{prefix}.{key}") != value
        for key, value in expected_config.items()
    ):
        raise RecurrenceAdmissionError(f"{label}_config_mismatch")
    return expected
