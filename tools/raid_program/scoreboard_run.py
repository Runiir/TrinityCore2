"""Run a batch of live kills for one label: validate, summarize, record, archive.

Each kill runs the target's bot-live-validate argv template into
/tmp/scoreboard-<label>-k<i>-<timestamp>. Afterwards the WCL timeline
comparison and the summary go to <run dir>-analysis, one line is appended to
the scoreboard, and the run is archived through experiments.archive_run_evidence
(DVC push, remote verify, local eviction). A kill without a native clear is
recorded and stops the batch.
"""
from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from tools.raid_program.scoreboard import (
    append_record, label_kills, load_records, load_target, scoreboard_path,
)
from tools.raid_program.scoreboard_record import (
    file_sha256, git_head, kill_line, record_from_run_dir, write_timeline,
)

EVIDENCE_DIR = "artifacts/cata_raid_program"


def plan_kills(root: Path, target: dict[str, Any], *, scenario: str, label: str, kills: int,
               worldserver: Path, first_index: int, stamp: str) -> list[dict[str, Any]]:
    """Exact argv and paths for each kill; nothing is created."""
    plan = []
    for index in range(first_index, first_index + kills):
        base = target["run_plan"].get("output_dir_pattern", "/tmp/scoreboard-{label}-k{kill}-{timestamp}")
        output_dir = Path(base.format(label=label, kill=index, timestamp=stamp))
        values = {"{worldserver}": str(worldserver), "{output_dir}": str(output_dir)}
        argv = [values.get(arg, arg) for arg in target["run_plan"]["argv_template"]]
        name = f"scoreboard_{scenario}_{label}_k{index}_{stamp}"
        plan.append({
            "kill": index,
            "argv": argv,
            "output_dir": output_dir,
            "analysis_dir": Path(f"{output_dir}-analysis"),
            "stdout": Path(f"{output_dir}.stdout"),
            "stderr": Path(f"{output_dir}.stderr"),
            "archive_name": name,
            "evidence_dvc_pointer": f"{EVIDENCE_DIR}/{name}.tar.gz.dvc",
        })
    return plan


def archive_argv(kill: dict[str, Any], sources: list[Path]) -> list[str]:
    return ["pixi", "run", "python", "-m", "experiments.archive_run_evidence",
            "--name", kill["archive_name"], *map(str, sources)]


def _print_plan(root: Path, target: dict[str, Any], plan: list[dict[str, Any]], scenario: str) -> None:
    manifest = target["wcl_cast_timelines"]
    for kill in plan:
        analysis = kill["analysis_dir"]
        print(f"kill {kill['kill']}:")
        print(f"  cwd:      {root}")
        print(f"  argv:     {shlex.join(kill['argv'])}")
        print(f"  stdout:   {kill['stdout']}")
        print(f"  stderr:   {kill['stderr']}")
        print(f"  run dir:  {kill['output_dir']}")
        print(f"  timeline: pixi run python -m tools.bot_ml.compare_magmaw_timelines --bot-run {kill['output_dir']} "
              f"--wcl-manifest {manifest} --output {analysis / 'timeline.json'}")
        print(f"  summary:  {analysis / 'summary.json'}")
        print(f"  record:   append to {scoreboard_path(root, scenario).relative_to(root)}")
        sources = [kill["output_dir"], analysis, kill["stdout"], kill["stderr"]]
        print(f"  archive:  {shlex.join(archive_argv(kill, sources))}")
        print(f"  pointer:  {kill['evidence_dvc_pointer']}")


def _archive(root: Path, kill: dict[str, Any]) -> str | None:
    sources = [path for path in (kill["output_dir"], kill["analysis_dir"], kill["stdout"], kill["stderr"])
               if path.exists()]
    if not sources:
        return None
    result = subprocess.run(archive_argv(kill, sources), cwd=root)
    pointer = kill["evidence_dvc_pointer"]
    return pointer if result.returncode == 0 and (root / pointer).exists() else None


def run_batch(root: Path, args) -> int:
    target = load_target(root, args.scenario)
    kills = args.kills or int(target["kills_per_measurement"])
    if kills < 1:
        raise SystemExit("--kills must be at least 1")
    worldserver = args.worldserver or Path(target["run_plan"]["default_worldserver"])
    worldserver = (worldserver if worldserver.is_absolute() else root / worldserver).resolve()
    first_index = len(label_kills(load_records(root, args.scenario), args.label)) + 1
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    plan = plan_kills(root, target, scenario=args.scenario, label=args.label, kills=kills,
                      worldserver=worldserver, first_index=first_index, stamp=stamp)
    if args.dry_run:
        print(f"dry run: {kills} kill(s) for {args.scenario} label {args.label}; nothing is executed")
        if not worldserver.exists():
            print(f"warning: worldserver not found: {worldserver}")
        _print_plan(root, target, plan, args.scenario)
        return 0
    if not worldserver.exists():
        raise SystemExit(f"worldserver not found: {worldserver}")

    source_commit = args.source_commit or git_head(root)
    manifest = root / target["wcl_cast_timelines"]
    for position, kill in enumerate(plan, start=1):
        for path in (kill["output_dir"], kill["analysis_dir"], kill["stdout"], kill["stderr"]):
            if path.exists():
                raise SystemExit(f"refusing to reuse an existing path: {path}")
        sha = file_sha256(worldserver)
        print(f"kill {position}/{kills} (k{kill['kill']}): {shlex.join(kill['argv'])}", flush=True)
        with kill["stdout"].open("w") as out, kill["stderr"].open("w") as err:
            returncode = subprocess.run(kill["argv"], cwd=root, stdout=out, stderr=err).returncode
        kill["analysis_dir"].mkdir(parents=True)
        timeline = write_timeline(kill["output_dir"], manifest, kill["analysis_dir"] / "timeline.json")
        record = record_from_run_dir(
            root, target, scenario=args.scenario, label=args.label, run_dir=kill["output_dir"],
            timeline_path=timeline, source_commit=source_commit, worldserver_sha256=sha,
            summary_output=kill["analysis_dir"] / "summary.json")
        if record["worldserver_sha256"] != sha:
            print(f"warning: report binary {record['worldserver_sha256']} differs from {worldserver} ({sha})")
        record["evidence_dvc_pointer"] = _archive(root, kill)
        append_record(root, args.scenario, record)
        # The exit code is informational: diagnostic route runs exit 1 even on a
        # clean native clear. The clear decision comes from report.json.
        print(kill_line(record) + f" harness_exit={returncode} (informational) "
              f"evidence={record['evidence_dvc_pointer']}", flush=True)
        if not record["native_clear"] or not record.get("encounter"):
            problem = ("was not a native clear" if not record["native_clear"]
                       else "cleared but combat_analysis.json has no encounter window")
            print(f"STOP: kill k{kill['kill']} {problem} "
                  f"(completion={record.get('completion_reason')}, native={record.get('native_reason')}). "
                  "It is recorded and fails this label; fix the cause and measure under a new label.")
            return 1
        if record["evidence_dvc_pointer"] is None:
            print(f"STOP: archiving k{kill['kill']} failed; the evidence is still under /tmp. "
                  "Archive it with experiments.archive_run_evidence before continuing.")
            return 1
    print(f"batch done: {kills} kill(s) recorded under {args.label}. Next: "
          f"pixi run python -m tools.raid_program.scoreboard verdict --scenario {args.scenario} --label {args.label}")
    return 0
