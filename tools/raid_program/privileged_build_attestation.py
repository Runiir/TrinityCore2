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
import urllib.parse
import urllib.request
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
PRODUCTION_POLICY = (
    ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v8.json"
)
PROTOCOL = "ed25519_signed_coordinator_receipt_v1"
REQUIRED_SIGNED_SCOPE = [
    "service_and_key_identity",
    "ledger_sequence_and_record_id",
    "signing_time",
    "receipt_and_policy_identity",
    "ticket_queue_resource_and_command_identity",
    "source_commit_tree_and_cleanliness_identity",
    "configure_lineage_cache_and_generated_build_graph_identity",
    "toolchain_and_positive_environment_identity",
    "worldserver_output_artifact_identity",
]
REQUIRED_AUTHORITY_BOUNDARY = {
    "execution_principal": "separate_os_uid_or_remote_service",
    "private_key_readable_by_capture_principal": False,
    "ledger_mutable_by_capture_principal": False,
    "service_executes_admitted_configure_and_build": True,
    "append_only_ledger": True,
    "hardware_backed_or_remote_signer_allowed": True,
}


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
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value
    ):
        raise CoordinatorError(f"privileged attestation {field} is missing")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError as error:
        raise CoordinatorError(f"privileged attestation {field} is invalid") from error


def _policy_service_config(policy: dict) -> Path:
    value = policy.get("mechanical_controls", {}).get("privileged_build_service_config")
    if not isinstance(value, str) or not value:
        raise CoordinatorError("policy privileged service config path is missing")
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _verify_ed25519(public_key: Path, payload: dict, signature_value: object, label: str) -> None:
    try:
        signature = base64.b64decode(signature_value, validate=True)
    except (TypeError, ValueError, binascii.Error) as error:
        raise CoordinatorError(f"{label} signature encoding is invalid") from error
    if len(signature) != 64:
        raise CoordinatorError(f"{label} Ed25519 signature length is invalid")
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
        raise CoordinatorError(f"{label} Ed25519 signature verification failed")


def attestation_record(attestation: dict) -> dict:
    return {
        key: value for key, value in attestation.items()
        if key not in {"attestation_sha256", "attestation_record_sha256"}
    }


def ledger_payload(
    receipt: dict,
    attestation: dict,
    proof: dict,
    record_sha256: str,
) -> dict:
    return {
        "schema_version": 1,
        "service_id": attestation.get("service_id"),
        "ledger_key_id": proof.get("ledger_key_id"),
        "ledger_sequence": attestation.get("ledger_sequence"),
        "ledger_head_sequence": proof.get("ledger_head_sequence"),
        "ledger_record_id": attestation.get("ledger_record_id"),
        "checkpoint_id": proof.get("checkpoint_id"),
        "checkpoint_at_utc": proof.get("checkpoint_at_utc"),
        "record_status": proof.get("record_status"),
        "record_unique": proof.get("record_unique"),
        "record_revoked": proof.get("record_revoked"),
        "attestation_record_sha256": record_sha256,
        "attestation_payload_sha256": attestation.get("payload_sha256"),
        "receipt_sha256": receipt.get("receipt_sha256"),
    }


def _fetch_ledger_proof(endpoint: str, record_id: str, allow_test_mode: bool) -> dict:
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme != "https" and not (allow_test_mode and parsed.scheme == "file"):
        raise CoordinatorError("privileged ledger endpoint must use HTTPS")
    if parsed.scheme == "file":
        request_url = endpoint
    else:
        query = urllib.parse.urlencode({"record_id": record_id})
        separator = "&" if parsed.query else "?"
        request_url = endpoint + separator + query
    try:
        with urllib.request.urlopen(request_url, timeout=15) as response:
            final_scheme = urllib.parse.urlparse(response.geturl()).scheme
            if parsed.scheme == "https" and final_scheme != "https":
                raise CoordinatorError("privileged ledger endpoint redirected outside HTTPS")
            status = getattr(response, "status", None)
            if status is not None and status != 200:
                raise CoordinatorError("privileged ledger endpoint returned non-success status")
            data = response.read(1024 * 1024 + 1)
    except (OSError, ValueError) as error:
        raise CoordinatorError(f"privileged ledger proof unavailable: {error}") from error
    if len(data) > 1024 * 1024:
        raise CoordinatorError("privileged ledger proof exceeds size limit")
    try:
        proof = json.loads(data)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CoordinatorError("privileged ledger proof is invalid JSON") from error
    if not isinstance(proof, dict):
        raise CoordinatorError("privileged ledger proof must be an object")
    return proof


def verify_privileged_attestation(
    attestation_path: Path,
    receipt_path: Path,
    policy_path: Path,
    service_config_path: Path | None = None,
    *,
    allow_test_mode: bool = False,
) -> dict:
    """Verify local semantics plus a signature from an authority outside this UID."""

    if not allow_test_mode and policy_path.resolve() != PRODUCTION_POLICY.resolve():
        raise CoordinatorError("production attestation requires the tracked v8 build policy")
    policy = load_json(policy_path)
    receipt = load_json(receipt_path)
    attestation = load_json(attestation_path)
    controls = policy.get("mechanical_controls", {})
    declared_service_path = _policy_service_config(policy)
    if service_config_path is not None and service_config_path.resolve() != declared_service_path:
        raise CoordinatorError("caller-selected privileged service config is forbidden")
    service_config_path = declared_service_path
    service = load_json(service_config_path)
    expected_config_hash = controls.get("privileged_build_service_config_sha256")
    if not isinstance(expected_config_hash, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_config_hash
    ) or sha256_file(service_config_path) != expected_config_hash:
        raise CoordinatorError("policy-pinned privileged service config identity mismatch")
    if service.get("schema_version") != 1:
        raise CoordinatorError("unsupported privileged build service schema")
    if service.get("state") != "provisioned":
        raise CoordinatorError("privileged build service is not provisioned")
    if service.get("protocol") != PROTOCOL or controls.get(
        "privileged_build_service_protocol"
    ) != PROTOCOL:
        raise CoordinatorError("privileged build service protocol mismatch")
    for field in ("service_id", "key_id", "ledger_key_id"):
        value = service.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,160}", value):
            raise CoordinatorError(f"privileged service {field} is invalid")
    for field in ("public_key_sha256", "ledger_public_key_sha256"):
        value = service.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise CoordinatorError(f"privileged service {field} is invalid")
    pinned_fields = {
        "service_id": "privileged_build_service_id",
        "key_id": "privileged_build_key_id",
        "public_key_sha256": "privileged_build_public_key_sha256",
        "submission_endpoint": "privileged_build_submission_endpoint",
        "ledger_key_id": "privileged_ledger_key_id",
        "ledger_public_key_sha256": "privileged_ledger_public_key_sha256",
        "ledger_verification_endpoint": "privileged_ledger_verification_endpoint",
        "maximum_ledger_checkpoint_age_seconds": (
            "privileged_ledger_maximum_checkpoint_age_seconds"
        ),
    }
    for service_field, policy_field in pinned_fields.items():
        service_value = service.get(service_field)
        if service_value is None or service_value != controls.get(policy_field):
            raise CoordinatorError(
                f"privileged service field {service_field} is not policy-pinned"
            )
    if service.get("signed_identity_scope") != REQUIRED_SIGNED_SCOPE:
        raise CoordinatorError("privileged service signed identity scope is incomplete")
    if service.get("required_authority_boundary") != REQUIRED_AUTHORITY_BOUNDARY:
        raise CoordinatorError("privileged service authority boundary contract is incomplete")
    for endpoint_field in ("submission_endpoint", "ledger_verification_endpoint"):
        endpoint = service.get(endpoint_field)
        parsed = urllib.parse.urlparse(endpoint) if isinstance(endpoint, str) else None
        if parsed is None or parsed.scheme != "https" or not parsed.netloc:
            if not (allow_test_mode and parsed is not None and parsed.scheme == "file"):
                raise CoordinatorError(f"privileged service {endpoint_field} must use HTTPS")
    if attestation.get("schema_version") != 1:
        raise CoordinatorError("unsupported privileged attestation schema")
    if attestation.get("service_id") != service.get("service_id"):
        raise CoordinatorError("privileged attestation service ID mismatch")
    if attestation.get("key_id") != service.get("key_id"):
        raise CoordinatorError("privileged attestation key ID mismatch")
    sequence = attestation.get("ledger_sequence")
    minimum_sequence = service.get("minimum_ledger_sequence", 1)
    if type(minimum_sequence) is not int or minimum_sequence < 1:
        raise CoordinatorError("privileged service minimum ledger sequence is invalid")
    if type(sequence) is not int or sequence < minimum_sequence:
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
    _verify_ed25519(
        public_key, payload, attestation.get("signature_base64"), "privileged attestation"
    )

    record_sha256 = sha256_bytes(canonical_json(attestation_record(attestation)))
    if attestation.get("attestation_record_sha256") != record_sha256:
        raise CoordinatorError("privileged attestation record hash mismatch")
    proof = _fetch_ledger_proof(
        str(service["ledger_verification_endpoint"]), record_id, allow_test_mode
    )
    if proof.get("schema_version") != 1:
        raise CoordinatorError("unsupported privileged ledger proof schema")
    checkpoint_id = proof.get("checkpoint_id")
    if not isinstance(checkpoint_id, str) or not re.fullmatch(
        r"[A-Za-z0-9._:-]{8,160}", checkpoint_id
    ):
        raise CoordinatorError("privileged ledger checkpoint ID is invalid")
    ledger_public_key_value = service.get("ledger_public_key_path")
    if not isinstance(ledger_public_key_value, str) or not ledger_public_key_value:
        raise CoordinatorError("privileged ledger public key path is missing")
    ledger_public_key = Path(ledger_public_key_value)
    if not ledger_public_key.is_absolute():
        ledger_public_key = (service_config_path.parent / ledger_public_key).resolve()
    if not ledger_public_key.is_file() or sha256_file(ledger_public_key) != service.get(
        "ledger_public_key_sha256"
    ):
        raise CoordinatorError("privileged ledger public key identity mismatch")
    checkpoint_payload = ledger_payload(receipt, attestation, proof, record_sha256)
    if proof.get("payload") != checkpoint_payload:
        raise CoordinatorError("privileged ledger proof differs from reconstructed inclusion")
    checkpoint_hash = sha256_bytes(canonical_json(checkpoint_payload))
    if proof.get("payload_sha256") != checkpoint_hash:
        raise CoordinatorError("privileged ledger proof payload hash mismatch")
    if proof.get("ledger_key_id") != service.get("ledger_key_id"):
        raise CoordinatorError("privileged ledger key ID mismatch")
    if proof.get("record_status") != "included" or proof.get("record_unique") is not True:
        raise CoordinatorError("privileged ledger record is not uniquely included")
    if proof.get("record_revoked") is not False:
        raise CoordinatorError("privileged ledger record is revoked")
    head = proof.get("ledger_head_sequence")
    if type(head) is not int or head < sequence:
        raise CoordinatorError("privileged ledger head does not include record sequence")
    checkpoint_at = _timestamp(
        proof.get("checkpoint_at_utc"), "ledger checkpoint_at_utc"
    )
    maximum_age = service.get("maximum_ledger_checkpoint_age_seconds")
    if type(maximum_age) is not int or maximum_age < 1 or maximum_age > 3600:
        raise CoordinatorError("privileged ledger checkpoint age policy is invalid")
    if (
        checkpoint_at < signed_at
        or checkpoint_at < time.time() - maximum_age
        or checkpoint_at > time.time() + 300
    ):
        raise CoordinatorError("privileged ledger checkpoint time is outside the valid window")
    _verify_ed25519(
        ledger_public_key,
        checkpoint_payload,
        proof.get("signature_base64"),
        "privileged ledger checkpoint",
    )
    return {
        "valid": True,
        "service_id": service["service_id"],
        "key_id": service["key_id"],
        "ledger_sequence": sequence,
        "ledger_record_id": record_id,
        "payload_sha256": payload_hash,
        "attestation_sha256": claimed_attestation_hash,
        "receipt_sha256": receipt["receipt_sha256"],
        "ledger_checkpoint_sha256": checkpoint_hash,
        "ledger_head_sequence": head,
        "commit": receipt["commit"],
        "classification": receipt["classification"],
        "test_mode": bool(receipt.get("test_mode")),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--attestation", type=Path, required=True)
    result.add_argument("--receipt", type=Path, required=True)
    result.add_argument("--policy", type=Path, required=True)
    result.add_argument("--allow-test-mode", action="store_true")
    return result


def main(arguments: Sequence[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    try:
        report = verify_privileged_attestation(
            args.attestation.resolve(),
            args.receipt.resolve(),
            args.policy.resolve(),
            None,
            allow_test_mode=args.allow_test_mode,
        )
    except CoordinatorError as error:
        print(f"privileged_build_attestation: {error}", flush=True)
        return 64
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
