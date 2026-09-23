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
    // DPS-066, Magmaw 10N Balance 30001 (verdict b2-fd4ba456): one set costs
    // four GCDs, three placements and Detonate. A prompt first set on the
    // spawn cluster landed 16 hits for 336k, while the third set of each kill,
    // placed on the single parasite in range, landed 2 hits for 24k (about
    // -0.9k DPS). A placement point therefore needs at least three live,
    // engaged parasites inside the native explosion radius, so a full set can
    // reach nine hits. Detonate spends one GCD on already-placed mushrooms and
    // needs three native damage events (12-21k each in that evidence) unless
    // the wave is ending. The radius is not a constant: it is read at runtime
    // from Wild Mushroom 78777, the payload that Wild Mushroom: Detonate 88751
    // casts at every owned mushroom (spell_dru_wild_mushroom_detonate). 88751
    // itself is a caster-targeted dummy with no radius. Pinned 4.3.4 client
    // data: 78777 effect 0 TargetB 16 (TARGET_UNIT_DEST_AREA_ENEMY) uses
    // SpellRadius 29, 6.0 yd.
    static constexpr uint32 RequiredParasiteHits = 3;
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

    struct Point3
    {
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
    };

    static bool Finite(Point3 const& position)
    {
        return std::isfinite(position.X) && std::isfinite(position.Y)
            && std::isfinite(position.Z);
    }

    static bool WithinRadius(Point3 const& left, Point3 const& right,
        float nativeRadius)
    {
        float const dx = left.X - right.X;
        float const dy = left.Y - right.Y;
        float const dz = left.Z - right.Z;
        return Finite(left) && Finite(right)
            && std::sqrt(dx * dx + dy * dy + dz * dz) <= nativeRadius;
    }

    // One native 78777 damage event per owned mushroom and engaged parasite
    // inside that mushroom's radius.
    static uint32 CountDetonationHits(std::vector<Point3> const& mushrooms,
        std::vector<Point3> const& parasites, float nativeRadius)
    {
        if (!std::isfinite(nativeRadius) || nativeRadius <= 0.0f)
            return 0;
        uint32 hits = 0;
        for (Point3 const& mushroom : mushrooms)
            for (Point3 const& parasite : parasites)
                if (WithinRadius(mushroom, parasite, nativeRadius))
                    ++hits;
        return hits;
    }

    // Fewer live parasites than the threshold remain, so the wave cannot form
    // another qualifying cluster; detonate whatever the placed set still hits.
    static bool WaveEnding(std::size_t liveParasites)
    {
        return liveParasites < RequiredParasiteHits;
    }

    static bool DetonationWorthwhile(std::size_t ownedMushrooms,
        uint32 detonationHits, std::size_t liveParasites)
    {
        return ReadyToDetonate(ownedMushrooms) && detonationHits > 0
            && (detonationHits >= RequiredParasiteHits
                || WaveEnding(liveParasites));
    }

    struct GroundCandidate
    {
        uint64 ParasiteGuid = 0;
        float ParasiteX = 0.0f;
        float ParasiteY = 0.0f;
        float ParasiteZ = 0.0f;
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
        uint32 ParasiteHits = 0;
    };

    // Live, attackable, engaged parasites whose position is inside the
    // native radius of the candidate's projected ground point.
    static uint32 CountGroundParasiteHits(
        std::vector<GroundCandidate> const& candidates,
        GroundCandidate const& anchor, float nativeRadius)
    {
        Point3 const ground{ anchor.GroundX, anchor.GroundY, anchor.GroundZ };
        uint32 hits = 0;
        for (GroundCandidate const& candidate : candidates)
            if (candidate.Live && candidate.Attackable && candidate.Engaged
                && WithinRadius(Point3{ candidate.ParasiteX,
                        candidate.ParasiteY, candidate.ParasiteZ },
                    ground, nativeRadius))
                ++hits;
        return hits;
    }

    // Returns the densest lawful anchor. bestLawfulHits reports the density of
    // that anchor even when it is below the placement threshold.
    static bool SelectGroundPoint(std::vector<GroundCandidate> const& candidates,
        float nativeRadius, GroundPoint& selected, uint32* bestLawfulHits = nullptr)
    {
        if (bestLawfulHits)
            *bestLawfulHits = 0;
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
        auto better = [](GroundCandidate const& left, uint32 leftHits,
            GroundCandidate const& right, uint32 rightHits)
        {
            if (leftHits != rightHits)
                return leftHits > rightHits;
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
        uint32 bestHits = 0;
        for (GroundCandidate const& candidate : candidates)
        {
            if (!lawful(candidate))
                continue;
            uint32 const hits = CountGroundParasiteHits(candidates, candidate,
                nativeRadius);
            if (!best || better(candidate, hits, *best, bestHits))
            {
                best = &candidate;
                bestHits = hits;
            }
        }
        if (bestLawfulHits)
            *bestLawfulHits = bestHits;
        if (!best || bestHits < RequiredParasiteHits)
            return false;

        selected.ParasiteGuid = best->ParasiteGuid;
        selected.X = best->GroundX;
        selected.Y = best->GroundY;
        selected.Z = best->GroundZ;
        selected.ParasiteHits = bestHits;
        return true;
    }
};

struct MagmawBalanceMushroomState
{
    bool Active = false;
    bool LivePillarVisible = false;
    bool GroundTargetAvailable = false;
    bool OwnedMushroomHasNativeRangeCandidate = false;
    bool DetonationReady = false;
    bool SolarEclipse = false;
    uint32 OwnedMushrooms = 0;
    // Density of the best lawful placement anchor, even below the threshold.
    uint32 GroundParasiteHits = 0;
    uint32 DetonationParasiteHits = 0;
    uint32 LiveParasites = 0;
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
