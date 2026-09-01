from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from tools.raid_program import mysql_build_identity as mbi


def _write_version_header(path: Path, version: int) -> None:
    path.write_text(f"#define MYSQL_VERSION_ID {version}\n", encoding="utf-8")


def _runtime_reader(path: Path) -> tuple[int, str]:
    version = int(path.read_text(encoding="utf-8"))
    return version, f"fixture-{version}"


def _mysql_fixture(tmp_path: Path) -> tuple[Path, dict[str, str], list[Path]]:
    root = tmp_path / "repo"
    include = tmp_path / "include"
    library = tmp_path / "libmysqlclient.so.24"
    include.mkdir()
    root.mkdir()
    for source in mbi.VERSION_SENSITIVE_SOURCES:
        path = root / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// fixture\n", encoding="utf-8")
    _write_version_header(include / "mysql_version.h", 80410)
    library.write_text("80410", encoding="utf-8")
    build = root / "build/src/server/database"
    build.mkdir(parents=True)
    rows = []
    objects = []
    for source in mbi.VERSION_SENSITIVE_SOURCES:
        object_path = build / f"{Path(source).stem}.cpp.o"
        dependency_path = Path(str(object_path) + ".d")
        object_path.write_bytes(f"stale-{source}".encode())
        dependency_path.write_text("stale dependency\n", encoding="utf-8")
        objects.append(object_path)
        rows.append(
            {
                "directory": str(build),
                "command": f"/usr/bin/c++ -o {object_path.name} -c {root / source}",
                "file": str(root / source),
                "output": object_path.name,
            }
        )
    (root / "build/compile_commands.json").write_text(
        json.dumps(rows), encoding="utf-8"
    )
    return root, {
        "MYSQL_INCLUDE_DIR": str(include),
        "MYSQL_LIBRARY": str(library),
    }, objects


def test_older_preserved_header_mtime_cannot_hide_version_and_hash_change(
    tmp_path: Path,
) -> None:
    root, cache, objects = _mysql_fixture(tmp_path)
    header = Path(cache["MYSQL_INCLUDE_DIR"]) / "mysql_version.h"
    library = Path(cache["MYSQL_LIBRARY"])
    preserved_mtime = 1_787_755_236_000_000_000
    newer_object_mtime = preserved_mtime + 4 * 24 * 60 * 60 * 1_000_000_000
    os.utime(header, ns=(preserved_mtime, preserved_mtime))
    os.utime(library, ns=(preserved_mtime, preserved_mtime))
    for path in objects:
        os.utime(path, ns=(newer_object_mtime, newer_object_mtime))

    old_identity = mbi.build_identity_snapshot(root, cache, _runtime_reader)
    _write_version_header(header, 80411)
    library.write_text("80411", encoding="utf-8")
    os.utime(header, ns=(preserved_mtime, preserved_mtime))
    os.utime(library, ns=(preserved_mtime, preserved_mtime))
    new_identity = mbi.build_identity_snapshot(root, cache, _runtime_reader)

    assert header.stat().st_mtime_ns < objects[0].stat().st_mtime_ns
    assert old_identity["header"]["compile_version_id"] == 80410
    assert new_identity["header"]["compile_version_id"] == 80411
    assert old_identity["header"]["sha256"] != new_identity["header"]["sha256"]
    assert old_identity["runtime_library"]["sha256"] != new_identity["runtime_library"]["sha256"]
    assert old_identity["identity_sha256"] != new_identity["identity_sha256"]

    invalidation = mbi.invalidate_version_sensitive_objects(root)
    assert all(not path.exists() for path in objects)
    assert all(
        not Path(row["dependency"]).exists() for row in invalidation["objects"]
    )
    assert all(row["absent_before_child"] for row in invalidation["objects"])
    assert all(
        row["object_removed"] and row["dependency_removed"]
        for row in invalidation["objects"]
    )
    for row in invalidation["objects"]:
        path = Path(row["object"])
        dependency = Path(row["dependency"])
        path.write_bytes(b"rebuilt-against-80411")
        dependency.write_text("rebuilt dependency\n", encoding="utf-8")
        now = max(time.time_ns(), invalidation["invalidated_at_unix_ns"] + 1)
        os.utime(path, ns=(now, now))
        os.utime(dependency, ns=(now, now))
    rebuilt = mbi.rebuilt_object_identity(invalidation)
    assert [row["source"] for row in rebuilt] == list(
        mbi.VERSION_SENSITIVE_SOURCES
    )
    assert all(row["dependency_state"]["size_bytes"] > 0 for row in rebuilt)

    Path(invalidation["objects"][0]["dependency"]).unlink()
    with pytest.raises(mbi.MySQLIdentityError, match="did not recreate.*depfile"):
        mbi.rebuilt_object_identity(invalidation)


def test_compile_header_runtime_version_mismatch_fails_closed(tmp_path: Path) -> None:
    root, cache, _objects = _mysql_fixture(tmp_path)
    Path(cache["MYSQL_LIBRARY"]).write_text("80411", encoding="utf-8")
    with pytest.raises(
        mbi.MySQLIdentityError,
        match="compile header/runtime library version mismatch: 80410 != 80411",
    ):
        mbi.build_identity_snapshot(root, cache, _runtime_reader)


def test_binary_runtime_identity_resolves_exact_linked_library(tmp_path: Path) -> None:
    binary = tmp_path / "worldserver"
    library = tmp_path / "libmysqlclient.so.24"
    binary.write_bytes(b"\x7fELFfixture")
    library.write_text("80411", encoding="utf-8")

    def fake_ldd(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=f"libmysqlclient.so.24 => {library} (0x1234)\n",
            stderr="",
        )

    identity = mbi.binary_runtime_identity(binary, _runtime_reader, fake_ldd)
    assert identity["needed_soname"] == "libmysqlclient.so.24"
    assert identity["runtime_version_id"] == 80411
    assert identity["sha256"] == mbi.library_identity(
        library, _runtime_reader
    )["sha256"]
