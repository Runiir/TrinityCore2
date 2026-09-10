from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.raid_program.capture_telemetry_transport import TelemetryScheduler


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
TRACE = BOT_DIR / "BotWorldPopulationMgrDecisionTrace.cpp"
TRACE_JSON = BOT_DIR / "BotWorldPopulationMgrDecisionTraceJson.h"
DIAGNOSIS = BOT_DIR / "BotWorldPopulationMgrDiagnosis.cpp"
STATUS = BOT_DIR / "BotWorldPopulationMgrStatus.cpp"


def test_trace_context_is_captured_and_both_exports_share_one_encoder() -> None:
    trace = TRACE.read_text(encoding="utf-8")
    diagnosis = DIAGNOSIS.read_text(encoding="utf-8")
    status = STATUS.read_text(encoding="utf-8")
    encoder = TRACE_JSON.read_text(encoding="utf-8")

    for path in (TRACE, TRACE_JSON, DIAGNOSIS, STATUS):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000

    for field in (
        "ActionCategory",
        "RoleGoal",
        "RecommendedBalanceMode",
        "SaturationReason",
        "MechanicFamily",
        "EncounterRoleResponsibility",
        "NextExpectedAction",
    ):
        assert f"entry.{field} = state.Last{field};" in trace
        assert f"entry.{field}" in encoder

    assert diagnosis.count("AppendDecisionTraceEntryJson") == 1
    assert status.count("AppendDecisionTraceEntryJson") == 1
    trace_method = diagnosis.split(
        "std::string BotWorldPopulationMgr::BuildBotTraceEntriesJson", 1
    )[1]
    delta_method = status.split(
        "std::string BotWorldPopulationMgr::GetBotTraceJson", 1
    )[1].split("std::string BotWorldPopulationMgr::GetCombatLogJson", 1)[0]
    for stale_lookup in (
        "MovementPlannerDiagnostics().ForTrace",
        "state.LastActionCategory",
        "state.LastRoleGoal",
        "state.LastRecommendedBalanceMode",
        "state.LastSaturationReason",
        "state.LastMechanicFamily",
        "state.LastEncounterRoleResponsibility",
        "state.LastNextExpectedAction",
    ):
        assert stale_lookup not in trace_method
        assert stale_lookup not in delta_method


def test_frozen_trace_policy_serialization_survives_state_mutation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "decision_trace_immutable_context.cpp"
    binary = tmp_path / "decision_trace_immutable_context"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrDecisionTraceJson.h"
#include "Bots/BotWorldPopulationMgrDecisionTraceCoalescing.h"

#include <cassert>
#include <iostream>
#include <sstream>
#include <string>

namespace BotWorldMovement
{
std::string MovementPlannerObservationJson(MovementPlannerObservation const&)
{
    return "{}";
}
}

using BotWorldPopulationMgrBotState::WorldBotState;

std::string Encode(WorldBotState::DecisionTraceEntry const& entry)
{
    std::ostringstream json;
    BotWorldTrace::AppendDecisionTraceEntryJson(json, entry,
        [](std::string const& value) { return value; },
        [](WorldBotState::CombatAttemptDiagnostic const&) { return "{}"; },
        [](WorldBotState::RouteProgressDiagnostic const&) { return "{}"; });
    return json.str();
}

int main()
{
    WorldBotState mutableState;
    mutableState.LastActionCategory = "damage";
    mutableState.LastRoleGoal = "hold_boss";
    mutableState.LastRecommendedBalanceMode = "raid";
    mutableState.LastSaturationReason = "assigned";
    mutableState.LastMechanicFamily = "mangle";
    mutableState.LastEncounterRoleResponsibility = "burn_head";
    mutableState.LastNextExpectedAction = "cast_fireball";

    WorldBotState::DecisionTraceEntry row;
    row.TimestampMs = 1200;
    row.Sequence = 8;
    row.PolicyObservedAtMs = 1100;
    row.ActionCategory = mutableState.LastActionCategory;
    row.RoleGoal = mutableState.LastRoleGoal;
    row.RecommendedBalanceMode = mutableState.LastRecommendedBalanceMode;
    row.SaturationReason = mutableState.LastSaturationReason;
    row.MechanicFamily = mutableState.LastMechanicFamily;
    row.EncounterRoleResponsibility =
        mutableState.LastEncounterRoleResponsibility;
    row.NextExpectedAction = mutableState.LastNextExpectedAction;

    std::string const fullEncoderBefore = Encode(row);
    mutableState.LastActionCategory = "wait";
    mutableState.LastRoleGoal = "regroup";
    mutableState.LastRecommendedBalanceMode = "role_first";
    mutableState.LastSaturationReason = "mutated";
    mutableState.LastMechanicFamily = "none";
    mutableState.LastEncounterRoleResponsibility = "maintain_role";
    mutableState.LastNextExpectedAction = "decision_tick";
    std::string const fullEncoderAfter = Encode(row);
    std::string const deltaEncoderAfter = Encode(row);

    assert(fullEncoderBefore == fullEncoderAfter);
    assert(fullEncoderAfter == deltaEncoderAfter);
    assert(fullEncoderAfter.find("\"action_category\":\"damage\"")
        != std::string::npos);
    assert(fullEncoderAfter.find("\"mechanic_family\":\"mangle\"")
        != std::string::npos);
    assert(fullEncoderAfter.find("\"policy_observed_at_ms\":1100")
        != std::string::npos);
    assert(fullEncoderAfter.find("\"action_category\":\"wait\"")
        == std::string::npos);

    WorldBotState::DecisionTraceEntry current = row;
    current.TimestampMs = 1300;
    assert(BotWorldTrace::CanCoalesceDecisionTrace(row, current, 0, false));
    assert(!BotWorldTrace::CanCoalesceDecisionTrace(row, current, 8, false));
    assert(!BotWorldTrace::CanCoalesceDecisionTrace(row, current, 0, true));

    row.NativeActor.NativePresent = true;
    row.NativeActor.InWorld = true;
    row.NativeActor.Alive = true;
    row.NativeActor.PositionAvailable = true;
    row.NativeActor.X = 1.0f;
    row.NativeActor.Y = 2.0f;
    row.NativeActor.Z = 3.0f;
    current = row;
    current.TimestampMs = 1300;
    current.NativeActor.X = 1.5f;
    assert(!BotWorldTrace::CanCoalesceDecisionTrace(row, current, 0, false));

    row.NativeActor.Moving = true;
    row.NativeActor.SplineInitialized = true;
    row.NativeActor.SplineFinalized = false;
    row.NativeActor.SplineId = 41;
    current = row;
    current.TimestampMs = 1300;
    current.NativeActor.X = 1.5f;
    assert(BotWorldTrace::CanCoalesceDecisionTrace(row, current, 0, false));
    current.NativeActor.SplineId = 42;
    assert(!BotWorldTrace::CanCoalesceDecisionTrace(row, current, 0, false));
    current = row;
    current.TimestampMs = 1300;
    current.NativeActor.CurrentGenericSpellId = 123;
    assert(!BotWorldTrace::CanCoalesceDecisionTrace(row, current, 0, false));
    current = row;
    current.TimestampMs = 1300;
    current.NativeSelectedTarget.LineOfSightAvailable = true;
    current.NativeSelectedTarget.LineOfSight = true;
    assert(!BotWorldTrace::CanCoalesceDecisionTrace(row, current, 0, false));

    BotEncounter::MagmawTargetReturnObservation::Record targetReturn;
    targetReturn.Evaluated = true;
    targetReturn.ObservedAtMs = 1190;
    targetReturn.AttemptId = 9;
    targetReturn.RouteGeneration = 4;
    targetReturn.SnapshotRevision = 17;
    targetReturn.RouteNodeId = "bwd.magmaw.encounter";
    targetReturn.ProposedTargetGuid = ObjectGuid(std::uint64_t(55));
    targetReturn.Result =
        BotEncounter::MagmawTargetReturnObservation::BindResult::NativeMissing;
    row.TargetReturn = targetReturn;
    row.TargetReturnCurrentAtRecord = true;
    row.TargetReturnAgeAvailable = true;
    row.TargetReturnAgeMs = 10;
    row.TimestampMs = 1200;
    row.Sequence = 9;
    std::string const currentTargetFailure = Encode(row);
    assert(currentTargetFailure.find("\"observed_at_ms\":1190")
        != std::string::npos);
    assert(currentTargetFailure.find("\"age_ms\":10")
        != std::string::npos);
    assert(currentTargetFailure.find("\"current_at_record\":true")
        != std::string::npos);
    assert(currentTargetFailure.find("\"stale\":false")
        != std::string::npos);
    assert(currentTargetFailure.find("\"current\":true")
        != std::string::npos);

    current = row;
    current.TimestampMs = 1300;
    current.TargetReturn->Body.NativePresent = true;
    assert(!BotWorldTrace::CanCoalesceDecisionTrace(row, current, 0, false));

    WorldBotState::DecisionTraceEntry staleTargetFailure = row;
    staleTargetFailure.TimestampMs = 2000;
    staleTargetFailure.Sequence = 10;
    staleTargetFailure.TargetReturnCurrentAtRecord = false;
    staleTargetFailure.TargetReturnAgeMs = 810;
    std::string const staleTargetJson = Encode(staleTargetFailure);
    assert(staleTargetJson.find("\"current_at_record\":false")
        != std::string::npos);
    assert(staleTargetJson.find("\"stale\":true") != std::string::npos);
    assert(staleTargetJson.find("\"current\":false") != std::string::npos);
    std::cout << currentTargetFailure << '\n' << staleTargetJson << '\n';
    return 0;
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            "-I",
            str(ROOT / "dep/g3dlite/include"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    run_result = subprocess.run(
        [str(binary)], check=True, cwd=ROOT, capture_output=True, text=True
    )
    current_entry, stale_entry = [
        json.loads(line) for line in run_result.stdout.splitlines()
    ]

    scheduler = TelemetryScheduler(
        status_interval_sec=5,
        diagnose_interval_sec=30,
        trace_interval_sec=10,
        diagnosis_failure_cooldown_sec=15,
    )
    scheduler.commands_due(0.0)
    scheduler.observe_trace(
        [{"bots": [{"bot_guid": 1001, "entries": [current_entry]}]}],
        observed_at=1.0,
    )
    assert scheduler.commands_due(1.1) == ["botauto diagnose all"]

    cached_scheduler = TelemetryScheduler(
        status_interval_sec=5,
        diagnose_interval_sec=30,
        trace_interval_sec=10,
        diagnosis_failure_cooldown_sec=15,
    )
    cached_scheduler.commands_due(0.0)
    cached_scheduler.observe_trace(
        [{"bots": [{"bot_guid": 1001, "entries": [stale_entry]}]}],
        observed_at=1.0,
    )
    assert cached_scheduler.commands_due(1.1) == []
