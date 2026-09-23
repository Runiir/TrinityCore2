#ifndef TRINITY_BOT_WORLD_TICK_RECORDER_H
#define TRINITY_BOT_WORLD_TICK_RECORDER_H

#include <cstddef>
#include <cstdint>
#include <deque>
#include <ostream>

namespace BotWorldTick
{
// A world update diff this long means the world thread did not tick for
// half a second: every bot action, aura tick and swing that was due lands in
// the next update.  The live-validation harness uses these rows to measure
// how much of a boss window the world was frozen.
inline constexpr std::uint32_t StallThresholdMs = 500;
inline constexpr std::size_t StallCapacity = 256;

struct Stall
{
    std::uint64_t Sequence = 0;
    // End of the stalled interval (the update that observed the diff), on
    // the game-time system clock used by combat-log ``timestamp_ms``.
    std::uint64_t AtMs = 0;
    std::uint32_t DiffMs = 0;
};

// Records long world update diffs in a bounded ring.  Counters are
// cumulative for the process lifetime and every row carries a sequence, so
// repeated status reads never consume or lose rows: a reader merges by
// sequence and detects ring overflow from ``dropped_count``.  Written and
// read on the world thread only (CLI and SOAP commands execute there).
class Recorder
{
public:
    explicit Recorder(std::uint32_t thresholdMs = StallThresholdMs,
        std::size_t capacity = StallCapacity)
        : _thresholdMs(thresholdMs), _capacity(capacity ? capacity : 1) { }

    bool Observe(std::uint64_t nowMs, std::uint32_t diffMs)
    {
        if (!_updateCount)
            _firstUpdateAtMs = nowMs;
        ++_updateCount;
        if (diffMs > _maxDiffMs)
        {
            _maxDiffMs = diffMs;
            _maxDiffAtMs = nowMs;
        }
        if (diffMs < _thresholdMs)
            return false;
        Stall stall;
        stall.Sequence = ++_stallCount;
        stall.AtMs = nowMs;
        stall.DiffMs = diffMs;
        _stalls.push_back(stall);
        while (_stalls.size() > _capacity)
        {
            _stalls.pop_front();
            ++_droppedCount;
        }
        return true;
    }

    std::uint32_t ThresholdMs() const { return _thresholdMs; }
    std::size_t Capacity() const { return _capacity; }
    std::uint64_t UpdateCount() const { return _updateCount; }
    std::uint64_t FirstUpdateAtMs() const { return _firstUpdateAtMs; }
    std::uint32_t MaxDiffMs() const { return _maxDiffMs; }
    std::uint64_t MaxDiffAtMs() const { return _maxDiffAtMs; }
    std::uint64_t StallCount() const { return _stallCount; }
    std::uint64_t DroppedCount() const { return _droppedCount; }
    std::deque<Stall> const& Stalls() const { return _stalls; }

    void WriteJson(std::ostream& json, std::uint64_t nowMs) const
    {
        json << "{\"schema\":\"bot_world_update_ticks_v1\""
             << ",\"now_ms\":" << nowMs
             << ",\"threshold_ms\":" << _thresholdMs
             << ",\"capacity\":" << _capacity
             << ",\"update_count\":" << _updateCount
             << ",\"first_update_at_ms\":" << _firstUpdateAtMs
             << ",\"max_diff_ms\":" << _maxDiffMs
             << ",\"max_diff_at_ms\":" << _maxDiffAtMs
             << ",\"stall_count\":" << _stallCount
             << ",\"dropped_count\":" << _droppedCount
             << ",\"stalls\":[";
        bool first = true;
        for (Stall const& stall : _stalls)
        {
            if (!first)
                json << ',';
            first = false;
            json << "{\"sequence\":" << stall.Sequence
                 << ",\"at_ms\":" << stall.AtMs
                 << ",\"diff_ms\":" << stall.DiffMs << '}';
        }
        json << "]}";
    }

private:
    std::uint32_t _thresholdMs;
    std::size_t _capacity;
    std::uint64_t _updateCount = 0;
    std::uint64_t _firstUpdateAtMs = 0;
    std::uint32_t _maxDiffMs = 0;
    std::uint64_t _maxDiffAtMs = 0;
    std::uint64_t _stallCount = 0;
    std::uint64_t _droppedCount = 0;
    std::deque<Stall> _stalls;
};

// One recorder for the world thread, shared by Update and the status JSON.
inline Recorder& WorldRecorder()
{
    static Recorder recorder;
    return recorder;
}
}

#endif
