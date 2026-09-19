#ifndef TRINITY_BOT_MAGMAW_BALANCE_MUSHROOM_DUTY_H
#define TRINITY_BOT_MAGMAW_BALANCE_MUSHROOM_DUTY_H

#include "Define.h"

#include <cstddef>
#include <string_view>

struct BotActionCandidate;
struct ResolvedCombatAction;
class Player;
class Unit;

namespace BotEncounter
{
struct MagmawBalanceMushroomDuty
{
    static constexpr uint32 WildMushroomSpellId = 88747;
    static constexpr uint32 WildMushroomDetonateSpellId = 88751;
    static constexpr uint32 RequiredMushroomCount = 3;
    static constexpr uint32 PillarOfFlameEntry = 41843;
    static constexpr uint32 ParasiteEntry = 41806;
    static constexpr uint32 ParasiteAltEntry = 42321;

    static bool IsParasiteEntry(uint32 entry)
    {
        return entry == ParasiteEntry || entry == ParasiteAltEntry;
    }

    static bool IsActive(bool validationRouteEnabled,
        std::string_view routeNodeId, std::string_view specTag,
        uint32 targetEntry, bool livePillarVisible = false)
    {
        return validationRouteEnabled
            && routeNodeId == "bwd.magmaw.encounter"
            && specTag == "balance_druid"
            && (livePillarVisible || IsParasiteEntry(targetEntry));
    }

    static bool NeedsPlacement(std::size_t ownedMushrooms)
    {
        return ownedMushrooms < RequiredMushroomCount;
    }

    static bool ReadyToDetonate(std::size_t ownedMushrooms)
    {
        return ownedMushrooms >= RequiredMushroomCount;
    }
};

struct MagmawBalanceMushroomState
{
    bool Active = false;
    bool LivePillarVisible = false;
    bool SolarEclipse = false;
    uint32 OwnedMushrooms = 0;
};

MagmawBalanceMushroomState ObserveMagmawBalanceMushroomState(
    Player* bot, bool validationRouteEnabled, std::string_view routeNodeId,
    std::string_view specTag, uint32 targetEntry, bool solarEclipse);
bool IsMagmawBalanceMushroomPlacement(
    MagmawBalanceMushroomState const& state, BotActionCandidate const& candidate);
bool IsMagmawBalanceMushroomDetonation(
    MagmawBalanceMushroomState const& state, BotActionCandidate const& candidate);
bool IsMagmawBalanceMushroomAction(
    MagmawBalanceMushroomState const& state, BotActionCandidate const& candidate);
char const* MagmawBalanceMushroomRejection(
    MagmawBalanceMushroomState const& state, BotActionCandidate const& candidate);
bool SetMagmawBalanceMushroomGroundTarget(
    ResolvedCombatAction& action, Player const* bot, Unit const* target);
}

#endif
