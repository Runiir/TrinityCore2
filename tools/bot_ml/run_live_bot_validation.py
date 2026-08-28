from __future__ import annotations

import argparse
import base64
import contextlib
import functools
import hashlib
import html
import json
import math
import os
import select
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse
import re

try:
    from .analyze_combat_log import analyze_combat_log
    from .audit_role_efficiency import build_audit
    from .batch_evidence_lifecycle import append_heartbeat, capture_batch, finalize_heartbeat, publish_batch, validate_capture
    from .build_validation_provisioning import DEFAULT_BWD_DIAGNOSTIC_SHARD_FIXTURE, VALIDATION_FULL_STAT_SEED, VALIDATION_GHOST_AURA_ID, VALIDATION_GHOST_CHARACTER_FLAG, VALIDATION_RESURRECT_AT_LOGIN_FLAG, apply_gear_profiles, build_account_insert_sql, build_character_insert_sql, load_config_with_bwd_diagnostic_shards, load_gear_profiles
    from .calibration_consumable_provisioning import (
        prepare_calibration_consumables as _prepare_calibration_consumables,
    )
    from .common import write_json
    from .extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url
    from .generate_bot_admission_identities import source_content_sha256 as admission_identity_source_sha256
    from .live_validation_session import apply_acceptance_evaluation, build_evidence_envelope, build_live_validation_standard_marker, build_session, canonical_sha256, ensure_healthy_matching_session, git_dirty_state_sha256, git_head, inspect_session, live_validation_lock, sha256_file, sha256_text
    from .phase8_calibration_adapter import Phase8CalibrationNormalizationError, canonical_gear_manifest, canonical_gear_profile_id, evaluate_runtime_calibration, expected_gear_manifest
    from .phase8_evidence_identity import validate_manifest as validate_phase8_evidence_manifest
    from .phase9_evidence_identity import validate_manifest as validate_phase9_evidence_manifest
    from .phase8_reference_conditions import load_reference_request_binding
except ImportError:
    from analyze_combat_log import analyze_combat_log
    from audit_role_efficiency import build_audit
    from batch_evidence_lifecycle import append_heartbeat, capture_batch, finalize_heartbeat, publish_batch, validate_capture
    from build_validation_provisioning import DEFAULT_BWD_DIAGNOSTIC_SHARD_FIXTURE, VALIDATION_FULL_STAT_SEED, VALIDATION_GHOST_AURA_ID, VALIDATION_GHOST_CHARACTER_FLAG, VALIDATION_RESURRECT_AT_LOGIN_FLAG, apply_gear_profiles, build_account_insert_sql, build_character_insert_sql, load_config_with_bwd_diagnostic_shards, load_gear_profiles
    from calibration_consumable_provisioning import (
        prepare_calibration_consumables as _prepare_calibration_consumables,
    )
    from common import write_json
    from extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url
    from generate_bot_admission_identities import source_content_sha256 as admission_identity_source_sha256
    from live_validation_session import apply_acceptance_evaluation, build_evidence_envelope, build_live_validation_standard_marker, build_session, canonical_sha256, ensure_healthy_matching_session, git_dirty_state_sha256, git_head, inspect_session, live_validation_lock, sha256_file, sha256_text
    from phase8_calibration_adapter import Phase8CalibrationNormalizationError, canonical_gear_manifest, canonical_gear_profile_id, evaluate_runtime_calibration, expected_gear_manifest
    from phase8_evidence_identity import validate_manifest as validate_phase8_evidence_manifest
    from phase9_evidence_identity import validate_manifest as validate_phase9_evidence_manifest
    from phase8_reference_conditions import load_reference_request_binding


DEFAULT_LIVE_VALIDATION_TIMEOUT_SEC = 90
DEFAULT_BOSS_ROUTE_TIMEOUT_SEC = 900
DEFAULT_COMPLETION_HEARTBEAT_SEC = 30
DEFAULT_NO_PROGRESS_WINDOW_SEC = 180
DEFAULT_MAX_REPEATED_DECISIONS = 20
DEFAULT_MAX_DEATH_LOOPS = 3
DEFAULT_MAX_WORLDSERVER_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_WORLDSERVER_DRAIN_BYTES_PER_WAKE = 64 * 1024
# A completion-watchdog run repeats the same four command families on every
# heartbeat.  Keep the single output budget hard, but give cleanup its own
# section so a full combat-log export cannot be evicted by old heartbeats.
WATCHDOG_PREFIX_OUTPUT_BYTES = 8 * 1024 * 1024
WATCHDOG_CLEANUP_OUTPUT_BYTES = 16 * 1024 * 1024
PRE_MARKER_PROMPT_GRACE_SEC = 1.0
WORLDSERVER_OUTPUT_TRUNCATED_MARKER = "\n[worldserver_output_truncated]\n"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMBAT_CALIBRATION_REFERENCE = REPO_ROOT / "dataset/combat_calibration/wowsims_cata_p4.json"
CALIBRATION_DPS_MODES = frozenset({"single_target_300", "aoe_300"})
DEFAULT_REFERENCE_HYDRATE_COMMAND = (
    "pixi run python -m tools.raid_program.wowsims_reference_workspace hydrate"
)
SESSION_CONTROLLER_PRELAUNCH_LAYOUTS = (
    frozenset({"runner.log", "physical_try_started.json"}),
    frozenset({"phase9_runner.log", "phase9_physical_try_started.json"}),
)


DEFAULT_STAGES = [
    "movement_smoke",
    "kill_quest",
    "collect_quest",
    "quest_hub_batching",
    "trainer_visit",
    "vendor_repair",
    "profession_recipe_acquisition",
    "material_farming",
    "smart_loot",
    "normal_dungeon_trash",
    "dungeon_boss",
    "full_stonecore_clear",
    "raid_trash",
    "raid_boss",
    "full_blackwing_descent_clear",
]

class BoundedOutputParts(list[str]):
    def __init__(self, max_bytes: int = DEFAULT_MAX_WORLDSERVER_OUTPUT_BYTES):
        super().__init__()
        self.max_bytes = max_bytes
        self.written_bytes = 0
        self.truncated = False

    def append(self, value: str) -> None:
        if self.truncated:
            return
        encoded = value.encode("utf-8")
        remaining = self.max_bytes - self.written_bytes
        if len(encoded) <= remaining:
            super().append(value)
            self.written_bytes += len(encoded)
            return
        marker = WORLDSERVER_OUTPUT_TRUNCATED_MARKER.encode("utf-8")
        prefix = encoded[: max(0, remaining - len(marker))].decode("utf-8", errors="ignore")
        super().append(prefix + WORLDSERVER_OUTPUT_TRUNCATED_MARKER)
        self.written_bytes = self.max_bytes
        self.truncated = True

    def extend(self, values: tuple[str, ...] | list[str]) -> None:
        for value in values:
            self.append(value)


class WatchdogOutputBuffer:
    """Bound watchdog output without discarding its terminal protocol.

    Status, diagnosis, trace, and summary are repeated snapshots.  Keeping
    every copy made a long route fill the global buffer before the cleanup
    combat-log command ran.  The watchdog only needs the newest snapshot of
    each repeated command for its current report; compact heartbeat reports
    already provide the historical progress stream.  Startup/unsolicited
    output and cleanup output use separate bounded sections, so cleanup is
    still retained after heartbeat compaction or a failed run.
    """

    def __init__(
        self,
        *,
        max_bytes: int = DEFAULT_MAX_WORLDSERVER_OUTPUT_BYTES,
        heartbeat_commands: tuple[str, ...] | list[str] = (),
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.max_bytes = max_bytes
        prefix_bytes = min(WATCHDOG_PREFIX_OUTPUT_BYTES, max(1, max_bytes // 4))
        cleanup_bytes = min(
            WATCHDOG_CLEANUP_OUTPUT_BYTES,
            max(1, max_bytes // 4),
        )
        if prefix_bytes + cleanup_bytes >= max_bytes:
            cleanup_bytes = max(0, max_bytes - prefix_bytes - 1)
        heartbeat_bytes = max(0, max_bytes - prefix_bytes - cleanup_bytes)
        keys = tuple(dict.fromkeys(str(command) for command in heartbeat_commands))
        self._heartbeat_section_bytes = (
            heartbeat_bytes // max(1, len(keys)) if heartbeat_bytes else 0
        )
        self._prefix = BoundedOutputParts(max_bytes=prefix_bytes)
        self._cleanup = BoundedOutputParts(max_bytes=cleanup_bytes)
        self._heartbeat: dict[str, BoundedOutputParts] = {}
        self._known_heartbeat_commands = set(keys)
        self._compacted = False

    def append(self, value: str) -> None:
        """Retain startup or unsolicited output in the prefix section."""
        self._prefix.append(value)

    def extend(self, values: tuple[str, ...] | list[str]) -> None:
        for value in values:
            self.append(value)

    def append_heartbeat(self, command: str, value: str) -> None:
        """Replace the prior response for one repeated heartbeat command."""
        key = str(command)
        if key in self._heartbeat:
            self._compacted = True
        # A new key is allowed for custom scripts, but never gets an
        # unbounded allocation.  Known keys share the heartbeat budget;
        # unknown keys use the smallest known section budget.
        section_bytes = self._heartbeat_section_bytes
        if key not in self._known_heartbeat_commands and not section_bytes:
            section_bytes = 1
        section = BoundedOutputParts(max_bytes=section_bytes)
        section.append(value)
        self._heartbeat[key] = section

    def append_cleanup(self, value: str) -> None:
        """Retain final export/stop/shutdown output independently."""
        self._cleanup.append(value)

    def render(self) -> str:
        return "".join(
            [
                *self._prefix,
                *(value for part in self._heartbeat.values() for value in part),
                *self._cleanup,
            ]
        )

    @property
    def compacted(self) -> bool:
        return self._compacted

    @property
    def truncated(self) -> bool:
        return self._prefix.truncated or any(
            part.truncated for part in self._heartbeat.values()
        ) or self._cleanup.truncated

    @property
    def written_bytes(self) -> int:
        return len(self.render().encode("utf-8"))


CommandTransport = Callable[[str, int], tuple[str, int, bool]]


def session_output_dir_available(path: Path) -> bool:
    """Allow only the controller's immutable prelaunch files in a new run dir.

    The outer campaign controller reserves a physical try and opens its bounded
    log before launching this process.  Those files are not child output and
    are never overwritten here.  Any result receipt or previous child artifact
    still makes the directory unavailable, preserving the no-overwrite gate.
    """
    if not path.exists():
        return True
    children = list(path.iterdir())
    if any(not child.is_file() or child.is_symlink() for child in children):
        return False
    if not children:
        return True
    names = {child.name for child in children}
    return names in SESSION_CONTROLLER_PRELAUNCH_LAYOUTS


def calibration_reference_hydrate_command() -> str:
    """Return the canonical read-only workloop command for reference hydration."""
    try:
        from tools.raid_program import raid_workloop

        control_plane = raid_workloop.wowsims_status(REPO_ROOT)
        work_unit = control_plane.get("required_hydration_work_unit")
        commands = work_unit.get("commands") if isinstance(work_unit, Mapping) else {}
        command = commands.get("hydrate_and_verify") if isinstance(commands, Mapping) else ""
        if isinstance(command, str) and command.strip():
            return command.strip()
    except Exception:
        # The binding check remains authoritative.  If the broader control
        # plane cannot be read, retain the deterministic workspace command.
        pass
    return DEFAULT_REFERENCE_HYDRATE_COMMAND


def preflight_calibration_reference_binding(
    *,
    calibration_only: bool,
    calibration_mode: str,
    target_spec: str,
) -> dict[str, Any]:
    """Require a verified generated reference before DPS calibration startup.

    Tank and healer calibration modes intentionally remain independent of the
    DPS WoWSims request catalog.  DPS modes must prove the exact target's
    generated request/result artifacts before any session, config, or fixture
    preparation can mutate live state.
    """
    required = calibration_only and calibration_mode in CALIBRATION_DPS_MODES
    if not required:
        return {
            "required": False,
            "valid": True,
            "calibration_mode": calibration_mode,
            "target_spec": target_spec,
        }

    binding = load_reference_request_binding(target_spec)
    if isinstance(binding, Mapping) and binding.get("valid") is True:
        return {
            "required": True,
            "valid": True,
            "calibration_mode": calibration_mode,
            "target_spec": target_spec,
        }

    reasons = []
    if isinstance(binding, Mapping):
        reasons = sorted(
            {
                str(reason)
                for reason in (binding.get("reasons") or [])
                if str(reason)
            }
        )
    hydrate_command = calibration_reference_hydrate_command()
    failure = {
        "schema": "bot_calibration_reference_preflight_v1",
        "valid": False,
        "calibration_mode": calibration_mode,
        "target_spec": target_spec,
        "reasons": reasons or ["reference_request_binding_invalid"],
        "hydrate_command": hydrate_command,
    }
    raise SystemExit(
        "calibration reference preflight failed: "
        + json.dumps(failure, sort_keys=True)
    )


def preflight_validation_scenario_stage(
    scenario_dir: Path,
    scenario_id: str,
    *,
    profile_name: str = "",
    pool_tag: str | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Reject stale repository-backed route output before live preparation.

    ``dataset/validation_scenarios`` is a DVC stage output.  A copied output
    can still contain a syntactically valid route after the source scenario
    config changes, so route/profile validation alone is not sufficient.  The
    DVC stage status is checked without reproducing it.  Custom scenario
    directories are deliberately exempt because tests and offline fixtures
    own their bytes.
    """
    canonical_dir = (REPO_ROOT / "dataset/validation_scenarios").resolve()
    selected_dir = (
        (REPO_ROOT / scenario_dir) if not scenario_dir.is_absolute() else scenario_dir
    ).resolve()
    result: dict[str, Any] = {
        "schema": "bot_live_validation_scenario_stage_preflight_v1",
        "required": False,
        "valid": True,
        "scenario_id": scenario_id,
        "profile_name": profile_name or scenario_id,
        "scenario_dir": str(selected_dir),
        "canonical_scenario_dir": str(canonical_dir),
        "pool_tag": pool_tag,
        "dvc_stage_current": False,
    }
    if not enabled:
        result["reason"] = "not_a_live_route_preparation"
        return result
    if selected_dir != canonical_dir:
        result["reason"] = "custom_scenario_dir"
        return result
    if not scenario_id:
        result["reason"] = "scenario_id_not_selected"
        return result

    result["required"] = True
    try:
        # Keep the stage check read-only.  The route/profile contract is
        # validated later against the selected scenario directory; this
        # preflight only answers whether the repository-backed DVC output is
        # current.  It must never repair the output with ``dvc repro``.
        dvc_environment = os.environ.copy()
        dvc_environment.pop("PIXI_PROJECT_MANIFEST", None)
        dvc_result = subprocess.run(
            ["pixi", "run", "dvc", "status", "validation_scenarios", "--json"],
            cwd=REPO_ROOT,
            env=dvc_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
            check=False,
        )
        dvc_status = dvc_result.stdout.strip()
        try:
            dvc_payload = json.loads(dvc_status)
        except (TypeError, ValueError):
            dvc_payload = None
        dvc_clean = (
            dvc_result.returncode == 0
            and isinstance(dvc_payload, dict)
            and not dvc_payload
        )
        assets = {
            "dvc_stage": "validation_scenarios",
            "dvc_status": dvc_status,
            "dvc_returncode": dvc_result.returncode,
            "passed": dvc_clean,
            "reasons": [] if dvc_clean else ["runtime_route_dvc_lineage_dirty"],
        }
    except Exception as exc:
        assets = {
            "passed": False,
            "reasons": [f"validator_error:{type(exc).__name__}"],
        }
    result["assets"] = assets
    result["valid"] = bool(assets.get("passed"))
    if not result["valid"]:
        reasons = sorted(
            {str(reason) for reason in (assets.get("reasons") or []) if str(reason)}
        ) or ["repository_validation_scenario_stage_invalid"]
        result["reasons"] = reasons
        raise SystemExit(
            "validation scenario stage preflight failed: "
            + json.dumps(result, sort_keys=True)
        )
    result["dvc_stage_current"] = True
    return result


@dataclass(frozen=True)
class ValidationAttempt:
    cohort_id: str
    attempt_index: int
    profile: str
    output_dir: Path
    timeout_sec: int | None
    observe_sec: int

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", self.cohort_id):
            raise ValueError("invalid cohort_id")
        if self.attempt_index < 1:
            raise ValueError("attempt_index must be positive")
        if (self.timeout_sec is not None and self.timeout_sec < 1) or self.observe_sec < 0:
            raise ValueError("attempt timing must be non-negative")


@dataclass
class SerialValidationScheduler:
    attempts: Sequence[ValidationAttempt]
    pending: deque[ValidationAttempt] = field(init=False)
    active: ValidationAttempt | None = field(default=None, init=False)
    completed: list[ValidationAttempt] = field(default_factory=list, init=False)
    events: list[dict[str, Any]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.pending = deque(self.attempts)
        identities = {(attempt.cohort_id, attempt.attempt_index) for attempt in self.attempts}
        if len(identities) != len(self.attempts):
            raise ValueError("duplicate cohort attempt identity")

    def admit_next(self) -> ValidationAttempt | None:
        if self.active is not None:
            raise RuntimeError("serial scheduler already owns an active attempt")
        if not self.pending:
            return None
        self.active = self.pending.popleft()
        self.events.append(
            {
                "action": "admit",
                "cohort_id": self.active.cohort_id,
                "attempt_index": self.active.attempt_index,
            }
        )
        return self.active

    def close_active(self) -> None:
        if self.active is None:
            raise RuntimeError("serial scheduler has no active attempt")
        self.events.append(
            {
                "action": "close",
                "cohort_id": self.active.cohort_id,
                "attempt_index": self.active.attempt_index,
            }
        )
        self.completed.append(self.active)
        self.active = None


@dataclass
class CohortCommandExecutor:
    execute_command: CommandTransport
    cohort_id: str
    default_timeout_sec: int = 180
    commands: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", self.cohort_id):
            raise ValueError("invalid cohort_id")

    @property
    def status_command(self) -> str:
        return f".botauto status {self.cohort_id}"

    def run(self, command: str, timeout_sec: int | None = None) -> tuple[str, int, bool]:
        tokens = command.split()
        addressed_actions = {
            "create",
            "prepare",
            "start",
            "stop",
            "status",
            "diagnose",
            "trace",
            "combatlog",
            "calibrate",
        }
        if (
            len(tokens) >= 2
            and tokens[0] == ".botauto"
            and tokens[1] in addressed_actions
            and (len(tokens) < 3 or tokens[2] != self.cohort_id)
        ):
            raise RuntimeError("global or cross-cohort botauto command is forbidden")
        self.commands.append(command)
        output, returncode, timed_out = self.execute_command(
            command,
            max(1, int(timeout_sec or self.default_timeout_sec)),
        )
        for payload in parse_json_objects(output):
            payload_cohort = payload.get("cohort_id")
            action = str(payload.get("action") or "")
            if action.startswith("botauto_") and payload_cohort not in {None, self.cohort_id}:
                raise RuntimeError("cohort command returned cross-cohort payload")
        return output, returncode, timed_out

    def create(self) -> tuple[str, int, bool]:
        return self.run(f".botauto create {self.cohort_id}")

    def prepare(
        self,
        profile: str,
        pool_tag: str = "",
        class_specs: Sequence[str] = (),
    ) -> tuple[str, int, bool]:
        exact_party = ""
        if class_specs:
            exact_party = " " + " ".join((pool_tag, *class_specs))
        return self.run(f".botauto prepare {self.cohort_id} {profile}{exact_party}")

    def start(self, profile: str = "") -> tuple[str, int, bool]:
        suffix = f" {profile}" if profile else ""
        return self.run(f".botauto start {self.cohort_id}{suffix}")

    def stop(self) -> tuple[str, int, bool]:
        return self.run(f".botauto stop {self.cohort_id}")

    def diagnose(self, selector: str) -> tuple[str, int, bool]:
        return self.run(f".botauto diagnose {self.cohort_id} {selector}")

    def trace(self, selector: str, limit: int) -> tuple[str, int, bool]:
        return self.run(f".botauto trace {self.cohort_id} {selector} {max(1, limit)}")

    def combat_log(self) -> tuple[str, int, bool]:
        return self.run(f".botauto combatlog {self.cohort_id}")

    def calibration(
        self,
        operation: str,
        *,
        mode: str = "",
        target_spec: str = "",
        seed: int = 1,
    ) -> tuple[str, int, bool]:
        if operation not in {"start", "stop", "status"}:
            raise ValueError("invalid calibration operation")
        suffix = ""
        if operation == "start":
            if not mode or not target_spec:
                raise ValueError("calibration start requires mode and target_spec")
            suffix = f" {mode} {target_spec} {max(1, seed)}"
        return self.run(f".botauto calibrate {self.cohort_id} {operation}{suffix}")


@dataclass
class CohortAttemptWatchdog:
    executor: CohortCommandExecutor
    attempt: ValidationAttempt

    def script(
        self,
        selector: str,
        trace_limit: int,
        combat_calibration: bool = False,
        *,
        calibration_mode: str = "single_target_300",
        calibration_target_spec: str = "protection_paladin",
        calibration_seed: int = 1,
        calibration_only: bool = False,
    ) -> str:
        return command_script(
            selector=selector,
            trace_limit=trace_limit,
            start=False,
            stop=False,
            exit_server=False,
            combat_calibration=combat_calibration,
            cohort_id=self.attempt.cohort_id,
            calibration_mode=calibration_mode,
            calibration_target_spec=calibration_target_spec,
            calibration_seed=calibration_seed,
            calibration_only=calibration_only,
            trace_delta=True,
        )


@dataclass
class ImmutableCaptureWriter:
    repository: Path

    def capture(
        self,
        attempt: ValidationAttempt,
        report: Mapping[str, Any],
        output: str,
        exact_manifests: Mapping[str, Any],
        *,
        returncode: int,
        timed_out: bool,
    ) -> dict[str, Any]:
        batch_root = attempt.output_dir / "batch"
        payloads = parse_json_objects(output)
        raw_rows = [
            {
                "batch_id": f"{attempt.cohort_id}-{attempt.attempt_index}",
                "cohort_id": attempt.cohort_id,
                "attempt_index": attempt.attempt_index,
                "sequence": index,
                "payload": payload,
            }
            for index, payload in enumerate(payloads)
        ]
        compact_rows = [
            {
                "batch_id": f"{attempt.cohort_id}-{attempt.attempt_index}",
                "cohort_id": attempt.cohort_id,
                "attempt_index": attempt.attempt_index,
                "all_passed": bool(report.get("all_passed")),
                "acceptable_final_evidence": bool(report.get("acceptable_final_evidence")),
                "failure_reason": str(report.get("failure_reason") or ""),
                "completion_reason": str(report.get("completion_reason") or ""),
            }
        ]
        context = report.get("validation_context")
        context = context if isinstance(context, Mapping) else {}
        if report.get("calibration_only") is True:
            evidence_kind = "dps_calibration"
        elif str(context.get("scenario_id") or "") == "stonecore_5h":
            evidence_kind = "stonecore_5h"
        else:
            evidence_kind = "live_validation"
        return capture_batch(
            batch_root,
            batch_id=f"{attempt.cohort_id}-{attempt.attempt_index}",
            raw_rows=raw_rows,
            compact_rows=compact_rows,
            exact_manifests=dict(exact_manifests),
            summary=compact_rows[0],
            acceptance_report=dict(report),
            raw_transport_output=output,
            transport_outcome={
                "returncode": returncode,
                "timed_out": timed_out,
            },
            semantic_evidence_kind=evidence_kind,
        )


def compact_published_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Retain acceptance and provenance without duplicating published raw payloads."""
    keys = (
        "schema",
        "generated_at_unix",
        "returncode",
        "timed_out",
        "execution_policy",
        "overall_wall_clock_timeout_sec",
        "completion_reason",
        "failure_reason",
        "failure_labels",
        "all_passed",
        "acceptable_final_evidence",
        "live_validation_standard",
        "acceptance_facts",
        "acceptance_verification",
        "evidence_envelope",
        "session",
        "validation_context",
        "validation_route_manifest",
        "requested_calibration",
        "calibration_acceptance",
        "role_calibration_record",
        "role_calibration_identity",
        "role_calibration_evaluation",
        "role_efficiency_audit",
        "role_quality_advisory_labels",
        "batch_capture",
        "batch_publication",
    )
    compact = {key: report[key] for key in keys if key in report}
    compact["published_raw_payloads_retained_locally"] = False
    return compact


class AcceptanceRecomputer:
    def recompute(
        self,
        report: dict[str, Any],
        *,
        identity_required: bool,
        session_required: bool,
    ) -> dict[str, Any]:
        return apply_acceptance_evaluation(
            report,
            identity_required=identity_required,
            session_required=session_required,
        )


@dataclass
class SerializedDvcPublisher:
    repository: Path
    evict_after_verify: bool = True

    def publish(self, batch_root: Path) -> dict[str, Any]:
        receipt = publish_batch(
            self.repository,
            batch_root,
            evict_after_verify=self.evict_after_verify,
        )
        if not self.evict_after_verify:
            validate_capture(batch_root)
        return receipt


BOT_MEMORY_TABLES = [
    "bot_memory_daily_cooldowns",
    "bot_memory_danger_zones",
    "bot_memory_decision_fingerprints",
    "bot_memory_failed_paths",
    "bot_memory_material_sources",
    "bot_memory_objective_clusters",
    "bot_memory_pois",
    "bot_memory_recipe_sources",
    "bot_memory_safe_positions",
    "bot_memory_transport_usage",
]

VALIDATION_EVIDENCE_ACTIONS = {
    "party_formation": {"party_formed", "raid_formed", "validation_group_formed"},
    "raid_formation": {"raid_formed", "validation_group_formed"},
    "role_assignments": {"role_assignment", "validation_role_assignment", "tank_assigned", "healer_assigned", "raid_role_assignment"},
    "pulls": {"trash_action", "validation_route_trash_action", "boss_started", "boss_action", "validation_route_pull"},
    "target_priority": {"target_priority", "target_switch", "validation_target_priority", "assist_target_search_authoritative_focus", "raid_add_wave", "raid_boss_action"},
    "interrupts": {"interrupt", "interrupt_success", "assigned_interrupt_success", "validation_interrupt", "raid_interrupt"},
    "healer_assignments": {"healer_assignment", "validation_route_group_heal", "trash_heal", "external_defensive", "raid_healer_cooldown"},
    "tank_positioning": {"validation_route_tank_boss", "tank_positioning", "force_tank_focus", "move_to_validation_route_assist_target", "raid_position_anchor", "raid_boss_action"},
    "regrouping": {"validation_route_regroup", "regroup", "validation_route_hold_anchor", "move_to_validation_route_focus", "raid_position_anchor", "validation_route_complete"},
    "recovery": {"stuck_detected", "unstuck", "death", "dead_recovery", "validation_route_recovery", "raid_wipe"},
    "instance_reset": {"instance_reset"},
}


def sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def database_name(database_url: str) -> str:
    return (urlparse(database_url).path or "/").lstrip("/")


def qualify_sql_schema(sql: str, schema: str, database: str) -> str:
    return sql.replace(f"`{schema}`.", f"`{database.replace('`', '``')}`.")


def trinity_config_string(path: Path, key: str, default: str = "") -> str:
    if not path.exists():
        return default
    pattern = re.compile(rf'^\s*{re.escape(key)}\s*=\s*"(?P<value>[^"]*)"', re.MULTILINE)
    match = pattern.search(path.read_text(encoding="utf-8"))
    return match.group("value") if match else default


def trinity_config_bool(path: Path, key: str, default: bool = False) -> bool:
    if not path.exists():
        return default
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(?P<value>[^\s#]+)", re.MULTILINE)
    match = pattern.search(path.read_text(encoding="utf-8"))
    if not match:
        return default
    value = match.group("value").strip().strip('"').lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def load_validation_route(scenario_dir: Path, context: dict[str, Any]) -> dict[str, Any]:
    scenario_id = str(context.get("scenario_id") or "")
    route_node_id = str(context.get("route_node_id") or "")
    if not scenario_id:
        return {}
    route_path = scenario_dir / "validation_routes.jsonl"
    if not route_path.exists():
        return {}
    rows: list[dict[str, Any]] = []
    for line in route_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("scenario_id") or "") != scenario_id:
            continue
        rows.append(row)
    rows.sort(key=lambda row: int(row.get("step") or 0))
    for generation, row in enumerate(rows, 1):
        row["route_generation"] = generation
    if route_node_id:
        return next((row for row in rows if str(row.get("route_node_id") or "") == route_node_id), {})
    route_step = int(context.get("route_step") or 0)
    route_kind = str(context.get("route_kind") or "")
    route_label = str(context.get("route_label") or "")
    mechanic_profile = str(context.get("mechanic_profile") or "")
    if not (route_step and route_kind and route_label):
        return {}
    return next(
        (
            row
            for row in rows
            if int(row.get("step") or 0) == route_step
            and str(row.get("kind") or "") == route_kind
            and str(row.get("label") or "") == route_label
            and (not mechanic_profile or str(row.get("mechanic_profile") or "") == mechanic_profile)
        ),
        {},
    )


def load_validation_routes_for_scenario(scenario_dir: Path, scenario_id: str) -> list[dict[str, Any]]:
    route_path = scenario_dir / "validation_routes.jsonl"
    if not scenario_id or not route_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in route_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("scenario_id") or "") == scenario_id and str(row.get("kind") or "") in {"trash", "boss", "travel", "regroup", "descent"} and bool(row.get("coordinates_valid", True)):
            rows.append(row)
    rows.sort(key=lambda row: int(row.get("step") or 0))
    for generation, row in enumerate(rows, 1):
        row["route_generation"] = generation
    return rows


def validate_route_runtime_profile_contract(
    config_path: Path,
    scenario_dir: Path,
    scenario_id: str,
    routes: list[dict[str, Any]],
) -> dict[str, Any]:
    if not routes:
        raise SystemExit("validation route selected no route rows")
    if any(
        str(route.get("scenario_id") or "") != scenario_id
        or str(route.get("runtime_profile_id") or "") != scenario_id
        for route in routes
    ):
        raise SystemExit("validation route/profile identity mismatch")
    profile_manifest = Path(
        trinity_config_string(config_path, "BotWorld.ProfileManifest", "dataset/bot_runtime_profiles/profiles.json")
    )
    if not profile_manifest.is_absolute():
        profile_manifest = REPO_ROOT / profile_manifest
    profile_rows = json.loads(profile_manifest.read_text(encoding="utf-8")).get("profiles") or []
    selected_profiles = [row for row in profile_rows if str(row.get("name") or "") == scenario_id]
    if len(selected_profiles) != 1:
        raise SystemExit("validation route runtime profile is missing or ambiguous")
    selected_profile = selected_profiles[0]
    profile_route = selected_profile.get("validation_route") if isinstance(selected_profile.get("validation_route"), dict) else {}
    configured_manifest = Path(str(profile_route.get("manifest_path") or ""))
    if not configured_manifest.is_absolute():
        configured_manifest = REPO_ROOT / configured_manifest
    expected_manifest = scenario_dir / "validation_routes.jsonl"
    if (
        str(selected_profile.get("pool_tag_filter") or "") != scenario_id
        or str(profile_route.get("scenario_id") or "") != scenario_id
        or configured_manifest.resolve() != expected_manifest.resolve()
    ):
        raise SystemExit("validation route runtime profile contract mismatch")
    return selected_profile


def validation_route_manifest_payload(scenario_id: str, routes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "bot_live_validation_route_manifest_v1",
        "scenario_id": scenario_id,
        "route_count": len(routes),
        "expected_segments": [route_segment_output_name(route) for route in routes],
        "advance_mode": "terminal",
        "routes": routes,
    }


def write_validation_route_manifest(output_dir: Path, scenario_id: str, routes: list[dict[str, Any]]) -> tuple[Path, dict[str, Any]]:
    payload = validation_route_manifest_payload(scenario_id, routes)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "validation_route_manifest.json"
    write_json(manifest_path, payload)
    return manifest_path, payload


def route_segment_output_name(route: dict[str, Any]) -> str:
    step = int(route.get("step") or 0)
    label = str(route.get("label") or route.get("route_node_id") or "segment")
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in label).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return f"{step:02d}_{slug or 'segment'}"


def route_validation_context(scenario_id: str, route: dict[str, Any], *, include_segment: bool = True) -> dict[str, Any]:
    context: dict[str, Any] = {
        "scenario_id": scenario_id,
        "route_node_id": str(route.get("route_node_id") or ""),
        "route_label": str(route.get("label") or ""),
        "route_kind": str(route.get("kind") or ""),
        "route_step": int(route.get("step") or 0),
        "route_generation": int(route.get("route_generation") or 0),
        "mechanic_profile": str(route.get("mechanic_profile") or ""),
    }
    if include_segment:
        context["segment_id"] = route_segment_output_name(route)
    return {key: value for key, value in context.items() if value not in {"", 0}}


def route_segment_complete(report: dict[str, Any], route: dict[str, Any] | None) -> bool:
    if not route:
        return False
    transient_terminal_labels = {
        "boss_attempt_no_kill",
        "no_progress_observed",
        "semantic_progress_plateau",
        "validation_route_assist_focus_loop",
        "validation_route_stuck_loop",
    }
    if any(label not in transient_terminal_labels for label in (report.get("failure_labels") or [])):
        return False
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    context = report.get("validation_context") if isinstance(report.get("validation_context"), dict) else {}
    node_id = str(route.get("route_node_id") or context.get("route_node_id") or "")
    generation = int(route.get("route_generation") or context.get("route_generation") or 0)
    trace = report.get("trace") if isinstance(report.get("trace"), dict) else {}
    counts = scoped_validation_evidence_counts(trace_entries(trace), node_id, generation)
    required = [str(row) for row in (route.get("required_evidence") or []) if row]
    if any(int(counts.get(name) or 0) <= 0 for name in required):
        return False
    terminals = evidence.get("route_terminal_evidence") if isinstance(evidence.get("route_terminal_evidence"), list) else []
    if not any(str(row.get("route_node_id") or "") == node_id and int(row.get("route_generation") or 0) == generation for row in terminals):
        return False
    kind = str(route.get("kind") or "")
    if kind == "boss":
        kills = evidence.get("real_boss_kill_evidence") if isinstance(evidence.get("real_boss_kill_evidence"), list) else []
        return any(str(row.get("route_node_id") or "") == node_id and int(row.get("route_generation") or 0) == generation for row in kills)
    if kind == "trash":
        return int(evidence.get("trash_pulls") or 0) > 0
    return bool(required)


def supersede_transient_route_failures(report: dict[str, Any]) -> None:
    transient = {
        "boss_attempt_no_kill",
        "no_progress_observed",
        "semantic_progress_plateau",
        "validation_route_assist_focus_loop",
        "validation_route_stuck_loop",
    }
    labels = [str(label) for label in (report.get("failure_labels") or [])]
    resolved = [label for label in labels if label in transient]
    report["failure_labels"] = [label for label in labels if label not in transient]
    superseded = [str(label) for label in (report.get("superseded_failure_labels") or [])]
    for label in resolved:
        if label not in superseded:
            superseded.append(label)
    report["superseded_failure_labels"] = superseded
    report["failure_reason"] = report["failure_labels"][0] if report["failure_labels"] else None


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def render_command(command: list[str]) -> str:
    return " ".join(shell_quote(part) for part in command)


def upsert_trinity_config(text: str, key: str, value: str) -> str:
    text = text.replace("\\n", "\n")
    line = f"{key} = {value}"
    pattern = re.compile(rf"^(?P<prefix>\s*{re.escape(key)}\s*=\s*).*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(line, text)
    return text.rstrip() + "\n" + line + "\n"


def route_alternate_target_entries(route: dict[str, Any]) -> list[int]:
    entries: list[int] = []
    for entry in route.get("alternate_target_entries") or []:
        entry_id = int(entry or 0)
        if entry_id > 0 and entry_id not in entries:
            entries.append(entry_id)
    return entries


def write_validation_config(
    base_config: Path,
    output_dir: Path,
    pool_tag: str = "",
    validation_route: dict[str, Any] | None = None,
    validation_route_manifest_path: Path | None = None,
    autostart: bool = True,
    calibration_only: bool = False,
    calibration_reference_conditions: bool = False,
    calibration_self_provided_baseline: bool = False,
    console_enabled: bool | None = None,
) -> Path:
    route = validation_route or {}
    if not pool_tag and not route and not validation_route_manifest_path and autostart and not calibration_only:
        return base_config
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = output_dir / "worldserver.validation.conf"
    if not base_config.exists() and not base_config.is_absolute():
        rooted = REPO_ROOT / base_config
        if rooted.exists():
            base_config = rooted
    if not base_config.exists():
        base_config = REPO_ROOT / "src/server/worldserver/worldserver.conf.dist"
    text = base_config.read_text(encoding="utf-8") if base_config.exists() else ""
    generator_marker = "# Generated by tools.bot_ml.run_live_bot_validation for scenario-scoped validation."
    if generator_marker not in text.splitlines():
        text = text.rstrip() + f"\n{generator_marker}\n"
    text = upsert_trinity_config(text, "BotWorld.AutoStart", "1" if autostart else "0")
    if console_enabled is not None:
        text = upsert_trinity_config(text, "Console.Enable", "1" if console_enabled else "0")
    if pool_tag:
        text = upsert_trinity_config(text, "BotWorld.PoolTagFilter", f'"{pool_tag.replace(chr(34), "")}"')
    if calibration_only:
        # The runner starts the named calibration cohort after server admission.
        # Suppress the default cohort so its route/profile cannot consume the
        # canonical calibration target or deterministic support bots first.
        text = upsert_trinity_config(text, "BotWorld.AutoStart", "0")
        text = upsert_trinity_config(text, "BotWorld.RuntimeProfile", '""')
        text = upsert_trinity_config(text, "BotWorld.TargetPopulation", "0")
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Enable", "0")
        text = upsert_trinity_config(
            text,
            "BotWorld.CombatCalibration.ReferenceConditions",
            "1" if calibration_reference_conditions else "0",
        )
        text = upsert_trinity_config(
            text,
            "BotWorld.CombatCalibration.SelfProvidedBaseline",
            "1" if calibration_self_provided_baseline else "0",
        )
    if validation_route_manifest_path and not calibration_only:
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ManifestPath", f'"{str(validation_route_manifest_path).replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.AdvanceMode", '"terminal"')
    if route and not calibration_only:
        route_profile = str(route.get("runtime_profile_id") or route.get("scenario_id") or "").strip()
        if validation_route_manifest_path and route_profile:
            # A manifest-scoped diagnostic must never inherit the base file's
            # Stonecore/canonical profile during AutoStart. The profile owns
            # the exact roster, pool, and route identity selected above.
            text = upsert_trinity_config(
                text,
                "BotWorld.RuntimeProfile",
                f'"{route_profile.replace(chr(34), "")}"',
            )
        # A configured runtime profile is applied after the file-backed route
        # settings.  Validation profiles commonly carry a full manifest, which
        # would silently replace a requested direct segment with node zero.
        # Direct-node configs already contain the pool and route contract, so
        # suppress only that late profile application for segment validation.
        if not validation_route_manifest_path:
            text = upsert_trinity_config(text, "BotWorld.RuntimeProfile", '""')
        expected_bot_count = int(route.get("expected_bot_count") or 0)
        if expected_bot_count > 0:
            text = upsert_trinity_config(text, "BotWorld.TargetPopulation", str(expected_bot_count))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Enable", "1")
        text = upsert_trinity_config(text, "BotWorld.SafePositionMemorySec", "900")
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ScenarioId", f'"{str(route.get("scenario_id") or "").replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.NodeId", f'"{str(route.get("route_node_id") or "").replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Generation", str(int(route.get("route_generation") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Label", f'"{str(route.get("label") or "").replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Kind", f'"{str(route.get("kind") or "").replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.MechanicProfile", f'"{str(route.get("mechanic_profile") or "").replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Map", str(int(route.get("map_id") or 0)))
        # Direct segments need the same legal movement destination used when
        # the node is loaded from a manifest.  Boss coordinates can be on an
        # elevated platform or inside collision while the navigation anchor
        # is the reachable pull position.
        route_x = route.get("navigation_anchor_x", route.get("x"))
        route_y = route.get("navigation_anchor_y", route.get("y"))
        route_z = route.get("navigation_anchor_z", route.get("z"))
        route_o = route.get("navigation_anchor_o", route.get("o"))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.X", str(float(route_x or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Y", str(float(route_y or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.Z", str(float(route_z or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.O", str(float(route_o or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.TargetEntry", str(int(route.get("source_entry") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.OpenerTargetEntry", str(int(route.get("opener_target_entry") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.AlternateTargetEntries", f'"{",".join(str(entry) for entry in route_alternate_target_entries(route))}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.AddTargetEntries", f'"{",".join(str(int(entry)) for entry in (route.get("add_target_entries") or []) if int(entry or 0) > 0)}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.PackTargetEntries", f'"{",".join(str(int(entry)) for entry in (route.get("pack_target_entries") or []) if int(entry or 0) > 0)}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.HazardSourceEntry", str(int(route.get("hazard_source_entry") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.HazardDetectionSpellId", str(int(route.get("hazard_detection_spell_id") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.HazardDamageSpellId", str(int(route.get("hazard_damage_spell_id") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.HazardShape", f'"{str(route.get("hazard_shape") or "").replace(chr(34), "")}"')
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.HazardRadiusYards", str(float(route.get("hazard_radius_yards") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.HazardSafetyMarginYards", str(float(route.get("hazard_safety_margin_yards") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ClusterRadiusYards", str(float(route.get("cluster_radius_yards") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationAreaTriggerId", str(int(route.get("activation_area_trigger_id") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationDataId", str(int(route.get("activation_data_id") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationDataValue", str(int(route.get("activation_data_value") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationSpawnGroupId", str(int(route.get("activation_spawn_group_id") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationActionEntry", str(int(route.get("activation_action_entry") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationActionId", str(int(route.get("activation_action_id") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationSummonEntry", str(int(route.get("activation_summon_entry") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationSummonX", str(float(route.get("activation_summon_x") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationSummonY", str(float(route.get("activation_summon_y") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationSummonZ", str(float(route.get("activation_summon_z") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.ActivationSummonO", str(float(route.get("activation_summon_o") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.OpenerSummonEntry", str(int(route.get("opener_summon_entry") or 0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.OpenerSummonX", str(float(route.get("opener_summon_x") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.OpenerSummonY", str(float(route.get("opener_summon_y") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.OpenerSummonZ", str(float(route.get("opener_summon_z") or 0.0)))
        text = upsert_trinity_config(text, "BotWorld.ValidationRoute.OpenerSummonO", str(float(route.get("opener_summon_o") or 0.0)))
        if str(route.get("kind") or "") in {"boss", "trash"}:
            text = upsert_trinity_config(text, "BotProgression.AllowDungeons", "1")
    generated.write_text(text, encoding="utf-8")
    return generated


def bind_validation_provisioning_sql(config_path: Path, provisioning: dict[str, Any]) -> Path:
    """Keep worldserver auto-prepare on the exact SQL generated for this run.

    Named validation profiles provision again when BotWorld starts.  Pointing the
    generated config at the run-scoped SQL prevents an older DVC checkout from
    replacing freshly provisioned characters (and, in particular, assigning
    deterministic item GUIDs to the wrong owners).
    """
    text = config_path.read_text(encoding="utf-8")
    account_path = Path(str(provisioning["account_sql"])).resolve()
    character_path = Path(str(provisioning["character_sql"])).resolve()
    text = upsert_trinity_config(text, "BotWorld.ValidationProvisionAccountsSql", f'"{account_path}"')
    text = upsert_trinity_config(text, "BotWorld.ValidationProvisionCharactersSql", f'"{character_path}"')
    config_path.write_text(text, encoding="utf-8")
    return config_path


def split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    uncommented = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    for char in uncommented:
        current.append(char)
        if escaped:
            escaped = False
            continue
        if quote and char == "\\":
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        elif char == ";" and quote is None:
            text = "".join(current).strip().rstrip(";").strip()
            if text and not text.startswith("--"):
                statements.append(text)
            current = []
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def execute_sql_text(database_url: str, sql: str) -> int:
    statements = split_sql_statements(sql)
    conn = connect_mysql(database_url)
    try:
        with conn.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        conn.commit()
    finally:
        conn.close()
    return len(statements)


def tag_predicate(tags: list[str]) -> str:
    if not tags:
        return "1 = 1"
    return "(" + " OR ".join(f"p.`experiment_tags` LIKE {sql_quote('%' + tag + '%')}" for tag in tags) + ")"


def build_bot_pool_reset_sql(tags: list[str] | None = None, world_database: str = "world", reset_positions: bool = True, reset_quests: bool = True, reset_memory: bool = True) -> str:
    tags = tags or ["test_account"]
    predicate = tag_predicate(tags)
    guid_select = f"SELECT p.`guid` FROM `characters`.`character_bot_pool` p WHERE p.`enabled` = 1 AND {predicate}"
    lines = [
        "-- Generated by tools.bot_ml.run_live_bot_validation.",
        "-- Resets only enabled bot-pool rows matching the configured experiment_tags predicate.",
        "UPDATE `characters`.`character_bot_pool` p SET p.`in_use` = 0 WHERE p.`enabled` = 1 AND " + predicate + ";",
        "UPDATE `characters`.`characters` c JOIN `characters`.`character_bot_pool` p ON p.`guid` = c.`guid` "
        f"SET c.`online` = 0, c.`health` = {VALIDATION_FULL_STAT_SEED}, c.`power1` = {VALIDATION_FULL_STAT_SEED}, "
        f"c.`characterFlags` = c.`characterFlags` & ~{VALIDATION_GHOST_CHARACTER_FLAG}, "
        f"c.`at_login` = c.`at_login` & ~{VALIDATION_RESURRECT_AT_LOGIN_FLAG} "
        "WHERE p.`enabled` = 1 AND " + predicate + ";",
        f"DELETE FROM `characters`.`character_instance` WHERE `guid` IN ({guid_select});",
        f"DELETE FROM `characters`.`corpse_phases` WHERE `OwnerGuid` IN ({guid_select});",
        f"DELETE FROM `characters`.`corpse` WHERE `guid` IN ({guid_select});",
        f"DELETE FROM `characters`.`character_aura` WHERE `guid` IN ({guid_select}) AND `spell` = {VALIDATION_GHOST_AURA_ID};",
        "DELETE gi FROM `characters`.`group_instance` gi "
        "JOIN `characters`.`groups` g ON g.`guid` = gi.`guid` "
        f"WHERE g.`leaderGuid` IN ({guid_select}) "
        f"OR g.`guid` IN (SELECT gm.`guid` FROM `characters`.`group_member` gm WHERE gm.`memberGuid` IN ({guid_select}));",
        "DELETE gm FROM `characters`.`group_member` gm "
        f"WHERE gm.`memberGuid` IN ({guid_select}) "
        f"OR gm.`guid` IN (SELECT g.`guid` FROM `characters`.`groups` g WHERE g.`leaderGuid` IN ({guid_select}));",
        "DELETE g FROM `characters`.`groups` g "
        f"WHERE g.`leaderGuid` IN ({guid_select});",
        f"DELETE pc FROM `characters`.`pet_spell_cooldown` pc JOIN `characters`.`character_pet` cp ON cp.`id` = pc.`guid` WHERE cp.`owner` IN ({guid_select});",
        f"DELETE pa FROM `characters`.`pet_aura` pa JOIN `characters`.`character_pet` cp ON cp.`id` = pa.`guid` WHERE cp.`owner` IN ({guid_select});",
        f"DELETE FROM `characters`.`mail_items` WHERE `receiver` IN ({guid_select});",
        f"DELETE FROM `characters`.`mail` WHERE `receiver` IN ({guid_select});",
    ]
    if reset_positions:
        lines.append(
            "UPDATE `characters`.`characters` c "
            "JOIN `characters`.`character_bot_pool` p ON p.`guid` = c.`guid` "
            f"JOIN `{world_database}`.`playercreateinfo` pci ON pci.`race` = c.`race` AND pci.`class` = c.`class` "
            f"SET c.`map` = pci.`map`, c.`position_x` = pci.`position_x`, c.`position_y` = pci.`position_y`, c.`position_z` = pci.`position_z`, c.`orientation` = pci.`orientation`, c.`health` = {VALIDATION_FULL_STAT_SEED}, c.`power1` = {VALIDATION_FULL_STAT_SEED} "
            "WHERE p.`enabled` = 1 AND "
            + predicate
            + ";"
        )
    if reset_quests:
        for table in [
            "character_queststatus",
            "character_queststatus_daily",
            "character_queststatus_monthly",
            "character_queststatus_rewarded",
            "character_queststatus_seasonal",
            "character_queststatus_weekly",
            "character_aura",
            "character_spell_cooldown",
        ]:
            lines.append(f"DELETE FROM `characters`.`{table}` WHERE `guid` IN ({guid_select});")
    if reset_memory:
        for table in BOT_MEMORY_TABLES:
            lines.append(f"DELETE FROM `characters`.`{table}` WHERE `bot_guid` IN ({guid_select});")
    return "\n".join(lines) + "\n"


def prepare_validation_provisioning(
    output_dir: Path,
    config_path: Path,
    gear_profiles_path: Path,
    worldserver_conf: Path,
    bwd_diagnostic_shard_fixture: Path = DEFAULT_BWD_DIAGNOSTIC_SHARD_FIXTURE,
    apply: bool = False,
) -> dict[str, Any]:
    # Keep live preparation on the exact merged config used by the checked-in
    # DVC provisioning pipeline.  Loading only the three canonical scenarios
    # here silently omitted all six disjoint BWD diagnostic pools (60 accounts
    # and 60 characters), making the route identity gate impossible to satisfy.
    config = apply_gear_profiles(
        load_config_with_bwd_diagnostic_shards(config_path, bwd_diagnostic_shard_fixture),
        load_gear_profiles(gear_profiles_path),
    )
    auth_url = database_url_from_worldserver_conf(worldserver_conf, "LoginDatabaseInfo")
    character_url = database_url_from_worldserver_conf(worldserver_conf, "CharacterDatabaseInfo")
    account_sql = qualify_sql_schema(build_account_insert_sql(config), "auth", database_name(auth_url))
    character_sql = qualify_sql_schema(build_character_insert_sql(config), "characters", database_name(character_url))
    provision_dir = output_dir / "validation_provisioning_apply"
    provision_dir.mkdir(parents=True, exist_ok=True)
    account_path = provision_dir / "provision_accounts.sql"
    character_path = provision_dir / "provision_characters.sql"
    account_path.write_text(account_sql, encoding="utf-8")
    character_path.write_text(character_sql, encoding="utf-8")

    report: dict[str, Any] = {
        "schema": "bot_live_validation_provisioning_apply_v1",
        "applied": apply,
        "config": str(config_path),
        "bwd_diagnostic_shard_fixture": str(bwd_diagnostic_shard_fixture),
        "gear_profiles": str(gear_profiles_path),
        "account_sql": str(account_path),
        "character_sql": str(character_path),
        "auth_database": sanitize_database_url(auth_url),
        "character_database": sanitize_database_url(character_url),
        "account_statement_count": len(split_sql_statements(account_sql)),
        "character_statement_count": len(split_sql_statements(character_sql)),
    }
    if apply:
        report["executed_account_statements"] = execute_sql_text(auth_url, account_sql)
        report["executed_character_statements"] = execute_sql_text(character_url, character_sql)
    return report


def prepare_calibration_consumables(
    output_dir: Path,
    worldserver_conf: Path,
    target_spec: str,
    target_catalog_path: Path,
    apply: bool = False,
) -> dict[str, Any]:
    """Keep runner dependencies injectable while delegating restock policy."""
    return _prepare_calibration_consumables(
        output_dir,
        worldserver_conf,
        target_spec,
        target_catalog_path,
        apply,
        connect_mysql_fn=connect_mysql,
        database_name_fn=database_name,
        database_url_from_conf_fn=database_url_from_worldserver_conf,
        execute_sql_text_fn=execute_sql_text,
    )


def server_route_start_contract(route: dict[str, Any]) -> dict[str, Any]:
    """Describe the entrance placement owned by the inactive server admission gate.

    The live operator must never rewrite character position, health, power, or
    corpse state to manufacture a clean attempt.  The population coordinator
    consumes these pinned coordinates while the cohort is still inert, proves
    the resulting native map/group/difficulty state in its admission receipt,
    and only then enables bot actions.
    """
    map_id = int(route.get("bot_start_map_id") or 0)
    x = float(route.get("bot_start_x") or 0.0)
    y = float(route.get("bot_start_y") or 0.0)
    z = float(route.get("bot_start_z") or 0.0)
    o = float(route.get("bot_start_o") or 0.0)
    if not map_id or (x == 0.0 and y == 0.0 and z == 0.0):
        return {
            "schema": "bot_live_validation_server_route_start_v2",
            "provisioning_owner": "server_population_coordinator",
            "orchestrator_mutation_applied": False,
            "reason": "route_start_not_configured",
        }
    return {
        "schema": "bot_live_validation_server_route_start_v2",
        "provisioning_owner": "server_population_coordinator",
        "orchestrator_mutation_applied": False,
        "action_gate_state": "inactive_until_admission_receipt_commit",
        "map_id": map_id,
        "x": x,
        "y": y,
        "z": z,
        "o": o,
    }


def prepare_bot_pool_reset(
    output_dir: Path,
    worldserver_conf: Path,
    tags: list[str],
    apply: bool = False,
    reset_positions: bool = True,
    reset_quests: bool = True,
    reset_memory: bool = True,
) -> dict[str, Any]:
    world_url = database_url_from_worldserver_conf(worldserver_conf, "WorldDatabaseInfo")
    character_url = database_url_from_worldserver_conf(worldserver_conf, "CharacterDatabaseInfo")
    sql = build_bot_pool_reset_sql(tags, database_name(world_url), reset_positions, reset_quests, reset_memory)
    sql = qualify_sql_schema(sql, "characters", database_name(character_url))
    reset_dir = output_dir / "bot_pool_reset"
    reset_dir.mkdir(parents=True, exist_ok=True)
    sql_path = reset_dir / "reset_bot_pool.sql"
    sql_path.write_text(sql, encoding="utf-8")
    report: dict[str, Any] = {
        "schema": "bot_live_validation_bot_pool_reset_v1",
        "applied": apply,
        "tags": tags,
        "reset_positions": reset_positions,
        "reset_quests": reset_quests,
        "reset_memory": reset_memory,
        "sql": str(sql_path),
        "statement_count": len(split_sql_statements(sql)),
        "world_database": sanitize_database_url(world_url),
        "character_database": sanitize_database_url(character_url),
    }
    if apply:
        report["executed_statements"] = execute_sql_text(character_url, sql)
    return report


def is_calibration_start_command(command_text: str) -> bool:
    tokens = command_text.strip().split()
    return len(tokens) >= 3 and tokens[:2] == [".botauto", "calibrate"] and "start" in tokens[2:4]


def command_script(
    selector: str = "all",
    trace_limit: int = 20,
    start: bool = True,
    stop: bool = False,
    exit_server: bool = True,
    combat_calibration: bool = False,
    cohort_id: str = "",
    calibration_mode: str = "single_target_300",
    calibration_target_spec: str = "protection_paladin",
    calibration_seed: int = 1,
    calibration_only: bool = False,
    trace_delta: bool = False,
) -> str:
    if cohort_id and not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", cohort_id):
        raise ValueError("invalid cohort_id")
    scope = f" {cohort_id}" if cohort_id else ""
    commands: list[str] = []
    if start:
        commands.append(f".botauto start{scope}")
    if combat_calibration:
        commands.append(
            f".botauto calibrate{scope} start {calibration_mode} "
            f"{calibration_target_spec} {max(1, calibration_seed)}"
        )
    commands.append(f".botauto status{scope}")
    if not calibration_only:
        trace_suffix = " delta" if trace_delta else ""
        commands.extend(
            [
                f".botauto diagnose{scope} {selector}",
                # Completion-watchdog heartbeats repeat this command.  Export
                # only the server-side trace cursor delta so a long route does
                # not replay each bot's cumulative 128-entry ring into the
                # bounded worldserver output buffer.  Status and diagnosis
                # remain full snapshots for liveness and current decisions.
                f".botauto trace{scope} {selector} {trace_limit}{trace_suffix}",
            ]
        )
    if combat_calibration:
        commands.append(f".botauto calibrate{scope} status")
    commands.append(f".botauto combatlog{scope}")
    if not cohort_id and not calibration_only:
        commands.append(".botexp summary")
    if combat_calibration:
        commands.append(f".botauto calibrate{scope} stop")
    if stop:
        commands.append(f".botauto stop{scope}")
    if exit_server:
        commands.append("server shutdown force 0")
    return "\n".join(commands) + "\n"


def parse_json_objects(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    index = 0
    while index < len(output):
        starts = [
            candidate
            for candidate in (output.find("{", index), output.find("[", index))
            if candidate >= 0
        ]
        start = min(starts) if starts else -1
        if start == -1:
            break
        try:
            payload, end = decoder.raw_decode(output[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(payload, dict) and _is_telemetry_payload(payload):
            rows.append(payload)
        index = start + max(end, 1)
    return rows


def _is_telemetry_payload(payload: Any) -> bool:
    """Accept only envelopes whose optional action identifier is a string."""
    if not isinstance(payload, dict):
        return False
    action = payload.get("action")
    return action is None or isinstance(action, str)


def strip_combat_log_chunks(output: str) -> str:
    """Drop transport-only base64 chunks after their decoded artifact is written."""
    return "\n".join(
        line for line in output.splitlines()
        if "botauto_combatlog_chunk" not in line and "botauto_combatlog_complete" not in line
    ) + ("\n" if output.endswith(("\n", "\r")) else "")


def strip_calibration_status_chunks(output: str) -> str:
    """Drop transport-only calibration chunks after the report retains the decoded status."""
    return "\n".join(
        line for line in output.splitlines()
        if "botauto_calibrate_status_chunk" not in line
        and "botauto_calibrate_status_complete" not in line
    ) + ("\n" if output.endswith(("\n", "\r")) else "")


def combined_calibration_status(
    payloads: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    latest: dict[str, Any] = {}
    transport: dict[str, Any] = {
        "direct": False,
        "complete_marker": False,
        "expected_chunks": 0,
        "received_chunks": 0,
        "total_bytes": 0,
        "reassembled": False,
    }
    chunks: dict[int, dict[str, Any]] = {}
    expected = 0
    cohort_id = ""

    for row in payloads:
        action = str(row.get("action") or "")
        if action == "botauto_calibrate_status":
            latest = row
            chunks = {}
            expected = 0
            cohort_id = str(row.get("cohort_id") or "")
            transport = {
                "direct": True,
                "complete_marker": False,
                "expected_chunks": 0,
                "received_chunks": 0,
                "total_bytes": 0,
                "reassembled": False,
            }
            continue
        if action == "botauto_calibrate_status_chunk":
            try:
                sequence = int(row.get("sequence"))
                chunk_count = int(row.get("chunk_count"))
            except (TypeError, ValueError):
                latest = {}
                transport["reassembled"] = False
                continue
            row_cohort = str(row.get("cohort_id") or "")
            if sequence == 0:
                chunks = {}
                expected = chunk_count
                cohort_id = row_cohort
                latest = {}
            if (
                chunk_count <= 0
                or chunk_count != expected
                or sequence < 0
                or sequence >= expected
                or row_cohort != cohort_id
                or row.get("encoding") != "base64"
                or int(row.get("calibration_status_chunk_schema_version") or 0) != 1
            ):
                latest = {}
                transport = {
                    "direct": False,
                    "complete_marker": False,
                    "expected_chunks": expected,
                    "received_chunks": len(chunks),
                    "total_bytes": 0,
                    "reassembled": False,
                }
                continue
            chunks[sequence] = row
            transport = {
                "direct": False,
                "complete_marker": False,
                "expected_chunks": expected,
                "received_chunks": len(chunks),
                "total_bytes": 0,
                "reassembled": False,
            }
            continue
        if action != "botauto_calibrate_status_complete":
            continue

        try:
            completion_expected = int(row.get("chunk_count"))
            total_bytes = int(row.get("total_bytes"))
        except (TypeError, ValueError):
            completion_expected = 0
            total_bytes = 0
        complete = (
            int(row.get("calibration_status_chunk_schema_version") or 0) == 1
            and str(row.get("cohort_id") or "") == cohort_id
            and completion_expected == expected
            and expected > 0
            and set(chunks) == set(range(expected))
        )
        decoded: dict[str, Any] = {}
        if complete:
            try:
                raw = b"".join(
                    base64.b64decode(chunks[index]["data"], validate=True)
                    for index in range(expected)
                )
                candidate = json.loads(raw)
                complete = (
                    len(raw) == total_bytes
                    and isinstance(candidate, dict)
                    and candidate.get("action") == "botauto_calibrate_status"
                    and bool(candidate.get("ok")) == bool(row.get("payload_ok"))
                )
                if complete:
                    decoded = candidate
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                complete = False
        latest = decoded
        transport = {
            "direct": False,
            "complete_marker": True,
            "expected_chunks": completion_expected,
            "received_chunks": len(chunks),
            "total_bytes": total_bytes,
            "reassembled": complete,
        }

    return latest, transport


def classify_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    payloads = [row for row in payloads if _is_telemetry_payload(row)]
    status = next(
        (
            row
            for row in reversed(payloads)
            if row.get("action") in {"botexp_status", "botauto_status"}
            or ("active" in row and not str(row.get("action") or "").startswith("botauto_calibrate"))
            or ({"active_bots", "target_bots"} <= set(row))
        ),
        {},
    )
    diagnosis = next((row for row in reversed(payloads) if row.get("diagnosis_schema_version") or row.get("diagnoses") or row.get("diagnosis")), {})
    trace_payloads = [row for row in payloads if row.get("trace_schema_version") or row.get("entries")]
    trace = combined_trace_payload(trace_payloads)
    summary = next((row for row in reversed(payloads) if row.get("summary_schema_version") or "duration_minutes" in row or "total_kills" in row or "bot_learning" in row), {})
    combat_log = combined_combat_log(payloads)
    combat_calibration, combat_calibration_transport = combined_calibration_status(payloads)
    return {
        "status": status,
        "diagnosis": diagnosis,
        "trace": trace,
        "summary": summary,
        "combat_log": combat_log,
        "combat_log_transport": combat_log_transport_status(payloads),
        "combat_calibration": combat_calibration,
        "combat_calibration_transport": combat_calibration_transport,
    }


def load_combat_calibration_reference(
    path: Path = DEFAULT_COMBAT_CALIBRATION_REFERENCE,
) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if payload.get("schema") != "bot_combat_calibration_reference_v1":
        return {}
    return payload


def enrich_combat_calibration_reference(
    calibration: dict[str, Any],
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not calibration:
        return calibration
    reference = reference if reference is not None else load_combat_calibration_reference()
    profiles = reference.get("profiles") if reference else None
    if not isinstance(profiles, list) or not profiles:
        return calibration

    profile_by_class = {
        int(profile.get("class_id") or 0): profile
        for profile in profiles
        if int(profile.get("class_id") or 0) > 0
    }
    comparisons: list[dict[str, Any]] = []
    best_single = ((calibration.get("best_windows") or {}).get("single_target") or [])
    for bot in best_single:
        profile = profile_by_class.get(int(bot.get("class_id") or 0))
        if not profile:
            continue
        live_dps = float(bot.get("dps") or 0.0)
        reference_dps = float(profile.get("single_target_dps") or 0.0)
        comparisons.append(
            {
                "name": str(bot.get("name") or ""),
                "spec": str(profile.get("spec") or ""),
                "live_dps": round(live_dps, 2),
                "reference_dps": round(reference_dps, 2),
                "reference_ratio": round(live_dps / reference_dps, 4) if reference_dps > 0 else None,
                "directly_comparable": False,
            }
        )

    # This older reference is retained only as descriptive provenance. Exact
    # calibration scoring is independently reconstructed from the generated
    # per-spec request/result binding; mutating native normalization here made
    # the report disagree with the immutable raw calibration payload.
    calibration["external_reference"] = {
        "reference_id": reference.get("reference_id"),
        "source": reference.get("source"),
        "methodology": reference.get("methodology"),
        "profiles": profiles,
        "live_acceptance": reference.get("live_acceptance"),
    }
    calibration["external_reference_comparisons"] = comparisons
    return calibration


def apply_calibration_only_acceptance(report: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one explicit Phase 8 calibration window's transport integrity."""
    calibration = report.get("combat_calibration") or {}
    requested = report.get("requested_calibration") or {}
    rejections: list[str] = []

    if report.get("timed_out"):
        rejections.append("calibration_timed_out")
    if int(report.get("returncode") or 0) != 0:
        rejections.append("calibration_worldserver_failed")
    if not calibration:
        rejections.append("missing_calibration_status")
    if not bool(calibration.get("window_complete")):
        rejections.append("calibration_window_incomplete")
    if str(calibration.get("phase") or "") != "complete":
        rejections.append("calibration_phase_incomplete")
    if str(calibration.get("mode") or "") != str(requested.get("mode") or ""):
        rejections.append("calibration_mode_mismatch")
    if str(calibration.get("target_spec") or "") != str(requested.get("target_spec") or ""):
        rejections.append("calibration_target_mismatch")
    if int(calibration.get("seed") or 0) != int(requested.get("seed") or 0):
        rejections.append("calibration_seed_mismatch")
    if int(calibration.get("target_guid") or 0) <= 0:
        rejections.append("missing_calibration_target")
    if str(calibration.get("runtime_authority") or "") != "explicit_sql_rule_profiles":
        rejections.append("invalid_runtime_authority")
    if str(calibration.get("runtime_mode") or "") != "calibration_fixture":
        rejections.append("calibration_runtime_mode_mismatch")
    if calibration.get("non_certifying_assistance") is not True:
        rejections.append("calibration_non_certifying_assistance_not_declared")
    if bool(calibration.get("generic_ml_runtime_authority")):
        rejections.append("generic_ml_runtime_authority_enabled")
    if not bool(calibration.get("reset_applied")) or not str(calibration.get("reset_id") or ""):
        rejections.append("missing_calibration_reset")
    if int(calibration.get("cross_window_event_count") or 0) != 0:
        rejections.append("cross_window_contamination")
    scored_seconds = float(calibration.get("scored_seconds") or 0.0)
    if not 295.0 <= scored_seconds <= 305.0:
        rejections.append("scored_window_outside_tolerance")
    if int(calibration.get("scored_started_at_ms") or 0) <= 0:
        rejections.append("missing_scored_start")
    if int(calibration.get("scored_ended_at_ms") or 0) <= 0:
        rejections.append("missing_scored_end")
    if int(calibration.get("profile_generation") or 0) <= 0:
        rejections.append("missing_profile_generation")
    if not re.fullmatch(r"[0-9A-Fa-f]{64}", str(calibration.get("profile_content_hash") or "")):
        rejections.append("missing_profile_content_hash")

    bots = ((calibration.get("previous_window") or {}).get("bots") or [])
    target_guid = int(calibration.get("target_guid") or 0)
    target = next((bot for bot in bots if int(bot.get("guid") or 0) == target_guid), None)
    if target is None:
        rejections.append("missing_target_window_metrics")
    elif int(target.get("attempts") or 0) <= 0:
        rejections.append("missing_target_actions")

    rejections = list(dict.fromkeys(rejections))
    passed = not rejections
    report["calibration_acceptance"] = {
        "schema": "bot_combat_calibration_acceptance_v2",
        "passed": passed,
        "requested": requested,
        "scored_window_seconds": scored_seconds,
        "window_tolerance_seconds": 5,
        "target_guid": target_guid,
        "rejections": rejections,
    }
    report["stages"] = [
        {"stage": "combat_calibration", "passed": passed, "missing": rejections}
    ]
    report["passed"] = 1 if passed else 0
    report["failed"] = 0 if passed else 1
    report["final_evidence_rejections"] = rejections
    report["failure_labels"] = rejections
    report["failure_reason"] = rejections[0] if rejections else None
    report["completion_reason"] = "combat_calibration_complete" if passed else "combat_calibration_incomplete"
    report["acceptable_final_evidence"] = passed
    report["all_passed"] = passed
    return report


def attach_phase8_role_calibration(
    report: dict[str, Any],
    *,
    policy_path: Path = Path("experiments/configs/all_spec_role_calibration_policy_v1.json"),
) -> dict[str, Any]:
    """Attach canonical target normalization and independent role acceptance."""
    requested = report.get("requested_calibration") or {}
    calibration = report.get("combat_calibration") or {}
    record: dict[str, Any] | None = None
    try:
        record, evaluation = evaluate_runtime_calibration(
            calibration,
            target_spec=str(requested.get("target_spec") or ""),
            mode=str(requested.get("mode") or ""),
            policy_path=policy_path,
        )
        role_rejections = [str(value) for value in evaluation.get("failure_reasons") or []]
    except (
        Phase8CalibrationNormalizationError,
        OSError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        role_rejections = [f"normalization_error:{exc}"]
        evaluation = {
            "schema": "all_spec_role_calibration_evaluation_v1",
            "mode": str(requested.get("mode") or ""),
            "role": "",
            "reference_ratio": 0.0,
            "hard_floor_passed": False,
            "optimization_target_met": False,
            "checks": {"runtime_normalization_complete": False},
            "failure_reasons": role_rejections,
            "passed": False,
            "record_sha256": None,
            "policy_sha256": None,
        }

    role_passed = bool(evaluation.get("passed")) and not role_rejections
    report["role_calibration_record"] = record
    report["role_calibration_identity"] = dict(record.get("identity") or {}) if record else {}
    report["role_calibration_evaluation"] = evaluation
    report.setdefault("stages", []).append(
        {
            "stage": "role_calibration",
            "passed": role_passed,
            "missing": role_rejections,
        }
    )
    transport = report.get("calibration_acceptance") or {}
    transport_rejections = [str(value) for value in transport.get("rejections") or []]
    combined_rejections = list(
        dict.fromkeys(
            [
                *transport_rejections,
                *(f"role_calibration:{value}" for value in role_rejections),
            ]
        )
    )
    transport["transport_passed"] = bool(transport.get("passed"))
    transport["role_calibration_passed"] = role_passed
    transport["passed"] = bool(transport["transport_passed"] and role_passed)
    transport["rejections"] = combined_rejections
    report["calibration_acceptance"] = transport
    report["failure_labels"] = combined_rejections
    report["failure_reason"] = combined_rejections[0] if combined_rejections else None
    report["completion_reason"] = (
        "combat_calibration_complete" if not combined_rejections
        else "combat_calibration_role_gate_failed"
    )
    report["acceptable_final_evidence"] = not combined_rejections
    report["all_passed"] = not combined_rejections
    return report


def combat_log_transport_attempts(
    payloads: list[dict[str, Any]],
) -> list[tuple[list[dict[str, Any]], dict[str, Any]]]:
    """Split repeated combat-log exports at their completion markers."""
    attempts: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []
    chunks: list[dict[str, Any]] = []
    for row in payloads:
        action = row.get("action")
        if action == "botauto_combatlog_chunk":
            chunks.append(row)
        elif action == "botauto_combatlog_complete":
            attempts.append((chunks, row))
            chunks = []
    if chunks:
        attempts.append((chunks, {}))
    return attempts


def combat_log_attempt_status(
    chunks: list[dict[str, Any]], completion: dict[str, Any]
) -> dict[str, Any]:
    expected = int(
        completion.get("chunk_count")
        or (chunks[-1].get("chunk_count") if chunks else 0)
        or 0
    )
    cohort_id = str(completion.get("cohort_id") or "")
    valid_sequences: list[int] = []
    invalid_sequences: list[int] = []
    for row in chunks:
        try:
            sequence = int(row.get("sequence"))
            chunk_count = int(row.get("chunk_count"))
        except (TypeError, ValueError):
            invalid_sequences.append(-1)
            continue
        valid = (
            expected > 0
            and 0 <= sequence < expected
            and chunk_count == expected
            and str(row.get("cohort_id") or "") == cohort_id
            and int(row.get("combat_log_chunk_schema_version") or 0) == 1
            and row.get("encoding") == "base64"
        )
        (valid_sequences if valid else invalid_sequences).append(sequence)
    unique_sequences = set(valid_sequences)
    missing_sequences = sorted(set(range(expected)) - unique_sequences)
    duplicate_sequences = sorted(
        sequence
        for sequence in unique_sequences
        if valid_sequences.count(sequence) > 1
    )
    complete_marker = bool(completion)
    reassembled = bool(
        complete_marker
        and expected > 0
        and not missing_sequences
        and not duplicate_sequences
        and not invalid_sequences
    )
    if reassembled:
        reason = "complete"
    elif not complete_marker:
        reason = "completion_marker_missing"
    elif missing_sequences:
        reason = "missing_sequences"
    elif duplicate_sequences:
        reason = "duplicate_sequences"
    else:
        reason = "invalid_chunks"
    return {
        "complete_marker": complete_marker,
        "expected_chunks": expected,
        "received_chunks": len(unique_sequences),
        "missing_sequences": missing_sequences,
        "duplicate_sequences": duplicate_sequences,
        "invalid_sequences": sorted(set(invalid_sequences)),
        "total_bytes": int(completion.get("total_bytes") or 0),
        "reason": reason,
        "reassembled": reassembled,
    }


def combat_log_transport_status(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = combat_log_transport_attempts(payloads)
    if not attempts:
        return combat_log_attempt_status([], {})
    statuses = [combat_log_attempt_status(chunks, completion)
        for chunks, completion in attempts]
    selected = next(
        (status for status in reversed(statuses) if status["reassembled"]),
        statuses[-1],
    )
    selected = dict(selected)
    retry_attempts = [
        int(row.get("attempt") or 0)
        for row in payloads
        if row.get("action") == "botauto_combatlog_retry"
    ]
    selected["attempt_count"] = max(
        len(attempts),
        (max(retry_attempts) + 1) if retry_attempts else 0,
    )
    return selected


def combined_combat_log(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    direct = next(
        (
            row
            for row in reversed(payloads)
            if row.get("combat_log_schema_version") or row.get("action") == "botauto_combatlog"
        ),
        {},
    )
    if direct:
        return direct

    for chunks, completion in reversed(combat_log_transport_attempts(payloads)):
        status = combat_log_attempt_status(chunks, completion)
        if not status["reassembled"]:
            continue
        expected = int(status["expected_chunks"])
        by_sequence = {int(row["sequence"]): row for row in chunks}
        try:
            raw = b"".join(
                base64.b64decode(by_sequence[index]["data"], validate=True)
                for index in range(expected)
            )
            decoded = json.loads(raw)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if (
            len(raw) == int(completion.get("total_bytes") or 0)
            and isinstance(decoded, dict)
        ):
            return decoded
    return {}


def combined_trace_payload(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    if not payloads:
        return {}

    combined: dict[str, Any] = {"trace_schema_version": payloads[-1].get("trace_schema_version", 1), "entries": []}
    seen: set[tuple[Any, ...]] = set()

    def add_entry(entry: dict[str, Any], bot_guid: Any = None, bot_name: Any = None, source_slot: int = 0) -> None:
        row = dict(entry)
        if bot_guid is not None and "bot_guid" not in row:
            row["bot_guid"] = bot_guid
        if bot_name is not None and "bot_name" not in row:
            row["bot_name"] = bot_name
        if row.get("sequence") is not None or row.get("timestamp_ms") is not None:
            key = (
                row.get("bot_guid"),
                row.get("sequence"),
                row.get("timestamp_ms"),
                row.get("action"),
                row.get("situation"),
                row.get("result"),
                row.get("target_id"),
            )
        else:
            key = (
                "unsequenced",
                source_slot,
                row.get("bot_guid"),
                row.get("action"),
                row.get("situation"),
                row.get("result"),
                row.get("target_id"),
            )
        if key in seen:
            return
        seen.add(key)
        combined["entries"].append(row)

    for payload in payloads:
        for source_slot, entry in enumerate(payload.get("entries") or []):
            if isinstance(entry, dict):
                add_entry(entry, payload.get("bot_guid"), payload.get("bot_name"), source_slot)
        for bot in payload.get("bots") or []:
            if not isinstance(bot, dict):
                continue
            for source_slot, entry in enumerate(bot.get("entries") or []):
                if isinstance(entry, dict):
                    add_entry(entry, bot.get("bot_guid"), bot.get("bot_name"), source_slot)

    return combined


def command_errors(output: str) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    current_command = ""
    for line in output.splitlines():
        text = line.strip()
        if text.startswith("$ "):
            current_command = text[2:]
        elif "There is no such subcommand" in text:
            errors.append({"command": current_command, "error": "no_such_subcommand"})
    return errors


def should_observe_before_command(command_text: str) -> bool:
    return (
        command_text.startswith(".botauto status")
        or command_text.startswith(".botauto diagnose")
        or command_text.startswith(".botauto trace")
        or command_text == ".botexp summary"
    )


def bot_status_snapshot(output: str) -> dict[str, Any] | None:
    """Return the latest bot status, preserving an explicit inactive state."""
    payloads = parse_json_objects(output)
    for row in reversed(payloads):
        if not isinstance(row, dict):
            continue
        if row.get("action") not in {"botexp_status", "botauto_status"} and not ({"active", "active_bots", "target_bots", "bots"} & set(row)):
            continue
        active_bots = int(row.get("active_bots") or row.get("bots") or row.get("activeBots") or 0)
        target_bots = int(row.get("target_bots") or row.get("targetBots") or 0)
        active_value = row.get("active")
        active = bool(active_value) if active_value is not None else active_bots > 0
        return {"active": active, "active_bots": active_bots, "target_bots": target_bots, "payload": row}
    return None


def bot_status_ready(output: str) -> bool:
    return bot_status_state(output) is True


def bot_status_state(output: str) -> bool | None:
    status = bot_status_snapshot(output)
    if status is None:
        return None
    if not status["active"] or status["active_bots"] <= 0:
        return False
    target_bots = int(status["target_bots"])
    return target_bots <= 0 or int(status["active_bots"]) >= target_bots


def poll_bot_status(
    execute_command: Callable[[str, int], tuple[str, int, bool]],
    deadline: float,
    *,
    status_command: str = ".botauto status",
    poll_sec: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, dict[str, Any] | None, int, bool]:
    """Poll a transport-neutral status command until it is ready or inactive."""
    output_parts = BoundedOutputParts()
    last_status: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        remaining = max(1, int(deadline - time.monotonic()))
        output, returncode, timed_out = execute_command(status_command, remaining)
        output_parts.append(f"$ {status_command}\n")
        output_parts.append(output)
        last_status = bot_status_snapshot(output)
        if returncode != 0 or timed_out or last_status is None or not last_status["active"] or bot_status_state(output) is True:
            return "".join(output_parts), last_status, returncode, timed_out
        sleep(min(poll_sec, max(0.0, deadline - time.monotonic())))
    return "".join(output_parts), last_status, 124, True


def wait_for_soap_command_available(
    execute_command: Callable[[str, int], tuple[str, int, bool]],
    deadline: float,
    *,
    status_command: str = ".botauto status",
    poll_sec: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    output_parts = BoundedOutputParts()
    while time.monotonic() < deadline:
        remaining = max(1, int(deadline - time.monotonic()))
        output, returncode, timed_out = execute_command(status_command, remaining)
        output_parts.extend((f"$ {status_command}\n", output))
        if returncode == 0 and not timed_out and bot_status_snapshot(output) is not None:
            return "".join(output_parts)
        sleep(min(poll_sec, max(0.0, deadline - time.monotonic())))
    raise RuntimeError("timed out waiting for reusable worldserver SOAP readiness")


def wait_for_bot_status_state(
    execute_command: Callable[[str, int], tuple[str, int, bool]],
    expected_active: bool,
    deadline: float,
    *,
    status_command: str = ".botauto status",
    poll_sec: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
    allow_zero_active: bool = False,
) -> tuple[str, dict[str, Any] | None]:
    output_parts = BoundedOutputParts()
    last_status: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        remaining = max(1, int(deadline - time.monotonic()))
        output, returncode, timed_out = execute_command(status_command, remaining)
        output_parts.extend((f"$ {status_command}\n", output))
        status = bot_status_snapshot(output)
        if status is not None:
            last_status = status
            ready = bot_status_state(output) is True or (
                allow_zero_active
                and status["active"]
                and int(status["target_bots"]) == 0
                and int(status["active_bots"]) == 0
            )
            inactive = not status["active"] and int(status["active_bots"]) == 0
            if returncode == 0 and not timed_out and ((expected_active and ready) or (not expected_active and inactive)):
                return "".join(output_parts), status
        sleep(min(poll_sec, max(0.0, deadline - time.monotonic())))
    expected = "active and ready" if expected_active else "inactive with zero active bots"
    raise RuntimeError(f"timed out waiting for BotWorld to become {expected}")


def wait_for_heroic_admission_status(
    execute_command: Callable[[str, int], tuple[str, int, bool]],
    deadline: float,
    *,
    status_command: str = ".botauto status",
    poll_sec: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, dict[str, Any]]:
    """Wait for server-side five-player admission to finish provisioning.

    BotWorld reports the leased roster as active before it has finished the
    route-instance readback and admission receipt commit.  A single status
    sample at that edge is an activation-pending state, not a failed heroic
    run.  Keep polling until the native receipt and action gate are committed.
    """
    output_parts = BoundedOutputParts()
    last_status: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        remaining = max(1, int(deadline - time.monotonic()))
        output, returncode, timed_out = execute_command(status_command, remaining)
        output_parts.extend((f"$ {status_command}\n", output))
        status = bot_status_snapshot(output)
        if status is not None:
            last_status = status
            payload = status["payload"]
            runtime = payload.get("raid_runtime") if isinstance(payload, dict) else None
            runtime = runtime if isinstance(runtime, dict) else {}
            receipt = runtime.get("admission_receipt")
            receipt = receipt if isinstance(receipt, dict) else {}
            committed = (
                status["active"]
                and returncode == 0
                and not timed_out
                and runtime.get("server_provisioning_complete") is True
                and runtime.get("roster_composition_valid") is True
                and runtime.get("bot_actions_enabled") is True
                and int(receipt.get("committed_at_ms") or 0) > 0
                and bool(receipt.get("runtime_profile"))
                and bool(receipt.get("scenario_id"))
                and bool(receipt.get("members"))
            )
            if committed:
                return "".join(output_parts), payload
            if not status["active"] and status["active_bots"] == 0:
                break
        sleep(min(poll_sec, max(0.0, deadline - time.monotonic())))
    raise RuntimeError(
        "timed out waiting for Stonecore 5H admission provisioning/receipt commit"
        + (f"; last_status={last_status!r}" if last_status is not None else "")
    )


def wait_for_bot_status_ready(process: subprocess.Popen[str], deadline: float, max_wait_sec: int = 180) -> str:
    if process.stdin is None:
        return ""
    output = []
    ready_deadline = min(deadline, time.monotonic() + max_wait_sec)
    while process.poll() is None and time.monotonic() < ready_deadline:
        process.stdin.write(".botauto status\n")
        process.stdin.flush()
        chunk = read_until_console_prompt(process, ready_deadline, expected_command_output_marker(".botauto status"))
        output.append("$ .botauto status\n")
        output.append(chunk)
        status_state = bot_status_state(chunk)
        if status_state is True:
            break
        if status_state is None:
            break
        time.sleep(2.0)
    return "".join(output)


def count_trace_entries(trace: dict[str, Any]) -> int:
    entries = trace.get("entries")
    if isinstance(entries, list):
        return len(entries)
    bots = trace.get("bots")
    if isinstance(bots, list):
        return sum(len(bot.get("entries") or []) for bot in bots if isinstance(bot, dict))
    return 0


def trace_entries(trace: dict[str, Any]) -> list[dict[str, Any]]:
    entries = trace.get("entries")
    if isinstance(entries, list):
        return [entry for entry in entries if isinstance(entry, dict)]
    bots = trace.get("bots")
    if isinstance(bots, list):
        rows: list[dict[str, Any]] = []
        for bot in bots:
            if isinstance(bot, dict):
                rows.extend(entry for entry in bot.get("entries") or [] if isinstance(entry, dict))
        return rows
    return []


def route_scope(entry: dict[str, Any]) -> tuple[str, int]:
    node_id = str(entry.get("route_node_id") or "")
    generation = int(entry.get("route_generation") or 0)
    if node_id and generation > 0:
        return node_id, generation
    validation_route = entry.get("validation_route") if isinstance(entry.get("validation_route"), dict) else {}
    return str(validation_route.get("route_node_id") or ""), int(validation_route.get("route_generation") or 0)


def scoped_event_evidence(entries: list[dict[str, Any]], actions: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for entry in entries:
        if str(entry.get("action") or "") not in actions:
            continue
        node_id, generation = route_scope(entry)
        if not node_id or generation <= 0:
            continue
        scope = (node_id, generation)
        if scope in seen:
            continue
        seen.add(scope)
        rows.append({"route_node_id": node_id, "route_generation": generation})
    return rows


def scoped_validation_evidence_counts(entries: list[dict[str, Any]], node_id: str, generation: int) -> dict[str, int]:
    return {
        name: sum(
            1
            for entry in entries
            if route_scope(entry) == (node_id, generation)
            and str(entry.get("action") or entry.get("situation") or "") in actions
        )
        for name, actions in VALIDATION_EVIDENCE_ACTIONS.items()
    }


def forbidden_completion_assists(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for entry in entries:
        action = str(entry.get("action") or "")
        result = str(entry.get("result") or "")
        if action in {"teacher_kill_assist", "validation_route_teacher_assist"} or any(token in result for token in {"teacher_assist", "forced_kill", "force_terminal", "force_damage"}):
            rows.append({"action": action, "result": result})
    return rows


def trace_after(entry: dict[str, Any], reference: dict[str, Any]) -> bool:
    entry_timestamp = int(entry.get("timestamp_ms") or 0)
    reference_timestamp = int(reference.get("timestamp_ms") or 0)
    entry_sequence = int(entry.get("sequence") or 0)
    reference_sequence = int(reference.get("sequence") or 0)
    if entry_timestamp and reference_timestamp:
        if entry_timestamp != reference_timestamp:
            return entry_timestamp > reference_timestamp
        return bool(entry_sequence and reference_sequence and entry_sequence > reference_sequence)
    return bool(entry_sequence and reference_sequence and entry_sequence > reference_sequence)


ROUTE_FAILURE_ACTIONS = {"stuck_detected", "guardrail_repath", "objective_target_lost", "validation_route_target_lost"}
ROUTE_PROGRESS_ACTIONS = {
    "mob_killed",
    "boss_killed",
    "raid_boss_killed",
    "objective_progress",
    "validation_route_pack_terminal",
    "validation_route_terminal",
    "validation_route_segment_advance",
}
ROUTE_PROGRESS_RESOLUTIONS = {"movement_progress", "route_target_combat_progress"}

# These actions indicate that the group is actively engaging a boss.  A
# validation_route_group_heal is useful role evidence, but it is support-only
# activity and must not keep the semantic no-progress watchdog alive.
BOSS_ENGAGEMENT_ACTIONS = {"boss_started", "boss_action", "validation_route_tank_boss"}


def route_failure(entry: dict[str, Any]) -> bool:
    action = str(entry.get("action") or "")
    result = str(entry.get("result") or "")
    return action in ROUTE_FAILURE_ACTIONS or (action == "unstuck" and result in {"failed", "failure"}) or "target_lost" in result


BOSS_ATTEMPT_RESET_ACTIONS = {"death", "repeated_death", "raid_wipe", "instance_reset"}
BOSS_HEALTH_PROGRESS_EPSILON = 1e-6
ROUTE_HEALTH_PROGRESS_KINDS = {"boss", "trash"}


def boss_attempt_reset(entry: dict[str, Any]) -> bool:
    return str(entry.get("action") or "") in BOSS_ATTEMPT_RESET_ACTIONS


def route_health_progress_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return strictly ordered health decreases for boss and trash targets.

    Samples are compared only within one route generation, target identity,
    reset epoch, and monotonic clock domain. The first sample in each group is
    a baseline, while a return to near-full health starts a fresh target
    attempt without counting the reset itself as progress.
    """
    samples: list[tuple[dict[str, Any], tuple[str, int], tuple[str, str, int, int, int], float]] = []
    failures: list[tuple[dict[str, Any], tuple[str, int]]] = []
    for entry in entries:
        if boss_attempt_reset(entry):
            scope = route_scope(entry)
            if scope == ("", 0):
                route_progress = entry.get("route_progress") if isinstance(entry.get("route_progress"), dict) else {}
                route = route_progress.get("route") if isinstance(route_progress.get("route"), dict) else {}
                scope = (str(route.get("node_id") or ""), int(route.get("generation") or 0))
            if scope != ("", 0):
                failures.append((entry, scope))
        route_progress = entry.get("route_progress") if isinstance(entry.get("route_progress"), dict) else {}
        route = route_progress.get("route") if isinstance(route_progress.get("route"), dict) else {}
        target = route_progress.get("target") if isinstance(route_progress.get("target"), dict) else {}
        try:
            node_id = str(route.get("node_id") or "")
            generation = int(route.get("generation") or 0)
            route_kind = str(route.get("kind") or "").lower()
            target_guid = int(target.get("guid") or 0)
            target_entry = int(target.get("entry") or 0)
            health = float(target.get("hp_pct"))
        except (TypeError, ValueError):
            continue
        if (
            route_kind not in ROUTE_HEALTH_PROGRESS_KINDS
            or not node_id
            or generation <= 0
            or target_guid <= 0
            or target_entry <= 0
            or not math.isfinite(health)
            or not 0.0 < health <= 1.0
        ):
            continue
        scope = (node_id, generation)
        samples.append((entry, scope, (route_kind, node_id, generation, target_guid, target_entry), health))

    ordered_groups: dict[tuple[str, tuple[str, str, int, int, int], tuple[int, ...]], list[tuple[dict[str, Any], float]]] = {}
    for entry, scope, target_key, health in samples:
        timestamp = int(entry.get("timestamp_ms") or 0)
        sequence = int(entry.get("sequence") or 0)
        if timestamp:
            clock = "timestamp"
        elif sequence:
            clock = "sequence"
        else:
            continue
        epoch: list[int] = []
        ambiguous = False
        for index, (failure, failure_scope) in enumerate(failures):
            if failure_scope != scope:
                continue
            failure_timestamp = int(failure.get("timestamp_ms") or 0)
            failure_sequence = int(failure.get("sequence") or 0)
            failure_clock = "timestamp" if failure_timestamp else "sequence" if failure_sequence else ""
            if failure_clock != clock:
                continue
            if trace_after(entry, failure):
                epoch.append(index)
            elif not trace_after(failure, entry):
                ambiguous = True
                break
        if not ambiguous:
            ordered_groups.setdefault((clock, target_key, tuple(epoch)), []).append((entry, health))

    progress: list[dict[str, Any]] = []
    for (clock, _target_key, _epoch), rows in ordered_groups.items():
        if clock == "timestamp":
            rows.sort(key=lambda row: (int(row[0].get("timestamp_ms") or 0), int(row[0].get("sequence") or 0)))
        else:
            rows.sort(key=lambda row: int(row[0].get("sequence") or 0))
        best_entry: dict[str, Any] | None = None
        best_health = 0.0
        for entry, health in rows:
            if best_entry is None:
                best_entry, best_health = entry, health
                continue
            if not trace_after(entry, best_entry):
                continue
            if health >= 0.95 and best_health <= 0.90:
                best_entry, best_health = entry, health
                continue
            if health < best_health - BOSS_HEALTH_PROGRESS_EPSILON:
                progress.append(entry)
                best_entry, best_health = entry, health
    return progress


def boss_route_health_progress_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compatibility wrapper for the shared boss/trash health signal."""
    return route_health_progress_entries(entries)


def route_health_progress(entries: list[dict[str, Any]]) -> int:
    return len(route_health_progress_entries(entries))


def boss_route_health_progress(entries: list[dict[str, Any]]) -> int:
    """Compatibility wrapper for the shared boss/trash health signal."""
    return route_health_progress(entries)


def _route_progress_metadata(
    entry: dict[str, Any], route: dict[str, Any]
) -> tuple[str, int, str]:
    """Resolve route identity for a nested progress sample."""
    node_id = str(route.get("node_id") or route.get("route_node_id") or "")
    generation = int(route.get("generation") or route.get("route_generation") or 0)
    route_kind = str(route.get("kind") or route.get("route_kind") or "").lower()
    if node_id and generation > 0 and route_kind:
        return node_id, generation, route_kind

    fallback_node, fallback_generation = route_scope(entry)
    if not node_id:
        node_id = fallback_node
    if generation <= 0:
        generation = fallback_generation
    if not route_kind:
        route_kind = str(entry.get("route_kind") or "").lower()
    validation_route = entry.get("validation_route")
    if isinstance(validation_route, dict):
        if not node_id:
            node_id = str(validation_route.get("node_id") or validation_route.get("route_node_id") or "")
        if generation <= 0:
            generation = int(validation_route.get("generation") or validation_route.get("route_generation") or 0)
        if not route_kind:
            route_kind = str(validation_route.get("kind") or validation_route.get("route_kind") or "").lower()
    return node_id, generation, route_kind


def _route_progress_health(
    candidate: dict[str, Any],
) -> float | None:
    for key in ("hp_pct", "health_pct", "aggregate_hp_pct", "aggregate_health_pct"):
        if key not in candidate:
            continue
        try:
            health = float(candidate.get(key))
        except (TypeError, ValueError):
            return None
        if math.isfinite(health) and 0.0 < health <= 1.0:
            return health
    return None


def _route_health_signal_samples(
    entry: dict[str, Any], order: tuple[int, ...]
) -> list[dict[str, Any]]:
    """Extract attributable target or stable pack health from one payload row."""
    samples: list[dict[str, Any]] = []
    owners: list[dict[str, Any]] = [entry]
    for key in ("diagnosis", "snapshot"):
        owner = entry.get(key)
        if isinstance(owner, dict):
            owners.append(owner)
    for owner in owners:
        route_progress = owner.get("route_progress")
        if not isinstance(route_progress, dict):
            continue
        route = route_progress.get("route")
        route = route if isinstance(route, dict) else {}
        node_id, generation, route_kind = _route_progress_metadata(entry, route)
        if (
            route_kind not in ROUTE_HEALTH_PROGRESS_KINDS
            or not node_id
            or generation <= 0
        ):
            continue

        candidates: list[tuple[str, dict[str, Any]]] = []
        target = route_progress.get("target")
        if isinstance(target, dict):
            candidates.append(("target", target))
        for pack_key in ("engaged_pack", "pack"):
            pack = route_progress.get(pack_key)
            if isinstance(pack, dict):
                candidates.append(("pack", pack))
        targets = route_progress.get("targets")
        if isinstance(targets, list):
            candidates.extend(
                ("target", target)
                for target in targets
                if isinstance(target, dict)
            )

        for identity_kind, candidate in candidates:
            health = _route_progress_health(candidate)
            if health is None:
                continue
            target_guid = int(
                candidate.get("guid")
                or candidate.get("target_guid")
                or candidate.get("id")
                or 0
            )
            target_entry = int(
                candidate.get("entry")
                or candidate.get("target_entry")
                or 0
            )
            if target_guid <= 0 or target_entry <= 0:
                continue
            samples.append(
                {
                    "kind": identity_kind,
                    "route_node_id": node_id,
                    "route_generation": generation,
                    "target_guid": target_guid,
                    "target_entry": target_entry,
                    "hp_pct": health,
                    "order": order,
                }
            )
    return samples


def live_combat_progress_snapshot(
    diagnoses: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    combat_metrics: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return current route-scoped combat samples for heartbeat comparisons.

    The snapshot is intentionally separate from durable evidence counters.  A
    watchdog heartbeat may reset its semantic plateau clock only when a target
    or stable pack has strictly less health, or when the same route's
    cumulative originated damage strictly increases.  Route generation and
    target identity are part of every comparison key.
    """
    reset_epochs: Counter[tuple[str, int]] = Counter()
    for entry in entries:
        if not boss_attempt_reset(entry):
            continue
        scope = route_scope(entry)
        if scope == ("", 0):
            route_progress = entry.get("route_progress")
            route_progress = route_progress if isinstance(route_progress, dict) else {}
            route = route_progress.get("route")
            route = route if isinstance(route, dict) else {}
            node_id, generation, _kind = _route_progress_metadata(entry, route)
            scope = (node_id, generation)
        if scope != ("", 0):
            reset_epochs[scope] += 1

    health_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        for sample in _route_health_signal_samples(entry, (0, index)):
            scope = (sample["route_node_id"], sample["route_generation"])
            sample["attempt_epoch"] = reset_epochs[scope]
            key = (
                sample["kind"],
                sample["route_node_id"],
                sample["route_generation"],
                sample["target_guid"],
                sample["target_entry"],
                sample["attempt_epoch"],
            )
            previous = health_by_key.get(key)
            if previous is None or sample["hp_pct"] <= previous["hp_pct"]:
                health_by_key[key] = sample
    for index, diagnosis in enumerate(diagnoses):
        for sample in _route_health_signal_samples(diagnosis, (1, index)):
            scope = (sample["route_node_id"], sample["route_generation"])
            sample["attempt_epoch"] = reset_epochs[scope]
            key = (
                sample["kind"],
                sample["route_node_id"],
                sample["route_generation"],
                sample["target_guid"],
                sample["target_entry"],
                sample["attempt_epoch"],
            )
            previous = health_by_key.get(key)
            if previous is None or sample["hp_pct"] <= previous["hp_pct"]:
                health_by_key[key] = sample

    metrics_rows: list[dict[str, Any]] = []
    if isinstance(combat_metrics, dict):
        try:
            generation = int(combat_metrics.get("route_generation") or 0)
            party_damage = int(combat_metrics.get("party_damage") or 0)
        except (TypeError, ValueError):
            generation = 0
            party_damage = 0
        node_id = str(combat_metrics.get("route_node_id") or "")
        if (
            combat_metrics.get("schema") == "bot_combat_metrics_v2"
            and combat_metrics.get("available") is True
            and node_id
            and generation > 0
            and party_damage >= 0
        ):
            metrics_rows.append(
                {
                    "route_node_id": node_id,
                    "route_generation": generation,
                    "attempt_epoch": reset_epochs[(node_id, generation)],
                    "party_damage": party_damage,
                }
            )

    def clean(row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items() if key != "order"}

    return {
        "health": [clean(health_by_key[key]) for key in sorted(health_by_key, key=str)],
        "damage": sorted(metrics_rows, key=lambda row: (row["route_node_id"], row["route_generation"])),
    }


def live_combat_progress_advanced(
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> bool:
    """Return true only for strict same-scope live combat advancement."""
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return False

    previous_health = {
        (
            row.get("kind"),
            row.get("route_node_id"),
            int(row.get("route_generation") or 0),
            int(row.get("target_guid") or 0),
            int(row.get("target_entry") or 0),
            int(row.get("attempt_epoch") or 0),
        ): float(row.get("hp_pct"))
        for row in previous.get("health") or []
        if isinstance(row, dict)
    }
    for row in current.get("health") or []:
        if not isinstance(row, dict):
            continue
        key = (
            row.get("kind"),
            row.get("route_node_id"),
            int(row.get("route_generation") or 0),
            int(row.get("target_guid") or 0),
            int(row.get("target_entry") or 0),
            int(row.get("attempt_epoch") or 0),
        )
        try:
            health = float(row.get("hp_pct"))
        except (TypeError, ValueError):
            continue
        if key in previous_health and health < previous_health[key] - BOSS_HEALTH_PROGRESS_EPSILON:
            return True

    previous_damage = {
        (
            row.get("route_node_id"),
            int(row.get("route_generation") or 0),
            int(row.get("attempt_epoch") or 0),
        ): int(row.get("party_damage") or 0)
        for row in previous.get("damage") or []
        if isinstance(row, dict)
    }
    for row in current.get("damage") or []:
        if not isinstance(row, dict):
            continue
        key = (
            row.get("route_node_id"),
            int(row.get("route_generation") or 0),
            int(row.get("attempt_epoch") or 0),
        )
        try:
            damage = int(row.get("party_damage") or 0)
        except (TypeError, ValueError):
            continue
        if key in previous_damage and damage > previous_damage[key]:
            return True
    return False


DEATH_LOOP_ACTIONS = {"repeated_death", "death_loop"}
DEATH_LOOP_DURABLE_PROGRESS_ACTIONS = ROUTE_PROGRESS_ACTIONS | {
    "boss_add_killed",
    "validation_route_pack_complete",
}


def death_loop_scope(entry: dict[str, Any]) -> tuple[str, int]:
    scope = route_scope(entry)
    if scope != ("", 0):
        return scope
    route_progress = entry.get("route_progress") if isinstance(entry.get("route_progress"), dict) else {}
    route = route_progress.get("route") if isinstance(route_progress.get("route"), dict) else {}
    return str(route.get("node_id") or ""), int(route.get("generation") or 0)


def unresolved_route_death_loop_count(entries: list[dict[str, Any]]) -> int:
    progress_entries = boss_route_health_progress_entries(entries) + [
        entry
        for entry in entries
        if str(entry.get("action") or "") in DEATH_LOOP_DURABLE_PROGRESS_ACTIONS
    ]
    unresolved_by_scope: Counter[tuple[str, int]] = Counter()
    seen: set[tuple[Any, ...]] = set()
    for entry in entries:
        if str(entry.get("action") or "") not in DEATH_LOOP_ACTIONS:
            continue
        scope = death_loop_scope(entry)
        if scope == ("", 0):
            continue
        timestamp = int(entry.get("timestamp_ms") or 0)
        sequence = int(entry.get("sequence") or 0)
        if timestamp or sequence:
            key = (
                scope,
                int(entry.get("bot_guid") or 0),
                timestamp,
                sequence,
                str(entry.get("action") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
        if not any(death_loop_scope(progress) == scope and trace_after(progress, entry) for progress in progress_entries):
            unresolved_by_scope[scope] += 1
    return max(unresolved_by_scope.values(), default=0)


def is_route_progress(entry: dict[str, Any], scope: tuple[str, int]) -> bool:
    same_scope = scope == ("", 0) or route_scope(entry) == scope
    return same_scope and (
        str(entry.get("action") or "") in ROUTE_PROGRESS_ACTIONS
        or (
            not str(entry.get("blocked_current_reason") or "")
            and str(entry.get("blocked_resolved_by") or "") in ROUTE_PROGRESS_RESOLUTIONS
        )
    )


def route_failure_resolved(entries: list[dict[str, Any]], failure: dict[str, Any]) -> bool:
    scope = route_scope(failure)
    return any(trace_after(entry, failure) and is_route_progress(entry, scope) for entry in entries)


def progress_after_latest_route_failure(entries: list[dict[str, Any]]) -> bool:
    failures = [entry for entry in entries if route_failure(entry)]
    return all(route_failure_resolved(entries, failure) for failure in failures)


def scripted_activation_wait_pending(entries: list[dict[str, Any]], now_ms: int, max_wait_ms: int = 30000) -> bool:
    unresolved = [
        entry for entry in entries
        if route_failure(entry)
        and route_scope(entry) != ("", 0)
        and not route_failure_resolved(entries, entry)
    ]
    if not unresolved:
        return False
    unresolved_by_scope = Counter(route_scope(entry) for entry in unresolved)
    unscoped_unresolved = sum(
        1 for entry in entries
        if route_failure(entry)
        and route_scope(entry) == ("", 0)
        and not route_failure_resolved(entries, entry)
    )
    max_unresolved = max([unscoped_unresolved, *unresolved_by_scope.values()], default=0)
    if unscoped_unresolved >= max_unresolved:
        return False
    max_scopes = {scope for scope, count in unresolved_by_scope.items() if count == max_unresolved}
    if len(max_scopes) != 1:
        return False
    scope = next(iter(max_scopes))
    latest_failure = max(
        (entry for entry in unresolved if route_scope(entry) == scope),
        key=lambda entry: (int(entry.get("timestamp_ms") or 0), int(entry.get("sequence") or 0)),
    )
    activations = [
        entry for entry in entries
        if route_scope(entry) == scope
        and str(entry.get("action") or "") == "validation_route_activation"
        and int(entry.get("timestamp_ms") or 0) > 0
        and trace_after(entry, latest_failure)
    ]
    return any(
        now_ms >= int(activation.get("timestamp_ms") or 0)
        and now_ms - int(activation.get("timestamp_ms") or 0) <= max_wait_ms
        and route_scope(entry) == scope
        and str(entry.get("action") or "") == "validation_route_target_search"
        and str(entry.get("result") or "") == "target_seen_not_attackable"
        and int(entry.get("target_id") or 0) > 0
        and trace_after(entry, activation)
        for activation in activations
        for entry in entries
    )


def unresolved_route_stuck_count(entries: list[dict[str, Any]]) -> int:
    failures = [entry for entry in entries if route_failure(entry)]
    if not failures:
        return 0
    unresolved_by_scope = Counter(route_scope(failure) for failure in failures if not route_failure_resolved(entries, failure))
    return max(unresolved_by_scope.values(), default=0)


def confirmed_boss_death_event(entry: dict[str, Any]) -> bool:
    return (
        str(entry.get("action") or "") in {"boss_killed", "raid_boss_killed"}
        and str(entry.get("result") or "") in {"ok", "confirmed_unit_death"}
        and int(entry.get("target_id") or 0) > 0
    )


def strict_manifest_evidence(evidence: dict[str, Any], manifest: dict[str, Any]) -> dict[str, list[str]]:
    terminal_scopes = {
        (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        for row in evidence.get("route_terminal_evidence") or []
        if isinstance(row, dict)
    }
    boss_scopes = {
        (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        for row in evidence.get("real_boss_kill_evidence") or []
        if isinstance(row, dict)
    }
    missing_terminals = []
    missing_boss_kills = []
    for generation, route in enumerate(manifest.get("routes") or [], 1):
        if not isinstance(route, dict):
            continue
        node_id = str(route.get("route_node_id") or "")
        expected = (node_id, int(route.get("route_generation") or generation))
        if expected not in terminal_scopes:
            missing_terminals.append(node_id)
        if str(route.get("kind") or "") == "boss" and expected not in boss_scopes:
            missing_boss_kills.append(node_id)
    return {"missing_terminal_route_nodes": missing_terminals, "missing_boss_route_nodes": missing_boss_kills}


def diagnosis_rows(diagnosis: dict[str, Any]) -> list[dict[str, Any]]:
    rows = diagnosis.get("diagnoses") or diagnosis.get("bots") or ([] if not diagnosis else [diagnosis])
    return [row for row in rows if isinstance(row, dict)]


def load_scenario_reports(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.exists():
        return {}
    single_file = path.is_file()
    files = [path] if single_file else sorted(path.glob("*.json"))
    reports: dict[str, dict[str, Any]] = {}
    for report_path in files:
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        scenario_id = str(payload.get("scenario_id") or payload.get("id") or (report_path.stem if single_file else ""))
        if scenario_id:
            reports[scenario_id] = payload
    return reports


def validation_context_from_args(args: argparse.Namespace) -> dict[str, Any]:
    context: dict[str, Any] = {
        "scenario_id": args.validation_scenario_id or "",
        "segment_id": args.validation_segment_id or "",
        "route_node_id": args.validation_route_node_id or "",
        "route_label": args.validation_route_label or "",
        "route_kind": args.validation_route_kind or "",
        "route_step": int(args.validation_route_step or 0),
        "mechanic_profile": args.validation_mechanic_profile or "",
    }
    return {key: value for key, value in context.items() if value not in {"", 0}}


def nested_get(row: dict[str, Any], path: list[str], default: Any = None) -> Any:
    value: Any = row
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    return default if value is None else value


def scenario_bool(report: dict[str, Any], *keys: str) -> bool:
    return any(bool(report.get(key)) for key in keys)


def scenario_int(report: dict[str, Any], *keys: str) -> int:
    values = []
    for key in keys:
        try:
            values.append(int(report.get(key) or 0))
        except (TypeError, ValueError):
            values.append(0)
    return max(values or [0])


def scenario_group_ready(report: dict[str, Any]) -> bool:
    if str(report.get("difficulty") or "") == "heroic_5man":
        return bool(report.get("heroic_admission_verified"))
    return scenario_bool(report, "prepared_group", "group_ready", "provisioning_ready")


@functools.lru_cache(maxsize=1)
def expected_class_spec_runtime_identities() -> dict[str, tuple[int, int]]:
    catalog_path = REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    result: dict[str, tuple[int, int]] = {}
    for target in catalog.get("targets") or []:
        if not isinstance(target, dict):
            continue
        spec = str(target.get("spec_target_id") or "")
        provisioning = target.get("provisioning_bot")
        if not spec or not isinstance(provisioning, dict):
            continue
        try:
            class_id = int(target["class_id"])
            tree_id = int(provisioning["primary_talent_tree_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if class_id > 0 and tree_id > 0 \
                and provisioning.get("class") == class_id \
                and provisioning.get("class_spec") == spec:
            result[spec] = (class_id, tree_id)
    return result


@functools.lru_cache(maxsize=1)
def expected_class_spec_talent_spells() -> dict[str, tuple[int, ...]]:
    catalog_path = REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    result: dict[str, tuple[int, ...]] = {}
    for target in catalog.get("targets") or []:
        if not isinstance(target, dict):
            continue
        spec = str(target.get("spec_target_id") or "")
        provisioning = target.get("provisioning_bot")
        if not spec or not isinstance(provisioning, dict):
            continue
        spells = sorted(
            int(row.get("spell_id") or 0)
            for row in provisioning.get("talents") or []
            if isinstance(row, dict) and int(row.get("spell_id") or 0) > 0
        )
        if spells:
            result[spec] = tuple(spells)
    return result


ALL_SPEC_PET_GUID_BASE = 8_700_000


def _pet_spellbook_sha256(spellbook: tuple[tuple[int, int], ...]) -> str:
    canonical = ";".join(f"{spell_id}:{active}" for spell_id, active in spellbook)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@functools.lru_cache(maxsize=1)
def expected_class_spec_pet_identities() -> dict[str, dict[str, Any]]:
    """Return the exact ordinary-pet identities pinned by all-spec provisioning."""
    catalog_path = REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for target in catalog.get("targets") or []:
        if not isinstance(target, dict):
            continue
        spec = str(target.get("spec_target_id") or "")
        provisioning = target.get("provisioning_bot")
        pet = provisioning.get("pet") if isinstance(provisioning, dict) else None
        if not spec or not isinstance(pet, dict):
            continue
        normalized: list[tuple[int, int]] = []
        valid = True
        for row in pet.get("spells") or []:
            if isinstance(row, bool):
                valid = False
                break
            if isinstance(row, int):
                spell_id, active = row, 1
            elif isinstance(row, dict):
                spell_id = row.get("id")
                active = row.get("active", 1)
                if isinstance(spell_id, bool) or isinstance(active, bool) \
                        or not isinstance(spell_id, int) or not isinstance(active, int):
                    valid = False
                    break
            else:
                valid = False
                break
            if spell_id <= 0 or active < 0 or active > 255:
                valid = False
                break
            normalized.append((spell_id, active))
        try:
            id_offset = pet["id_offset"]
            entry = pet["entry"]
        except KeyError:
            continue
        if isinstance(id_offset, bool) or isinstance(entry, bool) \
                or not isinstance(id_offset, int) or not isinstance(entry, int) \
                or id_offset <= 0 or entry <= 0 or not valid or not normalized:
            continue
        spellbook = tuple(sorted(normalized))
        if len({spell_id for spell_id, _active in spellbook}) != len(spellbook):
            continue
        result[spec] = {
            "pet_id": ALL_SPEC_PET_GUID_BASE + id_offset,
            "pet_entry": entry,
            "spellbook": spellbook,
            "spellbook_sha256": _pet_spellbook_sha256(spellbook),
        }
    return result


@functools.lru_cache(maxsize=1)
def _expected_class_spec_gear_identities_json() -> str:
    """Reconstruct the one exact gear identity declared across pinned catalogs."""
    target_path = REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
    reference_path = REPO_ROOT / "experiments/configs/all_spec_references_cata_p4_v1.json"
    try:
        target_catalog = json.loads(target_path.read_text(encoding="utf-8"))
        reference_catalog = json.loads(reference_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "{}"
    references = {
        str(row.get("spec_target_id") or ""): row
        for row in reference_catalog.get("references") or []
        if isinstance(row, dict) and row.get("spec_target_id")
    }
    result: dict[str, dict[str, Any]] = {}
    for target in target_catalog.get("targets") or []:
        if not isinstance(target, dict):
            continue
        spec = str(target.get("spec_target_id") or "")
        reference = references.get(spec)
        if not spec or not isinstance(reference, dict):
            continue
        try:
            gear_profile_id = canonical_gear_profile_id(target, reference)
            manifest = expected_gear_manifest(gear_profile_id)
        except (Phase8CalibrationNormalizationError, TypeError, ValueError):
            continue
        result[spec] = {
            "gear_profile_id": gear_profile_id,
            "manifest": manifest,
            "manifest_sha256": canonical_sha256(manifest),
        }
    return json.dumps(result, sort_keys=True, separators=(",", ":"))


def expected_class_spec_gear_identities() -> dict[str, dict[str, Any]]:
    """Return an isolated copy so callers cannot mutate the cached authority."""
    return json.loads(_expected_class_spec_gear_identities_json())


@functools.lru_cache(maxsize=1)
def expected_admission_identity_source_sha256() -> str:
    return admission_identity_source_sha256()


def _strict_admission_gear_manifest(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise TypeError
    required_fields = {
        "slot", "item_id", "enchant_id", "reforge_id", "gem_item_ids"
    }
    for row in value:
        if not isinstance(row, dict) or set(row) != required_fields:
            raise TypeError
        scalar_values = (
            row["slot"], row["item_id"], row["enchant_id"], row["reforge_id"]
        )
        if any(isinstance(field, bool) or not isinstance(field, int)
               for field in scalar_values):
            raise TypeError
        gems = row["gem_item_ids"]
        if not isinstance(gems, list) or any(
            isinstance(gem, bool) or not isinstance(gem, int) or gem < 0
            for gem in gems
        ):
            raise TypeError
    return canonical_gear_manifest(value, label="admission_member.gear_manifest")


def validate_heroic_admission_receipt(
    status: dict[str, Any], *, expected_size: int = 5, expected_map_id: int = 725,
    expected_class_specs: list[str] | None = None,
    expected_start: tuple[float, float, float] | None = None,
    expected_route_manifest_sha256: str = "",
    expected_recovery_entrance: tuple[int, int, int] | None = None,
    horizontal_tolerance: float = 5.0, vertical_tolerance: float = 3.0,
) -> dict[str, Any]:
    runtime = status.get("raid_runtime") if isinstance(status.get("raid_runtime"), dict) else {}
    receipt = runtime.get("admission_receipt") if isinstance(runtime.get("admission_receipt"), dict) else {}
    members = receipt.get("members") if isinstance(receipt.get("members"), list) else []
    expected_attempt = int(status.get("attempt_id") or 0)
    expected_group = int(runtime.get("group_guid") or 0)
    expected_instance = int(runtime.get("instance_id") or 0)
    expected_slots = [
        "party_tank_1",
        "party_healer_1",
        "party_dps_1",
        "party_dps_2",
        "party_dps_3",
    ]
    expected_roles_by_slot = {
        "party_tank_1": "tank",
        "party_healer_1": "healer",
        "party_dps_1": "dps",
        "party_dps_2": "dps",
        "party_dps_3": "dps",
    }
    expected_specs_by_slot = dict(zip(expected_slots, expected_class_specs or [], strict=False))
    reasons: list[str] = []
    if expected_start is None or len(expected_route_manifest_sha256) != 64 \
        or expected_recovery_entrance is None:
        reasons.append("expected_admission_contract_missing")
    if str(runtime.get("admission_phase") or "") != "active":
        reasons.append("admission_phase_not_active")
    if not bool(runtime.get("server_provisioning_complete")):
        reasons.append("server_provisioning_incomplete")
    if not bool(runtime.get("bot_actions_enabled")):
        reasons.append("bot_action_gate_closed")
    if not bool(runtime.get("difficulty_matches")):
        reasons.append("heroic_difficulty_readback_mismatch")
    if int(runtime.get("expected_difficulty") or -1) != 1:
        reasons.append("expected_difficulty_not_heroic")
    if int(runtime.get("group_difficulty") or -1) != 1 or int(runtime.get("map_difficulty") or -1) != 1:
        reasons.append("group_or_map_not_heroic")
    if int(runtime.get("expected_size") or 0) != expected_size:
        reasons.append("unexpected_admission_size")
    if int(receipt.get("attempt_id") or 0) != expected_attempt or not expected_attempt:
        reasons.append("admission_attempt_identity_mismatch")
    if str(receipt.get("scenario_id") or "") != "stonecore_5h":
        reasons.append("admission_scenario_identity_mismatch")
    if str(receipt.get("runtime_profile") or "") != "stonecore_5h":
        reasons.append("admission_profile_identity_mismatch")
    if str(receipt.get("identity_catalog_source_sha256") or "").lower() \
            != expected_admission_identity_source_sha256():
        reasons.append("admission_identity_catalog_source_mismatch")
    if str(receipt.get("route_manifest_sha256") or "").lower() != expected_route_manifest_sha256.lower():
        reasons.append("admission_route_manifest_identity_mismatch")
    if expected_recovery_entrance is not None and (
        int(receipt.get("recovery_entrance_area_trigger_id") or 0),
        int(receipt.get("recovery_entrance_source_map_id") or 0),
        int(receipt.get("recovery_entrance_target_map_id") or 0),
    ) != expected_recovery_entrance:
        reasons.append("admission_recovery_entrance_identity_mismatch")
    if int(receipt.get("entrance_map_id") or 0) != expected_map_id:
        reasons.append("admission_entrance_map_identity_mismatch")
    if expected_start is not None:
        try:
            receipt_entrance = (
                float(receipt["entrance_x"]),
                float(receipt["entrance_y"]),
                float(receipt["entrance_z"]),
            )
        except (KeyError, TypeError, ValueError):
            reasons.append("admission_entrance_receipt_missing")
        else:
            if math.hypot(
                receipt_entrance[0] - expected_start[0],
                receipt_entrance[1] - expected_start[1],
            ) > horizontal_tolerance or abs(
                receipt_entrance[2] - expected_start[2]
            ) > vertical_tolerance:
                reasons.append("admission_entrance_position_identity_mismatch")
    if int(receipt.get("profile_generation") or 0) != int(status.get("profile_generation") or 0):
        reasons.append("admission_profile_generation_mismatch")
    if str(receipt.get("profile_content_hash") or "") != str(status.get("profile_content_hash") or ""):
        reasons.append("admission_profile_hash_mismatch")
    if int(receipt.get("leader_guid") or 0) != int(runtime.get("leader_guid") or 0):
        reasons.append("admission_leader_identity_mismatch")
    if not bool(receipt.get("bot_actions_enabled_at_commit")):
        reasons.append("admission_not_committed_before_actions")
    if receipt.get("all_current_gear_matches_admission") is not True:
        reasons.append("admission_current_gear_identity_unverified")
    if len(members) != expected_size:
        reasons.append("admission_member_count_mismatch")

    guids: set[int] = set()
    observed_specs: list[str] = []
    observed_slots: set[str] = set()
    observed_roles_by_slot: dict[str, str] = {}
    observed_specs_by_slot: dict[str, str] = {}
    observed_gear_profiles_by_slot: dict[str, str] = {}
    observed_gear_hashes_by_slot: dict[str, str] = {}
    expected_runtime_identities = expected_class_spec_runtime_identities()
    expected_gear_identities = expected_class_spec_gear_identities()
    for member in members:
        if not isinstance(member, dict):
            reasons.append("invalid_admission_member")
            continue
        guid = int(member.get("guid") or 0)
        if not guid or guid in guids:
            reasons.append("duplicate_or_zero_admission_guid")
        guids.add(guid)
        roster_slot_id = str(member.get("roster_slot_id") or "")
        class_spec = str(member.get("class_spec") or "")
        if not roster_slot_id or roster_slot_id in observed_slots:
            reasons.append("duplicate_or_empty_admission_roster_slot")
        observed_slots.add(roster_slot_id)
        if not class_spec:
            reasons.append("empty_admission_class_spec")
        observed_specs.append(class_spec)
        observed_roles_by_slot[roster_slot_id] = str(member.get("role") or "")
        observed_specs_by_slot[roster_slot_id] = class_spec
        expected_runtime_identity = expected_runtime_identities.get(class_spec)
        if expected_runtime_identity is None:
            reasons.append("unsupported_admission_class_spec")
        else:
            try:
                observed_runtime_identity = (
                    int(member["class_id"]),
                    int(member["primary_talent_tree_id"]),
                )
                active_spec_index = int(member["active_spec_index"])
                active_talent_count = int(member["active_talent_count"])
            except (KeyError, TypeError, ValueError):
                reasons.append("member_runtime_spec_identity_missing")
            else:
                if observed_runtime_identity != expected_runtime_identity:
                    reasons.append("member_runtime_spec_identity_mismatch")
                if active_spec_index not in {0, 1}:
                    reasons.append("member_active_spec_index_invalid")
                if active_talent_count <= 0:
                    reasons.append("member_active_talent_set_empty")
                try:
                    observed_talent_spells = tuple(sorted(
                        int(spell_id) for spell_id in member["active_talent_spell_ids"]
                    ))
                except (KeyError, TypeError, ValueError):
                    reasons.append("member_active_talent_identity_missing")
                else:
                    expected_talent_spells = expected_class_spec_talent_spells().get(class_spec)
                    if expected_talent_spells is None:
                        reasons.append("expected_talent_identity_missing")
                    elif observed_talent_spells != expected_talent_spells \
                            or active_talent_count != len(observed_talent_spells):
                        reasons.append("member_active_talent_identity_mismatch")
        expected_pet_identity = expected_class_spec_pet_identities().get(class_spec)
        if expected_pet_identity is None:
            if member.get("pet_identity_present") is not False \
                    or member.get("pet_id") not in (0, None) \
                    or member.get("pet_entry") not in (0, None) \
                    or member.get("pet_spell_count") not in (0, None) \
                    or member.get("pet_spellbook") not in ([], None) \
                    or member.get("pet_spellbook_sha256") not in ("", None):
                reasons.append("non_hunter_pet_identity_fabricated")
        else:
            if member.get("pet_identity_present") is not True:
                reasons.append("member_hunter_pet_identity_missing")
            try:
                pet_id = member["pet_id"]
                pet_entry = member["pet_entry"]
                pet_spell_count = member["pet_spell_count"]
                raw_pet_spellbook = member["pet_spellbook"]
                pet_spellbook_hash = member["pet_spellbook_sha256"]
                if any(isinstance(value, bool) or not isinstance(value, int)
                       for value in (pet_id, pet_entry, pet_spell_count)):
                    raise TypeError
                if not isinstance(raw_pet_spellbook, list) \
                        or not isinstance(pet_spellbook_hash, str):
                    raise TypeError
                observed_pet_spellbook_rows: list[tuple[int, int]] = []
                for row in raw_pet_spellbook:
                    if not isinstance(row, dict):
                        raise TypeError
                    spell_id = row.get("spell_id")
                    active = row.get("active")
                    if isinstance(spell_id, bool) or isinstance(active, bool) \
                            or not isinstance(spell_id, int) or not isinstance(active, int):
                        raise TypeError
                    observed_pet_spellbook_rows.append((spell_id, active))
                observed_pet_spellbook = tuple(sorted(observed_pet_spellbook_rows))
            except (KeyError, TypeError, ValueError):
                reasons.append("member_hunter_pet_identity_missing")
            else:
                expected_pet_spellbook = expected_pet_identity["spellbook"]
                if pet_id != expected_pet_identity["pet_id"] \
                        or pet_entry != expected_pet_identity["pet_entry"] \
                        or pet_spell_count != len(observed_pet_spellbook) \
                        or observed_pet_spellbook != expected_pet_spellbook:
                    reasons.append("member_hunter_pet_identity_mismatch")
                observed_hash = _pet_spellbook_sha256(observed_pet_spellbook)
                if pet_spellbook_hash.lower() != observed_hash \
                        or pet_spellbook_hash.lower() != expected_pet_identity["spellbook_sha256"]:
                    reasons.append("member_hunter_pet_spellbook_hash_mismatch")
        expected_gear_identity = expected_gear_identities.get(class_spec)
        try:
            gear_profile_id = member["gear_profile_id"]
            gear_item_count = member["gear_item_count"]
            gear_manifest_hash = member["gear_manifest_sha256"]
            current_gear_manifest_hash = member["current_gear_manifest_sha256"]
            current_matches_admission = member[
                "gear_identity_current_matches_admission"
            ]
            if not isinstance(gear_profile_id, str) \
                    or isinstance(gear_item_count, bool) \
                    or not isinstance(gear_item_count, int) \
                    or not isinstance(gear_manifest_hash, str) \
                    or not isinstance(current_gear_manifest_hash, str) \
                    or not isinstance(current_matches_admission, bool):
                raise TypeError
            observed_gear_manifest = _strict_admission_gear_manifest(
                member["gear_manifest"]
            )
        except (KeyError, TypeError, ValueError, Phase8CalibrationNormalizationError):
            reasons.append("member_gear_identity_missing")
        else:
            observed_gear_profiles_by_slot[roster_slot_id] = gear_profile_id
            observed_gear_hashes_by_slot[roster_slot_id] = gear_manifest_hash.lower()
            observed_manifest_hash = canonical_sha256(observed_gear_manifest)
            hashes_are_hex = re.fullmatch(r"[0-9a-f]{64}", gear_manifest_hash.lower()) \
                and re.fullmatch(r"[0-9a-f]{64}", current_gear_manifest_hash.lower())
            if gear_item_count != len(observed_gear_manifest) \
                    or gear_item_count < 16:
                reasons.append("member_gear_identity_missing")
            if expected_gear_identity is None:
                reasons.append("expected_gear_identity_missing")
            else:
                if gear_profile_id != expected_gear_identity["gear_profile_id"]:
                    reasons.append("member_gear_profile_identity_mismatch")
                if observed_gear_manifest != expected_gear_identity["manifest"]:
                    reasons.append("member_gear_manifest_mismatch")
                if not hashes_are_hex \
                        or gear_manifest_hash.lower() != observed_manifest_hash \
                        or gear_manifest_hash.lower() != expected_gear_identity["manifest_sha256"]:
                    reasons.append("member_gear_manifest_hash_mismatch")
            if current_matches_admission is not True \
                    or current_gear_manifest_hash.lower() != gear_manifest_hash.lower():
                reasons.append("member_current_gear_identity_drift")
        if int(member.get("group_guid") or 0) != expected_group or not expected_group:
            reasons.append("admission_group_identity_mismatch")
        if int(member.get("leader_guid") or 0) != int(runtime.get("leader_guid") or 0):
            reasons.append("member_leader_identity_mismatch")
        if int(member.get("map_id") or 0) != expected_map_id:
            reasons.append("admission_map_identity_mismatch")
        if int(member.get("instance_id") or 0) != expected_instance or not expected_instance:
            reasons.append("admission_instance_identity_mismatch")
        if int(member.get("expected_difficulty") or -1) != 1:
            reasons.append("member_expected_difficulty_not_heroic")
        if int(member.get("player_difficulty") or -1) != 1:
            reasons.append("member_player_difficulty_not_heroic")
        if int(member.get("map_difficulty") or -1) != 1:
            reasons.append("member_map_difficulty_not_heroic")
        try:
            spawn_x = float(member["spawn_x"])
            spawn_y = float(member["spawn_y"])
            spawn_z = float(member["spawn_z"])
        except (KeyError, TypeError, ValueError):
            reasons.append("member_spawn_receipt_missing")
        else:
            if expected_start is not None:
                horizontal_distance = math.hypot(
                    spawn_x - expected_start[0], spawn_y - expected_start[1]
                )
                if horizontal_distance > horizontal_tolerance:
                    reasons.append("member_not_provisioned_at_dungeon_entrance")
                if abs(spawn_z - expected_start[2]) > vertical_tolerance:
                    reasons.append("member_not_provisioned_at_dungeon_entrance")
        if not bool(member.get("server_provisioned")):
            reasons.append("member_not_server_provisioned")
        if not bool(member.get("initial_baseline_normalized")):
            reasons.append("member_initial_baseline_not_normalized")
        if not bool(member.get("initial_alive_state_verified")):
            reasons.append("member_initial_alive_state_unverified")
    if observed_slots != set(expected_slots):
        reasons.append("admission_roster_slot_contract_mismatch")
    if observed_roles_by_slot != expected_roles_by_slot:
        reasons.append("admission_role_shape_mismatch")
    if expected_class_specs and observed_specs_by_slot != expected_specs_by_slot:
        reasons.append("admission_class_spec_roster_mismatch")

    unique_reasons = sorted(set(reasons))
    return {
        "verified": not unique_reasons,
        "failure_reasons": unique_reasons,
        "attempt_id": expected_attempt,
        "group_guid": expected_group,
        "map_id": expected_map_id,
        "instance_id": expected_instance,
        "expected_difficulty": 1,
        "member_guids": sorted(guids),
        "class_specs": sorted(observed_specs),
        "roster_slots": sorted(observed_slots),
        "roles_by_slot": dict(sorted(observed_roles_by_slot.items())),
        "class_specs_by_slot": dict(sorted(observed_specs_by_slot.items())),
        "gear_profiles_by_slot": dict(sorted(observed_gear_profiles_by_slot.items())),
        "gear_manifest_sha256_by_slot": dict(sorted(observed_gear_hashes_by_slot.items())),
        "gear_identity_sha256": canonical_sha256({
            "gear_profiles_by_slot": dict(sorted(observed_gear_profiles_by_slot.items())),
            "gear_manifest_sha256_by_slot": dict(sorted(observed_gear_hashes_by_slot.items())),
        }) if observed_gear_hashes_by_slot else "",
        "receipt_sha256": canonical_sha256(receipt) if receipt else "",
    }


def scenario_trash_ready(report: dict[str, Any]) -> bool:
    return scenario_bool(report, "trash_cleared", "trash_passed") or scenario_int(report, "trash_pulls", "trash_kills", "trash_packs_cleared") > 0


def scenario_boss_kills(report: dict[str, Any]) -> int:
    return scenario_int(report, "boss_kills", "raid_boss_kills", "bosses_killed")


def scenario_clear_complete(report: dict[str, Any]) -> bool:
    if not scenario_bool(report, "clear_complete", "all_passed", "scenario_passed"):
        return False
    if not bool(report.get("completion_claim_valid")):
        return False
    mode = str(report.get("completion_evidence_mode") or report.get("scenario_evidence_mode") or "")
    modes = {str(row) for row in (report.get("scenario_evidence_modes") or [])}
    if mode == "route_segment_context" or "route_segment_context" in modes:
        return False
    if report.get("source_segments") and not bool(report.get("strict_completion_evidence")):
        return False
    return True


def scenario_missing(report: dict[str, Any], missing_name: str) -> list[str]:
    return [] if report else [missing_name]


def scenario_stage_missing(stage: str, scenario_reports: dict[str, dict[str, Any]]) -> list[str]:
    stonecore = scenario_reports.get("stonecore_5h") or {}
    bwd = scenario_reports.get("blackwing_descent_10n") or {}
    if stage == "normal_dungeon_trash":
        missing = scenario_missing(stonecore, "stonecore_live_clear_report")
        if stonecore and not scenario_group_ready(stonecore):
            missing.append("prepared_5man_group")
        if stonecore and not scenario_trash_ready(stonecore):
            missing.append("dungeon_trash_evidence")
        return missing
    if stage == "dungeon_boss":
        missing = scenario_missing(stonecore, "stonecore_live_clear_report")
        if stonecore and not scenario_group_ready(stonecore):
            missing.append("prepared_5man_group")
        if stonecore and scenario_boss_kills(stonecore) <= 0:
            missing.append("dungeon_boss_kill_evidence")
        return missing
    if stage == "full_stonecore_clear":
        missing = scenario_missing(stonecore, "stonecore_live_clear_report")
        if stonecore and not scenario_group_ready(stonecore):
            missing.append("prepared_5man_group")
        if stonecore and not scenario_clear_complete(stonecore):
            missing.append("stonecore_full_clear_evidence")
        return missing
    if stage == "raid_trash":
        missing = scenario_missing(bwd, "blackwing_descent_live_clear_report")
        if bwd and not scenario_group_ready(bwd):
            missing.append("prepared_10man_raid")
        if bwd and not scenario_trash_ready(bwd):
            missing.append("raid_trash_evidence")
        return missing
    if stage == "raid_boss":
        missing = scenario_missing(bwd, "blackwing_descent_live_boss_report")
        if bwd and not scenario_group_ready(bwd):
            missing.append("prepared_10man_raid")
        if bwd and scenario_boss_kills(bwd) <= 0:
            missing.append("raid_boss_kill_evidence")
        return missing
    if stage == "full_blackwing_descent_clear":
        missing = scenario_missing(bwd, "blackwing_descent_live_clear_report")
        if bwd and not scenario_group_ready(bwd):
            missing.append("prepared_10man_raid")
        if bwd and not scenario_clear_complete(bwd):
            missing.append("blackwing_descent_full_clear_evidence")
        return missing
    return []


def live_evidence(
    status: dict[str, Any],
    diagnosis: dict[str, Any],
    trace: dict[str, Any],
    summary: dict[str, Any],
    validation_context: dict[str, Any] | None = None,
    raw_output: str = "",
) -> dict[str, Any]:
    entries = trace_entries(trace)
    diagnoses = diagnosis_rows(diagnosis)
    non_spawn_trace_entries = sum(1 for entry in entries if str(entry.get("action") or entry.get("situation") or "") != "bot_spawned")
    decisions = max(int(status.get("decisions") or 0), int(summary.get("decisions") or 0), non_spawn_trace_entries)
    failures = max(int(status.get("failures") or 0), int(summary.get("failures_recorded") or 0))
    duration_seconds = int(status.get("duration_seconds") or 0)
    duration_minutes = float(summary.get("duration_minutes") or 0.0)
    moved_diagnoses = sum(1 for row in diagnoses if bool(nested_get(row, ["snapshot", "movement", "is_moving"], False)) or float(nested_get(row, ["snapshot", "movement", "distance_moved_since_last_decision"], 0) or 0) > 0.0)
    non_wait_diagnoses = sum(1 for row in diagnoses if str(nested_get(row, ["snapshot", "decision", "action"], "wait")) not in {"", "wait"})
    diagnosis_codes = Counter(
        str(nested_get(row, ["diagnosis", "diagnosis_code"], nested_get(row, ["diagnosis_code"], "")))
        for row in diagnoses
        if nested_get(row, ["diagnosis", "diagnosis_code"], nested_get(row, ["diagnosis_code"], ""))
    )
    diagnosis_severities = Counter(
        str(nested_get(row, ["diagnosis", "severity"], nested_get(row, ["severity"], "")))
        for row in diagnoses
        if nested_get(row, ["diagnosis", "severity"], nested_get(row, ["severity"], ""))
    )
    action_names = {
        str(entry.get("action") or entry.get("situation") or "")
        for entry in entries
        if entry.get("action") or entry.get("situation")
    }
    action_counts = Counter(str(entry.get("action") or entry.get("situation") or "") for entry in entries if entry.get("action") or entry.get("situation"))
    result_counts = Counter(str(entry.get("result") or "") for entry in entries if entry.get("result"))
    raw_manifest_complete_count = len(re.findall(r'"action"\s*:\s*"validation_route_manifest_complete"', raw_output or ""))
    if raw_manifest_complete_count:
        action_names.add("validation_route_manifest_complete")
        action_counts["validation_route_manifest_complete"] = max(
            action_counts.get("validation_route_manifest_complete", 0),
            raw_manifest_complete_count,
        )
    diagnosis_result_counts = Counter()
    stuck_events = max(int(status.get("stuck") or 0), int(summary.get("stuck_events") or 0), action_counts.get("stuck_detected", 0))
    unresolved_route_stuck_events = unresolved_route_stuck_count(entries)
    failures = [entry for entry in entries if route_failure(entry)]
    if failures and not any(route_failure_resolved(entries, failure) for failure in failures):
        unresolved_route_stuck_events = max(unresolved_route_stuck_events, stuck_events)
    unstuck_failures = sum(1 for entry in entries if str(entry.get("action") or "") == "unstuck" and str(entry.get("result") or "") in {"failed", "failure"})
    repath_events = result_counts.get("repath", 0)
    quest_acceptance_actions = sum(
        1
        for entry in entries
        if str(entry.get("action") or "").startswith("accept_quest") or str(entry.get("action") or "") == "accept_hub_quests"
    )
    quest_completion_actions = sum(
        1
        for entry in entries
        if str(entry.get("action") or "").startswith("complete_quest")
    )
    hub_acceptance_actions = sum(1 for entry in entries if str(entry.get("action") or "") == "accept_hub_quests")
    teacher_assisted_kills = sum(1 for entry in entries if str(entry.get("action") or "") == "teacher_kill_assist")
    forbidden_assists = forbidden_completion_assists(entries)
    route_terminal_evidence = scoped_event_evidence(entries, {"validation_route_terminal"})
    status_route = status.get("validation_route") if isinstance(status.get("validation_route"), dict) else {}
    terminal_scopes = {(row["route_node_id"], row["route_generation"]) for row in route_terminal_evidence}
    for row in status_route.get("terminal_evidence") or []:
        if not isinstance(row, dict):
            continue
        scope = (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        if not scope[0] or scope[1] <= 0 or scope in terminal_scopes:
            continue
        terminal_scopes.add(scope)
        route_terminal_evidence.append({"route_node_id": scope[0], "route_generation": scope[1]})
    manifest_completion_evidence = scoped_event_evidence(entries, {"validation_route_manifest_complete"})
    if bool(status_route.get("manifest_complete")):
        node_id = str(status_route.get("node_id") or "")
        generation = int(status_route.get("generation") or status_route.get("manifest_count") or 0)
        if node_id and generation > 0:
            manifest_completion_evidence = [{"route_node_id": node_id, "route_generation": generation}]
    real_boss_kill_evidence = scoped_event_evidence(
        [entry for entry in entries if confirmed_boss_death_event(entry)],
        {"boss_killed", "raid_boss_killed"},
    )
    boss_scopes = {(row["route_node_id"], row["route_generation"]) for row in real_boss_kill_evidence}
    for row in status_route.get("boss_death_evidence") or []:
        if not isinstance(row, dict) or not confirmed_boss_death_event({"action": "boss_killed", **row}):
            continue
        scope = (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        if not scope[0] or scope[1] <= 0 or scope in boss_scopes:
            continue
        boss_scopes.add(scope)
        real_boss_kill_evidence.append({"route_node_id": scope[0], "route_generation": scope[1]})
    post_failure_progress = progress_after_latest_route_failure(entries)
    action_names.update(
        str(nested_get(row, ["snapshot", "decision", "action"], ""))
        for row in diagnoses
        if nested_get(row, ["snapshot", "decision", "action"], "")
    )
    diagnosis_action_counts = Counter()
    diagnosis_action_counts = Counter(
        str(nested_get(row, ["snapshot", "decision", "action"], ""))
        for row in diagnoses
        if nested_get(row, ["snapshot", "decision", "action"], "")
    )
    legacy_diagnosis_action_counts = diagnosis_action_counts if not entries else Counter()
    diagnosis_result_counts = Counter(
        str(nested_get(row, ["snapshot", "decision", "result"], ""))
        for row in diagnoses
        if nested_get(row, ["snapshot", "decision", "result"], "")
    )
    def max_diagnosis_evidence(name: str) -> int:
        values: list[int] = []
        for row in diagnoses:
            evidence_rows = nested_get(row, ["diagnosis", "evidence"], [])
            if not isinstance(evidence_rows, list):
                continue
            for item in evidence_rows:
                if not isinstance(item, dict) or str(item.get("name") or "") != name:
                    continue
                value = item.get("value")
                if isinstance(value, bool):
                    values.append(1 if value else 0)
                    continue
                try:
                    values.append(int(value or 0))
                except (TypeError, ValueError):
                    pass
        return max(values, default=0)

    route_no_progress_diagnoses = 0

    def count_route_progress(route_progress: Any) -> None:
        nonlocal route_no_progress_diagnoses
        if not isinstance(route_progress, dict):
            return
        no_progress = route_progress.get("no_progress") if isinstance(route_progress.get("no_progress"), dict) else {}
        try:
            count = int(no_progress.get("count") or 0)
            threshold = int(no_progress.get("threshold") or 0)
        except (TypeError, ValueError):
            return
        if threshold > 0 and count >= threshold:
            route_no_progress_diagnoses += 1

    for row in diagnoses:
        route_progress = nested_get(row, ["diagnosis", "route_progress"], None)
        if not isinstance(route_progress, dict):
            route_progress = nested_get(row, ["snapshot", "route_progress"], None)
        count_route_progress(route_progress)

    for entry in entries:
        count_route_progress(entry.get("route_progress") if isinstance(entry, dict) else None)

    route_combat_progress_diagnoses = boss_route_health_progress(entries)
    live_combat_progress = live_combat_progress_snapshot(
        diagnoses,
        entries,
        diagnosis.get("combat_metrics") if isinstance(diagnosis, dict) else None,
    )

    action_text = " ".join(sorted(action_names)).lower()
    quest_progress = max(int(status.get("quest_objective_progress") or 0), int(summary.get("quest_objective_progress") or 0))
    quests_accepted = max(int(status.get("quests_accepted") or 0), int(summary.get("quests_accepted") or 0), quest_acceptance_actions)
    quests_completed = max(int(status.get("quests_completed") or 0), int(summary.get("quests_completed") or 0), quest_completion_actions)
    kills = max(
        int(status.get("kills") or 0),
        int(summary.get("total_kills") or 0),
        action_counts.get("mob_killed", 0),
        action_counts.get("dungeon_trash_cleared", 0),
    )
    boss_kill_evidence = len(real_boss_kill_evidence)
    trash_action_evidence = sum(
        count
        for action, count in action_counts.items()
        if action in {"trash_action", "trash_heal", "validation_route_trash_action", "dungeon_trash_cleared", "raid_trash_cleared", "mob_killed"}
    )
    trash_action_evidence += sum(
        count
        for action, count in legacy_diagnosis_action_counts.items()
        if action in {"trash_action", "trash_heal", "validation_route_trash_action", "dungeon_trash_cleared", "raid_trash_cleared"}
    )
    validation_route_actions = sum(count for action, count in action_counts.items() if action.startswith("validation_route") or action.startswith("move_to_validation_route"))
    validation_route_actions += sum(count for action, count in legacy_diagnosis_action_counts.items() if action.startswith("validation_route") or action.startswith("move_to_validation_route"))
    trash_route_actions = (
        action_counts.get("trash_action", 0)
        + action_counts.get("validation_route_trash_action", 0)
        + legacy_diagnosis_action_counts.get("trash_action", 0)
        + legacy_diagnosis_action_counts.get("validation_route_trash_action", 0)
    )
    context = validation_context or {}
    route_kill_trash_evidence = kills if str(context.get("route_kind") or "").lower() == "trash" and validation_route_actions > 0 else 0
    trash_pulls = max(
        int(summary.get("trash_pulls") or 0),
        int(summary.get("trash_kills") or 0),
        int(summary.get("trash_packs_cleared") or 0),
        trash_action_evidence,
        route_kill_trash_evidence,
    )
    kill_evidence = kills + teacher_assisted_kills
    gear_upgrades = max(int(status.get("gear_upgrades") or 0), int(summary.get("gear_upgrades") or 0))
    role_assignment_evidence = max(
        int(summary.get("role_assignments") or 0),
        action_counts.get("role_assignment", 0) + action_counts.get("validation_role_assignment", 0) + action_counts.get("raid_role_assignment", 0),
        diagnosis_action_counts.get("role_assignment", 0) + diagnosis_action_counts.get("validation_role_assignment", 0) + diagnosis_action_counts.get("raid_role_assignment", 0),
    )
    group_formation_evidence = max(
        int(summary.get("group_formations") or 0),
        int(summary.get("raid_formations") or 0),
        action_counts.get("party_formed", 0) + action_counts.get("raid_formed", 0) + action_counts.get("validation_group_formed", 0),
        diagnosis_action_counts.get("party_formed", 0) + diagnosis_action_counts.get("raid_formed", 0) + diagnosis_action_counts.get("validation_group_formed", 0),
    )
    target_priority_evidence = max(
        int(summary.get("target_priority_decisions") or 0),
        action_counts.get("target_priority", 0) + action_counts.get("target_switch", 0) + action_counts.get("validation_target_priority", 0) + action_counts.get("raid_add_wave", 0) + action_counts.get("raid_boss_action", 0),
        diagnosis_action_counts.get("target_priority", 0) + diagnosis_action_counts.get("target_switch", 0) + diagnosis_action_counts.get("validation_target_priority", 0) + diagnosis_action_counts.get("raid_add_wave", 0) + diagnosis_action_counts.get("raid_boss_action", 0),
    )
    interrupt_evidence = max(
        int(summary.get("interrupt_success") or 0),
        int(summary.get("assigned_interrupt_success") or 0),
        action_counts.get("interrupt", 0) + action_counts.get("interrupt_success", 0) + action_counts.get("assigned_interrupt_success", 0) + action_counts.get("validation_interrupt", 0) + action_counts.get("raid_interrupt", 0),
        diagnosis_action_counts.get("interrupt", 0) + diagnosis_action_counts.get("interrupt_success", 0) + diagnosis_action_counts.get("assigned_interrupt_success", 0) + diagnosis_action_counts.get("validation_interrupt", 0) + diagnosis_action_counts.get("raid_interrupt", 0),
    )
    healer_assignment_evidence = max(
        int(summary.get("healer_assignments") or 0),
        action_counts.get("healer_assignment", 0) + action_counts.get("validation_route_group_heal", 0) + action_counts.get("trash_heal", 0) + action_counts.get("external_defensive", 0) + action_counts.get("raid_healer_cooldown", 0),
        diagnosis_action_counts.get("healer_assignment", 0) + diagnosis_action_counts.get("validation_route_group_heal", 0) + diagnosis_action_counts.get("trash_heal", 0) + diagnosis_action_counts.get("external_defensive", 0) + diagnosis_action_counts.get("raid_healer_cooldown", 0),
    )
    if str(context.get("route_kind") or "").lower() == "boss":
        healer_assignment_evidence = max(
            healer_assignment_evidence,
            action_counts.get("validation_target_priority", 0) if result_counts.get("assist_tank_focus", 0) > 0 else 0,
            diagnosis_action_counts.get("validation_target_priority", 0) if diagnosis_result_counts.get("assist_tank_focus", 0) > 0 else 0,
        )
    tank_positioning_evidence = max(
        int(summary.get("tank_positioning") or 0),
        action_counts.get("validation_route_tank_boss", 0)
        + action_counts.get("move_to_validation_route_assist_target", 0)
        + action_counts.get("raid_position_anchor", 0)
        + action_counts.get("raid_boss_action", 0)
        + result_counts.get("force_tank_focus", 0)
        + result_counts.get("assist_tank_focus", 0),
        diagnosis_action_counts.get("validation_route_tank_boss", 0)
        + diagnosis_action_counts.get("move_to_validation_route_assist_target", 0)
        + diagnosis_action_counts.get("raid_position_anchor", 0)
        + diagnosis_action_counts.get("raid_boss_action", 0)
        + diagnosis_result_counts.get("force_tank_focus", 0)
        + diagnosis_result_counts.get("assist_tank_focus", 0),
    )
    regrouping_evidence = max(
        int(summary.get("regroups") or 0),
        action_counts.get("validation_route_regroup", 0) + action_counts.get("regroup", 0) + action_counts.get("validation_route_hold_anchor", 0) + action_counts.get("move_to_validation_route_focus", 0) + action_counts.get("raid_position_anchor", 0) + action_counts.get("validation_route_complete", 0),
        diagnosis_action_counts.get("validation_route_regroup", 0) + diagnosis_action_counts.get("regroup", 0) + diagnosis_action_counts.get("validation_route_hold_anchor", 0) + diagnosis_action_counts.get("move_to_validation_route_focus", 0) + diagnosis_action_counts.get("raid_position_anchor", 0) + diagnosis_action_counts.get("validation_route_complete", 0),
    )
    recovery_evidence = max(
        int(summary.get("recovery_events") or 0),
        stuck_events + unstuck_failures + repath_events,
        action_counts.get("validation_route_recovery", 0) + action_counts.get("death", 0) + action_counts.get("dead_recovery", 0) + action_counts.get("raid_wipe", 0),
        diagnosis_action_counts.get("validation_route_recovery", 0) + diagnosis_action_counts.get("death", 0) + diagnosis_action_counts.get("dead_recovery", 0) + diagnosis_action_counts.get("raid_wipe", 0),
    )
    instance_reset_evidence = max(
        int(summary.get("instance_resets") or 0),
        action_counts.get("instance_reset", 0),
        diagnosis_action_counts.get("instance_reset", 0),
    )
    active_decision_evidence = decisions > 0 or non_spawn_trace_entries > 0 or moved_diagnoses > 0 or non_wait_diagnoses > 0
    boss_engagement_actions = sum(
        action_counts.get(action, 0) + legacy_diagnosis_action_counts.get(action, 0)
        for action in BOSS_ENGAGEMENT_ACTIONS
    )
    action_evidence_counts = {
        "party_formation": group_formation_evidence,
        "raid_formation": group_formation_evidence,
        "role_assignments": role_assignment_evidence,
        "pulls": max(trash_pulls, boss_engagement_actions, boss_kill_evidence),
        "target_priority": target_priority_evidence,
        "interrupts": interrupt_evidence,
        "healer_assignments": healer_assignment_evidence,
        "tank_positioning": tank_positioning_evidence,
        "regrouping": regrouping_evidence,
        "recovery": recovery_evidence,
        "instance_reset": instance_reset_evidence,
    }
    return {
        "decisions": decisions,
        "failures": failures,
        "duration_seconds": duration_seconds,
        "duration_minutes": duration_minutes,
        "moved_diagnoses": moved_diagnoses,
        "non_wait_diagnoses": non_wait_diagnoses,
        "diagnosis_codes": dict(sorted(diagnosis_codes.items())),
        "diagnosis_severities": dict(sorted(diagnosis_severities.items())),
        "bot_not_loaded_diagnoses": diagnosis_codes.get("bot_not_loaded", 0),
        "error_diagnoses": diagnosis_severities.get("error", 0),
        "non_spawn_trace_entries": non_spawn_trace_entries,
        "quest_objective_progress": quest_progress,
        "quests_accepted": quests_accepted,
        "quests_completed": quests_completed,
        "hub_acceptance_actions": hub_acceptance_actions,
        "kills": kills,
        "teacher_assisted_kills": teacher_assisted_kills,
        "forbidden_completion_assists": forbidden_assists,
        "kill_evidence": kill_evidence,
        "boss_kill_evidence": boss_kill_evidence,
        "real_boss_kill_evidence": real_boss_kill_evidence,
        "route_terminal_evidence": route_terminal_evidence,
        "manifest_completion_evidence": manifest_completion_evidence,
        "post_failure_progress": post_failure_progress,
        "scripted_activation_wait_pending": scripted_activation_wait_pending(entries, int(time.time() * 1000)),
        "trash_action_evidence": trash_action_evidence,
        "trash_pulls": trash_pulls,
        "gear_upgrades": gear_upgrades,
        "action_names": sorted(action_names),
        "action_counts": dict(sorted(action_counts.items())),
        "result_counts": dict(sorted(result_counts.items())),
        "diagnosis_action_counts": dict(sorted(diagnosis_action_counts.items())),
        "diagnosis_result_counts": dict(sorted(diagnosis_result_counts.items())),
        "role_assignment_evidence": role_assignment_evidence,
        "group_formation_evidence": group_formation_evidence,
        "target_priority_evidence": target_priority_evidence,
        "interrupt_evidence": interrupt_evidence,
        "healer_assignment_evidence": healer_assignment_evidence,
        "tank_positioning_evidence": tank_positioning_evidence,
        "regrouping_evidence": regrouping_evidence,
        "recovery_evidence": recovery_evidence,
        "instance_reset_evidence": instance_reset_evidence,
        "validation_evidence_counts": action_evidence_counts,
        "validation_evidence_ready": {name: count > 0 for name, count in sorted(action_evidence_counts.items())},
        "stuck_events": stuck_events,
        "unresolved_route_stuck_events": unresolved_route_stuck_events,
        "unstuck_failures": unstuck_failures,
        "repath_events": repath_events,
        "validation_route_actions": validation_route_actions,
        "validation_route_manifest_complete": action_counts.get("validation_route_manifest_complete", 0),
        "validation_route_no_progress_diagnoses": route_no_progress_diagnoses,
        "validation_route_combat_progress_diagnoses": route_combat_progress_diagnoses,
        "live_combat_progress": live_combat_progress,
        "unresolved_route_death_loop_events": unresolved_route_death_loop_count(entries),
        "boss_engagement_actions": boss_engagement_actions,
        "trash_route_actions": trash_route_actions,
        "validation_route_prerequisite_repeats": action_counts.get("validation_route_prerequisite", 0),
        "validation_route_activation_attempts": max(
            action_counts.get("validation_route_activation", 0),
            max_diagnosis_evidence("validation_route_activation_attempts"),
        ),
        "validation_route_no_visible_target_activations": result_counts.get("activation_applied_no_visible_target", 0),
        "validation_route_force_tank_focus_repeats": result_counts.get("force_tank_focus", 0),
        "vendor_or_trainer_action": any(token in action_text for token in ["vendor", "repair", "train"]),
        "profession_action": any(token in action_text for token in ["profession", "recipe", "craft"]),
        "material_farming_action": any(token in action_text for token in ["material", "farm", "gather", "herb", "mine", "skin"]),
        "loot_action": any(token in action_text for token in ["loot", "roll", "gear_upgrade"]),
        "active_decision_evidence": active_decision_evidence,
    }


def validation_failure_labels(
    returncode: int,
    timed_out: bool,
    active_bots: int,
    target_bots: int,
    trace_count: int,
    diagnosis_count: int,
    errors: list[dict[str, str]],
    evidence: dict[str, Any],
    max_death_loops: int = DEFAULT_MAX_DEATH_LOOPS,
) -> list[str]:
    labels: list[str] = []
    if timed_out:
        labels.append("worldserver_timeout")
    if returncode != 0:
        labels.append("worldserver_nonzero_return")
    if errors:
        labels.append("bot_command_error")
    if target_bots > 0 and active_bots < target_bots:
        labels.append("bot_pool_underfilled")
    if active_bots > 0 and diagnosis_count <= 0:
        labels.append("missing_diagnosis")
    if active_bots > 0 and trace_count <= 0 and not evidence.get("active_decision_evidence"):
        labels.append("missing_trace")

    boss_kills = int(evidence.get("boss_kill_evidence") or 0)
    kill_evidence = int(evidence.get("kill_evidence") or 0)
    trash_evidence = int(evidence.get("trash_action_evidence") or 0) + int(evidence.get("trash_pulls") or 0)
    route_actions = int(evidence.get("validation_route_actions") or 0)
    boss_engagement = int(evidence.get("boss_engagement_actions") or 0)
    trash_route_actions = int(evidence.get("trash_route_actions") or 0)
    route_no_progress_diagnoses = int(evidence.get("validation_route_no_progress_diagnoses") or 0)
    route_combat_progress_diagnoses = int(evidence.get("validation_route_combat_progress_diagnoses") or 0)
    activation_attempts = int(evidence.get("validation_route_activation_attempts") or 0)
    prerequisite_repeats = int(evidence.get("validation_route_prerequisite_repeats") or 0)
    no_visible_activations = int(evidence.get("validation_route_no_visible_target_activations") or 0)
    force_tank_focus = int(evidence.get("validation_route_force_tank_focus_repeats") or 0)
    unresolved_route_stuck_events = int(evidence.get("unresolved_route_stuck_events") or 0)
    action_counts = evidence.get("action_counts") if isinstance(evidence.get("action_counts"), dict) else {}
    result_counts = evidence.get("result_counts") if isinstance(evidence.get("result_counts"), dict) else {}
    unresolved_death_loop_events = int(evidence.get("unresolved_route_death_loop_events") or 0)
    bot_not_loaded_diagnoses = int(evidence.get("bot_not_loaded_diagnoses") or 0)
    error_diagnoses = int(evidence.get("error_diagnoses") or 0)
    post_failure_progress = bool(evidence.get("post_failure_progress"))
    recovered_route_stuck = (
        action_counts.get("validation_route_recovery", 0) > 0
        and result_counts.get("validation_route_stuck_safe_memory", 0) > 0
        and post_failure_progress
        and (int(evidence.get("kill_evidence") or 0) > 0 or trash_route_actions > 0 or boss_engagement > 0)
    )
    recovered_by_route_progress = (
        post_failure_progress
        and int(evidence.get("moved_diagnoses") or 0) > 0
        and route_no_progress_diagnoses <= 0
        and (int(evidence.get("kill_evidence") or 0) > 0 or trash_route_actions > 0 or boss_engagement > 0)
    )
    recovered_by_active_route_combat = (
        post_failure_progress
        and route_no_progress_diagnoses <= 0
        and (int((evidence.get("diagnosis_codes") or {}).get("normal_combat") or 0) > 0 or route_combat_progress_diagnoses > 0)
        and (int(evidence.get("kill_evidence") or 0) > 0 or trash_evidence > 0 or boss_engagement > 0)
    )

    route_diagnosis_progress = route_actions > 0 and (
        trash_evidence > 0
        or kill_evidence > 0
        or boss_engagement > 0
        or int(evidence.get("moved_diagnoses") or 0) > 0
        or route_combat_progress_diagnoses > 0
    )

    if bot_not_loaded_diagnoses > 0:
        labels.append("bot_lifecycle_not_loaded")
    elif error_diagnoses > 0 and not route_diagnosis_progress:
        labels.append("bot_diagnosis_error")

    if route_actions > 0 and boss_kills <= 0 and trash_route_actions <= 0 and kill_evidence <= 0:
        if boss_engagement > 0:
            labels.append("boss_attempt_no_kill")
        elif activation_attempts > 0:
            labels.append("validation_route_activation_no_engagement")
        else:
            labels.append("validation_route_no_engagement")
    if route_actions > 0 and trash_route_actions > 0 and trash_evidence <= 0:
        labels.append("trash_route_no_engagement")
    if route_actions > 0 and boss_kills <= 0 and trash_route_actions <= 0 and kill_evidence <= 0 and prerequisite_repeats >= 4:
        labels.append("validation_route_prerequisite_loop")
    if route_actions > 0 and boss_kills <= 0 and trash_route_actions <= 0 and kill_evidence <= 0 and no_visible_activations >= 2 and boss_engagement <= 0:
        labels.append("validation_route_activation_target_absent")
    if route_actions > 0 and boss_kills <= 0 and trash_route_actions <= 0 and kill_evidence <= 0 and force_tank_focus >= 4 and boss_engagement <= 0:
        labels.append("validation_route_assist_focus_loop")
    pending_scripted_activation = bool(evidence.get("scripted_activation_wait_pending"))
    if (route_actions > 0
        and not pending_scripted_activation
        and not post_failure_progress
        and unresolved_route_stuck_events >= max(8, active_bots)
        and not recovered_route_stuck
        and not recovered_by_route_progress
        and not recovered_by_active_route_combat):
        labels.append("validation_route_stuck_loop")
    if route_actions > 0 and unresolved_death_loop_events >= max_death_loops:
        labels.append("validation_route_death_loop")
    if route_actions > 0 and route_no_progress_diagnoses > 0:
        labels.append("no_progress_observed")
    if (
        active_bots > 0
        and int(evidence.get("decisions") or 0) > 0
        and int(evidence.get("kill_evidence") or 0) <= 0
        and boss_kills <= 0
        and trash_evidence <= 0
        and int(evidence.get("quest_objective_progress") or 0) <= 0
        and int(evidence.get("quests_accepted") or 0) <= 0
        and int(evidence.get("gear_upgrades") or 0) <= 0
    ):
        labels.append("no_progress_observed")

    unique: list[str] = []
    for label in labels:
        if label not in unique:
            unique.append(label)
    return unique


def progress_counters_from_evidence(evidence: dict[str, Any]) -> dict[str, int]:
    action_counts = evidence.get("action_counts") if isinstance(evidence.get("action_counts"), dict) else {}
    return {
        "decisions": int(evidence.get("decisions") or 0),
        "moved_diagnoses": int(evidence.get("moved_diagnoses") or 0),
        "non_spawn_trace_entries": int(evidence.get("non_spawn_trace_entries") or 0),
        "quest_objective_progress": int(evidence.get("quest_objective_progress") or 0),
        "quests_accepted": int(evidence.get("quests_accepted") or 0),
        "quests_completed": int(evidence.get("quests_completed") or 0),
        "kills": int(evidence.get("kills") or 0),
        "teacher_assisted_kills": int(evidence.get("teacher_assisted_kills") or 0),
        "boss_kill_evidence": int(evidence.get("boss_kill_evidence") or 0),
        "boss_engagement_actions": int(evidence.get("boss_engagement_actions") or 0),
        "trash_pulls": int(evidence.get("trash_pulls") or 0),
        "gear_upgrades": int(evidence.get("gear_upgrades") or 0),
        "validation_route_actions": int(evidence.get("validation_route_actions") or 0),
        "validation_route_terminal_evidence": len(evidence.get("route_terminal_evidence") or []),
        "validation_route_manifest_complete": int(evidence.get("validation_route_manifest_complete") or 0),
        "validation_route_no_progress_diagnoses": int(evidence.get("validation_route_no_progress_diagnoses") or 0),
        "validation_route_combat_progress_diagnoses": int(evidence.get("validation_route_combat_progress_diagnoses") or 0),
        "repeated_decisions": int(action_counts.get("repeated_decision") or action_counts.get("decision_repeated") or 0),
        "death_loop_events": int(evidence.get("unresolved_route_death_loop_events") or 0),
        "stuck_events": int(evidence.get("stuck_events") or 0),
        "repath_events": int(evidence.get("repath_events") or 0),
    }


def watchdog_state(
    evidence: dict[str, Any],
    failure_labels: list[str],
    *,
    heartbeat_sec: int = DEFAULT_COMPLETION_HEARTBEAT_SEC,
    no_progress_window_sec: int = DEFAULT_NO_PROGRESS_WINDOW_SEC,
    max_repeated_decisions: int = DEFAULT_MAX_REPEATED_DECISIONS,
    max_death_loops: int = DEFAULT_MAX_DEATH_LOOPS,
) -> dict[str, Any]:
    counters = progress_counters_from_evidence(evidence)
    # Starting/continuing a boss attempt is activity, but it is not durable
    # progress once the evidence classifies that attempt as having produced no
    # kill.  Counting those repeated actions here lets an endless pull/reset
    # loop keep the completion watchdog alive forever.
    effective_boss_progress = (
        0
        if "boss_attempt_no_kill" in failure_labels
        else counters["boss_engagement_actions"]
    )
    progress_total = (
        counters["quest_objective_progress"]
        + counters["quests_accepted"]
        + counters["quests_completed"]
        + counters["kills"]
        + counters["boss_kill_evidence"]
        + effective_boss_progress
        + counters["gear_upgrades"]
        + counters["validation_route_terminal_evidence"]
        + counters["validation_route_manifest_complete"]
        + counters["validation_route_combat_progress_diagnoses"]
    )
    route_motion_progress = (
        counters["validation_route_actions"] > 0
        and counters["moved_diagnoses"] > 0
        and counters["boss_engagement_actions"] <= 0
    )
    route_terminal_no_progress = counters["validation_route_no_progress_diagnoses"] > 0
    route_semantic_plateau = (
        counters["validation_route_actions"] > 0
        and counters["validation_route_manifest_complete"] <= 0
        and counters["boss_engagement_actions"] <= 0
        and counters["moved_diagnoses"] <= 0
        and counters["validation_route_combat_progress_diagnoses"] <= 0
        and progress_total > 0
    )
    no_progress = (
        route_terminal_no_progress
        or (not route_motion_progress and ("no_progress_observed" in failure_labels or (counters["decisions"] > 0 and progress_total <= 0)))
    )
    repeated_loop = counters["repeated_decisions"] >= max_repeated_decisions
    death_loop = counters["death_loop_events"] >= max_death_loops
    return {
        "policy": "completion-watchdog",
        "heartbeat_sec": heartbeat_sec,
        "no_progress_window_sec": no_progress_window_sec,
        "max_repeated_decisions": max_repeated_decisions,
        "max_death_loops": max_death_loops,
        "progress_total": progress_total,
        "no_progress": no_progress,
        "semantic_progress_plateau": route_semantic_plateau,
        "repeated_decision_loop": repeated_loop,
        "death_loop": death_loop,
        "live_combat_progress": evidence.get("live_combat_progress", {}),
        "progress_counters": counters,
    }


def calibration_pre_scoring_blocker(
    report: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return one exact zero-action warmup blocker, never a DPS inference."""
    calibration = report.get("combat_calibration") or {}
    if not isinstance(calibration, Mapping):
        return None
    if str(calibration.get("phase") or "").lower() in {"scoring", "complete"}:
        return None
    for bot in calibration.get("bots") or []:
        if not isinstance(bot, Mapping) or int(bot.get("attempts") or 0) != 0:
            continue
        diagnostic = bot.get("movement_diagnostic") or {}
        if not isinstance(diagnostic, Mapping):
            continue
        reason = str(diagnostic.get("last_recovery_result") or "")
        if not reason.startswith("persistent_setup_"):
            continue
        return {
            "bot_guid": int(bot.get("guid") or 0),
            "reason": reason,
            "attempts": 0,
        }
    return None


def finalize_calibration_pre_scoring_blocker(
    output_dir: Path,
    report: dict[str, Any],
    blocker: Mapping[str, Any],
) -> None:
    label = "calibration_pre_scoring_blocked"
    report["completion_reason"] = "calibration_pre_scoring_blocker_watchdog"
    report.setdefault("watchdog_state", {})["calibration_pre_scoring_blocker"] = dict(blocker)
    report.setdefault("watchdog_state", {})["calibration_pre_scoring_blocker_repeat_count"] = 3
    if label not in report["failure_labels"]:
        report["failure_labels"].insert(0, label)
    report["failure_reason"] = label
    report["failed"] = max(int(report.get("failed") or 0), 1)
    report["all_passed"] = False
    report["acceptable_final_evidence"] = False
    if "watchdog_failure_is_not_final_evidence" not in report["final_evidence_rejections"]:
        report["final_evidence_rejections"].append("watchdog_failure_is_not_final_evidence")
    finalize_heartbeat(output_dir, report)
    write_json(output_dir / "report.json", report)


def resolved_manifest_failure_labels(
    failure_labels: list[str], evidence: dict[str, Any], manifest: dict[str, Any] | None
) -> list[str]:
    manifest = manifest or {}
    routes = manifest.get("routes") or []
    if not routes or not all(isinstance(route, dict) for route in routes):
        return failure_labels
    final_route = routes[-1]
    final_scope = (
        str(final_route.get("route_node_id") or ""),
        int(final_route.get("route_generation") or len(routes)),
    )
    completion_scopes = {
        (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        for row in evidence.get("manifest_completion_evidence") or []
        if isinstance(row, dict)
    }
    if final_scope[0] == "" or final_scope not in completion_scopes:
        return failure_labels
    strict = strict_manifest_evidence(evidence, manifest)
    if strict["missing_terminal_route_nodes"] or strict["missing_boss_route_nodes"]:
        return failure_labels
    resolved = {
        "boss_attempt_no_kill",
        "no_progress_observed",
        "semantic_progress_plateau",
        "validation_route_assist_focus_loop",
        "validation_route_stuck_loop",
    }
    return [label for label in failure_labels if label not in resolved]


def terminal_failure_labels(failure_labels: list[str], state: dict[str, Any]) -> list[str]:
    counters = state.get("progress_counters") if isinstance(state.get("progress_counters"), dict) else {}
    route_motion_progress = (
        int(counters.get("validation_route_actions") or 0) > 0
        and int(counters.get("moved_diagnoses") or 0) > 0
        and int(counters.get("boss_engagement_actions") or 0) <= 0
        and int(counters.get("trash_pulls") or 0) <= 0
        and int(counters.get("kills") or 0) <= 0
    )
    nonterminal = {
        "boss_attempt_no_kill",
        "bot_pool_underfilled",
        "no_progress_observed",
        "trash_route_no_engagement",
        "validation_route_activation_no_engagement",
        "validation_route_no_engagement",
    }
    if route_motion_progress:
        nonterminal.add("validation_route_assist_focus_loop")
    progress_total = int(state.get("progress_total") or 0)
    if progress_total <= 0 and not route_motion_progress:
        return failure_labels
    return [label for label in failure_labels if label not in nonterminal]


def completion_reason(
    *,
    all_passed: bool,
    returncode: int,
    timed_out: bool,
    failure_labels: list[str],
    state: dict[str, Any],
    evidence: dict[str, Any] | None = None,
) -> str:
    evidence = evidence or {}
    if evidence.get("manifest_completion_evidence") and not terminal_failure_labels(failure_labels, state):
        return "validation_route_manifest_complete"
    if timed_out:
        return "emergency_wall_clock_timeout"
    if returncode != 0:
        return "worldserver_exited_nonzero"
    if all_passed and not failure_labels:
        return "success_predicates_passed"
    if state.get("death_loop"):
        return "death_loop_watchdog"
    if state.get("repeated_decision_loop"):
        return "repeated_decision_watchdog"
    if state.get("no_progress"):
        # This report has observed a no-progress diagnosis, but only the live
        # controller owns the elapsed-time window. It promotes this provisional
        # reason to no_progress_watchdog once the window actually expires.
        return "no_progress_observed"
    if terminal_failure_labels(failure_labels, state):
        return "machine_failure_predicate"
    return "incomplete_evidence"


def final_evidence_rejections(
    *,
    all_passed: bool,
    returncode: int,
    timed_out: bool,
    failure_labels: list[str],
    evidence: dict[str, Any],
    validation_context: dict[str, Any] | None = None,
    validation_route_manifest: dict[str, Any] | None = None,
    completion: str = "",
) -> list[str]:
    context = validation_context or {}
    manifest_complete = bool(evidence.get("manifest_completion_evidence"))
    rejections: list[str] = []
    if not all_passed and not manifest_complete:
        rejections.append("not_all_stages_passed")
    if timed_out:
        rejections.append("timeout_is_not_final_evidence")
    if returncode != 0:
        rejections.append("nonzero_return_is_not_final_evidence")
    if failure_labels:
        rejections.append("failure_labels_present")
    if context.get("segment_id") or context.get("route_node_id"):
        rejections.append("segment_or_route_context_is_debug_only")
    if completion in {"emergency_wall_clock_timeout", "no_progress_watchdog", "repeated_decision_watchdog", "death_loop_watchdog", "calibration_pre_scoring_blocker_watchdog"}:
        rejections.append("watchdog_failure_is_not_final_evidence")
    if evidence.get("forbidden_completion_assists"):
        rejections.append("forced_or_teacher_kill_evidence")
        if int(evidence.get("teacher_assisted_kills") or 0) > 0 and not evidence.get("real_boss_kill_evidence"):
            rejections.append("teacher_assisted_only_evidence")
    if manifest_complete:
        manifest = validation_route_manifest or {}
        if not manifest.get("routes"):
            rejections.append("missing_validation_route_manifest")
        else:
            strict = strict_manifest_evidence(evidence, manifest)
            if strict["missing_terminal_route_nodes"]:
                rejections.append("missing_node_terminal_evidence")
            if strict["missing_boss_route_nodes"]:
                rejections.append("missing_real_boss_kill_evidence")
    return list(dict.fromkeys(rejections))


def attach_stonecore_role_quality_audit(
    report: dict[str, Any],
    validation_context: dict[str, Any] | None,
    validation_route_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    """Attach the role audit without overriding an authoritative Stonecore clear."""
    context = validation_context or {}
    manifest = validation_route_manifest or {}
    is_full_stonecore = (
        context.get("scenario_id") in {"stonecore_5n", "stonecore_5h"}
        and bool(manifest.get("routes"))
        and not context.get("segment_id")
        and not context.get("route_node_id")
    )
    if not is_full_stonecore:
        return report

    source = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    audit = build_audit(report, hashlib.sha256(source).hexdigest())
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    routes = [route for route in (manifest.get("routes") or []) if isinstance(route, dict)]
    boss_routes = [route for route in routes if str(route.get("kind") or "") == "boss"]
    strict = strict_manifest_evidence(evidence, manifest)
    watchdog = report.get("watchdog_state") if isinstance(report.get("watchdog_state"), dict) else {}
    authoritative_boss_clear = (
        len(routes) == 14
        and len(boss_routes) == 4
        and bool(evidence.get("manifest_completion_evidence"))
        and not strict["missing_terminal_route_nodes"]
        and not strict["missing_boss_route_nodes"]
        and not evidence.get("forbidden_completion_assists")
        and int(report.get("returncode") or 0) == 0
        and not bool(report.get("timed_out"))
        and not watchdog.get("death_loop")
        and not watchdog.get("repeated_decision_loop")
        and str(report.get("completion_reason") or "") != "no_progress_watchdog"
    )
    audit["enforcement"] = "advisory" if authoritative_boss_clear else "required"
    audit["authoritative_boss_clear"] = authoritative_boss_clear
    report["role_efficiency_audit"] = audit
    if audit.get("passed"):
        return report

    if authoritative_boss_clear:
        report["role_quality_advisory_labels"] = [
            f"role_quality:{label}" for label in (audit.get("failure_labels") or [])
        ]
        return report

    labels = list(report.get("failure_labels") or [])
    for label in audit.get("failure_labels") or []:
        quality_label = f"role_quality:{label}"
        if quality_label not in labels:
            labels.append(quality_label)
    if "stonecore_role_quality_audit_failed" not in labels:
        labels.append("stonecore_role_quality_audit_failed")
    report["failure_labels"] = labels
    report["failure_reason"] = labels[0]
    rejections = list(report.get("final_evidence_rejections") or [])
    for rejection in ("failure_labels_present", "stonecore_role_quality_audit_failed"):
        if rejection not in rejections:
            rejections.append(rejection)
    report["final_evidence_rejections"] = rejections
    report["acceptable_final_evidence"] = False
    report["all_passed"] = False
    report["failed"] = max(1, int(report.get("failed") or 0))
    report["completion_reason"] = "stonecore_role_quality_audit_failed"
    return report


def live_validation_report(
    output: str,
    stages: list[str] | None = None,
    returncode: int = 0,
    timed_out: bool = False,
    command: list[str] | None = None,
    scenario_reports: dict[str, dict[str, Any]] | None = None,
    validation_context: dict[str, Any] | None = None,
    validation_route_manifest: dict[str, Any] | None = None,
    duration_policy: str = "completion-watchdog",
    heartbeat_sec: int = DEFAULT_COMPLETION_HEARTBEAT_SEC,
    no_progress_window_sec: int = DEFAULT_NO_PROGRESS_WINDOW_SEC,
    max_repeated_decisions: int = DEFAULT_MAX_REPEATED_DECISIONS,
    max_death_loops: int = DEFAULT_MAX_DEATH_LOOPS,
) -> dict[str, Any]:
    payloads = parse_json_objects(output)
    classified = classify_payloads(payloads)
    errors = command_errors(output)
    diagnosis = classified["diagnosis"]
    trace = classified["trace"]
    status = classified["status"]
    summary = classified["summary"]
    combat_log = classified["combat_log"]
    combat_log_transport = classified["combat_log_transport"]
    combat_calibration_transport = classified["combat_calibration_transport"]
    combat_calibration = enrich_combat_calibration_reference(classified["combat_calibration"])
    combat_analysis = analyze_combat_log(combat_log) if combat_log else {}

    active_bots = int(status.get("active_bots") or status.get("bots") or status.get("activeBots") or 0)
    target_bots = int(status.get("target_bots") or status.get("targetBots") or 0)
    trace_entries = count_trace_entries(trace)
    diagnosis_count = len(diagnosis_rows(diagnosis))
    evidence = live_evidence(status, diagnosis, trace, summary, validation_context, output)
    failure_labels = validation_failure_labels(
        returncode,
        timed_out,
        active_bots,
        target_bots,
        trace_entries,
        diagnosis_count,
        errors,
        evidence,
        max_death_loops,
    )
    if (
        combat_log_transport.get("complete_marker")
        and not combat_log_transport.get("reassembled")
    ):
        failure_labels.append("combat_log_transport_incomplete")
    if WORLDSERVER_OUTPUT_TRUNCATED_MARKER.strip() in output:
        failure_labels.append("worldserver_output_truncated")
    scenario_reports = scenario_reports or {}

    stage_rows = []
    for stage in stages or DEFAULT_STAGES:
        missing: list[str] = []
        if stage in {"movement_smoke", "kill_quest", "collect_quest", "quest_hub_batching", "trainer_visit", "vendor_repair", "profession_recipe_acquisition", "material_farming", "smart_loot"}:
            if active_bots <= 0:
                missing.append("active_autonomy_bots")
            if not diagnosis:
                missing.append("botauto_diagnose_json")
            if trace_entries <= 0:
                missing.append("botauto_trace_entries")
            if not evidence["active_decision_evidence"]:
                missing.append("active_decision_or_movement_evidence")
            if stage == "kill_quest" and evidence["kill_evidence"] <= 0:
                missing.append("kill_evidence")
            if stage in {"normal_dungeon_trash", "dungeon_boss"} and evidence["kills"] <= 0:
                missing.append("kill_evidence")
            if stage == "collect_quest" and evidence["quest_objective_progress"] <= 0 and evidence["quests_completed"] <= 0:
                missing.append("quest_progress_evidence")
            if stage == "quest_hub_batching" and evidence["quests_accepted"] <= 0:
                missing.append("quest_acceptance_evidence")
            if stage == "quest_hub_batching" and evidence["hub_acceptance_actions"] <= 0:
                missing.append("accept_hub_quests_action_evidence")
            if stage in {"trainer_visit", "vendor_repair"} and not evidence["vendor_or_trainer_action"]:
                missing.append("vendor_or_trainer_action_evidence")
            if stage == "profession_recipe_acquisition" and not evidence["profession_action"]:
                missing.append("profession_or_recipe_action_evidence")
            if stage == "material_farming" and not evidence["material_farming_action"]:
                missing.append("material_farming_action_evidence")
            if stage == "smart_loot" and evidence["gear_upgrades"] <= 0 and not evidence["loot_action"]:
                missing.append("loot_or_gear_upgrade_evidence")
        elif stage in {"normal_dungeon_trash", "dungeon_boss", "full_stonecore_clear", "raid_trash", "raid_boss", "full_blackwing_descent_clear"}:
            missing.extend(scenario_stage_missing(stage, scenario_reports))
        stage_rows.append({"stage": stage, "passed": not missing, "missing": missing})

    passed = sum(1 for row in stage_rows if row["passed"])
    all_passed = passed == len(stage_rows)
    state = watchdog_state(
        evidence,
        failure_labels,
        heartbeat_sec=heartbeat_sec,
        no_progress_window_sec=no_progress_window_sec,
        max_repeated_decisions=max_repeated_decisions,
        max_death_loops=max_death_loops,
    )
    effective_failure_labels = resolved_manifest_failure_labels(
        failure_labels, evidence, validation_route_manifest
    )
    reason = completion_reason(
        all_passed=all_passed,
        returncode=returncode,
        timed_out=timed_out,
        failure_labels=effective_failure_labels,
        state=state,
        evidence=evidence,
    )
    rejections = final_evidence_rejections(
        all_passed=all_passed,
        returncode=returncode,
        timed_out=timed_out,
        failure_labels=effective_failure_labels,
        evidence=evidence,
        validation_context=validation_context,
        validation_route_manifest=validation_route_manifest,
        completion=reason,
    )
    report = {
        "schema": "bot_live_validation_report_v1",
        "command": command or [],
        "duration_policy": duration_policy,
        "returncode": returncode,
        "timed_out": timed_out,
        "json_payloads": len(payloads),
        "active_bots": active_bots,
        "target_bots": target_bots,
        "diagnosis_count": diagnosis_count,
        "trace_entries": trace_entries,
        "status": status,
        "diagnosis": diagnosis,
        "trace": trace,
        "summary": summary,
        "combat_log": combat_log,
        "combat_log_transport": combat_log_transport,
        "combat_calibration": combat_calibration,
        "combat_calibration_transport": combat_calibration_transport,
        "combat_analysis": combat_analysis,
        "scenario_reports": scenario_reports,
        "validation_context": validation_context or {},
        "validation_route_manifest": validation_route_manifest or {},
        "command_errors": errors,
        "evidence": evidence,
        "progress_counters": state["progress_counters"],
        "watchdog_state": state,
        "completion_reason": reason,
        "acceptable_final_evidence": not rejections,
        "final_evidence_rejections": rejections,
        "failure_labels": effective_failure_labels,
        "superseded_failure_labels": [label for label in failure_labels if label not in effective_failure_labels],
        "failure_reason": effective_failure_labels[0] if effective_failure_labels else None,
        "stages": stage_rows,
        "passed": passed,
        "failed": len(stage_rows) - passed,
        "all_passed": all_passed,
        "runtime_ml_control": "offline_shadow_only",
        "control_eligible": False,
    }
    return apply_acceptance_evaluation(report)


def read_until_console_prompt(
    process: subprocess.Popen[str],
    deadline: float,
    required_text: str = "",
    terminal_marker: bool = False,
) -> str:
    if process.stdout is None:
        return ""
    output: list[str] = []
    fd = process.stdout.fileno()
    pre_marker_prompt_at: float | None = None
    while process.poll() is None and time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        ready, _, _ = select.select([fd], [], [], min(1.0, remaining))
        if not ready:
            if (
                required_text
                and pre_marker_prompt_at is not None
                and time.monotonic() - pre_marker_prompt_at >= PRE_MARKER_PROMPT_GRACE_SEC
            ):
                break
            continue
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        text = chunk.decode(errors="replace")
        output.append(text)
        joined = "".join(output)
        if required_text:
            marker_index = joined.find(required_text)
            if marker_index >= 0 and (
                terminal_marker or "TC>" in joined[marker_index + len(required_text):]
            ):
                break
            # A prompt before the required marker can be the console echo for
            # the command that is still streaming.  Ignore it and wait for a
            # prompt after the marker so the next command cannot interleave
            # with this response.  If the marker never arrives, the bounded
            # read returns incomplete output and the parser fails closed.
            if marker_index < 0:
                prompt_positions = [match.start() for match in re.finditer("TC>", joined)]
                if prompt_positions:
                    if pre_marker_prompt_at is None:
                        pre_marker_prompt_at = time.monotonic()
                    elif len(prompt_positions) > 1:
                        break
                if (
                    pre_marker_prompt_at is not None
                    and time.monotonic() - pre_marker_prompt_at >= PRE_MARKER_PROMPT_GRACE_SEC
                ):
                    break
        if not required_text and ("TC>" in text or "TC>" in joined[-16:]):
            break
    return "".join(output)


def drain_available_process_output(
    process: subprocess.Popen[str],
    output_parts: BoundedOutputParts,
    *,
    wait_sec: float = 0.0,
    max_bytes: int = MAX_WORLDSERVER_DRAIN_BYTES_PER_WAKE,
) -> int:
    """Drain unsolicited child output without crossing a command boundary."""
    if process.stdout is None or max_bytes <= 0:
        return 0
    try:
        fd = process.stdout.fileno()
        ready, _, _ = select.select([fd], [], [], max(0.0, wait_sec))
    except (OSError, ValueError):
        return 0
    if not ready:
        return 0

    drained = 0
    while drained < max_bytes:
        try:
            chunk = os.read(fd, min(4096, max_bytes - drained))
        except (BlockingIOError, OSError):
            break
        if not chunk:
            break
        output_parts.append(chunk.decode(errors="replace"))
        drained += len(chunk)
        if drained >= max_bytes:
            break
        try:
            ready, _, _ = select.select([fd], [], [], 0.0)
        except (OSError, ValueError):
            break
        if not ready:
            break
    return drained


def bounded_console_deadline(deadline: float, max_wait_sec: int | float) -> float:
    return min(deadline, time.monotonic() + max(1.0, float(max_wait_sec)))


def expected_command_output_marker(command_text: str) -> str:
    if command_text.startswith(".botauto status"):
        return '"target_bots"'
    if command_text.startswith(".botauto diagnose"):
        return '"diagnosis_schema_version"'
    if command_text.startswith(".botauto trace"):
        return '"trace_schema_version"'
    if command_text.startswith(".botauto combatlog"):
        return '"action":"botauto_combatlog_complete"'
    if command_text == ".botexp summary":
        return '"duration_minutes"'
    if command_text.startswith(".botauto calibrate") and command_text.split()[-1] == "status":
        return '"action":"botauto_calibrate_status_complete"'
    if command_text.startswith(".botauto calibrate"):
        return '"action":"botauto_calibrate_'
    return ""


def command_output_marker_is_terminal(command_text: str) -> bool:
    return (
        command_text.startswith(".botauto combatlog")
        or (
            command_text.startswith(".botauto calibrate")
            and command_text.split()[-1] == "status"
        )
    )


def run_worldserver(binary: Path, config: Path, timeout_sec: int, script: str, observe_sec: int = 0) -> tuple[str, int, bool, list[str]]:
    command = [str(binary), "--config", str(config)]
    if observe_sec > 0:
        deadline = time.monotonic() + timeout_sec
        explicit_start = any(line.strip().startswith(".botauto start") for line in script.splitlines())
        calibration_start = any(
            is_calibration_start_command(line)
            for line in script.splitlines()
        )
        observed_autostart = False
        output_prefix = ""
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdin is not None
        try:
            output_prefix += read_until_console_prompt(process, deadline)
            waited_for_ready = False
            for raw_command in script.splitlines():
                command_text = raw_command.strip()
                if not explicit_start and not calibration_start and not observed_autostart and should_observe_before_command(command_text):
                    if not waited_for_ready:
                        output_prefix += wait_for_bot_status_ready(process, deadline)
                        waited_for_ready = True
                    time.sleep(observe_sec)
                    observed_autostart = True
                process.stdin.write(raw_command + "\n")
                process.stdin.flush()
                if command_text.startswith(".botauto start"):
                    output_prefix += read_until_console_prompt(process, deadline)
                    if not waited_for_ready:
                        output_prefix += wait_for_bot_status_ready(process, deadline)
                        waited_for_ready = True
                    if not calibration_start:
                        time.sleep(observe_sec)
                elif is_calibration_start_command(command_text):
                    output_prefix += read_until_console_prompt(
                        process,
                        bounded_console_deadline(deadline, 10),
                        expected_command_output_marker(command_text),
                    )
                    time.sleep(observe_sec)
                elif command_text.startswith("server shutdown") or command_text == "server exit":
                    if process.stdin and not process.stdin.closed:
                        process.stdin.close()
                        process.stdin = None
                    shutdown_deadline = min(deadline, time.monotonic() + 10)
                    while process.poll() is None and time.monotonic() < shutdown_deadline:
                        time.sleep(0.25)
                    killed_after_shutdown = False
                    if process.poll() is None:
                        process.kill()
                        killed_after_shutdown = True
                    break
                elif command_text:
                    command_deadline = bounded_console_deadline(deadline, 10) if command_text.startswith(".botauto calibrate") else deadline
                    output_prefix += read_until_console_prompt(
                        process,
                        command_deadline,
                        expected_command_output_marker(command_text),
                        command_output_marker_is_terminal(command_text),
                    )
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
                process.stdin = None
            remaining = max(1, int(deadline - time.monotonic()))
            output, _ = process.communicate(timeout=remaining)
            returncode = 0 if locals().get("killed_after_shutdown", False) else (process.returncode if process.returncode is not None else 0)
            return output_prefix + output, returncode, False, command
        except (BrokenPipeError, subprocess.TimeoutExpired) as exc:
            process.kill()
            output = (exc.stdout or "") if isinstance(exc, subprocess.TimeoutExpired) else ""
            if not output and process.stdout:
                output = process.stdout.read()
            return output_prefix + output, 124, True, command

    try:
        completed = subprocess.run(command, input=script, text=True, capture_output=True, timeout=timeout_sec, check=False)
        return completed.stdout + completed.stderr, completed.returncode, False, command
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return output, 124, True, command


def heartbeat_commands_from_script(script: str) -> tuple[list[str], list[str], list[str]]:
    startup: list[str] = []
    heartbeat: list[str] = []
    cleanup: list[str] = []
    for raw_command in script.splitlines():
        command_text = raw_command.strip()
        if not command_text:
            continue
        if command_text.startswith(".botauto start") or (
            is_calibration_start_command(command_text)
        ):
            startup.append(command_text)
        elif command_text.startswith(".botauto combatlog") or (
            command_text.startswith(".botauto calibrate") and command_text.endswith(" stop")
        ) or command_text.startswith(".botauto stop"):
            cleanup.append(command_text)
        elif command_text.startswith("server shutdown") or command_text == "server exit":
            continue
        else:
            heartbeat.append(command_text)
    return startup, heartbeat, cleanup


def rolling_heartbeat_report(
    output_dir: Path,
    heartbeat_index: int,
    output: str,
    returncode: int,
    timed_out: bool,
    command: list[str],
    scenario_reports: dict[str, dict[str, Any]],
    validation_context: dict[str, Any],
    duration_policy: str,
    heartbeat_sec: int,
    no_progress_window_sec: int,
    max_repeated_decisions: int,
    max_death_loops: int,
    validation_route_manifest: dict[str, Any] | None = None,
    completion_reason_override: str = "",
) -> dict[str, Any]:
    report = live_validation_report(
        output,
        returncode=returncode,
        timed_out=timed_out,
        command=command,
        scenario_reports=scenario_reports,
        validation_context=validation_context,
        validation_route_manifest=validation_route_manifest,
        duration_policy=duration_policy,
        heartbeat_sec=heartbeat_sec,
        no_progress_window_sec=no_progress_window_sec,
        max_repeated_decisions=max_repeated_decisions,
        max_death_loops=max_death_loops,
    )
    if completion_reason_override:
        report["completion_reason"] = completion_reason_override
    report["heartbeat_index"] = heartbeat_index
    report["heartbeat_generated_at_unix"] = int(time.time())
    append_heartbeat(output_dir, report)
    write_json(output_dir / "report.json", report)
    return report


def combat_log_export_complete(output: str) -> bool:
    status = combat_log_transport_status(parse_json_objects(output))
    return bool(status.get("reassembled"))


def combat_log_retry_receipt(output: str, attempt: int) -> str:
    status = combat_log_transport_status(parse_json_objects(output))
    return json.dumps(
        {
            "action": "botauto_combatlog_retry",
            "attempt": attempt,
            "expected_chunks": int(status.get("expected_chunks") or 0),
            "received_chunks": int(status.get("received_chunks") or 0),
            "missing_sequences": status.get("missing_sequences") or [],
            "reason": str(status.get("reason") or "incomplete"),
        },
        separators=(",", ":"),
    ) + "\n"


def run_transport_completion_watchdog(
    execute_command: Callable[[str, int], tuple[str, int, bool]],
    command: list[str],
    timeout_sec: int | None,
    script: str,
    output_dir: Path,
    scenario_reports: dict[str, dict[str, Any]],
    validation_context: dict[str, Any],
    *,
    validation_route_manifest: dict[str, Any] | None = None,
    duration_policy: str = "completion-watchdog",
    heartbeat_sec: int = DEFAULT_COMPLETION_HEARTBEAT_SEC,
    no_progress_window_sec: int = DEFAULT_NO_PROGRESS_WINDOW_SEC,
    max_repeated_decisions: int = DEFAULT_MAX_REPEATED_DECISIONS,
    max_death_loops: int = DEFAULT_MAX_DEATH_LOOPS,
    status_command: str = ".botauto status",
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, int, bool, list[str]]:
    """Apply completion evidence watchdog policy to any command transport.

    The callback owns connection and lifecycle details; this function never sends a
    server shutdown command, making it safe for attached sessions and SOAP.
    """
    deadline = (
        None if timeout_sec is None else time.monotonic() + timeout_sec
    )
    startup_commands, heartbeat_commands, cleanup_commands = heartbeat_commands_from_script(script)
    output_parts = WatchdogOutputBuffer(heartbeat_commands=heartbeat_commands)
    heartbeat_index = 0
    last_progress_total = -1
    last_progress_at = time.monotonic()
    last_live_combat_progress: dict[str, Any] | None = None
    last_calibration_blocker = ""
    calibration_blocker_repeats = 0

    def send(command_text: str) -> tuple[int, bool]:
        remaining = (
            max(30, int(no_progress_window_sec))
            if deadline is None
            else max(1, int(deadline - time.monotonic()))
        )
        attempts = 2 if command_text.startswith(".botauto combatlog") else 1
        output = ""
        returncode = 0
        timed_out = False
        for attempt in range(1, attempts + 1):
            output, returncode, timed_out = execute_command(command_text, remaining)
            command_output = f"$ {command_text}\n"
            if (
                returncode != 0
                or timed_out
                or attempts == 1
                or combat_log_export_complete(output)
                or attempt == attempts
            ):
                command_output += output
                if command_text in cleanup_commands:
                    output_parts.append_cleanup(command_output)
                elif command_text in heartbeat_commands:
                    output_parts.append_heartbeat(command_text, command_output)
                else:
                    output_parts.append(command_output)
                break
            output_parts.append_cleanup(
                command_output + combat_log_retry_receipt(output, attempt)
            )
        if returncode == 0 and is_calibration_start_command(command_text):
            rejected = any(
                row.get("action") == "botauto_calibrate_start"
                and row.get("ok") is False
                for row in parse_json_objects(output)
            )
            if rejected:
                return 1, timed_out
        return returncode, timed_out

    def finish(returncode: int, timed_out: bool) -> tuple[str, int, bool, list[str]]:
        if not timed_out:
            for command_text in cleanup_commands:
                cleanup_returncode, cleanup_timed_out = send(command_text)
                if cleanup_returncode != 0 or cleanup_timed_out:
                    return output_parts.render(), cleanup_returncode, cleanup_timed_out, command
        return output_parts.render(), returncode, timed_out, command

    for command_text in startup_commands:
        returncode, timed_out = send(command_text)
        if returncode != 0 or timed_out:
            return finish(returncode, timed_out)
    calibration_startup = any(
        is_calibration_start_command(command_text)
        for command_text in startup_commands
    )
    if startup_commands and not calibration_startup:
        startup_deadline = (
            time.monotonic() + max(30, int(no_progress_window_sec))
            if deadline is None
            else deadline
        )
        status_output, _status, returncode, timed_out = poll_bot_status(
            execute_command,
            startup_deadline,
            status_command=status_command,
            sleep=sleep,
        )
        output_parts.append(status_output)
        if returncode != 0 or timed_out:
            return finish(returncode, timed_out)

    while deadline is None or time.monotonic() < deadline:
        sleep(
            max(1, heartbeat_sec)
            if deadline is None
            else min(
                max(1, heartbeat_sec),
                max(0.0, deadline - time.monotonic()),
            )
        )
        heartbeat_index += 1
        for command_text in heartbeat_commands:
            if deadline is not None and time.monotonic() >= deadline:
                break
            returncode, timed_out = send(command_text)
            if returncode != 0 or timed_out:
                return finish(returncode, timed_out)
        report = rolling_heartbeat_report(
            output_dir, heartbeat_index, output_parts.render(), 0, False, command,
            scenario_reports, validation_context, duration_policy, heartbeat_sec,
            no_progress_window_sec, max_repeated_decisions, max_death_loops,
            validation_route_manifest,
        )
        progress_total = int(report.get("watchdog_state", {}).get("progress_total") or 0)
        if progress_total > last_progress_total:
            last_progress_total = progress_total
            last_progress_at = time.monotonic()
        live_combat_progress = report.get("watchdog_state", {}).get("live_combat_progress")
        if live_combat_progress_advanced(last_live_combat_progress, live_combat_progress):
            last_progress_at = time.monotonic()
        last_live_combat_progress = live_combat_progress if isinstance(live_combat_progress, dict) else None
        no_progress_expired = time.monotonic() - last_progress_at >= no_progress_window_sec
        semantic_progress_plateau = (
            last_progress_total >= 0
            and progress_total <= last_progress_total
            and no_progress_expired
        )
        calibration = report.get("combat_calibration") or {}
        if bool(calibration.get("window_complete")):
            return finish(0, False)
        blocker = calibration_pre_scoring_blocker(report)
        blocker_key = canonical_sha256(blocker) if blocker else ""
        if blocker_key and blocker_key == last_calibration_blocker:
            calibration_blocker_repeats += 1
        else:
            last_calibration_blocker = blocker_key
            calibration_blocker_repeats = 1 if blocker_key else 0
        if blocker and calibration_blocker_repeats >= 3:
            finalize_calibration_pre_scoring_blocker(output_dir, report, blocker)
            return finish(0, False)
        if report["acceptable_final_evidence"] or report["completion_reason"] in {"repeated_decision_watchdog", "death_loop_watchdog", "machine_failure_predicate"}:
            return finish(0, False)
        if validation_route_manifest and semantic_progress_plateau:
            report["completion_reason"] = "semantic_progress_plateau_watchdog"
            report["watchdog_state"]["semantic_progress_plateau"] = True
            if "semantic_progress_plateau" not in report["failure_labels"]:
                report["failure_labels"].append("semantic_progress_plateau")
            report["failure_reason"] = report["failure_labels"][0]
            report["failed"] = max(int(report.get("failed") or 0), 1)
            report["all_passed"] = False
            report["acceptable_final_evidence"] = False
            if "failure_labels_present" not in report["final_evidence_rejections"]:
                report["final_evidence_rejections"].append("failure_labels_present")
            finalize_heartbeat(output_dir, report)
            write_json(output_dir / "report.json", report)
            return finish(0, False)
        if report["watchdog_state"].get("no_progress") and no_progress_expired:
            report["completion_reason"] = "no_progress_watchdog"
            finalize_heartbeat(output_dir, report)
            write_json(output_dir / "report.json", report)
            return finish(0, False)
    return finish(124, True)


def run_worldserver_completion_watchdog(
    binary: Path,
    config: Path,
    timeout_sec: int,
    script: str,
    output_dir: Path,
    scenario_reports: dict[str, dict[str, Any]],
    validation_context: dict[str, Any],
    duration_policy: str = "completion-watchdog",
    heartbeat_sec: int = DEFAULT_COMPLETION_HEARTBEAT_SEC,
    no_progress_window_sec: int = DEFAULT_NO_PROGRESS_WINDOW_SEC,
    max_repeated_decisions: int = DEFAULT_MAX_REPEATED_DECISIONS,
    max_death_loops: int = DEFAULT_MAX_DEATH_LOOPS,
    validation_route: dict[str, Any] | None = None,
    validation_route_manifest: dict[str, Any] | None = None,
) -> tuple[str, int, bool, list[str]]:
    command = [str(binary), "--config", str(config)]
    deadline = time.monotonic() + timeout_sec
    startup_commands, heartbeat_commands, cleanup_commands = heartbeat_commands_from_script(script)
    output_parts = WatchdogOutputBuffer(heartbeat_commands=heartbeat_commands)
    heartbeat_index = 0
    last_progress_total = -1
    last_progress_at = time.monotonic()
    last_live_combat_progress: dict[str, Any] | None = None
    last_calibration_blocker = ""
    calibration_blocker_repeats = 0
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.stdin is not None

    def joined_output() -> str:
        return output_parts.render()

    def record_command_output(
        command_text: str,
        value: str,
        *,
        cleanup: bool = False,
    ) -> None:
        if cleanup or command_text in cleanup_commands:
            output_parts.append_cleanup(value)
        elif command_text in heartbeat_commands:
            output_parts.append_heartbeat(command_text, value)
        else:
            output_parts.append(value)

    def send_command(command_text: str, *, cleanup: bool = False) -> None:
        assert process.stdin is not None
        attempts = (
            2
            if cleanup and command_text.startswith(".botauto combatlog")
            else 1
        )
        for attempt in range(1, attempts + 1):
            process.stdin.write(command_text + "\n")
            process.stdin.flush()
            command_output_prefix = f"$ {command_text}\n"
            command_deadline = (
                time.monotonic() + max(120, heartbeat_sec)
                if cleanup
                else bounded_console_deadline(deadline, max(5, heartbeat_sec))
            )
            command_output = read_until_console_prompt(
                process,
                command_deadline,
                expected_command_output_marker(command_text),
                command_output_marker_is_terminal(command_text),
            )
            if (
                attempts == 1
                or combat_log_export_complete(command_output)
                or attempt == attempts
            ):
                record_command_output(
                    command_text,
                    command_output_prefix + command_output,
                    cleanup=cleanup,
                )
                break
            record_command_output(
                command_text,
                command_output_prefix + combat_log_retry_receipt(
                    command_output, attempt
                ),
                cleanup=cleanup,
            )

    try:
        output_parts.append(read_until_console_prompt(process, deadline))
        for command_text in startup_commands:
            if process.poll() is not None:
                break
            send_command(command_text)
            output_parts.append(wait_for_bot_status_ready(process, deadline))

        while time.monotonic() < deadline:
            if process.poll() is not None:
                heartbeat_index += 1
                rolling_heartbeat_report(
                    output_dir,
                    heartbeat_index,
                    joined_output(),
                    process.returncode if process.returncode is not None else 0,
                    False,
                    command,
                    scenario_reports,
                    validation_context,
                    duration_policy,
                    heartbeat_sec,
                    no_progress_window_sec,
                    max_repeated_decisions,
                    max_death_loops,
                    validation_route_manifest,
                    completion_reason_override="worldserver_process_exit",
                )
                return joined_output(), process.returncode if process.returncode is not None else 0, False, command

            sleep_until = min(deadline, time.monotonic() + max(1, heartbeat_sec))
            while process.poll() is None and time.monotonic() < sleep_until:
                remaining = max(0.0, sleep_until - time.monotonic())
                if process.stdout is None:
                    time.sleep(min(1.0, remaining))
                else:
                    drained = drain_available_process_output(
                        process,
                        output_parts,
                        wait_sec=min(1.0, remaining),
                    )
                    if drained == 0:
                        # A closed or temporarily unavailable descriptor must
                        # not turn the bounded wait into a tight polling loop.
                        time.sleep(min(0.05, remaining))

            heartbeat_index += 1
            if process.poll() is None:
                for command_text in heartbeat_commands:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        break
                    send_command(command_text)
            report = rolling_heartbeat_report(
                output_dir,
                heartbeat_index,
                joined_output(),
                process.returncode if process.returncode is not None else 0,
                time.monotonic() >= deadline,
                command,
                scenario_reports,
                validation_context,
                duration_policy,
                heartbeat_sec,
                no_progress_window_sec,
                max_repeated_decisions,
                max_death_loops,
                validation_route_manifest,
            )
            progress_total = int(report.get("watchdog_state", {}).get("progress_total") or 0)
            if progress_total > last_progress_total:
                last_progress_total = progress_total
                last_progress_at = time.monotonic()
            live_combat_progress = report.get("watchdog_state", {}).get("live_combat_progress")
            if live_combat_progress_advanced(last_live_combat_progress, live_combat_progress):
                last_progress_at = time.monotonic()
            last_live_combat_progress = live_combat_progress if isinstance(live_combat_progress, dict) else None
            no_progress_expired = time.monotonic() - last_progress_at >= no_progress_window_sec
            semantic_progress_plateau = (
                last_progress_total >= 0
                and progress_total <= last_progress_total
                and no_progress_expired
            )
            if not validation_route_manifest and route_segment_complete(report, validation_route):
                supersede_transient_route_failures(report)
                report["completion_reason"] = "route_segment_complete"
                report["route_segment_complete"] = True
                report["acceptable_final_evidence"] = False
                rejections = list(report.get("final_evidence_rejections") or [])
                if "segment_or_route_context_is_debug_only" not in rejections:
                    rejections.append("segment_or_route_context_is_debug_only")
                report["final_evidence_rejections"] = rejections
                finalize_heartbeat(output_dir, report)
                write_json(output_dir / "report.json", report)
                break
            calibration = report.get("combat_calibration") or {}
            if bool(calibration.get("window_complete")):
                break
            if report["acceptable_final_evidence"]:
                break
            if report["completion_reason"] in {"repeated_decision_watchdog", "death_loop_watchdog", "machine_failure_predicate"}:
                break
            blocker = calibration_pre_scoring_blocker(report)
            blocker_key = canonical_sha256(blocker) if blocker else ""
            if blocker_key and blocker_key == last_calibration_blocker:
                calibration_blocker_repeats += 1
            else:
                last_calibration_blocker = blocker_key
                calibration_blocker_repeats = 1 if blocker_key else 0
            if blocker and calibration_blocker_repeats >= 3:
                finalize_calibration_pre_scoring_blocker(output_dir, report, blocker)
                break
            if validation_route_manifest and semantic_progress_plateau:
                report["completion_reason"] = "semantic_progress_plateau_watchdog"
                report["watchdog_state"]["semantic_progress_plateau"] = True
                if "semantic_progress_plateau" not in report["failure_labels"]:
                    report["failure_labels"].append("semantic_progress_plateau")
                report["failure_reason"] = report["failure_labels"][0]
                report["failed"] = max(int(report.get("failed") or 0), 1)
                report["all_passed"] = False
                report["acceptable_final_evidence"] = False
                if "failure_labels_present" not in report["final_evidence_rejections"]:
                    report["final_evidence_rejections"].append("failure_labels_present")
                finalize_heartbeat(output_dir, report)
                write_json(output_dir / "report.json", report)
                break
            if report["watchdog_state"].get("no_progress") and no_progress_expired:
                report["completion_reason"] = "no_progress_watchdog"
                finalize_heartbeat(output_dir, report)
                write_json(output_dir / "report.json", report)
                break
        timed_out = time.monotonic() >= deadline
        if process.poll() is None:
            for command_text in cleanup_commands:
                send_command(command_text, cleanup=True)
        if process.poll() is None and process.stdin and not process.stdin.closed:
            try:
                send_command("server shutdown force 0", cleanup=True)
            except BrokenPipeError:
                pass
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
            process.stdin = None
        shutdown_deadline = min(time.monotonic() + 10, deadline + 10)
        while process.poll() is None and time.monotonic() < shutdown_deadline:
            remaining = max(0.0, shutdown_deadline - time.monotonic())
            if process.stdout is None:
                time.sleep(min(0.25, remaining))
            else:
                drained = drain_available_process_output(
                    process,
                    output_parts,
                    wait_sec=min(0.25, remaining),
                )
                if drained == 0:
                    time.sleep(min(0.05, remaining))
        if process.poll() is None:
            process.kill()
            timed_out = True
        if process.stdout:
            output_parts.append_cleanup(process.stdout.read())
        returncode = process.returncode if process.returncode is not None else (124 if timed_out else 0)
        return joined_output(), returncode, timed_out, command
    except (BrokenPipeError, subprocess.TimeoutExpired) as exc:
        process.kill()
        output = (exc.stdout or "") if isinstance(exc, subprocess.TimeoutExpired) else ""
        if not output and process.stdout:
            output = process.stdout.read()
        output_parts.append_cleanup(output)
        return joined_output(), 124, True, command


def soap_envelope(command: str) -> bytes:
    escaped = html.escape(command, quote=True)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns1="urn:TC">'
        "<SOAP-ENV:Body>"
        f"<ns1:executeCommand><command>{escaped}</command></ns1:executeCommand>"
        "</SOAP-ENV:Body>"
        "</SOAP-ENV:Envelope>"
    ).encode("utf-8")


def parse_soap_result(payload: str) -> str:
    start = payload.find("<result>")
    end = payload.find("</result>")
    if start == -1 or end == -1 or end <= start:
        return payload
    return html.unescape(payload[start + len("<result>") : end])


def execute_soap_command(soap_url: str, username: str, password: str, command_text: str, timeout_sec: int) -> tuple[str, int, bool]:
    """Execute one SOAP console command without imposing process lifecycle policy."""
    auth = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        soap_url,
        data=soap_envelope(command_text),
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "urn:TC#executeCommand",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(1, timeout_sec)) as response:
            payload = response.read().decode("utf-8", errors="replace")
            return parse_soap_result(payload), 0, False
    except urllib.error.HTTPError as exc:
        return exc.read().decode("utf-8", errors="replace"), exc.code, False
    except TimeoutError:
        return "", 124, True
    except OSError as exc:
        return str(exc), 1, False


def run_soap_commands(soap_url: str, username: str, password: str, script: str, timeout_sec: int, observe_sec: int = 0) -> tuple[str, int, bool, list[str]]:
    output_parts = BoundedOutputParts()
    command = ["SOAP", soap_url]
    deadline = time.monotonic() + timeout_sec
    explicit_start = any(line.strip().startswith(".botauto start") for line in script.splitlines())
    calibration_start = any(
        is_calibration_start_command(line)
        for line in script.splitlines()
    )
    observed_autostart = False
    for raw_command in script.splitlines():
        command_text = raw_command.strip()
        if not command_text:
            continue
        if observe_sec > 0 and not explicit_start and not calibration_start and not observed_autostart and should_observe_before_command(command_text):
            output_parts.append(f"$ sleep {observe_sec}")
            time.sleep(observe_sec)
            observed_autostart = True
        remaining_float = deadline - time.monotonic()
        if remaining_float <= 0:
            return "\n".join(output_parts), 124, True, command
        payload, returncode, timed_out = execute_soap_command(soap_url, username, password, command_text, max(1, int(remaining_float)))
        output_parts.append(f"$ {command_text}")
        output_parts.append(payload)
        if returncode != 0 or timed_out:
            return "\n".join(output_parts), returncode, timed_out, command
        if observe_sec > 0 and command_text.startswith(".botauto start") and not calibration_start:
            output_parts.append(f"$ sleep {observe_sec}")
            time.sleep(observe_sec)
        elif observe_sec > 0 and is_calibration_start_command(command_text):
            output_parts.append(f"$ sleep {observe_sec}")
            time.sleep(observe_sec)
    return "\n".join(output_parts), 0, False, command


def route_sequence_child_command(args: argparse.Namespace, route: dict[str, Any], output_dir: Path, *, first_route: bool) -> list[str]:
    scenario_id = str(args.validation_scenario_id or "")
    context = route_validation_context(scenario_id, route, include_segment=True)
    command = [
        sys.executable,
        "-m",
        "tools.bot_ml.run_live_bot_validation",
        "--worldserver",
        str(args.worldserver),
        "--config",
        str(args.config),
        "--output-dir",
        str(output_dir),
        "--duration-policy",
        args.duration_policy,
        "--timeout-sec",
        str(args.timeout_sec),
        "--heartbeat-sec",
        str(args.heartbeat_sec),
        "--no-progress-window-sec",
        str(args.no_progress_window_sec),
        "--max-repeated-decision-count",
        str(args.max_repeated_decision_count),
        "--max-death-loop-count",
        str(args.max_death_loop_count),
        "--selector",
        args.selector,
        "--trace-limit",
        str(args.trace_limit),
        "--transport",
        args.transport,
        "--cohort-id",
        args.cohort_id,
        "--session-attempt-index",
        str(max(1, int(context.get("route_step") or 1))),
        "--session-environment",
        args.session_environment,
        "--session-profile",
        args.session_profile or scenario_id,
        "--session-transition-timeout-sec",
        str(args.session_transition_timeout_sec),
        "--validation-scenario-dir",
        str(args.validation_scenario_dir),
        "--validation-scenario-id",
        scenario_id,
        "--validation-segment-id",
        str(context.get("segment_id") or ""),
        "--validation-route-node-id",
        str(context.get("route_node_id") or ""),
        "--validation-route-label",
        str(context.get("route_label") or ""),
        "--validation-route-kind",
        str(context.get("route_kind") or ""),
        "--validation-route-step",
        str(context.get("route_step") or 0),
        "--validation-mechanic-profile",
        str(context.get("mechanic_profile") or ""),
    ]
    if args.no_start:
        command.append("--no-start")
    if args.force_start_command:
        command.append("--force-start-command")
    if args.stop:
        command.append("--stop")
    if getattr(args, "preserve_worldserver", False):
        command.append("--preserve-worldserver")
    if getattr(args, "session_runtime_dir", None):
        command.extend(["--session-runtime-dir", str(args.session_runtime_dir)])
    if getattr(args, "combat_calibration", False):
        command.append("--combat-calibration")
    if args.soap_user:
        command.extend(["--soap-user", args.soap_user])
    if args.soap_password:
        command.extend(["--soap-password", args.soap_password])
    if args.soap_url:
        command.extend(["--soap-url", args.soap_url])
    if args.scenario_report_dir:
        command.extend(["--scenario-report-dir", str(args.scenario_report_dir)])
    if first_route and args.apply_validation_provisioning:
        command.extend(
            [
                "--apply-validation-provisioning",
                "--validation-provisioning-config",
                str(args.validation_provisioning_config),
                "--gear-profiles",
                str(args.gear_profiles),
            ]
        )
    if first_route and args.reset_bot_pool:
        command.append("--reset-bot-pool")
    if args.publish_batch:
        command.append("--publish-batch")
    if args.retain_published_batch:
        command.append("--retain-published-batch")
    if first_route and args.reload_rotation_profiles:
        command.append("--reload-rotation-profiles")
    for tag in args.bot_pool_tag:
        command.extend(["--bot-pool-tag", tag])
    if args.keep_bot_pool_position:
        command.append("--keep-bot-pool-position")
    if args.keep_bot_pool_quests:
        command.append("--keep-bot-pool-quests")
    if args.keep_bot_pool_memory:
        command.append("--keep-bot-pool-memory")
    return command


def route_sequence_report(
    args: argparse.Namespace,
    routes: list[dict[str, Any]],
    commands: list[list[str]],
    segment_reports: list[dict[str, Any]],
    failed_command: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failure_labels: list[str] = []
    if not routes:
        failure_labels.append("no_executable_validation_routes")
    for report in segment_reports:
        for label in report.get("failure_labels") or []:
            if label not in failure_labels:
                failure_labels.append(str(label))
    if failed_command and "route_sequence_child_failed" not in failure_labels:
        failure_labels.append("route_sequence_child_failed")
    complete_segments = []
    for report in segment_reports:
        validation_context = report.get("validation_context") if isinstance(report.get("validation_context"), dict) else {}
        if route_segment_complete(report, report.get("validation_route") if isinstance(report.get("validation_route"), dict) else None):
            complete_segments.append(str(validation_context.get("segment_id") or ""))
    expected_segments = [route_segment_output_name(route) for route in routes]
    missing_segments = [segment for segment in expected_segments if segment not in complete_segments]
    result = {
        "schema": "bot_live_validation_report_v1",
        "generated_at_unix": int(time.time()),
        "duration_policy": args.duration_policy,
        "validation_context": {"scenario_id": args.validation_scenario_id},
        "route_sequence": {
            "schema": "bot_live_validation_route_sequence_v1",
            "scenario_id": args.validation_scenario_id,
            "route_count": len(routes),
            "expected_segments": expected_segments,
            "complete_segments": complete_segments,
            "missing_segments": missing_segments,
            "commands": commands,
            "segment_reports": [str(args.output_dir / route_segment_output_name(route) / "report.json") for route in routes],
            "failed_command": failed_command or {},
        },
        "command": commands,
        "returncode": int(failed_command.get("returncode", 0)) if failed_command else 0,
        "timed_out": False,
        "json_payloads": 0,
        "active_bots": 0,
        "target_bots": 0,
        "diagnosis_count": 0,
        "trace_entries": sum(int(report.get("trace_entries") or 0) for report in segment_reports),
        "scenario_reports": {},
        "command_errors": [],
        "evidence": {
            "validation_route_actions": sum(int(report.get("evidence", {}).get("validation_route_actions") or 0) for report in segment_reports),
            "validation_evidence_counts": {},
        },
        "progress_counters": {
            "validation_route_actions": sum(int(report.get("progress_counters", {}).get("validation_route_actions") or 0) for report in segment_reports),
            "kills": sum(int(report.get("progress_counters", {}).get("kills") or 0) for report in segment_reports),
            "boss_kill_evidence": sum(int(report.get("progress_counters", {}).get("boss_kill_evidence") or 0) for report in segment_reports),
            "trash_pulls": sum(int(report.get("progress_counters", {}).get("trash_pulls") or 0) for report in segment_reports),
        },
        "watchdog_state": {"policy": "route-sequence", "progress_total": len(complete_segments)},
        "completion_reason": "route_sequence_complete" if not failure_labels and not missing_segments else "route_sequence_incomplete",
        "acceptable_final_evidence": False,
        "final_evidence_rejections": ["route_sequence_context_is_not_uninterrupted_full_clear"],
        "failure_labels": failure_labels,
        "failure_reason": failure_labels[0] if failure_labels else None,
        "stages": [],
        "passed": len(complete_segments),
        "failed": len(missing_segments),
        "all_passed": not failure_labels and not missing_segments,
        "runtime_ml_control": "offline_shadow_only",
        "control_eligible": False,
    }
    result["live_validation_standard"] = build_live_validation_standard_marker(result, {})
    return result


def run_route_sequence(args: argparse.Namespace, routes: list[dict[str, Any]]) -> int:
    commands: list[list[str]] = []
    segment_reports: list[dict[str, Any]] = []
    failed_command: dict[str, Any] | None = None
    for index, route in enumerate(routes):
        segment_dir = args.output_dir / route_segment_output_name(route)
        command = route_sequence_child_command(args, route, segment_dir, first_route=index == 0)
        commands.append(command)
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        (segment_dir / "sequence_child_stdout.log").write_text(completed.stdout, encoding="utf-8")
        (segment_dir / "sequence_child_stderr.log").write_text(completed.stderr, encoding="utf-8")
        report_path = segment_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
        if report:
            segment_reports.append(report)
        append_jsonl(
            args.output_dir / "route_sequence_events.jsonl",
            {
                "segment_id": route_segment_output_name(route),
                "route_node_id": route.get("route_node_id") or "",
                "returncode": completed.returncode,
                "report": str(report_path),
                "completion_reason": report.get("completion_reason") if report else "",
                "failure_labels": report.get("failure_labels") if report else ["missing_segment_report"],
            },
        )
        if completed.returncode != 0 or not report or not route_segment_complete(report, route):
            failed_command = {
                "segment_id": route_segment_output_name(route),
                "route_node_id": route.get("route_node_id") or "",
                "returncode": completed.returncode,
                "report": str(report_path),
            }
            break
    report = route_sequence_report(args, routes, commands, segment_reports, failed_command)
    write_json(args.output_dir / "report.json", report)
    (args.output_dir / "commands.txt").write_text("\n".join(render_command(command) for command in commands) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_passed"] else 1


def attempt_evidence_envelope(
    args: argparse.Namespace,
    report: dict[str, Any],
    validation_context: dict[str, Any],
    validation_route_manifest: dict[str, Any],
    session_lifecycle: dict[str, Any],
) -> dict[str, Any]:
    """Bind one closed attempt to the shared Phase 2 evidence identity."""
    party_spec_target = list(getattr(args, "party_spec_target", None) or [])
    supplied: dict[str, Any] = {}
    manifest_path = getattr(args, "evidence_identity_manifest", None)
    if manifest_path:
        try:
            payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"invalid --evidence-identity-manifest: {exc}") from exc
        if not isinstance(payload, dict):
            raise SystemExit("--evidence-identity-manifest must contain a JSON object")
        if getattr(args, "calibration_only", False):
            try:
                payload = validate_phase8_evidence_manifest(
                    payload,
                    runtime_identity=session_lifecycle,
                )
            except ValueError as exc:
                raise SystemExit(f"invalid Phase 8 evidence identity manifest: {exc}") from exc
        supplied = payload
    supplied_components = supplied.get("component_hashes") if isinstance(supplied.get("component_hashes"), dict) else {}
    supplied_scopes = supplied.get("scope_ids") if isinstance(supplied.get("scope_ids"), dict) else {}
    supplied_artifacts = supplied.get("artifact_hashes") if isinstance(supplied.get("artifact_hashes"), dict) else {}

    def file_hash(path: Path, label: str) -> str:
        return sha256_file(path) if path.is_file() else canonical_sha256({"missing": label, "path": str(path)})

    profile_manifest = Path(trinity_config_string(args.config, "BotWorld.ProfileManifest", "dataset/bot_runtime_profiles/profiles.json"))
    if not profile_manifest.is_absolute():
        profile_manifest = REPO_ROOT / profile_manifest
    target_catalog = REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
    reference_catalog = REPO_ROOT / "experiments/configs/all_spec_references_cata_p4_v1.json"
    policy = REPO_ROOT / "experiments/configs/bot_acceptance_policy_v1.json"
    scenario_config = REPO_ROOT / "experiments/configs/validation_scenarios_cata_001.json"
    phase9_matrix = REPO_ROOT / "experiments/configs/stonecore_phase9_pairwise_matrix_v1.json"
    phase9_pair_policy = REPO_ROOT / "experiments/configs/stonecore_phase9_pair_policy_v1.json"
    external_names = (
        "database_snapshot_sha256",
        "database_schema_sha256",
        "server_epoch_sha256",
        "profile_generation_sha256",
    )
    incomplete = [name for name in external_names if not re.fullmatch(r"[0-9a-f]{64}", str(supplied_components.get(name) or ""))]
    process_session = canonical_sha256(
        {
            "transport": args.transport,
            "command": report.get("command") or [],
            "session_fingerprint": session_lifecycle.get("session_fingerprint") or "",
            "server_pid": int(session_lifecycle.get("server_pid") or 0),
            "generated_at_unix": int(report.get("generated_at_unix") or 0),
        }
    )
    components = {
        "git_commit_sha256": sha256_text(str(session_lifecycle.get("git_head") or git_head(REPO_ROOT))),
        "git_dirty_state_sha256": str(session_lifecycle.get("git_dirty_state_sha256") or git_dirty_state_sha256(REPO_ROOT)),
        "binary_sha256": sha256_file(args.worldserver.resolve()),
        "config_sha256": sha256_file(Path(report.get("config") or args.config).resolve()),
        "database_snapshot_sha256": str(supplied_components.get("database_snapshot_sha256") or canonical_sha256({"state": "unprobed_database_snapshot"})),
        "database_schema_sha256": str(supplied_components.get("database_schema_sha256") or canonical_sha256({"state": "unprobed_database_schema"})),
        "process_session_sha256": process_session,
        "server_epoch_sha256": str(supplied_components.get("server_epoch_sha256") or canonical_sha256({"state": "unpublished_server_epoch", "process_session_sha256": process_session})),
        "spec_catalog_sha256": file_hash(target_catalog, "spec_catalog"),
        "provisioning_sha256": file_hash(args.validation_provisioning_config.resolve(), "provisioning"),
        "gear_sha256": file_hash(args.gear_profiles.resolve(), "gear"),
        "profile_generation_sha256": str(supplied_components.get("profile_generation_sha256") or canonical_sha256({"state": "unpublished_profile_generation", "profile_content_sha256": file_hash(profile_manifest, "profile_manifest")})),
        "reference_sha256": file_hash(reference_catalog, "reference_catalog"),
        "policy_sha256": file_hash(policy, "acceptance_policy"),
        "scenario_sha256": canonical_sha256(
            {
                "validation_scenario_sha256": file_hash(scenario_config, "scenario_config"),
                "phase9_matrix_sha256": file_hash(phase9_matrix, "phase9_pairwise_matrix"),
                "phase9_pair_policy_sha256": file_hash(phase9_pair_policy, "phase9_pair_policy"),
            }
        ) if party_spec_target else file_hash(scenario_config, "scenario_config"),
        "route_sha256": canonical_sha256(validation_route_manifest or validation_context or {"state": "no_route"}),
    }
    generated = int(report.get("generated_at_unix") or 0)
    scenario_id = str(validation_context.get("scenario_id") or "unscoped")
    exact_party_id = canonical_sha256(party_spec_target) if party_spec_target else scenario_id
    scope_defaults = {
        "batch_id": str(args.output_dir.parent.resolve()),
        "cohort_id": str(args.cohort_id) if args.transport == "session" else (",".join(sorted(str(value) for value in (args.bot_pool_tag or []))) or str(args.selector)),
        "composition_id": exact_party_id,
        "party_id": exact_party_id,
        "instance_id": scenario_id,
        "attempt_id": f"{args.output_dir.resolve()}:{generated}",
        "repeat_id": str(validation_context.get("segment_id") or validation_context.get("route_node_id") or "full"),
        "measurement_window_id": f"observe:{int(args.observe_sec or 0)}:timeout:{int(args.timeout_sec or 0)}",
    }
    scopes = {name: str(supplied_scopes.get(name) or value) for name, value in scope_defaults.items()}
    raw_log = args.output_dir / "worldserver_output.log"
    compact_payload = {key: value for key, value in report.items() if key not in {"evidence_envelope", "acceptance_facts", "acceptance_verification"}}
    artifacts = {
        "raw_artifact_sha256": file_hash(raw_log, "raw_worldserver_output"),
        "compact_artifact_sha256": canonical_sha256(compact_payload),
        "dvc_pointer_sha256": str(supplied_artifacts.get("dvc_pointer_sha256") or canonical_sha256({"state": "not_yet_published_to_dvc"})),
        "remote_verification_receipt_sha256": str(supplied_artifacts.get("remote_verification_receipt_sha256") or canonical_sha256({"state": "not_yet_remote_verified"})),
    }
    envelope = build_evidence_envelope(
        components,
        scopes,
        artifacts,
        freshness="current" if not incomplete else "current_unpublished",
        live_validation_standard=report.get("live_validation_standard") if isinstance(report.get("live_validation_standard"), Mapping) else None,
    )
    envelope["identity_complete"] = not incomplete
    envelope["identity_incomplete_reasons"] = [f"missing_external_{name}" for name in incomplete]
    envelope["identity_manifest"] = str(Path(manifest_path).resolve()) if manifest_path else ""
    envelope["identity_manifest_sha256"] = (
        str(supplied.get("manifest_sha256") or "") if manifest_path else ""
    )
    return envelope


@dataclass
class ReusableValidationServerOwner:
    repository: Path
    environment: str
    session: Any
    execute_command: CommandTransport
    transition_timeout_sec: int
    lifecycle: dict[str, Any] = field(default_factory=dict)

    def wait_until_ready(self) -> str:
        output_parts = BoundedOutputParts()
        deadline = time.monotonic() + self.transition_timeout_sec
        while time.monotonic() < deadline:
            remaining = max(1, int(deadline - time.monotonic()))
            output, returncode, timed_out = self.execute_command(
                ".botauto cohorts", remaining
            )
            output_parts.extend(("$ .botauto cohorts\n", output))
            payload = next(
                (
                    row
                    for row in reversed(parse_json_objects(output))
                    if row.get("action") == "botauto_cohorts"
                ),
                None,
            )
            if returncode == 0 and not timed_out and payload is not None:
                server_pid = int(self.lifecycle.get("server_pid") or 0)
                responder_pid = int(payload.get("server_process_id") or 0)
                self.lifecycle["server_process_id"] = responder_pid
                self.lifecycle["server_process_identity_verified"] = (
                    server_pid > 0 and responder_pid == server_pid
                )
                if not self.lifecycle["server_process_identity_verified"]:
                    raise RuntimeError(
                        "worldserver command responder does not match the owned systemd process"
                    )
                self.lifecycle["server_epoch"] = int(payload.get("server_epoch") or 0)
                self.lifecycle["max_active_cohorts"] = int(
                    payload.get("max_active_cohorts") or 0
                )
                return "".join(output_parts)
            time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))
        raise RuntimeError("timed out waiting for reusable worldserver ownership API")

    def reload_rotation_profiles(self) -> dict[str, Any]:
        output, returncode, timed_out = self.execute_command(
            ".botauto rotations reload",
            self.transition_timeout_sec,
        )
        payload = next(
            (
                row for row in reversed(parse_json_objects(output))
                if row.get("action") == "botauto_rotations_reload"
            ),
            None,
        )
        if (
            returncode != 0
            or timed_out
            or payload is None
            or not bool(payload.get("ok"))
        ):
            raise RuntimeError("atomic rotation profile reload failed")
        result = {
            "generation": int(payload.get("active_generation") or 0),
            "content_hash": str(payload.get("active_content_hash") or ""),
        }
        self.lifecycle["rotation_reload"] = result
        return result

    def provision_once(
        self,
        identity: Mapping[str, Any],
        provision: Callable[[], Mapping[str, Any]],
    ) -> dict[str, Any]:
        epoch = int(self.lifecycle.get("server_epoch") or 0)
        if epoch <= 0:
            raise RuntimeError("server epoch is unavailable for provisioning")
        state_root = Path("/tmp") / "trinity-cata-live-validation"
        state_root.mkdir(parents=True, exist_ok=True)
        state_name = canonical_sha256(
            {
                "repository": str(self.repository.resolve()),
                "environment": self.environment,
            }
        )
        state_path = state_root / f"{state_name}.json"
        identity_sha256 = canonical_sha256(dict(identity))
        if state_path.is_file():
            try:
                stored = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                stored = {}
            if (
                int(stored.get("server_epoch") or 0) == epoch
                and stored.get("identity_sha256") == identity_sha256
            ):
                self.lifecycle["provisioning_reused"] = True
                return dict(stored.get("result") or {})
        result = dict(provision())
        payload = {
            "server_epoch": epoch,
            "identity_sha256": identity_sha256,
            "result": result,
        }
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(state_path)
        self.lifecycle["provisioning_reused"] = False
        return result

    @contextlib.contextmanager
    def owned(self):
        with live_validation_lock(self.repository, self.environment):
            action = ensure_healthy_matching_session(self.session)
            self.lifecycle.update(self.session.metadata())
            self.lifecycle["transport"] = "session"
            self.lifecycle["server_action"] = action.action
            self.lifecycle["server_pid"] = int(
                action.status.properties.get("MainPID") or 0
            )
            yield self


def run_reusable_validation_session(
    args: argparse.Namespace,
    script: str,
    scenario_reports: dict[str, dict[str, Any]],
    validation_context: dict[str, Any],
    validation_route: dict[str, Any],
    validation_route_manifest: dict[str, Any],
    validation_route_manifest_path: Path | None,
    bot_pool_tags: list[str],
) -> tuple[str, int, bool, list[str], dict[str, Any]]:
    del script
    if not args.soap_user or not args.soap_password:
        raise SystemExit("--soap-user and --soap-password are required with --transport session")
    profile_manifest = Path(trinity_config_string(args.config, "BotWorld.ProfileManifest", "dataset/bot_runtime_profiles/profiles.json"))
    if not profile_manifest.is_absolute():
        profile_manifest = REPO_ROOT / profile_manifest
    phase9_matrix = REPO_ROOT / "experiments/configs/stonecore_phase9_pairwise_matrix_v1.json"
    phase9_pair_policy = REPO_ROOT / "experiments/configs/stonecore_phase9_pair_policy_v1.json"
    fingerprint_paths = [
        path for path in (
            profile_manifest,
            args.validation_scenario_dir / "validation_routes.jsonl",
            args.validation_provisioning_config,
            REPO_ROOT / "experiments/configs/phase8_dps_representatives_cata_p4_v1.json",
            REPO_ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json",
            args.gear_profiles,
            REPO_ROOT / "dataset/validation_provisioning/manifest.json",
            phase9_matrix if args.party_spec_target else None,
            phase9_pair_policy if args.party_spec_target else None,
        ) if path is not None and path.is_file()
    ]
    profile = args.session_profile or str(validation_context.get("scenario_id") or "")
    if not profile:
        raise SystemExit("--transport session requires --session-profile or --validation-scenario-id")
    # The controller writes a descriptive JSON manifest for evidence, but the
    # server loads and hashes the executable route file named by the selected
    # runtime profile.  Admission identity must bind to that same executable
    # bytes; hashing the controller's summary would reject a valid receipt.
    route_manifest_identity_path = validation_route_manifest_path
    if validation_route_manifest_path and profile_manifest.is_file():
        profiles = json.loads(profile_manifest.read_text(encoding="utf-8"))
        selected = next((row for row in profiles.get("profiles", []) if str(row.get("name") or "") == profile), None)
        configured_manifest = str(((selected or {}).get("validation_route") or {}).get("manifest_path") or "")
        expected_manifest = args.validation_scenario_dir / "validation_routes.jsonl"
        if not configured_manifest or Path(configured_manifest).resolve() != expected_manifest.resolve():
            raise SystemExit("session runtime profile route manifest does not match --validation-scenario-dir")
        route_manifest_identity_path = Path(configured_manifest)
        if not route_manifest_identity_path.is_absolute():
            route_manifest_identity_path = REPO_ROOT / route_manifest_identity_path

    restart_components: dict[str, str] = {}
    identity_payload: dict[str, Any] = {}
    phase9_artifact_hashes: dict[str, str] = {}
    if args.party_spec_target:
        phase9_artifact_hashes = {
            "target_catalog_sha256": sha256_file(args.all_spec_target_catalog.resolve()),
            "pair_policy_sha256": sha256_file(phase9_pair_policy),
            "pairwise_matrix_sha256": sha256_file(phase9_matrix),
            "route_manifest_sha256": sha256_file(route_manifest_identity_path),
        }
    if args.evidence_identity_manifest:
        try:
            identity_payload = json.loads(args.evidence_identity_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"invalid --evidence-identity-manifest: {exc}") from exc
        try:
            if args.calibration_only:
                identity_payload = validate_phase8_evidence_manifest(identity_payload)
            elif args.party_spec_target:
                identity_payload = validate_phase9_evidence_manifest(
                    identity_payload,
                    artifact_hashes=phase9_artifact_hashes,
                )
        except (TypeError, ValueError) as exc:
            phase = "Phase 8" if args.calibration_only else "Phase 9"
            raise SystemExit(f"invalid {phase} evidence identity manifest: {exc}") from exc
        identity_components = identity_payload.get("component_hashes") if isinstance(identity_payload, dict) else {}
        for name in ("database_snapshot_sha256", "database_schema_sha256"):
            value = str((identity_components or {}).get(name) or "")
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise SystemExit(f"--evidence-identity-manifest is missing valid {name}")
            restart_components[name] = value

    session = build_session(
        REPO_ROOT, args.session_environment, args.worldserver, args.config,
        fingerprint_paths=fingerprint_paths,
        restart_components=restart_components,
    )
    command = ["SESSION", session.unit_name, args.soap_url]
    output_parts = BoundedOutputParts()

    def execute(command_text: str, remaining: int) -> tuple[str, int, bool]:
        return execute_soap_command(args.soap_url, args.soap_user, args.soap_password, command_text, remaining)

    attempt = ValidationAttempt(
        cohort_id=args.cohort_id,
        attempt_index=args.session_attempt_index,
        profile=profile,
        output_dir=args.output_dir,
        timeout_sec=args.timeout_sec,
        observe_sec=args.observe_sec,
    )
    scheduler = SerialValidationScheduler([attempt])
    admitted = scheduler.admit_next()
    if admitted is None:
        raise RuntimeError("serial scheduler did not admit the validation attempt")
    executor = CohortCommandExecutor(
        execute,
        admitted.cohort_id,
        args.session_transition_timeout_sec,
    )
    watchdog = CohortAttemptWatchdog(executor, admitted)
    owner = ReusableValidationServerOwner(
        REPO_ROOT,
        args.session_environment,
        session,
        execute,
        args.session_transition_timeout_sec,
    )
    lifecycle = owner.lifecycle
    lifecycle.update(
        {
            "cohort_id": admitted.cohort_id,
            "attempt_index": admitted.attempt_index,
            "profile": admitted.profile,
            "admitted_at_unix": int(time.time()),
            "scheduler_events": scheduler.events,
            "exact_party_pool_tag": args.party_pool_tag if args.party_spec_target else "",
            "exact_party_class_specs": list(args.party_spec_target),
            "exact_party_sha256": canonical_sha256(list(args.party_spec_target)) if args.party_spec_target else "",
        }
    )

    def checked(label: str, result: tuple[str, int, bool]) -> str:
        output, returncode, timed_out = result
        output_parts.extend((f"$ {label}\n", output))
        if returncode != 0 or timed_out:
            raise RuntimeError(f"cohort command failed: {label}")
        return output

    def cohort_registry() -> tuple[str, dict[str, Any]]:
        output, returncode, timed_out = execute(
            ".botauto cohorts",
            args.session_transition_timeout_sec,
        )
        output_parts.extend(("$ .botauto cohorts\n", output))
        payload = next(
            (
                row for row in reversed(parse_json_objects(output))
                if row.get("action") == "botauto_cohorts"
            ),
            None,
        )
        if returncode != 0 or timed_out or payload is None:
            raise RuntimeError("failed to read cohort registry")
        return output, payload

    with owner.owned():
        output_parts.append(owner.wait_until_ready())
        lifecycle["server_epoch"] = owner.lifecycle["server_epoch"]
        if int(owner.lifecycle.get("max_active_cohorts") or 0) != 1:
            raise RuntimeError("serial validation requires max_active_cohorts=1")
        if args.reload_rotation_profiles:
            owner.reload_rotation_profiles()
        try:
            create_output, create_returncode, create_timed_out = executor.create()
            output_parts.extend((f"$ .botauto create {admitted.cohort_id}\n", create_output))
            create_payloads = parse_json_objects(create_output)
            already_exists = any(
                row.get("failure_reason") == "cohort_already_exists"
                for row in create_payloads
            )
            if (create_returncode != 0 or create_timed_out) and not already_exists:
                raise RuntimeError("failed to create validation cohort")

            checked(f".botauto stop {admitted.cohort_id}", executor.stop())
            inactive_output, inactive_status = wait_for_bot_status_state(
                executor.run,
                False,
                time.monotonic() + args.session_transition_timeout_sec,
                status_command=executor.status_command,
            )
            output_parts.append(inactive_output)
            lifecycle["inactive_before_preparation"] = True
            lifecycle["preparation"] = {
                "provisioning_scope": "server_epoch",
                "server_epoch": lifecycle["server_epoch"],
                "bot_pool_reset": "cohort_prepare",
                "profile": admitted.profile,
            }
            if args.apply_validation_provisioning:
                lifecycle["preparation"]["validation_provisioning"] = owner.provision_once(
                    {
                        "validation_provisioning_sha256": sha256_file(args.validation_provisioning_config.resolve()),
                        "bwd_diagnostic_shard_fixture_sha256": sha256_file(args.bwd_diagnostic_shard_fixture.resolve()),
                        "gear_profiles_sha256": sha256_file(args.gear_profiles.resolve()),
                    },
                    lambda: prepare_validation_provisioning(
                        args.output_dir,
                        args.validation_provisioning_config,
                        args.gear_profiles,
                        args.config,
                        args.bwd_diagnostic_shard_fixture,
                        apply=True,
                    ),
                )
            if args.calibration_only and getattr(
                args, "calibration_self_provided_baseline", False
            ):
                # A reusable server keeps the candidate pool and its consumed
                # item stacks across attempts. Reset both while the cohort is
                # inactive, after any full provisioning and before calibration
                # can claim a bot.
                lifecycle["preparation"]["bot_pool_reset"] = prepare_bot_pool_reset(
                    args.output_dir,
                    args.config,
                    bot_pool_tags,
                    apply=True,
                    reset_positions=not args.keep_bot_pool_position,
                    reset_quests=not args.keep_bot_pool_quests,
                    reset_memory=not args.keep_bot_pool_memory,
                )
                lifecycle["preparation"]["calibration_consumables"] = (
                    prepare_calibration_consumables(
                        args.output_dir,
                        args.config,
                        args.calibration_target_spec,
                        args.all_spec_target_catalog.resolve(),
                        apply=True,
                    )
                )
            if validation_route and int(validation_route.get("bot_start_map_id") or 0):
                lifecycle["preparation"]["route_bot_start"] = (
                    server_route_start_contract(validation_route)
                )

            if args.calibration_only:
                lifecycle["preparation"]["profile"] = "calibration_only"
                checked(
                    f".botauto start {admitted.cohort_id}",
                    executor.start(),
                )
            else:
                prepare_suffix = ""
                if args.party_spec_target:
                    prepare_suffix = " " + " ".join((args.party_pool_tag, *args.party_spec_target))
                checked(
                    f".botauto prepare {admitted.cohort_id} {admitted.profile}{prepare_suffix}",
                    executor.prepare(admitted.profile, args.party_pool_tag, args.party_spec_target),
                )
                checked(
                    f".botauto start {admitted.cohort_id} {admitted.profile}",
                    executor.start(admitted.profile),
                )
            ready_output, ready_status = wait_for_bot_status_state(
                executor.run,
                True,
                time.monotonic() + args.session_transition_timeout_sec,
                status_command=executor.status_command,
                allow_zero_active=args.calibration_only,
            )
            output_parts.append(ready_output)
            if ready_status is None:
                raise RuntimeError("cohort status unavailable after start")
            if args.validation_scenario_id == "stonecore_5h":
                # Active leases are published before the route-instance
                # readback/receipt commit.  Do not classify that short
                # activation window as a failed heroic admission.
                admission_output, admission_payload = wait_for_heroic_admission_status(
                    executor.run,
                    time.monotonic() + args.session_transition_timeout_sec,
                    status_command=executor.status_command,
                )
                output_parts.append(admission_output)
                ready_status = {
                    "active": True,
                    "active_bots": int(admission_payload.get("bots") or 0),
                    "target_bots": int(admission_payload.get("target_bots") or 0),
                    "payload": admission_payload,
                }
            ready_payload = ready_status["payload"]
            lifecycle["active_after_start"] = True
            lifecycle["runtime_attempt_id"] = int(ready_payload.get("attempt_id") or 0)
            lifecycle["profile_generation"] = int(ready_payload.get("profile_generation") or 0)
            lifecycle["profile_content_hash"] = str(ready_payload.get("profile_content_hash") or "")
            lifecycle["lease_count_after_start"] = int(ready_payload.get("lease_count") or 0)
            if args.validation_scenario_id == "stonecore_5h":
                # Retain the bounded, five-member admission snapshot so the
                # remote evidence round-trip can independently re-run the
                # heroic entrance/role/spec receipt verifier.
                lifecycle["admission_status"] = ready_payload
                heroic_admission = validate_heroic_admission_receipt(
                    ready_payload,
                    expected_class_specs=list(args.party_spec_target) or None,
                    expected_map_id=int(validation_route.get("bot_start_map_id") or 0),
                    expected_start=(
                        float(validation_route.get("bot_start_x") or 0.0),
                        float(validation_route.get("bot_start_y") or 0.0),
                        float(validation_route.get("bot_start_z") or 0.0),
                    ),
                    expected_route_manifest_sha256=str(
                        phase9_artifact_hashes.get("route_manifest_sha256") or ""
                    ),
                    expected_recovery_entrance=(
                        int(validation_route.get("recovery_entrance_area_trigger_id") or 0),
                        int(validation_route.get("recovery_entrance_source_map_id") or 0),
                        int(validation_route.get("recovery_entrance_target_map_id") or 0),
                    ),
                )
                lifecycle["heroic_admission"] = heroic_admission
                lifecycle["heroic_admission_verified"] = bool(heroic_admission["verified"])
                if not heroic_admission["verified"]:
                    raise RuntimeError(
                        "Stonecore 5H admission receipt rejected: "
                        + ", ".join(heroic_admission["failure_reasons"])
                    )
            if args.party_spec_target:
                observed_party = [str(value) for value in ready_payload.get("exact_party_class_specs") or []]
                if observed_party != list(args.party_spec_target):
                    raise RuntimeError(
                        f"exact party mismatch after start: expected {args.party_spec_target}, observed {observed_party}"
                    )
                if str(ready_payload.get("pool_tag_filter") or "") != args.party_pool_tag:
                    raise RuntimeError("exact party pool tag mismatch after start")
                if int(ready_payload.get("lease_count") or 0) != 5 or int(ready_payload.get("bots") or 0) != 5:
                    raise RuntimeError("exact party did not admit exactly five leased bots")
                lifecycle["exact_party_verified"] = True
            if args.evidence_identity_manifest and (args.calibration_only or args.party_spec_target):
                try:
                    if args.calibration_only:
                        validate_phase8_evidence_manifest(
                            identity_payload,
                            runtime_identity=lifecycle,
                        )
                    else:
                        validate_phase9_evidence_manifest(
                            identity_payload,
                            runtime_identity=lifecycle,
                            artifact_hashes=phase9_artifact_hashes,
                        )
                except ValueError as exc:
                    raise RuntimeError(
                        f"live runtime identity mismatch: {exc}"
                    ) from exc

            watchdog_script = watchdog.script(
                args.selector,
                args.trace_limit,
                args.combat_calibration,
                calibration_mode=args.calibration_mode,
                calibration_target_spec=args.calibration_target_spec,
                calibration_seed=args.calibration_seed,
                calibration_only=args.calibration_only,
            )
            output, returncode, timed_out, _ = run_transport_completion_watchdog(
                executor.run, command, admitted.timeout_sec, watchdog_script, admitted.output_dir,
                scenario_reports, validation_context,
                validation_route_manifest=validation_route_manifest,
                duration_policy=args.duration_policy,
                heartbeat_sec=args.heartbeat_sec,
                no_progress_window_sec=args.no_progress_window_sec,
                max_repeated_decisions=args.max_repeated_decision_count,
                max_death_loops=args.max_death_loop_count,
                status_command=executor.status_command,
            )
            output_parts.append(output)
            lifecycle["watchdog_completed"] = True
        finally:
            cleanup_errors: list[str] = []
            cleanup_record: dict[str, Any] = {
                "cohort_id": admitted.cohort_id,
                "active": None,
                "active_bots": None,
                "lease_count": None,
                "party_bot_count": None,
                "server_epoch": None,
                "fixture_cleanup_required": bool(args.calibration_only),
                "fixture_cleanup_submitted_or_absent": not bool(args.calibration_only),
            }
            lifecycle["cleanup"] = cleanup_record
            lifecycle["worldserver_stop_requested"] = False
            try:
                fixture_cleanup_required = bool(args.calibration_only)
                fixture_cleanup_submitted_or_absent = not fixture_cleanup_required
                if fixture_cleanup_required:
                    try:
                        calibration_stop_output = checked(
                            f".botauto calibrate {admitted.cohort_id} stop",
                            executor.calibration("stop"),
                        )
                    except Exception as exc:
                        cleanup_errors.append(
                            f"calibration fixture cleanup command failed: {exc}"
                        )
                        calibration_stop_output = ""
                    calibration_stop = next(
                        (
                            row
                            for row in reversed(
                                parse_json_objects(calibration_stop_output)
                            )
                            if row.get("action") == "botauto_calibrate_stop"
                        ),
                        None,
                    )
                    fixture_cleanup_submitted_or_absent = bool(
                        calibration_stop
                        and calibration_stop.get(
                            "fixture_cleanup_submitted_or_absent"
                        )
                        is True
                    )
                    if not fixture_cleanup_submitted_or_absent:
                        cleanup_errors.append(
                            "calibration fixture cleanup was not submitted or absent"
                        )
                try:
                    checked(f".botauto stop {admitted.cohort_id}", executor.stop())
                except Exception as exc:
                    cleanup_errors.append(f"cohort cleanup command failed: {exc}")

                inactive_status = None
                registry: dict[str, Any] = {}
                try:
                    inactive_output, inactive_status = wait_for_bot_status_state(
                        execute,
                        False,
                        time.monotonic() + args.session_transition_timeout_sec,
                        status_command=executor.status_command,
                    )
                    output_parts.append(inactive_output)
                    if inactive_status is None:
                        raise RuntimeError("cohort status unavailable after stop")
                    _, registry = cohort_registry()
                except Exception as exc:
                    cleanup_errors.append(f"cohort cleanup readback failed: {exc}")

                cohort_row = next(
                    (
                        row for row in registry.get("cohorts", [])
                        if row.get("cohort_id") == admitted.cohort_id
                    ),
                    None,
                )
                inactive_payload = (
                    inactive_status["payload"] if inactive_status is not None else {}
                )
                cleanup_record.update(
                    {
                        "active": (
                            bool(inactive_status["active"])
                            if inactive_status is not None
                            else None
                        ),
                        "active_bots": (
                            int(inactive_status["active_bots"])
                            if inactive_status is not None
                            else None
                        ),
                        "lease_count": int(
                            inactive_payload.get("lease_count") or 0
                        ) if inactive_status is not None else None,
                        "party_bot_count": int(
                            cohort_row.get("party_bot_count") or 0
                        ) if cohort_row is not None else None,
                        "server_epoch": int(registry.get("server_epoch") or 0),
                        "fixture_cleanup_required": fixture_cleanup_required,
                        "fixture_cleanup_submitted_or_absent": (
                            fixture_cleanup_submitted_or_absent
                        ),
                    }
                )
                status_server_epoch = int(inactive_payload.get("server_epoch") or 0)
                registry_server_epoch = int(registry.get("server_epoch") or 0)
                clean = (
                    not cleanup_errors
                    and inactive_status is not None
                    and not inactive_status["active"]
                    and int(inactive_status["active_bots"]) == 0
                    and int(inactive_payload.get("lease_count") or 0) == 0
                    and cohort_row is not None
                    and not bool(cohort_row.get("active"))
                    and int(cohort_row.get("lease_count") or 0) == 0
                    and int(cohort_row.get("party_bot_count") or 0) == 0
                    and fixture_cleanup_submitted_or_absent
                    and status_server_epoch == int(lifecycle["server_epoch"])
                    and registry_server_epoch == int(lifecycle["server_epoch"])
                )
                if not clean:
                    if not cleanup_errors:
                        cleanup_errors.append(
                            "cohort cleanup left active bots, leases, party state, or changed server epoch"
                        )
                    raise RuntimeError("cleanup quarantined: " + "; ".join(cleanup_errors))
                scheduler.close_active()
                lifecycle["scheduler_events"] = scheduler.events
                lifecycle["closed_at_unix"] = int(time.time())
                lifecycle["inactive_after_attempt"] = True
                lifecycle["worldserver_preserved"] = True
                if cleanup_record["server_epoch"] != lifecycle["server_epoch"]:
                    raise RuntimeError("server epoch changed during validation attempt")
            except Exception as exc:
                lifecycle["inactive_after_attempt"] = False
                lifecycle["cleanup_failure"] = str(exc)
                lifecycle["cleanup_quarantine_reason"] = str(exc)
                lifecycle["worldserver_preserved"] = True
                lifecycle["worldserver_healthy_after_cleanup_failure"] = None
                lifecycle["worldserver_pid_after_cleanup_failure"] = None
                try:
                    session_status = inspect_session(session)
                    pid_value = session_status.properties.get("MainPID") or 0
                    lifecycle["worldserver_healthy_after_cleanup_failure"] = bool(
                        session_status.healthy
                    )
                    lifecycle["worldserver_pid_after_cleanup_failure"] = (
                        int(pid_value) if str(pid_value).isdigit() else 0
                    )
                except Exception as inspection_exc:
                    lifecycle["worldserver_inspection_error"] = str(inspection_exc)
                raise
            finally:
                lifecycle["commands"] = executor.commands
                lifecycle["global_lifecycle_command_count"] = sum(
                    command_text in {".botauto start", ".botauto stop", ".botauto status"}
                    for command_text in executor.commands
                )
                write_json(args.output_dir / "session.json", lifecycle)
    # Joining after cleanup is deliberate: stop/status/cohort-registry output
    # is part of the immutable raw evidence, not an unretained side effect of
    # returning from the protected attempt body.
    return "".join(output_parts), returncode, timed_out, command, lifecycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or prepare live BotWorld validation diagnostics.")
    parser.add_argument("--worldserver", type=Path, default=Path("build/src/server/worldserver/worldserver"))
    parser.add_argument("--config", type=Path, default=Path("trinity-worldserver-test.conf"))
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/live_validation"))
    parser.add_argument("--duration-policy", choices=["completion-watchdog", "fixed-window"], default="completion-watchdog")
    parser.add_argument("--timeout-sec", type=int, default=None, help="Emergency wall-clock cap. Defaults to 90 seconds for fixed smoke checks and 900 seconds for watchdog validations. Expiry never counts as route success.")
    parser.add_argument("--run-to-completion", action="store_true", help="Stonecore session mode: no overall wall-clock deadline; terminate only on clear, attributable watchdog failure, or controller interruption.")
    parser.add_argument("--heartbeat-sec", type=int, default=DEFAULT_COMPLETION_HEARTBEAT_SEC)
    parser.add_argument("--no-progress-window-sec", type=int, default=DEFAULT_NO_PROGRESS_WINDOW_SEC)
    parser.add_argument("--max-repeated-decision-count", type=int, default=DEFAULT_MAX_REPEATED_DECISIONS)
    parser.add_argument("--max-death-loop-count", type=int, default=DEFAULT_MAX_DEATH_LOOPS)
    parser.add_argument("--selector", default="all")
    parser.add_argument("--trace-limit", type=int, default=128)
    parser.add_argument("--no-start", action="store_true")
    parser.add_argument("--force-start-command", action="store_true", help="Send .botauto start even when BotWorld.AutoStart is enabled in the selected worldserver config.")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--combat-calibration", action="store_true", help="Run isolated DPS/TPS training-dummy clones beside the validation cohort and attach their status to the report.")
    parser.add_argument("--calibration-only", action="store_true", help="Start an empty autonomy controller and run only the isolated combat-calibration clones, without a route/world cohort.")
    parser.add_argument("--calibration-reference-conditions", action="store_true", help="For calibration-only runs, apply real full-raid reference auras, target debuffs, and class-appropriate flasks without changing damage coefficients.")
    parser.add_argument("--calibration-self-provided-baseline", action="store_true", help="For calibration-only runs, use only exact inventory flask, food, pre-pot, and combat potion through native item use; do not manufacture raid buffs or target debuffs.")
    parser.add_argument("--calibration-mode", choices=["single_target_300", "aoe_300", "tank_threat_300", "healer_controlled_damage_300"], default="single_target_300")
    parser.add_argument("--calibration-target-spec", default="protection_paladin", help="Canonical all-spec target selected from the calibration candidate pool.")
    parser.add_argument("--calibration-seed", type=int, default=1, help="Deterministic calibration target/support selection seed.")
    parser.add_argument("--role-calibration-policy", type=Path, default=Path("experiments/configs/all_spec_role_calibration_policy_v1.json"), help="Versioned role/DPS threshold policy used for independent calibration acceptance.")
    parser.add_argument("--transport", choices=["process", "soap", "session"], default="process")
    parser.add_argument("--soap-url", default="http://127.0.0.1:7878/")
    parser.add_argument("--soap-user", default=os.environ.get("TRINITY_SOAP_USER"))
    parser.add_argument("--soap-password", default=os.environ.get("TRINITY_SOAP_PASSWORD"))
    parser.add_argument("--session-environment", default="default", help="Stable identity for the shared validation server and live-attempt lock.")
    parser.add_argument("--session-runtime-dir", type=Path, help="Stable directory for the shared session config and route manifest across serial attempts.")
    parser.add_argument("--preserve-worldserver", action="store_true", help="Require reusable-session transport so cleanup stops only this cohort/calibration fixture and leaves the worldserver running.")
    parser.add_argument("--session-profile", default="", help="Runtime profile selected by .botauto start in reusable session mode; defaults to the scenario ID.")
    parser.add_argument("--cohort-id", default="live-validation", help="Explicit cohort identity used by every reusable-session command.")
    parser.add_argument("--session-attempt-index", type=int, default=1, help="Immutable scheduler attempt index for reusable-session evidence.")
    parser.add_argument("--party-spec-target", action="append", default=[], help="Ordered exact-party class/spec target. Supply exactly five in tank, healer, then sorted DPS order.")
    parser.add_argument("--party-pool-tag", default="all_spec_candidate_pool", help="Immutable candidate-pool tag used with --party-spec-target.")
    parser.add_argument("--all-spec-target-catalog", type=Path, default=Path("experiments/configs/all_spec_targets_cata_p4_v1.json"), help="Canonical target catalog used to validate an exact party before live admission.")
    parser.add_argument("--session-transition-timeout-sec", type=int, default=180, help="Bound for reusable-session stop/start state transitions.")
    parser.add_argument("--publish-batch", action="store_true", help="Capture, DVC-push, remotely verify, and target-evict the closed reusable-session batch.")
    parser.add_argument("--retain-published-batch", action="store_true", help="Keep raw and compact batch files locally after verified publication.")
    parser.add_argument("--reload-rotation-profiles", action="store_true", help="Ask the server owner to atomically reload DB-only rotation tuning before admission.")
    parser.add_argument("--evidence-identity-manifest", type=Path, help="Canonical Phase 2 component hashes and scope IDs; DB/schema/epoch/profile generation hashes are required for certifying acceptance.")
    parser.add_argument("--observe-sec", type=int, default=None, help="Fixed-window observation delay for non-route diagnostics. Raid/dungeon routes poll at --heartbeat-sec; isolated DPS calibration owns its native 300-second scoring window.")
    parser.add_argument("--reset-bot-pool", action="store_true", help="Before validation, reset volatile state for enabled bot-pool rows matching --bot-pool-tag.")
    parser.add_argument("--bot-pool-tag", action="append", default=[], help="Experiment tag substring for --reset-bot-pool. Defaults to test_account when omitted.")
    parser.add_argument("--keep-bot-pool-position", action="store_true", help="Do not move reset bot-pool characters back to race/class start positions.")
    parser.add_argument("--keep-bot-pool-quests", action="store_true", help="Do not clear quest/aura/cooldown state for reset bot-pool characters.")
    parser.add_argument("--keep-bot-pool-memory", action="store_true", help="Do not clear persistent bot memory tables for reset bot-pool characters.")
    parser.add_argument("--apply-validation-provisioning", action="store_true", help="Apply deterministic Stonecore/BWD validation account and character SQL before running diagnostics.")
    parser.add_argument("--prepare-only", action="store_true", help="Apply requested deterministic provisioning and route-start state, write a report, and exit without launching a worldserver.")
    parser.add_argument("--validation-provisioning-config", type=Path, default=Path("experiments/configs/validation_provisioning_cata_001.json"))
    parser.add_argument("--bwd-diagnostic-shard-fixture", type=Path, default=DEFAULT_BWD_DIAGNOSTIC_SHARD_FIXTURE)
    parser.add_argument("--gear-profiles", type=Path, default=Path("dataset/validation_gear_profiles/profiles.json"))
    parser.add_argument("--scenario-report-dir", type=Path, help="Optional directory or JSON file containing scenario live reports such as stonecore_5h.json and blackwing_descent_10n.json.")
    parser.add_argument("--validation-scenario-id", default="", help="Scenario ID this live validation run is measuring.")
    parser.add_argument("--validation-segment-id", default="", help="Boss/route segment ID this live validation run is measuring.")
    parser.add_argument("--validation-route-node-id", default="", help="Route node ID this live validation run is measuring.")
    parser.add_argument("--validation-route-label", default="", help="Human-readable route label this live validation run is measuring.")
    parser.add_argument("--validation-route-kind", default="", help="Route node kind this live validation run is measuring, such as boss or trash.")
    parser.add_argument("--validation-route-step", type=int, default=0, help="Route step number this live validation run is measuring.")
    parser.add_argument("--validation-mechanic-profile", default="", help="Mechanic profile associated with this live validation segment.")
    parser.add_argument("--validation-scenario-dir", type=Path, default=Path("dataset/validation_scenarios"), help="Directory containing validation_routes.jsonl for route-directed live validation.")
    parser.add_argument("--validation-route-manifest", action="store_true", help="For a scenario-level uninterrupted run, write the ordered route manifest and configure the first route without segment context.")
    parser.add_argument("--validation-route-sequence", action="store_true", help="For a scenario-level run, execute executable route nodes in manifest order and write an aggregate sequence report.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--input-log", type=Path)
    args = parser.parse_args()

    if args.calibration_only:
        args.combat_calibration = True
        if args.validation_route_manifest or args.validation_route_sequence:
            raise SystemExit("--calibration-only cannot be combined with a validation route manifest or sequence")
        if args.transport == "soap" and not args.input_log:
            raise SystemExit("--calibration-only cannot use SOAP because an empty controller config cannot be established")
    if args.calibration_reference_conditions and not args.calibration_only:
        raise SystemExit("--calibration-reference-conditions requires --calibration-only")
    if args.calibration_self_provided_baseline and not args.calibration_only:
        raise SystemExit("--calibration-self-provided-baseline requires --calibration-only")
    if args.calibration_reference_conditions and args.calibration_self_provided_baseline:
        raise SystemExit("calibration reference conditions and self-provided baseline are mutually exclusive")
    if args.calibration_self_provided_baseline and not args.reset_bot_pool:
        raise SystemExit(
            "--calibration-self-provided-baseline requires --reset-bot-pool "
            "so each attempt receives fresh inventory-backed consumables"
        )
    if args.session_runtime_dir and args.transport != "session":
        raise SystemExit("--session-runtime-dir requires --transport session")
    if args.preserve_worldserver and (
        args.transport != "session" or args.session_runtime_dir is None
    ):
        raise SystemExit(
            "--preserve-worldserver requires --transport session and "
            "--session-runtime-dir"
        )
    if args.prepare_only:
        if args.transport == "session" or args.input_log or args.dry_run:
            raise SystemExit("--prepare-only requires a live non-session preparation run")
        if not args.apply_validation_provisioning:
            raise SystemExit("--prepare-only requires --apply-validation-provisioning")
    if args.transport == "soap" and not args.input_log and (
        args.validation_scenario_id or args.validation_route_manifest or args.validation_route_sequence
    ):
        raise SystemExit("scenario-scoped validation cannot use SOAP because the server config identity is not owned")
    if args.transport == "session" and args.validation_scenario_id and args.session_profile and args.session_profile != args.validation_scenario_id:
        raise SystemExit("--session-profile must equal --validation-scenario-id for validation sessions")
    route_validation_requested = bool(
        args.validation_scenario_id
        or args.validation_segment_id
        or args.validation_route_node_id
        or args.validation_route_kind
        or args.validation_route_manifest
        or args.validation_route_sequence
    )
    if route_validation_requested and args.duration_policy != "completion-watchdog":
        raise SystemExit(
            "raid/dungeon validation requires --duration-policy "
            "completion-watchdog"
        )
    if route_validation_requested and args.observe_sec is not None:
        raise SystemExit(
            "--observe-sec is not a raid/dungeon completion timer; use "
            "--heartbeat-sec and the typed watchdogs"
        )
    if args.run_to_completion and not (
        args.transport == "session"
        and args.duration_policy == "completion-watchdog"
        and args.validation_scenario_id == "stonecore_5h"
        and args.party_spec_target
        and args.timeout_sec is None
    ):
        raise SystemExit(
            "--run-to-completion requires an exact-party Stonecore session "
            "without --timeout-sec"
        )

    exact_party_specs = [str(value) for value in args.party_spec_target]
    if exact_party_specs:
        if args.transport != "session":
            raise SystemExit("--party-spec-target requires --transport session")
        if args.validation_scenario_id != "stonecore_5h":
            raise SystemExit("--party-spec-target requires --validation-scenario-id stonecore_5h")
        if len(exact_party_specs) != 5 or len(set(exact_party_specs)) != 5:
            raise SystemExit("--party-spec-target requires exactly five unique targets")
        if not args.party_pool_tag:
            raise SystemExit("--party-pool-tag must be non-empty with --party-spec-target")
        target_catalog_path = args.all_spec_target_catalog
        if not target_catalog_path.is_absolute():
            target_catalog_path = REPO_ROOT / target_catalog_path
        target_catalog = json.loads(target_catalog_path.read_text(encoding="utf-8"))
        target_roles = {
            str(row.get("spec_target_id") or ""): str(row.get("role") or "")
            for row in target_catalog.get("targets") or []
        }
        if any(target not in target_roles for target in exact_party_specs):
            raise SystemExit("--party-spec-target contains an unknown canonical target")
        if [target_roles[target] for target in exact_party_specs] != ["tank", "healer", "dps", "dps", "dps"]:
            raise SystemExit("--party-spec-target order must be tank, healer, then three DPS")
        if exact_party_specs[2:] != sorted(exact_party_specs[2:]):
            raise SystemExit("--party-spec-target DPS targets must be canonically sorted")

    calibration_reference_preflight = preflight_calibration_reference_binding(
        calibration_only=args.calibration_only,
        calibration_mode=args.calibration_mode,
        target_spec=args.calibration_target_spec,
    )
    validation_scenario_stage_preflight = preflight_validation_scenario_stage(
        args.validation_scenario_dir,
        args.validation_scenario_id,
        profile_name=args.session_profile or args.validation_scenario_id,
        pool_tag=(
            args.party_pool_tag
            if exact_party_specs
            else (args.bot_pool_tag[0] if len(args.bot_pool_tag) == 1 else None)
        ),
        enabled=route_validation_requested and not args.input_log,
    )

    if args.run_to_completion:
        args.timeout_sec = None
        args.observe_sec = args.observe_sec if args.observe_sec is not None else args.heartbeat_sec
    elif args.duration_policy == "completion-watchdog":
        args.timeout_sec = args.timeout_sec if args.timeout_sec is not None else DEFAULT_BOSS_ROUTE_TIMEOUT_SEC
        args.observe_sec = args.observe_sec if args.observe_sec is not None else args.heartbeat_sec
    else:
        args.timeout_sec = args.timeout_sec if args.timeout_sec is not None else DEFAULT_LIVE_VALIDATION_TIMEOUT_SEC
        args.observe_sec = args.observe_sec if args.observe_sec is not None else 0

    output_dir_is_available = session_output_dir_available(args.output_dir)
    if args.transport == "session" and not output_dir_is_available and not args.dry_run and not args.input_log:
        raise SystemExit("--transport session requires a new or empty --output-dir")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    bot_pool_tags = [args.party_pool_tag] if exact_party_specs else (args.bot_pool_tag or ["test_account"])

    if args.validation_route_sequence:
        if not args.validation_scenario_id:
            raise SystemExit("--validation-route-sequence requires --validation-scenario-id")
        if args.input_log:
            raise SystemExit("--validation-route-sequence cannot be combined with --input-log")
        sequence_routes = load_validation_routes_for_scenario(args.validation_scenario_dir, args.validation_scenario_id)
        validate_route_runtime_profile_contract(args.config, args.validation_scenario_dir, args.validation_scenario_id, sequence_routes)
        commands = [
            route_sequence_child_command(args, route, args.output_dir / route_segment_output_name(route), first_route=index == 0)
            for index, route in enumerate(sequence_routes)
        ]
        if args.dry_run:
            report = {
                "schema": "bot_live_validation_report_v1",
                "dry_run": True,
                "validation_context": {"scenario_id": args.validation_scenario_id},
                "route_sequence": {
                    "schema": "bot_live_validation_route_sequence_v1",
                    "scenario_id": args.validation_scenario_id,
                    "route_count": len(sequence_routes),
                    "expected_segments": [route_segment_output_name(route) for route in sequence_routes],
                    "commands": commands,
                },
                "runtime_ml_control": "offline_shadow_only",
                "control_eligible": False,
            }
            write_json(args.output_dir / "report.json", report)
            (args.output_dir / "commands.txt").write_text("\n".join(render_command(command) for command in commands) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        return run_route_sequence(args, sequence_routes)

    session_runtime_dir = (
        args.session_runtime_dir.resolve()
        if args.transport == "session" and args.session_runtime_dir
        else args.output_dir
    )
    validation_context = validation_context_from_args(args)
    validation_route = load_validation_route(args.validation_scenario_dir, validation_context)
    if validation_route:
        validation_context = route_validation_context(args.validation_scenario_id, validation_route, include_segment=bool(args.validation_segment_id))
    validation_route_manifest: dict[str, Any] = {}
    validation_route_manifest_path: Path | None = None
    if args.validation_route_manifest:
        if not args.validation_scenario_id:
            raise SystemExit("--validation-route-manifest requires --validation-scenario-id")
        manifest_routes = load_validation_routes_for_scenario(args.validation_scenario_dir, args.validation_scenario_id)
        validate_route_runtime_profile_contract(args.config, args.validation_scenario_dir, args.validation_scenario_id, manifest_routes)
        validation_route_manifest_path, validation_route_manifest = write_validation_route_manifest(
            session_runtime_dir,
            args.validation_scenario_id,
            manifest_routes,
        )
        if not validation_route and manifest_routes:
            validation_route = manifest_routes[0]
    pool_tag_filter = str(
        args.party_pool_tag
        if exact_party_specs
        else (validation_context.get("scenario_id") or (bot_pool_tags[0] if bot_pool_tags else ""))
    )
    effective_config = args.config
    if args.transport in {"process", "session"} and not args.input_log:
        effective_config = write_validation_config(
            args.config,
            session_runtime_dir,
            pool_tag_filter,
            validation_route,
            validation_route_manifest_path,
            autostart=False if args.transport == "session" else (True if args.calibration_only else not args.no_start),
            calibration_only=args.calibration_only,
            calibration_reference_conditions=args.calibration_reference_conditions,
            calibration_self_provided_baseline=args.calibration_self_provided_baseline,
            console_enabled=False if args.transport == "session" else None,
        )
    config_autostart = trinity_config_bool(effective_config, "BotWorld.AutoStart", False)
    send_start_command = not args.no_start and (args.force_start_command or not config_autostart)
    script = command_script(
        selector=args.selector,
        trace_limit=args.trace_limit,
        start=send_start_command if args.transport != "session" else False,
        stop=args.stop if args.transport != "session" else False,
        exit_server=args.transport == "process",
        combat_calibration=args.combat_calibration,
        cohort_id=args.cohort_id if args.transport == "session" else "",
        calibration_mode=args.calibration_mode,
        calibration_target_spec=args.calibration_target_spec,
        calibration_seed=args.calibration_seed,
        calibration_only=args.calibration_only,
        trace_delta=args.duration_policy == "completion-watchdog",
    )
    (args.output_dir / "commands.txt").write_text(script, encoding="utf-8")
    preparation: dict[str, Any] = {}
    scenario_reports = load_scenario_reports(args.scenario_report_dir)
    if args.reset_bot_pool:
        preparation["bot_pool_reset"] = prepare_bot_pool_reset(
            args.output_dir,
            args.config,
            bot_pool_tags,
            apply=not args.dry_run and args.transport != "session",
            reset_positions=not args.keep_bot_pool_position,
            reset_quests=not args.keep_bot_pool_quests,
            reset_memory=not args.keep_bot_pool_memory,
        )
    if args.apply_validation_provisioning:
        preparation["validation_provisioning"] = prepare_validation_provisioning(
            args.output_dir,
            args.validation_provisioning_config,
            args.gear_profiles,
            args.config,
            args.bwd_diagnostic_shard_fixture,
            apply=not args.dry_run and args.transport != "session",
        )
        if args.transport == "process" and not args.input_log:
            effective_config = bind_validation_provisioning_sql(
                effective_config,
                preparation["validation_provisioning"],
            )
    if args.calibration_only and args.calibration_self_provided_baseline and args.transport != "session":
        if "bot_pool_reset" not in preparation:
            preparation["bot_pool_reset"] = prepare_bot_pool_reset(
                args.output_dir,
                args.config,
                bot_pool_tags,
                apply=not args.dry_run,
                reset_positions=not args.keep_bot_pool_position,
                reset_quests=not args.keep_bot_pool_quests,
                reset_memory=not args.keep_bot_pool_memory,
            )
        preparation["calibration_consumables"] = prepare_calibration_consumables(
            args.output_dir,
            args.config,
            args.calibration_target_spec,
            args.all_spec_target_catalog.resolve(),
            apply=not args.dry_run,
        )
    if validation_route and int(validation_route.get("bot_start_map_id") or 0):
        preparation["route_bot_start"] = server_route_start_contract(validation_route)

    if args.prepare_only:
        report = {
            "schema": "bot_live_validation_preparation_v1",
            "prepared": True,
            "worldserver_started": False,
            "validation_context": validation_context,
            "validation_route_manifest": validation_route_manifest,
            "pool_tags": bot_pool_tags,
            "validation_scenario_stage_preflight": validation_scenario_stage_preflight,
            "preparation": preparation,
        }
        write_json(args.output_dir / "report.json", report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.dry_run:
        report = {
            "schema": "bot_live_validation_report_v1",
            "dry_run": True,
            "command_script": script,
            "worldserver": str(args.worldserver),
            "config": str(effective_config),
            "base_config": str(args.config),
            "pool_tag_filter": pool_tag_filter,
            "exact_party_pool_tag": args.party_pool_tag if exact_party_specs else "",
            "exact_party_class_specs": exact_party_specs,
            "exact_party_sha256": canonical_sha256(exact_party_specs) if exact_party_specs else "",
            "validation_route": validation_route,
            "validation_route_manifest": validation_route_manifest,
            "validation_route_manifest_path": str(validation_route_manifest_path or ""),
            "transport": args.transport,
            "preserve_worldserver_required": args.preserve_worldserver,
            "soap_url": args.soap_url if args.transport == "soap" else "",
            "duration_policy": args.duration_policy,
            "execution_policy": (
                "run_to_completion"
                if args.run_to_completion
                else "bounded_wall_clock"
            ),
            "overall_wall_clock_timeout_sec": args.timeout_sec,
            "timeout_sec": args.timeout_sec,
            "observe_sec": args.observe_sec,
            "heartbeat_sec": args.heartbeat_sec,
            "no_progress_window_sec": args.no_progress_window_sec,
            "max_repeated_decision_count": args.max_repeated_decision_count,
            "max_death_loop_count": args.max_death_loop_count,
            "config_autostart": config_autostart,
            "start_command": send_start_command,
            "calibration_only": args.calibration_only,
            "calibration_reference_conditions": args.calibration_reference_conditions,
            "calibration_self_provided_baseline": args.calibration_self_provided_baseline,
            "calibration_reference_preflight": calibration_reference_preflight,
            "validation_scenario_stage_preflight": validation_scenario_stage_preflight,
            "preparation": preparation,
            "scenario_reports": scenario_reports,
            "validation_context": validation_context,
            "instructions": "Run make host-world-botexp-small for attached diagnostics or execute this script without --dry-run when the worldserver binary and config are ready.",
        }
        write_json(args.output_dir / "report.json", report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    watchdog_report: dict[str, Any] | None = None
    session_lifecycle: dict[str, Any] = {}
    if args.input_log:
        output = args.input_log.read_text(encoding="utf-8")
        returncode = 0
        timed_out = False
        command: list[str] = []
    else:
        if args.transport == "soap":
            if not args.soap_user or not args.soap_password:
                raise SystemExit("--soap-user and --soap-password are required with --transport soap")
            if args.duration_policy == "completion-watchdog":
                def execute_soap(command_text: str, remaining: int) -> tuple[str, int, bool]:
                    return execute_soap_command(args.soap_url, args.soap_user, args.soap_password, command_text, remaining)

                output, returncode, timed_out, command = run_transport_completion_watchdog(
                    execute_soap,
                    ["SOAP", args.soap_url],
                    args.timeout_sec,
                    script,
                    args.output_dir,
                    scenario_reports,
                    validation_context,
                    duration_policy=args.duration_policy,
                    heartbeat_sec=args.heartbeat_sec,
                    no_progress_window_sec=args.no_progress_window_sec,
                    max_repeated_decisions=args.max_repeated_decision_count,
                    max_death_loops=args.max_death_loop_count,
                )
                existing_report = args.output_dir / "report.json"
                if existing_report.exists():
                    try:
                        watchdog_report = json.loads(existing_report.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        watchdog_report = None
            else:
                output, returncode, timed_out, command = run_soap_commands(args.soap_url, args.soap_user, args.soap_password, script, args.timeout_sec, args.observe_sec)
        elif args.transport == "session":
            session_args = argparse.Namespace(**vars(args))
            session_args.config = effective_config
            output, returncode, timed_out, command, session_lifecycle = run_reusable_validation_session(
                session_args,
                script,
                scenario_reports,
                validation_context,
                validation_route,
                validation_route_manifest,
                validation_route_manifest_path,
                bot_pool_tags,
            )
            preparation = session_lifecycle.get("preparation") or preparation
            existing_report = args.output_dir / "report.json"
            if existing_report.exists():
                try:
                    watchdog_report = json.loads(existing_report.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    watchdog_report = None
        elif args.duration_policy == "completion-watchdog":
            output, returncode, timed_out, command = run_worldserver_completion_watchdog(
                args.worldserver,
                effective_config,
                args.timeout_sec,
                script,
                args.output_dir,
                scenario_reports,
                validation_context,
                duration_policy=args.duration_policy,
                heartbeat_sec=args.heartbeat_sec,
                no_progress_window_sec=args.no_progress_window_sec,
                max_repeated_decisions=args.max_repeated_decision_count,
                max_death_loops=args.max_death_loop_count,
                validation_route=validation_route,
                validation_route_manifest=validation_route_manifest,
            )
            existing_report = args.output_dir / "report.json"
            if existing_report.exists():
                try:
                    watchdog_report = json.loads(existing_report.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    watchdog_report = None
        else:
            output, returncode, timed_out, command = run_worldserver(args.worldserver, effective_config, args.timeout_sec, script, args.observe_sec)

    # Keep an incomplete combat-log transfer intact so a missing or malformed
    # sequence remains diagnosable. A successfully decoded export has its own
    # compact artifacts and may discard the transport-only base64 frames.
    parsed_output_payloads = parse_json_objects(output)
    output_combat_transport = combat_log_transport_status(
        parsed_output_payloads
    )
    incomplete_combat_transport = bool(
        output_combat_transport.get("attempt_count")
        and not output_combat_transport.get("reassembled")
    )
    retained_console_output = (
        output if incomplete_combat_transport
        else strip_combat_log_chunks(output)
    )
    (args.output_dir / "worldserver_output.log").write_text(
        retained_console_output,
        encoding="utf-8",
    )
    if watchdog_report:
        report = watchdog_report
        report["returncode"] = returncode
        report["timed_out"] = timed_out
        report["command"] = command
        final_payloads = classify_payloads(parsed_output_payloads)
        report["json_payloads"] = len(parsed_output_payloads)
        report["combat_log_transport"] = final_payloads["combat_log_transport"]
        report["combat_calibration_transport"] = final_payloads[
            "combat_calibration_transport"
        ]
        if final_payloads.get("combat_log"):
            report["combat_log"] = final_payloads["combat_log"]
            report["combat_analysis"] = analyze_combat_log(
                final_payloads["combat_log"]
            )
        if final_payloads.get("combat_calibration"):
            report["combat_calibration"] = enrich_combat_calibration_reference(
                final_payloads["combat_calibration"]
            )
        if incomplete_combat_transport:
            label = "combat_log_transport_incomplete"
            labels = report.setdefault("failure_labels", [])
            if label not in labels:
                labels.append(label)
            report["failure_reason"] = labels[0]
            report["all_passed"] = False
            report["acceptable_final_evidence"] = False
            rejections = report.setdefault("final_evidence_rejections", [])
            if "failure_labels_present" not in rejections:
                rejections.append("failure_labels_present")
    else:
        report = live_validation_report(
            output,
            returncode=returncode,
            timed_out=timed_out,
            command=command,
            scenario_reports=scenario_reports,
            validation_context=validation_context,
            validation_route_manifest=validation_route_manifest,
            duration_policy=args.duration_policy,
            heartbeat_sec=args.heartbeat_sec,
            no_progress_window_sec=args.no_progress_window_sec,
            max_repeated_decisions=args.max_repeated_decision_count,
            max_death_loops=args.max_death_loop_count,
        )
    report["generated_at_unix"] = int(time.time())
    report["config_autostart"] = config_autostart
    report["config"] = str(effective_config)
    report["base_config"] = str(args.config)
    report["pool_tag_filter"] = pool_tag_filter
    report["exact_party_pool_tag"] = args.party_pool_tag if exact_party_specs else ""
    report["exact_party_class_specs"] = exact_party_specs
    report["exact_party_sha256"] = canonical_sha256(exact_party_specs) if exact_party_specs else ""
    report["validation_route"] = validation_route
    report["validation_route_manifest"] = validation_route_manifest
    report["validation_route_manifest_path"] = str(validation_route_manifest_path or "")
    report["start_command"] = send_start_command
    report["calibration_only"] = args.calibration_only
    report["calibration_reference_conditions"] = args.calibration_reference_conditions
    report["calibration_self_provided_baseline"] = args.calibration_self_provided_baseline
    report["calibration_reference_preflight"] = calibration_reference_preflight
    report["validation_scenario_stage_preflight"] = validation_scenario_stage_preflight
    report["preserve_worldserver_required"] = args.preserve_worldserver
    report["execution_policy"] = (
        "run_to_completion" if args.run_to_completion else "bounded_wall_clock"
    )
    report["overall_wall_clock_timeout_sec"] = args.timeout_sec
    report["requested_calibration"] = {
        "mode": args.calibration_mode,
        "target_spec": args.calibration_target_spec,
        "seed": max(1, args.calibration_seed),
    }
    report["preparation"] = preparation
    if args.transport == "session":
        report["session"] = session_lifecycle
        if not session_lifecycle.get("inactive_after_attempt"):
            report["acceptable_final_evidence"] = False
            report["all_passed"] = False
    report["validation_context"] = validation_context
    report["live_validation_standard"] = build_live_validation_standard_marker(
        report, session_lifecycle
    )
    if report.get("combat_log"):
        report["combat_analysis"] = analyze_combat_log(report["combat_log"])
        write_json(args.output_dir / "combat_log.json", report["combat_log"])
        write_json(args.output_dir / "combat_analysis.json", report["combat_analysis"])
        report["combat_log_path"] = str(args.output_dir / "combat_log.json")
        report["combat_log_summary"] = {
            key: report["combat_log"].get(key)
            for key in (
                "combat_log_schema_version",
                "event_count",
                "aggregate_count",
                "second_bucket_count",
                "recent_events_dropped",
            )
        }
        report["combat_log"] = {}
    attach_stonecore_role_quality_audit(report, validation_context, validation_route_manifest)
    if args.calibration_only:
        apply_calibration_only_acceptance(report)
        attach_phase8_role_calibration(report, policy_path=args.role_calibration_policy)
    report["evidence_envelope"] = attempt_evidence_envelope(
        args,
        report,
        validation_context,
        validation_route_manifest,
        session_lifecycle,
    )
    report = AcceptanceRecomputer().recompute(
        report,
        identity_required=True,
        session_required=args.transport == "session",
    )
    if args.transport == "session":
        attempt = ValidationAttempt(
            cohort_id=args.cohort_id,
            attempt_index=args.session_attempt_index,
            profile=args.session_profile or str(validation_context.get("scenario_id") or ""),
            output_dir=args.output_dir,
            timeout_sec=args.timeout_sec,
            observe_sec=args.observe_sec,
        )
        capture_manifest = ImmutableCaptureWriter(REPO_ROOT).capture(
            attempt,
            report,
            output,
            {
                "evidence_envelope": report["evidence_envelope"],
                "session": session_lifecycle,
                "validation_context": validation_context,
                "validation_route_manifest": validation_route_manifest,
            },
            returncode=returncode,
            timed_out=timed_out,
        )
        report["batch_capture"] = capture_manifest
        if args.publish_batch:
            report["batch_publication"] = SerializedDvcPublisher(
                REPO_ROOT,
                evict_after_verify=not args.retain_published_batch,
            ).publish(args.output_dir / "batch")
    stored_report = report
    if args.transport == "session" and args.publish_batch:
        stored_report = compact_published_report(report)
        for name in (
            "combat_analysis.json",
            "combat_log.json",
            "heartbeat_events.jsonl",
            "latest.json",
            "worldserver_output.log",
        ):
            (args.output_dir / name).unlink(missing_ok=True)
    write_json(args.output_dir / "report.json", stored_report)
    print(json.dumps(stored_report, indent=2, sort_keys=True))
    segment_success = route_segment_complete(report, validation_route)
    full_success = bool(report.get("acceptable_final_evidence")) and bool(report.get("all_passed"))
    return 0 if returncode == 0 and not timed_out and (segment_success or full_success) else 1


if __name__ == "__main__":
    raise SystemExit(main())
