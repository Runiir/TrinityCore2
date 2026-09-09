#ifndef TRINITY_BOT_MAGMAW_COORDINATOR_ASSIGNMENTS_H
#define TRINITY_BOT_MAGMAW_COORDINATOR_ASSIGNMENTS_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawRaidPlan.h"

#include <map>

namespace BotEncounter
{
enum class MagmawRosterLiveness : uint8
{
    Unobserved,
    Alive,
    Dead,
    Invalid
};

using MagmawRosterObservations = std::map<uint64, MagmawRosterLiveness>;

MagmawRosterObservations BuildMagmawRosterObservations(
    Blackboard const& board);

MagmawRosterLiveness ObserveMagmawRosterMember(
    MagmawRosterObservations const& observations, ObjectGuid guid);

void ReconcileMagmawAssignments(MagmawRaidPlan& plan,
    MagmawRaidPlan const& before,
    std::vector<MagmawRosterMember> const& members,
    MagmawRosterObservations const& observations, bool authoritative,
    bool scopeChanged, bool mainTankConfigured,
    ObjectGuid configuredMainTank);
}

#endif
