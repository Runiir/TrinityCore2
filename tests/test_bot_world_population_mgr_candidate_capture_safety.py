from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFERRED_CANDIDATE_SOURCES = (
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelCandidates.cpp",
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp",
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelPreparation.cpp",
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrAfflictionPetCombat.cpp",
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrMagmawBloodlust.cpp",
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrRaidConsumables.cpp",
)


def _attempt_lambda_captures(source: str) -> list[str]:
    """Return capture lists belonging to deferred Candidate::Attempt lambdas."""
    pattern = re.compile(r"\bAttempt\s*=\s*(\[[^\]]*\])\s*\(", re.DOTALL)
    return [match.group(1) for match in pattern.finditer(source)]


def test_deferred_candidate_attempts_never_use_blanket_reference_capture() -> None:
    captures = [
        capture
        for path in DEFERRED_CANDIDATE_SOURCES
        for capture in _attempt_lambda_captures(path.read_text(encoding="utf-8"))
    ]

    assert captures, "expected deferred candidate Attempt lambdas"
    for capture in captures:
        # A candidate is resolved after its submitter's stack frame can return.
        # Every reference must name the live object it intentionally borrows;
        # a blanket [&] can silently retain a dead local helper or flag.
        assert not re.search(r"(?:\[|,)\s*&\s*(?:,|\])", capture), capture


def test_adaptive_attempts_borrow_only_explicit_live_context() -> None:
    source = DEFERRED_CANDIDATE_SOURCES[0].read_text(encoding="utf-8")
    captures = _attempt_lambda_captures(source)

    assert captures, "no adaptive deferred attempts found"
    assert all("&context" in capture for capture in captures)


def test_fallback_attempts_copy_route_closure_or_borrow_explicit_live_context() -> None:
    source = DEFERRED_CANDIDATE_SOURCES[1].read_text(encoding="utf-8")
    captures = _attempt_lambda_captures(source)

    assert captures, "no fallback deferred attempts found"
    assert captures[:2] == ["[runRoute, routeAttempt]", "[runRoute, routeAttempt]"]
    assert all("&context" in capture for capture in captures[2:])
