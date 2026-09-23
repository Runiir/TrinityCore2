"""evaluate_target: judge one label's counted kills against the scenario target.

Counted kills are the label's kills that are not voided, interrupted,
infrastructure failures, missing evidence, clears whose post-processing
crashed, recorded without measurement_validity, or measured over a stalled
boss window. Every kill of the label is listed in kills_detail with its exclusion.
`reasons` holds stable codes; `reason` is the readable explanation.

Each non-healer actor is judged against a reference_basis: "wcl" (median matched
WCL DPS x actor_dps_ratio), else "wowsims_fallback" (the verified WoWSims DPS of
the spec x fallback_reference.ratio), else "none" (status no_reference).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from tools.raid_program.scoreboard_core import (
    VERDICT_SCHEMA, actor_identity, actor_rows, clear_kills, counted_kills, default_label, exclusion_reason,
    fallback_index_path, file_sha256, healer_roles, label_kills, load_records, load_target, mean_sd,
    party_reference_dps, reference_targets, roster, target_path,
)

BASIS_TEXT = {"wcl": "WCL", "wowsims_fallback": "WoWSims fallback"}


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


REASON_ORDER = (
    "no_kills", "non_clear_kill", "missing_encounter_data", "boss_window_deaths_unknown", "boss_window_deaths",
    "mixed_binaries", "mixed_commits", "roster_incomplete", "insufficient_kills", "below_target",
    "encounter_failed", "no_reference", "voided", "interrupted", "infrastructure_failure", "no_evidence",
    "postprocess_error", "no_measurement_validity", "stalled_boss_window",
)


class _Reasons:
    """Unique reason codes in the fixed REASON_ORDER, with readable details in the same order."""

    def __init__(self) -> None:
        self._items: list[tuple[str, str]] = []

    def add(self, code: str, detail: str) -> None:
        if code not in REASON_ORDER:
            raise ValueError(f"unknown reason code {code}")
        self._items.append((code, detail))

    def _sorted(self) -> list[tuple[str, str]]:
        return sorted(self._items, key=lambda item: REASON_ORDER.index(item[0]))  # stable within a code

    @property
    def codes(self) -> list[str]:
        return list(dict.fromkeys(code for code, _ in self._sorted()))

    @property
    def details(self) -> list[str]:
        return [detail for _, detail in self._sorted()]

    def merge(self, other: "_Reasons") -> None:
        self._items.extend(other._items)

    def __len__(self) -> int:
        return len(self._items)


def _kill_name(record: dict[str, Any]) -> str:
    return str(record.get("kill_id"))


def _encounter_verdict(target, kills, clears, party_wcl, reasons: _Reasons) -> dict[str, Any]:
    """Batch validity and clears. Any failure here fails every actor."""
    required = int(target["kills_per_measurement"])
    max_deaths = int(target["max_boss_window_deaths"])
    local = _Reasons()
    for record in kills:
        if not record.get("native_clear"):
            local.add("non_clear_kill", f"kill {_kill_name(record)} was not a native clear "
                        f"({record.get('completion_reason') or record.get('native_reason') or 'no reason'})")
        elif not record.get("encounter"):
            local.add("missing_encounter_data", f"kill {_kill_name(record)} cleared but has no encounter-window data")
        elif record.get("boss_window_deaths") is None:
            local.add("boss_window_deaths_unknown",
                        f"kill {_kill_name(record)} has unknown boss-window deaths ({record.get('death_basis')})")
        elif record["boss_window_deaths"] > max_deaths:
            local.add("boss_window_deaths",
                        f"kill {_kill_name(record)} had {record['boss_window_deaths']} boss-window deaths (max {max_deaths})")
    binaries = {record.get("worldserver_sha256") for record in kills}
    if len(binaries) > 1:
        local.add("mixed_binaries", "counted kills ran different worldserver binaries: "
                    + ", ".join(sorted(str(sha)[:12] for sha in binaries)))
    commits = {record.get("source_commit") for record in kills}
    if len(commits) > 1:
        local.add("mixed_commits", "counted kills come from different source commits: "
                    + ", ".join(sorted(str(commit)[:12] for commit in commits)))
    missing: dict[str, list[str]] = {}
    for actor_id in roster(target):
        absent = [_kill_name(record) for record in clears
                  if actor_id not in {str(actor["actor_id"]) for actor in record.get("actors") or []}]
        if absent:
            missing[actor_id] = absent
    if missing:
        local.add("roster_incomplete", "expected actors missing from counted clears: "
                    + ", ".join(f"{actor_id} in {len(ids)} kill(s)" for actor_id, ids in missing.items()))
    failed = len(local) > 0
    if failed:
        status = "fail"
    elif len(clears) < required:
        status = "insufficient_kills"
        local.add("insufficient_kills", f"{len(clears)} of {required} required native-clear kills counted")
    else:
        status = "pass"
    reasons.merge(local)
    party_dps, _ = mean_sd([float(r["encounter"]["encounter_window_party_dps"]) for r in clears])
    duration, _ = mean_sd([float(r["encounter"]["duration_sec"]) for r in clears])
    window_deaths = [record.get("boss_window_deaths") for record in kills]
    return {
        "n": len(kills),
        "clears": len(clears),
        "mean_party_dps": _round(party_dps),
        "mean_duration_sec": _round(duration, 3),
        "boss_window_deaths": None if None in window_deaths else sum(window_deaths),
        "route_deaths": sum(int(record.get("route_deaths") or 0) for record in kills),
        "party_wcl_dps": party_wcl,
        "party_ratio": _round(party_dps / party_wcl, 3) if party_dps and party_wcl else None,
        "party_dps_gating": bool(target.get("party_dps_gating")),
        "status": status,
        "reasons": local.codes,
        "_missing": missing,
    }


def _kill_detail(record: dict[str, Any]) -> dict[str, Any]:
    reason = exclusion_reason(record)
    return {key: record.get(key) for key in (
        "kill_id", "recorded_at", "worldserver_sha256", "source_commit", "evidence_dvc_pointer", "native_clear")
    } | {"counted": reason is None, "exclusion_reason": reason}


def evaluate_target(root: Path, scenario: str, label: str | None = None) -> dict[str, Any]:
    """Judge one label's counted kills against the scenario target.

    label None judges the baseline label when a baseline is set, else the latest recorded label, and
    names the choice on stderr.
    """
    root = Path(root)
    target = load_target(root, scenario)
    records = load_records(root, scenario)
    if label is None:
        label, source = default_label(root, scenario, records)
        print(f"verdict label: {label} ({source})", file=sys.stderr)
    all_kills = label_kills(records, label)
    kills = counted_kills(all_kills)
    clears = clear_kills(all_kills)
    required = int(target["kills_per_measurement"])
    minimum = float(target["actor_dps_ratio"])
    references = reference_targets(root, target)
    healers = healer_roles(target)
    reasons = _Reasons()
    encounter = _encounter_verdict(target, kills, clears, party_reference_dps(root, target), reasons)
    missing = encounter.pop("_missing")

    rows = actor_rows(clears)
    for actor_id in roster(target):
        rows.setdefault(actor_id, [])
    actors: dict[str, dict[str, Any]] = {}
    for actor_id in sorted(rows, key=lambda key: (0, int(key)) if key.isdigit() else (1, key)):
        series = rows[actor_id]
        spec, role, name = actor_identity(target, actor_id, series)
        mean, sd = mean_sd([float(row["encounter_window_dps"]) for row in series])
        reference = None if role in healers else references.get(spec)
        target_dps = reference["dps"] if reference else None
        required_ratio = reference["ratio"] if reference else None
        basis = reference["basis"] if reference else "none"
        source = BASIS_TEXT.get(basis, basis)
        ratio = mean / target_dps if target_dps and mean is not None else None
        reason = None
        if role in healers:
            status = encounter["status"]
            reason = "encounter_failed" if status == "fail" else None
        elif target_dps is None:
            status, reason = "no_reference", "no_reference"
            reasons.add("no_reference", f"actor {actor_id} ({spec}) has no matched WCL reference and no verified "
                                        "WoWSims fallback; add one before this target can pass")
        elif len(series) < required:
            status, reason = "insufficient_kills", "insufficient_kills"
        elif ratio < required_ratio:
            status, reason = "fail", "below_target"
            reasons.add("below_target", f"actor {actor_id} ({spec}) ratio {ratio:.3f} < {required_ratio} of {source}")
        elif encounter["status"] != "pass":
            status, reason = "fail", "encounter_failed"
            reasons.add("encounter_failed", f"actor {actor_id} ({spec}) meets its target but the encounter failed")
        else:
            status = "pass"
        actors[actor_id] = {
            "spec": spec, "role": role, "name": name, "n": len(series),
            "mean_dps": _round(mean), "sd_dps": _round(sd),
            "target_dps": _round(target_dps, 2),
            "reference_basis": basis,
            "required_ratio": required_ratio,
            "required_dps": _round(target_dps * required_ratio) if target_dps else None,
            "ratio": _round(ratio, 3), "status": status, "reason": reason,
        }

    non_healers = [actor for actor in actors.values() if actor["role"] not in healers]
    if encounter["status"] == "fail" or any(actor["status"] in ("fail", "no_reference") for actor in non_healers):
        status = "fail"
    elif encounter["status"] == "insufficient_kills" or not kills:
        status = "insufficient_kills"
    else:
        status = "pass"
    details = [_kill_detail(record) for record in all_kills]
    if status != "pass":
        if not all_kills:
            reasons.add("no_kills", f"no kills recorded for label {label!r}" if label else "no kills recorded")
        for detail in details:
            if detail["exclusion_reason"]:
                reasons.add(detail["exclusion_reason"],
                            f"kill {detail['kill_id']} not counted: {detail['exclusion_reason']}")
    binaries = {record.get("worldserver_sha256") for record in kills}
    index = fallback_index_path(root, target)
    stamps = sorted(str(record.get("recorded_at")) for record in all_kills if record.get("recorded_at"))
    return {
        "schema": VERDICT_SCHEMA,
        "scenario": scenario,
        "label": label,
        "kills": len(kills),
        "kills_per_measurement": required,
        "actor_dps_ratio": minimum,
        "target_path": str(target_path(root, scenario).relative_to(root)),
        "target_sha256": file_sha256(target_path(root, scenario)),
        "wcl_manifest_sha256": file_sha256(root / target["wcl_reference_manifest"]),
        "wcl_timelines_sha256": file_sha256(root / target["wcl_cast_timelines"]) if target.get("wcl_cast_timelines") else None,
        "fallback_index_sha256": file_sha256(index) if index is not None and index.exists() else None,
        "worldserver_sha256": next(iter(binaries)) if len(binaries) == 1 else None,
        "source_commits": sorted({record["source_commit"] for record in kills if record.get("source_commit")}),
        "first_recorded_at": stamps[0] if stamps else None,
        "last_recorded_at": stamps[-1] if stamps else None,
        "kills_detail": details,
        "voided": [{"kill_id": record["kill_id"], **record["voided"]} for record in all_kills if record.get("voided")],
        "roster": {"expected": list(roster(target)), "missing": missing},
        "actors": actors,
        "encounter": encounter,
        "status": status,
        "reason": "; ".join(reasons.details) if status != "pass" else None,
        "reasons": reasons.codes if status != "pass" else [],
    }
