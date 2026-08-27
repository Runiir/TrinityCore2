#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeNativeAnchor.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeNativePathDecision.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeRecoveryCandidates.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeRecovery.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrNativePathValidation.h"
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
constexpr float DrudgeMinimumDistanceEndpointToleranceYards = 1.0f;
uint64 NowMs()
{
    using namespace std::chrono;
    return uint64(duration_cast<milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

namespace BotWorldPopulationMgrValidationRoute
{
bool DrudgeLaneContext::TryMinimumDistance(bool specializedDrudgeRecovery)
{
    bool const drudgeProfile = Manager.Cohort().Config.ValidationRouteMechanicProfile
        == "trash_two_tank_charge_lanes";
    auto const& party = Manager.Party();
    bool const exactPrepullStaged = party.ValidationRouteDrudgePrepullStaged
        && party.ValidationRouteDrudgePrepullAttemptId == Manager.Cohort().AttemptId
        && party.ValidationRouteDrudgePrepullWipeGeneration
            == Manager.Cohort().Raid.WipeGeneration
        && party.ValidationRouteDrudgePrepullRouteGeneration
            == party.ValidationRouteGeneration;
    if (!specializedDrudgeRecovery
        && BotRaidDrudgeGeometry::ExactDrudgeLaneOwnsGroupMovement(
            drudgeProfile, exactPrepullStaged))
        return false;
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
        // Smooth-path generation may append an off-mesh destination when a
        // one-poly corridor only reaches its nearest boundary.  The straight
        // native query exposes that boundary so admission cannot bless the
        // raw point that MotionMaster would otherwise receive.
        path.SetUseStraightPath(true);
        bool pathOk = path.CalculatePath(candidateX, candidateY, candidateZ, false);
        PathType pathType = path.GetPathType();
        if (!pathOk || (pathType & PATHFIND_NOPATH)
            || (pathType & PATHFIND_NOT_USING_PATH)
            || (pathType & PATHFIND_INCOMPLETE)
            || (pathType & PATHFIND_SHORTCUT)
            || (pathType & PATHFIND_FARFROMPOLY))
            continue;
        // A complete corridor can still end at the nearest navmesh point
        // when the requested minimum-distance point is just beyond the
        // platform. MovePoint would otherwise receive the unreachable raw
        // destination and can send the bot off the platform.
        G3D::Vector3 const& actualEnd = path.GetActualEndPosition();
        if (std::hypot(actualEnd.x - candidateX, actualEnd.y - candidateY)
                > DrudgeMinimumDistanceEndpointToleranceYards
            || std::fabs(actualEnd.z - candidateZ) > 1.5f)
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
            if (Distance2d(actualEnd.x, actualEnd.y,
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
        moved = Manager.MoveBotToPoint(State, Bot, safeX, safeY, safeZ, false,
            BotMovementArbitration::Owner::Mechanic,
            BotMovementArbitration::Priority::Mechanic);
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
        bool requireExactEnd, bool requireSourceUnionSafety,
        std::string* rejectionOut) -> bool
    {
        auto reject = [rejectionOut](std::string reason)
        {
            if (rejectionOut)
                *rejectionOut = std::move(reason);
            return false;
        };
        if (!Bot || !Bot->GetMap())
            return reject("drudge_anchor_map_unavailable");
        float const resolvedZ = Bot->GetMap()->GetHeight(Bot->GetPhaseShift(), x, y,
            z + 2.0f, true, 8.0f);
        if (resolvedZ <= INVALID_HEIGHT)
            return reject("drudge_anchor_floor_rejected");
        BotWorldMovement::NativeFloorResult const floorAdmission =
            BotWorldMovement::AdmitResolvedHeight(resolvedZ, z);
        if (!floorAdmission.Accepted())
            return reject("drudge_anchor_floor_rejected");
        z = floorAdmission.Z;
        PathGenerator path(Bot);
        bool const pathOk = path.CalculatePath(x, y, z, false);
        if (!BotWorldMovement::NativePathIsComplete(pathOk, path))
        {
            PathType const pathType = path.GetPathType();
            return reject("drudge_anchor_native_path_rejected:path_type="
                + std::to_string(uint32(pathType)));
        }
        // The endpoint may resolve on the encounter floor while an
        // intermediate sample sees a stacked collision layer.  The complete
        // Drudge path still uses the declared/reference-floor envelope for
        // that remote evidence; generic movement keeps its strict overload.
        if (!BotWorldMovement::NativePathFloorsValid(Bot, path, z, true))
            return reject("drudge_anchor_path_floor_gap");
        auto const& route = Manager.Party().ValidationRouteManifest;
        size_t const nextIndex = Manager.Party().ValidationRouteManifestIndex + 1;
        if (nextIndex >= route.size() || route[nextIndex].Kind != "boss"
            || route[nextIndex].TargetEntry != 41570
            || route[nextIndex].MapId != Bot->GetMapId()
            || Manager.Cohort().Config.ValidationRouteSplitTankCombatAnchors.size() != 2)
            return reject("drudge_anchor_future_encounter_contract_unresolved");
        BotWorldPopulationMgrRouteState::ValidationRouteManifestNode const& future =
            route[nextIndex];
        float futureClearance = std::numeric_limits<float>::max();
        for (MemberAnchor const& combat :
            Manager.Cohort().Config.ValidationRouteSplitTankCombatAnchors)
            futureClearance = std::min(futureClearance,
                Distance2d(combat.X, combat.Y, future.X, future.Y));
        auto futureSafe = [&future, futureClearance](float pointX, float pointY)
        {
            return Distance2d(pointX, pointY, future.X, future.Y) + 0.01f
                >= futureClearance;
        };
        if (futureClearance <= 0.0f
            || !futureSafe(Bot->GetPositionX(), Bot->GetPositionY())
            || !futureSafe(path.GetActualEndPosition().x,
                path.GetActualEndPosition().y)
            || std::any_of(path.GetPath().begin(), path.GetPath().end(),
                [&futureSafe](G3D::Vector3 const& point)
                {
                    return !futureSafe(point.x, point.y);
                }))
            return reject("drudge_anchor_future_encounter_path_unsafe");
        G3D::Vector3 const& actualEnd = path.GetActualEndPosition();
        float const end2d = std::hypot(actualEnd.x - x, actualEnd.y - y);
        float const endZ = std::fabs(actualEnd.z - z);
        BotRaidDrudgeNativePath::PostFloorDecision const postFloorDecision =
            BotRaidDrudgeNativePath::EvaluatePostFloor(
                requireExactEnd, requireSourceUnionSafety, end2d, endZ,
                [this, &path]() { return SourceUnionPathSafe(path); });
        if (postFloorDecision
            == BotRaidDrudgeNativePath::PostFloorDecision::NativeEndpointRejected)
            return reject("drudge_anchor_native_end_rejected:end2d="
                + std::to_string(end2d) + ":endz=" + std::to_string(endZ));
        if (postFloorDecision
            == BotRaidDrudgeNativePath::PostFloorDecision::SourceUnionRejected)
            return reject("drudge_anchor_source_union_path_unsafe");
        if (rejectionOut)
            rejectionOut->clear();
        return true;
    };
    StrictTankRecoveryPath = [this](float x, float y, float z)
    {
        return ComputeStrictTankRecoveryPath(x, y, z);
    };
    RecoveryAnchorReachedFor = [this](uint32 slot)
    {
        return ComputeRecoveryAnchorReached(slot);
    };
    DeclaredRecoveryMemberAnchorFor = [this](uint32 slot) -> MemberAnchor const*
    {
        auto const& anchors =
            Manager.Cohort().Config.ValidationRouteSplitRecoveryMemberAnchors;
        auto const anchor = std::find_if(anchors.begin(), anchors.end(),
            [slot](MemberAnchor const& candidate)
            {
                return candidate.RosterSlot == slot;
            });
        return anchor == anchors.end() ? nullptr : &*anchor;
    };
    UniqueGroupAnchor = [this](uint32 slot) -> std::pair<float, float>
    {
        bool const tankSlot = std::find(
            Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.begin(),
            Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.end(), slot)
            != Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.end();
        bool const dynamicRecovery = IsRecoveryFormationActive();
        MemberAnchor const* anchor = dynamicRecovery || !tankSlot
            ? (tankSlot ? DeclaredRecoveryTankAnchorFor(slot)
                : DeclaredRecoveryMemberAnchorFor(slot))
            : (tankSlot && CombatTankStagingActive()
                ? DeclaredNavigationTankAnchorFor(slot) : DeclaredAnchorFor(slot));
        return anchor ? std::pair<float, float>{ anchor->X, anchor->Y }
                      : std::pair<float, float>{ 0.0f, 0.0f };
    };
    AnchorCandidatesFor = [this](uint32 slot)
    {
        auto const [x, y] = UniqueGroupAnchor(slot);
        std::vector<std::pair<float, float>> candidates{ { x, y } };
        bool const tankSlot = std::find(
            Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.begin(),
            Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.end(), slot)
            != Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.end();
        bool const tankRecovery = tankSlot && IsRecoveryFormationActive();
        if (Sources.size() == 2 && (((!tankSlot || tankRecovery)
                && (!tankSlot || RecoveryTankAnchorPending(slot))
                && IsDynamicGroupRecoveryActive())
            || (!tankSlot && !CombatTankStagingActive())))
        {
            BotRaidDrudgeRecoveryCandidates::Point2d const declaredOrigin{
                x, y };
            BotRaidDrudgeRecoveryCandidates::Point2d const currentOrigin{
                Bot->GetPositionX(), Bot->GetPositionY() };
            bool const currentSourceUnionSafe = SourceUnionSafe(
                currentOrigin.X, currentOrigin.Y);
            BotRaidDrudgeRecoveryCandidates::Point2d const candidateOrigin =
                BotRaidDrudgeRecoveryCandidates::SelectOrigin(
                    declaredOrigin, currentOrigin, tankSlot,
                    IsLandedRushPending(), currentSourceUnionSafe);
            auto const recoveryCandidates = tankSlot
                ? BotRaidDrudgeRecoveryCandidates::BuildCandidates(
                    candidateOrigin,
                    { Sources[0]->GetPositionX(), Sources[0]->GetPositionY() },
                    { Sources[1]->GetPositionX(), Sources[1]->GetPositionY() },
                    { AxisX, AxisY }, LaneSign,
                    Manager.Cohort().Config.ValidationRouteMinimumDistanceYards)
                : BotRaidDrudgeRecoveryCandidates::BuildCandidates(
                    candidateOrigin,
                    { Sources[0]->GetPositionX(), Sources[0]->GetPositionY() },
                    { Sources[1]->GetPositionX(), Sources[1]->GetPositionY() },
                    { Sources[0]->GetHomePosition().GetPositionX(),
                        Sources[0]->GetHomePosition().GetPositionY() },
                    { Sources[1]->GetHomePosition().GetPositionX(),
                        Sources[1]->GetHomePosition().GetPositionY() },
                    { AxisX, AxisY }, LaneSign,
                    Manager.Cohort().Config.ValidationRouteMinimumDistanceYards);
            candidates.clear();
            for (auto const& candidate : recoveryCandidates)
                candidates.emplace_back(candidate.Point.X, candidate.Point.Y);
        }
        if (tankSlot && !CombatTankStagingActive())
            if (MemberAnchor const* navigation = DeclaredNavigationTankAnchorFor(slot))
                candidates.emplace_back(navigation->X, navigation->Y);
        return candidates;
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
        if (memberLaneSign * projection <
            BotRaidDrudgeGeometry::ArrivalAdjustedLaneProjectionMinimum(
                HomeLaneProjectionMinimum,
                Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards,
                IsRecoveryFormationActive(), memberRoster->second.Role == "tank",
                IsEntrancePullActive()))
            return false;
        if (memberRoster->second.Role == "tank"
            && memberSlot != Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots[
                memberLaneA ? 0 : 1])
            return false;
        if (memberRoster->second.Role != "tank")
        {
            bool const cachedAnchorSafe = IsRecoveryFormationActive()
                ? NonTankEntranceEnvelopeSafe(memberSlot,
                    anchorState.ValidationRouteDrudgeAnchorX,
                    anchorState.ValidationRouteDrudgeAnchorY)
                : SourceUnionSafe(anchorState.ValidationRouteDrudgeAnchorX,
                    anchorState.ValidationRouteDrudgeAnchorY);
            if (!cachedAnchorSafe)
                return false;
        }
        float const arrivalTolerance = memberRoster->second.Role == "tank"
            ? Manager.Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards
            : Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards;
        return member->GetExactDist(anchorState.ValidationRouteDrudgeAnchorX,
            anchorState.ValidationRouteDrudgeAnchorY,
            anchorState.ValidationRouteDrudgeAnchorZ) <= arrivalTolerance;
    };
    GroupPositionSafe = [this](Player const* member)
    {
        return ComputeGroupPositionSafe(member);
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
        if (!source || sourceIndex >= Sources.size()
            || source != Sources[sourceIndex])
            return false;
        float const projection = (source->GetPositionX() - MidpointX) * AxisX
            + (source->GetPositionY() - MidpointY) * AxisY;
        if (projectionOut)
            *projectionOut = projection;
        if (IsEntrancePullActive())
            return Sources[0]->IsAlive() && Sources[1]->IsAlive()
                && Sources[0]->GetExactDist2d(Sources[1]) >= LaneSeparation;
        return (sourceIndex == 0 ? -1.0f : 1.0f) * projection
            >= HomeLaneProjectionMinimum;
    };
    SelectPathableDrudgeAnchor = [this](bool tank) -> bool
    {
        std::vector<std::pair<float, float>> const candidates =
            AnchorCandidatesFor(OneBasedSlot);
        if (candidates.empty())
        {
            State.LastPathRejectReason = "drudge_anchor_no_safe_candidate";
            State.LastRecoveryResult = State.LastPathRejectReason;
            return false;
        }
        bool const tankRecovery = tank && IsRecoveryFormationActive()
            && !RecoveryAnchorReachedFor(OneBasedSlot);
        float const laneProjectionMinimum =
            BotRaidDrudgeGeometry::ArrivalAdjustedLaneProjectionMinimum(
                HomeLaneProjectionMinimum,
                Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards,
                IsRecoveryFormationActive(), tank, IsEntrancePullActive());
        BotRaidDrudgeRecoveryCandidates::Constraints const recoveryConstraints{
            { Sources[0]->GetPositionX(), Sources[0]->GetPositionY() },
            { Sources[1]->GetPositionX(), Sources[1]->GetPositionY() },
            { MidpointX, MidpointY }, { AxisX, AxisY },
            Manager.Cohort().Config.ValidationRouteMinimumDistanceYards,
            LaneSign, laneProjectionMinimum };
        float const dynamicLaneProjection = laneProjectionMinimum
            + (tankRecovery
                ? Manager.Cohort().Config.ValidationRouteSplitNativeMeleeStopYards
                    + Manager.Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards
                : 0.0f);
        auto cacheUsable = [&]()
        {
            bool const activeDynamicRecovery = (!tank
                && (IsDynamicGroupRecoveryActive()
                    || (!CombatTankStagingActive()
                        && State.ValidationRouteDrudgeAnchorCandidateIndex > 0)))
                || tankRecovery;
            if (!AnchorCacheMatchesGeneration())
                return false;
            if (BotRaidDrudgeRecoveryCandidates::IsEscapeCandidateIndex(
                    State.ValidationRouteDrudgeAnchorCandidateIndex))
                return false;
            if ((!activeDynamicRecovery || tankRecovery
                || (!tank && IsRecoveryFormationActive()))
                && (State.ValidationRouteDrudgeAnchorCandidateIndex >= candidates.size()
                    || Distance2d(State.ValidationRouteDrudgeAnchorX,
                        State.ValidationRouteDrudgeAnchorY,
                        candidates[State.ValidationRouteDrudgeAnchorCandidateIndex].first,
                        candidates[State.ValidationRouteDrudgeAnchorCandidateIndex].second)
                        > 0.01f))
                return false;
            BotRaidDrudgeRecoveryCandidates::Point2d const cachedPoint{
                State.ValidationRouteDrudgeAnchorX,
                State.ValidationRouteDrudgeAnchorY };
            if (!tank && !NonTankEntranceEnvelopeSafe(OneBasedSlot,
                    cachedPoint.X, cachedPoint.Y))
                return false;
            if (activeDynamicRecovery
                && (!BotRaidDrudgeRecoveryCandidates::LaneSafe(
                        cachedPoint, recoveryConstraints)
                    || (!tank && !SourceUnionSafe(cachedPoint.X, cachedPoint.Y))
                    || !IsRecoveryCandidateSpacingSafe(
                        cachedPoint.X, cachedPoint.Y, tank)
                    || (tankRecovery
                        && !StrictTankRecoveryPath(
                            State.ValidationRouteDrudgeAnchorX,
                            State.ValidationRouteDrudgeAnchorY,
                            State.ValidationRouteDrudgeAnchorZ))))
                return false;
            float const projection =
                (State.ValidationRouteDrudgeAnchorX - MidpointX) * AxisX
                + (State.ValidationRouteDrudgeAnchorY - MidpointY) * AxisY;
            if (LaneSign * projection < laneProjectionMinimum)
                return false;
            if (!tank && !activeDynamicRecovery && (!GroupPositionSafe(Bot)
                || !SourceUnionSafe(State.ValidationRouteDrudgeAnchorX,
                    State.ValidationRouteDrudgeAnchorY)))
                return false;
            if (activeDynamicRecovery)
                return true;
            return IsRecoveryCandidateSpacingSafe(
                State.ValidationRouteDrudgeAnchorX,
                State.ValidationRouteDrudgeAnchorY, tank);
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
            && LaneSign * priorProjection >= laneProjectionMinimum;
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
            : (priorCandidateMatches && SourceUnionSafe(
                State.ValidationRouteDrudgeAnchorX,
                State.ValidationRouteDrudgeAnchorY));
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
            && IsRecoveryCandidateSpacingSafe(
                State.ValidationRouteDrudgeAnchorX,
                State.ValidationRouteDrudgeAnchorY, tank);
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
        bool const nativeSearchDueAtEntry = nowMs
            >= State.ValidationRouteDrudgeAnchorSearchCooldownUntilMs;
        bool const prepullTankFallback = tank && !CombatTankStagingActive();
        auto observeCandidate = [&](uint32 candidateIndex, float candidateX,
            float candidateY, float candidateZ,
            BotRaidDrudgeSpacing::CandidateResult const& spacing,
            bool selected, char const* outcome, char const* reject)
        {
            if (!Charge)
                return;
            BotRaidDrudgeGeometry::Scope const receiptScope{
                Manager.Cohort().AttemptId,
                Manager.Cohort().Raid.WipeGeneration,
                Manager.Party().ValidationRouteGeneration,
                Bot->GetMapId(), Bot->GetInstanceId(),
                Sources[0]->GetGUID().GetRawValue(),
                Sources[1]->GetGUID().GetRawValue() };
            BotRaidDrudgeSpacing::ObserveReseparationCandidate(
                Charge->ReseparationReceipts, receiptScope,
                Bot->GetGUID().GetCounter(), candidateIndex, candidateX,
                candidateY, candidateZ, spacing.Source0Safe,
                spacing.Source1Safe, spacing.LaneSafe, spacing.Spacing.Safe,
                spacing.GroupPositionSafe, selected, outcome, reject, nowMs);
        };
        for (size_t candidateIndex = 0; candidateIndex < candidates.size(); ++candidateIndex)
        {
            bool const dynamicRecovery = IsRecoveryFormationActive();
            MemberAnchor const* candidateAnchor = dynamicRecovery || !tank
                ? (tank ? DeclaredRecoveryTankAnchorFor(OneBasedSlot)
                    : DeclaredRecoveryMemberAnchorFor(OneBasedSlot))
                : (tank && CombatTankStagingActive()
                    ? DeclaredNavigationTankAnchorFor(OneBasedSlot)
                    : (prepullTankFallback && candidateIndex
                        ? DeclaredNavigationTankAnchorFor(OneBasedSlot)
                        : DeclaredAnchorFor(OneBasedSlot)));
            if (!candidateAnchor)
                continue;
            BotRaidDrudgeRecoveryCandidates::Point2d const candidatePoint{
                candidates[candidateIndex].first, candidates[candidateIndex].second };
            bool const dynamicCandidate = (!tank && (IsDynamicGroupRecoveryActive()
                || (!CombatTankStagingActive() && candidateIndex > 0)))
                || tankRecovery;
            BotRaidDrudgeSpacing::CandidateResult const candidateSpacing =
                EvaluateAndRecordCandidateSpacing(
                    uint32(candidateIndex), candidatePoint.X, candidatePoint.Y,
                    tank, dynamicCandidate, dynamicLaneProjection, nowMs);
            bool const combatEnvelopeSafe = tank || NonTankEntranceEnvelopeSafe(
                OneBasedSlot, candidatePoint.X, candidatePoint.Y);
            if ((dynamicCandidate || prepullTankFallback || !CombatTankStagingActive())
                && !candidateSpacing.LaneSafe)
            {
                State.LastPathRejectReason = "drudge_anchor_lane_unsafe";
                State.LastRecoveryResult = State.LastPathRejectReason;
                observeCandidate(uint32(candidateIndex), candidatePoint.X, candidatePoint.Y,
                    candidateAnchor->Z, candidateSpacing, false, "rejected",
                    State.LastPathRejectReason.c_str());
                continue;
            }
            bool const dynamicSpacingSafe = !dynamicCandidate
                || candidateSpacing.Spacing.Safe;
            bool const dynamicSourceSafe = !dynamicCandidate
                || (candidateSpacing.Source0Safe && candidateSpacing.Source1Safe
                    && combatEnvelopeSafe);
            BotRaidDrudgeGeometry::AnchorPathSearchDecision const pathSearch =
                BotRaidDrudgeGeometry::SelectAnchorPathSearch(
                    State.ValidationRouteDrudgeAnchorSearchCooldownUntilMs,
                    nowMs, dynamicSourceSafe, dynamicSpacingSafe);
            State.ValidationRouteDrudgeAnchorSearchCooldownUntilMs =
                pathSearch.RetryAfterMs;
            if (pathSearch.SourceBlocked)
            {
                State.LastPathRejectReason = combatEnvelopeSafe
                    ? "drudge_anchor_source_unsafe"
                    : "drudge_anchor_combat_range_unsafe";
                State.LastRecoveryResult = State.LastPathRejectReason;
                observeCandidate(uint32(candidateIndex), candidatePoint.X, candidatePoint.Y,
                    candidateAnchor->Z, candidateSpacing, false, "rejected",
                    State.LastPathRejectReason.c_str());
                continue;
            }
            if (pathSearch.SpacingBlocked)
            {
                State.LastPathRejectReason = "drudge_anchor_spacing_unsafe";
                State.LastRecoveryResult = State.LastPathRejectReason;
                observeCandidate(uint32(candidateIndex), candidatePoint.X, candidatePoint.Y,
                    candidateAnchor->Z, candidateSpacing, false, "rejected",
                    State.LastPathRejectReason.c_str());
                continue;
            }
            if (!pathSearch.NativePathSearchDue)
            {
                State.LastPathRejectReason = "drudge_anchor_path_retry_cooldown";
                State.LastRecoveryResult = State.LastPathRejectReason;
                observeCandidate(uint32(candidateIndex), candidatePoint.X, candidatePoint.Y,
                    candidateAnchor->Z, candidateSpacing, false, "rejected",
                    State.LastPathRejectReason.c_str());
                continue;
            }
            float candidateZ = candidateAnchor->Z;
            if (dynamicCandidate && candidateIndex > 0
                && !BotRaidDrudgeNativeAnchor::ResolveDynamicCandidateZ(
                    Bot->GetMap(), Bot->GetPhaseShift(), candidatePoint.X,
                    candidatePoint.Y, candidateAnchor->Z, &candidateZ))
            {
                State.LastPathRejectReason = "drudge_anchor_floor_rejected";
                State.LastRecoveryResult = State.LastPathRejectReason;
                observeCandidate(uint32(candidateIndex), candidatePoint.X, candidatePoint.Y,
                    candidateZ, candidateSpacing, false, "rejected",
                    State.LastPathRejectReason.c_str());
                continue;
            }
            std::string rejection;
            if (!StrictNativePath(candidatePoint.X, candidatePoint.Y, candidateZ,
                    tank || IsDynamicGroupRecoveryActive()
                        || (!CombatTankStagingActive() && candidateIndex > 0),
                    dynamicCandidate && !tank, &rejection))
            {
                State.ValidationRouteDrudgeAnchorSearchCooldownUntilMs =
                    candidateIndex + 1 == candidates.size()
                        ? nowMs + DrudgePathRetryHeartbeatMs : 0;
                State.LastPathRejectReason = rejection.empty()
                    ? "drudge_anchor_native_path_rejected" : rejection;
                State.LastRecoveryResult = State.LastPathRejectReason;
                observeCandidate(uint32(candidateIndex), candidatePoint.X, candidatePoint.Y,
                    candidateZ, candidateSpacing, false, "rejected",
                    State.LastPathRejectReason.c_str());
                continue;
            }
            if (tankRecovery
                && !StrictTankRecoveryPath(candidatePoint.X, candidatePoint.Y, candidateZ))
            {
                State.LastPathRejectReason = "drudge_anchor_tank_path_geometry_rejected";
                State.LastRecoveryResult = State.LastPathRejectReason;
                observeCandidate(uint32(candidateIndex), candidatePoint.X, candidatePoint.Y,
                    candidateZ, candidateSpacing, false, "rejected",
                    State.LastPathRejectReason.c_str());
                continue;
            }
            State.ValidationRouteDrudgeAnchorX = candidates[candidateIndex].first;
            State.ValidationRouteDrudgeAnchorY = candidates[candidateIndex].second;
            State.ValidationRouteDrudgeAnchorZ = candidateZ;
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
            observeCandidate(uint32(candidateIndex), candidatePoint.X,
                candidatePoint.Y, candidateZ, candidateSpacing, true,
                "selected_path_proven", "none");
            if (tankRecovery)
            {
                State.ValidationRouteDrudgeRecoveryAnchorPathProven = true;
                State.ValidationRouteDrudgeRecoveryAnchorX = candidatePoint.X;
                State.ValidationRouteDrudgeRecoveryAnchorY = candidatePoint.Y;
                State.ValidationRouteDrudgeRecoveryAnchorZ = candidateZ;
            }
            State.LastPathRejectReason.clear();
            State.LastRecoveryResult.clear();
            return true;
        }
        if (!tank && nativeSearchDueAtEntry
            && SelectProgressiveDrudgeEscape(nowMs))
            return true;
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
        if (IsEntrancePullActive())
        {
            MemberAnchor const* entrance = DeclaredRecoveryTankAnchorFor(slot);
            return entrance && tank->GetExactDist(
                entrance->X, entrance->Y, entrance->Z)
                    <= Manager.Cohort().Config
                        .ValidationRouteSplitTankArrivalToleranceYards;
        }
        bool const laneA = std::find(
            Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
            Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), slot)
            != Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
        float const projection = (tank->GetPositionX() - MidpointX) * AxisX
            + (tank->GetPositionY() - MidpointY) * AxisY;
        return (laneA ? -1.0f : 1.0f) * projection
            >= HomeLaneProjectionMinimum;
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
    ExactRecoveryTankAnchorsReached = [this]
    {
        return ComputeExactRecoveryTankAnchorsReached();
    };
    ExactCombatTankAnchorsReached = [this]
    {
        return ComputeExactCombatTankAnchorsReached();
    };
    ExactCombatTankAnchorsSafe = [this]
    {
        return ComputeExactCombatTankAnchorsReached();
    };
    ExactLiveRecoveryTankPathsPreflighted = [this]
    {
        return ComputeExactLiveRecoveryTankPathsPreflighted();
    };
    return PhaseResult::Continue;
}
}
