from __future__ import annotations

import json
from pathlib import Path

from tools.bot_ml.build_validation_provisioning import (
    NATIVE_SELF_SETUP_SPELL_IDS,
    bot_known_spell_ids,
    load_config_with_bwd_diagnostic_shards,
)


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrPersistentSetup.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
CONTRACT = ROOT / "src/server/game/Bots/BotPersistentSelfBuffContract.h"
SELF_AURAS = ROOT / "src/server/game/Bots/BotCalibrationSelfProvidedAuras.h"
TARGETS = ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
ACTION_PROFILES = ROOT / "experiments/configs/cata_434_action_profiles.json"


MOVED_METHODS = (
    "IsNativePoisonSetupReady",
    "TryEnsurePersistentCombatSetup",
)


def test_persistent_setup_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrPersistentSetup.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_persistent_setup_preserves_native_pet_and_presence_contracts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "OrdinaryPersistentPetMatches",
        "persistent_native_pet_setup_ready",
        "persistent_preexisting_affliction_pet_observed",
        "RequiredPresenceSetupSpellId",
        "PresenceSetupNativeCastSubmittedAtMs",
        "persistent_setup_unholy_master_of_ghouls_missing",
        "persistent_setup_spell_missing",
    ):
        assert marker in module


def test_druid_self_setup_is_native_and_provisioned_as_learned_parent() -> None:
    module = MODULE.read_text(encoding="utf-8")
    contract = CONTRACT.read_text(encoding="utf-8")
    self_auras = SELF_AURAS.read_text(encoding="utf-8")
    targets = json.loads(TARGETS.read_text(encoding="utf-8"))
    actions = json.loads(ACTION_PROFILES.read_text(encoding="utf-8"))
    druid_specs = {
        "balance_druid", "feral_druid_dps", "feral_druid_tank", "restoration_druid",
    }

    assert '{ CLASS_DRUID, nullptr, nullptr, 1126, 1126, 79061, "mark_of_the_wild" }' in contract
    assert "std::array<uint32, 13> PlayerAuraIds" in self_auras
    assert "1126, 79061" in self_auras
    assert NATIVE_SELF_SETUP_SPELL_IDS == {
        "feral_druid_tank": (5487, 1126, 87505),
        "feral_druid_dps": (768, 20484, 1126, 87505),
        "balance_druid": (1126, 87505),
        "restoration_druid": (1126, 87505),
    }
    for spec in druid_specs:
        target = next(row for row in targets["targets"] if row["spec_target_id"] == spec)
        assert 1126 not in target["action_profile_spell_ids"]
        assert 87505 not in actions["action_profile_spells_by_spec"][spec]
    config = load_config_with_bwd_diagnostic_shards(
        ROOT / "experiments/configs/validation_provisioning_cata_001.json",
        ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json",
    )
    for scenario in config["scenarios"]:
        for bot in scenario["bots"]:
            spec = bot.get("class_spec")
            if spec not in druid_specs:
                continue
            assert set(NATIVE_SELF_SETUP_SPELL_IDS[spec]) <= set(bot_known_spell_ids(bot))
            assert 86530 not in bot_known_spell_ids(bot)
    assert "BotPersistentSelfBuffContract::Buffs" in module
    assert "bot->HasSpell(buff.SpellId)" in module
    assert "executor.ExecuteCombat(bot, bot, action)" in module


def test_persistent_setup_preserves_weapon_imbue_and_poison_contracts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "RoguePoisonSetupRequired",
        "deadly_poison_mainhand",
        "instant_poison_offhand",
        "world.setup.weapon_poison",
        "world.setup.weapon_imbue",
        "SPELL_EFFECT_ENCHANT_ITEM_TEMPORARY",
        "NativeUseFinishedSuccessfully",
        "PoisonRefreshThresholdMs",
    ):
        assert marker in module
