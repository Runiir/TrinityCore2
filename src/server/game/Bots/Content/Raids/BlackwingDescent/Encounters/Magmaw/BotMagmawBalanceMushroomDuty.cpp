#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBalanceMushroomDuty.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotTypes.h"
#include "Creature.h"
#include "Map.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <list>
#include <utility>

namespace
{
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
}

namespace BotEncounter
{
MagmawBalanceMushroomState ObserveMagmawBalanceMushroomState(
    Player* bot, bool validationRouteEnabled, std::string_view routeNodeId,
    std::string_view specTag, uint32 targetEntry, bool solarEclipse)
{
    MagmawBalanceMushroomState state;
    state.Active = MagmawBalanceMushroomDuty::IsActive(
        validationRouteEnabled, routeNodeId, specTag, targetEntry);
    state.SolarEclipse = solarEclipse;
    state.OwnedMushrooms = state.Active ? OwnedWildMushroomCount(bot) : 0;
    return state;
}

bool IsMagmawBalanceMushroomPlacement(
    MagmawBalanceMushroomState const& state, BotActionCandidate const& candidate)
{
    return state.Active
        && candidate.SpellId == MagmawBalanceMushroomDuty::WildMushroomSpellId
        && candidate.Profile.TargetSelector == "ground_enemy"
        && candidate.Profile.RequiresGroundTarget;
}

bool IsMagmawBalanceMushroomDetonation(
    MagmawBalanceMushroomState const& state, BotActionCandidate const& candidate)
{
    return state.Active
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
            return "magmaw_mushroom_profile_not_ground_gated";
        if (!MagmawBalanceMushroomDuty::NeedsPlacement(state.OwnedMushrooms))
            return "magmaw_mushrooms_already_placed";
    }

    if (candidate.SpellId == MagmawBalanceMushroomDuty::WildMushroomDetonateSpellId)
    {
        if (state.Active)
        {
            if (!IsMagmawBalanceMushroomDetonation(state, candidate))
                return "magmaw_mushroom_profile_not_self_targeted";
            if (!MagmawBalanceMushroomDuty::ReadyToDetonate(state.OwnedMushrooms))
                return "magmaw_mushrooms_not_ready";
        }
        else if (!state.SolarEclipse || state.OwnedMushrooms < 3)
            return "solar_mushrooms_not_ready";
    }

    return nullptr;
}

void SetMagmawBalanceMushroomGroundTarget(
    ResolvedCombatAction& action, Player const* bot, Unit const* target)
{
    if (!target)
        return;

    // The player mechanic is to put the mushrooms below the lava spawn. The
    // parasite is a moving airborne target, so its position is a poor ground
    // spell anchor and was the source of repeated destination-LOS failures in
    // the shard35 canary. Prefer the live Pillar of Flame while it exists;
    // retain the parasite as a bounded fallback after the pillar despawns. The
    // resulting point is the live floor position of the lava spawn.
    Creature const* pillar = target->FindNearestCreature(
        MagmawBalanceMushroomDuty::PillarOfFlameEntry, 20.0f, true);
    Unit const* groundAnchor = pillar ? static_cast<Unit const*>(pillar) : target;
    float groundX = groundAnchor->GetPositionX();
    float groundY = groundAnchor->GetPositionY();
    float groundZ = groundAnchor->GetPositionZ();
    Map* map = target->GetMap();
    auto resolveFloor = [&](float x, float y, float hintZ, float& resolvedZ)
    {
        if (!map)
            return false;
        float const sampledZ = map->GetHeight(target->GetPhaseShift(), x, y,
            hintZ + 2.0f, true, 64.0f);
        if (sampledZ == INVALID_HEIGHT || !std::isfinite(sampledZ))
            return false;
        resolvedZ = sampledZ;
        return true;
    };
    resolveFloor(groundX, groundY, groundZ, groundZ);

    // Spell::CheckCast applies the same destination LOS check to a ground
    // spell. If the exact add coordinate is hidden by encounter geometry,
    // keep the point on the platform but search a small ring around the lava
    // spawn. The detonation radius still covers the parasite wave while the
    // lateral points avoid a pillar/body edge that blocks one ray.
    if (bot && !bot->IsWithinLOS(groundX, groundY, groundZ,
            LINEOFSIGHT_ALL_CHECKS, VMAP::ModelIgnoreFlags::M2))
    {
        float const towardX = bot->GetPositionX() - groundX;
        float const towardY = bot->GetPositionY() - groundY;
        float const towardLength = std::sqrt(towardX * towardX + towardY * towardY);
        if (towardLength > 0.01f)
        {
            float const directionX = towardX / towardLength;
            float const directionY = towardY / towardLength;
            float const lateralX = -directionY;
            float const lateralY = directionX;
            std::array<std::pair<float, float>, 12> const offsets = {{
                { 2.0f * directionX, 2.0f * directionY },
                { 4.0f * directionX, 4.0f * directionY },
                { 6.0f * directionX, 6.0f * directionY },
                { 2.0f * lateralX, 2.0f * lateralY },
                {-2.0f * lateralX,-2.0f * lateralY },
                { 4.0f * lateralX, 4.0f * lateralY },
                {-4.0f * lateralX,-4.0f * lateralY },
                { 2.0f * directionX + 2.0f * lateralX,
                  2.0f * directionY + 2.0f * lateralY },
                { 2.0f * directionX - 2.0f * lateralX,
                  2.0f * directionY - 2.0f * lateralY },
                { 4.0f * directionX + 2.0f * lateralX,
                  4.0f * directionY + 2.0f * lateralY },
                { 4.0f * directionX - 2.0f * lateralX,
                  4.0f * directionY - 2.0f * lateralY },
                { 6.0f * directionX, 6.0f * directionY }
            }};
            for (auto const& offset : offsets)
            {
                float const candidateX = groundX + offset.first;
                float const candidateY = groundY + offset.second;
                float candidateZ = groundAnchor->GetPositionZ();
                if (!resolveFloor(candidateX, candidateY, groundZ, candidateZ)
                    || !bot->IsWithinLOS(candidateX, candidateY, candidateZ,
                        LINEOFSIGHT_ALL_CHECKS, VMAP::ModelIgnoreFlags::M2))
                    continue;
                groundX = candidateX;
                groundY = candidateY;
                groundZ = candidateZ;
                break;
            }
        }
    }
    action.HasGroundTarget = true;
    action.GroundTargetX = groundX;
    action.GroundTargetY = groundY;
    action.GroundTargetZ = groundZ;
}
}
