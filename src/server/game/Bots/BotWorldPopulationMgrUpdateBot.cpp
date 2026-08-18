#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrScopeGuard.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"

void BotWorldPopulationMgr::UpdateBot(WorldBotState& state, uint32 diff)
{
    Player* bot = GetBot(state);
    if (!bot)
        return;

    BeginMeleeAutoAttackDecision(state, bot);
    BotWorldPopulationMgrInternal::ReconcileOnScopeExit meleeAutoAttackReconcile{
        [this, &state, bot]()
        {
            ResolveAndReconcileMeleeAutoAttack(state, bot);
        }};

    BotUpdateContext context(*this, state, bot, diff);
    if (!PrepareBotUpdate(context))
        return;
    if (!RunBotDecisionKernel(context))
        return;
    FinalizeBotUpdate(context);
}
