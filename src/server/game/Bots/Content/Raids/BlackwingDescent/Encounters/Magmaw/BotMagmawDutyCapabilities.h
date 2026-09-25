#ifndef TRINITY_BOT_MAGMAW_DUTY_CAPABILITIES_H
#define TRINITY_BOT_MAGMAW_DUTY_CAPABILITIES_H

#include "Define.h"

#include <cstddef>
#include <optional>
#include <string_view>
#include <vector>

// Who can own a Magmaw duty follows from what the member's spec can do in
// 4.3.4, never from a fixed roster slot, so the same selectors serve the
// accepted shard (2 Fire Mages, Survival Hunter, Balance and Resto druids,
// Elemental Shaman) and the canonical composition (one Fire Mage, a Beast
// Mastery Hunter, Retribution and Assassination melee, Elemental or Resto
// Shaman). The selectors that rank several capable members (baiter rotation,
// hook riders, pull tank) are unchanged; only their admission reads these.
//
// Duties and capabilities:
//  - pull tank: any living tank (BotAdaptiveMagmawStrategySupport.h);
//  - pillar/parasite baiters: two lanes of ranged DPS that keep damaging while
//    they move and own a directional escape, BaitLaneFor below;
//  - chain (pincer) riders: non-baiter DPS without a stationary duty first
//    (BotAdaptiveMagmawStrategyHook.h), so the mushroom caster rides last;
//  - mushrooms: the Wild Mushroom duty caster, IsMushroomCaster;
//  - Bloodlust: one shaman, SelectBloodlustOwner.
// Tank swaps and battle resurrections are not Magmaw duties: the generic
// runtime owns them (route mechanic contract, combat-res reconciler).
namespace BotEncounter::MagmawDutyCapabilities
{
constexpr uint32 BlinkSpell = 1953;
constexpr uint32 DisengageSpell = 781;

enum class BaitLane : uint8
{
    None,
    // Fire Mage: Scorch while moving (Firestarter) and Blink 1953 forward.
    // Arcane and Frost mages cast from a standstill and stay off the lane.
    Blink,
    // Every Hunter spec: shots while moving (Aspect of the Fox) and the
    // class spell Disengage 781 backward.
    Disengage
};

inline bool IsHunterSpec(std::string_view classSpec)
{
    return classSpec == "beast_mastery_hunter"
        || classSpec == "marksmanship_hunter"
        || classSpec == "survival_hunter";
}

inline BaitLane BaitLaneFor(std::string_view role, std::string_view classSpec)
{
    if (role != "dps")
        return BaitLane::None;
    if (classSpec == "fire_mage")
        return BaitLane::Blink;
    return IsHunterSpec(classSpec) ? BaitLane::Disengage : BaitLane::None;
}

// The directional mobility spell a bait lane uses, or 0. The kernel reads
// only the actor's spec here (the lane itself is gated by role).
inline uint32 BaitMobilitySpell(std::string_view classSpec)
{
    if (classSpec == "fire_mage")
        return BlinkSpell;
    return IsHunterSpec(classSpec) ? DisengageSpell : 0u;
}

// Stationary parasite duty: Wild Mushroom placements and Detonate
// (BotMagmawBalanceMushroomDuty). Balance keeps its casts where it stands.
inline bool IsMushroomCaster(std::string_view classSpec)
{
    return classSpec == "balance_druid";
}

inline bool Contains(std::string_view classSpec, std::string_view token)
{
    return classSpec.find(token) != std::string_view::npos;
}

// Bloodlust 2825 / Heroism 32182 are shaman class spells of every spec.
inline bool IsBloodlustCaster(std::string_view classSpec)
{
    return Contains(classSpec, "shaman");
}

// One member of a roster view for the Bloodlust owner rule. Templated on the
// GUID type so the runtime roster, the blackboard and offline probes share it.
template <typename GuidType>
struct BloodlustCandidate
{
    GuidType Guid;
    std::string_view Role;
    std::string_view ClassSpec;
};

// One raid-haste owner, or none when the choice is ambiguous: the single DPS
// Elemental Shaman (the accepted rule), else the single DPS shaman, else the
// single shaman of any role (a Restoration Shaman in a three-healer setup).
template <typename GuidType>
std::optional<GuidType> SelectBloodlustOwner(
    std::vector<BloodlustCandidate<GuidType>> const& members)
{
    auto single = [&members](auto accept) -> std::optional<GuidType>
    {
        std::optional<GuidType> owner;
        std::size_t count = 0;
        for (BloodlustCandidate<GuidType> const& member : members)
            if (IsBloodlustCaster(member.ClassSpec) && accept(member))
            {
                ++count;
                owner = member.Guid;
            }
        if (count != 1)
            return std::nullopt;
        return owner;
    };
    std::size_t shamans = 0;
    std::size_t dpsShamans = 0;
    for (BloodlustCandidate<GuidType> const& member : members)
        if (IsBloodlustCaster(member.ClassSpec))
        {
            ++shamans;
            dpsShamans += member.Role == "dps" ? 1 : 0;
        }
    if (std::optional<GuidType> elemental = single(
            [](BloodlustCandidate<GuidType> const& member)
            {
                return member.Role == "dps" && member.ClassSpec == "elemental_shaman";
            }))
        return elemental;
    if (dpsShamans)
        return single([](BloodlustCandidate<GuidType> const& member) { return member.Role == "dps"; });
    if (shamans != 1)
        return std::nullopt;
    return single([](BloodlustCandidate<GuidType> const&) { return true; });
}
}

#endif
