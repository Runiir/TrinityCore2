#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"

#include "CharmInfo.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

#include <string>
#include <utility>

// Kernel submission of the adaptive Nefarian's End strategy's outputs. The
// strategy (BotAdaptiveNefarianStrategy.h) decides from the encounter
// snapshot and the bot's native facts; this file only turns its typed
// proposals into arbitration candidates:
// - the platform/phase movement leg (a transport-surface Walk, or a native
//   point move on the ground), at hazard priority;
// - exact per-spec casts (Blast Nova interrupts, taunts, bone-warrior
//   controls); the native executor keeps every rule (known spell, cooldown,
//   range, line of sight) and a rejection is retryable, never an effect;
// - offense suppression (before the pull, the airborne dragon's tank, the
//   platform without a prototype, the landing);
// - the typed capability blocker or movement hold of this decision, recorded
//   as a not-applicable reason in the decision trace.
void BotWorldPopulationMgr::SubmitAdaptiveNefarianCandidates(BotUpdateContext& context)
{
    if (context.AdaptiveNefarianMovement
        && context.AdaptiveNefarianMovement->ExpiresAtMs > context.DecisionNowMs)
    {
        BotNativeAction::Candidate const& proposal = *context.AdaptiveNefarianMovement;
        BotActionArbitration::Candidate movement;
        movement.Key = proposal.Id.Key();
        movement.Source = proposal.Id.Strategy;
        movement.ActionPriority = proposal.ActionPriority;
        movement.UtilityScore = proposal.Utility;
        movement.RequiredResources = proposal.Resources();
        movement.ExpiresAtMs = proposal.ExpiresAtMs;
        movement.Attempt = [this, &context,
            intent = BotNativeAction::WithMovementReason(proposal.Action,
                proposal.Id.Mechanic)]()
        {
            BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                context.State, context.Bot, intent, BotMovementArbitration::Owner::Hazard,
                BotMovementArbitration::Priority::Hazard);
            if (outcome.Result == BotActionArbitration::Disposition::Committed)
            {
                context.Situation = "adaptive_nefarian";
                context.Action = "nefarian_mechanic_movement";
                context.State.LastDecisionHandler = "adaptive_nefarian";
            }
            return outcome;
        };
        context.State.DecisionKernel.Submit(std::move(movement));
    }

    for (BotNativeAction::Candidate const& proposal : context.AdaptiveNefarianActions)
    {
        if (proposal.ExpiresAtMs <= context.DecisionNowMs)
            continue;
        BotActionArbitration::Candidate action;
        action.Key = proposal.Id.Key();
        action.Source = proposal.Id.Strategy;
        action.ActionPriority = proposal.ActionPriority;
        action.UtilityScore = proposal.Utility;
        action.RequiredResources = proposal.Resources();
        action.ExpiresAtMs = proposal.ExpiresAtMs;
        action.Attempt = [this, &context, intent = proposal.Action,
            mechanic = proposal.Id.Mechanic]()
        {
            BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                context.State, context.Bot, intent, BotMovementArbitration::Owner::Mechanic,
                BotMovementArbitration::Priority::Mechanic);
            if (outcome.Result == BotActionArbitration::Disposition::Committed)
            {
                context.Situation = "adaptive_nefarian";
                context.Action = mechanic;
                context.State.LastDecisionHandler = "adaptive_nefarian";
            }
            return outcome;
        };
        context.State.DecisionKernel.Submit(std::move(action));
    }

    if (context.AdaptiveNefarianSuppressOffense)
    {
        std::string const suppressReason = context.AdaptiveNefarianSuppressReason.empty()
            ? std::string("nefarian_offense_suppressed")
            : context.AdaptiveNefarianSuppressReason;
        BotActionArbitration::Candidate suppress;
        suppress.Key = "adaptive_nefarian:" + suppressReason + ":"
            + std::to_string(Party().ValidationRouteGeneration);
        suppress.Source = "adaptive_nefarian";
        suppress.ActionPriority = BotActionArbitration::Priority::Mechanic;
        suppress.UtilityScore = 100.0f;
        suppress.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::Pet);
        suppress.Attempt = [this, &context, suppressReason]()
        {
            std::string const intentReason = "adaptive_nefarian_" + suppressReason;
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
            context.Situation = "adaptive_nefarian";
            context.Action = suppressReason;
            context.State.LastDecisionHandler = "adaptive_nefarian";
            return submitted
                ? BotActionArbitration::Outcome::Committed("melee_autoattack_suppression_submitted")
                : BotActionArbitration::Outcome::Retryable("melee_autoattack_suppression_rejected");
        };
        context.State.DecisionKernel.Submit(std::move(suppress));
    }

    // Claims no resource and never displaces a real action; its only effect
    // is the reason in the decision trace.
    if (!context.AdaptiveNefarianBlocked.empty()
        || !context.AdaptiveNefarianMovementHold.empty())
    {
        std::string const reason = !context.AdaptiveNefarianBlocked.empty()
            ? context.AdaptiveNefarianBlocked
            : context.AdaptiveNefarianMovementHold;
        BotActionArbitration::Candidate hold;
        hold.Key = "adaptive_nefarian:hold:" + reason;
        hold.Source = "adaptive_nefarian";
        hold.ActionPriority = BotActionArbitration::Priority::Idle;
        hold.UtilityScore = 0.0f;
        hold.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::None);
        hold.Attempt = [reason]()
        {
            return BotActionArbitration::Outcome::NotApplicable(reason);
        };
        context.State.DecisionKernel.Submit(std::move(hold));
    }
}
