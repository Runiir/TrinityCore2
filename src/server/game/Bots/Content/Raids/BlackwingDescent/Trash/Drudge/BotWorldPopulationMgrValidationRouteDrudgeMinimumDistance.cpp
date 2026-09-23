#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeMinimumDistanceExit.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrNativePathValidation.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "Map.h"
#include "PathGenerator.h"
#include "Player.h"
#include "Unit.h"
#include "Object.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <string>
#include <vector>
using BotWorldPopulationMgrNativeHelpers::Distance2d;
namespace
{
constexpr float DrudgeMinimumDistanceEndpointToleranceYards = 1.0f;
}

// Minimum-distance exit for ranged and healer bots inside a Drudge's native
// damaging radius.  Split from the Drudge anchor geometry module.
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
    bool const ordinaryEntranceCombat = IsEntrancePullEstablished();
    if (ordinaryEntranceCombat)
        return false;
    bool const specializedLaneMovement = drudgeProfile && !ordinaryEntranceCombat;
    if (!specializedDrudgeRecovery
        && BotRaidDrudgeGeometry::ExactDrudgeLaneOwnsGroupMovement(
            specializedLaneMovement, exactPrepullStaged))
        return false;
    BotRaidDrudgeGeometry::MinimumDistanceOwner const minimumDistanceOwner =
        BotRaidDrudgeGeometry::SelectMinimumDistanceOwner(
            specializedLaneMovement, IsLandedRushPending());
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
    if (!source)
        return false;
    // The contract distance is the exact native damaging radius. Search for
    // an exterior point against the union of every combat-linked source.
    float safeDistance = minimumDistance + 2.0f;
    if (sourceDistance >= minimumDistance)
    {
        // Outside the radius the rotation owns the decision again, but the
        // admitted exit keeps its movement (and lease) until it reaches the
        // safe distance.  The refreshed Mechanic lease restricts the rotation
        // to movement-compatible spells, so no cast parks the bot at the
        // radius edge.  Only the recorded exit continues, never another
        // Mechanic move, and never on a standing bot.
        uint64 const nowMs = BotWorldPopulationMgrSpellSemantics::NowMs();
        BotMovementArbitration::Lease const& lease = State.MovementLease;
        BotRaidDrudgeMinimumDistanceExit::ExitProgress progress;
        progress.ExitRecorded = State.MinimumDistanceExitStartedMs != 0
            && nowMs >= State.MinimumDistanceExitStartedMs;
        progress.LeaseIsThisExit = lease.MovementOwner
                == BotMovementArbitration::Owner::Mechanic
            && BotRaidDrudgeMinimumDistanceExit::SameExitDestination(lease.X,
                lease.Y, State.MinimumDistanceExitX, State.MinimumDistanceExitY);
        progress.LeaseActive = lease.ExpiresAtMs > nowMs;
        progress.Moving = Bot->isMoving() || Bot->HasUnitState(UNIT_STATE_MOVING);
        progress.ElapsedMs = progress.ExitRecorded
            ? nowMs - State.MinimumDistanceExitStartedMs : 0;
        progress.BotSourceDistance = sourceDistance;
        progress.DestinationSourceDistance = std::numeric_limits<float>::max();
        for (Creature const* candidateSource : sources)
            progress.DestinationSourceDistance = std::min(
                progress.DestinationSourceDistance, Distance2d(
                    State.MinimumDistanceExitX, State.MinimumDistanceExitY,
                    candidateSource->GetPositionX(), candidateSource->GetPositionY()));
        progress.SafeDistance = safeDistance;
        if (BotRaidDrudgeMinimumDistanceExit::ContinueAdmittedExit(progress)
            && Manager.MoveBotToPoint(State, Bot, State.MinimumDistanceExitX,
                State.MinimumDistanceExitY, State.MinimumDistanceExitZ, false,
                BotMovementArbitration::Owner::Mechanic,
                BotMovementArbitration::Priority::Mechanic))
        {
            State.LastRecoveryMode = "minimum_distance_exit";
            State.LastRecoveryResult = "exit_continuing";
        }
        else
            State.MinimumDistanceExitStartedMs = 0;
        return false;
    }
    std::vector<BotRaidDrudgeMinimumDistanceExit::Point> sourcePoints;
    sourcePoints.reserve(sources.size());
    for (Creature const* candidateSource : sources)
        sourcePoints.push_back({ candidateSource->GetPositionX(),
            candidateSource->GetPositionY() });
    size_t primaryDirections = 0;
    std::vector<BotRaidDrudgeMinimumDistanceExit::Direction> const directions =
        BotRaidDrudgeMinimumDistanceExit::CandidateDirections(
            { Bot->GetPositionX(), Bot->GetPositionY() }, sourcePoints,
            &primaryDirections);
    // Fallback directions also pass the lane part of the StrictNativePath
    // check: Drudge home lanes and the next encounter's boss.
    BotRaidDrudgeMinimumDistanceExit::FallbackLaneInput laneTemplate;
    laneTemplate.Start = { Bot->GetPositionX(), Bot->GetPositionY() };
    laneTemplate.MinimumDistance = minimumDistance;
    for (Creature const* candidateSource : sources)
        laneTemplate.SourceHomes.push_back({
            candidateSource->GetHomePosition().GetPositionX(),
            candidateSource->GetHomePosition().GetPositionY() });
    auto const& route = Manager.Party().ValidationRouteManifest;
    size_t const nextRouteIndex = Manager.Party().ValidationRouteManifestIndex + 1;
    if (nextRouteIndex < route.size() && route[nextRouteIndex].Kind == "boss"
        && route[nextRouteIndex].MapId == Bot->GetMapId())
    {
        laneTemplate.NextBossKnown = true;
        laneTemplate.NextBoss = { route[nextRouteIndex].X, route[nextRouteIndex].Y };
    }
    using BotRaidDrudgeMinimumDistanceExit::Rejection;
    BotRaidDrudgeMinimumDistanceExit::Attempt attempt;
    attempt.Sources = uint32(sources.size());
    attempt.Directions = uint32(directions.size());
    bool moved = false;
    float safeX = Bot->GetPositionX();
    float safeY = Bot->GetPositionY();
    float safeZ = Bot->GetPositionZ();
    for (size_t directionIndex = 0; directionIndex < directions.size(); ++directionIndex)
    {
        auto const& direction = directions[directionIndex];
        ++attempt.Tried;
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
        {
            attempt.LastPathType = uint32(pathType);
            attempt.Reject(Rejection::PathType);
            continue;
        }
        // A complete corridor can still end at the nearest navmesh point
        // when the requested minimum-distance point is just beyond the
        // platform. MovePoint would otherwise receive the unreachable raw
        // destination and can send the bot off the platform.
        G3D::Vector3 const& actualEnd = path.GetActualEndPosition();
        if (std::hypot(actualEnd.x - candidateX, actualEnd.y - candidateY)
                > DrudgeMinimumDistanceEndpointToleranceYards
            || std::fabs(actualEnd.z - candidateZ) > 1.5f)
        {
            attempt.Reject(Rejection::EndpointMismatch);
            continue;
        }

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
        {
            attempt.Reject(Rejection::UnsafePath);
            continue;
        }
        if (directionIndex >= primaryDirections)
        {
            if (!BotWorldMovement::NativePathFloorsValid(Bot, path, candidateZ, true))
            {
                attempt.Reject(Rejection::PathFloorGap);
                continue;
            }
            BotRaidDrudgeMinimumDistanceExit::FallbackLaneInput lane = laneTemplate;
            lane.End = { actualEnd.x, actualEnd.y };
            for (G3D::Vector3 const& point : path.GetPath())
                lane.Path.push_back({ point.x, point.y });
            if (BotRaidDrudgeMinimumDistanceExit::EvaluateFallbackLane(lane)
                != BotRaidDrudgeMinimumDistanceExit::FallbackLane::Safe)
            {
                attempt.Reject(Rejection::LaneUnsafe);
                continue;
            }
        }
        safeX = candidateX;
        safeY = candidateY;
        safeZ = candidateZ;
        // The executor reports a kept lease only through the recovery
        // result.  Observe this submission's own outcome without losing the
        // previous diagnostic when the executor leaves it untouched.
        std::string const previousRecoveryResult = State.LastRecoveryResult;
        State.LastRecoveryResult.clear();
        moved = Manager.MoveBotToPoint(State, Bot, safeX, safeY, safeZ, false,
            BotMovementArbitration::Owner::Mechanic,
            BotMovementArbitration::Priority::Mechanic);
        bool const leaseRefused = !moved
            && State.LastRecoveryResult == "higher_priority_movement_active";
        if (State.LastRecoveryResult.empty())
            State.LastRecoveryResult = previousRecoveryResult;
        if (moved)
        {
            // Record the admitted exit; a retained move to the same point
            // keeps its original start for the continuation cap.
            if (!State.MinimumDistanceExitStartedMs
                || !BotRaidDrudgeMinimumDistanceExit::SameExitDestination(safeX,
                    safeY, State.MinimumDistanceExitX, State.MinimumDistanceExitY))
                State.MinimumDistanceExitStartedMs =
                    BotWorldPopulationMgrSpellSemantics::NowMs();
            State.MinimumDistanceExitX = safeX;
            State.MinimumDistanceExitY = safeY;
            State.MinimumDistanceExitZ = safeZ;
            break;
        }
        if (leaseRefused)
        {
            attempt.LeaseOwner = uint32(State.MovementLease.MovementOwner);
            attempt.LeasePriority = uint32(State.MovementLease.MovementPriority);
            attempt.Reject(Rejection::LeaseRefused);
            // The kept lease refuses every direction alike.
            break;
        }
        attempt.Reject(Rejection::MoveRejected);
    }
    // Publish why the exit held (or how many directions it rejected first)
    // in the decision trace's recovery fields.
    State.LastRecoveryMode = "minimum_distance_exit";
    State.LastRecoveryResult = attempt.ToString(moved);
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
}
