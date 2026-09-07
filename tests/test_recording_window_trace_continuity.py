from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRecordingWindow.cpp"


def test_stats_window_rollover_preserves_trace_and_planner_state(
    tmp_path: Path,
) -> None:
    stub = tmp_path / "Bots" / "BotWorldPopulationMgr.h"
    stub.parent.mkdir()
    stub.write_text(
        r'''
#ifndef BOT_WORLD_POPULATION_MGR_RECORDING_WINDOW_TEST_STUB_H
#define BOT_WORLD_POPULATION_MGR_RECORDING_WINDOW_TEST_STUB_H

#include <cstdint>
#include <map>
#include <string>
#include <vector>

using uint32 = std::uint32_t;
using uint64 = std::uint64_t;

enum class BotWorldRuntimeMode
{
    AlwaysOnAutonomy,
    ManualExperiment,
};

struct BotWorldExperimentConfig
{
    bool AutoStartRecording = false;
    uint32 AutoRecordingWindowMinutes = 0;
    uint32 TargetPopulation = 0;
    std::string AutoRecordingNamePrefix;
    std::string BrainVersion;
    std::string Name;
};

struct BotWorldStatus
{
    bool Active = false;
    BotWorldRuntimeMode Mode = BotWorldRuntimeMode::ManualExperiment;
    std::string Name;
    uint32 TargetBots = 0;
    uint32 ActiveBots = 0;
    uint64 ExperimentId = 0;
    uint64 RunId = 0;
};

struct StubBotTraceState
{
    uint64 TraceSequence = 0;
    std::vector<uint64> DecisionTrace;
};

struct StubPartyRuntime
{
    std::vector<StubBotTraceState> Bots;
    std::map<uint32, uint64> TraceExportCursorByGuid;
    std::map<uint32, uint64> PlannerReceipts;
};

struct StubTelemetryBuffer
{
    uint32 FlushCount = 0;
    std::vector<uint64> FlushedRunIds;

    void FlushOpenClips(uint64, uint64 runId, std::string const&)
    {
        ++FlushCount;
        FlushedRunIds.push_back(runId);
    }
};

class BotWorldPopulationMgr
{
public:
    struct CohortRuntime
    {
        bool Active = false;
        BotWorldRuntimeMode RuntimeMode =
            BotWorldRuntimeMode::ManualExperiment;
        BotWorldExperimentConfig Config;
        BotWorldStatus Metrics;
        StubTelemetryBuffer TelemetryBuffer;
        std::string SelectedProfileName;
        uint64 ExperimentId = 0;
        uint64 RunId = 0;
        uint32 ElapsedMs = 0;
        uint32 RecordingWindowElapsedMs = 0;
        uint32 RecordingWindowIndex = 0;
    };

    using PartyRuntime = StubPartyRuntime;

    CohortRuntime& Cohort()
    {
        return _cohort;
    }

    CohortRuntime const& Cohort() const
    {
        return _cohort;
    }

    PartyRuntime& Party()
    {
        return _party;
    }

    void RecordRunStart()
    {
        ++_runStarts;
        ++_cohort.RunId;
        _cohort.ExperimentId = _cohort.RunId;
        _cohort.Metrics.ExperimentId = _cohort.ExperimentId;
        _cohort.Metrics.RunId = _cohort.RunId;
    }

    void RecordRunStop()
    {
        ++_runStops;
    }

    void ResetTraceStreams()
    {
        ++_resetCalls;
        _party.TraceExportCursorByGuid.clear();
        _party.PlannerReceipts.clear();
        for (StubBotTraceState& state : _party.Bots)
        {
            state.TraceSequence = 0;
            state.DecisionTrace.clear();
        }
    }

    uint32 RunStarts() const
    {
        return _runStarts;
    }

    uint32 RunStops() const
    {
        return _runStops;
    }

    uint32 ResetCalls() const
    {
        return _resetCalls;
    }

    void MaybeStartAutoRecordingWindow();
    void RotateAutoRecordingWindowIfNeeded(uint32 diff);
    std::string BuildAutoRecordingWindowName() const;

private:
    CohortRuntime _cohort;
    PartyRuntime _party;
    uint32 _runStarts = 0;
    uint32 _runStops = 0;
    uint32 _resetCalls = 0;
};

#endif
''',
        encoding="utf-8",
    )

    replay = tmp_path / "recording_window_trace_continuity.cpp"
    replay.write_text(
        f'''
#include "{MODULE}"

#include <cassert>

int main()
{{
    BotWorldPopulationMgr manager;
    BotWorldPopulationMgr::CohortRuntime& cohort = manager.Cohort();
    StubPartyRuntime& party = manager.Party();
    cohort.Active = true;
    cohort.RuntimeMode = BotWorldRuntimeMode::AlwaysOnAutonomy;
    cohort.Config.AutoStartRecording = true;
    cohort.Config.AutoRecordingWindowMinutes = 1;
    cohort.Config.TargetPopulation = 2;
    cohort.Config.BrainVersion = "brain-v1";
    cohort.SelectedProfileName = "frozen_profile";
    cohort.RunId = 31;
    cohort.ExperimentId = 31;
    cohort.Metrics.RunId = 31;
    cohort.Metrics.ExperimentId = 31;
    cohort.RecordingWindowIndex = 0;
    cohort.ElapsedMs = 899000;
    cohort.RecordingWindowElapsedMs = 59999;
    party.Bots.push_back({{ 4096, {{ 4088, 4089, 4090 }} }});
    party.TraceExportCursorByGuid[30009] = 4088;
    party.PlannerReceipts[30009] = 810;

    manager.RotateAutoRecordingWindowIfNeeded(1);
    assert(manager.RunStops() == 1);
    assert(manager.RunStarts() == 1);
    assert(cohort.TelemetryBuffer.FlushCount == 1);
    assert(cohort.TelemetryBuffer.FlushedRunIds[0] == 31);
    assert(cohort.RunId == 32);
    assert(cohort.ExperimentId == 32);
    assert(cohort.Metrics.RunId == 32);
    assert(cohort.Metrics.ExperimentId == 32);
    assert(cohort.RecordingWindowIndex == 1);
    assert(cohort.Config.Name == "autonomy_window_1");
    assert(cohort.Metrics.Name == "autonomy_window_1");
    assert(cohort.Metrics.Active);
    assert(cohort.Metrics.Mode == BotWorldRuntimeMode::AlwaysOnAutonomy);
    assert(cohort.Metrics.TargetBots == 2);
    assert(cohort.Metrics.ActiveBots == 1);
    assert(cohort.ElapsedMs == 0);
    assert(cohort.RecordingWindowElapsedMs == 0);
    assert(party.Bots[0].TraceSequence == 4096);
    assert((party.Bots[0].DecisionTrace ==
        std::vector<uint64>{{ 4088, 4089, 4090 }}));
    assert(party.TraceExportCursorByGuid.at(30009) == 4088);
    assert(party.PlannerReceipts.at(30009) == 810);
    assert(manager.ResetCalls() == 0);

    party.Bots[0].TraceSequence = 4097;
    party.Bots[0].DecisionTrace.push_back(4091);
    cohort.RecordingWindowElapsedMs = 59999;
    manager.RotateAutoRecordingWindowIfNeeded(1);
    assert(manager.RunStops() == 2);
    assert(manager.RunStarts() == 2);
    assert(cohort.TelemetryBuffer.FlushCount == 2);
    assert(cohort.TelemetryBuffer.FlushedRunIds[1] == 32);
    assert(cohort.RunId == 33);
    assert(cohort.ExperimentId == 33);
    assert(cohort.Metrics.RunId == 33);
    assert(cohort.Metrics.ExperimentId == 33);
    assert(cohort.RecordingWindowIndex == 2);
    assert(cohort.Config.Name == "autonomy_window_2");
    assert(cohort.Metrics.Name == "autonomy_window_2");
    assert(party.Bots[0].TraceSequence == 4097);
    assert((party.Bots[0].DecisionTrace ==
        std::vector<uint64>{{ 4088, 4089, 4090, 4091 }}));
    assert(party.TraceExportCursorByGuid.at(30009) == 4088);
    assert(party.PlannerReceipts.at(30009) == 810);
    assert(manager.ResetCalls() == 0);
}}
''',
        encoding="utf-8",
    )
    binary = tmp_path / "recording_window_trace_continuity"
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(tmp_path),
            str(replay),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)
