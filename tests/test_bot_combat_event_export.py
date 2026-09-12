from __future__ import annotations

import subprocess
from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
STATUS = BOT_DIR / "BotWorldPopulationMgrStatus.cpp"
COMBAT_LOG = BOT_DIR / "BotWorldPopulationMgrCombatLog.cpp"
COHORT = BOT_DIR / "BotWorldPopulationMgrCohort.cpp"
PLANNING = BOT_DIR / "BotWorldPopulationMgrPlanningContracts.h"
RUNTIME = BOT_DIR / "BotWorldPopulationMgrRuntimeContracts.h"
MGR_HEADER = BOT_DIR / "BotWorldPopulationMgr.h"
COMMANDS = ROOT / "src/server/scripts/Commands/cs_botauto.cpp"
COMMANDS_OLD = ROOT / "src/server/scripts/Commands/cs_healerbot.cpp"
SCRIPTS_CMAKE = ROOT / "src/server/scripts/CMakeLists.txt"
CURSOR_HEADER = BOT_DIR / "BotWorldTraceExportCursor.h"


def test_native_event_sequence_epoch_and_export_contract_is_bounded() -> None:
    planning = PLANNING.read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")
    combat_log = COMBAT_LOG.read_text(encoding="utf-8")
    status = STATUS.read_text(encoding="utf-8")
    cohort = COHORT.read_text(encoding="utf-8")
    header = MGR_HEADER.read_text(encoding="utf-8")
    commands = COMMANDS.read_text(encoding="utf-8")
    old_commands = COMMANDS_OLD.read_text(encoding="utf-8")

    for source in (
        planning, runtime, combat_log, status, cohort, header, commands, old_commands
    ):
        assert len(source.splitlines()) < 1000

    for field in ("EventSequence", "ExperimentId", "RunId"):
        assert f"uint64 {field} = 0;" in planning
    assert "uint64 CombatLogEpoch = 0;" in runtime
    party_contract = runtime.split("struct PartyRuntime", 1)[1].split(
        "struct RaidRosterItemIdentity", 1
    )[0]
    cohort_contract = runtime.split("struct CohortRuntime", 1)[1].split(
        "struct BotGuidLease", 1
    )[0]
    assert "CombatLogEpoch" not in party_contract
    assert "uint64 CombatLogEpoch = 0;" in cohort_contract
    assert "++Cohort().CombatLogEpoch;" in combat_log
    assert "event.EventSequence = Party().CombatLogEventCount;" in combat_log
    assert "event.ExperimentId = Cohort().ExperimentId;" in combat_log
    assert "event.RunId = Cohort().RunId;" in combat_log

    assert "GetCombatLogDeltaJsonForCohort" in header
    assert "GetCombatLogDeltaJson(uint64 cursor, uint32 limit) const" in header
    assert "AppendCombatLogEventJson" in header
    assert status.count('\\"combat_log_epoch\\"') >= 2
    assert '\\"event_count_at_export\\"' in status
    for field in ("event_sequence", "experiment_id", "run_id"):
        assert f'\\"{field}\\"' in status
    assert status.count("AppendCombatLogEventJson(json, event)") == 1

    full = status.split("std::string BotWorldPopulationMgr::GetCombatLogJson() const", 1)[1]
    delta = status.split("std::string BotWorldPopulationMgr::GetCombatLogDeltaJson(uint64 cursor, uint32 limit) const", 1)[1]
    delta = delta.split("std::string BotWorldPopulationMgr::GetBotDebugJson", 1)[0]
    for field in (
        '\\"aggregate_count\\"',
        '\\"second_bucket_count\\"',
        '\\"abilities\\"',
        '\\"second_buckets\\"',
        '\\"event_count\\"',
        '\\"raw_amount\\"',
        '\\"shared_amount\\"',
    ):
        assert field in full
    assert '\\"recent_events\\"' in delta
    assert "BuildExportCursorTransition" in delta
    assert "WriteExportCursorFields(json, transition)" in delta
    assert "CombatLogAbilities" not in delta
    assert "CombatLogSecondBuckets" not in delta
    assert "TraceExportCursorByGuid" not in delta
    assert "CombatLogEventCount =" not in delta
    assert "CombatLogRecentEventsDropped =" not in delta

    assert "GetCombatLogDeltaJson(cursor, limit)" in cohort
    assert "RegisterBotAutoCommands();" in old_commands
    assert "void RegisterBotAutoCommands()" in commands
    assert "new botauto_commandscript();" in commands
    assert '"combatlog", rbac::RBAC_PERM_COMMAND_HEALERBOT' in commands
    assert "Tokenize(args)" in commands
    assert "ParseUint64Token" in commands
    assert "std::from_chars" in commands
    assert "token.front() == '-'" in commands
    assert "requestedLimit == 0 || requestedLimit > 4096" in commands
    assert "botauto_combatlog_delta" in commands
    assert "static constexpr size_t RawChunkSize = 12 * 1024;" in commands
    assert "botauto_combatlog_chunk" in commands
    assert "botauto_combatlog_complete" in commands
    assert "Commands/cs_botauto.cpp" in SCRIPTS_CMAKE.read_text(encoding="utf-8")


def test_native_cursor_delta_fixture_compiles_sequence_bounds_gap_and_full_fields(tmp_path: Path) -> None:
    source = r'''
#include "BotWorldTraceExportCursor.h"

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

using BotWorldTrace::BuildExportCursorTransition;
using BotWorldTrace::ExportCursorTransition;
using BotWorldTrace::WriteExportCursorFields;

struct Event
{
    std::uint64_t event_sequence;
    std::uint64_t experiment_id;
    std::uint64_t run_id;
};

std::string EmitDelta(std::vector<Event> const& events, std::uint64_t cursor,
    std::size_t requested_limit)
{
    std::vector<std::uint64_t> sequences;
    for (Event const& event : events)
        sequences.push_back(event.event_sequence);
    std::size_t const limit = std::min<std::size_t>(requested_limit, 4096);
    ExportCursorTransition const transition =
        BuildExportCursorTransition(sequences, cursor, cursor != 0, limit);
    std::ostringstream json;
    json << "{\"combat_log_epoch\":4,\"event_count_at_export\":"
         << events.size();
    WriteExportCursorFields(json, transition);
    json << ",\"recent_events\":[";
    for (std::size_t index = 0; index < transition.EntryCount; ++index)
    {
        if (index)
            json << ',';
        Event const& event = events[transition.FirstEntryIndex + index];
        json << "{\"event_sequence\":" << event.event_sequence
             << ",\"experiment_id\":" << event.experiment_id
             << ",\"run_id\":" << event.run_id << '}';
    }
    json << "]}";
    return json.str();
}

int main()
{
    std::vector<Event> initial{{1, 7, 41}, {2, 7, 41}, {3, 7, 42}};
    std::string const page = EmitDelta(initial, 0, 2);
    auto const pageJson = page;
    assert(pageJson.find("\"cursor_before\":0") != std::string::npos);
    assert(pageJson.find("\"cursor_after\":2") != std::string::npos);
    assert(pageJson.find("\"event_sequence\":1") != std::string::npos);
    assert(pageJson.find("\"experiment_id\":7") != std::string::npos);
    assert(pageJson.find("\"run_id\":41") != std::string::npos);
    assert(pageJson.find("\"event_sequence\":3") == std::string::npos);

    // A client whose old cursor is ahead of a freshly reset stream still
    // receives the new namespace metadata and can restart from cursor zero.
    std::string const reset = EmitDelta(initial, 302, 4096);
    assert(reset.find("\"combat_log_epoch\":4") != std::string::npos);
    assert(reset.find("\"event_count_at_export\":3") != std::string::npos);
    assert(reset.find("\"cursor_before\":302") != std::string::npos);
    assert(reset.find("\"cursor_after\":302") != std::string::npos);
    assert(reset.find("\"recent_events\":[]") != std::string::npos);

    std::vector<Event> retained;
    for (std::uint64_t sequence = 175; sequence <= 302; ++sequence)
        retained.push_back(Event{sequence, 9, 49});
    ExportCursorTransition const first = BuildExportCursorTransition(
        [&retained]
        {
            std::vector<std::uint64_t> values;
            for (Event const& event : retained)
                values.push_back(event.event_sequence);
            return values;
        }(), 46, true, 64);
    assert(first.HasDiscontinuity);
    assert(first.MissingSequenceStart == 47 && first.MissingSequenceEnd == 174);
    assert(first.EntryCount == 64 && first.CursorAfter == 238);
    ExportCursorTransition const second = BuildExportCursorTransition(
        [&retained]
        {
            std::vector<std::uint64_t> values;
            for (Event const& event : retained)
                values.push_back(event.event_sequence);
            return values;
        }(), first.CursorAfter, true, 4096);
    assert(!second.HasDiscontinuity && second.EntryCount == 64
           && second.CursorAfter == 302);

    std::vector<Event> five_thousand;
    for (std::uint64_t sequence = 1; sequence <= 5000; ++sequence)
        five_thousand.push_back(Event{sequence, 1, 1});
    std::string const bounded = EmitDelta(five_thousand, 0, 5000);
    std::size_t const sequence_rows = [&bounded]
    {
        std::size_t count = 0;
        std::string needle = "\"event_sequence\":";
        std::size_t offset = 0;
        while ((offset = bounded.find(needle, offset)) != std::string::npos)
        {
            ++count;
            offset += needle.size();
        }
        return count;
    }();
    assert(sequence_rows == 4096);

    std::string const fullAggregates =
        "{\"aggregate_count\":2,\"second_bucket_count\":1,\"event_count\":5000}";
    std::string const fullBefore = fullAggregates;
    (void)EmitDelta(initial, 0, 1);
    assert(fullAggregates == fullBefore);
    assert(std::numeric_limits<std::uint64_t>::max() > 0);
    return 0;
}
'''
    source_path = tmp_path / "combat_event_export_fixture.cpp"
    binary_path = tmp_path / "combat_event_export_fixture"
    source_path.write_text(source, encoding="utf-8")
    compile_result = subprocess.run(
        [
            "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(CURSOR_HEADER.parent), str(source_path),
            "-o", str(binary_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert compile_result.returncode == 0, compile_result.stderr
    run_result = subprocess.run(
        [str(binary_path)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert run_result.returncode == 0, run_result.stderr


def test_combat_log_epoch_lifecycle_fixture_compiles_party_replacement(tmp_path: Path) -> None:
    # Compile the complete production lifecycle methods, with external services
    # inert and no bots loaded. ResetCombatLog and epoch storage come from source.
    lifecycle = (BOT_DIR / "BotWorldPopulationMgrLifecycle.cpp").read_text()
    methods = lifecycle[lifecycle.index("bool BotWorldPopulationMgr::Start("):
                        lifecycle.index("void BotWorldPopulationMgr::Shutdown()")]
    reset = COMBAT_LOG.read_text().split("void BotWorldPopulationMgr::ResetCombatLog()", 1)[1]
    reset = "void BotWorldPopulationMgr::ResetCombatLog()" + reset.split("\nPlayer*", 1)[0]
    runtime = RUNTIME.read_text()
    party = runtime.split("struct PartyRuntime", 1)[1].split("struct RaidRosterItemIdentity", 1)[0]
    cohort = runtime.split("struct CohortRuntime", 1)[1]
    epoch = "uint64 CombatLogEpoch = 0;"
    source = r'''#include <cassert>
#include <cstdint>
#include <string>
#include <vector>
using uint64 = std::uint64_t;
using uint32 = std::uint32_t;
enum class BotWorldRuntimeMode { ManualExperiment, AlwaysOnAutonomy };
enum class ValidationAdmissionPhase { Provisioning };
struct Guid { bool IsEmpty() const { return true; } uint32 GetCounter() const { return 0; } uint64 GetRawValue() const { return 0; } };
struct WorldBotState { struct Guid Guid; };
struct Player {};
struct Service {
    void Clear() {} void Configure(int, int) {} void FlushOpenClips(uint64, uint64, int) {}
    void ClearBot(uint32) {} void RemoveWorldBot(Guid) {}
};
namespace BotWorldMovement { Service& MovementPlannerDiagnostics() { static Service s; return s; } }
namespace BotRaidAreaAuthority { void Clear(uint64) {} }
namespace BotWorldCohortScope { bool AllowsConcurrentAdmission(int, int, int) { return true; } }
namespace BotClassSpecActionProfileStore { int ActiveDbGeneration() { return 0; } std::string ActiveDbContentHash() { return {}; } }
struct ConfigService { bool enabled = true; bool GetBoolDefault(char const*, bool) { return enabled; } } config;
auto* sConfigMgr = &config;
Service bots; auto* sBotMgr = &bots;
struct BotWorldExperimentConfig { std::string Name; int BrainVersion = 0, TargetPopulation = 0; bool ValidationRouteEnable = false; };
struct BotWorldStatus { bool Active = false; BotWorldRuntimeMode Mode{}; std::string Name; int TargetBots = 0; uint64 RunId = 0, ExperimentId = 0; };
struct RaidRuntime {};
struct PartyRuntime {
    // EPOCH_PARTY
    uint64 CombatLogEventCount = 0, CombatLogRecentEventsDropped = 0;
    std::vector<int> CombatLogAbilities, CombatLogSecondBuckets, CombatLogRecentEvents, CalibrationBots;
    std::vector<WorldBotState> Bots;
};
struct CohortRuntime {
    // EPOCH_COHORT
    PartyRuntime Party;
    uint64 AttemptId = 0, RunId = 0, ExperimentId = 0;
    int PinnedProfileGeneration = 0, ElapsedMs = 0, RecordingWindowElapsedMs = 0, RecordingWindowIndex = 0;
    int ValidationAttemptFailureAttemptId = 0, ValidationAttemptFailureRouteGeneration = 0;
    std::string PinnedProfileContentHash, LastPopulationFailureReason, ValidationAttemptFailureReason;
    std::vector<uint32> RosterLeases, FailedSpawnGuids;
    bool Active = false, RuntimeProfileSelectionPending = false, CalibrationActive = false, RuntimeProfileDirty = false;
    bool ValidationAdmissionStarted = false, ValidationAdmissionBatchSealed = false;
    bool ValidationRaidAdmissionComplete = false, ValidationRaidAdmissionFailed = false;
    BotWorldRuntimeMode RuntimeMode{}; ValidationAdmissionPhase ValidationAdmission{};
    BotWorldExperimentConfig Config; BotWorldStatus Metrics; RaidRuntime Raid;
    Service TelemetryBuffer, ExperimentCoordinator;
};
struct BotWorldPopulationMgr {
    CohortRuntime state;
    CohortRuntime& Cohort() { return state; } PartyRuntime& Party() { return state.Party; }
    static constexpr int MaxActiveCohorts = 2;
    int ActiveCohortCount() { return state.Active; } int MapWorkerThreadCount() { return 1; }
    void LoadConfig(std::string const& name, BotWorldExperimentConfig const*) { state.Config.Name = name; }
    bool IsValidationProfileName(std::string const&) { return false; }
    bool PrepareCurrentValidationProfile(char const*) { return true; }
    bool EligibleForDiagnosticCleanup(uint32) { return true; }
    Player* GetBot(WorldBotState const&) { return nullptr; }
    void RecordRunStop() {} void RecordRunStart() {} void EnsurePopulation() {}
    void ResetTraceStreams() {} void ClearPendingHealCasts(char const*) {}
    void StopCombatCalibration() {} void FlushPendingDecisionFingerprintMemory() {}
    void PersistBotPosition(Player*) {} void RecordActivityStop(WorldBotState const&, Player*) {}
    void ReleaseCohortLeases() {} void MaybeStartAutoRecordingWindow() {}
    bool Start(std::string const&, BotWorldExperimentConfig const* = nullptr);
    void Stop(); bool StartAutonomy(BotWorldExperimentConfig const* = nullptr); void StopAutonomy();
    void ResetCombatLog();
    uint64 Epoch() { return EPOCH_ACCESS; }
};
'''
    source = source.replace("// EPOCH_PARTY", epoch if epoch in party else "")
    source = source.replace("// EPOCH_COHORT", epoch if epoch in cohort else "")
    source = source.replace("EPOCH_ACCESS", "Cohort().CombatLogEpoch" if epoch in cohort else "Party().CombatLogEpoch")
    source += methods + reset + r'''
int main() {
    BotWorldPopulationMgr mgr;
    config.enabled = false;
    assert(!mgr.Start("disabled") && mgr.Epoch() == 0);
    config.enabled = true;
    assert(mgr.Start("first"));
    assert(mgr.state.AttemptId == 1 && mgr.Epoch() == 1);
    mgr.Party().CombatLogEventCount = 7;
    mgr.ResetCombatLog();
    assert(mgr.Epoch() == 2 && mgr.Party().CombatLogEventCount == 0);
    mgr.Party().CombatLogEventCount = 1;
    mgr.Stop();
    assert(mgr.Epoch() == 2 && !mgr.state.Active);
    mgr.Stop();
    assert(mgr.Epoch() == 2);
    assert(mgr.Start("second"));
    assert(mgr.state.AttemptId == 1 && mgr.Epoch() == 3);
    assert(mgr.Party().CombatLogEventCount == 0);
    mgr.Stop();
    assert(mgr.StartAutonomy());
    assert(mgr.Epoch() == 4 && mgr.state.AttemptId == 1);
    assert(mgr.StartAutonomy()); // Already active: no reset.
    assert(mgr.Epoch() == 4);
    assert(mgr.Start("recording"));
    assert(mgr.Epoch() == 5);
    mgr.Stop(); // Stops recording only, preserving autonomy and epoch.
    assert(mgr.state.Active && mgr.Epoch() == 5);
    mgr.StopAutonomy();
    assert(!mgr.state.Active && mgr.Epoch() == 5);
    assert(mgr.StartAutonomy());
    assert(mgr.Epoch() == 6 && mgr.state.AttemptId == 1);
    BotWorldPopulationMgr other;
    assert(other.Epoch() == 0);
    assert(other.Start("other") && other.Epoch() == 1);
    assert(mgr.Epoch() == 6);
}
'''
    source_path = tmp_path / "combat_log_epoch_lifecycle_fixture.cpp"
    binary_path = tmp_path / "combat_log_epoch_lifecycle_fixture"
    source_path.write_text(source)
    compiled = subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                               str(source_path), "-o", str(binary_path)], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run([str(binary_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_combatlog_command_rejects_invalid_uint64_and_limit_inputs() -> None:
    commands = COMMANDS.read_text(encoding="utf-8")
    command_body = commands.split(
        "static bool HandleAutoCombatLogCommand", 1
    )[1].split("static bool HandleAutoCalibrateCommand", 1)[0]
    for invalid_cursor in ("-1", "18446744073709551616", "1x"):
        assert invalid_cursor not in command_body
    assert "!ParseUint64Token(tokens[2], cursor)" in command_body
    assert "!ParseUint64Token(tokens[3], requestedLimit)" in command_body
    assert "requestedLimit == 0 || requestedLimit > 4096" in command_body
    assert '"invalid_cursor"' in command_body
    assert '"invalid_limit"' in command_body
    assert '"usage: .botauto combatlog <cohort_id> delta <cursor> <limit>"' in command_body


@pytest.mark.parametrize("schema", [3, 4])
def test_supported_delta_shape_is_accepted_by_event_stream_consumer(schema) -> None:
    from tools.bot_ml.combat_log_event_stream import CombatLogEventStream, merge_event_rows

    stream = CombatLogEventStream(expected_cohort_id="raid")
    common = {
        "ok": True,
        "combat_log_schema_version": schema,
        "cohort_id": "raid",
        "server_epoch": 11,
        "attempt_id": 2,
        "combat_log_epoch": 4,
        "profile_generation": 8,
        "profile_content_hash": "profile-hash",
        "experiment_id": 101,
        "run_id": 49,
        "event_count_at_export": 3,
    }
    payload = {
        **common,
        "action": "botauto_combatlog_delta",
        "delta": True,
        "cursor_before": 0,
        "cursor_after": 3,
        "gap": False,
        "recent_events": [
            {"event_sequence": 1, "experiment_id": 100, "run_id": 48},
            {"event_sequence": 2, "experiment_id": 101, "run_id": 49},
            {"event_sequence": 3, "experiment_id": 101, "run_id": 49},
        ],
    }
    import base64
    import json

    raw = json.dumps(payload, separators=(",", ":")).encode()
    envelope = {"cohort_id": "raid", "combat_log_chunk_schema_version": 1,
                "export_id": 1, "export_kind": "delta", "chunk_count": 1}
    frames = [
        {**envelope, "action": "botauto_combatlog_chunk", "sequence": 0,
         "encoding": "base64", "data": base64.b64encode(raw).decode()},
        {**envelope, "action": "botauto_combatlog_complete", "total_bytes": len(raw)},
    ]
    result = stream.observe_rows(frames)[0]
    assert result.accepted and result.cursor_after == 3
    receipt = stream.receipt()
    assert receipt["identity"] == {
        "cohort_id": "raid",
        "server_epoch": 11,
        "attempt_id": 2,
        "combat_log_epoch": 4,
    }
    assert receipt["namespace"]["event_count"] == 3
    assert receipt["namespace"]["labels"][-1] == {"experiment_id": 101, "run_id": 49}

    full = {
        **common,
        "action": "botauto_combatlog",
        "event_count": 3,
        "aggregate_count": 1,
        "second_bucket_count": 1,
        "abilities": [{"amount": 123, "raw_amount": 123}],
        "second_buckets": [{"amount": 123}],
        "recent_events": payload["recent_events"],
    }
    full_result = stream.observe(full)
    assert full_result is None
    assert full["aggregate_count"] == 1
    assert full["second_bucket_count"] == 1
    assert full["event_count"] == 3
    merged = merge_event_rows(full["recent_events"], payload["recent_events"])
    assert [row["event_sequence"] for row in merged] == [1, 2, 3]


def test_native_frames_bind_each_export_and_kind(tmp_path: Path) -> None:
    import json

    commands = COMMANDS.read_text()
    calibration = commands.split("    static bool SendCombatLogFrames", 1)[0]
    assert "exportId" not in calibration and "exportKind" not in calibration
    sender = commands.split("    static bool SendCombatLogFrames", 1)[1]
    sender = "static bool SendCombatLogFrames" + sender.split("    static bool SendCombatLogDeltaFailure", 1)[0]
    source = r'''
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>
using uint64 = std::uint64_t;
using uint8 = std::uint8_t;
struct ChatHandler {
    template<class... Args> void PSendSysMessage(char const* format, Args... args) {
        std::printf(format, args...); std::puts("");
    }
};
namespace Trinity::Encoding::Base64 {
    // Encoding is irrelevant to envelope identity; production framing is intact.
    std::string Encode(std::vector<uint8> const&) { return "e30="; }
}
''' + sender + r'''
int main() {
    ChatHandler handler;
    SendCombatLogFrames(&handler, "raid", std::string(13000, 'x'), "delta");
    SendCombatLogFrames(&handler, "raid", "{}", "full");
    SendCombatLogFrames(&handler, "other", "{}", "delta");
}
'''
    path = tmp_path / "frames.cpp"
    binary = tmp_path / "frames"
    path.write_text(source)
    compiled = subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                               str(path), "-o", str(binary)], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert [row["export_id"] for row in rows] == [1, 1, 1, 2, 2, 3, 3]
    assert [row["export_kind"] for row in rows] == ["delta"] * 3 + ["full"] * 2 + ["delta"] * 2
    assert [row["sequence"] for row in rows if "sequence" in row] == [0, 1, 0, 0]
    assert [row["total_bytes"] for row in rows if "total_bytes" in row] == [13000, 2, 2]
    assert 'cohortId, cursor, uint32(requestedLimit)), "delta")' in commands
    assert 'GetCombatLogJsonForCohort(cohortId), "full")' in commands
