from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "experiments/configs/cata_raid_strategy_catalog_v1.json"
MODES = ["10N", "10H", "25N", "25H"]
BWD_BOSSES = {
    "magmaw",
    "omnotron_defense_system",
    "maloriak",
    "atramedes",
    "chimaeron",
    "nefarian",
}


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_bwd_catalog_is_complete_and_fail_closed() -> None:
    catalog = load(CATALOG)
    target = catalog["fidelity_target"]
    assert target["patch"] == "4.4.2"
    assert target["client_build_frozen"] is False
    assert target["hotfix_cutoff_frozen"] is False
    assert target["client_data_hashes_frozen"] is False
    assert target["state"] == "research_unresolved"

    bosses = catalog["raids"]["blackwing_descent"]["bosses"]
    assert {row["boss_slug"] for row in bosses} == BWD_BOSSES
    for row in bosses:
        assert row["modes"] == MODES
        assert row["fidelity_state"] == "fidelity_blocked"
        assert row["contract_unresolved_material_count"] > 0
        for key in ("dossier", "contract", "ledger"):
            assert (ROOT / row[key]).is_file()


def test_bwd_contracts_and_ledgers_share_identity_envelope() -> None:
    catalog = load(CATALOG)
    for row in catalog["raids"]["blackwing_descent"]["bosses"]:
        contract = load(ROOT / row["contract"])
        ledger = load(ROOT / row["ledger"])
        assert contract["contract_schema"] == "cata_raid_encounter_contract_v1"
        assert ledger["ledger_schema"] == "cata_raid_value_timer_ledger_v1"
        for document in (contract, ledger):
            assert document["raid"] == "blackwing_descent"
            assert document["boss_slug"] == row["boss_slug"]
            assert document["encounter"] == row["boss_slug"]
            assert document["modes"] == MODES
            assert document["fidelity_state"] == "fidelity_blocked"
            assert document["unresolved_material_count"] > 0
            assert document["unresolved"]
        assert contract["ledger_path"] == row["ledger"]
        assert ledger["contract_path"] == row["contract"]


def test_bwd_repository_source_paths_exist() -> None:
    catalog = load(CATALOG)
    expected_sources = {
        "magmaw": "boss_magmaw.cpp",
        "omnotron_defense_system": "boss_omnotron_defense_system.cpp",
        "maloriak": "boss_maloriak.cpp",
        "atramedes": "boss_atramedes.cpp",
        "chimaeron": "boss_chimaeron.cpp",
        "nefarian": "boss_nefarians_end.cpp",
    }
    source_root = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent"
    for row in catalog["raids"]["blackwing_descent"]["bosses"]:
        assert (source_root / expected_sources[row["boss_slug"]]).is_file()


def test_bwd_dossiers_disclose_non_verified_state_and_sources() -> None:
    catalog = load(CATALOG)
    for row in catalog["raids"]["blackwing_descent"]["bosses"]:
        text = (ROOT / row["dossier"]).read_text(encoding="utf-8")
        lowered = text.lower()
        assert "4.4.2" in text
        assert "unresolved" in lowered or "fidelity_blocked" in lowered
        assert "wowhead.com" in lowered
        assert "icy-veins.com" in lowered
        assert "repository" in lowered
