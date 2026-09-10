from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BOT_ROOT = ROOT / "src/server/game/Bots"
MODULE = BOT_ROOT / "BotWorldPopulationMgrTraceTransportTest.cpp"
STATUS = BOT_ROOT / "BotWorldPopulationMgrStatus.cpp"
COMMAND = ROOT / "src/server/scripts/Commands/cs_trace_transport_test.cpp"
CAPTURE = ROOT / "tools/raid_program/capture_live_run.py"


def test_trace_pressure_gate_compiles_and_rejects_every_adjacent_lane(tmp_path: Path):
    replay = tmp_path / "trace_transport_test_gate.cpp"
    binary = tmp_path / "trace_transport_test_gate"
    replay.write_text(
        r'''
#include "Bots/BotWorldTraceTransportTest.h"

#include <cstring>

using namespace BotWorldTraceTransportTest;

GateInput accepted()
{
    GateInput input;
    input.Active = true;
    input.SelectedProfile = ProfileName;
    input.ConfigName = ProfileName;
    input.PoolTagFilter = PoolTag;
    input.TargetPopulation = ActorCount;
    input.ActiveActorCount = ActorCount;
    input.AttemptId = 7;
    input.RequestedCount = MinimumPressureCount;
    return input;
}

int main()
{
    GateInput input = accepted();
    if (RejectionReason(input))
        return 1;
    input.AllowCombat = true;
    if (std::strcmp(RejectionReason(input), "trace_transport_test_non_gameplay_gate_failed"))
        return 2;
    input = accepted();
    input.ValidationRouteEnabled = true;
    if (std::strcmp(RejectionReason(input), "trace_transport_test_non_gameplay_gate_failed"))
        return 3;
    input = accepted();
    input.SelectedProfile = "blackwing_descent_10n";
    if (std::strcmp(RejectionReason(input), "trace_transport_test_profile_required"))
        return 4;
    input = accepted();
    input.PressureAppliedAttemptId = input.AttemptId;
    if (std::strcmp(RejectionReason(input), "trace_transport_test_pressure_already_applied"))
        return 5;
    input = accepted();
    input.RequestedCount = MaximumPressureCount + 1;
    if (std::strcmp(RejectionReason(input), "trace_transport_test_pressure_count_out_of_bounds"))
        return 6;
    return 0;
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++", "-std=c++17", "-I", str(ROOT / "src/common"),
            "-I", str(ROOT / "src/server/game"), str(replay), "-o", str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_pressure_uses_real_writer_and_has_no_gameplay_or_persistence_writer():
    source = MODULE.read_text(encoding="utf-8")
    assert "RecordDecisionTrace(state" in source
    assert '"append_inert_trace_record"' in source
    assert "TraceTransportTestPressureAttemptId = Cohort().AttemptId" in source
    assert all(token not in source for token in (
        "CharacterDatabase", "WorldDatabase", "MovePoint", "CastSpell",
        "TeleportTo", "RemoveWorldBot", "PersistBotPosition",
    ))
    assert len(source.splitlines()) < 1000


def test_generic_identity_declares_fields_and_raid_runtime_stays_separate():
    module = MODULE.read_text(encoding="utf-8")
    status = STATUS.read_text(encoding="utf-8")
    assert all(field in module for field in (
        "cohort_id", "server_epoch", "attempt_id", "profile_generation",
        "profile_content_hash", "active_profile",
    ))
    assert status.count("BuildRaidRuntimeJson(true)") >= 3


def test_command_adapter_is_small_unique_and_controller_sends_pressure_once():
    command = COMMAND.read_text(encoding="utf-8")
    capture = CAPTURE.read_text(encoding="utf-8")
    assert '"botautotracepressure"' in command
    assert "ApplyTraceTransportTestPressureForCohort" in command
    assert len(command.splitlines()) < 1000
    assert capture.count("trace_transport_smoke.PRESSURE_COMMAND") == 1
    pressure_send = capture.index("trace_transport_smoke.PRESSURE_COMMAND")
    first_delta_schedule = capture.index("telemetry_scheduler.commands_due")
    assert pressure_send < first_delta_schedule


def test_command_adapter_passes_four_digit_pressure_to_manager(tmp_path: Path):
    include = tmp_path / "include"
    (include / "Bots").mkdir(parents=True)
    (include / "Bots/BotWorldPopulationMgr.h").write_text(
        r'''
#pragma once
#include <cstdint>
#include <string>
using uint32 = std::uint32_t;
class BotWorldPopulationMgr
{
public:
    std::string ResolveGlobalCohortId() { return "default"; }
    std::string ApplyTraceTransportTestPressureForCohort(
        std::string const&, uint32 count)
    {
        LastRequestedCount = count;
        return "{}";
    }
    uint32 LastRequestedCount = 0;
};
extern BotWorldPopulationMgr* sBotWorldPopulationMgr;
''',
        encoding="utf-8",
    )
    (include / "Chat.h").write_text(
        r'''
#pragma once
class ChatHandler
{
public:
    void SendSysMessage(char const*) { }
};
''',
        encoding="utf-8",
    )
    (include / "RBAC.h").write_text(
        r'''
#pragma once
namespace rbac { constexpr int RBAC_PERM_COMMAND_HEALERBOT = 1; }
''',
        encoding="utf-8",
    )
    (include / "ScriptMgr.h").write_text(
        r'''
#pragma once
#include "Chat.h"
#include <vector>
struct ChatCommand
{
    char const* Name;
    int Permission;
    bool AllowConsole;
    bool (*Handler)(ChatHandler*, char const*);
    char const* Help;
};
class CommandScript
{
public:
    explicit CommandScript(char const*) { }
    virtual ~CommandScript() = default;
    virtual std::vector<ChatCommand> GetCommands() const = 0;
};
''',
        encoding="utf-8",
    )
    replay = tmp_path / "trace_transport_command.cpp"
    binary = tmp_path / "trace_transport_command"
    replay.write_text(
        f'''
#include "{COMMAND}"

BotWorldPopulationMgr Manager;
BotWorldPopulationMgr* sBotWorldPopulationMgr = &Manager;

int main()
{{
    trace_transport_test_commandscript script;
    ChatHandler handler;
    auto command = script.GetCommands().at(0);
    if (!command.Handler(&handler, "4097") || Manager.LastRequestedCount != 4097)
        return 1;
    if (!command.Handler(&handler, " 4160 ") || Manager.LastRequestedCount != 4160)
        return 2;
    if (!command.Handler(&handler, "10000") || Manager.LastRequestedCount != 0)
        return 3;
    return 0;
}}
''',
        encoding="utf-8",
    )
    subprocess.run(
        ["c++", "-std=c++17", "-I", str(include), str(replay), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)
