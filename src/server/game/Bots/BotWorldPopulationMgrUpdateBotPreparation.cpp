#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/BotRaidAreaAuthority.h"

#include "Config.h"
#include "ObjectAccessor.h"
#include "Player.h"

#include <algorithm>
#include <limits>
#include <string>

using BotWorldPopulationMgrNativeHelpers::Distance2d;
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;
using BotWorldPopulationMgrSpellSemantics::NowMs;

void BotWorldPopulationMgr::BotUpdateContext::EnsureProgressionScored()
{
    if (ProgressionScored)
        return;
    Power = BotLongTermProgressionBrain::CalculateRolePower(Bot);
    Stage = BotLongTermProgressionBrain::ClassifyStage(Bot, Power);
    ActivityScores = Manager.Cohort().Config.EnableProgression
        ? BotLongTermProgressionBrain::ScoreActivities(Bot, Power, Stage,
            Manager.Cohort().Config.AllowQuesting,
            Manager.Cohort().Config.AllowCombat,
            &Manager.Cohort().LearningConfig)
        : std::vector<BotActivityScore>(1, BotActivityScore());
    Manager.ApplyPolicyModelScores(ActivityScores, Bot, Power, Stage);
    ChosenActivity = BotLongTermProgressionBrain::ChooseActivity(ActivityScores);
    State.ActivityType = BotLongTermProgressionBrain::ToString(ChosenActivity.Activity);
    State.ProgressionStage = BotLongTermProgressionBrain::ToString(Stage);
    ProgressionScored = true;
}

void BotWorldPopulationMgr::HoldValidationAttemptFailure(WorldBotState& state,
    Player* bot)
{
    BotRaidAreaAuthority::SetAllOffenseSuppressed(
        bot->GetGUID().GetRawValue(), true);
    if (!state.ValidationRouteTerminalState)
        state.ValidationRouteTerminalAtMs = NowMs();
    state.ValidationRouteTerminalState = true;
    state.ValidationRouteTerminalGeneration =
        Cohort().ValidationAttemptFailureRouteGeneration;
    state.ValidationRouteTerminalReason =
        Cohort().ValidationAttemptFailureReason;
    state.LastDecisionSituation = "validation_route_terminal";
    state.LastDecisionAction = "validation_route_terminal_hold";
    state.LastDecisionResult = Cohort().ValidationAttemptFailureReason;
    state.LastDecisionReason = Cohort().ValidationAttemptFailureReason;
    state.LastNoProgressReason = Cohort().ValidationAttemptFailureReason;
    state.DecisionTimer = 0;
}

bool BotWorldPopulationMgr::PrepareBotUpdate(BotUpdateContext& context)
{
    if (Cohort().Config.ValidationRouteEnable)
    {
        if (!Cohort().Raid.BotActionsEnabled)
        {
            context.State.LastDecisionResult = "validation_cohort_action_gate_closed";
            context.State.LastDecisionReason = Cohort().LastPopulationFailureReason.empty()
                ? "server_provisioning_activation_pending" : Cohort().LastPopulationFailureReason;
            return false;
        }
        if (context.State.ValidationCohortViolation)
            return false;
        if (!context.State.ValidationCohortLocked)
        {
            context.State.LastDecisionResult = "validation_cohort_formation_pending";
            context.State.LastDecisionReason = Cohort().LastPopulationFailureReason.empty()
                ? "validation_cohort_identity_not_frozen" : Cohort().LastPopulationFailureReason;
            return false;
        }
        if (!IsValidationCohortMemberInOriginalInstance(context.State, context.Bot))
        {
            MarkValidationCohortViolation(context.State, context.Bot, "validation_cohort_instance_mismatch");
            return false;
        }
    }

    // A successful native resurrection closes the release episode.  Do not
    // let a later unrelated death inherit permission to ACK an outside
    // worldport as if it were the BWD runback.
    if (context.Bot->IsAlive())
    {
        context.State.NativeBattleResDecision = "unresolved";
        context.State.NativeBattleResOwnerGuid.Clear();
        context.State.NativeBattleResSpellId = 0;
        context.State.NativeBattleResDecisionAtMs = 0;
        context.State.NativeBattleResDecisionUntilMs = 0;
        context.State.NativeBattleResApproachIntentDecisionAtMs = 0;
        context.State.NativeBattleResApproachIntentAcceptedUntilMs = 0;
        context.State.NativeReleaseRequested = false;
        context.State.NativeRunbackAreaTriggerId = 0;
        context.State.NativeReleaseLandingObserved = false;
        context.State.NativeReleaseLandingMapId = 0;
        context.State.NativeReleaseLandingInstanceId = 0;
        context.State.NativeReleaseLandingWipeGeneration = 0;
        context.State.NativeReleaseLandingX = 0.0f;
        context.State.NativeReleaseLandingY = 0.0f;
        context.State.NativeReleaseLandingZ = 0.0f;
        context.State.NativeRecoveryEpisodeAttemptId = 0;
        context.State.NativeRecoveryEpisodeRouteGeneration = 0;
        context.State.NativeRecoveryEpisodeWipeGeneration = 0;
        context.State.NativeRecoveryEpisodeDeathOrdinal = 0;
        context.State.NativeRecoveryEpisodePhase = "none";
        context.State.NativeRecoveryEpisodeStartedMs = 0;
        context.State.NativeRecoveryEpisodeLastProgressMs = 0;
        context.State.NativeRecoveryEpisodeDistanceTarget = "none";
        context.State.NativeRecoveryEpisodeBestDistance =
            std::numeric_limits<float>::max();
        context.State.NativeRecoveryMovementRetryCount = 0;
        context.State.NativeRecoveryReleaseRejectionCount = 0;
        context.State.NativeRecoveryEntranceUnavailableCount = 0;
        context.State.NativeRecoveryEntranceRejectionCount = 0;
        context.State.NativeRecoveryReclaimRejectionCount = 0;
        context.State.NativeRecoveryEntranceRequired = false;
        context.State.NativeRecoveryEntranceObserved = false;
        context.State.NativeRecoveryEntranceAvailable = false;
    }

    Cohort().TelemetryBuffer.Observe(context.Bot, context.Bot->IsInCombat() ? "combat" : "ambient", nullptr, nullptr, nullptr);
    Cohort().TelemetryBuffer.FlushClosedClips(Cohort().ExperimentId, Cohort().RunId, Cohort().Config.BrainVersion, context.Bot->GetGUID());

    if (!Cohort().ValidationAttemptFailureReason.empty()
        && Cohort().ValidationAttemptFailureAttemptId == Cohort().AttemptId
        && context.Bot->IsAlive())
    {
        HoldValidationAttemptFailure(context.State, context.Bot);
        return false;
    }

    // Install the recovery hold before any decision-timer or route branch can
    // return.  Native pet restoration is permitted while hostile authority is
    // suppressed; the ready response is withheld until the owner and every
    // extant controlled unit are alive, idle, and naturally out of combat.
    if (context.Bot->IsAlive() && IsNativeRaidRecoveryEvidencePending())
    {
        SuppressNativeRaidRecovery(context.State, context.Bot);
        if (!TryRestoreNativeRaidRecoveryPet(context.State, context.Bot))
            TryRespondNativeRaidReadyCheck(context.State, context.Bot);
        context.State.DecisionTimer = 0;
        return false;
    }

    TryRespondNativeRaidReadyCheck(context.State, context.Bot);

    if (!context.Bot->IsAlive())
    {
        HandleBotDeath(context.State, context.Bot, context.Diff);
        return false;
    }
    context.State.DeadTimer = 0;
    context.State.DeathEpisodeRecorded = false;
    RememberSafePosition(context.State, context.Bot, context.Diff);
    RememberVisiblePois(context.State, context.Bot, context.Diff);

    context.Target = context.State.TargetGuid.IsEmpty() ? nullptr : ObjectAccessor::GetUnit(*context.Bot, context.State.TargetGuid);
    if (!context.Target)
        context.Target = context.Bot->GetVictim();

    float moved = Distance2d(context.Bot->GetPositionX(), context.Bot->GetPositionY(), context.State.LastX, context.State.LastY);
    bool moving = context.Bot->isMoving() || context.Bot->HasUnitState(UNIT_STATE_MOVING);
    bool combatOrCasting = context.Bot->IsInCombat() || context.Bot->HasUnitState(UNIT_STATE_CASTING) || (context.Bot->GetVictim() && context.Bot->GetVictim()->IsAlive());
    uint32 previousStuckTimer = context.State.StuckTimer;
    context.State.IsMoving = moving;
    context.State.MovementProgressWindowMs += context.Diff;
    context.State.MovementProgressWindowDistance += moved;
    context.State.DistanceMovedSinceLastDecision += moved;
    bool movementProgress = context.State.MovementProgressWindowDistance >= 0.2f;
    if (movementProgress || combatOrCasting)
        context.State.LastMovementProgressMs = NowMs();
    if (movementProgress)
    {
        context.State.StuckRecoveryStage = 0;
        context.State.StuckRecoveryStartedMs = 0;
        TryResolveBotBlocker(context.State, context.Bot, "movement_progress");
    }
    bool validationRouteComplete = Cohort().Config.ValidationRouteEnable && Party().ValidationRouteManifestComplete;
    bool terminalRouteAction = Cohort().Config.ValidationRouteEnable
        && (context.State.LastDecisionAction == "validation_route_complete"
            || context.State.LastDecisionSituation == "validation_route_manifest");
    if (!combatOrCasting && moving && !movementProgress && !validationRouteComplete && !terminalRouteAction)
        context.State.StuckTimer += context.Diff;
    else
        context.State.StuckTimer = 0;
    if (movementProgress || context.State.MovementProgressWindowMs >= 1000)
    {
        context.State.MovementProgressWindowMs = 0;
        context.State.MovementProgressWindowDistance = 0.0f;
    }
    context.State.LastX = context.Bot->GetPositionX();
    context.State.LastY = context.Bot->GetPositionY();
    context.State.LastZ = context.Bot->GetPositionZ();

    uint32 const earlyStuckDiagnosticMs = 1500;
    if (!validationRouteComplete && !terminalRouteAction
        && context.State.StuckTimer >= earlyStuckDiagnosticMs && previousStuckTimer < earlyStuckDiagnosticMs)
    {
        char const* stuckReason = Cohort().Config.ValidationRouteEnable ? "validation_route_stuck_suspected" : "stuck_suspected";
        float targetHealthPct = context.Target ? UnitHealthPct(context.Target) : 0.0f;
        RecordRouteProgress(context.State, context.Bot, context.Target, stuckReason, targetHealthPct, targetHealthPct, context.State.StuckTimer, 6000);
        std::string stuckText = "Stuck: " + context.State.LastRouteProgress.Summary;
        if (context.Bot && stuckText != context.State.LastBlockedDiagnosticText)
        {
            context.Bot->Say(stuckText, LANG_UNIVERSAL);
            context.State.LastBlockedDiagnosticText = stuckText;
        }
    }

    if (!validationRouteComplete && !terminalRouteAction && context.State.StuckTimer >= 6000)
    {
        context.EnsureProgressionScored();
        ++Cohort().Metrics.StuckEvents;
        MarkStuckFailure(context.State, context.Bot);
        bool const recoveryScheduled = TryRecoverStuckBot(context.State, context.Bot);
        bool const validationRecovery = Cohort().Config.ValidationRouteEnable;
        char const* situationName = validationRecovery
            ? "validation_route_recovery" : "runtime_recovery";
        char const* actionName = recoveryScheduled
            ? "native_priority_repath" : "native_priority_repath_exhausted";
        char const* reason = recoveryScheduled
            ? "stuck_recovery_candidate_committed" : "stuck_recovery_candidates_exhausted";
        float const routeAnchorDistance = validationRecovery
            && Cohort().Config.ValidationRouteMapId == context.Bot->GetMapId()
                ? context.Bot->GetExactDist(Cohort().Config.ValidationRouteX,
                    Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ)
                : 0.0f;
        context.State.LastDecisionHandler = recoveryScheduled
            ? "recovery_supervisor" : "stuck_blocked";
        if (!recoveryScheduled)
            MarkBotBlocked(context.State, context.Bot, reason);
        std::string raw = BuildRawJson(context.Bot, context.Target);
        std::string semantic = BuildSemanticJson(context.Bot, context.Target, situationName,
            &context.Power, context.Stage, context.ChosenActivity.Activity);
        RecordEvent(context.State, context.Bot, recoveryScheduled ? "stuck_recovery_started" : "stuck_detected",
            context.Target, reason, raw.c_str(), semantic.c_str(), routeAnchorDistance,
            validationRecovery ? Cohort().Config.ValidationRouteTargetEntry : Cohort().Metrics.StuckEvents);
        RecordDecision(context.State, context.Bot, situationName, actionName, context.Target, raw.c_str(),
            semantic.c_str(), context.ActivityScores, context.ChosenActivity, context.Power,
            !recoveryScheduled, true);
        return false;
    }

    if (context.State.DecisionTimer > context.Diff)
    {
        context.State.DecisionTimer -= context.Diff;
        return false;
    }
    uint32 decisionTickMs = sConfigMgr->GetIntDefault("BotWorld.DecisionTickMs", 3000);
    BotClassSpecActionProfile const cadenceProfile =
        BotClassSpecActionProfileStore::Build(context.Bot, GetDungeonRole(context.Bot));
    uint32 const reactionTimeMs = BotClassSpecActionProfileStore::ReactionTimeMsForSpec(
        cadenceProfile.SpecTag.c_str());
    bool const responsiveSpecCombat = context.Bot->IsInCombat() && reactionTimeMs == 100;
    if (context.Bot->IsInCombat() || Cohort().Config.ValidationRouteEnable)
        decisionTickMs = std::min<uint32>(decisionTickMs, responsiveSpecCombat ? reactionTimeMs : 1000);
    context.State.DecisionTimer = std::max<uint32>(responsiveSpecCombat ? reactionTimeMs : 500, decisionTickMs);

    context.EnsureProgressionScored();

    if (context.Target && StopDisallowedDummyCombat(context.State, context.Bot, context.Target))
        context.Target = nullptr;

    uint32 maxHealth = context.Bot->GetMaxHealth();
    context.HpPct = maxHealth ? float(context.Bot->GetHealth()) / float(maxHealth) : 1.0f;
    context.Situation = context.Bot->IsInCombat() ? "open_world_combat" : "travel";
    context.Action = "wander";
    context.State.LastDecisionHandler = "none";
    context.State.LastDecisionQuestId = 0;
    context.HasActiveQuestObjective = (context.State.QuestWork.ActiveQuestId && FindQuestObjective(context.Bot, context.State.QuestWork.ActiveQuestId, context.ActivePlanForPriority))
        || (context.State.NewlyAcceptedQuestId && FindQuestObjective(context.Bot, context.State.NewlyAcceptedQuestId, context.ActivePlanForPriority))
        || FindActiveQuestObjective(context.Bot, context.ActivePlanForPriority);
    context.HasNearbyQuestGiver = Cohort().Config.AllowQuesting && HasNearbySupportedQuestGiver(context.Bot, context.State);
    context.CanInterleaveHubProfession = !context.Bot->IsInCombat()
        && !context.HasActiveQuestObjective
        && context.State.Sequence >= 2;

    // Validation runs are the first live adapter onto the decision kernel.
    // The route remains the preferred policy, but a retryable route outcome no
    // longer prevents boss, trash, or trained combat fallbacks from acting in
    // the same tick.  Native safety checks remain inside every legacy adapter.
    context.ValidationKernelOwnsTick = Cohort().Config.ValidationRouteEnable;

    return true;
}
