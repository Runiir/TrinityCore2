"""Bind an advisory worker review to the exact Git index, not the worktree.

Without a worker task contract the hook is silent, except for one tier-aware
warning when staged code would break the active graph unit's source binding.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from tools.raid_program.worker_checkpoint import review_checkpoint, deterministic_findings, validate_checkpoint

# Stages whose recorded tests/review/build a staged code change would invalidate.
BOUND_STAGES = ("review", "build", "smoke", "validate")


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args])


def staged_paths(root: Path) -> list[str]:
    return [p for p in git(root, "diff", "--cached", "--name-only", "-z", "--no-renames").decode().split("\0") if p]


def staged_checkpoint(root: Path, task: dict, output: Path) -> dict:
    head = git(root, "rev-parse", "HEAD").decode().strip()
    tree = git(root, "write-tree").decode().strip()
    paths = staged_paths(root)
    diff = git(root, "diff", "--cached", "--no-ext-diff", "--no-textconv", "--no-renames", "--unified=3")
    if tree != git(root, "write-tree").decode().strip() or head != git(root, "rev-parse", "HEAD").decode().strip():
        raise RuntimeError("HEAD or index changed while capturing staged diff")
    digest = hashlib.sha256(diff).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    (output / "staged.diff").write_bytes(diff)
    (output / "task.json").write_text(json.dumps(task, indent=2) + "\n")
    checkpoint = dict(task)
    checkpoint["changed_files"] = paths
    checkpoint["changed_files_source"] = "observed_git_index"
    checkpoint["stage"] = "result"
    checkpoint["evidence_excerpts"] = [*task.get("evidence_excerpts", []), {
        "id": "staged_diff", "path": str((output / "staged.diff").resolve()),
        "sha256": digest, "text": diff.decode("utf-8", errors="replace"),
    }]
    manifest = {
        "schema": "worker_staged_diff_v1", "head": head,
        "index_tree": tree, "staged_diff_sha256": digest,
        "task_sha256": hashlib.sha256((output / "task.json").read_bytes()).hexdigest(),
        "files": paths, "unstaged_changes_included": False,
    }
    (output / "index.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return checkpoint


def unit_notice(root: Path) -> str | None:
    """One warning when staged code conflicts with the active unit; None otherwise."""
    from tools.raid_program import development_graph as graph
    from tools.raid_program import graph_tiers as tiers
    try:
        g = json.loads((root / graph.STATE_PATH).read_text())["development_graph"]
        stage, unit, assignment = g["stage"], g["unit"], g.get("assignment")
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not assignment or stage not in ("implement", *BOUND_STAGES):
        return None
    code = [p for p in staged_paths(root) if graph.code_path(p)]
    tier = tiers.tier_of(g)
    prefix = f"Unit {unit['id']} ({tier}, {stage}): "
    if stage == "implement":
        scope = set(assignment.get("owned_files", [])) | set(assignment.get("supporting_files", {}))
        outside = sorted(p for p in code if p not in scope)
        if outside:
            return (prefix + "staged code outside owned files will fail tests/review binding: "
                    + ", ".join(outside[:8]) + (f" (+{len(outside) - 8} more)" if len(outside) > 8 else ""))
        return None
    if code:
        return (prefix + "staged code changes invalidate the recorded tests/build; expect rework. Remaining steps: "
                + " -> ".join(tiers.remaining(stage, tier)["remaining_steps"]))
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--backend", choices=("local", "hosted", "both"), default="both")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--model-advice", action="store_true", help="Opt in to a non-blocking legacy model review; no network by default")
    args = parser.parse_args(argv)
    root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip())
    task_path = args.task or Path(git(root, "rev-parse", "--git-path", "worker-task.json").decode().strip())
    if not task_path.is_absolute():
        task_path = root / task_path
    if not task_path.is_file():
        notice = unit_notice(root)
        if notice:
            print("Worker checkpoint: " + notice)
        return 0
    task_bytes = task_path.read_bytes()
    task = json.loads(task_bytes)
    files = set(staged_paths(root))
    outside = files - set(task.get("allowed_files", []))
    if outside:
        print("Worker checkpoint: BLOCKED, staged files outside task: " + ", ".join(sorted(outside)))
        return 1  # Deterministic scope failure; do not send unrelated files to a model.
    output = args.output or Path(git(root, "rev-parse", "--git-path", "worker-reviews").decode().strip()) / str(time.time_ns())
    if not output.is_absolute():
        output = root / output
    checkpoint = staged_checkpoint(root, task, output)
    manifest_path = output / "index.json"
    captured = json.loads(manifest_path.read_text())
    captured.update(source_task_path=str(task_path),
                    source_task_sha256=hashlib.sha256(task_bytes).hexdigest(),
                    test_receipts="reported; execution against this index is not independently verified")
    manifest_path.write_text(json.dumps(captured, indent=2) + "\n")
    if args.model_advice or args.prepare_only:
        review = review_checkpoint(checkpoint, output / "review", backend=args.backend,
                                  env_file=args.env_file, prepare_only=args.prepare_only, base_dir=root)
        lines = (output / "review" / "examples.jsonl").read_text().splitlines()
        print(f"Worker checkpoint: optional advice at {output / 'review'}")
    else:
        review = {"deterministic": deterministic_findings(validate_checkpoint(checkpoint), root)}
        (output / "deterministic.json").write_text(json.dumps(review) + "\n")
        lines = []
        print("Worker checkpoint: deterministic checks only; model advice is optional and was not requested.")
    for line in lines:
        row = json.loads(line)
        if row["model_status"] != "advisory":
            print(f"{row['provider']}: NOT REVIEWED ({row.get('error') or row['model_status']})")
            continue
        for question, answer in row["response"]["answers"].items():
            choice = answer["choice"]
            probability = answer["probabilities"].get(choice)
            print(f"{row['provider']} {question}: {choice}, probability={probability}, confidence={answer['confidence']}")
    print("Model scores require coordinator interpretation; this hook does not certify correctness.")
    # A concurrent index mutation invalidates the reviewed diff.
    if git(root, "write-tree").decode().strip() != captured["index_tree"]:
        print("Worker checkpoint: BLOCKED, staged tree changed during review.")
        return 1
    if git(root, "rev-parse", "HEAD").decode().strip() != captured["head"]:
        print("Worker checkpoint: BLOCKED, HEAD changed during review.")
        return 1
    if not task_path.is_file() or hashlib.sha256(task_path.read_bytes()).hexdigest() != captured["source_task_sha256"]:
        print("Worker checkpoint: BLOCKED, current task changed during review.")
        return 1
    return 1 if review["deterministic"]["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
