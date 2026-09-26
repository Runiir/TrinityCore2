#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"

#include "CharmInfo.h"
#include "MotionMaster.h"
#include "MoveSpline.h"
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

    // A bot leading warriors with no lawful leg (a running walk that would now
    // take them deeper into Nefarian's front, or no leg at all): hold it. The
    // hold is renewed every decision while the plan asks for it:
    // - the autonomous generator of the active slot (a native chase or point
    //   path) is cleared and the spline stopped, as a client releasing its
    //   keys; a controlled effect (fear, knockback, jump) is left alone;
    // - a Hazard movement lease at the bot's own position makes the movement
    //   executor preserve it against every lower lane, so combat range
    //   recovery (MoveBotToProfileRange, CombatRange/Combat) cannot move the
    //   bot in the same tick or before the lease expires.
    if (context.AdaptiveNefarianMovementHold == BotEncounter::Nefarian::WarriorStopHold)
    {
        BotActionArbitration::Candidate stop;
        stop.Key = "adaptive_nefarian:" + std::string(BotEncounter::Nefarian::WarriorStopHold);
        stop.Source = "adaptive_nefarian";
        stop.ActionPriority = BotActionArbitration::Priority::Survival;
        stop.UtilityScore = 480.0f;
        stop.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::Movement);
        stop.ExpiresAtMs = context.DecisionNowMs + 1000;
        stop.Attempt = [this, &context]()
        {
            Player* bot = context.Bot;
            MotionMaster* motion = bot->GetMotionMaster();
            if (motion->GetMotionSlot(MOTION_SLOT_CONTROLLED))
                return BotActionArbitration::Outcome::Retryable(
                    "nefarian_warrior_path_stop_controlled_motion");
            // As SettleRetainedMagmawFormation retires a native path.
            if (!bot->movespline->Finalized())
                bot->StopMoving();
            motion->Clear(MOTION_SLOT_ACTIVE);
            motion->MoveIdle();
            BotWorldMovement::Intent hold;
            hold.X = bot->GetPositionX();
            hold.Y = bot->GetPositionY();
            hold.Z = bot->GetPositionZ();
            hold.Owner = BotMovementArbitration::Owner::Hazard;
            hold.Priority = BotMovementArbitration::Priority::Hazard;
            BotMovementArbitration::Apply(context.State.MovementLease,
                BuildMovementRequest(bot, hold, context.DecisionNowMs));
            context.State.ActivePathValid = false;
            context.State.IsMoving = false;
            context.Situation = "adaptive_nefarian";
            context.Action = "nefarian_warrior_path_stop";
            context.State.LastDecisionHandler = "adaptive_nefarian";
            return BotActionArbitration::Outcome::Committed("nefarian_warrior_path_held");
        };
        context.State.DecisionKernel.Submit(std::move(stop));
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
