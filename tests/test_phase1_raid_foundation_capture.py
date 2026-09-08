import ast
import base64
import copy
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

import tools.raid_program.chainwielder_prestart_bundle as prestart_bundle
from tests.test_chainwielder_prestart_bundle import (
    _add_layered_build_control_authority,
    _create as _create_prestart_bundle,
    _generic_profile_range_fixture,
)

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
from tools.raid_program.capture_environment_validation import (
    snapshot_receipt_bound_artifacts,
)
from tools.raid_program.chainwielder_prestart_bundle import (
    PERSONAL_THREAT_EPISODE_SCOPE_KEY_TEMPLATE,
)
from tools.raid_program.prestart_bundle_dialects import (
    PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
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


@pytest.fixture
def verified_runtime_asset_capture_gate(monkeypatch):
    """Upstream fixture for tests of downstream capture/recurrence contracts.

    Missing-asset rejection is exercised without this fixture in
    test_runtime_asset_closure.py. No real launch is authorized by this stub.
    """
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.enforce_runtime_asset_closure_from_args",
        lambda *args, **kwargs: {"complete": True, "status": "runtime_asset_closure_complete"},
    )


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
    assert args.build_worktree is None
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
    assert args.trace_interval_sec == 2.0
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
        "tools.raid_program.capture_setup.enforce_runtime_asset_closure_from_args",
        lambda *_args, **_kwargs: {
            "complete": True, "status": "runtime_asset_closure_complete",
        },
    )

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
    assert setup.worktree == tmp_path.resolve()
    assert setup.build_worktree == tmp_path.resolve()
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


def test_prepare_capture_setup_separates_source_and_build_worktrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_worktree = tmp_path / "immutable-source"
    build_worktree = tmp_path / "retained-build"
    source_worktree.mkdir()
    build_worktree.mkdir()
    binary = build_worktree / "build/src/server/worldserver/worldserver"
    binary.parent.mkdir(parents=True)
    config = tmp_path / "worldserver.conf"
    receipt = tmp_path / "build.json"
    output = tmp_path / "capture.json"
    for path in (binary, config, receipt):
        path.write_bytes(b"fixture")
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.enforce_runtime_asset_closure_from_args",
        lambda *_args, **_kwargs: {
            "complete": True, "status": "runtime_asset_closure_complete",
        },
    )
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        "tools.raid_program.capture_setup.chainwielder_checkpoint_arm_command",
        lambda admission, actor_guid: None,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.trinity_config_bool",
        lambda *args, **kwargs: False,
    )

    def source_preflight(worktree: Path) -> dict[str, object]:
        observed["preflight_worktree"] = worktree
        return {"passed": True, "reasons": []}

    def source_identity(worktree: Path) -> dict[str, object]:
        observed["identity_worktree"] = worktree
        return {"clean": True, "head": "a" * 40, "tree": "b" * 40}

    def source_assets(worktree: Path, **kwargs) -> dict[str, object]:
        observed["asset_worktree"] = worktree
        return {
            "passed": True,
            "reasons": [],
            "route_manifest": None,
            "route_partition": "stonecore_5n",
        }

    monkeypatch.setattr(
        "tools.raid_program.capture_setup.preflight_runtime_exclusions",
        source_preflight,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.git_identity", source_identity,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.validate_runtime_profile_assets",
        source_assets,
    )

    def build_policy(build_receipt: Path, worktree: Path) -> Path:
        observed["policy_worktree"] = worktree
        return build_worktree / "experiments/configs/policy.json"

    build_identity = {
        "commit": "c" * 40,
        "tree": "d" * 40,
        "clean": True,
        "dirty": False,
        "porcelain_sha256": hashlib.sha256(b"").hexdigest(),
    }

    def build_validation(
        receipt_path: Path, policy_path: Path, worktree: Path,
        observed_binary: Path, *args, **kwargs,
    ) -> dict[str, object]:
        observed["validation_source_worktree"] = worktree
        observed["validation_build_worktree"] = kwargs["build_worktree"]
        observed["validation_binary"] = observed_binary
        return {
            "valid": True,
            "rejections": [],
            "build_worktree_identity": build_identity,
        }

    monkeypatch.setattr(
        "tools.raid_program.capture_setup.build_policy_path_for_receipt",
        build_policy,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.validate_build_receipt",
        build_validation,
    )

    setup = prepare_capture_setup([
        "--binary", str(binary),
        "--config", str(config),
        "--output", str(output),
        "--build-receipt", str(receipt),
        "--worktree", str(source_worktree),
        "--build-worktree", str(build_worktree),
        "--runtime-profile", "stonecore_5n",
    ], root=tmp_path)

    assert setup.worktree == source_worktree.resolve()
    assert setup.build_worktree == build_worktree.resolve()
    assert setup.identity_before["head"] == "a" * 40
    assert setup.build_identity_before == build_identity
    assert observed == {
        "preflight_worktree": source_worktree.resolve(),
        "identity_worktree": source_worktree.resolve(),
        "asset_worktree": source_worktree.resolve(),
        "policy_worktree": build_worktree.resolve(),
        "validation_source_worktree": source_worktree.resolve(),
        "validation_build_worktree": build_worktree.resolve(),
        "validation_binary": binary.resolve(),
    }


@pytest.mark.usefixtures("verified_runtime_asset_capture_gate")
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
            "route_partition": {"node_count": 3, "terminal_index": 2},
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


@pytest.mark.parametrize("drudge_observed", [False, True])
def test_execute_capture_run_owns_fake_process_and_live_loop(tmp_path: Path, monkeypatch, drudge_observed):
    binary = tmp_path / "worldserver"
    config = tmp_path / "worldserver.conf"
    server_log = tmp_path / "worldserver.log"
    binary.write_bytes(b"fixture")
    cache_path = tmp_path / "build/CMakeCache.txt"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_bytes(b"fixture")
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
        runtime_asset_closure={"complete": True, "status": "runtime_asset_closure_complete"},
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
        drudge_observed=drudge_observed,
        drudge_required=False,
        drudge_navmesh_preflight={"required": False, "all_passed": None},
        drudge_frozen_anchors={},
        build_provenance={
            "valid": True,
            "artifact_snapshots": {
                "accepted_final": snapshot_receipt_bound_artifacts(
                    binary, tmp_path,
                ),
            },
        },
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
    observation_batches = iter([[status] for status in statuses])

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

    def reject_optional_drudge_gate(*args, **kwargs):
        raise AssertionError("Optional trash diagnostics must not gate live completion")

    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.accepted_drudge_contract",
        reject_optional_drudge_gate,
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


def test_execute_capture_run_retains_native_combat_event_delta_before_terminal_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, native_watchdog=False,
):
    """Exercise the production capture loop with a split delta transfer."""

    watchdog_fixture = _watchdog_native_progress_fixture() if native_watchdog else None
    native_rows = [watchdog_fixture["status"]] * 4 if native_watchdog else _native_capture_binding_statuses()
    native_identity = native_rows[0]
    profile = native_identity["active_profile"]
    binary = tmp_path / "worldserver"
    config = tmp_path / "worldserver.conf"
    server_log = tmp_path / "worldserver.log"
    binary.write_bytes(b"fixture")
    cache_path = tmp_path / "build/CMakeCache.txt"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_bytes(b"fixture")
    config.write_bytes(b"fixture")
    args = SimpleNamespace(
        trace_transport_smoke=False,
        telemetry_timeout_sec=2,
        observe_sec=8,
        status_interval_sec=0.05,
        diagnose_interval_sec=0.15,
        trace_interval_sec=0.05,
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
        runtime_asset_closure={"complete": True, "status": "runtime_asset_closure_complete"},
        args=args,
        binary=binary,
        config=config,
        output=tmp_path / "capture.json",
        worktree=tmp_path,
        profile_name=profile,
        scenario_id=profile,
        raw_output=tmp_path / "capture.raw.jsonl",
        server_log_output=server_log,
        recurrence_admission=None,
        checkpoint_arm_command=None,
        preflight={"passed": True, "reasons": []},
        identity_before={"clean": True},
        runtime_assets={
            "route_sha256": native_identity["raid_runtime"]["admission_receipt"]["route_manifest_sha256"],
            "route_partition": {"node_count": 4, "terminal_index": 3,
                "expected_strategy_id": profile, "terminal_node_id": "bwd.magmaw.encounter",
                "terminal_kind": "boss", "terminal_target_entry": 41570},
        },
        controller_route_hold_scheduler=None,
        drudge_observed=False,
        drudge_required=False,
        drudge_navmesh_preflight={"required": False, "all_passed": None},
        drudge_frozen_anchors={},
        build_provenance={
            "valid": True,
            "artifact_snapshots": {
                "accepted_final": snapshot_receipt_bound_artifacts(binary, tmp_path),
            },
        },
    )

    def status(sequence: int) -> dict[str, object]:
        return copy.deepcopy(native_rows[min(sequence - 1, len(native_rows) - 1)])

    def delta_payload(cursor: int) -> dict[str, object]:
        if native_watchdog:
            return dict(watchdog_fixture["delta_template"], cursor_before=cursor,
                recent_events=[row for row in watchdog_fixture["events"] if row["event_sequence"] > cursor])
        return {
            "ok": True,
            "action": "botauto_combatlog_delta",
            "combat_log_schema_version": 3,
            "cohort_id": "default",
            "server_epoch": native_identity["server_epoch"],
            "attempt_id": native_identity["attempt_id"],
            "combat_log_epoch": 1,
            "profile_generation": native_identity["profile_generation"],
            "profile_content_hash": native_identity["profile_content_hash"],
            "experiment_id": 7,
            "run_id": 49,
            "event_count_at_export": 1,
            "cursor_before": cursor,
            "cursor_after": 1 if cursor == 0 else cursor,
            "gap": False,
            "recent_events": ([
                {"event_sequence": 1, "kind": "damage", "amount": 1},
            ] if cursor == 0 else []),
        }

    def frames(payload: dict[str, object], chunk_size: int = 31) -> list[dict[str, object]]:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        parts = [raw[index : index + chunk_size] for index in range(0, len(raw), chunk_size)]
        return [
            {
                "ok": True,
                "action": "botauto_combatlog_chunk",
                "cohort_id": "default",
                "combat_log_chunk_schema_version": 1,
                "sequence": index,
                "chunk_count": len(parts),
                "encoding": "base64",
                "data": base64.b64encode(part).decode(),
            }
            for index, part in enumerate(parts)
        ] + [{
            "ok": True,
            "action": "botauto_combatlog_complete",
            "cohort_id": "default",
            "combat_log_chunk_schema_version": 1,
            "chunk_count": len(parts),
            "total_bytes": len(raw),
        }]

    class FakeProcess:
        pid = 4322

        def __init__(self):
            self.returncode = None
            self.output = None
            self.status_sequence = 0
            self.first_delta_frames: list[dict[str, object]] | None = None
            self.native_trace_sent = False
            self.delta_requested = False
            self.commands: list[str] = []
            self.stdin = self.RecordingStdin(self)

        class RecordingStdin(io.BytesIO):
            def __init__(self, owner):
                super().__init__()
                self.owner = owner

            def write(self, value):
                result = super().write(value)
                for command in value.decode().splitlines():
                    if command:
                        self.owner.on_command(command)
                return result

        def emit(self, row: dict[str, object]) -> None:
            self.output.write((json.dumps(row) + "\n").encode())
            self.output.flush()

        def on_command(self, command: str) -> None:
            self.commands.append(command)
            if command == "botauto status":
                self.status_sequence += 1
                self.emit(status(self.status_sequence))
                if self.first_delta_frames:
                    for row in self.first_delta_frames:
                        self.emit(row)
                    self.first_delta_frames = None
            elif command.startswith("botauto combatlog default delta "):
                cursor = int(command.split()[4])
                self.delta_requested = True
                rows = frames(delta_payload(cursor), chunk_size=12288 if native_watchdog else 31)
                if cursor == 0 and self.first_delta_frames is None:
                    self.emit(rows[0])
                    self.first_delta_frames = rows[1:]
                else:
                    for row in rows:
                        self.emit(row)
            elif command.startswith("botauto diagnose"):
                self.emit({"ok": True, "action": "botauto_diagnose", "cohort_id": "default"})
            elif command.startswith("botauto trace"):
                if native_watchdog and self.delta_requested and not self.first_delta_frames and not self.native_trace_sent:
                    self.emit(_watchdog_native_trace(watchdog_fixture))
                    self.native_trace_sent = True
                else:
                    self.emit({"ok": True, "action": "botauto_trace", "cohort_id": "default", "bots": []})
            elif command.startswith("botauto combatlog default"):
                # A late delta must never satisfy the terminal full gate.
                for row in frames(delta_payload(1)):
                    self.emit(dict(row, export_kind="delta", export_id=100))
                self.emit({
                    "ok": True, "action": "botauto_combatlog_complete",
                    "cohort_id": "default", "combat_log_chunk_schema_version": 1,
                    "chunk_count": 1, "total_bytes": 0, "export_kind": "full",
                    "export_id": 101,
                })

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.returncode = 0
            return 0

    process = FakeProcess()

    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.subprocess.Popen",
        lambda *args, **kwargs: (setattr(process, "output", kwargs["stdout"]) or process),
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.wait_for_prompt",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.collect_log_observations",
        lambda cursor, **kwargs: cursor.read_new_observations(),
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.time.sleep",
        lambda seconds: None,
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
        "tools.raid_program.capture_live_run.terminal_runtime_failure_reason",
        lambda status, **kwargs: (None, []),
    )
    if not native_watchdog:
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
            "gate_passed": True, "missing_channels": [], "rejections": [],
        },
    )
    def validate_full_only(rows, cohort_id):
        assert all(row.get("export_kind") == "full" for row in rows)
        return {"gate_passed": bool(rows), "rejections": []}

    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.validate_forced_combat_log_bundle",
        validate_full_only,
    )
    def fake_shutdown(child, timeout_seconds):
        child.returncode = 0
        return {
            "commands_sent": ["botauto stop", "botauto status", "server exit"],
            "error": None, "operator_interrupted": False,
        }

    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.bounded_native_shutdown",
        fake_shutdown,
    )

    result = execute_capture_run(setup)

    delta_commands = [
        command for command in process.commands
        if command.startswith("botauto combatlog default delta ")
    ]
    assert delta_commands[0] == "botauto combatlog default delta 0 4096"
    assert len([command for command in delta_commands if " delta 0 " in command]) == 1
    expected_cursor = 748 if native_watchdog else 1
    assert f"botauto combatlog default delta {expected_cursor} 4096" in delta_commands
    full_index = process.commands.index("botauto combatlog default")
    assert process.commands.index(delta_commands[-1]) < full_index
    assert result.forced_evidence_report["combat_log_delta"]["requested"] is True
    assert result.process_return_code == 0
    assert result.startup_error is None
    assert result.stable == []
    assert result.combat_log_status == native_rows[0]
    for row in native_rows:
        accepted, reasons = accepted_foundation_status(row, profile_name=profile,
            route_partition=setup.runtime_assets["route_partition"])
        assert not accepted and "native_route_completion_missing" in reasons

    if native_watchdog:
        assert process.native_trace_sent
        assert result.controller_watchdog["detected"] is False
        assert result.controller_watchdog["repeated_decision_count"] == 7
        assert result.controller_watchdog["progress_reset_count"] == 11


@pytest.mark.parametrize("artifact", ["binary", "cmake_cache"])
def test_execute_capture_run_rejects_launch_artifact_drift_before_popen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, artifact: str,
):
    binary = tmp_path / "worldserver"
    config = tmp_path / "worldserver.conf"
    server_log = tmp_path / "worldserver.log"
    binary.write_bytes(b"fixture")
    cache_path = tmp_path / "build/CMakeCache.txt"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_bytes(b"cache-fixture")
    config.write_bytes(b"fixture")
    accepted = snapshot_receipt_bound_artifacts(binary, tmp_path)
    if artifact == "binary":
        binary.write_bytes(b"mutated")
    else:
        cache_path.write_bytes(b"cache-mutated")
    setup = CaptureSetup(
        runtime_asset_closure={"complete": True, "status": "runtime_asset_closure_complete"},
        args=SimpleNamespace(
            trace_transport_smoke=False,
            max_repeated_decision_count=20,
            max_death_loop_count=3,
        ),
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
        build_provenance={
            "valid": True,
            "artifact_snapshots": {"accepted_final": accepted},
        },
    )
    popen_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def forbidden_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        raise AssertionError("Popen must not run after launch artifact drift")

    monkeypatch.setattr(
        "tools.raid_program.capture_live_run.subprocess.Popen", forbidden_popen,
    )
    result = execute_capture_run(setup)

    assert popen_calls == []
    assert result.process_return_code is None
    assert result.startup_error is not None
    assert result.startup_error.startswith(
        "infrastructure_abort:launch_artifact_provenance_drift:"
    )
    assert f"launch_artifact_provenance_drift_{artifact}" in result.last_rejections
    assert result.telemetry_abort["classification"] == "infrastructure_abort"
    assert result.telemetry_abort["reason"] == "launch_artifact_provenance_drift"


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
        runtime_asset_closure={"complete": True, "status": "runtime_asset_closure_complete"},
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
    combat_bindings = []
    monkeypatch.setattr(
        capture_finalization,
        "combined_combat_log",
        lambda payloads, **kwargs: (
            combat_bindings.append(kwargs.get("expected_status")) or "combat-log"
        ),
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
    demux_fixture_terminals = []

    def finalization_demux(*args, **kwargs):
        demux_targets.append(kwargs.get("personal_threat_episode_target"))
        demux_fixture_terminals.append(kwargs.get("fixture_terminal"))
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
    assert demux_fixture_terminals == [None]
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
        stable=[],
        combat_log_status=_native_capture_binding_statuses()[0],
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
    assert combat_bindings[-1] == abort_run.combat_log_status
    assert abort_run.stable == []
    assert abort_exit_code == 2
    assert abort_stdout_report == abort_stored_report
    assert abort_stored_report["classification"] == "infrastructure_abort"
    assert abort_stored_report["fixture_terminal"]["detected"] is True
    assert demux_fixture_terminals[-1] is abort_run.fixture_terminal
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
    assert demux_fixture_terminals[-1] is None
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
    assert scheduler.trace_interval_sec == 2.0
    commands = [command for now in range(0, 121) for command in scheduler.commands_due(float(now))]
    assert commands.count("botauto status") == 25
    assert commands.count("botauto diagnose all") == 5
    assert commands.count("botauto trace all 128 delta") == 61
    assert set(commands) == {
        "botauto status", "botauto diagnose all", "botauto trace all 128 delta",
    }


def test_default_trace_poll_drains_first_burst_after_quiet_period():
    scheduler = TelemetryScheduler()
    pending = 0
    largest_batch = 0
    # Live actor 30008 produced about 28 events/sec before the first pressure
    # response. A quiet period offers no advance warning to the adaptive path.
    for now in range(41):
        pending += 28 if 21 <= now <= 30 else 0
        assert pending <= 128, "First burst overwrote the native trace ring"
        if "botauto trace all 128 delta" in scheduler.commands_due(float(now)):
            largest_batch = max(largest_batch, pending)
            pending = 0
    assert largest_batch > 0
    assert pending == 0


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
    assert (
        accepted["route_partition"]["expected_strategy_id"]
        == "blackwing_descent_10n"
    )

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
    accepted, reasons = accepted_foundation_status(
        accepted_status(),
        route_partition={"expected_strategy_id": "blackwing_descent_10n"},
    )
    assert accepted is True
    assert reasons == []


def test_magmaw_diagnostic_accepts_only_its_materialized_roster_identity():
    status = accepted_status()
    runtime = status["raid_runtime"]
    profile = "blackwing_descent_10n_magmaw_diagnostic"
    _materialize_profile_identity(status, profile)
    runtime["strategy_id"] = "tank_swap_adds_raid_aoe"
    runtime["route_progress"] = {"generation": 4, "node_index": 3}
    _completed_boss_partition(status)
    root = Path(__file__).parents[1]
    assets = validate_runtime_profile_assets(
        root, root, profile_name=profile, scenario_id=profile,
        require_dvc_lineage=False,
    )
    assert assets["passed"], assets["reasons"]
    partition = assets["route_partition"]
    assert partition["terminal_target_entry"] == 41570
    assert partition["expected_strategy_id"] == "tank_swap_adds_raid_aoe"
    accepted, reasons = accepted_foundation_status(
        status,
        profile_name=profile,
        route_partition=partition,
    )
    assert accepted is True
    assert reasons == []

    runtime["strategy_id"] = profile
    accepted, reasons = accepted_foundation_status(
        status,
        profile_name=profile,
        route_partition=partition,
    )
    assert accepted is False
    assert "strategy_owned" in reasons


def _completed_boss_partition(status):
    node = "bwd.magmaw.encounter"
    evidence = {"route_node_id": node, "route_generation": 4,
                "route_kind": "boss", "target_entry": 41570}
    status["validation_route"] = {
        "node_id": node, "kind": "boss", "generation": 4,
        "manifest_index": 3, "manifest_count": 4, "manifest_complete": True,
        "terminal_evidence": [{**evidence, "target_id": 0, "result": "boss_killed"}],
        "boss_death_evidence": [{**evidence, "target_id": 12345,
                                 "result": "confirmed_unit_death"}],
    }
    return {"node_count": 4, "terminal_index": 3, "node_ids": [node],
            "terminal_kind": "boss", "terminal_target_entry": 41570,
            "expected_strategy_id": "tank_swap_adds_raid_aoe"}


@pytest.mark.parametrize("mutation,reason", [
    ("arrival", "native_route_completion_missing"),
    ("missing_terminal", "native_terminal_evidence_missing"),
    ("missing_death", "native_terminal_boss_death_missing"),
    ("wrong_boss", "native_terminal_boss_death_missing"),
    ("stale_generation", "native_terminal_boss_death_missing"),
    ("wrong_node", "native_terminal_boss_death_missing"),
    ("unconfirmed_death", "native_terminal_boss_death_missing"),
])
def test_boss_partition_rejects_arrival_and_unrelated_death(mutation, reason):
    status = accepted_status()
    profile = "blackwing_descent_10n_magmaw_diagnostic"
    _materialize_profile_identity(status, profile)
    status["raid_runtime"]["strategy_id"] = "tank_swap_adds_raid_aoe"
    partition = _completed_boss_partition(status)
    route = status["validation_route"]
    if mutation == "arrival":
        route.update(manifest_complete=False, terminal_evidence=[], boss_death_evidence=[])
    elif mutation == "missing_terminal":
        route["terminal_evidence"] = []
    elif mutation == "missing_death":
        route["boss_death_evidence"] = []
    else:
        field, value = {"wrong_boss": ("target_entry", 42180),
                        "stale_generation": ("route_generation", 3),
                        "wrong_node": ("route_node_id", "other.encounter"),
                        "unconfirmed_death": ("result", "target_absent")}[mutation]
        route["boss_death_evidence"][0][field] = value
    accepted, reasons = accepted_foundation_status(status, profile_name=profile,
                                                   route_partition=partition)
    assert not accepted
    assert reason in reasons


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
    runtime["strategy_id"] = "tank_swap_adds_raid_aoe"
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
        route_partition={
            "node_count": 4,
            "terminal_index": 3,
            "expected_strategy_id": "tank_swap_adds_raid_aoe",
        },
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
    accepted, reasons = accepted_foundation_status(
        status,
        route_partition={"expected_strategy_id": "blackwing_descent_10n"},
    )
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


@pytest.mark.parametrize("readycheck_mode", ["claimed_action", "zero_wipe", "post_wipe_pending"])
def test_live_evidence_demux_requires_only_applicable_native_readycheck(readycheck_mode):
    active = accepted_status()
    active["cohort_id"] = "default"
    active["active_profile"] = "blackwing_descent_10n"
    runtime = active["raid_runtime"]
    if readycheck_mode != "claimed_action":
        runtime["native_recovery"]["ready_check_action_observed"] = False
        runtime["native_recovery"]["ready_check_action_generation"] = 0
    if readycheck_mode == "post_wipe_pending":
        active["validation_route"] = {"generation": 4, "node_id": "boss"}
        runtime.update(
            wipe_generation=1, native_recovery_hold_active=True,
            native_recovery_route_generation=4, native_recovery_node_id="boss",
            native_hostile_activity_active=False, boss_reset_generation=1,
        )
        runtime["native_recovery"].update(
            death_observed=True, corpse_observed=True, release_observed=True,
            resurrection_observed=True, runback_observed=True,
        )
        assert ready_for_native_readycheck(active)
    bots = [{"bot_guid": 1001 + index, "entries": []} for index in range(10)]
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
    expected_required = readycheck_mode != "zero_wipe"
    assert ("evidence_demux_required_action_missing:botauto_readycheck"
            in report["rejections"]) is expected_required
    assert report["gate_passed"] is not expected_required, report["rejections"]


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


@pytest.mark.usefixtures("verified_runtime_asset_capture_gate")
def test_generic_profile_range_capture_preflight_uses_verified_bundle_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    fixture = _generic_profile_range_fixture(tmp_path)
    monkeypatch.setattr(
        prestart_bundle, "_verify_gate_bearing_build_receipt",
        lambda *args, **kwargs: {"valid": True, "gate_bearing": True},
    )
    _create_prestart_bundle(fixture)
    bundle = fixture["output"]
    paths = fixture["paths"]
    root = fixture["root"]

    monkeypatch.setattr(
        "tools.raid_program.capture_setup.preflight_runtime_exclusions",
        lambda worktree: {"passed": True, "reasons": []},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.validate_runtime_profile_assets",
        lambda *args, **kwargs: {
            "passed": True,
            "reasons": [],
            "route_manifest": str(bundle / "route_manifest.json"),
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
        lambda build_receipt, worktree: bundle / "build_policy.json",
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.validate_build_receipt",
        lambda *args, **kwargs: {"valid": True, "rejections": []},
    )

    setup = prepare_capture_setup([
        "--binary", str(paths["binary"]),
        "--config", str(bundle / "worldserver.validation.conf"),
        "--output", str(tmp_path / "capture.json"),
        "--build-receipt", str(bundle / "build_receipt.json"),
        "--worktree", str(root),
        "--recurrence-admission", str(bundle / "recurrence_admission.json"),
        "--recurrence-admission-sha256", sha256_file(
            bundle / "recurrence_admission.json"
        ),
        "--profile-combat-range-checkpoint-actor-guid", "30010",
        "--profile-combat-range-checkpoint-target-guid", "39",
        "--fixture-expansion-replay",
        "--scenario-id", "blackwing_descent_10n_magmaw_diagnostic",
        "--runtime-profile", "blackwing_descent_10n_magmaw_diagnostic",
        "--pool-tag", "blackwing_descent_10n_magmaw_diagnostic",
    ], root=root)

    assert setup.recurrence_admission is not None
    assert setup.recurrence_admission["valid"] is True
    assert setup.recurrence_admission["checkpoint_fixture_id"] == (
        PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID
    )
    assert setup.recurrence_admission["checkpoint_actor_guid"] == 30010
    assert setup.recurrence_admission["checkpoint_target_guid"] == 39
    assert setup.checkpoint_target_guid == 39
    assert setup.controller_route_hold_scheduler is not None


@pytest.mark.usefixtures("verified_runtime_asset_capture_gate")
def test_build_control_capture_uses_only_admission_bound_layered_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    fixture = _generic_profile_range_fixture(tmp_path)
    authority = _add_layered_build_control_authority(fixture, tmp_path)
    monkeypatch.setattr(
        prestart_bundle, "_verify_gate_bearing_build_receipt",
        lambda *args, **kwargs: {"valid": True, "gate_bearing": True},
    )
    _create_prestart_bundle(fixture)
    bundle = fixture["output"]
    paths = fixture["paths"]
    root = fixture["root"]
    admission_value = json.loads(
        (bundle / "recurrence_admission.json").read_text(encoding="utf-8")
    )
    expected_compatibility = admission_value["build_control_compatibility"]
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        "tools.raid_program.capture_setup.preflight_runtime_exclusions",
        lambda worktree: {"passed": True, "reasons": []},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.validate_runtime_profile_assets",
        lambda *args, **kwargs: {
            "passed": True, "reasons": [],
            "route_manifest": str(bundle / "route_manifest.json"),
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
        lambda build_receipt, worktree: bundle / "build_policy.json",
    )

    def capture_build_validation(*args, **kwargs):
        observed.update(kwargs)
        return {"valid": True, "rejections": [], **expected_compatibility}

    monkeypatch.setattr(
        "tools.raid_program.capture_setup.validate_build_receipt",
        capture_build_validation,
    )
    setup = prepare_capture_setup([
        "--binary", str(paths["binary"]),
        "--config", str(bundle / "worldserver.validation.conf"),
        "--output", str(tmp_path / "capture.json"),
        "--build-receipt", str(bundle / "build_receipt.json"),
        "--worktree", str(root),
        "--recurrence-admission", str(bundle / "recurrence_admission.json"),
        "--recurrence-admission-sha256", sha256_file(
            bundle / "recurrence_admission.json"
        ),
        "--profile-combat-range-checkpoint-actor-guid", "30010",
        "--profile-combat-range-checkpoint-target-guid", "39",
        "--fixture-expansion-replay",
        "--scenario-id", "blackwing_descent_10n_magmaw_diagnostic",
        "--runtime-profile", "blackwing_descent_10n_magmaw_diagnostic",
        "--pool-tag", "blackwing_descent_10n_magmaw_diagnostic",
    ], root=root)

    copied = bundle / prestart_bundle.BUNDLE_NAMES["build_control_authority"]
    assert setup.build_provenance["valid"] is True
    assert observed["build_control_authority"] == copied.resolve()
    assert observed["build_control_authority_sha256"] == sha256_file(copied)
    assert copied.read_bytes() == authority.read_bytes()
    source = Path(
        prestart_bundle.__file__
    ).with_name("capture_setup.py").read_text(encoding="utf-8")
    assert 'parser.add_argument("--build-control-authority"' not in source


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("missing_admission", "magmaw_recurrence_admission_required"),
        ("unverified_admission", "recurrence_admission:fixture_expansion_not_admitted"),
        (
            "identity_mismatch",
            "recurrence_admission:profile_combat_range_checkpoint_seal_identity_mismatch",
        ),
        ("multiple_dialects", "multiple_checkpoint_actor_dialects"),
    ],
)
@pytest.mark.usefixtures("verified_runtime_asset_capture_gate")
def test_generic_profile_range_capture_preflight_fails_closed_on_admission_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str, reason: str,
):
    fixture = _generic_profile_range_fixture(tmp_path)
    monkeypatch.setattr(
        prestart_bundle, "_verify_gate_bearing_build_receipt",
        lambda *args, **kwargs: {"valid": True, "gate_bearing": True},
    )
    _create_prestart_bundle(fixture)
    bundle = fixture["output"]
    paths = fixture["paths"]
    root = fixture["root"]
    admission_path = bundle / "recurrence_admission.json"
    if mutation == "unverified_admission":
        admission = json.loads(admission_path.read_text(encoding="utf-8"))
        admission["fixture_expansion_admitted"] = False
        admission_path.write_text(json.dumps(admission), encoding="utf-8")
    elif mutation == "identity_mismatch":
        admission = json.loads(admission_path.read_text(encoding="utf-8"))
        admission["checkpoint_seal"]["target_guid"] = 40
        admission_path.write_text(json.dumps(admission), encoding="utf-8")

    monkeypatch.setattr(
        "tools.raid_program.capture_setup.preflight_runtime_exclusions",
        lambda worktree: {"passed": True, "reasons": []},
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.validate_runtime_profile_assets",
        lambda *args, **kwargs: {
            "passed": True,
            "reasons": [],
            "route_manifest": str(bundle / "route_manifest.json"),
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
        lambda build_receipt, worktree: bundle / "build_policy.json",
    )
    monkeypatch.setattr(
        "tools.raid_program.capture_setup.validate_build_receipt",
        lambda *args, **kwargs: {"valid": True, "rejections": []},
    )

    argv = [
        "--binary", str(paths["binary"]),
        "--config", str(bundle / "worldserver.validation.conf"),
        "--output", str(tmp_path / "capture.json"),
        "--build-receipt", str(bundle / "build_receipt.json"),
        "--worktree", str(root),
        "--recurrence-admission", str(admission_path),
        "--recurrence-admission-sha256", sha256_file(admission_path),
        "--profile-combat-range-checkpoint-actor-guid", "30010",
        "--profile-combat-range-checkpoint-target-guid", "39",
        "--fixture-expansion-replay",
        "--scenario-id", "blackwing_descent_10n_magmaw_diagnostic",
        "--runtime-profile", "blackwing_descent_10n_magmaw_diagnostic",
        "--pool-tag", "blackwing_descent_10n_magmaw_diagnostic",
    ]
    if mutation == "missing_admission":
        argv = argv[:argv.index("--recurrence-admission")]
        argv.extend([
            "--profile-combat-range-checkpoint-actor-guid", "30010",
            "--profile-combat-range-checkpoint-target-guid", "39",
            "--fixture-expansion-replay",
            "--scenario-id", "blackwing_descent_10n_magmaw_diagnostic",
            "--runtime-profile", "blackwing_descent_10n_magmaw_diagnostic",
            "--pool-tag", "blackwing_descent_10n_magmaw_diagnostic",
        ])
    elif mutation == "multiple_dialects":
        argv.extend([
            "--chainwielder-checkpoint-actor-guid", "30008",
        ])

    with pytest.raises(SystemExit, match=reason):
        prepare_capture_setup(argv, root=root)


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


@pytest.mark.parametrize(
    ("mutation", "expected_rejection"),
    [
        ("valid", None),
        ("moved", "build_receipt_worktree_mismatch"),
        ("dirty", "build_worktree_dirty"),
        ("drifted", "build_worktree_source_identity_mismatch"),
        ("artifact_binary", "build_artifact_concurrent_drift_binary"),
        ("artifact_cmake", "build_artifact_concurrent_drift_cmake_cache"),
    ],
)
def test_build_receipt_binds_current_build_worktree_identity_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    mutation: str, expected_rejection: str | None,
) -> None:
    source_worktree = tmp_path / "immutable-source"
    build_worktree = tmp_path / "retained-build"
    binary = build_worktree / "build/src/server/worldserver/worldserver"
    binary.parent.mkdir(parents=True)
    source_worktree.mkdir()
    binary.write_bytes(b"\x7fELFfixture")
    cache_path = build_worktree / "build/CMakeCache.txt"
    expected_cmake = {
        "CMAKE_BUILD_TYPE": "Release",
        "CMAKE_GENERATOR": "Unix Makefiles",
        "CMAKE_MAKE_PROGRAM": "/usr/bin/make",
        "CMAKE_EXPORT_COMPILE_COMMANDS": "OFF",
        "CMAKE_CXX_FLAGS": "",
        "CMAKE_CXX_FLAGS_RELEASE": "-O2",
        "CMAKE_CXX_COMPILER": "/usr/bin/c++",
        "CMAKE_CXX_COMPILER_LAUNCHER": "",
        "CMAKE_INTERPROCEDURAL_OPTIMIZATION": "OFF",
        "CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE": "OFF",
        "UNITY_BUILDS": "OFF",
        "USE_COREPCH": "OFF",
        "USE_SCRIPTPCH": "OFF",
        "WITH_COREDEBUG": "OFF",
    }
    cache_path.write_text(
        "".join(f"{key}:STRING={value}\n" for key, value in expected_cmake.items()),
        encoding="utf-8",
    )
    receipt_path = tmp_path / "receipt.json"
    policy_path = tmp_path / "policy.json"
    receipt_path.write_text("{}", encoding="utf-8")
    policy_path.write_text("{}", encoding="utf-8")

    empty_porcelain = hashlib.sha256(b"").hexdigest()
    expected_identity = {
        "commit": "1" * 40,
        "tree": "2" * 40,
        "clean": True,
        "dirty": False,
        "porcelain_sha256": empty_porcelain,
    }
    observed_identity = dict(expected_identity)
    if mutation == "dirty":
        observed_identity.update(
            clean=False, dirty=True,
            porcelain_sha256=hashlib.sha256(b" M tracked\0").hexdigest(),
        )
    elif mutation == "drifted":
        observed_identity["commit"] = "3" * 40

    build_stage = {
        "settings": expected_cmake,
        "matches_policy": True,
        "settings_sha256": "8" * 64,
        "cache_sha256": sha256_file(cache_path),
        "compiler_sha256": "9" * 64,
        "build_graph": {"generated": True, "manifest_sha256": "a" * 64},
    }
    receipt = {
        "classification": "success",
        "test_mode": False,
        "exit_code": 0,
        "worktree": str(
            tmp_path / "moved-build" if mutation == "moved" else build_worktree
        ),
        "worktree_dirty_at_request": False,
        "source_identity": {
            stage: dict(expected_identity)
            for stage in ("request", "admission", "completion")
        },
        "build_configuration": {
            stage: json.loads(json.dumps(build_stage))
            for stage in ("request", "admission", "completion")
        },
        "build_configuration_stable": True,
        "configure_lineage": {
            "completion_cache_sha256": build_stage["cache_sha256"],
            "completion_settings_sha256": build_stage["settings_sha256"],
            "compiler_sha256": build_stage["compiler_sha256"],
            "completion_build_graph_sha256": build_stage["build_graph"][
                "manifest_sha256"
            ],
            "receipt_sha256": "b" * 64,
            "ticket_id": "fixture-ticket",
        },
        "commit": expected_identity["commit"],
        "admitted_at_utc": "1970-01-01T00:00:00Z",
        "ended_at_utc": "2999-01-01T00:00:00Z",
        "output_artifacts": [{
            "kind": "worldserver_elf",
            "path": str(binary),
            "sha256": sha256_file(binary),
            "size_bytes": binary.stat().st_size,
            "mtime_ns": binary.stat().st_mtime_ns,
            "produced_by_ticket": True,
        }],
    }
    policy = {
        "mechanical_controls": {
            "cmake_release_cxx_flags": "-O2",
            "cmake_build_type": "Release",
            "cmake_generator": "Unix Makefiles",
            "cmake_make_program": "/usr/bin/make",
            "cmake_export_compile_commands": False,
            "cmake_cxx_flags": "",
            "cmake_cxx_compiler": "/usr/bin/c++",
            "cmake_cxx_compiler_launcher": "",
            "interprocedural_optimization": False,
            "release_interprocedural_optimization": False,
            "unity_builds": False,
            "core_precompiled_headers": False,
            "script_precompiled_headers": False,
            "with_coredebug": False,
        }
    }
    compatibility = {
        "valid": True,
        "rejections": [],
        "build_source_commit": expected_identity["commit"],
        "build_source_tree": expected_identity["tree"],
        "control_commit": "4" * 40,
        "control_tree": "5" * 40,
        "relationship": "control_only_descendant",
        "changed_control_path_count": 7,
        "changed_control_paths_sha256": "6" * 64,
        "layered_authority": {"sha256": "7" * 64},
    }
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        "tools.raid_program.queued_build.load_json",
        lambda path: policy if path == policy_path else receipt,
    )
    monkeypatch.setattr(
        "tools.raid_program.queued_build.verify_receipt",
        lambda *args, **kwargs: {
            "classification": "success",
            "receipt_trust_model": "fixture",
            "operator_identity": "fixture",
        },
    )

    def source_compatibility(**kwargs) -> dict[str, object]:
        observed["compatibility_worktree"] = kwargs["worktree"]
        return compatibility

    monkeypatch.setattr(
        "tools.raid_program.capture_environment_validation.verify_build_control_compatibility",
        source_compatibility,
    )
    identity_worktrees: list[Path] = []
    identity_calls = 0

    def build_identity(worktree: Path) -> dict[str, object]:
        nonlocal identity_calls
        identity_calls += 1
        if identity_calls == 2 and mutation == "artifact_binary":
            binary.write_bytes(b"\x7fELFchanged")
        elif identity_calls == 2 and mutation == "artifact_cmake":
            cache_path.write_text(
                "".join(
                    f"{key}:STRING={('Debug' if key == 'CMAKE_BUILD_TYPE' else value)}\n"
                    for key, value in expected_cmake.items()
                ),
                encoding="utf-8",
            )
        identity_worktrees.append(worktree)
        return {
            "head": observed_identity["commit"],
            "tree": observed_identity["tree"],
            "clean": observed_identity["clean"],
            "dirty": observed_identity["dirty"],
            "porcelain_sha256": observed_identity["porcelain_sha256"],
        }

    monkeypatch.setattr(
        "tools.raid_program.capture_environment_validation.git_identity",
        build_identity,
    )

    result = validate_build_receipt(
        receipt_path,
        policy_path,
        source_worktree,
        binary,
        build_worktree=build_worktree,
    )

    assert observed["compatibility_worktree"] == source_worktree.resolve()
    assert identity_worktrees == [build_worktree.resolve(), build_worktree.resolve()]
    assert result["source_worktree"] == str(source_worktree.resolve())
    assert result["build_worktree"] == str(build_worktree.resolve())
    assert result["build_worktree_identity"] == observed_identity
    assert result["build_source_commit"] == compatibility["build_source_commit"]
    assert result["control_commit"] == compatibility["control_commit"]
    assert result["relationship"] == compatibility["relationship"]
    assert result["layered_authority"] == compatibility["layered_authority"]
    if expected_rejection is None:
        assert result["valid"] is True
        assert result["rejections"] == []
    else:
        assert result["valid"] is False
        assert expected_rejection in result["rejections"]
    if mutation.startswith("artifact_"):
        assert result["artifact_snapshots"]["accepted_final"] == result[
            "artifact_snapshots"
        ]["post_final_identity"]
        assert result["binary_sha256"] == result["artifact_snapshots"][
            "accepted_final"
        ]["binary"]["sha256"]


def test_canonical_capture_is_terminal_gate_driven_without_a_raid_duration_cap():
    root = Path(__file__).resolve().parents[1] / "tools/raid_program"
    setup_source = (root / "capture_setup.py").read_text(encoding="utf-8")
    live_source = (root / "capture_live_run.py").read_text(encoding="utf-8")
    finalization_source = (root / "capture_finalization.py").read_text(encoding="utf-8")
    assert '"--observe-sec", type=int, default=0' in setup_source
    assert 'parser.add_argument("--semantic-stall-sec", type=int, default=300)' in setup_source
    assert 'parser.add_argument("--telemetry-timeout-sec", type=int, default=60)' in setup_source
    assert '"--diagnose-interval-sec", type=float, default=30.0,' in setup_source
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


def test_monotonic_semantic_progress_ignores_friendly_damage_for_high_water_mark():
    status = accepted_status()
    status["validation_route"] = {
        "node_id": "bwd.magmaw.encounter",
        "generation": 4,
        "manifest_index": 3,
    }

    def diagnosis_for(party_damage: int, friendly_damage: int) -> dict:
        return {
            "combat_metrics": {
                "schema": "bot_combat_metrics_v3",
                "measurement_basis": "hostile_originated_damage",
                "route_generation": 4,
                "route_node_id": "bwd.magmaw.encounter",
                "party_damage": party_damage,
                "party_friendly_damage": friendly_damage,
                "party_raw_event_friendly_damage": friendly_damage,
            },
        }

    state: dict = {}
    assert observe_monotonic_semantic_progress(
        state, status, diagnosis_for(1000, 0),
    ) is True
    assert observe_monotonic_semantic_progress(
        state, status, diagnosis_for(1000, 700),
    ) is False
    assert state["originated_party_damage_high_water"]["4:bwd.magmaw.encounter"] == 1000
    assert observe_monotonic_semantic_progress(
        state, status, diagnosis_for(1100, 700),
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
        bot_guid=2001,
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
        bot_guid=2007,
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
        bot_guid=2007,
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
        bot_guid=2007,
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
            for bot_guid in (2001, 2002)
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
            bot_guid=2001,
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
        bot_guid=2001,
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


@pytest.mark.usefixtures("verified_runtime_asset_capture_gate")
def test_magmaw_capture_requires_recurrence_admission_before_start(tmp_path: Path):
    config = tmp_path / "worldserver.conf"
    receipt = tmp_path / "build.json"
    config.write_text("BotWorld.AutoStart = 0\n", encoding="utf-8")
    receipt.write_text("{}\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="magmaw_recurrence_admission_required"):
        prepare_capture_setup([
            "--binary", "/bin/true", "--config", str(config),
            "--output", str(tmp_path / "report.json"),
            "--build-receipt", str(receipt),
            "--worktree", str(Path(__file__).resolve().parents[1]),
            "--scenario-id", "blackwing_descent_10n_magmaw_diagnostic",
        ])
    assert not (tmp_path / "report.json").exists()


def _native_capture_binding_statuses():
    """Exact run88 first active statuses per route node, read from native stdout.

    Raw JSON sha256: 27bb051c1a63bdd6c099003a9b17f41d2a88c28b43e0e66759f99bbe1ba9c7fd
    Collection includes regroup, chainwielder, drudges, and uncompleted Magmaw.
    """
    import zlib
    encoded = (
        "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"
        "8WvZTXQ/jXH6phWaocP8XOmbDvNDMxjiNipaYVL8tqWZdjwxxlHREpCQ05dmzscWA53okgJl5M2LM+2oYm4TXVZguZu+10yrc7HF"
        "KCu6sUAxfbJDy08qLjvEbaILKqSX1y7OtGOIWU10PwUMZGP3mp0sa7hBJhPdvaBGLtGdK4sOk4mvXLhu2Wdwlxlv37Zw10WZ6KaF"
        "ey7KKBstyphrF2WiLO80bHf/XWZqmNTo+OiivK4G2VHE5iMK1Zfb19Vqnm/W+9eXNFuhejskLX8uX9KayPR4mn/mpAUP2H/XCMon"
        "lUh8/dciXa5aL/clBAChbWj3167cl7vPrdfpAazaNnaS+PxTuS6DPEl1Jdjr4fQhxjlPD3McM1mI9XUHfAzsRS/vIKEv5UtW7qqq"
        "9TldLYugeQJm5p+2m+Waxt1yjbYdU7R9hhwL94uFF2BDvoFkfSoRuXwA1PgBnpW/A3Y5lMW8iYXVMc4rQofkboUw5/g3mDLfLODB"
        "SwZpPz6HYnyBsFoPgKx9ijxs2q+xcDbtAEJ+tCNezeNy2ZWhLhz9tPLnzz+h5rykTy/pl/lhl673CzBjla5LpIfF5gtmVF2x6oLd"
        "vO5yzPDPy31dKgdIdNOUD1hJ5gOPWsmAckDYCnmyTXdLKL2AgiC6zW5+XABEFZvGC6Znk3XqEmQu+MCyW5fLwzNYsMX6tsab4ba7"
        "zXazT1dt8zefiQPPe96lL9ny6XXzuj+a26oDWCUoW+Z5ui6wWrXerMqnNP/a96b6pm0Ya/x3nlZ+yy1YW5zU/uotZWTnVRUc0Hew"
        "rPOuqbOVJyrpJbWJ/ggKwKbLdfUYiuQztDJsFE2u/P7uwxo6ieTd1/rHH+HHn01KbgqjgBoHHdw6L0M1BRuqHEnz/PXldZVCrrUr"
        "ZwigqmlxtWs3lupJuk1zIiTc/Imdc7fOibc691bnvnGdk2917q3OfeM6p97q3Fud+8Z1Tr/Vubc6943rnHmrc2917hvXOftW597q"
        "3Deuc+6tzr3VuW9c5/xbnXurc9+2zuE63Fude6tzj6tzH4eWRSib09fD82ZHnpvVrqeXsJjxShtT/v1uf0h3hzIU4O51vV6un0Ju"
        "vuZgQLR4FZZQli8lVFpa/2wvWtEqWLReFRb46i0k8216eMZlqxSSVh7+3vp0n8M3u+Vm//duePv3/4SGs8LNf8XnFHJ0/gL5CKEc"
        "yt0LFBC+aSJYrovy99BK6kdV9tHWg2Nd4ZGPl+2qPBxLtg4ZaiNug8nLUCDZZr+HagE2dF7km/UhfakqS+ddE8tqkxbzcrfDcqdW"
        "VVkctm1mqzT/9AUyHutdjsXD2XpeFWuxTJ/WG6iOeLfFGmtR+OZL8Z5WZN/vyrC5EipvmuGeSNyn+V/4DjPsv/75uqaLLf7r6O8T"
        "5BSuolYPoBz3h9f8E2VdUea0XBYVfP8SZqju0Kd9qss6zUMGQ24doO5t5lC5Dq+00XMDFbHapVqUi/R1hR0c9YU76DA2OVQN5xW3"
        "zFtpUCQODwG0F1859YeL5SruWFqPsSQw857TPVY09bP++SdrflK/efeT/JX/6oWU7ud/OOt++eUn5ZmUv2n1D8b0P3769ZdffzX6"
        "t99+NT8x+ctv/jfnf3lXL1XPqwgmlVS0lsmrfmy3xMaH28sgc9abl69zCAv7LNwsBo3v3QdNfTxV8XT1Jf26n0Olqn1TBVjP83J3"
        "WC6+YirS/X4JeUwVrqq/WNXKYn7MlJACccynoRYJhTaHRGADrz/f/73+QQ3xXU8g3aq93WxW0Ps8zcEbnjuckmnl75DjkKzdAcai"
        "ZjdwtTqb7dIl1q3Xw3KFe9NorT/eTAAW7ENuQ6f2VB7mxwfF667qbGi9P9ToT8vVal9Ve8iLfbWVId3NX7dPO8jH8ORfr2DoHnvv"
        "clt3ldWzuvtoPZxvsn+WTcV52tWdKG1aoG7kGC2M95tlPu97Rc8OtA0aWnkYGytbaE83Fv3T+iU8xTO61JjnuFBPhlZPKZj2w1bu"
        "bKEHwtFhHjd6XO/e7V6h3bXHgBAf1Kz+15U4W5Qqimn9aQ5AhQbsemipOp592A8O5QGdwNFCSkGo1LQd49DKj6p6tgfPUPLNF3Xf"
        "Br5p1HhZ7tGyeb1rovqs6XugiML+AKyfx8GgqU/z0Kft551hrfmu2WHRbuyhLAIwEkIbySSeHeSorqRwbw50D0XZ2T3QIJ398o8y"
        "hFNvQz0+WMV/V0cAuglvgiqWi8Uyh972a6jblK7Ow5f05NHxzx7j2i/TQ/6MOXfWF+7zyKAPOElmNyRsbzVq2FKvb3AjX1O4lQY4"
        "3s+EG1X26efm2fc+lGCI0G6xjYT9Qs+bVUGMoBk9ezb2tIfNk/GSnexOimFFGFPa3Xn1kOJvOnCAzVBD26969zcdoUfodtvAf7H8"
        "/YDI4JjOcG6jCbfaiwPl/7I8hEeQIYvl03GrccyTjn1ta9cWRrFYlphv7SiP8YcwX3c0/gUW1XxfecHNYWD1GR+dmki2nAmY3g+H"
        "Sq+7Qda5MRxovXdpMNjgoRNwBjB097XZ8nT8qv91GBbmBLqH/FQxzEOETfyttFdJWZXrp8Nz1b/XyT591w2/fsUFbQ2knXttTrt7"
        "mYeeo35y3ByH6PKp22CObxuK0KT5+K6pdduTDX8tXytoIPnXfFVWPKkb2UkMyzWN/IjRmvQedsunpxIzKiPCjP13aFEBftW0I/JG"
        "m+2qfiL9I93BHyXtvmz2ylURUQ/yZU04K/jE0wzpoW7qrd2GW+CFa+x+yrxc1n0GZHqGezQBTyxwIDmTMcEfRthMQtQxAyotW3AZ"
        "SVJVqepdlK03NQUd9gHMBbo5nNyooHAn7Aq+NN1P+12nR2y/6tu72X7f2/mdeuh2hM3rzqRBoKJhPP0jZHWxKZ6gdqc0ZjfJD08B"
        "6a5W8+gRdt6regNpeJQBOCXgH8wMsydpheXnoVq09phim1oQCn8rtR+q1I7TgvjX6dbY/esWW+i+6SbSbr9z6qOaQWl1rqG7LVrb"
        "lEPPc/y7mQ05PqoSU5zZ3FxNhB3JQBdn1dMkUK1gqCD6ytpoveqjCAnEwO0SzruIvLtgMmCSw9Eebp1z1lsv6GLoHg4wp63RAcpU"
        "I/qV8zmn+Gz8t0fkBPx9tXmqB9sGd9lCpVyW0siUF6bMvMxtwVPhIcN8ngqeLyTPfMEKKcwi184VWijJc6WzgpnsDFRUzGhh89yU"
        "wqpFQVqlbKEznhWCZ87kssAomBKZyhaFSLWTkgmdlaJQutTv2ryvmqmCUa9M59U4WDepU18N8tkO+6m6mpaf5lVELJqn0Or/JpV+"
        "72qFI3oKvcDfhFDvZX24jZ5Cr8C9fN/chkEPN9Wu92/MKvpoJO6sz193u9Ds0l0D4Zrm1ZCsZn/9v99FQVxFX/tPo9MEAJ3KCOe+"
        "8e93nbPekD+HCjdt01VaLNfR0XCRtI9jtqZ5t7vlC4LJ6lzpYVeGVu2kbz6p3lWdHl4vFr+oO3A6IcnwgCG41oOL5yWhC0DXMG7Q"
        "xXv68RJBdI1LtNReg2sYQ9fjhTMWuK+RRrkE+iWFBzMNdEt49o6Ta/CoJsoDaKZk4iy3Glxl8LTMtuwi0xbiDy+D3fCzOo1T/UVD"
        "+nFswkfBsNaJjPpZtkHK+b8fO48ivoZvcNYRB70oi+oTonWVpoLuLb9wkBSPBNWTArZ6eDxU2j5LWp0eCpfjnB4wik5e9epCOxLx"
        "5R+js6PHUKXquU3ufKgfo8OirQRapScGBUmTLCH3Y3Q09Biq5T0n5y6GqviJ2TpKq3P+mrR+jM55tm3n4vpUnuSAjcJWkl8bdhSq"
        "iwpea359wfsoKMvsjZnJWcfiq3LzY3wWs13LewQ4RhvL42rO2A0tBg9btiq3v6X18bihVLIJt2Ra3EaU9TckLm4fSrm79A08ahrK"
        "OnldzfvY6XVbIE7muZMiM1alMnMqT+ETt9CFLjwrnZVSlDjc49lusxAs58aKRcmzhTYlc6hW1sEZD4ghvo+gjm8Y0pybNx6aFd+u"
        "0q8wfF6eFt9v0y/rGCyGRxFSDI/aMDE8CRixu+5wXFJYrpeHJVCtDNjVarlGzrp7Abr9x6mXahnggFs1ILTlYtm+Fyg6H3ZvLCfO"
        "Y7lshQdBw0L5p/Xy6fkQYTkzFctJ74awHDuH5ZTzTiQAooUDl+678Hg7tfIaLzoH16Or8Lk26Af12TUDAJdogZeea4k3XWkNoDxx"
        "dH2fo8viHF3d5egeLAc5qRJPF1N4pbX+gVFcb8mdojgzGsU5+52jOM3vj+Kc0f6O+OjRWM5cj7d+cCznjHVvWO7/Ipa7JdMeDrpg"
        "7PCZFwumbGkzbjKtcqtEqvUidSw1hcwVs8KzRWm4LxZplhbCwDCWp3JROH8ZdN0hhjfQdQvokncFXdXGmtYUWnjSBV4ANA6bao9T"
        "sXuldfEj7uJ8KvAivcV+4CXOAS9unMR7zaAhJtwy0p9h2qBrGbnw1tI9aBYFI6REhUx06TdANKnxZi/lFCQaXImiMlrhDWioS6Ot"
        "wyk2LvEGNGfxvjMobrz1TAmJUppG/cAgrK8Ub8FgPRoZlzGYJzCihjBY78VrV8+ksSu6f3WSwA4GMzeEehJ2Z3wR90lxF4ndM8Vd"
        "JKbukmIXVwJ7DdpRw3DMXZEDUp6BY57fmMAYjvXebDYxwC4m4/fCZL33l12JyaQRt0CoTnPh7tZM62IydV2Aw5gs46lMF7I0hVKZ"
        "5mnGRJpql3Jl88KZNJMysza1RS41/DOpFyzPvOPeLBZFVlzGZHeI4Q2T3YLJ1CMwmbiEyZ43q6/3WtLkV02DCQBgFpc0YZwVTMBI"
        "ILkTHF0ljsuYwKrRxQVMyBh0LfxWeH9oWMx0GqfQAIYZUgP0HlwN3RlOIah6GdNhyB5y1f7ACKxTZjctY4rvHXyZB4AvK8zjwJc0"
        "DwFf9mHgSxr+APClmLkr+FLmPhDxDYJ9jxDMmvutbkr53cO5gsmSM5G5POUAr3hp4bnJC0BgTqalsbnx8D+Z5qLMciZU7nOfOZ2m"
        "jJd5wS7DuTvE8AbnboFz+hFwTl6Cc8Vyny+3ZALgNBz625hOT55hM+wqTMcZQ/0AZXGGDRq3Q9fxhGvJ4LfT0EY5ToQlkB0G59YE"
        "Q3FmDf0Cuqj2rCW5zqFSGuSWtqh2jAIELrEOl0idVzi35lGZyAvhf2RM11dwN8yqWfbdz6rZBwA7lMB7FLCTnj8E2PnHzaop/whg"
        "dx0UPTOrduss3Ruk+w+YVeuVWr6UuGEEZguZGyut9gaSynyey0WewqAjjFxoky8WC73IeVmUaa5N5he5yxeZMcLn6QKGscsI7A4x"
        "vCGwWxCYuSsCQ1G61gpnWxyuwl6LJR3NfSojzOUmz6Pp6+bROKcVS9Imxf1fgLyE1OgCd0bXwlvhtSTNJp0A8ALiL4PmNIz+El1F"
        "v5VDF77VykqVOCXwOIBCjSforh0gL+M5/vbK/8CY68vmy375sqfTSfOtmrcL8CbsxfukpTqim2e1pgYAmGUXttuQxNF4COb6JKQ6"
        "UqdnRYqGJ9h8n2rUpaR29F+UuBqM9WXwqbrMICjrLqAGbag4Z8yk5F9AZpA/apIF4+FZUIAalfYzk2+8T/TpuvR24doFdDVYB88A"
        "tsl7Ck4CFJ3tZPqOW9P4HbemuT7lpqmFHUO3IbGmia03jmEalutL9Dk050sYinLNCiYLZyC1GoZ4m3LFcqZUplIFf0jjFzLjbmGt"
        "yr1Odep4qniap/llNHeHGN7Q3C1ozt4dzYk3NPeG5t7Q3Buae0Nzb2juDc29obk3NPfN0Jy7O5qTZ9FculisluH+hy/pDm9njGCd"
        "nwzr7BCs4+4srIMeA48YOMbJxaMHDron7hh0StxxB7DOORhwpcBmpSz3uAyKYzm6AOscHjEAWIkLoBpPgTqNh8Od4QKeG4Ob3cD9"
        "kRdDe0vrJgwnLmI4pa7BcFxZcfN41wVy/jKQs9cBOckuAbmLguuaXQ/jlLoJxvGT0VFMArgnyZ8O485bcBOMG0JcE2AcH1Orv1cY"
        "hwfU/zogd8911HFAzj4AyLHHwjg9CcZlGjqEQsIYZctM58JlaZazVGecW8NwWxCz5UKZRY6Xr3m2yFJhUmWKMhW5WKgRZxZuj+EN"
        "xt0C4/zdYZw6C+MAi33aQz3YPy+38+dXvOY9wnFyMo7DHrMfx/mzOM7j/gbuNTPoQsvh3giRAGhzgN2UAhyHrgXXa5VIjSMtuNDP"
        "amEdHmMQkH3gCrzHQ0hBrkucMIjppNQGXOw0Hfxkg2iuupi7AnO48YuKpQXpnNf+FNXJo78I2elTZAf9RXOHKLdKHDUNoAZSd9K8"
        "Fkb51mvh49fcCi3Pfa4MDrmD740Wx2lTeP/nMOjkC1NA5mqhFyrPdWFlWWaFLhe6gKfemxxoXVGo1Ai7EKYQPueM59aJUpmMl+dA"
        "K2VCsIVS3Ati++vqTSdlT2f4/OUuGlCsdTSDxQZRrLlwtnPaTKQ8ATun02G9uARoDLlnTs3yK2ci66BPMqKza+nCtsQBlNYOPUp+"
        "B8KyE4SJJ1FGAKvBCDoQluuT/NHXZn0Hwp5wB6HdpLQPAllpxEUgOzHfT+CsvK5Yz8DZCxfdcOx0LwXZhbPqjvOS/l5wlvfVqq61"
        "0o4s+pOTH7JbrYS9+joUCO5ktcbYW/YJlqVS2gmWOp8XwoosK6G7tKrkmVhogJ4wijBWALaEYYWlOfR+agFsIhUs42bBL4PYO8Tw"
        "BmJvALFXi+EMg1h9FsSSYNL6EPRHoD5ECNZORbDCXLnADGM+YFdDy8wGD2Ggq8jF53iYluNpCwA6iGOFR4aMi82AbxkuHmsgWAxd"
        "JxJr8aQmuBpdJ/FWYYeHciED8ditxVlJcM0PPCvZU2433T2nL81JsmtmJC8e0qA7fMevKvOLk5HcX7mqLC9iufNBn0TQGVqMnJwR"
        "E6Yjubu4qnw5An3m9AbTJ6u0XbjP7VXTkdLLi9OR3E6cjjTGXFxVxj0Klya9ph3mGMzjux7n+FGnIc3Facgx2Td9PVndMhFpmbvU"
        "cAfr5pkDH7le5GnmhXGo7mmz3GQaGmAqi4VQaQaDvcilEIB2UxgHlS5knmXpwsjcq4KNOHJ7hxjegNxEIIfiwn3yO6RUSdKMo96g"
        "XAoGQz5QaQcVsGrNDpTBm9dTThVM6frplfjpeooEfqqXz6iVsgriOJ+x0PsjOvG2L8tWqvs9L9eN9xNR747X3qy64Kcv02q/Ib7a"
        "WySPc8bnaS6Ks/5jreGgQPMeuo3l+gtq8NGE21AGHpHlkI8GZw55aOSQYg/7OuPLtoZMVzN8TYgRZWTWLRHWRjwtLaD9o87bfA8f"
        "7Y9VPhLUrFRLY3281/XyX6+oaActq9Hd69RFlC0K9yif1Ix8s9vuy9PntcJTz4s9dlRhvf707euahDV7PjvamA59fOqnq/zY8gEJ"
        "2W7WkQhVTwAdIa8eH30dSuStXzSqP7B+HammWvTF1Xxyovw9KIfTF0wo3yjaqmw7SQnlGj+sSq3jkxpN92Gr9FtvTm55/96TKL//"
        "JKrvP4n6+0+i+f6TaL//JLrvP4n+u08ikt3vMImIqvcHSE/59DXgK/hj/zzHadI1EIp0jfp3tVpnI8J3hDFgYgfEEVILk5kcBSt3"
        "r6g6eXiGEfOAYLboCikO5Ewv0M5Xm32EYDrDZiX+eIQVm0Yos5rta6HKilPXSQQ4uXsquyaROiaYUwyO3R1bmudnB/xe67a7cpui"
        "BuYR1hQlUqL4GRQfoD5EFYvV5ktHhrkyEyE8hJUeSHLzJBNwepWWq0/fHVKIp+c5XkOEVfXrOr/wdihnev305VKvx94ci32mq9cB"
        "g9v+iOXV+pTEYHvSR55IY6YhByevIfOR8eaH/tfb8tzb8DER3qYE+4OI/YQOo5Oz4eFw/9Kbd1XX05MR0ZvGfuhCPi8/b3a9n3Rf"
        "HqVpKawBbJxCs/uSLg/n3qevu3TgfT1pXwHwUY296e1QLDOQKmzyi93mZV6/myR9eti0v7vQfVa6t83qVIsdbp+hg8fjiCSEjsmq"
        "+kWaDqHr2IFytIlm/aLSTqb5DnqGtrIE/9P472PdDxKbuCCNGcYZXNOahym7zvtmhSPW+czJjDAjFT2CAH7+n1/++//9z0+ME0kn"
        "IeH/fvqCIaakkg7dVI5JOn23f81owa4aEE6Fnmrd3IsKnigHjbWJJhJX5edyRdPW7xUXnck4XP/51+tyuy2LGfvgLaALy4MQ5AfM"
        "UukAnSvjZML6/pvx6hsRBII+sOTMfzNR+ZZByZF8K2NFcPq/UdU3Kug0Vt9Ags6kSlff6KDcc4xnKGGm+sAEmcVOJEOfzmz1mQ2q"
        "O+3PBu1x1TcuaOpcyDFf+fZBAvGyJbwqRceCLs4xTYNfVGXoeBC+uZAiXhWiE0Hb5pJ3WXmXQb7mkvequJ0KCjUjkl8VttNBTvBS"
        "BFVROxMUA0fVQV4VtLNBmuZiMWBPGdamWw2ttQD+AdoCSt7OSPJ2RpK3M5K8nZHk7Ywkb2ckeTuju6JnJHk7I8nbGUnezkjydka3"
        "RM9I8nZGkrczkrwl18xI8nZGkrczuit6RpK3OCe/+rp9Hk4e+8C9heatNCQGXEgMuBqao4IA9QetPbQaywQ0Au4cVGtNwQazvwdN"
        "XzIwbGq1CZgB/6Bhag3/VALJT/D4DMd7GIP3aI3iuM79b1rC2ccL3mE4qLrLIEb9dUg/94zUWmcNLFr6bkchjlH0yrB1l84GwxVx"
        "uLKV9D5l3TMibINRqDgKdYyiV2b3jK7uYBQ6jkK3rOjTaesVihoM3MSBm3YWcTEh/ZcyysYR2VZEfQpuZyTbBqNwcRSuVY365NxG"
        "VyMfh+tb4fbp9E4rAB63L8eijBlXAmdCj5uW4+2m1XNxweg84XHbcq022ysBNz5gGQfcarS9enDjA46bqms31T5xuIkZHbdS126l"
        "faq/45Mdt1DXbqF9EsDXdGI8bpyu1Th7pelG1XAkZPUyaFi9qlaevqzbO/guKMCeoyyioSw8iVcpupRF9FEWcUJZsjOUJRtLWcwY"
        "odp+ymLfowjZRcrieVA9nUJZ/CTK4mWQLZ1CWbwKoqRj2UQFZP1U1uIDazEd+nGJtfgrWIufxFq8D2KfY1kLh4o5jbXAF1NYC0e+"
        "Mp61gPcprAW8T2Qt8EVgLReTbyvv5n4EhHSaZ6TTPCOd5hnpNM9Ip5lcPyOd5hnpNM9Ip3lGOs0z0mmekU7zjHSaZ6TTPCOdZnIN"
        "ucALUKd5RjrNM9JpHkM9NBfQTLHxAfvBpH7A1oEVXkMkFlwLNZJFdOOvk51uiAbK8kAC8STcDYTCR4TC2QcQCv8gQuEjQqH5AwiF"
        "V+3c0f6OgDwGLP6RtMLHtMJMQPvTaIV/PK3wD6IV3rdL2rp70gpe7Ud9DK3g1UXod6cVvCISd6cVnPaJPIBWcNrd8ShawRmLacUt"
        "GW3jgM1fDvlb+sMDoL/lo9MdVzt/urBf9sF+GcF+DHNopaJ+1wf7O8IttfTxRaXkfuDv32tzca2Cw39BarcG/hpRlzkH/OEbHk6T"
        "jAH+4FsErdwa0plzMVQwkMughNv5ZujDWYUFuQoit6OiMtU3OkjYjo2qwpHcBHXaUVG56hsbtGeP35yF//CBC+KyNVjVF+E/9+Fo"
        "xOUoavgvWDj5MOKLqkAFD0oVIxmACISBjWQAQga9iUveqyIXKkhKjEh+VXJCB+mui1+MYAAkGD4jwfAZCYbPSDB8RoLh5MJbFAwn"
        "18xIMJxc+g1cgQTDZyQYPiPB8BkJhs9IMHxGguEzEgyfkWD4jATDZyQYPiPB8DFswFgzwAYg6bj8YMUJG/g+tNAbZgAmYGLwcoWr"
        "mQFnnEVLDWwMM6i1j0YxA+wcW1H0Hbm7ihlgNxotNbAxKEBdSnoMNHibfPTpkF8UHBrFDLCfbmMOcR9bTByFjvjBPW2JYQ6PZk+l"
        "uostLo6iTUH6tMt79XJGkQQcYyKyPCajpBxNEnibgvQd2ZuW9A5JEBEFGbc2pkYzBcEjpsDvxhRETEHY3ZiCaDXgXs2m8QHHDVZE"
        "DZa7WzM6bkJCR0xBXRf6PZiCuMgUjgsEMok34HeZgupjCuqEKWRnmEI2nimI8/LdvRyBs/fCq8scQfigCD2FI0g2hSNIHiSdp3AE"
        "KYJg80SOIGXQYp7CEaQKSssTOYLUQUR5CkeQJkgkj+YI0gYN5FGR1DRBuqk0QfqpNEGxSTRB8Uk0QYlJNEHJICY8am8TeFdBL3g8"
        "q1B3ZBUkfE/bm/C3AIZBwvczEr4/bmbSnFzcxqSNnJHw/YyE76stTSR8PyPh+xkJ389I+H5Gwvf1ZiYUvp+R8P0YJgGmtpgEd77N"
        "JTyuLLATJkHmJGROQuYkZE5C5hy3LmlOLm5aAnMSMichc6oNTGROQuYkZE5C5iRkTr11Cc1JyJw2e0CtBkgs3sh3A3sQ0Xzq5Rm+"
        "K9iDZI9hD5JH7ME8gD3IiKAI8zD2IGWEuM0D2INUEXuwD2MPUkflzR/AHmREUJi5K3uQ0eqIuQ/76XAI6R7JIaR/JIdQ7EEcQvEH"
        "cQglHsQhVNRsrbnT/iUcrKP+QN6XnKjvhpzIi+RENuREJfHR2y450X3kRJ+Qk/wMOcnHkxM9Qoz+plUM5YO0+RSGoicxFB0Yip3C"
        "ULQIyuMTGYqW4cr8KQxFB4biJzIUrcP19lMYijbh3vrRDEXbIOY9AkxXxakn0xM9mZ6YafTETKMnZho9MXLqKoZR4WL28xGMWcJg"
        "kBWQbotLGNAtO3QdoHwtGfx2WsoZx+n4mZTc4OKFYGamrOaaXIuuJNcBLRHW25mGwMQM7wh0M+twM5TzChcvwPUzL4QfRTbYwKKF"
        "APZiPwgNAYLr4mULNCchcxIyJyFzEjInIXMSMichcxIyJyFzyEVNFTAnIXMSMichcxIyJyFzEjKHXJ+QOW2yAclLIHHwz91ANlQb"
        "l1j2iKUK/SCyoWOyYR9ANrSIkq4fRjZ0G7VIzx9ANnRMNvzDyIaOtnoo/wCyoSOyMZI4jSUb2kZLFbeug3Rohn4ozdAPpRnmUTTD"
        "PIpmmEfRDCMfuVRhVNQdTN/kdRMRwCuEz2xmql93+rHqapsuBTB9FMBEFAACHNrIVL06EgDee7NxJY07KKDbj/rde8lHoH7jggxr"
        "uCEXgBPqLgAB5Pib64CBcP6wB/0bH3RWT/ATygT04H/LgpRquOeWhWiauKAvpW+N7uMBNqxU+HCRbftbJfBk5TGpoo8P0CHshg8c"
        "vyUHe2iJOqynllbUIBzJFizcQ3smdmP6KEI4mq18EL06MVz1ZnJFFaysqAJdI8vqz+hD2RtpRRmsCjJW4arYkZHW7MG6NhfoiVL3"
        "Uggbtk6xgc/6WQQeEsdrXkeyCDwhjsqgI1kEXiSAmlHhftYx+VcTCjxbjheyhjtYe6rNQJWr6YWTA/SiE+EYgsFp/xMKVs9IsHpG"
        "gtUzEqyekWD1jASrZyRYPSPB6hkJVs9IsHpGgtXkuhkJVs9IsHpGgtUzEqyekWD1jASrZyRYPYZgSOAw/IPxHls5nhb/AJmDB7SB"
        "C+kPUmhoQ5AcaArAEqBSS9EhG3+ZFndDNsCEBAzADVMJlSzAbUg4RgX/D/xG3EJCjItISK/g9ZmbyE+0NIaYiPHtLc6Td3tDLR7i"
        "IpZFXKRXCvvMRdknOiZDhMTGqx+9utgXdaTPWBWDnOjE9hhWcnLH8pmiidlJfH67XzF7qmHGDFGU+BB3v+7i+OJqWxXzFCvP8ZRw"
        "63nvRdJnLInJio1mpfuFta+zpMNbrJvILC5V7A5zsfEWLnZN+MPMpX04vfe+9GuZS/tceq8Y97XMpX1dxZCg49Sq0+Ew7aPvQ9eq"
        "T27hYpDUOHkTqUFLbqY14jytOW67Mkl8HWaX1tg+WmO7tCYbpjXZX01r8I6ca2kNEJpJtMb562kNnRm/ntZ4dROtoUPe19Mab66n"
        "NXjw/SpaQ2fgr6U14bT5ZFrj3RW0Bs+dj6c1nLFJtMazK2kNx7PqN9AaTofX32jNfzqtad9G8kha49yjaI3z34bWREfpH05rvPpm"
        "tCY6nP5wWuPNt6E17WsJHkNrogsKHklr4nP396c13j2S1rSP3t+T1nDGHkRrPHs0reHtM/2PpzU8Oun/F9EaeZ7WHDds2SS+Qr9L"
        "a1wfrXFdWpMP05p8JK3xHVqTLharZSV/ku5Wm/zTmbum/OW7pqBcaEECoNhZflOh4ZjfAPtG2dn6CPVFECyqr2ihCMH+WZZje1gO"
        "pwPyVrIeliNxn1md4L6tXJzLkRynY62pPqddXYJj8zsXd9fsCu1yPYbjdKJ21bf8Isfp8BRffShqjsOZHRtpxXF4OFU/leNwOlg/"
        "zHHwqqEelsPxeP0ElkNn60dvAYMe9TLLsb0sB4/kj2E5vTvDOB3P7+c4eirHgexB1+GpD3DxeLvDm6Uc4CdwuQOO4xwwICkgxpmy"
        "eOUtNE+8/gpc4DgOj7E7zXEPmMYrrxwwAQ9cBtI5Q2lIRe6o/WDC4TF2ZR3ep+sE8BpriNdY5DXCIa+xGg+hCM9xb5hVMa9BcxIy"
        "h1w80g7mJGROQuYkZE5C5iRkTkLmkAu9FJqTkDkJmZOQOQmZk5A55Mb7wXBbpcXT7yKBBMNvm0BiE4t7xGAEh2Rez2U4i+bnu/fZ"
        "TOUySg1wGc5aeAx74JvxmIiDj1aaThDyVEJjBwgNj24AsCfS9SMIjR55ARaR6PvSmXbpmDiqaA+Z4CfobbpZUWHFyIrre9KZtlUu"
        "joffh860aYaPYxBn6Qxn9lpLYjrD42sC7k5neHRHwJV0BsbJIULD29cE3JXQRDcE3HGHGWf+ToTGDhKa9v0DdyI0g1vPeHQdwTV0"
        "Rt9OZ9R5OqMaOuOSWG6rS2d8H53xXTpTDNOZYiSdkR0685LuPu1hdCU1o2eSUjlz+ASvsLzIZ/BCIWc8raH4wGdoEUIHrKf7oWv1"
        "LSAWbjgbuV7DBa0NSYTlFaQHtEIOxiVrZK76mEw4xh+QuYi+DTO3TVJ712s4nbdX9QmY47fkYNRn12s4nbuHdgixC9MXwkBGVahW"
        "hnueNCZejzW84jIy3InLcMRwnW+FdaI33orOyHDXmTjSmVPDz6zacLoDAHwdc41FsXY/q+pFuAagvsK45zPfy2jwMgCL1yaPYzQy"
        "ECA/ktEIh9AvlAEbLAPZT2rCBQJWQiEIO+aqXk4XCAAGhy+MvfWUi1fcgauZQRe4CvdGiBngfAfsRSlgMuhacL1WMwkQX6DLGZ5p"
        "cXjIHlo3ugKv7RVSkOtmThhkNVJqAy6MvOBqw0at02jXOuFicGGIzrhILXGFRqMyiDR4ykWazgoNmpOQOQmZk5A5CZmTkDnk2oTM"
        "ScichMxJyJyEzEnInITMIdclZE5C5iRkTkLmRGsz0IggsXi/F/yDYKHlQAJv4DDtC2CwJz0B/76PwwClwmn4s7g1BkmiBcKw173b"
        "egzJm7doxQlS7UfEwBzJPYlHDdGX+AqCHrwqzsXTn1+D6zE8OtKvRhzkiaPqMWxoPYZHh/otO6EUWHRTYxsmMDK+z0ifZKO+trhi"
        "AiPjO3LZCYFxU+Jp2xPTGBlfOifG0ZjxZdUhM9GtBYrLUfXibPhxO42vLHD+uvD9IJlp31pgqwux70JmZMyS/N3IjHDt2ZeeCsum"
        "VCQ5TGni6xCs7NZYYa++EZhHlyEoe7Lsbuw3OD+jz1MY3VAYn8RyvB0K03p0pDCcdSlMOUxhypEUxnYoTLkiech0Nd8/pzDI3rjf"
        "jNNlR8bps+sxfUfoudIDR+iR1fewF0UrP4oPrMOo3m8r8KloDUfIvnWYaOtP5/MKftL5fWXkxZWYzucVe6Gj/NCWenabSZRFGIq9"
        "grJ0pF8xjQvkfthw28de6G4D6eWZlZjOhxV1oQsOjDHRbrPOwojrJS10m4BqL1t14vO9pCXcJjC4etO71YzjdQITFmHoMoHxizDK"
        "0uSPObMI0zWmrjBu5FYz1c9edDhgJuPMYH0FNuqiYY7MxdCeM4Pn8NFV5OJzvOiL4wl1iB9ZjPCQR7TzDNgNw51kGvKCoeuAVliL"
        "Fwpbq9F1EnUPHV4YZjie0ncWV2XANaNWZQTtNuMCV2Us7jYjJRT4zaHxWSBT5oPgHldlcBPbByAtnYuGcQ2DTEvINHIVufgcL/0i"
        "0xIyLSHTaOcZMB00LSHTEjItIdMSMi0h0xIyLSHTEjKNXBOt0AABAQMSHO9I9wTGJkh4AsmGfyrxNDl+LbuJ7qcxTt+0QjN0mJ8r"
        "fdNhfmgGQ9xGRStMit+2NNOOJ8Y4KloCEnL60sz52GKgE11SoIy8eXGmHVXMbaLLCix30/eaaXUuthhlRTcWKKZPdmj5ScVlh7hN"
        "dEGF9PLaxZl2DDGrie6ngIFs7F6zk2UNN8hkorsX1MglunNl0WEy8ZUL1y37DO4y4+3bFu66KBPdtHDPRRllo0UZc+2iTJTlnYbt"
        "7r/LTA2TGh0fXZTX1SA7ith8RA37cvu6Ws3zzXr/+pJmK1Rvh6Tlz+VLWhOZHk/zz5y04AH77zC8Rbral0klEl//tUiXq9bLfQkB"
        "QGgb2v21K/fl7nPrdXoAq7aNnSQ+/1SuyyBPUl0J9no4fYhxztPDHMdMFmJ93QEfA3vRyztI6Ev5kpW7qmp9TlfLImiegJn5p+1m"
        "uaZxt1yjbccUbZ8hx8L9YuEF2JBvIFmfSkQuHwA1foBn5e+AXQ5lMW9iYXWM84rQIblbIcw5/g2mzDcLePCSQdqPz6EYXyCs1gMg"
        "a58iD5v2ayycTTuAkB/tiFfzuFx2ZagLRz+t/PnzT6g5L+nTS/plftil6/0CzFil6xLpYbH5ghlVV6y6YDevuxwz/PNyT6ViEZDt"
        "PzVN+YCVZD7wqJUMKAeErZAn23S3hNILKAii2+zmxwVAVLFpvGB6NlmnLkHmgg8su3W5PDyDBVusb2u8GW6722w3+3TVNn/zmTjw"
        "vOdd+pItn143r/ujua06gFWCsmWep+sCq1Xrzap8SvOvfW+qb9qGscZ/52nlt9yCtcVJ7a/eUkZ2XlXBAX0HyzrvmjpbeaKSXlKb"
        "6I+gAGy6XFePoUg+QyvDRtHkyu/vPqyhk0jefa1//BF+/Nmk5KYwCqhx0MGt8zJUU7ChypE0z19fXlcp5Fq7coYAqpoWV7t2Y6me"
        "pNs0J0LCzZ/YOXfrnHirc2917hvXOflW597q3Deuc+qtzr3VuW9c5/RwnQvU5a3KvVW5+1Y589bNvdW5b1zn7Fude6tz37jOubeh"
        "9a3Kfdsq59+6ubc6923rHK7CvdW5tzr3uDr3cWhRhLI5fT08b3bkuVnrenoJSxmvtC3l3+/2h3R3KEMB7l7X6+X6KeTmaw4GREtX"
        "9PuwfCmh0tLqZ3vJitbAotWqMJDXG0jm2/TwjItWKSStPPy99ek+h292y83+793w9u//CQ1nhVv/is8p5Oj8BfIRQjmUuxcoIHzT"
        "RLBcF+XvtF+keVRlH208ONYVEfl42a7Kw7Fk65ChNuImmLykpZ6wwrfGQqR9ltmX4j0th77flWFnY98qIK8ffoK04apl4xcy/als"
        "1hSrv6r1VSrs/esKN1ymu90SMuUdrolmm/0eaiZkYzttH7GLWR/Sl6q+dt41hq42aTEvdzusetSwq0yv7Fml+acvUPZY9XOsIZyt"
        "51XNKpbp03oDLQIv14jzIPh4nz+ny/WXZbkq6JwZtBXcmvnuv+ntf/2j9fa/oJrun8FPlSXhT6hK+8Nr/omML8qc1uv2VFJV3etf"
        "Qw0tDrrVT3V1S/OQ9ZBbB6j+mznU78Mr7TTdQFuotskW5SLFDMYGAd3xDvqsTQ6103nFLfNWGlSpw1MI7dVfTl3yYrk6KeX6MZYE"
        "Zt4zGvXhnfpZ//yTNT+p37z7Sf7Kf/VCSvfzP5x1v/zyk/JMyt+0+gdj+h8//frLr78a/dtvv5qfmPzlN/+b87+8q9fK51UEk0oq"
        "WkzlVVe6W2L7x5oFmbPevHydQ1jYbeJuNWj/7z5oGmaolaWrL+nX/RwqVe2bKsB6npe7w3LxFVOR7vdLyGOqcFUTwqpWFvNjpoQU"
        "iGM+DXUKUGhzSAT2MfXn+7/XP6gveNcTSLdqbzebFXSAT3Pwhgcfp2Ra+TvkOCRrd4DhsNmOXC0PZzuoyBDc62G5ws1xtNkg3s0A"
        "FuxDbleN+vigeN1V/R1tONjTSWpsCKvVnmoRte19tZsi3c1ft087yMnw5F+vYOoeh5ByW/fX1bO6D2s9nG+yf5ZN1Xna1T057Zug"
        "jqSKFp4B6Ngs83nfK3p2oJ3Y0DWFARrTitvnaV85lv7T+iU8xnPC1MHNcbMA2Vo9pXDaD1sZtIVOCMeoeavdW1Wtuu92r9D42mNR"
        "iBGqV//rSiIuThfuVoIq+mkOkImgAw1yeG6h6pHBE5kEBQO9wdFQgbtglutQv2lryKGVMVVNbQ/loRI0X9T9PvimMexluUcL5/UO"
        "juqzphuCsgp7FbCqHoempmrNQ/e2n3cG2ea7ZrdHu92HMgkwTQhtJJN4jpGj0pPCfULQU0DXHO9kaHDXfvlHGcKpt8QeH6ziv6vj"
        "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"
        "wquL4roeZEYRm8/oxD57/9jtlulhf/p4S1Y79N4ORUtfs7ekIDItkZZfGfmCB+x/LB3KR7mT+OKvTbLdVV6eMkgAUjvQ6a9jdsqO"
        "XyuvkzNI9V7KSc7nX7J95t2T5CbBPs7Nh5jnMjkvcc2Mfa4fR+BjIC9G+QQFfcveVtkx71pfk9127X2egJjpl/fDdk/rbrZH2S4l"
        "en+FGvP2xfwLkCE9QLG+ZIhcngE1PsOz7DfALudsvSxziYsclzmhQ3K3Q5hz+RtEWR428OBtBWW/PIdmfIO0Kg+ArH0JIhyqr7Fx"
        "DtUEfH1UM94tw3Y5Zr4vXOJU6udf/4Ke85a8vCXfludjsj9tQIxdss+QHq4P37Ciio5VNOzh45hihX/dnqhVmMRxeoZyl6P5jP1k"
        "2fGoUhJoCkSuUC3vyXELDeiBEOR4OC4vOkB0ZFNGwSIdVkV38r0dqhciYOvts+35FWR4xx63R9tw78fD++GU7KoVcPhKLHjZ8i55"
        "W21fPg4fp4vAlV6AnYIqZpkm+zV2rMqbXfaSpN/b3uTfVOWKy/i1p3nc7B2EXTf6f/6W6rH2Kk8OCDxIVntX9to8ErX1lkZFewZr"
        "QKfbff4YWuQrjDMcFmWt/PbpeQ/TRPTpe/HjH/7Hv8qS3JTGGvocTHH7NPMdFWTIayRJ04+3j10CtVbtnj6BvKOFva46XPInyXuS"
        "EiVh+l84Pde7HJ+73NzlfmyXE3OXm7vcj+1ycu5yc5f7sV1OzV1u7nI/tsvpucvNXe7Hdjkzd7m5y/3YLmfnLjd3uR/b5dzc5eYu"
        "90O7HGrg5i43d7mHdbnPXfoQqubk4/x6OFLkUs318uZVGB90IuWfn07n5HjGbLGvHj/2++3+hZTTp48UJDjR2YtcbUUFOW/fMui1"
        "pPmsqqtI/xVoqnwPLw6PLN+T8ysqrBIoW3b+Q+XTUwrfHLeH0x/q6Z2e/gcGzg6P/a2/JlClyzeoSEjlnB3foIXwTZnBdr/OfqMT"
        "HeWjvP7o0MGls4ggxtv7LjtfmrZIGbojHoBJM9LxeO3eHluRzliuvq2fSBX6dMz8qcY2DSArHn6BsqHGsowLtf6SlfrE/K9ct0qt"
        "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"
        "8HAAd02VMs1Hn//X/wfEyTbT"
    )
    return json.loads(zlib.decompress(base64.b64decode(encoded)))


def test_combat_event_active_admission_binding_persists_through_recovery():
    from tools.bot_ml.combat_log_event_stream import CombatLogDeltaController
    native = _native_capture_binding_statuses()[0]
    def controller():
        return CombatLogDeltaController(send_commands=lambda rows: None,
            read_rows=lambda: [], command_counts={})
    kwargs = dict(profile_name=native["active_profile"], scenario_id=native["active_profile"],
        route_manifest_sha256=native["raid_runtime"]["admission_receipt"]["route_manifest_sha256"])
    for mutation in ("profile", "admission", "context"):
        rejected = copy.deepcopy(native)
        if mutation == "profile":
            rejected["active_profile"] = "foreign"
        elif mutation == "admission":
            rejected["raid_runtime"]["admission_receipt"]["attempt_id"] += 1
        else:
            rejected["server_epoch"] += 1
        candidate = controller()
        candidate.bind_active_status(rejected, **kwargs)
        assert candidate.cohort_id is None
    capture = controller()
    capture.bind_active_status(native, **kwargs)
    recovery = copy.deepcopy(native)
    recovery["raid_runtime"]["alive_size"] = 5
    recovery["raid_runtime"]["ready_check_satisfied"] = False
    capture.bind_active_status(recovery, **kwargs)
    commands = []
    assert capture.append_command(commands, force=True)
    assert commands == ["botauto combatlog default delta 0 4096"]
    assert capture.accepted_status == native


def _watchdog_native_progress_fixture():
    """Run fa34580f2f exact watchdog-field trace projection and native events.

    Actor 30002, sequences 252..286, captured before terminal capture row 308.
    Includes native delta prefix so accepted transport is gap-free from sequence 1.
    """
    import zlib
    encoded = (
        "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"
    )
    return json.loads(zlib.decompress(base64.b64decode(encoded)))


def _watchdog_completed_native_events(fixture, *, incomplete=False, gap=False):
    from tools.bot_ml.combat_log_event_stream import CombatLogEventStream
    from tests.test_combat_log_analysis import _framed_combat_payload
    stream = CombatLogEventStream()
    stream.bind_identity(fixture["status"])
    payload = dict(fixture["delta_template"], cursor_before=641 if gap else 0,
        recent_events=[row for row in fixture["events"] if not gap or row["event_sequence"] > 641])
    frames = _framed_combat_payload(payload)
    for row in frames:
        row["cohort_id"] = "default"
    stream.observe_rows(frames[:-1] if incomplete else frames)
    return stream.take_accepted_events(), stream.identity


def _watchdog_native_trace(fixture, entries=None, actor=30002):
    return {"action": "botauto_trace", "attempt_id": 1,
        "bots": [{"bot_guid": actor, "entries": fixture["entries"] if entries is None else entries}]}


def test_capture_watchdog_combat_event_native_counterexample_and_delayed_poll():
    fixture = _watchdog_native_progress_fixture()
    events, identity = _watchdog_completed_native_events(fixture)
    assert len(events) == 748
    kwargs = dict(profile_name=fixture["status"]["active_profile"], combat_event_identity=identity)
    state = {}
    report = observe_capture_watchdog(state, fixture["status"], None,
        [_watchdog_native_trace(fixture)], combat_events=events, **kwargs)
    assert report["detected"] is False
    assert report["repeated_decision_count"] == 7
    assert report["progress_reset_count"] == 11
    assert report["progress_reset_bot_guid"] == 30002
    baseline = observe_capture_watchdog({}, fixture["status"], None,
        [_watchdog_native_trace(fixture)], **kwargs)
    assert baseline["detected"] is True and baseline["repeated_decision_count"] == 20

    delayed_state = {}
    pending = list(events)
    previous_timestamp = 0
    for entry in fixture["entries"]:
        ready = [row for row in pending if row["event"]["timestamp_ms"] <= previous_timestamp]
        pending = [row for row in pending if row not in ready]
        report = observe_capture_watchdog(delayed_state, fixture["status"], None,
            [_watchdog_native_trace(fixture, [entry])], combat_events=ready, **kwargs)
        assert report["detected"] is False
        previous_timestamp = entry["timestamp_ms"]
    assert report["repeated_decision_count"] == 7


@pytest.mark.parametrize("mutation", ["actor", "target_guid", "target_entry", "route", "generation",
    "epoch", "attempt", "server", "profile", "zero", "shared", "heal", "source", "incomplete", "gap"])
def test_capture_watchdog_combat_event_rejects_noncausal_progress(mutation):
    fixture = _watchdog_native_progress_fixture()
    events, identity = _watchdog_completed_native_events(fixture,
        incomplete=mutation == "incomplete", gap=mutation == "gap")
    for envelope in events:
        event = envelope["event"]
        if mutation == "actor": event["actor_guid"] = event["source_guid"] = 999999
        elif mutation == "target_guid": event["target_guid"] = 28
        elif mutation == "target_entry": event["target_entry"] = 42650
        elif mutation == "route": event["route_node_id"] = "bwd.magmaw.drudges"
        elif mutation == "generation": event["route_generation"] = 3
        elif mutation == "epoch": envelope["identity"]["combat_log_epoch"] += 1
        elif mutation == "attempt": envelope["identity"]["attempt_id"] += 1
        elif mutation == "server": envelope["identity"]["server_epoch"] += 1
        elif mutation == "profile": envelope["profile_context"]["profile_content_hash"] = "foreign"
        elif mutation == "zero": event["originated_amount"] = 0
        elif mutation == "shared": event["shared_damage"] = True
        elif mutation == "heal": event["kind"] = "heal"
        elif mutation == "source": event["source_guid"] = 999999; event["source_is_pet"] = False
    report = observe_capture_watchdog({}, fixture["status"], None, [_watchdog_native_trace(fixture)],
        combat_events=events, combat_event_identity=identity, profile_name=fixture["status"]["active_profile"])
    assert report["detected"] is True
    assert report["repeated_decision_count"] == 20
    assert report["progress_reset_count"] == 0


def test_capture_watchdog_combat_event_resets_only_owned_actor_and_equal_timestamp():
    fixture = _watchdog_native_progress_fixture()
    events, identity = _watchdog_completed_native_events(fixture)
    entries = [entry for entry in fixture["entries"] if entry["result"] == "failed"]
    other_entries = copy.deepcopy(entries[:19])
    state = {}
    report = observe_capture_watchdog(state, fixture["status"], None,
        [_watchdog_native_trace(fixture), _watchdog_native_trace(fixture, other_entries, actor=30001)],
        combat_events=events, combat_event_identity=identity, profile_name=fixture["status"]["active_profile"])
    assert report["detected"] is False
    counts = {json.loads(key)[1]: value for key, value in state["repeated_decision_counts"].items()}
    assert counts == {"30001": 19, "30002": 7}
    event = copy.deepcopy(next(row for row in events if row["event"]["event_sequence"] == 738))
    event["event"]["timestamp_ms"] = entries[-1]["timestamp_ms"]
    report = observe_capture_watchdog({}, fixture["status"], None, [_watchdog_native_trace(fixture)],
        combat_events=[event], combat_event_identity=identity, profile_name=fixture["status"]["active_profile"])
    assert report["detected"] is False and report["repeated_decision_count"] == 1


def test_execute_capture_run_capture_watchdog_combat_event_native_progress(tmp_path, monkeypatch):
    # Both the entry controller and watchdog are production functions here;
    # native completed chunks and the exact failure tail meet in their real call path.
    test_execute_capture_run_retains_native_combat_event_delta_before_terminal_full(
        tmp_path, monkeypatch, native_watchdog=True)
