from __future__ import annotations

import pytest

from tools.raid_program.profile_combat_range_static_identity import (
    PENDING_LIVE_PROOF,
    STATIC_READBACK_SQL,
    StaticTargetIdentityError,
    perform_static_readback,
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
    ["runtime_target_guid", "target_spawn_id", "target_entry", "target_map_id"],
)
@pytest.mark.parametrize("invalid", [True, False, 0, -1, "39", 39.0])
def test_identity_rejects_bool_and_non_positive_or_non_integer_values(
    field: str, invalid: object,
) -> None:
    with pytest.raises(StaticTargetIdentityError, match=f"{field}_invalid"):
        _identity(**{field: invalid})


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
