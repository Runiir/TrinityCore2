"""Strategy-level Massive Crash side: every covered role moves once, then casts.

Exercises BotAdaptiveMagmawStrategyHazard.h through AdaptiveMagmawStrategy::
Propose with the native Room Stalker spawns lit by the native +/-22.5 degree
rule of each Massive Crash dummy (see test_magmaw_crash_side_footprint.py).
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
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include <cassert>
#include <cmath>
#include <string>
#include <vector>

using namespace BotEncounter;

namespace
{
constexpr float Pi = 3.14159265358979f;
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
constexpr Dummy RaidWide{-288.59f, -14.8472f, 3.64774f};
constexpr Dummy Narrow{-294.736f, -11.4306f, 4.62512f};

float RelativeDegrees(Dummy const& dummy, float x, float y)
{
    float angle = std::atan2(y - dummy.Y, x - dummy.X) - dummy.O;
    while (angle > Pi) angle -= 2.0f * Pi;
    while (angle < -Pi) angle += 2.0f * Pi;
    return angle * 180.0f / Pi;
}

ActorSnapshot Player(uint32 guid, char const* role, char const* spec,
    Vector3 position)
{
    ActorSnapshot player;
    player.Guid = ObjectGuid(HighGuid::Player, guid);
    player.Kind = ActorKind::Player;
    player.Role = role;
    player.ClassSpec = spec;
    player.Position = position;
    player.HealthPct = 100.0f;
    player.Alive = true;
    return player;
}

ActorSnapshot Boss()
{
    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit, AdaptiveMagmawStrategy::BossEntry,
        uint32(700));
    boss.Entry = AdaptiveMagmawStrategy::BossEntry;
    boss.Alive = true;
    boss.Attackable = true;
    boss.Selectable = true;
    boss.InCombat = true;
    boss.Position = { -302.467f, -31.7101f, 210.848f };
    return boss;
}

std::vector<ActorSnapshot> Lit(Dummy const& dummy, bool all = false)
{
    std::vector<ActorSnapshot> lit;
    uint32 counter = 0;
    for (auto const& stalker : Stalkers)
    {
        ++counter;
        ActorSnapshot actor;
        actor.Guid = ObjectGuid(HighGuid::Unit,
            AdaptiveMagmawStrategy::RoomStalkerEntry, 250062 + counter);
        actor.Entry = AdaptiveMagmawStrategy::RoomStalkerEntry;
        actor.Alive = true;
        actor.Position = { stalker[0], stalker[1], stalker[2] };
        if (all || std::fabs(RelativeDegrees(dummy, stalker[0], stalker[1]))
                <= 22.5f)
        {
            actor.Auras.push_back({ 87949, ObjectGuid{}, 1, 0 });
            lit.push_back(actor);
        }
    }
    return lit;
}

struct Geometry { Vector3 RoomSide, Support, Left, Right; };
Geometry Anchors(ActorSnapshot const& boss)
{
    // Room side that places the support point at the retained 8-yd spot.
    float dx = -308.9f - boss.Position.X;
    float dy = -36.5f - boss.Position.Y;
    float const length = std::hypot(dx, dy);
    dx /= length;
    dy /= length;
    Geometry geometry;
    geometry.RoomSide = { boss.Position.X + dx * 30.0f,
        boss.Position.Y + dy * 30.0f, 211.815f };
    float const support = AdaptiveMagmawStrategy::SupportStackDistance;
    float const ranged = AdaptiveMagmawStrategy::RangedStackDistance;
    float const lateral = AdaptiveMagmawStrategy::RangedStackLateralOffset;
    geometry.Support = { boss.Position.X + dx * support,
        boss.Position.Y + dy * support, 211.815f };
    Vector3 const center{ boss.Position.X + dx * ranged,
        boss.Position.Y + dy * ranged, 211.815f };
    geometry.Left = { center.X - dy * lateral, center.Y + dx * lateral,
        211.815f };
    geometry.Right = { center.X + dy * lateral, center.Y - dx * lateral,
        211.815f };
    return geometry;
}

Blackboard Board(ActorSnapshot const& boss, Geometry const& geometry,
    std::vector<ActorSnapshot> const& lit, std::vector<ActorSnapshot> players)
{
    Blackboard board;
    board.CurrentScope = Scope{ "crash-side-strategy", 11, 0, 4,
        "bwd.magmaw.encounter", 669, 2, "magmaw" };
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { geometry.RoomSide };
    board.NativeBossState = "in_progress";
    board.Revision = 900;
    board.ObservedAtMs = 99000;
    board.Players = std::move(players);
    board.Hostiles = { boss };
    board.Hostiles.insert(board.Hostiles.end(), lit.begin(), lit.end());
    return board;
}

std::vector<ActorSnapshot> Raid(ActorSnapshot const& tested)
{
    // Two lower-GUID DPS own the pincer duty so the tested actors never do.
    return { Player(30002, "dps", "affliction_warlock", { -309.5f, -37.0f, 211.815f }),
        Player(30003, "dps", "affliction_warlock", { -309.5f, -37.5f, 211.815f }),
        tested };
}

Vector3 Destination(AdaptiveMagmawPlan const& plan)
{
    assert(plan.Movement);
    assert(plan.Movement->Id.Mechanic == "massive_crash_evade");
    assert(plan.Movement->ActionPriority
        == BotActionArbitration::Priority::Survival);
    auto const* move = std::get_if<BotNativeAction::Move>(&plan.Movement->Action);
    assert(move);
    return { move->X, move->Y, move->Z };
}

void CheckMoveThenCast(char const* role, char const* spec, uint32 guid)
{
    ActorSnapshot const boss = Boss();
    Geometry const geometry = Anchors(boss);
    std::vector<ActorSnapshot> const lit = Lit(RaidWide);
    AdaptiveMagmawStrategy strategy;
    MagmawEventMovementTransitionState state;
    ObjectGuid const actor = ObjectGuid(HighGuid::Player, guid);
    ActorSnapshot tested = Player(guid, role, spec, geometry.Support);
    Blackboard board = Board(boss, geometry, lit, Raid(tested));

    auto first = strategy.Propose(board, actor, role, nullptr, false, false,
        nullptr, nullptr, &state);
    Vector3 const destination = Destination(first);
    float sideX = geometry.Left.X - geometry.Right.X;
    float sideY = geometry.Left.Y - geometry.Right.Y;
    float const sideLength = std::hypot(sideX, sideY);
    // The raid-wide lit set sits on the Right anchor's side: evade Left.
    assert(std::fabs(destination.X - (geometry.Support.X
        + sideX / sideLength * AdaptiveMagmawStrategy::SupportStackDistance)) < 0.01f);
    assert(std::fabs(destination.Y - (geometry.Support.Y
        + sideY / sideLength * AdaptiveMagmawStrategy::SupportStackDistance)) < 0.01f);
    assert(std::fabs(RelativeDegrees(RaidWide, geometry.Support.X,
        geometry.Support.Y)) < 23.5f);
    assert(RelativeDegrees(RaidWide, destination.X, destination.Y) > 30.0f);
    uint64 const intent = first.Movement->Id.EventGeneration;

    // The retained zig-zag points no longer re-decide the side.
    for (Vector3 const position : { Vector3{-313.3f, -30.7f, 211.815f},
             Vector3{-306.8f, -39.5f, 211.815f},
             Vector3{-309.3f, -38.3f, 211.815f} })
    {
        board.Revision += 1;
        board.ObservedAtMs += 250;
        tested.Position = position;
        board.Players = Raid(tested);
        auto next = strategy.Propose(board, actor, role, nullptr, false, false,
            nullptr, nullptr, &state);
        Vector3 const retained = Destination(next);
        assert(next.Movement->Id.EventGeneration == intent);
        assert(retained.X == destination.X && retained.Y == destination.Y);
    }

    // At the cleared point the actor holds: no crash, formation-restore or
    // pincer movement, and offense stays on Magmaw.
    board.Revision += 1;
    board.ObservedAtMs += 250;
    tested.Position = destination;
    board.Players = Raid(tested);
    auto arrived = strategy.Propose(board, actor, role, nullptr, false, false,
        nullptr, nullptr, &state);
    assert(!state.ActiveLethal());
    assert(arrived.Movement.Empty());
    assert(!arrived.SuppressOffense);
    if (std::string(role) == "dps")
        assert(arrived.DamageTarget == boss.Guid);
}
}

int main()
{
    // Generic across the roles the crash dodge covers.
    CheckMoveThenCast("dps", "balance_druid", 30005);
    CheckMoveThenCast("healer", "restoration_druid", 30006);

    ActorSnapshot const boss = Boss();
    Geometry const geometry = Anchors(boss);
    AdaptiveMagmawStrategy strategy;

    // The narrow crash evades toward the opposite, uncovered side.
    {
        MagmawEventMovementTransitionState state;
        ActorSnapshot tested = Player(30005, "dps", "balance_druid",
            geometry.Support);
        Blackboard board = Board(boss, geometry, Lit(Narrow), Raid(tested));
        auto plan = strategy.Propose(board, tested.Guid, "dps", nullptr, false,
            false, nullptr, nullptr, &state);
        Vector3 const destination = Destination(plan);
        assert(RelativeDegrees(Narrow, destination.X, destination.Y) < -35.0f);
        assert(std::hypot(destination.X - geometry.Support.X,
            destination.Y - geometry.Support.Y) > 7.99f);
    }

    // With no reachable point outside the crash the actor stays and casts:
    // a lit field far wider than the escape reach around the actor.
    {
        std::vector<ActorSnapshot> field;
        uint32 counter = 0;
        for (float x = -380.0f; x <= -240.0f; x += 10.0f)
            for (float y = -110.0f; y <= 30.0f; y += 10.0f)
            {
                ActorSnapshot stalker;
                stalker.Guid = ObjectGuid(HighGuid::Unit,
                    AdaptiveMagmawStrategy::RoomStalkerEntry, 260000 + ++counter);
                stalker.Entry = AdaptiveMagmawStrategy::RoomStalkerEntry;
                stalker.Alive = true;
                stalker.Position = { x, y, 211.815f };
                stalker.Auras.push_back({ 87949, ObjectGuid{}, 1, 0 });
                field.push_back(stalker);
            }
        MagmawEventMovementTransitionState state;
        ActorSnapshot tested = Player(30005, "dps", "balance_druid",
            geometry.Support);
        Blackboard board = Board(boss, geometry, field, Raid(tested));
        for (int tick = 0; tick < 3; ++tick)
        {
            board.Revision += 1;
            auto plan = strategy.Propose(board, tested.Guid, "dps", nullptr,
                false, false, nullptr, nullptr, &state);
            assert(plan.Movement.Empty());
            assert(!plan.SuppressOffense);
            assert(plan.DamageTarget == boss.Guid);
            assert(!state.ActiveLethal());
        }
    }

    // Every native stalker lit: the old side points are covered, but a short
    // outward step from the lit area clears it, so the actor moves.
    {
        MagmawEventMovementTransitionState state;
        ActorSnapshot tested = Player(30005, "dps", "balance_druid",
            geometry.Support);
        Blackboard board = Board(boss, geometry, Lit(RaidWide, true),
            Raid(tested));
        auto plan = strategy.Propose(board, tested.Guid, "dps", nullptr,
            false, false, nullptr, nullptr, &state);
        Vector3 const destination = Destination(plan);
        assert(std::hypot(destination.X - geometry.Support.X,
            destination.Y - geometry.Support.Y) <= MagmawCrashEscapeReach);
    }

    // Review item 2 through the blackboard: an observed crash dummy whose
    // native arc holds the lit set closes the cone tip. A bot at the tip
    // holds without it and evades with it; the inactive dummy is ignored.
    {
        auto dummy = [](Dummy const& native, uint32 counter)
        {
            ActorSnapshot actor;
            actor.Guid = ObjectGuid(HighGuid::Unit,
                AdaptiveMagmawStrategy::PersistentCrashDummyEntry, counter);
            actor.Entry = AdaptiveMagmawStrategy::PersistentCrashDummyEntry;
            actor.Alive = true;
            actor.Position = { native.X, native.Y, 211.257f };
            actor.Facing = native.O;
            return actor;
        };
        Vector3 const tip{ (RaidWide.X + boss.Position.X) / 2.0f,
            (RaidWide.Y + boss.Position.Y) / 2.0f, 211.0f };
        assert(std::fabs(RelativeDegrees(RaidWide, tip.X, tip.Y)) < 22.5f);
        ActorSnapshot tested = Player(30005, "dps", "balance_druid", tip);
        std::vector<ActorSnapshot> const lit = Lit(RaidWide);

        MagmawEventMovementTransitionState unseenState;
        Blackboard unseen = Board(boss, geometry, lit, Raid(tested));
        auto withoutDummy = strategy.Propose(unseen, tested.Guid, "dps",
            nullptr, false, false, nullptr, nullptr, &unseenState);
        assert(withoutDummy.Movement.Empty());

        MagmawEventMovementTransitionState wrongState;
        Blackboard wrong = Board(boss, geometry, lit, Raid(tested));
        wrong.Interactables = { dummy(Narrow, 250060) };
        auto inactiveDummy = strategy.Propose(wrong, tested.Guid, "dps",
            nullptr, false, false, nullptr, nullptr, &wrongState);
        assert(inactiveDummy.Movement.Empty());

        MagmawEventMovementTransitionState seenState;
        Blackboard seen = Board(boss, geometry, lit, Raid(tested));
        seen.Interactables = { dummy(Narrow, 250060), dummy(RaidWide, 250061) };
        auto withDummy = strategy.Propose(seen, tested.Guid, "dps", nullptr,
            false, false, nullptr, nullptr, &seenState);
        Vector3 const escape = Destination(withDummy);
        assert(std::fabs(RelativeDegrees(RaidWide, escape.X, escape.Y)) > 24.0f);
        assert(std::hypot(escape.X - tip.X, escape.Y - tip.Y)
            <= MagmawCrashEscapeReach);
    }

    // Review item 3 through the strategy: once the native path rejects the
    // retained crash point, the next tick evades elsewhere instead of
    // re-proposing it.
    {
        MagmawEventMovementTransitionState state;
        ActorSnapshot tested = Player(30005, "dps", "balance_druid",
            geometry.Support);
        Blackboard board = Board(boss, geometry, Lit(RaidWide), Raid(tested));
        auto first = strategy.Propose(board, tested.Guid, "dps", nullptr,
            false, false, nullptr, nullptr, &state);
        Vector3 const rejected = Destination(first);
        uint64 const intent = first.Movement->Id.EventGeneration;
        board.Revision += 1;
        auto retained = strategy.Propose(board, tested.Guid, "dps", nullptr,
            false, false, nullptr, nullptr, &state);
        assert(retained.Movement->Id.EventGeneration == intent);
        assert(ObserveMagmawCrashEvadeNativeRejection(state, tested.Guid,
            intent, rejected, "route_destination_unreachable"));
        board.Revision += 1;
        auto fallback = strategy.Propose(board, tested.Guid, "dps", nullptr,
            false, false, nullptr, nullptr, &state);
        Vector3 const alternative = Destination(fallback);
        assert(fallback.Movement->Id.EventGeneration != intent);
        assert(std::hypot(alternative.X - rejected.X,
            alternative.Y - rejected.Y) > MagmawCrashRejectedPointTolerance);
        assert(std::fabs(RelativeDegrees(RaidWide, alternative.X,
            alternative.Y)) > 24.0f);
        assert(fallback.DamageTarget == boss.Guid);
    }
    return 0;
}
'''


def test_magmaw_crash_side_strategy_moves_once_then_casts(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_crash_side_strategy.cpp"
    binary = tmp_path / "magmaw_crash_side_strategy"
    source.write_text(FIXTURE, encoding="utf-8")
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         *[arg for path in INCLUDES for arg in ("-I", str(ROOT / path))],
         str(source), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)
