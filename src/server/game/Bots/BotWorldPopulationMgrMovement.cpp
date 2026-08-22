#include "Bots/BotWorldPopulationMgr.h"

#include "Player.h"

bool BotWorldPopulationMgr::MoveBotToPoint(
    WorldBotState& state, Player* bot, float x, float y, float z,
    bool terminalOnFailure, BotMovementArbitration::Owner movementOwner,
    BotMovementArbitration::Priority movementPriority, Unit* dynamicTarget,
    float dynamicTargetRange)
{
    if (!bot)
        return false;

    // Legacy callers did not carry an explicit movement intent.  Keep this
    // compatibility adapter small and preserve their owner defaults; the
    // independent movement executor receives only the resulting intent.
    if (movementOwner == BotMovementArbitration::Owner::None)
    {
        if (bot->IsInCombat())
        {
            movementOwner = BotMovementArbitration::Owner::CombatRange;
            movementPriority = BotMovementArbitration::Priority::Combat;
        }
        else if (Cohort().Config.ValidationRouteEnable)
        {
            movementOwner = BotMovementArbitration::Owner::Route;
            movementPriority = BotMovementArbitration::Priority::Route;
        }
        else
        {
            movementOwner = BotMovementArbitration::Owner::Formation;
            movementPriority = BotMovementArbitration::Priority::Formation;
        }
    }

    BotWorldMovement::Intent intent;
    intent.X = x;
    intent.Y = y;
    intent.Z = z;
    intent.TerminalOnFailure = terminalOnFailure;
    intent.Owner = movementOwner;
    intent.Priority = movementPriority;
    intent.DynamicTarget = dynamicTarget;
    intent.DynamicTargetRange = dynamicTargetRange;

    // These are mechanical admission requirements carried by the legacy
    // route adapter.  The executor never infers them from combat, quest, or
    // encounter policy.
    intent.AllowProgressiveSegments = BotWorldMovement::AllowsProgressiveSegments(
        movementOwner, state.NativeRecoveryEntranceRequired);
    intent.RequireCompletePath = movementOwner
        == BotMovementArbitration::Owner::Route
        && intent.AllowProgressiveSegments
        && Cohort().Config.ValidationRouteKind == "descent"
        && Cohort().Config.ValidationRouteDescentAction
            == "native_walkable_descent";
    intent.AllowRecentFailureRetry = Cohort().Config.ValidationRouteEnable;
    return ExecuteMovementIntent(state, bot, intent);
}
