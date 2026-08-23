from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrAffliction.cpp"
CALIBRATION_BOT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationBot.cpp"
CALIBRATION_ROWS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationRows.cpp"
PERSISTENT_SETUP = ROOT / "src/server/game/Bots/BotWorldPopulationMgrPersistentSetup.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


FIELDS = (
    "sample_count",
    "shadow_mastery_active_samples",
    "potent_afflictions_active_samples",
    "haunt_debuff_active_samples",
    "shadow_embrace_active_samples",
    "maximum_shadow_embrace_stacks",
    "haunt_affects_corruption_samples",
    "shadow_embrace_affects_corruption_samples",
    "maximum_haunt_damage_modifier_pct",
    "maximum_shadow_embrace_damage_modifier_pct",
    "minimum_corruption_taken_multiplier_ppm",
    "maximum_corruption_taken_multiplier_ppm",
)


def test_affliction_module_is_narrow_and_registered() -> None:
    assert len(MODULE.read_text(encoding="utf-8").splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrAffliction.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    header = HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    for name in (
        "ConfigureAfflictionPetRequirements",
        "ObserveAfflictionCalibrationModifiers",
        "AppendAfflictionCalibrationJson",
    ):
        assert header.count(name) == 1
        assert module.count(f"BotWorldPopulationMgr::{name}") == 1


def test_affliction_pet_setup_keeps_native_profile_authority() -> None:
    source = WORLD.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    persistent_setup = PERSISTENT_SETUP.read_text(encoding="utf-8")
    assert "ConfigureAfflictionPetRequirements(requiredPet" in source or "ConfigureAfflictionPetRequirements(requiredPet" in persistent_setup
    assert "requiredPet.RequiredSummonSpellId = 691" in module
    assert "requiredPet.RequiredCreatedBySpellId = 691" in module
    assert "requiredPet.RequiredEntry = ENTRY_FELHUNTER" in module
    assert "requiredPet.RequiredFamilyId = CREATURE_FAMILY_FELHUNTER" in module
    assert "requiredPet.RequiredPetType = uint32(SUMMON_PET)" in module
    assert "requiredPet.RequiredPowerType = uint32(POWER_MANA)" in module
    assert 'requiredPetName = "summon_felhunter"' in module
    assert "sObjectMgr->GetCreatureTemplate" not in module


def test_affliction_calibration_json_schema_is_byte_ordered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    calibration_bot = CALIBRATION_BOT.read_text(encoding="utf-8")
    calibration_rows = CALIBRATION_ROWS.read_text(encoding="utf-8")
    assert "AppendAfflictionCalibrationJson(metrics)" in calibration_rows
    assert "affliction_modifier_observation" in module
    positions = [module.index(f'\\"{field}\\"') for field in FIELDS]
    assert positions == sorted(positions)
    assert module.count("Affliction") >= len(FIELDS)
    assert "ObserveAfflictionCalibrationModifiers(metrics, bot, fixtureTarget)" in calibration_bot


def test_affliction_inline_implementation_is_not_duplicated() -> None:
    source = WORLD.read_text(encoding="utf-8")
    assert not re.search(
        r"Affliction(?:ModifierObservation|ShadowMastery|PotentAfflictions|HauntDebuff|ShadowEmbrace)ActiveTicks",
        source,
    )


def test_affliction_damage_stage_receipt_covers_requested_native_events() -> None:
    metrics = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationMetrics.h").read_text(
        encoding="utf-8"
    )
    module = MODULE.read_text(encoding="utf-8")
    notifications = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatNotifications.cpp"
    ).read_text(encoding="utf-8")

    assert "AfflictionDamageStageObservation" in metrics
    assert "AfflictionDamageStageBySpell" in metrics
    assert "ObserveAfflictionDamageStage(calibration->second, owner, victim" in notifications
    for spell_id in (172, 30108, 48181, 47897, 47960, 1120):
        assert f"case {spell_id}:" in module
    for field in (
        "owner_damage_pct_done_ppm_sum",
        "target_taken_multiplier_ppm_sum",
        "shadow_mastery_affecting_events",
        "potent_afflictions_affecting_events",
        "haunt_affecting_events",
        "shadow_embrace_affecting_events",
    ):
        assert f'\\"{field}\\"' in module
    assert "SpellDamagePctDone(victim, spellInfo, effectType)" in module
    assert "SpellDamageBonusTaken(owner, spellInfo, 1000000, effectType)" in module
