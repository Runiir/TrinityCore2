from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatRes.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"

MOVED_METHODS = (
    "CurrentCombatResOwnerUsable",
    "PublishNativeBattleResDecision",
    "ReconcileNativeBattleResDecisions",
    "BuildCombatResNativeActionCandidate",
)


def test_combat_res_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCombatRes.cpp" in CMAKE.read_text()
    assert "#include \"Bots/BotWorldPopulationMgr.h\"" in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text


def test_combat_res_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_combat_res_module_keeps_native_reservation_contract():
    text = MODULE.read_text()
    for marker in (
        "declined_reservation_missing",
        "reserved_approach",
        "reserved_cast_submitted",
        "declined_no_combat_res_spell",
        "CombatResReservationLifetimeMs",
        "IsNativeCombatResSpell",
        "HasPowerForSpell",
        "PathGenerator",
        "ValidationCohort",
        "NativeResurrectionPendingUntilMs",
    ):
        assert marker in text


def _native_trash_recovery_window(
    *,
    route_kind="trash",
    boss_recovery_policy="native_encounter",
    hostile_active=False,
    inactivity_observed=True,
    reset_generation=1,
    reset_generation_at_wipe=0,
    observation_attempt_id=2,
    attempt_id=2,
    observation_route_generation=2,
    route_generation=2,
    observation_node_id="bwd.magmaw.chainwielder",
    route_node_id="bwd.magmaw.chainwielder",
):
    return (
        route_kind == "trash"
        and boss_recovery_policy != "native_full_wipe_only"
        and observation_attempt_id == attempt_id
        and observation_route_generation == route_generation
        and observation_node_id == route_node_id
        and inactivity_observed
        and not hostile_active
        and reset_generation > reset_generation_at_wipe
    )


def test_out_of_combat_rebirth_requires_current_cleared_trash_observation():
    text = MODULE.read_text()
    gate = text[
        text.index("bool const nativeTrashRecoveryWindow") :
        text.index("std::vector<Member> eligibleDead", text.index("bool const nativeTrashRecoveryWindow"))
    ]
    assert "NativeHostileInactivityObserved" in gate
    assert "NativeHostileResetGeneration > raid.NativeHostileResetGenerationAtWipe" in gate
    assert "if (!groupCombatActive && !nativeTrashRecoveryWindow)" in gate

    assert _native_trash_recovery_window()
    assert not _native_trash_recovery_window(hostile_active=True)
    assert not _native_trash_recovery_window(inactivity_observed=False)
    assert not _native_trash_recovery_window(reset_generation=0)
    assert not _native_trash_recovery_window(observation_attempt_id=1)
    assert not _native_trash_recovery_window(observation_route_generation=1)
    assert not _native_trash_recovery_window(
        observation_node_id="bwd.magmaw.drudge_pair"
    )
    assert not _native_trash_recovery_window(route_kind="boss")
    assert not _native_trash_recovery_window(
        boss_recovery_policy="native_full_wipe_only"
    )
