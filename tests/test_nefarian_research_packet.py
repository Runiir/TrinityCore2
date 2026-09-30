"""Data checks for the Nefarian's End research packet and raid target."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENCOUNTERS = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent"
CONTRACT = ENCOUNTERS / "nefarian_v1.json"
LEDGER = ENCOUNTERS / "nefarian_ledger_v1.json"
WCL_DPS = ENCOUNTERS / "nefarian_wcl_dps_reference_v1.json"
WCL_CASTS = ENCOUNTERS / "nefarian_wcl_cast_timelines_v1.json"
TARGET = ROOT / "experiments/configs/raid_targets/blackwing_descent_10n_nefarian.json"
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
DOSSIER = ROOT / "docs/bot_raids/strategies/t11/blackwing_descent/nefarian.md"
MODES = ["10N", "10H", "25N", "25H"]
TIER11_REFERENCE_IDS = [
    "MxFq7TRbvnjGY1hJ-fight35", "cYg4C93QNdqKfPF1-fight18", "Z186QkDJrHATNcVW-fight48",
    "ap7MNG1nYQcqtyZF-fight29", "8vxjXMR9fzgbJKBa-fight29", "FBvRDV7qHdYQpmxa-fight33",
    "PkbmWVZ6HrMy1RLB-fight25", "XKF12kztLBgvPn9T-fight11", "wBP9YzgJ73xCNAr4-fight48",
    "p9Kb2tRF7VwBQPcn-fight18",
]


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_contract_and_ledger_agree_and_fail_closed() -> None:
    contract = load(CONTRACT)
    ledger = load(LEDGER)
    for document in (contract, ledger):
        assert document["fidelity_state"] == "fidelity_blocked"
        assert document["modes"] == MODES
        assert document["unresolved_material_count"] == len(document["unresolved"]) == 8
    ledger_keys = [row["key"] for row in ledger["unresolved"]]
    assert contract["unresolved"] == ledger_keys
    assert all(row["status"] != "resolved" for row in ledger["unresolved"])
    assert contract["ledger_path"] == str(LEDGER.relative_to(ROOT))
    assert ledger["contract_path"] == str(CONTRACT.relative_to(ROOT))
    assert ledger["fidelity_target"]["build"] == "4.4.2.59185"


def test_ledger_rows_cite_known_sources() -> None:
    ledger = load(LEDGER)
    catalog = {row["id"] for row in ledger["source_catalog"]}
    for section in ("values", "timers", "research_completion"):
        for row in ledger[section]:
            assert row["key"]
            for source in row.get("source_refs", []):
                assert source in catalog, (section, row["key"], source)
    keys = {row["key"] for row in ledger["research_completion"]}
    assert {"engage_and_prerequisite", "reset_wipe_credit", "phase_transitions",
            "platform_phase", "bone_warriors", "damage_fidelity"} <= keys
    assert all(row["next"] for row in ledger["research_completion"])


def test_native_health_matches_modifier_arithmetic() -> None:
    ledger = load(LEDGER)
    health = next(row for row in ledger["values"] if row["key"] == "health")
    ten = health["mode_values"]["10N"]
    # HealthModifier x gt_npc_total_hp_exp3 (level 88 warrior 85892, level 85 paladin 77490).
    assert ten["nefarian"] == 265 * 85892
    assert ten["onyxia"] == 65 * 85892
    assert ten["prototype"] == 21 * 77490
    # WCL-derived max health (MxFq7TRbvnjGY1hJ fight 35) equals native in 10N.
    assert health["status"] == "resolved"


def test_wcl_files_hold_the_verified_10n_kills() -> None:
    dps = load(WCL_DPS)
    casts = load(WCL_CASTS)
    assert dps["schema"] == "nefarian_wcl_dps_reference_v1"
    assert casts["schema"] == "nefarian_wcl_cast_timelines_v1"
    for document in (dps, casts):
        assert document["status"] == "extracted"
        assert document["mode"] == "10N"
    ids = [ref["id"] for ref in dps["references"]]
    # Tier-11 set of 2026-09-30 (raid item level 352-366), replacing the 359.8/360/375 trio.
    assert ids == TIER11_REFERENCE_IDS
    assert "farY2cm8JMTB1jGh-fight10" not in ids
    band = dps["item_level_band"]
    assert (band["min"], band["max"]) == (352.0, 366.0)
    for ref in dps["references"]:
        assert ref["mode"] == "10N" and ref["kill"] is True
        assert all(isinstance(value, float) and value > 0 for value in ref["actor_dps"].values())
        assert band["min"] <= ref["item_level"] <= band["max"] and ref["in_item_level_band"] is True
        assert ref["average_item_level"] == ref["item_level"]
        assert ref["date"] <= "2025-02-20" and ref["after_hotfix_cutoff_2025_02_20"] is False
        assert ref["phase_coverage"]["all_three_phases"] is True
    # One enemy set: WCL's default view without Animated Bone Warriors (41918).
    assert len({ref["target_scope"] for ref in dps["references"]}) == 1
    assert "excludes Animated Bone Warriors (41918)" in dps["references"][0]["target_scope"]
    # Every gated spec has a WCL value; the exempt Feral tank is the only spec without one.
    coverage = dps["spec_coverage"]
    assert coverage["no_wcl_reference"] == ["feral_druid_tank"]
    assert "feral_druid_tank" in load(TARGET)["dps_gate_exempt_specs"]
    assert all(len(values) >= 3 for values in coverage["per_spec_values"].values())
    assert casts["reference_id"] == ids[0] and casts["duration_sec"] == 344.1
    assert casts["actors"] and all(actor["casts"] for actor in casts["actors"])
    # Cast timelines exist only for matched kills: the main kill, cYg4, and the four kills whose Fire, Elemental and
    # Assassination casts Sol captured on 2026-09-30 (tests/test_nefarian_cast_baselines.py); the retired farY2
    # timelines are no longer loaded as cast baselines.
    assert [ref["reference_id"] for ref in casts["additional_references"]] == [
        "cYg4C93QNdqKfPF1-fight18", "Z186QkDJrHATNcVW-fight48", "8vxjXMR9fzgbJKBa-fight29",
        "FBvRDV7qHdYQpmxa-fight33", "p9Kb2tRF7VwBQPcn-fight18"]
    assert {casts["reference_id"], *(ref["reference_id"] for ref in casts["additional_references"])} <= set(ids)
    assert [ref["reference_id"] for ref in casts["retired_references"]] == ["farY2cm8JMTB1jGh-fight10"]


def test_nefarian_tier11_reference_targets_match_the_wcl_summary() -> None:
    from tools.raid_program import scoreboard_core as scoreboard

    target = load(TARGET)
    manifest = load(WCL_DPS)
    assert target["matched_reference_ids"] == TIER11_REFERENCE_IDS
    assert target["native_dps_excluded_target_entries"] == [41918]
    medians = scoreboard.spec_targets(ROOT, target)
    # Per-spec medians of the ten kills (SUMMARY.md of the tier-11 read, in DPS).
    assert {spec: round(value, 2) for spec, value in medians.items()} == {
        "blood_death_knight": 12163.6, "survival_hunter": 19772.6, "fire_mage": 17429.5,
        "retribution_paladin": 17808.7, "assassination_rogue": 17651.1, "elemental_shaman": 18984.25,
        "demonology_warlock": 15359.75}
    assert {spec: len(values) for spec, values in manifest["spec_coverage"]["per_spec_values"].items()} == {
        "blood_death_knight": 5, "survival_hunter": 4, "fire_mage": 5, "retribution_paladin": 3,
        "assassination_rogue": 4, "elemental_shaman": 4, "demonology_warlock": 4}
    # Gear match first: cYg4's Fire mage (385) and Survival hunter (387) sit above the 347-371 player band.
    cyg4 = next(ref for ref in manifest["references"] if ref["id"] == "cYg4C93QNdqKfPF1-fight18")
    assert set(cyg4["actor_dps"]) == {"blood_death_knight", "demonology_warlock"}
    assert {key: entry["item_level"] for key, entry in cyg4["excluded_actor_dps"].items()} == {
        "fire_mage:Néawen": 385.0, "survival_hunter:Roiisoleil": 387.0}
    assert all("above the 347-371 player band" in entry["reason"] for entry in cyg4["excluded_actor_dps"].values())
    for ref in manifest["references"]:
        assert all(347 <= level <= 371 for level in (ref.get("actor_item_level") or {}).values()), ref["id"]
    references = scoreboard.reference_targets(ROOT, target)
    for spec in medians:
        assert references[spec]["basis"] == "wcl" and references[spec]["ratio"] == target["actor_dps_ratio"]
    assert "feral_druid_tank" not in references  # exempt, informational: no WCL value, no WoWSims fallback


def test_raid_target_matches_the_canonical_nefarian_shard() -> None:
    target = load(TARGET)
    composition = load(COMPOSITION)
    boss = next(row for row in composition["bosses"] if row["boss_key"] == "nefarian")
    assert target["schema"] == "raid_target_v1"
    assert target["composition_id"] == composition["composition_id"]
    assert target["matched_reference_ids"] == [ref["id"] for ref in load(WCL_DPS)["references"]]
    assert target["reference_status"] == "extracted"
    assert (ROOT / target["wcl_cast_timelines"]).is_file()
    assert (ROOT / target["wcl_reference_manifest"]).is_file()
    assert target["lockout"]["precompleted_boss_keys"] == [
        "magmaw", "omnotron", "chimaeron", "atramedes", "maloriak"]
    # The user's comp (user raid experience 2026-09-26): 2 tanks, 2 healers,
    # 6 DPS, the shaman Elemental; the Feral's Nature's Grasp 16689 declared.
    selection = boss["spec_selection"]
    assert selection == {"druid": "feral_druid_tank", "shaman": "elemental_shaman"}
    druid = next(c for c in composition["characters"] if c["character_key"] == "druid")
    known = set(druid.get("spells") or [])
    for spells in (druid.get("group_spells") or {}).values():
        known |= set(spells)
    assert 16689 in known, "the Feral handler's Nature's Grasp is provisioned"
    specs = {}
    for character in composition["characters"]:
        chosen = selection.get(character["character_key"], character["specs"][0])
        specs[character["slot"]] = chosen
    roster = target["roster"]
    assert len(roster) == 10
    for guid, actor in roster.items():
        assert specs[int(guid) - 11005000] == actor["spec"]
    roles = [actor["role"] for actor in roster.values()]
    assert (roles.count("tank"), roles.count("healer"), roles.count("dps")) == (2, 2, 6)
    assert "blackwing_descent_10n_nefarian_c0_diagnostic" in target["run_plan"]["argv_template"]


def test_dossier_discloses_sources_and_state() -> None:
    text = DOSSIER.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "4.4.2" in text
    assert "fidelity_blocked" in lowered
    for needle in ("wowhead.com", "icy-veins.com", "repository", "surfacegoal",
                   "650bab03981eb06b5fa6ded88e47c523caa3c7c3",
                   "4b02efec4552aef3df43c75fb19c6d8c7fdb3e6e"):
        assert needle in lowered
