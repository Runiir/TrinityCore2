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
    assert set(contract["unresolved_status"]) == {claim["key"] for claim in contract["unresolved"]}
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
    # Round 3: 10N health and add melee are resolved (the add migration is staged); the other modes
    # still lack matched WCL values.
    health = next(row for row in ledger["research_completion"] if row["key"] == "health_and_melee_damage")
    assert health["status"] == "resolved_10N_staged" and "25N/10H/25H" in health["next"]


def test_client_values_keep_the_extracted_numbers() -> None:
    values = {row["key"]: row for row in load(LEDGER)["values"]}
    assert "11309" in values["client_arcane_storm"]["value"] and "47124" in values["client_arcane_storm"]["value"]
    assert "400000" in values["client_scorching_blast"]["value"]
    assert "SHARE_DAMAGE" in values["client_scorching_blast"]["value"]
    assert "19,755,160" in values["native_health"]["value"]
    assert "4,553.3-6,764.2" in values["native_melee_roll_modifier_1"]["value"]


def test_wcl_reference_and_timelines_are_the_extracted_fight() -> None:
    reference, timelines = load(DPS_REFERENCE), load(CAST_TIMELINES)
    assert reference["schema"] == "maloriak_wcl_dps_reference_v1"
    assert reference["status"] == "extracted"
    by_id = {row["id"]: row for row in reference["references"]}
    ref, longer = by_id["MxFq7TRbvnjGY1hJ-fight34"], by_id["VL3fW9wNm2PRJDYt-fight13"]
    assert longer["id"] == "VL3fW9wNm2PRJDYt-fight13" and longer["duration_sec"] == 209.6
    # The only Feral (Labraizz) tanked Maloriak; a boss-tank reference is not matched for the
    # roster's add-tanking Feral, so it is recorded but kept out of actor_dps.
    assert "feral_druid_tank" not in longer["actor_dps"]
    # Unfiltered since the round-3 fix; the default-view value is kept beside it.
    assert longer["excluded_actor_dps"]["feral_druid_tank"]["dps"] == 16335.2
    assert longer["excluded_actor_dps"]["feral_druid_tank"]["dps_default_view"] == 16202.0
    assert "blood_death_knight" not in longer["actor_dps"]  # the add-tank DK is excluded
    assert ref["id"] == "MxFq7TRbvnjGY1hJ-fight34" and ref["mode"] == "10N" and ref["duration_sec"] == 125.1
    assert ref["actor_dps"]["blood_death_knight"] == 11793.0  # main tank (unfiltered), not the add off-tank
    assert ref["actor_dps"]["survival_hunter"] == 25375.4  # median of two Survival Hunters
    assert "holy_paladin" not in ref["actor_dps"]
    plan = reference["extraction_plan"]
    assert {row["report"] for row in plan["candidate_reports_to_open_first"]} >= {
        "Y8ajQ7dbmKMG1RZy", "MxFq7TRbvnjGY1hJ"}
    assert "1025" in plan["required_match"]
    assert timelines["schema"] == "maloriak_wcl_cast_timelines_v1"
    assert timelines["reference_id"] == ref["id"] and timelines["duration_sec"] == ref["duration_sec"]
    actors = timelines["actors"]
    assert len(actors) == 9 and sum(len(actor["casts"]) for actor in actors) == 818
    blood = [actor["source_name"] for actor in actors if actor["class_spec"] == "blood_death_knight"]
    assert blood == ["Greysnout", "Wongelrainer"]  # the comparator takes the first actor per spec
    assert all(cast["t"] <= ref["duration_sec"] for actor in actors for cast in actor["casts"])


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
    assert target["matched_reference_ids"][:2] == ["MxFq7TRbvnjGY1hJ-fight34", "VL3fW9wNm2PRJDYt-fight13"]
    assert (ROOT / target["wcl_cast_timelines"]).is_file()
    # Round 2: Fire Mage and Assassination Rogue have matched WCL kills, so no roster spec
    # falls back to WoWSims; the Feral add tank still has no reference.
    assert "with_wowsims_fallback" not in target["reference_gaps"]
    matched = set()
    for reference in load(DPS_REFERENCE)["references"]:
        if reference["id"] in target["matched_reference_ids"]:
            matched |= set(reference["actor_dps"])
    for spec in ("blood_death_knight", "survival_hunter", "retribution_paladin",
                 "elemental_shaman", "demonology_warlock", "fire_mage", "assassination_rogue"):
        assert spec in specs and spec in matched
    # The add-tanking Feral has no role-matched reference: an honest no_reference gap.
    assert "feral_druid_tank" in specs and "feral_druid_tank" not in matched
    assert target["reference_gaps"]["no_reference_until_wcl"] == ["feral_druid_tank"]


def test_dossier_carries_the_contract_and_its_blockers() -> None:
    text = DOSSIER.read_text(encoding="utf-8")
    for fragment in ("4.4.2", "fidelity_blocked", "wowhead.com", "icy-veins.com", "repository",
                     "Unresolved", "boss_maloriak_spells.cpp", "BotAdaptiveMaloriakStrategy.h",
                     "(-110.0, -335.0, 67.73)", "human-verification"):
        assert fragment in text, fragment


ROUND3_ADDS = {"41440": 0.81, "41841": 3.5}


def test_damage_registry_patch_is_schema_valid_and_honest() -> None:
    from tools.bot_ml.live_validation_fidelity import REGISTRY_STATUSES, load_registry

    patch = load(ENCOUNTERS / "maloriak_damage_calibration_registry_patch_v1.json")
    registry = load_registry(ROOT)
    assert patch["target"] == "experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json"
    assert patch["staged_sql"] == "sql/custom/world/2026_09_27_22_maloriak_damage_modifier.sql"
    creatures = patch["creatures"]
    for entry, row in creatures.items():
        assert entry.isdigit() and row["status"] in REGISTRY_STATUSES
        assert row["role"] in ("boss", "add") and row["mode"] in ("10N", "25N", "10H", "25H")
        assert row["boss"] == "maloriak" and isinstance(row["base_entry"], int)
        if entry in registry["creatures"] and entry not in ROUND3_ADDS:
            assert registry["creatures"][entry] == row, entry  # applied verbatim, never edited
        if entry == "41378":  # calibrated from WCL MxFq7TRbvnjGY1hJ fight 34 (10N)
            assert row["status"] == "calibrated" and row["damage_modifier"] == 9.5
            continue
        if entry in ROUND3_ADDS:  # round 3: promoted add migration; the registry rows are applied
            assert row["status"] == "calibrated" and row["damage_modifier"] == ROUND3_ADDS[entry]
            assert registry["creatures"][entry] in (row, {**registry["creatures"][entry], "status": "open"})
            assert row["evidence"]["migration_state"] == "staged"
            continue
        assert row["damage_modifier"] is None  # nothing else has a matched same-mode sample
        assert row.get("open_reason") if row["status"] == "open" else row.get("reason")
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
    assert items["biting_chill_target_selection"]["status"] == "fixed_in_owned_script_10n_only"
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
    assert "builds a new Creature and AI" in blockers["AI_object_reconstruction_and_custom_counter_reset_after_evade"]["evidence_gap"]


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


def test_round3_t11_reference_set_is_in_band_and_drives_the_targets() -> None:
    """Round 3 (user decision 2026-09-30): phase-gear roster (~359), references at raid item level
    352-366. Every reference carries each gated roster spec it fields; the round-2 single-spec
    Fire/Assassination values are kept as actor_dps_round2."""
    import statistics

    from tools.raid_program.scoreboard_core import spec_targets

    target, reference = load(TARGET), load(DPS_REFERENCE)
    by_id = {row["id"]: row for row in reference["references"]}
    assert target["matched_reference_ids"] == list(by_id)
    assert len(by_id) == 9 and "QfJR9AZw13G6kzXP-fight14" in by_id
    for row in by_id.values():
        assert row["mode"] == "10N" and row["reference_class"] == "matched_item_level_band"
        assert 352.0 <= row["item_level"] <= 366.0 and row["in_item_level_band"] is True
        assert row["after_hotfix_cutoff_2025_02_20"] is False
        assert target["reference_item_level"]["per_reference"][row["id"]] == row["item_level"]
    # Round-2 single-spec picks are preserved, not lost.
    for ref_id in ("ZyH2KkjchMRTdXga-fight33", "XzVpNLkxaAFG3DjW-fight18", "3pvXdMVntcjxygW4-fight13",
                   "h1LaC3FZ8BwPrbXW-fight18", "hmAcWCt3njMR4HFT-fight12", "cCXgM3dx9YGKaDt7-fight28"):
        (spec, dps), = by_id[ref_id]["actor_dps_round2"].items()
        assert by_id[ref_id]["actor_dps"][spec] == dps
    # The add-tanking Blood DK (fight 13) and the second Blood DK (fight 34) stay out of actor_dps.
    assert "blood_death_knight" not in by_id["VL3fW9wNm2PRJDYt-fight13"]["actor_dps"]
    assert "blood_death_knight:Orageux" in by_id["VL3fW9wNm2PRJDYt-fight13"]["excluded_actor_dps"]
    assert "blood_death_knight:Wongelrainer" in by_id["MxFq7TRbvnjGY1hJ-fight34"]["excluded_actor_dps"]
    expected = {"blood_death_knight": 15364.3, "survival_hunter": 22932.8, "fire_mage": 18701.95,
                "retribution_paladin": 20070.75, "assassination_rogue": 20705.9,
                "elemental_shaman": 22266.0, "demonology_warlock": 20471.5}
    targets = spec_targets(ROOT, target)
    assert {spec: round(value, 2) for spec, value in targets.items()} == expected
    assert target["reference_spec_targets"] == expected
    assert reference["t11_reference_set_20260930"]["per_spec_median"] == expected
    samples = {spec: sum(spec in row["actor_dps"] for row in by_id.values()) for spec in expected}
    assert samples == target["reference_kills_per_spec"] == {
        "blood_death_knight": 6, "survival_hunter": 9, "fire_mage": 4, "retribution_paladin": 4,
        "assassination_rogue": 4, "elemental_shaman": 8, "demonology_warlock": 3}
    assert statistics.median(row["item_level"] for row in by_id.values()) == 358.9


def test_user_add_switch_decision_is_recorded_with_its_evidence() -> None:
    """User raid experience 2026-09-27: no Remedy dispel in the hold; since round 1 removed none,
    the hold starts at 50%."""
    ledger = load(LEDGER)
    source = ledger["source_catalog"]["user_raid_experience_20260927"]
    assert "stop dps at 50%" in source["quote"]
    assert "94-104 s" in source["evidence_check"] and "Branch taken: 50%" in source["evidence_check"]
    value = next(row for row in ledger["values"] if row["key"] == "add_switch_threshold_50")
    assert value["source_refs"] == ["user_raid_experience_20260927"]
    duties = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/"
              "BotMaloriakDuties.h").read_text(encoding="utf-8")
    assert "constexpr float AddSwitchHealthPct = 50.0f;" in duties
    assert "user raid experience 2026-09-27" in DOSSIER.read_text(encoding="utf-8")


def test_round3_mode_gate_accepts_10n_and_keeps_the_other_modes_blocked() -> None:
    """Round 3 accepted 10N; the round-3 fix (review finding 4) needed target-era evidence for each 10N claim
    and reopened it on the Green Arcane Storm spread after the 2025-02-20 cutoff. The native 10N script now
    draws the observed Green ranges, which closed the live timer claim for 10N again: no unresolved claim covers
    10N and the per-mode gate accepts it, while 10H/25N/25H stay blocked by their scoped claims."""
    import copy

    from tools.raid_program.raid_program_inputs import mode_scoped_research_state

    contract, ledger = load(CONTRACT), load(LEDGER)
    for document in (contract, ledger):
        assert document["fidelity_state"] == "fidelity_blocked"
        assert document["fidelity_state_by_mode"] == {
            "10N": "accepted", "10H": "fidelity_blocked", "25N": "fidelity_blocked", "25H": "fidelity_blocked"}
        assert [claim["key"] for claim in document["unresolved"] if "10N" in claim["modes"]] == []
        for claim in document["unresolved"]:
            assert claim["modes"] and set(claim["modes"]) <= {"10H", "25N", "25H"}, claim["key"]
        assert len(document["unresolved"]) == document["unresolved_material_count"]
        timer = next(claim for claim in document["unresolved"] if claim["key"].startswith("live_timer"))
        assert timer["modes"] == ["10H", "25N", "25H"]
    assert mode_scoped_research_state(ROOT, contract, None, "10N") == ("accepted", None)
    for mode in ("10H", "25N", "25H"):
        state, reason = mode_scoped_research_state(ROOT, contract, None, mode)
        assert state == "fidelity_blocked" and "not accepted" in reason
    # The gate stays live: putting 10N back on the timer claim blocks it again.
    reopened = copy.deepcopy(contract)
    timer = next(claim for claim in reopened["unresolved"] if claim["key"].startswith("live_timer"))
    timer["modes"] = ["10N", *timer["modes"]]
    state, reason = mode_scoped_research_state(ROOT, reopened, None, "10N")
    assert state == "fidelity_blocked" and "covers 10N" in reason and timer["key"] in reason
    values = {row["key"] for row in ledger["values"]}
    assert {"pre_vial_opening_10N", "biting_chill_targets_10N", "flash_freeze_targets_10N", "health_10N_wcl",
            "green_phase_10N", "fourth_vial_10N", "remedy_ramp_10N", "enrage_10N", "add_melee_10N",
            "prime_subject_rend_10N", "spell_values_10N_wcl"} <= values
    assert "whether_historical_custom_SQL_pack_is_applied_to_current_database" in ledger["resolved_20260930"]


def test_round3_add_melee_bounds_recompute_from_the_ledger_samples() -> None:
    """The staged add DamageModifiers sit inside the bounds recomputed from the ledger's WCL rows."""
    import re

    value = next(row for row in load(LEDGER)["values"] if row["key"] == "add_melee_10N")
    rolls = value["native_roll_at_modifier_1"]
    pattern = re.compile(r"(\d+):(\d+\.\d+) (Apply|Remove|Refresh) Buff(?: Stack)? Growth Catalyst Growth Catalyst (.+?) → (.+)$")

    def bounds(sample: dict, roll: list, cut: float | None = None, roar: float | None = None) -> tuple[float, float]:
        events = sorted((int(m[1]) * 60 + float(m[2]), m[3], m[4].strip(), m[5].strip())
                        for m in (pattern.match(raw) for raw in sample["growth_catalyst"]) if m)
        low, high = 0.0, float("inf")
        for row in sample["rows"]:
            if not row["u"] or (cut is not None and row["t"] > cut):
                continue
            active = set()
            for t, kind, source, target in events:
                if t > row["t"]:
                    break
                if target == row["source"]:
                    (active.discard if kind == "Remove" else active.add)(source)
            factor = 1.1 ** len(active) * 1.01 * (0.9 if roar is not None and roar <= row["t"] <= roar + 30 else 1.0)
            low, high = max(low, row["u"] / (roll[1] * factor)), min(high, row["u"] / (roll[0] * factor))
        return low, high

    samples = value["samples"]
    low, high = bounds(samples["aberration_VL3fW9wNm2PRJDYt_13"], rolls["aberration"])
    assert (round(low, 3), round(high, 3)) == (0.802, 0.824) and low <= 0.81 <= high
    vl3 = bounds(samples["prime_subject_VL3fW9wNm2PRJDYt_13"], rolls["prime_subject"])
    qf_sample = samples["prime_subject_QfJR9AZw13G6kzXP_14"]
    qf = bounds(qf_sample, rolls["prime_subject"], cut=156.0, roar=qf_sample["demoralizing_roar_from"])
    low, high = max(vl3[0], qf[0]), min(vl3[1], qf[1])
    assert (round(low, 3), round(high, 3)) == (3.394, 3.627) and low <= 3.5 <= high


# Round-3 fix pass (review findings 4 and 6, 2026-09-30).
POST_CUTOFF_SOURCE = "wcl_maloriak_10n_post_cutoff_20260930"
HOTFIX_AUDIT_SOURCE = "official_hotfix_audit_20250113_20250220"
UNFILTERED_VIEW = "unfiltered_options_8192"


def _actor_unfiltered_dps(actor: dict) -> float | None:
    return actor["dps"] if "dps" in actor else actor.get("dps_displayed")


def test_no_matched_reference_uses_the_default_damage_view() -> None:
    """Native scoring counts add damage, so every matched reference is read with View Unfiltered
    Damage (options=8192); a default-view value survives only as dps_default_view."""
    target, reference = load(TARGET), load(DPS_REFERENCE)
    by_id = {row["id"]: row for row in reference["references"]}
    assert set(target["matched_reference_ids"]) == set(by_id)
    for ref_id, row in by_id.items():
        assert row["damage_view"] == UNFILTERED_VIEW, ref_id
        assert "options=8192" in row["url"], ref_id
        assert "default damage-done view" not in row["target_scope"], ref_id
        by_name = {actor["name"]: actor for actor in row["actors"]}
        for spec, names in row["actor_names"].items():
            values = [_actor_unfiltered_dps(by_name[name]) for name in names]
            assert abs(row["actor_dps"][spec] - sum(values) / len(values)) <= 0.05, (ref_id, spec)
    # The two re-read kills (capture part_a) carry the unfiltered value and keep the default one.
    fight34, fight13 = by_id["MxFq7TRbvnjGY1hJ-fight34"], by_id["VL3fW9wNm2PRJDYt-fight13"]
    for row in (fight34, fight13):
        assert row["damage_view_source"] == POST_CUTOFF_SOURCE
        assert all("dps_default_view" in actor for actor in row["actors"])
    greysnout = next(actor for actor in fight34["actors"] if actor["name"] == "Greysnout")
    assert (greysnout["dps_displayed"], greysnout["dps_default_view"]) == (11793.0, 11681.9)
    xenass = next(actor for actor in fight13["actors"] if actor["name"] == "Xenass")
    assert (xenass["dps_displayed"], xenass["dps_default_view"]) == (22112.5, 19314.1)
    assert fight13["actor_dps"] == {"survival_hunter": 20488.7, "retribution_paladin": 20432.7,
                                    "demonology_warlock": 20471.5}
    # The add-tanking Blood DK Orageux stays excluded, now with his unfiltered value.
    assert fight13["excluded_actor_dps"]["blood_death_knight:Orageux"]["dps"] == 5040.5
    assert "blood_death_knight" not in fight13["actor_dps"]
    t11 = reference["t11_reference_set_20260930"]
    assert "scope_caveat" not in t11
    assert POST_CUTOFF_SOURCE in t11["scope_resolution"] and "options=8192" in t11["scope_resolution"]
    assert "default damage-done view" not in json.dumps(target["reference_gaps"])


def test_reference_medians_reconcile_with_the_rows() -> None:
    import statistics

    target, reference = load(TARGET), load(DPS_REFERENCE)
    t11 = reference["t11_reference_set_20260930"]
    values: dict[str, list[float]] = {}
    for row in reference["references"]:
        for spec, dps in row["actor_dps"].items():
            values.setdefault(spec, []).append(dps)
    medians = {spec: round(statistics.median(dps), 2) for spec, dps in values.items()}
    samples = {spec: len(dps) for spec, dps in values.items()}
    assert t11["per_spec_median"] == medians == target["reference_spec_targets"]
    assert t11["per_spec_samples"] == samples == target["reference_kills_per_spec"]
    assert all(count >= 3 for count in samples.values()), samples
    longer = t11["longer_half_context"]
    by_id = {row["id"]: row for row in reference["references"]}
    rows = [by_id[ref_id] for ref_id in longer["reference_ids"]]
    for spec in longer["median"]:
        dps = [row["actor_dps"][spec] for row in rows if spec in row["actor_dps"]]
        assert longer["median"][spec] == round(statistics.median(dps), 2), spec
        assert longer["samples"][spec] == len(dps), spec


def _post_cutoff_closed_claims(document: dict) -> list[dict]:
    return [claim for claim in document["unresolved"]
            if (claim.get("target_era_10N") or {}).get("status") in ("closed_target_era", "bounded_by_official_audit")]


def test_10n_claims_closed_on_target_era_evidence_cite_the_capture_and_the_audit() -> None:
    """Finding 4: pre-cutoff kills alone cannot close the 2025-02-20 target. Every 10N claim part closed
    in round 3 now cites the post-cutoff capture and the official hotfix audit; a mechanic that disagrees
    after the cutoff keeps its claim open on 10N."""
    contract, ledger = load(CONTRACT), load(LEDGER)
    catalog = ledger["source_catalog"]
    capture, audit = catalog[POST_CUTOFF_SOURCE], catalog[HOTFIX_AUDIT_SOURCE]
    assert capture["mode"] == "10N" and len(capture["reports"]) == 5
    assert all(date >= "2025-02-21" for date in capture["dates"].values())
    assert capture["raw_capture"].endswith("wcl_round3_maloriak_bwd10n_20260930.tar.gz")
    assert audit["interval"] == ["2025-01-13", "2025-02-20"] and audit["none_found"] is True
    assert len(audit["sources_read"]) >= 3
    corroboration = next(row for row in ledger["values"] if row["key"] == "target_era_corroboration_10N")
    assert set(corroboration["source_refs"]) >= {POST_CUTOFF_SOURCE, HOTFIX_AUDIT_SOURCE}
    statuses = {row["mechanic"]: row["status"] for row in corroboration["mechanics"]}
    assert statuses["remedy_ramp"] == statuses["opening_and_first_vial"] == "corroborated"
    assert statuses["green_arcane_storm_offset"] == "modelled_by_native_draw"
    assert statuses["berserk_7_min"] == "not_observed"
    for document in (contract, ledger):
        closed = _post_cutoff_closed_claims(document)
        assert len(closed) == len(document["unresolved"])  # the timer claim is closed for 10N too
        for claim in closed:
            assert "10N" not in claim["modes"], claim["key"]
            assert {POST_CUTOFF_SOURCE, HOTFIX_AUDIT_SOURCE} <= set(claim["target_era_10N"]["source_refs"]), claim["key"]
            assert POST_CUTOFF_SOURCE in claim["evidence_gap"] and HOTFIX_AUDIT_SOURCE in claim["evidence_gap"]
            assert "so any Maloriak hotfix carryover" not in claim["evidence_gap"], claim["key"]
        timer = next(claim for claim in document["unresolved"] if claim["key"].startswith("live_timer"))
        assert "10N" not in timer["modes"] and timer["target_era_10N"]["status"] == "closed_target_era"
        assert timer["target_era_10N"]["bounded_parts"] == ["fourth_vial_after_green"]
        for fragment in ("Arcane Storm", "Slime Imbued", "3.1-6.1 s", "7.3-14.2 s", "ScheduleGreenPhaseCasts", "14.15 s",
                         "begin time", "0.474-0.531 s", "3.13-6.10 s", "instant cast"):
            assert fragment in timer["evidence_gap"], fragment
        assert "3.6-6.6 s" not in json.dumps(document)  # the cast-row span is not the begin-time range
        assert "open" not in timer["target_era_10N"]["status"] and "Resolve the Green storm spread" not in timer["evidence_gap"]
        cutoff = next(claim for claim in document["unresolved"] if claim["key"].startswith("exact_442"))
        assert cutoff["target_era_10N"]["status"] == "closed_target_era"
        assert document["fidelity_state_by_mode"]["10N"] == "accepted"
    completion = {row["key"]: row["status"] for row in ledger["research_completion"]}
    assert completion["green_phase"] == "resolved_10N"
    item = next(row for row in ledger["native_fidelity_items"] if row["key"] == "green_arcane_storm_offset_10N")
    assert item["status"] == "fixed_in_owned_script_10n_only"
    for key, text in contract["unresolved_status"].items():
        assert text == next(claim["evidence_gap"] for claim in contract["unresolved"] if claim["key"] == key)


def test_target_era_fix_reaches_the_audit_row_and_the_dossier() -> None:
    audit = next(boss for boss in load(AUDIT)["bosses"] if boss["boss_slug"] == "maloriak")
    rows = {row["key"]: row for row in audit["blockers"]}
    cutoff = rows["exact_442_client_build_and_BWD_hotfix_cutoff"]
    assert "10N_Maloriak_hotfix_carryover_resolved" in cutoff["resolution_state"]
    assert HOTFIX_AUDIT_SOURCE in cutoff["remaining_gap"] and POST_CUTOFF_SOURCE in cutoff["remaining_gap"]
    timer = rows["live_timer_and_movement_confirmation_for_10N_10H_25N_25H"]
    assert "Slime Imbued" in timer["remaining_gap"] and "native 10N script now draws" in timer["remaining_gap"]
    assert timer["resolution_state"].startswith("10N_resolved") and "non_10N_unresolved" in timer["resolution_state"]
    assert "covers 10N again" not in timer["remaining_gap"] and "native fixed 4.0 s" not in timer["remaining_gap"]
    assert "native 10N script now draws" in cutoff["remaining_gap"]
    text = DOSSIER.read_text(encoding="utf-8")
    for fragment in (POST_CUTOFF_SOURCE, HOTFIX_AUDIT_SOURCE, "wcl_round3_maloriak_bwd10n_20260930.tar.gz",
                     "Retribution 20,071", "Demonology 20,472", "3.66-6.57 s", "ScheduleGreenPhaseCasts",
                     "10N: none (accepted 2026-09-30", "3.1-6.1 s", "7.3-14.2 s"):
        assert fragment in text, fragment
    assert "blocked on one claim" not in text and "A native draw over the observed Green storm" not in text
    assert "10N is `accepted`" in text
