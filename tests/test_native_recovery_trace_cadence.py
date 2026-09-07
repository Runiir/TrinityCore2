from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRecovery.cpp"
EVENT_RECORDING = ROOT / "src/server/game/Bots/BotWorldPopulationMgrEventRecording.cpp"


def _matching_brace(source: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    raise AssertionError("unterminated production block")


def _recovery_episode_segment(source: str) -> str:
    start = source.index(
        "    uint64 const nowMs = NowMs();",
        source.index("TryNativeCorpseRun"),
    )
    branch = source.index("    if (!episodeMatches)", start)
    end = _matching_brace(source, source.index("{", branch)) + 1
    return source[start:end]


def _repeatable_event_segment(source: str) -> str:
    start = source.index("    bool const repeatableDiagnosticEvent =")
    end_marker = (
        "    RecordExperimentSegmentEvent(bot, eventType, result, 0, target, "
        "Cohort().TelemetryBuffer.GetActiveClipId(bot->GetGUID()), "
        "rawJson, semanticJson);"
    )
    end = source.index(end_marker, start) + len(end_marker)
    return source[start:end]


def test_native_recovery_episode_and_progress_cadence(
    tmp_path: Path,
) -> None:
    recovery_segment = _recovery_episode_segment(
        RECOVERY.read_text(encoding="utf-8")
    )
    event_segment = _repeatable_event_segment(
        EVENT_RECORDING.read_text(encoding="utf-8")
    )
    source = tmp_path / "native_recovery_trace_cadence.cpp"
    binary = tmp_path / "native_recovery_trace_cadence"
    harness = r'''
#include <cassert>
#include <cstdint>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

using uint32 = std::uint32_t;
using uint64 = std::uint64_t;

static uint64 gNowMs = 0;
constexpr uint64 RepeatableDiagnosticEventHeartbeatMs = 5000;

uint64 NowMs()
{
    return gNowMs;
}

struct Player
{
    uint64 Guid = 30002;

    uint64 GetGUID() const
    {
        return Guid;
    }
};

struct TargetGuid
{
    uint64 Counter = 0;

    uint64 GetCounter() const
    {
        return Counter;
    }
};

struct Target
{
    TargetGuid GetGUID() const
    {
        return {};
    }
};

bool EventLooksFailure(char const*, char const*)
{
    return false;
}

struct WorldBotState
{
    uint64 Guid = 30002;
    uint32 RecentDeathCount = 1;
    uint64 NativeRecoveryEpisodeAttemptId = 0;
    uint64 NativeRecoveryEpisodeRouteGeneration = 0;
    uint64 NativeRecoveryEpisodeWipeGeneration = 0;
    uint32 NativeRecoveryEpisodeDeathOrdinal = 0;
    std::string NativeRecoveryEpisodePhase = "none";
    uint64 NativeRecoveryEpisodeStartedMs = 0;
    uint64 NativeRecoveryEpisodeLastProgressMs = 0;
    std::string NativeRecoveryEpisodeDistanceTarget = "none";
    float NativeRecoveryEpisodeBestDistance =
        std::numeric_limits<float>::max();
    uint32 NativeRecoveryMovementRetryCount = 0;
    uint32 NativeRecoveryReleaseRejectionCount = 0;
    uint32 NativeRecoveryEntranceUnavailableCount = 0;
    uint32 NativeRecoveryEntranceRejectionCount = 0;
    uint32 NativeRecoveryReclaimRejectionCount = 0;
    bool NativeRecoveryEntranceRequired = false;
    bool NativeRecoveryEntranceObserved = false;
    bool NativeRecoveryEntranceAvailable = false;
    uint64 RecoveryAttemptCount = 0;
    uint64 ValidationRouteGeneration = 11;
    std::string LastRepeatableEventKey;
    uint64 LastRepeatableEventEmitMs = 0;
    uint32 SuppressedRepeatableEventCount = 0;
    uint32 PendingTraceSuppressedRepeatableEventCount = 0;
};

struct ConfigData
{
    std::string DeathRecoveryMode = "native_corpse_run";
    std::string ValidationRouteNodeId = "drudges";
};

struct RaidRuntime
{
    uint64 WipeGeneration = 3;
};

struct TelemetryBufferData
{
    uint64 GetActiveClipId(uint64) const
    {
        return 0;
    }
};

struct CohortRuntime
{
    uint64 AttemptId = 7;
    uint64 ValidationRouteGeneration = 11;
    uint64 RunId = 0;
    RaidRuntime Raid;
    ConfigData Config;
    TelemetryBufferData TelemetryBuffer;
};

struct PartyRuntime
{
    uint64 ValidationRouteGeneration = 11;
};

struct TraceRow
{
    std::string Event;
    std::string Result;
    uint32 Suppressed = 0;
};

class Fixture
{
public:
    WorldBotState State;
    CohortRuntime CohortState;
    PartyRuntime PartyState;
    std::vector<std::string> RecoveryStarts;
    std::vector<TraceRow> TraceRows;

    CohortRuntime& Cohort()
    {
        return CohortState;
    }

    PartyRuntime& Party()
    {
        return PartyState;
    }

    std::string BuildRawJson(Player*, Target*) const
    {
        return "{}";
    }

    std::string BuildSemanticJson(Player*, Target*, char const*) const
    {
        return "{}";
    }

    void RecordEvent(WorldBotState&, Player*, char const* event,
        Target const*, char const* result, char const*, char const*,
        float, uint32)
    {
        if (std::string(event ? event : "") == "death_recovery_started")
            RecoveryStarts.push_back(result ? result : "");
    }

    void RecordDecisionTrace(WorldBotState& state, char const* event,
        char const*, Target const*, uint32, char const* result,
        char const*)
    {
        TraceRows.push_back({ event ? event : "", result ? result : "",
            state.PendingTraceSuppressedRepeatableEventCount });
    }

    void RecordExperimentSegmentEvent(Player*, char const*, char const*,
        uint32, Target const*, uint64, char const*, char const*)
    {
    }

    void ObserveRecoveryEpisode(Player* bot, uint64 atMs,
        uint64 attempt, uint64 route, uint64 wipe, uint32 death)
    {
        gNowMs = atMs;
        Cohort().AttemptId = attempt;
        Party().ValidationRouteGeneration = route;
        Cohort().Raid.WipeGeneration = wipe;
        State.RecentDeathCount = death;
        WorldBotState& state = State;
        (void)bot;
__RECOVERY_SEGMENT__
    }

    void RecordProgress(Player* bot, char const* event,
        char const* result, uint32 valueInt, uint32 spellId)
    {
        std::string observedEvent = event ? event : "unknown";
        std::string observedResult = result ? result : "";
        Target const* target = nullptr;
        char const* eventType = event;
        char const* resultValue = result;
        char const* rawJson = "{}";
        char const* semanticJson = "{}";
        WorldBotState& state = State;
        (void)eventType;
        (void)resultValue;
__EVENT_SEGMENT__
    }
};

int main()
{
    Fixture fixture;
    Player bot;

    // The same scoped episode may be observed for 100 recovery ticks, but
    // episode start and attempt accounting occur exactly once.
    fixture.ObserveRecoveryEpisode(&bot, 1000, 7, 11, 3, 1);
    assert(fixture.RecoveryStarts.size() == 1);
    assert(fixture.State.RecoveryAttemptCount == 1);
    fixture.State.NativeRecoveryEpisodePhase = "moving_to_entrance";
    fixture.State.NativeRecoveryEpisodeLastProgressMs = 777;
    fixture.State.NativeRecoveryEpisodeDistanceTarget = "entrance";
    fixture.State.NativeRecoveryEpisodeBestDistance = 12.5f;
    for (uint64 tick = 0; tick < 99; ++tick)
        fixture.ObserveRecoveryEpisode(&bot, 1001 + tick, 7, 11, 3, 1);
    assert(fixture.RecoveryStarts.size() == 1);
    assert(fixture.State.RecoveryAttemptCount == 1);
    assert(fixture.State.NativeRecoveryEpisodePhase
        == "moving_to_entrance");
    assert(fixture.State.NativeRecoveryEpisodeLastProgressMs == 777);
    assert(fixture.State.NativeRecoveryEpisodeDistanceTarget == "entrance");
    assert(fixture.State.NativeRecoveryEpisodeBestDistance == 12.5f);

    // The first observed identity change opens one new episode, regardless of
    // whether it is attempt, route, wipe, or death scope.
    fixture.ObserveRecoveryEpisode(&bot, 2000, 8, 11, 3, 1);
    fixture.ObserveRecoveryEpisode(&bot, 3000, 8, 12, 3, 1);
    fixture.ObserveRecoveryEpisode(&bot, 4000, 8, 12, 4, 1);
    fixture.ObserveRecoveryEpisode(&bot, 5000, 8, 12, 4, 2);
    assert(fixture.RecoveryStarts.size() == 5);
    assert(fixture.State.RecoveryAttemptCount == 5);
    assert(fixture.State.NativeRecoveryEpisodeStartedMs == 5000);
    assert(fixture.State.NativeRecoveryEpisodePhase == "release_pending");

    // A terminal phase is retained for the matching identity and cannot be
    // mistaken for a fresh episode on a later recovery tick.
    fixture.State.NativeRecoveryEpisodePhase = "terminal";
    fixture.State.NativeRecoveryEpisodeLastProgressMs = 5555;
    fixture.ObserveRecoveryEpisode(&bot, 6000, 8, 12, 4, 2);
    assert(fixture.RecoveryStarts.size() == 5);
    assert(fixture.State.RecoveryAttemptCount == 5);
    assert(fixture.State.NativeRecoveryEpisodePhase == "terminal");
    assert(fixture.State.NativeRecoveryEpisodeLastProgressMs == 5555);

    // Same-result progress is bounded to an edge plus a five-second
    // heartbeat; changing the result or recovery identity emits immediately.
    fixture.State.ValidationRouteGeneration = 11;
    fixture.Cohort().Config.ValidationRouteNodeId = "drudges";
    gNowMs = 7000;
    fixture.RecordProgress(&bot, "death_recovery_progress",
        "native_instance_runback_in_progress", 1, 0);
    for (uint64 tick = 0; tick < 99; ++tick)
    {
        gNowMs = 7001 + tick;
        fixture.RecordProgress(&bot, "death_recovery_progress",
            "native_instance_runback_in_progress", 1, 0);
    }
    assert(fixture.TraceRows.size() == 1);
    gNowMs = 12000;
    fixture.RecordProgress(&bot, "death_recovery_progress",
        "native_instance_runback_in_progress", 1, 0);
    assert(fixture.TraceRows.size() == 2);
    assert(fixture.TraceRows[1].Suppressed == 100);

    gNowMs = 12100;
    fixture.RecordProgress(&bot, "death_recovery_progress",
        "native_instance_runback_no_progress", 1, 0);
    assert(fixture.TraceRows.size() == 3);
    gNowMs = 12200;
    fixture.RecordProgress(&bot, "death_recovery_started",
        "native_corpse_run", 1, 0);
    gNowMs = 12300;
    fixture.RecordProgress(&bot, "death_recovery_failed",
        "native_runback_no_progress", 1, 0);
    assert(fixture.TraceRows.size() == 5);

    fixture.State.NativeRecoveryEpisodeAttemptId = 9;
    fixture.State.NativeRecoveryEpisodeRouteGeneration = 13;
    fixture.State.NativeRecoveryEpisodeWipeGeneration = 5;
    fixture.State.NativeRecoveryEpisodeDeathOrdinal = 3;
    fixture.State.NativeRecoveryEpisodeStartedMs = 13000;
    gNowMs = 12400;
    fixture.RecordProgress(&bot, "death_recovery_progress",
        "native_instance_runback_in_progress", 1, 0);
    assert(fixture.TraceRows.size() == 6);

    fixture.State.NativeRecoveryEpisodeAttemptId = 10;
    gNowMs = 12500;
    fixture.RecordProgress(&bot, "death_recovery_progress",
        "native_instance_runback_in_progress", 1, 0);
    fixture.State.NativeRecoveryEpisodeRouteGeneration = 14;
    gNowMs = 12600;
    fixture.RecordProgress(&bot, "death_recovery_progress",
        "native_instance_runback_in_progress", 1, 0);
    fixture.State.NativeRecoveryEpisodeWipeGeneration = 6;
    gNowMs = 12700;
    fixture.RecordProgress(&bot, "death_recovery_progress",
        "native_instance_runback_in_progress", 1, 0);
    fixture.State.NativeRecoveryEpisodeDeathOrdinal = 4;
    gNowMs = 12800;
    fixture.RecordProgress(&bot, "death_recovery_progress",
        "native_instance_runback_in_progress", 1, 0);
    assert(fixture.TraceRows.size() == 10);
}
'''
    source.write_text(
        harness.replace("__RECOVERY_SEGMENT__", recovery_segment)
        .replace("__EVENT_SEGMENT__", event_segment),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)
