"""Cheap build prerequisites and mechanically generated graph file references."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.raid_program.development_graph import STATE_PATH, file_ref, read, snapshot

ROOT = Path(__file__).resolve().parents[2]


def preflight(root: Path, assignment: dict) -> dict:
    """Run before a build claim; launch repeats checks against the final inputs."""
    file_ref(root, assignment.get("policy"))
    identity = assignment["validation_identity"]
    for name in ("roster", "runtime_profile"):
        file_ref(root, identity.get(name))
    kind = identity.get("scenario_kind")
    result = {"schema": "raid_workflow_build_preflight_v1", "scenario_kind": kind,
              "validation_identity": identity}
    if kind == "dummy":
        file_ref(root, identity.get("reference"))
        if root.resolve() != ROOT:
            raise ValueError("run calibration build preflight from the coordinator checkout's module")
        from tools.bot_ml.run_live_bot_validation import preflight_calibration_reference_binding
        result["reference"] = preflight_calibration_reference_binding(
            calibration_only=True, calibration_mode="single_target_300",
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
    sub.add_parser("snapshot", help="Hash current assignment owned_files; does not attest tests/review")
    refs = sub.add_parser("refs", help="Generate path/sha256 references; never type hashes manually")
    refs.add_argument("paths", nargs="+")
    args = parser.parse_args()
    if args.command == "refs":
        paths = [Path(p).resolve().relative_to(ROOT).as_posix() for p in args.paths]
        result = [{"path": p, "sha256": sha} for p, sha in snapshot(ROOT, paths).items()]
    else:
        assignment = read(ROOT / STATE_PATH)["development_graph"].get("assignment")
        if not assignment:
            raise ValueError("record the bounded plan before preparing a build")
        result = preflight(ROOT, assignment) if args.command == "preflight" else snapshot(ROOT, assignment["owned_files"])
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
