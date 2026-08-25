import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_production_drudge_seed_transition_replays_native_event_orderings(tmp_path):
    source = tmp_path / "drudge_seed_replay.cpp"
    binary = tmp_path / "drudge_seed_replay"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeThreatSeedState.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeSeedActionSelection.h"
#include <cassert>
#include <string>

using namespace BotRaidDrudgeThreatSeed;
using namespace BotRaidDrudgeSeedActionSelection;

static Input ready(Scope scope, std::uint32_t lane)
{
    Input input;
    input.Identity = scope;
    input.SourceLane = lane;
    input.PrepullStaged = true;
    input.SourcesAlive = true;
    input.OwnershipSafe = true;
    input.SeparationSafe = true;
    input.FrozenLanesSafe = true;
    input.CandidateAvailable = true;
    input.AuthoritySafe = true;
    return input;
}

int main()
{
    Scope first{7, 0, 3};
    State state;

    // Asynchronous bot ticks may observe staging/ownership in either order.
    // Transient incompleteness holds without poisoning the attempt.
    for (unsigned mask = 0; mask < 32; ++mask)
    {
        Input input = ready(first, 0);
        input.PrepullStaged = mask & 1;
        input.SourcesAlive = mask & 2;
        input.OwnershipSafe = mask & 4;
        input.SeparationSafe = mask & 8;
        input.FrozenLanesSafe = mask & 16;
        Result result = Advance(state, input);
        if (mask != 31)
        {
            assert(result.NextDecision == Decision::HoldWindow);
            assert(!result.Next.Failure);
        }
    }

    Input lane0 = ready(first, 0);
    lane0.CandidateAvailable = false;
    Result result = Advance(state, lane0);
    assert(result.ScopeReset);
    assert(result.NextDecision == Decision::RetryCandidate);
    assert(!result.Next.Failure);

    // A later tick can use the same production transition and request the
    // ordinary profile action without reopening or changing scope.
    lane0.CandidateAvailable = true;
    result = Advance(result.Next, lane0);
    assert(result.NextDecision == Decision::RequestSeedAction);
    lane0.Type = Event::ActionResult;
    lane0.ActionSucceeded = true;
    result = Advance(result.Next, lane0);
    assert(result.NextDecision == Decision::SeedAccepted);
    assert(result.Next.SeededLanes[0]);
    assert(!result.Next.Complete);

    // A scheduling gap before the other lane is ready is retryable.
    Input lane1 = ready(first, 1);
    lane1.OwnershipSafe = false;
    Result wait = Advance(result.Next, lane1);
    assert(wait.NextDecision == Decision::HoldWindow);
    assert(!wait.Next.Failure);

    lane1.OwnershipSafe = true;
    lane1.Type = Event::ActionResult;
    lane1.ActionSucceeded = true;
    result = Advance(wait.Next, lane1);
    assert(result.NextDecision == Decision::Complete);
    assert(result.Next.Complete);
    assert(!result.Next.Failure);

    // Native Rush closes the scope. Complete seeds remain valid; incomplete
    // seeds fail closed and can never be submitted late.
    Input rush;
    rush.Type = Event::FirstNativeRush;
    rush.Identity = first;
    Result completeRush = Advance(result.Next, rush);
    assert(completeRush.NextDecision == Decision::Complete);
    assert(completeRush.Next.Closed);
    assert(!completeRush.Next.Failure);

    State incomplete;
    incomplete.Identity = first;
    incomplete.SeededLanes[0] = true;
    Result failedRush = Advance(incomplete, rush);
    assert(failedRush.NextDecision == Decision::HoldClosed);
    assert(failedRush.Next.Closed && failedRush.Next.Failure);
    Result late = Advance(failedRush.Next, ready(first, 1));
    assert(late.NextDecision == Decision::HoldClosed);

    // The transition still rejects a late seed action, while production must
    // bypass its pre-Rush hold branch once this closed failure is installed.

    // A real wipe generation creates a fresh scope rather than inheriting the
    // old completion/failure/lanes.
    Scope retryScope{7, 1, 3};
    Input retry = ready(retryScope, 0);
    Result reset = Advance(failedRush.Next, retry);
    assert(reset.ScopeReset);
    assert(reset.NextDecision == Decision::RequestSeedAction);
    assert(!reset.Next.Closed && !reset.Next.Complete && !reset.Next.Failure);
    assert(!reset.Next.SeededLanes[0] && !reset.Next.SeededLanes[1]);

    // Once the coordinator has installed the roster-wide authority barrier,
    // only a genuine mismatch is terminal.
    Input unsafe = ready(retryScope, 0);
    unsafe.AuthoritySafe = false;
    Result authority = Advance(reset.Next, unsafe);
    assert(authority.NextDecision == Decision::FailAuthority);
    assert(authority.Next.Failure && authority.Next.Closed);
    Result authorityRetry = Advance(authority.Next, ready(retryScope, 0));
    assert(authorityRetry.NextDecision == Decision::HoldClosed);
    assert(authorityRetry.Next.Failure && authorityRetry.Next.Closed);

    // One typed route-coordinator tick evaluates both opposite lanes before
    // returning. A lane is accepted only when its native action reports Ok.
    CoordinatorInput bothTick;
    bothTick.Identity = first;
    bothTick.PrepullStaged = true;
    bothTick.SourcesAlive = true;
    bothTick.OwnershipSafe = true;
    bothTick.SeparationSafe = true;
    bothTick.FrozenLanesSafe = true;
    bothTick.Lanes[0] = { true, true, true, true, RejectionGate::None };
    bothTick.Lanes[1] = { true, true, true, true, RejectionGate::None };
    CoordinatorResult both = AdvanceCoordinator(State{}, bothTick);
    assert(both.BothLanesEvaluated);
    assert(both.Lanes[0].ActionAttempted && both.Lanes[1].ActionAttempted);
    assert(both.Next.SeededLanes[0] && both.Next.SeededLanes[1]);
    assert(both.Next.Complete && !both.Next.Failure);

    // The bounded initial seed opportunity does not need the sources to have
    // reached their final separated/frozen lanes.  It still traverses the
    // same typed candidate/action-result barrier.
    CoordinatorInput initialGeometryGap = bothTick;
    initialGeometryGap.InitialSeedOpportunity = true;
    initialGeometryGap.SeparationSafe = false;
    initialGeometryGap.FrozenLanesSafe = false;
    CoordinatorResult initialGeometry = AdvanceCoordinator(
        State{}, initialGeometryGap);
    assert(initialGeometry.BothLanesEvaluated);
    assert(initialGeometry.Lanes[0].ActionAttempted
        && initialGeometry.Lanes[1].ActionAttempted);
    assert(initialGeometry.Next.SeededLanes[0]
        && initialGeometry.Next.SeededLanes[1]);
    assert(initialGeometry.Next.Complete);

    // Canary18: the longer-range cast-time Exorcism was accepted when its cast
    // started, but no threat reference existed at the first native Rush. A
    // cast-time action is not a synchronous seed candidate at all.
    assert(IsSynchronousSeedAction(0));
    assert(!IsSynchronousSeedAction(1500));
    assert(!HasPositiveThreatDelta(0.0f, 0.0f));
    assert(!HasPositiveThreatDelta(10.0f, 10.0f));
    assert(HasPositiveThreatDelta(10.0f, 10.5f));
    assert(PreferSeedAction(true, 35.0f, 1, 90,
        30.0f, 0, 55));
    assert(!PreferSeedAction(true, 30.0f, 0, 55,
        35.0f, 1, 90));

    // The exception is fail-closed if a caller tries to reuse it after a
    // lane has already been accepted.
    State partiallySeeded;
    partiallySeeded.Identity = first;
    partiallySeeded.SeededLanes[0] = true;
    CoordinatorResult staleInitial = AdvanceCoordinator(
        partiallySeeded, initialGeometryGap);
    assert(!staleInitial.Lanes[0].ActionAttempted
        && !staleInitial.Lanes[1].ActionAttempted);
    assert(!staleInitial.Next.Complete);

    // Once the bounded opportunity is over, the live source geometry gates
    // remain mandatory even when both candidates are otherwise ready.
    CoordinatorInput afterInitialGeometryGap = bothTick;
    afterInitialGeometryGap.SeparationSafe = false;
    afterInitialGeometryGap.FrozenLanesSafe = false;
    CoordinatorResult afterInitialGeometry = AdvanceCoordinator(
        State{}, afterInitialGeometryGap);
    assert(afterInitialGeometry.BothLanesEvaluated);
    assert(!afterInitialGeometry.Lanes[0].ActionAttempted
        && !afterInitialGeometry.Lanes[1].ActionAttempted);
    assert(!afterInitialGeometry.Next.Complete);

    // The state machine keeps ownership as a real gate.  The route coordinator
    // admits the bounded pre-taunt exception only after proving its local
    // staged, empty-seed, no-Rush window and setting this input accordingly.
    CoordinatorInput noOwnership = bothTick;
    noOwnership.OwnershipSafe = false;
    CoordinatorResult noOwnershipResult = AdvanceCoordinator(State{}, noOwnership);
    assert(noOwnershipResult.BothLanesEvaluated);
    assert(!noOwnershipResult.Lanes[0].ActionAttempted);
    assert(!noOwnershipResult.Lanes[1].ActionAttempted);
    assert(!noOwnershipResult.Next.Complete);

    // A cohort-linked body-pull recovery gets the same native seed barrier
    // without claiming that historical prepull staging completed.
    CoordinatorInput recoveredTick = bothTick;
    recoveredTick.PrepullStaged = false;
    recoveredTick.RecoveryAuthorityReady = true;
    CoordinatorResult recovered = AdvanceCoordinator(State{}, recoveredTick);
    assert(recovered.BothLanesEvaluated);
    assert(recovered.Next.SeededLanes[0] && recovered.Next.SeededLanes[1]);
    assert(recovered.Next.Complete && !recovered.Next.Failure);

    // A failed native lane preserves the exact rejection gate and cannot
    // manufacture its lane's success from the other lane's cast.
    CoordinatorInput rejectedTick = bothTick;
    rejectedTick.Lanes[1].ActionSucceeded = false;
    rejectedTick.Lanes[1].Rejection = RejectionGate::NativeAction;
    CoordinatorResult rejected = AdvanceCoordinator(State{}, rejectedTick);
    assert(rejected.BothLanesEvaluated);
    assert(rejected.Next.SeededLanes[0] && !rejected.Next.SeededLanes[1]);
    assert(!rejected.Next.Complete);
    assert(rejected.Lanes[1].Rejection == RejectionGate::NativeAction);
    assert(std::string(ToString(rejected.Lanes[1].Rejection)) == "native_action");

    // Native seed submission is a cohort barrier. If one pending lane has no
    // candidate, the ready lane must not submit either, and no lane can be
    // accepted from that partial tick. A later tick with both candidates
    // executes and accepts both lanes.
    State pending;
    pending.Identity = first;
    std::array<bool, 2> oneUnavailable = { true, false };
    assert(!AllPendingLanesReady(pending, oneUnavailable));
    CoordinatorInput heldTick;
    heldTick.Identity = first;
    heldTick.PrepullStaged = true;
    heldTick.SourcesAlive = true;
    heldTick.OwnershipSafe = true;
    heldTick.SeparationSafe = true;
    heldTick.FrozenLanesSafe = true;
    heldTick.Lanes[0] = { true, false, false, true, RejectionGate::PendingLaneBarrier };
    heldTick.Lanes[1] = { false, false, false, true, RejectionGate::PositionUnsafe };
    CoordinatorResult held = AdvanceCoordinator(pending, heldTick);
    assert(held.BothLanesEvaluated);
    assert(!held.Lanes[0].ActionAttempted && !held.Lanes[1].ActionAttempted);
    assert(!held.Next.SeededLanes[0] && !held.Next.SeededLanes[1]);
    assert(!held.Next.Complete);
    assert(held.Lanes[0].Rejection == RejectionGate::PendingLaneBarrier);

    std::array<bool, 2> bothAvailable = { true, true };
    assert(AllPendingLanesReady(held.Next, bothAvailable));
    CoordinatorInput readyTick = heldTick;
    readyTick.Lanes[0] = { true, true, true, true, RejectionGate::None };
    readyTick.Lanes[1] = { true, true, true, true, RejectionGate::None };
    CoordinatorResult accepted = AdvanceCoordinator(held.Next, readyTick);
    assert(accepted.Lanes[0].ActionAttempted && accepted.Lanes[1].ActionAttempted);
    assert(accepted.Next.SeededLanes[0] && accepted.Next.SeededLanes[1]);
    assert(accepted.Next.Complete && !accepted.Next.Failure);
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


def test_worldserver_uses_the_replayed_transition_and_resolved_spell_range():
    implementation = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    lane = (
        ROOT
        / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
        "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp"
    ).read_text(encoding="utf-8")
    lane += (
        ROOT
        / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
        "BotWorldPopulationMgrValidationRouteDrudgeThreat.cpp"
    ).read_text(encoding="utf-8")
    seed = (
        ROOT
        / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
        "BotWorldPopulationMgrValidationRouteDrudgeSeed.cpp"
    ).read_text(encoding="utf-8")
    seed_state = (
        ROOT
        / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
        "BotRaidDrudgeThreatSeedState.h"
    ).read_text(encoding="utf-8")
    drudge_header = (
        ROOT
        / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
        "BotWorldPopulationMgrValidationRouteDrudge.h"
    ).read_text(encoding="utf-8")
    callback = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatLog.cpp"
    ).read_text(encoding="utf-8")

    assert '#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeThreatSeedState.h"' in implementation
    assert '#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeSeed.h"' in lane
    assert "RunDrudgeSeedCoordinator()" in lane
    assert "PhaseResult RunDrudgeSeedCoordinator();" in drudge_header
    assert "DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunDrudgeSeedCoordinator()" in seed
    assert "DrudgeLaneContext::ExactDrudgeAuthorityRoster" in seed
    assert "DrudgeLaneContext::ResolveDrudgeSeedCandidate" in seed
    assert "bool ExactAuthorityRoster" not in seed
    assert "BotRaidDrudgeThreatSeed::CoordinatorResult const transition =" in seed
    assert "AdvanceCoordinator(seedState, input);" in seed
    assert "bothVictimsOwned" in seed
    assert "context.OneBasedSlot != manager.Cohort().Config" in seed
    assert "party.ValidationRouteDrudgeThreatSeedComplete" in seed
    assert "party.ValidationRouteDrudgeThreatSeedClosed" in seed
    assert "party.ValidationRouteDrudgeThreatSeedFailure" in seed
    assert '"drudge_pre_first_rush_seed_rejected:"' in seed
    assert '"drudge_pre_first_rush_seed_approach"' in seed
    assert '"native_action_rejected"' in seed
    assert '"native_action_no_threat_delta"' in seed
    assert "candidates[lane].ActionAttempted" in seed
    assert "for (uint32 lane = 0; lane < candidates.size(); ++lane)" in seed
    assert "Result const transition = Advance(seedState, rushInput);" in callback
    assert "BotClassSpecActionProfileStore::BuildCandidates(candidate, source, profile)" in seed
    assert "EffectiveSeedMaxRange" in seed
    assert "EffectiveSeedMinRange" in seed
    assert "PlanSeedApproach(context, selected, source, laneA" in seed
    assert "manager.MoveBotToPoint(*selected.State, selected.Bot" in seed
    assert "executor.ExecuteCombat(" in seed
    assert "source->GetGUID().GetCounter()" in seed
    assert "candidate.Distance <= candidate.Action.MaxRange" in seed
    assert "selected.Action.SuppressAreaDamage = true" in seed
    assert "selected.Action.MeleeAutoAttackExternallyReconciled = true" in seed
    seed_categories = seed[
        seed.index("bool IsSeedThreatCategory") : seed.index("float EffectiveSeedMaxRange")
    ]
    assert "BotCombatActionCategory::Taunt" not in seed_categories
    assert "ImmediateOwnershipRestoreReady" not in seed
    assert '"drudge_seed_native_taunt"' not in seed
    assert "category == BotCombatActionCategory::Cleave" not in seed
    assert 'roster->second.Role != "tank"' in seed
    assert "maxRange <= minimumSafeRange" in seed
    assert 'selected.Action.AutoAttackMode == "ranged"' not in seed
    assert "AllPendingLanesReady" in seed
    assert "allPendingCandidatesReady" in seed
    assert "SeedGate::PendingLaneBarrier" in seed
    assert "input.InitialSeedOpportunity = initialSeedOpportunity" in seed
    assert "InitialSeedGeometryReady" in seed
    assert "InitialSeedOpportunity" in seed_state
    assert "inline bool InitialSeedGeometryReady" in seed_state
    selection = (
        ROOT
        / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeSeedActionSelection.h"
    ).read_text(encoding="utf-8")
    assert "inline bool IsSynchronousSeedAction" in selection
    assert "inline bool PreferSeedAction" in selection
    assert "if (allPendingCandidatesReady)" in seed
    assert "BotRaidDrudgeSeedActionSelection::IsSynchronousSeedAction(" in seed
    assert "BotRaidDrudgeSeedActionSelection::HasPositiveThreatDelta(" in seed
    assert "BotRaidDrudgeSeedActionSelection::PreferSeedAction(" in seed
    assert "actionCandidate.CastTimeMs" in seed
    assert seed.index("if (allPendingCandidatesReady)") < seed.index(
        "executor.ExecuteCombat"
    )

    roster_gate = seed.index("bool DrudgeLaneContext::ExactDrudgeAuthorityRoster")
    assert "!member->IsInWorld() || !member->IsAlive()" in seed[roster_gate:]
    assert "!roster->second.Active || !roster->second.LeaseOwned" in seed[roster_gate:]
    suppression = seed.index("void DrudgeLaneContext::SuppressAllDrudgeOffense")
    release = seed.index("SetAllOffenseSuppressed(guid, false)", suppression)
    assert suppression < release

    resolver = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
    ).read_text(encoding="utf-8")
    assert 'hostileTargetOnly && candidate.Profile.TargetSelector != "enemy"' in resolver
    assert 'candidate.RejectReason = "hostile_target_required"' in resolver

    regular_action = lane.index("bool const valid = profileAction.Valid")
    regular_insert = lane.index(
        "ValidationRouteDrudgeProfileActionRosterGuids.insert", regular_action
    )
    assert lane.count("ValidationRouteDrudgeProfileActionRosterGuids.insert") == 1
    assert lane.index("&& !ExactRosterReSeparated()") < regular_insert
    assert 'profileAction.TargetGuid == LaneSource->GetGUID()' in lane[
        regular_action:regular_insert
    ]
    assert "if (succeeded)" in lane[regular_action:regular_insert]

    executor = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatExecution.cpp"
    ).read_text(encoding="utf-8")
    assert "allowMultidot && !forbidArea, hostileTargetOnly" in " ".join(
        executor.split()
    )
    assert "!hostileTargetOnly && state && TryEnsurePersistentCombatSetup" in executor
    assert "!hostileTargetOnly && state" in executor
    assert "&& TryEnsureCombatTotems" in executor


def test_profile_candidates_publish_live_cast_time_to_seed_selector():
    source = (
        ROOT / "src/server/game/Bots/BotClassSpecActionProfileCandidates.cpp"
    ).read_text(encoding="utf-8")
    build_candidates = source[
        source.index(
            "std::vector<BotActionCandidate> "
            "BotClassSpecActionProfileStore::BuildCandidates"
        ) : source.index(
            "std::string BotClassSpecActionProfileStore::CandidateMaskJson"
        )
    ]

    spell_info = (
        "SpellInfo const* spellInfo = spell.SpellId ? "
        "sSpellMgr->GetSpellInfo(spell.SpellId) : nullptr;"
    )
    cast_time_assignment = (
        "candidate.CastTimeMs = ProfileSpellCastTimeMs(bot, spellInfo);"
    )
    assert spell_info in build_candidates
    assert build_candidates.count(cast_time_assignment) == 1
    assert build_candidates.index(spell_info) < build_candidates.index(
        cast_time_assignment
    )
    assert build_candidates.index(cast_time_assignment) < build_candidates.index(
        "else if (spellInfo && spell.RequiresInstantCast"
    )
    assert "candidate.CastTimeMs = 0" not in build_candidates


def test_drudge_seed_approach_preserves_lane_and_native_range(tmp_path):
    source = tmp_path / "drudge_seed_approach.cpp"
    binary = tmp_path / "drudge_seed_approach"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeSeedApproach.h"
#include <cassert>
#include <cmath>

using namespace BotRaidDrudgeSeedApproach;

int main()
{
    Input paladin;
    paladin.Actor = {18.0f, 0.0f, 2.0f};
    paladin.Source = {-15.5f, 0.0f, 2.0f};
    paladin.AxisX = 1.0f;
    paladin.LaneSign = 1.0f;
    paladin.MinimumLaneProjection = 3.75f;
    paladin.MinimumSourceDistance = 16.0f;
    paladin.ActionMaxRange = 30.0f;
    Result ranged = Plan(paladin);
    assert(ranged.Needed && ranged.Safe);
    assert(std::fabs(ranged.DesiredDistance - 29.0f) < 0.001f);
    assert(ranged.Destination.X >= 3.75f);

    Input blockedLos = paladin;
    blockedLos.Actor = {18.0f, 0.0f, 2.0f};
    blockedLos.Source = {-7.0f, 0.0f, 2.0f};
    blockedLos.ActionMaxRange = 35.0f;
    blockedLos.LineOfSightBlocked = true;
    Result losStep = Plan(blockedLos);
    assert(losStep.Needed && losStep.Safe);
    assert(std::fabs(losStep.Travel - 3.0f) < 0.001f);
    assert(std::fabs(losStep.DesiredDistance - 22.0f) < 0.001f);

    Input deathKnight = paladin;
    deathKnight.Actor = {18.0f, 4.0f, 2.0f};
    deathKnight.Source = {-12.0f, 4.0f, 2.0f};
    deathKnight.ActionMaxRange = 20.0f;
    Result threatBuild = Plan(deathKnight);
    assert(threatBuild.Needed && threatBuild.Safe);
    assert(std::fabs(threatBuild.DesiredDistance - 19.0f) < 0.001f);

    Input melee = paladin;
    melee.ActionMaxRange = 10.0f;
    Result rejected = Plan(melee);
    assert(!rejected.Safe && !rejected.Needed);

    Input crossesLane = deathKnight;
    crossesLane.Actor = {5.0f, 0.0f, 0.0f};
    crossesLane.Source = {-30.0f, 0.0f, 0.0f};
    crossesLane.ActionMaxRange = 20.0f;
    Result unsafe = Plan(crossesLane);
    assert(unsafe.Needed && !unsafe.Safe);
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
