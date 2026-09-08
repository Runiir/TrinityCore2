"""Prove two addressed bot cohorts progress and clean up on one owned server.

The caller owns the server, transport, provisioning, and frozen input identity.
This module only drives the two named cohorts and writes a non-promotable
isolation fixture report.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import time
from typing import Any

from tools.bot_ml.run_live_bot_validation import (
    CohortCommandExecutor,
    combat_log_attempt_status,
    combat_log_transport_attempts,
    combined_combat_log,
    live_validation_report,
    parse_json_objects,
)
from tools.raid_program.shared_instance_observation import (
    InstanceExpectation,
    observe,
    validate_instance,
    validate_pair,
)
from tools.raid_program.shared_instance_progress import validate_combat_progress


CommandTransport = Callable[[str, int], tuple[str, int, bool]]
Clock = Callable[[], float]
Sleeper = Callable[[float], None]


class SharedInstanceValidationError(RuntimeError):
    """A typed fail-closed fixture boundary."""


COMBAT_LOG_PERSPECTIVES = frozenset({
    "damage_done", "damage_taken", "healing_done", "healing_received",
    "friendly_damage_done",
})


@dataclass(frozen=True)
class _Identity:
    cohort_id: str
    server_epoch: int
    attempt_id: int
    profile: str
    profile_generation: int
    profile_content_hash: str
    map_id: int
    instance_id: int
    group_guid: int
    lease_count: int
    roster_guids: tuple[int, ...]


class _RawRecorder:
    def __init__(self, path: Path, clock: Clock):
        self.path = path
        self.clock = clock
        self.sequence = 0
        self.last_command_context: dict[str, Any] | None = None
        self._handle = path.open("x", encoding="utf-8")

    def record(
        self, command: str, output: str, returncode: int, timed_out: bool,
        *, role: str, phase: str,
    ) -> None:
        self.sequence += 1
        self.last_command_context = {
            "sequence": self.sequence, "role": role, "phase": phase,
            "command": command,
        }
        row = {
            "sequence": self.sequence,
            "observed_at_monotonic": self.clock(),
            "role": role,
            "phase": phase,
            "command": command,
            "returncode": returncode,
            "timed_out": timed_out,
            "output": output,
        }
        self._handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise SharedInstanceValidationError(f"{label}_invalid")
    return value


def _number(value: Any, label: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
        raise SharedInstanceValidationError(f"{label}_invalid")
    return float(value)


def _one_envelope(output: str, action: str) -> dict[str, Any]:
    rows = [row for row in parse_json_objects(output) if row.get("action") == action]
    if len(rows) != 1:
        raise SharedInstanceValidationError(f"{action}_envelope_ambiguous")
    row = rows[0]
    if row.get("ok") is not True or row.get("failure_reason") not in {None, ""}:
        raise SharedInstanceValidationError(f"{action}_rejected")
    return row


def _run(
    executor: CohortCommandExecutor,
    command: str,
    action: str,
    recorder: _RawRecorder,
    *,
    role: str,
    phase: str,
) -> tuple[dict[str, Any], str]:
    output, returncode, timed_out = executor.run(command)
    recorder.record(command, output, returncode, timed_out, role=role, phase=phase)
    if returncode != 0 or timed_out:
        raise SharedInstanceValidationError(f"{action}_transport_failed")
    return _one_envelope(output, action), output


def _registry(
    execute: CommandTransport,
    recorder: _RawRecorder,
    *,
    phase: str,
    timeout: int,
    expected_epoch: int,
    expected_process_id: int,
    expected_active: set[str],
) -> dict[str, Any]:
    command = ".botauto cohorts"
    output, returncode, timed_out = execute(command, timeout)
    recorder.record(
        command, output, returncode, timed_out, role="coordinator", phase=phase,
    )
    if returncode != 0 or timed_out:
        raise SharedInstanceValidationError("registry_transport_failed")
    row = _one_envelope(output, "botauto_cohorts")
    if (
        _integer(row.get("server_epoch"), "registry_server_epoch", 1)
        != expected_epoch
        or _integer(row.get("server_process_id"), "registry_process_id", 1)
        != expected_process_id
        or _integer(row.get("max_active_cohorts"), "registry_capacity", 1) != 2
    ):
        raise SharedInstanceValidationError("registry_identity_mismatch")
    cohorts = row.get("cohorts")
    if not isinstance(cohorts, list):
        raise SharedInstanceValidationError("registry_cohorts_invalid")
    identities: set[str] = set()
    active: set[str] = set()
    for cohort in cohorts:
        if not isinstance(cohort, dict) or not isinstance(cohort.get("cohort_id"), str):
            raise SharedInstanceValidationError("registry_cohorts_invalid")
        cohort_id = cohort["cohort_id"]
        if not cohort_id or cohort_id in identities or type(cohort.get("active")) is not bool:
            raise SharedInstanceValidationError("registry_cohorts_invalid")
        identities.add(cohort_id)
        _integer(cohort.get("attempt_id"), "registry_attempt")
        _integer(cohort.get("lease_count"), "registry_lease_count")
        if cohort["active"]:
            active.add(cohort_id)
    if active != expected_active or _integer(
        row.get("active_cohort_count"), "registry_active_count"
    ) != len(active):
        raise SharedInstanceValidationError("active_cohort_set_mismatch")
    return row


def _runtime_identity(
    row: Mapping[str, Any], expected: InstanceExpectation, profile: str,
) -> tuple[int, int, int, str]:
    if (
        row.get("cohort_id") != expected.cohort_id
        or row.get("active_profile") != profile
        or row.get("ok") is not True
        or row.get("failure_reason") not in {None, ""}
    ):
        raise SharedInstanceValidationError("runtime_envelope_identity_mismatch")
    epoch = _integer(row.get("server_epoch"), "server_epoch", 1)
    attempt = _integer(row.get("attempt_id"), "attempt_id", 1)
    generation = _integer(row.get("profile_generation"), "profile_generation", 1)
    content_hash = row.get("profile_content_hash")
    if not isinstance(content_hash, str) or len(content_hash) != 64:
        raise SharedInstanceValidationError("profile_content_hash_invalid")
    try:
        int(content_hash, 16)
    except ValueError as error:
        raise SharedInstanceValidationError("profile_content_hash_invalid") from error
    return epoch, attempt, generation, content_hash


def _identity(
    observation: dict[str, Any], expected: InstanceExpectation, profile: str,
) -> _Identity:
    try:
        normalized = validate_instance(observation, expected)
    except (KeyError, TypeError, ValueError) as error:
        raise SharedInstanceValidationError("native_instance_identity_invalid") from error
    status = observation["status"]
    epoch, attempt, generation, content_hash = _runtime_identity(
        status, expected, profile,
    )
    if normalized["server_epoch"] != epoch or normalized["attempt_id"] != attempt:
        raise SharedInstanceValidationError("native_instance_identity_invalid")
    return _Identity(
        cohort_id=expected.cohort_id,
        server_epoch=epoch,
        attempt_id=attempt,
        profile=profile,
        profile_generation=generation,
        profile_content_hash=content_hash,
        map_id=normalized["map_id"],
        instance_id=normalized["instance_id"],
        group_guid=normalized["group_guid"],
        lease_count=len(normalized["roster_guids"]),
        roster_guids=tuple(normalized["roster_guids"]),
    )


def _movement_evidence(observation: Mapping[str, Any]) -> list[dict[str, Any]]:
    diagnosis = observation.get("diagnosis")
    bots = diagnosis.get("bots") if isinstance(diagnosis, Mapping) else None
    if not isinstance(bots, list) or not bots:
        raise SharedInstanceValidationError("movement_evidence_missing")
    result: list[dict[str, Any]] = []
    for bot in bots:
        identity = bot.get("identity") if isinstance(bot, Mapping) else None
        snapshot = bot.get("snapshot") if isinstance(bot, Mapping) else None
        guid = _integer(
            identity.get("bot_guid") if isinstance(identity, Mapping) else None,
            "movement_bot_guid", 1,
        )
        if not isinstance(snapshot, Mapping):
            raise SharedInstanceValidationError("movement_evidence_missing")
        native = snapshot.get("movement")
        planner = snapshot.get("movement_planner")
        receipt = snapshot.get("movement_receipt_progress")
        if not all(isinstance(item, Mapping) for item in (native, planner, receipt)):
            raise SharedInstanceValidationError("movement_evidence_missing")
        if type(planner.get("available")) is not bool or type(receipt.get("available")) is not bool:
            raise SharedInstanceValidationError("movement_evidence_invalid")
        for value in (planner, receipt):
            if value["available"] and _integer(value.get("bot_guid"), "movement_owner", 1) != guid:
                raise SharedInstanceValidationError("movement_owner_mismatch")
        if not isinstance(receipt.get("receipts"), list):
            raise SharedInstanceValidationError("movement_evidence_invalid")
        result.append({
            "bot_guid": guid,
            "native": dict(native),
            "planner": dict(planner),
            "receipt": dict(receipt),
            "position": dict(snapshot.get("validation_cohort", {}).get("current_position", {})),
        })
    return result


def _validate_movement_preserved(
    before: Mapping[str, Any], after: Mapping[str, Any],
    *, require_receipt_identity: bool = False,
) -> None:
    before_rows = {row["bot_guid"]: row for row in _movement_evidence(before)}
    after_rows = {row["bot_guid"]: row for row in _movement_evidence(after)}
    if before_rows.keys() != after_rows.keys():
        raise SharedInstanceValidationError("movement_roster_changed")
    witnessed = 0
    for guid, prior in before_rows.items():
        current = after_rows[guid]
        for field in ("planner", "receipt"):
            if prior[field].get("available") is True and current[field].get("available") is not True:
                raise SharedInstanceValidationError("movement_record_lost")
        if not require_receipt_identity or not prior["receipt"]["available"]:
            continue
        prior_receipts = prior["receipt"]["receipts"]
        if not prior_receipts:
            continue
        # Anchor the newest receipt near the stop. Older receipts may leave
        # the bounded active-then-newest publication during ordinary movement.
        anchor = max(prior_receipts, key=lambda row: _integer(row.get("receipt_id"), "receipt_id", 1))
        status = before["status"]
        raid = status["raid_runtime"]
        if (anchor.get("map") != raid["map_id"] or anchor.get("instance") != raid["instance_id"]
                or not isinstance(anchor.get("scope"), Mapping)
                or anchor["scope"].get("attempt_id") != status["attempt_id"]):
            raise SharedInstanceValidationError("movement_receipt_scope_mismatch")
        matches = [row for row in current["receipt"]["receipts"]
                   if row.get("receipt_id") == anchor["receipt_id"]]
        if len(matches) != 1:
            raise SharedInstanceValidationError("movement_receipt_identity_lost")
        retained = matches[0]
        for field in ("bot_guid", "map", "instance", "scope", "armed_at_ms",
                      "selected_endpoint", "actor_at_launch", "launched_spline"):
            if field not in anchor or retained.get(field) != anchor[field]:
                raise SharedInstanceValidationError("movement_receipt_identity_changed")
        if anchor["bot_guid"] != guid:
            raise SharedInstanceValidationError("movement_owner_mismatch")
        for row in (anchor, retained):
            if not isinstance(row.get("samples"), list):
                raise SharedInstanceValidationError("movement_samples_invalid")
        before_count = len(anchor["samples"]) + _integer(anchor.get("dropped_sample_count"), "movement_dropped_samples")
        after_count = len(retained["samples"]) + _integer(retained.get("dropped_sample_count"), "movement_dropped_samples")
        if after_count < before_count:
            raise SharedInstanceValidationError("movement_samples_regressed")
        witnessed += 1
    if require_receipt_identity and not witnessed:
        raise SharedInstanceValidationError("movement_receipt_witness_missing")


def _combat_log(
    executor: CohortCommandExecutor,
    expected: InstanceExpectation,
    profile: str,
    recorder: _RawRecorder,
    anchor: _Identity,
    *,
    role: str,
    phase: str,
) -> tuple[dict[str, Any], str]:
    command = f".botauto combatlog {executor.cohort_id}"
    output, returncode, timed_out = executor.run(command)
    recorder.record(command, output, returncode, timed_out, role=role, phase=phase)
    if returncode != 0 or timed_out:
        raise SharedInstanceValidationError("combat_log_transport_failed")
    payloads = parse_json_objects(output)
    if any(row.get("action") == "botauto_combatlog" for row in payloads):
        raise SharedInstanceValidationError("combat_log_direct_fallback_forbidden")
    attempts = combat_log_transport_attempts(payloads)
    if len(attempts) != 1:
        raise SharedInstanceValidationError("combat_log_export_ambiguous")
    chunks, completion = attempts[0]
    status = combat_log_attempt_status(chunks, completion)
    if not status.get("reassembled"):
        raise SharedInstanceValidationError("combat_log_export_incomplete")
    if any(
        row.get("ok") is not True or row.get("cohort_id") != expected.cohort_id
        for row in [*chunks, completion]
    ):
        raise SharedInstanceValidationError("combat_log_chunk_identity_mismatch")
    decoded = combined_combat_log(payloads)
    if not decoded:
        raise SharedInstanceValidationError("combat_log_decode_failed")
    envelope = _runtime_identity(decoded, expected, profile)
    if envelope != (
        anchor.server_epoch, anchor.attempt_id, anchor.profile_generation,
        anchor.profile_content_hash,
    ):
        raise SharedInstanceValidationError("combat_log_identity_stale")
    recent = decoded.get("recent_events")
    abilities = decoded.get("abilities")
    if not isinstance(recent, list) or not isinstance(abilities, list):
        raise SharedInstanceValidationError("combat_log_schema_invalid")
    event_count = _integer(decoded.get("event_count"), "combat_event_count")
    dropped = _integer(decoded.get("recent_events_dropped"), "combat_events_dropped")
    if event_count != len(recent) + dropped:
        raise SharedInstanceValidationError("combat_event_accounting_mismatch")
    roster = expected.roster_guids
    for event in recent:
        if not isinstance(event, Mapping):
            raise SharedInstanceValidationError("combat_event_invalid")
        actor = _integer(event.get("actor_guid"), "combat_actor_guid", 1)
        if actor not in roster:
            raise SharedInstanceValidationError("combat_actor_foreign")
        for prefix in ("source", "target"):
            entry = _integer(event.get(f"{prefix}_entry"), f"combat_{prefix}_entry")
            guid = _integer(event.get(f"{prefix}_guid"), f"combat_{prefix}_guid", 1)
            if entry == 0 and guid not in roster:
                raise SharedInstanceValidationError(f"combat_{prefix}_player_foreign")
        _integer(event.get("amount"), "combat_event_amount")
    outgoing = 0
    for ability in abilities:
        if not isinstance(ability, Mapping):
            raise SharedInstanceValidationError("combat_ability_invalid")
        actor = _integer(ability.get("actor_guid"), "combat_ability_actor", 1)
        if actor not in roster:
            raise SharedInstanceValidationError("combat_actor_foreign")
        perspective = ability.get("perspective")
        if perspective not in COMBAT_LOG_PERSPECTIVES:
            raise SharedInstanceValidationError("combat_ability_perspective_invalid")
        if perspective in {"damage_done", "healing_done"}:
            outgoing += _integer(
                ability.get("originated_amount"), "combat_outgoing_amount"
            )
    decoded = dict(decoded)
    decoded["validated_outgoing_amount"] = outgoing
    return decoded, output


def _trace(
    executor: CohortCommandExecutor,
    expected: InstanceExpectation,
    profile: str,
    recorder: _RawRecorder,
    anchor: _Identity,
    *,
    role: str,
    phase: str,
) -> tuple[dict[str, Any], str]:
    command = f".botauto trace {executor.cohort_id} all 128 delta"
    row, output = _run(
        executor, command, "botauto_trace", recorder, role=role, phase=phase,
    )
    envelope = _runtime_identity(row, expected, profile)
    if envelope != (
        anchor.server_epoch, anchor.attempt_id, anchor.profile_generation,
        anchor.profile_content_hash,
    ):
        raise SharedInstanceValidationError("trace_identity_stale")
    bots = row.get("bots")
    if not isinstance(bots, list):
        raise SharedInstanceValidationError("trace_roster_invalid")
    guids = []
    for bot in bots:
        if not isinstance(bot, Mapping) or not isinstance(bot.get("entries"), list):
            raise SharedInstanceValidationError("trace_roster_invalid")
        guids.append(_integer(bot.get("bot_guid"), "trace_bot_guid", 1))
    if len(guids) != len(set(guids)) or set(guids) != expected.roster_guids:
        raise SharedInstanceValidationError("trace_roster_invalid")
    return row, output


def _capture(
    executor: CohortCommandExecutor,
    expected: InstanceExpectation,
    profile: str,
    recorder: _RawRecorder,
    *,
    role: str,
    phase: str,
    watchdog: Mapping[str, Any],
) -> dict[str, Any]:
    outputs: list[str] = []

    def record_observation(command: str, output: str, code: int, timed_out: bool) -> None:
        recorder.record(command, output, code, timed_out, role=role, phase=phase)
        outputs.append(output)

    try:
        observation = observe(executor, record_observation)
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise SharedInstanceValidationError("native_observation_invalid") from error
    identity = _identity(observation, expected, profile)
    movement = _movement_evidence(observation)
    trace, trace_output = _trace(
        executor, expected, profile, recorder, identity, role=role, phase=phase,
    )
    combat, combat_output = _combat_log(
        executor, expected, profile, recorder, identity, role=role, phase=phase,
    )
    outputs.extend((trace_output, combat_output))
    status = observation["status"]
    decisions = _integer(status.get("decisions"), "decisions")
    metrics = observation["diagnosis"].get("combat_metrics")
    if not isinstance(metrics, Mapping):
        raise SharedInstanceValidationError("combat_metrics_missing")
    for name in ("party_dps", "party_hps"):
        _number(metrics.get(name), name)
    report = live_validation_report(
        "\n".join(outputs),
        duration_policy="completion-watchdog",
        heartbeat_sec=_integer(watchdog.get("heartbeat_sec"), "heartbeat_sec", 1),
        no_progress_window_sec=_integer(
            watchdog.get("no_progress_window_sec"), "no_progress_window_sec", 1,
        ),
        max_repeated_decisions=_integer(
            watchdog.get("max_repeated_decisions"), "max_repeated_decisions", 1,
        ),
        max_death_loops=_integer(
            watchdog.get("max_death_loops"), "max_death_loops", 1,
        ),
    )
    return {
        "identity": identity,
        "observation": observation,
        "transferring_guids": [bot["identity"]["bot_guid"]
                               for bot in observation["diagnosis"]["bots"]
                               if bot["snapshot"]["validation_cohort"]["in_world"] is False],
        "movement": movement,
        "trace_entry_count": sum(
            len(bot["entries"]) for bot in trace.get("bots", [])
        ),
        "combat": combat,
        "outgoing_amount": combat["validated_outgoing_amount"],
        "event_count": combat["event_count"],
        "decisions": decisions,
        "deaths": _integer(status.get("deaths"), "deaths"),
        "combat_metrics": dict(metrics),
        "route_progress": status.get("validation_route"),
        "watchdog_state": report.get("watchdog_state", {}),
    }


def _identity_unchanged(before: _Identity, after: _Identity) -> None:
    if before != after:
        raise SharedInstanceValidationError("witness_identity_changed")


def _advanced(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    if (
        _integer(after.get("event_count"), "event_count")
        < _integer(before.get("event_count"), "event_count")
        or _integer(after.get("decisions"), "decisions")
        < _integer(before.get("decisions"), "decisions")
    ):
        raise SharedInstanceValidationError("cumulative_progress_regressed")
    try:
        native_progress = validate_combat_progress(
            before["combat"], after["combat"], frozenset(before["identity"].roster_guids))
    except ValueError as error:
        raise SharedInstanceValidationError(str(error)) from error
    return (
        native_progress
        and not before.get("transferring_guids")
        and not after.get("transferring_guids")
        and after["decisions"] > before["decisions"]
        and after["trace_entry_count"] > 0
    )


def _heartbeat_summary(capture: Mapping[str, Any]) -> dict[str, Any]:
    identity = capture["identity"]
    movement = []
    for row in capture["movement"]:
        planner = row["planner"]
        receipt = row["receipt"]
        movement.append({
            "bot_guid": row["bot_guid"],
            "native": row["native"],
            "planner": {
                "available": planner.get("available"),
                "owner": planner.get("owner"),
                "intent_reason": planner.get("intent_reason"),
            },
            "receipt": {
                "available": receipt.get("available"),
                "active_receipt_id": receipt.get("active_receipt_id"),
                "requested_receipt_id": receipt.get("requested_receipt_id"),
                "published_receipt_count": receipt.get("published_receipt_count"),
                "receipt_ids": [
                    item.get("receipt_id") for item in receipt.get("receipts", [])
                    if isinstance(item, Mapping)
                ],
            },
            "position": row["position"],
        })
    return {
        "cohort_id": identity.cohort_id,
        "server_epoch": identity.server_epoch,
        "attempt_id": identity.attempt_id,
        "profile": identity.profile,
        "profile_generation": identity.profile_generation,
        "profile_content_hash": identity.profile_content_hash,
        "map_id": identity.map_id,
        "instance_id": identity.instance_id,
        "group_guid": identity.group_guid,
        "lease_count": identity.lease_count,
        "roster_guids": list(identity.roster_guids),
        "decisions": capture["decisions"],
        "deaths": capture["deaths"],
        "trace_entry_count": capture["trace_entry_count"],
        "event_count": capture["event_count"],
        "outgoing_amount": capture["outgoing_amount"],
        "combat_metrics": capture["combat_metrics"],
        "route_progress": capture["route_progress"],
        "movement": movement,
        "transferring_guids": list(capture.get("transferring_guids", ())),
        "watchdog_state": capture["watchdog_state"],
    }


def _watchdog_terminal(captures: Mapping[str, Mapping[str, Any]]) -> str | None:
    states = [capture.get("watchdog_state", {}) for capture in captures.values()]
    if any(state.get("death_loop") for state in states):
        return "death_loop_watchdog"
    if any(state.get("repeated_decision_loop") for state in states):
        return "repeated_decision_watchdog"
    return None


def _validate_inputs(
    fixture: Mapping[str, Any], session: Mapping[str, Any],
    executors: Mapping[str, CohortCommandExecutor],
    expectations: Mapping[str, InstanceExpectation],
    profile_ids: Mapping[str, str],
) -> tuple[int, int, Mapping[str, Any]]:
    if fixture.get("schema") != "cata_shared_instance_fixture_v1":
        raise SharedInstanceValidationError("fixture_schema_invalid")
    if fixture.get("boss_completion_eligible") is not False or fixture.get("training_eligible") is not False:
        raise SharedInstanceValidationError("fixture_scope_invalid")
    if fixture.get("maximum_active_cohorts") != 2 or fixture.get("map_update_threads") != 1:
        raise SharedInstanceValidationError("fixture_capacity_invalid")
    if fixture.get("start_order") != ["witness", "subject"] or fixture.get("stop_order") != ["subject", "witness"]:
        raise SharedInstanceValidationError("fixture_order_invalid")
    if set(executors) != {"subject", "witness"} or set(expectations) != set(executors) or set(profile_ids) != set(executors):
        raise SharedInstanceValidationError("pair_binding_invalid")
    for role in ("subject", "witness"):
        expected_id = fixture.get(f"{role}_shard_id")
        if (
            executors[role].cohort_id != expected_id
            or expectations[role].cohort_id != expected_id
            or executors[role].exclusive
            or not isinstance(profile_ids[role], str)
            or not profile_ids[role]
        ):
            raise SharedInstanceValidationError("pair_binding_invalid")
    if expectations["subject"].roster_guids & expectations["witness"].roster_guids:
        raise SharedInstanceValidationError("pair_rosters_overlap")
    epoch = _integer(session.get("server_epoch"), "session_server_epoch", 1)
    process_id = _integer(
        session.get("server_process_id"), "session_server_process_id", 1,
    )
    if session.get("server_process_identity_verified") is not True:
        raise SharedInstanceValidationError("session_ownership_unverified")
    watchdog = fixture.get("watchdog")
    if not isinstance(watchdog, Mapping) or watchdog.get("duration_policy") != "completion-watchdog":
        raise SharedInstanceValidationError("watchdog_invalid")
    for name in (
        "heartbeat_sec", "no_progress_window_sec", "max_repeated_decisions",
        "max_death_loops", "emergency_timeout_sec", "transition_timeout_sec",
    ):
        _integer(watchdog.get(name), name, 1)
    return epoch, process_id, watchdog


def _active_status_ready(
    row: Mapping[str, Any], expected: InstanceExpectation,
) -> bool:
    runtime = row.get("raid_runtime")
    return (
        row.get("active") is True
        and row.get("bots") == len(expected.roster_guids)
        and row.get("lease_count") == len(expected.roster_guids)
        and isinstance(runtime, Mapping)
        and runtime.get("bot_actions_enabled") is True
        and runtime.get("roster_complete") is True
        and runtime.get("difficulty_readback_complete") is True
        and runtime.get("difficulty_matches") is True
        and runtime.get("map_id") == expected.map_id
        and runtime.get("map_difficulty") == expected.difficulty
        and type(runtime.get("instance_id")) is int
        and runtime["instance_id"] > 0
        and type(runtime.get("group_guid")) is int
        and runtime["group_guid"] > 0
    )


def _wait_active(
    initial: dict[str, Any], executor: CohortCommandExecutor,
    expected: InstanceExpectation, profile: str, recorder: _RawRecorder,
    *, role: str, epoch: int, timeout: int, clock: Clock, sleep: Sleeper,
) -> tuple[int, int, int, str]:
    row = initial
    deadline = clock() + timeout
    while True:
        identity = _runtime_identity(row, expected, profile)
        if identity[0] != epoch:
            raise SharedInstanceValidationError("session_epoch_mismatch")
        if _active_status_ready(row, expected):
            return identity
        if clock() >= deadline:
            raise SharedInstanceValidationError("cohort_start_transition_timeout")
        sleep(min(1.0, max(0.0, deadline - clock())))
        row, _ = _run(
            executor, executor.status_command, "botauto_status", recorder,
            role=role, phase="start_transition",
        )


def _inactive_status(
    row: Mapping[str, Any], cohort_id: str, epoch: int,
    attempt_id: int | None = None,
) -> None:
    if (
        row.get("cohort_id") != cohort_id
        or row.get("server_epoch") != epoch
        or (attempt_id is not None and row.get("attempt_id") != attempt_id)
        or row.get("active") is not False
        or row.get("bots") != 0
        or row.get("lease_count") != 0
    ):
        raise SharedInstanceValidationError("cohort_cleanup_incomplete")


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _typed_terminal(detail: str, passed: bool) -> str:
    if passed:
        return "interruption"
    if detail in {"no_progress_watchdog"}:
        return "semantic_stall"
    if detail == "repeated_decision_watchdog":
        return "repeated_decision"
    if detail == "death_loop_watchdog":
        return "death_loop"
    if detail in {
        "operator_interrupt", "isolation_fixture_passed",
    }:
        return "interruption"
    if detail.startswith((
        "runtime_", "native_", "pair_", "combat_", "trace_", "movement_",
        "active_cohort_", "cumulative_", "botauto_", "prepare_identity_",
    )):
        return "contamination"
    return "infrastructure_loss"


def run_shared_instance_validation(
    *,
    fixture: Mapping[str, Any],
    session: Mapping[str, Any],
    coordinator_command: CommandTransport,
    executors: Mapping[str, CohortCommandExecutor],
    expectations: Mapping[str, InstanceExpectation],
    profile_ids: Mapping[str, str],
    output_path: Path,
    clock: Clock = time.monotonic,
    sleep: Sleeper = time.sleep,
) -> dict[str, Any]:
    """Run one non-promotable shared-instance isolation fixture."""

    if output_path.exists() or output_path.with_suffix(".raw.jsonl").exists():
        raise SharedInstanceValidationError("output_exists")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = output_path.with_suffix(".raw.jsonl")
    recorder = _RawRecorder(raw_path, clock)
    report: dict[str, Any] = {
        "schema": "cata_shared_instance_validation_v1",
        "fixture_id": str(fixture.get("fixture_id") or ""),
        "classification": "fixture_observation",
        "isolation_passed": False,
        "boss_clear_claimed": False,
        "training_eligible": False,
        "ml_admission_eligible": False,
        "terminal_reason": "infrastructure_loss",
        "terminal_detail": "incomplete_evidence",
        "failure_reason": "incomplete_evidence",
        "heartbeats": [],
        "cleanup": {"passed": False},
        "raw_output_path": str(raw_path),
    }
    created_roles: set[str] = set()
    dispatched_roles: set[str] = set()
    rejected_roles: set[str] = set()
    epoch = 0
    process_id = 0
    watchdog: Mapping[str, Any] = {}
    deadline = 0.0
    proof_complete = False
    attempt_ids: dict[str, int] = {}
    try:
        epoch, process_id, watchdog = _validate_inputs(
            fixture, session, executors, expectations, profile_ids,
        )
        timeout = int(watchdog["transition_timeout_sec"])
        deadline = clock() + int(watchdog["emergency_timeout_sec"])
        initial_registry = _registry(
            coordinator_command, recorder, phase="preflight", timeout=timeout,
            expected_epoch=epoch, expected_process_id=process_id,
            expected_active=set(),
        )
        requested_ids = {executor.cohort_id for executor in executors.values()}
        if any(row["cohort_id"] in requested_ids for row in initial_registry["cohorts"]):
            raise SharedInstanceValidationError("create_cohort_preexisting")
        for role in ("witness", "subject"):
            executor = executors[role]
            registry = _registry(
                coordinator_command, recorder, phase=f"before_create_{role}",
                timeout=timeout, expected_epoch=epoch, expected_active=set(),
                expected_process_id=process_id,
            )
            if any(item["cohort_id"] == executor.cohort_id for item in registry["cohorts"]):
                raise SharedInstanceValidationError("create_cohort_preexisting")
            dispatched_roles.add(role)
            row, _ = _run(
                executor, f".botauto create {executor.cohort_id}",
                "botauto_create", recorder, role=role, phase="create",
            )
            if row.get("cohort_id") != executor.cohort_id or type(row.get("created")) is not bool:
                raise SharedInstanceValidationError("create_identity_mismatch")
            if row["created"] is not True:
                rejected_roles.add(role)
                raise SharedInstanceValidationError("create_ownership_rejected")
            created_roles.add(role)
            row, _ = _run(
                executor, f".botauto stop {executor.cohort_id}",
                "botauto_stop", recorder, role=role, phase="normalize_inactive",
            )
            if row.get("cohort_id") != executor.cohort_id:
                raise SharedInstanceValidationError("stop_identity_mismatch")
            _registry(
                coordinator_command, recorder, phase=f"before_prepare_{role}",
                timeout=timeout, expected_epoch=epoch, expected_active=set(),
                expected_process_id=process_id,
            )
            prepared, _ = _run(
                executor,
                f".botauto prepare {executor.cohort_id} {profile_ids[role]}",
                "botauto_prepare", recorder, role=role, phase="prepare",
            )
            if (
                prepared.get("profile") != profile_ids[role]
                or prepared.get("pool_tag_filter") != profile_ids[role]
            ):
                raise SharedInstanceValidationError("prepare_identity_mismatch")
        _registry(
            coordinator_command, recorder, phase="prepared", timeout=timeout,
            expected_epoch=epoch, expected_process_id=process_id,
            expected_active=set(),
        )
        for index, role in enumerate(("witness", "subject"), 1):
            executor = executors[role]
            prior_active = {
                executors[item].cohort_id
                for item in fixture["start_order"][:index - 1]
            }
            _registry(
                coordinator_command, recorder, phase=f"before_start_{role}",
                timeout=timeout, expected_epoch=epoch,
                expected_process_id=process_id,
                expected_active=prior_active,
            )
            row, _ = _run(
                executor, f".botauto start {executor.cohort_id}",
                "botauto_status", recorder, role=role, phase="start",
            )
            start_identity = _wait_active(
                row, executor, expectations[role], profile_ids[role], recorder,
                role=role, epoch=epoch, timeout=timeout, clock=clock, sleep=sleep,
            )
            attempt_ids[role] = start_identity[1]
            _registry(
                coordinator_command, recorder, phase=f"start_{role}", timeout=timeout,
                expected_epoch=epoch, expected_process_id=process_id,
                expected_active={
                    executors[item].cohort_id
                    for item in fixture["start_order"][:index]
                },
            )

        baseline = {
            role: _capture(
                executors[role], expectations[role], profile_ids[role], recorder,
                role=role, phase="both_active_baseline", watchdog=watchdog,
            )
            for role in ("subject", "witness")
        }
        both_active_ids = {executors[role].cohort_id for role in executors}
        _registry(
            coordinator_command, recorder, phase="both_active_baseline_complete",
            timeout=timeout, expected_epoch=epoch,
            expected_process_id=process_id, expected_active=both_active_ids,
        )
        try:
            validate_pair(
                baseline["subject"]["observation"], expectations["subject"],
                baseline["witness"]["observation"], expectations["witness"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SharedInstanceValidationError("pair_instance_identity_invalid") from error
        for role in baseline:
            if baseline[role]["identity"].server_epoch != epoch:
                raise SharedInstanceValidationError("session_epoch_mismatch")
        progress_started_at = {role: clock() for role in baseline}
        previous = baseline
        both_progress: dict[str, dict[str, Any]] = {}
        while clock() < deadline and len(both_progress) < 2:
            remaining = min([deadline - clock()] + [
                int(watchdog["no_progress_window_sec"]) - (clock() - progress_started_at[role])
                for role in baseline if role not in both_progress])
            sleep(max(0.0, min(float(watchdog["heartbeat_sec"]), remaining)))
            _registry(
                coordinator_command, recorder, phase="both_active_heartbeat",
                timeout=timeout, expected_epoch=epoch,
                expected_process_id=process_id,
                expected_active=both_active_ids,
            )
            current = {
                role: _capture(
                    executors[role], expectations[role], profile_ids[role], recorder,
                    role=role, phase="both_active_heartbeat", watchdog=watchdog,
                )
                for role in ("subject", "witness")
            }
            _registry(
                coordinator_command, recorder, phase="both_active_heartbeat_complete",
                timeout=timeout, expected_epoch=epoch,
                expected_process_id=process_id,
                expected_active=both_active_ids,
            )
            for role in current:
                _identity_unchanged(baseline[role]["identity"], current[role]["identity"])
                if _advanced(previous[role], current[role]):
                    both_progress[role] = current[role]
            previous = current
            report["heartbeats"].append({
                "phase": "both_active",
                "captures": {role: _heartbeat_summary(value) for role, value in current.items()},
            })
            terminal = _watchdog_terminal(current)
            if terminal:
                raise SharedInstanceValidationError(terminal)
            if any(role not in both_progress and clock() - progress_started_at[role]
                   >= int(watchdog["no_progress_window_sec"]) for role in baseline):
                raise SharedInstanceValidationError("no_progress_watchdog")
        if len(both_progress) != 2:
            raise SharedInstanceValidationError("emergency_wall_clock_timeout")

        pre_stop_witness = _capture(
            executors["witness"], expectations["witness"], profile_ids["witness"],
            recorder, role="witness", phase="pre_stop_witness", watchdog=watchdog)
        _identity_unchanged(baseline["witness"]["identity"], pre_stop_witness["identity"])
        _advanced(previous["witness"], pre_stop_witness)
        subject = executors["subject"]
        stop, _ = _run(
            subject, f".botauto stop {subject.cohort_id}", "botauto_stop", recorder,
            role="subject", phase="subject_stop",
        )
        if (
            stop.get("cohort_id") != subject.cohort_id
            or _integer(stop.get("server_epoch"), "stop_server_epoch", 1) != epoch
            or _integer(stop.get("attempt_id"), "stop_attempt_id", 1)
            != baseline["subject"]["identity"].attempt_id
        ):
            raise SharedInstanceValidationError("subject_stop_identity_mismatch")
        _registry(
            coordinator_command, recorder, phase="subject_stopped", timeout=timeout,
            expected_epoch=epoch, expected_process_id=process_id,
            expected_active={executors["witness"].cohort_id},
        )
        inactive, _ = _run(
            subject, subject.status_command, "botauto_status", recorder,
            role="subject", phase="subject_stopped",
        )
        _inactive_status(
            inactive, subject.cohort_id, epoch,
            baseline["subject"]["identity"].attempt_id,
        )

        witness_baseline = _capture(
            executors["witness"], expectations["witness"], profile_ids["witness"],
            recorder, role="witness", phase="post_stop_baseline", watchdog=watchdog,
        )
        witness_active_ids = {executors["witness"].cohort_id}
        _registry(
            coordinator_command, recorder, phase="post_stop_baseline_complete",
            timeout=timeout, expected_epoch=epoch,
            expected_process_id=process_id,
            expected_active=witness_active_ids,
        )
        _identity_unchanged(baseline["witness"]["identity"], witness_baseline["identity"])
        _advanced(pre_stop_witness, witness_baseline)
        _validate_movement_preserved(pre_stop_witness["observation"], witness_baseline["observation"],
                                     require_receipt_identity=True)
        last_native_progress_at = clock()
        previous_witness = witness_baseline
        witness_after: dict[str, Any] | None = None
        while clock() < deadline and witness_after is None:
            remaining = min(deadline - clock(), int(watchdog["no_progress_window_sec"])
                            - (clock() - last_native_progress_at))
            sleep(max(0.0, min(float(watchdog["heartbeat_sec"]), remaining)))
            _registry(
                coordinator_command, recorder, phase="post_stop_heartbeat", timeout=timeout,
                expected_epoch=epoch,
                expected_process_id=process_id,
                expected_active=witness_active_ids,
            )
            current = _capture(
                executors["witness"], expectations["witness"], profile_ids["witness"],
                recorder, role="witness", phase="post_stop_heartbeat", watchdog=watchdog,
            )
            _registry(
                coordinator_command, recorder, phase="post_stop_heartbeat_complete",
                timeout=timeout, expected_epoch=epoch,
                expected_process_id=process_id,
                expected_active=witness_active_ids,
            )
            _identity_unchanged(witness_baseline["identity"], current["identity"])
            _validate_movement_preserved(witness_baseline["observation"], current["observation"])
            report["heartbeats"].append({
                "phase": "subject_stopped",
                "captures": {"witness": _heartbeat_summary(current)},
            })
            terminal = _watchdog_terminal({"witness": current})
            if terminal:
                raise SharedInstanceValidationError(terminal)
            if _advanced(previous_witness, current):
                witness_after = current
                last_native_progress_at = clock()
            previous_witness = current
            if clock() - last_native_progress_at >= int(watchdog["no_progress_window_sec"]):
                raise SharedInstanceValidationError("no_progress_watchdog")
        if witness_after is None:
            raise SharedInstanceValidationError("emergency_wall_clock_timeout")
        report["proof"] = {
            "both_active": {
                role: _heartbeat_summary(both_progress[role])
                for role in ("subject", "witness")
            },
            "witness_after_subject_stop_baseline": _heartbeat_summary(witness_baseline),
            "witness_after_subject_stop_progress": _heartbeat_summary(witness_after),
        }
        proof_complete = True
        report["terminal_detail"] = "isolation_fixture_passed"
        report["failure_reason"] = None
    except KeyboardInterrupt:
        report["terminal_detail"] = "operator_interrupt"
        report["failure_reason"] = "operator_interrupt"
    except SharedInstanceValidationError as error:
        report["terminal_detail"] = str(error)
        report["failure_reason"] = str(error)
        report["failure_diagnostic"] = {
            "last_command": recorder.last_command_context,
            "cause_type": type(error.__cause__).__name__ if error.__cause__ else None,
            "cause": str(error.__cause__) if error.__cause__ else None,
        }
    except Exception as error:
        report["terminal_detail"] = f"infrastructure_error:{type(error).__name__}"
        report["failure_reason"] = report["terminal_detail"]
    finally:
        cleanup_errors: list[str] = []
        uncertain_roles = dispatched_roles - created_roles - rejected_roles
        if uncertain_roles or rejected_roles:
            cleanup_errors.append("create_ownership_unverified")
        if epoch and watchdog:
            timeout = int(watchdog["transition_timeout_sec"])
            for role in ("subject", "witness"):
                if role not in created_roles | uncertain_roles:
                    continue
                executor = executors[role]
                try:
                    row, _ = _run(
                        executor, f".botauto stop {executor.cohort_id}",
                        "botauto_stop", recorder, role=role, phase="final_cleanup",
                    )
                    if row.get("cohort_id") != executor.cohort_id:
                        raise SharedInstanceValidationError("stop_identity_mismatch")
                    if role in attempt_ids and (
                        row.get("server_epoch") != epoch
                        or row.get("attempt_id") != attempt_ids[role]
                    ):
                        raise SharedInstanceValidationError("stop_identity_mismatch")
                    status, _ = _run(
                        executor, executor.status_command, "botauto_status", recorder,
                        role=role, phase="final_cleanup",
                    )
                    _inactive_status(
                        status, executor.cohort_id, epoch, attempt_ids.get(role),
                    )
                except Exception as error:
                    cleanup_errors.append(f"{role}:{error}")
            try:
                final_registry = _registry(
                    coordinator_command, recorder, phase="final_cleanup", timeout=timeout,
                    expected_epoch=epoch, expected_process_id=process_id,
                    expected_active=set(),
                )
                for row in final_registry["cohorts"]:
                    if row["cohort_id"] in {executor.cohort_id for executor in executors.values()} and row["lease_count"] != 0:
                        raise SharedInstanceValidationError("final_registry_leases_nonzero")
            except Exception as error:
                cleanup_errors.append(f"registry:{error}")
        cleanup_required = bool(dispatched_roles)
        cleanup_passed = not cleanup_errors
        report["cleanup"] = {
            "passed": cleanup_passed,
            "errors": cleanup_errors,
            "owned_cohorts": sorted(executors[role].cohort_id for role in created_roles),
            "uncertain_cohorts": sorted(executors[role].cohort_id for role in uncertain_roles),
        }
        report["isolation_passed"] = proof_complete and cleanup_passed
        if proof_complete and cleanup_required and not cleanup_passed:
            report["terminal_detail"] = "cleanup_failure"
            report["failure_reason"] = "cleanup_failure"
        report["terminal_reason"] = _typed_terminal(
            str(report["terminal_detail"]), report["isolation_passed"],
        )
        recorder.close()
        raw_bytes = raw_path.read_bytes()
        report["raw_output_sha256"] = hashlib.sha256(raw_bytes).hexdigest()
        report["raw_command_count"] = recorder.sequence
        _write_report(output_path, report)
    return report
