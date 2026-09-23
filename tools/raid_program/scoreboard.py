"""Raid scoreboard: numeric WCL target, per-kill records and a batch verdict.

Each scenario has a target file (experiments/configs/raid_targets/<scenario>.json)
and a scoreboard (artifacts/cata_raid_program/scoreboard/<scenario>.jsonl) with
one JSON line per kill, plus evidence-attachment and void lines. A label is one
build and one batch; a verdict is taken over that label's counted kills, never
from a single run.

    pixi run python -m tools.raid_program.scoreboard run --scenario S --label L --dry-run
    pixi run python -m tools.raid_program.scoreboard ingest --scenario S --label L --summary FILE
    pixi run python -m tools.raid_program.scoreboard show --scenario S [--label L] [--vs L2] [--actor A] [--min-kills N]
    pixi run python -m tools.raid_program.scoreboard verdict --scenario S [--label L]
    pixi run python -m tools.raid_program.scoreboard baseline --scenario S [--label L --reason TEXT [--force]]
    pixi run python -m tools.raid_program.scoreboard archive-pending --scenario S
    pixi run python -m tools.raid_program.scoreboard void --scenario S --kill-id K --reason TEXT
    pixi run python -m tools.raid_program.scoreboard rng-backfill --scenario S --label L --evidence-root DIR

Only the coordinator runs `run` without --dry-run: it launches live kills.

The baseline pointer (<scenario>.baseline.json next to the scoreboard) names the kept label.
`verdict` (and evaluate_target) without a label judges the baseline, else the latest label;
`show` without --vs compares the shown label against the baseline when they differ. The
keep/revert decision needs kills_per_batch counted native clears per label (--min-kills N overrides).

Python API: evaluate_target(root, scenario, label=None) and
compare_labels(root, scenario, new_label, old_label).
"""
from __future__ import annotations

import argparse
import getpass
import json
import re
from pathlib import Path

from tools.raid_program.scoreboard_compare import NON_GAMEPLAY_EXCLUSIONS, compare_labels
from tools.raid_program.scoreboard_core import (
    exclusion_reason,
    BASELINE_SCHEMA, KILL_SCHEMA, ROOT, VERDICT_SCHEMA, VOID_SCHEMA, append_record, baseline_path, clear_kills,
    counted_kills, git_head, label_kills, load_baseline, load_records, load_target, party_reference_dps,
    scoreboard_path, spec_targets, utc_now,
)
from tools.raid_program.scoreboard_verdict import evaluate_target

__all__ = ["evaluate_target", "compare_labels", "load_records", "load_target", "spec_targets",
           "party_reference_dps", "append_record", "scoreboard_path", "void_kill", "set_baseline", "load_baseline", "main",
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


def baseline_problems(kills: list[dict]) -> list[str]:
    """Why a label is not a clean baseline: counted non-clears and counted kills with boss-window deaths."""
    counted = counted_kills(kills)
    # Same blocking set as keep condition (a): every recorded gameplay kill, not only counted ones.
    problems = [f"kill {record['kill_id']} is not a native clear" for record in kills
                if not record.get("native_clear") and exclusion_reason(record) not in NON_GAMEPLAY_EXCLUSIONS]
    problems += [f"counted kill {record['kill_id']} has "
                 + ("unknown" if record.get("boss_window_deaths") is None else str(record["boss_window_deaths"]))
                 + " boss-window death(s)" for record in counted if record.get("boss_window_deaths") != 0]
    return problems


def set_baseline(root: Path, scenario: str, label: str, reason: str | None = None, force: bool = False) -> dict:
    """Point the scenario's baseline at a label with >= kills_per_measurement counted native clears on one build.

    A label with a counted non-clear or a counted boss-window death (or an unknown count) is refused
    unless force is set with a reason; the overridden problems are recorded in the pointer.
    """
    reason = (reason or "").strip() or None
    target = load_target(root, scenario)
    required = int(target.get("kills_per_batch") or target["kills_per_measurement"])
    kills = label_kills(load_records(root, scenario), label)
    if not kills:
        raise SystemExit(f"no kills recorded for label {label!r} in {scenario}")
    builds = {(record.get("worldserver_sha256"), record.get("source_commit")) for record in counted_kills(kills)}
    if len(builds) > 1:
        raise SystemExit(f"label {label} mixes builds in its counted kills: "
                         + ", ".join(sorted(f"{str(sha)[:12]}/{str(commit)[:12]}" for sha, commit in builds)))
    clears = clear_kills(kills)
    if len(clears) < required:
        raise SystemExit(f"label {label} has {len(clears)} counted native-clear kill(s); a baseline needs "
                         f">= {required} (kills_per_batch)")
    (sha, commit), = builds
    if not sha or not commit:
        raise SystemExit(f"label {label} lacks a worldserver_sha256 or source_commit on its counted kills")
    problems = baseline_problems(kills)
    if problems and not force:
        raise SystemExit(f"label {label} is not a clean baseline: {'; '.join(problems)}. "
                         "Pass --force --reason TEXT to set it anyway.")
    if force and not reason:
        raise SystemExit("--force needs --reason explaining why this label is the baseline anyway")
    baseline = {"schema": BASELINE_SCHEMA, "scenario": scenario, "label": label, "set_at": utc_now(),
                "source_commit": commit, "worldserver_sha256": sha, "counted_kills": len(clears),
                "reason": reason}
    if problems:
        baseline["forced_over"] = problems
    path = baseline_path(root, scenario)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, indent=1, sort_keys=True) + "\n")
    return baseline


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive number of kills")
    return number


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
    run.add_argument("--kills", type=int, help="default: the target's kills_per_batch (else kills_per_measurement)")
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
    show.add_argument("--vs", help="label to compare against (default: the baseline when it differs from --label)")
    show.add_argument("--actor", help="actor id the change targeted (for the keep/revert rule)")
    show.add_argument("--min-kills", type=_positive, dest="batch_kills",
                      help="override the target's kills_per_batch for the keep decision (printed in the decision)")

    verdict = commands.add_parser("verdict", help="print the evaluate_target JSON")
    verdict.add_argument("--scenario", required=True)
    verdict.add_argument("--label", help="default: the baseline label, else the most recently recorded label")

    base = commands.add_parser("baseline", help="print the scenario's baseline pointer, or set it with --label")
    base.add_argument("--scenario", required=True)
    base.add_argument("--label", type=_label,
                      help="set the baseline (needs kills_per_batch counted native clears on one binary/commit)")
    base.add_argument("--reason", help="with --label: why this label is the kept state (recorded)")
    base.add_argument("--force", action="store_true",
                      help="with --label and --reason: accept counted non-clears or boss-window deaths (recorded)")

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
    if args.command == "verdict":  # without --label evaluate_target judges the baseline and names it on stderr
        print(json.dumps(evaluate_target(root, args.scenario, args.label), indent=1, sort_keys=True))
        return 0
    if args.command == "baseline":
        if args.label is None:
            if args.reason or args.force:
                parser.error("--reason and --force need --label")
            current = load_baseline(root, args.scenario)
            print(json.dumps(current, indent=1, sort_keys=True) if current else
                  f"no baseline set for {args.scenario} (scoreboard baseline --scenario {args.scenario} --label L)")
            return 0
        written = set_baseline(root, args.scenario, args.label, args.reason, args.force)
        print(json.dumps(written, indent=1, sort_keys=True))
        print(f"baseline for {args.scenario} is now {written['label']}: {baseline_path(root, args.scenario)}")
        return 0
    if args.command == "show":
        from tools.raid_program.scoreboard_show import render
        print(render(root, args.scenario, args.label, args.vs, args.actor, args.batch_kills))
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
