import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
SOURCE = BOT_DIR / "BotWorldPopulationMgr.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"

MODULES = {
    "NativeHelpers": (
        "BotWorldPopulationMgrNativeHelpers",
        (
            "IsNativeCombatResSpell",
            "IsNativeCombatObserved",
            "SubmitNativeQuestAccept",
            "SubmitNativeQuestReward",
            "ReadLastInsertId",
            "Distance2d",
            "UsesRangedAoeCalibrationLane",
            "UnitHealthPct",
            "HasPowerForSpell",
            "ControlledDispelAuraForHealer",
            "CombatOwnerPlayer",
            "CancelRemovableShapeshifts",
            "MaintainedProfileAuraBlocksRefresh",
        ),
    ),
    "PolicyHelpers": (
        "BotWorldPopulationMgrPolicyHelpers",
        (
            "LowerCopy",
            "BoundedResultLabel",
            "ContainsInsensitive",
            "WorldPolicySource",
            "WorldPolicyVersion",
            "IsSimpleOpenWorldQuestMobAssistTarget",
        ),
    ),
    "SpellSemantics": (
        "BotWorldPopulationMgrSpellSemantics",
        (
            "NowMs",
            "SpellLooksLikeHeal",
            "SpellLooksDangerous",
            "SpellLooksLikeSummonOrAdds",
            "SpellLooksLikeGroundDanger",
            "SpellLooksRaidWide",
            "SpellLooksTankSpike",
            "SemanticMechanicKey",
            "SemanticMechanicFamily",
            "EventLooksSuccessful",
            "EventLooksFailure",
            "BuildSpellTagJson",
            "SpellHasHostileMultiTargetSemantics",
            "HasNearbyProtectedEncounterTarget",
        ),
    ),
}


def test_helper_modules_are_bounded_registered_and_namespaced():
    cmake = CMAKE.read_text()
    for stem, (namespace, helpers) in MODULES.items():
        module = BOT_DIR / f"BotWorldPopulationMgr{stem}.cpp"
        header = BOT_DIR / f"BotWorldPopulationMgr{stem}.h"
        module_text = module.read_text()
        header_text = header.read_text()
        assert len(module_text.splitlines()) <= 1000
        assert len(header_text.splitlines()) <= 1000
        assert f"BotWorldPopulationMgr{stem}.cpp" in cmake
        assert f"namespace {namespace}" in module_text
        for helper in helpers:
            assert helper in header_text
            assert re.search(rf"\b{re.escape(helper)}\s*\(", module_text)


def test_helper_definitions_are_not_left_in_the_monolith():
    source = SOURCE.read_text()
    for _, (_, helpers) in MODULES.items():
        for helper in helpers:
            assert not re.search(
                rf"(?:bool|float|uint32|uint64|char const\*|std::string|Player\*)\s+{re.escape(helper)}\s*\(",
                source,
            )


def test_helper_modules_preserve_their_behavioral_boundaries():
    native = (BOT_DIR / "BotWorldPopulationMgrNativeHelpers.cpp").read_text()
    policy = (BOT_DIR / "BotWorldPopulationMgrPolicyHelpers.cpp").read_text()
    spell = (BOT_DIR / "BotWorldPopulationMgrSpellSemantics.cpp").read_text()
    for marker in ("CMSG_QUEST_GIVER_ACCEPT_QUEST", "LAST_INSERT_ID", "SPELL_AURA_MOD_SHAPESHIFT", "GetCharmerOrOwner"):
        assert marker in native
    for marker in ("BotPolicySource::AssistModel", "BotPolicySource::ControlModel", "IsDungeonBoss", "IsSimpleOpenWorldQuestMobAssistTarget"):
        assert marker in policy
    for marker in ("SPELL_EFFECT_PERSISTENT_AREA_AURA", "SemanticMechanicFamily", "SpellHasHostileMultiTargetSemantics", "HasNearbyProtectedEncounterTarget"):
        assert marker in spell
