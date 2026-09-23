#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBalanceMushroomDuty.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotTypes.h"
#include "Creature.h"
#include "Map.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

#include <algorithm>
#include <cmath>
#include <list>
#include <vector>

namespace
{
constexpr float MagmawMushroomParasiteSearchRange = 60.0f;

uint32 OwnedWildMushroomCount(Player* bot)
{
    if (!bot)
        return 0;

    SpellInfo const* mushroomSpell = sSpellMgr->GetSpellInfo(
        BotEncounter::MagmawBalanceMushroomDuty::WildMushroomSpellId);
    if (!mushroomSpell)
        return 0;

    std::list<Creature*> mushrooms;
    bot->GetAllMinionsByEntry(mushrooms,
        uint32(mushroomSpell->Effects[EFFECT_0].MiscValue));
    return uint32(std::count_if(mushrooms.begin(), mushrooms.end(),
        [](Creature const* mushroom)
        {
            return mushroom && mushroom->IsAlive();
        }));
}

float NativeMagmawMushroomRadius(Player const* bot)
{
    SpellInfo const* damageSpell = sSpellMgr->GetSpellInfo(
        BotEncounter::MagmawBalanceMushroomDuty::WildMushroomDamageSpellId);
    if (!damageSpell)
        return 0.0f;

    float const radius = damageSpell->Effects[EFFECT_0].CalcRadius(
        const_cast<Player*>(bot), SpellTargetIndex::TargetB);
    return std::isfinite(radius) && radius > 0.0f ? radius : 0.0f;
}

// Collects live, attackable, engaged parasites. liveParasites, when given,
// also counts live attackable parasites that are not engaged yet, so a fresh
// spawn is never mistaken for the end of a wave.
bool CollectMagmawBalanceMushroomParasites(Player const* bot,
    std::vector<Creature const*>& parasites, uint32* liveParasites = nullptr)
{
    if (liveParasites)
        *liveParasites = 0;
    if (!bot || !bot->GetMap())
        return false;

    Map* map = bot->GetMap();
    auto appendEntry = [&](uint32 entry)
    {
        std::vector<Creature*> nearby;
        bot->GetCreatureListWithEntryInGrid(
            nearby, entry, MagmawMushroomParasiteSearchRange);
        for (Creature const* parasite : nearby)
        {
            if (!parasite || !parasite->IsInWorld()
                || parasite->GetMap() != map
                || parasite->GetInstanceId() != bot->GetInstanceId()
                || !parasite->IsAlive()
                || !bot->IsValidAttackTarget(parasite))
                continue;
            if (liveParasites)
                ++*liveParasites;
            if (parasite->IsInCombat() || parasite->GetVictim())
                parasites.push_back(parasite);
        }
    };

    appendEntry(BotEncounter::MagmawBalanceMushroomDuty::ParasiteEntry);
    appendEntry(BotEncounter::MagmawBalanceMushroomDuty::ParasiteAltEntry);
    return !parasites.empty();
}

bool BuildMagmawBalanceMushroomGroundCandidates(Player const* bot,
    std::vector<BotEncounter::MagmawBalanceMushroomDuty::GroundCandidate>& candidates,
    float& nativeRadius)
{
    if (!bot)
        return false;

    Map* map = bot->GetMap();
    SpellInfo const* placementSpell = sSpellMgr->GetSpellInfo(
        BotEncounter::MagmawBalanceMushroomDuty::WildMushroomSpellId);
    if (!map || !placementSpell)
        return false;

    nativeRadius = NativeMagmawMushroomRadius(bot);
    if (nativeRadius <= 0.0f)
        return false;

    float const nativeMinimum = bot->GetSpellMinRangeForTarget(nullptr, placementSpell);
    float const nativeMaximum = bot->GetSpellMaxRangeForTarget(nullptr, placementSpell);
    bool const hasNativeRange = placementSpell->RangeEntry != nullptr;
    if (hasNativeRange
        && (!std::isfinite(nativeMinimum) || !std::isfinite(nativeMaximum)
            || nativeMinimum < 0.0f || nativeMaximum < nativeMinimum))
        return false;

    std::vector<Creature const*> parasites;
    if (!CollectMagmawBalanceMushroomParasites(bot, parasites))
        return false;
    for (Creature const* parasite : parasites)
    {
        BotEncounter::MagmawBalanceMushroomDuty::GroundCandidate candidate;
        candidate.ParasiteGuid = parasite->GetGUID().GetRawValue();
        candidate.ParasiteX = parasite->GetPositionX();
        candidate.ParasiteY = parasite->GetPositionY();
        candidate.ParasiteZ = parasite->GetPositionZ();
        candidate.Live = true;
        candidate.Attackable = true;
        candidate.Engaged = true;
        candidate.GroundX = parasite->GetPositionX();
        candidate.GroundY = parasite->GetPositionY();
        candidate.GroundZ = map->GetHeight(bot->GetPhaseShift(),
            candidate.GroundX, candidate.GroundY,
            parasite->GetPositionZ() + 2.0f, true, 64.0f);
        candidate.GroundProjectionValid = candidate.GroundZ != INVALID_HEIGHT
            && std::isfinite(candidate.GroundZ);
        if (!candidate.GroundProjectionValid)
        {
            candidates.push_back(candidate);
            continue;
        }

        candidate.ParasiteToGroundDistance = parasite->GetExactDist(
            candidate.GroundX, candidate.GroundY, candidate.GroundZ);
        candidate.ActorToGroundDistance = bot->GetExactDist(
            candidate.GroundX, candidate.GroundY, candidate.GroundZ);
        candidate.ActorRangeValid = !hasNativeRange
            || (candidate.ActorToGroundDistance >= nativeMinimum
                && candidate.ActorToGroundDistance <= nativeMaximum);
        candidate.ActorLineOfSight = bot->IsWithinLOS(
            candidate.GroundX, candidate.GroundY, candidate.GroundZ,
            LINEOFSIGHT_ALL_CHECKS, VMAP::ModelIgnoreFlags::M2);
        candidates.push_back(candidate);
    }
    return !candidates.empty();
}

bool SelectMagmawBalanceMushroomGroundPoint(Player const* bot,
    BotEncounter::MagmawBalanceMushroomDuty::GroundPoint& point,
    uint32* bestLawfulHits = nullptr)
{
    if (bestLawfulHits)
        *bestLawfulHits = 0;
    std::vector<BotEncounter::MagmawBalanceMushroomDuty::GroundCandidate> candidates;
    float nativeRadius = 0.0f;
    if (!BuildMagmawBalanceMushroomGroundCandidates(bot, candidates, nativeRadius))
        return false;
    return BotEncounter::MagmawBalanceMushroomDuty::SelectGroundPoint(
        candidates, nativeRadius, point, bestLawfulHits);
}

struct MagmawBalanceMushroomDetonationObservation
{
    uint32 Hits = 0;
    uint32 LiveParasites = 0;
};

MagmawBalanceMushroomDetonationObservation ObserveMagmawBalanceMushroomDetonation(
    Player* bot, uint32 ownedMushrooms)
{
    using Duty = BotEncounter::MagmawBalanceMushroomDuty;
    MagmawBalanceMushroomDetonationObservation observed;
    if (!bot || ownedMushrooms < Duty::RequiredMushroomCount)
        return observed;

    SpellInfo const* mushroomSpell = sSpellMgr->GetSpellInfo(
        Duty::WildMushroomSpellId);
    float const nativeRadius = NativeMagmawMushroomRadius(bot);
    if (!mushroomSpell || nativeRadius <= 0.0f)
        return observed;

    std::vector<Creature const*> parasites;
    if (!CollectMagmawBalanceMushroomParasites(bot, parasites,
            &observed.LiveParasites))
        return observed;

    std::list<Creature*> mushrooms;
    bot->GetAllMinionsByEntry(mushrooms,
        uint32(mushroomSpell->Effects[EFFECT_0].MiscValue));
    Map* map = bot->GetMap();
    std::vector<Duty::Point3> mushroomPositions;
    for (Creature const* mushroom : mushrooms)
        if (mushroom && mushroom->IsInWorld() && mushroom->IsAlive()
            && mushroom->GetMap() == map
            && mushroom->GetInstanceId() == bot->GetInstanceId())
            mushroomPositions.push_back({ mushroom->GetPositionX(),
                mushroom->GetPositionY(), mushroom->GetPositionZ() });
    std::vector<Duty::Point3> parasitePositions;
    for (Creature const* parasite : parasites)
        parasitePositions.push_back({ parasite->GetPositionX(),
            parasite->GetPositionY(), parasite->GetPositionZ() });
    observed.Hits = Duty::CountDetonationHits(mushroomPositions,
        parasitePositions, nativeRadius);
    return observed;
}
}

namespace BotEncounter
{
MagmawBalanceMushroomState ObserveMagmawBalanceMushroomState(
    Player* bot, bool validationRouteEnabled, std::string_view routeNodeId,
    std::string_view specTag, uint32 targetEntry, bool solarEclipse)
{
    MagmawBalanceMushroomState state;
    bool const livePillarVisible = bot
        && bot->FindNearestCreature(
            MagmawBalanceMushroomDuty::PillarOfFlameEntry, 60.0f, true);
    state.LivePillarVisible = livePillarVisible;
    state.Active = MagmawBalanceMushroomDuty::IsActive(
        validationRouteEnabled, routeNodeId, specTag, targetEntry,
        livePillarVisible);
    state.SolarEclipse = solarEclipse;
    if (!state.Active)
        return state;

    state.OwnedMushrooms = OwnedWildMushroomCount(bot);
    MagmawBalanceMushroomDuty::GroundPoint point;
    state.GroundTargetAvailable = SelectMagmawBalanceMushroomGroundPoint(
        bot, point, &state.GroundParasiteHits);
    MagmawBalanceMushroomDetonationObservation const detonation =
        ObserveMagmawBalanceMushroomDetonation(bot, state.OwnedMushrooms);
    state.DetonationParasiteHits = detonation.Hits;
    state.LiveParasites = detonation.LiveParasites;
    state.OwnedMushroomHasNativeRangeCandidate = detonation.Hits > 0;
    state.DetonationReady = MagmawBalanceMushroomDuty::DetonationWorthwhile(
        state.OwnedMushrooms, detonation.Hits, detonation.LiveParasites);
    return state;
}

bool IsMagmawBalanceMushroomPlacement(
    MagmawBalanceMushroomState const& state, BotActionCandidate const& candidate)
{
    return state.Active
        && state.GroundTargetAvailable
        && candidate.SpellId == MagmawBalanceMushroomDuty::WildMushroomSpellId
        && candidate.Profile.TargetSelector == "ground_enemy"
        && candidate.Profile.RequiresGroundTarget;
}

bool IsMagmawBalanceMushroomDetonation(
    MagmawBalanceMushroomState const& state, BotActionCandidate const& candidate)
{
    return state.Active
        && state.DetonationReady
        && candidate.SpellId == MagmawBalanceMushroomDuty::WildMushroomDetonateSpellId
        && candidate.Profile.TargetSelector == "self";
}

bool IsMagmawBalanceMushroomAction(
    MagmawBalanceMushroomState const& state, BotActionCandidate const& candidate)
{
    return IsMagmawBalanceMushroomPlacement(state, candidate)
        || IsMagmawBalanceMushroomDetonation(state, candidate);
}

char const* MagmawBalanceMushroomRejection(
    MagmawBalanceMushroomState const& state, BotActionCandidate const& candidate)
{
    if (candidate.SpellId == MagmawBalanceMushroomDuty::WildMushroomSpellId)
    {
        if (!state.Active)
            return "prepull_only";
        if (!IsMagmawBalanceMushroomPlacement(state, candidate))
            return candidate.Profile.TargetSelector != "ground_enemy"
                || !candidate.Profile.RequiresGroundTarget
                ? "magmaw_mushroom_profile_not_ground_gated"
                : (state.GroundParasiteHits > 0
                    ? "magmaw_mushroom_parasite_density_below_threshold"
                    : "magmaw_mushroom_ground_target_unavailable");
        if (!MagmawBalanceMushroomDuty::NeedsPlacement(state.OwnedMushrooms))
            return "magmaw_mushrooms_already_placed";
    }

    if (candidate.SpellId == MagmawBalanceMushroomDuty::WildMushroomDetonateSpellId)
    {
        if (state.Active)
        {
            if (!IsMagmawBalanceMushroomDetonation(state, candidate))
                return candidate.Profile.TargetSelector != "self"
                    ? "magmaw_mushroom_profile_not_self_targeted"
                    : (!MagmawBalanceMushroomDuty::ReadyToDetonate(state.OwnedMushrooms)
                        ? "magmaw_mushrooms_not_ready"
                        : (!state.OwnedMushroomHasNativeRangeCandidate
                            ? "magmaw_mushroom_native_range_candidate_unavailable"
                            : "magmaw_mushroom_parasite_hits_below_threshold"));
            if (!MagmawBalanceMushroomDuty::ReadyToDetonate(state.OwnedMushrooms))
                return "magmaw_mushrooms_not_ready";
        }
        else if (!state.SolarEclipse || state.OwnedMushrooms < 3)
            return "solar_mushrooms_not_ready";
    }

    return nullptr;
}

bool SetMagmawBalanceMushroomGroundTarget(
    ResolvedCombatAction& action, Player const* bot, Unit const* target)
{
    action.HasGroundTarget = false;
    if (!bot || !target)
        return false;

    MagmawBalanceMushroomDuty::GroundPoint point;
    if (!SelectMagmawBalanceMushroomGroundPoint(bot, point))
        return false;

    action.HasGroundTarget = true;
    action.GroundTargetX = point.X;
    action.GroundTargetY = point.Y;
    action.GroundTargetZ = point.Z;
    return true;
}
}
