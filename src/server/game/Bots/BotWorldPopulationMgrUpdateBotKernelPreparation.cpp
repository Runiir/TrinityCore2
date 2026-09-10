#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAdaptiveAtramedesStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotAdaptiveChimaeronStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotAdaptiveDrudgeStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeActivationState.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawDamageTargetBinding.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneAuthority.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotAdaptiveMaloriakStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotAdaptiveOmnotronStrategy.h"
#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotSpellResolution.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/BotWorldPopulationMgrRaidConsumables.h"

#include "GossipDef.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "MotionMaster.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

#include <algorithm>
#include <cmath>
#include <optional>
#include <string>
#include <variant>

using BotWorldPopulationMgrSpellSemantics::NowMs;

namespace
{
// Called only after the pure plan matched the authoritative path purpose/scope.
template<class State, class Actor>
void SettleRetainedMagmawFormation(State& state, Actor* bot)
{
    auto* motion = bot->GetMotionMaster();
    float x = 0.0f, y = 0.0f, z = 0.0f;
    constexpr float ActiveDestinationEpsilon = 0.1f;
    bool const matchingNativePath = state.ActivePathSegmentValid
        && motion->GetMotionSlotType(MOTION_SLOT_ACTIVE) == POINT_MOTION_TYPE
        && motion->GetCurrentMovementGeneratorType() == POINT_MOTION_TYPE
        && motion->GetMotionSlotType(MOTION_SLOT_CONTROLLED) == MAX_MOTION_TYPE
        && motion->GetDestination(x, y, z)
        && std::fabs(x - state.ActivePathSegmentToX) <= ActiveDestinationEpsilon
        && std::fabs(y - state.ActivePathSegmentToY) <= ActiveDestinationEpsilon
        && std::fabs(z - state.ActivePathSegmentToZ) <= ActiveDestinationEpsilon;
    if (matchingNativePath)
    {
        bot->StopMoving();
        motion->Clear(MOTION_SLOT_ACTIVE);
        motion->MoveIdle();
    }
    // A replaced or completed native path only retires stale formation evidence.
    state.ActivePathValid = false;
    state.ActivePathPurposeValid = false;
    state.ActivePathSegmentValid = false;
    state.ActivePathTraversalMode.clear();
    state.ActivePathTargetGuid.Clear();
    state.MovementLease = {};
    state.IsMoving = bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING);
}

std::vector<BotEncounter::MagmawStaticDamageRange>
ObserveMagmawStaticDamageRanges(Player const* bot, Unit const* target,
    BotClassSpecActionProfile const& profile)
{
    std::vector<BotEncounter::MagmawStaticDamageRange> ranges;
    if (!bot || !target || profile.MissingProfile)
        return ranges;

    for (BotActionProfileSpell const& action : profile.Spells)
    {
        if (!bot->HasSpell(action.SpellId) || action.TargetSelector != "enemy"
            || !(action.DamageWeight > 0.0f) || action.RequiresGroundTarget
            || action.RequiresMeleeRange || action.RequiresInterruptibleTarget
            || action.Category == BotCombatActionCategory::Aoe
            || action.Category == BotCombatActionCategory::Cleave
            || action.Category == BotCombatActionCategory::OffensiveCooldown)
            continue;
        SpellInfo const* spellInfo =
            BotSpellResolution::Resolve(bot, action.SpellId).Effective;
        if (!spellInfo || spellInfo->IsPositive())
            continue;

        float minimum = action.MinRange > 0.0f
            ? action.MinRange : profile.MinRange;
        float maximum = action.MaxRange > 0.0f
            ? action.MaxRange : profile.MaxRange;
        float nativeMinimum = bot->GetSpellMinRangeForTarget(target, spellInfo);
        if (spellInfo->RangeEntry
            && (spellInfo->RangeEntry->Flags & SPELL_RANGE_RANGED))
            nativeMinimum += bot->GetMeleeRange(target);
        minimum = std::max(minimum, nativeMinimum);

        float nativeMaximum = bot->GetSpellMaxRangeForTarget(target, spellInfo);
        if (spellInfo->RangeEntry
            && (spellInfo->RangeEntry->Flags & SPELL_RANGE_MELEE))
            nativeMaximum = std::max(nativeMaximum,
                bot->GetMeleeRange(target));
        else
            nativeMaximum += bot->GetCombatReach() + target->GetCombatReach();
        maximum = maximum > 0.0f
            ? std::min(maximum, nativeMaximum) : nativeMaximum;
        if (std::isfinite(minimum) && std::isfinite(maximum)
            && minimum >= 0.0f && maximum > minimum)
            ranges.push_back({ minimum, maximum });
    }
    return ranges;
}

BotEncounter::MagmawSupportTargetOpportunities
ObserveMagmawSupportTargetOpportunities(Player const* bot,
    BotEncounter::Blackboard const& board, char const* role)
{
    BotEncounter::MagmawSupportTargetOpportunities opportunities;
    if (!bot || board.Route.NodeId != "bwd.magmaw.encounter")
        return opportunities;

    BotClassSpecActionProfile const profile =
        BotClassSpecActionProfileStore::Build(bot, role);
    auto inspect = [bot, &profile, &opportunities](
        BotEncounter::ActorSnapshot const& actor)
    {
        if (!actor.Alive
            || (actor.Entry != BotEncounter::AdaptiveMagmawStrategy::BossEntry
                && actor.Entry
                    != BotEncounter::AdaptiveMagmawStrategy::ParasiteEntry
                && actor.Entry
                    != BotEncounter::AdaptiveMagmawStrategy::ParasiteAltEntry))
            return;
        Unit* target = ObjectAccessor::GetUnit(*bot, actor.Guid);
        std::vector<BotEncounter::MagmawStaticDamageRange> const ranges =
            ObserveMagmawStaticDamageRanges(bot, target, profile);
        if (BotEncounter::ObserveMagmawStaticDamageOpportunity(
                bot, target, ranges))
            opportunities.Admit(actor.Guid);
    };
    for (BotEncounter::ActorSnapshot const& actor : board.Hostiles)
        inspect(actor);
    for (BotEncounter::ActorSnapshot const& actor : board.Summons)
        inspect(actor);
    return opportunities;
}
}

void BotWorldPopulationMgr::PrepareValidationKernel(
    BotUpdateContext& context)
{
    context.DecisionNowMs = NowMs();
    context.State.DecisionKernel.Begin(context.DecisionNowMs);
    SubmitMagmawTransferLaneCheckpointAfterKernelBegin(context);
    BotEncounter::ResetMagmawTransferLaneIntentComparison(
        context.State.MagmawTransferLaneIntentComparison);
    RaidRuntime& raid = Cohort().Raid;
    BotValidationPrepullCheckpoint::Scope const checkpointScope{
        Cohort().Id, Cohort().AttemptId, Party().ValidationRouteGeneration,
        Cohort().Config.ValidationRouteNodeId };
    bool const checkpointEnabled = Cohort().Config.ValidationRouteEnable
        && Cohort().Config.ValidationPrepullCheckpointEnable
        && Cohort().Config.ValidationRouteKind == "boss";
    raid.ValidationPrepullCheckpoint.Configure(checkpointEnabled,
        checkpointScope, raid.ExpectedSize);
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
            candidate.Attempt = [this, &context, intent = combatRes->Action,
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
                    candidate.Attempt = [this, &context,
                        intent = interaction.Action]()
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

            std::optional<BotEncounter::MagmawDirectionalMobilityInput>
                magmawMobility;
            if (BotEncounter::ActorSnapshot const* actor =
                    Cohort().EncounterSnapshot->FindActor(
                        context.Bot->GetGUID()))
            {
                uint32 const spellId = actor->ClassSpec == "fire_mage"
                    ? 1953u : actor->ClassSpec == "marksmanship_hunter"
                    ? 781u : 0u;
                if (spellId)
                    if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId))
                        magmawMobility =
                            BotEncounter::MagmawDirectionalMobilityInput{
                                spellId, info->GetRecoveryTime() };
            }

            BotEncounter::MagmawRetainedFormationPath const retainedFormation{
                context.State.ActivePathPurposeValid, context.State.ActivePathPurpose,
                context.State.ActivePathAttemptId, context.State.ActivePathWipeGeneration,
                context.State.ActivePathRouteGeneration, context.State.ActivePathRouteNodeId };
            ObjectGuid const magmawStateTargetBefore = context.State.TargetGuid;
            ObjectGuid const magmawContextTargetBefore = context.Target
                ? context.Target->GetGUID() : ObjectGuid::Empty;
            BotEncounter::MagmawFacts const* magmawFacts = Cohort().MagmawFacts
                ? &Cohort().MagmawFacts->Facts() : nullptr;
            std::string const magmawRole = GetDungeonRole(context.Bot);
            BotEncounter::MagmawSupportTargetOpportunities const
                magmawSupportOpportunities =
                    ObserveMagmawSupportTargetOpportunities(context.Bot,
                        *Cohort().EncounterSnapshot, magmawRole.c_str());
            BotEncounter::AdaptiveMagmawStrategy magmawStrategy;
            BotEncounter::AdaptiveMagmawPlan magmawPlan = magmawStrategy.Propose(
                *Cohort().EncounterSnapshot, context.Bot->GetGUID(),
                magmawRole, &context.State.MovementLease,
                context.State.ActivePathValid, context.State.IsMoving,
                &magmawLaneOwner->MagmawLaneTransition,
                &context.State.MagmawParasiteHazard,
                &context.State.MagmawEventMovement, magmawMobility,
                BotEncounter::AdaptiveMagmawStrategy::
                    DefaultMovementProducerOrder,
                magmawFacts,
                &context.State.MagmawPersonalParasiteEscape,
                &Cohort().MagmawParasiteWave, &retainedFormation,
                &magmawSupportOpportunities);
            if (magmawPlan.ReleaseRetainedRangedFormation)
                SettleRetainedMagmawFormation(context.State, context.Bot);

            static std::vector<BotEncounter::MagmawTransferLaneTask> const
                noMagmawTransferLaneTasks;
            auto const& transferLaneShadow =
                Cohort().MagmawTransferLaneTaskShadow;
            auto const& transferLaneTasks = transferLaneShadow
                ? transferLaneShadow->Tasks() : noMagmawTransferLaneTasks;
            BotEncounter::MagmawTransferLaneAuthoritySelection
                transferLaneSelection =
                    BotEncounter::SelectMagmawTransferLaneAuthority(
                        Cohort().Config.MagmawTransferLaneTaskAuthority,
                        transferLaneTasks, context.Bot->GetGUID(),
                        magmawPlan.Movement,
                        magmawLaneOwner->MagmawLaneTransition.TransitionId);
            context.State.MagmawTransferLaneIntentComparison =
                transferLaneSelection.Comparison;
            BotEncounter::ObserveMagmawTransferLaneIntentEpisode(
                context.State.MagmawTransferLaneIntentEpisodeAccumulator,
                transferLaneSelection.Comparison);
            context.AdaptiveMagmawTransferLaneBinding =
                std::move(transferLaneSelection.Binding);
            context.AdaptiveMagmawOwnsNode = magmawPlan.OwnsNode;
            context.State.MagmawParasiteCombat = magmawPlan.ParasiteCombat;
            context.AdaptiveMagmawSuppressOffense = magmawPlan.SuppressOffense;
            context.AdaptiveMagmawSuppressReason = magmawPlan.SuppressReason;
            context.AdaptiveMagmawPriorityHealTargetGuid =
                magmawPlan.PriorityHealTarget;
            context.AdaptiveMagmawMovements =
                std::move(transferLaneSelection.Movements);
            context.AdaptiveMagmawDirectionalMobility =
                std::move(magmawPlan.DirectionalMobility);
            context.AdaptiveMagmawInteraction = std::move(magmawPlan.Interaction);
            BotEncounter::MagmawTargetReturnObservation::Record* targetReturn =
                nullptr;
            if (Cohort().EncounterSnapshot->Route.NodeId
                == "bwd.magmaw.encounter")
            {
                context.State.MagmawTargetReturn =
                    BotEncounter::MagmawTargetReturnObservation::Begin(
                        *Cohort().EncounterSnapshot, magmawFacts,
                        Cohort().AttemptId, Party().ValidationRouteGeneration,
                        magmawPlan.OwnsNode, magmawPlan.DamageTarget,
                        magmawStateTargetBefore, magmawContextTargetBefore,
                        context.State.DesiredMeleeAttackTargetGuid);
                targetReturn = &context.State.MagmawTargetReturn;
            }
            auto observeNative = [this, &context](
                BotEncounter::MagmawTargetReturnObservation::Actor& actor)
            {
                Unit* unit = actor.Guid.IsEmpty() ? nullptr
                    : ObjectAccessor::GetUnit(*context.Bot, actor.Guid);
                BotEncounter::MagmawTargetReturnObservation::ObserveNative(
                    actor, unit != nullptr, unit && unit->IsAlive(),
                    unit && context.Bot->IsValidAttackTarget(unit));
            };
            if (targetReturn)
            {
                observeNative(targetReturn->Body);
                observeNative(targetReturn->Head);
            }
            using TargetBindResult =
                BotEncounter::MagmawTargetReturnObservation::BindResult;
            TargetBindResult bindResult = targetReturn
                ? targetReturn->Result : TargetBindResult::NotEvaluated;
            Unit* adaptiveTarget = magmawPlan.DamageTarget.IsEmpty()
                ? nullptr : ObjectAccessor::GetUnit(*context.Bot,
                    magmawPlan.DamageTarget);
            if (!magmawPlan.DamageTarget.IsEmpty())
            {
                if (targetReturn)
                    BotEncounter::MagmawTargetReturnObservation::
                        ObserveProposedNative(*targetReturn,
                            adaptiveTarget != nullptr,
                            adaptiveTarget && adaptiveTarget->IsAlive(),
                            adaptiveTarget && context.Bot->IsValidAttackTarget(
                                adaptiveTarget));
            }
            using NativeBindResult =
                BotEncounter::MagmawDamageTargetBindResult;
            NativeBindResult const nativeBind =
                BotEncounter::BindMagmawDamageTarget(context,
                    magmawPlan.DamageTarget,
                    magmawPlan.ClearOptionalDamageTarget, adaptiveTarget);
            if (nativeBind == NativeBindResult::NativeMissing)
                bindResult = TargetBindResult::NativeMissing;
            else if (nativeBind == NativeBindResult::NativeDead)
                bindResult = TargetBindResult::NativeDead;
            else if (nativeBind == NativeBindResult::NativeInvalid)
                bindResult = TargetBindResult::NativeInvalid;
            else if (nativeBind == NativeBindResult::Bound)
                bindResult = TargetBindResult::Bound;
            if (targetReturn)
                BotEncounter::MagmawTargetReturnObservation::Finish(
                    *targetReturn, bindResult, context.State.TargetGuid,
                    context.Target ? context.Target->GetGUID()
                        : ObjectGuid::Empty);

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

        if (raid.ValidationPrepullCheckpoint.Enabled()
            && !raid.ValidationPrepullCheckpoint.Released())
        {
            bool formationPending = false;
            for (size_t movementIndex = 0;
                movementIndex < context.AdaptiveMagmawMovements.Size();
                ++movementIndex)
            {
                BotEncounter::MagmawMovementProposalOrigin const origin =
                    context.AdaptiveMagmawMovements.Origin(movementIndex);
                formationPending = formationPending
                    || origin == BotEncounter::MagmawMovementProposalOrigin::
                        PrepullFormation
                    || origin == BotEncounter::MagmawMovementProposalOrigin::
                        FormationRestore;
            }
            BotValidationPrepullCheckpoint::MemberReceipt receipt;
            receipt.Guid = context.Bot->GetGUID().GetCounter();
            receipt.Alive = context.Bot->IsAlive();
            receipt.OutOfCombat = !context.Bot->IsInCombat();
            receipt.Formed = context.AdaptiveMagmawOwnsNode
                && !formationPending;
            auto const member = raid.PrepullConsumablesByGuid.find(receipt.Guid);
            if (member != raid.PrepullConsumablesByGuid.end()
                && member->second.AttemptId == Cohort().AttemptId
                && member->second.RouteGeneration
                    == Party().ValidationRouteGeneration)
            {
                using BotWorldPopulationMgrRaidConsumables::ReceiptReady;
                receipt.Flask = ReceiptReady(member->second.Flask);
                receipt.Food = ReceiptReady(member->second.Food);
                receipt.Prepot = ReceiptReady(member->second.Prepot);
            }
            raid.ValidationPrepullCheckpoint.Observe(checkpointScope, receipt);
            if (raid.ValidationPrepullCheckpoint.CurrentPhase()
                == BotValidationPrepullCheckpoint::Phase::Ready)
                raid.ValidationPrepullCheckpoint.Release(checkpointScope);
        }
        BotValidationPrepullCheckpoint::InstallAdmissionPolicy(
            context.State.DecisionKernel,
            raid.ValidationPrepullCheckpoint);
        InstallControllerRouteHoldAdmissionPolicy(context);


}
