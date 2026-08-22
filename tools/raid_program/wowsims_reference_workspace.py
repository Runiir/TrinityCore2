#!/usr/bin/env python3
"""Hydrate, verify, and evict the exact promoted WoWSims reference workspace."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from tools.raid_program import raid_workloop


ROOT = Path(__file__).resolve().parents[2]
POINTER = raid_workloop.WOWSIMS_DVC_POINTER
BUNDLE = raid_workloop.WOWSIMS_BUNDLE


class WorkspaceError(RuntimeError):
    """Raised when the exact reference workspace cannot be trusted."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise WorkspaceError(reason)


def _safe_paths(root: Path) -> tuple[Path, Path]:
    root = root.resolve()
    pointer = (root / POINTER).resolve()
    bundle = root / BUNDLE
    _require(pointer == root / POINTER, "dvc_pointer_symlink_forbidden")
    _require(pointer.is_file(), "dvc_pointer_missing")
    _require(bundle.parent.resolve() == (root / BUNDLE.parent).resolve(), "bundle_parent")
    _require(not bundle.is_symlink(), "bundle_symlink_forbidden")
    return pointer, bundle


def _pointer_metadata(pointer: Path) -> dict[str, Any]:
    text = pointer.read_text(encoding="utf-8")
    values: dict[str, str] = {}
    for key in ("md5", "size", "nfiles", "path"):
        match = re.search(rf"(?m)^\s*(?:-\s+)?{key}:\s*([^\s]+)\s*$", text)
        _require(match is not None, f"dvc_pointer_{key}_missing")
        values[key] = match.group(1)
    _require(values["md5"].endswith(".dir"), "dvc_pointer_directory_digest")
    _require(values["path"] == BUNDLE.name, "dvc_pointer_bundle_path")
    return {
        "digest": values["md5"],
        "size": int(values["size"]),
        "nfiles": int(values["nfiles"]),
    }


def _run(command: Sequence[str], *, root: Path) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command), cwd=root, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        suffix = detail[-1] if detail else f"exit_{completed.returncode}"
        raise WorkspaceError(f"command_failed:{command[0]}:{suffix}")
    return completed


def _dvc_command(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("dvc")
    _require(bool(executable), "dvc_executable_missing")
    return _run([str(executable), *arguments], root=root)


def _bundle_observation(root: Path) -> dict[str, Any]:
    _, bundle = _safe_paths(root)
    status = raid_workloop.wowsims_status(root)
    state_counts = status["promotion_states"]
    hydrated = bundle.is_dir()
    if hydrated:
        file_count = sum(1 for path in bundle.rglob("*") if path.is_file())
        byte_count = sum(path.stat().st_size for path in bundle.rglob("*") if path.is_file())
    else:
        file_count = 0
        byte_count = 0
    return {
        "hydrated": hydrated,
        "file_count": file_count,
        "byte_count": byte_count,
        "reference_class": status["reference_class"],
        "reference_count": status["accepted_reference_count"],
        "promotion_states": state_counts,
        "dvc_bundle_digest": status["dvc_bundle_digest"],
    }


def status(root: Path) -> dict[str, Any]:
    observation = _bundle_observation(root)
    state = (
        "locally_verified"
        if observation["reference_count"] == 16
        and observation["promotion_states"] == {"locally_reconstructed_current": 16}
        else "remote_requires_hydration"
        if observation["promotion_states"] == {"current_remote_requires_hydration": 16}
        else "invalid_or_incomplete"
    )
    return {
        "schema": "wowsims_reference_workspace_receipt_v1",
        "action": "status",
        "state": state,
        "root": str(root.resolve()),
        "dvc_pointer": POINTER.as_posix(),
        "bundle": BUNDLE.as_posix(),
        "observation": observation,
        "next_command": (
            "pixi run python -m tools.raid_program.wowsims_reference_workspace hydrate"
            if state == "remote_requires_hydration"
            else "pixi run python -m tools.raid_program.raid_workloop status"
        ),
    }


def verify(root: Path) -> dict[str, Any]:
    pointer, bundle = _safe_paths(root)
    pointer_metadata = _pointer_metadata(pointer)
    _require(bundle.is_dir(), "reference_bundle_not_hydrated")
    cloud = _dvc_command(root, "status", "--cloud", POINTER.as_posix())
    _run(
        [
            sys.executable,
            "-m",
            "tools.bot_ml.run_wowsims_exact_references",
            "validate-catalog",
        ],
        root=root,
    )
    observation = _bundle_observation(root)
    _require(
        observation["file_count"] == pointer_metadata["nfiles"],
        "reference_bundle_file_count",
    )
    _require(
        observation["byte_count"] == pointer_metadata["size"],
        "reference_bundle_byte_count",
    )
    _require(observation["reference_count"] == 16, "accepted_reference_count")
    _require(
        observation["promotion_states"] == {"locally_reconstructed_current": 16},
        "promotion_state",
    )
    return {
        "schema": "wowsims_reference_workspace_receipt_v1",
        "action": "verify",
        "state": "locally_verified",
        "root": str(root.resolve()),
        "dvc_pointer": POINTER.as_posix(),
        "bundle": BUNDLE.as_posix(),
        "cloud_status": (cloud.stdout + cloud.stderr).strip(),
        "dvc_pointer_metadata": pointer_metadata,
        "observation": observation,
        "next_command": "pixi run python -m tools.raid_program.raid_workloop status",
        "evict_command": (
            "pixi run python -m tools.raid_program.wowsims_reference_workspace evict"
        ),
    }


def hydrate(root: Path, *, jobs: int) -> dict[str, Any]:
    _safe_paths(root)
    _require(1 <= jobs <= 8, "dvc_jobs_out_of_range")
    _dvc_command(root, "pull", "--jobs", str(jobs), POINTER.as_posix())
    receipt = verify(root)
    receipt["action"] = "hydrate"
    return receipt


def evict(root: Path) -> dict[str, Any]:
    _, bundle = _safe_paths(root)
    verified = verify(root)
    _require(bundle.is_dir(), "reference_bundle_not_hydrated")
    for path in bundle.rglob("*"):
        _require(not path.is_symlink(), "bundle_child_symlink_forbidden")
    shutil.rmtree(bundle)
    _require(not bundle.exists(), "workspace_eviction_incomplete")
    observation = _bundle_observation(root)
    _require(
        observation["promotion_states"] == {"current_remote_requires_hydration": 16},
        "remote_reference_lost_after_eviction",
    )
    return {
        "schema": "wowsims_reference_workspace_receipt_v1",
        "action": "evict",
        "state": "workspace_evicted_remote_verified",
        "root": str(root.resolve()),
        "dvc_pointer": POINTER.as_posix(),
        "bundle": BUNDLE.as_posix(),
        "verified_before_eviction": verified["observation"],
        "observation": observation,
        "shared_dvc_cache_evicted": False,
        "shared_dvc_cache_policy": "preserved_no_broad_gc",
        "next_command": (
            "pixi run python -m tools.raid_program.wowsims_reference_workspace hydrate"
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    hydrate_parser = subparsers.add_parser("hydrate")
    hydrate_parser.add_argument("--jobs", type=int, default=4)
    subparsers.add_parser("verify")
    subparsers.add_parser("evict")
    return parser


def main() -> int:
    args = _parser().parse_args()
    root = args.root.resolve()
    try:
        if args.command == "status":
            receipt = status(root)
        elif args.command == "hydrate":
            receipt = hydrate(root, jobs=args.jobs)
        elif args.command == "verify":
            receipt = verify(root)
        else:
            receipt = evict(root)
    except WorkspaceError as exc:
        print(
            json.dumps(
                {
                    "schema": "wowsims_reference_workspace_error_v1",
                    "action": args.command,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
