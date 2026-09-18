#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBalanceMushroomDuty.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotTypes.h"
#include "Creature.h"
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
    ResolvedCombatAction& action, Unit const* target, Creature const* targetCreature)
{
    if (!target)
        return;

    float groundX = target->GetPositionX();
    float groundY = target->GetPositionY();
    float groundZ = target->GetPositionZ();
    if (targetCreature && targetCreature->GetHomePosition().IsPositionValid())
    {
        groundX = targetCreature->GetHomePosition().GetPositionX();
        groundY = targetCreature->GetHomePosition().GetPositionY();
        groundZ = targetCreature->GetHomePosition().GetPositionZ();
    }
    action.HasGroundTarget = true;
    action.GroundTargetX = groundX;
    action.GroundTargetY = groundY;
    action.GroundTargetZ = groundZ;
}
}
