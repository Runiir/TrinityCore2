import json
from copy import deepcopy
from pathlib import Path

from tools.raid_program.capture_watchdog import observe_capture_watchdog


FIXTURE = Path(__file__).parent / "fixtures" / "capture_death_loop_b0c7f38b0a.json"
PROFILE = "blackwing_descent_10n_magmaw_diagnostic"


def _status(*, attempt_id: int = 1, wipe_generation: int = 0) -> dict:
    roster = [
        {
            "slot": slot,
            "guid": 30001 + slot,
            "active": True,
            "lease_owned": True,
        }
        for slot in range(10)
    ]
    return {
        "ok": True,
        "action": "botauto_status",
        "cohort_id": "default",
        "active_profile": PROFILE,
        "bots": 10,
        "lease_count": 10,
        "validation_route": {
            "node_id": "bwd.magmaw.encounter",
            "generation": 3,
            "map_id": 669,
        },
        "raid_runtime": {
            "active": True,
            "expected_size": 10,
            "active_size": 10,
            "roster_complete": True,
            "map_id": 669,
            "instance_id": 77,
            "attempt_id": attempt_id,
            "assignment_generation": 1,
            "unique_leases": True,
            "strategy_id": "tank_swap_adds_raid_aoe",
            "wipe_generation": wipe_generation,
            "roster": roster,
            "admission_receipt": {
                "entrance_map_id": 669,
                "members": [{"guid": row["guid"]} for row in roster],
            },
        },
    }


def _trace(
    bot_guid: int,
    entries: list[dict],
    *,
    attempt_id: int = 1,
    wipe_generation: int | None = None,
) -> dict:
    row = {
        "action": "botauto_trace",
        "attempt_id": attempt_id,
        "bots": [{"bot_guid": bot_guid, "entries": entries}],
    }
    if wipe_generation is not None:
        row["raid_runtime"] = {"wipe_generation": wipe_generation}
    return row


def _death(sequence: int, *, action: str = "death", attempt_id: int = 1) -> dict:
    return {
        "action": action,
        "attempt_id": attempt_id,
        "decision_sequence": sequence,
        "result": "dead",
        "route_node_id": "bwd.magmaw.encounter",
        "route_generation": 3,
        "sequence": sequence,
        "timestamp_ms": sequence * 1000,
    }


def _failure(sequence: int, *, attempt_id: int) -> dict:
    return {
        "action": "validation_route_recovery",
        "attempt_id": attempt_id,
        "decision_sequence": sequence,
        "fingerprint_hash": 77,
        "result": "route_destination_invalid",
        "route_node_id": "bwd.magmaw.encounter",
        "route_generation": 3,
        "sequence": sequence,
        "timestamp_ms": sequence * 1000,
    }


def test_real_distinct_first_casualties_do_not_form_a_death_loop():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = [
        _trace(
            source["bot_guid"],
            [{
                key: value for key, value in source.items()
                if key not in {"bot_guid", "capture_sequence", "attempt_id"}
            }],
            attempt_id=source["attempt_id"],
        )
        for source in fixture["trace_rows"]
    ]

    report = observe_capture_watchdog(
        {}, _status(), None, rows,
        profile_name=PROFILE,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["distinct_death_casualty_count"] == 4
    assert report["death_lifecycle_count"] == 4
    assert report["death_loop_count"] == 1


def test_same_actor_three_distinct_death_lifecycles_reaches_existing_threshold():
    report = observe_capture_watchdog(
        {},
        _status(),
        None,
        [_trace(30009, [_death(sequence) for sequence in (1, 2, 3)])],
        profile_name=PROFILE,
        max_death_loops=3,
    )

    assert report["detected"] is True
    assert report["failure_reason"] == "death_loop_watchdog"
    assert report["distinct_death_casualty_count"] == 1
    assert report["death_lifecycle_count"] == 3
    assert report["death_loop_count"] == 3


def test_native_death_and_repeated_death_in_one_tick_are_one_lifecycle():
    death = _death(8)
    repeated = deepcopy(death)
    repeated.update(action="repeated_death", sequence=9)

    report = observe_capture_watchdog(
        {}, _status(), None, [_trace(30009, [death, repeated])],
        profile_name=PROFILE,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["death_loop_count"] == 1


def test_split_native_death_and_repeated_death_tick_is_one_lifecycle():
    state = {}
    death = _death(8)
    repeated = deepcopy(death)
    repeated.update(action="repeated_death", sequence=9)

    observe_capture_watchdog(
        state, _status(), None, [_trace(30009, [death])],
        profile_name=PROFILE,
        max_death_loops=3,
    )
    report = observe_capture_watchdog(
        state, _status(), None, [_trace(30009, [repeated])],
        profile_name=PROFILE,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["death_lifecycle_count"] == 1
    assert report["death_loop_count"] == 1


def test_same_decision_sequence_after_resurrection_counts_new_canonical_death():
    first = _death(8)
    first["decision_sequence"] = 5
    resurrected = {
        **_death(9, action="resurrected"),
        "decision_sequence": 5,
        "result": "alive",
    }
    second = _death(10)
    second["decision_sequence"] = 5

    report = observe_capture_watchdog(
        {},
        _status(),
        None,
        [_trace(30009, [first, resurrected, second])],
        profile_name=PROFILE,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["distinct_death_casualty_count"] == 1
    assert report["death_lifecycle_count"] == 2
    assert report["death_loop_count"] == 2


def test_actor_raid_wipe_reports_deduplicate_one_native_wipe_generation():
    status = _status(wipe_generation=4)
    rows = [
        _trace(
            guid,
            [_death(guid, action="raid_wipe")],
            wipe_generation=4,
        )
        for guid in (30001, 30002, 30003)
    ]
    state = {}

    report = observe_capture_watchdog(
        state, status, None, rows,
        profile_name=PROFILE,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["distinct_death_casualty_count"] == 0
    assert report["death_lifecycle_count"] == 0
    assert report["death_loop_count"] == 1
    assert list(state["death_loop_native_wipes"].values()) == [[4]]


def test_same_actor_duplicate_raid_wipe_ticks_do_not_form_a_loop():
    report = observe_capture_watchdog(
        {},
        _status(wipe_generation=4),
        None,
        [_trace(
            30001,
            [_death(sequence, action="raid_wipe") for sequence in (1, 2, 3)],
            wipe_generation=4,
        )],
        profile_name=PROFILE,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["distinct_death_casualty_count"] == 0
    assert report["death_lifecycle_count"] == 0
    assert report["death_loop_count"] == 1


def test_three_distinct_native_wipe_generations_reach_existing_threshold():
    state = {}
    report = None
    for wipe_generation, guid in enumerate((30001, 30002, 30003), start=1):
        report = observe_capture_watchdog(
            state,
            _status(wipe_generation=wipe_generation),
            None,
            [_trace(
                guid,
                [_death(wipe_generation, action="raid_wipe")],
                wipe_generation=wipe_generation,
            )],
            profile_name=PROFILE,
            max_death_loops=3,
        )

    assert report is not None
    assert report["detected"] is True
    assert report["failure_reason"] == "death_loop_watchdog"
    assert report["death_loop_count"] == 3


def test_death_counts_are_scoped_to_the_current_attempt():
    state = {}
    first = observe_capture_watchdog(
        state,
        _status(attempt_id=1),
        None,
        [_trace(30009, [_death(1), _death(2)])],
        profile_name=PROFILE,
        max_death_loops=3,
    )
    assert first["death_loop_count"] == 2

    second = observe_capture_watchdog(
        state,
        _status(attempt_id=2),
        None,
        [
            _trace(30009, [_death(3, attempt_id=1)], attempt_id=1),
            _trace(30009, [_death(4, attempt_id=2)], attempt_id=2),
        ],
        profile_name=PROFILE,
        max_death_loops=3,
    )

    assert second["detected"] is False
    assert second["distinct_death_casualty_count"] == 1
    assert second["death_lifecycle_count"] == 1
    assert second["death_loop_count"] == 1


def test_foreign_actor_and_malformed_attempt_cannot_increment_death_loop():
    report = observe_capture_watchdog(
        {},
        _status(),
        None,
        [
            _trace(99999, [_death(1)]),
            _trace(30009, [_death(2)], attempt_id=True),
        ],
        profile_name=PROFILE,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["distinct_death_casualty_count"] == 0
    assert report["death_lifecycle_count"] == 0
    assert report["death_loop_count"] == 0


def test_foreign_attempt_cannot_poison_current_attempt_trace_cursor():
    state = {}
    observe_capture_watchdog(
        state,
        _status(attempt_id=1),
        None,
        [_trace(30009, [_death(1)], attempt_id=1)],
        profile_name=PROFILE,
        max_death_loops=3,
    )

    report = observe_capture_watchdog(
        state,
        _status(attempt_id=2),
        None,
        [
            _trace(30009, [_death(100, attempt_id=1)], attempt_id=1),
            _trace(30009, [_death(2, attempt_id=2)], attempt_id=2),
        ],
        profile_name=PROFILE,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["distinct_death_casualty_count"] == 1
    assert report["death_lifecycle_count"] == 1
    assert report["death_loop_count"] == 1


def test_foreign_route_cannot_poison_current_route_trace_cursor():
    foreign = _death(100)
    foreign.update(
        route_node_id="bwd.magmaw.drudges",
        route_generation=2,
    )
    current = _death(2)

    report = observe_capture_watchdog(
        {},
        _status(),
        None,
        [_trace(30009, [foreign, current])],
        profile_name=PROFILE,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["distinct_death_casualty_count"] == 1
    assert report["death_lifecycle_count"] == 1
    assert report["death_loop_count"] == 1


def test_wipe_generation_uses_trace_envelope_instead_of_later_status():
    state = {}
    status = _status(wipe_generation=5)
    first = _trace(
        30001,
        [_death(1, action="raid_wipe")],
        wipe_generation=4,
    )
    second = _trace(
        30002,
        [_death(2, action="raid_wipe")],
        wipe_generation=4,
    )

    report = observe_capture_watchdog(
        state,
        status,
        None,
        [first, second],
        profile_name=PROFILE,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["death_loop_count"] == 1
    assert list(state["death_loop_native_wipes"].values()) == [[4]]


def test_repeated_decision_counts_do_not_cross_attempt_boundary():
    state = {}
    first = observe_capture_watchdog(
        state,
        _status(attempt_id=1),
        None,
        [_trace(
            30009,
            [_failure(1, attempt_id=1), _failure(2, attempt_id=1)],
            attempt_id=1,
        )],
        profile_name=PROFILE,
        max_repeated_decisions=3,
    )
    assert first["repeated_decision_count"] == 2

    second = observe_capture_watchdog(
        state,
        _status(attempt_id=2),
        None,
        [_trace(
            30009,
            [_failure(1, attempt_id=2)],
            attempt_id=2,
        )],
        profile_name=PROFILE,
        max_repeated_decisions=3,
    )

    assert second["detected"] is False
    assert second["repeated_decision_count"] == 1


def test_stale_diagnosis_cannot_trip_current_attempt_watchdog():
    stale_diagnosis = {
        "attempt_id": 1,
        "bots": [{
            "identity": {"bot_guid": 30009},
            "snapshot": {
                "decision": {
                    "action": "validation_route_recovery",
                    "result": "route_destination_invalid",
                    "consecutive_same_decision_count": 3,
                },
                "route_progress": {
                    "route": {
                        "node_id": "bwd.magmaw.encounter",
                        "generation": 3,
                    },
                },
            },
        }],
    }

    report = observe_capture_watchdog(
        {},
        _status(attempt_id=2),
        stale_diagnosis,
        profile_name=PROFILE,
        max_repeated_decisions=3,
    )

    assert report["detected"] is False
    assert report["repeated_decision_count"] == 0
