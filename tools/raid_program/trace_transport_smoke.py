"""Fail-closed admission and evidence gates for the ten-actor trace smoke."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROFILE = "trace_transport_10"
POOL_TAG = "blackwing_descent_10n"
ACTOR_COUNT = 10
PRESSURE_WATERMARK = 16
PRESSURE_INTERVAL_SECONDS = 2.0
PRESSURE_WARMUP_SECONDS = 5.0
AUTHORITY = "trace_transport_test_only_not_gameplay"
DELTA_COMMAND = "botauto trace all 128 delta"
PRESSURE_COUNT = 129
PRESSURE_COMMAND = f"botautotracepressure {PRESSURE_COUNT}"
GENERIC_IDENTITY_FIELDS = (
    "cohort_id", "server_epoch", "attempt_id", "profile_generation",
    "profile_content_hash", "active_profile",
)


def claim_scope() -> dict[str, Any]:
    return {
        "authority": AUTHORITY,
        "transport_admitted": None,
        "gameplay_admitted": False,
        "route_admitted": False,
        "fixture_admitted": False,
        "build_admitted": False,
        "canary_admitted": False,
        "acceptance_admitted": False,
        "boss_fidelity_admitted": False,
        "allowed_claim": (
            "ten-actor native trace transport through the production "
            "TelemetryScheduler and controller demultiplexer"
        ),
    }


def admission_rejections(
    *, profile: str, scenario: str, pool_tag: str | None,
    recurrence_supplied: bool, fixture_expansion: bool, observe_seconds: int,
) -> list[str]:
    checks = {
        "trace_transport_smoke_profile_mismatch": profile == PROFILE,
        "trace_transport_smoke_scenario_mismatch": scenario == PROFILE,
        "trace_transport_smoke_pool_tag_mismatch": pool_tag == POOL_TAG,
        "trace_transport_smoke_recurrence_admission_forbidden": not recurrence_supplied,
        "trace_transport_smoke_fixture_expansion_forbidden": not fixture_expansion,
        "trace_transport_smoke_emergency_cap_required": observe_seconds >= 30,
    }
    return [reason for reason, passed in checks.items() if not passed]


def validate_profile_assets(
    worktree: Path, reference_worktree: Path = ROOT,
) -> dict[str, Any]:
    expected = {
        "name": PROFILE,
        "target_population": ACTOR_COUNT,
        "pool_tag_filter": POOL_TAG,
        "spawn_mode": "resume_or_race_start",
        "allow_configured_center_fallback": False,
        "use_saved_position": True,
        "allow_combat": False,
        "allow_grinding": False,
        "allow_questing": False,
        "allow_dungeons": False,
        "allow_raids": False,
        "enable_progression": False,
        "record_decisions": False,
        "record_perception": False,
        "smart_sampling": False,
        "auto_start_recording": False,
        "validation_route": {"enable": False},
    }
    relative = Path("dataset/bot_runtime_profiles/profiles.json")

    def selected(root: Path) -> dict[str, Any] | None:
        try:
            rows = json.loads((root / relative).read_text(encoding="utf-8"))["profiles"]
        except (OSError, KeyError, TypeError, ValueError):
            return None
        matches = [row for row in rows if isinstance(row, dict) and row.get("name") == PROFILE]
        return matches[0] if len(matches) == 1 else None

    profile, reference = selected(worktree), selected(reference_worktree)
    reasons = []
    if profile is None:
        reasons.append("trace_transport_profile_missing_or_duplicated")
    elif any(profile.get(key) != value for key, value in expected.items()):
        reasons.append("trace_transport_profile_contract_mismatch")
    if profile != reference:
        reasons.append("trace_transport_profile_differs_from_reference")
    return {
        "profile_name": PROFILE,
        "profile_manifest": str(worktree / relative),
        "pool_tag_filter": POOL_TAG,
        "route_manifest": None,
        "route_partition": {"enabled": False, "node_count": 0},
        "profile_contract": expected,
        "reasons": reasons,
        "passed": not reasons,
    }


def _actors(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    identity = receipt.get("identity")
    rows = identity.get("actors") if isinstance(identity, dict) else None
    return rows if isinstance(rows, list) else []


def _by_guid(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {
        int(row["bot_guid"]): row for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("bot_guid"), int)
        and not isinstance(row.get("bot_guid"), bool)
        and row["bot_guid"] > 0
    }


def generic_identity(payload: dict[str, Any]) -> tuple[Any, ...] | None:
    if not all(field in payload for field in GENERIC_IDENTITY_FIELDS):
        return None
    identity = tuple(payload[field] for field in GENERIC_IDENTITY_FIELDS)
    cohort, epoch, attempt, generation, content_hash, profile = identity
    if not (
        isinstance(cohort, str) and cohort
        and isinstance(epoch, int) and not isinstance(epoch, bool) and epoch > 0
        and isinstance(attempt, int) and not isinstance(attempt, bool) and attempt > 0
        and isinstance(generation, int) and not isinstance(generation, bool)
        and generation > 0
        and isinstance(content_hash, str) and len(content_hash) == 64
        and isinstance(profile, str) and profile
    ):
        return None
    return identity


def pressure_receipt_report(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    receipts = [
        row for row in payloads
        if isinstance(row, dict) and row.get("action") == "botauto_trace_pressure"
    ]
    reasons: list[str] = []
    if len(receipts) != 1:
        reasons.append("trace_pressure_receipt_count_mismatch")
        return {
            "gate_passed": False, "rejections": reasons,
            "receipt_count": len(receipts), "receipt": receipts[0] if receipts else None,
        }
    receipt = receipts[0]
    before = receipt.get("sequence_before")
    after = receipt.get("sequence_after")
    if receipt.get("ok") is not True:
        reasons.append("trace_pressure_command_rejected")
    if receipt.get("authority") != AUTHORITY:
        reasons.append("trace_pressure_authority_mismatch")
    if generic_identity(receipt) is None or receipt.get("active_profile") != PROFILE:
        reasons.append("trace_pressure_generic_identity_invalid")
    if not (
        isinstance(receipt.get("actor_guid"), int)
        and not isinstance(receipt.get("actor_guid"), bool)
        and receipt["actor_guid"] > 0
    ):
        reasons.append("trace_pressure_actor_invalid")
    if (
        receipt.get("requested_count") != PRESSURE_COUNT
        or receipt.get("emitted_count") != PRESSURE_COUNT
    ):
        reasons.append("trace_pressure_count_mismatch")
    if not (
        isinstance(before, int) and not isinstance(before, bool) and before >= 0
        and isinstance(after, int) and not isinstance(after, bool)
        and after == before + PRESSURE_COUNT
    ):
        reasons.append("trace_pressure_sequence_receipt_invalid")
    if receipt.get("failure_reason") is not None:
        reasons.append("trace_pressure_failure_reason_present")
    return {
        "gate_passed": not reasons,
        "rejections": reasons,
        "receipt_count": len(receipts),
        "receipt": receipt,
    }


def evaluate(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    base = {
        "schema": "cata_trace_transport_smoke_gate_v1",
        **claim_scope(),
        "gate_passed": False,
        "terminal": False,
        "state": "awaiting_explicit_actor_local_gap",
        "rejections": [],
        "gap_actor_guid": None,
    }
    complete = [
        row for row in receipts
        if row.get("association_state") == "bound_in_serial_command_order"
    ]
    for index, first in enumerate(complete):
        first_rows = _actors(first)
        gaps = [row for row in first_rows if row.get("gap") is True]
        if not gaps:
            continue
        gap, reasons = gaps[0], []
        first_by_guid = _by_guid(first_rows)
        pressure = max((int(row.get("entry_count") or 0) for row in first_rows), default=0)
        scheduler = first.get("scheduler_state_after_response") or {}
        interval = (
            gap.get("missing_sequence_start"), gap.get("missing_sequence_end"),
            gap.get("oldest_retained_sequence"), gap.get("newest_retained_sequence"),
        )
        if first.get("command") != DELTA_COMMAND:
            reasons.append("gap_command_not_production_delta")
        if len(first_rows) != ACTOR_COUNT or len(first_by_guid) != ACTOR_COUNT:
            reasons.append("gap_response_actor_count_mismatch")
        if len(gaps) != 1:
            reasons.append("gap_not_actor_local")
        if pressure < PRESSURE_WATERMARK:
            reasons.append("gap_response_pressure_below_production_watermark")
        if scheduler.get("effective_trace_interval_seconds") != PRESSURE_INTERVAL_SECONDS:
            reasons.append("production_pressure_cadence_not_armed")
        if not all(isinstance(value, int) and value > 0 for value in interval):
            reasons.append("explicit_discontinuity_interval_missing")
        elif not (
            interval[0] <= interval[1] < interval[2] <= interval[3]
            and gap.get("first_sequence") == interval[2]
            and gap.get("last_sequence") == gap.get("cursor_after")
        ):
            reasons.append("explicit_discontinuity_interval_invalid")
        if index + 1 == len(complete):
            return {
                **base, "state": "awaiting_pressure_scheduled_followup",
                "gap_actor_guid": gap.get("bot_guid"), "rejections": reasons,
            }

        followup = complete[index + 1]
        second_rows, first_by_guid = _actors(followup), _by_guid(first_rows)
        second_by_guid = _by_guid(second_rows)
        if followup.get("command") != DELTA_COMMAND:
            reasons.append("followup_command_not_production_delta")
        if len(second_rows) != ACTOR_COUNT or set(second_by_guid) != set(first_by_guid):
            reasons.append("followup_actor_identity_mismatch")
        for guid, prior in first_by_guid.items():
            current = second_by_guid.get(guid)
            if current is None:
                continue
            if current.get("gap") is True:
                reasons.append(
                    "gap_actor_followup_reoverflowed"
                    if guid == gap.get("bot_guid") else "peer_actor_followup_gap"
                )
            elif current.get("cursor_before") != prior.get("cursor_after"):
                reasons.append(f"actor_cursor_not_independent_contiguous:{guid}")
            elif current.get("entry_count") and current.get("first_sequence") != int(prior["cursor_after"]) + 1:
                reasons.append(f"actor_first_sequence_not_contiguous:{guid}")
            elif current.get("entry_count") and current.get("last_sequence") != current.get("cursor_after"):
                reasons.append(f"actor_cursor_after_not_last_sequence:{guid}")
        delay = first.get("response_complete_to_next_send_seconds")
        if not isinstance(delay, (int, float)):
            reasons.append("next_command_send_timing_missing")
        elif not PRESSURE_INTERVAL_SECONDS <= delay <= PRESSURE_INTERVAL_SECONDS + 1.5:
            reasons.append("next_command_send_outside_production_poll_window")
        passed = not reasons
        return {
            **base, "transport_admitted": passed, "gate_passed": passed,
            "terminal": True, "state": "passed" if passed else "failed_verification",
            "rejections": list(dict.fromkeys(reasons)),
            "gap_command_sequence": first.get("command_sequence"),
            "followup_command_sequence": followup.get("command_sequence"),
            "gap_actor_guid": gap.get("bot_guid"), "actor_count": len(first_by_guid),
            "pressure_entries": pressure,
            "effective_trace_interval_seconds": scheduler.get("effective_trace_interval_seconds"),
            "response_complete_to_next_send_seconds": delay,
        }
    return base


def demux_report(rows: list[dict[str, Any]], gate: dict[str, Any]) -> dict[str, Any]:
    """Bind route-disabled status, diagnosis, and trace envelopes by actor."""

    payloads = [row.get("payload") for row in rows if isinstance(row.get("payload"), dict)]
    statuses = [row for row in payloads if row.get("action") == "botauto_status" and row.get("active") is True]
    diagnoses = [row for row in payloads if row.get("action") == "botauto_diagnose"]
    traces = [row for row in payloads if row.get("action") == "botauto_trace"]
    reasons = []
    pressure = pressure_receipt_report(payloads)
    reasons.extend(pressure["rejections"])
    non_gameplay = ("kills", "deaths", "quests_accepted", "quests_completed", "raid_boss_kills")
    for status in statuses:
        route = status.get("validation_route") or {}
        if not (
            status.get("active_profile") == PROFILE
            and status.get("cohort_id") == "default"
            and status.get("pool_tag_filter") == POOL_TAG
            and status.get("bots") == ACTOR_COUNT
            and status.get("lease_count") == ACTOR_COUNT
            and route.get("enabled") is False
            and all(int(status.get(field) or 0) == 0 for field in non_gameplay)
        ):
            reasons.append("route_disabled_status_identity_mismatch")
    canonical_sets = []
    for row in diagnoses:
        guids = {
            bot["identity"]["bot_guid"] for bot in row.get("bots", [])
            if isinstance(bot, dict) and isinstance(bot.get("identity"), dict)
            and isinstance(bot["identity"].get("bot_guid"), int)
            and bot["identity"]["bot_guid"] > 0
        }
        canonical_sets.append(guids)
    if not statuses:
        reasons.append("active_status_missing")
    status_identities = [generic_identity(status) for status in statuses]
    if not status_identities or any(identity is None for identity in status_identities):
        reasons.append("generic_status_identity_invalid")
    elif len(set(status_identities)) != 1:
        reasons.append("generic_status_identity_changed")
    canonical_generic_identity = status_identities[0] if status_identities else None
    if not canonical_sets or any(len(guids) != ACTOR_COUNT for guids in canonical_sets):
        reasons.append("diagnosis_actor_identity_mismatch")
    canonical = canonical_sets[0] if canonical_sets else set()
    actor_total = actor_rejected = 0
    for trace in traces:
        actors = _by_guid(trace.get("bots") if isinstance(trace.get("bots"), list) else [])
        actor_total += len(actors)
        if set(actors) != canonical or trace.get("cohort_id") != "default":
            reasons.append("trace_actor_envelope_identity_mismatch")
        if generic_identity(trace) != canonical_generic_identity:
            reasons.append("trace_generic_identity_mismatch")
        actor_rejected += sum(row.get("gap") is True for row in actors.values())
    pressure_receipt = pressure.get("receipt")
    if isinstance(pressure_receipt, dict):
        if generic_identity(pressure_receipt) != canonical_generic_identity:
            reasons.append("trace_pressure_identity_mismatch")
        if pressure_receipt.get("actor_guid") not in canonical:
            reasons.append("trace_pressure_actor_not_in_canonical_cohort")
    if actor_rejected != 1:
        reasons.append("actor_local_rejection_count_mismatch")
    if gate.get("gate_passed") is not True:
        reasons.append("transport_gate_not_passed")
    return {
        "gate_passed": not reasons,
        "rejections": list(dict.fromkeys(reasons)),
        "actor_binding_counts": {
            "total": actor_total, "bound": actor_total - actor_rejected,
            "rejected": actor_rejected, "unchecked": 0,
        },
        "expected_gap_actor_guid": gate.get("gap_actor_guid"),
        "pressure_receipt": pressure,
        "native_gap_remains_rejected": actor_rejected == 1,
        "peer_and_followup_rows_bound": not reasons,
    }
