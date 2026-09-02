import ast
from dataclasses import replace
import hashlib
import json
import io
from math import hypot
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tools.raid_program.capture_phase1_raid_foundation import (
    accepted_foundation_status,
    accepted_drudge_contract,
    accepted_native_recovery,
    action_payloads,
    JsonLogCursor,
    JsonLogObservation,
    TelemetryTransportLedger,
    collect_log_observations,
    _json_row_from_log_line,
    json_actions,
    json_rows,
    normalized_batch_payload,
    _normalized_batch_payload_impl,
    _forbidden_assistance_entries,
    _dvc_status_is_clean,
    _process_arguments,
    _protected_process_matches,
    expected_bwd_10n_roster,
    _provisioned_bwd_bots,
    _provisioned_bwd_10n_bots,
    _canonical_int_list,
    _expected_identity_by_slot,
    _runtime_gear_manifest,
    _compact_trailing_zero_gems,
    _identity_manifest_rejections,
    _roster_identity,
    _roster_rejections,
    preflight_runtime_exclusions,
    git_identity,
    _utc_timestamp,
    validate_build_receipt,
    validate_runtime_profile_assets,
    evidence_demux_report,
    _evidence_demux_report_impl,
    _required_telemetry_envelope_report,
    _trace_actor_transport_rejections,
    evidence_demux_rejections,
    write_normalized_batch,
    semantic_progress_signature,
    observe_monotonic_semantic_progress,
    observe_capture_watchdog,
    observe_telemetry_freshness,
    TelemetryScheduler,
    material_status_signature,
    terminal_preflight_failure_reason,
    terminal_runtime_failure_reason,
    validate_forced_combat_log_bundle,
    validate_forced_evidence_bundle,
    _primary_gameplay_terminal,
    _terminal_evidence_incomplete,
    _capture_classification,
    _artifact_record,
    bounded_native_shutdown,
    wait_for_prompt,
    build_policy_path_for_receipt,
    sha256_file,
    _frozen_drudge_member_anchors,
    _validate_drudge_observation_geometry,
    process_resource_sample,
    summarize_process_resource_samples,
    native_readycheck_request_identity,
    ready_for_native_readycheck,
    chainwielder_checkpoint_arm_command,
    chainwielder_checkpoint_pre_route_readiness,
    _initialize_chainwielder_checkpoint_arm_gate,
    chainwielder_checkpoint_monitor_commands,
    observe_chainwielder_checkpoint_arm_gate,
    ControllerRouteHoldLaunchIdentity,
    ControllerRouteHoldScheduler,
    CaptureSetup,
    build_capture_parser,
    prepare_capture_setup,
    CaptureRunResult,
    execute_capture_run,
    finalize_capture,
)
from tools.raid_program.capture_setup import recurrence_profile_authority
from tools.raid_program.chainwielder_prestart_bundle import (
    PERSONAL_THREAT_EPISODE_SCOPE_KEY_TEMPLATE,
)
from tools.raid_program.capture_finalization import (
    resolve_personal_threat_episode_target,
)
from tools.raid_program.capture_checkpoint_controller import (
    checkpoint_controller_dialect,
)
from tools.raid_program.recurrence_admission import (
    CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
)


def _personal_threat_target_declaration() -> dict:
    return {
        "actor_guid": 30008,
        "scope_key": PERSONAL_THREAT_EPISODE_SCOPE_KEY_TEMPLATE,
        "route_node_id": "bwd.magmaw.encounter",
        "route_generation": 3,
        "parent_wave_generation": (1 << 63) | 1,
        "parent_generation_authoritative": False,
    }


def _personal_threat_route_assets(tmp_path: Path) -> dict:
    route = tmp_path / "prepared-route.json"
    route.write_text(json.dumps({
        "routes": [
            {"step": 1, "route_node_id": "bwd.magmaw.chainwielder", "map_id": 669},
            {"step": 2, "route_node_id": "bwd.magmaw.drudges", "map_id": 669},
            {
                "step": 3, "route_node_id": "bwd.magmaw.encounter", "map_id": 669,
                "mechanic_profile": "tank_swap_adds_raid_aoe",
            },
        ],
    }), encoding="utf-8")
    return {
        "route_manifest": str(route),
        "route_partition": {
            "node_ids": [
                "bwd.magmaw.chainwielder", "bwd.magmaw.drudges",
                "bwd.magmaw.encounter",
            ],
        },
    }


def _personal_threat_route_hold_receipt(*, instance_id: int = 7) -> dict:
    return {
        "enabled": True,
        "phase": "complete",
        "gate_passed": True,
        "failure_reason": None,
        "held_status_count": 2,
        "held_status_identity_sha256": "e" * 64,
        "native_scope": {"cohort_id": "default", "attempt_id": 1},
        "runtime_scope": {"wipe_generation": 0, "instance_id": instance_id},
    }


def test_personal_threat_target_resolves_only_from_stable_route_hold_scope(
    tmp_path: Path,
) -> None:
    resolved, binding = resolve_personal_threat_episode_target(
        _personal_threat_target_declaration(),
        controller_route_hold_receipt=_personal_threat_route_hold_receipt(),
        runtime_assets=_personal_threat_route_assets(tmp_path),
    )
    assert resolved["scope_key"] == (
        "default:1:0:3:bwd.magmaw.encounter:669:7:tank_swap_adds_raid_aoe"
    )
    assert ":2:" not in resolved["scope_key"]
    assert binding["gate_passed"] is True
    assert binding["declaration_receipt"]["scope_key_template"] == (
        PERSONAL_THREAT_EPISODE_SCOPE_KEY_TEMPLATE
    )
    assert binding["resolution_receipt"]["runtime_scope"] == {
        "wipe_generation": 0, "instance_id": 7,
    }


@pytest.mark.parametrize(
    "mutation",
    ["missing_pair", "scope_drift", "route_mismatch", "parent_mismatch"],
)
def test_personal_threat_target_binding_fails_closed(
    tmp_path: Path, mutation: str,
) -> None:
    receipt = _personal_threat_route_hold_receipt()
    target = _personal_threat_target_declaration()
    assets = _personal_threat_route_assets(tmp_path)
    if mutation == "missing_pair":
        receipt["held_status_count"] = 1
    elif mutation == "scope_drift":
        receipt["failure_reason"] = "controller_route_hold_runtime_scope_drift"
    elif mutation == "route_mismatch":
        target["route_node_id"] = "bwd.magmaw.drudges"
    else:
        target["parent_wave_generation"] += 1
    resolved, binding = resolve_personal_threat_episode_target(
        target, controller_route_hold_receipt=receipt, runtime_assets=assets,
    )
    assert binding["gate_passed"] is False
    assert binding["resolution_receipt"]["rejections"]
    assert resolved["scope_key"] == target["scope_key"]


def test_normal_gameplay_admission_does_not_supply_fixture_profile_authority():
    profile, expected = recurrence_profile_authority(
        fixture_expansion_replay=False,
        configured_profile_manifest="dataset/bot_runtime_profiles/profiles.json",
        runtime_profile="blackwing_descent_10n_magmaw_diagnostic",
    )
    assert profile is None
    assert expected is None


def test_fixture_replay_admission_supplies_exact_profile_authority(tmp_path: Path):
    manifest = tmp_path / "profiles.json"
    profile, expected = recurrence_profile_authority(
        fixture_expansion_replay=True,
        configured_profile_manifest=str(manifest),
        runtime_profile="blackwing_descent_10n_magmaw_diagnostic",
    )
    assert profile == manifest.resolve()
    assert expected == "blackwing_descent_10n_magmaw_diagnostic"


def test_checkpoint_free_fixture_expansion_has_no_synthetic_controller():
    admission = {
        "valid": True,
        "purpose": "fixture_expansion_replay",
        "fixture_expansion_target_ids": [
            "magmaw_parasite_control_full_runtime_v1",
        ],
        "fixture_expansion_requests": [{
            "fixture_id": "magmaw_parasite_control_full_runtime_v1",
            "from_revision": 7,
            "to_revision": 8,
            "causal_signature": "magmaw_parasite_control_allows_player_infection",
            "required_production_boundary": "observe production behavior",
        }],
        "checkpoint_fixture_id": None,
        "checkpoint_seal_sha256": None,
        "checkpoint_case_id": None,
    }

    assert checkpoint_controller_dialect(admission, None) is None


def test_checkpoint_free_fixture_expansion_rejects_synthetic_actor():
    admission = {
        "valid": True,
        "purpose": "fixture_expansion_replay",
        "fixture_expansion_target_ids": [
            "magmaw_parasite_control_full_runtime_v1",
        ],
        "fixture_expansion_requests": [{
            "fixture_id": "magmaw_parasite_control_full_runtime_v1",
            "from_revision": 7,
            "to_revision": 8,
            "causal_signature": "magmaw_parasite_control_allows_player_infection",
            "required_production_boundary": "observe production behavior",
        }],
        "checkpoint_fixture_id": None,
        "checkpoint_seal_sha256": None,
        "checkpoint_case_id": None,
    }

    with pytest.raises(ValueError, match="checkpoint_free_fixture_expansion_invalid"):
        checkpoint_controller_dialect(admission, 30008)


def _scheduler_status(*, route_index: int = 0, encounter: bool = False) -> dict:
    return {
        "ok": True,
        "raid_runtime": {
            "active": True,
            "strategy_id": "blackwing_descent_10n",
            "assignment_generation": 1,
            "route_progress": {"manifest_index": route_index},
            "encounter_in_progress": encounter,
            "boss_states": [0] * 6,
            "alive_size": 10,
            "expected_size": 10,
            "wipe_state": "ready",
            "recovery_state": "none",
            "wipe_generation": 0,
            "boss_reset_generation": 0,
            "recovery_generation": 0,
            "ready_check_satisfied": True,
            "roster_complete": True,
        },
        "validation_route": {
            "manifest_index": route_index,
            "generation": 1,
            "node_id": f"node-{route_index}",
            "kind": "trash" if route_index else "regroup",
            "manifest_complete": False,
            "terminal_evidence": [],
            "boss_death_evidence": [],
        },
    }


def test_chainwielder_checkpoint_arm_uses_verified_precomputed_seal():
    admission = _verified_checkpoint_admission()
    seal = admission["checkpoint_seal_sha256"]
    commit = admission["source_commit"]

    assert chainwielder_checkpoint_arm_command(admission, 30008) == (
        f"botautochaincheckpoint arm 30008 {seal} {commit}"
    )


def test_chainwielder_checkpoint_arm_accepts_only_verified_composite_targets():
    admission = _verified_checkpoint_admission()
    requests = [
        {
            "fixture_id": "same_level_floor_observation_v1",
            "from_revision": 3,
            "to_revision": 4,
            "causal_signature": "same_level_movement_path_floor_false_negative",
            "required_production_boundary": "map_669_native_floor_observation",
        },
        {
            "fixture_id": "same_level_hazard_path_admission_v1",
            "from_revision": 4,
            "to_revision": 5,
            "causal_signature": "same_level_encounter_hazard_path_rejection",
            "required_production_boundary": "map_669_native_hazard_path_admission",
        },
        {
            "fixture_id": "same_level_native_path_proof_v1",
            "from_revision": 4,
            "to_revision": 5,
            "causal_signature": "same_level_native_path_proof_false_negative",
            "required_production_boundary": "map_669_native_path_proof",
        },
    ]
    target_ids = [
        "chainwielder_pre_admission_rejection_isolation_v1",
        *(request["fixture_id"] for request in requests),
    ]
    admission.update(
        fixture_expansion_target_ids=target_ids,
        fixture_expansion_requests=requests,
        pending_fixture_ids=["chainwielder_pre_admission_rejection_isolation_v1"],
        fixture_revisions={
            request["fixture_id"]: request["from_revision"]
            for request in requests
        },
    )

    assert chainwielder_checkpoint_arm_command(admission, 30008) is not None

    auxiliary = json.loads(json.dumps(admission))
    auxiliary["fixture_expansion_target_ids"].pop(0)
    auxiliary["pending_fixture_ids"] = []
    assert chainwielder_checkpoint_arm_command(auxiliary, 30008) is not None

    rejected = []
    for mutation in (
        "missing_checkpoint_identity", "unexpected_target", "stale", "wrong_gate"
    ):
        candidate = json.loads(json.dumps(admission))
        if mutation == "missing_checkpoint_identity":
            candidate["checkpoint_fixture_id"] = None
        elif mutation == "unexpected_target":
            candidate["fixture_expansion_target_ids"].append("unexpected_fixture_v1")
        elif mutation == "stale":
            candidate["fixture_revisions"][requests[0]["fixture_id"]] = 2
        else:
            candidate["purpose"] = "gameplay_canary"
        try:
            chainwielder_checkpoint_arm_command(candidate, 30008)
        except ValueError as error:
            rejected.append((mutation, str(error)))
        else:
            raise AssertionError(f"{mutation} composite target set was admitted")
    assert rejected == [
        (mutation, "checkpoint_verified_admission_invalid")
        for mutation in (
            "missing_checkpoint_identity", "unexpected_target", "stale",
            "wrong_gate",
        )
    ]


def test_chainwielder_checkpoint_arm_fails_closed_on_wrong_arm_value():
    admission = _verified_checkpoint_admission()

    for actor_guid in (None, 0, -1):
        try:
            chainwielder_checkpoint_arm_command(admission, actor_guid)
        except ValueError as error:
            assert str(error) == "checkpoint_actor_guid_required"
        else:
            raise AssertionError("invalid checkpoint actor was admitted")

    admission["checkpoint_seal_sha256"] = "wrong"
    try:
        chainwielder_checkpoint_arm_command(admission, 30008)
    except ValueError as error:
        assert str(error) == "checkpoint_verified_seal_invalid"
    else:
        raise AssertionError("invalid checkpoint seal was admitted")

    try:
        chainwielder_checkpoint_arm_command(None, 30008)
    except ValueError as error:
        assert str(error) == "checkpoint_actor_without_verified_seal"
    else:
        raise AssertionError("unsealed checkpoint arm was admitted")


def test_checkpoint_pre_route_readiness_resolves_watchdog_scope_validator():
    status = checkpoint_pre_route_status()
    admission = _verified_checkpoint_admission()
    command = chainwielder_checkpoint_arm_command(admission, 30008)

    accepted, reasons, receipt = chainwielder_checkpoint_pre_route_readiness(
        status,
        recurrence_admission=admission,
        checkpoint_arm_command=command,
        actor_guid=30008,
        profile_name="blackwing_descent_10n_magmaw_diagnostic",
        scenario_id="blackwing_descent_10n_magmaw_diagnostic",
        expected_route_manifest_sha256="d" * 64,
    )

    assert accepted is True
    assert reasons == []
    assert receipt["accepted"] is True


def test_capture_support_helpers_use_focused_production_modules():
    checkpoint_module = "tools.raid_program.capture_checkpoint_controller"
    for owner in (
        chainwielder_checkpoint_arm_command,
        chainwielder_checkpoint_pre_route_readiness,
        _initialize_chainwielder_checkpoint_arm_gate,
        observe_chainwielder_checkpoint_arm_gate,
        chainwielder_checkpoint_monitor_commands,
    ):
        assert owner.__module__ == checkpoint_module

    outcome_module = "tools.raid_program.capture_run_outcome"
    for owner in (
        _primary_gameplay_terminal,
        _terminal_evidence_incomplete,
        _capture_classification,
        process_resource_sample,
        summarize_process_resource_samples,
    ):
        assert owner.__module__ == outcome_module

    runtime_io_module = "tools.raid_program.capture_runtime_io"
    for owner in (wait_for_prompt, _artifact_record, bounded_native_shutdown):
        assert owner.__module__ == runtime_io_module


def test_capture_setup_uses_focused_production_module():
    setup_module = "tools.raid_program.capture_setup"
    assert CaptureSetup.__module__ == setup_module
    assert build_capture_parser.__module__ == setup_module
    assert prepare_capture_setup.__module__ == setup_module


def test_capture_parser_preserves_cli_defaults(tmp_path: Path):
    root = tmp_path / "default-worktree"
    parser = build_capture_parser(root=root)

    args = parser.parse_args([
        "--binary", "worldserver",
        "--config", "worldserver.conf",
        "--output", "capture.json",
        "--build-receipt", "build.json",
    ])

    assert args.worktree == root
    assert args.runtime_profile is None
    assert args.scenario_id is None
    assert args.pool_tag is None
    assert args.observe_sec == 0
    assert args.startup_timeout_sec == 180
    assert args.required_stable_statuses == 3
    assert args.semantic_stall_sec == 300
    assert args.semantic_stall_min_samples == 12
    assert args.telemetry_timeout_sec == 60
    assert args.status_interval_sec == 5.0
    assert args.diagnose_interval_sec == 30.0
    assert args.trace_interval_sec == 10.0
    assert args.resource_sample_interval_sec == 5.0
    assert args.fixture_expansion_replay is False
    assert args.trace_transport_smoke is False
    assert args.personal_threat_episode_actor_guid is None
    assert args.personal_threat_episode_scope_key is None
    assert args.personal_threat_episode_route_node_id is None
    assert args.personal_threat_episode_route_generation is None
    assert args.personal_threat_episode_parent_wave_generation is None
    assert args.personal_threat_episode_parent_generation_authoritative is None


def test_prepare_capture_setup_returns_typed_admitted_state(tmp_path: Path, monkeypatch):
    binary = tmp_path / "worldserver"
    config = tmp_path / "worldserver.conf"
    receipt = tmp_path / "build.json"
    output = tmp_path / "capture.json"
    for path in (binary, config, receipt):
        path.write_bytes(b"fixture")

    monkeypatch.setattr(
        "tools.raid_program.capture_setup.chainwielder_checkpoint_arm_command",
        lambda admission, actor_guid: None,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.trinity_config_bool",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.preflight_runtime_exclusions",
        lambda worktree: {"passed": True, "reasons": []},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.git_identity",
        lambda worktree: {"clean": True, "commit": "a" * 40},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.validate_runtime_profile_assets",
        lambda *args, **kwargs: {
            "passed": True,
            "reasons": [],
            "route_manifest": None,
            "route_partition": "stonecore_5n",
        },
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.build_policy_path_for_receipt",
        lambda build_receipt, worktree: tmp_path / "policy.json",
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.validate_build_receipt",
        lambda *args, **kwargs: {"valid": True, "rejections": []},
    )

    setup = prepare_capture_setup([
        "--binary", str(binary),
        "--config", str(config),
        "--output", str(output),
        "--build-receipt", str(receipt),
        "--worktree", str(tmp_path),
        "--runtime-profile", "stonecore_5n",
    ], root=tmp_path)

    assert isinstance(setup, CaptureSetup)
    assert setup.binary == binary.resolve()
    assert setup.config == config.resolve()
    assert setup.output == output.resolve()
    assert setup.raw_output == tmp_path / "capture.raw.jsonl"
    assert setup.server_log_output == tmp_path / "capture.worldserver.log"
    assert setup.profile_name == "stonecore_5n"
    assert setup.scenario_id == "stonecore_5n"
    assert setup.preflight == {"passed": True, "reasons": []}
    assert setup.runtime_assets["route_partition"] == "stonecore_5n"
    assert setup.build_provenance == {"valid": True, "rejections": []}
    assert setup.controller_route_hold_scheduler is None
    assert setup.drudge_observed is False
    assert setup.drudge_required is False
    assert setup.personal_threat_episode_target is None

    targeted = prepare_capture_setup([
        "--binary", str(binary),
        "--config", str(config),
        "--output", str(tmp_path / "targeted-capture.json"),
        "--build-receipt", str(receipt),
        "--worktree", str(tmp_path),
        "--runtime-profile", "stonecore_5n",
        "--personal-threat-episode-actor-guid", "30008",
        "--personal-threat-episode-scope-key",
        PERSONAL_THREAT_EPISODE_SCOPE_KEY_TEMPLATE,
        "--personal-threat-episode-route-node-id", "bwd.magmaw.encounter",
        "--personal-threat-episode-route-generation", "3",
        "--personal-threat-episode-parent-wave-generation",
        str((1 << 63) | 1),
        "--no-personal-threat-episode-parent-generation-authoritative",
    ], root=tmp_path)
    assert targeted.personal_threat_episode_target == {
        "actor_guid": 30008,
        "scope_key": PERSONAL_THREAT_EPISODE_SCOPE_KEY_TEMPLATE,
        "route_node_id": "bwd.magmaw.encounter",
        "route_generation": 3,
        "parent_wave_generation": (1 << 63) | 1,
        "parent_generation_authoritative": False,
    }

    with pytest.raises(
        SystemExit,
        match="personal_threat_episode_target:incomplete",
    ):
        prepare_capture_setup([
            "--binary", str(binary),
            "--config", str(config),
            "--output", str(tmp_path / "incomplete-capture.json"),
            "--build-receipt", str(receipt),
            "--personal-threat-episode-actor-guid", "30008",
        ], root=tmp_path)


def test_targeted_chainwielder_scheduler_binds_stable_runtime_scope_before_demux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the production setup path and its typed scheduler scope gate."""

    binary = tmp_path / "worldserver"
    config = tmp_path / "worldserver.conf"
    receipt = tmp_path / "build.json"
    admission_path = tmp_path / "admission.json"
    route = tmp_path / "prepared-route.json"
    for path in (binary, config, receipt, admission_path):
        path.write_bytes(b"fixture")
    route.write_text("{}", encoding="utf-8")
    target = _personal_threat_target_declaration()
    admission = {
        "valid": True,
        "purpose": "fixture_expansion_replay",
        "fixture_expansion_target_ids": ["chainwielder_checkpoint"],
        "checkpoint_fixture_id": CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        "checkpoint_seal_sha256": "a" * 64,
        "source_commit": "b" * 40,
    }
    identity = ControllerRouteHoldLaunchIdentity(
        scenario_id="blackwing_descent_10n_magmaw_diagnostic",
        runtime_profile="blackwing_descent_10n_magmaw_diagnostic",
        pool_tag="blackwing_descent_10n_magmaw_diagnostic",
        route_manifest_sha256="c" * 64,
        route_node_id="bwd.magmaw.chainwielder",
        actor_guid=30008,
        fixture_id=CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        seal_sha256="a" * 64,
        source_commit="b" * 40,
    )

    monkeypatch.setattr(
        "tools.raid_program.capture_setup.trinity_config_string",
        lambda _config, key: str(tmp_path / "profiles.json")
        if key == "BotWorld.ProfileManifest" else "",
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.trinity_config_bool",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.verify_recurrence_admission",
        lambda *args, **kwargs: admission,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.checkpoint_controller_dialect",
        lambda *args, **kwargs: {
            "fixture_id": CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
            "arm_command": "botautochaincheckpoint arm",
            "scheduler_kwargs": {},
        },
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.controller_route_hold_runtime_manifest_identity",
        lambda **kwargs: {
            "route_manifest_sha256": "c" * 64,
            "initial_route_node_id": "bwd.magmaw.chainwielder",
        },
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.controller_route_hold_launch_identity",
        lambda **kwargs: identity,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.preflight_runtime_exclusions",
        lambda worktree: {"passed": True, "reasons": []},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.git_identity",
        lambda worktree: {"clean": True, "commit": "b" * 40},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.validate_runtime_profile_assets",
        lambda *args, **kwargs: {
            "passed": True,
            "reasons": [],
            "route_manifest": str(route),
            "pool_tag_filter": "blackwing_descent_10n_magmaw_diagnostic",
        },
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup._drudge_navmesh_probe",
        lambda worktree: {"all_passed": True},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup._frozen_drudge_member_anchors",
        lambda route_manifest: {
            member: (0.0, 0.0, 0.0) for member in range(1, 11)
        },
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.build_policy_path_for_receipt",
        lambda build_receipt, worktree: tmp_path / "policy.json",
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.validate_build_receipt",
        lambda *args, **kwargs: {"valid": True, "rejections": []},
    )

    setup = prepare_capture_setup([
        "--binary", str(binary),
        "--config", str(config),
        "--output", str(tmp_path / "capture.json"),
        "--build-receipt", str(receipt),
        "--recurrence-admission", str(admission_path),
        "--recurrence-admission-sha256", "d" * 64,
        "--chainwielder-checkpoint-actor-guid", "30008",
        "--fixture-expansion-replay",
        "--scenario-id", "blackwing_descent_10n_magmaw_diagnostic",
        "--runtime-profile", "blackwing_descent_10n_magmaw_diagnostic",
        "--pool-tag", "blackwing_descent_10n_magmaw_diagnostic",
        "--personal-threat-episode-actor-guid", str(target["actor_guid"]),
        "--personal-threat-episode-scope-key", target["scope_key"],
        "--personal-threat-episode-route-node-id", target["route_node_id"],
        "--personal-threat-episode-route-generation", str(target["route_generation"]),
        "--personal-threat-episode-parent-wave-generation",
        str(target["parent_wave_generation"]),
        "--no-personal-threat-episode-parent-generation-authoritative",
    ], root=tmp_path)
    scheduler = setup.controller_route_hold_scheduler
    assert scheduler is not None

    def hold() -> dict[str, object]:
        return {
            "ok": True,
            "phase": "held",
            "cohort_id": "cohort-a",
            "server_epoch": 71,
            "attempt_id": 9,
            "scenario_id": identity.scenario_id,
            "runtime_profile": identity.runtime_profile,
            "route_manifest_sha256": identity.route_manifest_sha256,
            "route_generation": 1,
            "route_node_id": identity.route_node_id,
            "actor_guid": identity.actor_guid,
            "fixture_id": identity.fixture_id,
            "seal_sha256": identity.seal_sha256,
            "source_commit": identity.source_commit,
            "acquire_count": 1,
            "arm_ack_count": 0,
            "checkpoint_terminal": False,
            "release_count": 0,
        }

    def status(*, instance_id: int | None = 7) -> dict[str, object]:
        runtime = {
            "active": True,
            "server_epoch": 71,
            "attempt_id": 9,
            "route_progress": {"generation": 1},
            "controller_route_hold": hold(),
        }
        if instance_id is not None:
            runtime.update({"wipe_generation": 0, "instance_id": instance_id})
        return {
            "ok": True,
            "action": "botauto_status",
            "cohort_id": "cohort-a",
            "active_profile": identity.runtime_profile,
            "raid_runtime": runtime,
            "validation_route": {"generation": 1},
        }

    assert scheduler.start()
    assert scheduler.observe(hold()) == ["botauto status"]
    assert scheduler.observe(status()) == ["botauto status"]
    assert scheduler.observe(status())[0].startswith(
        "botautochaincheckpoint arm"
    )
    receipt_value = scheduler.receipt()
    assert receipt_value["runtime_scope"] == {
        "wipe_generation": 0, "instance_id": 7,
    }
    assert receipt_value["held_status_count"] == 2
    resolved, binding = resolve_personal_threat_episode_target(
        target,
        controller_route_hold_receipt=receipt_value,
        runtime_assets=_personal_threat_route_assets(tmp_path),
    )
    assert binding["gate_passed"] is True
    assert resolved is not None
    assert resolved["scope_key"] == (
        "cohort-a:9:0:3:bwd.magmaw.encounter:669:7:tank_swap_adds_raid_aoe"
    )

    missing_scope = ControllerRouteHoldScheduler(
        identity, runtime_scope_required=True,
    )
    missing_scope.start()
    missing_scope.observe(hold())
    missing_scope.observe(status(instance_id=None))
    assert missing_scope.failure_reason == (
        "controller_route_hold_runtime_scope_invalid"
    )
    _, missing_binding = resolve_personal_threat_episode_target(
        target,
        controller_route_hold_receipt=missing_scope.receipt(),
        runtime_assets=_personal_threat_route_assets(tmp_path),
    )
    assert missing_binding["gate_passed"] is False

    drifted_scope = ControllerRouteHoldScheduler(
        identity, runtime_scope_required=True,
    )
    drifted_scope.start()
    drifted_scope.observe(hold())
    drifted_scope.observe(status())
    drifted_scope.observe(status(instance_id=8))
    assert drifted_scope.failure_reason == (
        "controller_route_hold_runtime_scope_drift"
    )
    _, drift_binding = resolve_personal_threat_episode_target(
        target,
        controller_route_hold_receipt=drifted_scope.receipt(),
        runtime_assets=_personal_threat_route_assets(tmp_path),
    )
    assert drift_binding["gate_passed"] is False

    target_free = ControllerRouteHoldScheduler(identity)
    target_free.start()
    target_free.observe(hold())
    assert target_free.observe(status(instance_id=None)) == ["botauto status"]
    assert target_free.observe(status(instance_id=None))[0].startswith(
        "botautochaincheckpoint arm"
    )
    assert target_free.failure_reason is None
    assert target_free.receipt()["runtime_scope"] is None


def test_capture_live_run_uses_focused_production_module():
    run_module = "tools.raid_program.capture_live_run"
    assert CaptureRunResult.__module__ == run_module
    assert execute_capture_run.__module__ == run_module
    controller_source = (
        Path(__file__).resolve().parents[1]
        / "tools/raid_program/capture_finalization.py"
    ).read_text(encoding="utf-8")
    assert controller_source.index('demux_rejections = demux_report["rejections"]') < (
        controller_source.index(
            "default_trace_transport_gate = trace_transport_smoke.evaluate([])"
        )
    ) < controller_source.index("trace_transport_demux = trace_transport_smoke.demux_report")


def test_execute_capture_run_owns_fake_process_and_live_loop(tmp_path: Path, monkeypatch):
    binary = tmp_path / "worldserver"
    config = tmp_path / "worldserver.conf"
    server_log = tmp_path / "worldserver.log"
    binary.write_bytes(b"fixture")
    config.write_bytes(b"fixture")
    args = SimpleNamespace(
        trace_transport_smoke=False,
        telemetry_timeout_sec=60,
        observe_sec=0,
        status_interval_sec=5.0,
        diagnose_interval_sec=30.0,
        trace_interval_sec=10.0,
        required_stable_statuses=2,
        resource_sample_interval_sec=5.0,
        max_repeated_decision_count=20,
        max_death_loop_count=3,
        semantic_stall_min_samples=12,
        semantic_stall_sec=300,
        startup_timeout_sec=180,
        chainwielder_checkpoint_actor_guid=None,
    )
    setup = CaptureSetup(
        args=args,
        binary=binary,
        config=config,
        output=tmp_path / "capture.json",
        worktree=tmp_path,
        profile_name="stonecore_5n",
        scenario_id="stonecore_5n",
        raw_output=tmp_path / "capture.raw.jsonl",
        server_log_output=server_log,
        recurrence_admission=None,
        checkpoint_arm_command=None,
        preflight={"passed": True, "reasons": []},
        identity_before={"clean": True},
        runtime_assets={"route_partition": "stonecore_5n"},
        controller_route_hold_scheduler=None,
        drudge_observed=False,
        drudge_required=False,
        drudge_navmesh_preflight={"required": False, "all_passed": None},
        drudge_frozen_anchors={},
        build_provenance={"valid": True},
    )

    class FakeProcess:
        pid = 4321

        def __init__(self):
            self.stdin = io.BytesIO()
            self.returncode = None

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.returncode = 0
            return 0

    process = FakeProcess()
    statuses = [
        SimpleNamespace(row={"action": "botauto_status", "sequence": sequence})
        for sequence in (1, 2)
    ]
    observation_batches = iter([statuses])

    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.subprocess.Popen",
        lambda *args, **kwargs: process,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.wait_for_prompt",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.time.sleep",
        lambda seconds: None,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.collect_log_observations",
        lambda *args, **kwargs: next(observation_batches, []),
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.process_resource_sample",
        lambda pid, **kwargs: {"pid": pid, **kwargs},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.terminal_preflight_failure_reason",
        lambda status, **kwargs: (None, []),
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.accepted_foundation_status",
        lambda status, **kwargs: (True, []),
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.terminal_runtime_failure_reason",
        lambda status, **kwargs: (None, []),
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.observe_capture_watchdog",
        lambda *args, **kwargs: {"detected": False},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.observe_telemetry_freshness",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.semantic_progress_signature",
        lambda *args, **kwargs: ("progress",),
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.observe_monotonic_semantic_progress",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.ready_for_native_readycheck",
        lambda status: False,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.validate_forced_evidence_bundle",
        lambda *args, **kwargs: {
            "gate_passed": True,
            "missing_channels": [],
            "rejections": [],
        },
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.validate_forced_combat_log_bundle",
        lambda *args, **kwargs: {
            "gate_passed": True,
            "rejections": [],
        },
    )

    def fake_shutdown(child, timeout_seconds):
        child.returncode = 0
        return {
            "commands_sent": ["botauto stop", "botauto status", "server exit"],
            "error": None,
            "operator_interrupted": False,
        }

    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.bounded_native_shutdown",
        fake_shutdown,
    )

    result = execute_capture_run(setup)

    assert isinstance(result, CaptureRunResult)
    assert result.process_return_code == 0
    assert len(result.stable) == 2
    assert result.last_rejections == []
    assert result.forced_evidence_report["gate_passed"] is True
    assert result.stop_commands_sent is True
    assert result.log_bytes == b""
    assert process.stdin.getvalue().startswith(b"botauto start stonecore_5n\n")
    assert b"botauto status\n" in process.stdin.getvalue()


def test_capture_finalization_uses_focused_production_module():
    finalization_module = "tools.raid_program.capture_finalization"
    for owner in (
        finalize_capture,
        normalized_batch_payload,
        evidence_demux_report,
        evidence_demux_rejections,
        write_normalized_batch,
    ):
        assert owner.__module__ == finalization_module


def test_finalize_capture_writes_golden_report_and_keeps_abort_precedence(
    tmp_path: Path, monkeypatch, capsys,
):
    from tools.raid_program import capture_finalization

    config = tmp_path / "worldserver.conf"
    output = tmp_path / "capture.json"
    raw_output = tmp_path / "capture.raw.jsonl"
    server_log = tmp_path / "capture.worldserver.log"
    config.write_bytes(b"fixture-config")
    server_log.write_bytes(b"fixture-log")
    prepared_route = tmp_path / "prepared-route.json"
    prepared_route.write_text(json.dumps({
        "routes": [
            {"step": 1, "route_node_id": "bwd.magmaw.chainwielder", "map_id": 669},
            {"step": 2, "route_node_id": "bwd.magmaw.drudges", "map_id": 669},
                {
                    "step": 3, "route_node_id": "bwd.magmaw.encounter", "map_id": 669,
                    "mechanic_profile": "tank_swap_adds_raid_aoe",
                },
        ],
    }), encoding="utf-8")
    personal_threat_episode_target = {
        "actor_guid": 30008,
        "scope_key": PERSONAL_THREAT_EPISODE_SCOPE_KEY_TEMPLATE,
        "route_node_id": "bwd.magmaw.encounter",
        "route_generation": 3,
        "parent_wave_generation": (1 << 63) | 1,
        "parent_generation_authoritative": False,
    }
    args = SimpleNamespace(
        trace_transport_smoke=False,
        chainwielder_checkpoint_actor_guid=None,
        resource_sample_interval_sec=5.0,
        required_stable_statuses=2,
        status_interval_sec=5.0,
        diagnose_interval_sec=30.0,
        trace_interval_sec=10.0,
        observe_sec=0,
        startup_timeout_sec=180,
        semantic_stall_sec=300,
        semantic_stall_min_samples=12,
        max_repeated_decision_count=20,
        max_death_loop_count=3,
        telemetry_timeout_sec=60,
    )
    identity = {"clean": True, "commit": "a" * 40}
    controller_route_hold_receipt = {
        "schema": "generic_controller_route_hold_scheduler_v1",
        "enabled": True,
        "phase": "complete",
        "gate_passed": True,
        "failure_reason": None,
        "held_status_count": 2,
        "held_status_identity_sha256": "e" * 64,
        "start_ack_count": 1,
        "native_scope": {
            "cohort_id": "default",
            "attempt_id": 1,
            "runtime_profile": "stonecore_5n",
        },
        "runtime_scope": {"wipe_generation": 0, "instance_id": 7},
    }

    class _RouteHold:
        def receipt(self):
            return controller_route_hold_receipt

    setup = CaptureSetup(
        args=args,
        binary=tmp_path / "worldserver",
        config=config,
        output=output,
        worktree=tmp_path,
        profile_name="stonecore_5n",
        scenario_id="stonecore_5n",
        raw_output=raw_output,
        server_log_output=server_log,
        recurrence_admission=None,
        checkpoint_arm_command=None,
        preflight={"passed": True, "reasons": []},
        identity_before=identity,
        runtime_assets={
            "passed": True,
            "pool_tag_filter": None,
            "route_manifest": str(prepared_route),
            "route_partition": {
                "node_ids": [
                    "bwd.magmaw.chainwielder", "bwd.magmaw.drudges",
                    "bwd.magmaw.encounter",
                ],
            },
        },
        controller_route_hold_scheduler=_RouteHold(),
        drudge_observed=False,
        drudge_required=False,
        drudge_navmesh_preflight={"required": False, "all_passed": None},
        drudge_frozen_anchors={},
        build_provenance={"valid": True, "binary_sha256": "b" * 64},
        personal_threat_episode_target=personal_threat_episode_target,
    )
    stable_statuses = [
        {"raid_runtime": {"active": True, "sequence": sequence}}
        for sequence in (1, 2)
    ]
    run = CaptureRunResult(
        started_utc="2026-08-30T12:00:00Z",
        recovery_required=False,
        stable=stable_statuses,
        last_rejections=[],
        startup_error=None,
        process_return_code=0,
        telemetry_scheduler=None,
        telemetry_transport_ledger=TelemetryTransportLedger(),
        telemetry_command_counts={
            "status": 1,
            "diagnose": 1,
            "trace": 1,
            "trace_pressure": 0,
            "combat_log": 1,
        },
        trace_transport_pressure_gate={"gate_passed": None},
        operator_interrupt=False,
        shutdown_error=None,
        stop_commands_sent=True,
        checkpoint_arm_command_sent=False,
        checkpoint_arm_gate={"required": False, "gate_open": False},
        resource_samples=[],
        resource_sampling_errors=[],
        resource_sampling_error_count=0,
        resource_tick_rate=100,
        forced_evidence_report={"requested": True, "gate_passed": True},
        fixture_terminal={"detected": False},
        terminal_failure={"detected": False},
        semantic_stall={"detected": False},
        controller_watchdog={"detected": False},
        trace_transport_gate=None,
        telemetry_abort={"detected": False},
        log_bytes=b"fixture-log",
    )
    normalized_rows = [
        {"action": "first", "payload": {"sequence": 1}, "evidence_channel": "status"},
        {
            "action": "botauto_combatlog_complete",
            "payload": {"sequence": 2},
            "evidence_channel": "combat_log",
        },
    ]
    action_rows = {
        "botauto_status": [{"bots": 0, "lease_count": 0}],
        "botauto_diagnose": [{"ok": True}],
        "botauto_trace": [{"ok": True}],
        "botauto_profile": [{
            "ok": True,
            "cohort_id": "default",
            "active_profile": "stonecore_5n",
        }],
        "botauto_stop": [{"ok": True}],
    }
    monkeypatch.setattr(
        capture_finalization,
        "normalized_batch_payload",
        lambda log_bytes, **kwargs: normalized_rows,
    )
    monkeypatch.setattr(
        capture_finalization,
        "_required_telemetry_envelope_report",
        lambda *args, **kwargs: {"gate_passed": True, "rejections": []},
    )
    monkeypatch.setattr(
        capture_finalization,
        "action_payloads",
        lambda rows, action: action_rows.get(action, []),
    )
    monkeypatch.setattr(
        capture_finalization,
        "combat_log_transport_status",
        lambda payloads: {"complete_marker": True, "reassembled": True},
    )
    monkeypatch.setattr(
        capture_finalization,
        "combined_combat_log",
        lambda payloads: "combat-log",
    )
    monkeypatch.setattr(
        capture_finalization,
        "analyze_combat_log",
        lambda combat_log: {"damage": 1, "healing": 1},
    )
    monkeypatch.setattr(
        capture_finalization,
        "preflight_runtime_exclusions",
        lambda worktree: {"passed": True, "process_overlap": []},
    )
    monkeypatch.setattr(
        capture_finalization,
        "_forbidden_assistance_entries",
        lambda rows: [],
    )
    monkeypatch.setattr(capture_finalization, "git_identity", lambda worktree: identity)
    complete_join = {
        "requested": True,
        "target": {
            **personal_threat_episode_target,
            "scope_key": PERSONAL_THREAT_EPISODE_SCOPE_KEY_TEMPLATE.format(
                cohort_id="default", attempt_id=1, wipe_generation=0,
                instance_id=7,
            ),
        },
        "records": [
            {"edge": "falling", "capture_sequence": 1},
            {"edge": "rising", "capture_sequence": 2},
        ],
        "falling_count": 1,
        "rising_count": 1,
        "rejections": [],
        "gate_passed": True,
    }
    demux_targets = []

    def finalization_demux(*args, **kwargs):
        demux_targets.append(kwargs.get("personal_threat_episode_target"))
        return {
            "rejections": [],
            "retained_rows": 2,
            "bound_rows": 2,
            "rejected_rows": 0,
            "unchecked_rows": 0,
            "canonical_identity_sha256": "c" * 64,
            "canonical_roster_sha256": "d" * 64,
            "required_telemetry_envelopes": {"gate_passed": True},
            "actor_binding_counts": {},
            "trace_discontinuities": [],
            "personal_threat_episode_join": complete_join,
            "gate_passed": True,
        }

    monkeypatch.setattr(
        capture_finalization, "evidence_demux_report", finalization_demux,
    )
    monkeypatch.setattr(
        capture_finalization.trace_transport_smoke,
        "evaluate",
        lambda receipts: {"gate_passed": False, "terminal": False},
    )
    monkeypatch.setattr(capture_finalization.signal, "signal", lambda *args: None)
    artifact_observations = []
    real_artifact_record = capture_finalization._artifact_record

    def observed_artifact_record(path, kind):
        artifact_observations.append((kind, raw_output.exists(), output.exists()))
        return real_artifact_record(path, kind)

    monkeypatch.setattr(capture_finalization, "_artifact_record", observed_artifact_record)

    exit_code = finalize_capture(setup, run)

    stdout_report = json.loads(capsys.readouterr().out)
    stored_report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert stdout_report == stored_report
    assert stored_report["classification"] == "success"
    assert demux_targets == [complete_join["target"]]
    assert stored_report["evidence_demux"][
        "personal_threat_episode_join"
    ] == complete_join
    assert stored_report["raw_normalized_batch"]["row_count"] == 2
    assert [json.loads(line) for line in raw_output.read_text().splitlines()] == normalized_rows
    assert artifact_observations == [
        ("raw_normalized_jsonl", True, False),
        ("raw_worldserver_log", True, False),
    ]
    hash_payload = json.loads(json.dumps(stored_report))
    expected_hash = hash_payload["report_sha256"]
    hash_payload["report_sha256"] = None
    hash_payload["artifact_inventory"][-1]["sha256"] = None
    assert hashlib.sha256(
        json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest() == expected_hash

    abort_output = tmp_path / "fixture-terminal-abort.json"
    abort_raw_output = tmp_path / "fixture-terminal-abort.raw.jsonl"
    abort_server_log = tmp_path / "fixture-terminal-abort.worldserver.log"
    abort_server_log.write_bytes(b"fixture-log")
    abort_setup = replace(
        setup,
        output=abort_output,
        raw_output=abort_raw_output,
        server_log_output=abort_server_log,
    )
    abort_run = replace(
        run,
        forced_evidence_report={"requested": True, "gate_passed": False},
        fixture_terminal={
            "detected": True,
            "classification": "fixture_terminal_observation",
            "terminal_kind": "native_path_checkpoint_failed_terminal",
            "success": False,
            "gate_passed": False,
            "outcome": "native_path_checkpoint_stage_submit_failed",
        },
        telemetry_abort={
            "detected": True,
            "classification": "infrastructure_abort",
            "reason": "fixture_terminal_forced_evidence_incomplete",
        },
    )

    abort_exit_code = finalize_capture(abort_setup, abort_run)
    abort_stdout_report = json.loads(capsys.readouterr().out)
    abort_stored_report = json.loads(abort_output.read_text(encoding="utf-8"))
    assert abort_exit_code == 2
    assert abort_stdout_report == abort_stored_report
    assert abort_stored_report["classification"] == "infrastructure_abort"
    assert abort_stored_report["fixture_terminal"]["detected"] is True
    assert abort_stored_report["telemetry_abort"]["reason"] == (
        "fixture_terminal_forced_evidence_incomplete"
    )
    assert demux_targets[-1] == complete_join["target"]

    gameplay_output = tmp_path / "gameplay-terminal-incomplete.json"
    gameplay_raw_output = tmp_path / "gameplay-terminal-incomplete.raw.jsonl"
    gameplay_server_log = (
        tmp_path / "gameplay-terminal-incomplete.worldserver.log"
    )
    gameplay_server_log.write_bytes(b"fixture-log")
    gameplay_setup = replace(
        setup,
        output=gameplay_output,
        raw_output=gameplay_raw_output,
        server_log_output=gameplay_server_log,
    )
    gameplay_run = replace(
        run,
        forced_evidence_report={"requested": True, "gate_passed": False},
        fixture_terminal={"detected": False},
        terminal_failure={
            "detected": True,
            "classification": "gameplay_failure",
            "failure_reason": "death_loop_watchdog",
        },
        telemetry_abort={
            "detected": True,
            "classification": "infrastructure_abort",
            "reason": "terminal_failure_forced_evidence_incomplete",
        },
    )

    gameplay_exit_code = finalize_capture(gameplay_setup, gameplay_run)
    gameplay_stdout_report = json.loads(capsys.readouterr().out)
    gameplay_stored_report = json.loads(
        gameplay_output.read_text(encoding="utf-8")
    )
    assert gameplay_exit_code == 2
    assert gameplay_stdout_report == gameplay_stored_report
    assert gameplay_stored_report["classification"] == "gameplay_failure"
    assert gameplay_stored_report["terminal_evidence_incomplete"] is True
    assert gameplay_stored_report["telemetry_abort"]["reason"] == (
        "terminal_failure_forced_evidence_incomplete"
    )
    assert demux_targets[-1] == complete_join["target"]

    try:
        finalize_capture(setup, run)
    except RuntimeError as error:
        assert str(error) == "raw normalized batch output already exists; artifacts are immutable"
    else:
        raise AssertionError("second finalization overwrote immutable evidence")


def _verified_checkpoint_admission() -> dict:
    return {
        "valid": True,
        "admission_sha256": "9" * 64,
        "source_commit": "b" * 40,
        "source_tree": "c" * 40,
        "purpose": "fixture_expansion_replay",
        "fixture_expansion_target_ids": [
            "chainwielder_pre_admission_rejection_isolation_v1"
        ],
        "fixture_expansion_requests": [],
        "pending_fixture_ids": [
            "chainwielder_pre_admission_rejection_isolation_v1"
        ],
        "fixture_revisions": {},
        "checkpoint_seal_sha256": "a" * 64,
        "checkpoint_fixture_id": (
            "chainwielder_pre_admission_rejection_isolation_v1"
        ),
    }


def test_telemetry_scheduler_reduces_steady_state_heavy_commands():
    scheduler = TelemetryScheduler(status_interval_sec=5, diagnose_interval_sec=15, trace_interval_sec=10)
    commands = [command for now in range(0, 61) for command in scheduler.commands_due(float(now))]

    assert commands.count("botauto status") == 13
    assert commands.count("botauto diagnose all") == 5
    assert commands.count("botauto trace all 128 delta") == 7
    assert commands.count("botauto diagnose all") < commands.count("botauto status")


def test_telemetry_transport_uses_focused_production_module():
    expected_module = "tools.raid_program.capture_telemetry_transport"
    for owner in (
        _json_row_from_log_line,
        JsonLogCursor,
        JsonLogObservation,
        collect_log_observations,
        TelemetryTransportLedger,
        json_actions,
        json_rows,
        action_payloads,
        observe_telemetry_freshness,
        material_status_signature,
        TelemetryScheduler,
    ):
        assert owner.__module__ == expected_module


def test_default_scheduler_reduces_heavy_payload_volume_without_dropping_channels():
    scheduler = TelemetryScheduler()
    assert scheduler.status_interval_sec == 5.0
    assert scheduler.diagnose_interval_sec == 30.0
    assert scheduler.trace_interval_sec == 10.0
    commands = [command for now in range(0, 121) for command in scheduler.commands_due(float(now))]
    assert commands.count("botauto status") == 25
    assert commands.count("botauto diagnose all") == 5
    assert commands.count("botauto trace all 128 delta") == 13
    assert set(commands) == {
        "botauto status", "botauto diagnose all", "botauto trace all 128 delta",
    }


def test_trace_scheduler_shortens_after_ring_pressure_without_accepting_gaps():
    scheduler = TelemetryScheduler(
        status_interval_sec=5, diagnose_interval_sec=15, trace_interval_sec=10,
    )
    assert scheduler.commands_due(0.0) == [
        "botauto status", "botauto trace all 128 delta", "botauto diagnose all",
    ]

    scheduler.observe_trace(
        [{
            "ok": True,
            "action": "botauto_trace",
            "bots": [{"entries": [{}] * 16, "gap": False}],
        }],
        observed_at=1.0,
    )
    state = scheduler.state()
    assert state["trace_pressure_entries"] == 16
    assert state["effective_trace_interval_seconds"] == 2.0
    assert state["trace_gap_observed"] is False
    assert scheduler.commands_due(2.9) == []
    assert scheduler.commands_due(3.0) == ["botauto trace all 128 delta"]

    # A gap only records the integrity observation. It does not make the
    # response valid or reset/advance the native cursor on the controller's
    # behalf; evidence_demux_report remains the rejecting authority.
    scheduler.observe_trace(
        [{
            "ok": True,
            "action": "botauto_trace",
            "bots": [{"entries": [], "gap": True}],
        }],
        observed_at=4.0,
    )
    state = scheduler.state()
    assert state["trace_gap_observed"] is True
    assert state["effective_trace_interval_seconds"] == 2.0

    gap_only = TelemetryScheduler(trace_interval_sec=10)
    gap_only.commands_due(0.0)
    gap_only.observe_trace(
        [{"bots": [{"entries": [], "gap": True}]}], observed_at=1.0,
    )
    assert gap_only.state()["trace_gap_observed"] is True
    assert gap_only.state()["effective_trace_interval_seconds"] == 10.0
    assert gap_only.commands_due(2.0) == []


def test_terminal_runtime_failure_is_exact_roster_bound_and_material():
    status = accepted_status()
    status["cohort_id"] = "default"
    status["active_profile"] = "blackwing_descent_10n"
    baseline = material_status_signature(status)

    status["failure_reason"] = "drudge_partial_death_before_threat_seed"
    reason, rejections = terminal_runtime_failure_reason(status)

    assert reason == "drudge_partial_death_before_threat_seed"
    assert rejections == []
    assert material_status_signature(status) != baseline

    status["raid_runtime"]["roster"][0]["lease_owned"] = False
    reason, rejections = terminal_runtime_failure_reason(status)
    assert reason is None
    assert "terminal_failure_all_roster_leases_owned" in rejections


def test_runtime_acceptance_uses_focused_production_module():
    expected_module = "tools.raid_program.capture_runtime_acceptance"
    for owner in (
        expected_bwd_10n_roster,
        _provisioned_bwd_bots,
        _provisioned_bwd_10n_bots,
        _canonical_int_list,
        _expected_identity_by_slot,
        _runtime_gear_manifest,
        _compact_trailing_zero_gems,
        _identity_manifest_rejections,
        _roster_identity,
        _roster_rejections,
        accepted_foundation_status,
        terminal_preflight_failure_reason,
        terminal_runtime_failure_reason,
        accepted_native_recovery,
        native_readycheck_request_identity,
    ):
        assert owner.__module__ == expected_module


def test_terminal_preflight_failure_stops_before_semantic_stall_and_keeps_active_terminal_semantics():
    status = accepted_status()
    status["active_profile"] = "blackwing_descent_10n"
    status["bots"] = 0
    status["lease_count"] = 0
    status["failure_reason"] = "validation_raid_preflight_full_stat_seed_missing"
    status["raid_runtime"].update(
        active=False,
        admission_phase="terminal",
        expected_size=0,
        active_size=0,
        alive_size=0,
        roster_complete=False,
        roster=[],
    )

    reason, rejections = terminal_preflight_failure_reason(status)

    assert reason == "validation_raid_preflight_full_stat_seed_missing"
    assert rejections == []

    active = accepted_status()
    active["cohort_id"] = "default"
    active["active_profile"] = "blackwing_descent_10n"
    active["failure_reason"] = "drudge_partial_death_before_threat_seed"
    assert terminal_preflight_failure_reason(active)[0] is None
    gameplay_reason, gameplay_rejections = terminal_runtime_failure_reason(active)
    assert gameplay_reason == "drudge_partial_death_before_threat_seed"
    assert gameplay_rejections == []


class _FakeShutdownProcess:
    def __init__(self, *, interrupt_once: bool = False) -> None:
        self.stdin = io.BytesIO()
        self.returncode = None
        self.wait_calls = 0
        self.interrupt_once = interrupt_once

    def poll(self):
        return self.returncode

    def wait(self, *, timeout: float):
        self.wait_calls += 1
        if self.interrupt_once:
            self.interrupt_once = False
            raise KeyboardInterrupt
        self.returncode = 0
        return self.returncode


def test_bounded_native_shutdown_sends_cleanup_and_handles_operator_interrupt():
    process = _FakeShutdownProcess(interrupt_once=True)
    result = bounded_native_shutdown(process, 20.0)

    assert process.stdin.getvalue() == b"botauto stop\nbotauto status\nserver exit\n"
    assert result["commands_sent"] is True
    assert result["operator_interrupted"] is True
    assert result["exited"] is True
    assert result["error"] is None
    assert process.wait_calls == 2


def test_process_resource_sample_reuses_baseline_proc_units_and_binds_run_identity(monkeypatch):
    monkeypatch.setattr(
        "tools.raid_program.capture_run_outcome._baseline_process_sample",
        lambda pid: {
            "monotonic_sec": 12.5,
            "process_cpu_ticks": 321,
            "process_rss_bytes": 987654,
            "host_load_1m": 999,
        },
    )
    sample = process_resource_sample(
        4242,
        sample_sequence=3,
        scenario_id="magmaw-shard",
        runtime_profile="magmaw-shard",
        status={
            "cohort_id": "cohort-a",
            "raid_runtime": {
                "server_epoch": 8,
                "attempt_id": 9,
                "profile_generation": 2,
                "assignment_generation": 4,
                "instance_id": 55,
            },
        },
    )

    assert sample == {
        "sample_sequence": 3,
        "process_pid": 4242,
        "monotonic_sec": 12.5,
        "process_cpu_ticks": 321,
        "process_rss_bytes": 987654,
        "run_identity": {
            "scenario_id": "magmaw-shard",
            "runtime_profile": "magmaw-shard",
            "cohort_id": "cohort-a",
            "server_epoch": 8,
            "attempt_id": 9,
            "profile_generation": 2,
            "assignment_generation": 4,
            "instance_id": 55,
        },
    }


def test_process_resource_summary_matches_baseline_cpu_and_rss_semantics():
    samples = [
        {
            "process_pid": 4242,
            "monotonic_sec": 10.0,
            "process_cpu_ticks": 100,
            "process_rss_bytes": 20,
        },
        {
            "process_pid": 4242,
            "monotonic_sec": 13.0,
            "process_cpu_ticks": 160,
            "process_rss_bytes": 30,
        },
    ]
    summary = summarize_process_resource_samples(samples, tick_rate=100, sampling_errors=["one"])

    assert summary["sample_count"] == 2
    assert summary["process_pid"] == 4242
    assert summary["pid_consistent"] is True
    assert summary["cpu_ticks_delta"] == 60
    assert summary["mean_cpu_percent_one_core"] == 20.0
    assert summary["maximum_rss_bytes"] == 30
    assert summary["minimum_rss_bytes"] == 20
    assert summary["sampling_error_count"] == 1


def test_process_resource_summary_refuses_cpu_attribution_for_mixed_pids():
    samples = [
        {"process_pid": 1, "monotonic_sec": 1.0, "process_cpu_ticks": 10, "process_rss_bytes": 20},
        {"process_pid": 2, "monotonic_sec": 2.0, "process_cpu_ticks": 30, "process_rss_bytes": 40},
    ]
    summary = summarize_process_resource_samples(samples, tick_rate=100)

    assert summary["pid_consistent"] is False
    assert summary["process_pid"] is None
    assert summary["cpu_ticks_delta"] is None
    assert summary["mean_cpu_percent_one_core"] is None
    assert summary["maximum_rss_bytes"] == 40


def test_material_status_transition_forces_immediate_full_diagnosis():
    scheduler = TelemetryScheduler()
    initial = _scheduler_status(route_index=0)
    changed = _scheduler_status(route_index=1, encounter=True)
    assert material_status_signature(initial) != material_status_signature(changed)

    assert scheduler.commands_due(0.0) == [
        "botauto status", "botauto trace all 128 delta", "botauto diagnose all",
    ]
    scheduler.observe_status(initial)
    assert scheduler.commands_due(1.0) == []

    assert scheduler.observe_status(changed) is True
    assert scheduler.commands_due(1.1) == ["botauto diagnose all"]


def test_scheduler_intervals_are_below_freshness_timeout_and_channels_remain_fresh():
    scheduler = TelemetryScheduler(status_interval_sec=5, diagnose_interval_sec=15, trace_interval_sec=10)
    assert max(
        scheduler.status_interval_sec,
        scheduler.diagnose_interval_sec,
        scheduler.trace_interval_sec,
    ) < 30

    state: dict[str, dict[str, float | int]] = {}
    counts = {"status": 1, "diagnosis": 1, "trace": 1}
    assert observe_telemetry_freshness(state, counts, 0.0, 30) == []
    assert observe_telemetry_freshness(state, counts, 29.9, 30) == []
    assert observe_telemetry_freshness(state, counts, 30.1, 30) == [
        "status", "diagnosis", "trace",
    ]


def test_forced_stall_bundle_contains_diagnose_and_lossless_trace_delta():
    scheduler = TelemetryScheduler(status_interval_sec=5, diagnose_interval_sec=15, trace_interval_sec=10)
    scheduler.commands_due(0.0)
    scheduler.force_diagnosis(include_trace=True)
    assert scheduler.commands_due(2.0) == [
        "botauto trace all 128 delta", "botauto diagnose all",
    ]


def test_forced_stall_bundle_uses_full_trace_after_ring_pressure_but_keeps_gap_rejection():
    scheduler = TelemetryScheduler(
        status_interval_sec=5, diagnose_interval_sec=15, trace_interval_sec=10,
    )
    scheduler.commands_due(0.0)
    scheduler.observe_trace(
        [{"bots": [{"entries": [{}] * 16, "gap": False}]}],
        observed_at=1.0,
    )
    scheduler.force_diagnosis(include_trace=True)
    assert scheduler.commands_due(2.0) == [
        "botauto trace all 128", "botauto diagnose all",
    ]

    status = accepted_status()
    status["cohort_id"] = "raid"
    full_trace = _forced_response(status, "botauto_trace")
    for bot_row in full_trace["bots"]:
        bot_row.pop("gap")
        bot_row["entries"] = [{"sequence": 1}]
    accepted = validate_forced_evidence_bundle(
        [(_forced_response(status, "botauto_diagnose"), 10.1), (full_trace, 10.2)],
        status,
        requested_at_monotonic=10.0,
        freshness_timeout_seconds=5.0,
    )
    assert accepted["gate_passed"] is True

    missing = json.loads(json.dumps(full_trace))
    missing["bots"][0]["gap"] = True
    missing["bots"][0]["entries"] = []
    rejected = validate_forced_evidence_bundle(
        [(_forced_response(status, "botauto_diagnose"), 10.1), (missing, 10.2)],
        status,
        requested_at_monotonic=10.0,
        freshness_timeout_seconds=5.0,
    )
    assert rejected["gate_passed"] is False
    assert "trace:forced_response_trace_delta_gap" in rejected["rejections"]


def _forced_response(status: dict, action: str, *, ok: bool = True) -> dict:
    response = {
        "ok": ok,
        "action": action,
        "cohort_id": status["cohort_id"],
        "raid_runtime": status["raid_runtime"],
        "bots": [],
    }
    for member in status["raid_runtime"]["roster"]:
        if action == "botauto_diagnose":
            response["bots"].append({"identity": {"bot_guid": member["guid"]}})
        else:
            response["bots"].append({"bot_guid": member["guid"], "gap": False})
    return response


def test_final_forced_bundle_requires_both_fresh_identity_bound_ok_channels():
    status = accepted_status()
    status["cohort_id"] = "raid"
    diagnosis = _forced_response(status, "botauto_diagnose")
    trace = _forced_response(status, "botauto_trace")

    accepted = validate_forced_evidence_bundle(
        [(diagnosis, 10.1), (trace, 10.2)], status,
        requested_at_monotonic=10.0, freshness_timeout_seconds=5.0,
    )
    assert accepted["gate_passed"] is True
    assert accepted["missing_channels"] == []

    missing = validate_forced_evidence_bundle(
        [(trace, 10.2)], status,
        requested_at_monotonic=10.0, freshness_timeout_seconds=5.0,
    )
    assert missing["gate_passed"] is False
    assert missing["missing_channels"] == ["diagnosis"]

    delayed = validate_forced_evidence_bundle(
        [(diagnosis, 15.1), (trace, 15.2)], status,
        requested_at_monotonic=10.0, freshness_timeout_seconds=5.0,
    )
    assert delayed["gate_passed"] is False
    assert delayed["missing_channels"] == ["diagnosis", "trace"]
    assert "diagnosis:forced_response_stale" in delayed["rejections"]
    assert "trace:forced_response_stale" in delayed["rejections"]

    failed = validate_forced_evidence_bundle(
        [(_forced_response(status, "botauto_diagnose", ok=False), 10.1), (trace, 10.2)],
        status,
        requested_at_monotonic=10.0, freshness_timeout_seconds=5.0,
    )
    assert failed["gate_passed"] is False
    assert failed["missing_channels"] == ["diagnosis"]
    assert "diagnosis:forced_response_envelope_not_ok" in failed["rejections"]


def test_final_forced_bundle_rejects_pre_request_and_cross_identity_rows():
    status = accepted_status()
    status["cohort_id"] = "raid"
    diagnosis = _forced_response(status, "botauto_diagnose")
    trace = _forced_response(status, "botauto_trace")
    trace["cohort_id"] = "other-raid"
    result = validate_forced_evidence_bundle(
        [(diagnosis, 9.9), (trace, 10.1)], status,
        requested_at_monotonic=10.0, freshness_timeout_seconds=5.0,
    )
    assert result["gate_passed"] is False
    assert result["missing_channels"] == ["diagnosis", "trace"]
    assert "diagnosis:forced_response_before_request" in result["rejections"]
    assert "trace:forced_response_runtime_identity_unbound" in result["rejections"]


def test_final_forced_combat_log_requires_contiguous_identity_bound_chunks():
    chunks = [
        {
            "ok": True,
            "action": "botauto_combatlog_chunk",
            "cohort_id": "raid",
            "combat_log_chunk_schema_version": 1,
            "sequence": sequence,
            "chunk_count": 2,
            "encoding": "base64",
            "data": "YQ==",
        }
        for sequence in range(2)
    ]
    complete = {
        "ok": True,
        "action": "botauto_combatlog_complete",
        "cohort_id": "raid",
        "combat_log_chunk_schema_version": 1,
        "chunk_count": 2,
        "total_bytes": 2,
    }

    accepted = validate_forced_combat_log_bundle([*chunks, complete], "raid")
    assert accepted["gate_passed"] is True
    assert accepted["received_chunks"] == 2

    missing = validate_forced_combat_log_bundle([chunks[0], complete], "raid")
    assert missing["gate_passed"] is False
    assert "forced_combat_log_chunks_incomplete" in missing["rejections"]

    cross_identity = json.loads(json.dumps(chunks))
    cross_identity[1]["cohort_id"] = "other-raid"
    rejected = validate_forced_combat_log_bundle([*cross_identity, complete], "raid")
    assert rejected["gate_passed"] is False
    assert "forced_combat_log_cohort_mismatch" in rejected["rejections"]


def test_forced_evidence_admission_uses_focused_production_module():
    expected_module = "tools.raid_program.capture_forced_evidence"
    assert validate_forced_evidence_bundle.__module__ == expected_module
    assert validate_forced_combat_log_bundle.__module__ == expected_module
    assert _forbidden_assistance_entries.__module__ == expected_module


def test_material_signature_schedules_hostile_and_per_guid_recovery_edges():
    status = accepted_status()
    baseline = material_status_signature(status)
    hostile = json.loads(json.dumps(status))
    runtime = hostile["raid_runtime"]
    runtime.update(
        native_hostile_activity_active=True,
        native_hostile_reset_generation=2,
        native_hostile_activity_reason="hostile_pack_still_active",
    )
    assert material_status_signature(hostile) != baseline

    scheduler = TelemetryScheduler()
    scheduler.observe_status(status)
    assert scheduler.commands_due(0.0) == [
        "botauto status", "botauto trace all 128 delta", "botauto diagnose all",
    ]
    scheduler.observe_status(hostile)
    assert scheduler.commands_due(1.0) == ["botauto diagnose all"]

    recovery = json.loads(json.dumps(status))
    recovery["raid_runtime"]["native_recovery"]["members"] = [{
        "guid": 1001,
        "wipe_generation": 1,
        "death_sequence": 10,
        "corpse_sequence": 11,
        "release_sequence": 12,
        "runback_sequence": 13,
        "reentry_sequence": 14,
        "resurrection_sequence": 15,
    }]
    assert material_status_signature(recovery) != baseline


def test_readycheck_request_accepts_exact_trash_hostile_reset_without_boss_reset():
    status = accepted_status()
    runtime = status["raid_runtime"]
    status["validation_route"] = {"generation": 3, "node_id": "drudge-node"}
    runtime.update(
        attempt_id=2,
        assignment_generation=7,
        alive_size=10,
        encounter_in_progress=False,
        wipe_generation=1,
        boss_reset_generation=0,
        boss_reset_generation_at_wipe=0,
        native_hostile_activity_active=False,
        native_hostile_inactivity_observed=True,
        native_hostile_reset_generation=3,
        native_hostile_reset_generation_at_wipe=2,
        native_hostile_observation_attempt_id=2,
        native_hostile_observation_route_generation=3,
        native_hostile_observation_node_id="drudge-node",
        native_recovery_hold_active=True,
        native_recovery_route_generation=3,
        native_recovery_node_id="drudge-node",
    )
    runtime["native_recovery"].update(
        death_observed=True,
        corpse_observed=True,
        release_observed=True,
        resurrection_observed=True,
        runback_observed=True,
        ready_check_action_observed=False,
    )

    assert ready_for_native_readycheck(status) is True
    assert native_readycheck_request_identity(status) == (
        2, 1, 7, 3, "drudge-node",
    )


def test_readycheck_request_rejects_stale_or_active_native_hostile_reset():
    status = accepted_status()
    runtime = status["raid_runtime"]
    status["validation_route"] = {"generation": 3, "node_id": "drudge-node"}
    runtime.update(
        attempt_id=2,
        assignment_generation=1,
        alive_size=10,
        encounter_in_progress=False,
        wipe_generation=1,
        boss_reset_generation=0,
        boss_reset_generation_at_wipe=0,
        native_hostile_activity_active=False,
        native_hostile_inactivity_observed=True,
        native_hostile_reset_generation=2,
        native_hostile_reset_generation_at_wipe=2,
        native_hostile_observation_attempt_id=2,
        native_hostile_observation_route_generation=3,
        native_hostile_observation_node_id="drudge-node",
        native_recovery_hold_active=True,
        native_recovery_route_generation=3,
        native_recovery_node_id="drudge-node",
    )
    runtime["native_recovery"].update(
        death_observed=True,
        corpse_observed=True,
        release_observed=True,
        resurrection_observed=True,
        runback_observed=True,
        ready_check_action_observed=False,
    )
    assert ready_for_native_readycheck(status) is False

    runtime["native_hostile_reset_generation"] = 3
    runtime["native_hostile_activity_active"] = True
    assert ready_for_native_readycheck(status) is False

    runtime["native_hostile_activity_active"] = False
    runtime["native_hostile_observation_node_id"] = "stale-node"
    assert ready_for_native_readycheck(status) is False

    runtime["native_hostile_observation_node_id"] = "drudge-node"
    runtime["native_recovery_node_id"] = "other-node"
    assert ready_for_native_readycheck(status) is False


def test_readycheck_request_accepts_boss_reset_with_exact_recovery_scope():
    status = accepted_status()
    runtime = status["raid_runtime"]
    status["validation_route"] = {"generation": 4, "node_id": "magmaw-node"}
    runtime.update(
        attempt_id=3,
        assignment_generation=2,
        alive_size=10,
        encounter_in_progress=False,
        wipe_generation=2,
        boss_reset_generation=5,
        boss_reset_generation_at_wipe=4,
        native_hostile_activity_active=False,
        native_hostile_inactivity_observed=False,
        native_recovery_hold_active=True,
        native_recovery_route_generation=4,
        native_recovery_node_id="magmaw-node",
    )
    runtime["native_recovery"].update(
        death_observed=True,
        corpse_observed=True,
        release_observed=True,
        resurrection_observed=True,
        runback_observed=True,
        ready_check_action_observed=False,
    )

    assert ready_for_native_readycheck(status) is True


def _write_runtime_profile_assets(root: Path, route_payload: str) -> None:
    profile_dir = root / "dataset/bot_runtime_profiles"
    route_dir = root / "dataset/validation_scenarios"
    profile_dir.mkdir(parents=True, exist_ok=True)
    route_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "profiles.json").write_text(json.dumps({
        "profiles": [{
            "name": "blackwing_descent_10n",
            "validation_route": {
                "enable": True,
                "manifest_path": "dataset/validation_scenarios/validation_routes.jsonl",
                "scenario_id": "blackwing_descent_10n",
            },
        }],
    }), encoding="utf-8")
    (route_dir / "validation_routes.jsonl").write_text(route_payload, encoding="utf-8")


def _bwd_route_payload() -> str:
    route_identity = (
        (1, "regroup", "BWD entrance junction regroup", 0, "blackwing_descent_10n.start_position"),
        (2, "trash", "Magmaw Chainwielder trash", 42649, "250050"),
        (3, "trash", "Magmaw Drudge pair", 42362, "250140"),
        (4, "boss", "Magmaw", 41570, "@CGUID+8"),
        (5, "trash", "Omnotron Golem Sentries", 42800, "250049"),
        (6, "boss", "Omnotron Defense System", 42166, "script_summoned"),
        (7, "trash", "laboratory trash", 42803, "250119"),
        (8, "boss", "Maloriak", 41378, "@CGUID+69"),
        (9, "boss", "Atramedes", 41442, "native_instance_unlock"),
        (10, "boss", "Chimaeron", 43296, "@CGUID+70"),
        (11, "boss", "Nefarian", 41376, "native_instance_unlock"),
    )
    return "".join(json.dumps({
        "scenario_id": "blackwing_descent_10n",
        "step": step,
        "route_node_id": f"node-{step}",
        "kind": kind,
        "label": label,
        "source_entry": source_entry,
        "source_guid": source_guid,
    }) + "\n" for step, kind, label, source_entry, source_guid in route_identity)


def test_capture_preflight_requires_matching_hydrated_route_manifest(tmp_path: Path):
    worktree = tmp_path / "worktree"
    reference = tmp_path / "reference"
    route = _bwd_route_payload()
    _write_runtime_profile_assets(worktree, route)
    _write_runtime_profile_assets(reference, route)

    accepted = validate_runtime_profile_assets(worktree, reference, require_dvc_lineage=False)
    assert accepted["passed"] is True
    assert accepted["matching_route_rows"] == 11
    assert accepted["route_sha256"] == accepted["reference_route_sha256"]

    reordered_rows = route.splitlines()
    reordered_rows[1], reordered_rows[2] = reordered_rows[2], reordered_rows[1]
    reordered = "\n".join(reordered_rows) + "\n"
    _write_runtime_profile_assets(worktree, reordered)
    _write_runtime_profile_assets(reference, reordered)
    rejected_order = validate_runtime_profile_assets(
        worktree, reference, require_dvc_lineage=False
    )
    assert rejected_order["passed"] is False
    assert "worktree_route_steps_not_ordered_one_through_eleven" in rejected_order["reasons"]
    assert "worktree_route_identity_mismatch" in rejected_order["reasons"]

    _write_runtime_profile_assets(worktree, route)
    _write_runtime_profile_assets(reference, route)

    (worktree / "dataset/validation_scenarios/validation_routes.jsonl").unlink()
    missing = validate_runtime_profile_assets(worktree, reference, require_dvc_lineage=False)
    assert missing["passed"] is False
    assert "worktree_route_manifest_unreadable" in missing["reasons"]

    _write_runtime_profile_assets(worktree, json.dumps({
        "scenario_id": "stonecore_5n", "route_node_id": "wrong", "kind": "boss",
    }) + "\n")
    wrong = validate_runtime_profile_assets(worktree, reference, require_dvc_lineage=False)
    assert wrong["passed"] is False
    assert "worktree_route_expected_eleven_rows" in wrong["reasons"]
    assert "runtime_route_differs_from_reference" in wrong["reasons"]


def test_capture_preflight_rejects_dirty_dvc_lineage(tmp_path: Path, monkeypatch):
    worktree = tmp_path / "worktree"
    reference = tmp_path / "reference"
    route = _bwd_route_payload()
    _write_runtime_profile_assets(worktree, route)
    _write_runtime_profile_assets(reference, route)
    monkeypatch.setattr(
        "tools.raid_program.capture_environment_validation.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="validation_scenarios:\n\tchanged deps:\n"),
    )

    rejected = validate_runtime_profile_assets(worktree, reference)

    assert rejected["passed"] is False
    assert "runtime_route_dvc_lineage_dirty" in rejected["reasons"]


def test_canonical_capture_explicitly_starts_the_frozen_bwd_10n_profile():
    live_source = (
        Path(__file__).resolve().parents[1]
        / "tools/raid_program/capture_live_run.py"
    ).read_text(encoding="utf-8")
    demux_source = (
        Path(__file__).resolve().parents[1]
        / "tools/raid_program/capture_evidence_demux.py"
    ).read_text(encoding="utf-8")
    assert 'process.stdin.write(b"botauto start blackwing_descent_10n\\n")' in live_source
    assert '"botauto_profile": "profile_selection"' in demux_source


def test_canonical_capture_rejects_worldserver_autostart_before_spawn():
    source = (
        Path(__file__).resolve().parents[1]
        / "tools/raid_program/capture_setup.py"
    ).read_text(encoding="utf-8")
    assert 'trinity_config_bool(config, "BotWorld.AutoStart", False)' in source
    assert "config_autostart_enabled" in source
    assert "phase1 capture owns the single botauto start command" in source


def accepted_status() -> dict:
    frozen_roster = expected_bwd_10n_roster()
    frozen_identity = _expected_identity_by_slot()
    return {
        "ok": True,
        "action": "botauto_status",
        "bots": 10,
        "lease_count": 10,
        "raid_runtime": {
            "active": True,
            "expected_size": 10,
            "active_size": 10,
            "alive_size": 10,
            "roster_complete": True,
            "expected_difficulty": 0,
            "group_difficulty": 0,
            "map_difficulty": 0,
            "difficulty_matches": True,
            "map_id": 669,
            "instance_id": 42,
            "lockout_save_id": 42,
            "group_guid": 77,
            "leader_guid": 1001,
            "server_epoch": 88,
            "attempt_id": 1,
            "profile_generation": 1,
            "profile_content_hash": "fixture-profile-sha256",
            "assignment_generation": 1,
            "evidence_sequence": 1,
            "wipe_generation": 0,
            "boss_reset_generation": 0,
            "boss_reset_generation_at_wipe": 0,
            "recovery_generation": 0,
            "encounter_in_progress": False,
            "wipe_state": "ready",
            "recovery_state": "none",
            "strategy_id": "blackwing_descent_10n",
            "route_progress": {"generation": 4, "node_index": 3},
            "boss_states": [0] * 6,
            "ready_check_satisfied": True,
            "unique_leases": True,
            "roster": [
                {
                    "roster_slot_id": frozen_roster[index][0],
                    "lease_role_slot": frozen_roster[index][0],
                    "slot": index, "guid": 1001 + index,
                    "subgroup": index // 5, "role": "tank" if index < 2 else ("healer" if index < 5 else "dps"),
                    "class_id": frozen_roster[index][2],
                    "class_spec": frozen_roster[index][3],
                    "gear_identity": f"fixture_gear_{index}",
                    "active": True, "lease_owned": True,
                    "account_id": 1000 + index,
                    "account": frozen_identity[frozen_roster[index][0]]["account"],
                    "name": frozen_identity[frozen_roster[index][0]]["name"],
                    "talents": list(frozen_identity[frozen_roster[index][0]]["talents"]),
                    "glyphs": list(frozen_identity[frozen_roster[index][0]]["glyphs"]),
                    "gear_identity_manifest": {
                        "items": [
                            {
                                "slot": item["slot"], "guid": 500000 + index * 100 + item["slot"],
                                "entry": item["entry"], "enchant_id": item["enchant_id"],
                                "gem_item_ids": list(item["gem_item_ids"]), "reforge_id": item["reforge_id"],
                            }
                            for item in frozen_identity[frozen_roster[index][0]]["gear"]
                        ]
                    },
                }
                for index in range(10)
            ],
            "roster_composition_valid": True,
            "native_recovery": {
                "death_observed": False, "corpse_observed": False, "release_observed": False,
                "resurrection_observed": False, "runback_observed": False,
                "ready_check_action_observed": True, "evidence_complete": False,
                "ready_check_action_generation": 1, "ready_check_action_attempt_id": 1,
                "ready_check_action_wipe_generation": 0,
                "ready_check_assignment_generation": 1,
                "ready_check_action_evidence_sequence": 1,
                "recovery_wipe_generation": 0,
            },
        },
    }


def _materialize_profile_identity(status: dict, profile: str) -> None:
    runtime = status["raid_runtime"]
    expected = _expected_identity_by_slot(profile)
    for row in runtime["roster"]:
        identity = expected[row["roster_slot_id"]]
        gear_guids = {
            item["slot"]: item["guid"]
            for item in row["gear_identity_manifest"]["items"]
        }
        row.update(
            guid=identity["character_guid"],
            account_id=identity["account_id"],
            account=identity["account"],
            name=identity["name"],
            class_id=identity["class_id"],
            class_spec=identity["class_spec"],
            talents=list(identity["talents"]),
            glyphs=list(identity["glyphs"]),
        )
        row["gear_identity_manifest"]["items"] = [
            {
                "slot": item["slot"],
                "guid": gear_guids[item["slot"]],
                "entry": item["entry"],
                "enchant_id": item["enchant_id"],
                "gem_item_ids": list(item["gem_item_ids"]),
                "reforge_id": item["reforge_id"],
            }
            for item in identity["gear"]
        ]
    runtime["leader_guid"] = runtime["roster"][0]["guid"]


def checkpoint_pre_route_status() -> dict:
    profile = "blackwing_descent_10n_magmaw_diagnostic"
    status = accepted_status()
    _materialize_profile_identity(status, profile)
    runtime = status["raid_runtime"]
    runtime.update(
        admission_phase="active",
        server_provisioning_complete=True,
        bot_actions_enabled=True,
        strategy_id="pre_route_admission",
        route_progress={"generation": 1, "node_index": 0},
        alive_size=9,
        ready_check_satisfied=False,
    )
    runtime["admission_receipt"] = {
        "attempt_id": runtime["attempt_id"],
        "server_epoch": runtime["server_epoch"],
        "group_guid": runtime["group_guid"],
        "instance_id": runtime["instance_id"],
        "committed_at_ms": 12345,
        "bot_actions_enabled_at_commit": True,
        "scenario_id": profile,
        "runtime_profile": profile,
        "route_manifest_sha256": "d" * 64,
        "entrance_map_id": runtime["map_id"],
        "profile_generation": runtime["profile_generation"],
        "profile_content_hash": runtime["profile_content_hash"],
        "leader_guid": runtime["leader_guid"],
        "all_current_gear_matches_admission": True,
        "members": [{"guid": row["guid"]} for row in runtime["roster"]],
    }
    status.update(cohort_id="default", active_profile=profile)
    return status


class _CheckpointProcess:
    def __init__(self) -> None:
        self.stdin = io.BytesIO()


def _observe_checkpoint_gate(state: dict, process: _CheckpointProcess, status: dict, admission: dict) -> dict:
    command = chainwielder_checkpoint_arm_command(admission, 30008)
    assert command is not None
    return observe_chainwielder_checkpoint_arm_gate(
        state,
        status,
        process=process,
        recurrence_admission=admission,
        checkpoint_arm_command=command,
        actor_guid=30008,
        profile_name="blackwing_descent_10n_magmaw_diagnostic",
        scenario_id="blackwing_descent_10n_magmaw_diagnostic",
        expected_route_manifest_sha256="d" * 64,
    )


def test_checkpoint_arm_emits_once_at_stable_pre_route_gate_without_full_foundation_acceptance():
    status = checkpoint_pre_route_status()
    accepted, reasons = accepted_foundation_status(
        status,
        profile_name="blackwing_descent_10n_magmaw_diagnostic",
        route_partition={"node_count": 4, "terminal_index": 3},
    )
    assert accepted is False
    assert {
        "alive_size_10", "strategy_owned", "ready_check_satisfied",
        "selected_route_terminal_node",
    }.issubset(reasons)

    state: dict = {}
    process = _CheckpointProcess()
    admission = _verified_checkpoint_admission()
    _observe_checkpoint_gate(state, process, status, admission)
    assert process.stdin.getvalue() == b""
    _observe_checkpoint_gate(state, process, status, admission)
    _observe_checkpoint_gate(state, process, status, admission)

    command = chainwielder_checkpoint_arm_command(admission, 30008)
    assert process.stdin.getvalue() == (command + "\n").encode()
    assert state["command_sent"] is True
    assert state["emission_count"] == 1
    assert state["emission"]["route_generation"] == 1
    assert state["last_readiness"]["accepted"] is True


def test_checkpoint_arm_gate_rejects_material_identity_admission_and_source_tampering():
    cases = (
        "cohort", "profile", "admission_attempt", "admission_members",
        "actor", "route_generation", "seal", "source", "admission",
    )
    for case in cases:
        status = checkpoint_pre_route_status()
        admission = _verified_checkpoint_admission()
        actor_guid = 30008
        if case == "cohort":
            status["cohort_id"] = "foreign"
        elif case == "profile":
            status["active_profile"] = "blackwing_descent_10n"
        elif case == "admission_attempt":
            status["raid_runtime"]["admission_receipt"]["attempt_id"] += 1
        elif case == "admission_members":
            status["raid_runtime"]["admission_receipt"]["members"][0]["guid"] += 1
        elif case == "actor":
            actor_guid = 39999
        elif case == "route_generation":
            status["raid_runtime"]["route_progress"]["generation"] = 2
        elif case == "seal":
            admission["checkpoint_seal_sha256"] = "wrong"
        elif case == "source":
            admission["source_commit"] = "wrong"
        else:
            admission["valid"] = False
        command = (
            chainwielder_checkpoint_arm_command(_verified_checkpoint_admission(), actor_guid)
            if case in {"seal", "source", "admission"} else
            chainwielder_checkpoint_arm_command(admission, actor_guid)
        )
        state: dict = {}
        process = _CheckpointProcess()
        for _ in range(2):
            observe_chainwielder_checkpoint_arm_gate(
                state, status, process=process,
                recurrence_admission=admission,
                checkpoint_arm_command=command,
                actor_guid=actor_guid,
                profile_name="blackwing_descent_10n_magmaw_diagnostic",
                scenario_id="blackwing_descent_10n_magmaw_diagnostic",
                expected_route_manifest_sha256="d" * 64,
            )
        assert process.stdin.getvalue() == b"", case
        assert state["command_sent"] is False, case
        assert state["last_readiness"]["rejections"], case


def test_checkpoint_arm_gate_requires_two_matching_ready_identities():
    admission = _verified_checkpoint_admission()
    process = _CheckpointProcess()
    state: dict = {}
    first = checkpoint_pre_route_status()
    drifted = checkpoint_pre_route_status()
    drifted["raid_runtime"]["admission_receipt"]["committed_at_ms"] += 1

    _observe_checkpoint_gate(state, process, first, admission)
    _observe_checkpoint_gate(state, process, drifted, admission)
    assert process.stdin.getvalue() == b""
    assert state["consecutive_stable_statuses"] == 1
    _observe_checkpoint_gate(state, process, drifted, admission)
    assert state["emission_count"] == 1


def test_checkpoint_controller_pre_route_probe_closes_live_ordering_race():
    admission = _verified_checkpoint_admission()
    command = chainwielder_checkpoint_arm_command(admission, 30008)
    assert command is not None

    def run_controller(*, immediate_probe: bool) -> tuple[dict, bytes]:
        state: dict = {}
        process = _CheckpointProcess()
        for route_generation in (1, 2):
            scheduled = ["botauto status"]
            if immediate_probe:
                scheduled = chainwielder_checkpoint_monitor_commands(
                    scheduled,
                    checkpoint_arm_command=command,
                    checkpoint_arm_gate=state,
                )
            process.stdin.write(("\n".join(scheduled) + "\n").encode())
            status = checkpoint_pre_route_status()
            status["raid_runtime"]["route_progress"]["generation"] = (
                route_generation
            )
            for scheduled_command in scheduled:
                if scheduled_command == "botauto status":
                    _observe_checkpoint_gate(state, process, status, admission)
            if state.get("command_sent") is True:
                break
        return state, process.stdin.getvalue()

    fail_before, fail_before_bytes = run_controller(immediate_probe=False)
    assert fail_before["command_sent"] is False
    assert fail_before["emission_count"] == 0
    assert command.encode() not in fail_before_bytes

    pass_after, pass_after_bytes = run_controller(immediate_probe=True)
    assert pass_after["command_sent"] is True
    assert pass_after["emission_count"] == 1
    assert pass_after["emission"]["actor_guid"] == 30008
    assert pass_after["emission"]["route_generation"] == 1
    assert pass_after["pre_route_probe_batches"] == 1
    assert pass_after["pre_route_probe_command_count"] == 1
    assert pass_after_bytes.count((command + "\n").encode()) == 1


def _generic_hold_identity() -> ControllerRouteHoldLaunchIdentity:
    return ControllerRouteHoldLaunchIdentity(
        scenario_id="raid-scenario-a",
        runtime_profile="raid-profile-a",
        pool_tag="raid-pool-a",
        route_manifest_sha256="a" * 64,
        route_node_id="raid.node.a",
        actor_guid=77,
        fixture_id="fixture-a",
        seal_sha256="b" * 64,
        source_commit="c" * 40,
    )


def _generic_route_snapshot() -> dict:
    return {
        "movement_owner": "route",
        "active_path_valid": True,
        "active_path_segment_valid": True,
        "active_path_traversal_mode": "native_route",
        "active_path_target_guid": 0,
        "active_path_attempt_id": 9,
        "active_path_wipe_generation": 2,
        "active_path_route_generation": 1,
        "active_path_route_node_id": "raid.node.a",
        "active_path_destination": {"x": 1.0, "y": 2.0, "z": 3.0},
        "dodge_caster_guid": 0,
        "dodge_spell_id": 0,
        "dodge_until_ms": 0,
        "dodge_bearing_attempt": 0,
        "last_path_reject_reason": "",
    }


def _generic_checkpoint_lifecycle(*, terminal: bool) -> dict:
    return {
        "stage": "completed" if terminal else "armed",
        "terminal": terminal,
        "injection_count": 1 if terminal else 0,
        "triggered_by_active_route_path": terminal,
        "triggered_by_armed_route_hazard_retry": False,
        "rejection": {
            "owner": "hazard",
            "gate": "future_pack_destination" if terminal else "",
            "reason": (
                "route_destination_future_pack_unsafe" if terminal else ""
            ),
            "planner_receipt_id": 0,
        },
        "before_after_identity_preserved": terminal,
        "before": _generic_route_snapshot(),
        "after": _generic_route_snapshot() if terminal else {},
        "outcome": (
            "route_identity_preserved_after_receiptless_hazard_rejection"
            if terminal else "awaiting_real_route_owner"
        ),
    }


def _generic_hold(*, phase: str = "held", route_generation: int = 1) -> dict:
    terminal = phase in {"checkpoint_terminal", "released"}
    return {
        "ok": phase != "failed",
        "phase": phase,
        "cohort_id": "cohort-a",
        "server_epoch": 71,
        "attempt_id": 9,
        "scenario_id": "raid-scenario-a",
        "runtime_profile": "raid-profile-a",
        "route_manifest_sha256": "a" * 64,
        "route_generation": route_generation,
        "route_node_id": "raid.node.a",
        "actor_guid": 77,
        "fixture_id": "fixture-a",
        "seal_sha256": "b" * 64,
        "source_commit": "c" * 40,
        "acquire_count": 1,
        "arm_ack_count": 1 if phase in {"armed", "checkpoint_terminal", "released"} else 0,
        "checkpoint_stage": "disabled" if phase == "held" else "armed",
        "checkpoint_terminal": terminal,
        "checkpoint_identity_preserved": terminal,
        "checkpoint_lifecycle": _generic_checkpoint_lifecycle(
            terminal=terminal
        ),
        "release_count": 1 if phase == "released" else 0,
        "suppressed_route_action_count": 4,
        "suppressed_route_advance_count": 1,
        "acquired_at_ms": 10,
        "armed_at_ms": 20 if phase != "held" else 0,
        "terminal_at_ms": 30 if phase in {"checkpoint_terminal", "released"} else 0,
        "released_at_ms": 40 if phase == "released" else 0,
        "failure_reason": (
            "controller_route_hold_fixture_rejected" if phase == "failed" else None
        ),
    }


def _generic_hold_status(
    *, phase: str = "held", route_generation: int = 1,
    checkpoint_stage: str | None = None,
) -> dict:
    hold = _generic_hold(phase=phase)
    if checkpoint_stage is not None:
        hold["checkpoint_stage"] = checkpoint_stage
    return {
        "ok": True,
        "action": "botauto_status",
        "cohort_id": "cohort-a",
        "active_profile": "raid-profile-a",
        "raid_runtime": {
            "active": True,
            "server_epoch": 71,
            "attempt_id": 9,
            "route_progress": {"generation": route_generation},
            "controller_route_hold": hold,
        },
        "validation_route": {"generation": route_generation},
    }


def _generic_arm_ack() -> dict:
    return {
        "ok": True,
        "action": "botauto_chainwielder_checkpoint",
        "cohort_id": "cohort-a",
        "server_epoch": 71,
        "attempt_id": 9,
        "active_profile": "raid-profile-a",
        "actor_guid": 77,
        "fixture_id": "fixture-a",
        "controller_route_hold": _generic_hold(phase="armed"),
    }


def _advance_generic_hold_to_terminal(
    scheduler: ControllerRouteHoldScheduler,
) -> None:
    assert scheduler.start()[0].startswith(
        "botautochaincheckpoint start-held 77 fixture-a"
    )
    assert scheduler.observe(_generic_hold()) == ["botauto status"]
    assert scheduler.observe(_generic_hold_status()) == ["botauto status"]
    assert scheduler.observe(_generic_hold_status())[0].startswith(
        "botautochaincheckpoint arm 77"
    )
    assert scheduler.observe(_generic_arm_ack()) == []


def test_generic_controller_route_hold_scheduler_exact_production_transcript():
    scheduler = ControllerRouteHoldScheduler(_generic_hold_identity())
    _advance_generic_hold_to_terminal(scheduler)
    assert scheduler.observe(_generic_hold_status(
        phase="checkpoint_terminal", checkpoint_stage="completed",
    ))[0].startswith("botautochaincheckpoint release 77")
    assert scheduler.observe(_generic_hold(phase="released")) == ["botauto status"]
    assert scheduler.observe(_generic_hold_status(
        phase="released", route_generation=2,
    )) == []
    # V105 retained two post-release generation-2 statuses in one collection
    # batch (capture sequences 69 and 73).  The first completes the protocol;
    # the second is the same already-acknowledged progress observation.
    assert scheduler.observe(_generic_hold_status(
        phase="released", route_generation=2,
    )) == []

    receipt = scheduler.receipt()
    assert receipt["gate_passed"] is True
    assert receipt["failure_reason"] is None
    assert receipt["command_transcript"] == [
        "botautochaincheckpoint start-held 77 fixture-a " + "b" * 64 + " " + "c" * 40,
        "botauto status",
        "botauto status",
        "botautochaincheckpoint arm 77 " + "b" * 64 + " " + "c" * 40,
        "botautochaincheckpoint release 77 " + "b" * 64 + " " + "c" * 40,
        "botauto status",
    ]
    assert receipt["command_counts"] == {
        "start_held": 1, "status": 3, "arm": 1, "release": 1,
    }
    assert receipt["start_ack_count"] == 1
    assert receipt["held_status_count"] == 2
    assert receipt["arm_ack_count"] == 1
    assert receipt["checkpoint_terminal_count"] == 1
    assert receipt["checkpoint_terminal_stage"] == "completed"
    assert receipt["checkpoint_terminal_lifecycle"] == (
        _generic_checkpoint_lifecycle(terminal=True)
    )
    assert receipt["release_ack_count"] == 1


def test_generic_controller_route_hold_rejects_inexact_terminal_lifecycle():
    direct_mutations = (
        ("injection_count", 2),
        ("triggered_by_active_route_path", False),
        ("triggered_by_armed_route_hazard_retry", True),
        ("outcome", "hazard_exit_completed"),
    )
    for field, value in direct_mutations:
        scheduler = ControllerRouteHoldScheduler(_generic_hold_identity())
        _advance_generic_hold_to_terminal(scheduler)
        row = _generic_hold_status(
            phase="checkpoint_terminal", checkpoint_stage="completed",
        )
        row["raid_runtime"]["controller_route_hold"][
            "checkpoint_lifecycle"
        ][field] = value
        scheduler.observe(row)
        assert scheduler.failure_reason == (
            "controller_route_hold_checkpoint_lifecycle_invalid"
        )

    for field, value in (
        ("owner", "route"),
        ("gate", "movement_launch"),
        ("reason", "different_reason"),
        ("planner_receipt_id", 1),
    ):
        scheduler = ControllerRouteHoldScheduler(_generic_hold_identity())
        _advance_generic_hold_to_terminal(scheduler)
        row = _generic_hold_status(
            phase="checkpoint_terminal", checkpoint_stage="completed",
        )
        row["raid_runtime"]["controller_route_hold"][
            "checkpoint_lifecycle"
        ]["rejection"][field] = value
        scheduler.observe(row)
        assert scheduler.failure_reason == (
            "controller_route_hold_checkpoint_rejection_invalid"
        )

    changed = ControllerRouteHoldScheduler(_generic_hold_identity())
    _advance_generic_hold_to_terminal(changed)
    changed_row = _generic_hold_status(
        phase="checkpoint_terminal", checkpoint_stage="completed",
    )
    changed_row["raid_runtime"]["controller_route_hold"][
        "checkpoint_lifecycle"
    ]["after"]["active_path_destination"]["x"] = 99.0
    changed.observe(changed_row)
    assert changed.failure_reason == (
        "controller_route_hold_checkpoint_route_identity_changed"
    )

    invalid = ControllerRouteHoldScheduler(_generic_hold_identity())
    _advance_generic_hold_to_terminal(invalid)
    invalid_row = _generic_hold_status(
        phase="checkpoint_terminal", checkpoint_stage="completed",
    )
    lifecycle = invalid_row["raid_runtime"]["controller_route_hold"][
        "checkpoint_lifecycle"
    ]
    lifecycle["before"]["movement_owner"] = "hazard"
    lifecycle["after"]["movement_owner"] = "hazard"
    invalid.observe(invalid_row)
    assert invalid.failure_reason == (
        "controller_route_hold_checkpoint_route_identity_invalid"
    )


def test_generic_controller_route_hold_scheduler_extraction_is_bounded():
    module_path = Path("tools/raid_program/controller_route_hold.py")
    module_source = module_path.read_text(encoding="utf-8")
    bounded_paths = (
        module_path,
        Path("tools/raid_program/capture_phase1_raid_foundation.py"),
        Path("tools/raid_program/capture_setup.py"),
        Path("tools/raid_program/capture_live_run.py"),
        Path("tools/raid_program/capture_finalization.py"),
    )
    assert all(
        len(path.read_text(encoding="utf-8").splitlines()) < 1000
        for path in bounded_paths
    )
    assert ControllerRouteHoldScheduler.__module__ == (
        "tools.raid_program.controller_route_hold"
    )

    tree = ast.parse(module_source)
    branch_nodes = (
        ast.If, ast.For, ast.While, ast.Try, ast.BoolOp, ast.IfExp,
        ast.Match, ast.comprehension,
    )
    metrics = {
        node.name: sum(
            isinstance(child, branch_nodes) for child in ast.walk(node)
        )
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert len(metrics) == 27
    assert sum(metrics.values()) == 126
    assert max(metrics.values()) == 22
    assert metrics["_observe_status"] == 22
    assert metrics["_status_context"] == 8
    assert metrics["validate"] == 9
    assert metrics["from_status"] == 3
    assert metrics["_checkpoint_lifecycle_rejections"] == 8


def test_generic_controller_route_hold_scheduler_rejects_old_poll_race():
    scheduler = ControllerRouteHoldScheduler(_generic_hold_identity())
    scheduler.start()
    scheduler.observe(_generic_hold())
    scheduler.observe(_generic_hold_status(route_generation=1))
    scheduler.observe(_generic_hold_status(route_generation=2))
    assert scheduler.failed is True
    assert scheduler.failure_reason == (
        "controller_route_hold_route_advanced_before_release"
    )
    assert scheduler.command_counts["arm"] == 0
    assert scheduler.command_counts["release"] == 0

    armed = ControllerRouteHoldScheduler(_generic_hold_identity())
    _advance_generic_hold_to_terminal(armed)
    armed.observe(_generic_hold_status(
        phase="armed", route_generation=2,
    ))
    assert armed.failure_reason == (
        "controller_route_hold_route_advanced_before_release"
    )
    assert armed.command_counts["release"] == 0


def test_generic_controller_route_hold_scheduler_negative_protocol_edges():
    def fresh() -> ControllerRouteHoldScheduler:
        return ControllerRouteHoldScheduler(_generic_hold_identity())

    rejected_start = fresh()
    rejected_start.start()
    rejected_start.observe(_generic_hold(phase="failed"))
    assert rejected_start.failure_reason == "controller_route_hold_fixture_rejected"

    unstable = fresh()
    unstable.start()
    unstable.observe(_generic_hold())
    unstable.observe(_generic_hold_status())
    drifted = _generic_hold_status()
    drifted["raid_runtime"]["controller_route_hold"]["route_node_id"] = "raid.node.b"
    unstable.observe(drifted)
    assert unstable.failure_reason == "controller_route_hold_route_node_id_mismatch"

    missing_arm = fresh()
    missing_arm.start()
    missing_arm.observe(_generic_hold())
    missing_arm.observe(_generic_hold_status())
    missing_arm.observe(_generic_hold_status())
    missing_arm.finish()
    assert missing_arm.failure_reason == "controller_route_hold_arm_ack_missing"

    duplicate_arm = fresh()
    _advance_generic_hold_to_terminal(duplicate_arm)
    duplicate_arm.observe(_generic_arm_ack())
    assert duplicate_arm.failure_reason == (
        "controller_route_hold_duplicate_or_stale_arm_ack"
    )

    absent_lifecycle = fresh()
    _advance_generic_hold_to_terminal(absent_lifecycle)
    absent_lifecycle.finish()
    assert absent_lifecycle.failure_reason == (
        "controller_route_hold_checkpoint_lifecycle_missing"
    )

    rejected_lifecycle = fresh()
    _advance_generic_hold_to_terminal(rejected_lifecycle)
    rejected_lifecycle.observe(_generic_hold_status(phase="failed"))
    assert rejected_lifecycle.failed is True

    early_release = fresh()
    _advance_generic_hold_to_terminal(early_release)
    early_release.observe(_generic_hold_status(phase="released"))
    assert early_release.failure_reason == (
        "controller_route_hold_checkpoint_lifecycle_invalid"
    )

    missing_release = fresh()
    _advance_generic_hold_to_terminal(missing_release)
    missing_release.observe(_generic_hold_status(
        phase="checkpoint_terminal", checkpoint_stage="completed",
    ))
    missing_release.finish()
    assert missing_release.failure_reason == "controller_route_hold_release_ack_missing"

    duplicate_release = fresh()
    _advance_generic_hold_to_terminal(duplicate_release)
    duplicate_release.observe(_generic_hold_status(
        phase="checkpoint_terminal", checkpoint_stage="completed",
    ))
    duplicate_release.observe(_generic_hold(phase="released"))
    duplicate_release.observe(_generic_hold(phase="released"))
    assert duplicate_release.failure_reason == (
        "controller_route_hold_duplicate_release_ack"
    )

    no_advance = fresh()
    _advance_generic_hold_to_terminal(no_advance)
    no_advance.observe(_generic_hold_status(
        phase="checkpoint_terminal", checkpoint_stage="completed",
    ))
    no_advance.observe(_generic_hold(phase="released"))
    no_advance.observe(_generic_hold_status(
        phase="released", route_generation=1,
    ))
    no_advance.finish()
    assert no_advance.failure_reason == (
        "controller_route_hold_post_release_advance_missing"
    )


def accepted_drudge_status() -> dict:
    status = accepted_status()
    runtime = status["raid_runtime"]
    roster_guids = [row["guid"] for row in runtime["roster"]]
    tank_guids = [row["guid"] for row in runtime["roster"] if row["role"] == "tank"]
    offensive_guids = [row["guid"] for row in runtime["roster"] if row["role"] in {"tank", "dps"}]
    lane_a_slots = {1, 3, 4, 6, 7}
    lane_b_slots = {2, 5, 8, 9, 10}
    config = json.loads((
        Path(__file__).resolve().parents[1]
        / "experiments/configs/validation_scenarios_cata_001.json"
    ).read_text(encoding="utf-8"))
    scenario = next(row for row in config["scenarios"] if row["id"] == "blackwing_descent_10n")
    drudges = next(row for row in scenario["route"] if row.get("mechanic_profile") == "trash_two_tank_charge_lanes")
    anchors = {
        row["roster_slot"]: (row["x"], row["y"])
        for row in drudges["split_recovery_member_anchors"]
    }
    anchors.update({
        row["roster_slot"]: (row["x"], row["y"])
        for row in drudges["split_tank_recovery_anchors"]
    })
    home0 = (-298.833, -50.349)
    home1 = (-307.913, -49.5694)
    midpoint = ((home0[0] + home1[0]) * 0.5, (home0[1] + home1[1]) * 0.5)
    axis_length = hypot(home1[0] - home0[0], home1[1] - home0[1])
    axis = ((home1[0] - home0[0]) / axis_length, (home1[1] - home0[1]) / axis_length)
    projection = lambda x, y: (x - midpoint[0]) * axis[0] + (y - midpoint[1]) * axis[1]
    tank0 = anchors[1]
    tank1 = anchors[2]
    tank_pair_distance = hypot(tank1[0] - tank0[0], tank1[1] - tank0[1])
    tank_pair_axis = (
        (tank1[0] - tank0[0]) / tank_pair_distance,
        (tank1[1] - tank0[1]) / tank_pair_distance,
    )
    melee_stop = drudges["split_native_melee_stop_yards"]
    source0 = (
        tank0[0] + tank_pair_axis[0] * melee_stop,
        tank0[1] + tank_pair_axis[1] * melee_stop,
    )
    source1 = (
        tank1[0] - tank_pair_axis[0] * melee_stop,
        tank1[1] - tank_pair_axis[1] * melee_stop,
    )
    member_geometry = []
    for row in runtime["roster"]:
        slot = row["slot"] + 1
        lane_a = slot in lane_a_slots
        x, y = anchors[slot]
        if row["role"] == "tank":
            member_geometry.append({
                "guid": row["guid"], "roster_slot": slot, "x": x, "y": y,
                "projection": projection(x, y), "anchor_x": 0.0, "anchor_y": 0.0,
                "group_anchor_base_x": 0.0, "group_anchor_base_y": 0.0,
                "anchor_distance": 0.0, "nearest_same_lane_distance": 0.0,
                "anchor_candidate_index": 0, "lane_side_valid": True,
                "anchor_selected": False, "anchor_path_valid": False,
                "same_lane_spacing_valid": False,
            })
            continue
        same_lane_distance = min(
            hypot(x - anchors[other][0], y - anchors[other][1])
            for other in (lane_a_slots if lane_a else lane_b_slots)
            if other != slot and other not in {1, 2}
        )
        member_geometry.append({
            "guid": row["guid"], "roster_slot": slot, "x": x, "y": y,
            "projection": projection(x, y), "anchor_x": x, "anchor_y": y,
            "group_anchor_base_x": x, "group_anchor_base_y": y,
            "anchor_distance": 0.0, "nearest_same_lane_distance": same_lane_distance,
            "anchor_candidate_index": 0, "lane_side_valid": True,
            "anchor_selected": True, "anchor_path_valid": True,
            "same_lane_spacing_valid": True,
        })
    geometry = {
        "entrance_pull_established": True,
        "home0_x": home0[0], "home0_y": home0[1], "home1_x": home1[0], "home1_y": home1[1],
        "midpoint_x": midpoint[0], "midpoint_y": midpoint[1], "axis_x": axis[0], "axis_y": axis[1],
        "lane_separation": 17.0, "minimum_distance": 15.0,
        "navigation_margin": 2.0,
        "source0_x": source0[0], "source0_y": source0[1], "source0_projection": projection(*source0),
        "source0_health_pct": 100.0,
        "source0_lane_side_valid": True, "source1_x": source1[0], "source1_y": source1[1],
        "source1_projection": projection(*source1), "source1_health_pct": 100.0, "source1_lane_side_valid": True,
        "source0_victim_guid": tank_guids[0], "source1_victim_guid": tank_guids[1],
        "source0_alive": True, "source1_alive": True,
        "source_separation": hypot(source1[0] - source0[0], source1[1] - source0[1]), "minimum_source_separation": 15.0,
        "lane_tank_x": tank0[0], "lane_tank_y": tank0[1], "lane_tank_guid": tank_guids[0],
        "lane_tank_slot": 1, "lane_tank_projection": projection(*tank0),
        "lane_tank_source_distance": hypot(tank0[0] - source0[0], tank0[1] - source0[1]),
        "other_tank_x": tank1[0], "other_tank_y": tank1[1], "other_tank_guid": tank_guids[1],
        "other_tank_slot": 2, "other_tank_projection": projection(*tank1),
        "other_tank_source_distance": hypot(tank1[0] - source1[0], tank1[1] - source1[1]),
        "minimum_member_spacing": 3.0, "arrival_tolerance": 2.0,
        "tank_arrival_tolerance": 1.0,
        "tank0_x": tank0[0], "tank0_y": tank0[1], "tank0_guid": tank_guids[0],
        "tank0_slot": 1, "tank0_projection": projection(*tank0),
        "tank0_source_distance": hypot(tank0[0] - source0[0], tank0[1] - source0[1]),
        "tank1_x": tank1[0], "tank1_y": tank1[1], "tank1_guid": tank_guids[1],
        "tank1_slot": 2, "tank1_projection": projection(*tank1),
        "tank1_source_distance": hypot(tank1[0] - source1[0], tank1[1] - source1[1]),
        "members": member_geometry,
    }
    observations = []
    sequence = 0
    # The native first-Rush snapshots below include the complete (bounded)
    # threat list.  The seeded opposite-lane DPS is the farthest eligible
    # candidate for each source. Tanks and same-lane players remain native
    # selector candidates even though they are not tactic-eligible.
    for source, target in ((250140, roster_guids[7]), (250141, roster_guids[5])):
        for interval in (0, 20000):
            sequence += 1
            observations.append({
                "sequence": sequence,
                "attempt_id": runtime["attempt_id"],
                "wipe_generation": 0,
                "route_generation": 3,
                "observed_at_ms": sequence * 20000,
                "observed_interval_ms": interval,
                "source_guid": 5000 + source,
                "source_spawn_id": source,
                "target_guid": target,
                "target_raw_guid": target,
                "selected_distance": 40.0,
                "source_combat_reach": 1.5,
                "target_combat_reach": 1.5,
                "same_map": True,
                "same_phase": True,
                "range_valid": True,
                "interval_valid": interval == 20000,
                "landed": True,
                "reseparated_roster_guids": roster_guids,
                "geometry": geometry,
            })
    for observation in observations:
        if observation["sequence"] not in (1, 3):
            continue
        source = observation["source_spawn_id"]
        source_lane = 0 if source == 250140 else 1
        farthest_guid = roster_guids[7] if source == 250140 else roster_guids[5]
        distances = {
            slot: (40.0 if guid == farthest_guid else 35.0 - abs(slot - 6) * 0.5)
            for slot, guid in ((row["slot"] + 1, row["guid"]) for row in runtime["roster"])
        }
        candidate_rows = []
        for row in runtime["roster"]:
            slot = row["slot"] + 1
            lane = 0 if slot in lane_a_slots else 1
            role = row["role"]
            cross_lane = lane != source_lane
            native_selector_eligible = True
            tactic_cross_lane_eligible = cross_lane and role != "tank"
            candidate_rows.append({
                "guid": row["guid"],
                "raw_guid": row["guid"],
                "slot": slot,
                "lane": lane,
                "threat": float(1000 + slot),
                "distance": distances[slot],
                "source_combat_reach": 1.5,
                "candidate_combat_reach": 1.5,
                "is_player": True,
                "alive": True,
                "same_map": True,
                "same_phase": True,
                "available": True,
                "line_of_sight": True,
                "in_range": True,
                "native_combat_range": True,
                "cross_lane": cross_lane,
                "native_selector_eligible": native_selector_eligible,
                "tactic_cross_lane_eligible": tactic_cross_lane_eligible,
                "role": role,
            })
        observation["native_threat_candidates"] = candidate_rows
        observation["native_threat_candidates_count"] = len(candidate_rows)
        observation["native_threat_candidates_complete"] = True
        observation["native_threat_candidates_truncated"] = False
    runtime["drudge_charge"] = {
        "generation": 4,
        "landed_generation": 4,
        "evidence_attempt_id": runtime["attempt_id"],
        "evidence_wipe_generation": 0,
        "evidence_route_generation": 3,
        "prepared_count": 4,
        "delivered_count": 4,
        "queue_overflow": False,
        "sources": [
            {"spawn_id": 250140, "delivered_count": 2, "valid_interval_count": 1},
            {"spawn_id": 250141, "delivered_count": 2, "valid_interval_count": 1},
        ],
        "reseparated_roster_guids": roster_guids,
        "ownership_roster_guids": tank_guids,
        "taunt_roster_guids": tank_guids,
        "health_sync_roster_guids": tank_guids,
        "health_sync_evaluated_roster_guids": tank_guids,
        "health_sync_hold_source_spawn_id": 250140,
        "health_sync_hold_tank_guid": tank_guids[0],
        "health_sync_hold_lower_pct": 40.0,
        "health_sync_hold_peer_pct": 50.0,
        "health_sync_hold_lower_alive": True,
        "health_sync_hold_peer_alive": True,
        "death_attempt_id": runtime["attempt_id"],
        "death_wipe_generation": 0,
        "death_route_generation": 3,
        "death_source_spawn_id": 250140,
        "death_source_guid": 255140,
        "survivor_source_spawn_id": 250141,
        "survivor_source_guid": 255141,
        "death_evidence_sequence": 5,
        "rage_wait_evidence_sequence": 6,
        "rage_aura_evidence_sequence": 7,
        "health_sync_evidence_attempt_id": runtime["attempt_id"],
        "health_sync_evidence_wipe_generation": 0,
        "health_sync_evidence_route_generation": 3,
        "profile_action_roster_guids": offensive_guids,
        "observations": observations,
    }
    runtime["drudge_threat_seed"] = {
        "attempt_id": runtime["attempt_id"],
        "wipe_generation": 0,
        "route_generation": 3,
        "closed": True,
        "complete": True,
        "failure": False,
        "roster_guids": [roster_guids[5], roster_guids[7]],
        "observations": [
            {
                "sequence": 8,
                "attempt_id": runtime["attempt_id"],
                "wipe_generation": 0,
                "route_generation": 3,
                "observed_at_ms": 5000,
                "member_guid": roster_guids[7],
                "member_slot": 8,
                "member_lane": 1,
                "source_spawn_id": 250140,
                "source_guid": 255140,
                "source_lane": 0,
                "spell_id": 100001,
                "selected_distance": 40.0,
                "min_range": 5.0,
                "max_range": 80.0,
                "position_safe": True,
                "line_of_sight": True,
                "in_range": True,
                "profile_action_valid": True,
                "action_succeeded": True,
                "selected_offense_unsuppressed": True,
                "other_offense_suppressed": True,
                "action_debug_name": "trained_single_target",
                "action_result": "ok",
            },
            {
                "sequence": 9,
                "attempt_id": runtime["attempt_id"],
                "wipe_generation": 0,
                "route_generation": 3,
                "observed_at_ms": 10000,
                "member_guid": roster_guids[5],
                "member_slot": 6,
                "member_lane": 0,
                "source_spawn_id": 250141,
                "source_guid": 255141,
                "source_lane": 1,
                "spell_id": 100002,
                "selected_distance": 40.0,
                "min_range": 5.0,
                "max_range": 80.0,
                "position_safe": True,
                "line_of_sight": True,
                "in_range": True,
                "profile_action_valid": True,
                "action_succeeded": True,
                "selected_offense_unsuppressed": True,
                "other_offense_suppressed": True,
                "action_debug_name": "trained_single_target",
                "action_result": "ok",
            },
        ],
    }
    return status


def test_drudge_contract_reconstructs_delivery_interval_and_exact_roster_tactics():
    accepted, reasons = accepted_drudge_contract([accepted_drudge_status()])
    assert accepted is True
    assert reasons == []


def test_drudge_contract_and_geometry_use_focused_production_modules():
    assert accepted_drudge_contract.__module__ == "tools.raid_program.capture_drudge_contract"
    assert _frozen_drudge_member_anchors.__module__ == "tools.raid_program.capture_drudge_geometry"
    assert _validate_drudge_observation_geometry.__module__ == "tools.raid_program.capture_drudge_geometry"


def test_drudge_geometry_is_loaded_from_explicit_sealed_route_manifest(tmp_path, monkeypatch):
    sealed = (
        Path(__file__).resolve().parents[1]
        / "dataset/validation_scenarios/validation_routes.jsonl"
    )
    # A mutable controller checkout with no route assets cannot influence the
    # explicit generated manifest bound by the capture worktree.
    monkeypatch.setattr(
        "tools.raid_program.capture_drudge_geometry.ROOT", tmp_path,
    )
    anchors = _frozen_drudge_member_anchors(sealed)
    assert set(anchors) == set(range(1, 11))
    assert anchors[1] == (-330.0, -88.0, 214.0)
    assert anchors[2] == (-348.0, -120.0, 214.0)
    assert _frozen_drudge_member_anchors() == {}


def test_drudge_contract_does_not_skip_an_earlier_unlanded_observation():
    status = accepted_drudge_status()
    observations = status["raid_runtime"]["drudge_charge"]["observations"]
    observations[0]["landed"] = False
    accepted, reasons = accepted_drudge_contract([status])
    assert accepted is False
    assert "drudge_delivered_count_mismatch" in reasons
    observations[0]["landed"] = True
    accepted, reasons = accepted_drudge_contract([status])
    assert accepted is True
    assert reasons == []


def test_drudge_contract_rejects_prepared_only_stale_and_incomplete_tactics():
    prepared_only = accepted_drudge_status()
    prepared_only["raid_runtime"]["drudge_charge"]["observations"][0]["landed"] = False
    accepted, reasons = accepted_drudge_contract([prepared_only])
    assert accepted is False
    assert "drudge_delivered_count_mismatch" in reasons

    stale = accepted_drudge_status()
    stale["raid_runtime"]["drudge_charge"]["observations"][0]["attempt_id"] = 99
    accepted, reasons = accepted_drudge_contract([stale])
    assert accepted is False
    assert "drudge_observation_scope_mismatch" in reasons

    wrong_source_guid = accepted_drudge_status()
    wrong_source_guid["raid_runtime"]["drudge_charge"]["observations"][0]["source_guid"] = 0
    accepted, reasons = accepted_drudge_contract([wrong_source_guid])
    assert accepted is False
    assert "drudge_observation_source_guid_invalid" in reasons

    incomplete = accepted_drudge_status()
    incomplete["raid_runtime"]["drudge_charge"]["health_sync_evaluated_roster_guids"] = []
    accepted, reasons = accepted_drudge_contract([incomplete])
    assert accepted is False
    assert "drudge_exact_tank_health_sync_evaluation_missing" in reasons

    missing_ownership = accepted_drudge_status()
    missing_ownership["raid_runtime"]["drudge_charge"]["ownership_roster_guids"] = []
    accepted, reasons = accepted_drudge_contract([missing_ownership])
    assert accepted is False
    assert "drudge_exact_tank_ownership_missing" in reasons

    no_redundant_taunt = accepted_drudge_status()
    no_redundant_taunt["raid_runtime"]["drudge_charge"]["taunt_roster_guids"] = []
    accepted, reasons = accepted_drudge_contract([no_redundant_taunt])
    assert accepted is True
    assert reasons == []

    foreign_taunt = accepted_drudge_status()
    foreign_taunt["raid_runtime"]["drudge_charge"]["taunt_roster_guids"] = [
        foreign_taunt["raid_runtime"]["roster"][2]["guid"]
    ]
    accepted, reasons = accepted_drudge_contract([foreign_taunt])
    assert accepted is False
    assert "drudge_taunt_evidence_identity_mismatch" in reasons

    partial_sync = accepted_drudge_status()
    partial_sync["raid_runtime"]["drudge_charge"]["health_sync_roster_guids"] = [
        partial_sync["raid_runtime"]["roster"][0]["guid"]
    ]
    accepted, reasons = accepted_drudge_contract([partial_sync])
    assert accepted is True
    assert reasons == []

    foreign_sync = accepted_drudge_status()
    foreign_sync["raid_runtime"]["drudge_charge"]["health_sync_roster_guids"] = [
        foreign_sync["raid_runtime"]["roster"][2]["guid"]
    ]
    accepted, reasons = accepted_drudge_contract([foreign_sync])
    assert accepted is False
    assert "drudge_tank_health_sync_hold_identity_mismatch" in reasons

    out_of_scope_sync = accepted_drudge_status()
    evidence = out_of_scope_sync["raid_runtime"]["drudge_charge"]
    evidence["health_sync_evidence_attempt_id"] += 1
    accepted, reasons = accepted_drudge_contract([out_of_scope_sync])
    assert accepted is False
    assert "drudge_health_sync_scope_attempt_mismatch" in reasons

    tank_target = accepted_drudge_status()
    tank_target["raid_runtime"]["drudge_charge"]["observations"][0]["target_guid"] = 1001
    accepted, reasons = accepted_drudge_contract([tank_target])
    assert accepted is False
    assert "drudge_native_rush_target_tank" in reasons

    same_lane = accepted_drudge_status()
    # The core farthest-player selector may legitimately choose a same-lane
    # non-tank. Entrance pulling observes that result instead of scripting it.
    for observation in same_lane["raid_runtime"]["drudge_charge"]["observations"]:
        if observation["source_spawn_id"] != 250140:
            continue
        observation["target_guid"] = 1006
        observation["target_raw_guid"] = 1006
        observation["selected_distance"] = 45.0
        for candidate in observation.get("native_threat_candidates", []):
            if candidate["guid"] == 1006:
                candidate["distance"] = 45.0
    accepted, reasons = accepted_drudge_contract([same_lane])
    assert accepted is True
    assert reasons == []


def test_drudge_geometry_rejects_crossed_sources_and_unsafe_member_spacing():
    crossed = accepted_drudge_status()
    geometry = crossed["raid_runtime"]["drudge_charge"]["observations"][0]["geometry"]
    geometry["source0_x"] = geometry["source1_x"]
    geometry["source0_y"] = geometry["source1_y"]
    accepted, reasons = accepted_drudge_contract([crossed])
    assert accepted is False
    assert "drudge_geometry_source_separation_unsafe" in reasons

    too_close = accepted_drudge_status()
    geometry = too_close["raid_runtime"]["drudge_charge"]["observations"][0]["geometry"]
    member = next(row for row in geometry["members"] if row["roster_slot"] == 3)
    member["x"] = geometry["source0_x"]
    member["y"] = geometry["source0_y"]
    accepted, reasons = accepted_drudge_contract([too_close])
    assert accepted is False
    assert "drudge_geometry_member_source_distance_unsafe" in reasons


def test_drudge_entrance_geometry_requires_the_native_ownership_transition():
    status = accepted_drudge_status()
    observations = status["raid_runtime"]["drudge_charge"]["observations"]
    for observation in observations:
        observation["geometry"]["entrance_pull_established"] = False
    accepted, reasons = accepted_drudge_contract([status])
    assert accepted is False
    assert "drudge_geometry_member_lane_side_mismatch" in reasons


def test_drudge_geometry_rejects_forged_native_source_victim():
    status = accepted_drudge_status()
    geometry = status["raid_runtime"]["drudge_charge"]["observations"][0]["geometry"]
    geometry["source0_victim_guid"] = geometry["source1_victim_guid"]
    accepted, reasons = accepted_drudge_contract([status])
    assert accepted is False
    assert "drudge_geometry_source0_victim_invalid" in reasons


def test_drudge_geometry_rejects_unverified_path_fallback():
    status = accepted_drudge_status()
    geometry = status["raid_runtime"]["drudge_charge"]["observations"][0]["geometry"]
    member = next(row for row in geometry["members"] if row["roster_slot"] == 3)
    member["anchor_path_valid"] = False
    accepted, reasons = accepted_drudge_contract([status])
    assert accepted is False
    assert "drudge_geometry_member_anchor_path_unverified" in reasons


def test_drudge_threat_seed_is_diagnostic_for_entrance_pull():
    same_lane = accepted_drudge_status()
    same_lane["raid_runtime"]["drudge_threat_seed"]["observations"][0]["member_lane"] = 0
    accepted, reasons = accepted_drudge_contract([same_lane])
    assert accepted is True
    assert reasons == []

    unsuppressed = accepted_drudge_status()
    unsuppressed["raid_runtime"]["drudge_threat_seed"]["observations"][1][
        "other_offense_suppressed"
    ] = False
    accepted, reasons = accepted_drudge_contract([unsuppressed])
    assert accepted is True
    assert reasons == []

    late = accepted_drudge_status()
    late["raid_runtime"]["drudge_threat_seed"]["observations"][0]["observed_at_ms"] = 20000
    accepted, reasons = accepted_drudge_contract([late])
    assert accepted is True
    assert reasons == []


def test_drudge_native_threat_evidence_fails_closed_when_candidate_list_is_missing_or_truncated():
    missing = accepted_drudge_status()
    del missing["raid_runtime"]["drudge_charge"]["observations"][0]["native_threat_candidates"]
    accepted, reasons = accepted_drudge_contract([missing])
    assert accepted is False
    assert "drudge_native_threat_candidates_missing" in reasons

    truncated = accepted_drudge_status()
    first = truncated["raid_runtime"]["drudge_charge"]["observations"][0]
    first["native_threat_candidates_count"] = 33
    first["native_threat_candidates_complete"] = False
    first["native_threat_candidates_truncated"] = True
    accepted, reasons = accepted_drudge_contract([truncated])
    assert accepted is False
    assert "drudge_native_threat_candidates_metadata_invalid" in reasons
    assert "drudge_native_threat_candidates_truncated" in reasons


def test_drudge_native_threat_evidence_rejects_forged_eligibility_farthest_and_seed_linkage():
    forged_eligibility = accepted_drudge_status()
    first = forged_eligibility["raid_runtime"]["drudge_charge"]["observations"][0]
    first["native_threat_candidates"][0]["tactic_cross_lane_eligible"] = True
    accepted, reasons = accepted_drudge_contract([forged_eligibility])
    assert accepted is False
    assert "drudge_native_threat_candidate_eligibility_mismatch" in reasons

    same_lane_farthest = accepted_drudge_status()
    first = same_lane_farthest["raid_runtime"]["drudge_charge"]["observations"][0]
    first["native_threat_candidates"][2]["distance"] = 75.0
    accepted, reasons = accepted_drudge_contract([same_lane_farthest])
    assert accepted is False
    assert "drudge_native_threat_selected_target_not_farthest" in reasons

    combat_reach_farthest = accepted_drudge_status()
    first = combat_reach_farthest["raid_runtime"]["drudge_charge"]["observations"][0]
    first["native_threat_candidates"][2]["distance"] = 81.0
    first["native_threat_candidates"][2]["in_range"] = False
    accepted, reasons = accepted_drudge_contract([combat_reach_farthest])
    assert accepted is False
    assert "drudge_native_threat_selected_target_not_farthest" in reasons

    non_player_reference = accepted_drudge_status()
    for observation in non_player_reference["raid_runtime"]["drudge_charge"]["observations"]:
        if observation["observed_interval_ms"] != 0:
            continue
        observation["native_threat_candidates"].append({
            "guid": non_player_reference["raid_runtime"]["roster"][0]["guid"],
            "raw_guid": (4 << 60) + 900000 + observation["source_spawn_id"],
            "slot": 0,
            "lane": 0,
            "threat": 1.0,
            "distance": 79.0,
            "source_combat_reach": 1.5,
            "candidate_combat_reach": 1.5,
            "is_player": False,
            "alive": True,
            "same_map": True,
            "same_phase": True,
            "available": True,
            "line_of_sight": True,
            "in_range": True,
            "native_combat_range": True,
            "cross_lane": False,
            "native_selector_eligible": False,
            "tactic_cross_lane_eligible": False,
            "role": "unregistered",
        })
        observation["native_threat_candidates_count"] += 1
    accepted, reasons = accepted_drudge_contract([non_player_reference])
    assert accepted is True
    assert reasons == []


def test_drudge_native_threat_ignores_ordinary_pre_rush_snapshot_until_complete():
    early = accepted_drudge_status()
    early["raid_runtime"]["drudge_charge"]["observations"] = []
    early["raid_runtime"]["drudge_charge"]["prepared_count"] = 0
    early["raid_runtime"]["drudge_charge"]["delivered_count"] = 0
    accepted, reasons = accepted_drudge_contract([early, accepted_drudge_status()])
    assert accepted is True
    assert reasons == []

    started = accepted_drudge_status()
    started["raid_runtime"]["drudge_charge"]["observations"][0]["landed"] = False
    landed = accepted_drudge_status()
    accepted, reasons = accepted_drudge_contract([started, landed])
    assert accepted is True
    assert "drudge_native_threat_source_250140_first_rush_not_landed" not in reasons

    regressed = accepted_drudge_status()
    regressed["raid_runtime"]["drudge_charge"]["observations"][0]["landed"] = False
    accepted, reasons = accepted_drudge_contract([landed, regressed])
    assert accepted is False
    assert "drudge_native_threat_landing_regressed" in reasons

    changed_target = accepted_drudge_status()
    changed_target["raid_runtime"]["drudge_charge"]["observations"][0]["landed"] = False
    changed_target_landed = accepted_drudge_status()
    changed = changed_target_landed["raid_runtime"]["drudge_charge"]["observations"][0]
    changed["target_guid"] = changed_target_landed["raid_runtime"]["roster"][4]["guid"]
    changed["target_raw_guid"] = changed["target_guid"]
    accepted, reasons = accepted_drudge_contract([changed_target, changed_target_landed])
    assert accepted is False
    assert "drudge_native_threat_observation_identity_drift" in reasons

    changed_scope = accepted_drudge_status()
    changed_scope["raid_runtime"]["drudge_charge"]["observations"][0]["landed"] = False
    changed_scope["raid_runtime"]["drudge_charge"]["observations"][0]["attempt_id"] = 99
    accepted, reasons = accepted_drudge_contract([changed_scope, accepted_drudge_status()])
    assert accepted is False
    assert "drudge_native_threat_observation_scope_drift" in reasons

    malformed_landing = accepted_drudge_status()
    malformed_landing["raid_runtime"]["drudge_charge"]["observations"][0]["landed"] = "false"
    accepted, reasons = accepted_drudge_contract([malformed_landing, accepted_drudge_status()])
    assert accepted is False
    assert "drudge_native_threat_landing_type_invalid" in reasons

    forged_farthest = accepted_drudge_status()
    first = forged_farthest["raid_runtime"]["drudge_charge"]["observations"][0]
    first["target_guid"] = forged_farthest["raid_runtime"]["roster"][4]["guid"]
    first["target_raw_guid"] = first["target_guid"]
    first["selected_distance"] = 34.5
    accepted, reasons = accepted_drudge_contract([forged_farthest])
    assert accepted is False
    assert "drudge_native_threat_selected_target_not_farthest" in reasons

    forged_seed = accepted_drudge_status()
    forged_seed["raid_runtime"]["drudge_threat_seed"]["observations"][0]["source_guid"] = 999999
    accepted, reasons = accepted_drudge_contract([forged_seed])
    assert accepted is True
    assert reasons == []


def test_drudge_anchor_fallback_is_generation_scoped_and_native_path_validated():
    root = Path(__file__).parents[1] / "src/server/game/Bots"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            root / "BotWorldPopulationMgrBotState.h",
            root
            / "Content/Raids/BlackwingDescent/Trash/Drudge"
            / "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp",
            root / "BotWorldPopulationMgrRaidRuntime.cpp",
        )
    )
    assert "ValidationRouteDrudgeAnchorAttemptId" in source
    assert "ValidationRouteDrudgeAnchorWipeGeneration" in source
    assert "ValidationRouteDrudgeAnchorRouteGeneration" in source
    assert "SelectAnchorPathSearch" in source
    assert "StrictNativePath(candidatePoint.X, candidatePoint.Y, candidateZ" in source
    assert "anchor_path_valid" in source


def test_acceptance_reconstructs_all_identity_facts():
    accepted, reasons = accepted_foundation_status(accepted_status())
    assert accepted is True
    assert reasons == []


def test_magmaw_diagnostic_accepts_only_its_materialized_roster_identity():
    status = accepted_status()
    runtime = status["raid_runtime"]
    profile = "blackwing_descent_10n_magmaw_diagnostic"
    _materialize_profile_identity(status, profile)
    runtime["strategy_id"] = profile
    runtime["route_progress"] = {"generation": 4, "node_index": 3}
    accepted, reasons = accepted_foundation_status(
        status,
        profile_name=profile,
        route_partition={"node_count": 4, "terminal_index": 3},
    )
    assert accepted is True
    assert reasons == []


def test_compacted_runtime_gem_arrays_match_padded_frozen_manifests():
    status = accepted_status()
    padded_slots = {
        (row["roster_slot_id"], item["slot"])
        for row in status["raid_runtime"]["roster"]
        for item in row["gear_identity_manifest"]["items"]
        if item["gem_item_ids"] and item["gem_item_ids"][-1] == 0
    }
    assert padded_slots, "fixture must contain padded frozen gem arrays"
    for row in status["raid_runtime"]["roster"]:
        for item in row["gear_identity_manifest"]["items"]:
            while item["gem_item_ids"] and item["gem_item_ids"][-1] == 0:
                item["gem_item_ids"].pop()
    assert _identity_manifest_rejections({"roster": status["raid_runtime"]["roster"]}) == []


def test_trailing_zero_gem_canonicalization_is_symmetric():
    assert _compact_trailing_zero_gems((71881, 0)) == _compact_trailing_zero_gems((71881,))
    assert _compact_trailing_zero_gems((71881,)) == _compact_trailing_zero_gems((71881, 0, 0))
    assert _compact_trailing_zero_gems((71881, 71882)) != _compact_trailing_zero_gems((71881,))
    assert _compact_trailing_zero_gems((0, 71881)) == (0, 71881)
    assert _compact_trailing_zero_gems(()) == ()


def test_genuine_gem_content_and_length_differences_still_fail_closed():
    status = accepted_status()
    dps_row = next(
        row for row in status["raid_runtime"]["roster"] if row["roster_slot_id"] == "raid_dps_3"
    )
    slot8 = next(item for item in dps_row["gear_identity_manifest"]["items"] if item["slot"] == 8)
    assert slot8["entry"] == 78417
    slot8["gem_item_ids"] = [71825]
    tank_row = next(
        row for row in status["raid_runtime"]["roster"] if row["roster_slot_id"] == "raid_tank_1"
    )
    slot0 = next(item for item in tank_row["gear_identity_manifest"]["items"] if item["slot"] == 0)
    assert slot0["entry"] == 78693 and len(slot0["gem_item_ids"]) == 2
    slot0["gem_item_ids"] = [slot0["gem_item_ids"][0]]
    reasons = _identity_manifest_rejections({"roster": status["raid_runtime"]["roster"]})
    assert "frozen_identity_gear_modifiers_mismatch" in reasons


def test_enchant_reforge_talent_and_glyph_comparisons_stay_strict():
    status = accepted_status()
    tank_row = next(
        row for row in status["raid_runtime"]["roster"] if row["roster_slot_id"] == "raid_tank_1"
    )
    slot0 = next(item for item in tank_row["gear_identity_manifest"]["items"] if item["slot"] == 0)
    slot0["enchant_id"] += 1
    slot0["reforge_id"] += 1
    reasons = _identity_manifest_rejections({"roster": status["raid_runtime"]["roster"]})
    assert "frozen_identity_gear_modifiers_mismatch" in reasons
    zeroed = accepted_status()
    zeroed["raid_runtime"]["roster"][0]["talents"] += [0]
    zeroed["raid_runtime"]["roster"][0]["glyphs"] += [0]
    reasons = _identity_manifest_rejections({"roster": zeroed["raid_runtime"]["roster"]})
    assert "frozen_identity_talents_mismatch" in reasons
    assert "frozen_identity_glyphs_mismatch" in reasons


def test_gem_gate_canonicalization_is_boundary_only_text_contract():
    source = (
        Path(__file__).resolve().parents[1]
        / "tools/raid_program/capture_runtime_acceptance.py"
    ).read_text(encoding="utf-8")
    assert (
        '_compact_trailing_zero_gems(actual[4]) != _compact_trailing_zero_gems(item["gem_item_ids"])'
        in source
    )
    assert '"gem_item_ids": tuple(int(value) for value in item.get("gem_item_ids", [])),' in source
    assert 'actual[3] != item["enchant_id"]' in source
    assert 'actual[5] != item["reforge_id"]' in source
    assert source.count("_compact_trailing_zero_gems") == 3


def test_diagnostic_capture_rejects_cross_shard_account_and_guid_identity():
    status = accepted_status()
    runtime = status["raid_runtime"]
    profile = "blackwing_descent_10n_magmaw_diagnostic"
    runtime["strategy_id"] = profile
    runtime["route_progress"] = {"generation": 4, "node_index": 3}
    magmaw = _expected_identity_by_slot(profile)["raid_tank_1"]
    omnotron = _expected_identity_by_slot("blackwing_descent_10n_omnotron_diagnostic")["raid_tank_1"]
    row = runtime["roster"][0]
    row.update(
        guid=omnotron["character_guid"],
        account_id=omnotron["account_id"],
        account=omnotron["account"],
        name=omnotron["name"],
    )
    accepted, reasons = accepted_foundation_status(
        status,
        profile_name=profile,
        route_partition={"node_count": 4, "terminal_index": 3},
    )
    assert accepted is False
    assert "frozen_identity_account_mismatch" in reasons
    assert "frozen_identity_character_guid_mismatch" in reasons
    assert magmaw["account"] != omnotron["account"]


def test_wrong_difficulty_duplicate_identity_and_cleanup_shape_fail():
    status = accepted_status()
    status["raid_runtime"]["map_difficulty"] = 2
    status["raid_runtime"]["roster"][-1]["guid"] = status["raid_runtime"]["roster"][0]["guid"]
    accepted, reasons = accepted_foundation_status(status)
    assert accepted is False
    assert "live_map_difficulty_10n" in reasons
    assert "unique_roster_guids" in reasons


def test_leader_must_be_one_of_the_exact_frozen_roster_guids():
    status = accepted_status()
    status["raid_runtime"]["leader_guid"] = 999999
    accepted, reasons = accepted_foundation_status(status)
    assert accepted is False
    assert "leader_not_in_exact_roster" in reasons


def test_foundation_rejects_empty_profile_assignment_and_stale_lockout_identity():
    status = accepted_status()
    status["raid_runtime"].update(
        profile_generation=0,
        profile_content_hash="",
        assignment_generation=0,
        lockout_save_id=43,
    )
    accepted, reasons = accepted_foundation_status(status)
    assert accepted is False
    assert "profile_generation_owned" in reasons
    assert "profile_content_hash_owned" in reasons
    assert "assignment_generation_owned" in reasons
    assert "lockout_save_matches_live_instance" in reasons


def test_roster_serialization_order_does_not_change_assignment_acceptance():
    status = accepted_status()
    status["raid_runtime"]["roster"].reverse()
    accepted, reasons = accepted_foundation_status(status)
    assert accepted is True
    assert reasons == []


def test_json_action_parser_ignores_prefix_and_malformed_rows():
    log = b'TC> {"ok":true,"action":"botauto_status","bots":10}\nnot-json\n{"action":"other"}\n'
    assert json_actions(log, "botauto_status") == [{"ok": True, "action": "botauto_status", "bots": 10}]


def test_json_log_cursor_reads_append_only_chunks_once_and_preserves_partial_rows(tmp_path: Path):
    path = tmp_path / "worldserver.log"
    first = b'TC> {"action":"botauto_status","evidence_sequence":1}\n'
    second = b'TC> {"action":"botauto_diagnose","evidence_sequence":2}\n'
    third = b'TC> {"action":"botauto_trace","evidence_sequence":3}\n'
    path.write_bytes(first + second[:17])
    cursor = JsonLogCursor(path)

    assert cursor.read_new_rows() == json_rows(first)
    assert cursor.read_new_rows() == []

    with path.open("ab") as handle:
        handle.write(second[17:] + third)
    incremental = cursor.read_new_rows()
    assert incremental == json_rows(second + third)
    assert cursor.read_new_rows() == []
    assert cursor.offset == path.stat().st_size
    assert [row["action"] for row in incremental] == [
        "botauto_diagnose", "botauto_trace",
    ]


def test_production_trace_transport_receipt_binds_fragmented_response_and_next_pressure_send(
    tmp_path: Path,
):
    path = tmp_path / "worldserver.log"
    path.write_bytes(b"")
    cursor = JsonLogCursor(path)
    scheduler = TelemetryScheduler(
        status_interval_sec=5, diagnose_interval_sec=30, trace_interval_sec=10,
    )
    ledger = TelemetryTransportLedger()

    commands = scheduler.commands_due(10.0)
    ledger.command_sent(
        commands, sent_at_monotonic=10.0,
        scheduler_state=scheduler.state(),
    )
    trace = {
        "ok": True,
        "action": "botauto_trace",
        "cohort_id": "raid",
        "server_epoch": 123,
        "attempt_id": 4,
        "profile_generation": 9,
        "profile_content_hash": "a" * 64,
        "active_profile": "blackwing_descent_10n",
        "raid_runtime": {
            "server_epoch": 123,
            "attempt_id": 4,
            "instance_id": 8,
            "strategy_id": "blackwing_descent_10n_magmaw_diagnostic",
            "assignment_generation": 7,
        },
        "bots": [{
            "bot_guid": 30008,
            "cursor_before": 46,
            "cursor_after": 302,
            "gap": True,
            "entries": [{"sequence": sequence} for sequence in range(175, 303)],
            "discontinuity": {
                "missing_sequence_start": 47,
                "missing_sequence_end": 174,
                "oldest_retained_sequence": 175,
                "newest_retained_sequence": 302,
            },
        }],
    }
    raw = b"TC> " + json.dumps(trace, separators=(",", ":")).encode() + b"\n"
    split = len(raw) // 2
    path.write_bytes(raw[:split])
    assert cursor.read_new_observations(observed_at=10.25) == []
    with path.open("ab") as handle:
        handle.write(raw[split:])
    observations = cursor.read_new_observations(observed_at=10.75)
    assert len(observations) == 1
    receipt_index = ledger.observe(observations[0])
    assert receipt_index == 0

    scheduler.observe_trace([trace], observed_at=10.75)
    ledger.finalize_responses([receipt_index], scheduler.state())
    assert scheduler.state()["effective_trace_interval_seconds"] == 2.0
    next_commands = scheduler.commands_due(12.75)
    assert next_commands == ["botauto trace all 128 delta"]
    ledger.command_sent(
        next_commands, sent_at_monotonic=12.75,
        scheduler_state=scheduler.state(),
    )

    receipt = ledger.receipts()[0]
    assert receipt["command_sent_at_monotonic"] == 10.0
    assert receipt["response_first_byte_observed_at_monotonic"] == 10.25
    assert receipt["response_complete_observed_at_monotonic"] == 10.75
    assert receipt["observation_poll_interval_seconds"] == 0.01
    assert receipt["response_bytes"] == len(raw)
    assert receipt["response_sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["parse_duration_seconds"] >= 0
    assert receipt["next_command_sent_at_monotonic"] == 12.75
    assert receipt["next_command_delay_seconds"] == 2.75
    assert receipt["send_to_first_byte_observed_seconds"] == 0.25
    assert receipt["observed_response_delivery_seconds"] == 0.5
    assert receipt["response_complete_to_next_send_seconds"] == 2.0
    assert receipt["association_state"] == "bound_in_serial_command_order"
    assert receipt["scheduler_state_after_response"][
        "effective_trace_interval_seconds"
    ] == 2.0
    assert receipt["identity"]["cohort_id"] == "raid"
    assert receipt["identity"]["server_epoch"] == 123
    assert receipt["identity"]["attempt_id"] == 4
    assert receipt["identity"]["profile_generation"] == 9
    assert receipt["identity"]["profile_content_hash"] == "a" * 64
    assert receipt["identity"]["active_profile"] == "blackwing_descent_10n"
    assert receipt["identity"]["actors"] == [{
        "bot_guid": 30008,
        "cursor_before": 46,
        "cursor_after": 302,
        "gap": True,
        "entry_count": 128,
        "first_sequence": 175,
        "last_sequence": 302,
        "missing_sequence_start": 47,
        "missing_sequence_end": 174,
        "oldest_retained_sequence": 175,
        "newest_retained_sequence": 302,
    }]


def test_trace_transport_receipt_rejects_ambiguous_outstanding_commands(
    tmp_path: Path,
):
    path = tmp_path / "worldserver.log"
    trace = b'{"action":"botauto_trace","bots":[]}\n'
    path.write_bytes(trace)
    cursor = JsonLogCursor(path)
    ledger = TelemetryTransportLedger()
    scheduler = TelemetryScheduler()
    scheduler.commands_due(1.0)
    ledger.command_sent(
        ["botauto trace all 128 delta"], sent_at_monotonic=1.0,
        scheduler_state=scheduler.state(),
    )
    ledger.command_sent(
        ["botauto trace all 128 delta"], sent_at_monotonic=11.0,
        scheduler_state=scheduler.state(),
    )

    observation = cursor.read_new_observations(observed_at=11.1)[0]
    assert ledger.observe(observation) is None
    assert [receipt["association_state"] for receipt in ledger.receipts()] == [
        "ambiguous_multiple_pending", "ambiguous_multiple_pending",
    ]


def test_action_projection_reuses_normalized_payloads_without_reparsing_log():
    rows = normalized_batch_payload(
        b'{"action":"botauto_status"}\n{"action":"botauto_trace"}\n'
    )
    projected = action_payloads(rows, "botauto_trace")
    assert projected == [rows[1]["payload"]]
    assert projected[0] is rows[1]["payload"]


def test_normalized_batch_payload_is_ordered_and_forbidden_assistance_is_recomputed():
    log = (
        b'TC> {"action":"botauto_status","evidence_sequence":3}\n'
        b'TC> {"action":"botauto_trace","forbidden_completion_assists":[]}\n'
        b'TC> {"action":"botauto_diagnose","forbidden_completion_assists":[{"action":"forced_kill"}]}\n'
    )
    rows = normalized_batch_payload(log)
    assert [row["capture_sequence"] for row in rows] == [1, 2, 3]
    assert [row["action"] for row in rows] == ["botauto_status", "botauto_trace", "botauto_diagnose"]
    assert _forbidden_assistance_entries(rows)[0]["path"].endswith("forbidden_completion_assists")


def test_demux_adapters_execute_focused_production_implementations():
    assert _normalized_batch_payload_impl.__module__ == "tools.raid_program.capture_evidence_demux"
    assert _evidence_demux_report_impl.__module__ == "tools.raid_program.capture_evidence_demux"
    assert _required_telemetry_envelope_report.__module__ == "tools.raid_program.capture_evidence_demux"
    assert _trace_actor_transport_rejections.__module__ == "tools.raid_program.capture_evidence_demux"


def test_native_wipe_reset_recovery_is_reconstructed_across_statuses():
    ready = accepted_status()
    ready["raid_runtime"]["evidence_sequence"] = 1
    engaged = accepted_status()
    engaged["raid_runtime"].update(
        evidence_sequence=2, encounter_in_progress=True, boss_states=[1] + [0] * 5,
        ready_check_satisfied=False, wipe_state="engaged", recovery_state="none",
    )
    wiped = accepted_status()
    wiped["raid_runtime"].update(
        evidence_sequence=70, alive_size=0, ready_check_satisfied=False, wipe_generation=1,
        encounter_in_progress=False, recovery_state="release_resurrection_pending",
        wipe_state="wiped",
    )
    reset = accepted_status()
    reset["raid_runtime"].update(
        evidence_sequence=71, alive_size=0, boss_reset_generation=1, wipe_generation=1,
        recovery_state="release_resurrection_pending", wipe_state="wiped",
    )
    recovered = accepted_status()
    recovered["raid_runtime"].update(
        evidence_sequence=72, boss_reset_generation=1, wipe_generation=1, recovery_generation=1,
        recovery_state="recovered_ready_check", wipe_state="ready",
    )
    recovered["raid_runtime"]["native_recovery"] = {
        "death_observed": True, "corpse_observed": True, "release_observed": True,
        "resurrection_observed": True, "runback_observed": True,
        "ready_check_action_observed": True, "evidence_complete": True,
        "ready_check_action_generation": 2, "ready_check_action_attempt_id": 1,
        "ready_check_action_wipe_generation": 1,
        "ready_check_assignment_generation": 1,
        "ready_check_action_evidence_sequence": 72,
        "recovery_wipe_generation": 1,
        "members": [
            {
                "guid": 1001 + index, "wipe_generation": 1,
                "death_sequence": 10 + index * 6,
                "corpse_sequence": 11 + index * 6,
                "release_sequence": 12 + index * 6,
                "runback_sequence": 13 + index * 6,
                "reentry_sequence": 14 + index * 6,
                "resurrection_sequence": 15 + index * 6,
            }
            for index in range(10)
        ],
    }
    accepted, reasons = accepted_native_recovery([ready, engaged, wiped, reset, recovered])
    assert accepted is True
    assert reasons == []

    pre_magmaw = json.loads(json.dumps([ready, engaged, wiped, reset, recovered]))
    for status in pre_magmaw:
        status["raid_runtime"]["route_progress"] = {"generation": 3, "node_index": 2}
    accepted, reasons = accepted_native_recovery(pre_magmaw)
    assert accepted is False
    assert "native_magmaw_engagement_not_observed" in reasons

    stale = json.loads(json.dumps([ready, engaged, wiped, reset, recovered]))
    stale[1]["raid_runtime"]["evidence_sequence"] = 101
    stale[2]["raid_runtime"]["evidence_sequence"] = 102
    stale[3]["raid_runtime"]["evidence_sequence"] = 103
    stale[4]["raid_runtime"]["evidence_sequence"] = 170
    stale[4]["raid_runtime"]["native_recovery"]["ready_check_action_evidence_sequence"] = 170
    accepted, reasons = accepted_native_recovery(stale)
    assert accepted is False
    assert "native_per_member_recovery_predates_latest_engagement" in reasons

    future_deaths = json.loads(json.dumps([ready, engaged, wiped, reset, recovered]))
    future_deaths[1]["raid_runtime"]["evidence_sequence"] = 101
    future_deaths[2]["raid_runtime"]["evidence_sequence"] = 102
    future_deaths[3]["raid_runtime"]["evidence_sequence"] = 180
    future_deaths[4]["raid_runtime"]["evidence_sequence"] = 240
    future_deaths[4]["raid_runtime"]["native_recovery"]["ready_check_action_evidence_sequence"] = 240
    for index, member in enumerate(future_deaths[4]["raid_runtime"]["native_recovery"]["members"]):
        for offset, field in enumerate((
            "death_sequence", "corpse_sequence", "release_sequence",
            "runback_sequence", "reentry_sequence", "resurrection_sequence",
        )):
            member[field] = 120 + index * 6 + offset
    accepted, reasons = accepted_native_recovery(future_deaths)
    assert accepted is False
    assert "native_per_member_death_postdates_latest_wipe_snapshot" in reasons


def test_native_recovery_requires_post_wipe_reset_increment_and_bounded_member_sequences():
    ready = accepted_status()
    ready["raid_runtime"].update(evidence_sequence=1, boss_reset_generation=7)
    engaged = accepted_status()
    engaged["raid_runtime"].update(
        evidence_sequence=2, boss_reset_generation=7, encounter_in_progress=True,
        boss_states=[1] + [0] * 5, ready_check_satisfied=False,
        wipe_state="engaged", recovery_state="none",
    )
    wiped = accepted_status()
    wiped["raid_runtime"].update(
        evidence_sequence=3, boss_reset_generation=7, wipe_generation=1,
        boss_reset_generation_at_wipe=7,
        alive_size=0, ready_check_satisfied=False, encounter_in_progress=False,
        wipe_state="wiped", recovery_state="release_resurrection_pending",
    )
    unchanged_reset = accepted_status()
    unchanged_reset["raid_runtime"].update(
        evidence_sequence=4, boss_reset_generation=7, wipe_generation=1,
        alive_size=0, wipe_state="wiped",
        recovery_state="release_resurrection_pending",
    )
    recovered = accepted_status()
    recovered["raid_runtime"].update(
        evidence_sequence=5, boss_reset_generation=7, wipe_generation=1,
        recovery_generation=1, recovery_state="recovered_ready_check",
        wipe_state="ready",
    )
    recovered["raid_runtime"]["native_recovery"] = {
        "death_observed": True, "corpse_observed": True, "release_observed": True,
        "resurrection_observed": True, "runback_observed": True,
        "ready_check_action_observed": True, "evidence_complete": True,
        "ready_check_action_generation": 2, "ready_check_action_attempt_id": 1,
        "ready_check_action_wipe_generation": 1,
        "ready_check_assignment_generation": 1,
        "ready_check_action_evidence_sequence": 5,
        "recovery_wipe_generation": 1,
        "members": [
            {
                "guid": 1001 + index, "wipe_generation": 1,
                "death_sequence": 10 + index * 6,
                "corpse_sequence": 11 + index * 6,
                "release_sequence": 12 + index * 6,
                "runback_sequence": 13 + index * 6,
                "reentry_sequence": 14 + index * 6,
                "resurrection_sequence": 15 + index * 6,
            }
            for index in range(10)
        ],
    }
    accepted, reasons = accepted_native_recovery(
        [ready, engaged, wiped, unchanged_reset, recovered]
    )
    assert accepted is False
    assert "boss_reset_observed" in reasons

    valid = json.loads(json.dumps(recovered))
    accepted, reasons = accepted_native_recovery(
        [ready, engaged, wiped, unchanged_reset, valid]
    )
    assert accepted is False
    assert "native_per_member_death_postdates_latest_wipe_snapshot" in reasons


def test_native_recovery_does_not_cross_pair_reset_from_an_earlier_wipe():
    ready = accepted_status()
    engaged1 = accepted_status()
    engaged1["raid_runtime"].update(
        evidence_sequence=2, encounter_in_progress=True,
        boss_states=[1] + [0] * 5, ready_check_satisfied=False,
        wipe_state="engaged", recovery_state="none",
    )
    wiped1 = accepted_status()
    wiped1["raid_runtime"].update(
        evidence_sequence=3, alive_size=0, wipe_generation=1,
        boss_reset_generation_at_wipe=0, ready_check_satisfied=False,
        wipe_state="wiped", recovery_state="release_resurrection_pending",
    )
    reset1 = json.loads(json.dumps(wiped1))
    reset1["raid_runtime"].update(evidence_sequence=4, boss_reset_generation=1)
    recovered1 = accepted_status()
    recovered1["raid_runtime"].update(
        evidence_sequence=70, wipe_generation=1, boss_reset_generation=1,
        recovery_generation=1, recovery_state="recovered_ready_check",
    )
    engaged2 = json.loads(json.dumps(engaged1))
    engaged2["raid_runtime"].update(
        evidence_sequence=71, wipe_generation=1, boss_reset_generation=1,
        recovery_generation=1,
    )
    wiped2 = json.loads(json.dumps(wiped1))
    wiped2["raid_runtime"].update(
        evidence_sequence=72, wipe_generation=2, boss_reset_generation=1,
        boss_reset_generation_at_wipe=1, recovery_generation=1,
    )
    recovered2 = accepted_status()
    recovered2["raid_runtime"].update(
        evidence_sequence=140, wipe_generation=2, boss_reset_generation=1,
        boss_reset_generation_at_wipe=1, recovery_generation=2,
        recovery_state="recovered_ready_check",
    )
    recovered2["raid_runtime"]["native_recovery"] = {
        "death_observed": True, "corpse_observed": True, "release_observed": True,
        "resurrection_observed": True, "runback_observed": True,
        "ready_check_action_observed": True, "evidence_complete": True,
        "ready_check_action_generation": 3, "ready_check_action_attempt_id": 1,
        "ready_check_action_wipe_generation": 2,
        "ready_check_assignment_generation": 1,
        "ready_check_action_evidence_sequence": 140,
        "recovery_wipe_generation": 2,
        "members": [
            {
                "guid": 1001 + index, "wipe_generation": 2,
                "death_sequence": 75 + index * 6,
                "corpse_sequence": 76 + index * 6,
                "release_sequence": 77 + index * 6,
                "runback_sequence": 78 + index * 6,
                "reentry_sequence": 79 + index * 6,
                "resurrection_sequence": 80 + index * 6,
            }
            for index in range(10)
        ],
    }
    accepted, reasons = accepted_native_recovery(
        [ready, engaged1, wiped1, reset1, recovered1, engaged2, wiped2, recovered2]
    )
    assert accepted is False
    assert "boss_reset_observed" in reasons


def test_native_recovery_requires_the_latest_wipe_transition_in_retained_evidence():
    ready = accepted_status()
    engaged = accepted_status()
    engaged["raid_runtime"].update(
        evidence_sequence=2, encounter_in_progress=True,
        boss_states=[1] + [0] * 5, ready_check_satisfied=False,
        wipe_state="engaged", recovery_state="none",
    )
    wiped = accepted_status()
    wiped["raid_runtime"].update(
        evidence_sequence=3, alive_size=0, wipe_generation=1,
        boss_reset_generation_at_wipe=0, ready_check_satisfied=False,
        wipe_state="wiped", recovery_state="release_resurrection_pending",
    )
    reset = json.loads(json.dumps(wiped))
    reset["raid_runtime"].update(evidence_sequence=4, boss_reset_generation=1)
    recovered = accepted_status()
    recovered["raid_runtime"].update(
        evidence_sequence=70, wipe_generation=1, boss_reset_generation=1,
        recovery_generation=1, recovery_state="recovered_ready_check",
    )
    final_without_observed_second_wipe = accepted_status()
    final_without_observed_second_wipe["raid_runtime"].update(
        evidence_sequence=140, wipe_generation=2, boss_reset_generation=2,
        recovery_generation=2, recovery_state="recovered_ready_check",
    )
    final_without_observed_second_wipe["raid_runtime"]["native_recovery"] = {
        "death_observed": True, "corpse_observed": True, "release_observed": True,
        "resurrection_observed": True, "runback_observed": True,
        "ready_check_action_observed": True, "evidence_complete": True,
        "ready_check_action_generation": 3, "ready_check_action_attempt_id": 1,
        "ready_check_action_wipe_generation": 2,
        "ready_check_assignment_generation": 1,
        "ready_check_action_evidence_sequence": 140,
        "recovery_wipe_generation": 2,
        "members": [
            {
                "guid": 1001 + index, "wipe_generation": 2,
                "death_sequence": 75 + index * 6,
                "corpse_sequence": 76 + index * 6,
                "release_sequence": 77 + index * 6,
                "runback_sequence": 78 + index * 6,
                "reentry_sequence": 79 + index * 6,
                "resurrection_sequence": 80 + index * 6,
            }
            for index in range(10)
        ],
    }
    accepted, reasons = accepted_native_recovery(
        [ready, engaged, wiped, reset, recovered, final_without_observed_second_wipe]
    )
    assert accepted is False
    assert "native_latest_wipe_transition_not_observed" in reasons


def test_native_recovery_rejects_stored_ready_without_observed_transitions():
    accepted, reasons = accepted_native_recovery([accepted_status()])
    assert accepted is False
    assert "native_wipe_observed" in reasons
    assert "boss_reset_observed" in reasons
    assert "native_recovery_observed" in reasons


def test_native_recovery_rejects_mixed_identity_duplicate_sequence_and_wrong_composition():
    first = accepted_status()
    second = accepted_status()
    second["raid_runtime"]["group_guid"] = 999
    second["raid_runtime"]["evidence_sequence"] = 2
    accepted, reasons = accepted_native_recovery([first, second])
    assert accepted is False
    assert "native_recovery_mixed_identity" in reasons

    decreasing = accepted_status()
    first_sequence = accepted_status()
    first_sequence["raid_runtime"]["evidence_sequence"] = 2
    accepted, reasons = accepted_native_recovery([first_sequence, decreasing])
    assert accepted is False
    assert "native_evidence_sequence_not_monotonic" in reasons

    bad_roles = accepted_status()
    bad_roles["raid_runtime"]["roster"][9]["role"] = "healer"
    accepted, reasons = accepted_foundation_status(bad_roles)
    assert accepted is False
    assert "exact_10n_role_composition" in reasons


def test_repeated_snapshots_are_allowed_but_strategy_transition_requires_route_advance():
    first = accepted_status()
    repeated = accepted_status()
    accepted, reasons = accepted_native_recovery([first, repeated])
    assert not accepted
    assert "native_wipe_observed" in reasons

    transitioned = accepted_status()
    transitioned["raid_runtime"].update(
        evidence_sequence=2,
        strategy_id="blackwing_descent_10n_boss_route",
        route_progress={"generation": 5, "node_index": 4},
        strategy_transition={
            "from_strategy": "blackwing_descent_10n",
            "to_strategy": "blackwing_descent_10n_boss_route",
            "advanced": True,
        },
    )
    accepted, reasons = accepted_native_recovery([first, transitioned])
    assert "native_strategy_transition_without_route_advancement" not in reasons


def test_forbidden_event_markers_are_rejected_while_native_fields_are_not():
    rows = normalized_batch_payload(
        b'{"action":"native_recovery","result":"direct_resurrection"}\n'
        b'{"action":"botauto_status","recovery_state":"release_resurrection_pending"}\n'
    )
    found = _forbidden_assistance_entries(rows)
    assert any(entry["kind"] == "forbidden_event_marker" for entry in found)
    assert all("release_resurrection_pending" not in str(entry) for entry in found)


def test_no_fallback_diagnostic_is_not_misclassified_as_fallback_assistance():
    rows = normalized_batch_payload(
        b'{"action":"botauto_trace","recovery_mode":"blocked_no_fallback"}\n'
        b'{"action":"botauto_trace","recovery_mode":"fallback_action"}\n'
    )
    found = _forbidden_assistance_entries(rows)
    assert all(entry["value"] != "blocked_no_fallback" for entry in found)
    assert any(entry["value"] == "fallback_action" for entry in found)


def test_preflight_reports_coordinator_and_protected_process_overlap():
    report = preflight_runtime_exclusions(__import__("pathlib").Path.cwd())
    assert "coordinator_idle" in report
    assert "process_overlap" in report


def test_process_overlap_classifies_entrypoint_not_binary_data_argument():
    assert _protected_process_matches([
        "/usr/bin/pixi",
        "run",
        "python",
        "-m",
        "tools.raid_program.capture_phase1_raid_foundation",
        "--binary",
        "/tmp/build/worldserver",
    ]) == []
    assert _protected_process_matches(["/tmp/build/worldserver", "--config", "test.conf"]) == [
        "worldserver"
    ]
    assert _protected_process_matches([
        "/usr/bin/python3",
        "/repo/tools/bot_ml/run_live_bot_validation.py",
        "--worldserver",
        "/tmp/build/worldserver",
    ]) == ["run_live_bot_validation.py"]


def test_dvc_lineage_requires_an_exact_empty_json_status():
    assert _dvc_status_is_clean("{}") is True
    assert _dvc_status_is_clean('{"validation_scenarios": [{"changed outs": {}}]}') is False
    assert _dvc_status_is_clean("WARN inherited manifest\n{}") is False


def test_build_and_runtime_validation_use_focused_production_module():
    expected_module = "tools.raid_program.capture_environment_validation"
    for function in (
        git_identity,
        _utc_timestamp,
        validate_build_receipt,
        build_policy_path_for_receipt,
        _process_arguments,
        _protected_process_matches,
        _dvc_status_is_clean,
        preflight_runtime_exclusions,
        validate_runtime_profile_assets,
        sha256_file,
    ):
        assert function.__module__ == expected_module


def test_live_evidence_demux_rejects_cross_identity_runtime():
    first = accepted_status()
    first["cohort_id"] = "raid"
    second = accepted_status()
    second["cohort_id"] = "raid"
    second["raid_runtime"]["attempt_id"] = 2
    rows = normalized_batch_payload(
        (json.dumps(first) + "\n" + json.dumps(second) + "\n").encode()
    )
    assert "evidence_demux_cross_identity_row" in evidence_demux_rejections(rows)


def test_live_evidence_demux_rejects_profile_and_assignment_drift():
    active = accepted_status()
    active["cohort_id"] = "raid"
    drifted = json.loads(json.dumps(active))
    drifted["raid_runtime"]["profile_generation"] = 2
    drifted["raid_runtime"]["profile_content_hash"] = "different-profile"
    drifted["raid_runtime"]["assignment_generation"] = 9
    rows = normalized_batch_payload(
        (json.dumps(active) + "\n" + json.dumps(drifted) + "\n").encode()
    )
    assert "evidence_demux_cross_identity_row" in evidence_demux_rejections(rows)


def test_live_evidence_demux_binds_declared_route_transition_and_partial_death():
    active = accepted_status()
    active["cohort_id"] = "raid"
    transitioned = json.loads(json.dumps(active))
    transitioned["raid_runtime"]["strategy_id"] = "trash_two_tank_charge_lanes"
    transitioned["raid_runtime"]["route_progress"] = {"generation": 5, "node_index": 4}
    transitioned["raid_runtime"]["strategy_transition"] = {
        "from_strategy": active["raid_runtime"]["strategy_id"],
        "to_strategy": "trash_two_tank_charge_lanes",
        "advanced": True,
    }
    transitioned["raid_runtime"]["roster"][1]["active"] = False
    transitioned["raid_runtime"]["alive_size"] = 9
    bots = [{"bot_guid": 1001 + index} for index in range(10)]
    diagnosis = {
        "ok": True, "action": "botauto_diagnose", "cohort_id": "raid",
        "raid_runtime": transitioned["raid_runtime"], "bots": bots,
    }
    trace = {
        "ok": True, "action": "botauto_trace", "cohort_id": "raid",
        "raid_runtime": transitioned["raid_runtime"],
        "bots": [{"bot_guid": 1001 + index, "entries": [], "delta": True, "gap": False}
                 for index in range(10)],
    }
    readycheck = {
        "ok": True, "action": "botauto_readycheck", "cohort_id": "raid",
        "raid_runtime": transitioned["raid_runtime"],
    }
    stop = {
        "ok": True, "action": "botauto_stop", "cohort_id": "raid",
        "server_epoch": 88, "attempt_id": 1,
        "raid_runtime_before_cleanup": transitioned["raid_runtime"],
        "post_cleanup": {"active": False, "bots": 0, "lease_count": 0},
    }
    inactive = json.loads(json.dumps(transitioned))
    inactive["active"] = False
    inactive["bots"] = 0
    inactive["lease_count"] = 0
    inactive["server_epoch"] = 88
    inactive["attempt_id"] = 1
    inactive["raid_runtime"]["active"] = False
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode()
                   for row in (active, transitioned, diagnosis, trace, readycheck, stop, inactive)) + b"\n"
    )
    report = evidence_demux_report(rows)
    assert report["rejections"] == []
    assert report["bound_rows"] == report["retained_rows"] == 7


def test_live_evidence_demux_rejects_lease_drift_and_trace_cursor_gap():
    active = accepted_status()
    active["cohort_id"] = "raid"
    drifted = json.loads(json.dumps(active))
    drifted["raid_runtime"]["roster"][1]["lease_owned"] = False
    gap = {
        "ok": True, "action": "botauto_trace", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"],
        "bots": [{"bot_guid": 1001 + index, "entries": [], "delta": True, "gap": index == 0}
                 for index in range(10)],
    }
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (active, drifted, gap)) + b"\n"
    )
    reasons = evidence_demux_rejections(rows)
    assert "evidence_demux_roster_binding_lease_invalid" in reasons
    assert "evidence_demux_trace_delta_gap" in reasons


def test_native_trace_discontinuity_transition_resumes_through_controller_demux(tmp_path):
    fixture_source = tmp_path / "trace_discontinuity_fixture.cpp"
    fixture_binary = tmp_path / "trace_discontinuity_fixture"
    fixture_source.write_text(r'''
#include "src/server/game/Bots/BotWorldTraceExportCursor.h"

#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>
#include <vector>

using BotWorldTrace::BuildExportCursorTransition;
using BotWorldTrace::ExportCursorTransition;
using BotWorldTrace::WriteExportCursorFields;

void Emit(std::vector<std::uint64_t> const& retained, ExportCursorTransition const& transition)
{
    std::cout << "{\"bot_guid\":30008,\"entries\":[";
    for (std::size_t offset = 0; offset < transition.EntryCount; ++offset)
    {
        if (offset)
            std::cout << ',';
        std::cout << "{\"sequence\":"
                  << retained[transition.FirstEntryIndex + offset] << '}';
    }
    std::cout << ']';
    WriteExportCursorFields(std::cout, transition);
    std::cout << "}\n";
}

int main()
{
    ExportCursorTransition empty = BuildExportCursorTransition({}, 0, false, 128);
    assert(!empty.HasDiscontinuity && empty.EntryCount == 0 && empty.CursorAfter == 0);

    ExportCursorTransition initial = BuildExportCursorTransition({1, 2, 3}, 0, false, 128);
    assert(!initial.HasDiscontinuity && initial.EntryCount == 3 && initial.CursorAfter == 3);

    ExportCursorTransition partial = BuildExportCursorTransition({1, 2, 3}, 0, false, 2);
    assert(!partial.HasDiscontinuity && partial.EntryCount == 2 && partial.CursorAfter == 2);
    ExportCursorTransition noGap = BuildExportCursorTransition({1, 2, 3}, 2, true, 128);
    assert(!noGap.HasDiscontinuity && noGap.EntryCount == 1 && noGap.CursorAfter == 3);

    std::uint64_t const maximum = std::numeric_limits<std::uint64_t>::max();
    ExportCursorTransition atBoundary = BuildExportCursorTransition({maximum}, maximum - 1, true, 1);
    assert(!atBoundary.HasDiscontinuity && atBoundary.EntryCount == 1 && atBoundary.CursorAfter == maximum);
    ExportCursorTransition exhaustedBoundary = BuildExportCursorTransition({maximum}, maximum, true, 1);
    assert(!exhaustedBoundary.HasDiscontinuity && exhaustedBoundary.EntryCount == 0
           && exhaustedBoundary.CursorAfter == maximum);

    std::vector<std::uint64_t> retained;
    for (std::uint64_t sequence = 175; sequence <= 302; ++sequence)
        retained.push_back(sequence);
    ExportCursorTransition first = BuildExportCursorTransition(retained, 46, true, 64);
    assert(first.HasDiscontinuity && first.MissingSequenceStart == 47
           && first.MissingSequenceEnd == 174 && first.OldestRetainedSequence == 175
           && first.NewestRetainedSequence == 302 && first.EntryCount == 64
           && first.CursorAfter == 238);
    Emit(retained, first);

    ExportCursorTransition second = BuildExportCursorTransition(
        retained, first.CursorAfter, true, 128);
    assert(!second.HasDiscontinuity && second.FirstEntryIndex == 64
           && second.EntryCount == 64 && second.CursorAfter == 302);
    Emit(retained, second);
}
''', encoding="utf-8")
    subprocess.run(
        [
            "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(Path(__file__).resolve().parents[1]),
            str(fixture_source), "-o", str(fixture_binary),
        ],
        check=True,
    )
    native_rows = [
        json.loads(line)
        for line in subprocess.check_output([str(fixture_binary)], text=True).splitlines()
    ]
    assert native_rows[0]["discontinuity"] == {
        "missing_sequence_start": 47,
        "missing_sequence_end": 174,
        "oldest_retained_sequence": 175,
        "newest_retained_sequence": 302,
    }
    assert native_rows[0]["cursor_before"] == 46
    assert native_rows[0]["cursor_after"] == 238
    assert native_rows[0]["gap"] is True
    assert [entry["sequence"] for entry in native_rows[0]["entries"]] == list(range(175, 239))
    assert native_rows[1]["cursor_before"] == 238
    assert native_rows[1]["cursor_after"] == 302
    assert native_rows[1]["gap"] is False
    assert [entry["sequence"] for entry in native_rows[1]["entries"]] == list(range(239, 303))

    active = accepted_status()
    active["cohort_id"] = "raid"
    for index, member in enumerate(active["raid_runtime"]["roster"], start=1):
        member["guid"] = 30000 + index

    def trace_envelope(native_row: dict, peer_cursor: int) -> dict:
        bots = []
        for index in range(1, 11):
            guid = 30000 + index
            if guid == 30008:
                bots.append(native_row)
            else:
                bots.append({
                    "bot_guid": guid,
                    "entries": [{"sequence": peer_cursor + 1}],
                    "delta": True,
                    "cursor_before": peer_cursor,
                    "cursor_after": peer_cursor + 1,
                    "gap": False,
                })
        return {
            "ok": True,
            "action": "botauto_trace",
            "cohort_id": "raid",
            "raid_runtime": active["raid_runtime"],
            "bots": bots,
        }

    rows = normalized_batch_payload(
        b"\n".join(
            json.dumps(row, separators=(",", ":")).encode()
            for row in (
                active,
                trace_envelope(native_rows[0], 10),
                trace_envelope(native_rows[1], 11),
            )
        ) + b"\n"
    )
    report = evidence_demux_report(rows)
    first_binding = rows[1]["payload"]["bots"][7]["identity_binding"]
    second_binding = rows[2]["payload"]["bots"][7]["identity_binding"]
    assert first_binding["reasons"] == ["evidence_demux_trace_delta_gap"]
    assert second_binding["state"] == "bound"
    assert report["actor_binding_counts"] == {
        "total": 20, "bound": 19, "rejected": 1, "unchecked": 0,
    }
    assert report["trace_discontinuities"] == [{
        "epoch_id": "trace_discontinuity:30008:47:2",
        "bot_guid": 30008,
        "cursor_before": 46,
        "missing_sequence_start": 47,
        "missing_sequence_end": 174,
        "oldest_retained_sequence": 175,
        "newest_retained_sequence": 302,
        "first_gap_capture_sequence": 2,
        "last_gap_capture_sequence": 2,
        "gap_envelope_count": 1,
        "first_recovered_capture_sequence": 2,
        "first_recovered_sequence": 175,
        "classification": (
            "explicit_native_discontinuity_retained_suffix_resumed_"
            "missing_interval_rejected"
        ),
        "gate_passed": False,
    }]
    assert "evidence_demux_trace_delta_gap" in report["rejections"]
    assert report["gate_passed"] is False


def test_chainwielder_byte_faithful_actor_gap_does_not_reject_peer_trace_rows():
    # Exact canonical bot sub-envelope retained at capture sequences 28 and 30
    # in raw-output.log d28fabf617748a887ef0b2655df0a0dea852d7bc192fbaeceabb26228999ffa8.
    # Keeping the producer bytes here prevents the replay from starting from
    # a pre-approved controller observation.
    raw_gap_actor = (
        b'{"bot_guid":30008,"bot_name":"Mgwdpsc","cursor_after":46,'
        b'"cursor_before":46,"delta":true,"entries":[],"gap":true}'
    )
    assert hashlib.sha256(raw_gap_actor).hexdigest() == (
        "37e04eeefdbb3ace7e00f9d32ef44f5db2604157d5dbcb2fafecd8b21e1a7ff8"
    )
    active = accepted_status()
    active["cohort_id"] = "raid"
    for index, member in enumerate(active["raid_runtime"]["roster"], start=1):
        member["guid"] = 30000 + index

    diagnosis = {
        "ok": True,
        "action": "botauto_diagnose",
        "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"],
        "bots": [
            {"identity": {"bot_guid": 30000 + index}}
            for index in range(1, 11)
        ],
    }

    def delta_trace(peer_cursor: int) -> dict:
        bots = []
        for index in range(1, 11):
            guid = 30000 + index
            if guid == 30008:
                bots.append(json.loads(raw_gap_actor))
            else:
                bots.append({
                    "bot_guid": guid,
                    "cursor_before": peer_cursor,
                    "cursor_after": peer_cursor + 1,
                    "delta": True,
                    "entries": [{"sequence": peer_cursor + 1}],
                    "gap": False,
                })
        return {
            "ok": True,
            "action": "botauto_trace",
            "cohort_id": "raid",
            "raid_runtime": active["raid_runtime"],
            "bots": bots,
        }

    # The terminal full snapshot retained 30008 sequences 3248 down to 3121.
    # It closes the observed missing interval at 47..3120 without claiming
    # that the omitted decisions can be reconstructed.
    full_trace = {
        "ok": True,
        "action": "botauto_trace",
        "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"],
        "bots": [
            {
                "bot_guid": 30000 + index,
                "entries": (
                    [{"sequence": sequence} for sequence in range(3248, 3120, -1)]
                    if index == 8
                    else [{"sequence": 100 + index}]
                ),
            }
            for index in range(1, 11)
        ],
    }
    rows = normalized_batch_payload(
        b"\n".join(
            json.dumps(row, separators=(",", ":")).encode()
            for row in (
                active, diagnosis, delta_trace(10), delta_trace(11), full_trace,
            )
        ) + b"\n"
    )
    report = evidence_demux_report(rows)

    for capture_sequence in (3, 4):
        row = rows[capture_sequence - 1]
        assert row["identity_binding"]["state"] == "bound"
        bindings = {
            bot["bot_guid"]: bot["identity_binding"]
            for bot in row["payload"]["bots"]
        }
        assert bindings[30008]["state"] == "rejected"
        assert bindings[30008]["reasons"] == ["evidence_demux_trace_delta_gap"]
        assert all(
            binding["state"] == "bound"
            for guid, binding in bindings.items()
            if guid != 30008
        )

    assert report["actor_binding_counts"] == {
        "total": 40, "bound": 38, "rejected": 2, "unchecked": 0,
    }
    assert report["trace_discontinuities"] == [{
        "epoch_id": "trace_discontinuity:30008:47:3",
        "bot_guid": 30008,
        "cursor_before": 46,
        "missing_sequence_start": 47,
        "missing_sequence_end": 3120,
        "first_gap_capture_sequence": 3,
        "last_gap_capture_sequence": 4,
        "gap_envelope_count": 2,
        "first_recovered_capture_sequence": 5,
        "first_recovered_sequence": 3121,
        "classification": "closed_by_bounded_snapshot_missing_interval_rejected",
        "gate_passed": False,
    }]
    assert "evidence_demux_trace_delta_gap" in report["rejections"]
    assert report["gate_passed"] is False


def test_live_evidence_demux_rejects_frozen_character_build_drift():
    active = accepted_status()
    active["cohort_id"] = "raid"
    for field, replacement in (
        ("talents", [{"spell_id": 999999, "rank": 1}]),
        ("glyphs", [999999]),
        ("gear_identity_manifest", {"sha256": "forged"}),
    ):
        drifted = json.loads(json.dumps(active))
        drifted["raid_runtime"]["roster"][0][field] = replacement
        rows = normalized_batch_payload(
            b"\n".join(json.dumps(row).encode() for row in (active, drifted)) + b"\n"
        )
        assert "evidence_demux_cross_identity_row" in evidence_demux_rejections(rows)


def test_capture_telemetry_poll_is_incremental_and_bounded():
    root = Path(__file__).resolve().parents[1]
    capture_source = (root / "tools/raid_program/capture_live_run.py").read_text(encoding="utf-8")
    bot_root = root / "src/server/game/Bots"
    manager_source = (bot_root / "BotWorldPopulationMgrStatus.cpp").read_text(encoding="utf-8")
    header_source = (bot_root / "BotWorldPopulationMgrRuntimeContracts.h").read_text(encoding="utf-8")

    # A long capture must not re-export the complete ring on every poll.  Keep
    # this source-level regression independent of a heavyweight worldserver
    # build while checking the command, cursor, and hard server-side bound.
    assert "botauto trace all 128 delta" in capture_source
    assert "TraceExportCursorByGuid" in manager_source
    assert "TraceExportCursorByGuid" in header_source
    assert "std::min<uint32>(limit, 128)" in manager_source
    assert "BuildRaidRuntimeJson(true)" in manager_source


def test_drudge_lane_contract_is_diagnostic_while_route_outcome_gates_success():
    root = Path(__file__).resolve().parents[1] / "tools/raid_program"
    setup_source = (root / "capture_setup.py").read_text(encoding="utf-8")
    finalization_source = (root / "capture_finalization.py").read_text(encoding="utf-8")
    contract_source = (root / "capture_runtime_acceptance.py").read_text(encoding="utf-8")
    assert "drudge_observed = not args.trace_transport_smoke and (" in setup_source
    assert 'profile_name.endswith("_magmaw_diagnostic")' in setup_source
    assert "drudge_required = False" in setup_source
    assert '"acceptance_role": "diagnostic_only"' in finalization_source
    assert "if drudge_observed" in finalization_source
    assert "and (not drudge_required or drudge_accepted)" in finalization_source
    assert '"alive_size_10": runtime.get("alive_size") == 10' in contract_source


def test_live_evidence_demux_rejects_strategy_drift():
    active = accepted_status()
    active["cohort_id"] = "raid"
    drifted = json.loads(json.dumps(active))
    drifted["action"] = "botauto_diagnose"
    drifted["raid_runtime"]["strategy_id"] = "different_strategy"
    rows = normalized_batch_payload(
        (json.dumps(active) + "\n" + json.dumps(drifted) + "\n").encode()
    )
    assert "evidence_demux_strategy_transition_without_route_advancement" in evidence_demux_rejections(rows)

    drifted["raid_runtime"].update(
            route_progress={"generation": 5, "node_index": 4},
        strategy_transition={
            "from_strategy": active["raid_runtime"]["strategy_id"],
            "to_strategy": "different_strategy",
            "advanced": True,
        },
    )
    rows = normalized_batch_payload(
        (json.dumps(active) + "\n" + json.dumps(drifted) + "\n").encode()
    )
    assert "evidence_demux_strategy_transition_without_route_advancement" not in evidence_demux_rejections(rows)


def _personal_threat_episode_demux_input():
    target = {
        "actor_guid": 1008,
        "scope_key": "magmaw-scope",
        "route_node_id": "bwd.magmaw.encounter",
        "route_generation": 4,
        "parent_wave_generation": (1 << 63) | 1,
        "parent_generation_authoritative": False,
    }

    def transition(edge: str) -> dict:
        falling = edge == "falling"
        return {
            **target,
            "board_revision": 261 if falling else 265,
            "observed_at_ms": 261000 if falling else 265000,
            "facts_authoritative": True,
            "authority_gap_mask": 0,
            "personal_threat_present": not falling,
            "personal_threat_guid": 0 if falling else 91008,
            "prior_episode_open": falling,
            "new_episode_open": not falling,
            "edge": edge,
            "prior_task_generation": 5,
            "new_task_generation": 5 if falling else 6,
            "prior_candidate_generation": 6,
            "new_candidate_generation": 6 if falling else 7,
        }

    active = accepted_status()
    active["cohort_id"] = "raid"
    bot_rows = [{"bot_guid": 1001 + index} for index in range(10)]
    bot_rows[7]["diagnosis"] = {
        "magmaw_personal_parasite_escape": {
            "personal_threat_episode_transitions": [
                transition("falling"), transition("rising"),
            ],
        },
    }
    diagnosis = {
        "ok": True, "action": "botauto_diagnose", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"], "bots": bot_rows,
    }
    trace = {
        "ok": True, "action": "botauto_trace", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"],
        "bots": [
            {
                "bot_guid": 1001 + index,
                "entries": [],
                "delta": True,
                "cursor_before": 0,
                "cursor_after": 0,
                "gap": False,
            }
            for index in range(10)
        ],
    }
    readycheck = {
        "ok": True, "action": "botauto_readycheck", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"],
    }
    stop = {
        "ok": True, "action": "botauto_stop", "cohort_id": "raid",
        "server_epoch": 88, "attempt_id": 1,
        "raid_runtime_before_cleanup": active["raid_runtime"],
        "post_cleanup": {"active": False, "bots": 0, "lease_count": 0},
    }
    inactive = accepted_status()
    inactive["cohort_id"] = "raid"
    inactive.update(bots=0, lease_count=0, server_epoch=88, attempt_id=1)
    inactive["raid_runtime"]["active"] = False
    rows = normalized_batch_payload(
        b"\n".join(
            json.dumps(row).encode()
            for row in (active, diagnosis, trace, readycheck, stop, inactive)
        ) + b"\n"
    )
    return rows, target


def _personal_threat_episode_records(rows: list[dict]) -> list[dict]:
    diagnosis = next(
        row["payload"] for row in rows
        if row["payload"].get("action") == "botauto_diagnose"
    )
    return diagnosis["bots"][7]["diagnosis"][
        "magmaw_personal_parasite_escape"
    ]["personal_threat_episode_transitions"]


def test_public_demux_enforces_and_retains_requested_personal_threat_join():
    rows, target = _personal_threat_episode_demux_input()
    report = evidence_demux_report(
        rows, personal_threat_episode_target=target,
    )
    join = report["personal_threat_episode_join"]
    assert report["gate_passed"] is True
    assert join["gate_passed"] is True
    assert join["target"] == target
    assert [record["edge"] for record in join["records"]] == [
        "falling", "rising",
    ]

    ordinary = evidence_demux_report(
        json.loads(json.dumps(rows)),
    )
    assert ordinary["gate_passed"] is True
    assert ordinary["personal_threat_episode_join"] == {
        "requested": False,
        "records": [],
        "rejections": [],
        "gate_passed": True,
    }


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("missing", "magmaw_personal_threat_episode_complete_sequence_missing"),
        ("malformed", "magmaw_personal_threat_episode_record_missing_fields"),
        ("contradictory", "magmaw_personal_threat_episode_rising_contradiction"),
        ("cross_identity", "magmaw_personal_threat_episode_cross_scope"),
        ("non_authoritative", "magmaw_personal_threat_episode_record_non_authoritative"),
        ("nonmonotonic", "magmaw_personal_threat_episode_nonmonotonic"),
    ],
)
def test_public_demux_rejects_invalid_requested_personal_threat_join(
    mutation: str, expected_reason: str,
):
    rows, target = _personal_threat_episode_demux_input()
    records = _personal_threat_episode_records(rows)
    if mutation == "missing":
        records.pop()
    elif mutation == "malformed":
        del records[0]["observed_at_ms"]
    elif mutation == "contradictory":
        records[1]["prior_task_generation"] = 4
    elif mutation == "cross_identity":
        records[1]["scope_key"] = "other-scope"
    elif mutation == "non_authoritative":
        records[0]["facts_authoritative"] = False
    else:
        records[1]["board_revision"] = 260

    report = evidence_demux_report(
        rows, personal_threat_episode_target=target,
    )
    assert expected_reason in report["rejections"]
    assert report["personal_threat_episode_join"]["gate_passed"] is False
    assert report["gate_passed"] is False


def test_live_evidence_demux_binds_readycheck_stop_and_inactive_cleanup():
    active = accepted_status()
    active["cohort_id"] = "raid"
    bot_rows = [{"bot_guid": 1001 + index} for index in range(10)]
    diagnosis = {
        "ok": True, "action": "botauto_diagnose", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"], "bots": bot_rows,
    }
    trace_bot_rows = [
        {
            "bot_guid": 1001 + index,
            "entries": [],
            "delta": True,
            "cursor_before": 0,
            "cursor_after": 0,
            "gap": False,
        }
        for index in range(10)
    ]
    trace = {
        "ok": True, "action": "botauto_trace", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"], "bots": trace_bot_rows,
    }
    readycheck = {
        "ok": True, "action": "botauto_readycheck", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"],
    }
    stop = {
        "ok": True, "action": "botauto_stop", "cohort_id": "raid",
        "server_epoch": 88, "attempt_id": 1,
        "raid_runtime_before_cleanup": active["raid_runtime"],
        "post_cleanup": {"active": False, "bots": 0, "lease_count": 0},
    }
    inactive = accepted_status()
    inactive["cohort_id"] = "raid"
    inactive["bots"] = 0
    inactive["lease_count"] = 0
    inactive["server_epoch"] = 88
    inactive["attempt_id"] = 1
    inactive["raid_runtime"]["active"] = False
    rows = normalized_batch_payload(
        b"\n".join(
            json.dumps(row).encode()
            for row in (active, diagnosis, trace, readycheck, stop, inactive)
        ) + b"\n"
    )
    report = evidence_demux_report(rows)
    assert report["rejections"] == []
    assert report["bound_rows"] == report["retained_rows"] == 6
    assert report["rejected_rows"] == report["unchecked_rows"] == 0
    assert len(report["canonical_identity_sha256"]) == 64
    assert len(report["canonical_roster_sha256"]) == 64
    assert all(row["identity_binding"]["state"] == "bound" for row in rows)


def test_live_evidence_demux_rejects_empty_diagnose_and_trace_roster_envelopes():
    active = accepted_status()
    active["cohort_id"] = "raid"
    envelopes = []
    for action in ("botauto_diagnose", "botauto_trace"):
        envelopes.append({
            "ok": True, "action": action, "cohort_id": "raid",
            "raid_runtime": active["raid_runtime"], "bots": [],
        })
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (active, *envelopes)) + b"\n"
    )
    reasons = evidence_demux_rejections(rows)
    assert "evidence_demux_diagnosis_roster_empty" in reasons
    assert "evidence_demux_trace_roster_empty" in reasons


def test_live_evidence_demux_rejects_missing_and_duplicate_telemetry_bot_rows():
    active = accepted_status()
    active["cohort_id"] = "raid"
    missing = {
        "ok": True, "action": "botauto_diagnose", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"],
        "bots": [{"bot_guid": 1001 + index} for index in range(9)],
    }
    duplicate = {
        "ok": True, "action": "botauto_trace", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"],
        "bots": [{"bot_guid": 1001 + index} for index in range(9)] + [{"bot_guid": 1001}],
    }
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (active, missing, duplicate)) + b"\n"
    )
    reasons = evidence_demux_rejections(rows)
    assert "evidence_demux_diagnosis_canonical_roster_incomplete" in reasons
    assert "evidence_demux_diagnosis_bot_row_count_invalid" in reasons
    assert "evidence_demux_trace_duplicate_bot_guid" in reasons
    assert "evidence_demux_trace_canonical_roster_incomplete" in reasons


def test_live_evidence_demux_rejects_failed_telemetry_envelopes_with_full_roster():
    active = accepted_status()
    active["cohort_id"] = "raid"
    bot_rows = [{"bot_guid": 1001 + index} for index in range(10)]
    failed = []
    for action in ("botauto_diagnose", "botauto_trace"):
        failed.append({
            "ok": False, "action": action, "cohort_id": "raid",
            "raid_runtime": active["raid_runtime"], "bots": bot_rows,
            "failure_reason": "synthetic_channel_failure",
        })
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (active, *failed)) + b"\n"
    )
    reasons = evidence_demux_rejections(rows)
    assert "evidence_demux_diagnosis_envelope_not_ok" in reasons
    assert "evidence_demux_trace_envelope_not_ok" in reasons


def test_live_evidence_demux_rejects_unclassified_and_unbound_readycheck():
    active = accepted_status()
    active["cohort_id"] = "raid"
    rows = normalized_batch_payload(
        (json.dumps(active) + "\n" + json.dumps({"action": "unknown"}) + "\n").encode()
    )
    reasons = evidence_demux_rejections(rows)
    assert "evidence_demux_unclassified_row" in reasons
    assert "evidence_demux_cleanup_missing" in reasons


def test_live_evidence_demux_accepts_bound_terminal_without_readycheck():
    active = accepted_status()
    active["cohort_id"] = "default"
    active["active_profile"] = "blackwing_descent_10n"
    terminal = json.loads(json.dumps(active))
    terminal["failure_reason"] = "drudge_partial_death_before_threat_seed"
    terminal["raid_runtime"]["alive_size"] = 3
    bots = [{"bot_guid": 1001 + index} for index in range(10)]
    diagnosis = {
        "ok": True, "action": "botauto_diagnose", "cohort_id": "default",
        "failure_reason": terminal["failure_reason"],
        "raid_runtime": terminal["raid_runtime"], "bots": bots,
    }
    trace = {
        "ok": True, "action": "botauto_trace", "cohort_id": "default",
        "failure_reason": terminal["failure_reason"],
        "raid_runtime": terminal["raid_runtime"],
        "bots": [{"bot_guid": 1001 + index, "entries": [], "delta": True, "gap": False}
                 for index in range(10)],
    }
    profile = {
        "ok": True, "action": "botauto_profile", "cohort_id": "default",
        "active_profile": "blackwing_descent_10n",
    }
    stop = {
        "ok": True, "action": "botauto_stop", "cohort_id": "default",
        "server_epoch": 88, "attempt_id": 1,
        "raid_runtime_before_cleanup": terminal["raid_runtime"],
        "post_cleanup": {"active": False, "bots": 0, "lease_count": 0},
    }
    inactive = json.loads(json.dumps(terminal))
    inactive["active"] = False
    inactive["bots"] = 0
    inactive["lease_count"] = 0
    inactive["server_epoch"] = 88
    inactive["attempt_id"] = 1
    inactive["raid_runtime"]["active"] = False
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (
            profile, active, terminal, diagnosis, trace, stop, inactive,
        )) + b"\n"
    )

    report = evidence_demux_report(rows)

    assert "evidence_demux_required_action_missing:botauto_readycheck" not in report["rejections"]
    assert report["rejections"] == []
    assert report["gate_passed"] is True


def test_live_evidence_demux_accepts_controller_gameplay_terminals_without_readycheck():
    def build_rows():
        active = accepted_status()
        active["cohort_id"] = "default"
        active["active_profile"] = "blackwing_descent_10n"
        bots = [{"bot_guid": 1001 + index} for index in range(10)]
        diagnosis = {
            "ok": True, "action": "botauto_diagnose", "cohort_id": "default",
            "raid_runtime": active["raid_runtime"], "bots": bots,
        }
        trace_bots = [
            {
                "bot_guid": 1001 + index,
                "entries": [],
                "delta": True,
                "cursor_before": 0,
                "cursor_after": 0,
                "gap": False,
            }
            for index in range(10)
        ]
        trace = {
            "ok": True, "action": "botauto_trace", "cohort_id": "default",
            "raid_runtime": active["raid_runtime"], "bots": trace_bots,
        }
        stop = {
            "ok": True, "action": "botauto_stop", "cohort_id": "default",
            "server_epoch": 88, "attempt_id": 1,
            "raid_runtime_before_cleanup": active["raid_runtime"],
            "post_cleanup": {"active": False, "bots": 0, "lease_count": 0},
        }
        inactive = json.loads(json.dumps(active))
        inactive["active"] = False
        inactive["bots"] = 0
        inactive["lease_count"] = 0
        inactive["server_epoch"] = 88
        inactive["attempt_id"] = 1
        inactive["raid_runtime"]["active"] = False
        rows = normalized_batch_payload(
            b"\n".join(
                json.dumps(row).encode()
                for row in (
                    {"ok": True, "action": "botauto_profile", "cohort_id": "default",
                     "active_profile": "blackwing_descent_10n"},
                    active, diagnosis, trace, stop, inactive,
                )
            ) + b"\n"
        )
        return rows, active

    for reason in ("semantic_stall", "repeated_decision_watchdog", "death_loop_watchdog"):
        rows, terminal_status = build_rows()
        report = evidence_demux_report(
            rows,
            controller_terminal={
                "detected": True,
                "classification": "gameplay_failure",
                "failure_reason": reason,
                "terminal_status": terminal_status,
                "final_forced_evidence": True,
            },
        )
        assert report["rejections"] == []
        assert report["gate_passed"] is True

    rows, terminal_status = build_rows()
    drifted_status = json.loads(json.dumps(terminal_status))
    drifted_status["raid_runtime"]["attempt_id"] = 2
    report = evidence_demux_report(
        rows,
        controller_terminal={
            "detected": True,
            "classification": "gameplay_failure",
            "failure_reason": "semantic_stall",
            "terminal_status": drifted_status,
            "final_forced_evidence": True,
        },
    )
    assert "evidence_demux_controller_terminal_attempt_mismatch" in report["rejections"]
    assert "evidence_demux_required_action_missing:botauto_readycheck" in report["rejections"]


def test_live_evidence_demux_still_requires_readycheck_for_clear_run():
    active = accepted_status()
    active["cohort_id"] = "default"
    active["active_profile"] = "blackwing_descent_10n"
    bots = [{"bot_guid": 1001 + index} for index in range(10)]
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (
            {"ok": True, "action": "botauto_profile", "cohort_id": "default",
             "active_profile": "blackwing_descent_10n"},
            active,
            {"ok": True, "action": "botauto_diagnose", "cohort_id": "default",
             "raid_runtime": active["raid_runtime"], "bots": bots},
            {"ok": True, "action": "botauto_trace", "cohort_id": "default",
             "raid_runtime": active["raid_runtime"], "bots": bots},
            {"ok": True, "action": "botauto_stop", "cohort_id": "default",
             "server_epoch": 88, "attempt_id": 1,
             "raid_runtime_before_cleanup": active["raid_runtime"],
             "post_cleanup": {"active": False, "bots": 0, "lease_count": 0}},
            {"ok": True, "action": "botauto_status", "cohort_id": "default",
             "bots": 0, "lease_count": 0, "server_epoch": 88, "attempt_id": 1,
             "raid_runtime": {**active["raid_runtime"], "active": False}},
        )) + b"\n"
    )
    report = evidence_demux_report(rows)
    assert "evidence_demux_required_action_missing:botauto_readycheck" in report["rejections"]
    assert report["gate_passed"] is False


def _magmaw_fixture_demux_input():
    profile = "blackwing_descent_10n"
    actor = 30007
    fixture = "map669_magmaw_transfer_lane_authority_off_v1"
    case = "entrance_polygon_short_lane_v1"
    authority = "sealed_map669_transfer_lane_fixture_authority_off"
    hold_identity = {
        "cohort_id": "default", "server_epoch": 88, "attempt_id": 1,
        "scenario_id": profile, "runtime_profile": profile,
        "route_manifest_sha256": "a" * 64, "route_generation": 1,
        "route_node_id": "bwd.entry.regroup", "actor_guid": actor,
        "fixture_id": fixture, "seal_sha256": "b" * 64,
        "source_commit": "c" * 40,
    }
    comparison = {
        "accepted": True, "fixture_configured_present": True,
        "fixture_requested_present": True, "fixture_matches": True,
        "seal_configured_present": True, "seal_requested_present": True,
        "seal_matches": True, "source_configured_present": True,
        "source_requested_present": True, "source_matches": True,
        "binary_revision_present": True, "binary_revision_format_valid": True,
        "binary_revision_matches_source": True, "failure_field": "none",
        "configured_source_length": 40, "requested_source_length": 40,
        "binary_revision_length": 40,
    }

    def checkpoint(stage: str):
        completed = stage == "completed"
        lifecycle = {
            "stage": stage, "terminal": completed,
            "queue_count": 1 if completed else 0,
            "candidate_attempt_count": 1 if completed else 0,
            "native_submission_count": 1 if completed else 0,
            "planner_receipt_id": 7 if completed else 0,
            "progress_samples": 3 if completed else 0,
            "outcome": (
                "magmaw_transfer_checkpoint_completed" if completed
                else "magmaw_transfer_checkpoint_armed"
            ),
            "case_id": case,
        }
        hold = {
            **hold_identity, "ok": True,
            "phase": "checkpoint_terminal" if completed else "armed",
            "checkpoint_terminal": completed,
            "checkpoint_identity_preserved": completed,
            "checkpoint_stage": "completed" if completed else "disabled",
            "checkpoint_lifecycle": lifecycle,
            "config_identity_comparison": comparison,
        }
        return {
            "ok": True, "action": "botauto_magmaw_transfer_lane_checkpoint",
            "terminal_kind": "fixture_checkpoint",
            "certifies_gameplay_success": False,
            "certifies_boss_fidelity": False,
            "fixture_gate_passed": completed, "authority": authority,
            "fixture_id": fixture, "case_id": case, "actor_guid": actor,
            "task_authority_enabled": False, "episode_generation": 17,
            "task_generation": 31, "legacy_generation": 43,
            "scope_key": (
                "default:1:0:1:bwd.entry.regroup:669:42:"
                "magmaw_transfer_lane_checkpoint" if completed else ""
            ),
            "candidate_key": (
                "default:1:0:1:bwd.entry.regroup:669:42:"
                "magmaw_transfer_lane_checkpoint:adaptive_magmaw:"
                "pillar_bait_switch:GUID Full: 0x0000000000007537 "
                "Type: Player Low: 30007:43" if completed else ""
            ),
            "planner_candidate_key": (
                "default:1:0:1:bwd.entry.regroup:669:42:"
                "magmaw_transfer_lane_checkpoint:adaptive_magmaw:"
                "pillar_bait_switch:GUID Full: 0x0000000000007537 "
                "Type: Player Low: 30007:43" if completed else ""
            ),
            "stage": stage, "terminal": completed,
            "queue_count": lifecycle["queue_count"],
            "candidate_attempt_count": lifecycle["candidate_attempt_count"],
            "native_submission_count": lifecycle["native_submission_count"],
            "planner_receipt_id": lifecycle["planner_receipt_id"],
            "progress_samples": lifecycle["progress_samples"],
            "outcome": lifecycle["outcome"],
            "decreasing_progress_samples": 3 if completed else 0,
            "wrong_floor_samples": 0, "spline_id": 9 if completed else 0,
            "motion_master_slot": 1 if completed else 0,
            "motion_master_generator_type": 8 if completed else 0,
            "requested_destination": {
                "x": -345.872009, "y": -218.343994, "z": 193.126999,
            },
            "actor_start": {
                "x": -345.872009, "y": -224.343994, "z": 193.126999,
            },
            "actor_last_same_floor": {
                "x": -345.872009, "y": -218.343994, "z": 193.126999,
                "floor_z": 193.126999,
            },
            "task_state": "succeeded" if completed else "running",
            "controller_route_hold": hold,
        }

    active = accepted_status()
    active.update(cohort_id="default", active_profile=profile)
    active["raid_runtime"]["roster"][6]["guid"] = actor
    bots = [
        {"bot_guid": member["guid"]}
        for member in active["raid_runtime"]["roster"]
    ]
    diagnosis = {
        "ok": True, "action": "botauto_diagnose", "cohort_id": "default",
        "raid_runtime": active["raid_runtime"], "bots": bots,
    }
    trace = {
        "ok": True, "action": "botauto_trace", "cohort_id": "default",
        "raid_runtime": active["raid_runtime"],
        "bots": [
            {**bot, "entries": [], "delta": True, "gap": False}
            for bot in bots
        ],
    }
    terminal_response = checkpoint("completed")
    launch_hold = {
        **hold_identity, "ok": True, "action": "botauto_controller_route_hold",
        "native_action_inferred_from_exact_shape": True, "phase": "held",
    }
    stop = {
        "ok": True, "action": "botauto_stop", "cohort_id": "default",
        "server_epoch": 88, "attempt_id": 1,
        "raid_runtime_before_cleanup": active["raid_runtime"],
        "post_cleanup": {"active": False, "bots": 0, "lease_count": 0},
    }
    inactive = json.loads(json.dumps(active))
    inactive.update(bots=0, lease_count=0, server_epoch=88, attempt_id=1)
    inactive["raid_runtime"]["active"] = False
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (
            launch_hold, active, checkpoint("armed"), terminal_response,
            diagnosis, trace, stop, inactive,
        )) + b"\n"
    )
    terminal = {
        "detected": True, "classification": "fixture_terminal_observation",
        "terminal_kind": "magmaw_transfer_lane_checkpoint_terminal",
        "scheduler_phase": "complete", "stage": "completed",
        "outcome": "magmaw_transfer_checkpoint_completed",
        "success": False, "gate_passed": False, "fixture_gate_passed": True,
        "fixture_id": fixture, "case_id": case, "actor_guid": actor,
        "checkpoint_response": terminal_response,
        "final_forced_evidence": True,
        "final_forced_evidence_report": {"gate_passed": True},
    }
    expected = {
        "actor_guid": actor, "fixture_id": fixture, "case_id": case,
        "runtime_profile": profile, "scenario_id": profile,
        "route_manifest_sha256": "a" * 64, "seal_sha256": "b" * 64,
        "source_commit": "c" * 40,
    }
    return rows, terminal, expected


def test_fixture_checkpoint_demux_binds_transcript_and_waives_readycheck():
    rows, terminal, expected = _magmaw_fixture_demux_input()
    report = evidence_demux_report(
        rows, fixture_terminal=terminal, fixture_expected_identity=expected,
    )
    assert [row["evidence_channel"] for row in rows[2:4]] == [
        "controller_protocol", "controller_protocol",
    ]
    assert report["bound_rows"] == report["retained_rows"] == 8
    assert report["rejected_rows"] == report["unchecked_rows"] == 0
    assert report["rejections"] == []
    assert report["gate_passed"] is True


def test_fixture_checkpoint_demux_rejects_action_only_or_unretained_terminal():
    rows, terminal, expected = _magmaw_fixture_demux_input()
    action_only = evidence_demux_report(json.loads(json.dumps(rows)))
    assert "evidence_demux_fixture_terminal_missing" in action_only["rejections"]
    assert "evidence_demux_required_action_missing:botauto_readycheck" in action_only["rejections"]

    forged = json.loads(json.dumps(terminal))
    forged["checkpoint_response"]["spline_id"] = 999
    report = evidence_demux_report(
        json.loads(json.dumps(rows)), fixture_terminal=forged,
        fixture_expected_identity=expected,
    )
    assert "evidence_demux_fixture_terminal_response_unretained" in report["rejections"]
    assert report["gate_passed"] is False


def test_fixture_checkpoint_demux_rejects_cross_identity_and_authority_drift():
    for path, value in (
        (("payload", "actor_guid"), 9999),
        (("payload", "authority"), "wrong"),
        (("payload", "task_authority_enabled"), True),
        (("payload", "controller_route_hold", "source_commit"), "d" * 40),
        (("payload", "controller_route_hold", "seal_sha256"), "e" * 64),
        (("payload", "controller_route_hold", "route_manifest_sha256"), "f" * 64),
        (("payload", "controller_route_hold", "runtime_profile"), "wrong"),
        (("payload", "controller_route_hold", "attempt_id"), 2),
        (("payload", "controller_route_hold", "server_epoch"), 89),
    ):
        rows, terminal, expected = _magmaw_fixture_demux_input()
        target = rows[2]
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        report = evidence_demux_report(
            rows, fixture_terminal=terminal, fixture_expected_identity=expected,
        )
        assert report["gate_passed"] is False, path


def test_fixture_checkpoint_demux_rejects_coherent_identity_and_candidate_forgery():
    for field, value in (
        ("route_manifest_sha256", "d" * 64),
        ("seal_sha256", "e" * 64),
        ("source_commit", "f" * 40),
        ("runtime_profile", "coherently_forged_profile"),
    ):
        rows, terminal, expected = _magmaw_fixture_demux_input()
        for row in rows:
            payload = row["payload"]
            hold = (
                payload if payload.get("action") == "botauto_controller_route_hold"
                else payload.get("controller_route_hold")
            )
            if isinstance(hold, dict):
                hold[field] = value
        terminal["checkpoint_response"]["controller_route_hold"][field] = value
        report = evidence_demux_report(
            rows, fixture_terminal=terminal, fixture_expected_identity=expected,
        )
        assert "evidence_demux_fixture_expected_identity_mismatch" in report["rejections"]

    rows, terminal, expected = _magmaw_fixture_demux_input()
    for row in rows:
        payload = row["payload"]
        if payload.get("action") == "botauto_magmaw_transfer_lane_checkpoint":
            payload["actor_guid"] = 30006
            payload["controller_route_hold"]["actor_guid"] = 30006
        bots = payload.get("bots")
        if isinstance(bots, list):
            for bot in bots:
                if bot.get("bot_guid") == 30007:
                    bot["bot_guid"] = 30006
        roster = (payload.get("raid_runtime") or {}).get("roster")
        if isinstance(roster, list):
            for member in roster:
                if member.get("guid") == 30007:
                    member["guid"] = 30006
    rows[0]["payload"]["actor_guid"] = 30006
    terminal["actor_guid"] = 30006
    terminal["checkpoint_response"]["actor_guid"] = 30006
    terminal["checkpoint_response"]["controller_route_hold"]["actor_guid"] = 30006
    report = evidence_demux_report(
        rows, fixture_terminal=terminal, fixture_expected_identity=expected,
    )
    assert "evidence_demux_fixture_terminal_identity_mismatch" in report["rejections"]

    rows, terminal, expected = _magmaw_fixture_demux_input()
    forged = terminal["checkpoint_response"]["scope_key"] + ":forged"
    for row in rows:
        payload = row["payload"]
        if payload.get("candidate_key"):
            payload["candidate_key"] = forged
            payload["planner_candidate_key"] = forged
    terminal["checkpoint_response"]["candidate_key"] = forged
    terminal["checkpoint_response"]["planner_candidate_key"] = forged
    report = evidence_demux_report(
        rows, fixture_terminal=terminal, fixture_expected_identity=expected,
    )
    assert "evidence_demux_fixture_terminal_identity_mismatch" in report["rejections"]


def test_fixture_checkpoint_demux_rejects_forced_evidence_and_bad_ordering():
    rows, terminal, expected = _magmaw_fixture_demux_input()
    terminal["final_forced_evidence"] = False
    assert evidence_demux_report(
        rows, fixture_terminal=terminal, fixture_expected_identity=expected,
    )["gate_passed"] is False

    rows, terminal, expected = _magmaw_fixture_demux_input()
    terminal_row = rows.pop(3)
    rows.insert(7, terminal_row)
    for sequence, row in enumerate(rows, start=1):
        row["capture_sequence"] = sequence
    report = evidence_demux_report(
        rows, fixture_terminal=terminal, fixture_expected_identity=expected,
    )
    assert "evidence_demux_fixture_terminal_order_invalid" in report["rejections"]
    assert report["gate_passed"] is False


def test_fixture_checkpoint_demux_rejects_nonmonotonic_lifecycle():
    rows, terminal, expected = _magmaw_fixture_demux_input()
    queued = json.loads(json.dumps(rows[2]))
    queued["capture_sequence"] = 4
    queued["payload"]["stage"] = "queued"
    queued["payload"]["queue_count"] = 1
    queued["payload"]["controller_route_hold"]["checkpoint_lifecycle"].update(
        stage="queued", queue_count=1,
    )
    rows[3]["capture_sequence"] = 5
    rows.insert(3, queued)
    for sequence, row in enumerate(rows, start=1):
        row["capture_sequence"] = sequence
    rows[4]["payload"]["queue_count"] = 0
    rows[4]["payload"]["controller_route_hold"]["checkpoint_lifecycle"]["queue_count"] = 0
    terminal["checkpoint_response"] = rows[4]["payload"]
    report = evidence_demux_report(
        rows, fixture_terminal=terminal, fixture_expected_identity=expected,
    )
    assert "evidence_demux_fixture_checkpoint_lifecycle_nonmonotonic" in report["rejections"]
    assert report["gate_passed"] is False


def test_fixture_checkpoint_demux_enforces_observed_stage_counts():
    rows, terminal, expected = _magmaw_fixture_demux_input()
    rows[2]["payload"]["queue_count"] = 1
    rows[2]["payload"]["controller_route_hold"]["checkpoint_lifecycle"]["queue_count"] = 1
    report = evidence_demux_report(
        rows, fixture_terminal=terminal, fixture_expected_identity=expected,
    )
    assert "evidence_demux_fixture_checkpoint_stage_counts_invalid" in report["rejections"]

    rows, terminal, expected = _magmaw_fixture_demux_input()
    queued = json.loads(json.dumps(rows[2]))
    queued["payload"].update(
        stage="queued", queue_count=1, candidate_attempt_count=1,
        native_submission_count=0,
        scope_key=terminal["checkpoint_response"]["scope_key"],
        candidate_key=terminal["checkpoint_response"]["candidate_key"],
        planner_candidate_key="",
    )
    queued["payload"]["controller_route_hold"]["checkpoint_lifecycle"].update(
        stage="queued", queue_count=1, candidate_attempt_count=1,
        native_submission_count=0,
    )
    rows.insert(3, queued)
    for sequence, row in enumerate(rows, start=1):
        row["capture_sequence"] = sequence
    report = evidence_demux_report(
        rows, fixture_terminal=terminal, fixture_expected_identity=expected,
    )
    assert "evidence_demux_fixture_checkpoint_stage_counts_invalid" in report["rejections"]


def test_fixture_checkpoint_offline_audit_binds_input_hashes(tmp_path: Path):
    from tools.raid_program.audit_retained_evidence_demux import offline_demux_audit

    rows, terminal, expected = _magmaw_fixture_demux_input()
    raw = tmp_path / "capture_raw.jsonl"
    report = tmp_path / "capture_report.json"
    raw_bytes = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for row in rows
    )
    capture_report = {
        "runtime_profile": "blackwing_descent_10n",
        "scenario_id": "blackwing_descent_10n",
        "fixture_terminal": terminal,
        "identity": {
            "clean": True, "dirty": False, "head": expected["source_commit"],
        },
        "build_provenance": {"valid": True, "commit": expected["source_commit"]},
        "runtime_profile_assets": {
            "passed": True, "profile_name": expected["runtime_profile"],
            "scenario_id": expected["scenario_id"],
        },
        "recurrence_admission": {
            "valid": True, "source_commit": expected["source_commit"],
            "checkpoint_fixture_id": expected["fixture_id"],
            "checkpoint_case_id": expected["case_id"],
            "checkpoint_seal_sha256": expected["seal_sha256"],
            "expected_runtime_profile_id": expected["runtime_profile"],
            "bindings": {"route_manifest": {
                "sha256": expected["route_manifest_sha256"],
            }},
            "runtime_profile_overlay": {
                "runtime_route_manifest_sha256": expected["route_manifest_sha256"],
            },
        },
        "controller_route_hold": {
            "gate_passed": True,
            "launch_identity": {
                **expected, "source_commit": expected["source_commit"],
            },
        },
    }
    report_bytes = json.dumps(capture_report, sort_keys=True).encode()
    raw.write_bytes(raw_bytes)
    report.write_bytes(report_bytes)
    audit = offline_demux_audit(
        raw, report,
        expected_raw_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        expected_report_sha256=hashlib.sha256(report_bytes).hexdigest(),
        expected_actor_guid=expected["actor_guid"],
        expected_source_commit=expected["source_commit"],
        expected_route_sha256=expected["route_manifest_sha256"],
        expected_seal_sha256=expected["seal_sha256"],
        expected_profile=expected["runtime_profile"],
    )
    assert audit["raw_normalized_sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert audit["capture_report_sha256"] == hashlib.sha256(report_bytes).hexdigest()
    assert audit["demux"]["gate_passed"] is True
    try:
        offline_demux_audit(
            raw, report, expected_raw_sha256="0" * 64,
            expected_report_sha256=hashlib.sha256(report_bytes).hexdigest(),
            expected_actor_guid=expected["actor_guid"],
            expected_source_commit=expected["source_commit"],
            expected_route_sha256=expected["route_manifest_sha256"],
            expected_seal_sha256=expected["seal_sha256"],
            expected_profile=expected["runtime_profile"],
        )
    except ValueError as error:
        assert str(error) == "offline_demux_input_sha256_mismatch"
    else:
        raise AssertionError("offline audit admitted an unexpected raw hash")


def test_live_evidence_demux_reconstructs_bindings_and_rejects_missing_lifecycle_identity():
    active = accepted_status()
    active["cohort_id"] = "raid"
    missing_runtime = {
        "ok": False, "action": "botauto_readycheck", "cohort_id": "raid",
        "failure_reason": "not_ready",
    }
    bad_stop = {
        "ok": True, "action": "botauto_stop", "cohort_id": "raid",
        "server_epoch": 88, "attempt_id": 1,
        "post_cleanup": {"active": False, "bots": 0, "lease_count": 0},
    }
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (active, missing_runtime, bad_stop)) + b"\n"
    )
    rows[0]["identity_binding"] = {"state": "bound", "canonical_identity_sha256": "0" * 64}
    report = evidence_demux_report(rows)
    assert "evidence_demux_identity_missing" in report["rejections"]
    assert report["rejected_rows"] == 2
    assert report["unchecked_rows"] == 0
    assert rows[0]["identity_binding"]["canonical_identity_sha256"] != "0" * 64


def test_canonical_capture_uses_receipt_bound_tracked_policy_without_an_override():
    source = (
        Path(__file__).resolve().parents[1]
        / "tools/raid_program/capture_setup.py"
    ).read_text(encoding="utf-8")
    assert 'parser.add_argument("--build-policy"' not in source
    assert "build_policy_path_for_receipt" in source
    assert 'parser.add_argument("--build-attestation"' in source


def test_generic_profile_range_capture_arguments_are_explicit_and_admission_bound():
    parser = build_capture_parser()
    args = parser.parse_args([
        "--binary", "/tmp/worldserver",
        "--config", "/tmp/worldserver.conf",
        "--output", "/tmp/capture.json",
        "--build-receipt", "/tmp/build.json",
        "--profile-combat-range-checkpoint-actor-guid", "30010",
        "--profile-combat-range-checkpoint-target-guid", "39",
        "--fixture-expansion-replay",
        "--scenario-id", "blackwing_descent_10n_magmaw_diagnostic",
        "--runtime-profile", "blackwing_descent_10n_magmaw_diagnostic",
    ])
    assert args.profile_combat_range_checkpoint_actor_guid == 30010
    assert args.profile_combat_range_checkpoint_target_guid == 39
    source = (
        Path(__file__).resolve().parents[1]
        / "tools/raid_program/capture_setup.py"
    ).read_text(encoding="utf-8")
    assert "profile_combat_range_checkpoint_identity_mismatch" in source
    assert "checkpoint_target_guid = recurrence_admission.get(" in source


def test_build_policy_path_is_bound_to_receipt_identity(tmp_path):
    worktree = tmp_path / "worktree"
    policies = worktree / "experiments/configs"
    policies.mkdir(parents=True)
    policy_id = "cata_raid_build_resource_policy_fast8_v1"
    policy_path = policies / f"{policy_id}.json"
    policy_path.write_text(json.dumps({"policy_id": policy_id}), encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"policy_id": policy_id}), encoding="utf-8")

    assert build_policy_path_for_receipt(receipt, worktree) == policy_path.resolve()


def test_build_policy_path_rejects_untracked_or_unsafe_receipt_identity(tmp_path):
    worktree = tmp_path / "worktree"
    (worktree / "experiments/configs").mkdir(parents=True)
    receipt = tmp_path / "receipt.json"

    receipt.write_text(json.dumps({"policy_id": "../../outside"}), encoding="utf-8")
    try:
        build_policy_path_for_receipt(receipt, worktree)
    except RuntimeError as error:
        assert "policy ID is invalid" in str(error)
    else:
        raise AssertionError("unsafe policy identity was accepted")

    receipt.write_text(json.dumps({"policy_id": "cata_raid_build_resource_policy_missing_v1"}), encoding="utf-8")
    try:
        build_policy_path_for_receipt(receipt, worktree)
    except RuntimeError as error:
        assert "not tracked" in str(error)
    else:
        raise AssertionError("untracked policy identity was accepted")


def test_canonical_capture_is_terminal_gate_driven_without_a_raid_duration_cap():
    root = Path(__file__).resolve().parents[1] / "tools/raid_program"
    setup_source = (root / "capture_setup.py").read_text(encoding="utf-8")
    live_source = (root / "capture_live_run.py").read_text(encoding="utf-8")
    finalization_source = (root / "capture_finalization.py").read_text(encoding="utf-8")
    assert '"--observe-sec", type=int, default=0' in setup_source
    assert 'parser.add_argument("--semantic-stall-sec", type=int, default=300)' in setup_source
    assert 'parser.add_argument("--telemetry-timeout-sec", type=int, default=60)' in setup_source
    assert '"--diagnose-interval-sec", type=float, default=30.0,' in setup_source
    assert '"--trace-interval-sec", type=float, default=10.0,' in setup_source
    assert "deadline = time.monotonic() + args.observe_sec if args.observe_sec else None" in live_source
    assert "deadline is None or time.monotonic() < deadline" in live_source
    assert '"wall_clock_mode": "uncapped" if args.observe_sec == 0' in finalization_source
    assert '"policy": "capture-process-heartbeat-terminal-gate-driven"' in finalization_source
    assert "capture_classification = _capture_classification(" in finalization_source


def test_phase1_capture_uses_approved_fail_closed_taxonomy():
    root = Path(__file__).resolve().parents[1] / "tools/raid_program"
    taxonomy_source = (root / "capture_run_outcome.py").read_text(encoding="utf-8")
    finalization_source = (root / "capture_finalization.py").read_text(encoding="utf-8")
    assert 'return "incomplete_evidence"' in taxonomy_source
    assert 'return "diagnostic_only"' in taxonomy_source
    assert 'return "infrastructure_abort"' in taxonomy_source
    for condition in (
        "process_return_code != 0",
        "not identity_stable",
    ):
        assert condition in finalization_source
    assert "or demux_rejections" in taxonomy_source
    assert 'telemetry_envelopes.get("gate_passed") is not True' in taxonomy_source
    assert '"foundation_gate_failed"' not in taxonomy_source
    assert '"foundation_gate_failed"' not in finalization_source


def test_gameplay_terminal_preserves_primary_classification_when_trace_evidence_is_incomplete():
    terminal_failure = {
        "detected": True,
        "classification": "gameplay_failure",
        "failure_reason": "death_loop_watchdog",
    }
    forced_evidence = {
        "gate_passed": False,
        "missing_channels": ["trace"],
        "rejections": ["trace:forced_response_trace_delta_gap"],
    }
    telemetry_abort = {
        "detected": True,
        "classification": "infrastructure_abort",
        "reason": "terminal_failure_forced_evidence_incomplete",
    }
    telemetry_envelopes = {
        "gate_passed": False,
        "rejections": ["evidence_demux_trace_delta_gap"],
    }
    demux_rejections = [
        "evidence_demux_controller_terminal_forced_evidence_missing",
        "evidence_demux_trace_delta_gap",
        "evidence_demux_required_action_missing:botauto_readycheck",
    ]

    assert _primary_gameplay_terminal(terminal_failure, {"detected": False}) is True
    assert _terminal_evidence_incomplete(
        primary_gameplay_failure=True,
        forced_evidence_report=forced_evidence,
        telemetry_abort=telemetry_abort,
        telemetry_envelopes=telemetry_envelopes,
        demux_rejections=demux_rejections,
    ) is True
    # Evidence remains fail-closed for non-gameplay captures; the annotation
    # never turns a missing terminal bundle into a gameplay result by itself.
    assert _terminal_evidence_incomplete(
        primary_gameplay_failure=False,
        forced_evidence_report=forced_evidence,
        telemetry_abort=telemetry_abort,
        telemetry_envelopes=telemetry_envelopes,
        demux_rejections=demux_rejections,
    ) is False
    assert _capture_classification(
        success=False,
        forbidden_entries=[],
        primary_gameplay_failure=True,
        operational_infrastructure_abort=False,
        evidence_incomplete=True,
    ) == "gameplay_failure"
    assert _capture_classification(
        success=False,
        forbidden_entries=[],
        primary_gameplay_failure=True,
        operational_infrastructure_abort=True,
        evidence_incomplete=True,
    ) == "infrastructure_abort"
    assert _capture_classification(
        success=False,
        forbidden_entries=[],
        primary_gameplay_failure=False,
        operational_infrastructure_abort=False,
        evidence_incomplete=True,
    ) == "infrastructure_abort"

    source = (
        Path(__file__).resolve().parents[1]
        / "tools/raid_program/capture_finalization.py"
    ).read_text(encoding="utf-8")
    success = source[source.index("common_success = ("):source.index("report = {")]
    assert "capture_classification = _capture_classification(" in source
    assert '"terminal_evidence_incomplete": terminal_evidence_incomplete' in source
    assert "and not demux_rejections" in success
    assert 'and telemetry_envelopes["gate_passed"]' in success
    assert 'and forced_evidence_report.get("gate_passed") is True' in success


def test_capture_interrupt_is_native_cleanup_backed_and_classified_without_traceback():
    root = Path(__file__).resolve().parents[1] / "tools/raid_program"
    live_source = (root / "capture_live_run.py").read_text(encoding="utf-8")
    shutdown_source = (root / "capture_runtime_io.py").read_text(encoding="utf-8")
    finalization_source = (root / "capture_finalization.py").read_text(encoding="utf-8")
    assert "except KeyboardInterrupt:" in live_source
    assert 'startup_error = "KeyboardInterrupt:operator_interrupt"' in live_source
    assert 'process.stdin.write(b"botauto stop\\nbotauto status\\nserver exit\\n")' in shutdown_source
    assert '"operator_interrupt": operator_interrupt' in finalization_source
    assert '"operator_reason": "operator_interrupt" if operator_interrupt else None' in finalization_source
    assert 'forced_evidence_report = request_final_evidence("operator_interrupt")' in live_source
    assert 'signal.signal(signal.SIGINT, signal.SIG_IGN)' in live_source
    # The explicit handler must appear before the generic Exception handler;
    # otherwise Ctrl-C remains an uncaught BaseException.
    assert live_source.index("except KeyboardInterrupt:") < live_source.index(
        "except Exception as error:  # captured as infrastructure evidence below"
    )


def test_every_terminal_capture_path_requests_a_fresh_full_evidence_bundle():
    root = Path(__file__).resolve().parents[1] / "tools/raid_program"
    source = (root / "capture_live_run.py").read_text(encoding="utf-8")
    finalization_source = (root / "capture_finalization.py").read_text(encoding="utf-8")
    for reason in (
        '"telemetry_channel_stale"',
        '"terminal_gate_or_process_exit"',
        '"operator_interrupt"',
        '"capture_exception"',
    ):
        assert reason in source
    assert source.count("request_final_evidence(") >= 5
    success = finalization_source[
        finalization_source.index("common_success = ("):
        finalization_source.index("report = {")
    ]
    assert "operator_interrupt is False" in success
    assert 'forced_evidence_report.get("gate_passed") is True' in success
    assert "capture_classification = _capture_classification(" in finalization_source
    assert "operational_infrastructure_abort = bool(" in finalization_source
    assert "evidence_incomplete = bool(" in finalization_source
    post_capture = source[source.index("def defer_post_capture_interrupt"):]
    assert "nonlocal operator_interrupt, startup_error" in post_capture
    assert 'startup_error = "KeyboardInterrupt:operator_interrupt"' in post_capture
    assert "signal.signal(signal.SIGINT, defer_post_capture_interrupt)" in post_capture
    assert finalization_source.index("signal.signal(signal.SIGINT, signal.SIG_IGN)") > (
        finalization_source.index(
            "normalized_rows = normalized_batch_payload(log_bytes, profile_name=profile_name)"
        )
    )
    watchdog = finalization_source[
        finalization_source.index('"watchdog": {'):
        finalization_source.index('"preflight": preflight')
    ]
    assert "operator_interrupt is False" in watchdog
    assert 'forced_evidence_report.get("gate_passed") is True' in watchdog


def test_uncapped_capture_fails_closed_when_any_telemetry_channel_is_stale():
    state = {}
    assert observe_telemetry_freshness(
        state, {"status": 1, "diagnosis": 1, "trace": 1}, 100.0, 30.0,
    ) == []
    assert observe_telemetry_freshness(
        state, {"status": 2, "diagnosis": 2, "trace": 1}, 125.0, 30.0,
    ) == []
    assert observe_telemetry_freshness(
        state, {"status": 3, "diagnosis": 3, "trace": 1}, 131.0, 30.0,
    ) == ["trace"]
    assert observe_telemetry_freshness(
        state, {"status": 3, "diagnosis": 3, "trace": 2}, 132.0, 30.0,
    ) == []


def test_semantic_progress_signature_tracks_boss_and_bot_decisions_not_heartbeats():
    status = accepted_status()
    status["duration_seconds"] = 1
    diagnosis = {
        "bots": [{
            "identity": {"bot_guid": 1001},
            "snapshot": {
                "decision": {"action": "attack", "result": "ok", "reason": "boss"},
                "route_progress": {"target": {"guid": 9001, "hp_pct": 75.0}},
            },
        }],
    }
    status["deaths"] = 0
    baseline = semantic_progress_signature(status, diagnosis)
    status["duration_seconds"] = 999
    assert semantic_progress_signature(status, diagnosis) == baseline
    status["deaths"] += 99
    assert semantic_progress_signature(status, diagnosis) == baseline
    status["raid_runtime"].update(
        alive_size=2,
        wipe_state="partial_deaths",
        recovery_state="runback",
        wipe_generation=4,
        boss_reset_generation=8,
        recovery_generation=12,
        assignment_generation=99,
        encounter_in_progress=True,
    )
    status["instance_resets"] = 99
    diagnosis["bots"][0]["snapshot"]["route_progress"]["state"] = {
        "victim_guid": 7777,
        "bot_in_combat": True,
        "bot_casting": True,
    }
    assert semantic_progress_signature(status, diagnosis) == baseline
    status["raid_runtime"]["encounter_in_progress"] = False
    status["raid_runtime"]["assignment_generation"] = 100
    assert semantic_progress_signature(status, diagnosis) == baseline
    diagnosis["bots"][0]["snapshot"]["decision"]["action"] = "different_wrong_action"
    assert semantic_progress_signature(status, diagnosis) == baseline
    diagnosis["bots"][0]["snapshot"]["route_progress"]["target"]["hp_pct"] = 74.0
    assert semantic_progress_signature(status, diagnosis) != baseline


def test_watchdog_and_progress_are_reexported_from_focused_production_modules():
    assert semantic_progress_signature.__module__ == "tools.raid_program.capture_progress"
    assert observe_monotonic_semantic_progress.__module__ == "tools.raid_program.capture_progress"
    assert ready_for_native_readycheck.__module__ == "tools.raid_program.capture_progress"
    assert observe_capture_watchdog.__module__ == "tools.raid_program.capture_watchdog"


def test_monotonic_semantic_progress_rejects_cast_victim_and_hp_oscillation():
    status = accepted_status()
    status["validation_route"] = {"generation": 1, "manifest_index": 1}
    diagnosis = {
        "bots": [{
            "identity": {"bot_guid": 1001},
            "snapshot": {"route_progress": {
                "target": {"guid": 9001, "entry": 41570, "hp_pct": 75.0, "best_hp_pct": 75.0},
                "state": {"victim_guid": 9001, "bot_casting": False},
            }},
        }],
    }
    status["deaths"] = 0
    status["raid_runtime"]["encounter_phase"] = "combat"
    state = {}
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is True
    diagnosis["bots"][0]["snapshot"]["route_progress"]["state"] = {
        "victim_guid": 9002, "bot_casting": True,
    }
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    status["deaths"] += 1
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    diagnosis["bots"][0]["snapshot"]["route_progress"]["target"]["guid"] = 9002
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    status["raid_runtime"]["encounter_phase"] = "impaled"
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is True
    status["raid_runtime"]["encounter_phase"] = "combat"
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    diagnosis["bots"][0]["snapshot"]["route_progress"]["target"].update(
        hp_pct=80.0, best_hp_pct=80.0,
    )
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    diagnosis["bots"][0]["snapshot"]["route_progress"]["target"].update(
        hp_pct=74.0, best_hp_pct=74.0,
    )
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is True
    status["raid_runtime"]["wipe_generation"] += 1
    status["raid_runtime"]["boss_reset_generation"] += 1
    status["raid_runtime"]["recovery_generation"] += 1
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    status["raid_runtime"]["boss_reset_generation"] += 1
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    status["raid_runtime"]["native_recovery"].update(
        death_observed=True,
        corpse_observed=True,
        release_observed=True,
    )
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    status["raid_runtime"]["evidence_sequence"] = 80
    status["raid_runtime"]["native_recovery"].update(
        runback_observed=True,
        resurrection_observed=True,
        ready_check_action_observed=True,
        evidence_complete=True,
        recovery_wipe_generation=status["raid_runtime"]["wipe_generation"],
        ready_check_action_generation=2,
        ready_check_response_count=10,
        ready_check_action_attempt_id=status["raid_runtime"]["attempt_id"],
        ready_check_action_wipe_generation=status["raid_runtime"]["wipe_generation"],
        ready_check_assignment_generation=status["raid_runtime"]["assignment_generation"],
        ready_check_action_evidence_sequence=80,
        members=[
            {
                "guid": 1001 + index,
                "wipe_generation": status["raid_runtime"]["wipe_generation"],
                "death_sequence": 10 + index * 6,
                "corpse_sequence": 11 + index * 6,
                "release_sequence": 12 + index * 6,
                "runback_sequence": 13 + index * 6,
                "reentry_sequence": 14 + index * 6,
                "resurrection_sequence": 15 + index * 6,
            }
            for index in range(10)
        ],
    )
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    assert state["accepted_native_recovery_scopes"]
    status["raid_runtime"]["recovery_generation"] += 1
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    status["raid_runtime"]["boss_reset_generation"] += 1
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False


def test_monotonic_semantic_progress_uses_increasing_originated_party_damage_only():
    status = accepted_status()
    status["validation_route"] = {
        "node_id": "bwd.magmaw.encounter",
        "generation": 4,
        "manifest_index": 3,
    }

    def diagnosis_for(
        party_damage: int,
        *,
        route_generation: int = 4,
        route_node_id: str = "bwd.magmaw.encounter",
        measurement_basis: str = "originated_damage",
        party_healing: int = 0,
        raw_event_damage: int = 0,
    ) -> dict:
        return {
            "combat_metrics": {
                "schema": "bot_combat_metrics_v2",
                "measurement_basis": measurement_basis,
                "route_generation": route_generation,
                "route_node_id": route_node_id,
                "party_damage": party_damage,
                "party_healing": party_healing,
                "raw_event_damage": raw_event_damage,
            },
        }

    state = {}
    assert observe_monotonic_semantic_progress(
        state, status, diagnosis_for(0),
    ) is True
    assert observe_monotonic_semantic_progress(
        state, status, diagnosis_for(50),
    ) is True
    # Healing, recovery counters, and duplicated/raw callback totals do not
    # reset the watchdog when originated damage is unchanged.
    status["raid_runtime"]["recovery_generation"] += 1
    assert observe_monotonic_semantic_progress(
        state, status, diagnosis_for(
            50, party_healing=10000, raw_event_damage=100000,
        ),
    ) is False
    assert observe_monotonic_semantic_progress(
        state, status, diagnosis_for(40),
    ) is False
    assert observe_monotonic_semantic_progress(
        state, status, diagnosis_for(0),
    ) is False


def test_monotonic_semantic_progress_rejects_unscoped_or_raw_party_damage():
    status = accepted_status()
    status["validation_route"] = {
        "node_id": "bwd.magmaw.encounter",
        "generation": 4,
        "manifest_index": 3,
    }

    def diagnosis_for(
        party_damage: int,
        *,
        route_generation: int = 4,
        route_node_id: str = "bwd.magmaw.encounter",
        measurement_basis: str = "originated_damage",
    ) -> dict:
        return {
            "combat_metrics": {
                "schema": "bot_combat_metrics_v2",
                "measurement_basis": measurement_basis,
                "route_generation": route_generation,
                "route_node_id": route_node_id,
                "party_damage": party_damage,
            },
        }

    state = {}
    assert observe_monotonic_semantic_progress(
        state, status, diagnosis_for(0),
    ) is True
    # A value from another route generation/node, or a raw-event metric, must
    # never become this route's high-water mark.
    assert observe_monotonic_semantic_progress(
        state, status, diagnosis_for(1000, route_generation=3),
    ) is False
    assert observe_monotonic_semantic_progress(
        state, status, diagnosis_for(1000, route_node_id="bwd.magmaw.drudges"),
    ) is False
    assert observe_monotonic_semantic_progress(
        state, status, diagnosis_for(1000, measurement_basis="raw_event_damage"),
    ) is False
    assert observe_monotonic_semantic_progress(
        state, status, diagnosis_for(25),
    ) is True


def _watchdog_status() -> dict:
    status = accepted_status()
    runtime = status["raid_runtime"]
    runtime["admission_receipt"] = {
        "entrance_map_id": runtime["map_id"],
        "members": [{"guid": row["guid"]} for row in runtime["roster"]],
    }
    status["cohort_id"] = "default"
    status["active_profile"] = "blackwing_descent_10n"
    status["validation_route"] = {
        "node_id": "bwd.magmaw.drudges",
        "generation": 3,
        "manifest_index": 2,
        "terminal_evidence": [],
    }
    return status


def _generic_watchdog_status(*, size: int, profile: str, map_id: int) -> dict:
    roster = [
        {"slot": slot, "guid": 2000 + slot, "active": True, "lease_owned": True}
        for slot in range(size)
    ]
    return {
        "ok": True,
        "action": "botauto_status",
        "cohort_id": "default",
        "active_profile": profile,
        "bots": size,
        "lease_count": size,
        "validation_route": {
            "node_id": f"{profile}.node",
            "generation": 1,
            "map_id": map_id,
        },
        "raid_runtime": {
            "active": True,
            "expected_size": size,
            "active_size": size,
            "roster_complete": True,
            "map_id": map_id,
            "instance_id": 42,
            "attempt_id": 1,
            "assignment_generation": 1,
            "unique_leases": True,
            "leader_guid": roster[0]["guid"],
            "strategy_id": f"{profile}.initial",
            "roster": roster,
            "admission_receipt": {
                "entrance_map_id": map_id,
                "members": [{"guid": row["guid"]} for row in roster],
            },
        },
    }


def test_capture_watchdog_arms_for_bwd_raid_and_dungeon_roster_sizes():
    for size, profile, map_id in (
        (10, "blackwing_descent_10n", 669),
        (25, "blackwing_descent_25n", 669),
        (5, "stonecore_5h", 725),
    ):
        report = observe_capture_watchdog(
            {}, _generic_watchdog_status(size=size, profile=profile, map_id=map_id), None,
            profile_name=profile,
        )
        assert report["detected"] is False
        assert report["rejections"] == []


def test_capture_watchdog_fails_closed_for_roster_map_and_profile_mismatch():
    cases = (
        ("watchdog_roster_admission_identity_mismatch", "roster"),
        ("watchdog_map_mismatch", "map"),
        ("watchdog_profile_mismatch", "profile"),
    )
    for expected_reason, mismatch in cases:
        status = _generic_watchdog_status(size=25, profile="blackwing_descent_25n", map_id=669)
        if mismatch == "roster":
            status["raid_runtime"]["roster"][0]["guid"] += 1
        elif mismatch == "map":
            status["raid_runtime"]["map_id"] = 725
        else:
            status["active_profile"] = "stonecore_5h"
        report = observe_capture_watchdog({}, status, None, profile_name="blackwing_descent_25n")
        assert report["detected"] is False
        assert expected_reason in report["rejections"]


def test_capture_watchdog_stays_armed_across_route_strategy_transition():
    status = _generic_watchdog_status(size=10, profile="blackwing_descent_10n", map_id=669)
    state = {}
    first = observe_capture_watchdog(
        state,
        status,
        None,
        [_watchdog_trace([{
            "action": "validation_route_recovery",
            "result": "route_destination_invalid_z_transition",
            "route_node_id": "blackwing_descent_10n.node",
            "route_generation": 1,
            "sequence": 1,
        }])],
        profile_name="blackwing_descent_10n",
    )
    assert first["detected"] is False
    status["raid_runtime"]["strategy_id"] = "trash_two_tank_charge_lanes"
    second = observe_capture_watchdog(
        state, status, None, [], profile_name="blackwing_descent_10n",
    )
    assert second["detected"] is False
    assert second["rejections"] == []
    assert second["repeated_decision_count"] == 1


def _watchdog_trace(entries: list[dict], *, bot_guid: int = 1001) -> dict:
    return {
        "action": "botauto_trace",
        "bots": [{"bot_guid": bot_guid, "entries": entries}],
    }


def _watchdog_diagnosis(
    *, bot_guid: int, action: str, result: str, repeat_count: int,
    diagnosis_code: str = "repeated_decision_loop",
    consecutive_count: int | None = None,
) -> dict:
    decision = {
        "action": action,
        "result": result,
        "fingerprint_repeat_count": repeat_count,
    }
    if consecutive_count is not None:
        decision["consecutive_same_decision_count"] = consecutive_count
    return {
        "bots": [{
            "identity": {"bot_guid": bot_guid},
            "snapshot": {
                "decision": decision,
                "route_progress": {
                    "route": {
                        "node_id": "blackwing_descent_10n.node",
                        "generation": 1,
                    },
                },
            },
            "diagnosis": {"diagnosis_code": diagnosis_code},
        }],
    }


def test_capture_watchdog_stops_scoped_repeated_route_failures_and_deduplicates_trace_rows():
    status = _watchdog_status()
    state = {}
    entries = [
        {
            "action": "validation_route_recovery",
            "result": "route_destination_invalid_z_transition",
            "recovery_result": "route_destination_invalid_z_transition",
            "route_node_id": "bwd.magmaw.drudges",
            "route_generation": 3,
            "sequence": sequence,
            "fingerprint_hash": 4242,
        }
        for sequence in range(1, 3)
    ]

    report = observe_capture_watchdog(
        state, status, None, [_watchdog_trace(entries)],
        max_repeated_decisions=3, max_death_loops=3,
    )
    assert report["detected"] is False
    assert report["repeated_decision_count"] == 2

    terminal = observe_capture_watchdog(
        state,
        status,
        None,
        [_watchdog_trace([dict(entries[-1], sequence=3)])],
        max_repeated_decisions=3,
        max_death_loops=3,
    )
    assert terminal["detected"] is True
    assert terminal["classification"] == "gameplay_failure"
    assert terminal["failure_reason"] == "repeated_decision_watchdog"
    assert terminal["repeated_decision_outcome"] == "route_destination_invalid_z_transition"
    duplicate = observe_capture_watchdog(
        state, status, None, [_watchdog_trace([dict(entries[-1], sequence=3)])],
        max_repeated_decisions=3, max_death_loops=3,
    )
    assert duplicate["repeated_decision_count"] == 3


def test_capture_watchdog_scopes_repeated_decisions_per_bot_at_threshold():
    status = _watchdog_status()
    common_entry = {
        "action": "validation_route_recovery",
        "result": "route_destination_invalid_z_transition",
        "recovery_result": "route_destination_invalid_z_transition",
        "route_node_id": "bwd.magmaw.drudges",
        "route_generation": 3,
        "fingerprint_hash": 4242,
    }
    different_bot_state = {}
    different_bot_trace = {
        "action": "botauto_trace",
        "bots": [
            {
                "bot_guid": bot_guid,
                "entries": [
                    dict(common_entry, sequence=sequence, timestamp_ms=sequence)
                    for sequence in range(1, 3)
                ],
            }
            for bot_guid in range(1001, 1011)
        ],
    }

    report = observe_capture_watchdog(
        different_bot_state,
        status,
        None,
        [different_bot_trace],
        max_repeated_decisions=20,
        max_death_loops=3,
    )
    assert report["detected"] is False
    assert report["repeated_decision_count"] == 2
    assert different_bot_state["repeated_decision_counts"]
    assert set(different_bot_state["repeated_decision_counts"].values()) == {2}

    single_bot_state = {}
    below_threshold = _watchdog_trace(
        [dict(common_entry, sequence=sequence, timestamp_ms=sequence) for sequence in range(1, 20)]
    )
    report = observe_capture_watchdog(
        single_bot_state,
        status,
        None,
        [below_threshold],
        max_repeated_decisions=20,
        max_death_loops=3,
    )
    assert report["detected"] is False
    assert report["repeated_decision_count"] == 19

    threshold_entry = dict(common_entry, sequence=20, timestamp_ms=20)
    terminal = observe_capture_watchdog(
        single_bot_state,
        status,
        None,
        [_watchdog_trace([threshold_entry])],
        max_repeated_decisions=20,
        max_death_loops=3,
    )
    assert terminal["detected"] is True
    assert terminal["failure_reason"] == "repeated_decision_watchdog"
    assert terminal["repeated_decision_count"] == 20

    duplicate = observe_capture_watchdog(
        single_bot_state,
        status,
        None,
        [_watchdog_trace([threshold_entry])],
        max_repeated_decisions=20,
        max_death_loops=3,
    )
    assert duplicate["repeated_decision_count"] == 20
    assert list(single_bot_state["repeated_decision_counts"].values()) == [20]


def test_capture_watchdog_canary82_replay_keeps_stuck_drudge_scope_after_healthy_progress():
    status = _watchdog_status()
    state = {}
    healthy_entries = []
    for sequence in range(1, 21):
        hp = 0.80 - (sequence * 0.01)
        healthy_entries.append({
            "action": "cast_combat_spell",
            "result": "ok",
            "route_node_id": "bwd.magmaw.drudges",
            "route_generation": 3,
            "sequence": sequence,
            "timestamp_ms": sequence,
            "route_progress": {
                "route": {
                    "node_id": "bwd.magmaw.drudges",
                    "generation": 3,
                },
                "target": {
                    "entry": 42649,
                    "guid": 27,
                    "hp_pct": hp,
                    "best_hp_pct": hp,
                },
                "no_progress": {"reason": "route_target_combat_progress"},
            },
        })
    stuck_entries = []
    for sequence in range(1, 21):
        stuck_entries.append({
            "action": "validation_route_regroup",
            "result": "hold_anchor_no_focus",
            "route_node_id": "bwd.magmaw.drudges",
            "route_generation": 3,
            "fingerprint_hash": 3237198174,
            "consecutive_same_decision_count": 1,
            "sequence": 100 + sequence,
            "timestamp_ms": 100 + sequence,
            "route_progress": {
                "route": {
                    "node_id": "bwd.magmaw.drudges",
                    "generation": 3,
                },
                "target": {
                    "entry": 42649,
                    "guid": 27,
                    "hp_pct": 0.80,
                    "best_hp_pct": 0.80,
                },
            },
        })

    report = observe_capture_watchdog(
        state,
        status,
        None,
        [
            _watchdog_trace(healthy_entries, bot_guid=30009),
            _watchdog_trace(stuck_entries, bot_guid=30008),
        ],
        max_repeated_decisions=20,
        max_death_loops=3,
    )

    assert report["detected"] is True
    assert report["failure_reason"] == "repeated_decision_watchdog"
    assert report["scope"] == {
        "route_node_id": "bwd.magmaw.drudges",
        "route_generation": 3,
    }
    assert report["repeated_decision_count"] == 20
    assert report["repeated_decision_outcome"] == "hold_anchor_no_focus"
    assert report["death_loop_count"] == 0
    assert report["progress_reset_scope"] == "bwd.magmaw.drudges:3"
    assert report["progress_reset_bot_guid"] == 30009
    assert report["progress_reset_reason"] == "route_target_combat_progress"
    assert len(report["last_10_repeated_decisions"]) == 10
    assert {
        row["bot_guid"] for row in report["last_10_repeated_decisions"]
    } == {30008}


def test_capture_watchdog_ignores_non_failed_diagnosis_repeated_loop():
    status = _generic_watchdog_status(size=10, profile="blackwing_descent_10n", map_id=669)
    diagnosis = _watchdog_diagnosis(
        bot_guid=1001,
        action="validation_route_patrol_wait_for_safe_phase",
        result="ok",
        repeat_count=20,
    )

    report = observe_capture_watchdog(
        {}, status, diagnosis,
        max_repeated_decisions=3,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["repeated_decision_count"] == 0
    assert report["failure_reason"] is None


def test_capture_watchdog_stops_successful_wait_hiding_stalled_magmaw_move():
    status = _generic_watchdog_status(
        size=10, profile="blackwing_descent_10n", map_id=669,
    )
    status["validation_route"].update(
        node_id="bwd.magmaw.encounter", generation=4, kind="boss",
    )
    diagnosis = _watchdog_diagnosis(
        bot_guid=30007,
        action="raid_prepull_consumable",
        result="ok",
        repeat_count=20,
        consecutive_count=20,
    )
    bot = diagnosis["bots"][0]
    bot["snapshot"]["route_progress"]["route"].update(
        node_id="bwd.magmaw.encounter", generation=4,
    )
    bot["snapshot"]["movement"] = {
        "is_moving": False,
        "time_since_last_progress_ms": 20_000,
    }
    bot["diagnosis"]["decision_kernel"] = {
        "candidates": [{
            "source": "adaptive_magmaw",
            "phase": "failed",
            "status": "attempted",
            "reason": "native_move_retryable",
        }],
    }

    report = observe_capture_watchdog(
        {}, status, diagnosis,
        max_repeated_decisions=20, max_death_loops=3,
    )

    assert report["detected"] is True
    assert report["failure_reason"] == "repeated_decision_watchdog"
    assert report["repeated_decision_count"] == 20
    assert report["repeated_decision_outcome"] == "native_move_retryable"
    assert report["last_10_repeated_decisions"][-1]["action"] \
        == "adaptive_magmaw_movement"


def test_capture_watchdog_allows_retryable_magmaw_move_while_progressing():
    status = _generic_watchdog_status(
        size=10, profile="blackwing_descent_10n", map_id=669,
    )
    diagnosis = _watchdog_diagnosis(
        bot_guid=30007,
        action="raid_prepull_consumable",
        result="ok",
        repeat_count=20,
        consecutive_count=20,
    )
    bot = diagnosis["bots"][0]
    bot["snapshot"]["movement"] = {
        "is_moving": True,
        "time_since_last_progress_ms": 1_000,
    }
    bot["diagnosis"]["decision_kernel"] = {
        "candidates": [{
            "source": "adaptive_magmaw",
            "phase": "failed",
            "status": "attempted",
            "reason": "native_move_retryable",
        }],
    }

    report = observe_capture_watchdog(
        {}, status, diagnosis,
        max_repeated_decisions=20, max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["repeated_decision_count"] == 0


def test_capture_watchdog_does_not_reuse_stale_stalled_diagnosis():
    status = _generic_watchdog_status(
        size=10, profile="blackwing_descent_10n", map_id=669,
    )
    status["validation_route"].update(
        node_id="bwd.magmaw.encounter", generation=4, kind="boss",
    )
    diagnosis = _watchdog_diagnosis(
        bot_guid=30007,
        action="raid_prepull_consumable",
        result="ok",
        repeat_count=20,
        consecutive_count=19,
    )
    bot = diagnosis["bots"][0]
    bot["snapshot"]["route_progress"]["route"].update(
        node_id="bwd.magmaw.encounter", generation=4,
    )
    bot["snapshot"]["movement"] = {
        "is_moving": False,
        "time_since_last_progress_ms": 20_000,
    }
    bot["diagnosis"]["decision_kernel"] = {
        "candidates": [{
            "source": "adaptive_magmaw",
            "phase": "failed",
            "status": "attempted",
            "reason": "native_move_retryable",
        }],
    }
    state = {}

    first = observe_capture_watchdog(
        state, status, diagnosis,
        max_repeated_decisions=20, max_death_loops=3,
    )
    resumed_status = json.loads(json.dumps(status))
    resumed_status["raid_runtime"]["heartbeat"] = 2
    second = observe_capture_watchdog(
        state, resumed_status, None,
        max_repeated_decisions=20, max_death_loops=3,
    )

    assert first["detected"] is False
    assert second["detected"] is False
    assert second["repeated_decision_count"] == 0


def test_capture_watchdog_diagnosis_counts_failed_route_decisions_per_bot():
    status = _generic_watchdog_status(size=10, profile="blackwing_descent_10n", map_id=669)
    state = {}
    initial = {
        "bots": [
            _watchdog_diagnosis(
                bot_guid=bot_guid,
                action="validation_route_recovery",
                result="no_candidate_committed",
                repeat_count=2,
            )["bots"][0]
            for bot_guid in (1001, 1002)
        ],
    }

    report = observe_capture_watchdog(
        state, status, initial,
        max_repeated_decisions=3,
        max_death_loops=3,
    )
    assert report["detected"] is False
    assert report["repeated_decision_count"] == 2
    assert set(state["diagnosis_repeat_high_water"].values()) == {2}

    terminal = observe_capture_watchdog(
        state,
        status,
        _watchdog_diagnosis(
            bot_guid=1001,
            action="validation_route_recovery",
            result="no_candidate_committed",
            repeat_count=3,
        ),
        max_repeated_decisions=3,
        max_death_loops=3,
    )
    assert terminal["detected"] is True
    assert terminal["failure_reason"] == "repeated_decision_watchdog"
    assert terminal["repeated_decision_count"] == 3
    assert terminal["repeated_decision_outcome"] == "no_candidate_committed"


def test_capture_watchdog_ignores_cumulative_fingerprint_when_native_run_is_one():
    status = _generic_watchdog_status(
        size=10, profile="blackwing_descent_10n", map_id=669,
    )
    state = {}
    diagnosis = _watchdog_diagnosis(
        bot_guid=1001,
        action="wait_for_candidate_backoff",
        result="failed",
        repeat_count=158,
        consecutive_count=1,
    )

    first = observe_capture_watchdog(
        state, status, diagnosis, max_repeated_decisions=20, max_death_loops=3,
    )
    second = observe_capture_watchdog(
        state, status, diagnosis, max_repeated_decisions=20, max_death_loops=3,
    )

    assert first["detected"] is False
    assert second["detected"] is False
    assert second["repeated_decision_count"] == 1
    assert second["repeated_decision_outcome"] == "failed"


def test_capture_watchdog_uses_native_run_across_intervening_success():
    status = _watchdog_status()
    state = {}
    trace = _watchdog_trace([
        {
            "action": "wait_for_candidate_backoff",
            "result": "failed",
            "fingerprint_hash": 1225206246,
            "fingerprint_repeat_count": 158,
            "consecutive_same_decision_count": 1,
            "route_node_id": "bwd.magmaw.drudges",
            "route_generation": 3,
            "sequence": 1,
        },
        {
            "action": "attack",
            "result": "ok",
            "fingerprint_hash": 3531292137,
            "consecutive_same_decision_count": 1,
            "route_node_id": "bwd.magmaw.drudges",
            "route_generation": 3,
            "sequence": 2,
        },
        {
            "action": "wait_for_candidate_backoff",
            "result": "failed",
            "fingerprint_hash": 1225206246,
            "fingerprint_repeat_count": 159,
            "consecutive_same_decision_count": 1,
            "route_node_id": "bwd.magmaw.drudges",
            "route_generation": 3,
            "sequence": 3,
        },
    ])

    report = observe_capture_watchdog(
        state, status, None, [trace],
        max_repeated_decisions=20, max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["repeated_decision_count"] == 1
    assert list(state["repeated_decision_counts"].values()) == [1]


def test_capture_watchdog_stops_true_native_consecutive_failure_run():
    status = _watchdog_status()
    state = {}
    entries = [
        {
            "action": "wait_for_candidate_backoff",
            "result": "failed",
            "fingerprint_hash": 1225206246,
            "fingerprint_repeat_count": 158 + sequence,
            "consecutive_same_decision_count": sequence,
            "route_node_id": "bwd.magmaw.drudges",
            "route_generation": 3,
            "sequence": sequence,
        }
        for sequence in range(1, 21)
    ]

    report = observe_capture_watchdog(
        state, status, None, [_watchdog_trace(entries)],
        max_repeated_decisions=20, max_death_loops=3,
    )

    assert report["detected"] is True
    assert report["failure_reason"] == "repeated_decision_watchdog"
    assert report["repeated_decision_outcome"] == "failed"
    assert report["repeated_decision_count"] == 20


def test_capture_watchdog_ignores_stale_recovery_on_successful_progressing_trace():
    status = _watchdog_status()
    status["validation_route"].update(
        node_id="bwd.magmaw.chainwielder", generation=2, kind="trash",
    )
    route_progress = {
        "route": {
            "node_id": "bwd.magmaw.chainwielder",
            "generation": 2,
            "kind": "trash",
        },
        "target": {
            "entry": 42649,
            "guid": 27,
            "hp_pct": 0.987513,
            "best_hp_pct": 0.987513,
        },
        "no_progress": {
            "count": 0,
            "reason": "route_target_combat_progress",
            "threshold": 20,
        },
        "state": {
            "bot_casting": True,
            "bot_in_combat": True,
            "victim_guid": 30001,
        },
    }
    diagnosis = {
        "action": "botauto_diagnose",
        "bots": [{
            "identity": {"bot_guid": 1001},
            "diagnosis": {"diagnosis_code": "normal_combat"},
            "snapshot": {
                "decision": {
                    "action": "attack",
                    "result": "ok",
                    "fingerprint_hash": 1225206246,
                    "fingerprint_repeat_count": 4,
                },
                "route_progress": route_progress,
            },
        }],
    }
    trace = _watchdog_trace([
        {
            "action": "wait_for_candidate_backoff",
            "result": "ok",
            "recovery_result": "no_candidate_committed",
            "route_node_id": "bwd.magmaw.chainwielder",
            "route_generation": 2,
            "route_progress": route_progress,
            "fingerprint_hash": 1225206246,
            "sequence": sequence,
            "timestamp_ms": sequence,
        }
        for sequence in range(1, 21)
    ])

    watchdog_state = {}
    report = observe_capture_watchdog(
        watchdog_state,
        status,
        diagnosis,
        [trace],
        max_repeated_decisions=20,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["repeated_decision_count"] == 0
    assert report["repeated_decision_outcome"] is None
    assert watchdog_state.get("repeated_decision_counts", {}) == {}

    # The same sample carries objective route progress, so the separate
    # monotonic clock also advances after the watchdog observes it.
    progress_state = {}
    assert observe_monotonic_semantic_progress(
        progress_state, status, diagnosis,
    ) is True
    assert progress_state["lowest_target_hp"]


def test_capture_watchdog_resets_repeated_hazard_failures_on_monotonic_target_progress():
    status = _watchdog_status()
    status["validation_route"].update(
        node_id="bwd.magmaw.chainwielder", generation=2, kind="trash",
    )
    state = {}
    entries = []
    for sequence in range(1, 21):
        hp = 0.80 - (sequence * 0.01)
        entries.append({
            "action": "validation_route_mechanic",
            "result": "hazard_exit_failed",
            "route_node_id": "bwd.magmaw.chainwielder",
            "route_generation": 2,
            "fingerprint_hash": 1225206246,
            "sequence": sequence,
            "timestamp_ms": sequence,
            "route_progress": {
                "route": {
                    "node_id": "bwd.magmaw.chainwielder",
                    "generation": 2,
                    "kind": "trash",
                },
                "target": {
                    "entry": 42649,
                    "guid": 27,
                    "hp_pct": hp,
                    "best_hp_pct": hp,
                },
                "no_progress": {"count": 0, "threshold": 20},
            },
        })

    report = observe_capture_watchdog(
        state,
        status,
        None,
        [_watchdog_trace(entries)],
        max_repeated_decisions=20,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["failure_reason"] is None
    assert report["progress_reset_count"] == 19
    assert report["progress_reset_scope"] == "bwd.magmaw.chainwielder:2"
    assert report["repeated_decision_count"] == 0
    assert state["repeated_decision_counts"] == {}


def test_capture_watchdog_groups_canary23_adapter_failure_with_successful_native_tick():
    status = _watchdog_status()
    status["validation_route"].update(
        node_id="bwd.magmaw.chainwielder", generation=2, kind="trash",
    )
    state = {}
    route_progress = {
        "route": {
            "node_id": "bwd.magmaw.chainwielder",
            "generation": 2,
            "kind": "trash",
        },
        "target": {
            "entry": 42649,
            "guid": 27,
            "hp_pct": 0.70,
            "best_hp_pct": 0.70,
        },
        "no_progress": {"count": 0, "reason": "route_target_combat_progress", "threshold": 20},
    }

    # Establish the target high-water mark and then its observed progress so
    # the grouped tail is tested after progress, as in Canary23.
    for hp in (0.80, 0.70):
        progress = json.loads(json.dumps(route_progress))
        progress["target"]["hp_pct"] = hp
        progress["target"]["best_hp_pct"] = hp
        observe_capture_watchdog(
            state,
            status,
            None,
            [_watchdog_trace([{
                "action": "cast_combat_spell",
                "result": "ok",
                "route_node_id": "bwd.magmaw.chainwielder",
                "route_generation": 2,
                "route_progress": progress,
                "sequence": int(hp * 100),
                "timestamp_ms": int(hp * 100),
                "decision_sequence": int(hp * 100),
            }], bot_guid=30008)],
            max_repeated_decisions=20,
            max_death_loops=3,
        )

    entries = []
    for tick in range(1, 21):
        timestamp = 10_000 + tick
        failure = {
            "action": "validation_route_mechanic",
            "result": "hazard_exit_failed",
            "reason_code": "event_failure",
            "recovery_result": "hazard_exit_no_union_safe_native_path",
            "fingerprint_hash": 820785536,
            "consecutive_same_decision_count": tick,
            "route_node_id": "bwd.magmaw.chainwielder",
            "route_generation": 2,
            "route_progress": route_progress,
            "sequence": 300 + (tick * 3),
            "timestamp_ms": timestamp,
            "decision_sequence": 800 + tick,
        }
        entries.extend([
            failure,
            {
                **failure,
                "action": "spell_cast",
                "result": "ok",
                "reason_code": "",
                "recovery_result": "hazard_exit_no_union_safe_native_path",
                "sequence": failure["sequence"] + 1,
            },
            {
                **failure,
                "action": "cast_combat_spell",
                "result": "ok",
                "reason_code": "",
                "sequence": failure["sequence"] + 2,
            },
        ])

    report = observe_capture_watchdog(
        state,
        status,
        None,
        [_watchdog_trace(entries, bot_guid=30008)],
        max_repeated_decisions=20,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["failure_reason"] is None
    assert report["repeated_decision_count"] == 0
    assert state["repeated_decision_counts"] == {}


def test_capture_watchdog_counts_failure_only_decision_tick_groups():
    status = _watchdog_status()
    status["validation_route"].update(
        node_id="bwd.magmaw.chainwielder", generation=2, kind="trash",
    )
    failures = []
    for tick in range(1, 4):
        timestamp = 20_000 + tick
        base = {
            "result": "hazard_exit_failed",
            "reason_code": "event_failure",
            "recovery_result": "hazard_exit_no_union_safe_native_path",
            "fingerprint_hash": 820785536,
            "consecutive_same_decision_count": tick,
            "route_node_id": "bwd.magmaw.chainwielder",
            "route_generation": 2,
            "sequence": tick * 2,
            "timestamp_ms": timestamp,
            "decision_sequence": 900 + tick,
        }
        failures.extend([
            {**base, "action": "validation_route_mechanic"},
            {**base, "action": "validation_route_recovery", "sequence": tick * 2 + 1},
        ])

    state = {}
    first = observe_capture_watchdog(
        state,
        status,
        None,
        [_watchdog_trace(failures[:4], bot_guid=30008)],
        max_repeated_decisions=3,
        max_death_loops=3,
    )
    assert first["detected"] is False
    assert first["repeated_decision_count"] == 2

    terminal = observe_capture_watchdog(
        state,
        status,
        None,
        [_watchdog_trace(failures[4:], bot_guid=30008)],
        max_repeated_decisions=3,
        max_death_loops=3,
    )
    assert terminal["detected"] is True
    assert terminal["failure_reason"] == "repeated_decision_watchdog"
    assert terminal["repeated_decision_count"] == 3


def test_capture_watchdog_does_not_inherit_native_count_from_successful_events():
    status = _watchdog_status()
    status["validation_route"].update(
        node_id="bwd.magmaw.chainwielder", generation=2, kind="trash",
    )
    state = {}
    fingerprint = 947707352
    successful_movement = [
        {
            "action": "move_out_of_hazard",
            "result": "ok",
            "route_node_id": "bwd.magmaw.chainwielder",
            "route_generation": 2,
            "fingerprint_hash": fingerprint,
            "consecutive_same_decision_count": sequence,
            "sequence": sequence,
            "timestamp_ms": sequence,
        }
        for sequence in range(1, 26)
    ]
    inherited_failure = {
        "action": "validation_route_mechanic",
        "result": "tactical_path_rejected",
        "recovery_result": "higher_priority_movement_active",
        "route_node_id": "bwd.magmaw.chainwielder",
        "route_generation": 2,
        "fingerprint_hash": fingerprint,
        "consecutive_same_decision_count": 25,
        "sequence": 26,
        "timestamp_ms": 25,
    }

    report = observe_capture_watchdog(
        state,
        status,
        None,
        [_watchdog_trace([*successful_movement, inherited_failure])],
        max_repeated_decisions=20,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["repeated_decision_count"] == 1

    actual_failures = [
        {
            **inherited_failure,
            "consecutive_same_decision_count": native_count,
            "sequence": native_count + 1,
            "timestamp_ms": native_count,
        }
        for native_count in range(26, 45)
    ]
    terminal = observe_capture_watchdog(
        state,
        status,
        None,
        [_watchdog_trace(actual_failures)],
        max_repeated_decisions=20,
        max_death_loops=3,
    )

    assert terminal["detected"] is True
    assert terminal["failure_reason"] == "repeated_decision_watchdog"
    assert terminal["repeated_decision_count"] == 20
    assert terminal["repeated_decision_outcome"] == "tactical_path_rejected"


def test_capture_watchdog_does_not_inherit_native_count_from_successful_adapter_event():
    status = _watchdog_status()
    status["validation_route"].update(
        node_id="bwd.magmaw.chainwielder", generation=2, kind="trash",
    )
    state = {}
    fingerprint = 1225206246
    first_sample = _watchdog_trace([
        {
            "action": "wait_for_candidate_backoff",
            "result": "ok",
            "recovery_result": "no_candidate_committed",
            "fingerprint_hash": fingerprint,
            "consecutive_same_decision_count": 1,
            "route_node_id": "bwd.magmaw.chainwielder",
            "route_generation": 2,
            "sequence": 314,
        },
        {
            "action": "validation_route_mechanic",
            "result": "hazard_exit_failed",
            "reason_code": "event_failure",
            "recovery_result": "hazard_exit_no_union_safe_native_path",
            "fingerprint_hash": fingerprint,
            "consecutive_same_decision_count": 25,
            "route_node_id": "bwd.magmaw.chainwielder",
            "route_generation": 2,
            "sequence": 315,
        },
    ], bot_guid=30008)

    report = observe_capture_watchdog(
        state,
        status,
        None,
        [first_sample],
        max_repeated_decisions=20,
        max_death_loops=3,
    )

    assert report["detected"] is False
    assert report["repeated_decision_count"] == 1
    assert list(state.get("repeated_decision_counts", {}).values()) == [1]

    genuine_failures = _watchdog_trace([
        {
            "action": "validation_route_mechanic",
            "result": "hazard_exit_failed",
            "reason_code": "event_failure",
            "recovery_result": "hazard_exit_no_union_safe_native_path",
            "fingerprint_hash": fingerprint,
            "consecutive_same_decision_count": native_count,
            "route_node_id": "bwd.magmaw.chainwielder",
            "route_generation": 2,
            "sequence": native_count + 290,
        }
        for native_count in range(26, 45)
    ], bot_guid=30008)
    terminal = observe_capture_watchdog(
        state,
        status,
        None,
        [genuine_failures],
        max_repeated_decisions=20,
        max_death_loops=3,
    )

    assert terminal["detected"] is True
    assert terminal["failure_reason"] == "repeated_decision_watchdog"
    assert terminal["repeated_decision_count"] == 20
    assert terminal["repeated_decision_outcome"] == "hazard_exit_failed"


def test_capture_watchdog_still_stops_flat_repeated_hazard_failures():
    status = _watchdog_status()
    status["validation_route"].update(
        node_id="bwd.magmaw.chainwielder", generation=2, kind="trash",
    )
    state = {}
    route_progress = {
        "route": {
            "node_id": "bwd.magmaw.chainwielder",
            "generation": 2,
            "kind": "trash",
        },
        "target": {"entry": 42649, "guid": 27, "hp_pct": 0.80, "best_hp_pct": 0.80},
        "no_progress": {"count": 20, "threshold": 20},
    }
    baseline = {
        "action": "wait_for_candidate_backoff",
        "result": "ok",
        "route_node_id": "bwd.magmaw.chainwielder",
        "route_generation": 2,
        "sequence": 1,
        "timestamp_ms": 1,
        "route_progress": route_progress,
    }
    assert observe_capture_watchdog(
        state,
        status,
        None,
        [_watchdog_trace([baseline])],
        max_repeated_decisions=20,
        max_death_loops=3,
    )["detected"] is False

    repeated = [
        {
            "action": "validation_route_mechanic",
            "result": "hazard_exit_failed",
            "route_node_id": "bwd.magmaw.chainwielder",
            "route_generation": 2,
            "fingerprint_hash": 1225206246,
            "sequence": sequence,
            "timestamp_ms": sequence,
            "route_progress": route_progress,
        }
        for sequence in range(2, 22)
    ]
    report = observe_capture_watchdog(
        state,
        status,
        None,
        [_watchdog_trace(repeated)],
        max_repeated_decisions=20,
        max_death_loops=3,
    )

    assert report["detected"] is True
    assert report["failure_reason"] == "repeated_decision_watchdog"
    assert report["repeated_decision_outcome"] == "hazard_exit_failed"
    assert report["repeated_decision_count"] == 20


def test_capture_watchdog_classifies_excessive_scoped_deaths_as_gameplay_failure():
    status = _watchdog_status()
    trace = _watchdog_trace([
        {
            "action": "death",
            "route_node_id": "bwd.magmaw.drudges",
            "route_generation": 3,
            "sequence": sequence,
        }
        for sequence in range(1, 4)
    ])
    report = observe_capture_watchdog(
        {}, status, None, [trace], max_repeated_decisions=20, max_death_loops=3,
    )
    assert report["detected"] is True
    assert report["classification"] == "gameplay_failure"
    assert report["failure_reason"] == "death_loop_watchdog"
    assert report["death_loop_count"] == 3


def test_capture_watchdog_fails_closed_when_attempt_identity_is_not_exact():
    status = _watchdog_status()
    status["cohort_id"] = "foreign-cohort"
    trace = _watchdog_trace([
        {
            "action": "validation_route_recovery",
            "result": "route_destination_invalid_z_transition",
            "route_node_id": "bwd.magmaw.drudges",
            "route_generation": 3,
            "sequence": sequence,
        }
        for sequence in range(1, 5)
    ])
    report = observe_capture_watchdog(
        {}, status, None, [trace], max_repeated_decisions=3, max_death_loops=3,
    )
    assert report["detected"] is False
    assert "watchdog_cohort_mismatch" in report["rejections"]


def test_magmaw_capture_requires_recurrence_admission_before_start(tmp_path: Path):
    config = tmp_path / "worldserver.conf"
    receipt = tmp_path / "build.json"
    config.write_text("BotWorld.AutoStart = 0\n", encoding="utf-8")
    receipt.write_text("{}\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.raid_program.capture_phase1_raid_foundation",
            "--binary",
            "/bin/true",
            "--config",
            str(config),
            "--output",
            str(tmp_path / "report.json"),
            "--build-receipt",
            str(receipt),
            "--worktree",
            str(Path(__file__).resolve().parents[1]),
            "--scenario-id",
            "blackwing_descent_10n_magmaw_diagnostic",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "magmaw_recurrence_admission_required" in result.stderr
