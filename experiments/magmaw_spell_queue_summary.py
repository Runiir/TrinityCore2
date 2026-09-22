"""Compact Magmaw 10N run summary for the spell queue comparison.

Reads one closed live-validation run directory plus its WCL timeline
comparison and writes the exact encounter-window numbers used to compare the
spell queue binary with the unchanged baseline:

    pixi run python -m experiments.magmaw_spell_queue_summary \
        --run-dir /tmp/run --timeline /tmp/run_timeline.json \
        --label sq1 --binary-sha256 <sha> --output summary.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path
from typing import Any, Iterator

ENCOUNTER = "bwd.magmaw.encounter"


def _spell_queue(node: Any) -> dict[str, Any] | None:
    if isinstance(node, dict):
        kernel = node.get("decision_kernel")
        if isinstance(kernel, dict) and isinstance(kernel.get("spell_queue"), dict):
            return kernel["spell_queue"]
        values = node.values()
    elif isinstance(node, list):
        values = node
    else:
        return None
    for value in values:
        found = _spell_queue(value)
        if found is not None:
            return found
    return None


def _spell_queues(report: dict[str, Any]) -> Iterator[dict[str, Any]]:
    diagnosis = report.get("diagnosis")
    bots = diagnosis.get("bots") if isinstance(diagnosis, dict) else None
    for bot in bots or []:
        queue = _spell_queue(bot.get("diagnosis"))
        if queue is not None:
            yield {**(bot.get("identity") or {}), **queue}


def summarize(run_dir: Path, timeline_path: Path, label: str, binary_sha256: str) -> dict[str, Any]:
    report = json.loads((run_dir / "report.json").read_text())
    analysis = json.loads((run_dir / "combat_analysis.json").read_text())
    timeline = json.loads(timeline_path.read_text())
    encounter = next(row for row in analysis["encounters"] if row.get("route_node_id") == ENCOUNTER)
    outcome = report.get("native_gameplay_outcome") or {}

    wcl_by_guid = {int(actor["bot_guid"]): actor for actor in timeline["actors"]}
    actors = []
    for actor in sorted(encounter["actors"], key=lambda row: int(row["actor_guid"])):
        guid = int(actor["actor_guid"])
        reference = wcl_by_guid.get(guid, {})
        wcl_dps = float(reference.get("wcl_observed_dps") or 0.0)
        dps = float(actor["encounter_window_dps"])
        actors.append({
            "bot_guid": guid,
            "bot_name": actor["actor_name"],
            "class_spec": reference.get("class_spec"),
            "role": actor["actor_role"],
            "encounter_window_dps": round(dps, 3),
            "damage": round(float(actor["damage"])),
            "pet_damage_share": round(float(actor.get("pet_damage_share") or 0.0), 3),
            "damage_uptime": round(float(actor.get("damage_uptime") or 0.0), 3),
            "moving_fraction": round(float(actor.get("moving_fraction") or 0.0), 3),
            "hps": round(float(actor.get("hps") or 0.0), 3),
            "wcl_observed_dps": round(wcl_dps, 3) if wcl_dps else None,
            "ratio_to_wcl": round(dps / wcl_dps, 3) if wcl_dps else None,
        })

    # Spell queue counters are cumulative per bot for the whole route.
    queues = {}
    for row in _spell_queues(report):
        queues[str(row.get("bot_guid"))] = row
    latencies = [float(row.get("mean_release_latency_ms") or 0.0) for row in queues.values() if row.get("released")]

    status = report.get("status") or {}
    heartbeat_wipe_states = []
    heartbeats = run_dir / "heartbeat_events.jsonl"
    if heartbeats.exists():
        for line in heartbeats.read_text().splitlines():
            node = re.findall(r'"route_node_id": "([^"]+)"', line)
            wipe = re.findall(r'"wipe_state": "([^"]+)"', line)
            heartbeat_wipe_states.append([node[0] if node else None, wipe[0] if wipe else None])

    return {
        "schema": "magmaw_spell_queue_run_summary_v1",
        "label": label,
        "run_dir": str(run_dir),
        "worldserver_sha256": binary_sha256,
        "native_clear": bool(outcome.get("native_clear")),
        "native_reason": outcome.get("native_reason"),
        "completion_reason": report.get("completion_reason"),
        "watchdog": outcome.get("watchdog"),
        "route_deaths": status.get("deaths"),
        "route_duration_seconds": status.get("duration_seconds"),
        "heartbeat_route_wipe_states": heartbeat_wipe_states,
        "encounter": {
            "boundary_basis": encounter.get("encounter_window_boundary_basis"),
            "duration_sec": encounter["duration_sec"],
            "party_damage": encounter["party_damage"],
            "encounter_window_party_dps": encounter["encounter_window_party_dps"],
            "party_hps": encounter.get("party_hps"),
            "pets_included_in_owner": True,
        },
        "wcl_reference": {
            "reference_id": (timeline.get("reference") or {}).get("reference_id"),
            "common_window": timeline.get("comparison_window"),
        },
        "actors": actors,
        "spell_queue": {
            "bots": sorted(queues.values(), key=lambda row: str(row.get("bot_guid"))),
            "median_bot_mean_release_latency_ms": round(statistics.median(latencies), 3) if latencies else None,
            "max_release_latency_ms": max((int(row.get("max_release_latency_ms") or 0) for row in queues.values()), default=None),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--binary-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = summarize(args.run_dir, args.timeline, args.label, args.binary_sha256)
    args.output.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    encounter = summary["encounter"]
    print(f"{args.label}: clear={summary['native_clear']} deaths={summary['route_deaths']} "
          f"magmaw={encounter['duration_sec']:.3f}s party_dps={encounter['encounter_window_party_dps']:.0f} "
          f"hps={encounter['party_hps']:.0f} queue_latency_median={summary['spell_queue']['median_bot_mean_release_latency_ms']}")
    for actor in summary["actors"]:
        print(f"  {actor['bot_name']:9} {str(actor['class_spec']):20} {actor['role']:6} "
              f"{actor['encounter_window_dps']:9.0f} wcl={actor['wcl_observed_dps'] or 0:7.0f} "
              f"ratio={actor['ratio_to_wcl'] if actor['ratio_to_wcl'] is not None else '-'} hps={actor['hps']:.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
