#ifndef TRINITY_BOT_RAID_AREA_OBSERVATION_H
#define TRINITY_BOT_RAID_AREA_OBSERVATION_H

#include <cstdint>
#include <sstream>
#include <string>

class Player;
class Unit;

namespace BotRaidAreaObservation
{
constexpr float ProtectedTargetQueryRadiusYards = 45.0f;

struct CandidateFacts
{
    bool IsCreature = false;
    bool IsPrimary = false;
    bool Alive = false;
    bool ValidAttackTarget = false;
    bool Protected = false;
    std::uint64_t Guid = 0;
    std::uint32_t Entry = 0;
    std::uint32_t SpawnId = 0;
    float PrimaryDistance2d = 0.0f;
    float PrimaryDistance3d = 0.0f;
    bool PrimaryLineOfSight = false;
};

struct Observation
{
    bool ProtectedTargetFound = false;
    std::uint64_t FirstProtectedTargetGuid = 0;
    std::uint32_t FirstProtectedTargetEntry = 0;
    std::uint32_t FirstProtectedTargetSpawnId = 0;
    float FirstProtectedPrimaryDistance2d = 0.0f;
    float FirstProtectedPrimaryDistance3d = 0.0f;
    bool FirstProtectedPrimaryLineOfSight = false;

    std::string ObservationJson(bool forbidArea) const
    {
        std::ostringstream out;
        out << std::boolalpha
            << "{\"query_radius_yards\":" << ProtectedTargetQueryRadiusYards
            << ",\"protected_target_found\":" << ProtectedTargetFound
            << ",\"first_protected_target_guid\":" << FirstProtectedTargetGuid
            << ",\"first_protected_target_entry\":" << FirstProtectedTargetEntry
            << ",\"first_protected_target_spawn_id\":" << FirstProtectedTargetSpawnId;
        if (ProtectedTargetFound)
        {
            out << ",\"first_protected_primary_distance_2d\":" << FirstProtectedPrimaryDistance2d
                << ",\"first_protected_primary_distance_3d\":" << FirstProtectedPrimaryDistance3d
                << ",\"first_protected_primary_line_of_sight\":" << FirstProtectedPrimaryLineOfSight;
        }
        else
        {
            out << ",\"first_protected_primary_distance_2d\":null"
                << ",\"first_protected_primary_distance_3d\":null"
                << ",\"first_protected_primary_line_of_sight\":null";
        }
        out << ",\"forbid_area\":" << forbidArea
            << ",\"native_chain_selection_status\":\"not_observed\"}";
        return out.str();
    }
};

inline bool ConsiderCandidate(Observation& observation, CandidateFacts const& candidate)
{
    if (!candidate.IsCreature || candidate.IsPrimary || !candidate.Alive
        || !candidate.ValidAttackTarget || !candidate.Protected)
        return false;

    observation.ProtectedTargetFound = true;
    observation.FirstProtectedTargetGuid = candidate.Guid;
    observation.FirstProtectedTargetEntry = candidate.Entry;
    observation.FirstProtectedTargetSpawnId = candidate.SpawnId;
    observation.FirstProtectedPrimaryDistance2d = candidate.PrimaryDistance2d;
    observation.FirstProtectedPrimaryDistance3d = candidate.PrimaryDistance3d;
    observation.FirstProtectedPrimaryLineOfSight = candidate.PrimaryLineOfSight;
    return true;
}

template<class Range, class Project>
Observation ObserveFirstProtectedTarget(bool actorPresent, bool primaryPresent,
    Range const& candidates, Project project)
{
    Observation observation;
    if (!actorPresent || !primaryPresent)
        return observation;
    for (auto const& source : candidates)
    {
        CandidateFacts const candidate = project(source);
        if (ConsiderCandidate(observation, candidate))
            break;
    }
    return observation;
}

Observation ObserveNearbyProtectedEncounterTarget(Player* owner, Unit const* target);
bool HasNearbyProtectedEncounterTarget(Player* owner, Unit const* target);
}

#endif
