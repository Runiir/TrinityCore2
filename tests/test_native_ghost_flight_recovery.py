from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrGhostFlight.h"
RECOVERY = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRecovery.cpp"
PREPARATION = ROOT / (
    "src/server/game/Bots/BotWorldPopulationMgrUpdateBotPreparation.cpp"
)
STATE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBotState.h"
SEMANTIC = ROOT / "src/server/game/Bots/BotWorldPopulationMgrSemantic.cpp"


def test_ghost_flight_policy_replays_only_authorized_burning_steppes_recovery(
    tmp_path,
):
    source = tmp_path / "ghost_flight_policy.cpp"
    binary = tmp_path / "ghost_flight_policy"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrGhostFlight.h"
#include <cassert>

using BotWorldGhostFlight::Eligibility;

int main()
{
    Eligibility valid;
    valid.MapId = 0;
    valid.ZoneId = 46;
    valid.DeadGhost = true;
    valid.InWorld = true;
    valid.NativeRecoveryEpisode = true;
    valid.NativeCorpseAuthority = true;
    valid.CrossMapRecovery = true;
    valid.Outdoors = true;
    assert(BotWorldGhostFlight::IsEligible(valid));

    Eligibility alive = valid;
    alive.DeadGhost = false;
    assert(!BotWorldGhostFlight::IsEligible(alive));

    Eligibility wrongMap = valid;
    wrongMap.MapId = 669;
    assert(!BotWorldGhostFlight::IsEligible(wrongMap));

    Eligibility wrongZone = valid;
    wrongZone.ZoneId = 36;
    assert(!BotWorldGhostFlight::IsEligible(wrongZone));

    Eligibility indoor = valid;
    indoor.Outdoors = false;
    assert(!BotWorldGhostFlight::IsEligible(indoor));

    Eligibility instance = valid;
    instance.InstanceMap = true;
    assert(!BotWorldGhostFlight::IsEligible(instance));

    Eligibility noAuthority = valid;
    noAuthority.NativeCorpseAuthority = false;
    assert(!BotWorldGhostFlight::IsEligible(noAuthority));

    Eligibility noEpisode = valid;
    noEpisode.NativeRecoveryEpisode = false;
    assert(!BotWorldGhostFlight::IsEligible(noEpisode));

    Eligibility sameMap = valid;
    sameMap.CrossMapRecovery = false;
    assert(!BotWorldGhostFlight::IsEligible(sameMap));

    Eligibility transport = valid;
    transport.OnTransport = true;
    assert(!BotWorldGhostFlight::IsEligible(transport));

    Eligibility flight = valid;
    flight.InFlight = true;
    assert(!BotWorldGhostFlight::IsEligible(flight));
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
            str(ROOT / "src/server/game"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_ghost_flight_is_limited_to_native_recovery_and_cleared_on_exit():
    recovery = RECOVERY.read_text(encoding="utf-8")
    preparation = PREPARATION.read_text(encoding="utf-8")
    state = STATE.read_text(encoding="utf-8")
    semantic = SEMANTIC.read_text(encoding="utf-8")

    assert "BotWorldGhostFlight::Eligibility" in recovery
    assert "BotWorldGhostFlight::IsEligible(ghostFlightEligibility)" in recovery
    assert "HasNativeRaidCorpseAuthority(state, bot)" in recovery
    assert "bot->GetMapId() != state.ValidationCohortMapId" in recovery
    assert "bot->IsOutdoors()" in recovery
    assert "bot->GetMap() && bot->GetMap()->IsDungeon()" in recovery
    assert "bot->SetCanFly(true)" in recovery
    assert "bot->SetCanFly(false)" in recovery
    assert "clearGhostFlight();" in recovery
    assert "NativeRecoveryGhostFlightEnabled" in state
    assert "NativeRecoveryGhostFlightEnabled" in semantic

    # Resurrection closes the capability even if the recovery loop has not
    # reached its next dead-ghost tick yet.
    assert "if (context.State.NativeRecoveryGhostFlightEnabled)" in preparation
    assert preparation.index("context.Bot->SetCanFly(false)") < preparation.index(
        "context.State.NativeRecoveryGhostFlightEnabled = false"
    )


def test_ghost_flight_header_stays_small():
    assert len(HEADER.read_text(encoding="utf-8").splitlines()) < 1000
