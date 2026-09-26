"""A healer in the middle of its hop onto a pillar keeps the jump.

The review: a Disc or Holy healer mid-hop with an injured teammate could run
the raid heal, whose TryCastFriendlySpell stops the member before a cast-time
heal and so cancels the jump over the magma, short of the pillar. The ascent
candidate (BotNefarianAscentIntent.h, Survival priority, movement + GCD +
cast lanes) is answered with progress while the jump runs
(BotTransportLiquidMovement: native_liquid_hop_in_flight), a committed
outcome, so the kernel keeps those lanes and the heal is never attempted in
that tick. Replayed here with the real arbitration kernel.
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

int main()
{
    using BotActionArbitration::Outcome;
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
