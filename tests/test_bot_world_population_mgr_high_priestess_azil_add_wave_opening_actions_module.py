from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/"
    "HighPriestessAzilAddWaveOpeningActions.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
CONTEXT_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)


def test_azil_opening_actions_module_is_registered_and_bounded():
    world = WORLD.read_text(encoding="utf-8")
    mgr_header = MGR_HEADER.read_text(encoding="utf-8")
    module_header = MODULE_HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    context_header = CONTEXT_HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert len(mgr_header.splitlines()) <= 990
    assert len(module_header.splitlines()) <= 1000
    assert len(module.splitlines()) <= 1000
    assert "HighPriestessAzilAddWaveOpeningActions.cpp" in cmake
    assert "AddWaveOpeningActionsRequest" in module_header
    assert "TryAddWaveOpeningActions" in module_header
    assert "static bool Run(AddWaveOpeningActionsRequest const& request);" in context_header
    assert "HighPriestessAzilAddWaveOpeningActions.h" in world


def test_azil_opening_actions_stay_between_density_and_cluster_resolvers():
    world = WORLD.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    density = world.index("ResolveAddWaveDensity(")
    dispatch = world.index("TryAddWaveOpeningActions(")
    cluster = world.index("TryFeralActiveSwarmMovement(")
    assert density < dispatch < cluster
    opening_gap = world[dispatch:cluster]
    for marker in (
        "pendingSwarmPickupNowMs",
        "TankPendingSwarmPickupEngagedHandoff",
        "pendingSwarmPickupNowMs + 2500",
        "tank_continue_pending_swarm_pickup_preposition",
        "tank_pending_swarm_pickup_path_rejected",
        "healerWaveFadeReady",
        "fade_preemptive_add_wave_threat_drop",
    ):
        assert marker in module
        assert marker not in opening_gap


def test_azil_opening_actions_preserve_lease_and_fade_order():
    module = MODULE.read_text(encoding="utf-8")

    for earlier, later in (
        ("pendingSwarmPickupNowMs = NowMs()", "pendingSwarmPickupNowMs + 2500"),
        ("pendingSwarmPickupNowMs + 2500", "tank_continue_pending_swarm_pickup_preposition"),
        ("tank_continue_pending_swarm_pickup_preposition", "healerWaveFadeReady"),
        ("healerWaveFadeReady", "fade_preemptive_add_wave_threat_drop"),
        ("InterruptNonMeleeSpells(false)", "TryCastFriendlySpell(bot, bot, 586)"),
        ("TryCastFriendlySpell(bot, bot, 586)", "RecordEvent(state, bot, \"boss_adds\""),
    ):
        assert module.index(earlier) < module.index(later)

    assert "<= (engagedHandoff ? 10.0f : 6.0f)" in module
    assert "!densityTankOwnsSecureMajority" in module
    assert "observedListedAttackerCount(bot) > 0" in module
