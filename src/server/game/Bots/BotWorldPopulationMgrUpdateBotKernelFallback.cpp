#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/BotActionExecutor.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"

#include "Creature.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

#include <string>
#include <string_view>
#include <utility>

using BotWorldPopulationMgrNativeHelpers::IsNativeCombatObserved;

void BotWorldPopulationMgr::SubmitValidationKernelFallbackCandidates(
    BotUpdateContext& context)
{
        BotActionArbitration::Candidate route;
        route.Key = "world.validation_route";
        route.Source = "validation_route_adapter";
        route.ActionPriority = BotActionArbitration::Priority::Mechanic;
        route.UtilityScore = 3.0f;
        route.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::Movement,
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast,
            BotActionArbitration::Resource::Target,
            BotActionArbitration::Resource::Interaction);
        route.Attempt = [&]()
        {
            if (context.AdaptiveDrudgeOwnsNode || context.AdaptiveMagmawOwnsNode
                || context.AdaptiveOmnotronOwnsNode || context.AdaptiveMaloriakOwnsNode
                || context.AdaptiveChimaeronOwnsNode || context.AdaptiveAtramedesOwnsNode
                || context.AdaptiveNefarianOwnsNode || context.AdaptiveNativeRouteOwnsNode)
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
                                            : (context.AdaptiveNefarianOwnsNode
                                                ? "adaptive_nefarian_owns_live_encounter"
                                                : "native_route_contract_owns_node")))))));
            Unit* const targetBeforeRoute = context.Target;
            ObjectGuid const stateTargetBeforeRoute = context.State.TargetGuid;
            uint64 const previousPathChangeMs = context.State.LastPathChangeMs;
            uint64 const previousCombatAttemptMs = context.State.LastCombatAttempt.RecordedAtMs;
            bool const handled = TryValidationRouteObjective(context.State, context.Bot, context.Power,
                context.Stage, context.ChosenActivity.Activity, context.Situation, context.Action, context.Target);
            if (!handled)
                return BotActionArbitration::Outcome::NotApplicable(
                    "route_not_applicable");
            context.State.LastDecisionHandler = "validation_route";
            if (context.State.ValidationRouteTerminalState)
                return BotActionArbitration::Outcome::Terminal(
                    context.State.ValidationRouteTerminalReason.empty()
                        ? std::string_view("route_terminal")
                        : std::string_view(context.State.ValidationRouteTerminalReason));
            if (context.State.LastPathChangeMs > previousPathChangeMs && context.State.ActivePathValid)
                return BotActionArbitration::Outcome::Started(
                    "route_movement_submitted");
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
                            "route_native_combat_observed")
                        : BotActionArbitration::Outcome::Started(
                            "route_combat_submitted");
                }
                if (result == "casting" || result == "global_cooldown")
                    return BotActionArbitration::Outcome::Started(
                        "route_combat_scheduled");
                return BotActionArbitration::Outcome::Retryable(
                    context.State.LastCombatAttempt.Reason.empty()
                        ? std::string_view("route_combat_retryable")
                        : std::string_view(context.State.LastCombatAttempt.Reason));
            }
            bool const routeYield = context.Action.find("hold") != std::string::npos
                || context.Action.find("wait") != std::string::npos
                || context.Action.find("blocked") != std::string::npos
                || context.Action.find("pending") != std::string::npos
                || context.Action.find("retry") != std::string::npos
                || context.Action.find("failed") != std::string::npos
                || context.Action == "validation_route_wrong_map";
            if (routeYield)
            {
                // Legacy route handlers mutate their output context.Target before
                // returning a hold. Restore a still-valid native combat context.Target
                // so lower-priority healing/damage candidates can actually
                // fall through during this migration.
                if (targetBeforeRoute && targetBeforeRoute->IsAlive()
                    && context.Bot->IsValidAttackTarget(targetBeforeRoute)
                    && (context.Bot->IsInCombat() || targetBeforeRoute->IsInCombat()))
                {
                    context.Target = targetBeforeRoute;
                    context.State.TargetGuid = stateTargetBeforeRoute;
                }
                return BotActionArbitration::Outcome::Retryable(
                    context.State.LastNoProgressReason.empty()
                        ? std::string_view("route_retryable")
                        : std::string_view(context.State.LastNoProgressReason));
            }
            return BotActionArbitration::Outcome::Started(
                "route_handled_pending_postcondition");
        };
        context.State.DecisionKernel.Submit(std::move(route));

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
            if (context.AdaptiveMagmawOwnsNode || context.AdaptiveOmnotronOwnsNode
                || context.AdaptiveMaloriakOwnsNode || context.AdaptiveChimaeronOwnsNode
                || context.AdaptiveAtramedesOwnsNode || context.AdaptiveNefarianOwnsNode)
                return BotActionArbitration::Outcome::NotApplicable(
                    context.AdaptiveMagmawOwnsNode
                        ? "adaptive_magmaw_owns_live_encounter"
                        : (context.AdaptiveOmnotronOwnsNode
                            ? "adaptive_omnotron_owns_live_encounter"
                            : (context.AdaptiveMaloriakOwnsNode
                                ? "adaptive_maloriak_owns_live_encounter"
                                : (context.AdaptiveChimaeronOwnsNode
                                    ? "adaptive_chimaeron_owns_live_encounter"
                                    : (context.AdaptiveAtramedesOwnsNode
                                        ? "adaptive_atramedes_owns_live_encounter"
                                        : "adaptive_nefarian_owns_live_encounter")))));
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
            if (!context.Target || !context.Target->IsAlive())
                return BotActionArbitration::Outcome::NotApplicable(
                    "no_live_combat_target");
            char const* rejectReason = nullptr;
            if (!context.Bot->IsInCombat() && !IsQuestRelevantTarget(context.Bot, context.Target)
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
