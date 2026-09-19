"""Read the canonical capture's existing records without a second export format."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.bot_ml.analyze_combat_log import analyze_combat_log
from tools.raid_program.capture_runtime_identity import (
    _roster_binding_identity,
    _runtime_identity,
)
from tools.raid_program.capture_value_types import _canonical_object_sha256


_CANONICAL_SCHEMA_VERSION = 2
_TRACE_CHANNEL_ACTIONS = frozenset({"botauto_diagnose", "botauto_trace"})
_COMBAT_CHANNEL_ACTIONS = frozenset({
    "botauto_combatlog", "botauto_combatlog_delta",
    "botauto_combatlog_chunk", "botauto_combatlog_complete",
})


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _validate_report_self_hash(report: dict[str, Any]) -> str:
    """Validate the producer's non-circular report digest before any joins."""

    report_hash = report.get("report_sha256")
    inventory = report.get("artifact_inventory")
    if not _is_sha256(report_hash) or not isinstance(inventory, list):
        raise ValueError("canonical capture report self-hash is missing")
    report_entries = [
        entry for entry in inventory
        if isinstance(entry, dict) and entry.get("kind") == "capture_report"
    ]
    if len(report_entries) != 1 or not _is_sha256(report_entries[0].get("sha256")):
        raise ValueError("canonical capture report self-hash artifact is missing")
    if report_entries[0]["sha256"] != report_hash:
        raise ValueError("canonical capture report self-hash fields disagree")

    hash_payload = copy.deepcopy(report)
    hash_payload["report_sha256"] = None
    hash_payload["artifact_inventory"] = [
        (
            {**entry, "sha256": None}
            if isinstance(entry, dict) and entry.get("kind") == "capture_report"
            else entry
        )
        for entry in inventory
    ]
    actual = hashlib.sha256(
        json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if actual != report_hash:
        raise ValueError("canonical capture report self-hash mismatch")
    return report_hash


def canonical_actor_identity(report: Any) -> dict[str, dict[str, Any]]:
    """Return only identity admitted by the accepted runtime receipt.

    A canonical capture's telemetry contains transient actor projections.  They
    are useful for tracing, but they cannot add or overwrite the immutable
    identity accepted at admission.
    """

    if not is_canonical_capture(report) or not isinstance(report, dict):
        return {}
    runtime = report.get("accepted_raid_runtime")
    receipt = runtime.get("admission_receipt") if isinstance(runtime, dict) else None
    members = receipt.get("members") if isinstance(receipt, dict) else None
    if not isinstance(members, list):
        return {}
    identities: dict[str, dict[str, Any]] = {}
    for member in members:
        if not isinstance(member, dict):
            continue
        guid = member.get("guid")
        if isinstance(guid, bool) or not isinstance(guid, int) or guid <= 0:
            continue
        identity: dict[str, Any] = {}
        for target, keys in (
            ("bot_name", ("name", "bot_name")),
            ("role", ("role",)),
            ("class_spec", ("class_spec",)),
            ("class_name", ("class_name",)),
            ("class_id", ("class_id",)),
        ):
            for key in keys:
                if member.get(key) not in (None, ""):
                    identity[target] = member[key]
                    break
        identities[str(guid)] = identity
    return identities


def _validate_evidence_contract(report: dict[str, Any], row_count: int) -> str:
    evidence = report.get("evidence_demux")
    if not isinstance(evidence, dict):
        raise ValueError("canonical evidence demux report is missing")
    if evidence.get("normalized_schema_version") != _CANONICAL_SCHEMA_VERSION:
        raise ValueError("canonical evidence demux schema version invalid")
    canonical_hash = evidence.get("canonical_identity_sha256")
    if not _is_sha256(canonical_hash):
        raise ValueError("canonical identity digest is missing")
    retained_rows = evidence.get("retained_rows")
    if (
        isinstance(retained_rows, bool)
        or not isinstance(retained_rows, int)
        or retained_rows != row_count
    ):
        raise ValueError("canonical evidence demux row count mismatch")
    return canonical_hash


def _validated_rows(raw: bytes, *, expected_rows: int, canonical_hash: str) -> list[dict[str, Any]]:
    """Validate producer wrappers, retaining only bound rows."""

    rows: list[dict[str, Any]] = []
    parsed_rows = 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        parsed_rows += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("canonical raw capture contains invalid JSON") from exc
        if not isinstance(row, dict):
            raise ValueError("canonical raw capture row is not an object")
        if row.get("normalized_schema_version") != _CANONICAL_SCHEMA_VERSION:
            raise ValueError("canonical normalized schema version invalid")
        if (
            isinstance(row.get("capture_sequence"), bool)
            or not isinstance(row.get("capture_sequence"), int)
            or row.get("capture_sequence") != parsed_rows
        ):
            raise ValueError("canonical capture sequence is not contiguous")
        payload = row.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("canonical normalized payload is not an object")
        action = row.get("action")
        if not isinstance(action, str) or action != payload.get("action"):
            raise ValueError("canonical wrapper action mismatch")
        binding = row.get("identity_binding")
        if not isinstance(binding, dict):
            continue
        if binding.get("state") != "bound" or binding.get("canonical_identity_sha256") != canonical_hash:
            continue
        rows.append(row)
    if parsed_rows != expected_rows:
        raise ValueError("canonical raw capture row count mismatch")
    return rows


def _sanitize_payload(payload: dict[str, Any], *, canonical_hash: str,
                      actor_guids: set[int]) -> dict[str, Any]:
    value = copy.deepcopy(payload)
    if value.get("action") not in _TRACE_CHANNEL_ACTIONS:
        return value
    bots = value.get("bots")
    if not isinstance(bots, list):
        return value
    admitted: list[dict[str, Any]] = []
    for bot in bots:
        if not isinstance(bot, dict):
            continue
        binding = bot.get("identity_binding")
        if not isinstance(binding, dict):
            continue
        if (
            binding.get("state") != "bound"
            or binding.get("canonical_identity_sha256") != canonical_hash
        ):
            continue
        guid = bot.get("bot_guid")
        if isinstance(guid, bool) or not isinstance(guid, int) or guid <= 0:
            continue
        if guid not in actor_guids:
            continue
        admitted.append(bot)
    value["bots"] = admitted
    return value


def _filter_combat_log(combat_log: dict[str, Any], actor_guids: set[int]) -> dict[str, Any]:
    """Keep only rows and counts attributable to admitted actors.

    The native export's identity is bound at the runtime level, while every
    actor-scoped aggregate below is still a row-level projection.  Filter the
    projections before handing them to the offline analyzer; a report's
    precomputed analysis is not an identity boundary.
    """

    if not actor_guids:
        return {}
    value = copy.deepcopy(combat_log)

    def matches_actor(row: dict[str, Any], guid_fields: tuple[str, ...]) -> bool:
        # The first field is authoritative when it is present.  Do not let an
        # admitted alias rescue a row whose explicit actor is foreign.
        for key in guid_fields:
            if key not in row:
                continue
            guid = row.get(key)
            return (
                isinstance(guid, int)
                and not isinstance(guid, bool)
                and int(guid) in actor_guids
            )
        return False

    removed_rows = 0
    for field, guid_fields in (
        ("recent_events", ("actor_guid", "source_guid")),
        ("abilities", ("actor_guid", "bot_guid")),
        ("second_buckets", ("actor_guid", "bot_guid")),
        ("action_outcomes", ("actor_guid", "bot_guid")),
        ("candidate_rejections", ("actor_guid", "bot_guid")),
    ):
        rows = value.get(field)
        if not isinstance(rows, list):
            continue
        value[field] = [
            row for row in rows
            if isinstance(row, dict) and matches_actor(row, guid_fields)
        ]
        removed_rows += len(rows) - len(value[field])

    abilities = value.get("abilities")
    if removed_rows:
        # Native sequence counts cannot be reconstructed from ability aggregates:
        # one event can create multiple perspectives, and melee resolutions have
        # no ability aggregate. Preserve uncertainty after actor filtering.
        for key in ("event_count", "event_count_at_export", "full_event_count",
                    "recent_events_dropped"):
            value.pop(key, None)
        value["actor_filter"] = {"removed_rows": removed_rows,
                                 "event_counters_available": False}
    if "aggregate_count" in value or isinstance(abilities, list):
        value["aggregate_count"] = len(abilities) if isinstance(abilities, list) else 0
    buckets = value.get("second_buckets")
    if "second_bucket_count" in value or isinstance(buckets, list):
        value["second_bucket_count"] = len(buckets) if isinstance(buckets, list) else 0
    return value


def is_canonical_capture(report: Any) -> bool:
    return isinstance(report, dict) and str(report.get("capture_id", "")).startswith("cata_raid_phase1_")


def load_canonical_capture(directory: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Require the report-bound raw bytes; never substitute an old derived timeline."""
    if not is_canonical_capture(report):
        raise ValueError("not a canonical raid capture")
    _validate_report_self_hash(report)
    binding = report.get("raw_normalized_batch") or {}
    if not isinstance(binding, dict):
        raise ValueError("canonical raw capture binding is missing")
    expected_rows = binding.get("row_count")
    expected_raw_hash = binding.get("sha256")
    raw_path = binding.get("path")
    if (
        not isinstance(raw_path, str)
        or not raw_path
        or isinstance(expected_rows, bool)
        or not isinstance(expected_rows, int)
        or expected_rows < 0
        or not _is_sha256(expected_raw_hash)
    ):
        raise ValueError("canonical raw capture binding is invalid")
    canonical_hash = _validate_evidence_contract(report, expected_rows)
    filename = Path(raw_path).name
    path = directory / filename
    if not path.is_file():
        raise ValueError(f"canonical raw capture unavailable: {path}")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_raw_hash:
        raise ValueError("canonical raw capture hash mismatch")
    rows = _validated_rows(
        raw,
        expected_rows=expected_rows,
        canonical_hash=canonical_hash,
    )
    actor_identity = canonical_actor_identity(report)
    actor_guids = {int(guid) for guid in actor_identity}
    for row in rows:
        row["payload"] = _sanitize_payload(
            row["payload"], canonical_hash=canonical_hash,
            actor_guids=actor_guids,
        )
    payloads = [row["payload"] for row in rows]
    from tools.bot_ml.run_live_bot_validation import combined_combat_log

    # Recompute the producer's identity digest when an admitted active status is
    # retained.  The report digest is still required when no such status exists;
    # that case remains usable for trace review but cannot produce combat data.
    active = [row for row in payloads if row.get("action") == "botauto_status"
              and isinstance(row.get("raid_runtime"), dict)
              and row["raid_runtime"].get("active") is True]
    for status in active:
        runtime = status.get("raid_runtime")
        roster = runtime.get("roster") if isinstance(runtime, dict) else None
        identity = _runtime_identity(runtime, include_strategy=False) if isinstance(runtime, dict) else None
        roster_identity = _roster_binding_identity(roster) if isinstance(roster, list) else None
        if identity is None or roster_identity is None:
            continue
        recomputed = _canonical_object_sha256({
            "cohort_id": status.get("cohort_id"),
            "runtime_identity": identity,
            "roster_sha256": _canonical_object_sha256(roster_identity),
        })
        if recomputed != canonical_hash:
            raise ValueError("canonical identity digest does not match retained status")
        break

    if not active:
        return {
            "rows": rows,
            "payloads": payloads,
            "combat_log": {},
            "combat_analysis": {},
            "actor_identity": actor_identity,
        }
    combat = [row for row in payloads if row.get("action") in _COMBAT_CHANNEL_ACTIONS]
    combat_log = combined_combat_log(combat, expected_status=active[-1])
    combat_log = _filter_combat_log(combat_log, actor_guids)
    combat_analysis = analyze_combat_log(combat_log) if combat_log else {}
    if combat_log.get("actor_filter", {}).get("event_counters_available") is False:
        combat_analysis["tracked_event_count"] = None
        combat_analysis["recent_events_dropped"] = None
        combat_analysis["event_counters_available"] = False
    return {
        "rows": rows,
        "payloads": payloads,
        "combat_log": combat_log,
        "combat_analysis": combat_analysis,
        "actor_identity": actor_identity,
    }
