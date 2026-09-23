"""Raid scoreboard: numeric WCL target, per-kill records and a batch verdict.

Each scenario has a target file (experiments/configs/raid_targets/<scenario>.json)
and a scoreboard (artifacts/cata_raid_program/scoreboard/<scenario>.jsonl) with
one JSON line per kill, plus evidence-attachment and void lines. A label is one
build and one batch; a verdict is taken over that label's counted kills, never
from a single run.

    pixi run python -m tools.raid_program.scoreboard run --scenario S --label L --dry-run
    pixi run python -m tools.raid_program.scoreboard ingest --scenario S --label L --summary FILE
    pixi run python -m tools.raid_program.scoreboard show --scenario S --label L --vs L2
    pixi run python -m tools.raid_program.scoreboard verdict --scenario S --label L
    pixi run python -m tools.raid_program.scoreboard archive-pending --scenario S
    pixi run python -m tools.raid_program.scoreboard void --scenario S --kill-id K --reason TEXT
    pixi run python -m tools.raid_program.scoreboard rng-backfill --scenario S --label L --evidence-root DIR

Only the coordinator runs `run` without --dry-run: it launches live kills.

Python API: evaluate_target(root, scenario, label=None) and
compare_labels(root, scenario, new_label, old_label).
"""
from __future__ import annotations

import argparse
import getpass
import json
import re
from pathlib import Path

from tools.raid_program.scoreboard_compare import compare_labels
from tools.raid_program.scoreboard_core import (
    KILL_SCHEMA, ROOT, VERDICT_SCHEMA, VOID_SCHEMA, append_record, git_head, load_records, load_target,
    party_reference_dps, scoreboard_path, spec_targets, utc_now,
)
from tools.raid_program.scoreboard_verdict import evaluate_target

__all__ = ["evaluate_target", "compare_labels", "load_records", "load_target", "spec_targets",
           "party_reference_dps", "append_record", "scoreboard_path", "void_kill", "main",
           "KILL_SCHEMA", "VERDICT_SCHEMA"]

LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def void_kill(root: Path, scenario: str, kill_id: str, reason: str) -> dict:
    """Append an audited void line; the kill stays in the file but no longer counts."""
    records = {record["kill_id"]: record for record in load_records(root, scenario)}
    if kill_id not in records:
        raise SystemExit(f"unknown kill_id {kill_id!r} in {scenario}")
    if records[kill_id].get("voided"):
        raise SystemExit(f"kill {kill_id} is already voided: {records[kill_id]['voided']['reason']}")
    if not reason.strip():
        raise SystemExit("--reason must explain why the kill is voided")
    line = {"schema": VOID_SCHEMA, "kill_id": kill_id, "reason": reason.strip(), "recorded_at": utc_now(),
            "recorded_by": getpass.getuser(), "source_commit": git_head(root)}
    append_record(root, scenario, line)
    return line


def _label(value: str) -> str:
    if not LABEL_RE.match(value):
        raise argparse.ArgumentTypeError("labels use letters, digits, '.', '_' and '-' only")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run N live kills under a new label, record and archive each")
    run.add_argument("--scenario", required=True)
    run.add_argument("--label", required=True, type=_label, help="must not have kills yet")
    run.add_argument("--kills", type=int, help="default: the target's kills_per_measurement")
    run.add_argument("--worldserver", type=Path, help="default: the target's run_plan.default_worldserver")
    run.add_argument("--source-commit", help="default: git HEAD")
    run.add_argument("--dry-run", action="store_true", help="print the plan and run nothing")
    run.add_argument("--top-up", action="store_true",
                     help="add kills to an existing label whose kills were excluded only for measurement reasons "
                          "(stall, infrastructure); same binary and source commit required")
    run.add_argument("--target-kills", type=int,
                     help="with --top-up: counted native clears to reach (default kills_per_measurement); "
                          "raise it on both compared labels for a smaller expected effect")

    ingest = commands.add_parser("ingest", help="record existing kills (summary JSON or raw run dir)")
    ingest.add_argument("--scenario", required=True)
    ingest.add_argument("--label", required=True, type=_label)
    source = ingest.add_mutually_exclusive_group(required=True)
    source.add_argument("--summary", type=Path, nargs="+", help="magmaw_spell_queue_run_summary_v1 files")
    source.add_argument("--run-dir", type=Path, help="one closed live-validation run directory")
    ingest.add_argument("--timeline", type=Path, nargs="+",
                        help="WCL timeline comparison per summary/run (computed for --run-dir when omitted)")
    ingest.add_argument("--evidence-pointer", nargs="+", help="DVC pointer per summary/run, repo-relative")
    ingest.add_argument("--evidence-root", type=Path,
                        help="read-only folder holding the raw run dirs named by the summaries (for deaths)")
    ingest.add_argument("--source-commit", nargs="+", help="source commit per summary/run (one value applies to all)")
    ingest.add_argument("--worldserver-sha256", help="--run-dir only: used when report.json lacks it")

    show = commands.add_parser("show", help="per-actor table, optional Welch comparison with another label")
    show.add_argument("--scenario", required=True)
    show.add_argument("--label", help="default: the most recently recorded label")
    show.add_argument("--vs", help="baseline label to compare against")
    show.add_argument("--actor", help="actor id the change targeted (for the keep/revert rule)")

    verdict = commands.add_parser("verdict", help="print the evaluate_target JSON")
    verdict.add_argument("--scenario", required=True)
    verdict.add_argument("--label")

    pending = commands.add_parser("archive-pending", help="archive kept /tmp evidence of kills without a pointer")
    pending.add_argument("--scenario", required=True)

    void = commands.add_parser("void", help="exclude one kill with an audited reason")
    void.add_argument("--scenario", required=True)
    void.add_argument("--kill-id", required=True)
    void.add_argument("--reason", required=True)

    backfill = commands.add_parser(
        "rng-backfill", help="attach informational encounter RNG (e.g. Massive Crash side) to older kills")
    backfill.add_argument("--scenario", required=True)
    backfill.add_argument("--label", required=True, type=_label)
    backfill.add_argument("--evidence-root", required=True, type=Path,
                          help="read-only folder holding the label's extracted run dirs")

    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.command == "verdict":
        print(json.dumps(evaluate_target(root, args.scenario, args.label), indent=1, sort_keys=True))
        return 0
    if args.command == "show":
        from tools.raid_program.scoreboard_show import render
        print(render(root, args.scenario, args.label, args.vs, args.actor))
        return 0
    if args.command == "void":
        line = void_kill(root, args.scenario, args.kill_id, args.reason)
        print(f"voided {line['kill_id']}: {line['reason']}")
        return 0
    if args.command == "rng-backfill":
        from tools.raid_program.scoreboard_record import rng_backfill
        return rng_backfill(root, args.scenario, args.label, args.evidence_root)
    if args.command == "ingest":
        from tools.raid_program.scoreboard_record import ingest as run_ingest
        return run_ingest(root, args)
    from tools.raid_program.scoreboard_run import archive_pending, run_batch
    if args.command == "archive-pending":
        return archive_pending(root, args.scenario)
    try:
        return run_batch(root, args)
    except KeyboardInterrupt:
        print("batch interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
