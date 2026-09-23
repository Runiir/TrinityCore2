"""Raid scoreboard: numeric WCL target, per-kill records and a batch verdict.

Each scenario has a target file (experiments/configs/raid_targets/<scenario>.json)
and a scoreboard (artifacts/cata_raid_program/scoreboard/<scenario>.jsonl) with
one JSON line per kill. A label names one code/binary state; a verdict is taken
over all kills recorded under one label, never from a single run.

    pixi run python -m tools.raid_program.scoreboard run --scenario S --label L --dry-run
    pixi run python -m tools.raid_program.scoreboard ingest --scenario S --label L --summary FILE
    pixi run python -m tools.raid_program.scoreboard show --scenario S --label L --vs L2
    pixi run python -m tools.raid_program.scoreboard verdict --scenario S --label L

Only the coordinator runs `run` without --dry-run: it launches live kills.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TARGET_SCHEMA = "raid_target_v1"
KILL_SCHEMA = "raid_scoreboard_kill_v1"
VERDICT_SCHEMA = "raid_target_verdict_v1"
TARGET_DIR = "experiments/configs/raid_targets"
SCOREBOARD_DIR = "artifacts/cata_raid_program/scoreboard"
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def target_path(root: Path, scenario: str) -> Path:
    return root / TARGET_DIR / f"{scenario}.json"


def scoreboard_path(root: Path, scenario: str) -> Path:
    return root / SCOREBOARD_DIR / f"{scenario}.jsonl"


def load_target(root: Path, scenario: str) -> dict[str, Any]:
    path = target_path(root, scenario)
    if not path.exists():
        raise SystemExit(f"no raid target for scenario {scenario!r}: create {path.relative_to(root)}")
    target = json.loads(path.read_text())
    if target.get("schema") != TARGET_SCHEMA or target.get("scenario") != scenario:
        raise ValueError(f"{path} is not a {TARGET_SCHEMA} target for {scenario}")
    return target


def _matched_references(root: Path, target: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = json.loads((root / target["wcl_reference_manifest"]).read_text())
    wanted = list(target["matched_reference_ids"])
    matched = [ref for ref in manifest["references"] if ref["id"] in wanted]
    missing = sorted(set(wanted) - {ref["id"] for ref in matched})
    if missing:
        raise ValueError(f"matched reference ids not in {target['wcl_reference_manifest']}: {missing}")
    return matched


def spec_targets(root: Path, target: dict[str, Any]) -> dict[str, float]:
    """Median matched WCL DPS per spec. Specs without a matched reference are absent."""
    values: defaultdict[str, list[float]] = defaultdict(list)
    for ref in _matched_references(root, target):
        for spec, dps in ref["actor_dps"].items():
            values[spec].append(float(dps))
    return {spec: statistics.median(dps) for spec, dps in values.items()}


def party_reference_dps(root: Path, target: dict[str, Any]) -> float | None:
    values = [float(ref["raid_dps"]) for ref in _matched_references(root, target) if ref.get("raid_dps")]
    return statistics.median(values) if values else None


def load_records(root: Path, scenario: str) -> list[dict[str, Any]]:
    path = scoreboard_path(root, scenario)
    if not path.exists():
        return []
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for record in records:
        if record.get("schema") != KILL_SCHEMA:
            raise ValueError(f"{path}: unexpected record schema {record.get('schema')!r}")
    return records


def append_record(root: Path, scenario: str, record: dict[str, Any]) -> Path:
    path = scoreboard_path(root, scenario)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def latest_label(records: list[dict[str, Any]]) -> str | None:
    return records[-1]["label"] if records else None


def label_kills(records: list[dict[str, Any]], label: str | None) -> list[dict[str, Any]]:
    return [record for record in records if record["label"] == label]


def clear_kills(kills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Kills whose numbers count: native clears with encounter-window data."""
    return [record for record in kills if record.get("native_clear") and record.get("encounter")]


def mean_sd(values: list[float]) -> tuple[float | None, float | None]:
    """Sample mean and sample standard deviation (None when undefined)."""
    if not values:
        return None, None
    mean = statistics.fmean(values)
    return mean, (statistics.stdev(values) if len(values) > 1 else None)


def actor_rows(clears: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Actor rows of every native-clear kill, keyed by actor id in guid order."""
    rows: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in clears:
        for actor in record.get("actors") or []:
            rows[str(actor["actor_id"])].append(actor)
    return dict(sorted(rows.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0]))


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def _encounter_verdict(kills, clears, target, party_wcl) -> dict[str, Any]:
    required = int(target["kills_per_measurement"])
    max_deaths = int(target["max_boss_window_deaths"])
    reasons = []
    for record in kills:
        name = Path(str(record.get("run_dir") or "unknown")).name
        if not record.get("native_clear"):
            reasons.append(f"kill {name} was not a native clear "
                           f"({record.get('completion_reason') or record.get('native_reason') or 'no reason'})")
            continue
        if not record.get("encounter"):
            reasons.append(f"kill {name} cleared but has no encounter-window data")
            continue
        deaths = record.get("boss_window_deaths")
        if deaths is None:
            reasons.append(f"kill {name} has unknown boss-window deaths ({record.get('death_basis')})")
        elif deaths > max_deaths:
            reasons.append(f"kill {name} had {deaths} boss-window deaths (max {max_deaths})")
    party_dps, _ = mean_sd([float(r["encounter"]["encounter_window_party_dps"]) for r in clears])
    duration, _ = mean_sd([float(r["encounter"]["duration_sec"]) for r in clears])
    window_deaths = [record.get("boss_window_deaths") for record in kills]
    if reasons:
        status = "fail"
    elif len(clears) < required:
        status = "insufficient_kills"
        reasons.append(f"{len(clears)} of {required} required native-clear kills recorded")
    else:
        status = "pass"
    return {
        "n": len(kills),
        "clears": len(clears),
        "mean_party_dps": _round(party_dps),
        "mean_duration_sec": _round(duration, 3),
        "boss_window_deaths": None if None in window_deaths else sum(window_deaths),
        "route_deaths": sum(int(record.get("route_deaths") or 0) for record in kills),
        "party_wcl_dps": party_wcl,
        "party_ratio": _round(party_dps / party_wcl, 3) if party_dps and party_wcl else None,
        "party_dps_gating": bool(target.get("party_dps_gating")),
        "status": status,
        "reasons": reasons,
    }


def evaluate_target(root: Path, scenario: str, label: str | None = None) -> dict[str, Any]:
    """Judge one label's kills against the scenario target (label None = latest label)."""
    root = Path(root)
    target = load_target(root, scenario)
    records = load_records(root, scenario)
    label = latest_label(records) if label is None else label
    kills = label_kills(records, label)
    clears = clear_kills(kills)
    required = int(target["kills_per_measurement"])
    minimum = float(target["actor_dps_ratio"])
    targets = spec_targets(root, target)
    healer_roles = set(target.get("roles_without_dps_target", ["healer"]))
    encounter = _encounter_verdict(kills, clears, target, party_reference_dps(root, target))

    actors: dict[str, dict[str, Any]] = {}
    reasons = [] if encounter["status"] == "pass" else list(encounter["reasons"])
    for actor_id, rows in actor_rows(clears).items():
        spec, role = rows[-1].get("spec") or "unknown", rows[-1].get("role") or "unknown"
        mean, sd = mean_sd([float(row["encounter_window_dps"]) for row in rows])
        target_dps = None if role in healer_roles else targets.get(spec)
        ratio = mean / target_dps if target_dps and mean is not None else None
        if role in healer_roles:
            status = encounter["status"]
        elif target_dps is None:
            status = "no_reference"
            reasons.append(f"actor {actor_id} ({spec}) has no matched WCL reference; add one before this target can pass")
        elif len(rows) < required:
            status = "insufficient_kills"
        else:
            status = "pass" if ratio >= minimum else "fail"
            if status == "fail":
                reasons.append(f"actor {actor_id} ({spec}) ratio {ratio:.3f} < {minimum}")
        actors[actor_id] = {
            "spec": spec, "role": role, "name": rows[-1].get("name"), "n": len(rows),
            "mean_dps": _round(mean), "sd_dps": _round(sd),
            "target_dps": target_dps,
            "required_dps": _round(target_dps * minimum) if target_dps else None,
            "ratio": _round(ratio, 3), "status": status,
        }

    if not kills:
        reasons = [f"no kills recorded for label {label!r}" if label else "no kills recorded"]
    non_healers = [actor for actor in actors.values() if actor["role"] not in healer_roles]
    if encounter["status"] == "fail" or any(actor["status"] in ("fail", "no_reference") for actor in non_healers):
        status = "fail"
    elif encounter["status"] == "insufficient_kills" or not kills:
        status = "insufficient_kills"
    else:
        status = "pass"
    return {
        "schema": VERDICT_SCHEMA,
        "scenario": scenario,
        "label": label,
        "kills": len(kills),
        "kills_per_measurement": required,
        "actor_dps_ratio": minimum,
        "target_path": str(target_path(root, scenario).relative_to(root)),
        "actors": actors,
        "encounter": encounter,
        "status": status,
        "reason": "; ".join(reasons) if status != "pass" else None,
        "reasons": reasons if status != "pass" else [],
    }


def _label(value: str) -> str:
    if not LABEL_RE.match(value):
        raise argparse.ArgumentTypeError("labels use letters, digits, '.', '_' and '-' only")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run N live kills, record and archive each")
    run.add_argument("--scenario", required=True)
    run.add_argument("--label", required=True, type=_label)
    run.add_argument("--kills", type=int, help="default: the target's kills_per_measurement")
    run.add_argument("--worldserver", type=Path, help="default: the target's run_plan.default_worldserver")
    run.add_argument("--source-commit", help="default: git HEAD")
    run.add_argument("--dry-run", action="store_true", help="print the plan and run nothing")

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

    show = commands.add_parser("show", help="per-actor table, optional comparison with another label")
    show.add_argument("--scenario", required=True)
    show.add_argument("--label", help="default: the most recently recorded label")
    show.add_argument("--vs", help="baseline label to compare against")
    show.add_argument("--actor", help="actor id the change targeted (for the keep/revert rule)")

    verdict = commands.add_parser("verdict", help="print the evaluate_target JSON")
    verdict.add_argument("--scenario", required=True)
    verdict.add_argument("--label")

    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.command == "verdict":
        print(json.dumps(evaluate_target(root, args.scenario, args.label), indent=1, sort_keys=True))
        return 0
    if args.command == "show":
        from tools.raid_program.scoreboard_show import render
        print(render(root, args.scenario, args.label, args.vs, args.actor))
        return 0
    if args.command == "ingest":
        from tools.raid_program.scoreboard_record import ingest as run_ingest
        return run_ingest(root, args)
    from tools.raid_program.scoreboard_run import run_batch
    return run_batch(root, args)


if __name__ == "__main__":
    raise SystemExit(main())
