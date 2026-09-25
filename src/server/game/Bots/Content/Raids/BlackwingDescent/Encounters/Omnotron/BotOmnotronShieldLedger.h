#ifndef TRINITY_BOT_OMNOTRON_SHIELD_LEDGER_H
#define TRINITY_BOT_OMNOTRON_SHIELD_LEDGER_H

#include "Bots/BotEncounterBlackboard.h"
#include <algorithm>
#include <map>
#include <mutex>
#include <string>
#include <tuple>

// Remembers, per construct and activation, that its shield has been observed.
// Each construct shields exactly once per activation (client/DBM/native, see
// the ledger's shield_timing), so a construct whose shield has come and gone
// cannot shield again before it shuts down: it is the safest damage target.
// This is an observation, not a timer: nothing here predicts when a shield
// comes. Keys are cohort, attempt, wipe generation and construct, so parallel
// shards never share state; idle entries age out.
namespace BotEncounter::Omnotron
{
struct ShieldObservation
{
    bool SeenThisActivation = false;
    bool ShieldedNow = false;

    bool Spent() const { return SeenThisActivation && !ShieldedNow; }
};

class ShieldLedger
{
public:
    static constexpr uint64 IdleExpiryMs = 300000;
    // A later Activated expiry by more than this marks a new activation even
    // when no inactive snapshot was seen in between.
    static constexpr uint64 NewActivationMs = 10000;

    struct Sample
    {
        ObjectGuid Construct;
        bool Active = false;
        bool Shielded = false;
        uint64 ActivatedExpiresAtMs = 0;
    };

    // Mutating observation used by bot decisions; an older revision never
    // rewinds the ledger.
    static ShieldObservation Observe(Blackboard const& board, Sample const& sample)
    {
        std::lock_guard<std::mutex> lock(Mutex());
        auto& entries = Entries();
        Prune(entries, board.ObservedAtMs);
        Entry& entry = entries[KeyOf(board, sample.Construct)];
        if (board.Revision >= entry.LastRevision)
        {
            entry = Advance(entry, sample);
            entry.LastRevision = board.Revision;
        }
        entry.LastTouchedMs = std::max(entry.LastTouchedMs, board.ObservedAtMs);
        return View(entry, sample);
    }

    // Read-only view for status receipts.
    static ShieldObservation Peek(Blackboard const& board, Sample const& sample)
    {
        std::lock_guard<std::mutex> lock(Mutex());
        auto const& entries = Entries();
        auto itr = entries.find(KeyOf(board, sample.Construct));
        Entry const entry = Advance(itr == entries.end() ? Entry{} : itr->second, sample);
        return View(entry, sample);
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
        bool SeenThisActivation = false;
        uint64 ActivatedExpiresAtMs = 0;
        uint64 LastRevision = 0;
        uint64 LastTouchedMs = 0;
    };

    static Entry Advance(Entry entry, Sample const& sample)
    {
        if (!sample.Active
            || sample.ActivatedExpiresAtMs > entry.ActivatedExpiresAtMs + NewActivationMs)
            entry.SeenThisActivation = false;
        if (sample.Active)
            entry.ActivatedExpiresAtMs = std::max(entry.ActivatedExpiresAtMs,
                sample.ActivatedExpiresAtMs);
        else
            entry.ActivatedExpiresAtMs = 0;
        if (sample.Active && sample.Shielded)
            entry.SeenThisActivation = true;
        return entry;
    }

    static ShieldObservation View(Entry const& entry, Sample const& sample)
    {
        ShieldObservation view;
        view.SeenThisActivation = sample.Active && entry.SeenThisActivation;
        view.ShieldedNow = sample.Shielded;
        return view;
    }

    static Key KeyOf(Blackboard const& board, ObjectGuid construct)
    {
        return Key{ board.CurrentScope.CohortId, board.CurrentScope.AttemptId,
            board.CurrentScope.WipeGeneration, construct.GetRawValue() };
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
