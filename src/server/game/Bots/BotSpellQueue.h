#ifndef TRINITY_BOT_SPELL_QUEUE_H
#define TRINITY_BOT_SPELL_QUEUE_H

#include "Define.h"
#include <queue>
#include <string>
#include <unordered_map>
#include <vector>

class Player;

// Player-style spell queue for server-driven bots.  A player presses the next
// ability shortly before the global cooldown or the current cast ends and the
// client submits it the moment the lock clears.  Bots used to discover the
// release only by polling, and a GCD rejection counted as a failed attempt
// with exponential backoff, so the next cast routinely landed one backoff step
// after the lock had already cleared.
//
// Each pending intent records the native release time it waits for.  The
// queue is a std::priority_queue ordered by release time and then by action
// priority, so the decision scheduler always wakes for the earliest release
// and, when several intents become ready together, the most important one is
// on top.  The spell itself is resolved again at release time: a proc or an
// encounter transition that happened during the lock is never skipped in
// favour of a stale choice.
namespace BotSpellQueue
{
// Largest release delay a queued intent may request.  Longer locks (long
// casts, channels) are simply re-observed on later decisions.
constexpr uint32 MaxWaitMs = 3000;
// Retry cadence for waits whose release time is not natively observable
// (rune, energy, focus or cooldown regeneration).  Matches the fastest
// combat decision cadence instead of growing an exponential backoff.
constexpr uint32 RegenerationPollMs = 100;
// In-combat decision cadence for a spec without a calibration reference
// interval (tanks and healers).  It equals the native reference floor.
constexpr uint32 CombatDecisionIntervalMs = 100;

struct NativeLock
{
    uint64 GlobalCooldownEndsAtMs = 0;
    uint64 CastEndsAtMs = 0;
    uint64 ChannelEndsAtMs = 0;

    uint64 ReleaseAtMs() const;
    bool Locked(uint64 nowMs) const { return ReleaseAtMs() > nowMs; }
};

// Observe the bot's current native lock.  The GCD is read through a spell
// that shares its start recovery category; zero skips the GCD component.
NativeLock ObserveNativeLock(Player const* bot, uint32 gcdProbeSpellId,
    uint64 nowMs);

// Remember a spell that triggers the GCD so later observations can read the
// lock without knowing the next action.
bool IsGlobalCooldownProbe(uint32 spellId);

bool IsRegenerationWaitReason(std::string const& reason);

struct Entry
{
    std::string Key;
    std::string Reason;
    uint8 Priority = 0;
    uint64 ReadyAtMs = 0;
    uint64 QueuedAtMs = 0;
    uint64 Serial = 0;
};

// std::priority_queue keeps the greatest element on top, so "less" means
// "released later, or released together with a lower action priority".
struct ReleasedLater
{
    bool operator()(Entry const& left, Entry const& right) const
    {
        if (left.ReadyAtMs != right.ReadyAtMs)
            return left.ReadyAtMs > right.ReadyAtMs;
        if (left.Priority != right.Priority)
            return left.Priority < right.Priority;
        return left.Serial > right.Serial;
    }
};

class Queue
{
public:
    // Queue or re-time the intent for key.  A newer entry for the same key
    // supersedes the older one, which is discarded lazily when it surfaces.
    void Schedule(std::string key, std::string reason, uint8 priority,
        uint64 readyAtMs, uint64 nowMs);
    // Release every intent whose lock has cleared, recording how late the
    // decision that released it ran.  Returns the number released.
    uint32 ReleaseDue(uint64 nowMs);
    // Delay until the earliest pending release, never longer than
    // currentTimerMs.  At least 1 ms so the scheduler always advances.
    uint32 WakeDelayMs(uint64 nowMs, uint32 currentTimerMs);
    void Clear();
    bool Empty();
    std::string ToJson(uint64 nowMs);

    uint32 GcdProbeSpellId = 0;

private:
    bool IsCurrent(Entry const& entry) const;
    void DropSuperseded();

    std::priority_queue<Entry, std::vector<Entry>, ReleasedLater> _pending;
    std::unordered_map<std::string, uint64> _currentSerialByKey;
    uint64 _nextSerial = 0;
    uint64 _scheduled = 0;
    uint64 _released = 0;
    uint64 _totalReleaseLatencyMs = 0;
    uint64 _maxReleaseLatencyMs = 0;
    std::string _lastReleasedKey;
    std::string _lastReleasedReason;
};
}

#endif
