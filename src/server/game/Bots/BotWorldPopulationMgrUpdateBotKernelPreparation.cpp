#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAdaptiveAtramedesStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotAdaptiveChimaeronStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotAdaptiveDrudgeStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeActivationState.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotAdaptiveMaloriakStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotAdaptiveOmnotronStrategy.h"
#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "GossipDef.h"
#include "ObjectAccessor.h"
#include "Player.h"

#include <algorithm>
#include <optional>
#include <string>
#include <variant>

using BotWorldPopulationMgrSpellSemantics::NowMs;

void BotWorldPopulationMgr::PrepareValidationKernel(
    BotUpdateContext& context)
{
        context.DecisionNowMs = NowMs();
        context.State.DecisionKernel.Begin(context.DecisionNowMs);
        // Adaptive encounter ownership is recomputed from the current
        // observation. Do not let a vanished Magmaw node retain its previous
        // parasite area/dot authority into a generic profile tick.
        context.State.MagmawParasiteCombat = {};
        SubmitRaidPrepullConsumableCandidate(context);

        if (std::optional<BotNativeAction::Candidate> combatRes =
                BuildCombatResNativeActionCandidate(context.State, context.Bot,
                    context.DecisionNowMs))
        {
            BotActionArbitration::Candidate candidate;
            candidate.Key = combatRes->Id.Key();
            candidate.Source = combatRes->Id.Strategy;
            candidate.ActionPriority = combatRes->ActionPriority;
            candidate.UtilityScore = combatRes->Utility;
            candidate.RequiredResources = combatRes->Resources();
            candidate.ExpiresAtMs = combatRes->ExpiresAtMs;
            candidate.RetryBaseMs = 100;
            candidate.RetryMaxMs = 1000;
            ObjectGuid const combatResTarget = combatRes->Id.Actor;
            candidate.Attempt = [&, intent = combatRes->Action,
                                    combatResTarget]()
            {
                BotActionArbitration::Outcome outcome =
                    ExecuteNativeActionIntent(context.State, context.Bot, intent,
                        BotMovementArbitration::Owner::Support,
                        BotMovementArbitration::Priority::Support);
                if (outcome.Result
                    == BotActionArbitration::Disposition::Committed)
                {
                    context.Situation = "validation_route_resurrection";
                    if (std::holds_alternative<
                            BotNativeAction::CombatResApproach>(intent))
                        context.Action = "typed_combat_res_approach";
                    else if (std::holds_alternative<
                            BotNativeAction::CombatResCast>(intent))
                        context.Action = "typed_combat_res_cast";
                    else
                        context.Action = "typed_combat_res_accept";
                    context.Target = ObjectAccessor::GetUnit(*context.Bot,
                        combatResTarget);
                    context.State.LastDecisionHandler = "typed_combat_res";
                }
                return outcome;
            };
            context.State.DecisionKernel.Submit(std::move(candidate));
        }

        if (Cohort().EncounterSnapshot)
        {
            BotEncounter::Blackboard const& blackboard =
                *Cohort().EncounterSnapshot;
            context.AdaptiveNativeRouteOwnsNode =
                !blackboard.Route.InteractionAction.empty()
                || !blackboard.Route.CompletionKind.empty();

            auto actorWithEntry = [&blackboard](uint32 entry)
                -> BotEncounter::ActorSnapshot const*
            {
                auto find = [entry](std::vector<BotEncounter::ActorSnapshot> const& actors)
                    -> BotEncounter::ActorSnapshot const*
                {
                    auto itr = std::find_if(actors.begin(), actors.end(),
                        [entry](BotEncounter::ActorSnapshot const& actor)
                        {
                            return actor.Entry == entry && actor.Alive;
                        });
                    return itr == actors.end() ? nullptr : &*itr;
                };
                if (BotEncounter::ActorSnapshot const* actor = find(blackboard.Hostiles))
                    return actor;
                if (BotEncounter::ActorSnapshot const* actor = find(blackboard.Summons))
                    return actor;
                return find(blackboard.Interactables);
            };

            bool nativePostconditionSatisfied = false;
            BotEncounter::ActorSnapshot const* completionActor =
                actorWithEntry(blackboard.Route.CompletionEntry);
            if (blackboard.Route.CompletionKind == "gameobject_selectable")
                nativePostconditionSatisfied = completionActor
                    && completionActor->Selectable && completionActor->Interactable;
            else if (blackboard.Route.CompletionKind == "boss_summoned"
                || blackboard.Route.CompletionKind == "creature_summoned")
                nativePostconditionSatisfied = completionActor != nullptr;
            else if (blackboard.Route.CompletionKind == "aura_present")
                nativePostconditionSatisfied = completionActor
                    && std::any_of(completionActor->Auras.begin(), completionActor->Auras.end(),
                        [&blackboard](BotEncounter::AuraSnapshot const& aura)
                        {
                            return aura.SpellId == blackboard.Route.CompletionSpellId;
                        });
            else if (blackboard.Route.CompletionKind == "creature_aggressive_with_victim")
                nativePostconditionSatisfied = completionActor
                    && completionActor->ReactAggressive
                    && !completionActor->VictimGuid.IsEmpty();
            else if (blackboard.Route.CompletionKind == "creature_grounded_aggressive_or_engaged")
                nativePostconditionSatisfied = completionActor
                    && !completionActor->Flying
                    && (completionActor->ReactAggressive
                        || completionActor->InCombat
                        || !completionActor->VictimGuid.IsEmpty());

            bool nativePostconditionAlreadyRecorded =
                std::any_of(Party().Bots.begin(), Party().Bots.end(),
                    [this](WorldBotState const& cohortState)
                    {
                        return cohortState.ValidationRouteTerminalState
                            && cohortState.ValidationRouteTerminalGeneration
                                == Party().ValidationRouteGeneration
                            && cohortState.ValidationRouteTerminalReason
                                == "native_postcondition";
                    });
            if (nativePostconditionSatisfied && !nativePostconditionAlreadyRecorded)
            {
                uint64 const observedAtMs = NowMs();
                for (WorldBotState& cohortState : Party().Bots)
                {
                    cohortState.ValidationRouteTerminalState = true;
                    cohortState.ValidationRouteTerminalAtMs = observedAtMs;
                    cohortState.ValidationRouteTerminalGeneration =
                        Party().ValidationRouteGeneration;
                    cohortState.ValidationRouteTerminalReason =
                        "native_postcondition";
                }
                std::string raw = BuildRawJson(context.Bot,
                    completionActor ? ObjectAccessor::GetUnit(*context.Bot,
                        completionActor->Guid) : nullptr);
                std::string semantic = BuildSemanticJson(context.Bot, nullptr,
                    "native_route_postcondition", &context.Power, context.Stage,
                    context.ChosenActivity.Activity);
                RecordEvent(context.State, context.Bot, "native_route_postcondition",
                    completionActor ? ObjectAccessor::GetUnit(*context.Bot,
                        completionActor->Guid) : nullptr,
                    blackboard.Route.CompletionKind.c_str(), raw.c_str(),
                    semantic.c_str(), 1.0f,
                    blackboard.Route.CompletionEntry,
                    blackboard.Route.CompletionSpellId);
            }

            if (!nativePostconditionSatisfied
                && !blackboard.Route.InteractionAction.empty())
            {
                ObjectGuid electedInteractor;
                for (BotEncounter::ActorSnapshot const& member : blackboard.Players)
                    if (member.Alive && (electedInteractor.IsEmpty()
                            || member.Guid.GetRawValue()
                                < electedInteractor.GetRawValue()))
                        electedInteractor = member.Guid;

                BotEncounter::ActorSnapshot const* interactionActor =
                    actorWithEntry(blackboard.Route.InteractionEntry);
                if (interactionActor && context.Bot->GetGUID() == electedInteractor)
                {
                    BotNativeAction::Candidate interaction;
                    interaction.Id.ScopeKey = blackboard.CurrentScope.Key();
                    interaction.Id.Strategy = "native_route_interaction";
                    interaction.Id.Mechanic = blackboard.Route.InteractionAction;
                    interaction.Id.Actor = interactionActor->Guid;
                    interaction.Id.EventGeneration = blackboard.Revision;
                    interaction.ActionPriority =
                        BotActionArbitration::Priority::Mechanic;
                    interaction.Utility = 6.0f;
                    interaction.ExpiresAtMs = context.DecisionNowMs + 500;

                    WorldObject* interactionObject =
                        ObjectAccessor::GetWorldObject(*context.Bot, interactionActor->Guid);
                    if (!interactionObject
                        || !context.Bot->IsWithinDistInMap(interactionObject,
                            INTERACTION_DISTANCE))
                        interaction.Action = BotNativeAction::Move{
                            interactionActor->Position.X,
                            interactionActor->Position.Y,
                            interactionActor->Position.Z };
                    else if (blackboard.Route.InteractionAction
                        == "gameobject_use")
                        interaction.Action = BotNativeAction::GameObjectUse{
                            interactionActor->Guid };
                    else
                    {
                        uint32 const currentMenu =
                            context.Bot->PlayerTalkClass->GetGossipMenu().GetMenuId();
                        bool const sourceBound = context.Bot->PlayerTalkClass
                            ->GetInteractionData().SourceGuid
                                == interactionActor->Guid;
                        bool const configuredMenu = sourceBound
                            && std::find(blackboard.Route.InteractionMenus.begin(),
                                blackboard.Route.InteractionMenus.end(), currentMenu)
                                != blackboard.Route.InteractionMenus.end();
                        interaction.Action = configuredMenu
                            ? BotNativeAction::Intent(BotNativeAction::GossipSelect{
                                interactionActor->Guid, currentMenu,
                                blackboard.Route.InteractionOption })
                            : BotNativeAction::Intent(BotNativeAction::GossipOpen{
                                interactionActor->Guid });
                    }

                    BotActionArbitration::Candidate candidate;
                    candidate.Key = interaction.Id.Key();
                    candidate.Source = interaction.Id.Strategy;
                    candidate.ActionPriority = interaction.ActionPriority;
                    candidate.UtilityScore = interaction.Utility;
                    candidate.RequiredResources = interaction.Resources();
                    candidate.ExpiresAtMs = interaction.ExpiresAtMs;
                    candidate.Attempt = [&, intent = interaction.Action]()
                    {
                        BotActionArbitration::Outcome outcome =
                            ExecuteNativeActionIntent(context.State, context.Bot, intent,
                                BotMovementArbitration::Owner::Route,
                                BotMovementArbitration::Priority::Route);
                        if (outcome.Result
                            == BotActionArbitration::Disposition::Committed)
                        {
                            context.Situation = "native_route_interaction";
                            context.Action = "native_route_interaction_submitted";
                            context.State.LastDecisionHandler =
                                "native_route_interaction";
                        }
                        return outcome;
                    };
                    context.State.DecisionKernel.Submit(std::move(candidate));
                }
            }

            BotEncounter::AdaptiveDrudgeStrategy drudgeStrategy;
            BotEncounter::AdaptiveDrudgePlan drudgePlan = drudgeStrategy.Propose(
                *Cohort().EncounterSnapshot, context.Bot->GetGUID(), GetDungeonRole(context.Bot));
            context.AdaptiveDrudgeOwnsNode = drudgePlan.OwnsNode;
            context.AdaptiveDrudgeTankTargetGuid = drudgePlan.TankTarget;
            context.AdaptiveDrudgeMovement = std::move(drudgePlan.Movement);

            bool const exactDrudgeProfile =
                Cohort().Config.ValidationRouteMechanicProfile
                    == "trash_two_tank_charge_lanes";
            context.DrudgeCombatAuthorityAllowed =
                !exactDrudgeProfile || !context.AdaptiveDrudgeOwnsNode;
            if (exactDrudgeProfile && context.AdaptiveDrudgeOwnsNode)
            {
                auto exactTankRosterObserved = [this](auto const& observed)
                {
                    auto const& tankSlots =
                        Cohort().Config.ValidationRouteSplitLaneTankSlots;
                    if (tankSlots.size() != 2 || observed.size() != 2)
                        return false;
                    for (uint32 slot : tankSlots)
                    {
                        auto roster = std::find_if(Cohort().Raid.RosterByGuid.begin(),
                            Cohort().Raid.RosterByGuid.end(),
                            [slot](auto const& candidate)
                            {
                                return candidate.second.Active
                                    && candidate.second.LeaseOwned
                                    && candidate.second.Role == "tank"
                                    && candidate.second.SlotIndex + 1 == slot;
                            });
                        if (roster == Cohort().Raid.RosterByGuid.end()
                            || !observed.count(roster->first))
                            return false;
                    }
                    return true;
                };

                auto const& party = Party();
                bool const prepullStaged = party.ValidationRouteDrudgePrepullStaged
                    && party.ValidationRouteDrudgePrepullAttemptId == Cohort().AttemptId
                    && party.ValidationRouteDrudgePrepullWipeGeneration
                        == Cohort().Raid.WipeGeneration
                    && party.ValidationRouteDrudgePrepullRouteGeneration
                        == party.ValidationRouteGeneration;
                bool const seedScope =
                    party.ValidationRouteDrudgeThreatSeedAttemptId == Cohort().AttemptId
                    && party.ValidationRouteDrudgeThreatSeedWipeGeneration
                        == Cohort().Raid.WipeGeneration
                    && party.ValidationRouteDrudgeThreatSeedRouteGeneration
                        == party.ValidationRouteGeneration;
                bool seedLane0 = false;
                bool seedLane1 = false;
                if (seedScope)
                    for (auto const& evidence :
                        party.ValidationRouteDrudgeThreatSeedEvidenceRows)
                        if (evidence.ActionSucceeded && evidence.ProfileActionValid
                            && evidence.AttemptId == Cohort().AttemptId
                            && evidence.WipeGeneration == Cohort().Raid.WipeGeneration
                            && evidence.RouteGeneration == party.ValidationRouteGeneration)
                        {
                            if (evidence.SourceLane == 0)
                                seedLane0 = true;
                            else if (evidence.SourceLane == 1)
                                seedLane1 = true;
                        }
                bool const seedProfileActionsAccepted = seedScope
                    && party.ValidationRouteDrudgeThreatSeedComplete
                    && !party.ValidationRouteDrudgeThreatSeedFailure
                    && party.ValidationRouteDrudgeThreatSeedRosterGuids.size() == 2
                    && seedLane0 && seedLane1;
                bool const seedWindowClosedOrFailed = seedScope
                    && (party.ValidationRouteDrudgeThreatSeedClosed
                        || party.ValidationRouteDrudgeThreatSeedFailure);
                bool const firstNativeRushObserved = std::any_of(
                    party.ValidationRouteDrudgeChargeObservations.begin(),
                    party.ValidationRouteDrudgeChargeObservations.end(),
                    [this](auto const& observation)
                    {
                        return observation.AttemptId == Cohort().AttemptId
                            && observation.WipeGeneration == Cohort().Raid.WipeGeneration
                            && observation.RouteGeneration == Party().ValidationRouteGeneration
                            && observation.Landed;
                    });
                bool const exactRosterReseparated =
                    party.ValidationRouteDrudgeReseparatedRosterGuids.size()
                    == Cohort().Raid.RosterByGuid.size()
                    && !Cohort().Raid.RosterByGuid.empty()
                    && std::all_of(Cohort().Raid.RosterByGuid.begin(),
                        Cohort().Raid.RosterByGuid.end(),
                        [&party](auto const& roster)
                        {
                            return roster.second.Active && roster.second.LeaseOwned
                                && party.ValidationRouteDrudgeReseparatedRosterGuids
                                    .count(roster.first);
                        });
                bool const profileActionAccepted =
                    std::any_of(party.ValidationRouteDrudgeProfileActionRosterGuids.begin(),
                        party.ValidationRouteDrudgeProfileActionRosterGuids.end(),
                        [this](uint32 guid)
                        {
                            auto roster = Cohort().Raid.RosterByGuid.find(guid);
                            return roster != Cohort().Raid.RosterByGuid.end()
                                && roster->second.Active && roster->second.LeaseOwned;
                        });

                BotRaidDrudgeActivation::Input activationInput;
                activationInput.ExactRouteProfile = true;
                activationInput.ExactRosterPrepullStaged = prepullStaged;
                activationInput.BothTankAnchorsAccepted =
                    exactTankRosterObserved(
                        party.ValidationRouteDrudgeOwnershipRosterGuids);
                activationInput.BothTankVictimsAccepted =
                    exactTankRosterObserved(
                        party.ValidationRouteDrudgeTauntRosterGuids);
                activationInput.SeedProfileActionsAccepted =
                    seedProfileActionsAccepted;
                activationInput.SeedWindowClosedOrFailed =
                    seedWindowClosedOrFailed;
                activationInput.FirstNativeRushObserved = firstNativeRushObserved;
                activationInput.ExactRosterReseparated = exactRosterReseparated;
                activationInput.ProfileActionAccepted = profileActionAccepted;
                context.DrudgeCombatAuthorityAllowed =
                    BotRaidDrudgeActivation::Evaluate(activationInput)
                        .CombatAuthorityAllowed;
            }

            ObjectGuid const adaptiveTargetGuid = std::string(GetDungeonRole(context.Bot)) == "tank"
                ? drudgePlan.TankTarget : drudgePlan.DamageTarget;
            if (!adaptiveTargetGuid.IsEmpty())
                if (Unit* adaptiveTarget = ObjectAccessor::GetUnit(*context.Bot, adaptiveTargetGuid);
                    adaptiveTarget && adaptiveTarget->IsAlive()
                        && context.Bot->IsValidAttackTarget(adaptiveTarget))
                {
                    context.Target = adaptiveTarget;
                    context.State.TargetGuid = adaptiveTargetGuid;
                }

            if (context.AdaptiveDrudgeOwnsNode)
                for (BotEncounter::ActorSnapshot const& hostile : Cohort().EncounterSnapshot->Hostiles)
                    if (hostile.Entry == BotEncounter::AdaptiveDrudgeStrategy::DrudgeEntry
                        && hostile.Alive && (hostile.InCombat || hostile.HealthPct < 99.9f))
                    {
                        Party().ValidationRoutePackObservedEngagement = true;
                        break;
                    }

            // The bait pair must read and write one encounter-scoped
            // transition. Keep that state on the deterministic fire-mage
            // owner (or the hunter when the mage is absent); per-bot
            // MovementLease remains only the short native arbitration lease.
            WorldBotState* magmawLaneOwner = &context.State;
            std::pair<ObjectGuid, ObjectGuid> const magmawBaiters =
                BotEncounter::MagmawParasitePolicy::ResolveFixedBaiters(
                    *Cohort().EncounterSnapshot);
            ObjectGuid const magmawLaneOwnerGuid =
                magmawBaiters.first.IsEmpty() ? magmawBaiters.second
                    : magmawBaiters.first;
            if (!magmawLaneOwnerGuid.IsEmpty())
                for (WorldBotState& candidate : Party().Bots)
                    if (candidate.Guid == magmawLaneOwnerGuid)
                    {
                        magmawLaneOwner = &candidate;
                        break;
                    }

            BotEncounter::AdaptiveMagmawStrategy magmawStrategy;
            BotEncounter::AdaptiveMagmawPlan magmawPlan = magmawStrategy.Propose(
                *Cohort().EncounterSnapshot, context.Bot->GetGUID(),
                GetDungeonRole(context.Bot), &context.State.MovementLease,
                context.State.ActivePathValid, context.State.IsMoving,
                &magmawLaneOwner->MagmawLaneTransition,
                &context.State.MagmawParasiteHazard);
            context.AdaptiveMagmawOwnsNode = magmawPlan.OwnsNode;
            context.State.MagmawParasiteCombat = magmawPlan.ParasiteCombat;
            context.AdaptiveMagmawSuppressOffense = magmawPlan.SuppressOffense;
            context.AdaptiveMagmawSuppressReason = magmawPlan.SuppressReason;
            context.AdaptiveMagmawMovement = std::move(magmawPlan.Movement);
            context.AdaptiveMagmawInteraction = std::move(magmawPlan.Interaction);
            if (!magmawPlan.DamageTarget.IsEmpty())
                if (Unit* adaptiveTarget = ObjectAccessor::GetUnit(*context.Bot,
                        magmawPlan.DamageTarget);
                    adaptiveTarget && adaptiveTarget->IsAlive()
                        && context.Bot->IsValidAttackTarget(adaptiveTarget))
                {
                    context.Target = adaptiveTarget;
                    context.State.TargetGuid = magmawPlan.DamageTarget;
                }

            BotEncounter::AdaptiveOmnotronStrategy omnotronStrategy;
            BotEncounter::AdaptiveOmnotronPlan omnotronPlan =
                omnotronStrategy.Propose(*Cohort().EncounterSnapshot,
                    context.Bot->GetGUID(), GetDungeonRole(context.Bot));
            context.AdaptiveOmnotronOwnsNode = omnotronPlan.OwnsNode;
            context.AdaptiveOmnotronSuppressOffense = omnotronPlan.SuppressOffense;
            context.AdaptiveOmnotronInterruptTargetGuid = omnotronPlan.InterruptTarget;
            context.AdaptiveOmnotronMovement = std::move(omnotronPlan.Movement);
            if (!omnotronPlan.DamageTarget.IsEmpty())
                if (Unit* adaptiveTarget = ObjectAccessor::GetUnit(*context.Bot,
                        omnotronPlan.DamageTarget);
                    adaptiveTarget && adaptiveTarget->IsAlive()
                        && context.Bot->IsValidAttackTarget(adaptiveTarget))
                {
                    context.Target = adaptiveTarget;
                    context.State.TargetGuid = omnotronPlan.DamageTarget;
                }

            BotEncounter::AdaptiveMaloriakStrategy maloriakStrategy;
            BotEncounter::AdaptiveMaloriakPlan maloriakPlan =
                maloriakStrategy.Propose(*Cohort().EncounterSnapshot,
                    context.Bot->GetGUID(), GetDungeonRole(context.Bot));
            context.AdaptiveMaloriakOwnsNode = maloriakPlan.OwnsNode;
            context.AdaptiveMaloriakInterruptTargetGuid = maloriakPlan.InterruptTarget;
            context.AdaptiveMaloriakDispelTargetGuid = maloriakPlan.DispelTarget;
            context.AdaptiveMaloriakMovement = std::move(maloriakPlan.Movement);
            if (!maloriakPlan.DamageTarget.IsEmpty())
                if (Unit* adaptiveTarget = ObjectAccessor::GetUnit(*context.Bot,
                        maloriakPlan.DamageTarget);
                    adaptiveTarget && adaptiveTarget->IsAlive()
                        && context.Bot->IsValidAttackTarget(adaptiveTarget))
                {
                    context.Target = adaptiveTarget;
                    context.State.TargetGuid = maloriakPlan.DamageTarget;
                }

            BotEncounter::AdaptiveChimaeronStrategy chimaeronStrategy;
            BotEncounter::AdaptiveChimaeronPlan chimaeronPlan =
                chimaeronStrategy.Propose(*Cohort().EncounterSnapshot,
                    context.Bot->GetGUID(), GetDungeonRole(context.Bot));
            context.AdaptiveChimaeronOwnsNode = chimaeronPlan.OwnsNode;
            context.AdaptiveChimaeronHealingDisabled = chimaeronPlan.HealingDisabled;
            context.AdaptiveChimaeronPriorityHealTargetGuid =
                chimaeronPlan.PriorityHealTarget;
            context.AdaptiveChimaeronMovement = std::move(chimaeronPlan.Movement);
            if (!chimaeronPlan.DamageTarget.IsEmpty())
                if (Unit* adaptiveTarget = ObjectAccessor::GetUnit(*context.Bot,
                        chimaeronPlan.DamageTarget);
                    adaptiveTarget && adaptiveTarget->IsAlive()
                        && context.Bot->IsValidAttackTarget(adaptiveTarget))
                {
                    context.Target = adaptiveTarget;
                    context.State.TargetGuid = chimaeronPlan.DamageTarget;
                }

            BotEncounter::AdaptiveAtramedesStrategy atramedesStrategy;
            BotEncounter::AdaptiveAtramedesPlan atramedesPlan =
                atramedesStrategy.Propose(*Cohort().EncounterSnapshot,
                    context.Bot->GetGUID(), GetDungeonRole(context.Bot));
            context.AdaptiveAtramedesOwnsNode = atramedesPlan.OwnsNode;
            context.AdaptiveAtramedesMovement = std::move(atramedesPlan.Movement);
            context.AdaptiveAtramedesInteraction = std::move(atramedesPlan.Interaction);
            if (!atramedesPlan.DamageTarget.IsEmpty())
                if (Unit* adaptiveTarget = ObjectAccessor::GetUnit(*context.Bot,
                        atramedesPlan.DamageTarget);
                    adaptiveTarget && adaptiveTarget->IsAlive()
                        && context.Bot->IsValidAttackTarget(adaptiveTarget))
                {
                    context.Target = adaptiveTarget;
                    context.State.TargetGuid = atramedesPlan.DamageTarget;
                }

            BotEncounter::AdaptiveNefarianStrategy nefarianStrategy;
            BotEncounter::AdaptiveNefarianPlan nefarianPlan =
                nefarianStrategy.Propose(*Cohort().EncounterSnapshot,
                    context.Bot->GetGUID(), GetDungeonRole(context.Bot));
            context.AdaptiveNefarianOwnsNode = nefarianPlan.OwnsNode;
            context.AdaptiveNefarianInterruptTargetGuid = nefarianPlan.InterruptTarget;
            context.AdaptiveNefarianMovement = std::move(nefarianPlan.Movement);
            if (!nefarianPlan.DamageTarget.IsEmpty())
                if (Unit* adaptiveTarget = ObjectAccessor::GetUnit(*context.Bot,
                        nefarianPlan.DamageTarget);
                    adaptiveTarget && adaptiveTarget->IsAlive()
                        && context.Bot->IsValidAttackTarget(adaptiveTarget))
                {
                    context.Target = adaptiveTarget;
                    context.State.TargetGuid = nefarianPlan.DamageTarget;
                }
        }


}
