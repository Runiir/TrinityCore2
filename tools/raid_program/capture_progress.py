from __future__ import annotations

import hashlib
import json
from math import isfinite
from typing import Any


def ready_for_native_readycheck(status: dict[str, Any]) -> bool:
    """Mirror the native C++ boss-or-hostile reset admission predicate."""
    runtime = status.get("raid_runtime") or {}
    route = status.get("validation_route") or {}
    native = runtime.get("native_recovery") or {}
    attempt_id = int(runtime.get("attempt_id") or 0)
    assignment_generation = int(runtime.get("assignment_generation") or 0)
    route_generation = int(route.get("generation") or 0)
    route_node_id = str(route.get("node_id") or "")
    recovery_scope_matches = (
        attempt_id > 0
        and assignment_generation > 0
        and route_generation > 0
        and bool(route_node_id)
        and runtime.get("native_recovery_hold_active") is True
        and int(runtime.get("native_recovery_route_generation") or 0) == route_generation
        and str(runtime.get("native_recovery_node_id") or "") == route_node_id
    )
    boss_reset_observed = int(runtime.get("boss_reset_generation") or 0) > int(
        runtime.get("boss_reset_generation_at_wipe") or 0
    )
    hostile_reset_observed = (
        runtime.get("native_hostile_inactivity_observed") is True
        and int(runtime.get("native_hostile_reset_generation") or 0)
        > int(runtime.get("native_hostile_reset_generation_at_wipe") or 0)
        and int(runtime.get("native_hostile_observation_attempt_id") or 0) == attempt_id
        and int(runtime.get("native_hostile_observation_route_generation") or 0) == route_generation
        and str(runtime.get("native_hostile_observation_node_id") or "") == route_node_id
    )
    return (
        recovery_scope_matches
        and runtime.get("alive_size") == 10
        and runtime.get("encounter_in_progress") is False
        and int(runtime.get("wipe_generation") or 0) > 0
        and runtime.get("native_hostile_activity_active") is False
        and (boss_reset_observed or hostile_reset_observed)
        and native.get("death_observed") is True
        and native.get("corpse_observed") is True
        and native.get("release_observed") is True
        and native.get("resurrection_observed") is True
        and native.get("runback_observed") is True
        and native.get("ready_check_action_observed") is not True
    )


def semantic_progress_signature(status: dict[str, Any], diagnosis: dict[str, Any] | None) -> str:
    """Hash only raid facts whose change proves meaningful live progress.

    Timers, heartbeat counters, cumulative deaths and trace length are
    deliberately excluded. Boss health/phase, route state and native recovery
    generations are excluded when they only describe death/revive churn. A
    living but semantically wedged run can therefore be stopped for diagnosis
    without imposing a raid-duration deadline.
    """
    runtime = status.get("raid_runtime") if isinstance(status.get("raid_runtime"), dict) else {}
    route = status.get("validation_route") if isinstance(status.get("validation_route"), dict) else {}
    bot_progress: list[dict[str, Any]] = []
    if isinstance(diagnosis, dict):
        for row in diagnosis.get("bots") or []:
            if not isinstance(row, dict):
                continue
            identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
            snapshot = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {}
            progress = snapshot.get("route_progress") if isinstance(snapshot.get("route_progress"), dict) else {}
            target = progress.get("target") if isinstance(progress.get("target"), dict) else {}
            state = progress.get("state") if isinstance(progress.get("state"), dict) else {}
            bot_progress.append({
                "bot_guid": identity.get("bot_guid"),
                # Decision churn is diagnostic evidence, not objective
                # progress. Keep it in the immutable raw diagnose/trace rows,
                # but do not let alternating wrong actions reset this clock.
                "target": {key: target.get(key) for key in (
                    "guid", "entry", "hp_pct", "best_hp_pct",
                )},
            })
    payload = {
        "route": {key: route.get(key) for key in (
            "manifest_index", "generation", "node_id", "kind", "manifest_complete",
            "terminal_evidence", "boss_death_evidence",
        )},
        "raid": {key: runtime.get(key) for key in (
            "map_id", "instance_id", "lockout_save_id", "strategy_id",
            "boss_states", "encounter_phase",
        )},
        "metrics": {key: status.get(key) for key in (
            "kills", "raid_boss_kills",
        )},
        "bots": sorted(bot_progress, key=lambda row: int(row.get("bot_guid") or 0)),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(canonical).hexdigest()



def observe_monotonic_semantic_progress(
    state: dict[str, Any], status: dict[str, Any], diagnosis: dict[str, Any] | None,
) -> bool:
    """Update objective high-water marks and report genuine forward progress."""
    runtime = status.get("raid_runtime") if isinstance(status.get("raid_runtime"), dict) else {}
    route = status.get("validation_route") if isinstance(status.get("validation_route"), dict) else {}
    advanced = not state

    counters = {
        "route_generation": int(route.get("generation") or 0),
        "route_index": int(route.get("manifest_index") or 0),
        "route_terminal_count": len(route.get("terminal_evidence") or []),
        "boss_death_evidence_count": len(route.get("boss_death_evidence") or []),
        "kills": int(status.get("kills") or 0),
        "raid_boss_kills": int(status.get("raid_boss_kills") or 0),
        "boss_done_count": sum(1 for value in runtime.get("boss_states") or [] if value == 3),
    }
    high_water = state.setdefault("high_water", {})
    for key, value in counters.items():
        previous = int(high_water.get(key, -1))
        if value > previous:
            advanced = True
            high_water[key] = value

    # Combat metrics are useful semantic activity only when the producer has
    # explicitly scoped originated damage to the route generation currently
    # under observation.  Do not substitute healing, recovery churn, or raw
    # callback totals: those can move while the encounter is stalled, and the
    # raw callback stream may duplicate the same originated event.
    combat_metrics = (
        diagnosis.get("combat_metrics")
        if isinstance(diagnosis, dict)
        and isinstance(diagnosis.get("combat_metrics"), dict)
        else {}
    )
    route_generation = route.get("generation")
    route_node_id = route.get("node_id")
    metric_generation = combat_metrics.get("route_generation")
    metric_node_id = combat_metrics.get("route_node_id")
    party_damage = combat_metrics.get("party_damage")
    schema_basis_valid = (
        (
            combat_metrics.get("schema") == "bot_combat_metrics_v3"
            and combat_metrics.get("measurement_basis") == "hostile_originated_damage"
        )
        or (
            combat_metrics.get("schema") == "bot_combat_metrics_v2"
            and combat_metrics.get("measurement_basis") == "originated_damage"
        )
    )
    damage_scope_valid = (
        isinstance(route_generation, int)
        and not isinstance(route_generation, bool)
        and route_generation > 0
        and isinstance(route_node_id, str)
        and bool(route_node_id)
        and schema_basis_valid
        and isinstance(metric_generation, int)
        and not isinstance(metric_generation, bool)
        and metric_generation == route_generation
        and isinstance(metric_node_id, str)
        and metric_node_id == route_node_id
        and isinstance(party_damage, (int, float))
        and not isinstance(party_damage, bool)
        and isfinite(float(party_damage))
        and party_damage >= 0
    )
    if damage_scope_valid:
        damage_high_water = state.setdefault("originated_party_damage_high_water", {})
        damage_key = f"{route_generation}:{route_node_id}"
        previous_damage = damage_high_water.get(damage_key)
        if previous_damage is None:
            damage_high_water[damage_key] = party_damage
            # A positive first scoped observation is evidence of activity even
            # when the controller did not capture the initial zero baseline.
            if party_damage > 0:
                advanced = True
        elif party_damage > previous_damage:
            damage_high_water[damage_key] = party_damage
            advanced = True

    # Wipe/reset counters and aggregate native booleans are lifecycle churn,
    # not objective progress.  Record an exact-roster, per-member, ordered
    # native recovery proof for evidence, but never let death/revive churn
    # reset the semantic-progress clock. The proof identity deliberately
    # excludes recovery_generation so incrementing that counter cannot replay
    # stale evidence as a new completion.
    native = runtime.get("native_recovery") if isinstance(
        runtime.get("native_recovery"), dict
    ) else {}
    completion_scope: list[Any] | None = None
    evidence_sequence = int(runtime.get("evidence_sequence") or 0)
    attempt_id = int(runtime.get("attempt_id") or 0)
    wipe_generation = int(runtime.get("wipe_generation") or 0)
    assignment_generation = int(runtime.get("assignment_generation") or 0)
    expected_size = int(runtime.get("expected_size") or 0)
    roster = runtime.get("roster") if isinstance(runtime.get("roster"), list) else []
    roster_guids = sorted(
        int(row.get("guid") or 0) for row in roster
        if isinstance(row, dict) and int(row.get("guid") or 0) > 0
    )
    members = native.get("members") if isinstance(native.get("members"), list) else []
    ordered_members: list[list[int]] = []
    member_guids: list[int] = []
    member_sequences_valid = len(members) == expected_size == len(roster_guids) > 0
    sequence_fields = (
        "death_sequence", "corpse_sequence", "release_sequence",
        "runback_sequence", "reentry_sequence", "resurrection_sequence",
    )
    for member in members:
        if not isinstance(member, dict):
            member_sequences_valid = False
            continue
        guid = int(member.get("guid") or 0)
        sequences = [int(member.get(field) or 0) for field in sequence_fields]
        if (
            guid <= 0
            or int(member.get("wipe_generation") or 0) != wipe_generation
            or any(value <= 0 for value in sequences)
            or sequences != sorted(sequences)
            or len(set(sequences)) != len(sequences)
            or sequences[-1] > evidence_sequence
        ):
            member_sequences_valid = False
        member_guids.append(guid)
        ordered_members.append([guid, *sequences])
    ordered_members.sort()
    member_guids.sort()
    ready_sequence = int(native.get("ready_check_action_evidence_sequence") or 0)
    proof_valid = (
        native.get("evidence_complete") is True
        and all(native.get(field) is True for field in (
            "death_observed", "corpse_observed", "release_observed",
            "runback_observed", "resurrection_observed",
            "ready_check_action_observed",
        ))
        and evidence_sequence > 0 and attempt_id > 0 and wipe_generation > 0
        and assignment_generation > 0
        and int(native.get("recovery_wipe_generation") or 0) == wipe_generation
        and member_sequences_valid and member_guids == roster_guids
        and int(native.get("ready_check_action_generation") or 0) > 0
        and int(native.get("ready_check_response_count") or 0) == expected_size
        and int(native.get("ready_check_action_attempt_id") or 0) == attempt_id
        and int(native.get("ready_check_action_wipe_generation") or 0) == wipe_generation
        and int(native.get("ready_check_assignment_generation") or 0) == assignment_generation
        and ready_sequence > max((row[-1] for row in ordered_members), default=0)
        and ready_sequence <= evidence_sequence
    )
    if proof_valid:
        completion_scope = [
            attempt_id, wipe_generation, assignment_generation,
            ordered_members, ready_sequence,
        ]
    if completion_scope is not None:
        completed_scopes = state.setdefault("accepted_native_recovery_scopes", [])
        if completion_scope not in completed_scopes:
            completed_scopes.append(completion_scope)
            # A complete native death/revive cycle is retained for lifecycle
            # evidence, but it is not route progress. Otherwise repeated
            # recovery churn could keep an uncapped capture alive forever.

    if runtime.get("encounter_in_progress") is True and not state.get("engagement_observed"):
        state["engagement_observed"] = True
        advanced = True
    encounter_phase = str(runtime.get("encounter_phase") or "")
    observed_phases = state.setdefault("observed_encounter_phases", [])
    if encounter_phase and encounter_phase not in observed_phases:
        observed_phases.append(encounter_phase)
        advanced = True
    if route.get("manifest_complete") is True and not state.get("manifest_complete_observed"):
        state["manifest_complete_observed"] = True
        advanced = True

    lowest_hp = state.setdefault("lowest_target_hp", {})
    if isinstance(diagnosis, dict):
        for row in diagnosis.get("bots") or []:
            if not isinstance(row, dict):
                continue
            snapshot = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {}
            progress = snapshot.get("route_progress") if isinstance(snapshot.get("route_progress"), dict) else {}
            target = progress.get("target") if isinstance(progress.get("target"), dict) else {}
            # Runtime GUIDs change when the same native boss respawns after an
            # evade. Entry identity is the stable semantic target; a replacement
            # object alone must not keep an invalid pull loop alive forever.
            target_id = int(target.get("entry") or target.get("guid") or 0)
            hp = target.get("best_hp_pct", target.get("hp_pct"))
            if not target_id or not isinstance(hp, (int, float)) or hp <= 0:
                continue
            key = f"{int(runtime.get('instance_id') or 0)}:{int(route.get('generation') or 0)}:{target_id}"
            previous_hp = float(lowest_hp.get(key, 101.0))
            if float(hp) < previous_hp:
                lowest_hp[key] = float(hp)
                advanced = True
    return advanced
