#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"

#include "Bots/BotRaidAreaAuthority.h"
#include "Creature.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "PathGenerator.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>
#include <set>
#include <string>
#include <vector>

using BotWorldPopulationMgrNativeHelpers::Distance2d;

bool BotWorldPopulationMgr::TryValidationRoutePatrolPull(
    WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, std::string& situation,
    std::string& action, Unit*& target,
    std::function<ObjectGuid::LowType()> const& currentValidationRouteTargetSpawnId,
    std::function<bool(Creature const*)> const& isValidationCohortCombatLinked,
    std::function<void(Creature const*, bool)> const& enrollValidationRoutePackMember)
{
        if (Cohort().Config.ValidationRoutePatrolPullPolicy.empty())
            return false;

        auto hold = [&](char const* result, Creature* source = nullptr) -> bool
        {
            BotRaidAreaAuthority::SetAllOffenseSuppressed(
                bot->GetGUID().GetRawValue(), true);
            state.TargetGuid.Clear();
            target = source;
            situation = "validation_route_patrol_pull";
            action = result;
            return true;
        };
        if (Cohort().Config.ValidationRoutePatrolPullPolicy
                != "ranged_patrol_to_anchor"
            || !Cohort().Config.ValidationRoutePatrolPullOwnerRosterSlot
            || Cohort().Config.ValidationRoutePatrolWaitToleranceYards <= 0.0f
            || Cohort().Config.ValidationRoutePatrolAnchorToleranceYards <= 0.0f
            || Cohort().Config.ValidationRoutePatrolEngageRadiusYards <= 0.0f
            || Cohort().Config.ValidationRoutePatrolFutureGuardMarginYards <= 0.0f
            || Cohort().Config.ValidationRouteClusterRadiusYards <= 0.0f)
        {
            state.LastNoProgressReason = "patrol_pull_contract_unresolved";
            return hold("validation_route_patrol_pull_contract_hold");
        }

        ObjectGuid::LowType const spawnId = currentValidationRouteTargetSpawnId();
        Creature* source = spawnId && bot->GetMap()
            ? bot->GetMap()->GetCreatureBySpawnId(spawnId) : nullptr;
        if (!source || !source->IsAlive() || !source->GetHealth()
            || source->GetMap() != bot->GetMap())
            return false;

        auto exactRosterAtAnchor = [this, bot]() -> bool
        {
            if (!bot || !bot->GetMap() || !Cohort().Config.TargetPopulation
                || Party().Bots.size() != Cohort().Config.TargetPopulation
                || Cohort().Raid.RosterByGuid.size()
                    != Cohort().Config.TargetPopulation)
                return false;
            std::set<uint32> seen;
            for (WorldBotState const& cohortState : Party().Bots)
            {
                Player* member = GetLoadedBot(cohortState);
                auto const roster = Cohort().Raid.RosterByGuid.find(
                    cohortState.Guid.GetCounter());
                if (!member || !member->IsInWorld() || !member->IsAlive()
                    || member->GetMap() != bot->GetMap()
                    || !IsValidationCohortMemberInOriginalInstance(
                        cohortState, member)
                    || roster == Cohort().Raid.RosterByGuid.end()
                    || !roster->second.Active || !roster->second.LeaseOwned
                    || !seen.insert(member->GetGUID().GetCounter()).second
                    || member->GetExactDist(
                        Cohort().Config.ValidationRouteX,
                        Cohort().Config.ValidationRouteY,
                        Cohort().Config.ValidationRouteZ)
                        > Cohort().Config.ValidationRoutePatrolAnchorToleranceYards)
                    return false;
            }
            return seen.size() == Cohort().Config.TargetPopulation;
        };
        auto sourcePathKeepsFutureEncountersSafe = [this, bot, source]() -> bool
        {
            if (!bot || !bot->GetMap() || !source
                || source->GetMap() != bot->GetMap())
                return false;
            PathGenerator path(source);
            bool const calculated = path.CalculatePath(
                Cohort().Config.ValidationRouteX,
                Cohort().Config.ValidationRouteY,
                Cohort().Config.ValidationRouteZ, false);
            PathType const pathType = calculated
                ? path.GetPathType() : PATHFIND_NOPATH;
            if (!calculated || (pathType & PATHFIND_NOPATH)
                || (pathType & PATHFIND_NOT_USING_PATH)
                || (pathType & PATHFIND_INCOMPLETE)
                || (pathType & PATHFIND_SHORTCUT)
                || (pathType & PATHFIND_FARFROMPOLY))
                return false;
            G3D::Vector3 const& actualEnd = path.GetActualEndPosition();
            if (std::hypot(
                    actualEnd.x - Cohort().Config.ValidationRouteX,
                    actualEnd.y - Cohort().Config.ValidationRouteY) > 0.25f
                || std::fabs(
                    actualEnd.z - Cohort().Config.ValidationRouteZ) > 1.0f)
                return false;

            std::vector<G3D::Vector3> points;
            points.emplace_back(source->GetPositionX(), source->GetPositionY(),
                source->GetPositionZ());
            points.insert(points.end(), path.GetPath().begin(), path.GetPath().end());
            points.push_back(actualEnd);
            float const requiredClearance =
                Cohort().Config.ValidationRouteClusterRadiusYards
                + Cohort().Config.ValidationRoutePatrolFutureGuardMarginYards;
            for (size_t routeIndex = Party().ValidationRouteManifestIndex + 1;
                routeIndex < Party().ValidationRouteManifest.size(); ++routeIndex)
            {
                ValidationRouteManifestNode const& futureNode =
                    Party().ValidationRouteManifest[routeIndex];
                if (futureNode.Kind != "trash" || !futureNode.TargetSpawnId
                    || futureNode.MapId != bot->GetMapId())
                    continue;
                std::vector<ObjectGuid::LowType> protectedSpawnIds = {
                    futureNode.TargetSpawnId,
                };
                protectedSpawnIds.insert(protectedSpawnIds.end(),
                    futureNode.SplitSourceGuids.begin(),
                    futureNode.SplitSourceGuids.end());
                std::sort(protectedSpawnIds.begin(), protectedSpawnIds.end());
                protectedSpawnIds.erase(std::unique(protectedSpawnIds.begin(),
                    protectedSpawnIds.end()), protectedSpawnIds.end());
                for (ObjectGuid::LowType const protectedSpawnId :
                    protectedSpawnIds)
                {
                    Creature* futureSource = bot->GetMap()->GetCreatureBySpawnId(
                        protectedSpawnId);
                    CreatureData const* futureData = sObjectMgr->GetCreatureData(
                        protectedSpawnId);
                    for (G3D::Vector3 const& point : points)
                    {
                        if (futureSource && futureSource->IsAlive()
                            && Distance2d(point.x, point.y,
                                futureSource->GetPositionX(),
                                futureSource->GetPositionY()) <= requiredClearance)
                            return false;
                        if (futureData && futureData->mapId == bot->GetMapId()
                            && Distance2d(point.x, point.y,
                                futureData->spawnPoint.GetPositionX(),
                                futureData->spawnPoint.GetPositionY())
                                <= requiredClearance)
                            return false;
                    }
                }
            }
            return true;
        };

        bool const sourceEngaged = isValidationCohortCombatLinked(source);

        for (WorldBotState const& cohortState : Party().Bots)
            if (Player* member = GetLoadedBot(cohortState))
                BotRaidAreaAuthority::SetAllOffenseSuppressed(
                    member->GetGUID().GetRawValue(), true);

        if (!sourceEngaged)
        {
            bool const atWait = source->GetExactDist(
                Cohort().Config.ValidationRoutePatrolWaitX,
                Cohort().Config.ValidationRoutePatrolWaitY,
                Cohort().Config.ValidationRoutePatrolWaitZ)
                <= Cohort().Config.ValidationRoutePatrolWaitToleranceYards;
            bool const rosterStaged = exactRosterAtAnchor();
            float const anchorDistance = bot->GetExactDist(
                Cohort().Config.ValidationRouteX,
                Cohort().Config.ValidationRouteY,
                Cohort().Config.ValidationRouteZ);
            if (anchorDistance
                > Cohort().Config.ValidationRoutePatrolAnchorToleranceYards)
            {
                bool const moved = MoveBotToPoint(state, bot,
                    Cohort().Config.ValidationRouteX,
                    Cohort().Config.ValidationRouteY,
                    Cohort().Config.ValidationRouteZ, true,
                    BotMovementArbitration::Owner::Route,
                    BotMovementArbitration::Priority::Route);
                return hold(moved ? "validation_route_patrol_anchor_move"
                                  : "validation_route_patrol_anchor_path_rejected",
                    source);
            }
            if (!rosterStaged)
                return hold("validation_route_patrol_roster_stage", source);
            if (!atWait)
                return hold("validation_route_patrol_wait_for_safe_phase", source);
            if (!sourcePathKeepsFutureEncountersSafe())
            {
                state.LastPathRejectReason =
                    "patrol_pull_native_chase_path_rejected";
                return hold("validation_route_patrol_chase_path_rejected", source);
            }

            auto const roster = Cohort().Raid.RosterByGuid.find(
                bot->GetGUID().GetCounter());
            bool const pullOwner = roster != Cohort().Raid.RosterByGuid.end()
                && roster->second.Active && roster->second.LeaseOwned
                && roster->second.SlotIndex + 1
                    == Cohort().Config.ValidationRoutePatrolPullOwnerRosterSlot;
            if (!pullOwner)
                return hold("validation_route_patrol_wait_for_puller", source);

            Player* tank = nullptr;
            for (WorldBotState const& cohortState : Party().Bots)
            {
                Player* member = GetLoadedBot(cohortState);
                auto const memberRoster = Cohort().Raid.RosterByGuid.find(
                    cohortState.Guid.GetCounter());
                if (member && memberRoster != Cohort().Raid.RosterByGuid.end()
                    && memberRoster->second.Active
                    && memberRoster->second.LeaseOwned
                    && memberRoster->second.Role == "tank"
                    && (!tank || memberRoster->second.SlotIndex
                        < Cohort().Raid.RosterByGuid.at(
                            tank->GetGUID().GetCounter()).SlotIndex))
                    tank = member;
            }
            if (!tank)
                return hold("validation_route_patrol_puller_no_tank", source);

            if (bot->getClass() == CLASS_HUNTER && bot->HasSpell(34477)
                && !bot->HasAura(34477)
                && TryCastFriendlySpell(bot, tank, 34477))
            {
                std::string raw = BuildRawJson(bot, source);
                std::string semantic = BuildSemanticJson(bot, source,
                    "validation_route_patrol_pull", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_patrol_pull", source,
                    "misdirection_to_anchor_tank", raw.c_str(), semantic.c_str(),
                    bot->GetExactDist(source), source->GetEntry(), 34477);
                target = source;
                state.TargetGuid = source->GetGUID();
                situation = "validation_route_patrol_pull";
                action = "validation_route_patrol_misdirection";
                return true;
            }

            BotRaidAreaAuthority::SetAllOffenseSuppressed(
                bot->GetGUID().GetRawValue(), false);
            BotRaidAreaAuthority::Set(bot->GetGUID().GetRawValue(), true);
            ResolvedCombatAction pullAction = ResolveProfileCombatAction(
                bot, source, 1, false, 0, false, false, true, false, true);
            bool const pullActionValid = pullAction.Valid
                && pullAction.Type == "cast" && pullAction.SpellId
                && pullAction.TargetGuid == source->GetGUID()
                && bot->IsWithinLOSInMap(source)
                && bot->GetExactDist(source)
                    <= std::max(5.0f, pullAction.MaxRange);
            BotActionResult result = pullActionValid
                ? ExecuteProfileCombatAction(&state, bot, source, &pullAction,
                    1, false, 0, false, false, true, false, true)
                : BotActionResult::NoAction;
            BotRaidAreaAuthority::SetAllOffenseSuppressed(
                bot->GetGUID().GetRawValue(), true);
            std::string raw = BuildRawJson(bot, source);
            std::string semantic = BuildSemanticJson(bot, source,
                "validation_route_patrol_pull", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_patrol_pull", source,
                result == BotActionResult::Ok ? "ordinary_ranged_pull_submitted"
                    : "ordinary_ranged_pull_pending",
                raw.c_str(), semantic.c_str(), bot->GetExactDist(source),
                source->GetEntry(),
                result == BotActionResult::Ok ? pullAction.SpellId : 0);
            target = source;
            state.TargetGuid = source->GetGUID();
            situation = "validation_route_patrol_pull";
            action = result == BotActionResult::Ok
                ? "validation_route_patrol_pull_submitted"
                : "validation_route_patrol_pull_pending";
            return true;
        }

        enrollValidationRoutePackMember(source, true);
        float const sourceAnchorDistance = source->GetExactDist(
            Cohort().Config.ValidationRouteX,
            Cohort().Config.ValidationRouteY,
            Cohort().Config.ValidationRouteZ);
        if (sourceAnchorDistance
            > Cohort().Config.ValidationRoutePatrolEngageRadiusYards)
            return hold("validation_route_patrol_chase_to_anchor", source);

        bool const tankOwned = source->GetVictim()
            && source->GetVictim()->ToPlayer()
            && Cohort().Raid.RosterByGuid.find(
                source->GetVictim()->GetGUID().GetCounter())
                != Cohort().Raid.RosterByGuid.end()
            && Cohort().Raid.RosterByGuid.at(
                source->GetVictim()->GetGUID().GetCounter()).Role == "tank";
        auto const roster = Cohort().Raid.RosterByGuid.find(
            bot->GetGUID().GetCounter());
        bool const botIsTank = roster != Cohort().Raid.RosterByGuid.end()
            && roster->second.Role == "tank";
        if (!botIsTank && !tankOwned)
            return hold("validation_route_patrol_wait_for_tank_threat", source);

        // The patrol contract ends once the source is engaged, inside its
        // declared chase radius, and tank-owned (or this bot is the tank).
        // Release only this bot's route offense gate and let the ordinary
        // priority queue own movement, healing, pet, and class actions.
        BotRaidAreaAuthority::SetAllOffenseSuppressed(
            bot->GetGUID().GetRawValue(), false);
        return false;
}
