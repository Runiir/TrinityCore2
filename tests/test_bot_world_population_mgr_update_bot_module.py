from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
SOURCE = BOT_DIR / "BotWorldPopulationMgr.cpp"
HEADER = BOT_DIR / "BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"

MODULES = (
    "BotWorldPopulationMgrUpdateBot.cpp",
    "BotWorldPopulationMgrUpdateBotPreparation.cpp",
    "BotWorldPopulationMgrUpdateBotDecision.cpp",
    "BotWorldPopulationMgrUpdateBotFinalization.cpp",
    "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp",
    "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp",
    "BotWorldPopulationMgrUpdateBotKernelFallback.cpp",
    "BotWorldPopulationMgrUpdateBotLegacy.cpp",
)


def test_update_bot_modules_are_bounded_and_registered() -> None:
    cmake = CMAKE.read_text(encoding="utf-8")
    for name in MODULES:
        module = BOT_DIR / name
        text = module.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 1000
        assert name in cmake
        assert '#include "Bots/BotWorldPopulationMgrUpdateContext.h"' in text

    context = BOT_DIR / "BotWorldPopulationMgrUpdateContext.h"
    assert len(context.read_text(encoding="utf-8").splitlines()) <= 1000


def test_update_bot_dispatches_explicit_phases() -> None:
    source = (BOT_DIR / "BotWorldPopulationMgrUpdateBot.cpp").read_text(
        encoding="utf-8"
    )
    assert "PrepareBotUpdate(context)" in source
    assert "RunBotDecisionKernel(context)" in source
    assert "FinalizeBotUpdate(context)" in source
    assert "ReconcileOnScopeExit" in source
    assert "BotWorldPopulationMgr::UpdateBot" in source
    assert "BotWorldPopulationMgr::UpdateBot" not in SOURCE.read_text(
        encoding="utf-8"
    )


def test_update_bot_preserves_lifecycle_contracts() -> None:
    preparation = (BOT_DIR / "BotWorldPopulationMgrUpdateBotPreparation.cpp").read_text(
        encoding="utf-8"
    )
    decision = (BOT_DIR / "BotWorldPopulationMgrUpdateBotDecision.cpp").read_text(
        encoding="utf-8"
    )
    finalization = (BOT_DIR / "BotWorldPopulationMgrUpdateBotFinalization.cpp").read_text(
        encoding="utf-8"
    )
    for marker in (
        "ValidationAttemptFailureReason",
        "IsNativeRaidRecoveryEvidencePending",
        "TryRespondNativeRaidReadyCheck",
        "RememberSafePosition",
        "DecisionTimer",
        "EnsureProgressionScored",
    ):
        assert marker in preparation
    for marker in (
        "PrepareValidationKernel",
        "SubmitAdaptiveKernelCandidates",
        "SubmitValidationKernelFallbackCandidates",
        "DecisionKernel.Resolve",
    ):
        assert marker in decision
    for marker in (
        "loop_guardrail_triggered",
        "RecordDecision",
        "MaybeAdvanceValidationRouteManifest",
    ):
        assert marker in finalization
    assert "BotUpdateContext" in HEADER.read_text(encoding="utf-8")
