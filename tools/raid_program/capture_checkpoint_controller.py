from __future__ import annotations

import re
from typing import Any

try:
    from tools.raid_program.capture_runtime_acceptance import _roster_rejections
    from tools.raid_program.capture_runtime_identity import (
        IDENTITY_FIELDS,
        _roster_binding_identity,
    )
    from tools.raid_program.capture_value_types import (
        _canonical_object_sha256,
        _positive_int,
    )
    from tools.raid_program.capture_watchdog import _watchdog_scope_rejections
    from tools.raid_program.recurrence_admission import (
        CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        FIXTURE_EXPANSION_PURPOSE,
        NATIVE_PATH_CHECKPOINT_FIXTURE_ID,
        NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS,
        RecurrenceAdmissionError,
        _fixture_expansion_contract,
    )
except ModuleNotFoundError:
    from capture_runtime_acceptance import _roster_rejections
    from capture_runtime_identity import IDENTITY_FIELDS, _roster_binding_identity
    from capture_value_types import _canonical_object_sha256, _positive_int
    from capture_watchdog import _watchdog_scope_rejections
    from recurrence_admission import (
        CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        FIXTURE_EXPANSION_PURPOSE,
        NATIVE_PATH_CHECKPOINT_FIXTURE_ID,
        NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS,
        RecurrenceAdmissionError,
        _fixture_expansion_contract,
    )


def _verified_checkpoint_target_contract(
    recurrence_admission: dict[str, Any],
) -> bool:
    """Require a verified auxiliary checkpoint and expansion requests."""

    try:
        requests = _fixture_expansion_contract(
            recurrence_admission, label="checkpoint_verified_admission"
        )
    except RecurrenceAdmissionError:
        return False
    revisions = recurrence_admission.get("fixture_revisions")
    if (
        recurrence_admission.get("checkpoint_fixture_id")
        != CHAINWIELDER_CHECKPOINT_FIXTURE_ID
        or not isinstance(revisions, dict)
    ):
        return False
    return all(
        revisions.get(request["fixture_id"]) == request["from_revision"]
        for request in requests
    )


def chainwielder_checkpoint_arm_command(
    recurrence_admission: dict[str, Any] | None,
    actor_guid: int | None,
) -> str | None:
    """Build the exact post-admission arm command, or fail closed."""

    seal = recurrence_admission.get("checkpoint_seal_sha256") \
        if isinstance(recurrence_admission, dict) else None
    if seal is None:
        if actor_guid is not None:
            raise ValueError("checkpoint_actor_without_verified_seal")
        return None
    admission_sha256 = recurrence_admission.get("admission_sha256")
    source_commit = recurrence_admission.get("source_commit")
    if (
        recurrence_admission.get("valid") is not True
        or recurrence_admission.get("purpose") != FIXTURE_EXPANSION_PURPOSE
        or not _verified_checkpoint_target_contract(recurrence_admission)
        or not isinstance(admission_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", admission_sha256)
    ):
        raise ValueError("checkpoint_verified_admission_invalid")
    if (
        not isinstance(actor_guid, int)
        or isinstance(actor_guid, bool)
        or actor_guid <= 0
    ):
        raise ValueError("checkpoint_actor_guid_required")
    if not isinstance(seal, str) or not re.fullmatch(r"[0-9a-f]{64}", seal):
        raise ValueError("checkpoint_verified_seal_invalid")
    if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("checkpoint_verified_source_invalid")
    return f"botautochaincheckpoint arm {actor_guid} {seal} {source_commit}"


def native_path_checkpoint_arm_command(
    recurrence_admission: dict[str, Any] | None,
    actor_guid: int | None,
) -> str | None:
    """Build the fixed-case arm command from verified admission only."""

    if recurrence_admission is None and actor_guid is None:
        return None
    if not isinstance(recurrence_admission, dict):
        raise ValueError("native_path_checkpoint_verified_admission_missing")
    requests = recurrence_admission.get("fixture_expansion_requests")
    request_contract = {
        row.get("fixture_id"): (row.get("from_revision"), row.get("to_revision"))
        for row in requests if isinstance(row, dict)
    } if isinstance(requests, list) else {}
    fixture_ids = recurrence_admission.get("fixture_expansion_target_ids")
    seal = recurrence_admission.get("checkpoint_seal_sha256")
    case_id = recurrence_admission.get("checkpoint_case_id")
    source = recurrence_admission.get("source_commit")
    if (
        recurrence_admission.get("valid") is not True
        or recurrence_admission.get("purpose") != FIXTURE_EXPANSION_PURPOSE
        or recurrence_admission.get("checkpoint_fixture_id")
            != NATIVE_PATH_CHECKPOINT_FIXTURE_ID
        or not isinstance(fixture_ids, list)
        or set(fixture_ids) != set(NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS)
        or request_contract != NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS
        or not isinstance(actor_guid, int) or isinstance(actor_guid, bool)
        or actor_guid <= 0
        or not isinstance(case_id, str) or not case_id
        or not isinstance(seal, str) or not re.fullmatch(r"[0-9a-f]{64}", seal)
        or not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source)
    ):
        raise ValueError("native_path_checkpoint_verified_admission_invalid")
    return (
        f"botautonativepathcheckpoint arm {actor_guid} {case_id} "
        f"{seal} {source}"
    )


def chainwielder_checkpoint_pre_route_readiness(
    status: dict[str, Any],
    *,
    recurrence_admission: dict[str, Any] | None,
    checkpoint_arm_command: str | None,
    actor_guid: int | None,
    profile_name: str,
    scenario_id: str,
    expected_route_manifest_sha256: str | None,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Validate the immutable admission boundary before route generation two."""

    reasons: list[str] = []
    try:
        expected_command = chainwielder_checkpoint_arm_command(
            recurrence_admission, actor_guid,
        )
    except ValueError as error:
        reasons.append(str(error))
        expected_command = None
    if expected_command is None or checkpoint_arm_command != expected_command:
        reasons.append("checkpoint_arm_command_identity_mismatch")
    runtime = status.get("raid_runtime")
    if not isinstance(runtime, dict):
        reasons.append("checkpoint_runtime_missing")
        return False, reasons, {"accepted": False, "identity_sha256": None}
    receipt = runtime.get("admission_receipt")
    receipt = receipt if isinstance(receipt, dict) else {}
    roster = runtime.get("roster") if isinstance(runtime.get("roster"), list) else []
    roster_rows = [row for row in roster if isinstance(row, dict)]
    route_progress = runtime.get("route_progress")
    route_progress = route_progress if isinstance(route_progress, dict) else {}
    actor_rows = [row for row in roster_rows if row.get("guid") == actor_guid]
    reasons.extend(_watchdog_scope_rejections(status, profile_name=profile_name))
    reasons.extend(f"checkpoint_{reason}" for reason in _roster_rejections(runtime, profile_name))
    expected_receipt = {
        "attempt_id": runtime.get("attempt_id"),
        "server_epoch": runtime.get("server_epoch"),
        "group_guid": runtime.get("group_guid"),
        "instance_id": runtime.get("instance_id"),
        "scenario_id": scenario_id,
        "runtime_profile": profile_name,
        "route_manifest_sha256": expected_route_manifest_sha256,
        "entrance_map_id": runtime.get("map_id"),
        "profile_generation": runtime.get("profile_generation"),
        "profile_content_hash": runtime.get("profile_content_hash"),
        "leader_guid": runtime.get("leader_guid"),
    }
    if (
        runtime.get("admission_phase") != "active"
        or runtime.get("server_provisioning_complete") is not True
        or runtime.get("bot_actions_enabled") is not True
    ):
        reasons.append("checkpoint_admission_not_active")
    if route_progress.get("generation") != 1:
        reasons.append("checkpoint_route_not_pre_generation_two")
    if (
        not _positive_int(receipt.get("committed_at_ms"))
        or receipt.get("bot_actions_enabled_at_commit") is not True
        or receipt.get("all_current_gear_matches_admission") is not True
        or any(receipt.get(key) != value for key, value in expected_receipt.items())
        or not isinstance(expected_route_manifest_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_route_manifest_sha256)
    ):
        reasons.append("checkpoint_admission_identity_mismatch")
    if len(actor_rows) != 1:
        reasons.append("checkpoint_actor_identity_missing")

    identity_projection = {
        "cohort_id": status.get("cohort_id"),
        "active_profile": status.get("active_profile"),
        "runtime_identity": {field: runtime.get(field) for field in IDENTITY_FIELDS},
        "roster_identity": _roster_binding_identity(roster_rows),
        "admission_receipt": receipt,
        "actor_guid": actor_guid,
    }
    identity_sha256 = _canonical_object_sha256(identity_projection) if not reasons else None
    facts = {
        "accepted": not reasons,
        "actor_guid": actor_guid,
        "route_generation": route_progress.get("generation"),
        "evidence_sequence": runtime.get("evidence_sequence"),
        "identity_sha256": identity_sha256,
    }
    return not reasons, list(dict.fromkeys(reasons)), facts


def _initialize_chainwielder_checkpoint_arm_gate(
    state: dict[str, Any],
) -> None:
    defaults = {
        "schema": "chainwielder_checkpoint_pre_route_arm_gate_v1",
        "required_stable_statuses": 2,
        "consecutive_stable_statuses": 0,
        "last_identity_sha256": None,
        "last_readiness": None,
        "pre_route_probe_batches": 0,
        "pre_route_probe_command_count": 0,
        "gate_open": False,
        "command_sent": False,
        "emission_count": 0,
        "emission": None,
    }
    for key, value in defaults.items():
        state.setdefault(key, value)


def observe_chainwielder_checkpoint_arm_gate(
    state: dict[str, Any],
    status: dict[str, Any],
    *,
    process: Any,
    recurrence_admission: dict[str, Any] | None,
    checkpoint_arm_command: str,
    actor_guid: int,
    profile_name: str,
    scenario_id: str,
    expected_route_manifest_sha256: str | None,
) -> dict[str, Any]:
    """Observe two stable pre-route statuses and emit the arm command once."""

    _initialize_chainwielder_checkpoint_arm_gate(state)
    ready, rejections, facts = chainwielder_checkpoint_pre_route_readiness(
        status,
        recurrence_admission=recurrence_admission,
        checkpoint_arm_command=checkpoint_arm_command,
        actor_guid=actor_guid,
        profile_name=profile_name,
        scenario_id=scenario_id,
        expected_route_manifest_sha256=expected_route_manifest_sha256,
    )
    if ready:
        if facts["identity_sha256"] == state["last_identity_sha256"]:
            state["consecutive_stable_statuses"] += 1
        else:
            state["consecutive_stable_statuses"] = 1
        state["last_identity_sha256"] = facts["identity_sha256"]
    else:
        state["consecutive_stable_statuses"] = 0
        state["last_identity_sha256"] = None
    state["last_readiness"] = {**facts, "rejections": rejections}
    state["gate_open"] = (
        ready
        and state["consecutive_stable_statuses"]
        >= state["required_stable_statuses"]
    )
    if state["gate_open"] and state["emission_count"] == 0:
        process.stdin.write((checkpoint_arm_command + "\n").encode())
        process.stdin.flush()
        state["emission_count"] = 1
        state["command_sent"] = True
        state["emission"] = {
            "actor_guid": actor_guid,
            "admission_sha256": recurrence_admission.get("admission_sha256")
                if isinstance(recurrence_admission, dict) else None,
            "identity_sha256": facts["identity_sha256"],
            "evidence_sequence": facts["evidence_sequence"],
            "route_generation": facts["route_generation"],
        }
    return state


def chainwielder_checkpoint_monitor_commands(
    scheduled_commands: list[str],
    *,
    checkpoint_arm_command: str | None,
    checkpoint_arm_gate: dict[str, Any],
) -> list[str]:
    """Add one adjacent status probe while the pre-route arm gate is pending.

    The normal five-second heartbeat allowed the validation route to advance
    from generation one to generation two between the two identity receipts
    required by the arm gate. In fixture-expansion mode, issue the second
    status in the same console batch as the scheduled heartbeat. The existing
    readiness gate still validates both responses independently and remains
    the only authority that can emit the sealed arm command.
    """

    commands = list(scheduled_commands)
    if (
        checkpoint_arm_command is None
        or checkpoint_arm_gate.get("command_sent") is True
        or "botauto status" not in commands
    ):
        return commands
    _initialize_chainwielder_checkpoint_arm_gate(checkpoint_arm_gate)
    status_index = commands.index("botauto status")
    commands.insert(status_index + 1, "botauto status")
    checkpoint_arm_gate["pre_route_probe_batches"] = int(
        checkpoint_arm_gate.get("pre_route_probe_batches") or 0
    ) + 1
    checkpoint_arm_gate["pre_route_probe_command_count"] = int(
        checkpoint_arm_gate.get("pre_route_probe_command_count") or 0
    ) + 1
    return commands
