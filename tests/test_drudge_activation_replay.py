import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
ACTIVATION = (
    ROOT
    / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
    "BotRaidDrudgeActivationState.h"
)


def test_exact_drudge_activation_latch_replays_every_missing_evidence_edge(tmp_path):
    source = tmp_path / "drudge_activation_replay.cpp"
    binary = tmp_path / "drudge_activation_replay"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeActivationState.h"
#include <cassert>

using namespace BotRaidDrudgeActivation;

int main()
{
    Input exact;
    exact.ExactRouteProfile = true;
    exact.ExactRosterPrepullStaged = true;
    exact.BothTankAnchorsAccepted = true;
    exact.BothTankVictimsAccepted = true;
    exact.SeedProfileActionsAccepted = true;
    exact.FirstNativeRushObserved = true;
    exact.ExactRosterReseparated = true;
    exact.ProfileActionAccepted = true;

    Result open = Evaluate(exact);
    assert(open.CombatAuthorityAllowed);
    assert(open.BlockingEvidence == Blocker::None);

    // Every individual missing edge keeps adaptive/generic combat denied.
    bool* gates[] = {
        &exact.ExactRosterPrepullStaged,
        &exact.BothTankAnchorsAccepted,
        &exact.BothTankVictimsAccepted,
        &exact.SeedProfileActionsAccepted,
        &exact.FirstNativeRushObserved,
        &exact.ExactRosterReseparated,
        &exact.ProfileActionAccepted,
    };
    Blocker blockers[] = {
        Blocker::ExactRosterPrepull,
        Blocker::TankAnchors,
        Blocker::TankVictims,
        Blocker::SeedProfileActions,
        Blocker::FirstNativeRush,
        Blocker::ExactRosterReseparation,
        Blocker::ProfileAction,
    };
    for (unsigned index = 0; index < 7; ++index)
    {
        *gates[index] = false;
        Result closed = Evaluate(exact);
        assert(!closed.CombatAuthorityAllowed);
        assert(closed.BlockingEvidence == blockers[index]);
        *gates[index] = true;
    }

    // An incomplete seed is fail-closed before the native clock edge, but a
    // scoped landed Rush plus closed/failed seed releases the existing
    // post-Rush recovery fallback. This does not mark the seed successful.
    Input failedSeed = exact;
    failedSeed.SeedProfileActionsAccepted = false;
    failedSeed.SeedWindowClosedOrFailed = true;
    failedSeed.FirstNativeRushObserved = false;
    Result beforeRush = Evaluate(failedSeed);
    assert(!beforeRush.CombatAuthorityAllowed);
    assert(beforeRush.BlockingEvidence == Blocker::FirstNativeRush);

    failedSeed.FirstNativeRushObserved = true;
    failedSeed.BothTankAnchorsAccepted = false;
    failedSeed.BothTankVictimsAccepted = false;
    failedSeed.ExactRosterReseparated = false;
    failedSeed.ProfileActionAccepted = false;
    Result postRushRecovery = Evaluate(failedSeed);
    assert(postRushRecovery.CombatAuthorityAllowed);
    assert(postRushRecovery.BlockingEvidence == Blocker::PostRushSeedRecovery);

    // A complete seed never takes the escape edge: success remains gated by
    // exact reseparation and a later accepted profile action.
    Input successfulSeed = exact;
    successfulSeed.ExactRosterReseparated = false;
    Result beforeReseparation = Evaluate(successfulSeed);
    assert(!beforeReseparation.CombatAuthorityAllowed);
    assert(beforeReseparation.BlockingEvidence == Blocker::ExactRosterReseparation);
    successfulSeed.ExactRosterReseparated = true;
    successfulSeed.ProfileActionAccepted = false;
    Result beforeProfile = Evaluate(successfulSeed);
    assert(!beforeProfile.CombatAuthorityAllowed);
    assert(beforeProfile.BlockingEvidence == Blocker::ProfileAction);

    // A generic/adaptive profile does not inherit this exact validation latch.
    Input generic = exact;
    generic.ExactRouteProfile = false;
    Result genericResult = Evaluate(generic);
    assert(genericResult.CombatAuthorityAllowed);
    assert(genericResult.BlockingEvidence == Blocker::NotExactRoute);
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


def test_exact_drudge_candidates_fail_closed_behind_the_typed_route_latch():
    candidates = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelCandidates.cpp"
    ).read_text(encoding="utf-8")
    fallback = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp"
    ).read_text(encoding="utf-8")
    preparation = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelPreparation.cpp"
    ).read_text(encoding="utf-8")

    assert ACTIVATION.name in preparation
    assert "BotRaidDrudgeActivation::Evaluate(activationInput)" in preparation
    assert "SeedWindowClosedOrFailed" in preparation
    assert "context.DrudgeCombatAuthorityAllowed" in candidates
    assert '"drudge_activation_latch_closed"' in fallback
    assert fallback.count('"drudge_activation_latch_closed"') == 3
    assert "typedDrudgeValidationRoute" in fallback
    assert "context.AdaptiveDrudgeOwnsNode" in fallback


def test_pending_drudge_recovery_reserves_the_route_movement_lane():
    fallback = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp"
    ).read_text(encoding="utf-8")
    resource_start = fallback.index(
        "BotActionArbitration::ResourceMask routeActionResources"
    )
    resource_end = fallback.index(
        "routeAction.Attempt =", resource_start
    )
    resource_block = fallback[resource_start:resource_end]

    # Before exact reseparation, the route action owns Movement as well as
    # cast/target resources. This prevents profile combat range from
    # replacing the assigned tank's native recovery anchor with a chase.
    assert "typedDrudgeValidationRoute" in resource_block
    assert "context.AdaptiveDrudgeOwnsNode" in resource_block
    assert "!context.DrudgeCombatAuthorityAllowed" in resource_block
    assert "Resource::Movement" in resource_block
    assert "routeAction.RequiredResources = routeActionResources" in resource_block

    # The ordinary route keeps the original action/movement split, and the
    # movement candidate remains independently declared for that path.
    assert "routeMovement.RequiredResources = BotActionArbitration::Uses(" in fallback
    assert fallback.count("Resource::Movement") >= 2
