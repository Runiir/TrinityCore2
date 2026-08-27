from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_validation_cohort_readiness_replays_terminal_and_advance_gates(
    tmp_path: Path,
) -> None:
    source = tmp_path / "validation_cohort_readiness.cpp"
    binary = tmp_path / "validation_cohort_readiness"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrValidationCohortReadiness.h"

#include <cassert>

using namespace BotWorldPopulationMgrValidationRoute;

ValidationCohortMemberObservation Living(bool atEndpoint = true)
{
    ValidationCohortMemberObservation member;
    member.Accounted = true;
    member.Valid = true;
    member.Living = true;
    member.AtEndpoint = atEndpoint;
    return member;
}

ValidationCohortMemberObservation Recovering()
{
    ValidationCohortMemberObservation member;
    member.Accounted = true;
    member.Valid = true;
    member.KnownRecovering = true;
    return member;
}

ValidationCohortReadinessObservation TenMemberObservation()
{
    ValidationCohortReadinessObservation observation;
    observation.ExpectedMemberCount = 10;
    for (int index = 0; index < 10; ++index)
        observation.ObserveMember(Living());
    return observation;
}

int main()
{
    ValidationCohortRecoveryObservation recovery;
    recovery.Alive = false;
    recovery.Ghost = true;
    recovery.ReleaseRequested = true;
    recovery.NativeCorpseAuthority = true;
    recovery.EpisodeStartedMs = 100;
    recovery.EpisodeAttemptId = recovery.AttemptId = 7;
    recovery.EpisodeRouteGeneration = recovery.RouteGeneration = 3;
    recovery.EpisodeWipeGeneration = recovery.WipeGeneration = 2;
    recovery.EpisodeDeathOrdinal = recovery.DeathOrdinal = 1;
    recovery.EpisodePhase = "runback";
    assert(IsKnownValidationRecovery(recovery));
    recovery.NativeCorpseAuthority = false;
    assert(!IsKnownValidationRecovery(recovery));
    recovery.NativeCorpseAuthority = true;
    ++recovery.RouteGeneration;
    assert(!IsKnownValidationRecovery(recovery));

    ValidationCohortReadinessObservation full = TenMemberObservation();
    ValidationCohortReadiness fullResult =
        ClassifyValidationCohortReadiness(full);
    assert(fullResult.AllExpectedMembersAccounted);
    assert(fullResult.AllLivingAtEndpoint);
    assert(fullResult.FullRosterAtEndpoint);
    assert(fullResult.TrashTerminalReady);

    ValidationCohortReadinessObservation runback;
    runback.ExpectedMemberCount = 10;
    for (int index = 0; index < 9; ++index)
        runback.ObserveMember(Living());
    runback.ObserveMember(Recovering());
    ValidationCohortReadiness runbackResult =
        ClassifyValidationCohortReadiness(runback);
    assert(runbackResult.AllExpectedMembersAccounted);
    assert(runbackResult.AllLivingAtEndpoint);
    assert(!runbackResult.FullRosterAtEndpoint);
    assert(runbackResult.TrashTerminalReady);

    ValidationCohortReadinessObservation away = TenMemberObservation();
    away.LivingAtEndpointCount = 9;
    assert(!ClassifyValidationCohortReadiness(away).TrashTerminalReady);

    ValidationCohortReadinessObservation missing;
    missing.ExpectedMemberCount = 10;
    for (int index = 0; index < 9; ++index)
        missing.ObserveMember(Living());
    missing.ObserveMember({});
    assert(!ClassifyValidationCohortReadiness(missing).TrashTerminalReady);

    ValidationCohortReadinessObservation invalid;
    invalid.ExpectedMemberCount = 10;
    for (int index = 0; index < 9; ++index)
        invalid.ObserveMember(Living());
    ValidationCohortMemberObservation invalidMember;
    invalidMember.Accounted = true;
    invalid.ObserveMember(invalidMember);
    assert(!ClassifyValidationCohortReadiness(invalid).TrashTerminalReady);

    ValidationCohortReadinessObservation noLiving;
    noLiving.ExpectedMemberCount = 10;
    for (int index = 0; index < 10; ++index)
        noLiving.ObserveMember(Recovering());
    assert(!ClassifyValidationCohortReadiness(noLiving).TrashTerminalReady);

    ValidationCohortReadinessObservation livePack = TenMemberObservation();
    livePack.PackHasLiveMobs = true;
    assert(!ClassifyValidationCohortReadiness(livePack).TrashTerminalReady);

    ValidationCohortReadinessObservation activeCombat = TenMemberObservation();
    activeCombat.PartyHasActiveCombat = true;
    assert(!ClassifyValidationCohortReadiness(activeCombat).TrashTerminalReady);
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
