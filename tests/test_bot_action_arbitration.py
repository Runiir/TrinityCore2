from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"


def bot_source(*names: str) -> str:
    return "\n".join((BOTS / name).read_text(encoding="utf-8") for name in names)


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : index]
    raise AssertionError(f"unterminated function: {signature}")


def test_action_and_movement_arbiters_compile_and_replay(tmp_path: Path) -> None:
    source = tmp_path / "arbiter_replay.cpp"
    binary = tmp_path / "arbiter_replay"
    source.write_text(
        r'''
#include "Bots/BotActionArbiter.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotAdaptiveDrudgeStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAdaptiveAtramedesStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotAdaptiveChimaeronStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotAdaptiveMaloriakStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotAdaptiveOmnotronStrategy.h"
#include "Bots/Content/Raids/Shared/Trash/BotAdaptiveRaidTrashStrategy.h"
#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotMovementArbiter.h"
#include "Bots/BotMeleeAutoAttackIntent.h"
#include "Bots/BotNativeActionIntent.h"
#include <cassert>
#include <limits>
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
    Scope uninitialized;
    assert(!ValidScope(uninitialized));
    Scope easternKingdoms{ 0, 0, 0, 0, 0 };
    assert(ValidScope(easternKingdoms));
    Lease easternKingdomsLease;
    Request easternKingdomsMove{ Owner::CombatRange,
        BotMovementArbitration::Priority::Combat, 1100,
        easternKingdoms, 1.0f, 2.0f, 3.0f };
    assert(Evaluate(easternKingdomsLease, easternKingdomsMove, 1000)
        == Decision::Acquire);
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

    // A stale lease never blocks a new intent, even when the replacement is
    // lower priority.  Lease expiry is checked before priority preservation.
    Lease expiredLease = lease;
    expiredLease.ExpiresAtMs = 1000;
    assert(Evaluate(expiredLease, lower, 1001) == Decision::Acquire);

    assert(FromBotActionResult(BotActionResult::Ok).LifecyclePhase
        == Phase::Submitted);
    assert(FromBotActionResult(BotActionResult::GlobalCooldown).Result
        == Disposition::Retryable);

    BotNativeAction::Intent descent = BotNativeAction::NativeDescent{
        10.0f, 20.0f, 30.0f, 15.0f, 25.0f, 30.0f, 9, true };
    assert(BotNativeAction::RequiredResources(descent)
        == Uses(Resource::Movement));
    BotNativeAction::Intent combatResApproach =
        BotNativeAction::CombatResApproach{ ObjectGuid{}, 20484,
            1000, 9000 };
    assert(BotNativeAction::RequiredResources(combatResApproach)
        == Uses(Resource::Movement));
    BotNativeAction::Intent combatResCast =
        BotNativeAction::CombatResCast{ ObjectGuid{}, 20484,
            1000, 9000 };
    assert(BotNativeAction::RequiredResources(combatResCast)
        == Uses(Resource::Movement, Resource::GlobalCooldown,
            Resource::Cast, Resource::Target));
    BotNativeAction::Intent combatResAccept =
        BotNativeAction::CombatResAccept{ ObjectGuid{}, 20484,
            1000, 9000 };
    assert(BotNativeAction::RequiredResources(combatResAccept)
        == Uses(Resource::Interaction, Resource::Target));

    Scope newInstance = scope;
    newInstance.InstanceId = 42;
    Request formationNewInstance{ Owner::Formation,
        BotMovementArbitration::Priority::Formation, 1300, newInstance,
        7.0f, 8.0f, 9.0f };
    assert(Evaluate(lease, formationNewInstance, 1002) == Decision::Acquire);

    // Producers submit in arbitrary order. The kernel applies the hard mask,
    // then ranks by priority and utility/model score. A failed high-priority
    // candidate does not monopolize the tick. An active route movement and a
    // legal DPS cast use independent lanes and both commit in one tick.
    Kernel kernel;
    kernel.Begin(2000);
    bool lowRan = false;
    bool hazardRan = false;
    bool damageRan = false;
    bool maskedRan = false;
    bool duplicateRan = false;
    kernel.Submit(Candidate{
        "active_route_movement", "legacy_route", BotActionArbitration::Priority::RouteMovement, 1.0f, 0.0f, 0.0f,
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
        "legal_dps_cast", "profile", BotActionArbitration::Priority::TrainedDamage, 5.0f, 1.0f, 2.0f,
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
    assert(resolution.CommittedCandidates.front() == "legal_dps_cast");
    assert(resolution.CommittedCandidates.back() == "active_route_movement");
    assert(kernel.LastResolutionJson().find("hard_masked") != std::string::npos);

    // Combat-res approach owns only movement: the owner can keep performing
    // normal stationary damage while closing range. A committed survival
    // movement still preempts the approach without blocking that damage lane.
    Kernel combatResConcurrency;
    combatResConcurrency.Begin(2010);
    bool approachRan = false;
    bool approachDamageRan = false;
    combatResConcurrency.Submit(Candidate{
        "combat_res_approach", "typed_combat_res",
        BotActionArbitration::Priority::Mechanic, 9.0f, 0.0f, 0.0f,
        BotNativeAction::RequiredResources(combatResApproach),
        0, 100, 3000, 5, true, "", [&]
        {
            approachRan = true;
            return Outcome::Progressed("approaching");
        }
    });
    combatResConcurrency.Submit(Candidate{
        "approach_damage", "profile",
        BotActionArbitration::Priority::TrainedDamage, 5.0f, 0.0f, 0.0f,
        Uses(Resource::GlobalCooldown, Resource::Cast, Resource::Target),
        0, 100, 3000, 5, true, "", [&]
        {
            approachDamageRan = true;
            return Outcome::Submitted("damage_cast_submitted");
        }
    });
    Resolution const& combatResResolution = combatResConcurrency.Resolve();
    assert(approachRan);
    assert(approachDamageRan);
    assert(combatResResolution.CommittedCandidates.size() == 2);

    Kernel hazardOverApproach;
    hazardOverApproach.Begin(2020);
    bool survivalMoveRan = false;
    bool blockedApproachRan = false;
    bool hazardDamageRan = false;
    hazardOverApproach.Submit(Candidate{
        "combat_res_approach_hazard", "typed_combat_res",
        BotActionArbitration::Priority::Mechanic, 9.0f, 0.0f, 0.0f,
        BotNativeAction::RequiredResources(combatResApproach),
        0, 100, 3000, 5, true, "", [&]
        {
            blockedApproachRan = true;
            return Outcome::Progressed("must_not_preempt_hazard");
        }
    });
    hazardOverApproach.Submit(Candidate{
        "survival_move", "hazard",
        BotActionArbitration::Priority::Survival, 2.0f, 0.0f, 0.0f,
        Uses(Resource::Movement), 0, 100, 3000, 5, true, "", [&]
        {
            survivalMoveRan = true;
            return Outcome::Submitted("hazard_move_submitted");
        }
    });
    hazardOverApproach.Submit(Candidate{
        "hazard_damage", "profile",
        BotActionArbitration::Priority::TrainedDamage, 5.0f, 0.0f, 0.0f,
        Uses(Resource::GlobalCooldown, Resource::Cast, Resource::Target),
        0, 100, 3000, 5, true, "", [&]
        {
            hazardDamageRan = true;
            return Outcome::Submitted("damage_during_hazard_move");
        }
    });
    Resolution const& hazardResolution = hazardOverApproach.Resolve();
    assert(survivalMoveRan);
    assert(!blockedApproachRan);
    assert(hazardDamageRan);
    assert(hazardResolution.CommittedCandidates.size() == 2);

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

    // The patrol safe-phase wait remains retryable for arbitration, so an
    // independent movement lane can still run in the same tick.
    Kernel patrolWaitRetry;
    patrolWaitRetry.Begin(7300);
    bool patrolWaitAlternativeRan = false;
    patrolWaitRetry.Submit(Candidate{
        "world.validation_route_action", "validation_route_adapter",
        BotActionArbitration::Priority::Mechanic, 3.1f, 0.0f, 0.0f,
        Uses(Resource::GlobalCooldown, Resource::Cast, Resource::Target,
            Resource::Interaction),
        0, 100, 3000, 5, true, "", []
        {
            return Outcome::Retryable(
                "validation_route_patrol_wait_for_safe_phase");
        }
    });
    patrolWaitRetry.Submit(Candidate{
        "independent_movement", "test",
        BotActionArbitration::Priority::TrainedDamage, 1.0f,
        0.0f, 0.0f, Uses(Resource::Movement), 0, 100, 3000, 5, true, "",
        [&]
        {
            patrolWaitAlternativeRan = true;
            return Outcome::Started("independent_movement_started");
        }
    });
    Resolution const& patrolWaitResolution = patrolWaitRetry.Resolve();
    assert(patrolWaitResolution.AnyCommitted);
    assert(patrolWaitAlternativeRan);

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

    // Melee autoattack is a separate persistent resource lane. It resolves
    // independently from movement/GCD work, ignores producer order, and lets
    // a higher-priority suppression prevent a lower-priority start in the
    // same tick.
    BotMeleeAutoAttack::Lane meleeLane;
    meleeLane.Begin(8500);
    BotMeleeAutoAttack::Intent profileStart;
    profileStart.Toggle = BotMeleeAutoAttack::Kind::StartOrSwitch;
    profileStart.IntentOwner = BotMeleeAutoAttack::Owner::Profile;
    profileStart.ActionPriority = BotActionArbitration::Priority::TrainedDamage;
    profileStart.Target = channels.MechanicTarget;
    profileStart.Reason = "profile_melee_autoattack";
    assert(profileStart.Resources() == Uses(Resource::AutoAttackToggle));
    assert(!Conflicts(profileStart.Resources(), Uses(Resource::Movement)));
    assert(!Conflicts(profileStart.Resources(), Uses(Resource::GlobalCooldown)));
    assert(meleeLane.Submit(profileStart));
    BotMeleeAutoAttack::Intent mechanicSuppress;
    mechanicSuppress.Toggle = BotMeleeAutoAttack::Kind::Suppress;
    mechanicSuppress.IntentOwner = BotMeleeAutoAttack::Owner::Mechanic;
    mechanicSuppress.ActionPriority = BotActionArbitration::Priority::Mechanic;
    mechanicSuppress.Reason = "mechanic_hold";
    assert(meleeLane.Submit(mechanicSuppress));
    auto selectedToggle = meleeLane.Resolve();
    assert(selectedToggle);
    assert(selectedToggle->Toggle == BotMeleeAutoAttack::Kind::Suppress);

    // Cross-bot safety work submitted after a peer's scope remains queued
    // across Begin and is consumed by that peer's sole next resolution.
    BotMeleeAutoAttack::Intent queuedStop;
    queuedStop.Toggle = BotMeleeAutoAttack::Kind::Stop;
    queuedStop.IntentOwner = BotMeleeAutoAttack::Owner::Recovery;
    queuedStop.ActionPriority = BotActionArbitration::Priority::Survival;
    queuedStop.Reason = "peer_recovery_hold";
    assert(meleeLane.Submit(queuedStop));
    meleeLane.Begin(8600);
    selectedToggle = meleeLane.Resolve();
    assert(selectedToggle);
    assert(selectedToggle->Toggle == BotMeleeAutoAttack::Kind::Stop);
    assert(!meleeLane.Resolve());

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
    tankA.HealthPct = 100.0f;
    tankB.HealthPct = 100.0f;
    dps.HealthPct = 100.0f;
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
    magmawBoss.Position = { 20.0f, 0.0f, 210.8483f };
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
    assert(!magmawPlan.SuppressOffense);
    assert(magmawPlan.DamageTarget == magmawHead.Guid);
    assert(magmawPlan.Movement.has_value());
    assert(magmawPlan.Movement->Resources() == Uses(Resource::Movement));
    assert(magmawPlan.Movement->Id.ScopeKey == magmaw.CurrentScope.CohortId + ":"
        + std::to_string(magmaw.CurrentScope.AttemptId) + ":"
        + std::to_string(magmaw.CurrentScope.WipeGeneration) + ":"
        + std::to_string(magmaw.CurrentScope.RouteGeneration) + ":"
        + magmaw.CurrentScope.NodeId);
    assert(magmawPlan.Movement->Id.Strategy == "adaptive_magmaw");
    assert(magmawPlan.Movement->Id.Mechanic == "pillar_evade");
    assert(magmawPlan.Movement->Id.Actor == pillar.Guid);
    assert(magmawPlan.Movement->Id.EventGeneration == magmaw.Revision);
    assert(magmawPlan.Movement->ActionPriority
        == BotActionArbitration::Priority::Survival);
    assert(magmawPlan.Movement->Utility == 499.0f);
    assert(magmawPlan.Movement->ExpiresAtMs == magmaw.ObservedAtMs + 750);
    auto const* magmawPillarMove = std::get_if<Move>(
        &magmawPlan.Movement->Action);
    assert(magmawPillarMove);
    assert(magmawPillarMove->X == 16.0f);
    assert(magmawPillarMove->Y == 0.0f);
    assert(magmawPillarMove->Z == dps.Position.Z);

    // An actor inside Pillar keeps the survival escape candidate while the
    // ordinary target channel still selects the nearest parasite add.
    BotEncounter::Blackboard magmawPillarAdd = magmaw;
    BotEncounter::ActorSnapshot pillarAdd = pillar;
    BotEncounter::ActorSnapshot parasiteAtPillar = magmawBoss;
    parasiteAtPillar.Guid = ObjectGuid(HighGuid::Unit, uint32(41806), uint32(76));
    parasiteAtPillar.Entry = BotEncounter::AdaptiveMagmawStrategy::ParasiteEntry;
    parasiteAtPillar.Position = { 2.0f, 0.0f, 0.0f };
    magmawPillarAdd.Hostiles = { magmawBoss, magmawHead, parasiteAtPillar };
    magmawPillarAdd.Summons = { pillarAdd };
    auto magmawPillarAddPlan = magmawStrategy.Propose(
        magmawPillarAdd, dps.Guid, "dps");
    assert(magmawPillarAddPlan.DamageTarget == parasiteAtPillar.Guid);
    assert(magmawPillarAddPlan.Movement.has_value());
    assert(magmawPillarAddPlan.Movement->Id.Mechanic == "pillar_evade");
    assert(magmawPillarAddPlan.Movement->ActionPriority
        == BotActionArbitration::Priority::Survival);

    // Pillar movement owns only Movement, so an independent trained damage
    // action remains committable during the native escape.
    Kernel magmawHazardDps;
    magmawHazardDps.Begin(9050);
    BotActionArbitration::Candidate magmawHazardCandidate;
    magmawHazardCandidate.Key = "magmaw_pillar_escape";
    magmawHazardCandidate.Source = magmawPlan.Movement->Id.Strategy;
    magmawHazardCandidate.ActionPriority = magmawPlan.Movement->ActionPriority;
    magmawHazardCandidate.UtilityScore = magmawPlan.Movement->Utility;
    magmawHazardCandidate.RequiredResources = magmawPlan.Movement->Resources();
    magmawHazardCandidate.ExpiresAtMs = magmawPlan.Movement->ExpiresAtMs;
    magmawHazardCandidate.Attempt = []
    {
        return Outcome::Submitted("pillar_escape_submitted");
    };
    magmawHazardDps.Submit(std::move(magmawHazardCandidate));
    bool magmawDamageRan = false;
    BotActionArbitration::Candidate magmawDamageCandidate;
    magmawDamageCandidate.Key = "magmaw_profile_damage";
    magmawDamageCandidate.Source = "profile";
    magmawDamageCandidate.ActionPriority =
        BotActionArbitration::Priority::TrainedDamage;
    magmawDamageCandidate.UtilityScore = 1.0f;
    magmawDamageCandidate.RequiredResources = Uses(
        Resource::GlobalCooldown, Resource::Cast, Resource::Target);
    magmawDamageCandidate.ExpiresAtMs = 10000;
    magmawDamageCandidate.Attempt = [&]
    {
        magmawDamageRan = true;
        return Outcome::Submitted("instant_damage_submitted");
    };
    magmawHazardDps.Submit(std::move(magmawDamageCandidate));
    Resolution const& magmawHazardDpsResolution = magmawHazardDps.Resolve();
    assert(magmawDamageRan);
    assert(magmawHazardDpsResolution.CommittedCandidates.size() == 2);

    BotEncounter::Blackboard magmawPrepull = magmaw;
    magmawPrepull.Players.front().HealthPct = 93.0f;
    auto magmawPrepullPlan = magmawStrategy.Propose(
        magmawPrepull, dps.Guid, "dps");
    assert(magmawPrepullPlan.OwnsNode);
    assert(magmawPrepullPlan.SuppressOffense);
    assert(magmawPrepullPlan.DamageTarget.IsEmpty());

    // Magmaw can be pulled by a full-health tank from range.  Melee closure
    // belongs to normal post-pull combat movement, not prepull readiness.
    BotEncounter::Blackboard magmawRangedTank = magmaw;
    magmawRangedTank.Summons.clear();
    magmawRangedTank.Hostiles = { magmawBoss };
    magmawRangedTank.Players.front().Position = { 0.0f, 0.0f, 213.87f };
    magmawRangedTank.Players[1].Position = { 60.0f, 0.0f, 0.0f };
    auto magmawRangedTankPlan = magmawStrategy.Propose(
        magmawRangedTank, tankA.Guid, "tank");
    assert(magmawRangedTankPlan.OwnsNode);
    assert(!magmawRangedTankPlan.SuppressOffense);
    assert(magmawRangedTankPlan.DamageTarget == magmawBoss.Guid);
    assert(!magmawRangedTankPlan.Movement.has_value());

    // Health readiness remains a hard prepull gate even when the tank is
    // already close enough to pull.
    BotEncounter::Blackboard magmawInjuredRangedTank = magmawRangedTank;
    magmawInjuredRangedTank.Players[2].HealthPct = 93.0f;
    auto magmawInjuredRangedTankPlan = magmawStrategy.Propose(
        magmawInjuredRangedTank, tankA.Guid, "tank");
    assert(magmawInjuredRangedTankPlan.OwnsNode);
    assert(magmawInjuredRangedTankPlan.SuppressOffense);
    assert(magmawInjuredRangedTankPlan.DamageTarget.IsEmpty());
    assert(!magmawInjuredRangedTankPlan.Movement.has_value());

    BotEncounter::Blackboard magmawDeadMember = magmawRangedTank;
    magmawDeadMember.Players[2].Alive = false;
    auto magmawDeadMemberPlan = magmawStrategy.Propose(
        magmawDeadMember, tankA.Guid, "tank");
    assert(magmawDeadMemberPlan.SuppressOffense);
    assert(magmawDeadMemberPlan.DamageTarget.IsEmpty());
    assert(!magmawDeadMemberPlan.Movement.has_value());

    // The pull remains suppressed until every living ranged DPS and healer is
    // staged at the deterministic back-room stack. Tanks wait in place while
    // the ranged member receives a typed movement candidate.
    BotEncounter::Blackboard magmawStage = magmawRangedTank;
    magmawStage.CurrentScope.AttemptId = 3;
    magmawStage.Route.NavigationHints = {
        { magmawBoss.Position.X - 5.0f, magmawBoss.Position.Y,
            magmawBoss.Position.Z + 1.0f } };
    magmawStage.Players[2].Position = magmawBoss.Position;
    auto rangedStagePlan = magmawStrategy.Propose(
        magmawStage, dps.Guid, "dps");
    auto tankStageWaitPlan = magmawStrategy.Propose(
        magmawStage, tankA.Guid, "tank");
    assert(rangedStagePlan.SuppressOffense);
    assert(rangedStagePlan.Movement.has_value());
    assert(rangedStagePlan.Movement->Id.Mechanic
        == "prepull_ranged_stage");
    assert(tankStageWaitPlan.SuppressOffense);
    assert(!tankStageWaitPlan.Movement.has_value());
    auto const* rangedStageMove = std::get_if<Move>(
        &rangedStagePlan.Movement->Action);
    assert(rangedStageMove);
    magmawStage.Players[2].Position = {
        rangedStageMove->X, rangedStageMove->Y, rangedStageMove->Z };
    auto stagedTankPullPlan = magmawStrategy.Propose(
        magmawStage, tankA.Guid, "tank");
    assert(!stagedTankPullPlan.SuppressOffense);
    assert(stagedTankPullPlan.DamageTarget == magmawBoss.Guid);

    // A nearer immediate hazard cannot replace a pillar movement proposal,
    // while the fallback hazard candidate retains its source-relative identity.
    BotEncounter::Blackboard magmawPillarPriority = magmaw;
    BotEncounter::ActorSnapshot nearbyCrash = magmawBoss;
    nearbyCrash.Guid = ObjectGuid(HighGuid::Unit, uint32(47330), uint32(73));
    nearbyCrash.Entry = BotEncounter::AdaptiveMagmawStrategy::CrashEntry;
    nearbyCrash.Position = { 1.5f, 0.0f, 0.0f };
    magmawPillarPriority.Hostiles.push_back(nearbyCrash);
    auto magmawPillarPriorityPlan = magmawStrategy.Propose(
        magmawPillarPriority, dps.Guid, "dps");
    assert(magmawPillarPriorityPlan.Movement.has_value());
    assert(magmawPillarPriorityPlan.Movement->Id.Mechanic == "pillar_evade");
    assert(magmawPillarPriorityPlan.Movement->Id.Actor == pillar.Guid);

    BotEncounter::Blackboard magmawCrash = magmaw;
    magmawCrash.Summons.clear();
    BotEncounter::ActorSnapshot crash = magmawBoss;
    crash.Guid = ObjectGuid(HighGuid::Unit, uint32(47330), uint32(74));
    crash.Entry = BotEncounter::AdaptiveMagmawStrategy::CrashEntry;
    crash.Position = { 2.0f, 0.0f, 0.0f };
    magmawCrash.Hostiles = { magmawBoss, magmawHead, crash };
    auto magmawCrashPlan = magmawStrategy.Propose(
        magmawCrash, dps.Guid, "dps");
    assert(magmawCrashPlan.Movement.has_value());
    assert(magmawCrashPlan.Movement->Id.ScopeKey == magmawCrash.CurrentScope.Key());
    assert(magmawCrashPlan.Movement->Id.Mechanic == "massive_crash_evade");
    assert(magmawCrashPlan.Movement->Id.Actor == crash.Guid);
    assert(magmawCrashPlan.Movement->Id.EventGeneration == magmawCrash.Revision);
    assert(magmawCrashPlan.Movement->ActionPriority
        == BotActionArbitration::Priority::Survival);
    assert(magmawCrashPlan.Movement->Utility == 450.0f);
    assert(magmawCrashPlan.Movement->ExpiresAtMs
        == magmawCrash.ObservedAtMs + 750);
    assert(magmawCrashPlan.Movement->Resources() == Uses(Resource::Movement));
    auto const* magmawCrashMove = std::get_if<Move>(
        &magmawCrashPlan.Movement->Action);
    assert(magmawCrashMove);
    assert(magmawCrashMove->X == -14.0f);
    assert(magmawCrashMove->Y == 0.0f);
    assert(magmawCrashMove->Z == dps.Position.Z);

    BotEncounter::Blackboard magmawParasite = magmaw;
    magmawParasite.Summons.clear();
    BotEncounter::ActorSnapshot parasite = magmawBoss;
    parasite.Guid = ObjectGuid(HighGuid::Unit, uint32(41806), uint32(75));
    parasite.Entry = BotEncounter::AdaptiveMagmawStrategy::ParasiteEntry;
    parasite.Position = { 2.0f, 0.0f, 0.0f };
    magmawParasite.Hostiles = { magmawBoss, magmawHead, parasite };
    auto magmawParasitePlan = magmawStrategy.Propose(
        magmawParasite, dps.Guid, "dps");
    assert(magmawParasitePlan.Movement.has_value());
    assert(magmawParasitePlan.Movement->Id.ScopeKey
        == magmawParasite.CurrentScope.Key());
    assert(magmawParasitePlan.Movement->Id.Mechanic
        == "parasite_contact_evade");
    assert(magmawParasitePlan.Movement->Id.Actor == parasite.Guid);
    assert(magmawParasitePlan.Movement->Id.EventGeneration
        == magmawParasite.Revision);
    assert(magmawParasitePlan.Movement->ActionPriority
        == BotActionArbitration::Priority::Survival);
    assert(magmawParasitePlan.Movement->Utility == 450.0f);
    assert(magmawParasitePlan.Movement->ExpiresAtMs
        == magmawParasite.ObservedAtMs + 750);
    assert(magmawParasitePlan.Movement->Resources()
        == Uses(Resource::Movement));
    auto const* magmawParasiteMove = std::get_if<Move>(
        &magmawParasitePlan.Movement->Action);
    assert(magmawParasiteMove);
    assert(magmawParasiteMove->X == -14.0f);
    assert(magmawParasiteMove->Y == 0.0f);
    assert(magmawParasiteMove->Z == dps.Position.Z);

    // Every observed parasite outranks the boss for ranged damage even beyond
    // the old 30-yard cutoff. During the exposed-head window tanks also use
    // the vulnerable head instead of continuing on Magmaw's armored body.
    BotEncounter::Blackboard magmawDistantParasite = magmaw;
    magmawDistantParasite.Summons.clear();
    parasite.Position = { 80.0f, 0.0f, 0.0f };
    magmawDistantParasite.Hostiles = { magmawBoss, magmawHead, parasite };
    auto distantParasitePlan = magmawStrategy.Propose(
        magmawDistantParasite, dps.Guid, "dps");
    auto exposedHeadTankPlan = magmawStrategy.Propose(
        magmawDistantParasite, tankA.Guid, "tank");
    assert(distantParasitePlan.DamageTarget == parasite.Guid);
    assert(exposedHeadTankPlan.DamageTarget == magmawHead.Guid);

    // Ranged players switch to the back-room stack farthest from Pillar, then
    // restore the nearest legal stack after an unrelated displacement.
    BotEncounter::Blackboard magmawRangedPillar = magmawStage;
    magmawRangedPillar.NativeBossState = "in_progress";
    magmawRangedPillar.Hostiles.front().InCombat = true;
    magmawRangedPillar.Hostiles.front().VictimGuid = tankA.Guid;
    magmawRangedPillar.Summons = { pillar };
    magmawRangedPillar.Summons.front().Position =
        magmawRangedPillar.Players[2].Position;
    auto rangedPillarPlan = magmawStrategy.Propose(
        magmawRangedPillar, dps.Guid, "dps");
    assert(rangedPillarPlan.Movement.has_value());
    assert(rangedPillarPlan.Movement->Id.Mechanic
        == "pillar_bait_switch");
    auto const* rangedPillarMove = std::get_if<Move>(
        &rangedPillarPlan.Movement->Action);
    assert(rangedPillarMove);
    assert(std::hypot(rangedPillarMove->X
            - magmawRangedPillar.Summons.front().Position.X,
        rangedPillarMove->Y
            - magmawRangedPillar.Summons.front().Position.Y) > 12.0f);

    // Once the ranged actor is already at the selected safe anchor, the
    // observed Pillar must not churn a matching movement request.
    magmawRangedPillar.Players[2].Position = {
        rangedPillarMove->X, rangedPillarMove->Y, rangedPillarMove->Z };
    auto rangedPillarStablePlan = magmawStrategy.Propose(
        magmawRangedPillar, dps.Guid, "dps");
    assert(!rangedPillarStablePlan.Movement.has_value());

    // Tank handling remains source-relative and does not inherit ranged
    // anchor switching. A tank placed inside Pillar still gets its existing
    // survival movement candidate.
    BotEncounter::Blackboard magmawTankPillar = magmawRangedPillar;
    magmawTankPillar.Players[0].Position =
        magmawTankPillar.Summons.front().Position;
    auto tankPillarPlan = magmawStrategy.Propose(
        magmawTankPillar, tankA.Guid, "tank");
    assert(tankPillarPlan.Movement.has_value());
    assert(tankPillarPlan.Movement->Id.Mechanic == "pillar_evade");
    assert(tankPillarPlan.Movement->ActionPriority
        == BotActionArbitration::Priority::Survival);

    BotEncounter::Blackboard magmawFormationRestore = magmawRangedPillar;
    magmawFormationRestore.Summons.clear();
    magmawFormationRestore.Players[2].Position = magmawBoss.Position;
    auto restorePlan = magmawStrategy.Propose(
        magmawFormationRestore, dps.Guid, "dps");
    assert(restorePlan.Movement.has_value());
    assert(restorePlan.Movement->Id.Mechanic
        == "ranged_formation_restore");

    // Hook users are sorted by raw GUID and only the first two may submit a
    // native hook. Vehicle actions and free-pincer mounting remain separate
    // interaction candidates with their original resource lanes.
    BotEncounter::Blackboard magmawHook = magmaw;
    magmawHook.NativeBossState = "in_progress";
    magmawHook.Players.clear();
    BotEncounter::ActorSnapshot hookBot = dps;
    hookBot.Guid = ObjectGuid(HighGuid::Player, uint32(100));
    hookBot.Role = "dps";
    hookBot.VehicleGuid = ObjectGuid(HighGuid::Unit, uint32(41620), uint32(101));
    BotEncounter::ActorSnapshot secondHookBot = hookBot;
    secondHookBot.Guid = ObjectGuid(HighGuid::Player, uint32(200));
    secondHookBot.VehicleGuid = ObjectGuid{};
    BotEncounter::ActorSnapshot nonHookBot = hookBot;
    nonHookBot.Guid = ObjectGuid(HighGuid::Player, uint32(300));
    nonHookBot.Role = "healer";
    magmawHook.Players = { secondHookBot, hookBot, nonHookBot };
    magmawHook.Hostiles = { magmawBoss, magmawHead };
    BotEncounter::ActorSnapshot leftPincer = magmawBoss;
    leftPincer.Guid = ObjectGuid(HighGuid::Unit, uint32(41620), uint32(101));
    leftPincer.Entry = BotEncounter::AdaptiveMagmawStrategy::PincerLeftEntry;
    BotEncounter::ActorSnapshot spike = magmawBoss;
    spike.Guid = ObjectGuid(HighGuid::Unit, uint32(41767), uint32(102));
    spike.Entry = BotEncounter::AdaptiveMagmawStrategy::SpikeEntry;
    magmawHook.Summons = { leftPincer, spike };
    auto leftHookPlan = magmawStrategy.Propose(
        magmawHook, hookBot.Guid, "dps");
    assert(leftHookPlan.Interaction.has_value());
    assert(leftHookPlan.Interaction->Id.ScopeKey == magmawHook.CurrentScope.Key());
    assert(leftHookPlan.Interaction->Id.Strategy == "adaptive_magmaw");
    assert(leftHookPlan.Interaction->Id.Mechanic == "launch_native_hook");
    assert(leftHookPlan.Interaction->Id.Actor == spike.Guid);
    assert(leftHookPlan.Interaction->Id.EventGeneration == magmawHook.Revision);
    assert(leftHookPlan.Interaction->ActionPriority
        == BotActionArbitration::Priority::Mechanic);
    assert(leftHookPlan.Interaction->Utility == 400.0f);
    assert(leftHookPlan.Interaction->ExpiresAtMs == magmawHook.ObservedAtMs + 500);
    assert(leftHookPlan.Interaction->Resources()
        == Uses(Resource::Cast, Resource::Target));
    auto const* leftHook = std::get_if<VehicleAction>(
        &leftHookPlan.Interaction->Action);
    assert(leftHook && leftHook->SpellId == 77917u
        && leftHook->Target == spike.Guid);

    BotEncounter::Blackboard magmawRightHook = magmawHook;
    magmawRightHook.Summons.front().Entry =
        BotEncounter::AdaptiveMagmawStrategy::PincerRightEntry;
    auto rightHookPlan = magmawStrategy.Propose(
        magmawRightHook, hookBot.Guid, "dps");
    assert(rightHookPlan.Interaction.has_value());
    auto const* rightHook = std::get_if<VehicleAction>(
        &rightHookPlan.Interaction->Action);
    assert(rightHook && rightHook->SpellId == 77941u
        && rightHook->Target == spike.Guid);
    auto nonHookPlan = magmawStrategy.Propose(
        magmawHook, nonHookBot.Guid, "healer");
    assert(!nonHookPlan.Interaction.has_value());

    // Assigned hook users approach the native spell-click window before
    // mounting; ordinary ranged formation cannot keep them at the back wall.
    BotEncounter::Blackboard magmawHookApproach = magmawHook;
    magmawHookApproach.Route.NavigationHints = {
        { magmawBoss.Position.X - 5.0f, magmawBoss.Position.Y,
            magmawBoss.Position.Z + 1.0f } };
    magmawHookApproach.Summons.clear();
    magmawHookApproach.Hostiles.front().Interactable = true;
    magmawHookApproach.Players[1].VehicleGuid = ObjectGuid{};
    magmawHookApproach.Players[1].Position = {
        magmawBoss.Position.X - 30.0f, magmawBoss.Position.Y,
        magmawBoss.Position.Z };
    auto hookApproachPlan = magmawStrategy.Propose(
        magmawHookApproach, hookBot.Guid, "dps");
    // Always offer the native click while Magmaw is interactable. The native
    // executor owns effective range validation, so a distant click retries
    // without displacing the simultaneous approach movement.
    assert(hookApproachPlan.Interaction.has_value());
    assert(hookApproachPlan.Interaction->Id.Mechanic
        == "mount_free_pincer");
    assert(std::holds_alternative<SpellClick>(
        hookApproachPlan.Interaction->Action));
    assert(hookApproachPlan.Movement.has_value());
    assert(hookApproachPlan.Movement->Id.Mechanic == "pincer_approach");
    auto const* hookApproachMove = std::get_if<Move>(
        &hookApproachPlan.Movement->Action);
    assert(hookApproachMove);
    assert(std::hypot(hookApproachMove->X - magmawBoss.Position.X,
        hookApproachMove->Y - magmawBoss.Position.Y)
        < BotEncounter::AdaptiveMagmawStrategy::HookInteractionDistance);

    // The native Mangle warning gives only the deterministic hook pair time
    // to stage at the ordinary spell-click distance.  The warning is observed
    // from native player aura state, while the open interaction window below
    // still owns the existing approach and mount path.
    BotEncounter::Blackboard magmawPincerPreposition = magmawHookApproach;
    magmawPincerPreposition.Hostiles.front().Interactable = false;
    magmawPincerPreposition.Players[0].Position = {
        magmawBoss.Position.X - 20.0f, magmawBoss.Position.Y, 0.0f };
    magmawPincerPreposition.Players[1].Position = {
        magmawBoss.Position.X - 25.0f, magmawBoss.Position.Y, 0.0f };
    magmawPincerPreposition.Players[2].Position = { -10.0f, 8.0f, 0.0f };
    magmawPincerPreposition.Players[2].Auras = {
        BotEncounter::AuraSnapshot{ 89773u, ObjectGuid{}, 1, 0 } };
    BotEncounter::Blackboard magmawPincerWarningParasite =
        magmawPincerPreposition;
    BotEncounter::ActorSnapshot warningParasite = magmawBoss;
    warningParasite.Guid = ObjectGuid(HighGuid::Unit, uint32(41806),
        uint32(109));
    warningParasite.Entry = BotEncounter::AdaptiveMagmawStrategy::ParasiteEntry;
    warningParasite.Position = { magmawBoss.Position.X - 24.0f,
        magmawBoss.Position.Y, magmawBoss.Position.Z };
    magmawPincerWarningParasite.Hostiles.push_back(warningParasite);
    auto prepositionPlan = magmawStrategy.Propose(
        magmawPincerWarningParasite, hookBot.Guid, "dps");
    assert(prepositionPlan.Movement.has_value());
    assert(prepositionPlan.Movement->Id.Mechanic
        == "pincer_preposition");
    assert(prepositionPlan.Movement->ActionPriority
        == BotActionArbitration::Priority::Mechanic);
    auto const* prepositionMove = std::get_if<Move>(
        &prepositionPlan.Movement->Action);
    assert(prepositionMove);
    assert(std::hypot(prepositionMove->X - magmawBoss.Position.X,
        prepositionMove->Y - magmawBoss.Position.Y)
        <= BotEncounter::AdaptiveMagmawStrategy::HookInteractionDistance);

    // The alternate native Mangle aura is equivalent, and a non-assigned
    // ranged player keeps ordinary formation behavior instead of staging.
    BotEncounter::Blackboard alternateMangle = magmawPincerPreposition;
    alternateMangle.Players[2].Auras.front().SpellId = 78412u;
    auto alternatePrepositionPlan = magmawStrategy.Propose(
        alternateMangle, secondHookBot.Guid, "dps");
    assert(alternatePrepositionPlan.Movement.has_value());
    assert(alternatePrepositionPlan.Movement->Id.Mechanic
        == "pincer_preposition");
    auto nonAssignedWarningPlan = magmawStrategy.Propose(
        alternateMangle, nonHookBot.Guid, "healer");
    assert(!nonAssignedWarningPlan.Movement.has_value()
        || nonAssignedWarningPlan.Movement->Id.Mechanic
            != "pincer_preposition");

    // Without a warning, the assigned user remains on normal ranged
    // formation logic. A warning-local Pillar retains survival ownership over
    // prepositioning and never turns into a mechanic-owned move.
    BotEncounter::Blackboard noPincerWarning = magmawPincerPreposition;
    noPincerWarning.Players[2].Auras.clear();
    auto noWarningPlan = magmawStrategy.Propose(
        noPincerWarning, hookBot.Guid, "dps");
    assert(noWarningPlan.Movement.has_value());
    assert(noWarningPlan.Movement->Id.Mechanic
        == "ranged_formation_restore");

    BotEncounter::Blackboard crashWarning = noPincerWarning;
    BotEncounter::ActorSnapshot crashWarningActor = magmawBoss;
    crashWarningActor.Guid = ObjectGuid(HighGuid::Unit, uint32(47330),
        uint32(108));
    crashWarningActor.Entry = BotEncounter::AdaptiveMagmawStrategy::CrashEntry;
    crashWarningActor.Position = {
        magmawBoss.Position.X + 20.0f, magmawBoss.Position.Y, 0.0f };
    crashWarning.Hostiles.push_back(crashWarningActor);
    auto crashPrepositionPlan = magmawStrategy.Propose(
        crashWarning, hookBot.Guid, "dps");
    assert(crashPrepositionPlan.Movement.has_value());
    assert(crashPrepositionPlan.Movement->Id.Mechanic
        == "pincer_preposition");

    // A warning does not suppress immediate Crash survival. When the native
    // telegraph is already within the existing 12-yard escape radius, that
    // Survival candidate wins over mechanic prepositioning.
    BotEncounter::Blackboard immediateCrash = magmawPincerPreposition;
    BotEncounter::ActorSnapshot immediateCrashActor = crashWarningActor;
    immediateCrashActor.Position = {
        immediateCrash.Players[1].Position.X + 2.0f,
        immediateCrash.Players[1].Position.Y, 0.0f };
    immediateCrash.Hostiles.push_back(immediateCrashActor);
    auto immediateCrashPlan = magmawStrategy.Propose(
        immediateCrash, hookBot.Guid, "dps");
    assert(immediateCrashPlan.Movement.has_value());
    assert(immediateCrashPlan.Movement->Id.Mechanic
        == "massive_crash_evade");
    assert(immediateCrashPlan.Movement->ActionPriority
        == BotActionArbitration::Priority::Survival);

    BotEncounter::Blackboard warningPillar = magmawPincerPreposition;
    BotEncounter::ActorSnapshot warningPillarActor = magmawBoss;
    warningPillarActor.Guid = ObjectGuid(HighGuid::Unit, uint32(41843),
        uint32(107));
    warningPillarActor.Entry = BotEncounter::AdaptiveMagmawStrategy::PillarEntry;
    warningPillarActor.Position = warningPillar.Players[1].Position;
    warningPillar.Summons = { warningPillarActor };
    auto warningPillarPlan = magmawStrategy.Propose(
        warningPillar, hookBot.Guid, "dps");
    assert(warningPillarPlan.Movement.has_value());
    assert(warningPillarPlan.Movement->ActionPriority
        == BotActionArbitration::Priority::Survival);
    assert(warningPillarPlan.Movement->Id.Mechanic
        != "pincer_preposition");

    // An open pincer remains the movement owner when Crash and a parasite
    // compete for the same assigned ranged user.  A local Pillar still
    // preempts that ownership, even when an older/farther Pillar is listed
    // first in the observed summons.
    BotEncounter::Blackboard magmawPincerHazards = magmawHookApproach;
    BotEncounter::ActorSnapshot competingCrash = magmawBoss;
    competingCrash.Guid = ObjectGuid(HighGuid::Unit, uint32(47330), uint32(103));
    competingCrash.Entry = BotEncounter::AdaptiveMagmawStrategy::CrashEntry;
    competingCrash.Position = { -8.0f, 0.0f, magmawBoss.Position.Z };
    BotEncounter::ActorSnapshot competingParasite = magmawBoss;
    competingParasite.Guid = ObjectGuid(HighGuid::Unit, uint32(41806), uint32(104));
    competingParasite.Entry = BotEncounter::AdaptiveMagmawStrategy::ParasiteEntry;
    competingParasite.Position = { -6.0f, 0.0f, magmawBoss.Position.Z };
    magmawPincerHazards.Hostiles.push_back(competingCrash);
    magmawPincerHazards.Hostiles.push_back(competingParasite);
    auto competingHazardsPlan = magmawStrategy.Propose(
        magmawPincerHazards, hookBot.Guid, "dps");
    assert(competingHazardsPlan.Movement.has_value());
    assert(competingHazardsPlan.Movement->Id.Mechanic == "pincer_approach");

    BotEncounter::Blackboard magmawPincerPillar = magmawPincerHazards;
    BotEncounter::ActorSnapshot distantPillar = magmawBoss;
    distantPillar.Guid = ObjectGuid(HighGuid::Unit, uint32(41843), uint32(105));
    distantPillar.Entry = BotEncounter::AdaptiveMagmawStrategy::PillarEntry;
    distantPillar.Position = { 40.0f, 0.0f, magmawBoss.Position.Z };
    BotEncounter::ActorSnapshot localPillar = distantPillar;
    localPillar.Guid = ObjectGuid(HighGuid::Unit, uint32(41843), uint32(106));
    localPillar.Position = magmawPincerPillar.Players[1].Position;
    magmawPincerPillar.Summons = { distantPillar, localPillar };
    auto competingPillarPlan = magmawStrategy.Propose(
        magmawPincerPillar, hookBot.Guid, "dps");
    assert(competingPillarPlan.Movement.has_value());
    assert(competingPillarPlan.Movement->Id.Mechanic == "pillar_evade");
    assert(competingPillarPlan.Movement->Id.Actor == localPillar.Guid);
    assert(competingPillarPlan.Movement->ActionPriority
        == BotActionArbitration::Priority::Survival);

    BotEncounter::Blackboard magmawMount = magmawHook;
    magmawMount.Summons.clear();
    magmawMount.Hostiles.front().Interactable = true;
    magmawMount.Players[1].VehicleGuid = ObjectGuid{};
    // This is outside the strategy's old five-yard center gate but inside
    // the native spell-click envelope supplied by Magmaw's combat reach.
    magmawMount.Players[1].Position = {
        magmawBoss.Position.X + 6.7f, magmawBoss.Position.Y,
        magmawBoss.Position.Z };
    auto mountPlan = magmawStrategy.Propose(
        magmawMount, hookBot.Guid, "dps");
    assert(mountPlan.Interaction.has_value());
    assert(mountPlan.Interaction->Id.ScopeKey == magmawMount.CurrentScope.Key());
    assert(mountPlan.Interaction->Id.Mechanic == "mount_free_pincer");
    assert(mountPlan.Interaction->Id.Actor == magmawBoss.Guid);
    assert(mountPlan.Interaction->ActionPriority
        == BotActionArbitration::Priority::Mechanic);
    assert(mountPlan.Interaction->Utility == 350.0f);
    assert(mountPlan.Interaction->ExpiresAtMs == magmawMount.ObservedAtMs + 500);
    assert(mountPlan.Interaction->Resources() == Uses(Resource::Interaction));
    auto const* mount = std::get_if<SpellClick>(
        &mountPlan.Interaction->Action);
    assert(mount && mount->Target == magmawBoss.Guid);

    BotEncounter::Blackboard magmawNativeInProgress = magmawRangedTank;
    magmawNativeInProgress.NativeBossState = "in_progress";
    magmawNativeInProgress.Hostiles = { magmawBoss, magmawHead };
    auto magmawNativeInProgressPlan = magmawStrategy.Propose(
        magmawNativeInProgress, dps.Guid, "dps");
    assert(magmawNativeInProgressPlan.OwnsNode);
    assert(!magmawNativeInProgressPlan.SuppressOffense);
    assert(magmawNativeInProgressPlan.DamageTarget == magmawHead.Guid);

    BotEncounter::Blackboard magmawInCombat = magmawPrepull;
    magmawInCombat.Hostiles.front().InCombat = true;
    magmawInCombat.Hostiles.front().VictimGuid = tankA.Guid;
    auto magmawInCombatPlan = magmawStrategy.Propose(
        magmawInCombat, dps.Guid, "dps");
    assert(magmawInCombatPlan.OwnsNode);
    assert(!magmawInCombatPlan.SuppressOffense);
    assert(magmawInCombatPlan.DamageTarget == magmawHead.Guid);

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
    main = bot_source("BotWorldPopulationMgr.cpp")
    route = "\n".join((
        function_body(main, "bool BotWorldPopulationMgr::TryValidationRouteObjective("),
        function_body(
            bot_source("BotWorldPopulationMgrValidationRouteGate.cpp"),
            "bool BotWorldPopulationMgr::TryValidationRouteObjectiveGate(",
        ),
    ))
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
    targeting = function_body(
        bot_source("BotWorldPopulationMgrValidationTargeting.cpp"),
        "BotWorldPopulationMgr::BuildValidationRouteTargetingContext("
    )

    objective_start = targeting.index("auto isValidationRouteObjectiveTarget")
    objective_end = targeting.index(
        "\n    auto findCurrentDiscoveryScriptedEventTarget", objective_start
    )
    objective = targeting[objective_start:objective_end]
    assert "ValidationRouteAddTargetEntries.begin()" in objective
    assert "creature->GetEntry()" in objective

    fallback = bot_source("BotWorldPopulationMgrUpdateBotKernelFallback.cpp")
    route_adapter = function_body(
        fallback,
        "void BotWorldPopulationMgr::SubmitValidationKernelFallbackCandidates(",
    )
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
    movement_start = route_adapter.index("routeMovement.RequiredResources")
    movement_end = route_adapter.index("routeMovement.Attempt", movement_start)
    movement_resources = route_adapter[movement_start:movement_end]
    assert "Resource::Movement" in movement_resources
    for resource in (
        "Resource::GlobalCooldown",
        "Resource::Cast",
        "Resource::Target",
        "Resource::Interaction",
    ):
        assert resource not in movement_resources

    action_start = route_adapter.index(
        "BotActionArbitration::ResourceMask routeActionResources"
    )
    action_end = route_adapter.index("routeAction.Attempt", action_start)
    action_resources = route_adapter[action_start:action_end]
    for resource in (
        "Resource::GlobalCooldown",
        "Resource::Cast",
        "Resource::Target",
        "Resource::Interaction",
    ):
        assert resource in action_resources
    base_action_resources = action_resources[: action_resources.index(
        "if (typedDrudgeValidationRoute"
    )]
    assert "Resource::Movement" not in base_action_resources
    assert "!context.DrudgeCombatAuthorityAllowed" in action_resources
    assert "Resource::Movement" in action_resources
    assert "std::shared_ptr<RouteAttempt>" in route_adapter
    assert "auto runRoute = [this, &context, routeAttempt" in route_adapter
    assert "routeAction.Attempt = [runRoute, routeAttempt]" in route_adapter
    assert "routeMovement.Attempt = [runRoute, routeAttempt]" in route_adapter


def test_patrol_safe_phase_hold_preserves_explicit_route_wait_only() -> None:
    fallback = bot_source("BotWorldPopulationMgrUpdateBotKernelFallback.cpp")
    route_adapter = function_body(
        fallback,
        "void BotWorldPopulationMgr::SubmitValidationKernelFallbackCandidates(",
    )
    assert 'context.Action\n                        == "validation_route_patrol_wait_for_safe_phase"' in route_adapter
    assert 'context.State.LastRecoveryMode =\n                            "validation_route_wait";' in route_adapter
    assert "context.State.LastRecoveryResult = context.Action;" in route_adapter
    assert "Outcome::Retryable" in route_adapter

    decision = bot_source("BotWorldPopulationMgrUpdateBotDecision.cpp")
    assert 'context.State.LastDecisionHandler == "validation_route"' in decision
    assert 'context.Action == "validation_route_patrol_wait_for_safe_phase"' in decision
    assert 'context.State.LastRecoveryMode = "validation_route_wait";' in decision
    assert 'context.State.LastRecoveryResult = "no_candidate_committed";' in decision


def test_boss_adapter_requires_observable_work_and_rejects_stale_focus() -> None:
    fallback = bot_source("BotWorldPopulationMgrUpdateBotKernelFallback.cpp")
    boss_start = fallback.index('boss.Key = "world.boss_mechanics"')
    boss_end = fallback.index('trash.Key = "world.dungeon_trash"', boss_start)
    boss_adapter = fallback[boss_start:boss_end]
    assert "previousPathChangeMs" in boss_adapter
    assert "previousCombatAttemptMs" in boss_adapter
    assert "boss_no_observable_effect" in boss_adapter
    assert "boss_action_committed" not in boss_adapter
    assert "BossMechanicActionResult& bossAction = context.BossAction;" in boss_adapter
    resources = boss_adapter.split("boss.Attempt", 1)[0]
    assert "Resource::Movement" in resources
    assert "Resource::Cast" in resources

    focus = function_body(
        bot_source("BotWorldPopulationMgrValidationFocus.cpp"),
        "BotWorldPopulationMgr::BuildValidationRouteFocusContext("
    )
    focus_start = focus.index("auto routeUsableValidationFocus")
    focus_end = focus.index("\n    auto routeGroupFocusTarget", focus_start)
    focus_filter = focus[focus_start:focus_end]
    assert "targeting.IsObjectiveTarget" in focus_filter
    assert "targeting.IsScriptTarget" not in focus_filter


def test_trash_adapter_requires_observable_work_and_yields_passive_waits() -> None:
    fallback = bot_source("BotWorldPopulationMgrUpdateBotKernelFallback.cpp")
    start = fallback.index('trash.Key = "world.dungeon_trash"')
    end = fallback.index('combat.Key = "world.profile_combat"', start)
    adapter = fallback[start:end]

    assert "previousPathChangeMs" in adapter
    assert "previousCombatAttemptMs" in adapter
    assert "DungeonTrashActionResult& trashAction = context.TrashAction;" in adapter
    assert 'context.State.LastCombatAttempt.Reason == "no_line_of_sight"' in adapter
    assert "nativeFollowActive" in adapter
    assert 'context.Action.find("wait")' in adapter
    assert 'context.Action.find("readiness")' in adapter
    assert "trash_no_observable_effect" in adapter
    assert "trash_action_committed" not in adapter
    resources = adapter.split("trash.Attempt", 1)[0]
    assert "Resource::Movement" in resources


def test_raid_healing_is_independent_and_does_not_cancel_hazard_movement() -> None:
    candidates = bot_source("BotWorldPopulationMgrUpdateBotKernelCandidates.cpp")
    support_start = candidates.index('support.Key = "raid.support.heal."')
    support = candidates[support_start:]
    assert "Resource::GlobalCooldown" in support
    assert "Resource::Cast" in support
    assert "Resource::Movement" not in support
    assert '#include "MotionMaster.h"' in candidates
    assert "auto activeNativeMovementPath = [&]()" in candidates
    assert "context.State.ActivePathValid" in candidates
    assert "context.State.ActivePathAttemptId != Cohort().AttemptId" in candidates
    assert "context.State.IsMoving || context.Bot->isMoving()" in candidates
    assert "GetMotionSlotType(MOTION_SLOT_ACTIVE)" in candidates
    assert "MovementLease.ExpiresAtMs" not in candidates[
        candidates.index("auto activeNativeMovementPath = [&]()") : support_start
    ]
    support_capture = support.split("support.Attempt = ", 1)[1].split("()", 1)[0]
    assert "activeNativeMovementPath" in support_capture
    assert "&activeNativeMovementPath" not in support_capture
    assert "bool const instantHealRequired =" in support
    assert "adaptiveHazardMovementProposed\n                        || activeNativeMovementPath()" in support
    assert "SelectHealSpell(\n                        context.Bot, healTarget, instantHealRequired)" in support
    assert support.index("activeNativeMovementPath()") < support.index("SelectHealSpell(")
    assert '"adaptive_heal_resolve"' in support
    assert '"adaptive_heal_cast"' in support
    assert support.index("SelectHealSpell(") < support.index("TryCastFriendlySpell(")
    assert '"no_instant_heal_while_moving"' in support

    combat_support = bot_source("BotWorldPopulationMgrCombatSupport.cpp")
    heal = function_body(
        combat_support, "uint32 BotWorldPopulationMgr::SelectHealSpell("
    )
    assert "instantOnly" in heal
    assert 'candidate.RejectReason = "movement_requires_instant_heal"' in heal


def test_magmaw_movement_adapter_maps_typed_leases_and_fails_closed() -> None:
    candidates = bot_source("BotWorldPopulationMgrUpdateBotKernelCandidates.cpp")
    helper_start = candidates.index("struct AdaptiveMagmawMovementLease")
    helper_end = candidates.index(
        "void BotWorldPopulationMgr::SubmitAdaptiveKernelCandidates",
        helper_start,
    )
    helper = candidates[helper_start:helper_end]

    mechanic_start = helper.index('if (mechanic == "prepull_ranged_stage"')
    mechanic = helper[mechanic_start:]
    for mechanic_name in (
        "prepull_ranged_stage",
        "ranged_formation_restore",
        "pincer_preposition",
        "pincer_approach",
    ):
        assert f'"{mechanic_name}"' in mechanic
    assert "Owner::Mechanic" in mechanic
    assert "Priority::Mechanic" in mechanic

    hazard_start = helper.index('if (mechanic == "pillar_evade"')
    hazard = helper[hazard_start:]
    assert "prepull_health_suppress" in bot_source(
        "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp"
    )
    for mechanic in (
        "pillar_evade",
        "pillar_bait_switch",
        "massive_crash_evade",
        "parasite_contact_evade",
    ):
        assert f'"{mechanic}"' in hazard
    assert "Owner::Hazard" in hazard
    assert "Priority::Hazard" in hazard
    assert "return std::nullopt;" in hazard

    movement_start = candidates.index(
        "if (context.AdaptiveMagmawMovement"
    )
    movement_end = candidates.index(
        "if (context.AdaptiveMagmawInteraction", movement_start
    )
    movement = candidates[movement_start:movement_end]
    assert "AdaptiveMagmawMovementLeaseFor(intent.Id.Mechanic)" in movement
    assert "if (movementLease)" in movement
    assert "lease = *movementLease" in movement
    assert "mechanic = intent.Id.Mechanic" in movement
    assert "lease.Owner" in movement
    assert "lease.Priority" in movement
    assert "context.Action = mechanic;" in movement
    assert 'context.Action = "pillar_evade"' not in movement
    for assignment in (
        "movement.Key = intent.Id.Key();",
        "movement.Source = intent.Id.Strategy;",
        "movement.ActionPriority = intent.ActionPriority;",
        "movement.UtilityScore = intent.Utility;",
        "movement.RequiredResources = intent.Resources();",
        "movement.ExpiresAtMs = intent.ExpiresAtMs;",
    ):
        assert assignment in movement
    assert movement.index("if (movementLease)") < movement.index(
        "context.State.DecisionKernel.Submit(std::move(movement));"
    )


def test_native_route_interactions_use_player_handlers_and_observed_postconditions() -> None:
    native_action = bot_source("BotWorldPopulationMgrNativeAction.cpp")
    preparation = bot_source("BotWorldPopulationMgrUpdateBotKernelPreparation.cpp")
    runtime = bot_source("BotWorldPopulationMgrValidationRouteRuntime.cpp")
    manifest = bot_source("BotWorldPopulationMgrValidationRouteManifest.cpp")
    source = "\n".join((native_action, preparation, runtime, manifest))
    native = (ROOT / "src/server/game/Bots/BotNativeActionIntent.h").read_text(
        encoding="utf-8"
    )
    header = bot_source(
        "BotWorldPopulationMgr.h",
        "BotWorldPopulationMgrConfig.h",
        "BotWorldPopulationMgrRouteState.h",
    )

    assert "struct GossipOpen" in native
    assert "BotNativeAction::GossipOpen" in source
    assert "HandleGossipHelloOpcode(hello)" in source
    assert "HandleGossipSelectOptionOpcode(select)" in source
    assert "HandleGameObjectUseOpcode(use)" in source
    native_block = function_body(
        preparation, "void BotWorldPopulationMgr::PrepareValidationKernel("
    )
    assert "AI()->DoAction" not in native_block

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

    assert '"gameobject_selectable"' in native_block
    assert '"boss_summoned"' in native_block
    assert '"aura_present"' in native_block
    assert '"creature_aggressive_with_victim"' in native_block
    assert '"creature_grounded_aggressive_or_engaged"' in native_block
    assert 'ValidationRouteTerminalReason =\n                        "native_postcondition"' in native_block
    assert "intro_complete_and_elevator_ready" not in native_block
    assert "player_in_nefarian_arena" not in native_block

    route_adapter = bot_source(
        "BotWorldPopulationMgrUpdateBotKernelFallback.cpp"
    )
    assert "AdaptiveNativeRouteOwnsNode" in route_adapter
    assert '"native_route_contract_owns_node"' in route_adapter


def test_dungeon_intro_activation_uses_native_area_trigger_opcode() -> None:
    activation_source = bot_source("BotWorldPopulationMgrValidationActivation.cpp")
    activation = function_body(
        activation_source,
        "bool BotWorldPopulationMgr::TryValidationRouteActivation(",
    )
    native_action = bot_source("BotWorldPopulationMgrNativeAction.cpp")
    manifest = bot_source("BotWorldPopulationMgrValidationRouteManifest.cpp")
    header = bot_source(
        "BotWorldPopulationMgr.h",
        "BotWorldPopulationMgrConfig.h",
        "BotWorldPopulationMgrRouteState.h",
    )
    config = (ROOT / "src/server/worldserver/worldserver.conf.dist").read_text(
        encoding="utf-8"
    )
    live_runner = (ROOT / "tools/bot_ml/run_live_bot_validation.py").read_text(
        encoding="utf-8"
    )

    assert "ValidationRouteActivationAreaTriggerId" in header
    assert "BotWorld.ValidationRoute.ActivationAreaTriggerId = 0" in config
    assert 'readInt(routeJson, "activation_area_trigger_id")' in manifest
    assert '"activation_area_trigger_id"' in live_runner
    assert "sAreaTriggerStore.LookupEntry(triggerId)" in activation
    assert "bot->IsInAreaTriggerRadius(trigger)" in activation
    assert "BotNativeAction::Move" in activation
    assert "BotNativeAction::AreaTrigger" in activation
    assert "struct AreaTrigger" in (ROOT / "src/server/game/Bots/BotNativeActionIntent.h").read_text(
        encoding="utf-8"
    )
    assert "HandleAreaTriggerOpcode(areaTrigger)" in native_action
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

    generated_routes_path = ROOT / "dataset/validation_scenarios/validation_routes.jsonl"
    if generated_routes_path.exists():
        generated_routes = [
            json.loads(line)
            for line in generated_routes_path.read_text(encoding="utf-8").splitlines()
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
