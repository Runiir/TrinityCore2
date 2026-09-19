#ifndef TRINITY_BOT_MAGMAW_BALANCE_MUSHROOM_DUTY_H
#define TRINITY_BOT_MAGMAW_BALANCE_MUSHROOM_DUTY_H

#include "Define.h"

#include <cmath>
#include <cstddef>
#include <string_view>
#include <vector>

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
    static constexpr uint32 WildMushroomDamageSpellId = 78777;
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

    struct GroundCandidate
    {
        uint64 ParasiteGuid = 0;
        float GroundX = 0.0f;
        float GroundY = 0.0f;
        float GroundZ = 0.0f;
        float ParasiteToGroundDistance = 0.0f;
        float ActorToGroundDistance = 0.0f;
        bool Live = false;
        bool Attackable = false;
        bool Engaged = false;
        bool GroundProjectionValid = false;
        bool ActorRangeValid = false;
        bool ActorLineOfSight = false;
    };

    struct GroundPoint
    {
        uint64 ParasiteGuid = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
    };

    static bool SelectGroundPoint(std::vector<GroundCandidate> const& candidates,
        float nativeRadius, GroundPoint& selected)
    {
        if (!std::isfinite(nativeRadius) || nativeRadius <= 0.0f)
            return false;

        auto lawful = [nativeRadius](GroundCandidate const& candidate)
        {
            return candidate.Live && candidate.Attackable && candidate.Engaged
                && candidate.GroundProjectionValid
                && std::isfinite(candidate.GroundX)
                && std::isfinite(candidate.GroundY)
                && std::isfinite(candidate.GroundZ)
                && std::isfinite(candidate.ParasiteToGroundDistance)
                && std::isfinite(candidate.ActorToGroundDistance)
                && candidate.ParasiteToGroundDistance <= nativeRadius
                && candidate.ActorRangeValid
                && candidate.ActorLineOfSight;
        };
        auto better = [](GroundCandidate const& left, GroundCandidate const& right)
        {
            if (left.ParasiteToGroundDistance != right.ParasiteToGroundDistance)
                return left.ParasiteToGroundDistance < right.ParasiteToGroundDistance;
            if (left.ParasiteGuid != right.ParasiteGuid)
                return left.ParasiteGuid < right.ParasiteGuid;
            if (left.GroundX != right.GroundX)
                return left.GroundX < right.GroundX;
            if (left.GroundY != right.GroundY)
                return left.GroundY < right.GroundY;
            return left.GroundZ < right.GroundZ;
        };

        GroundCandidate const* best = nullptr;
        for (GroundCandidate const& candidate : candidates)
            if (lawful(candidate) && (!best || better(candidate, *best)))
                best = &candidate;
        if (!best)
            return false;

        selected.ParasiteGuid = best->ParasiteGuid;
        selected.X = best->GroundX;
        selected.Y = best->GroundY;
        selected.Z = best->GroundZ;
        return true;
    }
};

struct MagmawBalanceMushroomState
{
    bool Active = false;
    bool LivePillarVisible = false;
    bool GroundTargetAvailable = false;
    bool OwnedMushroomHasNativeRangeCandidate = false;
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
