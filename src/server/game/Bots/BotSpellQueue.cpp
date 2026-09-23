#include "Bots/BotSpellQueue.h"

#include <algorithm>
#include <sstream>

namespace BotSpellQueue
{
uint64 NativeLock::ReleaseAtMs() const
{
    return std::max({ GlobalCooldownEndsAtMs, CastEndsAtMs, ChannelEndsAtMs });
}

uint64 LockRetryAtMs(NativeLock const& lock, uint64 nowMs)
{
    if (!lock.Locked(nowMs))
        return nowMs + RegenerationPollMs;
    if (lock.Casting(nowMs))
        return std::min<uint64>(lock.ReleaseAtMs(),
            nowMs + CombatDecisionIntervalMs);
    return lock.GlobalCooldownEndsAtMs;
}

bool IsRegenerationWaitReason(std::string const& reason)
{
    // Candidate rejection reasons that clear on their own as runes, energy,
    // focus, combo points or cooldowns regenerate.  Every other reason keeps
    // the ordinary retry backoff.
    return reason == "insufficient_resource"
        || reason == "cooldown_not_ready"
        || reason == "cooldown_group_not_aligned"
        || reason == "insufficient_combo_points"
        || reason == "global_cooldown"
        || reason == "already_casting";
}

void Queue::Schedule(std::string key, std::string reason, uint8 priority,
    uint64 readyAtMs, uint64 nowMs)
{
    Entry entry;
    entry.Key = std::move(key);
    entry.Reason = std::move(reason);
    entry.Priority = priority;
    entry.ReadyAtMs = std::min<uint64>(std::max(readyAtMs, nowMs),
        nowMs + MaxWaitMs);
    entry.QueuedAtMs = nowMs;
    entry.Serial = ++_nextSerial;
    _currentSerialByKey[entry.Key] = entry.Serial;
    _pending.push(std::move(entry));
    ++_scheduled;

    // Repeated waits on one key leave superseded entries behind.  Compact
    // before they can grow without bound.
    if (_pending.size() > 4 * _currentSerialByKey.size() + 8)
        DropSuperseded();
}

uint32 Queue::ReleaseDue(uint64 nowMs)
{
    // The lateness of a release after a paused decision loop measures the
    // pause (death, hold, skipped update, world stall), not the scheduler.
    bool const resumedAfterPause = _lastReleaseCheckMs
        && nowMs > _lastReleaseCheckMs + PausedReleaseGapMs;
    _lastReleaseCheckMs = nowMs;
    uint32 released = 0;
    while (!_pending.empty() && _pending.top().ReadyAtMs <= nowMs)
    {
        Entry const& top = _pending.top();
        if (IsCurrent(top))
        {
            ++_released;
            if (resumedAfterPause)
                ++_releasedAfterPause;
            else
            {
                uint64 const latencyMs = nowMs - top.ReadyAtMs;
                _totalReleaseLatencyMs += latencyMs;
                _maxReleaseLatencyMs = std::max(_maxReleaseLatencyMs, latencyMs);
            }
            _lastReleasedKey = top.Key;
            _lastReleasedReason = top.Reason;
            _currentSerialByKey.erase(top.Key);
            ++released;
        }
        _pending.pop();
    }
    return released;
}

uint32 Queue::WakeDelayMs(uint64 nowMs, uint32 currentTimerMs)
{
    while (!_pending.empty() && !IsCurrent(_pending.top()))
        _pending.pop();
    if (_pending.empty())
        return currentTimerMs;

    uint64 const readyAtMs = _pending.top().ReadyAtMs;
    uint64 const delayMs = readyAtMs > nowMs ? readyAtMs - nowMs : 1;
    return uint32(std::max<uint64>(1, std::min<uint64>(currentTimerMs, delayMs)));
}

void Queue::Clear()
{
    // Called on every update of a dead or out-of-combat bot.
    if (_pending.empty() && _currentSerialByKey.empty())
        return;
    _pending = {};
    _currentSerialByKey.clear();
}

bool Queue::Empty()
{
    while (!_pending.empty() && !IsCurrent(_pending.top()))
        _pending.pop();
    return _pending.empty();
}

std::string Queue::ToJson(uint64 nowMs)
{
    Empty();
    uint64 const timedReleases = _released - _releasedAfterPause;
    std::ostringstream out;
    out << "{\"pending\":" << _currentSerialByKey.size()
        << ",\"next_key\":\""
        << (_pending.empty() ? std::string() : _pending.top().Key)
        << "\",\"next_ready_in_ms\":"
        << (_pending.empty() || _pending.top().ReadyAtMs <= nowMs
            ? 0 : _pending.top().ReadyAtMs - nowMs)
        << ",\"scheduled\":" << _scheduled
        << ",\"released\":" << _released
        << ",\"released_after_pause\":" << _releasedAfterPause
        << ",\"mean_release_latency_ms\":"
        << (timedReleases
            ? double(_totalReleaseLatencyMs) / double(timedReleases) : 0.0)
        << ",\"max_release_latency_ms\":" << _maxReleaseLatencyMs
        << ",\"last_released_key\":\"" << _lastReleasedKey
        << "\",\"last_released_reason\":\"" << _lastReleasedReason
        << "\",\"gcd_probe_spell_id\":" << GcdProbeSpellId << '}';
    return out.str();
}

bool Queue::IsCurrent(Entry const& entry) const
{
    auto const itr = _currentSerialByKey.find(entry.Key);
    return itr != _currentSerialByKey.end() && itr->second == entry.Serial;
}

void Queue::DropSuperseded()
{
    std::vector<Entry> current;
    current.reserve(_currentSerialByKey.size());
    while (!_pending.empty())
    {
        if (IsCurrent(_pending.top()))
            current.push_back(_pending.top());
        _pending.pop();
    }
    for (Entry& entry : current)
        _pending.push(std::move(entry));
}
}
