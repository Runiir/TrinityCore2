from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_action_and_movement_arbiters_compile_and_replay(tmp_path: Path) -> None:
    source = tmp_path / "arbiter_replay.cpp"
    binary = tmp_path / "arbiter_replay"
    source.write_text(
        r'''
#include "Bots/BotActionArbiter.h"
#include "Bots/BotAdaptiveDrudgeStrategy.h"
#include "Bots/BotAdaptiveAtramedesStrategy.h"
#include "Bots/BotAdaptiveChimaeronStrategy.h"
#include "Bots/BotAdaptiveMagmawStrategy.h"
#include "Bots/BotAdaptiveMaloriakStrategy.h"
#include "Bots/BotAdaptiveNefarianStrategy.h"
#include "Bots/BotAdaptiveOmnotronStrategy.h"
#include "Bots/BotAdaptiveRaidTrashStrategy.h"
#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotMovementArbiter.h"
#include "Bots/BotNativeActionIntent.h"
#include <cassert>
#include <string>

int main()
{
    using namespace BotActionArbitration;
    Tick tick;
    Outcome hazard = tick.Try(Priority::Survival, "hazard", []
    {
        return Outcome::Retryable("path_temporarily_blocked");
    });
    assert(hazard.Result == Disposition::Retryable);
    Outcome heal = tick.Try(Priority::Support, "heal", []
    {
        return FromBotActionResult(BotActionResult::Cooldown);
    });
    assert(heal.Result == Disposition::Retryable);
    Outcome damage = tick.Try(Priority::TrainedDamage, "trained_damage", []
    {
        return FromBotActionResult(BotActionResult::Ok);
    });
    assert(damage.Result == Disposition::Committed);
    assert(tick.Resolved());
    assert(tick.AttemptCount() == 3);

    Tick inversion;
    inversion.Try(Priority::Support, "heal", []
    {
        return Outcome::Retryable("cooldown");
    });
    Outcome bad = inversion.Try(Priority::Survival, "late_hazard", []
    {
        return Outcome::Committed("should_not_run");
    });
    assert(bad.Result == Disposition::Terminal);
    assert(!inversion.OrderingValid());

    using namespace BotMovementArbitration;
    Scope scope{ 7, 2, 9, 669, 41 };
    Lease lease;
    Request route{ Owner::Route, BotMovementArbitration::Priority::Route,
        1100, scope, 1.0f, 2.0f, 3.0f };
    assert(Evaluate(lease, route, 1000) == Decision::Acquire);
    Apply(lease, route);

    Request combat{ Owner::CombatRange, BotMovementArbitration::Priority::Combat,
        1200, scope, 4.0f, 5.0f, 6.0f };
    assert(Evaluate(lease, combat, 1001) == Decision::Preempt);
    Apply(lease, combat);

    Request lower{ Owner::Formation, BotMovementArbitration::Priority::Formation,
        1300, scope, 7.0f, 8.0f, 9.0f };
    assert(Evaluate(lease, lower, 1002) == Decision::PreserveExisting);

    Request retargetSameOwner{ Owner::CombatRange,
        BotMovementArbitration::Priority::Combat, 1300, scope,
        9.0f, 10.0f, 11.0f };
    assert(Evaluate(lease, retargetSameOwner, 1002)
        == Decision::PreserveExisting);
    Request refreshSameDestination{ Owner::CombatRange,
        BotMovementArbitration::Priority::Combat, 1300, scope,
        4.0f, 5.0f, 6.0f };
    assert(Evaluate(lease, refreshSameDestination, 1002)
        == Decision::Refresh);

    Request targetAwareUpgrade{ Owner::CombatRange,
        BotMovementArbitration::Priority::Combat, 1300, scope,
        4.0f, 5.0f, 6.0f, 7001 };
    assert(Evaluate(lease, targetAwareUpgrade, 1002) == Decision::Preempt);
    Apply(lease, targetAwareUpgrade);
    Request movingSameTarget{ Owner::CombatRange,
        BotMovementArbitration::Priority::Combat, 1400, scope,
        40.0f, 50.0f, 60.0f, 7001 };
    assert(Evaluate(lease, movingSameTarget, 1003) == Decision::Refresh);
    Request differentLiveTarget{ Owner::CombatRange,
        BotMovementArbitration::Priority::Combat, 1400, scope,
        40.0f, 50.0f, 60.0f, 7002 };
    assert(Evaluate(lease, differentLiveTarget, 1003)
        == Decision::PreserveExisting);

    assert(FromBotActionResult(BotActionResult::Ok).LifecyclePhase
        == Phase::Submitted);
    assert(FromBotActionResult(BotActionResult::GlobalCooldown).Result
        == Disposition::Retryable);

    Scope newInstance = scope;
    newInstance.InstanceId = 42;
    Request formationNewInstance{ Owner::Formation,
        BotMovementArbitration::Priority::Formation, 1300, newInstance,
        7.0f, 8.0f, 9.0f };
    assert(Evaluate(lease, formationNewInstance, 1002) == Decision::Acquire);

    // Producers submit in arbitrary order. The kernel applies the hard mask,
    // then ranks by priority and utility/model score. A failed high-priority
    // candidate does not monopolize the tick. Stationary trained damage does
    // not claim movement, so independent route movement may also commit.
    Kernel kernel;
    kernel.Begin(2000);
    bool lowRan = false;
    bool hazardRan = false;
    bool damageRan = false;
    bool maskedRan = false;
    bool duplicateRan = false;
    kernel.Submit(Candidate{
        "route", "legacy_route", BotActionArbitration::Priority::RouteMovement, 1.0f, 0.0f, 0.0f,
        Uses(Resource::Movement), 0, 100, 3000, 5, true, "", [&]
        {
            lowRan = true;
            return Outcome::Committed("route_move");
        }
    });
    kernel.Submit(Candidate{
        "unsafe_cheat", "test", BotActionArbitration::Priority::Terminal, 100.0f, 0.0f, 0.0f,
        Uses(Resource::Movement), 0, 100, 3000, 5, false,
        "native_only", [&]
        {
            maskedRan = true;
            return Outcome::Committed("must_not_run");
        }
    });
    kernel.Submit(Candidate{
        "hazard", "encounter", BotActionArbitration::Priority::Survival, 2.0f, 0.0f, 0.0f,
        Uses(Resource::Movement), 0, 100, 3000, 5, true, "", [&]
        {
            hazardRan = true;
            return Outcome::Retryable("path_temporarily_blocked");
        }
    });
    kernel.Submit(Candidate{
        "damage", "profile", BotActionArbitration::Priority::TrainedDamage, 5.0f, 1.0f, 2.0f,
        Uses(Resource::GlobalCooldown, Resource::Cast, Resource::Target),
        0, 100, 3000, 5, true, "", [&]
        {
            damageRan = true;
            return Outcome::Committed("cast_submitted");
        }
    });
    kernel.Submit(Candidate{
        "damage", "worse_duplicate", BotActionArbitration::Priority::TrainedDamage, 1.0f, 0.0f, 0.0f,
        Uses(Resource::Cast), 0, 100, 3000, 5, true, "", [&]
        {
            duplicateRan = true;
            return Outcome::Committed("wrong_duplicate");
        }
    });
    Resolution const& resolution = kernel.Resolve();
    assert(resolution.AnyCommitted);
    assert(!resolution.Terminal);
    assert(hazardRan);
    assert(damageRan);
    assert(lowRan);
    assert(!maskedRan);
    assert(!duplicateRan);
    assert(resolution.CommittedCandidates.size() == 2);
    assert(resolution.CommittedCandidates.front() == "damage");
    assert(resolution.CommittedCandidates.back() == "route");
    assert(kernel.LastResolutionJson().find("hard_masked") != std::string::npos);

    // Retry backoff belongs to the failing candidate, not the bot. The
    // alternative remains eligible and progress clears escalation state.
    kernel.Begin(2050);
    bool backedOffCandidateRan = false;
    bool alternativeRan = false;
    kernel.Submit(Candidate{
        "hazard", "encounter", BotActionArbitration::Priority::Survival, 2.0f, 0.0f, 0.0f,
        Uses(Resource::Movement), 0, 100, 3000, 2, true, "", [&]
        {
            backedOffCandidateRan = true;
            return Outcome::Retryable("still_blocked");
        }
    });
    kernel.Submit(Candidate{
        "alternative", "recovery", BotActionArbitration::Priority::Mechanic, 1.0f, 0.0f, 0.0f,
        Uses(Resource::Movement), 0, 100, 3000, 2, true, "", [&]
        {
            alternativeRan = true;
            return Outcome::Progressed("alternate_path");
        }
    });
    kernel.Resolve();
    assert(!backedOffCandidateRan);
    assert(alternativeRan);
    kernel.Observe("hazard", Outcome::Retryable("still_blocked"), 7100, 100, 3000, 2);
    assert(kernel.ShouldEscalate("hazard", 7100, 5000));
    kernel.MarkProgress("hazard", 7101, "movement_progress");
    assert(!kernel.ShouldEscalate("hazard", 7101, 0));

    // Native submission owns its resource lane but is not semantic progress.
    // Only an observed game-state postcondition advances LastProgressAtMs.
    kernel.Begin(7200);
    kernel.Submit(Candidate{
        "native_submission", "player_signal", BotActionArbitration::Priority::TrainedDamage,
        1.0f, 0.0f, 0.0f, Uses(Resource::Cast), 0, 100, 3000, 5, true, "", []
        {
            return Outcome::Submitted("native_cast_submitted");
        }
    });
    kernel.Resolve();
    Lifecycle const* submittedLifecycle = kernel.FindLifecycle("native_submission");
    assert(submittedLifecycle);
    assert(submittedLifecycle->CurrentPhase == Phase::Submitted);
    assert(submittedLifecycle->LastProgressAtMs == 0);
    kernel.MarkProgress("native_submission", 7201, "native_combat_observed");
    assert(kernel.FindLifecycle("native_submission")->LastProgressAtMs == 7201);
    kernel.Observe("native_selection", Outcome::Selected("profile_action_valid"), 7202);
    assert(kernel.FindLifecycle("native_selection")->CurrentPhase == Phase::Selected);
    assert(kernel.FindLifecycle("native_selection")->LastProgressAtMs == 0);

    // Resolution must own callback-local reason text for later replay/export.
    kernel.Begin(8000);
    kernel.Submit(Candidate{
        "owned_reason", "test", BotActionArbitration::Priority::TrainedDamage,
        1.0f, 0.0f, 0.0f, Uses(Resource::Cast), 0, 100, 3000, 5, true, "", []
        {
            std::string transient = "callback_local_reason";
            return Outcome::Retryable(transient);
        }
    });
    kernel.Resolve();
    assert(kernel.LastResolutionJson().find("callback_local_reason") != std::string::npos);

    // Encounter facts are scoped once and target channels remain independent:
    // a mechanic focus can never overwrite the trained rotation's target.
    BotEncounter::Scope encounterScope;
    encounterScope.CohortId = "magmaw";
    encounterScope.AttemptId = 7;
    encounterScope.WipeGeneration = 2;
    encounterScope.RouteGeneration = 9;
    encounterScope.NodeId = "bwd.magmaw.drudges";
    encounterScope.MapId = 669;
    encounterScope.InstanceId = 41;
    encounterScope.EncounterId = "magmaw_trash";
    assert(encounterScope.Valid());
    BotEncounter::TargetChannels channels;
    channels.DamageTarget = ObjectGuid(HighGuid::Player, uint32(100));
    channels.MechanicTarget = ObjectGuid(HighGuid::Unit, uint32(42362), uint32(60));
    assert(channels.DamageTarget != channels.MechanicTarget);

    // Resource ownership is derived from the closed native intent, never from
    // a blanket subsystem mask.
    using namespace BotNativeAction;
    Intent move = Move{ 1.0f, 2.0f, 3.0f };
    assert(RequiredResources(move) == Uses(Resource::Movement));
    Intent cast = CastSpell{ channels.DamageTarget, 133 };
    assert((RequiredResources(cast) & Uses(Resource::Movement)) == 0);
    assert((RequiredResources(cast) & Uses(Resource::Cast)) != 0);
    Intent click = SpellClick{ channels.MechanicTarget };
    assert(RequiredResources(click) == Uses(Resource::Interaction));
    Intent pet = PetCommand{ ObjectGuid(HighGuid::Pet, uint32(1), uint32(5)), channels.DamageTarget, 2 };
    assert((RequiredResources(pet) & Uses(Resource::Pet)) != 0);

    // A raid hazard is proposed independently from trained damage. The
    // endpoint is derived from the observed source, not a fixed route point.
    BotEncounter::Blackboard board;
    board.CurrentScope = encounterScope;
    board.Revision = 1;
    board.ObservedAtMs = 9000;
    board.Route.HazardSourceEntry = 42690;
    board.Route.HazardDetectionSpellId = 79580;
    board.Route.HazardRadius = 20.0f;
    BotEncounter::ActorSnapshot botActor;
    botActor.Guid = channels.DamageTarget;
    botActor.Kind = BotEncounter::ActorKind::Player;
    botActor.Alive = true;
    botActor.Position = { 0.0f, 0.0f, 10.0f };
    board.Players.push_back(botActor);
    BotEncounter::ActorSnapshot hazardActor;
    hazardActor.Guid = channels.MechanicTarget;
    hazardActor.Entry = 42690;
    hazardActor.Alive = true;
    hazardActor.Position = { 2.0f, 0.0f, 10.0f };
    hazardActor.Cast = BotEncounter::CastSnapshot{ 79580, channels.DamageTarget, 9000, false, false };
    board.Hostiles.push_back(hazardActor);
    BotEncounter::AdaptiveRaidTrashStrategy trashStrategy;
    auto hazardExit = trashStrategy.ProposeHazardExit(board, channels.DamageTarget);
    assert(hazardExit.has_value());
    assert(hazardExit->Resources() == Uses(Resource::Movement));
    auto const* hazardMove = std::get_if<Move>(&hazardExit->Action);
    assert(hazardMove && hazardMove->X < 0.0f);

    // Drudge behavior is adaptive: tanks deterministically own distinct
    // native sources, DPS balances the healthier add, and unsafe players get
    // a local source-relative movement intent instead of an exact lane gate.
    BotEncounter::Blackboard drudges;
    drudges.CurrentScope = encounterScope;
    drudges.Revision = 2;
    drudges.ObservedAtMs = 9100;
    drudges.Route.MechanicProfile = "trash_two_tank_charge_lanes";
    drudges.Route.MinimumDistance = 15.0f;
    BotEncounter::ActorSnapshot tankA = botActor;
    tankA.Guid = ObjectGuid(HighGuid::Player, uint32(101));
    tankA.Role = "tank";
    tankA.Position = { -4.0f, 0.0f, 0.0f };
    BotEncounter::ActorSnapshot tankB = tankA;
    tankB.Guid = ObjectGuid(HighGuid::Player, uint32(102));
    tankB.Position = { 14.0f, 0.0f, 0.0f };
    BotEncounter::ActorSnapshot dps = botActor;
    dps.Guid = ObjectGuid(HighGuid::Player, uint32(103));
    dps.Role = "dps";
    dps.Position = { 1.0f, 0.0f, 0.0f };
    drudges.Players = { tankA, tankB, dps };
    BotEncounter::ActorSnapshot sourceA;
    sourceA.Guid = ObjectGuid(HighGuid::Unit, uint32(42362), uint32(59));
    sourceA.Entry = 42362;
    sourceA.Alive = true;
    sourceA.HealthPct = 70.0f;
    sourceA.Position = { 0.0f, 0.0f, 0.0f };
    BotEncounter::ActorSnapshot sourceB = sourceA;
    sourceB.Guid = ObjectGuid(HighGuid::Unit, uint32(42362), uint32(60));
    sourceB.HealthPct = 90.0f;
    sourceB.Position = { 10.0f, 0.0f, 0.0f };
    drudges.Hostiles = { sourceA, sourceB };
    BotEncounter::AdaptiveDrudgeStrategy drudgeStrategy;
    auto tankAPlan = drudgeStrategy.Propose(drudges, tankA.Guid, "tank");
    auto tankBPlan = drudgeStrategy.Propose(drudges, tankB.Guid, "tank");
    auto dpsPlan = drudgeStrategy.Propose(drudges, dps.Guid, "dps");
    assert(tankAPlan.OwnsNode && tankBPlan.OwnsNode && dpsPlan.OwnsNode);
    assert(!tankAPlan.TankTarget.IsEmpty());
    assert(!tankBPlan.TankTarget.IsEmpty());
    assert(tankAPlan.TankTarget != tankBPlan.TankTarget);
    assert(dpsPlan.DamageTarget == sourceB.Guid);
    assert(dpsPlan.Movement.has_value());
    assert(dpsPlan.Movement->Resources() == Uses(Resource::Movement));

    // Magmaw keeps trained damage intact while phase-aware target scoring
    // promotes the exposed head and a Pillar marker proposes movement only.
    BotEncounter::Blackboard magmaw = drudges;
    magmaw.Route.NodeId = "bwd.magmaw.encounter";
    magmaw.Hostiles.clear();
    magmaw.Summons.clear();
    BotEncounter::ActorSnapshot magmawBoss = sourceA;
    magmawBoss.Guid = ObjectGuid(HighGuid::Unit, uint32(41570), uint32(70));
    magmawBoss.Entry = 41570;
    magmawBoss.Position = { 20.0f, 0.0f, 0.0f };
    BotEncounter::ActorSnapshot magmawHead = magmawBoss;
    magmawHead.Guid = ObjectGuid(HighGuid::Unit, uint32(42347), uint32(71));
    magmawHead.Entry = 42347;
    magmawHead.Selectable = true;
    magmawHead.Attackable = true;
    BotEncounter::ActorSnapshot pillar = magmawBoss;
    pillar.Guid = ObjectGuid(HighGuid::Unit, uint32(41843), uint32(72));
    pillar.Entry = 41843;
    pillar.Position = dps.Position;
    magmaw.Hostiles = { magmawBoss, magmawHead };
    magmaw.Summons = { pillar };
    BotEncounter::AdaptiveMagmawStrategy magmawStrategy;
    auto magmawPlan = magmawStrategy.Propose(magmaw, dps.Guid, "dps");
    assert(magmawPlan.OwnsNode);
    assert(magmawPlan.DamageTarget == magmawHead.Guid);
    assert(magmawPlan.Movement.has_value());
    assert(magmawPlan.Movement->Resources() == Uses(Resource::Movement));

    // Omnotron uses observed shield/cast state: a shielded construct is not
    // selected for damage, Arcane Annihilator remains independently
    // interruptible, and Conductor isolation claims movement only.
    BotEncounter::Blackboard omnotron = magmaw;
    omnotron.Route.NodeId = "bwd.omnotron.encounter";
    omnotron.Hostiles.clear();
    BotEncounter::ActorSnapshot electron = sourceA;
    electron.Entry = 42179;
    electron.Guid = ObjectGuid(HighGuid::Unit, uint32(42179), uint32(80));
    electron.InCombat = true;
    electron.Auras.push_back({79900, ObjectGuid{}, 1, 0});
    BotEncounter::ActorSnapshot arcanotron = sourceB;
    arcanotron.Entry = 42166;
    arcanotron.Guid = ObjectGuid(HighGuid::Unit, uint32(42166), uint32(81));
    arcanotron.InCombat = true;
    arcanotron.Cast = BotEncounter::CastSnapshot{
        79710, tankA.Guid, 1, false, true };
    omnotron.Hostiles = { electron, arcanotron };
    BotEncounter::ActorSnapshot conductorBot = dps;
    conductorBot.Auras.push_back({79888, ObjectGuid{}, 1, 0});
    omnotron.Players = { tankA, tankB, conductorBot };
    BotEncounter::AdaptiveOmnotronStrategy omnotronStrategy;
    auto omnotronPlan = omnotronStrategy.Propose(
        omnotron, conductorBot.Guid, "dps");
    assert(omnotronPlan.OwnsNode);
    assert(omnotronPlan.DamageTarget == arcanotron.Guid);
    assert(omnotronPlan.InterruptTarget == arcanotron.Guid);
    assert(!omnotronPlan.SuppressOffense);
    assert(omnotronPlan.Movement.has_value());
    assert(omnotronPlan.Movement->Resources() == Uses(Resource::Movement));

    BotEncounter::Blackboard maloriak = omnotron;
    maloriak.Route.NodeId = "bwd.maloriak.encounter";
    maloriak.Hostiles.clear();
    maloriak.Summons.clear();
    BotEncounter::ActorSnapshot maloriakBoss = sourceA;
    maloriakBoss.Entry = 41378;
    maloriakBoss.Guid = ObjectGuid(HighGuid::Unit, uint32(41378), uint32(90));
    maloriakBoss.Cast = BotEncounter::CastSnapshot{
        77896, tankA.Guid, 2, false, true };
    BotEncounter::ActorSnapshot absoluteZero = sourceB;
    absoluteZero.Entry = 41961;
    absoluteZero.Guid = ObjectGuid(HighGuid::Unit, uint32(41961), uint32(91));
    absoluteZero.Position = conductorBot.Position;
    maloriak.Hostiles = { maloriakBoss, absoluteZero };
    BotEncounter::AdaptiveMaloriakStrategy maloriakStrategy;
    auto maloriakPlan = maloriakStrategy.Propose(
        maloriak, conductorBot.Guid, "dps");
    assert(maloriakPlan.OwnsNode);
    assert(maloriakPlan.DamageTarget == maloriakBoss.Guid);
    assert(maloriakPlan.InterruptTarget == maloriakBoss.Guid);
    assert(maloriakPlan.Movement.has_value());

    BotEncounter::Blackboard chimaeron = maloriak;
    chimaeron.Route.NodeId = "bwd.chimaeron.encounter";
    chimaeron.Hostiles.clear();
    BotEncounter::ActorSnapshot chimaeronBoss = sourceA;
    chimaeronBoss.Entry = 43296;
    chimaeronBoss.Guid = ObjectGuid(HighGuid::Unit, uint32(43296), uint32(92));
    chimaeronBoss.Auras.push_back({88872, ObjectGuid{}, 1, 0});
    BotEncounter::ActorSnapshot floorTarget = tankA;
    floorTarget.Health = 9000;
    floorTarget.Auras.push_back({82705, ObjectGuid{}, 1, 0});
    chimaeron.Hostiles = { chimaeronBoss };
    chimaeron.Players = { floorTarget, tankB, conductorBot };
    BotEncounter::AdaptiveChimaeronStrategy chimaeronStrategy;
    auto chimaeronPlan = chimaeronStrategy.Propose(
        chimaeron, conductorBot.Guid, "healer");
    assert(chimaeronPlan.OwnsNode);
    assert(chimaeronPlan.PriorityHealTarget == floorTarget.Guid);
    assert(chimaeronPlan.Movement.has_value());

    BotEncounter::Blackboard atramedes = chimaeron;
    atramedes.Route.NodeId = "bwd.atramedes.encounter";
    atramedes.Hostiles.clear();
    atramedes.Interactables.clear();
    BotEncounter::ActorSnapshot atramedesBoss = sourceA;
    atramedesBoss.Entry = 41442;
    atramedesBoss.Guid = ObjectGuid(HighGuid::Unit, uint32(41442), uint32(93));
    atramedesBoss.Cast = BotEncounter::CastSnapshot{
        77840, ObjectGuid{}, 3, false, false };
    BotEncounter::ActorSnapshot gong = sourceB;
    gong.Entry = 41445;
    gong.Guid = ObjectGuid(HighGuid::Unit, uint32(41445), uint32(94));
    gong.Selectable = true;
    gong.Interactable = true;
    gong.Position = floorTarget.Position;
    atramedes.Hostiles = { atramedesBoss };
    atramedes.Interactables = { gong };
    atramedes.Players = { floorTarget, tankB, conductorBot };
    BotEncounter::AdaptiveAtramedesStrategy atramedesStrategy;
    auto atramedesPlan = atramedesStrategy.Propose(
        atramedes, floorTarget.Guid, "tank");
    assert(atramedesPlan.OwnsNode);
    assert(atramedesPlan.Interaction.has_value());

    BotEncounter::Blackboard nefarian = atramedes;
    nefarian.Route.NodeId = "bwd.nefarian.encounter";
    nefarian.Hostiles.clear();
    nefarian.Summons.clear();
    BotEncounter::ActorSnapshot nefarianBoss = sourceA;
    nefarianBoss.Entry = 41376;
    nefarianBoss.Guid = ObjectGuid(HighGuid::Unit, uint32(41376), uint32(95));
    nefarianBoss.Auras.push_back({81582, ObjectGuid{}, 1, 0});
    BotEncounter::ActorSnapshot prototype = sourceB;
    prototype.Entry = 41948;
    prototype.Guid = ObjectGuid(HighGuid::Unit, uint32(41948), uint32(96));
    prototype.Cast = BotEncounter::CastSnapshot{
        80734, floorTarget.Guid, 4, false, true };
    nefarian.Hostiles = { nefarianBoss, prototype };
    BotEncounter::AdaptiveNefarianStrategy nefarianStrategy;
    auto nefarianPlan = nefarianStrategy.Propose(
        nefarian, floorTarget.Guid, "tank");
    assert(nefarianPlan.OwnsNode);
    assert(nefarianPlan.DamageTarget == prototype.Guid);
    assert(nefarianPlan.InterruptTarget == prototype.Guid);
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
            "-I",
            str(ROOT / "src/common/Debugging"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_live_route_function_does_not_reintroduce_direct_cheat_actions() -> None:
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    start = source.index("bool BotWorldPopulationMgr::TryValidationRouteObjective(")
    end = source.index("\nbool BotWorldPopulationMgr::IsBossContext", start)
    route = source[start:end]
    for forbidden in (
        "ResurrectPlayer(",
        "NearTeleportTo(",
        "TeleportTo(",
        "SetHealth(",
        "SetPower(",
        "AddThreat(",
    ):
        assert forbidden not in route


def test_route_adapter_yields_retryable_holds_and_declared_boss_adds() -> None:
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    start = source.index("bool BotWorldPopulationMgr::TryValidationRouteObjective(")
    end = source.index("\nbool BotWorldPopulationMgr::IsBossContext", start)
    route = source[start:end]

    objective_start = route.index("auto isValidationRouteObjectiveTarget")
    objective_end = route.index("\n    auto findNearestTrashClusterMob", objective_start)
    objective = route[objective_start:objective_end]
    assert "ValidationRouteAddTargetEntries.begin()" in objective
    assert "creature->GetEntry()" in objective

    kernel_start = source.index('route.Key = "world.validation_route"')
    kernel_end = source.index('boss.Key = "world.boss_mechanics"', kernel_start)
    route_adapter = source[kernel_start:kernel_end]
    for retryable_fragment in (
        'action.find("hold")',
        'action.find("wait")',
        'action.find("blocked")',
        'action.find("pending")',
        'action.find("retry")',
        'action.find("failed")',
    ):
        assert retryable_fragment in route_adapter
    assert "targetBeforeRoute" in route_adapter
    assert "stateTargetBeforeRoute" in route_adapter
    resources = route_adapter.split("route.Attempt", 1)[0]
    for resource in (
        "Resource::Movement",
        "Resource::GlobalCooldown",
        "Resource::Cast",
        "Resource::Target",
        "Resource::Interaction",
    ):
        assert resource in resources


def test_boss_adapter_requires_observable_work_and_rejects_stale_focus() -> None:
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    kernel_start = source.index('boss.Key = "world.boss_mechanics"')
    kernel_end = source.index('trash.Key = "world.dungeon_trash"', kernel_start)
    boss_adapter = source[kernel_start:kernel_end]
    assert "previousPathChangeMs" in boss_adapter
    assert "previousCombatAttemptMs" in boss_adapter
    assert "boss_no_observable_effect" in boss_adapter
    assert "boss_action_committed" not in boss_adapter
    resources = boss_adapter.split("boss.Attempt", 1)[0]
    assert "Resource::Movement" in resources
    assert "Resource::Cast" in resources

    route_start = source.index("bool BotWorldPopulationMgr::TryValidationRouteObjective(")
    focus_start = source.index("auto routeUsableValidationFocus", route_start)
    focus_end = source.index("\n    auto routeGroupFocusTarget", focus_start)
    focus_filter = source[focus_start:focus_end]
    assert "isValidationRouteObjectiveTarget" in focus_filter
    assert "isValidationRouteScriptTarget" not in focus_filter


def test_trash_adapter_requires_observable_work_and_yields_passive_waits() -> None:
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    start = source.index('trash.Key = "world.dungeon_trash"')
    end = source.index('combat.Key = "world.profile_combat"', start)
    adapter = source[start:end]

    assert "previousPathChangeMs" in adapter
    assert "previousCombatAttemptMs" in adapter
    assert 'state.LastCombatAttempt.Reason == "no_line_of_sight"' in adapter
    assert "nativeFollowActive" in adapter
    assert 'action.find("wait")' in adapter
    assert 'action.find("readiness")' in adapter
    assert "trash_no_observable_effect" in adapter
    assert "trash_action_committed" not in adapter
    resources = adapter.split("trash.Attempt", 1)[0]
    assert "Resource::Movement" in resources


def test_raid_healing_is_independent_and_does_not_cancel_hazard_movement() -> None:
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    support_start = source.index('support.Key = "raid.support.heal."')
    route_start = source.index('route.Key = "world.validation_route"', support_start)
    support = source[support_start:route_start]
    assert "Resource::GlobalCooldown" in support
    assert "Resource::Cast" in support
    assert "Resource::Movement" not in support
    assert "SelectHealSpell(\n                        bot, healTarget, adaptiveHazardMovementProposed)" in support
    assert '"no_instant_heal_while_moving"' in support

    heal_start = source.index("uint32 BotWorldPopulationMgr::SelectHealSpell")
    heal_end = source.index("bool BotWorldPopulationMgr::TryCastFriendlySpell", heal_start)
    heal = source[heal_start:heal_end]
    assert "instantOnly" in heal
    assert 'candidate.RejectReason = "movement_requires_instant_heal"' in heal


def test_native_route_interactions_use_player_handlers_and_observed_postconditions() -> None:
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    native = (ROOT / "src/server/game/Bots/BotNativeActionIntent.h").read_text(
        encoding="utf-8"
    )
    header = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(
        encoding="utf-8"
    )

    assert "struct GossipOpen" in native
    assert "BotNativeAction::GossipOpen" in source
    assert "HandleGossipHelloOpcode(hello)" in source
    assert "HandleGossipSelectOptionOpcode(select)" in source
    assert "HandleGameObjectUseOpcode(use)" in source
    assert "AI()->DoAction" not in source[source.index(
        "adaptiveNativeRouteOwnsNode"
    ):source.index('route.Key = "world.validation_route"')]

    for field in (
        "NativeInteractionAction",
        "NativeInteractionEntry",
        "NativeInteractionMenus",
        "NativeInteractionOption",
        "NativeCompletionKind",
        "NativeCompletionEntry",
        "NativeCompletionSpellId",
    ):
        assert field in header
        assert field in source

    native_block = source[
        source.index("adaptiveNativeRouteOwnsNode"):
        source.index('route.Key = "world.validation_route"')
    ]
    assert '"gameobject_selectable"' in native_block
    assert '"boss_summoned"' in native_block
    assert '"aura_present"' in native_block
    assert '"creature_aggressive_with_victim"' in native_block
    assert '"creature_grounded_aggressive_or_engaged"' in native_block
    assert 'ValidationRouteTerminalReason =\n                        "native_postcondition"' in native_block
    assert "intro_complete_and_elevator_ready" not in native_block
    assert "player_in_nefarian_arena" not in native_block

    route_adapter = source[
        source.index('route.Key = "world.validation_route"'):
        source.index('boss.Key = "world.boss_mechanics"')
    ]
    assert "adaptiveNativeRouteOwnsNode" in route_adapter
    assert '"native_route_contract_owns_node"' in route_adapter


def test_dungeon_intro_activation_uses_native_area_trigger_opcode() -> None:
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    header = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(
        encoding="utf-8"
    )
    config = (ROOT / "src/server/worldserver/worldserver.conf.dist").read_text(
        encoding="utf-8"
    )
    live_runner = (ROOT / "tools/bot_ml/run_live_bot_validation.py").read_text(
        encoding="utf-8"
    )

    activation = source[
        source.index("auto tryValidationRouteActivation"):
        source.index("auto routeTankFocusTarget")
    ]
    assert "ValidationRouteActivationAreaTriggerId" in header
    assert "BotWorld.ValidationRoute.ActivationAreaTriggerId = 0" in config
    assert 'readInt(routeJson, "activation_area_trigger_id")' in source
    assert '"activation_area_trigger_id"' in live_runner
    assert "sAreaTriggerStore.LookupEntry(triggerId)" in activation
    assert "bot->IsInAreaTriggerRadius(trigger)" in activation
    assert "BotNativeAction::Move" in activation
    assert "BotNativeAction::AreaTrigger" in activation
    assert "struct AreaTrigger" in (ROOT / "src/server/game/Bots/BotNativeActionIntent.h").read_text(
        encoding="utf-8"
    )
    assert "HandleAreaTriggerOpcode(areaTrigger)" in source
    assert '"native_area_trigger_submitted"' in activation
    assert "InstanceScript::SetData" in activation
    assert "->SetData(" not in activation
    assert "SpawnGroupSpawn(" not in activation
    assert "AI()->DoAction(" not in activation
    assert "SummonCreature(" not in activation

    scenario_config = json.loads((
        ROOT / "experiments/configs/validation_scenarios_cata_001.json"
    ).read_text(encoding="utf-8"))
    stonecore_steps = {
        step["label"]: step
        for scenario in scenario_config["scenarios"]
        if scenario["id"] == "stonecore_5n"
        for step in scenario["route"]
    }
    assert stonecore_steps["Corborus"]["activation_area_trigger_id"] == 6076
    assert stonecore_steps["Slabhide"]["activation_area_trigger_id"] == 6070

    generated_routes = [
        json.loads(line)
        for line in (
            ROOT / "dataset/validation_scenarios/validation_routes.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stonecore_routes = {
        route["label"]: route
        for route in generated_routes
        if route["scenario_id"] == "stonecore_5n"
    }
    assert stonecore_routes["Corborus"]["activation_area_trigger_id"] == 6076
    assert stonecore_routes["Slabhide"]["activation_area_trigger_id"] == 6070
    assert "interaction_contract" not in stonecore_routes["Corborus"]
    assert "completion_contract" not in stonecore_routes["Corborus"]
    assert "mechanic_contract" not in stonecore_routes["Corborus"]
