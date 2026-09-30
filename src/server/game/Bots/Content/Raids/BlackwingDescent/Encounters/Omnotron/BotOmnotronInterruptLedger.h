#ifndef TRINITY_BOT_OMNOTRON_INTERRUPT_LEDGER_H
#define TRINITY_BOT_OMNOTRON_INTERRUPT_LEDGER_H

#include "Bots/BotEncounterBlackboard.h"
#include <algorithm>
#include <map>
#include <mutex>
#include <optional>
#include <string>
#include <tuple>

// Counts Arcane Annihilator casts per cohort attempt so the interrupt
// rotation can advance without another timer. The blackboard only shows
// "casting now"; this ledger remembers when each cast was first observed and
// how many casts came before it, and when each bot last submitted its
// interrupt and when the bot's own spell history said that interrupt is ready
// again (so the rotation skips a bot still on cooldown). Entries are keyed by
// cohort, attempt, wipe generation and caster, so parallel shards never share
// a count; idle entries age out, so no cohort teardown hook is needed.
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

// One submitted interrupt: when it was submitted and when the bot's native
// spell history reported the interrupt ready again.
struct InterruptUse
{
    uint64 AtMs = 0;
    uint64 ReadyAtMs = 0;

    bool CoolingAt(uint64 nowMs) const { return nowMs < ReadyAtMs; }
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

    // A bot submitted its interrupt at atMs (the runtime's decision clock,
    // the same clock as Blackboard::ObservedAtMs). remainingCooldownMs is the
    // bot's own native remaining cooldown of the spell it just cast, read from
    // its spell history right after the cast: it already carries every talent,
    // glyph, haste and aura modifier (Reverberation cuts Wind Shear from 15 s
    // to 5 s), so the rotation never assumes a base cooldown. 0 means the
    // spell is ready again at once. The rotation skips the bot until then, so
    // a turn never lands on a bot that cannot cast and leaves the cast to a
    // late backup.
    static void RecordUse(Blackboard const& board, ObjectGuid bot, uint64 atMs,
        uint64 remainingCooldownMs)
    {
        std::lock_guard<std::mutex> lock(Mutex());
        auto& uses = Uses();
        PruneUses(uses, atMs);
        InterruptUse& use = uses[KeyOf(board, bot)];
        // An older submission never rewinds a newer one.
        if (atMs >= use.AtMs)
            use = InterruptUse{ atMs, atMs + remainingCooldownMs };
    }

    // Last recorded interrupt of this bot in the board's scope, if any.
    static std::optional<InterruptUse> LastUse(Blackboard const& board,
        ObjectGuid bot)
    {
        std::lock_guard<std::mutex> lock(Mutex());
        auto const& uses = Uses();
        auto itr = uses.find(KeyOf(board, bot));
        if (itr == uses.end())
            return std::nullopt;
        return itr->second;
    }

    static void ResetForTests()
    {
        std::lock_guard<std::mutex> lock(Mutex());
        Entries().clear();
        Uses().clear();
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

    static void PruneUses(std::map<Key, InterruptUse>& uses, uint64 nowMs)
    {
        for (auto itr = uses.begin(); itr != uses.end();)
        {
            if (nowMs > std::max(itr->second.AtMs, itr->second.ReadyAtMs)
                    + IdleExpiryMs)
                itr = uses.erase(itr);
            else
                ++itr;
        }
    }

    static std::map<Key, InterruptUse>& Uses()
    {
        static std::map<Key, InterruptUse> uses;
        return uses;
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
