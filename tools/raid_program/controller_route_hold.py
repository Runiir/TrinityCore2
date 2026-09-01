"""Generic fail-closed controller for the native route-hold protocol."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Callable

from tools.raid_program.recurrence_admission import (
    CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
)


def _canonical_object_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ControllerRouteHoldLaunchIdentity:
    """Controller-owned immutable inputs to one generic held route attempt."""

    scenario_id: str
    runtime_profile: str
    pool_tag: str
    route_manifest_sha256: str
    route_node_id: str
    actor_guid: int
    fixture_id: str
    seal_sha256: str
    source_commit: str
    route_generation: int = 1

    def validate(self) -> None:
        text_fields = {
            "scenario_id": self.scenario_id,
            "runtime_profile": self.runtime_profile,
            "pool_tag": self.pool_tag,
            "route_node_id": self.route_node_id,
            "fixture_id": self.fixture_id,
        }
        for name, value in text_fields.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"controller_route_hold_{name}_invalid")
        if not isinstance(self.actor_guid, int) or isinstance(self.actor_guid, bool) \
                or self.actor_guid <= 0:
            raise ValueError("controller_route_hold_actor_guid_invalid")
        if self.route_generation != 1:
            raise ValueError("controller_route_hold_initial_generation_invalid")
        for name, value, length in (
            ("route_manifest_sha256", self.route_manifest_sha256, 64),
            ("seal_sha256", self.seal_sha256, 64),
            ("source_commit", self.source_commit, 40),
        ):
            if not isinstance(value, str) or not re.fullmatch(
                rf"[0-9a-f]{{{length}}}", value
            ):
                raise ValueError(f"controller_route_hold_{name}_invalid")


@dataclass(frozen=True)
class ControllerRouteHoldRuntimeScope:
    """Authoritative instance scope frozen by the stable status pair."""

    wipe_generation: int
    instance_id: int

    @classmethod
    def from_status(
        cls, row: dict[str, Any],
    ) -> ControllerRouteHoldRuntimeScope | None:
        runtime = row.get("raid_runtime")
        if not isinstance(runtime, dict):
            return None
        wipe_generation = runtime.get("wipe_generation")
        instance_id = runtime.get("instance_id")
        if (
            not isinstance(wipe_generation, int)
            or isinstance(wipe_generation, bool)
            or wipe_generation < 0
            or not isinstance(instance_id, int)
            or isinstance(instance_id, bool)
            or instance_id <= 0
        ):
            return None
        return cls(wipe_generation=wipe_generation, instance_id=instance_id)


def controller_route_hold_launch_identity(
    *,
    recurrence_admission: dict[str, Any] | None,
    required_purpose: str,
    actor_guid: int | None,
    scenario_id: str,
    runtime_profile: str,
    pool_tag: str,
    route_manifest_sha256: str | None,
    route_node_id: str,
    expected_checkpoint_fixture_id: str = CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
) -> ControllerRouteHoldLaunchIdentity | None:
    """Build the generic hold identity from verified launch/config inputs."""

    if recurrence_admission is None and actor_guid is None:
        return None
    if not isinstance(recurrence_admission, dict):
        raise ValueError("controller_route_hold_verified_admission_missing")
    fixture_ids = recurrence_admission.get("fixture_expansion_target_ids")
    checkpoint_fixture_id = recurrence_admission.get("checkpoint_fixture_id")
    if (
        not isinstance(required_purpose, str)
        or not required_purpose
        or recurrence_admission.get("valid") is not True
        or recurrence_admission.get("purpose") != required_purpose
        or not isinstance(fixture_ids, list)
        or not fixture_ids
        or not isinstance(checkpoint_fixture_id, str)
        or not checkpoint_fixture_id.strip()
        or checkpoint_fixture_id != expected_checkpoint_fixture_id
    ):
        raise ValueError("controller_route_hold_verified_admission_invalid")
    identity = ControllerRouteHoldLaunchIdentity(
        scenario_id=scenario_id,
        runtime_profile=runtime_profile,
        pool_tag=pool_tag,
        route_manifest_sha256=route_manifest_sha256 or "",
        route_node_id=route_node_id,
        actor_guid=actor_guid if isinstance(actor_guid, int) else 0,
        fixture_id=checkpoint_fixture_id,
        seal_sha256=str(recurrence_admission.get("checkpoint_seal_sha256") or ""),
        source_commit=str(recurrence_admission.get("source_commit") or ""),
    )
    identity.validate()
    return identity


class ControllerRouteHoldScheduler:
    """Schedule commands from actual native route-hold JSON receipts."""

    _HOLD_IDENTITY_FIELDS = (
        "cohort_id", "server_epoch", "attempt_id", "scenario_id",
        "runtime_profile", "route_manifest_sha256", "route_generation",
        "route_node_id", "actor_guid", "fixture_id", "seal_sha256",
        "source_commit",
    )
    _CHECKPOINT_OUTCOME = (
        "route_identity_preserved_after_receiptless_hazard_rejection"
    )

    def __init__(self, identity: ControllerRouteHoldLaunchIdentity, *,
        checkpoint_action: str = "botauto_chainwielder_checkpoint",
        checkpoint_arm_command: str | None = None,
        checkpoint_receipt_field: str = "fixture_id",
        checkpoint_receipt_value: object = None,
        lifecycle_rejections: Callable[
            [dict[str, Any]], list[str]
        ] | None = None,
        checkpoint_observer: Callable[
            [Any, dict[str, Any]], list[str]
        ] | None = None,
        checkpoint_terminal_status_command: str = "",
        release_after_terminal: bool = True,
        checkpoint_terminal_from_status: bool = True,
        runtime_scope_required: bool = False,
    ):
        identity.validate()
        self.identity = identity
        default_arm_command = (
            "botautochaincheckpoint arm "
            f"{identity.actor_guid} {identity.seal_sha256} "
            f"{identity.source_commit}"
        )
        self._checkpoint_action = checkpoint_action
        self._checkpoint_arm_command = (
            default_arm_command
            if checkpoint_arm_command is None else checkpoint_arm_command
        )
        self._checkpoint_receipt_field = checkpoint_receipt_field
        self._checkpoint_receipt_value = (
            identity.fixture_id
            if checkpoint_receipt_value is None else checkpoint_receipt_value
        )
        self._lifecycle_rejections = (
            self._checkpoint_lifecycle_rejections
            if lifecycle_rejections is None else lifecycle_rejections
        )
        self._checkpoint_observer = checkpoint_observer
        self._checkpoint_terminal_status_command = (
            checkpoint_terminal_status_command
        )
        self._release_after_terminal = release_after_terminal
        self._checkpoint_terminal_from_status = (
            checkpoint_terminal_from_status
        )
        self._runtime_scope_required = runtime_scope_required
        self.phase = "ready"
        self.failure_reason: str | None = None
        self.command_counts = {
            "start_held": 0, "status": 0, "arm": 0, "release": 0,
        }
        self.command_transcript: list[str] = []
        self.receipt_transcript: list[dict[str, Any]] = []
        self._native_scope: dict[str, Any] | None = None
        self._runtime_scope: ControllerRouteHoldRuntimeScope | None = None
        self._held_status_bytes: bytes | None = None
        self._held_status_count = 0
        self._start_ack_count = 0
        self._arm_ack_count = 0
        self._release_ack_count = 0
        self._terminal_count = 0
        self._terminal_stage: str | None = None
        self._terminal_lifecycle: dict[str, Any] | None = None
        self._terminal_observation: dict[str, Any] | None = None

    @property
    def complete(self) -> bool:
        return self.phase in {"complete", "checkpoint_terminal_failed"}

    @property
    def failed(self) -> bool:
        return self.phase == "failed"

    @property
    def runtime_scope(self) -> ControllerRouteHoldRuntimeScope | None:
        return self._runtime_scope

    def _fail(self, reason: str) -> list[str]:
        if self.failure_reason is None:
            self.failure_reason = reason
        self.phase = "failed"
        return []

    def _emit(self, kind: str, command: str) -> list[str]:
        if self.failed:
            return []
        if self.command_counts[kind] != 0:
            return self._fail(f"controller_route_hold_duplicate_{kind}_command")
        self.command_counts[kind] = 1
        self.command_transcript.append(command)
        return [command]

    def start(self) -> list[str]:
        if self.phase != "ready":
            return self._fail("controller_route_hold_duplicate_start_held_command")
        self.phase = "awaiting_start_ack"
        return self._emit(
            "start_held",
            "botautochaincheckpoint start-held "
            f"{self.identity.actor_guid} {self.identity.fixture_id} "
            f"{self.identity.seal_sha256} {self.identity.source_commit}",
        )

    def _status_command(self) -> list[str]:
        if self.failed:
            return []
        if self.command_counts["status"] >= 2:
            return self._fail("controller_route_hold_duplicate_held_status_command")
        self.command_counts["status"] += 1
        command = "botauto status"
        self.command_transcript.append(command)
        return [command]

    @staticmethod
    def _hold_from_status(row: dict[str, Any]) -> dict[str, Any] | None:
        runtime = row.get("raid_runtime")
        if not isinstance(runtime, dict):
            return None
        hold = runtime.get("controller_route_hold")
        return hold if isinstance(hold, dict) else None

    @staticmethod
    def _hold_from_checkpoint(row: dict[str, Any]) -> dict[str, Any] | None:
        hold = row.get("controller_route_hold")
        return hold if isinstance(hold, dict) else None

    def _hold_rejections(
        self, hold: dict[str, Any], *, expected_phase: str | None = None,
    ) -> list[str]:
        expected = {
            "scenario_id": self.identity.scenario_id,
            "runtime_profile": self.identity.runtime_profile,
            "route_manifest_sha256": self.identity.route_manifest_sha256,
            "route_generation": self.identity.route_generation,
            "route_node_id": self.identity.route_node_id,
            "actor_guid": self.identity.actor_guid,
            "fixture_id": self.identity.fixture_id,
            "seal_sha256": self.identity.seal_sha256,
            "source_commit": self.identity.source_commit,
        }
        reasons: list[str] = []
        if hold.get("ok") is not True:
            reasons.append(
                str(hold.get("failure_reason") or "controller_route_hold_not_ok")
            )
        reasons.extend(
            f"controller_route_hold_{field}_mismatch"
            for field, value in expected.items() if hold.get(field) != value
        )
        if expected_phase is not None and hold.get("phase") != expected_phase:
            reasons.append("controller_route_hold_phase_mismatch")
        for field in ("cohort_id", "server_epoch", "attempt_id"):
            value = hold.get(field)
            if field == "cohort_id":
                valid = isinstance(value, str) and bool(value)
            else:
                valid = isinstance(value, int) and not isinstance(value, bool) and value > 0
            if not valid:
                reasons.append(f"controller_route_hold_{field}_invalid")
        if self._native_scope is not None:
            reasons.extend(
                f"controller_route_hold_{field}_drift"
                for field in self._HOLD_IDENTITY_FIELDS
                if hold.get(field) != self._native_scope.get(field)
            )
        return list(dict.fromkeys(reasons))

    def _checkpoint_lifecycle_rejections(
        self, hold: dict[str, Any],
    ) -> list[str]:
        lifecycle = hold.get("checkpoint_lifecycle")
        if not isinstance(lifecycle, dict):
            return ["controller_route_hold_checkpoint_lifecycle_missing"]
        rejection = lifecycle.get("rejection")
        before = lifecycle.get("before")
        after = lifecycle.get("after")
        if (
            lifecycle.get("stage") != "completed"
            or lifecycle.get("terminal") is not True
            or lifecycle.get("injection_count") != 1
            or lifecycle.get("triggered_by_active_route_path") is not True
            or lifecycle.get("triggered_by_armed_route_hazard_retry") is not False
            or lifecycle.get("before_after_identity_preserved") is not True
            or lifecycle.get("outcome") != self._CHECKPOINT_OUTCOME
        ):
            return ["controller_route_hold_checkpoint_lifecycle_invalid"]
        if rejection != {
            "owner": "hazard",
            "gate": "future_pack_destination",
            "reason": "route_destination_future_pack_unsafe",
            "planner_receipt_id": 0,
        }:
            return ["controller_route_hold_checkpoint_rejection_invalid"]
        if not isinstance(before, dict) or not isinstance(after, dict) \
                or before != after:
            return ["controller_route_hold_checkpoint_route_identity_changed"]
        if (
            before.get("movement_owner") != "route"
            or before.get("active_path_valid") is not True
            or before.get("active_path_attempt_id") != hold.get("attempt_id")
            or before.get("active_path_route_generation")
                != self.identity.route_generation
            or before.get("active_path_route_node_id") != self.identity.route_node_id
        ):
            return ["controller_route_hold_checkpoint_route_identity_invalid"]
        return []

    def _observe_checkpoint_terminal(
        self, hold: dict[str, Any],
    ) -> list[str]:
        rejections = self._hold_rejections(hold)
        lifecycle_rejections = self._lifecycle_rejections(hold)
        if (
            hold.get("phase") != "checkpoint_terminal"
            or hold.get("checkpoint_terminal") is not True
            or hold.get("checkpoint_identity_preserved") is not True
            or hold.get("checkpoint_stage") != "completed"
            or rejections
            or lifecycle_rejections
        ):
            return self._fail(
                rejections[0] if rejections
                else lifecycle_rejections[0] if lifecycle_rejections
                else "controller_route_hold_checkpoint_lifecycle_invalid"
            )
        self._terminal_count = 1
        self._terminal_stage = hold["checkpoint_stage"]
        self._terminal_lifecycle = hold["checkpoint_lifecycle"]
        if not self._release_after_terminal:
            self.phase = "complete"
            return []
        self.phase = "awaiting_release_ack"
        return self._emit(
            "release",
            "botautochaincheckpoint release "
            f"{self.identity.actor_guid} {self.identity.seal_sha256} "
            f"{self.identity.source_commit}",
        )

    def _record(self, kind: str, row: dict[str, Any], hold: dict[str, Any]) -> None:
        self.receipt_transcript.append({
            "kind": kind,
            "phase": hold.get("phase"),
            "route_generation": hold.get("route_generation"),
            "checkpoint_stage": hold.get("checkpoint_stage"),
            "checkpoint_terminal": hold.get("checkpoint_terminal"),
            "acquire_count": hold.get("acquire_count"),
            "arm_ack_count": hold.get("arm_ack_count"),
            "release_count": hold.get("release_count"),
            "payload_sha256": _canonical_object_sha256(row),
        })

    def _status_route_generation(self, row: dict[str, Any]) -> int | None:
        runtime = row.get("raid_runtime")
        runtime = runtime if isinstance(runtime, dict) else {}
        runtime_route = runtime.get("route_progress")
        runtime_route = runtime_route if isinstance(runtime_route, dict) else {}
        status_route = row.get("validation_route")
        status_route = status_route if isinstance(status_route, dict) else {}
        generations = [
            value for value in (
                runtime_route.get("generation"), status_route.get("generation")
            ) if value is not None
        ]
        if not generations or any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in generations
        ) or len(set(generations)) != 1:
            return None
        return generations[0]

    def _stable_status_projection(
        self, row: dict[str, Any], hold: dict[str, Any], route_generation: int,
        runtime_scope: ControllerRouteHoldRuntimeScope | None,
    ) -> bytes:
        runtime = row["raid_runtime"]
        projection = {
            "cohort_id": row.get("cohort_id"),
            "active_profile": row.get("active_profile"),
            "runtime_active": runtime.get("active"),
            "server_epoch": runtime.get("server_epoch"),
            "attempt_id": runtime.get("attempt_id"),
            "route_generation": route_generation,
            "runtime_scope": (
                {
                    "wipe_generation": runtime_scope.wipe_generation,
                    "instance_id": runtime_scope.instance_id,
                }
                if runtime_scope is not None else None
            ),
            "controller_route_hold": {
                field: hold.get(field) for field in self._HOLD_IDENTITY_FIELDS
            } | {
                "phase": hold.get("phase"),
                "acquire_count": hold.get("acquire_count"),
                "arm_ack_count": hold.get("arm_ack_count"),
                "checkpoint_stage": hold.get("checkpoint_stage"),
                "checkpoint_terminal": hold.get("checkpoint_terminal"),
                "checkpoint_identity_preserved": hold.get(
                    "checkpoint_identity_preserved"
                ),
                "release_count": hold.get("release_count"),
            },
        }
        return json.dumps(
            projection, sort_keys=True, separators=(",", ":"),
        ).encode()

    def _observe_direct_hold(self, row: dict[str, Any]) -> list[str]:
        hold = row
        if self.phase == "awaiting_start_ack":
            rejections = self._hold_rejections(hold, expected_phase="held")
            if (
                hold.get("acquire_count") != 1
                or hold.get("arm_ack_count") != 0
                or hold.get("release_count") != 0
                or hold.get("checkpoint_terminal") is not False
            ):
                rejections.append("controller_route_hold_start_ack_shape_invalid")
            if rejections:
                return self._fail(rejections[0])
            self._native_scope = {
                field: hold.get(field) for field in self._HOLD_IDENTITY_FIELDS
            }
            self._start_ack_count = 1
            self._record("start_held_ack", row, hold)
            self.phase = "collecting_held_status"
            return self._status_command()
        if self.phase == "awaiting_release_ack":
            rejections = self._hold_rejections(hold, expected_phase="released")
            if hold.get("release_count") != 1:
                rejections.append("controller_route_hold_release_ack_shape_invalid")
            if rejections:
                return self._fail(rejections[0])
            self._release_ack_count = 1
            self._record("release_ack", row, hold)
            self.phase = "awaiting_post_release_advance"
            self.command_counts["status"] += 1
            command = "botauto status"
            self.command_transcript.append(command)
            return [command]
        if hold.get("phase") == "held":
            return self._fail("controller_route_hold_duplicate_start_held_ack")
        if hold.get("phase") == "released":
            return self._fail("controller_route_hold_duplicate_release_ack")
        return self._fail("controller_route_hold_unexpected_direct_receipt")

    def _status_context(
        self, row: dict[str, Any], hold: dict[str, Any],
    ) -> tuple[
        dict[str, Any] | None,
        int | None,
        ControllerRouteHoldRuntimeScope | None,
        list[str],
    ]:
        """Validate one status envelope and project its typed runtime scope."""

        rejections = self._hold_rejections(hold)
        runtime = row.get("raid_runtime")
        route_generation = self._status_route_generation(row)
        runtime_scope = (
            ControllerRouteHoldRuntimeScope.from_status(row)
            if self._runtime_scope_required else None
        )
        if (
            row.get("ok") is not True
            or row.get("action") != "botauto_status"
            or row.get("active_profile") != self.identity.runtime_profile
            or not isinstance(runtime, dict)
            or runtime.get("active") is not True
            or runtime.get("server_epoch") != hold.get("server_epoch")
            or runtime.get("attempt_id") != hold.get("attempt_id")
        ):
            rejections.append("controller_route_hold_active_status_invalid")
        if route_generation is None:
            rejections.append("controller_route_hold_status_generation_invalid")
        if self._runtime_scope_required and runtime_scope is None:
            rejections.append("controller_route_hold_runtime_scope_invalid")
        if self._runtime_scope is not None and runtime_scope != self._runtime_scope:
            rejections.append("controller_route_hold_runtime_scope_drift")
        return runtime, route_generation, runtime_scope, rejections

    def _observe_status(self, row: dict[str, Any]) -> list[str]:
        hold = self._hold_from_status(row)
        if hold is None:
            return self._fail("controller_route_hold_status_receipt_missing")
        _, route_generation, runtime_scope, rejections = self._status_context(
            row, hold,
        )
        if rejections:
            return self._fail(rejections[0])
        assert route_generation is not None
        if route_generation > self.identity.route_generation and \
                self._release_ack_count != 1:
            return self._fail("controller_route_hold_route_advanced_before_release")
        self._record("status", row, hold)
        if self.phase == "collecting_held_status":
            if hold.get("phase") != "held" or route_generation != 1:
                return self._fail("controller_route_hold_unstable_held_status")
            status_bytes = self._stable_status_projection(
                row, hold, route_generation, runtime_scope,
            )
            if self._held_status_bytes is None:
                self._held_status_bytes = status_bytes
                self._runtime_scope = runtime_scope
                self._held_status_count = 1
                return self._status_command()
            if status_bytes != self._held_status_bytes:
                return self._fail("controller_route_hold_unstable_held_status")
            self._held_status_count = 2
            self.phase = "awaiting_arm_ack"
            return self._emit(
                "arm", self._checkpoint_arm_command,
            )
        if self.phase == "awaiting_terminal":
            if hold.get("phase") == "armed":
                if hold.get("arm_ack_count") != 1:
                    return self._fail("controller_route_hold_arm_ack_lost")
                return []
            if not self._checkpoint_terminal_from_status:
                return []
            return self._observe_checkpoint_terminal(hold)
        if self.phase == "awaiting_release_ack":
            if hold.get("phase") != "checkpoint_terminal":
                return self._fail("controller_route_hold_early_release_without_ack")
            return []
        if self.phase == "awaiting_post_release_advance":
            if hold.get("phase") != "released" or hold.get("release_count") != 1:
                return self._fail("controller_route_hold_release_status_invalid")
            if route_generation == self.identity.route_generation:
                return []
            if route_generation != self.identity.route_generation + 1:
                return self._fail("controller_route_hold_post_release_generation_invalid")
            self.phase = "complete"
            return []
        if self.phase in {"awaiting_start_ack", "awaiting_arm_ack"}:
            return self._fail("controller_route_hold_status_before_ack")
        if self.phase == "complete":
            return []
        return self._fail("controller_route_hold_unexpected_status")

    def _observe_arm_ack(self, row: dict[str, Any]) -> list[str]:
        hold = self._hold_from_checkpoint(row)
        if hold is None:
            return self._fail("controller_route_hold_arm_receipt_missing")
        if self.phase != "awaiting_arm_ack":
            return self._fail("controller_route_hold_duplicate_or_stale_arm_ack")
        rejections = self._hold_rejections(hold, expected_phase="armed")
        if (
            row.get("ok") is not True
            or hold.get("arm_ack_count") != 1
            or hold.get("checkpoint_terminal") is not False
            or row.get("actor_guid") != self.identity.actor_guid
            or row.get("fixture_id") != self.identity.fixture_id
            or row.get(self._checkpoint_receipt_field)
                != self._checkpoint_receipt_value
        ):
            rejections.append("controller_route_hold_arm_ack_shape_invalid")
        if rejections:
            return self._fail(rejections[0])
        self._arm_ack_count = 1
        self._record("arm_ack", row, hold)
        self.phase = "awaiting_terminal"
        return []

    def observe(self, row: dict[str, Any]) -> list[str]:
        """Consume one actual native JSON row and return ordered commands."""

        if self.failed or self.complete or not isinstance(row, dict):
            return []
        if row.get("action") == "botauto_status":
            return self._observe_status(row)
        if row.get("action") == self._checkpoint_action:
            if self._checkpoint_observer is None:
                return self._observe_arm_ack(row)
            return self._checkpoint_observer(self, row)
        if "phase" in row and "acquire_count" in row:
            return self._observe_direct_hold(row)
        return []

    def finish(self) -> None:
        if self.complete or self.failed:
            return
        missing = {
            "awaiting_start_ack": "controller_route_hold_start_ack_missing",
            "collecting_held_status": "controller_route_hold_stable_status_missing",
            "awaiting_arm_ack": "controller_route_hold_arm_ack_missing",
            "awaiting_terminal": "controller_route_hold_checkpoint_lifecycle_missing",
            "awaiting_release_ack": "controller_route_hold_release_ack_missing",
            "awaiting_post_release_advance": (
                "controller_route_hold_post_release_advance_missing"
            ),
        }.get(self.phase, "controller_route_hold_protocol_incomplete")
        self._fail(missing)

    def receipt(self) -> dict[str, Any]:
        return {
            "schema": "generic_controller_route_hold_scheduler_v1",
            "enabled": True,
            "phase": self.phase,
            "gate_passed": self.phase == "complete" and not self.failed,
            "failure_reason": self.failure_reason,
            "launch_identity": {
                field: getattr(self.identity, field)
                for field in self.identity.__dataclass_fields__
            },
            "native_scope": self._native_scope,
            "runtime_scope": (
                {
                    "wipe_generation": self._runtime_scope.wipe_generation,
                    "instance_id": self._runtime_scope.instance_id,
                }
                if self._runtime_scope is not None else None
            ),
            "held_status_count": self._held_status_count,
            "held_status_identity_sha256": (
                hashlib.sha256(self._held_status_bytes).hexdigest()
                if self._held_status_bytes is not None else None
            ),
            "start_ack_count": self._start_ack_count,
            "arm_ack_count": self._arm_ack_count,
            "checkpoint_terminal_count": self._terminal_count,
            "checkpoint_terminal_stage": self._terminal_stage,
            "checkpoint_terminal_lifecycle": self._terminal_lifecycle,
            "checkpoint_terminal_observation": self._terminal_observation,
            "release_ack_count": self._release_ack_count,
            "command_counts": dict(self.command_counts),
            "command_transcript": list(self.command_transcript),
            "receipt_transcript": list(self.receipt_transcript),
        }
