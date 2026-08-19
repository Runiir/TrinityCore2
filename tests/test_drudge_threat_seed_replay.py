import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_production_drudge_seed_transition_replays_native_event_orderings(tmp_path):
    source = tmp_path / "drudge_seed_replay.cpp"
    binary = tmp_path / "drudge_seed_replay"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeThreatSeedState.h"
#include <cassert>

using namespace BotRaidDrudgeThreatSeed;

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
    callback = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatLog.cpp"
    ).read_text(encoding="utf-8")

    assert '#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeThreatSeedState.h"' in implementation
    assert "BotRaidDrudgeThreatSeed::Result seedTransition =" in lane
    assert "Advance(seedState, seedInput);" in lane
    assert "seedInput.Type = Event::ActionResult;" in lane
    assert "Result const transition = Advance(seedState, rushInput);" in callback
    assert "candidate, LaneSource, 1, false, 0, false, false, true, false, true" in lane
    assert "selected, LaneSource, 1, false, 0, false, false, true, false, true" in lane
    assert "1, false, 0, false, false, true, false, true" in lane
    assert 'candidateAction.MovementDirective != "ranged"' in lane
    assert "candidateAction.MaxRange <= 5.0f" in lane
    assert 'candidateAction.AutoAttackMode == "ranged"' not in lane

    roster_gate = lane.index("bool exactAuthorityRoster")
    roster_hold = lane.index('"drudge_pre_first_rush_seed_roster_wait"', roster_gate)
    assert "!member->IsInWorld() || !member->IsAlive()" in lane[roster_gate:roster_hold]
    assert "!roster->second.Active || !roster->second.LeaseOwned" in lane[
        roster_gate:roster_hold
    ]
    assert "authorityRosterGuids.size() != Manager.Cohort().Raid.RosterByGuid.size()" in lane[
        roster_gate:roster_hold
    ]
    suppression = lane.index(
        "for (WorldBotState const& memberState : Manager.Party().Bots)",
        roster_hold,
    )
    release = lane.index(
        "BotRaidAreaAuthority::SetAllOffenseSuppressed(\n"
        "            selected->GetGUID().GetRawValue(), false)",
        suppression,
    )
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
