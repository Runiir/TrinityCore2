"""Bounded REC-002 coverage for partial trash corpse recovery admission."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATE_DEATH = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateDeath.cpp"
POLICY = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativeRecovery.h"


def test_update_death_calls_partial_trash_predicate_after_combat_reservation():
    update = UPDATE_DEATH.read_text(encoding="utf-8")
    policy = POLICY.read_text(encoding="utf-8")

    reservation = update.index("if (battleResReserved)")
    partial = update.index("partialTrashRecoveryAllowed")
    assert reservation < partial
    assert "CurrentCombatResOwnerUsable" in update[:reservation]
    reservation_block = update[reservation:partial]
    assert 'state.LastRecoveryMode = "wait_for_reserved_combat_res"' in reservation_block
    assert "state.LastRecoveryResult = state.NativeBattleResDecision" in reservation_block
    assert "return;" in reservation_block
    assert "IsAttributablePartialTrashDeath" in update[partial:]
    assert 'Cohort().Config.ValidationRouteKind' in update[partial:]
    assert "nativeHostileRecoveryBlocked = !partialTrashRecoveryAllowed" in update

    boss_gate = update.index(
        "Cohort().Config.ValidationRouteBossRecovery == "
        "ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly"
    )
    assert '&& Cohort().Config.ValidationRouteKind == "boss"' in update[boss_gate:boss_gate + 260]

    for marker in (
        "routeKind == \"trash\"",
        "observation.AliveSize > 0",
        "observation.AliveSize < observation.ActiveSize",
        "observation.AttemptId == observation.ExpectedAttemptId",
        "hostileScopeMatches",
        "observation.HostileActivityActive",
        "observation.HostileActivityEntry",
        "observation.HostileActivityGuid",
        "!observation.EncounterInProgress",
    ):
        assert marker in policy


def test_partial_trash_predicate_compiles_with_native_identity_counterexamples(
    tmp_path: Path, request
):
    request.addfinalizer(lambda: shutil.rmtree(tmp_path, ignore_errors=True))
    source = tmp_path / "partial_trash_recovery_predicate.cpp"
    binary = tmp_path / "partial_trash_recovery_predicate"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrNativeRecovery.h"

#include <cassert>

using namespace BotWorldPopulationMgrNativeRecovery;

PartialDeathObservation ValidPartialTrash()
{
    PartialDeathObservation observation;
    observation.Active = true;
    observation.RosterComplete = true;
    observation.EncounterInProgress = false;
    observation.HostileActivityActive = true;
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
    observation.NodeId = "bwd.magmaw.drudges";
    observation.HostileObservationNodeId = "bwd.magmaw.drudges";
    observation.HostileActivityEntry = 45879;
    observation.HostileActivityGuid = 0x1234;
    return observation;
}

int main()
{
    PartialDeathObservation valid = ValidPartialTrash();
    assert(IsAttributablePartialTrashDeath(valid, "trash"));

    PartialDeathObservation boss = valid;
    assert(!IsAttributablePartialTrashDeath(boss, "boss"));

    PartialDeathObservation allDead = valid;
    allDead.AliveSize = 0;
    allDead.PartialDeathState = false;
    assert(!IsAttributablePartialTrashDeath(allDead, "trash"));

    PartialDeathObservation staleAttempt = valid;
    staleAttempt.HostileObservationAttemptId = 6;
    assert(!IsAttributablePartialTrashDeath(staleAttempt, "trash"));

    PartialDeathObservation staleRoute = valid;
    staleRoute.HostileObservationRouteGeneration = 3;
    assert(!IsAttributablePartialTrashDeath(staleRoute, "trash"));

    PartialDeathObservation staleNode = valid;
    staleNode.HostileObservationNodeId = "bwd.other.node";
    assert(!IsAttributablePartialTrashDeath(staleNode, "trash"));

    PartialDeathObservation incompleteIdentity = valid;
    incompleteIdentity.AttemptId = 0;
    incompleteIdentity.ExpectedAttemptId = 0;
    incompleteIdentity.RouteGeneration = 0;
    incompleteIdentity.NodeId = {};
    incompleteIdentity.HostileObservationAttemptId = 0;
    incompleteIdentity.HostileObservationRouteGeneration = 0;
    incompleteIdentity.HostileObservationNodeId = {};
    assert(!IsAttributablePartialTrashDeath(incompleteIdentity, "trash"));

    PartialDeathObservation incompleteRoster = valid;
    incompleteRoster.RosterComplete = false;
    assert(!IsAttributablePartialTrashDeath(incompleteRoster, "trash"));

    PartialDeathObservation encounter = valid;
    encounter.EncounterInProgress = true;
    assert(!IsAttributablePartialTrashDeath(encounter, "trash"));

    PartialDeathObservation inactiveNoReset = valid;
    inactiveNoReset.HostileActivityActive = false;
    assert(!IsAttributablePartialTrashDeath(inactiveNoReset, "trash"));

    PartialDeathObservation forcedActiveNoIdentity = valid;
    forcedActiveNoIdentity.HostileActivityEntry = 0;
    forcedActiveNoIdentity.HostileActivityGuid = 0;
    assert(!IsAttributablePartialTrashDeath(forcedActiveNoIdentity, "trash"));
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
