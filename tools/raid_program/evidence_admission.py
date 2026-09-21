"""Join exact supplied inputs through existing rotation-review admission logic."""
from __future__ import annotations

from tools.raid_program.evidence_inputs import load_input
from tools.raid_program.evidence_metrics import native_actors


def admission(current, request, result, compute_stats, reference_class, actor=None, debug_result=None, player_index=0):
    from tools.bot_ml.review_rotation_mechanics import build_review, find_wowsims_apl
    inputs = {"runtime_report": current, "wowsims_request": request,
              "wowsims_result": result, "wowsims_compute_stats": compute_stats}
    if debug_result:
        inputs["wowsims_debug_result"] = debug_result
    loaded, sources = {}, {}
    for key, path in inputs.items():
        loaded[key], sources[key] = load_input(path)
    actors = native_actors(loaded["runtime_report"])
    if actor is None:
        if len(actors) != 1:
            raise ValueError("admission requires --actor for a multi-actor report")
        actor = next(iter(actors))
    actor = str(actor)
    if actor not in actors:
        raise ValueError(f"unknown actor {actor}; available: {', '.join(actors)}")
    doc = loaded["runtime_report"]
    if "combat_calibration" not in doc:
        raise ValueError("setup admission needs the retained calibration report; a raid timeline alone lacks setup evidence")
    cal = doc["combat_calibration"]
    if not (cal.get("window_complete") or cal.get("phase") == "complete"):
        cal = cal.get("previous_window") or cal
    bots = [b for b in cal.get("bots", []) if str(b.get("guid")) == actor]
    if len(bots) != 1:
        raise ValueError("actor does not identify one scored bot")
    # Pass one complete scoring snapshot, avoiding duplicate legacy previous_window
    # or unrelated bot/trace roots in normalize_runtime_report.
    loaded["runtime_report"] = {"combat_calibration": {k:v for k,v in cal.items() if k not in ("bots", "previous_window")} | {"bots": bots}}
    loaded["wowsims_apl"] = find_wowsims_apl(loaded["wowsims_request"], player_index)
    full = build_review(**loaded, wowsims_player_index=player_index, reference_class=reference_class, sources=sources)
    gates = {key: {k:v for k,v in full[key].items() if k in
                  ("status", "reason", "tuning_admitted", "comparison_admitted", "first_broken_edge")}
             for key in ("gear_parity", "effective_stat_parity", "consumable_parity", "dps_tuning_gate", "total_dps_comparison_gate")}
    admitted = full["total_dps_comparison_gate"].get("comparison_admitted") is True
    summary = {"schema": "evidence_admission_v1", "actor": actor, "reference_class": reference_class,
        "sources": sources, "gates": gates, "setup_comparison_admitted": admitted,
        "policy": ("Self-provided baseline uses existing one-sided favorable-stat rules; higher throughput stats alone are not a setup defect."
                   if reference_class == "self_provided_baseline" else "Controlled live parity requires the existing like-for-like checks."),
        "next_action": ("Continue damage-loss attribution; do not route a setup/stat repair from raw deltas alone."
                        if admitted else "Inspect the failing or missing joined gate before choosing a setup/stat repair."),
        "limits": ["Admission does not prove coefficient/cadence correctness or recoverable DPS.",
                   "Exact supplied sources are hashed; caller must bind them to the intended run and promoted catalog.",
                   "Per-spell causal diagnosis and all parent actor/raid requirements remain separate."]}
    return summary, full
