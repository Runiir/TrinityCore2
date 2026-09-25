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
        assert document["unresolved_material_count"] == len(document["unresolved"]) == 10
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
    assert health["status"] == "conflict"


def test_wcl_files_are_explicitly_pending() -> None:
    dps = load(WCL_DPS)
    casts = load(WCL_CASTS)
    assert dps["schema"] == "nefarian_wcl_dps_reference_v1"
    assert casts["schema"] == "nefarian_wcl_cast_timelines_v1"
    for document in (dps, casts):
        assert document["status"] == "pending_extraction"
        assert document["mode"] == "10N"
    assert dps["references"] == []
    assert casts["actors"] == []
    assert len(dps["extraction_plan"]["candidate_reports_to_open_first"]) >= 3


def test_raid_target_matches_the_canonical_nefarian_shard() -> None:
    target = load(TARGET)
    composition = load(COMPOSITION)
    boss = next(row for row in composition["bosses"] if row["boss_key"] == "nefarian")
    assert target["schema"] == "raid_target_v1"
    assert target["composition_id"] == composition["composition_id"]
    assert target["matched_reference_ids"] == []
    assert target["reference_status"] == "pending_extraction"
    assert (ROOT / target["wcl_reference_manifest"]).is_file()
    assert target["lockout"]["precompleted_boss_keys"] == [
        "magmaw", "omnotron", "chimaeron", "atramedes", "maloriak"]
    specs = {}
    for character in composition["characters"]:
        chosen = boss["spec_selection"].get(character["character_key"], character["specs"][0])
        specs[character["slot"]] = chosen
    roster = target["roster"]
    assert len(roster) == 10
    for guid, actor in roster.items():
        assert specs[int(guid) - 11005000] == actor["spec"]
    roles = [actor["role"] for actor in roster.values()]
    assert (roles.count("tank"), roles.count("healer"), roles.count("dps")) == (2, 3, 5)
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
