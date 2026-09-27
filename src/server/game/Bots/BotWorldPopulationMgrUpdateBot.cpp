#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotNativeLifeEvents.h"
#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"
#include "Bots/BotWorldPopulationMgrScopeGuard.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Player.h"

void BotWorldPopulationMgr::UpdateBot(WorldBotState& state, uint32 diff)
{
    Player* bot = GetBot(state);
    if (!bot)
        return;

    // Native life edges on entry and on exit (BotNativeLifeEvents.h): a death
    // is seen before this update can release it, an in-update revive before
    // the next map update can kill it again.  Scoped to this cohort run.
    uint32 const lifeGuid = bot->GetGUID().GetCounter();
    BotNativeLifeEvents::Scope const lifeScope = BotNativeLifeEvents::LifecycleScope(Cohort().Id, Cohort().AttemptId);
    BotNativeLifeEvents::Observe(lifeGuid, lifeScope, bot->IsAlive(),
        BotWorldPopulationMgrSpellSemantics::NowMs());
    BotWorldPopulationMgrInternal::ReconcileOnScopeExit lifeEdgeObserve{
        [this, &state, lifeGuid, lifeScope]()
        {
            if (Player* current = GetBot(state))
                BotNativeLifeEvents::Observe(lifeGuid, lifeScope, current->IsAlive(),
                    BotWorldPopulationMgrSpellSemantics::NowMs());
        }};

    ObserveChainwielderOwnerCheckpointBeforeUpdate(state, bot);

    if (Cohort().Config.ValidationRouteEnable)
        BotWorldMovement::ObserveReceiptTaggedMovementProgress(bot);

    ObserveNativePathCheckpointBeforeUpdate(state, bot);

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
    MaybeInjectChainwielderOwnerCheckpointAfterUpdate(state, bot);
}
