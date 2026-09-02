from __future__ import annotations

import dis
import types

import pytest

import tools.raid_program.profile_combat_range_static_identity as static_identity
from tools.raid_program.profile_combat_range_static_identity import (
    PENDING_LIVE_PROOF,
    STATIC_READBACK_SQL,
    StaticTargetIdentityError,
    identity_from_projection,
    perform_static_readback,
    static_readback_request,
    target_identity,
    validate_target_identity,
    verify_static_readback,
)


def _identity(**changes: object) -> dict[str, object]:
    values = {
        "runtime_target_guid": 39,
        "target_spawn_id": 250051,
        "target_entry": 41570,
        "target_map_id": 669,
    }
    values.update(changes)
    return target_identity(**values)


def _row(**changes: object) -> dict[str, object]:
    values = {
        "target_spawn_id": 250051,
        "target_entry": 41570,
        "target_map_id": 669,
    }
    values.update(changes)
    return values


def test_static_readback_queries_only_persistent_spawn_identity() -> None:
    calls: list[tuple[str, tuple[int]]] = []

    def query(statement: str, parameters: tuple[int]):
        calls.append((statement, parameters))
        return [_row()]

    receipt = perform_static_readback(identity=_identity(), query=query)

    assert calls == [(STATIC_READBACK_SQL, (250051,))]
    assert receipt["accepted"] is True
    assert receipt["target_identity"] == _identity()
    assert receipt["row"] == _row()
    assert receipt["live_proof"] == PENDING_LIVE_PROOF
    assert set(receipt["live_proof"].values()) == {"pending_live_proof"}


@pytest.mark.parametrize("field", sorted(PENDING_LIVE_PROOF))
def test_pending_live_proof_cannot_be_rewritten_by_a_caller(field: str) -> None:
    with pytest.raises(TypeError):
        PENDING_LIVE_PROOF[field] = "proven"  # type: ignore[index]

    identity = _identity()
    assert set(identity["live_proof"].values()) == {"pending_live_proof"}

    identity["live_proof"][field] = "proven"
    with pytest.raises(
        StaticTargetIdentityError, match="target_identity_metadata_mismatch"
    ):
        validate_target_identity(identity)

    assert set(_identity()["live_proof"].values()) == {"pending_live_proof"}


def test_pending_live_proof_export_rebinding_has_no_canonical_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forged_proof = {
        field: "proven_without_live_evidence" for field in PENDING_LIVE_PROOF
    }
    monkeypatch.setattr(static_identity, "PENDING_LIVE_PROOF", forged_proof)

    identity = _identity()
    assert set(identity["live_proof"].values()) == {"pending_live_proof"}
    assert validate_target_identity(identity) == identity

    forged_identity = dict(identity)
    forged_identity["live_proof"] = forged_proof
    with pytest.raises(
        StaticTargetIdentityError, match="target_identity_metadata_mismatch"
    ):
        validate_target_identity(forged_identity)

    receipt = verify_static_readback(
        identity=identity,
        query_target_spawn_id=250051,
        rows=[_row()],
    )
    assert set(receipt["live_proof"].values()) == {"pending_live_proof"}


def test_private_pending_helper_and_public_constructor_have_no_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = _identity()
    forged_proof = {
        field: "proven_without_live_evidence" for field in PENDING_LIVE_PROOF
    }
    monkeypatch.setattr(static_identity, "_pending_live_proof", lambda: forged_proof)
    monkeypatch.setattr(
        static_identity,
        "target_identity",
        lambda **fields: {**fields, "live_proof": forged_proof},
    )

    projected = identity_from_projection(canonical)
    assert set(projected["live_proof"].values()) == {"pending_live_proof"}
    assert validate_target_identity(canonical) == canonical

    forged = dict(canonical)
    forged["live_proof"] = forged_proof
    with pytest.raises(
        StaticTargetIdentityError, match="target_identity_metadata_mismatch"
    ):
        validate_target_identity(forged)


def test_all_exported_identity_authority_is_lexically_fixed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stable_api = {
        "target_identity": target_identity,
        "validate_target_identity": validate_target_identity,
        "identity_from_projection": identity_from_projection,
        "static_readback_request": static_readback_request,
        "verify_static_readback": verify_static_readback,
        "perform_static_readback": perform_static_readback,
    }
    forged = lambda *args, **kwargs: {"forged": True}
    for name in stable_api:
        monkeypatch.setattr(static_identity, name, forged)
    monkeypatch.setattr(static_identity, "_canonical_identity_api", forged)
    monkeypatch.setattr(static_identity, "_positive_integer", forged)
    monkeypatch.setattr(static_identity, "_nonnegative_integer", forged)
    monkeypatch.setattr(static_identity, "_pending_live_proof", forged)
    monkeypatch.setattr(static_identity, "Mapping", int)
    monkeypatch.setattr(static_identity, "TARGET_IDENTITY_SCHEMA", "forged_target")
    monkeypatch.setattr(
        static_identity, "STATIC_READBACK_REQUEST_SCHEMA", "forged_request"
    )
    monkeypatch.setattr(
        static_identity, "STATIC_READBACK_RECEIPT_SCHEMA", "forged_receipt"
    )
    monkeypatch.setattr(static_identity, "TARGET_IDENTITY_FIELDS", ("forged",))
    monkeypatch.setattr(static_identity, "STATIC_READBACK_SQL", "forged_sql")
    monkeypatch.setattr(
        static_identity,
        "PENDING_LIVE_PROOF",
        {"alive": "proven_without_live_evidence"},
    )

    identity = stable_api["target_identity"](
        runtime_target_guid=39,
        target_spawn_id=250051,
        target_entry=41570,
        target_map_id=0,
    )
    assert identity == {
        "schema": "cata_raid_typed_target_identity_v1",
        "runtime_target_guid": 39,
        "target_spawn_id": 250051,
        "target_entry": 41570,
        "target_map_id": 0,
        "static_readback_key": "target_spawn_id",
        "live_proof": {
            "alive": "pending_live_proof",
            "current_target": "pending_live_proof",
            "positive_instance": "pending_live_proof",
            "same_instance": "pending_live_proof",
            "route_scope": "pending_live_proof",
            "runtime_spawn_relation": "pending_live_proof",
        },
    }
    assert stable_api["validate_target_identity"](identity) == identity
    assert stable_api["identity_from_projection"]({**identity, "extra": 7}) == identity

    request = stable_api["static_readback_request"](identity)
    assert request["schema"] == "cata_raid_static_target_readback_request_v1"
    assert request["statement"] == STATIC_READBACK_SQL
    assert request["parameters"] == [250051]

    receipt = stable_api["verify_static_readback"](
        identity=identity,
        query_target_spawn_id=250051,
        rows=[_row(target_map_id=0)],
    )
    assert receipt["schema"] == "cata_raid_static_target_readback_receipt_v1"
    assert receipt["query"] == request
    assert receipt["live_proof"] == identity["live_proof"]

    executed: list[tuple[str, tuple[int]]] = []

    def query(statement: str, parameters: tuple[int]):
        executed.append((statement, parameters))
        return [_row(target_map_id=0)]

    performed = stable_api["perform_static_readback"](identity=identity, query=query)
    assert executed == [(STATIC_READBACK_SQL, (250051,))]
    assert performed == receipt


def test_query_callback_cannot_change_executed_or_receipted_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, tuple[int]]] = []

    def query(statement: str, parameters: tuple[int]):
        calls.append((statement, parameters))
        monkeypatch.setattr(static_identity, "STATIC_READBACK_SQL", "forged_sql")
        return [_row()]

    receipt = perform_static_readback(identity=_identity(), query=query)

    assert calls == [(STATIC_READBACK_SQL, (250051,))]
    assert receipt["query"]["statement"] == calls[0][0]


@pytest.mark.parametrize(
    ("name", "replacement"),
    [
        ("int", str),
        ("bool", int),
        ("dict", list),
        ("isinstance", lambda *_: False),
        ("list", lambda _: []),
        ("len", lambda _: 0),
        ("set", lambda _: {"forged"}),
        ("KeyError", RuntimeError),
        ("TypeError", RuntimeError),
        ("ValueError", RuntimeError),
    ],
)
def test_semantic_builtin_rebinding_before_calls_has_no_authority(
    monkeypatch: pytest.MonkeyPatch, name: str, replacement: object,
) -> None:
    monkeypatch.setattr(static_identity, name, replacement, raising=False)

    identity = _identity(target_map_id=0)
    assert validate_target_identity(identity) == identity
    assert identity_from_projection({**identity, "ignored": "field"}) == identity
    receipt = verify_static_readback(
        identity=identity,
        query_target_spawn_id=250051,
        rows=[_row(target_map_id=0)],
    )
    performed = perform_static_readback(
        identity=identity,
        query=lambda _statement, _parameters: [_row(target_map_id=0)],
    )

    assert receipt["accepted"] is True
    assert performed == receipt


def test_key_error_rebinding_before_projection_keeps_typed_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(static_identity, "KeyError", RuntimeError, raising=False)

    with pytest.raises(
        StaticTargetIdentityError, match="target_identity_unbound:target_entry"
    ):
        identity_from_projection(
            {
                "runtime_target_guid": 39,
                "target_spawn_id": 250051,
                "target_map_id": 669,
            }
        )


def test_type_error_rebinding_before_row_verification_keeps_typed_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(static_identity, "TypeError", RuntimeError, raising=False)

    with pytest.raises(StaticTargetIdentityError, match="static_target_rows_invalid"):
        verify_static_readback(
            identity=_identity(),
            query_target_spawn_id=250051,
            rows=None,  # type: ignore[arg-type]
        )


def test_value_error_rebinding_before_row_verification_keeps_typed_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InvalidRows:
        def __iter__(self):
            raise ValueError("invalid rows")

    monkeypatch.setattr(static_identity, "ValueError", RuntimeError, raising=False)

    with pytest.raises(StaticTargetIdentityError, match="static_target_rows_invalid"):
        verify_static_readback(
            identity=_identity(),
            query_target_spawn_id=250051,
            rows=InvalidRows(),
        )


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ([], "static_target_row_count_mismatch"),
        ([_row(), _row()], "static_target_row_count_mismatch"),
        ([_row(target_entry=41571)], "static_target_entry_mismatch"),
    ],
)
def test_callback_time_semantic_rebinding_cannot_accept_invalid_rows(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[dict[str, object]],
    reason: str,
) -> None:
    calls: list[tuple[str, tuple[int]]] = []

    def query(statement: str, parameters: tuple[int]):
        calls.append((statement, parameters))
        replacements = {
            "int": str,
            "bool": int,
            "dict": list,
            "isinstance": lambda *_: False,
            "list": lambda _: [_row()],
            "len": lambda _: 1,
            "set": lambda _: {
                "target_spawn_id",
                "target_entry",
                "target_map_id",
            },
            "KeyError": RuntimeError,
            "TypeError": RuntimeError,
            "ValueError": RuntimeError,
        }
        for name, replacement in replacements.items():
            monkeypatch.setattr(static_identity, name, replacement, raising=False)
        return rows

    with pytest.raises(StaticTargetIdentityError, match=reason):
        perform_static_readback(identity=_identity(), query=query)

    assert calls == [(STATIC_READBACK_SQL, (250051,))]


def test_callback_time_semantic_rebinding_preserves_success_and_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, tuple[int]]] = []

    def query(statement: str, parameters: tuple[int]):
        calls.append((statement, parameters))
        replacements = {
            "int": str,
            "bool": int,
            "dict": list,
            "isinstance": lambda *_: False,
            "list": lambda _: [],
            "len": lambda _: 0,
            "set": lambda _: {"forged"},
            "KeyError": RuntimeError,
            "TypeError": RuntimeError,
            "ValueError": RuntimeError,
        }
        for name, replacement in replacements.items():
            monkeypatch.setattr(static_identity, name, replacement, raising=False)
        return [_row()]

    receipt = perform_static_readback(identity=_identity(), query=query)

    assert calls == [(STATIC_READBACK_SQL, (250051,))]
    assert receipt["accepted"] is True
    assert receipt["query"]["statement"] == calls[0][0]


@pytest.mark.parametrize("rows", [None, 7])
def test_callback_time_exception_rebinding_keeps_typed_failure(
    monkeypatch: pytest.MonkeyPatch, rows: object,
) -> None:
    calls: list[tuple[str, tuple[int]]] = []

    def query(statement: str, parameters: tuple[int]):
        calls.append((statement, parameters))
        monkeypatch.setattr(static_identity, "TypeError", RuntimeError, raising=False)
        monkeypatch.setattr(static_identity, "ValueError", RuntimeError, raising=False)
        return rows

    with pytest.raises(StaticTargetIdentityError, match="static_target_rows_invalid"):
        perform_static_readback(identity=_identity(), query=query)

    assert calls == [(STATIC_READBACK_SQL, (250051,))]


def test_canonical_reachable_closures_have_no_semantic_global_fallbacks() -> None:
    semantic_names = {
        "int",
        "bool",
        "dict",
        "isinstance",
        "list",
        "len",
        "set",
        "KeyError",
        "TypeError",
        "ValueError",
    }
    pending = [
        target_identity,
        validate_target_identity,
        identity_from_projection,
        static_readback_request,
        verify_static_readback,
        perform_static_readback,
    ]
    reachable: dict[int, types.FunctionType] = {}
    while pending:
        function = pending.pop()
        if id(function) in reachable:
            continue
        reachable[id(function)] = function
        for cell in function.__closure__ or ():
            value = cell.cell_contents
            if isinstance(value, types.FunctionType):
                pending.append(value)

    fallbacks = {
        (function.__qualname__, instruction.argval)
        for function in reachable.values()
        for instruction in dis.get_instructions(function)
        if instruction.opname == "LOAD_GLOBAL"
        and instruction.argval in semantic_names
    }

    assert len(reachable) >= 12
    assert fallbacks == set()


def test_runtime_guid_cannot_be_substituted_as_static_spawn_key() -> None:
    with pytest.raises(
        StaticTargetIdentityError,
        match="runtime_target_guid_used_as_static_spawn_key",
    ):
        verify_static_readback(
            identity=_identity(), query_target_spawn_id=39,
            rows=[_row(target_spawn_id=39)],
        )


@pytest.mark.parametrize(
    ("query_key", "rows", "reason"),
    [
        (250052, [_row()], "target_spawn_id_query_mismatch"),
        (250051, [], "static_target_row_count_mismatch"),
        (250051, [_row(), _row()], "static_target_row_count_mismatch"),
        (250051, [_row(target_spawn_id=250052)], "static_target_spawn_id_mismatch"),
        (250051, [_row(target_entry=41571)], "static_target_entry_mismatch"),
        (250051, [_row(target_map_id=670)], "static_target_map_id_mismatch"),
        (
            250051,
            [{"target_spawn_id": 250051, "target_entry": 41570}],
            "static_target_row_metadata_unbound",
        ),
    ],
)
def test_static_readback_fails_closed_on_wrong_or_unbound_rows(
    query_key: int, rows: list[dict[str, object]], reason: str,
) -> None:
    with pytest.raises(StaticTargetIdentityError, match=reason):
        verify_static_readback(
            identity=_identity(), query_target_spawn_id=query_key, rows=rows,
        )


@pytest.mark.parametrize(
    "field",
    ["runtime_target_guid", "target_spawn_id", "target_entry"],
)
@pytest.mark.parametrize("invalid", [True, False, 0, -1, "39", 39.0])
def test_identity_rejects_bool_and_non_positive_or_non_integer_values(
    field: str, invalid: object,
) -> None:
    with pytest.raises(StaticTargetIdentityError, match=f"{field}_invalid"):
        _identity(**{field: invalid})


def test_map_zero_is_a_valid_static_identity_domain_value() -> None:
    identity = _identity(target_map_id=0)
    receipt = verify_static_readback(
        identity=identity,
        query_target_spawn_id=250051,
        rows=[_row(target_map_id=0)],
    )

    assert identity["target_map_id"] == 0
    assert receipt["row"]["target_map_id"] == 0


@pytest.mark.parametrize("invalid", [True, False, -1, "0", 0.0])
def test_identity_rejects_invalid_map_domain_values(invalid: object) -> None:
    with pytest.raises(StaticTargetIdentityError, match="target_map_id_invalid"):
        _identity(target_map_id=invalid)


@pytest.mark.parametrize("rows", [None, 7])
def test_static_readback_rejects_non_iterable_rows_with_typed_reason(
    rows: object,
) -> None:
    with pytest.raises(StaticTargetIdentityError, match="static_target_rows_invalid"):
        verify_static_readback(
            identity=_identity(),
            query_target_spawn_id=250051,
            rows=rows,  # type: ignore[arg-type]
        )


def test_identity_rejects_missing_or_noncanonical_metadata() -> None:
    missing = _identity()
    del missing["target_spawn_id"]
    with pytest.raises(StaticTargetIdentityError, match="target_identity_unbound"):
        validate_target_identity(missing)

    drifted = _identity()
    drifted["static_readback_key"] = "runtime_target_guid"
    with pytest.raises(
        StaticTargetIdentityError, match="target_identity_metadata_mismatch"
    ):
        validate_target_identity(drifted)
