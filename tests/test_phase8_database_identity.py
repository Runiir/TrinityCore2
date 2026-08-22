from tools.bot_ml.build_phase8_evidence_identity_manifest import (
    _identity_rows,
    _startup_identity_rebind,
    canonical_sha256,
)

import pytest


def _snapshot(rows: list[dict[str, object]]) -> str:
    return canonical_sha256({"characters": {"item_instance": _identity_rows("item_instance", rows)}})


def test_item_durability_load_normalization_does_not_change_identity() -> None:
    before = {
        "guid": 9700386,
        "itemEntry": 58085,
        "owner_guid": 1293,
        "count": 20,
        "duration": 0,
        "charges": "",
        "flags": 0,
        "enchantments": "0 0 0 0 0",
        "randomPropertyType": 0,
        "randomPropertyId": 0,
        "durability": 1,
        "creationTime": 1787404339,
        "text": "",
    }
    after = {**before, "durability": 0}

    projected = _identity_rows("item_instance", [before])[0]
    assert set(before) - set(projected) == {"durability"}
    assert _snapshot([before]) == _snapshot([after])


def test_nonvolatile_item_identity_change_still_changes_snapshot() -> None:
    baseline = {
        "guid": 9700386,
        "itemEntry": 78689,
        "owner_guid": 1281,
        "count": 1,
        "duration": 0,
        "charges": "",
        "flags": 0,
        "enchantments": "4195 0 0 0 0",
        "randomPropertyType": 0,
        "randomPropertyId": 0,
        "durability": 100,
        "creationTime": 1787404339,
        "text": "",
    }
    changed_enchantment = {
        **baseline,
        "enchantments": "4195 0 0 0 4054",
        "durability": 0,
    }

    assert _snapshot([baseline]) != _snapshot([changed_enchantment])


def _database(snapshot: str) -> dict[str, object]:
    return {
        "database_snapshot_sha256": snapshot * 64,
        "database_schema_sha256": "s" * 64,
        "summary": {},
    }


def test_startup_identity_uses_existing_session_when_database_is_stable() -> None:
    stable = _database("a")
    reads = iter((stable, stable))
    ensured: list[str] = []
    captured: list[str] = []

    database, runtime, rebound, session = _startup_identity_rebind(
        preboot_database=stable,
        preboot_session="preboot",
        read_database=lambda: next(reads),
        build_rebound_session=lambda _: pytest.fail("stable startup must not rebind"),
        ensure_session=ensured.append,
        capture_runtime_identity=lambda active: captured.append(active) or ("runtime",),
    )

    assert database == stable
    assert runtime == ("runtime",)
    assert rebound is False
    assert session == "preboot"
    assert ensured == ["preboot"]
    assert captured == ["preboot"]


def test_startup_identity_rebinds_once_before_runtime_capture() -> None:
    preboot = _database("a")
    stable_postboot = _database("b")
    reads = iter((stable_postboot, stable_postboot))
    ensured: list[str] = []
    built: list[dict[str, object]] = []
    captured: list[str] = []

    database, runtime, rebound, session = _startup_identity_rebind(
        preboot_database=preboot,
        preboot_session="preboot",
        read_database=lambda: next(reads),
        build_rebound_session=lambda identity: built.append(dict(identity)) or "rebound",
        ensure_session=ensured.append,
        capture_runtime_identity=lambda active: captured.append(active) or (active, "runtime"),
    )

    assert database == stable_postboot
    assert runtime == ("rebound", "runtime")
    assert rebound is True
    assert session == "rebound"
    assert built == [stable_postboot]
    assert ensured == ["preboot", "rebound"]
    assert captured == ["preboot", "rebound"]


def test_startup_identity_fails_closed_on_second_database_drift() -> None:
    preboot = _database("a")
    first_postboot = _database("b")
    second_postboot = _database("c")
    reads = iter((first_postboot, second_postboot))

    with pytest.raises(RuntimeError, match="after one allowed startup rebind"):
        _startup_identity_rebind(
            preboot_database=preboot,
            preboot_session="preboot",
            read_database=lambda: next(reads),
            build_rebound_session=lambda _: "rebound",
            ensure_session=lambda _: None,
            capture_runtime_identity=lambda active: (active, "runtime"),
        )
