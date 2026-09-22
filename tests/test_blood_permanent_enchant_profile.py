from __future__ import annotations

import json
from pathlib import Path

from tools.bot_ml.build_validation_provisioning import (
    SPELL_ITEM_ENCHANTMENT_FMT,
    apply_gear_profiles,
    load_gear_profiles,
)
from tools.bot_ml.generate_bot_admission_identities import (
    build_identity_catalog,
    canonical_gear_manifest,
    canonical_sha256,
    load_gear_profiles as load_admission_gear_profiles,
)
from tools.bot_ml.permanent_enchant_overlays import (
    DEFAULT_OVERLAYS,
    apply_permanent_enchant_overlays,
)
from tools.bot_ml.phase8_calibration_adapter import expected_gear_manifest
from tools.bot_ml.wowsims_gear_binding import load_wdbc


ROOT = Path(__file__).resolve().parents[1]
GEAR = ROOT / "dataset/validation_gear_profiles/profiles.json"
WOWSIMS = ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json"
DBC = ROOT / "data/dbc/enUS/SpellItemEnchantment.dbc"
EXPECTED = {
    0: 4208,
    2: 4198,
    4: 4103,
    6: 4127,
    7: 4062,
    8: 4191,
    9: 4106,
    14: 4100,
}


def _by_slot(rows: list[dict]) -> dict[int, dict]:
    return {int(row["slot"]): row for row in rows}


def test_overlay_is_pinned_and_excludes_the_dk_runeforge() -> None:
    document = json.loads(DEFAULT_OVERLAYS.read_text(encoding="utf-8"))
    authority = document["authority"]
    assert authority["applicability"] == "pinned_wowsims_preset_exact"
    assert authority["scope"] == "permanent_enchant_applicability_only"
    assert len(authority["source_sha256"]) == 64
    profile = document["profiles"]["blood_death_knight"]
    assert {int(slot): int(value) for slot, value in profile["permanent_enchants_by_slot"].items()} == EXPECTED
    assert profile["excluded_source_enchants"] == [{
        "slot": 15,
        "enchant_id": 3368,
        "kind": "dk_runeforge",
        "reason": "Runeforge presence is a separate native observation and is not created by this permanent-enchant overlay.",
    }]


def test_overlay_preserves_blood_identity_and_is_idempotent() -> None:
    original = json.loads(GEAR.read_text(encoding="utf-8"))["profiles"]["blood_death_knight"]["equipment"]
    merged = load_gear_profiles(GEAR, profile_ids={"blood_death_knight", "fire_mage"})
    blood = _by_slot(merged["blood_death_knight"]["equipment"])
    before = _by_slot(original)
    assert set(blood) == set(before)
    for slot, row in before.items():
        for field in ("item_id", "gem_item_ids", "gem_enchant_ids", "reforge_id", "temp_enchant_id", "temp_enchant_duration_ms"):
            assert blood[slot].get(field) == row.get(field)
        fields = [int(value) for value in blood[slot]["enchantments"].split()]
        assert len(fields) == 45
        if slot in EXPECTED:
            assert blood[slot]["enchant_id"] == EXPECTED[slot]
            assert fields[0] == EXPECTED[slot]
        else:
            assert blood[slot]["enchant_id"] == row["enchant_id"] == 0
            assert fields[0] == 0
    assert blood[15]["enchant_id"] == 0
    assert apply_permanent_enchant_overlays(merged)["blood_death_knight"] == merged["blood_death_knight"]


def test_overlay_only_changes_blood_in_provisioning_and_admission() -> None:
    profiles = load_gear_profiles(GEAR, profile_ids={"blood_death_knight", "fire_mage"})
    config = {
        "default_skills": [],
        "scenarios": [{
            "id": "overlay_test",
            "bots": [{
                "name": "Blood",
                "class_spec": "blood_death_knight",
                "role": "tank",
                "class": 6,
                "gear_profile": "blood_death_knight",
                "gear_profile_id": "blood_death_knight",
            }, {
                "name": "Fire",
                "class_spec": "fire_mage",
                "role": "dps",
                "class": 8,
                "gear_profile": "fire_mage",
                "gear_profile_id": "fire_mage",
            }],
        }],
    }
    resolved = apply_gear_profiles(config, profiles)["scenarios"][0]["bots"]
    blood = resolved[0]
    fire = resolved[1]
    assert _by_slot(blood["equipment"])[0]["enchant_id"] == EXPECTED[0]
    assert _by_slot(blood["equipment"])[15]["enchant_id"] == 0
    assert "permanent_enchant_overlay" not in profiles["fire_mage"]
    admission_profiles = load_admission_gear_profiles(GEAR, WOWSIMS)
    assert canonical_gear_manifest(
        admission_profiles["blood_death_knight"]["equipment"], label="admission"
    ) == canonical_gear_manifest(blood["equipment"], label="provisioning")
    assert _by_slot(expected_gear_manifest("blood_death_knight"))[14]["enchant_id"] == EXPECTED[14]


def test_pinned_enchants_exist_in_the_native_dbc() -> None:
    enchant_ids = {
        int(row["values"][0])
        for row in load_wdbc(DBC, SPELL_ITEM_ENCHANTMENT_FMT)
    }
    assert set(EXPECTED.values()) <= enchant_ids


def test_generated_identity_uses_the_enchanted_blood_manifest() -> None:
    catalog = build_identity_catalog()
    identity = next(row for row in catalog["identities"] if row["class_spec"] == "blood_death_knight")
    expected = expected_gear_manifest("blood_death_knight")
    assert identity["gear_manifest_sha256"]
    assert identity["gear_manifest_sha256"] == canonical_sha256(expected)
