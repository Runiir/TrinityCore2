from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrDiagnosis.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "BuildBotDiagnosis",
    "BuildBotDiagnosisObjectJson",
    "BuildBotDecisionSnapshotJson",
    "BuildBotTraceEntriesJson",
)


def test_diagnosis_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrDiagnosis.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_diagnosis_module_preserves_state_codes_and_evidence() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for code in (
        "validation_cohort_instance_violation",
        "dead_recovery",
        "blocked_no_fallback",
        "route_destination_unreachable",
        "native_descent_blocked",
        "repeated_decision_loop",
        "target_churn_loop",
        "no_supported_objective",
    ):
        assert code in module
    for evidence in (
        "native_current_motion_type",
        "validationRoutePackMembers",
        "pet_db_row_present",
        "combat_attempt",
        "route_progress",
        "decision_kernel",
    ):
        assert evidence in module


def test_diagnosis_module_preserves_trace_snapshot_contract() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for field in (
        "threat_snapshot",
        "engaged_hostile_guids",
        "tank_owned_hostile_guids",
        "healer_targeting_hostile_guids",
        "fingerprint_repeat_count",
        "blocked_episode_id",
        "ValidationDescentPhaseName",
        "RuntimeModeName",
    ):
        assert field in module
