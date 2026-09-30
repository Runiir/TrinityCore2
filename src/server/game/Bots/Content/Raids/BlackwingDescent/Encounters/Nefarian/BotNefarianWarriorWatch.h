#ifndef TRINITY_BOT_NEFARIAN_WARRIOR_WATCH_H
#define TRINITY_BOT_NEFARIAN_WARRIOR_WATCH_H

// Acceptance observation for the bone warriors (round 3; user tactic: the
// Feral kites them with Nature's Grasp and keeps them out of Nefarian's
// front). Each Animate Bones tick costs 3 energy with no regeneration, so a
// warrior collapses about 33 s after it wakes unless Nefarian's Shadowflame
// Breath refills it (it is in his front). Round 2: warriors stayed active
// for 150-260 s and climbed the pillar-1 ramp to the casters left on its rim.
//
// The watch reports, once per warrior and kind:
// - active_over_limit: active (IsActiveBoneWarrior) for more than
//   WarriorActiveLimitMs without collapsing;
// - on_pillar: standing on a pillar structure (within the step-off radius of
//   a pillar centre and above the skirt), where only a member left on a
//   pillar leads it.
// Observation only: it never moves, targets or casts.
//
// Warrior guids are map-local: one watch serves one cohort attempt in one map
// instance (BotNefarianObservationStore.h scopes it).
//
// The clock is a monotonic millisecond clock (ObservationClockMs; the blackboard's
// own ObservedAtMs is system time, which a clock step can move by any amount).
// A span is only trusted while the observations are continuous:
// - an observation more than WarriorObservationGapMs after the previous one
//   (a stall, or a forward jump of the clock) restarts every active span at
//   this observation: a collapse and a wake hidden in the gap can no longer
//   join two spans, and a jump can no longer age a warrior;
// - an observation older than one already observed (a backward step) is
//   skipped whole, so no age underflows and no live entry is erased;
// - either one marks the watch's coverage broken (CoverageBroken), which the
//   store exports as complete:false.
// Observations closer together than the bound are taken as continuous.
//
// A snapshot is one observation (ObserveSnapshot). The blackboard is
// republished only while its system-time throttle allows, about every 100 ms
// (PublishEncounterBlackboard), and a step back of the wall clock holds one
// snapshot for as long as the step, while the reporter decides far more often.
// Observing that cached snapshot on every decision would age it with the
// reporter's steady time: a warrior active for 2 s in it would be reported
// active for 45 s. So the watch keeps the newest observed snapshot's revision:
// - a snapshot revision is observed once, at the steady time of the decision
//   that first sees it (the blackboard carries no steady publication time:
//   its ObservedAtMs is system time);
// - a repeat of it adds no observation and no time. A repeat that comes more
//   than WarriorObservationGapMs after the last new snapshot means the
//   snapshot went stale while the fight continued, and marks the coverage
//   broken (the next new snapshot then restarts every span as a gap does);
// - a revision below the observed one is out of order: skipped, coverage
//   broken; revision 0 is no snapshot identity (the publisher counts from 1):
//   never observed, coverage broken.
//
// The store exports when the watch first and last observed, in the clock the
// run harness judges the boss window by: the observed snapshots' own
// publication times (Blackboard::ObservedAtMs, system ms, the combat log's
// clock). The harness needs them: a watch that observed once is `complete`
// by its own gaps, but covers a boss window only if it observed near both of
// its edges (tools/raid_program/run_sanity_inputs.py).

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianMagma.h"
#include <algorithm>
#include <chrono>
#include <iterator>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace BotEncounter::Nefarian
{
constexpr uint64 WarriorActiveLimitMs = 45000;
// An entry not observed for this long belongs to a despawned warrior (a wipe
// or a reset) and is forgotten.
constexpr uint64 WarriorForgetMs = 30000;
// The longest interval between two observations that still counts as
// continuous. The reporter observes every decision (a fraction of a second);
// a longer silence hides what the warriors did.
constexpr uint64 WarriorObservationGapMs = 2000;

// The watch's clock: milliseconds of a monotonic (steady) time point.
inline uint64 ObservationClockMs(std::chrono::steady_clock::time_point point)
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        point.time_since_epoch()).count());
}

enum class WarriorViolationKind : uint8
{
    ActiveOverLimit,
    OnPillar
};

inline std::string_view WarriorViolationName(WarriorViolationKind kind)
{
    return kind == WarriorViolationKind::ActiveOverLimit
        ? "nefarian_bone_warrior_active_over_45s" : "nefarian_bone_warrior_on_pillar";
}

struct WarriorViolation
{
    ObjectGuid Warrior;
    WarriorViolationKind Kind = WarriorViolationKind::ActiveOverLimit;
    uint64 ActiveMs = 0;
};

// A warrior on a pillar top, rim or ramp above the skirt, in the platform
// frame of the observed elevator.
inline bool WarriorOnPillar(ActorSnapshot const& warrior, float originZ)
{
    float distance = 0.0f;
    NearestPillar(WorldToLocal(warrior.Position), distance);
    return distance <= DescentStepOffRadius
        && warrior.Position.Z - originZ > PillarSkirtLocalZ + 1.5f;
}

// The cohort's one reporter of the watch: its living bot with the lowest guid.
// `board.Players` lists the assignable cohort bots only; a play cohort's humans
// are published in `ExternalPlayers` and never lead. A guid found there is not
// a bot, whichever list also carries it.
inline bool ReportsWarriorWatch(Blackboard const& board, ObjectGuid bot)
{
    ObjectGuid reporter;
    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive)
            continue;
        bool const external = std::any_of(board.ExternalPlayers.begin(),
            board.ExternalPlayers.end(),
            [&player](ActorSnapshot const& human) { return human.Guid == player.Guid; });
        if (external)
            continue;
        if (reporter.IsEmpty() || player.Guid.GetCounter() < reporter.GetCounter())
            reporter = player.Guid;
    }
    return reporter == bot;
}

// One published snapshot as the reporter offers it: the blackboard's Revision
// and its ObservedAtMs (system ms: the combat log's clock).
struct SnapshotStamp
{
    uint64 Revision = 0;
    uint64 PublishedAtMs = 0;
};

class WarriorWatch
{
public:
    // The reporter's decision offers the cohort's snapshot (`snapshot`) at
    // steady time `nowMs` (ObservationClockMs); the production entry. A
    // revision already observed adds nothing (see above).
    std::vector<WarriorViolation> ObserveSnapshot(SnapshotStamp snapshot,
        EncounterView const& view, uint64 nowMs)
    {
        uint64 const revision = snapshot.Revision;
        if (!revision || (_haveRevision && revision < _revision))
        {
            _coverageBroken = true;
            return {};
        }
        if (_haveRevision && revision == _revision)
        {
            // The same snapshot again: no new state, no new time. Silence past
            // the bound (or a clock that went back) is lost coverage.
            if (nowMs < _latestMs || nowMs - _latestMs > WarriorObservationGapMs)
                _coverageBroken = true;
            return {};
        }
        _haveRevision = true;
        _revision = revision;
        return Observe(view, nowMs, snapshot.PublishedAtMs);
    }

    // The observation of one snapshot at steady time `nowMs` (`publishedAtMs`:
    // its publication time, 0 when unknown): every span and report of the
    // watch. Callers with a snapshot identity use ObserveSnapshot.
    std::vector<WarriorViolation> Observe(EncounterView const& view, uint64 nowMs,
        uint64 publishedAtMs = 0)
    {
        std::vector<WarriorViolation> found;
        // An older observation (a step back of the clock, or a reader's cached
        // copy) carries no newer state. Every entry time stays at or below
        // _latestMs, and so below nowMs. The clock cannot be trusted across it.
        if (_observed && nowMs < _latestMs)
        {
            _coverageBroken = true;
            return found;
        }
        // A silence longer than the bound (or a forward jump over it): no span
        // is proven continuous, so each active one restarts at this observation.
        if (_observed && nowMs - _latestMs > WarriorObservationGapMs)
        {
            _coverageBroken = true;
            for (auto& item : _entries)
                item.second.ActiveSinceMs = 0;
        }
        if (!_observed)
            _firstPublishedAtMs = publishedAtMs;
        _observed = true;
        _latestMs = nowMs;
        _lastPublishedAtMs = publishedAtMs;
        for (ActorSnapshot const* warrior : view.BoneWarriors)
        {
            Entry& entry = _entries[warrior->Guid.GetRawValue()];
            entry.LastSeenMs = nowMs;
            if (!IsActiveBoneWarrior(*warrior))
            {
                // Collapsed: the next wake starts a new active span.
                entry.ActiveSinceMs = 0;
                entry.ReportedOverLimit = false;
                continue;
            }
            if (!entry.ActiveSinceMs)
                entry.ActiveSinceMs = nowMs;
            uint64 const active = nowMs - entry.ActiveSinceMs;
            if (active > WarriorActiveLimitMs && !entry.ReportedOverLimit)
            {
                entry.ReportedOverLimit = true;
                found.push_back({ warrior->Guid, WarriorViolationKind::ActiveOverLimit, active });
            }
            if (view.Elevator.Observed && WarriorOnPillar(*warrior, view.Elevator.OriginZ)
                && !entry.ReportedOnPillar)
            {
                entry.ReportedOnPillar = true;
                found.push_back({ warrior->Guid, WarriorViolationKind::OnPillar, active });
            }
        }
        for (auto it = _entries.begin(); it != _entries.end();)
            it = nowMs - it->second.LastSeenMs > WarriorForgetMs ? _entries.erase(it)
                : std::next(it);
        return found;
    }

    // The newest observation time (0 before the first).
    uint64 LatestMs() const { return _latestMs; }

    // The revision of the newest observed snapshot (0 before the first).
    uint64 LatestRevision() const { return _haveRevision ? _revision : 0; }

    // The publication time (system ms) of the first and of the newest
    // observed snapshot; 0 before the first observation or when unknown.
    uint64 FirstPublishedAtMs() const { return _firstPublishedAtMs; }
    uint64 LastPublishedAtMs() const { return _lastPublishedAtMs; }

    // True once an observation came after a gap longer than
    // WarriorObservationGapMs, or before one already observed, or a snapshot
    // stayed unchanged past that bound, or one came without a usable identity:
    // what the watch reports is then not proven to cover the whole attempt.
    bool CoverageBroken() const { return _coverageBroken; }

private:
    struct Entry
    {
        uint64 ActiveSinceMs = 0;
        uint64 LastSeenMs = 0;
        bool ReportedOverLimit = false;
        bool ReportedOnPillar = false;
    };
    std::unordered_map<uint64, Entry> _entries;
    uint64 _latestMs = 0;
    uint64 _firstPublishedAtMs = 0;
    uint64 _lastPublishedAtMs = 0;
    uint64 _revision = 0;
    bool _haveRevision = false;
    bool _observed = false;
    bool _coverageBroken = false;
};
}

#endif
