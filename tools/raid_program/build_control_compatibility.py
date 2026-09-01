from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any, Mapping


COMMIT_RE = re.compile(r"[0-9a-f]{40,64}")
EMPTY_PORCELAIN_SHA256 = hashlib.sha256(b"").hexdigest()
ROOT_DOCUMENTATION = {
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "DATASET.md",
    "README.md",
}
NATIVE_ROOTS = ("src/", "dep/", "cmake/")
BUILD_ROOT_FILES = {
    "CMakeLists.txt",
    "PreLoad.cmake",
    "revision_data.h.in.cmake",
}


def _git(worktree: Path, *args: str, binary: bool = False) -> str | bytes:
    value = subprocess.check_output(
        ["git", "-C", str(worktree), *args],
        text=not binary,
    )
    return value if binary else value.strip()


def _allowed_control_path(value: str) -> bool:
    path = PurePosixPath(value)
    if (
        value in BUILD_ROOT_FILES
        or value.startswith(NATIVE_ROOTS)
        or path.name == "CMakeLists.txt"
        or path.suffix == ".cmake"
        or path.suffix in {".sql", ".conf"}
    ):
        return False
    if value == "AGENTS.md" or value in ROOT_DOCUMENTATION:
        return True
    if value.startswith("experiments/configs/"):
        return True
    if value.startswith(".agents/skills/"):
        return True
    if value.startswith("artifacts/") and path.suffix == ".dvc":
        return True
    if value.startswith(("docs/", "doc/")):
        return True
    return False


def compatibility_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return the immutable two-identity subset stored in admissions."""

    return {
        "build_source_commit": report.get("build_source_commit"),
        "build_source_tree": report.get("build_source_tree"),
        "control_commit": report.get("control_commit"),
        "control_tree": report.get("control_tree"),
        "relationship": report.get("relationship"),
        "changed_control_path_count": report.get("changed_control_path_count"),
        "changed_control_paths_sha256": report.get("changed_control_paths_sha256"),
    }


def verify_build_control_compatibility(
    *, worktree: Path, receipt: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind one built binary to an exact or control-only clean descendant.

    The build receipt remains authoritative for the binary's source revision.
    A later control revision is accepted only when every changed tracked path is
    in the narrow allowlist above. Unknown, native, build-system, SQL, and
    worldserver-config paths fail closed.
    """

    worktree = worktree.resolve()
    rejections: list[str] = []
    build_commit = str(receipt.get("commit") or "")
    source_identity = receipt.get("source_identity")
    snapshots = (
        [source_identity.get(stage) for stage in ("request", "admission", "completion")]
        if isinstance(source_identity, Mapping)
        else []
    )
    completion: Mapping[str, Any] = {}
    if len(snapshots) != 3 or not all(isinstance(row, Mapping) for row in snapshots):
        rejections.append("build_source_identity_incomplete")
    elif not (snapshots[0] == snapshots[1] == snapshots[2]):
        rejections.append("build_source_identity_changed")
    else:
        completion = snapshots[2]
        if completion.get("commit") != build_commit:
            rejections.append("build_source_commit_mismatch")
        if completion.get("clean") is not True or completion.get("dirty") is not False:
            rejections.append("build_source_dirty")
        if completion.get("porcelain_sha256") != EMPTY_PORCELAIN_SHA256:
            rejections.append("build_source_porcelain_mismatch")

    if not COMMIT_RE.fullmatch(build_commit):
        rejections.append("build_source_commit_invalid")

    try:
        control_commit = str(_git(worktree, "rev-parse", "HEAD"))
        control_tree = str(_git(worktree, "rev-parse", "HEAD^{tree}"))
        porcelain = _git(worktree, "status", "--porcelain=v1", "-z", binary=True)
        assert isinstance(porcelain, bytes)
    except (OSError, subprocess.SubprocessError) as error:
        return {
            "valid": False,
            "rejections": [
                *rejections,
                f"control_source_identity_unavailable:{type(error).__name__}",
            ],
            "build_source_commit": build_commit or None,
            "build_source_tree": completion.get("tree"),
            "control_commit": None,
            "control_tree": None,
            "relationship": "invalid",
            "changed_control_path_count": 0,
            "changed_control_paths_sha256": hashlib.sha256(b"[]").hexdigest(),
        }

    if porcelain:
        rejections.append("control_source_dirty")
    if not COMMIT_RE.fullmatch(control_commit):
        rejections.append("control_source_commit_invalid")

    relationship = "invalid"
    changed_paths: list[str] = []
    if COMMIT_RE.fullmatch(build_commit) and COMMIT_RE.fullmatch(control_commit):
        exists = subprocess.run(
            ["git", "-C", str(worktree), "cat-file", "-e", f"{build_commit}^{{commit}}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
        if not exists:
            rejections.append("build_source_commit_missing")
        elif build_commit == control_commit:
            relationship = "exact"
        else:
            ancestor = subprocess.run(
                ["git", "-C", str(worktree), "merge-base", "--is-ancestor", build_commit, control_commit],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode == 0
            if not ancestor:
                rejections.append("build_source_not_ancestor")
            else:
                relationship = "control_only_descendant"
                raw = _git(
                    worktree,
                    "diff",
                    "--name-only",
                    "-z",
                    "--no-renames",
                    f"{build_commit}..{control_commit}",
                    "--",
                    binary=True,
                )
                assert isinstance(raw, bytes)
                changed_paths = sorted(
                    path.decode("utf-8", errors="strict")
                    for path in raw.split(b"\0")
                    if path
                )
                for path in changed_paths:
                    if not _allowed_control_path(path):
                        rejections.append(f"control_path_not_allowed:{path}")

    if relationship == "exact" and completion:
        if completion.get("tree") != control_tree:
            rejections.append("exact_source_tree_mismatch")

    changed_paths_sha256 = hashlib.sha256(
        json.dumps(changed_paths, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "valid": not rejections,
        "rejections": rejections,
        "build_source_commit": build_commit or None,
        "build_source_tree": completion.get("tree"),
        "control_commit": control_commit,
        "control_tree": control_tree,
        "relationship": relationship,
        "changed_control_path_count": len(changed_paths),
        "changed_control_paths_sha256": changed_paths_sha256,
    }
