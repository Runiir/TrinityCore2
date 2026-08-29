from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_magmaw_lethal_movement_survives_observation_and_lease_churn(
    tmp_path: Path,
) -> None:
    source = tmp_path / "magmaw_lethal_movement.cpp"
    binary = tmp_path / "magmaw_lethal_movement"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include <cassert>

using namespace BotEncounter;

static ObjectGuid PlayerGuid(uint32 value)
{
    return ObjectGuid(HighGuid::Player, value);
}

static ObjectGuid UnitGuid(uint32 entry, uint32 value)
{
    return ObjectGuid(HighGuid::Unit, entry, value);
}

static BotMovementArbitration::Request RequestFor(Blackboard const& board,
    BotNativeAction::Candidate const& candidate, uint64 expiresAt)
{
    auto const* move = std::get_if<BotNativeAction::Move>(&candidate.Action);
    assert(move);
    return { BotMovementArbitration::Owner::Hazard,
        BotMovementArbitration::Priority::Hazard, expiresAt,
        { board.CurrentScope.AttemptId, board.CurrentScope.WipeGeneration,
            board.CurrentScope.RouteGeneration, board.CurrentScope.MapId,
            board.CurrentScope.InstanceId },
        move->X, move->Y, move->Z, 0 };
}

int main()
{
    Blackboard board;
    board.CurrentScope = Scope{ "canary121", 11, 0, 4,
        "bwd.magmaw.encounter", 669, 2, "magmaw" };
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.NativeBossState = "in_progress";
    board.ObservedAtMs = 1000;
    ObjectGuid const actor = PlayerGuid(30009);

    MagmawEventMovementTransitionState state;
    ActorSnapshot bot;
    bot.Guid = actor;
    bot.Alive = true;
    bot.Role = "dps";
    bot.Position = { -330.936f, -27.3621f, 211.313f };
    ActorSnapshot boss;
    boss.Guid = UnitGuid(41570, 700);
    boss.Entry = AdaptiveMagmawStrategy::BossEntry;
    boss.Alive = true;
    boss.Attackable = true;
    boss.Selectable = true;
    boss.InCombat = true;
    boss.Position = { -324.0f, -20.0f, 211.313f };
    ActorSnapshot crash;
    crash.Guid = UnitGuid(47196, 800);
    crash.Entry = AdaptiveMagmawStrategy::RoomStalkerEntry;
    crash.Alive = true;
    crash.Position = { -331.0f, -20.0f, 211.313f };
    crash.Auras.push_back({ 87949, ObjectGuid{}, 1, 0 });
    board.Players = { bot };
    board.Hostiles = { boss, crash };
    AdaptiveMagmawStrategy strategy;
    auto firstPlan = strategy.Propose(board, actor, "dps", nullptr, false,
        false, nullptr, nullptr, &state);
    auto first = firstPlan.Movement;
    assert(first && first->ActionPriority
        == BotActionArbitration::Priority::Survival);
    assert(firstPlan.DamageTarget == boss.Guid);
    auto const* firstPoint = std::get_if<BotNativeAction::Move>(&first->Action);
    assert(firstPoint && state.ActiveLethal());
    uint64 const firstIntent = first->Id.EventGeneration;

    BotMovementArbitration::Lease lease;
    auto firstRequest = RequestFor(board, *first, 2500);
    assert(BotMovementArbitration::Evaluate(lease, firstRequest, 1000)
        == BotMovementArbitration::Decision::Acquire);
    BotMovementArbitration::Apply(lease, firstRequest);

    // Snapshot geometry may move and the short lease may expire. One lethal
    // event still retains one safe point and one candidate identity.
    board.Revision += 1;
    board.ObservedAtMs = 3000;
    bot.Position = { -339.442f, -36.9149f, 211.17f };
    crash.Position = { -335.0f, -24.0f, 211.17f };
    board.Players = { bot };
    board.Hostiles = { boss, crash };
    auto retainedPlan = strategy.Propose(board, actor, "dps", nullptr,
        false, false, nullptr, nullptr, &state);
    auto retained = retainedPlan.Movement;
    assert(retained && retained->Id.EventGeneration == firstIntent);
    auto const* retainedPoint = std::get_if<BotNativeAction::Move>(
        &retained->Action);
    assert(retainedPoint && retainedPoint->X == firstPoint->X
        && retainedPoint->Y == firstPoint->Y
        && retainedPoint->Z == firstPoint->Z);
    auto expiredRequest = RequestFor(board, *retained, 4500);
    assert(BotMovementArbitration::Evaluate(lease, expiredRequest, 3000)
        == BotMovementArbitration::Decision::Acquire);

    // The exact survival movement owns only Movement, so stationary trained
    // damage remains eligible in the same priority-queue tick.
    BotActionArbitration::Kernel kernel;
    kernel.Begin(board.ObservedAtMs);
    bool moved = false;
    bool damaged = false;
    kernel.Submit(BotActionArbitration::Candidate{
        "stable_lethal_movement", "adaptive_magmaw",
        retained->ActionPriority, retained->Utility, 0.0f, 0.0f,
        retained->Resources(), retained->ExpiresAtMs, 100, 3000, 5, true, "",
        [&] { moved = true; return BotActionArbitration::Outcome::Submitted(
            "lethal_move_submitted"); }});
    kernel.Submit(BotActionArbitration::Candidate{
        "trained_damage", "db_class_spec_profile",
        BotActionArbitration::Priority::TrainedDamage, 1.0f, 0.0f, 0.0f,
        BotActionArbitration::Uses(BotActionArbitration::Resource::Cast,
            BotActionArbitration::Resource::Target),
        retained->ExpiresAtMs, 100, 3000, 5, true, "",
        [&] { damaged = true; return BotActionArbitration::Outcome::Submitted(
            "damage_submitted"); }});
    auto const& resolution = kernel.Resolve();
    assert(moved && damaged && resolution.CommittedCandidates.size() == 2);

    // Matching X/Y on another floor is not arrival.
    state.ObserveArrival({ firstPoint->X, firstPoint->Y,
        firstPoint->Z - 20.0f });
    assert(state.ActiveLethal());
    state.ObserveArrival({ firstPoint->X, firstPoint->Y, firstPoint->Z });
    assert(!state.ActiveLethal());

    // Re-entry into the same persistent hazard source is a new escape, not
    // a permanently retired match on the old source GUID.
    bot.Position = { -330.936f, -27.3621f, 211.313f };
    crash.Position = { -331.0f, -20.0f, 211.313f };
    auto reentered = RetainMagmawRadialLethalMovement(
        board, bot, crash, "massive_crash_evade", 16.0f, state, 450.0f);
    assert(reentered && reentered->Id.EventGeneration != firstIntent);

    Blackboard reset = board;
    reset.CurrentScope.AttemptId += 1;
    reset.CurrentScope.WipeGeneration += 1;
    state.ObserveScope(reset, actor);
    assert(!state.ActiveLethal());
    auto resetMove = RetainMagmawRadialLethalMovement(
        reset, bot, crash, "massive_crash_evade", 16.0f, state, 450.0f);
    assert(resetMove && resetMove->Id.ScopeKey != first->Id.ScopeKey);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "src/common/Utilities"),
            "-I",
            str(ROOT / "src/common/Logging"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)
