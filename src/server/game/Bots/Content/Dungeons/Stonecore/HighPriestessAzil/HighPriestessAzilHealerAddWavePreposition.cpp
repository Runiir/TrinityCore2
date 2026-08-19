#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilHealerAddWavePreposition.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"

#include "CellImpl.h"
#include "Creature.h"
#include "Entities/Object/Position.h"
#include "GridNotifiersImpl.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"
#include "WorldObject.h"

#include <algorithm>
#include <string>
#include <vector>

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

bool Context::Run(
    HealerAddWavePrepositionRequest const& request)
{
    BotWorldPopulationMgr& manager = *request.Manager;
    BotWorldPopulationMgrBotState::WorldBotState& state = *request.State;
    Player* bot = request.Bot;
    BotRolePowerBreakdown const& power = *request.Power;
    std::string& situation = *request.Situation;
    std::string& action = *request.Action;
    Unit*& target = *request.Target;

    if (std::string(manager.GetDungeonRole(bot)) != "healer"
        || manager.Party().ValidationRouteBossProgressTargetGuid.IsEmpty())
        return false;

    Unit* routeBoss = ObjectAccessor::GetUnit(
        *bot, manager.Party().ValidationRouteBossProgressTargetGuid);
    Player* routeTank = nullptr;
    for (BotWorldPopulationMgrBotState::WorldBotState const& cohortState
        : manager.Party().Bots)
    {
        Player* member = manager.GetLoadedBot(cohortState);
        if (member && member->IsAlive() && member->GetMap() == bot->GetMap()
            && std::string(manager.GetDungeonRole(member)) == "tank")
        {
            routeTank = member;
            break;
        }
    }

    if (!routeBoss || !routeBoss->IsAlive() || !routeBoss->IsInCombat()
        || !routeTank || !routeTank->IsInCombat()
        || bot->GetExactDist2d(routeTank) <= 5.0f
        || bot->HasUnitState(UNIT_STATE_CASTING) || bot->IsFalling())
        return false;

    // Rerun122 proved the native attacker container can lag the explicit
    // listed-victim view during an Azil activation: the authoritative trace
    // observed nineteen followers targeting the healer while this early branch
    // kept classifying the pickup as non-urgent and preempted the later Fade
    // resolver. Reconstruct the same bounded 45-yard listed-add view here so
    // preposition and threat-drop decisions agree with the add resolver and
    // identity-scoped retention evidence.
    size_t explicitListedHealerAttackers = 0;
    std::vector<WorldObject*> pickupObjects;
    Trinity::AllWorldObjectsInRange pickupCheck(bot, 45.0f);
    Trinity::WorldObjectListSearcher<
        Trinity::AllWorldObjectsInRange> pickupSearcher(
            bot, pickupObjects, pickupCheck);
    Cell::VisitAllObjects(bot, pickupSearcher, 45.0f);
    for (WorldObject* object : pickupObjects)
    {
        Creature* creature = object ? object->ToCreature() : nullptr;
        if (!creature || !creature->IsAlive() || !creature->GetHealth()
            || creature->GetMap() != bot->GetMap()
            || creature->GetVictim() != bot
            || !bot->IsValidAttackTarget(creature)
            || !bot->IsWithinLOSInMap(creature)
            || std::find(
                manager.Cohort().Config.ValidationRouteAddTargetEntries.begin(),
                manager.Cohort().Config.ValidationRouteAddTargetEntries.end(),
                creature->GetEntry())
                == manager.Cohort().Config.ValidationRouteAddTargetEntries.end())
            continue;
        ++explicitListedHealerAttackers;
    }
    size_t observedHealerAttackers = std::max(
        bot->getAttackers().size(), explicitListedHealerAttackers);
    // Rerun71 showed the healer repeatedly selecting ordinary group heals while
    // 15+ followers retained it and the Feral crossed the platform. Preserve
    // emergency healing, but when both healer and tank have safe health, begin
    // the existing bounded stack movement before another heal can keep the
    // remote swarm split from the tank.
    bool urgentPickupStack = observedHealerAttackers >= 3
        && UnitHealthPct(bot) > 0.45f
        && UnitHealthPct(routeTank) > 0.40f;
    // Rerun115 showed this early preposition branch returning for seven seconds
    // while 9--20 Azil followers targeted the healer. It precedes the general
    // boss-wave Fade resolver, so submit the same ready native threat drop
    // before movement when the urgent exact-attacker gate is already satisfied.
    if (urgentPickupStack && bot->HasSpell(586)
        && !bot->HasAura(586))
    {
        std::string fadeFailureReason;
        if (manager.TryCastFriendlySpell(
                bot, bot, 586, &fadeFailureReason))
        {
            std::string raw = manager.BuildRawJson(bot, routeBoss);
            std::string semantic = manager.BuildSemanticJson(
                bot, routeBoss, "dungeon_boss", &power,
                request.Stage, request.Activity);
            manager.RecordEvent(state, bot, "boss_adds", bot,
                "fade_before_urgent_add_pickup_preposition",
                raw.c_str(), semantic.c_str(),
                float(observedHealerAttackers),
                manager.Cohort().Config.ValidationRouteTargetEntry, 586);
            state.TargetGuid = routeBoss->GetGUID();
            target = routeBoss;
            situation = "dungeon_boss";
            action = "fade_before_urgent_add_pickup_preposition";
            return true;
        }
        // The first rerun122 attempt occurred one second after a legal instant
        // heal. Keep movement bounded and retry only that GCD-blocked urgent
        // Fade at the established lower decision cadence; native cooldown
        // failures do not pin healer movement or healing.
        if (fadeFailureReason == "global_cooldown")
            state.DecisionTimer = std::min<uint32>(state.DecisionTimer, 500);
    }
    if (!urgentPickupStack && request.TryRouteGroupHeal(bot, routeBoss))
        return true;

    Position pickup = routeTank->GetFirstCollisionPosition(4.0f,
        routeBoss->GetAngle(routeTank) - routeTank->GetOrientation());
    if (manager.MoveBotToPoint(state, bot,
            pickup.GetPositionX(), pickup.GetPositionY(), pickup.GetPositionZ()))
    {
        std::string raw = manager.BuildRawJson(bot, routeBoss);
        std::string semantic = manager.BuildSemanticJson(
            bot, routeBoss, "dungeon_boss", &power,
            request.Stage, request.Activity);
        manager.RecordEvent(state, bot, "boss_adds", routeTank,
            "healer_preposition_for_add_pickup", raw.c_str(), semantic.c_str(),
            bot->GetExactDist2d(routeTank),
            manager.Cohort().Config.ValidationRouteTargetEntry);
        state.TargetGuid = routeBoss->GetGUID();
        target = routeBoss;
        situation = "dungeon_boss";
        action = "healer_preposition_for_add_pickup";
        return true;
    }
    return false;
}

bool TryHealerAddWavePreposition(
    HealerAddWavePrepositionRequest const& request)
{
    return Context::Run(request);
}
}
