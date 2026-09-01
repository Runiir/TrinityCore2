"""Typed capture termination for verified controller fixture observations."""

from __future__ import annotations

from typing import Any


def controller_fixture_terminal_observation(
    scheduler: Any, *, elapsed_seconds: float,
) -> dict[str, Any]:
    """Project one verified failed checkpoint into a typed capture terminal.

    ``checkpoint_terminal_failed`` is set only after the scheduler validates
    the native receipt, lifecycle, identity, and planner payload. It is a
    completed fixture observation, not a successful gameplay gate and not a
    gameplay failure. Keeping this projection separate prevents the generic
    semantic-stall watchdog from relabelling an already terminal fixture.
    """

    if scheduler is None or scheduler.phase != "checkpoint_terminal_failed":
        return {"detected": False}
    receipt = scheduler.receipt()
    observation = receipt.get("checkpoint_terminal_observation")
    lifecycle = receipt.get("checkpoint_terminal_lifecycle")
    if (
        scheduler.complete is not True
        or scheduler.failed is True
        or receipt.get("gate_passed") is not False
        or receipt.get("checkpoint_terminal_count") != 1
        or receipt.get("checkpoint_terminal_stage") != "failed"
        or not isinstance(observation, dict)
        or observation.get("ok") is not False
        or observation.get("terminal") is not True
        or observation.get("stage") != "failed"
        or not isinstance(lifecycle, dict)
        or lifecycle.get("terminal") is not True
        or lifecycle.get("stage") != "failed"
        or observation.get("outcome") != lifecycle.get("outcome")
    ):
        raise RuntimeError("controller route hold failed terminal invalid")
    return {
        "detected": True,
        "classification": "fixture_terminal_observation",
        "terminal_kind": "native_path_checkpoint_failed_terminal",
        "success": False,
        "gate_passed": False,
        "scheduler_phase": receipt["phase"],
        "fixture_id": receipt["launch_identity"]["fixture_id"],
        "case_id": lifecycle.get("case_id"),
        "stage": observation["stage"],
        "outcome": observation["outcome"],
        "movement_planner": observation.get("movement_planner"),
        "elapsed_seconds": round(elapsed_seconds, 3),
    }


def bind_fixture_terminal_evidence(
    fixture_terminal: dict[str, Any],
    forced_evidence_report: dict[str, Any],
    *,
    elapsed_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Attach final evidence without converting the fixture into gameplay."""

    if fixture_terminal.get("detected") is not True:
        raise ValueError("fixture terminal evidence binding requires a terminal")
    result = dict(fixture_terminal)
    result["final_forced_evidence"] = (
        forced_evidence_report.get("gate_passed") is True
    )
    result["final_forced_evidence_report"] = forced_evidence_report
    if forced_evidence_report.get("gate_passed") is True:
        return result, {"detected": False}
    return result, {
        "detected": True,
        "classification": "infrastructure_abort",
        "reason": "fixture_terminal_forced_evidence_incomplete",
        "missing_channels": forced_evidence_report.get("missing_channels", []),
        "rejections": forced_evidence_report.get("rejections", []),
        "elapsed_seconds": round(elapsed_seconds, 3),
    }
