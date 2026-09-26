#ifndef TRINITY_BOT_NEFARIAN_PICKUP_MEMORY_H
#define TRINITY_BOT_NEFARIAN_PICKUP_MEMORY_H

// The Onyxia tank's pickup across decisions (round 7 review). The plan is
// rebuilt every decision; this memory, kept by the native observer, carries
// what a single decision cannot see:
// - when the pickup began (Onyxia in combat on someone other than her tank),
//   keyed by tank and Onyxia GUID, so a moving victim never resets it;
// - the spots where the tank stood still and the native line of sight to her
//   failed (never reselected);
// - the budget: PickupBudgetMs, PickupRejectionBudget rejections, or
//   PickupStallDecisions standing still without sight of her. Spent, the
//   pickup is exhausted: the tank holds and keeps trying from where it
//   stands, the damage dealers start on Onyxia anyway, and the plan publishes
//   nefarian_pickup_exhausted.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianNativeFacts.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <vector>

namespace BotEncounter::Nefarian
{
constexpr uint64 PickupBudgetMs = 10000;
constexpr uint32 PickupRejectionBudget = 4;
constexpr float PickupRejectedSpotYards = 2.0f;
constexpr uint32 PickupStallDecisions = 30; // about 3 s of 100 ms decisions

class PickupMemory
{
public:
    // One observation per decision of the tank that picks Onyxia up. Returns
    // the pickup's state (empty when no pickup is under way).
    // `onyxia` is the dragon being picked up (Onyxia or Nefarian) and
    // `dragonEntry` its creature entry: entries are kept per tank and dragon,
    // so observing one dragon never erases the other's memory.
    PickupState Observe(ObjectGuid tank, ObjectGuid onyxia, uint32 dragonEntry, bool pickupActive,
        Vector3 position, bool moving, bool nativeSight, uint64 nowMs)
    {
        // A new dragon of that entry (a new attempt), or the pickup over,
        // retires the tank's entry for that dragon only.
        _entries.erase(std::remove_if(_entries.begin(), _entries.end(),
            [&](Entry const& entry)
            {
                return entry.State.Tank == tank && entry.State.DragonEntry == dragonEntry
                    && (!pickupActive || entry.State.Onyxia != onyxia);
            }), _entries.end());
        if (!pickupActive)
            return PickupState{};
        Entry* entry = FindEntry(tank, onyxia);
        if (!entry)
        {
            Entry fresh;
            fresh.State.Tank = tank;
            fresh.State.Onyxia = onyxia;
            fresh.State.DragonEntry = dragonEntry;
            fresh.StartedMs = nowMs;
            _entries.push_back(fresh);
            entry = &_entries.back();
        }
        // Standing still without sight of her (a leg the native layer never
        // admits, say) spends the budget faster: PickupStallDecisions.
        entry->StalledDecisions = !moving && !nativeSight ? entry->StalledDecisions + 1 : 0;
        if (!moving && !nativeSight
            && std::none_of(entry->State.RejectedSpots.begin(), entry->State.RejectedSpots.end(),
                [&](Vector3 const& spot)
                {
                    return std::hypot(spot.X - position.X, spot.Y - position.Y)
                        < PickupRejectedSpotYards;
                }))
        {
            entry->State.RejectedSpots.push_back(position);
            ++entry->State.Rejections;
        }
        return Snapshot(*entry, nowMs);
    }

    // The state as another member sees it (a damage dealer waiting for the
    // pickup): the same budget, read at `nowMs`.
    PickupState Find(ObjectGuid tank, ObjectGuid onyxia, uint64 nowMs) const
    {
        for (Entry const& entry : _entries)
            if (entry.State.Tank == tank && entry.State.Onyxia == onyxia)
                return Snapshot(entry, nowMs);
        return PickupState{};
    }

private:
    struct Entry
    {
        PickupState State;
        uint64 StartedMs = 0;
        uint32 StalledDecisions = 0;
    };

    Entry* FindEntry(ObjectGuid tank, ObjectGuid onyxia)
    {
        for (Entry& entry : _entries)
            if (entry.State.Tank == tank && entry.State.Onyxia == onyxia)
                return &entry;
        return nullptr;
    }

    static PickupState Snapshot(Entry const& entry, uint64 nowMs)
    {
        PickupState state = entry.State;
        state.ElapsedMs = nowMs > entry.StartedMs ? nowMs - entry.StartedMs : 0;
        state.Exhausted = state.ElapsedMs >= PickupBudgetMs
            || state.Rejections >= PickupRejectionBudget
            || entry.StalledDecisions >= PickupStallDecisions;
        return state;
    }

    std::vector<Entry> _entries;
};

// The order in which the pillars killed their prototypes (round 8 review):
// per attempt (Nefarian's GUID), a pillar's kill time is the first
// observation in phase 2 of its prototype gone after it was once seen.
class PillarKillMemory
{
public:
    std::array<uint64, 3> Observe(ObjectGuid nefarian, bool phaseTwo,
        std::array<bool, 3> const& prototypeAlive, uint64 nowMs)
    {
        if (nefarian != _nefarian)
        {
            _nefarian = nefarian;
            _seen = { false, false, false };
            _kill = { 0, 0, 0 };
        }
        if (phaseTwo)
            for (std::size_t pillar = 0; pillar < 3; ++pillar)
            {
                if (prototypeAlive[pillar])
                    _seen[pillar] = true;
                else if (_seen[pillar] && !_kill[pillar])
                    _kill[pillar] = nowMs ? nowMs : 1;
            }
        return _kill;
    }

private:
    ObjectGuid _nefarian;
    std::array<bool, 3> _seen{ false, false, false };
    std::array<uint64, 3> _kill{ 0, 0, 0 };
};
}

#endif
