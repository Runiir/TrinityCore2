from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
EXECUTOR = ROOT / "src/server/game/Bots/BotActionExecutor.cpp"
BOT_MGR = ROOT / "src/server/game/Bots/BotMgr.cpp"


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : index]
    raise AssertionError(f"unterminated function: {signature}")


def code_only(body: str) -> str:
    body = re.sub(r"//.*", "", body)
    return re.sub(r"/\*.*?\*/", "", body, flags=re.S)


FORBIDDEN_LIVE_MUTATIONS = (
    "SetFullHealth(",
    "SetFullPower(",
    "SetHealth(",
    "SetPower(",
    "ResurrectPlayer(",
    "TeleportTo(",
    "NearTeleportTo(",
    "CombatStop(",
    "CombatStopWithPets(",
    "SetInCombatWith(",
    "AddThreat(",
    "ClearAllThreat(",
    "SetReactState(",
    "SetEnchantment(",
    "Unit::Kill(",
    "DealDamage(",
    "Respawn(",
    "SpawnGroupSpawn(",
    "SummonCreature(",
    "SetData(",
    "DoAction(",
    "TRIGGERED_IGNORE_POWER_COST",
    "->AddQuest(",
    "->CompleteQuest(",
    "->RewardQuest(",
    "ModifyMoney(",
    "StoreLootItem(",
    "DurabilityRepairAll(",
)


def test_live_autonomy_functions_do_not_mutate_native_game_state() -> None:
    world = WORLD.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")
    live_functions = (
        function_body(world, "BotWorldPopulationMgr::DeathRecoveryResult BotWorldPopulationMgr::RecoverDeadBot"),
        function_body(world, "bool BotWorldPopulationMgr::TryNativeCorpseRun"),
        function_body(world, "BotWorldPopulationMgr::QuestActionResult BotWorldPopulationMgr::TryQuesting"),
        function_body(world, "bool BotWorldPopulationMgr::TryValidationRouteObjective"),
        function_body(world, "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup"),
        function_body(world, "bool BotWorldPopulationMgr::TryEnsureCombatTotems"),
        function_body(world, "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState*"),
        function_body(executor, "BotActionResult BotActionExecutor::ExecuteCombat"),
        function_body(executor, "BotActionExecutor::LootResult BotActionExecutor::AutoLoot"),
        function_body(executor, "BotEconomyActionResult BotActionExecutor::VendorTrash"),
        function_body(executor, "BotEconomyActionResult BotActionExecutor::Repair"),
    )

    for body in map(code_only, live_functions):
        for forbidden in FORBIDDEN_LIVE_MUTATIONS:
            assert forbidden not in body, forbidden


def test_native_player_handlers_are_the_only_progression_boundaries() -> None:
    world = WORLD.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")

    corpse_run = function_body(world, "bool BotWorldPopulationMgr::TryNativeCorpseRun")
    assert "HandleRepopRequestOpcode" in corpse_run
    assert "HandleReclaimCorpseOpcode" in corpse_run

    quest_accept = function_body(world, "bool SubmitNativeQuestAccept")
    quest_reward = function_body(world, "bool SubmitNativeQuestReward")
    assert "HandleQuestgiverAcceptQuestOpcode" in quest_accept
    assert "HandleQuestgiverChooseRewardOpcode" in quest_reward

    loot = function_body(executor, "BotActionExecutor::LootResult BotActionExecutor::AutoLoot")
    for handler in (
        "HandleLootOpcode",
        "HandleLootMoneyOpcode",
        "HandleAutostoreLootItemOpcode",
        "HandleLootReleaseOpcode",
    ):
        assert handler in loot

    combat = function_body(executor, "BotActionResult BotActionExecutor::ExecuteCombat")
    assert "HandlePetActionHelper" in combat
    assert "TRIGGERED_IGNORE_POWER_COST" not in combat


def test_login_does_not_promote_stabled_pets_or_restore_resources() -> None:
    source = BOT_MGR.read_text(encoding="utf-8")
    login = function_body(source, "Player* BotMgr::LoadCharacterAsBotSession")
    for forbidden in (
        "UPDATE character_pet",
        "SetFullHealth(",
        "SetFullPower(",
        "SetPower(",
        "SetHealth(",
    ):
        assert forbidden not in login
    assert "provisioning must assign a valid active pet" in login


def test_certifying_routes_only_load_persisted_character_placement() -> None:
    source = WORLD.read_text(encoding="utf-8")
    placement = function_body(
        source, "bool BotWorldPopulationMgr::ResolveSpawnPlacement"
    )
    validation_guard = placement.index("if (Cohort().Config.ValidationRouteEnable)")
    saved_return = placement.index("ResolveSavedSpawnPlacement", validation_guard)
    generic_modes = placement.index("std::string mode", saved_return)
    assert validation_guard < saved_return < generic_modes
    assert "UseSavedPosition" in placement[validation_guard:generic_modes]


def test_fixture_mutations_remain_outside_live_update_paths() -> None:
    source = WORLD.read_text(encoding="utf-8")
    header = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(encoding="utf-8")
    calibration = function_body(source, "void BotWorldPopulationMgr::UpdateCalibrationControlledDamage")
    calibration_start = function_body(source, "std::string BotWorldPopulationMgr::StartCombatCalibration(std::string const& mode")
    replay = function_body(source, "BotWorldPopulationMgr::ReplayExecutionResult BotWorldPopulationMgr::ExecuteReplayRecord")
    update_bot = function_body(source, "void BotWorldPopulationMgr::UpdateBot")

    # Synthetic mutations are explicit, isolated, and forever non-certifying.
    assert "SetHealth(" in calibration
    assert "ResurrectPlayer(" in replay
    assert "CalibrationFixture" in header
    assert "ReplayFixture" in header
    assert "NonCertifyingAssistance" in header
    assert "!Party().Bots.empty() || Cohort().Config.TargetPopulation != 0" in calibration_start
    assert "BotWorldRuntimeMode::CalibrationFixture" in calibration_start
    assert "Cohort().NonCertifyingAssistance = true" in calibration_start
    assert "BotWorldRuntimeMode::ReplayFixture" in replay
    assert "Cohort().NonCertifyingAssistance = true" in replay
    assert replay.index("BotWorldRuntimeMode::ReplayFixture") < replay.index("ResurrectPlayer(")
    assert "UpdateCalibrationControlledDamage" not in update_bot
    assert "ExecuteReplayRecord" not in update_bot
