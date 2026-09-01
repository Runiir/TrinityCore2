#!/usr/bin/env python3
"""Compose and validate one production-bound composite fixture replay plan.

This module does not execute the plan.  It exists to remove hand-built argv
from the replay boundary.  Every external command is derived from one typed
request and repository-owned constants, then validated before publication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Callable, Sequence

from tools.raid_program.chainwielder_prestart_bundle import (
    ACTOR_GUID,
    BUNDLE_NAMES,
    BundleError,
    SCENARIO_ID,
    verify_bundle,
)
from tools.raid_program.canonical_route_staging import git_output
from tools.raid_program.chainwielder_runtime_config_authority import (
    TRACKED_DERIVED_AUTHORITY,
)
from tools.raid_program.queued_build import (
    CoordinatorError,
    command_hash,
    expected_build_configuration,
    validate_command,
    verify_receipt,
)
from tools.raid_program.recurrence_admission import (
    CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
)


ROOT = Path(__file__).resolve().parents[2]
PREBUILD_SCHEMA = "cata_raid_composite_fixture_replay_prebuild_plan_v1"
REALIZED_SCHEMA = "cata_raid_composite_fixture_replay_realized_plan_v1"
REQUEST_SCHEMA = "cata_raid_composite_fixture_replay_request_v1"
LAUNCHER_AUTHORITY_SCHEMA = "cata_raid_composite_fixture_replay_launcher_authority_v1"
FIXTURE_DESCRIPTOR_OWNER = "raid-shard-architecture"
FIXTURE_DESCRIPTOR_CLASSIFICATION = "fixture_replay_authorized"
FIXTURE_SCENARIO = {
    "scenario_id": SCENARIO_ID,
    "raid": "blackwing_descent",
    "boss": "magmaw",
    "mode": "10N",
}
FIXTURE_PROGRAM_SCOPE = {
    "acceptance_admitted": False,
    "fixture_expansion_replay_admitted": True,
    "gameplay_canary_admitted": False,
    "gameplay_mutations_allowed": False,
    "live_diagnostic_admitted": True,
    "configure_admitted": True,
    "worldserver_build_admitted": True,
    "worldserver_start_admitted": True,
    "authserver_start_admitted": False,
    "retry_admitted": False,
    "database_mutations_allowed": True,
    "database_mutation_scope": "validation_provisioning_only",
    "dvc_publication_required_after_terminal": True,
}
POLICY_RELATIVE_PATH = Path(
    "experiments/configs/cata_raid_build_resource_policy_fast8_v4.json"
)
LEDGER_RELATIVE_PATH = Path(
    "experiments/configs/cata_raid_magmaw_blocker_recurrence_v1.json"
)
RUNTIME_CONFIG_CONTRACT = (
    "experiments/configs/cata_raid_tracked_base_runtime_config_contract_v1.json"
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_OBJECT_RE = re.compile(r"[0-9a-f]{40,64}")
WORK_UNIT_RE = re.compile(r"[a-z][a-z0-9_-]*:[a-z0-9][a-z0-9_.-]*")
REQUEST_FIELDS = {
    "schema",
    "worktree",
    "run_root",
    "expected_work_unit",
    "decision",
    "suite_receipt",
    "route_manifest",
    "base_runtime_config_receipt",
    "runtime_config_authorities",
}


class ReplayPlanError(RuntimeError):
    """The replay plan is incomplete or differs from repository authority."""


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReplayPlanError(f"json_input_invalid:{path}") from error
    if not isinstance(value, dict):
        raise ReplayPlanError(f"json_object_required:{path}")
    return value


def _absolute_path(value: object, label: str) -> Path:
    if type(value) is not str or not value:
        raise ReplayPlanError(f"{label}_path_invalid")
    path = Path(value)
    if (
        not path.is_absolute()
        or Path(os.path.abspath(path)) != path
        or path.resolve() != path
    ):
        raise ReplayPlanError(f"{label}_path_invalid")
    return path


def _hash(value: object, label: str) -> str:
    if type(value) is not str or not SHA256_RE.fullmatch(value):
        raise ReplayPlanError(f"{label}_sha256_invalid")
    return value


def _git_object(value: object, label: str) -> str:
    if type(value) is not str or not GIT_OBJECT_RE.fullmatch(value):
        raise ReplayPlanError(f"{label}_invalid")
    return value


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise ReplayPlanError(f"{label}_invalid")
    return value


def _artifact(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"path"}:
        raise ReplayPlanError(f"{label}_artifact_invalid")
    return {"path": str(_absolute_path(value["path"], label))}


def _bound_file(path: Path, label: str) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise ReplayPlanError(f"{label}_missing")
    return {"path": str(path), "sha256": _sha256_bytes(path.read_bytes())}


def _source_authority(
    worktree: Path, expected_work_unit: str,
) -> dict[str, str]:
    """Bind the clean HEAD, active descriptor, and its exact source handoff."""

    try:
        commit = str(git_output(worktree, "rev-parse", "HEAD"))
        tree = str(git_output(worktree, "rev-parse", "HEAD^{tree}"))
        dirty = git_output(
            worktree, "status", "--porcelain=v1", "-z", binary=True
        )
    except subprocess.SubprocessError as error:
        raise ReplayPlanError("source_identity_invalid") from error
    if dirty:
        raise ReplayPlanError("source_worktree_dirty")
    descriptor_relative = Path(
        "experiments/configs/cata_raid_active_work_unit_v1.json"
    )
    descriptor_path = worktree / descriptor_relative
    try:
        descriptor_bytes = descriptor_path.read_bytes()
        committed_descriptor = git_output(
            worktree, "show", f"HEAD:{descriptor_relative.as_posix()}", binary=True
        )
        descriptor = json.loads(descriptor_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        raise ReplayPlanError("active_descriptor_identity_invalid") from error
    if (
        descriptor_bytes != committed_descriptor
        or not isinstance(descriptor, dict)
        or descriptor.get("schema") != "cata_raid_active_work_unit_v1"
    ):
        raise ReplayPlanError("active_descriptor_identity_invalid")
    authority = descriptor.get("launcher_authority")
    authority_fields = {
        "schema", "expected_work_unit", "descriptor_owner_skill",
        "descriptor_classification", "source_handoff_schema",
        "source_handoff_work_unit", "source_handoff_owner_skill",
        "source_handoff_classification", "required_action_sha256",
        "required_postcondition_sha256", "scenario", "fixture_expansion",
        "program_scope", "validation_clock",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != authority_fields
        or authority.get("schema") != LAUNCHER_AUTHORITY_SCHEMA
    ):
        raise ReplayPlanError("launcher_authority_invalid")
    for field in (
        "expected_work_unit", "descriptor_owner_skill",
        "descriptor_classification", "source_handoff_schema",
        "source_handoff_work_unit", "source_handoff_owner_skill",
        "source_handoff_classification",
    ):
        _text(authority.get(field), f"launcher_authority_{field}")
    _hash(authority.get("required_action_sha256"), "required_action")
    _hash(
        authority.get("required_postcondition_sha256"),
        "required_postcondition",
    )
    if (
        descriptor.get("work_unit") != expected_work_unit
        or authority.get("expected_work_unit") != expected_work_unit
        or descriptor.get("owner_skill") != authority.get("descriptor_owner_skill")
        or descriptor.get("classification")
        != authority.get("descriptor_classification")
    ):
        raise ReplayPlanError("active_work_unit_mismatch")
    scenario = authority.get("scenario")
    fixture_expansion = authority.get("fixture_expansion")
    program_scope = authority.get("program_scope")
    validation_clock = authority.get("validation_clock")
    descriptor_fixture_expansion = descriptor.get("fixture_expansion")
    descriptor_program_scope = descriptor.get("program_scope")
    if (
        authority.get("descriptor_owner_skill") != FIXTURE_DESCRIPTOR_OWNER
        or authority.get("descriptor_classification")
        != FIXTURE_DESCRIPTOR_CLASSIFICATION
        or scenario != FIXTURE_SCENARIO
        or {key: descriptor.get(key) for key in ("raid", "boss", "mode")}
        != {key: FIXTURE_SCENARIO[key] for key in ("raid", "boss", "mode")}
        or fixture_expansion != {
            "purpose": "fixture_expansion_replay",
            "attempts": 1,
            "retries": 0,
            "authserver_starts": 0,
            "worldserver_starts": 1,
            "duration_policy": "completion_watchdog",
        }
        or not isinstance(descriptor_fixture_expansion, dict)
        or any(
            descriptor_fixture_expansion.get(key) != value
            for key, value in fixture_expansion.items()
        )
        or program_scope != FIXTURE_PROGRAM_SCOPE
        or not isinstance(descriptor_program_scope, dict)
        or frozenset(descriptor_program_scope) not in {
            frozenset(FIXTURE_PROGRAM_SCOPE),
            frozenset((*FIXTURE_PROGRAM_SCOPE, "admission_conditions")),
        }
        or any(
            descriptor_program_scope.get(key) != value
            for key, value in FIXTURE_PROGRAM_SCOPE.items()
        )
        or validation_clock != {
            "fixed_success_timer_seconds": None,
            "policy": "completion_watchdog",
            "worldserver_starts": 1,
            "authserver_starts": 0,
            "retries": 0,
        }
        or descriptor.get("validation_clock") != validation_clock
    ):
        raise ReplayPlanError("launcher_authority_scope_invalid")
    source_handoff = descriptor.get("source_handoff")
    if (
        not isinstance(source_handoff, dict)
        or set(source_handoff)
        != {"path", "sha256", "source_commit", "source_tree"}
    ):
        raise ReplayPlanError("source_handoff_identity_invalid")
    _hash(source_handoff.get("sha256"), "source_handoff")
    handoff_source_commit = _git_object(
        source_handoff.get("source_commit"), "handoff_source_commit"
    )
    handoff_source_tree = _git_object(
        source_handoff.get("source_tree"), "handoff_source_tree"
    )
    try:
        resolved_handoff_commit = str(git_output(
            worktree, "rev-parse", f"{handoff_source_commit}^{{commit}}"
        ))
        resolved_handoff_tree = str(git_output(
            worktree, "rev-parse", f"{handoff_source_commit}^{{tree}}"
        ))
        git_output(
            worktree, "merge-base", "--is-ancestor",
            handoff_source_commit, commit,
        )
    except subprocess.SubprocessError as error:
        raise ReplayPlanError("source_handoff_provenance_invalid") from error
    if (
        resolved_handoff_commit != handoff_source_commit
        or resolved_handoff_tree != handoff_source_tree
    ):
        raise ReplayPlanError("source_handoff_provenance_invalid")
    handoff_relative = Path(str(source_handoff.get("path") or ""))
    if (
        handoff_relative.is_absolute()
        or ".." in handoff_relative.parts
        or handoff_relative.as_posix() in {"", "."}
    ):
        raise ReplayPlanError("source_handoff_identity_invalid")
    handoff_path = worktree / handoff_relative
    try:
        handoff_bytes = handoff_path.read_bytes()
        committed_handoff = git_output(
            worktree, "show", f"HEAD:{handoff_relative.as_posix()}", binary=True
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ReplayPlanError("source_handoff_identity_invalid") from error
    handoff_sha = _sha256_bytes(handoff_bytes)
    try:
        handoff = json.loads(handoff_bytes)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReplayPlanError("source_handoff_identity_invalid") from error
    handoff_source = handoff.get("source") if isinstance(handoff, dict) else None
    next_work_unit = handoff.get("next_work_unit") if isinstance(handoff, dict) else None
    required_action = (
        next_work_unit.get("required_action")
        if isinstance(next_work_unit, dict) else None
    )
    required_postcondition = (
        next_work_unit.get("required_postcondition")
        if isinstance(next_work_unit, dict) else None
    )
    if (
        handoff_bytes != committed_handoff
        or source_handoff.get("sha256") != handoff_sha
        or not isinstance(handoff_source, dict)
        or not isinstance(next_work_unit, dict)
        or handoff.get("schema") != authority.get("source_handoff_schema")
        or handoff.get("work_unit_id")
        != authority.get("source_handoff_work_unit")
        or handoff.get("owner_skill")
        != authority.get("source_handoff_owner_skill")
        or handoff.get("classification")
        != authority.get("source_handoff_classification")
        or handoff_source.get("commit") != source_handoff.get("source_commit")
        or handoff_source.get("tree") != source_handoff.get("source_tree")
        or next_work_unit.get("id") != expected_work_unit
        or next_work_unit.get("owner_skill") != descriptor.get("owner_skill")
        or type(required_action) is not str
        or _sha256_bytes(required_action.encode())
        != authority.get("required_action_sha256")
        or type(required_postcondition) is not str
        or _sha256_bytes(required_postcondition.encode())
        != authority.get("required_postcondition_sha256")
        or descriptor.get("observed_at_commit")
        != source_handoff.get("source_commit")
        or descriptor.get("immutable_input_commit")
        != source_handoff.get("source_commit")
    ):
        raise ReplayPlanError("source_handoff_identity_invalid")
    return {
        "commit": _git_object(commit, "source_commit"),
        "tree": _git_object(tree, "source_tree"),
        "active_descriptor_path": descriptor_relative.as_posix(),
        "active_descriptor_sha256": _sha256_bytes(descriptor_bytes),
        "source_handoff_path": handoff_relative.as_posix(),
        "source_handoff_sha256": handoff_sha,
    }


def _policy(worktree: Path) -> tuple[Path, dict[str, Any], str]:
    path = worktree / POLICY_RELATIVE_PATH
    value = _load_object(path)
    payload = path.read_bytes()
    controls = value.get("mechanical_controls")
    parallelism = value.get("parallelism")
    if not isinstance(controls, dict) or not isinstance(parallelism, dict):
        raise ReplayPlanError("build_policy_schema_invalid")
    if (
        parallelism.get("maximum_compiler_jobs") != 8
        or parallelism.get("maximum_linker_jobs") != 1
        or controls.get("cmake_build_parallel_level") != 8
        or controls.get("cmake_link_job_pool") != 1
    ):
        raise ReplayPlanError("build_policy_parallelism_invalid")
    return path, value, _sha256_bytes(payload)


def _configure_child(policy: dict[str, Any]) -> list[str]:
    controls = policy["mechanical_controls"]
    expected = expected_build_configuration(policy)
    if expected is None:
        raise ReplayPlanError("build_policy_configuration_missing")
    command = [
        str(controls["cmake_executable"]),
        "-S", ".", "-B", "build", "-G", str(controls["cmake_generator"]),
        *(f"-D{key}={value}" for key, value in expected.items()),
    ]
    try:
        validate_command(command, 8, resource_class="configure", policy=policy)
    except CoordinatorError as error:
        raise ReplayPlanError(f"configure_command_invalid:{error}") from error
    return command


def _build_child(policy: dict[str, Any]) -> list[str]:
    command = [
        str(policy["mechanical_controls"]["cmake_executable"]),
        "--build", "build", "--target", "worldserver", "--parallel", "8",
    ]
    try:
        validate_command(
            command, 8, resource_class="worldserver_build", policy=policy
        )
    except CoordinatorError as error:
        raise ReplayPlanError(f"build_command_invalid:{error}") from error
    return command


def _queued_command(
    *, worktree: Path, policy_path: Path, resource_class: str,
    receipt: Path, child: Sequence[str],
) -> list[str]:
    return [
        "pixi", "run", "python", "-m", "tools.raid_program.queued_build",
        "--worktree", str(worktree), "--policy", str(policy_path), "run",
        "--resource-class", resource_class, "--receipt", str(receipt),
        "--", *child,
    ]


def _bundle_create(
    *, worktree: Path, source: dict[str, str], run_root: Path,
    policy_path: Path, policy_sha256: str,
    artifacts: dict[str, dict[str, str]],
) -> list[str]:
    binary = worktree / "build/src/server/worldserver/worldserver"
    build_receipt = run_root / "worldserver_build_receipt.json"
    return [
        "pixi", "run", "python", "-m",
        "tools.raid_program.chainwielder_prestart_bundle", "create",
        "--output-dir", str(run_root / "prestart_bundle"),
        "--worktree", str(worktree),
        "--source-commit", source["commit"], "--source-tree", source["tree"],
        "--binary", str(binary), "--binary-sha256", artifacts["binary"]["sha256"],
        "--build-receipt", str(build_receipt),
        "--build-receipt-sha256", artifacts["build_receipt"]["sha256"],
        "--build-policy", str(policy_path),
        "--build-policy-sha256", policy_sha256,
        "--decision", artifacts["decision"]["path"],
        "--decision-sha256", artifacts["decision"]["sha256"],
        "--suite-receipt", artifacts["suite_receipt"]["path"],
        "--suite-receipt-sha256", artifacts["suite_receipt"]["sha256"],
        "--route-manifest", artifacts["route_manifest"]["path"],
        "--route-manifest-sha256", artifacts["route_manifest"]["sha256"],
        "--base-runtime-config-receipt",
        artifacts["base_runtime_config_receipt"]["path"],
        "--base-runtime-config-receipt-sha256",
        artifacts["base_runtime_config_receipt"]["sha256"],
        "--ledger", artifacts["ledger"]["path"],
        "--ledger-sha256", artifacts["ledger"]["sha256"],
        "--scenario-id", SCENARIO_ID,
        "--runtime-profile-id", SCENARIO_ID,
        "--pool-tag", SCENARIO_ID,
        "--actor-guid", str(ACTOR_GUID),
        "--checkpoint-fixture-id", CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        "--base-runtime-config-authority", TRACKED_DERIVED_AUTHORITY,
        "--base-runtime-config-contract-relative-path", RUNTIME_CONFIG_CONTRACT,
    ]


def _command(argv: Sequence[str], worktree: Path) -> dict[str, Any]:
    return {"argv": list(argv), "cwd": str(worktree)}


def _request_context(
    request: dict[str, Any], *, check_prebuild_outputs: bool,
) -> tuple[Path, Path, dict[str, dict[str, str]], Path, dict[str, Any], str]:
    """Validate typed static inputs before any external command may run."""

    if set(request) != REQUEST_FIELDS or request.get("schema") != REQUEST_SCHEMA:
        raise ReplayPlanError("request_schema_invalid")
    worktree = _absolute_path(request["worktree"], "worktree")
    if worktree != ROOT:
        raise ReplayPlanError("worktree_identity_invalid")
    run_root = _absolute_path(request["run_root"], "run_root")
    try:
        run_root.relative_to(worktree)
    except ValueError:
        pass
    else:
        raise ReplayPlanError("run_root_must_be_external")
    expected_work_unit = request["expected_work_unit"]
    if (
        type(expected_work_unit) is not str
        or not WORK_UNIT_RE.fullmatch(expected_work_unit)
    ):
        raise ReplayPlanError("expected_work_unit_invalid")
    authorities = request["runtime_config_authorities"]
    if authorities != [TRACKED_DERIVED_AUTHORITY]:
        raise ReplayPlanError("runtime_config_authority_selection_invalid")
    artifacts = {
        label: _artifact(request[label], label)
        for label in (
            "decision", "suite_receipt", "route_manifest",
            "base_runtime_config_receipt",
        )
    }
    for label, artifact in artifacts.items():
        path = Path(artifact["path"]).resolve()
        try:
            path.relative_to(worktree.resolve())
        except ValueError:
            try:
                path.relative_to(run_root)
            except ValueError:
                continue
            raise ReplayPlanError(f"{label}_aliases_run_root")
        raise ReplayPlanError(f"{label}_must_be_external")
    artifact_paths = [value["path"] for value in artifacts.values()]
    if len(set(artifact_paths)) != len(artifact_paths):
        raise ReplayPlanError("material_input_paths_not_unique")
    policy_path, policy, policy_sha256 = _policy(worktree)
    if check_prebuild_outputs:
        for output in (
            run_root / "configure_receipt.json",
            run_root / "worldserver_build_receipt.json",
            run_root / "prestart_bundle",
            run_root / "strict_provisioning_readback.json",
            run_root / "shard_roster_readback.json",
        ):
            if output.exists() or output.is_symlink():
                raise ReplayPlanError(f"declared_output_exists:{output.name}")
        if run_root.exists() and any(run_root.iterdir()):
            raise ReplayPlanError("run_root_not_empty")
    return worktree, run_root, artifacts, policy_path, policy, policy_sha256


def compose_plan(
    request: dict[str, Any], *, _check_outputs: bool = True,
) -> dict[str, Any]:
    """Compose the immutable configure/build half of the replay."""

    worktree, run_root, _artifacts, policy_path, policy, policy_sha256 = (
        _request_context(request, check_prebuild_outputs=_check_outputs)
    )
    source = _source_authority(worktree, request["expected_work_unit"])
    configure_receipt = run_root / "configure_receipt.json"
    build_receipt = run_root / "worldserver_build_receipt.json"
    plan = {
        "schema": PREBUILD_SCHEMA,
        "source": {"worktree": str(worktree), **source},
        "request_sha256": _sha256_bytes(_canonical_bytes(request)),
        "build_policy_sha256": policy_sha256,
        "scenario_id": SCENARIO_ID,
        "commands": {
            "configure": _command(_queued_command(
                worktree=worktree, policy_path=policy_path,
                resource_class="configure", receipt=configure_receipt,
                child=_configure_child(policy),
            ), worktree),
            "build": _command(_queued_command(
                worktree=worktree, policy_path=policy_path,
                resource_class="worldserver_build", receipt=build_receipt,
                child=_build_child(policy),
            ), worktree),
        },
        "execution": {
            "composition_side_effect_free": True,
            "order": ["configure", "build"],
            "postbuild_realization_required": True,
        },
    }
    plan["plan_sha256"] = _sha256_bytes(_canonical_bytes(plan))
    return plan


def _verify_plan_hash(plan: dict[str, Any]) -> None:
    claimed = plan.get("plan_sha256")
    unhashed = dict(plan)
    unhashed.pop("plan_sha256", None)
    if claimed != _sha256_bytes(_canonical_bytes(unhashed)):
        raise ReplayPlanError("plan_sha256_mismatch")


def validate_plan(
    plan: dict[str, Any], request: dict[str, Any], *, check_outputs: bool = False,
) -> None:
    """Reject a prebuild token that differs from clean recomposition."""

    _verify_plan_hash(plan)
    expected = compose_plan(dict(request), _check_outputs=check_outputs)
    if plan != expected:
        raise ReplayPlanError("plan_command_binding_mismatch")


def _verified_build_artifacts(
    *, worktree: Path, run_root: Path, policy: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, dict[str, str]]:
    build_receipt = run_root / "worldserver_build_receipt.json"
    configure_receipt = run_root / "configure_receipt.json"
    try:
        configure_verification = verify_receipt(configure_receipt, policy)
        verification = verify_receipt(build_receipt, policy)
        configure = _load_object(configure_receipt)
        receipt = _load_object(build_receipt)
    except (CoordinatorError, ReplayPlanError) as error:
        raise ReplayPlanError(f"build_receipt_not_gate_bearing:{error}") from error
    if (
        configure_verification.get("gate_bearing") is not True
        or verification.get("gate_bearing") is not True
    ):
        raise ReplayPlanError("build_receipt_not_gate_bearing")
    configure_lineage = receipt.get("configure_lineage")
    if (
        configure.get("resource_class") != "configure"
        or configure.get("commit") != source["commit"]
        or configure.get("command_sha256")
        != command_hash(_configure_child(policy))
        or receipt.get("resource_class") != "worldserver_build"
        or receipt.get("commit") != source["commit"]
        or receipt.get("command_sha256") != command_hash(_build_child(policy))
        or not isinstance(configure_lineage, dict)
        or configure_lineage.get("receipt_sha256")
        != configure.get("receipt_sha256")
    ):
        raise ReplayPlanError("build_receipt_binding_mismatch")
    binary = worktree / "build/src/server/worldserver/worldserver"
    binary_artifact = _bound_file(binary, "binary")
    output_rows = receipt.get("output_artifacts")
    worldserver = next((
        row for row in output_rows
        if isinstance(row, dict) and row.get("kind") == "worldserver_elf"
    ), None) if isinstance(output_rows, list) else None
    if not isinstance(worldserver, dict) or (
        Path(str(worldserver.get("path") or "")).resolve() != binary
        or worldserver.get("sha256") != binary_artifact["sha256"]
    ):
        raise ReplayPlanError("binary_receipt_binding_mismatch")
    return {
        "binary": binary_artifact,
        "configure_receipt": _bound_file(
            configure_receipt, "configure_receipt"
        ),
        "build_receipt": _bound_file(build_receipt, "build_receipt"),
    }


def realize_plan(
    request: dict[str, Any], prebuild: dict[str, Any], prebuild_path: Path,
) -> dict[str, Any]:
    """Bind postbuild commands only after authenticating fresh build outputs."""

    validate_plan(prebuild, request)
    worktree, run_root, requested, policy_path, policy, policy_sha256 = (
        _request_context(request, check_prebuild_outputs=False)
    )
    source = prebuild["source"]
    current_source = _source_authority(
        worktree, request["expected_work_unit"]
    )
    if source != {"worktree": str(worktree), **current_source}:
        raise ReplayPlanError("source_changed_after_prebuild")
    prebuild_path = _absolute_path(str(prebuild_path), "prebuild_plan")
    if prebuild_path.read_bytes() != _canonical_bytes(prebuild):
        raise ReplayPlanError("prebuild_plan_path_binding_mismatch")
    if (
        not run_root.is_dir()
        or {path.name for path in run_root.iterdir()}
        != {"configure_receipt.json", "worldserver_build_receipt.json"}
    ):
        raise ReplayPlanError("prebuild_output_inventory_invalid")
    artifacts = _verified_build_artifacts(
        worktree=worktree, run_root=run_root, policy=policy,
        source=current_source,
    )
    for label, value in requested.items():
        artifacts[label] = _bound_file(Path(value["path"]), label)
    ledger = _bound_file(worktree / LEDGER_RELATIVE_PATH, "ledger")
    artifacts["ledger"] = ledger
    bundle = run_root / "prestart_bundle"
    for output in (
        bundle,
        run_root / "provisioning_apply",
        run_root / "strict_provisioning_readback.json",
        run_root / "shard_roster_readback.json",
        bundle.with_suffix(".json"),
        bundle.with_suffix(".raw.jsonl"),
        bundle.with_suffix(".worldserver.log"),
    ):
        if output.exists() or output.is_symlink():
            raise ReplayPlanError(f"declared_output_exists:{output.name}")
    commands = {
        "bundle_create": _command(_bundle_create(
            worktree=worktree, source=current_source, run_root=run_root,
            policy_path=policy_path, policy_sha256=policy_sha256,
            artifacts=artifacts,
        ), worktree),
        "bundle_verify": _command([
            "pixi", "run", "python", "-m",
            "tools.raid_program.chainwielder_prestart_bundle", "verify",
            "--output-dir", str(bundle),
        ], worktree),
        "provisioning_apply": _command([
            "pixi", "run", "python", "-m",
            "tools.bot_ml.run_live_bot_validation",
            "--config", str(bundle / BUNDLE_NAMES["runtime_config"]),
            "--output-dir", str(run_root / "provisioning_apply"),
            "--validation-scenario-id", SCENARIO_ID,
            "--apply-validation-provisioning", "--prepare-only",
        ], worktree),
        "strict_readback": _command([
            "pixi", "run", "python", "-m",
            "tools.bot_ml.validate_validation_provisioning",
            "--worldserver-conf", str(bundle / BUNDLE_NAMES["runtime_config"]),
            "--check-db", "--require-applied", "--output",
            str(run_root / "strict_provisioning_readback.json"),
        ], worktree),
        "shard_readback": _command([
            "pixi", "run", "python", "-m",
            "tools.raid_program.capture_phase1_provisioning_readback",
            "--scenario-id", SCENARIO_ID,
            "--worldserver-conf", str(bundle / BUNDLE_NAMES["runtime_config"]),
            "--output", str(run_root / "shard_roster_readback.json"),
        ], worktree),
        "capture": _command([
            "pixi", "run", "python", "-m",
            "tools.raid_program.composite_fixture_replay_launcher",
            "run-capture", "--bundle", str(bundle),
        ], worktree),
    }
    plan = {
        "schema": REALIZED_SCHEMA,
        "source": source,
        "request_sha256": prebuild["request_sha256"],
        "prebuild_plan": {
            "path": str(prebuild_path),
            "sha256": prebuild["plan_sha256"],
        },
        "runtime_config_authority": TRACKED_DERIVED_AUTHORITY,
        "artifact_bindings": artifacts,
        "commands": commands,
        "execution": {
            "composition_side_effect_free": True,
            "order": [
                "bundle_create", "bundle_verify", "provisioning_apply",
                "strict_readback", "shard_readback", "capture",
            ],
            "capture_timer": "completion_watchdog",
            "fixed_success_timer_seconds": None,
        },
    }
    plan["plan_sha256"] = _sha256_bytes(_canonical_bytes(plan))
    return plan


def validate_realized_plan(
    plan: dict[str, Any], request: dict[str, Any], prebuild: dict[str, Any],
    prebuild_path: Path,
) -> None:
    _verify_plan_hash(plan)
    expected = realize_plan(request, prebuild, prebuild_path)
    if plan != expected:
        raise ReplayPlanError("realized_plan_command_binding_mismatch")


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ReplayPlanError(f"declared_output_exists:{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError as error:
            raise ReplayPlanError(
                f"declared_output_exists:{path.name}"
            ) from error
    finally:
        temporary_path.unlink(missing_ok=True)


def run_verified_capture(
    bundle: Path,
    runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> int:
    """Execute only the exact capture argv returned by full bundle verification."""

    try:
        verified = verify_bundle(bundle)
    except BundleError as error:
        raise ReplayPlanError(f"verified_bundle_required:{error}") from error
    argv = verified.get("launch_argv")
    if (
        not isinstance(argv, list)
        or not argv
        or any(type(token) is not str for token in argv)
        or any(
            token == "--observe-sec" or token.startswith("--observe-sec=")
            for token in argv
        )
        or argv.count("--fixture-expansion-replay") != 1
    ):
        raise ReplayPlanError("verified_capture_argv_invalid")
    if argv.count("--worktree") != 1:
        raise ReplayPlanError("verified_capture_worktree_invalid")
    worktree_index = argv.index("--worktree")
    if worktree_index + 1 >= len(argv):
        raise ReplayPlanError("verified_capture_worktree_invalid")
    worktree = Path(argv[worktree_index + 1])
    if not worktree.is_absolute():
        raise ReplayPlanError("verified_capture_worktree_invalid")
    result = runner(argv, check=False, cwd=worktree)
    return int(result.returncode)


def run_plan(
    plan: dict[str, Any], request: dict[str, Any],
    runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> int:
    """Run one authenticated plan once, in its frozen order and cwd."""

    if plan.get("schema") == PREBUILD_SCHEMA:
        validate_plan(plan, request, check_outputs=True)
    elif plan.get("schema") == REALIZED_SCHEMA:
        parent = plan.get("prebuild_plan")
        if not isinstance(parent, dict) or set(parent) != {"path", "sha256"}:
            raise ReplayPlanError("realized_parent_plan_invalid")
        parent_path = _absolute_path(parent["path"], "prebuild_plan")
        prebuild = _load_object(parent_path)
        validate_realized_plan(plan, request, prebuild, parent_path)
    else:
        raise ReplayPlanError("plan_schema_invalid")
    execution = plan.get("execution")
    commands = plan.get("commands")
    if not isinstance(execution, dict) or not isinstance(commands, dict):
        raise ReplayPlanError("plan_execution_contract_invalid")
    order = execution.get("order")
    if not isinstance(order, list) or set(order) != set(commands):
        raise ReplayPlanError("plan_execution_order_invalid")
    for name in order:
        command = commands.get(name)
        if not isinstance(command, dict) or set(command) != {"argv", "cwd"}:
            raise ReplayPlanError(f"command_contract_invalid:{name}")
        argv = command["argv"]
        cwd = Path(str(command["cwd"]))
        if (
            not isinstance(argv, list) or not argv
            or any(type(token) is not str for token in argv)
            or not cwd.is_absolute() or cwd != ROOT
        ):
            raise ReplayPlanError(f"command_contract_invalid:{name}")
        result = runner(argv, check=False, cwd=cwd)
        if result.returncode:
            return int(result.returncode)
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    compose = commands.add_parser("compose")
    compose.add_argument("--request", type=Path, required=True)
    compose.add_argument("--output", type=Path, required=True)
    realize = commands.add_parser("realize")
    realize.add_argument("--request", type=Path, required=True)
    realize.add_argument("--prebuild-plan", type=Path, required=True)
    realize.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run-plan")
    run.add_argument("--request", type=Path, required=True)
    run.add_argument("--plan", type=Path, required=True)
    capture = commands.add_parser("run-capture")
    capture.add_argument("--bundle", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "run-capture":
            return run_verified_capture(args.bundle)
        if args.command == "run-plan":
            request = _load_object(
                _absolute_path(str(args.request), "request")
            )
            plan = _load_object(_absolute_path(str(args.plan), "plan"))
            return run_plan(plan, request)
        request_path = _absolute_path(str(args.request), "request")
        output = _absolute_path(str(args.output), "output")
        for label, path in (("request", request_path), ("output", output)):
            try:
                path.relative_to(ROOT)
            except ValueError:
                continue
            raise ReplayPlanError(f"{label}_must_be_external")
        request = _load_object(request_path)
        run_root = _absolute_path(request.get("run_root"), "run_root")
        try:
            output.relative_to(run_root)
        except ValueError:
            pass
        else:
            raise ReplayPlanError("plan_output_must_be_outside_run_root")
        if args.command == "realize":
            prebuild_path = _absolute_path(
                str(args.prebuild_plan), "prebuild_plan"
            )
            try:
                prebuild_path.relative_to(run_root)
            except ValueError:
                pass
            else:
                raise ReplayPlanError("prebuild_plan_must_be_outside_run_root")
            prebuild = _load_object(prebuild_path)
            plan = realize_plan(request, prebuild, prebuild_path)
        else:
            plan = compose_plan(request)
        _atomic_write(args.output, _canonical_bytes(plan))
    except ReplayPlanError as error:
        print(json.dumps({"valid": False, "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"valid": True, "output": str(args.output), "plan_sha256": plan["plan_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
