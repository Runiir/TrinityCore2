from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from tools.raid_program.build_control_compatibility import (
    compatibility_projection,
    verify_build_control_compatibility,
)

try:
    from tools.raid_program.capture_value_types import (
        _canonical_object_sha256,
        _positive_int,
    )
except ModuleNotFoundError:
    from capture_value_types import _canonical_object_sha256, _positive_int


ROOT = Path(__file__).resolve().parents[2]


EXPECTED_BWD_ROUTE_IDENTITY = (
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

# These are the generated partitions in validation_scenarios_cata_001.json.
# Keep the capture gate tied to the generator's shard shape so an accidentally
# truncated or cross-shard route cannot be accepted merely because its last
# row happens to be a boss.
EXPECTED_BWD_ROUTE_PARTITION_COUNTS = {
    "blackwing_descent_10n": (11, 6),
    "blackwing_descent_10n_magmaw_diagnostic": (4, 1),
    "blackwing_descent_10n_omnotron_diagnostic": (3, 1),
    "blackwing_descent_10n_maloriak_diagnostic": (3, 1),
    "blackwing_descent_10n_atramedes_diagnostic": (2, 1),
    "blackwing_descent_10n_chimaeron_diagnostic": (2, 1),
    "blackwing_descent_10n_nefarian_diagnostic": (3, 1),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_identity(cwd: Path) -> dict[str, Any]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cwd, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=cwd, text=True).strip()
    porcelain = subprocess.check_output(["git", "status", "--porcelain=v1", "-z"], cwd=cwd)
    return {
        "head": head,
        "tree": tree,
        "clean": not porcelain,
        "dirty": bool(porcelain),
        "porcelain_sha256": hashlib.sha256(porcelain).hexdigest(),
    }

def _utc_timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def validate_build_receipt(
    receipt_path: Path,
    policy_path: Path,
    worktree: Path,
    binary: Path,
    config: Path | None = None,
    attestation_path: Path | None = None,
    build_control_authority: Path | None = None,
    build_control_authority_sha256: str | None = None,
) -> dict[str, Any]:
    """Reconstruct the production build gate without trusting receipt pass fields."""

    try:
        from tools.raid_program.queued_build import load_json, verify_receipt

        policy = load_json(policy_path)
        receipt = load_json(receipt_path)
        verification = verify_receipt(receipt_path, policy, allow_test_mode=False)
        privileged_verification = None
        if policy.get("mechanical_controls", {}).get(
            "privileged_receipt_signature_required"
        ):
            if attestation_path is None:
                raise RuntimeError("privileged build attestation is required")
            from tools.raid_program.privileged_build_attestation import (
                verify_privileged_attestation,
            )

            privileged_verification = verify_privileged_attestation(
                attestation_path,
                receipt_path,
                policy_path,
                None,
                allow_test_mode=False,
            )
        source_compatibility = verify_build_control_compatibility(
            worktree=worktree, receipt=receipt,
            authority_path=build_control_authority,
            authority_sha256=build_control_authority_sha256,
        )
        rejections: list[str] = []
        if verification.get("classification") != "success" or receipt.get("classification") != "success":
            rejections.append("build_receipt_not_success")
        if receipt.get("test_mode") is not False:
            rejections.append("build_receipt_test_mode")
        if receipt.get("exit_code") != 0:
            rejections.append("build_receipt_nonzero_exit")
        rejections.extend(source_compatibility["rejections"])
        if Path(str(receipt.get("worktree", ""))).resolve() != worktree.resolve():
            rejections.append("build_receipt_worktree_mismatch")
        if receipt.get("worktree_dirty_at_request") is not False:
            rejections.append("build_receipt_worktree_dirty")
        source_identity = receipt.get("source_identity")
        if not isinstance(source_identity, dict):
            rejections.append("build_receipt_source_identity_missing")
        else:
            snapshots = [source_identity.get(stage) for stage in ("request", "admission", "completion")]
            if not all(isinstance(snapshot, dict) for snapshot in snapshots):
                rejections.append("build_receipt_source_identity_incomplete")
            elif not (snapshots[0] == snapshots[1] == snapshots[2]):
                rejections.append("build_receipt_source_identity_changed")
            else:
                completion = snapshots[2]
                if completion.get("clean") is not True or completion.get("dirty") is not False:
                    rejections.append("build_receipt_completion_source_dirty")
        controls = policy.get("mechanical_controls", {})
        release_flags = controls.get("cmake_release_cxx_flags")
        if isinstance(release_flags, str) and release_flags:
            expected_cmake = {
                "CMAKE_BUILD_TYPE": controls.get("cmake_build_type"),
                "CMAKE_GENERATOR": str(controls.get("cmake_generator", "")),
                "CMAKE_MAKE_PROGRAM": str(controls.get("cmake_make_program", "")),
                "CMAKE_EXPORT_COMPILE_COMMANDS": (
                    "ON" if controls.get("cmake_export_compile_commands") else "OFF"
                ),
                "CMAKE_CXX_FLAGS": str(controls.get("cmake_cxx_flags", "")),
                "CMAKE_CXX_FLAGS_RELEASE": release_flags,
                "CMAKE_CXX_COMPILER": str(
                    controls.get("cmake_cxx_compiler", "/usr/bin/c++")
                ),
                "CMAKE_CXX_COMPILER_LAUNCHER": str(
                    controls.get("cmake_cxx_compiler_launcher", "")
                ),
                "CMAKE_INTERPROCEDURAL_OPTIMIZATION": (
                    "ON" if controls.get("interprocedural_optimization") else "OFF"
                ),
                "CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE": (
                    "ON" if controls.get("release_interprocedural_optimization") else "OFF"
                ),
                "UNITY_BUILDS": "ON" if controls.get("unity_builds") else "OFF",
                "USE_COREPCH": "ON" if controls.get("core_precompiled_headers") else "OFF",
                "USE_SCRIPTPCH": "ON" if controls.get("script_precompiled_headers") else "OFF",
                "WITH_COREDEBUG": "ON" if controls.get("with_coredebug") else "OFF",
            }
            cache_path = (worktree / "build/CMakeCache.txt").resolve()
            cache_values: dict[str, str] = {}
            if cache_path.is_file():
                for line in cache_path.read_text(encoding="utf-8").splitlines():
                    if not line or line.startswith(("//", "#")) or "=" not in line:
                        continue
                    typed_key, value = line.split("=", 1)
                    cache_values[typed_key.split(":", 1)[0]] = value
            current_cmake = {key: cache_values.get(key) for key in expected_cmake}
            if current_cmake != expected_cmake:
                rejections.append("effective_cmake_settings_policy_mismatch")
            build_configuration = receipt.get("build_configuration")
            stages = (
                [build_configuration.get(stage) for stage in ("request", "admission", "completion")]
                if isinstance(build_configuration, dict)
                else []
            )
            if len(stages) != 3 or not all(isinstance(stage, dict) for stage in stages):
                rejections.append("build_receipt_cmake_snapshots_missing")
            else:
                if not all(stage.get("settings") == expected_cmake for stage in stages):
                    rejections.append("build_receipt_cmake_settings_mismatch")
                if not all(stage.get("matches_policy") is True for stage in stages):
                    rejections.append("build_receipt_cmake_policy_match_missing")
                if not (
                    stages[0].get("settings_sha256")
                    == stages[1].get("settings_sha256")
                    == stages[2].get("settings_sha256")
                ):
                    rejections.append("build_receipt_cmake_settings_changed")
                if not (
                    stages[0].get("cache_sha256")
                    == stages[1].get("cache_sha256")
                    == stages[2].get("cache_sha256")
                ):
                    rejections.append("build_receipt_cmake_cache_changed")
                if not all(
                    stage.get("build_graph", {}).get("generated") is True
                    for stage in stages
                ):
                    rejections.append("build_receipt_generated_graph_invalid")
                if not (
                    stages[0].get("build_graph", {}).get("manifest_sha256")
                    == stages[1].get("build_graph", {}).get("manifest_sha256")
                    == stages[2].get("build_graph", {}).get("manifest_sha256")
                ):
                    rejections.append("build_receipt_generated_graph_changed")
                current_cache_sha256 = sha256_file(cache_path) if cache_path.is_file() else None
                if stages[2].get("cache_sha256") != current_cache_sha256:
                    rejections.append("build_receipt_cmake_cache_hash_mismatch")
                lineage = receipt.get("configure_lineage")
                if not isinstance(lineage, dict):
                    rejections.append("build_receipt_configure_lineage_missing")
                elif not (
                    lineage.get("completion_cache_sha256")
                        == stages[0].get("cache_sha256")
                    and lineage.get("completion_settings_sha256")
                        == stages[0].get("settings_sha256")
                    and lineage.get("compiler_sha256")
                        == stages[0].get("compiler_sha256")
                    and lineage.get("completion_build_graph_sha256")
                        == stages[0].get("build_graph", {}).get("manifest_sha256")
                    and isinstance(lineage.get("receipt_sha256"), str)
                    and isinstance(lineage.get("ticket_id"), str)
                ):
                    rejections.append("build_receipt_configure_lineage_mismatch")
            if receipt.get("build_configuration_stable") is not True:
                rejections.append("build_receipt_cmake_stability_missing")
        expected_config_sha256 = sha256_file(config) if config is not None and config.is_file() else None
        try:
            binary.relative_to(worktree)
        except ValueError:
            rejections.append("binary_outside_worktree")
        binary_bytes = binary.read_bytes() if binary.is_file() else b""
        is_elf = binary_bytes[:4] == b"\x7fELF"
        if not binary_bytes:
            rejections.append("binary_missing")
        if not is_elf:
            rejections.append("binary_not_elf")
        artifacts = receipt.get("output_artifacts")
        expected_binary = None
        if isinstance(artifacts, list):
            expected_binary = next(
                (row for row in artifacts if isinstance(row, dict) and row.get("kind") == "worldserver_elf"),
                None,
            )
        if not expected_binary:
            rejections.append("build_receipt_binary_artifact_missing")
        else:
            if expected_binary.get("sha256") != (sha256_file(binary) if binary.is_file() else None):
                rejections.append("build_receipt_binary_hash_mismatch")
            if Path(str(expected_binary.get("path", ""))).resolve() != binary.resolve():
                rejections.append("build_receipt_binary_path_mismatch")
            if expected_binary.get("size_bytes") != (binary.stat().st_size if binary.is_file() else 0):
                rejections.append("build_receipt_binary_size_mismatch")
            try:
                binary_mtime = binary.stat().st_mtime
                admitted_at = _utc_timestamp(str(receipt["admitted_at_utc"]))
                receipt_end = _utc_timestamp(str(receipt["ended_at_utc"]))
                if binary_mtime < admitted_at - 2.0:
                    rejections.append("binary_precedes_admitted_build")
                if binary_mtime > receipt_end + 2.0:
                    rejections.append("binary_newer_than_receipt")
                if expected_binary.get("produced_by_ticket") is not True:
                    rejections.append("build_receipt_binary_not_produced_by_ticket")
                if int(expected_binary.get("mtime_ns") or 0) != binary.stat().st_mtime_ns:
                    rejections.append("build_receipt_binary_mtime_mismatch")
            except (KeyError, OSError, TypeError, ValueError):
                rejections.append("binary_provenance_timestamp_unavailable")
        return {
            "valid": not rejections,
            "rejections": rejections,
            "receipt_path": str(receipt_path),
            "policy_path": str(policy_path),
            "receipt_sha256": receipt.get("receipt_sha256"),
            "ticket_id": receipt.get("ticket_id"),
            "commit": receipt.get("commit"),
            "worktree": receipt.get("worktree"),
            "classification": receipt.get("classification"),
            "test_mode": receipt.get("test_mode"),
            "config_sha256": expected_config_sha256,
            "binary_path": str(binary),
            "binary_sha256": sha256_file(binary) if binary.is_file() else None,
            "binary_size_bytes": binary.stat().st_size if binary.is_file() else 0,
            "binary_is_elf": is_elf,
            "binary_binding": (
                "privileged_ed25519_attestation_plus_coordinator_receipt_path_size_sha256_commit_and_timestamp_verified"
                if privileged_verification is not None
                else "explicit_trusted_local_operator_coordinator_receipt_path_size_sha256_commit_and_timestamp_verified"
            ),
            "privileged_attestation": privileged_verification,
            "receipt_trust_model": verification.get("receipt_trust_model"),
            "operator_identity": verification.get("operator_identity"),
            **compatibility_projection(source_compatibility),
        }
    except Exception as error:  # fail closed, while retaining a useful rejection
        return {
            "valid": False,
            "rejections": [f"build_receipt_verification_error:{type(error).__name__}:{error}"],
            "receipt_path": str(receipt_path),
            "policy_path": str(policy_path),
            "binary_path": str(binary),
        }


def build_policy_path_for_receipt(receipt_path: Path, worktree: Path) -> Path:
    """Resolve the tracked policy named by a receipt without accepting an override."""

    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"build receipt is unreadable: {error}") from error
    policy_id = receipt.get("policy_id")
    if not isinstance(policy_id, str) or not re.fullmatch(
        r"cata_raid_build_resource_policy_[a-z0-9_]+", policy_id
    ):
        raise RuntimeError("build receipt policy ID is invalid")
    policy_path = (
        worktree / "experiments/configs" / f"{policy_id}.json"
    ).resolve()
    policy_root = (worktree / "experiments/configs").resolve()
    if policy_path.parent != policy_root or not policy_path.is_file():
        raise RuntimeError("build receipt policy is not tracked by the worktree")
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"build policy is unreadable: {error}") from error
    if policy.get("policy_id") != policy_id:
        raise RuntimeError("build policy content does not match its receipt identity")
    return policy_path


def _process_arguments(pid: int) -> list[str]:
    try:
        return [
            value.decode(errors="replace")
            for value in (Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0"))
            if value
        ]
    except OSError:
        return []


def _protected_process_matches(arguments: list[str]) -> list[str]:
    """Classify process entrypoints without treating data arguments as processes.

    The capture command itself passes the prospective worldserver path through
    ``--binary``.  Scanning every argv basename therefore classified the
    capture's parent ``pixi`` process as a live worldserver.  Only argv[0] is an
    executable; for Python, the script or ``-m`` module is also an entrypoint.
    """

    if not arguments:
        return []
    protected_names = {
        "worldserver", "run_live_bot_validation.py", "live_validation_session.py",
        "run_phase9_serial_canaries.py", "publish_live_validation.py",
        "publish_live_validation", "promote_live_validation_artifact.py",
        "bot-live-validate", "operator", "raid_operator.py",
    }
    entrypoints = {Path(arguments[0]).name}
    executable = Path(arguments[0]).name.lower()
    if executable.startswith("python"):
        for index, value in enumerate(arguments[1:], start=1):
            if value == "-m" and index + 1 < len(arguments):
                module = arguments[index + 1].rsplit(".", 1)[-1]
                entrypoints.update((module, f"{module}.py"))
                break
            if not value.startswith("-"):
                entrypoints.add(Path(value).name)
                break
    return sorted(entrypoints & protected_names)


def _dvc_status_is_clean(output: str) -> bool:
    try:
        payload = json.loads(output)
    except (TypeError, ValueError):
        return False
    return isinstance(payload, dict) and not payload


def preflight_runtime_exclusions(worktree: Path) -> dict[str, Any]:
    """Require an idle coordinator and exclusive canonical-capture host."""

    from tools.raid_program.queued_build import Paths, status as coordinator_status

    coordinator = coordinator_status(Paths.for_worktree(worktree), recover=False)
    reasons: list[str] = []
    if coordinator.get("active") is not None:
        reasons.append("coordinator_active_lease")
    if coordinator.get("queue"):
        reasons.append("coordinator_queue_not_idle")

    overlap: list[dict[str, Any]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        arguments = _process_arguments(int(entry.name))
        if not arguments:
            continue
        matched = _protected_process_matches(arguments)
        lower_args = [value.lower() for value in arguments]
        dvc_index = next((index for index, value in enumerate(lower_args) if Path(value).name == "dvc"), None)
        if dvc_index is not None and "push" in lower_args[dvc_index + 1:]:
            matched.append("dvc push")
        if matched:
            overlap.append({"pid": int(entry.name), "matched": sorted(set(matched))})
    if overlap:
        reasons.append("canonical_process_overlap")
    return {
        "coordinator_idle": coordinator.get("active") is None and not coordinator.get("queue"),
        "coordinator": {
            "active": coordinator.get("active"),
            "queue": coordinator.get("queue", []),
        },
        "process_overlap": overlap,
        "reasons": reasons,
        "passed": not reasons,
    }


def validate_runtime_profile_assets(
    worktree: Path,
    reference_worktree: Path = ROOT,
    profile_name: str = "blackwing_descent_10n",
    require_dvc_lineage: bool = True,
    scenario_id: str | None = None,
    pool_tag: str | None = None,
) -> dict[str, Any]:
    """Fail closed when a capture lacks its exact profile-owned route partition.

    ``profile_name`` and ``scenario_id`` are explicit inputs for diagnostic
    boss shards.  The route file is shared, so validating only its full-file
    digest would allow a shard to consume a canonical or neighboring shard
    partition.  This function independently checks the selected scenario's
    contiguous node sequence, identity fields, diagnostic flags, and profile
    binding before a worldserver is started.
    """

    reasons: list[str] = []
    selected_scenario_id = scenario_id or profile_name
    if scenario_id is not None and scenario_id != profile_name:
        reasons.append("profile_scenario_argument_mismatch")
    if not selected_scenario_id:
        reasons.append("profile_scenario_required")
    profile_relative = Path("dataset/bot_runtime_profiles/profiles.json")

    def load_profile(root: Path) -> tuple[dict[str, Any] | None, Path | None, str | None]:
        manifest = root / profile_relative
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None, None, "profile_manifest_unreadable"
        profiles = payload.get("profiles") if isinstance(payload, dict) else None
        matches = [row for row in profiles or [] if isinstance(row, dict) and row.get("name") == profile_name]
        if len(matches) != 1:
            return None, None, "profile_missing_or_duplicated"
        profile = matches[0]
        route = profile.get("validation_route")
        if not isinstance(route, dict) or route.get("enable") is not True:
            return profile, None, "profile_route_disabled"
        route_text = route.get("manifest_path")
        if not isinstance(route_text, str) or not route_text:
            return profile, None, "profile_route_path_missing"
        if route.get("scenario_id") != selected_scenario_id:
            return profile, None, "profile_route_scenario_mismatch"
        route_relative = Path(route_text)
        if route_relative.is_absolute() or ".." in route_relative.parts:
            return profile, None, "profile_route_path_outside_worktree"
        route_path = (root / route_relative).resolve()
        try:
            route_path.relative_to(root.resolve())
        except ValueError:
            return profile, None, "profile_route_path_outside_worktree"
        return profile, route_path, None

    worktree_profile, route_path, worktree_error = load_profile(worktree)
    reference_profile, reference_route_path, reference_error = load_profile(reference_worktree)
    if worktree_error:
        reasons.append(f"worktree_{worktree_error}")
    if reference_error:
        reasons.append(f"reference_{reference_error}")
    if worktree_profile is not None:
        declared_tag = worktree_profile.get("pool_tag_filter")
        if ((profile_name != "blackwing_descent_10n" or pool_tag is not None)
                and (not isinstance(declared_tag, str) or not declared_tag)):
            reasons.append("profile_pool_tag_missing")
        elif pool_tag is not None and declared_tag != pool_tag:
            reasons.append("profile_pool_tag_argument_mismatch")
        if worktree_profile.get("name") != profile_name:
            reasons.append("profile_name_identity_mismatch")
        route = worktree_profile.get("validation_route")
        if isinstance(route, dict) and route.get("scenario_id") != selected_scenario_id:
            reasons.append("profile_scenario_identity_mismatch")

    route_rows = 0
    route_sha256 = None
    reference_route_sha256 = None
    route_partition: dict[str, Any] = {
        "scenario_id": selected_scenario_id,
        "profile_name": profile_name,
        "node_count": 0,
        "terminal_index": None,
        "terminal_kind": None,
        "node_ids": [],
        "diagnostic_only": None,
        "boss_node_count": 0,
        "passed": False,
        "reasons": [],
    }
    if route_path is not None:
        try:
            route_bytes = route_path.read_bytes()
            if not route_bytes:
                reasons.append("worktree_route_manifest_empty")
            if len(route_bytes) > 4 * 1024 * 1024:
                reasons.append("worktree_route_manifest_oversized")
            route_sha256 = hashlib.sha256(route_bytes).hexdigest()
            rows = [json.loads(line) for line in route_bytes.decode("utf-8").splitlines() if line.strip()]
            matching_rows = [row for row in rows if isinstance(row, dict) and row.get("scenario_id") == selected_scenario_id]
            route_rows = len(matching_rows)
            route_partition["node_count"] = route_rows
            if route_rows == 0:
                route_partition["reasons"].append("route_partition_empty")
            steps = [int(row.get("step") or 0) for row in matching_rows]
            node_ids = [str(row.get("route_node_id") or "") for row in matching_rows]
            kinds = [str(row.get("kind") or "") for row in matching_rows]
            route_partition["node_ids"] = node_ids
            route_partition["terminal_index"] = route_rows - 1 if route_rows else None
            route_partition["terminal_kind"] = kinds[-1] if kinds else None
            diagnostic_values = [row.get("diagnostic_only") for row in matching_rows]
            diagnostic_only = diagnostic_values[0] if diagnostic_values else None
            route_partition["diagnostic_only"] = diagnostic_only
            route_partition["boss_node_count"] = sum(kind == "boss" for kind in kinds)
            expected_partition = EXPECTED_BWD_ROUTE_PARTITION_COUNTS.get(profile_name)
            if expected_partition is not None and (
                route_rows != expected_partition[0]
                or route_partition["boss_node_count"] != expected_partition[1]
            ):
                route_partition["reasons"].append("route_partition_shape_mismatch")
            if matching_rows and isinstance(worktree_profile, dict):
                if any(row.get("runtime_profile_id", profile_name) != profile_name for row in matching_rows):
                    route_partition["reasons"].append("route_partition_runtime_profile_mismatch")
                declared_population = worktree_profile.get("target_population")
                route_population = matching_rows[0].get("expected_bot_count")
                if (isinstance(declared_population, int) and declared_population > 0
                        and route_population != declared_population):
                    route_partition["reasons"].append("route_partition_roster_size_mismatch")
                expected_roster = matching_rows[0].get("roster_identity")
                if declared_population and (
                    not isinstance(expected_roster, list)
                    or len(expected_roster) != declared_population
                    or len({str(row.get("roster_slot_id")) for row in expected_roster if isinstance(row, dict)}) != declared_population
                    or len({str(row.get("guid")) for row in expected_roster if isinstance(row, dict)}) != declared_population
                    or any(
                        not isinstance(row, dict)
                        or not str(row.get("roster_slot_id") or "").strip()
                        or not _positive_int(row.get("guid"))
                        or not str(row.get("name") or "").strip()
                        or not str(row.get("class_spec") or "").strip()
                        or not str(row.get("role") or "").strip()
                        for row in expected_roster
                    )
                ):
                    route_partition["reasons"].append("route_partition_roster_identity_invalid")
                roster_signatures = {
                    _canonical_object_sha256(row.get("roster_identity"))
                    if isinstance(row.get("roster_identity"), list) else "missing"
                    for row in matching_rows
                }
                if len(roster_signatures) != 1:
                    route_partition["reasons"].append("route_partition_roster_identity_drift")
            route_identity = tuple(
                (
                    int(row.get("step") or 0),
                    str(row.get("kind") or ""),
                    str(row.get("label") or ""),
                    int(row.get("source_entry") or 0),
                    str(row.get("source_guid") or ""),
                )
                for row in matching_rows
            )
            if steps != list(range(1, route_rows + 1)):
                route_partition["reasons"].append("route_partition_steps_not_contiguous")
                if selected_scenario_id == "blackwing_descent_10n":
                    reasons.append("worktree_route_steps_not_ordered_one_through_eleven")
            # Preserve the canonical Phase 1 identity contract for the
            # foundation capture. Diagnostic shards use the generated
            # partition contract above and are never compared to this list.
            if selected_scenario_id == "blackwing_descent_10n":
                if route_rows != len(EXPECTED_BWD_ROUTE_IDENTITY):
                    reasons.append("worktree_route_expected_eleven_rows")
                if route_identity != EXPECTED_BWD_ROUTE_IDENTITY:
                    reasons.append("worktree_route_identity_mismatch")
            if any(not node_id for node_id in node_ids):
                route_partition["reasons"].append("route_partition_node_id_missing")
            if len(set(node_ids)) != len(node_ids):
                route_partition["reasons"].append("route_partition_node_id_duplicated")
            if any(not kind for kind in kinds):
                route_partition["reasons"].append("route_partition_kind_missing")
            if kinds and kinds[-1] != "boss":
                route_partition["reasons"].append("route_partition_terminal_not_boss")
            for row in matching_rows:
                kind = str(row.get("kind") or "")
                if kind in {"trash", "boss"} and not str(row.get("label") or "").strip():
                    route_partition["reasons"].append("route_partition_target_label_missing")
                if kind in {"trash", "boss"} and not str(row.get("source_guid") or "").strip():
                    route_partition["reasons"].append("route_partition_target_identity_missing")
            if matching_rows and any(value != diagnostic_only for value in diagnostic_values):
                route_partition["reasons"].append("route_partition_diagnostic_flag_drift")
            if worktree_profile is not None:
                declared_diagnostic = worktree_profile.get("diagnostic_only")
                if declared_diagnostic is not None and diagnostic_only != declared_diagnostic:
                    route_partition["reasons"].append("route_partition_profile_diagnostic_mismatch")
                parent = worktree_profile.get("diagnostic_parent_scenario_id")
                if parent and any(row.get("diagnostic_parent_scenario_id") != parent for row in matching_rows):
                    route_partition["reasons"].append("route_partition_parent_identity_mismatch")
                prerequisite = worktree_profile.get("prerequisite_contract")
                if declared_diagnostic is True:
                    if not isinstance(prerequisite, dict) or prerequisite.get("certifies_predecessors") is not False:
                        route_partition["reasons"].append("profile_prerequisite_contract_not_noncertifying")
                    else:
                        expected_precompleted = prerequisite.get("precompleted_boss_entries", [])
                        for row in matching_rows:
                            state = row.get("diagnostic_prerequisite_state")
                            if not isinstance(state, dict):
                                route_partition["reasons"].append("route_partition_prerequisite_state_missing")
                                continue
                            if state.get("certifies_predecessors") is not False:
                                route_partition["reasons"].append("route_partition_prerequisite_certification_enabled")
                            if ("precompleted_boss_entries" not in state
                                    or state.get("precompleted_boss_entries") != expected_precompleted):
                                route_partition["reasons"].append("route_partition_precompleted_boss_identity_mismatch")
                            for key in ("upper_ledge_start", "requires_native_descent_before_engagement"):
                                if key in prerequisite and state.get(key) != prerequisite.get(key):
                                    route_partition["reasons"].append(f"route_partition_prerequisite_{key}_mismatch")
                        if prerequisite.get("requires_native_descent_before_engagement") is True:
                            descent_rows = [row for row in matching_rows if str(row.get("node_kind") or "") == "descent"]
                            preparation_rows = [row for row in matching_rows if row.get("upper_ledge_preparation") is True]
                            if not descent_rows:
                                route_partition["reasons"].append("route_partition_native_descent_node_missing")
                            elif any(row.get("descent_action") != "native_jump_or_fall" for row in descent_rows):
                                route_partition["reasons"].append("route_partition_native_descent_action_invalid")
                            if not preparation_rows:
                                route_partition["reasons"].append("route_partition_upper_ledge_preparation_missing")
                            elif descent_rows and not any(
                                isinstance(prep.get("z"), (int, float))
                                and isinstance(descent.get("z"), (int, float))
                                and prep["z"] > descent["z"]
                                for prep in preparation_rows for descent in descent_rows
                            ):
                                route_partition["reasons"].append("route_partition_upper_ledge_height_invalid")
            route_partition["passed"] = not route_partition["reasons"]
            reasons.extend(route_partition["reasons"])
        except (OSError, UnicodeError, ValueError, TypeError):
            reasons.append("worktree_route_manifest_unreadable")
    if reference_route_path is not None:
        try:
            reference_route_sha256 = sha256_file(reference_route_path)
        except OSError:
            reasons.append("reference_route_manifest_unreadable")

    if worktree_profile is not None and reference_profile is not None and worktree_profile != reference_profile:
        reasons.append("runtime_profile_differs_from_reference")
    if route_sha256 is not None and reference_route_sha256 is not None and route_sha256 != reference_route_sha256:
        reasons.append("runtime_route_differs_from_reference")

    dvc_status = None
    if require_dvc_lineage:
        dvc_environment = os.environ.copy()
        # A capture launched by ``pixi run`` inherits the caller's manifest
        # path.  The DVC check intentionally runs in the reviewed worktree;
        # leaving the caller locator set produces a warning on otherwise clean
        # output and makes the exact human-text check reject itself.
        dvc_environment.pop("PIXI_PROJECT_MANIFEST", None)
        result = subprocess.run(
            ["pixi", "run", "dvc", "status", "validation_scenarios", "--json"],
            cwd=worktree,
            env=dvc_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
            check=False,
        )
        dvc_status = result.stdout.strip()
        if result.returncode != 0 or not _dvc_status_is_clean(dvc_status):
            reasons.append("runtime_route_dvc_lineage_dirty")

    return {
        "profile_name": profile_name,
        "profile_manifest": str(worktree / profile_relative),
        "route_manifest": str(route_path) if route_path else None,
        "route_sha256": route_sha256,
        "reference_route_sha256": reference_route_sha256,
        "matching_route_rows": route_rows,
        "scenario_id": selected_scenario_id,
        "pool_tag_filter": (
            worktree_profile.get("pool_tag_filter")
            if isinstance(worktree_profile, dict) else None
        ),
        "route_partition": route_partition,
        "dvc_stage": "validation_scenarios",
        "dvc_status": dvc_status,
        "reasons": reasons,
        "passed": not reasons,
    }
