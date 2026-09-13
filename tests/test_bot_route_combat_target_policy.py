from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotRouteCombatTargetPolicy.h"
FALLBACK = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp"
RANGE_ADAPTER = ROOT / "src/server/game/Bots/BotProfileCombatRangeCandidate.h"


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


def test_generic_range_candidate_admits_only_valid_too_close_targets() -> None:
    adapter = RANGE_ADAPTER.read_text(encoding="utf-8")
    fallback = FALLBACK.read_text(encoding="utf-8")
    assert "BotProfileCombatRangeCandidate::Build" in fallback
    assert "BotRouteCombatTargetPolicy::IsOwnedNativeEncounterTarget" in fallback
    assert "target->IsInWorld()" in fallback
    assert '"profile_combat_target_invalid"' in adapter
    assert "ResolveProfileCombatAction" in fallback
    assert "ResolvedCombatAction profileAction = ResolveProfileCombatAction(" in fallback
    assert "insideLegalMinRange" in adapter
    assert "outsideLegalMaxRange" in adapter
    assert "MoveBotToProfileRange" in fallback
    assert "Resource::Movement" in adapter
    for resource in (
        "Resource::GlobalCooldown",
        "Resource::Cast",
        "Resource::Target",
    ):
        assert resource not in adapter
    assert adapter.index("outsideLegalMaxRange") < adapter.index("if (!decision.Move")
    assert adapter.index("insideLegalMinRange") < adapter.index("if (!decision.Move")
    assert '"profile_min_range_satisfied"' in adapter
    assert '"profile_combat_min_range_reconciled"' in adapter
    assert "41570" not in adapter
    assert "Magmaw" not in adapter


def test_generic_range_candidate_preserves_drudge_latch_and_native_guards() -> None:
    adapter = RANGE_ADAPTER.read_text(encoding="utf-8")
    fallback = FALLBACK.read_text(encoding="utf-8")

    # The typed Drudge route still has the activation latch and its original
    # max-range/LOS reconciliation. Generic hostile admission is a separate
    # minimum-range branch and cannot inherit an encounter identity.
    assert '"drudge_activation_latch_closed"' in adapter
    assert '"drudge_profile_range_satisfied"' in adapter
    assert '"profile_combat_los_reconciled"' in adapter
    assert '"drudge_profile_los_path_rejected"' in adapter
    assert adapter.index("if (decision.OwnedDrudge)") < adapter.index(
        "else if (!insideLegalMinRange)"
    )
    assert fallback.index("target->IsInWorld()") < fallback.index(
        "ResolveProfileCombatAction"
    )
    assert fallback.index("!decision.SameMap") < fallback.index(
        "ResolveProfileCombatAction"
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


def test_current_encounter_authority_actual_producer_and_independent_future_slice(tmp_path):
    """Compile the actual adaptive producer, native contract and authority header.

    Only unrelated future-route collection is stubbed in the refresh adapter;
    its new clearing statement is copied from the real ordinary refresh.
    """
    fallback = FALLBACK.read_text()
    start = fallback.index('        if (routeOwnerReason())')
    end = fallback.index('\n\n        auto routeActionIsMovementOnly', start)
    producer = fallback[start:end]
    refresh = (ROOT / 'src/server/game/Bots/BotWorldPopulationMgrValidationAuthority.cpp').read_text()
    clear = next(line for line in refresh.splitlines() if 'SetCurrentEncounterRestrictions(' in line)
    source = tmp_path / 'current_authority.cpp'
    source.write_text(r'''
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawLaneTransition.h"
#include <cassert>
struct Bot {ObjectGuid Guid{HighGuid::Player,30008u};ObjectGuid GetGUID()const{return Guid;}};
struct Context {struct {BotEncounter::MagmawParasiteCombatContract MagmawParasiteCombat;} State;struct Bot* Bot;};
void ConfigureValidationRouteCombatAuthority(Bot* bot){uint64 const raidAuthorityOwner=bot->GetGUID().GetRawValue();
''' + clear + r'''
}
void publish(Context& context){auto routeOwnerReason=[](){return true;};
''' + producer + r'''
}
int main(){using namespace BotRaidAreaAuthority;
 Bot bot;Context context{{},&bot};auto& c=context.State.MagmawParasiteCombat;
 uint64 owner=bot.Guid.GetRawValue();ObjectGuid personal(HighGuid::Unit,41806u,191u),support(HighGuid::Unit,42321u,192u),other(HighGuid::Unit,41806u,193u);
 auto blocked=[&](uint32 entry,ObjectGuid guid){return IsProtectedEncounterTarget(owner,entry,0,guid.GetRawValue());};
 SetProtectedEncounterEntries(owner,{9999});SetProtectedEncounterSpawnIds(owner,{55});
 c.Active=true;c.ActorGuid=bot.Guid;c.PersonalThreatGuid=personal;c.SupportTargetGuid=support;publish(context);
 assert(HasProtectedEncounterEntries(owner));assert(IsCurrentEncounterRestrictedEntry(owner,41806));assert(IsCurrentEncounterRestrictedEntry(owner,42321));
 assert(blocked(41806,other));assert(blocked(42321,other));assert(!blocked(41806,personal));assert(!blocked(42321,support));
 assert(!blocked(41570,other));assert(!blocked(42347,other));assert(blocked(9999,personal));
 assert(IsProtectedEncounterTarget(owner,1,55,personal.GetRawValue()));
 // Future-route allowed GUIDs cannot bypass this encounter's restriction.
 SetAllowedEncounterGuids(owner,{other.GetRawValue()});assert(blocked(41806,other));
 SetProtectedEncounterEntries(owner,{41806,9999});assert(blocked(41806,personal));
 SetProtectedEncounterEntries(owner,{9999});
 c.FireMageGuid=bot.Guid;publish(context);assert(!IsCurrentEncounterRestrictedEntry(owner,41806));assert(!blocked(41806,other));assert(blocked(9999,personal));
 c.FireMageGuid.Clear();c.MarksmanshipHunterGuid=bot.Guid;publish(context);assert(!blocked(42321,other));
 c.MarksmanshipHunterGuid.Clear();c.Active=false;publish(context);assert(!IsCurrentEncounterRestrictedEntry(owner,42321));assert(blocked(9999,personal));
 c.Active=true;c.ActorGuid=ObjectGuid(HighGuid::Player,30007u);publish(context);assert(blocked(41806,personal));
 c.ActorGuid=bot.Guid;publish(context);assert(!blocked(41806,personal));
 ConfigureValidationRouteCombatAuthority(&bot);assert(!blocked(41806,other));assert(blocked(9999,personal));
 publish(context);Clear(owner);assert(!HasProtectedEncounterEntries(owner));assert(!IsCurrentEncounterRestrictedEntry(owner,41806));assert(!blocked(41806,other));
}
''')
    binary = tmp_path / 'current_authority'
    subprocess.run(['g++', '-std=c++17', '-I', str(ROOT / 'src/server/game'), '-I', str(ROOT / 'src/common'), '-I', str(ROOT / 'src/server/game/Entities/Object'), str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
