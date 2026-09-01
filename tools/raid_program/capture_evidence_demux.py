from __future__ import annotations

from collections import Counter
from typing import Any, Callable

try:
    from tools.raid_program.capture_runtime_identity import (
        STRATEGY_FIELD,
        _roster_binding_identity,
        _roster_binding_lifecycle_rejections,
        _route_advancement_marker,
        _runtime_identity,
    )
    from tools.raid_program.capture_value_types import (
        _canonical_object_sha256,
        _nonnegative_int,
        _positive_int,
        _uint64_int,
    )
    from tools.raid_program.capture_watchdog import _CONTROLLER_TERMINAL_FAILURE_REASONS
    from tools.raid_program.capture_fixture_evidence_binding import (
        MAGMAW_TRANSFER_CHECKPOINT_ACTION,
        fixture_terminal_binding,
    )
except ModuleNotFoundError:
    from capture_runtime_identity import (
        STRATEGY_FIELD,
        _roster_binding_identity,
        _roster_binding_lifecycle_rejections,
        _route_advancement_marker,
        _runtime_identity,
    )
    from capture_value_types import (
        _canonical_object_sha256,
        _nonnegative_int,
        _positive_int,
        _uint64_int,
    )
    from capture_watchdog import _CONTROLLER_TERMINAL_FAILURE_REASONS
    from capture_fixture_evidence_binding import (
        MAGMAW_TRANSFER_CHECKPOINT_ACTION,
        fixture_terminal_binding,
    )


def _controller_terminal_binding(
    controller_terminal: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    *,
    canonical_identity: tuple[Any, ...],
    canonical_roster: tuple[tuple[Any, ...], ...],
    canonical_cohort: str,
    profile_name: str,
) -> tuple[bool, list[str]]:
    """Validate controller-owned terminal evidence before waiving ready-check.

    Semantic stalls and watchdog thresholds are capture-controller decisions,
    not native status failure reasons.  They may skip the ready-check only when
    the controller retained the exact active status that triggered the edge and
    its forced diagnosis/trace bundle passed.  This keeps the exception bound
    to the same attempt and prevents a caller-provided terminal label from
    weakening the ordinary demux gates.
    """

    if controller_terminal is None:
        return False, []
    reasons: list[str] = []
    if not isinstance(controller_terminal, dict):
        return False, ["evidence_demux_controller_terminal_invalid"]
    if controller_terminal.get("detected") is not True:
        reasons.append("evidence_demux_controller_terminal_not_detected")
    if controller_terminal.get("classification") != "gameplay_failure":
        reasons.append("evidence_demux_controller_terminal_classification_invalid")
    if controller_terminal.get("failure_reason") not in _CONTROLLER_TERMINAL_FAILURE_REASONS:
        reasons.append("evidence_demux_controller_terminal_reason_invalid")
    if controller_terminal.get("final_forced_evidence") is not True:
        reasons.append("evidence_demux_controller_terminal_forced_evidence_missing")

    terminal_status = controller_terminal.get("terminal_status")
    if not isinstance(terminal_status, dict):
        reasons.append("evidence_demux_controller_terminal_status_missing")
        return False, reasons
    if terminal_status.get("ok") is not True:
        reasons.append("evidence_demux_controller_terminal_status_not_ok")
    if terminal_status.get("action") != "botauto_status":
        reasons.append("evidence_demux_controller_terminal_status_action_invalid")
    if terminal_status.get("cohort_id") != canonical_cohort:
        reasons.append("evidence_demux_controller_terminal_cohort_mismatch")
    if terminal_status.get("active_profile") != profile_name:
        reasons.append("evidence_demux_controller_terminal_profile_mismatch")
    runtime = terminal_status.get("raid_runtime")
    roster = runtime.get("roster") if isinstance(runtime, dict) else None
    if not isinstance(runtime, dict) or runtime.get("active") is not True:
        reasons.append("evidence_demux_controller_terminal_runtime_inactive")
    if not isinstance(runtime, dict) or _runtime_identity(runtime, include_strategy=False) != canonical_identity:
        reasons.append("evidence_demux_controller_terminal_attempt_mismatch")
    if not isinstance(roster, list) or _roster_binding_identity(roster) != canonical_roster:
        reasons.append("evidence_demux_controller_terminal_roster_mismatch")
    if terminal_status.get("bots") != len(canonical_roster):
        reasons.append("evidence_demux_controller_terminal_bot_count_mismatch")
    if terminal_status.get("lease_count") != len(canonical_roster):
        reasons.append("evidence_demux_controller_terminal_lease_count_mismatch")

    # The context is only admissible if its exact trigger status was retained
    # in the immutable batch.  Equal identity alone is insufficient: it could
    # otherwise waive ready-check for an unobserved or stale controller edge.
    if not any(
        isinstance(row.get("payload"), dict)
        and row.get("payload") == terminal_status
        and row.get("payload", {}).get("action") == "botauto_status"
        for row in rows
    ):
        reasons.append("evidence_demux_controller_terminal_status_unretained")
    return not reasons, list(dict.fromkeys(reasons))


def normalized_batch_payload(
    log_bytes: bytes,
    *,
    profile_name: str,
    json_row_parser: Callable[[bytes], list[dict[str, Any]]],
    evidence_reporter: Callable[..., dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return an immutable, replayable JSONL representation of parsed evidence."""

    channel_by_action = {
        "botauto_controller_route_hold": "controller_protocol",
        "botauto_chainwielder_checkpoint": "controller_protocol",
        MAGMAW_TRANSFER_CHECKPOINT_ACTION: "controller_protocol",
        "botauto_status": "status",
        "botauto_diagnose": "diagnosis",
        "botauto_trace": "trace",
        "botauto_combatlog_chunk": "combat_log",
        "botauto_combatlog_complete": "combat_log",
        "botauto_profile": "profile_selection",
        "botauto_readycheck": "native_action",
        "botauto_stop": "cleanup",
    }
    parsed_rows: list[dict[str, Any]] = []
    for raw_row in json_row_parser(log_bytes):
        row = dict(raw_row)
        if (
            row.get("action") is None
            and "phase" in row
            and "acquire_count" in row
            and "route_manifest_sha256" in row
        ):
            row["action"] = "botauto_controller_route_hold"
            row["native_action_inferred_from_exact_shape"] = True
        parsed_rows.append(row)
    rows = [
        {
            "normalized_schema_version": 2,
            "capture_sequence": sequence,
            "action": row.get("action"),
            "evidence_channel": channel_by_action.get(str(row.get("action")), "other"),
            "payload": row,
        }
        for sequence, row in enumerate(parsed_rows, start=1)
    ]
    # Populate diagnostic bindings for the immutable batch, but never trust
    # them during acceptance: evidence_demux_report reconstructs and replaces
    # every binding from the retained payload on every call.
    evidence_reporter(rows, profile_name=profile_name)
    return rows


def _trace_actor_transport_rejections(
    bot_row: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    """Classify one native trace actor without widening a gap to its envelope.

    Delta cursors are per bot in the worldserver.  A ring overwrite for one
    busy actor therefore says nothing about the nine peers serialized beside
    it.  Keep the actor's exact cursor/sequence facts independently checkable;
    callers still reject a real gap globally, but they can retain the peer
    rows and later bounded snapshots as truthful evidence.
    """

    reasons: list[str] = []
    entries = bot_row.get("entries")
    if not isinstance(entries, list):
        return ["evidence_demux_trace_entries_invalid"], {
            "mode": "invalid",
            "cursor_before": bot_row.get("cursor_before"),
            "cursor_after": bot_row.get("cursor_after"),
            "sequence_first": None,
            "sequence_last": None,
            "entry_count": 0,
        }

    sequences: list[int] = []
    for entry in entries:
        if not isinstance(entry, dict) or not _positive_int(entry.get("sequence")):
            reasons.append("evidence_demux_trace_entry_sequence_invalid")
            continue
        sequences.append(int(entry["sequence"]))
    if len(sequences) != len(entries):
        reasons.append("evidence_demux_trace_entry_count_invalid")
    delta = bot_row.get("delta") is True
    expected_step = 1 if delta else -1
    if any(
        current != previous + expected_step
        for previous, current in zip(sequences, sequences[1:])
    ):
        reasons.append("evidence_demux_trace_entry_sequence_gap")
    observation = {
        "mode": "delta" if delta else "bounded_full_snapshot",
        "cursor_before": bot_row.get("cursor_before") if delta else None,
        "cursor_after": bot_row.get("cursor_after") if delta else None,
        "sequence_first": min(sequences) if sequences else None,
        "sequence_last": max(sequences) if sequences else None,
        "entry_count": len(entries),
    }
    if not delta:
        return list(dict.fromkeys(reasons)), observation

    cursor_before = bot_row.get("cursor_before")
    cursor_after = bot_row.get("cursor_after")
    gap = bot_row.get("gap")
    # Historical normalized fixtures predate cursor serialization.  Retain
    # their compatibility while requiring every current live cursor pair to
    # be internally coherent when present.
    if not _uint64_int(cursor_before) or not _uint64_int(cursor_after):
        if gap is True:
            reasons.append("evidence_demux_trace_delta_gap")
        elif any(field in bot_row for field in ("cursor_before", "cursor_after")):
            reasons.append("evidence_demux_trace_delta_cursor_invalid")
        return list(dict.fromkeys(reasons)), observation
    if not isinstance(gap, bool):
        reasons.append("evidence_demux_trace_delta_gap_flag_invalid")
        return list(dict.fromkeys(reasons)), observation
    if gap:
        discontinuity = bot_row.get("discontinuity")
        if discontinuity is None:
            if entries or cursor_after != cursor_before:
                reasons.append("evidence_demux_trace_delta_gap_shape_invalid")
            if int(cursor_before) < (1 << 64) - 1:
                observation["missing_sequence_start"] = int(cursor_before) + 1
        else:
            fields = (
                "missing_sequence_start",
                "missing_sequence_end",
                "oldest_retained_sequence",
                "newest_retained_sequence",
            )
            valid = isinstance(discontinuity, dict) and all(
                _uint64_int(discontinuity.get(field)) for field in fields
            )
            if valid:
                missing_start = int(discontinuity["missing_sequence_start"])
                missing_end = int(discontinuity["missing_sequence_end"])
                oldest_retained = int(discontinuity["oldest_retained_sequence"])
                newest_retained = int(discontinuity["newest_retained_sequence"])
                valid = (
                    int(cursor_before) < (1 << 64) - 1
                    and missing_start == int(cursor_before) + 1
                    and missing_start <= missing_end
                    and missing_end < (1 << 64) - 1
                    and oldest_retained == missing_end + 1
                    and oldest_retained <= newest_retained
                    and bool(sequences)
                    and sequences[0] == oldest_retained
                    and sequences[-1] <= newest_retained
                    and int(cursor_after) == sequences[-1]
                )
            if not valid:
                reasons.append("evidence_demux_trace_delta_discontinuity_invalid")
                reasons.append("evidence_demux_trace_delta_gap_shape_invalid")
            else:
                observation.update({
                    "discontinuity_explicit": True,
                    "missing_sequence_start": missing_start,
                    "missing_sequence_end": missing_end,
                    "oldest_retained_sequence": oldest_retained,
                    "newest_retained_sequence": newest_retained,
                })
        reasons.append("evidence_demux_trace_delta_gap")
        return list(dict.fromkeys(reasons)), observation

    expected_first = int(cursor_before) + 1
    if sequences and sequences[0] != expected_first:
        reasons.append("evidence_demux_trace_delta_first_sequence_invalid")
    expected_after = sequences[-1] if sequences else int(cursor_before)
    if int(cursor_after) != expected_after:
        reasons.append("evidence_demux_trace_delta_cursor_after_invalid")
    return list(dict.fromkeys(reasons)), observation


def _required_telemetry_envelope_report(
    rows: list[dict[str, Any]], *, profile_name: str = "blackwing_descent_10n",
) -> dict[str, Any]:
    """Validate the complete canonical bot roster in every diagnose/trace row.

    Status rows establish the canonical live runtime.  Diagnose and trace are
    independent retained evidence channels, so a non-empty channel alone is
    insufficient: every one of their envelopes must bind to that runtime and
    enumerate each canonical bot exactly once.
    """

    canonical_identity: tuple[Any, ...] | None = None
    canonical_roster: tuple[tuple[Any, ...], ...] | None = None
    canonical_cohort: str | None = None
    canonical_guids: set[int] | None = None
    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict) or payload.get("action") != "botauto_status":
            continue
        runtime = payload.get("raid_runtime")
        roster = runtime.get("roster") if isinstance(runtime, dict) else None
        identity = _runtime_identity(runtime, include_strategy=False) if isinstance(runtime, dict) else None
        roster_identity = _roster_binding_identity(roster) if isinstance(roster, list) else None
        cohort = payload.get("cohort_id")
        if not isinstance(runtime, dict) or runtime.get("active") is not True:
            continue
        if identity is None or roster_identity is None or not isinstance(cohort, str) or not cohort:
            continue
        guids = [member[3] for member in roster_identity]
        if not all(_positive_int(guid) for guid in guids) or len(set(guids)) != 10:
            continue
        canonical_identity = identity
        canonical_roster = roster_identity
        canonical_cohort = cohort
        canonical_guids = {int(guid) for guid in guids}
        break

    row_rejections: dict[int, list[str]] = {}
    actor_rejections: dict[int, dict[int, list[str]]] = {}
    actor_bindings: list[dict[str, Any]] = []
    trace_discontinuities: list[dict[str, Any]] = []
    active_trace_discontinuity_by_guid: dict[int, dict[str, Any]] = {}
    channel_counts = {"diagnosis": 0, "trace": 0}
    if canonical_identity is None or canonical_roster is None or canonical_cohort is None or canonical_guids is None:
        return {
            "rejections": ["evidence_demux_telemetry_canonical_runtime_missing"],
            "row_rejections": row_rejections,
            "actor_rejections": actor_rejections,
            "actor_binding_counts": {
                "total": 0, "bound": 0, "rejected": 0, "unchecked": 0,
            },
            "trace_discontinuities": trace_discontinuities,
            "diagnosis_envelopes": 0,
            "trace_envelopes": 0,
            "gate_passed": False,
        }
    canonical_roster_sha256 = _canonical_object_sha256(canonical_roster)
    canonical_identity_sha256 = _canonical_object_sha256(
        {
            "cohort_id": canonical_cohort,
            "runtime_identity": canonical_identity,
            "roster_sha256": canonical_roster_sha256,
        }
    )

    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        action = payload.get("action")
        channel = {"botauto_diagnose": "diagnosis", "botauto_trace": "trace"}.get(action)
        if channel is None:
            continue
        channel_counts[channel] += 1
        row_reasons: list[str] = []
        if payload.get("ok") is not True:
            row_reasons.append(f"evidence_demux_{channel}_envelope_not_ok")
        runtime = payload.get("raid_runtime")
        roster = runtime.get("roster") if isinstance(runtime, dict) else None
        if (
            not isinstance(runtime, dict)
            or runtime.get("active") is not True
            or _runtime_identity(runtime, include_strategy=False) != canonical_identity
            or (_roster_binding_identity(roster) if isinstance(roster, list) else None) != canonical_roster
            or payload.get("cohort_id") != canonical_cohort
        ):
            row_reasons.append(f"evidence_demux_{channel}_runtime_identity_unbound")
        row_reasons.extend(
            f"evidence_demux_{channel}_{reason}"
            for reason in _roster_binding_lifecycle_rejections(roster)
        )

        bot_rows = payload.get("bots")
        if not isinstance(bot_rows, list):
            row_reasons.append(f"evidence_demux_{channel}_bot_rows_missing")
        elif not bot_rows:
            row_reasons.append(f"evidence_demux_{channel}_roster_empty")
        else:
            bot_guids: list[int] = []
            for bot_row in bot_rows:
                if not isinstance(bot_row, dict):
                    row_reasons.append(f"evidence_demux_{channel}_bot_row_invalid")
                    continue
                bot_guid = bot_row.get("bot_guid")
                identity_object = bot_row.get("identity")
                if isinstance(identity_object, dict):
                    bot_guid = identity_object.get("bot_guid")
                if not _positive_int(bot_guid):
                    row_reasons.append(f"evidence_demux_{channel}_bot_guid_invalid")
                    continue
                guid = int(bot_guid)
                bot_guids.append(guid)
                binding = {
                    "state": "rejected",
                    "scope": "telemetry_actor",
                    "binding_source": "retained_payload_reconstruction",
                    "canonical_identity_sha256": canonical_identity_sha256,
                    "roster_sha256": canonical_roster_sha256,
                    "correlation": {
                        "capture_sequence": int(row.get("capture_sequence") or 0),
                        "telemetry_channel": channel,
                        "bot_guid": guid,
                        "scenario": profile_name,
                        "cohort_id": canonical_cohort,
                        "server_epoch": canonical_identity[9],
                        "attempt_id": canonical_identity[10],
                        "runtime_profile_generation": canonical_identity[11],
                        "runtime_profile_hash": canonical_identity[12],
                        "assignment_generation": canonical_identity[13],
                        "route_generation": (
                            (runtime.get("route_progress") or {}).get("generation")
                            if isinstance(runtime.get("route_progress"), dict)
                            else None
                        ),
                        "wipe_generation": runtime.get("wipe_generation"),
                    },
                    "reasons": [],
                }
                bot_row["identity_binding"] = binding
                actor_bindings.append(binding)
                actor_reasons: list[str] = []
                if guid not in canonical_guids:
                    actor_reasons.append(f"evidence_demux_{channel}_bot_outside_roster")
                if channel == "trace":
                    transport_reasons, transport = _trace_actor_transport_rejections(bot_row)
                    actor_reasons.extend(transport_reasons)
                    binding["trace_transport"] = transport
                    if "evidence_demux_trace_delta_gap" in transport_reasons:
                        cursor_before = transport.get("cursor_before")
                        if not _nonnegative_int(cursor_before):
                            # A legacy fixture can still prove a gap rejection,
                            # but cannot manufacture a discontinuity interval.
                            cursor_before = None
                        if cursor_before is None:
                            cursor = None
                        else:
                            cursor = int(cursor_before)
                        if (
                            cursor is not None
                            and transport.get("discontinuity_explicit") is True
                        ):
                            capture_sequence = int(row.get("capture_sequence") or 0)
                            epoch = {
                                "epoch_id": (
                                    f"trace_discontinuity:{guid}:"
                                    f"{transport['missing_sequence_start']}:"
                                    f"{capture_sequence}"
                                ),
                                "bot_guid": guid,
                                "cursor_before": cursor,
                                "missing_sequence_start": transport["missing_sequence_start"],
                                "missing_sequence_end": transport["missing_sequence_end"],
                                "oldest_retained_sequence": transport["oldest_retained_sequence"],
                                "newest_retained_sequence": transport["newest_retained_sequence"],
                                "first_gap_capture_sequence": capture_sequence,
                                "last_gap_capture_sequence": capture_sequence,
                                "gap_envelope_count": 1,
                                "first_recovered_capture_sequence": capture_sequence,
                                "first_recovered_sequence": transport["sequence_first"],
                                "classification": (
                                    "explicit_native_discontinuity_retained_suffix_resumed_"
                                    "missing_interval_rejected"
                                ),
                                "gate_passed": False,
                            }
                            transport["discontinuity_epoch_id"] = epoch["epoch_id"]
                            trace_discontinuities.append(epoch)
                            active_trace_discontinuity_by_guid.pop(guid, None)
                            cursor = None
                        epoch = active_trace_discontinuity_by_guid.get(guid)
                        if cursor is not None and (
                            epoch is None or epoch["cursor_before"] != cursor
                        ):
                            epoch = {
                                "epoch_id": (
                                    f"trace_discontinuity:{guid}:"
                                    f"{cursor + 1}:{int(row.get('capture_sequence') or 0)}"
                                ),
                                "bot_guid": guid,
                                "cursor_before": cursor,
                                "missing_sequence_start": cursor + 1,
                                "missing_sequence_end": None,
                                "first_gap_capture_sequence": int(
                                    row.get("capture_sequence") or 0
                                ),
                                "last_gap_capture_sequence": int(
                                    row.get("capture_sequence") or 0
                                ),
                                "gap_envelope_count": 0,
                                "first_recovered_capture_sequence": None,
                                "first_recovered_sequence": None,
                                "classification": "unresolved_trace_delta_gap",
                                "gate_passed": False,
                            }
                            active_trace_discontinuity_by_guid[guid] = epoch
                            trace_discontinuities.append(epoch)
                        if cursor is not None and epoch is not None:
                            epoch["last_gap_capture_sequence"] = int(
                                row.get("capture_sequence") or 0
                            )
                            epoch["gap_envelope_count"] += 1
                            transport["discontinuity_epoch_id"] = epoch["epoch_id"]
                    else:
                        epoch = active_trace_discontinuity_by_guid.get(guid)
                        first_sequence = transport.get("sequence_first")
                        if epoch is not None and _positive_int(first_sequence):
                            epoch["missing_sequence_end"] = int(first_sequence) - 1
                            epoch["first_recovered_capture_sequence"] = int(
                                row.get("capture_sequence") or 0
                            )
                            epoch["first_recovered_sequence"] = int(first_sequence)
                            epoch["classification"] = (
                                "closed_by_bounded_snapshot_missing_interval_rejected"
                            )
                            transport["follows_discontinuity_epoch_id"] = epoch["epoch_id"]
                            del active_trace_discontinuity_by_guid[guid]
                if actor_reasons:
                    unique_actor_reasons = list(dict.fromkeys(actor_reasons))
                    binding["reasons"] = unique_actor_reasons
                    actor_rejections.setdefault(
                        int(row.get("capture_sequence") or 0), {}
                    )[guid] = unique_actor_reasons
                else:
                    binding["state"] = "bound"
            counts = Counter(bot_guids)
            if any(count > 1 for count in counts.values()):
                row_reasons.append(f"evidence_demux_{channel}_duplicate_bot_guid")
            if any(guid not in canonical_guids for guid in counts):
                row_reasons.append(f"evidence_demux_{channel}_bot_outside_roster")
            if set(bot_guids) != canonical_guids:
                row_reasons.append(f"evidence_demux_{channel}_canonical_roster_incomplete")
            if len(bot_guids) != 10:
                row_reasons.append(f"evidence_demux_{channel}_bot_row_count_invalid")
            if row_reasons:
                # Runtime/roster envelope faults invalidate every actor join;
                # an actor-local gap alone never enters row_reasons and thus
                # remains scoped to only the affected bot.
                for bot_row in bot_rows:
                    if not isinstance(bot_row, dict):
                        continue
                    binding = bot_row.get("identity_binding")
                    if not isinstance(binding, dict):
                        continue
                    guid = (binding.get("correlation") or {}).get("bot_guid")
                    if not _positive_int(guid):
                        continue
                    combined = list(dict.fromkeys(
                        list(binding.get("reasons") or []) + row_reasons
                    ))
                    binding["state"] = "rejected"
                    binding["reasons"] = combined
                    actor_rejections.setdefault(
                        int(row.get("capture_sequence") or 0), {}
                    )[int(guid)] = combined
        if row_reasons:
            row_rejections[int(row.get("capture_sequence") or 0)] = list(dict.fromkeys(row_reasons))

    rejections = [
        reason
        for reasons in row_rejections.values()
        for reason in reasons
    ]
    rejections.extend(
        reason
        for by_guid in actor_rejections.values()
        for reasons in by_guid.values()
        for reason in reasons
    )
    for channel, count in channel_counts.items():
        if count == 0:
            rejections.append(f"evidence_demux_{channel}_roster_envelope_missing")
    unique_rejections = list(dict.fromkeys(rejections))
    actor_states = Counter(str(binding.get("state", "unchecked")) for binding in actor_bindings)
    unchecked_actors = (
        len(actor_bindings)
        - actor_states.get("bound", 0)
        - actor_states.get("rejected", 0)
    )
    return {
        "rejections": unique_rejections,
        "row_rejections": row_rejections,
        "actor_rejections": actor_rejections,
        "actor_binding_counts": {
            "total": len(actor_bindings),
            "bound": actor_states.get("bound", 0),
            "rejected": actor_states.get("rejected", 0),
            "unchecked": unchecked_actors,
        },
        "trace_discontinuities": trace_discontinuities,
        "diagnosis_envelopes": channel_counts["diagnosis"],
        "trace_envelopes": channel_counts["trace"],
        "gate_passed": not unique_rejections,
    }


def evidence_demux_report(
    rows: list[dict[str, Any]],
    *,
    profile_name: str,
    controller_terminal: dict[str, Any] | None,
    terminal_failure_validator: Callable[..., tuple[str | None, list[str]]],
    fixture_terminal: dict[str, Any] | None = None,
    fixture_expected_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Independently bind every retained JSON row to one raid lifecycle."""

    reasons: list[str] = []
    known_actions = {
        "botauto_profile", "botauto_status", "botauto_diagnose", "botauto_trace",
        "botauto_combatlog_chunk", "botauto_combatlog_complete",
        "botauto_readycheck", "botauto_stop",
        "botauto_controller_route_hold", "botauto_chainwielder_checkpoint",
        MAGMAW_TRANSFER_CHECKPOINT_ACTION,
    }
    canonical_identity: tuple[Any, ...] | None = None
    canonical_roster: tuple[tuple[Any, ...], ...] | None = None
    canonical_cohort: str | None = None
    roster_guids: set[int] = set()
    canonical_identity_sha256: str | None = None
    canonical_roster_sha256: str | None = None
    canonical_active_sequence: int | None = None

    for row in rows:
        # An outer annotation is evidence output, not evidence input.  Replace
        # it before reconstructing so a forged binding can never self-certify.
        row["identity_binding"] = {
            "state": "rejected",
            "scope": "unknown",
            "canonical_identity_sha256": None,
            "cohort_id": None,
            "roster_sha256": None,
            "binding_source": "retained_payload_reconstruction",
            "reasons": [],
        }

    # First establish canonical identity only from a complete active status.
    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict) or payload.get("action") != "botauto_status":
            continue
        runtime = payload.get("raid_runtime")
        if not isinstance(runtime, dict) or runtime.get("active") is not True:
            continue
        identity = _runtime_identity(runtime, include_strategy=False)
        roster = runtime.get("roster")
        roster_identity = _roster_binding_identity(roster) if isinstance(roster, list) else None
        cohort = payload.get("cohort_id")
        roster_guid_values = (
            [member[3] for member in roster_identity]
            if roster_identity is not None else []
        )
        if (
            identity is not None
            and roster_identity is not None
            and all(_positive_int(guid) for guid in roster_guid_values)
            and len(set(roster_guid_values)) == 10
            and isinstance(cohort, str)
            and cohort
        ):
            canonical_identity = identity
            canonical_roster = roster_identity
            canonical_cohort = cohort
            canonical_active_sequence = row.get("capture_sequence")
            roster_guids = {int(member[3]) for member in roster_identity if _positive_int(member[3])}
            canonical_roster_sha256 = _canonical_object_sha256(roster_identity)
            canonical_identity_sha256 = _canonical_object_sha256(
                {
                    "cohort_id": canonical_cohort,
                    "runtime_identity": canonical_identity,
                    "roster_sha256": canonical_roster_sha256,
                }
            )
            break
    if canonical_identity is None:
        telemetry_envelopes = _required_telemetry_envelope_report(
            rows, profile_name=profile_name,
        )
        for row in rows:
            row["identity_binding"]["reasons"] = ["evidence_demux_no_active_raid_rows"]
        return {
            "rejections": ["evidence_demux_no_active_raid_rows"],
            "retained_rows": len(rows),
            "bound_rows": 0,
            "rejected_rows": len(rows),
            "unchecked_rows": 0,
            "canonical_identity_sha256": None,
            "canonical_roster_sha256": None,
            "required_telemetry_envelopes": telemetry_envelopes,
            "actor_binding_counts": telemetry_envelopes["actor_binding_counts"],
            "trace_discontinuities": telemetry_envelopes["trace_discontinuities"],
            "gate_passed": False,
        }

    telemetry_envelopes = _required_telemetry_envelope_report(
        rows, profile_name=profile_name,
    )
    controller_terminal_bound, controller_terminal_rejections = _controller_terminal_binding(
        controller_terminal,
        rows,
        canonical_identity=canonical_identity,
        canonical_roster=canonical_roster,
        canonical_cohort=canonical_cohort,
        profile_name=profile_name,
    )
    reasons.extend(controller_terminal_rejections)
    fixture_terminal_bound, fixture_terminal_rejections, fixture_row_rejections = (
        fixture_terminal_binding(
            fixture_terminal,
            rows,
            canonical_identity=canonical_identity,
            canonical_roster_guids=roster_guids,
            canonical_cohort=canonical_cohort,
            canonical_active_sequence=int(canonical_active_sequence),
            profile_name=profile_name,
            expected_identity=fixture_expected_identity,
        )
    )
    reasons.extend(fixture_terminal_rejections)
    stop_seen = False
    inactive_cleanup_seen = False
    observed_actions: set[str] = set()
    previous_strategy: str | None = None
    previous_route_advance = 0
    profile_selection_seen = False
    terminal_failure_seen = False
    for expected_sequence, row in enumerate(rows, start=1):
        binding = row["identity_binding"]
        binding.update(
            canonical_identity_sha256=canonical_identity_sha256,
            cohort_id=canonical_cohort,
            roster_sha256=canonical_roster_sha256,
        )
        row_reasons: list[str] = binding["reasons"]

        def reject(reason: str) -> None:
            row_reasons.append(reason)
            reasons.append(reason)

        payload = row.get("payload")
        if not isinstance(payload, dict):
            reject("evidence_demux_payload_missing")
            continue
        action = payload.get("action")
        if row.get("capture_sequence") != expected_sequence:
            reject("evidence_demux_sequence_invalid")
        if row.get("action") != action:
            reject("evidence_demux_wrapper_action_mismatch")
        if action not in known_actions:
            reject("evidence_demux_unclassified_row")
            continue
        observed_actions.add(str(action))

        if action == "botauto_status":
            terminal_reason, _ = terminal_failure_validator(
                payload, profile_name=profile_name,
            )
            terminal_failure_seen = terminal_failure_seen or terminal_reason is not None

        if action == "botauto_profile":
            binding["scope"] = "pre_start_profile"
            if canonical_cohort != "default" or payload.get("cohort_id") != canonical_cohort:
                reject("evidence_demux_profile_cohort_mismatch")
            if payload.get("ok") is not True or payload.get("active_profile") != profile_name:
                reject("evidence_demux_profile_selection_invalid")
            if profile_selection_seen:
                reject("evidence_demux_duplicate_profile_selection")
            if (not isinstance(canonical_active_sequence, int)
                    or expected_sequence >= canonical_active_sequence):
                reject("evidence_demux_profile_selection_not_before_active_status")
            profile_selection_seen = True
            if not row_reasons:
                binding["state"] = "bound"
            continue

        if action == MAGMAW_TRANSFER_CHECKPOINT_ACTION:
            binding["scope"] = "fixture_checkpoint"
            if stop_seen:
                reject("evidence_demux_fixture_checkpoint_after_cleanup")
            for reason in fixture_row_rejections.get(expected_sequence, []):
                reject(reason)
            if not fixture_terminal_bound and not row_reasons:
                reject("evidence_demux_fixture_terminal_unbound")
            if not row_reasons:
                binding["state"] = "bound"
            continue

        if action in {
            "botauto_controller_route_hold",
            "botauto_chainwielder_checkpoint",
        }:
            binding["scope"] = "controller_protocol"
            if stop_seen:
                reject("evidence_demux_controller_protocol_after_stop")
            hold = (
                payload if action == "botauto_controller_route_hold"
                else payload.get("controller_route_hold")
            )
            if not isinstance(hold, dict):
                reject("evidence_demux_controller_hold_missing")
                continue
            if payload.get("ok") is not True or hold.get("ok") is not True:
                reject("evidence_demux_controller_hold_not_ok")
            if (
                hold.get("cohort_id") != canonical_cohort
                or hold.get("server_epoch") != canonical_identity[9]
                or hold.get("attempt_id") != canonical_identity[10]
                or hold.get("runtime_profile") != profile_name
            ):
                reject("evidence_demux_controller_hold_cross_identity")
            if action == "botauto_controller_route_hold":
                if payload.get("native_action_inferred_from_exact_shape") is not True:
                    reject("evidence_demux_controller_hold_action_not_reconstructed")
                if hold.get("phase") not in {"held", "released"}:
                    reject("evidence_demux_controller_hold_phase_invalid")
            else:
                if (
                    payload.get("cohort_id") != canonical_cohort
                    or payload.get("server_epoch") != canonical_identity[9]
                    or payload.get("attempt_id") != canonical_identity[10]
                    or payload.get("active_profile") != profile_name
                    or hold.get("phase") != "armed"
                    or hold.get("arm_ack_count") != 1
                ):
                    reject("evidence_demux_controller_arm_identity_invalid")
            if not row_reasons:
                binding["state"] = "bound"
            continue

        if action in {
            "botauto_combatlog_chunk", "botauto_combatlog_complete",
        }:
            binding["scope"] = "active_runtime"
            if stop_seen:
                reject("evidence_demux_active_row_after_stop")
            if payload.get("ok") is not True:
                reject("evidence_demux_combat_log_not_ok")
            if payload.get("cohort_id") != canonical_cohort:
                reject("evidence_demux_cross_identity_row")
            if payload.get("combat_log_chunk_schema_version") != 1:
                reject("evidence_demux_combat_log_schema_invalid")
            if action == "botauto_combatlog_chunk" and (
                not isinstance(payload.get("sequence"), int)
                or int(payload.get("chunk_count") or 0) <= 0
                or payload.get("encoding") != "base64"
                or not isinstance(payload.get("data"), str)
                or not payload.get("data")
            ):
                reject("evidence_demux_combat_log_chunk_invalid")
            if action == "botauto_combatlog_complete" and (
                int(payload.get("chunk_count") or 0) <= 0
                or int(payload.get("total_bytes") or 0) <= 0
            ):
                reject("evidence_demux_combat_log_complete_invalid")
            if not row_reasons:
                binding["state"] = "bound"
            continue

        runtime_key = "raid_runtime_before_cleanup" if action == "botauto_stop" else "raid_runtime"
        runtime = payload.get(runtime_key)
        if action == "botauto_status" and isinstance(runtime, dict) and runtime.get("active") is False:
            binding["scope"] = "post_cleanup"
            if not stop_seen:
                reject("evidence_demux_inactive_status_before_stop")
            if payload.get("cohort_id") != canonical_cohort:
                reject("evidence_demux_cross_identity_row")
            if payload.get("bots") != 0 or payload.get("lease_count") != 0:
                reject("evidence_demux_cleanup_not_empty")
            if (
                payload.get("server_epoch") != canonical_identity[9]
                or payload.get("attempt_id") != canonical_identity[10]
                or _runtime_identity(runtime, include_strategy=False) != canonical_identity
            ):
                reject("evidence_demux_cross_identity_row")
            inactive_cleanup_seen = True
            if not row_reasons:
                binding["state"] = "bound"
            continue

        binding["scope"] = "pre_cleanup_runtime" if action == "botauto_stop" else "active_runtime"
        if stop_seen:
            reject("evidence_demux_active_row_after_stop")
        if not isinstance(runtime, dict) or runtime.get("active") is not True:
            reject("evidence_demux_identity_missing")
            continue
        identity = _runtime_identity(runtime, include_strategy=False)
        roster = runtime.get("roster")
        roster_identity = _roster_binding_identity(roster) if isinstance(roster, list) else None
        if (identity != canonical_identity or roster_identity != canonical_roster
                or payload.get("cohort_id") != canonical_cohort):
            reject("evidence_demux_cross_identity_row")
        for lifecycle_reason in _roster_binding_lifecycle_rejections(roster):
            reject(f"evidence_demux_{lifecycle_reason}")
        strategy = runtime.get(STRATEGY_FIELD)
        route_marker = _route_advancement_marker(runtime)
        if not isinstance(strategy, str) or not strategy.strip():
            reject("evidence_demux_strategy_identity_missing")
        elif previous_strategy is not None and strategy != previous_strategy:
            transition = runtime.get("strategy_transition")
            if not (
                isinstance(transition, dict)
                and transition.get("from_strategy") == previous_strategy
                and transition.get("to_strategy") == strategy
                and transition.get("advanced") is True
                and route_marker is not None
                and route_marker > previous_route_advance
            ):
                reject("evidence_demux_strategy_transition_without_route_advancement")
        if route_marker is not None:
            previous_route_advance = max(previous_route_advance, route_marker)
        if isinstance(strategy, str) and strategy.strip():
            previous_strategy = strategy

        if action == "botauto_stop":
            if stop_seen:
                reject("evidence_demux_duplicate_stop")
            cleanup = payload.get("post_cleanup")
            if (payload.get("server_epoch") != canonical_identity[9]
                    or payload.get("attempt_id") != canonical_identity[10]
                    or not isinstance(cleanup, dict) or cleanup.get("active") is not False
                    or cleanup.get("bots") != 0 or cleanup.get("lease_count") != 0):
                reject("evidence_demux_cleanup_identity_invalid")
            stop_seen = True

        for reason in telemetry_envelopes["row_rejections"].get(expected_sequence, []):
            reject(reason)

        bot_rows = payload.get("bots")
        if isinstance(bot_rows, list):
            for bot_row in bot_rows:
                if not isinstance(bot_row, dict):
                    reject("evidence_demux_bot_row_invalid")
                    continue
                bot_guid = bot_row.get("bot_guid")
                identity_object = bot_row.get("identity")
                if isinstance(identity_object, dict):
                    bot_guid = identity_object.get("bot_guid")
                if not _positive_int(bot_guid) or int(bot_guid) not in roster_guids:
                    reject("evidence_demux_bot_outside_roster")
        if not row_reasons:
            binding["state"] = "bound"
    if not stop_seen:
        reasons.append("evidence_demux_cleanup_missing")
    if not inactive_cleanup_seen:
        reasons.append("evidence_demux_inactive_cleanup_missing")
    reasons.extend(telemetry_envelopes["rejections"])
    # Historical/reconstructed captures predate the bounded combat-log export.
    # Keep the generic demultiplexer compatible with those receipts. New live
    # captures require combat-log transport and analysis through their explicit
    # forced-evidence and success gates below.
    required_actions = known_actions - {
        "botauto_profile",
        "botauto_combatlog_chunk",
        "botauto_combatlog_complete",
        "botauto_controller_route_hold",
        "botauto_chainwielder_checkpoint",
        MAGMAW_TRANSFER_CHECKPOINT_ACTION,
    }
    if terminal_failure_seen or controller_terminal_bound or fixture_terminal_bound:
        # A recognized failed attempt never reaches the post-wipe ready-check
        # success gate.  Its exact terminal status plus forced diagnose/trace
        # and ordinary cleanup remain mandatory evidence.
        required_actions.discard("botauto_readycheck")
    for required_action in required_actions:
        if required_action not in observed_actions:
            reasons.append(f"evidence_demux_required_action_missing:{required_action}")
    unique_reasons = list(dict.fromkeys(reasons))
    states = Counter(
        str((row.get("identity_binding") or {}).get("state", "unchecked"))
        for row in rows
    )
    unchecked = len(rows) - states.get("bound", 0) - states.get("rejected", 0)
    return {
        "rejections": unique_reasons,
        "retained_rows": len(rows),
        "bound_rows": states.get("bound", 0),
        "rejected_rows": states.get("rejected", 0),
        "unchecked_rows": unchecked,
        "canonical_identity_sha256": canonical_identity_sha256,
        "canonical_roster_sha256": canonical_roster_sha256,
        "required_telemetry_envelopes": telemetry_envelopes,
        "actor_binding_counts": telemetry_envelopes["actor_binding_counts"],
        "trace_discontinuities": telemetry_envelopes["trace_discontinuities"],
        "gate_passed": not unique_reasons and states.get("bound", 0) == len(rows) and unchecked == 0,
    }
