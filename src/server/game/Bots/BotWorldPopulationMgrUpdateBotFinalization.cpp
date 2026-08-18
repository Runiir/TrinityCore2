#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "Entities/Object/Position.h"
#include "Player.h"
#include "Random.h"

#include <cmath>
#include <string>

using BotWorldPopulationMgrSpellSemantics::NowMs;

void BotWorldPopulationMgr::FinalizeBotUpdate(BotUpdateContext& context)
{
    uint64 nowMs = NowMs();
    bool loopRecoveryAvailable = nowMs >= context.State.LoopRecoveryCooldownUntilMs && !context.Bot->IsInCombat() && !Cohort().Config.ValidationRouteEnable;
    bool repeatedDecisionLoop = context.State.LastDecisionFingerprintRepeatCount >= 5 && context.State.ConsecutiveSameDecisionCount >= 3;
    bool idleLoop = context.State.IdleDecisionRepeatCount >= 4 && context.State.LastDecisionDistanceMoved < 1.0f;
    bool targetChurnLoop = context.State.TargetChurnCount >= 4;
    if (loopRecoveryAvailable && (repeatedDecisionLoop || idleLoop || targetChurnLoop))
    {
        char const* reason = repeatedDecisionLoop ? "repeated_decision_loop" : (idleLoop ? "idle_loop" : "target_churn_loop");
        context.State.LastLoopGuardrailAction = "guardrail_repath";
        context.State.LastLoopGuardrailReason = reason;
        context.State.LastLoopGuardrailMs = nowMs;
        context.State.LoopRecoveryCooldownUntilMs = nowMs + 15000;
        ++context.State.LoopGuardrailCount;
        context.State.TargetGuid.Clear();
        context.State.QuestWork.SelectedTargetGuid.Clear();
        SubmitMeleeAutoAttackIntent(context.State,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Recovery,
            BotActionArbitration::Priority::Survival,
            "loop_guardrail_repath");
        Position pos = context.Bot->GetFirstCollisionPosition(6.0f, frand(0.0f, 2.0f * float(M_PI)));
        MoveBotToPoint(context.State, context.Bot, pos.GetPositionX(), pos.GetPositionY(), pos.GetPositionZ());
        context.Situation = "runtime_recovery";
        context.Action = "guardrail_repath";
        context.Target = nullptr;
        context.State.LastDecisionHandler = "runtime_recovery";
        std::string guardRaw = BuildRawJson(context.Bot, nullptr);
        std::string guardSemantic = BuildSemanticJson(context.Bot, nullptr, context.Situation.c_str(), &context.Power, context.Stage, context.ChosenActivity.Activity);
        RecordEvent(context.State, context.Bot, "loop_guardrail_triggered", nullptr, reason, guardRaw.c_str(), guardSemantic.c_str(), float(context.State.LoopGuardrailCount), context.State.LastDecisionFingerprintRepeatCount);
    }

    context.Power = BotLongTermProgressionBrain::CalculateRolePower(context.Bot);
    std::string raw = BuildRawJson(context.Bot, context.Target);
    std::string semantic = BuildSemanticJson(context.Bot, context.Target, context.Situation.c_str(), &context.Power, context.Stage, context.ChosenActivity.Activity);
    bool validationRouteFailure = context.Action == "validation_route_target_blocked" || context.Action == "validation_route_wrong_map";
    bool runtimeRecovery = context.Action == "guardrail_repath";
    bool failure = context.QuestAction.Failure || context.TrashAction.Failure
        || context.BossAction.Failure || validationRouteFailure;
    bool rare = context.QuestAction.Rare || context.TrashAction.Rare
        || context.BossAction.Rare || validationRouteFailure || runtimeRecovery;
    RecordDecision(context.State, context.Bot, context.Situation.c_str(), context.Action.c_str(), context.Target, raw.c_str(), semantic.c_str(), context.ActivityScores, context.ChosenActivity, context.Power, failure, rare);
    if (context.Action == "validation_route_complete")
        MaybeAdvanceValidationRouteManifest();
}
