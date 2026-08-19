#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilSwarmThreatSafety.h"

#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

#include <limits>
#include <string>

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
bool Context::Run(SwarmThreatSafetyRequest const& request)
{
    BotWorldPopulationMgr& manager = *request.Manager;
    BotWorldPopulationMgrBotState::WorldBotState& state = *request.State;
    Player* bot = request.Bot;
    BotRolePowerBreakdown const& power = *request.Power;
    BotProgressionStage stage = request.Stage;
    BotProgressionActivity activity = request.Activity;
    AddWaveDiscoveryResult const& discovery = *request.Discovery;
    AddWaveDensityResult const& density = *request.Density;
    HunterThreatTransferResult const& hunterThreatTransfer =
        *request.HunterThreatTransfer;
    Unit* add = request.Add;
    std::string& situation = *request.Situation;
    std::string& action = *request.Action;
    Unit*& target = *request.Target;
    uint32 addCount = discovery.AddCount;
    std::vector<Creature*> const& localAdds = discovery.LocalAdds;
    bool cohortSwarmActive = discovery.CohortSwarmActive;
    std::string const& role = density.Role;
    Player* densityTank = density.DensityTank;
    Player* densityHealer = density.DensityHealer;
    bool dpsSwarmDamageRelease = density.DpsSwarmDamageRelease;
    bool botInsideTankPickup = density.BotInsideTankPickup;
    std::function<size_t(Player const*)> const& observedListedAttackerCount =
        density.ObservedListedAttackerCount;
    bool hunterMisdirectionActive =
        hunterThreatTransfer.HunterMisdirectionActive;

    // Azil can activate an entire follower wave on one damage dealer in a
    // single server tick. The tank normally owns the wave on its next
    // decision, but that interval is enough to kill a cloth or mail DPS.
    // Use each spec's native emergency defensive immediately while normal
    // tank pickup completes; Enhancement needs the earlier threshold
    // because Shamanistic Rage mitigates rather than immunizes.
    size_t swarmDefensiveThreshold = bot->getClass() == CLASS_SHAMAN ? 3 : 5;
    uint32 swarmDefensiveSpellId = bot->getClass() == CLASS_MAGE ? 45438
        : (bot->getClass() == CLASS_HUNTER ? 19263
            : (bot->getClass() == CLASS_SHAMAN ? 30823 : 0));
    if (role == "dps" && cohortSwarmActive
        && observedListedAttackerCount(bot) >= swarmDefensiveThreshold
        && swarmDefensiveSpellId && bot->HasSpell(swarmDefensiveSpellId)
        && !bot->HasAura(swarmDefensiveSpellId)
        && manager.TryCastFriendlySpell(bot, bot, swarmDefensiveSpellId))
    {
        manager.SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Threat,
            BotActionArbitration::Priority::ThreatControl,
            "swarm_pickup_emergency_defensive");
        std::string raw = manager.BuildRawJson(bot, add);
        std::string semantic = manager.BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "defensive", bot, "swarm_pickup_emergency_defensive",
            raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(bot)), addCount,
            swarmDefensiveSpellId);
        state.TargetGuid = densityTank && densityTank->GetVictim()
            ? densityTank->GetVictim()->GetGUID() : (add ? add->GetGUID() : ObjectGuid::Empty);
        target = densityTank && densityTank->GetVictim() ? densityTank->GetVictim() : add;
        situation = "dungeon_boss";
        action = "swarm_pickup_emergency_defensive";
        return true;
    }

    // Do not let the first ranged AoE tick assign an entire newly spawned
    // swarm to a DPS before the tank can act.  Stack an unowned focus into
    // the pickup radius and suppress new threat until that focus transfers.
    if (role == "dps" && densityTank && cohortSwarmActive && add
        && !hunterMisdirectionActive
        && (!dpsSwarmDamageRelease
            || (observedListedAttackerCount(bot) && !botInsideTankPickup)))
    {
        manager.SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Threat,
            BotActionArbitration::Priority::ThreatControl,
            "dps_wait_for_swarm_tank_ownership");
        if (Pet* pet = bot->GetPet())
            pet->AttackStop();

        if (!bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
        {
            Position pickup = densityTank->GetFirstCollisionPosition(4.0f,
                add->GetAngle(densityTank) - densityTank->GetOrientation());
            if (bot->GetExactDist2d(pickup.GetPositionX(), pickup.GetPositionY()) > 2.0f
                && manager.MoveBotToPoint(state, bot, pickup.GetPositionX(), pickup.GetPositionY(), pickup.GetPositionZ()))
            {
                std::string raw = manager.BuildRawJson(bot, add);
                std::string semantic = manager.BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
                manager.RecordEvent(state, bot, "boss_adds", add, "dps_stack_for_swarm_pickup",
                    raw.c_str(), semantic.c_str(), bot->GetExactDist2d(densityTank), addCount);
                state.TargetGuid = densityTank->GetVictim() ? densityTank->GetVictim()->GetGUID() : add->GetGUID();
                target = densityTank->GetVictim() ? densityTank->GetVictim() : add;
                situation = "dungeon_boss";
                action = "dps_stack_for_swarm_pickup";
                return true;
            }
        }

        Unit* pickupFocus = densityTank->GetVictim() ? densityTank->GetVictim() : add;
        state.TargetGuid = pickupFocus ? pickupFocus->GetGUID() : ObjectGuid::Empty;
        target = pickupFocus;
        std::string raw = manager.BuildRawJson(bot, add);
        std::string semantic = manager.BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_adds", add, "dps_wait_for_swarm_tank_ownership",
            raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(bot)), addCount);
        situation = "dungeon_boss";
        action = "dps_wait_for_swarm_tank_ownership";
        return true;
    }

    if (role == "dps" && densityTank && !dpsSwarmDamageRelease && observedListedAttackerCount(bot)
        && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
    {
        Unit* nearestAttacker = nullptr;
        float nearestDistance = std::numeric_limits<float>::max();
        auto considerPickupAttacker = [&](Unit* attacker)
        {
            if (!attacker || !attacker->IsAlive() || attacker->GetMap() != bot->GetMap())
                return;
            float distance = bot->GetExactDist2d(attacker);
            if (!nearestAttacker || distance < nearestDistance)
            {
                nearestAttacker = attacker;
                nearestDistance = distance;
            }
        };
        for (Creature* candidate : localAdds)
            if (candidate && candidate->GetVictim() == bot)
                considerPickupAttacker(candidate);
        if (!nearestAttacker)
            for (Unit* attacker : bot->getAttackers())
                considerPickupAttacker(attacker);
        if (nearestAttacker)
        {
            Position pickup = densityTank->GetFirstCollisionPosition(4.0f,
                nearestAttacker->GetAngle(densityTank) - densityTank->GetOrientation());
            if (bot->GetExactDist2d(pickup.GetPositionX(), pickup.GetPositionY()) > 2.0f
                && manager.MoveBotToPoint(state, bot, pickup.GetPositionX(), pickup.GetPositionY(), pickup.GetPositionZ()))
            {
                manager.SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                    BotMeleeAutoAttack::Owner::Threat,
                    BotActionArbitration::Priority::ThreatControl,
                    "dps_stack_for_add_pickup");
                if (Pet* pet = bot->GetPet())
                    pet->AttackStop();
                std::string raw = manager.BuildRawJson(bot, nearestAttacker);
                std::string semantic = manager.BuildSemanticJson(bot, nearestAttacker, "dungeon_boss", &power, stage, activity);
                manager.RecordEvent(state, bot, "boss_adds", nearestAttacker, "dps_stack_for_add_pickup",
                    raw.c_str(), semantic.c_str(), nearestDistance, addCount);
                Unit* pickupFocus = densityTank->GetVictim() ? densityTank->GetVictim() : add;
                state.TargetGuid = pickupFocus ? pickupFocus->GetGUID() : ObjectGuid::Empty;
                target = pickupFocus;
                situation = "dungeon_boss";
                action = "dps_stack_for_add_pickup";
                return true;
            }
        }
    }

    // If the bot is already in pickup range, or its legal path to the tank
    // was rejected above, stop adding threat until ownership transfers.
    if (role == "dps" && densityTank && !dpsSwarmDamageRelease && observedListedAttackerCount(bot))
    {
        manager.SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Threat,
            BotActionArbitration::Priority::ThreatControl,
            "dps_hold_for_nearby_add_pickup");
        if (Pet* pet = bot->GetPet())
            pet->AttackStop();
        Unit* pickupFocus = densityTank->GetVictim() ? densityTank->GetVictim() : add;
        state.TargetGuid = pickupFocus ? pickupFocus->GetGUID() : ObjectGuid::Empty;
        target = pickupFocus;
        std::string raw = manager.BuildRawJson(bot, add);
        std::string semantic = manager.BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_adds", add, "dps_hold_for_nearby_add_pickup",
            raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(bot)), addCount);
        situation = "dungeon_boss";
        action = "dps_hold_for_nearby_add_pickup";
        return true;
    }

    if (role == "tank" && densityHealer
        && observedListedAttackerCount(densityHealer)
        && bot->HasSpell(1038) && !densityHealer->HasAura(1038)
        && manager.TryCastFriendlySpell(bot, densityHealer, 1038))
    {
        std::string raw = manager.BuildRawJson(bot, densityHealer);
        std::string semantic = manager.BuildSemanticJson(bot, densityHealer, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_adds", densityHealer, "hand_of_salvation_healer_threat_drop",
            raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(densityHealer)), addCount, 1038);
        target = add;
        situation = "dungeon_boss";
        action = "hand_of_salvation_healer_threat_drop";
        return true;
    }

    return false;
}

bool TrySwarmThreatSafety(
    SwarmThreatSafetyRequest const& request)
{
    return Context::Run(request);
}
}
