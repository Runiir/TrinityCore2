#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBalanceMushroomDuty.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotTypes.h"
#include "Creature.h"
#include "Map.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

#include <algorithm>
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
    bool const livePillarVisible = bot
        && bot->FindNearestCreature(
            MagmawBalanceMushroomDuty::PillarOfFlameEntry, 60.0f, true);
    state.LivePillarVisible = livePillarVisible;
    state.Active = MagmawBalanceMushroomDuty::IsActive(
        validationRouteEnabled, routeNodeId, specTag, targetEntry,
        livePillarVisible);
    state.SolarEclipse = solarEclipse;
    state.OwnedMushrooms = state.Active ? OwnedWildMushroomCount(bot) : 0;
    return state;
}

bool IsMagmawBalanceMushroomPlacement(
    MagmawBalanceMushroomState const& state, BotActionCandidate const& candidate)
{
    return state.Active
        && state.LivePillarVisible
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

bool SetMagmawBalanceMushroomGroundTarget(
    ResolvedCombatAction& action, Player const* bot, Unit const* target)
{
    if (!bot || !target)
        return false;

    // Aim at the live Pillar of Flame's X/Y and let the map resolve the
    // platform floor. The pillar is the encounter's ground marker; the
    // parasites are airborne and moving targets, so they are not destination
    // coordinates for a player-placed mushroom.
    Creature const* pillar = target->FindNearestCreature(
        MagmawBalanceMushroomDuty::PillarOfFlameEntry, 20.0f, true);
    if (!pillar)
        return false;

    Map* map = pillar->GetMap();
    if (!map)
        return false;

    float const groundX = pillar->GetPositionX();
    float const groundY = pillar->GetPositionY();
    float const groundZ = map->GetHeight(bot->GetPhaseShift(), groundX, groundY,
        pillar->GetPositionZ() + 2.0f, true, 64.0f);
    if (groundZ == INVALID_HEIGHT)
        return false;

    action.HasGroundTarget = true;
    action.GroundTargetX = groundX;
    action.GroundTargetY = groundY;
    action.GroundTargetZ = groundZ;
    return true;
}
}
