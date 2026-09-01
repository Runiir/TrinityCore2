"""Derive one authenticated runtime config from tracked source bytes."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any

from tools.raid_program.canonical_route_staging import (
    CanonicalRouteStagingError,
    atomic_write_new,
    git_output,
    is_within,
)


CONTRACT_SCHEMA = "cata_raid_tracked_base_runtime_config_v1"
RECEIPT_SCHEMA = "cata_raid_tracked_runtime_config_derivation_receipt_v1"
TEMPLATE_PATH = "src/server/worldserver/worldserver.conf.dist"
TEMPLATE_SHA256 = "ab0bf9adac893c97ce1c8c78034e70311ed98f4b3e32e52b998cf479122f80cd"
RECIPE_PATH = "Makefile"
RECIPE_SHA256 = "76c854e1c4e7dcbc4fc9f5a2444ede512ca65a7d1ff6e2514be8941641ea918a"
RECIPE_TARGET = "test-configs"
OUTPUT_SHA256 = "8a80c67f6c1ecca22bee90bda81e779a8371c027bb703f2f1b30f446ca3aa65f"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
SAFE_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_.-]*")
CONTRACT_FIELDS = {
    "schema", "contract_id", "template", "recipe", "typed_inputs",
    "fixed_recipe_substitutions", "external_secret_inputs",
    "profile_precedence", "expected_output_sha256",
}
TYPED_INPUT_TYPES: dict[str, type] = {
    "data_dir": str,
    "botworld_auto_start": bool,
    "botworld_auto_start_recording": bool,
    "botworld_enable": bool,
    "botworld_runtime_profile": str,
    "botworld_recording_window_minutes": int,
    "botworld_target_population": int,
    "botworld_spawn_mode": str,
    "botworld_allow_configured_center_fallback": bool,
    "botworld_use_saved_position": bool,
    "botworld_quest_first": bool,
    "botworld_allow_grinding": bool,
    "botworld_grind_only_when_no_quest_available": bool,
    "bot_policy_model_enable": bool,
    "bot_policy_model_mode": str,
    "bot_policy_model_version": str,
    "bot_policy_model_score_weight_lexical": str,
    "bot_policy_model_fail_closed": bool,
}
FIXED_INPUT_TYPES: dict[str, type] = {
    "database_host": str,
    "database_port": int,
    "database_names": list,
    "player_bot_enable": bool,
    "remote_access_enable": bool,
    "soap_enable": bool,
    "death_recovery_mode": str,
    "respawn_mode": str,
    "allow_questing": bool,
    "allow_dungeons": bool,
    "allow_raids": bool,
    "bot_learning_enable": bool,
}
RECEIPT_FIELDS = {
    "schema", "contract_id", "source_commit", "source_tree", "template",
    "recipe", "contract", "typed_inputs", "typed_inputs_sha256",
    "fixed_recipe_substitutions", "fixed_recipe_substitutions_sha256",
    "substitution_inventory", "substitution_inventory_sha256",
    "destination", "output_length", "output_sha256",
}


class RuntimeConfigDerivationError(RuntimeError):
    pass


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeConfigDerivationError(f"contract_duplicate_key:{key}")
        result[key] = value
    return result


def _clean_identity(worktree: Path) -> tuple[str, str]:
    try:
        commit = str(git_output(worktree, "rev-parse", "HEAD"))
        tree = str(git_output(worktree, "rev-parse", "HEAD^{tree}"))
        dirty = git_output(
            worktree, "status", "--porcelain=v1", "-z", binary=True)
    except subprocess.SubprocessError as error:
        raise RuntimeConfigDerivationError("source_identity_invalid") from error
    if dirty:
        raise RuntimeConfigDerivationError("source_worktree_dirty")
    return commit, tree


def _relative_path(value: str, label: str) -> str:
    path = Path(value)
    if (
        not value or path.is_absolute() or ".." in path.parts
        or path.as_posix() != value
    ):
        raise RuntimeConfigDerivationError(f"{label}_path_invalid")
    return value


def _tracked_blob(worktree: Path, relative: str, label: str) -> bytes:
    relative = _relative_path(relative, label)
    try:
        row = str(git_output(
            worktree, "ls-tree", "HEAD", "--", relative))
        payload = git_output(
            worktree, "show", f"HEAD:{relative}", binary=True)
    except subprocess.SubprocessError as error:
        raise RuntimeConfigDerivationError(f"{label}_tracked_blob_invalid") from error
    if not row.startswith("100644 blob ") or not row.endswith(f"\t{relative}"):
        raise RuntimeConfigDerivationError(f"{label}_tracked_blob_invalid")
    return bytes(payload)


def _typed_map(value: object, types: dict[str, type], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(types):
        raise RuntimeConfigDerivationError(f"{label}_schema_invalid")
    for key, expected_type in types.items():
        if type(value[key]) is not expected_type:
            raise RuntimeConfigDerivationError(f"{label}_type_invalid:{key}")
    return value


def _validate_contract(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeConfigDerivationError("contract_json_invalid") from error
    if not isinstance(value, dict) or set(value) != CONTRACT_FIELDS:
        raise RuntimeConfigDerivationError("contract_schema_invalid")
    if payload != _canonical_bytes(value):
        raise RuntimeConfigDerivationError("contract_not_canonical")
    if value.get("schema") != CONTRACT_SCHEMA or value.get("contract_id") != CONTRACT_SCHEMA:
        raise RuntimeConfigDerivationError("contract_identity_invalid")
    template = value.get("template")
    recipe = value.get("recipe")
    if template != {"relative_path": TEMPLATE_PATH, "sha256": TEMPLATE_SHA256}:
        raise RuntimeConfigDerivationError("contract_template_identity_invalid")
    if recipe != {
        "relative_path": RECIPE_PATH, "sha256": RECIPE_SHA256,
        "target": RECIPE_TARGET,
    }:
        raise RuntimeConfigDerivationError("contract_recipe_identity_invalid")
    if (
        value.get("expected_output_sha256") != OUTPUT_SHA256
        or value.get("external_secret_inputs") is not False
        or value.get("profile_precedence")
        != "bundle_local_selected_profile_overlay"
    ):
        raise RuntimeConfigDerivationError("contract_policy_invalid")
    typed = _typed_map(value.get("typed_inputs"), TYPED_INPUT_TYPES, "typed_inputs")
    fixed = _typed_map(
        value.get("fixed_recipe_substitutions"), FIXED_INPUT_TYPES,
        "fixed_recipe_substitutions",
    )
    if (
        typed["bot_policy_model_score_weight_lexical"] != "1.0"
        or typed["botworld_runtime_profile"] != ""
        or fixed["database_names"] != ["auth", "world", "characters", "hotfixes"]
    ):
        raise RuntimeConfigDerivationError("contract_input_value_invalid")
    return value


def _target_bytes(recipe: bytes) -> bytes:
    lines = recipe.splitlines(keepends=True)
    indexes = [index for index, line in enumerate(lines)
               if line.rstrip(b"\r\n") == b"test-configs:"]
    if len(indexes) != 1:
        raise RuntimeConfigDerivationError("recipe_target_invalid")
    start = indexes[0]
    end = start + 1
    while end < len(lines) and (
        lines[end].startswith(b"\t") or not lines[end].strip()
    ):
        end += 1
    if not any(line.startswith(b"\t") for line in lines[start + 1:end]):
        raise RuntimeConfigDerivationError("recipe_target_invalid")
    return b"".join(lines[start:end])


def _bit(value: bool) -> str:
    return "1" if value else "0"


def _substitutions(contract: dict[str, Any]) -> list[tuple[str, str, str]]:
    values = contract["typed_inputs"]
    fixed = contract["fixed_recipe_substitutions"]
    port = fixed["database_port"]
    operations: list[tuple[str, str, str]] = [
        ("data_dir", r"^DataDir\s*=.*$", f'DataDir = "{values["data_dir"]}"'),
    ]
    for key, database in (
        ("LoginDatabaseInfo", "auth"), ("WorldDatabaseInfo", "world"),
        ("CharacterDatabaseInfo", "characters"), ("HotfixDatabaseInfo", "hotfixes"),
    ):
        operations.append((
            f"database_{database}",
            rf'^{key}\s*=\s*"127\.0\.0\.1;3306;trinity;trinity;{database}"$',
            f'{key} = "{fixed["database_host"]};{port};trinity;trinity;{database}"',
        ))
    operations.extend([
        ("player_bot_enable", r"^PlayerBot\.Enable\s*=.*$", f'PlayerBot.Enable = {_bit(fixed["player_bot_enable"])}'),
        ("remote_access_enable", r"^Ra\.Enable\s*=.*$", f'Ra.Enable = {_bit(fixed["remote_access_enable"])}'),
        ("soap_enable", r"^SOAP\.Enabled\s*=.*$", f'SOAP.Enabled = {_bit(fixed["soap_enable"])}'),
        ("botworld_auto_start", r"^BotWorld\.AutoStart\s*=.*$", f'BotWorld.AutoStart = {_bit(values["botworld_auto_start"])}'),
        ("botworld_runtime_profile", r"^BotWorld\.RuntimeProfile\s*=.*$", f'BotWorld.RuntimeProfile = "{values["botworld_runtime_profile"]}"'),
        ("botworld_auto_start_recording", r"^BotWorld\.AutoStartRecording\s*=.*$", f'BotWorld.AutoStartRecording = {_bit(values["botworld_auto_start_recording"])}'),
        ("botworld_recording_window_minutes", r"^BotWorld\.AutoRecordingWindowMinutes\s*=.*$", f'BotWorld.AutoRecordingWindowMinutes = {values["botworld_recording_window_minutes"]}'),
        ("botworld_enable", r"^BotWorld\.Enable\s*=.*$", f'BotWorld.Enable = {_bit(values["botworld_enable"])}'),
        ("botworld_target_population", r"^BotWorld\.TargetPopulation\s*=.*$", f'BotWorld.TargetPopulation = {values["botworld_target_population"]}'),
        ("botworld_spawn_mode", r"^BotWorld\.SpawnMode\s*=.*$", f'BotWorld.SpawnMode = "{values["botworld_spawn_mode"]}"'),
        ("botworld_allow_configured_center_fallback", r"^BotWorld\.AllowConfiguredCenterFallback\s*=.*$", f'BotWorld.AllowConfiguredCenterFallback = {_bit(values["botworld_allow_configured_center_fallback"])}'),
        ("botworld_use_saved_position", r"^BotWorld\.UseSavedPosition\s*=.*$", f'BotWorld.UseSavedPosition = {_bit(values["botworld_use_saved_position"])}'),
        ("botworld_allow_grinding", r"^BotWorld\.AllowGrinding\s*=.*$", f'BotWorld.AllowGrinding = {_bit(values["botworld_allow_grinding"])}'),
        ("botworld_quest_first", r"^BotWorld\.QuestFirst\s*=.*$", f'BotWorld.QuestFirst = {_bit(values["botworld_quest_first"])}'),
        ("botworld_grind_only", r"^BotWorld\.GrindOnlyWhenNoQuestAvailable\s*=.*$", f'BotWorld.GrindOnlyWhenNoQuestAvailable = {_bit(values["botworld_grind_only_when_no_quest_available"])}'),
        ("death_recovery", r"^BotWorld\.DeathRecoveryMode\s*=.*$", f'BotWorld.DeathRecoveryMode = "{fixed["death_recovery_mode"]}"\nBotWorld.RespawnMode = "{fixed["respawn_mode"]}"'),
        ("allow_questing", r"^BotProgression\.AllowQuesting\s*=.*$", f'BotProgression.AllowQuesting = {_bit(fixed["allow_questing"])}\nBotWorld.AllowQuesting = {_bit(fixed["allow_questing"])}'),
        ("allow_dungeons", r"^BotProgression\.AllowDungeons\s*=.*$", f'BotProgression.AllowDungeons = {_bit(fixed["allow_dungeons"])}'),
        ("allow_raids", r"^BotProgression\.AllowRaids\s*=.*$", f'BotProgression.AllowRaids = {_bit(fixed["allow_raids"])}'),
        ("bot_learning_enable", r"^BotLearning\.Enable\s*=.*$", f'BotLearning.Enable = {_bit(fixed["bot_learning_enable"])}'),
        ("policy_enable", r"^BotPolicyModel\.Enable\s*=.*$", f'BotPolicyModel.Enable = {_bit(values["bot_policy_model_enable"])}'),
        ("policy_mode", r"^BotPolicyModel\.Mode\s*=.*$", f'BotPolicyModel.Mode = "{values["bot_policy_model_mode"]}"'),
        ("policy_version", r"^BotPolicyModel\.Version\s*=.*$", f'BotPolicyModel.Version = "{values["bot_policy_model_version"]}"'),
        ("policy_score_weight", r"^BotPolicyModel\.ScoreWeight\s*=.*$", f'BotPolicyModel.ScoreWeight = {values["bot_policy_model_score_weight_lexical"]}'),
        ("policy_fail_closed", r"^BotPolicyModel\.FailClosed\s*=.*$", f'BotPolicyModel.FailClosed = {_bit(values["bot_policy_model_fail_closed"])}'),
    ])
    return operations


def _derive(template: bytes, contract: dict[str, Any]) -> tuple[bytes, list[dict[str, Any]]]:
    try:
        text = template.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeConfigDerivationError("template_encoding_invalid") from error
    inventory: list[dict[str, Any]] = []
    for identity, expression, replacement in _substitutions(contract):
        pattern = re.compile(expression, re.MULTILINE)
        before = len(pattern.findall(text))
        if before != 1:
            raise RuntimeConfigDerivationError(
                f"substitution_before_cardinality:{identity}:{before}")
        text = pattern.sub(lambda _match: replacement, text, count=1)
        after = len(re.findall(
            rf"^{re.escape(replacement)}$", text, re.MULTILINE))
        if after != 1:
            raise RuntimeConfigDerivationError(
                f"substitution_after_cardinality:{identity}:{after}")
        inventory.append({
            "id": identity, "before_count": before, "after_count": after,
            "replacement_sha256": _sha(replacement.encode()),
        })
    return text.encode(), inventory


def _stable_snapshot(path: Path) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        finished = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
    except OSError as error:
        raise RuntimeConfigDerivationError("derived_snapshot_replaced") from error
    finally:
        if "descriptor" in locals():
            os.close(descriptor)
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if (
        not stat.S_ISREG(opened.st_mode)
        or any(getattr(opened, field) != getattr(finished, field) for field in fields)
        or any(getattr(finished, field) != getattr(current, field) for field in fields)
    ):
        raise RuntimeConfigDerivationError("derived_snapshot_replaced")
    return b"".join(chunks), finished


def _source_material(
    worktree: Path, contract_relative_path: str,
    expected_source_commit: str, expected_source_tree: str,
) -> dict[str, Any]:
    worktree = worktree.resolve()
    commit, tree = _clean_identity(worktree)
    if commit != expected_source_commit or tree != expected_source_tree:
        raise RuntimeConfigDerivationError("source_identity_mismatch")
    contract_path = _relative_path(contract_relative_path, "contract")
    contract_bytes = _tracked_blob(worktree, contract_path, "contract")
    contract = _validate_contract(contract_bytes)
    template_bytes = _tracked_blob(worktree, TEMPLATE_PATH, "template")
    recipe_bytes = _tracked_blob(worktree, RECIPE_PATH, "recipe")
    if _sha(template_bytes) != TEMPLATE_SHA256:
        raise RuntimeConfigDerivationError("template_hash_mismatch")
    if _sha(recipe_bytes) != RECIPE_SHA256:
        raise RuntimeConfigDerivationError("recipe_hash_mismatch")
    target = _target_bytes(recipe_bytes)
    output, inventory = _derive(template_bytes, contract)
    if _sha(output) != OUTPUT_SHA256:
        raise RuntimeConfigDerivationError("derived_output_hash_mismatch")
    return {
        "worktree": worktree, "commit": commit, "tree": tree,
        "contract_path": contract_path, "contract_bytes": contract_bytes,
        "contract": contract, "template_bytes": template_bytes,
        "recipe_bytes": recipe_bytes, "target_bytes": target,
        "output": output, "inventory": inventory,
    }


def derive_runtime_config(
    *, worktree: Path, contract_relative_path: str,
    expected_source_commit: str, expected_source_tree: str,
    external_run_root: Path, destination_name: str,
) -> dict[str, Any]:
    material = _source_material(
        worktree, contract_relative_path,
        expected_source_commit, expected_source_tree,
    )
    root_lexical = external_run_root
    root = external_run_root.resolve()
    if (
        not root_lexical.is_absolute() or root_lexical != root
        or external_run_root.is_symlink()
        or not root.is_dir() or is_within(root, material["worktree"])
        or not SAFE_NAME_RE.fullmatch(destination_name)
    ):
        raise RuntimeConfigDerivationError("derivation_destination_invalid")
    destination = root / destination_name
    receipt_path = root / f"{destination_name}.receipt.json"
    if (
        destination.exists() or destination.is_symlink()
        or receipt_path.exists() or receipt_path.is_symlink()
    ):
        raise RuntimeConfigDerivationError("derivation_destination_conflict")
    try:
        atomic_write_new(destination, material["output"])
    except CanonicalRouteStagingError as error:
        raise RuntimeConfigDerivationError("derivation_destination_conflict") from error
    output_snapshot, output_stat = _stable_snapshot(destination)
    if output_snapshot != material["output"] or _sha(output_snapshot) != OUTPUT_SHA256:
        destination.unlink(missing_ok=True)
        raise RuntimeConfigDerivationError("derived_output_hash_mismatch")

    typed = material["contract"]["typed_inputs"]
    fixed = material["contract"]["fixed_recipe_substitutions"]
    inventory = material["inventory"]
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "contract_id": CONTRACT_SCHEMA,
        "source_commit": material["commit"], "source_tree": material["tree"],
        "template": {"path": TEMPLATE_PATH, "length": len(material["template_bytes"]), "sha256": TEMPLATE_SHA256},
        "recipe": {"path": RECIPE_PATH, "target": RECIPE_TARGET, "length": len(material["recipe_bytes"]), "sha256": RECIPE_SHA256, "target_length": len(material["target_bytes"]), "target_sha256": _sha(material["target_bytes"])},
        "contract": {"path": material["contract_path"], "length": len(material["contract_bytes"]), "sha256": _sha(material["contract_bytes"])},
        "typed_inputs": typed, "typed_inputs_sha256": _sha(_canonical_bytes(typed)),
        "fixed_recipe_substitutions": fixed,
        "fixed_recipe_substitutions_sha256": _sha(_canonical_bytes(fixed)),
        "substitution_inventory": inventory,
        "substitution_inventory_sha256": _sha(_canonical_bytes(inventory)),
        "destination": {"path": str(destination), "parent": str(root), "name": destination_name, "device": output_stat.st_dev, "inode": output_stat.st_ino},
        "output_length": len(output_snapshot), "output_sha256": OUTPUT_SHA256,
    }
    receipt_bytes = _canonical_bytes(receipt)
    try:
        atomic_write_new(receipt_path, receipt_bytes)
    except CanonicalRouteStagingError as error:
        destination.unlink(missing_ok=True)
        raise RuntimeConfigDerivationError("derivation_destination_conflict") from error
    return {
        **receipt, "receipt_path": str(receipt_path),
        "receipt_sha256": _sha(receipt_bytes),
    }


def verify_runtime_config_derivation(
    *, worktree: Path, receipt_path: Path, expected_receipt_sha256: str,
    contract_relative_path: str, expected_source_commit: str,
    expected_source_tree: str,
) -> dict[str, Any]:
    receipt_lexical = receipt_path
    receipt = receipt_path.resolve()
    if (
        not receipt_lexical.is_absolute() or receipt_lexical != receipt
        or receipt_path.is_symlink()
        or not receipt.is_file() or is_within(receipt, worktree.resolve())
    ):
        raise RuntimeConfigDerivationError("derivation_receipt_location_invalid")
    receipt_bytes, _receipt_stat = _stable_snapshot(receipt)
    if not SHA256_RE.fullmatch(expected_receipt_sha256) or _sha(receipt_bytes) != expected_receipt_sha256:
        raise RuntimeConfigDerivationError("derivation_receipt_hash_mismatch")
    try:
        value = json.loads(receipt_bytes, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeConfigDerivationError("derivation_receipt_invalid") from error
    if (
        not isinstance(value, dict) or set(value) != RECEIPT_FIELDS
        or value.get("schema") != RECEIPT_SCHEMA
        or receipt_bytes != _canonical_bytes(value)
    ):
        raise RuntimeConfigDerivationError("derivation_receipt_invalid")
    material = _source_material(
        worktree, contract_relative_path,
        expected_source_commit, expected_source_tree,
    )
    typed = material["contract"]["typed_inputs"]
    fixed = material["contract"]["fixed_recipe_substitutions"]
    inventory = material["inventory"]
    expected = {
        "schema": RECEIPT_SCHEMA, "contract_id": CONTRACT_SCHEMA,
        "source_commit": material["commit"], "source_tree": material["tree"],
        "template": {"path": TEMPLATE_PATH, "length": len(material["template_bytes"]), "sha256": TEMPLATE_SHA256},
        "recipe": {"path": RECIPE_PATH, "target": RECIPE_TARGET, "length": len(material["recipe_bytes"]), "sha256": RECIPE_SHA256, "target_length": len(material["target_bytes"]), "target_sha256": _sha(material["target_bytes"])},
        "contract": {"path": material["contract_path"], "length": len(material["contract_bytes"]), "sha256": _sha(material["contract_bytes"])},
        "typed_inputs": typed, "typed_inputs_sha256": _sha(_canonical_bytes(typed)),
        "fixed_recipe_substitutions": fixed,
        "fixed_recipe_substitutions_sha256": _sha(_canonical_bytes(fixed)),
        "substitution_inventory": inventory,
        "substitution_inventory_sha256": _sha(_canonical_bytes(inventory)),
        "output_length": len(material["output"]), "output_sha256": OUTPUT_SHA256,
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise RuntimeConfigDerivationError("derivation_receipt_binding_mismatch")
    destination_value = value.get("destination")
    if not isinstance(destination_value, dict) or set(destination_value) != {
        "path", "parent", "name", "device", "inode",
    }:
        raise RuntimeConfigDerivationError("derivation_receipt_binding_mismatch")
    destination = Path(str(destination_value["path"]))
    if (
        not destination.is_absolute() or destination.resolve() != destination
        or destination.is_symlink()
        or not destination.is_file()
        or is_within(destination, worktree.resolve())
        or str(destination.parent) != destination_value["parent"]
        or destination.name != destination_value["name"]
    ):
        raise RuntimeConfigDerivationError("derived_snapshot_location_invalid")
    snapshot, state = _stable_snapshot(destination)
    if (
        state.st_dev != destination_value["device"]
        or state.st_ino != destination_value["inode"]
        or snapshot != material["output"]
        or len(snapshot) != value["output_length"]
        or _sha(snapshot) != OUTPUT_SHA256
    ):
        raise RuntimeConfigDerivationError("derived_snapshot_binding_mismatch")
    return {
        **value, "receipt_path": str(receipt),
        "receipt_sha256": expected_receipt_sha256,
        "output_snapshot_base64": base64.b64encode(snapshot).decode("ascii"),
    }
