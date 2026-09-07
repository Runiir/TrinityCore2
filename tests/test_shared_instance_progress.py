from __future__ import annotations

from copy import deepcopy

import pytest

from tools.raid_program.shared_instance_progress import validate_combat_progress


ROSTER = frozenset({101, 202})


def combat_event(
    *,
    kind: str = "damage",
    actor_guid: int = 101,
    source_guid: int = 9001,
    source_entry: int = 41570,
    source_is_pet: bool = False,
    originated_amount: int = 0,
) -> dict[str, object]:
    return {
        "kind": kind,
        "actor_guid": actor_guid,
        "source_guid": source_guid,
        "source_entry": source_entry,
        "source_is_pet": source_is_pet,
        "originated_amount": originated_amount,
    }


def envelope(
    events: list[dict[str, object]],
    *,
    dropped: int = 0,
    outgoing: int = 0,
) -> dict[str, object]:
    return {
        "event_count": len(events) + dropped,
        "recent_events_dropped": dropped,
        "recent_events": events,
        "validated_outgoing_amount": outgoing,
    }


def test_player_and_owned_pet_outgoing_mix_is_progress():
    after_events = [
        combat_event(
            source_guid=101, source_entry=0, originated_amount=125,
        ),
        combat_event(
            actor_guid=101, source_guid=9101, source_entry=12345,
            source_is_pet=True, originated_amount=75,
        ),
        combat_event(
            actor_guid=101, source_guid=101, source_entry=41570,
            originated_amount=300,
        ),
        combat_event(
            actor_guid=202, source_guid=8888, source_entry=0,
            originated_amount=200,
        ),
        combat_event(kind="heal", actor_guid=202, source_guid=202,
                     source_entry=0, originated_amount=25),
    ]

    assert validate_combat_progress(
        envelope([]), envelope(after_events, outgoing=225), ROSTER,
    ) is True


def test_same_count_aggregate_growth_is_rejected():
    prior = envelope([combat_event()], outgoing=10)
    current = envelope([combat_event()], outgoing=11)

    with pytest.raises(ValueError, match="^combat_outgoing_delta_mismatch$"):
        validate_combat_progress(prior, current, ROSTER)


def test_count_delta_larger_than_visible_ring_is_rejected():
    visible = [combat_event(source_guid=5000 + index) for index in range(4096)]
    current = envelope(visible, dropped=1)
    assert current["event_count"] == 4097
    assert len(current["recent_events"]) == 4096

    with pytest.raises(ValueError, match="^combat_event_visibility_gap$"):
        validate_combat_progress(envelope([]), current, ROSTER)


@pytest.mark.parametrize(
    ("prior", "current", "error"),
    [
        (
            envelope([combat_event(), combat_event(source_guid=7001)]),
            envelope([combat_event()]),
            "combat_event_count_regression",
        ),
        (
            envelope([combat_event()], outgoing=10),
            envelope([combat_event()], outgoing=9),
            "combat_outgoing_amount_regression",
        ),
    ],
)
def test_cumulative_event_and_amount_regressions_are_rejected(
    prior, current, error,
):
    with pytest.raises(ValueError, match=f"^{error}$"):
        validate_combat_progress(prior, current, ROSTER)


@pytest.mark.parametrize("field", ["originated_amount", "source_is_pet"])
def test_new_event_requires_originated_amount_and_exact_boolean(field):
    event = combat_event(source_guid=1234, source_entry=0, originated_amount=4)
    if field == "originated_amount":
        del event[field]
    else:
        event[field] = 1

    with pytest.raises(ValueError, match="^combat_event_invalid$"):
        validate_combat_progress(envelope([]), envelope([event], outgoing=4), ROSTER)


def test_incoming_only_event_is_valid_but_not_progress():
    incoming = combat_event(
        source_guid=6001, source_entry=41570, originated_amount=37,
    )

    assert validate_combat_progress(
        envelope([]), envelope([incoming], outgoing=0), ROSTER,
    ) is False


def test_creature_guid_collision_is_incoming():
    collision = combat_event(
        source_guid=101, source_entry=41570, originated_amount=37,
    )

    assert validate_combat_progress(
        envelope([]), envelope([collision], outgoing=0), ROSTER,
    ) is False


def test_unchanged_counters_are_valid_and_false_without_suffix_scan():
    old_ring = [{"kind": "legacy"}]
    prior = envelope(old_ring)
    current = deepcopy(prior)

    assert validate_combat_progress(prior, current, ROSTER) is False
