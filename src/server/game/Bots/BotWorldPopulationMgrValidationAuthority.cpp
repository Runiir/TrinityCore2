#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotRaidAreaAuthority.h"
#include "Creature.h"
#include "Map.h"
#include "Player.h"

#include <algorithm>
#include <vector>

void BotWorldPopulationMgr::ConfigureValidationRouteCombatAuthority(Player* bot) const
{
    if (!bot)
        return;

    uint64 const raidAuthorityOwner = bot->GetGUID().GetRawValue();
    // Freeze every later encounter's complete declared creature surface in
    // the shared offensive authority before any route decision can submit a
    // cast.  Trash nodes are encounters too: their pack entries and split
    // source spawn IDs must be protected while the current pack is alive. The
    // current generation's persisted pack GUIDs are explicitly allowed so an
    // entry reused by adjacent nodes cannot block the live current target.
    std::vector<uint32> protectedEncounterEntries;
    std::vector<uint32> protectedEncounterSpawnIds;
    std::vector<uint64> allowedCurrentPackGuids;
    if (Cohort().Config.ValidationRouteKind != "boss")
    {
        size_t const nextIndex = Party().ValidationRouteManifestIndex + 1;
        for (size_t routeIndex = nextIndex;
            routeIndex < Party().ValidationRouteManifest.size(); ++routeIndex)
        {
            ValidationRouteManifestNode const& nextNode =
                Party().ValidationRouteManifest[routeIndex];
            if (nextNode.Kind != "boss" && nextNode.Kind != "trash")
                continue;
            if (nextNode.TargetEntry)
                protectedEncounterEntries.push_back(nextNode.TargetEntry);
            if (nextNode.OpenerTargetEntry)
                protectedEncounterEntries.push_back(nextNode.OpenerTargetEntry);
            protectedEncounterEntries.insert(protectedEncounterEntries.end(),
                nextNode.TargetEntries.begin(), nextNode.TargetEntries.end());
            protectedEncounterEntries.insert(protectedEncounterEntries.end(),
                nextNode.AlternateTargetEntries.begin(), nextNode.AlternateTargetEntries.end());
            protectedEncounterEntries.insert(protectedEncounterEntries.end(),
                nextNode.AddTargetEntries.begin(), nextNode.AddTargetEntries.end());
            protectedEncounterEntries.insert(protectedEncounterEntries.end(),
                nextNode.PackTargetEntries.begin(), nextNode.PackTargetEntries.end());
            protectedEncounterEntries.insert(protectedEncounterEntries.end(),
                nextNode.ScriptedEventEntries.begin(), nextNode.ScriptedEventEntries.end());
            if (nextNode.TargetSpawnId)
                protectedEncounterSpawnIds.push_back(nextNode.TargetSpawnId);
            protectedEncounterSpawnIds.insert(protectedEncounterSpawnIds.end(),
                nextNode.SplitSourceGuids.begin(), nextNode.SplitSourceGuids.end());
        }

        protectedEncounterEntries.erase(std::remove(
            protectedEncounterEntries.begin(), protectedEncounterEntries.end(), 0),
            protectedEncounterEntries.end());
        std::sort(protectedEncounterEntries.begin(), protectedEncounterEntries.end());
        protectedEncounterEntries.erase(std::unique(
            protectedEncounterEntries.begin(), protectedEncounterEntries.end()),
            protectedEncounterEntries.end());
        protectedEncounterSpawnIds.erase(std::remove(
            protectedEncounterSpawnIds.begin(), protectedEncounterSpawnIds.end(), 0),
            protectedEncounterSpawnIds.end());
        std::sort(protectedEncounterSpawnIds.begin(), protectedEncounterSpawnIds.end());
        protectedEncounterSpawnIds.erase(std::unique(
            protectedEncounterSpawnIds.begin(), protectedEncounterSpawnIds.end()),
            protectedEncounterSpawnIds.end());

        // Scripted-event actors on the current node are native encounter
        // participants.  Do not protect them from this node's damage: the
        // Stonecore Millhouse event intentionally transitions when the party
        // damages him below 50%, after which the native script makes him
        // passive and moves him to the next position.  Future-node scripted
        // actors are already included through nextNode above and remain
        // protected until their own node.
        protectedEncounterEntries.erase(std::remove(
            protectedEncounterEntries.begin(), protectedEncounterEntries.end(), 0),
            protectedEncounterEntries.end());
        std::sort(protectedEncounterEntries.begin(), protectedEncounterEntries.end());
        protectedEncounterEntries.erase(std::unique(
            protectedEncounterEntries.begin(), protectedEncounterEntries.end()),
            protectedEncounterEntries.end());

        if (Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration)
            for (ObjectGuid const& guid : Party().ValidationRoutePackMemberGuids)
                if (Party().ValidationRoutePackDeathGuids.find(guid)
                        == Party().ValidationRoutePackDeathGuids.end()
                    && Party().ValidationRoutePackTransitionGuids.find(guid)
                        == Party().ValidationRoutePackTransitionGuids.end()
                    && (!bot->GetMap()
                        || !IsImmediateNextValidationRouteEncounterMember(
                            bot->GetMap()->GetCreature(guid))))
                    allowedCurrentPackGuids.push_back(guid.GetRawValue());
    }
    BotRaidAreaAuthority::SetProtectedEncounterEntries(
        raidAuthorityOwner, protectedEncounterEntries);
    BotRaidAreaAuthority::SetProtectedEncounterSpawnIds(
        raidAuthorityOwner, protectedEncounterSpawnIds);
    BotRaidAreaAuthority::SetAllowedEncounterGuids(
        raidAuthorityOwner, allowedCurrentPackGuids);
    BotRaidAreaAuthority::SetAllOffenseSuppressed(raidAuthorityOwner, false);
    BotRaidAreaAuthority::Set(raidAuthorityOwner, false);
}
