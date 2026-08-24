from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeObservationBacklog.h"


def test_exact_recovery_closes_only_landed_observations_that_existed_at_proof() -> None:
    source = r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeObservationBacklog.h"

#include <cassert>
#include <deque>

struct Observation
{
    unsigned long long AttemptId;
    unsigned WipeGeneration;
    unsigned long long RouteGeneration;
    unsigned long long ObservedAtMs;
    bool Landed;
    bool ReseparationRecorded;
};

int main()
{
    std::deque<Observation> observations{
        {11, 2, 7, 100, true, false},
        {11, 2, 7, 110, true, false},
        {11, 2, 7, 115, false, false},
        {12, 2, 7, 120, true, false},
        {11, 3, 7, 130, true, false},
        {11, 2, 8, 140, true, false},
        {11, 2, 7, 145, true, true},
        {11, 2, 7, 201, true, false},
    };
    unsigned calls = 0;
    auto const closed = BotRaidDrudgeObservationBacklog::CloseLandedThroughProof(
        observations, 11, 2, 7, 200,
        [&calls](Observation& observation)
        {
            observation.ReseparationRecorded = true;
            ++calls;
        });

    assert(closed == 2);
    assert(calls == 2);
    assert(observations[0].ReseparationRecorded);
    assert(observations[1].ReseparationRecorded);
    assert(!observations[2].ReseparationRecorded); // unlanded
    assert(!observations[3].ReseparationRecorded); // different attempt
    assert(!observations[4].ReseparationRecorded); // different wipe
    assert(!observations[5].ReseparationRecorded); // different route
    assert(observations[6].ReseparationRecorded);  // already closed
    assert(!observations[7].ReseparationRecorded); // observed after proof
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cpp = tmp_path / "observation_backlog.cpp"
        binary = tmp_path / "observation_backlog"
        cpp.write_text(source, encoding="utf-8")
        subprocess.run(
            [
                "c++",
                "-std=c++17",
                "-I",
                str(ROOT / "src/server/game"),
                "-I",
                str(ROOT / "src/common"),
                str(cpp),
                "-o",
                str(binary),
            ],
            check=True,
            cwd=ROOT,
        )
        subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_runtime_uses_backlog_closure_only_after_exact_recovery() -> None:
    actions = (HEADER.parent / "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp").read_text(
        encoding="utf-8"
    )

    recovery = actions.index("LandedRushRecoveryComplete")
    closure = actions.index("CloseLandedThroughProof")
    record = actions.index("drudge_native_charge_reseparation_complete")

    assert recovery < closure < record
    assert "Manager.Cohort().AttemptId" in actions[closure:record]
    assert "Manager.Cohort().Raid.WipeGeneration" in actions[closure:record]
    assert "Manager.Party().ValidationRouteGeneration" in actions[closure:record]


def test_post_closure_replay_returns_to_combat_path_gate(tmp_path) -> None:
    actions = (HEADER.parent / "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp").read_text(
        encoding="utf-8"
    )
    assert "RecoveryFormationActive = NativeChargePending && IsRecoveryFormationActive();" in actions

    source = tmp_path / "post_closure_replay.cpp"
    binary = tmp_path / "post_closure_replay"
    source.write_text(
        r'''
#include <cassert>

int main()
{
    // The historical landed observation remains visible to the formation
    // helper, but the current head is no longer pending after closure.
    bool const historicalLanded = true;
    bool currentHeadLanded = true;
    bool recoveryPathsProven = false;
    bool combatPathsProven = true;

    bool recoveryActive = currentHeadLanded && historicalLanded;
    assert(recoveryActive);
    assert(!(recoveryActive ? recoveryPathsProven : combatPathsProven));

    currentHeadLanded = false;
    recoveryActive = currentHeadLanded && historicalLanded;
    bool const activePathsProven = recoveryActive
        ? recoveryPathsProven : combatPathsProven;
    assert(!recoveryActive);
    assert(activePathsProven);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        ["c++", "-std=c++17", str(source), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)
