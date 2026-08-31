#ifndef TRINITY_BOT_MAGMAW_PARASITE_ROUTE_H
#define TRINITY_BOT_MAGMAW_PARASITE_ROUTE_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotWorldPopulationMgrNativeFloor.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <optional>
#include <vector>

namespace BotEncounter
{
// Strategy supplies this only while the native Massive Crash warning is
// active. The route policy consumes geometry; it does not infer Crash timing.
struct MagmawParasiteCrashObstacle
{
    bool Active = false;
    Vector3 Center;
    Vector3 UnsafeSideAnchor;
    Vector3 SafeSideAnchor;
    float Radius = 0.0f;
};

struct MagmawParasiteMobilityWindow
{
    // Caller derives both values from native spell/event observations. This
    // policy deliberately owns no Mangle/Crash timer.
    std::optional<uint64> TimeToNextMangleCrashMs;
    // Recovery time that casting the currently-ready spell would incur (for
    // example SpellInfo::GetRecoveryTime()), not its current cooldown state.
    uint64 NativeReuseCooldownMs = 0;
};

struct MagmawParasiteRouteFacts
{
    float ActorClearance = std::numeric_limits<float>::infinity();
    bool EmergencyClearance = false;

    bool ReserveDirectionalMobility(
        MagmawParasiteMobilityWindow const& window) const
    {
        return !EmergencyClearance && window.TimeToNextMangleCrashMs
            && *window.TimeToNextMangleCrashMs
                < window.NativeReuseCooldownMs;
    }

    bool MayUseBlinkOrDisengage(
        MagmawParasiteMobilityWindow const& window) const
    {
        return EmergencyClearance
            || !ReserveDirectionalMobility(window);
    }
};

// An immutable route is retained by the semantic lane transition. Point zero
// is either the direct far endpoint or the first far-perimeter arc waypoint;
// the final point is always the selected far endpoint.
struct MagmawParasiteRoutePlan
{
    static constexpr uint8 MaxPoints = 3;

    std::array<Vector3, MaxPoints> Points{};
    uint8 PointCount = 0;
    float AdmittedClearance = 0.0f;
    bool UsesFarPerimeterArc = false;

    bool Empty() const
    {
        return PointCount == 0;
    }

    Vector3 const& Destination() const
    {
        return Points[PointCount - 1];
    }
};

class MagmawParasiteRoute
{
public:
    static constexpr float MinimumClearance = 10.0f;
    static constexpr float PreferredClearance = 16.0f;

    static float Distance2d(Vector3 const& left, Vector3 const& right)
    {
        return std::hypot(left.X - right.X, left.Y - right.Y);
    }

    static float DistanceToSegment(Vector3 const& point,
        Vector3 const& start, Vector3 const& end)
    {
        float const dx = end.X - start.X;
        float const dy = end.Y - start.Y;
        float const lengthSquared = dx * dx + dy * dy;
        if (lengthSquared < 0.0001f)
            return Distance2d(point, start);
        float const projection = std::clamp(((point.X - start.X) * dx
            + (point.Y - start.Y) * dy) / lengthSquared, 0.0f, 1.0f);
        return Distance2d(point, {
            start.X + projection * dx,
            start.Y + projection * dy,
            start.Z });
    }

    static float PointClearance(Vector3 const& point,
        std::vector<Vector3> const& parasites)
    {
        float clearance = std::numeric_limits<float>::infinity();
        for (Vector3 const& parasite : parasites)
            clearance = std::min(clearance, Distance2d(point, parasite));
        return clearance;
    }

    static float SegmentClearance(Vector3 const& start, Vector3 const& end,
        std::vector<Vector3> const& parasites)
    {
        float clearance = std::numeric_limits<float>::infinity();
        for (Vector3 const& parasite : parasites)
            clearance = std::min(clearance,
                DistanceToSegment(parasite, start, end));
        return clearance;
    }

    static MagmawParasiteRouteFacts ObserveFacts(Vector3 const& actor,
        std::vector<Vector3> const& parasites)
    {
        MagmawParasiteRouteFacts facts;
        facts.ActorClearance = PointClearance(actor, parasites);
        facts.EmergencyClearance = facts.ActorClearance < MinimumClearance;
        return facts;
    }

    static bool RemainingRouteSafe(Vector3 const& actor,
        MagmawParasiteRoutePlan const& route, uint8 nextPoint,
        std::vector<Vector3> const& parasites)
    {
        if (route.Empty() || nextPoint >= route.PointCount)
            return false;
        Vector3 previous = actor;
        for (uint8 index = nextPoint; index < route.PointCount; ++index)
        {
            Vector3 const& point = route.Points[index];
            if (PointClearance(point, parasites) < MinimumClearance
                || SegmentClearance(previous, point, parasites)
                    < MinimumClearance)
                return false;
            previous = point;
        }
        return true;
    }

    static bool RemainingRouteAvoidsCrash(Vector3 const& actor,
        MagmawParasiteRoutePlan const& route, uint8 nextPoint,
        std::optional<MagmawParasiteCrashObstacle> const& crash)
    {
        if (!crash || !crash->Active)
            return true;
        if (route.Empty() || nextPoint >= route.PointCount
            || !SafeCrashHalf(route.Destination(), crash))
            return false;
        Vector3 previous = actor;
        for (uint8 index = nextPoint; index < route.PointCount; ++index)
        {
            if (CrashIntersects(previous, route.Points[index], crash))
                return false;
            previous = route.Points[index];
        }
        return true;
    }

    static std::optional<MagmawParasiteRoutePlan> Build(
        Vector3 const& actor, Vector3 const& support,
        Vector3 const& destination,
        std::vector<Vector3> const& parasites,
        std::optional<MagmawParasiteCrashObstacle> const& crash = std::nullopt,
        float supportClearance = 20.0f)
    {
        if (!Finite(actor) || !SameNavigationFloor(actor, support)
            || !SameNavigationFloor(actor, destination)
            || supportClearance <= 0.0f)
            return std::nullopt;

        Vector3 const declaredDestination = destination;
        for (float clearance : { PreferredClearance, MinimumClearance })
        {
            bool const crashIntersects = CrashIntersects(actor,
                declaredDestination, crash);
            if (!crashIntersects
                && SegmentAdmissible(actor, declaredDestination, support,
                    parasites, clearance, supportClearance))
            {
                MagmawParasiteRoutePlan route;
                route.Points[0] = declaredDestination;
                route.PointCount = 1;
                route.AdmittedClearance = clearance;
                return route;
            }

            std::optional<MagmawParasiteRoutePlan> arc = BuildFarArc(actor,
                support, declaredDestination, parasites, crash, clearance,
                supportClearance);
            if (arc)
                return arc;
        }
        return std::nullopt;
    }

private:
    struct Disc
    {
        Vector3 Center;
        float Radius = 0.0f;
    };

    static bool Finite(Vector3 const& point)
    {
        return std::isfinite(point.X) && std::isfinite(point.Y)
            && std::isfinite(point.Z);
    }

    static bool SameNavigationFloor(Vector3 const& actor,
        Vector3 const& point)
    {
        return Finite(point) && std::fabs(point.Z - actor.Z)
            <= BotWorldMovement::NativeFloorTolerance;
    }

    static bool CrashIntersects(Vector3 const& start, Vector3 const& end,
        std::optional<MagmawParasiteCrashObstacle> const& crash)
    {
        return crash && crash->Active && Finite(crash->Center)
            && crash->Radius > 0.0f
            && DistanceToSegment(crash->Center, start, end) < crash->Radius;
    }

    static bool SegmentAdmissible(Vector3 const& start, Vector3 const& end,
        Vector3 const& support, std::vector<Vector3> const& parasites,
        float parasiteClearance, float supportClearance)
    {
        return PointClearance(end, parasites) >= parasiteClearance
            && SegmentClearance(start, end, parasites) >= parasiteClearance
            && SupportCorridorAdmissible(start, end, support,
                supportClearance);
    }

    static bool SupportCorridorAdmissible(Vector3 const& start,
        Vector3 const& end, Vector3 const& support, float clearance)
    {
        float const startDistance = Distance2d(start, support);
        float const segmentDistance = DistanceToSegment(support, start, end);
        if (startDistance >= clearance)
            return segmentDistance >= clearance;

        // A baiter staged too close to the support group must still be able
        // to leave it. Admit only a monotonic egress whose closest point is
        // the current actor position and whose endpoint reaches the corridor.
        return Distance2d(end, support) >= clearance
            && segmentDistance + 0.01f >= startDistance;
    }

    static bool SafeCrashHalf(Vector3 const& point,
        std::optional<MagmawParasiteCrashObstacle> const& crash)
    {
        if (!crash || !crash->Active)
            return true;
        return Distance2d(point, crash->SafeSideAnchor)
            <= Distance2d(point, crash->UnsafeSideAnchor);
    }

    static bool RouteAdmissible(Vector3 const& actor, Vector3 const& support,
        MagmawParasiteRoutePlan const& route,
        std::vector<Vector3> const& parasites,
        std::optional<MagmawParasiteCrashObstacle> const& crash,
        float clearance, float supportClearance)
    {
        Vector3 previous = actor;
        for (uint8 index = 0; index < route.PointCount; ++index)
        {
            Vector3 const& point = route.Points[index];
            if (!SameNavigationFloor(actor, point)
                || !SegmentAdmissible(previous, point, support, parasites,
                    clearance, supportClearance))
                return false;
            if (crash && crash->Active && crash->Radius > 0.0f
                && DistanceToSegment(crash->Center, previous, point)
                    < crash->Radius)
                return false;
            previous = point;
        }
        return SafeCrashHalf(route.Destination(), crash);
    }

    static std::optional<MagmawParasiteRoutePlan> BuildFarArc(
        Vector3 const& actor, Vector3 const& support,
        Vector3 const& destination, std::vector<Vector3> const& parasites,
        std::optional<MagmawParasiteCrashObstacle> const& crash,
        float clearance, float supportClearance)
    {
        float dx = destination.X - actor.X;
        float dy = destination.Y - actor.Y;
        float const length = std::hypot(dx, dy);
        if (length < 0.01f)
            return std::nullopt;
        dx /= length;
        dy /= length;
        float const normalX = -dy;
        float const normalY = dx;

        Disc blocker;
        if (CrashIntersects(actor, destination, crash))
            blocker = { crash->Center, crash->Radius };
        else
        {
            float nearest = std::numeric_limits<float>::infinity();
            for (Vector3 const& parasite : parasites)
            {
                float const distance = DistanceToSegment(parasite, actor,
                    destination);
                if (distance < clearance && distance < nearest)
                {
                    nearest = distance;
                    blocker = { parasite, clearance };
                }
            }
            if (!std::isfinite(nearest))
            {
                if (DistanceToSegment(support, actor, destination)
                    >= supportClearance)
                    return std::nullopt;
                blocker = { support, supportClearance };
            }
        }

        float const positiveSupportDistance = Distance2d(support, {
            blocker.Center.X + normalX, blocker.Center.Y + normalY,
            destination.Z });
        float const negativeSupportDistance = Distance2d(support, {
            blocker.Center.X - normalX, blocker.Center.Y - normalY,
            destination.Z });
        std::array<float, 2> sides = positiveSupportDistance
                >= negativeSupportDistance
            ? std::array<float, 2>{ 1.0f, -1.0f }
            : std::array<float, 2>{ -1.0f, 1.0f };

        for (float side : sides)
            for (float scale : { 2.0f, 3.0f, 4.0f })
            {
                float const perimeter = std::max(blocker.Radius, clearance)
                    * scale;
                MagmawParasiteRoutePlan route;
                route.Points[0] = {
                    blocker.Center.X - dx * perimeter
                        + normalX * side * perimeter,
                    blocker.Center.Y - dy * perimeter
                        + normalY * side * perimeter,
                    destination.Z };
                route.Points[1] = {
                    blocker.Center.X + dx * perimeter
                        + normalX * side * perimeter,
                    blocker.Center.Y + dy * perimeter
                        + normalY * side * perimeter,
                    destination.Z };
                route.Points[2] = destination;
                route.PointCount = 3;
                route.AdmittedClearance = clearance;
                route.UsesFarPerimeterArc = true;
                if (RouteAdmissible(actor, support, route, parasites, crash,
                        clearance, supportClearance))
                    return route;
            }
        return std::nullopt;
    }
};
}

#endif
