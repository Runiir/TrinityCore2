"""Plain-text scoreboard table with the Welch comparison and keep/revert advice."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.raid_program.scoreboard_compare import compare_labels
from tools.raid_program.scoreboard_core import (
    actor_rows, clear_kills, label_kills, latest_label, load_records, load_target, mean_sd,
)
from tools.raid_program.scoreboard_verdict import evaluate_target


def _num(value: float | None, width: int = 7, digits: int = 0) -> str:
    return f"{value:{width}.{digits}f}" if value is not None else f"{'-':>{width}}"


def _signed(value: float | None, width: int = 7) -> str:
    return f"{value:+{width}.0f}" if value is not None else f"{'-':>{width}}"


def _mean_of(rows: list[dict[str, Any]], key: str) -> float | None:
    return mean_sd([float(row[key]) for row in rows if row.get(key) is not None])[0]


def _change(change: dict[str, Any]) -> str:
    return (f" | {change['old_n']:>2} {_num(change['old_mean'], 8)} {_signed(change['delta'])} "
            f"{_num(change['t'], 6, 2)} {_num(change['df'], 5, 1)} {_num(change['critical_t'], 5, 2)} {change['verdict']}")


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
    rows = actor_rows(clear_kills(kills))
    comparison = compare_labels(root, scenario, label, vs, targeted_actor) if vs else None
    encounter = verdict["encounter"]

    out = [f"scoreboard {scenario} label={label} counted={verdict['kills']} of {len(kills)} clears={encounter['clears']}"
           + (f"  vs {vs}" if vs else ""),
           f"target: actor DPS >= {target['actor_dps_ratio']} x median WCL of {', '.join(target['matched_reference_ids'])}; "
           f"{target['kills_per_measurement']} kills per measurement; max {target['max_boss_window_deaths']} boss-window deaths"]
    header = (f"{'actor':6} {'name':9} {'spec':19} {'role':6} {'n':>2} {'mean DPS':>8} {'± sd':>6} {'WCL':>7} "
              f"{'ratio':>5} {'status':18} {'active':>6} {'casts/m':>7}")
    if vs:
        header += f" | {'n':>2} {vs[:8]:>8} {'delta':>7} {'t':>6} {'df':>5} {'t95':>5} verdict"
    out += [header, "-" * len(header)]
    for actor_id, actor in verdict["actors"].items():
        series = rows.get(actor_id, [])
        uptime = _mean_of(series, "damage_uptime")
        line = (f"{actor_id:6} {str(actor['name'])[:9]:9} {actor['spec'][:19]:19} {actor['role'][:6]:6} {actor['n']:>2} "
                f"{_num(actor['mean_dps'], 8)} {_num(actor['sd_dps'], 6)} {_num(actor['target_dps'])} "
                f"{_num(actor['ratio'], 5, 2)} {actor['status']:18} "
                f"{_num(uptime * 100 if uptime is not None else None, 5)}% {_num(_mean_of(series, 'casts_per_minute'), 7, 1)}")
        if comparison:
            change = comparison["actors"][actor_id]
            line += _change(change) + ("" if change["gating"] else " (healer, not gating)")
        out.append(line)

    party_values = [float(r["encounter"]["encounter_window_party_dps"]) for r in clear_kills(kills)]
    mean, sd = mean_sd(party_values)
    party_line = (f"{'party':6} {'':9} {'':19} {'':6} {len(party_values):>2} {_num(mean, 8)} {_num(sd, 6)} "
                  f"{_num(encounter['party_wcl_dps'])} {_num(encounter['party_ratio'], 5, 2)} "
                  f"{'encounter ' + encounter['status']:18} {'':>6}  {'':>7}")
    if comparison:
        party_line += _change(comparison["party"])
    out += ["-" * len(header), party_line, ""]

    duration, duration_sd = mean_sd([float(r["encounter"]["duration_sec"]) for r in clear_kills(kills)])
    kill_time = f"kill time: {_num(duration, 1, 1)} ± {_num(duration_sd, 1, 1)} s"
    window = encounter["boss_window_deaths"]
    deaths = (f"deaths per counted kill: route {encounter['route_deaths'] / verdict['kills'] if verdict['kills'] else 0:.2f}, "
              f"boss window {window if window is not None else 'unknown'} total")
    if comparison:
        kill_time += f" ({vs}: {_num(comparison['mean_duration_sec']['old'], 1, 1)} s)"
        deaths += f" ({vs}: route {comparison['route_deaths_per_kill']['old']:.2f})"
    out += [kill_time, deaths]
    excluded = [row for row in verdict["kills_detail"] if not row["counted"]]
    if excluded:
        out.append("not counted: " + ", ".join(f"{row['kill_id']} ({row['exclusion_reason']})" for row in excluded))
    out.append(f"verdict: {verdict['status']}" + (f" - {verdict['reason']}" if verdict["reason"] else ""))
    if comparison:
        keep = comparison["keep"]
        out.append(f"keep/revert (two-sided 95% Welch t): {keep['decision']}"
                   + (f" - {'; '.join(keep['reasons'])}" if keep["reasons"] else ""))
    if kills:
        latest = kills[-1]
        gaps = latest.get("ranked_gaps") or []
        out.append(f"top gaps, latest kill {latest['kill_id']}:" + ("" if gaps else " none recorded"))
        out += [_gap_line(rank, gap) for rank, gap in enumerate(gaps, start=1)]
    return "\n".join(out)
