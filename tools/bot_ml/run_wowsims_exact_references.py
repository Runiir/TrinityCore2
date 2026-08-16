#!/usr/bin/env python3
"""Build and run content-addressed, live-compatible WoWSims references.

The request catalog describes intended inputs.  It is never evidence by itself.
This module admits the native RaidSimRequest bytes, executes a clean pinned
WoWSims CLI in an isolated process group, and derives every numeric observation
from the native RaidSimResult bytes.  Publication/reconstruction remains a
separate DVC lifecycle step.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .build_wowsims_reference_requests import (
    canonical_sha256 as request_canonical_sha256,
    load_manifest as load_request_manifest,
    pending_catalog_projection,
    request_by_spec,
    request_condition_projection as project_request_contract_conditions,
    validate_manifest as validate_request_manifest,
)
from .live_validation_session import sha256_file, sha256_text
from .phase8_fixture_contract import load_fixture_contract
from .run_cata_raid_dps_acceptance import run_child_process_group
from .wowsims_gear_binding import canonical_sha256, canonical_wowsims_manifest


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REQUEST_CATALOG = (
    REPO_ROOT / "experiments/configs/wowsims_cata_dps_reference_requests_v1.json"
)
DEFAULT_FIXTURE_CONTRACT = (
    REPO_ROOT
    / "experiments/configs/phase8_calibration_fixture_contract_v1.materialized.json"
)
DEFAULT_GEAR_PROFILES = (
    REPO_ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json"
)
BUILD_RECEIPT_SCHEMA = "wowsims_cata_cli_build_receipt_v1"
GENERATION_RECEIPT_SCHEMA = "wowsims_cata_reference_generation_receipt_v1"
CONDITION_PROJECTION_SCHEMA = "wowsims_native_request_condition_projection_v1"
MATERIALIZATION_RECEIPT_SCHEMA = "wowsims_native_request_materialization_receipt_v1"
DVC_RECONSTRUCTION_SCHEMA = "wowsims_dvc_reconstruction_receipt_v1"
PROMOTION_INDEX_SCHEMA = "wowsims_generated_reference_promotion_index_v1"
RESEARCH_CLASSIFICATION = "research_only_not_gate_bearing"
UNPUBLISHED_CLASSIFICATION = "generated_candidate_requires_dvc_reconstruction"
EXPECTED_ITERATIONS = 2000
EXPECTED_RANDOM_SEED = 101
FORBIDDEN_TEMPORAL_EXTERNAL_RESULT_SPELL_IDS = {
    2825,
    32182,
    80353,
    10060,
    85759,
    85767,
    82174,
    82175,
    96230,
}
DEFAULT_COMMAND_TIMEOUT_SECONDS = 900.0
SHA256_LENGTH = 64
REQUEST_VALIDATOR_SOURCE = b'''package main

import (
    "fmt"
    "os"

    "github.com/wowsims/cata/sim"
    "github.com/wowsims/cata/sim/core"
    "github.com/wowsims/cata/sim/core/proto"
    "google.golang.org/protobuf/encoding/protojson"
)

func main() {
    if len(os.Args) != 3 {
        fmt.Fprintln(os.Stderr, "usage: wowsimrequestvalidate REQUEST.json COMPUTE_STATS.json")
        os.Exit(2)
    }
    sim.RegisterAll()
    payload, err := os.ReadFile(os.Args[1])
    if err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
    request := &proto.RaidSimRequest{}
    if err := (protojson.UnmarshalOptions{DiscardUnknown: false}).Unmarshal(payload, request); err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
    result := core.ComputeStats(&proto.ComputeStatsRequest{Raid: request.Raid, Encounter: request.Encounter})
    if result.ErrorResult != "" {
        fmt.Fprintln(os.Stderr, result.ErrorResult)
        os.Exit(1)
    }
    output, err := (protojson.MarshalOptions{EmitUnpopulated: true}).Marshal(result)
    if err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
    if err := os.WriteFile(os.Args[2], output, 0600); err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
}
'''

PROTO_RACE_TO_TRINITY_ID = {
    "RaceHuman": 1,
    "RaceOrc": 2,
    "RaceDwarf": 3,
    "RaceNightElf": 4,
    "RaceUndead": 5,
    "RaceTauren": 6,
    "RaceGnome": 7,
    "RaceTroll": 8,
    "RaceGoblin": 9,
    "RaceBloodElf": 10,
    "RaceDraenei": 11,
    "RaceWorgen": 22,
}
TRINITY_RACE_TO_PROTO = {value: key for key, value in PROTO_RACE_TO_TRINITY_ID.items()}
TRINITY_CLASS_TO_PROTO = {
    1: "ClassWarrior",
    2: "ClassPaladin",
    3: "ClassHunter",
    4: "ClassRogue",
    5: "ClassPriest",
    6: "ClassDeathKnight",
    7: "ClassShaman",
    8: "ClassMage",
    9: "ClassWarlock",
    11: "ClassDruid",
}
TRINITY_CLASS_TO_SOURCE_STEM = {
    1: "warrior",
    2: "paladin",
    3: "hunter",
    4: "rogue",
    5: "priest",
    6: "death_knight",
    7: "shaman",
    8: "mage",
    9: "warlock",
    11: "druid",
}
NATIVE_SPEC_KEYS = {
    "affliction_warlock",
    "arms_warrior",
    "assassination_rogue",
    "balance_druid",
    "combat_rogue",
    "demonology_warlock",
    "elemental_shaman",
    "feral_druid",
    "fire_mage",
    "frost_death_knight",
    "fury_warrior",
    "marksmanship_hunter",
    "retribution_paladin",
    "shadow_priest",
    "survival_hunter",
    "unholy_death_knight",
}
MANDATORY_FORBIDDEN_GENERIC_APL_OPERATIONS = {
    "autocast_other_cooldowns",
    "cast_all_stat_buff_cooldowns",
    "activate_all_stat_buff_proc_auras",
    "item_swap",
}
FORBIDDEN_STATE_MUTATION_APL_OPERATIONS = {
    "activate_aura",
    "activate_aura_with_stacks",
    "trigger_icd",
    "cancel_aura",
}


class WowsimsGenerationError(ValueError):
    """Raised when source, request, result, or transport identity is unsafe."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise WowsimsGenerationError(reason)


def _normalized_repository_url(value: Any) -> str:
    normalized = str(value or "").rstrip("/")
    return normalized[:-4] if normalized.endswith(".git") else normalized


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _json_object_from_bytes(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WowsimsGenerationError(f"{label}:invalid_json") from exc
    _require(isinstance(value, dict), f"{label}:not_object")
    return value


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    _require(path.is_file(), f"{label}:missing")
    return _json_object_from_bytes(path.read_bytes(), label=label)


def load_slot_map(path: Path = DEFAULT_GEAR_PROFILES) -> list[int]:
    payload = _read_json_object(path, label="gear_profiles")
    slot_map = payload.get("slot_map")
    _require(isinstance(slot_map, list) and bool(slot_map), "gear_profiles:slot_map")
    values = [int(value) for value in slot_map]
    _require(len(values) == len(set(values)), "gear_profiles:duplicate_slots")
    return values


def _write_exact(path: Path, payload: bytes, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _require(path.is_file(), f"artifact_path_not_file:{path}")
        _require(path.read_bytes() == payload, f"artifact_content_collision:{path}")
    else:
        handle, raw_temp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp_path = Path(raw_temp_path)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
    if executable:
        path.chmod(0o755)


def store_content_addressed_bytes(
    output_root: Path,
    artifact_kind: str,
    payload: bytes,
    *,
    suffix: str,
    executable: bool = False,
) -> dict[str, Any]:
    _require(
        artifact_kind.replace("_", "").isalnum(), "unsafe_artifact_kind"
    )
    digest = hashlib.sha256(payload).hexdigest()
    path = output_root / artifact_kind / f"{digest}{suffix}"
    _write_exact(path, payload, executable=executable)
    return {
        "path": path.relative_to(output_root).as_posix(),
        "sha256": digest,
        "byte_count": len(payload),
    }


def store_content_addressed_json(
    output_root: Path, artifact_kind: str, value: Mapping[str, Any]
) -> dict[str, Any]:
    return store_content_addressed_bytes(
        output_root, artifact_kind, canonical_json_bytes(value), suffix=".json"
    )


def verify_artifact(
    record: Mapping[str, Any], *, artifact_root: Path, label: str
) -> Path:
    relative = Path(str(record.get("path") or ""))
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{label}:unsafe_path")
    _require(not artifact_root.is_symlink(), f"{label}:artifact_root_symlink")
    root = artifact_root.resolve()
    unresolved_path = root / relative
    cursor = root
    for part in relative.parts:
        cursor /= part
        _require(not cursor.is_symlink(), f"{label}:symlink")
    path = unresolved_path.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise WowsimsGenerationError(f"{label}:outside_root") from exc
    _require(path.is_file(), f"{label}:missing")
    expected_sha = str(record.get("sha256") or "")
    _require(len(expected_sha) == SHA256_LENGTH, f"{label}:sha256")
    _require(sha256_file(path) == expected_sha, f"{label}:hash_mismatch")
    _require(path.stat().st_size == int(record.get("byte_count", -1)), f"{label}:size")
    return path


def _run_capture(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: float,
) -> tuple[dict[str, Any], bytes]:
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stream:
        started_ns = time.time_ns()
        outcome, interrupted = run_child_process_group(
            command,
            cwd=cwd,
            env=env,
            output_stream=stream,
            timeout_sec=timeout_seconds,
        )
        finished_ns = time.time_ns()
        stream.flush()
        stream.seek(0)
        output = stream.read().encode("utf-8")
    if interrupted is not None:
        raise WowsimsGenerationError("child_controller_interrupted") from interrupted
    observed = {
        **outcome,
        "command": [str(value) for value in command],
        "command_sha256": canonical_sha256([str(value) for value in command]),
        "working_directory": cwd.resolve().as_posix(),
        "started_unix_ns": started_ns,
        "finished_unix_ns": finished_ns,
        "wall_duration_ns": max(0, finished_ns - started_ns),
        "output_sha256": hashlib.sha256(output).hexdigest(),
        "output_byte_count": len(output),
    }
    return observed, output


def _require_normal_child(outcome: Mapping[str, Any], *, label: str) -> None:
    _require(outcome.get("transport_classification") == "child_exited", f"{label}:transport")
    _require(outcome.get("returncode_observed") is True, f"{label}:returncode_unobserved")
    _require(outcome.get("returncode") == 0, f"{label}:returncode")
    _require(outcome.get("outer_timed_out") is False, f"{label}:timeout")
    _require(outcome.get("controller_interrupted") is False, f"{label}:interrupted")
    _require(outcome.get("process_group_gone") is True, f"{label}:process_group")


def verify_process_evidence(
    transport: Mapping[str, Any],
    process_log: Mapping[str, Any],
    *,
    artifact_root: Path,
    label: str,
) -> Path:
    """Bind a successful child-process claim to its retained output bytes."""
    _require_normal_child(transport, label=label)
    log_path = verify_artifact(
        process_log,
        artifact_root=artifact_root,
        label=f"{label}:process_log",
    )
    _require(
        transport.get("output_sha256") == sha256_file(log_path)
        and int(transport.get("output_byte_count", -1)) == log_path.stat().st_size,
        f"{label}:process_output_identity",
    )
    return log_path


def _git_output(checkout: Path, arguments: Sequence[str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(checkout), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def clean_checkout_identity(checkout: Path, expected_revision: str) -> dict[str, Any]:
    checkout = checkout.resolve()
    _require((checkout / ".git").exists(), "wowsims_checkout_not_git")
    revision = _git_output(checkout, ["rev-parse", "HEAD"])
    status = _git_output(checkout, ["status", "--porcelain=v1", "--untracked-files=all"])
    remote = _git_output(checkout, ["remote", "get-url", "origin"])
    _require(revision == expected_revision, "wowsims_source_revision_mismatch")
    _require(status == "", "wowsims_source_dirty")
    return {
        "repository": remote,
        "revision": revision,
        "source_tree_clean": True,
        "porcelain_sha256": sha256_text(status),
    }


def _checked_source_bytes(
    checkout: Path, relative_path: str, *, expected_revision: str, label: str
) -> bytes:
    relative = Path(relative_path)
    _require(
        relative_path and not relative.is_absolute() and ".." not in relative.parts,
        f"{label}:unsafe_path",
    )
    root = checkout.resolve()
    path = root / relative
    cursor = root
    for part in relative.parts:
        cursor /= part
        _require(not cursor.is_symlink(), f"{label}:symlink")
    try:
        path.resolve().relative_to(root)
    except ValueError as exc:
        raise WowsimsGenerationError(f"{label}:outside_root") from exc
    _require(path.is_file(), f"{label}:missing")
    working_bytes = path.read_bytes()
    try:
        committed_bytes = subprocess.run(
            ["git", "-C", str(checkout), "show", f"{expected_revision}:{relative.as_posix()}"],
            check=True,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise WowsimsGenerationError(f"{label}:not_at_pinned_revision") from exc
    _require(working_bytes == committed_bytes, f"{label}:working_tree_drift")
    return working_bytes


def _snake_case_key(value: str) -> str:
    first = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first).lower()


def _snake_case_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {_snake_case_key(str(key)): _snake_case_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_snake_case_json(item) for item in value]
    return value


def decode_talent_spell_ids(
    talent_string: str, talent_trees: Sequence[Mapping[str, Any]]
) -> list[int]:
    """Decode WoWSims' wowhead talent string through the pinned UI tree data."""
    trees = talent_string.split("-")
    _require(len(trees) <= len(talent_trees), "talents:tree_count")
    decoded: list[int] = []
    for tree_index, tree_string in enumerate(trees):
        talents = talent_trees[tree_index].get("talents") or []
        _require(len(tree_string) <= len(talents), f"talents:tree_length:{tree_index}")
        for talent_index, point_character in enumerate(tree_string):
            _require(point_character.isdigit(), "talents:non_numeric")
            points = int(point_character)
            talent = talents[talent_index]
            _require(isinstance(talent, Mapping), "talents:row")
            max_points = int(talent.get("maxPoints", -1))
            spell_ids = talent.get("spellIds") or []
            _require(0 <= points <= max_points, "talents:rank")
            _require(len(spell_ids) == max_points, "talents:spell_rank_count")
            if points:
                decoded.append(int(spell_ids[points - 1]))
    return sorted(decoded)


def _glyph_enum_members(proto_source: str, enum_suffix: str) -> set[int]:
    match = re.search(
        rf"enum\s+[A-Za-z]+{re.escape(enum_suffix)}Glyph\s*\{{(?P<body>.*?)\}}",
        proto_source,
        re.DOTALL,
    )
    _require(match is not None, f"glyphs:enum_missing:{enum_suffix}")
    return {
        int(value)
        for value in re.findall(r"=\s*([0-9]+)\s*;", match.group("body"))
        if int(value) > 0
    }


def glyph_slots_from_pinned_proto(
    glyph_item_ids: Sequence[int], proto_source: str
) -> dict[str, int]:
    category_members = {
        "prime": _glyph_enum_members(proto_source, "Prime"),
        "major": _glyph_enum_members(proto_source, "Major"),
        "minor": _glyph_enum_members(proto_source, "Minor"),
    }
    categorized: dict[str, list[int]] = {key: [] for key in category_members}
    for raw_value in glyph_item_ids:
        value = int(raw_value)
        categories = [key for key, members in category_members.items() if value in members]
        _require(len(categories) == 1, f"glyphs:category:{value}")
        categorized[categories[0]].append(value)
    for category, values in categorized.items():
        _require(len(values) <= 3, f"glyphs:too_many:{category}")
    slots: dict[str, int] = {}
    for category in ("prime", "major", "minor"):
        for index, value in enumerate(categorized[category], start=1):
            slots[f"{category}{index}"] = value
    return slots


def apl_action_variants_from_pinned_proto(proto_source: str) -> set[str]:
    """Return the exact native APLAction oneof field names from pinned apl.proto."""
    message = re.search(
        r"message\s+APLAction\s*\{(?P<body>.*?)\n\}", proto_source, re.DOTALL
    )
    _require(message is not None, "apl_proto:action_message")
    oneof = re.search(
        r"oneof\s+action\s*\{(?P<body>.*?)\n\s*\}",
        message.group("body"),
        re.DOTALL,
    )
    _require(oneof is not None, "apl_proto:action_oneof")
    fields = {
        field
        for field in re.findall(
            r"\bAPLAction[A-Za-z0-9_]+\s+([a-z][a-z0-9_]*)\s*=\s*[0-9]+\s*;",
            oneof.group("body"),
        )
    }
    _require(
        (
            MANDATORY_FORBIDDEN_GENERIC_APL_OPERATIONS
            | FORBIDDEN_STATE_MUTATION_APL_OPERATIONS
        ).issubset(fields),
        "apl_proto:mandatory_generic_operations",
    )
    return fields


def apl_condition_variants_from_pinned_proto(proto_source: str) -> set[str]:
    """Return the exact native APLValue oneof field names from pinned apl.proto."""
    message = re.search(
        r"message\s+APLValue\s*\{(?P<body>.*?)\n\}", proto_source, re.DOTALL
    )
    _require(message is not None, "apl_proto:value_message")
    oneof = re.search(
        r"oneof\s+value\s*\{(?P<body>.*?)\n\s*\}",
        message.group("body"),
        re.DOTALL,
    )
    _require(oneof is not None, "apl_proto:value_oneof")
    fields = {
        field
        for field in re.findall(
            r"\bAPLValue[A-Za-z0-9_]+\s+([a-z][a-z0-9_]*)\s*=\s*[0-9]+\s*;",
            oneof.group("body"),
        )
    }
    _require(
        {
            "const",
            "and",
            "or",
            "not",
            "cmp",
            "math",
            "number_targets",
            "aura_is_active",
            "aura_is_known",
            "aura_remaining_time",
            "dot_is_active",
            "spell_time_to_ready",
        }
        <= fields,
        "apl_proto:mandatory_condition_values",
    )
    return fields


_REMOVE_APL_NODE = object()


def transform_apl_rotation(
    rotation: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    prepull_actions: Sequence[Mapping[str, Any]],
    action_variants: set[str],
    condition_variants: set[str],
    equipped_item_ids: set[int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply the fixture-owned recursive dynamic-action deny policy."""
    _require(
        policy.get("schema") == "phase8_forbidden_dynamic_actions_transform_v1"
        and policy.get("policy") == "recursive_remove_matching_action"
        and policy.get("matching_semantics")
        == "exact_native_field_and_canonical_full_payload"
        and policy.get("combat_tree_policy") == "preserve_allowed_nodes_and_order"
        and policy.get("preserve_surviving_action_order") is True
        and policy.get("empty_node_policy")
        == "remove_empty_sequence_or_strict_sequence_parent_recursively"
        and policy.get("unlisted_cast_item_policy") == "reject"
        and policy.get("unknown_generic_operation_policy") == "reject"
        and policy.get("provenance_policy")
        == "hash_input_output_removed_and_added_actions",
        "apl_transform:policy",
    )
    _require(bool(action_variants), "apl_transform:action_variants")
    _require(bool(condition_variants), "apl_transform:condition_variants")
    forbidden_kinds = {str(value) for value in policy.get("forbidden_action_kinds") or []}
    forbidden_generic_rows = policy.get("forbidden_generic_operations") or []
    _require(
        isinstance(forbidden_generic_rows, list)
        and all(isinstance(value, Mapping) for value in forbidden_generic_rows),
        "apl_transform:forbidden_generic_operations",
    )
    forbidden_generic_operations = {
        str(value.get("native_field") or "") for value in forbidden_generic_rows
    }
    _require(
        (
            MANDATORY_FORBIDDEN_GENERIC_APL_OPERATIONS
            | FORBIDDEN_STATE_MUTATION_APL_OPERATIONS
        )
        <= forbidden_generic_operations
        <= action_variants,
        "apl_transform:generic_operation_coverage",
    )
    for row in forbidden_generic_rows:
        semantic_name = str(row.get("semantic_name") or "")
        native_field = str(row.get("native_field") or "")
        _require(
            semantic_name
            and native_field
            and _snake_case_key(semantic_name) == native_field,
            "apl_transform:generic_operation_spelling",
        )
    forbidden_spell_ids = {
        int(value) for value in policy.get("forbidden_cast_spell_ids") or []
    }
    forbidden_item_ids = {
        int(value) for value in policy.get("forbidden_cast_item_ids") or []
    }
    allowed_item_ids = {
        int(value) for value in policy.get("allowed_cast_item_ids") or []
    }
    state_mutation_rows = policy.get("forbidden_state_mutation_instances") or []
    _require(
        isinstance(state_mutation_rows, list)
        and all(isinstance(value, Mapping) for value in state_mutation_rows)
        and policy.get("unlisted_state_mutation_instance_policy") == "reject",
        "apl_transform:state_mutation_policy",
    )
    declared_state_mutations = {
        canonical_json_bytes(dict(value)) for value in state_mutation_rows
    }
    _require(bool(forbidden_kinds), "apl_transform:forbidden_action_kinds")
    _require(bool(forbidden_spell_ids), "apl_transform:forbidden_spell_ids")
    _require(70142 in forbidden_item_ids, "apl_transform:moonwell_chalice")
    _require(
        not (forbidden_item_ids & allowed_item_ids),
        "apl_transform:item_policy_overlap",
    )
    _require(
        allowed_item_ids <= equipped_item_ids,
        "apl_transform:allowed_item_not_equipped",
    )
    prepull_policy = policy.get("prepull_replacement_policy") or {}
    _require(
        prepull_policy
        == {
            "mode": "replace_entire_source_with_fixture_exact_list",
            "source_prepull_policy": "record_and_remove_all",
            "replacement_source_field": "native_request.rotation_prepull_actions",
            "replacement_order_policy": "preserve_declared_order",
            "replacement_reason": "live_native_persistent_setup_then_resource_cooldown_clean_edge",
            "pet_or_option_setup_policy": "represent_at_start_and_do_not_recast",
            "source_provenance": "hash_bytes_count_and_action_identities",
        },
        "apl_transform:prepull_replacement_policy",
    )
    condition_policy = policy.get("condition_rewrite_policy") or {}
    _require(
        condition_policy.get("schema")
        == "phase8_exact_native_condition_payload_rewrite_v2"
        and condition_policy.get("authority")
        == "materialized_live_fixture_absence"
        and condition_policy.get("boolean_folding")
        == "deterministic_recursive_not_and_or_constant_fold"
        and condition_policy.get("numeric_folding")
        == "deterministic_recursive_arithmetic_and_comparison_constant_fold"
        and condition_policy.get("false_row_policy") == "remove_action_row"
        and condition_policy.get("true_condition_policy")
        == "remove_condition_field"
        and condition_policy.get("unknown_condition_leaf_policy") == "reject"
        and condition_policy.get("unresolved_target_reference_policy") == "reject"
        and condition_policy.get("compute_stats_warning_or_error_policy") == "reject"
        and condition_policy.get("provenance_policy")
        == "record_path_before_after_reason_and_hashes",
        "apl_transform:condition_rewrite_policy",
    )
    condition_rows = condition_policy.get("unavailable_condition_leaves") or []
    _require(
        isinstance(condition_rows, list)
        and all(isinstance(value, Mapping) for value in condition_rows),
        "apl_transform:condition_rows",
    )
    unavailable_conditions: dict[str, dict[bytes, dict[str, Any]]] = {}
    unavailable_payload_ids: dict[str, set[tuple[str, int]]] = {}

    def payload_ids(value: Any) -> set[tuple[str, int]]:
        observed: set[tuple[str, int]] = set()
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key in {"spell_id", "item_id"} and isinstance(child, int) and child > 0:
                    observed.add((str(key), child))
                observed.update(payload_ids(child))
        elif isinstance(value, list):
            for child in value:
                observed.update(payload_ids(child))
        return observed

    for row in condition_rows:
        native_field = str(row.get("native_field") or "")
        payloads = row.get("payloads") or []
        is_numeric = native_field in {"aura_remaining_time", "spell_time_to_ready"}
        _require(
            native_field
            in {
                "aura_is_active",
                "aura_is_known",
                "aura_remaining_time",
                "dot_is_active",
                "spell_time_to_ready",
            }
            and isinstance(payloads, list)
            and payloads
            and all(isinstance(value, Mapping) and bool(value) for value in payloads)
            and (
                (
                    is_numeric
                    and row.get("replacement") == 0
                    and row.get("replacement_type") == "number"
                )
                or (
                    not is_numeric
                    and row.get("replacement") is False
                    and "replacement_type" not in row
                )
            ),
            "apl_transform:condition_row",
        )
        _require(
            native_field not in unavailable_conditions,
            "apl_transform:condition_duplicate",
        )
        by_payload: dict[bytes, dict[str, Any]] = {}
        configured_ids: set[tuple[str, int]] = set()
        for payload in payloads:
            payload_key = canonical_json_bytes(payload)
            _require(
                payload_key not in by_payload,
                "apl_transform:condition_payload_duplicate",
            )
            exact_ids = payload_ids(payload)
            _require(bool(exact_ids), "apl_transform:condition_payload_identity")
            configured_ids.update(exact_ids)
            by_payload[payload_key] = {
                "payload": copy.deepcopy(dict(payload)),
                "replacement": row.get("replacement"),
                "replacement_type": row.get("replacement_type", "boolean"),
            }
        unavailable_conditions[native_field] = by_payload
        unavailable_payload_ids[native_field] = configured_ids
    forbidden_executable_spells = {
        int(value)
        for value in condition_policy.get("forbidden_executable_cast_spell_ids")
        or []
    }
    _require(
        forbidden_executable_spells <= forbidden_spell_ids,
        "apl_transform:condition_executable_spells",
    )
    unsupported_target_references = condition_policy.get(
        "unsupported_target_references"
    ) or []
    _require(
        unsupported_target_references
        == [
            {
                "type": "Target",
                "index": 1,
                "replacement": False,
                "row_policy": "remove_after_false_fold",
            }
        ],
        "apl_transform:unsupported_target_references",
    )
    _require(
        condition_policy.get("preserved_target_references")
        == [{"type": "Pet", "owner": "Self", "index": 1}],
        "apl_transform:preserved_target_references",
    )
    numeric_rewrite_rows = condition_policy.get("single_target_numeric_rewrites") or []
    _require(
        numeric_rewrite_rows
        == [
            {
                "native_action_field": "multidot",
                "field": "max_dots",
                "source_value": 2,
                "replacement": 1,
            }
        ],
        "apl_transform:single_target_numeric_rewrites",
    )
    predicate_rewrite_rows = condition_policy.get(
        "single_target_predicate_rewrites"
    ) or []
    _require(
        predicate_rewrite_rows
        == [
            {
                "native_value_field": "number_targets",
                "operator": "OpEq",
                "constant": 2,
                "observed_target_count": 1,
                "replacement": False,
                "reason": "fixture_has_exactly_one_hostile_target",
            }
        ],
        "apl_transform:single_target_predicate_rewrites",
    )
    removed: list[dict[str, Any]] = []
    condition_rewrites: list[dict[str, Any]] = []
    removed_false_rows: list[dict[str, Any]] = []
    numeric_rewrites: list[dict[str, Any]] = []

    def state_mutation_identity(
        action: Mapping[str, Any], variant: str
    ) -> dict[str, Any]:
        payload = action.get(variant)
        _require(isinstance(payload, Mapping), "apl_transform:state_mutation_payload")
        aura_id = payload.get("aura_id")
        _require(isinstance(aura_id, Mapping), "apl_transform:state_mutation_aura")
        identity: dict[str, Any] = {
            "native_field": variant,
            "spell_id": int(aura_id.get("spell_id") or 0),
        }
        _require(identity["spell_id"] > 0, "apl_transform:state_mutation_spell")
        tag = int(aura_id.get("tag") or 0)
        if tag:
            identity["tag"] = tag
        if variant == "activate_aura_with_stacks":
            stacks = int(payload.get("num_stacks") or 0)
            _require(stacks > 0, "apl_transform:state_mutation_stacks")
            identity["stacks"] = stacks
        return identity

    def action_variant(value: Mapping[str, Any], *, require_action: bool) -> str | None:
        present = sorted(set(value) & action_variants)
        unknown = set(value) - action_variants - {"condition"}
        if require_action or present:
            _require(not unknown, "apl_transform:unknown_action_field")
            _require(len(present) == 1, "apl_transform:action_oneof")
            return present[0]
        return None

    def record_condition_rewrite(
        *,
        path: tuple[str, ...],
        before: Any,
        after: Any,
        reason: str,
        identity: Mapping[str, Any] | None = None,
    ) -> None:
        row: dict[str, Any] = {
            "path": ".".join(path),
            "reason": reason,
            "before": before,
            "after": after,
            "before_sha256": canonical_sha256(before),
            "after_sha256": canonical_sha256(after),
        }
        if identity is not None:
            row["identity"] = dict(identity)
        condition_rewrites.append(row)

    def unavailable_payload_identity(
        native_field: str, payload: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        configured = unavailable_conditions.get(native_field) or {}
        matched = configured.get(canonical_json_bytes(payload))
        if matched is not None:
            return {
                "native_field": native_field,
                "payload": copy.deepcopy(dict(payload)),
                "replacement": matched["replacement"],
                "replacement_type": matched["replacement_type"],
            }
        if payload_ids(payload) & unavailable_payload_ids.get(native_field, set()):
            raise WowsimsGenerationError(
                f"apl_transform:unlisted_condition_payload:{native_field}"
            )
        return None

    def unavailable_leaf_identity(condition: Mapping[str, Any]) -> dict[str, Any] | None:
        for native_field, configured_payloads in unavailable_conditions.items():
            if not all(
                configured["replacement_type"] == "boolean"
                for configured in configured_payloads.values()
            ):
                continue
            payloads: list[Mapping[str, Any]] = []

            def collect_payloads(value: Any) -> None:
                if isinstance(value, Mapping):
                    payload = value.get(native_field)
                    if isinstance(payload, Mapping):
                        payloads.append(payload)
                    for child in value.values():
                        collect_payloads(child)
                elif isinstance(value, list):
                    for child in value:
                        collect_payloads(child)

            collect_payloads(condition)
            if not payloads:
                continue
            for payload in payloads:
                identity = unavailable_payload_identity(native_field, payload)
                if identity is not None:
                    return identity
        return None

    def rewrite_numeric_expressions(value: Any, *, path: tuple[str, ...]) -> Any:
        if isinstance(value, list):
            return [
                rewrite_numeric_expressions(child, path=path + (str(index),))
                for index, child in enumerate(value)
            ]
        if not isinstance(value, Mapping):
            return value
        for native_field in ("aura_remaining_time", "spell_time_to_ready"):
            payload = value.get(native_field)
            if not isinstance(payload, Mapping):
                continue
            identity = unavailable_payload_identity(native_field, payload)
            if identity is None:
                continue
            _require(
                identity.get("replacement_type") == "number"
                and identity.get("replacement") == 0
                and len(value) == 1,
                "apl_transform:numeric_condition_replacement",
            )
            replacement = {"const": {"val": "0s"}}
            record_condition_rewrite(
                path=path,
                before=dict(value),
                after=replacement,
                reason="fixture_absent_numeric_condition_leaf",
                identity=identity,
            )
            return replacement
        return {
            str(key): rewrite_numeric_expressions(
                child, path=path + (str(key),)
            )
            for key, child in value.items()
        }

    def static_number(value: Any) -> float | None:
        if not isinstance(value, Mapping):
            return None
        constant = value.get("const")
        if isinstance(constant, Mapping):
            raw = str(constant.get("val") or "")
            match = re.fullmatch(r"(-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))(?:s)?", raw)
            return float(match.group(1)) if match else None
        math_value = value.get("math")
        if not isinstance(math_value, Mapping):
            return None
        lhs = static_number(math_value.get("lhs"))
        rhs = static_number(math_value.get("rhs"))
        if lhs is None or rhs is None:
            return None
        operation = str(math_value.get("op") or "")
        if operation == "OpAdd":
            return lhs + rhs
        if operation == "OpSub":
            return lhs - rhs
        if operation == "OpMul":
            return lhs * rhs
        if operation == "OpDiv" and rhs != 0:
            return lhs / rhs
        return None

    def fold_static_comparison(value: Mapping[str, Any]) -> bool | None:
        comparison = value.get("cmp")
        if not isinstance(comparison, Mapping):
            return None
        lhs = static_number(comparison.get("lhs"))
        rhs = static_number(comparison.get("rhs"))
        if lhs is None or rhs is None:
            return None
        operation = str(comparison.get("op") or "")
        comparisons = {
            "OpEq": lhs == rhs,
            "OpNe": lhs != rhs,
            "OpLt": lhs < rhs,
            "OpLe": lhs <= rhs,
            "OpGt": lhs > rhs,
            "OpGe": lhs >= rhs,
        }
        return comparisons.get(operation)

    def contains_unsupported_target(value: Any) -> bool:
        if isinstance(value, Mapping):
            if value.get("type") == "Target" and int(value.get("index") or 0) >= 1:
                return True
            return any(contains_unsupported_target(child) for child in value.values())
        if isinstance(value, list):
            return any(contains_unsupported_target(child) for child in value)
        return False

    def rewrite_condition(value: Any, *, path: tuple[str, ...]) -> Any:
        _require(isinstance(value, Mapping), "apl_transform:condition_shape")
        present_variants = set(value) & condition_variants
        unknown_fields = set(value) - condition_variants - {"uuid"}
        _require(
            not unknown_fields and len(present_variants) == 1,
            "apl_transform:condition_oneof",
        )
        before = copy.deepcopy(dict(value))
        if "and" in value:
            payload = value.get("and")
            _require(isinstance(payload, Mapping), "apl_transform:condition_and")
            vals = payload.get("vals") or []
            _require(isinstance(vals, list), "apl_transform:condition_and_vals")
            rewritten = [
                rewrite_condition(child, path=path + ("and", "vals", str(index)))
                for index, child in enumerate(vals)
            ]
            if any(child is False for child in rewritten):
                after: Any = False
            else:
                survivors = [child for child in rewritten if child is not True]
                if not survivors:
                    after = True
                elif len(survivors) == 1:
                    after = survivors[0]
                else:
                    after = {"and": {**dict(payload), "vals": survivors}}
            if after != before:
                record_condition_rewrite(
                    path=path,
                    before=before,
                    after=after,
                    reason="constant_fold_and",
                )
            return after
        if "or" in value:
            payload = value.get("or")
            _require(isinstance(payload, Mapping), "apl_transform:condition_or")
            vals = payload.get("vals") or []
            _require(isinstance(vals, list), "apl_transform:condition_or_vals")
            rewritten = [
                rewrite_condition(child, path=path + ("or", "vals", str(index)))
                for index, child in enumerate(vals)
            ]
            if any(child is True for child in rewritten):
                after = True
            else:
                survivors = [child for child in rewritten if child is not False]
                if not survivors:
                    after = False
                elif len(survivors) == 1:
                    after = survivors[0]
                else:
                    after = {"or": {**dict(payload), "vals": survivors}}
            if after != before:
                record_condition_rewrite(
                    path=path,
                    before=before,
                    after=after,
                    reason="constant_fold_or",
                )
            return after
        if "not" in value:
            payload = value.get("not")
            _require(isinstance(payload, Mapping), "apl_transform:condition_not")
            rewritten = rewrite_condition(
                payload.get("val"), path=path + ("not", "val")
            )
            if rewritten is True:
                after = False
            elif rewritten is False:
                after = True
            else:
                after = {"not": {**dict(payload), "val": rewritten}}
            if after != before:
                record_condition_rewrite(
                    path=path,
                    before=before,
                    after=after,
                    reason="constant_fold_not",
                )
            return after
        comparison = value.get("cmp")
        if isinstance(comparison, Mapping):
            numeric_rewritten = rewrite_numeric_expressions(before, path=path)
            _require(
                isinstance(numeric_rewritten, Mapping),
                "apl_transform:numeric_condition_shape",
            )
            if numeric_rewritten != before:
                folded = fold_static_comparison(numeric_rewritten)
                if folded is not None:
                    record_condition_rewrite(
                        path=path,
                        before=numeric_rewritten,
                        after=folded,
                        reason="constant_fold_comparison",
                    )
                    return folded
                before = copy.deepcopy(dict(numeric_rewritten))
                value = numeric_rewritten
                comparison = value.get("cmp")
                _require(
                    isinstance(comparison, Mapping),
                    "apl_transform:numeric_comparison_shape",
                )
            lhs = comparison.get("lhs") or {}
            rhs = comparison.get("rhs") or {}
            constant = (rhs.get("const") or {}).get("val") if isinstance(rhs, Mapping) else None
            if (
                comparison.get("op") == "OpEq"
                and isinstance(lhs, Mapping)
                and lhs.get("number_targets") == {}
                and str(constant) == "2"
            ):
                identity = {
                    "native_value_field": "number_targets",
                    "operator": "OpEq",
                    "constant": 2,
                    "observed_target_count": 1,
                }
                record_condition_rewrite(
                    path=path,
                    before=before,
                    after=False,
                    reason="fixture_has_exactly_one_hostile_target",
                    identity=identity,
                )
                return False
        identity = unavailable_leaf_identity(value)
        if identity is not None:
            record_condition_rewrite(
                path=path,
                before=before,
                after=False,
                reason="fixture_absent_condition_leaf",
                identity=identity,
            )
            return False
        if contains_unsupported_target(value):
            record_condition_rewrite(
                path=path,
                before=before,
                after=False,
                reason="single_target_reference_unavailable",
                identity={"type": "Target", "minimum_unavailable_index": 1},
            )
            return False
        return before

    def rewrite_action_conditions(value: Any, *, path: tuple[str, ...] = ()) -> Any:
        if isinstance(value, list):
            output = []
            for index, child in enumerate(value):
                rewritten = rewrite_action_conditions(child, path=path + (str(index),))
                if rewritten is not _REMOVE_APL_NODE:
                    output.append(rewritten)
            return output
        if not isinstance(value, Mapping):
            return value
        output = copy.deepcopy(dict(value))
        candidate = output.get("action")
        action_wrapped = isinstance(candidate, Mapping)
        action = candidate if action_wrapped else output
        present = sorted(set(action) & action_variants)
        if present:
            _require(len(present) == 1, "apl_transform:condition_action_oneof")
            condition = action.get("condition")
            if condition is not None:
                rewritten_condition = rewrite_condition(
                    condition,
                    path=path + (("action",) if action_wrapped else ()) + ("condition",),
                )
                if rewritten_condition is False:
                    removed_false_rows.append(
                        {
                            "path": ".".join(path),
                            "action_sha256": canonical_sha256(action),
                            "reason": "condition_folded_false",
                        }
                    )
                    return _REMOVE_APL_NODE
                if rewritten_condition is True:
                    action.pop("condition", None)
                else:
                    action["condition"] = rewritten_condition
            if present[0] == "multidot":
                multidot = action.get("multidot")
                _require(isinstance(multidot, Mapping), "apl_transform:multidot")
                if int(multidot.get("max_dots") or 0) == 2:
                    before_multidot = copy.deepcopy(dict(multidot))
                    rewritten_multidot = {**dict(multidot), "max_dots": 1}
                    action["multidot"] = rewritten_multidot
                    numeric_rewrites.append(
                        {
                            "path": ".".join(
                                path
                                + (("action",) if action_wrapped else ())
                                + ("multidot", "max_dots")
                            ),
                            "source_value": 2,
                            "replacement": 1,
                            "before_sha256": canonical_sha256(before_multidot),
                            "after_sha256": canonical_sha256(rewritten_multidot),
                            "reason": "single_target_multidot_clamp",
                        }
                    )
            if contains_unsupported_target(action):
                raise WowsimsGenerationError(
                    "apl_transform:surviving_unsupported_target_reference:"
                    + ".".join(path)
                )
            for key, child in list(action.items()):
                if key == "condition":
                    continue
                rewritten_child = rewrite_action_conditions(
                    child,
                    path=path
                    + (("action",) if action_wrapped else ())
                    + (str(key),),
                )
                if rewritten_child is _REMOVE_APL_NODE:
                    action.pop(key, None)
                else:
                    action[key] = rewritten_child
            if action_wrapped:
                output["action"] = action
                return output
            return action
        for key, child in list(output.items()):
            rewritten_child = rewrite_action_conditions(
                child, path=path + (str(key),)
            )
            if rewritten_child is _REMOVE_APL_NODE:
                output.pop(key, None)
            else:
                output[key] = rewritten_child
        return output

    def forbidden_identity(
        value: Any, *, require_action: bool = False
    ) -> dict[str, Any] | None:
        if not isinstance(value, Mapping):
            return None
        action = value.get("action") if isinstance(value.get("action"), Mapping) else value
        variant = action_variant(action, require_action=require_action or action is not value)
        if variant in FORBIDDEN_STATE_MUTATION_APL_OPERATIONS:
            identity = state_mutation_identity(action, variant)
            _require(
                canonical_json_bytes(identity) in declared_state_mutations,
                "apl_transform:unlisted_state_mutation",
            )
            return identity
        if variant in forbidden_generic_operations:
            return {"native_action_field": variant}
        if variant != "cast_spell":
            return None
        cast = action.get("cast_spell") if isinstance(action, Mapping) else None
        spell = cast.get("spell_id") if isinstance(cast, Mapping) else None
        _require(isinstance(spell, Mapping), "apl_transform:cast_spell_identity")
        other_id = str(spell.get("other_id") or "")
        if other_id in forbidden_kinds:
            return {"other_action_id": other_id}
        spell_id = int(spell.get("spell_id") or 0)
        if spell_id in forbidden_spell_ids:
            return {"spell_id": spell_id}
        item_id = int(spell.get("item_id") or 0)
        if item_id:
            if item_id in forbidden_item_ids:
                return {"item_id": item_id}
            _require(item_id in allowed_item_ids, f"apl_transform:unlisted_item_id:{item_id}")
        return None

    def visit(
        value: Any,
        *,
        require_action: bool = False,
        sequence_payload: bool = False,
    ) -> Any:
        identity = forbidden_identity(value, require_action=require_action)
        if identity is not None:
            removed.append(identity)
            return _REMOVE_APL_NODE
        if isinstance(value, list):
            output = []
            for item in value:
                transformed = visit(item, require_action=require_action)
                if transformed is not _REMOVE_APL_NODE:
                    output.append(transformed)
            return output
        if not isinstance(value, Mapping):
            return value
        candidate_action = (
            value.get("action") if isinstance(value.get("action"), Mapping) else value
        )
        current_variant = action_variant(
            candidate_action,
            require_action=require_action or candidate_action is not value,
        )
        output: dict[str, Any] = {}
        for key, item in value.items():
            child_requires_action = key == "action" or (
                sequence_payload and key == "actions"
            )
            child_sequence_payload = (
                current_variant in {"sequence", "strict_sequence"}
                and key == current_variant
            )
            transformed = visit(
                item,
                require_action=child_requires_action,
                sequence_payload=child_sequence_payload,
            )
            if transformed is _REMOVE_APL_NODE:
                if key == "action":
                    return _REMOVE_APL_NODE
                continue
            output[str(key)] = transformed
        for sequence_key in ("sequence", "strict_sequence"):
            sequence = output.get(sequence_key)
            if isinstance(sequence, Mapping) and sequence.get("actions") == []:
                return _REMOVE_APL_NODE
        return output

    source_prepull = rotation.get("prepull_actions") or []
    _require(isinstance(source_prepull, list), "apl_transform:source_prepull")
    removed_source_prepull: list[dict[str, Any]] = []
    for index, raw_row in enumerate(source_prepull):
        _require(isinstance(raw_row, Mapping), "apl_transform:source_prepull_row")
        action = raw_row.get("action")
        _require(isinstance(action, Mapping), "apl_transform:source_prepull_action")
        variant = action_variant(action, require_action=True)
        removed_source_prepull.append(
            {
                "source_index": index,
                "native_action_field": variant,
                "row_sha256": canonical_sha256(raw_row),
                "action_sha256": canonical_sha256(action),
                "reason": prepull_policy["replacement_reason"],
            }
        )
    combat_rotation = copy.deepcopy(dict(rotation))
    combat_rotation.pop("prepull_actions", None)
    rewritten_combat_rotation = rewrite_action_conditions(combat_rotation)
    _require(
        isinstance(rewritten_combat_rotation, Mapping),
        "apl_transform:condition_rewritten_rotation",
    )
    transformed = visit(rewritten_combat_rotation)
    _require(isinstance(transformed, dict), "apl_transform:removed_rotation")
    replacement_prepull: list[dict[str, Any]] = []
    for raw_row in prepull_actions:
        _require(isinstance(raw_row, Mapping), "apl_transform:required_prepull_row")
        row = copy.deepcopy(dict(raw_row))
        _require(
            forbidden_identity(row, require_action=True) is None,
            "apl_transform:forbidden_required_prepull",
        )
        replacement_prepull.append(row)
    transformed["prepull_actions"] = replacement_prepull

    def find_forbidden(value: Any) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        identity = forbidden_identity(value)
        if identity is not None:
            matches.append(identity)
        if isinstance(value, Mapping):
            for item in value.values():
                matches.extend(find_forbidden(item))
        elif isinstance(value, list):
            for item in value:
                matches.extend(find_forbidden(item))
        return matches

    _require(not find_forbidden(transformed), "apl_transform:forbidden_action_survived")
    observation = {
        "policy_sha256": canonical_sha256(policy),
        "apl_action_variants_sha256": canonical_sha256(sorted(action_variants)),
        "equipped_item_ids_sha256": canonical_sha256(sorted(equipped_item_ids)),
        "input_rotation_sha256": canonical_sha256(rotation),
        "output_rotation_sha256": canonical_sha256(transformed),
        "removed_action_count": len(removed) + len(removed_source_prepull),
        "removed_actions": sorted(
            removed, key=lambda value: canonical_json_bytes(value)
        ),
        "removed_combat_action_count": len(removed),
        "condition_rewrite_policy_sha256": canonical_sha256(condition_policy),
        "condition_rewrite_count": len(condition_rewrites),
        "condition_rewrites": condition_rewrites,
        "condition_rewrites_sha256": canonical_sha256(condition_rewrites),
        "removed_false_row_count": len(removed_false_rows),
        "removed_false_rows": removed_false_rows,
        "removed_false_rows_sha256": canonical_sha256(removed_false_rows),
        "numeric_rewrite_count": len(numeric_rewrites),
        "numeric_rewrites": numeric_rewrites,
        "numeric_rewrites_sha256": canonical_sha256(numeric_rewrites),
        "removed_source_prepull_action_count": len(removed_source_prepull),
        "removed_source_prepull_actions": removed_source_prepull,
        "source_prepull_sha256": canonical_sha256(source_prepull),
        "replacement_prepull_action_count": len(replacement_prepull),
        "replacement_prepull_actions": replacement_prepull,
        "replacement_prepull_sha256": canonical_sha256(replacement_prepull),
        "prepull_replacement_reason": prepull_policy["replacement_reason"],
    }
    return transformed, observation


def _direct_cast_item_ids(value: Any) -> set[int]:
    observed: set[int] = set()
    if isinstance(value, Mapping):
        cast = value.get("cast_spell")
        spell_id = cast.get("spell_id") if isinstance(cast, Mapping) else None
        if isinstance(spell_id, Mapping):
            item_id = int(spell_id.get("item_id") or 0)
            if item_id > 0:
                observed.add(item_id)
        for child in value.values():
            observed.update(_direct_cast_item_ids(child))
    elif isinstance(value, list):
        for child in value:
            observed.update(_direct_cast_item_ids(child))
    return observed


def _state_mutation_instances(value: Any) -> set[bytes]:
    observed: set[bytes] = set()
    if isinstance(value, Mapping):
        for variant in FORBIDDEN_STATE_MUTATION_APL_OPERATIONS & set(value):
            payload = value.get(variant)
            _require(isinstance(payload, Mapping), "apl_items:state_mutation_payload")
            aura_id = payload.get("aura_id")
            _require(isinstance(aura_id, Mapping), "apl_items:state_mutation_aura")
            identity: dict[str, Any] = {
                "native_field": variant,
                "spell_id": int(aura_id.get("spell_id") or 0),
            }
            tag = int(aura_id.get("tag") or 0)
            if tag:
                identity["tag"] = tag
            if variant == "activate_aura_with_stacks":
                identity["stacks"] = int(payload.get("num_stacks") or 0)
            observed.add(canonical_json_bytes(identity))
        for child in value.values():
            observed.update(_state_mutation_instances(child))
    elif isinstance(value, list):
        for child in value:
            observed.update(_state_mutation_instances(child))
    return observed


def _condition_payload_instances(
    value: Any, *, native_fields: set[str]
) -> set[bytes]:
    observed: set[bytes] = set()
    if isinstance(value, Mapping):
        for native_field in native_fields & set(value):
            payload = value.get(native_field)
            _require(
                isinstance(payload, Mapping) and bool(payload),
                "apl_conditions:payload",
            )
            observed.add(
                canonical_json_bytes(
                    {
                        "native_field": native_field,
                        "payload": copy.deepcopy(dict(payload)),
                    }
                )
            )
        for child in value.values():
            observed.update(
                _condition_payload_instances(child, native_fields=native_fields)
            )
    elif isinstance(value, list):
        for child in value:
            observed.update(
                _condition_payload_instances(child, native_fields=native_fields)
            )
    return observed


def validate_catalog_apl_item_policy(
    manifest: Mapping[str, Any],
    *,
    checkout: Path,
    fixture_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Close the selected pinned APL set over every direct item cast identity."""
    revision = str((fixture_contract.get("authority") or {}).get("revision") or "")
    clean_checkout_identity(checkout, revision)
    observed: set[int] = set()
    declared: set[int] | None = None
    observed_state_mutations: set[bytes] = set()
    declared_state_mutations: set[bytes] | None = None
    observed_declared_condition_payloads: set[bytes] = set()
    declared_condition_payloads: set[bytes] | None = None
    per_spec: dict[str, list[int]] = {}
    rows = manifest.get("requests") or []
    _require(isinstance(rows, list) and len(rows) == 16, "apl_items:request_count")
    for row in rows:
        _require(isinstance(row, Mapping), "apl_items:request_row")
        target_spec = str(row.get("target_spec") or "")
        request = row.get("request") or {}
        rotation = request.get("rotation") or {}
        relative = str(rotation.get("path") or "")
        payload = _checked_source_bytes(
            checkout,
            relative,
            expected_revision=revision,
            label=f"apl_items:{target_spec}",
        )
        _require(
            hashlib.sha256(payload).hexdigest() == rotation.get("sha256"),
            f"apl_items:{target_spec}:hash",
        )
        source_rotation = _snake_case_json(
            _json_object_from_bytes(payload, label=f"apl_items:{target_spec}")
        )
        item_ids = _direct_cast_item_ids(source_rotation)
        state_mutations = _state_mutation_instances(source_rotation)
        per_spec[target_spec] = sorted(item_ids)
        observed.update(item_ids)
        observed_state_mutations.update(state_mutations)
        native = (
            ((fixture_contract.get("specs") or {}).get(target_spec) or {}).get(
                "native_request"
            )
            or {}
        )
        policy = native.get("apl_transform_policy") or {}
        row_declared = {
            int(value) for value in policy.get("forbidden_cast_item_ids") or []
        } | {int(value) for value in policy.get("allowed_cast_item_ids") or []}
        if declared is None:
            declared = row_declared
        _require(
            row_declared == declared,
            f"apl_items:{target_spec}:policy_cohort",
        )
        row_state_mutations = {
            canonical_json_bytes(dict(value))
            for value in policy.get("forbidden_state_mutation_instances") or []
        }
        if declared_state_mutations is None:
            declared_state_mutations = row_state_mutations
        _require(
            row_state_mutations == declared_state_mutations,
            f"apl_items:{target_spec}:state_mutation_policy_cohort",
        )
        condition_policy = policy.get("condition_rewrite_policy") or {}
        row_condition_payloads = {
            canonical_json_bytes(
                {
                    "native_field": str(condition_row.get("native_field") or ""),
                    "payload": copy.deepcopy(dict(payload)),
                }
            )
            for condition_row in condition_policy.get(
                "unavailable_condition_leaves"
            )
            or []
            if isinstance(condition_row, Mapping)
            for payload in condition_row.get("payloads") or []
            if isinstance(payload, Mapping)
        }
        _require(bool(row_condition_payloads), f"apl_items:{target_spec}:conditions")
        if declared_condition_payloads is None:
            declared_condition_payloads = row_condition_payloads
        _require(
            row_condition_payloads == declared_condition_payloads,
            f"apl_items:{target_spec}:condition_policy_cohort",
        )
        source_condition_payloads = _condition_payload_instances(
            source_rotation,
            native_fields={
                str(value.get("native_field") or "")
                for value in condition_policy.get("unavailable_condition_leaves") or []
                if isinstance(value, Mapping)
            },
        )
        observed_declared_condition_payloads.update(
            source_condition_payloads & row_condition_payloads
        )
    _require(observed == (declared or set()), "apl_items:selected_union_mismatch")
    _require(
        observed_state_mutations == (declared_state_mutations or set()),
        "apl_items:selected_state_mutation_union_mismatch",
    )
    _require(
        observed_declared_condition_payloads
        == (declared_condition_payloads or set()),
        "apl_items:selected_condition_payload_union_mismatch",
    )
    state_rows = [json.loads(value) for value in sorted(observed_state_mutations)]
    observation = {
        "source_revision": revision,
        "selected_direct_cast_item_ids": sorted(observed),
        "selected_direct_cast_item_ids_sha256": canonical_sha256(sorted(observed)),
        "per_spec": per_spec,
        "per_spec_sha256": canonical_sha256(per_spec),
        "selected_state_mutation_instances": state_rows,
        "selected_state_mutation_instances_sha256": canonical_sha256(state_rows),
        "selected_condition_payloads": [
            json.loads(value)
            for value in sorted(observed_declared_condition_payloads)
        ],
        "selected_condition_payloads_sha256": canonical_sha256(
            [
                json.loads(value)
                for value in sorted(observed_declared_condition_payloads)
            ]
        ),
    }
    return {**observation, "observation_sha256": canonical_sha256(observation)}


def _tool_version(binary: Path, arguments: Sequence[str]) -> str:
    completed = subprocess.run(
        [str(binary), *arguments], check=True, capture_output=True, text=True
    )
    return (completed.stdout or completed.stderr).strip()


def build_pinned_cli(
    *,
    checkout: Path,
    fixture_contract_path: Path,
    go_binary: Path,
    protoc_binary: Path,
    protoc_gen_go_binary: Path,
    output_root: Path,
    timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    fixture, fixture_sha256 = load_fixture_contract(fixture_contract_path)
    revision = str(fixture["authority"]["revision"])
    source = clean_checkout_identity(checkout, revision)
    tools = {
        "go": {
            "executable_name": go_binary.name,
            "sha256": sha256_file(go_binary),
            "version": _tool_version(go_binary, ["version"]),
        },
        "protoc": {
            "executable_name": protoc_binary.name,
            "sha256": sha256_file(protoc_binary),
            "version": _tool_version(protoc_binary, ["--version"]),
        },
        "protoc_gen_go": {
            "executable_name": protoc_gen_go_binary.name,
            "sha256": sha256_file(protoc_gen_go_binary),
            "version": _tool_version(protoc_gen_go_binary, ["--version"]),
        },
    }
    _require(tools["go"]["version"].startswith("go version go1.23."), "unsupported_go_version")

    env = dict(os.environ)
    env["GOTOOLCHAIN"] = "local"
    env["PATH"] = os.pathsep.join(
        [
            go_binary.resolve().parent.as_posix(),
            protoc_binary.resolve().parent.as_posix(),
            protoc_gen_go_binary.resolve().parent.as_posix(),
            env.get("PATH", ""),
        ]
    )
    proto_files = [path.relative_to(checkout).as_posix() for path in sorted((checkout / "proto").glob("*.proto"))]
    _require(bool(proto_files), "wowsims_proto_sources_missing")
    protoc_command = [
        str(protoc_binary.resolve()),
        "-I=./proto",
        "--go_out=./sim/core",
        *proto_files,
    ]
    proto_outcome, proto_output = _run_capture(
        protoc_command, cwd=checkout, env=env, timeout_seconds=timeout_seconds
    )
    _require_normal_child(proto_outcome, label="protoc")

    build_outcomes: list[dict[str, Any]] = []
    validator_build_outcomes: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="wowsims-clean-build-") as temporary:
        temporary_root = Path(temporary)
        built_paths = [temporary_root / "wowsimcli.first", temporary_root / "wowsimcli.second"]
        for built_path in built_paths:
            command = [
                str(go_binary.resolve()),
                "build",
                "-trimpath",
                "--tags=with_db",
                f"-ldflags=-X main.Version={revision} -s -w",
                "-o",
                str(built_path),
                "./cmd/wowsimcli/cli_main.go",
            ]
            outcome, output = _run_capture(
                command, cwd=checkout, env=env, timeout_seconds=timeout_seconds
            )
            _require_normal_child(outcome, label="go_build")
            build_outcomes.append(
                {
                    **outcome,
                    "process_log": store_content_addressed_bytes(
                        output_root, "process_logs", output, suffix=".log"
                    ),
                }
            )
        first_bytes = built_paths[0].read_bytes()
        second_bytes = built_paths[1].read_bytes()
        _require(first_bytes == second_bytes, "wowsims_cli_rebuild_not_reproducible")
        binary_artifact = store_content_addressed_bytes(
            output_root,
            "binaries",
            first_bytes,
            suffix=".wowsimcli",
            executable=True,
        )
        validator_source = temporary_root / "wowsimrequestvalidate.go"
        _write_exact(validator_source, REQUEST_VALIDATOR_SOURCE)
        validator_paths = [
            temporary_root / "wowsimrequestvalidate.first",
            temporary_root / "wowsimrequestvalidate.second",
        ]
        for validator_path in validator_paths:
            command = [
                str(go_binary.resolve()),
                "build",
                "-trimpath",
                "--tags=with_db",
                "-ldflags=-s -w",
                "-o",
                str(validator_path),
                str(validator_source),
            ]
            outcome, output = _run_capture(
                command, cwd=checkout, env=env, timeout_seconds=timeout_seconds
            )
            _require_normal_child(outcome, label="go_build_request_validator")
            validator_build_outcomes.append(
                {
                    **outcome,
                    "process_log": store_content_addressed_bytes(
                        output_root, "process_logs", output, suffix=".log"
                    ),
                }
            )
        validator_first_bytes = validator_paths[0].read_bytes()
        _require(
            validator_first_bytes == validator_paths[1].read_bytes(),
            "wowsims_request_validator_rebuild_not_reproducible",
        )
        request_validator_artifact = store_content_addressed_bytes(
            output_root,
            "binaries",
            validator_first_bytes,
            suffix=".wowsimrequestvalidate",
            executable=True,
        )

    final_source = clean_checkout_identity(checkout, revision)
    _require(final_source == source, "wowsims_source_changed_during_build")
    binary_path = output_root.resolve() / str(binary_artifact["path"])
    version_outcome, version_output = _run_capture(
        [str(binary_path), "version"],
        cwd=checkout,
        env=env,
        timeout_seconds=60.0,
    )
    _require_normal_child(version_outcome, label="wowsimcli_version")
    _require(version_output.decode("utf-8").strip() == revision, "wowsimcli_version_mismatch")

    identity: dict[str, Any] = {
        "schema": BUILD_RECEIPT_SCHEMA,
        "provider_revision": revision,
        "binary_sha256": binary_artifact["sha256"],
        "source": source,
        "fixture_contract": {
            **store_content_addressed_bytes(
                output_root,
                "fixture_contracts",
                fixture_contract_path.read_bytes(),
                suffix=".json",
            ),
            "canonical_sha256": fixture_sha256,
        },
        "tools": tools,
        "protobuf_generation": {
            **proto_outcome,
            "process_log": store_content_addressed_bytes(
                output_root, "process_logs", proto_output, suffix=".log"
            ),
        },
        "protobuf_generation_output": {
            "sha256": hashlib.sha256(proto_output).hexdigest(),
            "byte_count": len(proto_output),
        },
        "builds": build_outcomes,
        "binary": binary_artifact,
        "request_validator": {
            **request_validator_artifact,
            "source_sha256": hashlib.sha256(REQUEST_VALIDATOR_SOURCE).hexdigest(),
            "builds": validator_build_outcomes,
        },
        "byte_identical_clean_rebuild": True,
        "version_probe": {
            **version_outcome,
            "process_log": store_content_addressed_bytes(
                output_root, "process_logs", version_output, suffix=".log"
            ),
        },
    }
    receipt = {**identity, "receipt_sha256": canonical_sha256(identity)}
    receipt_artifact = store_content_addressed_json(output_root, "build_receipts", receipt)
    return {**receipt, "artifact": receipt_artifact}


def validate_build_receipt(
    receipt_path: Path,
    *,
    expected_revision: str,
) -> tuple[dict[str, Any], Path]:
    receipt = _read_json_object(receipt_path, label="build_receipt")
    _require(receipt.get("schema") == BUILD_RECEIPT_SCHEMA, "build_receipt:schema")
    stored_hash = str(receipt.get("receipt_sha256") or "")
    identity = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    _require(stored_hash == canonical_sha256(identity), "build_receipt:self_hash")
    source = receipt.get("source") or {}
    _require(
        source.get("revision") == expected_revision
        and receipt.get("provider_revision") == expected_revision,
        "build_receipt:revision",
    )
    _require(source.get("source_tree_clean") is True, "build_receipt:dirty")
    _require(receipt.get("byte_identical_clean_rebuild") is True, "build_receipt:rebuild")
    artifact_root = receipt_path.resolve().parent.parent
    protobuf_generation = receipt.get("protobuf_generation") or {}
    protobuf_log_path = verify_process_evidence(
        protobuf_generation,
        protobuf_generation.get("process_log") or {},
        artifact_root=artifact_root,
        label="build_receipt:protobuf",
    )
    protobuf_output = receipt.get("protobuf_generation_output") or {}
    _require(
        protobuf_output.get("sha256") == sha256_file(protobuf_log_path)
        and int(protobuf_output.get("byte_count", -1))
        == protobuf_log_path.stat().st_size,
        "build_receipt:protobuf_output_identity",
    )
    builds = receipt.get("builds") or []
    _require(isinstance(builds, list) and len(builds) == 2, "build_receipt:build_count")
    for index, outcome in enumerate(builds):
        verify_process_evidence(
            outcome,
            outcome.get("process_log") or {},
            artifact_root=artifact_root,
            label=f"build_receipt:build:{index}",
        )
    version_probe = receipt.get("version_probe") or {}
    verify_process_evidence(
        version_probe,
        version_probe.get("process_log") or {},
        artifact_root=artifact_root,
        label="build_receipt:version_probe",
    )
    tools = receipt.get("tools") or {}
    _require(set(tools) == {"go", "protoc", "protoc_gen_go"}, "build_receipt:tools")
    for name, tool in tools.items():
        _require(
            isinstance(tool, Mapping)
            and bool(re.fullmatch(r"[0-9a-f]{64}", str(tool.get("sha256") or "")))
            and bool(str(tool.get("version") or "")),
            f"build_receipt:tool:{name}",
        )
    binary_record = receipt.get("binary") or {}
    fixture_path = verify_artifact(
        receipt.get("fixture_contract") or {},
        artifact_root=artifact_root,
        label="build_fixture_contract",
    )
    _, fixture_sha256 = load_fixture_contract(fixture_path)
    _require(
        fixture_sha256
        == (receipt.get("fixture_contract") or {}).get("canonical_sha256"),
        "build_fixture_contract:canonical_hash",
    )
    binary_path = verify_artifact(
        binary_record, artifact_root=artifact_root, label="build_binary"
    )
    request_validator = receipt.get("request_validator") or {}
    _require(
        request_validator.get("source_sha256")
        == hashlib.sha256(REQUEST_VALIDATOR_SOURCE).hexdigest(),
        "build_request_validator:source",
    )
    verify_artifact(
        request_validator,
        artifact_root=artifact_root,
        label="build_request_validator",
    )
    validator_builds = request_validator.get("builds") or []
    _require(
        isinstance(validator_builds, list) and len(validator_builds) == 2,
        "build_request_validator:build_count",
    )
    for index, outcome in enumerate(validator_builds):
        verify_process_evidence(
            outcome,
            outcome.get("process_log") or {},
            artifact_root=artifact_root,
            label=f"build_request_validator:build:{index}",
        )
    _require(
        receipt.get("binary_sha256") == sha256_file(binary_path),
        "build_receipt:binary_identity",
    )
    return receipt, binary_path


def _request_player(native_request: Mapping[str, Any]) -> Mapping[str, Any]:
    raid = native_request.get("raid") or {}
    parties = raid.get("parties") or []
    _require(isinstance(parties, list) and len(parties) == 1, "native_request:party_count")
    players = (parties[0] or {}).get("players") or []
    _require(isinstance(players, list) and len(players) == 1, "native_request:player_count")
    _require(isinstance(players[0], Mapping), "native_request:player")
    return players[0]


def _require_temporal_external_absence(native_contract: Mapping[str, Any]) -> None:
    external = native_contract.get("external_windows") or {}
    _require(external.get("schema") == "phase8_external_windows_v1", "external:schema")
    for name in ("heroism", "power_infusion"):
        row = external.get(name) or {}
        _require(
            int(row.get("source_count") or 0) == 0
            and list(row.get("windows_ms") or []) == [],
            f"external:{name}",
        )
    dark_intent = external.get("dark_intent_proc") or {}
    _require(
        dark_intent.get("base_enabled") is False
        and float(dark_intent.get("uptime_pct") or 0.0) == 0.0,
        "external:dark_intent",
    )
    _require(
        list((external.get("synapse_springs") or {}).get("windows_ms") or []) == [],
        "external:synapse",
    )
    _require(
        (native_contract.get("raid_buffs") or {}).get("bloodlust") is False,
        "external:native_bloodlust",
    )
    individual = native_contract.get("individual_buffs") or {}
    _require(
        individual.get("dark_intent", False) is False
        and int(individual.get("power_infusion_count") or 0) == 0
        and float((native_contract.get("player_fields") or {}).get("dark_intent_uptime") or 0.0)
        == 0.0,
        "external:native_shadow",
    )


def build_native_raid_sim_request(
    *,
    target_spec: str,
    request: Mapping[str, Any],
    native_contract: Mapping[str, Any],
    class_name: str,
    race_name: str,
    equipment_items: Sequence[Mapping[str, Any]],
    talents_string: str,
    glyphs: Mapping[str, Any],
    rotation: Mapping[str, Any],
) -> dict[str, Any]:
    """Pure, exact native RaidSimRequest materializer used by producer and verifier."""
    _require_temporal_external_absence(native_contract)
    native_spec_key = str(native_contract.get("player_spec_key") or "")
    _require(native_spec_key in NATIVE_SPEC_KEYS, "materialize:spec_key")
    professions = native_contract.get("professions") or []
    _require(
        isinstance(professions, list)
        and len(professions) == 2
        and all(isinstance(value, str) and value for value in professions),
        "materialize:professions",
    )
    execution = native_contract.get("reference_execution_policy") or {}
    expected_execution_keys = {
        "reaction_time_ms",
        "channel_clip_delay_ms",
        "in_front_of_target",
        "cooldowns",
        "bonus_stats",
        "healing_model",
        "database",
        "raid_topology",
        "target_flags",
    }
    _require(set(execution) == expected_execution_keys, "materialize:execution_policy")
    _require(
        execution.get("reaction_time_ms") == 10
        and execution.get("channel_clip_delay_ms") == 0
        and execution.get("in_front_of_target") is False,
        "materialize:execution_latency",
    )
    player = {
        "name": f"phase8_{target_spec}",
        "race": race_name,
        "class": class_name,
        "equipment": {"items": [dict(value) for value in equipment_items]},
        "consumables": dict(native_contract.get("consumables") or {}),
        "bonus_stats": copy.deepcopy(execution["bonus_stats"]),
        "enable_item_swap": False,
        "item_swap": {
            "mh_item": None,
            "oh_item": None,
            "ranged_item": None,
            "items": [],
            "prepull_bonus_stats": None,
        },
        "buffs": dict(native_contract.get("individual_buffs") or {}),
        native_spec_key: dict(native_contract.get("player_spec") or {}),
        "talents_string": talents_string,
        "glyphs": dict(glyphs),
        "profession1": professions[0],
        "profession2": professions[1],
        "cooldowns": copy.deepcopy(execution["cooldowns"]),
        "rotation": copy.deepcopy(dict(rotation)),
        "reaction_time_ms": int(execution["reaction_time_ms"]),
        "channel_clip_delay_ms": int(execution["channel_clip_delay_ms"]),
        "in_front_of_target": execution["in_front_of_target"] is True,
        "distance_from_target": float(
            (request.get("target_distance") or {}).get("simulator_yards") or 0.0
        ),
        "healing_model": copy.deepcopy(execution["healing_model"]),
        "database": copy.deepcopy(execution["database"]),
    }
    player_fields = native_contract.get("player_fields") or {}
    _require(
        isinstance(player_fields, Mapping)
        and set(player_fields) == {"dark_intent_uptime"}
        and math.isfinite(float(player_fields["dark_intent_uptime"])),
        "materialize:player_fields",
    )
    player.update(player_fields)
    topology = execution["raid_topology"]
    _require(
        topology
        == {
            "party_count": 1,
            "players_per_party": [1],
            "num_active_parties": 1,
            "tanks": [],
            "stagger_stormstrikes": False,
            "target_dummies": 0,
        },
        "materialize:raid_topology",
    )
    target_flags = execution["target_flags"]
    _require(
        set(target_flags)
        == {
            "dual_wield",
            "dual_wield_penalty",
            "parry_haste",
            "suppress_dodge",
            "tank_index",
            "second_tank_index",
            "disabled_at_start",
            "target_inputs",
        },
        "materialize:target_flags",
    )
    fixture_target = request.get("fixture_target") or {}
    stats = [0.0] * 27
    stats[12] = float(fixture_target.get("simulator_attack_power") or 0.0)
    stats[22] = float(fixture_target.get("armor") or 0.0)
    encounter = request.get("encounter") or {}
    return {
        "raid": {
            "parties": [
                {
                    "players": [player],
                    "buffs": dict(native_contract.get("party_buffs") or {}),
                }
            ],
            "num_active_parties": int(topology["num_active_parties"]),
            "buffs": dict(native_contract.get("raid_buffs") or {}),
            "debuffs": dict(native_contract.get("target_debuffs") or {}),
            "tanks": copy.deepcopy(topology["tanks"]),
            "stagger_stormstrikes": topology["stagger_stormstrikes"] is True,
            "target_dummies": int(topology["target_dummies"]),
        },
        "encounter": {
            "duration": float(encounter.get("duration_seconds") or 0.0),
            "duration_variation": float(
                encounter.get("duration_variation_seconds") or 0.0
            ),
            "execute_proportion_20": float(
                (encounter.get("execute_proportions") or {}).get("20") or 0.0
            ),
            "execute_proportion_25": float(
                (encounter.get("execute_proportions") or {}).get("25") or 0.0
            ),
            "execute_proportion_35": float(
                (encounter.get("execute_proportions") or {}).get("35") or 0.0
            ),
            "execute_proportion_90": float(
                (encounter.get("execute_proportions") or {}).get("90") or 0.0
            ),
            "use_health": False,
            "targets": [
                {
                    "id": int(fixture_target.get("entry") or 0),
                    "name": "Phase 8 passive mechanical fixture",
                    "level": int(fixture_target.get("level") or 0),
                    "mob_type": "MobTypeMechanical",
                    "stats": stats,
                    "min_base_damage": float(
                        fixture_target.get("simulator_min_base_damage") or 0.0
                    ),
                    "damage_spread": float(
                        fixture_target.get("simulator_damage_spread") or 0.0
                    ),
                    "swing_speed": float(
                        fixture_target.get("simulator_swing_speed_seconds") or 0.0
                    ),
                    **copy.deepcopy(dict(target_flags)),
                }
            ],
        },
        "sim_options": dict(request.get("sim_options") or {}),
    }


def validate_exact_native_request_bytes(
    native_request: Mapping[str, Any], rebuilt_native_request: Mapping[str, Any]
) -> None:
    _require(
        canonical_json_bytes(native_request) == canonical_json_bytes(rebuilt_native_request),
        "native_request_not_exact_rematerialization",
    )


def materialize_native_request(
    *,
    request_row: Mapping[str, Any],
    checkout: Path,
    fixture_contract_path: Path,
    slot_map: Sequence[int],
    output_root: Path,
) -> dict[str, Any]:
    """Create canonical native RaidSimRequest bytes from pinned/live authorities."""
    fixture, fixture_sha256 = load_fixture_contract(fixture_contract_path)
    revision = str(fixture["authority"]["revision"])
    source = clean_checkout_identity(checkout, revision)
    target_spec = str(request_row.get("target_spec") or "")
    request = request_row.get("request")
    _require(isinstance(request, Mapping), "materialize:request")
    _require(
        request_canonical_sha256(request) == request_row.get("request_sha256"),
        "materialize:request_hash",
    )
    _require(
        request.get("fixture_contract_sha256") == fixture_sha256,
        "materialize:fixture_hash",
    )
    fixture_spec = (fixture.get("specs") or {}).get(target_spec)
    _require(isinstance(fixture_spec, Mapping), "materialize:fixture_spec")
    native_contract = fixture_spec.get("native_request")
    _require(isinstance(native_contract, Mapping), "materialize:native_contract")

    contract_player = request.get("player") or {}
    class_id = int(contract_player.get("class_id") or 0)
    race_id = int(contract_player.get("race_id") or 0)
    class_name = TRINITY_CLASS_TO_PROTO.get(class_id)
    race_name = TRINITY_RACE_TO_PROTO.get(race_id)
    source_stem = TRINITY_CLASS_TO_SOURCE_STEM.get(class_id)
    _require(class_name is not None and source_stem is not None, "materialize:class")
    _require(race_name is not None, "materialize:race")
    _require(int(native_contract.get("race_id") or 0) == race_id, "materialize:fixture_race")

    rotation_contract = request.get("rotation") or {}
    rotation_relative = str(rotation_contract.get("path") or "")
    rotation_bytes = _checked_source_bytes(
        checkout,
        rotation_relative,
        expected_revision=revision,
        label="materialize_apl",
    )
    _require(
        hashlib.sha256(rotation_bytes).hexdigest() == rotation_contract.get("sha256"),
        "materialize:apl_hash",
    )
    raw_rotation = _snake_case_json(
        _json_object_from_bytes(rotation_bytes, label="materialize_apl")
    )
    apl_proto_relative = "proto/apl.proto"
    apl_proto_bytes = _checked_source_bytes(
        checkout,
        apl_proto_relative,
        expected_revision=revision,
        label="materialize_apl_proto",
    )
    apl_action_variants = apl_action_variants_from_pinned_proto(
        apl_proto_bytes.decode("utf-8")
    )
    apl_condition_variants = apl_condition_variants_from_pinned_proto(
        apl_proto_bytes.decode("utf-8")
    )
    equipped_item_ids = {
        int(value.get("id") or 0)
        for value in ((contract_player.get("gear") or {}).get("wowsims_items") or [])
        if isinstance(value, Mapping) and int(value.get("id") or 0) > 0
    }
    rotation, apl_transform_observation = transform_apl_rotation(
        raw_rotation,
        native_contract.get("apl_transform_policy") or {},
        prepull_actions=list(native_contract.get("rotation_prepull_actions") or []),
        action_variants=apl_action_variants,
        condition_variants=apl_condition_variants,
        equipped_item_ids=equipped_item_ids,
    )

    talent_relative = f"ui/core/talents/trees/{source_stem}.json"
    talent_bytes = _checked_source_bytes(
        checkout,
        talent_relative,
        expected_revision=revision,
        label="materialize_talent_tree",
    )
    talent_trees = json.loads(talent_bytes)
    _require(isinstance(talent_trees, list), "materialize:talent_tree_shape")
    talents = contract_player.get("talents") or {}
    decoded_talent_ids = decode_talent_spell_ids(
        str(talents.get("talent_string") or ""), talent_trees
    )
    _require(
        decoded_talent_ids
        == sorted(int(value) for value in talents.get("active_spell_ids") or []),
        "materialize:talent_semantics",
    )

    proto_relative = f"proto/{source_stem}.proto"
    glyph_proto_bytes = _checked_source_bytes(
        checkout,
        proto_relative,
        expected_revision=revision,
        label="materialize_glyph_proto",
    )
    glyph_item_ids = [
        int(value) for value in (contract_player.get("glyphs") or {}).get("item_ids") or []
    ]
    _require(
        glyph_item_ids == list(native_contract.get("glyph_item_ids") or []),
        "materialize:fixture_glyphs",
    )
    glyphs = glyph_slots_from_pinned_proto(
        glyph_item_ids, glyph_proto_bytes.decode("utf-8")
    )

    gear = contract_player.get("gear") or {}
    equipment_items = []
    for raw_item in gear.get("wowsims_items") or []:
        _require(isinstance(raw_item, Mapping), "materialize:gear_item")
        equipment_items.append(
            {
                key: value
                for key, value in {
                    "id": int(raw_item.get("id") or 0),
                    "enchant": int(raw_item.get("enchant") or 0),
                    "gems": [int(value or 0) for value in raw_item.get("gems") or []],
                    "reforging": int(raw_item.get("reforging") or 0),
                }.items()
                if value != 0 and value != []
            }
        )
    native_request = build_native_raid_sim_request(
        target_spec=target_spec,
        request=request,
        native_contract=native_contract,
        class_name=class_name,
        race_name=race_name,
        equipment_items=equipment_items,
        talents_string=str(talents.get("talent_string") or ""),
        glyphs=glyphs,
        rotation=rotation,
    )
    projection = project_native_request_conditions(
        native_request,
        target_spec=target_spec,
        fixture_contract=fixture,
        fixture_sha256=fixture_sha256,
        slot_map=slot_map,
        talent_trees=talent_trees,
        talent_tree_provider_path=talent_relative,
        talent_tree_sha256=hashlib.sha256(talent_bytes).hexdigest(),
        apl_transform_observation=apl_transform_observation,
    )
    validate_native_request_projection(projection, fixture)
    validate_projection_against_request_contract(projection, request_row, fixture)

    native_artifact = store_content_addressed_bytes(
        output_root,
        "native_requests",
        canonical_json_bytes(native_request),
        suffix=".json",
    )
    projection_artifact = store_content_addressed_json(
        output_root, "condition_projections", projection
    )
    source_assets = {
        "rotation": {
            **store_content_addressed_bytes(
                output_root, "source_assets", rotation_bytes, suffix=".apl.json"
            ),
            "provider_path": rotation_relative,
        },
        "talent_tree": {
            **store_content_addressed_bytes(
                output_root, "source_assets", talent_bytes, suffix=".talents.json"
            ),
            "provider_path": talent_relative,
        },
        "glyph_proto": {
            **store_content_addressed_bytes(
                output_root, "source_assets", glyph_proto_bytes, suffix=".proto"
            ),
            "provider_path": proto_relative,
        },
        "apl_proto": {
            **store_content_addressed_bytes(
                output_root, "source_assets", apl_proto_bytes, suffix=".proto"
            ),
            "provider_path": apl_proto_relative,
        },
    }
    identity = {
        "schema": MATERIALIZATION_RECEIPT_SCHEMA,
        "target_spec": target_spec,
        "runtime_gate_ready": not runtime_projection_blockers(fixture, target_spec),
        "runtime_gate_blockers": runtime_projection_blockers(fixture, target_spec),
        "source": source,
        "fixture_contract_sha256": fixture_sha256,
        "request_contract_sha256": request_row.get("request_sha256"),
        "native_request": native_artifact,
        "condition_projection": projection_artifact,
        "source_assets": source_assets,
        "apl_transform_observation": apl_transform_observation,
    }
    receipt = {**identity, "receipt_sha256": canonical_sha256(identity)}
    receipt_artifact = store_content_addressed_json(
        output_root, "materialization_receipts", receipt
    )
    return {**receipt, "artifact": receipt_artifact}


def validate_materialization_receipt(
    receipt_path: Path,
    *,
    request_row: Mapping[str, Any],
    fixture_contract: Mapping[str, Any],
    fixture_sha256: str,
    slot_map: Sequence[int],
) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    receipt = _read_json_object(receipt_path, label="materialization_receipt")
    _require(
        receipt.get("schema") == MATERIALIZATION_RECEIPT_SCHEMA,
        "materialization_receipt:schema",
    )
    stored = str(receipt.get("receipt_sha256") or "")
    identity = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    _require(stored == canonical_sha256(identity), "materialization_receipt:self_hash")
    _require(
        receipt.get("target_spec") == request_row.get("target_spec"),
        "materialization_receipt:target_spec",
    )
    expected_blockers = runtime_projection_blockers(
        fixture_contract, str(request_row.get("target_spec") or "")
    )
    _require(
        receipt.get("runtime_gate_blockers") == expected_blockers
        and receipt.get("runtime_gate_ready") == (not expected_blockers),
        "materialization_receipt:runtime_gate",
    )
    _require(
        receipt.get("fixture_contract_sha256") == fixture_sha256,
        "materialization_receipt:fixture",
    )
    _require(
        receipt.get("request_contract_sha256") == request_row.get("request_sha256"),
        "materialization_receipt:request",
    )
    source = receipt.get("source") or {}
    source_contract = request_row.get("source_contract") or {}
    _require(
        source.get("revision") == (fixture_contract.get("authority") or {}).get("revision")
        and source.get("revision") == source_contract.get("provider_revision")
        and _normalized_repository_url(source.get("repository"))
        == _normalized_repository_url(source_contract.get("repository"))
        and source.get("source_tree_clean") is True,
        "materialization_receipt:source",
    )
    artifact_root = receipt_path.resolve().parent.parent
    native_path = verify_artifact(
        receipt.get("native_request") or {},
        artifact_root=artifact_root,
        label="materialized_native_request",
    )
    projection_path = verify_artifact(
        receipt.get("condition_projection") or {},
        artifact_root=artifact_root,
        label="materialized_condition_projection",
    )
    assets = receipt.get("source_assets") or {}
    rotation_path = verify_artifact(
        assets.get("rotation") or {}, artifact_root=artifact_root, label="materialized_apl"
    )
    talent_path = verify_artifact(
        assets.get("talent_tree") or {},
        artifact_root=artifact_root,
        label="materialized_talent_tree",
    )
    glyph_proto_path = verify_artifact(
        assets.get("glyph_proto") or {},
        artifact_root=artifact_root,
        label="materialized_glyph_proto",
    )
    apl_proto_path = verify_artifact(
        assets.get("apl_proto") or {},
        artifact_root=artifact_root,
        label="materialized_apl_proto",
    )
    request = request_row.get("request") or {}
    _require(
        (assets.get("rotation") or {}).get("provider_path")
        == (request.get("rotation") or {}).get("path")
        and sha256_file(rotation_path) == (request.get("rotation") or {}).get("sha256"),
        "materialization_receipt:apl_authority",
    )
    class_id = int((request.get("player") or {}).get("class_id") or 0)
    source_stem = TRINITY_CLASS_TO_SOURCE_STEM.get(class_id)
    _require(source_stem is not None, "materialization_receipt:class")
    _require(
        (assets.get("talent_tree") or {}).get("provider_path")
        == f"ui/core/talents/trees/{source_stem}.json",
        "materialization_receipt:talent_path",
    )
    _require(
        (assets.get("glyph_proto") or {}).get("provider_path")
        == f"proto/{source_stem}.proto",
        "materialization_receipt:glyph_path",
    )
    _require(
        (assets.get("apl_proto") or {}).get("provider_path") == "proto/apl.proto",
        "materialization_receipt:apl_proto_path",
    )
    talent_trees = json.loads(talent_path.read_bytes())
    _require(isinstance(talent_trees, list), "materialization_receipt:talent_tree")
    contract_player = request.get("player") or {}
    glyph_item_ids = [
        int(value) for value in (contract_player.get("glyphs") or {}).get("item_ids") or []
    ]
    expected_glyphs = glyph_slots_from_pinned_proto(
        glyph_item_ids, glyph_proto_path.read_text(encoding="utf-8")
    )
    native_request = _read_json_object(native_path, label="materialized_native_request")
    source_rotation = _snake_case_json(
        _json_object_from_bytes(rotation_path.read_bytes(), label="materialized_apl")
    )
    fixture_spec = (fixture_contract.get("specs") or {}).get(
        str(receipt.get("target_spec") or "")
    ) or {}
    fixture_native = fixture_spec.get("native_request") or {}
    apl_action_variants = apl_action_variants_from_pinned_proto(
        apl_proto_path.read_text(encoding="utf-8")
    )
    apl_condition_variants = apl_condition_variants_from_pinned_proto(
        apl_proto_path.read_text(encoding="utf-8")
    )
    equipped_item_ids = {
        int(value.get("id") or 0)
        for value in (((request.get("player") or {}).get("gear") or {}).get("wowsims_items") or [])
        if isinstance(value, Mapping) and int(value.get("id") or 0) > 0
    }
    expected_rotation, apl_transform_observation = transform_apl_rotation(
        source_rotation,
        fixture_native.get("apl_transform_policy") or {},
        prepull_actions=list(fixture_native.get("rotation_prepull_actions") or []),
        action_variants=apl_action_variants,
        condition_variants=apl_condition_variants,
        equipped_item_ids=equipped_item_ids,
    )
    _require(
        receipt.get("apl_transform_observation") == apl_transform_observation,
        "materialization_receipt:apl_transform_observation",
    )
    _require(
        (_request_player(native_request).get("rotation") or {}) == expected_rotation,
        "materialization_receipt:rotation_transform",
    )
    _require(
        (_request_player(native_request).get("glyphs") or {}) == expected_glyphs,
        "materialization_receipt:glyph_semantics",
    )
    class_name = TRINITY_CLASS_TO_PROTO.get(class_id)
    race_id = int((request.get("player") or {}).get("race_id") or 0)
    race_name = TRINITY_RACE_TO_PROTO.get(race_id)
    _require(class_name is not None and race_name is not None, "materialization_receipt:identity")
    equipment_items: list[dict[str, Any]] = []
    for raw_item in (
        (((request.get("player") or {}).get("gear") or {}).get("wowsims_items") or [])
    ):
        _require(isinstance(raw_item, Mapping), "materialization_receipt:gear_item")
        equipment_items.append(
            {
                key: value
                for key, value in {
                    "id": int(raw_item.get("id") or 0),
                    "enchant": int(raw_item.get("enchant") or 0),
                    "gems": [int(value or 0) for value in raw_item.get("gems") or []],
                    "reforging": int(raw_item.get("reforging") or 0),
                }.items()
                if value != 0 and value != []
            }
        )
    rebuilt_native_request = build_native_raid_sim_request(
        target_spec=str(receipt.get("target_spec") or ""),
        request=request,
        native_contract=fixture_native,
        class_name=class_name,
        race_name=race_name,
        equipment_items=equipment_items,
        talents_string=str(
            ((request.get("player") or {}).get("talents") or {}).get(
                "talent_string"
            )
            or ""
        ),
        glyphs=expected_glyphs,
        rotation=expected_rotation,
    )
    try:
        validate_exact_native_request_bytes(native_request, rebuilt_native_request)
    except WowsimsGenerationError as exc:
        raise WowsimsGenerationError(
            "materialization_receipt:native_request_not_exact_rematerialization"
        ) from exc
    projected_again = project_native_request_conditions(
        native_request,
        target_spec=str(receipt.get("target_spec") or ""),
        fixture_contract=fixture_contract,
        fixture_sha256=fixture_sha256,
        slot_map=slot_map,
        talent_trees=talent_trees,
        talent_tree_provider_path=str(
            (assets.get("talent_tree") or {}).get("provider_path") or ""
        ),
        talent_tree_sha256=sha256_file(talent_path),
        apl_transform_observation=apl_transform_observation,
    )
    stored_projection = _read_json_object(
        projection_path, label="materialized_condition_projection"
    )
    _require(
        projected_again == stored_projection,
        "materialization_receipt:projection_not_derived",
    )
    validate_native_request_projection(projected_again, fixture_contract)
    validate_projection_against_request_contract(
        projected_again, request_row, fixture_contract
    )
    return receipt, native_path, projected_again


def _single_player(native_request: Mapping[str, Any]) -> Mapping[str, Any]:
    raid = native_request.get("raid") or {}
    parties = raid.get("parties") or []
    _require(isinstance(parties, list) and len(parties) == 1, "native_request:party_count")
    players = (parties[0] or {}).get("players") or []
    _require(isinstance(players, list) and len(players) == 1, "native_request:player_count")
    _require(isinstance(players[0], Mapping), "native_request:player")
    return players[0]


def _single_target(native_request: Mapping[str, Any]) -> Mapping[str, Any]:
    encounter = native_request.get("encounter") or {}
    targets = encounter.get("targets") or []
    _require(isinstance(targets, list) and len(targets) == 1, "native_request:target_count")
    _require(isinstance(targets[0], Mapping), "native_request:target")
    return targets[0]


def _empty_item_swap(player: Mapping[str, Any]) -> bool:
    if player.get("enable_item_swap") not in {None, False}:
        return False
    swap = player.get("item_swap")
    if not isinstance(swap, Mapping):
        return False
    allowed_empty = {
        "mh_item": None,
        "oh_item": None,
        "ranged_item": None,
        "items": [],
        "prepull_bonus_stats": None,
    }
    return set(swap) == set(allowed_empty) and all(
        swap.get(key) in {None, False} if key != "items" else swap.get(key) == []
        for key in allowed_empty
    )


def project_native_request_conditions(
    native_request: Mapping[str, Any],
    *,
    target_spec: str,
    fixture_contract: Mapping[str, Any],
    fixture_sha256: str,
    slot_map: Sequence[int],
    talent_trees: Sequence[Mapping[str, Any]] | None = None,
    talent_tree_provider_path: str | None = None,
    talent_tree_sha256: str | None = None,
    apl_transform_observation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Independently derive comparison facts from native request fields."""
    fixture_spec = (fixture_contract.get("specs") or {}).get(target_spec)
    _require(isinstance(fixture_spec, Mapping), "fixture_spec_missing")
    player = _single_player(native_request)
    target = _single_target(native_request)
    encounter = native_request.get("encounter") or {}
    sim_options = native_request.get("sim_options") or {}
    raid = native_request.get("raid") or {}
    party = (raid.get("parties") or [])[0]
    equipment = player.get("equipment") or {}
    raw_items = equipment.get("items") or []
    source_items: list[dict[str, Any] | None] = []
    for raw_item in raw_items:
        if not raw_item:
            source_items.append(None)
            continue
        _require(isinstance(raw_item, Mapping), "native_request:gear_item")
        source_items.append(
            {
                "id": int(raw_item.get("id") or 0),
                "enchant": int(raw_item.get("enchant") or 0),
                "gems": [int(value or 0) for value in raw_item.get("gems") or []],
                "reforging": int(raw_item.get("reforging") or 0),
            }
        )
    transformed_gear = canonical_wowsims_manifest(
        {"items": source_items}, list(slot_map)
    )
    spec_keys = [key for key in sorted(NATIVE_SPEC_KEYS) if key in player]
    _require(len(spec_keys) == 1, "native_request:spec_options_oneof")
    stats = list(target.get("stats") or [])
    armor = stats[22] if len(stats) > 22 else 0
    attack_power = stats[12] if len(stats) > 12 else 0
    projection: dict[str, Any] = {
        "schema": CONDITION_PROJECTION_SCHEMA,
        "target_spec": target_spec,
        "fixture_contract_sha256": fixture_sha256,
        "simulator": {
            "iterations": int(sim_options.get("iterations") or 0),
            "random_seed": int(sim_options.get("random_seed") or 0),
            "is_test": sim_options.get("is_test") is True,
        },
        "encounter": {
            "duration_seconds": float(encounter.get("duration") or 0.0),
            "duration_variation_seconds": float(encounter.get("duration_variation") or 0.0),
            "execute_proportions": {
                "90": float(encounter.get("execute_proportion_90") or 0.0),
                "35": float(encounter.get("execute_proportion_35") or 0.0),
                "25": float(encounter.get("execute_proportion_25") or 0.0),
                "20": float(encounter.get("execute_proportion_20") or 0.0),
            },
        },
        "target": {
            "count": 1,
            "level": int(target.get("level") or 0),
            "mob_type": str(target.get("mob_type") or ""),
            "armor": int(armor),
            "attack_power": int(attack_power),
            "swing_speed_seconds": float(target.get("swing_speed") or 0.0),
            "min_base_damage": float(target.get("min_base_damage") or 0.0),
            "damage_spread": float(target.get("damage_spread") or 0.0),
            "parry_haste": target.get("parry_haste") is True,
            "target_flags": {
                "dual_wield": target.get("dual_wield") is True,
                "dual_wield_penalty": target.get("dual_wield_penalty") is True,
                "parry_haste": target.get("parry_haste") is True,
                "suppress_dodge": target.get("suppress_dodge") is True,
                "tank_index": int(target.get("tank_index", 0)),
                "second_tank_index": int(target.get("second_tank_index", 0)),
                "disabled_at_start": target.get("disabled_at_start") is True,
                "target_inputs": list(target.get("target_inputs") or []),
            },
        },
        "player": {
            "race": str(player.get("race") or ""),
            "class": str(player.get("class") or ""),
            "talents_string": str(player.get("talents_string") or ""),
            "glyphs": dict(player.get("glyphs") or {}),
            "distance_from_target": float(player.get("distance_from_target") or 0.0),
            "profession1": str(player.get("profession1") or ""),
            "profession2": str(player.get("profession2") or ""),
            "consumables": dict(player.get("consumables") or {}),
            "individual_buffs": dict(player.get("buffs") or {}),
            "item_swap_empty": _empty_item_swap(player),
            "gear_manifest": transformed_gear,
            "gear_manifest_sha256": canonical_sha256(transformed_gear),
            "spec_options_key": spec_keys[0],
            "spec_options": dict(player[spec_keys[0]] or {}),
            "rotation": dict(player.get("rotation") or {}),
            "rotation_sha256": canonical_sha256(dict(player.get("rotation") or {})),
            "rotation_prepull_actions": list(
                (player.get("rotation") or {}).get("prepull_actions") or []
            ),
            "reference_execution_policy": {
                "reaction_time_ms": int(player.get("reaction_time_ms") or 0),
                "channel_clip_delay_ms": int(
                    player.get("channel_clip_delay_ms") or 0
                ),
                "in_front_of_target": player.get("in_front_of_target") is True,
                "cooldowns": dict(player.get("cooldowns") or {}),
                "bonus_stats": dict(player.get("bonus_stats") or {}),
                "healing_model": dict(player.get("healing_model") or {}),
                "database": dict(player.get("database") or {}),
            },
        },
        "raid": {
            "buffs": dict(raid.get("buffs") or {}),
            "debuffs": dict(raid.get("debuffs") or {}),
            "party_buffs": dict((party or {}).get("buffs") or {}),
            "topology": {
                "party_count": len(raid.get("parties") or []),
                "players_per_party": [
                    len((value or {}).get("players") or [])
                    for value in raid.get("parties") or []
                ],
                "num_active_parties": int(raid.get("num_active_parties") or 0),
                "tanks": list(raid.get("tanks") or []),
                "stagger_stormstrikes": raid.get("stagger_stormstrikes") is True,
                "target_dummies": int(raid.get("target_dummies") or 0),
            },
        },
        "native_request": {
            "player_spec_key": spec_keys[0],
            "player_spec": dict(player[spec_keys[0]] or {}),
            "professions": [
                str(player.get("profession1") or ""),
                str(player.get("profession2") or ""),
            ],
            "player_fields": {
                "dark_intent_uptime": float(
                    player.get("dark_intent_uptime") or 0.0
                )
            },
            "consumables": dict(player.get("consumables") or {}),
            "individual_buffs": dict(player.get("buffs") or {}),
            "raid_buffs": dict(raid.get("buffs") or {}),
            "party_buffs": dict((party or {}).get("buffs") or {}),
            "target_debuffs": dict(raid.get("debuffs") or {}),
            "rotation_prepull_actions": list(
                (player.get("rotation") or {}).get("prepull_actions") or []
            ),
            "temporal_external_absence": {
                "bloodlust": (raid.get("buffs") or {}).get("bloodlust", False)
                is False,
                "power_infusion_count": int(
                    (player.get("buffs") or {}).get("power_infusion_count") or 0
                ),
                "dark_intent": (player.get("buffs") or {}).get(
                    "dark_intent", False
                )
                is False,
                "dark_intent_uptime": float(
                    player.get("dark_intent_uptime") or 0.0
                ),
            },
        },
    }
    if talent_trees is not None:
        _require(bool(talent_tree_provider_path), "talents:provider_path")
        _require(
            isinstance(talent_tree_sha256, str)
            and len(talent_tree_sha256) == SHA256_LENGTH,
            "talents:tree_sha256",
        )
        projection["talent_semantics"] = {
            "talent_tree_provider_path": talent_tree_provider_path,
            "talent_tree_sha256": talent_tree_sha256,
            "decoded_active_spell_ids": decode_talent_spell_ids(
                str(player.get("talents_string") or ""), talent_trees
            ),
        }
    if apl_transform_observation is not None:
        projection["apl_transform_observation"] = dict(apl_transform_observation)
    projection["projection_sha256"] = canonical_sha256(projection)
    return projection


def validate_projection_against_request_contract(
    projection: Mapping[str, Any],
    request_row: Mapping[str, Any],
    fixture_contract: Mapping[str, Any],
) -> None:
    """Prove the semantic request/manifest describes the native proto bytes."""
    target_spec = str(request_row.get("target_spec") or "")
    _require(projection.get("target_spec") == target_spec, "request_contract:target_spec")
    request = request_row.get("request")
    _require(isinstance(request, Mapping), "request_contract:request")
    _require(
        request_canonical_sha256(request) == request_row.get("request_sha256"),
        "request_contract:self_hash",
    )
    expected_projection = project_request_contract_conditions(request)
    comparison = request_row.get("comparison_manifest")
    _require(isinstance(comparison, Mapping), "request_contract:comparison_manifest")
    _require(
        comparison.get("source_setup") == expected_projection["source_setup"],
        "request_contract:source_setup",
    )
    requirements = comparison.get("requirements") or []
    _require(isinstance(requirements, list), "request_contract:requirements")
    by_id = {
        str(row.get("id") or ""): row
        for row in requirements
        if isinstance(row, Mapping)
    }
    for requirement_id, expected in expected_projection["runtime_equals"].items():
        _require(requirement_id in by_id, f"request_contract:requirement:{requirement_id}")
        _require(
            by_id[requirement_id].get("equals") == expected,
            f"request_contract:requirement_value:{requirement_id}",
        )

    player = projection.get("player") or {}
    contract_player = request.get("player") or {}
    _require(
        PROTO_RACE_TO_TRINITY_ID.get(str(player.get("race") or ""))
        == int(contract_player.get("race_id") or 0),
        "native_request_contract:race",
    )
    _require(
        player.get("talents_string")
        == (contract_player.get("talents") or {}).get("talent_string"),
        "native_request_contract:talents",
    )
    talent_semantics = projection.get("talent_semantics") or {}
    _require(
        talent_semantics.get("decoded_active_spell_ids")
        == sorted(
            int(value)
            for value in (contract_player.get("talents") or {}).get(
                "active_spell_ids"
            )
            or []
        ),
        "native_request_contract:talent_semantics",
    )
    raw_glyphs = player.get("glyphs") or {}
    glyph_order = (
        "prime1", "prime2", "prime3", "major1", "major2", "major3",
        "minor1", "minor2", "minor3",
    )
    raw_glyph_ids = [int(raw_glyphs.get(key) or 0) for key in glyph_order]
    raw_glyph_ids = [value for value in raw_glyph_ids if value > 0]
    contract_glyphs = contract_player.get("glyphs") or {}
    _require(
        raw_glyph_ids
        == [int(value) for value in contract_glyphs.get("item_ids") or []],
        "native_request_contract:glyphs",
    )
    _require(
        player.get("gear_manifest_sha256")
        == (contract_player.get("gear") or {}).get("transformed_manifest_sha256"),
        "native_request_contract:gear",
    )
    _require(
        player.get("distance_from_target")
        == float((request.get("target_distance") or {}).get("simulator_yards") or 0.0),
        "native_request_contract:distance",
    )
    _require(player.get("item_swap_empty") is True, "native_request_contract:item_swap")
    fixture_spec = (fixture_contract.get("specs") or {}).get(target_spec)
    _require(isinstance(fixture_spec, Mapping), "native_request_contract:fixture_spec")
    native_expected = fixture_spec.get("native_request")
    _require(
        isinstance(native_expected, Mapping),
        "native_request_contract:fixture_native_request_missing",
    )
    expected_keys = {
        "player_spec_key",
        "player_spec",
        "race_id",
        "glyph_item_ids",
        "glyph_property_ids",
        "glyph_aura_spell_ids",
        "professions",
        "player_fields",
        "consumables",
        "individual_buffs",
        "raid_buffs",
        "party_buffs",
        "target_debuffs",
        "rotation_prepull_actions",
        "apl_transform_policy",
        "reference_execution_policy",
        "external_windows",
        "initial_state",
    }
    _require(
        set(native_expected) == expected_keys,
        "native_request_contract:fixture_native_request_fields",
    )
    projected_native = projection.get("native_request") or {}
    for key in (
        "player_spec_key",
        "player_spec",
        "professions",
        "player_fields",
        "consumables",
        "individual_buffs",
        "raid_buffs",
        "party_buffs",
        "target_debuffs",
        "rotation_prepull_actions",
    ):
        _require(
            projected_native.get(key) == native_expected.get(key),
            f"native_request_contract:fixture_native_request:{key}",
        )
    _require(
        player.get("reference_execution_policy")
        == {
            key: value
            for key, value in native_expected["reference_execution_policy"].items()
            if key not in {"raid_topology", "target_flags"}
        }
        and (projection.get("raid") or {}).get("topology")
        == native_expected["reference_execution_policy"]["raid_topology"]
        and (projection.get("target") or {}).get("target_flags")
        == native_expected["reference_execution_policy"]["target_flags"],
        "native_request_contract:reference_execution_policy",
    )
    absence = projected_native.get("temporal_external_absence") or {}
    _require(
        absence
        == {
            "bloodlust": True,
            "power_infusion_count": 0,
            "dark_intent": True,
            "dark_intent_uptime": 0.0,
        },
        "native_request_contract:temporal_external_absence",
    )
    apl_observation = projection.get("apl_transform_observation") or {}
    _require(
        apl_observation.get("policy_sha256")
        == canonical_sha256(native_expected.get("apl_transform_policy") or {}),
        "native_request_contract:apl_transform_policy",
    )
    _require(
        int(native_expected.get("race_id") or 0)
        == int(contract_player.get("race_id") or 0),
        "native_request_contract:fixture_race",
    )
    _require(
        list(native_expected.get("glyph_item_ids") or [])
        == list(contract_glyphs.get("item_ids") or []),
        "native_request_contract:fixture_glyph_items",
    )
    _require(
        sorted(int(value) for value in native_expected.get("glyph_property_ids") or [])
        == sorted(
            int(value)
            for value in (contract_glyphs.get("runtime_identity") or {}).get(
                "property_ids"
            )
            or []
        ),
        "native_request_contract:fixture_glyph_properties",
    )
    _require(
        sorted(int(value) for value in native_expected.get("glyph_aura_spell_ids") or [])
        == sorted(
            int(value)
            for value in (contract_glyphs.get("runtime_identity") or {}).get(
                "aura_spell_ids"
            )
            or []
        ),
        "native_request_contract:fixture_glyph_auras",
    )
    _require(
        native_expected.get("initial_state") == fixture_spec.get("initial_state")
        and isinstance(fixture_spec.get("initial_state"), Mapping),
        "native_request_contract:initial_state_missing",
    )


def runtime_projection_blockers(
    fixture_contract: Mapping[str, Any], target_spec: str
) -> list[str]:
    fixture_spec = (fixture_contract.get("specs") or {}).get(target_spec) or {}
    blockers: list[str] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            if value.get("runtime_projection_complete") is False:
                reasons = [str(item) for item in value.get("blockers") or []]
                blockers.extend(reasons or [f"{path}:runtime_projection_incomplete"])
            for key, item in value.items():
                visit(item, f"{path}.{key}" if path else str(key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    visit(fixture_spec.get("runtime_expected") or {}, "runtime_expected")
    visit(fixture_spec.get("native_request") or {}, "native_request")
    return sorted(set(blockers))


def validate_native_request_projection(
    projection: Mapping[str, Any], fixture_contract: Mapping[str, Any]
) -> None:
    simulator = projection.get("simulator") or {}
    _require(simulator.get("iterations") == EXPECTED_ITERATIONS, "request_iterations")
    _require(simulator.get("random_seed") == EXPECTED_RANDOM_SEED, "request_seed")
    _require(simulator.get("is_test") is True, "request_is_test")
    encounter = projection.get("encounter") or {}
    expected_encounter = fixture_contract["encounter"]
    _require(
        encounter.get("duration_seconds") == float(expected_encounter["duration_seconds"]),
        "request_duration",
    )
    _require(
        encounter.get("duration_variation_seconds")
        == float(expected_encounter["duration_variation_seconds"]),
        "request_duration_variation",
    )
    _require(
        encounter.get("execute_proportions") == expected_encounter["execute_proportions"],
        "request_execute_proportions",
    )
    target = projection.get("target") or {}
    fixture_target = fixture_contract["target"]
    _require(target.get("count") == 1, "request_target_count")
    _require(target.get("level") == fixture_target["level"], "request_target_level")
    _require(target.get("mob_type") == "MobTypeMechanical", "request_target_type")
    _require(target.get("armor") == fixture_target["armor"], "request_target_armor")
    if fixture_target.get("live_target_attacks") is False:
        _require(target.get("attack_power") == 0, "request_passive_target_attack_power")
        _require(target.get("swing_speed_seconds") == 0.0, "request_passive_target_swing")
        _require(target.get("min_base_damage") == 0.0, "request_passive_target_damage")
        _require(target.get("damage_spread") == 0.0, "request_passive_target_spread")
    player = projection.get("player") or {}
    _require(player.get("item_swap_empty") is True, "request_item_swap")
    spec = str(projection.get("target_spec") or "")
    fixture_spec = fixture_contract["specs"][spec]
    lane = fixture_spec["lane"]
    expected_distance = float(fixture_contract["distance_contracts"][lane]["simulator_yards"])
    _require(player.get("distance_from_target") == expected_distance, "request_distance")
    # These keys are mandatory because borrowing an upstream default by name is
    # not proof of live compatibility.
    for key in (
        "simulator_options",
        "pet_setup",
        "prepull_setup",
        "initial_state",
        "native_request",
    ):
        _require(key in fixture_spec, f"fixture_spec_missing_{key}")
    _require(
        player.get("spec_options")
        == fixture_spec["native_request"]["player_spec"],
        "request_simulator_options",
    )


def parse_native_result(native_result: Mapping[str, Any]) -> dict[str, Any]:
    _require(native_result.get("error") is None, "native_result:simulator_error")
    iterations = int(native_result.get("iterationsDone") or 0)
    _require(iterations == EXPECTED_ITERATIONS, "native_result:iterations")
    raid_metrics = native_result.get("raidMetrics") or {}
    raid_dps = float((raid_metrics.get("dps") or {}).get("avg") or 0.0)
    parties = raid_metrics.get("parties") or []
    _require(isinstance(parties, list) and len(parties) == 1, "native_result:parties")
    players = (parties[0] or {}).get("players") or []
    _require(isinstance(players, list) and len(players) == 1, "native_result:players")
    player_dps = float(((players[0] or {}).get("dps") or {}).get("avg") or 0.0)
    _require(math.isfinite(raid_dps) and raid_dps > 0.0, "native_result:raid_dps")
    _require(math.isfinite(player_dps) and player_dps > 0.0, "native_result:player_dps")
    _require(abs(raid_dps - player_dps) < 1e-9, "native_result:dps_disagreement")
    avg_duration = float(native_result.get("avgIterationDuration") or 0.0)
    first_duration = float(native_result.get("firstIterationDuration") or 0.0)
    _require(avg_duration == 300.0 and first_duration == 300.0, "native_result:duration")

    action_activity_fields = {
        "casts",
        "hits",
        "crits",
        "ticks",
        "critTicks",
        "misses",
        "dodges",
        "parries",
        "blocks",
        "critBlocks",
        "glances",
        "damage",
        "critDamage",
        "tickDamage",
        "critTickDamage",
        "glanceDamage",
        "blockDamage",
        "critBlockDamage",
        "threat",
        "healing",
        "critHealing",
        "shielding",
        "castTimeMs",
    }
    aura_activity_fields = {"uptimeSecondsAvg", "procsAvg"}

    def contains_positive_number(value: Any) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return math.isfinite(float(value)) and float(value) > 0.0
        if isinstance(value, Mapping):
            return any(contains_positive_number(child) for child in value.values())
        if isinstance(value, list):
            return any(contains_positive_number(child) for child in value)
        return False

    def metric_has_activity(metric: Mapping[str, Any], fields: set[str]) -> bool:
        for key, value in metric.items():
            if key in fields and contains_positive_number(value):
                return True
            if isinstance(value, Mapping) and metric_has_activity(value, fields):
                return True
            if isinstance(value, list):
                for child in value:
                    if isinstance(child, Mapping) and metric_has_activity(child, fields):
                        return True
        return False

    def observed_active_spell_ids(value: Any, metric_kind: str | None = None) -> set[int]:
        found: set[int] = set()
        if isinstance(value, Mapping):
            identity = value.get("id")
            if metric_kind is not None and isinstance(identity, Mapping):
                spell_id = int(identity.get("spellId") or 0)
                fields = (
                    action_activity_fields
                    if metric_kind == "action"
                    else aura_activity_fields
                )
                if spell_id > 0 and metric_has_activity(value, fields):
                    found.add(spell_id)
            for key, child in value.items():
                child_kind = (
                    "action"
                    if key == "actions"
                    else "aura"
                    if key == "auras"
                    else None
                )
                found.update(observed_active_spell_ids(child, child_kind))
        elif isinstance(value, list):
            for child in value:
                found.update(observed_active_spell_ids(child, metric_kind))
        return found

    forbidden_observed = sorted(
        observed_active_spell_ids(native_result)
        & FORBIDDEN_TEMPORAL_EXTERNAL_RESULT_SPELL_IDS
    )
    _require(
        not forbidden_observed,
        f"native_result:temporal_external_activity:{forbidden_observed}",
    )
    return {
        "dps": raid_dps,
        "iterations_done": iterations,
        "simulator_error": None,
        "avg_iteration_duration_seconds": avg_duration,
        "first_iteration_duration_seconds": first_duration,
        "temporal_external_spell_ids_observed": forbidden_observed,
        "source_paths": {
            "raid_dps": "raidMetrics.dps.avg",
            "player_dps": "raidMetrics.parties[0].players[0].dps.avg",
            "iterations": "iterationsDone",
            "error": "error",
        },
    }


def _rotation_spell_action_ids(value: Any) -> set[tuple[int, int]]:
    observed: set[tuple[int, int]] = set()
    spell_action_fields = {
        "cast_spell",
        "cast_friendly_spell",
        "channel_spell",
        "multidot",
        "strict_multidot",
        "multishield",
    }
    if isinstance(value, Mapping):
        for field in spell_action_fields & set(value):
            payload = value.get(field)
            action_id = payload.get("spell_id") if isinstance(payload, Mapping) else None
            _require(isinstance(action_id, Mapping), "compute_stats:spell_action_id")
            spell_id = int(action_id.get("spell_id") or 0)
            _require(spell_id > 0, "compute_stats:non_spell_action_survived")
            observed.add((spell_id, int(action_id.get("tag") or 0)))
        for child in value.values():
            observed.update(_rotation_spell_action_ids(child))
    elif isinstance(value, list):
        for child in value:
            observed.update(_rotation_spell_action_ids(child))
    return observed


def parse_compute_stats_validation(
    result: Mapping[str, Any], *, rotation: Mapping[str, Any]
) -> dict[str, Any]:
    """Require every surviving spell action to resolve in pinned ComputeStats."""
    _require(not result.get("errorResult"), "compute_stats:error")
    parties = ((result.get("raidStats") or {}).get("parties") or [])
    _require(len(parties) == 1, "compute_stats:party_count")
    players = (parties[0] or {}).get("players") or []
    _require(len(players) == 5, "compute_stats:player_slot_count")
    _require(
        all(
            not (value or {}).get("rotationStats")
            and not ((value or {}).get("metadata") or {}).get("spells")
            for value in players[1:]
        ),
        "compute_stats:inactive_player_slots",
    )
    player = players[0] or {}
    rotation_stats = player.get("rotationStats") or {}
    validations: list[dict[str, Any]] = []
    for section in ("prepullActions", "priorityList"):
        for action_index, action in enumerate(rotation_stats.get(section) or []):
            for validation in (action or {}).get("validations") or []:
                level = str((validation or {}).get("logLevel") or "")
                validations.append(
                    {
                        "section": section,
                        "action_index": action_index,
                        "log_level": level,
                        "validation": str(
                            (validation or {}).get("validation") or ""
                        ),
                    }
                )
                _require(
                    level not in {"Warning", "Error", "1", "2"},
                    f"compute_stats:apl_validation:{section}:{action_index}",
                )
    metadata_spells: dict[tuple[int, int], bool] = {}
    for row in ((player.get("metadata") or {}).get("spells") or []):
        action_id = (row or {}).get("id") or {}
        spell_id = int(action_id.get("spellId") or 0)
        if spell_id > 0:
            metadata_spells[(spell_id, int(action_id.get("tag") or 0))] = (
                (row or {}).get("isCastable") is True
            )
    required = _rotation_spell_action_ids(rotation)
    missing = sorted(identity for identity in required if identity not in metadata_spells)
    uncastable = sorted(
        identity for identity in required if metadata_spells.get(identity) is not True
    )
    _require(not missing, f"compute_stats:missing_spells:{missing}")
    _require(not uncastable, f"compute_stats:uncastable_spells:{uncastable}")
    normalized_required = [
        {"spell_id": spell_id, "tag": tag} for spell_id, tag in sorted(required)
    ]
    observation = {
        "required_spell_actions": normalized_required,
        "required_spell_actions_sha256": canonical_sha256(normalized_required),
        "validation_count": len(validations),
        "validations_sha256": canonical_sha256(validations),
        "warning_or_error_count": 0,
    }
    return {**observation, "observation_sha256": canonical_sha256(observation)}


def generate_one_reference(
    *,
    request_row: Mapping[str, Any],
    materialization_receipt_path: Path,
    build_receipt_path: Path,
    fixture_contract_path: Path,
    slot_map: Sequence[int],
    output_root: Path,
    classification: str,
    request_catalog_sha256: str,
    evidence_repository_admission_commit: str | None,
    timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    _require(
        classification in {RESEARCH_CLASSIFICATION, UNPUBLISHED_CLASSIFICATION},
        "generation_classification",
    )
    _require(
        bool(re.fullmatch(r"[0-9a-f]{64}", request_catalog_sha256)),
        "generation_request_catalog_hash",
    )
    if classification == UNPUBLISHED_CLASSIFICATION:
        _require(
            bool(
                re.fullmatch(
                    r"[0-9a-f]{40}", str(evidence_repository_admission_commit or "")
                )
            ),
            "generation_admission_commit",
        )
    fixture, fixture_sha256 = load_fixture_contract(fixture_contract_path)
    if classification == UNPUBLISHED_CLASSIFICATION:
        _require(
            (fixture.get("authority") or {}).get("lifecycle_status")
            == "final_for_offline_reference_generation",
            "generation_fixture_not_final",
        )
    target_spec = str(request_row.get("target_spec") or "")
    _require(bool(target_spec), "generation_target_spec")
    revision = str(fixture["authority"]["revision"])
    build_receipt, binary_path = validate_build_receipt(
        build_receipt_path, expected_revision=revision
    )
    _require(
        build_receipt_path.resolve().parent.parent == output_root.resolve(),
        "build_receipt_must_share_artifact_root",
    )
    materialization_receipt, native_request_path, projection = (
        validate_materialization_receipt(
            materialization_receipt_path,
            request_row=request_row,
            fixture_contract=fixture,
            fixture_sha256=fixture_sha256,
            slot_map=slot_map,
        )
    )
    _require(
        materialization_receipt.get("runtime_gate_ready") is True
        and not materialization_receipt.get("runtime_gate_blockers"),
        "generation_runtime_projection_incomplete",
    )
    _require(
        materialization_receipt_path.resolve().parent.parent == output_root.resolve(),
        "materialization_receipt_must_share_artifact_root",
    )
    request_bytes = native_request_path.read_bytes()
    request = _json_object_from_bytes(request_bytes, label="native_request")
    _require(request_bytes == canonical_json_bytes(request), "native_request:not_canonical_bytes")
    request_contract = request_row.get("request")
    _require(isinstance(request_contract, Mapping), "generation_request_contract")
    request_contract_sha256 = request_canonical_sha256(request_contract)
    _require(
        request_contract_sha256 == request_row.get("request_sha256"),
        "generation_request_contract_hash",
    )
    request_contract_artifact = store_content_addressed_json(
        output_root, "request_contracts", request_contract
    )
    request_row_artifact = store_content_addressed_json(
        output_root, "request_rows", request_row
    )
    request_artifact = store_content_addressed_bytes(
        output_root, "native_requests", request_bytes, suffix=".json"
    )
    projection_artifact = store_content_addressed_json(
        output_root, "condition_projections", projection
    )
    validator_path = output_root.resolve() / str(
        (build_receipt.get("request_validator") or {}).get("path") or ""
    )
    with tempfile.TemporaryDirectory(prefix=f"wowsims-compute-{target_spec}-") as temporary:
        compute_stats_path = Path(temporary) / "compute-stats.json"
        proto_validation_outcome, proto_validation_output = _run_capture(
            [
                str(validator_path),
                str(output_root.resolve() / str(request_artifact["path"])),
                str(compute_stats_path),
            ],
            cwd=REPO_ROOT,
            env=dict(os.environ),
            timeout_seconds=60.0,
        )
        _require_normal_child(proto_validation_outcome, label="native_request_protojson")
        _require(compute_stats_path.is_file(), "compute_stats:missing")
        compute_stats_bytes = compute_stats_path.read_bytes()
    compute_stats_result = _json_object_from_bytes(
        compute_stats_bytes, label="compute_stats"
    )
    compute_stats_observation = parse_compute_stats_validation(
        compute_stats_result, rotation=(_request_player(request).get("rotation") or {})
    )
    compute_stats_artifact = store_content_addressed_bytes(
        output_root, "compute_stats", compute_stats_bytes, suffix=".json"
    )
    proto_validation_log = store_content_addressed_bytes(
        output_root,
        "process_logs",
        proto_validation_output,
        suffix=".log",
    )

    with tempfile.TemporaryDirectory(prefix=f"wowsims-{target_spec}-") as temporary:
        raw_result_path = Path(temporary) / "result.json"
        command = [
            str(binary_path),
            "sim",
            "--infile",
            str(output_root.resolve() / str(request_artifact["path"])),
            "--outfile",
            str(raw_result_path),
        ]
        outcome, process_output = _run_capture(
            command,
            cwd=REPO_ROOT,
            env=dict(os.environ),
            timeout_seconds=timeout_seconds,
        )
        _require_normal_child(outcome, label="wowsims_sim")
        _require(raw_result_path.is_file(), "native_result:missing")
        result_bytes = raw_result_path.read_bytes()
    result = _json_object_from_bytes(result_bytes, label="native_result")
    observation = parse_native_result(result)
    result_artifact = store_content_addressed_bytes(
        output_root, "native_results", result_bytes, suffix=".json"
    )
    process_output_artifact = store_content_addressed_bytes(
        output_root, "process_logs", process_output, suffix=".log"
    )
    build_artifact = {
        "path": build_receipt_path.resolve().relative_to(output_root.resolve()).as_posix(),
        "sha256": sha256_file(build_receipt_path),
        "byte_count": build_receipt_path.stat().st_size,
        "receipt_sha256": build_receipt["receipt_sha256"],
        "binary_sha256": build_receipt["binary"]["sha256"],
    }
    materialization_artifact = {
        "path": materialization_receipt_path.resolve()
        .relative_to(output_root.resolve())
        .as_posix(),
        "sha256": sha256_file(materialization_receipt_path),
        "byte_count": materialization_receipt_path.stat().st_size,
        "receipt_sha256": materialization_receipt["receipt_sha256"],
    }
    identity: dict[str, Any] = {
        "schema": GENERATION_RECEIPT_SCHEMA,
        "classification": classification,
        "gate_bearing": False,
        "authority_scope": "offline_denominator_only",
        "live_fixture_join_status": "pending_physical_raw_capture",
        "request_catalog_sha256": request_catalog_sha256,
        "evidence_repository_admission_commit": evidence_repository_admission_commit,
        "target_spec": target_spec,
        "fixture_contract": {
            **store_content_addressed_bytes(
                output_root,
                "fixture_contracts",
                fixture_contract_path.read_bytes(),
                suffix=".json",
            ),
            "canonical_sha256": fixture_sha256,
        },
        "source_revision": revision,
        "request_contract_sha256": request_contract_sha256,
        "request_contract": request_contract_artifact,
        "request_row": request_row_artifact,
        "build_receipt": build_artifact,
        "materialization_receipt": materialization_artifact,
        "native_request": request_artifact,
        "condition_projection": projection_artifact,
        "request_proto_validation": {
            "transport": proto_validation_outcome,
            "process_log": proto_validation_log,
            "validator_binary_sha256": sha256_file(validator_path),
            "compute_stats": compute_stats_artifact,
            "compute_stats_observation": compute_stats_observation,
        },
        "native_result": result_artifact,
        "process_log": process_output_artifact,
        "transport": outcome,
        "returncode": outcome.get("returncode"),
        "timed_out": outcome.get("outer_timed_out") is True,
        "native_request_sha256": request_artifact["sha256"],
        "native_result_sha256": result_artifact["sha256"],
        "iterations": observation["iterations_done"],
        "simulator_error": observation["simulator_error"],
        "result_observation": observation,
    }
    receipt = {**identity, "receipt_sha256": canonical_sha256(identity)}
    receipt_artifact = store_content_addressed_json(
        output_root, "generation_receipts", receipt
    )
    return {**receipt, "artifact": receipt_artifact}


def validate_generation_receipt(
    receipt_path: Path,
    *,
    require_dvc_reconstruction: bool,
    slot_map: Sequence[int] | None = None,
) -> dict[str, Any]:
    receipt = _read_json_object(receipt_path, label="generation_receipt")
    artifact_root = receipt_path.resolve().parent.parent
    _require(receipt.get("schema") == GENERATION_RECEIPT_SCHEMA, "generation_receipt:schema")
    stored = str(receipt.get("receipt_sha256") or "")
    identity = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    _require(stored == canonical_sha256(identity), "generation_receipt:self_hash")
    _require(
        receipt.get("authority_scope") == "offline_denominator_only"
        and receipt.get("live_fixture_join_status")
        == "pending_physical_raw_capture"
        and bool(
            re.fullmatch(
                r"[0-9a-f]{64}", str(receipt.get("request_catalog_sha256") or "")
            )
        ),
        "generation_receipt:authority_scope",
    )
    if receipt.get("classification") == UNPUBLISHED_CLASSIFICATION:
        _require(
            bool(
                re.fullmatch(
                    r"[0-9a-f]{40}",
                    str(receipt.get("evidence_repository_admission_commit") or ""),
                )
            ),
            "generation_receipt:admission_commit",
        )
    request_path = verify_artifact(
        receipt.get("native_request") or {}, artifact_root=artifact_root, label="native_request"
    )
    result_path = verify_artifact(
        receipt.get("native_result") or {}, artifact_root=artifact_root, label="native_result"
    )
    projection_path = verify_artifact(
        receipt.get("condition_projection") or {},
        artifact_root=artifact_root,
        label="condition_projection",
    )
    proto_validation = receipt.get("request_proto_validation") or {}
    verify_process_evidence(
        proto_validation.get("transport") or {},
        proto_validation.get("process_log") or {},
        artifact_root=artifact_root,
        label="generation_proto_validation",
    )
    compute_stats_path = verify_artifact(
        proto_validation.get("compute_stats") or {},
        artifact_root=artifact_root,
        label="generation_compute_stats",
    )
    request_contract_path = verify_artifact(
        receipt.get("request_contract") or {},
        artifact_root=artifact_root,
        label="request_contract",
    )
    request_row_path = verify_artifact(
        receipt.get("request_row") or {},
        artifact_root=artifact_root,
        label="request_row",
    )
    build_record = receipt.get("build_receipt") or {}
    build_path = verify_artifact(
        build_record,
        artifact_root=artifact_root,
        label="generation_build_receipt",
    )
    fixture_path = verify_artifact(
        receipt.get("fixture_contract") or {},
        artifact_root=artifact_root,
        label="generation_fixture_contract",
    )
    fixture, fixture_sha256 = load_fixture_contract(fixture_path)
    _require(
        fixture_sha256
        == (receipt.get("fixture_contract") or {}).get("canonical_sha256"),
        "generation_fixture_contract:hash",
    )
    request = _read_json_object(request_path, label="native_request")
    compute_stats_observation = parse_compute_stats_validation(
        _read_json_object(compute_stats_path, label="compute_stats"),
        rotation=(_request_player(request).get("rotation") or {}),
    )
    _require(
        compute_stats_observation
        == proto_validation.get("compute_stats_observation"),
        "generation_compute_stats:observation",
    )
    request_contract = _read_json_object(
        request_contract_path, label="request_contract"
    )
    request_row = _read_json_object(request_row_path, label="request_row")
    _require(
        request_canonical_sha256(request_contract)
        == receipt.get("request_contract_sha256")
        == request_row.get("request_sha256"),
        "generation_request_contract:hash",
    )
    _require(
        request_row.get("request") == request_contract,
        "generation_request_contract:row_projection",
    )
    materialization_record = receipt.get("materialization_receipt") or {}
    materialization_path = verify_artifact(
        materialization_record,
        artifact_root=artifact_root,
        label="generation_materialization_receipt",
    )
    materialization, materialized_native_path, projected_again = (
        validate_materialization_receipt(
            materialization_path,
            request_row=request_row,
            fixture_contract=fixture,
            fixture_sha256=fixture_sha256,
            slot_map=list(slot_map) if slot_map is not None else load_slot_map(),
        )
    )
    _require(
        materialization.get("receipt_sha256")
        == materialization_record.get("receipt_sha256"),
        "generation_materialization_receipt:self_identity",
    )
    _require(
        materialized_native_path.read_bytes() == request_path.read_bytes(),
        "generation_materialization_receipt:native_request",
    )
    projection = _read_json_object(projection_path, label="condition_projection")
    _require(
        projection.get("projection_sha256")
        == canonical_sha256({key: value for key, value in projection.items() if key != "projection_sha256"}),
        "condition_projection:self_hash",
    )
    _require(projected_again == projection, "condition_projection:not_request_derived")
    validate_native_request_projection(projection, fixture)
    validate_projection_against_request_contract(projection, request_row, fixture)
    parsed_result = parse_native_result(_read_json_object(result_path, label="native_result"))
    _require(parsed_result == receipt.get("result_observation"), "generation_result_observation")
    verify_process_evidence(
        receipt.get("transport") or {},
        receipt.get("process_log") or {},
        artifact_root=artifact_root,
        label="generation_transport",
    )
    _require(
        receipt.get("returncode") == 0
        and receipt.get("timed_out") is False
        and receipt.get("iterations") == EXPECTED_ITERATIONS
        and receipt.get("simulator_error") is None
        and receipt.get("native_request_sha256") == sha256_file(request_path)
        and receipt.get("native_result_sha256") == sha256_file(result_path),
        "generation_flat_transport_identity",
    )
    build_receipt, binary_path = validate_build_receipt(
        build_path,
        expected_revision=str((fixture.get("authority") or {}).get("revision") or ""),
    )
    _require(
        build_record.get("receipt_sha256") == build_receipt.get("receipt_sha256")
        and build_record.get("binary_sha256") == sha256_file(binary_path)
        and proto_validation.get("validator_binary_sha256")
        == (build_receipt.get("request_validator") or {}).get("sha256")
        and receipt.get("source_revision") == build_receipt.get("provider_revision"),
        "generation_build_receipt:identity",
    )
    if require_dvc_reconstruction:
        raise WowsimsGenerationError(
            "generation_dvc_requires_separate_reconstruction_receipt"
        )
    return receipt


def audit_generation_reexecution(
    *,
    generation_receipt_path: Path,
    rebuilt_build_receipt_path: Path,
    timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Independently rerun a bundled request with a byte-identical fresh rebuild."""
    generation = validate_generation_receipt(
        generation_receipt_path, require_dvc_reconstruction=False
    )
    artifact_root = generation_receipt_path.resolve().parent.parent
    original_build_path = verify_artifact(
        generation.get("build_receipt") or {},
        artifact_root=artifact_root,
        label="audit:original_build_receipt",
    )
    original_build, original_binary = validate_build_receipt(
        original_build_path, expected_revision=str(generation.get("source_revision") or "")
    )
    rebuilt_build, rebuilt_binary = validate_build_receipt(
        rebuilt_build_receipt_path,
        expected_revision=str(generation.get("source_revision") or ""),
    )
    _require(
        sha256_file(original_binary)
        == sha256_file(rebuilt_binary)
        == generation.get("build_receipt", {}).get("binary_sha256"),
        "audit:rebuilt_binary_mismatch",
    )
    request_path = verify_artifact(
        generation.get("native_request") or {},
        artifact_root=artifact_root,
        label="audit:native_request",
    )
    expected_result_path = verify_artifact(
        generation.get("native_result") or {},
        artifact_root=artifact_root,
        label="audit:native_result",
    )
    compute_record = (
        (generation.get("request_proto_validation") or {}).get("compute_stats") or {}
    )
    expected_compute_path = verify_artifact(
        compute_record,
        artifact_root=artifact_root,
        label="audit:compute_stats",
    )
    rebuilt_root = rebuilt_build_receipt_path.resolve().parent.parent
    validator_path = verify_artifact(
        rebuilt_build.get("request_validator") or {},
        artifact_root=rebuilt_root,
        label="audit:rebuilt_validator",
    )
    with tempfile.TemporaryDirectory(prefix="wowsims-reexecution-") as temporary:
        temporary_root = Path(temporary)
        compute_path = temporary_root / "compute-stats.json"
        validator_outcome, validator_output = _run_capture(
            [str(validator_path), str(request_path), str(compute_path)],
            cwd=REPO_ROOT,
            env=dict(os.environ),
            timeout_seconds=60.0,
        )
        _require_normal_child(validator_outcome, label="audit:compute_stats")
        _require(
            compute_path.read_bytes() == expected_compute_path.read_bytes(),
            "audit:compute_stats_bytes",
        )
        result_path = temporary_root / "result.json"
        sim_outcome, sim_output = _run_capture(
            [
                str(rebuilt_binary),
                "sim",
                "--infile",
                str(request_path),
                "--outfile",
                str(result_path),
            ],
            cwd=REPO_ROOT,
            env=dict(os.environ),
            timeout_seconds=timeout_seconds,
        )
        _require_normal_child(sim_outcome, label="audit:sim")
        _require(result_path.is_file(), "audit:result_missing")
        rerun_bytes = result_path.read_bytes()
    expected_bytes = expected_result_path.read_bytes()
    if rerun_bytes != expected_bytes:
        _require(
            canonical_json_bytes(
                _json_object_from_bytes(rerun_bytes, label="audit:rerun_result")
            )
            == canonical_json_bytes(
                _json_object_from_bytes(expected_bytes, label="audit:expected_result")
            ),
            "audit:result_bytes",
        )
    observation = {
        "schema": "wowsims_generation_reexecution_audit_v1",
        "generation_receipt_sha256": generation["receipt_sha256"],
        "source_revision": generation["source_revision"],
        "rebuilt_binary_sha256": sha256_file(rebuilt_binary),
        "native_request_sha256": sha256_file(request_path),
        "native_result_sha256": hashlib.sha256(rerun_bytes).hexdigest(),
        "canonical_result_sha256": canonical_sha256(
            _json_object_from_bytes(rerun_bytes, label="audit:rerun_result")
        ),
        "compute_stats_sha256": sha256_file(expected_compute_path),
        "validator_transport": validator_outcome,
        "validator_output_sha256": hashlib.sha256(validator_output).hexdigest(),
        "validator_output_byte_count": len(validator_output),
        "validator_output_utf8": validator_output.decode("utf-8"),
        "sim_transport": sim_outcome,
        "sim_output_sha256": hashlib.sha256(sim_output).hexdigest(),
        "sim_output_byte_count": len(sim_output),
        "sim_output_utf8": sim_output.decode("utf-8"),
        "byte_identical_rebuild": original_build["binary_sha256"]
        == rebuilt_build["binary_sha256"],
        "canonical_result_identical": True,
    }
    return {**observation, "observation_sha256": canonical_sha256(observation)}


def parse_dvc_pointer(
    pointer_bytes: bytes,
    *,
    pointer_relative_path: str,
    expected_bundle_root: str,
) -> dict[str, Any]:
    pointer_path = Path(pointer_relative_path)
    bundle_path = Path(expected_bundle_root)
    for label, path in (("pointer", pointer_path), ("bundle", bundle_path)):
        _require(
            str(path) and not path.is_absolute() and ".." not in path.parts,
            f"dvc_pointer:{label}_path",
        )
    _require(pointer_path.suffix == ".dvc", "dvc_pointer:suffix")
    try:
        payload = yaml.safe_load(pointer_bytes)
    except yaml.YAMLError as exc:
        raise WowsimsGenerationError("dvc_pointer:yaml") from exc
    _require(isinstance(payload, Mapping), "dvc_pointer:shape")
    outs = payload.get("outs") or []
    _require(isinstance(outs, list) and len(outs) == 1, "dvc_pointer:out_count")
    out = outs[0]
    _require(isinstance(out, Mapping), "dvc_pointer:out")
    out_path = Path(str(out.get("path") or ""))
    _require(
        str(out_path) and not out_path.is_absolute() and ".." not in out_path.parts,
        "dvc_pointer:out_path",
    )
    resolved_out = Path(os.path.normpath((pointer_path.parent / out_path).as_posix()))
    _require(resolved_out == bundle_path, "dvc_pointer:bundle_root")
    digest_keys = [key for key in ("md5", "etag", "checksum") if out.get(key)]
    _require(len(digest_keys) == 1, "dvc_pointer:out_digest")
    normalized_out = {
        "path": out_path.as_posix(),
        "digest_kind": digest_keys[0],
        "digest": str(out[digest_keys[0]]),
        "size": int(out.get("size") or 0),
        "nfiles": int(out.get("nfiles") or 0),
    }
    _require(normalized_out["size"] > 0, "dvc_pointer:out_size")
    observation = {
        "path": pointer_path.as_posix(),
        "sha256": hashlib.sha256(pointer_bytes).hexdigest(),
        "byte_count": len(pointer_bytes),
        "bundle_root": bundle_path.as_posix(),
        "out": normalized_out,
    }
    return {**observation, "observation_sha256": canonical_sha256(observation)}


def validate_dvc_bundle_pre_pull(
    checkout: Path, *, bundle_relative: Path
) -> dict[str, Any]:
    """Prove a DVC out is absent, Git-untracked, and ignored before hydration."""
    _require(
        str(bundle_relative)
        and not bundle_relative.is_absolute()
        and ".." not in bundle_relative.parts,
        "dvc:bundle_pre_pull_path",
    )
    root = checkout.resolve()
    bundle_path = root / bundle_relative
    tracked = subprocess.run(
        [
            "git",
            "ls-files",
            "--",
            bundle_relative.as_posix(),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    ignored = subprocess.run(
        [
            "git",
            "check-ignore",
            "-q",
            "--no-index",
            (bundle_relative / ".dvc-hydration-probe").as_posix(),
        ],
        cwd=root,
        check=False,
    )
    _require(
        not os.path.lexists(bundle_path)
        and tracked.stdout.strip() == ""
        and ignored.returncode == 0,
        "dvc:bundle_not_absent_untracked_ignored_before_pull",
    )
    observation = {
        "bundle_root": bundle_relative.as_posix(),
        "absent": True,
        "git_untracked": True,
        "git_ignored": True,
    }
    return {**observation, "observation_sha256": canonical_sha256(observation)}


def parse_fresh_build_log_identity(
    payload: bytes,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Derive the immutable fresh-build identity from retained CLI stdout."""
    build_log = _json_object_from_bytes(payload, label="fresh_rebuild_log")
    artifact = build_log.get("artifact") or {}
    receipt_payload = {
        key: value for key, value in build_log.items() if key != "artifact"
    }
    receipt_bytes = canonical_json_bytes(receipt_payload)
    receipt_identity = {
        key: value for key, value in receipt_payload.items() if key != "receipt_sha256"
    }
    relative = Path(str(artifact.get("path") or ""))
    _require(
        receipt_payload.get("schema") == BUILD_RECEIPT_SCHEMA
        and receipt_payload.get("receipt_sha256")
        == canonical_sha256(receipt_identity)
        and str(relative)
        and not relative.is_absolute()
        and ".." not in relative.parts
        and artifact.get("sha256") == hashlib.sha256(receipt_bytes).hexdigest()
        and int(artifact.get("byte_count", -1)) == len(receipt_bytes),
        "fresh_rebuild_log:identity",
    )
    identity = {
        "build_receipt_artifact": {
            "path": relative.as_posix(),
            "sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "byte_count": len(receipt_bytes),
        },
        "receipt_sha256": str(receipt_payload.get("receipt_sha256") or ""),
        "binary_sha256": str(receipt_payload.get("binary_sha256") or ""),
        "provider_revision": str(receipt_payload.get("provider_revision") or ""),
    }
    return build_log, identity


def reconstruct_generation_with_dvc(
    *,
    repository_url: str,
    repository_revision: str,
    dvc_target: str,
    bundle_root: str,
    generation_receipt_relative_paths: Sequence[str],
    original_repository_root: Path,
    output_root: Path,
    dvc_binary: Path,
    go_binary: Path,
    protoc_binary: Path,
    protoc_gen_go_binary: Path,
    timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Fresh-clone, DVC-pull, rebuild once, and reexecute the full 16-spec cohort."""
    revision = repository_revision.strip()
    _require(bool(re.fullmatch(r"[0-9a-f]{40}", revision)), "dvc:revision")
    receipt_relatives = [Path(value) for value in generation_receipt_relative_paths]
    _require(len(receipt_relatives) == 16, "dvc:generation_receipt_count")
    _require(len(set(receipt_relatives)) == 16, "dvc:generation_receipt_duplicate")
    target_relative = Path(dvc_target)
    bundle_relative = Path(bundle_root)
    for label, relative in (
        [("dvc:target", target_relative), ("dvc:bundle", bundle_relative)]
        + [("dvc:generation_receipt", value) for value in receipt_relatives]
    ):
        _require(
            str(relative)
            and not relative.is_absolute()
            and ".." not in relative.parts,
            f"{label}:unsafe_path",
        )
    _require(target_relative.suffix == ".dvc", "dvc:target_not_pointer")
    original_root = original_repository_root.resolve()
    _require(
        _git_output(original_root, ["rev-parse", "HEAD"]) == revision,
        "dvc:original_repository_revision",
    )
    _require(
        _git_output(original_root, ["status", "--porcelain=v1", "--untracked-files=all"])
        == "",
        "dvc:original_repository_dirty",
    )
    _require(
        _normalized_repository_url(_git_output(original_root, ["remote", "get-url", "origin"]))
        == _normalized_repository_url(repository_url),
        "dvc:repository_url",
    )
    pointer_bytes = _checked_source_bytes(
        original_root,
        target_relative.as_posix(),
        expected_revision=revision,
        label="dvc_pointer",
    )
    pointer_observation = parse_dvc_pointer(
        pointer_bytes,
        pointer_relative_path=target_relative.as_posix(),
        expected_bundle_root=bundle_relative.as_posix(),
    )
    for receipt_relative in receipt_relatives:
        try:
            receipt_relative.relative_to(bundle_relative)
        except ValueError as exc:
            raise WowsimsGenerationError("dvc:generation_receipt_outside_bundle") from exc
    output_resolved = output_root.resolve()
    bundle_resolved = original_root / bundle_relative
    try:
        output_resolved.relative_to(bundle_resolved)
    except ValueError:
        pass
    else:
        raise WowsimsGenerationError("dvc:receipt_cycle_output_inside_bundle")
    original_receipts: list[tuple[Path, dict[str, Any], bytes]] = []
    for receipt_relative in receipt_relatives:
        original_receipt_path = original_root / receipt_relative
        original_receipt = validate_generation_receipt(
            original_receipt_path, require_dvc_reconstruction=False
        )
        original_receipts.append(
            (original_receipt_path, original_receipt, original_receipt_path.read_bytes())
        )
    original_receipts.sort(key=lambda value: str(value[1].get("target_spec") or ""))
    _require(
        len({str(value[1].get("target_spec") or "") for value in original_receipts})
        == 16,
        "dvc:generation_target_spec_cohort",
    )
    cohort_identities = {
        (
            str((receipt.get("fixture_contract") or {}).get("canonical_sha256") or ""),
            str((receipt.get("build_receipt") or {}).get("binary_sha256") or ""),
            str(receipt.get("request_catalog_sha256") or ""),
            str(receipt.get("evidence_repository_admission_commit") or ""),
            str(receipt.get("source_revision") or ""),
        )
        for _, receipt, _ in original_receipts
    }
    _require(len(cohort_identities) == 1, "dvc:generation_cohort_identity")
    original_receipt_path, original_receipt, _ = original_receipts[0]
    original_artifact_root = original_receipt_path.parent.parent
    original_build_path = verify_artifact(
        original_receipt.get("build_receipt") or {},
        artifact_root=original_artifact_root,
        label="dvc:original_build_receipt",
    )
    original_build, _ = validate_build_receipt(
        original_build_path,
        expected_revision=str(original_receipt.get("source_revision") or ""),
    )
    for name, binary in (
        ("go", go_binary),
        ("protoc", protoc_binary),
        ("protoc_gen_go", protoc_gen_go_binary),
    ):
        _require(
            sha256_file(binary) == ((original_build.get("tools") or {}).get(name) or {}).get("sha256"),
            f"dvc:rebuild_tool:{name}",
        )
    local_auth_path = original_root / ".dvc/config.local"
    _require(local_auth_path.is_file(), "dvc:local_auth_config_missing")
    local_auth_bytes = local_auth_path.read_bytes()
    _require(
        bool(local_auth_bytes) and len(local_auth_bytes) <= 1024 * 1024,
        "dvc:local_auth_config_size",
    )
    env = dict(os.environ)
    env.pop("DVC_CACHE_DIR", None)
    env.pop("DVC_CACHE_TYPE", None)
    logs: dict[str, dict[str, Any]] = {}
    cache_isolation: dict[str, Any] = {}
    cloud_status_classification = ""
    fresh_checkout_clean_before_and_after = False
    targeted_eviction_complete = False
    reexecution_audits: list[dict[str, Any]] = []
    fresh_materialization_audits: list[dict[str, Any]] = []
    fresh_rebuild_identity: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="wowsims-dvc-reconstruct-") as temporary:
        clone_path = Path(temporary) / "repository"
        isolated_cache = Path(temporary) / "isolated-dvc-cache"
        clone_outcome, clone_output = _run_capture(
            ["git", "clone", "--no-checkout", repository_url, str(clone_path)],
            cwd=Path(temporary),
            env=env,
            timeout_seconds=timeout_seconds,
        )
        _require_normal_child(clone_outcome, label="dvc_git_clone")
        logs["git_clone"] = {
            **store_content_addressed_bytes(
                output_root, "process_logs", clone_output, suffix=".log"
            ),
            "transport": clone_outcome,
        }
        checkout_outcome, checkout_output = _run_capture(
            ["git", "checkout", "--detach", revision],
            cwd=clone_path,
            env=env,
            timeout_seconds=timeout_seconds,
        )
        _require_normal_child(checkout_outcome, label="dvc_git_checkout")
        logs["git_checkout"] = {
            **store_content_addressed_bytes(
                output_root, "process_logs", checkout_output, suffix=".log"
            ),
            "transport": checkout_outcome,
        }
        _require(_git_output(clone_path, ["rev-parse", "HEAD"]) == revision, "dvc:checkout")
        _require(
            _normalized_repository_url(_git_output(clone_path, ["remote", "get-url", "origin"]))
            == _normalized_repository_url(repository_url),
            "dvc:clone_repository_url",
        )
        cloned_pointer_path = clone_path / target_relative
        _require(
            cloned_pointer_path.read_bytes() == pointer_bytes,
            "dvc:cloned_pointer_bytes",
        )
        _require(
            parse_dvc_pointer(
                cloned_pointer_path.read_bytes(),
                pointer_relative_path=target_relative.as_posix(),
                expected_bundle_root=bundle_relative.as_posix(),
            )
            == pointer_observation,
            "dvc:cloned_pointer_semantics",
        )
        before_status = _git_output(
            clone_path, ["status", "--porcelain=v1", "--untracked-files=all"]
        )
        _require(before_status == "", "dvc:fresh_checkout_dirty")
        cloned_bundle_path = clone_path / bundle_relative
        bundle_pre_pull = validate_dvc_bundle_pre_pull(
            clone_path, bundle_relative=bundle_relative
        )
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", ".dvc/config.local"],
            cwd=clone_path,
            check=False,
        )
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", ".dvc/config.local"],
            cwd=clone_path,
            check=False,
            capture_output=True,
        )
        _require(
            ignored.returncode == 0 and tracked.returncode != 0,
            "dvc:local_auth_config_not_safely_ignored",
        )
        destination_auth = clone_path / ".dvc/config.local"
        _write_exact(destination_auth, local_auth_bytes)
        destination_auth.chmod(0o600)
        isolated_cache.mkdir(parents=True, exist_ok=False)
        _require(not any(isolated_cache.iterdir()), "dvc:isolated_cache_not_empty")
        cache_outcome, cache_output = _run_capture(
            [
                str(dvc_binary.resolve()),
                "config",
                "--local",
                "cache.dir",
                str(isolated_cache.resolve()),
            ],
            cwd=clone_path,
            env=env,
            timeout_seconds=60.0,
        )
        _require_normal_child(cache_outcome, label="dvc_cache_config")
        logs["dvc_cache_config"] = {
            **store_content_addressed_bytes(
                output_root, "process_logs", cache_output, suffix=".log"
            ),
            "transport": cache_outcome,
        }
        configured_cache = subprocess.run(
            [str(dvc_binary.resolve()), "config", "--local", "cache.dir"],
            cwd=clone_path,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        _require(
            Path(configured_cache).resolve() == isolated_cache.resolve(),
            "dvc:isolated_cache_config_mismatch",
        )
        cache_isolation = {
            "shared_cache_disabled": True,
            "initial_entry_count": 0,
            "local_override_verified": True,
            "bundle_absent_untracked_and_ignored_before_pull": True,
            "bundle_pre_pull_observation_sha256": bundle_pre_pull[
                "observation_sha256"
            ],
            "bundle_real_directory_after_pull": True,
            "temporary_cache_evicted_after_validation": True,
        }
        pull_outcome, pull_output = _run_capture(
            [str(dvc_binary.resolve()), "pull", target_relative.as_posix()],
            cwd=clone_path,
            env=env,
            timeout_seconds=timeout_seconds,
        )
        _require_normal_child(pull_outcome, label="dvc_pull")
        logs["dvc_pull"] = {
            **store_content_addressed_bytes(
                output_root, "process_logs", pull_output, suffix=".log"
            ),
            "transport": pull_outcome,
        }
        bundle_cursor = clone_path.resolve()
        for part in bundle_relative.parts:
            bundle_cursor /= part
            _require(not bundle_cursor.is_symlink(), "dvc:reconstructed_bundle_symlink")
        try:
            cloned_bundle_path.resolve().relative_to(clone_path.resolve())
        except ValueError as exc:
            raise WowsimsGenerationError(
                "dvc:reconstructed_bundle_outside_checkout"
            ) from exc
        _require(cloned_bundle_path.is_dir(), "dvc:reconstructed_bundle_missing")
        cloud_outcome, cloud_output = _run_capture(
            [str(dvc_binary.resolve()), "status", "--cloud", target_relative.as_posix()],
            cwd=clone_path,
            env=env,
            timeout_seconds=timeout_seconds,
        )
        _require_normal_child(cloud_outcome, label="dvc_status_cloud")
        logs["dvc_status_cloud"] = {
            **store_content_addressed_bytes(
                output_root, "process_logs", cloud_output, suffix=".log"
            ),
            "transport": cloud_outcome,
        }
        cloud_status_text = cloud_output.decode("utf-8").strip()
        _require(
            cloud_status_text in {"", "Data and pipelines are up to date."},
            "dvc:cloud_status_not_clean",
        )
        cloud_status_classification = "clean_no_remote_divergence"
        reconstructed_receipts: list[tuple[Path, dict[str, Any]]] = []
        for source_path, source_receipt, source_bytes in original_receipts:
            relative = source_path.relative_to(original_root)
            reconstructed_receipt_path = clone_path / relative
            _require(
                reconstructed_receipt_path.is_file(),
                "dvc:reconstructed_receipt_missing",
            )
            _require(
                reconstructed_receipt_path.read_bytes() == source_bytes,
                "dvc:reconstructed_receipt_bytes",
            )
            reconstructed = validate_generation_receipt(
                reconstructed_receipt_path, require_dvc_reconstruction=False
            )
            _require(
                reconstructed == source_receipt,
                "dvc:reconstructed_receipt_semantics",
            )
            reconstructed_receipts.append((reconstructed_receipt_path, reconstructed))
        provider_source = (original_build.get("source") or {})
        provider_repository_url = str(provider_source.get("repository") or "")
        provider_revision = str(original_receipt.get("source_revision") or "")
        provider_checkout = Path(temporary) / "wowsims-provider"
        provider_clone_outcome, provider_clone_output = _run_capture(
            [
                "git",
                "clone",
                "--no-checkout",
                provider_repository_url,
                str(provider_checkout),
            ],
            cwd=Path(temporary),
            env=env,
            timeout_seconds=timeout_seconds,
        )
        _require_normal_child(provider_clone_outcome, label="dvc_provider_clone")
        logs["provider_git_clone"] = {
            **store_content_addressed_bytes(
                output_root, "process_logs", provider_clone_output, suffix=".log"
            ),
            "transport": provider_clone_outcome,
        }
        provider_checkout_outcome, provider_checkout_output = _run_capture(
            ["git", "checkout", "--detach", provider_revision],
            cwd=provider_checkout,
            env=env,
            timeout_seconds=timeout_seconds,
        )
        _require_normal_child(provider_checkout_outcome, label="dvc_provider_checkout")
        logs["provider_git_checkout"] = {
            **store_content_addressed_bytes(
                output_root, "process_logs", provider_checkout_output, suffix=".log"
            ),
            "transport": provider_checkout_outcome,
        }
        audit_build_root = Path(temporary) / "fresh-rebuilt-cli"
        build_command = [
            str(Path(sys.executable).resolve()),
            "-m",
            "tools.bot_ml.run_wowsims_exact_references",
            "build",
            "--checkout",
            str(provider_checkout),
            "--fixture-contract",
            str(clone_path / DEFAULT_FIXTURE_CONTRACT.relative_to(REPO_ROOT)),
            "--go-binary",
            str(go_binary.resolve()),
            "--protoc-binary",
            str(protoc_binary.resolve()),
            "--protoc-gen-go-binary",
            str(protoc_gen_go_binary.resolve()),
            "--output-root",
            str(audit_build_root),
        ]
        build_outcome, build_output = _run_capture(
            build_command,
            cwd=clone_path,
            env=env,
            timeout_seconds=timeout_seconds,
        )
        _require_normal_child(build_outcome, label="dvc_fresh_rebuild")
        logs["fresh_rebuild"] = {
            **store_content_addressed_bytes(
                output_root, "process_logs", build_output, suffix=".log"
            ),
            "transport": build_outcome,
        }
        rebuilt_receipts = sorted((audit_build_root / "build_receipts").glob("*.json"))
        _require(len(rebuilt_receipts) == 1, "dvc:fresh_build_receipt_count")
        rebuilt_receipt_path = rebuilt_receipts[0]
        rebuilt_receipt, rebuilt_binary = validate_build_receipt(
            rebuilt_receipt_path, expected_revision=provider_revision
        )
        _require(
            rebuilt_receipt.get("binary_sha256")
            == original_build.get("binary_sha256"),
            "dvc:fresh_rebuild_binary",
        )
        fresh_rebuild_identity = {
            "build_receipt_artifact": {
                "path": rebuilt_receipt_path.relative_to(
                    audit_build_root
                ).as_posix(),
                "sha256": sha256_file(rebuilt_receipt_path),
                "byte_count": rebuilt_receipt_path.stat().st_size,
            },
            "receipt_sha256": str(rebuilt_receipt.get("receipt_sha256") or ""),
            "binary_sha256": str(rebuilt_receipt.get("binary_sha256") or ""),
            "provider_revision": str(
                rebuilt_receipt.get("provider_revision") or ""
            ),
        }
        fresh_materialization_root = Path(temporary) / "fresh-materialized-requests"
        materialize_command = [
            str(Path(sys.executable).resolve()),
            "-m",
            "tools.bot_ml.run_wowsims_exact_references",
            "materialize-all",
            "--catalog",
            str(clone_path / DEFAULT_REQUEST_CATALOG.relative_to(REPO_ROOT)),
            "--checkout",
            str(provider_checkout),
            "--fixture-contract",
            str(clone_path / DEFAULT_FIXTURE_CONTRACT.relative_to(REPO_ROOT)),
            "--gear-profiles",
            str(clone_path / DEFAULT_GEAR_PROFILES.relative_to(REPO_ROOT)),
            "--output-root",
            str(fresh_materialization_root),
            "--build-receipt",
            str(rebuilt_receipt_path),
        ]
        materialize_outcome, materialize_output = _run_capture(
            materialize_command,
            cwd=clone_path,
            env=env,
            timeout_seconds=timeout_seconds,
        )
        _require_normal_child(
            materialize_outcome, label="dvc_fresh_materialize_all"
        )
        logs["fresh_materialize_all"] = {
            **store_content_addressed_bytes(
                output_root, "process_logs", materialize_output, suffix=".json"
            ),
            "transport": materialize_outcome,
        }
        materialize_summary = _json_object_from_bytes(
            materialize_output, label="dvc_fresh_materialize_all"
        )
        materialized_outputs = materialize_summary.get("outputs") or []
        _require(
            materialize_summary.get("ok") is True
            and isinstance(materialized_outputs, list)
            and len(materialized_outputs) == 16,
            "dvc:fresh_materialize_all_count",
        )
        materialized_by_spec = {
            str(value.get("target_spec") or ""): value
            for value in materialized_outputs
            if isinstance(value, Mapping)
        }
        _require(len(materialized_by_spec) == 16, "dvc:fresh_materialize_spec_set")
        for reconstructed_receipt_path, reconstructed in reconstructed_receipts:
            target_spec = str(reconstructed.get("target_spec") or "")
            fresh_row = materialized_by_spec.get(target_spec) or {}
            _require(
                fresh_row.get("pinned_protojson_validated") is True
                and fresh_row.get("pinned_compute_stats_validated") is True
                and ((fresh_row.get("compute_stats_observation") or {}).get(
                    "warning_or_error_count"
                ) == 0),
                f"dvc:fresh_materialize_validation:{target_spec}",
            )
            validation_process = (
                fresh_row.get("pinned_validation_process_evidence") or {}
            )
            validation_transport = validation_process.get("transport") or {}
            _require_normal_child(
                validation_transport,
                label=f"dvc:fresh_materialize_process:{target_spec}",
            )
            validation_output = str(
                validation_process.get("output_utf8") or ""
            ).encode("utf-8")
            _require(
                hashlib.sha256(validation_output).hexdigest()
                == validation_process.get("output_sha256")
                == validation_transport.get("output_sha256")
                and len(validation_output)
                == int(validation_process.get("output_byte_count", -1))
                == int(validation_transport.get("output_byte_count", -2)),
                f"dvc:fresh_materialize_process_output:{target_spec}",
            )
            fresh_native_path = verify_artifact(
                fresh_row.get("native_request") or {},
                artifact_root=fresh_materialization_root,
                label=f"dvc:fresh_native_request:{target_spec}",
            )
            fresh_receipt_path = verify_artifact(
                fresh_row.get("materialization_receipt") or {},
                artifact_root=fresh_materialization_root,
                label=f"dvc:fresh_materialization_receipt:{target_spec}",
            )
            reconstructed_root = reconstructed_receipt_path.parent.parent
            bundled_native_path = verify_artifact(
                reconstructed.get("native_request") or {},
                artifact_root=reconstructed_root,
                label=f"dvc:bundled_native_request:{target_spec}",
            )
            bundled_materialization_path = verify_artifact(
                reconstructed.get("materialization_receipt") or {},
                artifact_root=reconstructed_root,
                label=f"dvc:bundled_materialization_receipt:{target_spec}",
            )
            _require(
                fresh_native_path.read_bytes() == bundled_native_path.read_bytes()
                and fresh_receipt_path.read_bytes()
                == bundled_materialization_path.read_bytes(),
                f"dvc:fresh_materialization_bytes:{target_spec}",
            )
            fresh_materialization = _read_json_object(
                fresh_receipt_path,
                label=f"dvc:fresh_materialization_receipt:{target_spec}",
            )
            audit_identity = {
                "target_spec": target_spec,
                "native_request_sha256": sha256_file(fresh_native_path),
                "materialization_receipt_sha256": sha256_file(fresh_receipt_path),
                "source_assets_sha256": canonical_sha256(
                    fresh_materialization.get("source_assets") or {}
                ),
                "byte_identical_to_dvc_bundle": True,
                "pinned_compute_stats_warning_or_error_count": 0,
                "pinned_validation_process_evidence_sha256": canonical_sha256(
                    validation_process
                ),
            }
            fresh_materialization_audits.append(
                {
                    **audit_identity,
                    "observation_sha256": canonical_sha256(audit_identity),
                }
            )
        for reconstructed_receipt_path, reconstructed in reconstructed_receipts:
            target_spec = str(reconstructed.get("target_spec") or "")
            audit_command = [
                str(Path(sys.executable).resolve()),
                "-m",
                "tools.bot_ml.run_wowsims_exact_references",
                "audit-reexecute",
                "--generation-receipt",
                str(reconstructed_receipt_path),
                "--rebuilt-build-receipt",
                str(rebuilt_receipt_path),
            ]
            audit_outcome, audit_output = _run_capture(
                audit_command,
                cwd=clone_path,
                env=env,
                timeout_seconds=timeout_seconds,
            )
            _require_normal_child(
                audit_outcome, label=f"dvc_reexecution_audit:{target_spec}"
            )
            reexecution_audit = _json_object_from_bytes(
                audit_output, label=f"dvc_reexecution_audit:{target_spec}"
            )
            _require(
                reexecution_audit.get("generation_receipt_sha256")
                == reconstructed.get("receipt_sha256")
                and reexecution_audit.get("rebuilt_binary_sha256")
                == sha256_file(rebuilt_binary)
                and reexecution_audit.get("canonical_result_identical") is True,
                "dvc:reexecution_observation",
            )
            reexecution_audits.append(
                {"target_spec": target_spec, "audit": reexecution_audit}
            )
            logs[f"reexecution_audit:{target_spec}"] = {
                **store_content_addressed_bytes(
                    output_root, "process_logs", audit_output, suffix=".json"
                ),
                "transport": audit_outcome,
            }
        after_status = _git_output(
            clone_path, ["status", "--porcelain=v1", "--untracked-files=all"]
        )
        _require(after_status == "", "dvc:fresh_checkout_dirty_after_pull")
        fresh_checkout_clean_before_and_after = True

    targeted_eviction_complete = not clone_path.exists() and not isolated_cache.exists()
    _require(targeted_eviction_complete, "dvc:temporary_reconstruction_not_evicted")

    generation_artifacts = [
        {
            "target_spec": str(receipt.get("target_spec") or ""),
            "path": path.relative_to(original_root).as_posix(),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "byte_count": len(payload),
            "receipt_sha256": receipt["receipt_sha256"],
        }
        for path, receipt, payload in original_receipts
    ]
    identity = {
        "schema": DVC_RECONSTRUCTION_SCHEMA,
        "status": "published_and_freshly_reconstructed",
        "repository_url": repository_url,
        "repository_revision": revision,
        "dvc_target": target_relative.as_posix(),
        "bundle_root": bundle_relative.as_posix(),
        "dvc_pointer": pointer_observation,
        "generation_receipts": generation_artifacts,
        "dvc_binary": {
            "executable_name": dvc_binary.name,
            "sha256": sha256_file(dvc_binary),
            "version": _tool_version(dvc_binary, ["--version"]),
        },
        "process_evidence": logs,
        "cache_isolation": cache_isolation,
        "cloud_status_classification": cloud_status_classification,
        "fresh_checkout_clean_before_and_after": fresh_checkout_clean_before_and_after,
        "targeted_eviction_complete": targeted_eviction_complete,
        "fresh_recursive_reconstruction_verified": True,
        "fresh_rebuild_identity": fresh_rebuild_identity,
        "fresh_materialization_audits": sorted(
            fresh_materialization_audits,
            key=lambda value: str(value.get("target_spec") or ""),
        ),
        "fresh_rebuild_and_reexecution_audits": reexecution_audits,
    }
    receipt = {**identity, "receipt_sha256": canonical_sha256(identity)}
    artifact = store_content_addressed_json(
        output_root, "dvc_reconstruction_receipts", receipt
    )
    return {**receipt, "artifact": artifact}


def validate_dvc_reconstruction_receipt(
    receipt_path: Path,
    *,
    expected_generation_receipt_paths: Sequence[Path],
    expected_repository_root: Path,
    expected_repository_url: str,
    expected_repository_revision: str,
    expected_dvc_pointer_path: str,
    expected_bundle_root: str,
) -> dict[str, Any]:
    receipt = _read_json_object(receipt_path, label="dvc_reconstruction_receipt")
    _require(receipt.get("schema") == DVC_RECONSTRUCTION_SCHEMA, "dvc_receipt:schema")
    stored = str(receipt.get("receipt_sha256") or "")
    identity = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    _require(stored == canonical_sha256(identity), "dvc_receipt:self_hash")
    _require(
        receipt.get("status") == "published_and_freshly_reconstructed"
        and receipt.get("fresh_recursive_reconstruction_verified") is True,
        "dvc_receipt:status",
    )
    repository_root = expected_repository_root.resolve()
    generation_paths = [value.resolve() for value in expected_generation_receipt_paths]
    _require(len(generation_paths) == 16, "dvc_receipt:generation_count")
    generation_relatives = [value.relative_to(repository_root) for value in generation_paths]
    generations = receipt.get("generation_receipts") or []
    _require(isinstance(generations, list), "dvc_receipt:generation_receipts")
    _require(
        _normalized_repository_url(receipt.get("repository_url"))
        == _normalized_repository_url(expected_repository_url)
        == _normalized_repository_url(
            _git_output(repository_root, ["remote", "get-url", "origin"])
        )
        and receipt.get("repository_revision") == expected_repository_revision
        and receipt.get("dvc_target") == expected_dvc_pointer_path
        and receipt.get("bundle_root") == expected_bundle_root,
        "dvc_receipt:publication_domain",
    )
    _require(
        bool(re.fullmatch(r"[0-9a-f]{40}", expected_repository_revision)),
        "dvc_receipt:expected_revision",
    )
    pointer_bytes = subprocess.run(
        [
            "git",
            "-C",
            str(repository_root),
            "show",
            f"{expected_repository_revision}:{expected_dvc_pointer_path}",
        ],
        check=True,
        capture_output=True,
    ).stdout
    pointer_observation = parse_dvc_pointer(
        pointer_bytes,
        pointer_relative_path=expected_dvc_pointer_path,
        expected_bundle_root=expected_bundle_root,
    )
    _require(
        receipt.get("dvc_pointer") == pointer_observation,
        "dvc_receipt:pointer_identity",
    )
    bundle_relative = Path(expected_bundle_root)
    for generation_relative in generation_relatives:
        try:
            generation_relative.relative_to(bundle_relative)
        except ValueError as exc:
            raise WowsimsGenerationError("dvc_receipt:generation_outside_bundle") from exc
    try:
        receipt_path.resolve().relative_to(repository_root / bundle_relative)
    except ValueError:
        pass
    else:
        raise WowsimsGenerationError("dvc_receipt:receipt_cycle")
    expected_generations: dict[str, dict[str, Any]] = {}
    verified_generation_receipts: dict[str, dict[str, Any]] = {}
    verified_generation_paths: dict[str, Path] = {}
    for generation_path, generation_relative in zip(generation_paths, generation_relatives):
        verified = validate_generation_receipt(
            generation_path, require_dvc_reconstruction=False
        )
        target_spec = str(verified.get("target_spec") or "")
        _require(target_spec not in expected_generations, "dvc_receipt:generation_duplicate_spec")
        payload = generation_path.read_bytes()
        expected_generations[target_spec] = {
            "target_spec": target_spec,
            "path": generation_relative.as_posix(),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "byte_count": len(payload),
            "receipt_sha256": verified["receipt_sha256"],
        }
        verified_generation_receipts[target_spec] = verified
        verified_generation_paths[target_spec] = generation_path
    _require(
        sorted(generations, key=lambda value: str(value.get("target_spec") or ""))
        == [expected_generations[key] for key in sorted(expected_generations)],
        "dvc_receipt:generation_identity",
    )
    fixed_log_labels = (
        "git_clone",
        "git_checkout",
        "dvc_cache_config",
        "dvc_pull",
        "dvc_status_cloud",
        "provider_git_clone",
        "provider_git_checkout",
        "fresh_rebuild",
        "fresh_materialize_all",
    )
    audit_log_labels = tuple(
        f"reexecution_audit:{target_spec}" for target_spec in sorted(expected_generations)
    )
    _require(
        set(receipt.get("process_evidence") or {})
        == set(fixed_log_labels) | set(audit_log_labels),
        "dvc_receipt:process_evidence_set",
    )
    verified_process_logs: dict[str, Path] = {}
    for label in (*fixed_log_labels, *audit_log_labels):
        row = (receipt.get("process_evidence") or {}).get(label) or {}
        verified_process_logs[label] = verify_process_evidence(
            row.get("transport") or {},
            row,
            artifact_root=receipt_path.resolve().parent.parent,
            label=f"dvc_receipt:{label}",
        )
    cloud_status_text = verified_process_logs["dvc_status_cloud"].read_text(
        encoding="utf-8"
    ).strip()
    _require(
        cloud_status_text in {"", "Data and pipelines are up to date."}
        and receipt.get("cloud_status_classification")
        == "clean_no_remote_divergence",
        "dvc_receipt:cloud_status_output",
    )
    _, parsed_fresh_rebuild_identity = parse_fresh_build_log_identity(
        verified_process_logs["fresh_rebuild"].read_bytes()
    )
    fresh_materialize_log = _json_object_from_bytes(
        verified_process_logs["fresh_materialize_all"].read_bytes(),
        label="dvc_receipt:fresh_materialize_log",
    )
    fresh_materialize_outputs = fresh_materialize_log.get("outputs") or []
    _require(
        fresh_materialize_log.get("ok") is True
        and isinstance(fresh_materialize_outputs, list)
        and len(fresh_materialize_outputs) == 16,
        "dvc_receipt:fresh_materialize_log_count",
    )
    fresh_materialize_by_spec = {
        str(value.get("target_spec") or ""): value
        for value in fresh_materialize_outputs
        if isinstance(value, Mapping)
    }
    _require(
        len(fresh_materialize_by_spec) == 16
        and set(fresh_materialize_by_spec) == set(expected_generations),
        "dvc_receipt:fresh_materialize_log_spec_set",
    )
    for target_spec, value in fresh_materialize_by_spec.items():
        validation_process = value.get("pinned_validation_process_evidence") or {}
        validation_transport = validation_process.get("transport") or {}
        _require_normal_child(
            validation_transport,
            label=f"dvc_receipt:fresh_materialize_process:{target_spec}",
        )
        validation_output = str(
            validation_process.get("output_utf8") or ""
        ).encode("utf-8")
        _require(
            hashlib.sha256(validation_output).hexdigest()
            == validation_process.get("output_sha256")
            == validation_transport.get("output_sha256")
            and len(validation_output)
            == int(validation_process.get("output_byte_count", -1))
            == int(validation_transport.get("output_byte_count", -2)),
            f"dvc_receipt:fresh_materialize_process_output:{target_spec}",
        )
    process = receipt.get("process_evidence") or {}
    clone_transport = (process.get("git_clone") or {}).get("transport") or {}
    checkout_transport = (process.get("git_checkout") or {}).get("transport") or {}
    clone_cwd = str(checkout_transport.get("working_directory") or "")
    clone_parent = str(Path(clone_cwd).parent)
    _require(
        clone_transport.get("command")
        == ["git", "clone", "--no-checkout", expected_repository_url, clone_cwd]
        and clone_transport.get("working_directory") == clone_parent
        and checkout_transport.get("command")
        == ["git", "checkout", "--detach", expected_repository_revision]
        and (process.get("dvc_pull") or {}).get("transport", {}).get("command", [None])[-1]
        == expected_dvc_pointer_path
        and (process.get("dvc_status_cloud") or {}).get("transport", {}).get(
            "command", [None]
        )[-1]
        == expected_dvc_pointer_path
        and all(
            ((process.get(label) or {}).get("transport") or {}).get(
                "working_directory"
            )
            == clone_cwd
            for label in (
                "git_checkout",
                "dvc_cache_config",
                "dvc_pull",
                "dvc_status_cloud",
            )
        ),
        "dvc_receipt:transport_domain",
    )
    first_target_spec = sorted(verified_generation_receipts)[0]
    first_generation = verified_generation_receipts[first_target_spec]
    first_generation_root = verified_generation_paths[first_target_spec].parent.parent
    first_build_path = verify_artifact(
        first_generation.get("build_receipt") or {},
        artifact_root=first_generation_root,
        label="dvc_receipt:build_receipt",
    )
    first_build, _ = validate_build_receipt(
        first_build_path,
        expected_revision=str(first_generation.get("source_revision") or ""),
    )
    provider_source = first_build.get("source") or {}
    provider_clone_transport = (
        (process.get("provider_git_clone") or {}).get("transport") or {}
    )
    provider_checkout_transport = (
        (process.get("provider_git_checkout") or {}).get("transport") or {}
    )
    provider_checkout_cwd = str(provider_checkout_transport.get("working_directory") or "")
    provider_parent = str(Path(provider_checkout_cwd).parent)
    fresh_build_transport = (process.get("fresh_rebuild") or {}).get("transport") or {}
    fresh_build_command = fresh_build_transport.get("command") or []
    _require(
        provider_clone_transport.get("command")
        == [
            "git",
            "clone",
            "--no-checkout",
            str(provider_source.get("repository") or ""),
            provider_checkout_cwd,
        ]
        and provider_clone_transport.get("working_directory") == provider_parent
        and provider_checkout_transport.get("command")
        == [
            "git",
            "checkout",
            "--detach",
            str(first_generation.get("source_revision") or ""),
        ]
        and len(fresh_build_command) >= 16
        and fresh_build_command[1:4]
        == ["-m", "tools.bot_ml.run_wowsims_exact_references", "build"]
        and fresh_build_transport.get("working_directory") == clone_cwd
        and all(
            flag in fresh_build_command
            for flag in ("--checkout", "--fixture-contract", "--output-root")
        )
        and fresh_build_command[fresh_build_command.index("--checkout") + 1]
        == provider_checkout_cwd
        and fresh_build_command[fresh_build_command.index("--fixture-contract") + 1]
        == str(Path(clone_cwd) / DEFAULT_FIXTURE_CONTRACT.relative_to(REPO_ROOT)),
        "dvc_receipt:provider_rebuild_transport",
    )
    fresh_build_output_root = Path(
        fresh_build_command[fresh_build_command.index("--output-root") + 1]
    )
    fresh_build_receipt_relative = Path(
        str(
            (
                parsed_fresh_rebuild_identity.get("build_receipt_artifact") or {}
            ).get("path")
            or ""
        )
    )
    _require(
        str(fresh_build_receipt_relative)
        and not fresh_build_receipt_relative.is_absolute()
        and ".." not in fresh_build_receipt_relative.parts,
        "dvc_receipt:fresh_rebuild_receipt_path",
    )
    expected_fresh_rebuild_identity = parsed_fresh_rebuild_identity
    _require(
        receipt.get("fresh_rebuild_identity") == expected_fresh_rebuild_identity
        and expected_fresh_rebuild_identity["binary_sha256"]
        == first_build.get("binary_sha256")
        and expected_fresh_rebuild_identity["provider_revision"]
        == first_generation.get("source_revision"),
        "dvc_receipt:fresh_rebuild_cohort_identity",
    )
    expected_fresh_build_receipt_path = str(
        fresh_build_output_root / fresh_build_receipt_relative
    )
    fresh_materialize_transport = (
        (process.get("fresh_materialize_all") or {}).get("transport") or {}
    )
    fresh_materialize_command = fresh_materialize_transport.get("command") or []
    _require(
        fresh_materialize_transport.get("working_directory") == clone_cwd
        and fresh_materialize_command[1:4]
        == [
            "-m",
            "tools.bot_ml.run_wowsims_exact_references",
            "materialize-all",
        ]
        and all(
            flag in fresh_materialize_command
            for flag in (
                "--catalog",
                "--checkout",
                "--fixture-contract",
                "--gear-profiles",
                "--output-root",
                "--build-receipt",
            )
        )
        and fresh_materialize_command[
            fresh_materialize_command.index("--catalog") + 1
        ]
        == str(Path(clone_cwd) / DEFAULT_REQUEST_CATALOG.relative_to(REPO_ROOT))
        and fresh_materialize_command[
            fresh_materialize_command.index("--checkout") + 1
        ]
        == provider_checkout_cwd
        and fresh_materialize_command[
            fresh_materialize_command.index("--fixture-contract") + 1
        ]
        == str(Path(clone_cwd) / DEFAULT_FIXTURE_CONTRACT.relative_to(REPO_ROOT))
        and fresh_materialize_command[
            fresh_materialize_command.index("--gear-profiles") + 1
        ]
        == str(Path(clone_cwd) / DEFAULT_GEAR_PROFILES.relative_to(REPO_ROOT))
        and fresh_materialize_command[
            fresh_materialize_command.index("--build-receipt") + 1
        ]
        == expected_fresh_build_receipt_path,
        "dvc_receipt:fresh_materialize_transport",
    )
    materialization_audit_rows = receipt.get("fresh_materialization_audits") or []
    _require(
        isinstance(materialization_audit_rows, list)
        and len(materialization_audit_rows) == 16,
        "dvc_receipt:fresh_materialization_audit_count",
    )
    materialization_audits = {
        str(value.get("target_spec") or ""): value
        for value in materialization_audit_rows
        if isinstance(value, Mapping)
    }
    _require(
        set(materialization_audits) == set(expected_generations),
        "dvc_receipt:fresh_materialization_spec_set",
    )
    for target_spec, generation in verified_generation_receipts.items():
        generation_root = verified_generation_paths[target_spec].parent.parent
        bundled_native = verify_artifact(
            generation.get("native_request") or {},
            artifact_root=generation_root,
            label=f"dvc_receipt:materialized_native:{target_spec}",
        )
        bundled_materialization = verify_artifact(
            generation.get("materialization_receipt") or {},
            artifact_root=generation_root,
            label=f"dvc_receipt:materialization_receipt:{target_spec}",
        )
        materialization_payload = _read_json_object(
            bundled_materialization,
            label=f"dvc_receipt:materialization_payload:{target_spec}",
        )
        expected_audit_identity = {
            "target_spec": target_spec,
            "native_request_sha256": sha256_file(bundled_native),
            "materialization_receipt_sha256": sha256_file(
                bundled_materialization
            ),
            "source_assets_sha256": canonical_sha256(
                materialization_payload.get("source_assets") or {}
            ),
            "byte_identical_to_dvc_bundle": True,
            "pinned_compute_stats_warning_or_error_count": 0,
            "pinned_validation_process_evidence_sha256": canonical_sha256(
                (
                    fresh_materialize_by_spec[target_spec].get(
                        "pinned_validation_process_evidence"
                    )
                    or {}
                )
            ),
        }
        _require(
            materialization_audits[target_spec]
            == {
                **expected_audit_identity,
                "observation_sha256": canonical_sha256(expected_audit_identity),
            },
            f"dvc_receipt:fresh_materialization_identity:{target_spec}",
        )
    audit_rows = receipt.get("fresh_rebuild_and_reexecution_audits") or []
    _require(isinstance(audit_rows, list) and len(audit_rows) == 16, "dvc_receipt:audit_count")
    audits_by_spec = {
        str(value.get("target_spec") or ""): value.get("audit") or {}
        for value in audit_rows
        if isinstance(value, Mapping)
    }
    _require(set(audits_by_spec) == set(expected_generations), "dvc_receipt:audit_spec_set")
    for target_spec, expected_generation in expected_generations.items():
        audit = audits_by_spec[target_spec]
        audit_identity = {
            key: value for key, value in audit.items() if key != "observation_sha256"
        }
        _require(
            audit.get("observation_sha256") == canonical_sha256(audit_identity)
            and audit.get("generation_receipt_sha256")
            == expected_generation["receipt_sha256"]
            and audit.get("canonical_result_identical") is True
            and audit.get("byte_identical_rebuild") is True,
            f"dvc_receipt:audit_identity:{target_spec}",
        )
        validator_output = str(audit.get("validator_output_utf8") or "").encode(
            "utf-8"
        )
        sim_output = str(audit.get("sim_output_utf8") or "").encode("utf-8")
        _require(
            hashlib.sha256(validator_output).hexdigest()
            == audit.get("validator_output_sha256")
            and len(validator_output)
            == int(audit.get("validator_output_byte_count", -1))
            and hashlib.sha256(sim_output).hexdigest()
            == audit.get("sim_output_sha256")
            and len(sim_output) == int(audit.get("sim_output_byte_count", -1)),
            f"dvc_receipt:audit_process_output:{target_spec}",
        )
        audit_transport = (
            (process.get(f"reexecution_audit:{target_spec}") or {}).get("transport")
            or {}
        )
        audit_command = audit_transport.get("command") or []
        _require(
            audit_transport.get("working_directory") == clone_cwd
            and audit_command[1:4]
            == [
                "-m",
                "tools.bot_ml.run_wowsims_exact_references",
                "audit-reexecute",
            ]
            and all(
                flag in audit_command
                for flag in ("--generation-receipt", "--rebuilt-build-receipt")
            )
            and audit_command[audit_command.index("--generation-receipt") + 1]
            == str(Path(clone_cwd) / expected_generation["path"])
            and audit_command[
                audit_command.index("--rebuilt-build-receipt") + 1
            ]
            == expected_fresh_build_receipt_path
            and audit.get("rebuilt_binary_sha256")
            == first_build.get("binary_sha256")
            and (audit.get("validator_transport") or {}).get("working_directory")
            == clone_cwd
            and (audit.get("sim_transport") or {}).get("working_directory")
            == clone_cwd
            and (audit.get("sim_transport") or {}).get("command", [None])[0]
            == fresh_build_command[
                fresh_build_command.index("--output-root") + 1
            ]
            + "/binaries/"
            + str(audit.get("rebuilt_binary_sha256") or "")
            + ".wowsimcli",
            f"dvc_receipt:audit_transport:{target_spec}",
        )
    isolation = receipt.get("cache_isolation") or {}
    expected_bundle_pre_pull = {
        "bundle_root": expected_bundle_root,
        "absent": True,
        "git_untracked": True,
        "git_ignored": True,
    }
    _require(
        isolation
        == {
            "shared_cache_disabled": True,
            "initial_entry_count": 0,
            "local_override_verified": True,
            "bundle_absent_untracked_and_ignored_before_pull": True,
            "bundle_pre_pull_observation_sha256": canonical_sha256(
                expected_bundle_pre_pull
            ),
            "bundle_real_directory_after_pull": True,
            "temporary_cache_evicted_after_validation": True,
        }
        and receipt.get("cloud_status_classification")
        == "clean_no_remote_divergence"
        and receipt.get("fresh_checkout_clean_before_and_after") is True
        and receipt.get("targeted_eviction_complete") is True,
        "dvc_receipt:remote_reconstruction_proof",
    )
    return receipt


def _repo_artifact_record(path: Path, *, repository_root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(repository_root.resolve())
    except ValueError as exc:
        raise WowsimsGenerationError("promotion:artifact_outside_repository") from exc
    _require(resolved.is_file(), "promotion:artifact_missing")
    return {
        "path": relative.as_posix(),
        "sha256": sha256_file(resolved),
        "byte_count": resolved.stat().st_size,
    }


def _require_committed_head_file(
    path: Path, *, repository_root: Path, label: str
) -> None:
    root = repository_root.resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise WowsimsGenerationError(f"{label}:outside_repository") from exc
    cursor = root
    for part in relative.parts:
        cursor /= part
        _require(not cursor.is_symlink(), f"{label}:symlink")
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", relative.as_posix()],
        check=False,
        capture_output=True,
    )
    _require(tracked.returncode == 0, f"{label}:not_tracked")
    try:
        committed = subprocess.run(
            ["git", "-C", str(root), "show", f"HEAD:{relative.as_posix()}"],
            check=True,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise WowsimsGenerationError(f"{label}:not_at_head") from exc
    _require(resolved.read_bytes() == committed, f"{label}:head_bytes")


def promote_generated_references(
    *,
    catalog_path: Path,
    promotion_index_path: Path,
    output_path: Path,
    repository_root: Path = REPO_ROOT,
    check: bool = False,
) -> dict[str, Any]:
    """Promote all 16 only from native+DVC-verified receipts, idempotently."""
    manifest = load_request_manifest(catalog_path)
    validate_request_manifest(manifest, root=repository_root, verify_generated_artifacts=True)
    pending_manifest = pending_catalog_projection(manifest)
    index = _read_json_object(promotion_index_path, label="promotion_index")
    _require(index.get("schema") == PROMOTION_INDEX_SCHEMA, "promotion:index_schema")
    index_hash = str(index.get("index_sha256") or "")
    index_identity = {key: value for key, value in index.items() if key != "index_sha256"}
    _require(index_hash == canonical_sha256(index_identity), "promotion:index_hash")
    publication = index.get("publication_domain") or {}
    _require(
        set(publication)
        == {
            "repository_url",
            "repository_revision",
            "dvc_pointer_path",
            "bundle_root",
            "pending_request_catalog_sha256",
            "control_plane_policy",
        }
        and publication.get("control_plane_policy")
        == "commit_a_pointer_then_commit_b_reconstruction_receipt_and_promotion",
        "promotion:publication_domain",
    )
    _require(
        canonical_sha256(pending_manifest)
        == publication.get("pending_request_catalog_sha256"),
        "promotion:pending_catalog_identity",
    )
    _require(
        _normalized_repository_url(publication.get("repository_url"))
        == _normalized_repository_url(
            _git_output(repository_root, ["remote", "get-url", "origin"])
        ),
        "promotion:repository_url",
    )
    ancestor = subprocess.run(
        [
            "git",
            "-C",
            str(repository_root),
            "merge-base",
            "--is-ancestor",
            str(publication.get("repository_revision") or ""),
            "HEAD",
        ],
        check=False,
    )
    _require(ancestor.returncode == 0, "promotion:commit_a_not_ancestor")
    if check:
        head_revision = _git_output(repository_root, ["rev-parse", "HEAD"])
        _require(
            head_revision != str(publication.get("repository_revision") or "")
            and _git_output(
                repository_root,
                ["status", "--porcelain=v1", "--untracked-files=all"],
            )
            == "",
            "promotion:commit_b_not_clean_distinct_head",
        )
    entries = index.get("entries") or []
    _require(isinstance(entries, list) and len(entries) == 16, "promotion:entry_count")
    by_spec: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        _require(isinstance(entry, Mapping), "promotion:entry")
        target_spec = str(entry.get("target_spec") or "")
        _require(target_spec and target_spec not in by_spec, "promotion:duplicate_spec")
        by_spec[target_spec] = entry
    expected_specs = {str(row["target_spec"]) for row in pending_manifest["requests"]}
    _require(set(by_spec) == expected_specs, "promotion:spec_set")

    generation_paths_by_spec: dict[str, Path] = {}
    dvc_paths_by_spec: dict[str, Path] = {}
    for target_spec, entry in by_spec.items():
        generation_paths_by_spec[target_spec] = verify_artifact(
            entry.get("generation_receipt") or {},
            artifact_root=repository_root,
            label=f"promotion:{target_spec}:generation_receipt",
        )
        dvc_paths_by_spec[target_spec] = verify_artifact(
            entry.get("dvc_reconstruction_receipt") or {},
            artifact_root=repository_root,
            label=f"promotion:{target_spec}:dvc_receipt",
        )
    common_dvc_paths = {value.resolve() for value in dvc_paths_by_spec.values()}
    _require(len(common_dvc_paths) == 1, "promotion:common_dvc_reconstruction_receipt")
    common_dvc_path = next(iter(common_dvc_paths))
    validate_dvc_reconstruction_receipt(
        common_dvc_path,
        expected_generation_receipt_paths=[
            generation_paths_by_spec[target_spec] for target_spec in sorted(expected_specs)
        ],
        expected_repository_root=repository_root,
        expected_repository_url=str(publication["repository_url"]),
        expected_repository_revision=str(publication["repository_revision"]),
        expected_dvc_pointer_path=str(publication["dvc_pointer_path"]),
        expected_bundle_root=str(publication["bundle_root"]),
    )

    promoted = copy.deepcopy(pending_manifest)
    cohort_fixture_hashes: set[str] = set()
    cohort_build_hashes: set[str] = set()
    cohort_catalog_hashes: set[str] = set()
    cohort_admission_commits: set[str] = set()
    for row in promoted["requests"]:
        target_spec = str(row["target_spec"])
        entry = by_spec[target_spec]
        generation_path = generation_paths_by_spec[target_spec]
        dvc_path = dvc_paths_by_spec[target_spec]
        generation = validate_generation_receipt(
            generation_path, require_dvc_reconstruction=False
        )
        _require(
            generation.get("target_spec") == target_spec
            and generation.get("request_contract_sha256") == row.get("request_sha256")
            and generation.get("source_revision")
            == pending_manifest.get("provider_revision")
            and generation.get("classification") == UNPUBLISHED_CLASSIFICATION,
            f"promotion:{target_spec}:generation_identity",
        )
        cohort_fixture_hashes.add(
            str((generation.get("fixture_contract") or {}).get("canonical_sha256") or "")
        )
        cohort_build_hashes.add(
            str((generation.get("build_receipt") or {}).get("binary_sha256") or "")
        )
        cohort_catalog_hashes.add(str(generation.get("request_catalog_sha256") or ""))
        cohort_admission_commits.add(
            str(generation.get("evidence_repository_admission_commit") or "")
        )
        artifact_root = generation_path.resolve().parent.parent

        def nested_artifact(name: str) -> dict[str, Any]:
            value = generation.get(name) or {}
            relative = Path(str(value.get("path") or ""))
            _require(
                not relative.is_absolute() and ".." not in relative.parts,
                f"promotion:{target_spec}:{name}:path",
            )
            return _repo_artifact_record(
                artifact_root / relative, repository_root=repository_root
            )

        dps = float((generation.get("result_observation") or {}).get("dps") or 0.0)
        _require(math.isfinite(dps) and dps > 0.0, f"promotion:{target_spec}:dps")
        result_key = (
            f"generated:{target_spec}:"
            f"{str((generation.get('native_result') or {}).get('sha256') or '')}"
        )
        row["result"] = {
            "status": "generated_verified",
            "result_key": result_key,
            "dps": dps,
            "authority_scope": "offline_denominator_only",
            "live_fixture_join_status": "pending_physical_raw_capture",
            "publication_domain": copy.deepcopy(publication),
            "artifacts": {
                "request_contract_sha256": row["request_sha256"],
                "native_request": nested_artifact("native_request"),
                "native_result": nested_artifact("native_result"),
                "build_receipt": nested_artifact("build_receipt"),
                "generation_receipt": _repo_artifact_record(
                    generation_path, repository_root=repository_root
                ),
                "dvc_reconstruction_receipt": _repo_artifact_record(
                    dvc_path, repository_root=repository_root
                ),
            },
        }
        comparison = row["comparison_manifest"]
        comparison["result_status"] = "generated_verified"
        comparison["reference_result_key"] = result_key
        comparison["reference_dps"] = dps

    _require(
        len(cohort_fixture_hashes) == 1
        and len(cohort_build_hashes) == 1
        and cohort_catalog_hashes
        == {str(publication["pending_request_catalog_sha256"])}
        and len(cohort_admission_commits) == 1
        and next(iter(cohort_admission_commits)) != "",
        "promotion:cohort_identity",
    )

    validate_request_manifest(
        promoted, root=repository_root, verify_generated_artifacts=True
    )
    rendered = json.dumps(promoted, indent=2, ensure_ascii=False) + "\n"
    existing = output_path.read_text(encoding="utf-8") if output_path.exists() else None
    if check:
        _require(existing == rendered, "promotion:catalog_drift")
        for path, label in (
            (promotion_index_path, "promotion:commit_b_index"),
            (common_dvc_path, "promotion:commit_b_dvc_receipt"),
            (output_path, "promotion:commit_b_catalog"),
            (
                repository_root / str(publication["dvc_pointer_path"]),
                "promotion:commit_b_pointer",
            ),
        ):
            _require_committed_head_file(
                path, repository_root=repository_root, label=label
            )
        pointer_at_commit_a = subprocess.run(
            [
                "git",
                "-C",
                str(repository_root),
                "show",
                f"{publication['repository_revision']}:{publication['dvc_pointer_path']}",
            ],
            check=True,
            capture_output=True,
        ).stdout
        _require(
            (repository_root / str(publication["dvc_pointer_path"])).read_bytes()
            == pointer_at_commit_a,
            "promotion:commit_b_pointer_drifted_from_commit_a",
        )
    elif existing != rendered:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        handle, raw_temp_path = tempfile.mkstemp(
            prefix=f".{output_path.name}.", dir=output_path.parent
        )
        temp_path = Path(raw_temp_path)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(rendered)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, output_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
    return promoted


def _require_generation_admission(admission_commit: str | None) -> None:
    _require(bool(admission_commit), "candidate_generation_requires_admission_commit")
    _require(
        bool(re.fullmatch(r"[0-9a-f]{40}", str(admission_commit))),
        "candidate_generation_admission_commit",
    )
    _require(
        _git_output(REPO_ROOT, ["rev-parse", "HEAD"]) == admission_commit,
        "candidate_generation_wrong_repository_commit",
    )
    _require(
        _git_output(REPO_ROOT, ["status", "--porcelain=v1", "--untracked-files=all"])
        == "",
        "candidate_generation_dirty_repository",
    )


def _require_fixture_final_for_generation(
    fixture_contract: Mapping[str, Any],
) -> None:
    _require(
        (fixture_contract.get("authority") or {}).get("lifecycle_status")
        == "final_for_offline_reference_generation",
        "generation_fixture_not_final",
    )


def _materialize_from_cli(args: argparse.Namespace, row: Mapping[str, Any]) -> dict[str, Any]:
    return materialize_native_request(
        request_row=row,
        checkout=args.checkout,
        fixture_contract_path=args.fixture_contract,
        slot_map=load_slot_map(args.gear_profiles),
        output_root=args.output_root,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--checkout", type=Path, required=True)
    build.add_argument("--fixture-contract", type=Path, default=DEFAULT_FIXTURE_CONTRACT)
    build.add_argument("--go-binary", type=Path, required=True)
    build.add_argument("--protoc-binary", type=Path, required=True)
    build.add_argument("--protoc-gen-go-binary", type=Path, required=True)
    build.add_argument("--output-root", type=Path, required=True)

    verify = subparsers.add_parser("verify-receipt")
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--require-dvc-reconstruction", action="store_true")

    audit_reexecute = subparsers.add_parser("audit-reexecute")
    audit_reexecute.add_argument("--generation-receipt", type=Path, required=True)
    audit_reexecute.add_argument("--rebuilt-build-receipt", type=Path, required=True)

    validate_catalog = subparsers.add_parser("validate-catalog")
    validate_catalog.add_argument("--catalog", type=Path, default=DEFAULT_REQUEST_CATALOG)

    def add_materialization_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--catalog", type=Path, default=DEFAULT_REQUEST_CATALOG)
        command.add_argument("--checkout", type=Path, required=True)
        command.add_argument(
            "--fixture-contract", type=Path, default=DEFAULT_FIXTURE_CONTRACT
        )
        command.add_argument("--gear-profiles", type=Path, default=DEFAULT_GEAR_PROFILES)
        command.add_argument("--output-root", type=Path, required=True)

    materialize = subparsers.add_parser("materialize")
    add_materialization_arguments(materialize)
    materialize.add_argument("--target-spec", required=True)
    materialize.add_argument("--build-receipt", type=Path)

    materialize_all = subparsers.add_parser("materialize-all")
    add_materialization_arguments(materialize_all)
    materialize_all.add_argument("--build-receipt", type=Path)

    generate = subparsers.add_parser("generate")
    add_materialization_arguments(generate)
    generate.add_argument("--target-spec", required=True)
    generate.add_argument("--build-receipt", type=Path, required=True)
    generate.add_argument("--candidate", action="store_true")
    generate.add_argument("--admission-commit")

    generate_all = subparsers.add_parser("generate-all")
    add_materialization_arguments(generate_all)
    generate_all.add_argument("--build-receipt", type=Path, required=True)
    generate_all.add_argument("--admission-commit", required=True)

    reconstruct = subparsers.add_parser("reconstruct-with-dvc")
    reconstruct.add_argument("--repository-url", required=True)
    reconstruct.add_argument("--repository-revision", required=True)
    reconstruct.add_argument("--dvc-target", required=True)
    reconstruct.add_argument("--bundle-root", required=True)
    reconstruct.add_argument(
        "--generation-receipt-relative-path", action="append", required=True
    )
    reconstruct.add_argument("--original-repository-root", type=Path, default=REPO_ROOT)
    reconstruct.add_argument("--output-root", type=Path, required=True)
    reconstruct.add_argument("--dvc-binary", type=Path, required=True)
    reconstruct.add_argument("--go-binary", type=Path, required=True)
    reconstruct.add_argument("--protoc-binary", type=Path, required=True)
    reconstruct.add_argument("--protoc-gen-go-binary", type=Path, required=True)

    verify_dvc = subparsers.add_parser("verify-dvc-reconstruction")
    verify_dvc.add_argument("--receipt", type=Path, required=True)
    verify_dvc.add_argument(
        "--generation-receipt", type=Path, action="append", required=True
    )
    verify_dvc.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    verify_dvc.add_argument("--repository-url", required=True)
    verify_dvc.add_argument("--repository-revision", required=True)
    verify_dvc.add_argument("--dvc-pointer-path", required=True)
    verify_dvc.add_argument("--bundle-root", required=True)

    promote = subparsers.add_parser("promote-all")
    promote.add_argument("--catalog", type=Path, default=DEFAULT_REQUEST_CATALOG)
    promote.add_argument("--promotion-index", type=Path, required=True)
    promote.add_argument("--output", type=Path, default=DEFAULT_REQUEST_CATALOG)
    promote.add_argument("--check", action="store_true")

    args = parser.parse_args()
    if args.command == "build":
        receipt = build_pinned_cli(
            checkout=args.checkout,
            fixture_contract_path=args.fixture_contract,
            go_binary=args.go_binary,
            protoc_binary=args.protoc_binary,
            protoc_gen_go_binary=args.protoc_gen_go_binary,
            output_root=args.output_root,
        )
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    if args.command == "validate-catalog":
        manifest = load_request_manifest(args.catalog)
        validate_request_manifest(manifest, verify_generated_artifacts=True)
        print(
            json.dumps(
                {
                    "ok": True,
                    "request_count": len(manifest["requests"]),
                    "provider_revision": manifest["provider_revision"],
                    "fixture_contract_sha256": manifest["fixture_contract_sha256"],
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command == "audit-reexecute":
        observation = audit_generation_reexecution(
            generation_receipt_path=args.generation_receipt,
            rebuilt_build_receipt_path=args.rebuilt_build_receipt,
        )
        print(json.dumps(observation, sort_keys=True))
        return 0
    if args.command in {"materialize", "materialize-all", "generate", "generate-all"}:
        manifest = load_request_manifest(args.catalog)
        validate_request_manifest(manifest, verify_generated_artifacts=False)
        fixture_contract, _ = load_fixture_contract(args.fixture_contract)
        validate_catalog_apl_item_policy(
            manifest,
            checkout=args.checkout,
            fixture_contract=fixture_contract,
        )
        if args.command == "generate-all":
            _require_generation_admission(args.admission_commit)
            _require_fixture_final_for_generation(fixture_contract)
            selected_rows = list(manifest["requests"])
            classification = UNPUBLISHED_CLASSIFICATION
        elif args.command == "materialize-all":
            selected_rows = list(manifest["requests"])
            classification = RESEARCH_CLASSIFICATION
        else:
            selected_rows = [request_by_spec(manifest, args.target_spec)]
            classification = (
                UNPUBLISHED_CLASSIFICATION
                if args.command == "generate" and args.candidate
                else RESEARCH_CLASSIFICATION
            )
            if classification == UNPUBLISHED_CLASSIFICATION:
                _require_generation_admission(args.admission_commit)
                _require_fixture_final_for_generation(fixture_contract)
        outputs = []
        for row in selected_rows:
            materialized = _materialize_from_cli(args, row)
            if args.command in {"materialize", "materialize-all"}:
                protojson_validated = False
                compute_stats_observation: dict[str, Any] | None = None
                protojson_process_evidence: dict[str, Any] | None = None
                if args.build_receipt is not None:
                    fixture, _ = load_fixture_contract(args.fixture_contract)
                    build_receipt, _ = validate_build_receipt(
                        args.build_receipt,
                        expected_revision=str(fixture["authority"]["revision"]),
                    )
                    build_root = args.build_receipt.resolve().parent.parent
                    validator_path = build_root / str(
                        (build_receipt.get("request_validator") or {}).get("path") or ""
                    )
                    with tempfile.TemporaryDirectory(
                        prefix="wowsims-materialize-compute-"
                    ) as temporary:
                        compute_stats_path = Path(temporary) / "compute-stats.json"
                        outcome, validator_output = _run_capture(
                            [
                                str(validator_path),
                                str(
                                    args.output_root
                                    / materialized["native_request"]["path"]
                                ),
                                str(compute_stats_path),
                            ],
                            cwd=REPO_ROOT,
                            env=dict(os.environ),
                            timeout_seconds=60.0,
                        )
                        _require_normal_child(outcome, label="materialize_protojson")
                        protojson_process_evidence = {
                            "transport": outcome,
                            "output_sha256": hashlib.sha256(
                                validator_output
                            ).hexdigest(),
                            "output_byte_count": len(validator_output),
                            "output_utf8": validator_output.decode("utf-8"),
                        }
                        compute_stats_result = _read_json_object(
                            compute_stats_path, label="materialize_compute_stats"
                        )
                        native_request_path = (
                            args.output_root / materialized["native_request"]["path"]
                        )
                        materialized_request = _read_json_object(
                            native_request_path, label="materialize_native_request"
                        )
                        compute_stats_observation = parse_compute_stats_validation(
                            compute_stats_result,
                            rotation=(_request_player(materialized_request).get("rotation") or {}),
                        )
                    protojson_validated = True
                outputs.append(
                    {
                        "target_spec": row["target_spec"],
                        "materialization_receipt": materialized["artifact"],
                        "native_request": materialized["native_request"],
                        "pinned_protojson_validated": protojson_validated,
                        "pinned_compute_stats_validated": (
                            compute_stats_observation is not None
                        ),
                        "compute_stats_observation": compute_stats_observation,
                        "pinned_validation_process_evidence": (
                            protojson_process_evidence
                        ),
                    }
                )
                continue
            materialization_path = args.output_root / materialized["artifact"]["path"]
            generated = generate_one_reference(
                request_row=row,
                materialization_receipt_path=materialization_path,
                build_receipt_path=args.build_receipt,
                fixture_contract_path=args.fixture_contract,
                slot_map=load_slot_map(args.gear_profiles),
                output_root=args.output_root,
                classification=classification,
                request_catalog_sha256=canonical_sha256(manifest),
                evidence_repository_admission_commit=getattr(
                    args, "admission_commit", None
                ),
            )
            outputs.append(
                {
                    "target_spec": row["target_spec"],
                    "generation_receipt": generated["artifact"],
                    "dps": generated["result_observation"]["dps"],
                    "classification": classification,
                }
            )
        print(json.dumps({"ok": True, "outputs": outputs}, sort_keys=True))
        return 0
    if args.command == "reconstruct-with-dvc":
        receipt = reconstruct_generation_with_dvc(
            repository_url=args.repository_url,
            repository_revision=args.repository_revision,
            dvc_target=args.dvc_target,
            bundle_root=args.bundle_root,
            generation_receipt_relative_paths=args.generation_receipt_relative_path,
            original_repository_root=args.original_repository_root,
            output_root=args.output_root,
            dvc_binary=args.dvc_binary,
            go_binary=args.go_binary,
            protoc_binary=args.protoc_binary,
            protoc_gen_go_binary=args.protoc_gen_go_binary,
        )
        print(json.dumps({"ok": True, "receipt": receipt["artifact"]}, sort_keys=True))
        return 0
    if args.command == "verify-dvc-reconstruction":
        receipt = validate_dvc_reconstruction_receipt(
            args.receipt,
            expected_generation_receipt_paths=args.generation_receipt,
            expected_repository_root=args.repository_root,
            expected_repository_url=args.repository_url,
            expected_repository_revision=args.repository_revision,
            expected_dvc_pointer_path=args.dvc_pointer_path,
            expected_bundle_root=args.bundle_root,
        )
        print(json.dumps({"ok": True, "receipt_sha256": receipt["receipt_sha256"]}))
        return 0
    if args.command == "promote-all":
        promoted = promote_generated_references(
            catalog_path=args.catalog,
            promotion_index_path=args.promotion_index,
            output_path=args.output,
            check=args.check,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "promoted_count": sum(
                        row.get("result", {}).get("status") == "generated_verified"
                        for row in promoted["requests"]
                    ),
                },
                sort_keys=True,
            )
        )
        return 0
    receipt = validate_generation_receipt(
        args.receipt, require_dvc_reconstruction=args.require_dvc_reconstruction
    )
    print(json.dumps({"ok": True, "receipt_sha256": receipt["receipt_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
