#include "Bots/BotWorldPopulationMgr.h"

#include "Player.h"

bool BotWorldPopulationMgr::MoveBotToPoint(
    WorldBotState& state, Player* bot, float x, float y, float z,
    bool terminalOnFailure, BotMovementArbitration::Owner movementOwner,
    BotMovementArbitration::Priority movementPriority, Unit* dynamicTarget,
    float dynamicTargetRange, std::string_view movementReason)
{
    return MoveBotToPointWithReferenceFloor(state, bot, x, y, z,
        std::nullopt, terminalOnFailure, movementOwner, movementPriority,
        dynamicTarget, dynamicTargetRange, movementReason);
}

bool BotWorldPopulationMgr::MoveBotToPointWithReferenceFloor(
    WorldBotState& state, Player* bot, float x, float y, float z,
    std::optional<float> referenceFloorZ, bool terminalOnFailure,
    BotMovementArbitration::Owner movementOwner,
    BotMovementArbitration::Priority movementPriority, Unit* dynamicTarget,
    float dynamicTargetRange, std::string_view movementReason)
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
    intent.ReferenceFloorZ = referenceFloorZ;
    intent.TerminalOnFailure = terminalOnFailure;
    intent.Owner = movementOwner;
    intent.Priority = movementPriority;
    intent.DynamicTarget = dynamicTarget;
    intent.DynamicTargetRange = dynamicTargetRange;
    intent.IntentReason = movementReason;

    // A released validation member can briefly reach this adapter before the
    // recovery episode has published its entrance-required flag.  The exact
    // frozen corpse authority and map mismatch are sufficient to admit the
    // already-typed entrance Move through the native long-path executor; no
    // destination is rewritten here.
    bool const nativeRecoveryEpisodeScoped = state.NativeRecoveryEpisodeStartedMs
        && state.NativeRecoveryEpisodeAttemptId == Cohort().AttemptId
        && state.NativeRecoveryEpisodeRouteGeneration
            == Party().ValidationRouteGeneration
        && state.NativeRecoveryEpisodeWipeGeneration
            == Cohort().Raid.WipeGeneration
        && state.NativeRecoveryEpisodeDeathOrdinal == state.RecentDeathCount;
    bool const nativeRecoveryCrossMap = movementOwner
        == BotMovementArbitration::Owner::Recovery
        && state.ValidationCohortLocked
        && nativeRecoveryEpisodeScoped
        && HasNativeRaidCorpseAuthority(state, bot)
        && bot->GetMapId() != state.ValidationCohortMapId;
    bool const nativeRecoveryEntranceRequired =
        (state.NativeRecoveryEntranceRequired && nativeRecoveryEpisodeScoped)
        || nativeRecoveryCrossMap;

    // These are mechanical admission requirements carried by the legacy
    // route adapter.  The executor never infers them from combat, quest, or
    // encounter policy.
    bool const boundedHazardProgress = movementOwner
        == BotMovementArbitration::Owner::Hazard
        && movementReason == "parasite_contact_evade";
    intent.AllowProgressiveSegments = BotWorldMovement::AllowsProgressiveSegments(
        movementOwner, nativeRecoveryEntranceRequired);
    intent.BoundedHazardProgress = boundedHazardProgress;
    intent.RequireCompletePath = movementOwner
        == BotMovementArbitration::Owner::Route
        && intent.AllowProgressiveSegments
        && Cohort().Config.ValidationRouteKind == "descent"
        && Cohort().Config.ValidationRouteDescentAction
            == "native_walkable_descent";
    intent.AllowRecentFailureRetry = Cohort().Config.ValidationRouteEnable;
    intent.AllowNativeLongPath = BotWorldMovement::AllowsNativeLongPath(
        movementOwner, nativeRecoveryEntranceRequired);
    intent.NativeRecoveryCrossMapPending =
        nativeRecoveryEntranceRequired
        && state.ValidationCohortLocked
        && bot->GetMapId() != state.ValidationCohortMapId;
    return ExecuteMovementIntent(state, bot, intent);
}
