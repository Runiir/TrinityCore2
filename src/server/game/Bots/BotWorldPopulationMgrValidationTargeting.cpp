#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "PathGenerator.h"
#include "Pet.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>
#include <memory>
#include <sstream>
#include <string>
#include <unordered_set>
#include <vector>

using BotWorldPopulationMgrNativeHelpers::Distance2d;
using BotWorldPopulationMgrSpellSemantics::NowMs;
using BotWorldPopulationMgrSpellSemantics::SpellHasHostileMultiTargetSemantics;

BotWorldPopulationMgr::ValidationRouteTargetingContext
BotWorldPopulationMgr::BuildValidationRouteTargetingContext(
    WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, bool discoveryLeg)
{
    ValidationRouteTargetingContext result;
    auto routeEngageRange = [=, this, &state, &power](Player* engageBot, Unit const* engageTarget, uint32 spellId) -> float
    {
        if (SpellInfo const* spellInfo = spellId ? sSpellMgr->GetSpellInfo(spellId) : nullptr)
            return std::max(5.0f, spellInfo->GetMaxRange(false));

        std::string role = GetDungeonRole(engageBot);
        BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(engageBot, role.c_str());
        for (BotActionProfileSpell const& spell : profile.Spells)
        {
            if (!spell.SpellId || !engageBot->HasSpell(spell.SpellId))
                continue;

            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spell.SpellId);
            if (!spellInfo)
                continue;

            if (engageTarget && (spell.DamageWeight > 0.0f || spell.ThreatWeight > 0.0f || spell.ProgressionWeight > 0.0f))
                return std::max(5.0f, spellInfo->GetMaxRange(false));
        }

        return 5.0f;
    };
    auto currentValidationRouteTargetSpawnId = [=, this, &state, &power]() -> ObjectGuid::LowType
    {
        if (Party().ValidationRouteManifestIndex >= Party().ValidationRouteManifest.size())
            return 0;
        return Party().ValidationRouteManifest[Party().ValidationRouteManifestIndex].TargetSpawnId;
    };
    auto isFutureCanonicalValidationRouteSource = [=, this, &state, &power](Creature const* creature) -> bool
    {
        if (!creature)
            return false;
        for (size_t routeIndex = Party().ValidationRouteManifestIndex + 1;
            routeIndex < Party().ValidationRouteManifest.size(); ++routeIndex)
        {
            ValidationRouteManifestNode const& futureNode = Party().ValidationRouteManifest[routeIndex];
            if (futureNode.Kind != "trash" || !futureNode.TargetSpawnId)
                continue;
            if (creature->GetSpawnId() == futureNode.TargetSpawnId)
                return true;
        }
        return false;
    };
    auto wouldPullProtectedFutureValidationRouteSource = [=, this, &state, &power](Creature const* creature) -> bool
    {
        if (!bot || !bot->GetMap() || !creature || creature->GetMap() != bot->GetMap())
            return false;

        float const futureSourceSocialGuardYards = std::max(35.0f,
            Cohort().Config.ValidationRouteClusterRadiusYards);
        for (size_t routeIndex = Party().ValidationRouteManifestIndex + 1;
            routeIndex < Party().ValidationRouteManifest.size(); ++routeIndex)
        {
            ValidationRouteManifestNode const& futureNode = Party().ValidationRouteManifest[routeIndex];
            if (futureNode.Kind != "trash" || !futureNode.TargetSpawnId || futureNode.MapId != bot->GetMapId())
                continue;

            if (creature->GetSpawnId() == futureNode.TargetSpawnId)
                return true;
            Creature* futureSource = bot->GetMap()->GetCreatureBySpawnId(futureNode.TargetSpawnId);
            if (futureSource && futureSource->IsAlive() && futureSource->GetHealth()
                && creature->GetExactDist(futureSource) <= futureSourceSocialGuardYards)
                return true;
            CreatureData const* futureSourceData = sObjectMgr->GetCreatureData(futureNode.TargetSpawnId);
            if (futureSourceData && futureSourceData->mapId == bot->GetMapId()
                && Distance2d(
                    creature->GetPositionX(),
                    creature->GetPositionY(),
                    futureSourceData->spawnPoint.GetPositionX(),
                    futureSourceData->spawnPoint.GetPositionY()) <= futureSourceSocialGuardYards)
                return true;
        }
        return false;
    };
    auto isValidationRouteEntry = [=, this, &state, &power](uint32 entry) -> bool
    {
        if (!entry)
            return false;
        if ((Cohort().Config.ValidationRouteTargetEntry && entry == Cohort().Config.ValidationRouteTargetEntry)
            || (Cohort().Config.ValidationRouteOpenerTargetEntry && entry == Cohort().Config.ValidationRouteOpenerTargetEntry))
            return true;
        return std::find(Cohort().Config.ValidationRouteAlternateTargetEntries.begin(), Cohort().Config.ValidationRouteAlternateTargetEntries.end(), entry) != Cohort().Config.ValidationRouteAlternateTargetEntries.end();
    };
    auto isValidationRouteAlternateTargetEntry = [=, this, &state, &power](uint32 entry) -> bool
    {
        if (!entry)
            return false;
        return std::find(Cohort().Config.ValidationRouteAlternateTargetEntries.begin(), Cohort().Config.ValidationRouteAlternateTargetEntries.end(), entry) != Cohort().Config.ValidationRouteAlternateTargetEntries.end();
    };
    auto isValidationRouteCombatEntry = [=, this, &state, &power](uint32 entry) -> bool
    {
        if (!entry)
            return false;
        if (isValidationRouteAlternateTargetEntry(entry))
            return true;
        if (Cohort().Config.ValidationRouteOpenerTargetEntry && entry == Cohort().Config.ValidationRouteOpenerTargetEntry)
            return true;
        if (Cohort().Config.ValidationRouteTargetEntry && entry == Cohort().Config.ValidationRouteTargetEntry)
        {
            bool targetIsActivationController = Cohort().Config.ValidationRouteActivationActionEntry
                && entry == Cohort().Config.ValidationRouteActivationActionEntry
                && !Cohort().Config.ValidationRouteAlternateTargetEntries.empty();
            return !targetIsActivationController;
        }
        return false;
    };
    auto isValidationRoutePackEntry = [=, this, &state, &power](uint32 entry) -> bool
    {
        if (!entry)
            return false;
        if (!Cohort().Config.ValidationRoutePackTargetEntries.empty())
            return std::find(Cohort().Config.ValidationRoutePackTargetEntries.begin(), Cohort().Config.ValidationRoutePackTargetEntries.end(), entry) != Cohort().Config.ValidationRoutePackTargetEntries.end();
        return isValidationRouteCombatEntry(entry);
    };
    auto isValidationRouteScriptTarget = [=, this, &state, &power](Creature const* creature) -> bool
    {
        if (!creature)
            return false;

        if (Cohort().Config.ValidationRouteKind == "boss")
            return isValidationRouteEntry(creature->GetEntry());
        if (discoveryLeg)
            return Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
                && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID()) != Party().ValidationRoutePackMemberGuids.end();
        if (!isValidationRoutePackEntry(creature->GetEntry()))
            return false;

        bool persistedPackMember = Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
            && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID()) != Party().ValidationRoutePackMemberGuids.end();
        if (!Party().ValidationRoutePackObservedEngagement
            && wouldPullProtectedFutureValidationRouteSource(creature))
            return false;

        ObjectGuid::LowType canonicalSpawnId = currentValidationRouteTargetSpawnId();
        if (canonicalSpawnId
            && creature->GetEntry() == Cohort().Config.ValidationRouteTargetEntry
            && !Party().ValidationRoutePackObservedEngagement
            && creature->GetSpawnId() != canonicalSpawnId)
            return false;

        float radius = Cohort().Config.ValidationRouteClusterRadiusYards > 1.0f ? Cohort().Config.ValidationRouteClusterRadiusYards : 90.0f;
        return creature->GetMapId() == bot->GetMapId()
            && creature->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ) <= radius;
    };
    auto isValidationRouteCombatTarget = [=, this, &state, &power](Creature const* creature) -> bool
    {
        if (!creature)
            return false;

        return isValidationRouteCombatEntry(creature->GetEntry());
    };
    auto hasStrictPathToValidationRouteTarget = [=, this, &state, &power](Unit const* unit) -> bool
    {
        if (!bot || !unit || !bot->GetMap() || unit->GetMap() != bot->GetMap())
            return false;

        PathGenerator path(bot);
        bool pathOk = path.CalculatePath(unit->GetPositionX(), unit->GetPositionY(), unit->GetPositionZ(), false);
        PathType pathType = path.GetPathType();
        return pathOk
            && !(pathType & PATHFIND_NOPATH)
            && !(pathType & PATHFIND_NOT_USING_PATH)
            && !(pathType & PATHFIND_INCOMPLETE)
            && !(pathType & PATHFIND_SHORTCUT)
            && !(pathType & PATHFIND_FARFROMPOLY);
    };
    auto resolvedScriptedTransitionAuraId = [=, this, &state, &power](Creature const* creature) -> uint32
    {
        if (!creature || creature->GetVictim())
            return 0;
        auto entryItr = std::find(Cohort().Config.ValidationRouteScriptedEventEntries.begin(), Cohort().Config.ValidationRouteScriptedEventEntries.end(), creature->GetEntry());
        if (entryItr == Cohort().Config.ValidationRouteScriptedEventEntries.end())
            return 0;
        size_t index = std::distance(Cohort().Config.ValidationRouteScriptedEventEntries.begin(), entryItr);
        if (index >= Cohort().Config.ValidationRouteScriptedEventTransitionAuraIds.size())
            return 0;
        uint32 auraId = Cohort().Config.ValidationRouteScriptedEventTransitionAuraIds[index];
        if (!auraId || !creature->HasAura(auraId))
            return 0;
        if (Cohort().Config.ValidationRouteScriptedEventRequirePassive && !creature->HasReactState(REACT_PASSIVE))
            return 0;
        return auraId;
    };
    auto isPendingScriptedEventEntry = [=, this, &state, &power](Creature const* creature) -> bool
    {
        if (!creature || !Cohort().Config.ValidationRouteScriptedEventRequirePassive)
            return false;

        auto entryItr = std::find(Cohort().Config.ValidationRouteScriptedEventEntries.begin(), Cohort().Config.ValidationRouteScriptedEventEntries.end(), creature->GetEntry());
        if (entryItr == Cohort().Config.ValidationRouteScriptedEventEntries.end())
            return false;

        // A configured scripted-event creature is not ordinary route trash until
        // its native transition aura/passive state is observed.  In particular,
        // Millhouse can be attackable and pathable in the opening corridor while
        // still being the future Corborus event actor; treating it as discovery
        // trash causes the tank to pull the event out of order.
        return resolvedScriptedTransitionAuraId(creature) == 0;
    };
    auto isCurrentDiscoveryScriptedEventTarget = [=, this, &state, &power](Creature const* creature) -> bool
    {
        if (!discoveryLeg || !creature || !isPendingScriptedEventEntry(creature))
            return false;

        // A configured actor such as Millhouse is a native script participant,
        // not an opening trash target.  It becomes eligible only after the
        // discovery scan has observed real native combat/victim/health-loss
        // evidence and enrolled its GUID in this generation's pack ledger.
        // This keeps the party on the real corridor pulls and lets the next
        // boss node enter the native Corborus area trigger.
        return Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
            && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID())
                != Party().ValidationRoutePackMemberGuids.end();
    };
    auto isEligibleTrashClusterMob = [=, this, &state, &power](Creature const* creature) -> bool
    {
        if (!bot || !creature || !creature->IsAlive() || !creature->GetHealth() || !bot->IsValidAttackTarget(creature))
            return false;
        if (Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
            && Party().ValidationRoutePackTransitionGuids.find(creature->GetGUID()) != Party().ValidationRoutePackTransitionGuids.end())
            return false;
        if (Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID()) != Party().ValidationRouteFinalTransitionGuids.end())
            return false;
        if (isPendingScriptedEventEntry(creature))
            return false;
        if (resolvedScriptedTransitionAuraId(creature))
            return false;
        if (creature->IsInEvadeMode() || creature->HasUnitState(UNIT_STATE_EVADE))
            return false;
        if (creature->IsDungeonBoss() || creature->isWorldBoss())
            return false;
        if (creature->IsCritter() || creature->IsPet() || creature->IsTotem() || creature->IsSummon() || creature->IsGuardian() || !creature->GetOwnerGUID().IsEmpty())
            return false;
        bool persistedPackMember = Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
            && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID()) != Party().ValidationRoutePackMemberGuids.end();
        bool focusedDiscoveryCandidate = discoveryLeg && Party().ValidationRouteFocusGuid == creature->GetGUID();
        if (!persistedPackMember && !focusedDiscoveryCandidate && (discoveryLeg || !isValidationRoutePackEntry(creature->GetEntry())))
            return false;
        if (!Party().ValidationRoutePackObservedEngagement
            && wouldPullProtectedFutureValidationRouteSource(creature))
            return false;

        ObjectGuid::LowType canonicalSpawnId = currentValidationRouteTargetSpawnId();
        if (!persistedPackMember
            && canonicalSpawnId
            && creature->GetEntry() == Cohort().Config.ValidationRouteTargetEntry
            && !Party().ValidationRoutePackObservedEngagement
            && creature->GetSpawnId() != canonicalSpawnId)
            return false;

        float radius = discoveryLeg || persistedPackMember ? std::numeric_limits<float>::max()
            : (Cohort().Config.ValidationRouteClusterRadiusYards > 1.0f ? Cohort().Config.ValidationRouteClusterRadiusYards : 90.0f);
        bool pullable = bot->IsWithinLOSInMap(creature)
            && bot->GetExactDist(creature) <= routeEngageRange(bot, creature, 0);
        return creature->GetMapId() == bot->GetMapId()
            && creature->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ) <= radius
            && (hasStrictPathToValidationRouteTarget(creature) || pullable);
    };
    auto forEachActiveValidationCohortCombatCreature = [=, this, &state, &power](auto&& visitor) -> void
    {
        if (!bot || !bot->GetMap())
            return;

        std::unordered_set<ObjectGuid> visited;
        for (WorldBotState const& cohortState : Party().Bots)
        {
            Player* member = GetLoadedBot(cohortState);
            if (!member || !member->IsInWorld() || member->GetMap() != bot->GetMap())
                continue;

            for (auto const& pair : member->GetCombatManager().GetPvECombatRefs())
            {
                auto const* combatReference = pair.second;
                if (!combatReference || combatReference->IsSuppressedFor(member))
                    continue;

                Unit* other = combatReference->GetOther(member);
                if (!other || combatReference->IsSuppressedFor(other))
                    continue;

                Creature* creature = other->ToCreature();
                if (!creature || creature->GetMap() != bot->GetMap() || !visited.insert(creature->GetGUID()).second)
                    continue;
                visitor(creature);
            }
        }
    };
    auto isValidationCohortCombatLinked = [=, this, &state, &power](Creature const* creature) -> bool
    {
        if (!bot || !bot->GetMap() || !creature || creature->GetMap() != bot->GetMap())
            return false;

        for (WorldBotState const& cohortState : Party().Bots)
        {
            Player* member = GetLoadedBot(cohortState);
            if (!member || !member->IsInWorld() || member->GetMap() != bot->GetMap())
                continue;

            auto const& combatReferences = member->GetCombatManager().GetPvECombatRefs();
            auto referenceItr = combatReferences.find(creature->GetGUID());
            if (referenceItr == combatReferences.end())
                continue;
            auto const* combatReference = referenceItr->second;
            if (combatReference && !combatReference->IsSuppressedFor(member) && !combatReference->IsSuppressedFor(creature))
                return true;
        }
        return false;
    };
    auto isImmediateNextValidationRouteBossTarget = [=, this, &state, &power](Creature const* creature) -> bool
    {
        return IsImmediateNextValidationRouteBossTarget(creature);
    };
    auto isImmediateNextValidationRouteEncounterMember = [=, this, &state, &power](Creature const* creature) -> bool
    {
        return IsImmediateNextValidationRouteEncounterMember(creature);
    };
    auto validationPartyHasActiveCombat = [=, this, &state, &power](bool transferImmediateNextEncounter = false) -> bool
    {
        bool active = false;
        forEachActiveValidationCohortCombatCreature([&](Creature const* creature)
        {
            if (!creature || !creature->IsAlive() || !creature->GetHealth())
                return;
            if (Party().ValidationRoutePendingFinalTransitionGuids.find(creature->GetGUID()) != Party().ValidationRoutePendingFinalTransitionGuids.end()
                || Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID()) != Party().ValidationRouteFinalTransitionGuids.end())
                return;
            if (Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
                && (Party().ValidationRoutePackDeathGuids.find(creature->GetGUID()) != Party().ValidationRoutePackDeathGuids.end()
                    || Party().ValidationRoutePackTransitionGuids.find(creature->GetGUID()) != Party().ValidationRoutePackTransitionGuids.end()))
                return;
            // Preserve active next-encounter combat while the current pack is
            // alive. Once that pack is clear, the terminal caller transfers the
            // manifest-classified boss and listed adds to their own generation.
            if (transferImmediateNextEncounter
                && isImmediateNextValidationRouteEncounterMember(creature))
                return;
            active = true;
        });
        return active;
    };
    auto isBoundedTerminalPartyCombatTarget = [=, this, &state, &power](Creature const* creature) -> bool
    {
        if (!bot || !creature || !creature->IsAlive() || !creature->GetHealth()
            || creature->GetMap() != bot->GetMap() || !bot->IsValidAttackTarget(creature))
            return false;
        if (Party().ValidationRoutePendingFinalTransitionGuids.find(creature->GetGUID()) != Party().ValidationRoutePendingFinalTransitionGuids.end()
            || Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID()) != Party().ValidationRouteFinalTransitionGuids.end()
            || isImmediateNextValidationRouteEncounterMember(creature)
            || creature->IsDungeonBoss() || creature->isWorldBoss())
            return false;
        if (!isValidationCohortCombatLinked(creature))
            return false;

        // This is only a bounded resolver for a terminal node whose normal
        // pack is already dead. Keep it inside the same 120-yard
        // prerequisite envelope used by route combat, and require either
        // current LOS or a strict path before it can become shared focus.
        if (creature->GetExactDist(
                Cohort().Config.ValidationRouteX,
                Cohort().Config.ValidationRouteY,
                Cohort().Config.ValidationRouteZ) > 120.0f)
            return false;
        return bot->IsWithinLOSInMap(creature)
            || hasStrictPathToValidationRouteTarget(creature);
    };
    auto findBoundedTerminalPartyCombatTarget = [=, this, &state, &power]() -> Unit*
    {
        Creature* best = nullptr;
        uint8 bestPriority = 0;
        float bestDistance = std::numeric_limits<float>::max();
        uint64 bestGuid = std::numeric_limits<uint64>::max();
        forEachActiveValidationCohortCombatCreature([&](Creature* creature)
        {
            if (!isBoundedTerminalPartyCombatTarget(creature))
                return;

            Unit* victim = creature->GetVictim();
            Player* victimPlayer = victim ? victim->ToPlayer() : nullptr;
            std::string victimRole = victimPlayer ? GetDungeonRole(victimPlayer) : "";
            uint8 priority = victimRole == "healer" ? 3
                : victimPlayer && victimRole != "tank" ? 2
                : victim != bot ? 1 : 0;
            float distance = bot->GetExactDist(creature);
            uint64 guid = creature->GetGUID().GetRawValue();
            if (!best || priority > bestPriority
                || (priority == bestPriority && distance < bestDistance)
                || (priority == bestPriority && distance == bestDistance && guid < bestGuid))
            {
                best = creature;
                bestPriority = priority;
                bestDistance = distance;
                bestGuid = guid;
            }
        });
        return best;
    };
    auto tryCanonicalValidationRouteBossRecovery = [=, this, &state, &power](std::string& recoveryResult, bool& recoveryInitiated) -> bool
    {
        recoveryResult.clear();
        recoveryInitiated = false;
        if (!bot || !bot->GetMap()
            || Cohort().Config.ValidationRouteKind != "boss"
            || std::string(GetDungeonRole(bot)) != "tank"
            || !Cohort().Config.ValidationRouteTargetEntry
            || Party().ValidationRouteManifestIndex >= Party().ValidationRouteManifest.size())
            return false;

        uint32 deathParticipants = 0;
        uint32 recentDeathCount = 0;
        for (WorldBotState const& cohortState : Party().Bots)
            if (cohortState.RecentDeathCount)
            {
                ++deathParticipants;
                recentDeathCount += cohortState.RecentDeathCount;
            }
        if (deathParticipants < 2 || recentDeathCount < 2
            || validationPartyHasActiveCombat(false))
            return false;

        // Boss recovery is always owned by the encounter script and ordinary
        // player lifecycle, regardless of map type. Never force a spawn,
        // advance a respawn clock, or load a creature from DB for autonomy.
        recoveryResult = "native_boss_recovery_pending";
        std::ostringstream raw;
        raw << "{\"base\":" << BuildRawJson(bot, nullptr)
            << ",\"native_recovery_gate\":{\"authority\":\"native_encounter\""
            << ",\"assistance\":\"none\",\"direct_respawn\":false"
            << ",\"direct_state_manufacture\":false"
            << ",\"death_participants\":" << deathParticipants
            << ",\"recent_death_count\":" << recentDeathCount
            << "}}";
        std::string semantic = BuildSemanticJson(bot, nullptr,
            "native_boss_recovery", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_recovery", nullptr,
            recoveryResult.c_str(), raw.str().c_str(), semantic.c_str(),
            float(deathParticipants), recentDeathCount);
        return true;
    };
    auto isNaturalForwardHostile = [=, this, &state, &power](Creature const* creature) -> bool
    {
        if (!bot || !creature || !creature->IsAlive() || !creature->GetHealth() || creature->GetMap() != bot->GetMap())
            return false;
        if (!bot->IsValidAttackTarget(creature) || creature->IsInEvadeMode() || creature->HasUnitState(UNIT_STATE_EVADE))
            return false;
        if (isPendingScriptedEventEntry(creature))
            return false;
        if (resolvedScriptedTransitionAuraId(creature))
            return false;
        if (creature->IsDungeonBoss() || creature->isWorldBoss() || creature->IsCivilian() || creature->IsNeutralToAll() || creature->HasReactState(REACT_PASSIVE)
            || Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID()) != Party().ValidationRouteFinalTransitionGuids.end())
            return false;
        if (creature->IsCritter() || creature->IsPet() || creature->IsTotem() || creature->IsSummon() || creature->IsGuardian() || !creature->GetOwnerGUID().IsEmpty())
            return false;
        return hasStrictPathToValidationRouteTarget(creature);
    };
    auto findForwardDiscoveryTarget = [=, this, &state, &power]() -> Unit*
    {
        if (!discoveryLeg || !bot || std::string(GetDungeonRole(bot)) != "tank")
            return nullptr;

        PathGenerator path(bot);
        if (!path.CalculatePath(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ, false))
            return nullptr;
        PathType pathType = path.GetPathType();
        if ((pathType & PATHFIND_NOPATH) || (pathType & PATHFIND_NOT_USING_PATH) || (pathType & PATHFIND_INCOMPLETE)
            || (pathType & PATHFIND_SHORTCUT) || (pathType & PATHFIND_FARFROMPOLY))
            return nullptr;
        Movement::PointsArray const& points = path.GetPath();
        if (points.size() < 2)
            return nullptr;

        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, 220.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, 220.0f);

        Creature* best = nullptr;
        uint32 bestAlongPath = std::numeric_limits<uint32>::max();
        uint64 bestGuid = std::numeric_limits<uint64>::max();
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!isNaturalForwardHostile(creature))
                continue;

            G3D::Vector3 position(creature->GetPositionX(), creature->GetPositionY(), creature->GetPositionZ());
            float corridorRadius = creature->GetAttackDistance(bot) + creature->GetCombatReach() + bot->GetCombatReach();
            float cumulative = 0.0f;
            float candidateAlongPath = std::numeric_limits<float>::max();
            for (size_t index = 1; index < points.size(); ++index)
            {
                G3D::Vector3 segment = points[index] - points[index - 1];
                float segmentLengthSquared = segment.squaredLength();
                if (segmentLengthSquared <= 0.0001f)
                    continue;
                float segmentLength = std::sqrt(segmentLengthSquared);
                float projection = std::clamp((position - points[index - 1]).dot(segment) / segmentLengthSquared, 0.0f, 1.0f);
                G3D::Vector3 nearest = points[index - 1] + segment * projection;
                if (projection > 0.0f && (position - nearest).length() <= corridorRadius)
                    candidateAlongPath = std::min(candidateAlongPath, cumulative + segmentLength * projection);
                cumulative += segmentLength;
            }
            if (candidateAlongPath == std::numeric_limits<float>::max())
                continue;

            uint32 alongPath = uint32(std::lround(candidateAlongPath * 100.0f));
            uint64 guid = creature->GetGUID().GetRawValue();
            if (!best || alongPath < bestAlongPath || (alongPath == bestAlongPath && guid < bestGuid))
            {
                best = creature;
                bestAlongPath = alongPath;
                bestGuid = guid;
            }
        }

        return best;
    };
    auto isValidationRouteObjectiveTarget = [=, this, &state, &power](Creature const* creature) -> bool
    {
        if (!creature)
            return false;

        if (Cohort().Config.ValidationRouteKind != "boss")
        {
            // The current discovery node owns its declared scripted actor.
            // It is intentionally not ordinary trash (and therefore is not
            // eligible for the generic cluster predicate), but the tank must
            // be allowed to open the native scripted handoff once it is
            // pathable.  Future-node actors never satisfy this current-node
            // predicate because the helper is bound to this node's entries.
            if (isCurrentDiscoveryScriptedEventTarget(creature))
                return true;
            return isEligibleTrashClusterMob(creature);
        }

        // A boss node's explicit add list is part of that node's hostile
        // authority. Treating a listed add as an undeclared prerequisite made
        // the fail-closed route adapter monopolize every tick while Corborus
        // was burrowed, even though the boss mechanic adapter was prepared to
        // switch to entry 43917. Keep arbitrary corridor targets masked, but
        // allow declared adds to flow through the typed mechanic policy.
        return isValidationRouteScriptTarget(creature)
            || std::find(Cohort().Config.ValidationRouteAddTargetEntries.begin(),
                Cohort().Config.ValidationRouteAddTargetEntries.end(),
                creature->GetEntry())
                != Cohort().Config.ValidationRouteAddTargetEntries.end();
    };
    auto findCurrentDiscoveryScriptedEventTarget = [=, this, &state, &power]() -> Unit*
    {
        if (!discoveryLeg || !bot || !bot->GetMap() || std::string(GetDungeonRole(bot)) != "tank")
            return nullptr;

        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, 220.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, 220.0f);

        Creature* best = nullptr;
        float bestDistance = std::numeric_limits<float>::max();
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!isCurrentDiscoveryScriptedEventTarget(creature)
                || !creature->IsAlive() || !creature->GetHealth()
                || !bot->IsValidAttackTarget(creature)
                || !hasStrictPathToValidationRouteTarget(creature))
                continue;

            float distance = bot->GetExactDist(creature);
            if (!best || distance < bestDistance
                || (distance == bestDistance
                    && creature->GetGUID().GetRawValue() < best->GetGUID().GetRawValue()))
            {
                best = creature;
                bestDistance = distance;
            }
        }
        return best;
    };
    result.RouteEngageRange = routeEngageRange;
    result.CurrentTargetSpawnId = currentValidationRouteTargetSpawnId;
    result.IsFutureCanonicalSource = isFutureCanonicalValidationRouteSource;
    result.WouldPullProtectedFutureSource = wouldPullProtectedFutureValidationRouteSource;
    result.IsRouteEntry = isValidationRouteEntry;
    result.IsRouteAlternateEntry = isValidationRouteAlternateTargetEntry;
    result.IsRouteCombatEntry = isValidationRouteCombatEntry;
    result.IsRoutePackEntry = isValidationRoutePackEntry;
    result.IsScriptTarget = isValidationRouteScriptTarget;
    result.IsCombatTarget = isValidationRouteCombatTarget;
    result.HasStrictPath = hasStrictPathToValidationRouteTarget;
    result.ResolvedTransitionAura = resolvedScriptedTransitionAuraId;
    result.IsPendingScripted = isPendingScriptedEventEntry;
    result.IsCurrentDiscoveryScripted = isCurrentDiscoveryScriptedEventTarget;
    result.IsEligibleTrash = isEligibleTrashClusterMob;
    result.ForEachActiveCombat = forEachActiveValidationCohortCombatCreature;
    result.IsCombatLinked = isValidationCohortCombatLinked;
    result.IsImmediateNextBoss = isImmediateNextValidationRouteBossTarget;
    result.IsImmediateNextEncounter = isImmediateNextValidationRouteEncounterMember;
    result.PartyHasActiveCombat = validationPartyHasActiveCombat;
    result.IsBoundedTerminalCombat = isBoundedTerminalPartyCombatTarget;
    result.FindBoundedTerminalCombat = findBoundedTerminalPartyCombatTarget;
    result.TryCanonicalBossRecovery = tryCanonicalValidationRouteBossRecovery;
    result.IsNaturalForwardHostile = isNaturalForwardHostile;
    result.FindForwardDiscovery = findForwardDiscoveryTarget;
    result.IsObjectiveTarget = isValidationRouteObjectiveTarget;
    result.FindCurrentDiscoveryScripted = findCurrentDiscoveryScriptedEventTarget;
    return result;
}

Unit* BotWorldPopulationMgr::ResolveUsableValidationRouteCombatTarget(
    Player* bot, bool discoveryLeg, Unit* candidate,
    std::function<bool(Creature const*)> const& isValidationRouteCombatTarget,
    std::function<bool(Creature const*)> const& isEligibleTrashClusterMob,
    std::function<bool(Unit const*)> const& hasStrictPathToValidationRouteTarget,
    std::function<bool(Creature const*)> const& isBoundedTerminalPartyCombatTarget,
    std::function<bool(Creature const*)> const& isCurrentDiscoveryScriptedEventTarget)
{
    if (!candidate || !candidate->IsAlive() || !candidate->GetHealth() || !bot || !bot->IsValidAttackTarget(candidate))
        return nullptr;

    Creature const* creature = candidate->ToCreature();
    if (!creature || Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID()) != Party().ValidationRouteFinalTransitionGuids.end())
        return nullptr;

    if (Cohort().Config.ValidationRouteKind != "boss")
    {
        if (isEligibleTrashClusterMob(creature))
            return candidate;
        bool currentDiscoveryPackMember = discoveryLeg
            && Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
            && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID()) != Party().ValidationRoutePackMemberGuids.end()
            && Party().ValidationRoutePackTransitionGuids.find(creature->GetGUID()) == Party().ValidationRoutePackTransitionGuids.end()
            && hasStrictPathToValidationRouteTarget(creature);
        if (currentDiscoveryPackMember
            || (isCurrentDiscoveryScriptedEventTarget(creature)
                && hasStrictPathToValidationRouteTarget(creature)))
            return candidate;
        bool explicitTerminalCombatFocus = !Party().ValidationRouteFocusGuid.IsEmpty()
            && candidate->GetGUID() == Party().ValidationRouteFocusGuid
            && isBoundedTerminalPartyCombatTarget(creature);
        return explicitTerminalCombatFocus ? candidate : nullptr;
    }

    bool unengagedListedBossAdd = Cohort().Config.ValidationRouteKind == "boss"
        && std::find(
            Cohort().Config.ValidationRouteAddTargetEntries.begin(),
            Cohort().Config.ValidationRouteAddTargetEntries.end(),
            creature->GetEntry())
            != Cohort().Config.ValidationRouteAddTargetEntries.end()
        && !candidate->IsInCombat() && !candidate->GetVictim();
    if (unengagedListedBossAdd)
        return nullptr;

    if (isValidationRouteCombatTarget(creature))
        return candidate;

    if (creature->IsDungeonBoss() || creature->isWorldBoss())
        return nullptr;

    float routeProximity = candidate->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ);
    return routeProximity <= 120.0f ? candidate : nullptr;
}
