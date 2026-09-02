"""Typed runtime-target and persistent-spawn identity verification.

Static world metadata cannot prove which runtime object represents a spawn in
any server epoch.  This module deliberately keeps those identity domains
separate and leaves every live relationship pending.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from types import MappingProxyType
from typing import Any


TARGET_IDENTITY_SCHEMA = "cata_raid_typed_target_identity_v1"
STATIC_READBACK_REQUEST_SCHEMA = "cata_raid_static_target_readback_request_v1"
STATIC_READBACK_RECEIPT_SCHEMA = "cata_raid_static_target_readback_receipt_v1"
TARGET_IDENTITY_FIELDS = (
    "runtime_target_guid",
    "target_spawn_id",
    "target_entry",
    "target_map_id",
)
PENDING_LIVE_PROOF = MappingProxyType({
    "alive": "pending_live_proof",
    "current_target": "pending_live_proof",
    "positive_instance": "pending_live_proof",
    "same_instance": "pending_live_proof",
    "route_scope": "pending_live_proof",
    "runtime_spawn_relation": "pending_live_proof",
})
STATIC_READBACK_SQL = (
    "SELECT guid AS target_spawn_id, id AS target_entry, "
    "map AS target_map_id FROM creature WHERE guid = %s"
)


class StaticTargetIdentityError(ValueError):
    """A typed target identity or static readback failed closed."""


def _positive_integer(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise StaticTargetIdentityError(f"{field}_invalid")
    return value


def _nonnegative_integer(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StaticTargetIdentityError(f"{field}_invalid")
    return value


def target_identity(
    *, runtime_target_guid: object, target_spawn_id: object,
    target_entry: object, target_map_id: object,
) -> dict[str, Any]:
    """Build the canonical, explicitly separated target identity."""

    identity = {
        "schema": TARGET_IDENTITY_SCHEMA,
        "runtime_target_guid": _positive_integer(
            runtime_target_guid, field="runtime_target_guid"
        ),
        "target_spawn_id": _positive_integer(
            target_spawn_id, field="target_spawn_id"
        ),
        "target_entry": _positive_integer(target_entry, field="target_entry"),
        "target_map_id": _nonnegative_integer(
            target_map_id, field="target_map_id"
        ),
        "static_readback_key": "target_spawn_id",
        "live_proof": dict(PENDING_LIVE_PROOF),
    }
    return identity


def validate_target_identity(value: object) -> dict[str, Any]:
    """Require an exact canonical identity, including pending live claims."""

    if not isinstance(value, dict):
        raise StaticTargetIdentityError("target_identity_unbound")
    missing = [field for field in TARGET_IDENTITY_FIELDS if field not in value]
    if missing:
        raise StaticTargetIdentityError(
            f"target_identity_unbound:{missing[0]}"
        )
    expected = target_identity(
        **{field: value[field] for field in TARGET_IDENTITY_FIELDS}
    )
    if value != expected:
        raise StaticTargetIdentityError("target_identity_metadata_mismatch")
    return expected


def identity_from_projection(value: Mapping[str, object]) -> dict[str, Any]:
    """Extract the exact four typed fields from a larger sealed projection."""

    try:
        fields = {field: value[field] for field in TARGET_IDENTITY_FIELDS}
    except KeyError as error:
        raise StaticTargetIdentityError(
            f"target_identity_unbound:{error.args[0]}"
        ) from error
    return target_identity(**fields)


def static_readback_request(identity: object) -> dict[str, Any]:
    """Return the only admitted parameterized static-spawn query."""

    bound = validate_target_identity(identity)
    return {
        "schema": STATIC_READBACK_REQUEST_SCHEMA,
        "statement": STATIC_READBACK_SQL,
        "parameter_domain": "target_spawn_id",
        "parameters": [bound["target_spawn_id"]],
        "target_identity": bound,
    }


def verify_static_readback(
    *, identity: object, query_target_spawn_id: object,
    rows: Iterable[Mapping[str, object]],
) -> dict[str, Any]:
    """Verify one static row without asserting a runtime-to-spawn relation."""

    bound = validate_target_identity(identity)
    query_key = _positive_integer(
        query_target_spawn_id, field="query_target_spawn_id"
    )
    if (
        query_key == bound["runtime_target_guid"]
        and query_key != bound["target_spawn_id"]
    ):
        raise StaticTargetIdentityError(
            "runtime_target_guid_used_as_static_spawn_key"
        )
    if query_key != bound["target_spawn_id"]:
        raise StaticTargetIdentityError("target_spawn_id_query_mismatch")
    try:
        materialized = list(rows)
    except (TypeError, ValueError) as error:
        raise StaticTargetIdentityError("static_target_rows_invalid") from error
    if len(materialized) != 1:
        raise StaticTargetIdentityError("static_target_row_count_mismatch")
    row = materialized[0]
    if not isinstance(row, Mapping):
        raise StaticTargetIdentityError("static_target_row_invalid")
    expected_row = {
        "target_spawn_id": bound["target_spawn_id"],
        "target_entry": bound["target_entry"],
        "target_map_id": bound["target_map_id"],
    }
    if set(row) != set(expected_row):
        raise StaticTargetIdentityError("static_target_row_metadata_unbound")
    for field, expected in expected_row.items():
        validator = (
            _nonnegative_integer if field == "target_map_id" else _positive_integer
        )
        actual = validator(row[field], field=f"row_{field}")
        if actual != expected:
            raise StaticTargetIdentityError(f"static_{field}_mismatch")
    return {
        "schema": STATIC_READBACK_RECEIPT_SCHEMA,
        "accepted": True,
        "query": static_readback_request(bound),
        "row": expected_row,
        "target_identity": bound,
        "live_proof": dict(PENDING_LIVE_PROOF),
    }


def perform_static_readback(
    *, identity: object,
    query: Callable[[str, tuple[int]], Iterable[Mapping[str, object]]],
) -> dict[str, Any]:
    """Execute the parameterized query and verify its exact typed result."""

    request = static_readback_request(identity)
    parameter = request["parameters"][0]
    assert isinstance(parameter, int)
    rows = query(STATIC_READBACK_SQL, (parameter,))
    return verify_static_readback(
        identity=request["target_identity"],
        query_target_spawn_id=parameter,
        rows=rows,
    )
