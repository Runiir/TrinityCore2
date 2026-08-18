#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/BotClassSpecActionProfile.h"

#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "ObjectAccessor.h"
#include "PathGenerator.h"
#include "Player.h"
#include "SpellInfo.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <string>
#include <vector>

using BotWorldPopulationMgrNativeHelpers::Distance2d;
using BotWorldPopulationMgrSpellSemantics::NowMs;

bool BotWorldPopulationMgr::TryValidationRouteFeralHazardHealerRoar(WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, std::string& situation,
    std::string& action)
{
            BotClassSpecActionProfile hazardProfile = BotClassSpecActionProfileStore::Build(
                bot, GetDungeonRole(bot));
            if (hazardProfile.SpecTag != "feral_druid_tank"
                || !bot->IsInCombat() || !bot->HasSpell(99))
                return false;

            Unit* nearbyHealerOwnedAttacker = nullptr;
            uint32 nearbyHealerOwnedCount = 0;
            float nearestDistance = std::numeric_limits<float>::max();
            uint32 nearestGuid = std::numeric_limits<uint32>::max();
            std::vector<WorldObject*> objects;
            Trinity::AllWorldObjectsInRange check(bot, 45.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(
                bot, objects, check);
            Cell::VisitAllObjects(bot, searcher, 45.0f);
            for (WorldObject* object : objects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                Player* victim = creature && creature->GetVictim()
                    ? creature->GetVictim()->ToPlayer() : nullptr;
                if (!creature || !creature->IsAlive() || !creature->GetHealth()
                    || !bot->IsValidAttackTarget(creature) || !victim
                    || GetDungeonRole(victim) != "healer"
                    || (bot->GetGroup() ? victim->GetGroup() != bot->GetGroup()
                                        : victim != bot)
                    || bot->GetExactDist2d(creature) > 10.0f)
                    continue;

                ++nearbyHealerOwnedCount;
                float distance = bot->GetExactDist(creature);
                uint32 guid = creature->GetGUID().GetCounter();
                if (!nearbyHealerOwnedAttacker || distance < nearestDistance
                    || (distance == nearestDistance && guid < nearestGuid))
                {
                    nearbyHealerOwnedAttacker = creature;
                    nearestDistance = distance;
                    nearestGuid = guid;
                }
            }
            if (nearbyHealerOwnedCount < 2
                || !TryCastFriendlySpell(bot, bot, 99))
                return false;

            // Rerun101 proved the native in-flight Roar immediately recovers
            // an exposed strict-hazard wave, but rerun133 still sampled six
            // healer-owned identities 503 ms after a Roar submitted at 2528 ms,
            // crossing the dwell ceiling by 31 ms. Preserve the accepted exit
            // path and observe only this active pickup at 250 ms cadence.
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);

            std::string raw = BuildRawJson(bot, nearbyHealerOwnedAttacker);
            std::string semantic = BuildSemanticJson(
                bot, nearbyHealerOwnedAttacker, "validation_route_mechanic",
                &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup",
                nearbyHealerOwnedAttacker,
                "feral_in_flight_hazard_healer_roar",
                raw.c_str(), semantic.c_str(),
                float(nearbyHealerOwnedCount),
                Cohort().Config.ValidationRouteTargetEntry, 99);
            state.TargetGuid = nearbyHealerOwnedAttacker
                ? nearbyHealerOwnedAttacker->GetGUID() : ObjectGuid::Empty;
            state.WasInCombat = true;
            situation = "validation_route_mechanic";
            action = "feral_in_flight_hazard_healer_roar";
            return true;
}
bool BotWorldPopulationMgr::TryValidationRouteFeralHazardLooseTaunt(WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, std::string& situation,
    std::string& action)
{
            BotClassSpecActionProfile hazardProfile = BotClassSpecActionProfileStore::Build(
                bot, GetDungeonRole(bot));
            if (hazardProfile.SpecTag != "feral_druid_tank"
                || !bot->IsInCombat() || !bot->HasSpell(6795))
                return false;

            Creature* looseAttacker = nullptr;
            uint8 bestPriority = 0;
            float bestDistance = std::numeric_limits<float>::max();
            uint32 bestGuid = std::numeric_limits<uint32>::max();
            std::vector<WorldObject*> objects;
            Trinity::AllWorldObjectsInRange check(bot, 45.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
            Cell::VisitAllObjects(bot, searcher, 45.0f);
            for (WorldObject* object : objects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                Player* victim = creature && creature->GetVictim()
                    ? creature->GetVictim()->ToPlayer() : nullptr;
                if (!creature || !creature->IsAlive() || !creature->GetHealth()
                    || !bot->IsValidAttackTarget(creature) || !victim
                    || (bot->GetGroup() ? victim->GetGroup() != bot->GetGroup() : victim != bot))
                    continue;

                std::string victimRole = GetDungeonRole(victim);
                if (victimRole == "tank")
                    continue;
                // Boss-add encounters can activate an overlapping healer wave
                // inside Growl's cooldown. Rerun76 spent Growl on a DPS
                // attacker while healer exposure was zero, then could not
                // taunt the following Azil wave until its dwell gate had
                // already expired. Trash hazards retain generalized party
                // pickup; declared boss-add nodes reserve Growl for the healer.
                bool declaredBossAddEncounter =
                    Cohort().Config.ValidationRouteKind == "boss"
                    && !Cohort().Config.ValidationRouteAddTargetEntries.empty()
                    && Cohort().Config.ValidationRouteMechanicProfile.find("adds")
                        != std::string::npos;
                if (declaredBossAddEncounter && victimRole != "healer")
                    continue;
                uint8 priority = victimRole == "healer" ? 2 : 1;
                float distance = bot->GetExactDist(creature);
                uint32 guid = creature->GetGUID().GetCounter();
                if (!looseAttacker || priority > bestPriority
                    || (priority == bestPriority && (distance < bestDistance
                        || (distance == bestDistance && guid < bestGuid))))
                {
                    looseAttacker = creature;
                    bestPriority = priority;
                    bestDistance = distance;
                    bestGuid = guid;
                }
            }
            if (!looseAttacker || !TryCastCombatSpell(bot, looseAttacker, 6795))
                return false;

            Player* victim = looseAttacker->GetVictim()
                ? looseAttacker->GetVictim()->ToPlayer() : nullptr;
            bool healerVictim = GetDungeonRole(victim) == "healer";
            if (healerVictim)
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
            std::string raw = BuildRawJson(bot, looseAttacker);
            std::string semantic = BuildSemanticJson(
                bot, looseAttacker, "validation_route_mechanic", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup", looseAttacker,
                healerVictim
                    ? "feral_in_flight_hazard_healer_growl"
                    : "feral_in_flight_hazard_party_growl",
                raw.c_str(), semantic.c_str(),
                bestDistance, Cohort().Config.ValidationRouteTargetEntry, 6795);
            state.TargetGuid = looseAttacker->GetGUID();
            state.WasInCombat = true;
            situation = "validation_route_mechanic";
            action = healerVictim
                ? "feral_in_flight_hazard_healer_growl"
                : "feral_in_flight_hazard_party_growl";
            return true;
}

bool BotWorldPopulationMgr::TryValidationRouteHealerHazardFade(WorldBotState& state, Player* bot, Unit* preferredTarget,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, std::string& situation,
    std::string& action)
{
            if (std::string(GetDungeonRole(bot)) != "healer"
                || !bot->IsInCombat() || !bot->HasSpell(586)
                || bot->HasAura(586))
                return false;

            size_t healerTargetingHostileCount = 0;
            std::vector<WorldObject*> objects;
            Trinity::AllWorldObjectsInRange check(bot, 45.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(
                bot, objects, check);
            Cell::VisitAllObjects(bot, searcher, 45.0f);
            for (WorldObject* object : objects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                if (creature && creature->IsAlive() && creature->GetHealth()
                    && bot->IsValidAttackTarget(creature)
                    && creature->GetVictim() == bot)
                    ++healerTargetingHostileCount;
            }
            // Rerun114 passed Feral all-hostile retention, but Fade was spent
            // on a transient two-hostile transfer that cleared by the next
            // sample. It was then unavailable for the ten-hostile Flayer
            // hazard transfer responsible for the entire 8.120-second dwell
            // failure. Rerun116 then showed a three-attacker precursor still
            // consuming Fade before a 20-hostile Flayer transfer. Reserve the
            // existing native threat drop for nine or more exact-party
            // attackers. Rerun117 proved the precursor peaks at eight while
            // the sustained follow-up reaches eleven inside acquisition grace.
            // Hazard geometry remains unchanged.
            if (healerTargetingHostileCount < 9
                || !TryCastFriendlySpell(bot, bot, 586))
                return false;

            std::string raw = BuildRawJson(bot, preferredTarget);
            std::string semantic = BuildSemanticJson(
                bot, preferredTarget, "validation_route_mechanic",
                &power, stage, activity);
            RecordEvent(state, bot, "healer_assignment", bot,
                "fade_in_flight_hazard_threat_drop",
                raw.c_str(), semantic.c_str(),
                float(healerTargetingHostileCount),
                Cohort().Config.ValidationRouteTargetEntry, 586);
            situation = "validation_route_mechanic";
            action = "fade_in_flight_hazard_threat_drop";
            state.WasInCombat = true;
            return true;
}

bool BotWorldPopulationMgr::TryValidationRouteTankHazardHoldAreaThreat(WorldBotState& state, Player* bot, Unit* activeHazard,
    float safeRadius, bool radialHazard, bool allowMovement,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, std::string& situation,
    std::string& action)
{
            if (std::string(GetDungeonRole(bot)) != "tank" || !bot->IsInCombat())
                return false;

            std::vector<WorldObject*> objects;
            Trinity::AllWorldObjectsInRange check(bot, 45.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
            Cell::VisitAllObjects(bot, searcher, 45.0f);
            std::vector<Creature*> engagedHostiles;
            for (WorldObject* object : objects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                if (!creature || !creature->IsAlive() || !creature->GetHealth()
                    || !bot->IsValidAttackTarget(creature) || (!creature->IsInCombat() && !creature->GetVictim()))
                    continue;
                Player* victim = creature->GetVictim() ? creature->GetVictim()->ToPlayer() : nullptr;
                if (!victim || (bot->GetGroup() ? victim->GetGroup() != bot->GetGroup() : victim != bot))
                    continue;
                engagedHostiles.push_back(creature);
            }
            uint32 engagedCount = engagedHostiles.size();
            if (engagedCount < 2)
                return false;

            // Rerun86 showed the generic hazard area resolver selecting Thrash
            // while a local healer-owned cluster remained exposed for 8.061
            // seconds. Prefer the existing native self-centered Roar when at
            // least two such hostiles are already inside its exact ten-yard
            // radius. This does not alter the accepted hazard path.
            if (TryValidationRouteFeralHazardHealerRoar(state, bot, power, stage, activity, situation, action))
                return true;

            // Growl remains the instant single-target fallback and does not
            // replace the accepted hazard path or the area-threat resolver
            // below. Rerun75 showed non-healer party attackers can otherwise
            // remain loose through an entire safe-side hold.
            TryValidationRouteFeralHazardLooseTaunt(state, bot, power, stage, activity, situation, action);

            // A nearest hostile can sit on the safe-side edge while most of a
            // newly activated wave remains around the healer. Select the densest
            // exact-party cluster first, preserving victim-role priority and
            // deterministic distance/GUID tie-breaks.
            Unit* areaTarget = nullptr;
            uint8 areaPriority = 0;
            uint32 areaClusterCount = 0;
            float areaDistance = std::numeric_limits<float>::max();
            uint32 areaGuid = std::numeric_limits<uint32>::max();
            for (Creature* creature : engagedHostiles)
            {
                Player* victim = creature->GetVictim() ? creature->GetVictim()->ToPlayer() : nullptr;
                std::string victimRole = GetDungeonRole(victim);
                uint8 priority = victimRole == "healer" ? 3 : (victimRole == "tank" ? 1 : 2);
                uint32 clusterCount = 0;
                for (Creature* neighbor : engagedHostiles)
                    if (creature->GetExactDist2d(neighbor) <= 10.0f)
                        ++clusterCount;
                float distance = bot->GetExactDist(creature);
                uint32 guid = creature->GetGUID().GetCounter();
                if (!areaTarget || priority > areaPriority
                    || (priority == areaPriority && clusterCount > areaClusterCount)
                    || (priority == areaPriority && clusterCount == areaClusterCount
                        && (distance < areaDistance
                            || (distance == areaDistance && guid < areaGuid))))
                {
                    areaTarget = creature;
                    areaPriority = priority;
                    areaClusterCount = clusterCount;
                    areaDistance = distance;
                    areaGuid = guid;
                }
            }

            BotClassSpecActionProfile hazardProfile = BotClassSpecActionProfileStore::Build(
                bot, GetDungeonRole(bot));
            // Rerun173's only over-ceiling dwell began when an Azil follower
            // selected the healer after Hammer of the Righteous had landed on
            // a different add. The accepted radial hazard exit then returned
            // before Protection's ordinary single-target rescue for 4032 ms.
            // Hand of Reckoning is instant and does not replace or clear that
            // movement. Try it only against the deterministic healer-priority
            // hostile; failures preserve the area-threat and safe-path chain.
            // Rerun187 then presented two new healer-owned hostiles together.
            // The single taunt acquired one, but its cooldown left the second
            // behind while this hazard hold preempted ordinary Righteous
            // Defense for 3573 ms. Keep the single taunt first, then use the
            // existing native multi-attacker rescue on the healer before the
            // bounded safe-side hold. All native spell gates remain unchanged.
            if (hazardProfile.SpecTag == "protection"
                && bot->getClass() == CLASS_PALADIN
                && areaPriority == 3 && areaTarget)
            {
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                if (bot->HasSpell(62124)
                    && TryCastCombatSpell(bot, areaTarget, 62124))
                {
                    std::string raw = BuildRawJson(bot, areaTarget);
                    std::string semantic = BuildSemanticJson(
                        bot, areaTarget, "validation_route_mechanic",
                        &power, stage, activity);
                    RecordEvent(state, bot,
                        "validation_route_threat_pickup", areaTarget,
                        "hand_of_reckoning_hazard_healer_pickup",
                        raw.c_str(), semantic.c_str(), areaDistance,
                        Cohort().Config.ValidationRouteTargetEntry, 62124);
                    state.TargetGuid = areaTarget->GetGUID();
                    state.WasInCombat = true;
                    situation = "validation_route_mechanic";
                    action = "hand_of_reckoning_hazard_healer_pickup";
                    return true;
                }
                Player* hazardHealer = areaTarget->GetVictim()
                    ? areaTarget->GetVictim()->ToPlayer() : nullptr;
                if (hazardHealer
                    && GetDungeonRole(hazardHealer) == "healer"
                    && bot->HasSpell(31789)
                    && TryCastFriendlySpell(bot, hazardHealer, 31789))
                {
                    std::string raw = BuildRawJson(bot, hazardHealer);
                    std::string semantic = BuildSemanticJson(
                        bot, hazardHealer, "validation_route_mechanic",
                        &power, stage, activity);
                    RecordEvent(state, bot,
                        "validation_route_threat_pickup", hazardHealer,
                        "righteous_defense_hazard_healer_pickup",
                        raw.c_str(), semantic.c_str(), areaDistance,
                        Cohort().Config.ValidationRouteTargetEntry, 31789);
                    state.TargetGuid = areaTarget->GetGUID();
                    state.WasInCombat = true;
                    situation = "validation_route_mechanic";
                    action = "righteous_defense_hazard_healer_pickup";
                    return true;
                }
            }
            auto tryFeralHazardThrashRetention = [&]() -> bool
            {
                // Rerun159 localized all Feral healer exposure to a fully
                // tank-owned 53-hostile wave that lost ten identities during
                // strict hazard movement immediately after native Swipe. Try
                // the known persistent native area spell before movement; if
                // any native legality gate rejects it, preserve the existing
                // Charge, safe path, profile resolver, and Swipe fallbacks.
                if (hazardProfile.SpecTag != "feral_druid_tank"
                    || engagedCount < 12 || !areaTarget
                    || !bot->HasSpell(77758)
                    || !TryCastCombatSpell(bot, areaTarget, 77758))
                    return false;

                std::string raw = BuildRawJson(bot, areaTarget);
                std::string semantic = BuildSemanticJson(
                    bot, areaTarget, "validation_route_mechanic",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    areaTarget, "feral_thrash_hazard_secure_threat_retention",
                    raw.c_str(), semantic.c_str(), float(engagedCount),
                    Cohort().Config.ValidationRouteTargetEntry, 77758);
                state.TargetGuid = areaTarget->GetGUID();
                state.WasInCombat = true;
                situation = "validation_route_mechanic";
                action = "feral_thrash_hazard_secure_threat_retention";
                return true;
            };
            auto tryFeralHazardSwipeMargin = [&]() -> bool
            {
                if (hazardProfile.SpecTag != "feral_druid_tank"
                    || engagedCount < 12 || !bot->HasSpell(779))
                    return false;

                Creature* swipeTarget = nullptr;
                float swipeDistance = std::numeric_limits<float>::max();
                uint32 swipeGuid = std::numeric_limits<uint32>::max();
                for (Creature* creature : engagedHostiles)
                {
                    float distance = bot->GetExactDist(creature);
                    uint32 guid = creature->GetGUID().GetCounter();
                    if (!swipeTarget || distance < swipeDistance
                        || (distance == swipeDistance && guid < swipeGuid))
                    {
                        swipeTarget = creature;
                        swipeDistance = distance;
                        swipeGuid = guid;
                    }
                }
                if (!swipeTarget
                    || !TryCastCombatSpell(bot, swipeTarget, 779))
                    return false;

                std::string raw = BuildRawJson(bot, swipeTarget);
                std::string semantic = BuildSemanticJson(
                    bot, swipeTarget, "validation_route_mechanic",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    swipeTarget, "feral_swipe_hazard_secure_threat_margin",
                    raw.c_str(), semantic.c_str(), float(engagedCount),
                    Cohort().Config.ValidationRouteTargetEntry, 779);
                state.TargetGuid = swipeTarget->GetGUID();
                state.WasInCombat = true;
                situation = "validation_route_mechanic";
                action = "feral_swipe_hazard_secure_threat_margin";
                return true;
            };
            // The safe-side movement branch below already uses the lower
            // cadence, but rerun133's accepted in-flight path returned through
            // Roar, Growl, area threat, or the bounded hold before reaching it.
            // Observe the deterministic healer-owned target at 250 ms cadence;
            // spell and movement legality remain unchanged.
            if (hazardProfile.SpecTag == "feral_druid_tank"
                && areaPriority == 3)
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
            if (tryFeralHazardThrashRetention())
                return true;
            auto radialChargePathSafe = [&](Unit* chargeTarget) -> bool
            {
                if (!chargeTarget || !radialHazard || !activeHazard || safeRadius <= 0.0f)
                    return false;
                float fromX = bot->GetPositionX();
                float fromY = bot->GetPositionY();
                float toX = chargeTarget->GetPositionX();
                float toY = chargeTarget->GetPositionY();
                float deltaX = toX - fromX;
                float deltaY = toY - fromY;
                float segmentLengthSq = deltaX * deltaX + deltaY * deltaY;
                float projection = 0.0f;
                if (segmentLengthSq > 0.01f)
                    projection = std::clamp(
                        ((activeHazard->GetPositionX() - fromX) * deltaX
                            + (activeHazard->GetPositionY() - fromY) * deltaY)
                            / segmentLengthSq,
                        0.0f, 1.0f);
                float closestX = fromX + projection * deltaX;
                float closestY = fromY + projection * deltaY;
                return Distance2d(
                    closestX, closestY,
                    activeHazard->GetPositionX(), activeHazard->GetPositionY())
                    > safeRadius + 0.5f;
            };
            auto radialGroundPathSafe = [&](Unit* movementTarget) -> bool
            {
                if (!movementTarget || !radialHazard || !activeHazard
                    || safeRadius <= 0.0f)
                    return false;

                PathGenerator path(bot);
                if (!path.CalculatePath(
                        movementTarget->GetPositionX(),
                        movementTarget->GetPositionY(),
                        movementTarget->GetPositionZ(), false))
                    return false;
                PathType pathType = path.GetPathType();
                if ((pathType & PATHFIND_NOPATH)
                    || (pathType & PATHFIND_NOT_USING_PATH)
                    || (pathType & PATHFIND_INCOMPLETE)
                    || (pathType & PATHFIND_SHORTCUT)
                    || (pathType & PATHFIND_FARFROMPOLY))
                    return false;

                for (G3D::Vector3 const& point : path.GetPath())
                    if (Distance2d(
                            point.x, point.y,
                            activeHazard->GetPositionX(),
                            activeHazard->GetPositionY())
                        <= safeRadius + 0.5f)
                        return false;
                return true;
            };

            Unit* chargeTarget = nullptr;
            uint8 chargePriority = 0;
            uint32 chargeClusterCount = 0;
            float chargeDistance = std::numeric_limits<float>::max();
            uint32 chargeGuid = std::numeric_limits<uint32>::max();
            if (hazardProfile.SpecTag == "feral_druid_tank" && engagedCount >= 3)
                for (Creature* creature : engagedHostiles)
                {
                    float distance = bot->GetExactDist(creature);
                    if (distance <= 8.0f || !radialChargePathSafe(creature))
                        continue;
                    Player* victim = creature->GetVictim() ? creature->GetVictim()->ToPlayer() : nullptr;
                    std::string victimRole = GetDungeonRole(victim);
                    uint8 priority = victimRole == "healer" ? 3 : (victimRole == "tank" ? 1 : 2);
                    uint32 clusterCount = 0;
                    for (Creature* neighbor : engagedHostiles)
                        if (creature->GetExactDist2d(neighbor) <= 10.0f)
                            ++clusterCount;
                    uint32 guid = creature->GetGUID().GetCounter();
                    if (!chargeTarget || priority > chargePriority
                        || (priority == chargePriority && clusterCount > chargeClusterCount)
                        || (priority == chargePriority && clusterCount == chargeClusterCount
                            && (distance < chargeDistance
                                || (distance == chargeDistance && guid < chargeGuid))))
                    {
                        chargeTarget = creature;
                        chargePriority = priority;
                        chargeClusterCount = clusterCount;
                        chargeDistance = distance;
                        chargeGuid = guid;
                    }
                }

            if (allowMovement && chargeTarget && bot->HasSpell(16979)
                && TryCastCombatSpell(bot, chargeTarget, 16979))
            {
                std::string raw = BuildRawJson(bot, chargeTarget);
                std::string semantic = BuildSemanticJson(
                    bot, chargeTarget, "validation_route_mechanic", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup", chargeTarget,
                    "feral_charge_safe_hazard_swarm_pickup", raw.c_str(), semantic.c_str(),
                    float(engagedCount), Cohort().Config.ValidationRouteTargetEntry, 16979);
                state.FeralChargePickupTargetGuid = chargeTarget->GetGUID();
                state.FeralChargePickupUntilMs = NowMs() + 2500;
                state.TargetGuid = chargeTarget->GetGUID();
                state.WasInCombat = true;
                situation = "validation_route_mechanic";
                action = "feral_charge_safe_hazard_swarm_pickup";
                return true;
            }

            // A ready Charge is the fastest safe-side pickup, but its native
            // cooldown must not pin Feral outside the hazard for the entire
            // acquisition window. Reuse the unchanged radial safety margin
            // against every point in the strict mmap path before allowing
            // ordinary ground movement toward the selected hostile cluster.
            // Unsafe or incomplete paths still fall through to the bounded
            // safe-side hold.
            if (allowMovement
                && hazardProfile.SpecTag == "feral_druid_tank"
                && areaTarget
                && bot->GetExactDist2d(areaTarget) > 10.0f
                && radialGroundPathSafe(areaTarget))
            {
                bool moved = MoveBotToProfileRange(
                    state, bot, areaTarget);
                if (moved)
                {
                    // Rerun98's only generation-13 dwell failure spent four
                    // one-second decisions on this already-accepted safe path
                    // before native Roar became legal (4032 ms total). Rerun133
                    // then missed the strict ceiling by 31 ms after a legal
                    // hazard Roar. Keep hazard movement authoritative, but
                    // observe this active healer-owned pickup at 250 ms cadence.
                    if (areaPriority == 3)
                        state.DecisionTimer = std::min<uint32>(
                            state.DecisionTimer, 250);
                    std::string raw = BuildRawJson(bot, areaTarget);
                    std::string semantic = BuildSemanticJson(
                        bot, areaTarget, "validation_route_mechanic",
                        &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_threat_pickup",
                        areaTarget, "feral_move_safe_side_hazard_swarm_pickup",
                        raw.c_str(), semantic.c_str(),
                        bot->GetExactDist2d(areaTarget),
                        Cohort().Config.ValidationRouteTargetEntry);
                    state.TargetGuid = areaTarget->GetGUID();
                    situation = "validation_route_mechanic";
                    action = "feral_move_safe_side_hazard_swarm_pickup";
                    return true;
                }
            }

            ResolvedCombatAction areaThreat = ResolveProfileCombatAction(
                bot, areaTarget, engagedCount, true, 0, true);
            if (!areaThreat.Valid)
                return tryFeralHazardSwipeMargin();
            if (areaThreat.TargetGuid == bot->GetGUID())
            {
                uint32 nearbyEngagedCount = 0;
                for (Creature* creature : engagedHostiles)
                    if (creature && bot->GetExactDist2d(creature) <= 10.0f)
                        ++nearbyEngagedCount;
                if (nearbyEngagedCount < 2)
                    return tryFeralHazardSwipeMargin();
            }
            BotActionResult areaResult = ExecuteProfileCombatAction(
                &state, bot, areaTarget, &areaThreat, engagedCount, true, 0, true);
            if (areaResult != BotActionResult::Ok)
                return tryFeralHazardSwipeMargin();

            std::string raw = BuildRawJson(bot, areaTarget);
            std::string semantic = BuildSemanticJson(
                bot, areaTarget, "validation_route_mechanic", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup", areaTarget,
                "tank_hazard_hold_aoe_threat", raw.c_str(), semantic.c_str(),
                float(engagedCount), Cohort().Config.ValidationRouteTargetEntry, areaThreat.SpellId);
            state.TargetGuid = areaTarget->GetGUID();
            state.WasInCombat = true;
            situation = "validation_route_mechanic";
            action = "tank_hazard_hold_aoe_threat";
            return true;
}
