#ifndef TRINITY_BOT_OMNOTRON_OFFENSE_AUTHORITY_H
#define TRINITY_BOT_OMNOTRON_OFFENSE_AUTHORITY_H

#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronFacts.h"
#include <algorithm>
#include <utility>
#include <vector>

// Per-bot offensive authority over the four constructs, applied through the
// shared current-encounter restriction (BotRaidAreaAuthority): every construct
// entry is restricted and only the plan's active, unshielded constructs are
// allowed. Direct casts on a restricted construct are refused and area spells
// are refused next to one (HasNearbyProtectedEncounterTarget).
//
// A single interrupt or taunt may still target a shielded construct. That
// exception is scoped to the one native cast (SingleCastAllowance) and never
// enters the tick's allowed set: an allowed GUID lifts the restriction for
// every offense path of the bot, including area spells beside it.
namespace BotEncounter::Omnotron
{
struct OffenseRestriction
{
    std::vector<uint32> Entries;
    std::vector<uint64> AllowedGuids;
};

inline OffenseRestriction BuildOffenseRestriction(std::vector<ObjectGuid> const& allowed)
{
    OffenseRestriction restriction;
    restriction.Entries = { ArcanotronEntry, MagmatronEntry, ElectronEntry, ToxitronEntry };
    for (ObjectGuid guid : allowed)
        if (!guid.IsEmpty())
            restriction.AllowedGuids.push_back(guid.GetRawValue());
    return restriction;
}

inline bool Allows(OffenseRestriction const& restriction, ObjectGuid guid)
{
    return std::find(restriction.AllowedGuids.begin(), restriction.AllowedGuids.end(),
        guid.GetRawValue()) != restriction.AllowedGuids.end();
}

inline void ApplyOffenseRestriction(uint64 ownerGuid, OffenseRestriction const& restriction)
{
    BotRaidAreaAuthority::SetCurrentEncounterRestrictions(ownerGuid,
        restriction.Entries, restriction.AllowedGuids);
}

// Widens the restriction by exactly one target for the lifetime of this
// object, then restores the tick's restriction. Use it around the native
// cast of one interrupt or one taunt and nothing else. A hit under it still
// procs the construct's shield natively, damaging or not (Converted Power,
// Static Shock, Soaked In Poison); that cost is a live signal, not hidden.
class SingleCastAllowance
{
public:
    SingleCastAllowance(uint64 ownerGuid, OffenseRestriction restriction,
        ObjectGuid target)
        : _ownerGuid(ownerGuid), _restriction(std::move(restriction))
    {
        if (!_ownerGuid || target.IsEmpty() || Allows(_restriction, target))
            return;
        OffenseRestriction widened = _restriction;
        widened.AllowedGuids.push_back(target.GetRawValue());
        ApplyOffenseRestriction(_ownerGuid, widened);
        _widened = true;
    }

    ~SingleCastAllowance()
    {
        if (_widened)
            ApplyOffenseRestriction(_ownerGuid, _restriction);
    }

    SingleCastAllowance(SingleCastAllowance const&) = delete;
    SingleCastAllowance& operator=(SingleCastAllowance const&) = delete;

    bool Widened() const { return _widened; }

private:
    uint64 _ownerGuid;
    OffenseRestriction _restriction;
    bool _widened = false;
};
}

#endif
