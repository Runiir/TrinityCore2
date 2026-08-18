from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationProfile.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "IsValidationProfileName",
    "PrepareValidationProfile",
    "PrepareCurrentValidationProfile",
    "ApplyValidationProvisioningSql",
    "ResetValidationBotPool",
)


def test_validation_profile_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationProfile.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_validation_profile_methods_and_sql_helpers_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text
    for helper in (
        "ReadSmallTextFile",
        "SplitSqlStatements",
        "ExecuteSqlFile",
        "BlackwingDescentMapId",
    ):
        assert f"{helper}" not in text


def test_validation_profile_keeps_exact_pool_and_provisioning_contract():
    text = MODULE.read_text()
    for marker in (
        "not_executable_validation_profile",
        "invalid_exact_party_contract",
        "validation_pool_exact_size_mismatch",
        "validation_pool_exact_raid_composition_mismatch",
        "validation_pool_exact_party_composition_mismatch",
        "exact_party_pool_mismatch",
        "validation_pool_guid_leased",
        "ValidationProvisionOnPrepare",
        "validation_accounts",
        "validation_characters",
        "character_instance",
        "group_member",
        "pet_spell_cooldown",
    ):
        assert marker in text
