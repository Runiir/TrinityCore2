from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRUDGE = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge"
HEADER = DRUDGE / "BotRaidDrudgeTauntConfirmation.h"
ACTION = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp"
TAUNT = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeTaunt.cpp"
TELEMETRY = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeTelemetry.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_taunt_confirmation_transition_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "drudge_taunt_confirmation.cpp"
    binary = tmp_path / "drudge_taunt_confirmation"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeTauntConfirmation.h"

#include <cassert>

int main()
{
    using namespace BotRaidDrudgeTauntConfirmation;
    Scope scope{11, 4294967297ULL, 7, 669, 14, 250141, 250141, 30002};
    State state;

    Submit(state, scope, 56222, 1000);
    assert(state.Pending && state.SubmittedAtMs == 1000);
    assert(Observe(state, scope, 30006, 1000) == Observation::Pending);
    assert(Observe(state, scope, 30006, 1000 + RetryBackoffMs - 1)
        == Observation::Pending);
    assert(Observe(state, scope, 30006, 1000 + RetryBackoffMs)
        == Observation::RetryReady);
    DeferRetry(state, 2500);
    assert(Observe(state, scope, 30006, 2500 + RetryBackoffMs - 1)
        == Observation::Pending);
    assert(Observe(state, scope, 30002, 2500 + RetryBackoffMs)
        == Observation::Confirmed);
    assert(!state.Pending);

    Submit(state, scope, 56222, 5000);
    Scope newSource = scope;
    newSource.SourceIdentity = 250142;
    assert(Observe(state, newSource, 30006, 5001) == Observation::ScopeReset);
    assert(!state.Pending);

    Submit(state, scope, 56222, 6000);
    Scope sameLowBits = scope;
    sameLowBits.WipeGeneration = 1;
    assert(Observe(state, sameLowBits, 30006, 6001) == Observation::ScopeReset);
    assert(!state.Pending);

    Submit(state, scope, 56222, 7000);
    Scope newTank = scope;
    newTank.TankGuid = 30001;
    assert(Observe(state, newTank, 30006, 7001) == Observation::ScopeReset);
    assert(!state.Pending);
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


def test_native_taunt_submission_and_confirmation_are_separate_modules() -> None:
    action = ACTION.read_text(encoding="utf-8")
    taunt = TAUNT.read_text(encoding="utf-8")
    telemetry = TELEMETRY.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert len(ACTION.read_text(encoding="utf-8").splitlines()) < 1000
    assert len(HEADER.read_text(encoding="utf-8").splitlines()) < 1000
    assert len(TAUNT.read_text(encoding="utf-8").splitlines()) < 1000
    assert "RunNativeTauntConfirmation" in action
    assert "BotRaidDrudgeTauntConfirmation::Observe" in taunt
    assert "BotRaidDrudgeTauntConfirmation::Submit" in taunt
    assert "BotRaidDrudgeTauntConfirmation::DeferRetry" in taunt
    assert "drudge_lane_native_taunt_submitted_pending" in taunt
    assert "drudge_lane_native_taunt_confirmed" in taunt
    assert "drudge_lane_native_taunt_unconfirmed_retry_backoff" in taunt
    assert "ValidationRouteDrudgeTauntRosterGuids.insert" in taunt
    for receipt in (
        "drudge_lane_native_taunt_pending",
        "drudge_lane_native_taunt_unconfirmed_retry_backoff",
    ):
        assert receipt in telemetry
    assert telemetry.index(
        'std::strcmp(result, "drudge_lane_native_taunt_pending")'
    ) < telemetry.index(
        'std::strcmp(result, "drudge_lane_native_taunt_unconfirmed_retry_backoff")'
    )
    assert "TauntSubmitted = std::strcmp(result" in telemetry
    assert "TauntOutcomeObserved = std::strcmp(result" in telemetry
    assert "BotWorldPopulationMgrValidationRouteDrudgeTaunt.cpp" in cmake
