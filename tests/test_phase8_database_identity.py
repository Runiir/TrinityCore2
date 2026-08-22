from tools.bot_ml.build_phase8_evidence_identity_manifest import (
    _identity_rows,
    canonical_sha256,
)


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
