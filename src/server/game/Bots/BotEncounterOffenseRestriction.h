#ifndef TRINITY_BOT_ENCOUNTER_OFFENSE_RESTRICTION_H
#define TRINITY_BOT_ENCOUNTER_OFFENSE_RESTRICTION_H

#include "Bots/BotRaidAreaAuthority.h"
#include "ObjectGuid.h"

#include <algorithm>
#include <chrono>
#include <mutex>
#include <unordered_map>
#include <utility>
#include <vector>

// A bot's current-encounter offense restriction, applied through
// BotRaidAreaAuthority::SetCurrentEncounterRestrictions: every listed entry
// is restricted for the bot and only the listed GUIDs are allowed. Direct
// casts on a restricted unit are refused, area spells are refused next to
// one, and the bot's pet, guardians and totems follow the owner's authority.
//
// An encounter re-applies its restriction from its route-authority hook after
// ConfigureValidationRouteCombatAuthority clears it, every tick, so the
// restriction never depends on which candidate the kernel resolves.
// Omnotron (the four constructs) and Maloriak (the 30% add switch) use it.
namespace BotEncounterOffense
{
struct OffenseRestriction
{
    std::vector<uint32> Entries;
    std::vector<uint64> AllowedGuids;
};

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

// Guardian area sparing: a leased per-owner flag an encounter sets with its
// restriction. A guardian summoned by a totem (the shaman's Greater Fire
// Elemental) is not owned by the player directly, so the controlled-unit
// gates never see its owner; its script skips an area spell while a unit
// restricted for the owner stands in the spell's radius. Only Maloriak's add
// switch sets it, so every other scenario keeps its elemental unchanged.
constexpr uint64 GuardianAreaSparingLeaseMs = 3000;
inline std::mutex GuardianAreaSparingMutex;
inline std::unordered_map<uint64, uint64> GuardianAreaSparingLeases;

inline uint64 SteadyNowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}

inline void SetGuardianAreaSparing(uint64 ownerGuid, bool sparing,
    uint64 leaseMs = GuardianAreaSparingLeaseMs)
{
    if (!ownerGuid)
        return;
    std::lock_guard<std::mutex> guard(GuardianAreaSparingMutex);
    if (sparing)
        GuardianAreaSparingLeases[ownerGuid] = SteadyNowMs() + leaseMs;
    else
        GuardianAreaSparingLeases.erase(ownerGuid);
}

inline bool IsGuardianAreaSparing(uint64 ownerGuid)
{
    std::lock_guard<std::mutex> guard(GuardianAreaSparingMutex);
    auto lease = GuardianAreaSparingLeases.find(ownerGuid);
    if (lease == GuardianAreaSparingLeases.end())
        return false;
    if (lease->second > SteadyNowMs())
        return true;
    GuardianAreaSparingLeases.erase(lease);
    return false;
}

// A guardian's area spell of the given radius around each center reaches a
// restricted unit (its distance within radius plus its combat reach). The
// pure decision behind the shaman elemental's check (pet_shaman.cpp
// ShamanAreaCastBlocked); positions are 2D.
struct AreaPoint
{
    float X = 0.0f;
    float Y = 0.0f;
    float Reach = 0.0f;
};

inline bool AreaReachesRestricted(std::vector<AreaPoint> const& centers,
    float radius, std::vector<AreaPoint> const& restricted)
{
    if (radius <= 0.0f)
        return false;
    for (AreaPoint const& center : centers)
        for (AreaPoint const& unit : restricted)
        {
            float const dx = unit.X - center.X;
            float const dy = unit.Y - center.Y;
            float const limit = radius + unit.Reach;
            if (dx * dx + dy * dy <= limit * limit)
                return true;
        }
    return false;
}

// Widens the restriction by exactly one target for the lifetime of this
// object, then restores the tick's restriction. Use it around the native
// cast of one interrupt, purge or taunt and nothing else: an allowed GUID
// lifts the restriction for every offense path of the bot, including area
// spells beside it, so the exception never enters the tick's allowed set.
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
