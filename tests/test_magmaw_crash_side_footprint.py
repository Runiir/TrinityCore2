"""Massive Crash side is decided once per crash from the whole native lit set.

The geometry is the native Blackwing Descent spawn set (world DB creature rows
for Room Stalker 47196 and the two Massive Crash dummies 47330) lit by the
native rule in instance_blackwing_descent.cpp: every stalker inside the chosen
dummy's HasInArc(pi/4) arc, i.e. within +/-22.5 degrees of its facing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = (
    "src/server/game",
    "src/server/game/Entities/Object",
    "src/common",
    "src/common/Utilities",
    "src/common/Logging",
)

FIXTURE = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawCrashSideMovement.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <optional>
#include <set>
#include <vector>

using namespace BotEncounter;

namespace
{
constexpr float Pi = 3.14159265358979f;
// World DB spawns (map 669): Room Stalker 47196 guids 250063-250100.
constexpr float Stalkers[][3] = {
    {-301.389f,-48.184f,212.725f},{-349.906f,-62.3403f,215.352f},
    {-322.063f,-67.8993f,213.49f},{-295.868f,-67.7691f,213.633f},
    {-319.583f,-79.7934f,213.529f},{-334.538f,-71.0017f,213.488f},
    {-341.177f,-52.6892f,212.832f},{-294.569f,-56.066f,213.071f},
    {-307.99f,-75.2205f,214.026f},{-344.514f,-73.4253f,214.168f},
    {-317.28f,-58.316f,213.071f},{-304.632f,-57.7813f,212.651f},
    {-327.238f,-78.3177f,213.984f},{-328.76f,-62.691f,212.579f},
    {-350.08f,-60.0764f,214.058f},{-332.335f,-88.3212f,213.992f},
    {-338.257f,-62.4462f,212.957f},{-304.181f,-90.1806f,214.165f},
    {-328.618f,-50.2396f,211.982f},{-323.554f,-90.3785f,214.027f},
    {-321.983f,-54.4618f,212.152f},{-351.951f,-84.474f,214.022f},
    {-313.292f,-87.1059f,214.17f},{-328.802f,-24.9653f,211.336f},
    {-307.531f,-35.4375f,211.815f},{-333.566f,-33.6076f,211.458f},
    {-307.519f,-41.3299f,211.779f},{-342.142f,-80.7257f,214.04f},
    {-322.295f,-38.5278f,211.791f},{-298.063f,-79.6476f,214.023f},
    {-313.043f,-67.6042f,213.106f},{-308.677f,-26.7292f,211.418f},
    {-296.743f,-42.9635f,211.961f},{-314.66f,-44.7049f,212.787f},
    {-346.333f,-31.7135f,211.643f},{-311.465f,-48.5972f,212.807f},
    {-317.934f,-29.7604f,211.392f},{-337.375f,-43.6615f,212.085f}};
struct Dummy { float X, Y, O; };
// Massive Crash dummies 47330: 250061 hit the whole ranged stack in the
// retained kills, 250060 hit only one to three targets.
constexpr Dummy RaidWide{-288.59f, -14.8472f, 3.64774f};
constexpr Dummy Narrow{-294.736f, -11.4306f, 4.62512f};
constexpr Vector3 Boss{-302.467f, -31.7101f, 210.848f};
// The retained ranged support point is 8 yd from Magmaw.
constexpr Vector3 Support{-308.9f, -36.5f, 211.815f};

float RelativeDegrees(Dummy const& dummy, Vector3 const& point)
{
    float angle = std::atan2(point.Y - dummy.Y, point.X - dummy.X) - dummy.O;
    while (angle > Pi) angle -= 2.0f * Pi;
    while (angle < -Pi) angle += 2.0f * Pi;
    return angle * 180.0f / Pi;
}

// Native: every hit lay within 23.5 degrees, every miss at 25.6 or more.
bool InsideNativeCone(Dummy const& dummy, Vector3 const& point)
{
    return std::fabs(RelativeDegrees(dummy, point)) <= 24.0f;
}

std::vector<ActorSnapshot> Light(Dummy const& dummy, bool all = false)
{
    std::vector<ActorSnapshot> lit;
    uint32 counter = 0;
    for (auto const& stalker : Stalkers)
    {
        ++counter;
        ActorSnapshot actor;
        actor.Guid = ObjectGuid(HighGuid::Unit, 47196, 250062 + counter);
        actor.Entry = 47196;
        actor.Alive = true;
        actor.Position = { stalker[0], stalker[1], stalker[2] };
        if (all || std::fabs(RelativeDegrees(dummy, actor.Position)) <= 22.5f)
            lit.push_back(actor);
    }
    return lit;
}

MagmawCrashFootprint Footprint(std::vector<ActorSnapshot> const& lit,
    std::vector<Vector3> const& inside = {})
{
    std::vector<ActorSnapshot const*> pointers;
    for (ActorSnapshot const& actor : lit)
        pointers.push_back(&actor);
    return BuildMagmawCrashFootprint(pointers, inside);
}

float Travel(Vector3 const& first, Vector3 const& second)
{
    return std::hypot(first.X - second.X, first.Y - second.Y);
}

// Independent statement of the review's escape rule: the side candidates,
// then each hull edge's nearest point stepped outward by margin + 1 yd; the
// shortest point within reach that clears coverage and was not rejected.
std::optional<Vector3> ExpectedEscape(MagmawCrashFootprint const& footprint,
    Vector3 const& actor, std::vector<Vector3> candidates, float floorZ,
    std::optional<Vector3> const& rejected)
{
    std::size_t const count = footprint.Hull.size();
    for (std::size_t index = 0; index < count; ++index)
    {
        Vector3 const& a = footprint.Hull[index];
        Vector3 const& b = footprint.Hull[(index + 1) % count];
        float const ex = b.X - a.X;
        float const ey = b.Y - a.Y;
        float const length = std::hypot(ex, ey);
        float t = ((actor.X - a.X) * ex + (actor.Y - a.Y) * ey)
            / (length * length);
        t = std::min(1.0f, std::max(0.0f, t));
        float const step = MagmawCrashCoverageMargin + 1.0f;
        candidates.push_back({ a.X + t * ex + ey / length * step,
            a.Y + t * ey - ex / length * step, floorZ });
    }
    std::optional<Vector3> best;
    float bestTravel = MagmawCrashEscapeReach;
    for (Vector3 const& candidate : candidates)
        if (!MagmawCrashCovers(footprint, candidate)
            && Travel(actor, candidate) <= bestTravel
            && !(rejected && Travel(candidate, *rejected)
                <= MagmawCrashRejectedPointTolerance))
        {
            best = candidate;
            bestTravel = Travel(actor, candidate);
        }
    return best;
}

struct Anchors { Vector3 Support, Left, Right; };
Anchors RangedAnchors()
{
    float dx = Support.X - Boss.X;
    float dy = Support.Y - Boss.Y;
    float const length = std::hypot(dx, dy);
    dx /= length;
    dy /= length;
    Vector3 const center{Boss.X + dx * 30.0f, Boss.Y + dy * 30.0f, Support.Z};
    Vector3 const lateral{-dy * 18.0f, dx * 18.0f, 0.0f};
    return { { Boss.X + dx * 8.0f, Boss.Y + dy * 8.0f, Support.Z },
        { center.X + lateral.X, center.Y + lateral.Y, Support.Z },
        { center.X - lateral.X, center.Y - lateral.Y, Support.Z } };
}

ActorSnapshot Bot(Vector3 position)
{
    ActorSnapshot bot;
    bot.Guid = ObjectGuid(HighGuid::Player, uint32(30001));
    bot.Alive = true;
    bot.Role = "dps";
    bot.Position = position;
    return bot;
}

Blackboard Board()
{
    Blackboard board;
    board.CurrentScope = Scope{ "crash-side", 11, 0, 4,
        "bwd.magmaw.encounter", 669, 2, "magmaw" };
    board.Revision = 40;
    board.ObservedAtMs = 99000;
    return board;
}

Vector3 MoveTarget(MagmawCrashSideProposal const& proposal)
{
    auto const* move = std::get_if<BotNativeAction::Move>(
        &proposal.Movement->Action);
    assert(move);
    return { move->X, move->Y, move->Z };
}
}

int main()
{
    Anchors const anchors = RangedAnchors();
    Blackboard const board = Board();
    std::vector<ActorSnapshot> const raidWide = Light(RaidWide);
    std::vector<ActorSnapshot> const narrow = Light(Narrow);
    assert(raidWide.size() == 20 && narrow.size() == 18);
    MagmawCrashFootprint const wide = Footprint(raidWide);
    MagmawCrashFootprint const tight = Footprint(narrow);
    assert(wide.Valid && wide.HasCoverage() && wide.LitCount == 20);
    assert(tight.Valid && tight.HasCoverage() && tight.LitCount == 18);
    // Identity is the lowest raw GUID of the lit set, independent of order.
    std::vector<ActorSnapshot> reversed(raidWide.rbegin(), raidWide.rend());
    assert(Footprint(reversed).Identity == wide.Identity);
    assert(Footprint(reversed).Centroid.X == wide.Centroid.X);

    // Retained zig-zag of fid16 kill 1 (Balance, 94.7-99.9 s) plus support.
    std::vector<Vector3> const path{ Support, {-313.3f,-30.7f,211.8f},
        {-311.5f,-33.1f,211.8f}, {-306.8f,-39.5f,211.8f},
        {-309.3f,-38.3f,211.8f}, {-314.3f,-33.0f,211.8f},
        {-313.7f,-30.0f,211.8f}, {-305.1f,-41.8f,211.8f} };
    // The lit set straddles the anchor midline, so a footprint taken from the
    // lit stalker nearest a bot can name either side depending on where the
    // bot stands; the one nearest the support point is a near tie.
    std::set<float> perStalkerSides;
    for (ActorSnapshot const& stalker : raidWide)
        perStalkerSides.insert(ResolveMagmawCrashSideMovement(anchors.Support,
            stalker.Position, anchors.Support, anchors.Left, anchors.Right,
            false, 8.0f).UnsafeSideAnchor.X);
    assert(perStalkerSides.size() == 2);
    ActorSnapshot const* supportNearest = nullptr;
    for (ActorSnapshot const& stalker : raidWide)
        if (!supportNearest || std::hypot(stalker.Position.X - Support.X,
                stalker.Position.Y - Support.Y)
            < std::hypot(supportNearest->Position.X - Support.X,
                supportNearest->Position.Y - Support.Y))
            supportNearest = &stalker;
    assert(std::fabs(std::hypot(supportNearest->Position.X - anchors.Left.X,
        supportNearest->Position.Y - anchors.Left.Y)
        - std::hypot(supportNearest->Position.X - anchors.Right.X,
            supportNearest->Position.Y - anchors.Right.Y)) < 0.1f);
    // The whole-set footprint names one side at every retained position.
    std::set<float> footprintSides;
    for (Vector3 const& position : path)
        footprintSides.insert(ResolveMagmawCrashSideMovement(position,
            wide.Centroid, anchors.Support, anchors.Left, anchors.Right,
            false, 8.0f).UnsafeSideAnchor.X);
    assert(footprintSides.size() == 1);

    // Raid-wide crash: support is inside both the native cone and the model;
    // the chosen evade point is outside both.
    MagmawEventMovementTransitionState state;
    ActorSnapshot bot = Bot(anchors.Support);
    assert(InsideNativeCone(RaidWide, anchors.Support));
    assert(MagmawCrashCovers(wide, anchors.Support));
    MagmawCrashSideProposal first = ProposeMagmawCrashSideMovement(board, bot,
        wide, anchors.Support, anchors.Left, anchors.Right, false, 8.0f,
        &state, 450.0f);
    assert(first.CoverageModel && !first.Hold && first.Movement);
    assert(first.Movement->ActionPriority
        == BotActionArbitration::Priority::Survival);
    Vector3 const wideDestination = MoveTarget(first);
    assert(!InsideNativeCone(RaidWide, wideDestination));
    assert(RelativeDegrees(RaidWide, wideDestination) > 30.0f);
    assert(!MagmawCrashCovers(wide, wideDestination));
    assert(std::fabs(std::hypot(wideDestination.X - anchors.Support.X,
        wideDestination.Y - anchors.Support.Y) - 8.0f) < 0.01f);
    uint64 const intent = first.Movement->Id.EventGeneration;

    // Every later tick along the retained zig-zag keeps one intent and point.
    for (Vector3 const& position : path)
    {
        state.ObserveArrival(position);
        ActorSnapshot moved = Bot(position);
        MagmawCrashSideProposal next = ProposeMagmawCrashSideMovement(board,
            moved, wide, anchors.Support, anchors.Left, anchors.Right, false,
            8.0f, &state, 450.0f);
        if (!MagmawCrashCovers(wide, position))
            continue;
        assert(next.Movement && next.Movement->Id.EventGeneration == intent);
        Vector3 const retained = MoveTarget(next);
        assert(retained.X == wideDestination.X
            && retained.Y == wideDestination.Y);
    }

    // Crossing the anchor midline is not arrival: this point is on the safe
    // side of the midline yet still inside the native cone and the model.
    Vector3 const pastMidline{-307.6f, -37.9f, 211.815f};
    assert(!ResolveMagmawCrashSideMovement(pastMidline, wide.Centroid,
        anchors.Support, anchors.Left, anchors.Right, false, 8.0f).ActorUnsafe);
    assert(InsideNativeCone(RaidWide, pastMidline));
    MagmawEventMovementTransitionState midlineState;
    MagmawCrashSideProposal midline = ProposeMagmawCrashSideMovement(board,
        Bot(pastMidline), wide, anchors.Support, anchors.Left, anchors.Right,
        false, 8.0f, &midlineState, 450.0f);
    assert(!midline.Hold && midline.Movement);
    midlineState.ObserveArrival(pastMidline);
    assert(midlineState.ActiveLethal());

    // Arrival at the cleared point completes the task and then holds there.
    state.ObserveArrival(wideDestination);
    assert(!state.ActiveLethal());
    MagmawCrashSideProposal arrived = ProposeMagmawCrashSideMovement(board,
        Bot(wideDestination), wide, anchors.Support, anchors.Left,
        anchors.Right, false, 8.0f, &state, 450.0f);
    assert(arrived.Hold && !arrived.NoSafeSpot && !arrived.Movement);

    // Narrow crash: the opposite side is chosen and is outside its cone.
    MagmawEventMovementTransitionState narrowState;
    MagmawCrashSideProposal narrowMove = ProposeMagmawCrashSideMovement(board,
        Bot(anchors.Support), tight, anchors.Support, anchors.Left,
        anchors.Right, false, 8.0f, &narrowState, 450.0f);
    assert(narrowMove.Movement);
    Vector3 const narrowDestination = MoveTarget(narrowMove);
    assert(!InsideNativeCone(Narrow, narrowDestination));
    assert(RelativeDegrees(Narrow, narrowDestination) < -35.0f);
    assert(!MagmawCrashCovers(tight, narrowDestination));
    assert(std::hypot(narrowDestination.X - wideDestination.X,
        narrowDestination.Y - wideDestination.Y) > 15.0f);

    // Fixed-lane baiters keep their lateral anchor, chosen from the same
    // footprint, and that anchor is outside the raid-wide native cone.
    MagmawCrashSideProposal lane = ProposeMagmawCrashSideMovement(board,
        Bot(anchors.Right), wide, anchors.Support, anchors.Left, anchors.Right,
        true, 8.0f, nullptr, 450.0f);
    assert(lane.Movement);
    Vector3 const laneDestination = MoveTarget(lane);
    assert(laneDestination.X == anchors.Left.X
        && laneDestination.Y == anchors.Left.Y);
    assert(!InsideNativeCone(RaidWide, laneDestination));

    // Review item 1: a covered side point is not a reason to hold while a
    // nearby point clears. Lighting the three stalkers around the raid-wide
    // evade point covers it (and the opposite side stays inside the cone).
    std::vector<ActorSnapshot> blocked = raidWide;
    for (ActorSnapshot const& stalker : narrow)
        for (float const x : { -307.519f, -301.389f, -296.743f })
            if (stalker.Position.X == x)
                blocked.push_back(stalker);
    MagmawCrashFootprint const blockedFootprint = Footprint(blocked);
    MagmawCrashSideMovement const blockedSide = ResolveMagmawCrashSideMovement(
        anchors.Support, blockedFootprint.Centroid, anchors.Support,
        anchors.Left, anchors.Right, false, 8.0f);
    assert(blockedSide.SafeDestinationValid);
    assert(MagmawCrashCovers(blockedFootprint, blockedSide.SafeDestination));
    Vector3 const opposite{ 2.0f * anchors.Support.X
        - blockedSide.SafeDestination.X, 2.0f * anchors.Support.Y
        - blockedSide.SafeDestination.Y, anchors.Support.Z };
    assert(MagmawCrashCovers(blockedFootprint, opposite));
    MagmawEventMovementTransitionState blockedState;
    MagmawCrashSideProposal escaped = ProposeMagmawCrashSideMovement(board,
        Bot(anchors.Support), blockedFootprint, anchors.Support, anchors.Left,
        anchors.Right, false, 8.0f, &blockedState, 450.0f);
    assert(escaped.CoverageModel && !escaped.Hold && escaped.Movement);
    Vector3 const outward = MoveTarget(escaped);
    assert(!MagmawCrashCovers(blockedFootprint, outward));
    assert(Travel(anchors.Support, outward) <= MagmawCrashEscapeReach);
    std::optional<Vector3> const expected = ExpectedEscape(blockedFootprint,
        anchors.Support, { opposite, blockedSide.SafeSideAnchor,
            blockedSide.UnsafeSideAnchor }, anchors.Support.Z, std::nullopt);
    assert(expected && Travel(*expected, outward) < 0.01f);

    // An invalid side point (zero-length side axis) also falls through to
    // the outward steps rather than holding inside the cone.
    MagmawEventMovementTransitionState degenerateState;
    MagmawCrashSideProposal degenerate = ProposeMagmawCrashSideMovement(board,
        Bot(anchors.Support), wide, anchors.Support, anchors.Left,
        anchors.Left, false, 8.0f, &degenerateState, 450.0f);
    assert(degenerate.Movement && !degenerate.NoSafeSpot);
    Vector3 const degenerateTarget = MoveTarget(degenerate);
    assert(!MagmawCrashCovers(wide, degenerateTarget));
    std::optional<Vector3> const degenerateExpected = ExpectedEscape(wide,
        anchors.Support, { anchors.Left }, anchors.Support.Z, std::nullopt);
    assert(degenerateExpected
        && Travel(*degenerateExpected, degenerateTarget) < 0.01f);

    // Without ranged anchors the outward steps remain, on the actor's floor.
    MagmawEventMovementTransitionState anchorlessState;
    MagmawCrashSideProposal anchorless =
        ProposeMagmawCrashSideMovementWithoutAnchors(board,
            Bot(anchors.Support), wide, &anchorlessState, 450.0f);
    assert(anchorless.CoverageModel && anchorless.Movement);
    Vector3 const anchorlessTarget = MoveTarget(anchorless);
    assert(!MagmawCrashCovers(wide, anchorlessTarget));
    assert(anchorlessTarget.Z == anchors.Support.Z);
    MagmawCrashSideProposal anchorlessClear =
        ProposeMagmawCrashSideMovementWithoutAnchors(board,
            Bot(wideDestination), wide, nullptr, 450.0f);
    assert(anchorlessClear.Hold && !anchorlessClear.Movement);

    // No reachable point outside the crash: a lit field far larger than the
    // escape reach around the actor. Hold and keep casting.
    std::vector<ActorSnapshot> field;
    uint32 fieldCounter = 0;
    for (float x = -380.0f; x <= -240.0f; x += 10.0f)
        for (float y = -110.0f; y <= 30.0f; y += 10.0f)
        {
            ActorSnapshot stalker;
            stalker.Guid = ObjectGuid(HighGuid::Unit, 47196, 260000 + ++fieldCounter);
            stalker.Entry = 47196;
            stalker.Alive = true;
            stalker.Position = { x, y, 211.815f };
            field.push_back(stalker);
        }
    MagmawCrashFootprint const everywhere = Footprint(field);
    MagmawEventMovementTransitionState trappedState;
    for (Vector3 const& position : path)
    {
        MagmawCrashSideProposal trapped = ProposeMagmawCrashSideMovement(board,
            Bot(position), everywhere, anchors.Support, anchors.Left,
            anchors.Right, false, 8.0f, &trappedState, 450.0f);
        assert(trapped.Hold && trapped.NoSafeSpot && !trapped.Movement);
        assert(!trappedState.ActiveLethal());
    }

    // Review item 2: the observed crash dummy closes the cone tip. It extends
    // the covered hull only; the side decision and identity are unchanged.
    Vector3 const dummyPosition{ RaidWide.X, RaidWide.Y, 211.257f };
    MagmawCrashFootprint const tipped = Footprint(raidWide, { dummyPosition });
    assert(tipped.Identity == wide.Identity);
    assert(tipped.Centroid.X == wide.Centroid.X
        && tipped.Centroid.Y == wide.Centroid.Y);
    assert(std::any_of(tipped.Hull.begin(), tipped.Hull.end(),
        [&dummyPosition](Vector3 const& vertex)
        {
            return vertex.X == dummyPosition.X && vertex.Y == dummyPosition.Y;
        }));
    Vector3 const tip{ (RaidWide.X + Boss.X) / 2.0f,
        (RaidWide.Y + Boss.Y) / 2.0f, 211.0f };
    assert(InsideNativeCone(RaidWide, tip));
    assert(!MagmawCrashCovers(wide, tip));
    assert(MagmawCrashCovers(tipped, tip));
    // Known-inside points never create coverage without a lit area.
    assert(!Footprint(std::vector<ActorSnapshot>(raidWide.begin(),
        raidWide.begin() + 2), { dummyPosition, Boss }).HasCoverage());

    // Review item 3: a permanent native path rejection of the exact crash
    // intent retires it; the next proposal falls through to an alternative
    // instead of repeating the unreachable point.
    MagmawEventMovementTransitionState rejectState;
    ActorSnapshot const rejectBot = Bot(anchors.Support);
    MagmawCrashSideProposal planned = ProposeMagmawCrashSideMovement(board,
        rejectBot, wide, anchors.Support, anchors.Left, anchors.Right, false,
        8.0f, &rejectState, 450.0f);
    Vector3 const unreachable = MoveTarget(planned);
    uint64 const plannedIntent = planned.Movement->Id.EventGeneration;
    assert(!ObserveMagmawCrashEvadeNativeRejection(rejectState, rejectBot.Guid,
        plannedIntent, unreachable, "magmaw_movement_executor_unavailable"));
    assert(!ObserveMagmawCrashEvadeNativeRejection(rejectState, rejectBot.Guid,
        plannedIntent + 1, unreachable, "route_destination_unreachable"));
    assert(!ObserveMagmawCrashEvadeNativeRejection(rejectState,
        ObjectGuid(HighGuid::Player, uint32(30099)), plannedIntent,
        unreachable, "route_destination_unreachable"));
    assert(!ObserveMagmawCrashEvadeNativeRejection(rejectState, rejectBot.Guid,
        plannedIntent, { unreachable.X + 3.0f, unreachable.Y, unreachable.Z },
        "route_destination_unreachable"));
    assert(rejectState.ActiveLethal());
    assert(ObserveMagmawCrashEvadeNativeRejection(rejectState, rejectBot.Guid,
        plannedIntent, unreachable, "route_destination_unreachable"));
    assert(!rejectState.ActiveLethal());
    MagmawCrashSideProposal fallback = ProposeMagmawCrashSideMovement(board,
        rejectBot, wide, anchors.Support, anchors.Left, anchors.Right, false,
        8.0f, &rejectState, 450.0f);
    assert(fallback.Movement);
    Vector3 const alternative = MoveTarget(fallback);
    assert(Travel(alternative, unreachable) > MagmawCrashRejectedPointTolerance);
    assert(!MagmawCrashCovers(wide, alternative));
    assert(fallback.Movement->Id.EventGeneration != plannedIntent);
    std::optional<Vector3> const alternativeExpected = ExpectedEscape(wide,
        anchors.Support, { {
            2.0f * anchors.Support.X - unreachable.X,
            2.0f * anchors.Support.Y - unreachable.Y, anchors.Support.Z },
            anchors.Left, anchors.Right }, anchors.Support.Z, unreachable);
    assert(alternativeExpected
        && Travel(*alternativeExpected, alternative) < 0.01f);
    // The alternative's own rejection is not repeated on the next tick.
    assert(ObserveMagmawCrashEvadeNativeRejection(rejectState, rejectBot.Guid,
        fallback.Movement->Id.EventGeneration, alternative,
        "route_destination_partial_path"));
    MagmawCrashSideProposal third = ProposeMagmawCrashSideMovement(board,
        rejectBot, wide, anchors.Support, anchors.Left, anchors.Right, false,
        8.0f, &rejectState, 450.0f);
    assert(!third.Movement || Travel(MoveTarget(third), alternative)
        > MagmawCrashRejectedPointTolerance);
    // Other mechanics are never retired by the crash hook, and a genuine
    // arrival is not an abandoned destination.
    MagmawEventMovementTransitionState pillarState;
    auto const* pillar = pillarState.RetainLethal(
        ObjectGuid(HighGuid::Unit, 41843, uint32(5)), rejectBot.Guid,
        "pillar_evade", unreachable);
    assert(pillar && !ObserveMagmawCrashEvadeNativeRejection(pillarState,
        rejectBot.Guid, pillar->IntentId, unreachable,
        "route_destination_unreachable"));
    assert(!MagmawCrashAbandonedDestination(&state, wide.Identity,
        Bot(wideDestination).Guid, wideDestination));

    // Fewer than three lit stalkers: no coverage model, historical rule.
    std::vector<ActorSnapshot> single{ raidWide.front() };
    MagmawCrashFootprint const lone = Footprint(single);
    assert(lone.Valid && !lone.HasCoverage());
    assert(lone.Identity == single.front().Guid);
    assert(lone.Centroid.X == single.front().Position.X);
    MagmawCrashSideMovement const legacy = ResolveMagmawCrashSideMovement(
        anchors.Support, lone.Centroid, anchors.Support, anchors.Left,
        anchors.Right, false, 8.0f);
    MagmawEventMovementTransitionState legacyState;
    MagmawCrashSideProposal legacyProposal = ProposeMagmawCrashSideMovement(
        board, Bot(anchors.Support), lone, anchors.Support, anchors.Left,
        anchors.Right, false, 8.0f, &legacyState, 450.0f);
    assert(!legacyProposal.CoverageModel);
    assert(legacyProposal.Hold == !legacy.ActorUnsafe);
    assert(bool(legacyProposal.Movement) == legacy.ActorUnsafe);
    assert(!Footprint({}).Valid);
    std::vector<ActorSnapshot> collinear(raidWide.begin(), raidWide.begin() + 2);
    collinear.push_back(collinear.front());
    assert(!Footprint(collinear).HasCoverage());

    // Retained native Massive Crash outcomes (bundle1/bundle2/fid16). Every
    // hit, including the four nearest each cone edge, is covered; the ranged
    // stack that the narrow crash missed is clear.
    struct Observation { bool Wide; float X, Y; bool Hit; };
    Observation const observations[] = {
        { true, -308.87f, -41.24f, true }, { true, -309.53f, -40.92f, true },
        { true, -311.62f, -42.70f, true }, { true, -310.07f, -40.22f, true },
        { true, -313.70f, -30.00f, true }, { true, -312.30f, -36.30f, true },
        { false, -307.58f, -37.12f, true }, { false, -309.91f, -41.67f, true },
        { false, -294.85f, -43.13f, true }, { false, -309.97f, -47.13f, true },
        { false, -310.95f, -34.07f, false }, { false, -311.21f, -33.71f, false },
        { false, -311.30f, -33.59f, false }, { false, -311.43f, -33.41f, false } };
    for (Observation const& observed : observations)
    {
        Vector3 const point{ observed.X, observed.Y, 211.815f };
        MagmawCrashFootprint const& footprint = observed.Wide ? wide : tight;
        assert(MagmawCrashCovers(footprint, point) == observed.Hit);
        assert(InsideNativeCone(observed.Wide ? RaidWide : Narrow, point)
            == observed.Hit);
    }
    // The only two raid-wide misses (Survival 25.6 deg, Elemental 27.5 deg)
    // lie 4.4-4.7 yd outside the hull: the margin deliberately counts them as
    // covered, so the model errs toward moving, never toward holding in a hit.
    for (Vector3 const& miss : { Vector3{-320.34f, -59.55f, 211.815f},
             Vector3{-305.78f, -40.84f, 211.815f} })
    {
        assert(!InsideNativeCone(RaidWide, miss));
        assert(MagmawCrashCovers(wide, miss));
    }
    return 0;
}
'''


def test_magmaw_crash_side_decides_once_per_crash_and_holds_without_escape(
    tmp_path: Path,
) -> None:
    source = tmp_path / "magmaw_crash_side_footprint.cpp"
    binary = tmp_path / "magmaw_crash_side_footprint"
    source.write_text(FIXTURE, encoding="utf-8")
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         *[arg for path in INCLUDES for arg in ("-I", str(ROOT / path))],
         str(source), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_crash_side_headers_stay_below_module_size_limit() -> None:
    folder = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw"
    for name in ("BotMagmawCrashSideMovement.h", "BotAdaptiveMagmawStrategyHazard.h"):
        assert len((folder / name).read_text(encoding="utf-8").splitlines()) < 1000
