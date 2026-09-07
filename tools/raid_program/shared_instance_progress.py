"""Validate progress between two shared-instance combat-log captures.

The combat log keeps a cumulative event count and a bounded recent-event ring.
This helper only treats events that are provably visible in the later ring as
evidence.  Aggregate totals are reconciled with that visible suffix so a
changing aggregate cannot manufacture progress across an uninspectable gap.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def validate_combat_progress(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    roster_guids: frozenset[int],
) -> bool:
    """Return whether ``after`` proves positive attributed combat progress.

    ``before`` and ``after`` are cumulative combat-log envelopes.  Their
    bounded recent-event rings only expose a suffix of the cumulative stream,
    so a count increase larger than the later ring is rejected as an
    uninspectable visibility gap.  The function has no native or external
    effects and scans at most the later ring's newly visible suffix.
    """

    def envelope(row: Mapping[str, Any]) -> tuple[int, int, list[Any], int]:
        if not isinstance(row, Mapping):
            raise ValueError("combat_log_invalid")

        event_count = row.get("event_count")
        dropped = row.get("recent_events_dropped")
        outgoing = row.get("validated_outgoing_amount")
        recent = row.get("recent_events")
        if type(event_count) is not int or event_count < 0:
            raise ValueError("combat_event_count_invalid")
        if type(dropped) is not int or dropped < 0:
            raise ValueError("combat_events_dropped_invalid")
        if type(outgoing) is not int or outgoing < 0:
            raise ValueError("combat_outgoing_amount_invalid")
        if not isinstance(recent, list):
            raise ValueError("combat_recent_events_invalid")
        if event_count != len(recent) + dropped:
            raise ValueError("combat_event_accounting_mismatch")
        return event_count, dropped, recent, outgoing

    before_count, _before_dropped, _before_recent, before_outgoing = envelope(before)
    after_count, _after_dropped, after_recent, after_outgoing = envelope(after)

    if after_count < before_count:
        raise ValueError("combat_event_count_regression")
    if after_outgoing < before_outgoing:
        raise ValueError("combat_outgoing_amount_regression")

    event_delta = after_count - before_count
    amount_delta = after_outgoing - before_outgoing
    if event_delta > len(after_recent):
        raise ValueError("combat_event_visibility_gap")
    if event_delta == 0 and amount_delta != 0:
        raise ValueError("combat_outgoing_delta_mismatch")

    # ``recent[-0:]`` is the complete list in Python.  An explicit empty
    # suffix keeps an unchanged cumulative count from revalidating old rows.
    new_events = after_recent[-event_delta:] if event_delta else ()
    outgoing_delta = 0
    for event in new_events:
        if not isinstance(event, Mapping):
            raise ValueError("combat_event_invalid")
        kind = event.get("kind")
        actor_guid = event.get("actor_guid")
        source_guid = event.get("source_guid")
        source_entry = event.get("source_entry")
        source_is_pet = event.get("source_is_pet")
        originated_amount = event.get("originated_amount")
        if (
            kind not in ("damage", "heal")
            or type(actor_guid) is not int
            or actor_guid <= 0
            or actor_guid not in roster_guids
            or type(source_guid) is not int
            or source_guid <= 0
            or type(source_entry) is not int
            or source_entry < 0
            or type(source_is_pet) is not bool
            or type(originated_amount) is not int
            or originated_amount < 0
        ):
            raise ValueError("combat_event_invalid")

        # A player source is identified by its zero entry and the actor's
        # player GUID.  A nonzero entry is a creature, even if its low GUID
        # happens to collide with a roster player.  Native SourceIsPet already
        # carries the normalized owning player attribution for owned pets.
        outgoing_event = (
            (source_entry == 0 and source_guid == actor_guid)
            or source_is_pet
        )
        if outgoing_event:
            outgoing_delta += originated_amount

    if outgoing_delta != amount_delta:
        raise ValueError("combat_outgoing_delta_mismatch")
    return event_delta > 0 and amount_delta > 0


__all__ = ["validate_combat_progress"]
