"""A member held up by liquid under a transport holds, typed and bounded; it
is never airborne and never moved by ordinary point movement.

Batch 3 (BWD 10N, Nefarian): a paladin revived at its corpse after the
run-back, in the lava pit under the raised platform at (-112.6, -217.1, 2.77).
Settled with no floor underfoot and none within the re-snap band, the
transport logic failed the cohort with transport_member_airborne_without_floor.
Ordinary point movement has no swimming lifecycle and the native liquid stages
only board a transport's own surface, so the swimmer holds (a route walk of
ours is stopped) and the node fails typed with
transport_member_swimming_without_exit after SwimmingHoldMaxMs of observed
time. Header-only replays compiled with g++ like the other transport tests.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_bot_transport_surface_approach import PRELUDE, ROOT, _compile_and_run

RUNTIME = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteNativeRuntime.cpp"
LOGIC = ROOT / "src/server/game/Bots/BotValidationRouteNativeTransportLogic.h"

SWIMMER = r'''
// The batch-3 paladin: alive, revived in the lava under the raised platform
// (stop frame 0 reached), 60.7 yd from the ledge's approach start.
static TransportMemberObservation LavaSwimmer(std::uint64_t now)
{
    TransportMemberObservation o;
    o.Alive = true; o.TransportPresent = true;
    o.ReadyToBoard = true; o.RestRemainingMs = UnboundedRestMs;
    o.DistanceToApproachStart = 60.7f; o.DistanceToBoard = 20.8f;
    o.InLiquid = true; o.NowMs = now;
    return o;
}

[[maybe_unused]] static bool Moves(TransportStep step)
{
    switch (step)
    {
        case TransportStep::Hold: case TransportStep::Stop: case TransportStep::Fail:
            return false;
        default:
            return true;
    }
}
'''


def test_batch3_lava_swimmer_holds_then_fails_typed(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + SWIMMER + r'''
int main()
{
    TransportContract platform;
    CHECK(!Transport(Nefarian, platform));
    // Negative control: the same observation without the liquid evidence is
    // exactly the batch-3 failure.
    TransportMemberState before;
    TransportMemberObservation dry = LavaSwimmer(5000);
    dry.InLiquid = false;
    TransportDecision airborne = DecideTransportStep(platform, dry, before);
    CHECK(airborne.Step == TransportStep::Fail && airborne.Reason == "transport_member_airborne_without_floor");

    // Held up by the lava: hold in place, never an ordinary move, until the
    // bound; then a typed failure instead of the node timeout.
    TransportMemberState state;
    std::uint64_t const start = 5000;
    for (std::uint64_t now = start; now < start + SwimmingHoldMaxMs; now += 250)
    {
        TransportDecision d = DecideTransportStep(platform, LavaSwimmer(now), state);
        CHECK(d.Step == TransportStep::Hold && d.Reason == "transport_member_swimming_waiting");
        CHECK(!ApproachWantsFollowUp(platform, d, state));
    }
    CHECK(state.SwimmingSinceMs == start && state.ResnapMoves == 0 && state.FloorlessObservations == 0);
    TransportDecision last = DecideTransportStep(platform, LavaSwimmer(start + SwimmingHoldMaxMs), state);
    CHECK(last.Step == TransportStep::Fail && last.Reason == "transport_member_swimming_without_exit");
    CHECK(SwimmingHoldMaxMs < platform.TimeoutMs);
    return failures ? 1 : 0;
}
''')


def test_the_bound_counts_observed_time_not_decisions(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + SWIMMER + r'''
int main()
{
    TransportContract platform;
    CHECK(!Transport(Nefarian, platform));
    // Adversarial: every hold loses arbitration (a Rebirth cast takes the
    // tick) and the member is decided again and again at the same time. Only
    // observed time spends the bound; proposals spend nothing.
    TransportMemberState state;
    for (int proposal = 0; proposal < 1000; ++proposal)
        CHECK(DecideTransportStep(platform, LavaSwimmer(20000), state).Reason
            == "transport_member_swimming_waiting");
    CHECK(DecideTransportStep(platform, LavaSwimmer(20000 + SwimmingHoldMaxMs - 1), state).Step
        == TransportStep::Hold);
    CHECK(DecideTransportStep(platform, LavaSwimmer(20000 + SwimmingHoldMaxMs), state).Step
        == TransportStep::Fail);

    // A floor underfoot ends the hold: the next swim starts a new one.
    TransportMemberState shore;
    DecideTransportStep(platform, LavaSwimmer(1000), shore);
    TransportMemberObservation ledge = LavaSwimmer(9000);
    ledge.InLiquid = false; ledge.StaticFloorUnderfoot = true; ledge.DistanceToApproachStart = 0.4f;
    ledge.ReadyToBoard = false;
    // On the ledge after the reset: wait there for the raised stop.
    CHECK(DecideTransportStep(platform, ledge, shore).Reason == "transport_waiting");
    CHECK(shore.SwimmingSinceMs == 0);
    CHECK(DecideTransportStep(platform, LavaSwimmer(10500), shore).Step == TransportStep::Hold);
    CHECK(shore.SwimmingSinceMs == 10500);
    // A death ends it too (the adapter does the same for dead members).
    TransportMemberObservation dead = LavaSwimmer(11000);
    dead.Alive = false;
    CHECK(DecideTransportStep(platform, dead, shore).Reason == "transport_member_dead");
    CHECK(shore.SwimmingSinceMs == 0);
    // Boarding ends it.
    TransportMemberState rescued;
    DecideTransportStep(platform, LavaSwimmer(1000), rescued);
    TransportMemberObservation aboard = LavaSwimmer(2000);
    aboard.OnThisTransport = true;
    CHECK(DecideTransportStep(platform, aboard, rescued).Step == TransportStep::Done);
    CHECK(rescued.SwimmingSinceMs == 0);
    return failures ? 1 : 0;
}
''')


def test_swimmers_are_never_moved_by_ordinary_movement(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + SWIMMER + r'''
int main()
{
    TransportContract platform;
    CHECK(!Transport(Nefarian, platform));
    TransportContract bare;
    CHECK(!Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2, 3], "timeout_ms": 1000000})", bare));
    // Every swimming situation: moving or not, free or not, next to a floor
    // or not, after standing on the platform or not, in any approach phase.
    for (TransportContract const* contract : { &platform, &bare })
        for (int bits = 0; bits < 32; ++bits)
            for (ApproachPhase phase : { ApproachPhase::Idle, ApproachPhase::Walking })
            {
                TransportMemberState state;
                state.Approach = phase;
                state.PlatformFloorSeen = bits & 1;
                TransportMemberObservation o = LavaSwimmer(3000);
                o.Moving = bits & 2; o.MemberNotFree = bits & 4; o.FloorNear = bits & 8;
                o.ReadyToBoard = bits & 16;
                TransportDecision d = DecideTransportStep(*contract, o, state);
                CHECK(!Moves(d.Step));
                CHECK(d.Reason.rfind("transport_member_swimming_", 0) == 0);
                CHECK(state.ResnapMoves == 0 && state.FloorlessObservations == 0);
            }
    // A route walk of ours that reached the liquid is stopped; a controlled
    // effect is left to run its course.
    TransportMemberState walker;
    TransportMemberObservation walking = LavaSwimmer(3000);
    walking.Moving = true;
    CHECK(DecideTransportStep(platform, walking, walker).Reason == "transport_member_swimming_stop");
    walking.MemberNotFree = true;
    CHECK(DecideTransportStep(platform, walking, walker).Reason == "transport_member_swimming_not_free");
    // A fall into the liquid belongs to gravity until it settles.
    TransportMemberState falling;
    TransportMemberObservation fall = LavaSwimmer(3000);
    fall.Falling = true; fall.Moving = true;
    CHECK(DecideTransportStep(platform, fall, falling).Reason.rfind("transport_member_swimming_", 0) != 0);
    CHECK(falling.SwimmingSinceMs == 0);
    return failures ? 1 : 0;
}
''')


def test_liquid_never_masks_a_landing_off_the_platform_or_a_real_stranding(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + SWIMMER + r'''
int main()
{
    TransportContract platform;
    CHECK(!Transport(Nefarian, platform));
    // Adversarial: the member's own ledge drop came down in the lava, off the
    // platform it was proven to land on: the landing rule decides.
    TransportMemberState landed;
    landed.Approach = ApproachPhase::Landed;
    TransportDecision d = DecideTransportStep(platform, LavaSwimmer(3000), landed);
    CHECK(d.Step == TransportStep::Fail && d.Reason == "transport_drop_landed_off_platform");

    // Knocked off the platform into the liquid: held up, not stranded.
    TransportMemberState knocked;
    TransportMemberObservation aboard;
    aboard.Alive = true; aboard.TransportPresent = true; aboard.TransportFloorUnderfoot = true;
    aboard.DistanceToBoard = 0.2f;
    CHECK(DecideTransportStep(platform, aboard, knocked).Step == TransportStep::Board);
    CHECK(knocked.PlatformFloorSeen);
    for (std::uint64_t now : { 1000u, 1200u, 1400u, 1600u, 2000u })
        CHECK(DecideTransportStep(platform, LavaSwimmer(now), knocked).Reason
            == "transport_member_swimming_waiting");
    CHECK(knocked.FloorlessObservations == 0);
    // Negative control: with no floor and no liquid under it after standing
    // on the platform a member is still stranded, typed.
    TransportMemberState stranded;
    DecideTransportStep(platform, aboard, stranded);
    TransportDecision last;
    for (std::uint64_t now : { 1000u, 1200u, 1400u, 1600u })
    {
        TransportMemberObservation air = LavaSwimmer(now);
        air.InLiquid = false;
        last = DecideTransportStep(platform, air, stranded);
    }
    CHECK(last.Step == TransportStep::Fail && last.Reason == "transport_member_stranded_without_floor");
    // Negative control: a dry probe miss next to a floor still re-snaps.
    TransportMemberState dry;
    TransportMemberObservation near = LavaSwimmer(3000);
    near.InLiquid = false; near.FloorNear = true;
    d = DecideTransportStep(platform, near, dry);
    CHECK(d.Step == TransportStep::MoveToApproachStart && d.Reason == "transport_member_floor_unverified_resnap");
    return failures ? 1 : 0;
}
''')


def test_adapter_reads_the_native_liquid_status_and_moves_nothing() -> None:
    text = RUNTIME.read_text(encoding="utf-8")
    run = text[text.index("void RunTransport(Input const& input"):]
    run = run[:run.index("\n}\n")]
    guard = run.index("if (!observation.StaticFloorUnderfoot && !observation.TransportFloorUnderfoot)\n    {")
    liquid = run.index("observation.InLiquid = bot->IsInWater();")
    decide = run.index("DecideTransportStep(contract, observation, member)")
    assert guard < liquid < decide
    # Dead members never reach the decision: the hold reads the life edges.
    assert run.index("if (!bot->IsAlive())\n        return;") < run.index("TransportMemberState& member")
    assert run.index("observation.LifeGeneration = input.LifeGeneration;") < decide
    # No swim-out: no path proof, no swim movement of any kind.
    assert "CompleteNativePath" not in text and "SwimOutPath" not in text
    logic = LOGIC.read_text(encoding="utf-8")
    swimming = logic[logic.index("inline TransportDecision DecideSwimming("):]
    swimming = swimming[:swimming.index("\n}\n")]
    assert "TransportStep::Move" not in swimming
    assert "SwimOut" not in logic
    assert len(text.splitlines()) < 1000


BOUNDARY = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelPreparation.cpp"
RECOVERY = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteNativeRecovery.cpp"


def test_a_member_revived_after_the_bound_gets_a_fresh_hold(tmp_path: Path) -> None:
    # Through the caller boundary: RunTransport never sees a dead member, and
    # the kernel builder reads the life generation from the native registry.
    _compile_and_run(tmp_path, PRELUDE.replace("#include <cmath>", "#include \"Bots/BotNativeLifeEvents.h\"\n#include <cmath>")
        + SWIMMER + r"""
struct Member
{
    std::uint32_t Guid = 11005009;
    bool Alive = true;
};

// The kernel builder (Input::LifeGeneration) and RunTransport (dead members
// return before any observation); `plumbed` false is the v2 adapter.
static bool Deliver(TransportContract const& contract, Member const& member,
    BotNativeLifeEvents::Scope const& scope, std::uint64_t now, TransportMemberState& state,
    bool plumbed, TransportDecision& out)
{
    BotNativeLifeEvents::Observe(member.Guid, scope, member.Alive, now);
    if (!member.Alive)
        return false;
    BotNativeLifeEvents::Counts const life = BotNativeLifeEvents::Get(member.Guid, scope);
    TransportMemberObservation o = LavaSwimmer(now);
    o.LifeGeneration = plumbed ? life.Deaths + life.Resurrections : 0;
    out = DecideTransportStep(contract, o, state);
    return true;
}

static TransportDecision Replay(bool plumbed, char const* cohort)
{
    TransportContract platform;
    CHECK(!Transport(Nefarian, platform));
    BotNativeLifeEvents::BeginLifecycle(cohort);
    BotNativeLifeEvents::Scope const scope = BotNativeLifeEvents::LifecycleScope(cohort, 1);
    Member paladin;
    TransportMemberState state;
    TransportDecision d;
    // Holding in the lava for 5 s.
    for (std::uint64_t now = 1000; now <= 6000; now += 500)
    {
        CHECK(Deliver(platform, paladin, scope, now, state, plumbed, d));
        CHECK(d.Reason == "transport_member_swimming_waiting");
    }
    // Killed by a lethal hit; dead for 20 s: nothing is delivered.
    BotNativeLifeEvents::ObserveLethal(paladin.Guid, scope, 6200);
    paladin.Alive = false;
    for (std::uint64_t now = 6500; now < 26500; now += 500)
        CHECK(!Deliver(platform, paladin, scope, now, state, plumbed, d));
    // Revived at its corpse in the lava, long past the 10 s bound.
    paladin.Alive = true;
    CHECK(Deliver(platform, paladin, scope, 26500, state, plumbed, d));
    return d;
}

int main()
{
    TransportDecision const fresh = Replay(true, "swim_fresh");
    CHECK(fresh.Step == TransportStep::Hold && fresh.Reason == "transport_member_swimming_waiting");
    // Negative control: without the life generation the stale hold fails at once.
    TransportDecision const stale = Replay(false, "swim_stale");
    CHECK(stale.Step == TransportStep::Fail && stale.Reason == "transport_member_swimming_without_exit");
    // The fresh hold is still bounded.
    TransportContract platform;
    CHECK(!Transport(Nefarian, platform));
    BotNativeLifeEvents::BeginLifecycle("swim_bound");
    BotNativeLifeEvents::Scope const scope = BotNativeLifeEvents::LifecycleScope("swim_bound", 1);
    Member member;
    TransportMemberState state;
    TransportDecision d;
    Deliver(platform, member, scope, 1000, state, true, d);
    BotNativeLifeEvents::ObserveLethal(member.Guid, scope, 1500);
    Deliver(platform, member, scope, 2000, state, true, d);  // revived: generation 2
    CHECK(d.Reason == "transport_member_swimming_waiting" && state.SwimmingSinceMs == 2000);
    Deliver(platform, member, scope, 2000 + SwimmingHoldMaxMs, state, true, d);
    CHECK(d.Reason == "transport_member_swimming_without_exit");
    return failures ? 1 : 0;
}
""")


def test_the_life_generation_reaches_every_transport_runtime() -> None:
    builder = BOUNDARY.read_text(encoding="utf-8")
    assert ("BotNativeLifeEvents::Counts const life = BotNativeLifeEvents::Get(\n"
            "                        context.Bot->GetGUID().GetCounter(),\n"
            "                        BotNativeLifeEvents::LifecycleScope(Cohort().Id, Cohort().AttemptId));\n"
            "                    nativeInput.LifeGeneration = life.Deaths + life.Resurrections;") in builder
    assert builder.index("nativeInput.LifeGeneration") < builder.index("NativeRoute::Callbacks nativeCallbacks;")
    # Recovery rides run on a copy of the same input.
    recovery = RECOVERY.read_text(encoding="utf-8")
    assert "Input riders = input;" in recovery
    assert "ops.Ride(ArrivalOnly(ride) ? ArrivalRiders(input, views, boardZ, exitZ) : input," in recovery
    runtime = RUNTIME.read_text(encoding="utf-8")
    assert runtime.count("RunTransport(") == 4  # definition, recovery ride, node (twice)
