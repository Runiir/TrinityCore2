from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


SCHEMA = "cata_raid_recurrence_admission_v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class RecurrenceAdmissionError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _verify_binding(
    admission: dict[str, Any], name: str, actual_path: Path | None = None
) -> Path:
    binding = (admission.get("bindings") or {}).get(name)
    if not isinstance(binding, dict):
        raise RecurrenceAdmissionError(f"{name}_binding_missing")
    raw_path = binding.get("path")
    expected_hash = binding.get("sha256")
    if not isinstance(raw_path, str) or not SHA256_RE.fullmatch(str(expected_hash or "")):
        raise RecurrenceAdmissionError(f"{name}_binding_invalid")
    path = Path(raw_path).resolve()
    if actual_path is not None and path != actual_path.resolve():
        raise RecurrenceAdmissionError(f"{name}_path_mismatch")
    if not path.is_file():
        raise RecurrenceAdmissionError(f"{name}_missing")
    if sha256_file(path) != expected_hash:
        raise RecurrenceAdmissionError(f"{name}_hash_mismatch")
    return path


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
    empty_fields = (
        "invalidated_fixture_ids",
        "failing_fixture_ids",
        "missing_fixture_ids",
        "stale_fixture_ids",
    )
    admission = {
        "schema": SCHEMA,
        "build_admitted": decision_value.get("build_admitted") is True,
        "canary_admitted": decision_value.get("canary_admitted") is True,
        **{key: decision_value.get(key) for key in empty_fields},
        "source": {
            "commit": head,
            "tree": tree,
            "porcelain_sha256": hashlib.sha256(porcelain).hexdigest(),
        },
        "bindings": {
            name: {"path": str(path.resolve()), "sha256": sha256_file(path.resolve())}
            for name, path in {
                "binary": binary,
                "build_receipt": build_receipt,
                "runtime_config": runtime_config,
                "route_manifest": route_manifest,
                "ledger": ledger,
                "decision": decision,
                "suite_receipt": suite_receipt,
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
    if admission.get("build_admitted") is not True:
        raise RecurrenceAdmissionError("build_not_admitted")
    if admission.get("canary_admitted") is not True:
        raise RecurrenceAdmissionError("canary_not_admitted")
    for key in (
        "invalidated_fixture_ids",
        "failing_fixture_ids",
        "missing_fixture_ids",
        "stale_fixture_ids",
    ):
        if admission.get(key) != []:
            raise RecurrenceAdmissionError(f"{key}_present")

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

    binary_path = _verify_binding(admission, "binary", binary)
    build_receipt_path = _verify_binding(admission, "build_receipt", build_receipt)
    _verify_binding(admission, "runtime_config", runtime_config)
    route_path = _verify_binding(admission, "route_manifest")
    ledger_path = _verify_binding(admission, "ledger")
    decision_path = _verify_binding(admission, "decision")
    suite_path = _verify_binding(admission, "suite_receipt")

    config_text = runtime_config.read_text(encoding="utf-8")
    if str(route_path) not in config_text:
        raise RecurrenceAdmissionError("route_manifest_not_bound_by_config")
    decision = _load(decision_path, "decision")
    if decision.get("build_admitted") is not True or decision.get("canary_admitted") is not True:
        raise RecurrenceAdmissionError("decision_not_admitted")
    for key in (
        "invalidated_fixture_ids",
        "failing_fixture_ids",
        "missing_fixture_ids",
        "stale_fixture_ids",
    ):
        if decision.get(key) != []:
            raise RecurrenceAdmissionError(f"decision_{key}_present")

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
    verify.add_argument("--admission", type=Path, required=True)
    verify.add_argument("--sha256", required=True)
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
            )
            result = {
                "created": True,
                "path": str(args.output.resolve()),
                "sha256": sha256_file(args.output.resolve()),
                "source": result["source"],
            }
        else:
            result = verify_recurrence_admission(
                admission_path=args.admission,
                expected_sha256=args.sha256,
                worktree=args.worktree,
                binary=args.binary,
                build_receipt=args.build_receipt,
                runtime_config=args.runtime_config,
            )
    except RecurrenceAdmissionError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
