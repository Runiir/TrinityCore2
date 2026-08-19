#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotRaidAreaAuthority.h"

#include "CellImpl.h"
#include "Creature.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Map.h"
#include "PathGenerator.h"
#include "Player.h"
#include "Unit.h"
#include "Object.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <string>
#include <vector>

using BotWorldPopulationMgrNativeHelpers::Distance2d;
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

namespace
{
constexpr uint64 DrudgePathRetryHeartbeatMs = 5000;

uint64 NowMs()
{
    using namespace std::chrono;
    return uint64(duration_cast<milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

namespace BotWorldPopulationMgrValidationRoute
{
bool DrudgeLaneContext::IsLandedRushPending() const
{
    if (Manager.Cohort().Config.ValidationRouteMechanicProfile
        != "trash_two_tank_charge_lanes")
        return false;
    auto observation = std::find_if(
        Manager.Party().ValidationRouteDrudgeChargeObservations.begin(),
        Manager.Party().ValidationRouteDrudgeChargeObservations.end(),
        [this](ChargeObservation const& candidate)
        {
            return !candidate.ReseparationRecorded
                && candidate.AttemptId == Manager.Cohort().AttemptId
                && candidate.WipeGeneration == Manager.Cohort().Raid.WipeGeneration
                && candidate.RouteGeneration
                    == Manager.Party().ValidationRouteGeneration;
        });
    return observation != Manager.Party().ValidationRouteDrudgeChargeObservations.end()
        && observation->Landed;
}

}

bool BotWorldPopulationMgr::TryValidationRouteDrudgeMinimumDistance(
    WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power,
    BotProgressionStage stage, BotProgressionActivity activity,
    std::string& situation, std::string& action, Unit*& target,
    std::function<bool(Creature const*)> const& isValidationCohortCombatLinked,
    bool specializedDrudgeRecovery)
{
    BotWorldPopulationMgrValidationRoute::DrudgeLaneRequest request;
    request.Manager = this;
    request.State = &state;
    request.Bot = bot;
    request.Power = &power;
    request.Stage = stage;
    request.Activity = activity;
    request.Situation = &situation;
    request.Action = &action;
    request.Target = &target;
    request.Callbacks.IsCombatLinked = isValidationCohortCombatLinked;
    BotWorldPopulationMgrValidationRoute::DrudgeLaneContext context(request);
    return context.TryMinimumDistance(specializedDrudgeRecovery);
}

namespace BotWorldPopulationMgrValidationRoute
{

bool DrudgeLaneContext::IsRecoveryFormationActive() const
{
    if (Manager.Cohort().Config.ValidationRouteMechanicProfile
        != "trash_two_tank_charge_lanes")
        return false;
    for (ChargeObservation const& observation :
        Manager.Party().ValidationRouteDrudgeChargeObservations)
        if (observation.Landed
            && observation.AttemptId == Manager.Cohort().AttemptId
            && observation.WipeGeneration == Manager.Cohort().Raid.WipeGeneration
            && observation.RouteGeneration
                == Manager.Party().ValidationRouteGeneration)
            return true;
    return false;
}

bool DrudgeLaneContext::TryMinimumDistance(bool specializedDrudgeRecovery)
{
    bool const drudgeProfile = Manager.Cohort().Config.ValidationRouteMechanicProfile
        == "trash_two_tank_charge_lanes";
    BotRaidDrudgeGeometry::MinimumDistanceOwner const minimumDistanceOwner =
        BotRaidDrudgeGeometry::SelectMinimumDistanceOwner(
            drudgeProfile, IsLandedRushPending());
    if (specializedDrudgeRecovery
        != (minimumDistanceOwner
            == BotRaidDrudgeGeometry::MinimumDistanceOwner::LandedRushRecovery))
        return false;

    uint32 sourceEntry = Manager.Cohort().Config.ValidationRouteMinimumDistanceSourceEntry;
    float minimumDistance = Manager.Cohort().Config.ValidationRouteMinimumDistanceYards;
    if (!sourceEntry || minimumDistance <= 0.0f
        || std::string(Manager.GetDungeonRole(Bot)) == "tank")
        return false;

    BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(
        Bot, Manager.GetDungeonRole(Bot));
    bool rangeAssigned = std::string(Manager.GetDungeonRole(Bot)) == "healer"
        || profile.MovementDirective == "ranged"
        || profile.MovementDirective == "healer_support";
    if (!rangeAssigned)
        return false;

    Creature* source = nullptr;
    float sourceDistance = std::numeric_limits<float>::max();
    std::vector<Creature*> sources;
    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(Bot, 60.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(
        Bot, objects, check);
    Cell::VisitAllObjects(Bot, searcher, 60.0f);
    for (WorldObject* object : objects)
    {
        Creature* creature = object ? object->ToCreature() : nullptr;
        if (!creature || creature->GetEntry() != sourceEntry
            || !creature->IsAlive() || !creature->GetHealth()
            || creature->GetMap() != Bot->GetMap()
            || !Bot->IsValidAttackTarget(creature)
            || !Callbacks.IsCombatLinked(creature))
            continue;
        sources.push_back(creature);
        float distance = Bot->GetExactDist2d(creature);
        if (!source || distance < sourceDistance)
        {
            source = creature;
            sourceDistance = distance;
        }
    }
    if (!source || sourceDistance >= minimumDistance)
        return false;

    // The contract distance is the exact native damaging radius. Search for
    // an exterior point against the union of every combat-linked source.
    float safeDistance = minimumDistance + 2.0f;
    std::vector<std::pair<float, float>> directions;
    auto addDirection = [&directions](float x, float y)
    {
        float length = std::hypot(x, y);
        if (length <= 0.001f)
            return;
        x /= length;
        y /= length;
        for (auto const& direction : directions)
            if (direction.first * x + direction.second * y >= 0.999f)
                return;
        directions.emplace_back(x, y);
    };
    float centroidX = 0.0f;
    float centroidY = 0.0f;
    for (Creature const* candidateSource : sources)
    {
        centroidX += candidateSource->GetPositionX();
        centroidY += candidateSource->GetPositionY();
        addDirection(
            Bot->GetPositionX() - candidateSource->GetPositionX(),
            Bot->GetPositionY() - candidateSource->GetPositionY());
    }
    centroidX /= float(sources.size());
    centroidY /= float(sources.size());
    addDirection(Bot->GetPositionX() - centroidX, Bot->GetPositionY() - centroidY);
    for (size_t left = 0; left < sources.size(); ++left)
        for (size_t right = left + 1; right < sources.size(); ++right)
        {
            float pairX = sources[right]->GetPositionX() - sources[left]->GetPositionX();
            float pairY = sources[right]->GetPositionY() - sources[left]->GetPositionY();
            addDirection(-pairY, pairX);
            addDirection(pairY, -pairX);
        }

    bool moved = false;
    float safeX = Bot->GetPositionX();
    float safeY = Bot->GetPositionY();
    float safeZ = Bot->GetPositionZ();
    for (auto const& direction : directions)
    {
        float requiredTravel = 0.0f;
        for (Creature const* candidateSource : sources)
        {
            float offsetX = Bot->GetPositionX() - candidateSource->GetPositionX();
            float offsetY = Bot->GetPositionY() - candidateSource->GetPositionY();
            float distanceSquared = offsetX * offsetX + offsetY * offsetY;
            if (distanceSquared >= safeDistance * safeDistance)
                continue;
            float projection = offsetX * direction.first + offsetY * direction.second;
            float discriminant = projection * projection
                + safeDistance * safeDistance - distanceSquared;
            requiredTravel = std::max(requiredTravel,
                -projection + std::sqrt(std::max(0.0f, discriminant)));
        }
        requiredTravel += 0.5f;
        float candidateX = Bot->GetPositionX() + direction.first * requiredTravel;
        float candidateY = Bot->GetPositionY() + direction.second * requiredTravel;
        float candidateZ = Bot->GetPositionZ();
        if (Map* map = Bot->GetMap())
        {
            float floorZ = map->GetHeight(Bot->GetPhaseShift(), candidateX,
                candidateY, candidateZ + 4.0f, true, 10.0f);
            if (floorZ > INVALID_HEIGHT && std::fabs(floorZ - candidateZ) <= 10.0f)
                candidateZ = floorZ;
        }

        PathGenerator path(Bot);
        bool pathOk = path.CalculatePath(candidateX, candidateY, candidateZ, false);
        PathType pathType = path.GetPathType();
        if (!pathOk || (pathType & PATHFIND_NOPATH)
            || (pathType & PATHFIND_NOT_USING_PATH)
            || (pathType & PATHFIND_INCOMPLETE)
            || (pathType & PATHFIND_SHORTCUT)
            || (pathType & PATHFIND_FARFROMPOLY))
            continue;

        bool unionSafe = true;
        for (Creature const* candidateSource : sources)
        {
            float startDistance = Bot->GetExactDist2d(candidateSource);
            float pathFloor = std::max(0.0f,
                std::min(startDistance, minimumDistance) - 0.25f);
            if (Distance2d(candidateX, candidateY,
                    candidateSource->GetPositionX(), candidateSource->GetPositionY())
                < safeDistance)
            {
                unionSafe = false;
                break;
            }
            for (G3D::Vector3 const& point : path.GetPath())
                if (Distance2d(point.x, point.y,
                        candidateSource->GetPositionX(), candidateSource->GetPositionY())
                    < pathFloor)
                {
                    unionSafe = false;
                    break;
                }
            if (!unionSafe)
                break;
        }
        if (!unionSafe)
            continue;

        safeX = candidateX;
        safeY = candidateY;
        safeZ = candidateZ;
        moved = Manager.MoveBotToPoint(State, Bot, safeX, safeY, safeZ);
        if (moved)
            break;
    }
    std::string raw = Manager.BuildRawJson(Bot, source);
    std::string semantic = Manager.BuildSemanticJson(
        Bot, source, "validation_route_mechanic", &Power, Stage, Activity);
    Manager.RecordEvent(State, Bot, "validation_route_mechanic", source,
        moved ? "minimum_distance_exit_started" : "minimum_distance_exit_failed",
        raw.c_str(), semantic.c_str(), sourceDistance, sourceEntry);
    Target = source;
    State.TargetGuid = source->GetGUID();
    Situation = "validation_route_mechanic";
    Action = moved ? "move_to_minimum_distance" : "hold_minimum_distance_exit_failed";
    return true;
}

DrudgeLaneContext::PhaseResult DrudgeLaneContext::BuildAnchorPolicies()
{
    CombatTankStagingActive = [this]
    {
        return SourceCombatStarted
            || (Manager.Party().ValidationRouteDrudgePrepullStaged
                && Manager.Party().ValidationRouteDrudgePrepullAttemptId
                    == Manager.Cohort().AttemptId
                && Manager.Party().ValidationRouteDrudgePrepullWipeGeneration
                    == Manager.Cohort().Raid.WipeGeneration
                && Manager.Party().ValidationRouteDrudgePrepullRouteGeneration
                    == Manager.Party().ValidationRouteGeneration);
    };
    StrictNativePath = [this](float x, float y, float z,
        bool requireExactEnd, std::string* rejectionOut) -> bool
    {
        auto reject = [rejectionOut](std::string reason)
        {
            if (rejectionOut)
                *rejectionOut = std::move(reason);
            return false;
        };
        if (!Bot || !Bot->GetMap())
            return reject("drudge_anchor_map_unavailable");
        float floorZ = Bot->GetMap()->GetHeight(Bot->GetPhaseShift(), x, y,
            z + 2.0f, true, 8.0f);
        if (floorZ <= INVALID_HEIGHT || std::fabs(floorZ - z) > 4.0f)
            return reject("drudge_anchor_floor_rejected");
        PathGenerator path(Bot);
        bool const pathOk = path.CalculatePath(x, y, z, false);
        PathType const pathType = path.GetPathType();
        bool const pathValid = pathOk
            && !(pathType & PATHFIND_NOPATH)
            && !(pathType & PATHFIND_NOT_USING_PATH)
            && !(pathType & PATHFIND_INCOMPLETE)
            && !(pathType & PATHFIND_SHORTCUT)
            && !(pathType & PATHFIND_FARFROMPOLY);
        if (!pathValid)
            return reject("drudge_anchor_native_path_rejected:path_type="
                + std::to_string(uint32(pathType)));
        if (!requireExactEnd)
        {
            if (rejectionOut)
                rejectionOut->clear();
            return true;
        }
        G3D::Vector3 const& actualEnd = path.GetActualEndPosition();
        float const end2d = std::hypot(actualEnd.x - x, actualEnd.y - y);
        float const endZ = std::fabs(actualEnd.z - z);
        if (end2d > 0.25f || endZ > 1.0f)
            return reject("drudge_anchor_native_end_rejected:end2d="
                + std::to_string(end2d) + ":endz=" + std::to_string(endZ));
        if (rejectionOut)
            rejectionOut->clear();
        return true;
    };
    StrictTankRecoveryPath = [this](float x, float y, float z) -> bool
    {
        if (!AssignedTank || !OtherTank || !Bot->GetMap())
            return false;
        if (!StrictNativePath(x, y, z, true, nullptr))
            return false;
        PathGenerator path(Bot);
        if (!path.CalculatePath(x, y, z, false))
            return false;
        std::vector<BotRaidDrudgeGeometry::Point2d> points;
        points.push_back({ Bot->GetPositionX(), Bot->GetPositionY() });
        for (G3D::Vector3 const& point : path.GetPath())
            points.push_back({ point.x, point.y });
        points.push_back({ path.GetActualEndPosition().x,
            path.GetActualEndPosition().y });
        float const otherProjection =
            (OtherTank->GetPositionX() - MidpointX) * AxisX
            + (OtherTank->GetPositionY() - MidpointY) * AxisY;
        return BotRaidDrudgeGeometry::RecoveryPathPreservesTankSeparation(
            points, MidpointX, MidpointY, AxisX, AxisY, LaneSign,
            -LaneSign * otherProjection,
            Manager.Cohort().Config.ValidationRouteSplitMinimumSeparationYards);
    };
    UniqueGroupAnchor = [this](uint32 slot) -> std::pair<float, float>
    {
        bool const tankSlot = std::find(
            Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.begin(),
            Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.end(), slot)
            != Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.end();
        MemberAnchor const* anchor = tankSlot && IsRecoveryFormationActive()
            ? DeclaredRecoveryTankAnchorFor(slot)
            : (tankSlot && CombatTankStagingActive()
                ? DeclaredNavigationTankAnchorFor(slot) : DeclaredAnchorFor(slot));
        return anchor ? std::pair<float, float>{ anchor->X, anchor->Y }
                      : std::pair<float, float>{ 0.0f, 0.0f };
    };
    AnchorCandidatesFor = [this](uint32 slot)
    {
        auto const [x, y] = UniqueGroupAnchor(slot);
        return std::vector<std::pair<float, float>>{ { x, y } };
    };
    AnchorCacheMatchesGeneration = [this]
    {
        return State.ValidationRouteDrudgeAnchorValid
            && State.ValidationRouteDrudgeAnchorAttemptId == Manager.Cohort().AttemptId
            && State.ValidationRouteDrudgeAnchorWipeGeneration
                == Manager.Cohort().Raid.WipeGeneration
            && State.ValidationRouteDrudgeAnchorRouteGeneration
                == Manager.Party().ValidationRouteGeneration
            && State.ValidationRouteDrudgeAnchorMapId == Bot->GetMapId()
            && State.ValidationRouteDrudgeAnchorInstanceId == Bot->GetInstanceId()
            && Bot->GetInstanceId() != 0
            && State.ValidationRouteDrudgeAnchorSource0Identity
                == Sources[0]->GetGUID().GetRawValue()
            && State.ValidationRouteDrudgeAnchorSource1Identity
                == Sources[1]->GetGUID().GetRawValue();
    };
    CachedAnchorSafe = [this](WorldBotState const& anchorState,
        Player const* member) -> bool
    {
        if (!member || anchorState.Guid != member->GetGUID()
            || !anchorState.ValidationRouteDrudgeAnchorValid
            || anchorState.ValidationRouteDrudgeAnchorAttemptId != Manager.Cohort().AttemptId
            || anchorState.ValidationRouteDrudgeAnchorWipeGeneration
                != Manager.Cohort().Raid.WipeGeneration
            || anchorState.ValidationRouteDrudgeAnchorRouteGeneration
                != Manager.Party().ValidationRouteGeneration
            || anchorState.ValidationRouteDrudgeAnchorMapId != Bot->GetMapId()
            || anchorState.ValidationRouteDrudgeAnchorInstanceId != Bot->GetInstanceId()
            || Bot->GetInstanceId() == 0
            || anchorState.ValidationRouteDrudgeAnchorSource0Identity
                != Sources[0]->GetGUID().GetRawValue()
            || anchorState.ValidationRouteDrudgeAnchorSource1Identity
                != Sources[1]->GetGUID().GetRawValue())
            return false;
        auto memberRoster = Manager.Cohort().Raid.RosterByGuid.find(
            member->GetGUID().GetCounter());
        if (memberRoster == Manager.Cohort().Raid.RosterByGuid.end())
            return false;
        uint32 const memberSlot = memberRoster->second.SlotIndex + 1;
        bool const memberLaneA = std::find(
            Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
            Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), memberSlot)
            != Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
        auto candidates = AnchorCandidatesFor(memberSlot);
        if (anchorState.ValidationRouteDrudgeAnchorCandidateIndex >= candidates.size()
            || Distance2d(anchorState.ValidationRouteDrudgeAnchorX,
                anchorState.ValidationRouteDrudgeAnchorY,
                candidates[anchorState.ValidationRouteDrudgeAnchorCandidateIndex].first,
                candidates[anchorState.ValidationRouteDrudgeAnchorCandidateIndex].second)
                > 0.01f)
            return false;
        float const memberLaneSign = memberLaneA ? -1.0f : 1.0f;
        float const projection =
            (anchorState.ValidationRouteDrudgeAnchorX - MidpointX) * AxisX
            + (anchorState.ValidationRouteDrudgeAnchorY - MidpointY) * AxisY;
        if (memberLaneSign * projection < LaneSeparation * 0.25f)
            return false;
        if (memberRoster->second.Role == "tank"
            && memberSlot != Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots[
                memberLaneA ? 0 : 1])
            return false;
        if (memberRoster->second.Role != "tank"
            && (Distance2d(anchorState.ValidationRouteDrudgeAnchorX,
                    anchorState.ValidationRouteDrudgeAnchorY,
                    Sources[0]->GetPositionX(), Sources[0]->GetPositionY())
                    < Manager.Cohort().Config.ValidationRouteMinimumDistanceYards
                || Distance2d(anchorState.ValidationRouteDrudgeAnchorX,
                    anchorState.ValidationRouteDrudgeAnchorY,
                    Sources[1]->GetPositionX(), Sources[1]->GetPositionY())
                    < Manager.Cohort().Config.ValidationRouteMinimumDistanceYards))
            return false;
        float const arrivalTolerance = memberRoster->second.Role == "tank"
            ? Manager.Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards
            : Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards;
        return member->GetExactDist(anchorState.ValidationRouteDrudgeAnchorX,
            anchorState.ValidationRouteDrudgeAnchorY,
            anchorState.ValidationRouteDrudgeAnchorZ) <= arrivalTolerance;
    };
    GroupPositionSafe = [this](Player const* member) -> bool
    {
        if (!member)
            return false;
        auto memberRoster = Manager.Cohort().Raid.RosterByGuid.find(
            member->GetGUID().GetCounter());
        if (memberRoster == Manager.Cohort().Raid.RosterByGuid.end()
            || memberRoster->second.Role == "tank")
            return false;
        uint32 const slot = memberRoster->second.SlotIndex + 1;
        bool const laneA = std::find(
            Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
            Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), slot)
            != Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
        bool const laneB = std::find(
            Manager.Cohort().Config.ValidationRouteSplitLaneBRosterSlots.begin(),
            Manager.Cohort().Config.ValidationRouteSplitLaneBRosterSlots.end(), slot)
            != Manager.Cohort().Config.ValidationRouteSplitLaneBRosterSlots.end();
        if (laneA == laneB)
            return false;
        float const minimumSafeDistance =
            Manager.Cohort().Config.ValidationRouteMinimumDistanceYards;
        if (Distance2d(member->GetPositionX(), member->GetPositionY(),
                Sources[0]->GetPositionX(), Sources[0]->GetPositionY()) < minimumSafeDistance
            || Distance2d(member->GetPositionX(), member->GetPositionY(),
                Sources[1]->GetPositionX(), Sources[1]->GetPositionY()) < minimumSafeDistance)
            return false;
        float const projection = (member->GetPositionX() - MidpointX) * AxisX
            + (member->GetPositionY() - MidpointY) * AxisY;
        if ((laneA ? -1.0f : 1.0f) * projection < LaneSeparation * 0.25f)
            return false;
        auto memberState = std::find_if(Manager.Party().Bots.begin(),
            Manager.Party().Bots.end(), [member](WorldBotState const& candidate)
            {
                return candidate.Guid == member->GetGUID();
            });
        if (memberState == Manager.Party().Bots.end()
            || !CachedAnchorSafe(*memberState, member))
            return false;
        float const sameLaneMinimum = std::max(3.0f,
            Manager.Cohort().Config.ValidationRouteSplitNavigationMarginYards
                + Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards * 0.5f);
        for (WorldBotState const& cohortState : Manager.Party().Bots)
        {
            Player* other = Manager.GetLoadedBot(cohortState);
            if (!other || other == member || !other->IsInWorld()
                || !other->IsAlive() || other->GetMap() != Bot->GetMap())
                continue;
            auto otherRoster = Manager.Cohort().Raid.RosterByGuid.find(
                other->GetGUID().GetCounter());
            if (otherRoster == Manager.Cohort().Raid.RosterByGuid.end()
                || otherRoster->second.Role == "tank")
                continue;
            bool const otherLaneA = std::find(
                Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(),
                otherRoster->second.SlotIndex + 1)
                != Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
            if (otherLaneA == laneA && member->GetExactDist2d(other) < sameLaneMinimum)
                return false;
        }
        return true;
    };
    ExactRosterPrepullStaged = [this]
    {
        std::set<uint32> stagedGuids;
        for (WorldBotState const& cohortState : Manager.Party().Bots)
        {
            Player* member = Manager.GetLoadedBot(cohortState);
            if (!member || !member->IsInWorld() || !member->IsAlive()
                || member->GetMap() != Bot->GetMap())
                return false;
            auto memberRoster = Manager.Cohort().Raid.RosterByGuid.find(
                member->GetGUID().GetCounter());
            if (memberRoster == Manager.Cohort().Raid.RosterByGuid.end()
                || !memberRoster->second.Active || !memberRoster->second.LeaseOwned)
                return false;
            bool const memberSafe = memberRoster->second.Role == "tank"
                ? CachedAnchorSafe(cohortState, member) : GroupPositionSafe(member);
            if (!memberSafe)
                return false;
            stagedGuids.insert(member->GetGUID().GetCounter());
        }
        return stagedGuids.size() == ExactRosterSlots.size();
    };
    SourceOnFrozenLane = [this](Creature const* source, uint32 sourceIndex,
        float* projectionOut) -> bool
    {
        if (!source)
            return false;
        float const projection = (source->GetPositionX() - MidpointX) * AxisX
            + (source->GetPositionY() - MidpointY) * AxisY;
        if (projectionOut)
            *projectionOut = projection;
        return (sourceIndex == 0 ? -1.0f : 1.0f) * projection
            >= LaneSeparation * 0.25f;
    };
    SelectPathableDrudgeAnchor = [this](bool tank) -> bool
    {
        std::vector<std::pair<float, float>> const candidates =
            AnchorCandidatesFor(OneBasedSlot);
        auto candidateSpacingSafe = [this, tank](float x, float y)
        {
            if (tank)
                return true;
            for (WorldBotState const& cohortState : Manager.Party().Bots)
            {
                Player* other = Manager.GetLoadedBot(cohortState);
                if (!other || other == Bot || !other->IsInWorld()
                    || !other->IsAlive() || other->GetMap() != Bot->GetMap())
                    continue;
                auto otherRoster = Manager.Cohort().Raid.RosterByGuid.find(
                    other->GetGUID().GetCounter());
                if (otherRoster == Manager.Cohort().Raid.RosterByGuid.end()
                    || otherRoster->second.Role == "tank")
                    continue;
                bool const otherLaneA = std::find(
                    Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                    Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(),
                    otherRoster->second.SlotIndex + 1)
                    != Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
                if (otherLaneA != LaneA)
                    continue;
                float otherX = other->GetPositionX();
                float otherY = other->GetPositionY();
                if (cohortState.ValidationRouteDrudgeAnchorValid
                    && cohortState.ValidationRouteDrudgeAnchorAttemptId
                        == Manager.Cohort().AttemptId
                    && cohortState.ValidationRouteDrudgeAnchorWipeGeneration
                        == Manager.Cohort().Raid.WipeGeneration
                    && cohortState.ValidationRouteDrudgeAnchorRouteGeneration
                        == Manager.Party().ValidationRouteGeneration)
                {
                    otherX = cohortState.ValidationRouteDrudgeAnchorX;
                    otherY = cohortState.ValidationRouteDrudgeAnchorY;
                }
                if (Distance2d(x, y, otherX, otherY)
                    < std::max(3.0f,
                        Manager.Cohort().Config.ValidationRouteSplitNavigationMarginYards
                            + Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards
                                * 0.5f))
                    return false;
            }
            return true;
        };
        auto cacheUsable = [&]()
        {
            if (!AnchorCacheMatchesGeneration()
                || State.ValidationRouteDrudgeAnchorCandidateIndex >= candidates.size()
                || Distance2d(State.ValidationRouteDrudgeAnchorX,
                    State.ValidationRouteDrudgeAnchorY,
                    candidates[State.ValidationRouteDrudgeAnchorCandidateIndex].first,
                    candidates[State.ValidationRouteDrudgeAnchorCandidateIndex].second)
                    > 0.01f)
                return false;
            float const projection =
                (State.ValidationRouteDrudgeAnchorX - MidpointX) * AxisX
                + (State.ValidationRouteDrudgeAnchorY - MidpointY) * AxisY;
            if (LaneSign * projection < LaneSeparation * 0.25f)
                return false;
            if (!tank && (!GroupPositionSafe(Bot)
                || Distance2d(State.ValidationRouteDrudgeAnchorX,
                    State.ValidationRouteDrudgeAnchorY, Sources[0]->GetPositionX(),
                    Sources[0]->GetPositionY())
                    < Manager.Cohort().Config.ValidationRouteMinimumDistanceYards
                || Distance2d(State.ValidationRouteDrudgeAnchorX,
                    State.ValidationRouteDrudgeAnchorY, Sources[1]->GetPositionX(),
                    Sources[1]->GetPositionY())
                    < Manager.Cohort().Config.ValidationRouteMinimumDistanceYards))
                return false;
            return candidateSpacingSafe(State.ValidationRouteDrudgeAnchorX,
                State.ValidationRouteDrudgeAnchorY);
        };
        if (cacheUsable())
            return true;

        bool const priorScopeMatches = State.ValidationRouteDrudgeAnchorPathProven
            && State.ValidationRouteDrudgeAnchorAttemptId == Manager.Cohort().AttemptId
            && State.ValidationRouteDrudgeAnchorWipeGeneration
                == Manager.Cohort().Raid.WipeGeneration
            && State.ValidationRouteDrudgeAnchorRouteGeneration
                == Manager.Party().ValidationRouteGeneration
            && State.ValidationRouteDrudgeAnchorMapId == Bot->GetMapId()
            && State.ValidationRouteDrudgeAnchorInstanceId == Bot->GetInstanceId()
            && Bot->GetInstanceId() != 0
            && State.ValidationRouteDrudgeAnchorSource0Identity
                == Sources[0]->GetGUID().GetRawValue()
            && State.ValidationRouteDrudgeAnchorSource1Identity
                == Sources[1]->GetGUID().GetRawValue();
        bool const priorCandidateMatches = priorScopeMatches
            && State.ValidationRouteDrudgeAnchorCandidateIndex < candidates.size()
            && Distance2d(State.ValidationRouteDrudgeAnchorX,
                State.ValidationRouteDrudgeAnchorY,
                candidates[State.ValidationRouteDrudgeAnchorCandidateIndex].first,
                candidates[State.ValidationRouteDrudgeAnchorCandidateIndex].second)
                <= 0.01f;
        float const priorProjection =
            (State.ValidationRouteDrudgeAnchorX - MidpointX) * AxisX
            + (State.ValidationRouteDrudgeAnchorY - MidpointY) * AxisY;
        bool const priorLaneSafe = priorCandidateMatches
            && LaneSign * priorProjection >= LaneSeparation * 0.25f;
        bool const sourcesSeparated = Sources[0]->GetExactDist2d(Sources[1])
            >= LaneSeparation;
        bool const recoveryFormationActiveForProof = IsRecoveryFormationActive();
        bool const priorSourceSafe = tank
            ? (priorCandidateMatches && (recoveryFormationActiveForProof
                || (sourcesSeparated && SourceOnFrozenLane(Sources[0], 0, nullptr)
                    && SourceOnFrozenLane(Sources[1], 1, nullptr)
                    && Distance2d(State.ValidationRouteDrudgeAnchorX,
                        State.ValidationRouteDrudgeAnchorY,
                        Sources[LaneIndex]->GetPositionX(),
                        Sources[LaneIndex]->GetPositionY())
                        <= Manager.Cohort().Config.ValidationRouteSplitMinimumSeparationYards)))
            : (priorCandidateMatches
                && Distance2d(State.ValidationRouteDrudgeAnchorX,
                    State.ValidationRouteDrudgeAnchorY, Sources[0]->GetPositionX(),
                    Sources[0]->GetPositionY())
                    >= Manager.Cohort().Config.ValidationRouteMinimumDistanceYards
                && Distance2d(State.ValidationRouteDrudgeAnchorX,
                    State.ValidationRouteDrudgeAnchorY, Sources[1]->GetPositionX(),
                    Sources[1]->GetPositionY())
                    >= Manager.Cohort().Config.ValidationRouteMinimumDistanceYards);
        bool const memberAtPriorAnchor = priorCandidateMatches
            && Bot->GetExactDist(State.ValidationRouteDrudgeAnchorX,
                State.ValidationRouteDrudgeAnchorY,
                State.ValidationRouteDrudgeAnchorZ)
                <= (tank
                    ? Manager.Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards
                    : Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards);
        BotRaidDrudgeGeometry::Scope const proofScope{
            Manager.Cohort().AttemptId, Manager.Cohort().Raid.WipeGeneration,
            Manager.Party().ValidationRouteGeneration, Bot->GetMapId(),
            Bot->GetInstanceId(), Sources[0]->GetGUID().GetRawValue(),
            Sources[1]->GetGUID().GetRawValue() };
        BotRaidDrudgeGeometry::State proofState;
        proofState.Identity = proofScope;
        proofState.PriorPathProofAvailable = State.ValidationRouteDrudgeAnchorPathProven;
        BotRaidDrudgeGeometry::Input proofInput;
        proofInput.Identity = proofScope;
        proofInput.EvaluatePriorPathProof = true;
        proofInput.PriorProofScopeMatches = priorScopeMatches;
        proofInput.PriorProofCandidateMatches = priorCandidateMatches;
        proofInput.MemberAtProvenAnchor = memberAtPriorAnchor;
        proofInput.DynamicLaneSafe = priorLaneSafe;
        proofInput.DynamicSourceSafe = priorSourceSafe;
        proofInput.DynamicSpacingSafe = priorCandidateMatches
            && candidateSpacingSafe(State.ValidationRouteDrudgeAnchorX,
                State.ValidationRouteDrudgeAnchorY);
        BotRaidDrudgeGeometry::Result const proofTransition =
            BotRaidDrudgeGeometry::Advance(proofState, proofInput);
        State.ValidationRouteDrudgeAnchorPathProven =
            proofTransition.Next.PriorPathProofAvailable;
        if (proofTransition.ReactivatePriorPathProof)
        {
            State.ValidationRouteDrudgeAnchorValid = true;
            return true;
        }

        State.ValidationRouteDrudgeAnchorValid = false;
        uint64 const nowMs = NowMs();
        for (size_t candidateIndex = 0; candidateIndex < candidates.size(); ++candidateIndex)
        {
            MemberAnchor const* candidateAnchor = tank && IsRecoveryFormationActive()
                ? DeclaredRecoveryTankAnchorFor(OneBasedSlot)
                : (tank && CombatTankStagingActive()
                    ? DeclaredNavigationTankAnchorFor(OneBasedSlot)
                    : DeclaredAnchorFor(OneBasedSlot));
            if (!candidateAnchor)
                continue;
            float const projection = (candidates[candidateIndex].first - MidpointX) * AxisX
                + (candidates[candidateIndex].second - MidpointY) * AxisY;
            if (LaneSign * projection < LaneSeparation * 0.25f)
                continue;
            if (!tank && (Distance2d(candidates[candidateIndex].first,
                    candidates[candidateIndex].second, Sources[0]->GetPositionX(),
                    Sources[0]->GetPositionY())
                    < Manager.Cohort().Config.ValidationRouteMinimumDistanceYards
                || Distance2d(candidates[candidateIndex].first,
                    candidates[candidateIndex].second, Sources[1]->GetPositionX(),
                    Sources[1]->GetPositionY())
                    < Manager.Cohort().Config.ValidationRouteMinimumDistanceYards))
                continue;
            bool const dynamicSpacingSafe = tank
                || candidateSpacingSafe(candidates[candidateIndex].first,
                    candidates[candidateIndex].second);
            bool const dynamicSourceSafe = tank
                || (Distance2d(candidates[candidateIndex].first,
                        candidates[candidateIndex].second, Sources[0]->GetPositionX(),
                        Sources[0]->GetPositionY())
                    >= Manager.Cohort().Config.ValidationRouteMinimumDistanceYards
                && Distance2d(candidates[candidateIndex].first,
                        candidates[candidateIndex].second, Sources[1]->GetPositionX(),
                        Sources[1]->GetPositionY())
                    >= Manager.Cohort().Config.ValidationRouteMinimumDistanceYards);
            BotRaidDrudgeGeometry::AnchorPathSearchDecision const pathSearch =
                BotRaidDrudgeGeometry::SelectAnchorPathSearch(
                    State.ValidationRouteDrudgeAnchorSearchCooldownUntilMs,
                    nowMs, dynamicSourceSafe, dynamicSpacingSafe);
            State.ValidationRouteDrudgeAnchorSearchCooldownUntilMs =
                pathSearch.RetryAfterMs;
            if (pathSearch.SourceBlocked)
            {
                State.LastPathRejectReason = "drudge_anchor_source_unsafe";
                State.LastRecoveryResult = State.LastPathRejectReason;
                continue;
            }
            if (pathSearch.SpacingBlocked)
            {
                State.LastPathRejectReason = "drudge_anchor_spacing_unsafe";
                State.LastRecoveryResult = State.LastPathRejectReason;
                continue;
            }
            if (!pathSearch.NativePathSearchDue)
            {
                State.LastPathRejectReason = "drudge_anchor_path_retry_cooldown";
                State.LastRecoveryResult = State.LastPathRejectReason;
                continue;
            }
            std::string rejection;
            if (!StrictNativePath(candidates[candidateIndex].first,
                candidates[candidateIndex].second, candidateAnchor->Z,
                    tank, &rejection))
            {
                State.ValidationRouteDrudgeAnchorSearchCooldownUntilMs =
                    nowMs + DrudgePathRetryHeartbeatMs;
                State.LastPathRejectReason = rejection.empty()
                    ? "drudge_anchor_native_path_rejected" : rejection;
                State.LastRecoveryResult = State.LastPathRejectReason;
                continue;
            }
            State.ValidationRouteDrudgeAnchorX = candidates[candidateIndex].first;
            State.ValidationRouteDrudgeAnchorY = candidates[candidateIndex].second;
            State.ValidationRouteDrudgeAnchorZ = candidateAnchor->Z;
            State.ValidationRouteDrudgeAnchorCandidateIndex = uint32(candidateIndex);
            State.ValidationRouteDrudgeAnchorValid = true;
            State.ValidationRouteDrudgeAnchorPathProven = true;
            State.ValidationRouteDrudgeAnchorAttemptId = Manager.Cohort().AttemptId;
            State.ValidationRouteDrudgeAnchorWipeGeneration = Manager.Cohort().Raid.WipeGeneration;
            State.ValidationRouteDrudgeAnchorRouteGeneration = Manager.Party().ValidationRouteGeneration;
            State.ValidationRouteDrudgeAnchorMapId = Bot->GetMapId();
            State.ValidationRouteDrudgeAnchorInstanceId = Bot->GetInstanceId();
            State.ValidationRouteDrudgeAnchorSource0Identity = Sources[0]->GetGUID().GetRawValue();
            State.ValidationRouteDrudgeAnchorSource1Identity = Sources[1]->GetGUID().GetRawValue();
            State.LastPathRejectReason.clear();
            State.LastRecoveryResult.clear();
            return true;
        }
        State.ValidationRouteDrudgeAnchorValid = false;
        return false;
    };
    ExactRosterReSeparated = [this]
    {
        if (!LaneTank || !OtherTank || Sources[0]->GetExactDist2d(Sources[1])
                < LaneSeparation || !SourceOnFrozenLane(Sources[0], 0, nullptr)
            || !SourceOnFrozenLane(Sources[1], 1, nullptr))
            return false;
        auto tankSafe = [this](Player const* tank, uint32 slot)
        {
            return tank && tank->IsAlive() && TankOnFrozenLane(tank, slot);
        };
        if (!tankSafe(LaneTank, LaneTankSlot) || !tankSafe(OtherTank, OtherTankSlot)
            || LaneTank->GetExactDist2d(LaneSource)
                > Manager.Cohort().Config.ValidationRouteSplitMinimumSeparationYards
            || OtherTank->GetExactDist2d(OtherSource)
                > Manager.Cohort().Config.ValidationRouteSplitMinimumSeparationYards)
            return false;
        if ((LaneSource->IsAlive() && LaneSource->GetVictim() != LaneTank)
            || (OtherSource->IsAlive() && OtherSource->GetVictim() != OtherTank))
            return false;
        for (WorldBotState const& cohortState : Manager.Party().Bots)
        {
            Player* member = Manager.GetLoadedBot(cohortState);
            if (!member || !member->IsInWorld() || !member->IsAlive()
                || member->GetMap() != Bot->GetMap())
                return false;
            auto roster = Manager.Cohort().Raid.RosterByGuid.find(
                member->GetGUID().GetCounter());
            if (roster == Manager.Cohort().Raid.RosterByGuid.end()
                || !roster->second.Active || !roster->second.LeaseOwned
                || (roster->second.Role == "tank"
                    && member != (roster->second.SlotIndex + 1 == LaneTankSlot
                        ? LaneTank : OtherTank))
                || (roster->second.Role != "tank" && !GroupPositionSafe(member)))
                return false;
        }
        return true;
    };
    MarkAllRosterReseparated = [this](ChargeObservation& observation)
    {
        RecordReseparationEvidence(observation);
    };
    TankOnFrozenLane = [this](Player const* tank, uint32 slot)
    {
        if (!tank)
            return false;
        bool const laneA = std::find(
            Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
            Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), slot)
            != Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
        float const projection = (tank->GetPositionX() - MidpointX) * AxisX
            + (tank->GetPositionY() - MidpointY) * AxisY;
        return (laneA ? -1.0f : 1.0f) * projection >= LaneSeparation * 0.25f;
    };
    TanksOnFrozenLanes = [this]
    {
        return LaneTank && OtherTank && LaneTank->IsAlive() && OtherTank->IsAlive()
            && LaneTank->GetMap() == Bot->GetMap() && OtherTank->GetMap() == Bot->GetMap()
            && LaneTank->GetExactDist2d(OtherTank)
                >= Manager.Cohort().Config.ValidationRouteSplitMinimumSeparationYards
            && TankOnFrozenLane(LaneTank, LaneTankSlot)
            && TankOnFrozenLane(OtherTank, OtherTankSlot);
    };
    BoundTankSourceGeometrySafe = [this]
    {
        return TanksOnFrozenLanes()
            && LaneTank->GetExactDist2d(LaneSource)
                <= Manager.Cohort().Config.ValidationRouteSplitMinimumSeparationYards
            && OtherTank->GetExactDist2d(OtherSource)
                <= Manager.Cohort().Config.ValidationRouteSplitMinimumSeparationYards;
    };
    ExactCombatTankPathsProven = [this]
    {
        return ComputeExactCombatTankPathsProven();
    };
    ExactRecoveryTankPathsProven = [this]
    {
        return ComputeExactRecoveryTankPathsProven();
    };
    ExactCombatTankAnchorsSafe = [this]
    {
        return ComputeExactCombatTankPathsProven();
    };
    ExactLiveRecoveryTankPathsPreflighted = [this]
    {
        return ComputeExactLiveRecoveryTankPathsPreflighted();
    };
    return PhaseResult::Continue;
}
}
