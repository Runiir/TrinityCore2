#include "Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"
#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotActionArbiter.h"
#include "Bots/BotMeleeAutoAttackIntent.h"
#include "Bots/BotMovementArbiter.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "Creature.h"
#include "MotionMaster.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <utility>

using BotWorldPopulationMgrSpellSemantics::NowMs;

namespace BotWorldPopulationMgrValidationRoute
{
ObjectiveContext::ObjectiveContext(BotWorldPopulationMgr& manager,
    WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, std::string& situation,
    std::string& action, Unit*& target, bool arrivalRoute,
    float routeArrivalRadius, float const& canonicalRouteDistance,
    float& routeAnchorX, float& routeAnchorY, float& routeAnchorZ,
    std::string& routeAnchorReason, float& routeDistance,
    ObjectiveCallbacks callbacks)
    : Manager(manager), State(state), Bot(bot), Power(power), Stage(stage),
      Activity(activity), Situation(situation), Action(action), Target(target),
      ArrivalRoute(arrivalRoute), RouteArrivalRadius(routeArrivalRadius),
      CanonicalRouteDistance(canonicalRouteDistance),
      RouteAnchorX(routeAnchorX), RouteAnchorY(routeAnchorY),
      RouteAnchorZ(routeAnchorZ), RouteAnchorReason(routeAnchorReason),
      RouteDistance(routeDistance), Callbacks(std::move(callbacks))
{
}

bool ObjectiveContext::Run()
{
    bool failedTrashPackComplete = !Callbacks.PersistedPackHasLiveMembers();
    Unit* retryableFailedTrashTarget = failedTrashPackComplete ? nullptr : Callbacks.ActivePackTarget();
    bool failedTrashPackCanRetry = retryableFailedTrashTarget
        && Callbacks.IsEligibleTrash(retryableFailedTrashTarget->ToCreature());
    bool failedTrashPartyCombatActive = Callbacks.PartyHasActiveCombat();
    bool failedTrashRetryDue = State.ValidationRouteTerminalAtMs
        && NowMs() - State.ValidationRouteTerminalAtMs >= 5000;
    if (State.ValidationRouteTerminalState
        && State.ValidationRouteGeneration == Manager.Party().ValidationRouteGeneration
        && State.ValidationRouteTerminalGeneration == Manager.Party().ValidationRouteGeneration
        && Manager.Cohort().Config.ValidationRouteKind != "boss"
        && State.ValidationRouteTerminalReason == "validation_trash_no_progress"
        && Manager.Party().ValidationRoutePackGeneration == Manager.Party().ValidationRouteGeneration
        && Manager.Party().ValidationRoutePackObservedEngagement
        && (failedTrashPackComplete || failedTrashPackCanRetry)
        && (!failedTrashPartyCombatActive || (failedTrashPackCanRetry && failedTrashRetryDue)))
    {
        uint64 retryNowMs = NowMs();
        for (WorldBotState& cohortState : Manager.Party().Bots)
        {
            if (Player* cohortBot = Manager.GetLoadedBot(cohortState))
                cohortBot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
            cohortState.TargetGuid.Clear();
            cohortState.ValidationRouteCombatProgressTargetGuid.Clear();
            cohortState.ValidationRoutePackProgressTargetGuid.Clear();
            cohortState.ValidationRouteCombatNoProgressCount = 0;
            cohortState.ValidationRouteCombatNoProgressSinceMs = 0;
            cohortState.ValidationRoutePackNoProgressCount = 0;
            cohortState.ValidationRoutePackNoProgressSinceMs = 0;
            cohortState.ValidationRouteTerminalState = false;
            cohortState.ValidationRouteTerminalAtMs = 0;
            cohortState.ValidationRouteTerminalGeneration = 0;
            cohortState.ValidationRouteTerminalReason.clear();
            cohortState.ActivePathValid = false;
            cohortState.IsMoving = false;
            cohortState.LoopRecoveryCooldownUntilMs = retryNowMs + 1000;
            if (failedTrashPackCanRetry)
            {
                // Reopen onto the actual surviving pack member rather than
                // the already-cleared lower anchor. This also recovers a live
                // engaged pack after the bounded terminal hold instead of
                // waiting forever for hostile combat state to disappear.
                cohortState.ValidationRouteAnchorOverrideValid = true;
                cohortState.ValidationRouteAnchorOverrideUntilMs = retryNowMs + 30000;
                cohortState.ValidationRouteAnchorOverrideX = retryableFailedTrashTarget->GetPositionX();
                cohortState.ValidationRouteAnchorOverrideY = retryableFailedTrashTarget->GetPositionY();
                cohortState.ValidationRouteAnchorOverrideZ = retryableFailedTrashTarget->GetPositionZ();
                cohortState.ValidationRouteAnchorOverrideReason = "validation_route_live_pack_reapproach";
            }
        }
        Unit* retryEvidenceTarget = failedTrashPackCanRetry ? retryableFailedTrashTarget : nullptr;
        // Leave combat focus empty for one decision so the route override
        // stays authoritative and all roles reapproach with the tank.
        Target = nullptr;
        std::string raw = Manager.BuildRawJson(Bot, retryEvidenceTarget);
        std::string semantic = Manager.BuildSemanticJson(Bot, nullptr, "validation_route_recovery", &Power, Stage, Activity);
        char const* recoveryReason = failedTrashPackCanRetry
            ? "failed_terminal_reopened_for_live_pack_reapproach"
            : "failed_terminal_reopened_after_pack_death";
        Manager.RecordEvent(State, Bot, "validation_route_recovery", retryEvidenceTarget, recoveryReason,
            raw.c_str(), semantic.c_str(), float(Manager.Party().ValidationRoutePackDeathGuids.size()), uint32(Manager.Party().ValidationRoutePackMemberGuids.size()));
        Situation = "validation_route_recovery";
        Action = "validation_route_recovery";
        return true;
    }
    bool routePartyCombatActive = Callbacks.PartyHasActiveCombat();
    bool arrivalCombatActive = ArrivalRoute && routePartyCombatActive;
    bool allRouteParticipantsAlive = true;
    uint32 loadedRouteParticipants = 0;
    for (WorldBotState const& cohortState : Manager.Party().Bots)
    {
        Player* cohortBot = Manager.GetLoadedBot(cohortState);
        if (!cohortBot)
            continue;
        ++loadedRouteParticipants;
        if (!cohortBot->IsAlive() || !Callbacks.IsOriginalInstanceMember(cohortState, cohortBot))
        {
            allRouteParticipantsAlive = false;
            break;
        }
    }
    if (Manager.Cohort().Config.TargetPopulation && loadedRouteParticipants < Manager.Cohort().Config.TargetPopulation)
        allRouteParticipantsAlive = false;

    bool releasedRetreatRendezvous = !routePartyCombatActive && allRouteParticipantsAlive
        && State.ValidationRouteAnchorOverrideValid
        && State.ValidationRouteAnchorOverrideReason == "validation_route_partial_wipe_retreat_rendezvous";
    if (releasedRetreatRendezvous)
    {
        for (WorldBotState& cohortState : Manager.Party().Bots)
        {
            if (cohortState.ValidationRouteAnchorOverrideReason != "validation_route_partial_wipe_retreat_rendezvous")
                continue;
            cohortState.ValidationRouteAnchorOverrideValid = false;
            cohortState.ValidationRouteAnchorOverrideUntilMs = 0;
            cohortState.ValidationRouteAnchorOverrideReason.clear();
        }
        RouteAnchorX = Manager.Cohort().Config.ValidationRouteX;
        RouteAnchorY = Manager.Cohort().Config.ValidationRouteY;
        RouteAnchorZ = Manager.Cohort().Config.ValidationRouteZ;
        RouteAnchorReason = "validation_route_anchor";
        RouteDistance = CanonicalRouteDistance;
        State.QuestRouteDestination.X = RouteAnchorX;
        State.QuestRouteDestination.Y = RouteAnchorY;
        State.QuestRouteDestination.Z = RouteAnchorZ;
        State.QuestRouteDestination.Reason = RouteAnchorReason;
    }

    bool invalidArrivalTerminal = ArrivalRoute
        && State.ValidationRouteTerminalState
        && State.ValidationRouteGeneration == Manager.Party().ValidationRouteGeneration
        && State.ValidationRouteTerminalGeneration == Manager.Party().ValidationRouteGeneration
        && State.ValidationRouteTerminalReason == "arrival"
        && (CanonicalRouteDistance > RouteArrivalRadius
            || std::fabs(Bot->GetPositionZ() - Manager.Cohort().Config.ValidationRouteZ) > 4.0f
            || arrivalCombatActive);
    if (invalidArrivalTerminal)
    {
        State.ValidationRouteTerminalState = false;
        State.ValidationRouteTerminalAtMs = 0;
        State.ValidationRouteTerminalGeneration = 0;
        State.ValidationRouteTerminalReason.clear();
        State.LoopRecoveryCooldownUntilMs = 0;
    }

    if (State.ValidationRouteTerminalState
        && State.ValidationRouteGeneration == Manager.Party().ValidationRouteGeneration
        && State.ValidationRouteTerminalGeneration == Manager.Party().ValidationRouteGeneration)
    {
        float terminalCohortRadius = Manager.Cohort().Config.ValidationRouteClusterRadiusYards > 1.0f
            ? std::min(Manager.Cohort().Config.ValidationRouteClusterRadiusYards, 90.0f)
            : 90.0f;
        if (!ArrivalRoute
            && !Manager.Party().ValidationRouteManifest.empty()
            && !Manager.Party().ValidationRouteManifestComplete
            && Manager.Cohort().Config.ValidationRouteAdvanceMode == "terminal"
            && RouteDistance > terminalCohortRadius)
        {
            Manager.SubmitMeleeAutoAttackIntent(State,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Safety,
                BotActionArbitration::Priority::Terminal,
                "terminal_cohort_catchup");
            Target = nullptr;
            State.TargetGuid.Clear();
            if (Callbacks.MoveToRouteAnchor())
            {
                std::string raw = Manager.BuildRawJson(Bot, nullptr);
                std::string semantic = Manager.BuildSemanticJson(Bot, nullptr, "validation_route_regroup", &Power, Stage, Activity);
                Manager.RecordEvent(State, Bot, "validation_route_regroup", nullptr, "terminal_cohort_catchup", raw.c_str(), semantic.c_str(), RouteDistance, Manager.Cohort().Config.ValidationRouteTargetEntry);
                Situation = "validation_route_regroup";
                Action = "move_to_validation_route_anchor";
                return true;
            }
        }

        Manager.SubmitMeleeAutoAttackIntent(State,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Safety,
            BotActionArbitration::Priority::Terminal,
            "validation_route_terminal_hold");
        State.TargetGuid.Clear();
        State.WasInCombat = false;
        State.LoopRecoveryCooldownUntilMs = NowMs() + 60000;
        Situation = Manager.Cohort().Config.ValidationRouteKind == "boss"
            ? "validation_route_manifest"
            : "normal_dungeon_trash";
        Action = State.ValidationRouteTerminalReason == "trash_cluster_cleared"
            || State.ValidationRouteTerminalReason == "boss_killed"
            || State.ValidationRouteTerminalReason == "arrival"
            ? "validation_route_complete"
            : "validation_route_failed";
        if (!State.ValidationRouteTerminalAtMs || NowMs() - State.ValidationRouteTerminalAtMs <= 5000)
        {
            std::string raw = Manager.BuildRawJson(Bot, nullptr);
            std::string semantic = Manager.BuildSemanticJson(Bot, nullptr, Situation.c_str(), &Power, Stage, Activity);
            Manager.RecordEvent(State, Bot, "validation_route_recovery", nullptr, State.ValidationRouteTerminalReason.empty() ? "route_terminal_hold" : State.ValidationRouteTerminalReason.c_str(), raw.c_str(), semantic.c_str(), RouteDistance, Manager.Cohort().Config.ValidationRouteTargetEntry);
        }
        return true;
    }
    // Regroup and descent nodes must not suppress a natural pull merely because
    // the cohort reached the navigation anchor. Finish every active attacker
    // before marking arrival; otherwise mobs can evade back across a one-way
    // descent and poison the following trash ledger with unreachable survivors.
    if (arrivalCombatActive)
        Callbacks.EnrollEngagedPackMembers();
    if (ArrivalRoute && !arrivalCombatActive)
    {
        Manager.SubmitMeleeAutoAttackIntent(State,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Route,
            BotActionArbitration::Priority::Mechanic,
            "validation_route_arrival_hold");
        Target = nullptr;
        State.TargetGuid.Clear();
        std::string raw = Manager.BuildRawJson(Bot, nullptr);
        std::string semantic = Manager.BuildSemanticJson(Bot, nullptr, "validation_route_regroup", &Power, Stage, Activity);
        if (Manager.Cohort().Config.ValidationRouteKind == "descent"
            && !Manager.Cohort().Config.ValidationRouteDescentAction.empty())
        {
            if (Manager.Cohort().Config.ValidationRouteDescentAction
                != "native_walkable_descent")
            {
                // A manifest may name a player input that the server-side bot
                // cannot safely express (for example a client jump). Keep it
                // fail-closed instead of substituting a spline or position
                // mutation.
                State.ActivePathValid = false;
                State.ValidationRouteDescentPhase =
                    WorldBotState::ValidationDescentPhase::Blocked;
                State.ValidationRouteDescentRejectReason =
                    "native_descent_semantics_unavailable";
                State.LastPathRejectReason =
                    State.ValidationRouteDescentRejectReason;
                State.LastNoProgressReason =
                    State.ValidationRouteDescentRejectReason;
                State.LastDecisionResult = "native_descent_unavailable";
                Manager.FailValidationAttemptOnce(State, Bot,
                    "native_descent_semantics_unavailable",
                    Manager.Party().ValidationRouteGeneration);
                Situation = "validation_route_descent";
                Action = "validation_route_descent_blocked";
                Target = nullptr;
                return true;
            }

            size_t const nextIndex = Manager.Party().ValidationRouteManifestIndex + 1;
            bool const hasNextGoal = nextIndex
                < Manager.Party().ValidationRouteManifest.size();
            ValidationRouteManifestNode const* nextNode = hasNextGoal
                ? &Manager.Party().ValidationRouteManifest[nextIndex] : nullptr;
            WorldBotState::ValidationDescentPhase const previousPhase =
                State.ValidationRouteDescentPhase;
            BotActionArbitration::Outcome const descentOutcome =
                Manager.ExecuteNativeActionIntent(State, Bot,
                    BotNativeAction::NativeDescent{
                        Manager.Cohort().Config.ValidationRouteX,
                        Manager.Cohort().Config.ValidationRouteY,
                        Manager.Cohort().Config.ValidationRouteZ,
                        nextNode ? nextNode->NavigationAnchorX : 0.0f,
                        nextNode ? nextNode->NavigationAnchorY : 0.0f,
                        nextNode ? nextNode->NavigationAnchorZ : 0.0f,
                        Manager.Party().ValidationRouteGeneration,
                        hasNextGoal },
                    BotMovementArbitration::Owner::Route,
                    BotMovementArbitration::Priority::Route);

            char const* const descentPhase = Manager.ValidationDescentPhaseName(
                State.ValidationRouteDescentPhase);
            bool const phaseChanged = previousPhase
                != State.ValidationRouteDescentPhase;
            bool const descentReady = State.ValidationRouteDescentPhase
                    == WorldBotState::ValidationDescentPhase::Ready
                && State.ValidationRouteDescentDepartureObserved
                && State.ValidationRouteDescentLandingObserved
                && State.ValidationRouteDescentHealthMarginSatisfied
                && State.ValidationRouteDescentLandingPathProven
                && State.ValidationRouteDescentMonotonicProgressObserved
                && !Bot->IsFalling();
            if (phaseChanged || descentReady
                || descentOutcome.Result
                    != BotActionArbitration::Disposition::Committed)
                Manager.RecordEvent(State, Bot, "validation_route_descent", nullptr,
                    State.ValidationRouteDescentRejectReason.empty()
                        ? descentPhase
                        : State.ValidationRouteDescentRejectReason.c_str(),
                    raw.c_str(), semantic.c_str(), CanonicalRouteDistance,
                    uint32(std::round(
                        State.ValidationRouteDescentLandingHealthPct * 100.0f)));

            Situation = "validation_route_descent";
            if (descentReady)
            {
                State.ValidationRouteTerminalState = true;
                State.ValidationRouteTerminalAtMs = NowMs();
                State.ValidationRouteTerminalGeneration =
                    Manager.Party().ValidationRouteGeneration;
                State.ValidationRouteTerminalReason =
                    "native_descent_landed_path_proven";
                State.LoopRecoveryCooldownUntilMs = NowMs() + 60000;
                Manager.RecordEvent(State, Bot, "validation_route_terminal", nullptr,
                    State.ValidationRouteTerminalReason.c_str(), raw.c_str(),
                    semantic.c_str(), CanonicalRouteDistance,
                    Manager.Cohort().Config.ValidationRouteTargetEntry);
                Action = "validation_route_descent_complete";
                Manager.MaybeAdvanceValidationRouteManifest();
            }
            else if (State.ValidationRouteDescentPhase
                == WorldBotState::ValidationDescentPhase::Falling)
                Action = "validation_route_descent_falling";
            else if (State.ValidationRouteDescentPhase
                == WorldBotState::ValidationDescentPhase::Landed)
                Action = "validation_route_descent_landing_pending";
            else if (descentOutcome.Result
                == BotActionArbitration::Disposition::Committed)
                Action = "validation_route_descent_walk_segment";
            else
                Action = "validation_route_descent_blocked";
            Target = nullptr;
            return true;
        }
        if (CanonicalRouteDistance <= RouteArrivalRadius
            && std::fabs(Bot->GetPositionZ() - Manager.Cohort().Config.ValidationRouteZ) <= 4.0f)
        {
            State.ValidationRouteTerminalState = true;
            State.ValidationRouteTerminalAtMs = NowMs();
            State.ValidationRouteTerminalGeneration = Manager.Party().ValidationRouteGeneration;
            State.ValidationRouteTerminalReason = "arrival";
            State.LoopRecoveryCooldownUntilMs = NowMs() + 60000;
            Manager.RecordEvent(State, Bot, "validation_route_regroup", nullptr, "arrival", raw.c_str(), semantic.c_str(), CanonicalRouteDistance, Manager.Cohort().Config.ValidationRouteTargetEntry);
            Manager.RecordEvent(State, Bot, "validation_route_terminal", nullptr, "arrival", raw.c_str(), semantic.c_str(), CanonicalRouteDistance, Manager.Cohort().Config.ValidationRouteTargetEntry);
            Situation = "validation_route_regroup";
            Action = "validation_route_complete";
            Manager.MaybeAdvanceValidationRouteManifest();
            return true;
        }

        bool const moved = Callbacks.MoveToRouteAnchor();
        char const* movementResult = moved
            ? (Manager.Cohort().Config.ValidationRouteLabel.empty()
                ? "move_to_arrival" : Manager.Cohort().Config.ValidationRouteLabel.c_str())
            : (State.LastPathRejectReason.empty()
                ? "route_anchor_retryable" : State.LastPathRejectReason.c_str());
        Manager.RecordEvent(State, Bot, "validation_route_regroup", nullptr,
            movementResult, raw.c_str(), semantic.c_str(), RouteDistance,
            Manager.Cohort().Config.ValidationRouteTargetEntry);
        Situation = "validation_route_regroup";
        Action = moved ? "move_to_validation_route_anchor" : "validation_route_hold_anchor";
        return true;
    }
    return false;
}
}
