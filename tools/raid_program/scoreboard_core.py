"""Shared scoreboard primitives: paths, target file, WCL targets, records, counting rules."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from tools.raid_program.play_mode_guard import PLAY_EXCLUSION_REASON, find_play_markers

ROOT = Path(__file__).resolve().parents[2]
TARGET_SCHEMA = "raid_target_v1"
KILL_SCHEMA = "raid_scoreboard_kill_v1"
ATTACHMENT_SCHEMA = "raid_scoreboard_evidence_attachment_v1"
# Informational encounter RNG (e.g. Massive Crash side) recomputed later from archived evidence.
RNG_ATTACHMENT_SCHEMA = "raid_scoreboard_rng_attachment_v1"
VOID_SCHEMA = "raid_scoreboard_void_v1"
VERDICT_SCHEMA = "raid_target_verdict_v1"
COMPARISON_SCHEMA = "raid_label_comparison_v1"
BASELINE_SCHEMA = "raid_scoreboard_baseline_v1"
TARGET_DIR = "experiments/configs/raid_targets"
# Sidecars of raid targets: other rosters a target judges without changing its bytes (verdicts pin them).
ROSTER_VARIANTS_SCHEMA = "raid_target_roster_variants_v1"
ROSTER_VARIANTS_DIR = "experiments/configs/raid_target_roster_variants"
SCOREBOARD_DIR = "artifacts/cata_raid_program/scoreboard"
PROMOTED_RECEIPT_MIRROR = "experiments/configs/wowsims_promoted_generation_receipts"
EVIDENCE_DIR = "artifacts/cata_raid_program"
HEALER_ROLES = ("healer",)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def git_head(root: Path) -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    return result.stdout.strip() or None


def target_path(root: Path, scenario: str) -> Path:
    return root / TARGET_DIR / f"{scenario}.json"


def scoreboard_path(root: Path, scenario: str) -> Path:
    return root / SCOREBOARD_DIR / f"{scenario}.jsonl"


def baseline_path(root: Path, scenario: str) -> Path:
    return root / SCOREBOARD_DIR / f"{scenario}.baseline.json"


def load_baseline(root: Path, scenario: str) -> dict[str, Any] | None:
    """The scenario's baseline pointer written by `scoreboard baseline --label`, or None when unset."""
    path = baseline_path(Path(root), scenario)
    if not path.exists():
        return None
    baseline = json.loads(path.read_text())
    if baseline.get("schema") != BASELINE_SCHEMA or baseline.get("scenario") != scenario or not baseline.get("label"):
        raise ValueError(f"{path} is not a {BASELINE_SCHEMA} pointer for {scenario}")
    return baseline


def default_label(root: Path, scenario: str, records: list[dict[str, Any]]) -> tuple[str | None, str]:
    """(label, source) when no label is given: the baseline when set, else the most recently recorded label."""
    baseline = load_baseline(root, scenario)
    if baseline:
        return baseline["label"], f"baseline set {baseline.get('set_at')}"
    return latest_label(records), "latest recorded label; no baseline set"


def load_target(root: Path, scenario: str) -> dict[str, Any]:
    path = target_path(root, scenario)
    if not path.exists():
        raise SystemExit(f"no raid target for scenario {scenario!r}: create {TARGET_DIR}/{scenario}.json")
    target = json.loads(path.read_text())
    if target.get("schema") != TARGET_SCHEMA or target.get("scenario") != scenario:
        raise ValueError(f"{path} is not a {TARGET_SCHEMA} target for {scenario}")
    return target


def kills_per_batch(target: dict[str, Any]) -> int:
    """Counted native clears per label for a keep/revert batch (kills_per_measurement is the finish-line minimum)."""
    return int(target.get("kills_per_batch", target["kills_per_measurement"]))


def healer_roles(target: dict[str, Any]) -> set[str]:
    return set(target.get("roles_without_dps_target", HEALER_ROLES))


# The user's decision (2026-09-27) exempts only the Feral tank; any other value is a config error.
ALLOWED_DPS_GATE_EXEMPT_SPECS = frozenset({"feral_druid_tank"})


class TargetConfigError(ValueError):
    """A raid target field is malformed; the verdict refuses rather than passing."""


def dps_gate_exempt_specs(target: dict[str, Any]) -> set[str]:
    """Specs whose DPS is recorded but informational: no parity gate, and no reference needed.

    Declared per target (dps_gate_exempt_specs), like roles_without_dps_target for healers. The field
    must be a list of strings drawn from ALLOWED_DPS_GATE_EXEMPT_SPECS; only actors whose roster role
    is tank are exempt (see is_dps_gate_exempt).
    """
    if "dps_gate_exempt_specs" not in target:
        return set()
    value = target["dps_gate_exempt_specs"]
    if not isinstance(value, list) or not all(isinstance(spec, str) for spec in value):
        raise TargetConfigError(f"dps_gate_exempt_specs must be a list of spec strings, got {value!r}")
    unknown = sorted(set(value) - ALLOWED_DPS_GATE_EXEMPT_SPECS)
    if unknown:
        raise TargetConfigError(f"dps_gate_exempt_specs may only name {sorted(ALLOWED_DPS_GATE_EXEMPT_SPECS)}; "
                                f"got {unknown}")
    return set(value)


def is_dps_gate_exempt(exempt: set[str], spec: str, role: str) -> bool:
    """An actor is exempt only when its spec is exempt and its roster role is tank."""
    return spec in exempt and role == "tank"


def roster(target: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Expected actors: actor id -> {spec, role, name}."""
    return {str(actor_id): row for actor_id, row in (target.get("roster") or {}).items()}


def roster_variants_path(root: Path, scenario: str) -> Path:
    return Path(root) / ROSTER_VARIANTS_DIR / f"{scenario}.json"


def target_for_records(root: Path, target: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    """The target as it judges these kill records.

    A target's sidecar (ROSTER_VARIANTS_DIR/<scenario>.json, raid_target_roster_variants_v1) may declare
    roster variants. When every record is a shard run of one variant's validation scenario (the record's
    shard_identity.scenario_id), that variant's roster replaces the top-level roster, and `roster_variant`
    pins the sidecar (path, sha256) for the verdict; otherwise (legacy runs, no records, mixed scenarios)
    the target is returned unchanged. The target file itself never changes, so accepted verdicts keep
    their target_sha256.
    """
    scenario = target.get("scenario")
    path = roster_variants_path(root, str(scenario)) if scenario else None
    if path is None or not path.is_file():
        return target
    sidecar = json.loads(path.read_text())
    if sidecar.get("schema") != ROSTER_VARIANTS_SCHEMA or sidecar.get("target_scenario") != scenario:
        raise ValueError(f"{path} is not a {ROSTER_VARIANTS_SCHEMA} sidecar of {scenario}")
    scenarios = {str(((record or {}).get("shard_identity") or {}).get("scenario_id") or "") for record in records}
    for variant in sidecar.get("variants") or []:
        variant_id = str(variant.get("validation_scenario_id") or "")
        if variant_id and scenarios == {variant_id}:
            return {**target, "roster": variant["roster"], "validation_scenario_id": variant_id,
                    "roster_variant": {"path": path.relative_to(root).as_posix(), "sha256": file_sha256(path),
                                       "validation_scenario_id": variant_id}}
    return target


def _matched_references(root: Path, target: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = json.loads((root / target["wcl_reference_manifest"]).read_text())
    wanted = list(target["matched_reference_ids"])
    matched = [ref for ref in manifest["references"] if ref["id"] in wanted]
    missing = sorted(set(wanted) - {ref["id"] for ref in matched})
    if missing:
        raise ValueError(f"matched reference ids not in {target['wcl_reference_manifest']}: {missing}")
    return matched


def spec_targets(root: Path, target: dict[str, Any]) -> dict[str, float]:
    """Median matched WCL DPS per spec. Specs without a matched reference are absent."""
    values: defaultdict[str, list[float]] = defaultdict(list)
    for ref in _matched_references(root, target):
        for spec, dps in ref["actor_dps"].items():
            values[spec].append(float(dps))
    return {spec: statistics.median(dps) for spec, dps in values.items()}


def fallback_index_path(root: Path, target: dict[str, Any]) -> Path | None:
    fallback = target.get("fallback_reference") or {}
    return root / fallback["promotion_index"] if fallback.get("promotion_index") else None


def fallback_targets(root: Path, target: dict[str, Any]) -> dict[str, float]:
    """WoWSims DPS per spec from the promotion index, used only where no matched WCL reference exists.

    A spec's DPS is result_observation.dps of its entry's generation receipt. A receipt that is
    missing, unreadable, differs from the index sha256, names another spec, reports a simulator
    error or has no positive DPS is skipped, so that spec stays no_reference.
    """
    path = fallback_index_path(root, target)
    if path is None or not path.exists():
        return {}
    values: defaultdict[str, list[float]] = defaultdict(list)
    for entry in json.loads(path.read_text()).get("entries") or []:
        receipt = (entry or {}).get("generation_receipt") or {}
        spec = entry.get("target_spec")
        try:
            receipt_path = root / receipt["path"]
            if not receipt_path.exists():
                # The promoted bundle is DVC payload that is normally evicted; the finish line
                # must not depend on it. Read the sha256-named git-tracked mirror instead.
                receipt_path = root / PROMOTED_RECEIPT_MIRROR / f"{receipt.get('sha256')}.json"
            data = receipt_path.read_bytes()
            if hashlib.sha256(data).hexdigest() != receipt.get("sha256"):
                continue
            document = json.loads(data)
            dps = float(document["result_observation"]["dps"])
        except (KeyError, TypeError, ValueError, OSError):
            continue
        if document.get("target_spec") not in (None, spec) or document.get("simulator_error"):
            continue
        if spec and dps > 0 and dps != float("inf"):
            values[spec].append(dps)
    return {spec: statistics.median(dps) for spec, dps in values.items()}


NATIVE_SCOPE_KEY = "native_dps_excluded_target_entries"


def dps_enemy_scope(excluded: list[int]) -> dict[str, Any]:
    """The normalized enemy-scope marker a scoped record carries (and the verdict requires)."""
    return {"excluded_target_entries": sorted(int(entry) for entry in excluded), "scoped": True}


def native_excluded_entries(target: dict[str, Any]) -> list[int]:
    """Creature entries a target's WCL references leave out of damage-done (e.g. Nefarian's bone warriors)."""
    return sorted({int(entry) for entry in target.get(NATIVE_SCOPE_KEY) or []})


def declared_no_reference_specs(target: dict[str, Any]) -> set[str]:
    """Specs a target declares without a reference: no_reference_until_wcl (top level, or under
    reference_status/reference_gaps) and its alias reference_status.no_reference_specs (Omnotron)."""
    specs = set(target.get("no_reference_until_wcl") or [])
    for parent in ("reference_status", "reference_gaps"):
        block = target.get(parent)
        if isinstance(block, dict):
            specs.update(block.get("no_reference_until_wcl") or [])
    status = target.get("reference_status")
    if isinstance(status, dict):
        specs.update(status.get("no_reference_specs") or [])
    return {str(spec) for spec in specs}


def reference_targets(root: Path, target: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per spec: {"dps", "basis", "ratio"}. Matched WCL wins; WoWSims is the fallback.

    A spec declared no_reference_until_wcl never qualifies on the WoWSims fallback: it stays
    no_reference until a role-matched WCL reference exists (and the declaration is then removed).
    """
    blocked = declared_no_reference_specs(target)
    wcl = spec_targets(root, target)
    # An exempt spec (dps_gate_exempt_specs) is informational, so its declaration can never fail anything.
    contradicted = sorted((blocked & set(wcl)) - dps_gate_exempt_specs(target))
    if contradicted:
        raise ValueError(f"{target.get('scenario')}: {contradicted} declared no_reference_until_wcl but has a "
                         "matched WCL reference; remove the declaration or the reference")
    references = {spec: {"dps": dps, "basis": "wowsims_fallback",
                         "ratio": float(target["fallback_reference"]["ratio"])}
                  for spec, dps in fallback_targets(root, target).items() if spec not in blocked}
    references.update({spec: {"dps": dps, "basis": "wcl", "ratio": float(target["actor_dps_ratio"])}
                       for spec, dps in wcl.items()})
    return references


def party_reference_dps(root: Path, target: dict[str, Any]) -> float | None:
    values = [float(ref["raid_dps"]) for ref in _matched_references(root, target) if ref.get("raid_dps")]
    return statistics.median(values) if values else None


def legacy_kill_id(record: dict[str, Any]) -> str:
    """Stable id for lines written before kill ids existed."""
    return f"{record['label']}-{Path(str(record.get('run_dir') or 'unknown')).name}"


def load_lines(root: Path, scenario: str) -> list[dict[str, Any]]:
    path = scoreboard_path(root, scenario)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_records(root: Path, scenario: str) -> list[dict[str, Any]]:
    """Kill records in recording order, with evidence and RNG attachments and voids merged in.

    An RNG attachment only fills a kill that has no encounter_rng yet (the first value wins), so
    informational data can never make the file unreadable or change counting.
    """
    kills: dict[str, dict[str, Any]] = {}
    path = scoreboard_path(root, scenario)
    for line in load_lines(root, scenario):
        schema = line.get("schema")
        if schema == KILL_SCHEMA:
            record = dict(line)
            record.setdefault("kill_id", legacy_kill_id(record))
            record.setdefault("outcome", "clear" if record.get("native_clear") else "gameplay_failure")
            if record["kill_id"] in kills:
                raise ValueError(f"{path}: duplicate kill_id {record['kill_id']}")
            kills[record["kill_id"]] = record
            continue
        if schema not in (ATTACHMENT_SCHEMA, RNG_ATTACHMENT_SCHEMA, VOID_SCHEMA):
            raise ValueError(f"{path}: unexpected record schema {schema!r}")
        record = kills.get(line.get("kill_id"))
        if record is None:
            raise ValueError(f"{path}: {schema} for unknown kill_id {line.get('kill_id')!r}")
        if schema == ATTACHMENT_SCHEMA:
            if record.get("evidence_dvc_pointer"):
                raise ValueError(f"{path}: kill {record['kill_id']} already has evidence")
            record["evidence_dvc_pointer"] = line["evidence_dvc_pointer"]
            record["evidence_attached_at"] = line.get("recorded_at")
        elif schema == RNG_ATTACHMENT_SCHEMA:
            if not record.get("encounter_rng") and isinstance(line.get("encounter_rng"), dict):
                record["encounter_rng"] = line["encounter_rng"]
                record["encounter_rng_attached_at"] = line.get("recorded_at")
        else:
            record["voided"] = {key: line.get(key) for key in ("reason", "recorded_at", "recorded_by")}
    return list(kills.values())


def append_record(root: Path, scenario: str, record: dict[str, Any]) -> Path:
    path = scoreboard_path(root, scenario)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def latest_label(records: list[dict[str, Any]]) -> str | None:
    return records[-1]["label"] if records else None


def label_kills(records: list[dict[str, Any]], label: str | None) -> list[dict[str, Any]]:
    return [record for record in records if record["label"] == label]


# Harness reason codes for a boss window invalidated by world stalls: v1 used one code,
# v2 (bot_measurement_validity_v2) separates the stalled fraction from one long stall.
BOSS_WINDOW_STALL_REASONS = frozenset({"world_stall_overlaps_boss_window", "boss_window_stall_fraction_exceeded",
                                       "boss_window_stall_too_long"})
# Harness reason codes for a boss window that was never measured (the combat log did not
# reach the harness, so there is no encounter window to judge). Not a stall, and not gameplay.
BOSS_WINDOW_UNMEASURED_REASONS = frozenset({"combat_log_unavailable", "no_boss_window",
                                            "combat_log_event_window_misses_boss_window"})


def exclusion_reason(record: dict[str, Any]) -> str | None:
    """Why a kill does not count toward a verdict (None = counted)."""
    if find_play_markers(record):  # human play sessions are recorded for ML, never scored
        return PLAY_EXCLUSION_REASON
    if record.get("voided"):
        return "voided"
    if record.get("interrupted"):
        return "interrupted"
    if record.get("outcome") == "infrastructure_failure":
        return "infrastructure_failure"
    if not record.get("evidence_dvc_pointer"):
        return "no_evidence"
    if record.get("postprocess_error") and record.get("outcome") != "gameplay_failure":
        return "postprocess_error"
    validity = record.get("measurement_validity")
    if not validity:
        # Recorded before the harness measured world stalls (d2393eb5a1): those boss
        # windows lost 11-21% to heartbeat freezes and are not comparable.
        return "no_measurement_validity"
    if validity.get("valid_for_dps") is not True:
        # A clear with an invalid window is not a DPS measurement. A wipe still counts
        # as a gameplay failure unless a stall actually hit the boss window (a trash
        # wipe is invalid only because it has no boss window).
        reasons = set(validity.get("reasons") or [])
        if BOSS_WINDOW_STALL_REASONS & reasons:
            return "stalled_boss_window"
        if record.get("native_clear"):
            # Only an explicit unmeasured-window code relabels a clear; any other invalid
            # window keeps the historical stalled_boss_window code.
            return "unmeasured_boss_window" if reasons and reasons <= BOSS_WINDOW_UNMEASURED_REASONS \
                else "stalled_boss_window"
    return None


def counted_kills(kills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in kills if exclusion_reason(record) is None]


def clear_kills(kills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Counted kills whose numbers count: native clears with encounter-window data."""
    return [record for record in counted_kills(kills) if record.get("native_clear") and record.get("encounter")]


def mean_sd(values: list[float]) -> tuple[float | None, float | None]:
    """Sample mean and sample standard deviation (None when undefined)."""
    if not values:
        return None, None
    mean = statistics.fmean(values)
    return mean, (statistics.stdev(values) if len(values) > 1 else None)


def detectable_delta(critical: float | None, new: list[float], old: list[float]) -> float | None:
    """Smallest |delta| the two-sided 95% Welch t calls a change at these n: t95 x sqrt(sd1^2/n1 + sd2^2/n2)."""
    (_, new_sd), (_, old_sd) = mean_sd(new), mean_sd(old)
    if critical is None or new_sd is None or old_sd is None:
        return None
    return critical * math.sqrt(new_sd ** 2 / len(new) + old_sd ** 2 / len(old))


def _actor_key(actor_id: str):
    return (0, int(actor_id)) if actor_id.isdigit() else (1, actor_id)


def actor_rows(clears: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Actor rows of the given kills, keyed by actor id in guid order."""
    rows: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in clears:
        for actor in record.get("actors") or []:
            rows[str(actor["actor_id"])].append(actor)
    return dict(sorted(rows.items(), key=lambda item: _actor_key(item[0])))


def actor_identity(target: dict[str, Any], actor_id: str, rows: list[dict[str, Any]]) -> tuple[str, str, str | None]:
    """(spec, role, name): the target roster wins over whatever a run recorded."""
    expected = roster(target).get(actor_id) or {}
    last = rows[-1] if rows else {}
    return (expected.get("spec") or last.get("spec") or "unknown",
            expected.get("role") or last.get("role") or "unknown",
            expected.get("name") or last.get("name"))
