from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_magmaw_directional_mobility_and_point_fallback(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_directional_integration.cpp"
    binary = tmp_path / "magmaw_directional_integration"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/BotActionArbiter.h"
#include <cassert>

using namespace BotEncounter;
using namespace BotActionArbitration;

static ActorSnapshot Player(uint32 guid, char const* spec, Vector3 position)
{
    ActorSnapshot actor;
    actor.Guid = ObjectGuid(HighGuid::Player, guid);
    actor.Alive = true;
    actor.Role = "dps";
    actor.ClassSpec = spec;
    actor.Position = position;
    return actor;
}

static Blackboard Board(uint32 remaining, bool active,
    Vector3 parasitePosition)
{
    Blackboard board;
    board.CurrentScope = Scope{
        "mobility", 4, 0, 2, "bwd.magmaw.encounter", 669, 1, "magmaw" };
    board.Revision = 10;
    board.ObservedAtMs = 1000;
    board.NativeBossState = "in_progress";
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { { 0.0f, -1.0f, 210.0f } };
    board.Players = {
        Player(30006, "fire_mage", { 24.0f, -30.0f, 210.0f }),
        Player(30009, "marksmanship_hunter", { 24.0f, -30.0f, 210.0f }),
        Player(30008, "affliction_warlock", { 0.0f, -8.0f, 210.0f }) };
    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit, uint32(41570), uint32(1));
    boss.Entry = 41570;
    boss.Alive = true;
    boss.Attackable = true;
    boss.Selectable = true;
    boss.InCombat = true;
    boss.Position = { 0.0f, 0.0f, 210.0f };
    boss.MechanicTimers.push_back({ 88253, remaining, active,
        FactSource::NativeInstanceState });
    ActorSnapshot parasite;
    parasite.Guid = ObjectGuid(HighGuid::Unit, uint32(41806), uint32(9));
    parasite.Entry = 41806;
    parasite.Alive = true;
    parasite.Position = parasitePosition;
    board.Hostiles = { boss, parasite };
    return board;
}

static AdaptiveMagmawPlan Propose(Blackboard const& board, ObjectGuid actor,
    MagmawLaneTransitionState& lane, uint32 spell, uint32 cooldown)
{
    return AdaptiveMagmawStrategy().Propose(board, actor, "dps", nullptr,
        false, false, &lane, nullptr, nullptr,
        MagmawDirectionalMobilityInput{ spell, cooldown });
}

int main()
{
    Blackboard distant = Board(30000, false,
        { 0.0f, -60.0f, 210.0f });
    MagmawLaneTransitionState mageLane;
    AdaptiveMagmawPlan mage = Propose(distant, distant.Players[0].Guid,
        mageLane, 1953, 15000);
    assert(mage.Movement && mage.DirectionalMobility);
    auto const* blink = std::get_if<BotNativeAction::DirectionalMobility>(
        &mage.DirectionalMobility->Action);
    assert(blink && blink->SpellId == 1953);
    assert(blink->Facing == BotNativeAction::DirectionalMobilityFacing::Forward);
    assert(mage.DirectionalMobility->Id.Actor == distant.Players[0].Guid);
    assert(mage.DirectionalMobility->Id.EventGeneration
        == mage.Movement->Id.EventGeneration);
    assert(mage.DirectionalMobility->Utility > mage.Movement->Utility);

    // The direct route is admitted before Crash exists. A later lit Room
    // Stalker on that same remaining segment must replace it with one
    // same-transition far-perimeter arc, not a straight Crash move.
    assert(!mageLane.MageParasiteRoute.Empty());
    auto const* magePoint = std::get_if<BotNativeAction::Move>(
        &mage.Movement->Action);
    assert(magePoint);
    Blackboard crash = distant;
    crash.Revision += 1;
    ActorSnapshot crashStalker;
    crashStalker.Guid = ObjectGuid(HighGuid::Unit, uint32(47196), uint32(17));
    crashStalker.Entry = 47196;
    crashStalker.Alive = true;
    crashStalker.Position = {
        (crash.Players[0].Position.X + magePoint->X) * 0.5f,
        (crash.Players[0].Position.Y + magePoint->Y) * 0.5f,
        crash.Players[0].Position.Z };
    crashStalker.Auras.push_back({ 87949, ObjectGuid{}, 1, 0 });
    crash.Hostiles.push_back(crashStalker);
    uint64 const directGeneration = mage.Movement->Id.EventGeneration;
    AdaptiveMagmawPlan crashArc = Propose(crash, crash.Players[0].Guid,
        mageLane, 1953, 15000);
    assert(crashArc.Movement);
    assert(crashArc.Movement->Id.Mechanic == "parasite_contact_evade");
    assert(mageLane.MageParasiteRoute.UsesFarPerimeterArc);
    assert(crashArc.Movement->Id.EventGeneration != directGeneration);
    uint64 const arcGeneration = crashArc.Movement->Id.EventGeneration;
    AdaptiveMagmawPlan retainedArc = Propose(crash, crash.Players[0].Guid,
        mageLane, 1953, 15000);
    assert(retainedArc.Movement);
    assert(retainedArc.Movement->Id.EventGeneration == arcGeneration);
    assert(mageLane.MageParasiteRoute.UsesFarPerimeterArc);

    MagmawLaneTransitionState hunterLane;
    AdaptiveMagmawPlan hunter = Propose(distant, distant.Players[1].Guid,
        hunterLane, 781, 25000);
    auto const* disengage = std::get_if<BotNativeAction::DirectionalMobility>(
        &hunter.DirectionalMobility->Action);
    assert(disengage && disengage->SpellId == 781);
    assert(disengage->Facing
        == BotNativeAction::DirectionalMobilityFacing::Backward);

    // A moving parasite entering the Hunter's future segment triggers one
    // proactive per-baiter replan. Repeating the same observation retains the
    // new geometry and identity instead of oscillating the shared lane.
    auto const* hunterPoint = std::get_if<BotNativeAction::Move>(
        &hunter.Movement->Action);
    assert(hunterPoint && !hunterLane.HunterParasiteRoute.Empty());
    Blackboard movingPack = distant;
    movingPack.Revision += 1;
    movingPack.Hostiles[1].Position = {
        (movingPack.Players[1].Position.X + hunterPoint->X) * 0.5f,
        (movingPack.Players[1].Position.Y + hunterPoint->Y) * 0.5f,
        movingPack.Players[1].Position.Z };
    auto const laneDirection = hunterLane.Lane;
    uint64 const hunterDirectGeneration = hunter.Movement->Id.EventGeneration;
    AdaptiveMagmawPlan hunterReplan = Propose(movingPack,
        movingPack.Players[1].Guid, hunterLane, 781, 25000);
    assert(hunterReplan.Movement);
    assert(hunterLane.Lane == laneDirection);
    assert(hunterReplan.Movement->Id.EventGeneration
        != hunterDirectGeneration);
    uint64 const hunterArcGeneration =
        hunterReplan.Movement->Id.EventGeneration;
    movingPack.Revision += 1;
    AdaptiveMagmawPlan hunterStable = Propose(movingPack,
        movingPack.Players[1].Guid, hunterLane, 781, 25000);
    assert(hunterStable.Movement);
    assert(hunterStable.Movement->Id.EventGeneration
        == hunterArcGeneration);
    assert(hunterLane.Lane == laneDirection);

    Blackboard soon = Board(14999, false,
        { 0.0f, -60.0f, 210.0f });
    MagmawLaneTransitionState soonLane;
    AdaptiveMagmawPlan reserved = Propose(soon, soon.Players[0].Guid,
        soonLane, 1953, 15000);
    assert(reserved.Movement);
    assert(!reserved.DirectionalMobility);

    Blackboard active = Board(0, true, { 0.0f, -60.0f, 210.0f });
    MagmawLaneTransitionState activeLane;
    AdaptiveMagmawPlan activePlan = Propose(active, active.Players[0].Guid,
        activeLane, 1953, 15000);
    assert(activePlan.Movement);
    assert(!activePlan.DirectionalMobility);

    Blackboard missingTimer = distant;
    missingTimer.Hostiles[0].MechanicTimers.clear();
    MagmawLaneTransitionState missingTimerLane;
    AdaptiveMagmawPlan missingTimerPlan = Propose(missingTimer,
        missingTimer.Players[0].Guid, missingTimerLane, 1953, 15000);
    assert(missingTimerPlan.Movement);
    assert(!missingTimerPlan.DirectionalMobility);

    Blackboard emergency = Board(0, true,
        { 29.0f, -30.0f, 210.0f });
    MagmawLaneTransitionState emergencyLane;
    AdaptiveMagmawPlan emergencyPlan = Propose(emergency,
        emergency.Players[0].Guid, emergencyLane, 1953, 15000);
    assert(emergencyPlan.Movement && emergencyPlan.DirectionalMobility);

    // A retryable directional cast claims no resources. The separate point
    // candidate remains eligible and submits in the same kernel tick.
    Kernel kernel;
    kernel.Begin(1001);
    Candidate directional;
    directional.Key = "directional:30006:1";
    directional.Source = mage.DirectionalMobility->Id.Strategy;
    directional.ActionPriority = mage.DirectionalMobility->ActionPriority;
    directional.UtilityScore = mage.DirectionalMobility->Utility;
    directional.RequiredResources = mage.DirectionalMobility->Resources();
    directional.ExpiresAtMs = mage.DirectionalMobility->ExpiresAtMs;
    directional.Attempt = [] {
        return Outcome::Retryable("native_directional_mobility_cast_rejected");
    };
    kernel.Submit(std::move(directional));
    bool pointRan = false;
    Candidate point;
    point.Key = "point:30006:1";
    point.Source = mage.Movement->Id.Strategy;
    point.ActionPriority = mage.Movement->ActionPriority;
    point.UtilityScore = mage.Movement->Utility;
    point.RequiredResources = mage.Movement->Resources();
    point.ExpiresAtMs = mage.Movement->ExpiresAtMs;
    point.Attempt = [&pointRan] {
        pointRan = true;
        return Outcome::Submitted("native_move_submitted");
    };
    kernel.Submit(std::move(point));
    Resolution const& resolution = kernel.Resolve();
    assert(pointRan);
    assert(resolution.AnyCommitted);
    assert(resolution.CommittedCandidates.size() == 1);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "src/server/game"),
            "-I", str(ROOT / "src/server/game/Entities/Object"),
            "-I", str(ROOT / "src/common"),
            "-I", str(ROOT / "src/common/Utilities"),
            "-I", str(ROOT / "src/common/Logging"),
            "-I", str(ROOT / "src/common/Debugging"),
            str(source), "-o", str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_magmaw_runtime_join_uses_native_cooldown_and_two_candidates() -> None:
    preparation = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp").read_text()
    candidates = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp").read_text()
    context = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrUpdateContext.h").read_text()

    assert "sSpellMgr->GetSpellInfo(spellId)" in preparation
    assert "info->GetRecoveryTime()" in preparation
    assert "AdaptiveMagmawDirectionalMobility" in context
    assert "context.AdaptiveMagmawDirectionalMobility" in candidates
    assert "context.AdaptiveMagmawMovement" in candidates
    assert "parasite_directional_mobility" in candidates
