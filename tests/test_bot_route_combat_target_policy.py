from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotRouteCombatTargetPolicy.h"
FALLBACK = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp"


def test_owned_route_target_gate_replays_safe_admission(tmp_path: Path) -> None:
    source = tmp_path / "route_target_policy.cpp"
    binary = tmp_path / "route_target_policy"
    source.write_text(
        r'''
#include "Bots/BotRouteCombatTargetPolicy.h"
#include "Bots/BotActionArbiter.h"
#include "Bots/BotRaidAreaAuthority.h"
#include <cassert>

int main()
{
    using BotRouteCombatTargetPolicy::IsOwnedNativeEncounterTarget;
    assert(IsOwnedNativeEncounterTarget(true, true, true, true, true, 42362, 42362));
    assert(!IsOwnedNativeEncounterTarget(false, true, true, true, true, 42362, 42362));
    assert(!IsOwnedNativeEncounterTarget(true, false, true, true, true, 42362, 42362));
    assert(!IsOwnedNativeEncounterTarget(true, true, false, true, true, 42362, 42362));
    assert(!IsOwnedNativeEncounterTarget(true, true, true, false, true, 42362, 42362));
    assert(!IsOwnedNativeEncounterTarget(true, true, true, true, false, 42362, 42362));
    assert(!IsOwnedNativeEncounterTarget(true, true, true, true, true, 42649, 42362));
    assert(!IsOwnedNativeEncounterTarget(true, true, true, true, true, 0, 42362));

    // Entering an adaptive-owned route node refreshes a stale ordinary route
    // hold without dropping the next encounter's target protection.
    uint64 owner = 30001;
    BotRaidAreaAuthority::SetAllOffenseSuppressed(owner, true);
    BotRaidAreaAuthority::SetProtectedEncounterEntries(owner, { 41570 });
    BotRaidAreaAuthority::SetAllOffenseSuppressed(owner, false);
    assert(!BotRaidAreaAuthority::IsAllOffenseSuppressed(owner));
    assert(BotRaidAreaAuthority::IsProtectedEncounterTarget(
        owner, 41570, 0, 39));
    BotRaidAreaAuthority::Clear(owner);

    // A range-closure candidate owns only movement, so a normal profile cast
    // can still commit during the same validation decision tick.
    using namespace BotActionArbitration;
    Kernel kernel;
    kernel.Begin(1000);
    bool moved = false;
    bool cast = false;
    Candidate range;
    range.Key = "world.profile_combat_range";
    range.Source = "db_class_spec_profile";
    range.ActionPriority = Priority::CombatMovement;
    range.RequiredResources = Uses(Resource::Movement);
    range.Attempt = [&]
    {
        moved = true;
        return Outcome::Started("range_reconciled");
    };
    kernel.Submit(std::move(range));
    Candidate profile;
    profile.Key = "world.profile_combat";
    profile.Source = "db_class_spec_profile";
    profile.ActionPriority = Priority::TrainedDamage;
    profile.RequiredResources = Uses(Resource::GlobalCooldown,
        Resource::Cast, Resource::Target);
    profile.Attempt = [&]
    {
        cast = true;
        return Outcome::Submitted("cast_submitted");
    };
    kernel.Submit(std::move(profile));
    Resolution const& resolution = kernel.Resolve();
    assert(moved && cast);
    assert(resolution.CommittedCandidates.size() == 2);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)


def test_route_target_allow_list_is_used_only_for_declared_drudge_entry() -> None:
    header = HEADER.read_text(encoding="utf-8")
    fallback = FALLBACK.read_text(encoding="utf-8")
    assert "targetEntry == declaredEntry" in header
    assert "BotRouteCombatTargetPolicy::IsOwnedNativeEncounterTarget" in fallback
    assert "BotEncounter::AdaptiveDrudgeStrategy::DrudgeEntry" in fallback
    assert "context.AdaptiveDrudgeOwnsNode" in fallback


def test_owned_drudge_range_candidate_is_movement_only_and_rechecks_profile_range() -> None:
    fallback = FALLBACK.read_text(encoding="utf-8")
    start = fallback.index('combatRange.Key = "world.profile_combat_range"')
    end = fallback.index('combat.Key = "world.profile_combat"', start)
    candidate = fallback[start:end]
    assert "BotRouteCombatTargetPolicy::IsOwnedNativeEncounterTarget" in candidate
    assert "ResolveProfileCombatAction" in candidate
    assert "outsideLegalMaxRange" in candidate
    assert "noLineOfSight" in candidate
    assert "MoveBotToProfileRange" in candidate
    assert "Resource::Movement" in candidate
    for resource in (
        "Resource::GlobalCooldown",
        "Resource::Cast",
        "Resource::Target",
    ):
        assert resource not in candidate
    assert candidate.index("outsideLegalMaxRange") < candidate.index(
        "MoveBotToProfileRange"
    )


def test_drudge_route_owns_target_before_boss_adapter_can_replace_it() -> None:
    fallback = FALLBACK.read_text(encoding="utf-8")
    start = fallback.index('boss.Key = "world.boss_mechanics"')
    end = fallback.index('BotActionArbitration::Candidate trash;', start)
    candidate = fallback[start:end]
    guard_end = candidate.index("if (!IsBossContext")
    guard = candidate[:guard_end]

    assert "context.AdaptiveDrudgeOwnsNode" in guard
    assert '"adaptive_drudge_owns_live_pack"' in guard
    assert guard.index("context.AdaptiveDrudgeOwnsNode") < guard_end
    assert candidate.index("context.AdaptiveDrudgeOwnsNode") < candidate.index(
        "IsBossContext"
    )


def test_adaptive_route_refreshes_combat_authority_before_kernel_resolution() -> None:
    fallback = FALLBACK.read_text(encoding="utf-8")
    start = fallback.index("auto routeOwnerReason")
    end = fallback.index("auto routeActionIsMovementOnly", start)
    admission = fallback[start:end]

    assert "if (routeOwnerReason())" in admission
    assert "ConfigureValidationRouteCombatAuthority(context.Bot);" in admission
    assert admission.index("if (routeOwnerReason())") < admission.index(
        "ConfigureValidationRouteCombatAuthority(context.Bot);"
    )


def test_drudge_reseparate_actions_stay_in_movement_lane_and_heal_is_independent() -> None:
    fallback = FALLBACK.read_text(encoding="utf-8")
    classifier_start = fallback.index("auto routeActionIsMovementOnly")
    classifier_end = fallback.index("auto runRoute", classifier_start)
    classifier = fallback[classifier_start:classifier_end]
    assert 'action.find("reseparate") != std::string::npos' in classifier

    route_start = fallback.index("BotActionArbitration::ResourceMask routeActionResources")
    route_end = fallback.index("routeAction.Attempt", route_start)
    route_resources = fallback[route_start:route_end]
    assert "Resource::Movement" in route_resources
    assert "!context.DrudgeCombatAuthorityAllowed" in route_resources

    candidates = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelCandidates.cpp"
    ).read_text(encoding="utf-8")
    support_start = candidates.index('support.Key = "raid.support.heal."')
    support = candidates[support_start:]
    assert "Resource::GlobalCooldown" in support
    assert "Resource::Cast" in support
    assert "Resource::Movement" not in support
