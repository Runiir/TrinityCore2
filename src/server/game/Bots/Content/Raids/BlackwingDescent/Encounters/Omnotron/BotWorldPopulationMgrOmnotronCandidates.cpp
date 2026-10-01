#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronInterruptLedger.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronOffenseAuthority.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronPetShieldGuard.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronTankSurvival.h"

#include "CharmInfo.h"
#include "Creature.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "WorldPacket.h"
#include "WorldSession.h"

#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

// Native submission of the adaptive Omnotron plan (BotAdaptiveOmnotronStrategy.h).
// The strategy chooses; these candidates only submit ordinary player actions
// (movement, autoattack stop, pet follow, interrupt, taunt, dispel) that the
// core validates again. Attempts run after this function returns, so they
// capture only `this`, the live context and values.
//
// Blocks moved from BotWorldPopulationMgrUpdateBotKernelCandidates.cpp, with
// three changes: the suppress candidate reports the plan's suppress reason as
// its Action; the interrupt key carries the Arcane Annihilator cast ordinal
// (one candidate identity per cast) and the attempt tries each known
// interrupt until one is submitted; interrupts and taunts on a shielded
// construct run under a SingleCastAllowance.
using BotWorldPopulationMgrNativeHelpers::HasPowerForSpell;
using BotWorldPopulationMgrNativeHelpers::IsNativeCombatObserved;
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

namespace
{
// The owner's Felguard whirling (Felstorm aura) beside a shielded construct
// (BotOmnotronPetShieldGuard.h), or an empty GUID.
ObjectGuid OmnotronFelstormBesideShield(Player* bot,
    BotEncounter::Omnotron::EncounterFacts const& facts)
{
    namespace O = BotEncounter::Omnotron;
    Pet* pet = bot->GetPet();
    if (!pet || !pet->IsAlive() || pet->GetEntry() != O::FelguardEntry
        || !pet->HasAura(O::FelstormAura) || !bot->GetSession()
        || !O::FelstormReachesShieldedConstruct(facts,
            { pet->GetPositionX(), pet->GetPositionY(), pet->GetPositionZ() }))
        return ObjectGuid::Empty;
    return pet->GetGUID();
}

// Cancels the pet's Felstorm aura with the client's pet cancel-aura request
// (CMSG_PET_CANCEL_AURA), as a player right-clicks the pet buff. Returns
// whether the aura is gone afterwards.
bool CancelOmnotronPetFelstorm(Player* bot, ObjectGuid petGuid)
{
    Pet* live = bot->GetPet();
    if (!live || live->GetGUID() != petGuid
        || !live->HasAura(BotEncounter::Omnotron::FelstormAura))
        return true;
    if (!bot->GetSession())
        return false;
    WorldPacket request(CMSG_PET_CANCEL_AURA, 8 + 4);
    request << petGuid;
    request << uint32(BotEncounter::Omnotron::FelstormAura);
    bot->GetSession()->HandlePetCancelAuraOpcode(request);
    return !live->HasAura(BotEncounter::Omnotron::FelstormAura);
}
}

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

    // Review r4 finding 6: shield suppression and the Felstorm cancel both
    // need the Pet lane, and suppression (utility 100) commits first. A pet
    // whirling beside a shielded construct is therefore cancelled by
    // whichever of the two runs: suppression cancels it itself, and the
    // standalone cancel below covers a bot that is not suppressing.
    namespace O = BotEncounter::Omnotron;
    std::optional<O::EncounterFacts> ownedFacts;
    if (context.AdaptiveOmnotronOwnsNode && Cohort().EncounterSnapshot)
        ownedFacts.emplace(O::Observe(*Cohort().EncounterSnapshot));
    ObjectGuid const felstormPet = ownedFacts
        ? OmnotronFelstormBesideShield(context.Bot, *ownedFacts) : ObjectGuid::Empty;

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
        suppress.Attempt = [this, &context, felstormPet]()
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
            // A follow command does not end a running whirl.
            if (!felstormPet.IsEmpty())
                CancelOmnotronPetFelstorm(context.Bot, felstormPet);
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
            uint32 castSpellId = 0;
            {
                // Arcanotron under Power Conversion is restricted for this
                // bot; widen the restriction for this one interrupt only.
                std::optional<BotEncounter::Omnotron::SingleCastAllowance> allowance;
                if (context.AdaptiveOmnotronOwnsNode)
                    allowance.emplace(context.Bot->GetGUID().GetRawValue(),
                        BotEncounter::Omnotron::BuildOffenseRestriction(
                            context.AdaptiveOmnotronOffenseAllowedGuids),
                        caster->GetGUID());
                // Try every known interrupt: a Feral druid knows both Skull
                // Bash forms but only the one for its current form can be cast.
                for (uint32 spellId : { 6552u, 1766u, 2139u, 57994u,
                        96231u, 47528u, 80964u, 80965u, 15487u, 34490u })
                    if (context.Bot->HasSpell(spellId)
                        && TryCastCombatSpell(context.Bot, caster, spellId))
                    {
                        castSpellId = spellId;
                        break;
                    }
            }
            if (!castSpellId)
                return BotActionArbitration::Outcome::Retryable(
                    "native_interrupt_retryable");
            // The rotation passes over this bot until its interrupt is back.
            // The cooldown is the bot's own native remaining cooldown right
            // after the cast (spell history), which already includes talent
            // and glyph changes such as Reverberation on Wind Shear; the
            // instant interrupts start it inside the cast call.
            if (Cohort().EncounterSnapshot)
            {
                SpellInfo const* castInfo = sSpellMgr->GetSpellInfo(castSpellId);
                uint32 const remainingCooldownMs = castInfo
                    ? context.Bot->GetSpellHistory()->GetRemainingCooldown(castInfo)
                    : 0;
                BotEncounter::Omnotron::InterruptLedger::RecordUse(
                    *Cohort().EncounterSnapshot, context.Bot->GetGUID(),
                    context.DecisionNowMs, remainingCooldownMs);
            }
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
            bool submitted = false;
            {
                // A shielded construct is restricted for this bot; widen the
                // restriction for this one taunt only.
                std::optional<BotEncounter::Omnotron::SingleCastAllowance> allowance;
                if (context.AdaptiveOmnotronOwnsNode)
                    allowance.emplace(context.Bot->GetGUID().GetRawValue(),
                        BotEncounter::Omnotron::BuildOffenseRestriction(
                            context.AdaptiveOmnotronOffenseAllowedGuids),
                        golem->GetGUID());
                submitted = TryCastCombatSpell(context.Bot, golem, tauntSpell);
            }
            if (!submitted)
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

    if (!ownedFacts)
        return;
    BotEncounter::Blackboard const& board = *Cohort().EncounterSnapshot;
    O::EncounterFacts const& facts = *ownedFacts;

    // A running Felstorm beside a shielded construct (BotOmnotronPetShieldGuard.h):
    // the owner cancels the pet's aura with the client's pet cancel-aura
    // request, as a player right-clicks the pet buff.
    if (!felstormPet.IsEmpty())
    {
        BotActionArbitration::Candidate cancel;
        cancel.Key = "adaptive_omnotron:felstorm_cancel:"
            + std::to_string(felstormPet.GetRawValue());
        cancel.Source = "adaptive_omnotron";
        cancel.ActionPriority = BotActionArbitration::Priority::Mechanic;
        cancel.UtilityScore = 95.0f;
        cancel.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::Pet);
        cancel.Attempt = [&context, petGuid = felstormPet]()
        {
            Pet* live = context.Bot->GetPet();
            if (!live || live->GetGUID() != petGuid || !live->HasAura(
                    BotEncounter::Omnotron::FelstormAura))
                return BotActionArbitration::Outcome::NotApplicable(
                    "felstorm_already_ended");
            bool const cancelled = CancelOmnotronPetFelstorm(context.Bot, petGuid);
            context.Situation = "adaptive_omnotron";
            context.Action = "felstorm_cancel_beside_shield";
            context.State.LastDecisionHandler = "adaptive_omnotron";
            return cancelled
                ? BotActionArbitration::Outcome::Submitted("felstorm_cancel_submitted")
                : BotActionArbitration::Outcome::Retryable("felstorm_cancel_rejected");
        };
        context.State.DecisionKernel.Submit(std::move(cancel));
    }

    // Tank survival (BotOmnotronTankSurvival.h): the first decision this bot
    // can cast now, judged by its own spell book, native cooldown, power and
    // movement (FirstSubmittableSurvival). The cast is an ordinary native cast
    // of that spell on the decision's target. Recomputed from the shared
    // snapshot; the duty plan's ledgers are not touched here. While this bot
    // is the assigned Arcane Annihilator interrupter only urgent survival is
    // submitted, so nonurgent maintenance never takes the interrupt's lanes.
    BotEncounter::ActorSnapshot const* self = board.FindActor(context.Bot->GetGUID());
    if (!self)
        return;
    bool const moving = context.Bot->isMoving();
    bool const assignedInterrupt = !context.AdaptiveOmnotronInterruptTargetGuid.IsEmpty();
    std::vector<O::SurvivalDecision> const decisions
        = O::DecideSurvivalActions(board, facts, *self, moving);
    O::SurvivalDecision const* chosen = O::FirstSubmittableSurvival(decisions,
        assignedInterrupt, [&context, moving](O::SurvivalDecision const& decision)
        {
            SpellInfo const* info = sSpellMgr->GetSpellInfo(decision.SpellId);
            if (!info || !context.Bot->HasActiveSpell(decision.SpellId)
                || !context.Bot->GetSpellHistory()->IsReady(info)
                || !HasPowerForSpell(context.Bot, info)
                || (moving && info->CalcCastTime() > 0))
                return false;
            Unit* target = decision.Target == context.Bot->GetGUID() ? context.Bot
                : ObjectAccessor::GetUnit(*context.Bot, decision.Target);
            return target && target->IsAlive();
        });
    if (!chosen)
        return;
    O::SurvivalDecision const decision = *chosen;
    bool const onSelf = decision.Target == context.Bot->GetGUID();
    BotNativeAction::Intent intent = BotNativeAction::CastSpell{
        onSelf ? ObjectGuid::Empty : decision.Target, decision.SpellId };
    BotActionArbitration::Candidate survival;
    survival.Key = "adaptive_omnotron:" + std::string(decision.Reason) + ":"
        + std::to_string(decision.Target.GetRawValue());
    survival.Source = "adaptive_omnotron";
    survival.ActionPriority = decision.Urgent
        ? BotActionArbitration::Priority::Survival
        : BotActionArbitration::Priority::Mechanic;
    survival.UtilityScore = decision.Urgent ? 150.0f : 140.0f;
    survival.RequiredResources = BotNativeAction::RequiredResources(intent);
    survival.Attempt = [this, &context, intent = std::move(intent),
        reason = std::string(decision.Reason)]()
    {
        BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
            context.State, context.Bot, intent,
            BotMovementArbitration::Owner::Mechanic,
            BotMovementArbitration::Priority::Mechanic);
        if (outcome.Result == BotActionArbitration::Disposition::Committed)
        {
            context.Situation = "adaptive_omnotron";
            context.Action = reason;
            context.State.LastDecisionHandler = "adaptive_omnotron";
        }
        return outcome;
    };
    context.State.DecisionKernel.Submit(std::move(survival));
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
        BotEncounter::Omnotron::ApplyOffenseRestriction(
            context.Bot->GetGUID().GetRawValue(),
            BotEncounter::Omnotron::BuildOffenseRestriction(
                context.AdaptiveOmnotronOffenseAllowedGuids));

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
