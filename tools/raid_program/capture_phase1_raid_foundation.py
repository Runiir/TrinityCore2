from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

IDENTITY_FIELDS = (
    "group_guid",
    "leader_guid",
    "expected_size",
    "expected_difficulty",
    "group_difficulty",
    "map_difficulty",
    "map_id",
    "instance_id",
    "lockout_save_id",
    "server_epoch",
    "attempt_id",
)
STRATEGY_FIELD = "strategy_id"
ROSTER_ID_FIELDS = (
    "roster_slot_id", "lease_role_slot", "slot", "guid", "subgroup", "role",
    "class_id", "class_spec", "gear_identity", "active", "lease_owned",
    "account_id", "account", "name", "talents", "glyphs", "gear_identity_manifest",
)
FORBIDDEN_ASSISTANCE_FIELDS = (
    "forbidden_completion_assists",
    "forbidden_assistance",
    "teacher_assisted",
    "encounter_state_injection",
    "forced_kill",
    "direct_resurrection",
    "combat_teleport",
    "door_unlock",
    "npc_spawn_assist",
    "direct_resurrect",
    "admin_resurrection",
    "forced_resurrection",
    "forced_teleport",
    "fallback_action",
    "fallback_result",
    "soap_command",
    "operator_command",
    "publisher_command",
    "dvc_push",
)

# These markers are forbidden even when they occur in an otherwise innocuous
# trace row.  A status field such as ``recovery_state`` is not a command/event
# marker and is therefore intentionally not included in this scan.
FORBIDDEN_MARKER_FIELDS = {
    "action", "event", "event_name", "result", "result_code", "command",
    "command_name", "failure_reason", "mode", "recovery_mode", "source",
    "operator", "publisher", "transport", "assistance_mode",
}
FORBIDDEN_MARKER_RE = re.compile(
    r"(?:direct[ _-]*resurrect|admin[ _-]*(?:resurrect|revive)|"
    r"forced[ _-]*(?:resurrect|revive|teleport|move|kill|wipe|reset)|"
    r"(?:^|[ _-])teleport(?:$|[ _-])|(?:^|[ _-])fallback(?:$|[ _-])|"
    r"(?:^|[ _-])(?:soap|console|operator|publisher)(?:$|[ _-])|"
    r"dvc[ _-]*push)",
    re.IGNORECASE,
)


def expected_bwd_10n_roster() -> tuple[tuple[str, str, int, str], ...]:
    manifest = json.loads(
        (ROOT / "experiments/configs/validation_provisioning_cata_001.json").read_text(
            encoding="utf-8"
        )
    )
    scenario = next(
        row for row in manifest["scenarios"] if row.get("id") == "blackwing_descent_10n"
    )
    role_counts: Counter[str] = Counter()
    expected: list[tuple[str, str, int, str]] = []
    for bot in scenario["bots"]:
        role = str(bot["role"])
        role_counts[role] += 1
        expected.append(
            (
                f"raid_{role}_{role_counts[role]}",
                role,
                int(bot["class"]),
                str(bot["class_spec"]),
            )
        )
    if len(expected) != 10 or role_counts != Counter({"tank": 2, "healer": 3, "dps": 5}):
        raise ValueError("frozen BWD 10N provisioning roster is invalid")
    return tuple(expected)


def _provisioned_bwd_10n_bots() -> list[dict[str, Any]]:
    """Load the checked-in, post-normalization BWD provisioning roster.

    The capture verifier must not silently fall back to a partial roster when
    provisioning data is unavailable.  The builder's loader is used here so
    talent defaults and the checked-in gear profile overlay are represented by
    the same canonical values that generated the provisioning SQL.
    """

    try:
        from tools.bot_ml.build_validation_provisioning import (
            apply_gear_profiles,
            load_config,
            load_gear_profiles,
        )

        config = load_config(ROOT / "experiments/configs/validation_provisioning_cata_001.json")
        config = apply_gear_profiles(
            config,
            load_gear_profiles(ROOT / "dataset/validation_gear_profiles/profiles.json"),
        )
        scenario = next(
            row for row in config["scenarios"] if row.get("id") == "blackwing_descent_10n"
        )
        bots = scenario.get("bots")
        if not isinstance(bots, list) or len(bots) != 10:
            raise ValueError("frozen BWD 10N provisioning roster is missing")
        return [row for row in bots if isinstance(row, dict)]
    except (ImportError, KeyError, OSError, StopIteration, TypeError, ValueError) as error:
        raise ValueError(f"frozen BWD 10N identity manifest unavailable: {error}") from error


def _canonical_int_list(values: Any) -> tuple[int, ...] | None:
    if not isinstance(values, list):
        return None
    result: list[int] = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("spell_id", value.get("id"))
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return None
        result.append(value)
    return tuple(result)


def _expected_identity_by_slot() -> dict[str, dict[str, Any]]:
    from tools.bot_ml.build_validation_provisioning import normalized_glyph_slots

    result: dict[str, dict[str, Any]] = {}
    for bot in _provisioned_bwd_10n_bots():
        role = str(bot.get("role") or "")
        # Roster slot IDs are generated deterministically by the native plan.
        index = sum(1 for existing in result.values() if existing["role"] == role) + 1
        slot_id = f"raid_{role}_{index}"
        talents = _canonical_int_list([row.get("spell_id") for row in bot.get("talents", [])])
        glyphs = _canonical_int_list(
            [value for value in normalized_glyph_slots(bot) if int(value) > 0]
        )
        equipment = bot.get("equipment")
        if not isinstance(equipment, list) or not equipment:
            raise ValueError(f"frozen gear manifest missing for {slot_id}")
        expected_items = []
        for item in equipment:
            if not isinstance(item, dict) or int(item.get("slot", -1)) < 0 or int(item.get("item_id") or 0) <= 0:
                raise ValueError(f"frozen gear manifest invalid for {slot_id}")
            expected_items.append(
                {
                    "slot": int(item["slot"]),
                    "entry": int(item["item_id"]),
                    "enchant_id": int(item.get("enchant_id") or 0),
                    "gem_item_ids": tuple(int(value) for value in item.get("gem_item_ids", [])),
                    "reforge_id": int(item.get("reforge_id") or 0),
                }
            )
        if talents is None or glyphs is None:
            raise ValueError(f"frozen talent/glyph manifest missing for {slot_id}")
        result[slot_id] = {
            "account": str(bot.get("account") or "").upper(),
            "name": str(bot.get("name") or ""),
            "role": role,
            "class_id": int(bot.get("class") or 0),
            "class_spec": str(bot.get("class_spec") or ""),
            "talents": talents,
            "glyphs": glyphs,
            "gear": tuple(sorted(expected_items, key=lambda row: row["slot"])),
        }
    return result


def _runtime_gear_manifest(row: dict[str, Any]) -> tuple[tuple[Any, ...], ...] | None:
    value = row.get("gear_identity_manifest")
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        return None
    items: list[tuple[Any, ...]] = []
    for item in value["items"]:
        if not isinstance(item, dict):
            return None
        guid = item.get("guid")
        entry = item.get("entry", item.get("item_entry"))
        if not _positive_int(guid) or not _positive_int(entry):
            return None
        gem_ids = item.get("gem_item_ids", [])
        if not isinstance(gem_ids, list) or any(not _nonnegative_int(gem) for gem in gem_ids):
            return None
        items.append(
            (
                int(item.get("slot", -1)), int(guid), int(entry),
                int(item.get("enchant_id") or 0), tuple(int(gem) for gem in gem_ids),
                int(item.get("reforge_id") or 0),
            )
        )
    if len({item[0] for item in items}) != len(items) or len({item[1] for item in items}) != len(items):
        return None
    return tuple(sorted(items))


def _identity_manifest_rejections(runtime: dict[str, Any]) -> list[str]:
    """Check all identity-bearing provisioning fields, fail-closed on omission."""

    try:
        expected_by_slot = _expected_identity_by_slot()
    except ValueError:
        return ["frozen_identity_manifest_unavailable"]
    roster = runtime.get("roster")
    if not isinstance(roster, list):
        return ["frozen_identity_manifest_missing"]
    reasons: list[str] = []
    for row in roster:
        if not isinstance(row, dict):
            continue
        slot_id = str(row.get("roster_slot_id") or "")
        expected = expected_by_slot.get(slot_id)
        if expected is None:
            reasons.append("frozen_identity_unknown_roster_slot")
            continue
        for field in ("account", "name", "talents", "glyphs"):
            if field not in row:
                reasons.append(f"frozen_identity_{field}_missing")
        if not _positive_int(row.get("guid")):
            reasons.append("frozen_identity_guid_missing")
        if str(row.get("account") or "").upper() != expected["account"]:
            reasons.append("frozen_identity_account_mismatch")
        if row.get("name") != expected["name"]:
            reasons.append("frozen_identity_name_mismatch")
        if _canonical_int_list(row.get("talents")) != expected["talents"]:
            reasons.append("frozen_identity_talents_mismatch")
        if _canonical_int_list(row.get("glyphs")) != expected["glyphs"]:
            reasons.append("frozen_identity_glyphs_mismatch")
        actual_gear = _runtime_gear_manifest(row)
        if actual_gear is None:
            reasons.append("frozen_identity_full_gear_manifest_missing")
        else:
            expected_gear = expected["gear"]
            actual_by_slot = {item[0]: item for item in actual_gear}
            if set(actual_by_slot) != {item["slot"] for item in expected_gear}:
                reasons.append("frozen_identity_full_gear_slots_mismatch")
            for item in expected_gear:
                actual = actual_by_slot.get(item["slot"])
                if actual is None:
                    continue
                if actual[2] != item["entry"]:
                    reasons.append("frozen_identity_gear_entry_mismatch")
                if actual[3] != item["enchant_id"] or actual[4] != item["gem_item_ids"] or actual[5] != item["reforge_id"]:
                    reasons.append("frozen_identity_gear_modifiers_mismatch")
    return list(dict.fromkeys(reasons))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_actions(log_bytes: bytes, action: str) -> list[dict[str, Any]]:
    return [row for row in json_rows(log_bytes) if row.get("action") == action]


def json_rows(log_bytes: bytes) -> list[dict[str, Any]]:
    """Parse only complete JSON objects, retaining their log order."""

    rows: list[dict[str, Any]] = []
    for raw in log_bytes.splitlines():
        start = raw.find(b"{")
        end = raw.rfind(b"}")
        if start < 0 or end < start:
            continue
        try:
            row = json.loads(raw[start : end + 1])
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _runtime_identity(runtime: dict[str, Any]) -> tuple[Any, ...] | None:
    if not all(field in runtime for field in IDENTITY_FIELDS):
        return None
    return tuple(runtime[field] for field in IDENTITY_FIELDS)


def _roster_identity(roster: list[dict[str, Any]]) -> tuple[tuple[Any, ...], ...] | None:
    if len(roster) != 10 or any(not isinstance(row, dict) for row in roster):
        return None
    rows: list[tuple[Any, ...]] = []
    for row in sorted(roster, key=lambda value: value.get("slot") if isinstance(value.get("slot"), int) else -1):
        if any(field not in row for field in ROSTER_ID_FIELDS):
            return None
        rows.append(tuple(row[field] for field in ROSTER_ID_FIELDS))
    return tuple(rows)


def _roster_rejections(runtime: dict[str, Any]) -> list[str]:
    roster = runtime.get("roster")
    if not isinstance(roster, list):
        return ["roster_not_a_list"]
    reasons: list[str] = []
    if len(roster) != 10:
        reasons.append("exact_roster")
    rows = [row for row in roster if isinstance(row, dict)]
    if len(rows) != len(roster):
        reasons.append("roster_rows_are_not_objects")
    rows.sort(key=lambda row: row.get("slot") if isinstance(row.get("slot"), int) else -1)
    slots = [row.get("slot") for row in rows]
    if slots != list(range(10)):
        reasons.append("deterministic_slots")
    roster_ids = [row.get("roster_slot_id") for row in rows]
    if any(not isinstance(value, (str, int)) or isinstance(value, bool) or not str(value).strip() for value in roster_ids):
        reasons.append("stable_roster_slot_ids")
    if len(set(roster_ids)) != 10:
        reasons.append("unique_roster_slot_ids")
    if any(row.get("roster_slot_id") == row.get("guid") for row in rows):
        # A numeric GUID is not a roster slot identity.  Distinct identities
        # must be present even when a producer happens to serialize numbers.
        reasons.append("roster_slot_id_not_guid_identity")
    if any(row.get("lease_role_slot") != row.get("roster_slot_id") for row in rows):
        reasons.append("lease_role_slot_identity_mismatch")
    if any(not _positive_int(row.get("class_id")) for row in rows):
        reasons.append("class_identity_missing")
    if any(not isinstance(row.get("class_spec"), str) or not row["class_spec"].strip() for row in rows):
        reasons.append("class_spec_identity_missing")
    if any(not isinstance(row.get("gear_identity"), str) or not row["gear_identity"].strip() for row in rows):
        reasons.append("gear_identity_missing")
    if [row.get("subgroup") for row in rows] != [0] * 5 + [1] * 5:
        reasons.append("deterministic_subgroups")
    guids = [row.get("guid") for row in rows]
    if any(not _positive_int(guid) for guid in guids):
        reasons.append("positive_roster_guids")
    if len(set(guids)) != 10:
        reasons.append("unique_roster_guids")
    roles = Counter(row.get("role") for row in rows)
    if roles != Counter({"tank": 2, "healer": 3, "dps": 5}):
        reasons.append("exact_10n_role_composition")
    observed_roster = tuple(
        (
            str(row.get("roster_slot_id")), str(row.get("role")),
            row.get("class_id"), str(row.get("class_spec")),
        )
        for row in rows
    )
    if observed_roster != expected_bwd_10n_roster():
        reasons.append("exact_frozen_bwd_10n_roster_identity")
    if not all(row.get("active") is True for row in rows):
        reasons.append("all_roster_active")
    if not all(row.get("lease_owned") is True for row in rows):
        reasons.append("all_roster_leases_owned")
    reasons.extend(_identity_manifest_rejections(runtime))
    return reasons


def accepted_foundation_status(status: dict[str, Any]) -> tuple[bool, list[str]]:
    runtime = status.get("raid_runtime") or {}
    reasons: list[str] = []
    if not isinstance(runtime, dict):
        return False, ["raid_runtime_missing"]
    checks = {
        "status_ok": status.get("ok") is True,
        "ten_bots": status.get("bots") == 10,
        "ten_leases": status.get("lease_count") == 10,
        "runtime_active": runtime.get("active") is True,
        "expected_size_10": runtime.get("expected_size") == 10,
        "active_size_10": runtime.get("active_size") == 10,
        "alive_size_10": runtime.get("alive_size") == 10,
        "roster_complete": runtime.get("roster_complete") is True,
        "difficulty_10n": runtime.get("expected_difficulty") == 0 and runtime.get("group_difficulty") == 0,
        "live_map_difficulty_10n": runtime.get("map_difficulty") == 0,
        "difficulty_matches": runtime.get("difficulty_matches") is True,
        "map_bwd": runtime.get("map_id") == 669,
        "instance_owned": _positive_int(runtime.get("instance_id")),
        "lockout_save_owned": _positive_int(runtime.get("lockout_save_id")),
        "group_owned": _positive_int(runtime.get("group_guid")),
        "leader_owned": _positive_int(runtime.get("leader_guid")),
        "server_epoch_owned": _positive_int(runtime.get("server_epoch")),
        "attempt_owned": _positive_int(runtime.get("attempt_id")),
        "strategy_owned": isinstance(runtime.get("strategy_id"), str) and bool(runtime.get("strategy_id", "").strip()),
        "boss_state_readback": len(runtime.get("boss_states") or []) == 6,
        "ready_check_satisfied": runtime.get("ready_check_satisfied") is True,
        "roster_composition_valid": runtime.get("roster_composition_valid") is True,
        "evidence_sequence_owned": _positive_int(runtime.get("evidence_sequence")),
        "unique_leases": runtime.get("unique_leases") is True,
    }
    reasons.extend(name for name, passed in checks.items() if not passed)
    reasons.extend(_roster_rejections(runtime))
    return not reasons, reasons


def _route_advancement_marker(runtime: dict[str, Any]) -> int | None:
    """Return an explicit monotonic route-progress generation, if present."""

    candidates: list[Any] = [
        runtime.get("route_generation"),
        runtime.get("route_step"),
        runtime.get("route_node_index"),
        runtime.get("route_terminal_count"),
        runtime.get("route_progress_generation"),
    ]
    progress = runtime.get("route_progress")
    if isinstance(progress, dict):
        candidates.extend(
            progress.get(field)
            for field in ("generation", "route_generation", "step", "node_index", "terminal_count", "advancement")
        )
    values = [
        int(value) for value in candidates
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ]
    return max(values) if values else None


def accepted_native_recovery(statuses: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    runtimes = [status.get("raid_runtime") if isinstance(status, dict) else None for status in statuses]
    if not statuses or any(not isinstance(runtime, dict) for runtime in runtimes):
        return False, ["native_event_evidence_missing"]

    identity: tuple[Any, ...] | None = None
    roster_identity: tuple[tuple[Any, ...], ...] | None = None
    previous_sequence = 0
    previous_generations = (0, 0, 0)
    previous_strategy: str | None = None
    previous_route_advance = 0
    previous_transition_state: tuple[Any, ...] | None = None
    engagement_index: int | None = None
    wipe_index: int | None = None
    reset_index: int | None = None
    recovery_index: int | None = None
    for index, runtime in enumerate(runtimes):
        assert isinstance(runtime, dict)
        if statuses[index].get("ok") is not True:
            reasons.append("native_status_not_ok")
        current_identity = _runtime_identity(runtime)
        if current_identity is None:
            reasons.append("native_identity_fields_missing")
        elif identity is None:
            identity = current_identity
        elif current_identity != identity:
            reasons.append("native_recovery_mixed_identity")
        strategy = runtime.get(STRATEGY_FIELD)
        strategy_changed = previous_strategy is not None and strategy != previous_strategy
        route_marker = _route_advancement_marker(runtime)
        if not isinstance(strategy, str) or not strategy.strip():
            reasons.append("native_strategy_identity_missing")
        elif strategy_changed:
            transition = runtime.get("strategy_transition")
            transition_ok = (
                isinstance(transition, dict)
                and transition.get("from_strategy") == previous_strategy
                and transition.get("to_strategy") == strategy
                and transition.get("advanced") is True
                and route_marker is not None
                and route_marker > previous_route_advance
            )
            if not transition_ok:
                reasons.append("native_strategy_transition_without_route_advancement")
        if route_marker is not None:
            previous_route_advance = max(previous_route_advance, route_marker)
        if isinstance(strategy, str):
            previous_strategy = strategy
        transition_state = (
            strategy,
            runtime.get("wipe_generation"),
            runtime.get("boss_reset_generation"),
            runtime.get("recovery_generation"),
            runtime.get("encounter_in_progress"),
            runtime.get("wipe_state"),
            runtime.get("recovery_state"),
            runtime.get("alive_size"),
        )
        if any(
            not _positive_int(runtime.get(field))
            for field in ("group_guid", "leader_guid", "instance_id", "lockout_save_id", "server_epoch", "attempt_id")
        ):
            reasons.append("native_identity_values_invalid")
        if (
            runtime.get("expected_size") != 10
            or runtime.get("expected_difficulty") != 0
            or runtime.get("group_difficulty") != 0
            or runtime.get("map_difficulty") != 0
            or runtime.get("map_id") != 669
            or not isinstance(runtime.get("strategy_id"), str)
            or not runtime.get("strategy_id", "").strip()
        ):
            reasons.append("native_identity_not_exact_bwd_10n")

        current_roster = _roster_identity(runtime.get("roster") if isinstance(runtime.get("roster"), list) else [])
        if current_roster is None:
            reasons.append("native_roster_identity_missing")
        elif roster_identity is None:
            roster_identity = current_roster
        elif current_roster != roster_identity:
            reasons.append("native_recovery_mixed_roster")
        reasons.extend(f"native_{reason}" for reason in _roster_rejections(runtime) if reason not in {"all_roster_active", "all_roster_leases_owned"})

        sequence = runtime.get("evidence_sequence")
        if not _positive_int(sequence):
            reasons.append("native_evidence_sequence_missing")
        elif sequence < previous_sequence:
            reasons.append("native_evidence_sequence_not_monotonic")
        elif sequence == previous_sequence and transition_state != previous_transition_state:
            reasons.append("native_evidence_sequence_transition_without_advancement")
        previous_sequence = max(previous_sequence, sequence if _positive_int(sequence) else 0)
        previous_transition_state = transition_state

        generation_fields = ("wipe_generation", "boss_reset_generation", "recovery_generation")
        if any(
            not isinstance(runtime.get(field), int)
            or isinstance(runtime.get(field), bool)
            or runtime.get(field) < 0
            for field in generation_fields
        ):
            reasons.append("native_generation_missing_or_invalid")
        generations = tuple(
            int(runtime.get(field))
            if isinstance(runtime.get(field), int) and not isinstance(runtime.get(field), bool) and runtime.get(field) >= 0
            else 0
            for field in generation_fields
        )
        if any(current < previous for current, previous in zip(generations, previous_generations, strict=True)):
            reasons.append("native_generations_not_monotonic")
        previous_generations = tuple(max(current, previous) for current, previous in zip(generations, previous_generations, strict=True))

        if engagement_index is None and (
            runtime.get("encounter_in_progress") is True
            or any(state == 1 for state in (runtime.get("boss_states") or []))
        ):
            engagement_index = index
        if (
            engagement_index is not None
            and wipe_index is None
            and index > engagement_index
            and generations[0] > 0
            and runtime.get("wipe_state") == "wiped"
            and runtime.get("alive_size") == 0
            and runtime.get("recovery_state") in {"awaiting_native_reset", "release_resurrection_pending"}
        ):
            wipe_index = index
        if (
            wipe_index is not None
            and reset_index is None
            and index > wipe_index
            and generations[1] > 0
            and runtime.get("encounter_in_progress") is False
        ):
            reset_index = index
        if (
            reset_index is not None
            and recovery_index is None
            and index > reset_index
            and generations[2] > 0
            and runtime.get("recovery_state") == "recovered_ready_check"
            and runtime.get("ready_check_satisfied") is True
            and runtime.get("alive_size") == 10
        ):
            recovery_index = index

    native_signals = [
        runtime.get("native_recovery")
        for runtime in runtimes
        if isinstance(runtime.get("native_recovery"), dict)
    ]
    final_native = native_signals[-1] if native_signals else {}
    final_runtime = runtimes[-1]
    wipe_generation = final_runtime.get("wipe_generation")
    if not isinstance(wipe_generation, int) or isinstance(wipe_generation, bool) or wipe_generation <= 0:
        reasons.append("native_recovery_wipe_scope_missing")
    if final_native.get("recovery_wipe_generation") != wipe_generation:
        reasons.append("native_recovery_wipe_scope_mismatch")
    for field in (
        "death_observed", "corpse_observed", "release_observed",
        "resurrection_observed", "runback_observed", "ready_check_action_observed",
        "evidence_complete",
    ):
        if final_native.get(field) is not True:
            reasons.append(f"native_{field}_missing")
    if not _positive_int(final_native.get("ready_check_action_generation")):
        reasons.append("native_ready_check_action_generation_missing")
    if final_native.get("ready_check_action_attempt_id") != runtimes[-1].get("attempt_id"):
        reasons.append("native_ready_check_action_attempt_mismatch")
    if final_native.get("ready_check_action_wipe_generation") != runtimes[-1].get("wipe_generation"):
        reasons.append("native_ready_check_action_wipe_generation_mismatch")

    ordered_checks = {
        "ready_check_observed": any(runtime.get("ready_check_satisfied") is True for runtime in runtimes),
        "native_engagement_observed": engagement_index is not None,
        "native_wipe_observed": wipe_index is not None,
        "boss_reset_observed": reset_index is not None,
        "native_recovery_observed": recovery_index is not None,
    }
    reasons.extend(name for name, passed in ordered_checks.items() if not passed)
    # Preserve deterministic diagnostics rather than reporting the same
    # rejection once for every status snapshot.
    return not reasons, list(dict.fromkeys(reasons))


def wait_for_prompt(process: subprocess.Popen[bytes], log_path: Path, timeout_sec: int) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"worldserver exited before readiness with code {process.returncode}")
        if log_path.exists() and b"TC>" in log_path.read_bytes()[-65536:]:
            return
        time.sleep(0.25)
    raise RuntimeError("worldserver readiness prompt timed out")


def git_identity(cwd: Path) -> dict[str, Any]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cwd, text=True).strip()
    porcelain = subprocess.check_output(["git", "status", "--porcelain=v1", "-z"], cwd=cwd)
    return {"head": head, "clean": not porcelain, "porcelain_sha256": hashlib.sha256(porcelain).hexdigest()}


def _utc_timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def validate_build_receipt(
    receipt_path: Path,
    policy_path: Path,
    worktree: Path,
    binary: Path,
    config: Path | None = None,
) -> dict[str, Any]:
    """Reconstruct the production build gate without trusting receipt pass fields."""

    try:
        from tools.raid_program.queued_build import load_json, verify_receipt

        policy = load_json(policy_path)
        receipt = load_json(receipt_path)
        verification = verify_receipt(receipt_path, policy, allow_test_mode=False)
        identity = git_identity(worktree)
        rejections: list[str] = []
        if verification.get("classification") != "success" or receipt.get("classification") != "success":
            rejections.append("build_receipt_not_success")
        if receipt.get("test_mode") is not False:
            rejections.append("build_receipt_test_mode")
        if receipt.get("exit_code") != 0:
            rejections.append("build_receipt_nonzero_exit")
        if receipt.get("commit") != identity["head"]:
            rejections.append("build_receipt_commit_mismatch")
        if Path(str(receipt.get("worktree", ""))).resolve() != worktree.resolve():
            rejections.append("build_receipt_worktree_mismatch")
        if receipt.get("worktree_dirty_at_request") is not False:
            rejections.append("build_receipt_worktree_dirty")
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
            "binary_binding": "coordinator_receipt_path_size_sha256_commit_and_timestamp_verified",
        }
    except Exception as error:  # fail closed, while retaining a useful rejection
        return {
            "valid": False,
            "rejections": [f"build_receipt_verification_error:{type(error).__name__}:{error}"],
            "receipt_path": str(receipt_path),
            "policy_path": str(policy_path),
            "binary_path": str(binary),
        }


def normalized_batch_payload(log_bytes: bytes) -> list[dict[str, Any]]:
    """Return an immutable, replayable JSONL representation of parsed evidence."""

    channel_by_action = {
        "botauto_status": "status",
        "botauto_diagnose": "diagnosis",
        "botauto_trace": "trace",
        "botauto_readycheck": "native_action",
        "botauto_stop": "cleanup",
    }
    return [
        {
            "capture_sequence": sequence,
            "action": row.get("action"),
            "evidence_channel": channel_by_action.get(str(row.get("action")), "other"),
            "payload": row,
        }
        for sequence, row in enumerate(json_rows(log_bytes), start=1)
    ]


def evidence_demux_rejections(rows: list[dict[str, Any]]) -> list[str]:
    """Bind every retained raid-bearing channel to one runtime and roster identity."""

    reasons: list[str] = []
    canonical_identity: tuple[Any, ...] | None = None
    canonical_roster: tuple[tuple[Any, ...], ...] | None = None
    canonical_cohort: str | None = None
    roster_guids: set[int] = set()
    checked = 0
    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict):
            reasons.append("evidence_demux_payload_missing")
            continue
        action = payload.get("action")
        if action not in {"botauto_status", "botauto_diagnose", "botauto_trace"}:
            continue
        runtime = payload.get("raid_runtime")
        if not isinstance(runtime, dict) or runtime.get("active") is not True:
            continue
        checked += 1
        identity = _runtime_identity(runtime)
        roster = runtime.get("roster")
        roster_identity = _roster_identity(roster) if isinstance(roster, list) else None
        cohort = payload.get("cohort_id")
        if identity is None or roster_identity is None or not isinstance(cohort, str) or not cohort:
            reasons.append("evidence_demux_identity_missing")
            continue
        if canonical_identity is None:
            canonical_identity = identity
            canonical_roster = roster_identity
            canonical_cohort = cohort
            roster_guids = {
                int(member[3]) for member in roster_identity
                if _positive_int(member[3])
            }
        elif identity != canonical_identity or roster_identity != canonical_roster or cohort != canonical_cohort:
            reasons.append("evidence_demux_cross_identity_row")
        bot_rows = payload.get("bots")
        if isinstance(bot_rows, list):
            for bot_row in bot_rows:
                if not isinstance(bot_row, dict):
                    reasons.append("evidence_demux_bot_row_invalid")
                    continue
                bot_guid = bot_row.get("bot_guid")
                identity_object = bot_row.get("identity")
                if isinstance(identity_object, dict):
                    bot_guid = identity_object.get("bot_guid")
                if not _positive_int(bot_guid) or int(bot_guid) not in roster_guids:
                    reasons.append("evidence_demux_bot_outside_roster")
    if checked == 0:
        reasons.append("evidence_demux_no_active_raid_rows")
    return list(dict.fromkeys(reasons))


def write_normalized_batch(path: Path, rows: list[dict[str, Any]]) -> tuple[str, int]:
    if path.exists():
        raise RuntimeError("raw normalized batch output already exists; artifacts are immutable")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for row in rows
    )
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest(), len(rows)


def _forbidden_assistance_entries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in FORBIDDEN_ASSISTANCE_FIELDS and child not in (None, False, [], {}, "", 0):
                    found.append({"path": f"{path}.{key}", "value": child})
                if key in FORBIDDEN_MARKER_FIELDS and isinstance(child, str) and FORBIDDEN_MARKER_RE.search(child):
                    found.append({"path": f"{path}.{key}", "value": child, "kind": "forbidden_event_marker"})
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    for row in rows:
        visit(row, "evidence")
    return found


def _process_arguments(pid: int) -> list[str]:
    try:
        return [
            value.decode(errors="replace")
            for value in (Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0"))
            if value
        ]
    except OSError:
        return []


def preflight_runtime_exclusions(worktree: Path) -> dict[str, Any]:
    """Require an idle coordinator and exclusive canonical-capture host."""

    from tools.raid_program.queued_build import Paths, status as coordinator_status

    coordinator = coordinator_status(Paths.for_worktree(worktree), recover=False)
    reasons: list[str] = []
    if coordinator.get("active") is not None:
        reasons.append("coordinator_active_lease")
    if coordinator.get("queue"):
        reasons.append("coordinator_queue_not_idle")

    protected_names = {
        "worldserver", "run_live_bot_validation.py", "live_validation_session.py",
        "run_phase9_serial_canaries.py", "publish_live_validation.py",
        "publish_live_validation", "promote_live_validation_artifact.py",
        "bot-live-validate", "operator", "raid_operator.py",
    }
    overlap: list[dict[str, Any]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        arguments = _process_arguments(int(entry.name))
        if not arguments:
            continue
        basenames = {Path(value).name for value in arguments}
        matched = sorted(basenames & protected_names)
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


def _artifact_record(path: Path, kind: str) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"immutable artifact missing: {path}")
    return {
        "kind": kind,
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "immutable": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, default=None)
    parser.add_argument("--server-log-output", type=Path, default=None)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument(
        "--build-policy",
        type=Path,
        default=ROOT / "experiments/configs/cata_raid_build_resource_policy_v1.json",
    )
    parser.add_argument("--worktree", type=Path, default=ROOT)
    parser.add_argument("--observe-sec", type=int, default=900)
    parser.add_argument("--startup-timeout-sec", type=int, default=180)
    parser.add_argument("--required-stable-statuses", type=int, default=3)
    args = parser.parse_args()

    binary = args.binary.resolve()
    config = args.config.resolve()
    output = args.output.resolve()
    worktree = args.worktree.resolve()
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
    if args.observe_sec < 30 or args.required_stable_statuses < 2:
        raise SystemExit("observation must be at least 30 seconds and require at least two stable statuses")
    preflight = preflight_runtime_exclusions(worktree)
    if not preflight["passed"]:
        raise SystemExit("capture preflight rejected: " + ",".join(preflight["reasons"]))

    identity_before = git_identity(worktree)
    if not identity_before["clean"]:
        raise SystemExit("canonical phase1 capture requires a clean worktree")
    build_provenance = validate_build_receipt(
        args.build_receipt.resolve(), args.build_policy.resolve(), worktree, binary, config
    )
    if not build_provenance.get("valid"):
        raise SystemExit("build receipt rejected: " + ",".join(build_provenance.get("rejections", [])))

    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stable: list[dict[str, Any]] = []
    last_rejections: list[str] = ["no_status_observed"]
    startup_error: str | None = None
    process: subprocess.Popen[bytes] | None = None
    server_log_output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=".raid-phase1-worldserver-", suffix=".log.tmp", dir=server_log_output.parent, delete=False
    ) as log:
        log_path = Path(log.name)
        process = subprocess.Popen(
            [str(binary), "--config", str(config)], cwd=worktree, stdin=subprocess.PIPE,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
        try:
            wait_for_prompt(process, log_path, args.startup_timeout_sec)
            assert process.stdin is not None
            deadline = time.monotonic() + args.observe_sec
            next_probe = 0.0
            seen_statuses = 0
            recovery_accepted = False
            readycheck_requested_for: tuple[Any, ...] | None = None
            while time.monotonic() < deadline and not (
                len(stable) >= args.required_stable_statuses and recovery_accepted
            ):
                if process.poll() is not None:
                    break
                if time.monotonic() >= next_probe:
                    process.stdin.write(b"botauto status\nbotauto diagnose all\nbotauto trace all 20\n")
                    process.stdin.flush()
                    next_probe = time.monotonic() + 5.0
                    time.sleep(1.0)
                    statuses = json_actions(log_path.read_bytes(), "botauto_status")
                    for status in statuses[seen_statuses:]:
                        accepted, rejections = accepted_foundation_status(status)
                        last_rejections = rejections
                        if accepted:
                            stable.append(status)
                        else:
                            stable.clear()
                    seen_statuses = len(statuses)
                    recovery_accepted, _ = accepted_native_recovery(statuses)
                    if statuses:
                        runtime = statuses[-1].get("raid_runtime") or {}
                        native = runtime.get("native_recovery") or {}
                        request_identity = (
                            runtime.get("attempt_id"), runtime.get("wipe_generation"),
                            runtime.get("boss_reset_generation"),
                        )
                        ready_for_native_check = (
                            runtime.get("alive_size") == 10
                            and runtime.get("encounter_in_progress") is False
                            and int(runtime.get("wipe_generation") or 0) > 0
                            and int(runtime.get("boss_reset_generation") or 0) > 0
                            and native.get("death_observed") is True
                            and native.get("corpse_observed") is True
                            and native.get("release_observed") is True
                            and native.get("resurrection_observed") is True
                            and native.get("runback_observed") is True
                            and native.get("ready_check_action_observed") is not True
                        )
                        if ready_for_native_check and readycheck_requested_for != request_identity:
                            # This invokes only the native Group ready-check packet path.
                            # It cannot alter encounter, death, movement, or resurrection state.
                            process.stdin.write(b"botauto readycheck\n")
                            process.stdin.flush()
                            readycheck_requested_for = request_identity
                time.sleep(0.25)

            process.stdin.write(b"botauto stop\nbotauto status\nserver exit\n")
            process.stdin.flush()
            process.wait(timeout=60)
        except Exception as error:  # captured as infrastructure evidence below
            startup_error = f"{type(error).__name__}:{error}"
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, 15)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, 9)
                    process.wait(timeout=10)
        # Move the captured file into its caller-selected immutable location;
        # do not delete the raw worldserver log after capture.
        os.replace(log_path, server_log_output)
        log_bytes = server_log_output.read_bytes()

    normalized_rows = normalized_batch_payload(log_bytes)
    demux_rejections = evidence_demux_rejections(normalized_rows)
    raw_payload_sha256, raw_payload_rows = write_normalized_batch(raw_output, normalized_rows)
    statuses = json_actions(log_bytes, "botauto_status")
    active_statuses = [
        status for status in statuses
        if isinstance(status.get("raid_runtime"), dict)
        and status["raid_runtime"].get("active") is True
    ]
    diagnoses = json_actions(log_bytes, "botauto_diagnose")
    traces = json_actions(log_bytes, "botauto_trace")
    stop_rows = json_actions(log_bytes, "botauto_stop")
    recovery_accepted, recovery_rejections = accepted_native_recovery(active_statuses)
    cleanup_status = statuses[-1] if statuses else {}
    cleanup_ok = cleanup_status.get("bots") == 0 and cleanup_status.get("lease_count") == 0
    postflight = preflight_runtime_exclusions(worktree)
    process_absent = not postflight["process_overlap"]
    forbidden_entries = _forbidden_assistance_entries(normalized_rows)
    identity_after = git_identity(worktree)
    identity_stable = identity_before == identity_after
    process_return_code = process.returncode if process is not None else None
    success = (
        startup_error is None
        and process_return_code == 0
        and len(stable) >= args.required_stable_statuses
        and recovery_accepted
        and cleanup_ok
        and bool(stop_rows and stop_rows[-1].get("ok") is True)
        and process_absent
        and postflight["passed"]
        and not forbidden_entries
        and not demux_rejections
        and identity_stable
    )
    report = {
        "schema_version": 1,
        "capture_id": "cata_raid_phase1_bwd_10n_foundation_v1",
        "classification": "success" if success else ("infrastructure_abort" if startup_error else "foundation_gate_failed"),
        "started_at_utc": started_utc,
        "identity": identity_before,
        "identity_stable_during_run": identity_stable,
        "build_provenance": build_provenance,
        "binary_sha256": build_provenance.get("binary_sha256"),
        "config_sha256": sha256_file(config),
        "worldserver_exit_code": process_return_code,
        "startup_error": startup_error,
        "required_stable_statuses": args.required_stable_statuses,
        "accepted_stable_statuses": len(stable),
        "last_foundation_rejections": last_rejections,
        "native_recovery_accepted": recovery_accepted,
        "native_recovery_rejections": recovery_rejections,
        "accepted_raid_runtime": stable[-1].get("raid_runtime") if stable else None,
        "diagnose_observed": bool(diagnoses),
        "trace_observed": bool(traces),
        "stop_observed": bool(stop_rows),
        "native_event_evidence": {
            "source": "botauto_status.raid_runtime",
            "ordered_transition_reconstruction": recovery_accepted,
            "rejections": recovery_rejections,
            "synthetic_wipe_or_encounter_command_sent": False,
        },
        "forbidden_assistance": {
            "observed": bool(forbidden_entries),
            "entries": forbidden_entries,
            "gate_passed": not forbidden_entries,
            "policy": "native encounter events only; no forced state, teleport, spawn, kill, resurrection, or aura assistance",
        },
        "watchdog": {
            "policy": "capture-process-heartbeat-and-wall-clock",
            "heartbeat_rows": len(statuses) + len(diagnoses) + len(traces),
            "observe_window_seconds": args.observe_sec,
            "startup_timeout_seconds": args.startup_timeout_sec,
            "healthy": startup_error is None and process_return_code == 0 and process_absent,
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
            "retained_rows": len(normalized_rows),
            "channels": dict(Counter(str(row.get("evidence_channel")) for row in normalized_rows)),
            "every_retained_row_demuxed": all("evidence_channel" in row for row in normalized_rows),
            "identity_rejections": demux_rejections,
            "gate_passed": not demux_rejections,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    report["artifact_inventory"] = [
        _artifact_record(raw_output, "raw_normalized_jsonl"),
        _artifact_record(server_log_output, "raw_worldserver_log"),
    ]
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


if __name__ == "__main__":
    raise SystemExit(main())
