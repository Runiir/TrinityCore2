#ifndef TRINITY_BOT_OMNOTRON_INTERRUPT_LEDGER_H
#define TRINITY_BOT_OMNOTRON_INTERRUPT_LEDGER_H

#include "Bots/BotEncounterBlackboard.h"
#include <algorithm>
#include <map>
#include <mutex>
#include <string>
#include <tuple>

// Counts Arcane Annihilator casts per cohort attempt so the interrupt
// rotation can advance without another timer. The blackboard only shows
// "casting now"; this ledger remembers when each cast was first observed and
// how many casts came before it. Entries are keyed by cohort, attempt, wipe
// generation and caster, so parallel shards never share a count; idle
// entries age out, so no cohort teardown hook is needed.
namespace BotEncounter::Omnotron
{
struct InterruptCastObservation
{
    bool Casting = false;
    uint64 Ordinal = 0;
    uint64 FirstSeenMs = 0;

    uint64 AgeMs(uint64 nowMs) const
    {
        return Casting && nowMs > FirstSeenMs ? nowMs - FirstSeenMs : 0;
    }
};

class InterruptLedger
{
public:
    static constexpr uint64 IdleExpiryMs = 300000;

    // Mutating observation used by bot decisions. Idempotent per snapshot
    // revision; an older revision never rewinds the ledger.
    static InterruptCastObservation Observe(Blackboard const& board,
        ObjectGuid caster, bool casting)
    {
        std::lock_guard<std::mutex> lock(Mutex());
        auto& entries = Entries();
        Prune(entries, board.ObservedAtMs);
        Entry& entry = entries[KeyOf(board, caster)];
        if (board.Revision >= entry.LastRevision)
        {
            if (casting && !entry.CastActive)
            {
                ++entry.Ordinal;
                entry.FirstSeenMs = board.ObservedAtMs;
            }
            entry.CastActive = casting;
            entry.LastRevision = board.Revision;
        }
        entry.LastTouchedMs = std::max(entry.LastTouchedMs, board.ObservedAtMs);
        return View(entry);
    }

    // Read-only view for status receipts: never changes the rotation.
    static InterruptCastObservation Peek(Blackboard const& board,
        ObjectGuid caster, bool casting)
    {
        std::lock_guard<std::mutex> lock(Mutex());
        auto const& entries = Entries();
        auto itr = entries.find(KeyOf(board, caster));
        InterruptCastObservation view;
        if (itr != entries.end())
            view = View(itr->second);
        if (casting && !view.Casting)
        {
            view.Casting = true;
            ++view.Ordinal;
            view.FirstSeenMs = board.ObservedAtMs;
        }
        view.Casting = casting;
        return view;
    }

    static void ResetForTests()
    {
        std::lock_guard<std::mutex> lock(Mutex());
        Entries().clear();
    }

private:
    using Key = std::tuple<std::string, uint64, uint32, uint64>;

    struct Entry
    {
        uint64 Ordinal = 0;
        uint64 FirstSeenMs = 0;
        uint64 LastRevision = 0;
        uint64 LastTouchedMs = 0;
        bool CastActive = false;
    };

    static Key KeyOf(Blackboard const& board, ObjectGuid caster)
    {
        return Key{ board.CurrentScope.CohortId, board.CurrentScope.AttemptId,
            board.CurrentScope.WipeGeneration, caster.GetRawValue() };
    }

    static InterruptCastObservation View(Entry const& entry)
    {
        InterruptCastObservation view;
        view.Casting = entry.CastActive;
        view.Ordinal = entry.Ordinal;
        view.FirstSeenMs = entry.FirstSeenMs;
        return view;
    }

    static void Prune(std::map<Key, Entry>& entries, uint64 nowMs)
    {
        for (auto itr = entries.begin(); itr != entries.end();)
        {
            if (nowMs > itr->second.LastTouchedMs + IdleExpiryMs)
                itr = entries.erase(itr);
            else
                ++itr;
        }
    }

    static std::mutex& Mutex()
    {
        static std::mutex mutex;
        return mutex;
    }

    static std::map<Key, Entry>& Entries()
    {
        static std::map<Key, Entry> entries;
        return entries;
    }
};
}

#endif
