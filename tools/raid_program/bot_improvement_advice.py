"""Optional per-bot suggestions from existing evidence_view comparisons.

No model vote gates commits, experiments, graph transitions or acceptance.
Full inputs stay in the receipt; only one actor/component is sent per request.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from tools.bot_ml import analyze_magmaw_trace as analyzer
from tools.bot_ml import jev_shadow, laya_packets

SCHEMA = "bot_improvement_advice_v1"
MAX_STATE_BYTES = 1800  # Conservative preflight, NOT an exact tokenizer count.
OPTIONS = {
    "compare_setup": "Resolve unmatched setup/reference before tuning.",
    "inspect_cadence": "Inspect fewer casts or avoidable idle.",
    "inspect_damage": "Inspect damage per event, modifiers or procs.",
    "inspect_target_execution": "Inspect target binding, LOS or native failures.",
    "inspect_priority": "Inspect an observed eligible-action priority conflict.",
    "account_for_duty": "Account for observed required duty/movement first.",
    "no_supported_change": "No change supported in this slice.",
    "insufficient_evidence": "Missing evidence prevents a useful suggestion.",
}
FOLLOWUPS = {
    "compare_setup": "Join gear, effective stats, target count, buffs, window and phase coverage; do not tune against an incompatible reference.",
    "inspect_cadence": "Inspect actor/spell cast starts, finishes, resources and idle intervals. Separate unavoidable duty from avoidable gaps.",
    "inspect_damage": "Join ordinary hits, crits, ticks, copies and pets with effective stats before changing native mechanics.",
    "inspect_target_execution": "Read the interval from proposed target through binding, native submission and outcome, including range/LOS.",
    "inspect_priority": "Replay eligible candidates against the declared comparator and action legality. Selection counts alone do not prove a priority defect.",
    "account_for_duty": "Join the duty intervals to cast gaps and movement. Do not subtract all duty time or count continuing DoTs/pets as fresh casts.",
    "no_supported_change": "Keep this slice unchanged; inspect other measured gaps. This is not actor or encounter acceptance.",
    "insufficient_evidence": "Retrieve the missing actor-scoped observation from retained evidence first; do not launch another run solely on this suggestion.",
}


def encoded(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def compact_checks(checks):
    return {key: ({"status": row["status"], "value": row["current"]}
                  if row.get("status") == "match" and "current" in row
                  and row.get("current") == row.get("reference") else row)
            for key, row in checks.items()}


def compact_component(component):
    if component is None:
        return None
    result = dict(component)
    for side in ("current", "reference"):
        if isinstance(result.get(side), dict):
            result[side] = {k: v for k, v in result[side].items()
                            if not (k == "name" and v == component.get("name"))
                            and not (k == "spell_id" and str(v) == str(component.get("key")))}
    return result


def projections(report, actor=None, top=2):
    """Consume full comparison output, never raw logs or agent-written goals."""
    if report.get("schema") not in {"evidence_comparison_v1", "raid_damage_gap_comparison_v1"}:
        raise ValueError("requires evidence_view compare --output JSON")
    if top < 1 or top > 5:
        raise ValueError("top must be between 1 and 5")
    result = []
    for index, pair in enumerate(report.get("pairs", report.get("actors", []))):
        current = pair.get("current", pair)
        aid = current.get("actor", current.get("actor_guid"))
        if aid is None:
            raise ValueError("actor identity missing; use full comparison --output, not a roster overview")
        if actor is not None and str(aid) != str(actor):
            continue
        reference = pair.get("reference", {})
        context = {
            "kind": report.get("kind", "wcl"),
            "status": pair.get("status", "diagnostic_only"),
            "checks": compact_checks(pair.get("context_comparison", {}).get("checks", {})),
            "setup_differences": pair.get("setup_differences"),
            "setup_differences_omitted": pair.get("setup_differences_omitted", 0),
            "missing": current.get("completeness", {}).get("missing_observations"),
        }
        if report.get("schema") == "raid_damage_gap_comparison_v1":
            context["reference_limitations"] = pair.get("limitations")
            context["duty_coverage"] = pair.get("duty_coverage")
        # A missing check is unknown, never an inferred pass. Keep whole checks.
        rows = pair.get("components", [])
        for component in rows[:top] or [None]:
            state = {
                "actor": str(aid), "spec": current.get("spec"), "role": current.get("role"),
                "context": context,
                "dps": [current.get("dps", current.get("native_dps")), reference.get("dps", pair.get("reference_dps"))],
                "window": [current.get("window", report.get("window")), reference.get("window")],
                "component": compact_component(component),
                "activity": current.get("activity"),
                "duties": current.get("duties"),
                "residual_dps": pair.get("reconciliation", {}).get("unattributed_residual_dps"),
                "components_outside_this_packet": max(0, len(rows) - (1 if component else 0)) + pair.get("components_omitted", 0),
            }
            result.append({"actor": str(aid), "pair_index": index,
                           "component_key": (component or {}).get("key", (component or {}).get("name")),
                           "state": state})
    if not result:
        raise ValueError("no selected actors in comparison")
    return result


def packet(state, model):
    return {"model": model, "state": state, "questions": {"next_investigation": {
        "type": "choice",
        "instructions": (
            "Suggest one investigation for this actor/component, not approval. "
            "Use supplied facts only. Missing checks are unknown. Selections are not completed casts; "
            "damage gaps are not recoverable DPS. A priority defect needs eligible candidates. "
            "Duty overlap does not prove all downtime necessary. Return insufficient_evidence when needed."
        ),
        "criteria": OPTIONS,
    }}}


def review(report, output, *, actor=None, top=2, backend="both", env_file=Path(".env"),
           endpoint=jev_shadow.ENDPOINT, prepare_only=False):
    slices = projections(report, actor, top)
    output.mkdir(parents=True, exist_ok=False)
    (output / "comparison.json").write_bytes(encoded(report) + b"\n")
    providers = ["local", "hosted"] if backend == "both" else [backend]
    if any(p not in {"local", "hosted"} for p in providers):
        raise ValueError("unknown provider")
    rows = []
    for part in slices:
        for provider in providers:
            request = packet(part["state"], laya_packets.MODEL if provider == "local" else analyzer.JEV_MODEL)
            row = {k: v for k, v in part.items() if k != "state"}
            row.update(provider=provider, request=request, request_sha256=digest(request),
                       endpoint=endpoint if provider == "local" else analyzer.JEV_URL,
                       status="prepared", response=None, error=None, suggestion=None,
                       state_bytes=len(encoded(part["state"])))
            started = time.monotonic()
            if row["state_bytes"] > MAX_STATE_BYTES:
                row.update(status="not_reviewed", error="state_budget_preflight: narrow the comparison; no evidence was truncated")
            elif not prepare_only:
                try:
                    response = (jev_shadow.call_local(request, endpoint) if provider == "local" else
                                analyzer._call_jev(request["state"], analyzer._jev_key(env_file), request["questions"], attempts=1))
                    analyzer._validate_typed_answers(response["answers"], request["questions"])
                    answer = response["answers"]["next_investigation"]
                    row.update(status="advisory", response=response, suggestion={
                        "choice": answer["choice"], "next_step": FOLLOWUPS[answer["choice"]],
                        "probabilities": answer["probabilities"], "confidence": answer["confidence"],
                        "basis": "model suggestion; reviewer must verify against comparison and retained events",
                    })
                except Exception as exc:
                    row.update(status="not_reviewed", error=f"{type(exc).__name__}: {exc}")
            row["latency_seconds"] = round(time.monotonic() - started, 3)
            rows.append(row)
    summary = {"schema": SCHEMA, "comparison_sha256": digest(report),
               "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "authority": "suggestions_only", "acceptance_changed": False,
               "training_eligible": False, "prepared_only": prepare_only,
               "reviews": [{k: v for k, v in row.items() if k not in {"request", "response"}} for row in rows]}
    (output / "examples.jsonl").write_bytes(b"".join(encoded(row) + b"\n" for row in rows))
    (output / "summary.json").write_bytes(encoded(summary) + b"\n")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--actor")
    parser.add_argument("--top", type=int, default=2)
    parser.add_argument("--backend", choices=("local", "hosted", "both"), default="both")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--endpoint", default=jev_shadow.ENDPOINT)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args(argv)
    summary = review(json.loads(args.comparison.read_text()), args.output, actor=args.actor,
                     top=args.top, backend=args.backend, env_file=args.env_file,
                     endpoint=args.endpoint, prepare_only=args.prepare_only)
    print(json.dumps(summary))
    return 0  # Model disagreement/unavailability never becomes an execution gate.


if __name__ == "__main__":
    raise SystemExit(main())
