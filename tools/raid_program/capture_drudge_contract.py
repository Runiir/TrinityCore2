from __future__ import annotations

from collections import Counter
from math import isfinite
from typing import Any

try:
    from tools.raid_program.capture_drudge_geometry import (
        _validate_drudge_observation_geometry,
    )
    from tools.raid_program.capture_value_types import _positive_int
except ModuleNotFoundError:
    from capture_drudge_geometry import _validate_drudge_observation_geometry
    from capture_value_types import _positive_int


def accepted_drudge_contract(
    statuses: list[dict[str, Any]],
    *,
    frozen_anchors: dict[int, tuple[float, float, float]] | None = None,
) -> tuple[bool, list[str]]:
    """Reconstruct the exact two-lane Drudge contract from native evidence.

    Stored counters and booleans are corroboration only. Acceptance is derived
    from the retained delivered observations, their exact source/target/scope,
    their per-roster reseparation acknowledgements, and the frozen role slots.
    """

    reasons: list[str] = []
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for status in statuses:
        runtime = status.get("raid_runtime") if isinstance(status, dict) else None
        evidence = runtime.get("drudge_charge") if isinstance(runtime, dict) else None
        if isinstance(evidence, dict) and evidence.get("evidence_route_generation") == 3:
            candidates.append((runtime, evidence))
    if not candidates:
        return False, ["drudge_evidence_missing"]

    def candidate_key(pair: tuple[dict[str, Any], dict[str, Any]]) -> tuple[int, int, int, int, int]:
        candidate_runtime, candidate_evidence = pair
        observations = candidate_evidence.get("observations")
        observations = observations if isinstance(observations, list) else []
        delivered_rows = [row for row in observations if isinstance(row, dict) and row.get("landed") is True]
        source_counts = Counter(row.get("source_spawn_id") for row in delivered_rows)
        roster_rows = candidate_runtime.get("roster")
        roster_set = {
            row.get("guid") for row in roster_rows
            if isinstance(row, dict) and _positive_int(row.get("guid"))
        } if isinstance(roster_rows, list) else set()
        tank_set = {
            row.get("guid") for row in roster_rows
            if isinstance(row, dict) and row.get("role") == "tank"
            and _positive_int(row.get("guid"))
        } if isinstance(roster_rows, list) else set()
        offensive_set = {
            row.get("guid") for row in roster_rows
            if isinstance(row, dict) and row.get("role") in {"tank", "dps"}
            and _positive_int(row.get("guid"))
        } if isinstance(roster_rows, list) else set()
        threat_seed = candidate_runtime.get("drudge_threat_seed")
        threat_seed_complete = (
            isinstance(threat_seed, dict)
            and threat_seed.get("closed") is True
            and threat_seed.get("complete") is True
            and threat_seed.get("failure") is False
        )
        def exact_set(field: str) -> set[int]:
            values = candidate_evidence.get(field)
            return set(values) if isinstance(values, list) and all(_positive_int(value) for value in values) else set()
        complete = int(
            len(delivered_rows) >= 4
            and source_counts.get(250140, 0) >= 2
            and source_counts.get(250141, 0) >= 2
            and all(isinstance(row.get("geometry"), dict) for row in delivered_rows)
            and exact_set("ownership_roster_guids") == tank_set
            and exact_set("health_sync_evaluated_roster_guids") == tank_set
            and exact_set("profile_action_roster_guids") == offensive_set
            and exact_set("health_sync_roster_guids")
            and exact_set("health_sync_roster_guids").issubset(tank_set)
            and candidate_evidence.get("health_sync_hold_source_spawn_id") in {250140, 250141}
            and _positive_int(candidate_evidence.get("health_sync_hold_tank_guid"))
            and _positive_int(candidate_evidence.get("death_evidence_sequence"))
            and _positive_int(candidate_evidence.get("rage_wait_evidence_sequence"))
            and _positive_int(candidate_evidence.get("rage_aura_evidence_sequence"))
            and threat_seed_complete
        )
        latest_observation = max(
            (int(row.get("sequence") or 0) for row in delivered_rows), default=0
        )
        evidence_sequence = int(candidate_runtime.get("evidence_sequence") or 0)
        return (
            complete,
            latest_observation,
            evidence_sequence,
            int(candidate_evidence.get("delivered_count") or 0),
            int(candidate_evidence.get("prepared_count") or 0),
        )

    _, (runtime, evidence) = max(
        enumerate(candidates), key=lambda indexed: (candidate_key(indexed[1]), indexed[0])
    )
    roster = runtime.get("roster")
    if not isinstance(roster, list) or len(roster) != 10:
        return False, ["drudge_exact_roster_missing"]
    roster_guids = {
        row.get("guid") for row in roster
        if isinstance(row, dict) and _positive_int(row.get("guid"))
    }
    if len(roster_guids) != 10:
        reasons.append("drudge_exact_roster_guids_invalid")
    tank_guids = {
        row.get("guid") for row in roster
        if isinstance(row, dict) and row.get("role") == "tank"
        and _positive_int(row.get("guid"))
    }
    offensive_guids = {
        row.get("guid") for row in roster
        if isinstance(row, dict) and row.get("role") in {"tank", "dps"}
        and _positive_int(row.get("guid"))
    }
    if len(tank_guids) != 2 or len(offensive_guids) != 7:
        reasons.append("drudge_frozen_role_slots_invalid")
    role_by_guid = {
        row.get("guid"): row.get("role")
        for row in roster
        if isinstance(row, dict) and _positive_int(row.get("guid"))
    }
    roster_by_guid = {
        row.get("guid"): row
        for row in roster
        if isinstance(row, dict) and _positive_int(row.get("guid"))
    }
    attempt_id = runtime.get("attempt_id")
    expected_observation_scope = (attempt_id, 0, 3)

    # A capture can contain statuses from an earlier attempt.  They are not
    # part of the selected immutable Drudge evidence scope and must neither
    # poison nor complete it.  Conversely, a status that claims the selected
    # attempt while carrying a different evidence scope is corrupt and fails
    # closed instead of being silently ignored.
    scoped_candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for candidate_runtime, candidate_evidence in candidates:
        if candidate_runtime.get("attempt_id") != attempt_id:
            continue
        candidate_scope = (
            candidate_evidence.get("evidence_attempt_id"),
            candidate_evidence.get("evidence_wipe_generation"),
            candidate_evidence.get("evidence_route_generation"),
        )
        if candidate_scope != expected_observation_scope:
            reasons.append("drudge_candidate_evidence_scope_mismatch")
            continue
        scoped_candidates.append((candidate_runtime, candidate_evidence))

    # A bad native delivery is permanently disqualifying for this capture,
    # even when a later status snapshot contains a clean-looking generation.
    # Otherwise a poisoned queue item could be hidden by selecting the latest
    # status and the resulting dataset would certify a formation that never
    # satisfied the native farthest-target selector.
    lane_a_slots = {1, 3, 4, 6, 7}
    for candidate_runtime, candidate_evidence in scoped_candidates:
        candidate_roster = candidate_runtime.get("roster")
        candidate_roles = {
            row.get("guid"): row
            for row in candidate_roster
            if isinstance(row, dict) and _positive_int(row.get("guid"))
        } if isinstance(candidate_roster, list) else {}
        candidate_observations = candidate_evidence.get("observations")
        if not isinstance(candidate_observations, list):
            continue
        for observation in candidate_observations:
            if not isinstance(observation, dict) or observation.get("landed") is not True:
                continue
            target_row = candidate_roles.get(observation.get("target_guid"))
            if target_row and target_row.get("role") == "tank":
                reasons.append("drudge_native_rush_target_tank")
            source = observation.get("source_spawn_id")
            if source not in {250140, 250141} or not target_row:
                continue
            target_slot = target_row.get("slot")
            if not isinstance(target_slot, int) or isinstance(target_slot, bool):
                continue
            target_slot += 1
            target_in_lane_a = target_slot in lane_a_slots
            source_in_lane_a = source == 250140
            if target_in_lane_a == source_in_lane_a:
                reasons.append("drudge_native_rush_lane_target_invalid")

    if evidence.get("evidence_attempt_id") != attempt_id:
        reasons.append("drudge_attempt_scope_mismatch")
    if evidence.get("evidence_wipe_generation") != 0:
        reasons.append("drudge_pre_magmaw_wipe_contamination")
    if evidence.get("queue_overflow") is not False:
        reasons.append("drudge_observation_queue_overflow")

    observations = evidence.get("observations")
    if not isinstance(observations, list):
        observations = []
        reasons.append("drudge_observations_missing")
    delivered = [
        row for row in observations
        if isinstance(row, dict) and row.get("landed") is True
    ]
    sequences = [row.get("sequence") for row in delivered]
    if (not sequences or any(not _positive_int(sequence) for sequence in sequences)
            or len(set(sequences)) != len(sequences)
            or sequences != sorted(sequences)):
        reasons.append("drudge_delivered_sequence_invalid")
    if evidence.get("delivered_count") != len(delivered):
        reasons.append("drudge_delivered_count_mismatch")
    prepared_count = evidence.get("prepared_count")
    if not isinstance(prepared_count, int) or isinstance(prepared_count, bool) \
            or prepared_count < len(delivered):
        reasons.append("drudge_prepared_count_invalid")

    exact_sources = {250140, 250141}
    reconstructed: dict[int, dict[str, int]] = {
        source: {"delivered": 0, "valid_intervals": 0, "source_guid": 0}
        for source in exact_sources
    }
    for row in delivered:
        source = row.get("source_spawn_id")
        if (row.get("attempt_id") != attempt_id
                or row.get("wipe_generation") != 0
                or row.get("route_generation") != 3):
            reasons.append("drudge_observation_scope_mismatch")
        if source not in exact_sources:
            reasons.append("drudge_observation_source_invalid")
            continue
        source_guid = row.get("source_guid")
        if not _positive_int(source_guid):
            reasons.append("drudge_observation_source_guid_invalid")
        elif reconstructed[source]["source_guid"] not in {0, source_guid}:
            reasons.append("drudge_observation_source_guid_drift")
        else:
            reconstructed[source]["source_guid"] = source_guid
        if row.get("target_guid") not in roster_guids:
            reasons.append("drudge_observation_target_not_in_roster")
        # The native Drudge Rush is the farthest-player selector.  A tank
        # target proves that the two non-tank lanes were not separated before
        # the cast and would make the capture a formation failure rather than
        # a valid two-group mechanic observation.
        if role_by_guid.get(row.get("target_guid")) == "tank":
            reasons.append("drudge_native_rush_target_tank")
        distance = row.get("selected_distance")
        source_reach = row.get("source_combat_reach")
        target_reach = row.get("target_combat_reach")
        reach_values = (source_reach, target_reach)
        native_range = (
            isinstance(distance, (int, float)) and not isinstance(distance, bool)
            and isfinite(float(distance)) and float(distance) >= 0.0
            and all(isinstance(value, (int, float)) and not isinstance(value, bool)
                    and isfinite(float(value)) and 0.0 <= float(value) <= 100.0
                    for value in reach_values)
            and row.get("same_map") is True and row.get("same_phase") is True
            and float(distance) < 80.0 + float(source_reach) + float(target_reach)
        )
        if row.get("range_valid") is not native_range or not native_range:
            reasons.append("drudge_observation_range_invalid")
        reconstructed[source]["delivered"] += 1
        interval = row.get("observed_interval_ms")
        if isinstance(interval, int) and not isinstance(interval, bool) and interval > 0:
            if interval < 20000 or row.get("interval_valid") is not True:
                reasons.append("drudge_observation_interval_invalid")
            else:
                reconstructed[source]["valid_intervals"] += 1
        acknowledgements = row.get("reseparated_roster_guids")
        if not isinstance(acknowledgements, list) or set(acknowledgements) != roster_guids:
            reasons.append("drudge_observation_not_reseparated_by_exact_roster")
        # Geometry is immutable evidence for the acknowledgement.  Never
        # accept a stored reseparation bit/acknowledgement without rebuilding
        # the lane, tank, and member-anchor predicates from coordinates.
        reasons.extend(_validate_drudge_observation_geometry(
            row, roster, tank_guids, frozen_anchors=frozen_anchors,
        ))

    for source in exact_sources:
        if reconstructed[source]["delivered"] < 2:
            reasons.append(f"drudge_source_{source}_two_deliveries_missing")
        if reconstructed[source]["valid_intervals"] < 1:
            reasons.append(f"drudge_source_{source}_native_interval_missing")
    source_guids = {reconstructed[source]["source_guid"] for source in exact_sources}
    if 0 in source_guids or len(source_guids) != len(exact_sources):
        reasons.append("drudge_exact_source_runtime_guids_invalid")

    # The native selector is acceptance evidence, not a claim supplied by the
    # bot policy.  Reconstruct the candidate predicate from the exact roster
    # and the serialized core threat-list snapshot.  The runtime intentionally
    # bounds this list; a missing, truncated, or internally inconsistent first
    # Rush snapshot cannot prove selector fidelity and therefore fails closed.
    native_candidate_snapshot_signatures: dict[int, tuple[Any, ...]] = {}
    native_candidate_rows_by_guid: dict[int, dict[int, dict[str, Any]]] = {}
    native_candidate_eligible_guids_by_source: dict[int, set[int]] = {}
    native_first_rush_observed_at_ms: dict[int, int] = {}
    native_first_rush_landed_by_key: dict[tuple[Any, ...], bool] = {}
    native_first_rush_identity_by_key: dict[tuple[Any, ...], tuple[Any, ...]] = {}
    native_candidate_tolerance = 0.05
    complete_candidate_snapshots = []
    for candidate_runtime, candidate_evidence in scoped_candidates:
        observations = candidate_evidence.get("observations")
        observations = observations if isinstance(observations, list) else []
        observed_sources = {
            row.get("source_spawn_id") for row in observations
            if isinstance(row, dict)
        }
        if exact_sources.issubset(observed_sources):
            complete_candidate_snapshots.append((candidate_runtime, candidate_evidence))
    if not complete_candidate_snapshots:
        for source in exact_sources:
            reasons.append(f"drudge_native_threat_source_{source}_first_rush_missing")
    for candidate_runtime, candidate_evidence in complete_candidate_snapshots:
        candidate_observations = candidate_evidence.get("observations")
        if not isinstance(candidate_observations, list):
            reasons.append("drudge_native_threat_candidates_observations_missing")
            continue
        candidate_roster = candidate_runtime.get("roster")
        candidate_roster_by_guid = {
            row.get("guid"): row
            for row in candidate_roster
            if isinstance(row, dict) and _positive_int(row.get("guid"))
        } if isinstance(candidate_roster, list) else {}
        for source in exact_sources:
            source_observations = [
                row for row in candidate_observations
                if isinstance(row, dict) and row.get("source_spawn_id") == source
            ]
            if not source_observations:
                reasons.append(f"drudge_native_threat_source_{source}_first_rush_missing")
                continue
            first_observation = min(
                source_observations,
                key=lambda row: (
                    int(row.get("sequence") or 0),
                    int(row.get("observed_at_ms") or 0),
                ),
            )
            observation_scope = (
                first_observation.get("attempt_id"),
                first_observation.get("wipe_generation"),
                first_observation.get("route_generation"),
            )
            if observation_scope != expected_observation_scope:
                reasons.append("drudge_native_threat_observation_scope_drift")
                continue
            first_time = first_observation.get("observed_at_ms")
            sequence = first_observation.get("sequence")
            if not _positive_int(sequence):
                reasons.append("drudge_native_threat_observation_sequence_invalid")
            else:
                landing_key = (*expected_observation_scope, source, int(sequence))
                observation_identity = (
                    first_observation.get("source_guid"),
                    first_observation.get("target_guid"),
                    first_observation.get("target_raw_guid"),
                    first_observation.get("observed_at_ms"),
                    first_observation.get("observed_interval_ms"),
                    first_observation.get("selected_distance"),
                    first_observation.get("source_combat_reach"),
                    first_observation.get("target_combat_reach"),
                    first_observation.get("same_map"),
                    first_observation.get("same_phase"),
                    first_observation.get("range_valid"),
                )
                prior_identity = native_first_rush_identity_by_key.get(landing_key)
                if prior_identity is not None and prior_identity != observation_identity:
                    reasons.append("drudge_native_threat_observation_identity_drift")
                    continue
                native_first_rush_identity_by_key[landing_key] = observation_identity
                if _positive_int(first_time):
                    prior_time = native_first_rush_observed_at_ms.get(source)
                    if prior_time is not None and prior_time != int(first_time):
                        reasons.append("drudge_native_threat_observation_identity_drift")
                        continue
                    native_first_rush_observed_at_ms[source] = int(first_time)
                landed_value = first_observation.get("landed")
                if not isinstance(landed_value, bool):
                    reasons.append("drudge_native_threat_landing_type_invalid")
                    continue
                landed = landed_value
                prior_landed = native_first_rush_landed_by_key.get(landing_key)
                # A status sampled between SpellStarted and SpellLanded is a
                # legitimate partial observation.  Preserve the edge, merge
                # the later landing monotonically, and reject only an actual
                # true -> false regression.  Treating the early false row as
                # permanently disqualifying made a native landed Rush fail
                # capture even though every later scoped status retained it.
                if prior_landed is True and not landed:
                    reasons.append("drudge_native_threat_landing_regressed")
                native_first_rush_landed_by_key[landing_key] = bool(
                    prior_landed or landed
                )
            candidate_rows = first_observation.get("native_threat_candidates")
            if not isinstance(candidate_rows, list):
                reasons.append("drudge_native_threat_candidates_missing")
                continue
            count = first_observation.get("native_threat_candidates_count")
            complete = first_observation.get("native_threat_candidates_complete")
            truncated = first_observation.get("native_threat_candidates_truncated")
            if (not isinstance(count, int) or isinstance(count, bool) or count < 0
                    or complete is not True or truncated is not False
                    or count != len(candidate_rows) or count > 32):
                reasons.append("drudge_native_threat_candidates_metadata_invalid")
                if truncated is True or (isinstance(count, int) and count > len(candidate_rows)):
                    reasons.append("drudge_native_threat_candidates_truncated")
                continue

            source_lane = 0 if source == 250140 else 1
            expected_candidates: list[dict[str, Any]] = []
            reconstructed_native_selector_guids: set[int] = set()
            reconstructed_tactic_guids: set[int] = set()
            seen_raw_guids: set[int] = set()
            for candidate in candidate_rows:
                if not isinstance(candidate, dict):
                    reasons.append("drudge_native_threat_candidate_invalid")
                    continue
                guid = candidate.get("guid")
                raw_guid = candidate.get("raw_guid")
                if (not _positive_int(guid) or not _positive_int(raw_guid)
                        or raw_guid in seen_raw_guids):
                    reasons.append("drudge_native_threat_candidate_identity_invalid")
                    continue
                seen_raw_guids.add(raw_guid)
                distance = candidate.get("distance")
                threat = candidate.get("threat")
                if (not isinstance(distance, (int, float)) or isinstance(distance, bool)
                        or not isfinite(float(distance)) or distance < 0.0
                        or not isinstance(threat, (int, float)) or isinstance(threat, bool)
                        or not isfinite(float(threat)) or threat < 0.0):
                    reasons.append("drudge_native_threat_candidate_measurement_invalid")
                    continue
                boolean_fields = (
                    "is_player", "alive", "same_map", "same_phase", "available", "line_of_sight",
                    "in_range", "native_combat_range", "cross_lane", "native_selector_eligible",
                    "tactic_cross_lane_eligible",
                )
                if any(not isinstance(candidate.get(field), bool) for field in boolean_fields):
                    reasons.append("drudge_native_threat_candidate_flags_invalid")
                    continue
                is_player = candidate.get("is_player") is True
                roster_row = roster_by_guid.get(guid) if is_player else None
                candidate_runtime_row = candidate_roster_by_guid.get(guid) if is_player else None
                registered = isinstance(roster_row, dict)
                role = roster_row.get("role") if registered else "unregistered"
                slot = (roster_row.get("slot") + 1) if registered and isinstance(roster_row.get("slot"), int) else 0
                lane = (
                    0 if slot in lane_a_slots else 1
                ) if registered else 0
                active_lease = bool(
                    registered and roster_row.get("active") is True
                    and roster_row.get("lease_owned") is True
                )
                expected_in_range = float(distance) <= 80.0
                source_reach = candidate.get("source_combat_reach")
                candidate_reach = candidate.get("candidate_combat_reach")
                reaches_valid = all(
                    isinstance(value, (int, float)) and not isinstance(value, bool)
                    and isfinite(float(value)) and 0.0 <= float(value) <= 100.0
                    for value in (source_reach, candidate_reach)
                )
                expected_native_combat_range = bool(
                    reaches_valid
                    and candidate.get("same_map") is True
                    and candidate.get("same_phase") is True
                    and float(distance) < 80.0 + float(source_reach) + float(candidate_reach)
                )
                expected_cross_lane = registered and lane != source_lane
                expected_native_selector_eligible = (
                    candidate.get("is_player") is True
                    and candidate.get("available") is True
                    and candidate.get("line_of_sight") is True
                    and expected_native_combat_range
                )
                expected_tactic_eligible = (
                    expected_native_selector_eligible
                    and registered
                    and active_lease
                    and candidate.get("alive") is True
                    and candidate.get("same_map") is True
                    and expected_cross_lane
                    and role != "tank"
                )
                if ((is_player and (not registered or candidate_runtime_row is None))
                        or (not is_player and (registered or candidate_runtime_row is not None))
                        or (is_player and raw_guid != guid)
                        or candidate.get("role") != role
                        or candidate.get("slot") != slot
                        or candidate.get("lane") != lane
                        or candidate.get("in_range") is not expected_in_range
                        or candidate.get("native_combat_range") is not expected_native_combat_range
                        or candidate.get("cross_lane") is not expected_cross_lane
                        or candidate.get("native_selector_eligible") is not expected_native_selector_eligible
                        or candidate.get("tactic_cross_lane_eligible") is not expected_tactic_eligible):
                    reasons.append("drudge_native_threat_candidate_eligibility_mismatch")
                if expected_native_selector_eligible:
                    reconstructed_native_selector_guids.add(raw_guid)
                if expected_tactic_eligible:
                    reconstructed_tactic_guids.add(raw_guid)
                expected_candidates.append(candidate)

            if len(seen_raw_guids) != len(candidate_rows):
                reasons.append("drudge_native_threat_candidate_identity_invalid")
            if not expected_candidates:
                reasons.append(f"drudge_native_threat_source_{source}_candidate_list_empty")
                continue
            eligible_candidates = [
                row for row in expected_candidates
                if row.get("raw_guid") in reconstructed_native_selector_guids
            ]
            target_guid = first_observation.get("target_guid")
            target_raw_guid = first_observation.get("target_raw_guid")
            target = next((row for row in expected_candidates if row.get("raw_guid") == target_raw_guid), None)
            if (not _positive_int(target_raw_guid) or target is None
                    or target_raw_guid not in reconstructed_native_selector_guids
                    or target.get("guid") != target_guid):
                reasons.append("drudge_native_threat_selected_target_ineligible")
            else:
                if target_raw_guid not in reconstructed_tactic_guids:
                    reasons.append("drudge_native_threat_selected_target_not_cross_lane_tactic")
                selected_distance = first_observation.get("selected_distance")
                if (not isinstance(selected_distance, (int, float))
                        or isinstance(selected_distance, bool)
                        or abs(float(selected_distance) - float(target.get("distance"))) > native_candidate_tolerance):
                    reasons.append("drudge_native_threat_selected_distance_mismatch")
                if eligible_candidates:
                    farthest_distance = max(float(row.get("distance")) for row in eligible_candidates)
                    if farthest_distance - float(target.get("distance")) > native_candidate_tolerance:
                        reasons.append("drudge_native_threat_selected_target_not_farthest")
                else:
                    reasons.append(f"drudge_native_threat_source_{source}_eligible_candidates_missing")

            # Repeated status snapshots must retain the exact first-Rush
            # candidate set.  Do not let a later forged list erase it.
            signature = tuple(
                tuple(sorted(row.items())) for row in sorted(expected_candidates, key=lambda row: row.get("guid", 0))
            )
            previous_signature = native_candidate_snapshot_signatures.get(source)
            if previous_signature is not None and previous_signature != signature:
                reasons.append("drudge_native_threat_candidate_snapshot_drift")
            else:
                native_candidate_snapshot_signatures[source] = signature
                native_candidate_rows_by_guid[source] = {
                    row.get("guid"): row for row in expected_candidates
                    if row.get("is_player") is True
                }
                native_candidate_eligible_guids_by_source[source] = {
                    row.get("guid") for row in expected_candidates
                    if row.get("raw_guid") in reconstructed_tactic_guids
                }

    for source in exact_sources:
        source_landings = [
            landed for landing_key, landed
            in native_first_rush_landed_by_key.items()
            if landing_key[3] == source
        ]
        if not source_landings or not any(source_landings):
            reasons.append(f"drudge_native_threat_source_{source}_first_rush_not_landed")

    # The pre-first-Rush seed is a bounded, real profile action rather than a
    # threat-manager shortcut.  Reconstruct both cross-lane rows and all
    # safety/authority predicates from the serialized evidence.
    threat_seed = runtime.get("drudge_threat_seed")
    if not isinstance(threat_seed, dict):
        reasons.append("drudge_threat_seed_missing")
    else:
        if (threat_seed.get("attempt_id") != attempt_id
                or threat_seed.get("wipe_generation") != 0
                or threat_seed.get("route_generation") != 3):
            reasons.append("drudge_threat_seed_scope_mismatch")
        if threat_seed.get("closed") is not True:
            reasons.append("drudge_threat_seed_not_closed_by_native_rush")
        if threat_seed.get("complete") is not True:
            reasons.append("drudge_threat_seed_incomplete")
        if threat_seed.get("failure") is not False:
            reasons.append("drudge_threat_seed_failure")

        seed_roster_value = threat_seed.get("roster_guids")
        seed_roster = (
            set(seed_roster_value)
            if isinstance(seed_roster_value, list)
            and all(_positive_int(guid) for guid in seed_roster_value)
            and len(set(seed_roster_value)) == len(seed_roster_value)
            else set()
        )
        if len(seed_roster) != 2 or not seed_roster.issubset(roster_guids):
            reasons.append("drudge_threat_seed_roster_invalid")

        seed_observations = threat_seed.get("observations")
        if not isinstance(seed_observations, list):
            seed_observations = []
            reasons.append("drudge_threat_seed_observations_missing")
        successful_seed_rows = []
        successful_source_lanes: set[int] = set()
        successful_member_guids: set[int] = set()
        expected_seed_source = {0: 250140, 1: 250141}
        first_native_observation_ms: dict[int, int] = {}
        for native_row in delivered:
            native_source = native_row.get("source_spawn_id")
            native_time = native_row.get("observed_at_ms")
            if (native_source in exact_sources and _positive_int(native_time)
                    and (native_source not in first_native_observation_ms
                         or native_time < first_native_observation_ms[native_source])):
                first_native_observation_ms[native_source] = native_time
        for row in seed_observations:
            if not isinstance(row, dict):
                reasons.append("drudge_threat_seed_observation_invalid")
                continue
            if (row.get("attempt_id") != attempt_id
                    or row.get("wipe_generation") != 0
                    or row.get("route_generation") != 3):
                reasons.append("drudge_threat_seed_observation_scope_mismatch")
            source_lane = row.get("source_lane")
            member_lane = row.get("member_lane")
            source_spawn = row.get("source_spawn_id")
            member_guid = row.get("member_guid")
            if source_lane not in {0, 1} or member_lane not in {0, 1}:
                reasons.append("drudge_threat_seed_lane_invalid")
                continue
            if source_spawn != expected_seed_source[source_lane]:
                reasons.append("drudge_threat_seed_source_lane_invalid")
            if member_lane != 1 - source_lane:
                reasons.append("drudge_threat_seed_cross_lane_invalid")
            member_row = next(
                (member for member in roster
                 if isinstance(member, dict) and member.get("guid") == member_guid),
                None,
            )
            if (not _positive_int(member_guid) or member_guid not in roster_guids
                    or not isinstance(member_row, dict)
                    or member_row.get("role") != "dps"):
                reasons.append("drudge_threat_seed_member_identity_invalid")
            elif member_row.get("slot") != (row.get("member_slot") or 0) - 1:
                reasons.append("drudge_threat_seed_member_slot_invalid")
            if row.get("source_guid") != reconstructed.get(source_spawn, {}).get("source_guid"):
                reasons.append("drudge_threat_seed_source_identity_invalid")
            seed_time = row.get("observed_at_ms")
            first_native_time = first_native_observation_ms.get(source_spawn)
            if (row.get("action_succeeded") is True
                    and (not _positive_int(seed_time)
                         or not _positive_int(first_native_time)
                         or seed_time >= first_native_time)):
                reasons.append("drudge_threat_seed_not_pre_first_rush")
            distance = row.get("selected_distance")
            minimum = row.get("min_range")
            maximum = row.get("max_range")
            if (not isinstance(distance, (int, float)) or isinstance(distance, bool)
                    or not isfinite(float(distance)) or distance < 0.0 or distance > 80.0
                    or not isinstance(minimum, (int, float)) or isinstance(minimum, bool)
                    or not isfinite(float(minimum)) or minimum < 0.0
                    or not isinstance(maximum, (int, float)) or isinstance(maximum, bool)
                    or not isfinite(float(maximum)) or maximum < 0.0
                    or (maximum > 0.0 and distance > maximum)
                    or distance < minimum):
                reasons.append("drudge_threat_seed_range_invalid")
            if (row.get("position_safe") is not True
                    or row.get("line_of_sight") is not True
                    or row.get("in_range") is not True
                    or row.get("profile_action_valid") is not True
                    or row.get("action_succeeded") is not True
                    or row.get("selected_offense_unsuppressed") is not True
                    or row.get("other_offense_suppressed") is not True):
                reasons.append("drudge_threat_seed_safety_evidence_invalid")
            if (not _positive_int(row.get("spell_id"))
                    or not isinstance(row.get("action_debug_name"), str)
                    or not row.get("action_debug_name", "").strip()
                    or not isinstance(row.get("action_result"), str)
                    or not row.get("action_result", "").strip()):
                reasons.append("drudge_threat_seed_profile_action_invalid")
            if row.get("action_succeeded") is True:
                successful_seed_rows.append(row)
                successful_source_lanes.add(source_lane)
                if _positive_int(member_guid):
                    successful_member_guids.add(member_guid)

        if successful_source_lanes != {0, 1}:
            reasons.append("drudge_threat_seed_source_lanes_incomplete")
        if len(successful_seed_rows) != 2:
            reasons.append("drudge_threat_seed_success_count_invalid")
        if len(successful_member_guids) != 2 or successful_member_guids != seed_roster:
            reasons.append("drudge_threat_seed_roster_evidence_mismatch")
        for row in successful_seed_rows:
            source = row.get("source_spawn_id")
            member_guid = row.get("member_guid")
            candidate = native_candidate_rows_by_guid.get(source, {}).get(member_guid)
            if candidate is None:
                reasons.append("drudge_native_threat_seed_member_missing_from_candidates")
                continue
            if (member_guid not in native_candidate_eligible_guids_by_source.get(source, set())
                    or candidate.get("role") != "dps"
                    or candidate.get("cross_lane") is not True):
                reasons.append("drudge_native_threat_seed_member_ineligible")
            seed_time = row.get("observed_at_ms")
            first_time = native_first_rush_observed_at_ms.get(source)
            if (not _positive_int(seed_time) or not _positive_int(first_time)
                    or int(seed_time) >= int(first_time)):
                reasons.append("drudge_native_threat_seed_timing_link_invalid")

    death_fields = (
        "death_attempt_id", "death_wipe_generation", "death_route_generation",
        "death_source_spawn_id", "death_source_guid", "survivor_source_spawn_id",
        "survivor_source_guid", "death_evidence_sequence",
        "rage_wait_evidence_sequence", "rage_aura_evidence_sequence",
    )
    death_values = {field: evidence.get(field) for field in death_fields}
    if (death_values["death_attempt_id"] != attempt_id
            or death_values["death_wipe_generation"] != 0
            or death_values["death_route_generation"] != 3):
        reasons.append("drudge_death_scope_mismatch")
    if (not isinstance(death_values["death_source_spawn_id"], int)
            or isinstance(death_values["death_source_spawn_id"], bool)
            or not isinstance(death_values["survivor_source_spawn_id"], int)
            or isinstance(death_values["survivor_source_spawn_id"], bool)
            or death_values["death_source_spawn_id"] not in exact_sources
            or death_values["survivor_source_spawn_id"] not in exact_sources
            or death_values["death_source_spawn_id"] == death_values["survivor_source_spawn_id"]
            or not _positive_int(death_values["death_source_guid"])
            or not _positive_int(death_values["survivor_source_guid"])
            or death_values["death_source_guid"] != reconstructed[death_values["death_source_spawn_id"]]["source_guid"]
            or death_values["survivor_source_guid"] != reconstructed[death_values["survivor_source_spawn_id"]]["source_guid"]):
        reasons.append("drudge_death_source_identity_mismatch")
    if (not all(_positive_int(death_values[field]) for field in (
            "death_evidence_sequence", "rage_wait_evidence_sequence",
            "rage_aura_evidence_sequence"))
            or not (death_values["death_evidence_sequence"]
                    < death_values["rage_wait_evidence_sequence"]
                    < death_values["rage_aura_evidence_sequence"])):
        reasons.append("drudge_native_rage_transition_order_invalid")

    source_rows = evidence.get("sources")
    source_summary = {
        row.get("spawn_id"): row for row in source_rows
        if isinstance(row, dict)
    } if isinstance(source_rows, list) else {}
    if set(source_summary) != exact_sources:
        reasons.append("drudge_source_summary_identity_mismatch")
    else:
        for source in exact_sources:
            if source_summary[source].get("delivered_count") != reconstructed[source]["delivered"]:
                reasons.append("drudge_source_delivered_summary_mismatch")
            if source_summary[source].get("valid_interval_count") != reconstructed[source]["valid_intervals"]:
                reasons.append("drudge_source_interval_summary_mismatch")

    def exact_guid_set(field: str) -> set[int]:
        value = evidence.get(field)
        if not isinstance(value, list) or any(not _positive_int(guid) for guid in value):
            reasons.append(f"drudge_{field}_invalid")
            return set()
        result = set(value)
        if len(result) != len(value) or not result.issubset(roster_guids):
            reasons.append(f"drudge_{field}_identity_mismatch")
        return result

    reseparated = exact_guid_set("reseparated_roster_guids")
    taunts = exact_guid_set("taunt_roster_guids")
    health_sync = exact_guid_set("health_sync_roster_guids")
    health_sync_evaluated = exact_guid_set("health_sync_evaluated_roster_guids")
    profile_actions = exact_guid_set("profile_action_roster_guids")
    ownership = exact_guid_set("ownership_roster_guids")
    if ownership != tank_guids:
        reasons.append("drudge_exact_tank_ownership_missing")
    if reseparated != roster_guids:
        reasons.append("drudge_exact_roster_reseparation_missing")
    if not taunts.issubset(tank_guids):
        reasons.append("drudge_taunt_evidence_identity_mismatch")
    if not health_sync.issubset(tank_guids):
        reasons.append("drudge_tank_health_sync_hold_identity_mismatch")
    if not health_sync:
        reasons.append("drudge_tank_health_sync_hold_missing")
    hold_source = evidence.get("health_sync_hold_source_spawn_id")
    hold_tank = evidence.get("health_sync_hold_tank_guid")
    hold_lower = evidence.get("health_sync_hold_lower_pct")
    hold_peer = evidence.get("health_sync_hold_peer_pct")
    hold_lower_alive = evidence.get("health_sync_hold_lower_alive")
    hold_peer_alive = evidence.get("health_sync_hold_peer_alive")
    expected_hold_tank = {250140: next((row.get("guid") for row in roster if row.get("slot") == 0), None),
                          250141: next((row.get("guid") for row in roster if row.get("slot") == 1), None)}
    if (not health_sync or hold_tank not in health_sync
            or hold_source not in expected_hold_tank
            or hold_tank != expected_hold_tank.get(hold_source)):
        reasons.append("drudge_health_sync_hold_source_identity_mismatch")
    if (not isinstance(hold_lower, (int, float)) or isinstance(hold_lower, bool)
            or not isinstance(hold_peer, (int, float)) or isinstance(hold_peer, bool)
            or not isfinite(float(hold_lower)) or not isfinite(float(hold_peer))
            or hold_lower <= 0.0 or hold_peer <= 0.0
            or hold_lower >= hold_peer
            or hold_lower_alive is not True or hold_peer_alive is not True):
        reasons.append("drudge_health_sync_hold_order_invalid")
    if health_sync_evaluated != tank_guids:
        reasons.append("drudge_exact_tank_health_sync_evaluation_missing")
    if evidence.get("health_sync_evidence_attempt_id") != attempt_id:
        reasons.append("drudge_health_sync_scope_attempt_mismatch")
    if evidence.get("health_sync_evidence_wipe_generation") != 0:
        reasons.append("drudge_health_sync_scope_wipe_mismatch")
    if evidence.get("health_sync_evidence_route_generation") != 3:
        reasons.append("drudge_health_sync_scope_route_mismatch")
    if profile_actions != offensive_guids:
        reasons.append("drudge_trained_single_target_profile_missing")

    # Entrance pulling deliberately leaves the native Rush target to the core
    # selector. Seed and cross-lane-target rows remain useful diagnostics, but
    # they no longer gate a valid exact-Drudge pull, tank-ownership proof,
    # reseparation, kill synchronization, or trained-profile execution.
    non_gating = {
        "drudge_native_rush_lane_target_invalid",
        "drudge_native_threat_selected_target_not_cross_lane_tactic",
    }
    reasons = [reason for reason in reasons
               if reason not in non_gating
               and not reason.startswith("drudge_threat_seed_")
               and not reason.startswith("drudge_native_threat_seed_")]
    return not reasons, sorted(set(reasons))
