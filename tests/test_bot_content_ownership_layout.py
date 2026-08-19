from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
CONTENT = BOTS / "Content"

CONTENT_KINDS = frozenset({"Raids", "Dungeons"})
INSTANCE_SECTIONS = frozenset({"Instance", "Trash", "Encounters"})
SOURCE_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".h",
        ".hh",
        ".hpp",
        ".hxx",
        ".inc",
        ".ipp",
    }
)

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

def test_content_contract_covers_raids_and_dungeons():
    contract = (CONTENT / "README.md").read_text(encoding="utf-8")

    for fragment in (
        "Content/Raids/<Raid>/Instance/<module>",
        "Content/Raids/<Raid>/Trash/<WingOrPack>/<module>",
        "Content/Raids/<Raid>/Encounters/<Boss>/<module>",
        "Content/Dungeons/<Dungeon>/Instance/<module>",
        "Content/Dungeons/<Dungeon>/Trash/<WingOrPack>/<module>",
        "Content/Dungeons/<Dungeon>/Encounters/<Boss>/<module>",
    ):
        assert fragment in contract

    assert "Do not create placeholder modules" in contract


def _is_source_or_header(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES


def _find_layout_violations(content_root: Path) -> list[str]:
    """Return source/header paths that do not name a concrete owner."""

    violations = []
    for kind_name in sorted(CONTENT_KINDS):
        kind_root = content_root / kind_name
        if not kind_root.is_dir():
            continue

        for instance_root in sorted(kind_root.iterdir(), key=lambda path: path.name):
            if instance_root.is_file():
                if _is_source_or_header(instance_root):
                    violations.append(
                        f"{instance_root}: source/header directly under {kind_name}"
                    )
                continue

            # Shared code may be reused by several instances, but it must live
            # at the category level rather than in an instance's namespace.
            if instance_root.name.casefold() == "shared":
                continue

            for child in sorted(instance_root.iterdir(), key=lambda path: path.name):
                if child.is_file():
                    if _is_source_or_header(child):
                        violations.append(
                            f"{child}: source/header directly under instance root"
                        )
                    continue
                if child.name not in INSTANCE_SECTIONS:
                    violations.append(f"{child}: unknown instance content section")

            # A nested Shared directory would make ownership ambiguous even
            # when it is below the otherwise valid Instance section.
            violations.extend(
                f"{path}: shared content inside instance-specific folder"
                for path in instance_root.rglob("*")
                if path.is_dir() and path.name.casefold() == "shared"
            )

            for section_name in ("Trash", "Encounters"):
                section_root = instance_root / section_name
                if not section_root.is_dir():
                    continue
                for child in sorted(section_root.iterdir(), key=lambda path: path.name):
                    if _is_source_or_header(child):
                        violations.append(
                            f"{child}: source/header directly under {section_name}"
                        )

    return sorted(violations)


def test_bot_content_layout_has_explicit_owners_and_bounded_size():
    violations = _find_layout_violations(CONTENT)
    assert violations == []

    oversized = [
        path
        for path in CONTENT.rglob("*")
        if _is_source_or_header(path)
        and len(path.read_text(encoding="utf-8").splitlines()) > 1000
    ]
    assert oversized == []


def test_current_bot_content_remains_under_named_instance_sections():
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
