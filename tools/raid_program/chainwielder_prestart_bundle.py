"""Create and verify one atomic Chainwielder checkpoint prestart bundle."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

from tools.raid_program.canonical_route_staging import (
    CanonicalRouteStagingError,
    STAGING_RECEIPT_SCHEMA,
    atomic_write_new,
    stage_canonical_route as _stage_canonical_route,
)
from tools.raid_program.queued_build import (
    CoordinatorError,
    load_json as load_build_json,
    verify_receipt,
)
from tools.raid_program.recurrence_admission import (
    CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX,
    CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
    FIXTURE_EXPANSION_PURPOSE,
    PROFILE_MANIFEST_RELATIVE_PATH,
    RecurrenceAdmissionError,
    chainwielder_checkpoint_seal,
    build_runtime_profile_suffix_manifest,
    create_recurrence_admission,
    sha256_file,
    verify_recurrence_admission,
)


SCHEMA = "cata_raid_chainwielder_prestart_bundle_v1"
LAUNCH_SCHEMA = "cata_raid_chainwielder_launch_contract_v1"
MANIFEST_SCHEMA = "cata_raid_chainwielder_bundle_manifest_v1"
FAILURE_SCHEMA = "cata_raid_chainwielder_prestart_failure_v1"
SCENARIO_ID = "blackwing_descent_10n_magmaw_diagnostic"
NODE_ID = "bwd.magmaw.chainwielder"
ACTOR_GUID = 30008
MAP_ID = 669
TARGET_ENTRY = 42649
ACTOR_COUNT = 10
SHA256_RE = re.compile(r"[0-9a-f]{64}")
TRACKED_LEDGER_RELATIVE_PATH = Path(
    "experiments/configs/cata_raid_magmaw_blocker_recurrence_v1.json"
)
BUNDLE_NAMES = {
    "source_route_manifest": "source_route_manifest.json",
    "route_manifest": "route_manifest.json",
    "profile_manifest": "runtime_profiles.json",
    "runtime_config": "worldserver.validation.conf",
    "base_runtime_config": "prepared_base_runtime.conf",
    "build_receipt": "build_receipt.json",
    "build_policy": "build_policy.json",
    "ledger": "recurrence_ledger.json",
    "decision": "recurrence_decision.json",
    "suite_receipt": "regression_suite_receipt.json",
    "checkpoint_seal": "checkpoint_seal.json",
    "admission": "recurrence_admission.json",
    "launch_contract": "launch_contract.json",
    "bundle_manifest": "bundle_manifest.json",
}

REQUIRED_SUFFIX_NODE_IDS = (
    NODE_ID,
    "bwd.magmaw.drudges",
    "bwd.magmaw.encounter",
)
ROUTE_INVARIANT_FIELDS = (
    "bot_start_map_id",
    "bot_start_x",
    "bot_start_y",
    "bot_start_z",
    "bot_start_o",
    "roster_identity",
    "diagnostic_only",
    "diagnostic_parent_scenario_id",
    "diagnostic_prerequisite_state",
)

CONFIG_VALUES = {
    "BotWorld.AutoStart": "0",
    "BotWorld.RuntimeProfile": f'"{SCENARIO_ID}"',
    "BotWorld.PoolTagFilter": f'"{SCENARIO_ID}"',
    "BotWorld.TargetPopulation": str(ACTOR_COUNT),
    "BotWorld.ValidationRoute.Enable": "1",
    "BotWorld.ValidationRoute.AdvanceMode": '"terminal"',
    "BotWorld.ValidationRoute.ScenarioId": f'"{SCENARIO_ID}"',
    "BotWorld.ValidationRoute.NodeId": f'"{NODE_ID}"',
    "BotWorld.ValidationRoute.Map": str(MAP_ID),
    "BotWorld.ValidationRoute.TargetEntry": str(TARGET_ENTRY),
    "BotWorld.ValidationRoute.PrepullCheckpointEnable": "1",
    "BotProgression.AllowRaids": "1",
    f"{CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX}.Enable": "1",
    f"{CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX}.FixtureId": (
        f'"{CHAINWIELDER_CHECKPOINT_FIXTURE_ID}"'
    ),
}


class BundleError(RuntimeError):
    pass


def _git(worktree: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(worktree), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout if binary else result.stdout.decode().strip()


def _json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise BundleError(f"{label}_missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BundleError(f"{label}_invalid") from error
    if not isinstance(value, dict):
        raise BundleError(f"{label}_invalid")
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _canonical_pretty_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _require_hash(path: Path, expected: str, label: str) -> None:
    if not SHA256_RE.fullmatch(expected):
        raise BundleError(f"{label}_sha256_invalid")
    if not path.is_file():
        raise BundleError(f"{label}_missing")
    if sha256_file(path) != expected:
        raise BundleError(f"{label}_hash_mismatch")


def _source_identity(
    worktree: Path, expected_commit: str, expected_tree: str
) -> tuple[str, str]:
    worktree = worktree.resolve()
    head = str(_git(worktree, "rev-parse", "HEAD"))
    tree = str(_git(worktree, "rev-parse", "HEAD^{tree}"))
    if head != expected_commit or tree != expected_tree:
        raise BundleError("source_identity_mismatch")
    porcelain = _git(worktree, "status", "--porcelain=v1", "-z", binary=True)
    if porcelain:
        raise BundleError("source_worktree_dirty")
    return head, tree


def _tracked_profile_manifest(worktree: Path) -> tuple[Path, dict[str, Any]]:
    path = worktree.resolve() / PROFILE_MANIFEST_RELATIVE_PATH
    try:
        committed = _git(
            worktree, "show", f"HEAD:{PROFILE_MANIFEST_RELATIVE_PATH.as_posix()}",
            binary=True,
        )
        payload = path.read_bytes()
    except (OSError, subprocess.SubprocessError) as error:
        raise BundleError("source_profile_manifest_not_tracked") from error
    if payload != committed:
        raise BundleError("source_profile_manifest_commit_mismatch")
    return path, _json(path, "source_profile_manifest")


def _validate_locations(
    *, worktree: Path, output_dir: Path, material_inputs: dict[str, Path],
    binary: Path, capture_paths: list[Path],
    read_only_source_inputs: set[str] | None = None,
    exact_read_only_source_inputs: dict[str, Path] | None = None,
) -> None:
    worktree = worktree.resolve()
    output = output_dir.resolve()
    if _is_within(output, worktree):
        raise BundleError("output_inside_worktree")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise BundleError("output_not_empty")
    for label, path in material_inputs.items():
        resolved = path.resolve()
        if _is_within(resolved, worktree):
            if label not in (read_only_source_inputs or set()):
                raise BundleError(f"{label}_inside_mutable_worktree")
            relative = resolved.relative_to(worktree).as_posix()
            required_relative = (exact_read_only_source_inputs or {}).get(label)
            if required_relative is not None:
                expected = worktree / required_relative
                lexical = Path(os.path.abspath(path))
                if (
                    lexical != expected
                    or expected.resolve() != expected
                    or resolved != expected
                ):
                    raise BundleError(f"{label}_source_path_mismatch")
            try:
                _git(worktree, "ls-files", "--error-unmatch", relative)
                _git(worktree, "cat-file", "-e", f"HEAD:{relative}")
            except subprocess.CalledProcessError as error:
                raise BundleError(f"{label}_not_tracked_read_only_source") from error
        if _is_within(resolved, output) or resolved == output:
            raise BundleError(f"{label}_aliases_output")
    for path in capture_paths:
        resolved = path.resolve()
        if _is_within(resolved, worktree) or _is_within(resolved, output):
            raise BundleError("capture_output_location_invalid")
    if not binary.resolve().is_file():
        raise BundleError("binary_missing")


def _config_assignments(text: str, key: str) -> list[re.Match[str]]:
    pattern = re.compile(
        rf"^(?!\s*[#;])\s*{re.escape(key)}\s*=.*$", re.MULTILINE
    )
    return list(pattern.finditer(text))


def _set_config(text: str, key: str, value: str) -> str:
    matches = _config_assignments(text, key)
    if len(matches) > 1:
        raise BundleError(f"config_duplicate_key:{key}")
    line = f"{key} = {value}"
    if matches:
        match = matches[0]
        return text[:match.start()] + line + text[match.end():]
    return text.rstrip() + "\n" + line + "\n"


def _config_value(text: str, key: str) -> str:
    matches = _config_assignments(text, key)
    if len(matches) != 1:
        reason = "missing" if not matches else "duplicate"
        raise BundleError(f"config_{reason}_key:{key}")
    return matches[0].group(0).split("=", 1)[1].strip()


def _render_config(
    base: Path, *, route_path: Path, profile_manifest_path: Path,
    seal: dict[str, str], source_commit: str,
) -> bytes:
    try:
        text = base.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise BundleError("base_runtime_config_invalid") from error
    values = {
        **CONFIG_VALUES,
        "BotWorld.ValidationRoute.ManifestPath": f'"{route_path}"',
        "BotWorld.ProfileManifest": f'"{profile_manifest_path}"',
        f"{CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX}.SealSha256": (
            f'"{seal["seal_sha256"]}"'
        ),
        f"{CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX}.SourceCommit": (
            f'"{source_commit}"'
        ),
    }
    for key, value in values.items():
        text = _set_config(text, key, value)
    for key, value in values.items():
        if _config_value(text, key) != value:
            raise BundleError(f"config_binding_mismatch:{key}")
    return text.encode("utf-8")


def _validate_route(path: Path, scenario: str, profile: str) -> dict[str, Any]:
    route = _json(path, "route_manifest")
    if route.get("scenario_id") != scenario:
        raise BundleError("route_scenario_mismatch")
    rows = route.get("routes")
    if not isinstance(rows, list):
        rows = [route]
    matching = [row for row in rows if isinstance(row, dict) and row.get("route_node_id") == NODE_ID]
    if len(matching) != 1:
        raise BundleError("route_checkpoint_node_missing_or_ambiguous")
    node = matching[0]
    if (
        node.get("scenario_id", scenario) != scenario
        or node.get("runtime_profile_id", profile) != profile
        or int(node.get("map_id") or 0) != MAP_ID
        or int(node.get("source_entry") or node.get("target_entry") or 0)
        != TARGET_ENTRY
        or int(node.get("expected_bot_count") or ACTOR_COUNT) != ACTOR_COUNT
    ):
        raise BundleError("route_checkpoint_identity_mismatch")
    return route


def _target_route_suffix(
    source: dict[str, Any], scenario: str, profile: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the exact checkpoint suffix and its separated identities."""

    rows = source.get("routes")
    if not isinstance(rows, list) or not rows:
        raise BundleError("source_route_rows_missing_or_empty")
    if any(not isinstance(row, dict) for row in rows):
        raise BundleError("source_route_row_invalid")
    targets = [index for index, row in enumerate(rows)
               if row.get("route_node_id") == NODE_ID]
    if len(targets) != 1:
        raise BundleError("route_checkpoint_node_missing_or_ambiguous")
    source_initial = rows[0]
    suffix_rows = rows[targets[0]:]
    suffix_node_ids = [str(row.get("route_node_id") or "") for row in suffix_rows]
    if suffix_node_ids != list(REQUIRED_SUFFIX_NODE_IDS):
        raise BundleError("route_checkpoint_required_suffix_mismatch")

    source_invariants = {
        field: source_initial.get(field) for field in ROUTE_INVARIANT_FIELDS
    }
    if (
        not isinstance(source_invariants["bot_start_map_id"], int)
        or source_invariants["bot_start_map_id"] <= 0
        or any(not isinstance(source_invariants[field], (int, float))
               for field in ("bot_start_x", "bot_start_y", "bot_start_z", "bot_start_o"))
        or not isinstance(source_invariants["roster_identity"], list)
        or not source_invariants["roster_identity"]
        or source_invariants["diagnostic_only"] is not True
        or not isinstance(source_invariants["diagnostic_parent_scenario_id"], str)
        or not source_invariants["diagnostic_parent_scenario_id"]
        or not isinstance(source_invariants["diagnostic_prerequisite_state"], dict)
        or source_invariants["diagnostic_prerequisite_state"].get(
            "certifies_predecessors"
        ) is not False
    ):
        raise BundleError("route_source_invariant_invalid")
    for row in suffix_rows:
        if {field: row.get(field) for field in ROUTE_INVARIANT_FIELDS} != source_invariants:
            raise BundleError("route_suffix_invariant_drift")
        if row.get("scenario_id", scenario) != scenario \
                or row.get("runtime_profile_id", profile) != profile:
            raise BundleError("route_suffix_identity_drift")

    retained_rows: list[dict[str, Any]] = []
    for step, row in enumerate(suffix_rows, start=1):
        retained = json.loads(json.dumps(row))
        retained["step"] = step
        retained_rows.append(retained)
    suffix = json.loads(json.dumps(source))
    suffix["routes"] = retained_rows
    suffix["scenario_id"] = scenario
    return suffix, {
        "source_initial_node_id": str(source_initial.get("route_node_id") or ""),
        "runtime_initial_node_id": suffix_node_ids[0],
        "checkpoint_target_node_id": NODE_ID,
        "retained_node_ids": suffix_node_ids,
    }


def _verify_gate_bearing_build_receipt(receipt: Path, policy: Path) -> dict[str, Any]:
    try:
        report = verify_receipt(receipt, load_build_json(policy))
    except CoordinatorError as error:
        raise BundleError(f"build_receipt_verification_failed:{error}") from error
    if report.get("gate_bearing") is not True:
        raise BundleError("build_receipt_not_gate_bearing")
    return report


def _copy_exact(source: Path, destination: Path) -> None:
    try:
        atomic_write_new(destination, source.read_bytes())
    except CanonicalRouteStagingError as error:
        raise BundleError(str(error)) from error
    if sha256_file(source) != sha256_file(destination):
        destination.unlink(missing_ok=True)
        raise BundleError(f"copy_hash_mismatch:{destination.name}")


def stage_canonical_route(
    *, worktree: Path, source_route: Path, expected_sha256: str,
    external_run_root: Path,
) -> dict[str, Any]:
    try:
        return _stage_canonical_route(
            worktree=worktree,
            source_route=source_route,
            expected_sha256=expected_sha256,
            external_run_root=external_run_root,
            dvc_stage_name="validation_scenarios",
            output_relative_member="validation_routes.jsonl",
        )
    except CanonicalRouteStagingError as error:
        raise BundleError(str(error)) from error


def _file_rows(root: Path, names: list[str]) -> list[dict[str, str]]:
    return [
        {"path": name, "sha256": sha256_file(root / name)}
        for name in sorted(names)
    ]


def _logical_bindings(root: Path) -> dict[str, Path]:
    return {
        key: root / BUNDLE_NAMES[key]
        for key in (
            "runtime_config", "route_manifest", "profile_manifest",
            "build_receipt", "ledger",
            "decision", "suite_receipt",
        )
    }


def _verify_config(
    path: Path, *, route_path: Path, profile_manifest_path: Path,
    seal: dict[str, Any], source_commit: str,
) -> None:
    text = path.read_text(encoding="utf-8")
    expected = {
        **CONFIG_VALUES,
        "BotWorld.ValidationRoute.ManifestPath": f'"{route_path}"',
        "BotWorld.ProfileManifest": f'"{profile_manifest_path}"',
        f"{CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX}.SealSha256": (
            f'"{seal.get("seal_sha256")}"'
        ),
        f"{CHAINWIELDER_CHECKPOINT_CONFIG_PREFIX}.SourceCommit": (
            f'"{source_commit}"'
        ),
    }
    for key, value in expected.items():
        if _config_value(text, key) != value:
            raise BundleError(f"config_binding_mismatch:{key}")


def verify_bundle(
    output_dir: Path, *, materialized_root: Path | None = None,
) -> dict[str, Any]:
    logical_root = output_dir.resolve()
    root = (materialized_root or output_dir).resolve()
    if not root.is_dir():
        raise BundleError("bundle_missing")
    expected_names = set(BUNDLE_NAMES.values())
    actual_names = {path.name for path in root.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise BundleError("bundle_partial_or_extra_files")
    manifest = _json(root / BUNDLE_NAMES["bundle_manifest"], "bundle_manifest")
    if (root / BUNDLE_NAMES["bundle_manifest"]).read_bytes() != _canonical_pretty_json(manifest):
        raise BundleError("bundle_manifest_not_canonical")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise BundleError("bundle_manifest_schema_invalid")
    expected_manifest_names = expected_names - {BUNDLE_NAMES["bundle_manifest"]}
    rows = manifest.get("files")
    if not isinstance(rows, list) or {row.get("path") for row in rows if isinstance(row, dict)} != expected_manifest_names:
        raise BundleError("bundle_manifest_incomplete")
    for row in rows:
        name = row.get("path")
        digest = row.get("sha256")
        if not isinstance(name, str) or not SHA256_RE.fullmatch(str(digest or "")):
            raise BundleError("bundle_manifest_entry_invalid")
        if sha256_file(root / name) != digest:
            raise BundleError(f"bundle_file_hash_mismatch:{name}")
    launch = _json(root / BUNDLE_NAMES["launch_contract"], "launch_contract")
    if launch.get("schema") != LAUNCH_SCHEMA or launch.get("bundle_schema") != SCHEMA:
        raise BundleError("launch_contract_schema_invalid")
    payload_names = [
        BUNDLE_NAMES[key] for key in (
            "source_route_manifest", "route_manifest", "profile_manifest",
            "runtime_config",
            "build_receipt", "ledger",
            "decision", "suite_receipt", "checkpoint_seal", "admission",
            "base_runtime_config", "build_policy",
        )
    ]
    if launch.get("canonical_payload_manifest") != _file_rows(root, payload_names):
        raise BundleError("launch_payload_manifest_mismatch")
    source = launch.get("source") or {}
    worktree = Path(str(source.get("worktree") or ""))
    commit, tree = _source_identity(
        worktree, str(source.get("commit") or ""), str(source.get("tree") or "")
    )
    identities = launch.get("identity") or {}
    if identities != {
        "scenario_id": SCENARIO_ID,
        "runtime_profile_id": SCENARIO_ID,
        "pool_tag": SCENARIO_ID,
        "actor_guid": ACTOR_GUID,
        "checkpoint_fixture_id": CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
    }:
        raise BundleError("launch_identity_mismatch")
    paths = launch.get("paths") or {}
    logical = {
        key: logical_root / BUNDLE_NAMES[key]
        for key in (
            "runtime_config", "build_receipt", "admission", "route_manifest",
            "source_route_manifest", "profile_manifest",
            "ledger", "decision", "suite_receipt", "checkpoint_seal",
            "base_runtime_config", "build_policy",
        )
    }
    for key, path in logical.items():
        binding = paths.get(key)
        if not isinstance(binding, dict) or binding.get("path") != str(path):
            raise BundleError(f"launch_path_mismatch:{key}")
        materialized = root / path.name
        if binding.get("sha256") != sha256_file(materialized):
            raise BundleError(f"launch_hash_mismatch:{key}")
    binary = Path(str((paths.get("binary") or {}).get("path") or ""))
    _require_hash(binary, str((paths.get("binary") or {}).get("sha256") or ""), "binary")
    policy = root / BUNDLE_NAMES["build_policy"]
    _verify_gate_bearing_build_receipt(
        root / BUNDLE_NAMES["build_receipt"], policy
    )
    source_route = _validate_route(
        root / BUNDLE_NAMES["source_route_manifest"], SCENARIO_ID, SCENARIO_ID
    )
    expected_runtime_route, route_identity = _target_route_suffix(
        source_route, SCENARIO_ID, SCENARIO_ID
    )
    runtime_route_path = root / BUNDLE_NAMES["route_manifest"]
    if runtime_route_path.read_bytes() != _canonical_pretty_json(expected_runtime_route):
        raise BundleError("runtime_route_suffix_reconstruction_mismatch")
    _validate_route(runtime_route_path, SCENARIO_ID, SCENARIO_ID)
    expected_route_identity = {
        **route_identity,
        "source_route_sha256": sha256_file(
            root / BUNDLE_NAMES["source_route_manifest"]
        ),
        "runtime_route_sha256": sha256_file(runtime_route_path),
    }
    if launch.get("route_identity") != expected_route_identity:
        raise BundleError("launch_route_identity_mismatch")
    source_profile_path, source_profile = _tracked_profile_manifest(worktree)
    try:
        expected_profile, profile_identity = build_runtime_profile_suffix_manifest(
            source_manifest=source_profile, runtime_profile=SCENARIO_ID,
            route_manifest_path=logical["route_manifest"],
        )
    except ValueError as error:
        raise BundleError(str(error)) from error
    if (root / BUNDLE_NAMES["profile_manifest"]).read_bytes() != (
        _canonical_pretty_json(expected_profile)
    ):
        raise BundleError("runtime_profile_manifest_reconstruction_mismatch")
    profile_identity["runtime_profile_manifest_sha256"] = sha256_file(
        root / BUNDLE_NAMES["profile_manifest"]
    )
    profile_identity["source_profile_manifest_sha256"] = sha256_file(
        source_profile_path
    )
    profile_identity["runtime_route_manifest_sha256"] = sha256_file(
        runtime_route_path
    )
    if launch.get("runtime_profile_overlay") != profile_identity:
        raise BundleError("launch_profile_overlay_identity_mismatch")
    seal = _json(root / BUNDLE_NAMES["checkpoint_seal"], "checkpoint_seal")
    _verify_config(
        root / BUNDLE_NAMES["runtime_config"],
        route_path=logical["route_manifest"],
        profile_manifest_path=logical["profile_manifest"],
        seal=seal, source_commit=commit,
    )
    reconstructed = _render_config(
        root / BUNDLE_NAMES["base_runtime_config"],
        route_path=logical["route_manifest"],
        profile_manifest_path=logical["profile_manifest"],
        seal=seal, source_commit=commit,
    )
    if reconstructed != (root / BUNDLE_NAMES["runtime_config"]).read_bytes():
        raise BundleError("runtime_config_reconstruction_mismatch")
    admission_sha = sha256_file(root / BUNDLE_NAMES["admission"])
    try:
        verified = verify_recurrence_admission(
            admission_path=root / BUNDLE_NAMES["admission"],
            expected_sha256=admission_sha,
            worktree=worktree,
            binary=binary,
            build_receipt=root / BUNDLE_NAMES["build_receipt"],
            runtime_config=root / BUNDLE_NAMES["runtime_config"],
            profile_manifest=root / BUNDLE_NAMES["profile_manifest"],
            expected_runtime_profile_id=SCENARIO_ID,
            required_purpose=FIXTURE_EXPANSION_PURPOSE,
            atomic_bundle_roots=(logical_root, root) if root != logical_root else None,
        )
    except RecurrenceAdmissionError as error:
        raise BundleError(f"recurrence_admission:{error}") from error
    if verified.get("checkpoint_seal_sha256") != seal.get("seal_sha256"):
        raise BundleError("checkpoint_seal_verification_mismatch")
    admission_profile = (verified.get("bindings") or {}).get(
        "profile_manifest"
    )
    if admission_profile != {
        "path": str(logical["profile_manifest"]),
        "sha256": profile_identity["runtime_profile_manifest_sha256"],
    } or verified.get("runtime_profile_overlay") != profile_identity:
        raise BundleError("recurrence_admission_profile_overlay_mismatch")
    watchdog = launch.get("completion_watchdog") or {}
    if (
        launch.get("fixed_success_timer_seconds") is not None
        or launch.get("start_budget") != {"worldserver_starts": 1, "owner": "capture_controller"}
        or watchdog.get("duration_policy") != "completion-watchdog"
    ):
        raise BundleError("launch_watchdog_or_start_budget_invalid")
    if launch.get("expected_arm_predicates") != {
        "required": True, "command_sent": True, "emission_count": 1,
        "actor_guid": ACTOR_GUID, "seal_sha256": seal["seal_sha256"],
        "source_commit": commit,
    }:
        raise BundleError("launch_arm_predicates_invalid")
    if launch.get("expected_lifecycle_predicates") != {
        "stage": "completed", "terminal": True, "injection_count": 1,
        "actor_guid": ACTOR_GUID,
        "authority": "chainwielder_fixture_observation_only_not_gameplay",
        "trigger": "active_route_path_or_armed_route_hazard_retry",
        "rejection_owner": "hazard",
        "rejection_gate": "future_pack_destination",
        "rejection_reason": "route_destination_future_pack_unsafe",
        "planner_receipt_id": 0,
        "before_after_identity_preserved": True,
        "outcome": "hazard_exit_completed",
    }:
        raise BundleError("launch_lifecycle_predicates_invalid")
    argv = launch.get("launch_argv")
    if not isinstance(argv, list) or any(not isinstance(value, str) for value in argv):
        raise BundleError("launch_argv_invalid")
    required_argv = {
        "--binary": str(binary),
        "--config": str(logical["runtime_config"]),
        "--build-receipt": str(logical["build_receipt"]),
        "--recurrence-admission": str(logical["admission"]),
        "--recurrence-admission-sha256": admission_sha,
        "--chainwielder-checkpoint-actor-guid": str(ACTOR_GUID),
        "--scenario-id": SCENARIO_ID,
        "--runtime-profile": SCENARIO_ID,
        "--pool-tag": SCENARIO_ID,
    }
    for flag, value in required_argv.items():
        try:
            index = argv.index(flag)
        except ValueError as error:
            raise BundleError(f"launch_argv_missing:{flag}") from error
        if index + 1 >= len(argv) or argv[index + 1] != value:
            raise BundleError(f"launch_argv_binding_mismatch:{flag}")
    if argv.count("--fixture-expansion-replay") != 1 or "--observe-sec" in argv:
        raise BundleError("launch_argv_duration_contract_invalid")
    return {
        "valid": True,
        "bundle": str(logical_root),
        "admission_sha256": admission_sha,
        "checkpoint_seal_sha256": seal["seal_sha256"],
        "source_commit": commit,
        "source_tree": tree,
        "route_identity": expected_route_identity,
        "launch_argv": argv,
    }


def _failure_receipt(output_dir: Path, reason: str, worktree: Path) -> None:
    destination = output_dir.resolve().with_name(output_dir.name + ".failure.json")
    if _is_within(destination, worktree.resolve()):
        destination = worktree.resolve().parent / destination.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    _write_json(temporary, {
        "schema": FAILURE_SCHEMA,
        "classification": "failed_closed",
        "launchable": False,
        "output_dir": str(output_dir.resolve()),
        "reason": reason,
    })
    os.replace(temporary, destination)


def create_bundle(
    *, worktree: Path, output_dir: Path, source_commit: str, source_tree: str,
    binary: Path, binary_sha256: str, build_receipt: Path,
    build_receipt_sha256: str, build_policy: Path, build_policy_sha256: str,
    decision: Path, decision_sha256: str, suite_receipt: Path,
    suite_receipt_sha256: str, route_manifest: Path, route_manifest_sha256: str,
    base_runtime_config: Path, base_runtime_config_sha256: str, ledger: Path,
    ledger_sha256: str, scenario_id: str, runtime_profile_id: str,
    pool_tag: str, actor_guid: int, checkpoint_fixture_id: str,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    staging: Path | None = None
    copied_inputs = {
        "build_receipt": build_receipt,
        "decision": decision,
        "suite_receipt": suite_receipt,
        "route_manifest": route_manifest,
        "base_runtime_config": base_runtime_config,
        "ledger": ledger,
        "build_policy": build_policy,
    }
    try:
        if (
            scenario_id != SCENARIO_ID or runtime_profile_id != SCENARIO_ID
            or pool_tag != SCENARIO_ID or actor_guid != ACTOR_GUID
            or checkpoint_fixture_id != CHAINWIELDER_CHECKPOINT_FIXTURE_ID
        ):
            raise BundleError("chainwielder_identity_input_mismatch")
        capture_stem = output_dir.with_name(output_dir.name + ".capture")
        capture_paths = [
            capture_stem.with_suffix(".json"),
            capture_stem.with_suffix(".raw.jsonl"),
            capture_stem.with_suffix(".worldserver.log"),
        ]
        _validate_locations(
            worktree=worktree, output_dir=output_dir,
            material_inputs=copied_inputs, binary=binary,
            capture_paths=capture_paths,
            read_only_source_inputs={"build_policy", "ledger"},
            exact_read_only_source_inputs={
                "ledger": TRACKED_LEDGER_RELATIVE_PATH,
            },
        )
        commit, tree = _source_identity(worktree, source_commit, source_tree)
        hashes = {
            "binary": (binary, binary_sha256),
            "build_receipt": (build_receipt, build_receipt_sha256),
            "build_policy": (build_policy, build_policy_sha256),
            "decision": (decision, decision_sha256),
            "suite_receipt": (suite_receipt, suite_receipt_sha256),
            "route_manifest": (route_manifest, route_manifest_sha256),
            "base_runtime_config": (base_runtime_config, base_runtime_config_sha256),
            "ledger": (ledger, ledger_sha256),
        }
        for label, (path, digest) in hashes.items():
            _require_hash(path.resolve(), digest, label)
        _verify_gate_bearing_build_receipt(build_receipt, build_policy)
        _validate_route(route_manifest, scenario_id, runtime_profile_id)
        parent = output_dir.parent
        parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=parent))
        source_route = _validate_route(
            route_manifest, scenario_id, runtime_profile_id
        )
        runtime_route, route_identity = _target_route_suffix(
            source_route, scenario_id, runtime_profile_id
        )
        for key in (
            "build_receipt", "build_policy", "decision", "suite_receipt",
            "base_runtime_config", "ledger",
        ):
            _copy_exact(copied_inputs[key], staging / BUNDLE_NAMES[key])
        _copy_exact(
            route_manifest, staging / BUNDLE_NAMES["source_route_manifest"]
        )
        _write_json(staging / BUNDLE_NAMES["route_manifest"], runtime_route)
        source_profile_path, source_profile = _tracked_profile_manifest(worktree)
        try:
            runtime_profile, profile_identity = build_runtime_profile_suffix_manifest(
                source_manifest=source_profile, runtime_profile=runtime_profile_id,
                route_manifest_path=output_dir / BUNDLE_NAMES["route_manifest"],
            )
        except ValueError as error:
            raise BundleError(str(error)) from error
        _write_json(staging / BUNDLE_NAMES["profile_manifest"], runtime_profile)
        profile_identity["runtime_profile_manifest_sha256"] = sha256_file(
            staging / BUNDLE_NAMES["profile_manifest"]
        )
        profile_identity["source_profile_manifest_sha256"] = sha256_file(
            source_profile_path
        )
        profile_identity["runtime_route_manifest_sha256"] = sha256_file(
            staging / BUNDLE_NAMES["route_manifest"]
        )
        seal = chainwielder_checkpoint_seal(
            worktree=worktree,
            binary=binary,
            build_receipt=staging / BUNDLE_NAMES["build_receipt"],
            decision=staging / BUNDLE_NAMES["decision"],
            profile_manifest=staging / BUNDLE_NAMES["profile_manifest"],
            runtime_profile_overlay=profile_identity,
            expected_runtime_profile_id=runtime_profile_id,
        )
        if seal.get("fixture_id") != checkpoint_fixture_id:
            raise BundleError("checkpoint_seal_fixture_mismatch")
        _write_json(staging / BUNDLE_NAMES["checkpoint_seal"], seal)
        logical = _logical_bindings(output_dir)
        (staging / BUNDLE_NAMES["runtime_config"]).write_bytes(
            _render_config(
                staging / BUNDLE_NAMES["base_runtime_config"],
                route_path=logical["route_manifest"],
                profile_manifest_path=logical["profile_manifest"],
                seal=seal, source_commit=commit,
            )
        )
        materialized = _logical_bindings(staging)
        create_recurrence_admission(
            output=staging / BUNDLE_NAMES["admission"],
            worktree=worktree,
            binary=binary,
            build_receipt=materialized["build_receipt"],
            runtime_config=materialized["runtime_config"],
            route_manifest=materialized["route_manifest"],
            ledger=materialized["ledger"],
            decision=materialized["decision"],
            suite_receipt=materialized["suite_receipt"],
            profile_manifest=materialized["profile_manifest"],
            runtime_profile_overlay=profile_identity,
            expected_runtime_profile_id=runtime_profile_id,
            purpose=FIXTURE_EXPANSION_PURPOSE,
            atomic_bundle_roots=(output_dir, staging),
        )
        admission_sha = sha256_file(staging / BUNDLE_NAMES["admission"])
        payload_names = [
            BUNDLE_NAMES[key] for key in (
                "source_route_manifest", "route_manifest", "profile_manifest",
                "runtime_config",
                "build_receipt", "ledger",
                "decision", "suite_receipt", "checkpoint_seal", "admission",
                "base_runtime_config", "build_policy",
            )
        ]
        launch = {
            "schema": LAUNCH_SCHEMA,
            "bundle_schema": SCHEMA,
            "source": {"worktree": str(worktree.resolve()), "commit": commit, "tree": tree},
            "identity": {
                "scenario_id": scenario_id,
                "runtime_profile_id": runtime_profile_id,
                "pool_tag": pool_tag,
                "actor_guid": actor_guid,
                "checkpoint_fixture_id": checkpoint_fixture_id,
            },
            "route_identity": {
                **route_identity,
                "source_route_sha256": sha256_file(
                    staging / BUNDLE_NAMES["source_route_manifest"]
                ),
                "runtime_route_sha256": sha256_file(
                    staging / BUNDLE_NAMES["route_manifest"]
                ),
            },
            "runtime_profile_overlay": profile_identity,
            "paths": {
                "binary": {"path": str(binary.resolve()), "sha256": binary_sha256},
                **{
                    key: {
                        "path": str(output_dir / BUNDLE_NAMES[key]),
                        "sha256": sha256_file(staging / BUNDLE_NAMES[key]),
                    }
                    for key in (
                        "runtime_config", "build_receipt", "admission",
                        "route_manifest", "source_route_manifest",
                        "profile_manifest", "ledger",
                        "decision", "suite_receipt",
                        "checkpoint_seal",
                        "base_runtime_config", "build_policy",
                    )
                },
            },
            "canonical_payload_manifest": _file_rows(staging, payload_names),
            "completion_watchdog": {
                "duration_policy": "completion-watchdog",
                "terminal_edges": [
                    "normal_clear", "monotonic_semantic_or_no_progress_stall",
                    "repeated_decisions", "excessive_death_loops",
                    "infrastructure_loss", "contamination", "explicit_interruption",
                ],
            },
            "fixed_success_timer_seconds": None,
            "start_budget": {"worldserver_starts": 1, "owner": "capture_controller"},
            "expected_arm_predicates": {
                "required": True, "command_sent": True, "emission_count": 1,
                "actor_guid": actor_guid, "seal_sha256": seal["seal_sha256"],
                "source_commit": commit,
            },
            "expected_lifecycle_predicates": {
                "stage": "completed", "terminal": True, "injection_count": 1,
                "actor_guid": actor_guid, "authority": "chainwielder_fixture_observation_only_not_gameplay",
                "trigger": "active_route_path_or_armed_route_hazard_retry",
                "rejection_owner": "hazard", "rejection_gate": "future_pack_destination",
                "rejection_reason": "route_destination_future_pack_unsafe",
                "planner_receipt_id": 0, "before_after_identity_preserved": True,
                "outcome": "hazard_exit_completed",
            },
            "launch_argv": [
                "pixi", "run", "python", "-m",
                "tools.raid_program.capture_phase1_raid_foundation",
                "--worktree", str(worktree.resolve()),
                "--binary", str(binary.resolve()),
                "--config", str(output_dir / BUNDLE_NAMES["runtime_config"]),
                "--output", str(capture_paths[0]),
                "--raw-output", str(capture_paths[1]),
                "--server-log-output", str(capture_paths[2]),
                "--build-receipt", str(output_dir / BUNDLE_NAMES["build_receipt"]),
                "--recurrence-admission", str(output_dir / BUNDLE_NAMES["admission"]),
                "--recurrence-admission-sha256", admission_sha,
                "--chainwielder-checkpoint-actor-guid", str(actor_guid),
                "--fixture-expansion-replay",
                "--scenario-id", scenario_id,
                "--runtime-profile", runtime_profile_id,
                "--pool-tag", pool_tag,
            ],
        }
        _write_json(staging / BUNDLE_NAMES["launch_contract"], launch)
        _write_json(staging / BUNDLE_NAMES["bundle_manifest"], {
            "schema": MANIFEST_SCHEMA,
            "files": _file_rows(
                staging,
                payload_names + [BUNDLE_NAMES["launch_contract"]],
            ),
        })
        result = verify_bundle(output_dir, materialized_root=staging)
        for label, (path, digest) in hashes.items():
            _require_hash(path.resolve(), digest, label)
        failure = output_dir.with_name(output_dir.name + ".failure.json")
        failure.unlink(missing_ok=True)
        os.replace(staging, output_dir)
        staging = None
        return {
            **result,
            "bundle": str(output_dir),
            "pre_rename_verified": result["valid"],
        }
    except (BundleError, RecurrenceAdmissionError, OSError, subprocess.SubprocessError) as error:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
        reason = str(error) or type(error).__name__
        _failure_receipt(output_dir, reason, worktree)
        if isinstance(error, BundleError):
            raise
        raise BundleError(reason) from error


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", type=Path, required=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    verify = commands.add_parser("verify")
    _add_common(create)
    _add_common(verify)
    create.add_argument("--worktree", type=Path, required=True)
    create.add_argument("--source-commit", required=True)
    create.add_argument("--source-tree", required=True)
    for name in (
        "binary", "build-receipt", "build-policy", "decision", "suite-receipt",
        "route-manifest", "base-runtime-config", "ledger",
    ):
        create.add_argument(f"--{name}", type=Path, required=True)
        create.add_argument(f"--{name}-sha256", required=True)
    create.add_argument("--scenario-id", required=True)
    create.add_argument("--runtime-profile-id", required=True)
    create.add_argument("--pool-tag", required=True)
    create.add_argument("--actor-guid", type=int, required=True)
    create.add_argument("--checkpoint-fixture-id", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "verify":
            value = verify_bundle(args.output_dir)
        else:
            values = vars(args)
            values.pop("command")
            value = create_bundle(**values)
    except BundleError as error:
        print(json.dumps({"valid": False, "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
