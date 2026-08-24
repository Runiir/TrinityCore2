#ifndef TRINITY_BOT_ADAPTIVE_RAID_HAZARD_PLANNER_H
#define TRINITY_BOT_ADAPTIVE_RAID_HAZARD_PLANNER_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"

#include <optional>

class Player;

namespace BotEncounter
{
enum class HazardPlanResult : uint8
{
    NoActiveHazard,
    NoSafeEndpoint,
    PathRejected,
    CandidateSelected
};

struct HazardPlan
{
    HazardPlanResult Result = HazardPlanResult::NoActiveHazard;
    std::optional<BotNativeAction::Candidate> Candidate;
};

// The optional live player is required for strict native path admission. A
// null player retains a deterministic geometry-only seam for offline replay;
// live callers must pass the loaded bot and therefore cannot bypass mmap/path
// validation.
HazardPlan PlanSharedHazardExit(Blackboard const& board, ObjectGuid botGuid,
    Player* liveBot);
}

#endif
