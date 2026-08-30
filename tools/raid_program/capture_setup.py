from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Sequence

from tools.bot_ml.run_live_bot_validation import (
    trinity_config_bool,
    trinity_config_string,
)
from tools.raid_program.capture_checkpoint_controller import (
    chainwielder_checkpoint_arm_command,
)
from tools.raid_program.capture_drudge_geometry import (
    _frozen_drudge_member_anchors,
)
from tools.raid_program.capture_environment_validation import (
    build_policy_path_for_receipt,
    git_identity,
    preflight_runtime_exclusions,
    validate_build_receipt,
    validate_runtime_profile_assets,
)
from tools.raid_program.capture_watchdog import (
    DEFAULT_MAX_DEATH_LOOPS,
    DEFAULT_MAX_REPEATED_DECISIONS,
)
from tools.raid_program.controller_route_hold import (
    ControllerRouteHoldScheduler,
    controller_route_hold_launch_identity,
)
from tools.raid_program.probe_drudge_navmesh_recovery import run_probe as _drudge_navmesh_probe
from tools.raid_program.recurrence_admission import (
    FIXTURE_EXPANSION_PURPOSE,
    GAMEPLAY_CANARY_PURPOSE,
    RecurrenceAdmissionError,
    verify_recurrence_admission,
)
from tools.raid_program import trace_transport_smoke


ROOT = Path(__file__).resolve().parents[2]
SHA256_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class CaptureSetup:
    args: argparse.Namespace
    binary: Path
    config: Path
    output: Path
    worktree: Path
    profile_name: str
    scenario_id: str
    raw_output: Path
    server_log_output: Path
    recurrence_admission: dict[str, Any] | None
    checkpoint_arm_command: str | None
    preflight: dict[str, Any]
    identity_before: dict[str, Any]
    runtime_assets: dict[str, Any]
    controller_route_hold_scheduler: ControllerRouteHoldScheduler | None
    drudge_observed: bool
    drudge_required: bool
    drudge_navmesh_preflight: dict[str, Any]
    drudge_frozen_anchors: dict[int, tuple[float, float, float]]
    build_provenance: dict[str, Any]


def controller_route_hold_runtime_manifest_identity(
    *, config: Path, admission_path: Path, scenario_id: str,
    runtime_profile: str, expected_admission_sha256: str,
) -> dict[str, str]:
    """Project the exact verified runtime route identity used by native start."""

    if not SHA256_RE.fullmatch(expected_admission_sha256):
        raise ValueError("controller_route_hold_admission_projection_hash_invalid")
    try:
        admission_bytes = admission_path.read_bytes()
        admission = json.loads(admission_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("controller_route_hold_admission_projection_invalid") from error
    if hashlib.sha256(admission_bytes).hexdigest() != expected_admission_sha256:
        raise ValueError("controller_route_hold_admission_projection_hash_mismatch")
    binding = ((admission.get("bindings") or {}).get("route_manifest")
               if isinstance(admission, dict) else None)
    bound_path_text = binding.get("path") if isinstance(binding, dict) else None
    bound_sha256 = binding.get("sha256") if isinstance(binding, dict) else None
    configured_path_text = trinity_config_string(
        config, "BotWorld.ValidationRoute.ManifestPath",
    )
    if not isinstance(bound_path_text, str) or not bound_path_text:
        raise ValueError("controller_route_hold_runtime_manifest_binding_missing")
    if not isinstance(bound_sha256, str) or not SHA256_RE.fullmatch(bound_sha256):
        raise ValueError("controller_route_hold_runtime_manifest_hash_invalid")
    if not configured_path_text:
        raise ValueError("controller_route_hold_runtime_manifest_config_missing")
    configured_path = Path(configured_path_text).resolve()
    if configured_path != Path(bound_path_text).resolve():
        raise ValueError("controller_route_hold_runtime_manifest_path_mismatch")
    try:
        payload_bytes = configured_path.read_bytes()
    except OSError as error:
        raise ValueError("controller_route_hold_runtime_manifest_missing") from error
    if hashlib.sha256(payload_bytes).hexdigest() != bound_sha256:
        raise ValueError("controller_route_hold_runtime_manifest_hash_mismatch")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("controller_route_hold_runtime_manifest_invalid") from error
    rows = payload.get("routes") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise ValueError("controller_route_hold_runtime_manifest_initial_node_missing")
    first = rows[0]
    initial_node_id = first.get("route_node_id")
    if not isinstance(initial_node_id, str) or not initial_node_id.strip():
        raise ValueError("controller_route_hold_runtime_manifest_initial_node_invalid")
    if payload.get("scenario_id") != scenario_id \
            or first.get("scenario_id", scenario_id) != scenario_id \
            or first.get("runtime_profile_id", runtime_profile) != runtime_profile:
        raise ValueError("controller_route_hold_runtime_manifest_identity_mismatch")
    checkpoint_target_node_id = trinity_config_string(
        config, "BotWorld.ValidationRoute.NodeId",
    )
    if not checkpoint_target_node_id:
        raise ValueError("controller_route_hold_checkpoint_target_missing")
    if initial_node_id != checkpoint_target_node_id:
        raise ValueError("controller_route_hold_checkpoint_target_not_initial_node")
    return {
        "route_manifest_path": str(configured_path),
        "route_manifest_sha256": bound_sha256,
        "initial_route_node_id": initial_node_id,
        "checkpoint_target_node_id": checkpoint_target_node_id,
    }


def build_capture_parser(*, root: Path = ROOT) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, default=None)
    parser.add_argument("--server-log-output", type=Path, default=None)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--recurrence-admission", type=Path)
    parser.add_argument("--recurrence-admission-sha256")
    parser.add_argument("--chainwielder-checkpoint-actor-guid", type=int)
    parser.add_argument(
        "--fixture-expansion-replay",
        action="store_true",
        help=(
            "admit one evidence-only fixture expansion while the ordinary "
            "gameplay canary gate remains closed"
        ),
    )
    parser.add_argument(
        "--trace-transport-smoke",
        action="store_true",
        help=(
            "run the typed ten-actor production trace-transport lane; this "
            "mode can never admit route, gameplay, fixture, or acceptance claims"
        ),
    )
    parser.add_argument("--build-attestation", type=Path, default=None)
    parser.add_argument("--worktree", type=Path, default=root)
    parser.add_argument(
        "--scenario-id", default=None,
        help="exact validation scenario partition to execute; defaults to --runtime-profile",
    )
    parser.add_argument(
        "--runtime-profile", default=None,
        help="exact runtime profile to select; defaults to blackwing_descent_10n",
    )
    parser.add_argument(
        "--pool-tag", default=None,
        help="optional exact pool tag; must match the selected runtime profile",
    )
    parser.add_argument(
        "--observe-sec", type=int, default=0,
        help=(
            "optional diagnostic wall-clock limit; 0 (the canonical default) "
            "runs until the terminal acceptance gates are satisfied"
        ),
    )
    parser.add_argument("--startup-timeout-sec", type=int, default=180)
    parser.add_argument("--required-stable-statuses", type=int, default=3)
    parser.add_argument("--semantic-stall-sec", type=int, default=300)
    parser.add_argument("--semantic-stall-min-samples", type=int, default=12)
    parser.add_argument(
        "--max-repeated-decision-count", type=int,
        default=DEFAULT_MAX_REPEATED_DECISIONS,
        help="controller terminal threshold for one scoped failed decision fingerprint",
    )
    parser.add_argument(
        "--max-death-loop-count", type=int,
        default=DEFAULT_MAX_DEATH_LOOPS,
        help="controller terminal threshold for scoped death/recovery events",
    )
    parser.add_argument("--telemetry-timeout-sec", type=int, default=60)
    parser.add_argument(
        "--status-interval-sec", type=float, default=5.0,
        help="status heartbeat cadence; must remain below telemetry timeout",
    )
    parser.add_argument(
        "--diagnose-interval-sec", type=float, default=30.0,
        help="steady-state full semantic diagnosis cadence",
    )
    parser.add_argument(
        "--trace-interval-sec", type=float, default=10.0,
        help="append-only trace-delta export cadence",
    )
    parser.add_argument(
        "--resource-sample-interval-sec", type=float, default=5.0,
        help="low-cost worldserver /proc CPU-tick and RSS sampling cadence",
    )
    return parser


def prepare_capture_setup(
    argv: Sequence[str] | None = None, *, root: Path = ROOT,
) -> CaptureSetup:
    args = build_capture_parser(root=root).parse_args(argv)

    binary = args.binary.resolve()
    config = args.config.resolve()
    output = args.output.resolve()
    worktree = args.worktree.resolve()
    profile_name = args.runtime_profile or args.scenario_id or "blackwing_descent_10n"
    scenario_id = args.scenario_id or profile_name
    if args.runtime_profile and args.scenario_id and args.runtime_profile != args.scenario_id:
        raise SystemExit("runtime profile and scenario ID must identify the same partition")
    raw_output = (args.raw_output or output.with_name(f"{output.stem}.raw.jsonl")).resolve()
    server_log_output = (
        args.server_log_output or output.with_name(f"{output.stem}.worldserver.log")
    ).resolve()
    if output.exists():
        raise SystemExit("output already exists; phase1 artifacts are immutable")
    if raw_output.exists():
        raise SystemExit("raw output already exists; phase1 artifacts are immutable")
    if server_log_output.exists():
        raise SystemExit("server log output already exists; phase1 artifacts are immutable")
    if not binary.is_file() or not config.is_file():
        raise SystemExit("binary and config must exist")
    trace_transport_admission_rejections = trace_transport_smoke.admission_rejections(
        profile=profile_name,
        scenario=scenario_id,
        pool_tag=args.pool_tag,
        recurrence_supplied=(
            args.recurrence_admission is not None
            or bool(args.recurrence_admission_sha256)
        ),
        fixture_expansion=args.fixture_expansion_replay,
        observe_seconds=args.observe_sec,
    ) if args.trace_transport_smoke else []
    if trace_transport_admission_rejections:
        raise SystemExit(
            "capture preflight rejected: "
            + ",".join(trace_transport_admission_rejections)
        )
    recurrence_admission: dict[str, Any] | None = None
    recurrence_required = scenario_id == "blackwing_descent_10n_magmaw_diagnostic"
    if args.fixture_expansion_replay and not recurrence_required:
        raise SystemExit(
            "capture preflight rejected: fixture_expansion_route_mismatch"
        )
    if recurrence_required and (
        args.recurrence_admission is None or not args.recurrence_admission_sha256
    ):
        raise SystemExit(
            "capture preflight rejected: magmaw_recurrence_admission_required"
        )
    if args.recurrence_admission is not None or args.recurrence_admission_sha256:
        if args.recurrence_admission is None or not args.recurrence_admission_sha256:
            raise SystemExit(
                "capture preflight rejected: incomplete_recurrence_admission_binding"
            )
        try:
            recurrence_admission = verify_recurrence_admission(
                admission_path=args.recurrence_admission,
                expected_sha256=args.recurrence_admission_sha256,
                worktree=worktree,
                binary=binary,
                build_receipt=args.build_receipt.resolve(),
                runtime_config=config,
                required_purpose=(
                    FIXTURE_EXPANSION_PURPOSE
                    if args.fixture_expansion_replay
                    else GAMEPLAY_CANARY_PURPOSE
                ),
            )
        except RecurrenceAdmissionError as error:
            raise SystemExit(
                f"capture preflight rejected: recurrence_admission:{error}"
            ) from error
    try:
        checkpoint_arm_command = chainwielder_checkpoint_arm_command(
            recurrence_admission,
            args.chainwielder_checkpoint_actor_guid,
        )
    except ValueError as error:
        raise SystemExit(
            f"capture preflight rejected: checkpoint_arm:{error}"
        ) from error
    # This controller owns the single explicit native start command. A
    # prepare-only runner must not leave worldserver AutoStart enabled because
    # duplicate profile selection tears down the first cohort during startup.
    if trinity_config_bool(config, "BotWorld.AutoStart", False):
        raise SystemExit(
            "capture preflight rejected: config_autostart_enabled; "
            "phase1 capture owns the single botauto start command"
        )
    if (
        args.observe_sec < 0
        or 0 < args.observe_sec < 30
        or args.required_stable_statuses < 2
        or args.max_repeated_decision_count <= 0
        or args.max_death_loop_count <= 0
    ):
        raise SystemExit(
            "observation must be uncapped (0) or at least 30 seconds, require at least two stable statuses, and use positive watchdog thresholds"
        )
    if args.semantic_stall_sec < 60 or args.semantic_stall_min_samples < 3:
        raise SystemExit("semantic stall detection requires at least 60 seconds and three samples")
    if args.telemetry_timeout_sec < 15:
        raise SystemExit("telemetry freshness timeout must be at least 15 seconds")
    if any(interval <= 0 for interval in (
        args.status_interval_sec, args.diagnose_interval_sec, args.trace_interval_sec,
        args.resource_sample_interval_sec,
    )):
        raise SystemExit("telemetry intervals must be positive")
    if any(interval >= args.telemetry_timeout_sec for interval in (
        args.status_interval_sec, args.diagnose_interval_sec, args.trace_interval_sec,
    )):
        raise SystemExit("telemetry intervals must be shorter than the freshness timeout")
    preflight = preflight_runtime_exclusions(worktree)
    if not preflight["passed"]:
        raise SystemExit("capture preflight rejected: " + ",".join(preflight["reasons"]))

    identity_before = git_identity(worktree)
    if not identity_before["clean"]:
        raise SystemExit("canonical phase1 capture requires a clean worktree")
    runtime_assets = (
        trace_transport_smoke.validate_profile_assets(worktree)
        if args.trace_transport_smoke
        else validate_runtime_profile_assets(
            worktree,
            profile_name=profile_name,
            scenario_id=scenario_id,
            pool_tag=args.pool_tag,
        )
    )
    if not runtime_assets["passed"]:
        raise SystemExit("runtime profile assets rejected: " + ",".join(runtime_assets["reasons"]))
    route_manifest = runtime_assets.get("route_manifest")
    controller_route_hold_scheduler: ControllerRouteHoldScheduler | None = None
    if args.fixture_expansion_replay:
        try:
            if args.recurrence_admission is None:
                raise ValueError("controller_route_hold_verified_admission_missing")
            runtime_route_identity = controller_route_hold_runtime_manifest_identity(
                config=config,
                admission_path=args.recurrence_admission.resolve(),
                scenario_id=scenario_id,
                runtime_profile=profile_name,
                expected_admission_sha256=args.recurrence_admission_sha256,
            )
            controller_hold_identity = controller_route_hold_launch_identity(
                recurrence_admission=recurrence_admission,
                required_purpose=FIXTURE_EXPANSION_PURPOSE,
                actor_guid=args.chainwielder_checkpoint_actor_guid,
                scenario_id=scenario_id,
                runtime_profile=profile_name,
                pool_tag=str(runtime_assets.get("pool_tag_filter") or ""),
                route_manifest_sha256=runtime_route_identity[
                    "route_manifest_sha256"
                ],
                route_node_id=runtime_route_identity["initial_route_node_id"],
            )
        except ValueError as error:
            raise SystemExit(
                f"capture preflight rejected: controller_route_hold:{error}"
            ) from error
        if controller_hold_identity is None:
            raise SystemExit(
                "capture preflight rejected: controller_route_hold_identity_missing"
            )
        controller_route_hold_scheduler = ControllerRouteHoldScheduler(
            controller_hold_identity,
        )
    drudge_observed = not args.trace_transport_smoke and (
        profile_name == "blackwing_descent_10n"
        or profile_name.endswith("_magmaw_diagnostic")
    )
    # Retain the exact lane/re-separation contract as diagnostic evidence;
    # trash acceptance itself remains outcome-based.
    drudge_required = False
    drudge_navmesh_preflight: dict[str, Any] = {
        "required": drudge_observed,
        "all_passed": None,
    }
    if drudge_observed:
        try:
            drudge_navmesh_preflight = {
                "required": True,
                **_drudge_navmesh_probe(worktree),
            }
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            raise SystemExit(f"drudge navmesh preflight rejected: {exc}") from exc
    drudge_frozen_anchors = _frozen_drudge_member_anchors(
        Path(route_manifest) if isinstance(route_manifest, str) else None
    )
    if (profile_name == "blackwing_descent_10n" or profile_name.endswith("_magmaw_diagnostic")) \
            and set(drudge_frozen_anchors) != set(range(1, 11)):
        raise SystemExit("runtime profile assets rejected: drudge_frozen_member_anchors_missing")
    try:
        build_policy_path = build_policy_path_for_receipt(
            args.build_receipt.resolve(), worktree,
        )
    except RuntimeError as error:
        raise SystemExit(f"build receipt rejected: {error}") from error
    build_provenance = validate_build_receipt(
        args.build_receipt.resolve(),
        build_policy_path,
        worktree, binary, config,
        args.build_attestation.resolve() if args.build_attestation is not None else None,
    )
    if not build_provenance.get("valid"):
        raise SystemExit("build receipt rejected: " + ",".join(build_provenance.get("rejections", [])))

    return CaptureSetup(
        args=args,
        binary=binary,
        config=config,
        output=output,
        worktree=worktree,
        profile_name=profile_name,
        scenario_id=scenario_id,
        raw_output=raw_output,
        server_log_output=server_log_output,
        recurrence_admission=recurrence_admission,
        checkpoint_arm_command=checkpoint_arm_command,
        preflight=preflight,
        identity_before=identity_before,
        runtime_assets=runtime_assets,
        controller_route_hold_scheduler=controller_route_hold_scheduler,
        drudge_observed=drudge_observed,
        drudge_required=drudge_required,
        drudge_navmesh_preflight=drudge_navmesh_preflight,
        drudge_frozen_anchors=drudge_frozen_anchors,
        build_provenance=build_provenance,
    )
