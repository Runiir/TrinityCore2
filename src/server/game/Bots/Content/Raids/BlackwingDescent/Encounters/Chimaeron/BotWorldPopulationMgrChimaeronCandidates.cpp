#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotAdaptiveChimaeronStrategy.h"

#include "CharmInfo.h"
#include "Creature.h"
#include "Pet.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <optional>
#include <string>
#include <utility>
#include <variant>

using BotWorldPopulationMgrNativeHelpers::IsNativeCombatObserved;
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

// Kernel submission of the adaptive Chimaeron strategy's non-movement
// outputs. The strategy (BotAdaptiveChimaeronStrategy.h) decides; this file
// only turns its typed proposals into arbitration candidates.

// Native casts: taunt exchange, outage raid cooldowns, Mortality absorbs and
// the burn Bloodlust. The executor revalidates the spell, cooldown and
// target; a rejection is retryable and never manufactures an effect.
// Offense suppression: the sleeping boss before the wake and the burn window.
void BotWorldPopulationMgr::SubmitAdaptiveChimaeronCandidates(BotUpdateContext& context)
{
    if (context.AdaptiveChimaeronAction
        && context.AdaptiveChimaeronAction->ExpiresAtMs > context.DecisionNowMs)
    {
        BotNativeAction::Candidate const& proposal = *context.AdaptiveChimaeronAction;
        BotActionArbitration::Candidate action;
        action.Key = proposal.Id.Key();
        action.Source = proposal.Id.Strategy;
        action.ActionPriority = proposal.ActionPriority;
        action.UtilityScore = proposal.Utility;
        action.RequiredResources = proposal.Resources();
        action.ExpiresAtMs = proposal.ExpiresAtMs;
        BotNativeAction::Intent intent = proposal.Action;
        // The lust is cast only from this bot's own spell book (as Maloriak's
        // raid haste does): the shaman's faction variant it knows, and never a
        // Time Warp the mage owner was not taught. An owner that knows no lust
        // spell skips it with a typed reason (resource-free, so nothing else
        // is displaced) instead of submitting a cast the executor refuses.
        bool lustUnknown = false;
        if (auto* cast = std::get_if<BotNativeAction::CastSpell>(&intent);
            cast && BotEncounter::Chimaeron::IsLustSpell(cast->SpellId))
        {
            std::optional<uint32> const known = BotEncounter::Chimaeron::KnownLustSpell(
                cast->SpellId,
                context.Bot->HasSpell(BotEncounter::Chimaeron::TimeWarpSpell),
                context.Bot->HasSpell(BotEncounter::Chimaeron::BloodlustSpell),
                context.Bot->HasSpell(BotEncounter::Chimaeron::HeroismSpell));
            if (known)
                cast->SpellId = *known;
            else
                lustUnknown = true;
        }
        // Healer mana cooldowns: the snapshot carries no mana, so the healer
        // checks its own mana line, spell book and cooldown here and skips a
        // cast it does not need or cannot make (typed, resource-free).
        bool manaCooldownSkipped = false;
        if (auto* cast = std::get_if<BotNativeAction::CastSpell>(&intent);
            cast && BotEncounter::Chimaeron::IsManaCooldownSpell(cast->SpellId))
        {
            uint32 const maxMana = context.Bot->GetMaxPower(POWER_MANA);
            float const manaPct = maxMana
                ? 100.0f * float(context.Bot->GetPower(POWER_MANA)) / float(maxMana) : 100.0f;
            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(cast->SpellId);
            manaCooldownSkipped = !BotEncounter::Chimaeron::ManaCooldownWanted(
                    cast->SpellId, manaPct)
                || !context.Bot->HasSpell(cast->SpellId) || !spellInfo
                || !context.Bot->GetSpellHistory()->IsReady(spellInfo);
        }
        if (lustUnknown || manaCooldownSkipped)
        {
            char const* const reason = lustUnknown
                ? BotEncounter::Chimaeron::LustSpellUnknownReason
                : BotEncounter::Chimaeron::ManaCooldownNotNeededReason;
            action.RequiredResources = BotActionArbitration::Uses(
                BotActionArbitration::Resource::None);
            action.Attempt = [reason]()
            {
                return BotActionArbitration::Outcome::NotApplicable(reason);
            };
        }
        else
            action.Attempt = [this, &context, intent = std::move(intent),
                mechanic = proposal.Id.Mechanic]()
            {
                BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                    context.State, context.Bot, intent,
                    BotMovementArbitration::Owner::Mechanic,
                    BotMovementArbitration::Priority::Mechanic);
                if (outcome.Result == BotActionArbitration::Disposition::Committed)
                {
                    context.Situation = "adaptive_chimaeron";
                    context.Action = mechanic;
                    context.State.LastDecisionHandler = "adaptive_chimaeron";
                }
                return outcome;
            };
        context.State.DecisionKernel.Submit(std::move(action));
    }

    if (!context.AdaptiveChimaeronSuppressOffense)
        return;

    std::string const suppressReason = context.AdaptiveChimaeronSuppressReason.empty()
        ? std::string("chimaeron_offense_suppressed")
        : context.AdaptiveChimaeronSuppressReason;
    BotActionArbitration::Candidate suppress;
    suppress.Key = "adaptive_chimaeron:" + suppressReason + ":"
        + std::to_string(Party().ValidationRouteGeneration);
    suppress.Source = "adaptive_chimaeron";
    suppress.ActionPriority = BotActionArbitration::Priority::Mechanic;
    suppress.UtilityScore = 100.0f;
    suppress.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::Pet);
    suppress.Attempt = [this, &context, suppressReason]()
    {
        std::string const intentReason = "adaptive_chimaeron_" + suppressReason;
        bool const submitted = SubmitMeleeAutoAttackIntent(context.State,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Mechanic,
            BotActionArbitration::Priority::Mechanic, intentReason.c_str());
        if (Pet* pet = context.Bot->GetPet(); pet && pet->GetCharmInfo())
            ExecuteNativeActionIntent(context.State, context.Bot,
                BotNativeAction::PetCommand{ pet->GetGUID(), context.Bot->GetGUID(),
                    COMMAND_FOLLOW },
                BotMovementArbitration::Owner::Mechanic,
                BotMovementArbitration::Priority::Mechanic);
        context.State.TargetGuid.Clear();
        context.Target = nullptr;
        context.Situation = "adaptive_chimaeron";
        context.Action = suppressReason;
        context.State.LastDecisionHandler = "adaptive_chimaeron";
        return submitted
            ? BotActionArbitration::Outcome::Committed("melee_autoattack_suppression_submitted")
            : BotActionArbitration::Outcome::Retryable("melee_autoattack_suppression_rejected");
    };
    context.State.DecisionKernel.Submit(std::move(suppress));
}

// The adaptive owner replaces the route adapter on the encounter node, so it
// must also carry the route's engagement edge (as Magmaw's observer does).
// Without RememberValidationRouteBossEngagement the native boss death is
// rejected and the route never records the clear. Observation only: it never
// changes target, focus or movement.
void BotWorldPopulationMgr::SubmitAdaptiveChimaeronRouteObservation(BotUpdateContext& context)
{
    auto observe = [this, &context]() -> BotActionArbitration::Outcome
    {
        if (!context.AdaptiveChimaeronOwnsNode
            || Cohort().Config.ValidationRouteKind != "boss"
            || Cohort().Config.ValidationRouteNodeId
                != BotEncounter::Chimaeron::EncounterNode)
            return BotActionArbitration::Outcome::NotApplicable(
                "chimaeron_route_observation_not_owned");

        Unit* target = context.Target;
        Creature const* creature = target ? target->ToCreature() : nullptr;
        if (!target || !creature || !target->IsAlive()
            || creature->GetEntry() != BotEncounter::Chimaeron::BossEntry
            || creature->GetEntry() != Cohort().Config.ValidationRouteTargetEntry
            || !context.Bot->IsValidAttackTarget(target)
            || !IsNativeCombatObserved(context.Bot, target))
            return BotActionArbitration::Outcome::NotApplicable(
                "chimaeron_route_observation_wait_for_native_combat");

        RememberValidationRouteBossEngagement(creature);

        bool const targetChanged = context.State.LastDecisionTargetGuid != target->GetGUID();
        bool const firstEngagement = !context.State.WasInCombat;
        if (!targetChanged && !firstEngagement)
            return BotActionArbitration::Outcome::NotApplicable(
                "chimaeron_route_observation_already_recorded");

        float const targetHealthPct = UnitHealthPct(target);
        RecordRouteProgress(context.State, context.Bot, target,
            "route_target_combat_progress", targetHealthPct, targetHealthPct, 0, 20);
        Party().ValidationRouteObservedEngagement = true;
        std::string raw = BuildRawJson(context.Bot, target);
        std::string semantic = BuildSemanticJson(context.Bot, target, "adaptive_chimaeron",
            &context.Power, context.Stage, context.ChosenActivity.Activity);
        RecordEvent(context.State, context.Bot, "validation_target_priority", target,
            "native_combat_observed", raw.c_str(), semantic.c_str(),
            context.Bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, 0);
        RecordEvent(context.State, context.Bot, "boss_action", target,
            "native_combat_observed", raw.c_str(), semantic.c_str(),
            context.Bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, 0);
        if (firstEngagement)
            RecordEvent(context.State, context.Bot, "boss_started", target,
                "native_combat_observed", raw.c_str(), semantic.c_str(),
                context.Bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, 0);
        context.State.WasInCombat = true;
        return BotActionArbitration::Outcome::NotApplicable(
            "adaptive_chimaeron_route_observation_recorded");
    };

    BotActionArbitration::Candidate observation;
    observation.Key = "world.validation_route_chimaeron_observation";
    observation.Source = "validation_route_observer";
    observation.ActionPriority = BotActionArbitration::Priority::Mechanic;
    observation.UtilityScore = 0.0f;
    observation.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::None);
    observation.Attempt = std::move(observe);
    context.State.DecisionKernel.Submit(std::move(observation));
}
