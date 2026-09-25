#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronFacts.h"

#include "CharmInfo.h"
#include "Creature.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

#include <string>
#include <string_view>
#include <utility>
#include <vector>

// Native submission of the adaptive Omnotron plan (BotAdaptiveOmnotronStrategy.h).
// The strategy chooses; these candidates only submit ordinary player actions
// (movement, autoattack stop, pet follow, interrupt, taunt, dispel) that the
// core validates again. Attempts run after this function returns, so they
// capture only `this`, the live context and values.
using BotWorldPopulationMgrNativeHelpers::IsNativeCombatObserved;
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

void BotWorldPopulationMgr::SubmitAdaptiveOmnotronCandidates(
    BotUpdateContext& context)
{
    if (context.AdaptiveOmnotronMovement
        && context.AdaptiveOmnotronMovement->ExpiresAtMs > context.DecisionNowMs)
    {
        BotActionArbitration::Candidate movement;
        movement.Key = context.AdaptiveOmnotronMovement->Id.Key();
        movement.Source = context.AdaptiveOmnotronMovement->Id.Strategy;
        movement.ActionPriority = context.AdaptiveOmnotronMovement->ActionPriority;
        movement.UtilityScore = context.AdaptiveOmnotronMovement->Utility;
        movement.RequiredResources = context.AdaptiveOmnotronMovement->Resources();
        movement.ExpiresAtMs = context.AdaptiveOmnotronMovement->ExpiresAtMs;
        movement.Attempt = [this, &context,
            intent = BotNativeAction::WithMovementReason(
            context.AdaptiveOmnotronMovement->Action,
            context.AdaptiveOmnotronMovement->Id.Mechanic)]()
        {
            BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                context.State, context.Bot, intent, BotMovementArbitration::Owner::Hazard,
                BotMovementArbitration::Priority::Hazard);
            if (outcome.Result == BotActionArbitration::Disposition::Committed)
            {
                context.Situation = "adaptive_omnotron";
                context.Action = "omnotron_hazard_movement";
                context.State.LastDecisionHandler = "adaptive_omnotron";
            }
            return outcome;
        };
        context.State.DecisionKernel.Submit(std::move(movement));
    }

    if (context.AdaptiveOmnotronSuppressOffense)
    {
        BotActionArbitration::Candidate suppress;
        suppress.Key = "adaptive_omnotron:shield_suppress:"
            + std::to_string(Party().ValidationRouteGeneration);
        suppress.Source = "adaptive_omnotron";
        suppress.ActionPriority = BotActionArbitration::Priority::Mechanic;
        suppress.UtilityScore = 100.0f;
        suppress.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::Pet);
        suppress.Attempt = [this, &context]()
        {
            bool const submitted = SubmitMeleeAutoAttackIntent(context.State,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Mechanic,
                BotActionArbitration::Priority::Mechanic,
                "adaptive_omnotron_shield_suppress");
            if (Pet* pet = context.Bot->GetPet(); pet && pet->GetCharmInfo())
                ExecuteNativeActionIntent(context.State, context.Bot,
                    BotNativeAction::PetCommand{ pet->GetGUID(),
                        context.Bot->GetGUID(), COMMAND_FOLLOW },
                    BotMovementArbitration::Owner::Mechanic,
                    BotMovementArbitration::Priority::Mechanic);
            context.State.TargetGuid.Clear();
            context.Target = nullptr;
            context.Situation = "adaptive_omnotron";
            context.Action = context.AdaptiveOmnotronSuppressReason;
            context.State.LastDecisionHandler = "adaptive_omnotron";
            return submitted
                ? BotActionArbitration::Outcome::Committed(
                    "melee_autoattack_suppression_submitted")
                : BotActionArbitration::Outcome::Retryable(
                    "melee_autoattack_suppression_rejected");
        };
        context.State.DecisionKernel.Submit(std::move(suppress));
    }

    if (!context.AdaptiveOmnotronInterruptTargetGuid.IsEmpty())
    {
        BotActionArbitration::Candidate interrupt;
        interrupt.Key = "adaptive_omnotron:arcane_annihilator:"
            + std::to_string(context.AdaptiveOmnotronInterruptTargetGuid.GetRawValue())
            + ":" + std::to_string(context.AdaptiveOmnotronInterruptOrdinal);
        interrupt.Source = "adaptive_omnotron";
        interrupt.ActionPriority = BotActionArbitration::Priority::Interrupt;
        interrupt.UtilityScore = 90.0f;
        interrupt.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast,
            BotActionArbitration::Resource::Target);
        interrupt.Attempt = [this, &context,
            adaptiveOmnotronInterruptTargetGuid = context.AdaptiveOmnotronInterruptTargetGuid]()
        {
            Unit* caster = ObjectAccessor::GetUnit(*context.Bot,
                adaptiveOmnotronInterruptTargetGuid);
            if (!caster || !caster->IsAlive())
                return BotActionArbitration::Outcome::NotApplicable(
                    "interrupt_caster_stale");
            // Try every known interrupt: a Feral druid knows both Skull Bash
            // forms but only the one for its current form can be cast.
            bool submitted = false;
            for (uint32 spellId : { 6552u, 1766u, 2139u, 57994u,
                    96231u, 47528u, 80964u, 80965u, 15487u, 34490u })
                if (context.Bot->HasSpell(spellId)
                    && TryCastCombatSpell(context.Bot, caster, spellId))
                {
                    submitted = true;
                    break;
                }
            if (!submitted)
                return BotActionArbitration::Outcome::Retryable(
                    "native_interrupt_retryable");
            context.Situation = "adaptive_omnotron";
            context.Action = "arcane_annihilator_interrupt";
            context.State.LastDecisionHandler = "adaptive_omnotron";
            return BotActionArbitration::Outcome::Started(
                "native_interrupt_submitted");
        };
        context.State.DecisionKernel.Submit(std::move(interrupt));
    }

    // Construct ownership: the owner taunts its construct when it attacks
    // anyone else (the plan re-derives ownership from victims every tick).
    if (!context.AdaptiveOmnotronTankTargetGuid.IsEmpty())
    {
        BotActionArbitration::Candidate ownership;
        ownership.Key = "adaptive_omnotron:taunt:"
            + std::to_string(context.AdaptiveOmnotronTankTargetGuid.GetRawValue());
        ownership.Source = "adaptive_omnotron";
        ownership.ActionPriority = BotActionArbitration::Priority::ThreatControl;
        ownership.UtilityScore = 4.0f;
        ownership.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast,
            BotActionArbitration::Resource::Target);
        ownership.Attempt = [this, &context,
            construct = context.AdaptiveOmnotronTankTargetGuid]()
        {
            Unit* golem = ObjectAccessor::GetUnit(*context.Bot, construct);
            if (!golem || !golem->IsAlive())
                return BotActionArbitration::Outcome::Retryable(
                    "assigned_construct_stale");
            if (golem->GetVictim() == context.Bot)
                return BotActionArbitration::Outcome::NotApplicable(
                    "native_ownership_established");
            uint32 tauntSpell = 0;
            switch (context.Bot->getClass())
            {
                case CLASS_WARRIOR: tauntSpell = 355; break;
                case CLASS_PALADIN: tauntSpell = 62124; break;
                case CLASS_DEATH_KNIGHT: tauntSpell = 56222; break;
                case CLASS_DRUID: tauntSpell = 6795; break;
                default: break;
            }
            if (!tauntSpell || !context.Bot->HasSpell(tauntSpell))
                return BotActionArbitration::Outcome::Retryable(
                    "native_taunt_unavailable");
            if (!TryCastCombatSpell(context.Bot, golem, tauntSpell))
                return BotActionArbitration::Outcome::Retryable(
                    "native_taunt_retryable");
            context.Situation = "adaptive_omnotron";
            context.Action = "construct_taunt";
            context.State.LastDecisionHandler = "adaptive_omnotron";
            return BotActionArbitration::Outcome::Started(
                "native_taunt_submitted");
        };
        context.State.DecisionKernel.Submit(std::move(ownership));
    }

    // Soaked In Poison is a poison: Cleanse (4987) or Remove Corruption (2782).
    if (!context.AdaptiveOmnotronDispelTargetGuid.IsEmpty())
    {
        BotActionArbitration::Candidate dispel;
        dispel.Key = "adaptive_omnotron:soaked_in_poison:"
            + std::to_string(context.AdaptiveOmnotronDispelTargetGuid.GetRawValue());
        dispel.Source = "adaptive_omnotron";
        dispel.ActionPriority = BotActionArbitration::Priority::Support;
        dispel.UtilityScore = 80.0f;
        dispel.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast,
            BotActionArbitration::Resource::Target);
        dispel.Attempt = [this, &context,
            carrierGuid = context.AdaptiveOmnotronDispelTargetGuid]()
        {
            Unit* carrier = ObjectAccessor::GetUnit(*context.Bot, carrierGuid);
            if (!carrier || !carrier->IsAlive())
                return BotActionArbitration::Outcome::NotApplicable(
                    "dispel_target_stale");
            uint32 dispelSpell = 0;
            for (uint32 spellId : { 4987u, 2782u })
                if (context.Bot->HasSpell(spellId))
                {
                    dispelSpell = spellId;
                    break;
                }
            if (!dispelSpell)
                return BotActionArbitration::Outcome::Retryable(
                    "native_dispel_unavailable");
            if (!TryCastFriendlySpell(context.Bot, carrier, dispelSpell))
                return BotActionArbitration::Outcome::Retryable(
                    "native_dispel_retryable");
            context.Situation = "adaptive_omnotron";
            context.Action = "soaked_in_poison_cleanse";
            context.State.LastDecisionHandler = "adaptive_omnotron";
            return BotActionArbitration::Outcome::Started(
                "native_dispel_submitted");
        };
        context.State.DecisionKernel.Submit(std::move(dispel));
    }
}

// Adaptive Omnotron owns targets and movement once a construct is engaged, so
// the generic route objective does not run. Called by the fallback submitter
// right after it resets this bot's current-encounter restrictions, this:
// 1. restricts every construct entry except the plan's unshielded constructs,
//    so neither a direct cast nor an area spell can reach a shielded one;
// 2. records the route's engagement, progress and kill-credit evidence. Kill
//    credit belongs to the route target entry, the encounter's credit
//    construct (42180), which shares the pool's health; it is bound as soon as
//    any construct is engaged, even while it is still inactive. The
//    observation never changes target, focus or movement.
void BotWorldPopulationMgr::SubmitAdaptiveOmnotronRouteAuthority(
    BotUpdateContext& context)
{
    if (context.AdaptiveOmnotronOwnsNode)
    {
        std::vector<uint64> allowed;
        for (ObjectGuid guid : context.AdaptiveOmnotronOffenseAllowedGuids)
            allowed.push_back(guid.GetRawValue());
        BotRaidAreaAuthority::SetCurrentEncounterRestrictions(
            context.Bot->GetGUID().GetRawValue(),
            { BotEncounter::Omnotron::ArcanotronEntry,
                BotEncounter::Omnotron::MagmatronEntry,
                BotEncounter::Omnotron::ElectronEntry,
                BotEncounter::Omnotron::ToxitronEntry },
            allowed);
    }

    auto observe = [this, &context]() -> BotActionArbitration::Outcome
    {
        if (!context.AdaptiveOmnotronOwnsNode
            || Cohort().Config.ValidationRouteKind != "boss"
            || Cohort().Config.ValidationRouteNodeId
                != BotEncounter::Omnotron::EncounterNodeId)
            return BotActionArbitration::Outcome::NotApplicable(
                "omnotron_route_observation_not_owned");

        Unit* target = context.Target;
        Creature* creature = target ? target->ToCreature() : nullptr;
        if (!target || !creature || !target->IsAlive()
            || !context.Bot->IsValidAttackTarget(target)
            || !IsNativeCombatObserved(context.Bot, target))
            return BotActionArbitration::Outcome::NotApplicable(
                "omnotron_route_observation_wait_for_native_combat");
        if (!BotEncounter::Omnotron::KindOf(creature->GetEntry()))
            return BotActionArbitration::Outcome::NotApplicable(
                "omnotron_route_observation_target_not_declared");

        RememberValidationRouteBossEngagement(creature);
        if (creature->GetEntry() != Cohort().Config.ValidationRouteTargetEntry)
            if (Creature* credit = creature->FindNearestCreature(
                    Cohort().Config.ValidationRouteTargetEntry, 100.0f, true))
                RememberValidationRouteBossEngagement(credit);

        bool const targetChanged = context.State.LastDecisionTargetGuid
            != target->GetGUID();
        bool const firstEngagement = !context.State.WasInCombat;
        if (!targetChanged && !firstEngagement)
            return BotActionArbitration::Outcome::NotApplicable(
                "omnotron_route_observation_already_recorded");

        float const targetHealthPct = UnitHealthPct(target);
        RecordRouteProgress(context.State, context.Bot, target,
            "route_target_combat_progress", targetHealthPct, targetHealthPct,
            0, 20);
        Party().ValidationRouteObservedEngagement = true;
        std::string raw = BuildRawJson(context.Bot, target);
        std::string semantic = BuildSemanticJson(context.Bot, target,
            "adaptive_omnotron", &context.Power, context.Stage,
            context.ChosenActivity.Activity);
        RecordEvent(context.State, context.Bot, "validation_target_priority",
            target, "native_combat_observed", raw.c_str(), semantic.c_str(),
            context.Bot->GetExactDist(target),
            Cohort().Config.ValidationRouteTargetEntry, 0);
        RecordEvent(context.State, context.Bot, "boss_action", target,
            "native_combat_observed", raw.c_str(), semantic.c_str(),
            context.Bot->GetExactDist(target),
            Cohort().Config.ValidationRouteTargetEntry, 0);
        if (firstEngagement)
            RecordEvent(context.State, context.Bot, "boss_started", target,
                "native_combat_observed", raw.c_str(), semantic.c_str(),
                context.Bot->GetExactDist(target),
                Cohort().Config.ValidationRouteTargetEntry, 0);
        context.State.WasInCombat = true;
        return BotActionArbitration::Outcome::NotApplicable(
            "adaptive_omnotron_route_observation_recorded");
    };

    BotActionArbitration::Candidate observation;
    observation.Key = "world.validation_route_omnotron_observation";
    observation.Source = "validation_route_observer";
    observation.ActionPriority = BotActionArbitration::Priority::Mechanic;
    observation.UtilityScore = 0.0f;
    observation.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::None);
    observation.Attempt = observe;
    context.State.DecisionKernel.Submit(std::move(observation));
}
