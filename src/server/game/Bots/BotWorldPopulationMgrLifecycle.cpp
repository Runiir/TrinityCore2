#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotMgr.h"
#include "Bots/BotRaidAreaAuthority.h"

#include "Config.h"
#include "DatabaseEnv.h"
#include "Player.h"

#include <string>

bool BotWorldPopulationMgr::IsActive() const
{
    return ActiveCohortCount() != 0;
}

bool BotWorldPopulationMgr::Start(std::string const& experimentName, BotWorldExperimentConfig const* overrideConfig)
{
    if (Cohort().Active && Cohort().RuntimeMode == BotWorldRuntimeMode::AlwaysOnAutonomy)
    {
        if (Cohort().RunId)
        {
            Cohort().TelemetryBuffer.FlushOpenClips(Cohort().ExperimentId, Cohort().RunId, Cohort().Config.BrainVersion);
            RecordRunStop();
        }
        else
            Cohort().TelemetryBuffer.Clear();

        if (overrideConfig)
            LoadConfig(experimentName.empty() ? "autonomy_recording_window" : experimentName, overrideConfig);
        else if (!experimentName.empty())
            Cohort().Config.Name = experimentName;
        else
            Cohort().Config.Name = "autonomy_recording_window";

        Cohort().Metrics = BotWorldStatus();
        Cohort().Metrics.Active = true;
        Cohort().Metrics.Mode = BotWorldRuntimeMode::AlwaysOnAutonomy;
        Cohort().Metrics.Name = Cohort().Config.Name;
        Cohort().Metrics.TargetBots = Cohort().Config.TargetPopulation;
        Cohort().ElapsedMs = 0;
        Cohort().RecordingWindowElapsedMs = 0;
        ResetTraceStreams();
        ResetCombatLog();
        RecordRunStart();
        return true;
    }

    if (Cohort().Active)
        Stop();

    if (!sConfigMgr->GetBoolDefault("BotWorld.Enable", false) || !sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
    {
        Cohort().RuntimeProfileSelectionPending = false;
        return false;
    }

    if (!Cohort().AttemptId)
        Cohort().AttemptId = 1;
    Party() = PartyRuntime();
    LoadConfig(experimentName.empty() ? "autonomous_zone_10" : experimentName, overrideConfig);
    Cohort().PinnedProfileGeneration = BotClassSpecActionProfileStore::ActiveDbGeneration();
    Cohort().PinnedProfileContentHash = BotClassSpecActionProfileStore::ActiveDbContentHash();
    if (!overrideConfig && Cohort().Config.ValidationRouteEnable && IsValidationProfileName(Cohort().Config.Name) && !PrepareCurrentValidationProfile("manual_start"))
        return false;
    Cohort().TelemetryBuffer.Clear();
    Cohort().ExperimentCoordinator.Clear();
    Cohort().FailedSpawnGuids.clear();
    Cohort().LastPopulationFailureReason.clear();
    Cohort().ValidationAttemptFailureReason.clear();
    Cohort().ValidationAttemptFailureAttemptId = 0;
    Cohort().ValidationAttemptFailureRouteGeneration = 0;
    Cohort().ValidationAdmission = ValidationAdmissionPhase::Provisioning;
    Cohort().ValidationAdmissionStarted = false;
    Cohort().ValidationAdmissionBatchSealed = false;
    Cohort().ValidationRaidAdmissionComplete = false;
    Cohort().ValidationRaidAdmissionFailed = false;
    Cohort().Raid = RaidRuntime();
    Cohort().Metrics = BotWorldStatus();
    Cohort().Metrics.Active = true;
    Cohort().Metrics.Mode = BotWorldRuntimeMode::ManualExperiment;
    Cohort().Metrics.Name = Cohort().Config.Name;
    Cohort().Metrics.TargetBots = Cohort().Config.TargetPopulation;
    Cohort().ElapsedMs = 0;
    Cohort().RecordingWindowElapsedMs = 0;
    ResetCombatLog();
    Cohort().Active = true;
    Cohort().RuntimeMode = BotWorldRuntimeMode::ManualExperiment;

    RecordRunStart();
    EnsurePopulation();
    return Cohort().Active;
}

void BotWorldPopulationMgr::Stop()
{
    ClearPendingHealCasts("run_stop");
    if (Cohort().CalibrationActive || !Party().CalibrationBots.empty())
        StopCombatCalibration();
    if (!Cohort().Active)
        return;

    // Flush the in-memory fingerprint tail while bots are still loaded.
    // RecordRunStop() repeats this safely for callers that stop a run through
    // a different lifecycle path.
    FlushPendingDecisionFingerprintMemory();

    if (Cohort().RuntimeMode == BotWorldRuntimeMode::AlwaysOnAutonomy)
    {
        for (WorldBotState const& state : Party().Bots)
        {
            BotRaidAreaAuthority::Clear(state.Guid.GetRawValue());
            PersistBotPosition(GetBot(state));
        }
        Cohort().TelemetryBuffer.FlushOpenClips(Cohort().ExperimentId, Cohort().RunId, Cohort().Config.BrainVersion);
        RecordRunStop();
        Cohort().ExperimentCoordinator.Clear();
        Cohort().ExperimentCoordinator.Configure(0, Cohort().Config.BrainVersion);
        Cohort().RunId = 0;
        Cohort().ExperimentId = 0;
        Cohort().Metrics.RunId = 0;
        Cohort().Metrics.ExperimentId = 0;
        return;
    }

    for (WorldBotState const& state : Party().Bots)
    {
        BotRaidAreaAuthority::Clear(state.Guid.GetRawValue());
        Player* bot = GetBot(state);
        PersistBotPosition(bot);
        RecordActivityStop(state, bot);
        sBotMgr->RemoveWorldBot(state.Guid);
    }

    Cohort().TelemetryBuffer.FlushOpenClips(Cohort().ExperimentId, Cohort().RunId, Cohort().Config.BrainVersion);
    RecordRunStop();
    Cohort().ExperimentCoordinator.Clear();
    Cohort().RunId = 0;
    Cohort().ExperimentId = 0;
    ReleaseCohortLeases();
    Party() = PartyRuntime();
    Cohort().Active = false;
}

bool BotWorldPopulationMgr::StartAutonomy(BotWorldExperimentConfig const* overrideConfig)
{
    if (Cohort().Active)
    {
        if (Cohort().RuntimeMode == BotWorldRuntimeMode::AlwaysOnAutonomy && !overrideConfig && !Cohort().RuntimeProfileDirty)
            return true;

        if (Cohort().RuntimeMode == BotWorldRuntimeMode::AlwaysOnAutonomy)
            StopAutonomy();
        else
            Stop();
    }

    if (!sConfigMgr->GetBoolDefault("BotWorld.Enable", false) || !sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
    {
        Cohort().RuntimeProfileSelectionPending = false;
        return false;
    }

    ClearPendingHealCasts("autonomy_reset");
    if (!Cohort().AttemptId)
        Cohort().AttemptId = 1;
    Party() = PartyRuntime();
    LoadConfig("always_on_autonomy", overrideConfig);
    Cohort().PinnedProfileGeneration = BotClassSpecActionProfileStore::ActiveDbGeneration();
    Cohort().PinnedProfileContentHash = BotClassSpecActionProfileStore::ActiveDbContentHash();
    if (!overrideConfig && Cohort().Config.ValidationRouteEnable && IsValidationProfileName(Cohort().Config.Name) && !PrepareCurrentValidationProfile("autonomy_start"))
        return false;
    Cohort().TelemetryBuffer.Clear();
    Cohort().ExperimentCoordinator.Clear();
    Cohort().ExperimentCoordinator.Configure(0, Cohort().Config.BrainVersion);
    Cohort().FailedSpawnGuids.clear();
    Cohort().LastPopulationFailureReason.clear();
    Cohort().ValidationAttemptFailureReason.clear();
    Cohort().ValidationAttemptFailureAttemptId = 0;
    Cohort().ValidationAttemptFailureRouteGeneration = 0;
    Cohort().ValidationAdmission = ValidationAdmissionPhase::Provisioning;
    Cohort().ValidationAdmissionStarted = false;
    Cohort().ValidationAdmissionBatchSealed = false;
    Cohort().ValidationRaidAdmissionComplete = false;
    Cohort().ValidationRaidAdmissionFailed = false;
    Cohort().Raid = RaidRuntime();
    Cohort().Metrics = BotWorldStatus();
    Cohort().Metrics.Active = true;
    Cohort().Metrics.Mode = BotWorldRuntimeMode::AlwaysOnAutonomy;
    Cohort().Metrics.Name = Cohort().Config.Name;
    Cohort().Metrics.TargetBots = Cohort().Config.TargetPopulation;
    Cohort().ElapsedMs = 0;
    Cohort().RecordingWindowElapsedMs = 0;
    Cohort().RecordingWindowIndex = 0;
    Cohort().RunId = 0;
    Cohort().ExperimentId = 0;
    ResetCombatLog();
    Cohort().Active = true;
    Cohort().RuntimeMode = BotWorldRuntimeMode::AlwaysOnAutonomy;
    Cohort().RuntimeProfileDirty = false;

    MaybeStartAutoRecordingWindow();
    EnsurePopulation();
    return Cohort().Active;
}

void BotWorldPopulationMgr::StopAutonomy()
{
    ClearPendingHealCasts("autonomy_stop");
    if (Cohort().CalibrationActive || !Party().CalibrationBots.empty())
        StopCombatCalibration();
    if (!Cohort().Active || Cohort().RuntimeMode != BotWorldRuntimeMode::AlwaysOnAutonomy)
        return;

    // RemoveWorldBot invalidates GetBot(state); flush while every state still
    // has its loaded Player so the final fingerprint tail is retained.
    FlushPendingDecisionFingerprintMemory();
    for (WorldBotState const& state : Party().Bots)
    {
        BotRaidAreaAuthority::Clear(state.Guid.GetRawValue());
        Player* bot = GetBot(state);
        PersistBotPosition(bot);
        RecordActivityStop(state, bot);
        sBotMgr->RemoveWorldBot(state.Guid);
    }

    Cohort().TelemetryBuffer.FlushOpenClips(Cohort().ExperimentId, Cohort().RunId, Cohort().Config.BrainVersion);
    RecordRunStop();
    Cohort().ExperimentCoordinator.Clear();
    ReleaseCohortLeases();
    Party() = PartyRuntime();
    Cohort().Active = false;
    Cohort().RunId = 0;
    Cohort().ExperimentId = 0;
}

void BotWorldPopulationMgr::Shutdown()
{
    ClearPendingHealCasts("shutdown");
    if (Cohort().CalibrationActive || !Party().CalibrationBots.empty())
        StopCombatCalibration();
    if (!Cohort().Active)
        return;

    FlushPendingDecisionFingerprintMemory();
    for (WorldBotState const& state : Party().Bots)
    {
        BotRaidAreaAuthority::Clear(state.Guid.GetRawValue());
        if (!state.Guid.IsEmpty() && LeaseOwnedByCurrentCohort(state.Guid.GetCounter()))
        {
            CharacterDatabase.DirectPExecute("UPDATE characters SET online = 0 WHERE guid = %u", state.Guid.GetCounter());
            CharacterDatabase.DirectPExecute("UPDATE character_bot_pool SET in_use = 0 WHERE guid = %u", state.Guid.GetCounter());
        }
    }

    Cohort().TelemetryBuffer.FlushOpenClips(Cohort().ExperimentId, Cohort().RunId, Cohort().Config.BrainVersion);
    RecordRunStop();
    Cohort().ExperimentCoordinator.Clear();
    ReleaseCohortLeases();
    Party() = PartyRuntime();
    Cohort().Active = false;
    Cohort().RunId = 0;
    Cohort().ExperimentId = 0;
    Cohort().Metrics.Active = false;
    Cohort().Metrics.ActiveBots = 0;
}

bool BotWorldPopulationMgr::SpawnAutonomyBots(uint32 count)
{
    if (!Cohort().Active || Cohort().RuntimeMode != BotWorldRuntimeMode::AlwaysOnAutonomy || !count)
        return false;

    Cohort().Config.TargetPopulation += count;
    Cohort().Metrics.TargetBots = Cohort().Config.TargetPopulation;
    EnsurePopulation();
    return true;
}

