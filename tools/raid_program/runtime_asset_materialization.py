from __future__ import annotations

import argparse
import configparser
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
from typing import Any, Callable, Mapping, Sequence

import yaml

from tools.raid_program.runtime_asset_safe_io import (
    SafePathError,
    absolute_path,
    read_regular_no_follow,
    require_directory_no_follow,
    walk_inventory_no_follow,
)


RECEIPT_SCHEMA = "cata_runtime_asset_verified_materialization_receipt_v1"
PROVENANCE_KIND = "verified_materialization"
ARCHIVE_FORMAT = "posix-tar-v1"
REQUIREMENT_KEYS = {
    "kind", "root", "path", "receipt_sha256",
    "historical_extraction_origin", "inventory_authority_sha256",
    "archive_sha256", "dvc_content_address", "creation_command_inputs",
}


class MaterializationError(ValueError):
    pass


@dataclass(frozen=True)
class DvcTransportRequest:
    archive_path: Path
    dvc_workspace: Path
    pointer_path: Path
    reconstruction_root: Path
    dvc_command: tuple[str, ...]


@dataclass(frozen=True)
class DvcTransportResult:
    pointer_path: Path
    downloaded_archive_path: Path
    commands: tuple[dict[str, Any], ...]
    isolated_cache_path: Path


DvcTransport = Callable[[DvcTransportRequest], DvcTransportResult]
HEX64_RE = re.compile(r"[0-9a-f]{64}")
MD5_RE = re.compile(r"[0-9a-f]{32}")


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _inventory(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = [dict(row) for row in sorted(records, key=lambda row: str(row["path"]))]
    files = [row for row in normalized if row.get("type") == "file"]
    directories = [row for row in normalized if row.get("type") == "directory"]
    return {
        "entry_count": len(normalized),
        "file_count": len(files),
        "directory_count": len(directories),
        "size_bytes": sum(int(row["size_bytes"]) for row in files),
        "path_set_sha256": _canonical_sha256([row["path"] for row in normalized]),
        "inventory_sha256": _canonical_sha256(normalized),
    }


def _relative_if_within(path: Path, root: Path) -> str | None:
    try:
        relative = absolute_path(path).relative_to(absolute_path(root)).as_posix()
    except ValueError:
        return None
    if relative == "." or not relative:
        raise MaterializationError("materialization_output_cannot_replace_data_root")
    return relative


def _read_authority(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        payload, _stat = read_regular_no_follow(path)
        authority = json.loads(payload.decode("utf-8"))
    except (SafePathError, OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MaterializationError(f"inventory_authority_invalid:{error}") from error
    if not isinstance(authority, dict) or authority.get("schema") != (
        "cata_runtime_asset_native_data_inventory_v1"
    ):
        raise MaterializationError("inventory_authority_schema_invalid")
    records = authority.get("records")
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise MaterializationError("inventory_authority_records_invalid")
    from tools.raid_program.runtime_asset_closure import _validate_inventory_records
    try:
        records = _validate_inventory_records(records)
    except ValueError as error:
        raise MaterializationError(f"inventory_authority_records_invalid:{error}") from error
    if authority.get("record_inventory") != _inventory(records):
        raise MaterializationError("inventory_authority_digest_invalid")
    authority["records"] = records
    return authority, payload


def _stream_hashes(path: Path) -> tuple[str, str, os.stat_result]:
    """Hash a large regular file without loading it into memory."""

    path = absolute_path(path)
    parent_before = require_directory_no_follow(path.parent)
    parent_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(path.parent, parent_flags)
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path.name, flags, dir_fd=parent_fd)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise MaterializationError(f"regular_file_invalid:{path}:type")
        sha256 = hashlib.sha256()
        md5 = hashlib.md5(usedforsecurity=False)
        while chunk := os.read(descriptor, 1024 * 1024):
            sha256.update(chunk)
            md5.update(chunk)
        after = os.fstat(descriptor)
        linked = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns,
        )
        if identity(before) != identity(after) or identity(after) != identity(linked):
            raise MaterializationError(f"regular_file_drift:{path}")
        parent_after = require_directory_no_follow(path.parent)
        if (
            parent_before.st_dev, parent_before.st_ino, parent_before.st_mtime_ns,
            parent_before.st_ctime_ns,
        ) != (
            parent_after.st_dev, parent_after.st_ino, parent_after.st_mtime_ns,
            parent_after.st_ctime_ns,
        ):
            raise MaterializationError(f"regular_file_drift:{path.parent}")
        return sha256.hexdigest(), md5.hexdigest(), after
    except OSError as error:
        raise MaterializationError(f"regular_file_invalid:{path}:{error}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_fd)


def _open_exclusive(path: Path, mode: int = 0o600) -> io.BufferedWriter:
    path = absolute_path(path)
    require_directory_no_follow(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, mode)
    return os.fdopen(descriptor, "wb")


def _write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with _open_exclusive(path) as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())


def _archive_data_dir(
    *, data_dir: Path, archive_path: Path, excluded_paths: Sequence[str],
    expected_records: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    before = walk_inventory_no_follow(
        data_dir, ".", include_directories=True, excluded_paths=excluded_paths,
    )
    if before != [dict(row) for row in expected_records]:
        raise MaterializationError("source_inventory_authority_mismatch")

    archive_path = absolute_path(archive_path)
    with _open_exclusive(archive_path) as raw_archive:
        with tarfile.open(fileobj=raw_archive, mode="w") as archive:
            for record in before:
                relative = str(record["path"])
                member = tarfile.TarInfo(relative)
                member.mode = int(str(record["mode"]), 8)
                member.uid = 0
                member.gid = 0
                member.uname = ""
                member.gname = ""
                member.mtime = 0
                if record["type"] == "directory":
                    member.type = tarfile.DIRTYPE
                    member.size = 0
                    archive.addfile(member)
                    continue
                try:
                    payload, observed = read_regular_no_follow(data_dir / relative)
                except (SafePathError, OSError) as error:
                    raise MaterializationError(f"source_drift:{relative}:{error}") from error
                if (
                    observed.st_size != record["size_bytes"]
                    or f"{stat.S_IMODE(observed.st_mode):04o}" != record["mode"]
                    or hashlib.sha256(payload).hexdigest() != record["sha256"]
                ):
                    raise MaterializationError(f"source_drift:{relative}")
                member.type = tarfile.REGTYPE
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
        raw_archive.flush()
        os.fsync(raw_archive.fileno())

    after = walk_inventory_no_follow(
        data_dir, ".", include_directories=True, excluded_paths=excluded_paths,
    )
    if after != before:
        raise MaterializationError("source_drift:inventory_changed_during_archive")
    archive_sha256, archive_md5, archive_stat = _stream_hashes(archive_path)
    return before, {
        "format": ARCHIVE_FORMAT,
        "sha256": archive_sha256,
        "md5": archive_md5,
        "size_bytes": archive_stat.st_size,
        "member_count": len(before),
        "source_inventory_sha256": _inventory(before)["inventory_sha256"],
    }


def _safe_member_name(name: str) -> str:
    pure = PurePosixPath(name)
    if (
        not name or name == "." or pure.is_absolute() or ".." in pure.parts
        or "." in pure.parts or "\\" in name or pure.as_posix() != name
    ):
        raise MaterializationError(f"archive_member_path_invalid:{name}")
    return name


def _extract_and_verify_archive(
    *, archive_path: Path, output_dir: Path,
    expected_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    output_dir = absolute_path(output_dir)
    if output_dir.exists():
        raise MaterializationError("reconstructed_data_dir_not_absent")
    output_dir.mkdir(parents=True, mode=0o700)
    require_directory_no_follow(output_dir)
    expected = {str(row["path"]): dict(row) for row in expected_records}
    seen: set[str] = set()
    directory_modes: list[tuple[Path, int]] = []
    try:
        with tarfile.open(archive_path, mode="r:") as archive:
            for member in archive:
                relative = _safe_member_name(member.name)
                if relative in seen:
                    raise MaterializationError(f"archive_member_duplicate:{relative}")
                seen.add(relative)
                record = expected.get(relative)
                if record is None:
                    raise MaterializationError(f"archive_member_unexpected:{relative}")
                expected_type = record.get("type")
                if member.issym() or member.islnk() or not (
                    member.isfile() or member.isdir()
                ):
                    raise MaterializationError(f"archive_member_type_invalid:{relative}")
                if member.isdir() != (expected_type == "directory"):
                    raise MaterializationError(f"archive_member_type_mismatch:{relative}")
                if f"{member.mode & 0o7777:04o}" != record.get("mode"):
                    raise MaterializationError(f"archive_member_mode_mismatch:{relative}")
                target = output_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if member.isdir():
                    target.mkdir(exist_ok=False, mode=0o700)
                    directory_modes.append((target, member.mode & 0o7777))
                    continue
                if member.size != record.get("size_bytes"):
                    raise MaterializationError(f"archive_member_size_mismatch:{relative}")
                source = archive.extractfile(member)
                if source is None:
                    raise MaterializationError(f"archive_member_payload_missing:{relative}")
                digest = hashlib.sha256()
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(target, flags, member.mode & 0o7777)
                try:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        view = memoryview(chunk)
                        while view:
                            written = os.write(descriptor, view)
                            if written <= 0:
                                raise MaterializationError(
                                    f"archive_member_write_failed:{relative}"
                                )
                            view = view[written:]
                    os.fchmod(descriptor, member.mode & 0o7777)
                finally:
                    os.close(descriptor)
                if digest.hexdigest() != record.get("sha256"):
                    raise MaterializationError(f"archive_member_hash_mismatch:{relative}")
        missing = sorted(set(expected) - seen)
        if missing:
            raise MaterializationError(f"archive_member_missing:{missing[0]}")
        for directory, mode in reversed(directory_modes):
            directory.chmod(mode)
        observed = walk_inventory_no_follow(output_dir, ".", include_directories=True)
        if observed != [dict(row) for row in expected_records]:
            raise MaterializationError("reconstructed_inventory_mismatch")
        return _inventory(observed)
    except (tarfile.TarError, OSError, SafePathError) as error:
        raise MaterializationError(f"archive_invalid:{error}") from error


def _command_record(argv: Sequence[str], cwd: Path, **environment: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "argv": [str(value) for value in argv],
        "cwd": str(absolute_path(cwd)),
    }
    if environment:
        result["environment"] = dict(sorted(environment.items()))
    return result


def _run_quiet(argv: Sequence[str], *, cwd: Path, environment: Mapping[str, str] | None = None) -> None:
    process_environment = os.environ.copy()
    if environment:
        process_environment.update(environment)
    try:
        result = subprocess.run(
            list(argv), cwd=cwd, env=process_environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, check=False, timeout=1800,
        )
    except subprocess.TimeoutExpired as error:
        raise MaterializationError(
            f"dvc_command_timeout:{Path(argv[0]).name}:1800"
        ) from error
    if result.returncode != 0:
        raise MaterializationError(
            f"dvc_command_failed:{Path(argv[0]).name}:{result.returncode}"
        )


def _copy_dvc_configuration(source: Path, destination: Path, cache_dir: Path) -> None:
    source = absolute_path(source)
    destination.mkdir(parents=True, mode=0o700)
    require_directory_no_follow(destination)
    parser = configparser.RawConfigParser()
    parser.optionxform = str
    for name in ("config", "config.local"):
        candidate = source / name
        if not candidate.exists():
            continue
        try:
            payload, _stat = read_regular_no_follow(candidate)
            parser.read_string(payload.decode("utf-8"))
        except (SafePathError, OSError, UnicodeError, configparser.Error) as error:
            raise MaterializationError(f"dvc_config_invalid:{name}:{error}") from error
    if not parser.has_section("cache"):
        parser.add_section("cache")
    parser.set("cache", "dir", str(absolute_path(cache_dir)))
    if not parser.has_section("core"):
        parser.add_section("core")
    parser.set("core", "no_scm", "true")
    target = destination / "config"
    with _open_exclusive(target, mode=0o600) as output:
        text = io.TextIOWrapper(output, encoding="utf-8", write_through=True)
        parser.write(text)
        text.flush()
        os.fsync(output.fileno())
        text.detach()


def _dvc_pointer(path: Path) -> tuple[dict[str, Any], str]:
    try:
        payload, _stat = read_regular_no_follow(path)
        document = yaml.safe_load(payload)
    except (SafePathError, OSError, yaml.YAMLError) as error:
        raise MaterializationError(f"dvc_pointer_invalid:{error}") from error
    outs = document.get("outs") if isinstance(document, dict) else None
    if not isinstance(outs, list) or len(outs) != 1 or not isinstance(outs[0], dict):
        raise MaterializationError("dvc_pointer_single_output_required")
    output = dict(outs[0])
    if set(output) != {"md5", "size", "hash", "path"}:
        raise MaterializationError("dvc_pointer_fields_invalid")
    if (
        output.get("hash") != "md5"
        or not isinstance(output.get("md5"), str)
        or not MD5_RE.fullmatch(output["md5"])
    ):
        raise MaterializationError("dvc_pointer_content_address_invalid")
    if not isinstance(output.get("size"), int) or output["size"] < 0:
        raise MaterializationError("dvc_pointer_size_invalid")
    _safe_member_name(str(output.get("path") or ""))
    return output, hashlib.sha256(payload).hexdigest()


def publish_and_reconstruct_dvc(request: DvcTransportRequest) -> DvcTransportResult:
    workspace = absolute_path(request.dvc_workspace)
    archive = absolute_path(request.archive_path)
    pointer = absolute_path(request.pointer_path)
    reconstruction = absolute_path(request.reconstruction_root)
    if not reconstruction.is_dir():
        raise MaterializationError("reconstruction_root_not_prepared")
    try:
        archive_relative = archive.relative_to(workspace)
        pointer_relative = pointer.relative_to(workspace)
    except ValueError as error:
        raise MaterializationError("dvc_paths_outside_workspace") from error
    commands: list[dict[str, Any]] = []
    add = (*request.dvc_command, "add", "-f", archive_relative.as_posix())
    commands.append(_command_record(add, workspace))
    _run_quiet(add, cwd=workspace)
    if pointer != Path(str(archive) + ".dvc"):
        raise MaterializationError("dvc_pointer_path_invalid")
    _dvc_pointer(pointer)
    push = (*request.dvc_command, "push", pointer_relative.as_posix())
    commands.append(_command_record(push, workspace))
    _run_quiet(push, cwd=workspace)

    isolated = reconstruction / "workspace"
    cache = reconstruction / "cache"
    site_cache = reconstruction / "site-cache"
    if not cache.is_dir() or any(cache.iterdir()):
        raise MaterializationError("reconstruction_cache_not_empty")
    isolated.mkdir(parents=True, mode=0o700)
    site_cache.mkdir(mode=0o700)
    _copy_dvc_configuration(workspace / ".dvc", isolated / ".dvc", cache)
    isolated_pointer = isolated / pointer_relative
    isolated_pointer.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    pointer_payload, _stat = read_regular_no_follow(pointer)
    with _open_exclusive(isolated_pointer, mode=0o600) as output:
        output.write(pointer_payload)
    environment = {"DVC_SITE_CACHE_DIR": str(site_cache)}
    pull = (*request.dvc_command, "pull", pointer_relative.as_posix())
    commands.append(_command_record(pull, isolated, **environment))
    _run_quiet(pull, cwd=isolated, environment=environment)
    pointer_output, _sha = _dvc_pointer(isolated_pointer)
    downloaded = isolated_pointer.parent / str(pointer_output["path"])
    _stream_hashes(downloaded)
    return DvcTransportResult(
        pointer_path=pointer,
        downloaded_archive_path=downloaded,
        commands=tuple(commands),
        isolated_cache_path=cache,
    )


def validate_materialization_receipt(payload: Mapping[str, Any]) -> None:
    expected = {
        "schema", "kind", "historical_extraction_origin",
        "inventory_authority_sha256", "canonical_audit_inventory_sha256",
        "source_inventory", "archive", "dvc", "creation_command_inputs",
        "remote_reconstruction",
    }
    if set(payload) != expected or payload.get("schema") != RECEIPT_SCHEMA:
        raise MaterializationError("materialization_receipt_fields_invalid")
    if payload.get("kind") != PROVENANCE_KIND:
        raise MaterializationError("materialization_receipt_kind_invalid")
    if payload.get("historical_extraction_origin") != "unknown":
        raise MaterializationError("historical_extraction_origin_invalid")
    for field in ("inventory_authority_sha256", "canonical_audit_inventory_sha256"):
        value = payload.get(field)
        if not isinstance(value, str) or not HEX64_RE.fullmatch(value):
            raise MaterializationError(f"materialization_receipt_{field}_invalid")
    inventory_keys = {
        "entry_count", "file_count", "directory_count", "size_bytes",
        "path_set_sha256", "inventory_sha256",
    }
    if not isinstance(payload.get("source_inventory"), dict) or set(
        payload["source_inventory"]
    ) != inventory_keys:
        raise MaterializationError("materialization_source_inventory_invalid")
    source_inventory = payload["source_inventory"]
    if (
        any(
            not isinstance(source_inventory.get(field), int)
            or source_inventory[field] < 0
            for field in ("entry_count", "file_count", "directory_count", "size_bytes")
        )
        or source_inventory["entry_count"]
        != source_inventory["file_count"] + source_inventory["directory_count"]
        or any(
            not isinstance(source_inventory.get(field), str)
            or not HEX64_RE.fullmatch(source_inventory[field])
            for field in ("path_set_sha256", "inventory_sha256")
        )
    ):
        raise MaterializationError("materialization_source_inventory_invalid")
    archive = payload.get("archive")
    if not isinstance(archive, dict) or set(archive) != {
        "format", "sha256", "md5", "size_bytes", "member_count",
        "source_inventory_sha256",
    } or archive.get("format") != ARCHIVE_FORMAT:
        raise MaterializationError("materialization_archive_invalid")
    if (
        not isinstance(archive.get("sha256"), str)
        or not HEX64_RE.fullmatch(archive["sha256"])
        or not isinstance(archive.get("md5"), str)
        or not MD5_RE.fullmatch(archive["md5"])
        or not isinstance(archive.get("size_bytes"), int)
        or archive["size_bytes"] < 0
        or not isinstance(archive.get("member_count"), int)
        or archive["member_count"] < 0
    ):
        raise MaterializationError("materialization_archive_identity_invalid")
    if (
        archive.get("member_count") != source_inventory["entry_count"]
        or archive.get("source_inventory_sha256")
        != source_inventory["inventory_sha256"]
    ):
        raise MaterializationError("materialization_archive_inventory_disagree")
    dvc = payload.get("dvc")
    if not isinstance(dvc, dict) or set(dvc) != {
        "pointer_path", "pointer_sha256", "hash", "content_address",
        "size_bytes", "object_count",
    } or dvc.get("hash") != "md5" or dvc.get("object_count") != 1:
        raise MaterializationError("materialization_dvc_identity_invalid")
    if (
        not isinstance(dvc.get("pointer_sha256"), str)
        or not HEX64_RE.fullmatch(dvc["pointer_sha256"])
        or not isinstance(dvc.get("content_address"), str)
        or not MD5_RE.fullmatch(dvc["content_address"])
        or dvc.get("content_address") != archive.get("md5")
        or dvc.get("size_bytes") != archive.get("size_bytes")
    ):
        raise MaterializationError("materialization_dvc_archive_disagree")
    commands = payload.get("creation_command_inputs")
    if not _commands_valid(commands):
        raise MaterializationError("materialization_commands_invalid")
    remote = payload.get("remote_reconstruction")
    if not isinstance(remote, dict) or set(remote) != {
        "transport", "isolated_empty_cache", "downloaded_archive_sha256",
        "reconstructed_inventory", "commands",
    } or remote.get("transport") != "dvc_pull" or remote.get(
        "isolated_empty_cache"
    ) is not True:
        raise MaterializationError("materialization_remote_reconstruction_invalid")
    if not _commands_valid(remote.get("commands")):
        raise MaterializationError("materialization_remote_commands_invalid")
    if remote.get("reconstructed_inventory") != payload.get("source_inventory"):
        raise MaterializationError("materialization_reconstructed_inventory_invalid")
    if remote.get("downloaded_archive_sha256") != archive.get("sha256"):
        raise MaterializationError("materialization_downloaded_archive_invalid")


def validate_materialization_requirement(
    requirement: Mapping[str, Any], receipt: Mapping[str, Any],
    inventory_authority_sha256: str,
) -> None:
    if set(requirement) != REQUIREMENT_KEYS:
        raise MaterializationError("materialization_requirement_fields_invalid")
    if requirement.get("kind") != PROVENANCE_KIND or requirement.get("root") != "dvc-workspace":
        raise MaterializationError("materialization_requirement_kind_invalid")
    if requirement.get("historical_extraction_origin") != "unknown":
        raise MaterializationError("materialization_requirement_origin_invalid")
    for field in ("receipt_sha256", "inventory_authority_sha256", "archive_sha256"):
        if not isinstance(requirement.get(field), str) or not HEX64_RE.fullmatch(requirement[field]):
            raise MaterializationError(f"materialization_requirement_{field}_invalid")
    if not isinstance(requirement.get("dvc_content_address"), str) or not MD5_RE.fullmatch(
        requirement["dvc_content_address"]
    ):
        raise MaterializationError("materialization_requirement_dvc_content_address_invalid")
    if not _commands_valid(requirement.get("creation_command_inputs")):
        raise MaterializationError("materialization_requirement_commands_invalid")
    validate_materialization_receipt(receipt)
    comparisons = {
        "historical_extraction_origin": receipt.get("historical_extraction_origin"),
        "inventory_authority_sha256": receipt.get("inventory_authority_sha256"),
        "archive_sha256": receipt.get("archive", {}).get("sha256"),
        "dvc_content_address": receipt.get("dvc", {}).get("content_address"),
        "creation_command_inputs": receipt.get("creation_command_inputs"),
    }
    for field, observed in comparisons.items():
        if requirement.get(field) != observed:
            raise MaterializationError(f"materialization_requirement_{field}_mismatch")
    if inventory_authority_sha256 != receipt.get("inventory_authority_sha256"):
        raise MaterializationError("materialization_inventory_authority_mismatch")


def verify_current_dvc_pointer(
    receipt: Mapping[str, Any], dvc_workspace: Path,
) -> None:
    pointer_value = receipt.get("dvc", {}).get("pointer_path")
    try:
        pointer_relative = _safe_member_name(str(pointer_value or ""))
        pointer, pointer_sha256 = _dvc_pointer(
            absolute_path(dvc_workspace) / pointer_relative
        )
    except (MaterializationError, SafePathError, OSError) as error:
        raise MaterializationError(f"materialization_dvc_pointer_invalid:{error}") from error
    expected = receipt["dvc"]
    if (
        pointer_sha256 != expected.get("pointer_sha256")
        or pointer.get("md5") != expected.get("content_address")
        or pointer.get("size") != expected.get("size_bytes")
    ):
        raise MaterializationError("materialization_dvc_pointer_mismatch")


def build_materialization_requirement(
    receipt_path: Path, dvc_workspace: Path,
) -> dict[str, Any]:
    try:
        payload, _stat = read_regular_no_follow(receipt_path)
        receipt = json.loads(payload.decode("utf-8"))
    except (SafePathError, OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MaterializationError(f"materialization_receipt_invalid:{error}") from error
    if not isinstance(receipt, dict):
        raise MaterializationError("materialization_receipt_invalid")
    validate_materialization_receipt(receipt)
    workspace = absolute_path(dvc_workspace)
    try:
        relative = absolute_path(receipt_path).relative_to(workspace).as_posix()
    except ValueError as error:
        raise MaterializationError("materialization_receipt_outside_dvc_workspace") from error
    requirement = {
        "kind": PROVENANCE_KIND, "root": "dvc-workspace", "path": relative,
        "receipt_sha256": hashlib.sha256(payload).hexdigest(),
        "historical_extraction_origin": "unknown",
        "inventory_authority_sha256": receipt["inventory_authority_sha256"],
        "archive_sha256": receipt["archive"]["sha256"],
        "dvc_content_address": receipt["dvc"]["content_address"],
        "creation_command_inputs": receipt["creation_command_inputs"],
    }
    validate_materialization_requirement(
        requirement, receipt, receipt["inventory_authority_sha256"],
    )
    verify_current_dvc_pointer(receipt, workspace)
    return requirement


def _commands_valid(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for row in value:
        if not isinstance(row, dict) or set(row) not in (
            {"argv", "cwd"}, {"argv", "cwd", "environment"},
        ):
            return False
        argv = row.get("argv")
        if not isinstance(argv, list) or not argv or not all(
            isinstance(item, str) and item for item in argv
        ):
            return False
        if not isinstance(row.get("cwd"), str) or not Path(row["cwd"]).is_absolute():
            return False
        environment = row.get("environment")
        if environment is not None and (
            not isinstance(environment, dict)
            or not all(
                isinstance(key, str) and isinstance(item, str)
                for key, item in environment.items()
            )
        ):
            return False
    return True


def produce_verified_materialization_receipt(
    *, data_dir: Path, inventory_authority_path: Path, archive_path: Path,
    dvc_workspace: Path, pointer_path: Path, reconstruction_root: Path,
    receipt_path: Path, creation_command_inputs: Sequence[Mapping[str, Any]],
    dvc_command: Sequence[str] = ("dvc",),
    dvc_transport: DvcTransport = publish_and_reconstruct_dvc,
) -> dict[str, Any]:
    data_dir = absolute_path(data_dir)
    archive_path = absolute_path(archive_path)
    receipt_path = absolute_path(receipt_path)
    reconstruction_root = absolute_path(reconstruction_root)
    dvc_workspace = absolute_path(dvc_workspace)
    pointer_path = absolute_path(pointer_path)
    try:
        archive_path.relative_to(dvc_workspace)
        pointer_path.relative_to(dvc_workspace)
        receipt_path.relative_to(dvc_workspace)
    except ValueError as error:
        raise MaterializationError("materialization_outputs_outside_dvc_workspace") from error
    if pointer_path != Path(str(archive_path) + ".dvc"):
        raise MaterializationError("dvc_pointer_path_invalid")
    command_rows = [dict(row) for row in creation_command_inputs]
    if not _commands_valid(command_rows):
        raise MaterializationError("materialization_commands_invalid")
    if not dvc_command or not all(
        isinstance(value, str) and value for value in dvc_command
    ):
        raise MaterializationError("dvc_command_invalid")
    if _relative_if_within(reconstruction_root, data_dir) is not None:
        raise MaterializationError("reconstruction_root_inside_data_dir")
    excluded = [
        relative for relative in (
            _relative_if_within(archive_path, data_dir),
            _relative_if_within(receipt_path, data_dir),
        ) if relative is not None
    ]
    authority, authority_payload = _read_authority(inventory_authority_path)
    expected_records = authority["records"]
    try:
        source_records, archive_identity = _archive_data_dir(
            data_dir=data_dir, archive_path=archive_path,
            excluded_paths=excluded, expected_records=expected_records,
        )
    except (SafePathError, OSError) as error:
        raise MaterializationError(f"source_inventory_invalid:{error}") from error
    if reconstruction_root.exists():
        raise MaterializationError("reconstruction_root_must_not_exist")
    reconstruction_root.mkdir(parents=True, mode=0o700)
    (reconstruction_root / "cache").mkdir(mode=0o700)
    request = DvcTransportRequest(
        archive_path=archive_path,
        dvc_workspace=dvc_workspace,
        pointer_path=pointer_path,
        reconstruction_root=reconstruction_root,
        dvc_command=tuple(str(value) for value in dvc_command),
    )
    result = dvc_transport(request)
    expected_download_root = reconstruction_root / "workspace"
    if absolute_path(result.pointer_path) != absolute_path(pointer_path):
        raise MaterializationError("dvc_transport_pointer_mismatch")
    if absolute_path(result.isolated_cache_path) != reconstruction_root / "cache":
        raise MaterializationError("dvc_transport_cache_mismatch")
    try:
        absolute_path(result.downloaded_archive_path).relative_to(
            expected_download_root
        )
    except ValueError as error:
        raise MaterializationError("dvc_transport_download_outside_workspace") from error
    pointer_identity, pointer_sha256 = _dvc_pointer(result.pointer_path)
    if pointer_identity.get("path") != archive_path.name:
        raise MaterializationError("dvc_pointer_archive_name_mismatch")
    downloaded_sha256, downloaded_md5, downloaded_stat = _stream_hashes(
        result.downloaded_archive_path
    )
    if (
        downloaded_sha256 != archive_identity["sha256"]
        or downloaded_md5 != archive_identity["md5"]
        or pointer_identity["md5"] != archive_identity["md5"]
        or downloaded_stat.st_size != archive_identity["size_bytes"]
        or pointer_identity["size"] != archive_identity["size_bytes"]
    ):
        raise MaterializationError("remote_archive_identity_mismatch")
    if not result.isolated_cache_path.is_dir() or not any(
        result.isolated_cache_path.iterdir()
    ):
        raise MaterializationError("remote_reconstruction_cache_empty_after_pull")
    reconstructed_inventory = _extract_and_verify_archive(
        archive_path=result.downloaded_archive_path,
        output_dir=absolute_path(reconstruction_root) / "reconstructed-data",
        expected_records=expected_records,
    )
    source_after = walk_inventory_no_follow(
        data_dir, ".", include_directories=True, excluded_paths=excluded,
    )
    if source_after != source_records:
        raise MaterializationError("source_drift:inventory_changed_before_receipt")
    source_inventory = _inventory(source_records)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "kind": PROVENANCE_KIND,
        "historical_extraction_origin": "unknown",
        "inventory_authority_sha256": hashlib.sha256(authority_payload).hexdigest(),
        "canonical_audit_inventory_sha256": authority.get(
            "canonical_audit_inventory_sha256"
        ),
        "source_inventory": source_inventory,
        "archive": archive_identity,
        "dvc": {
            "pointer_path": absolute_path(result.pointer_path).relative_to(
                absolute_path(dvc_workspace)
            ).as_posix(),
            "pointer_sha256": pointer_sha256,
            "hash": "md5",
            "content_address": pointer_identity["md5"],
            "size_bytes": pointer_identity["size"],
            "object_count": 1,
        },
        "creation_command_inputs": command_rows,
        "remote_reconstruction": {
            "transport": "dvc_pull",
            "isolated_empty_cache": True,
            "downloaded_archive_sha256": downloaded_sha256,
            "reconstructed_inventory": reconstructed_inventory,
            "commands": [dict(row) for row in result.commands],
        },
    }
    validate_materialization_receipt(receipt)
    _write_json_exclusive(receipt_path, receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish and independently reconstruct a verified runtime asset materialization",
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--inventory-authority", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--dvc-workspace", type=Path, required=True)
    parser.add_argument("--dvc-pointer", type=Path, required=True)
    parser.add_argument("--reconstruction-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    command_inputs = [{
        "argv": [
            sys.executable, "-m",
            "tools.raid_program.runtime_asset_materialization",
            *(argv or sys.argv[1:]),
        ],
        "cwd": str(absolute_path(Path.cwd())),
    }]
    receipt = produce_verified_materialization_receipt(
        data_dir=args.data_dir,
        inventory_authority_path=args.inventory_authority,
        archive_path=args.archive,
        dvc_workspace=args.dvc_workspace,
        pointer_path=args.dvc_pointer,
        reconstruction_root=args.reconstruction_root,
        receipt_path=args.receipt,
        creation_command_inputs=command_inputs,
    )
    receipt_payload, _stat = read_regular_no_follow(args.receipt)
    print(json.dumps({
        "ok": True,
        "receipt_sha256": hashlib.sha256(receipt_payload).hexdigest(),
        "archive_sha256": receipt["archive"]["sha256"],
        "dvc_content_address": receipt["dvc"]["content_address"],
        "native_extraction_provenance": build_materialization_requirement(
            args.receipt, args.dvc_workspace,
        ),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
