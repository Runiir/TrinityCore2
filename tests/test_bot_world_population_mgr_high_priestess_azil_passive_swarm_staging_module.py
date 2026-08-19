from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/HighPriestessAzil/"
    "HighPriestessAzilPassiveSwarmStaging.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
CONTEXT_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)


def test_azil_passive_swarm_staging_is_registered_and_bounded():
    world = WORLD.read_text(encoding="utf-8")
    mgr_header = MGR_HEADER.read_text(encoding="utf-8")
    module_header = MODULE_HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    context_header = CONTEXT_HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert len(mgr_header.splitlines()) <= 990
    assert len(module_header.splitlines()) <= 1000
    assert len(module.splitlines()) <= 1000
    assert "HighPriestessAzilPassiveSwarmStaging.cpp" in cmake
    assert "PassiveSwarmStagingRequest" in module_header
    assert "AddWaveDiscoveryResult const* Discovery" in module_header
    assert "AddWaveDensityResult const* Density" in module_header
    assert "TryPassiveSwarmStaging" in module_header
    assert "static bool Run(PassiveSwarmStagingRequest const& request);" in (
        context_header
    )
    assert "HighPriestessAzilPassiveSwarmStaging.h" in world


def test_azil_passive_swarm_staging_owns_the_exact_ordered_window():
    world = WORLD.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    dispatch = world.index("TryPassiveSwarmStaging(")
    continuation = world.index(
        "// A moving swarm can select a different representative attacker every",
        dispatch,
    )
    manager_gap = world[dispatch:continuation]
    for marker in (
        "pendingSwarmActivation",
        "passiveSwarmClusterAnchor",
        "tankViewProvesLargePassiveSwarm",
        "largePassiveSwarmPartyStaged",
        "tank_preposition_for_pending_swarm_pickup",
        "feral_prepare_bear_form_before_passive_swarm_activation",
        "tank_activate_passive_swarm",
        "hold_pending_swarm_area_threat_resources",
    ):
        assert marker in module
        assert marker not in manager_gap

    assert world.index("tank_swarm_defensive") < dispatch
    assert module.index("pendingSwarmActivation") < module.index(
        "passiveSwarmClusterAnchor"
    )
    assert module.index("tankViewProvesLargePassiveSwarm") < module.index(
        "largePassiveSwarmPartyStaged"
    )
    assert module.index("tank_preposition_for_pending_swarm_pickup") < module.index(
        "feral_prepare_bear_form_before_passive_swarm_activation"
    )
    assert module.index("feral_prepare_bear_form_before_passive_swarm_activation") < (
        module.index("tank_activate_passive_swarm")
    )
    assert module.index("tank_activate_passive_swarm") < module.index(
        "hold_pending_swarm_area_threat_resources"
    )


def test_azil_passive_swarm_staging_keeps_native_movement_and_activation():
    module = MODULE.read_text(encoding="utf-8")

    for marker in (
        "MoveFollow(",
        "MoveBotToPoint(state, bot",
        "SubmitMeleeAutoAttackIntent(state",
        "BotMeleeAutoAttack::Kind::StartOrSwitch",
        "TryEnsurePersistentCombatSetup(",
        "GetSpellHistory()->HasGlobalCooldown(",
        "IsWithinMeleeRange",
        "IsWithinLOSInMap",
        "RecordEvent(state, bot",
        "tank_activate_passive_swarm",
    ):
        assert marker in module
    for forbidden in (
        "NearTeleportTo",
        "SetVictim",
        "AddThreat",
        "SetThreat",
    ):
        assert forbidden not in module
