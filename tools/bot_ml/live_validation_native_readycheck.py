"""Request the native wipe-recovery ready check from a completion watchdog.

After a native full wipe the bots hold (BotWorldPopulationMgr::
SuppressNativeRaidRecovery) until the wipe's recovery evidence is complete, and
that evidence ends with a native raid ready check: the leader's
MSG_RAID_READY_CHECK request (`.botauto readycheck <cohort>`, which invokes only
the Group ready-check packet path) answered by every member from its own update
loop. tools.raid_program.capture_live_run sends the request once the status
predicate holds; the completion watchdogs did not, so a wiped cohort waited at
the instance entrance, alive and resurrected, until the no-progress window
expired. Round 3 Omnotron c0 (blackwing_descent_10n-r03-b1-20260925T200656Z):
the predicate held on 11 consecutive status heartbeats (worldserver.console.log
lines 1844 to 3708) and no ready check was ever sent.

Protocol (one ``NativeReadyCheckRequester`` per watchdog loop):

* ``due(status_rows, heartbeat_index)`` runs on each heartbeat's own status
  reply and stages at most one request.  The loop sends it at the END of the
  heartbeat, and only when no terminal or clear fired on that heartbeat.
* ``record_reply(...)`` parses the ``botauto_readycheck`` reply.  ``ok: true``
  accepts the recovery scope (one request per attempt, wipe generation,
  assignment generation, route generation and route node).  Anything else is a
  refusal that re-arms the same scope on a later heartbeat, at most
  ``max_requests_per_scope`` requests per scope; the C++ handler ignores a
  repeat while a check is pending, so a retry is safe.
* A refusal is not a transport failure: over SOAP a refused command is HTTP
  500 with the refusal payload.  Only a timeout or a lost transport (no reply
  payload and no server answer) propagates to the watchdog.
* Every request and reply is a receipt (``receipt()``, reported as
  ``watchdog_state.native_readycheck``).

The predicate mirrors RequestNativeRaidReadyCheckForCohort for any raid size:
the exact roster is active (``active_size == expected_size > 0``) and alive
(``alive_size == active_size``), rather than the 10-man ``alive_size == 10`` of
tools.raid_program.capture_progress.
"""
from __future__ import annotations

import html
import json
from typing import Any, Callable, Iterable, Mapping

READYCHECK_PHASE = "native_readycheck"
READYCHECK_ACTION = "botauto_readycheck"
MAX_REQUESTS_PER_SCOPE = 3
RECEIPT_REQUEST_LIMIT = 32

PayloadParser = Callable[[str], list[dict[str, Any]]]


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def exact_roster_alive(runtime: Mapping[str, Any]) -> bool:
    """The native handler's roster gate: exact roster active and all alive."""
    expected = _int(runtime.get("expected_size"))
    active = _int(runtime.get("active_size"))
    alive = _int(runtime.get("alive_size"))
    return (
        expected is not None
        and expected > 0
        and active == expected
        and alive == active
        and runtime.get("roster_complete") is True
    )


def ready_for_native_readycheck(status: Mapping[str, Any]) -> bool:
    """Mirror the native wipe-recovery ready-check admission for any raid size."""
    status = _mapping(status)
    runtime = _mapping(status.get("raid_runtime"))
    route = _mapping(status.get("validation_route"))
    native = _mapping(runtime.get("native_recovery"))
    attempt_id = _int(runtime.get("attempt_id")) or 0
    assignment_generation = _int(runtime.get("assignment_generation")) or 0
    route_generation = _int(route.get("generation")) or 0
    route_node_id = str(route.get("node_id") or "")
    recovery_scope_matches = (
        attempt_id > 0
        and assignment_generation > 0
        and route_generation > 0
        and bool(route_node_id)
        and runtime.get("native_recovery_hold_active") is True
        and (_int(runtime.get("native_recovery_route_generation")) or 0) == route_generation
        and str(runtime.get("native_recovery_node_id") or "") == route_node_id
    )
    boss_reset_observed = (_int(runtime.get("boss_reset_generation")) or 0) > (
        _int(runtime.get("boss_reset_generation_at_wipe")) or 0
    )
    hostile_reset_observed = (
        runtime.get("native_hostile_inactivity_observed") is True
        and (_int(runtime.get("native_hostile_reset_generation")) or 0)
        > (_int(runtime.get("native_hostile_reset_generation_at_wipe")) or 0)
        and (_int(runtime.get("native_hostile_observation_attempt_id")) or 0) == attempt_id
        and (_int(runtime.get("native_hostile_observation_route_generation")) or 0) == route_generation
        and str(runtime.get("native_hostile_observation_node_id") or "") == route_node_id
    )
    return (
        recovery_scope_matches
        and exact_roster_alive(runtime)
        and runtime.get("encounter_in_progress") is False
        and (_int(runtime.get("wipe_generation")) or 0) > 0
        and runtime.get("native_hostile_activity_active") is False
        and (boss_reset_observed or hostile_reset_observed)
        and native.get("death_observed") is True
        and native.get("corpse_observed") is True
        and native.get("release_observed") is True
        and native.get("resurrection_observed") is True
        and native.get("runback_observed") is True
        and native.get("ready_check_action_observed") is not True
    )


def readycheck_request_identity(status: Mapping[str, Any]) -> tuple[Any, ...]:
    """The recovery scope one request binds to.

    Mirrors tools.raid_program.capture_runtime_acceptance.
    native_readycheck_request_identity, which the single-cohort capture uses.
    """
    runtime = _mapping(_mapping(status).get("raid_runtime"))
    route = _mapping(_mapping(status).get("validation_route"))
    return (
        runtime.get("attempt_id"),
        runtime.get("wipe_generation"),
        runtime.get("assignment_generation"),
        route.get("generation"),
        route.get("node_id"),
    )


def _scope_receipt(identity: tuple[Any, ...]) -> dict[str, Any]:
    keys = ("attempt_id", "wipe_generation", "assignment_generation", "route_generation", "route_node_id")
    return dict(zip(keys, identity))


def _parse_json_objects(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    index = 0
    while True:
        start = text.find("{", index)
        if start < 0:
            return rows
        try:
            payload, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        index = start + max(end, 1)


class NativeReadyCheckRequester:
    """Stages, sends and records the native ready check for one watchdog loop."""

    def __init__(self, cohort_id: str, *, max_requests_per_scope: int = MAX_REQUESTS_PER_SCOPE,
                 parse: PayloadParser | None = None) -> None:
        self.cohort_id = cohort_id if cohort_id and cohort_id != "default" else ""
        self.max_requests_per_scope = max(1, int(max_requests_per_scope))
        self.parse = parse or _parse_json_objects
        self.pending: tuple[Any, ...] | None = None
        self.pending_heartbeat_index = 0
        self.in_flight: tuple[Any, ...] | None = None
        self.requests: list[tuple[Any, ...]] = []
        self.scopes: dict[tuple[Any, ...], dict[str, Any]] = {}
        self.receipts: list[dict[str, Any]] = []

    @property
    def command(self) -> str:
        return ".botauto readycheck" + (f" {self.cohort_id}" if self.cohort_id else "")

    def _status_row(self, rows: Iterable[Any]) -> Mapping[str, Any] | None:
        for row in rows:
            if (
                not isinstance(row, Mapping)
                or row.get("action") != "botauto_status"
                or row.get("ok") is not True
            ):
                continue
            if self.cohort_id and row.get("cohort_id") not in (None, self.cohort_id):
                continue
            return row
        return None

    def due(self, rows: Iterable[Any], heartbeat_index: int = 0) -> str:
        """Stage the request this heartbeat's status allows; return its command or ''."""
        self.pending = None
        row = self._status_row(rows)
        if row is None or not ready_for_native_readycheck(row):
            return ""
        identity = readycheck_request_identity(row)
        scope = self.scopes.get(identity)
        if scope is not None:
            if scope["accepted"] or scope["awaiting_reply"]:
                return ""
            if scope["requests"] >= self.max_requests_per_scope:
                scope["exhausted"] = True
                return ""
        self.pending = identity
        self.pending_heartbeat_index = int(heartbeat_index)
        return self.command

    def take(self) -> str:
        """The staged command, marked as sent; '' when nothing is staged."""
        identity, self.pending = self.pending, None
        if identity is None:
            return ""
        scope = self.scopes.setdefault(identity, {
            "scope": _scope_receipt(identity), "requests": 0, "accepted": False,
            "awaiting_reply": False, "exhausted": False, "last_failure_reason": "",
        })
        scope["requests"] += 1
        scope["awaiting_reply"] = True
        self.in_flight = identity
        self.requests.append(identity)
        return self.command

    def record_reply(self, output: str, *, returncode: int = 0, timed_out: bool = False,
                     heartbeat_index: int = 0) -> dict[str, Any]:
        """Classify the reply to the in-flight request; ``propagate`` marks a transport loss."""
        identity, self.in_flight = self.in_flight, None
        text = output or ""
        replies = [
            row for row in self.parse(text) + (self.parse(html.unescape(text)) if "&quot;" in text else [])
            if row.get("action") == READYCHECK_ACTION
            and (not self.cohort_id or row.get("cohort_id") in (None, self.cohort_id))
        ]
        reply = replies[-1] if replies else {}
        if timed_out:
            outcome = "transport_timeout"
        elif reply.get("ok") is True:
            outcome = "accepted"
        elif reply:
            outcome = "refused"
        elif returncode >= 400:
            # The server answered (SOAP fault) without a parseable payload.
            outcome = "refused_unparsed"
        elif returncode != 0:
            outcome = "transport_lost"
        else:
            outcome = "no_reply"
        receipt: dict[str, Any] = {
            "heartbeat_index": int(heartbeat_index),
            "scope": _scope_receipt(identity) if identity is not None else {},
            "command": self.command,
            "outcome": outcome,
            "ok": reply.get("ok") is True,
            "failure_reason": str(reply.get("failure_reason") or ""),
            "returncode": int(returncode),
            "timed_out": bool(timed_out),
        }
        for key in ("ready_check_pending", "ready_check_complete", "ready_check_action_generation",
                    "ready_check_response_count", "wipe_generation", "attempt_id"):
            if key in reply:
                receipt[key] = reply[key]
        scope = self.scopes.get(identity) if identity is not None else None
        if scope is not None:
            scope["awaiting_reply"] = False
            scope["accepted"] = outcome == "accepted"
            scope["last_failure_reason"] = receipt["failure_reason"] or ("" if scope["accepted"] else outcome)
            scope["exhausted"] = not scope["accepted"] and scope["requests"] >= self.max_requests_per_scope
            receipt["request"] = scope["requests"]
            receipt["rearmed"] = not scope["accepted"] and not scope["exhausted"]
        receipt["propagate"] = outcome in {"transport_timeout", "transport_lost"}
        self.receipts.append(receipt)
        del self.receipts[:-RECEIPT_REQUEST_LIMIT]
        return receipt

    def receipt(self) -> dict[str, Any]:
        return {
            "schema": "bot_native_readycheck_requests_v1",
            "command": self.command,
            "max_requests_per_scope": self.max_requests_per_scope,
            "requests_sent": len(self.requests),
            "scopes": [dict(scope) for scope in self.scopes.values()],
            "requests": [dict(row) for row in self.receipts],
        }
