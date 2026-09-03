from __future__ import annotations

import errno
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Iterable


class SafePathError(OSError):
    def __init__(self, kind: str, path: Path, detail: str = "") -> None:
        self.kind = kind
        self.path = Path(path)
        self.detail = detail
        super().__init__(f"{kind}:{self.path}{':' + detail if detail else ''}")


def absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _classify_open_error(error: OSError, parent_fd: int, name: str, path: Path) -> SafePathError:
    if error.errno == errno.ENOENT:
        return SafePathError("missing", path, str(error))
    try:
        observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        observed = None
    if observed is not None and stat.S_ISLNK(observed.st_mode):
        return SafePathError("symlink", path)
    return SafePathError("type_mismatch", path, str(error))


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _open_absolute(path: Path, *, directory: bool) -> tuple[int, tuple[tuple[int, int, int, int, int, int], ...]]:
    path = absolute_path(path)
    parts = path.parts[1:]
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    current = os.open("/", os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_DIRECTORY)
    identities = [_identity(os.fstat(current))]
    if not parts:
        if not directory:
            os.close(current)
            raise SafePathError("type_mismatch", path, "expected_regular_file")
        return current, tuple(identities)
    try:
        for index, part in enumerate(parts):
            is_last = index == len(parts) - 1
            component_flags = flags
            if not is_last or directory:
                component_flags |= os.O_DIRECTORY
            component_path = Path("/", *parts[: index + 1])
            try:
                following = os.open(part, component_flags, dir_fd=current)
            except OSError as error:
                raise _classify_open_error(error, current, part, component_path) from error
            value = os.fstat(following)
            expected_directory = not is_last or directory
            if expected_directory and not stat.S_ISDIR(value.st_mode):
                os.close(following)
                raise SafePathError("type_mismatch", component_path, "expected_directory")
            if is_last and not directory and not stat.S_ISREG(value.st_mode):
                os.close(following)
                raise SafePathError("type_mismatch", component_path, "expected_regular_file")
            identities.append(_identity(value))
            os.close(current)
            current = following
        return current, tuple(identities)
    except BaseException:
        os.close(current)
        raise


def _recheck_path(
    path: Path, *, directory: bool,
    expected: tuple[tuple[int, int, int, int, int, int], ...],
) -> None:
    descriptor, observed = _open_absolute(path, directory=directory)
    os.close(descriptor)
    if observed != expected:
        raise SafePathError("path_drift", absolute_path(path), "component_identity_changed")


def read_regular_no_follow(path: Path) -> tuple[bytes, os.stat_result]:
    path = absolute_path(path)
    descriptor, identities = _open_absolute(path, directory=False)
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if _identity(before) != _identity(after):
            raise SafePathError("path_drift", path, "file_changed_while_reading")
    finally:
        os.close(descriptor)
    _recheck_path(path, directory=False, expected=identities)
    return b"".join(chunks), after


def require_directory_no_follow(path: Path) -> os.stat_result:
    path = absolute_path(path)
    descriptor, identities = _open_absolute(path, directory=True)
    try:
        value = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    _recheck_path(path, directory=True, expected=identities)
    return value


def _relative_parts(relative: str) -> tuple[str, ...]:
    if relative in {"", "."}:
        return ()
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise SafePathError("path_traversal", Path(relative))
    if "\\" in relative or relative != pure.as_posix():
        raise SafePathError("path_traversal", Path(relative))
    return pure.parts


def _file_record(parent_fd: int, name: str, relative: str, absolute: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as error:
        raise _classify_open_error(error, parent_fd, name, absolute) from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SafePathError("type_mismatch", absolute, "expected_regular_file")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        if _identity(before) != _identity(after):
            raise SafePathError("path_drift", absolute, "file_changed_while_reading")
        linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if _identity(after) != _identity(linked):
            raise SafePathError("path_drift", absolute, "directory_entry_changed")
        return {
            "path": relative,
            "type": "file",
            "mode": f"{stat.S_IMODE(after.st_mode):04o}",
            "size_bytes": after.st_size,
            "sha256": digest.hexdigest(),
        }
    finally:
        os.close(descriptor)


def walk_inventory_no_follow(
    root: Path, relative: str = ".", *, include_directories: bool = True,
    excluded_paths: Iterable[str] = (),
) -> list[dict[str, Any]]:
    root = absolute_path(root)
    root_fd, root_identities = _open_absolute(root, directory=True)
    excluded = set(excluded_paths)
    try:
        start_path = root.joinpath(*_relative_parts(relative))
        start_fd, start_identities = _open_absolute(start_path, directory=True)
        start_relative = start_path.relative_to(root).as_posix()
        if start_relative == ".":
            start_relative = ""
        records: list[dict[str, Any]] = []

        def visit(directory_fd: int, directory_path: Path, prefix: str) -> None:
            before = os.fstat(directory_fd)
            try:
                names = sorted(os.listdir(directory_fd))
            except OSError as error:
                raise SafePathError("type_mismatch", directory_path, str(error)) from error
            for name in names:
                member = f"{prefix}/{name}" if prefix else name
                if member in excluded:
                    continue
                absolute = directory_path / name
                value = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if stat.S_ISLNK(value.st_mode):
                    raise SafePathError("symlink", absolute)
                if stat.S_ISREG(value.st_mode):
                    records.append(_file_record(directory_fd, name, member, absolute))
                    continue
                if not stat.S_ISDIR(value.st_mode):
                    raise SafePathError("type_mismatch", absolute, "unsupported_member_type")
                flags = (
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                )
                try:
                    child_fd = os.open(name, flags, dir_fd=directory_fd)
                except OSError as error:
                    raise _classify_open_error(error, directory_fd, name, absolute) from error
                try:
                    opened = os.fstat(child_fd)
                    if _identity(opened) != _identity(value):
                        raise SafePathError("path_drift", absolute, "directory_entry_changed")
                    if include_directories:
                        records.append({
                            "path": member,
                            "type": "directory",
                            "mode": f"{stat.S_IMODE(opened.st_mode):04o}",
                            "size_bytes": opened.st_size,
                        })
                    visit(child_fd, absolute, member)
                    linked = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if _identity(opened) != _identity(linked):
                        raise SafePathError("path_drift", absolute, "directory_entry_changed")
                finally:
                    os.close(child_fd)
            after = os.fstat(directory_fd)
            if _identity(before) != _identity(after):
                raise SafePathError("path_drift", directory_path, "directory_changed_while_reading")

        try:
            visit(start_fd, start_path, start_relative)
        finally:
            os.close(start_fd)
        _recheck_path(start_path, directory=True, expected=start_identities)
    finally:
        os.close(root_fd)
    _recheck_path(root, directory=True, expected=root_identities)
    return sorted(records, key=lambda row: str(row["path"]))
