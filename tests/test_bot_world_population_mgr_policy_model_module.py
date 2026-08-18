from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrPolicyModel.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "BuildActivityCandidatesJson",
    "ApplyPolicyModelScores",
    "BuildPolicyModelFeatureMap",
    "PredictPolicyModelLabel",
    "ScorePolicyModelCandidate",
    "BuildPolicyModelTrace",
    "FeatureSchemaHash",
)


def test_policy_model_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrPolicyModel.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_policy_model_module_preserves_candidate_features_and_labels() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for field in (
        "learned_score",
        "expected_power_gain",
        "expected_death_risk",
        "json_chosen_activity_score",
        "action_success",
        "expected_reward",
        "death_risk",
        "quest_completion_likelihood",
        "top_alternatives",
        "model_features_hash",
    ):
        assert field in module


def test_policy_model_module_keeps_assist_latency_gate() -> None:
    module = MODULE.read_text(encoding="utf-8")
    assert 'PolicyModelConfig.Mode == "assist"' in module
    assert "MaxDecisionLatencyMs" in module
    assert "ScoreWeight" in module
    assert "EvalPortableTree" in module
    assert "Sigmoid" in module
