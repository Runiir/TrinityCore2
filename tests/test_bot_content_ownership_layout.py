from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
CONTENT = BOTS / "Content"

AZIL_FILES = {
    "HighPriestessAzilAddWaveDensity.cpp",
    "HighPriestessAzilAddWaveDensity.h",
    "HighPriestessAzilAddWaveDiscovery.cpp",
    "HighPriestessAzilAddWaveDiscovery.h",
    "HighPriestessAzilAddWaveOpeningActions.cpp",
    "HighPriestessAzilAddWaveOpeningActions.h",
    "HighPriestessAzilAddWaveTankPreparation.cpp",
    "HighPriestessAzilAddWaveTankPreparation.h",
    "HighPriestessAzilDensityCombatResolution.cpp",
    "HighPriestessAzilDensityCombatResolution.h",
    "HighPriestessAzilFeralActiveSwarmMovement.cpp",
    "HighPriestessAzilFeralActiveSwarmMovement.h",
    "HighPriestessAzilFeralHandoffState.cpp",
    "HighPriestessAzilFeralHandoffState.h",
    "HighPriestessAzilFeralLocalRetention.cpp",
    "HighPriestessAzilFeralLocalRetention.h",
    "HighPriestessAzilFeralRemoteActions.cpp",
    "HighPriestessAzilFeralRemoteActions.h",
    "HighPriestessAzilHealerAddWavePreposition.cpp",
    "HighPriestessAzilHealerAddWavePreposition.h",
    "HighPriestessAzilHighDensityPositioning.cpp",
    "HighPriestessAzilHighDensityPositioning.h",
    "HighPriestessAzilHunterThreatTransfer.cpp",
    "HighPriestessAzilHunterThreatTransfer.h",
    "HighPriestessAzilPassiveSwarmStaging.cpp",
    "HighPriestessAzilPassiveSwarmStaging.h",
    "HighPriestessAzilSwarmThreatSafety.cpp",
    "HighPriestessAzilSwarmThreatSafety.h",
    "HighPriestessAzilTankThreatRecovery.cpp",
    "HighPriestessAzilTankThreatRecovery.h",
}

ENCOUNTER_FILES = {
    "Magmaw/BotAdaptiveMagmawStrategy.h",
    "Omnotron/BotAdaptiveOmnotronStrategy.h",
    "Maloriak/BotAdaptiveMaloriakStrategy.h",
    "Atramedes/BotAdaptiveAtramedesStrategy.h",
    "Chimaeron/BotAdaptiveChimaeronStrategy.h",
    "Nefarian/BotAdaptiveNefarianStrategy.h",
}

DRUDGE_FILES = {
    "BotAdaptiveDrudgeStrategy.h",
    "BotRaidDrudgeGeometryState.h",
    "BotRaidDrudgeNativeRushState.h",
    "BotRaidDrudgeThreatSeedState.h",
    "BotWorldPopulationMgrValidationRouteDrudge.h",
    "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp",
    "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp",
    "BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp",
}

OLD_ROOT_FILES = {
    "BotAdaptiveAtramedesStrategy.h",
    "BotAdaptiveChimaeronStrategy.h",
    "BotAdaptiveDrudgeStrategy.h",
    "BotAdaptiveMagmawStrategy.h",
    "BotAdaptiveMaloriakStrategy.h",
    "BotAdaptiveNefarianStrategy.h",
    "BotAdaptiveOmnotronStrategy.h",
    "BotAdaptiveRaidTrashStrategy.h",
    "BotRaidDrudgeGeometryState.h",
    "BotRaidDrudgeNativeRushState.h",
    "BotRaidDrudgeThreatSeedState.h",
    "BotWorldPopulationMgrValidationRouteDrudge.h",
    "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp",
    "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp",
    "BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp",
}


def test_bot_content_files_have_explicit_ownership_and_bounded_size():
    azil = CONTENT / "Dungeons/Stonecore/Encounters/HighPriestessAzil"
    encounters = CONTENT / "Raids/BlackwingDescent/Encounters"
    drudge = CONTENT / "Raids/BlackwingDescent/Trash/Drudge"
    shared_trash = CONTENT / "Raids/Shared/Trash"

    assert {path.name for path in azil.iterdir()} == AZIL_FILES
    assert {
        str(path.relative_to(encounters))
        for path in encounters.glob("*/BotAdaptive*Strategy.h")
    } == ENCOUNTER_FILES
    assert {path.name for path in drudge.iterdir()} == DRUDGE_FILES
    assert (shared_trash / "BotAdaptiveRaidTrashStrategy.h").is_file()

    assert not (CONTENT / "Dungeons/Stonecore/HighPriestessAzil").exists()
    assert not any((BOTS / name).exists() for name in OLD_ROOT_FILES)

    oversized = [
        path
        for path in CONTENT.rglob("*")
        if path.is_file()
        and len(path.read_text(encoding="utf-8").splitlines()) > 1000
    ]
    assert oversized == []
