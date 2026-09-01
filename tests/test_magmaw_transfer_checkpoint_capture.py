from __future__ import annotations

import io
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.raid_program.capture_checkpoint_controller import (
    checkpoint_controller_dialect,
    magmaw_transfer_checkpoint_arm_command,
)
from tools.raid_program.capture_fixture_terminal import (
    bind_fixture_terminal_evidence,
    controller_fixture_terminal_observation,
)
from tools.raid_program.capture_live_run import execute_capture_run
from tools.raid_program.capture_run_outcome import _capture_classification
from tools.raid_program.capture_setup import CaptureSetup
from tools.raid_program.controller_route_hold import (
    ControllerRouteHoldLaunchIdentity,
    ControllerRouteHoldScheduler,
)
from tools.raid_program import recurrence_admission


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = recurrence_admission.MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID
CASE = recurrence_admission.MAGMAW_TRANSFER_CHECKPOINT_CASE_ID
ACTOR = 30007
SEAL = "a" * 64
SOURCE = "b" * 40


def _admission() -> dict[str, object]:
    return {
        "valid": True,
        "purpose": recurrence_admission.FIXTURE_EXPANSION_PURPOSE,
        "fixture_expansion_target_ids": [FIXTURE],
        "fixture_expansion_requests": [],
        "pending_fixture_ids": [FIXTURE],
        "checkpoint_fixture_id": FIXTURE,
        "checkpoint_case_id": CASE,
        "checkpoint_seal_sha256": SEAL,
        "source_commit": SOURCE,
    }


def _identity() -> ControllerRouteHoldLaunchIdentity:
    return ControllerRouteHoldLaunchIdentity(
        scenario_id="blackwing_descent_10n_magmaw_diagnostic",
        runtime_profile="blackwing_descent_10n_magmaw_diagnostic",
        pool_tag="blackwing_descent_10n_magmaw_diagnostic",
        route_manifest_sha256="c" * 64,
        route_node_id="bwd.entry.regroup",
        actor_guid=ACTOR,
        fixture_id=FIXTURE,
        seal_sha256=SEAL,
        source_commit=SOURCE,
    )


def _config_comparison(
    binary_revision_length: int = 40,
) -> dict[str, object]:
    return {
        "accepted": True,
        "failure_field": "none",
        "fixture_configured_present": True,
        "fixture_requested_present": True,
        "fixture_matches": True,
        "seal_configured_present": True,
        "seal_requested_present": True,
        "seal_matches": True,
        "source_configured_present": True,
        "source_requested_present": True,
        "source_matches": True,
        "binary_revision_present": True,
        "binary_revision_format_valid": True,
        "binary_revision_matches_source": True,
        "configured_source_length": 40,
        "requested_source_length": 40,
        "binary_revision_length": binary_revision_length,
    }


def _lifecycle(stage: str) -> dict[str, object]:
    terminal = stage in {"completed", "failed"}
    completed = stage == "completed"
    return {
        "stage": stage,
        "terminal": terminal,
        "case_id": CASE,
        "queue_count": 1 if terminal else 0,
        "candidate_attempt_count": 1 if completed else 0,
        "native_submission_count": 1 if completed else 0,
        "planner_receipt_id": 812 if completed else 0,
        "progress_samples": 4 if completed else 0,
        "outcome": (
            "magmaw_transfer_checkpoint_completed" if completed
            else "magmaw_transfer_checkpoint_start_invalid" if terminal
            else "magmaw_transfer_checkpoint_armed" if stage == "armed"
            else "disabled"
        ),
    }


def _hold(phase: str, stage: str) -> dict[str, object]:
    identity = _identity()
    terminal = phase == "checkpoint_terminal"
    return {
        "ok": True,
        "phase": phase,
        "cohort_id": "default",
        "server_epoch": 91,
        "attempt_id": 7,
        "scenario_id": identity.scenario_id,
        "runtime_profile": identity.runtime_profile,
        "route_manifest_sha256": identity.route_manifest_sha256,
        "route_generation": 1,
        "route_node_id": identity.route_node_id,
        "actor_guid": ACTOR,
        "fixture_id": FIXTURE,
        "seal_sha256": SEAL,
        "source_commit": SOURCE,
        "config_identity_comparison": _config_comparison(),
        "acquire_count": 1,
        "arm_ack_count": 1 if phase in {"armed", "checkpoint_terminal"} else 0,
        "checkpoint_stage": stage if terminal else "",
        "checkpoint_terminal": terminal,
        "checkpoint_identity_preserved": terminal,
        "checkpoint_lifecycle": _lifecycle(stage),
        "release_count": 0,
        "failure_reason": None,
    }


def _status(phase: str = "held", stage: str = "disabled") -> dict[str, object]:
    hold = _hold(phase, stage)
    return {
        "ok": True,
        "action": "botauto_status",
        "cohort_id": "default",
        "active_profile": _identity().runtime_profile,
        "validation_route": {"generation": 1},
        "raid_runtime": {
            "active": True,
            "server_epoch": 91,
            "attempt_id": 7,
            "wipe_generation": 0,
            "instance_id": 123,
            "route_progress": {"generation": 1},
            "controller_route_hold": hold,
        },
    }


def _direct_hold() -> dict[str, object]:
    return _hold("held", "disabled")


def _checkpoint_row(
    stage: str = "completed", *, binary_revision_length: int = 40,
    scope_wipe_generation: int = 0, scope_instance_id: int = 123,
) -> dict[str, object]:
    terminal = stage in {"completed", "failed"}
    completed = stage == "completed"
    lifecycle = _lifecycle(stage)
    hold = _hold("checkpoint_terminal" if terminal else "armed", stage)
    hold["config_identity_comparison"] = _config_comparison(
        binary_revision_length
    )
    return {
        "ok": not (stage == "failed"),
        "action": "botauto_magmaw_transfer_lane_checkpoint",
        "terminal_kind": "fixture_checkpoint",
        "certifies_gameplay_success": False,
        "certifies_boss_fidelity": False,
        "fixture_gate_passed": completed,
        "authority": recurrence_admission.MAGMAW_TRANSFER_CHECKPOINT_AUTHORITY,
        "fixture_id": FIXTURE,
        "case_id": CASE,
        "stage": stage,
        "terminal": terminal,
        "actor_guid": ACTOR,
        "task_authority_enabled": False,
        "scope_key": (
            f"default:7:{scope_wipe_generation}:1:bwd.entry.regroup:669:"
            f"{scope_instance_id}:"
            "magmaw_transfer_lane_checkpoint"
            if completed else ""
        ),
        "episode_generation": 17,
        "task_generation": 31,
        "legacy_generation": 43,
        "candidate_key": "magmaw_native:30007:17",
        "queue_count": lifecycle["queue_count"],
        "candidate_attempt_count": lifecycle["candidate_attempt_count"],
        "native_submission_count": lifecycle["native_submission_count"],
        "planner_receipt_id": lifecycle["planner_receipt_id"],
        "planner_candidate_key": "magmaw_native:30007:17" if completed else "",
        "motion_master_slot": 1 if completed else 0,
        "motion_master_generator_type": 8 if completed else 0,
        "spline_id": 77 if completed else 0,
        "requested_destination": {
            "x": -345.872, "y": -218.344, "z": 193.127,
        },
        "actor_start": {
            "x": -345.872, "y": -224.344, "z": 193.127,
        },
        "actor_last_same_floor": {
            "x": -345.872, "y": -218.344, "z": 193.127,
            "floor_z": 193.127,
        },
        "progress_samples": lifecycle["progress_samples"],
        "decreasing_progress_samples": 3 if completed else 0,
        "wrong_floor_samples": 1 if completed else 0,
        "task_state": "succeeded" if completed else "failed",
        "outcome": lifecycle["outcome"],
        "controller_route_hold": hold,
    }


def _scheduler() -> ControllerRouteHoldScheduler:
    dialect = checkpoint_controller_dialect(_admission(), ACTOR)
    assert isinstance(dialect, dict)
    return ControllerRouteHoldScheduler(
        _identity(), **dialect["scheduler_kwargs"],
    )


def test_launch_identity_validation_rejects_invalid_native_authority() -> None:
    identity = _identity()
    mutations = (
        ({"actor_guid": 0}, "actor_guid_invalid"),
        ({"route_generation": 2}, "initial_generation_invalid"),
        ({"route_manifest_sha256": "short"}, "route_manifest_sha256_invalid"),
        ({"seal_sha256": "short"}, "seal_sha256_invalid"),
        ({"source_commit": "short"}, "source_commit_invalid"),
    )
    for values, expected in mutations:
        with pytest.raises(ValueError, match=expected):
            replace(identity, **values).validate()


def _awaiting_terminal(
    *, binary_revision_length: int = 40,
) -> ControllerRouteHoldScheduler:
    scheduler = _awaiting_arm_ack()
    assert scheduler.observe(_checkpoint_row(
        "armed", binary_revision_length=binary_revision_length,
    )) == [
        "botautomagmawtransfercheckpoint status"
    ]
    assert scheduler.phase == "awaiting_terminal"
    return scheduler


def _awaiting_arm_ack() -> ControllerRouteHoldScheduler:
    scheduler = _scheduler()
    assert scheduler.start()
    assert scheduler.observe(_direct_hold()) == ["botauto status"]
    assert scheduler.observe(_status()) == ["botauto status"]
    assert scheduler.observe(_status()) == [
        f"botautomagmawtransfercheckpoint arm {ACTOR} {CASE} {SEAL} {SOURCE}"
    ]
    assert scheduler.phase == "awaiting_arm_ack"
    return scheduler


def test_command_is_exact_and_never_carries_coordinates() -> None:
    command = magmaw_transfer_checkpoint_arm_command(_admission(), ACTOR)
    assert command == (
        f"botautomagmawtransfercheckpoint arm {ACTOR} {CASE} {SEAL} {SOURCE}"
    )
    assert "-345" not in command and "-218" not in command
    assert len(command.split()) == 6


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("actor", 30006),
        ("case", "unknown_case"),
        ("fixture", "unknown_fixture"),
        ("seal", "short"),
        ("source", "short"),
        ("purpose", recurrence_admission.GAMEPLAY_CANARY_PURPOSE),
        ("extra_target", "unexpected"),
        ("request", {"fixture_id": FIXTURE}),
    ],
)
def test_command_rejects_unknown_or_extra_admission_arguments(
    mutation: str, value: object,
) -> None:
    admission = _admission()
    actor = ACTOR
    if mutation == "actor":
        actor = int(value)
    elif mutation == "case":
        admission["checkpoint_case_id"] = value
    elif mutation == "fixture":
        admission["checkpoint_fixture_id"] = value
    elif mutation == "seal":
        admission["checkpoint_seal_sha256"] = value
    elif mutation == "source":
        admission["source_commit"] = value
    elif mutation == "purpose":
        admission["purpose"] = value
    elif mutation == "extra_target":
        admission["fixture_expansion_target_ids"].append(value)
    else:
        admission["fixture_expansion_requests"] = [value]
    with pytest.raises(ValueError, match="verified_admission_invalid"):
        magmaw_transfer_checkpoint_arm_command(admission, actor)


def test_generic_hold_terminal_cannot_spoof_fixture_success() -> None:
    scheduler = _awaiting_terminal()
    assert scheduler.observe(_status("checkpoint_terminal", "completed")) == []
    assert scheduler.phase == "awaiting_terminal"
    assert controller_fixture_terminal_observation(
        scheduler, elapsed_seconds=1.0,
    ) == {"detected": False}


def test_production_identity_success_sentinel_arms_without_terminalizing() -> None:
    scheduler = _awaiting_arm_ack()
    assert scheduler.observe(_checkpoint_row("armed")) == [
        "botautomagmawtransfercheckpoint status"
    ]
    assert scheduler.phase == "awaiting_terminal"
    assert scheduler.complete is False
    assert scheduler.receipt()["checkpoint_terminal_count"] == 0
    assert controller_fixture_terminal_observation(
        scheduler, elapsed_seconds=1.0,
    ) == {"detected": False}


@pytest.mark.parametrize("failure_field", ["", "fixture_matches"])
def test_arm_ack_rejects_nonproduction_identity_failure_field(
    failure_field: str,
) -> None:
    scheduler = _awaiting_arm_ack()
    row = _checkpoint_row("armed")
    comparison = row["controller_route_hold"]["config_identity_comparison"]
    comparison["failure_field"] = failure_field
    assert scheduler.observe(row) == []
    assert scheduler.failure_reason == "magmaw_transfer_checkpoint_identity_invalid"


def test_arm_ack_rejects_missing_identity_failure_field() -> None:
    scheduler = _awaiting_arm_ack()
    row = _checkpoint_row("armed")
    comparison = row["controller_route_hold"]["config_identity_comparison"]
    comparison.pop("failure_field")
    assert scheduler.observe(row) == []
    assert scheduler.failure_reason == "magmaw_transfer_checkpoint_identity_invalid"


@pytest.mark.parametrize("field", [
    "accepted", "fixture_configured_present", "fixture_requested_present",
    "fixture_matches", "seal_configured_present", "seal_requested_present",
    "seal_matches", "source_configured_present", "source_requested_present",
    "source_matches", "binary_revision_present",
    "binary_revision_format_valid", "binary_revision_matches_source",
])
def test_arm_ack_rejects_each_contradictory_identity_boolean(field: str) -> None:
    scheduler = _awaiting_arm_ack()
    row = _checkpoint_row("armed")
    comparison = row["controller_route_hold"]["config_identity_comparison"]
    comparison[field] = False
    assert scheduler.observe(row) == []
    assert scheduler.failure_reason == "magmaw_transfer_checkpoint_identity_invalid"


def test_exact_dedicated_success_stops_as_non_gameplay_fixture_observation() -> None:
    scheduler = _awaiting_terminal()
    assert scheduler.observe(_checkpoint_row()) == []
    terminal = controller_fixture_terminal_observation(
        scheduler, elapsed_seconds=1.2346,
    )
    assert terminal["classification"] == "fixture_terminal_observation"
    assert terminal["terminal_kind"] == "magmaw_transfer_lane_checkpoint_terminal"
    assert terminal["fixture_gate_passed"] is True
    assert terminal["success"] is False
    assert terminal["gate_passed"] is False
    assert terminal["stage"] == "completed"
    assert terminal["checkpoint_response"]["wrong_floor_samples"] == 1
    assert terminal["elapsed_seconds"] == 1.235
    assert _capture_classification(
        success=False, forbidden_entries=[], fixture_terminal_observed=True,
        primary_gameplay_failure=False,
        operational_infrastructure_abort=False, evidence_incomplete=False,
    ) == "fixture_terminal_observation"


def test_twelve_character_binary_revision_transcript_is_valid() -> None:
    scheduler = _awaiting_terminal(binary_revision_length=12)
    assert scheduler.observe(_checkpoint_row(
        binary_revision_length=12,
    )) == []
    assert scheduler.complete is True


@pytest.mark.parametrize(
    ("path", "bad"),
    [
        (("terminal_kind",), "controller_hold"),
        (("certifies_gameplay_success",), True),
        (("certifies_boss_fidelity",), True),
        (("fixture_gate_passed",), False),
        (("task_authority_enabled",), True),
        (("fixture_id",), "wrong"),
        (("case_id",), "wrong"),
        (("actor_guid",), 30006),
        (("queue_count",), 2),
        (("candidate_attempt_count",), 2),
        (("native_submission_count",), 2),
        (("planner_receipt_id",), 0),
        (("spline_id",), 0),
        (("motion_master_slot",), 0),
        (("motion_master_generator_type",), 16),
        (("planner_candidate_key",), "wrong"),
        (("progress_samples",), 1),
        (("decreasing_progress_samples",), 4),
        (("wrong_floor_samples",), -1),
        (("actor_last_same_floor",), None),
        (("actor_last_same_floor", "y"), -224.0),
        (("episode_generation",), 18),
        (("task_generation",), 32),
        (("legacy_generation",), 44),
        (
            ("scope_key",),
            "default:7:0:1:wrong:669:123:magmaw_transfer_lane_checkpoint",
        ),
        (
            ("scope_key",),
            "default:7:999:1:bwd.entry.regroup:669:123:"
            "magmaw_transfer_lane_checkpoint",
        ),
        (
            ("scope_key",),
            "default:7:0:1:bwd.entry.regroup:669:999:"
            "magmaw_transfer_lane_checkpoint",
        ),
        (
            (
                "controller_route_hold", "config_identity_comparison",
                "configured_source_length",
            ),
            0,
        ),
        (
            (
                "controller_route_hold", "config_identity_comparison",
                "requested_source_length",
            ),
            0,
        ),
        (
            (
                "controller_route_hold", "config_identity_comparison",
                "binary_revision_length",
            ),
            0,
        ),
        (("task_state",), "running"),
        (("outcome",), "wrong"),
        (("requested_destination", "y"), -219.0),
        (("actor_start", "y"), -223.0),
        (("controller_route_hold", "checkpoint_identity_preserved"), False),
        (("controller_route_hold", "config_identity_comparison", "accepted"), False),
        (("controller_route_hold", "seal_sha256"), "d" * 64),
    ],
)
def test_every_decisive_success_mismatch_is_rejected(
    path: tuple[str, ...], bad: object,
) -> None:
    scheduler = _awaiting_terminal()
    row = _checkpoint_row()
    target: dict[str, object] = row
    for key in path[:-1]:
        target = target[key]  # type: ignore[assignment,index]
    target[path[-1]] = bad
    assert scheduler.observe(row) == []
    assert scheduler.failed is True
    assert scheduler.complete is False


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("missing", None),
        ("extra", 1),
        ("nan", float("nan")),
        ("floor", 188.0),
    ],
)
def test_same_floor_arrival_must_be_complete_finite_and_consistent(
    mutation: str, value: object,
) -> None:
    scheduler = _awaiting_terminal()
    row = _checkpoint_row()
    arrival = row["actor_last_same_floor"]
    assert isinstance(arrival, dict)
    if mutation == "missing":
        arrival.pop("floor_z")
    elif mutation == "extra":
        arrival["extra"] = value
    elif mutation == "nan":
        arrival["x"] = value
    else:
        arrival["floor_z"] = value
    assert scheduler.observe(row) == []
    assert scheduler.failed is True


@pytest.mark.parametrize(
    ("progress", "decreasing", "wrong_floor"),
    [
        (4, 3, 2),
        (4, 3, 4),
        (4, 3, 5),
        (301, 2, 299),
    ],
)
def test_progress_counts_reject_incoherent_or_unbounded_wrong_floor_samples(
    progress: int, decreasing: int, wrong_floor: int,
) -> None:
    scheduler = _awaiting_terminal()
    row = _checkpoint_row()
    row["progress_samples"] = progress
    row["decreasing_progress_samples"] = decreasing
    row["wrong_floor_samples"] = wrong_floor
    hold = row["controller_route_hold"]
    assert isinstance(hold, dict)
    lifecycle = hold["checkpoint_lifecycle"]
    assert isinstance(lifecycle, dict)
    lifecycle["progress_samples"] = progress
    assert scheduler.observe(row) == []
    assert scheduler.failed is True


@pytest.mark.parametrize("bad_length", [0, 11, 13, 39, 41])
def test_binary_revision_rejects_lengths_other_than_twelve_or_forty(
    bad_length: int,
) -> None:
    scheduler = _awaiting_terminal()
    row = _checkpoint_row(binary_revision_length=bad_length)
    assert scheduler.observe(row) == []
    assert scheduler.failed is True


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("wipe_generation", None),
        ("wipe_generation", -1),
        ("instance_id", None),
        ("instance_id", 0),
    ],
)
def test_stable_status_requires_authoritative_runtime_scope(
    field: str, bad: object,
) -> None:
    scheduler = _scheduler()
    assert scheduler.start()
    assert scheduler.observe(_direct_hold()) == ["botauto status"]
    status = _status()
    runtime = status["raid_runtime"]
    assert isinstance(runtime, dict)
    runtime[field] = bad
    assert scheduler.observe(status) == []
    assert scheduler.failure_reason == "controller_route_hold_runtime_scope_invalid"


@pytest.mark.parametrize(("field", "bad"), [("wipe_generation", 1), ("instance_id", 124)])
def test_second_stable_status_rejects_runtime_scope_drift(
    field: str, bad: int,
) -> None:
    scheduler = _scheduler()
    assert scheduler.start()
    assert scheduler.observe(_direct_hold()) == ["botauto status"]
    assert scheduler.observe(_status()) == ["botauto status"]
    status = _status()
    runtime = status["raid_runtime"]
    assert isinstance(runtime, dict)
    runtime[field] = bad
    assert scheduler.observe(status) == []
    assert scheduler.failure_reason == "controller_route_hold_runtime_scope_drift"


def test_armed_status_scope_drift_fails_before_old_scope_terminal() -> None:
    scheduler = _awaiting_terminal()
    armed = _status("armed")
    runtime = armed["raid_runtime"]
    assert isinstance(runtime, dict)
    runtime["wipe_generation"] = 1
    assert scheduler.observe(armed) == []
    assert scheduler.failure_reason == "controller_route_hold_runtime_scope_drift"
    assert scheduler.observe(_checkpoint_row()) == []
    assert scheduler.failed is True
    assert scheduler.complete is False
    assert scheduler.receipt()["checkpoint_terminal_count"] == 0


def test_success_permits_one_wrong_floor_before_three_decreasing_samples() -> None:
    scheduler = _awaiting_terminal()
    row = _checkpoint_row()
    assert row["progress_samples"] == 4
    assert row["decreasing_progress_samples"] == 3
    assert row["wrong_floor_samples"] == 1
    assert scheduler.observe(row) == []
    assert scheduler.complete is True


def test_failed_stage_is_fixture_failure_even_when_hold_terminalized() -> None:
    scheduler = _awaiting_terminal()
    row = _checkpoint_row("failed")
    assert scheduler.observe(row) == []
    terminal = controller_fixture_terminal_observation(
        scheduler, elapsed_seconds=2.0,
    )
    assert terminal["classification"] == "fixture_terminal_observation"
    assert terminal["fixture_gate_passed"] is False
    assert terminal["stage"] == "failed"
    assert terminal["success"] is False
    assert scheduler.receipt()["phase"] == "checkpoint_terminal_failed"


def test_forced_evidence_taxonomy_preserves_fixture_and_aborts_incomplete() -> None:
    scheduler = _awaiting_terminal()
    scheduler.observe(_checkpoint_row())
    terminal = controller_fixture_terminal_observation(
        scheduler, elapsed_seconds=2.0,
    )
    bound, abort = bind_fixture_terminal_evidence(
        terminal, {"gate_passed": True}, elapsed_seconds=2.1,
    )
    assert bound["final_forced_evidence"] is True
    assert abort == {"detected": False}
    incomplete, abort = bind_fixture_terminal_evidence(
        terminal,
        {"gate_passed": False, "missing_channels": ["trace"], "rejections": []},
        elapsed_seconds=2.2,
    )
    assert incomplete["classification"] == "fixture_terminal_observation"
    assert abort["classification"] == "infrastructure_abort"
    assert abort["reason"] == "fixture_terminal_forced_evidence_incomplete"


@pytest.mark.parametrize(
    "same_batch_failure", [None, "preflight", "gameplay", "both"],
)
@pytest.mark.parametrize("terminal_stage", ["completed", "failed"])
def test_prompt_loop_stops_with_full_batch_failure_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    same_batch_failure: str | None,
    terminal_stage: str,
) -> None:
    scheduler = _scheduler()
    binary = tmp_path / "worldserver"
    config = tmp_path / "worldserver.conf"
    binary.write_bytes(b"fixture")
    config.write_bytes(b"fixture")
    setup = CaptureSetup(
        args=SimpleNamespace(
            trace_transport_smoke=False, telemetry_timeout_sec=60,
            observe_sec=0, status_interval_sec=5.0,
            diagnose_interval_sec=30.0, trace_interval_sec=10.0,
            required_stable_statuses=3, resource_sample_interval_sec=5.0,
            max_repeated_decision_count=20, max_death_loop_count=3,
            semantic_stall_min_samples=12, semantic_stall_sec=300,
            startup_timeout_sec=180,
            chainwielder_checkpoint_actor_guid=None,
            magmaw_transfer_checkpoint_actor_guid=ACTOR,
        ),
        binary=binary, config=config, output=tmp_path / "capture.json",
        worktree=tmp_path,
        profile_name="blackwing_descent_10n_magmaw_diagnostic",
        scenario_id="blackwing_descent_10n_magmaw_diagnostic",
        raw_output=tmp_path / "capture.raw.jsonl",
        server_log_output=tmp_path / "capture.worldserver.log",
        recurrence_admission=_admission(),
        checkpoint_arm_command=magmaw_transfer_checkpoint_arm_command(
            _admission(), ACTOR,
        ),
        preflight={"passed": True, "reasons": []},
        identity_before={"clean": True},
        runtime_assets={"route_partition": "magmaw"},
        controller_route_hold_scheduler=scheduler,
        drudge_observed=False, drudge_required=False,
        drudge_navmesh_preflight={"required": False, "all_passed": None},
        drudge_frozen_anchors={}, build_provenance={"valid": True},
    )

    class FakeProcess:
        pid = 4321

        def __init__(self) -> None:
            self.stdin = io.BytesIO()
            self.returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            self.returncode = 0
            return 0

    process = FakeProcess()
    batches = iter([
        [SimpleNamespace(row=_direct_hold())],
        [SimpleNamespace(row=_status())],
        [SimpleNamespace(row=_status())],
        [SimpleNamespace(row=_checkpoint_row("armed"))],
        [
            SimpleNamespace(row=_checkpoint_row(terminal_stage)),
            SimpleNamespace(row=_status("checkpoint_terminal", terminal_stage)),
        ],
    ])
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.subprocess.Popen",
        lambda *args, **kwargs: process,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.wait_for_prompt",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.time.sleep", lambda _seconds: None,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.collect_log_observations",
        lambda *args, **kwargs: next(batches, []),
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.process_resource_sample",
        lambda pid, **kwargs: {"process_pid": pid, **kwargs},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.validate_forced_evidence_bundle",
        lambda *args, **kwargs: {
            "gate_passed": True, "missing_channels": [], "rejections": [],
        },
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.validate_forced_combat_log_bundle",
        lambda *args, **kwargs: {"gate_passed": True, "rejections": []},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.terminal_preflight_failure_reason",
        lambda status, **kwargs: (
            ("validation_raid_preflight_fixture_failure", [])
            if same_batch_failure in {"preflight", "both"}
            and status.get("raid_runtime", {}).get(
                "controller_route_hold", {}
            ).get("checkpoint_terminal") is True else (None, [])
        ),
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.terminal_runtime_failure_reason",
        lambda status, **kwargs: (
            ("terminal_runtime_gameplay_failure", ["raid_wipe"])
            if same_batch_failure in {"gameplay", "both"}
            and status.get("raid_runtime", {}).get(
                "controller_route_hold", {}
            ).get("checkpoint_terminal") is True else (None, [])
        ),
    )

    def fake_shutdown(child: FakeProcess, _timeout_seconds: float) -> dict:
        child.returncode = 0
        return {
            "commands_sent": ["botauto stop", "botauto status", "server exit"],
            "error": None, "operator_interrupted": False,
        }

    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.bounded_native_shutdown",
        fake_shutdown,
    )
    run = execute_capture_run(setup)
    assert run.stable == []
    assert run.semantic_stall == {"detected": False}
    assert run.process_return_code == 0
    if same_batch_failure in {"preflight", "both"}:
        assert run.fixture_terminal == {"detected": False}
        assert run.terminal_failure["classification"] == "infrastructure_abort"
        assert run.terminal_failure["terminal_kind"] == "admission_preflight"
    elif same_batch_failure == "gameplay":
        assert run.fixture_terminal == {"detected": False}
        assert run.terminal_failure["classification"] == "gameplay_failure"
        assert run.terminal_failure["failure_reason"] == (
            "terminal_runtime_gameplay_failure"
        )
        assert run.terminal_failure["final_forced_evidence"] is True
    else:
        assert run.fixture_terminal["classification"] == (
            "fixture_terminal_observation"
        )
        assert run.fixture_terminal["fixture_gate_passed"] is (
            terminal_stage == "completed"
        )
        assert run.fixture_terminal["final_forced_evidence"] is True
        assert run.terminal_failure == {"detected": False}


def _seal_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], dict[str, object]]:
    binary = tmp_path / "worldserver"
    build = tmp_path / "build.json"
    decision = tmp_path / "decision.json"
    profile = tmp_path / "profiles.json"
    binary.write_bytes(b"elf")
    build.write_text("{}", encoding="utf-8")
    decision.write_text(json.dumps({
        "fixture_expansion_target_ids": [FIXTURE],
        "pending_fixture_ids": [FIXTURE],
        "fixture_expansion_requests": [],
    }), encoding="utf-8")
    profile.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        recurrence_admission, "_git",
        lambda _worktree, *args, **_kwargs: (
            SOURCE if args[-1] == "HEAD" else "e" * 40
        ),
    )
    kwargs = {
        "worktree": ROOT,
        "binary": binary,
        "build_receipt": build,
        "decision": decision,
        "case_id": CASE,
        "profile_manifest": profile,
        "runtime_profile_overlay": {"profile": "map669"},
        "expected_runtime_profile_id": "map669",
    }
    return kwargs, {"decision": decision, "profile": profile}


def test_seal_binds_probe_profile_and_source_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    kwargs, files = _seal_inputs(tmp_path, monkeypatch)
    seal = recurrence_admission.magmaw_transfer_checkpoint_seal(**kwargs)
    assert seal["fixture_id"] == FIXTURE
    assert seal["case_id"] == CASE
    assert seal["source_commit"] == SOURCE
    assert seal["probe_receipt_sha256"] == recurrence_admission.sha256_file(
        ROOT / recurrence_admission.MAGMAW_TRANSFER_CHECKPOINT_PROBE
    )
    files["profile"].write_text('{"drift":true}', encoding="utf-8")
    assert recurrence_admission.magmaw_transfer_checkpoint_seal(
        **kwargs
    )["seal_sha256"] != seal["seal_sha256"]
    config = tmp_path / "worldserver.conf"
    config.write_text("\n".join([
        "BotWorld.ValidationRoute.Enable = 1",
        "BotWorld.Magmaw.TransferLaneTaskAuthority = 0",
        "BotWorld.ValidationFixture.MagmawTransferLaneCheckpoint.Enable = 1",
        f'BotWorld.ValidationFixture.MagmawTransferLaneCheckpoint.FixtureId = "{FIXTURE}"',
        f'BotWorld.ValidationFixture.MagmawTransferLaneCheckpoint.CaseId = "{CASE}"',
        f'BotWorld.ValidationFixture.MagmawTransferLaneCheckpoint.SealSha256 = "{seal["seal_sha256"]}"',
        f'BotWorld.ValidationFixture.MagmawTransferLaneCheckpoint.SourceCommit = "{SOURCE}"',
    ]) + "\n", encoding="utf-8")
    with pytest.raises(
        recurrence_admission.RecurrenceAdmissionError,
        match="seal_identity_mismatch",
    ):
        recurrence_admission._verify_magmaw_transfer_checkpoint_seal(
            seal=seal, runtime_config=config,
            **{key: value for key, value in kwargs.items() if key != "case_id"},
        )


@pytest.mark.parametrize(
    ("config_key", "config_value", "error"),
    [
        ("BotWorld.Magmaw.TransferLaneTaskAuthority", "1", "task_authority_enabled"),
        ("BotWorld.ValidationRoute.Enable", "0", "progress_sampling_disabled"),
        (
            "BotWorld.ValidationFixture.MagmawTransferLaneCheckpoint.CaseId",
            '"wrong"', "config_mismatch",
        ),
    ],
)
def test_prestart_verifier_rejects_authority_or_config_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    config_key: str, config_value: str, error: str,
) -> None:
    kwargs, _ = _seal_inputs(tmp_path, monkeypatch)
    seal = recurrence_admission.magmaw_transfer_checkpoint_seal(**kwargs)
    config = tmp_path / "worldserver.conf"
    values = {
        "BotWorld.ValidationRoute.Enable": "1",
        "BotWorld.Magmaw.TransferLaneTaskAuthority": "0",
        "BotWorld.ValidationFixture.MagmawTransferLaneCheckpoint.Enable": "1",
        "BotWorld.ValidationFixture.MagmawTransferLaneCheckpoint.FixtureId": f'"{FIXTURE}"',
        "BotWorld.ValidationFixture.MagmawTransferLaneCheckpoint.CaseId": f'"{CASE}"',
        "BotWorld.ValidationFixture.MagmawTransferLaneCheckpoint.SealSha256": f'"{seal["seal_sha256"]}"',
        "BotWorld.ValidationFixture.MagmawTransferLaneCheckpoint.SourceCommit": f'"{SOURCE}"',
    }
    values[config_key] = config_value
    config.write_text(
        "\n".join(f"{key} = {value}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(recurrence_admission.RecurrenceAdmissionError, match=error):
        recurrence_admission._verify_magmaw_transfer_checkpoint_seal(
            seal=seal, runtime_config=config,
            **{key: value for key, value in kwargs.items() if key != "case_id"},
        )


def test_capture_modules_and_import_graph_stay_bounded() -> None:
    paths = [
        ROOT / "tools/raid_program/recurrence_checkpoint_seals.py",
        ROOT / "tools/raid_program/recurrence_admission.py",
        ROOT / "tools/raid_program/capture_checkpoint_controller.py",
        ROOT / "tools/raid_program/capture_terminal_batch.py",
        ROOT / "tools/raid_program/capture_live_run.py",
        ROOT / "tools/raid_program/controller_route_hold.py",
        ROOT / "tools/raid_program/capture_setup.py",
        ROOT / "tools/raid_program/capture_fixture_terminal.py",
        ROOT / "tools/raid_program/capture_finalization.py",
    ]
    assert all(len(path.read_text(encoding="utf-8").splitlines()) < 1000
               for path in paths)
    assert recurrence_admission.RecurrenceAdmissionError.__module__ == (
        "tools.raid_program.recurrence_checkpoint_seals"
    )
