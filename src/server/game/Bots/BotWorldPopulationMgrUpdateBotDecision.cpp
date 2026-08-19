#include "Bots/BotWorldPopulationMgrUpdateContext.h"

bool BotWorldPopulationMgr::RunBotDecisionKernel(BotUpdateContext& context)
{
    if (!context.ValidationKernelOwnsTick)
        return RunLegacyBotDecision(context);

    PrepareValidationKernel(context);
    SubmitAdaptiveKernelCandidates(context);
    SubmitValidationKernelFallbackCandidates(context);

    BotActionArbitration::Resolution const& resolution =
        context.State.DecisionKernel.Resolve();
    context.State.LastDecisionKernelJson =
        context.State.DecisionKernel.LastResolutionJson();
    if (!resolution.AnyCommitted)
    {
        context.Situation = "decision_kernel_retry";
        context.Action = "wait_for_candidate_backoff";
        context.State.LastDecisionHandler = "decision_kernel";
        context.State.LastRecoveryMode = "candidate_backoff";
        context.State.LastRecoveryResult = "no_candidate_committed";
    }
    return true;
}
