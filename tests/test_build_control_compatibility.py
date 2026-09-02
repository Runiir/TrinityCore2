from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from tools.raid_program.build_control_compatibility import (
    LAYERED_AUTHORITY_SCHEMA,
    verify_build_control_compatibility,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "build source")
    commit = _git(root, "rev-parse", "HEAD")
    snapshot = {
        "commit": commit,
        "tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "clean": True,
        "dirty": False,
        "porcelain_sha256": hashlib.sha256(b"").hexdigest(),
    }
    return root, {
        "commit": commit,
        "source_identity": {
            stage: dict(snapshot)
            for stage in ("request", "admission", "completion")
        },
    }


def _commit_file(root: Path, relative: str, content: str = "control\n") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(root, "add", relative)
    _git(root, "commit", "-m", f"change {relative}")


def _diff_paths(root: Path, parent: str, child: str) -> list[str]:
    output = _git(
        root, "diff", "--name-only", "--no-renames", f"{parent}..{child}",
    )
    return sorted(output.splitlines()) if output else []


def _authority(
    path: Path, *, build: str, reviewed: str, current: str,
    build_paths: list[str], current_paths: list[str],
) -> str:
    path.write_text(json.dumps({
        "schema": LAYERED_AUTHORITY_SCHEMA,
        "build_source_commit": build,
        "reviewed_control_commit": reviewed,
        "current_control_commit": current,
        "build_to_review_paths": build_paths,
        "review_to_current_paths": current_paths,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _layered_repo(
    tmp_path: Path,
) -> tuple[Path, dict[str, object], str, str, Path, str]:
    root, receipt = _repo(tmp_path)
    build = str(receipt["commit"])
    _commit_file(root, "tools/raid_program/reviewed.py", "reviewed\n")
    reviewed = _git(root, "rev-parse", "HEAD")
    _commit_file(root, "tests/test_current.py", "current\n")
    current = _git(root, "rev-parse", "HEAD")
    path = tmp_path / "authority.json"
    digest = _authority(
        path, build=build, reviewed=reviewed, current=current,
        build_paths=_diff_paths(root, build, reviewed),
        current_paths=_diff_paths(root, reviewed, current),
    )
    return root, receipt, reviewed, current, path, digest


def test_exact_and_explicit_control_only_descendant_are_compatible(
    tmp_path: Path,
) -> None:
    root, receipt = _repo(tmp_path)
    exact = verify_build_control_compatibility(worktree=root, receipt=receipt)
    assert exact["valid"] is True
    assert exact["relationship"] == "exact"

    allowed = {
        "experiments/configs/descriptor.json": "{}\n",
        "artifacts/receipts/build.dvc": "outs: []\n",
        ".agents/skills/runtime/SKILL.md": "instructions\n",
        "docs/raid.md": "documentation\n",
        "AGENTS.md": "agent instructions\n",
    }
    for path, content in allowed.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "control metadata")

    descendant = verify_build_control_compatibility(
        worktree=root, receipt=receipt,
    )
    assert descendant["valid"] is True
    assert descendant["relationship"] == "control_only_descendant"
    assert descendant["build_source_commit"] == receipt["commit"]
    assert descendant["control_commit"] == _git(root, "rev-parse", "HEAD")
    assert descendant["changed_control_path_count"] == len(allowed)
    assert len(descendant["changed_control_paths_sha256"]) == 64


def test_exact_layered_authority_accepts_reviewed_tools_and_tests(
    tmp_path: Path,
) -> None:
    root, receipt, reviewed, current, path, digest = _layered_repo(tmp_path)

    report = verify_build_control_compatibility(
        worktree=root, receipt=receipt,
        authority_path=path, authority_sha256=digest,
    )

    assert report["valid"] is True
    assert report["relationship"] == "control_only_descendant"
    authority = report["layered_authority"]
    assert authority["build_source_commit"] == receipt["commit"]
    assert authority["reviewed_control_commit"] == reviewed
    assert authority["current_control_commit"] == current
    assert authority["build_to_review_path_count"] == 1
    assert authority["review_to_current_path_count"] == 1
    assert authority["sha256"] == digest


def test_layered_authority_rejects_hash_and_current_head_drift(
    tmp_path: Path,
) -> None:
    root, receipt, _, _, path, digest = _layered_repo(tmp_path)
    bad_hash = verify_build_control_compatibility(
        worktree=root, receipt=receipt, authority_path=path,
        authority_sha256="0" * 64,
    )
    assert bad_hash["valid"] is False
    assert "build_control_authority:hash_mismatch" in bad_hash["rejections"]

    _commit_file(root, "docs/after-authority.md", "drift\n")
    drift = verify_build_control_compatibility(
        worktree=root, receipt=receipt, authority_path=path,
        authority_sha256=digest,
    )
    assert drift["valid"] is False
    assert "build_control_authority:current_control_commit_mismatch" in (
        drift["rejections"]
    )


def test_layered_authority_rejects_wrong_commits_schema_and_reordered_layer(
    tmp_path: Path,
) -> None:
    root, receipt, reviewed, current, path, _ = _layered_repo(tmp_path)
    build = str(receipt["commit"])
    wrong_build_digest = _authority(
        path, build=reviewed, reviewed=reviewed, current=current,
        build_paths=[], current_paths=["tests/test_current.py"],
    )
    wrong_build = verify_build_control_compatibility(
        worktree=root, receipt=receipt, authority_path=path,
        authority_sha256=wrong_build_digest,
    )
    assert any("build_source_commit_mismatch" in row for row in wrong_build["rejections"])

    schema_value = json.loads(path.read_text(encoding="utf-8"))
    schema_value["unexpected"] = True
    path.write_text(json.dumps(schema_value), encoding="utf-8")
    schema = verify_build_control_compatibility(
        worktree=root, receipt=receipt, authority_path=path,
        authority_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    assert any("schema_fields_invalid" in row for row in schema["rejections"])

    _commit_file(root, "tests/test_z_current.py", "second current\n")
    latest = _git(root, "rev-parse", "HEAD")
    reordered_digest = _authority(
        path, build=build, reviewed=reviewed, current=latest,
        build_paths=["tools/raid_program/reviewed.py"],
        current_paths=["tests/test_z_current.py", "tests/test_current.py"],
    )
    reordered = verify_build_control_compatibility(
        worktree=root, receipt=receipt, authority_path=path,
        authority_sha256=reordered_digest,
    )
    assert any("not_canonical" in row for row in reordered["rejections"])


@pytest.mark.parametrize(
    ("paths", "reason"),
    [
        (["tests/test_current.py", "tests/test_current.py"], "not_canonical"),
        (["aaa.py", "tests/test_current.py"], "not_file"),
        ([], "diff_mismatch"),
        (["/tests/test_current.py"], "path_malformed"),
        (["../tests/test_current.py"], "path_malformed"),
        (["tests/*.py"], "path_glob_forbidden"),
    ],
)
def test_layered_authority_rejects_noncanonical_and_malformed_paths(
    tmp_path: Path, paths: list[str], reason: str,
) -> None:
    root, receipt, reviewed, current, path, _ = _layered_repo(tmp_path)
    digest = _authority(
        path, build=str(receipt["commit"]), reviewed=reviewed,
        current=current,
        build_paths=["tools/raid_program/reviewed.py"],
        current_paths=paths,
    )

    report = verify_build_control_compatibility(
        worktree=root, receipt=receipt,
        authority_path=path, authority_sha256=digest,
    )

    assert report["valid"] is False
    assert any(reason in rejection for rejection in report["rejections"])


@pytest.mark.parametrize(
    "relative",
    [
        "src/server/native.cpp",
        "dep/library/header.h",
        "cmake/options.cmake",
        "nested/CMakeLists.txt",
        "sql/custom/change.sql",
        "trinity-worldserver-test.conf",
    ],
)
def test_layered_authority_cannot_name_unconditionally_forbidden_paths(
    tmp_path: Path, relative: str,
) -> None:
    root, receipt = _repo(tmp_path)
    build = str(receipt["commit"])
    _commit_file(root, relative)
    current = _git(root, "rev-parse", "HEAD")
    path = tmp_path / "authority.json"
    digest = _authority(
        path, build=build, reviewed=current, current=current,
        build_paths=[relative], current_paths=[],
    )

    report = verify_build_control_compatibility(
        worktree=root, receipt=receipt,
        authority_path=path, authority_sha256=digest,
    )

    assert report["valid"] is False
    assert any(
        "path_unconditionally_forbidden" in rejection
        for rejection in report["rejections"]
    )


def test_layered_authority_rejects_directory_and_rename(tmp_path: Path) -> None:
    root, receipt = _repo(tmp_path)
    build = str(receipt["commit"])
    _commit_file(root, "tools/reviewed/original.py")
    reviewed = _git(root, "rev-parse", "HEAD")
    _git(root, "mv", "tools/reviewed/original.py", "tools/reviewed/renamed.py")
    _git(root, "commit", "-m", "rename reviewed control")
    current = _git(root, "rev-parse", "HEAD")
    path = tmp_path / "authority.json"
    digest = _authority(
        path, build=build, reviewed=reviewed, current=current,
        build_paths=["tools/reviewed"],
        current_paths=_diff_paths(root, reviewed, current),
    )
    directory = verify_build_control_compatibility(
        worktree=root, receipt=receipt, authority_path=path,
        authority_sha256=digest,
    )
    assert any("not_file:tools/reviewed" in row for row in directory["rejections"])

    digest = _authority(
        path, build=build, reviewed=reviewed, current=current,
        build_paths=_diff_paths(root, build, reviewed),
        current_paths=_diff_paths(root, reviewed, current),
    )
    renamed = verify_build_control_compatibility(
        worktree=root, receipt=receipt, authority_path=path,
        authority_sha256=digest,
    )
    assert any("rename_forbidden" in row for row in renamed["rejections"])


@pytest.mark.parametrize(
    "relative",
    [
        "src/server/native.cpp",
        "dep/library/header.h",
        "cmake/options.cmake",
        "nested/CMakeLists.txt",
        "sql/custom/change.sql",
        "trinity-worldserver-test.conf",
        "tools/raid_program/unknown.py",
        "tests/unknown_test.py",
        "unknown/data.json",
    ],
)
def test_descendant_rejects_native_build_runtime_and_unknown_paths(
    tmp_path: Path, relative: str,
) -> None:
    root, receipt = _repo(tmp_path)
    _commit_file(root, relative)

    report = verify_build_control_compatibility(worktree=root, receipt=receipt)

    assert report["valid"] is False
    assert f"control_path_not_allowed:{relative}" in report["rejections"]


def test_descendant_rejects_dirty_tree_and_nonancestor(tmp_path: Path) -> None:
    root, receipt = _repo(tmp_path)
    (root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    dirty = verify_build_control_compatibility(worktree=root, receipt=receipt)
    assert dirty["valid"] is False
    assert "control_source_dirty" in dirty["rejections"]

    (root / "untracked.txt").unlink()
    baseline = str(receipt["commit"])
    _git(root, "checkout", "--orphan", "unrelated")
    for path in list(root.iterdir()):
        if path.name != ".git" and path.is_file():
            path.unlink()
    (root / "README.md").write_text("unrelated\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "unrelated")
    assert _git(root, "rev-parse", "HEAD") != baseline

    unrelated = verify_build_control_compatibility(worktree=root, receipt=receipt)
    assert unrelated["valid"] is False
    assert "build_source_not_ancestor" in unrelated["rejections"]


def test_receipt_source_snapshots_must_be_stable_and_clean(tmp_path: Path) -> None:
    root, receipt = _repo(tmp_path)
    changed = json.loads(json.dumps(receipt))
    changed["source_identity"]["completion"]["dirty"] = True
    changed["source_identity"]["completion"]["clean"] = False

    report = verify_build_control_compatibility(worktree=root, receipt=changed)

    assert report["valid"] is False
    assert "build_source_identity_changed" in report["rejections"]
