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

    // Lava Parasites can still be airborne when the add wave appears.  Keep
    // their live X/Y so the mushrooms follow the wave, but resolve the target
    // onto the visible platform instead of casting at the airborne Z or the
    // elevated home point. This is the parasite's live floor position.
    float groundX = target->GetPositionX();
    float groundY = target->GetPositionY();
    float groundZ = target->GetPositionZ();
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
    // keep the point on the platform but move it toward the caster in small
    // steps. The detonation radius still covers the parasite wave.
    if (bot && !bot->IsWithinLOS(groundX, groundY, groundZ,
            LINEOFSIGHT_ALL_CHECKS, VMAP::ModelIgnoreFlags::M2))
    {
        float const towardX = bot->GetPositionX() - groundX;
        float const towardY = bot->GetPositionY() - groundY;
        float const towardLength = std::sqrt(towardX * towardX + towardY * towardY);
        if (towardLength > 0.01f)
        {
            for (float offset = 2.0f; offset <= 6.0f; offset += 2.0f)
            {
                float const candidateX = groundX + towardX / towardLength * offset;
                float const candidateY = groundY + towardY / towardLength * offset;
                float candidateZ = groundZ;
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
