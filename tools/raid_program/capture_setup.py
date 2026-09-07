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
    checkpoint_controller_dialect,
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
from tools.raid_program.prestart_bundle_dialects import (
    PROFILE_COMBAT_RANGE_ACTOR_GUID,
    PROFILE_COMBAT_RANGE_TARGET_GUID,
)
from tools.raid_program.controller_route_hold import (
    ControllerRouteHoldScheduler,
    controller_route_hold_launch_identity,
)
from tools.raid_program.probe_drudge_navmesh_recovery import run_probe as _drudge_navmesh_probe
from tools.raid_program.recurrence_admission import (
    CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
    FIXTURE_EXPANSION_PURPOSE,
    PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
    GAMEPLAY_CANARY_PURPOSE,
    RecurrenceAdmissionError,
    verify_recurrence_admission,
)
from tools.raid_program.runtime_asset_closure import (
    add_runtime_asset_closure_arguments,
    enforce_runtime_asset_closure_from_args,
)
from tools.raid_program import trace_transport_smoke


ROOT = Path(__file__).resolve().parents[2]
SHA256_RE = re.compile(r"[0-9a-f]{64}")
PERSONAL_THREAT_EPISODE_TARGET_FIELDS = (
    "actor_guid",
    "scope_key",
    "route_node_id",
    "route_generation",
    "parent_wave_generation",
    "parent_generation_authoritative",
)

DEVELOPMENT_CHECKPOINT_CONFIG_KEYS = (
    "BotWorld.Magmaw.TransferLaneTaskAuthority",
    "BotWorld.ValidationRoute.PrepullCheckpointEnable",
    "BotWorld.ValidationFixture.MagmawTransferLaneCheckpoint.Enable",
    "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.Enable",
    "BotWorld.ValidationFixture.NativePathCheckpoint.Enable",
    "BotWorld.ValidationFixture.ProfileCombatRangeCheckpoint.Enable",
)
DEVELOPMENT_CHECKPOINT_IDENTITY_PREFIXES = (
    "BotWorld.ValidationFixture.MagmawTransferLaneCheckpoint",
    "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint",
    "BotWorld.ValidationFixture.NativePathCheckpoint",
    "BotWorld.ValidationFixture.ProfileCombatRangeCheckpoint",
)
DEVELOPMENT_CHECKPOINT_NUMERIC_KEYS = (
    "BotWorld.ValidationFixture.ProfileCombatRangeCheckpoint.ActorGuid",
    "BotWorld.ValidationFixture.ProfileCombatRangeCheckpoint.RuntimeTargetGuid",
    "BotWorld.ValidationFixture.ProfileCombatRangeCheckpoint.TargetSpawnId",
    "BotWorld.ValidationFixture.ProfileCombatRangeCheckpoint.TargetEntry",
    "BotWorld.ValidationFixture.ProfileCombatRangeCheckpoint.TargetMapId",
)


def _trinity_config_nonzero_int(path: Path, key: str) -> bool:
    pattern = re.compile(
        rf'^\s*{re.escape(key)}\s*=\s*"?([+-]?\d+)"?\s*(?:#.*)?$'
    )
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return False
    for line in lines:
        match = pattern.match(line)
        if match:
            return int(match.group(1)) != 0
    return False


def development_run_argument_rejections(args: argparse.Namespace) -> list[str]:
    """Reject auxiliary evidence authorities from a development gameplay run."""

    if not args.development_run:
        return []
    rejections: list[str] = []
    incompatible = {
        "trace_transport_smoke": args.trace_transport_smoke,
        "fixture_expansion_replay": args.fixture_expansion_replay,
        "recurrence_admission": args.recurrence_admission is not None,
        "recurrence_admission_sha256": bool(args.recurrence_admission_sha256),
        "chainwielder_checkpoint_actor": (
            args.chainwielder_checkpoint_actor_guid is not None
        ),
        "magmaw_transfer_checkpoint_actor": (
            args.magmaw_transfer_checkpoint_actor_guid is not None
        ),
        "profile_combat_range_checkpoint_actor": (
            args.profile_combat_range_checkpoint_actor_guid is not None
        ),
        "profile_combat_range_checkpoint_target": (
            args.profile_combat_range_checkpoint_target_guid is not None
        ),
        "personal_threat_episode": any(
            getattr(args, f"personal_threat_episode_{field}", None) is not None
            for field in PERSONAL_THREAT_EPISODE_TARGET_FIELDS
        ),
    }
    rejections.extend(
        f"development_run_incompatible_{name}"
        for name, supplied in incompatible.items() if supplied
    )
    if args.scenario_id is None:
        rejections.append("development_run_scenario_id_required")
    if args.runtime_profile is None:
        rejections.append("development_run_runtime_profile_required")
    if args.pool_tag is None:
        rejections.append("development_run_pool_tag_required")
    return rejections


def development_run_canonical_rejections(
    args: argparse.Namespace, *, config: Path, worktree: Path,
    runtime_assets: dict[str, Any],
) -> list[str]:
    """Bind development execution to the tracked diagnostic profile and route."""

    if not args.development_run:
        return []
    rejections: list[str] = []
    partition = runtime_assets.get("route_partition")
    if not isinstance(partition, dict):
        return ["development_run_route_partition_missing"]
    if partition.get("passed") is not True:
        rejections.append("development_run_route_partition_not_verified")
    if partition.get("diagnostic_only") is not True:
        rejections.append("development_run_diagnostic_partition_required")
    if partition.get("terminal_kind") != "boss":
        rejections.append("development_run_terminal_boss_required")
    node_count = partition.get("node_count")
    terminal_index = partition.get("terminal_index")
    node_ids = partition.get("node_ids")
    if (
        not isinstance(node_count, int) or isinstance(node_count, bool)
        or node_count <= 0
        or terminal_index != node_count - 1
        or not isinstance(node_ids, list) or len(node_ids) != node_count
        or any(not isinstance(node, str) or not node for node in node_ids)
        or len(set(node_ids)) != node_count
        or runtime_assets.get("matching_route_rows") != node_count
    ):
        rejections.append("development_run_route_partition_identity_invalid")
    if not isinstance(partition.get("terminal_target_entry"), int) \
            or isinstance(partition.get("terminal_target_entry"), bool) \
            or partition.get("terminal_target_entry") <= 0:
        rejections.append("development_run_terminal_boss_identity_missing")
    if (
        runtime_assets.get("scenario_id") != args.scenario_id
        or runtime_assets.get("profile_name") != args.runtime_profile
        or runtime_assets.get("pool_tag_filter") != args.pool_tag
    ):
        rejections.append("development_run_canonical_identity_mismatch")
    route_sha256 = runtime_assets.get("route_sha256")
    if (
        not isinstance(route_sha256, str)
        or not SHA256_RE.fullmatch(route_sha256)
        or runtime_assets.get("reference_route_sha256") != route_sha256
    ):
        rejections.append("development_run_canonical_route_hash_mismatch")

    configured_profile = trinity_config_string(config, "BotWorld.ProfileManifest")
    expected_profile = runtime_assets.get("profile_manifest")
    configured_profile_path = (
        Path(configured_profile)
        if Path(configured_profile).is_absolute()
        else worktree / configured_profile
    ) if configured_profile else None
    if (
        configured_profile_path is None
        or not isinstance(expected_profile, str)
        or configured_profile_path.resolve() != Path(expected_profile).resolve()
    ):
        rejections.append("development_run_canonical_profile_manifest_mismatch")
    if trinity_config_string(config, "BotWorld.ValidationRoute.ManifestPath"):
        rejections.append("development_run_route_overlay_forbidden")
    if trinity_config_string(config, "BotWorld.ValidationRoute.ScenarioId") \
            or trinity_config_string(config, "BotWorld.ValidationRoute.NodeId"):
        rejections.append("development_run_route_checkpoint_identity_forbidden")
    configured_runtime_profile = trinity_config_string(
        config, "BotWorld.RuntimeProfile",
    )
    if configured_runtime_profile not in {"", args.runtime_profile}:
        rejections.append("development_run_configured_profile_mismatch")
    if trinity_config_bool(config, "BotWorld.ValidationRoute.Enable", False):
        rejections.append("development_run_configured_route_override_forbidden")
    for key in DEVELOPMENT_CHECKPOINT_CONFIG_KEYS:
        if trinity_config_bool(config, key, False):
            rejections.append(
                "development_run_checkpoint_authority_forbidden:" + key
            )
    for prefix in DEVELOPMENT_CHECKPOINT_IDENTITY_PREFIXES:
        for field in ("FixtureId", "CaseId", "SealSha256", "SourceCommit"):
            key = f"{prefix}.{field}"
            if trinity_config_string(config, key):
                rejections.append(
                    "development_run_checkpoint_identity_forbidden:" + key
                )
    for key in DEVELOPMENT_CHECKPOINT_NUMERIC_KEYS:
        if _trinity_config_nonzero_int(config, key):
            rejections.append(
                "development_run_checkpoint_identity_forbidden:" + key
            )
    return rejections


def _personal_threat_episode_target(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    values = {
        field: getattr(args, f"personal_threat_episode_{field}", None)
        for field in PERSONAL_THREAT_EPISODE_TARGET_FIELDS
    }
    supplied = [field for field, value in values.items() if value is not None]
    if not supplied:
        return None
    if len(supplied) != len(PERSONAL_THREAT_EPISODE_TARGET_FIELDS):
        raise ValueError("incomplete")
    if any(
        not isinstance(values[field], int)
        or isinstance(values[field], bool)
        or values[field] <= 0
        for field in (
            "actor_guid", "route_generation", "parent_wave_generation",
        )
    ):
        raise ValueError("integer_invalid")
    if any(
        not isinstance(values[field], str)
        or not values[field]
        or values[field] != values[field].strip()
        for field in ("scope_key", "route_node_id")
    ):
        raise ValueError("identity_invalid")
    if not isinstance(values["parent_generation_authoritative"], bool):
        raise ValueError("parent_authority_invalid")
    return values


def recurrence_profile_authority(
    *, fixture_expansion_replay: bool, configured_profile_manifest: str,
    runtime_profile: str,
) -> tuple[Path | None, str | None]:
    """Return profile authority only for a generated fixture replay overlay."""

    if not fixture_expansion_replay:
        return None, None
    return (
        Path(configured_profile_manifest).resolve()
        if configured_profile_manifest else None,
        runtime_profile,
    )


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
    runtime_asset_closure: dict[str, Any]
    personal_threat_episode_target: dict[str, Any] | None = None
    checkpoint_target_guid: int | None = None
    build_worktree: Path | None = None
    build_identity_before: dict[str, Any] | None = None


def controller_route_hold_runtime_manifest_identity(
    *, config: Path, recurrence_admission: dict[str, Any], scenario_id: str,
    runtime_profile: str,
) -> dict[str, str]:
    """Project the exact verified runtime route identity used by native start."""

    if recurrence_admission.get("valid") is not True:
        raise ValueError("controller_route_hold_verified_admission_missing")
    bindings = recurrence_admission.get("bindings")
    binding = bindings.get("route_manifest") if isinstance(bindings, dict) else None
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
    profile_binding = bindings.get("profile_manifest") \
        if isinstance(bindings, dict) else None
    profile_path_text = profile_binding.get("path") \
        if isinstance(profile_binding, dict) else None
    profile_sha256 = profile_binding.get("sha256") \
        if isinstance(profile_binding, dict) else None
    configured_profile_path = trinity_config_string(config, "BotWorld.ProfileManifest")
    if not isinstance(profile_path_text, str) or not profile_path_text:
        raise ValueError("controller_route_hold_profile_manifest_binding_missing")
    if not isinstance(profile_sha256, str) or not SHA256_RE.fullmatch(profile_sha256):
        raise ValueError("controller_route_hold_profile_manifest_hash_invalid")
    if not configured_profile_path:
        raise ValueError("controller_route_hold_profile_manifest_config_missing")
    profile_path = Path(configured_profile_path).resolve()
    if profile_path != Path(profile_path_text).resolve():
        raise ValueError("controller_route_hold_profile_manifest_path_mismatch")
    try:
        profile_bytes = profile_path.read_bytes()
    except OSError as error:
        raise ValueError("controller_route_hold_profile_manifest_missing") from error
    if hashlib.sha256(profile_bytes).hexdigest() != profile_sha256:
        raise ValueError("controller_route_hold_profile_manifest_hash_mismatch")
    try:
        profile_manifest = json.loads(profile_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("controller_route_hold_profile_manifest_invalid") from error
    if not isinstance(profile_manifest, dict):
        raise ValueError("controller_route_hold_profile_manifest_invalid")
    profile_identity = recurrence_admission.get("runtime_profile_overlay")
    if not isinstance(profile_identity, dict):
        raise ValueError("controller_route_hold_profile_overlay_binding_missing")
    if profile_identity.get("runtime_profile_id") != runtime_profile \
            or profile_identity.get("runtime_validation_route_manifest_path") != str(
                configured_path
            ) \
            or profile_identity.get("runtime_profile_manifest_sha256") != profile_sha256 \
            or profile_identity.get("runtime_route_manifest_sha256") != bound_sha256:
        raise ValueError("controller_route_hold_verified_profile_overlay_mismatch")
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
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("controller_route_hold_runtime_manifest_row_invalid")
    return {
        "route_manifest_path": str(configured_path),
        "route_manifest_sha256": bound_sha256,
        "profile_manifest_path": str(profile_path),
        "profile_manifest_sha256": profile_sha256,
        "initial_route_node_id": initial_node_id,
        "checkpoint_target_node_id": checkpoint_target_node_id,
        "route_partition": {
            "node_count": len(rows),
            "terminal_index": len(rows) - 1,
            "node_ids": [row.get("route_node_id") for row in rows],
            "terminal_kind": rows[-1].get("kind"),
            "terminal_target_entry": rows[-1].get("source_entry"),
        },
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
    parser.add_argument("--magmaw-transfer-checkpoint-actor-guid", type=int)
    parser.add_argument("--profile-combat-range-checkpoint-actor-guid", type=int)
    parser.add_argument("--profile-combat-range-checkpoint-target-guid", type=int)
    parser.add_argument("--personal-threat-episode-actor-guid", type=int)
    parser.add_argument("--personal-threat-episode-scope-key")
    parser.add_argument("--personal-threat-episode-route-node-id")
    parser.add_argument("--personal-threat-episode-route-generation", type=int)
    parser.add_argument("--personal-threat-episode-parent-wave-generation", type=int)
    parser.add_argument(
        "--personal-threat-episode-parent-generation-authoritative",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument(
        "--fixture-expansion-replay",
        action="store_true",
        help=(
            "admit one evidence-only fixture expansion while the ordinary "
            "gameplay canary gate remains closed"
        ),
    )
    parser.add_argument(
        "--development-run",
        action="store_true",
        help=(
            "run one canonical diagnostic boss partition without recurrence or "
            "checkpoint authorities; reports are not training or qualification evidence"
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
    add_runtime_asset_closure_arguments(parser)
    parser.add_argument("--worktree", type=Path, default=root)
    parser.add_argument(
        "--build-worktree", type=Path, default=None,
        help=(
            "retained checkout that owns the receipt, CMake cache, and binary; "
            "defaults to --worktree"
        ),
    )
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
    development_argument_rejections = development_run_argument_rejections(args)
    if development_argument_rejections:
        raise SystemExit(
            "capture preflight rejected: "
            + ",".join(development_argument_rejections)
        )
    try:
        personal_threat_episode_target = _personal_threat_episode_target(args)
    except ValueError as error:
        raise SystemExit(
            f"capture preflight rejected: personal_threat_episode_target:{error}"
        ) from error
    checkpoint_actors = [
        actor for actor in (
            args.chainwielder_checkpoint_actor_guid,
            args.magmaw_transfer_checkpoint_actor_guid,
            args.profile_combat_range_checkpoint_actor_guid,
        ) if actor is not None
    ]
    if len(checkpoint_actors) > 1:
        raise SystemExit(
            "capture preflight rejected: multiple_checkpoint_actor_dialects"
        )
    checkpoint_actor_guid = checkpoint_actors[0] if checkpoint_actors else None
    if (
        args.profile_combat_range_checkpoint_target_guid is not None
        and args.profile_combat_range_checkpoint_actor_guid is None
    ):
        raise SystemExit(
            "capture preflight rejected: profile_combat_range_target_without_actor"
        )

    binary = args.binary.resolve()
    config = args.config.resolve()
    output = args.output.resolve()
    worktree = args.worktree.resolve()
    build_worktree = (
        args.build_worktree.resolve()
        if args.build_worktree is not None else worktree
    )
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
    runtime_asset_closure = enforce_runtime_asset_closure_from_args(
        args, worldserver_config=config,
    )
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
    checkpoint_target_guid: int | None = None
    recurrence_required = scenario_id == "blackwing_descent_10n_magmaw_diagnostic"
    if args.fixture_expansion_replay and not recurrence_required:
        raise SystemExit(
            "capture preflight rejected: fixture_expansion_route_mismatch"
        )
    if recurrence_required and not args.development_run and (
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
            configured_profile_manifest = trinity_config_string(
                config, "BotWorld.ProfileManifest",
            )
            profile_manifest, expected_runtime_profile_id = (
                recurrence_profile_authority(
                    fixture_expansion_replay=args.fixture_expansion_replay,
                    configured_profile_manifest=configured_profile_manifest,
                    runtime_profile=profile_name,
                )
            )
            recurrence_admission = verify_recurrence_admission(
                admission_path=args.recurrence_admission,
                expected_sha256=args.recurrence_admission_sha256,
                worktree=worktree,
                binary=binary,
                build_receipt=args.build_receipt.resolve(),
                runtime_config=config,
                profile_manifest=profile_manifest,
                expected_runtime_profile_id=expected_runtime_profile_id,
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
        checkpoint_fixture = (
            recurrence_admission.get("checkpoint_fixture_id")
            if isinstance(recurrence_admission, dict) else None
        )
        if checkpoint_fixture == PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID:
            admitted_actor = recurrence_admission.get("checkpoint_actor_guid")
            checkpoint_target_guid = recurrence_admission.get(
                "checkpoint_target_guid"
            )
            if (
                args.profile_combat_range_checkpoint_actor_guid
                != admitted_actor
                or admitted_actor != PROFILE_COMBAT_RANGE_ACTOR_GUID
                or args.profile_combat_range_checkpoint_target_guid
                != checkpoint_target_guid
                or checkpoint_target_guid != PROFILE_COMBAT_RANGE_TARGET_GUID
            ):
                raise ValueError(
                    "profile_combat_range_checkpoint_identity_mismatch"
                )
        elif (
            args.profile_combat_range_checkpoint_actor_guid is not None
            or args.profile_combat_range_checkpoint_target_guid is not None
        ):
            raise ValueError("profile_combat_range_checkpoint_identity_unexpected")
        if checkpoint_fixture is not None:
            checkpoint_dialect = checkpoint_controller_dialect(
                recurrence_admission,
                checkpoint_actor_guid,
            )
            checkpoint_arm_command = (
                checkpoint_dialect.get("arm_command")
                if isinstance(checkpoint_dialect, dict) else None
            )
        else:
            checkpoint_arm_command = chainwielder_checkpoint_arm_command(
                recurrence_admission,
                checkpoint_actor_guid,
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
    development_canonical_rejections = development_run_canonical_rejections(
        args, config=config, worktree=worktree, runtime_assets=runtime_assets,
    )
    if development_canonical_rejections:
        raise SystemExit(
            "capture preflight rejected: "
            + ",".join(development_canonical_rejections)
        )
    route_manifest = runtime_assets.get("route_manifest")
    controller_route_hold_scheduler: ControllerRouteHoldScheduler | None = None
    if args.fixture_expansion_replay:
        try:
            if args.recurrence_admission is None:
                raise ValueError("controller_route_hold_verified_admission_missing")
            runtime_route_identity = controller_route_hold_runtime_manifest_identity(
                config=config,
                recurrence_admission=recurrence_admission,
                scenario_id=scenario_id,
                runtime_profile=profile_name,
            )
            runtime_assets["runtime_route_partition"] = runtime_route_identity["route_partition"]
            checkpoint_dialect = checkpoint_controller_dialect(
                recurrence_admission,
                checkpoint_actor_guid,
            )
            controller_hold_identity = None
            if checkpoint_dialect is not None:
                controller_hold_identity = controller_route_hold_launch_identity(
                    recurrence_admission=recurrence_admission,
                    required_purpose=FIXTURE_EXPANSION_PURPOSE,
                    actor_guid=checkpoint_actor_guid,
                    scenario_id=scenario_id,
                    runtime_profile=profile_name,
                    pool_tag=str(runtime_assets.get("pool_tag_filter") or ""),
                    route_manifest_sha256=runtime_route_identity[
                        "route_manifest_sha256"
                    ],
                    route_node_id=runtime_route_identity["initial_route_node_id"],
                    expected_checkpoint_fixture_id=checkpoint_dialect["fixture_id"],
                )
        except ValueError as error:
            raise SystemExit(
                f"capture preflight rejected: controller_route_hold:{error}"
            ) from error
        if checkpoint_dialect is not None:
            if controller_hold_identity is None:
                raise SystemExit(
                    "capture preflight rejected: controller_route_hold_identity_missing"
                )
            scheduler_kwargs = dict(checkpoint_dialect["scheduler_kwargs"])
            if (
                personal_threat_episode_target is not None
                and checkpoint_dialect.get("fixture_id")
                    == CHAINWIELDER_CHECKPOINT_FIXTURE_ID
            ):
                scheduler_kwargs["runtime_scope_required"] = True
            controller_route_hold_scheduler = ControllerRouteHoldScheduler(
                controller_hold_identity,
                **scheduler_kwargs,
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
            args.build_receipt.resolve(), build_worktree,
        )
    except RuntimeError as error:
        raise SystemExit(f"build receipt rejected: {error}") from error
    build_provenance = validate_build_receipt(
        args.build_receipt.resolve(),
        build_policy_path,
        worktree, binary, config,
        args.build_attestation.resolve() if args.build_attestation is not None else None,
        build_control_authority=(
            Path(
                recurrence_admission["bindings"]["build_control_authority"][
                    "path"
                ]
            ).resolve()
            if recurrence_admission is not None
            and "build_control_authority" in recurrence_admission.get(
                "bindings", {}
            ) else None
        ),
        build_control_authority_sha256=(
            recurrence_admission["bindings"]["build_control_authority"][
                "sha256"
            ]
            if recurrence_admission is not None
            and "build_control_authority" in recurrence_admission.get(
                "bindings", {}
            ) else None
        ),
        build_worktree=build_worktree,
    )
    if not build_provenance.get("valid"):
        raise SystemExit("build receipt rejected: " + ",".join(build_provenance.get("rejections", [])))
    if recurrence_admission is not None and "build_control_authority" in (
        recurrence_admission.get("bindings") or {}
    ) and (
        recurrence_admission.get("build_control_compatibility")
        != {
            key: build_provenance.get(key)
            for key in recurrence_admission.get(
                "build_control_compatibility", {}
            )
        }
    ):
        raise SystemExit(
            "build receipt rejected: admission_build_control_compatibility_mismatch"
        )

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
        checkpoint_target_guid=checkpoint_target_guid,
        preflight=preflight,
        identity_before=identity_before,
        runtime_assets=runtime_assets,
        controller_route_hold_scheduler=controller_route_hold_scheduler,
        drudge_observed=drudge_observed,
        drudge_required=drudge_required,
        drudge_navmesh_preflight=drudge_navmesh_preflight,
        drudge_frozen_anchors=drudge_frozen_anchors,
        build_provenance=build_provenance,
        runtime_asset_closure=runtime_asset_closure,
        personal_threat_episode_target=personal_threat_episode_target,
        build_worktree=build_worktree,
        build_identity_before=build_provenance.get("build_worktree_identity"),
    )
