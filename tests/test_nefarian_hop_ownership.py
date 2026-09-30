"""A healer in the middle of its hop onto a pillar keeps the jump.

The review: a Disc or Holy healer mid-hop with an injured teammate could run
the raid heal, whose TryCastFriendlySpell stops the member before a cast-time
heal and so cancels the jump over the magma, short of the pillar. The ascent
candidate (BotNefarianAscentIntent.h, Survival priority, movement + GCD +
cast lanes) is answered with progress while the jump runs
(BotTransportLiquidMovement: native_liquid_hop_in_flight), a committed
outcome, so the kernel keeps those lanes and the heal is never attempted in
that tick. Replayed here with the real arbitration kernel.

Round 3 (E2, round-2 evidence): melee members' native chase toward the
prototype on the pillar top put the rogue (3 of 3 runs) and both tanks (2 of
3) inside the hollow pillar shaft, and a Ret paladin on a top without boarding.
In phase 2 every plan now carries the pillar hold (BotNefarianMovement.h),
alone or as the fallback beside a proposed step: whenever the step is refused
the hold claims the movement lane and renews the movement lease that native
combat movement meets (tests/test_nefarian_stop_hold.py). The positions below
are the recorded ones.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_nefarian_strategy import PRELUDE, _compile_and_run


PROGRAM = PRELUDE.replace(
    '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"',
    '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"\n'
    '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianAscentIntent.h"\n'
    '#include "Bots/BotActionArbiter.h"') + r'''
static bool Replay(BotActionArbitration::Outcome hopAnswer)
{
    using namespace BotActionArbitration;
    Blackboard board = PlatformBoard(PlatformFrame::LoweredOriginZ);
    // The Disc priest mid-hop, its teammate at 35%.
    DutyPlan const duty = BuildNefarianDutyPlan(board);
    uint8 const pillar = uint8(duty.PillarOf(Bot(7)));
    uint8 const slot = duty.SlotOf(Bot(7));
    Vector3 const landing = LocalToWorld(PillarRadial(pillar, slot, HopLandingRadius(pillar, slot)),
        HopLandingLocalZ, PlatformFrame::LoweredOriginZ);
    Vector3 air = LocalToWorld(PillarRadial(pillar, slot, 5.5f), 0.0f, 0.0f);
    air.Z = MagmaSurfaceZ + 0.6f;
    FindPlayer(board, 7).Position = air;
    FindPlayer(board, 6).HealthPct = 35.0f;
    NativeFacts facts;
    facts.PillarAscentSupported = true;
    facts.Motion.push_back({ Bot(7), true, landing });
    AdaptiveNefarianStrategy strategy;
    AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(7), "healer", &facts);
    CHECK(plan.Ascent && plan.Ascent->Stage == AscentStage::Hop, "the plan keeps the hop");
    BotNativeAction::Candidate const ascent = AscentCandidate(*plan.Ascent, board, Bot(7));

    Kernel kernel;
    kernel.Begin(1000);
    bool healAttempted = false;
    Candidate heal;
    heal.Key = "raid.support.heal.test";
    heal.Source = "adaptive_raid_support";
    heal.ActionPriority = Priority::Mechanic; // a teammate under 50%
    heal.UtilityScore = 0.65f;
    heal.RequiredResources = Uses(Resource::GlobalCooldown, Resource::Cast);
    heal.Attempt = [&healAttempted]()
    {
        healAttempted = true; // TryCastFriendlySpell would StopMoving here
        return Outcome::Submitted("heal_submitted");
    };
    kernel.Submit(std::move(heal));
    Candidate hop;
    hop.Key = ascent.Id.Key();
    hop.Source = ascent.Id.Strategy;
    hop.ActionPriority = ascent.ActionPriority;
    hop.UtilityScore = ascent.Utility;
    hop.RequiredResources = ascent.Resources();
    hop.Attempt = [hopAnswer]() { return hopAnswer; };
    kernel.Submit(std::move(hop));
    kernel.Resolve();
    return healAttempted;
}


// The candidate the dispatch builds from a pillar hold
// (BotWorldPopulationMgrNefarianCandidates.cpp): the fallback beside a
// proposed step, otherwise Mechanic 250. It commits the movement lane (and
// there renews the lease) whenever it runs.
static BotActionArbitration::Candidate HoldCandidate(AdaptiveNefarianPlan const& plan,
    bool withStep, bool& ran)
{
    using namespace BotActionArbitration;
    Candidate stop;
    stop.Key = "adaptive_nefarian:" + std::string(plan.MovementHold);
    stop.Source = "adaptive_nefarian";
    stop.ActionPriority = withStep ? Priority::CombatMovement : Priority::Mechanic;
    stop.UtilityScore = withStep ? 1.0f : 250.0f;
    stop.RequiredResources = Uses(Resource::Movement);
    stop.Attempt = [&ran]() { ran = true; return Outcome::Committed("nefarian_movement_held"); };
    return stop;
}

// One decision: the plan's step (answered `stepAnswer`) and its pillar hold.
static bool HoldRuns(Blackboard const& board, uint32 slot, NativeFacts const& facts,
    BotActionArbitration::Outcome stepAnswer, std::string_view& hold, bool& stepProposed)
{
    using namespace BotActionArbitration;
    AdaptiveNefarianStrategy strategy;
    AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(slot),
        board.FindActor(Bot(slot))->Role, &facts);
    hold = plan.MovementHold;
    stepProposed = plan.Ascent.has_value() || plan.Movement.has_value();
    CHECK(IsPillarHold(plan.MovementHold), "phase 2: the plan carries the pillar hold");
    Kernel kernel;
    kernel.Begin(1000);
    bool ran = false;
    if (plan.Ascent)
    {
        BotNativeAction::Candidate const ascent = AscentCandidate(*plan.Ascent, board, Bot(slot));
        Candidate step;
        step.Key = ascent.Id.Key();
        step.Source = ascent.Id.Strategy;
        step.ActionPriority = ascent.ActionPriority;
        step.UtilityScore = ascent.Utility;
        step.RequiredResources = ascent.Resources();
        step.Attempt = [stepAnswer]() { return stepAnswer; };
        kernel.Submit(std::move(step));
    }
    kernel.Submit(HoldCandidate(plan, stepProposed, ran));
    kernel.Resolve();
    return ran;
}

static void TestPillarHoldKeepsNativeChaseOut()
{
    using BotActionArbitration::Outcome;
    DutyPlan const duty = BuildNefarianDutyPlan(CanonicalBoard());
    // 1. The rogue floating at its swim station while the floor sinks: no
    //    step, the hold runs (native chase toward the prototype is what put
    //    him in the shaft).
    Blackboard sinking = PlatformBoard(0.0f);
    uint8 const roguePillar = uint8(duty.PillarOf(Bot(8)));
    Vector3 station = LocalToWorld(PillarRadial(roguePillar, duty.SlotOf(Bot(8)), SwimStationRadius),
        0.0f, 0.0f);
    station.Z = MagmaSurfaceZ - FloatDepthYards;
    FindPlayer(sinking, 8).Position = station;
    NativeFacts swimmer;
    swimmer.PillarAscentSupported = true;
    std::string_view hold;
    bool stepProposed = false;
    CHECK(HoldRuns(sinking, 8, swimmer, Outcome::Committed("unused"), hold, stepProposed)
        && !stepProposed && HoldReason(hold) == "nefarian_float_hold_for_pillar",
        "at the station: held, no chase");
    // 2. The rogue and both tanks inside their shafts (local z 3-4 within
    //    1.5 yd of the centre): no step at all, held.
    Blackboard lowered = PlatformBoard(PlatformFrame::LoweredOriginZ);
    struct Inside { uint32 Slot; LocalPoint Offset; float LocalZ; };
    for (Inside const& in : { Inside{ 8, { 1.1f, 0.3f }, 3.5f }, Inside{ 1, { -0.4f, 1.2f }, 3.2f },
             Inside{ 2, { 0.2f, -1.4f }, 3.9f } })
    {
        uint8 const pillar = uint8(duty.PillarOf(Bot(in.Slot)));
        FindPlayer(lowered, in.Slot).Position = LocalToWorld({ PillarCenters[pillar].X + in.Offset.X,
            PillarCenters[pillar].Y + in.Offset.Y }, in.LocalZ, PlatformFrame::LoweredOriginZ);
        CHECK(HoldRuns(lowered, in.Slot, swimmer, Outcome::Committed("unused"), hold, stepProposed)
            && !stepProposed && HoldReason(hold) == "nefarian_inside_pillar_column",
            "inside the shaft: no hop or swim through the wall, held");
    }
    // 3. The Ret paladin on the pillar-1 top, not a passenger: the board is
    //    proposed; while the executor refuses it, the hold takes the lane,
    //    and once the board is answered the hold stands aside.
    Blackboard top = PlatformBoard(PlatformFrame::LoweredOriginZ);
    FindPlayer(top, 6).Position = LocalToWorld(PillarSlot(1, 1), PlatformFrame::PillarTopLocalZ,
        PlatformFrame::LoweredOriginZ);
    CHECK(HoldRuns(top, 6, swimmer, Outcome::Retryable("native_liquid_emerge_no_platform_floor"),
        hold, stepProposed) && stepProposed, "a refused board leaves the lane to the hold");
    CHECK(!HoldRuns(top, 6, swimmer, Outcome::Submitted("native_liquid_emerge_submitted"),
        hold, stepProposed) && stepProposed, "an answered board keeps the lane (control)");
}

int main()
{
    using BotActionArbitration::Outcome;
    TestPillarHoldKeepsNativeChaseOut();
    CHECK(!Replay(Outcome::Progressed("native_liquid_hop_in_flight")),
        "mid-hop, the healer's heal never runs (the hop keeps its lanes)");
    CHECK(Replay(Outcome::Retryable("native_liquid_controlled_motion")),
        "control: a retryable answer would have let the heal stop the jump");
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    return failures ? 1 : 0;
}
'''


def test_healer_mid_hop_keeps_the_jump(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PROGRAM)


def test_healer_mid_hop_under_sanitizers(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PROGRAM, sanitize=True)
