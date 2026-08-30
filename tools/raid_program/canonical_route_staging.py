"""Authenticate and stage a DVC-owned route outside its source worktree."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Any

import yaml


STAGING_RECEIPT_SCHEMA = "cata_raid_external_route_staging_receipt_v1"
TRACKED_SNAPSHOT_RECEIPT_SCHEMA = "cata_raid_tracked_snapshot_receipt_v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
MD5_RE = re.compile(r"[0-9a-f]{32}")
ARTIFACT_LABEL_RE = re.compile(r"[a-z0-9][a-z0-9_.-]*")
STAGING_RECEIPT_FIELDS = {
    "schema",
    "source_commit",
    "source_path",
    "source_sha256",
    "staged_path",
    "staged_sha256",
}
TRACKED_SNAPSHOT_RECEIPT_FIELDS = {
    "schema",
    "source_commit",
    "source_tree",
    "source_relative_path",
    "source_sha256",
    "snapshot_path",
    "snapshot_sha256",
}


class CanonicalRouteStagingError(RuntimeError):
    pass


def _git(worktree: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(worktree), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout if binary else result.stdout.decode().strip()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _md5_bytes(payload: bytes) -> str:
    return hashlib.md5(payload, usedforsecurity=False).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def git_output(worktree: Path, *args: str, binary: bool = False) -> str | bytes:
    """Expose the shared exact Git read primitive to evidence consumers."""

    return _git(worktree, *args, binary=binary)


def is_within(path: Path, parent: Path) -> bool:
    return _is_within(path, parent)


def file_sha_rows(root: Path, names: list[str]) -> list[dict[str, str]]:
    return [
        {"path": name, "sha256": _sha256_file(root / name)}
        for name in sorted(names)
    ]


def copy_exact_file(source: Path, destination: Path) -> None:
    atomic_write_new(destination, source.read_bytes())
    if _sha256_file(source) != _sha256_file(destination):
        destination.unlink(missing_ok=True)
        raise CanonicalRouteStagingError(
            f"copy_hash_mismatch:{destination.name}"
        )


def _stable_regular_file_snapshot(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise CanonicalRouteStagingError(
            "staging_receipt_location_invalid"
        ) from error
    try:
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        finished = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
    except OSError as error:
        raise CanonicalRouteStagingError(
            "staging_receipt_path_replaced"
        ) from error
    finally:
        os.close(descriptor)
    identity_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if (
        not stat.S_ISREG(opened.st_mode)
        or any(getattr(opened, field) != getattr(finished, field)
               for field in identity_fields)
        or any(getattr(finished, field) != getattr(current, field)
               for field in identity_fields)
    ):
        raise CanonicalRouteStagingError("staging_receipt_path_replaced")
    return b"".join(chunks)


def _verified_receipt_snapshot(
    *, worktree: Path, receipt_bytes: bytes, expected_receipt_sha256: str,
    dvc_stage_name: str, output_relative_member: str,
) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(expected_receipt_sha256) or (
        hashlib.sha256(receipt_bytes).hexdigest() != expected_receipt_sha256
    ):
        raise CanonicalRouteStagingError("staging_receipt_sha256_mismatch")
    try:
        receipt = json.loads(receipt_bytes)
    except json.JSONDecodeError as error:
        raise CanonicalRouteStagingError("staging_receipt_invalid") from error
    if (
        not isinstance(receipt, dict)
        or set(receipt) != STAGING_RECEIPT_FIELDS
        or receipt.get("schema") != STAGING_RECEIPT_SCHEMA
        or receipt_bytes != _canonical_json_bytes(receipt)
    ):
        raise CanonicalRouteStagingError("staging_receipt_invalid")

    head, _tree = _clean_source_identity(worktree)
    if receipt.get("source_commit") != head:
        raise CanonicalRouteStagingError("staging_receipt_source_commit_mismatch")
    source = Path(str(receipt.get("source_path") or ""))
    staged = Path(str(receipt.get("staged_path") or ""))
    if (
        Path(os.path.abspath(source)) != source
        or source.resolve() != source
        or not source.is_file()
        or not _is_within(source, worktree)
        or Path(os.path.abspath(staged)) != staged
        or staged.resolve() != staged
        or staged.is_symlink()
        or not staged.is_file()
        or _is_within(staged, worktree)
    ):
        raise CanonicalRouteStagingError("staging_receipt_catalog_path_invalid")
    source_sha = str(receipt.get("source_sha256") or "")
    staged_sha = str(receipt.get("staged_sha256") or "")
    if (
        not SHA256_RE.fullmatch(source_sha)
        or staged_sha != source_sha
        or _sha256_file(source) != source_sha
        or _sha256_file(staged) != staged_sha
    ):
        raise CanonicalRouteStagingError("staging_receipt_catalog_hash_mismatch")
    member_md5 = _locked_member_md5(
        worktree=worktree,
        source=source,
        lock=_head_dvc_lock(worktree),
        dvc_stage_name=dvc_stage_name,
        output_relative_member=output_relative_member,
    )
    if _md5_bytes(source.read_bytes()) != member_md5:
        raise CanonicalRouteStagingError("source_route_dvc_member_hash_mismatch")
    return {
        **receipt,
        "receipt_snapshot_base64": base64.b64encode(receipt_bytes).decode("ascii"),
        "receipt_sha256": expected_receipt_sha256,
        "dvc_stage_name": dvc_stage_name,
        "output_relative_member": output_relative_member,
    }


def atomic_write_new(destination: Path, payload: bytes) -> None:
    """Publish complete bytes without following or replacing a destination."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    except FileExistsError as error:
        raise CanonicalRouteStagingError(
            f"copy_destination_exists:{destination.name}"
        ) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _clean_source_identity(worktree: Path) -> tuple[str, str]:
    head = str(_git(worktree, "rev-parse", "HEAD"))
    tree = str(_git(worktree, "rev-parse", "HEAD^{tree}"))
    porcelain = _git(worktree, "status", "--porcelain=v1", "-z", binary=True)
    if porcelain:
        raise CanonicalRouteStagingError("source_worktree_dirty")
    return head, tree


def _head_dvc_lock(worktree: Path) -> dict[str, Any]:
    try:
        for authority in ("dvc.yaml", "dvc.lock"):
            committed = _git(
                worktree, "show", f"HEAD:{authority}", binary=True
            )
            if (worktree / authority).read_bytes() != committed:
                raise CanonicalRouteStagingError(
                    "dvc_authority_commit_mismatch"
                )
        value = yaml.safe_load(
            (worktree / "dvc.lock").read_text(encoding="utf-8")
        )
    except CanonicalRouteStagingError:
        raise
    except (OSError, subprocess.SubprocessError, yaml.YAMLError) as error:
        raise CanonicalRouteStagingError(
            "source_route_dvc_authority_invalid"
        ) from error
    if not isinstance(value, dict):
        raise CanonicalRouteStagingError("source_route_dvc_authority_invalid")
    return value


def _locked_member_md5(
    *, worktree: Path, source: Path, lock: dict[str, Any],
    dvc_stage_name: str, output_relative_member: str,
) -> str:
    try:
        outputs = lock["stages"][dvc_stage_name]["outs"]
        relative = source.relative_to(worktree).as_posix()
        owners = [
            row for row in outputs
            if relative
            == f'{str(row["path"]).rstrip("/")}/{output_relative_member}'
        ]
        if (
            len(owners) != 1
            or not str(owners[0].get("md5", "")).endswith(".dir")
        ):
            raise CanonicalRouteStagingError(
                "source_route_dvc_output_identity_invalid"
            )
        digest = str(owners[0]["md5"])
        cache = worktree / ".dvc/cache/files/md5" / digest[:2] / digest[2:]
        cache_bytes = cache.read_bytes()
        if _md5_bytes(cache_bytes) != digest[:-4]:
            raise CanonicalRouteStagingError(
                "dvc_directory_manifest_hash_mismatch"
            )
        manifest = json.loads(cache_bytes)
        members = [
            row for row in manifest
            if isinstance(row, dict)
            and row.get("relpath") == output_relative_member
        ]
        if len(members) != 1 or not MD5_RE.fullmatch(
            str(members[0].get("md5", ""))
        ):
            raise CanonicalRouteStagingError(
                "source_route_dvc_member_identity_invalid"
            )
        return str(members[0]["md5"])
    except CanonicalRouteStagingError:
        raise
    except (
        AttributeError,
        json.JSONDecodeError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise CanonicalRouteStagingError(
            "source_route_dvc_authority_invalid"
        ) from error


def _copy_exact(source: Path, destination: Path) -> None:
    atomic_write_new(destination, source.read_bytes())
    if _sha256_file(source) != _sha256_file(destination):
        destination.unlink(missing_ok=True)
        raise CanonicalRouteStagingError(
            f"copy_hash_mismatch:{destination.name}"
        )


def verify_staging_receipt(
    *, worktree: Path, receipt_path: Path, expected_receipt_sha256: str,
    dvc_stage_name: str = "validation_scenarios",
    output_relative_member: str = "validation_routes.jsonl",
) -> dict[str, Any]:
    worktree = worktree.resolve()
    receipt_lexical = Path(os.path.abspath(receipt_path))
    receipt_path = receipt_path.resolve()
    if (
        receipt_lexical != receipt_path
        or receipt_path.is_symlink()
        or not receipt_path.is_file()
        or _is_within(receipt_path, worktree)
    ):
        raise CanonicalRouteStagingError("staging_receipt_location_invalid")
    verified = _verified_receipt_snapshot(
        worktree=worktree,
        receipt_bytes=_stable_regular_file_snapshot(receipt_path),
        expected_receipt_sha256=expected_receipt_sha256,
        dvc_stage_name=dvc_stage_name,
        output_relative_member=output_relative_member,
    )
    return {**verified, "receipt_locator": str(receipt_path)}


def verify_staging_receipt_snapshot(
    *, worktree: Path, receipt_snapshot_base64: str,
    expected_receipt_sha256: str,
    dvc_stage_name: str = "validation_scenarios",
    output_relative_member: str = "validation_routes.jsonl",
) -> dict[str, Any]:
    try:
        receipt_bytes = base64.b64decode(
            receipt_snapshot_base64.encode("ascii"), validate=True
        )
    except (UnicodeEncodeError, ValueError, binascii.Error) as error:
        raise CanonicalRouteStagingError(
            "staging_receipt_snapshot_invalid"
        ) from error
    return _verified_receipt_snapshot(
        worktree=worktree.resolve(),
        receipt_bytes=receipt_bytes,
        expected_receipt_sha256=expected_receipt_sha256,
        dvc_stage_name=dvc_stage_name,
        output_relative_member=output_relative_member,
    )


def stage_canonical_route(
    *, worktree: Path, source_route: Path, expected_sha256: str,
    external_run_root: Path, dvc_stage_name: str = "validation_scenarios",
    output_relative_member: str = "validation_routes.jsonl",
) -> dict[str, Any]:
    worktree = worktree.resolve()
    source = source_route.resolve()
    root = external_run_root.resolve()
    if (
        Path(os.path.abspath(source_route)) != source
        or not source.is_file()
        or not _is_within(source, worktree)
    ):
        raise CanonicalRouteStagingError("source_route_location_invalid")
    if (
        Path(os.path.abspath(external_run_root)) != root
        or not root.is_dir()
        or _is_within(root, worktree)
    ):
        raise CanonicalRouteStagingError("external_staging_root_invalid")

    head, _tree = _clean_source_identity(worktree)
    member_md5 = _locked_member_md5(
        worktree=worktree,
        source=source,
        lock=_head_dvc_lock(worktree),
        dvc_stage_name=dvc_stage_name,
        output_relative_member=output_relative_member,
    )
    source_bytes = source.read_bytes()
    if _md5_bytes(source_bytes) != member_md5:
        raise CanonicalRouteStagingError(
            "source_route_dvc_member_hash_mismatch"
        )
    if (
        not SHA256_RE.fullmatch(expected_sha256)
        or _sha256_file(source) != expected_sha256
    ):
        raise CanonicalRouteStagingError("source_route_sha256_mismatch")

    name = f"{source.stem}-{expected_sha256}{source.suffix}"
    destination = root / name
    receipt_path = root / f"{name}.receipt.json"
    if (
        destination.exists()
        or destination.is_symlink()
        or receipt_path.exists()
        or receipt_path.is_symlink()
    ):
        raise CanonicalRouteStagingError(
            "external_staging_destination_conflict"
        )
    _copy_exact(source, destination)
    if (
        _sha256_file(destination) != expected_sha256
        or _sha256_file(source) != expected_sha256
    ):
        destination.unlink(missing_ok=True)
        raise CanonicalRouteStagingError("external_staging_copy_hash_mismatch")

    receipt = {
        "schema": STAGING_RECEIPT_SCHEMA,
        "source_commit": head,
        "source_path": str(source),
        "source_sha256": expected_sha256,
        "staged_path": str(destination),
        "staged_sha256": expected_sha256,
    }
    receipt_bytes = _canonical_json_bytes(receipt)
    atomic_write_new(receipt_path, receipt_bytes)
    return {
        **receipt,
        "receipt_path": str(receipt_path),
        "receipt_sha256": _sha256_file(receipt_path),
    }


def _tracked_source_snapshot(
    worktree: Path, source: Path,
) -> tuple[str, str, str, bytes]:
    commit, tree = _clean_source_identity(worktree)
    try:
        relative = source.relative_to(worktree).as_posix()
        _git(worktree, "ls-files", "--error-unmatch", relative)
        committed = _git(worktree, "show", f"HEAD:{relative}", binary=True)
        source_bytes = source.read_bytes()
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise CanonicalRouteStagingError(
            "tracked_snapshot_source_invalid"
        ) from error
    if source_bytes != committed:
        raise CanonicalRouteStagingError("tracked_snapshot_source_commit_mismatch")
    return commit, tree, relative, source_bytes


def stage_tracked_snapshot(
    *, worktree: Path, source_path: Path, expected_sha256: str,
    external_run_root: Path, artifact_label: str,
) -> dict[str, Any]:
    worktree = worktree.resolve()
    source = source_path.resolve()
    root = external_run_root.resolve()
    if (
        Path(os.path.abspath(source_path)) != source
        or source_path.is_symlink()
        or not source.is_file()
        or not _is_within(source, worktree)
    ):
        raise CanonicalRouteStagingError("tracked_snapshot_source_invalid")
    if (
        Path(os.path.abspath(external_run_root)) != root
        or external_run_root.is_symlink()
        or not root.is_dir()
        or _is_within(root, worktree)
    ):
        raise CanonicalRouteStagingError("tracked_snapshot_root_invalid")
    if not ARTIFACT_LABEL_RE.fullmatch(artifact_label):
        raise CanonicalRouteStagingError("tracked_snapshot_label_invalid")

    commit, tree, relative, source_bytes = _tracked_source_snapshot(
        worktree, source
    )
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    if not SHA256_RE.fullmatch(expected_sha256) or source_sha != expected_sha256:
        raise CanonicalRouteStagingError("tracked_snapshot_source_sha256_mismatch")
    suffix = source.suffix or ".bin"
    snapshot = root / f"{artifact_label}-{source_sha}{suffix}"
    receipt_path = root / f"{artifact_label}-{source_sha}.receipt.json"
    if (
        snapshot.exists()
        or snapshot.is_symlink()
        or receipt_path.exists()
        or receipt_path.is_symlink()
    ):
        raise CanonicalRouteStagingError("tracked_snapshot_destination_conflict")
    try:
        atomic_write_new(snapshot, source_bytes)
    except CanonicalRouteStagingError as error:
        raise CanonicalRouteStagingError(
            "tracked_snapshot_destination_conflict"
        ) from error
    if snapshot.read_bytes() != source_bytes:
        snapshot.unlink(missing_ok=True)
        raise CanonicalRouteStagingError("tracked_snapshot_copy_mismatch")
    repeated = _tracked_source_snapshot(worktree, source)
    if repeated != (commit, tree, relative, source_bytes):
        snapshot.unlink(missing_ok=True)
        raise CanonicalRouteStagingError("tracked_snapshot_source_mutated")

    receipt = {
        "schema": TRACKED_SNAPSHOT_RECEIPT_SCHEMA,
        "source_commit": commit,
        "source_tree": tree,
        "source_relative_path": relative,
        "source_sha256": source_sha,
        "snapshot_path": str(snapshot),
        "snapshot_sha256": source_sha,
    }
    receipt_bytes = _canonical_json_bytes(receipt)
    try:
        atomic_write_new(receipt_path, receipt_bytes)
    except CanonicalRouteStagingError as error:
        snapshot.unlink(missing_ok=True)
        raise CanonicalRouteStagingError(
            "tracked_snapshot_destination_conflict"
        ) from error
    return {
        **receipt,
        "receipt_path": str(receipt_path),
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
    }


def verify_tracked_snapshot(
    *, worktree: Path, receipt_path: Path, expected_receipt_sha256: str,
) -> dict[str, Any]:
    worktree = worktree.resolve()
    lexical = Path(os.path.abspath(receipt_path))
    receipt_path = receipt_path.resolve()
    if (
        lexical != receipt_path
        or receipt_path.is_symlink()
        or not receipt_path.is_file()
        or _is_within(receipt_path, worktree)
    ):
        raise CanonicalRouteStagingError(
            "tracked_snapshot_receipt_location_invalid"
        )
    receipt_bytes = _stable_regular_file_snapshot(receipt_path)
    if (
        not SHA256_RE.fullmatch(expected_receipt_sha256)
        or hashlib.sha256(receipt_bytes).hexdigest() != expected_receipt_sha256
    ):
        raise CanonicalRouteStagingError("tracked_snapshot_receipt_sha256_mismatch")
    try:
        receipt = json.loads(receipt_bytes)
    except json.JSONDecodeError as error:
        raise CanonicalRouteStagingError("tracked_snapshot_receipt_invalid") from error
    if (
        not isinstance(receipt, dict)
        or set(receipt) != TRACKED_SNAPSHOT_RECEIPT_FIELDS
        or receipt.get("schema") != TRACKED_SNAPSHOT_RECEIPT_SCHEMA
        or receipt_bytes != _canonical_json_bytes(receipt)
    ):
        raise CanonicalRouteStagingError("tracked_snapshot_receipt_invalid")

    commit, tree = _clean_source_identity(worktree)
    relative = str(receipt.get("source_relative_path") or "")
    source = worktree / relative
    if (
        receipt.get("source_commit") != commit
        or receipt.get("source_tree") != tree
        or not relative
        or Path(relative).is_absolute()
        or source.resolve() != source
        or not source.is_file()
        or not _is_within(source, worktree)
    ):
        raise CanonicalRouteStagingError("tracked_snapshot_source_identity_mismatch")
    verified = _tracked_source_snapshot(worktree, source)
    source_bytes = verified[3]
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    snapshot = Path(str(receipt.get("snapshot_path") or ""))
    if (
        Path(os.path.abspath(snapshot)) != snapshot
        or snapshot.resolve() != snapshot
        or snapshot.is_symlink()
        or not snapshot.is_file()
        or _is_within(snapshot, worktree)
    ):
        raise CanonicalRouteStagingError("tracked_snapshot_path_invalid")
    snapshot_bytes = snapshot.read_bytes()
    if (
        verified[:3] != (commit, tree, relative)
        or receipt.get("source_sha256") != source_sha
        or receipt.get("snapshot_sha256") != source_sha
        or hashlib.sha256(snapshot_bytes).hexdigest() != source_sha
        or snapshot_bytes != source_bytes
    ):
        raise CanonicalRouteStagingError("tracked_snapshot_binding_mismatch")
    return {
        **receipt,
        "receipt_path": str(receipt_path),
        "receipt_sha256": expected_receipt_sha256,
    }


def verify_derived_runtime_config_snapshot(
    *, worktree: Path, receipt_path: Path, expected_receipt_sha256: str,
    contract_relative_path: str, expected_source_commit: str,
    expected_source_tree: str,
) -> dict[str, Any]:
    """Admit only the byte snapshot authenticated by its derivation receipt."""

    from tools.raid_program.tracked_runtime_config_derivation import (
        RuntimeConfigDerivationError,
        verify_runtime_config_derivation,
    )

    try:
        verified = verify_runtime_config_derivation(
            worktree=worktree, receipt_path=receipt_path,
            expected_receipt_sha256=expected_receipt_sha256,
            contract_relative_path=contract_relative_path,
            expected_source_commit=expected_source_commit,
            expected_source_tree=expected_source_tree,
        )
    except RuntimeConfigDerivationError as error:
        raise CanonicalRouteStagingError(str(error)) from error
    return {
        "schema": "cata_raid_verified_derived_runtime_config_snapshot_v1",
        "contract_id": verified["contract_id"],
        "source_commit": verified["source_commit"],
        "source_tree": verified["source_tree"],
        "snapshot_path": verified["destination"]["path"],
        "snapshot_sha256": verified["output_sha256"],
        "snapshot_length": verified["output_length"],
        "snapshot_bytes_base64": verified["output_snapshot_base64"],
        "derivation_receipt_path": verified["receipt_path"],
        "derivation_receipt_sha256": verified["receipt_sha256"],
    }
