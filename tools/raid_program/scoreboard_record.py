"""Build raid_scoreboard_kill_v1 records from closed runs or run summaries.

outcome is one of:
  clear                   native boss death and a complete route manifest
  gameplay_failure        counted against the label (wipe, stall at or after the boss, deaths)
  infrastructure_failure  not counted: report.json missing, or the run never reached
                          the boss encounter and no bot died
The harness exit code is recorded but never decides the outcome: diagnostic
route runs exit 1 even on a clean native clear. measurement_validity (world
stalls in the encounter window) and damage_reconciliation (killed-hostile damage
vs max HP) are copied from report.json / combat_analysis.json when the harness
wrote them. encounter_fidelity (creature DamageModifier calibration and boss melee
vs WCL, tools/bot_ml/live_validation_fidelity.py) and encounter_rng (random
encounter events such as Magmaw's Massive Crash side,
tools/bot_ml/live_validation_encounter_rng.py) are informational: nothing in
counting or the verdict reads them. rng_backfill attaches encounter_rng to kills
recorded before the harness wrote it, as separate append-only lines.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from tools.raid_program.play_mode_guard import refuse_play
from tools.raid_program.scoreboard_core import (
    KILL_SCHEMA, RNG_ATTACHMENT_SCHEMA, append_record, file_sha256, healer_roles, label_kills, legacy_kill_id,
    load_records, load_target, roster, spec_targets, utc_now,
)

SUMMARY_SCHEMA = "magmaw_spell_queue_run_summary_v1"
CLEAR_COMPLETION = "validation_route_manifest_complete"


def clear_completion(target: dict[str, Any]) -> str:
    return (target.get("clear_rule") or {}).get("completion_reason", CLEAR_COMPLETION)


def is_native_clear(summary: dict[str, Any], completion: str = CLEAR_COMPLETION) -> bool:
    """Clear = native boss death and a complete route manifest; the harness exit code is ignored."""
    return bool(summary.get("native_clear")) and summary.get("completion_reason") == completion


def classify_outcome(*, report_present: bool, native_clear: bool, reached_encounter: bool, died: bool) -> str:
    if not report_present:
        return "infrastructure_failure"
    if native_clear:
        return "clear"
    if not reached_encounter and not died:
        return "infrastructure_failure"
    return "gameplay_failure"


def run_dir_reached_encounter(run_dir: Path, node: str) -> bool:
    """The encounter has a combat window, or a heartbeat saw the route on the encounter node."""
    analysis = run_dir / "combat_analysis.json"
    if analysis.exists():
        if any(row.get("route_node_id") == node for row in json.loads(analysis.read_text()).get("encounters") or []):
            return True
    heartbeats = run_dir / "heartbeat_events.jsonl"
    if heartbeats.exists():
        for line in heartbeats.read_text().splitlines():
            if line.strip() and (json.loads(line).get("semantic_liveness") or {}).get("route_node_id") == node:
                return True
    return False


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


def ranked_gaps(actors: list[dict[str, Any]], targets: dict[str, float], timeline: dict[str, Any] | None,
                healers: set[str], limit: int = 3) -> list[dict[str, Any]]:
    """Largest DPS shortfalls to the WCL target, with timeline hints for where to look."""
    hints = {str(row.get("bot_guid")): row for row in (timeline or {}).get("actors") or []}
    window = float(((timeline or {}).get("comparison_window") or {}).get("common_window_sec") or 0.0)
    gaps = []
    for actor in actors:
        target = targets.get(actor["spec"]) if actor["role"] not in healers else None
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


def record_from_summary(summary: dict[str, Any], *, root: Path, target: dict[str, Any], scenario: str, label: str,
                        kill_id: str, deaths: dict[str, Any], timeline: dict[str, Any] | None = None,
                        source_commit: str | None = None, evidence_pointer: str | None = None,
                        report_present: bool = True, reached_encounter: bool | None = None) -> dict[str, Any]:
    """Convert one run summary into the compact per-kill scoreboard line. Specs come from the target roster."""
    refuse_play(summary, f"scoreboard record {kill_id}")
    node = target["encounter_route_node_id"]
    expected = roster(target)
    encounter = summary.get("encounter")
    actors = []
    for actor in summary.get("actors") or []:
        actor_id = str(actor["bot_guid"])
        known = expected.get(actor_id) or {}
        actors.append({
            "actor_id": actor_id,
            "name": actor.get("bot_name"),
            "spec": known.get("spec") or actor.get("class_spec") or "unknown",
            "role": known.get("role") or actor.get("role") or "unknown",
            "encounter_window_dps": actor.get("encounter_window_dps"),
            "damage_uptime": actor.get("damage_uptime"),
            "casts_per_minute": actor.get("casts_per_minute"),
            "hps": actor.get("hps"),
        })
    if reached_encounter is None:
        reached_encounter = bool(encounter) or any(
            state and state[0] == node for state in summary.get("heartbeat_route_wipe_states") or [])
    native_clear = is_native_clear(summary, clear_completion(target))
    died = bool(summary.get("route_deaths")) or bool(deaths.get("deaths"))
    return {
        "schema": KILL_SCHEMA,
        "kill_id": kill_id,
        "scenario": scenario,
        "label": label,
        "recorded_at": utc_now(),
        "source_commit": source_commit,
        "worldserver_sha256": summary.get("worldserver_sha256"),
        **({"report_binary_sha256": summary["report_binary_sha256"]}
           if summary.get("report_binary_sha256") not in (None, summary.get("worldserver_sha256")) else {}),
        "run_dir": summary.get("run_dir"),
        "evidence_dvc_pointer": evidence_pointer,
        "native_clear": native_clear,
        "native_reason": summary.get("native_reason"),
        "completion_reason": summary.get("completion_reason"),
        "outcome": classify_outcome(report_present=report_present, native_clear=native_clear,
                                    reached_encounter=reached_encounter, died=died),
        "reached_encounter": reached_encounter,
        "route_deaths": summary.get("route_deaths"),
        **deaths,
        "encounter": {
            "duration_sec": encounter["duration_sec"],
            "encounter_window_party_dps": encounter["encounter_window_party_dps"],
            "party_hps": encounter.get("party_hps"),
        } if encounter else None,
        "actors": actors,
        "ranked_gaps": ranked_gaps(actors, spec_targets(root, target), timeline, healer_roles(target)),
        **{key: summary[key] for key in (*MEASUREMENT_KEYS, *INFO_KEYS) if summary.get(key) is not None},
    }


MEASUREMENT_KEYS = ("measurement_validity", "damage_reconciliation")
INFO_KEYS = ("encounter_fidelity", "encounter_rng")  # shown by scoreboard show; never read by counting or the verdict


def fidelity_fields(run_dir: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Blizzlike status and each boss's after-attacker melee mean vs WCL for one kill.

    Taken from report.json encounter_fidelity, or recomputed from combat_log.json and the
    calibration registry for runs recorded before the harness wrote it.
    """
    from tools.bot_ml.live_validation_fidelity import fidelity_from_run_dir, scoreboard_summary
    try:
        summary = scoreboard_summary(fidelity_from_run_dir(run_dir, report=report))
    except Exception as error:  # informational: never costs a kill its record
        summary = {"blizzlike": None, "reasons": [f"fidelity unavailable: {type(error).__name__}: {error}"],
                   "basis": "error", "bosses": {}}
    return {"encounter_fidelity": summary} if summary else {}


def rng_fields(run_dir: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Random encounter events of one kill (e.g. each Massive Crash side, time and players hit).

    Taken from report.json encounter_rng, or recomputed from combat_log.json for older runs.
    """
    from tools.bot_ml.live_validation_encounter_rng import rng_from_run_dir
    try:
        summary = rng_from_run_dir(run_dir, report=report)
    except Exception as error:  # informational: never costs a kill its record
        summary = {"basis": "error", "error": f"{type(error).__name__}: {error}"}
    return {"encounter_rng": summary} if summary else {}


def measurement_fields(report: dict[str, Any], analysis: dict[str, Any] | None, node: str) -> dict[str, Any]:
    """Compact measurement quality: stall validity of the encounter window and killed-hostile damage reconciliation.

    Runs recorded before the harness wrote measurement_validity get neither key.
    """
    fields: dict[str, Any] = {}
    validity = report.get("measurement_validity")
    if isinstance(validity, dict):
        window = next((row for row in validity.get("boss_windows") or []
                       if isinstance(row, dict) and row.get("route_node_id") == node), None) or {}
        fields["measurement_validity"] = {
            "schema": validity.get("schema"),
            "valid_for_dps": validity.get("valid_for_dps") is True,
            "reasons": list(validity.get("reasons") or []),
            "window_duration_sec": window.get("duration_sec"),
            "stalled_sec": window.get("stalled_sec", validity.get("boss_window_stalled_sec")),
            "stall_fraction": window.get("stall_fraction"),
            "max_stall_sec": window.get("max_stall_sec", validity.get("max_boss_window_stall_sec")),
            "stall_count": window.get("stall_count", validity.get("boss_window_stall_count")),
            "unstalled_duration_sec": window.get("unstalled_duration_sec"),
            "thresholds": dict(validity.get("thresholds") or {}),
        }
    reconciliation = (analysis or {}).get("killed_hostile_damage_reconciliation")
    if not isinstance(reconciliation, dict):
        reconciliation = (report.get("combat_analysis") or {}).get("killed_hostile_damage_reconciliation")
    if isinstance(reconciliation, dict):
        mismatches = [row for row in reconciliation.get("mismatches") or [] if isinstance(row, dict)]
        fields["damage_reconciliation"] = {
            "reconciled": reconciliation.get("reconciled"),
            "mismatch_count": int(reconciliation.get("mismatch_count") or 0),
            "encounter_mismatch_count": sum(row.get("route_node_id") == node for row in mismatches),
            "killed_hostile_count": reconciliation.get("killed_hostile_count"),
            "unlogged_health_loss": sum(int(row.get("unlogged_health_loss") or 0)
                                        for row in reconciliation.get("hostiles") or [] if isinstance(row, dict)),
        }
    return fields


def outcome_summary(run_dir: Path, worldserver_sha256: str | None, encounter_node: str) -> dict[str, Any]:
    """Outcome and measurement fields, read defensively; report_present False when report.json is missing or unreadable.

    worldserver_sha256 is the hash of the launched binary file when known; the
    report's own binary hash is kept separately and used only as a fallback.
    """
    refuse_play(run_dir, "scoreboard record")
    try:
        report = json.loads((run_dir / "report.json").read_text())
    except (OSError, ValueError):
        return {"run_dir": str(run_dir), "report_present": False, "native_clear": False,
                "native_reason": "missing_report_json", "completion_reason": "missing_report_json",
                "route_deaths": None, "worldserver_sha256": worldserver_sha256, "report_binary_sha256": None,
                "encounter": None, "actors": []}
    try:
        analysis = json.loads((run_dir / "combat_analysis.json").read_text())
    except (OSError, ValueError):
        analysis = None
    outcome = report.get("native_gameplay_outcome") or {}
    sha = ((report.get("evidence_envelope") or {}).get("component_hashes") or {}).get("binary_sha256")
    return {"run_dir": str(run_dir), "report_present": True, "native_clear": bool(outcome.get("native_clear")),
            "native_reason": outcome.get("native_reason"), "completion_reason": report.get("completion_reason"),
            "route_deaths": (report.get("status") or {}).get("deaths"),
            "worldserver_sha256": worldserver_sha256 or sha, "report_binary_sha256": sha,
            **measurement_fields(report, analysis, encounter_node), **fidelity_fields(run_dir, report),
            **rng_fields(run_dir, report), "encounter": None, "actors": []}


def summarize_run_dir(run_dir: Path, timeline_path: Path | None, label: str,
                      worldserver_sha256: str | None, encounter_node: str) -> dict[str, Any]:
    """Summary of a closed run; a run without the encounter keeps only its outcome."""
    summary = outcome_summary(run_dir, worldserver_sha256, encounter_node)
    analysis_path = run_dir / "combat_analysis.json"
    if not summary["report_present"] or not analysis_path.exists():
        return summary
    if not any(row.get("route_node_id") == encounter_node for row in json.loads(analysis_path.read_text()).get("encounters") or []):
        return summary
    from experiments.magmaw_spell_queue_summary import summarize
    with tempfile.TemporaryDirectory(prefix="scoreboard-stub-") as temp:
        if timeline_path is None:  # no comparison: keep the actors; specs come from the roster
            timeline_path = Path(temp) / "timeline.json"
            timeline_path.write_text('{"actors": []}')
        full = summarize(run_dir, timeline_path, label, summary["worldserver_sha256"] or "")
    kept = ("report_present", "worldserver_sha256", "report_binary_sha256", *MEASUREMENT_KEYS, *INFO_KEYS)
    return full | {key: summary[key] for key in kept if key in summary}


def write_timeline(run_dir: Path, manifest: Path, output: Path) -> Path | None:
    """Run the WCL timeline comparison; None when it cannot be computed."""
    from tools.bot_ml.compare_magmaw_timelines import compare_timelines
    try:
        result = compare_timelines(run_dir, manifest)
    except Exception as error:  # a failed comparison only loses hints, never the kill
        print(f"timeline comparison skipped for {run_dir}: {type(error).__name__}: {error}")
        return None
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return output


def record_from_run_dir(root: Path, target: dict[str, Any], *, scenario: str, label: str, kill_id: str,
                        run_dir: Path, timeline_path: Path | None, source_commit: str | None,
                        worldserver_sha256: str | None = None, evidence_pointer: str | None = None,
                        summary_output: Path | None = None) -> dict[str, Any]:
    node = target["encounter_route_node_id"]
    summary = summarize_run_dir(run_dir, timeline_path, label, worldserver_sha256, node)
    if summary_output is not None:
        summary_output.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    timeline = json.loads(timeline_path.read_text()) if timeline_path is not None else None
    return record_from_summary(
        summary, root=root, target=target, scenario=scenario, label=label, kill_id=kill_id,
        deaths=death_evidence(run_dir, node, summary.get("route_deaths")), timeline=timeline,
        source_commit=source_commit, evidence_pointer=evidence_pointer,
        report_present=summary["report_present"], reached_encounter=run_dir_reached_encounter(run_dir, node))


def fallback_record(root: Path, target: dict[str, Any], *, scenario: str, label: str, kill_id: str,
                    run_dir: Path, source_commit: str | None, worldserver_sha256: str | None) -> dict[str, Any]:
    """Outcome-only record used when full post-processing crashed."""
    node = target["encounter_route_node_id"]
    summary = outcome_summary(run_dir, worldserver_sha256, node)
    try:
        reached = run_dir_reached_encounter(run_dir, node)
    except (OSError, ValueError):
        reached = False
    deaths = {"boss_window_deaths": None, "death_basis": "unknown_postprocess_failed", "deaths": []}
    record = record_from_summary(
        summary, root=root, target=target, scenario=scenario, label=label, kill_id=kill_id, deaths=deaths,
        source_commit=source_commit, report_present=summary["report_present"], reached_encounter=reached)
    return record


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


def rng_backfill(root: Path, scenario: str, label: str, evidence_root: Path) -> int:
    """Attach encounter_rng to a label's kills from extracted run dirs; one append-only line per kill.

    Kills that already have encounter_rng are skipped, so the command can be rerun. Exit 1
    when a kill's run dir or combat log is missing under evidence_root (read only).
    """
    from tools.bot_ml.live_validation_encounter_rng import rng_from_run_dir
    kills = label_kills(load_records(root, scenario), label)
    if not kills:
        raise SystemExit(f"no kills recorded under {label} in {scenario}")
    missing = attached = 0
    for record in kills:
        if record.get("encounter_rng"):
            print(f"{record['kill_id']}: encounter_rng already recorded ({record['encounter_rng'].get('basis')}); skipped")
            continue
        run_dir = _find_run_dir(evidence_root, record.get("run_dir"))
        summary = None
        if run_dir is not None:
            report_path = run_dir / "report.json"
            try:
                report = json.loads(report_path.read_text()) if report_path.exists() else {}
                summary = rng_from_run_dir(run_dir, report=report)
            except (OSError, ValueError) as error:
                print(f"{record['kill_id']}: unreadable evidence in {run_dir}: {type(error).__name__}: {error}")
        if summary is None:
            print(f"{record['kill_id']}: no run dir with combat_log.json for {Path(str(record.get('run_dir'))).name} "
                  f"under {evidence_root}")
            missing += 1
            continue
        log = run_dir / "combat_log.json"
        append_record(root, scenario, {
            "schema": RNG_ATTACHMENT_SCHEMA, "kill_id": record["kill_id"], "encounter_rng": summary,
            "recorded_at": utc_now(), "source_run_dir": run_dir.name,
            "combat_log_sha256": file_sha256(log) if log.exists() else None})
        attached += 1
        sides = {name: [row.get("side") for row in rows] for name, rows in summary.items() if isinstance(rows, list)}
        print(f"{record['kill_id']}: attached encounter_rng {sides}")
    print(f"rng-backfill {label}: attached {attached}, missing {missing}, of {len(kills)} kill(s)")
    return 1 if missing else 0


def ingest(root: Path, args) -> int:
    target = load_target(root, args.scenario)
    count = len(args.summary) if args.summary else 1
    timelines = _per_source([str(path) for path in args.timeline or []], count, "--timeline")
    pointers = _per_source(args.evidence_pointer, count, "--evidence-pointer")
    commits = _per_source(args.source_commit, count, "--source-commit")
    for pointer in pointers:
        if pointer and not (root / pointer).exists():
            raise SystemExit(f"missing evidence pointer: {pointer}")
    known = {record["kill_id"] for record in load_records(root, args.scenario)}
    records = []
    if args.run_dir:
        run_dir = args.run_dir.resolve()
        refuse_play(run_dir, "scoreboard ingest --run-dir")
        kill_id = legacy_kill_id({"label": args.label, "run_dir": str(run_dir)})
        options = dict(scenario=args.scenario, label=args.label, kill_id=kill_id, run_dir=run_dir,
                       source_commit=commits[0], worldserver_sha256=args.worldserver_sha256, evidence_pointer=pointers[0])
        if timelines[0]:
            records.append(record_from_run_dir(root, target, timeline_path=Path(timelines[0]), **options))
        else:
            with tempfile.TemporaryDirectory(prefix="scoreboard-timeline-") as temp:
                timeline = write_timeline(run_dir, root / target["wcl_cast_timelines"], Path(temp) / "timeline.json")
                records.append(record_from_run_dir(root, target, timeline_path=timeline, **options))
    else:
        for path, timeline, pointer, commit in zip(args.summary, timelines, pointers, commits):
            summary = json.loads(path.read_text())
            if summary.get("schema") != SUMMARY_SCHEMA:
                raise SystemExit(f"{path} is not a {SUMMARY_SCHEMA} summary")
            refuse_play(summary, f"scoreboard ingest --summary {path}")
            raw = _find_run_dir(args.evidence_root, summary.get("run_dir"))
            if raw is not None:
                refuse_play(raw, "scoreboard ingest --evidence-root")
            deaths = death_evidence(raw, target["encounter_route_node_id"], summary.get("route_deaths"))
            records.append(record_from_summary(
                summary, root=root, target=target, scenario=args.scenario, label=args.label,
                kill_id=legacy_kill_id({"label": args.label, "run_dir": summary.get("run_dir")}), deaths=deaths,
                timeline=json.loads(Path(timeline).read_text()) if timeline else None,
                source_commit=commit, evidence_pointer=pointer))
    for record in records:
        if record["kill_id"] in known:
            raise SystemExit(f"kill {record['kill_id']} is already recorded; nothing written")
        known.add(record["kill_id"])
    for record in records:
        path = append_record(root, args.scenario, record)
        print(kill_line(record))
    print(f"recorded {len(records)} kill(s) under {args.label} in {path.relative_to(root)}")
    return 0


def kill_line(record: dict[str, Any]) -> str:
    encounter = record.get("encounter") or {}
    party = encounter.get("encounter_window_party_dps")
    return (f"{record['kill_id']}: outcome={record.get('outcome')} clear={record['native_clear']} "
            f"route_deaths={record.get('route_deaths')} boss_window_deaths={record.get('boss_window_deaths')} "
            f"kill={encounter.get('duration_sec', '-')}s party_dps={round(party) if party else '-'}")
