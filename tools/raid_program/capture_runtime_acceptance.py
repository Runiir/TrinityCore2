from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

try:
    from tools.raid_program.capture_runtime_identity import (
        ROSTER_ID_FIELDS,
        STRATEGY_FIELD,
        _route_advancement_marker,
        _runtime_identity,
    )
    from tools.raid_program.capture_value_types import (
        _nonnegative_int,
        _positive_int,
    )
except ModuleNotFoundError:
    from capture_runtime_identity import (
        ROSTER_ID_FIELDS,
        STRATEGY_FIELD,
        _route_advancement_marker,
        _runtime_identity,
    )
    from capture_value_types import _nonnegative_int, _positive_int


ROOT = Path(__file__).resolve().parents[2]


def expected_bwd_10n_roster(
    profile_name: str = "blackwing_descent_10n",
) -> tuple[tuple[str, str, int, str], ...]:
    scenario = {"id": profile_name, "bots": _provisioned_bwd_bots(profile_name)}
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


def _provisioned_bwd_bots(profile_name: str = "blackwing_descent_10n") -> list[dict[str, Any]]:
    """Load the checked-in, post-normalization BWD provisioning roster.

    The capture verifier must not silently fall back to a partial roster when
    provisioning data is unavailable.  The builder's loader is used here so
    talent defaults and the checked-in gear profile overlay are represented by
    the same canonical values that generated the provisioning SQL.
    """

    try:
        from tools.bot_ml.build_validation_provisioning import (
            DEFAULT_BWD_DIAGNOSTIC_SHARD_FIXTURE,
            apply_gear_profiles,
            load_config_with_bwd_diagnostic_shards,
            load_gear_profiles,
        )

        config = load_config_with_bwd_diagnostic_shards(
            ROOT / "experiments/configs/validation_provisioning_cata_001.json",
            DEFAULT_BWD_DIAGNOSTIC_SHARD_FIXTURE,
        )
        config = apply_gear_profiles(
            config,
            load_gear_profiles(ROOT / "dataset/validation_gear_profiles/profiles.json"),
        )
        scenario = next(
            row for row in config["scenarios"] if row.get("id") == profile_name
        )
        bots = scenario.get("bots")
        if not isinstance(bots, list) or len(bots) != 10:
            raise ValueError(f"frozen BWD provisioning roster is missing for {profile_name}")
        return [row for row in bots if isinstance(row, dict)]
    except (ImportError, KeyError, OSError, StopIteration, TypeError, ValueError) as error:
        raise ValueError(f"frozen BWD identity manifest unavailable for {profile_name}: {error}") from error


def _provisioned_bwd_10n_bots() -> list[dict[str, Any]]:
    """Backward-compatible canonical-roster accessor for existing callers."""

    return _provisioned_bwd_bots("blackwing_descent_10n")


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


def _expected_identity_by_slot(
    profile_name: str = "blackwing_descent_10n",
) -> dict[str, dict[str, Any]]:
    from tools.bot_ml.build_validation_provisioning import normalized_glyph_slots

    result: dict[str, dict[str, Any]] = {}
    for bot in _provisioned_bwd_bots(profile_name):
        role = str(bot.get("role") or "")
        # Roster slot IDs are generated deterministically by the native plan.
        index = sum(1 for existing in result.values() if existing["role"] == role) + 1
        slot_id = str(bot.get("canonical_roster_slot_id") or f"raid_{role}_{index}")
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
            "account_id": bot.get("expected_account_id", bot.get("account_id")),
            "character_guid": bot.get("expected_character_guid", bot.get("character_guid")),
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


def _compact_trailing_zero_gems(values: tuple[int, ...]) -> tuple[int, ...]:
    end = len(values)
    while end and values[end - 1] == 0:
        end -= 1
    return values[:end]


def _identity_manifest_rejections(
    runtime: dict[str, Any],
    profile_name: str = "blackwing_descent_10n",
) -> list[str]:
    """Check all identity-bearing provisioning fields, fail-closed on omission."""

    try:
        expected_by_slot = _expected_identity_by_slot(profile_name)
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
        if expected.get("character_guid") is not None and row.get("guid") != expected["character_guid"]:
            reasons.append("frozen_identity_character_guid_mismatch")
        if expected.get("account_id") is not None and row.get("account_id") != expected["account_id"]:
            reasons.append("frozen_identity_account_id_mismatch")
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
                if (
                    actual[3] != item["enchant_id"]
                    or _compact_trailing_zero_gems(actual[4]) != _compact_trailing_zero_gems(item["gem_item_ids"])
                    or actual[5] != item["reforge_id"]
                ):
                    reasons.append("frozen_identity_gear_modifiers_mismatch")
    return list(dict.fromkeys(reasons))


def _roster_identity(roster: list[dict[str, Any]]) -> tuple[tuple[Any, ...], ...] | None:
    if len(roster) != 10 or any(not isinstance(row, dict) for row in roster):
        return None
    rows: list[tuple[Any, ...]] = []
    for row in sorted(roster, key=lambda value: value.get("slot") if isinstance(value.get("slot"), int) else -1):
        if any(field not in row for field in ROSTER_ID_FIELDS):
            return None
        rows.append(tuple(row[field] for field in ROSTER_ID_FIELDS))
    return tuple(rows)


def _roster_rejections(
    runtime: dict[str, Any],
    profile_name: str = "blackwing_descent_10n",
) -> list[str]:
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
    if observed_roster != expected_bwd_10n_roster(profile_name):
        reasons.append("exact_frozen_bwd_10n_roster_identity")
    if not all(row.get("active") is True for row in rows):
        reasons.append("all_roster_active")
    if not all(row.get("lease_owned") is True for row in rows):
        reasons.append("all_roster_leases_owned")
    reasons.extend(_identity_manifest_rejections(runtime, profile_name))
    return reasons


def accepted_foundation_status(
    status: dict[str, Any],
    *,
    profile_name: str = "blackwing_descent_10n",
    route_partition: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    runtime = status.get("raid_runtime") or {}
    reasons: list[str] = []
    if not isinstance(runtime, dict):
        return False, ["raid_runtime_missing"]
    route_progress = runtime.get("route_progress")
    # Phase 1's canonical foundation gate stops at Magmaw. An explicit boss
    # shard instead targets the terminal node of its own generated partition.
    route_partition = route_partition or {}
    if profile_name == "blackwing_descent_10n":
        expected_route_generation = 4
        expected_route_index = 3
    else:
        expected_route_generation = int(route_partition.get("node_count") or 0)
        expected_route_index = int(route_partition.get("terminal_index") or 0)
    expected_strategy = profile_name
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
        "strategy_owned": runtime.get("strategy_id") == expected_strategy,
        "boss_state_readback": len(runtime.get("boss_states") or []) == 6,
        "ready_check_satisfied": runtime.get("ready_check_satisfied") is True,
        "roster_composition_valid": runtime.get("roster_composition_valid") is True,
        "evidence_sequence_owned": _positive_int(runtime.get("evidence_sequence")),
        "unique_leases": runtime.get("unique_leases") is True,
        "selected_route_terminal_node": isinstance(route_progress, dict)
            and route_progress.get("generation") == expected_route_generation
            and route_progress.get("node_index") == expected_route_index,
    }
    reasons.extend(name for name, passed in checks.items() if not passed)
    reasons.extend(_roster_rejections(runtime, profile_name))
    roster = runtime.get("roster")
    roster_guids = {
        row.get("guid") for row in roster if isinstance(row, dict)
    } if isinstance(roster, list) else set()
    if runtime.get("leader_guid") not in roster_guids:
        reasons.append("leader_not_in_exact_roster")
    return not reasons, reasons


def terminal_preflight_failure_reason(
    status: dict[str, Any],
    *,
    profile_name: str = "blackwing_descent_10n",
) -> tuple[str | None, list[str]]:
    """Recognize a native admission/preflight terminal before watchdog timing.

    Validation admission is a one-shot native transaction.  A failed
    preflight leaves the generic bot status envelope alive while the raid
    runtime is terminal and empty, so the ordinary active-attempt terminal
    predicate cannot bind a ten-member roster.  This edge is an infrastructure
    failure, not a raid attempt that should consume the semantic-stall window.
    """

    runtime = status.get("raid_runtime")
    if not isinstance(runtime, dict) or runtime.get("admission_phase") != "terminal":
        return None, []
    reason = status.get("failure_reason")
    checks = {
        "terminal_preflight_status_not_ok": status.get("ok") is True,
        "terminal_preflight_action_mismatch": status.get("action") == "botauto_status",
        "terminal_preflight_profile_mismatch": status.get("active_profile") == profile_name,
        "terminal_preflight_reason_missing": isinstance(reason, str) and bool(reason.strip()),
        "terminal_preflight_reason_not_validation": (
            isinstance(reason, str)
            and reason.strip().startswith("validation_raid_preflight_")
        ),
    }
    rejections = [name for name, passed in checks.items() if not passed]
    return (reason.strip() if not rejections else None), rejections


def terminal_runtime_failure_reason(
    status: dict[str, Any],
    *,
    profile_name: str = "blackwing_descent_10n",
) -> tuple[str | None, list[str]]:
    """Return an exact active-attempt failure without requiring success state.

    A terminal failure can legitimately have dead members, an incomplete
    route, and no ready check.  It must still be bound to the selected profile,
    exact leased roster, native group/instance, and active attempt before the
    capture controller is allowed to stop the shared worldserver.
    """

    runtime = status.get("raid_runtime")
    reason = status.get("failure_reason")
    rejections: list[str] = []
    if not isinstance(reason, str) or not reason.strip():
        return None, ["terminal_failure_reason_missing"]
    if not isinstance(runtime, dict):
        return None, ["terminal_failure_runtime_missing"]
    checks = {
        "terminal_failure_status_not_ok": status.get("ok") is True,
        "terminal_failure_action_mismatch": status.get("action") == "botauto_status",
        "terminal_failure_cohort_mismatch": status.get("cohort_id") == "default",
        "terminal_failure_profile_mismatch": status.get("active_profile") == profile_name,
        "terminal_failure_bot_count_mismatch": status.get("bots") == 10,
        "terminal_failure_lease_count_mismatch": status.get("lease_count") == 10,
        "terminal_failure_runtime_inactive": runtime.get("active") is True,
        "terminal_failure_expected_size_mismatch": runtime.get("expected_size") == 10,
        "terminal_failure_active_size_mismatch": runtime.get("active_size") == 10,
        "terminal_failure_roster_incomplete": runtime.get("roster_complete") is True,
        "terminal_failure_map_mismatch": runtime.get("map_id") == 669,
        "terminal_failure_instance_missing": _positive_int(runtime.get("instance_id")),
        "terminal_failure_group_missing": _positive_int(runtime.get("group_guid")),
        "terminal_failure_attempt_missing": _positive_int(runtime.get("attempt_id")),
        "terminal_failure_assignment_missing": _positive_int(runtime.get("assignment_generation")),
        "terminal_failure_unique_leases_missing": runtime.get("unique_leases") is True,
    }
    rejections.extend(name for name, passed in checks.items() if not passed)
    rejections.extend(
        f"terminal_failure_{item}" for item in _roster_rejections(runtime, profile_name)
    )
    return (reason.strip() if not rejections else None), list(dict.fromkeys(rejections))


def accepted_native_recovery(
    statuses: list[dict[str, Any]],
    *,
    profile_name: str = "blackwing_descent_10n",
) -> tuple[bool, list[str]]:
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
        reasons.extend(
            f"native_{reason}"
            for reason in _roster_rejections(runtime, profile_name)
            if reason not in {"all_roster_active", "all_roster_leases_owned"}
        )

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

        route_progress = runtime.get("route_progress")
        boss_states = runtime.get("boss_states") or []
        exact_magmaw_engagement = (
            runtime.get("encounter_in_progress") is True
            and isinstance(route_progress, dict)
            and route_progress.get("generation") == 4
            and route_progress.get("node_index") == 3
            and isinstance(boss_states, list)
            and len(boss_states) == 6
            and boss_states[0] == 1
        )
        if engagement_index is None and exact_magmaw_engagement:
            engagement_index = index
        if exact_magmaw_engagement:
            latest_engagement_index = index
        if (
            latest_engagement_index is not None
            and index > latest_engagement_index
            and isinstance(route_progress, dict)
            and route_progress.get("generation") == 4
            and route_progress.get("node_index") == 3
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
    if engagement_index is None:
        reasons.append("native_magmaw_engagement_not_observed")
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


def native_readycheck_request_identity(status: dict[str, Any]) -> tuple[Any, ...]:
    """Bind one controller request to the exact recovery and route scope."""
    runtime = status.get("raid_runtime") or {}
    route = status.get("validation_route") or {}
    return (
        runtime.get("attempt_id"),
        runtime.get("wipe_generation"),
        runtime.get("assignment_generation"),
        route.get("generation"),
        route.get("node_id"),
    )
