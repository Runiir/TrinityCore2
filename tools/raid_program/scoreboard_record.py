"""Build raid_scoreboard_kill_v1 records from closed runs or run summaries."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from tools.raid_program.scoreboard import (
    KILL_SCHEMA, append_record, load_target, spec_targets,
)

SUMMARY_SCHEMA = "magmaw_spell_queue_run_summary_v1"
CLEAR_COMPLETION = "validation_route_manifest_complete"


def clear_completion(target: dict[str, Any]) -> str:
    return (target.get("clear_rule") or {}).get("completion_reason", CLEAR_COMPLETION)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def git_head(root: Path) -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    return result.stdout.strip() or None


def death_evidence(run_dir: Path | None, encounter_node: str, route_deaths: int | None) -> dict[str, Any]:
    """Party deaths from lethal landed damage in the native combat log.

    A death is a damage event on a party member whose amount reaches the
    target's health before the hit. It is in the boss window when it happens on
    the encounter route node or between the first and last encounter damage.
    The count is trusted only when it reconciles with the route death count.
    """
    if route_deaths == 0:
        return {"boss_window_deaths": 0, "death_basis": "no_route_deaths", "deaths": []}
    if run_dir is None or not (run_dir / "combat_log.json").exists() or not (run_dir / "combat_analysis.json").exists():
        return {"boss_window_deaths": None, "death_basis": "unknown_raw_combat_log_unavailable", "deaths": []}
    analysis = json.loads((run_dir / "combat_analysis.json").read_text())
    log = json.loads((run_dir / "combat_log.json").read_text())
    encounters = analysis.get("encounters") or []
    window = next((row for row in encounters if row.get("route_node_id") == encounter_node), None)
    first, last = (int(window["first_at_ms"]), int(window["last_at_ms"])) if window else (None, None)
    events = log.get("recent_events") or []
    party = {int(actor["actor_guid"]) for row in encounters for actor in row.get("actors") or []}
    party |= {int(event["actor_guid"]) for event in events if event.get("actor_guid")}
    deaths = []
    for event in events:
        if event.get("kind") != "damage" or int(event.get("target_guid") or 0) not in party:
            continue
        before = (event.get("landed_damage_observation") or {}).get("target_health_before_damage")
        if before is None or int(event.get("amount") or 0) < int(before):
            continue
        at = int(event.get("timestamp_ms") or 0)
        in_window = event.get("route_node_id") == encounter_node or (first is not None and first <= at <= last)
        deaths.append({
            "timestamp_ms": at, "route_node_id": event.get("route_node_id"),
            "actor_id": str(event.get("target_guid")), "name": event.get("target_name"),
            "killed_by": event.get("source_name"), "spell": event.get("spell_name"),
            "in_boss_window": in_window,
        })
    reconciled = route_deaths is not None and len(deaths) == route_deaths and not log.get("recent_events_dropped")
    return {
        "boss_window_deaths": sum(death["in_boss_window"] for death in deaths) if reconciled else None,
        "death_basis": "combat_log_lethal_damage" if reconciled else "combat_log_lethal_damage_unreconciled",
        "deaths": deaths,
    }


def ranked_gaps(actors: list[dict[str, Any]], targets: dict[str, float],
                timeline: dict[str, Any] | None, limit: int = 3) -> list[dict[str, Any]]:
    """Largest DPS shortfalls to the WCL target, with timeline hints for where to look."""
    hints = {str(row.get("bot_guid")): row for row in (timeline or {}).get("actors") or []}
    window = float(((timeline or {}).get("comparison_window") or {}).get("common_window_sec") or 0.0)
    gaps = []
    for actor in actors:
        target = targets.get(actor["spec"]) if actor["role"] != "healer" else None
        dps = float(actor["encounter_window_dps"] or 0.0)
        if not target or dps >= target:
            continue
        gap = {"actor_id": actor["actor_id"], "name": actor["name"], "spec": actor["spec"],
               "dps": round(dps, 1), "target_dps": target, "gap_dps": round(target - dps, 1),
               "casts_per_minute": actor.get("casts_per_minute")}
        hint = hints.get(actor["actor_id"])
        if hint:
            largest = ((hint.get("bot") or {}).get("largest_gaps") or [None])[0]
            gap["largest_owner_gap"] = {key: largest[key] for key in ("gap_sec", "from_t", "from_ability", "to_ability")} if largest else None
            gap["wcl_only_abilities"] = [row["ability"] for row in hint.get("wcl_only_abilities") or []][:3]
            casts = (hint.get("wcl") or {}).get("completed_casts")
            gap["wcl_casts_per_minute"] = round(casts / (window / 60.0), 2) if casts and window else None
        gaps.append(gap)
    gaps.sort(key=lambda row: -row["gap_dps"])
    return gaps[:limit]


def is_native_clear(summary: dict[str, Any], clear_completion: str = CLEAR_COMPLETION) -> bool:
    """Clear = native boss death and a complete route manifest; the harness exit code is ignored."""
    return bool(summary.get("native_clear")) and summary.get("completion_reason") == clear_completion


def record_from_summary(summary: dict[str, Any], *, scenario: str, label: str, targets: dict[str, float],
                        deaths: dict[str, Any], timeline: dict[str, Any] | None = None,
                        source_commit: str | None = None, evidence_pointer: str | None = None,
                        clear_completion: str = CLEAR_COMPLETION) -> dict[str, Any]:
    """Convert one run summary into the compact per-kill scoreboard line."""
    encounter = summary.get("encounter")
    actors = [{
        "actor_id": str(actor["bot_guid"]),
        "name": actor.get("bot_name"),
        "spec": actor.get("class_spec") or "unknown",
        "role": actor.get("role") or "unknown",
        "encounter_window_dps": actor.get("encounter_window_dps"),
        "damage_uptime": actor.get("damage_uptime"),
        "casts_per_minute": actor.get("casts_per_minute"),
        "hps": actor.get("hps"),
    } for actor in summary.get("actors") or []]
    return {
        "schema": KILL_SCHEMA,
        "scenario": scenario,
        "label": label,
        "recorded_at": utc_now(),
        "source_commit": source_commit,
        "worldserver_sha256": summary.get("worldserver_sha256"),
        "run_dir": summary.get("run_dir"),
        "evidence_dvc_pointer": evidence_pointer,
        "native_clear": is_native_clear(summary, clear_completion),
        "native_reason": summary.get("native_reason"),
        "completion_reason": summary.get("completion_reason"),
        "route_deaths": summary.get("route_deaths"),
        **deaths,
        "encounter": {
            "duration_sec": encounter["duration_sec"],
            "encounter_window_party_dps": encounter["encounter_window_party_dps"],
            "party_hps": encounter.get("party_hps"),
        } if encounter else None,
        "actors": actors,
        "ranked_gaps": ranked_gaps(actors, targets, timeline),
    }


def summarize_run_dir(run_dir: Path, timeline_path: Path | None, label: str,
                      worldserver_sha256: str | None, encounter_node: str) -> dict[str, Any]:
    """Summary of a closed run; a run without the encounter keeps only its outcome."""
    report = json.loads((run_dir / "report.json").read_text())
    sha = ((report.get("evidence_envelope") or {}).get("component_hashes") or {}).get("binary_sha256")
    analysis_path = run_dir / "combat_analysis.json"
    encounters = json.loads(analysis_path.read_text()).get("encounters", []) if analysis_path.exists() else []
    if any(row.get("route_node_id") == encounter_node for row in encounters):
        from experiments.magmaw_spell_queue_summary import summarize
        with tempfile.TemporaryDirectory(prefix="scoreboard-stub-") as temp:
            if timeline_path is None:  # no comparison: keep the actors, specs become unknown
                timeline_path = Path(temp) / "timeline.json"
                timeline_path.write_text('{"actors": []}')
            summary = summarize(run_dir, timeline_path, label, sha or worldserver_sha256 or "")
    else:
        outcome = report.get("native_gameplay_outcome") or {}
        summary = {"schema": SUMMARY_SCHEMA, "label": label, "run_dir": str(run_dir),
                   "native_clear": bool(outcome.get("native_clear")), "native_reason": outcome.get("native_reason"),
                   "completion_reason": report.get("completion_reason"),
                   "route_deaths": (report.get("status") or {}).get("deaths"), "encounter": None, "actors": []}
    summary["worldserver_sha256"] = sha or worldserver_sha256
    return summary


def write_timeline(run_dir: Path, manifest: Path, output: Path) -> Path | None:
    """Run the WCL timeline comparison; None when the run has no encounter to compare."""
    from tools.bot_ml.compare_magmaw_timelines import compare_timelines
    try:
        result = compare_timelines(run_dir, manifest)
    except (FileNotFoundError, KeyError, ValueError) as error:
        print(f"timeline comparison skipped for {run_dir}: {error}")
        return None
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return output


def record_from_run_dir(root: Path, target: dict[str, Any], *, scenario: str, label: str, run_dir: Path,
                        timeline_path: Path | None, source_commit: str | None,
                        worldserver_sha256: str | None = None, evidence_pointer: str | None = None,
                        summary_output: Path | None = None) -> dict[str, Any]:
    node = target["encounter_route_node_id"]
    if not (run_dir / "report.json").exists():
        summary = {"run_dir": str(run_dir), "native_clear": False, "native_reason": "missing_report_json",
                   "completion_reason": "missing_report_json", "route_deaths": None,
                   "worldserver_sha256": worldserver_sha256, "encounter": None, "actors": []}
    else:
        summary = summarize_run_dir(run_dir, timeline_path, label, worldserver_sha256, node)
    if summary_output is not None:
        summary_output.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    timeline = json.loads(timeline_path.read_text()) if timeline_path is not None else None
    return record_from_summary(
        summary, scenario=scenario, label=label, targets=spec_targets(root, target),
        deaths=death_evidence(run_dir, node, summary.get("route_deaths")), timeline=timeline,
        source_commit=source_commit, evidence_pointer=evidence_pointer,
        clear_completion=clear_completion(target))


def _per_source(values: list[str] | None, count: int, name: str) -> list[Any]:
    if not values:
        return [None] * count
    if len(values) == 1 and name == "--source-commit":
        return values * count
    if len(values) != count:
        raise SystemExit(f"{name} needs one value per summary/run ({count}), got {len(values)}")
    return list(values)


def _find_run_dir(evidence_root: Path | None, run_dir: str | None) -> Path | None:
    if evidence_root is None or not run_dir:
        return None
    name = Path(run_dir).name
    return next((path for path in sorted(evidence_root.glob(f"**/{name}")) if path.is_dir()), None)


def ingest(root: Path, args) -> int:
    target = load_target(root, args.scenario)
    targets = spec_targets(root, target)
    count = len(args.summary) if args.summary else 1
    timelines = _per_source([str(path) for path in args.timeline or []], count, "--timeline")
    pointers = _per_source(args.evidence_pointer, count, "--evidence-pointer")
    commits = _per_source(args.source_commit, count, "--source-commit")
    for pointer in pointers:
        if pointer and not (root / pointer).exists():
            raise SystemExit(f"missing evidence pointer: {pointer}")
    records = []
    if args.run_dir:
        run_dir = args.run_dir.resolve()
        if timelines[0]:
            records.append(record_from_run_dir(
                root, target, scenario=args.scenario, label=args.label, run_dir=run_dir,
                timeline_path=Path(timelines[0]), source_commit=commits[0],
                worldserver_sha256=args.worldserver_sha256, evidence_pointer=pointers[0]))
        else:
            with tempfile.TemporaryDirectory(prefix="scoreboard-timeline-") as temp:
                timeline = write_timeline(run_dir, root / target["wcl_cast_timelines"], Path(temp) / "timeline.json")
                records.append(record_from_run_dir(
                    root, target, scenario=args.scenario, label=args.label, run_dir=run_dir,
                    timeline_path=timeline, source_commit=commits[0],
                    worldserver_sha256=args.worldserver_sha256, evidence_pointer=pointers[0]))
    else:
        for path, timeline, pointer, commit in zip(args.summary, timelines, pointers, commits):
            summary = json.loads(path.read_text())
            if summary.get("schema") != SUMMARY_SCHEMA:
                raise SystemExit(f"{path} is not a {SUMMARY_SCHEMA} summary")
            raw = _find_run_dir(args.evidence_root, summary.get("run_dir"))
            deaths = death_evidence(raw, target["encounter_route_node_id"], summary.get("route_deaths"))
            records.append(record_from_summary(
                summary, scenario=args.scenario, label=args.label, targets=targets, deaths=deaths,
                timeline=json.loads(Path(timeline).read_text()) if timeline else None,
                source_commit=commit, evidence_pointer=pointer, clear_completion=clear_completion(target)))
    for record in records:
        path = append_record(root, args.scenario, record)
        print(kill_line(record))
    print(f"recorded {len(records)} kill(s) under {args.label} in {path.relative_to(root)}")
    return 0


def kill_line(record: dict[str, Any]) -> str:
    encounter = record.get("encounter") or {}
    party = encounter.get("encounter_window_party_dps")
    return (f"{record['label']} {Path(str(record.get('run_dir'))).name}: clear={record['native_clear']} "
            f"route_deaths={record.get('route_deaths')} boss_window_deaths={record.get('boss_window_deaths')} "
            f"kill={encounter.get('duration_sec', '-')}s party_dps={round(party) if party else '-'}")
