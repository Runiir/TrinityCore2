"""Plain-text scoreboard table, the noise rule and the keep/revert recommendation."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from tools.raid_program.scoreboard import (
    actor_rows, clear_kills, evaluate_target, label_kills, latest_label, load_records, load_target, mean_sd,
)

MIN_KILLS = 3


def noise_verdict(new: list[float], old: list[float], min_kills: int = MIN_KILLS) -> dict[str, Any]:
    """improved / regressed / within_noise when both sides have >= min_kills values."""
    new_mean, new_sd = mean_sd(new)
    old_mean, old_sd = mean_sd(old)
    delta = new_mean - old_mean if new_mean is not None and old_mean is not None else None
    if len(new) < min_kills or len(old) < min_kills:
        return {"delta": delta, "threshold": None, "verdict": "insufficient_kills"}
    threshold = 2.0 * math.sqrt(new_sd ** 2 / len(new) + old_sd ** 2 / len(old))
    verdict = "improved" if delta > threshold else "regressed" if delta < -threshold else "within_noise"
    return {"delta": delta, "threshold": threshold, "verdict": verdict}


def keep_recommendation(party: dict[str, Any], actors: dict[str, dict[str, Any]], *,
                        targeted_actor: str | None, new_deaths_per_kill: float, old_deaths_per_kill: float,
                        new_non_clears: int) -> tuple[str, list[str]]:
    """keep only if party or the targeted actor improved, nothing regressed, deaths did not rise."""
    if party["verdict"] == "insufficient_kills":
        return "insufficient_kills", [f"need >= {MIN_KILLS} native-clear kills per label"]
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
        reasons.append(f"route deaths per kill rose {old_deaths_per_kill:.2f} -> {new_deaths_per_kill:.2f}")
    if new_non_clears:
        reasons.append(f"{new_non_clears} kill(s) of the candidate label did not clear natively")
    return ("revert" if reasons else "keep"), reasons


def _num(value: float | None, width: int = 7, digits: int = 0) -> str:
    return f"{value:{width}.{digits}f}" if value is not None else f"{'-':>{width}}"


def _signed(value: float | None, width: int = 7) -> str:
    return f"{value:+{width}.0f}" if value is not None else f"{'-':>{width}}"


def _mean_of(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return mean_sd(values)[0]


def _deaths_per_kill(kills: list[dict[str, Any]]) -> float:
    return sum(int(record.get("route_deaths") or 0) for record in kills) / len(kills) if kills else 0.0


def _gap_line(rank: int, gap: dict[str, Any]) -> str:
    line = (f"  {rank}. {gap['actor_id']} {gap['name']} {gap['spec']}: {gap['dps']:.0f} vs WCL "
            f"{gap['target_dps']:.0f} (-{gap['gap_dps']:.0f} DPS)")
    owner = gap.get("largest_owner_gap")
    if owner:
        line += (f"; largest owner damage gap {owner['gap_sec']:.1f}s at {owner['from_t']:.1f}s "
                 f"({owner['from_ability']} -> {owner['to_ability']})")
    if gap.get("wcl_casts_per_minute") is not None:
        line += f"; casts/min {gap.get('casts_per_minute')} vs WCL {gap['wcl_casts_per_minute']}"
    if gap.get("wcl_only_abilities"):
        line += f"; WCL-only: {', '.join(gap['wcl_only_abilities'])}"
    return line


def render(root: Path, scenario: str, label: str | None = None, vs: str | None = None,
           targeted_actor: str | None = None) -> str:
    target = load_target(root, scenario)
    records = load_records(root, scenario)
    label = label or latest_label(records)
    verdict = evaluate_target(root, scenario, label)
    kills = label_kills(records, label)
    clears = clear_kills(kills)
    rows = actor_rows(clears)
    old_kills = label_kills(records, vs) if vs else []
    old_clears = clear_kills(old_kills)
    old_rows = actor_rows(old_clears)
    healers = set(target.get("roles_without_dps_target", ["healer"]))
    min_kills = int((target.get("noise_rule") or {}).get("min_kills_per_label", MIN_KILLS))

    out = [f"scoreboard {scenario} label={label} kills={len(kills)} clears={len(clears)}"
           + (f"  vs {vs} kills={len(old_kills)} clears={len(old_clears)}" if vs else ""),
           f"target: actor DPS >= {target['actor_dps_ratio']} x median WCL of {', '.join(target['matched_reference_ids'])}; "
           f"{target['kills_per_measurement']} kills per measurement; max {target['max_boss_window_deaths']} boss-window deaths"]
    header = (f"{'actor':6} {'name':9} {'spec':19} {'role':6} {'n':>2} {'mean DPS':>8} {'± sd':>6} {'WCL':>7} "
              f"{'ratio':>5} {'status':18} {'active':>6} {'casts/m':>7}")
    if vs:
        header += f" | {'n':>2} {vs[:8]:>8} {'delta':>7} {'noise':>7} verdict"
    out += [header, "-" * len(header)]

    compared: dict[str, dict[str, Any]] = {}
    for actor_id, actor in verdict["actors"].items():
        series = rows[actor_id]
        uptime = _mean_of(series, "damage_uptime")
        line = (f"{actor_id:6} {str(actor['name'])[:9]:9} {actor['spec'][:19]:19} {actor['role'][:6]:6} {actor['n']:>2} "
                f"{_num(actor['mean_dps'], 8)} {_num(actor['sd_dps'], 6)} {_num(actor['target_dps'])} "
                f"{_num(actor['ratio'], 5, 2)} {actor['status']:18} "
                f"{_num(uptime * 100 if uptime is not None else None, 5)}% {_num(_mean_of(series, 'casts_per_minute'), 7, 1)}")
        if vs:
            old = old_rows.get(actor_id, [])
            change = noise_verdict([float(r["encounter_window_dps"]) for r in series],
                                   [float(r["encounter_window_dps"]) for r in old], min_kills)
            change["gating"] = actor["role"] not in healers
            compared[actor_id] = change
            line += (f" | {len(old):>2} {_num(mean_sd([float(r['encounter_window_dps']) for r in old])[0], 8)} "
                     f"{_signed(change['delta'])} {_num(change['threshold'])} {change['verdict']}"
                     + ("" if change["gating"] else " (healer, not gating)"))
        out.append(line)

    encounter = verdict["encounter"]
    party_new = [float(r["encounter"]["encounter_window_party_dps"]) for r in clears]
    mean, sd = mean_sd(party_new)
    party_line = (f"{'party':6} {'':9} {'':19} {'':6} {len(party_new):>2} {_num(mean, 8)} {_num(sd, 6)} "
                  f"{_num(encounter['party_wcl_dps'])} {_num(encounter['party_ratio'], 5, 2)} "
                  f"{'encounter ' + encounter['status']:18} {'':>6}  {'':>7}")
    party = None
    if vs:
        party_old = [float(r["encounter"]["encounter_window_party_dps"]) for r in old_clears]
        party = noise_verdict(party_new, party_old, min_kills)
        party_line += (f" | {len(party_old):>2} {_num(mean_sd(party_old)[0], 8)} {_signed(party['delta'])} "
                       f"{_num(party['threshold'])} {party['verdict']}")
    out += ["-" * len(header), party_line, ""]

    duration, duration_sd = mean_sd([float(r["encounter"]["duration_sec"]) for r in clears])
    kill_time = f"kill time: {_num(duration, 1, 1)} ± {_num(duration_sd, 1, 1)} s"
    deaths = (f"deaths per kill: route {_deaths_per_kill(kills):.2f}, "
              f"boss window {encounter['boss_window_deaths'] if encounter['boss_window_deaths'] is not None else 'unknown'} total")
    if vs:
        old_duration = mean_sd([float(r["encounter"]["duration_sec"]) for r in old_clears])[0]
        old_window = [r.get("boss_window_deaths") for r in old_kills]
        kill_time += f" ({vs}: {_num(old_duration, 1, 1)} s)"
        deaths += (f" ({vs}: route {_deaths_per_kill(old_kills):.2f}, boss window "
                   f"{'unknown' if None in old_window else sum(old_window)} total)")
    out += [kill_time, deaths, f"verdict: {verdict['status']}" + (f" - {verdict['reason']}" if verdict["reason"] else "")]
    if vs:
        decision, reasons = keep_recommendation(
            party, compared, targeted_actor=targeted_actor,
            new_deaths_per_kill=_deaths_per_kill(kills), old_deaths_per_kill=_deaths_per_kill(old_kills),
            new_non_clears=len(kills) - len(clears))
        out.append(f"keep/revert: {decision}" + (f" - {'; '.join(reasons)}" if reasons else ""))
    if kills:
        latest = kills[-1]
        gaps = latest.get("ranked_gaps") or []
        out.append(f"top gaps, latest kill {Path(str(latest.get('run_dir'))).name}:" + ("" if gaps else " none recorded"))
        out += [_gap_line(rank, gap) for rank, gap in enumerate(gaps, start=1)]
    return "\n".join(out)
