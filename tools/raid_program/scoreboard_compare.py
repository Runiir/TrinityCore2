"""Compare two labels: two-sided 95% Welch t-test per actor and for party DPS.

t = delta / sqrt(s1^2/n1 + s2^2/n2), Welch-Satterthwaite degrees of freedom,
critical t = t_{0.975, df}. improved when t > critical, regressed when
t < -critical, otherwise within_noise; insufficient_kills when either label
has fewer than min_kills counted native-clear kills.

keep_decision is the one keep/revert rule: compare_labels()["keep"] and
`scoreboard show` both come from it.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from tools.raid_program.scoreboard_core import (
    COMPARISON_SCHEMA, actor_identity, actor_rows, clear_kills, counted_kills, exclusion_reason, healer_roles,
    kills_per_batch, label_kills, load_records, load_target, mean_sd, roster,
)

MIN_KILLS = 3
ALPHA = 0.05
# Kills that are not gameplay outcomes and so never block condition (a): the harness lost the run,
# the operator interrupted it, or an audited void excluded it.
# A play-mode run (humans in the raid) is never bot gameplay evidence.
NON_GAMEPLAY_EXCLUSIONS = frozenset({"infrastructure_failure", "interrupted", "voided", "play_mode_run"})
COUNTED_CLEAR_BASIS = "counted_native_clears"


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


def batch_shortfall(label: str, clears: int, required: int) -> str:
    return (f"{label} has {clears} counted native-clear kill(s), fewer than kills_per_batch {required}; "
            "see det95 for what these n can detect")


def boss_deaths_per_kill(kills: list[dict[str, Any]]) -> tuple[float | None, list[str]]:
    """Boss-window deaths per counted kill, or None with the kill ids whose count is unknown (never 0)."""
    counted = counted_kills(kills)
    unknown = [record["kill_id"] for record in counted if record.get("boss_window_deaths") is None]
    if unknown:
        return None, unknown
    return (sum(int(record["boss_window_deaths"]) for record in counted) / len(counted) if counted else 0.0), []


def _condition(name: str, ok: bool | None, text: str) -> dict[str, Any]:
    return {"condition": name, "ok": ok, "text": text}


def keep_decision(party: dict[str, Any], actors: dict[str, dict[str, Any]], *, new_label: str, old_label: str,
                  new_kills: list[dict[str, Any]], old_kills: list[dict[str, Any]], targeted_actor: str | None = None,
                  min_kills: int = MIN_KILLS, batch_kills: int = MIN_KILLS,
                  batch_override: int | None = None) -> dict[str, Any]:
    """The keep/revert rule of a candidate label (new) against the baseline (old).

    keep only when all hold:
      (a) every kill recorded under the candidate label is a native clear, apart from kills that are no
          gameplay outcome (NON_GAMEPLAY_EXCLUSIONS); a counted native clear without encounter data
          cannot be judged;
      (b) boss-window deaths per counted kill did not increase; an unknown count cannot be judged;
      (c) neither the party nor any non-healer actor is regressed (two-sided 95% Welch t per row);
      (d) the point estimate is non-negative: the targeted actor's mean, else the party mean, is at
          least the baseline mean;
      and each label has at least kills_per_batch counted native clears (batch_override lowers it).
    A failed condition means revert; otherwise anything unjudged or a short batch means insufficient_kills.
    new_kills and old_kills are every kill recorded under each label; party and actors are Welch rows.
    """
    conditions = []
    blocking = [record["kill_id"] for record in new_kills
                if not record.get("native_clear") and exclusion_reason(record) not in NON_GAMEPLAY_EXCLUSIONS]
    no_data = [record["kill_id"] for record in counted_kills(new_kills)
               if record.get("native_clear") and not record.get("encounter")]
    gameplay = [record for record in new_kills if exclusion_reason(record) not in NON_GAMEPLAY_EXCLUSIONS]
    if blocking:
        conditions.append(_condition("a", False, f"{len(blocking)} kill(s) of {new_label} did not clear natively: "
                                     + ", ".join(blocking)))
    elif no_data:
        conditions.append(_condition("a", None, "counted native clear(s) without encounter-window data: "
                                     + ", ".join(no_data)))
    else:
        conditions.append(_condition("a", True, f"{len(gameplay)} of {len(gameplay)} gameplay kill(s) of {new_label} "
                                     "are native clears"))

    (new_deaths, new_unknown), (old_deaths, old_unknown) = boss_deaths_per_kill(new_kills), boss_deaths_per_kill(old_kills)
    if new_deaths is None or old_deaths is None:
        conditions.append(_condition("b", None, "unknown boss-window deaths in counted kill(s): "
                                     + ", ".join(new_unknown + old_unknown)))
    else:
        conditions.append(_condition("b", new_deaths <= old_deaths, f"boss-window deaths per counted kill "
                                     f"{old_label} {old_deaths:.2f} -> {new_label} {new_deaths:.2f}"))

    rows = {"party": party} | {actor_id: row for actor_id, row in actors.items() if row["gating"]}
    regressed = [name for name, row in rows.items() if row["verdict"] == "regressed"]
    unjudged = [name for name, row in rows.items() if row["verdict"] == "insufficient_kills"]
    if regressed:
        conditions.append(_condition("c", False, f"regressed (two-sided 95% Welch t): {', '.join(regressed)}"))
    elif unjudged:
        conditions.append(_condition("c", None, f"not judged: fewer than {min_kills} counted native-clear kills "
                                     f"on a side for {', '.join(unjudged)}"))
    else:
        conditions.append(_condition("c", True, "neither the party nor any non-healer actor regressed "
                                     "(two-sided 95% Welch t)"))

    subject = f"actor {targeted_actor}" if targeted_actor else "party"
    row = actors.get(targeted_actor) if targeted_actor else party
    if row is None:
        conditions.append(_condition("d", None, f"{subject} is in neither label nor the roster (check --actor)"))
    elif (row.get("basis", COUNTED_CLEAR_BASIS) != COUNTED_CLEAR_BASIS
          or row.get("new_mean") is None or row.get("old_mean") is None):
        conditions.append(_condition("d", None, f"{subject} has no counted native-clear mean on a side"))
    else:
        conditions.append(_condition("d", row["new_mean"] >= row["old_mean"],
                                     f"{subject} mean {row['new_mean']:.0f} vs {old_label} {row['old_mean']:.0f} "
                                     f"({row['new_mean'] - row['old_mean']:+.0f})"))

    required = batch_kills if batch_override is None else batch_override
    short = [batch_shortfall(label, count, required) for label, count in (
        (new_label, len(clear_kills(new_kills))), (old_label, len(clear_kills(old_kills)))) if count < required]
    states = [condition["ok"] for condition in conditions]
    if False in states:
        decision = "revert"
        reasons = [f"({c['condition']}) {c['text']}" for c in conditions if c["ok"] is False]
    else:
        reasons = [f"({c['condition']}) {c['text']}" for c in conditions if c["ok"] is None] + short
        decision = "insufficient_kills" if reasons else "keep"
    return {"decision": decision, "reasons": reasons, "conditions": conditions, "kills_per_batch": required,
            "target_kills_per_batch": batch_kills, "min_kills_override": batch_override}


def _deaths_per_kill(kills: list[dict[str, Any]], field: str) -> float:
    return sum(int(record.get(field) or 0) for record in kills) / len(kills) if kills else 0.0


def compare_labels(root: Path, scenario: str, new_label: str, old_label: str,
                   targeted_actor: str | None = None, batch_kills: int | None = None) -> dict[str, Any]:
    """Party and per-actor DPS deltas of new_label minus old_label with Welch verdicts and keep_decision.

    batch_kills overrides the target's kills_per_batch for the keep decision (show --min-kills).
    """
    target = load_target(Path(root), scenario)
    records = load_records(Path(root), scenario)
    min_kills = int((target.get("noise_rule") or {}).get("min_kills_per_label", MIN_KILLS))
    new_kills, old_kills = label_kills(records, new_label), label_kills(records, old_label)
    new_counted, old_counted = counted_kills(new_kills), counted_kills(old_kills)
    new_clears, old_clears = clear_kills(new_kills), clear_kills(old_kills)
    basis = COUNTED_CLEAR_BASIS
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
    deaths = {"new": _deaths_per_kill(new_counted, "route_deaths"), "old": _deaths_per_kill(old_counted, "route_deaths")}
    boss_deaths = {"new": boss_deaths_per_kill(new_kills)[0], "old": boss_deaths_per_kill(old_kills)[0]}
    keep = keep_decision(party, actors, new_label=new_label, old_label=old_label, new_kills=new_kills,
                         old_kills=old_kills, targeted_actor=targeted_actor, min_kills=min_kills,
                         batch_kills=kills_per_batch(target), batch_override=batch_kills)
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
        "keep": keep,
    }
