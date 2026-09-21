"""Bounded projections of existing events. Preserve source order and missing state."""
from __future__ import annotations

from collections import Counter


def event_rows(document):
    """Yield locator, row, clock origin; never infer cast outcomes from damage."""
    if "combat_calibration" in document:
        cal = document["combat_calibration"]
        prefix = "/combat_calibration"
        if not (cal.get("window_complete") or cal.get("phase") == "complete"):
            if cal.get("previous_window"):
                cal = cal["previous_window"]
                prefix += "/previous_window"
        origin = cal.get("scored_started_at_ms")
        for bi, bot in enumerate(cal.get("bots", [])):
            for i, row in enumerate(bot.get("decision_timeline", [])):
                yield f"{prefix}/bots/{bi}/decision_timeline/{i}", {
                    **row, "actor_guid": bot["guid"], "kind": "decision",
                    "provenance": "calibration_decision_observation"}, origin
        return
    if "events" in document:
        origin = document.get("window", {}).get("first_hostile_at_ms")
        for i, row in enumerate(document["events"]):
            yield f"/events/{i}", row, origin
        return
    # Existing normalized simulator/review timelines, not a new raw-log parser.
    for key in ("wowsims_debug_result", "wowsims_result"):
        if isinstance(document.get(key), dict) and document[key].get("timeline", {}).get("events"):
            for i, row in enumerate(document[key]["timeline"]["events"]):
                yield f"/{key}/timeline/events/{i}", row, None
            return
    if isinstance(document.get("timeline"), dict):
        for i, row in enumerate(document["timeline"].get("events", [])):
            yield f"/timeline/events/{i}", row, None
        return
    raise ValueError("no supported event stream; build the existing bot_timeline or normalized rotation review first")


def clocks(row, origin):
    absolute = row.get("at_ms")
    relative = row.get("elapsed_ms")
    if relative is None and row.get("timestamp_seconds") is not None:
        relative = row["timestamp_seconds"] * 1000
    if absolute is None and relative is not None and origin is not None:
        absolute = origin + relative
    if relative is None and absolute is not None and origin is not None:
        relative = absolute - origin
    return absolute, relative


SCALARS = ("kind", "actor_guid", "spell_id", "target_guid", "target_entry", "phase",
           "phase_provenance", "result", "reason", "reason_code", "action", "amount",
           "attack_origin", "source_is_pet", "sequence", "decision_sequence", "event_sequence",
           "related_event_sequence", "cast_instance_id", "cast_correlation", "line_index",
           "source_entity", "target_entity", "provenance", "historical_metadata", "mana", "health",
           "alive", "is_moving", "distance", "target_distance", "los", "in_range", "movement_owner",
           "current_generic_spell_id", "current_channeled_spell_id", "pet_victim_guid")
NESTED = ("native_selected_target", "state_bound_target", "event_target", "native_actor",
          "observation_quality", "resource", "landed_effect", "identity", "movement", "failure")


def projection(row, locator, absolute, relative):
    out = {"locator": locator, "at_ms": absolute, "elapsed_ms": relative}
    for key in SCALARS:
        if key in row:
            out[key] = row[key]
    for key in NESTED:
        if isinstance(row.get(key), dict):
            out[key] = {k: v for k, v in row[key].items() if not isinstance(v, (dict, list))}
    if isinstance(row.get("summon_observation"), dict):
        out["offensive_target_observation"] = {k: row["summon_observation"].get(k) for k in
            ("offensive_target_guid", "offensive_target_valid", "observed_elapsed_ms")}
    out["missing_observations"] = [key for key in ("phase", "cast_instance_id") if not row.get(key)]
    return out


def query_events(document, *, actor=None, spell=None, target=None, phase=None, kind=None,
                 start_ms=None, end_ms=None, clock="relative", offset=0, limit=20):
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("limit must be 1..100 and offset nonnegative")
    if start_ms is not None and end_ms is not None and end_ms < start_ms:
        raise ValueError("end precedes start")
    rows, total, excluded = [], 0, Counter()
    for locator, row, origin in event_rows(document):
        absolute, relative = clocks(row, origin)
        at = absolute if clock == "absolute" else relative
        checks = ((actor, row.get("actor_guid", row.get("source_entity")), "actor"),
                  (spell, row.get("spell_id", (row.get("identity") or {}).get("id")), "spell"),
                  (phase, row.get("phase"), "phase"), (kind, row.get("kind"), "kind"))
        skip = False
        for wanted, observed, field in checks:
            if wanted is not None and str(wanted) != str(observed):
                if observed is None:
                    excluded[f"missing_{field}"] += 1
                skip = True
                break
        if skip:
            continue
        if target is not None:
            targets = [row.get("target_guid"), row.get("target_entity"),
                (row.get("summon_observation") or {}).get("offensive_target_guid")]
            targets.extend((row.get(k) or {}).get("guid") for k in
                           ("native_selected_target", "state_bound_target", "event_target"))
            targets = [str(t) for t in targets if t is not None]
            if str(target) not in targets:
                if not targets:
                    excluded["missing_target"] += 1
                continue
        if start_ms is not None or end_ms is not None:
            if at is None:
                excluded[f"missing_{clock}_clock"] += 1
                continue
            if (start_ms is not None and at < start_ms) or (end_ms is not None and at > end_ms):
                continue
        if offset <= total < offset + limit:
            rows.append(projection(row, locator, absolute, relative))
        total += 1
    return {"schema": "evidence_event_page_v1", "clock": clock, "matching_records": total,
            "offset": offset, "returned_records": len(rows),
            "next_offset": offset + len(rows) if offset + len(rows) < total else None,
            "excluded_missing_observations": dict(excluded), "records": rows,
            "completeness": document.get("completeness"),
            "ordering": "source order preserved; equal timestamps are not reordered or deduplicated",
            "target_filter_basis": "any explicit effect/selected/bound/offensive target; distinct fields retain their meaning",
            "note": "No match is not proof of no event. Missing fields remain unknown. Locators address the hashed source."}
