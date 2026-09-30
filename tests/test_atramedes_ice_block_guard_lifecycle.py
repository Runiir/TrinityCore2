"""BWD 10N round 3, v4 review (Atramedes): the once-per-fight Ice Block memory belongs to the fight.

The v4 review reproduced, with the production guard (BotAtramedesIceBlockGuard.h): `.botexp start` on an
active AlwaysOnAutonomy default cohort advances the cohort's combat-log lifecycle (CombatLogEpoch, by
ResetCombatLog) without ending the fight, and the guard replaced its record whenever the
ObservationAttempt (lifecycle, attempt id) changed: Spent went from 1 to 0 with Atramedes still engaged,
and the ready mage played the rescue a second time.

The fix: the record is keyed by cohort and attempt id only. It ends with the fight:
- Atramedes out of combat in a snapshot (PrePull, the evade or respawn after a wipe);
- the snapshot's wipe generation (Scope::WipeGeneration) moved since the record's last snapshot;
- a new attempt id.
A combat-log lifecycle change alone changes nothing. Cohort scoping (cohort, attempt id, encounter node)
is unchanged.

The program also replays the pre-fix guard (the record replaced on any ObservationAttempt change) as the
reproduction. Also under the sanitizers.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_atramedes_observation_scope import ROOT, _compile_and_run

FOLDER = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes"
GUARD = FOLDER / "BotAtramedesIceBlockGuard.h"
ADAPTER = FOLDER / "BotWorldPopulationMgrAtramedesCandidates.cpp"


PROGRAM = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesIceBlockGuard.h"
#include <cstdio>
#include <map>
#include <mutex>
#include <string>

static int failures = 0;
#define CHECK(condition, message) do { if (!(condition)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, message); ++failures; } } while (0)

using namespace BotEncounter;
using namespace BotEncounter::Atramedes;

static std::string const Cohort = "blackwing_descent_10n_atramedes_c0";
static uint64 const AttemptId = 3;

static ObjectGuid PlayerGuid(uint32 counter) { return ObjectGuid(HighGuid::Player, counter); }
static ObjectGuid UnitGuid(uint32 entry, uint32 counter) { return ObjectGuid(HighGuid::Unit, entry, counter); }

// Atramedes engaged, `players` living players, nobody under Ice Block.
static Blackboard Board(uint64 attempt = AttemptId, uint32 wipeGeneration = 0)
{
    Blackboard board;
    board.Route.NodeId = std::string(EncounterNode);
    board.CurrentScope.CohortId = Cohort;
    board.CurrentScope.AttemptId = attempt;
    board.CurrentScope.WipeGeneration = wipeGeneration;
    board.CurrentScope.MapId = 669;
    board.CurrentScope.InstanceId = 7;
    ActorSnapshot boss;
    boss.Guid = UnitGuid(BossEntry, 1);
    boss.Entry = BossEntry;
    boss.Kind = ActorKind::Summon;
    boss.Alive = true;
    boss.InCombat = true;
    board.Summons.push_back(boss);
    for (uint32 counter = 1; counter <= 3; ++counter)
    {
        ActorSnapshot player;
        player.Guid = PlayerGuid(counter);
        player.Kind = ActorKind::Player;
        player.Alive = true;
        board.Players.push_back(player);
    }
    return board;
}

static Blackboard Iced(Blackboard board)
{
    board.Players[1].Auras.push_back({ IceBlockAura, PlayerGuid(2), 0, board.ObservedAtMs + 10000 });
    return board;
}

static Blackboard Wiped(Blackboard board)
{
    board.Summons.front().InCombat = false;
    return board;
}

// The guard as it was at the v4 review: the record replaced on any change of the ObservationAttempt.
class LegacyGuard
{
public:
    void Observe(std::string const& cohortId, ObservationAttempt attempt, Blackboard const& board)
    {
        Scope const& scope = board.CurrentScope;
        if (!attempt.AttemptId || scope.CohortId != cohortId || scope.AttemptId != attempt.AttemptId
            || board.Route.NodeId != EncounterNode)
            return;
        ActorSnapshot const* boss = FindBoss(board);
        if (!boss)
            return;
        Record& record = _cohorts[cohortId];
        if (record.Attempt != attempt)
        {
            record = Record();
            record.Attempt = attempt;
        }
        if (!boss->InCombat)
        {
            record.Spent = false;
            return;
        }
        for (ActorSnapshot const& player : board.Players)
            if (player.Alive && FindAura(player, IceBlockAura))
                record.Spent = true;
    }
    bool Spent(std::string const& cohortId, std::uint64_t attemptId) const
    {
        auto const found = _cohorts.find(cohortId);
        return found != _cohorts.end() && attemptId
            && found->second.Attempt.AttemptId == attemptId && found->second.Spent;
    }

private:
    struct Record { ObservationAttempt Attempt; bool Spent = false; };
    std::map<std::string, Record> _cohorts;
};

// The reviewer's scenario: the mage blocks, the recording restarts (lifecycle 1 -> 2, then 3) while
// Atramedes stays engaged.
static void TestRestartWhileEngaged()
{
    ObservationAttempt const first{ 1, AttemptId };
    ObservationAttempt const second{ 2, AttemptId };
    ObservationAttempt const third{ 3, AttemptId };

    // Control: before any restart the block is remembered.
    IceBlockGuard guard;
    guard.Observe(Cohort, first, Iced(Board()));
    CHECK(guard.Spent(Cohort, AttemptId), "the block seen in the fight is spent");

    // The reproduction: the same engaged boss, the lifecycle moves on.
    LegacyGuard legacy;
    legacy.Observe(Cohort, first, Iced(Board()));
    CHECK(legacy.Spent(Cohort, AttemptId), "legacy: spent");
    legacy.Observe(Cohort, second, Board());
    CHECK(!legacy.Spent(Cohort, AttemptId), "before the fix: a restart while engaged forgot the block (v4)");

    guard.Observe(Cohort, second, Board());  // the ice has expired in this snapshot
    CHECK(guard.Spent(Cohort, AttemptId), "lifecycle 1 -> 2 with Atramedes engaged: Spent stays 1");
    guard.Observe(Cohort, second, Board());  // every bot offers it
    guard.Observe(Cohort, third, Board());
    CHECK(guard.Spent(Cohort, AttemptId), "lifecycle 2 -> 3: still spent");
    // The first snapshot of the new lifecycle may also still show the block: idempotent.
    guard.Observe(Cohort, third, Iced(Board()));
    CHECK(guard.Spent(Cohort, AttemptId), "and spent");

    // A block first seen after a restart is recorded under the new lifecycle.
    IceBlockGuard late;
    late.Observe(Cohort, first, Board());
    late.Observe(Cohort, second, Iced(Board()));
    CHECK(late.Spent(Cohort, AttemptId), "a block seen after the restart counts");
    late.Observe(Cohort, first, Board());  // an older lifecycle's snapshot offered late changes nothing
    CHECK(late.Spent(Cohort, AttemptId), "a late snapshot of the old lifecycle changes nothing");

    // Atramedes absent from a snapshot (dead, or not yet observed) neither spends nor clears it.
    Blackboard gone = Board();
    gone.Summons.clear();
    guard.Observe(Cohort, third, gone);
    CHECK(guard.Spent(Cohort, AttemptId), "no Atramedes in the snapshot: unchanged");
}

// The fight really ends: the record is cleared, and the next fight spends its own block.
static void TestRealWipeResets()
{
    ObservationAttempt const first{ 1, AttemptId };
    ObservationAttempt const second{ 2, AttemptId };

    // The boss out of combat (PrePull, the evade or respawn after a wipe).
    IceBlockGuard guard;
    guard.Observe(Cohort, first, Iced(Board()));
    CHECK(guard.Spent(Cohort, AttemptId), "spent in the first fight");
    guard.Observe(Cohort, first, Wiped(Board()));
    CHECK(!guard.Spent(Cohort, AttemptId), "Atramedes out of combat: a new pull");
    guard.Observe(Cohort, first, Board());
    CHECK(!guard.Spent(Cohort, AttemptId), "the new fight starts unspent");
    guard.Observe(Cohort, first, Iced(Board()));
    CHECK(guard.Spent(Cohort, AttemptId), "and spends its own block");

    // A wipe that also changed the lifecycle: the wipe still resets it.
    IceBlockGuard restartedWipe;
    restartedWipe.Observe(Cohort, first, Iced(Board()));
    restartedWipe.Observe(Cohort, second, Board());
    CHECK(restartedWipe.Spent(Cohort, AttemptId), "the restart alone keeps it");
    restartedWipe.Observe(Cohort, second, Wiped(Board()));
    CHECK(!restartedWipe.Spent(Cohort, AttemptId), "the wipe after the restart resets it");

    // The wipe generation moved (the raid wiped) although no snapshot caught the boss out of combat: the
    // boss may still be in combat (evading) when the bots stand up.
    IceBlockGuard wipe;
    wipe.Observe(Cohort, first, Iced(Board(AttemptId, 0)));
    CHECK(wipe.Spent(Cohort, AttemptId), "spent in generation 0");
    wipe.Observe(Cohort, first, Board(AttemptId, 0));
    CHECK(wipe.Spent(Cohort, AttemptId), "the same generation keeps it");
    wipe.Observe(Cohort, first, Board(AttemptId, 1));
    CHECK(!wipe.Spent(Cohort, AttemptId), "a wipe (generation 1) resets it with the boss still in combat");
    wipe.Observe(Cohort, first, Iced(Board(AttemptId, 1)));
    CHECK(wipe.Spent(Cohort, AttemptId), "the next fight spends its own block");
    wipe.Observe(Cohort, second, Board(AttemptId, 1));
    CHECK(wipe.Spent(Cohort, AttemptId), "and a restart inside it keeps that one");

    // A guard first seeing generation 2 (a process that joined late) starts on it, not as a wipe.
    IceBlockGuard joined;
    joined.Observe(Cohort, first, Iced(Board(AttemptId, 2)));
    CHECK(joined.Spent(Cohort, AttemptId), "a first snapshot in a later generation is recorded");
}

// A new attempt id is a new record; cohort scoping is unchanged.
static void TestNewAttemptAndScoping()
{
    ObservationAttempt const first{ 1, AttemptId };
    IceBlockGuard guard;
    guard.Observe(Cohort, first, Iced(Board()));
    CHECK(guard.Spent(Cohort, AttemptId), "spent");
    guard.Observe(Cohort, ObservationAttempt{ 1, AttemptId + 1 }, Board(AttemptId + 1));
    CHECK(!guard.Spent(Cohort, AttemptId + 1), "a new attempt id starts unspent");
    CHECK(!guard.Spent(Cohort, AttemptId), "and replaces the old attempt's record");
    // The new attempt is also a new lifecycle usually: also clean when the old block is still in the snapshot.
    IceBlockGuard replaced;
    replaced.Observe(Cohort, first, Iced(Board()));
    replaced.Observe(Cohort, ObservationAttempt{ 2, AttemptId + 1 }, Board(AttemptId + 1));
    CHECK(!replaced.Spent(Cohort, AttemptId + 1) && !replaced.Spent(Cohort, AttemptId), "new attempt id, new lifecycle");

    // Cohort scoping: another cohort never reads or writes this record; a snapshot of another cohort or
    // attempt, or off the encounter node, is never observed; a cohort that never ran Atramedes has no record.
    IceBlockGuard strict;
    Blackboard foreign = Iced(Board());
    foreign.CurrentScope.CohortId = "foreign";
    strict.Observe(Cohort, first, foreign);
    Blackboard stale = Iced(Board(AttemptId - 1));
    strict.Observe(Cohort, first, stale);
    Blackboard elsewhere = Iced(Board());
    elsewhere.Route.NodeId = "bwd.nefarian.encounter";
    strict.Observe(Cohort, first, elsewhere);
    strict.Observe(Cohort, ObservationAttempt{ 1, 0 }, Iced(Board()));
    CHECK(!strict.Spent(Cohort, AttemptId) && !strict.Spent("foreign", AttemptId)
        && !strict.Spent(Cohort, AttemptId - 1), "nothing else is observed");
    strict.Observe(Cohort, first, Iced(Board()));
    CHECK(strict.Spent(Cohort, AttemptId) && !strict.Spent("other_cohort", AttemptId)
        && !strict.Spent(Cohort, 0), "the record is this cohort's and this attempt's");
    // A restart of another cohort's recording never touches this cohort's record.
    Blackboard other = Board();
    other.CurrentScope.CohortId = "other_cohort";
    strict.Observe("other_cohort", ObservationAttempt{ 2, AttemptId }, other);
    CHECK(strict.Spent(Cohort, AttemptId) && !strict.Spent("other_cohort", AttemptId),
        "cohorts keep separate records");
    // Evidence only while engaged: a block on trash before the pull is another fight's.
    IceBlockGuard trash;
    trash.Observe(Cohort, first, Wiped(Iced(Board())));
    CHECK(!trash.Spent(Cohort, AttemptId), "a block seen before the pull counts for nothing");
    // A dead mage under no aura is no evidence.
    Blackboard dead = Iced(Board());
    dead.Players[1].Alive = false;
    trash.Observe(Cohort, first, dead);
    CHECK(!trash.Spent(Cohort, AttemptId), "a dead player is no evidence");
}

int main()
{
    TestRestartWhileEngaged();
    TestRealWipeResets();
    TestNewAttemptAndScoping();
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    else
        std::printf("ok\n");
    return failures ? 1 : 0;
}
'''


def test_ice_block_memory_survives_a_recording_restart(tmp_path: Path) -> None:
    assert _compile_and_run(tmp_path, PROGRAM).strip() == "ok"


def test_ice_block_memory_survives_a_recording_restart_under_sanitizers(tmp_path: Path) -> None:
    assert _compile_and_run(tmp_path, PROGRAM, sanitize=True).strip() == "ok"


def test_guard_identity_is_the_attempt_id_not_the_lifecycle() -> None:
    guard = GUARD.read_text(encoding="utf-8")
    assert "if (record.AttemptId != attempt.AttemptId)" in guard
    assert "else if (record.WipeGeneration != scope.WipeGeneration)" in guard
    assert "record.Attempt != attempt" not in guard
    assert "ObservationAttempt Attempt;" not in guard
    # Cohort scoping is unchanged.
    assert ("if (!attempt.AttemptId || scope.CohortId != cohortId || scope.AttemptId != attempt.AttemptId\n"
            "            || board.Route.NodeId != EncounterNode)") in guard
    assert "found->second.AttemptId == attemptId && found->second.Spent" in guard
    adapter = ADAPTER.read_text(encoding="utf-8")
    assert ("BotEncounter::Atramedes::ProcessIceBlockGuard().Observe(Cohort().Id,\n"
            "            observationAttempt, *Cohort().EncounterSnapshot);") in adapter
    assert len(guard.splitlines()) < 1000 and len(adapter.splitlines()) < 1000
