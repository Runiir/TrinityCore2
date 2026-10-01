"""BWD 10N round 3 fix (Atramedes): the kiter Sound observation is sampled per cohort attempt and instance.

The program drives the production store (BotAtramedesObservationStore.h) with encounter snapshots, as the
kernel adapter (BotWorldPopulationMgrAtramedesCandidates.cpp) offers them on every bot decision:
- a chase is the run of snapshots in which the Reverberating Flame follows one player (its Tracking target,
  or the iced mage it keeps following): a redirect, another target or the landing ends it, and only the
  chased player's Sound is sampled, once per snapshot however many bots read it;
- the observations are scoped like the Nefarian ones (cohort, start lifecycle and attempt id, map instance):
  parallel shards never share a record, a new attempt starts clean, and a reused cohort (Stonecore,
  calibration, legacy Magmaw) exports what a process that never ran Atramedes does;
- `complete` needs affirmative coverage: an instance change, a clock that went back, or a sampling gap that
  could hide Sound (over 1 s next to the air phase, over 5 s starting in a ground engagement, whatever the
  next snapshot is: a boss-absent or other-route snapshot after a long outage proves nothing) ends it.
Also under the sanitizers. The counters and the wiring are checked in
tests/test_atramedes_observation_counters.py.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.test_atramedes_strategy import INCLUDES, ROOT

SANITIZERS = ["-fsanitize=address,undefined", "-fsanitize-address-use-after-scope", "-fno-omit-frame-pointer",
              "-fno-sanitize-recover=all", "-g", "-O1"]


def _compile_and_run(tmp_path: Path, program: str, sanitize: bool = False) -> str:
    source, binary = tmp_path / "program.cpp", tmp_path / "program"
    source.write_text(program, encoding="utf-8")
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES, str(source), "-o", str(binary)]
    if sanitize:
        command[1:1] = SANITIZERS
    subprocess.run(command, check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return result.stdout


PROGRAM = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesObservationStore.h"
#include <cstdio>
#include <string>
#include <string_view>

static int failures = 0;
#define CHECK(condition, message) do { if (!(condition)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, message); ++failures; } } while (0)

using namespace BotEncounter;
using namespace BotEncounter::Atramedes;

static uint64 const T0 = 1790000000000ull;
static ObservationAttempt const Attempt1{ 1, 1 };
static uint32 const FlameCounter = 900;

static ObjectGuid PlayerGuid(uint32 counter) { return ObjectGuid(HighGuid::Player, counter); }
static ObjectGuid UnitGuid(uint32 entry, uint32 counter) { return ObjectGuid(HighGuid::Unit, entry, counter); }

// Atramedes engaged on the ground in `instance`, three players with a Sound Bar.
static Blackboard Board(std::string const& cohort, uint64 attempt, uint32 instance)
{
    Blackboard board;
    board.Route.NodeId = std::string(EncounterNode);
    board.CurrentScope.CohortId = cohort;
    board.CurrentScope.AttemptId = attempt;
    board.CurrentScope.MapId = 669;
    board.CurrentScope.InstanceId = instance;
    ActorSnapshot boss;
    boss.Guid = UnitGuid(BossEntry, 1);
    boss.Entry = BossEntry;
    boss.Kind = ActorKind::Summon;
    boss.Alive = true;
    boss.InCombat = true;
    boss.ReactAggressive = true;
    board.Summons.push_back(boss);
    for (uint32 counter = 1; counter <= 3; ++counter)
    {
        ActorSnapshot player;
        player.Guid = PlayerGuid(counter);
        player.Kind = ActorKind::Player;
        player.Alive = true;
        player.MaxAlternatePower = 100;
        player.Position = { 145.0f + float(counter) * 10.0f, -225.0f, 75.0f };
        board.Players.push_back(player);
    }
    return board;
}

static ActorSnapshot& Player(Blackboard& board, uint32 counter) { return board.Players[counter - 1]; }

static void Liftoff(Blackboard& board)
{
    board.Summons.front().Flying = true;
    board.Summons.front().ReactAggressive = false;
}

static void Land(Blackboard& board)
{
    board.Summons.front().Flying = false;
    board.Summons.front().ReactAggressive = true;
    board.Summons.resize(1);
    for (ActorSnapshot& player : board.Players)
        player.Auras.clear();
}

// The flame tracks `counter` (its Tracking aura on the player, cast by the flame), or nobody (0: a redirect).
static void Track(Blackboard& board, uint32 counter)
{
    board.Summons.resize(1);
    for (ActorSnapshot& player : board.Players)
        player.Auras.clear();
    ActorSnapshot flame;
    flame.Guid = UnitGuid(ReverberatingFlameEntry, FlameCounter);
    flame.Entry = ReverberatingFlameEntry;
    flame.Kind = ActorKind::Summon;
    flame.Alive = true;
    flame.Position = { 146.0f, -225.0f, 75.0f };
    board.Summons.push_back(flame);
    if (counter)
        Player(board, counter).Auras.push_back({ TrackingAura, flame.Guid, 0, 0 });
}

static void Sound(Blackboard& board, uint32 counter, uint32 sound)
{
    Player(board, counter).AlternatePower = sound;
}

// As the adapter does on one bot decision: the plan owns the node, then the snapshot is offered.
static void Offer(ObservationStore& store, std::string const& cohort, ObservationAttempt attempt,
    Blackboard& board, uint64 at, bool owns = true)
{
    board.ObservedAtMs = at;
    if (owns)
        store.Begin(cohort, attempt);
    store.Observe(cohort, attempt, board);
}

// The block with its observation times (the first and newest sample's time, system ms) zeroed: these checks
// compare the counters and the coverage flag; TestObservationTimes checks the times.
static std::string ZeroTimes(std::string json)
{
    size_t const at = json.find(",\"first_observed_at_ms\":");
    return at == std::string::npos ? json
        : json.substr(0, at) + ",\"first_observed_at_ms\":0,\"last_observed_at_ms\":0}}";
}

static uint64 TimeField(std::string const& json, std::string const& key)
{
    size_t const at = json.find("\"" + key + "\":");
    return at == std::string::npos ? ~0ull : std::stoull(json.substr(at + key.size() + 3));
}

static std::string Block(ObservationStore const& store, std::string const& cohort, ObservationAttempt attempt,
    std::string_view route = EncounterNode, std::string const& field = "")
{
    return ZeroTimes(store.JsonField(field, cohort, attempt, route));
}

// The block names the attempt and its start lifecycle (combat_log_epoch), which run_sanity binds to the
// judged combat-log capture.
static std::string Expected(int air, int chases, int samples, int maxSound, int above, int gap, bool complete,
    ObservationAttempt attempt)
{
    return ",\"encounter_observations\":{\"atramedes\":{\"air_phases\":" + std::to_string(air)
        + ",\"chases\":" + std::to_string(chases) + ",\"chase_samples\":" + std::to_string(samples)
        + ",\"max_kiter_sound\":" + std::to_string(maxSound) + ",\"samples_above_10\":" + std::to_string(above)
        + ",\"max_sample_gap_ms\":" + std::to_string(gap) + ",\"complete\":" + (complete ? "true" : "false")
        + ",\"attempt_id\":" + std::to_string(attempt.AttemptId)
        + ",\"combat_log_epoch\":" + std::to_string(attempt.Lifecycle)
        + ",\"first_observed_at_ms\":0,\"last_observed_at_ms\":0}}";
}

// One air phase: a chase of player 2 (0 to 9 Sound), a redirect to the striker 3 (every bar reset), a
// chase of 3; ten bots offer every snapshot, and the loudest bystander never counts.
static void TestChaseSampling()
{
    ObservationStore store;
    Blackboard board = Board("shard", 1, 7);
    uint64 at = T0;
    for (int step = 0; step < 4; ++step)
        Offer(store, "shard", Attempt1, board, at += 250);
    Liftoff(board);
    Offer(store, "shard", Attempt1, board, at += 250);
    Sound(board, 1, 80);  // a bystander at 80 Sound: not the kiter
    Track(board, 2);
    for (uint32 sound : { 0u, 3u, 6u, 9u })
    {
        Sound(board, 2, sound);
        at += 250;
        for (int bot = 0; bot < 10; ++bot)  // every bot reads the same snapshot
            Offer(store, "shard", Attempt1, board, at);
    }
    CHECK(Block(store, "shard", Attempt1) == Expected(1, 1, 4, 9, 0, 250, true, Attempt1), "one chase, sampled once per snapshot");
    // The strike: every bar at 0, the flame waits and flies to the shield (nobody tracked), then the striker.
    for (uint32 counter = 1; counter <= 3; ++counter)
        Sound(board, counter, 0);
    Track(board, 0);
    Offer(store, "shard", Attempt1, board, at += 250);
    Track(board, 3);
    Offer(store, "shard", Attempt1, board, at += 250);
    Sound(board, 3, 12);
    Offer(store, "shard", Attempt1, board, at += 250);
    CHECK(Block(store, "shard", Attempt1) == Expected(1, 2, 6, 12, 1, 250, true, Attempt1), "the striker's chase, above 10");
    // A dead kiter is no sample; the iced mage the flame keeps following (no Tracking aura) is one.
    Player(board, 3).Alive = false;
    Offer(store, "shard", Attempt1, board, at += 250);
    CHECK(Block(store, "shard", Attempt1) == Expected(1, 2, 6, 12, 1, 250, true, Attempt1), "a dead kiter is not sampled");
    Player(board, 3).Alive = true;
    Track(board, 0);
    Player(board, 1).Auras.push_back({ IceBlockAura, PlayerGuid(1), 0, 0 });
    Player(board, 1).Position = { 147.0f, -225.0f, 75.0f };
    Sound(board, 1, 4);
    Offer(store, "shard", Attempt1, board, at += 250);
    CHECK(Block(store, "shard", Attempt1) == Expected(1, 3, 7, 12, 1, 250, true, Attempt1), "the iced mage's chase");
    // The landing ends the air phase; the next liftoff is a second one.
    Land(board);
    Offer(store, "shard", Attempt1, board, at += 250);
    Liftoff(board);
    Track(board, 2);
    Offer(store, "shard", Attempt1, board, at += 250);
    CHECK(Block(store, "shard", Attempt1) == Expected(2, 4, 8, 12, 1, 250, true, Attempt1), "a second air phase");
    // Another node's snapshot (the route moved on) is not engaged: no chase.
    Blackboard elsewhere = board;
    elsewhere.Route.NodeId = "bwd.nefarian.encounter";
    Offer(store, "shard", Attempt1, elsewhere, at += 250);
    CHECK(Block(store, "shard", Attempt1) == Expected(2, 4, 8, 12, 1, 250, true, Attempt1), "no chase off the node");
    CHECK(SampleChase(elsewhere).Engaged == false, "off the encounter node nothing is engaged");
}

// Scope: the cohort's attempt (start lifecycle and attempt id) and the instance sampling binds to.
static void TestAttemptAndInstanceScope()
{
    ObservationStore store;
    CHECK(!store.Begin("shard", ObservationAttempt{ 1, 0 }), "attempt 0 is never an attempt");
    CHECK(Block(store, "shard", Attempt1) == Expected(0, 0, 0, 0, 0, 0, false, Attempt1), "nothing begun: a fresh block");
    Blackboard board = Board("shard", 1, 7);
    board.ObservedAtMs = T0;
    store.Observe("shard", Attempt1, board);
    CHECK(Block(store, "shard", Attempt1) == Expected(0, 0, 0, 0, 0, 0, false, Attempt1), "a snapshot before Begin is no sample");
    CHECK(store.Begin("shard", Attempt1), "attempt 1 live");
    CHECK(Block(store, "shard", Attempt1) == Expected(0, 0, 0, 0, 0, 0, false, Attempt1), "begun but not sampled: not complete");
    Liftoff(board);
    Track(board, 2);
    Sound(board, 2, 30);
    Offer(store, "shard", Attempt1, board, T0 + 250);
    CHECK(Block(store, "shard", Attempt1) == Expected(1, 1, 1, 30, 1, 0, true, Attempt1), "attempt 1's sample");

    // Parallel shards in one worldserver: another cohort's identical instance id and player guids never mix.
    Blackboard other = Board("other", 1, 7);
    Liftoff(other);
    Track(other, 2);
    Offer(store, "other", Attempt1, other, T0 + 250);
    CHECK(Block(store, "other", Attempt1) == Expected(1, 1, 1, 0, 0, 0, true, Attempt1), "the other shard's own chase");
    CHECK(Block(store, "shard", Attempt1) == Expected(1, 1, 1, 30, 1, 0, true, Attempt1), "unchanged by it");

    // A new attempt in the same instance starts clean; so does a restart that keeps the attempt id.
    ObservationAttempt const attempt2{ 1, 2 };
    Blackboard second = board;
    second.CurrentScope.AttemptId = 2;
    Sound(second, 2, 0);
    Offer(store, "shard", attempt2, second, T0 + 500);
    CHECK(Block(store, "shard", attempt2) == Expected(1, 1, 1, 0, 0, 0, true, attempt2), "a new attempt: its own counters");
    CHECK(Block(store, "shard", Attempt1) == Expected(0, 0, 0, 0, 0, 0, false, Attempt1), "the old attempt is stale");
    ObservationAttempt const restarted{ 2, 2 };
    Offer(store, "shard", restarted, second, T0 + 750);
    CHECK(Block(store, "shard", attempt2) == Expected(0, 0, 0, 0, 0, 0, false, attempt2),
        "the earlier lifecycle's counts never pass as the restart's");

    // Snapshots of another attempt or cohort, or of no map, are never samples.
    ObservationAttempt const attempt3{ 2, 3 };
    CHECK(store.Begin("shard", attempt3), "attempt 3 live");
    Blackboard stale = second;
    Sound(stale, 2, 50);
    Offer(store, "shard", attempt3, stale, T0 + 1000);
    Blackboard foreign = Board("foreign", 3, 7);
    Liftoff(foreign);
    Track(foreign, 2);
    Sound(foreign, 2, 50);
    Offer(store, "shard", attempt3, foreign, T0 + 1000);
    Blackboard noMap = Board("shard", 3, 7);
    noMap.CurrentScope.MapId = 0;
    Liftoff(noMap);
    Track(noMap, 2);
    Sound(noMap, 2, 50);
    Offer(store, "shard", attempt3, noMap, T0 + 1000);
    Offer(store, "never", Attempt1, foreign, T0 + 1000, false);
    CHECK(Block(store, "shard", attempt3) == Expected(0, 0, 0, 0, 0, 0, false, attempt3), "nothing sampled: not complete");
    CHECK(Block(store, "never", Attempt1, "") == "", "an offer never creates a record");

    // An instance change within the attempt ends the chase and the coverage; counts are kept.
    Blackboard here = Board("shard", 3, 7);
    Liftoff(here);
    Track(here, 2);
    Offer(store, "shard", attempt3, here, T0 + 2000);
    CHECK(Block(store, "shard", attempt3) == Expected(1, 1, 1, 0, 0, 0, true, attempt3), "instance 7");
    Blackboard there = Board("shard", 3, 8);
    Liftoff(there);
    Track(there, 2);
    Sound(there, 2, 5);
    Offer(store, "shard", attempt3, there, T0 + 2250);
    CHECK(Block(store, "shard", attempt3) == Expected(2, 2, 2, 5, 0, 0, false, attempt3),
        "instance 8: a new chase, complete false");
}

// Coverage: a sampling gap that could hide Sound, or a clock that went back, is no complete zero.
static void TestCoverage()
{
    auto air = [](ObservationStore& store, uint64 firstGap, uint64 secondGap)
    {
        Blackboard board = Board("c", 1, 7);
        Offer(store, "c", Attempt1, board, T0);
        Liftoff(board);
        Offer(store, "c", Attempt1, board, T0 + firstGap);
        Track(board, 2);
        Offer(store, "c", Attempt1, board, T0 + firstGap + secondGap);
    };
    ObservationStore tight;
    air(tight, 1000, 1000);
    CHECK(Block(tight, "c", Attempt1) == Expected(1, 1, 1, 0, 0, 1000, true, Attempt1), "1 s gaps next to the air phase");
    ObservationStore intoAir;
    air(intoAir, 1001, 250);
    CHECK(Block(intoAir, "c", Attempt1) == Expected(1, 1, 1, 0, 0, 1001, false, Attempt1), "a longer gap into the air phase");
    ObservationStore inAir;
    air(inAir, 250, 1001);
    CHECK(Block(inAir, "c", Attempt1) == Expected(1, 1, 1, 0, 0, 1001, false, Attempt1), "a longer gap in the air phase");

    // Ground: up to 5 s inside one engagement (no air phase fits). The same bound holds when the next
    // snapshot is not engaged (Atramedes died, or the route moved on): a short gap hides no air phase.
    ObservationStore ground;
    Blackboard board = Board("c", 1, 7);
    Offer(ground, "c", Attempt1, board, T0);
    Offer(ground, "c", Attempt1, board, T0 + 5000);
    CHECK(Block(ground, "c", Attempt1) == Expected(0, 0, 0, 0, 0, 5000, true, Attempt1), "a 5 s ground gap");
    board.Summons.clear();  // Atramedes died: not engaged
    Offer(ground, "c", Attempt1, board, T0 + 5000 + 5000, false);
    CHECK(Block(ground, "c", Attempt1) == Expected(0, 0, 0, 0, 0, 5000, true, Attempt1), "a kill within 5 s of the ground");
    Offer(ground, "c", Attempt1, board, T0 + 60000, false);
    CHECK(Block(ground, "c", Attempt1) == Expected(0, 0, 0, 0, 0, 5000, true, Attempt1),
        "absent after absent: no engagement left to lose");
    ObservationStore lateKill;
    board = Board("c", 1, 7);
    Offer(lateKill, "c", Attempt1, board, T0);
    board.Summons.clear();
    Offer(lateKill, "c", Attempt1, board, T0 + 5001, false);
    CHECK(Block(lateKill, "c", Attempt1) == Expected(0, 0, 0, 0, 0, 5001, false, Attempt1),
        "a ground gap over 5 s before a boss-absent snapshot");
    ObservationStore longGround;
    board = Board("c", 1, 7);
    Offer(longGround, "c", Attempt1, board, T0);
    Offer(longGround, "c", Attempt1, board, T0 + 5001);
    CHECK(Block(longGround, "c", Attempt1) == Expected(0, 0, 0, 0, 0, 5001, false, Attempt1), "a longer ground gap");
    // Atramedes dies in the air after a long unsampled stretch: the chase's end is unseen.
    ObservationStore airEnd;
    air(airEnd, 250, 250);
    board.Summons.clear();
    Offer(airEnd, "c", Attempt1, board, T0 + 500 + 1001, false);
    CHECK(Block(airEnd, "c", Attempt1) == Expected(1, 1, 1, 0, 0, 1001, false, Attempt1), "an unseen chase end");

    // A cached copy a little older is no sample and no gap; a clock that went back further blinds the store.
    ObservationStore cached;
    air(cached, 250, 250);
    Blackboard copy = Board("c", 1, 7);
    Liftoff(copy);
    Track(copy, 2);
    Sound(copy, 2, 40);
    Offer(cached, "c", Attempt1, copy, T0 + 500 - 50);
    CHECK(Block(cached, "c", Attempt1) == Expected(1, 1, 1, 0, 0, 250, true, Attempt1), "an older copy is not sampled");
    Offer(cached, "c", Attempt1, copy, T0 + 500 - 1001);
    CHECK(Block(cached, "c", Attempt1) == Expected(1, 1, 1, 0, 0, 250, false, Attempt1), "a clock 1 s back: not complete");
}

// A whole air phase unseen between an engaged ground sample and the first sample after Atramedes died or the
// route moved on: the terminal snapshot is no proof that the outage held no chase above the bound.
static void TestTerminalOutageIsLostCoverage()
{
    for (int terminal = 0; terminal < 2; ++terminal)  // 0: Atramedes gone, 1: the route moved on
        for (uint64 outage : { 119500ull, 31000ull, 5001ull })
        {
            ObservationStore store;
            Blackboard board = Board("c", 1, 7);
            uint64 at = T0;
            Offer(store, "c", Attempt1, board, at);
            Liftoff(board);
            Offer(store, "c", Attempt1, board, at += 250);
            Track(board, 2);
            Sound(board, 2, 5);
            Offer(store, "c", Attempt1, board, at += 250);  // an in-bound first chase
            Land(board);
            Offer(store, "c", Attempt1, board, at += 250);
            Offer(store, "c", Attempt1, board, at += 250);  // and its ground phase
            CHECK(Block(store, "c", Attempt1) == Expected(1, 1, 1, 5, 0, 250, true, Attempt1), "observed so far");
            Blackboard after = board;
            if (terminal == 0)
                after.Summons.clear();
            else
                after.Route.NodeId = "bwd.nefarian.encounter";
            Offer(store, "c", Attempt1, after, at + outage, false);
            CHECK(Block(store, "c", Attempt1) == Expected(1, 1, 1, 5, 0, int(outage), false, Attempt1),
                "an outage before the terminal snapshot is lost coverage");
            // Negative control: the same terminal snapshot right after the last sample keeps the coverage.
            ObservationStore tight;
            Blackboard again = board;
            Offer(tight, "c", Attempt1, again, T0);
            Offer(tight, "c", Attempt1, again, T0 + 250);
            Blackboard end = again;
            if (terminal == 0)
                end.Summons.clear();
            else
                end.Route.NodeId = "bwd.nefarian.encounter";
            Offer(tight, "c", Attempt1, end, T0 + 500, false);
            CHECK(Block(tight, "c", Attempt1) == Expected(0, 0, 0, 0, 0, 250, true, Attempt1),
                "a prompt terminal snapshot is covered");
        }
}

// A cohort reused after an Atramedes run exports what a fresh process does; the same attempt keeps its
// terminal observations, merged into the Nefarian field when there is one.
static void TestExportCohortReuse()
{
    ObservationStore fresh;
    ObservationStore store;
    std::string const nefarian = ",\"encounter_observations\":{\"nefarian\":{\"bone_warrior_on_pillar\":0}}";
    std::string_view const otherRoutes[] = { "", "bwd.magmaw.encounter", "stonecore.encounter",
        "bwd.nefarian.encounter", "bwd.atramedes.north_spirits" };
    for (std::string_view route : otherRoutes)
    {
        CHECK(fresh.JsonField("", "default", Attempt1, route).empty(), "a fresh process: nothing elsewhere");
        CHECK(fresh.JsonField(nefarian, "default", Attempt1, route) == nefarian,
            "another encounter's field stays byte-identical");
    }
    CHECK(Block(fresh, "default", Attempt1) == Expected(0, 0, 0, 0, 0, 0, false, Attempt1),
        "a fresh process on Atramedes' route: an incomplete zero");

    Blackboard board = Board("default", 1, 9);
    Offer(store, "default", Attempt1, board, T0);
    Liftoff(board);
    Track(board, 2);
    Sound(board, 2, 15);
    Offer(store, "default", Attempt1, board, T0 + 250);
    std::string const terminal = Block(store, "default", Attempt1);
    CHECK(terminal == Expected(1, 1, 1, 15, 1, 250, true, Attempt1), terminal.c_str());
    for (std::string_view route : otherRoutes)
    {
        CHECK(Block(store, "default", Attempt1, route) == terminal,
            "the same attempt keeps its terminal observations after the route moved on");
        std::string const merged = ZeroTimes(store.JsonField(nefarian, "default", Attempt1, route));
        CHECK(merged == nefarian.substr(0, nefarian.size() - 1) + ",\"atramedes\":"
            + terminal.substr(std::string(",\"encounter_observations\":{\"atramedes\":").size()),
            "merged into the one encounter_observations object");
    }

    // Reuse by `.botauto start` (a new attempt id) or `.botexp start` (a new lifecycle, the attempt id kept):
    // byte-identical to a fresh process.
    for (ObservationAttempt reuse : { ObservationAttempt{ 1, 2 }, ObservationAttempt{ 2, 1 } })
    {
        for (std::string_view route : otherRoutes)
        {
            CHECK(store.JsonField("", "default", reuse, route).empty(), "no stale block on another scenario");
            CHECK(store.JsonField(nefarian, "default", reuse, route) == nefarian, "nor inside another's field");
        }
        CHECK(Block(store, "default", reuse) == Block(fresh, "default", reuse),
            "a new Atramedes run in the reused cohort starts from the fresh block");
    }
}

// The export's observation times: the time (system ms, ObservedAtMs) of the first and the newest sample of
// the attempt, which the run harness holds against the boss window (complete only says there was no internal
// gap): one sample then nothing leaves first == last far from a window's end, however late the status is read.
// A repeated or older snapshot is never a sample and moves neither.
static void TestObservationTimes()
{
    ObservationStore store;
    Blackboard board = Board("shard", 1, 7);

    // Begun, nothing offered: no times.
    store.Begin("shard", Attempt1);
    std::string raw = store.JsonField("", "shard", Attempt1, EncounterNode);
    CHECK(TimeField(raw, "first_observed_at_ms") == 0 && TimeField(raw, "last_observed_at_ms") == 0, "no sample: no times");

    // One sample: first == last, complete by its own gaps (nothing says the window's edges were sampled).
    Offer(store, "shard", Attempt1, board, T0);
    raw = store.JsonField("", "shard", Attempt1, EncounterNode);
    CHECK(TimeField(raw, "first_observed_at_ms") == T0 && TimeField(raw, "last_observed_at_ms") == T0,
        "one sample: first and last");
    CHECK(ZeroTimes(raw) == Expected(0, 0, 0, 0, 0, 0, true, Attempt1), "and complete by its own gaps");

    // More samples move the last only; a repeated snapshot (ten bots) and an older one move nothing.
    Offer(store, "shard", Attempt1, board, T0 + 250);
    Offer(store, "shard", Attempt1, board, T0 + 500);
    Offer(store, "shard", Attempt1, board, T0 + 500);
    Offer(store, "shard", Attempt1, board, T0 + 400);
    raw = store.JsonField("", "shard", Attempt1, EncounterNode);
    CHECK(TimeField(raw, "first_observed_at_ms") == T0 && TimeField(raw, "last_observed_at_ms") == T0 + 500,
        "the last is the newest sample");

    // A snapshot off the encounter node is a sample too (the route moved on): the observer is still running.
    Blackboard elsewhere = board;
    elsewhere.Route.NodeId = "bwd.nefarian.encounter";
    Offer(store, "shard", Attempt1, elsewhere, T0 + 750);
    raw = store.JsonField("", "shard", Attempt1, EncounterNode);
    CHECK(TimeField(raw, "last_observed_at_ms") == T0 + 750, "an off-node snapshot is sampled");

    // A stale attempt exports none; a new attempt starts its own.
    ObservationAttempt const second{ 1, 2 };
    CHECK(TimeField(store.JsonField("", "shard", second, EncounterNode), "first_observed_at_ms") == 0,
        "a stale attempt exports none");
    Blackboard next = Board("shard", 2, 7);
    Offer(store, "shard", second, next, T0 + 9000);
    raw = store.JsonField("", "shard", second, EncounterNode);
    CHECK(TimeField(raw, "first_observed_at_ms") == T0 + 9000 && TimeField(raw, "last_observed_at_ms") == T0 + 9000,
        "a new attempt starts its own times");

    // A clock that went back: the stale sample is refused, the last stays where it was.
    ObservationStore clock;
    Blackboard late = Board("shard", 1, 7);
    Offer(clock, "shard", Attempt1, late, T0 + 60000);
    Offer(clock, "shard", Attempt1, late, T0 + 10000);
    raw = clock.JsonField("", "shard", Attempt1, EncounterNode);
    CHECK(TimeField(raw, "first_observed_at_ms") == T0 + 60000 && TimeField(raw, "last_observed_at_ms") == T0 + 60000,
        "an older snapshot moves neither time");
}

// Round 4 (live r03 batch 2 had a 20 Sound chase sample nothing could explain): each chase sample in the
// export names the source of the kiter's last Sound rise, read off the snapshot that shows it, even when the
// rise came before the chase (the striker a Sonar Bomb hit before the redirected flame re-tracked it).
static void TestSoundSources()
{
    ObservationStore store;
    Blackboard board = Board("shard", 1, 7);
    uint64 at = T0;
    Offer(store, "shard", Attempt1, board, at += 250);
    Liftoff(board);
    Track(board, 2);
    Offer(store, "shard", Attempt1, board, at += 250);
    // A breath tick on the kiter (the flame 9 yd from it at (146, -225)... moved beside it).
    board.Summons.back().Position = { 163.0f, -225.0f, 75.0f };
    Sound(board, 2, 3);
    Offer(store, "shard", Attempt1, board, at += 250);
    // The redirect: nobody chased. A Sonar Bomb marker lands on the striker (player 3) at 20.
    Track(board, 0);
    ActorSnapshot marker;
    marker.Guid = UnitGuid(SonarBombMarkerEntry, 950);
    marker.Entry = SonarBombMarkerEntry;
    marker.Kind = ActorKind::Summon;
    marker.Alive = true;
    marker.Position = { 176.0f, -224.0f, 75.0f };
    board.Summons.push_back(marker);
    Sound(board, 3, 20);
    uint64 const bombAt = at += 250;
    Offer(store, "shard", Attempt1, board, bombAt);
    // Two seconds later the flame re-tracks the striker, far from the marker now: its first sample is 20.
    board.Summons.pop_back();
    Track(board, 3);
    Player(board, 3).Position = { 185.0f, -240.0f, 75.0f };
    Offer(store, "shard", Attempt1, board, at += 2000);
    // A rise with nothing in reach is unattributed, never guessed.
    board.Summons.back().Position = { 100.0f, -300.0f, 75.0f };
    Sound(board, 3, 25);
    Offer(store, "shard", Attempt1, board, at += 250);
    std::string const raw = store.JsonField("", "shard", Attempt1, EncounterNode);
    auto has = [&raw](std::string const& text) { return raw.find(text) != std::string::npos; };
    CHECK(has("\"kiter\":" + std::to_string(PlayerGuid(2).GetRawValue()) + ",\"sound\":3,"
        "\"last_increment_source\":\"roaring_flame\",\"last_increment\":3"), raw.c_str());
    CHECK(has("\"kiter\":" + std::to_string(PlayerGuid(3).GetRawValue()) + ",\"sound\":20,"
        "\"last_increment_source\":\"sonar_bomb\",\"last_increment\":20,\"last_increment_at_ms\":"
        + std::to_string(bombAt) + "}"), raw.c_str());
    CHECK(has("\"sound\":25,\"last_increment_source\":\"unattributed\",\"last_increment\":5"), raw.c_str());
    CHECK(has(",\"sound_samples_dropped\":0}}"), raw.c_str());
    // Negative control: the bomb's Sound is not the kiter's until the flame tracks it; no chase sample before.
    CHECK(raw.find("\"sound\":20") > raw.find("\"sound\":3,"), "the bomb shows up in the striker's chase");

    // A player first seen with Sound: the rise predates the sampling.
    ObservationStore late;
    Blackboard loud = Board("shard", 1, 7);
    Liftoff(loud);
    Track(loud, 1);
    Sound(loud, 1, 15);
    Offer(late, "shard", Attempt1, loud, T0);
    CHECK(late.JsonField("", "shard", Attempt1, EncounterNode).find(
        "\"sound\":15,\"last_increment_source\":\"before_observation\"") != std::string::npos,
        "before the observation");
}

int main()
{
    TestSoundSources();
    TestObservationTimes();
    TestChaseSampling();
    TestAttemptAndInstanceScope();
    TestCoverage();
    TestTerminalOutageIsLostCoverage();
    TestExportCohortReuse();
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    else
        std::printf("ok\n");
    return failures ? 1 : 0;
}
'''


def test_observations_are_sampled_per_chase_and_scoped_by_cohort_attempt_and_instance(tmp_path: Path) -> None:
    assert _compile_and_run(tmp_path, PROGRAM).strip() == "ok"


def test_observation_scope_under_sanitizers(tmp_path: Path) -> None:
    assert _compile_and_run(tmp_path, PROGRAM, sanitize=True).strip() == "ok"
