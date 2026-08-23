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
        bool const validationRouteWait =
            context.State.LastDecisionHandler == "validation_route"
            && context.Action == "validation_route_patrol_wait_for_safe_phase";
        if (validationRouteWait)
        {
            // Preserve the route contract's intentional hold after lower
            // priority adapters have had a chance to find independent work.
            context.State.LastRecoveryMode = "validation_route_wait";
            context.State.LastRecoveryResult = context.Action;
        }
        else
        {
            context.Situation = "decision_kernel_retry";
            context.Action = "wait_for_candidate_backoff";
            context.State.LastDecisionHandler = "decision_kernel";
            context.State.LastRecoveryMode = "candidate_backoff";
            context.State.LastRecoveryResult = "no_candidate_committed";
        }
    }
    return true;
}
