from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TELEMETRY = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeRecoveryTelemetry.h"
IMPLEMENTATION = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeTelemetry.cpp"
ACTION = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeActions.cpp"
RUNTIME = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRaidRuntime.cpp"
ROUTE_STATE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRouteState.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_diagnostic_rings_are_scoped_bounded_and_deduplicated(tmp_path: Path) -> None:
    source = tmp_path / "drudge_recovery_telemetry.cpp"
    binary = tmp_path / "drudge_recovery_telemetry"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeRecoveryTelemetry.h"

#include <cassert>

int main()
{
    using namespace BotRaidDrudgeGeometry;
    using namespace BotRaidDrudgeSpacing;
    Scope first{11, 2, 7, 669, 14, 250140, 250141};
    Scope second{11, 3, 7, 669, 14, 250140, 250141};
    std::vector<RecoveryTick> ticks;
    RecoveryTick sample;
    sample.Scope = first;
    sample.ObservedAtMs = 1000;
    sample.Members.resize(MaximumRecoveryMembers);
    ObserveRecoveryTick(ticks, first, sample);
    assert(ticks.size() == 1 && ticks.front().Members.size() == 10);
    sample.ObservedAtMs = 1500;
    sample.Sequence = 9;
    ObserveRecoveryTick(ticks, first, sample);
    assert(ticks.size() == 1 && ticks.front().Sequence == 9);
    sample.ObservedAtMs = 2501;
    ObserveRecoveryTick(ticks, first, sample);
    assert(ticks.size() == 2);
    for (unsigned index = 0; index < MaximumRecoveryTicks + 8; ++index) {
        sample.ObservedAtMs = 10000 + index * (RecoveryTickIntervalMs + 1);
        ObserveRecoveryTick(ticks, first, sample);
    }
    assert(ticks.size() == MaximumRecoveryTicks);
    ObserveRecoveryTick(ticks, second, sample);
    assert(ticks.size() == 1 && ticks.front().Scope == second);

    std::vector<NativeTransition> transitions;
    NativeTransition transition;
    transition.Scope = first;
    transition.BotGuid = 30001;
    transition.SourceGuid = 42362;
    transition.CurrentVictimGuid = 30001;
    transition.Result = "drudge_lane_native_taunt";
    ObserveNativeTransition(transitions, first, transition);
    ObserveNativeTransition(transitions, first, transition);
    assert(transitions.size() == 1 && transitions.front().SuppressedCount == 1);
    for (unsigned index = 0; index < MaximumNativeTransitions + 8; ++index) {
        transition.BotGuid = 30001 + index;
        ObserveNativeTransition(transitions, first, transition);
    }
    assert(transitions.size() == MaximumNativeTransitions);
    ObserveNativeTransition(transitions, second, transition);
    assert(transitions.size() == 1 && transitions.front().Scope == second);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++", "-std=c++17", "-I", str(ROOT / "src/server/game"),
            "-I", str(ROOT / "src/common"), str(source), "-o", str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_recovery_telemetry_is_observational_and_serialized() -> None:
    telemetry = TELEMETRY.read_text(encoding="utf-8")
    implementation = IMPLEMENTATION.read_text(encoding="utf-8")
    action = ACTION.read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")
    route_state = ROUTE_STATE.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")
    for path in (TELEMETRY, IMPLEMENTATION, ACTION, RUNTIME, ROUTE_STATE):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000
    for field in (
        "AllRecoveryAnchorsReached", "AllRecoveryTankPathsProven",
        "AllCombatTankPathsProven", "AllCombatTankAnchorsReached",
        "ExactRosterReseparated", "LandedRushRecoveryComplete",
        "Source0VictimGuid", "Source1VictimGuid", "ActivePathDestinationZ",
        "CombatAnchorPathProven", "RecoveryAnchorReached",
    ):
        assert field in telemetry or field in implementation
    for field in (
        "recovery_ticks", "native_transitions", "all_recovery_anchors_reached",
        "all_combat_tank_paths_proven", "all_combat_tank_anchors_reached",
        "exact_roster_reseparated", "landed_rush_recovery_complete",
        "source0_victim_guid", "source1_victim_guid", "active_path_destination_z",
        "combat_anchor_path_proven", "taunt_submitted", "taunt_outcome_observed",
        "current_victim_guid",
    ):
        assert field in runtime
    assert "RecoveryTicks" in route_state
    assert "NativeTransitions" in route_state
    assert "BotWorldPopulationMgrValidationRouteDrudgeTelemetry.cpp" in cmake
    assert "RecordRecoveryDiagnosticTick" in action
    assert "RecordNativeTransition(source, result, value2)" in action
    assert action.index("RecordRecoveryDiagnosticTick") < action.index(
        "if (PrepullStaged && !NativeChargePending && !activePathsProvenBeforeTick)")
    assert "MoveBotToPoint" not in implementation
    assert "TryCastCombatSpell" not in implementation
    assert "SetAllOffenseSuppressed" not in implementation
    assert "RecordEvent" not in implementation
    assert "TauntSucceeded" not in implementation
    assert "transition.TauntOutcomeObserved =" in implementation
    assert "transition.NativeVictimOwned" in implementation
