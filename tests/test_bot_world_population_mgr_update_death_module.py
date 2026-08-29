import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateDeath.cpp"
POLICY = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativeRecovery.h"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_update_death_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrUpdateDeath.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert '#include "Bots/BotWorldPopulationMgrNativeRecovery.h"' in text
    assert "BotWorldPopulationMgr::HandleBotDeath" in text
    assert "HandleBotDeath" in HEADER.read_text()


def test_update_death_handler_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "HandleBotDeath(state, bot, diff);" in text
    assert "state.DeathEpisodeRecorded = true;" not in text


def test_update_death_keeps_native_recovery_contract():
    text = MODULE.read_text()
    for marker in (
        "NativeFullWipeOnly",
        "native_full_wipe_only",
        "CurrentCombatResOwnerUsable",
        "PublishNativeBattleResDecision",
        "RecoverDeadBot",
        "death_recovery_started",
        "tactical_retreat_no_combat_res",
    ):
        assert marker in text


def test_partial_trash_deaths_do_not_require_a_manufactured_full_wipe():
    text = MODULE.read_text()
    full_wipe_gate = text.index(
        "Cohort().Config.ValidationRouteBossRecovery == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly"
    )
    reset_gate = text.index("native_recovery_wait_hostile_activity")

    assert '&& Cohort().Config.ValidationRouteKind == "boss"' in text[
        full_wipe_gate:full_wipe_gate + 240
    ]
    assert "RecoverDeadBot(state, bot)" in text[reset_gate:]


def _native_partial_death_reset_recovery_allowed(
    *,
    active=True,
    attempt_id=7,
    raid_attempt_id=7,
    route_generation=4,
    observed_route_generation=4,
    node_id="bwd.magmaw.encounter",
    observed_node_id="bwd.magmaw.encounter",
    expected_population=10,
    raid_expected_population=10,
    active_size=10,
    alive_size=1,
    roster_complete=True,
    wipe_state="partial_deaths",
    encounter_in_progress=False,
    hostile_active=False,
    boss_reset_generation=1,
    boss_reset_generation_at_wipe=0,
    hostile_inactivity_observed=False,
    hostile_reset_generation=0,
    hostile_reset_generation_at_wipe=0,
):
    hostile_scope_matches = (
        attempt_id == raid_attempt_id
        and route_generation == observed_route_generation
        and node_id == observed_node_id
    )
    hostile_reset_observed = (
        hostile_scope_matches
        and hostile_inactivity_observed
        and hostile_reset_generation > hostile_reset_generation_at_wipe
    )
    boss_reset_observed = boss_reset_generation > boss_reset_generation_at_wipe
    return (
        active
        and attempt_id == raid_attempt_id
        and roster_complete
        and raid_expected_population == expected_population
        and active_size == raid_expected_population
        and 0 < alive_size < active_size
        and wipe_state == "partial_deaths"
        and not encounter_in_progress
        and not hostile_active
        and (boss_reset_observed or hostile_reset_observed)
    )


def test_partial_boss_death_releases_only_after_native_reset_and_idle_hostiles():
    assert _native_partial_death_reset_recovery_allowed()

    # The exact Canary109 failure: one survivor and nine dead while Magmaw is
    # still active must remain held, even though the roster is otherwise valid.
    assert not _native_partial_death_reset_recovery_allowed(
        encounter_in_progress=True,
        boss_reset_generation=0,
        boss_reset_generation_at_wipe=0,
    )
    assert not _native_partial_death_reset_recovery_allowed(
        boss_reset_generation=0,
        boss_reset_generation_at_wipe=0,
    )
    assert not _native_partial_death_reset_recovery_allowed(hostile_active=True)
    assert not _native_partial_death_reset_recovery_allowed(
        route_generation=3,
        observed_route_generation=4,
        boss_reset_generation=0,
        boss_reset_generation_at_wipe=0,
        hostile_inactivity_observed=True,
        hostile_reset_generation=1,
        hostile_reset_generation_at_wipe=0,
    )

    # Hostile-pack reset is an equivalent native authority when the instance
    # script has no boss-state transition for the current route node.
    assert _native_partial_death_reset_recovery_allowed(
        boss_reset_generation=0,
        boss_reset_generation_at_wipe=0,
        hostile_inactivity_observed=True,
        hostile_reset_generation=1,
        hostile_reset_generation_at_wipe=0,
    )


def test_partial_reset_release_is_native_only_and_distinct_from_full_wipe_latch():
    text = MODULE.read_text()
    policy = POLICY.read_text()
    gate = policy.index("EvaluatePartialDeathAdmission")
    release = text.index("native_partial_death_reset_release_allowed")
    wait = text.index("native_full_wipe_wait_partial_death")
    for token in (
        "PartialDeathObservation",
        "exactPartialRoster",
        "observation.AliveSize > 0",
        "observation.AliveSize < observation.ActiveSize",
        "!observation.EncounterInProgress",
        "!observation.HostileActivityActive",
        "observation.BossResetGeneration",
        "observation.BossResetGenerationAtWipe",
        "HostileObservationRouteGeneration",
    ):
        assert token in policy[gate:]
    assert wait < release
    assert "EvaluatePartialDeathAdmission" in text
    assert '"direct_respawn\\":false' in text[wait:release]
    assert '"direct_state_manufacture\\":false' in text[wait:release]


def test_partial_death_admission_compiles_and_replays_all_native_reset_edges(tmp_path):
    source = tmp_path / "native_recovery_replay.cpp"
    binary = tmp_path / "native_recovery_replay"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrNativeRecovery.h"

#include <cassert>

using namespace BotWorldPopulationMgrNativeRecovery;

PartialDeathObservation Valid()
{
    PartialDeathObservation observation;
    observation.Active = true;
    observation.RosterComplete = true;
    observation.PartialDeathState = true;
    observation.ExpectedPopulation = 10;
    observation.RaidExpectedPopulation = 10;
    observation.ActiveSize = 10;
    observation.AliveSize = 1;
    observation.AttemptId = 7;
    observation.ExpectedAttemptId = 7;
    observation.RouteGeneration = 4;
    observation.HostileObservationAttemptId = 7;
    observation.HostileObservationRouteGeneration = 4;
    observation.NodeId = "bwd.magmaw.encounter";
    observation.HostileObservationNodeId = "bwd.magmaw.encounter";
    observation.BossResetGeneration = 1;
    return observation;
}

int main()
{
    PartialDeathObservation activeBoss = Valid();
    activeBoss.EncounterInProgress = true;
    assert(EvaluatePartialDeathAdmission(activeBoss)
        == PartialDeathAdmission::Hold);

    PartialDeathObservation hostileActive = Valid();
    hostileActive.HostileActivityActive = true;
    assert(EvaluatePartialDeathAdmission(hostileActive)
        == PartialDeathAdmission::Hold);

    PartialDeathObservation staleScope = Valid();
    staleScope.BossResetGeneration = 0;
    staleScope.HostileInactivityObserved = true;
    staleScope.HostileResetGeneration = 1;
    staleScope.HostileObservationRouteGeneration = 3;
    assert(EvaluatePartialDeathAdmission(staleScope)
        == PartialDeathAdmission::Hold);

    PartialDeathObservation noReset = Valid();
    noReset.BossResetGeneration = 0;
    assert(EvaluatePartialDeathAdmission(noReset)
        == PartialDeathAdmission::Hold);

    PartialDeathObservation validBossReset = Valid();
    assert(EvaluatePartialDeathAdmission(validBossReset)
        == PartialDeathAdmission::ReleaseAfterNativeReset);

    PartialDeathObservation validHostileReset = Valid();
    validHostileReset.BossResetGeneration = 0;
    validHostileReset.HostileInactivityObserved = true;
    validHostileReset.HostileResetGeneration = 1;
    assert(EvaluatePartialDeathAdmission(validHostileReset)
        == PartialDeathAdmission::ReleaseAfterNativeReset);

    PartialDeathObservation allDead = Valid();
    allDead.AliveSize = 0;
    assert(EvaluatePartialDeathAdmission(allDead)
        == PartialDeathAdmission::Hold);

    PartialDeathObservation fullyAlive = Valid();
    fullyAlive.AliveSize = fullyAlive.ActiveSize;
    assert(EvaluatePartialDeathAdmission(fullyAlive)
        == PartialDeathAdmission::Hold);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++",
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
