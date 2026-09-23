"""Plain-text scoreboard table with the Welch comparison and keep/revert advice."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.raid_program.scoreboard_compare import batch_shortfall, compare_labels
from tools.raid_program.scoreboard_core import (
    actor_rows, clear_kills, detectable_delta, exclusion_reason, kills_per_batch, label_kills, latest_label,
    load_baseline, load_records, load_target, mean_sd,
)

RNG_PRIMARY_SIDE = {"massive_crash": "raid_wide"}  # side whose share is compared between labels
BASIS_TAG = {"wcl": "WCL", "wowsims_fallback": "WoWS", "none": "-"}  # reference_basis next to the target
MECHANISM_REMINDER = ("keep also requires the change's mechanism to be visible in the candidate kills "
                      "(ranked gaps, evidence_view); this tool cannot check that")
DETECT_LEGEND = ("det95 = detectable delta (95%, these n) = t95 x sqrt(sd1^2/n1 + sd2^2/n2): a smaller |delta| "
                 "cannot be told from noise with these kill counts")
from tools.raid_program.scoreboard_verdict import evaluate_target


def _num(value: float | None, width: int = 7, digits: int = 0) -> str:
    return f"{value:{width}.{digits}f}" if value is not None else f"{'-':>{width}}"


def _signed(value: float | None, width: int = 7) -> str:
    return f"{value:+{width}.0f}" if value is not None else f"{'-':>{width}}"


def _mean_of(rows: list[dict[str, Any]], key: str) -> float | None:
    return mean_sd([float(row[key]) for row in rows if row.get(key) is not None])[0]


def _change(change: dict[str, Any], detect: float | None = None) -> str:
    return (f" | {change['old_n']:>2} {_num(change['old_mean'], 8)} {_signed(change['delta'])} "
            f"{_num(change['t'], 6, 2)} {_num(change['df'], 5, 1)} {_num(change['critical_t'], 5, 2)} "
            f"{_num(detect)} {change['verdict']}")


def _keep_lines(keep: dict[str, Any]) -> list[str]:
    """The keep_decision of compare_labels: decision, override, reasons, one line per condition, reminder."""
    override = keep.get("min_kills_override")
    line = f"keep/revert: {keep['decision']}"
    if override is not None:
        line += f" [--min-kills {override} overrides kills_per_batch {keep['target_kills_per_batch']}]"
    lines = [line + (f" - {'; '.join(keep['reasons'])}" if keep["reasons"] else "")]
    lines += [f"  ({c['condition']}) {'ok' if c['ok'] else 'FAIL' if c['ok'] is False else 'n/a':4} {c['text']}"
              for c in keep["conditions"]]
    return lines + [MECHANISM_REMINDER]


def _kill_table(label: str | None, kills: list[dict[str, Any]]) -> list[str]:
    """One line per kill: counted or why not, boss-window stall share and damage reconciliation."""
    lines = [f"kills of {label}:",
             f"  {'kill_id':58} {'counted':27} {'stall%':>6} {'max stall':>9} {'recon mismatch':>14} {'unlogged HP':>11}"]
    for record in kills:
        reason = exclusion_reason(record)
        validity = record.get("measurement_validity") or {}
        recon = record.get("damage_reconciliation") or {}
        fraction = validity.get("stall_fraction")
        lines.append(f"  {record['kill_id']:58} {'yes' if reason is None else 'no: ' + reason:27} "
                     f"{_num(fraction * 100 if fraction is not None else None, 6, 2)} "
                     f"{_num(validity.get('max_stall_sec'), 8, 1)}{'s' if validity.get('max_stall_sec') is not None else ' '} "
                     f"{_num(recon.get('mismatch_count'), 14)} {_num(recon.get('unlogged_health_loss'), 11)}")
    return lines


def _fidelity_line(kills: list[dict[str, Any]]) -> str:
    """Creature damage fidelity of the label's kills. Informational: counting and the verdict ignore it."""
    rows = [record["encounter_fidelity"] for record in kills if isinstance(record.get("encounter_fidelity"), dict)]
    if not rows:
        return "encounter fidelity (informational): not recorded"
    states = [row.get("blizzlike") for row in rows]
    parts = [f"blizzlike true {states.count(True)}, false {states.count(False)}, unknown {states.count(None)} "
             f"of {len(kills)} kills"]
    bosses: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for entry, boss in (row.get("bosses") or {}).items():
            bosses.setdefault(entry, []).append(boss)
    for entry, series in sorted(bosses.items()):
        mean = _mean_of(series, "after_attacker_mean")
        if mean is None:
            continue
        ratio = _mean_of(series, "mean_ratio")
        reference = next((boss for boss in reversed(series) if boss.get("wcl_mean")), None)
        text = f"{series[-1].get('name') or entry} after-attacker mean {mean:.0f}"
        if ratio is not None and reference is not None:
            text += (f" = {ratio:.2f}x WCL {reference['wcl_mean']:.0f}"
                     + (" (envelope midpoint)" if reference.get("wcl_mean_basis") == "wcl_envelope_midpoint" else ""))
        parts.append(text)
    reason = next((row["reasons"][0] for row in reversed(rows) if row.get("reasons")), None)
    if reason:
        parts.append(reason)
    return "encounter fidelity (informational): " + "; ".join(parts)


def rng_mix(kills: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Side counts per random event over the counted clears (the kills actor means use) and over all kills."""
    mix: dict[str, dict[str, Any]] = {}
    for scope, rows in (("counted", clear_kills(kills)), ("all", kills)):
        for record in rows:
            rng = record.get("encounter_rng")
            if not isinstance(rng, dict):
                continue
            for name, events in rng.items():
                if not isinstance(events, list):
                    continue
                entry = mix.setdefault(name, {"counted": {}, "all": {}, "no_event_kills": 0})
                for event in events:
                    side = str(event.get("side") or "unknown")
                    entry[scope][side] = entry[scope].get(side, 0) + 1
                if scope == "all" and not events:
                    entry["no_event_kills"] += 1
    return mix


def _share(counts: dict[str, int], side: str) -> tuple[int, int]:
    return counts.get(side, 0), sum(value for key, value in counts.items() if key != "unknown")


def _rng_line(label: str | None, kills: list[dict[str, Any]], mix: dict[str, dict[str, Any]]) -> str:
    """Informational: the side mix of each random event; counting and the verdict ignore it."""
    missing = sum(1 for record in kills if not isinstance(record.get("encounter_rng"), dict))
    parts = []
    for name, entry in sorted(mix.items()):
        side = RNG_PRIMARY_SIDE.get(name, "raid_wide")
        hits, known = _share(entry["counted"], side)
        all_hits, all_known = _share(entry["all"], side)
        text = f"{name} {side} {hits}/{known} counted (all kills {all_hits}/{all_known})"
        unknown = entry["all"].get("unknown", 0)
        if unknown:
            text += f", unknown side {unknown}"
        if entry["no_event_kills"]:
            text += f", no event in {entry['no_event_kills']} kill(s)"
        parts.append(text)
    if missing:
        parts.append(f"not recorded for {missing} of {len(kills)} kills (scoreboard rng-backfill)")
    return f"encounter RNG (informational) {label}: " + ("; ".join(parts) if parts else "none recorded")


def rng_mix_warnings(new: dict[str, dict[str, Any]], old: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    """Events whose counted side shares differ by more than one kill between labels.

    The gap is |share_new - share_old| x the smaller label's count: 4/4 vs 2/5 is 0.6 x 4 = 2.4 kills.
    """
    warnings = []
    for name in sorted(set(new) & set(old)):
        side = RNG_PRIMARY_SIDE.get(name, "raid_wide")
        (a, n), (b, m) = _share(new[name]["counted"], side), _share(old[name]["counted"], side)
        if n and m and abs(a / n - b / m) * min(n, m) > 1.0:
            warnings.append((name, f"RNG mix differs: {name} {side} {a}/{n} vs {b}/{m}, interpret actor deltas with care"))
    return warnings


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
           targeted_actor: str | None = None, batch_kills: int | None = None) -> str:
    """The scoreboard table; with a comparison label (--vs, else the baseline) the keep/revert decision.

    batch_kills (show --min-kills) overrides kills_per_batch for the keep decision only.
    """
    target = load_target(root, scenario)
    records = load_records(root, scenario)
    label = label or latest_label(records)
    baseline = (load_baseline(root, scenario) or {}).get("label")
    auto_vs = vs is None and baseline is not None and label != baseline
    vs = baseline if auto_vs else vs
    verdict = evaluate_target(root, scenario, label)
    kills = label_kills(records, label)
    rows = actor_rows(clear_kills(kills))
    comparison = compare_labels(root, scenario, label, vs, targeted_actor, batch_kills) if vs else None
    old_kills = label_kills(records, vs) if vs else []
    old_rows = actor_rows(clear_kills(old_kills))
    encounter = verdict["encounter"]

    fallback = target.get("fallback_reference") or {}
    out = [f"scoreboard {scenario} label={label} baseline={baseline or 'unset'} counted={verdict['kills']} of "
           f"{len(kills)} clears={encounter['clears']}" + (f"  vs {vs}" if vs else "")
           + (" (the baseline; pass --vs to override)" if auto_vs else ""),
           f"target: actor DPS >= {target['actor_dps_ratio']} x median WCL of {', '.join(target['matched_reference_ids'])}"
           + (f" (no WCL: >= {fallback['ratio']} x WoWSims)" if fallback else "") + "; "
           f"{target['kills_per_measurement']} kills per measurement; max {target['max_boss_window_deaths']} boss-window deaths"]
    header = (f"{'actor':6} {'name':9} {'spec':19} {'role':6} {'n':>2} {'mean DPS':>8} {'± sd':>6} {'target':>7} {'ref':4} "
              f"{'ratio':>5} {'status':18} {'active':>6} {'casts/m':>7}")
    if vs:
        header += f" | {'n':>2} {vs[:8]:>8} {'delta':>7} {'t':>6} {'df':>5} {'t95':>5} {'det95':>7} verdict"
    out += [header, "-" * len(header)]
    for actor_id, actor in verdict["actors"].items():
        series = rows.get(actor_id, [])
        uptime = _mean_of(series, "damage_uptime")
        line = (f"{actor_id:6} {str(actor['name'])[:9]:9} {actor['spec'][:19]:19} {actor['role'][:6]:6} {actor['n']:>2} "
                f"{_num(actor['mean_dps'], 8)} {_num(actor['sd_dps'], 6)} {_num(actor['target_dps'])} "
                f"{BASIS_TAG.get(actor.get('reference_basis'), '-'):4} "
                f"{_num(actor['ratio'], 5, 2)} {actor['status']:18} "
                f"{_num(uptime * 100 if uptime is not None else None, 5)}% {_num(_mean_of(series, 'casts_per_minute'), 7, 1)}")
        if comparison:
            change = comparison["actors"][actor_id]
            detect = detectable_delta(change["critical_t"], [float(row["encounter_window_dps"]) for row in series],
                                      [float(row["encounter_window_dps"]) for row in old_rows.get(actor_id, [])])
            line += (_change(change, detect) if change["gating"] else _change(change) + " (healer, not gating)")
        out.append(line)

    party_values = [float(r["encounter"]["encounter_window_party_dps"]) for r in clear_kills(kills)]
    mean, sd = mean_sd(party_values)
    party_line = (f"{'party':6} {'':9} {'':19} {'':6} {len(party_values):>2} {_num(mean, 8)} {_num(sd, 6)} "
                  f"{_num(encounter['party_wcl_dps'])} {'WCL':4} {_num(encounter['party_ratio'], 5, 2)} "
                  f"{'encounter ' + encounter['status']:18} {'':>6}  {'':>7}")
    if comparison:
        old_party = [float(r["encounter"]["encounter_window_party_dps"]) for r in clear_kills(old_kills)]
        party_line += _change(comparison["party"], detectable_delta(comparison["party"]["critical_t"], party_values, old_party))
    out += ["-" * len(header), party_line] + ([DETECT_LEGEND] if comparison else []) + [""]

    duration, duration_sd = mean_sd([float(r["encounter"]["duration_sec"]) for r in clear_kills(kills)])
    kill_time = f"kill time: {_num(duration, 1, 1)} ± {_num(duration_sd, 1, 1)} s"
    window = encounter["boss_window_deaths"]
    deaths = (f"deaths per counted kill: route {encounter['route_deaths'] / verdict['kills'] if verdict['kills'] else 0:.2f}, "
              f"boss window {window if window is not None else 'unknown'} total")
    if comparison:
        kill_time += f" ({vs}: {_num(comparison['mean_duration_sec']['old'], 1, 1)} s)"
        deaths += f" ({vs}: route {comparison['route_deaths_per_kill']['old']:.2f})"
    out += [kill_time, deaths, ""]
    out += _kill_table(label, kills)
    if vs:
        out += _kill_table(vs, old_kills)
    out.append(_fidelity_line(kills))
    mix = rng_mix(kills)
    out.append(_rng_line(label, kills, mix))
    if vs:
        old_mix = rng_mix(old_kills)
        out.append(_rng_line(vs, old_kills, old_mix))
        out += [text for _, text in rng_mix_warnings(mix, old_mix)]
    out.append("")
    bases = [actor.get("reference_basis") for actor in verdict["actors"].values()
             if actor["role"] not in set(target.get("roles_without_dps_target", ["healer"]))]
    basis_text = ", ".join(f"{bases.count(key)} {text}" for key, text in (
        ("wcl", "WCL"), ("wowsims_fallback", "WoWSims fallback"), ("none", "no reference")) if bases.count(key))
    out.append(f"verdict: {verdict['status']}" + (f" [references: {basis_text}]" if basis_text else "")
               + (f" - {verdict['reason']}" if verdict["reason"] else ""))
    if comparison:
        keep = comparison["keep"]
        out += _keep_lines(keep)
        batch = kills_per_batch(target)
        for side, side_kills in ((label, kills), (vs, old_kills)):
            text = batch_shortfall(side, len(clear_kills(side_kills)), batch)
            if len(clear_kills(side_kills)) < batch and text not in keep["reasons"]:
                out.append("warning: " + text)
    if kills:
        latest = kills[-1]
        gaps = latest.get("ranked_gaps") or []
        out.append(f"top gaps, latest kill {latest['kill_id']}:" + ("" if gaps else " none recorded"))
        out += [_gap_line(rank, gap) for rank, gap in enumerate(gaps, start=1)]
    return "\n".join(out)
