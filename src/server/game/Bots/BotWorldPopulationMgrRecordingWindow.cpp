#include <string>
#include <string_view>
#include <utility>

namespace BotRecordingWindowIdentity
{
struct NameTransition
{
    std::string_view ImmutableSelectedRuntimeProfile;
    std::string ExperimentName;
    std::string MetricsName;
};

NameTransition BuildNameTransition(
    std::string_view immutableSelectedRuntimeProfile,
    std::string recordingWindowName)
{
    return {
        immutableSelectedRuntimeProfile,
        recordingWindowName,
        std::move(recordingWindowName),
    };
}
}

#ifndef BOT_RECORDING_WINDOW_IDENTITY_ADAPTER_ONLY

#include "Bots/BotWorldPopulationMgr.h"

#include <sstream>
void BotWorldPopulationMgr::MaybeStartAutoRecordingWindow()
{
    if (!Cohort().Active || Cohort().RuntimeMode != BotWorldRuntimeMode::AlwaysOnAutonomy || !Cohort().Config.AutoStartRecording || Cohort().RunId)
        return;

    BotRecordingWindowIdentity::NameTransition const names =
        BotRecordingWindowIdentity::BuildNameTransition(
            Cohort().SelectedProfileName, BuildAutoRecordingWindowName());
    Cohort().Config.Name = names.ExperimentName;
    Cohort().Metrics.Name = names.MetricsName;
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
    BotRecordingWindowIdentity::NameTransition const names =
        BotRecordingWindowIdentity::BuildNameTransition(
            Cohort().SelectedProfileName, BuildAutoRecordingWindowName());
    Cohort().Config.Name = names.ExperimentName;
    Cohort().Metrics = BotWorldStatus();
    Cohort().Metrics.Active = true;
    Cohort().Metrics.Mode = BotWorldRuntimeMode::AlwaysOnAutonomy;
    Cohort().Metrics.Name = names.MetricsName;
    Cohort().Metrics.TargetBots = Cohort().Config.TargetPopulation;
    Cohort().Metrics.ActiveBots = uint32(Party().Bots.size());
    Cohort().ElapsedMs = 0;
    Cohort().RecordingWindowElapsedMs = 0;
    // This is a statistics window boundary, not a lifecycle reset. Keep the
    // attempt-scoped trace sequence/history, export cursors, and planner
    // receipts continuous; true start/profile resets still call the reset.
    RecordRunStart();
}

std::string BotWorldPopulationMgr::BuildAutoRecordingWindowName() const
{
    std::ostringstream name;
    name << (Cohort().Config.AutoRecordingNamePrefix.empty() ? "autonomy_window" : Cohort().Config.AutoRecordingNamePrefix)
         << "_" << Cohort().RecordingWindowIndex;
    return name.str();
}

#endif
