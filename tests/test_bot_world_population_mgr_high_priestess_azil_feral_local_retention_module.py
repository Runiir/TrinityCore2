from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MODULE_HEADER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/"
    "HighPriestessAzilFeralLocalRetention.h"
)
MODULE = MODULE_HEADER.with_suffix(".cpp")
CONTEXT_HEADER = MODULE_HEADER.with_name(
    "HighPriestessAzilHealerAddWavePreposition.h"
)


def test_azil_feral_local_retention_is_registered_and_bounded():
    world = WORLD.read_text(encoding="utf-8")
    mgr_header = MGR_HEADER.read_text(encoding="utf-8")
    module_header = MODULE_HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    context_header = CONTEXT_HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert len(mgr_header.splitlines()) <= 990
    assert len(module_header.splitlines()) <= 1000
    assert len(module.splitlines()) <= 1000
    assert "HighPriestessAzilFeralLocalRetention.cpp" in cmake
    assert "FeralLocalRetentionRequest" in module_header
    assert "FeralHandoffStateResult const* FeralHandoff" in module_header
    assert "TryFeralLocalRetention" in module_header
    assert "static bool Run(FeralLocalRetentionRequest const& request);" in (
        context_header
    )
    assert "HighPriestessAzilFeralLocalRetention.h" in world


def test_azil_feral_local_retention_owns_the_exact_handoff_tail():
    world = WORLD.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    handoff_dispatch = world.index("ResolveFeralHandoffState(")
    retention_dispatch = world.index("TryFeralLocalRetention(")
    remote_actions_dispatch = world.index("TryFeralRemoteActions(")
    assert handoff_dispatch < retention_dispatch < remote_actions_dispatch
    assert "localHealerOwnedSwipeWindow" not in world[
        retention_dispatch:remote_actions_dispatch
    ]
    assert "feralHealerHandoffArrived" not in world[
        retention_dispatch:remote_actions_dispatch
    ]

    for marker in (
        "localHealerOwnedSwipeWindow",
        "localHealerOwnedSwipeCount * 2",
        "manager.TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)",
        '"feral_thrash_healer_swarm_retention_before_roar"',
        "manager.TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
        "tryFeralRoarPickup(true)",
        "postRoarAreaThreatReady = feralHealerHandoffActive",
        '"feral_charge_remote_cluster_swarm_handoff"',
        "manager.MoveBotToPoint(state,",
        "if (feralHealerHandoffArrived)",
        "bot->StopMoving();",
    ):
        assert marker in module

    assert module.index(
        "manager.TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)"
    ) < module.index('"feral_thrash_healer_swarm_retention_before_roar"')
    assert module.index(
        '"feral_charge_remote_cluster_swarm_handoff"'
    ) < module.index("manager.MoveBotToPoint(state,")
    assert module.index("manager.MoveBotToPoint(state,") < module.index(
        "bot->StopMoving();"
    )


def test_azil_feral_local_retention_preserves_native_only_state_boundaries():
    module = MODULE.read_text(encoding="utf-8")

    assert "SetVictim" not in module
    assert "AddThreat" not in module
    assert "SetThreat" not in module
    assert "NearTeleportTo" not in module
    assert "FeralHandoffStateResult const& feralHandoff" in module
    assert "return false;" in module
