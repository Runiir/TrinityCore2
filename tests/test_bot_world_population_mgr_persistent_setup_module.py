from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrPersistentSetup.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


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
