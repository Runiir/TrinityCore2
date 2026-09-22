"""Prepare and apply one hash-bound development-graph advance event.

The development graph is the authority for workflow transitions.  This small
adapter only fills in the values that are safe to derive from the current
state: the current revision and unit identity, the receipt's byte hash, and a
claimed operation's token after checking its owner.  It deliberately does not
create claims or edit the state file itself.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from tools.raid_program import development_graph as graph


ROOT = Path(__file__).resolve().parents[2]


def _repo_relative(root: Path, value: str | Path) -> tuple[str, Path]:
    """Resolve a receipt inside ``root`` and return its canonical repo path."""

    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise graph.GraphError("receipt path required")
    candidate = Path(value).expanduser()
    root_resolved = root.resolve()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root_resolved / candidate).resolve()
    if not resolved.is_relative_to(root_resolved):
        raise graph.GraphError("receipt must be inside the coordinator worktree")
    if not resolved.is_file():
        raise graph.GraphError("receipt must be an existing file")
    return resolved.relative_to(root_resolved).as_posix(), resolved


def _state_snapshot(root: Path) -> tuple[dict[str, Any], str]:
    """Read and validate one state snapshot before constructing an event."""

    path = root / graph.STATE_PATH
    try:
        data = path.read_bytes()
        state = json.loads(data)
    except (OSError, json.JSONDecodeError) as exc:
        raise graph.GraphError("invalid workflow state") from exc
    if not isinstance(state, dict):
        raise graph.GraphError("workflow state must be a JSON object")
    graph.check_state(root, state)
    return state, graph.digest(data)


def _claimed_token(g: dict[str, Any], owner: str | None) -> str | None:
    """Return a claim token only after the caller proves the claim owner."""

    claim = g.get("claim")
    if not claim:
        return None
    if not isinstance(claim, dict):
        raise graph.GraphError("invalid workflow claim")
    if not isinstance(owner, str) or not owner:
        raise graph.GraphError("explicit owner required for claimed operation")
    if claim.get("owner") != owner:
        raise graph.GraphError("claim owner mismatch")
    token = claim.get("token")
    if not isinstance(token, str) or not token:
        raise graph.GraphError("claimed operation has no token")
    return token


def receipt_reference(root: Path, receipt: str | Path) -> dict[str, str]:
    """Return a path/hash reference computed from the receipt's current bytes."""

    relative, path = _repo_relative(root, receipt)
    reference = {"path": relative, "sha256": graph.digest(path.read_bytes())}
    # Keep path and hash validation identical to reducer validation.
    graph.file_ref(root, reference)
    return reference


def prepare_event(
    root: Path,
    receipt: str | Path,
    *,
    owner: str | None = None,
    action: str = "advance",
    recorded_source: bool = False,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Build an advance event from one validated state snapshot.

    The returned state hash is the compare-and-swap value to pass to
    :func:`development_graph.advance`.  Callers must not replace it with a
    newly calculated value after doing work.
    """

    state, state_sha256 = _state_snapshot(root)
    development = state["development_graph"]
    if action == "advance":
        if development["stage"] not in graph.RECEIPTS:
            raise graph.GraphError("current stage does not accept an advance")
    elif action == "refresh_support":
        if development["stage"] != "implement":
            raise graph.GraphError("support refresh is only valid during implementation")
    else:
        raise graph.GraphError("unsupported workflow action: " + str(action))
    event: dict[str, Any] = {
        "revision": development["revision"],
        "unit_id": development["unit"]["id"],
        "action": action,
        "receipt": receipt_reference(root, receipt),
    }
    token = _claimed_token(development, owner)
    if token is not None:
        event["claim_token"] = token
    if recorded_source:
        if action != 'advance':
            raise graph.GraphError('--recorded-source is only for validation advance')
        from tools.raid_program.completed_operation import find_launch_commit
        event['recorded_source_commit'] = find_launch_commit(root, development)
    return event, state_sha256, state


def _dry_run_result(
    root: Path,
    event: dict[str, Any],
    state_sha256: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Run the real reducer against a copy and return a compact preview."""

    candidate = graph.reduce(root, copy.deepcopy(state), event)
    graph.check_state(root, candidate)
    old_graph = state["development_graph"]
    new_graph = candidate["development_graph"]
    return {
        "dry_run": True,
        "state_sha256": state_sha256,
        "event": event,
        "from_stage": old_graph["stage"],
        "to_stage": new_graph["stage"],
        "revision": new_graph["revision"],
        "unit_id": new_graph["unit"]["id"],
        "next_command_hint": "pixi run python -m tools.raid_program.raid_workloop resume",
    }


def _resume_projection(result: dict[str, Any]) -> dict[str, Any]:
    """Keep CLI output useful without returning the complete bootstrap state."""

    return {
        "state_sha256": result["state_sha256"],
        "revision": result["revision"],
        "stage": result["stage"],
        "claim": result.get("claim"),
        "unit": {key: result["unit"].get(key) for key in ('id', 'edge', 'owner_skill', 'requirements', 'next_action')},
        "next_action": result["next_action"],
        "open_requirements": sorted(result.get("open_requirements", {})),
        "receipts": result.get("receipts", {}),
        "next_command_hint": "pixi run python -m tools.raid_program.evidence_view task --max-chars 6000",
    }


def apply_step(
    root: Path,
    receipt: str | Path,
    *,
    owner: str | None = None,
    expected_sha256: str | None = None,
    dry_run: bool = False,
    action: str = "advance",
    recorded_source: bool = False,
) -> dict[str, Any]:
    """Validate and optionally commit one advance through the graph API."""

    event, state_sha256, state = prepare_event(root, receipt, owner=owner, action=action,
                                             recorded_source=recorded_source)
    if expected_sha256 is not None and expected_sha256 != state_sha256:
        raise graph.GraphError("state changed; resume before applying this event")
    preview = _dry_run_result(root, event, state_sha256, state)
    if dry_run:
        return preview
    result = graph.advance(root, event, state_sha256)
    return {
        **preview,
        "dry_run": False,
        **_resume_projection(result),
        "new_state_sha256": result["state_sha256"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    worker = commands.add_parser('packet', help='Assemble bounded worker context from the admitted plan')
    worker.add_argument('--output', type=Path, help='Write the packet; stdout contains only its path/hash')
    advance = commands.add_parser("advance", help="derive and apply one advance event")
    advance.add_argument("receipt_positional", nargs="?", type=Path)
    advance.add_argument("--receipt", dest="receipt_option", type=Path)
    advance.add_argument("--owner", help="required when the current operation is claimed")
    advance.add_argument("--action", choices=("advance", "refresh_support"), default="advance")
    advance.add_argument("--expect", "--expected-state-sha256", dest="expected_sha256")
    advance.add_argument("--dry-run", action="store_true", help="validate through the reducer without writing")
    advance.add_argument("--recorded-source", action="store_true",
                         help="close an already completed run against its committed launch snapshot; no current-source acceptance")
    advance.add_argument("--root", dest="subcommand_root", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == 'packet':
        from tools.raid_program.worker_packet import packet
        try:
            result = packet(args.root.resolve())
            payload = (json.dumps(result, sort_keys=True) + '\n').encode()
            if args.output:
                args.output.write_bytes(payload)
                result = {'packet': str(args.output), 'sha256': graph.digest(payload),
                          'bytes': len(payload), 'unit_id': result['unit_id']}
        except (graph.GraphError, OSError, ValueError) as exc:
            print(json.dumps({'error': str(exc)}), file=sys.stderr)
            return 2
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command != "advance":
        raise AssertionError("unhandled workflow command")
    receipt = args.receipt_option or args.receipt_positional
    if receipt is None or (args.receipt_option is not None and args.receipt_positional is not None):
        print(json.dumps({"error": "provide exactly one receipt path"}), file=sys.stderr)
        return 2
    root = (args.subcommand_root or args.root).resolve()
    try:
        result = apply_step(
            root,
            receipt,
            owner=args.owner,
            expected_sha256=args.expected_sha256,
            dry_run=args.dry_run,
            action=args.action,
            recorded_source=args.recorded_source,
        )
    except (graph.GraphError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
