from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
from math import hypot, isfinite
from pathlib import Path
import re
import signal
import sys
from typing import Any

try:
    from tools.bot_ml.analyze_combat_log import analyze_combat_log
    from tools.bot_ml.run_live_bot_validation import (
        combined_combat_log,
        combat_log_transport_status,
        trinity_config_bool,
        trinity_config_string,
    )
    from tools.raid_program.capture_checkpoint_controller import (
        _initialize_chainwielder_checkpoint_arm_gate,
        chainwielder_checkpoint_arm_command,
        chainwielder_checkpoint_monitor_commands,
        chainwielder_checkpoint_pre_route_readiness,
        observe_chainwielder_checkpoint_arm_gate,
    )
    from tools.raid_program.controller_route_hold import (
        ControllerRouteHoldLaunchIdentity,
        ControllerRouteHoldScheduler,
        controller_route_hold_launch_identity,
    )
    from tools.raid_program.capture_progress import (
        observe_monotonic_semantic_progress,
        ready_for_native_readycheck,
        semantic_progress_signature,
    )
    from tools.raid_program.capture_evidence_demux import (
        _required_telemetry_envelope_report,
        _trace_actor_transport_rejections,
        evidence_demux_report as _evidence_demux_report_impl,
        normalized_batch_payload as _normalized_batch_payload_impl,
    )
    from tools.raid_program.capture_drudge_contract import accepted_drudge_contract
    from tools.raid_program.capture_drudge_geometry import (
        _frozen_drudge_member_anchors,
        _validate_drudge_observation_geometry,
    )
    from tools.raid_program.capture_environment_validation import (
        EXPECTED_BWD_ROUTE_IDENTITY,
        EXPECTED_BWD_ROUTE_PARTITION_COUNTS,
        _dvc_status_is_clean,
        _process_arguments,
        _protected_process_matches,
        _utc_timestamp,
        build_policy_path_for_receipt,
        git_identity,
        preflight_runtime_exclusions,
        sha256_file,
        validate_build_receipt,
        validate_runtime_profile_assets,
    )
    from tools.raid_program.capture_forced_evidence import (
        FORBIDDEN_ASSISTANCE_FIELDS,
        FORBIDDEN_MARKER_FIELDS,
        FORBIDDEN_MARKER_RE,
        _forbidden_assistance_entries,
        validate_forced_combat_log_bundle,
        validate_forced_evidence_bundle,
    )
    from tools.raid_program.capture_finalization import (
        evidence_demux_rejections,
        evidence_demux_report,
        finalize_capture,
        normalized_batch_payload,
        write_normalized_batch,
    )
    from tools.raid_program.capture_live_run import (
        CaptureRunResult,
        execute_capture_run,
    )
    from tools.raid_program.capture_telemetry_transport import (
        TRACE_PRESSURE_INTERVAL_SEC,
        TRACE_PRESSURE_WATERMARK,
        TRACE_RING_CAPACITY,
        JsonLogCursor,
        JsonLogObservation,
        TelemetryScheduler,
        TelemetryTransportLedger,
        _json_row_from_log_line,
        action_payloads,
        collect_log_observations,
        json_actions,
        json_rows,
        material_status_signature,
        observe_telemetry_freshness,
    )
    from tools.raid_program.capture_runtime_identity import (
        IDENTITY_FIELDS,
        ROSTER_BINDING_ID_FIELDS,
        ROSTER_ID_FIELDS,
        STRATEGY_FIELD,
        _roster_binding_identity,
        _roster_binding_lifecycle_rejections,
        _route_advancement_marker,
        _runtime_identity,
    )
    from tools.raid_program.capture_run_outcome import (
        _capture_classification,
        _primary_gameplay_terminal,
        _terminal_evidence_incomplete,
        process_resource_sample,
        summarize_process_resource_samples,
    )
    from tools.raid_program.capture_runtime_io import (
        _artifact_record,
        bounded_native_shutdown,
        wait_for_prompt,
    )
    from tools.raid_program.capture_setup import (
        CaptureSetup,
        build_capture_parser,
        prepare_capture_setup,
    )
    from tools.raid_program.capture_runtime_acceptance import (
        _canonical_int_list,
        _compact_trailing_zero_gems,
        _expected_identity_by_slot,
        _identity_manifest_rejections,
        _provisioned_bwd_10n_bots,
        _provisioned_bwd_bots,
        _roster_identity,
        _roster_rejections,
        _runtime_gear_manifest,
        accepted_foundation_status,
        accepted_native_recovery,
        expected_bwd_10n_roster,
        native_readycheck_request_identity,
        terminal_preflight_failure_reason,
        terminal_runtime_failure_reason,
    )
    from tools.raid_program.capture_value_types import (
        _canonical_object_sha256,
        _nonnegative_int,
        _positive_int,
        _uint64_int,
    )
    from tools.raid_program.capture_watchdog import (
        DEFAULT_MAX_DEATH_LOOPS,
        DEFAULT_MAX_REPEATED_DECISIONS,
        _CONTROLLER_TERMINAL_FAILURE_REASONS,
        observe_capture_watchdog,
    )
    from tools.raid_program.probe_drudge_navmesh_recovery import run_probe as _drudge_navmesh_probe
    from tools.raid_program.recurrence_admission import (
        CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        FIXTURE_EXPANSION_PURPOSE,
        GAMEPLAY_CANARY_PURPOSE,
        RecurrenceAdmissionError,
        verify_recurrence_admission,
    )
    from tools.raid_program import trace_transport_smoke
except ModuleNotFoundError:
    # Direct execution places tools/raid_program, not the repository root, on
    # sys.path. Keep the CLI and imported test/module paths on the same sampler.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.bot_ml.analyze_combat_log import analyze_combat_log
    from tools.bot_ml.run_live_bot_validation import (
        combined_combat_log,
        combat_log_transport_status,
        trinity_config_bool,
        trinity_config_string,
    )
    from capture_checkpoint_controller import (
        _initialize_chainwielder_checkpoint_arm_gate,
        chainwielder_checkpoint_arm_command,
        chainwielder_checkpoint_monitor_commands,
        chainwielder_checkpoint_pre_route_readiness,
        observe_chainwielder_checkpoint_arm_gate,
    )
    from controller_route_hold import (
        ControllerRouteHoldLaunchIdentity,
        ControllerRouteHoldScheduler,
        controller_route_hold_launch_identity,
    )
    from capture_progress import (
        observe_monotonic_semantic_progress,
        ready_for_native_readycheck,
        semantic_progress_signature,
    )
    from capture_evidence_demux import (
        _required_telemetry_envelope_report,
        _trace_actor_transport_rejections,
        evidence_demux_report as _evidence_demux_report_impl,
        normalized_batch_payload as _normalized_batch_payload_impl,
    )
    from capture_drudge_contract import accepted_drudge_contract
    from capture_drudge_geometry import (
        _frozen_drudge_member_anchors,
        _validate_drudge_observation_geometry,
    )
    from capture_environment_validation import (
        EXPECTED_BWD_ROUTE_IDENTITY,
        EXPECTED_BWD_ROUTE_PARTITION_COUNTS,
        _dvc_status_is_clean,
        _process_arguments,
        _protected_process_matches,
        _utc_timestamp,
        build_policy_path_for_receipt,
        git_identity,
        preflight_runtime_exclusions,
        sha256_file,
        validate_build_receipt,
        validate_runtime_profile_assets,
    )
    from capture_forced_evidence import (
        FORBIDDEN_ASSISTANCE_FIELDS,
        FORBIDDEN_MARKER_FIELDS,
        FORBIDDEN_MARKER_RE,
        _forbidden_assistance_entries,
        validate_forced_combat_log_bundle,
        validate_forced_evidence_bundle,
    )
    from capture_finalization import (
        evidence_demux_rejections,
        evidence_demux_report,
        finalize_capture,
        normalized_batch_payload,
        write_normalized_batch,
    )
    from capture_live_run import (
        CaptureRunResult,
        execute_capture_run,
    )
    from capture_telemetry_transport import (
        TRACE_PRESSURE_INTERVAL_SEC,
        TRACE_PRESSURE_WATERMARK,
        TRACE_RING_CAPACITY,
        JsonLogCursor,
        JsonLogObservation,
        TelemetryScheduler,
        TelemetryTransportLedger,
        _json_row_from_log_line,
        action_payloads,
        collect_log_observations,
        json_actions,
        json_rows,
        material_status_signature,
        observe_telemetry_freshness,
    )
    from capture_runtime_identity import (
        IDENTITY_FIELDS,
        ROSTER_BINDING_ID_FIELDS,
        ROSTER_ID_FIELDS,
        STRATEGY_FIELD,
        _roster_binding_identity,
        _roster_binding_lifecycle_rejections,
        _route_advancement_marker,
        _runtime_identity,
    )
    from capture_run_outcome import (
        _capture_classification,
        _primary_gameplay_terminal,
        _terminal_evidence_incomplete,
        process_resource_sample,
        summarize_process_resource_samples,
    )
    from capture_runtime_io import (
        _artifact_record,
        bounded_native_shutdown,
        wait_for_prompt,
    )
    from capture_setup import (
        CaptureSetup,
        build_capture_parser,
        prepare_capture_setup,
    )
    from capture_runtime_acceptance import (
        _canonical_int_list,
        _compact_trailing_zero_gems,
        _expected_identity_by_slot,
        _identity_manifest_rejections,
        _provisioned_bwd_10n_bots,
        _provisioned_bwd_bots,
        _roster_identity,
        _roster_rejections,
        _runtime_gear_manifest,
        accepted_foundation_status,
        accepted_native_recovery,
        expected_bwd_10n_roster,
        native_readycheck_request_identity,
        terminal_preflight_failure_reason,
        terminal_runtime_failure_reason,
    )
    from capture_value_types import (
        _canonical_object_sha256,
        _nonnegative_int,
        _positive_int,
        _uint64_int,
    )
    from capture_watchdog import (
        DEFAULT_MAX_DEATH_LOOPS,
        DEFAULT_MAX_REPEATED_DECISIONS,
        _CONTROLLER_TERMINAL_FAILURE_REASONS,
        observe_capture_watchdog,
    )
    from probe_drudge_navmesh_recovery import run_probe as _drudge_navmesh_probe
    from recurrence_admission import (
        CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        FIXTURE_EXPANSION_PURPOSE,
        GAMEPLAY_CANARY_PURPOSE,
        RecurrenceAdmissionError,
        verify_recurrence_admission,
    )
    import trace_transport_smoke


ROOT = Path(__file__).resolve().parents[2]



















































































def main() -> int:
    setup = prepare_capture_setup(root=ROOT)
    run = execute_capture_run(setup)
    return finalize_capture(setup, run)


if __name__ == "__main__":
    raise SystemExit(main())
