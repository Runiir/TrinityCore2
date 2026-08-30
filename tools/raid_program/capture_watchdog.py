from __future__ import annotations

import json
from math import isfinite
from typing import Any

try:
    from tools.raid_program.capture_value_types import _positive_int
except ModuleNotFoundError:
    from capture_value_types import _positive_int


DEFAULT_MAX_REPEATED_DECISIONS = 20
DEFAULT_MAX_DEATH_LOOPS = 3
DEFAULT_STALLED_CANDIDATE_NO_PROGRESS_MS = 20_000

_WATCHDOG_DEATH_ACTIONS = {
    "death",
    "repeated_death",
    "death_loop",
    "raid_wipe",
}
_WATCHDOG_SUCCESSFUL_NATIVE_ACTIONS = frozenset({
    "spell_cast",
    "cast_combat_spell",
    "attack",
    "move_out_of_hazard",
    "trash_action",
})
_WATCHDOG_TRANSIENT_RECOVERY_RESULTS = {
    "native_recovery_wait_hostile_activity",
    "native_recovery_wait_native_reset",
}
_WATCHDOG_FAILURE_TOKENS = (
    "invalid",
    "unreachable",
    "rejected",
    "failed",
    "failure",
    "no_candidate",
)
_WATCHDOG_NO_PROGRESS_DECISIONS = frozenset({
    ("validation_route_regroup", "hold_anchor_no_focus"),
    ("validation_route_hold_anchor", "hold_anchor_no_focus"),
})
_WATCHDOG_STALLED_CANDIDATE_FAILURES = frozenset({
    ("adaptive_magmaw", "native_move_retryable"),
})
_CONTROLLER_TERMINAL_FAILURE_REASONS = frozenset({
    "semantic_stall",
    "repeated_decision_watchdog",
    "death_loop_watchdog",
})


def _watchdog_route_scope(value: dict[str, Any] | None) -> tuple[str, int]:
    """Return the exact route node/generation scope carried by one payload."""

    if not isinstance(value, dict):
        return "", 0
    route = value.get("validation_route")
    if not isinstance(route, dict):
        runtime = value.get("raid_runtime")
        route = runtime.get("validation_route") if isinstance(runtime, dict) else None
    if not isinstance(route, dict):
        return "", 0
    node_id = str(route.get("node_id") or "")
    try:
        generation = int(route.get("generation") or 0)
    except (TypeError, ValueError):
        generation = 0
    return node_id, generation


def _watchdog_entry_scope(
    entry: dict[str, Any], current_scope: tuple[str, int],
) -> tuple[str, int]:
    """Bind a trace entry to its explicit route scope or the current status."""

    try:
        generation = int(entry.get("route_generation") or 0)
    except (TypeError, ValueError):
        generation = 0
    node_id = str(entry.get("route_node_id") or "")
    if node_id and generation > 0:
        return node_id, generation
    return current_scope


def _watchdog_failure_outcome(entry: dict[str, Any]) -> str:
    """Return the current decision result before historical recovery state.

    ``recovery_result`` is serialized on every trace row from the bot's
    previous recovery state.  The decision ``result`` is the only field that
    describes the row being classified, so a successful current decision must
    not inherit a stale recovery failure token.
    """

    for field in ("result", "reason", "reason_code", "recovery_result"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _watchdog_native_consecutive_count(entry: dict[str, Any]) -> int | None:
    """Read the native consecutive counter without treating it as cumulative.

    ``fingerprint_repeat_count`` is a lifetime counter for one fingerprint and
    can stay large while successful decisions are interleaved.  The native
    consecutive counter is the only trustworthy threshold signal when the
    producer supplies it.  ``None`` means the older payload has no such field
    and the controller may use its local fallback.
    """

    if "consecutive_same_decision_count" not in entry:
        return None
    try:
        value = int(entry.get("consecutive_same_decision_count") or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def _watchdog_is_repeated_decision(entry: dict[str, Any]) -> bool:
    """Identify a failed route decision without counting normal wait churn."""

    action = str(entry.get("action") or "")
    outcome = _watchdog_failure_outcome(entry)
    if not outcome:
        return False
    if outcome in _WATCHDOG_TRANSIENT_RECOVERY_RESULTS:
        return False
    lowered = outcome.lower()
    if any(token in lowered for token in _WATCHDOG_FAILURE_TOKENS):
        return True
    if (action, outcome) in _WATCHDOG_NO_PROGRESS_DECISIONS:
        return True
    # Native recovery entries with a non-transient result are route decisions
    # even when a producer gives the result a neutral spelling.
    # An explicit current result is authoritative, including ``ok``.  Only
    # retain the legacy action-only fallback for rows without that field.
    return action == "validation_route_recovery" and not (
        isinstance(entry.get("result"), str) and entry.get("result", "").strip()
    )


def _watchdog_stalled_candidate_failure(
    bot: dict[str, Any], *, max_repeated_decisions: int,
) -> dict[str, Any] | None:
    """Expose a failed movement candidate hidden by a successful wait action.

    Canary115 repeatedly committed the prepull-consumable wait lane while the
    Magmaw formation movement candidate failed. The top-level decision was
    therefore ``ok`` for over five minutes even though the bot had not moved.
    Require both a known failed candidate and a full watchdog window without
    movement progress so ordinary retryable movement is never terminal.
    """

    snapshot = bot.get("snapshot") if isinstance(bot.get("snapshot"), dict) else {}
    movement = snapshot.get("movement") if isinstance(snapshot.get("movement"), dict) else {}
    if movement.get("is_moving") is True:
        return None
    try:
        stalled_ms = int(movement.get("time_since_last_progress_ms") or 0)
    except (TypeError, ValueError):
        stalled_ms = 0
    if stalled_ms < DEFAULT_STALLED_CANDIDATE_NO_PROGRESS_MS:
        return None

    decision = snapshot.get("decision") if isinstance(snapshot.get("decision"), dict) else {}
    native_count = _watchdog_native_consecutive_count(decision)
    if native_count is None:
        try:
            native_count = int(decision.get("fingerprint_repeat_count") or 0)
        except (TypeError, ValueError):
            native_count = 0
    if native_count < max_repeated_decisions:
        return None

    diagnosis = bot.get("diagnosis") if isinstance(bot.get("diagnosis"), dict) else {}
    kernel = diagnosis.get("decision_kernel") if isinstance(diagnosis.get("decision_kernel"), dict) else {}
    for candidate in kernel.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        source = str(candidate.get("source") or "")
        reason = str(candidate.get("reason") or "")
        if (source, reason) not in _WATCHDOG_STALLED_CANDIDATE_FAILURES:
            continue
        if candidate.get("phase") != "failed" or candidate.get("status") != "attempted":
            continue
        return {
            "action": f"{source}_movement",
            "outcome": reason,
            "repeat_count": native_count,
            "fingerprint_hash": int(decision.get("fingerprint_hash") or 0),
        }
    return None


def _watchdog_is_local_no_progress_decision(entry: dict[str, Any]) -> bool:
    """Identify route no-progress rows whose native count is another lane.

    The regroup event is emitted before the final hold-anchor decision.  Its
    native consecutive counter can therefore remain at one even when the
    same no-focus event is repeated.  Count this exact pair locally, while
    retaining native consecutive semantics for ordinary failure rows.
    """

    return (
        str(entry.get("action") or ""),
        _watchdog_failure_outcome(entry),
    ) in _WATCHDOG_NO_PROGRESS_DECISIONS


def _watchdog_trace_group_key(entry: dict[str, Any]) -> tuple[str, int]:
    """Identify one bot decision tick in a trace delta.

    Native trace producers emit several rows for one decision: an adapter or
    mechanic row can share the decision sequence with the native spell row.
    Prefer that sequence when present.  Older payloads may have only the
    per-entry sequence, with timestamp as the final compatibility fallback.
    """

    for field in ("decision_sequence", "decision_tick"):
        try:
            value = int(entry.get(field) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return field, value
    try:
        sequence = int(entry.get("sequence") or 0)
    except (TypeError, ValueError):
        sequence = 0
    if sequence > 0:
        return "sequence", sequence
    try:
        timestamp = int(entry.get("timestamp_ms") or 0)
    except (TypeError, ValueError):
        timestamp = 0
    return "timestamp_ms", max(0, timestamp)


def _watchdog_is_successful_native_action(entry: dict[str, Any]) -> bool:
    """Return whether a trace row is a successful primary bot action.

    Validation-route mechanic/recovery rows are subordinate evidence.  A
    successful native/brain row in the same decision tick proves that the bot
    made progress through the primary action lane, so the subordinate failure
    must not be attributed as a repeated-decision failure for that tick.
    """

    return (
        entry.get("result") == "ok"
        and str(entry.get("action") or "") in _WATCHDOG_SUCCESSFUL_NATIVE_ACTIONS
    )


def _watchdog_representative_repeated_failure(
    entries: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Select one deterministic failed decision from a complete tick group."""

    failures = [entry for entry in entries if _watchdog_is_repeated_decision(entry)]
    if not failures:
        return None

    def sort_key(entry: dict[str, Any]) -> tuple[int, int, str, str, int]:
        native_count = _watchdog_native_consecutive_count(entry) or 0
        action = str(entry.get("action") or "")
        outcome = _watchdog_failure_outcome(entry)
        try:
            sequence = int(entry.get("sequence") or 0)
        except (TypeError, ValueError):
            sequence = 0
        return (
            native_count,
            int(action == "validation_route_mechanic"),
            action,
            outcome,
            sequence,
        )

    return max(failures, key=sort_key)


def _watchdog_route_progress_scope(
    route_progress: dict[str, Any] | None,
    current_scope: tuple[str, int],
) -> tuple[str, int]:
    """Resolve the route scope carried by a bot route-progress snapshot."""

    if not isinstance(route_progress, dict):
        return current_scope
    route = route_progress.get("route")
    if not isinstance(route, dict):
        return current_scope
    return _watchdog_entry_scope(
        {
            "route_node_id": route.get("node_id"),
            "route_generation": route.get("generation"),
        },
        current_scope,
    )


def _watchdog_target_progress(
    state: dict[str, Any],
    status: dict[str, Any],
    scope: tuple[str, int],
    route_progress: dict[str, Any] | None,
    *,
    bot_key: str = "",
) -> bool:
    """Record a lower target high-water mark for one exact watchdog scope.

    Route mechanics can report a failed hazard-exit decision while the party
    is still damaging the target.  That is objective progress, even when the
    decision outcome itself is repeated.  Keep this high-water mark separate
    from the semantic-stall state because the watchdog must reset only the
    repeated-decision counter for the scope that actually progressed.
    """

    if not isinstance(route_progress, dict) or scope == ("", 0):
        return False
    target = route_progress.get("target")
    if not isinstance(target, dict):
        return False
    try:
        target_id = int(target.get("entry") or target.get("guid") or 0)
    except (TypeError, ValueError):
        target_id = 0
    if target_id <= 0:
        return False
    hp = target.get("best_hp_pct", target.get("hp_pct"))
    if (
        isinstance(hp, bool)
        or not isinstance(hp, (int, float))
        or not isfinite(float(hp))
        or hp <= 0
    ):
        return False
    runtime = status.get("raid_runtime")
    runtime = runtime if isinstance(runtime, dict) else {}
    key = json.dumps(
        [int(runtime.get("instance_id") or 0), scope[0], scope[1], bot_key, target_id],
        separators=(",", ":"),
    )
    high_water = state.setdefault("watchdog_target_hp_high_water", {})
    previous = high_water.get(key)
    high_water[key] = float(hp) if previous is None else min(float(previous), float(hp))
    return previous is not None and float(hp) < float(previous)


def _watchdog_progress_reset_reason(route_progress: dict[str, Any] | None) -> str:
    """Return the producer reason attached to objective target progress."""

    no_progress = route_progress.get("no_progress") if isinstance(route_progress, dict) else None
    reason = no_progress.get("reason") if isinstance(no_progress, dict) else None
    return str(reason).strip() if isinstance(reason, str) and reason.strip() else "target_hp_decrease"


def _watchdog_reset_repeated_scope(
    state: dict[str, Any], scope_key: str, *, bot_key: str = "",
) -> int:
    """Forget repeated decisions invalidated by one bot's progress."""

    repeated_counts = state.setdefault("repeated_decision_counts", {})
    for key in list(repeated_counts):
        try:
            decoded = json.loads(key)
        except (TypeError, ValueError):
            continue
        if (
            isinstance(decoded, list)
            and len(decoded) >= 2
            and decoded[0] == scope_key
            and (not bot_key or str(decoded[1]) == bot_key)
        ):
            del repeated_counts[key]

    scope_repeated_max = state.setdefault("scope_repeated_max", {})
    remaining_max = 0
    for key, value in repeated_counts.items():
        try:
            decoded = json.loads(key)
        except (TypeError, ValueError):
            continue
        if isinstance(decoded, list) and decoded and decoded[0] == scope_key:
            remaining_max = max(remaining_max, int(value or 0))
    if remaining_max:
        scope_repeated_max[scope_key] = remaining_max
    else:
        scope_repeated_max.pop(scope_key, None)

    diagnosis_high_water = state.setdefault("diagnosis_repeat_high_water", {})
    for key in list(diagnosis_high_water):
        try:
            decoded = json.loads(key)
        except (TypeError, ValueError):
            continue
        if (
            isinstance(decoded, list)
            and len(decoded) >= 3
            and f"{decoded[0]}:{decoded[1]}" == scope_key
            and (not bot_key or str(decoded[2]) == bot_key)
        ):
            del diagnosis_high_water[key]

    state["watchdog_progress_reset_count"] = int(
        state.get("watchdog_progress_reset_count") or 0
    ) + 1
    state["watchdog_progress_reset_scope"] = scope_key
    state["watchdog_progress_reset_bot_guid"] = bot_key or None
    return remaining_max


def _watchdog_scope_rejections(
    status: dict[str, Any], *, profile_name: str,
) -> list[str]:
    """Require an exact active attempt before attributing a watchdog failure."""

    runtime = status.get("raid_runtime")
    if not isinstance(runtime, dict):
        return ["watchdog_runtime_missing"]
    expected_size = runtime.get("expected_size")
    if not _positive_int(expected_size):
        return ["watchdog_expected_size_invalid"]
    roster = runtime.get("roster")
    roster_rejections: list[str] = []
    roster_guids: list[int] = []
    if not isinstance(roster, list):
        roster_rejections.append("watchdog_roster_not_a_list")
    else:
        if len(roster) != expected_size:
            roster_rejections.append("watchdog_roster_size_mismatch")
        rows = [row for row in roster if isinstance(row, dict)]
        if len(rows) != len(roster):
            roster_rejections.append("watchdog_roster_row_invalid")
        slots = [row.get("slot") for row in rows]
        if (
            any(isinstance(slot, bool) or not isinstance(slot, int) for slot in slots)
            or sorted(slots) != list(range(expected_size))
        ):
            roster_rejections.append("watchdog_roster_slots_mismatch")
        guids = [row.get("guid") for row in rows]
        if any(not _positive_int(guid) for guid in guids):
            roster_rejections.append("watchdog_roster_guid_invalid")
        else:
            roster_guids = [int(guid) for guid in guids]
            if len(set(roster_guids)) != len(roster_guids):
                roster_rejections.append("watchdog_roster_guid_duplicate")
        if any(row.get("active") is not True for row in rows):
            roster_rejections.append("watchdog_roster_member_inactive")
        if any(row.get("lease_owned") is not True for row in rows):
            roster_rejections.append("watchdog_roster_lease_unowned")

    admission = runtime.get("admission_receipt")
    expected_map_id = admission.get("entrance_map_id") if isinstance(admission, dict) else None
    route = status.get("validation_route")
    if not isinstance(route, dict):
        route = runtime.get("validation_route")
    if not _positive_int(expected_map_id) and isinstance(route, dict):
        expected_map_id = route.get("map_id")
    if not _positive_int(expected_map_id):
        roster_rejections.append("watchdog_expected_map_missing")
    accepted_members = admission.get("members") if isinstance(admission, dict) else None
    if isinstance(accepted_members, list):
        accepted_guids = [
            member.get("guid") for member in accepted_members
            if isinstance(member, dict)
        ]
        if len(accepted_guids) != len(accepted_members):
            roster_rejections.append("watchdog_admission_member_invalid")
        elif len(accepted_members) != expected_size:
            roster_rejections.append("watchdog_admission_member_count_mismatch")
        elif any(not _positive_int(guid) for guid in accepted_guids):
            roster_rejections.append("watchdog_admission_guid_invalid")
        elif len(set(accepted_guids)) != len(accepted_guids):
            roster_rejections.append("watchdog_admission_guid_duplicate")
        elif roster_guids and sorted(roster_guids) != sorted(accepted_guids):
            roster_rejections.append("watchdog_roster_admission_identity_mismatch")
    checks = {
        "watchdog_status_not_ok": status.get("ok") is True,
        "watchdog_action_mismatch": status.get("action") == "botauto_status",
        "watchdog_cohort_mismatch": status.get("cohort_id") == "default",
        "watchdog_profile_mismatch": status.get("active_profile") == profile_name,
        "watchdog_bot_count_mismatch": status.get("bots") == expected_size,
        "watchdog_lease_count_mismatch": status.get("lease_count") == expected_size,
        "watchdog_runtime_inactive": runtime.get("active") is True,
        "watchdog_active_size_mismatch": runtime.get("active_size") == expected_size,
        "watchdog_roster_incomplete": runtime.get("roster_complete") is True,
        "watchdog_map_mismatch": runtime.get("map_id") == expected_map_id,
        "watchdog_strategy_missing": (
            isinstance(runtime.get("strategy_id"), str)
            and bool(runtime.get("strategy_id", "").strip())
        ),
        "watchdog_instance_missing": _positive_int(runtime.get("instance_id")),
        "watchdog_attempt_missing": _positive_int(runtime.get("attempt_id")),
        "watchdog_assignment_missing": _positive_int(runtime.get("assignment_generation")),
        "watchdog_unique_leases_missing": runtime.get("unique_leases") is True,
    }
    reasons = [name for name, passed in checks.items() if not passed]
    reasons.extend(roster_rejections)
    return list(dict.fromkeys(reasons))


def observe_capture_watchdog(
    state: dict[str, Any],
    status: dict[str, Any],
    diagnosis: dict[str, Any] | None,
    trace_rows: list[dict[str, Any]] | None = None,
    *,
    profile_name: str = "blackwing_descent_10n",
    max_repeated_decisions: int = DEFAULT_MAX_REPEATED_DECISIONS,
    max_death_loops: int = DEFAULT_MAX_DEATH_LOOPS,
) -> dict[str, Any]:
    """Observe scoped trace/diagnosis evidence for deterministic termination.

    Route failures, stalled failed movement candidates, and explicit death
    events can trip this watchdog. The ordinary decision heartbeat, changing
    victims, casts, and native death/revive lifecycle rows are retained as
    evidence but never count as semantic route progress. The first threshold
    crossed in trace order wins, which keeps the terminal reason deterministic
    when both counters grow.
    """

    if max_repeated_decisions <= 0 or max_death_loops <= 0:
        raise ValueError("watchdog thresholds must be positive")

    current_scope = _watchdog_route_scope(status)
    report: dict[str, Any] = {
        "detected": False,
        "classification": None,
        "failure_reason": None,
        "scope": {
            "route_node_id": current_scope[0],
            "route_generation": current_scope[1],
        },
        "max_repeated_decisions": max_repeated_decisions,
        "max_death_loops": max_death_loops,
        "repeated_decision_count": 0,
        "death_loop_count": 0,
        "repeated_decision_outcome": None,
        "progress_reset_count": int(state.get("watchdog_progress_reset_count") or 0),
        "progress_reset_scope": state.get("watchdog_progress_reset_scope"),
        "progress_reset_bot_guid": state.get("watchdog_progress_reset_bot_guid"),
        "progress_reset_reason": state.get("watchdog_progress_reset_reason"),
        "last_10_repeated_decisions": list(
            state.get("last_10_repeated_decisions") or []
        ),
        "rejections": [],
    }
    scope_rejections = _watchdog_scope_rejections(status, profile_name=profile_name)
    report["rejections"] = scope_rejections
    if scope_rejections or current_scope == ("", 0):
        if current_scope == ("", 0) and "watchdog_route_scope_missing" not in scope_rejections:
            scope_rejections.append("watchdog_route_scope_missing")
        return report

    repeated_counts = state.setdefault("repeated_decision_counts", {})
    death_counts = state.setdefault("death_loop_counts", {})
    scope_repeated_max = state.setdefault("scope_repeated_max", {})
    trace_seen = state.setdefault("trace_seen", [])
    trace_cursors = state.setdefault("trace_cursors", {})
    terminal = state.get("terminal_failure")
    scope_key = f"{current_scope[0]}:{current_scope[1]}"
    report["repeated_decision_count"] = int(scope_repeated_max.get(scope_key) or 0)
    report["death_loop_count"] = int(death_counts.get(scope_key) or 0)

    def maybe_terminal(reason: str, *, outcome: str | None = None) -> bool:
        nonlocal terminal
        if terminal:
            return True
        terminal = {
            "detected": True,
            "classification": "gameplay_failure",
            "failure_reason": reason,
            "scope": {
                "route_node_id": current_scope[0],
                "route_generation": current_scope[1],
            },
            "outcome": outcome,
        }
        state["terminal_failure"] = terminal
        return True

    progress_reset_keys: set[tuple[str, str]] = set()

    def reset_on_progress(
        scope: tuple[str, int], route_progress: dict[str, Any] | None, *,
        bot_key: str,
    ) -> bool:
        if not _watchdog_target_progress(
            state, status, scope, route_progress, bot_key=bot_key,
        ):
            return False
        scope_key = f"{scope[0]}:{scope[1]}"
        remaining_max = _watchdog_reset_repeated_scope(
            state, scope_key, bot_key=bot_key,
        )
        progress_reset_keys.add((scope_key, bot_key))
        report["progress_reset_count"] = int(state["watchdog_progress_reset_count"])
        report["progress_reset_scope"] = scope_key
        report["progress_reset_bot_guid"] = int(bot_key) if bot_key.isdigit() else bot_key or None
        reset_reason = _watchdog_progress_reset_reason(route_progress)
        state["watchdog_progress_reset_reason"] = reset_reason
        report["progress_reset_reason"] = reset_reason
        report["repeated_decision_count"] = remaining_max
        if not remaining_max:
            report["repeated_decision_outcome"] = None
        return True

    # Diagnose snapshots are the slower semantic channel.  Apply their
    # objective progress before processing the faster trace delta so a lower
    # target high-water mark cannot arrive after a threshold decision.
    if isinstance(diagnosis, dict):
        for bot in diagnosis.get("bots") or []:
            if not isinstance(bot, dict):
                continue
            snapshot = bot.get("snapshot") if isinstance(bot.get("snapshot"), dict) else {}
            route_progress = snapshot.get("route_progress")
            if not isinstance(route_progress, dict):
                continue
            route_scope = _watchdog_route_progress_scope(route_progress, current_scope)
            if route_scope == current_scope:
                identity = bot.get("identity") if isinstance(bot.get("identity"), dict) else {}
                try:
                    bot_key = str(int(identity.get("bot_guid") or 0))
                except (TypeError, ValueError):
                    bot_key = "0"
                reset_on_progress(current_scope, route_progress, bot_key=bot_key)

    # A single native decision can emit several trace rows.  Collect complete
    # per-bot decision-tick groups before classifying route failures so a
    # subordinate adapter/event cannot trip the watchdog ahead of its primary
    # native/brain action in the same group.
    trace_groups: list[tuple[str, tuple[str, int], list[dict[str, Any]]]] = []
    trace_group_indexes: dict[tuple[Any, ...], int] = {}
    for trace_row in trace_rows or []:
        if not isinstance(trace_row, dict) or trace_row.get("action") != "botauto_trace":
            continue
        for bot in trace_row.get("bots") or []:
            if not isinstance(bot, dict):
                continue
            try:
                bot_guid = int(bot.get("bot_guid") or 0)
            except (TypeError, ValueError):
                bot_guid = 0
            cursor_key = str(bot_guid)
            for entry in bot.get("entries") or []:
                if not isinstance(entry, dict):
                    continue
                try:
                    sequence = int(entry.get("sequence") or 0)
                except (TypeError, ValueError):
                    sequence = 0
                entry_key = json.dumps(
                    [cursor_key, sequence, entry.get("timestamp_ms"), entry.get("action")],
                    separators=(",", ":"), sort_keys=True,
                )
                if entry_key in trace_seen:
                    continue
                trace_seen.append(entry_key)
                if len(trace_seen) > 4096:
                    del trace_seen[: len(trace_seen) - 4096]
                if sequence > 0:
                    previous = int(trace_cursors.get(cursor_key) or 0)
                    if sequence <= previous:
                        continue
                    trace_cursors[cursor_key] = sequence
                scope = _watchdog_entry_scope(entry, current_scope)
                if scope != current_scope:
                    continue
                group_key = (
                    cursor_key,
                    scope[0],
                    scope[1],
                    *_watchdog_trace_group_key(entry),
                )
                group_index = trace_group_indexes.get(group_key)
                if group_index is None:
                    trace_group_indexes[group_key] = len(trace_groups)
                    trace_groups.append((cursor_key, scope, [entry]))
                else:
                    trace_groups[group_index][2].append(entry)

    for cursor_key, scope, group_entries in trace_groups:
        scope_key = f"{scope[0]}:{scope[1]}"
        # Apply every progress row before classifying the group.  Death loops
        # remain independent terminals even when the same group has a success.
        group_progress_reset = False
        for entry in group_entries:
            route_progress = entry.get("route_progress")
            if isinstance(route_progress, dict):
                group_progress_reset = reset_on_progress(
                    scope, route_progress, bot_key=cursor_key,
                ) or group_progress_reset
        for entry in group_entries:
            if entry.get("action") not in _WATCHDOG_DEATH_ACTIONS:
                continue
            death_counts[scope_key] = int(death_counts.get(scope_key) or 0) + 1
            report["death_loop_count"] = death_counts[scope_key]
            if death_counts[scope_key] >= max_death_loops:
                maybe_terminal("death_loop_watchdog")
                break
        if terminal:
            break
        if any(_watchdog_is_successful_native_action(entry) for entry in group_entries):
            continue
        # Several failed adapter rows may share the same native decision tick.
        # They are one failed decision for watchdog purposes, not one count
        # per serialized event.
        entry = _watchdog_representative_repeated_failure(group_entries)
        if entry is None or group_progress_reset:
            continue
        outcome = _watchdog_failure_outcome(entry)
        try:
            fingerprint = int(entry.get("fingerprint_hash") or 0)
        except (TypeError, ValueError):
            fingerprint = 0
        native_count = _watchdog_native_consecutive_count(entry)
        decision_key = json.dumps(
            [scope_key, cursor_key, str(entry.get("action") or ""), outcome, fingerprint],
            separators=(",", ":"),
        )
        previous_count = int(repeated_counts.get(decision_key) or 0)
        if _watchdog_is_local_no_progress_decision(entry):
            current_count = previous_count + 1
        elif native_count is not None:
            # The native counter belongs to the decision kernel, while this
            # row may be a failed adapter/event emitted for that decision.
            # Count one representative group locally and use the native value
            # only as an upper bound when it reports a reset to a lower run.
            current_count = min(previous_count + 1, native_count)
        else:
            current_count = previous_count + 1
        if current_count > 0:
            repeated_counts[decision_key] = current_count
        else:
            repeated_counts.pop(decision_key, None)
        current_max = 0
        for key, value in repeated_counts.items():
            try:
                decoded = json.loads(key)
            except (TypeError, ValueError):
                continue
            if isinstance(decoded, list) and decoded and decoded[0] == scope_key:
                current_max = max(current_max, int(value or 0))
        if current_max:
            scope_repeated_max[scope_key] = current_max
        else:
            scope_repeated_max.pop(scope_key, None)
        report["repeated_decision_count"] = max(
            int(report["repeated_decision_count"]), current_count
        )
        report["repeated_decision_outcome"] = outcome
        recent = state.setdefault("last_10_repeated_decisions", [])
        recent.append({
            "route_node_id": scope[0],
            "route_generation": scope[1],
            "bot_guid": int(cursor_key) if cursor_key.isdigit() else cursor_key,
            "action": str(entry.get("action") or ""),
            "outcome": outcome,
            "fingerprint_hash": fingerprint,
            "sequence": int(entry.get("sequence") or 0),
        })
        del recent[:-10]
        report["last_10_repeated_decisions"] = list(recent)
        if current_count >= max_repeated_decisions:
            maybe_terminal("repeated_decision_watchdog", outcome=outcome)
        if terminal:
            break

    if not terminal and isinstance(diagnosis, dict):
        diagnosis_high_water = state.setdefault("diagnosis_repeat_high_water", {})
        for bot in diagnosis.get("bots") or []:
            if not isinstance(bot, dict):
                continue
            identity = bot.get("identity") if isinstance(bot.get("identity"), dict) else {}
            snapshot = bot.get("snapshot") if isinstance(bot.get("snapshot"), dict) else {}
            decision = snapshot.get("decision") if isinstance(snapshot.get("decision"), dict) else {}
            route_progress = snapshot.get("route_progress") if isinstance(snapshot.get("route_progress"), dict) else {}
            route = route_progress.get("route") if isinstance(route_progress.get("route"), dict) else {}
            entry_scope = _watchdog_entry_scope(
                {
                    "route_node_id": route.get("node_id"),
                    "route_generation": route.get("generation"),
                }, current_scope,
            )
            if entry_scope != current_scope:
                continue
            stalled_candidate = _watchdog_stalled_candidate_failure(
                bot, max_repeated_decisions=max_repeated_decisions,
            )
            if stalled_candidate is not None:
                try:
                    bot_key = str(int(identity.get("bot_guid") or 0))
                except (TypeError, ValueError):
                    bot_key = "0"
                repeat_count = int(stalled_candidate["repeat_count"])
                outcome = str(stalled_candidate["outcome"])
                action = str(stalled_candidate["action"])
                report["repeated_decision_count"] = max(
                    int(report["repeated_decision_count"]), repeat_count
                )
                report["repeated_decision_outcome"] = outcome
                recent = state.setdefault("last_10_repeated_decisions", [])
                recent.append({
                    "route_node_id": entry_scope[0],
                    "route_generation": entry_scope[1],
                    "bot_guid": int(bot_key) if bot_key.isdigit() else bot_key,
                    "action": action,
                    "outcome": outcome,
                    "fingerprint_hash": int(
                        stalled_candidate["fingerprint_hash"]
                    ),
                })
                del recent[:-10]
                report["last_10_repeated_decisions"] = list(recent)
                maybe_terminal("repeated_decision_watchdog", outcome=outcome)
                break
            action = str(decision.get("action") or "")
            outcome = _watchdog_failure_outcome(decision)
            if not _watchdog_is_repeated_decision({"action": action, "result": outcome}):
                continue
            try:
                bot_key = str(int(identity.get("bot_guid") or 0))
            except (TypeError, ValueError):
                bot_key = "0"
            if (f"{entry_scope[0]}:{entry_scope[1]}", bot_key) in progress_reset_keys:
                continue
            native_count = _watchdog_native_consecutive_count(decision)
            if native_count is not None:
                repeat_count = native_count
            else:
                try:
                    repeat_count = int(decision.get("fingerprint_repeat_count") or 0)
                except (TypeError, ValueError):
                    repeat_count = 0
            if repeat_count <= 0:
                continue
            key = json.dumps(
                [current_scope[0], current_scope[1], identity.get("bot_guid"), action, outcome],
                separators=(",", ":"),
            )
            # Native consecutive counts describe this exact snapshot.  Do
            # not high-water them across snapshots, or an earlier cumulative
            # fingerprint value can turn later count=1 observations into a
            # false terminal.  The legacy fallback remains for payloads that
            # predate the native field.
            diagnosis_high_water[key] = repeat_count
            report["repeated_decision_count"] = max(
                int(report["repeated_decision_count"]), repeat_count
            )
            report["repeated_decision_outcome"] = outcome or action
            recent = state.setdefault("last_10_repeated_decisions", [])
            recent.append({
                "route_node_id": entry_scope[0],
                "route_generation": entry_scope[1],
                "bot_guid": int(bot_key) if bot_key.isdigit() else bot_key,
                "action": action,
                "outcome": outcome or action,
                "fingerprint_hash": int(decision.get("fingerprint_hash") or 0),
            })
            del recent[:-10]
            report["last_10_repeated_decisions"] = list(recent)
            if repeat_count >= max_repeated_decisions:
                maybe_terminal("repeated_decision_watchdog", outcome=outcome or action)
                break

    if terminal:
        report.update(terminal)
    return report
