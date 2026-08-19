from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/HighPriestessAzil/"
    "HighPriestessAzilHunterThreatTransfer.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
CONTEXT_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)


def test_azil_hunter_threat_transfer_is_registered_and_bounded():
    world = WORLD.read_text(encoding="utf-8")
    mgr_header = MGR_HEADER.read_text(encoding="utf-8")
    module_header = MODULE_HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    context_header = CONTEXT_HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert len(mgr_header.splitlines()) <= 990
    assert len(module_header.splitlines()) <= 1000
    assert len(module.splitlines()) <= 1000
    assert "HighPriestessAzilHunterThreatTransfer.cpp" in cmake
    assert "HunterThreatTransferRequest" in module_header
    assert "HunterThreatTransferResult" in module_header
    assert "HunterMisdirectionActive" in module_header
    assert "TryHunterThreatTransfer" in module_header
    assert "static HunterThreatTransferResult Run(" in context_header
    assert "HighPriestessAzilHunterThreatTransfer.h" in world


def test_azil_hunter_threat_transfer_owns_the_exact_ordered_window():
    world = WORLD.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    dispatch = world.index("TryHunterThreatTransfer(")
    strict_area_resolver = world.index(
        "// The strict area-only resolver intentionally filters defensives",
        dispatch,
    )
    manager_gap = world[dispatch:strict_area_resolver]
    assert "hunterAoeTransferReady" not in manager_gap
    assert "legalTransferTarget" not in manager_gap
    assert "misdirection_aoe_wait_for_focus" not in manager_gap
    assert "misdirection_single_target_transfer" not in manager_gap
    for marker in (
        "hunterAoeTransferReady = true",
        "HunterAoeMinRangeSafety = 3.0f",
        "hunterAoeResourceReady",
        "Readiness",
        "HunterMisdirectionActive",
        "readiness_for_misdirection_swarm_pickup",
        "misdirection_to_tank",
        "legalTransferTarget",
        "misdirection_aoe_wait_for_focus",
        "misdirection_aoe_transfer",
        "misdirection_single_target_transfer",
    ):
        assert marker in module


def test_azil_hunter_threat_transfer_preserves_native_legality_and_ties():
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")

    assert "AddWaveDiscoveryResult const* Discovery" in MODULE_HEADER.read_text(
        encoding="utf-8"
    )
    assert "AddWaveDensityResult const* Density" in MODULE_HEADER.read_text(
        encoding="utf-8"
    )
    assert "bool Handled = false;" in MODULE_HEADER.read_text(encoding="utf-8")
    assert "bool hunterMisdirectionActive =" in world
    assert "hunterThreatTransfer.HunterMisdirectionActive" in world
    assert module.index("hunterAoeResourceReady") < module.index(
        "hunterAoeTransferReady = hunterAoeResourceReady"
    )
    assert module.index("distance < legalTransferDistance") < module.index(
        "guid < legalTransferGuid"
    )
    for marker in (
        "GetSpellMinRangeForTarget",
        "IsWithinLOSInMap",
        "GetSpellHistory()->IsReady",
        "TryCastFriendlySpell(bot, bot, 23989)",
        "TryCastFriendlySpell(bot, densityTank, 34477)",
        "MoveBotToProfileRange(state, bot, add, &rangeAction)",
        "BotActionExecutor executor",
        "RecordCombatAttempt",
        "state.WasInCombat = true",
        "sharedFocusValid = false",
    ):
        assert marker in module
    for forbidden in ("SetVictim", "AddThreat", "SetThreat", "NearTeleportTo"):
        assert forbidden not in module
