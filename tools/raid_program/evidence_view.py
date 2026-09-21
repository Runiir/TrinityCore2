"""Compact run/reference comparisons and paginated evidence. Read-only inputs.

Use `compare --current INPUT --baseline INPUT`, `--wowsims INPUT`, or `--wcl INPUT`.
INPUT accepts JSON or archive.tar.gz::exact/member.json. No hydration or live work.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tarfile
import sys

from tools.raid_program.evidence_inputs import inventory, load_input, select_path
from tools.raid_program.evidence_metrics import native_actors, simulator_actor, wcl_actor
from tools.raid_program.evidence_events import query_events
from tools.raid_program.evidence_paging import bounded_select, command_with, encoded, outline


def select_actor(actors, selected):
    if selected is not None:
        if str(selected) not in actors:
            raise ValueError(f"unknown actor {selected}; available: {', '.join(actors)}")
        return actors[str(selected)]
    if len(actors) != 1:
        raise ValueError("select --actor/--baseline-actor explicitly for a multi-actor detail comparison")
    return next(iter(actors.values()))


def scalar_delta(current, reference):
    return None if current is None or reference is None else current - reference


def overview(actors):
    return [{k: a.get(k) for k in ("actor", "name", "spec", "role", "dps", "hps", "duration_seconds")}
            for a in actors.values()]


def setup_differences(current, reference):
    differences = []
    left, right = current.get("setup", {}), reference.get("setup", {})
    for key in sorted(set(left) | set(right)):
        if key == "stats":
            for field in sorted(set(left.get(key, {})) | set(right.get(key, {}))):
                a, b = left.get(key, {}).get(field), right.get(key, {}).get(field)
                if a != b:
                    differences.append({"field": f"stats.{field}", "current": a, "reference": b})
        elif left.get(key) != right.get(key):
            a, b = left.get(key), right.get(key)
            if key == "modifier_effects":
                a = [x for x in left.get(key, []) if x not in right.get(key, [])]
                b = [x for x in right.get(key, []) if x not in left.get(key, [])]
            differences.append({"field": key, "current": a, "reference": b})
    return differences


def paired_components(current, reference):
    rows = []
    for key in sorted(set(current["components"]) | set(reference["components"])):
        a, b = current["components"].get(key), reference["components"].get(key)
        # Absent rows are unknown, not zero. The total residual keeps them visible.
        da, db = a.get("damage") if a else None, b.get("damage") if b else None
        na = da / current["duration_seconds"] if da is not None else None
        nb = db / reference["duration_seconds"] if db is not None else None
        row = {"key": key, "name": (a or b).get("name"), "current_dps": na, "reference_dps": nb,
               "apparent_gap_dps": scalar_delta(nb, na),
               "current": a, "reference": b, "recoverable_dps": None}
        rows.append(row)
    return sorted(rows, key=lambda r: (r["apparent_gap_dps"] is None, -abs(r["apparent_gap_dps"] or 0), r["key"]))


def pair_context(current, reference, kind):
    fields = {"spec": (current.get("spec"), reference.get("spec")),
              "role": (current.get("role"), reference.get("role")),
              "mode": (current.get("identity", {}).get("mode"), reference.get("identity", {}).get("mode"))}
    checks = {key: {"current": a, "reference": b,
                    "status": "missing" if a is None or b is None else "match" if a == b else "mismatch"}
              for key, (a, b) in fields.items()}
    mismatch = kind == "native" and any(c["status"] == "mismatch" for c in checks.values())
    changes = [{"field": key, "current": current.get("identity", {}).get(key),
                "reference": reference.get("identity", {}).get(key)}
               for key in ("server_epoch", "attempt_id", "cohort_id", "scenario_id", "capture_id", "source")
               if current.get("identity", {}).get(key) != reference.get("identity", {}).get(key)]
    return {"status": "incompatible_context" if mismatch else "diagnostic_only",
            "checks": checks, "identity_differences": changes,
            "interpretation": "Run identities normally differ between experiments. Same GUID does not prove same spec, role, setup or scenario. Missing checks do not establish comparability."}


def compare_pair(current, reference, kind="native"):
    rows = paired_components(current, reference)
    gap = scalar_delta(reference["dps"], current["dps"])
    known = [r["apparent_gap_dps"] for r in rows if r["apparent_gap_dps"] is not None]
    signed = sum(known)
    context = pair_context(current, reference, kind)
    return {"current": {k: v for k, v in current.items() if k != "components"},
            "reference": {k: v for k, v in reference.items() if k != "components"},
            "delta_dps_current_minus_reference": scalar_delta(current["dps"], reference["dps"]),
            "delta_hps_current_minus_reference": scalar_delta(current["hps"], reference["hps"]),
            "setup_differences": setup_differences(current, reference),
            "reconciliation": {"total_gap_dps": gap, "component_losses_dps": sum(x for x in known if x > 0),
                "component_gains_dps": -sum(x for x in known if x < 0), "signed_component_gap_dps": signed,
                "unattributed_residual_dps": scalar_delta(gap, signed),
                "basis": "reference minus current; missing components and denominator differences remain residual"},
            "components": rows, "status": context["status"], "context_comparison": context,
            "limitations": ["Apparent gaps do not estimate recoverable DPS or establish patch causality.",
                "Different fight lengths, setup, duties and phase coverage require review before performance acceptance.",
                "Literal spell IDs are aligned; unmapped aliases remain explicit."]}


def wcl_comparison(current_doc, refs, actor=None):
    from tools.bot_ml.rank_raid_damage_gaps import compare
    full = compare(current_doc, refs)
    for a in full["actors"]:
        gap = a.get("apparent_dps_gap")
        signed = sum(c["apparent_dps_gap"] for c in a["components"])
        a["reconciliation"] = {"total_gap_dps": gap, "signed_component_gap_dps": signed,
                                "unattributed_residual_dps": scalar_delta(gap, signed)}
    if actor is not None:
        full["actors"] = [a for a in full["actors"] if str(a["actor_guid"]) == str(actor)]
        if not full["actors"]:
            raise ValueError("selected actor is absent from native timeline")
    return full


def comparison(current_doc, reference_doc, kind, actor=None, reference_actor=None, player_index=0, reference_id=None):
    if kind == "wcl" and isinstance(reference_doc.get("actors"), dict):
        return wcl_comparison(current_doc, reference_doc, actor)
    current = native_actors(current_doc)
    reference = native_actors(reference_doc) if kind == "native" else None
    report = {"schema": "evidence_comparison_v1", "kind": kind, "current_roster": overview(current),
              "reference_roster": overview(reference) if reference is not None else None, "pairs": []}
    if kind == "wcl":
        selected = {actor: select_actor(current, actor)} if actor is not None else current
        report["unmatched_current_actors"] = []
        for key, a in selected.items():
            b = wcl_actor(reference_doc, a["spec"], reference_id, reference_actor)
            if b is None:
                report["unmatched_current_actors"].append(key)
            else:
                report["pairs"].append(compare_pair(a, b, kind))
        return report
    if actor is not None or len(current) == 1:
        a = select_actor(current, actor)
        if reference is not None:
            mapped_actor = reference_actor if reference_actor is not None else a["actor"]
            if mapped_actor not in reference:
                raise ValueError("native actor GUID changed; supply --baseline-actor explicitly")
            b = select_actor(reference, mapped_actor)
        else:
            b = simulator_actor(reference_doc, player_index)
        report["pairs"].append(compare_pair(a, b, kind))
    elif reference is not None:
        for key in current:
            if key in reference:
                report["pairs"].append(compare_pair(current[key], reference[key], kind))
        report["unmatched_current_actors"] = sorted(set(current) - set(reference))
        report["unmatched_reference_actors"] = sorted(set(reference) - set(current))
    else:
        raise ValueError("WoWSims comparison requires --actor for a multi-actor native input")
    return report


def brief_activity(activity):
    result = {k: v for k, v in activity.items() if not isinstance(v, (dict, list))}
    for key, value in activity.items():
        if isinstance(value, dict):
            entries = [(k, v) for k, v in value.items() if not isinstance(v, (dict, list))]
            result[key] = dict(entries[:12])
            if len(entries) > 12:
                result[key+"_omitted"] = len(entries)-12
        elif isinstance(value, list):
            result[key+"_observations"] = len(value)
            if key == "target_switch_latency_ms" and value:
                values = [r["latency_ms"] for r in value if r.get("latency_ms") is not None]
                result["maximum_target_switch_latency_ms"] = max(values, default=None)
    return result


def compact_comparison(report, top=8, actor=None, offset=0, limit=10):
    if report.get("schema") == "raid_damage_gap_comparison_v1":
        return {**{k: report[k] for k in ("schema", "identity", "window", "interpretation")},
                "actors": [{k: v for k, v in a.items() if k not in ("components", "duties")}
                           | {"components": a["components"][:top] if actor is not None else [],
                              "components_omitted": max(0, len(a["components"]) - (top if actor is not None else 0))}
                           for a in report["actors"][offset:offset+limit]],
                "actor_count": len(report["actors"]), "next_offset": offset+limit if offset+limit < len(report["actors"]) else None}
    out = {k: v for k, v in report.items() if k != "pairs"}
    out["pairs"] = []
    out["current_roster"] = report["current_roster"][offset:offset+limit]
    out["reference_roster"] = (report["reference_roster"] or [])[offset:offset+limit]
    out["pair_count"] = len(report["pairs"])
    out["next_offset"] = offset+limit if offset+limit < len(report["pairs"]) else None
    for p in report["pairs"][offset:offset+limit]:
        if actor is None and len(report["pairs"]) > 1:
            out["pairs"].append({"actor": p["current"]["actor"],
                "delta_dps_current_minus_reference": p["delta_dps_current_minus_reference"],
                "delta_hps_current_minus_reference": p["delta_hps_current_minus_reference"],
                "reconciliation": p["reconciliation"], "setup_difference_count": len(p["setup_differences"]),
                "detail": "Select --actor for component and setup differences", "status": p["status"],
                "context_checks": p["context_comparison"]["checks"]})
            continue
        item = {k: p[k] for k in ("status", "context_comparison", "delta_dps_current_minus_reference", "delta_hps_current_minus_reference", "reconciliation", "limitations")}
        for key in ("current", "reference"):
            item[key] = {k: p[key].get(k) for k in ("actor", "spec", "dps", "hps", "damage", "window", "identity", "gates", "gate_binding", "iterations", "dps_distribution", "limitations") if k in p[key]}
            item[key]["activity"] = brief_activity(p[key].get("activity", {}))
            item[key]["setup_observations"] = {"stats_present": bool(p[key].get("setup", {}).get("stats")),
                                               "gear_present": bool(p[key].get("setup", {}).get("gear_sha256"))}
            if "completeness" in p[key]:
                item[key]["completeness"] = {k: len(v) if isinstance(v, (list, dict)) and k not in
                    ("missing_observations", "unavailable_correlations") else v
                    for k, v in p[key]["completeness"].items()}
        detail = actor is not None or len(report["pairs"]) == 1
        item["setup_differences"] = p["setup_differences"][:top]
        item["setup_differences_omitted"] = max(0, len(p["setup_differences"]) - top)
        item["components"] = p["components"][:top] if detail else []
        omitted = p["components"][top:] if detail else p["components"]
        item["components_omitted"] = len(omitted)
        item["omitted_signed_gap_dps"] = sum(r["apparent_gap_dps"] or 0 for r in omitted)
        out["pairs"].append(item)
    return out


def fit_comparison(full, args, argv):
    top, limit = args.top, args.limit
    while True:
        result = compact_comparison(full, top, args.actor, args.offset, limit)
        result["sources"] = full["sources"]
        result["full_comparison"] = str(args.output) if args.output else None
        result["requested_top"] = args.top
        result["displayed_top_limit"] = top
        result["detail_command"] = command_with(argv, view_path=f"/pairs/{args.offset}/components" if "pairs" in full else f"/actors/{args.offset}/components", offset=0, limit=5)
        if result.get("next_offset") is not None:
            result["next_command"] = command_with(argv, offset=result["next_offset"], limit=limit, top=max(1, top))
        if len(encoded(result)) <= args.max_chars:
            return result
        if top > 0:
            top //= 2
        elif limit > 1:
            limit = max(1, limit//2)
        else:
            rows = full.get('pairs', full.get('actors', []))
            row = rows[args.offset] if args.offset < len(rows) else {}
            return {"view": "minimal_comparison", "pairs": [{
                        "actor": row.get('current', {}).get('actor', row.get('actor_guid')),
                        "reconciliation": row.get('reconciliation'), "status": row.get('status'),
                        "delta_dps_current_minus_reference": row.get('delta_dps_current_minus_reference')}],
                    "detail_command": result['detail_command'],
                    "setup_command": command_with(argv, view_path=f"/pairs/{args.offset}/setup_differences", offset=0, limit=3) if 'pairs' in full else None,
                    "next_offset": result.get('next_offset'), "next_command": result.get('next_command'),
                    "source_hashes": {k:v["payload_sha256"] for k,v in full["sources"].items()},
                    "limits": "Diagnostic only; use details for context and omitted observations. No performance acceptance."}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    task = sub.add_parser("task", help="Resolve exact comparison commands from saved receipts and promoted references")
    task.add_argument("--root", type=Path, default=Path.cwd())
    inspect = sub.add_parser("inspect", help="JSON shape/actors, or regular JSON archive members")
    inspect.add_argument("input")
    inspect.add_argument("--offset", type=int, default=0)
    inspect.add_argument("--limit", type=int, default=20)
    select = sub.add_parser("select", help="Read an explicit JSON Pointer; arrays/dicts are paginated")
    select.add_argument("input")
    select.add_argument("--path", required=True)
    select.add_argument("--offset", type=int, default=0)
    select.add_argument("--limit", type=int, default=10)
    admit = sub.add_parser("admission", help="Run existing joined gear/stat/consume gates before routing a setup repair")
    admit.add_argument("--current", required=True)
    admit.add_argument("--wowsims-request", required=True)
    admit.add_argument("--wowsims-result", required=True)
    admit.add_argument("--compute-stats", required=True)
    admit.add_argument("--debug-result")
    admit.add_argument("--reference-class", required=True, choices=("self_provided_baseline", "controlled_live_parity"))
    admit.add_argument("--actor")
    admit.add_argument("--player-index", type=int, default=0)
    compare = sub.add_parser("compare", help="Rank signed differences without dumping source logs")
    compare.add_argument("--current", required=True)
    rhs = compare.add_mutually_exclusive_group(required=True)
    rhs.add_argument("--baseline")
    rhs.add_argument("--wowsims")
    rhs.add_argument("--wcl", help="Existing normalized rank_raid_damage_gaps references; current must be bot_timeline JSON")
    compare.add_argument("--actor")
    compare.add_argument("--baseline-actor")
    compare.add_argument("--reference-actor", help="Explicit WCL actor ID (native baseline uses --baseline-actor)")
    compare.add_argument("--reference-id", help="Select an entry from a retained WCL reference catalog")
    compare.add_argument("--player-index", type=int, default=0)
    compare.add_argument("--top", type=int, default=8)
    compare.add_argument("--offset", type=int, default=0)
    compare.add_argument("--limit", type=int, default=10, help="Maximum actor pairs in overview")
    compare.add_argument("--output", type=Path, help="Optional full comparison file; stdout remains compact")
    compare.add_argument("--view-path", help="JSON Pointer into the full computed comparison, with --offset/--limit")
    events = sub.add_parser("events", help="Filter existing timeline/decision records; defaults to 20 rows")
    events.add_argument("input")
    for key in ("actor", "spell", "target", "phase", "kind"):
        events.add_argument("--" + key)
    for key in ("start-ms", "end-ms"):
        events.add_argument("--" + key, type=float)
    events.add_argument("--clock", choices=("relative", "absolute"), default="relative")
    events.add_argument("--offset", type=int, default=0)
    events.add_argument("--limit", type=int, default=20)
    for command in (inspect, select, events, admit, task):
        command.add_argument("--output", type=Path, help="Export requested result; stdout remains bounded")
    for command in (inspect, select, compare, events, admit, task):
        command.add_argument("--max-chars", type=int, default=12000, help="Stdout budget, 2000..16000 characters")
    args = parser.parse_args(argv)
    try:
        if not 2000 <= args.max_chars <= 16000:
            raise ValueError("--max-chars must be 2000..16000")
        if args.command == "task":
            from tools.raid_program.evidence_task import task_view
            result = task_view(args.root)
        elif args.command == "admission":
            from tools.raid_program.evidence_admission import admission
            result, full = admission(args.current, args.wowsims_request, args.wowsims_result,
                                     args.compute_stats, args.reference_class, args.actor, args.debug_result, args.player_index)
            if args.output:
                args.output.write_text(json.dumps(full, allow_nan=False) + "\n")
        elif args.command == "inspect" and "::" not in args.input and tarfile.is_tarfile(args.input):
            with tarfile.open(args.input) as archive:
                members = [{"member": m.name, "bytes": m.size} for m in archive
                           if m.isfile() and m.name.endswith((".json", ".jsonl"))]
            result = bounded_select({'members': members}, '/members', args.offset, args.limit, argv, args.max_chars-500)
            # inspect owns the members pointer internally; its continuation takes only offsets.
            if result.get('next_offset') is not None:
                result['next_command'] = command_with(argv, offset=result['next_offset'], limit=result['page_limit'])
            result.update(archive=args.input, usage='Use archive::exact/member.json; no extraction needed')
        elif args.command == "compare":
            if not 1 <= args.top <= 30 or not 1 <= args.limit <= 25 or args.offset < 0:
                raise ValueError("--top must be 1..30, --limit 1..25, --offset nonnegative")
            kind = "native" if args.baseline else "wowsims" if args.wowsims else "wcl"
            current, left = load_input(args.current)
            reference, right = load_input(args.baseline or args.wowsims or args.wcl)
            full = comparison(current, reference, kind, args.actor,
                              args.baseline_actor if kind == "native" else args.reference_actor,
                              args.player_index, args.reference_id)
            full["sources"] = {"current": left, "reference": right}
            if args.output:
                args.output.write_text(json.dumps(full, indent=2, allow_nan=False) + "\n")
            result = (bounded_select(full, args.view_path, args.offset, args.limit, argv, args.max_chars-1500, view_path=True)
                      if args.view_path else fit_comparison(full, args, argv))
            if args.view_path:
                result['sources'] = full['sources']
        else:
            document, receipt = load_input(args.input)
            if args.command == "inspect":
                result = inventory(document, receipt)
            elif args.command == "select":
                result = select_path(document, args.path, args.offset, args.limit)
                result["source"] = receipt
                if args.output:
                    args.output.write_text(json.dumps(result, allow_nan=False) + "\n")
                result = bounded_select(document, args.path, args.offset, args.limit, argv, args.max_chars-1000)
                result["source"] = receipt
            else:
                result = query_events(document, **{k: getattr(args, k) for k in
                    ("actor", "spell", "target", "phase", "kind", "start_ms", "end_ms", "clock", "offset", "limit")})
                result["source"] = receipt
        if args.command not in ("compare", "select", "admission") and args.output:
            args.output.write_text(json.dumps(result, allow_nan=False) + "\n")
        if args.command == "events":
            requested = args.limit
            while len(encoded(result)) > args.max_chars and len(result["records"]) > 1:
                result["records"] = result["records"][:max(1,len(result["records"])//2)]
                result["returned_records"] = len(result["records"])
                result["next_offset"] = args.offset+len(result["records"])
            if len(encoded(result)) > args.max_chars and result["records"]:
                row = result["records"][0]
                result["records"] = [{"locator": row["locator"], "view": "oversized_record_structure",
                    "value": outline(select_path(document, row['locator'], 0, 100)['value'], row["locator"], 1),
                    "detail_command": command_with(["select", args.input], path=row["locator"], limit=5)}]
            if result["next_offset"] is not None:
                result["next_command"] = command_with(argv, offset=result["next_offset"], limit=len(result["records"]))
            result["requested_limit"] = requested
        if len(encoded(result)) > args.max_chars:
            result = {"view": "oversized_result_structure", "value": outline(result, "", 2),
                      "output": str(args.output) if args.output else None,
                      "instruction": "Use explicit pointers and smaller pages; no raw-log fallback is needed."}
        rendered = encoded(result)
        print(rendered)
    except (ValueError, KeyError, IndexError, OSError, tarfile.TarError) as exc:
        parser.exit(2, f"evidence_view: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
