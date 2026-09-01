from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from tools.raid_program.build_control_compatibility import (
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
