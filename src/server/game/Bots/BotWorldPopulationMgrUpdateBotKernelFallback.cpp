#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/BotActionExecutor.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotRouteCombatTargetPolicy.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotAdaptiveDrudgeStrategy.h"

#include "Creature.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

#include <string>
#include <string_view>
#include <memory>
#include <utility>

using BotWorldPopulationMgrNativeHelpers::IsNativeCombatObserved;

void BotWorldPopulationMgr::SubmitValidationKernelFallbackCandidates(
    BotUpdateContext& context)
{
        struct RouteAttempt
        {
            bool Attempted = false;
            bool Handled = false;
            bool MovementSubmitted = false;
            bool CombatAttempted = false;
            bool ActionSubmitted = false;
            BotActionArbitration::Outcome RouteOutcome;
        };
        std::shared_ptr<RouteAttempt> routeAttempt =
            std::make_shared<RouteAttempt>();

        auto routeOwnerReason = [&context]() -> char const*
        {
            if (context.AdaptiveDrudgeOwnsNode)
                return "adaptive_drudge_owns_live_pack";
            if (context.AdaptiveMagmawOwnsNode)
                return "adaptive_magmaw_owns_live_encounter";
            if (context.AdaptiveOmnotronOwnsNode)
                return "adaptive_omnotron_owns_live_encounter";
            if (context.AdaptiveMaloriakOwnsNode)
                return "adaptive_maloriak_owns_live_encounter";
            if (context.AdaptiveChimaeronOwnsNode)
                return "adaptive_chimaeron_owns_live_encounter";
            if (context.AdaptiveAtramedesOwnsNode)
                return "adaptive_atramedes_owns_live_encounter";
            if (context.AdaptiveNefarianOwnsNode)
                return "adaptive_nefarian_owns_live_encounter";
            if (context.AdaptiveNativeRouteOwnsNode)
                return "native_route_contract_owns_node";
            return nullptr;
        };

        // The Drudge owner is still authoritative for generic candidates, but
        // this route owns a typed lane adapter that must run before that
        // generic-owner short circuit. Keep the exception bound to the exact
        // declared mechanic profile so another adaptive owner cannot bypass
        // its typed route contract.
        bool const typedDrudgeValidationRoute =
            Cohort().Config.ValidationRouteMechanicProfile
                == "trash_two_tank_charge_lanes";

        // Adaptive encounter owners skip TryValidationRouteObjectiveGate(),
        // which normally refreshes the current route's offensive authority.
        // Clear a stale hold from the previous node before the kernel resolves
        // normal native casts, while retaining the current node's declared
        // future-encounter protections. Terminal and recovery holds return
        // before candidate submission and cannot reach this refresh.
        if (routeOwnerReason())
            ConfigureValidationRouteCombatAuthority(context.Bot);

        auto routeActionIsMovementOnly = [](std::string const& action)
        {
            return action.empty()
                || action == "validation_route"
                || action.find("hold") != std::string::npos
                || action.find("wait") != std::string::npos
                || action.find("move") != std::string::npos
                || action.find("approach") != std::string::npos
                || action.find("retreat") != std::string::npos
                || action.find("stack") != std::string::npos
                || action.find("preposition") != std::string::npos
                || action.find("staging") != std::string::npos
                || action.find("descent") != std::string::npos
                || action.find("anchor") != std::string::npos
                || action.find("position") != std::string::npos
                || action.find("density_escape") != std::string::npos
                || action.find("side_hazard") != std::string::npos
                || action.find("reseparate") != std::string::npos
                || action.find("blocked") != std::string::npos
                || action.find("pending") != std::string::npos
                || action.find("retry") != std::string::npos
                || action.find("failed") != std::string::npos;
        };

        auto runRoute = [this, &context, routeAttempt, routeOwnerReason,
            routeActionIsMovementOnly, typedDrudgeValidationRoute]()
            -> BotActionArbitration::Outcome
        {
            if (routeAttempt->Attempted)
                return routeAttempt->RouteOutcome;
            routeAttempt->Attempted = true;

            if (char const* ownerReason = routeOwnerReason(); ownerReason
                && !typedDrudgeValidationRoute)
            {
                routeAttempt->RouteOutcome =
                    BotActionArbitration::Outcome::NotApplicable(ownerReason);
                return routeAttempt->RouteOutcome;
            }

            Unit* const targetBeforeRoute = context.Target;
            ObjectGuid const stateTargetBeforeRoute = context.State.TargetGuid;
            uint64 const previousPathChangeMs = context.State.LastPathChangeMs;
            uint64 const previousCombatAttemptMs =
                context.State.LastCombatAttempt.RecordedAtMs;
            routeAttempt->Handled = TryValidationRouteObjective(
                context.State, context.Bot, context.Power, context.Stage,
                context.ChosenActivity.Activity, context.Situation,
                context.Action, context.Target);
            if (!routeAttempt->Handled)
            {
                routeAttempt->RouteOutcome =
                    BotActionArbitration::Outcome::NotApplicable(
                        "route_not_applicable");
                return routeAttempt->RouteOutcome;
            }

            context.State.LastDecisionHandler = "validation_route";
            if (context.State.ValidationRouteTerminalState)
            {
                routeAttempt->RouteOutcome = BotActionArbitration::Outcome::Terminal(
                    context.State.ValidationRouteTerminalReason.empty()
                        ? std::string_view("route_terminal")
                        : std::string_view(
                            context.State.ValidationRouteTerminalReason));
                return routeAttempt->RouteOutcome;
            }

            routeAttempt->MovementSubmitted =
                context.State.LastPathChangeMs > previousPathChangeMs
                && context.State.ActivePathValid;
            routeAttempt->CombatAttempted =
                context.State.LastCombatAttempt.RecordedAtMs
                    > previousCombatAttemptMs;
            routeAttempt->ActionSubmitted = routeAttempt->CombatAttempted
                || (!routeAttempt->MovementSubmitted
                    && !routeActionIsMovementOnly(context.Action));

            if (routeAttempt->MovementSubmitted)
                routeAttempt->RouteOutcome =
                    BotActionArbitration::Outcome::Started(
                        "route_movement_submitted");
            else if (routeAttempt->CombatAttempted)
            {
                std::string const& result =
                    context.State.LastCombatAttempt.Result;
                if (result == "ok")
                {
                    if (context.State.LastCombatAttempt.Reason
                            == "no_line_of_sight"
                        || context.State.LastCombatAttempt.Reason
                            == "target_missing"
                        || context.State.LastCombatAttempt.Reason
                            == "target_dead"
                        || context.State.LastCombatAttempt.Reason
                            == "target_not_attackable")
                        routeAttempt->RouteOutcome =
                            BotActionArbitration::Outcome::Retryable(
                                context.State.LastCombatAttempt.Reason);
                    else
                        routeAttempt->RouteOutcome =
                            IsNativeCombatObserved(context.Bot, context.Target)
                                ? BotActionArbitration::Outcome::Progressed(
                                    "route_native_combat_observed")
                                : BotActionArbitration::Outcome::Started(
                                    "route_combat_submitted");
                }
                else if (result == "casting" || result == "global_cooldown")
                    routeAttempt->RouteOutcome =
                        BotActionArbitration::Outcome::Started(
                            "route_combat_scheduled");
                else
                    routeAttempt->RouteOutcome =
                        BotActionArbitration::Outcome::Retryable(
                            context.State.LastCombatAttempt.Reason.empty()
                                ? std::string_view("route_combat_retryable")
                                : std::string_view(
                                    context.State.LastCombatAttempt.Reason));
            }
            else if (routeAttempt->ActionSubmitted)
                routeAttempt->RouteOutcome =
                    BotActionArbitration::Outcome::Started(
                        "route_action_submitted");
            else
            {
                bool const routeYield = context.Action.find("hold")
                        != std::string::npos
                    || context.Action.find("wait") != std::string::npos
                    || context.Action.find("blocked") != std::string::npos
                    || context.Action.find("pending") != std::string::npos
                    || context.Action.find("retry") != std::string::npos
                    || context.Action.find("failed") != std::string::npos
                    || context.Action == "validation_route_wrong_map";
                if (routeYield)
                {
                    if (targetBeforeRoute && targetBeforeRoute->IsAlive()
                        && context.Bot->IsValidAttackTarget(targetBeforeRoute)
                        && (context.Bot->IsInCombat()
                            || targetBeforeRoute->IsInCombat()))
                    {
                        context.Target = targetBeforeRoute;
                        context.State.TargetGuid = stateTargetBeforeRoute;
                    }
                    if (context.Action
                        == "validation_route_patrol_wait_for_safe_phase")
                    {
                        context.State.LastRecoveryMode =
                            "validation_route_wait";
                        context.State.LastRecoveryResult = context.Action;
                    }
                    routeAttempt->RouteOutcome =
                        BotActionArbitration::Outcome::Retryable(
                            context.State.LastNoProgressReason.empty()
                                ? std::string_view("route_retryable")
                                : std::string_view(
                                    context.State.LastNoProgressReason));
                }
                else
                    routeAttempt->RouteOutcome =
                        BotActionArbitration::Outcome::Started(
                            "route_handled_pending_postcondition");
            }
            return routeAttempt->RouteOutcome;
        };

        // A pending exact Drudge recovery is a single movement contract. The
        // route action must reserve that lane even when this tick also emits
        // a legal cast; otherwise the generic combat-range candidate can
        // submit a chase before the assigned tank reaches its anchor.
        // Ordinary routes retain the paired movement candidate semantics.
        BotActionArbitration::Candidate routeAction;
        routeAction.Key = "world.validation_route_action";
        routeAction.Source = "validation_route_adapter";
        routeAction.ActionPriority = BotActionArbitration::Priority::Mechanic;
        routeAction.UtilityScore = 3.1f;
        BotActionArbitration::ResourceMask routeActionResources =
            BotActionArbitration::Uses(
                BotActionArbitration::Resource::GlobalCooldown,
                BotActionArbitration::Resource::Cast,
                BotActionArbitration::Resource::Target,
                BotActionArbitration::Resource::Interaction);
        if (typedDrudgeValidationRoute && context.AdaptiveDrudgeOwnsNode
            && !context.DrudgeCombatAuthorityAllowed)
            routeActionResources |= BotActionArbitration::Uses(
                BotActionArbitration::Resource::Movement);
        routeAction.RequiredResources = routeActionResources;
        routeAction.Attempt = [runRoute, routeAttempt]()
        {
            BotActionArbitration::Outcome const outcome = runRoute();
            if (outcome.Result == BotActionArbitration::Disposition::Terminal
                || routeAttempt->ActionSubmitted)
                return outcome;
            return BotActionArbitration::Outcome::NotApplicable(
                routeAttempt->MovementSubmitted
                    ? "route_movement_only"
                    : outcome.Reason);
        };
        context.State.DecisionKernel.Submit(std::move(routeAction));

        BotActionArbitration::Candidate routeMovement;
        routeMovement.Key = "world.validation_route_movement";
        routeMovement.Source = "validation_route_adapter";
        routeMovement.ActionPriority = BotActionArbitration::Priority::Mechanic;
        routeMovement.UtilityScore = 3.0f;
        routeMovement.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::Movement);
        routeMovement.Attempt = [runRoute, routeAttempt]()
        {
            BotActionArbitration::Outcome const outcome = runRoute();
            if (outcome.Result == BotActionArbitration::Disposition::Terminal)
                return outcome;
            if (routeAttempt->MovementSubmitted)
                return outcome;
            if (routeAttempt->ActionSubmitted)
                return BotActionArbitration::Outcome::NotApplicable(
                    "route_action_only");
            return outcome;
        };
        context.State.DecisionKernel.Submit(std::move(routeMovement));
        BotActionArbitration::Candidate boss;
        boss.Key = "world.boss_mechanics";
        boss.Source = "boss_mechanics_adapter";
        boss.ActionPriority = BotActionArbitration::Priority::Mechanic;
        boss.UtilityScore = 2.0f;
        boss.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast,
            BotActionArbitration::Resource::Movement,
            BotActionArbitration::Resource::Target,
            BotActionArbitration::Resource::Interaction);
        boss.Attempt = [&]()
        {
            BossMechanicActionResult& bossAction = context.BossAction;
            if (context.AdaptiveDrudgeOwnsNode || context.AdaptiveMagmawOwnsNode
                || context.AdaptiveOmnotronOwnsNode
                || context.AdaptiveMaloriakOwnsNode || context.AdaptiveChimaeronOwnsNode
                || context.AdaptiveAtramedesOwnsNode || context.AdaptiveNefarianOwnsNode)
                return BotActionArbitration::Outcome::NotApplicable(
                    context.AdaptiveDrudgeOwnsNode
                        ? "adaptive_drudge_owns_live_pack"
                        : (context.AdaptiveMagmawOwnsNode
                            ? "adaptive_magmaw_owns_live_encounter"
                            : (context.AdaptiveOmnotronOwnsNode
                                ? "adaptive_omnotron_owns_live_encounter"
                                : (context.AdaptiveMaloriakOwnsNode
                                    ? "adaptive_maloriak_owns_live_encounter"
                                    : (context.AdaptiveChimaeronOwnsNode
                                        ? "adaptive_chimaeron_owns_live_encounter"
                                        : (context.AdaptiveAtramedesOwnsNode
                                            ? "adaptive_atramedes_owns_live_encounter"
                                            : "adaptive_nefarian_owns_live_encounter"))))));
            if (!IsBossContext(context.Bot, context.Target))
                return BotActionArbitration::Outcome::NotApplicable(
                    "not_boss_context");
            uint64 const previousPathChangeMs = context.State.LastPathChangeMs;
            uint64 const previousCombatAttemptMs = context.State.LastCombatAttempt.RecordedAtMs;
            bossAction = TryBossMechanics(context.State, context.Bot, context.Power, context.Stage,
                context.ChosenActivity.Activity);
            if (!bossAction.Handled)
                return BotActionArbitration::Outcome::NotApplicable(
                    "boss_adapter_not_applicable");
            context.Situation = bossAction.Situation;
            context.Action = bossAction.Action;
            context.Target = bossAction.Target;
            context.State.LastDecisionHandler = "boss_mechanics";
            if (bossAction.Failure)
                return BotActionArbitration::Outcome::Retryable(
                    "boss_action_failed");

            // Handled is a legacy routing signal, not proof that the game
            // accepted work. A rejected path, an already-owned movement lease,
            // or a passive wait must yield so another compatible candidate can
            // run in the same tick.
            if (context.State.LastPathChangeMs > previousPathChangeMs
                && context.State.ActivePathValid)
                return BotActionArbitration::Outcome::Started(
                    "boss_movement_submitted");
            if (context.State.LastCombatAttempt.RecordedAtMs > previousCombatAttemptMs)
            {
                std::string const& result = context.State.LastCombatAttempt.Result;
                if (result == "ok")
                {
                    if (context.State.LastCombatAttempt.Reason == "no_line_of_sight"
                        || context.State.LastCombatAttempt.Reason == "target_missing"
                        || context.State.LastCombatAttempt.Reason == "target_dead"
                        || context.State.LastCombatAttempt.Reason == "target_not_attackable")
                        return BotActionArbitration::Outcome::Retryable(
                            context.State.LastCombatAttempt.Reason);
                    return IsNativeCombatObserved(context.Bot, context.Target)
                        ? BotActionArbitration::Outcome::Progressed(
                            "boss_native_combat_observed")
                        : BotActionArbitration::Outcome::Started(
                            "boss_combat_submitted");
                }
                if (result == "casting" || result == "global_cooldown")
                    return BotActionArbitration::Outcome::Started(
                        "boss_combat_scheduled");
                return BotActionArbitration::Outcome::Retryable(
                    context.State.LastCombatAttempt.Reason.empty()
                        ? std::string_view("boss_combat_retryable")
                        : std::string_view(context.State.LastCombatAttempt.Reason));
            }
            if (bossAction.SpellId)
                return BotActionArbitration::Outcome::Started(
                    "boss_spell_submitted");
            if (bossAction.Action.find("_submitted") != std::string::npos)
                return BotActionArbitration::Outcome::Started(
                    "boss_native_submission_started");
            bool const observedPostcondition =
                bossAction.Action.find("_complete") != std::string::npos
                || bossAction.Action.find("_postcondition") != std::string::npos
                || bossAction.Action.find("_boarded") != std::string::npos
                || bossAction.Action.find("_entered") != std::string::npos;
            bool const safetyHold = bossAction.Action == "raid_do_not_damage_hold"
                || bossAction.Action == "raid_soak_wait_for_assigned_count"
                || bossAction.Action == "raid_kill_sync_execution_hold_low_target";
            if (observedPostcondition || safetyHold)
                return observedPostcondition
                    ? BotActionArbitration::Outcome::Committed(
                        "boss_postcondition_observed")
                    : BotActionArbitration::Outcome::Submitted(
                        "boss_safety_hold_submitted");
            return BotActionArbitration::Outcome::Retryable(
                "boss_no_observable_effect");
        };
        context.State.DecisionKernel.Submit(std::move(boss));

        BotActionArbitration::Candidate trash;
        trash.Key = "world.dungeon_trash";
        trash.Source = "dungeon_trash_adapter";
        trash.ActionPriority = BotActionArbitration::Priority::ThreatControl;
        trash.UtilityScore = 2.0f;
        trash.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast,
            BotActionArbitration::Resource::Movement,
            BotActionArbitration::Resource::Target);
        trash.Attempt = [&]()
        {
            if (typedDrudgeValidationRoute && context.AdaptiveDrudgeOwnsNode
                && !context.DrudgeCombatAuthorityAllowed)
                return BotActionArbitration::Outcome::NotApplicable(
                    "drudge_activation_latch_closed");
            DungeonTrashActionResult& trashAction = context.TrashAction;
            if (!IsDungeonTrashContext(context.Bot, context.Target))
                return BotActionArbitration::Outcome::NotApplicable(
                    "not_dungeon_trash_context");
            Unit* const targetBeforeTrash = context.Target;
            ObjectGuid const stateTargetBeforeTrash = context.State.TargetGuid;
            uint64 const previousPathChangeMs = context.State.LastPathChangeMs;
            uint64 const previousCombatAttemptMs =
                context.State.LastCombatAttempt.RecordedAtMs;
            trashAction = TryDungeonTrash(context.State, context.Bot, context.Power, context.Stage,
                context.ChosenActivity.Activity);
            if (!trashAction.Handled)
                return BotActionArbitration::Outcome::NotApplicable(
                    "trash_adapter_not_applicable");
            context.Situation = trashAction.Situation;
            context.Action = trashAction.Action;
            context.Target = trashAction.Target;
            context.State.LastDecisionHandler = "dungeon_trash";
            if (context.State.LastPathChangeMs > previousPathChangeMs
                && context.State.ActivePathValid)
                return BotActionArbitration::Outcome::Started(
                    "trash_movement_submitted");
            if (context.State.LastCombatAttempt.RecordedAtMs > previousCombatAttemptMs)
            {
                std::string const& result = context.State.LastCombatAttempt.Result;
                if (result == "ok")
                {
                    if (context.State.LastCombatAttempt.Reason == "no_line_of_sight"
                        || context.State.LastCombatAttempt.Reason == "target_missing"
                        || context.State.LastCombatAttempt.Reason == "target_dead"
                        || context.State.LastCombatAttempt.Reason == "target_not_attackable")
                        return BotActionArbitration::Outcome::Retryable(
                            context.State.LastCombatAttempt.Reason);
                    return IsNativeCombatObserved(context.Bot, context.Target)
                        ? BotActionArbitration::Outcome::Progressed(
                            "trash_native_combat_observed")
                        : BotActionArbitration::Outcome::Started(
                            "trash_combat_submitted");
                }
                if (result == "casting")
                    return BotActionArbitration::Outcome::Started(
                        "trash_combat_started");
                return BotActionArbitration::Outcome::Retryable(
                    context.State.LastCombatAttempt.Reason.empty()
                        ? std::string_view("trash_combat_retryable")
                        : std::string_view(context.State.LastCombatAttempt.Reason));
            }
            if (trashAction.Failure)
                return BotActionArbitration::Outcome::Retryable(
                    "trash_action_failed");
            if (trashAction.SpellId)
                return BotActionArbitration::Outcome::Started(
                    "trash_spell_submitted");

            bool const followAction = context.Action == "formation_follow"
                || context.Action == "healer_follow_tank"
                || context.Action == "avoid_extra_pull";
            MotionMaster* trashMotion = context.Bot->GetMotionMaster();
            bool const nativeFollowActive = trashMotion
                && (trashMotion->GetCurrentMovementGeneratorType()
                        == FOLLOW_MOTION_TYPE
                    || trashMotion->GetMotionSlotType(MOTION_SLOT_IDLE)
                        == FOLLOW_MOTION_TYPE
                    || trashMotion->GetMotionSlotType(MOTION_SLOT_ACTIVE)
                        == FOLLOW_MOTION_TYPE);
            if (followAction && nativeFollowActive)
                return BotActionArbitration::Outcome::Started(
                    "trash_follow_started");

            bool const observedPostcondition =
                context.Action.find("_complete") != std::string::npos;
            if (observedPostcondition)
                return BotActionArbitration::Outcome::Committed(
                    "trash_postcondition_observed");
            bool const trashYield = context.Action.find("hold") != std::string::npos
                || context.Action.find("wait") != std::string::npos
                || context.Action.find("pending") != std::string::npos
                || context.Action.find("retry") != std::string::npos
                || context.Action.find("failed") != std::string::npos
                || context.Action.find("readiness") != std::string::npos
                || followAction;
            if (trashYield && targetBeforeTrash && targetBeforeTrash->IsAlive()
                && context.Bot->IsValidAttackTarget(targetBeforeTrash)
                && (context.Bot->IsInCombat() || targetBeforeTrash->IsInCombat()))
            {
                context.Target = targetBeforeTrash;
                context.State.TargetGuid = stateTargetBeforeTrash;
            }
            return BotActionArbitration::Outcome::Retryable(
                trashYield ? std::string_view("trash_yield")
                    : std::string_view("trash_no_observable_effect"));
        };
        context.State.DecisionKernel.Submit(std::move(trash));

        BotActionArbitration::Candidate combatRange;
        combatRange.Key = "world.profile_combat_range";
        combatRange.Source = "db_class_spec_profile";
        combatRange.ActionPriority = BotActionArbitration::Priority::CombatMovement;
        combatRange.UtilityScore = context.Target && context.Target->IsAlive()
            ? 0.9f : 0.0f;
        // Range reconciliation is a movement-only lane.  A legal profile cast,
        // support action, or threat action must be able to commit beside it.
        combatRange.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::Movement);
        combatRange.Attempt = [&]()
        {
            if (typedDrudgeValidationRoute && context.AdaptiveDrudgeOwnsNode
                && !context.DrudgeCombatAuthorityAllowed)
                return BotActionArbitration::Outcome::NotApplicable(
                    "drudge_activation_latch_closed");
            Unit* const target = context.Target;
            Creature const* targetCreature = target ? target->ToCreature() : nullptr;
            bool const targetAlive = target && target->IsAlive();
            bool const targetAttackable = targetAlive
                && context.Bot->IsValidAttackTarget(target);
            bool const sameMap = target
                && target->GetMapId() == context.Bot->GetMapId();
            bool const sameInstance = target
                && target->GetInstanceId() == context.Bot->GetInstanceId();
            bool const ownedDrudge = targetCreature
                && BotRouteCombatTargetPolicy::IsOwnedNativeEncounterTarget(
                    context.AdaptiveDrudgeOwnsNode, targetAlive,
                    targetAttackable, sameMap, sameInstance,
                    targetCreature->GetEntry(),
                    BotEncounter::AdaptiveDrudgeStrategy::DrudgeEntry);
            if (!ownedDrudge)
                return BotActionArbitration::Outcome::NotApplicable(
                    "not_owned_drudge_target");

            ResolvedCombatAction profileAction = ResolveProfileCombatAction(
                context.Bot, target);
            bool const outsideLegalMaxRange = profileAction.MaxRange > 0.0f
                && context.Bot->GetExactDist(target) > profileAction.MaxRange;
            bool const noLineOfSight = !context.Bot->IsWithinLOSInMap(target);
            if (!outsideLegalMaxRange && !noLineOfSight)
                return BotActionArbitration::Outcome::NotApplicable(
                    "drudge_profile_range_satisfied");

            bool const moved = MoveBotToProfileRange(context.State, context.Bot,
                target, &profileAction, noLineOfSight);
            if (!moved)
                return BotActionArbitration::Outcome::Retryable(
                    noLineOfSight ? "drudge_profile_los_path_rejected"
                        : "drudge_profile_range_path_rejected");

            context.Situation = "open_world_combat";
            context.Action = "profile_combat_range_movement";
            context.State.LastDecisionHandler = "combat_range";
            return BotActionArbitration::Outcome::Started(
                noLineOfSight ? "profile_combat_los_reconciled"
                    : "profile_combat_range_reconciled");
        };
        context.State.DecisionKernel.Submit(std::move(combatRange));

        BotActionArbitration::Candidate combat;
        combat.Key = "world.profile_combat";
        combat.Source = "db_class_spec_profile";
        combat.ActionPriority = BotActionArbitration::Priority::TrainedDamage;
        combat.UtilityScore = context.Target && context.Target->IsAlive() ? 1.0f : 0.0f;
        combat.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast,
            BotActionArbitration::Resource::Target);
        combat.Attempt = [&]()
        {
            if (typedDrudgeValidationRoute && context.AdaptiveDrudgeOwnsNode
                && !context.DrudgeCombatAuthorityAllowed)
                return BotActionArbitration::Outcome::NotApplicable(
                    "drudge_activation_latch_closed");
            if (!context.Target || !context.Target->IsAlive())
                return BotActionArbitration::Outcome::NotApplicable(
                    "no_live_combat_target");
            char const* rejectReason = nullptr;
            Creature const* targetCreature = context.Target->ToCreature();
            bool const ownedNativeRouteTarget = targetCreature
                && BotRouteCombatTargetPolicy::IsOwnedNativeEncounterTarget(
                    context.AdaptiveDrudgeOwnsNode,
                    context.Target->IsAlive(),
                    context.Bot->IsValidAttackTarget(context.Target),
                    context.Target->GetMapId() == context.Bot->GetMapId(),
                    context.Target->GetInstanceId() == context.Bot->GetInstanceId(),
                    targetCreature->GetEntry(),
                    BotEncounter::AdaptiveDrudgeStrategy::DrudgeEntry);
            if (!context.Bot->IsInCombat() && !ownedNativeRouteTarget
                && !IsQuestRelevantTarget(context.Bot, context.Target)
                && !IsProgressionCombatTarget(context.Bot, context.Target, &rejectReason))
            {
                context.State.LastRejectedTargetReason = rejectReason
                    ? rejectReason : "not_progression_relevant";
                context.State.TargetGuid.Clear();
                context.Target = nullptr;
                return BotActionArbitration::Outcome::Unsafe(
                    "combat_target_hard_masked");
            }

            context.State.TargetGuid = context.Target->GetGUID();
            ResolvedCombatAction profileAction;
            BotActionResult const result = ExecuteProfileCombatAction(
                &context.State, context.Bot, context.Target, &profileAction);
            uint32 const spellId = profileAction.SpellId;
            context.Situation = "open_world_combat";
            context.Action = spellId ? "cast_combat_spell" : "attack";
            if (result == BotActionResult::Ok && spellId)
            {
                std::string raw = BuildRawJson(context.Bot, context.Target);
                std::string semantic = BuildSemanticJson(context.Bot, context.Target,
                    context.Situation.c_str(), &context.Power, context.Stage, context.ChosenActivity.Activity);
                RecordEvent(context.State, context.Bot, "spell_cast", context.Target, "ok",
                    raw.c_str(), semantic.c_str(), 0.0f, 0, spellId);
            }
            if (!context.State.WasInCombat)
            {
                std::string raw = BuildRawJson(context.Bot, context.Target);
                std::string semantic = BuildSemanticJson(context.Bot, context.Target,
                    context.Situation.c_str(), &context.Power, context.Stage, context.ChosenActivity.Activity);
                RecordEvent(context.State, context.Bot, "combat_started", context.Target, "ok",
                    raw.c_str(), semantic.c_str());
            }
            context.State.WasInCombat = true;
            context.State.LastDecisionHandler = "combat";
            if (result == BotActionResult::Ok
                && (context.State.LastCombatAttempt.Reason == "no_line_of_sight"
                    || context.State.LastCombatAttempt.Reason == "target_missing"
                    || context.State.LastCombatAttempt.Reason == "target_dead"
                    || context.State.LastCombatAttempt.Reason == "target_not_attackable"))
                return BotActionArbitration::Outcome::Retryable(
                    context.State.LastCombatAttempt.Reason);
            BotActionArbitration::Outcome outcome =
                BotActionArbitration::FromBotActionResult(result);
            return outcome.Result == BotActionArbitration::Disposition::NotApplicable
                ? BotActionArbitration::Outcome::Retryable(
                    profileAction.DebugName.empty()
                        ? std::string_view("profile_combat_retryable")
                        : std::string_view(profileAction.DebugName))
                : outcome;
        };
        context.State.DecisionKernel.Submit(std::move(combat));

}
