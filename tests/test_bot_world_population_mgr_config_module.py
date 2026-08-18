from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrConfig.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"

MOVED_METHODS = (
    "ApplyRuntimeConfigOverride",
    "ApplyRuntimeProfile",
    "LoadConfig",
)


def test_config_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrConfig.cpp" in CMAKE.read_text()
    assert "#include \"Bots/BotWorldPopulationMgr.h\"" in text
    assert "#include \"Config.h\"" in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text


def test_config_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_config_module_keeps_profile_and_route_loading_contract():
    text = MODULE.read_text()
    for marker in (
        "BotWorld.RuntimeProfile",
        "BotProgression.DungeonDifficulty",
        "BotWorld.ValidationRoute.ManifestPath",
        "ParseUIntList",
        "LoadValidationRouteManifest",
        "EnsureRuntimeProfilesLoaded",
        "BotTelemetryBufferConfig",
        "ValidatePolicyModelDeployment",
    ):
        assert marker in text
