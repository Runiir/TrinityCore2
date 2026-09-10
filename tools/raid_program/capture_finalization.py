from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import signal
from typing import Any

from tools.bot_ml.analyze_combat_log import analyze_combat_log
from tools.bot_ml.run_live_bot_validation import (
    combined_combat_log,
    combat_log_transport_status,
    trinity_config_string,
)
from tools.raid_program.capture_drudge_contract import accepted_drudge_contract
from tools.raid_program.capture_evidence_demux import (
    _required_telemetry_envelope_report,
    evidence_demux_report as _evidence_demux_report_impl,
    normalized_batch_payload as _normalized_batch_payload_impl,
)
from tools.raid_program.capture_environment_validation import (
    git_identity,
    preflight_runtime_exclusions,
    sha256_file,
)
from tools.raid_program.capture_forced_evidence import _forbidden_assistance_entries
from tools.raid_program.capture_live_run import CaptureRunResult
from tools.raid_program.capture_run_outcome import (
    _capture_classification,
    _primary_gameplay_terminal,
    _terminal_evidence_incomplete,
    summarize_process_resource_samples,
)
from tools.raid_program.capture_runtime_acceptance import (
    accepted_native_recovery,
    terminal_runtime_failure_reason,
)
from tools.raid_program.capture_runtime_io import _artifact_record
from tools.raid_program.capture_setup import CaptureSetup
from tools.raid_program.capture_telemetry_transport import (
    action_payloads,
    json_rows,
)
from tools.raid_program.capture_watchdog import (
    _CONTROLLER_TERMINAL_FAILURE_REASONS,
)
from tools.raid_program.chainwielder_prestart_bundle import (
    BundleError,
    PERSONAL_THREAT_EPISODE_SCOPE_KEY_TEMPLATE,
    validate_personal_threat_episode_target,
)
from tools.raid_program.recurrence_checkpoint_seals import (
    MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID,
)
from tools.raid_program import trace_transport_smoke


def _canonical_object_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _positive_int(value: object, *, allow_zero: bool = False) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= (0 if allow_zero else 1)
    )


def _prepared_route_rejections(
    target: dict[str, Any], runtime_assets: dict[str, Any] | None,
) -> list[str]:
    """Prove the declaration's route literals against the authenticated row."""

    assets = runtime_assets if isinstance(runtime_assets, dict) else {}
    route_path = assets.get("route_manifest")
    if not isinstance(route_path, str) or not route_path:
        return ["personal_threat_episode_target_prepared_route_missing"]
    try:
        route_text = Path(route_path).read_text(encoding="utf-8")
        try:
            payload = json.loads(route_text)
        except json.JSONDecodeError:
            payload = {
                "routes": [
                    json.loads(line) for line in route_text.splitlines()
                    if line.strip()
                ]
            }
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ["personal_threat_episode_target_prepared_route_unreadable"]
    rows = payload.get("routes") if isinstance(payload, dict) else None
    scenario_id = assets.get("scenario_id")
    matches = [
        row for row in rows or []
        if isinstance(row, dict)
        and row.get("route_node_id") == target["route_node_id"]
        and (not isinstance(scenario_id, str) or row.get("scenario_id") == scenario_id)
    ] if isinstance(rows, list) else []
    if len(matches) != 1:
        return ["personal_threat_episode_target_route_row_missing_or_ambiguous"]
    row = matches[0]
    if row.get("step") != target["route_generation"]:
        return ["personal_threat_episode_target_route_generation_mismatch"]
    if row.get("map_id") != 669:
        return ["personal_threat_episode_target_route_map_mismatch"]
    if row.get("mechanic_profile") != "tank_swap_adds_raid_aoe":
        return ["personal_threat_episode_target_encounter_mismatch"]
    return []


def resolve_personal_threat_episode_target(
    declared_target: dict[str, Any] | None, *,
    controller_route_hold_receipt: dict[str, Any] | None,
    runtime_assets: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Resolve only the dynamic scope from the scheduler's stable status pair."""

    if declared_target is None:
        return None, {"requested": False, "gate_passed": True}
    reasons: list[str] = []
    try:
        declaration = validate_personal_threat_episode_target(declared_target)
    except BundleError as error:
        declaration = None
        reasons.append(f"personal_threat_episode_target_declaration_invalid:{error}")
    if declaration is None:
        declaration = dict(declared_target) if isinstance(declared_target, dict) else {}
    receipt = controller_route_hold_receipt
    if not isinstance(receipt, dict):
        reasons.append("personal_threat_episode_target_controller_receipt_missing")
        receipt = {}
    if receipt.get("enabled") is not True:
        reasons.append("personal_threat_episode_target_controller_receipt_invalid")
    if receipt.get("held_status_count") != 2:
        reasons.append("personal_threat_episode_target_stable_status_pair_missing")
    if not isinstance(receipt.get("held_status_identity_sha256"), str) or len(
        receipt.get("held_status_identity_sha256", "")
    ) != 64:
        reasons.append("personal_threat_episode_target_stable_status_identity_missing")
    if receipt.get("failure_reason") is not None:
        reasons.append("personal_threat_episode_target_controller_scope_drift")
    native_scope = receipt.get("native_scope")
    runtime_scope = receipt.get("runtime_scope")
    if not isinstance(native_scope, dict) or not isinstance(runtime_scope, dict):
        reasons.append("personal_threat_episode_target_controller_scope_missing")
        native_scope = native_scope if isinstance(native_scope, dict) else {}
        runtime_scope = runtime_scope if isinstance(runtime_scope, dict) else {}
    cohort_id = native_scope.get("cohort_id")
    attempt_id = native_scope.get("attempt_id")
    wipe_generation = runtime_scope.get("wipe_generation")
    instance_id = runtime_scope.get("instance_id")
    if (
        not isinstance(cohort_id, str) or not cohort_id or ":" in cohort_id
        or not _positive_int(attempt_id)
        or not _positive_int(wipe_generation, allow_zero=True)
        or not _positive_int(instance_id)
    ):
        reasons.append("personal_threat_episode_target_controller_scope_invalid")
    if not reasons:
        resolved_scope_key = PERSONAL_THREAT_EPISODE_SCOPE_KEY_TEMPLATE.format(
            cohort_id=cohort_id,
            attempt_id=attempt_id,
            wipe_generation=wipe_generation,
            instance_id=instance_id,
        )
        resolved_target = {**declaration, "scope_key": resolved_scope_key}
        reasons.extend(_prepared_route_rejections(resolved_target, runtime_assets))
    else:
        resolved_target = None
    resolution_receipt = {
        "source": "controller_route_hold_scheduler.frozen_stable_status_pair",
        "controller_route_hold_receipt_sha256": _canonical_object_sha256(receipt),
        "held_status_count": receipt.get("held_status_count"),
        "held_status_identity_sha256": receipt.get("held_status_identity_sha256"),
        "native_scope": native_scope,
        "runtime_scope": runtime_scope,
        "resolved_target": resolved_target,
        "rejections": list(dict.fromkeys(reasons)),
        "gate_passed": not reasons,
    }
    binding_receipt = {
        "requested": True,
        "declaration_receipt": {
            "source": "sealed_capture_argv",
            "target": declaration,
            "scope_key_template": declaration.get("scope_key"),
        },
        "resolution_receipt": resolution_receipt,
        "gate_passed": not reasons,
    }
    return resolved_target if not reasons else declaration, binding_receipt


def normalized_batch_payload(
    log_bytes: bytes, *, profile_name: str = "blackwing_descent_10n",
) -> list[dict[str, Any]]:
    """Return an immutable, replayable JSONL representation of parsed evidence."""

    return _normalized_batch_payload_impl(
        log_bytes,
        profile_name=profile_name,
        json_row_parser=json_rows,
        evidence_reporter=evidence_demux_report,
    )


def evidence_demux_report(
    rows: list[dict[str, Any]], *, profile_name: str = "blackwing_descent_10n",
    controller_terminal: dict[str, Any] | None = None,
    fixture_terminal: dict[str, Any] | None = None,
    fixture_expected_identity: dict[str, Any] | None = None,
    personal_threat_episode_target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Independently bind every retained JSON row to one raid lifecycle."""

    return _evidence_demux_report_impl(
        rows,
        profile_name=profile_name,
        controller_terminal=controller_terminal,
        terminal_failure_validator=terminal_runtime_failure_reason,
        fixture_terminal=fixture_terminal,
        fixture_expected_identity=fixture_expected_identity,
        personal_threat_episode_target=personal_threat_episode_target,
    )
def evidence_demux_rejections(rows: list[dict[str, Any]]) -> list[str]:
    return evidence_demux_report(rows)["rejections"]


def write_normalized_batch(path: Path, rows: list[dict[str, Any]]) -> tuple[str, int]:
    if path.exists():
        raise RuntimeError("raw normalized batch output already exists; artifacts are immutable")
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with path.open("xb") as handle:
        for row in rows:
            encoded = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            handle.write(encoded)
            digest.update(encoded)
    return digest.hexdigest(), len(rows)


def development_run_claim(
    *, requested: bool, stable_statuses: list[dict[str, Any]],
    route_partition: object,
) -> dict[str, Any]:
    """Describe only the claim supported by native development-run evidence."""

    boss_death_accepted = False
    accepted_identity: dict[str, Any] | None = None
    partition = route_partition if isinstance(route_partition, dict) else {}
    nodes = partition.get("node_ids")
    node_id = nodes[-1] if isinstance(nodes, list) and nodes else None
    generation = partition.get("node_count")
    terminal_index = partition.get("terminal_index")
    target_entry = partition.get("terminal_target_entry")

    def matches(row: object) -> bool:
        return isinstance(row, dict) and (
            row.get("route_node_id") == node_id
            and row.get("route_generation") == generation
            and row.get("route_kind") == "boss"
        )

    if requested:
        for status in stable_statuses:
            route = status.get("validation_route")
            if not isinstance(route, dict):
                continue
            terminal = route.get("terminal_evidence")
            deaths = route.get("boss_death_evidence")
            boss_death_accepted = bool(
                partition.get("terminal_kind") == "boss"
                and isinstance(node_id, str) and bool(node_id)
                and isinstance(generation, int)
                and not isinstance(generation, bool)
                and generation > 0
                and isinstance(target_entry, int)
                and not isinstance(target_entry, bool)
                and target_entry > 0
                and route.get("node_id") == node_id
                and route.get("kind") == "boss"
                and route.get("generation") == generation
                and route.get("manifest_index") == terminal_index
                and route.get("manifest_count") == generation
                and route.get("manifest_complete") is True
                and isinstance(terminal, list)
                and any(matches(row) for row in terminal)
                and isinstance(deaths, list)
                and any(
                    matches(row)
                    and row.get("target_entry") == target_entry
                    and isinstance(row.get("target_id"), int)
                    and not isinstance(row.get("target_id"), bool)
                    and row.get("target_id") > 0
                    and row.get("result") == "confirmed_unit_death"
                    for row in deaths if isinstance(row, dict)
                )
            )
            if boss_death_accepted:
                accepted_identity = {
                    "route_node_id": node_id,
                    "route_generation": generation,
                    "target_entry": target_entry,
                }
                break
    return {
        "requested": requested,
        "claim_class": "development_diagnostic" if requested else None,
        "training_eligible": False if requested else None,
        "qualification_eligible": False if requested else None,
        "native_boss_death_required": True if requested else None,
        "native_boss_death_accepted": boss_death_accepted if requested else None,
        "accepted_boss_identity": accepted_identity,
    }


def finalize_capture(setup: CaptureSetup, run: CaptureRunResult) -> int:
    args = setup.args
    config = setup.config
    output = setup.output
    worktree = setup.worktree
    profile_name = setup.profile_name
    scenario_id = setup.scenario_id
    raw_output = setup.raw_output
    server_log_output = setup.server_log_output
    recurrence_admission = setup.recurrence_admission
    checkpoint_arm_command = setup.checkpoint_arm_command
    preflight = setup.preflight
    identity_before = setup.identity_before
    runtime_assets = setup.runtime_assets
    controller_route_hold_scheduler = setup.controller_route_hold_scheduler
    drudge_observed = setup.drudge_observed
    drudge_required = setup.drudge_required
    drudge_navmesh_preflight = setup.drudge_navmesh_preflight
    drudge_frozen_anchors = setup.drudge_frozen_anchors
    build_provenance = setup.build_provenance

    started_utc = run.started_utc
    recovery_required = run.recovery_required
    stable = run.stable
    last_rejections = run.last_rejections
    startup_error = run.startup_error
    process_return_code = run.process_return_code
    telemetry_scheduler = run.telemetry_scheduler
    telemetry_transport_ledger = run.telemetry_transport_ledger
    telemetry_command_counts = run.telemetry_command_counts
    trace_transport_pressure_gate = run.trace_transport_pressure_gate
    operator_interrupt = run.operator_interrupt
    shutdown_error = run.shutdown_error
    stop_commands_sent = run.stop_commands_sent
    checkpoint_arm_command_sent = run.checkpoint_arm_command_sent
    checkpoint_arm_gate = run.checkpoint_arm_gate
    resource_samples = run.resource_samples
    resource_sampling_errors = run.resource_sampling_errors
    resource_sampling_error_count = run.resource_sampling_error_count
    resource_tick_rate = run.resource_tick_rate
    forced_evidence_report = run.forced_evidence_report
    fixture_terminal = run.fixture_terminal
    terminal_failure = run.terminal_failure
    semantic_stall = run.semantic_stall
    controller_watchdog = run.controller_watchdog
    trace_transport_gate = run.trace_transport_gate
    telemetry_abort = run.telemetry_abort
    log_bytes = run.log_bytes

    normalized_rows = normalized_batch_payload(log_bytes, profile_name=profile_name)
    telemetry_envelopes = _required_telemetry_envelope_report(
        normalized_rows, profile_name=profile_name,
    )
    raw_payload_sha256, raw_payload_rows = write_normalized_batch(raw_output, normalized_rows)
    # The complete log was decoded once into normalized_rows above.  Project
    # final action channels from those parsed payloads instead of decoding the
    # complete log five more times after every uncapped capture.
    statuses = action_payloads(normalized_rows, "botauto_status")
    active_statuses = [
        status for status in statuses
        if isinstance(status.get("raid_runtime"), dict)
        and status["raid_runtime"].get("active") is True
    ]
    diagnoses = action_payloads(normalized_rows, "botauto_diagnose")
    traces = action_payloads(normalized_rows, "botauto_trace")
    combat_log_payloads = [
        row["payload"] for row in normalized_rows
        if row.get("action") in {
            "botauto_combatlog", "botauto_combatlog_delta",
            "botauto_combatlog_chunk", "botauto_combatlog_complete",
        }
        and isinstance(row.get("payload"), dict)
    ]
    combat_log_transport = combat_log_transport_status(combat_log_payloads)
    combat_log = combined_combat_log(
        combat_log_payloads, expected_status=run.combat_log_status or (stable[0] if stable else None),
    )
    combat_analysis = analyze_combat_log(combat_log) if combat_log else {}
    combat_log_transport["gate_passed"] = bool(
        combat_log_transport.get("complete_marker")
        and combat_log_transport.get("reassembled")
        and combat_log
        and combat_analysis
    )
    profiles = action_payloads(normalized_rows, "botauto_profile")
    stop_rows = action_payloads(normalized_rows, "botauto_stop")
    recovery_accepted, recovery_rejections = (
        accepted_native_recovery(active_statuses, profile_name=profile_name) if recovery_required
        else (True, ["native_recovery_not_required_for_diagnostic_partition"])
    )
    drudge_accepted, drudge_rejections = (
        accepted_drudge_contract(active_statuses, frozen_anchors=drudge_frozen_anchors)
        if drudge_observed
        else (True, ["drudge_contract_not_required_for_diagnostic_partition"])
    )
    cleanup_status = statuses[-1] if statuses else {}
    cleanup_ok = cleanup_status.get("bots") == 0 and cleanup_status.get("lease_count") == 0
    postflight = preflight_runtime_exclusions(worktree)
    process_absent = not postflight["process_overlap"]
    forbidden_entries = _forbidden_assistance_entries(normalized_rows)
    identity_after = git_identity(worktree)
    identity_stable = identity_before == identity_after
    controller_route_hold_receipt = (
        controller_route_hold_scheduler.receipt()
        if controller_route_hold_scheduler is not None
        else {
            "schema": "generic_controller_route_hold_scheduler_v1",
            "enabled": False,
            "phase": "not_requested",
            "gate_passed": None,
            "failure_reason": None,
        }
    )
    resolved_personal_threat_episode_target = setup.personal_threat_episode_target
    personal_threat_episode_target_binding = None
    if setup.personal_threat_episode_target is not None:
        target_runtime_assets = dict(runtime_assets)
        configured_route_manifest = trinity_config_string(
            config, "BotWorld.ValidationRoute.ManifestPath",
        )
        if configured_route_manifest:
            target_runtime_assets["route_manifest"] = configured_route_manifest
            target_runtime_assets["scenario_id"] = scenario_id
        (
            resolved_personal_threat_episode_target,
            personal_threat_episode_target_binding,
        ) = resolve_personal_threat_episode_target(
            setup.personal_threat_episode_target,
            controller_route_hold_receipt=controller_route_hold_receipt,
            runtime_assets=target_runtime_assets,
        )
    controller_terminal = None
    if (
        isinstance(terminal_failure, dict)
        and terminal_failure.get("detected") is True
        and terminal_failure.get("failure_reason") in _CONTROLLER_TERMINAL_FAILURE_REASONS
    ):
        controller_terminal = terminal_failure
    elif isinstance(semantic_stall, dict) and semantic_stall.get("detected") is True:
        controller_terminal = semantic_stall
    demux_report = evidence_demux_report(
        normalized_rows,
        profile_name=profile_name,
        controller_terminal=controller_terminal,
        fixture_terminal=(
            fixture_terminal
            if fixture_terminal.get("detected") is True else None
        ),
        fixture_expected_identity=(
            {
                "actor_guid": MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID,
                "fixture_id": recurrence_admission.get("checkpoint_fixture_id"),
                "case_id": recurrence_admission.get("checkpoint_case_id"),
                "runtime_profile": profile_name,
                "scenario_id": scenario_id,
                "route_manifest_sha256": (
                    (recurrence_admission.get("bindings") or {}).get("route_manifest") or {}
                ).get("sha256"),
                "seal_sha256": recurrence_admission.get("checkpoint_seal_sha256"),
                "source_commit": identity_before.get("head"),
            }
            if isinstance(recurrence_admission, dict)
            and fixture_terminal.get("detected") is True
            else None
        ),
        personal_threat_episode_target=resolved_personal_threat_episode_target,
    )
    if (
        personal_threat_episode_target_binding is not None
        and personal_threat_episode_target_binding.get("gate_passed") is not True
    ):
        binding_rejections = (
            personal_threat_episode_target_binding.get("resolution_receipt") or {}
        ).get("rejections") or [
            "personal_threat_episode_target_resolution_failed"
        ]
        demux_report["rejections"] = list(dict.fromkeys(
            list(demux_report.get("rejections") or [])
            + [str(reason) for reason in binding_rejections]
        ))
        demux_report["gate_passed"] = False
    demux_rejections = demux_report["rejections"]
    default_trace_transport_gate = trace_transport_smoke.evaluate([])
    if trace_transport_gate is None:
        trace_transport_gate = default_trace_transport_gate
    trace_transport_demux = trace_transport_smoke.demux_report(
        normalized_rows, trace_transport_gate,
    ) if args.trace_transport_smoke else {
        "gate_passed": None,
        "rejections": ["trace_transport_smoke_not_requested"],
    }
    primary_gameplay_failure = _primary_gameplay_terminal(
        terminal_failure, semantic_stall,
    )
    terminal_evidence_incomplete = False if args.trace_transport_smoke else _terminal_evidence_incomplete(
        primary_gameplay_failure=primary_gameplay_failure,
        forced_evidence_report=forced_evidence_report,
        telemetry_abort=telemetry_abort,
        telemetry_envelopes=telemetry_envelopes,
        demux_rejections=demux_rejections,
    )
    resource_summary = summarize_process_resource_samples(
        resource_samples,
        tick_rate=resource_tick_rate,
        sampling_errors=resource_sampling_errors,
        sampling_error_count=resource_sampling_error_count,
    )
    # From this point through the two immutable output writes, ignore another
    # interrupt. Any prior deferred interrupt is already reflected in the
    # variables used to construct the report and success classification.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    profile_selection_accepted = bool(
        (
            len(profiles) == 1
            and profiles[0].get("ok") is True
            and profiles[0].get("cohort_id") == "default"
            and profiles[0].get("active_profile") == profile_name
        )
        or (
            controller_route_hold_scheduler is not None
            and controller_route_hold_receipt.get("start_ack_count") == 1
            and (
                controller_route_hold_receipt.get("native_scope") or {}
            ).get("runtime_profile") == profile_name
        )
    )
    common_success = (
        startup_error is None
        and operator_interrupt is False
        and process_return_code == 0
        and cleanup_ok
        and bool(stop_rows and stop_rows[-1].get("ok") is True)
        and process_absent
        and postflight["passed"]
        and not forbidden_entries
        and profile_selection_accepted
        and identity_stable
        and fixture_terminal.get("detected") is not True
        and terminal_failure.get("detected") is not True
        and telemetry_abort.get("detected") is not True
        and bool(diagnoses)
        and bool(traces)
    )
    success = common_success and (
        (
            trace_transport_gate.get("gate_passed") is True
            and trace_transport_demux.get("gate_passed") is True
            and recurrence_admission is None
        )
        if args.trace_transport_smoke
        else (
            len(stable) >= args.required_stable_statuses
            and recovery_accepted
            and (not drudge_required or drudge_accepted)
            and telemetry_envelopes["gate_passed"]
            and not demux_rejections
            and semantic_stall.get("detected") is not True
            and forced_evidence_report.get("gate_passed") is True
            and combat_log_transport["gate_passed"] is True
            and (
                controller_route_hold_scheduler is None
                or controller_route_hold_receipt.get("gate_passed") is True
            )
        )
    )
    development_requested = bool(getattr(args, "development_run", False))
    development_claim = development_run_claim(
        requested=development_requested,
        stable_statuses=stable,
        route_partition=runtime_assets.get("route_partition"),
    )
    if development_requested:
        success = success and (
            development_claim["native_boss_death_accepted"] is True
        )
    evidence_incomplete = bool(
        telemetry_abort.get("detected") is True
        or (
            not args.trace_transport_smoke
            and telemetry_envelopes.get("gate_passed") is not True
        )
        or (
            trace_transport_gate.get("gate_passed") is not True
            or trace_transport_demux.get("gate_passed") is not True
            if args.trace_transport_smoke
            else (
                bool(demux_rejections)
                or forced_evidence_report.get("gate_passed") is not True
                or combat_log_transport.get("gate_passed") is not True
            )
        )
    )
    operational_infrastructure_abort = bool(
        startup_error
        or operator_interrupt
        or process_return_code != 0
        or not process_absent
        or not postflight["passed"]
        or not cleanup_ok
        or not identity_stable
        or (
            fixture_terminal.get("detected") is True
            and telemetry_abort.get("detected") is True
        )
        or terminal_failure.get("classification") == "infrastructure_abort"
    )
    if args.trace_transport_smoke:
        if success:
            capture_classification = "trace_transport_smoke_passed"
        elif operational_infrastructure_abort:
            capture_classification = "trace_transport_smoke_infrastructure_abort"
        elif trace_transport_gate.get("terminal") is True:
            capture_classification = "trace_transport_smoke_failed_verification"
        else:
            capture_classification = "trace_transport_smoke_noncompletion"
    else:
        capture_classification = _capture_classification(
            success=success,
            forbidden_entries=forbidden_entries,
            fixture_terminal_observed=(
                fixture_terminal.get("detected") is True
            ),
            primary_gameplay_failure=primary_gameplay_failure,
            operational_infrastructure_abort=operational_infrastructure_abort,
            evidence_incomplete=evidence_incomplete,
        )
    report = {
        "schema_version": 1,
        "capture_id": f"cata_raid_phase1_{profile_name}_v1",
        "classification": capture_classification,
        "claim_scope": (
            {
                **trace_transport_smoke.claim_scope(),
                "transport_admitted": success,
            }
            if args.trace_transport_smoke
            else development_claim if development_requested else None
        ),
        "development_run": development_claim,
        "trace_transport_smoke": {
            "requested": args.trace_transport_smoke,
            "pressure_warmup_seconds": (
                trace_transport_smoke.PRESSURE_WARMUP_SECONDS
                if args.trace_transport_smoke else None
            ),
            "transport_gate": trace_transport_gate,
            "controller_demux_gate": trace_transport_demux,
            "pressure_receipt_gate": trace_transport_pressure_gate,
            "pressure_command_count": telemetry_command_counts["trace_pressure"],
            "one_start_owned_by_capture": True,
        },
        "terminal_evidence_incomplete": terminal_evidence_incomplete,
        "started_at_utc": started_utc,
        "identity": identity_before,
        "scenario_id": scenario_id,
        "runtime_profile": profile_name,
        "pool_tag_filter": runtime_assets.get("pool_tag_filter"),
        "identity_stable_during_run": identity_stable,
        "recurrence_admission": recurrence_admission,
        "chainwielder_checkpoint_arm": {
            "required": checkpoint_arm_command is not None,
            "actor_guid": (
                getattr(args, "magmaw_transfer_checkpoint_actor_guid", None)
                or args.chainwielder_checkpoint_actor_guid
            ),
            "seal_sha256": (
                recurrence_admission.get("checkpoint_seal_sha256")
                if isinstance(recurrence_admission, dict) else None
            ),
            "command_sent": checkpoint_arm_command_sent,
            "gate": checkpoint_arm_gate,
        },
        "controller_route_hold": controller_route_hold_receipt,
        "build_provenance": build_provenance,
        "runtime_profile_assets": runtime_assets,
        "runtime_asset_closure": setup.runtime_asset_closure,
        "drudge_navmesh_preflight": drudge_navmesh_preflight,
        "binary_sha256": build_provenance.get("binary_sha256"),
        "config_sha256": sha256_file(config),
        "worldserver_exit_code": process_return_code,
        "startup_error": startup_error,
        "operator_interrupt": operator_interrupt,
        "shutdown_error": shutdown_error,
        "native_shutdown": {
            "commands_sent": stop_commands_sent,
            "bounded_wait_seconds": 20 if operator_interrupt else 60,
            "operator_reason": "operator_interrupt" if operator_interrupt else None,
        },
        "resource_sampling": {
            "source": "proc_pid_stat_and_proc_pid_status_via_capture_no_bots_baseline",
            "interval_seconds": args.resource_sample_interval_sec,
            "samples_retained": True,
            "summary": resource_summary,
            "samples": resource_samples,
            "sampling_errors": resource_sampling_errors,
        },
        "required_stable_statuses": args.required_stable_statuses,
        "accepted_stable_statuses": len(stable),
        "last_foundation_rejections": last_rejections,
        "native_recovery_accepted": recovery_accepted,
        "native_recovery_required": recovery_required,
        "native_recovery_rejections": recovery_rejections,
        "drudge_contract_accepted": drudge_accepted,
        "drudge_contract_required": drudge_required,
        "drudge_contract_rejections": drudge_rejections,
        "fixture_terminal": fixture_terminal,
        "terminal_failure": terminal_failure,
        "semantic_stall": semantic_stall,
        "telemetry_abort": telemetry_abort,
        "telemetry_schedule": {
            "status_interval_seconds": args.status_interval_sec,
            "diagnose_interval_seconds": args.diagnose_interval_sec,
            "trace_interval_seconds": args.trace_interval_sec,
            "commands_sent": telemetry_command_counts,
            "scheduler_state": telemetry_scheduler.state() if telemetry_scheduler is not None else None,
            "trace_transport_receipts": telemetry_transport_ledger.receipts(),
            "material_status_diagnosis": "immediate",
            "stall_bundle": (
                "forced_diagnose_trace_delta_and_bounded_combat_log_before_termination"
            ),
            "final_forced_evidence": forced_evidence_report,
        },
        "accepted_raid_runtime": (
            None if args.trace_transport_smoke
            else (stable[-1].get("raid_runtime") if stable else None)
        ),
        "diagnose_observed": bool(diagnoses),
        "trace_observed": bool(traces),
        "combat_log_transport": combat_log_transport,
        "combat_log_event_stream": (
            combat_log.get("event_stream_receipt", {})
            if isinstance(combat_log, dict) else {}
        ),
        "combat_analysis": combat_analysis,
        "required_telemetry_envelopes": telemetry_envelopes,
        "profile_selection_observed": profile_selection_accepted,
        "stop_observed": bool(stop_rows),
        "native_event_evidence": {
            "source": "botauto_status.raid_runtime",
            "ordered_transition_reconstruction": recovery_accepted,
            "rejections": recovery_rejections,
            "synthetic_wipe_or_encounter_command_sent": False,
        },
        "drudge_contract_evidence": {
            "source": "botauto_status.raid_runtime.drudge_charge",
            "acceptance_role": "diagnostic_only",
            "independently_reconstructed": drudge_accepted,
            "rejections": drudge_rejections,
            "requirements": "two delivered native Rushes per exact source; one non-early 20000ms interval per source; exact-roster reseparation; exact native tank ownership; any recorded taunts are successful tank casts; tank health-sync hold; all seven offensive slots use trained single-target profiles",
        },
        "forbidden_assistance": {
            "observed": bool(forbidden_entries),
            "entries": forbidden_entries,
            "gate_passed": not forbidden_entries,
            "policy": "native encounter events only; no forced state, teleport, spawn, kill, resurrection, or aura assistance",
        },
        "watchdog": {
            "policy": "capture-process-heartbeat-terminal-gate-driven",
            "controller_policy": "scoped-repeated-decision-or-death-loop-terminal",
            "heartbeat_rows": len(statuses) + len(diagnoses) + len(traces),
            "wall_clock_mode": "uncapped" if args.observe_sec == 0 else "bounded_diagnostic",
            "observe_window_seconds": args.observe_sec if args.observe_sec else None,
            "startup_timeout_seconds": args.startup_timeout_sec,
            "semantic_stall_seconds": args.semantic_stall_sec,
            "semantic_stall_min_samples": args.semantic_stall_min_samples,
            "max_repeated_decisions": args.max_repeated_decision_count,
            "max_death_loops": args.max_death_loop_count,
            "max_repeated_decision_count": args.max_repeated_decision_count,
            "max_death_loop_count": args.max_death_loop_count,
            "controller_terminal": controller_watchdog,
            "telemetry_timeout_seconds": args.telemetry_timeout_sec,
            "telemetry_intervals_seconds": {
                "status": args.status_interval_sec,
                "diagnose": args.diagnose_interval_sec,
                "trace": args.trace_interval_sec,
            },
            "telemetry_commands_sent": telemetry_command_counts,
            "required_channels": [
                "status", "diagnosis", "trace", "combat_log",
            ],
            "healthy": (
                startup_error is None
                and operator_interrupt is False
                and telemetry_abort.get("detected") is not True
                and forced_evidence_report.get("gate_passed") is True
                and bool(statuses) and bool(diagnoses) and bool(traces)
                and process_return_code == 0 and process_absent
            ),
        },
        "preflight": preflight,
        "postflight": postflight,
        "cleanup": {
            "zero_bots": cleanup_status.get("bots") == 0,
            "zero_leases": cleanup_status.get("lease_count") == 0,
            "stop_observed": bool(stop_rows),
            "stop_ok": bool(stop_rows and stop_rows[-1].get("ok") is True),
            "worldserver_process_absent": process_absent,
            "gate_passed": cleanup_ok and process_absent and bool(stop_rows and stop_rows[-1].get("ok") is True),
        },
        "cleanup_zero_bots_and_leases": cleanup_ok,
        "log_sha256": hashlib.sha256(log_bytes).hexdigest(),
        "log_bytes": len(log_bytes),
        "raw_log_retained": True,
        "raw_server_log": {
            "path": str(server_log_output),
            "sha256": hashlib.sha256(log_bytes).hexdigest(),
            "bytes": len(log_bytes),
            "immutable": True,
        },
        "raw_normalized_batch": {
            "path": str(raw_output),
            "sha256": raw_payload_sha256,
            "row_count": raw_payload_rows,
            "immutable": True,
        },
        "evidence_demux": {
            "normalized_schema_version": 2,
            "retained_rows": demux_report["retained_rows"],
            "bound_rows": demux_report["bound_rows"],
            "rejected_rows": demux_report["rejected_rows"],
            "unchecked_rows": demux_report["unchecked_rows"],
            "canonical_identity_sha256": demux_report["canonical_identity_sha256"],
            "canonical_roster_sha256": demux_report["canonical_roster_sha256"],
            "required_telemetry_envelopes": demux_report["required_telemetry_envelopes"],
            "actor_binding_counts": demux_report["actor_binding_counts"],
            "trace_discontinuities": demux_report["trace_discontinuities"],
            "personal_threat_episode_join": demux_report[
                "personal_threat_episode_join"
            ],
            "channels": dict(Counter(str(row.get("evidence_channel")) for row in normalized_rows)),
            "every_retained_row_demuxed": (
                demux_report["bound_rows"] == demux_report["retained_rows"]
                and demux_report["unchecked_rows"] == 0
            ),
            "identity_rejections": demux_rejections,
            "gate_passed": demux_report["gate_passed"],
        },
    }
    if personal_threat_episode_target_binding is not None:
        report["personal_threat_episode_target_binding"] = (
            personal_threat_episode_target_binding
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    report["optimization_acceptance"] = {
        "clear_accepted": (
            report.get("development_run", {}).get("native_boss_death_accepted") is True
            and report.get("classification") == "success"
        ),
        "repair_edge_accepted": None,
        "performance_accepted": None,
        "state": "requires_closed_run_review_and_baseline_comparison",
    }
    report["artifact_inventory"] = [
        _artifact_record(raw_output, "raw_normalized_jsonl"),
        _artifact_record(server_log_output, "raw_worldserver_log"),
    ]
    # Render from the same bound rows before final hashing. Failure preserves
    # the native clear/cleanup evidence but cannot silently complete the
    # diagnostic workflow without its primary view.
    from tools.raid_program.capture_timeline_artifacts import attach_capture_timeline
    if not attach_capture_timeline(
        normalized_rows, report, output, raw_sha256=raw_payload_sha256,
    ):
        success = False
    report["capture_success"] = success
    # The report entry is a deliberate self-reference.  Its digest is the
    # canonical report hash after nulling both self-reference fields; this is
    # stable and independently reproducible without a circular hash.
    report["artifact_inventory"].append(
        {
            "kind": "capture_report",
            "path": str(output),
            "sha256": None,
            "bytes": 0,
            "immutable": True,
            "hash_basis": "canonical_report_with_report_sha256_and_self_inventory_sha256_null",
        }
    )
    for _ in range(8):
        encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        report["artifact_inventory"][-1]["bytes"] = len(encoded)
        hash_payload = json.loads(json.dumps(report))
        hash_payload["report_sha256"] = None
        hash_payload["artifact_inventory"][-1]["sha256"] = None
        report_hash = hashlib.sha256(
            json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        report["artifact_inventory"][-1]["sha256"] = report_hash
        report["report_sha256"] = report_hash
        final_encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if report["artifact_inventory"][-1]["bytes"] == len(final_encoded):
            break
    output.write_bytes(final_encoded)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if success else 2
