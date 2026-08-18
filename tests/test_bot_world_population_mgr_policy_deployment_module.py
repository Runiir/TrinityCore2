from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrPolicyDeployment.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "ValidatePolicyModelDeployment",
    "LoadPolicyModelArtifact",
)


def test_policy_deployment_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrPolicyDeployment.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_policy_deployment_methods_and_parser_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text
    for helper in (
        "ParsePortableTree",
        "ParsePortableTreeEnsembles",
        "ExtractJsonNumberMap",
    ):
        assert f"{helper}(" not in text


def test_policy_deployment_keeps_fail_closed_contract():
    text = MODULE.read_text()
    for marker in (
        "model_not_registered",
        "artifact_load_failed",
        "control_mode_disabled",
        "model_not_accepted",
        "insufficient_eval_rows",
        "death_rate_regression",
        "stuck_rate_regression",
        "failure_rate_regression",
        "AssistAllowed = true",
        'Mode = "shadow"',
        "tree_ensembles",
    ):
        assert marker in text
