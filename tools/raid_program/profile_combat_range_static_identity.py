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


def _pending_live_proof() -> dict[str, str]:
    """Construct canonical pending-only state without exported authority."""

    return {
        "alive": "pending_live_proof",
        "current_target": "pending_live_proof",
        "positive_instance": "pending_live_proof",
        "same_instance": "pending_live_proof",
        "route_scope": "pending_live_proof",
        "runtime_spawn_relation": "pending_live_proof",
    }


# Compatibility view only. Canonical construction and validation must never
# read this caller-rebindable module name.
PENDING_LIVE_PROOF = MappingProxyType(_pending_live_proof())
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


def _canonical_identity_api() -> tuple[Callable[..., dict[str, Any]], ...]:
    """Bind canonical evidence semantics outside caller-rebindable globals."""

    integer_type = int
    boolean_type = bool
    dictionary_type = dict
    is_instance = isinstance
    list_type = list
    length = len
    set_type = set
    key_error_type = KeyError
    type_error_type = TypeError
    value_error_type = ValueError
    target_schema = "cata_raid_typed_target_identity_v1"
    request_schema = "cata_raid_static_target_readback_request_v1"
    receipt_schema = "cata_raid_static_target_readback_receipt_v1"
    target_fields = (
        "runtime_target_guid",
        "target_spawn_id",
        "target_entry",
        "target_map_id",
    )
    pending_fields = (
        "alive",
        "current_target",
        "positive_instance",
        "same_instance",
        "route_scope",
        "runtime_spawn_relation",
    )
    readback_sql = (
        "SELECT guid AS target_spawn_id, id AS target_entry, "
        "map AS target_map_id FROM creature WHERE guid = %s"
    )
    error_type = StaticTargetIdentityError
    mapping_type = Mapping

    def pending_proof() -> dict[str, str]:
        return {field: "pending_live_proof" for field in pending_fields}

    def positive_integer(value: object, *, field: str) -> int:
        if (
            not is_instance(value, integer_type)
            or is_instance(value, boolean_type)
            or value <= 0
        ):
            raise error_type(f"{field}_invalid")
        return value

    def nonnegative_integer(value: object, *, field: str) -> int:
        if (
            not is_instance(value, integer_type)
            or is_instance(value, boolean_type)
            or value < 0
        ):
            raise error_type(f"{field}_invalid")
        return value

    def construct_identity(
        *, runtime_target_guid: object, target_spawn_id: object,
        target_entry: object, target_map_id: object,
    ) -> dict[str, Any]:
        return {
            "schema": target_schema,
            "runtime_target_guid": positive_integer(
                runtime_target_guid, field="runtime_target_guid"
            ),
            "target_spawn_id": positive_integer(
                target_spawn_id, field="target_spawn_id"
            ),
            "target_entry": positive_integer(target_entry, field="target_entry"),
            "target_map_id": nonnegative_integer(
                target_map_id, field="target_map_id"
            ),
            "static_readback_key": "target_spawn_id",
            "live_proof": pending_proof(),
        }

    def validate_identity(value: object) -> dict[str, Any]:
        if not is_instance(value, dictionary_type):
            raise error_type("target_identity_unbound")
        missing = [field for field in target_fields if field not in value]
        if missing:
            raise error_type(f"target_identity_unbound:{missing[0]}")
        expected = {
            "schema": target_schema,
            "runtime_target_guid": positive_integer(
                value["runtime_target_guid"], field="runtime_target_guid"
            ),
            "target_spawn_id": positive_integer(
                value["target_spawn_id"], field="target_spawn_id"
            ),
            "target_entry": positive_integer(
                value["target_entry"], field="target_entry"
            ),
            "target_map_id": nonnegative_integer(
                value["target_map_id"], field="target_map_id"
            ),
            "static_readback_key": "target_spawn_id",
            "live_proof": pending_proof(),
        }
        if value != expected:
            raise error_type("target_identity_metadata_mismatch")
        return expected

    def make_request(
        identity: object, *, statement: str = readback_sql,
    ) -> dict[str, Any]:
        bound = validate_identity(identity)
        return {
            "schema": request_schema,
            "statement": statement,
            "parameter_domain": "target_spawn_id",
            "parameters": [bound["target_spawn_id"]],
            "target_identity": bound,
        }

    def verify_rows(
        *, identity: object, query_target_spawn_id: object,
        rows: Iterable[Mapping[str, object]], statement: str = readback_sql,
    ) -> dict[str, Any]:
        bound = validate_identity(identity)
        query_key = positive_integer(
            query_target_spawn_id, field="query_target_spawn_id"
        )
        if (
            query_key == bound["runtime_target_guid"]
            and query_key != bound["target_spawn_id"]
        ):
            raise error_type("runtime_target_guid_used_as_static_spawn_key")
        if query_key != bound["target_spawn_id"]:
            raise error_type("target_spawn_id_query_mismatch")
        try:
            materialized = list_type(rows)
        except (type_error_type, value_error_type) as error:
            raise error_type("static_target_rows_invalid") from error
        if length(materialized) != 1:
            raise error_type("static_target_row_count_mismatch")
        row = materialized[0]
        if not is_instance(row, mapping_type):
            raise error_type("static_target_row_invalid")
        expected_row = {
            "target_spawn_id": bound["target_spawn_id"],
            "target_entry": bound["target_entry"],
            "target_map_id": bound["target_map_id"],
        }
        if set_type(row) != set_type(expected_row):
            raise error_type("static_target_row_metadata_unbound")
        for field, expected in expected_row.items():
            validator = (
                nonnegative_integer if field == "target_map_id" else positive_integer
            )
            actual = validator(row[field], field=f"row_{field}")
            if actual != expected:
                raise error_type(f"static_{field}_mismatch")
        return {
            "schema": receipt_schema,
            "accepted": True,
            "query": make_request(bound, statement=statement),
            "row": expected_row,
            "target_identity": bound,
            "live_proof": pending_proof(),
        }

    def target_identity(
        *, runtime_target_guid: object, target_spawn_id: object,
        target_entry: object, target_map_id: object,
    ) -> dict[str, Any]:
        """Build the canonical, explicitly separated target identity."""

        return construct_identity(
            runtime_target_guid=runtime_target_guid,
            target_spawn_id=target_spawn_id,
            target_entry=target_entry,
            target_map_id=target_map_id,
        )

    def validate_target_identity(value: object) -> dict[str, Any]:
        """Require an exact canonical identity, including pending live claims."""

        return validate_identity(value)

    def identity_from_projection(value: Mapping[str, object]) -> dict[str, Any]:
        """Extract the exact four typed fields from a sealed projection."""

        try:
            fields = {field: value[field] for field in target_fields}
        except key_error_type as error:
            raise error_type(f"target_identity_unbound:{error.args[0]}") from error
        return construct_identity(**fields)

    def static_readback_request(identity: object) -> dict[str, Any]:
        """Return the only admitted parameterized static-spawn query."""

        return make_request(identity)

    def verify_static_readback(
        *, identity: object, query_target_spawn_id: object,
        rows: Iterable[Mapping[str, object]],
    ) -> dict[str, Any]:
        """Verify one static row without asserting a runtime-spawn relation."""

        return verify_rows(
            identity=identity,
            query_target_spawn_id=query_target_spawn_id,
            rows=rows,
        )

    def perform_static_readback(
        *, identity: object,
        query: Callable[[str, tuple[int]], Iterable[Mapping[str, object]]],
    ) -> dict[str, Any]:
        """Execute the query and verify its exact typed result."""

        statement = readback_sql
        request = make_request(identity, statement=statement)
        parameter = request["parameters"][0]
        assert is_instance(parameter, integer_type)
        rows = query(statement, (parameter,))
        return verify_rows(
            identity=request["target_identity"],
            query_target_spawn_id=parameter,
            rows=rows,
            statement=statement,
        )

    return (
        target_identity,
        validate_target_identity,
        identity_from_projection,
        static_readback_request,
        verify_static_readback,
        perform_static_readback,
    )


(
    target_identity,
    validate_target_identity,
    identity_from_projection,
    static_readback_request,
    verify_static_readback,
    perform_static_readback,
) = _canonical_identity_api()
