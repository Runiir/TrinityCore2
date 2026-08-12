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
    "profile_generation",
    "profile_content_hash",
    "assignment_generation",
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
        raw_talents = _canonical_int_list([row.get("spell_id") for row in bot.get("talents", [])])
        talents = tuple(sorted(raw_talents)) if raw_talents is not None else None
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
        actual_talents = _canonical_int_list(row.get("talents"))
        if actual_talents is None or tuple(sorted(actual_talents)) != expected["talents"]:
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


def _runtime_identity(runtime: dict[str, Any], *, include_strategy: bool = False) -> tuple[Any, ...] | None:
    fields = IDENTITY_FIELDS + ((STRATEGY_FIELD,) if include_strategy else ())
    if not all(field in runtime for field in fields):
        return None
    return tuple(runtime[field] for field in fields)


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
        "lockout_save_matches_live_instance": runtime.get("lockout_save_id") == runtime.get("instance_id"),
        "group_owned": _positive_int(runtime.get("group_guid")),
        "leader_owned": _positive_int(runtime.get("leader_guid")),
        "server_epoch_owned": _positive_int(runtime.get("server_epoch")),
        "attempt_owned": _positive_int(runtime.get("attempt_id")),
        "profile_generation_owned": _positive_int(runtime.get("profile_generation")),
        "profile_content_hash_owned": isinstance(runtime.get("profile_content_hash"), str)
            and bool(runtime.get("profile_content_hash", "").strip()),
        "assignment_generation_owned": _positive_int(runtime.get("assignment_generation")),
        "strategy_owned": isinstance(runtime.get("strategy_id"), str) and bool(runtime.get("strategy_id", "").strip()),
        "boss_state_readback": len(runtime.get("boss_states") or []) == 6,
        "ready_check_satisfied": runtime.get("ready_check_satisfied") is True,
        "roster_composition_valid": runtime.get("roster_composition_valid") is True,
        "evidence_sequence_owned": _positive_int(runtime.get("evidence_sequence")),
        "unique_leases": runtime.get("unique_leases") is True,
    }
    reasons.extend(name for name, passed in checks.items() if not passed)
    reasons.extend(_roster_rejections(runtime))
    roster = runtime.get("roster")
    roster_guids = {
        row.get("guid") for row in roster if isinstance(row, dict)
    } if isinstance(roster, list) else set()
    if runtime.get("leader_guid") not in roster_guids:
        reasons.append("leader_not_in_exact_roster")
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
    latest_engagement_index: int | None = None
    wipe_index: int | None = None
    selected_wipe_generation = 0
    selected_engagement_sequence = 0
    boss_reset_generation_at_wipe: int | None = None
    recovery_generation_at_wipe: int | None = None
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
            for field in ("group_guid", "leader_guid", "instance_id", "lockout_save_id", "server_epoch",
                          "attempt_id", "profile_generation", "assignment_generation")
        ):
            reasons.append("native_identity_values_invalid")
        if not isinstance(runtime.get("profile_content_hash"), str) or not runtime.get("profile_content_hash", "").strip():
            reasons.append("native_profile_content_hash_invalid")
        if runtime.get("lockout_save_id") != runtime.get("instance_id"):
            reasons.append("native_lockout_instance_mismatch")
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
            runtime.get("encounter_in_progress") is True
            or any(state == 1 for state in (runtime.get("boss_states") or []))
        ):
            latest_engagement_index = index
        if (
            engagement_index is not None
            and index > engagement_index
            and generations[0] > selected_wipe_generation
            and runtime.get("wipe_state") == "wiped"
            and runtime.get("alive_size") == 0
            and runtime.get("recovery_state") in {"awaiting_native_reset", "release_resurrection_pending"}
        ):
            wipe_index = index
            selected_wipe_generation = generations[0]
            selected_engagement_sequence = (
                runtimes[latest_engagement_index].get("evidence_sequence", 0)
                if latest_engagement_index is not None and latest_engagement_index < index else 0
            )
            reset_index = None
            recovery_index = None
            declared_reset_baseline = runtime.get("boss_reset_generation_at_wipe")
            boss_reset_generation_at_wipe = (
                declared_reset_baseline
                if _nonnegative_int(declared_reset_baseline)
                and declared_reset_baseline <= generations[1]
                else generations[1]
            )
            recovery_generation_at_wipe = generations[2]
            if generations[1] > boss_reset_generation_at_wipe:
                reset_index = index
        if (
            wipe_index is not None
            and reset_index is None
            and index > wipe_index
            and boss_reset_generation_at_wipe is not None
            and generations[1] > boss_reset_generation_at_wipe
            and runtime.get("encounter_in_progress") is False
        ):
            reset_index = index
        if (
            reset_index is not None
            and recovery_index is None
            and index > reset_index
            and recovery_generation_at_wipe is not None
            and generations[2] > recovery_generation_at_wipe
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
    if selected_wipe_generation != wipe_generation:
        reasons.append("native_latest_wipe_transition_not_observed")
    for transition_name, transition_index in (
        ("wipe", wipe_index),
        ("reset", reset_index),
        ("recovery", recovery_index),
    ):
        if transition_index is not None and runtimes[transition_index].get("wipe_generation") != wipe_generation:
            reasons.append(f"native_{transition_name}_transition_wipe_scope_mismatch")
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
    if final_native.get("ready_check_assignment_generation") != runtimes[-1].get("assignment_generation"):
        reasons.append("native_ready_check_assignment_generation_mismatch")
    ready_sequence = final_native.get("ready_check_action_evidence_sequence")
    if not _positive_int(ready_sequence) or not _positive_int(final_runtime.get("evidence_sequence")) \
            or ready_sequence > final_runtime["evidence_sequence"]:
        reasons.append("native_ready_check_sequence_exceeds_runtime")
    recovery_members = final_native.get("members")
    final_roster = final_runtime.get("roster")
    roster_guids = {
        row.get("guid") for row in final_roster
        if isinstance(row, dict) and _positive_int(row.get("guid"))
    } if isinstance(final_roster, list) else set()
    if not isinstance(recovery_members, list) or len(recovery_members) != 10:
        reasons.append("native_per_member_recovery_missing")
    else:
        recovery_guids = {
            row.get("guid") for row in recovery_members
            if isinstance(row, dict) and _positive_int(row.get("guid"))
        }
        if recovery_guids != roster_guids or len(recovery_guids) != 10:
            reasons.append("native_per_member_recovery_roster_mismatch")
        sequence_fields = (
            "death_sequence", "corpse_sequence", "release_sequence",
            "runback_sequence", "reentry_sequence", "resurrection_sequence",
        )
        for row in recovery_members:
            if not isinstance(row, dict):
                reasons.append("native_per_member_recovery_invalid")
                continue
            sequences = tuple(row.get(field) for field in sequence_fields)
            if row.get("wipe_generation") != wipe_generation:
                reasons.append("native_per_member_recovery_wipe_mismatch")
            if not all(_positive_int(value) for value in sequences) or not all(
                left < right for left, right in zip(sequences, sequences[1:])
            ):
                reasons.append("native_per_member_recovery_order_invalid")
            elif not _positive_int(selected_engagement_sequence) or sequences[0] <= selected_engagement_sequence:
                reasons.append("native_per_member_recovery_predates_latest_engagement")
            elif wipe_index is None or not _positive_int(runtimes[wipe_index].get("evidence_sequence")) \
                    or sequences[0] > runtimes[wipe_index]["evidence_sequence"]:
                reasons.append("native_per_member_death_postdates_latest_wipe_snapshot")
            elif not _positive_int(final_runtime.get("evidence_sequence")) or any(
                value > final_runtime["evidence_sequence"] for value in sequences
            ):
                reasons.append("native_per_member_recovery_sequence_exceeds_runtime")

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


def semantic_progress_signature(status: dict[str, Any], diagnosis: dict[str, Any] | None) -> str:
    """Hash only raid facts whose change proves meaningful live progress.

    Timers, heartbeat counters and trace length are deliberately excluded. Boss
    health/phase, route state, combat targets, decisions and native recovery
    generations are included so a living but semantically wedged run can be
    stopped for diagnosis without imposing a raid-duration deadline.
    """
    runtime = status.get("raid_runtime") if isinstance(status.get("raid_runtime"), dict) else {}
    route = status.get("validation_route") if isinstance(status.get("validation_route"), dict) else {}
    bot_progress: list[dict[str, Any]] = []
    if isinstance(diagnosis, dict):
        for row in diagnosis.get("bots") or []:
            if not isinstance(row, dict):
                continue
            identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
            snapshot = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {}
            progress = snapshot.get("route_progress") if isinstance(snapshot.get("route_progress"), dict) else {}
            target = progress.get("target") if isinstance(progress.get("target"), dict) else {}
            state = progress.get("state") if isinstance(progress.get("state"), dict) else {}
            bot_progress.append({
                "bot_guid": identity.get("bot_guid"),
                # Decision churn is diagnostic evidence, not objective
                # progress. Keep it in the immutable raw diagnose/trace rows,
                # but do not let alternating wrong actions reset this clock.
                "target": {key: target.get(key) for key in (
                    "guid", "entry", "hp_pct", "best_hp_pct",
                )},
                "combat_state": {key: state.get(key) for key in (
                    "victim_guid", "bot_in_combat", "bot_casting",
                )},
            })
    payload = {
        "route": {key: route.get(key) for key in (
            "manifest_index", "generation", "node_id", "kind", "manifest_complete",
            "terminal_evidence", "boss_death_evidence",
        )},
        "raid": {key: runtime.get(key) for key in (
            "map_id", "instance_id", "lockout_save_id", "strategy_id",
            "assignment_generation", "boss_states", "encounter_phase",
            "encounter_in_progress", "alive_size", "wipe_state", "recovery_state",
            "wipe_generation", "boss_reset_generation", "recovery_generation",
        )},
        "metrics": {key: status.get(key) for key in (
            "kills", "deaths", "raid_boss_kills", "instance_resets",
        )},
        "bots": sorted(bot_progress, key=lambda row: int(row.get("bot_guid") or 0)),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def observe_monotonic_semantic_progress(
    state: dict[str, Any], status: dict[str, Any], diagnosis: dict[str, Any] | None,
) -> bool:
    """Update objective high-water marks and report genuine forward progress."""
    runtime = status.get("raid_runtime") if isinstance(status.get("raid_runtime"), dict) else {}
    route = status.get("validation_route") if isinstance(status.get("validation_route"), dict) else {}
    advanced = not state

    counters = {
        "route_generation": int(route.get("generation") or 0),
        "route_index": int(route.get("manifest_index") or 0),
        "route_terminal_count": len(route.get("terminal_evidence") or []),
        "boss_death_evidence_count": len(route.get("boss_death_evidence") or []),
        "wipe_generation": int(runtime.get("wipe_generation") or 0),
        "boss_reset_generation": int(runtime.get("boss_reset_generation") or 0),
        "recovery_generation": int(runtime.get("recovery_generation") or 0),
        "kills": int(status.get("kills") or 0),
        "deaths": int(status.get("deaths") or 0),
        "raid_boss_kills": int(status.get("raid_boss_kills") or 0),
        "instance_resets": int(status.get("instance_resets") or 0),
        "boss_done_count": sum(1 for value in runtime.get("boss_states") or [] if value == 3),
    }
    high_water = state.setdefault("high_water", {})
    for key, value in counters.items():
        previous = int(high_water.get(key, -1))
        if value > previous:
            advanced = True
            high_water[key] = value

    if runtime.get("encounter_in_progress") is True and not state.get("engagement_observed"):
        state["engagement_observed"] = True
        advanced = True
    if route.get("manifest_complete") is True and not state.get("manifest_complete_observed"):
        state["manifest_complete_observed"] = True
        advanced = True

    lowest_hp = state.setdefault("lowest_target_hp", {})
    if isinstance(diagnosis, dict):
        for row in diagnosis.get("bots") or []:
            if not isinstance(row, dict):
                continue
            snapshot = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {}
            progress = snapshot.get("route_progress") if isinstance(snapshot.get("route_progress"), dict) else {}
            target = progress.get("target") if isinstance(progress.get("target"), dict) else {}
            target_id = int(target.get("guid") or target.get("entry") or 0)
            hp = target.get("best_hp_pct", target.get("hp_pct"))
            if not target_id or not isinstance(hp, (int, float)) or hp <= 0:
                continue
            key = f"{int(runtime.get('instance_id') or 0)}:{int(route.get('generation') or 0)}:{target_id}"
            previous_hp = float(lowest_hp.get(key, 101.0))
            if float(hp) < previous_hp:
                lowest_hp[key] = float(hp)
                advanced = True
    return advanced


def observe_telemetry_freshness(
    state: dict[str, dict[str, float | int]], counts: dict[str, int], now: float,
    timeout_seconds: float,
) -> list[str]:
    """Update per-channel heartbeats and return channels whose output is stale.

    The canonical raid runtime is intentionally uncapped, but its control and
    evidence channels are not. A live worldserver that stops producing any one
    of status, diagnosis, or trace evidence is an infrastructure failure, not a
    healthy long boss attempt.
    """
    stale: list[str] = []
    for channel in ("status", "diagnosis", "trace"):
        channel_state = state.setdefault(channel, {
            "count": 0,
            "last_observed_monotonic": now,
        })
        count = int(counts.get(channel, 0))
        if count > int(channel_state["count"]):
            channel_state["count"] = count
            channel_state["last_observed_monotonic"] = now
        if now - float(channel_state["last_observed_monotonic"]) > timeout_seconds:
            stale.append(channel)
    return stale


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
                current_source = {
                    "commit": identity["head"],
                    "tree": identity["tree"],
                    "clean": identity["clean"],
                    "dirty": identity["dirty"],
                    "porcelain_sha256": identity["porcelain_sha256"],
                }
                if completion != current_source:
                    rejections.append("build_receipt_completion_source_mismatch")
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
        "botauto_profile": "profile_selection",
        "botauto_readycheck": "native_action",
        "botauto_stop": "cleanup",
    }
    rows = [
        {
            "normalized_schema_version": 2,
            "capture_sequence": sequence,
            "action": row.get("action"),
            "evidence_channel": channel_by_action.get(str(row.get("action")), "other"),
            "payload": row,
        }
        for sequence, row in enumerate(json_rows(log_bytes), start=1)
    ]
    # Populate diagnostic bindings for the immutable batch, but never trust
    # them during acceptance: evidence_demux_report reconstructs and replaces
    # every binding from the retained payload on every call.
    evidence_demux_report(rows)
    return rows


def _canonical_object_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _required_telemetry_envelope_report(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate the complete canonical bot roster in every diagnose/trace row.

    Status rows establish the canonical live runtime.  Diagnose and trace are
    independent retained evidence channels, so a non-empty channel alone is
    insufficient: every one of their envelopes must bind to that runtime and
    enumerate each canonical bot exactly once.
    """

    canonical_identity: tuple[Any, ...] | None = None
    canonical_roster: tuple[tuple[Any, ...], ...] | None = None
    canonical_cohort: str | None = None
    canonical_guids: set[int] | None = None
    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict) or payload.get("action") != "botauto_status":
            continue
        runtime = payload.get("raid_runtime")
        roster = runtime.get("roster") if isinstance(runtime, dict) else None
        identity = _runtime_identity(runtime, include_strategy=False) if isinstance(runtime, dict) else None
        roster_identity = _roster_identity(roster) if isinstance(roster, list) else None
        cohort = payload.get("cohort_id")
        if not isinstance(runtime, dict) or runtime.get("active") is not True:
            continue
        if identity is None or roster_identity is None or not isinstance(cohort, str) or not cohort:
            continue
        guids = [member[3] for member in roster_identity]
        if not all(_positive_int(guid) for guid in guids) or len(set(guids)) != 10:
            continue
        canonical_identity = identity
        canonical_roster = roster_identity
        canonical_cohort = cohort
        canonical_guids = {int(guid) for guid in guids}
        break

    row_rejections: dict[int, list[str]] = {}
    channel_counts = {"diagnosis": 0, "trace": 0}
    if canonical_identity is None or canonical_roster is None or canonical_cohort is None or canonical_guids is None:
        return {
            "rejections": ["evidence_demux_telemetry_canonical_runtime_missing"],
            "row_rejections": row_rejections,
            "diagnosis_envelopes": 0,
            "trace_envelopes": 0,
            "gate_passed": False,
        }

    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        action = payload.get("action")
        channel = {"botauto_diagnose": "diagnosis", "botauto_trace": "trace"}.get(action)
        if channel is None:
            continue
        channel_counts[channel] += 1
        row_reasons: list[str] = []
        if payload.get("ok") is not True:
            row_reasons.append(f"evidence_demux_{channel}_envelope_not_ok")
        runtime = payload.get("raid_runtime")
        roster = runtime.get("roster") if isinstance(runtime, dict) else None
        if (
            not isinstance(runtime, dict)
            or runtime.get("active") is not True
            or _runtime_identity(runtime, include_strategy=False) != canonical_identity
            or (_roster_identity(roster) if isinstance(roster, list) else None) != canonical_roster
            or payload.get("cohort_id") != canonical_cohort
        ):
            row_reasons.append(f"evidence_demux_{channel}_runtime_identity_unbound")

        bot_rows = payload.get("bots")
        if not isinstance(bot_rows, list):
            row_reasons.append(f"evidence_demux_{channel}_bot_rows_missing")
        elif not bot_rows:
            row_reasons.append(f"evidence_demux_{channel}_roster_empty")
        else:
            bot_guids: list[int] = []
            for bot_row in bot_rows:
                if not isinstance(bot_row, dict):
                    row_reasons.append(f"evidence_demux_{channel}_bot_row_invalid")
                    continue
                bot_guid = bot_row.get("bot_guid")
                identity_object = bot_row.get("identity")
                if isinstance(identity_object, dict):
                    bot_guid = identity_object.get("bot_guid")
                if not _positive_int(bot_guid):
                    row_reasons.append(f"evidence_demux_{channel}_bot_guid_invalid")
                    continue
                bot_guids.append(int(bot_guid))
            counts = Counter(bot_guids)
            if any(count > 1 for count in counts.values()):
                row_reasons.append(f"evidence_demux_{channel}_duplicate_bot_guid")
            if any(guid not in canonical_guids for guid in counts):
                row_reasons.append(f"evidence_demux_{channel}_bot_outside_roster")
            if set(bot_guids) != canonical_guids:
                row_reasons.append(f"evidence_demux_{channel}_canonical_roster_incomplete")
            if len(bot_guids) != 10:
                row_reasons.append(f"evidence_demux_{channel}_bot_row_count_invalid")
        if row_reasons:
            row_rejections[int(row.get("capture_sequence") or 0)] = list(dict.fromkeys(row_reasons))

    rejections = [
        reason
        for reasons in row_rejections.values()
        for reason in reasons
    ]
    for channel, count in channel_counts.items():
        if count == 0:
            rejections.append(f"evidence_demux_{channel}_roster_envelope_missing")
    unique_rejections = list(dict.fromkeys(rejections))
    return {
        "rejections": unique_rejections,
        "row_rejections": row_rejections,
        "diagnosis_envelopes": channel_counts["diagnosis"],
        "trace_envelopes": channel_counts["trace"],
        "gate_passed": not unique_rejections,
    }


def evidence_demux_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Independently bind every retained JSON row to one raid lifecycle."""

    reasons: list[str] = []
    known_actions = {
        "botauto_profile", "botauto_status", "botauto_diagnose", "botauto_trace",
        "botauto_readycheck", "botauto_stop",
    }
    canonical_identity: tuple[Any, ...] | None = None
    canonical_roster: tuple[tuple[Any, ...], ...] | None = None
    canonical_cohort: str | None = None
    roster_guids: set[int] = set()
    canonical_identity_sha256: str | None = None
    canonical_roster_sha256: str | None = None
    canonical_active_sequence: int | None = None

    for row in rows:
        # An outer annotation is evidence output, not evidence input.  Replace
        # it before reconstructing so a forged binding can never self-certify.
        row["identity_binding"] = {
            "state": "rejected",
            "scope": "unknown",
            "canonical_identity_sha256": None,
            "cohort_id": None,
            "roster_sha256": None,
            "binding_source": "retained_payload_reconstruction",
            "reasons": [],
        }

    # First establish canonical identity only from a complete active status.
    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict) or payload.get("action") != "botauto_status":
            continue
        runtime = payload.get("raid_runtime")
        if not isinstance(runtime, dict) or runtime.get("active") is not True:
            continue
        identity = _runtime_identity(runtime, include_strategy=False)
        roster = runtime.get("roster")
        roster_identity = _roster_identity(roster) if isinstance(roster, list) else None
        cohort = payload.get("cohort_id")
        roster_guid_values = (
            [member[3] for member in roster_identity]
            if roster_identity is not None else []
        )
        if (
            identity is not None
            and roster_identity is not None
            and all(_positive_int(guid) for guid in roster_guid_values)
            and len(set(roster_guid_values)) == 10
            and isinstance(cohort, str)
            and cohort
        ):
            canonical_identity = identity
            canonical_roster = roster_identity
            canonical_cohort = cohort
            canonical_active_sequence = row.get("capture_sequence")
            roster_guids = {int(member[3]) for member in roster_identity if _positive_int(member[3])}
            canonical_roster_sha256 = _canonical_object_sha256(roster_identity)
            canonical_identity_sha256 = _canonical_object_sha256(
                {
                    "cohort_id": canonical_cohort,
                    "runtime_identity": canonical_identity,
                    "roster_sha256": canonical_roster_sha256,
                }
            )
            break
    if canonical_identity is None:
        telemetry_envelopes = _required_telemetry_envelope_report(rows)
        for row in rows:
            row["identity_binding"]["reasons"] = ["evidence_demux_no_active_raid_rows"]
        return {
            "rejections": ["evidence_demux_no_active_raid_rows"],
            "retained_rows": len(rows),
            "bound_rows": 0,
            "rejected_rows": len(rows),
            "unchecked_rows": 0,
            "canonical_identity_sha256": None,
            "canonical_roster_sha256": None,
            "required_telemetry_envelopes": telemetry_envelopes,
            "gate_passed": False,
        }

    telemetry_envelopes = _required_telemetry_envelope_report(rows)
    stop_seen = False
    inactive_cleanup_seen = False
    observed_actions: set[str] = set()
    previous_strategy: str | None = None
    previous_route_advance = 0
    profile_selection_seen = False
    for expected_sequence, row in enumerate(rows, start=1):
        binding = row["identity_binding"]
        binding.update(
            canonical_identity_sha256=canonical_identity_sha256,
            cohort_id=canonical_cohort,
            roster_sha256=canonical_roster_sha256,
        )
        row_reasons: list[str] = binding["reasons"]

        def reject(reason: str) -> None:
            row_reasons.append(reason)
            reasons.append(reason)

        payload = row.get("payload")
        if not isinstance(payload, dict):
            reject("evidence_demux_payload_missing")
            continue
        action = payload.get("action")
        if row.get("capture_sequence") != expected_sequence:
            reject("evidence_demux_sequence_invalid")
        if row.get("action") != action:
            reject("evidence_demux_wrapper_action_mismatch")
        if action not in known_actions:
            reject("evidence_demux_unclassified_row")
            continue
        observed_actions.add(str(action))

        if action == "botauto_profile":
            binding["scope"] = "pre_start_profile"
            if canonical_cohort != "default" or payload.get("cohort_id") != canonical_cohort:
                reject("evidence_demux_profile_cohort_mismatch")
            if payload.get("ok") is not True or payload.get("active_profile") != "blackwing_descent_10n":
                reject("evidence_demux_profile_selection_invalid")
            if profile_selection_seen:
                reject("evidence_demux_duplicate_profile_selection")
            if (not isinstance(canonical_active_sequence, int)
                    or expected_sequence >= canonical_active_sequence):
                reject("evidence_demux_profile_selection_not_before_active_status")
            profile_selection_seen = True
            if not row_reasons:
                binding["state"] = "bound"
            continue

        runtime_key = "raid_runtime_before_cleanup" if action == "botauto_stop" else "raid_runtime"
        runtime = payload.get(runtime_key)
        if action == "botauto_status" and isinstance(runtime, dict) and runtime.get("active") is False:
            binding["scope"] = "post_cleanup"
            if not stop_seen:
                reject("evidence_demux_inactive_status_before_stop")
            if payload.get("cohort_id") != canonical_cohort:
                reject("evidence_demux_cross_identity_row")
            if payload.get("bots") != 0 or payload.get("lease_count") != 0:
                reject("evidence_demux_cleanup_not_empty")
            if (
                payload.get("server_epoch") != canonical_identity[9]
                or payload.get("attempt_id") != canonical_identity[10]
                or _runtime_identity(runtime, include_strategy=False) != canonical_identity
            ):
                reject("evidence_demux_cross_identity_row")
            inactive_cleanup_seen = True
            if not row_reasons:
                binding["state"] = "bound"
            continue

        binding["scope"] = "pre_cleanup_runtime" if action == "botauto_stop" else "active_runtime"
        if stop_seen:
            reject("evidence_demux_active_row_after_stop")
        if not isinstance(runtime, dict) or runtime.get("active") is not True:
            reject("evidence_demux_identity_missing")
            continue
        identity = _runtime_identity(runtime, include_strategy=False)
        roster = runtime.get("roster")
        roster_identity = _roster_identity(roster) if isinstance(roster, list) else None
        if (identity != canonical_identity or roster_identity != canonical_roster
                or payload.get("cohort_id") != canonical_cohort):
            reject("evidence_demux_cross_identity_row")
        strategy = runtime.get(STRATEGY_FIELD)
        route_marker = _route_advancement_marker(runtime)
        if not isinstance(strategy, str) or not strategy.strip():
            reject("evidence_demux_strategy_identity_missing")
        elif previous_strategy is not None and strategy != previous_strategy:
            transition = runtime.get("strategy_transition")
            if not (
                isinstance(transition, dict)
                and transition.get("from_strategy") == previous_strategy
                and transition.get("to_strategy") == strategy
                and transition.get("advanced") is True
                and route_marker is not None
                and route_marker > previous_route_advance
            ):
                reject("evidence_demux_strategy_transition_without_route_advancement")
        if route_marker is not None:
            previous_route_advance = max(previous_route_advance, route_marker)
        if isinstance(strategy, str) and strategy.strip():
            previous_strategy = strategy

        if action == "botauto_stop":
            if stop_seen:
                reject("evidence_demux_duplicate_stop")
            cleanup = payload.get("post_cleanup")
            if (payload.get("server_epoch") != canonical_identity[9]
                    or payload.get("attempt_id") != canonical_identity[10]
                    or not isinstance(cleanup, dict) or cleanup.get("active") is not False
                    or cleanup.get("bots") != 0 or cleanup.get("lease_count") != 0):
                reject("evidence_demux_cleanup_identity_invalid")
            stop_seen = True

        for reason in telemetry_envelopes["row_rejections"].get(expected_sequence, []):
            reject(reason)

        bot_rows = payload.get("bots")
        if isinstance(bot_rows, list):
            for bot_row in bot_rows:
                if not isinstance(bot_row, dict):
                    reject("evidence_demux_bot_row_invalid")
                    continue
                bot_guid = bot_row.get("bot_guid")
                identity_object = bot_row.get("identity")
                if isinstance(identity_object, dict):
                    bot_guid = identity_object.get("bot_guid")
                if not _positive_int(bot_guid) or int(bot_guid) not in roster_guids:
                    reject("evidence_demux_bot_outside_roster")
        if not row_reasons:
            binding["state"] = "bound"
    if not stop_seen:
        reasons.append("evidence_demux_cleanup_missing")
    if not inactive_cleanup_seen:
        reasons.append("evidence_demux_inactive_cleanup_missing")
    reasons.extend(telemetry_envelopes["rejections"])
    for required_action in known_actions - {"botauto_profile"}:
        if required_action not in observed_actions:
            reasons.append(f"evidence_demux_required_action_missing:{required_action}")
    unique_reasons = list(dict.fromkeys(reasons))
    states = Counter(
        str((row.get("identity_binding") or {}).get("state", "unchecked"))
        for row in rows
    )
    unchecked = len(rows) - states.get("bound", 0) - states.get("rejected", 0)
    return {
        "rejections": unique_reasons,
        "retained_rows": len(rows),
        "bound_rows": states.get("bound", 0),
        "rejected_rows": states.get("rejected", 0),
        "unchecked_rows": unchecked,
        "canonical_identity_sha256": canonical_identity_sha256,
        "canonical_roster_sha256": canonical_roster_sha256,
        "required_telemetry_envelopes": telemetry_envelopes,
        "gate_passed": not unique_reasons and states.get("bound", 0) == len(rows) and unchecked == 0,
    }


def evidence_demux_rejections(rows: list[dict[str, Any]]) -> list[str]:
    return evidence_demux_report(rows)["rejections"]


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
                # This diagnostic means that no fallback was available or
                # executed; its wording must not invert the evidence.
                negative_fallback_marker = child == "blocked_no_fallback"
                if (key in FORBIDDEN_MARKER_FIELDS and isinstance(child, str)
                        and not negative_fallback_marker and FORBIDDEN_MARKER_RE.search(child)):
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


def validate_runtime_profile_assets(
    worktree: Path,
    reference_worktree: Path = ROOT,
    profile_name: str = "blackwing_descent_10n",
    require_dvc_lineage: bool = True,
) -> dict[str, Any]:
    """Fail closed when the isolated live worktree lacks frozen route data."""

    reasons: list[str] = []
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
        if route.get("scenario_id") != profile_name:
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

    route_rows = 0
    route_sha256 = None
    reference_route_sha256 = None
    if route_path is not None:
        try:
            route_bytes = route_path.read_bytes()
            if not route_bytes:
                reasons.append("worktree_route_manifest_empty")
            if len(route_bytes) > 4 * 1024 * 1024:
                reasons.append("worktree_route_manifest_oversized")
            route_sha256 = hashlib.sha256(route_bytes).hexdigest()
            rows = [json.loads(line) for line in route_bytes.decode("utf-8").splitlines() if line.strip()]
            matching_rows = [row for row in rows if isinstance(row, dict) and row.get("scenario_id") == profile_name]
            route_rows = len(matching_rows)
            if route_rows != 8:
                reasons.append("worktree_route_expected_eight_rows")
            node_ids = [str(row.get("route_node_id") or "") for row in matching_rows]
            kinds = [str(row.get("kind") or "") for row in matching_rows]
            if any(not node_id for node_id in node_ids):
                reasons.append("worktree_route_node_id_missing")
            if len(set(node_ids)) != len(node_ids):
                reasons.append("worktree_route_node_id_duplicated")
            if any(not kind for kind in kinds):
                reasons.append("worktree_route_kind_missing")
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
        result = subprocess.run(
            ["pixi", "run", "dvc", "status", "validation_scenarios"],
            cwd=worktree,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
            check=False,
        )
        dvc_status = result.stdout.strip()
        if result.returncode != 0 or dvc_status != "Data and pipelines are up to date.":
            reasons.append("runtime_route_dvc_lineage_dirty")

    return {
        "profile_name": profile_name,
        "profile_manifest": str(worktree / profile_relative),
        "route_manifest": str(route_path) if route_path else None,
        "route_sha256": route_sha256,
        "reference_route_sha256": reference_route_sha256,
        "matching_route_rows": route_rows,
        "dvc_stage": "validation_scenarios",
        "dvc_status": dvc_status,
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
    parser.add_argument("--build-attestation", type=Path, default=None)
    parser.add_argument("--worktree", type=Path, default=ROOT)
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
    parser.add_argument("--telemetry-timeout-sec", type=int, default=30)
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
    if args.observe_sec < 0 or 0 < args.observe_sec < 30 or args.required_stable_statuses < 2:
        raise SystemExit(
            "observation must be uncapped (0) or at least 30 seconds and require at least two stable statuses"
        )
    if args.semantic_stall_sec < 60 or args.semantic_stall_min_samples < 3:
        raise SystemExit("semantic stall detection requires at least 60 seconds and three samples")
    if args.telemetry_timeout_sec < 15:
        raise SystemExit("telemetry freshness timeout must be at least 15 seconds")
    preflight = preflight_runtime_exclusions(worktree)
    if not preflight["passed"]:
        raise SystemExit("capture preflight rejected: " + ",".join(preflight["reasons"]))

    identity_before = git_identity(worktree)
    if not identity_before["clean"]:
        raise SystemExit("canonical phase1 capture requires a clean worktree")
    runtime_assets = validate_runtime_profile_assets(worktree)
    if not runtime_assets["passed"]:
        raise SystemExit("runtime profile assets rejected: " + ",".join(runtime_assets["reasons"]))
    build_provenance = validate_build_receipt(
        args.build_receipt.resolve(),
        (worktree / "experiments/configs/cata_raid_build_resource_policy_degraded_v8.json").resolve(),
        worktree, binary, config,
        args.build_attestation.resolve() if args.build_attestation is not None else None,
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
            # Bind the canonical run to the frozen BWD 10N runtime profile.
            # The test worldserver configuration deliberately has AutoStart
            # disabled, so an explicit native operator command is required;
            # omitting it would only poll an inactive default cohort forever.
            process.stdin.write(b"botauto start blackwing_descent_10n\n")
            process.stdin.flush()
            time.sleep(1.0)
            # Canonical raid validation is terminal-gate driven. Raid and boss
            # duration alone must never end an otherwise healthy run. A
            # positive limit remains available only for explicitly bounded
            # diagnostics and tests; zero is deliberately uncapped.
            deadline = time.monotonic() + args.observe_sec if args.observe_sec else None
            next_probe = 0.0
            seen_statuses = 0
            recovery_accepted = False
            readycheck_requested_for: tuple[Any, ...] | None = None
            semantic_progress_state: dict[str, Any] = {}
            last_semantic_progress_at = time.monotonic()
            unchanged_semantic_samples = 0
            semantic_stall: dict[str, Any] = {"detected": False}
            monitor_started_at = time.monotonic()
            telemetry_freshness: dict[str, dict[str, float | int]] = {}
            telemetry_abort: dict[str, Any] = {"detected": False}
            while (deadline is None or time.monotonic() < deadline) and not (
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
                    diagnoses_now = json_actions(log_path.read_bytes(), "botauto_diagnose")
                    traces_now = json_actions(log_path.read_bytes(), "botauto_trace")
                    telemetry_now = time.monotonic()
                    stale_channels = observe_telemetry_freshness(
                        telemetry_freshness,
                        {
                            "status": len(statuses),
                            "diagnosis": len(diagnoses_now),
                            "trace": len(traces_now),
                        },
                        telemetry_now,
                        args.telemetry_timeout_sec,
                    )
                    if stale_channels:
                        telemetry_abort = {
                            "detected": True,
                            "classification": "infrastructure_abort",
                            "reason": "telemetry_channel_stale",
                            "stale_channels": stale_channels,
                            "timeout_seconds": args.telemetry_timeout_sec,
                            "elapsed_seconds": round(telemetry_now - monitor_started_at, 3),
                            "channel_state": telemetry_freshness,
                        }
                        break
                    if statuses:
                        signature = semantic_progress_signature(
                            statuses[-1], diagnoses_now[-1] if diagnoses_now else None,
                        )
                        if observe_monotonic_semantic_progress(
                            semantic_progress_state,
                            statuses[-1], diagnoses_now[-1] if diagnoses_now else None,
                        ):
                            last_semantic_progress_at = time.monotonic()
                            unchanged_semantic_samples = 1
                        else:
                            unchanged_semantic_samples += 1
                        stalled_for = time.monotonic() - last_semantic_progress_at
                        if (unchanged_semantic_samples >= args.semantic_stall_min_samples
                                and stalled_for >= args.semantic_stall_sec):
                            semantic_stall = {
                                "detected": True,
                                "stalled_for_seconds": round(stalled_for, 3),
                                "unchanged_samples": unchanged_semantic_samples,
                                "semantic_signature": signature,
                                "monotonic_progress_state": semantic_progress_state,
                                "route": statuses[-1].get("validation_route"),
                                "raid_runtime": statuses[-1].get("raid_runtime"),
                                "diagnosis_rows": len(diagnoses_now),
                            }
                            break
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
    demux_report = evidence_demux_report(normalized_rows)
    demux_rejections = demux_report["rejections"]
    telemetry_envelopes = _required_telemetry_envelope_report(normalized_rows)
    raw_payload_sha256, raw_payload_rows = write_normalized_batch(raw_output, normalized_rows)
    statuses = json_actions(log_bytes, "botauto_status")
    active_statuses = [
        status for status in statuses
        if isinstance(status.get("raid_runtime"), dict)
        and status["raid_runtime"].get("active") is True
    ]
    diagnoses = json_actions(log_bytes, "botauto_diagnose")
    traces = json_actions(log_bytes, "botauto_trace")
    profiles = json_actions(log_bytes, "botauto_profile")
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
    semantic_stall = locals().get("semantic_stall", {"detected": False})
    telemetry_abort = locals().get("telemetry_abort", {"detected": False})
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
        and telemetry_envelopes["gate_passed"]
        and len(profiles) == 1
        and profiles[0].get("ok") is True
        and profiles[0].get("cohort_id") == "default"
        and profiles[0].get("active_profile") == "blackwing_descent_10n"
        and identity_stable
        and semantic_stall.get("detected") is not True
        and telemetry_abort.get("detected") is not True
        and bool(diagnoses)
        and bool(traces)
    )
    report = {
        "schema_version": 1,
        "capture_id": "cata_raid_phase1_bwd_10n_foundation_v1",
        "classification": "success" if success else (
            "infrastructure_abort" if startup_error or telemetry_abort.get("detected") else (
                "incomplete_evidence" if semantic_stall.get("detected") else "foundation_gate_failed"
            )
        ),
        "started_at_utc": started_utc,
        "identity": identity_before,
        "identity_stable_during_run": identity_stable,
        "build_provenance": build_provenance,
        "runtime_profile_assets": runtime_assets,
        "binary_sha256": build_provenance.get("binary_sha256"),
        "config_sha256": sha256_file(config),
        "worldserver_exit_code": process_return_code,
        "startup_error": startup_error,
        "required_stable_statuses": args.required_stable_statuses,
        "accepted_stable_statuses": len(stable),
        "last_foundation_rejections": last_rejections,
        "native_recovery_accepted": recovery_accepted,
        "native_recovery_rejections": recovery_rejections,
        "semantic_stall": semantic_stall,
        "telemetry_abort": telemetry_abort,
        "accepted_raid_runtime": stable[-1].get("raid_runtime") if stable else None,
        "diagnose_observed": bool(diagnoses),
        "trace_observed": bool(traces),
        "required_telemetry_envelopes": telemetry_envelopes,
        "profile_selection_observed": len(profiles) == 1,
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
            "policy": "capture-process-heartbeat-terminal-gate-driven",
            "heartbeat_rows": len(statuses) + len(diagnoses) + len(traces),
            "wall_clock_mode": "uncapped" if args.observe_sec == 0 else "bounded_diagnostic",
            "observe_window_seconds": args.observe_sec if args.observe_sec else None,
            "startup_timeout_seconds": args.startup_timeout_sec,
            "semantic_stall_seconds": args.semantic_stall_sec,
            "semantic_stall_min_samples": args.semantic_stall_min_samples,
            "telemetry_timeout_seconds": args.telemetry_timeout_sec,
            "required_channels": ["status", "diagnosis", "trace"],
            "healthy": (
                startup_error is None
                and telemetry_abort.get("detected") is not True
                and bool(statuses) and bool(diagnoses) and bool(traces)
                and process_return_code == 0 and process_absent
            ),
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
            "normalized_schema_version": 2,
            "retained_rows": demux_report["retained_rows"],
            "bound_rows": demux_report["bound_rows"],
            "rejected_rows": demux_report["rejected_rows"],
            "unchecked_rows": demux_report["unchecked_rows"],
            "canonical_identity_sha256": demux_report["canonical_identity_sha256"],
            "canonical_roster_sha256": demux_report["canonical_roster_sha256"],
            "required_telemetry_envelopes": demux_report["required_telemetry_envelopes"],
            "channels": dict(Counter(str(row.get("evidence_channel")) for row in normalized_rows)),
            "every_retained_row_demuxed": (
                demux_report["bound_rows"] == demux_report["retained_rows"]
                and demux_report["unchecked_rows"] == 0
            ),
            "identity_rejections": demux_rejections,
            "gate_passed": demux_report["gate_passed"],
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
