"""A heal never cancels a protected Nefarian surface leg or escape (round 7 review).

The plan's surface legs and escapes (TransportSurfaceMove) are admitted
outside the native path bookkeeping (ActivePathValid) the shared heal guard
reads, and a platform hold clears that bookkeeping. The plan publishes them as
a movement lease (BotWorldPopulationMgrNefarianCandidates.cpp): Mechanic for a
leg or hold, Hazard for a survival escape. The shared patch
(.git/round7_patches/nefarian/R7_protected_movement_heal_guard.patch) reads
that lease through BotEncounter::Nefarian::ProtectedMovementActive:
- the heal candidate then selects only instant heals;
- TryCastFriendlySpell refuses a cast-time spell instead of stopping the
  spline ("protected_movement_active").
The temporal replay drives the real strategy: hold, escape launch, retained
escape, and a concurrent heal decision on each tick.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.test_nefarian_strategy import PROGRAM, _compile_and_run

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
PATCH = ROOT / ".git/round7_patches/nefarian/R7_protected_movement_heal_guard.patch"
HELPER = BOTS / "Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianProtectedMovement.h"


def _patched_sources() -> dict[str, str]:
    """The two shared files, as in the tree or as the patch leaves them."""
    files = {
        "candidates": BOTS / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp",
        "support": BOTS / "BotWorldPopulationMgrCombatSupport.cpp",
    }
    texts = {key: path.read_text(encoding="utf-8") for key, path in files.items()}
    if all("ProtectedMovementActive" in text for text in texts.values()):
        return texts
    if not PATCH.exists():
        pytest.skip("heal guard neither in the tree nor patched")
    result = subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    patch = PATCH.read_text(encoding="utf-8")
    added = "\n".join(line[1:] for line in patch.splitlines()
                      if line.startswith("+") and not line.startswith("+++"))
    return {"candidates": added, "support": added}


def test_patch_guards_both_heal_paths() -> None:
    texts = _patched_sources()
    candidates, support = texts["candidates"], texts["support"]
    assert "BotEncounter::Nefarian::ProtectedMovementActive(" in candidates
    assert "context.State.MovementLease, !context.Bot->movespline->Finalized()" in candidates
    assert "Cohort().Config.ValidationRouteNodeId" in candidates
    assert 'return fail("protected_movement_active");' in support
    assert "state->MovementLease" in support
    tree = (BOTS / "BotWorldPopulationMgrCombatSupport.cpp").read_text(encoding="utf-8")
    if "ProtectedMovementActive" in tree:
        stop = tree.index("bot->StopMoving();\n        bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);")
        assert tree.index('return fail("protected_movement_active");') < stop
        guard = (BOTS / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp").read_text(encoding="utf-8")
        lam = guard[guard.index("auto activeNativeMovementPath = [this, &context]()"):]
        assert lam.index("ProtectedMovementActive(") < lam.index("if (!context.State.ActivePathValid)")


def test_patch_scope_is_the_nefarian_node() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    assert 'ProtectedMovementNodeId = "bwd.nefarian.encounter";' in helper
    facts = (HELPER.parent / "BotNefarianFacts.h").read_text(encoding="utf-8")
    assert 'EncounterNodeId = "bwd.nefarian.encounter";' in facts
    assert "routeNodeId == ProtectedMovementNodeId && splineRunning" in helper
    assert ">= uint8(BotMovementArbitration::Priority::Mechanic)" in helper


REPLAY = PROGRAM.replace(
    '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"',
    '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"\n'
    '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianProtectedMovement.h"').replace(
    "int main()", "[[maybe_unused]] static int StrategyMain()") + r'''
using BotMovementArbitration::Apply;
using BotMovementArbitration::Lease;
using BotMovementArbitration::Owner;
using BotMovementArbitration::Priority;
using BotMovementArbitration::Request;

// The lease the candidates file applies for each plan (mirrors
// BotWorldPopulationMgrNefarianCandidates.cpp: an admitted leg - Hazard for a
// survival escape, Mechanic otherwise - and every hold, Hazard for the
// warrior stop, Mechanic for the platform hold and a leg in flight).
static void Publish(Lease& lease, AdaptiveNefarianPlan const& plan, uint64 now)
{
    Request request;
    request.MovementScope = BotMovementArbitration::Scope{ 1, 0, 0, 669, 1 };
    request.ExpiresAtMs = now + 1500;
    bool hazard = false;
    if (plan.Movement)
        hazard = uint8(plan.Movement->ActionPriority)
            >= uint8(BotActionArbitration::Priority::Survival);
    else if (plan.MovementHold == WarriorStopHold)
        hazard = true;
    else if (!IsPlatformHold(plan.MovementHold) && plan.MovementHold != LegInFlightHold)
        return;
    request.MovementOwner = hazard ? Owner::Hazard : Owner::Mechanic;
    request.MovementPriority = hazard ? Priority::Hazard : Priority::Mechanic;
    Apply(lease, request);
}

int main()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = CanonicalBoard();
    AddDragons(board, true);
    uint32 const healer = 5; // the Holy paladin
    LocalPoint const at{ -8.0f, 16.0f };
    PlaceAt(FindPlayer(board, healer), at);
    std::string_view const node = "bwd.nefarian.encounter";
    Lease lease;
    uint64 now = 1000;

    // Tick 0: standing on the platform, held; nothing runs, a hard cast is free.
    NativeFacts standing = StandingFacts(board, healer);
    AdaptiveNefarianPlan const held = strategy.Propose(board, Bot(healer), "healer", &standing);
    CHECK(IsPlatformHold(held.MovementHold), "tick 0: the platform hold");
    Publish(lease, held, now);
    CHECK(!ProtectedMovementActive(lease, false, node, now), "tick 0: standing, hard casts allowed");

    // Tick 1: a Shadowblaze fire under it: the escape is launched.
    now += 100;
    ActorSnapshot fire = MakeCreature(ShadowblazeEntry, 50, { at.X + 1.0f, at.Y });
    fire.Attackable = false;
    board.Summons.push_back(fire);
    AdaptiveNefarianPlan const escape = strategy.Propose(board, Bot(healer), "healer", &standing);
    CHECK(escape.Movement && escape.MovementLeg && escape.MovementSurface
        && escape.MovementSurface->Purpose == MovePurpose::FireEscape, "tick 1: the fire escape");
    CHECK(escape.Movement && escape.Movement->ActionPriority == BotActionArbitration::Priority::Survival,
        "tick 1: a survival escape");
    Publish(lease, escape, now);
    CHECK(ProtectedMovementActive(lease, true, node, now),
        "tick 1: the launched escape is protected (instant heals only, no hard-cast stop)");

    // Ticks 2-6: the escape retained (in flight); a heal decision each tick.
    NativeFacts running = standing;
    LocalPoint const end = escape.MovementLeg->To;
    running.Motion.push_back({ Bot(healer), true, LocalToWorld(end, FloorLocalZAt(end),
        PlatformFrame::RaisedOriginZ) });
    for (int tick = 2; tick <= 6; ++tick)
    {
        now += 250;
        AdaptiveNefarianPlan const retained = strategy.Propose(board, Bot(healer), "healer", &running);
        CHECK(retained.MovementHold == LegInFlightHold, "the escape is kept in flight");
        Publish(lease, retained, now);
        CHECK(ProtectedMovementActive(lease, true, node, now),
            "a concurrent heal decision sees protected movement");
        CHECK(!ProtectedMovementActive(lease, true, "bwd.maloriak.encounter", now),
            "scope: the Nefarian node only");
    }
    // The escape done (spline finished): hard casts are free again.
    CHECK(!ProtectedMovementActive(lease, false, node, now), "after the escape, hard casts allowed");
    // A lapsed lease protects nothing.
    CHECK(!ProtectedMovementActive(lease, true, node, now + 5000), "a lapsed lease protects nothing");
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    return failures ? 1 : 0;
}
'''


def test_hold_escape_retained_heal_replay(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, REPLAY)
