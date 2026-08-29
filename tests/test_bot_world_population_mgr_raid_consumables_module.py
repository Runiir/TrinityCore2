from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
CORE = BOT_DIR / "BotWorldPopulationMgrRaidConsumables.cpp"
JSON = BOT_DIR / "BotWorldPopulationMgrRaidConsumablesJson.cpp"
INVENTORY = BOT_DIR / "BotWorldPopulationMgrConsumables.cpp"
CONTRACT = BOT_DIR / "BotWorldPopulationMgrRaidConsumables.h"
CONTRACT_IMPL = BOT_DIR / "BotWorldPopulationMgrRaidConsumableContracts.cpp"
RUNTIME = BOT_DIR / "BotWorldPopulationMgrRaidRuntime.cpp"
SEMANTIC = BOT_DIR / "BotWorldPopulationMgrSemantic.cpp"
CALIBRATION = BOT_DIR / "BotWorldPopulationMgrCalibrationReference.cpp"
ROUTE = BOT_DIR / "BotWorldPopulationMgrValidationRouteTargetEngagement.cpp"
KERNEL = BOT_DIR / "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_raid_consumable_modules_are_registered_and_bounded() -> None:
    cmake = source(CMAKE)
    assert "BotWorldPopulationMgrConsumables.cpp" in cmake
    assert "BotWorldPopulationMgrRaidConsumables.cpp" in cmake
    assert "BotWorldPopulationMgrRaidConsumableContracts.cpp" in cmake
    assert "BotWorldPopulationMgrRaidConsumablesJson.cpp" in cmake
    for path in (CORE, JSON, INVENTORY, CONTRACT_IMPL):
        assert len(source(path).splitlines()) < 1000


def test_inventory_helper_reuses_exact_player_bag_item_contract() -> None:
    text = source(INVENTORY)
    assert "INVENTORY_SLOT_ITEM_START" in text
    assert "INVENTORY_SLOT_BAG_START" in text
    assert "effect.SpellID == int32(spellId)" in text
    assert "ITEM_SPELLTRIGGER_ON_USE" in text
    assert "item->GetCount()" in text


def test_raid_profiles_reuse_generated_dps_and_cover_exact_non_dps_roster() -> None:
    text = source(CORE) + source(CONTRACT) + source(CONTRACT_IMPL)
    assert "BotCalibrationFixtureContractGenerated::FindSpec" in text
    for class_spec in (
        "blood_death_knight",
        "protection_paladin",
        "holy_paladin",
        "discipline_priest",
        "restoration_shaman",
        "restoration_druid",
        "holy_priest",
        "feral_druid_tank",
    ):
        assert f'"{class_spec}"' in text
    for item_id in ("58086", "58087", "58088", "62669", "62670", "62671", "58091", "58145", "58146"):
        assert item_id in text


def test_raid_use_is_native_and_fail_closed_without_inventory_mutation() -> None:
    text = source(CORE)
    for marker in (
        "FindNativeConsumable",
        "CountNativeConsumable",
        "BotNativeAction::UseItem",
        "ExecuteNativeActionIntent",
        "raid_prepull_missing_",
        "raid_prepull_",
        "GetRemainingCooldown",
        "GetRemainingGlobalCooldown",
        "IsReady(spellInfo",
    ):
        assert marker in text
    for forbidden in (
        "AddAura(",
        "SetCount(",
        "DestroyItem(",
        "AddItem(",
        "ResetAllCooldowns(",
        "SetHealth(",
    ):
        assert forbidden not in text


def test_receipt_observes_item_finish_aura_and_cooldown_and_reserves_second_potion() -> None:
    text = source(CORE) + source(JSON)
    for marker in (
        "ReconcileRaidPrepullItemSpellFinished",
        "NativeUseFinishedSuccessfully",
        "NativeUseAwaitingAura",
        "AuraObservedAtMs",
        "CooldownObserved",
        "FinishedItemGuid",
        "PreUseItemCount",
        "PostUseItemCount",
        "availableCount < 2",
        "raid_prepull_missing_prepot_combat_potion_reserve",
        "CombatPotionReservedCount",
        "second_potion_reserved",
    ):
        assert marker in text


def test_exact_roster_health_gate_and_boss_pull_gate_are_wired() -> None:
    text = source(CORE)
    route = source(ROUTE)
    kernel = source(KERNEL)
    for marker in (
        "RosterByGuid",
        "RosterComplete",
        "RosterCompositionValid",
        "AliveAndHealed",
        "GetHealth() == memberBot->GetMaxHealth()",
        "raid_prepull_wait_alive_and_healed",
        "raid_prepull_ready_for_pull",
    ):
        assert marker in text
    assert "SubmitRaidPrepullConsumableCandidate(context);" in kernel
    assert "ApplyRaidPrepullBossPullGate" in route
    assert "raid_prepull_wait_for_consumables" in text
    assert 'roster->second.Role == "healer"' in text
    healer_gate = text.index('roster->second.Role == "healer"')
    candidate = text.index("BotActionArbitration::Candidate candidate;", healer_gate)
    assert "member->GetHealth() < member->GetMaxHealth()" in text[
        healer_gate:candidate
    ]


def test_short_prepot_waits_for_magmaw_formation_and_health_staging(
    tmp_path: Path,
) -> None:
    text = source(CORE)
    contract = source(CONTRACT)
    assert "prepotStageReady" in text
    assert '== "prepull_pull_owner_wait"' in contract
    assert "raid_prepull_wait_prepot_formation_ready" in text
    assert "RaidPrepotWindowYards" not in text
    assert "raid_prepull_wait_boss_prepot_window" not in text
    durable_setup = text.index("if (!allSetupReady)")
    prepot_gate = text.index("if (!prepotStageReady)")
    prepot_submit = text.index("auto submitPrepot")
    assert durable_setup < prepot_gate < prepot_submit

    replay = tmp_path / "prepot_stage_replay.cpp"
    replay.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrRaidConsumables.h"
#include <cassert>

int main()
{
    using BotWorldPopulationMgrRaidConsumables::PrepotStageReady;
    assert(PrepotStageReady(false, false, ""));
    assert(PrepotStageReady(true, false, ""));
    assert(!PrepotStageReady(true, true, "prepull_formation_staging"));
    assert(!PrepotStageReady(true, true, "prepull_health_recovery"));
    assert(PrepotStageReady(true, true, "prepull_pull_owner_wait"));
}
''',
        encoding="utf-8",
    )
    binary = tmp_path / "prepot_stage_replay"
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-I",
            str(ROOT / "src/server/game"),
            str(replay),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)


def test_calibration_and_completion_paths_share_inventory_scanner() -> None:
    assert "BotWorldPopulationMgrConsumables.h" in source(CALIBRATION)
    assert "BotWorldPopulationMgrConsumables.h" in source(SEMANTIC)
    assert "CountNativeConsumable" in source(CALIBRATION)
    assert "CountNativeConsumable" in source(SEMANTIC)
    assert "AppendRaidPrepullConsumablesJson(json);" in source(RUNTIME)
    assert "ReconcileRaidPrepullItemSpellFinished(caster" in source(SEMANTIC)
