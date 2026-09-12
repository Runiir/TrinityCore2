"""Join native swing observations to health callbacks by durable event identity."""
from __future__ import annotations

from collections import Counter, defaultdict


# Unit.h MeleeHitOutcome. Preserve unknown future numeric values in the event.
OUTCOMES = ("evade", "miss", "dodge", "block", "parry", "glancing", "critical", "crushing", "normal")


def melee_resolutions(rows: list[dict]) -> tuple[list[dict], dict]:
    """Input must already be scoped to one combat stream, route and death bound.

    Timestamp proximity is never a substitute for the native sequence link.
    Resolution damage precedes DealDamage and is not an extra health callback.
    """
    callbacks = defaultdict(list)
    for row in rows:
        link = row.get("related_event_sequence")
        if row.get("kind") == "damage" and type(link) is int and link > 0:
            callbacks[link].append(row)
    events = []
    for row in rows:
        if row.get("kind") != "melee_resolution":
            continue
        event = {key: value for key, value in row.items() if not key.startswith("_")}
        event.update(at_ms=row.get("timestamp_ms"), provenance="observed_native_melee_resolution",
                     health_damage=None, health_event_sequence=None)
        stages = row.get("melee_resolution") or {}
        outcome = stages.get("hit_outcome")
        event["hit_outcome_name"] = stages.get("hit_outcome_name") or (
            OUTCOMES[outcome] if type(outcome) is int and 0 <= outcome < len(OUTCOMES) else "unavailable")
        sequence = row.get("event_sequence")
        linked = callbacks.get(sequence, []) if type(sequence) is int and sequence > 0 else []
        matching = [candidate for candidate in linked if all(
            type(row.get(key)) is int and row[key] > 0
            and type(candidate.get(key)) is int and candidate[key] == row[key]
            for key in ("actor_guid", "source_guid", "target_guid"))
            and all(type(row.get(key)) is int and row[key] >= 0
                    and type(candidate.get(key)) is int and candidate[key] == row[key]
                    for key in ("source_entry", "target_entry"))
            and type(candidate.get("event_sequence")) is int
            and candidate["event_sequence"] > sequence
            and type(candidate.get("timestamp_ms")) is int
            and type(row.get("timestamp_ms")) is int
            and candidate["timestamp_ms"] >= row["timestamp_ms"]]
        if not linked:
            state = "no_correlated_health_callback"
        elif len(linked) != 1:
            state = "ambiguous_health_callbacks"
        elif len(matching) != 1:
            state = "inconsistent_health_callback_identity"
        else:
            callback = matching[0]
            state = "matched"
            event["health_damage"] = callback.get("amount")
            event["health_event_sequence"] = callback["event_sequence"]
        event["health_correlation"] = state
        events.append(event)
    return events, {
        "observations": len(events),
        "health_correlations": dict(Counter(e["health_correlation"] for e in events)),
        "first_at_ms": min((e["at_ms"] for e in events), default=None),
        "semantics": "Native swing calculation stages. Only the explicitly linked damage callback observes health damage; missing callbacks do not establish zero health loss.",
        "scope": "timeline_identity_and_selected_route_through_death",
    }
