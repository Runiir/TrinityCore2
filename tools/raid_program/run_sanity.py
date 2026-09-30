"""Run-sanity findings: results a careful coordinator used to reject by eye (hand-off hardening).

``sanity_findings(root, scenario, label)`` is a pure function over the label's stored scoreboard
records, the scenario's raid target with its matched WCL references, and the creature damage
calibration registry. It never changes a verdict: ``program assess`` (raid_program_sanity) refuses a
unit with any ``blocking`` finding even when ``evaluate_target`` passes, and lists every finding as
"investigate before tuning". Each finding is::

    {"check": str, "severity": "blocking" | "warn", "kill_id": str | None, "detail": str, "evidence": dict}

A check that needs a field an older counted record lacks reports ``not_evaluable`` instead of
guessing: one ``warn`` finding per check and reason, with ``evidence.status == "not_evaluable"`` and
the kill ids.
New records carry those fields in ``sanity_inputs`` (tools/raid_program/run_sanity_inputs.py).

Checks (thresholds are the module constants):

duration_outlier (blocking)
    The boss window is longer than DURATION_OUTLIER_RATIO x the longest matched WCL reference fight
    (BWD 10N round 1: an 18-minute Nefarian kill against 4-6 minute references).
enrage_reached (blocking)
    A pull ran past a scripted enrage (registry ``enrage_after_ms``). Needs the record's per-pull
    timing; an older record whose whole window exceeds the enrage is not evaluable (a single pull past
    Berserk and several pulls in one window look alike there), and one whose window is shorter passes.
death_signal_conflict (blocking)
    The record's conflict flag; or lethal combat-log hits while the native death signal saw no death;
    or 0 boss-window deaths recorded from route_deaths == 0 while the lethal scan found hits in the
    window (round 2: route_deaths 0-2 against 1,045-1,207 native deaths).
repeated_deaths (blocking)
    One actor took REPEATED_DEATHS_PER_ACTOR or more lethal hits inside one boss window: bots revived
    in place and kept dying (round 1 Nefarian: 1,103 lethal hits in one kill).
health_pinned_half (blocking)
    More than HALF_HEALTH_SHARE of the hits bots took in the boss window (at least HALF_HEALTH_MIN_HITS)
    found them at exactly half their maximum health (+-1 hp): the round-2 Nefarian root cause, bots
    repopped at their homebind every tick and revived at 50% (93-95% of hits). Needs
    sanity_inputs.health_half.
instant_revive (blocking)
    A bot that died in the boss window was resurrected within INSTANT_REVIVE_MS: a measured native life
    edge pair (not one the producer inferred) or a combat-log lethal hit followed that fast by a hit that
    found the bot alive. Deaths outside the boss window never count (recovered trash deaths are fine).
    Needs sanity_inputs.revives.
idle_actor (blocking)
    A non-healer actor outside dps_gate_exempt_specs below IDLE_DPS_RATIO of its reference DPS (the
    verdict's target_dps), or with damage uptime below IDLE_UPTIME (stranded or stuck bots).
boss_melee_fidelity (warn)
    A calibrated creature's after-attacker melee mean is outside +-MELEE_TOLERANCE of the WCL mean over
    at least MELEE_MIN_SWINGS swings, or the harness judged the encounter not Blizzlike.
unmeasured_kills (warn)
    A kill was excluded as unmeasured (no combat log, e.g. the 16 MB capture cap), or a counted kill's
    capture was truncated or its combat-log ring no longer covers the boss window.
excluded_kills (warn)
    A kill was excluded as stalled, voided, interrupted, an infrastructure failure, without evidence,
    with a post-processing error or with an unscoped DPS; a stall label with no recorded stall time is
    called out as a possible mislabel.

A blocking check on a kill the verdict does not count is reported as ``warn`` (its numbers are not
comparable); human play-mode kills are never checked. Command line::

    python -m tools.raid_program.run_sanity SCENARIO [SCENARIO ...] --label LABEL [--json]

exits 1 when any finding is blocking.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tools.raid_program.play_mode_guard import find_play_markers
from tools.raid_program.run_sanity_inputs import enrage_rows
from tools.raid_program.scoreboard_core import (
    ROOT, dps_gate_exempt_specs, healer_roles, is_dps_gate_exempt, label_kills, load_records, load_target,
    native_excluded_entries, reference_targets, roster, target_for_records,
)
from tools.raid_program.scoreboard_deaths import ENCOUNTER_RECONCILED_BASIS
# The verdict's own counting decision, so "counted" here always means counted by evaluate_target.
from tools.raid_program.scoreboard_verdict import _eligibility

REGISTRY_PATH = "experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json"
DURATION_OUTLIER_RATIO = 2.0
IDLE_DPS_RATIO = 0.25
IDLE_UPTIME = 0.20
MELEE_TOLERANCE = 0.10
MELEE_MIN_SWINGS = 10
REPEATED_DEATHS_PER_ACTOR = 4
HALF_HEALTH_SHARE = 0.20
HALF_HEALTH_MIN_HITS = 20
INSTANT_REVIVE_MS = 250
EVIDENCE_BUDGET = 1800  # program assess keeps evidence up to 2,000 JSON bytes
NOT_EVALUABLE = "not_evaluable"
UNMEASURED_REASONS = frozenset({"unmeasured_boss_window", "no_measurement_validity"})
EXCLUDED_REASONS = frozenset({"stalled_boss_window", "voided", "interrupted", "infrastructure_failure",
                              "no_evidence", "postprocess_error", "enemy_scope_mismatch"})
LOG_DEATH_BASES = frozenset({"combat_log_lethal_damage", "combat_log_lethal_damage_unreconciled",
                             ENCOUNTER_RECONCILED_BASIS})
CHECK_ORDER = ("duration_outlier", "enrage_reached", "death_signal_conflict", "repeated_deaths", "health_pinned_half",
               "instant_revive", "idle_actor", "boss_melee_fidelity", "unmeasured_kills", "excluded_kills")


def _fit(evidence: dict[str, Any], budget: int = EVIDENCE_BUDGET) -> dict[str, Any]:
    """Trim list values (longest first) until the evidence fits the assess budget."""
    evidence = dict(evidence)
    while len(json.dumps(evidence, sort_keys=True, default=str)) > budget:
        lists = [key for key, value in evidence.items() if isinstance(value, list) and len(value) > 1]
        if not lists:
            break
        key = max(lists, key=lambda name: len(json.dumps(evidence[name], default=str)))
        keep = len(evidence[key]) // 2
        evidence[f"{key}_omitted"] = int(evidence.get(f"{key}_omitted") or 0) + len(evidence[key]) - keep
        evidence[key] = evidence[key][:keep]
    return evidence


def _finding(check: str, severity: str, kill_id: str | None, detail: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"check": check, "severity": severity, "kill_id": kill_id, "detail": detail, "evidence": _fit(evidence)}


def _round(value: Any, digits: int = 3) -> float | None:
    return None if value is None else round(float(value), digits)


class _Label:
    """The label's kills, the target as it judges them, and the lookups every check shares."""

    def __init__(self, root: Path, scenario: str, label: str) -> None:
        self.root, self.scenario, self.label = Path(root), scenario, label
        records = load_records(self.root, scenario)
        self.kills = [record for record in label_kills(records, label) if not find_play_markers(record)]
        self.target = target_for_records(self.root, load_target(self.root, scenario), self.kills)
        self.excluded_entries = native_excluded_entries(self.target)
        self.healers = healer_roles(self.target)
        self.exempt = dps_gate_exempt_specs(self.target)
        self.roster = roster(self.target)
        self.reference_error = None
        try:
            self.references = reference_targets(self.root, self.target)
        except ValueError as error:  # a contradictory target: the verdict refuses too; uptime still judged
            self.references, self.reference_error = {}, str(error)
        self.registry = self._registry()
        self.not_evaluable: dict[tuple[str, str], list[str]] = {}
        self._longest: tuple[str | None, float | None] | None = None

    def _registry(self) -> dict[str, Any]:
        path = self.root / REGISTRY_PATH
        return json.loads(path.read_text()) if path.is_file() else {"creatures": {}}

    def eligibility(self, record: dict[str, Any]) -> str | None:
        return _eligibility(record, self.excluded_entries)

    def severity(self, record: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        """blocking for a counted kill; warn (with the exclusion) for a kill the verdict does not count."""
        reason = self.eligibility(record)
        if reason is None:
            return "blocking", "", {}
        return "warn", f" (kill not counted: {reason})", {"counted": False, "exclusion_reason": reason}

    def unevaluable(self, check: str, why: str, record: dict[str, Any]) -> None:
        """Note a check the record cannot answer; only counted kills matter (the rest never reach a verdict)."""
        if self.eligibility(record) is None:
            self.not_evaluable.setdefault((check, why), []).append(str(record.get("kill_id")))

    def longest_reference(self) -> tuple[str | None, float | None]:
        """(reference id, duration_sec) of the longest matched WCL reference fight."""
        if self._longest is None:
            manifest = json.loads((self.root / self.target["wcl_reference_manifest"]).read_text())
            wanted = set(self.target.get("matched_reference_ids") or [])
            durations = [(float(ref["duration_sec"]), ref["id"]) for ref in manifest.get("references") or []
                         if ref.get("id") in wanted and isinstance(ref.get("duration_sec"), (int, float))]
            self._longest = (max(durations)[1], max(durations)[0]) if durations else (None, None)
        return self._longest


# --- per-kill facts -----------------------------------------------------------------------------------

def _window_sec(record: dict[str, Any]) -> float | None:
    encounter = record.get("encounter")
    if isinstance(encounter, dict) and isinstance(encounter.get("duration_sec"), (int, float)):
        return float(encounter["duration_sec"])
    return None


def _lethal(record: dict[str, Any]) -> dict[str, Any] | None:
    """Lethal-hit counts of one kill, or None when they were never scanned (route_deaths == 0 shortcut)."""
    scan = (record.get("sanity_inputs") or {}).get("deaths")
    if isinstance(scan, dict) and scan.get("lethal_events") is not None:
        return {"source": "sanity_inputs", "total": int(scan["lethal_events"]),
                "window": int(scan.get("lethal_events_in_boss_window") or 0),
                "by_actor": dict(scan.get("lethal_events_in_boss_window_by_actor") or {}),
                "native": scan.get("native_death_signal") or record.get("native_death_signal"),
                "conflict": scan.get("death_signal_conflict")}
    if record.get("death_basis") not in LOG_DEATH_BASES:
        return None
    by_actor: dict[str, int] = {}
    for death in record.get("deaths") or []:
        if death.get("in_boss_window"):
            by_actor[str(death.get("actor_id"))] = by_actor.get(str(death.get("actor_id")), 0) + 1
    return {"source": "record", "total": len(record.get("deaths") or []), "window": sum(by_actor.values()),
            "by_actor": by_actor, "native": record.get("native_death_signal"),
            "conflict": record.get("death_signal_conflict")}


def _unscanned(record: dict[str, Any]) -> str:
    """Why a record has no lethal-hit counts."""
    if record.get("death_basis") == "no_route_deaths":
        return ("route_deaths was 0, so the record never scanned the combat log for lethal hits "
                "(records before sanity_inputs.deaths)")
    return f"the record has no lethal-hit scan (death_basis {record.get('death_basis')})"


# --- checks -------------------------------------------------------------------------------------------

def check_duration(ctx: _Label, record: dict[str, Any], out: list) -> None:
    window = _window_sec(record)
    if window is None:
        return
    ref_id, longest = ctx.longest_reference()
    if longest is None:
        ctx.unevaluable("duration_outlier", "the target's matched WCL references record no duration_sec", record)
        return
    limit = DURATION_OUTLIER_RATIO * longest
    if window > limit:
        severity, note, extra = ctx.severity(record)
        out.append(_finding("duration_outlier", severity, record["kill_id"],
                            f"boss window {window:.0f} s is {window / longest:.1f}x the longest matched WCL kill "
                            f"({longest:.0f} s, {ref_id}); limit {DURATION_OUTLIER_RATIO:g}x = {limit:.0f} s{note}",
                            {"window_sec": window, "longest_reference_sec": longest, "reference_id": ref_id,
                             "ratio": _round(window / longest), "limit_ratio": DURATION_OUTLIER_RATIO, **extra}))


def check_enrage(ctx: _Label, record: dict[str, Any], out: list) -> None:
    window = _window_sec(record)
    if window is None:
        return
    seen = {int(key) for key in ((record.get("encounter_fidelity") or {}).get("bosses") or {}) if str(key).isdigit()}
    inputs = record.get("sanity_inputs") or {}
    pulls = inputs.get("enrage_pulls") if isinstance(inputs.get("enrage_pulls"), dict) else None
    for entry, row in sorted(enrage_rows(ctx.registry, ctx.scenario, seen).items()):
        enrage_sec = float(row["enrage_after_ms"]) / 1000.0
        name = row.get("name") or str(entry)
        measured = (pulls or {}).get(str(entry))
        if isinstance(measured, dict) and measured.get("longest_engaged_sec") is not None:
            longest = float(measured["longest_engaged_sec"])
            if longest > enrage_sec:
                severity, note, extra = ctx.severity(record)
                out.append(_finding("enrage_reached", severity, record["kill_id"],
                                    f"{name} stayed engaged {longest:.0f} s in one pull, past its {enrage_sec:.0f} s "
                                    f"enrage ({measured.get('pulls')} pull(s) in the window){note}",
                                    {"entry": entry, "enrage_sec": enrage_sec, "longest_engaged_sec": longest,
                                     "engaged_sec": measured.get("engaged_sec"), "pulls": measured.get("pulls"),
                                     "post_enrage_anchor_events": measured.get("post_enrage_anchor_events"),
                                     "basis": "sanity_inputs.enrage_pulls", **extra}))
            elif (inputs.get("combat_log") or {}).get("boss_window_retained") is False and window > enrage_sec:
                ctx.unevaluable("enrage_reached", f"the combat-log ring dropped events inside the boss window, so "
                                f"{name}'s pulls (enrage {enrage_sec:.0f} s) are incomplete", record)
            continue
        if window > enrage_sec:
            ctx.unevaluable("enrage_reached", f"the boss window exceeds {name}'s {enrage_sec:.0f} s enrage but the "
                            "record predates per-pull timing (sanity_inputs.enrage_pulls): a pull past Berserk and "
                            "several pulls in one window look alike; duration_outlier judges the window", record)


def check_death_signal(ctx: _Label, record: dict[str, Any], out: list) -> None:
    if _window_sec(record) is None:
        return
    facts = _lethal(record)
    severity, note, extra = ctx.severity(record)
    native = (facts or {}).get("native") or record.get("native_death_signal")
    evidence = {"death_basis": record.get("death_basis"), "route_deaths": record.get("route_deaths"),
                "boss_window_deaths": record.get("boss_window_deaths"),
                "lethal_events": (facts or {}).get("total"), "lethal_events_in_boss_window": (facts or {}).get("window"),
                "native_deaths": (native or {}).get("deaths"), "native_resurrections": (native or {}).get("resurrections"),
                "source": (facts or {}).get("source"), **extra}
    if record.get("death_signal_conflict") is True or (facts and facts.get("conflict") is True) or (
            facts and native and int(native.get("deaths") or 0) == 0 and facts["total"] > 0):
        out.append(_finding("death_signal_conflict", severity, record["kill_id"],
                            f"{evidence['lethal_events']} lethal combat-log hits while the native death signal saw "
                            f"no death: bots died without the runtime recording it{note}", evidence))
        return
    if facts and facts["source"] == "sanity_inputs" and record.get("death_basis") == "no_route_deaths" and facts["window"]:
        out.append(_finding("death_signal_conflict", severity, record["kill_id"],
                            f"boss_window_deaths was recorded as 0 from route_deaths 0, but {facts['window']} lethal "
                            f"hits landed in the boss window (native deaths {evidence['native_deaths']}){note}",
                            evidence))
        return
    if facts is None:
        ctx.unevaluable("death_signal_conflict", _unscanned(record), record)
    elif native is None and record.get("death_basis") != "combat_log_lethal_damage":
        ctx.unevaluable("death_signal_conflict", "lethal hits disagree with the route death count and the record "
                        "has no native death signal", record)


def check_repeated_deaths(ctx: _Label, record: dict[str, Any], out: list) -> None:
    if _window_sec(record) is None:
        return
    facts = _lethal(record)
    if facts is None:
        ctx.unevaluable("repeated_deaths", _unscanned(record), record)
        return
    repeated = sorted(((count, actor) for actor, count in facts["by_actor"].items()
                       if count >= REPEATED_DEATHS_PER_ACTOR), reverse=True)
    if not repeated:
        return
    severity, note, extra = ctx.severity(record)
    native = facts.get("native") or {}
    names = {str(actor_id): row.get("name") for actor_id, row in ctx.roster.items()}
    out.append(_finding("repeated_deaths", severity, record["kill_id"],
                        f"{len(repeated)} actor(s) took {REPEATED_DEATHS_PER_ACTOR}+ lethal hits in one boss window "
                        f"(worst actor {repeated[0][0]} hits, {facts['window']} in total): bots were revived in place "
                        f"and kept dying{note}",
                        {"lethal_events_in_boss_window": facts["window"], "threshold_per_actor": REPEATED_DEATHS_PER_ACTOR,
                         "actors": [{"id": actor, "name": names.get(actor), "lethal": count} for count, actor in repeated],
                         "native_deaths": native.get("deaths"), "native_resurrections": native.get("resurrections"),
                         "source": facts["source"], **extra}))


def _inputs(record: dict[str, Any], key: str) -> Any:
    """A sanity_inputs block, or None for a record that predates it (or whose inputs failed)."""
    inputs = record.get("sanity_inputs")
    return inputs.get(key) if isinstance(inputs, dict) and key in inputs else None


def check_health_pinned(ctx: _Label, record: dict[str, Any], out: list) -> None:
    if _window_sec(record) is None:
        return
    half = _inputs(record, "health_half")
    if not isinstance(half, dict):
        ctx.unevaluable("health_pinned_half", "the record has no per-hit health of the bots "
                        "(records before sanity_inputs.health_half)", record)
        return
    hits, at_half = int(half.get("hits") or 0), int(half.get("at_half") or 0)
    if hits < HALF_HEALTH_MIN_HITS or at_half <= HALF_HEALTH_SHARE * hits:
        return
    severity, note, extra = ctx.severity(record)
    names = {str(actor_id): row.get("name") for actor_id, row in ctx.roster.items()}
    actors = sorted(((row.get("at_half", 0), actor, row.get("hits", 0)) for actor, row in
                     (half.get("by_actor") or {}).items() if row.get("at_half")), reverse=True)
    out.append(_finding("health_pinned_half", severity, record["kill_id"],
                        f"{at_half} of {hits} hits bots took in the boss window ({at_half / hits:.0%}) found them at "
                        f"exactly half health (limit {HALF_HEALTH_SHARE:.0%}): bots are being revived at 50% in "
                        f"place, e.g. a homebind repop every tick{note}",
                        {"hits": hits, "at_half": at_half, "fraction": _round(at_half / hits, 4),
                         "limit": HALF_HEALTH_SHARE, "tolerance_hp": half.get("tolerance_hp"),
                         "actors": [{"id": actor, "name": names.get(actor), "at_half": count, "hits": total}
                                    for count, actor, total in actors], **extra}))


def check_instant_revive(ctx: _Label, record: dict[str, Any], out: list) -> None:
    revive = _inputs(record, "revives")
    if not isinstance(revive, dict):
        if record.get("reached_encounter") is not False:
            ctx.unevaluable("instant_revive", "the record has no death-to-resurrection timing "
                            "(records before sanity_inputs.revives)", record)
        return
    names = {str(actor_id): row.get("name") for actor_id, row in ctx.roster.items()}
    fast: dict[str, dict[str, Any]] = {}
    legacy = False
    for row in revive.get("native") or []:  # only measured gaps of boss-window deaths (run_sanity_inputs)
        gap = row.get("gap_ms")
        if "measured" not in row or "in_boss_window" not in row:  # rows written before the attribution
            legacy = True
            continue
        if row.get("measured") is True and row.get("in_boss_window") is True and gap is not None \
                and 0 <= int(gap) <= INSTANT_REVIVE_MS:
            fast[str(row["actor_id"])] = {"id": str(row["actor_id"]), "name": names.get(str(row["actor_id"])),
                                          "native_gap_ms": gap, "deaths": row.get("deaths")}
    if legacy:
        ctx.unevaluable("instant_revive", "native_revive_unattributed_legacy_row: native revive rows without "
                        "measured/in_boss_window cannot be told apart from inferred or trash revives", record)
    for actor, gap in ((revive.get("combat_log") or {}).get("min_gap_ms_by_actor") or {}).items():
        if 0 <= int(gap) <= INSTANT_REVIVE_MS:
            fast.setdefault(actor, {"id": actor, "name": names.get(actor)})["combat_log_gap_ms"] = gap
    if not fast:
        return
    severity, note, extra = ctx.severity(record)
    def gap(row: dict[str, Any]) -> int:
        return min(row.get("native_gap_ms", 10**9), row.get("combat_log_gap_ms", 10**9))

    rows = sorted(fast.values(), key=gap)
    worst = gap(rows[0])
    out.append(_finding("instant_revive", severity, record["kill_id"],
                        f"{len(rows)} bot(s) were resurrected within {INSTANT_REVIVE_MS} ms of dying (fastest "
                        f"{worst} ms): no release, corpse run or resurrection spell takes that long{note}",
                        {"limit_ms": INSTANT_REVIVE_MS, "actors": rows, **extra}))


def check_idle(ctx: _Label, record: dict[str, Any], out: list) -> None:
    if _window_sec(record) is None:
        return
    idle = []
    for actor in record.get("actors") or []:
        actor_id = str(actor.get("actor_id"))
        known = ctx.roster.get(actor_id) or {}
        spec, role = known.get("spec") or actor.get("spec"), known.get("role") or actor.get("role")
        if role in ctx.healers or is_dps_gate_exempt(ctx.exempt, str(spec), str(role)):
            continue
        dps = float(actor.get("encounter_window_dps") or 0.0)
        reference = (ctx.references.get(str(spec)) or {}).get("dps")
        uptime = actor.get("damage_uptime")
        why = []
        if reference and dps < IDLE_DPS_RATIO * float(reference):
            why.append("dps")
        if isinstance(uptime, (int, float)) and uptime < IDLE_UPTIME:
            why.append("uptime")
        if why:
            idle.append({"id": actor_id, "spec": spec, "dps": _round(dps, 1),
                         "ref": _round(reference, 1), "ratio": _round(dps / float(reference)) if reference else None,
                         "uptime": _round(uptime), "why": "+".join(why)})
    if not idle:
        return
    severity, note, extra = ctx.severity(record)
    shown = ", ".join(f"{row['spec']} {row['ratio'] if row['ratio'] is not None else '-'}x/"
                      f"{row['uptime'] if row['uptime'] is not None else '-'} uptime" for row in idle[:4])
    evidence = {"dps_ratio_below": IDLE_DPS_RATIO, "uptime_below": IDLE_UPTIME, "actors": idle, **extra}
    if ctx.reference_error:
        evidence["reference_error"] = ctx.reference_error[:200]
    out.append(_finding("idle_actor", severity, record["kill_id"],
                        f"{len(idle)} actor(s) below {IDLE_DPS_RATIO:.0%} of reference DPS or {IDLE_UPTIME:.0%} damage "
                        f"uptime (stranded or stuck): {shown}{'...' if len(idle) > 4 else ''}{note}", evidence))


def check_melee(ctx: _Label, record: dict[str, Any], out: list) -> None:
    fidelity = record.get("encounter_fidelity")
    if not isinstance(fidelity, dict):
        return
    creatures = ctx.registry.get("creatures") or {}
    outside = []
    for entry, row in sorted((fidelity.get("bosses") or {}).items()):
        registered = creatures.get(str(entry)) or {}
        ratio, swings = row.get("mean_ratio"), int(row.get("swings") or 0)
        if registered.get("status") != "calibrated" or ratio is None or swings < MELEE_MIN_SWINGS:
            continue
        if abs(float(ratio) - 1.0) > MELEE_TOLERANCE:
            outside.append({"entry": str(entry), "name": row.get("name"), "mean_ratio": _round(ratio),
                            "swings": swings, "native_mean": row.get("after_attacker_mean"),
                            "wcl_mean": row.get("wcl_mean")})
    reasons = [str(reason)[:160] for reason in fidelity.get("reasons") or []] if fidelity.get("blizzlike") is False else []
    if not outside and not reasons:
        return
    parts = [f"{row['name']} melee mean {row['mean_ratio']}x WCL over {row['swings']} swings" for row in outside]
    if reasons:
        parts.append("not Blizzlike: " + "; ".join(reasons[:2]))
    out.append(_finding("boss_melee_fidelity", "warn", record["kill_id"],
                        "; ".join(parts) + f" (tolerance +-{MELEE_TOLERANCE:.0%}, min {MELEE_MIN_SWINGS} swings)",
                        {"creatures": outside, "blizzlike": fidelity.get("blizzlike"), "reasons": reasons,
                         "tolerance": MELEE_TOLERANCE, "min_swings": MELEE_MIN_SWINGS}))


def check_unmeasured(ctx: _Label, record: dict[str, Any], out: list) -> None:
    reason = ctx.eligibility(record)
    validity = record.get("measurement_validity") or {}
    if reason in UNMEASURED_REASONS:
        out.append(_finding("unmeasured_kills", "warn", record["kill_id"],
                            f"not counted ({reason}): {', '.join(validity.get('reasons') or []) or 'no measurement'}; "
                            f"native_clear={record.get('native_clear')}. A truncated capture (16 MB cap) or missing "
                            "combat log leaves no boss window to judge",
                            {"exclusion_reason": reason, "reasons": list(validity.get("reasons") or []),
                             "native_clear": record.get("native_clear"), "death_basis": record.get("death_basis")}))
        return
    if reason is not None:
        return
    log = (record.get("sanity_inputs") or {}).get("combat_log") or {}
    ring = (record.get("encounter_reconciliation") or {}).get("window_retained")
    problems = []
    if log.get("capture_truncated"):
        problems.append("the harness truncated the worldserver capture")
    if log.get("boss_window_retained") is False or ring is False:
        problems.append("the combat-log ring dropped events inside the boss window")
    if problems:
        out.append(_finding("unmeasured_kills", "warn", record["kill_id"],
                            "counted kill with partial telemetry: " + "; ".join(problems)
                            + " (deaths, pulls and fidelity may be incomplete)",
                            {"capture_truncated": log.get("capture_truncated"),
                             "boss_window_retained": log.get("boss_window_retained", ring),
                             "recent_events_dropped": log.get("recent_events_dropped")}))


def check_excluded(ctx: _Label, record: dict[str, Any], out: list) -> None:
    reason = ctx.eligibility(record)
    if reason not in EXCLUDED_REASONS:
        return
    evidence: dict[str, Any] = {"exclusion_reason": reason, "native_clear": record.get("native_clear"),
                                "outcome": record.get("outcome")}
    detail = f"not counted ({reason})"
    if reason == "stalled_boss_window":
        validity = record.get("measurement_validity") or {}
        thresholds = validity.get("thresholds") or {}
        evidence.update({key: validity.get(key) for key in ("reasons", "stall_fraction", "stalled_sec", "max_stall_sec",
                                                            "stall_count", "window_duration_sec")})
        evidence["max_stall_fraction"] = thresholds.get("max_boss_window_stall_fraction")
        evidence["max_single_stall_sec"] = thresholds.get("max_single_boss_window_stall_sec")
        detail += (f": {validity.get('stalled_sec')} s stalled in {validity.get('stall_count')} stall(s), fraction "
                   f"{validity.get('stall_fraction')} (limit {evidence['max_stall_fraction']}), longest "
                   f"{validity.get('max_stall_sec')} s")
        if not validity.get("stalled_sec") and not validity.get("max_stall_sec"):
            detail += "; no stall time was recorded, so the stall label is suspect (check the harness reason codes)"
    elif reason == "voided":
        evidence["void_reason"] = str((record.get("voided") or {}).get("reason") or "")[:300]
        detail += f": {evidence['void_reason']}"
    elif reason == "postprocess_error":
        evidence["postprocess_error"] = str(record.get("postprocess_error") or "")[:300]
        detail += f": {evidence['postprocess_error']}"
    elif reason in ("infrastructure_failure", "interrupted"):
        evidence["completion_reason"] = record.get("completion_reason")
        detail += f": {record.get('completion_reason')}"
    out.append(_finding("excluded_kills", "warn", record["kill_id"], detail, evidence))


KILL_CHECKS = (check_duration, check_enrage, check_death_signal, check_repeated_deaths, check_health_pinned,
               check_instant_revive, check_idle, check_melee, check_unmeasured, check_excluded)


def sanity_findings(root: Path, scenario: str, label: str) -> list[dict]:
    """Findings for one label of one scenario, blocking first; [] when the label has no kills."""
    ctx = _Label(Path(root), scenario, label)
    findings: list[dict[str, Any]] = []
    for record in ctx.kills:
        for check in KILL_CHECKS:
            check(ctx, record, findings)
    for (check, why), kill_ids in ctx.not_evaluable.items():
        findings.append(_finding(check, "warn", None, f"not evaluable for {len(kill_ids)} kill(s): {why}",
                                 {"status": NOT_EVALUABLE, "kill_ids": kill_ids}))
    order = {name: index for index, name in enumerate(CHECK_ORDER)}
    return sorted(findings, key=lambda row: (row["severity"] != "blocking", order.get(row["check"], len(order))))


def _print(scenario: str, label: str, findings: list[dict[str, Any]]) -> None:
    blocking = sum(row["severity"] == "blocking" for row in findings)
    print(f"{scenario} {label}: {blocking} blocking, {len(findings) - blocking} warn")
    for row in findings:
        kill = f" [{row['kill_id']}]" if row.get("kill_id") else ""
        print(f"  {row['severity']:8} {row['check']}{kill}: {row['detail']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run-sanity findings for scoreboard labels.")
    parser.add_argument("scenarios", nargs="+", help="raid target scenario ids")
    parser.add_argument("--label", required=True)
    parser.add_argument("--json", action="store_true", help="print {scenario: findings} as JSON")
    args = parser.parse_args(argv)
    result = {scenario: sanity_findings(ROOT, scenario, args.label) for scenario in args.scenarios}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for scenario, findings in result.items():
            _print(scenario, args.label, findings)
    return 1 if any(row["severity"] == "blocking" for rows in result.values() for row in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
