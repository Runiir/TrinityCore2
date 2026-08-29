"""Deterministic derived metrics for tactical replay windows."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def dps_hps(combat: list[dict[str, Any]], duration_seconds: float) -> dict[str, Any]:
    actors: dict[int, dict[str, Any]] = {}
    for event in combat:
        actor = actors.setdefault(
            event["actor_guid"],
            {
                "actor_guid": event["actor_guid"],
                "actor_name": event["actor_name"],
                "actor_role": event["actor_role"],
                "damage": 0,
                "healing": 0,
                "damage_seconds": set(),
                "healing_seconds": set(),
            },
        )
        amount = event["originated_amount"]
        second = event["timestamp_ms"] // 1000
        if event["kind"] == "damage" and amount > 0:
            actor["damage"] += amount
            actor["damage_seconds"].add(second)
        elif event["kind"] == "heal" and amount > 0:
            actor["healing"] += amount
            actor["healing_seconds"].add(second)
    result = []
    for actor in actors.values():
        damage_seconds = len(actor.pop("damage_seconds"))
        healing_seconds = len(actor.pop("healing_seconds"))
        actor.update(
            {
                "dps": round(actor["damage"] / max(duration_seconds, 0.001), 3),
                "hps": round(actor["healing"] / max(duration_seconds, 0.001), 3),
                "active_damage_seconds": damage_seconds,
                "active_healing_seconds": healing_seconds,
                "active_dps": round(actor["damage"] / max(damage_seconds, 1), 3),
                "active_hps": round(actor["healing"] / max(healing_seconds, 1), 3),
            }
        )
        result.append(actor)
    result.sort(key=lambda row: (-row["damage"], row["actor_guid"]))
    party_damage = sum(row["damage"] for row in result)
    party_healing = sum(row["healing"] for row in result)
    return {
        "denominator": "fixed_bounded_replay_window",
        "duration_seconds": duration_seconds,
        "party_damage": party_damage,
        "party_healing": party_healing,
        "party_dps": round(party_damage / max(duration_seconds, 0.001), 3),
        "party_hps": round(party_healing / max(duration_seconds, 0.001), 3),
        "actors": result,
    }


def movement_diagnostics(
    positions: list[dict[str, Any]], receipts: list[dict[str, Any]]
) -> dict[str, Any]:
    by_actor: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in positions:
        by_actor[row["bot_guid"]].append(row)
    reversals: list[dict[str, Any]] = []
    discontinuities: list[dict[str, Any]] = []
    for bot_guid, rows in by_actor.items():
        rows.sort(key=lambda row: (row["timestamp_ms"], row["basis"]))
        vectors: list[tuple[dict[str, Any], dict[str, Any], tuple[float, float]]] = []
        for left, right in zip(rows, rows[1:]):
            if right["timestamp_ms"] <= left["timestamp_ms"]:
                continue
            a, b = left["position"], right["position"]
            dx, dy, dz = b["x"] - a["x"], b["y"] - a["y"], b["z"] - a["z"]
            distance = math.hypot(dx, dy)
            if abs(dz) >= 4.0:
                recovery = next(
                    (
                        candidate
                        for candidate in rows
                        if candidate["timestamp_ms"] > right["timestamp_ms"]
                        and candidate["position"]["z"] >= a["z"] - 1.0
                    ),
                    None,
                )
                discontinuities.append(
                    {
                        "bot_guid": bot_guid,
                        "from_ms": left["timestamp_ms"],
                        "to_ms": right["timestamp_ms"],
                        "from_position": a,
                        "to_position": b,
                        "vertical_delta": round(dz, 6),
                        "from_basis": left["basis"],
                        "to_basis": right["basis"],
                        "recovered_to_prior_level_at_ms": (
                            recovery["timestamp_ms"] if recovery else None
                        ),
                        "persistent_through_window": recovery is None,
                    }
                )
            if distance >= 0.75 and right["timestamp_ms"] - left["timestamp_ms"] <= 5000:
                vectors.append((left, right, (dx, dy)))
        for previous, current in zip(vectors, vectors[1:]):
            if previous[1]["timestamp_ms"] != current[0]["timestamp_ms"]:
                continue
            ax, ay = previous[2]
            bx, by = current[2]
            cosine = (ax * bx + ay * by) / max(
                math.hypot(ax, ay) * math.hypot(bx, by), 0.001
            )
            if cosine <= -0.5:
                reversals.append(
                    {
                        "bot_guid": bot_guid,
                        "timestamp_ms": current[0]["timestamp_ms"],
                        "direction_cosine": round(cosine, 6),
                    }
                )
    latency_rows = []
    for receipt in receipts:
        progress = receipt["progress"]
        latency_rows.append(
            {
                "bot_guid": receipt["bot_guid"],
                "receipt_id": receipt["receipt_id"],
                "intent_reason": receipt["intent_reason"],
                "submitted": receipt["executor"]["spline_launch_succeeded"],
                "submission_to_first_progress_latency_ms": progress[
                    "submission_to_first_progress_latency_ms"
                ],
                "sample_count": progress["sample_count"],
                "terminal_outcome": progress["terminal_outcome"],
            }
        )
    return {
        "oscillation": {
            "definition": "horizontal direction reversal with cosine <= -0.5, both legs >=0.75 yards and <=5 seconds",
            "reversal_count": len(reversals),
            "reversals": reversals,
        },
        "vertical_discontinuities": discontinuities,
        "decision_to_native": {
            "selection_to_submission_precision": "same_millisecond_only",
            "receipts": latency_rows,
        },
    }


def target_distribution(combat: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[tuple[int, str], dict[str, Any]] = {}
    for event in combat:
        if event["kind"] != "damage" or event["originated_amount"] <= 0:
            continue
        key = (event["target_entry"], event["target_name"])
        row = totals.setdefault(
            key,
            {
                "target_entry": key[0],
                "target_name": key[1],
                "damage": 0,
                "events": 0,
                "first_at_ms": event["timestamp_ms"],
                "last_at_ms": event["timestamp_ms"],
            },
        )
        row["damage"] += event["originated_amount"]
        row["events"] += 1
        row["first_at_ms"] = min(row["first_at_ms"], event["timestamp_ms"])
        row["last_at_ms"] = max(row["last_at_ms"], event["timestamp_ms"])
    return sorted(totals.values(), key=lambda row: (-row["damage"], row["target_entry"]))


def mechanic_signals(combat: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keywords = (
        "lava",
        "parasite",
        "infection",
        "pillar",
        "mangle",
        "spew",
        "vulnerability",
    )
    grouped: dict[tuple[int, str], dict[str, Any]] = {}
    for event in combat:
        spell_name = event["spell_name"]
        if not any(word in spell_name.lower() for word in keywords):
            continue
        key = (event["spell_id"], spell_name)
        row = grouped.setdefault(
            key,
            {
                "spell_id": key[0],
                "spell_name": key[1],
                "event_count": 0,
                "timestamps_ms": [],
                "source_names": set(),
                "target_names": set(),
            },
        )
        row["event_count"] += 1
        row["timestamps_ms"].append(event["timestamp_ms"])
        row["source_names"].add(event["source_name"])
        row["target_names"].add(event["target_name"])
    output = []
    for row in grouped.values():
        row["timestamps_ms"] = sorted(set(row["timestamps_ms"]))
        row["source_names"] = sorted(row["source_names"])
        row["target_names"] = sorted(row["target_names"])
        output.append(row)
    return sorted(output, key=lambda row: (row["timestamps_ms"][0], row["spell_id"]))


def output_idle_proxy(
    decisions: list[dict[str, Any]],
    combat: list[dict[str, Any]],
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    active: dict[int, set[int]] = defaultdict(set)
    for event in combat:
        if event["originated_amount"] > 0 and event["kind"] in {"damage", "heal"}:
            active[event["actor_guid"]].add(event["timestamp_ms"] // 1000)
    for decision in decisions:
        if decision["action"] in {
            "spell_cast",
            "cast_combat_spell",
            "raid_heal",
            "trained_heal",
        }:
            active[decision["bot_guid"]].add(decision["timestamp_ms"] // 1000)
    total_seconds = max(1, (end_ms - start_ms + 999) // 1000)
    return {
        "status": "proxy_only",
        "definition": "seconds without originated damage/healing or a retained successful cast/heal action",
        "not_equivalent_to_cast_downtime": True,
        "actors": [
            {
                "bot_guid": bot_guid,
                "active_seconds": len(seconds),
                "idle_seconds": max(0, total_seconds - len(seconds)),
                "idle_fraction": round(
                    max(0, total_seconds - len(seconds)) / total_seconds, 6
                ),
            }
            for bot_guid, seconds in sorted(active.items())
        ],
    }


def causal_assessment(
    movement: dict[str, Any],
    receipts: list[dict[str, Any]],
    diagnoses: list[dict[str, Any]],
) -> dict[str, Any]:
    discontinuities = movement.get("vertical_discontinuities") or []
    if not discontinuities:
        return {
            "status": "not_localized",
            "first_observed_state_infection": None,
            "suspected_upstream_receipt": None,
            "exact_missing_field": "continuous_actor_state_or_an_observed_state_discontinuity",
        }
    persistent = [
        row
        for row in discontinuities
        if row["vertical_delta"] < 0 and row["persistent_through_window"]
    ]
    edge = min(persistent or discontinuities, key=lambda row: row["to_ms"])
    prior = [
        row
        for row in receipts
        if row["bot_guid"] == edge["bot_guid"]
        and row["executor"]["spline_launch_succeeded"]
        and row["observed_at_ms"] <= edge["to_ms"]
    ]
    receipt = max(prior, key=lambda row: row["observed_at_ms"], default=None)
    if not receipt:
        return {
            "status": "localized_without_upstream_receipt",
            "first_observed_state_infection": edge,
            "suspected_upstream_receipt": None,
            "exact_missing_field": "receipt_tagged_native_movement_preceding_the_position_discontinuity",
        }
    progress = receipt["progress"]
    gap_ms = edge["to_ms"] - _integer(progress.get("last_observed_at_ms"))
    rejected = [
        row
        for row in receipts
        if row["bot_guid"] == edge["bot_guid"]
        and row["observed_at_ms"] >= edge["to_ms"]
        and row["admission"]["result"] == "rejected"
    ]
    first_rejected = min(rejected, key=lambda row: row["observed_at_ms"], default=None)
    repeated_frames = [
        row
        for row in diagnoses
        if row["bot_guid"] == edge["bot_guid"]
        and row["timestamp_ms"] >= edge["to_ms"]
        and row["current_action"] == "wait_for_candidate_backoff"
    ]
    max_repeated_backoff = max(
        (
            _integer((row.get("decision") or {}).get("consecutive_same_decision_count"))
            for row in repeated_frames
        ),
        default=0,
    )
    return {
        "status": "localized_not_causally_closed",
        "first_observed_state_infection": edge,
        "suspected_upstream_receipt": {
            "receipt_id": receipt["receipt_id"],
            "bot_guid": receipt["bot_guid"],
            "intent_reason": receipt["intent_reason"],
            "floor_observation_conflict": receipt["planner"][
                "floor_observation_conflict"
            ],
            "spline_id": receipt["executor"]["spline_id"],
            "launched_at_ms": progress["armed_at_ms"],
            "last_receipt_tagged_sample_at_ms": progress["last_observed_at_ms"],
            "sampling_gap_to_infection_ms": gap_ms,
        },
        "correlation": "same_actor_temporal_predecessor_only",
        "downstream": {
            "first_rejected_receipt": (
                {
                    "receipt_id": first_rejected["receipt_id"],
                    "observed_at_ms": first_rejected["observed_at_ms"],
                    "reason": first_rejected["admission"]["reason"],
                    "planner_reason": str(
                        first_rejected["admission"]["planner"].get("reason") or ""
                    ),
                    "path_type": first_rejected["planner"]["path_type"],
                    "actor_before_planning": first_rejected["actor_before_planning"],
                }
                if first_rejected
                else None
            ),
            "max_consecutive_backoff_decisions": max_repeated_backoff,
        },
        "exact_missing_field": (
            "continuous_receipt_tagged_actor_position_and_spline_identity_from_the_last_"
            "sample_until_terminal_outcome_or_supersession"
        ),
    }
