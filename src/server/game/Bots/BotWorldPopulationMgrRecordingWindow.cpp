#include "Bots/BotWorldPopulationMgr.h"

#include <sstream>
void BotWorldPopulationMgr::MaybeStartAutoRecordingWindow()
{
    if (!Cohort().Active || Cohort().RuntimeMode != BotWorldRuntimeMode::AlwaysOnAutonomy || !Cohort().Config.AutoStartRecording || Cohort().RunId)
        return;

    Cohort().Config.Name = BuildAutoRecordingWindowName();
    Cohort().Metrics.Name = Cohort().Config.Name;
    Cohort().Metrics.TargetBots = Cohort().Config.TargetPopulation;
    Cohort().RecordingWindowElapsedMs = 0;
    RecordRunStart();
}

void BotWorldPopulationMgr::RotateAutoRecordingWindowIfNeeded(uint32 diff)
{
    if (!Cohort().Active || Cohort().RuntimeMode != BotWorldRuntimeMode::AlwaysOnAutonomy || !Cohort().Config.AutoStartRecording)
        return;

    if (!Cohort().RunId)
    {
        MaybeStartAutoRecordingWindow();
        return;
    }

    Cohort().RecordingWindowElapsedMs += diff;
    uint32 windowMs = Cohort().Config.AutoRecordingWindowMinutes * 60 * 1000;
    if (Cohort().RecordingWindowElapsedMs < windowMs)
        return;

    Cohort().TelemetryBuffer.FlushOpenClips(Cohort().ExperimentId, Cohort().RunId, Cohort().Config.BrainVersion);
    RecordRunStop();
    ++Cohort().RecordingWindowIndex;
    Cohort().Config.Name = BuildAutoRecordingWindowName();
    Cohort().Metrics = BotWorldStatus();
    Cohort().Metrics.Active = true;
    Cohort().Metrics.Mode = BotWorldRuntimeMode::AlwaysOnAutonomy;
    Cohort().Metrics.Name = Cohort().Config.Name;
    Cohort().Metrics.TargetBots = Cohort().Config.TargetPopulation;
    Cohort().Metrics.ActiveBots = uint32(Party().Bots.size());
    Cohort().ElapsedMs = 0;
    Cohort().RecordingWindowElapsedMs = 0;
    ResetTraceStreams();
    RecordRunStart();
}

std::string BotWorldPopulationMgr::BuildAutoRecordingWindowName() const
{
    std::ostringstream name;
    name << (Cohort().Config.AutoRecordingNamePrefix.empty() ? "autonomy_window" : Cohort().Config.AutoRecordingNamePrefix)
         << "_" << Cohort().RecordingWindowIndex;
    return name.str();
}

