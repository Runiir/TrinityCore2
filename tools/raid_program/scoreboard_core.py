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


def roster(target: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Expected actors: actor id -> {spec, role, name}."""
    return {str(actor_id): row for actor_id, row in (target.get("roster") or {}).items()}


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


def reference_targets(root: Path, target: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per spec: {"dps", "basis", "ratio"}. Matched WCL wins; WoWSims is the fallback."""
    references = {spec: {"dps": dps, "basis": "wowsims_fallback",
                         "ratio": float(target["fallback_reference"]["ratio"])}
                  for spec, dps in fallback_targets(root, target).items()}
    references.update({spec: {"dps": dps, "basis": "wcl", "ratio": float(target["actor_dps_ratio"])}
                       for spec, dps in spec_targets(root, target).items()})
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
        if record.get("native_clear") or BOSS_WINDOW_STALL_REASONS & set(validity.get("reasons") or []):
            return "stalled_boss_window"
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
