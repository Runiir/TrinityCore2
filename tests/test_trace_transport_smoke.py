import copy
import json
from pathlib import Path

from tools.raid_program import trace_transport_smoke as smoke
from tools.raid_program.capture_telemetry_transport import (
    JsonLogObservation,
    TelemetryScheduler,
    TelemetryTransportLedger,
    drain_pending_trace_batches,
)
from tools.raid_program.capture_runtime_identity import (
    IDENTITY_FIELDS,
    ROSTER_BINDING_ID_FIELDS,
)


def generic_identity():
    return {
        "cohort_id": "default", "server_epoch": 123, "attempt_id": 1,
        "profile_generation": 2, "profile_content_hash": "a" * 64,
        "active_profile": smoke.PROFILE,
    }


def receipts(*, actor_count: int = 10, followup_gap: bool = False):
    first, second = [], []
    for index in range(actor_count):
        guid = 30001 + index
        if index == 7:
            prior = {
                "bot_guid": guid, "cursor_before": 46, "cursor_after": 238,
                "gap": True, "entry_count": 64,
                "first_sequence": 175, "last_sequence": 238,
                "missing_sequence_start": 47, "missing_sequence_end": 174,
                "oldest_retained_sequence": 175, "newest_retained_sequence": 302,
            }
        else:
            cursor = 10 + index
            prior = {
                "bot_guid": guid, "cursor_before": cursor,
                "cursor_after": cursor + 32, "gap": False,
                "entry_count": 32, "first_sequence": cursor + 1,
                "last_sequence": cursor + 32,
            }
        first.append(prior)
        second.append({
            "bot_guid": guid, "cursor_before": prior["cursor_after"],
            "cursor_after": prior["cursor_after"] + 4,
            "gap": followup_gap and index == 7, "entry_count": 4,
            "first_sequence": prior["cursor_after"] + 1,
            "last_sequence": prior["cursor_after"] + 4,
        })
    common = {
        "command": smoke.DELTA_COMMAND,
        "association_state": "bound_in_serial_command_order",
        "scheduler_state_after_response": {
            "effective_trace_interval_seconds": smoke.PRESSURE_INTERVAL_SECONDS,
        },
    }
    return [
        {
            **common, "command_sequence": 1,
            "response_complete_to_next_send_seconds": 2.1,
            "identity": {"actors": first},
        },
        {**common, "command_sequence": 2, "identity": {"actors": second}},
    ]


def test_gate_requires_ten_independent_cursors_and_contiguous_followup():
    gate = smoke.evaluate(receipts())
    assert gate["gate_passed"] is True
    assert gate["state"] == "passed"
    assert gate["gap_actor_guid"] == 30008
    assert gate["actor_count"] == 10
    assert gate["effective_trace_interval_seconds"] == 2.0
    assert all(gate[field] is False for field in (
        "gameplay_admitted", "route_admitted", "fixture_admitted",
        "canary_admitted", "acceptance_admitted", "boss_fidelity_admitted",
    ))


def _transport_trace(*, start: int, end: int, pending: int, gap: bool):
    actors = []
    for index in range(10):
        guid = 30001 + index
        pressured = index == 7
        entries = (
            [{"sequence": sequence} for sequence in range(start, end + 1)]
            if pressured else []
        )
        cursor_before = start - 1 if pressured else 0
        cursor_after = end if pressured else 0
        actor = {
            "bot_guid": guid,
            "cursor_before": cursor_before,
            "cursor_after": cursor_after,
            "gap": gap if pressured else False,
            "entries": entries,
            "pending_entry_count": pending if pressured else 0,
            "newest_retained_sequence": 4097 if pressured else 0,
        }
        if gap and pressured:
            actor["discontinuity"] = {
                "missing_sequence_start": 1,
                "missing_sequence_end": 1,
                "oldest_retained_sequence": 2,
                "newest_retained_sequence": 4097,
            }
        actors.append(actor)
    return {"ok": True, "action": "botauto_trace", "bots": actors}


def _observation(row, observed_at):
    return JsonLogObservation(
        row=row,
        response_bytes=100,
        response_sha256="a" * 64,
        first_byte_observed_at_monotonic=observed_at,
        response_complete_observed_at_monotonic=observed_at,
        parse_duration_seconds=0.0001,
    )


def _scheduler_pending_receipts():
    scheduler = TelemetryScheduler(
        status_interval_sec=5, diagnose_interval_sec=30, trace_interval_sec=10,
    )
    ledger = TelemetryTransportLedger()
    first_commands = scheduler.commands_due(0.0)
    ledger.command_sent(
        first_commands, sent_at_monotonic=0.0,
        scheduler_state=scheduler.state(),
    )
    first = _transport_trace(start=2, end=129, pending=3968, gap=True)
    first_index = ledger.observe(_observation(first, 0.1))
    scheduler.observe_trace([first], observed_at=0.1)
    ledger.finalize_responses([first_index], scheduler.state())

    followup_commands = scheduler.commands_due(0.2)
    assert followup_commands == [smoke.DELTA_COMMAND]
    ledger.command_sent(
        followup_commands, sent_at_monotonic=0.2,
        scheduler_state=scheduler.state(),
    )
    followup = _transport_trace(
        start=130, end=257, pending=3840, gap=False,
    )
    followup_index = ledger.observe(_observation(followup, 0.3))
    scheduler.observe_trace([followup], observed_at=0.3)
    ledger.finalize_responses([followup_index], scheduler.state())

    return scheduler, ledger.receipts()


def test_gate_accepts_actual_scheduler_immediate_pending_followup_receipts():
    scheduler, receipts = _scheduler_pending_receipts()
    assert all(row["association_state"] == "bound_in_serial_command_order"
               for row in receipts)
    gate = smoke.evaluate(receipts)
    assert gate["gate_passed"] is True
    assert gate["pending_entry_count"] == 3968
    assert gate["response_complete_to_next_send_seconds"] == 0.1
    assert scheduler.state()["trace_gap_observed"] is True


def test_gate_rejects_zero_pressure_backlog_and_invalid_followup_metadata():
    _, valid = _scheduler_pending_receipts()
    partial = copy.deepcopy(valid)
    for actor in partial[0]["identity"]["actors"]:
        actor.pop("pending_entry_count")
    rejected_partial = smoke.evaluate(partial)
    assert "pending_drain_metadata_invalid" in rejected_partial["rejections"]

    discontinuity_collision = copy.deepcopy(valid)
    pressured_initial = discontinuity_collision[0]["identity"]["actors"][7]
    assert "newest_retained_sequence" in pressured_initial
    pressured_initial["newest_retained_sequence_present"] = False
    rejected_collision = smoke.evaluate(discontinuity_collision)
    assert "pending_drain_metadata_invalid" in rejected_collision["rejections"]

    zero_backlog = copy.deepcopy(valid)
    for actor in zero_backlog[0]["identity"]["actors"]:
        actor["pending_entry_count"] = 0
        actor["newest_retained_sequence"] = actor["cursor_after"]
    rejected_zero = smoke.evaluate(zero_backlog)
    assert "pressure_pending_backlog_mismatch" in rejected_zero["rejections"]

    drifted_followup = copy.deepcopy(valid)
    pressured = drifted_followup[1]["identity"]["actors"][7]
    pressured["pending_entry_count"] -= 1
    rejected_followup = smoke.evaluate(drifted_followup)
    assert "followup_pending_metadata_invalid:30008" in (
        rejected_followup["rejections"]
    )


def test_legacy_no_pending_response_retains_two_second_cadence():
    legacy = receipts()
    assert smoke.evaluate(legacy)["gate_passed"] is True
    legacy[0]["response_complete_to_next_send_seconds"] = 0.1
    rejected = smoke.evaluate(legacy)
    assert "next_command_send_outside_production_poll_window" in (
        rejected["rejections"]
    )
    legacy[0]["response_complete_to_next_send_seconds"] = True
    rejected_bool = smoke.evaluate(legacy)
    assert "next_command_send_timing_missing" in rejected_bool["rejections"]


def _drain_status():
    runtime = {field: f"runtime-{field}" for field in IDENTITY_FIELDS}
    runtime.update({
        "map_id": 669, "instance_id": 42, "server_epoch": 123,
        "attempt_id": 1,
    })
    roster = []
    for index in range(10):
        member = {
            field: f"member-{field}-{index}"
            for field in ROSTER_BINDING_ID_FIELDS
        }
        member.update({
            "slot": index, "guid": 30001 + index,
            "talents": [], "glyphs": [], "gear_identity_manifest": {},
        })
        roster.append(member)
    runtime["roster"] = roster
    return {"cohort_id": "default", "raid_runtime": runtime}


def _drain_page(status, start, end):
    newest = 4097
    bot_rows = []
    for index, member in enumerate(status["raid_runtime"]["roster"]):
        pressured = index == 7
        entries = []
        if pressured:
            entries = [{
                "sequence": sequence,
                "server_epoch": status["raid_runtime"]["server_epoch"],
                "attempt_id": status["raid_runtime"]["attempt_id"],
                "cohort_id": status["cohort_id"],
                "actor": {
                    "guid": member["guid"],
                    "map_id": status["raid_runtime"]["map_id"],
                    "instance_id": status["raid_runtime"]["instance_id"],
                },
            } for sequence in range(start, end + 1)]
        cursor_before = start - 1 if pressured else 0
        cursor_after = end if pressured else 0
        bot_rows.append({
            "bot_guid": member["guid"],
            "cursor_before": cursor_before,
            "cursor_after": cursor_after,
            "gap": False,
            "entries": entries,
            "pending_entry_count": newest - end if pressured else 0,
            "newest_retained_sequence": newest if pressured else 0,
        })
    return {
        "ok": True, "action": "botauto_trace", "cohort_id": "default",
        "raid_runtime": status["raid_runtime"], "bots": bot_rows,
    }


def test_terminal_drain_consumes_all_remaining_pressure_pages_after_known_gap():
    scheduler = TelemetryScheduler(trace_interval_sec=10)
    scheduler.commands_due(0.0)
    intentional_gap = _transport_trace(
        start=2, end=129, pending=3968, gap=True,
    )
    scheduler.observe_trace([intentional_gap], observed_at=0.1)
    status = _drain_status()
    initial = _drain_page(status, 130, 257)
    next_start = 258
    commands = []

    def read_page(deadline):
        nonlocal next_start
        end = min(next_start + 127, 4097)
        row = _drain_page(status, next_start, end)
        next_start = end + 1
        scheduler.observe_trace([row], observed_at=1.0)
        return row, 1.0

    report = drain_pending_trace_batches(
        (initial, 0.5), status,
        deadline_monotonic=10.0,
        send_delta=lambda: commands.append(smoke.DELTA_COMMAND),
        read_trace_response=read_page,
        monotonic=lambda: 1.0,
    )

    assert report["gate_passed"] is True
    assert report["batch_count"] == 31
    assert report["additional_delta_command_count"] == 30
    assert report["pending_entry_count_final"] == 0
    assert commands == [smoke.DELTA_COMMAND] * 30
    assert scheduler.state()["trace_gap_observed"] is True


def test_gate_fails_closed_on_reoverflow_or_short_roster():
    reoverflow = smoke.evaluate(receipts(followup_gap=True))
    assert reoverflow["terminal"] is True
    assert "gap_actor_followup_reoverflowed" in reoverflow["rejections"]
    short = smoke.evaluate(receipts(actor_count=9))
    assert short["terminal"] is True
    assert "gap_response_actor_count_mismatch" in short["rejections"]


def test_route_disabled_demux_binds_ten_diagnosis_and_trace_actors():
    gate = smoke.evaluate(receipts())
    guids = list(range(30001, 30011))
    status = {
        "action": "botauto_status", "active": True,
        **generic_identity(),
        "active_profile": smoke.PROFILE, "pool_tag_filter": smoke.POOL_TAG,
        "bots": 10, "lease_count": 10, "validation_route": {"enabled": False},
        "kills": 0, "deaths": 0, "quests_accepted": 0,
        "quests_completed": 0, "raid_boss_kills": 0,
    }
    diagnosis = {
        "action": "botauto_diagnose",
        "bots": [{"identity": {"bot_guid": guid}} for guid in guids],
    }
    trace_rows = []
    for receipt in receipts():
        actors = receipt["identity"]["actors"]
        trace_rows.append({
            "action": "botauto_trace", **generic_identity(),
            "bots": [{"bot_guid": row["bot_guid"], "gap": row["gap"]} for row in actors],
        })
    pressure = {
        "ok": True, "action": "botauto_trace_pressure",
        **generic_identity(), "authority": smoke.AUTHORITY,
        "actor_guid": guids[0], "actor_name": "Bwdtanka",
        "requested_count": smoke.PRESSURE_COUNT,
        "emitted_count": smoke.PRESSURE_COUNT,
        "sequence_before": 3, "sequence_after": 3 + smoke.PRESSURE_COUNT,
        "failure_reason": None,
    }
    rows = [{"payload": row} for row in (pressure, status, diagnosis, *trace_rows)]
    report = smoke.demux_report(rows, gate)
    assert report["gate_passed"] is True
    assert report["actor_binding_counts"] == {
        "total": 20, "bound": 19, "rejected": 1, "unchecked": 0,
    }
    status["validation_route"]["enabled"] = True
    assert "route_disabled_status_identity_mismatch" in smoke.demux_report(
        rows, gate
    )["rejections"]


def test_pressure_receipt_is_exactly_once_bounded_and_generic_identity_bound():
    receipt = {
        "ok": True, "action": "botauto_trace_pressure",
        **generic_identity(), "authority": smoke.AUTHORITY,
        "actor_guid": 30001, "actor_name": "Bwdtanka",
        "requested_count": smoke.PRESSURE_COUNT,
        "emitted_count": smoke.PRESSURE_COUNT,
        "sequence_before": 4, "sequence_after": 4 + smoke.PRESSURE_COUNT,
        "failure_reason": None,
    }
    assert smoke.pressure_receipt_report([receipt])["gate_passed"] is True
    duplicate = smoke.pressure_receipt_report([receipt, receipt])
    assert duplicate["rejections"] == ["trace_pressure_receipt_count_mismatch"]
    drifted = dict(receipt, active_profile="blackwing_descent_10n")
    assert "trace_pressure_generic_identity_invalid" in smoke.pressure_receipt_report(
        [drifted]
    )["rejections"]


def test_admission_and_profile_contract_cannot_be_used_as_magmaw_bypass(tmp_path: Path):
    assert smoke.admission_rejections(
        profile=smoke.PROFILE, scenario=smoke.PROFILE,
        pool_tag=smoke.POOL_TAG, recurrence_supplied=False,
        fixture_expansion=False, observe_seconds=60,
    ) == []
    rejected = smoke.admission_rejections(
        profile="blackwing_descent_10n_magmaw_diagnostic",
        scenario="blackwing_descent_10n_magmaw_diagnostic",
        pool_tag="blackwing_descent_10n_magmaw_diagnostic",
        recurrence_supplied=True, fixture_expansion=True, observe_seconds=0,
    )
    assert len(rejected) == 6
    assert smoke.validate_profile_assets(smoke.ROOT)["passed"] is True

    manifest = json.loads(
        (smoke.ROOT / "dataset/bot_runtime_profiles/profiles.json").read_text()
    )
    profile = next(row for row in manifest["profiles"] if row["name"] == smoke.PROFILE)
    profile["validation_route"]["enable"] = True
    path = tmp_path / "dataset/bot_runtime_profiles"
    path.mkdir(parents=True)
    (path / "profiles.json").write_text(json.dumps(manifest))
    assert smoke.validate_profile_assets(tmp_path)["reasons"] == [
        "trace_transport_profile_contract_mismatch",
        "trace_transport_profile_differs_from_reference",
    ]
