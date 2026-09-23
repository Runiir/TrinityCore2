"""Run one labelled batch of live kills: validate, summarize, record, archive.

A label is one build and one batch: `run` refuses a label that already has
kills (unless `--top-up` replaces kills excluded for measurement reasons with
the same binary and source commit), and copies the worldserver once to /tmp/worldserver-<sha12> so a rebuild
cannot change the binary mid-batch. Each kill runs the target's
bot-live-validate argv template into /tmp/scoreboard-<label>-k<i>-<timestamp>.
Whatever happens afterwards, one kill record is appended and archiving is
attempted; failures are recorded (postprocess_error, archive_error) and the
/tmp evidence is kept for `archive-pending`.
"""
from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any

from tools.raid_program.scoreboard_core import (
    ATTACHMENT_SCHEMA, EVIDENCE_DIR, KILL_SCHEMA, append_record, clear_kills, exclusion_reason, file_sha256, git_head,
    label_kills, load_records, load_target, scoreboard_path, utc_now,
)
from tools.raid_program.scoreboard_record import (
    fallback_record, kill_line, record_from_run_dir, write_timeline,
)

PIN_DIR = Path("/tmp")
KILL_GRACE_SEC = 30


def stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def plan_kills(target: dict[str, Any], *, label: str, kills: int, worldserver: Path, batch: str) -> list[dict[str, Any]]:
    """Exact argv and paths for each kill; nothing is created."""
    plan = []
    pattern = target["run_plan"].get("output_dir_pattern", "/tmp/scoreboard-{label}-k{kill}-{timestamp}")
    for index in range(1, kills + 1):
        output_dir = Path(pattern.format(label=label, kill=index, timestamp=batch))
        values = {"{worldserver}": str(worldserver), "{output_dir}": str(output_dir)}
        plan.append({
            "kill": index,
            "kill_id": f"{label}-k{index}-{batch}",
            "argv": [values.get(arg, arg) for arg in target["run_plan"]["argv_template"]],
            "output_dir": output_dir,
            "analysis_dir": Path(f"{output_dir}-analysis"),
            "stdout": Path(f"{output_dir}.stdout"),
            "stderr": Path(f"{output_dir}.stderr"),
        })
    return plan


def evidence_sources(kill: dict[str, Any]) -> list[Path]:
    return [kill["output_dir"], kill["analysis_dir"], kill["stdout"], kill["stderr"]]


def archive_base(scenario: str, kill_id: str) -> str:
    return f"scoreboard_{scenario}_{kill_id}"


def archive_argv(name: str, sources: list[Path]) -> list[str]:
    return ["pixi", "run", "python", "-m", "experiments.archive_run_evidence", "--name", name, *map(str, sources)]


def _leftovers(root: Path, base: str) -> list[Path]:
    return sorted((root / EVIDENCE_DIR).glob(f"{base}*"))


def _fresh_name(root: Path, base: str) -> str:
    """The first free archive name: a leftover pointer or tarball never blocks a retry."""
    name, attempt = base, 0
    while any((root / EVIDENCE_DIR).glob(f"{name}.*")):
        attempt += 1
        name = f"{base}_retry{attempt}"
    return name


def archive_evidence(root: Path, scenario: str, kill_id: str, sources: list[Path],
                     recorded_pointers: set[str]) -> tuple[str | None, str | None]:
    """Archive through experiments.archive_run_evidence; returns (pointer, error)."""
    existing = [path for path in sources if path.exists()]
    if not existing:
        return None, "no evidence paths exist"
    base = archive_base(scenario, kill_id)
    stale = [path for path in _leftovers(root, base) if str(path.relative_to(root)) not in recorded_pointers]
    if stale:
        print("left behind by an earlier archive attempt (not removed): "
              + ", ".join(str(path.relative_to(root)) for path in stale))
    name = _fresh_name(root, base)
    pointer = f"{EVIDENCE_DIR}/{name}.tar.gz.dvc"
    try:
        returncode = subprocess.run(archive_argv(name, existing), cwd=root).returncode
    except Exception as error:
        returncode, detail = None, f"{type(error).__name__}: {error}"
    else:
        detail = f"exit {returncode}"
    if returncode == 0 and (root / pointer).exists():
        return pointer, None
    left = [str(path.relative_to(root)) for path in _leftovers(root, name)]
    if left:
        print(f"left behind by the failed archive {name}: {', '.join(left)}")
    return None, f"archive_run_evidence failed ({detail}) for {name}"


def pin_worldserver(worldserver: Path) -> tuple[Path, str]:
    """Copy the binary once; the copy's bytes name it, so a concurrent rebuild cannot slip in."""
    partial = PIN_DIR / f"worldserver-pinning-{os.getpid()}.partial"
    shutil.copy2(worldserver, partial)
    sha = file_sha256(partial)
    pinned = PIN_DIR / f"worldserver-{sha[:12]}"
    if pinned.exists() and file_sha256(pinned) == sha:
        partial.unlink()
    else:
        partial.replace(pinned)
    return pinned, sha


def run_harness(argv: list[str], cwd: Path, stdout, stderr) -> int:
    """Run in its own session; the whole process group dies on interrupt or error."""
    process = subprocess.Popen(argv, cwd=cwd, stdout=stdout, stderr=stderr, start_new_session=True)
    try:
        return process.wait()
    except BaseException:
        for sig, grace in ((signal.SIGTERM, KILL_GRACE_SEC), (signal.SIGKILL, None)):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                break
            try:
                process.wait(timeout=grace)
                break
            except subprocess.TimeoutExpired:
                continue
        raise


def _base_record(scenario: str, label: str, kill: dict[str, Any], sha: str, source_commit: str | None) -> dict[str, Any]:
    return {"schema": KILL_SCHEMA, "kill_id": kill["kill_id"], "scenario": scenario, "label": label,
            "recorded_at": utc_now(), "source_commit": source_commit, "worldserver_sha256": sha,
            "run_dir": str(kill["output_dir"]), "evidence_dvc_pointer": None, "native_clear": False,
            "native_reason": None, "completion_reason": None, "outcome": "unknown", "route_deaths": None,
            "boss_window_deaths": None, "death_basis": "unknown", "deaths": [], "encounter": None,
            "actors": [], "ranked_gaps": []}


def _postprocess(root, target, scenario, label, kill, sha, source_commit) -> dict[str, Any]:
    options = dict(scenario=scenario, label=label, kill_id=kill["kill_id"], run_dir=kill["output_dir"],
                   source_commit=source_commit, worldserver_sha256=sha)
    try:
        kill["analysis_dir"].mkdir(parents=True, exist_ok=True)
        timeline = write_timeline(kill["output_dir"], root / target["wcl_cast_timelines"],
                                  kill["analysis_dir"] / "timeline.json") if target.get("wcl_cast_timelines") else None
        return record_from_run_dir(root, target, timeline_path=timeline,
                                   summary_output=kill["analysis_dir"] / "summary.json", **options)
    except Exception as error:
        traceback.print_exc()
        message = f"{type(error).__name__}: {error}"
    try:
        record = fallback_record(root, target, **options)
    except Exception as error:
        record = _base_record(scenario, label, kill, sha, source_commit)
        message += f"; fallback failed: {type(error).__name__}: {error}"
    return record | {"postprocess_error": message}


def run_kill(root: Path, target: dict[str, Any], *, scenario: str, label: str, kill: dict[str, Any],
             sha: str, source_commit: str | None, recorded_pointers: set[str]) -> bool:
    """One kill end to end. Returns True when the batch may continue."""
    for path in evidence_sources(kill):
        if path.exists():
            raise SystemExit(f"refusing to reuse an existing path: {path}")
    print(f"kill k{kill['kill']}: {shlex.join(kill['argv'])}", flush=True)
    try:
        with kill["stdout"].open("w") as out, kill["stderr"].open("w") as err:
            exit_code = run_harness(kill["argv"], root, out, err)
    except BaseException as error:
        record = _base_record(scenario, label, kill, sha, source_commit) | {
            "outcome": "interrupted", "interrupted": type(error).__name__, "harness_exit_code": None,
            "evidence_paths": [str(path) for path in evidence_sources(kill) if path.exists()]}
        append_record(root, scenario, record)
        print(f"INTERRUPTED: kill {kill['kill_id']} ({type(error).__name__}); the harness process group was "
              f"stopped. The kill is recorded as not counted and its evidence is kept under /tmp; run "
              f"`scoreboard archive-pending --scenario {scenario}` to archive it.", flush=True)
        raise
    record = _postprocess(root, target, scenario, label, kill, sha, source_commit)
    record["worldserver_sha256"] = sha  # the hash of the pinned file that was launched always wins
    if record.get("report_binary_sha256"):
        print(f"warning: report.json names binary {record['report_binary_sha256']} but the launched file is {sha}; "
              "both are recorded, the file hash is used", flush=True)
    record["harness_exit_code"] = exit_code
    record["evidence_paths"] = [str(path) for path in evidence_sources(kill) if path.exists()]
    try:
        pointer, error = archive_evidence(root, scenario, kill["kill_id"], evidence_sources(kill), recorded_pointers)
    except Exception as failure:
        pointer, error = None, f"{type(failure).__name__}: {failure}"
    record["evidence_dvc_pointer"] = pointer
    if error:
        record["archive_error"] = error
    append_record(root, scenario, record)
    if pointer:
        recorded_pointers.add(pointer)
    # The exit code is informational: diagnostic route runs exit 1 even on a clean clear.
    print(kill_line(record) + f" harness_exit={exit_code} (informational) evidence={pointer}", flush=True)
    problems = []
    if record.get("postprocess_error"):
        problems.append(f"POSTPROCESS FAILED: {record['postprocess_error']}. The kill is recorded "
                        "(a clear is not counted until its numbers exist); fix the tool before measuring again.")
    if record["outcome"] == "infrastructure_failure":
        problems.append(f"INFRASTRUCTURE FAILURE: {record.get('completion_reason')}; the kill is not counted "
                        "and is not a gameplay failure. Investigate the harness, then measure under a new label.")
    elif record["outcome"] == "gameplay_failure":
        problems.append(f"NOT A NATIVE CLEAR (completion={record.get('completion_reason')}, "
                        f"native={record.get('native_reason')}): it is recorded and fails this label; "
                        "fix the cause and measure under a new label.")
    elif record["outcome"] == "clear" and not record.get("encounter"):
        problems.append("CLEARED WITHOUT ENCOUNTER DATA: combat_analysis.json has no encounter window.")
    if error:
        problems.append(f"ARCHIVE FAILED: {error}. Evidence kept: {', '.join(record['evidence_paths'])}. "
                        f"Retry with `scoreboard archive-pending --scenario {scenario}`.")
    for problem in problems:
        print(f"STOP: {problem}", flush=True)
    reason = exclusion_reason(record)
    if not problems and reason:
        validity = record.get("measurement_validity") or {}
        print(f"NOTE: kill {kill['kill_id']} is recorded but not counted ({reason}; stalled "
              f"{validity.get('stalled_sec')}s, max stall {validity.get('max_stall_sec')}s). The batch continues; "
              "this label will have fewer counted kills.", flush=True)
    return not problems


# Exclusions that say nothing about gameplay: the kill may be replaced by a top-up.
TOP_UP_REASONS = frozenset({"stalled_boss_window", "infrastructure_failure", "interrupted"})


def top_up_plan(existing: list[dict[str, Any]], target: dict[str, Any], worldserver: Path, args) -> tuple[int, str]:
    """How many kills a --top-up may add to an existing label, and the label's source commit.

    Only kills excluded for measurement reasons can be replaced; a counted non-clear (a wipe) or
    any other exclusion refuses.  The binary and source commit must match the label's kills.
    """
    reasons = [exclusion_reason(record) for record in existing]
    others = sorted({reason for reason in reasons if reason and reason not in TOP_UP_REASONS})
    if others:
        raise SystemExit(f"--top-up refused: label {args.label} has kills excluded for {', '.join(others)}")
    wipes = [record["kill_id"] for record, reason in zip(existing, reasons)
             if reason is None and not record.get("native_clear")]
    if wipes:
        raise SystemExit(f"--top-up refused: label {args.label} has counted non-clear kills {', '.join(wipes)}")
    shas = {record.get("worldserver_sha256") for record in existing}
    commits = {record.get("source_commit") for record in existing}
    if len(shas) != 1 or len(commits) != 1:
        raise SystemExit(f"--top-up refused: label {args.label} already mixes binaries or commits")
    sha, commit = next(iter(shas)), next(iter(commits))
    if not worldserver.exists() or file_sha256(worldserver) != sha:
        raise SystemExit(f"--top-up refused: {worldserver} is not the label's binary {sha}")
    if args.source_commit and args.source_commit != commit:
        raise SystemExit(f"--top-up refused: --source-commit differs from the label's {commit}")
    # --target-kills raises the goal above kills_per_measurement when a smaller effect needs
    # more power (the playbook's "--kills 5" case); both compared labels should use it.
    goal = int(getattr(args, "target_kills", None) or target.get("kills_per_batch") or target["kills_per_measurement"])
    missing = goal - len(clear_kills(existing))
    if missing < 1:
        raise SystemExit(f"--top-up refused: label {args.label} already has {goal} counted native clears")
    return min(args.kills or missing, missing), commit


def run_batch(root: Path, args) -> int:
    target = load_target(root, args.scenario)
    kills = args.kills or int(target.get("kills_per_batch") or target["kills_per_measurement"])
    if kills < 1:
        raise SystemExit("--kills must be at least 1")
    existing = label_kills(load_records(root, args.scenario), args.label)
    worldserver = args.worldserver or Path(target["run_plan"]["default_worldserver"])
    worldserver = (worldserver if worldserver.is_absolute() else root / worldserver).resolve()
    top_up_commit = None
    if existing and not getattr(args, "top_up", False):
        raise SystemExit(f"label {args.label} already has {len(existing)} kill(s); a label is one build and one "
                         "batch. Use a new label, or --top-up to replace kills excluded for measurement reasons.")
    if existing:
        kills, top_up_commit = top_up_plan(existing, target, worldserver, args)
    batch = stamp()
    if args.dry_run:
        sha = file_sha256(worldserver) if worldserver.exists() else None
        pinned = PIN_DIR / f"worldserver-{sha[:12]}" if sha else PIN_DIR / "worldserver-<sha12>"
        print(f"dry run: {kills} kill(s) for {args.scenario} label {args.label}; nothing is executed")
        print(f"pin:      copy {worldserver} -> {pinned}" + ("" if sha else "  (warning: worldserver not found)"))
        for kill in plan_kills(target, label=args.label, kills=kills, worldserver=pinned, batch=batch):
            _print_kill(root, target, args.scenario, kill)
        return 0
    if not worldserver.exists():
        raise SystemExit(f"worldserver not found: {worldserver}")
    pinned, sha = pin_worldserver(worldserver)
    print(f"pinned {worldserver} -> {pinned} ({sha}); the copy is kept for re-measuring this build", flush=True)
    source_commit = top_up_commit or args.source_commit or git_head(root)
    pointers = {r["evidence_dvc_pointer"] for r in load_records(root, args.scenario) if r.get("evidence_dvc_pointer")}
    for kill in plan_kills(target, label=args.label, kills=kills, worldserver=pinned, batch=batch):
        if not run_kill(root, target, scenario=args.scenario, label=args.label, kill=kill, sha=sha,
                        source_commit=source_commit, recorded_pointers=pointers):
            return 1
    print(f"batch done: {kills} kill(s) recorded under {args.label}. Next: "
          f"pixi run python -m tools.raid_program.scoreboard verdict --scenario {args.scenario} --label {args.label}")
    return 0


def _print_kill(root: Path, target: dict[str, Any], scenario: str, kill: dict[str, Any]) -> None:
    analysis = kill["analysis_dir"]
    name = archive_base(scenario, kill["kill_id"])
    print(f"kill {kill['kill']} ({kill['kill_id']}):")
    print(f"  cwd:      {root}")
    print(f"  argv:     {shlex.join(kill['argv'])}  (own session; process group killed on interrupt)")
    print(f"  stdout:   {kill['stdout']}")
    print(f"  stderr:   {kill['stderr']}")
    print(f"  run dir:  {kill['output_dir']}")
    if target.get("wcl_cast_timelines"):
        print(f"  timeline: pixi run python -m tools.bot_ml.compare_magmaw_timelines --bot-run {kill['output_dir']} "
              f"--wcl-manifest {target['wcl_cast_timelines']} --output {analysis / 'timeline.json'}")
    print(f"  summary:  {analysis / 'summary.json'}")
    print(f"  record:   append to {scoreboard_path(root, scenario).relative_to(root)}")
    print(f"  archive:  {shlex.join(archive_argv(name, evidence_sources(kill)))}")
    print(f"  pointer:  {EVIDENCE_DIR}/{name}.tar.gz.dvc (a fresh _retryN name if that one is taken)")


def archive_pending(root: Path, scenario: str) -> int:
    """Archive the kept /tmp evidence of every kill without a pointer; attach the pointer."""
    records = load_records(root, scenario)
    pointers = {r["evidence_dvc_pointer"] for r in records if r.get("evidence_dvc_pointer")}
    pending = [record for record in records if not record.get("evidence_dvc_pointer")]
    if not pending:
        print("every kill has evidence; nothing to archive")
        return 0
    failures = 0
    for record in pending:
        sources = [Path(path) for path in record.get("evidence_paths") or []]
        if not any(path.exists() for path in sources):
            print(f"{record['kill_id']}: no kept evidence exists ({', '.join(map(str, sources)) or 'none recorded'}); "
                  "it stays not counted (no_evidence); void it if it should be ignored")
            failures += 1
            continue
        pointer, error = archive_evidence(root, scenario, record["kill_id"], sources, pointers)
        if pointer is None:
            print(f"{record['kill_id']}: {error}; evidence kept")
            failures += 1
            continue
        pointers.add(pointer)
        append_record(root, scenario, {"schema": ATTACHMENT_SCHEMA, "kill_id": record["kill_id"],
                                       "evidence_dvc_pointer": pointer, "recorded_at": utc_now()})
        print(f"{record['kill_id']}: attached {pointer}")
    return 1 if failures else 0
