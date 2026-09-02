from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any, Mapping


COMMIT_RE = re.compile(r"[0-9a-f]{40,64}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
EMPTY_PORCELAIN_SHA256 = hashlib.sha256(b"").hexdigest()
LAYERED_AUTHORITY_SCHEMA = "cata_raid_layered_build_control_authority_v1"
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
LAYERED_AUTHORITY_FIELDS = {
    "schema",
    "build_source_commit",
    "reviewed_control_commit",
    "current_control_commit",
    "build_to_review_paths",
    "review_to_current_paths",
}
GLOB_CHARACTERS = frozenset("*?[]{}")


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


def _paths_sha256(paths: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(paths, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _authority_path_rejection(value: object) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return "path_malformed"
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return "path_malformed"
    if any(character in value for character in GLOB_CHARACTERS):
        return "path_glob_forbidden"
    if (
        value in BUILD_ROOT_FILES
        or value.startswith(NATIVE_ROOTS)
        or path.name == "CMakeLists.txt"
        or path.suffix == ".cmake"
        or path.suffix in {".sql", ".conf"}
        or "worldserver" in path.name.lower() and "conf" in path.name.lower()
    ):
        return "path_unconditionally_forbidden"
    return None


def _commit_exists(worktree: Path, commit: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(worktree), "cat-file", "-e", f"{commit}^{{commit}}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def _is_ancestor(worktree: Path, parent: str, child: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(worktree), "merge-base", "--is-ancestor", parent, child],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def _diff_paths(worktree: Path, parent: str, child: str) -> list[str]:
    raw = _git(
        worktree,
        "diff",
        "--name-only",
        "-z",
        "--no-renames",
        f"{parent}..{child}",
        "--",
        binary=True,
    )
    assert isinstance(raw, bytes)
    return sorted(
        path.decode("utf-8", errors="strict")
        for path in raw.split(b"\0")
        if path
    )


def _has_renamed_path(worktree: Path, parent: str, child: str) -> bool:
    raw = _git(
        worktree,
        "diff",
        "--name-status",
        "-z",
        "--find-renames",
        f"{parent}..{child}",
        "--",
        binary=True,
    )
    assert isinstance(raw, bytes)
    return any(
        field.startswith((b"R", b"C"))
        for field in raw.split(b"\0")
        if field
    )


def _git_object_is_blob(worktree: Path, commit: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(worktree), "cat-file", "-t", f"{commit}:{path}"],
        check=False,
        text=True,
        capture_output=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "blob"


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def _verify_layered_authority(
    *, worktree: Path, authority_path: Path, expected_sha256: str,
    build_commit: str, current_commit: str,
) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(expected_sha256):
        raise ValueError("sha256_invalid")
    authority_path = authority_path.resolve()
    try:
        payload = authority_path.read_bytes()
    except OSError as error:
        raise ValueError("file_unavailable") from error
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError("hash_mismatch")
    try:
        authority = json.loads(payload, object_pairs_hook=_unique_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("json_invalid") from error
    if not isinstance(authority, dict) or set(authority) != LAYERED_AUTHORITY_FIELDS:
        raise ValueError("schema_fields_invalid")
    if authority.get("schema") != LAYERED_AUTHORITY_SCHEMA:
        raise ValueError("schema_invalid")
    commits = {
        name: authority.get(name)
        for name in (
            "build_source_commit", "reviewed_control_commit",
            "current_control_commit",
        )
    }
    if any(
        not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit)
        for commit in commits.values()
    ):
        raise ValueError("commit_invalid")
    if commits["build_source_commit"] != build_commit:
        raise ValueError("build_source_commit_mismatch")
    if commits["current_control_commit"] != current_commit:
        raise ValueError("current_control_commit_mismatch")
    if any(not _commit_exists(worktree, commit) for commit in commits.values()):
        raise ValueError("commit_missing")
    reviewed_commit = str(commits["reviewed_control_commit"])
    if not _is_ancestor(worktree, build_commit, reviewed_commit):
        raise ValueError("build_source_not_reviewed_ancestor")
    if not _is_ancestor(worktree, reviewed_commit, current_commit):
        raise ValueError("reviewed_not_current_ancestor")
    layer_specs = (
        ("build_to_review_paths", build_commit, reviewed_commit),
        ("review_to_current_paths", reviewed_commit, current_commit),
    )
    projection: dict[str, Any] = {
        "schema": LAYERED_AUTHORITY_SCHEMA,
        "sha256": actual_sha256,
        **commits,
    }
    for field, parent, child in layer_specs:
        paths = authority.get(field)
        if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
            raise ValueError(f"{field}_invalid")
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError(f"{field}_not_canonical")
        if _has_renamed_path(worktree, parent, child):
            raise ValueError(f"{field}_rename_forbidden")
        for path in paths:
            rejection = _authority_path_rejection(path)
            if rejection is not None:
                raise ValueError(f"{field}_{rejection}:{path}")
            if not _git_object_is_blob(worktree, child, path):
                raise ValueError(f"{field}_not_file:{path}")
        actual_paths = _diff_paths(worktree, parent, child)
        if paths != actual_paths:
            raise ValueError(f"{field}_diff_mismatch")
        projection[field.replace("paths", "path_count")] = len(paths)
        projection[field + "_sha256"] = _paths_sha256(paths)
    return projection


def compatibility_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return the immutable two-identity subset stored in admissions."""

    projection = {
        "build_source_commit": report.get("build_source_commit"),
        "build_source_tree": report.get("build_source_tree"),
        "control_commit": report.get("control_commit"),
        "control_tree": report.get("control_tree"),
        "relationship": report.get("relationship"),
        "changed_control_path_count": report.get("changed_control_path_count"),
        "changed_control_paths_sha256": report.get("changed_control_paths_sha256"),
    }
    if report.get("layered_authority") is not None:
        projection["layered_authority"] = report.get("layered_authority")
    return projection


def verify_build_control_compatibility(
    *, worktree: Path, receipt: Mapping[str, Any],
    authority_path: Path | None = None, authority_sha256: str | None = None,
) -> dict[str, Any]:
    """Bind one built binary to an exact or control-only clean descendant.

    The build receipt remains authoritative for the binary's source revision.
    A later control revision is accepted only when every changed tracked path is
    in the narrow allowlist above. Unknown, native, build-system, SQL, and
    worldserver-config paths fail closed.
    """

    worktree = worktree.resolve()
    rejections: list[str] = []
    authority_supplied = authority_path is not None or authority_sha256 is not None
    if (authority_path is None) != (authority_sha256 is None):
        rejections.append("build_control_authority_binding_incomplete")
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
            "layered_authority": None,
        }

    initial_control_commit = control_commit
    initial_control_tree = control_tree
    initial_porcelain = porcelain
    if porcelain:
        rejections.append("control_source_dirty")
    if not COMMIT_RE.fullmatch(control_commit):
        rejections.append("control_source_commit_invalid")

    relationship = "invalid"
    changed_paths: list[str] = []
    if COMMIT_RE.fullmatch(build_commit) and COMMIT_RE.fullmatch(control_commit):
        exists = _commit_exists(worktree, build_commit)
        if not exists:
            rejections.append("build_source_commit_missing")
        elif build_commit == control_commit:
            relationship = "exact"
        else:
            ancestor = _is_ancestor(worktree, build_commit, control_commit)
            if not ancestor:
                rejections.append("build_source_not_ancestor")
            else:
                relationship = "control_only_descendant"
                changed_paths = _diff_paths(worktree, build_commit, control_commit)

    layered_authority: dict[str, Any] | None = None
    if authority_supplied and authority_path is not None and authority_sha256 is not None:
        try:
            layered_authority = _verify_layered_authority(
                worktree=worktree,
                authority_path=authority_path,
                expected_sha256=authority_sha256,
                build_commit=build_commit,
                current_commit=control_commit,
            )
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError, ValueError) as error:
            rejections.append(f"build_control_authority:{error}")
    elif relationship == "control_only_descendant":
        for path in changed_paths:
            if not _allowed_control_path(path):
                rejections.append(f"control_path_not_allowed:{path}")

    if relationship == "exact" and completion:
        if completion.get("tree") != control_tree:
            rejections.append("exact_source_tree_mismatch")

    try:
        final_control_commit = str(_git(worktree, "rev-parse", "HEAD"))
        final_control_tree = str(_git(worktree, "rev-parse", "HEAD^{tree}"))
        final_porcelain = _git(
            worktree, "status", "--porcelain=v1", "-z", binary=True
        )
        assert isinstance(final_porcelain, bytes)
    except (OSError, subprocess.SubprocessError) as error:
        rejections.append(
            f"control_source_identity_unavailable_after_verification:{type(error).__name__}"
        )
        layered_authority = None
    else:
        if (
            final_control_commit != initial_control_commit
            or final_control_tree != initial_control_tree
            or final_porcelain != initial_porcelain
        ):
            rejections.append("control_source_changed_during_verification")
            layered_authority = None

    changed_paths_sha256 = _paths_sha256(changed_paths)
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
        "layered_authority": layered_authority,
    }
