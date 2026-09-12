"""Expose retained incoming damage without inventing mitigation observations."""
from __future__ import annotations

from collections import defaultdict


RAW_SEMANTICS = (
    "Native callback raw_amount. For melee this is after damage-done/taken "
    "modifiers and script hooks, before armor and hit-outcome adjustments; it is not automatically WCL U "
    "or the unmodified weapon roll. Other damage paths require separate tracing."
)
LIMITATIONS = [
    "Zero health damage does not identify absorb, avoidance or another cause.",
    "Legacy absorbed_amount is supplied as zero by the damage notifier; it is unavailable, not observed zero.",
    "Misses clear native raw and may be absent. Parry/dodge/evade callbacks with nonzero raw survive but lack outcome labels; event count is not swing-attempt count.",
]


def incoming_damage(rows: list[dict]) -> tuple[list[dict], dict]:
    """Rows have already been identity/route/window scoped by the timeline."""
    events = []
    grouped = defaultdict(list)
    for row in rows:
        if row.get("kind") != "damage" or row.get("_perspective") != "damage_taken":
            continue
        event = {key: row.get(key) for key in (
            "event_sequence", "related_event_sequence", "actor_guid", "source_guid", "source_entry", "source_name",
            "target_guid", "target_entry", "target_name", "spell_id", "spell_name",
            "effect_type", "school_mask", "raw_amount", "route_generation", "route_node_id", "shared_damage",
        )}
        event.update(kind="damage_taken", at_ms=row.get("timestamp_ms"),
                     amount=row.get("amount"), provenance="observed_combat_event",
                     raw_amount_semantics=RAW_SEMANTICS,
                     absorbed_amount=None, absorbed_amount_observation="unavailable_legacy_notifier",
                     zero_health_cause="unavailable" if row.get("amount") == 0 else None,
                     cast_correlation="unavailable")
        events.append(event)
        key = tuple(row.get(k) for k in ("actor_guid", "source_guid", "source_entry", "spell_id"))
        grouped[key].append(event)
    groups = []
    for (actor, source, entry, spell), samples in grouped.items():
        raw = [e["raw_amount"] for e in samples if e["raw_amount"] is not None]
        health = [e["amount"] for e in samples if e["amount"] is not None]
        groups.append({
            "actor_guid": actor, "source_guid": source, "source_entry": entry,
            "source_name": samples[0]["source_name"], "spell_id": spell,
            "spell_name": samples[0]["spell_name"], "events": len(samples),
            "health_damage": sum(health), "health_observations": len(health),
            "zero_health_events": sum(v == 0 for v in health),
            "raw_observations": len(raw), "raw_min": min(raw) if raw else None,
            "raw_max": max(raw) if raw else None,
            "raw_mean": sum(raw) / len(raw) if raw else None,
            "first_at_ms": min(e["at_ms"] for e in samples),
            "last_at_ms": max(e["at_ms"] for e in samples),
        })
    return events, {"groups": groups, "raw_amount_semantics": RAW_SEMANTICS,
                    "limitations": LIMITATIONS, "scope": "timeline_identity_and_selected_route_through_death",
                    "window": {"first_at_ms": min((e["at_ms"] for e in events), default=None),
                               "last_at_ms": max((e["at_ms"] for e in events), default=None),
                               "basis": "retained_incoming_callbacks_not_an_observed_pull_start"}}
