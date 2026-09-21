"""Cheap build prerequisites and mechanically generated graph file references."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.raid_program.development_graph import STATE_PATH, check_state, file_ref, read, snapshot, source_binding

ROOT = Path(__file__).resolve().parents[2]


def build_commands(policy: dict) -> dict:
    """Use the queue's exact policy contract, including generator and fan-out."""
    from tools.raid_program import queued_build as queue
    settings = queue.expected_build_configuration(policy)
    if not settings:
        raise ValueError("workflow build requires a policy with frozen CMake settings")
    cmake = policy["mechanical_controls"]["cmake_executable"]
    jobs = int(policy["parallelism"]["maximum_compiler_jobs"])
    commands = {
        "configure": [cmake, "-S", ".", "-B", "build", "-G", settings["CMAKE_GENERATOR"],
                      *(f"-D{k}={v}" for k, v in settings.items())],
        "worldserver_build": [cmake, "--build", "build", "--target", "worldserver", "--parallel", str(jobs)],
    }
    for kind, command in commands.items():
        queue.validate_command(command, jobs, resource_class=kind, policy=policy)
    return commands


def run_build(root: Path) -> dict:
    """Configure and build one frozen source without intervening Git writes.

    Queue-owned, unique receipts stay outside the tracked source. No graph
    transition or automatic retry occurs here; failed receipts remain reusable.
    """
    from tools.raid_program import queued_build as queue
    state = read(root / STATE_PATH)
    check_state(root, state)
    graph = state["development_graph"]
    if graph["stage"] != "build" or graph.get("claim", {}).get("stage") != "build":
        raise ValueError("claim the build stage and commit its state before workflow_build run")
    assignment = graph["assignment"]
    preflight(root, assignment)
    source_binding(root, assignment, graph["tested_commit"])
    if snapshot(root, assignment["owned_files"]) != graph["tested_files"]:
        raise ValueError("owned files changed after review")
    identity = queue.worktree_state(root)
    if not identity["clean"]:
        raise ValueError("commit source, review and build claim before workflow_build run")
    policy = read(file_ref(root, assignment["policy"]))
    commands = build_commands(policy)
    results = {"source_commit": identity["commit"], "steps": [], "success": False}
    for kind, command in commands.items():
        if queue.worktree_state(root) != identity:
            raise ValueError("source changed between configure and build; reconcile retained queue receipts")
        print(json.dumps({"step": kind, "command": command}), flush=True)
        code, receipt = queue.run_ticket(root, policy, kind, command, None, None, None)
        path = queue.Paths.for_worktree(root).receipts / (receipt["ticket_id"] + ".json")
        results["steps"].append({"step": kind, "receipt": str(path), "exit_status": code})
        if code or receipt.get("classification") != "success":
            return results
        verification = queue.verify_receipt(path, policy, allow_test_mode=False)
        if verification.get("gate_bearing") is not True:
            raise ValueError("queued receipt is not gate-bearing: " + str(path))
    results["success"] = True
    return results


def preflight(root: Path, assignment: dict) -> dict:
    """Run before a build claim; launch repeats checks against the final inputs."""
    # Reject role/evidence policies here, before tests, review or a build claim.
    commands = build_commands(read(file_ref(root, assignment.get("policy"))))
    identity = assignment["validation_identity"]
    for name in ("roster", "runtime_profile"):
        file_ref(root, identity.get(name))
    kind = identity.get("scenario_kind")
    result = {"schema": "raid_workflow_build_preflight_v1", "scenario_kind": kind,
              "validation_identity": identity, "commands": commands}
    if kind == "dummy":
        file_ref(root, identity.get("reference"))
        if root.resolve() != ROOT:
            raise ValueError("run calibration build preflight from the coordinator checkout's module")
        from tools.bot_ml.run_live_bot_validation import preflight_calibration_reference_binding
        calibration_mode = str(identity.get("mode") or "single_target_300")
        result["reference"] = preflight_calibration_reference_binding(
            calibration_only=True, calibration_mode=calibration_mode,
            target_spec=identity["spec"])
    elif kind == "raid":
        file_ref(root, identity.get("route"))
    else:
        raise ValueError("unknown validation scenario kind")
    result["valid"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    sub.add_parser("run", help="After committing a reviewed build claim, configure and build once through queued_build")
    sub.add_parser("commands", help="Print exact policy argv without configuring or compiling")
    sub.add_parser("snapshot", help="Hash current assignment owned_files; does not attest tests/review")
    refs = sub.add_parser("refs", help="Generate path/sha256 references; never type hashes manually")
    refs.add_argument("paths", nargs="+")
    args = parser.parse_args()
    if args.command == "run":
        result = run_build(ROOT)
    elif args.command == "refs":
        paths = [Path(p).resolve().relative_to(ROOT).as_posix() for p in args.paths]
        result = [{"path": p, "sha256": sha} for p, sha in snapshot(ROOT, paths).items()]
    else:
        assignment = read(ROOT / STATE_PATH)["development_graph"].get("assignment")
        if not assignment:
            raise ValueError("record the bounded plan before preparing a build")
        if args.command == "commands":
            result = build_commands(read(file_ref(ROOT, assignment["policy"])))
        else:
            result = preflight(ROOT, assignment) if args.command == "preflight" else snapshot(ROOT, assignment["owned_files"])
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.command == "run" and not result["success"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
