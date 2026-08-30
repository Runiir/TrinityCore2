import json
from pathlib import Path

from tools.raid_program import trace_transport_smoke as smoke


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
        "cohort_id": "default",
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
            "action": "botauto_trace", "cohort_id": "default",
            "bots": [{"bot_guid": row["bot_guid"], "gap": row["gap"]} for row in actors],
        })
    rows = [{"payload": row} for row in (status, diagnosis, *trace_rows)]
    report = smoke.demux_report(rows, gate)
    assert report["gate_passed"] is True
    assert report["actor_binding_counts"] == {
        "total": 20, "bound": 19, "rejected": 1, "unchecked": 0,
    }
    status["validation_route"]["enabled"] = True
    assert "route_disabled_status_identity_mismatch" in smoke.demux_report(
        rows, gate
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
