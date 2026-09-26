#ifndef TRINITY_BOT_ENCOUNTER_COOLDOWN_HOLD_H
#define TRINITY_BOT_ENCOUNTER_COOLDOWN_HOLD_H

#include "Bots/BotWorldPopulationMgrRaidCooldownReservation.h"
#include "Define.h"

#include <chrono>
#include <mutex>
#include <string_view>
#include <unordered_map>

// A per-bot hold on the offensive cooldowns an encounter needs in a later
// window. Maloriak's add switch keeps the raid on the Aberrations from 30%
// until the chambers are empty; a guardian summon, a major offensive
// cooldown, a combat potion or a raid haste spent then is missing from the
// phase-two burn, and a guardian summoned then may not attack the boss. The
// held candidates are the ones the raid route reserves on trash
// (BotRaidCooldownReservation::ReservationReason); emergency, survival and
// reservation-exempt rows are never held.
//
// The encounter publishes the hold from its route-authority hook every
// decision tick, before the kernel resolves, and the entry lapses after its
// lease, so a bot that stops ticking the encounter (death, a recovery walk,
// the next node) cannot keep it. Scope: the profile resolvers
// (ResolveProfileCombatAction's admission and SelectCombatSpell).
namespace BotEncounterCooldownHold
{
constexpr uint64 DefaultLeaseMs = 3000;

inline std::mutex Mutex;
// Owner raw GUID -> lease expiry (steady clock, ms).
inline std::unordered_map<uint64, uint64> Leases;

inline uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}

inline void Set(uint64 ownerGuid, bool held, uint64 leaseMs = DefaultLeaseMs)
{
    if (!ownerGuid)
        return;
    std::lock_guard<std::mutex> guard(Mutex);
    if (held)
        Leases[ownerGuid] = NowMs() + leaseMs;
    else
        Leases.erase(ownerGuid);
}

inline bool IsHeld(uint64 ownerGuid)
{
    std::lock_guard<std::mutex> guard(Mutex);
    auto lease = Leases.find(ownerGuid);
    if (lease == Leases.end())
        return false;
    if (lease->second > NowMs())
        return true;
    Leases.erase(lease);
    return false;
}

// The category decision alone, without the owner's lease: the raid route's
// own trash reservation, asked as if on trash, so its emergency, survival
// and exemption rules apply unchanged.
inline char const* HoldReason(BotRaidCooldownReservation::CandidateContext const& candidate)
{
    BotRaidCooldownReservation::RouteContext trash;
    trash.ValidationRouteEnabled = true;
    trash.RaidInstance = true;
    trash.RouteKind = "trash";
    char const* reserved = BotRaidCooldownReservation::ReservationReason(trash, candidate);
    if (!reserved)
        return nullptr;
    std::string_view const reason(reserved);
    if (reason == "raid_bloodlust_reserved")
        return "encounter_hold_bloodlust_reserved";
    if (reason == "raid_combat_potion_reserved")
        return "encounter_hold_combat_potion_reserved";
    if (reason == "raid_offensive_guardian_reserved")
        return "encounter_hold_offensive_guardian_reserved";
    return "encounter_hold_offensive_cooldown_reserved";
}

// Non-null while ownerGuid's hold is live and the candidate is held. The
// category check comes first, so most candidates never take the lock.
inline char const* ReservationReason(uint64 ownerGuid,
    BotRaidCooldownReservation::CandidateContext const& candidate)
{
    char const* reason = HoldReason(candidate);
    return reason && IsHeld(ownerGuid) ? reason : nullptr;
}
}

#endif
