#include "Bots/Content/Raids/Shared/Trash/BotAdaptiveRaidHazardPlanner.h"

#include "Bots/BotWorldPopulationMgrValidationHazards.h"
#include "Player.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <string>
#include <utility>
#include <vector>

namespace
{
constexpr std::array<float, 5> CandidateAngleOffsets{
    0.0f, float(M_PI_4), -float(M_PI_4),
    float(M_PI_2), -float(M_PI_2) };

float Distance2d(float ax, float ay, float bx, float by)
{
    float const dx = ax - bx;
    float const dy = ay - by;
    return std::sqrt(dx * dx + dy * dy);
}

bool Active(BotEncounter::SpatialRegion const& region, uint64 observedAtMs)
{
    return region.Kind == BotEncounter::RegionKind::Hazard
        && (!region.ExpiresAtMs || region.ExpiresAtMs > observedAtMs)
        && region.Radius > 0.0f;
}

std::string ScopeKey(BotEncounter::Scope const& scope)
{
    return scope.Key();
}
}

namespace BotEncounter
{
HazardPlan PlanSharedHazardExit(Blackboard const& board, ObjectGuid botGuid,
    Player* liveBot)
{
    HazardPlan plan;
    ActorSnapshot const* botActor = board.FindActor(botGuid);
    if (!botActor || !botActor->Alive)
        return plan;

    std::vector<SpatialRegion const*> hazards;
    std::vector<SpatialRegion> activeRegions;
    for (SpatialRegion const& region : board.Regions)
        if (Active(region, board.ObservedAtMs))
        {
            hazards.push_back(&region);
            activeRegions.push_back(region);
        }
    if (hazards.empty())
        return plan;

    float const botX = liveBot ? liveBot->GetPositionX() : botActor->Position.X;
    float const botY = liveBot ? liveBot->GetPositionY() : botActor->Position.Y;
    float const botZ = liveBot ? liveBot->GetPositionZ() : botActor->Position.Z;
    float awayX = 0.0f;
    float awayY = 0.0f;
    float escapeDistance = 4.0f;
    float nearestDistance = std::numeric_limits<float>::max();
    SpatialRegion const* dominant = nullptr;
    uint64 expiry = 0;
    bool insideHazard = false;

    for (SpatialRegion const* region : hazards)
    {
        float const dx = botX - region->Center.X;
        float const dy = botY - region->Center.Y;
        float const distance = Distance2d(botX, botY,
            region->Center.X, region->Center.Y);
        if (distance <= region->Radius)
        {
            insideHazard = true;
            float nx = dx;
            float ny = dy;
            if (distance < 0.01f)
            {
                float const facing = liveBot ? liveBot->GetOrientation()
                    : botActor->Facing;
                nx = std::cos(facing + float(M_PI));
                ny = std::sin(facing + float(M_PI));
            }
            else
            {
                nx /= distance;
                ny /= distance;
            }
            float const weight = std::max(1.0f,
                region->Radius - distance + 1.0f);
            awayX += nx * weight;
            awayY += ny * weight;
            // Measure the move from the bot, not from the hazard center.
            // Remaining clearance plus a fixed margin is enough; endpoint
            // and strict path checks decide whether it clears the union.
            escapeDistance = std::max(escapeDistance,
                std::max(0.0f, region->Radius - distance) + 2.0f);
            if (!dominant || distance < nearestDistance
                || (distance == nearestDistance
                    && region->SourceGuid < dominant->SourceGuid))
            {
                nearestDistance = distance;
                dominant = region;
            }
        }
        if (region->ExpiresAtMs
            && (!expiry || region->ExpiresAtMs < expiry))
            expiry = region->ExpiresAtMs;
    }

    if (!insideHazard || !dominant)
        return plan;

    float const vectorLength = std::sqrt(awayX * awayX + awayY * awayY);
    float baseAngle;
    if (vectorLength > 0.01f)
        baseAngle = std::atan2(awayY, awayX);
    else
    {
        float const facing = liveBot ? liveBot->GetOrientation()
            : botActor->Facing;
        baseAngle = facing + float(M_PI);
    }

    bool pathRejected = false;
    for (float const offset : CandidateAngleOffsets)
    {
        float const angle = baseAngle + offset;
        float const candidateX = botX + std::cos(angle) * escapeDistance;
        float const candidateY = botY + std::sin(angle) * escapeDistance;
        if (!BotWorldValidationHazards::PositionsOutside(
                activeRegions, candidateX, candidateY))
            continue;
        if (liveBot && !BotWorldValidationHazards::PathOutside(
                liveBot, activeRegions, candidateX, candidateY, botZ))
        {
            pathRejected = true;
            continue;
        }

        BotNativeAction::Candidate candidate;
        candidate.Id.ScopeKey = ScopeKey(board.CurrentScope);
        candidate.Id.Strategy = "shared_hazard_movement";
        candidate.Id.Mechanic = "generic_hazard_exit";
        candidate.Id.Actor = dominant->SourceGuid;
        candidate.Id.EventGeneration = dominant->Generation;
        candidate.ActionPriority = BotActionArbitration::Priority::Survival;
        candidate.Utility = 1000.0f - nearestDistance;
        uint64 const boundedExpiry = board.ObservedAtMs + 1000;
        candidate.ExpiresAtMs = expiry
            ? std::min(expiry, boundedExpiry) : boundedExpiry;
        candidate.Action = BotNativeAction::Move{
            candidateX, candidateY, botZ };
        plan.Result = HazardPlanResult::CandidateSelected;
        plan.Candidate = std::move(candidate);
        return plan;
    }

    plan.Result = pathRejected ? HazardPlanResult::PathRejected
        : HazardPlanResult::NoSafeEndpoint;
    return plan;
}
}
