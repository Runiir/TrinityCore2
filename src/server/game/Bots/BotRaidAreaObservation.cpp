#include "Bots/BotRaidAreaObservation.h"

#include "Bots/BotRaidAreaAuthority.h"
#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "Player.h"
#include "Unit.h"

#include <vector>

namespace BotRaidAreaObservation
{
Observation ObserveNearbyProtectedEncounterTarget(Player* owner, Unit const* target)
{
    Observation observation;
    if (!owner || !target
        || !BotRaidAreaAuthority::HasProtectedEncounterEntries(owner->GetGUID().GetRawValue()))
        return observation;

    std::vector<WorldObject*> nearbyObjects;
    Trinity::AllWorldObjectsInRange check(target, ProtectedTargetQueryRadiusYards);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(
        target, nearbyObjects, check);
    Cell::VisitAllObjects(target, searcher, ProtectedTargetQueryRadiusYards);
    return ObserveFirstProtectedTarget(true, true, nearbyObjects,
        [owner, target](WorldObject* object)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            CandidateFacts candidate;
            candidate.IsCreature = creature != nullptr;
            candidate.IsPrimary = creature == target;
            if (!creature || creature == target)
                return candidate;

            candidate.Alive = creature->IsAlive();
            if (!candidate.Alive)
                return candidate;

            candidate.ValidAttackTarget = owner->IsValidAttackTarget(creature);
            if (!candidate.ValidAttackTarget)
                return candidate;

            candidate.Protected = BotRaidAreaAuthority::IsProtectedEncounterTarget(
                owner->GetGUID().GetRawValue(), creature->GetEntry(),
                creature->GetSpawnId(), creature->GetGUID().GetRawValue());
            if (!candidate.Protected)
                return candidate;

            candidate.Guid = creature->GetGUID().GetCounter();
            candidate.Entry = creature->GetEntry();
            candidate.SpawnId = creature->GetSpawnId();
            candidate.PrimaryDistance2d = target->GetExactDist2d(creature);
            candidate.PrimaryDistance3d = target->GetExactDist(creature);
            candidate.PrimaryLineOfSight = target->IsWithinLOSInMap(creature);
            return candidate;
        });
}

bool HasNearbyProtectedEncounterTarget(Player* owner, Unit const* target)
{
    return ObserveNearbyProtectedEncounterTarget(owner, target).ProtectedTargetFound;
}
}
