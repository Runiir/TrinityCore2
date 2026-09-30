"""Omnotron Defense System research packet, raid target and native script shape."""
from __future__ import annotations

import json
import math
import re
import struct
from pathlib import Path

import pytest

from tools.raid_program import raid_shard_identity as ids

ROOT = Path(__file__).resolve().parents[1]
ENCOUNTERS = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent"
CONTRACT = ENCOUNTERS / "omnotron_defense_system_v1.json"
LEDGER = ENCOUNTERS / "omnotron_defense_system_ledger_v1.json"
WCL_REFERENCE = ENCOUNTERS / "omnotron_defense_system_wcl_dps_reference_v1.json"
WCL_TIMELINES = ENCOUNTERS / "omnotron_defense_system_wcl_cast_timelines_v1.json"
TARGET = ROOT / "experiments/configs/raid_targets/blackwing_descent_10n_omnotron_defense_system.json"
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
SCRIPTS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent"
CONTENT = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron"
DOSSIER = ROOT / "docs/bot_raids/strategies/t11/blackwing_descent/omnotron_defense_system.md"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_contract_and_ledger_share_identity_and_unresolved_list() -> None:
    contract, ledger = load(CONTRACT), load(LEDGER)
    for document in (contract, ledger):
        assert document["raid"] == "blackwing_descent"
        assert document["boss_slug"] == "omnotron_defense_system"
        assert document["fidelity_state"] == "fidelity_blocked"
        assert document["unresolved_material_count"] == len(document["unresolved"]) > 0
    assert contract["unresolved"] == ledger["unresolved"]
    assert ledger["fidelity_target"]["build"] == "4.4.2.59185"
    assert ledger["dossier_path"] == contract["dossier_path"]
    assert (ROOT / contract["dossier_path"]).is_file()


def test_ledger_completion_inventory_names_next_questions() -> None:
    ledger = load(LEDGER)
    rows = {row["key"]: row for row in ledger["research_completion"]}
    for key in ("lifecycle_engage_reset_wipe_credit", "activation_rotation", "shields",
                "construct_melee_calibration_10n", "wcl_actor_references_10n", "health_10n"):
        assert key in rows and rows[key]["next"] and rows[key]["source_refs"]
    for row in rows.values():
        for ref in row["source_refs"]:
            assert ref in ledger["source_catalog"], ref


def test_ledger_retains_client_rotation_and_native_roll() -> None:
    values = {row["key"]: row for row in load(LEDGER)["values"]}
    rotation = values["activation_rotation"]["client_rows"]
    assert rotation["78740"]["duration_ms"] == {"normal": 90000, "heroic": 60000}
    assert rotation["78697"]["duration_ms"] == {"normal": 45000, "heroic": 30000}
    assert values["lightning_conductor"]["modes"]["10N"] == "10 s"
    assert values["shared_health_and_construct_count"]["native_calculated_mode_values"]["10N"] == math.ceil(85892 * 300)
    low = (2947.9421 + 920 / 14) * 1.5
    high = (2947.9421 * 1.5 + 920 / 14) * 1.5
    assert values["construct_melee_native_roll_10n"]["modes"]["10N"] == (
        f"{low:,.1f}-{high:,.1f} per swing at DamageModifier 1")
    assert values["kill_credit_and_route_attribution"]["modes"]["10N"] == "credit creature 42180 Toxitron"


T11_REFERENCES = [
    "MxFq7TRbvnjGY1hJ-fight24", "BwaHpnPbjkWtCX4Z-fight26", "TaAF1ncP89KgpbLx-fight12",
    "mfnZAdFTLkjMBC3z-fight6", "qaKLyFTxkvc9hVpM-fight11", "kCLpgK4xBXcWahN1-fight22",
    "Z36FdRPNbAgjrqGX-fight13", "w2W84MtybL1VKCvQ-fight12", "VvXJBz2A93FRY4xm-fight15",
    "MRytXdWJxkBpfPK1-fight26"]
GATED_SPECS = {"blood_death_knight", "survival_hunter", "fire_mage", "retribution_paladin",
               "assassination_rogue", "elemental_shaman", "demonology_warlock"}


def test_wcl_manifests_hold_tier11_band_10n_kills() -> None:
    reference, timelines = load(WCL_REFERENCE), load(WCL_TIMELINES)
    assert reference["status"] == "references_extracted" and timelines["status"] == "extracted"
    ids_ = [row["id"] for row in reference["references"]]
    assert ids_ == T11_REFERENCES
    band = reference["item_level_band"]
    assert (band["min"], band["max"], band["roster_average_item_level"]) == (352.0, 366.0, 359)
    for row in reference["references"]:
        assert row["mode"] == "10N" and row["difficulty_text"] == "Normal (10 Player)"
        assert row["duration_sec"] > 0 and row["raid_dps"] > 0 and row["actor_dps"]
        assert band["min"] <= row["item_level"] <= band["max"] and row["in_item_level_band"]
        assert row["after_hotfix_cutoff_2025_02_20"] is False
        assert set(row["actor_dps"]) <= GATED_SPECS
        # One value per spec: the named actors' mean (same-spec DPS actors averaged).
        for spec, dps in row["actor_dps"].items():
            names = row["actor_names"][spec]
            values = [p["dps"] for p in row["players"] if p["name"] in names and p["class_spec"] == spec]
            assert len(values) == len(names) and abs(sum(values) / len(values) - dps) < 0.06
        for key in row["excluded_actor_dps"]:
            spec, name = key.split(":", 1)
            assert name not in row["actor_names"].get(spec, [])
    # Nine kills rotate all four constructs; the reused MxFq kill saw three.
    four = [row["id"] for row in reference["references"] if row["phase_coverage"]["all_four_damaged"]]
    assert len(four) == 9 and "MxFq7TRbvnjGY1hJ-fight24" not in four
    assert set(reference["dropped_references"]) == {"Y8ajQ7dbmKMG1RZy-fight24", "xAhkN2y9YP3KRmnJ-fight12"}

    assert timelines["reference_id"] == "w2W84MtybL1VKCvQ-fight12" and timelines["duration_sec"] > 0
    specs = [actor["class_spec"] for actor in timelines["actors"]]
    specs += [actor["class_spec"] for ref in timelines["additional_references"] for actor in ref["actors"]]
    assert len(specs) == len(set(specs)) and set(specs) == GATED_SPECS
    by_id = {row["id"]: row for row in reference["references"]}
    for ref_id, actors in [(timelines["reference_id"], timelines["actors"])] + [
            (ref["reference_id"], ref["actors"]) for ref in timelines["additional_references"]]:
        assert ref_id in by_id
        for actor in actors:
            assert actor["casts"] and actor["source_name"] in by_id[ref_id]["actor_names"][actor["class_spec"]]
            assert actor["observed_dps"] == by_id[ref_id]["actor_dps"][actor["class_spec"]]
    assert "MxFq7TRbvnjGY1hJ-fight24" in timelines["enemy_cast_timelines"]


def test_wcl_evidence_is_sourced_and_open_10n_claims_stay_blocked() -> None:
    ledger, contract = load(LEDGER), load(CONTRACT)
    assert "wcl_omnotron_10n_20260927" in ledger["source_catalog"]
    assert "wcl_omnotron_10n_20260927" in {row["id"] for row in contract["source_catalog"]}
    rows = {row["key"]: row for row in ledger["research_completion"]}
    for key in ("construct_melee_calibration_10n", "wcl_actor_references_10n", "health_10n",
                "construct_abilities_10n", "damage_scaling_electrical_discharge", "poison_bomb_death"):
        assert rows[key]["status"] == "resolved", key
        assert "wcl_omnotron_10n_20260927" in rows[key]["source_refs"]
    # Round 3 (tier-11 kills): Static Shock is attacker-centred and a non-damaging interrupt
    # gives no Converted Power on 10N; no Barrier broke in 21 kills, so only the absorb
    # amount kept 10N blocked until the user decision of 2026-09-30 ("Accept 300,000
    # (Recommended)") closed it for 10N. All three claims stay open for the other modes.
    open_10n = {item["key"] for item in ledger["unresolved"] if "10N" in item["modes"]}
    assert open_10n == set()
    by_key = {item["key"]: item for item in ledger["unresolved"]}
    assert by_key["barrier_absorb_amount"]["modes"] == ["10H", "25N", "25H"]
    assert "user_decision_20260930_omnotron_barrier_absorb_10n" in by_key["barrier_absorb_amount"]["evidence_gap"]
    assert "Accept 300,000 (Recommended)" in by_key["barrier_absorb_amount"]["evidence_gap"]
    assert "267,864" in by_key["barrier_absorb_amount"]["evidence_gap"]
    decision = ledger["source_catalog"]["user_decision_20260930_omnotron_barrier_absorb_10n"]
    assert decision["quote"] == "Accept 300,000 (Recommended)"
    assert "user_decision_20260930_omnotron_barrier_absorb_10n" in {row["id"] for row in contract["source_catalog"]}
    assert contract["difficulty_matrix"]["10N"]["barrier_absorb"] == 300000
    other_modes = {"static_shock_center_attacker_or_construct", "power_conversion_no_damage_proc"}
    by_key = {item["key"]: item for item in ledger["unresolved"]}
    for key in other_modes:
        assert by_key[key]["modes"] == ["10H", "25N", "25H"]
        assert "wcl_omnotron_10n_r3_20260930" in by_key[key]["evidence_gap"]
    assert all(item["key"].startswith("heroic_") for item in ledger["unresolved"]
               if item["key"] not in open_10n | other_modes | {"barrier_absorb_amount"})
    for key in ("static_shock_centre_10n", "arcanotron_interrupt_rotation_10n", "poison_bomb_kill_priority_10n"):
        assert rows[key]["status"] == "resolved" and "wcl_omnotron_10n_r3_20260930" in rows[key]["source_refs"]
    assert rows["power_conversion_no_damage_proc"]["status"] == "resolved_for_10N"
    # Promoted 2026-09-30 from sql/custom/staged/world to the auto-applied sql/custom/world.
    proc = ROOT / "sql/custom/world/2026_09_30_30_omnotron_defense_system_power_conversion_proc.sql"
    assert not (ROOT / "sql/custom/staged/world" / proc.name).exists()
    sql = [line for line in proc.read_text().splitlines() if line and not line.startswith("--")]
    assert sql == ["UPDATE `spell_proc` SET `SpellTypeMask` = 1 WHERE `SpellId` = 79729;"]
    assert all(item["modes"] and set(item["modes"]) <= {"10N", "10H", "25N", "25H"} for item in ledger["unresolved"])
    assert rows["barrier_periodic_break"]["status"] == "resolved_for_10N_by_user_decision"
    for document in (ledger, contract):
        assert document["fidelity_state"] == "fidelity_blocked"
        assert document["fidelity_state_by_mode"] == {"10N": "accepted", "10H": "fidelity_blocked",
                                                      "25N": "fidelity_blocked", "25H": "fidelity_blocked"}
    # The per-mode gate accepts 10N only because contract and ledger agree and no claim covers it.
    from tools.raid_program.raid_program_inputs import mode_scoped_research_state
    assert mode_scoped_research_state(ROOT, contract, None, "10N") == ("accepted", None)
    for mode in ("10H", "25N", "25H"):
        assert mode_scoped_research_state(ROOT, contract, None, mode)[0] == "fidelity_blocked"
    values = {row["key"]: row for row in ledger["values"]}
    health = values["shared_health_and_construct_count"]["wcl_10N_derivation"]["max_health_tooltip_at_pull"]
    assert set(health.values()) == {values["shared_health_and_construct_count"]["native_calculated_mode_values"]["10N"]}


def test_raid_target_follows_the_canonical_omnotron_selection() -> None:
    target, composition = load(TARGET), load(COMPOSITION)
    assert target["schema"] == "raid_target_v1"
    assert target["scenario"] == TARGET.stem
    assert target["encounter_route_node_id"] == "bwd.omnotron.encounter"
    manifest = load(ROOT / target["wcl_reference_manifest"])
    assert set(target["matched_reference_ids"]) <= {row["id"] for row in manifest["references"]}
    assert target["matched_reference_ids"] == T11_REFERENCES
    assert set(target["unmatched_reference_notes"]) == {"Y8ajQ7dbmKMG1RZy-fight24", "xAhkN2y9YP3KRmnJ-fight12"}
    assert set(target["reference_item_level"]["references"]) == set(T11_REFERENCES)
    status = target["reference_status"]
    assert status["wowsims_fallback_specs"] == [] and status["no_reference_specs"] == ["feral_druid_tank"]
    assert set(status["wcl_spec_kill_counts"]) == GATED_SPECS
    assert all(count >= 3 for count in status["wcl_spec_kill_counts"].values())
    from tools.raid_program.scoreboard_core import reference_targets
    targets = reference_targets(ROOT, target)
    for spec in GATED_SPECS:
        assert targets[spec]["basis"] == "wcl"
        assert targets[spec]["dps"] == pytest.approx(status["wcl_spec_targets"][spec])
    assert (ROOT / target["wcl_cast_timelines"]) == WCL_TIMELINES
    assert "wcl_cast_timelines_pending" not in target
    boss = next(row for row in composition["bosses"] if row["boss_key"] == "omnotron")
    assert target["cohort_id"] == ids.cohort_id("blackwing_descent", "10N", "omnotron", 0)
    expected = {}
    for character in composition["characters"]:
        packed = ids.packed_index("blackwing_descent", "10N", boss["boss_number"], 0, character["slot"])
        spec = boss["spec_selection"].get(character["character_key"], character["specs"][0])
        expected[str(ids.character_guid(packed))] = (
            ids.character_name("blackwing_descent", boss["name_code"], "10N", 0, character["slot"]), spec)
    assert {guid: (row["name"], row["spec"]) for guid, row in target["roster"].items()} == expected
    roles = [row["role"] for row in target["roster"].values()]
    assert roles.count("tank") == 2 and roles.count("healer") == 2 and roles.count("dps") == 6
    assert "bot-pool-tag" in " ".join(target["run_plan"]["argv_template"])
    assert target["validation_scenario_id"] in target["run_plan"]["argv_template"]


def test_native_script_is_split_and_carries_the_round2_fixes() -> None:
    main = (SCRIPTS / "boss_omnotron_defense_system.cpp").read_text(encoding="utf-8")
    spells = (SCRIPTS / "boss_omnotron_defense_system_spells.cpp").read_text(encoding="utf-8")
    shared = (SCRIPTS / "boss_omnotron_defense_system_shared.h").read_text(encoding="utf-8")
    for text in (main, spells, shared):
        assert len(text.splitlines()) < 1000
    assert "AddSC_boss_omnotron_defense_system_spells();" in main
    assert "void AddSC_boss_omnotron_defense_system_spells()" in spells
    assert "RegisterSpellScript(spell_omnotron_electrical_discharge_trigger);" in spells
    discharge = main[main.index("case EVENT_ELECTRICAL_DISCHARGE:"):]
    discharge = discharge[:discharge.index("break;")]
    assert "DoCastAOE(SPELL_ELECTRICAL_DISCHARGE_TRIGGER);" in discharge
    acquiring = main[main.index("case EVENT_ACQUIRING_TARGET:"):]
    assert "_events.Repeat(IsHeroic() ? 26s : 40s);" in acquiring[:acquiring.index("break;")]
    assert "_events.ScheduleEvent(EVENT_POISON_SOAKED_SHELL, IsHeroic() ? 40s : 50s);" in main
    protocol = main[main.index("case EVENT_POISON_PROTOCOL:"):]
    protocol = protocol[:protocol.index("break;")]
    assert "if (++_poisonProtocolCasts < 2)" in protocol and "IsHeroic() ? 25s : 45s" in protocol
    # Every registration of the original file survives the split exactly once.
    registrations = re.findall(r"Register(?:BlackwingDescentCreatureAI|SpellScript)\((\w+)\)", main + spells)
    assert len(registrations) == len(set(registrations)) == 22


def test_strategy_constants_match_the_execution_client() -> None:
    dbc = ROOT / "data/dbc/enUS/SpellDifficulty.dbc"
    if not dbc.is_file():
        pytest.skip("execution client DBC not present")
    data = dbc.read_bytes()
    _, count, fields, size, _ = struct.unpack_from("<4s4I", data)
    rows = {}
    for index in range(count):
        record = struct.unpack_from(f"<{fields}I", data, 20 + index * size)
        rows[record[1]] = list(record[1:5])
    facts = (CONTENT / "BotOmnotronFacts.h").read_text(encoding="utf-8")
    for name, ids_ in re.findall(r"SpellSet (\w+)\{ ([0-9, ]+) \};", facts):
        values = [int(value) for value in ids_.split(",")]
        assert rows[values[0]] == values, name


def test_arena_disc_is_walkable_on_the_map_669_navmesh() -> None:
    tiles = sorted((ROOT / "data/mmaps").glob("669*.mmtile"))
    if not tiles:
        pytest.skip("map 669 navmesh not present")
    center = (-324.78, -399.078)
    polygons = []
    for tile in tiles:
        blob = tile.read_bytes()
        header = struct.unpack_from("<15i", blob, 20)
        poly_count, vert_count = header[6], header[7]
        verts = [struct.unpack_from("<3f", blob, 120 + 12 * i) for i in range(vert_count)]
        base = 120 + 12 * vert_count
        for index in range(poly_count):
            offset = base + 32 * index
            indices = struct.unpack_from("<6H", blob, offset + 4)
            vertex_count, area = struct.unpack_from("<BB", blob, offset + 30)
            if area >> 6:
                continue
            points = [(verts[i][2], verts[i][0], verts[i][1]) for i in indices[:vertex_count]]
            z = sum(point[2] for point in points) / vertex_count
            if 205.0 < z < 222.0:
                polygons.append(points)

    def inside(x: float, y: float) -> bool:
        for points in polygons:
            hit = False
            for i in range(len(points)):
                x1, y1 = points[i][0], points[i][1]
                x2, y2 = points[(i + 1) % len(points)][0], points[(i + 1) % len(points)][1]
                if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                    hit = not hit
            if hit:
                return True
        return False

    for radius in (5.0, 12.0, 20.0):
        for degrees in range(0, 360, 6):
            angle = math.radians(degrees)
            assert inside(center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius)


def test_runtime_candidate_attempts_capture_only_live_context() -> None:
    source = (CONTENT / "BotWorldPopulationMgrOmnotronCandidates.cpp").read_text(encoding="utf-8")
    captures = re.findall(r"\bAttempt\s*=\s*(\[[^\]]*\])\s*\(", source, re.DOTALL)
    assert len(captures) == 5
    for capture in captures:
        assert "&context" in capture and not re.search(r"(?:\[|,)\s*&\s*(?:,|\])", capture)
    assert "ApplyOffenseRestriction" in source
    # Interrupts and taunts widen the restriction for their one cast only.
    for marker in ("native_interrupt_submitted", "native_taunt_submitted"):
        attempt = source[:source.index(marker)]
        attempt = attempt[attempt.rindex("Attempt ="):]
        assert "SingleCastAllowance" in attempt
    assert source.count("std::optional<BotEncounter::Omnotron::SingleCastAllowance>") == 2
    authority = (CONTENT / "BotOmnotronOffenseAuthority.h").read_text(encoding="utf-8")
    assert "SetCurrentEncounterRestrictions" in authority
    assert len(source.splitlines()) < 1000


def test_dossier_discloses_sources_and_blocked_state() -> None:
    text = DOSSIER.read_text(encoding="utf-8")
    for token in ("4.4.2", "fidelity_blocked", "wowhead.com", "icy-veins.com", "repository",
                  "boss_omnotron_defense_system_spells.cpp", "42180"):
        assert token in text


def test_damage_calibration_registry_patch_is_schema_valid_and_honest() -> None:
    from tools.bot_ml.live_validation_fidelity import REGISTRY_STATUSES, load_registry

    patch = load(ENCOUNTERS / "omnotron_defense_system_damage_calibration_registry_patch_v1.json")
    registry = load_registry(ROOT)
    assert patch["target"] == "experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json"
    assert (ROOT / patch["staged_sql"]).is_file()
    creatures = patch["creatures"]
    for entry, row in creatures.items():
        assert entry.isdigit() and row["status"] in REGISTRY_STATUSES
        assert row["role"] in ("boss", "add") and row["mode"] in ("10N", "25N", "10H", "25H")
        assert row["boss"] == "omnotron_defense_system" and isinstance(row["base_entry"], int)
        if row["status"] == "calibrated":
            assert entry in ("42166", "42178", "42179", "42180") and row["damage_modifier"] == 11.2
            assert row["evidence"]["wcl_mode"] == "10N"
        else:
            assert row["damage_modifier"] is None  # nothing else has a matched sample
            assert row.get("open_reason") if row["status"] == "open" else row.get("reason")
        if entry in registry["creatures"]:
            current = registry["creatures"][entry]
            # Applied verbatim; the four calibrated rows may still be the open rows until the
            # coordinator applies this packet's registry patch together with the staged SQL.
            assert current == row or (row["status"] == "calibrated" and current["status"] == "open")
    bosses_10n = {entry for entry, row in creatures.items() if row["role"] == "boss" and row["mode"] == "10N"}
    assert bosses_10n == {"42166", "42178", "42179", "42180", "42186"}
    assert all(creatures[entry]["template_at_audit"]["base_attack_time_ms"] == 1500
               for entry in ("42166", "42178", "42179", "42180"))
    # Every Poison Bomb and Chemical Cloud difficulty entry has its own row.
    for entry, mode in (("49121", "25N"), ("49122", "10H"), ("49123", "25H")):
        row = creatures[entry]
        assert row["status"] == "open" and row["mode"] == mode and row["base_entry"] == 42897
        assert "ledger" not in row
    for entry, mode in (("49118", "25N"), ("49119", "10H"), ("49120", "25H")):
        row = creatures[entry]
        assert row["status"] == "not_applicable" and row["mode"] == mode and row["base_entry"] == 42934
