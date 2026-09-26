"""The Atramedes route observation (the engagement edge the kill needs).

Round 5 killed Atramedes (26,110,798 damage, no death) but the native death
callback rejected the kill: gate=combined_rejected with an empty
engaged_guid_expected. The adaptive owner skips the route adapter, and only
the route adapter or an adaptive observer calls
RememberValidationRouteBossEngagement. Magmaw and Chimaeron have observers;
Atramedes had none, so the route never recorded the clear. These checks pin
the observer, its wiring patch, and the death-callback gate that needs it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
ADAPTER = (BOTS / "Content/Raids/BlackwingDescent/Encounters/Atramedes/"
           "BotWorldPopulationMgrAtramedesCandidates.cpp")
PATCH = ROOT / ".git/round6_patches/atramedes/atramedes_route_observation.patch"


def body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[brace + 1:index]
    raise AssertionError(signature)


def test_observer_binds_the_engagement_only_while_the_plan_owns_the_boss() -> None:
    source = ADAPTER.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 1000
    observer = body(source, "void BotWorldPopulationMgr::SubmitAdaptiveAtramedesRouteObservation")
    remember = observer.index("RememberValidationRouteBossEngagement(creature)")
    # The gates come first: the plan owns the node, the node is the
    # encounter, the target is Atramedes (the route target entry), he is in
    # combat and native combat with him is observed.
    for gate in ("context.AdaptiveAtramedesOwnsNode",
                 "BotEncounter::Atramedes::EncounterNode",
                 "BotEncounter::Atramedes::BossEntry",
                 "Cohort().Config.ValidationRouteTargetEntry",
                 "!target->IsInCombat()",
                 "IsNativeCombatObserved(context.Bot, target)"):
        assert observer.index(gate) < remember, gate
    # Bound before the per-bot dedupe, so every tick refreshes it.
    assert remember < observer.index("atramedes_route_observation_already_recorded")
    # Observation only: never retargets, refocuses or moves.
    for forbidden in ("context.Target =", "State.TargetGuid =", "ValidationRouteFocusGuid",
                      "MoveBotToPoint", "ExecuteNativeActionIntent"):
        assert forbidden not in observer, forbidden
    assert '"world.validation_route_atramedes_observation"' in observer
    assert "Resource::None" in observer


def test_death_callback_still_needs_the_engagement_edge() -> None:
    source = (BOTS / "BotWorldPopulationMgrCombatLog.cpp").read_text(encoding="utf-8")
    callback = body(source, "void BotWorldPopulationMgr::NotifyCreatureDeath")
    assert "Party().ValidationRouteEngagedBossGuid != killed->GetGUID()" in callback
    focus = (BOTS / "BotWorldPopulationMgrValidationFocus.cpp").read_text(encoding="utf-8")
    assert "Party().ValidationRouteEngagedBossGuid = boss->GetGUID();" in body(
        focus, "void BotWorldPopulationMgr::RememberValidationRouteBossEngagement")


DECLARATION = "void SubmitAdaptiveAtramedesRouteObservation(BotUpdateContext& context);"
CALL = "SubmitAdaptiveAtramedesRouteObservation(context);"
BESIDE_CHIMAERON = re.compile(r"SubmitAdaptiveChimaeronRouteObservation\(context\);\n"
                              r"[+ ]? *SubmitAdaptiveAtramedesRouteObservation\(context\);")


def test_wiring_declares_and_submits_the_observer() -> None:
    # The tree first: once the round 6 patch is applied (and its directory
    # archived), both sites are in the tree and the patch is not read.
    header = (BOTS / "BotWorldPopulationMgr.h").read_text(encoding="utf-8")
    fallback = (BOTS / "BotWorldPopulationMgrUpdateBotKernelFallback.cpp").read_text(encoding="utf-8")
    if DECLARATION in header or CALL in fallback:
        assert DECLARATION in header
        # Beside the Chimaeron observer, in the fallback candidates.
        assert BESIDE_CHIMAERON.search(fallback)
        return
    # Not applied yet: the patch adds both sites and still applies.
    if not PATCH.exists():
        pytest.skip("observer wiring not in the tree and no round 6 patch")
    patch = PATCH.read_text(encoding="utf-8")
    added = [line[1:].strip() for line in patch.splitlines()
             if line.startswith("+") and not line.startswith("+++")]
    assert DECLARATION in added
    assert CALL in added
    assert BESIDE_CHIMAERON.search(patch)
    result = subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
