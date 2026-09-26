"""Maloriak research packet, WCL reference placeholders and raid target."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENCOUNTERS = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent"
CONTRACT = ENCOUNTERS / "maloriak_v1.json"
LEDGER = ENCOUNTERS / "maloriak_ledger_v1.json"
DPS_REFERENCE = ENCOUNTERS / "maloriak_wcl_dps_reference_v1.json"
CAST_TIMELINES = ENCOUNTERS / "maloriak_wcl_cast_timelines_v1.json"
TARGET = ROOT / "experiments/configs/raid_targets/blackwing_descent_10n_maloriak.json"
MAGMAW_TARGET = ROOT / "experiments/configs/raid_targets/blackwing_descent_10n_magmaw.json"
CATALOG = ROOT / "experiments/configs/cata_raid_strategy_catalog_v1.json"
AUDIT = ROOT / "experiments/configs/cata_raid_bwd_quantitative_resolution_audit_v1.json"
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
DOSSIER = ROOT / "docs/bot_raids/strategies/t11/blackwing_descent/maloriak.md"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_packet_identity_and_fail_closed_counts_match_the_catalog() -> None:
    contract, ledger = load(CONTRACT), load(LEDGER)
    row = next(row for row in load(CATALOG)["raids"]["blackwing_descent"]["bosses"]
               if row["boss_slug"] == "maloriak")
    for document in (contract, ledger):
        assert document["fidelity_state"] == "fidelity_blocked"
        assert document["modes"] == ["10N", "10H", "25N", "25H"]
        assert len(document["unresolved"]) == document["unresolved_material_count"]
    assert contract["unresolved_material_count"] == row["contract_unresolved_material_count"]
    assert ledger["unresolved_material_count"] == row["ledger_unresolved_material_count"]
    assert set(contract["unresolved_status"]) == set(contract["unresolved"])
    audit = next(boss for boss in load(AUDIT)["bosses"] if boss["boss_slug"] == "maloriak")
    assert {item["key"] for item in ledger["unresolved"]} == {finding["key"] for finding in audit["blockers"]}


def test_ledger_sources_and_completion_rows_are_traceable() -> None:
    ledger = load(LEDGER)
    catalog = ledger["source_catalog"]
    for source_id in ("client_442_59185_maloriak_rows_20260925", "native_stats_20260925",
                      "navmesh_669_probe_20260925", "round1_two_shard_proof_20260925", "wcl_gate_20260925"):
        assert source_id in catalog
    tables = catalog["client_442_59185_maloriak_rows_20260925"]["table_full_csv_sha256"]
    assert len(tables) == 11 and all(len(digest) == 64 for digest in tables.values())
    keys = {row["key"] for row in ledger["research_completion"]}
    assert {"arcane_storm", "remedy", "release_aberrations_and_growth_catalyst", "red_phase", "blue_phase",
            "green_phase", "phase_two", "health_and_melee_damage", "route_and_shard"} <= keys
    for row in ledger["research_completion"]:
        assert row["status"] and row["next"] and row["known"]
        assert all(ref in catalog for ref in row["source_refs"]), row["key"]
    for row in ledger["values"]:
        for ref in row.get("source_refs", []):
            assert ref in catalog, (row["key"], ref)
    # WCL-dependent values stay blocked while no report was read.
    health = next(row for row in ledger["research_completion"] if row["key"] == "health_and_melee_damage")
    assert health["status"] == "blocked"


def test_client_values_keep_the_extracted_numbers() -> None:
    values = {row["key"]: row for row in load(LEDGER)["values"]}
    assert "11309" in values["client_arcane_storm"]["value"] and "47124" in values["client_arcane_storm"]["value"]
    assert "400000" in values["client_scorching_blast"]["value"]
    assert "SHARE_DAMAGE" in values["client_scorching_blast"]["value"]
    assert "19,755,160" in values["native_health"]["value"]
    assert "4,553.3-6,764.2" in values["native_melee_roll_modifier_1"]["value"]


def test_wcl_placeholders_hold_no_measured_values() -> None:
    reference, timelines = load(DPS_REFERENCE), load(CAST_TIMELINES)
    assert reference["schema"] == "maloriak_wcl_dps_reference_v1"
    assert reference["status"] == "pending_extraction" and reference["references"] == []
    plan = reference["extraction_plan"]
    assert {row["report"] for row in plan["candidate_reports_to_open_first"]} >= {
        "Y8ajQ7dbmKMG1RZy", "MxFq7TRbvnjGY1hJ"}
    assert "1025" in plan["required_match"]
    assert timelines["schema"] == "maloriak_wcl_cast_timelines_v1"
    assert timelines["actors"] == [] and timelines["reference_id"] is None


def test_raid_target_matches_the_canonical_maloriak_shard() -> None:
    target, magmaw = load(TARGET), load(MAGMAW_TARGET)
    assert target["schema"] == "raid_target_v1"
    assert target["scenario"] == "blackwing_descent_10n_maloriak"
    assert target["encounter_route_node_id"] == "bwd.maloriak.encounter"
    assert (ROOT / target["wcl_reference_manifest"]).is_file()
    manifest_ids = {row["id"] for row in load(ROOT / target["wcl_reference_manifest"])["references"]}
    assert set(target["matched_reference_ids"]) <= manifest_ids
    for key in ("kills_per_measurement", "kills_per_batch", "actor_dps_ratio", "max_boss_window_deaths",
                "clear_rule", "noise_rule", "counting_rules", "status_rules", "fallback_reference"):
        assert target[key] == magmaw[key], key
    roster = target["roster"]
    assert len(roster) == 10
    specs = sorted(row["spec"] for row in roster.values())
    composition = load(COMPOSITION)
    selection = next(boss for boss in composition["bosses"] if boss["boss_key"] == "maloriak")["spec_selection"]
    expected = []
    for character in composition["characters"]:
        chosen = selection.get(character["character_key"].split("_")[0], character["specs"][0])
        expected.append(chosen if chosen in character["specs"] else character["specs"][0])
    assert specs == sorted(expected)
    assert sum(row["role"] == "tank" for row in roster.values()) == 2
    assert sum(row["role"] == "healer" for row in roster.values()) == 2
    for spec in ("blood_death_knight", "feral_druid_tank"):
        assert spec in target["reference_gaps"]
    # The Survival hunter (canonical since 2026-09-26) has a WoWSims fallback, so it is no gap.
    assert "survival_hunter" not in target["reference_gaps"]
    assert "survival_hunter" in target["reference_gaps"]["with_wowsims_fallback"]


def test_dossier_carries_the_contract_and_its_blockers() -> None:
    text = DOSSIER.read_text(encoding="utf-8")
    for fragment in ("4.4.2", "fidelity_blocked", "wowhead.com", "icy-veins.com", "repository",
                     "Unresolved", "boss_maloriak_spells.cpp", "BotAdaptiveMaloriakStrategy.h",
                     "(-110.0, -335.0, 67.73)", "human-verification"):
        assert fragment in text, fragment


def test_damage_registry_patch_is_schema_valid_and_honest() -> None:
    from tools.bot_ml.live_validation_fidelity import REGISTRY_STATUSES, load_registry

    patch = load(ENCOUNTERS / "maloriak_damage_calibration_registry_patch_v1.json")
    registry = load_registry(ROOT)
    assert patch["target"] == "experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json"
    assert patch["staged_sql"] is None
    creatures = patch["creatures"]
    for entry, row in creatures.items():
        assert entry.isdigit() and row["status"] in REGISTRY_STATUSES
        assert row["role"] in ("boss", "add") and row["mode"] in ("10N", "25N", "10H", "25H")
        assert row["boss"] == "maloriak" and isinstance(row["base_entry"], int)
        assert row["damage_modifier"] is None  # nothing is calibrated without a matched sample
        assert row.get("open_reason") if row["status"] == "open" else row.get("reason")
        if entry in registry["creatures"]:
            assert registry["creatures"][entry] == row  # applied verbatim, never edited
    bosses = {entry: row["mode"] for entry, row in creatures.items() if row["role"] == "boss"}
    assert bosses == {"41378": "10N", "49974": "25N", "49980": "10H", "49986": "25H"}
    assert creatures["41378"]["native_roll_at_modifier_1"] == {"min": 4553.3, "max": 6764.2}
    assert creatures["41378"]["template_at_audit"]["base_attack_time_ms"] == 1500
    for helper in ("41576", "41961", "41901", "50030", "41505", "49799"):
        assert creatures[helper]["status"] == "not_applicable"


def test_route_rows_patch_moves_the_regroup_off_the_patrol() -> None:
    import math

    patch = load(ENCOUNTERS / "maloriak_route_rows_patch_v1.json")
    assert patch["target"] == "experiments/configs/validation_scenarios_cata_001.json"
    regroup = patch["rows"]["bwd.maloriak.regroup"]
    trash = patch["rows"]["bwd.maloriak.lab_trash"]
    start = patch["start_position"]
    assert (regroup["x"], regroup["y"], regroup["z"]) == (start["x"], start["y"], start["z"])
    assert trash["pack_target_entries"] == [42802, 42803]
    assert trash["source_entry"] == 42802 and trash["source_guid"] == "250117"
    assert trash["completion_policy"] == "cluster_clear_after_pull"
    old_start = (-66.85, -315.91)
    maimgor = (-108.766, -293.486)
    patrol_far_end = (-16.0868, -235.837)

    def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    junction = (regroup["x"], regroup["y"])
    leader = (trash["x"], trash["y"])
    assert distance(junction, old_start) > 40.0  # outside patrol aggro
    assert distance(junction, maimgor) > 40.0
    assert distance(leader, patrol_far_end) > trash["cluster_radius_yards"]
    assert set(patch["apply_to_scenarios"]) >= {
        "blackwing_descent_10n_maloriak_diagnostic", "blackwing_descent_10n_maloriak_c0_diagnostic"}


def test_fix_pass_research_items_are_recorded() -> None:
    ledger = load(LEDGER)
    quotes = {(row["key"], row["source_ref"]) for row in ledger["verbatim_quotes"]}
    assert ("vial_order_random_first", "icy_cata_classic") in quotes
    assert ("vial_order_random_first", "icy_original") in quotes
    assert ("shadow_imbued_taunt", "icy_cata_classic") in quotes
    items = {row["key"]: row for row in ledger["native_fidelity_items"]}
    assert items["biting_chill_target_selection"]["status"] == "open"
    assert "10-yd spell range" in items["biting_chill_target_selection"]["native"]
    assert "mask 1614" in items["shadow_imbued_taunt_immunity"]["native"]
    conflicts = {row["key"] for row in ledger["conflicts"]}
    assert {"green_duration", "biting_chill_target_selection"} <= conflicts
    parity = ledger["source_catalog"]["dbc_434_parity_20260925"]
    assert any("88 identical" in claim for claim in parity["claims"])
    reset = next(row for row in ledger["phase_reset_credit"] if row["key"] == "reset")
    assert "Default Group" in reset["behavior"] and "always Blue" in reset["behavior"]
    blockers = {row["key"]: row for row in ledger["unresolved"]}
    assert "parity is closed" in blockers["exact_spell_coefficients_and_target_counts_by_mode"]["evidence_gap"]
    assert "counters did not survive" in blockers["AI_object_reconstruction_and_custom_counter_reset_after_evade"]["evidence_gap"]


def test_every_roster_spec_has_a_raid_prepull_consumable_contract(tmp_path: Path) -> None:
    """Round 3: the raid prepull fails the whole raid closed on the first
    roster spec without a native contract. Run r02-b1 stopped Maloriak (and
    Magmaw after its kill) on raid_prepull_unknown_spec_contract_beast_mastery_hunter."""
    import subprocess

    specs = {row["spec"] for row in load(TARGET)["roster"].values()}
    specs |= {spec for character in load(COMPOSITION)["characters"] for spec in character["specs"]}
    program = tmp_path / "prepull_contracts.cpp"
    program.write_text(
        '#include "Bots/BotWorldPopulationMgrRaidConsumables.h"\n'
        "#include <cstdio>\n"
        "int main(int argc, char** argv)\n"
        "{\n"
        "    int missing = 0;\n"
        "    for (int index = 1; index < argc; ++index)\n"
        "        if (!BotWorldPopulationMgrRaidConsumables::FindContract(argv[index]))\n"
        "        {\n"
        '            std::printf("missing %s\\n", argv[index]);\n'
        "            ++missing;\n"
        "        }\n"
        "    return missing;\n"
        "}\n",
        encoding="utf-8",
    )
    binary = tmp_path / "prepull_contracts"
    subprocess.run(
        ["c++", "-std=c++17", "-I", str(ROOT / "src/server/game"), str(program),
         str(ROOT / "src/server/game/Bots/BotWorldPopulationMgrRaidConsumableContracts.cpp"),
         "-o", str(binary)],
        check=True,
    )
    result = subprocess.run([str(binary), *sorted(specs)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout


def test_boss_row_keeps_dead_raiders_in_the_instance() -> None:
    """Round 5: without a boss recovery policy a raider who died mid-fight
    released at once; its ghost reached the portal while the encounter was in
    progress and was resurrected outside the raid (r04 rogue,
    validation_active_instance_drift). The Maloriak boss row must declare the
    policy Magmaw and Omnotron use."""
    patch = load(ENCOUNTERS / "maloriak_route_rows_patch_v1.json")
    fields = patch["boss_row_fields"]["bwd.maloriak.encounter"]
    assert fields == {"boss_recovery_policy": "native_full_wipe_only"}
    assert set(patch["apply_to_scenarios"]) == {
        "blackwing_descent_10n_maloriak_diagnostic", "blackwing_descent_10n_maloriak_c0_diagnostic",
        "blackwing_descent_10n", "blackwing_descent_10n_full_c0"}
    scenarios = load(ROOT / "experiments/configs/validation_scenarios_cata_001.json")
    policies = []

    def walk(value):
        if isinstance(value, dict):
            if value.get("node_id") in ("bwd.magmaw.encounter", "bwd.omnotron.encounter"):
                policies.append(value.get("boss_recovery_policy"))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(scenarios)
    # The policy value is the one the proven Magmaw and Omnotron rows use.
    assert policies and set(policies) == {fields["boss_recovery_policy"]}
