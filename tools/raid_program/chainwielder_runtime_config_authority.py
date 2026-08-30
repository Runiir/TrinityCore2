"""Resolve the explicit base-runtime-config authority for a prestart bundle."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any

from tools.raid_program.canonical_route_staging import (
    CanonicalRouteStagingError,
    verify_derived_runtime_config_snapshot,
    verify_tracked_snapshot,
)
from tools.raid_program.tracked_runtime_config_derivation import OUTPUT_SHA256


LEGACY_TRACKED_SNAPSHOT_AUTHORITY = "tracked_snapshot_v1"
TRACKED_DERIVED_AUTHORITY = "tracked_derived_runtime_config_v1"
DERIVED_OUTPUT_LENGTH = 156_488


class RuntimeConfigAuthorityError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedRuntimeConfigAuthority:
    authority_type: str
    payload: bytes
    payload_sha256: str
    receipt_path: str
    receipt_sha256: str
    snapshot_path: str


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def runtime_config_value(
    text: str, key: str, error_type: type[RuntimeError],
) -> str:
    pattern = re.compile(
        rf"^(?!\s*[#;])\s*{re.escape(key)}\s*=.*$", re.MULTILINE
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        reason = "missing" if not matches else "duplicate"
        raise error_type(f"config_{reason}_key:{key}")
    return matches[0].group(0).split("=", 1)[1].strip()


def render_runtime_config(
    base: bytes, values: dict[str, str], error_type: type[RuntimeError],
) -> bytes:
    """Apply exact one-assignment overrides to authenticated config bytes."""

    try:
        text = base.decode("utf-8")
    except UnicodeError as error:
        raise error_type("base_runtime_config_invalid") from error
    for key, replacement in values.items():
        pattern = re.compile(
            rf"^(?!\s*[#;])\s*{re.escape(key)}\s*=.*$", re.MULTILINE
        )
        matches = list(pattern.finditer(text))
        if len(matches) > 1:
            raise error_type(f"config_duplicate_key:{key}")
        line = f"{key} = {replacement}"
        if matches:
            match = matches[0]
            text = text[:match.start()] + line + text[match.end():]
        else:
            text = text.rstrip() + "\n" + line + "\n"
    for key, expected in values.items():
        if runtime_config_value(text, key, error_type) != expected:
            raise error_type(f"config_binding_mismatch:{key}")
    return text.encode("utf-8")


def _decode_snapshot(value: dict[str, Any]) -> bytes:
    encoded = value.get("snapshot_bytes_base64")
    if not isinstance(encoded, str):
        raise RuntimeConfigAuthorityError("derived_runtime_config_snapshot_invalid")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as error:
        raise RuntimeConfigAuthorityError(
            "derived_runtime_config_snapshot_invalid"
        ) from error
    if base64.b64encode(payload).decode("ascii") != encoded:
        raise RuntimeConfigAuthorityError("derived_runtime_config_snapshot_invalid")
    return payload


def resolve_runtime_config_authority(
    *, authority_type: object, worktree: Path, receipt_path: Path,
    expected_receipt_sha256: str, contract_relative_path: str | None,
    expected_source_commit: str, expected_source_tree: str,
) -> VerifiedRuntimeConfigAuthority:
    """Return only bytes authenticated by the selected authority verifier."""

    if type(authority_type) is not str or authority_type not in {
        LEGACY_TRACKED_SNAPSHOT_AUTHORITY,
        TRACKED_DERIVED_AUTHORITY,
    }:
        raise RuntimeConfigAuthorityError("runtime_config_authority_selection_invalid")

    try:
        if authority_type == LEGACY_TRACKED_SNAPSHOT_AUTHORITY:
            if contract_relative_path is not None:
                raise RuntimeConfigAuthorityError(
                    "runtime_config_authority_arguments_ambiguous"
                )
            verified = verify_tracked_snapshot(
                worktree=worktree,
                receipt_path=receipt_path,
                expected_receipt_sha256=expected_receipt_sha256,
            )
            snapshot_path = Path(str(verified["snapshot_path"]))
            payload = snapshot_path.read_bytes()
            payload_sha256 = str(verified["snapshot_sha256"])
            if _sha256(payload) != payload_sha256:
                raise RuntimeConfigAuthorityError(
                    "tracked_snapshot_binding_mismatch"
                )
            receipt_identity = str(verified["receipt_path"])
            receipt_sha256 = str(verified["receipt_sha256"])
        else:
            if not isinstance(contract_relative_path, str) or not contract_relative_path:
                raise RuntimeConfigAuthorityError(
                    "derived_runtime_config_contract_missing"
                )
            verified = verify_derived_runtime_config_snapshot(
                worktree=worktree,
                receipt_path=receipt_path,
                expected_receipt_sha256=expected_receipt_sha256,
                contract_relative_path=contract_relative_path,
                expected_source_commit=expected_source_commit,
                expected_source_tree=expected_source_tree,
            )
            payload = _decode_snapshot(verified)
            payload_sha256 = str(verified.get("snapshot_sha256") or "")
            snapshot_length = verified.get("snapshot_length")
            if (
                snapshot_length != DERIVED_OUTPUT_LENGTH
                or len(payload) != DERIVED_OUTPUT_LENGTH
                or payload_sha256 != OUTPUT_SHA256
                or _sha256(payload) != OUTPUT_SHA256
            ):
                raise RuntimeConfigAuthorityError(
                    "derived_runtime_config_snapshot_binding_mismatch"
                )
            snapshot_path = Path(str(verified["snapshot_path"]))
            receipt_identity = str(verified["derivation_receipt_path"])
            receipt_sha256 = str(verified["derivation_receipt_sha256"])
    except CanonicalRouteStagingError as error:
        raise RuntimeConfigAuthorityError(str(error)) from error
    except OSError as error:
        raise RuntimeConfigAuthorityError(
            "runtime_config_authority_snapshot_unreadable"
        ) from error

    return VerifiedRuntimeConfigAuthority(
        authority_type=authority_type,
        payload=payload,
        payload_sha256=payload_sha256,
        receipt_path=receipt_identity,
        receipt_sha256=receipt_sha256,
        snapshot_path=str(snapshot_path),
    )
