"""Read native cohort state without owning the shared server lifecycle.

This is a simultaneous-instance admission check, not boss completion or proof
of callback/stop isolation. Those require subsequent attributed live outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from tools.bot_ml.run_live_bot_validation import CohortCommandExecutor, parse_json_objects


@dataclass(frozen=True)
class InstanceExpectation:
    cohort_id: str
    map_id: int
    difficulty: int
    roster_guids: frozenset[int]

    def __post_init__(self) -> None:
        if (type(self.map_id) is not int or self.map_id < 0
                or type(self.difficulty) is not int or self.difficulty < 0
                or not self.roster_guids
                or any(type(guid) is not int or guid <= 0 for guid in self.roster_guids)):
            raise ValueError("invalid expected native instance identity")


ObservationRecorder = Callable[[str, str, int, bool], None]


def observe(
    executor: CohortCommandExecutor,
    recorder: ObservationRecorder | None = None,
) -> dict[str, Any]:
    result = {}
    for name, command in (
        ("status", executor.status_command),
        ("diagnosis", f".botauto diagnose {executor.cohort_id} all"),
    ):
        output, code, timed_out = executor.run(command)
        if recorder is not None:
            recorder(command, output, code, timed_out)
        action = "botauto_status" if name == "status" else "botauto_diagnose"
        rows = [row for row in parse_json_objects(output) if row.get("action") == action]
        if code or timed_out or len(rows) != 1:
            raise ValueError(f"{name}: unavailable or ambiguous native response")
        row = rows[0]
        if (row.get("ok") is not True or row.get("failure_reason")
                or row.get("cohort_id") != executor.cohort_id):
            raise ValueError(f"{name}: rejected or foreign native response")
        result[name] = row
    return result


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label}: missing or invalid native integer")
    return value


def validate_instance(observation: dict[str, Any], expected: InstanceExpectation) -> dict[str, Any]:
    status, diagnosis = observation["status"], observation["diagnosis"]
    for row in (status, diagnosis):
        if (row.get("ok") is not True or row.get("failure_reason")
                or row.get("cohort_id") != expected.cohort_id):
            raise ValueError("foreign or failed cohort snapshot")
    if status.get("active") is not True:
        raise ValueError("cohort inactive")
    raid = status["raid_runtime"]
    epoch = _integer(status.get("server_epoch"), "server_epoch", 1)
    attempt = _integer(status.get("attempt_id"), "attempt_id", 1)
    for snapshot in (raid, diagnosis["raid_runtime"]):
        for field, value in (("server_epoch", epoch), ("attempt_id", attempt),
                             ("map_id", expected.map_id), ("map_difficulty", expected.difficulty)):
            if _integer(snapshot.get(field), field) != value:
                raise ValueError(f"{field}: native identity mismatch")
        if snapshot.get("bot_actions_enabled") is not True:
            raise ValueError("cohort not admitted")
        if snapshot.get("roster_complete") is not True:
            raise ValueError("native roster readback incomplete")
    instance = _integer(raid.get("instance_id"), "instance_id", 1)
    group = _integer(raid.get("group_guid"), "group_guid", 1)
    for field, value in (("instance_id", instance), ("group_guid", group)):
        if _integer(diagnosis["raid_runtime"].get(field), field, 1) != value:
            raise ValueError(f"{field}: observation changed while polling")
    guids = []
    recovering = 0
    for bot in diagnosis["bots"]:
        guids.append(_integer(bot["identity"].get("bot_guid"), "bot_guid", 1))
        scope = bot["snapshot"]["validation_cohort"]
        # Admission receipts retain the initial map. Read current native state.
        if (scope.get("locked") is not True
                or type(scope.get("in_world")) is not bool
                or scope.get("matches_cohort") is not True
                or scope.get("violation") is not False):
            raise ValueError("member outside its admitted native instance")
        current_map = _integer(scope.get("current_map_id"), "current_map_id")
        current_instance = _integer(scope.get("current_instance_id"), "current_instance_id")
        if (not scope["in_world"] or (current_map, current_instance) != (expected.map_id, instance)
                or (scope.get("ghost") is True and scope.get("alive") is False)):
            recovery = bot["snapshot"].get("native_recovery_episode", {})
            # Native matches_cohort verifies the corpse owner in the frozen
            # instance. Living players never receive this runback exception.
            if (scope.get("alive") is not False or scope.get("ghost") is not True
                    or scope.get("has_corpse") is not True
                    or _integer(scope.get("map_id"), "frozen_map_id") != expected.map_id
                    or _integer(scope.get("instance_id"), "frozen_instance_id", 1) != instance
                    or _integer(recovery.get("attempt_id"), "recovery_attempt", 1) != attempt
                    or recovery.get("phase") not in {
                        "released_ghost_observed", "entrance_unavailable", "moving_to_entrance",
                        "entrance_submitted", "entrance_worldport_pending", "corpse_authority_wait",
                        "moving_to_corpse", "reclaim_delay_pending", "reclaim_submitted",
                    }):
                raise ValueError("member outside its admitted native instance without valid recovery")
            if not scope["in_world"] and recovery["phase"] not in {
                "released_ghost_observed", "entrance_submitted", "entrance_worldport_pending",
            }:
                raise ValueError("member absent outside native recovery transfer")
            recovering += 1
    for snapshot in (raid, diagnosis["raid_runtime"]):
        if snapshot.get("difficulty_readback_complete") is True and snapshot.get("difficulty_matches") is True:
            continue
        # Difficulty readback intentionally counts only current raid members.
        # Status and diagnosis are sequential; more deaths may occur between
        # them, so require a bounded deficit, not identical cached counts.
        count = _integer(snapshot.get("difficulty_member_count"), "difficulty_member_count")
        matching = _integer(snapshot.get("difficulty_matching_member_count"), "difficulty_matching_member_count")
        newer_readback_complete = (snapshot is raid
                                  and diagnosis["raid_runtime"].get("difficulty_readback_complete") is True
                                  and diagnosis["raid_runtime"].get("difficulty_matches") is True)
        if (not 0 < len(expected.roster_guids) - count <= (len(expected.roster_guids) if newer_readback_complete else recovering)
                or matching != count
                or _integer(snapshot.get("group_difficulty"), "group_difficulty") != expected.difficulty
                or _integer(snapshot.get("expected_difficulty"), "expected_difficulty") != expected.difficulty):
            raise ValueError("native difficulty readback incomplete without attributable recovery")
    if len(guids) != len(set(guids)) or set(guids) != expected.roster_guids:
        raise ValueError("live roster differs from frozen roster")
    if _integer(status.get("lease_count"), "lease_count") != len(guids):
        raise ValueError("lease count differs from frozen roster")
    return {"cohort_id": expected.cohort_id, "server_epoch": epoch,
            "attempt_id": attempt, "map_id": expected.map_id,
            "instance_id": instance, "group_guid": group,
            "roster_guids": sorted(guids), "combat_metrics": diagnosis.get("combat_metrics"),
            "decisions": status.get("decisions"), "deaths": status.get("deaths"),
            "movement": [{"bot_guid": bot["identity"]["bot_guid"],
                          "native": bot["snapshot"].get("movement"),
                          "planner": bot["snapshot"].get("movement_planner"),
                          "receipt": bot["snapshot"].get("movement_receipt_progress"),
                          "position": bot["snapshot"]["validation_cohort"].get("current_position")}
                         for bot in diagnosis["bots"]],
            "route_progress": status.get("validation_route")}


def validate_pair(left: dict[str, Any], left_expected: InstanceExpectation,
                  right: dict[str, Any], right_expected: InstanceExpectation) -> list[dict[str, Any]]:
    a, b = validate_instance(left, left_expected), validate_instance(right, right_expected)
    if a["server_epoch"] != b["server_epoch"]:
        raise ValueError("cohorts are not on the same worldserver epoch")
    if (a["cohort_id"] == b["cohort_id"] or a["group_guid"] == b["group_guid"]
            or (a["map_id"], a["instance_id"]) == (b["map_id"], b["instance_id"])
            or set(a["roster_guids"]) & set(b["roster_guids"])):
        raise ValueError("cohorts share instance, group, or roster ownership")
    return [a, b]
