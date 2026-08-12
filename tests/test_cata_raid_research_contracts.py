from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "experiments/configs/cata_raid_strategy_catalog_v1.json"
ACCEPTANCE_POLICY = ROOT / "experiments/configs/cata_raid_acceptance_policy_v1.json"
SCRIPT_READINESS = ROOT / "experiments/configs/cata_raid_script_readiness_v1.json"
SOURCE_REGISTRY = ROOT / "experiments/configs/cata_raid_quantitative_source_registry_v1.json"
SCENARIO_AUDIT = ROOT / "experiments/configs/cata_raid_bwd_10n_scenario_audit_v1.json"
SCENARIO_CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
PROVISIONING_CONFIG = ROOT / "experiments/configs/validation_provisioning_cata_001.json"
ROSTER = ROOT / "experiments/configs/cata_raid_roster_25_v1.json"
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
    assert target["client_build_frozen"] is True
    assert target["hotfix_cutoff_frozen"] is True
    assert target["client_data_hashes_frozen"] is True
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


def test_raid_acceptance_policy_fails_closed_until_identity_is_frozen() -> None:
    policy = load(ACCEPTANCE_POLICY)
    target = policy["fidelity_target"]
    assert target["patch"] == "4.4.2"
    assert target["locale"] == "enUS"
    assert target["client_build"] == 59185
    assert target["client_build_status"] == "frozen_from_public_secondary_build_table"
    assert target["client_data_hashes"][0]["dvc_md5"] == "eff38325fc3aeac0fa15d0c81b2be901"
    assert target["fidelity_gate"] == "research_unresolved"
    assert policy["authoritative_requirements"]["zero_forbidden_assistance"] is True
    forbidden = set(policy["forbidden_certification_assistance"])
    assert "encounter_state_injection" in forbidden
    assert "missing_boss_or_actor_spawn" in forbidden
    hierarchy = policy["quantitative_evidence_hierarchy"]
    assert [row["rank"] for row in hierarchy] == [1, 2, 3, 4, 5]
    assert hierarchy[0]["kind"] == "primary_client_and_official_blizzard"
    assert hierarchy[-1]["kind"] == "repository_implementation"
    assert policy["target_source_metadata"]["official_launch_notes"]["authority"] == "official_blizzard"


def test_quantitative_source_registry_pins_available_inputs_and_blocks_missing_inputs() -> None:
    registry = load(SOURCE_REGISTRY)
    assert registry["target"]["launch_build"] == 59185
    assert registry["target"]["hotfix_cutoff_utc"] == "2025-02-20T23:00:00Z"
    sources = {row["source_id"]: row for row in registry["sources"]}
    unlock = sources["blizzard_dragon_soul_live_24173042"]
    assert unlock["identity"]["global_unlock_at_utc"] == "2025-02-20T23:00:00Z"
    assert sources["bigwigs_cataclysm_v11_0_13"]["commit"] == "650bab03981eb06b5fa6ded88e47c523caa3c7c3"
    assert len(sources["bigwigs_cataclysm_v11_0_13"]["archive_sha256"]) == 64
    assert sources["dbm_cataclysm_prelaunch_4b02efe"]["commit"] == "4b02efec4552aef3df43c75fb19c6d8c7fdb3e6e"
    assert sources["wowhead_442_quantitative_extract"]["status"].startswith("unresolved")
    assert sources["warcraftlogs_442_known_mode_reports"]["status"].startswith("unresolved")
    assert registry["gate"] == {
        "build_and_cutoff_frozen": True,
        "addon_inputs_pinned": True,
        "primary_client_data_pinned": True,
        "wowhead_extract_pinned": False,
        "known_mode_logs_pinned": False,
        "quantitative_fidelity_acceptance": "blocked",
    }


def test_script_readiness_inventory_reconciles_catalog_and_filesystem() -> None:
    readiness = load(SCRIPT_READINESS)
    encounters = [encounter for raid in readiness["raids"] for encounter in raid["encounters"]]
    present = [encounter for encounter in encounters if encounter["status"] == "source_present_not_runtime_validated"]
    missing = [encounter for encounter in encounters if encounter["status"] == "missing_dedicated_implementation"]
    summary = readiness["summary"]

    assert len(encounters) == summary["required_named_encounters"] == 28
    assert len(present) == summary["dedicated_source_present"] == 19
    assert len(missing) == summary["missing_dedicated_implementation"] == 9
    assert {encounter["boss"] for encounter in missing} == set(summary["known_missing_bosses"])
    assert summary["instance_foundation_incomplete"] == 1
    assert summary["runtime_ready"] == 0

    raid_roots = {
        "blackwing_descent": ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent",
        "bastion_of_twilight": ROOT / "src/server/scripts/EasternKingdoms/BastionOfTwilight",
        "throne_of_the_four_winds": ROOT / "src/server/scripts/Kalimdor/ThroneOfTheFourWinds",
        "firelands": ROOT / "src/server/scripts/Kalimdor/Firelands",
        "dragon_soul": ROOT / "src/server/scripts/Kalimdor/CavernsOfTime/DragonSoul",
    }
    for raid in readiness["raids"]:
        assert (ROOT / raid["instance_source"]).is_file()
        assert (ROOT / raid["loader"]).is_file()
        for encounter in raid["encounters"]:
            if encounter["source"] is not None:
                assert (raid_roots[raid["raid"]] / encounter["source"]).is_file()

    assert readiness["database_baseline"]["runtime_database_instance_template_audit_pending"] is False
    assert readiness["database_baseline"]["runtime_database_encounter_template_audit_pending"] is False
    assert set(readiness["database_baseline"]["instance_template_scripts"]) == {"669", "671", "720", "754", "967"}
    assert all(row["entrance_teleports"] == 1 for row in readiness["database_baseline"]["raid_map_shape_observations"].values())
    assert summary["loader_registration_complete_for_present_sources"] is True


def test_bwd_certification_route_is_native_and_fail_closed() -> None:
    config = load(SCENARIO_CONFIG)
    scenario = next(row for row in config["scenarios"] if row["id"] == "blackwing_descent_10n")
    assert scenario["map_id"] == 669
    assert scenario["difficulty"] == "normal_10man"
    assert scenario["required_roles"] == {"tank": 2, "healer": 3, "dps": 5}
    bosses = [row for row in scenario["route"] if row["kind"] == "boss"]
    assert len(bosses) == 6
    assert all(row.get("activation_summon_entry", 0) == 0 for row in bosses)

    by_label = {row["label"]: row for row in bosses}
    for label in ("Atramedes", "Nefarian"):
        assert by_label[label].get("activation_data_id", 0) == 0
        assert by_label[label]["source_guid"] == "native_instance_unlock"
    assert by_label["Omnotron Defense System"]["activation_action_entry"] == 42186
    assert by_label["Omnotron Defense System"]["activation_action_id"] == 1


def test_bwd_scenario_audit_reconstructs_and_blocks_unproven_native_unlocks() -> None:
    audit = load(SCENARIO_AUDIT)
    assert audit["scenario_id"] == "blackwing_descent_10n"
    checks = audit["independent_checks"]
    assert checks["roster_roles"]["observed"] == {"tank": 2, "healer": 3, "dps": 5}
    assert checks["boss_count"]["observed"] == 6
    assert checks["boss_entries"]["passed"] is True
    assert checks["coordinates"]["passed"] is True
    assert audit["forbidden_activation_fields_after_correction"] == {
        "boss_activation_data_ids_nonzero": 0,
        "boss_activation_summon_entries_nonzero": 0,
    }
    assert audit["certification_status"].startswith("blocked_")
    assert audit["authoritative_pass_claimed"] is False
    provisioning = load(PROVISIONING_CONFIG)
    scenario = next(row for row in provisioning["scenarios"] if row["id"] == "blackwing_descent_10n")
    tanks = [row["class_spec"] for row in scenario["bots"] if row["role"] == "tank"]
    assert tanks == ["protection_paladin", "blood_death_knight"]
    assert all(row["class_spec"] != "protection_warrior" for row in scenario["bots"])


def test_stable_raid_roster_reconstructs_exactly_25_slots_and_24_modes() -> None:
    roster = load(ROSTER)
    slots = roster["slots"]
    assert len(slots) == roster["slot_count"] == 25
    assert len({row["slot"] for row in slots}) == 25
    roles = [row["role"] for row in slots]
    assert roles.count("tank") == 2
    assert roles.count("healer") == 6
    assert roles.count("ranged_dps") == 12
    assert roles.count("melee_dps") == 5
    modes = {row["class_spec"] for row in slots}
    modes.update(row["alternate_spec"] for row in slots if "alternate_spec" in row)
    modes.update(row["alternate_role_spec"] for row in slots if "alternate_role_spec" in row)
    assert len(modes) == roster["supported_mode_count"] == 24
    assert "feral_druid_tank" in modes
    assert "protection_warrior" not in modes
