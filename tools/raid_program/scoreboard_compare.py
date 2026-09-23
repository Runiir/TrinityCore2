"""Compare two labels: two-sided 95% Welch t-test per actor and for party DPS.

t = delta / sqrt(s1^2/n1 + s2^2/n2), Welch-Satterthwaite degrees of freedom,
critical t = t_{0.975, df}. improved when t > critical, regressed when
t < -critical, otherwise within_noise; insufficient_kills when either label
has fewer than min_kills counted native-clear kills.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from tools.raid_program.scoreboard_core import (
    COMPARISON_SCHEMA, actor_identity, actor_rows, clear_kills, counted_kills, healer_roles, label_kills,
    load_records, load_target, mean_sd, roster,
)

MIN_KILLS = 3
ALPHA = 0.05


def critical_t(df: float, alpha: float = ALPHA) -> float:
    from scipy.stats import t as student_t
    return float(student_t.ppf(1.0 - alpha / 2.0, df))


def welch(new: list[float], old: list[float], min_kills: int = MIN_KILLS) -> dict[str, Any]:
    """Welch t-test of new minus old; verdict improved / regressed / within_noise / insufficient_kills."""
    new_mean, new_sd = mean_sd(new)
    old_mean, old_sd = mean_sd(old)
    delta = new_mean - old_mean if new_mean is not None and old_mean is not None else None
    result = {"new_n": len(new), "old_n": len(old), "new_mean": new_mean, "old_mean": old_mean,
              "delta": delta, "t": None, "df": None, "critical_t": None}
    if len(new) < min_kills or len(old) < min_kills:
        return result | {"verdict": "insufficient_kills"}
    a, b = new_sd ** 2 / len(new), old_sd ** 2 / len(old)
    if a + b == 0.0:  # no spread on either side: any difference is exact
        verdict = "within_noise" if delta == 0 else "improved" if delta > 0 else "regressed"
        return result | {"verdict": verdict}
    t = delta / math.sqrt(a + b)
    df = (a + b) ** 2 / (a ** 2 / (len(new) - 1) + b ** 2 / (len(old) - 1))
    critical = critical_t(df)
    verdict = "improved" if t > critical else "regressed" if t < -critical else "within_noise"
    return result | {"t": t, "df": df, "critical_t": critical, "verdict": verdict}


def keep_recommendation(party: dict[str, Any], actors: dict[str, dict[str, Any]], *,
                        targeted_actor: str | None, new_deaths_per_kill: float, old_deaths_per_kill: float,
                        new_non_clears: int, min_kills: int = MIN_KILLS) -> tuple[str, list[str]]:
    """keep only if party or the targeted actor improved, nothing regressed, boss deaths did not rise.

    The death counts are boss-window deaths per kill: recovered trash deaths are context, not a
    regression (a trash wipe the party does not recover from already fails the kill as a non-clear).

    A candidate label with counted non-clear kills is reverted even before it has enough kills.
    """
    wipes = f"{new_non_clears} counted kill(s) of the candidate label did not clear natively"
    if party["verdict"] == "insufficient_kills":
        if new_non_clears:
            return "revert", [wipes]
        return "insufficient_kills", [f"need >= {min_kills} counted native-clear kills per label"]
    reasons = []
    improved = party["verdict"] == "improved"
    if targeted_actor is not None:
        improved = improved or (actors.get(targeted_actor) or {}).get("verdict") == "improved"
    if not improved:
        reasons.append("neither party DPS nor the targeted actor improved beyond noise"
                       if targeted_actor else "party DPS did not improve beyond noise (pass --actor for a targeted change)")
    regressed = [actor_id for actor_id, row in actors.items() if row["gating"] and row["verdict"] == "regressed"]
    if regressed:
        reasons.append(f"regressed actors: {', '.join(regressed)}")
    if new_deaths_per_kill > old_deaths_per_kill:
        reasons.append(f"boss-window deaths per kill rose {old_deaths_per_kill:.2f} -> {new_deaths_per_kill:.2f}")
    if new_non_clears:
        reasons.append(wipes)
    return ("revert" if reasons else "keep"), reasons


def _deaths_per_kill(kills: list[dict[str, Any]], field: str) -> float:
    return sum(int(record.get(field) or 0) for record in kills) / len(kills) if kills else 0.0


def compare_labels(root: Path, scenario: str, new_label: str, old_label: str,
                   targeted_actor: str | None = None) -> dict[str, Any]:
    """Party and per-actor DPS deltas of new_label minus old_label with Welch verdicts."""
    target = load_target(Path(root), scenario)
    records = load_records(Path(root), scenario)
    min_kills = int((target.get("noise_rule") or {}).get("min_kills_per_label", MIN_KILLS))
    new_kills, old_kills = label_kills(records, new_label), label_kills(records, old_label)
    new_counted, old_counted = counted_kills(new_kills), counted_kills(old_kills)
    new_clears, old_clears = clear_kills(new_kills), clear_kills(old_kills)
    basis = "counted_native_clears"
    if not new_clears or not old_clears:
        # Keep a numeric delta when a side has counted kills but no clear (e.g. boss wipes);
        # such a delta is never judged: its verdict is insufficient_kills.
        basis = "counted_kills_with_encounter_data"
        new_clears = [record for record in new_counted if record.get("encounter")]
        old_clears = [record for record in old_counted if record.get("encounter")]

    def judged(new: list[float], old: list[float]) -> dict[str, Any]:
        change = welch(new, old, min_kills)
        if basis != "counted_native_clears":
            change |= {"t": None, "df": None, "critical_t": None, "verdict": "insufficient_kills"}
        return change | {"basis": basis}

    party = judged([float(r["encounter"]["encounter_window_party_dps"]) for r in new_clears],
                   [float(r["encounter"]["encounter_window_party_dps"]) for r in old_clears])
    new_rows, old_rows = actor_rows(new_clears), actor_rows(old_clears)
    actor_ids = list(dict.fromkeys([*roster(target), *new_rows, *old_rows]))
    healers = healer_roles(target)
    actors = {}
    for actor_id in sorted(actor_ids, key=lambda key: (0, int(key)) if key.isdigit() else (1, key)):
        spec, role, name = actor_identity(target, actor_id, new_rows.get(actor_id) or old_rows.get(actor_id) or [])
        change = judged([float(row["encounter_window_dps"]) for row in new_rows.get(actor_id, [])],
                        [float(row["encounter_window_dps"]) for row in old_rows.get(actor_id, [])])
        actors[actor_id] = {"spec": spec, "role": role, "name": name, "gating": role not in healers, **change}
    new_clear_count = len(clear_kills(new_kills))
    deaths = {"new": _deaths_per_kill(new_counted, "route_deaths"), "old": _deaths_per_kill(old_counted, "route_deaths")}
    boss_deaths = {"new": _deaths_per_kill(new_counted, "boss_window_deaths"),
                   "old": _deaths_per_kill(old_counted, "boss_window_deaths")}
    decision, reasons = keep_recommendation(
        party, actors, targeted_actor=targeted_actor, new_deaths_per_kill=boss_deaths["new"],
        old_deaths_per_kill=boss_deaths["old"], new_non_clears=len(new_counted) - new_clear_count, min_kills=min_kills)
    durations = {side: mean_sd([float(r["encounter"]["duration_sec"]) for r in clears])[0]
                 for side, clears in (("new", new_clears), ("old", old_clears))}
    return {
        "schema": COMPARISON_SCHEMA,
        "scenario": scenario,
        "new_label": new_label,
        "old_label": old_label,
        "test": "two_sided_welch_t", "alpha": ALPHA, "min_kills_per_label": min_kills, "basis": basis,
        "party": party,
        "actors": actors,
        "route_deaths_per_kill": deaths,
        "boss_window_deaths_per_kill": boss_deaths,
        "mean_duration_sec": durations,
        "targeted_actor": targeted_actor,
        "keep": {"decision": decision, "reasons": reasons},
    }
