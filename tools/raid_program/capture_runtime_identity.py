from __future__ import annotations

from typing import Any

try:
    from tools.raid_program.capture_value_types import _positive_int
except ModuleNotFoundError:
    from capture_value_types import _positive_int


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


# Round 10: a canonical full raid switches talent groups at authorised route
# nodes (capture_spec_transitions.py). Its runtime and roster rows declare
# `spec_contract_scope`; there the mutable loadout identity (assignment
# generation, role, class spec, talents, glyphs, gear) is masked out of these
# frozen projections and validated against the route's contracts instead.
# Masking needs the caller's authorisation (capture_spec_transitions.
# masking_authorised: a verified route contract and a consistently scoped
# runtime); a marker alone never masks. Other rows project as before.
SPEC_CONTRACT_SCOPE_FIELD = "spec_contract_scope"
SPEC_CONTRACT_SCOPE_MARKER = "<spec_contract_scope>"
ROSTER_LOADOUT_FIELDS = ("role", "class_spec", "gear_identity", "talents", "glyphs", "gear_identity_manifest")


def _in_spec_contract_scope(value: Any) -> bool:
    return isinstance(value, dict) and value.get(SPEC_CONTRACT_SCOPE_FIELD) is True


def _runtime_identity(
    runtime: dict[str, Any], *, include_strategy: bool = False, spec_scope_authorised: bool = False,
) -> tuple[Any, ...] | None:
    fields = IDENTITY_FIELDS + ((STRATEGY_FIELD,) if include_strategy else ())
    if not all(field in runtime for field in fields):
        return None
    scoped = spec_scope_authorised and _in_spec_contract_scope(runtime)
    return tuple(SPEC_CONTRACT_SCOPE_MARKER if scoped and field == "assignment_generation" else runtime[field]
                 for field in fields)


def _roster_row_projection(
    row: dict[str, Any], fields: tuple[str, ...], *, spec_scope_authorised: bool = False,
) -> tuple[Any, ...]:
    scoped = spec_scope_authorised and _in_spec_contract_scope(row)
    return tuple(SPEC_CONTRACT_SCOPE_MARKER if scoped and field in ROSTER_LOADOUT_FIELDS else row[field]
                 for field in fields)


def _roster_binding_identity(
    roster: list[dict[str, Any]], *, spec_scope_authorised: bool = False,
) -> tuple[tuple[Any, ...], ...] | None:
    """Return immutable roster membership used to demultiplex live channels."""

    if len(roster) != 10 or any(not isinstance(row, dict) for row in roster):
        return None
    rows: list[tuple[Any, ...]] = []
    for row in sorted(roster, key=lambda value: value.get("slot") if isinstance(value.get("slot"), int) else -1):
        if any(field not in row for field in ROSTER_BINDING_ID_FIELDS):
            return None
        rows.append(_roster_row_projection(row, ROSTER_BINDING_ID_FIELDS, spec_scope_authorised=spec_scope_authorised))
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


def _membership_identity_rejections(
    row: dict[str, Any], expected: dict[str, Any], *, check_position: bool = False,
) -> list[str]:
    """Membership identity of one roster row against provisioning: GUID, account id and name, character name and,
    with `check_position`, the roster slot id, slot index and class. Shared by the frozen-identity validator and
    the spec-contract (canonical full raid) path, which specialises only the loadout checks."""
    reasons = []
    for field in ("account", "name"):
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
    if check_position:
        if row.get("roster_slot_id") != expected["roster_slot_id"] or row.get("slot") != expected["slot"]:
            reasons.append("frozen_identity_roster_slot_mismatch")
        if row.get("class_id") != expected["class_id"]:
            reasons.append("frozen_identity_class_mismatch")
    return reasons
