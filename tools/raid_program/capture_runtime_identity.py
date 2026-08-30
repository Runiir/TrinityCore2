from __future__ import annotations

from typing import Any


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
# The roster's membership/assignment identity is immutable for a run, while
# ``active`` and ``lease_owned`` are live lifecycle state.  Deaths and native
# recovery legitimately change the latter in status/diagnose/trace envelopes;
# treating those flags as membership identity made telemetry from a partial
# wipe look like a cross-shard row.  Keep the full roster contract above for
# provisioning/acceptance, but demultiplex telemetry against this frozen
# membership projection and validate the lifecycle flags separately.
ROSTER_BINDING_ID_FIELDS = tuple(
    field for field in ROSTER_ID_FIELDS if field not in ("active", "lease_owned")
)


def _runtime_identity(runtime: dict[str, Any], *, include_strategy: bool = False) -> tuple[Any, ...] | None:
    fields = IDENTITY_FIELDS + ((STRATEGY_FIELD,) if include_strategy else ())
    if not all(field in runtime for field in fields):
        return None
    return tuple(runtime[field] for field in fields)


def _roster_binding_identity(roster: list[dict[str, Any]]) -> tuple[tuple[Any, ...], ...] | None:
    """Return immutable roster membership used to demultiplex live channels."""

    if len(roster) != 10 or any(not isinstance(row, dict) for row in roster):
        return None
    rows: list[tuple[Any, ...]] = []
    for row in sorted(roster, key=lambda value: value.get("slot") if isinstance(value.get("slot"), int) else -1):
        if any(field not in row for field in ROSTER_BINDING_ID_FIELDS):
            return None
        rows.append(tuple(row[field] for field in ROSTER_BINDING_ID_FIELDS))
    return tuple(rows)


def _roster_binding_lifecycle_rejections(roster: Any) -> list[str]:
    """Reject malformed lease/lifecycle claims without treating death as drift."""

    if not isinstance(roster, list) or len(roster) != 10:
        return ["roster_binding_shape_invalid"]
    rows = [row for row in roster if isinstance(row, dict)]
    reasons: list[str] = []
    if len(rows) != len(roster):
        return ["roster_binding_row_invalid"]
    # Producers may serialize the map-backed roster in GUID order rather than
    # slot order.  Membership identity is canonicalized by slot above, so the
    # lifecycle check must be order-independent as well.
    slots = sorted(row.get("slot") for row in rows)
    if slots != list(range(10)):
        reasons.append("roster_binding_slots_invalid")
    for row in rows:
        if not isinstance(row.get("active"), bool):
            reasons.append("roster_binding_active_invalid")
        if row.get("lease_owned") is not True:
            reasons.append("roster_binding_lease_invalid")
    return sorted(set(reasons))


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
