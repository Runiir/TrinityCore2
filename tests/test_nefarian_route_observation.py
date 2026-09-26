"""The Nefarian route observation (the engagement edge the kill needs).

The adaptive Nefarian owner replaces the route adapter on the encounter node,
and only the route adapter or an adaptive observer calls
RememberValidationRouteBossEngagement. Without it the native death callback
rejects the kill (gate=combined_rejected), as it rejected Atramedes' in
round 5. These checks pin the observer (Nefarian only - never Onyxia, whose
death is not the kill), its wiring patch, and the death-callback gate.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
ADAPTER = (BOTS / "Content/Raids/BlackwingDescent/Encounters/Nefarian/"
           "BotWorldPopulationMgrNefarianCandidates.cpp")
PATCH = ROOT / ".git/round7_patches/nefarian/R7_nefarian_route_observation.patch"
FACTS = BOTS / "Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianFacts.h"


def body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[brace + 1:index]
    raise AssertionError(signature)


def test_observer_binds_only_nefarian_while_the_plan_owns_him() -> None:
    source = ADAPTER.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 1000
    observer = body(source, "void BotWorldPopulationMgr::SubmitAdaptiveNefarianRouteObservation")
    remember = observer.index("RememberValidationRouteBossEngagement(creature)")
    for gate in ("context.AdaptiveNefarianOwnsNode",
                 'Cohort().Config.ValidationRouteKind != "boss"',
                 "BotEncounter::Nefarian::EncounterNodeId",
                 "BotEncounter::Nefarian::NefarianEntry",
                 "Cohort().Config.ValidationRouteTargetEntry",
                 "!target->IsInCombat()",
                 "target->IsFlying()",
                 "!context.Bot->IsValidAttackTarget(target)",
                 "IsNativeCombatObserved(context.Bot, target)"):
        assert observer.index(gate) < remember, gate
    # Onyxia never registers: the entry gate is Nefarian's alone.
    assert "OnyxiaEntry" not in observer and "41270" not in observer
    facts = FACTS.read_text(encoding="utf-8")
    assert "constexpr uint32 NefarianEntry = 41376;" in facts
    assert 'EncounterNodeId = "bwd.nefarian.encounter";' in facts
    assert remember < observer.index("nefarian_route_observation_already_recorded")
    for forbidden in ("context.Target =", "State.TargetGuid =", "ValidationRouteFocusGuid",
                      "MoveBotToPoint", "ExecuteNativeActionIntent", "MovementLease"):
        assert forbidden not in observer, forbidden
    assert '"world.validation_route_nefarian_observation"' in observer
    assert "Resource::None" in observer


def test_death_callback_still_needs_the_engagement_edge() -> None:
    source = (BOTS / "BotWorldPopulationMgrCombatLog.cpp").read_text(encoding="utf-8")
    callback = body(source, "void BotWorldPopulationMgr::NotifyCreatureDeath")
    assert "Party().ValidationRouteEngagedBossGuid != killed->GetGUID()" in callback
    focus = (BOTS / "BotWorldPopulationMgrValidationFocus.cpp").read_text(encoding="utf-8")
    assert "Party().ValidationRouteEngagedBossGuid = boss->GetGUID();" in body(
        focus, "void BotWorldPopulationMgr::RememberValidationRouteBossEngagement")


DECLARATION = "void SubmitAdaptiveNefarianRouteObservation(BotUpdateContext& context);"
CALL = "SubmitAdaptiveNefarianRouteObservation(context);"
BESIDE_ATRAMEDES = re.compile(r"SubmitAdaptiveAtramedesRouteObservation\(context\);\n"
                              r"[+ ]? *SubmitAdaptiveNefarianRouteObservation\(context\);")


def test_wiring_declares_and_submits_the_observer() -> None:
    header = (BOTS / "BotWorldPopulationMgr.h").read_text(encoding="utf-8")
    fallback = (BOTS / "BotWorldPopulationMgrUpdateBotKernelFallback.cpp").read_text(encoding="utf-8")
    if DECLARATION in header or CALL in fallback:
        assert DECLARATION in header
        assert BESIDE_ATRAMEDES.search(fallback)
        return
    if not PATCH.exists():
        pytest.skip("observer wiring not in the tree and no round 7 patch")
    patch = PATCH.read_text(encoding="utf-8")
    added = [line[1:].strip() for line in patch.splitlines()
             if line.startswith("+") and not line.startswith("+++")]
    assert DECLARATION in added
    assert CALL in added
    assert BESIDE_ATRAMEDES.search(patch)
    result = subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
