from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrGearIdentity.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "ObserveEquippedGearIdentity",
    "EquippedGearManifestsEqual",
)


def test_gear_identity_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrGearIdentity.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_gear_identity_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_gear_identity_keeps_canonical_manifest_contract():
    text = MODULE.read_text()
    for marker in (
        "EQUIPMENT_SLOT_START",
        "PERM_ENCHANTMENT_SLOT",
        "REFORGE_ENCHANTMENT_SLOT",
        "MAX_GEM_SOCKETS",
        "Src_itemID",
        "canonical_gear_manifest",
        "enchant_id",
        "gem_item_ids",
        "item_id",
        "reforge_id",
        "slot",
        "manifest.size() >= 16",
    ):
        assert marker in text
