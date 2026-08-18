from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCohort.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


COHORT_METHODS = (
    "BotWorldPopulationMgr::BotWorldPopulationMgr",
    "BotWorldPopulationMgr::Cohort",
    "BotWorldPopulationMgr::Party",
    "BotWorldPopulationMgr::FindCohort",
    "BotWorldPopulationMgr::SelectCohort",
    "BotWorldPopulationMgr::ClaimBotGuid",
    "BotWorldPopulationMgr::ReleaseBotGuid",
    "BotWorldPopulationMgr::StartAutonomyForCohort",
    "BotWorldPopulationMgr::RequestNativeRaidReadyCheckForCohort",
)


def test_cohort_module_is_narrow_and_registered() -> None:
    assert len(MODULE.read_text(encoding="utf-8").splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrCohort.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    for method in COHORT_METHODS:
        assert module.count(method) >= 1
        assert method not in world


def test_cohort_module_keeps_epoch_identity_local() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert "BuildServerEpoch()" in module
    assert "CurrentProcessId()" in module
    assert "uint64 BuildServerEpoch()" not in world
    assert "uint64 CurrentProcessId()" not in world


def test_cohort_module_preserves_native_ready_check_guards() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for guard in (
        "raid_runtime_inactive",
        "raid_attempt_identity_mismatch",
        "exact_active_raid_roster_required",
        "all_raid_members_must_be_alive",
        "all_raid_leases_must_be_owned",
        "exact_raid_composition_required",
        "live_raid_difficulty_mismatch",
        "actual_raid_leader_group_unavailable",
        "native_raid_group_shape_mismatch",
        "live_exact_raid_roster_revalidation_failed",
    ):
        assert f'fail("{guard}")' in module
