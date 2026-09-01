"""Deterministic MySQL header/library identity for queued Trinity builds."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Callable, Mapping


VERSION_SENSITIVE_SOURCES = (
    "src/server/database/Database/DatabaseWorkerPool.cpp",
    "src/server/database/Database/MySQLThreading.cpp",
)
VERSION_CHAIN_OUTPUTS = {
    "database_archive": "build/src/server/database/libdatabase.a",
    "worldserver": "build/src/server/worldserver/worldserver",
}
VERSION_HEADER_CANDIDATES = ("mysql_version.h", "mariadb_version.h")
VERSION_MACROS = ("MYSQL_VERSION_ID", "MARIADB_PACKAGE_VERSION_ID")


class MySQLIdentityError(RuntimeError):
    """The compile-time and runtime MySQL identities cannot be proven equal."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def identity_required(worktree: Path, resource_class: str) -> bool:
    if resource_class not in {"worldserver_build", "integration_build"}:
        return False
    return all((worktree / source).is_file() for source in VERSION_SENSITIVE_SOURCES)


def _version_header(include_dir: Path) -> tuple[Path, str, int]:
    for name in VERSION_HEADER_CANDIDATES:
        path = include_dir / name
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8", errors="strict")
        for macro in VERSION_MACROS:
            match = re.search(
                rf"^\s*#\s*define\s+{re.escape(macro)}\s+(\d+)\b",
                content,
                flags=re.MULTILINE,
            )
            if match:
                return path.resolve(), macro, int(match.group(1))
    raise MySQLIdentityError(
        f"no supported MySQL version header found beneath {include_dir}"
    )


def client_library_version(path: Path) -> tuple[int, str]:
    try:
        library = ctypes.CDLL(str(path))
        get_version = library.mysql_get_client_version
        get_version.argtypes = []
        get_version.restype = ctypes.c_ulong
        get_info = library.mysql_get_client_info
        get_info.argtypes = []
        get_info.restype = ctypes.c_char_p
        raw_info = get_info()
        return int(get_version()), raw_info.decode(errors="replace") if raw_info else ""
    except (AttributeError, OSError) as error:
        raise MySQLIdentityError(
            f"cannot query MySQL client identity from {path}: {error}"
        ) from error


def library_identity(
    configured_path: Path,
    version_reader: Callable[[Path], tuple[int, str]] = client_library_version,
) -> dict[str, object]:
    if not configured_path.is_file():
        raise MySQLIdentityError(
            f"configured MySQL client library is missing: {configured_path}"
        )
    resolved = configured_path.resolve(strict=True)
    before_hash = _sha256_file(resolved)
    version_id, client_info = version_reader(resolved)
    after_hash = _sha256_file(resolved)
    if before_hash != after_hash:
        raise MySQLIdentityError("MySQL client library changed while its identity was read")
    return {
        "configured_path": str(configured_path.resolve(strict=False)),
        "configured_symlink_target": (
            os.readlink(configured_path) if configured_path.is_symlink() else None
        ),
        "resolved_path": str(resolved),
        "sha256": after_hash,
        "size_bytes": resolved.stat().st_size,
        "runtime_version_id": version_id,
        "client_info": client_info,
    }


def build_identity_snapshot(
    worktree: Path,
    cache: Mapping[str, str],
    version_reader: Callable[[Path], tuple[int, str]] = client_library_version,
) -> dict[str, object]:
    raw_include = cache.get("MYSQL_INCLUDE_DIR")
    raw_library = cache.get("MYSQL_LIBRARY")
    if not raw_include or not raw_library:
        raise MySQLIdentityError(
            "CMake cache does not bind MYSQL_INCLUDE_DIR and MYSQL_LIBRARY"
        )
    include_dir = Path(raw_include)
    library_path = Path(raw_library)
    header_path, version_macro, header_version = _version_header(include_dir)
    header = {
        "include_dir": str(include_dir.resolve(strict=True)),
        "path": str(header_path),
        "sha256": _sha256_file(header_path),
        "size_bytes": header_path.stat().st_size,
        "version_macro": version_macro,
        "compile_version_id": header_version,
    }
    library = library_identity(library_path, version_reader)
    if header_version != library["runtime_version_id"]:
        raise MySQLIdentityError(
            "MySQL compile header/runtime library version mismatch: "
            f"{header_version} != {library['runtime_version_id']}"
        )
    core = {"header": header, "runtime_library": library}
    return {**core, "identity_sha256": _identity_sha256(core)}


def _compile_command_output(row: Mapping[str, object]) -> Path | None:
    directory = Path(str(row.get("directory") or ""))
    command = row.get("command")
    try:
        raw_arguments = row.get("arguments")
        arguments = (
            [str(value) for value in raw_arguments]
            if isinstance(raw_arguments, list)
            else shlex.split(command) if isinstance(command, str) else []
        )
        index = arguments.index("-o")
        candidate = Path(arguments[index + 1])
        return candidate if candidate.is_absolute() else directory / candidate
    except (IndexError, ValueError):
        output = row.get("output")
        if isinstance(output, str) and output:
            candidate = Path(output)
            return candidate if candidate.is_absolute() else directory / candidate
        return None


def version_sensitive_objects(worktree: Path) -> list[dict[str, str]]:
    commands_path = worktree / "build/compile_commands.json"
    try:
        commands = json.loads(commands_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MySQLIdentityError(
            f"cannot read generated compile commands {commands_path}: {error}"
        ) from error
    if not isinstance(commands, list):
        raise MySQLIdentityError("generated compile commands are not a JSON array")
    build_root = (worktree / "build").resolve()
    results: list[dict[str, str]] = []
    for source in VERSION_SENSITIVE_SOURCES:
        expected_source = (worktree / source).resolve()
        matches = [
            row for row in commands
            if isinstance(row, dict)
            and Path(str(row.get("file", ""))).resolve() == expected_source
        ]
        if len(matches) != 1:
            raise MySQLIdentityError(
                f"expected one compile command for {source}, found {len(matches)}"
            )
        output = _compile_command_output(matches[0])
        if output is None:
            raise MySQLIdentityError(f"compile command has no output for {source}")
        resolved_output = output.resolve()
        if not resolved_output.is_relative_to(build_root):
            raise MySQLIdentityError(
                f"version-sensitive object escapes the build directory: {resolved_output}"
            )
        results.append(
            {
                "source": source,
                "object": str(resolved_output),
                "dependency": str(Path(str(resolved_output) + ".d")),
            }
        )
    if len({row["object"] for row in results}) != len(VERSION_SENSITIVE_SOURCES):
        raise MySQLIdentityError("version-sensitive sources share one object output")
    return results


def version_chain_outputs(worktree: Path) -> dict[str, str]:
    build_root = (worktree / "build").resolve()
    outputs = {
        name: str((worktree / relative).resolve())
        for name, relative in VERSION_CHAIN_OUTPUTS.items()
    }
    if any(not Path(path).is_relative_to(build_root) for path in outputs.values()):
        raise MySQLIdentityError("MySQL freshness-chain output escapes the build directory")
    return outputs


def _file_state(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    stat = path.stat()
    return {
        "sha256": _sha256_file(path),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def invalidate_version_sensitive_objects(worktree: Path) -> dict[str, object]:
    invalidated_at_unix_ns = time.time_ns()
    rows: list[dict[str, object]] = []
    for binding in version_sensitive_objects(worktree):
        object_path = Path(binding["object"])
        dependency_path = Path(binding["dependency"])
        before = _file_state(object_path)
        dependency_before = _file_state(dependency_path)
        object_path.unlink(missing_ok=True)
        dependency_path.unlink(missing_ok=True)
        if object_path.exists() or dependency_path.exists():
            raise MySQLIdentityError(
                f"failed to invalidate version-sensitive object {object_path}"
            )
        rows.append(
            {
                **binding,
                "before": before,
                "dependency_before": dependency_before,
                "object_removed": before is not None,
                "dependency_removed": dependency_before is not None,
                "absent_before_child": True,
            }
        )
    chain_outputs: dict[str, dict[str, object]] = {}
    for name, raw_path in version_chain_outputs(worktree).items():
        path = Path(raw_path)
        before = _file_state(path)
        path.unlink(missing_ok=True)
        if path.exists():
            raise MySQLIdentityError(
                f"failed to invalidate MySQL freshness-chain output {path}"
            )
        chain_outputs[name] = {
            "path": str(path),
            "before": before,
            "removed": before is not None,
            "absent_before_child": True,
        }
    return {
        "strategy": "unlink_exact_mysql_object_archive_binary_chain_before_child",
        "invalidated_at_unix_ns": invalidated_at_unix_ns,
        "objects": rows,
        "chain_outputs": chain_outputs,
    }


def rebuilt_object_identity(
    invalidation: Mapping[str, object],
) -> list[dict[str, object]]:
    raw_rows = invalidation.get("objects")
    if not isinstance(raw_rows, list):
        raise MySQLIdentityError("MySQL targeted invalidation record is missing")
    invalidated_at = int(invalidation.get("invalidated_at_unix_ns") or 0)
    results: list[dict[str, object]] = []
    for row in raw_rows:
        if not isinstance(row, dict) or row.get("absent_before_child") is not True:
            raise MySQLIdentityError("MySQL targeted invalidation record is invalid")
        path = Path(str(row.get("object", "")))
        state = _file_state(path)
        if state is None:
            raise MySQLIdentityError(
                f"build did not recreate version-sensitive object {path}"
            )
        dependency_path = Path(str(row.get("dependency", "")))
        dependency_state = _file_state(dependency_path)
        if dependency_state is None:
            raise MySQLIdentityError(
                f"build did not recreate version-sensitive depfile {dependency_path}"
            )
        if int(state["mtime_ns"]) < invalidated_at:
            raise MySQLIdentityError(
                f"rebuilt object predates targeted invalidation: {path}"
            )
        if int(dependency_state["mtime_ns"]) < invalidated_at:
            raise MySQLIdentityError(
                f"rebuilt depfile predates targeted invalidation: {dependency_path}"
            )
        results.append(
            {
                "source": row.get("source"),
                "object": str(path),
                "dependency": str(dependency_path),
                "dependency_state": dependency_state,
                **state,
            }
        )
    return results


def relinked_chain_identity(
    invalidation: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    raw_outputs = invalidation.get("chain_outputs")
    if not isinstance(raw_outputs, dict):
        raise MySQLIdentityError("MySQL freshness-chain invalidation is missing")
    results: dict[str, dict[str, object]] = {}
    for name in VERSION_CHAIN_OUTPUTS:
        row = raw_outputs.get(name)
        if not isinstance(row, dict) or row.get("absent_before_child") is not True:
            raise MySQLIdentityError(
                f"MySQL freshness-chain invalidation is invalid for {name}"
            )
        path = Path(str(row.get("path", "")))
        state = _file_state(path)
        if state is None:
            raise MySQLIdentityError(
                f"build did not recreate MySQL freshness-chain output {path}"
            )
        results[name] = {"path": str(path), **state}
    return results


def binary_runtime_identity(
    binary: Path,
    version_reader: Callable[[Path], tuple[int, str]] = client_library_version,
    ldd_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    if not binary.is_file() or binary.read_bytes()[:4] != b"\x7fELF":
        raise MySQLIdentityError(f"worldserver is not an ELF binary: {binary}")
    result = ldd_runner(
        ["/usr/bin/ldd", str(binary)],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
        },
    )
    if result.returncode:
        raise MySQLIdentityError(
            f"cannot resolve worldserver runtime libraries: {result.stderr.strip()}"
        )
    matches: list[tuple[str, Path]] = []
    for line in result.stdout.splitlines():
        match = re.match(
            r"^\s*(lib(?:mysqlclient|mariadb)\.so[^\s]*)\s+=>\s+([^\s]+)",
            line,
        )
        if match and match.group(2) != "not":
            matches.append((match.group(1), Path(match.group(2))))
    if len(matches) != 1:
        raise MySQLIdentityError(
            f"expected one linked MySQL client library, found {len(matches)}"
        )
    soname, path = matches[0]
    identity = library_identity(path, version_reader)
    return {"needed_soname": soname, **identity}


def same_runtime_library(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    return (
        left.get("sha256") == right.get("sha256")
        and left.get("runtime_version_id") == right.get("runtime_version_id")
        and left.get("size_bytes") == right.get("size_bytes")
    )
