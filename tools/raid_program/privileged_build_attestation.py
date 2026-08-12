#!/usr/bin/env python3
"""Verify externally signed raid-build receipts without local signing authority."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from tools.raid_program.queued_build import (
    CoordinatorError,
    canonical_json,
    load_json,
    sha256_bytes,
    sha256_file,
    verify_receipt,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SERVICE_CONFIG = (
    ROOT / "experiments/configs/cata_raid_privileged_build_service_v1.json"
)


def signed_payload(receipt: dict, attestation: dict) -> dict:
    """Reconstruct every signed identity from the receipt and ledger envelope."""

    return {
        "schema_version": 1,
        "service_id": attestation.get("service_id"),
        "key_id": attestation.get("key_id"),
        "ledger_sequence": attestation.get("ledger_sequence"),
        "ledger_record_id": attestation.get("ledger_record_id"),
        "signed_at_utc": attestation.get("signed_at_utc"),
        "receipt_sha256": receipt.get("receipt_sha256"),
        "policy_id": receipt.get("policy_id"),
        "policy_sha256": receipt.get("policy_sha256"),
        "ticket_id": receipt.get("ticket_id"),
        "queue_sequence": receipt.get("queue_sequence"),
        "resource_class": receipt.get("resource_class"),
        "classification": receipt.get("classification"),
        "exit_code": receipt.get("exit_code"),
        "commit": receipt.get("commit"),
        "worktree": receipt.get("worktree"),
        "command_sha256": receipt.get("command_sha256"),
        "source_identity_sha256": sha256_bytes(
            canonical_json(receipt.get("source_identity"))
        ),
        "build_configuration_sha256": sha256_bytes(
            canonical_json(receipt.get("build_configuration"))
        ),
        "configure_lineage_sha256": sha256_bytes(
            canonical_json(receipt.get("configure_lineage"))
        ),
        "toolchain_identity_sha256": sha256_bytes(
            canonical_json(receipt.get("toolchain_identity"))
        ),
        "environment_contract_sha256": sha256_bytes(
            canonical_json(receipt.get("environment_contract"))
        ),
        "output_artifacts_sha256": sha256_bytes(
            canonical_json(receipt.get("output_artifacts"))
        ),
    }


def _timestamp(value: object, field: str) -> float:
    if not isinstance(value, str):
        raise CoordinatorError(f"privileged attestation {field} is missing")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError as error:
        raise CoordinatorError(f"privileged attestation {field} is invalid") from error


def verify_privileged_attestation(
    attestation_path: Path,
    receipt_path: Path,
    policy_path: Path,
    service_config_path: Path = DEFAULT_SERVICE_CONFIG,
    *,
    allow_test_mode: bool = False,
) -> dict:
    """Verify local semantics plus a signature from an authority outside this UID."""

    policy = load_json(policy_path)
    receipt = load_json(receipt_path)
    attestation = load_json(attestation_path)
    service = load_json(service_config_path)
    if service.get("schema_version") != 1:
        raise CoordinatorError("unsupported privileged build service schema")
    if service.get("state") != "provisioned":
        raise CoordinatorError("privileged build service is not provisioned")
    if attestation.get("schema_version") != 1:
        raise CoordinatorError("unsupported privileged attestation schema")
    if attestation.get("service_id") != service.get("service_id"):
        raise CoordinatorError("privileged attestation service ID mismatch")
    if attestation.get("key_id") != service.get("key_id"):
        raise CoordinatorError("privileged attestation key ID mismatch")
    sequence = attestation.get("ledger_sequence")
    minimum_sequence = service.get("minimum_ledger_sequence", 1)
    if not isinstance(sequence, int) or sequence < int(minimum_sequence):
        raise CoordinatorError("privileged attestation ledger sequence is invalid")
    record_id = attestation.get("ledger_record_id")
    if not isinstance(record_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,160}", record_id):
        raise CoordinatorError("privileged attestation ledger record ID is invalid")

    local_verification = verify_receipt(
        receipt_path, policy, allow_test_mode=allow_test_mode
    )
    if local_verification.get("classification") != "success":
        raise CoordinatorError("privileged attestation references a non-success receipt")
    if receipt.get("test_mode") and not allow_test_mode:
        raise CoordinatorError("test receipt cannot satisfy privileged production attestation")

    payload = signed_payload(receipt, attestation)
    if attestation.get("payload") != payload:
        raise CoordinatorError("privileged attestation payload differs from reconstructed receipt")
    payload_hash = sha256_bytes(canonical_json(payload))
    if attestation.get("payload_sha256") != payload_hash:
        raise CoordinatorError("privileged attestation payload hash mismatch")
    claimed_attestation_hash = attestation.get("attestation_sha256")
    unhashed = dict(attestation)
    unhashed.pop("attestation_sha256", None)
    if claimed_attestation_hash != sha256_bytes(canonical_json(unhashed)):
        raise CoordinatorError("privileged attestation canonical hash mismatch")

    signed_at = _timestamp(attestation.get("signed_at_utc"), "signed_at_utc")
    ended_at = _timestamp(receipt.get("ended_at_utc"), "receipt ended_at_utc")
    if signed_at < ended_at or signed_at > time.time() + 300:
        raise CoordinatorError("privileged attestation signing time is outside the valid window")

    public_key_value = service.get("public_key_path")
    if not isinstance(public_key_value, str) or not public_key_value:
        raise CoordinatorError("privileged service public key path is missing")
    public_key = Path(public_key_value)
    if not public_key.is_absolute():
        public_key = (service_config_path.parent / public_key).resolve()
    if not public_key.is_file():
        raise CoordinatorError("privileged service public key is unavailable")
    if sha256_file(public_key) != service.get("public_key_sha256"):
        raise CoordinatorError("privileged service public key identity mismatch")
    signature_value = attestation.get("signature_base64")
    try:
        signature = base64.b64decode(signature_value, validate=True)
    except (TypeError, ValueError, binascii.Error) as error:
        raise CoordinatorError("privileged attestation signature encoding is invalid") from error
    if len(signature) != 64:
        raise CoordinatorError("privileged Ed25519 signature length is invalid")

    with tempfile.TemporaryDirectory(prefix="raid-attestation-verify-") as temporary:
        temporary_path = Path(temporary)
        payload_path = temporary_path / "payload.json"
        signature_path = temporary_path / "signature.bin"
        payload_path.write_bytes(canonical_json(payload))
        signature_path.write_bytes(signature)
        result = subprocess.run(
            [
                "/usr/bin/openssl", "pkeyutl", "-verify", "-pubin",
                "-inkey", str(public_key), "-rawin", "-in", str(payload_path),
                "-sigfile", str(signature_path),
            ],
            check=False,
            capture_output=True,
        )
    if result.returncode != 0:
        raise CoordinatorError("privileged Ed25519 signature verification failed")
    return {
        "valid": True,
        "service_id": service["service_id"],
        "key_id": service["key_id"],
        "ledger_sequence": sequence,
        "ledger_record_id": record_id,
        "payload_sha256": payload_hash,
        "attestation_sha256": claimed_attestation_hash,
        "receipt_sha256": receipt["receipt_sha256"],
        "commit": receipt["commit"],
        "classification": receipt["classification"],
        "test_mode": bool(receipt.get("test_mode")),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--attestation", type=Path, required=True)
    result.add_argument("--receipt", type=Path, required=True)
    result.add_argument("--policy", type=Path, required=True)
    result.add_argument("--service-config", type=Path, default=DEFAULT_SERVICE_CONFIG)
    result.add_argument("--allow-test-mode", action="store_true")
    return result


def main(arguments: Sequence[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    try:
        report = verify_privileged_attestation(
            args.attestation.resolve(),
            args.receipt.resolve(),
            args.policy.resolve(),
            args.service_config.resolve(),
            allow_test_mode=args.allow_test_mode,
        )
    except CoordinatorError as error:
        print(f"privileged_build_attestation: {error}", flush=True)
        return 64
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
