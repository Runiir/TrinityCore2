#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrScopeGuard.h"
#include "Bots/BotCalibrationFixtureContractGenerated.h"
#include "Bots/BotActionExecutor.h"
#include "Bots/BotAdaptiveDrudgeStrategy.h"
#include "Bots/BotAdaptiveAtramedesStrategy.h"
#include "Bots/BotAdaptiveChimaeronStrategy.h"
#include "Bots/BotAdaptiveMagmawStrategy.h"
#include "Bots/BotAdaptiveMaloriakStrategy.h"
#include "Bots/BotAdaptiveNefarianStrategy.h"
#include "Bots/BotAdaptiveOmnotronStrategy.h"
#include "Bots/BotAdaptiveRaidTrashStrategy.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotDatasetEvent.h"
#include "Bots/BotEncounterMechanicCatalog.h"
#include "Bots/BotMgr.h"
#include "Bots/BotProgressionGoalPolicy.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotRaidHazardState.h"
#include "Bots/BotRaidDrudgeGeometryState.h"
#include "Bots/BotWorldPopulationMgrValidationHazards.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrPolicyHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/BotRaidDrudgeThreatSeedState.h"
#include "Bots/BotRaidDrudgeNativeRushState.h"
#include "CellImpl.h"
#include "CharmInfo.h"
#include "ChaseMovementGenerator.h"
#include "Config.h"
#include "Corpse.h"
#include "DatabaseEnv.h"
#include "DynamicObject.h"
#include "DataStores/DBCStores.h"
#include "GameTime.h"
#include "GameObject.h"
#include "GridNotifiersImpl.h"
#include "GossipDef.h"
#include "Group.h"
#include "GroupMgr.h"
#include "GroupReference.h"
#include "GameClient.h"
#include "Instances/InstanceScript.h"
#include "Instances/InstanceSaveMgr.h"
#include "Entities/Item/Item.h"
#include "Entities/Item/ItemTemplate.h"
#include "LFG.h"
#include "Log.h"
#include "Map.h"
#include "MapManager.h"
#include "MotionMaster.h"
#include "MovementPackets.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "PathGenerator.h"
#include "Pet.h"
#include "PhasingHandler.h"
#include "Player.h"
#include "Quests/QuestDef.h"
#include "Random.h"
#include "Spell.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "TemporarySummon.h"
#include "TerrainMgr.h"
#include "Totem.h"
#include "TotemAI.h"
#include "Unit.h"
#include "VehicleDefines.h"
#include "Creature.h"
#include "CreatureGroups.h"
#include "Cryptography/CryptoHash.h"
#include "WorldSession.h"
#include "WorldPacket.h"
#include "Server/Packets/QuestPackets.h"
#include "Server/Packets/NPCPackets.h"
#include "Server/Packets/SpellPackets.h"
#include "Util.h"

#include <array>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <iomanip>
#include <limits>
#include <regex>
#include <shared_mutex>
#include <sstream>
#include <unordered_map>
#include <unordered_set>

#if defined(_WIN32)
#include <process.h>
#else
#include <unistd.h>
#endif

namespace
{

// Blackwing Descent's native entrance is the only runback contract used by
// the phase-one validation route.  Keep these IDs tied to the DBC/SQL
// contract instead of selecting an arbitrary area trigger at runtime.
constexpr uint32 DecisionFingerprintPersistHeartbeatMs = 5000;
constexpr uint32 RepeatableDiagnosticEventHeartbeatMs = 5000;

using BotWorldPopulationMgrNativeHelpers::CancelRemovableShapeshifts;
using BotWorldPopulationMgrNativeHelpers::CombatOwnerPlayer;
using BotWorldPopulationMgrNativeHelpers::ControlledDispelAuraForHealer;
using BotWorldPopulationMgrNativeHelpers::Distance2d;
using BotWorldPopulationMgrNativeHelpers::HasPowerForSpell;
using BotWorldPopulationMgrNativeHelpers::IsNativeCombatObserved;
using BotWorldPopulationMgrNativeHelpers::IsNativeCombatResSpell;
using BotWorldPopulationMgrNativeHelpers::MaintainedProfileAuraBlocksRefresh;
using BotWorldPopulationMgrNativeHelpers::ReadLastInsertId;
using BotWorldPopulationMgrNativeHelpers::SubmitNativeQuestAccept;
using BotWorldPopulationMgrNativeHelpers::SubmitNativeQuestReward;
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;
using BotWorldPopulationMgrNativeHelpers::UsesRangedAoeCalibrationLane;

using BotWorldPopulationMgrPolicyHelpers::BoundedResultLabel;
using BotWorldPopulationMgrPolicyHelpers::ContainsInsensitive;
using BotWorldPopulationMgrPolicyHelpers::IsSimpleOpenWorldQuestMobAssistTarget;
using BotWorldPopulationMgrPolicyHelpers::LowerCopy;
using BotWorldPopulationMgrPolicyHelpers::ToString;
using BotWorldPopulationMgrPolicyHelpers::WorldPolicySource;
using BotWorldPopulationMgrPolicyHelpers::WorldPolicyVersion;

using BotWorldPopulationMgrSpellSemantics::BuildSpellTagJson;
using BotWorldPopulationMgrSpellSemantics::EventLooksFailure;
using BotWorldPopulationMgrSpellSemantics::EventLooksSuccessful;
using BotWorldPopulationMgrSpellSemantics::HasNearbyProtectedEncounterTarget;
using BotWorldPopulationMgrSpellSemantics::NowMs;
using BotWorldPopulationMgrSpellSemantics::SemanticMechanicFamily;
using BotWorldPopulationMgrSpellSemantics::SemanticMechanicKey;
using BotWorldPopulationMgrSpellSemantics::SpellHasHostileMultiTargetSemantics;
using BotWorldPopulationMgrSpellSemantics::SpellLooksDangerous;
using BotWorldPopulationMgrSpellSemantics::SpellLooksLikeGroundDanger;
using BotWorldPopulationMgrSpellSemantics::SpellLooksLikeHeal;
using BotWorldPopulationMgrSpellSemantics::SpellLooksLikeSummonOrAdds;
using BotWorldPopulationMgrSpellSemantics::SpellLooksRaidWide;
using BotWorldPopulationMgrSpellSemantics::SpellLooksTankSpike;

}

std::string BotWorldPopulationMgr::GetCombatCalibrationJson() const
{
    uint64 nowMs = NowMs();
    BotCalibrationFixtureContractGenerated::SpecContract const*
        fixtureSpecContract =
            BotCalibrationFixtureContractGenerated::FindSpec(
                Cohort().CalibrationTargetSpec);
    std::ostringstream json;
    auto writeBots = [this, &json, nowMs, fixtureSpecContract](
        std::map<uint32, CalibrationMetrics> const& metricsByGuid,
        bool completedWindow)
    {
        AppendCombatCalibrationBotRowsJson(
            json, metricsByGuid, nowMs, fixtureSpecContract, completedWindow);
    };
    AppendCombatCalibrationSummaryJson(json, nowMs, writeBots);
    return json.str();
}

// UpdateBot's preparation phase retains the original death boundary:
// HandleBotDeath(state, bot, diff);

bool BotWorldPopulationMgr::TryValidationRouteObjective(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, std::string& situation, std::string& action, Unit*& target)
{
    bool arrivalRoute = false;
    if (!TryValidationRouteObjectiveGate(state, bot, power, stage,
            activity, situation, action, target, arrivalRoute))
        return false;
    auto routeEngageRange = [this](Player* engageBot, Unit const* engageTarget, uint32 spellId) -> float
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
    auto moveOutOfProfileDeadZone = [this, &state](Player* rangeBot, Unit* rangeTarget, ResolvedCombatAction const& rangeAction) -> bool
    {
        if (!rangeBot || !rangeTarget || rangeAction.MinRange <= 0.0f)
            return false;

        if (state.ActivePathValid && state.IsMoving)
        {
            float endpointDistance = rangeTarget->GetExactDist(
                state.ActivePathToX, state.ActivePathToY, state.ActivePathToZ);
            bool endpointOutsideDeadZone = endpointDistance >= rangeAction.MinRange + 1.0f;
            bool endpointWithinMaxRange = rangeAction.MaxRange <= 0.0f
                || endpointDistance <= rangeAction.MaxRange - 1.0f;
            if (endpointOutsideDeadZone && endpointWithinMaxRange)
                return true;
        }

        return MoveBotToProfileRange(state, rangeBot, rangeTarget, &rangeAction);
    };
    auto tryRouteGroupHeal = [this, &state, &bot, &power, &stage, &activity, &situation, &action](
        Player* healer, Unit* combatTarget, bool allowMovement = true,
        bool allowStationaryCastTime = false) -> bool
    {
        return TryValidationRouteGroupHeal(state, bot, healer, combatTarget,
            power, stage, activity, situation, action, allowMovement,
            allowStationaryCastTime);
    };
    bool discoveryLeg = Cohort().Config.ValidationRouteNodeKind == "discovery_leg";
    auto currentValidationRouteTargetSpawnId = [this]() -> ObjectGuid::LowType
    {
        if (Party().ValidationRouteManifestIndex >= Party().ValidationRouteManifest.size())
            return 0;
        return Party().ValidationRouteManifest[Party().ValidationRouteManifestIndex].TargetSpawnId;
    };
    auto isFutureCanonicalValidationRouteSource = [this](Creature const* creature) -> bool
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
    auto wouldPullProtectedFutureValidationRouteSource = [this, bot](Creature const* creature) -> bool
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
    auto isValidationRouteEntry = [this](uint32 entry) -> bool
    {
        if (!entry)
            return false;
        if ((Cohort().Config.ValidationRouteTargetEntry && entry == Cohort().Config.ValidationRouteTargetEntry)
            || (Cohort().Config.ValidationRouteOpenerTargetEntry && entry == Cohort().Config.ValidationRouteOpenerTargetEntry))
            return true;
        return std::find(Cohort().Config.ValidationRouteAlternateTargetEntries.begin(), Cohort().Config.ValidationRouteAlternateTargetEntries.end(), entry) != Cohort().Config.ValidationRouteAlternateTargetEntries.end();
    };
    auto isValidationRouteAlternateTargetEntry = [this](uint32 entry) -> bool
    {
        if (!entry)
            return false;
        return std::find(Cohort().Config.ValidationRouteAlternateTargetEntries.begin(), Cohort().Config.ValidationRouteAlternateTargetEntries.end(), entry) != Cohort().Config.ValidationRouteAlternateTargetEntries.end();
    };
    auto isValidationRouteCombatEntry = [this, &isValidationRouteAlternateTargetEntry](uint32 entry) -> bool
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
    auto isValidationRoutePackEntry = [this, &isValidationRouteCombatEntry](uint32 entry) -> bool
    {
        if (!entry)
            return false;
        if (!Cohort().Config.ValidationRoutePackTargetEntries.empty())
            return std::find(Cohort().Config.ValidationRoutePackTargetEntries.begin(), Cohort().Config.ValidationRoutePackTargetEntries.end(), entry) != Cohort().Config.ValidationRoutePackTargetEntries.end();
        return isValidationRouteCombatEntry(entry);
    };
    auto isValidationRouteScriptTarget = [
        this,
        bot,
        discoveryLeg,
        &currentValidationRouteTargetSpawnId,
        &isValidationRouteEntry,
        &isValidationRoutePackEntry,
        &wouldPullProtectedFutureValidationRouteSource
    ](Creature const* creature) -> bool
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
    auto isValidationRouteCombatTarget = [&isValidationRouteCombatEntry](Creature const* creature) -> bool
    {
        if (!creature)
            return false;

        return isValidationRouteCombatEntry(creature->GetEntry());
    };
    auto hasStrictPathToValidationRouteTarget = [bot](Unit const* unit) -> bool
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
    auto resolvedScriptedTransitionAuraId = [this](Creature const* creature) -> uint32
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
    auto isPendingScriptedEventEntry = [this, &resolvedScriptedTransitionAuraId](Creature const* creature) -> bool
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
    auto isCurrentDiscoveryScriptedEventTarget = [this, discoveryLeg, &isPendingScriptedEventEntry](Creature const* creature) -> bool
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
    auto isEligibleTrashClusterMob = [
        this,
        bot,
        discoveryLeg,
        &currentValidationRouteTargetSpawnId,
        &isValidationRoutePackEntry,
        &hasStrictPathToValidationRouteTarget,
        &resolvedScriptedTransitionAuraId,
        &isPendingScriptedEventEntry,
        &routeEngageRange,
        &wouldPullProtectedFutureValidationRouteSource
    ](Creature const* creature) -> bool
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
    auto forEachActiveValidationCohortCombatCreature = [this, bot](auto&& visitor) -> void
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
    auto isValidationCohortCombatLinked = [this, bot](Creature const* creature) -> bool
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
    auto isImmediateNextValidationRouteBossTarget = [this](Creature const* creature) -> bool
    {
        return IsImmediateNextValidationRouteBossTarget(creature);
    };
    auto isImmediateNextValidationRouteEncounterMember = [this](Creature const* creature) -> bool
    {
        return IsImmediateNextValidationRouteEncounterMember(creature);
    };

    // The current route node owns every offensive decision until its terminal
    // evidence advances the manifest.  If native threat already includes the
    // next encounter, fail closed immediately: do not compound the accidental
    // pull with profile cleaves, multidots, auto-attacks, pets, or controlled
    // units while waiting for the native encounter to evade/reset.
    Creature* prematureNextEncounter = nullptr;
    forEachActiveValidationCohortCombatCreature([&](Creature* creature)
    {
        if (!prematureNextEncounter && creature && creature->IsAlive()
            && creature->GetHealth()
            && isImmediateNextValidationRouteEncounterMember(creature))
            prematureNextEncounter = creature;
    });
    if (prematureNextEncounter)
    {
        // This route generation is contaminated even if the future encounter
        // later evades. Persist the first edge at cohort scope so a later
        // quiet snapshot cannot certify the current node as cleared.
        if (Cohort().ValidationAttemptFailureReason.empty())
        {
            Cohort().ValidationAttemptFailureReason =
                "validation_route_future_encounter_contamination";
            Cohort().ValidationAttemptFailureAttemptId = Cohort().AttemptId;
            Cohort().ValidationAttemptFailureRouteGeneration =
                Party().ValidationRouteGeneration;
        }
        BotRaidAreaAuthority::SetAllOffenseSuppressed(raidAuthorityOwner, true);
        BotRaidAreaAuthority::Set(raidAuthorityOwner, true);
        for (CurrentSpellTypes spellType : { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL })
            if (Spell* current = bot->GetCurrentSpell(spellType))
            {
                Unit* castTarget = current->m_targets.GetUnitTarget();
                Creature const* castCreature = castTarget ? castTarget->ToCreature() : nullptr;
                if ((castCreature && isImmediateNextValidationRouteEncounterMember(castCreature))
                    || SpellHasHostileMultiTargetSemantics(current->GetSpellInfo()))
                    bot->InterruptSpell(spellType, false);
            }
        if (bot->GetCurrentSpell(CURRENT_AUTOREPEAT_SPELL))
            bot->InterruptSpell(CURRENT_AUTOREPEAT_SPELL, false);
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Safety,
            BotActionArbitration::Priority::Terminal,
            "future_encounter_contamination");
        if (Pet* pet = bot->GetPet())
            pet->AttackStop();
        for (Unit* controlled : bot->m_Controlled)
            if (controlled)
            {
                for (CurrentSpellTypes spellType : { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL })
                    if (Spell* current = controlled->GetCurrentSpell(spellType))
                    {
                        Unit* castTarget = current->m_targets.GetUnitTarget();
                        Creature const* castCreature = castTarget ? castTarget->ToCreature() : nullptr;
                        if ((castCreature && isImmediateNextValidationRouteEncounterMember(castCreature))
                            || SpellHasHostileMultiTargetSemantics(current->GetSpellInfo()))
                            controlled->InterruptSpell(spellType, false);
                }
                controlled->AttackStop();
            }

        std::string raw = BuildRawJson(bot, prematureNextEncounter);
        std::string semantic = BuildSemanticJson(bot, prematureNextEncounter,
            "validation_route_future_encounter_contamination", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_future_encounter_contamination",
            prematureNextEncounter, "native_reset_required_hold", raw.c_str(), semantic.c_str(),
            bot->GetExactDist(prematureNextEncounter), prematureNextEncounter->GetEntry());
        MarkBotBlocked(state, bot, "future_encounter_premature_engagement");
        target = prematureNextEncounter;
        situation = "validation_route_future_encounter_contamination";
        action = "hold_for_native_future_encounter_reset";
        return true;
    }

    auto validationPartyHasActiveCombat = [
        this,
        &forEachActiveValidationCohortCombatCreature,
        &isImmediateNextValidationRouteEncounterMember
    ](bool transferImmediateNextEncounter = false) -> bool
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
    auto isBoundedTerminalPartyCombatTarget = [
        this,
        bot,
        &isValidationCohortCombatLinked,
        &isImmediateNextValidationRouteEncounterMember,
        &hasStrictPathToValidationRouteTarget
    ](Creature const* creature) -> bool
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
    auto findBoundedTerminalPartyCombatTarget = [
        this,
        bot,
        &forEachActiveValidationCohortCombatCreature,
        &isBoundedTerminalPartyCombatTarget
    ]() -> Unit*
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
    auto tryCanonicalValidationRouteBossRecovery = [
        this,
        bot,
        &state,
        &power,
        stage,
        activity,
        &validationPartyHasActiveCombat
    ](std::string& recoveryResult, bool& recoveryInitiated) -> bool
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
        if (deathParticipants < 2 || recentDeathCount < 2 || validationPartyHasActiveCombat())
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
    auto isNaturalValidationRoutePackMember = [
        this,
        bot,
        &isFutureCanonicalValidationRouteSource,
        &isImmediateNextValidationRouteEncounterMember,
        &isPendingScriptedEventEntry
    ](Creature const* creature) -> bool
    {
        if (!bot || !creature || !creature->IsAlive() || !creature->GetHealth() || creature->GetMap() != bot->GetMap())
            return false;
        if (Party().ValidationRoutePendingFinalTransitionGuids.find(creature->GetGUID()) != Party().ValidationRoutePendingFinalTransitionGuids.end())
            return false;
        if (Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID()) != Party().ValidationRouteFinalTransitionGuids.end())
            return false;
        if (isImmediateNextValidationRouteEncounterMember(creature))
            return false;
        bool nativeCombatObserved = creature->IsInCombat()
            || creature->GetVictim()
            || creature->GetHealth() < creature->GetMaxHealth();
        // A future source remains protected while unengaged.  Once native
        // combat has already linked it to this pull, however, it is part of
        // the current natural pack and must be enrolled so pack-clear and
        // death accounting cannot strand the party on one selected GUID.
        if (isFutureCanonicalValidationRouteSource(creature) && !nativeCombatObserved)
            return false;
        if (creature->IsDungeonBoss() || creature->isWorldBoss())
            return false;
        return !creature->IsCritter() && !creature->IsPet() && !creature->IsTotem() && !creature->IsSummon()
            && !creature->IsGuardian() && creature->GetOwnerGUID().IsEmpty();
    };
    auto enrollValidationRoutePackMember = [this, bot, &state, &power, stage, activity, &isNaturalValidationRoutePackMember](Creature const* creature, bool engaged) -> void
    {
        if (Cohort().Config.ValidationRouteKind == "boss" || !engaged || !isNaturalValidationRoutePackMember(creature))
            return;

        if (Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration)
        {
            Party().ValidationRoutePackMemberGuids.clear();
            Party().ValidationRoutePackEngagedGuids.clear();
            Party().ValidationRoutePackDeathGuids.clear();
            Party().ValidationRoutePackTransitionGuids.clear();
            Party().ValidationRoutePackGeneration = Party().ValidationRouteGeneration;
            Party().ValidationRoutePackObservedEngagement = false;
            Party().ValidationRoutePackClearCandidateSinceMs = 0;
        }
        bool memberInserted = Party().ValidationRoutePackMemberGuids.insert(creature->GetGUID()).second;
        bool engagementInserted = Party().ValidationRoutePackEngagedGuids.insert(creature->GetGUID()).second;
        Party().ValidationRoutePackTransitionGuids.erase(creature->GetGUID());
        Party().ValidationRoutePackObservedEngagement = true;
        Party().ValidationRoutePackClearCandidateSinceMs = 0;
        if (memberInserted || engagementInserted)
        {
            std::string raw = BuildRawJson(bot, creature);
            std::string semantic = BuildSemanticJson(bot, creature, "validation_route_pack_enrollment", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_pack_enrolled", creature, "cohort_combat_reference", raw.c_str(), semantic.c_str(), bot ? bot->GetExactDist(creature) : 0.0f, creature->GetEntry());
        }
    };
    auto recordValidationRouteScriptedTransition = [this, bot, discoveryLeg, &state, &power, stage, activity, &resolvedScriptedTransitionAuraId](Creature* creature) -> bool
    {
        if (!creature || Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration
            || Party().ValidationRoutePackEngagedGuids.find(creature->GetGUID()) == Party().ValidationRoutePackEngagedGuids.end()
            || Party().ValidationRoutePackTransitionGuids.find(creature->GetGUID()) != Party().ValidationRoutePackTransitionGuids.end())
            return false;

        uint32 auraId = resolvedScriptedTransitionAuraId(creature);
        if (!auraId)
            return false;

        Party().ValidationRoutePackTransitionGuids.insert(creature->GetGUID());
        ObjectGuid transitionedGuid = creature->GetGUID();
        bool declaredByFutureNode = false;
        for (size_t routeIndex = Party().ValidationRouteManifestIndex + 1; routeIndex < Party().ValidationRouteManifest.size(); ++routeIndex)
            if (std::find(Party().ValidationRouteManifest[routeIndex].ScriptedEventEntries.begin(), Party().ValidationRouteManifest[routeIndex].ScriptedEventEntries.end(), creature->GetEntry())
                != Party().ValidationRouteManifest[routeIndex].ScriptedEventEntries.end())
            {
                declaredByFutureNode = true;
                break;
            }
        if (!declaredByFutureNode)
        {
            if (discoveryLeg)
                Party().ValidationRoutePendingFinalTransitionGuids.insert(transitionedGuid);
            else
                Party().ValidationRouteFinalTransitionGuids.insert(transitionedGuid);
        }
        if (Party().ValidationRouteFocusGuid == transitionedGuid)
        {
            Party().ValidationRouteFocusGuid.Clear();
            Party().ValidationRouteFocusEntry = 0;
            Party().ValidationRouteFocusSeenMs = 0;
        }
        for (WorldBotState& cohortState : Party().Bots)
        {
            bool pursuingTransition = cohortState.TargetGuid == transitionedGuid
                || cohortState.ValidationRouteCombatProgressTargetGuid == transitionedGuid
                || cohortState.ValidationRoutePackProgressTargetGuid == transitionedGuid;
            if (!pursuingTransition)
                continue;
            if (Player* member = GetLoadedBot(cohortState))
                member->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
            if (cohortState.TargetGuid == transitionedGuid)
                cohortState.TargetGuid.Clear();
            if (cohortState.LastDecisionTargetGuid == transitionedGuid)
                cohortState.LastDecisionTargetGuid.Clear();
            cohortState.ValidationRouteCombatProgressTargetGuid.Clear();
            cohortState.ValidationRoutePackProgressTargetGuid.Clear();
            cohortState.ValidationRouteCombatNoProgressCount = 0;
            cohortState.ValidationRouteCombatNoProgressSinceMs = 0;
            cohortState.ValidationRoutePackNoProgressCount = 0;
            cohortState.ValidationRoutePackNoProgressSinceMs = 0;
            if (cohortState.LastCombatAttempt.TargetGuid == transitionedGuid)
                cohortState.LastCombatAttempt = WorldBotState::CombatAttemptDiagnostic();
            if (cohortState.LastRouteProgress.TargetGuid == transitionedGuid)
                cohortState.LastRouteProgress = WorldBotState::RouteProgressDiagnostic();
            cohortState.ActivePathValid = false;
        }
        std::string raw = BuildRawJson(bot, creature);
        std::string semantic = BuildSemanticJson(bot, creature, "validation_route_scripted_transition", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_scripted_transition", creature, "manifest_transition_observed", raw.c_str(), semantic.c_str(), UnitHealthPct(creature), auraId);
        return true;
    };
    auto retireStaleValidationRoutePackMembers = [
        this,
        bot,
        &state,
        &power,
        stage,
        activity,
        discoveryLeg,
        &isNaturalValidationRoutePackMember,
        &isValidationCohortCombatLinked,
        &isValidationRouteScriptTarget
    ]() -> void
    {
        if (Cohort().Config.ValidationRouteKind == "boss" || !bot || !bot->GetMap()
            || Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration)
            return;

        std::vector<ObjectGuid> memberGuids(Party().ValidationRoutePackMemberGuids.begin(), Party().ValidationRoutePackMemberGuids.end());
        for (ObjectGuid const& guid : memberGuids)
        {
            if (Party().ValidationRoutePackDeathGuids.find(guid) != Party().ValidationRoutePackDeathGuids.end()
                || Party().ValidationRoutePackTransitionGuids.find(guid) != Party().ValidationRoutePackTransitionGuids.end())
                continue;

            Creature* creature = bot->GetMap()->GetCreature(guid);
            if (creature && (!creature->IsAlive() || !creature->GetHealth()))
                continue;

            bool combatLinked = creature && isValidationCohortCombatLinked(creature);
            bool recentProgress = false;
            uint64 nowMs = NowMs();
            static constexpr uint64 PackProgressFreshMs = 10000;
            for (WorldBotState const& cohortState : Party().Bots)
            {
                bool recentCombatAttempt = cohortState.LastCombatAttempt.TargetGuid == guid
                    && cohortState.LastCombatAttempt.RecordedAtMs
                    && nowMs >= cohortState.LastCombatAttempt.RecordedAtMs
                    && nowMs - cohortState.LastCombatAttempt.RecordedAtMs <= PackProgressFreshMs;
                bool recentRouteProgress = cohortState.LastRouteProgress.TargetGuid == guid
                    && cohortState.LastRouteProgress.RecordedAtMs
                    && nowMs >= cohortState.LastRouteProgress.RecordedAtMs
                    && nowMs - cohortState.LastRouteProgress.RecordedAtMs <= PackProgressFreshMs;
                if (recentCombatAttempt || recentRouteProgress)
                {
                    recentProgress = true;
                    break;
                }
            }

            bool naturalMember = creature && isNaturalValidationRoutePackMember(creature);
            bool attackable = creature && bot->IsValidAttackTarget(creature);
            // Combat linkage and recent progress are transient.  For the
            // current non-discovery node, an alive natural attackable member
            // that is still an exact declared/persisted route target remains
            // authoritative until actual death or an explicit scripted/final
            // transition removes it.  Do not use a per-bot path test here:
            // retirement is shared state, and one bot's temporary no-path
            // result must not retire a GUID that another bot can reacquire.
            bool const exactCurrentRouteMember = !discoveryLeg
                && isValidationRouteScriptTarget(creature);
            if (naturalMember && attackable
                && (combatLinked || recentProgress || exactCurrentRouteMember))
                continue;

            if (!Party().ValidationRoutePackTransitionGuids.insert(guid).second)
                continue;

            if (Party().ValidationRouteFocusGuid == guid)
            {
                Party().ValidationRouteFocusGuid.Clear();
                Party().ValidationRouteFocusEntry = 0;
                Party().ValidationRouteFocusMapId = 0;
                Party().ValidationRouteFocusX = 0.0f;
                Party().ValidationRouteFocusY = 0.0f;
                Party().ValidationRouteFocusZ = 0.0f;
                Party().ValidationRouteFocusSeenMs = 0;
            }
            for (WorldBotState& cohortState : Party().Bots)
            {
                if (Player* member = GetLoadedBot(cohortState); member && cohortState.TargetGuid == guid)
                    member->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                if (cohortState.TargetGuid == guid)
                    cohortState.TargetGuid.Clear();
                if (cohortState.LastDecisionTargetGuid == guid)
                    cohortState.LastDecisionTargetGuid.Clear();
                if (cohortState.ValidationRouteCombatProgressTargetGuid == guid)
                    cohortState.ValidationRouteCombatProgressTargetGuid.Clear();
                if (cohortState.ValidationRoutePackProgressTargetGuid == guid)
                    cohortState.ValidationRoutePackProgressTargetGuid.Clear();
                if (cohortState.LastCombatAttempt.TargetGuid == guid)
                    cohortState.LastCombatAttempt = WorldBotState::CombatAttemptDiagnostic();
                if (cohortState.LastRouteProgress.TargetGuid == guid)
                    cohortState.LastRouteProgress = WorldBotState::RouteProgressDiagnostic();
                cohortState.ValidationRouteCombatNoProgressCount = 0;
                cohortState.ValidationRouteCombatNoProgressSinceMs = 0;
                cohortState.ValidationRoutePackNoProgressCount = 0;
                cohortState.ValidationRoutePackNoProgressSinceMs = 0;
                cohortState.ActivePathValid = false;
            }

            char const* reason = !creature ? "member_not_loaded"
                : !naturalMember ? "member_no_longer_natural"
                : !attackable ? "member_no_longer_attackable"
                : "member_no_longer_engaged_or_progressing";
            std::ostringstream raw;
            raw << "{\"base\":" << BuildRawJson(bot, creature)
                << ",\"pack_retirement\":{\"guid\":" << guid.GetCounter()
                << ",\"route_generation\":" << Party().ValidationRouteGeneration
                << ",\"combat_linked\":" << (combatLinked ? "true" : "false")
                << ",\"recent_progress\":" << (recentProgress ? "true" : "false")
                << ",\"natural_member\":" << (naturalMember ? "true" : "false")
                << ",\"attackable\":" << (attackable ? "true" : "false") << "}}";
            std::string semantic = BuildSemanticJson(bot, creature, "validation_route_pack_retirement", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_pack_retired", creature, reason, raw.str().c_str(), semantic.c_str(),
                creature ? bot->GetExactDist(creature) : 0.0f, creature ? creature->GetEntry() : 0);
        }
    };
    auto enrollEngagedValidationRoutePackMembers = [this, bot, discoveryLeg,
        &forEachActiveValidationCohortCombatCreature,
        &isNaturalValidationRoutePackMember,
        &enrollValidationRoutePackMember,
        &recordValidationRouteScriptedTransition,
        &retireStaleValidationRoutePackMembers,
        &isImmediateNextValidationRouteEncounterMember,
        &isPendingScriptedEventEntry]() -> void
    {
        if (Cohort().Config.ValidationRouteKind == "boss" || !bot)
            return;

        forEachActiveValidationCohortCombatCreature([&](Creature* creature)
        {
            if (!isNaturalValidationRoutePackMember(creature))
                return;

            enrollValidationRoutePackMember(creature, true);
            recordValidationRouteScriptedTransition(creature);
        });

        // CombatManager references are not guaranteed to exist for every
        // member of a native area pull.  The first Stonecore 5H trace exposed
        // this boundary: the party had ten engaged trash creatures, but only
        // the first selected GUID was in the reference iterator.  Once that
        // GUID died the route ledger could not prove the natural pack clear
        // and sent the whole party into an unnecessary runback.  In the
        // discovery leg, supplement the reference scan with a bounded nearby
        // world scan and enroll every alive natural creature that has native
        // combat/victim/health-loss evidence.  Future canonical sources,
        // bosses, scripted actors, and next-route members remain excluded by
        // isNaturalValidationRoutePackMember().
        if (discoveryLeg && bot->GetMap())
        {
            auto isCurrentNativeNaturalPackMember = [&](Creature const* creature) -> bool
            {
                if (!creature || !creature->IsAlive() || !creature->GetHealth()
                    || creature->GetMap() != bot->GetMap()
                    || !bot->IsValidAttackTarget(creature)
                    || Party().ValidationRoutePendingFinalTransitionGuids.find(creature->GetGUID())
                        != Party().ValidationRoutePendingFinalTransitionGuids.end()
                    || Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID())
                        != Party().ValidationRouteFinalTransitionGuids.end()
                    || isImmediateNextValidationRouteEncounterMember(creature)
                    || isPendingScriptedEventEntry(creature)
                    || creature->IsDungeonBoss() || creature->isWorldBoss()
                    || creature->IsCritter() || creature->IsPet()
                    || creature->IsTotem() || creature->IsSummon()
                    || creature->IsGuardian() || !creature->GetOwnerGUID().IsEmpty())
                    return false;

                return creature->IsInCombat() || creature->GetVictim()
                    || creature->GetHealth() < creature->GetMaxHealth();
            };
            std::vector<WorldObject*> nearbyObjects;
            Trinity::AllWorldObjectsInRange nearbyCheck(bot, 80.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> nearbySearcher(
                bot, nearbyObjects, nearbyCheck);
            Cell::VisitAllObjects(bot, nearbySearcher, 80.0f);
            for (WorldObject* object : nearbyObjects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                if (!isCurrentNativeNaturalPackMember(creature))
                    continue;

                enrollValidationRoutePackMember(creature, true);
                recordValidationRouteScriptedTransition(creature);
            }
        }

        // Passive scripted actors do not always create a CombatManager PvE
        // reference when they are only clipped by native area damage.  That
        // is still valid native handoff evidence, but the reference iterator
        // above cannot see it.  Observe only the current node's declared
        // scripted entries, and require combat/victim state or real health
        // loss before enrolling; this never discovers or pulls a future node.
        if (discoveryLeg && bot->GetMap())
        {
            std::vector<WorldObject*> objects;
            Trinity::AllWorldObjectsInRange check(bot, 220.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
            Cell::VisitAllObjects(bot, searcher, 220.0f);
            for (WorldObject* object : objects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                if (!creature || !isPendingScriptedEventEntry(creature)
                    || !creature->IsAlive() || !creature->GetHealth()
                    || !bot->IsValidAttackTarget(creature))
                    continue;

                bool nativeCombatObserved = creature->IsInCombat()
                    || creature->GetVictim()
                    || creature->GetHealth() < creature->GetMaxHealth();
                if (!nativeCombatObserved)
                    continue;

                enrollValidationRoutePackMember(creature, true);
                recordValidationRouteScriptedTransition(creature);
            }
        }

        if (Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration || !bot->GetMap())
            return;
        std::vector<ObjectGuid> memberGuids(Party().ValidationRoutePackMemberGuids.begin(), Party().ValidationRoutePackMemberGuids.end());
        for (ObjectGuid const& guid : memberGuids)
            if (Creature* creature = bot->GetMap()->GetCreature(guid))
                recordValidationRouteScriptedTransition(creature);
        retireStaleValidationRoutePackMembers();
    };
    auto persistedValidationRoutePackHasLiveMembers = [this]() -> bool
    {
        if (Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration)
            return false;
        for (ObjectGuid const& guid : Party().ValidationRoutePackMemberGuids)
            if (Party().ValidationRoutePackDeathGuids.find(guid) == Party().ValidationRoutePackDeathGuids.end()
                && Party().ValidationRoutePackTransitionGuids.find(guid) == Party().ValidationRoutePackTransitionGuids.end())
                return true;
        return false;
    };
    auto activeValidationRoutePackTarget = [this, bot, discoveryLeg,
        &isValidationRoutePackEntry,
        &hasStrictPathToValidationRouteTarget,
        &isPendingScriptedEventEntry]() -> Unit*
    {
        if (Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration || !bot || !bot->GetMap())
            return nullptr;

        Creature* best = nullptr;
        float bestScore = -std::numeric_limits<float>::max();
        for (ObjectGuid const& guid : Party().ValidationRoutePackMemberGuids)
        {
            if (Party().ValidationRoutePackDeathGuids.find(guid) != Party().ValidationRoutePackDeathGuids.end()
                || Party().ValidationRoutePackTransitionGuids.find(guid) != Party().ValidationRoutePackTransitionGuids.end())
                continue;
            Creature* creature = bot->GetMap()->GetCreature(guid);
            if (!creature || !creature->IsAlive() || !creature->GetHealth() || !bot->IsValidAttackTarget(creature))
                continue;
            // Discovery's current scripted actor is enrolled only after its
            // native combat state is observed.  It is then a persisted member
            // of the current pack even when the discovery node has no static
            // PackTargetEntries (Millhouse is the canonical example).  Future
            // scripted actors remain protected until their own transition.
            bool currentDiscoveryPackMember = discoveryLeg
                && Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
                && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID()) != Party().ValidationRoutePackMemberGuids.end();
            // Reengagement is restricted to the exact declared pack entries
            // (or the persisted current discovery member). A member that is
            // already in native combat may have moved off the original route
            // corridor, so requiring a fresh path to the navigation anchor
            // would incorrectly discard the real pull and let the tank select
            // an unrelated second creature. Keep the engaged member
            // authoritative; only an unengaged member needs a new path.
            bool const persistedCurrentPackMember =
                Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
                && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID())
                    != Party().ValidationRoutePackMemberGuids.end();
            bool const persistedCurrentPackCombat = persistedCurrentPackMember
                && (creature->IsInCombat() || creature->GetVictim());
            if ((!isValidationRoutePackEntry(creature->GetEntry()) && !currentDiscoveryPackMember)
                || (!hasStrictPathToValidationRouteTarget(creature)
                    && !persistedCurrentPackCombat))
                continue;
            Unit* victim = creature->GetVictim();
            bool botIsTank = std::string(GetDungeonRole(bot)) == "tank";
            Player* victimPlayer = victim ? victim->ToPlayer() : nullptr;
            std::string victimRole = victimPlayer ? GetDungeonRole(victimPlayer) : "";
            bool victimIsTank = victimRole == "tank";
            float score = (creature->IsInCombat() || victim ? 10000.0f : 0.0f)
                - bot->GetExactDist(creature);
            // Once the current discovery scripted actor has been observed in
            // native combat, it is the handoff target—not ordinary corridor
            // trash.  Keep future scripted actors protected, but give this
            // enrolled actor deterministic focus so its transition aura can
            // actually be reached before the party dies to the surrounding
            // pack.  Without this bias the tank's victim/role score can keep
            // selecting a normal trash mob while AoE still chips the actor.
            if (currentDiscoveryPackMember && isPendingScriptedEventEntry(creature))
                score += 50000.0f;
            if (botIsTank && victimRole == "healer")
                score += 30000.0f;
            else if (botIsTank && victim && !victimIsTank)
                score += 20000.0f;
            else if (botIsTank && !victim)
                score += 5000.0f;
            if (victim == bot)
                score += 1000.0f;
            if (!best || score > bestScore)
            {
                best = creature;
                bestScore = score;
            }
        }
        return best;
    };
    auto isNaturalForwardHostile = [this, bot, &hasStrictPathToValidationRouteTarget, &resolvedScriptedTransitionAuraId, &isPendingScriptedEventEntry](Creature const* creature) -> bool
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
    auto findForwardDiscoveryTarget = [this, bot, discoveryLeg, &isNaturalForwardHostile]() -> Unit*
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
    auto isValidationRouteObjectiveTarget = [&isValidationRouteScriptTarget,
        &isEligibleTrashClusterMob,
        &isCurrentDiscoveryScriptedEventTarget,
        this](Creature const* creature) -> bool
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
    auto findNearestTrashClusterMob = [&]() -> Unit*
    {
        if (Cohort().Config.ValidationRouteKind == "boss" || !bot)
            return nullptr;
        if (discoveryLeg)
            return findForwardDiscoveryTarget();

        float radius = Cohort().Config.ValidationRouteClusterRadiusYards > 1.0f ? Cohort().Config.ValidationRouteClusterRadiusYards : 90.0f;
        float searchRange = std::max(40.0f, bot->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ) + radius + 40.0f);
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, searchRange);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, searchRange);

        Unit* best = nullptr;
        float bestScore = std::numeric_limits<float>::max();
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!isEligibleTrashClusterMob(creature))
                continue;
            float score = bot->GetExactDist(creature) + creature->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ) * 0.25f;
            if (!best || score < bestScore)
            {
                best = creature;
                bestScore = score;
            }
        }
        if (Creature* creature = best ? best->ToCreature() : nullptr)
            enrollValidationRoutePackMember(creature, isValidationCohortCombatLinked(creature));
        return best;
    };
    auto findCurrentDiscoveryScriptedEventTarget = [this, bot, discoveryLeg,
        &isCurrentDiscoveryScriptedEventTarget,
        &hasStrictPathToValidationRouteTarget]() -> Unit*
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
    auto findTrashClusterThreatTarget = [&]() -> Unit*
    {
        if (Cohort().Config.ValidationRouteKind == "boss" || !bot)
            return nullptr;

        enrollEngagedValidationRoutePackMembers();
        if (Unit* packTarget = activeValidationRoutePackTarget())
            return packTarget;
        if (Unit* scriptedTarget = findCurrentDiscoveryScriptedEventTarget())
            return scriptedTarget;
        // A live current-pack member is a hard ownership boundary. If it is
        // temporarily not pathable from this decision point, hold the party
        // rather than pulling a second natural creature and compounding the
        // encounter. The next native combat/path update can reselect the same
        // member through activeValidationRoutePackTarget().
        if (Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration)
            for (ObjectGuid const& guid : Party().ValidationRoutePackMemberGuids)
                if (Party().ValidationRoutePackDeathGuids.find(guid)
                        == Party().ValidationRoutePackDeathGuids.end()
                    && Party().ValidationRoutePackTransitionGuids.find(guid)
                        == Party().ValidationRoutePackTransitionGuids.end())
                    return nullptr;
        float radius = discoveryLeg ? 120.0f : (Cohort().Config.ValidationRouteClusterRadiusYards > 1.0f ? Cohort().Config.ValidationRouteClusterRadiusYards : 90.0f);
        float searchRange = std::max(40.0f, bot->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ) + radius + 40.0f);
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, searchRange);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, searchRange);

        Unit* best = nullptr;
        float bestScore = -1.0f;
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!isEligibleTrashClusterMob(creature))
                continue;

            Unit* victim = creature->GetVictim();
            Player* victimPlayer = victim ? victim->ToPlayer() : nullptr;
            std::string victimRole = victimPlayer ? GetDungeonRole(victimPlayer) : "";
            bool looseOnNonTank = victim && victimRole != "tank";
            bool unengaged = !victim;
            float score = 1000.0f - bot->GetExactDist(creature);
            if (victimRole == "healer")
                score += 7500.0f;
            else if (looseOnNonTank)
                score += 5000.0f;
            else if (unengaged)
                score += 1500.0f;
            if (creature == bot->GetVictim())
                score += 250.0f;

            if (!best || score > bestScore)
            {
                best = creature;
                bestScore = score;
            }
        }
        if (Creature* creature = best ? best->ToCreature() : nullptr)
            enrollValidationRoutePackMember(creature, isValidationCohortCombatLinked(creature));
        return best;
    };
    struct TrashClusterTerminalBlocker
    {
        ObjectGuid Guid;
        uint32 Entry = 0;
        ObjectGuid::LowType SpawnId = 0;
        uint32 FormationId = 0;
        ObjectGuid FormationLeaderGuid;
        float Distance = 0.0f;
        float PositionX = 0.0f;
        float PositionY = 0.0f;
        float PositionZ = 0.0f;
        float HomeX = 0.0f;
        float HomeY = 0.0f;
        float HomeZ = 0.0f;
        float HomeDistance = 0.0f;
        uint32 CurrentMotionType = MAX_MOTION_TYPE;
        uint32 ActiveMotionType = MAX_MOTION_TYPE;
        bool Observed = false;
        bool Alive = false;
        bool Attackable = false;
        bool Evade = false;
        bool Path = false;
        bool Member = false;
        bool ReturningHome = false;
        bool FormationMember = false;
        bool FormationLeader = false;
        bool FormationFormed = false;
    } trashClusterTerminalBlocker;
    auto captureTrashClusterTerminalBlocker = [&](Creature* creature) -> void
    {
        if (!creature)
            return;

        trashClusterTerminalBlocker.Observed = true;
        trashClusterTerminalBlocker.Entry = creature->GetEntry();
        trashClusterTerminalBlocker.SpawnId = creature->GetSpawnId();
        trashClusterTerminalBlocker.Distance = creature->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ);
        trashClusterTerminalBlocker.PositionX = creature->GetPositionX();
        trashClusterTerminalBlocker.PositionY = creature->GetPositionY();
        trashClusterTerminalBlocker.PositionZ = creature->GetPositionZ();
        Position const& home = creature->GetHomePosition();
        trashClusterTerminalBlocker.HomeX = home.GetPositionX();
        trashClusterTerminalBlocker.HomeY = home.GetPositionY();
        trashClusterTerminalBlocker.HomeZ = home.GetPositionZ();
        trashClusterTerminalBlocker.HomeDistance = creature->GetExactDist(home);
        trashClusterTerminalBlocker.Alive = creature->IsAlive() && creature->GetHealth();
        trashClusterTerminalBlocker.Attackable = bot->IsValidAttackTarget(creature);
        trashClusterTerminalBlocker.Evade = creature->IsInEvadeMode() || creature->HasUnitState(UNIT_STATE_EVADE);
        trashClusterTerminalBlocker.Path = hasStrictPathToValidationRouteTarget(creature);
        trashClusterTerminalBlocker.ReturningHome = creature->IsReturningHome();
        trashClusterTerminalBlocker.CurrentMotionType = creature->GetMotionMaster()->GetCurrentMovementGeneratorType();
        trashClusterTerminalBlocker.ActiveMotionType = creature->GetMotionMaster()->GetMotionSlotType(MOTION_SLOT_ACTIVE);
        if (CreatureGroup const* formation = creature->GetFormation())
        {
            trashClusterTerminalBlocker.FormationMember = true;
            trashClusterTerminalBlocker.FormationId = formation->GetId();
            trashClusterTerminalBlocker.FormationFormed = formation->isFormed();
            trashClusterTerminalBlocker.FormationLeader = formation->IsLeader(creature);
            if (Creature const* leader = formation->getLeader())
                trashClusterTerminalBlocker.FormationLeaderGuid = leader->GetGUID();
        }
    };
    auto trashClusterHasLiveMobs = [&]() -> bool
    {
        trashClusterTerminalBlocker = TrashClusterTerminalBlocker();
        if (Cohort().Config.ValidationRouteKind == "boss" || !bot)
            return false;

        enrollEngagedValidationRoutePackMembers();
        if (persistedValidationRoutePackHasLiveMembers())
        {
            for (ObjectGuid const& guid : Party().ValidationRoutePackMemberGuids)
            {
                if (Party().ValidationRoutePackDeathGuids.find(guid) != Party().ValidationRoutePackDeathGuids.end()
                    || Party().ValidationRoutePackTransitionGuids.find(guid) != Party().ValidationRoutePackTransitionGuids.end())
                    continue;
                trashClusterTerminalBlocker.Guid = guid;
                trashClusterTerminalBlocker.Member = true;
                if (Creature* creature = bot->GetMap() ? bot->GetMap()->GetCreature(guid) : nullptr)
                    captureTrashClusterTerminalBlocker(creature);
                break;
            }
            return true;
        }
        if (discoveryLeg)
            return false;

        float radius = Cohort().Config.ValidationRouteClusterRadiusYards > 1.0f ? Cohort().Config.ValidationRouteClusterRadiusYards : 90.0f;
        float searchRange = std::max(40.0f, bot->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ) + radius + 40.0f);
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, searchRange);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, searchRange);

        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (isEligibleTrashClusterMob(creature))
            {
                trashClusterTerminalBlocker.Guid = creature->GetGUID();
                captureTrashClusterTerminalBlocker(creature);
                trashClusterTerminalBlocker.Member = Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
                    && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID()) != Party().ValidationRoutePackMemberGuids.end();
                return true;
            }
        }

        return false;
    };
    auto markTrashClusterCleared = [&](char const* reason) -> void
    {
        MarkTrashClusterCleared(state, bot, power, stage, activity, reason);
    };
    auto markValidationRouteTrashFailed = [&](Unit* failedTarget, char const* reason, char const* situationName, float metric, uint32 data, float bestHealthPct = -1.0f, uint32 noProgressCount = 0, uint32 noProgressThreshold = 0) -> void
    {
        MarkValidationRouteTrashFailed(state, bot, power, stage, activity,
            failedTarget, reason, situationName, metric, data, bestHealthPct,
            noProgressCount, noProgressThreshold);
    };
    auto clearValidationRouteKilledFocus = [this, &state](ObjectGuid killedGuid)
    {
        ClearValidationRouteKilledFocus(state, killedGuid);
    };
    auto recordValidationRouteBossKill = [this, &state, bot, &power, stage, activity](Unit* killedTarget, char const* assistResult) -> bool
    {
        return RecordValidationRouteBossKill(state, bot, power, stage, activity,
            killedTarget, assistResult);
    };
    auto recordValidationRouteTrashKill = [this, &state, bot, &power, stage, activity, &isValidationRouteScriptTarget, &trashClusterHasLiveMobs](Unit* killedTarget, char const* reason) -> bool
    {
        return RecordValidationRouteTrashKill(state, bot, power, stage, activity,
            killedTarget, reason, isValidationRouteScriptTarget,
            trashClusterHasLiveMobs);
    };
    auto recordDefeatedValidationRouteTarget = [this, &isValidationRouteScriptTarget, &recordValidationRouteBossKill, &recordValidationRouteTrashKill](Unit* defeatedTarget, char const* reason) -> bool
    {
        return RecordDefeatedValidationRouteTarget(defeatedTarget, reason,
            isValidationRouteScriptTarget, recordValidationRouteBossKill,
            recordValidationRouteTrashKill);
    };
    auto recordDefeatedValidationRoutePackMembers = [this, bot, &recordValidationRouteTrashKill]() -> bool
    {
        return RecordDefeatedValidationRoutePackMembers(bot,
            recordValidationRouteTrashKill);
    };
    auto completeDiscoveredPackIfReady = [this, bot, discoveryLeg, &state, &power, stage, activity, &validationPartyHasActiveCombat]() -> bool
    {
        return CompleteDiscoveredPackIfReady(discoveryLeg, bot, state, power,
            stage, activity, validationPartyHasActiveCombat);
    };
    auto routeUsableCombatTarget = [
        this,
        bot,
        discoveryLeg,
        &isValidationRouteCombatTarget,
        &isEligibleTrashClusterMob,
        &hasStrictPathToValidationRouteTarget,
        &isBoundedTerminalPartyCombatTarget,
        &isCurrentDiscoveryScriptedEventTarget
    ](Unit* candidate) -> Unit*
    {
        return ResolveUsableValidationRouteCombatTarget(bot, discoveryLeg,
            candidate, isValidationRouteCombatTarget,
            isEligibleTrashClusterMob, hasStrictPathToValidationRouteTarget,
            isBoundedTerminalPartyCombatTarget,
            isCurrentDiscoveryScriptedEventTarget);
    };
    auto maybeValidationPrerequisiteNoProgressAssist = [this, &state, bot, &power, stage, activity, &isValidationRouteScriptTarget, &isValidationRoutePackEntry, &recordValidationRouteTrashKill](Unit* prerequisiteTarget, char const* context) -> bool
    {
        return MaybeValidationPrerequisiteNoProgressAssist(state, bot, power,
            stage, activity, isValidationRouteScriptTarget,
            isValidationRoutePackEntry, recordValidationRouteTrashKill,
            prerequisiteTarget, context);
    };
    auto routeFocusMemoryFresh = [this, bot]() -> bool
    {
        return !Party().ValidationRouteFocusGuid.IsEmpty()
            && Party().ValidationRouteFocusMapId == bot->GetMapId()
            && Party().ValidationRouteFocusSeenMs
            && NowMs() - Party().ValidationRouteFocusSeenMs <= (Cohort().Config.ValidationRouteKind == "boss" ? 60000 : 20000);
    };
    auto routeUsableValidationFocus = [this, &routeUsableCombatTarget,
        &isValidationRouteObjectiveTarget, &isValidationCohortCombatLinked](Unit* focus) -> Unit*
    {
        focus = routeUsableCombatTarget(focus);
        if (!focus)
            return nullptr;

        if (Cohort().Config.ValidationRouteKind != "boss" || !Party().ValidationRouteActivationApplied
            || isValidationRouteObjectiveTarget(focus->ToCreature())
            || focus->IsInCombat() || focus->GetVictim())
            return focus;

        Creature* creature = focus->ToCreature();
        return creature && isValidationCohortCombatLinked(creature) ? focus : nullptr;
    };
    auto routeGroupFocusTarget = [this, bot, &routeUsableValidationFocus, &routeFocusMemoryFresh]() -> Unit*
    {
        return FindValidationRouteGroupFocusTarget(bot,
            routeUsableValidationFocus, routeFocusMemoryFresh);
    };
    auto routeTankFocusGuid = [this, bot, &routeUsableValidationFocus, &routeFocusMemoryFresh]() -> ObjectGuid
    {
        return FindValidationRouteTankFocusGuid(bot,
            routeUsableValidationFocus, routeFocusMemoryFresh);
    };
    auto rememberValidationRouteFocus = [this](Unit* focus)
    {
        RememberValidationRouteFocus(focus);
    };
    auto makeExistingValidationRouteCombatReady = [this, bot, &isValidationRouteCombatTarget](Creature* creature) -> Unit*
    {
        return MakeExistingValidationRouteCombatReady(bot, creature,
            isValidationRouteCombatTarget);
    };
    auto tryValidationRouteActivation = [this, &state, bot, &power, stage, activity](Unit* seenTarget, char const* reason) -> bool
    {
        return TryValidationRouteActivation(state, bot, power, stage,
            activity, seenTarget, reason);
    };
    auto routeTankFocusTarget = [this, bot, &routeUsableCombatTarget](ObjectGuid expectedGuid) -> Unit*
    {
        return FindValidationRouteTankFocusTarget(bot,
            routeUsableCombatTarget, expectedGuid);
    };
    auto routeFocusMemoryActive = [&routeFocusMemoryFresh]() -> bool
    {
        return routeFocusMemoryFresh();
    };
    auto authoritativeRouteFocusActive = [&]() -> bool
    {
        return routeFocusMemoryActive();
    };
    auto findLastKnownFocusTarget = [this, bot, &routeUsableCombatTarget, &routeFocusMemoryFresh]() -> Unit*
    {
        return FindLastKnownValidationRouteFocusTarget(bot,
            routeUsableCombatTarget, routeFocusMemoryFresh);
    };
    std::string authoritativeFocusFailure = "authoritative_focus_not_checked";
    auto findAuthoritativeRouteFocusTarget = [this, bot, &routeUsableCombatTarget, &isValidationRouteScriptTarget, &authoritativeFocusFailure]() -> Unit*
    {
        return FindAuthoritativeValidationRouteFocusTarget(bot,
            routeUsableCombatTarget, isValidationRouteScriptTarget,
            authoritativeFocusFailure);
    };
    auto recoverAuthoritativeFocus = [this, &state, bot, &power, stage, activity, &findAuthoritativeRouteFocusTarget, &authoritativeFocusFailure](char const* context) -> bool
    {
        return RecoverAuthoritativeValidationRouteFocus(state, bot, power,
            stage, activity, findAuthoritativeRouteFocusTarget,
            authoritativeFocusFailure, context);
    };
    auto teacherAssistAuthoritativeFocus = [this, &state, &authoritativeRouteFocusActive, &findAuthoritativeRouteFocusTarget, &authoritativeFocusFailure](Unit* proposedFocus) -> Unit*
    {
        return this->TeacherAssistAuthoritativeValidationFocus(state, proposedFocus,
            authoritativeRouteFocusActive, findAuthoritativeRouteFocusTarget,
            authoritativeFocusFailure);
    };

    uint32 routeAnchorMapId = Cohort().Config.ValidationRouteMapId ? Cohort().Config.ValidationRouteMapId : bot->GetMapId();
    float routeAnchorX = Cohort().Config.ValidationRouteX;
    float routeAnchorY = Cohort().Config.ValidationRouteY;
    float routeAnchorZ = Cohort().Config.ValidationRouteZ;
    std::string routeAnchorReason = "validation_route";
    uint64 routeNowMs = NowMs();
    if (state.ValidationRouteAnchorOverrideValid && state.ValidationRouteAnchorOverrideUntilMs <= routeNowMs)
    {
        state.ValidationRouteAnchorOverrideValid = false;
        state.ValidationRouteAnchorOverrideReason.clear();
    }
    bool routeHasActiveCombatIntent = routeUsableCombatTarget(target)
        || routeUsableCombatTarget(bot->GetVictim())
        || !routeTankFocusGuid().IsEmpty();
    bool routeHasCurrentGenerationLivePackAuthority =
        Cohort().Config.ValidationRouteKind != "boss"
        && persistedValidationRoutePackHasLiveMembers();
    bool repeatedDeathNearRoute = state.LastDeathMapId == routeAnchorMapId
        && Distance2d(state.LastDeathX, state.LastDeathY, Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY) <= 70.0f
        && state.RecentDeathCount >= 2;
    bool partialWipeRetreatRendezvous =
        state.ValidationRouteAnchorOverrideValid
        && state.ValidationRouteAnchorOverrideReason
            == "validation_route_partial_wipe_retreat_rendezvous";
    // A current-generation live pack is stronger route authority than the
    // generic safe-memory fallback.  Clear only that fallback here; the
    // partial-wipe rendezvous and live-pack reapproach overrides retain their
    // existing recovery semantics.
    if (state.ValidationRouteAnchorOverrideValid
        && state.ValidationRouteAnchorOverrideReason
            == "validation_route_safe_memory_after_death_loop"
        && routeHasCurrentGenerationLivePackAuthority)
    {
        state.ValidationRouteAnchorOverrideValid = false;
        state.ValidationRouteAnchorOverrideUntilMs = 0;
        state.ValidationRouteAnchorOverrideReason.clear();
    }
    if (state.ValidationRouteAnchorOverrideValid && routeHasActiveCombatIntent
        && !repeatedDeathNearRoute && !partialWipeRetreatRendezvous)
    {
        state.ValidationRouteAnchorOverrideValid = false;
        state.ValidationRouteAnchorOverrideUntilMs = 0;
        state.ValidationRouteAnchorOverrideReason.clear();
    }
    float routeAnchorDanger = GetLocalDangerScore(state.Guid.GetCounter(), routeAnchorMapId, routeAnchorX, routeAnchorY, routeAnchorZ);
    if (state.ValidationRouteAnchorOverrideValid)
    {
        routeAnchorX = state.ValidationRouteAnchorOverrideX;
        routeAnchorY = state.ValidationRouteAnchorOverrideY;
        routeAnchorZ = state.ValidationRouteAnchorOverrideZ;
        routeAnchorReason = state.ValidationRouteAnchorOverrideReason.empty() ? "validation_route_safe_memory_override" : state.ValidationRouteAnchorOverrideReason;
    }
    else if (!routeHasActiveCombatIntent && repeatedDeathNearRoute
        && !routeHasCurrentGenerationLivePackAuthority)
    {
        PruneSafePositions(state, routeNowMs);

        WorldBotState::SafePosition const* bestSafe = nullptr;
        float bestSafeScore = std::numeric_limits<float>::max();
        for (WorldBotState::SafePosition const& safe : state.SafePositions)
        {
            if (safe.MapId != routeAnchorMapId || safe.HpPct < 0.35f)
                continue;

            float safeRouteDistance = Distance2d(safe.X, safe.Y, Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY);
            if (safeRouteDistance > 260.0f)
                continue;
            if (state.RecentDeathCount >= 2
                && state.LastDeathMapId == routeAnchorMapId
                && Distance2d(state.LastDeathX, state.LastDeathY, safe.X, safe.Y) <= 70.0f)
                continue;

            // Rerun162 selected a remembered post-death anchor whose stored Z
            // could not satisfy MoveBotToPoint's floor contract. Installing it
            // as the long-lived override made the final Azil generation
            // terminal while the canonical manifest anchor remained valid.
            // Apply the exact movement gate before ranking remembered anchors;
            // an invalid memory simply leaves the canonical anchor available.
            Map* safeMap = bot->GetMap();
            float safeFloorZ = safeMap
                ? safeMap->GetHeight(bot->GetPhaseShift(), safe.X, safe.Y,
                    safe.Z + 2.0f, true, 8.0f)
                : INVALID_HEIGHT;
            if (safeFloorZ <= INVALID_HEIGHT
                || std::fabs(safeFloorZ - safe.Z) > 4.0f)
                continue;

            float safeDanger = GetLocalDangerScore(state.Guid.GetCounter(), routeAnchorMapId, safe.X, safe.Y, safe.Z);
            if (safeDanger >= routeAnchorDanger && safeDanger >= 3.0f)
                continue;

            float botDistance = bot->GetExactDist(safe.X, safe.Y, safe.Z);
            float score = safeDanger * 100.0f + safeRouteDistance * 0.20f + botDistance * 0.02f - safe.HpPct * 10.0f;
            if (safeRouteDistance > 135.0f)
                score += 80.0f;
            if (!bestSafe || score < bestSafeScore)
            {
                bestSafe = &safe;
                bestSafeScore = score;
            }
        }

        if (bestSafe)
        {
            routeAnchorX = bestSafe->X;
            routeAnchorY = bestSafe->Y;
            routeAnchorZ = bestSafe->Z;
            routeAnchorReason = "validation_route_safe_memory_after_death_loop";
            state.ValidationRouteAnchorOverrideValid = true;
            state.ValidationRouteAnchorOverrideUntilMs = routeNowMs + 120000;
            state.ValidationRouteAnchorOverrideX = routeAnchorX;
            state.ValidationRouteAnchorOverrideY = routeAnchorY;
            state.ValidationRouteAnchorOverrideZ = routeAnchorZ;
            state.ValidationRouteAnchorOverrideReason = routeAnchorReason;

            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_recovery", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_recovery", nullptr, routeAnchorReason.c_str(), raw.c_str(), semantic.c_str(), routeAnchorDanger, Cohort().Config.ValidationRouteTargetEntry);
        }
    }

    Map* routeMap = bot->GetMap();
    if (routeMap)
    {
        float floorZ = routeMap->GetHeight(bot->GetPhaseShift(), routeAnchorX, routeAnchorY, routeAnchorZ + 2.0f, true, 8.0f);
        if (floorZ > INVALID_HEIGHT && std::fabs(floorZ - routeAnchorZ) <= 8.0f)
            routeAnchorZ = floorZ;
    }

    state.QuestRouteDestination.Valid = true;
    state.QuestRouteDestination.MapId = routeAnchorMapId;
    state.QuestRouteDestination.X = routeAnchorX;
    state.QuestRouteDestination.Y = routeAnchorY;
    state.QuestRouteDestination.Z = routeAnchorZ;
    state.QuestRouteDestination.QuestId = 0;
    state.QuestRouteDestination.Reason = routeAnchorReason;

    float routeDistance = bot->GetExactDist(routeAnchorX, routeAnchorY, routeAnchorZ);
    float canonicalRouteDistance = bot->GetExactDist(
        Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ);
    auto moveToRouteAnchor = [&]() -> bool
    {
        // Ordinary descents use progressive native walking and, only at a
        // locally verified ledge, a bounded player-like jump. Preserve a
        // rejected segment as diagnostic evidence without terminalizing the
        // route so the next observation can reconcile changed geometry.
        bool terminalOnFailure = Cohort().Config.ValidationRouteKind != "descent";
        return MoveBotToPoint(state, bot, routeAnchorX, routeAnchorY, routeAnchorZ, terminalOnFailure);
    };
    auto routeFocusTankOwned = [this, bot](Unit* focus) -> bool
    {
        Unit* victim = focus ? focus->GetVictim() : nullptr;
        Player* victimPlayer = victim ? victim->ToPlayer() : nullptr;
        return victimPlayer
            && victimPlayer->GetMap() == bot->GetMap()
            && std::string(GetDungeonRole(victimPlayer)) == "tank";
    };
    auto validationRouteHasLivingTank = [this, bot]() -> bool
    {
        for (WorldBotState const& cohortState : Party().Bots)
            if (Player* member = GetBot(cohortState); member && member->IsAlive()
                && member->GetMap() == bot->GetMap() && std::string(GetDungeonRole(member)) == "tank")
                return true;
        return false;
    };
    bool hasValidationRouteActivation = Cohort().Config.ValidationRouteActivationAreaTriggerId
        || Cohort().Config.ValidationRouteActivationDataId
        || Cohort().Config.ValidationRouteActivationSpawnGroupId
        || Cohort().Config.ValidationRouteActivationActionEntry
        || Cohort().Config.ValidationRouteActivationSummonEntry
        || Cohort().Config.ValidationRouteOpenerSummonEntry
        || (Cohort().Config.ValidationRouteKind == "boss" && Cohort().Config.ValidationRouteTargetEntry);
    float routeArrivalRadius = 18.0f;
    if (Cohort().Config.ValidationRouteKind == "boss")
    {
        BotClassSpecActionProfile routeProfile = BotClassSpecActionProfileStore::Build(bot, GetDungeonRole(bot));
        routeArrivalRadius = routeProfile.MovementDirective == "melee" ? 8.0f : 30.0f;
    }
    auto tryValidationRouteInterrupt = [this, &state, bot, &power, stage, activity, &situation, &action](Unit* interruptTarget, char const* context) -> bool
    {
        return TryValidationRouteInterrupt(state, bot, power, stage, activity,
            situation, action, interruptTarget, context);
    };
    auto tryValidationRouteMovementCheck = [this, &state, bot, &power, stage,
        activity, &situation, &action, &isValidationCohortCombatLinked,
        &tryRouteGroupHeal](Unit* preferredTarget) -> bool
    {
        if (!bot
            || !bot->IsAlive()
            || bot->IsFalling())
            return false;

        using HazardDefinition = BotWorldValidationHazards::Definition;
        using ActiveHazard = BotWorldValidationHazards::Active;
        std::vector<HazardDefinition> hazardDefinitions =
            BotWorldValidationHazards::BuildDefinitions(
                Cohort().Config.ValidationRouteHazardSourceEntry,
                Cohort().Config.ValidationRouteHazardDetectionSpellId,
                Cohort().Config.ValidationRouteHazardDamageSpellId,
                Cohort().Config.ValidationRouteHazardShape,
                Cohort().Config.ValidationRouteHazardRadiusYards,
                Cohort().Config.ValidationRouteHazardSafetyMarginYards);

        // Hazard geometry belongs to the active route node. Importing every
        // later manifest node here made ordinary opening-pack casts inherit
        // Slabhide, Flayer, and Azil dodge behavior before those encounters.
        bool profileAllowsGenericCastMovement = Cohort().Config.ValidationRouteMechanicProfile.find("movement_check") != std::string::npos
            || Cohort().Config.ValidationRouteMechanicProfile.find("ground_danger") != std::string::npos;
        bool mechanicProfileRequiresMovement = profileAllowsGenericCastMovement || !hazardDefinitions.empty();
        bool currentNodeHasConfiguredHazard = Cohort().Config.ValidationRouteHazardSourceEntry != 0;
        auto hazardDefinitionFor = [&hazardDefinitions](uint32 sourceEntry, uint32 spellId) -> HazardDefinition const*
        {
            return BotWorldValidationHazards::FindDefinition(
                hazardDefinitions, sourceEntry, spellId);
        };
        std::vector<ActiveHazard> activeHazards;
        auto hazardIsActive = [bot](Creature* hazard, HazardDefinition const* definition) -> bool
        {
            return BotWorldValidationHazards::IsActive(bot, hazard, definition);
        };
        auto refreshActiveHazards = [&]()
        {
            activeHazards = BotWorldValidationHazards::FindActive(
                bot, hazardDefinitions, mechanicProfileRequiresMovement);
        };
        auto positionOutsideHazard = [](ActiveHazard const& hazard, Position const& position) -> bool
        {
            return BotWorldValidationHazards::PositionOutside(
                hazard, position.GetPositionX(), position.GetPositionY());
        };
        auto positionOutsideActiveHazards = [&](Position const& position) -> bool
        {
            return BotWorldValidationHazards::PositionsOutside(
                activeHazards, position.GetPositionX(), position.GetPositionY());
        };
        auto pathOutsideActiveHazards = [&](float x, float y, float z) -> bool
        {
            return BotWorldValidationHazards::PathOutside(
                bot, activeHazards, x, y, z);
        };
        auto isScopedGenericCastCandidate = [this, &hazardDefinitionFor, &isValidationCohortCombatLinked,
            currentNodeHasConfiguredHazard](Unit* candidate) -> bool
        {
            if (!currentNodeHasConfiguredHazard)
                return true;

            Creature* creature = candidate ? candidate->ToCreature() : nullptr;
            if (!creature || hazardDefinitionFor(creature->GetEntry(), 0)
                || Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration
                || Party().ValidationRoutePackMemberGuids.find(creature->GetGUID())
                    == Party().ValidationRoutePackMemberGuids.end()
                || Party().ValidationRoutePackDeathGuids.find(creature->GetGUID())
                    != Party().ValidationRoutePackDeathGuids.end()
                || Party().ValidationRoutePackTransitionGuids.find(creature->GetGUID())
                    != Party().ValidationRoutePackTransitionGuids.end())
                return false;

            return isValidationCohortCombatLinked(creature);
        };
        uint64 const nowMs = NowMs();
        auto tryFeralInFlightHazardHealerRoar = [&]() -> bool
        {
            BotClassSpecActionProfile hazardProfile = BotClassSpecActionProfileStore::Build(
                bot, GetDungeonRole(bot));
            if (hazardProfile.SpecTag != "feral_druid_tank"
                || !bot->IsInCombat() || !bot->HasSpell(99))
                return false;

            Unit* nearbyHealerOwnedAttacker = nullptr;
            uint32 nearbyHealerOwnedCount = 0;
            float nearestDistance = std::numeric_limits<float>::max();
            uint32 nearestGuid = std::numeric_limits<uint32>::max();
            std::vector<WorldObject*> objects;
            Trinity::AllWorldObjectsInRange check(bot, 45.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(
                bot, objects, check);
            Cell::VisitAllObjects(bot, searcher, 45.0f);
            for (WorldObject* object : objects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                Player* victim = creature && creature->GetVictim()
                    ? creature->GetVictim()->ToPlayer() : nullptr;
                if (!creature || !creature->IsAlive() || !creature->GetHealth()
                    || !bot->IsValidAttackTarget(creature) || !victim
                    || GetDungeonRole(victim) != "healer"
                    || (bot->GetGroup() ? victim->GetGroup() != bot->GetGroup()
                                        : victim != bot)
                    || bot->GetExactDist2d(creature) > 10.0f)
                    continue;

                ++nearbyHealerOwnedCount;
                float distance = bot->GetExactDist(creature);
                uint32 guid = creature->GetGUID().GetCounter();
                if (!nearbyHealerOwnedAttacker || distance < nearestDistance
                    || (distance == nearestDistance && guid < nearestGuid))
                {
                    nearbyHealerOwnedAttacker = creature;
                    nearestDistance = distance;
                    nearestGuid = guid;
                }
            }
            if (nearbyHealerOwnedCount < 2
                || !TryCastFriendlySpell(bot, bot, 99))
                return false;

            // Rerun101 proved the native in-flight Roar immediately recovers
            // an exposed strict-hazard wave, but rerun133 still sampled six
            // healer-owned identities 503 ms after a Roar submitted at 2528 ms,
            // crossing the dwell ceiling by 31 ms. Preserve the accepted exit
            // path and observe only this active pickup at 250 ms cadence.
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);

            std::string raw = BuildRawJson(bot, nearbyHealerOwnedAttacker);
            std::string semantic = BuildSemanticJson(
                bot, nearbyHealerOwnedAttacker, "validation_route_mechanic",
                &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup",
                nearbyHealerOwnedAttacker,
                "feral_in_flight_hazard_healer_roar",
                raw.c_str(), semantic.c_str(),
                float(nearbyHealerOwnedCount),
                Cohort().Config.ValidationRouteTargetEntry, 99);
            state.TargetGuid = nearbyHealerOwnedAttacker
                ? nearbyHealerOwnedAttacker->GetGUID() : ObjectGuid::Empty;
            state.WasInCombat = true;
            situation = "validation_route_mechanic";
            action = "feral_in_flight_hazard_healer_roar";
            return true;
        };
        auto tryFeralInFlightHazardLooseTaunt = [&]() -> bool
        {
            BotClassSpecActionProfile hazardProfile = BotClassSpecActionProfileStore::Build(
                bot, GetDungeonRole(bot));
            if (hazardProfile.SpecTag != "feral_druid_tank"
                || !bot->IsInCombat() || !bot->HasSpell(6795))
                return false;

            Creature* looseAttacker = nullptr;
            uint8 bestPriority = 0;
            float bestDistance = std::numeric_limits<float>::max();
            uint32 bestGuid = std::numeric_limits<uint32>::max();
            std::vector<WorldObject*> objects;
            Trinity::AllWorldObjectsInRange check(bot, 45.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
            Cell::VisitAllObjects(bot, searcher, 45.0f);
            for (WorldObject* object : objects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                Player* victim = creature && creature->GetVictim()
                    ? creature->GetVictim()->ToPlayer() : nullptr;
                if (!creature || !creature->IsAlive() || !creature->GetHealth()
                    || !bot->IsValidAttackTarget(creature) || !victim
                    || (bot->GetGroup() ? victim->GetGroup() != bot->GetGroup() : victim != bot))
                    continue;

                std::string victimRole = GetDungeonRole(victim);
                if (victimRole == "tank")
                    continue;
                // Boss-add encounters can activate an overlapping healer wave
                // inside Growl's cooldown. Rerun76 spent Growl on a DPS
                // attacker while healer exposure was zero, then could not
                // taunt the following Azil wave until its dwell gate had
                // already expired. Trash hazards retain generalized party
                // pickup; declared boss-add nodes reserve Growl for the healer.
                bool declaredBossAddEncounter =
                    Cohort().Config.ValidationRouteKind == "boss"
                    && !Cohort().Config.ValidationRouteAddTargetEntries.empty()
                    && Cohort().Config.ValidationRouteMechanicProfile.find("adds")
                        != std::string::npos;
                if (declaredBossAddEncounter && victimRole != "healer")
                    continue;
                uint8 priority = victimRole == "healer" ? 2 : 1;
                float distance = bot->GetExactDist(creature);
                uint32 guid = creature->GetGUID().GetCounter();
                if (!looseAttacker || priority > bestPriority
                    || (priority == bestPriority && (distance < bestDistance
                        || (distance == bestDistance && guid < bestGuid))))
                {
                    looseAttacker = creature;
                    bestPriority = priority;
                    bestDistance = distance;
                    bestGuid = guid;
                }
            }
            if (!looseAttacker || !TryCastCombatSpell(bot, looseAttacker, 6795))
                return false;

            Player* victim = looseAttacker->GetVictim()
                ? looseAttacker->GetVictim()->ToPlayer() : nullptr;
            bool healerVictim = GetDungeonRole(victim) == "healer";
            if (healerVictim)
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
            std::string raw = BuildRawJson(bot, looseAttacker);
            std::string semantic = BuildSemanticJson(
                bot, looseAttacker, "validation_route_mechanic", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup", looseAttacker,
                healerVictim
                    ? "feral_in_flight_hazard_healer_growl"
                    : "feral_in_flight_hazard_party_growl",
                raw.c_str(), semantic.c_str(),
                bestDistance, Cohort().Config.ValidationRouteTargetEntry, 6795);
            state.TargetGuid = looseAttacker->GetGUID();
            state.WasInCombat = true;
            situation = "validation_route_mechanic";
            action = healerVictim
                ? "feral_in_flight_hazard_healer_growl"
                : "feral_in_flight_hazard_party_growl";
            return true;
        };
        auto tryHealerInFlightHazardFade = [&]() -> bool
        {
            if (std::string(GetDungeonRole(bot)) != "healer"
                || !bot->IsInCombat() || !bot->HasSpell(586)
                || bot->HasAura(586))
                return false;

            size_t healerTargetingHostileCount = 0;
            std::vector<WorldObject*> objects;
            Trinity::AllWorldObjectsInRange check(bot, 45.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(
                bot, objects, check);
            Cell::VisitAllObjects(bot, searcher, 45.0f);
            for (WorldObject* object : objects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                if (creature && creature->IsAlive() && creature->GetHealth()
                    && bot->IsValidAttackTarget(creature)
                    && creature->GetVictim() == bot)
                    ++healerTargetingHostileCount;
            }
            // Rerun114 passed Feral all-hostile retention, but Fade was spent
            // on a transient two-hostile transfer that cleared by the next
            // sample. It was then unavailable for the ten-hostile Flayer
            // hazard transfer responsible for the entire 8.120-second dwell
            // failure. Rerun116 then showed a three-attacker precursor still
            // consuming Fade before a 20-hostile Flayer transfer. Reserve the
            // existing native threat drop for nine or more exact-party
            // attackers. Rerun117 proved the precursor peaks at eight while
            // the sustained follow-up reaches eleven inside acquisition grace.
            // Hazard geometry remains unchanged.
            if (healerTargetingHostileCount < 9
                || !TryCastFriendlySpell(bot, bot, 586))
                return false;

            std::string raw = BuildRawJson(bot, preferredTarget);
            std::string semantic = BuildSemanticJson(
                bot, preferredTarget, "validation_route_mechanic",
                &power, stage, activity);
            RecordEvent(state, bot, "healer_assignment", bot,
                "fade_in_flight_hazard_threat_drop",
                raw.c_str(), semantic.c_str(),
                float(healerTargetingHostileCount),
                Cohort().Config.ValidationRouteTargetEntry, 586);
            situation = "validation_route_mechanic";
            action = "fade_in_flight_hazard_threat_drop";
            state.WasInCombat = true;
            return true;
        };
        auto tryTankHazardHoldAreaThreat = [&](Unit* activeHazard, float safeRadius,
            bool radialHazard, bool allowMovement = true) -> bool
        {
            if (std::string(GetDungeonRole(bot)) != "tank" || !bot->IsInCombat())
                return false;

            std::vector<WorldObject*> objects;
            Trinity::AllWorldObjectsInRange check(bot, 45.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
            Cell::VisitAllObjects(bot, searcher, 45.0f);
            std::vector<Creature*> engagedHostiles;
            for (WorldObject* object : objects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                if (!creature || !creature->IsAlive() || !creature->GetHealth()
                    || !bot->IsValidAttackTarget(creature) || (!creature->IsInCombat() && !creature->GetVictim()))
                    continue;
                Player* victim = creature->GetVictim() ? creature->GetVictim()->ToPlayer() : nullptr;
                if (!victim || (bot->GetGroup() ? victim->GetGroup() != bot->GetGroup() : victim != bot))
                    continue;
                engagedHostiles.push_back(creature);
            }
            uint32 engagedCount = engagedHostiles.size();
            if (engagedCount < 2)
                return false;

            // Rerun86 showed the generic hazard area resolver selecting Thrash
            // while a local healer-owned cluster remained exposed for 8.061
            // seconds. Prefer the existing native self-centered Roar when at
            // least two such hostiles are already inside its exact ten-yard
            // radius. This does not alter the accepted hazard path.
            if (tryFeralInFlightHazardHealerRoar())
                return true;

            // Growl remains the instant single-target fallback and does not
            // replace the accepted hazard path or the area-threat resolver
            // below. Rerun75 showed non-healer party attackers can otherwise
            // remain loose through an entire safe-side hold.
            tryFeralInFlightHazardLooseTaunt();

            // A nearest hostile can sit on the safe-side edge while most of a
            // newly activated wave remains around the healer. Select the densest
            // exact-party cluster first, preserving victim-role priority and
            // deterministic distance/GUID tie-breaks.
            Unit* areaTarget = nullptr;
            uint8 areaPriority = 0;
            uint32 areaClusterCount = 0;
            float areaDistance = std::numeric_limits<float>::max();
            uint32 areaGuid = std::numeric_limits<uint32>::max();
            for (Creature* creature : engagedHostiles)
            {
                Player* victim = creature->GetVictim() ? creature->GetVictim()->ToPlayer() : nullptr;
                std::string victimRole = GetDungeonRole(victim);
                uint8 priority = victimRole == "healer" ? 3 : (victimRole == "tank" ? 1 : 2);
                uint32 clusterCount = 0;
                for (Creature* neighbor : engagedHostiles)
                    if (creature->GetExactDist2d(neighbor) <= 10.0f)
                        ++clusterCount;
                float distance = bot->GetExactDist(creature);
                uint32 guid = creature->GetGUID().GetCounter();
                if (!areaTarget || priority > areaPriority
                    || (priority == areaPriority && clusterCount > areaClusterCount)
                    || (priority == areaPriority && clusterCount == areaClusterCount
                        && (distance < areaDistance
                            || (distance == areaDistance && guid < areaGuid))))
                {
                    areaTarget = creature;
                    areaPriority = priority;
                    areaClusterCount = clusterCount;
                    areaDistance = distance;
                    areaGuid = guid;
                }
            }

            BotClassSpecActionProfile hazardProfile = BotClassSpecActionProfileStore::Build(
                bot, GetDungeonRole(bot));
            // Rerun173's only over-ceiling dwell began when an Azil follower
            // selected the healer after Hammer of the Righteous had landed on
            // a different add. The accepted radial hazard exit then returned
            // before Protection's ordinary single-target rescue for 4032 ms.
            // Hand of Reckoning is instant and does not replace or clear that
            // movement. Try it only against the deterministic healer-priority
            // hostile; failures preserve the area-threat and safe-path chain.
            // Rerun187 then presented two new healer-owned hostiles together.
            // The single taunt acquired one, but its cooldown left the second
            // behind while this hazard hold preempted ordinary Righteous
            // Defense for 3573 ms. Keep the single taunt first, then use the
            // existing native multi-attacker rescue on the healer before the
            // bounded safe-side hold. All native spell gates remain unchanged.
            if (hazardProfile.SpecTag == "protection"
                && bot->getClass() == CLASS_PALADIN
                && areaPriority == 3 && areaTarget)
            {
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                if (bot->HasSpell(62124)
                    && TryCastCombatSpell(bot, areaTarget, 62124))
                {
                    std::string raw = BuildRawJson(bot, areaTarget);
                    std::string semantic = BuildSemanticJson(
                        bot, areaTarget, "validation_route_mechanic",
                        &power, stage, activity);
                    RecordEvent(state, bot,
                        "validation_route_threat_pickup", areaTarget,
                        "hand_of_reckoning_hazard_healer_pickup",
                        raw.c_str(), semantic.c_str(), areaDistance,
                        Cohort().Config.ValidationRouteTargetEntry, 62124);
                    state.TargetGuid = areaTarget->GetGUID();
                    state.WasInCombat = true;
                    situation = "validation_route_mechanic";
                    action = "hand_of_reckoning_hazard_healer_pickup";
                    return true;
                }
                Player* hazardHealer = areaTarget->GetVictim()
                    ? areaTarget->GetVictim()->ToPlayer() : nullptr;
                if (hazardHealer
                    && GetDungeonRole(hazardHealer) == "healer"
                    && bot->HasSpell(31789)
                    && TryCastFriendlySpell(bot, hazardHealer, 31789))
                {
                    std::string raw = BuildRawJson(bot, hazardHealer);
                    std::string semantic = BuildSemanticJson(
                        bot, hazardHealer, "validation_route_mechanic",
                        &power, stage, activity);
                    RecordEvent(state, bot,
                        "validation_route_threat_pickup", hazardHealer,
                        "righteous_defense_hazard_healer_pickup",
                        raw.c_str(), semantic.c_str(), areaDistance,
                        Cohort().Config.ValidationRouteTargetEntry, 31789);
                    state.TargetGuid = areaTarget->GetGUID();
                    state.WasInCombat = true;
                    situation = "validation_route_mechanic";
                    action = "righteous_defense_hazard_healer_pickup";
                    return true;
                }
            }
            auto tryFeralHazardThrashRetention = [&]() -> bool
            {
                // Rerun159 localized all Feral healer exposure to a fully
                // tank-owned 53-hostile wave that lost ten identities during
                // strict hazard movement immediately after native Swipe. Try
                // the known persistent native area spell before movement; if
                // any native legality gate rejects it, preserve the existing
                // Charge, safe path, profile resolver, and Swipe fallbacks.
                if (hazardProfile.SpecTag != "feral_druid_tank"
                    || engagedCount < 12 || !areaTarget
                    || !bot->HasSpell(77758)
                    || !TryCastCombatSpell(bot, areaTarget, 77758))
                    return false;

                std::string raw = BuildRawJson(bot, areaTarget);
                std::string semantic = BuildSemanticJson(
                    bot, areaTarget, "validation_route_mechanic",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    areaTarget, "feral_thrash_hazard_secure_threat_retention",
                    raw.c_str(), semantic.c_str(), float(engagedCount),
                    Cohort().Config.ValidationRouteTargetEntry, 77758);
                state.TargetGuid = areaTarget->GetGUID();
                state.WasInCombat = true;
                situation = "validation_route_mechanic";
                action = "feral_thrash_hazard_secure_threat_retention";
                return true;
            };
            auto tryFeralHazardSwipeMargin = [&]() -> bool
            {
                if (hazardProfile.SpecTag != "feral_druid_tank"
                    || engagedCount < 12 || !bot->HasSpell(779))
                    return false;

                Creature* swipeTarget = nullptr;
                float swipeDistance = std::numeric_limits<float>::max();
                uint32 swipeGuid = std::numeric_limits<uint32>::max();
                for (Creature* creature : engagedHostiles)
                {
                    float distance = bot->GetExactDist(creature);
                    uint32 guid = creature->GetGUID().GetCounter();
                    if (!swipeTarget || distance < swipeDistance
                        || (distance == swipeDistance && guid < swipeGuid))
                    {
                        swipeTarget = creature;
                        swipeDistance = distance;
                        swipeGuid = guid;
                    }
                }
                if (!swipeTarget
                    || !TryCastCombatSpell(bot, swipeTarget, 779))
                    return false;

                std::string raw = BuildRawJson(bot, swipeTarget);
                std::string semantic = BuildSemanticJson(
                    bot, swipeTarget, "validation_route_mechanic",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    swipeTarget, "feral_swipe_hazard_secure_threat_margin",
                    raw.c_str(), semantic.c_str(), float(engagedCount),
                    Cohort().Config.ValidationRouteTargetEntry, 779);
                state.TargetGuid = swipeTarget->GetGUID();
                state.WasInCombat = true;
                situation = "validation_route_mechanic";
                action = "feral_swipe_hazard_secure_threat_margin";
                return true;
            };
            // The safe-side movement branch below already uses the lower
            // cadence, but rerun133's accepted in-flight path returned through
            // Roar, Growl, area threat, or the bounded hold before reaching it.
            // Observe the deterministic healer-owned target at 250 ms cadence;
            // spell and movement legality remain unchanged.
            if (hazardProfile.SpecTag == "feral_druid_tank"
                && areaPriority == 3)
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
            if (tryFeralHazardThrashRetention())
                return true;
            auto radialChargePathSafe = [&](Unit* chargeTarget) -> bool
            {
                if (!chargeTarget || !radialHazard || !activeHazard || safeRadius <= 0.0f)
                    return false;
                float fromX = bot->GetPositionX();
                float fromY = bot->GetPositionY();
                float toX = chargeTarget->GetPositionX();
                float toY = chargeTarget->GetPositionY();
                float deltaX = toX - fromX;
                float deltaY = toY - fromY;
                float segmentLengthSq = deltaX * deltaX + deltaY * deltaY;
                float projection = 0.0f;
                if (segmentLengthSq > 0.01f)
                    projection = std::clamp(
                        ((activeHazard->GetPositionX() - fromX) * deltaX
                            + (activeHazard->GetPositionY() - fromY) * deltaY)
                            / segmentLengthSq,
                        0.0f, 1.0f);
                float closestX = fromX + projection * deltaX;
                float closestY = fromY + projection * deltaY;
                return Distance2d(
                    closestX, closestY,
                    activeHazard->GetPositionX(), activeHazard->GetPositionY())
                    > safeRadius + 0.5f;
            };
            auto radialGroundPathSafe = [&](Unit* movementTarget) -> bool
            {
                if (!movementTarget || !radialHazard || !activeHazard
                    || safeRadius <= 0.0f)
                    return false;

                PathGenerator path(bot);
                if (!path.CalculatePath(
                        movementTarget->GetPositionX(),
                        movementTarget->GetPositionY(),
                        movementTarget->GetPositionZ(), false))
                    return false;
                PathType pathType = path.GetPathType();
                if ((pathType & PATHFIND_NOPATH)
                    || (pathType & PATHFIND_NOT_USING_PATH)
                    || (pathType & PATHFIND_INCOMPLETE)
                    || (pathType & PATHFIND_SHORTCUT)
                    || (pathType & PATHFIND_FARFROMPOLY))
                    return false;

                for (G3D::Vector3 const& point : path.GetPath())
                    if (Distance2d(
                            point.x, point.y,
                            activeHazard->GetPositionX(),
                            activeHazard->GetPositionY())
                        <= safeRadius + 0.5f)
                        return false;
                return true;
            };

            Unit* chargeTarget = nullptr;
            uint8 chargePriority = 0;
            uint32 chargeClusterCount = 0;
            float chargeDistance = std::numeric_limits<float>::max();
            uint32 chargeGuid = std::numeric_limits<uint32>::max();
            if (hazardProfile.SpecTag == "feral_druid_tank" && engagedCount >= 3)
                for (Creature* creature : engagedHostiles)
                {
                    float distance = bot->GetExactDist(creature);
                    if (distance <= 8.0f || !radialChargePathSafe(creature))
                        continue;
                    Player* victim = creature->GetVictim() ? creature->GetVictim()->ToPlayer() : nullptr;
                    std::string victimRole = GetDungeonRole(victim);
                    uint8 priority = victimRole == "healer" ? 3 : (victimRole == "tank" ? 1 : 2);
                    uint32 clusterCount = 0;
                    for (Creature* neighbor : engagedHostiles)
                        if (creature->GetExactDist2d(neighbor) <= 10.0f)
                            ++clusterCount;
                    uint32 guid = creature->GetGUID().GetCounter();
                    if (!chargeTarget || priority > chargePriority
                        || (priority == chargePriority && clusterCount > chargeClusterCount)
                        || (priority == chargePriority && clusterCount == chargeClusterCount
                            && (distance < chargeDistance
                                || (distance == chargeDistance && guid < chargeGuid))))
                    {
                        chargeTarget = creature;
                        chargePriority = priority;
                        chargeClusterCount = clusterCount;
                        chargeDistance = distance;
                        chargeGuid = guid;
                    }
                }

            if (allowMovement && chargeTarget && bot->HasSpell(16979)
                && TryCastCombatSpell(bot, chargeTarget, 16979))
            {
                std::string raw = BuildRawJson(bot, chargeTarget);
                std::string semantic = BuildSemanticJson(
                    bot, chargeTarget, "validation_route_mechanic", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup", chargeTarget,
                    "feral_charge_safe_hazard_swarm_pickup", raw.c_str(), semantic.c_str(),
                    float(engagedCount), Cohort().Config.ValidationRouteTargetEntry, 16979);
                state.FeralChargePickupTargetGuid = chargeTarget->GetGUID();
                state.FeralChargePickupUntilMs = NowMs() + 2500;
                state.TargetGuid = chargeTarget->GetGUID();
                state.WasInCombat = true;
                situation = "validation_route_mechanic";
                action = "feral_charge_safe_hazard_swarm_pickup";
                return true;
            }

            // A ready Charge is the fastest safe-side pickup, but its native
            // cooldown must not pin Feral outside the hazard for the entire
            // acquisition window. Reuse the unchanged radial safety margin
            // against every point in the strict mmap path before allowing
            // ordinary ground movement toward the selected hostile cluster.
            // Unsafe or incomplete paths still fall through to the bounded
            // safe-side hold.
            if (allowMovement
                && hazardProfile.SpecTag == "feral_druid_tank"
                && areaTarget
                && bot->GetExactDist2d(areaTarget) > 10.0f
                && radialGroundPathSafe(areaTarget))
            {
                bool moved = MoveBotToProfileRange(
                    state, bot, areaTarget);
                if (moved)
                {
                    // Rerun98's only generation-13 dwell failure spent four
                    // one-second decisions on this already-accepted safe path
                    // before native Roar became legal (4032 ms total). Rerun133
                    // then missed the strict ceiling by 31 ms after a legal
                    // hazard Roar. Keep hazard movement authoritative, but
                    // observe this active healer-owned pickup at 250 ms cadence.
                    if (areaPriority == 3)
                        state.DecisionTimer = std::min<uint32>(
                            state.DecisionTimer, 250);
                    std::string raw = BuildRawJson(bot, areaTarget);
                    std::string semantic = BuildSemanticJson(
                        bot, areaTarget, "validation_route_mechanic",
                        &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_threat_pickup",
                        areaTarget, "feral_move_safe_side_hazard_swarm_pickup",
                        raw.c_str(), semantic.c_str(),
                        bot->GetExactDist2d(areaTarget),
                        Cohort().Config.ValidationRouteTargetEntry);
                    state.TargetGuid = areaTarget->GetGUID();
                    situation = "validation_route_mechanic";
                    action = "feral_move_safe_side_hazard_swarm_pickup";
                    return true;
                }
            }

            ResolvedCombatAction areaThreat = ResolveProfileCombatAction(
                bot, areaTarget, engagedCount, true, 0, true);
            if (!areaThreat.Valid)
                return tryFeralHazardSwipeMargin();
            if (areaThreat.TargetGuid == bot->GetGUID())
            {
                uint32 nearbyEngagedCount = 0;
                for (Creature* creature : engagedHostiles)
                    if (creature && bot->GetExactDist2d(creature) <= 10.0f)
                        ++nearbyEngagedCount;
                if (nearbyEngagedCount < 2)
                    return tryFeralHazardSwipeMargin();
            }
            BotActionResult areaResult = ExecuteProfileCombatAction(
                &state, bot, areaTarget, &areaThreat, engagedCount, true, 0, true);
            if (areaResult != BotActionResult::Ok)
                return tryFeralHazardSwipeMargin();

            std::string raw = BuildRawJson(bot, areaTarget);
            std::string semantic = BuildSemanticJson(
                bot, areaTarget, "validation_route_mechanic", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup", areaTarget,
                "tank_hazard_hold_aoe_threat", raw.c_str(), semantic.c_str(),
                float(engagedCount), Cohort().Config.ValidationRouteTargetEntry, areaThreat.SpellId);
            state.TargetGuid = areaTarget->GetGUID();
            state.WasInCombat = true;
            situation = "validation_route_mechanic";
            action = "tank_hazard_hold_aoe_threat";
            return true;
        };

        // Refresh immediately before the state guard so a newly spawned or
        // overlapping Laser Strike cannot be missed between two AI ticks.
        refreshActiveHazards();
        if (!state.ValidationRouteDodgeCasterGuid.IsEmpty()
            && state.ValidationRouteDodgeSpellId)
        {
            Unit* previousHazard = ObjectAccessor::GetUnit(*bot, state.ValidationRouteDodgeCasterGuid);
            HazardDefinition const* previousDefinition = previousHazard
                ? hazardDefinitionFor(previousHazard->GetEntry(), state.ValidationRouteDodgeSpellId) : nullptr;
            if (previousDefinition)
            {
                float safeRadius = std::max(1.0f, previousDefinition->RadiusYards + previousDefinition->SafetyMarginYards);
                bool outsideHazard = bot->GetExactDist2d(previousHazard) > safeRadius;
                if (previousDefinition->Shape == "frontal_cone" && !previousHazard->HasInArc(float(M_PI), bot))
                    outsideHazard = true;
                // The previous single-caster guard is retained for telemetry,
                // but an exit is complete only when the bot is outside every
                // currently active source.  This matters when two Golem
                // Sentries place overlapping Laser Strike creatures.
                for (ActiveHazard const& activeHazard : activeHazards)
                {
                    if (!activeHazard.Source || !activeHazard.HazardDefinition)
                        continue;
                    bool insideActiveHazard = bot->GetExactDist2d(activeHazard.Source)
                        <= activeHazard.SafeRadius;
                    if (activeHazard.HazardDefinition->Shape == "frontal_cone")
                        insideActiveHazard = insideActiveHazard
                            && activeHazard.Source->HasInArc(float(M_PI), bot);
                    bool outsideActiveHazard = !insideActiveHazard;
                    outsideHazard = outsideHazard && outsideActiveHazard;
                }
                // Persistent ground objects and native timed markers share the
                // same activity predicate used by the fresh-hazard scan.
                bool hazardActive = hazardIsActive(
                    previousHazard->ToCreature(), previousDefinition);
                if (outsideHazard && hazardActive && state.ValidationRouteDodgeUntilMs > nowMs)
                {
                    if (previousDefinition->Shape == "radial"
                        && state.FeralChargePickupUntilMs > nowMs
                        && !state.FeralChargePickupTargetGuid.IsEmpty())
                    {
                        Unit* chargeTarget = ObjectAccessor::GetUnit(
                            *bot, state.FeralChargePickupTargetGuid);
                        if (chargeTarget && chargeTarget->IsAlive()
                            && bot->IsValidAttackTarget(chargeTarget)
                            && bot->GetExactDist2d(chargeTarget) > 10.0f)
                        {
                            std::string raw = BuildRawJson(bot, chargeTarget);
                            std::string semantic = BuildSemanticJson(
                                bot, chargeTarget, "validation_route_mechanic",
                                &power, stage, activity);
                            RecordEvent(state, bot, "validation_route_threat_pickup",
                                chargeTarget,
                                "feral_charge_safe_hazard_swarm_pickup_in_flight",
                                raw.c_str(), semantic.c_str(),
                                bot->GetExactDist2d(chargeTarget),
                                Cohort().Config.ValidationRouteTargetEntry, 16979);
                            state.TargetGuid = chargeTarget->GetGUID();
                            situation = "validation_route_mechanic";
                            action = "feral_charge_safe_hazard_swarm_pickup_in_flight";
                            return true;
                        }
                        state.FeralChargePickupTargetGuid.Clear();
                        state.FeralChargePickupUntilMs = 0;
                    }
                    else if (state.FeralChargePickupUntilMs
                        && state.FeralChargePickupUntilMs <= nowMs)
                    {
                        state.FeralChargePickupTargetGuid.Clear();
                        state.FeralChargePickupUntilMs = 0;
                    }

                    // Crossing the radius is not enough: ordinary melee/range
                    // movement immediately walked bots back into live fissures
                    // and rotating Flay cones. Hold the safe side briefly while
                    // the exact hazard remains active. A bounded safe Charge keeps
                    // its motion until arrival before this hold clears the slot.
                    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                    state.ActivePathValid = false;
                    state.IsMoving = false;
                    // Once safely outside, a healer may use the native trained
                    // healing profile from this exact position. Movement-owned
                    // healer convergence remains disabled, but cast-time heals
                    // are safe because the accepted hazard exit is complete.
                    if (tryRouteGroupHeal(bot, preferredTarget, false, true))
                        return true;
                    if (tryHealerInFlightHazardFade())
                        return true;
                    if (tryTankHazardHoldAreaThreat(previousHazard, safeRadius,
                            previousDefinition->Shape == "radial"))
                        return true;
                    situation = "validation_route_mechanic";
                    action = "hold_outside_hazard";
                    return true;
                }
                if (!previousHazard->IsAlive() || outsideHazard || !hazardActive)
                {
                    std::string raw = BuildRawJson(bot, previousHazard);
                    std::string semantic = BuildSemanticJson(bot, previousHazard, "validation_route_mechanic", &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_mechanic", previousHazard, "hazard_exit_completed",
                        raw.c_str(), semantic.c_str(), bot->GetExactDist(previousHazard),
                        previousDefinition->SourceEntry, state.ValidationRouteDodgeSpellId);
                    state.ValidationRouteDodgeCasterGuid.Clear();
                    state.ValidationRouteDodgeSpellId = 0;
                    state.ValidationRouteDodgeUntilMs = 0;
                    state.ValidationRouteDodgeBearingAttempt = 0;
                }
                else if (state.ActivePathValid && state.IsMoving)
                {
                    // Keep the accepted exit path authoritative until the bot
                    // is outside the hazard. A normal combat/range decision on
                    // the next tick must not replace the dodge mid-stride.
                    // Rerun73 isolated one healer-owned hostile for 15 seconds
                    // while every Feral decision returned here. Growl is an
                    // instant single-target pickup and does not replace or
                    // clear the already accepted hazard-exit motion.
                    if (tryHealerInFlightHazardFade())
                        return true;
                    // Preserve the accepted strict hazard-exit path while still
                    // allowing native instant self-centered threat. Rerun83
                    // showed Flayer and Azil waves targeting the healer for
                    // 6-10 seconds because every Feral tick returned here
                    // before the declared add handler could submit Roar,
                    // Swipe, or Thrash. This in-flight mode cannot Charge or
                    // issue ground movement, so hazard geometry remains the
                    // sole movement authority.
                    if (previousDefinition->Shape == "radial"
                        && tryTankHazardHoldAreaThreat(
                            previousHazard, safeRadius, true, false))
                        return true;
                    if (previousDefinition->Shape == "radial"
                        && tryFeralInFlightHazardLooseTaunt())
                        return true;
                    situation = "validation_route_mechanic";
                    action = "move_out_of_hazard";
                    return true;
                }
            }
        }

        Unit* caster = nullptr;
        WorldObject const* movementOrigin = nullptr;
        SpellInfo const* castSpell = nullptr;
        bool configuredHazard = false;
        float configuredSafeRadius = 0.0f;
        std::string configuredHazardShape;
        auto inspectCaster = [&](Unit* candidate) -> bool
        {
            if (!candidate || !candidate->IsAlive() || !bot->IsValidAttackTarget(candidate) || !bot->IsWithinDistInMap(candidate, 35.0f))
                return false;

            if (Spell* spell = candidate->GetCurrentSpell(CURRENT_GENERIC_SPELL))
                castSpell = spell->GetSpellInfo();
            if (!castSpell)
                if (Spell* spell = candidate->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
                    castSpell = spell->GetSpellInfo();
            if (!castSpell || !castSpell->CalcCastTime(candidate->getLevel()))
            {
                castSpell = nullptr;
                return false;
            }
            if (!SpellLooksLikeGroundDanger(castSpell))
            {
                castSpell = nullptr;
                return false;
            }

            caster = candidate;
            movementOrigin = candidate;
            return true;
        };

        if (mechanicProfileRequiresMovement && !hazardDefinitions.empty())
        {
            float bestHazardDistance = std::numeric_limits<float>::max();
            for (ActiveHazard const& activeHazard : activeHazards)
            {
                Creature* hazard = activeHazard.Source;
                HazardDefinition const* definition = activeHazard.HazardDefinition;
                if (!hazard || !definition)
                    continue;

                float safeRadius = activeHazard.SafeRadius;
                float distance = bot->GetExactDist2d(hazard);
                if (distance > safeRadius)
                    continue;
                if (definition->Shape == "frontal_cone" && !hazard->HasInArc(float(M_PI), bot))
                    continue;
                if (distance >= bestHazardDistance)
                    continue;

                bestHazardDistance = distance;
                caster = hazard;
                movementOrigin = hazard;
                castSpell = sSpellMgr->GetSpellInfo(definition->DamageSpellId
                    ? definition->DamageSpellId : definition->DetectionSpellId);
                configuredHazard = castSpell != nullptr;
                configuredSafeRadius = safeRadius;
                configuredHazardShape = definition->Shape;
            }
        }

        // Exact route geometry takes precedence over spell-shape guessing.
        // When that configured source is inactive, a different enrolled and
        // cohort-combat-linked member of the current trash pack can still cast
        // a second ground danger (rerun208: Crystalspawn Giant Quake alongside
        // configured Flayer Flay). Keep boss phases, future packs, and unrelated
        // nearby casters outside this fallback.
        if (!caster && profileAllowsGenericCastMovement
            && isScopedGenericCastCandidate(preferredTarget))
            inspectCaster(preferredTarget);
        if (!caster && mechanicProfileRequiresMovement)
        {
            for (auto const& [_, application] : bot->GetAppliedAuras())
            {
                if (!application || application->IsPositive())
                    continue;

                Aura const* aura = application->GetBase();
                SpellInfo const* auraSpell = aura ? aura->GetSpellInfo() : nullptr;
                if (!auraSpell)
                    continue;

                bool persistentPeriodicDamage = false;
                for (SpellEffectInfo const& effect : auraSpell->Effects)
                {
                    if (effect.Effect == SPELL_EFFECT_PERSISTENT_AREA_AURA
                        && (effect.ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE
                            || effect.ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE_PERCENT))
                    {
                        persistentPeriodicDamage = true;
                        break;
                    }
                }
                if (!persistentPeriodicDamage)
                    continue;

                movementOrigin = aura->GetOwner();
                caster = ObjectAccessor::GetUnit(*bot, aura->GetCasterGUID());
                if (!caster)
                    caster = preferredTarget;
                if (!caster)
                    continue;

                castSpell = auraSpell;
                break;
            }
        }
        if (!caster && profileAllowsGenericCastMovement)
        {
            std::vector<WorldObject*> objects;
            Trinity::AllWorldObjectsInRange check(bot, 35.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
            Cell::VisitAllObjects(bot, searcher, 35.0f);
            for (WorldObject* object : objects)
            {
                Unit* candidate = object ? object->ToUnit() : nullptr;
                if (isScopedGenericCastCandidate(candidate) && inspectCaster(candidate))
                    break;
            }
        }

        if (!caster || !castSpell)
            return false;

        // A generic cast is one dodge window, not a movement command on every
        // AI tick. Exact configured hazards use the active exit/hold logic
        // above because they may remain dangerous after the cast completes.
        if (!configuredHazard
            && state.ValidationRouteDodgeCasterGuid == caster->GetGUID()
            && state.ValidationRouteDodgeSpellId == castSpell->Id
            && state.ValidationRouteDodgeUntilMs > nowMs)
            return false;

        WorldObject const* dodgeOrigin = movementOrigin && movementOrigin != bot ? movementOrigin : caster;
        float distanceFromOrigin = bot->GetExactDist2d(dodgeOrigin);
        float dodgeDistance = configuredHazard
            ? std::max(3.0f, configuredSafeRadius - distanceFromOrigin + 2.0f) : 8.0f;
        float angle = bot->GetRelativeAngle(dodgeOrigin) + float(M_PI);
        if (configuredHazard)
        {
            float absoluteAwayAngle = dodgeOrigin->GetAngle(bot);
            if (configuredHazardShape == "frontal_cone")
            {
                float side = bot->GetGUID().GetCounter() % 2 ? 1.0f : -1.0f;
                absoluteAwayAngle = dodgeOrigin->GetOrientation() + side * float(M_PI_2);
                dodgeDistance = std::max(4.0f, configuredSafeRadius);
            }
            else
            {
                uint8 bearingBucket = BotRaidHazard::RotatedBearingBucket(
                    bot->GetGUID().GetCounter(),
                    state.ValidationRouteDodgeBearingAttempt);
                float spreadOffset = (int32(bearingBucket) - 2) * 0.16f;
                absoluteAwayAngle += spreadOffset;
            }
            angle = absoluteAwayAngle - bot->GetOrientation();
        }
        // Rerun84 showed the new strict radial path was accepted before the
        // instant healer threat-drop and Feral loose-healer taunt were
        // submitted. Once movement owned the decision, the last loose hostile
        // persisted for 4017 ms even though the subsequent safe-side area
        // resolver succeeded. Submit only these existing instant native rules
        // before path ownership; the strict hazard destination below remains
        // unchanged and is still issued in this decision.
        if (configuredHazard && configuredHazardShape == "radial")
        {
            tryHealerInFlightHazardFade();
            if (!tryFeralInFlightHazardHealerRoar())
                tryFeralInFlightHazardLooseTaunt();
        }

        bot->InterruptNonMeleeSpells(false);
        bool moved = false;
        bool feralHazardHandoffBiased = false;
        bool feralHazardCurrentClusterBiased = false;
        std::vector<Position> dodgeCandidates;
        // A direct radial exit can land outside the local navmesh beside lava
        // cracks, walls, or shelf edges.  Try a small deterministic fan of
        // equally safe bearings before reporting a failed hazard exit.
        for (float angleOffset : { 0.0f, float(M_PI_4), -float(M_PI_4), float(M_PI_2), -float(M_PI_2) })
            dodgeCandidates.push_back(
                bot->GetFirstCollisionPosition(dodgeDistance, angle + angleOffset));

        // MoveBotToPoint validates navmesh reachability, while this geometry
        // gate validates the complete active-hazard set.  Do not submit a
        // candidate that exits one Laser Strike only to enter another
        // overlapping strike on the same path endpoint.
        dodgeCandidates.erase(
            std::remove_if(dodgeCandidates.begin(), dodgeCandidates.end(),
                [&](Position const& candidate)
                {
                    return !positionOutsideActiveHazards(candidate);
                }),
            dodgeCandidates.end());
        dodgeCandidates.erase(
            std::remove_if(dodgeCandidates.begin(), dodgeCandidates.end(),
                [&](Position const& candidate)
                {
                    return !pathOutsideActiveHazards(
                        candidate.GetPositionX(), candidate.GetPositionY(), candidate.GetPositionZ());
                }),
            dodgeCandidates.end());

        // Rerun106's longest healer dwell began while ordinary-trash recovery
        // already owned a validated remote hostile anchor. A new strict radial
        // hazard correctly replaced that movement, but the geometry-only fan
        // chose the opposite safe side and local Swipe could not reach the
        // remote cluster for 6.56 seconds. Preserve the same five collision-safe
        // candidates and unchanged hazard radius, but rank their endpoints
        // toward the still-valid identity-bound handoff anchor. Hazard movement
        // remains authoritative and every candidate still passes MoveBotToPoint.
        Unit* feralHazardHandoffAnchor = nullptr;
        if (configuredHazard && configuredHazardShape == "radial"
            && state.FeralHealerThreatHandoffUntilMs > nowMs
            && !state.FeralHealerThreatHandoffAnchorGuid.IsEmpty())
        {
            BotClassSpecActionProfile hazardProfile =
                BotClassSpecActionProfileStore::Build(bot, GetDungeonRole(bot));
            Unit* candidate = ObjectAccessor::GetUnit(
                *bot, state.FeralHealerThreatHandoffAnchorGuid);
            Player* victim = candidate && candidate->GetVictim()
                ? candidate->GetVictim()->ToPlayer() : nullptr;
            if (hazardProfile.SpecTag == "feral_druid_tank"
                && candidate && candidate->IsAlive()
                && candidate->GetMap() == bot->GetMap()
                && bot->IsValidAttackTarget(candidate)
                && victim && GetDungeonRole(victim) == "healer"
                && bot->GetGroup()
                && victim->GetGroup() == bot->GetGroup())
                feralHazardHandoffAnchor = candidate;
        }
        // Rerun109's largest loss began when a fresh Flayer wave flipped to
        // the healer after hazard movement became authoritative but before an
        // ordinary handoff existed.  In that state the rerun106 rule had no
        // anchor and retained the geometry-only bearing for 5.6 seconds.  Use
        // the same deterministic densest healer-owned cluster as a bearing
        // hint for the unchanged five safe candidates.  This neither creates
        // a handoff nor changes the hazard radius/path acceptance contract.
        if (!feralHazardHandoffAnchor
            && configuredHazard && configuredHazardShape == "radial")
        {
            BotClassSpecActionProfile hazardProfile =
                BotClassSpecActionProfileStore::Build(
                    bot, GetDungeonRole(bot));
            if (hazardProfile.SpecTag == "feral_druid_tank")
            {
                std::vector<WorldObject*> objects;
                Trinity::AllWorldObjectsInRange check(bot, 45.0f);
                Trinity::WorldObjectListSearcher<
                    Trinity::AllWorldObjectsInRange> searcher(
                        bot, objects, check);
                Cell::VisitAllObjects(bot, searcher, 45.0f);
                std::vector<Creature*> healerAttackers;
                for (WorldObject* object : objects)
                {
                    Creature* creature = object ? object->ToCreature() : nullptr;
                    Player* victim = creature && creature->GetVictim()
                        ? creature->GetVictim()->ToPlayer() : nullptr;
                    if (creature && creature->IsAlive()
                        && creature->GetMap() == bot->GetMap()
                        && bot->IsValidAttackTarget(creature)
                        && victim && GetDungeonRole(victim) == "healer"
                        && bot->GetGroup()
                        && victim->GetGroup() == bot->GetGroup())
                        healerAttackers.push_back(creature);
                }
                uint32 bestClusterCount = 0;
                float bestDistance = std::numeric_limits<float>::max();
                uint32 bestGuid = std::numeric_limits<uint32>::max();
                for (Creature* candidate : healerAttackers)
                {
                    uint32 clusterCount = 0;
                    for (Creature* neighbor : healerAttackers)
                        if (candidate->GetExactDist2d(neighbor) <= 10.0f)
                            ++clusterCount;
                    float distance = bot->GetExactDist(candidate);
                    uint32 guid = candidate->GetGUID().GetCounter();
                    if (!feralHazardHandoffAnchor
                        || clusterCount > bestClusterCount
                        || (clusterCount == bestClusterCount
                            && (distance < bestDistance
                                || (distance == bestDistance
                                    && guid < bestGuid))))
                    {
                        feralHazardHandoffAnchor = candidate;
                        bestClusterCount = clusterCount;
                        bestDistance = distance;
                        bestGuid = guid;
                    }
                }
                feralHazardCurrentClusterBiased =
                    feralHazardHandoffAnchor != nullptr;
            }
        }
        if (feralHazardHandoffAnchor)
        {
            std::stable_sort(dodgeCandidates.begin(), dodgeCandidates.end(),
                [&](Position const& left, Position const& right)
                {
                    bool leftOutside = Distance2d(
                        left.GetPositionX(), left.GetPositionY(),
                        dodgeOrigin->GetPositionX(), dodgeOrigin->GetPositionY())
                        > configuredSafeRadius + 0.5f;
                    bool rightOutside = Distance2d(
                        right.GetPositionX(), right.GetPositionY(),
                        dodgeOrigin->GetPositionX(), dodgeOrigin->GetPositionY())
                        > configuredSafeRadius + 0.5f;
                    if (leftOutside != rightOutside)
                        return leftOutside;
                    return Distance2d(
                        left.GetPositionX(), left.GetPositionY(),
                        feralHazardHandoffAnchor->GetPositionX(),
                        feralHazardHandoffAnchor->GetPositionY())
                        < Distance2d(
                            right.GetPositionX(), right.GetPositionY(),
                            feralHazardHandoffAnchor->GetPositionX(),
                            feralHazardHandoffAnchor->GetPositionY());
                });
            feralHazardHandoffBiased = true;
        }
        for (Position const& dodge : dodgeCandidates)
        {
            if (MoveBotToPoint(state, bot, dodge.GetPositionX(), dodge.GetPositionY(), dodge.GetPositionZ()))
            {
                moved = true;
                break;
            }
        }
        bool const newDodgeSource = state.ValidationRouteDodgeCasterGuid
            != caster->GetGUID();
        if (newDodgeSource)
            state.ValidationRouteDodgeBearingAttempt = 0;
        state.ValidationRouteDodgeCasterGuid = caster->GetGUID();
        state.ValidationRouteDodgeSpellId = castSpell->Id;
        state.ValidationRouteDodgeUntilMs = nowMs + (moved ? 3000 : 500);
        if (configuredHazard && moved)
            state.ValidationRouteDodgeUntilMs = nowMs + (configuredHazardShape == "radial" ? 6000 : 3000);
        if (configuredHazard && !moved)
        {
            state.ValidationRouteDodgeBearingAttempt = uint8(
                (state.ValidationRouteDodgeBearingAttempt + 1) % 5);
            state.LastPathRejectReason = "hazard_exit_no_union_safe_native_path";
            state.LastRecoveryResult = state.LastPathRejectReason;
        }

        std::string raw = BuildRawJson(bot, caster);
        std::string semantic = BuildSemanticJson(bot, caster, "validation_route_mechanic", &power, stage, activity);
        char const* movementReason = moved
            ? (configuredHazard
                ? (feralHazardHandoffBiased
                    ? (feralHazardCurrentClusterBiased
                        ? "hazard_exit_started_toward_feral_healer_cluster"
                        : "hazard_exit_started_toward_feral_healer_handoff")
                    : "hazard_exit_started")
                : "movement_check_jump")
            : (configuredHazard ? "hazard_exit_failed" : "tactical_path_rejected");
        RecordEvent(state, bot, "validation_route_mechanic", caster, movementReason, raw.c_str(), semantic.c_str(), bot->GetExactDist(caster), Cohort().Config.ValidationRouteTargetEntry, castSpell->Id);
        if (moved && configuredHazard && configuredHazardShape == "radial"
            && tryTankHazardHoldAreaThreat(
                caster, configuredSafeRadius, true, false))
            return true;
        situation = "validation_route_mechanic";
        action = moved ? (configuredHazard ? "move_out_of_hazard" : "movement_check_jump")
            : (configuredHazard ? "hold_hazard_exit_failed" : "hold_tactical_path_rejected");
        return true;
    };
    auto drudgeLandedRushPending = [this]() -> bool
    {
        if (Cohort().Config.ValidationRouteMechanicProfile
            != "trash_two_tank_charge_lanes")
            return false;
        auto observation = std::find_if(
            Party().ValidationRouteDrudgeChargeObservations.begin(),
            Party().ValidationRouteDrudgeChargeObservations.end(),
            [this](ValidationRouteDrudgeChargeObservation const& observation)
            {
                return !observation.ReseparationRecorded
                    && observation.AttemptId == Cohort().AttemptId
                    && observation.WipeGeneration == Cohort().Raid.WipeGeneration
                    && observation.RouteGeneration == Party().ValidationRouteGeneration;
            });
        return observation != Party().ValidationRouteDrudgeChargeObservations.end()
            && observation->Landed;
    };
    auto tryValidationRouteMinimumDistance = [this, &state, bot, &power, stage, activity,
        &situation, &action, &target, &isValidationCohortCombatLinked,
        &drudgeLandedRushPending](bool specializedDrudgeRecovery = false) -> bool
    {
        bool const drudgeProfile = Cohort().Config.ValidationRouteMechanicProfile
            == "trash_two_tank_charge_lanes";
        BotRaidDrudgeGeometry::MinimumDistanceOwner const minimumDistanceOwner =
            BotRaidDrudgeGeometry::SelectMinimumDistanceOwner(
                drudgeProfile, drudgeLandedRushPending());
        if (specializedDrudgeRecovery
            != (minimumDistanceOwner
                == BotRaidDrudgeGeometry::MinimumDistanceOwner::LandedRushRecovery))
            return false;

        uint32 sourceEntry = Cohort().Config.ValidationRouteMinimumDistanceSourceEntry;
        float minimumDistance = Cohort().Config.ValidationRouteMinimumDistanceYards;
        if (!sourceEntry || minimumDistance <= 0.0f
            || std::string(GetDungeonRole(bot)) == "tank")
            return false;

        BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(
            bot, GetDungeonRole(bot));
        bool rangeAssigned = std::string(GetDungeonRole(bot)) == "healer"
            || profile.MovementDirective == "ranged"
            || profile.MovementDirective == "healer_support";
        if (!rangeAssigned)
            return false;

        Creature* source = nullptr;
        float sourceDistance = std::numeric_limits<float>::max();
        std::vector<Creature*> sources;
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, 60.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(
            bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, 60.0f);
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!creature || creature->GetEntry() != sourceEntry
                || !creature->IsAlive() || !creature->GetHealth()
                || creature->GetMap() != bot->GetMap()
                || !bot->IsValidAttackTarget(creature)
                || !isValidationCohortCombatLinked(creature))
                continue;
            sources.push_back(creature);
            float distance = bot->GetExactDist2d(creature);
            if (!source || distance < sourceDistance)
            {
                source = creature;
                sourceDistance = distance;
            }
        }
        if (!source || sourceDistance >= minimumDistance)
            return false;

        // The contract distance is the exact native damaging radius.  Search
        // for a two-yard exterior point against the union of every exact,
        // combat-linked source.  A nearest-source ray is insufficient when two
        // overlapping Drudges bracket a player: that ray can cross the second
        // source and finish inside its native damage radius.
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
                bot->GetPositionX() - candidateSource->GetPositionX(),
                bot->GetPositionY() - candidateSource->GetPositionY());
        }
        centroidX /= float(sources.size());
        centroidY /= float(sources.size());
        addDirection(bot->GetPositionX() - centroidX, bot->GetPositionY() - centroidY);
        for (size_t left = 0; left < sources.size(); ++left)
            for (size_t right = left + 1; right < sources.size(); ++right)
            {
                float pairX = sources[right]->GetPositionX() - sources[left]->GetPositionX();
                float pairY = sources[right]->GetPositionY() - sources[left]->GetPositionY();
                addDirection(-pairY, pairX);
                addDirection(pairY, -pairX);
            }

        bool moved = false;
        float safeX = bot->GetPositionX();
        float safeY = bot->GetPositionY();
        float safeZ = bot->GetPositionZ();
        for (auto const& direction : directions)
        {
            float requiredTravel = 0.0f;
            for (Creature const* candidateSource : sources)
            {
                float offsetX = bot->GetPositionX() - candidateSource->GetPositionX();
                float offsetY = bot->GetPositionY() - candidateSource->GetPositionY();
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
            float candidateX = bot->GetPositionX() + direction.first * requiredTravel;
            float candidateY = bot->GetPositionY() + direction.second * requiredTravel;
            float candidateZ = bot->GetPositionZ();
            if (Map* map = bot->GetMap())
            {
                float floorZ = map->GetHeight(bot->GetPhaseShift(), candidateX,
                    candidateY, candidateZ + 4.0f, true, 10.0f);
                if (floorZ > INVALID_HEIGHT && std::fabs(floorZ - candidateZ) <= 10.0f)
                    candidateZ = floorZ;
            }

            PathGenerator path(bot);
            bool pathOk = path.CalculatePath(candidateX, candidateY, candidateZ, false);
            PathType pathType = path.GetPathType();
            if (!pathOk || (pathType & PATHFIND_NOPATH)
                || (pathType & PATHFIND_NOT_USING_PATH)
                || (pathType & PATHFIND_INCOMPLETE)
                || (pathType & PATHFIND_SHORTCUT)
                || (pathType & PATHFIND_FARFROMPOLY))
                continue;

            bool unionSafe = true;
            for (Creature const* candidateSource : sources)
            {
                float startDistance = bot->GetExactDist2d(candidateSource);
                float pathFloor = std::max(0.0f,
                    std::min(startDistance, minimumDistance) - 0.25f);
                if (Distance2d(candidateX, candidateY,
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
            moved = MoveBotToPoint(state, bot, safeX, safeY, safeZ);
            if (moved)
                break;
        }
        std::string raw = BuildRawJson(bot, source);
        std::string semantic = BuildSemanticJson(
            bot, source, "validation_route_mechanic", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_mechanic", source,
            moved ? "minimum_distance_exit_started" : "minimum_distance_exit_failed",
            raw.c_str(), semantic.c_str(), sourceDistance, sourceEntry);
        target = source;
        state.TargetGuid = source->GetGUID();
        situation = "validation_route_mechanic";
        action = moved ? "move_to_minimum_distance" : "hold_minimum_distance_exit_failed";
        return true;
    };
    auto drudgeRecoveryFormationActive = [this]() -> bool
    {
        if (Cohort().Config.ValidationRouteMechanicProfile
            != "trash_two_tank_charge_lanes")
            return false;
        for (ValidationRouteDrudgeChargeObservation const& observation :
            Party().ValidationRouteDrudgeChargeObservations)
            if (observation.Landed
                && observation.AttemptId == Cohort().AttemptId
                && observation.WipeGeneration == Cohort().Raid.WipeGeneration
                && observation.RouteGeneration == Party().ValidationRouteGeneration)
                return true;
        return false;
    };
    auto tryValidationRouteDrudgeChargeLanes = [this, &state, bot, &power, stage,
        activity, &situation, &action, &target, &tryRouteGroupHeal,
        &tryValidationRouteMinimumDistance, &drudgeLandedRushPending,
        &drudgeRecoveryFormationActive,
        &canonicalRouteDistance,
        &routeArrivalRadius]() -> bool
    {
        if (Cohort().Config.ValidationRouteMechanicProfile != "trash_two_tank_charge_lanes")
            return false;

        std::vector<uint32> laneSlots = Cohort().Config.ValidationRouteSplitLaneARosterSlots;
        laneSlots.insert(laneSlots.end(), Cohort().Config.ValidationRouteSplitLaneBRosterSlots.begin(),
            Cohort().Config.ValidationRouteSplitLaneBRosterSlots.end());
        std::sort(laneSlots.begin(), laneSlots.end());
        std::vector<uint32> const exactRosterSlots = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 };
        std::vector<uint32> anchorSlots;
        for (ValidationRouteMemberAnchor const& anchor :
            Cohort().Config.ValidationRouteSplitMemberAnchors)
            anchorSlots.push_back(anchor.RosterSlot);
        std::sort(anchorSlots.begin(), anchorSlots.end());
        std::vector<uint32> combatTankAnchorSlots;
        for (ValidationRouteMemberAnchor const& anchor :
            Cohort().Config.ValidationRouteSplitTankCombatAnchors)
            combatTankAnchorSlots.push_back(anchor.RosterSlot);
        std::sort(combatTankAnchorSlots.begin(), combatTankAnchorSlots.end());
        std::vector<uint32> navigationTankAnchorSlots;
        for (ValidationRouteMemberAnchor const& anchor :
            Cohort().Config.ValidationRouteSplitTankNavigationAnchors)
            navigationTankAnchorSlots.push_back(anchor.RosterSlot);
        std::sort(navigationTankAnchorSlots.begin(), navigationTankAnchorSlots.end());
        std::vector<uint32> recoveryTankAnchorSlots;
        for (ValidationRouteMemberAnchor const& anchor :
            Cohort().Config.ValidationRouteSplitTankRecoveryAnchors)
            recoveryTankAnchorSlots.push_back(anchor.RosterSlot);
        std::sort(recoveryTankAnchorSlots.begin(), recoveryTankAnchorSlots.end());
        auto rosterSlotHasExactRole = [this](uint32 oneBasedSlot, char const* role) -> bool
        {
            for (auto const& [guid, roster] : Cohort().Raid.RosterByGuid)
            {
                (void)guid;
                if (roster.SlotIndex + 1 == oneBasedSlot)
                    return roster.Active && roster.LeaseOwned && roster.Role == role;
            }
            return false;
        };
        std::vector<uint32> healerSlots =
            Cohort().Config.ValidationRouteSplitHealerRosterSlots;
        std::sort(healerSlots.begin(), healerSlots.end());
        bool const healerSlotsResolved = healerSlots.size() == 3
            && std::adjacent_find(healerSlots.begin(), healerSlots.end()) == healerSlots.end()
            && std::all_of(healerSlots.begin(), healerSlots.end(),
                [&rosterSlotHasExactRole](uint32 oneBasedSlot)
                {
                    return rosterSlotHasExactRole(oneBasedSlot, "healer");
                });
        bool const seedSlotsResolved =
            Cohort().Config.ValidationRouteSplitSeedRosterSlots.size() == 2
            && Cohort().Config.ValidationRouteSplitSeedRosterSlots[0]
                != Cohort().Config.ValidationRouteSplitSeedRosterSlots[1]
            && std::find(Cohort().Config.ValidationRouteSplitLaneBRosterSlots.begin(),
                Cohort().Config.ValidationRouteSplitLaneBRosterSlots.end(),
                Cohort().Config.ValidationRouteSplitSeedRosterSlots[0])
                != Cohort().Config.ValidationRouteSplitLaneBRosterSlots.end()
            && std::find(Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(),
                Cohort().Config.ValidationRouteSplitSeedRosterSlots[1])
                != Cohort().Config.ValidationRouteSplitLaneARosterSlots.end()
            && std::find(Cohort().Config.ValidationRouteSplitLaneTankSlots.begin(),
                Cohort().Config.ValidationRouteSplitLaneTankSlots.end(),
                Cohort().Config.ValidationRouteSplitSeedRosterSlots[0])
                == Cohort().Config.ValidationRouteSplitLaneTankSlots.end()
            && std::find(Cohort().Config.ValidationRouteSplitLaneTankSlots.begin(),
                Cohort().Config.ValidationRouteSplitLaneTankSlots.end(),
                Cohort().Config.ValidationRouteSplitSeedRosterSlots[1])
                == Cohort().Config.ValidationRouteSplitLaneTankSlots.end()
            && rosterSlotHasExactRole(
                Cohort().Config.ValidationRouteSplitSeedRosterSlots[0], "dps")
            && rosterSlotHasExactRole(
                Cohort().Config.ValidationRouteSplitSeedRosterSlots[1], "dps");
        auto repeatedNativeFarthestGeometrySafe = [this, &healerSlots]() -> bool
        {
            if (Cohort().Config.ValidationRouteSplitSeedRosterSlots.size() != 2
                || Cohort().Config.ValidationRouteSplitLaneARosterSlots.size() != 5
                || Cohort().Config.ValidationRouteSplitLaneBRosterSlots.size() != 5
                || Cohort().Config.ValidationRouteSplitLaneTankSlots.size() != 2
                || Cohort().Config.ValidationRouteSplitTankRecoveryAnchors.size() != 2
                || Cohort().Config.ValidationRouteSplitNativeMeleeStopYards <= 0.0f
                || Cohort().Config.ValidationRouteSplitArrivalToleranceYards <= 0.0f)
                return false;
            auto findAnchor = [](std::vector<ValidationRouteMemberAnchor> const& anchors,
                                  uint32 rosterSlot) -> ValidationRouteMemberAnchor const*
            {
                auto const itr = std::find_if(anchors.begin(), anchors.end(),
                    [rosterSlot](ValidationRouteMemberAnchor const& anchor)
                    {
                        return anchor.RosterSlot == rosterSlot;
                    });
                return itr == anchors.end() ? nullptr : &*itr;
            };
            std::array<std::vector<uint32> const*, 2> const laneSets = {
                &Cohort().Config.ValidationRouteSplitLaneARosterSlots,
                &Cohort().Config.ValidationRouteSplitLaneBRosterSlots,
            };
            for (uint32 sourceIndex = 0; sourceIndex < 2; ++sourceIndex)
            {
                uint32 const seedSlot =
                    Cohort().Config.ValidationRouteSplitSeedRosterSlots[sourceIndex];
                ValidationRouteMemberAnchor const* seed = findAnchor(
                    Cohort().Config.ValidationRouteSplitMemberAnchors, seedSlot);
                ValidationRouteMemberAnchor const* recovery = findAnchor(
                    Cohort().Config.ValidationRouteSplitTankRecoveryAnchors,
                    Cohort().Config.ValidationRouteSplitLaneTankSlots[sourceIndex]);
                if (!seed || !recovery)
                    return false;
                float const toSeedX = seed->X - recovery->X;
                float const toSeedY = seed->Y - recovery->Y;
                float const toSeedDistance = std::hypot(toSeedX, toSeedY);
                float const meleeStop =
                    Cohort().Config.ValidationRouteSplitNativeMeleeStopYards;
                if (toSeedDistance <= meleeStop)
                    return false;
                float const sourceX = recovery->X + toSeedX * meleeStop / toSeedDistance;
                float const sourceY = recovery->Y + toSeedY * meleeStop / toSeedDistance;
                float const seedDistance = Distance2d(sourceX, sourceY, seed->X, seed->Y);
                std::vector<uint32> forbiddenSlots = *laneSets[sourceIndex];
                forbiddenSlots.insert(
                    forbiddenSlots.end(), healerSlots.begin(), healerSlots.end());
                std::sort(forbiddenSlots.begin(), forbiddenSlots.end());
                forbiddenSlots.erase(
                    std::unique(forbiddenSlots.begin(), forbiddenSlots.end()),
                    forbiddenSlots.end());
                for (uint32 forbiddenSlot : forbiddenSlots)
                {
                    if (forbiddenSlot == seedSlot)
                        continue;
                    ValidationRouteMemberAnchor const* forbidden = findAnchor(
                        Cohort().Config.ValidationRouteSplitMemberAnchors, forbiddenSlot);
                    if (!forbidden
                        || seedDistance + 0.0001f
                            < Distance2d(sourceX, sourceY, forbidden->X, forbidden->Y)
                                + 2.0f * Cohort().Config.ValidationRouteSplitArrivalToleranceYards)
                        return false;
                }
            }
            return true;
        };
        bool contractResolved = Cohort().Config.ValidationRouteSplitSourceGuids.size() == 2
            && Cohort().Config.ValidationRouteSplitLaneARosterSlots.size() == 5
            && Cohort().Config.ValidationRouteSplitLaneBRosterSlots.size() == 5
            && Cohort().Config.ValidationRouteSplitLaneTankSlots.size() == 2
            && laneSlots == exactRosterSlots
            && anchorSlots == exactRosterSlots
            && combatTankAnchorSlots == std::vector<uint32>({ 1, 2 })
            && navigationTankAnchorSlots == std::vector<uint32>({ 1, 2 })
            && recoveryTankAnchorSlots == std::vector<uint32>({ 1, 2 })
            && Cohort().Config.ValidationRouteBossRecovery
                == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly
            && Cohort().Config.ValidationRouteSplitLaneTankSlots[0]
                == Cohort().Config.ValidationRouteSplitLaneARosterSlots[0]
            && Cohort().Config.ValidationRouteSplitLaneTankSlots[1]
                == Cohort().Config.ValidationRouteSplitLaneBRosterSlots[0]
            && Cohort().Config.ValidationRouteSplitMinimumSeparationYards > 0.0f
            && Cohort().Config.ValidationRouteSplitNavigationMarginYards >= 0.0f
            && Cohort().Config.ValidationRouteSplitArrivalToleranceYards > 0.0f
            && Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards > 0.0f
            && Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards
                <= Cohort().Config.ValidationRouteSplitArrivalToleranceYards
            && Cohort().Config.ValidationRouteSplitNativeMeleeStopYards > 0.0f
            && healerSlotsResolved
            && seedSlotsResolved
            && repeatedNativeFarthestGeometrySafe()
            && Cohort().Config.ValidationRouteSplitSeedMaxRangeYards > 0.0f
            && Cohort().Config.ValidationRouteSplitTankThreatHeadroomMultiplier >= 1.3f
            && Cohort().Config.ValidationRouteMinimumDistanceYards > 0.0f
            && Cohort().Config.ValidationRouteThunderclapSpellId
            && Cohort().Config.ValidationRouteChargeSpellId
            && Cohort().Config.ValidationRouteChargeRangeYards > 0.0f
            && Cohort().Config.ValidationRouteChargeNativeIntervalMs
            && Cohort().Config.ValidationRouteVengefulRageSpellId;

        auto holdOffense = [this, &state, bot]()
        {
            uint64 const ownerGuid = bot->GetGUID().GetRawValue();
            BotRaidAreaAuthority::SetAllOffenseSuppressed(ownerGuid, true);
            BotRaidAreaAuthority::Set(ownerGuid, true);
            for (CurrentSpellTypes spellType : { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL })
                if (Spell* current = bot->GetCurrentSpell(spellType))
                    if (Unit* castTarget = current->m_targets.GetUnitTarget();
                        castTarget && bot->IsValidAttackTarget(castTarget))
                        bot->InterruptSpell(spellType, false);
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Safety,
                BotActionArbitration::Priority::Terminal,
                "mechanic_all_offense_suppressed");
            if (Pet* pet = bot->GetPet())
            {
                for (CurrentSpellTypes spellType : { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL })
                    if (Spell* current = pet->GetCurrentSpell(spellType))
                        if (Unit* castTarget = current->m_targets.GetUnitTarget();
                            castTarget && pet->IsValidAttackTarget(castTarget))
                            pet->InterruptSpell(spellType, false);
                pet->AttackStop();
            }
            for (Unit* controlled : bot->m_Controlled)
                if (controlled)
                {
                    for (CurrentSpellTypes spellType : { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL })
                        if (Spell* current = controlled->GetCurrentSpell(spellType))
                            if (Unit* castTarget = current->m_targets.GetUnitTarget();
                                castTarget && controlled->IsValidAttackTarget(castTarget))
                                controlled->InterruptSpell(spellType, false);
                    controlled->AttackStop();
                }
        };
        auto record = [&](Creature* source, char const* result, float value = 0.0f, uint32 value2 = 0)
        {
            std::string raw = BuildRawJson(bot, source);
            std::string semantic = BuildSemanticJson(bot, source,
                "validation_route_mechanic", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_drudge_lanes", source, result,
                raw.c_str(), semantic.c_str(), value, value2,
                Cohort().Config.ValidationRouteChargeSpellId);
            situation = "validation_route_mechanic";
            action = result;
        };

        // The earliest unresolved observation is the sole authority for both
        // generic radius escape and Drudge reseparation.  Run the safety exit
        // before contract/roster/source validation can return: an incomplete
        // later stage must never strand a member inside a landed Rush radius.
        // Once outside the radius, normal fail-closed validation below retains
        // the same observation as the durable return obligation.
        if (bot->GetMap() && drudgeLandedRushPending())
        {
            holdOffense();
            if (tryValidationRouteMinimumDistance(true))
                return true;
        }
        if (!contractResolved || !bot->GetMap() || !Cohort().Raid.RosterComplete
            || Cohort().Raid.RosterByGuid.size() != exactRosterSlots.size())
        {
            holdOffense();
            record(nullptr, "drudge_lane_contract_unresolved");
            target = nullptr;
            state.TargetGuid.Clear();
            return true;
        }

        auto roster = Cohort().Raid.RosterByGuid.find(bot->GetGUID().GetCounter());
        if (roster == Cohort().Raid.RosterByGuid.end() || !roster->second.Active
            || !roster->second.LeaseOwned || roster->second.SlotIndex >= exactRosterSlots.size())
        {
            holdOffense();
            record(nullptr, "drudge_lane_roster_identity_missing");
            target = nullptr;
            state.TargetGuid.Clear();
            return true;
        }
        uint32 const oneBasedSlot = roster->second.SlotIndex + 1;
        std::vector<std::string> const exactSlotIds = {
            "raid_tank_1", "raid_tank_2", "raid_healer_1", "raid_healer_2",
            "raid_healer_3", "raid_dps_1", "raid_dps_2", "raid_dps_3",
            "raid_dps_4", "raid_dps_5"
        };
        if (roster->second.RosterSlotId != exactSlotIds[roster->second.SlotIndex])
        {
            holdOffense();
            record(nullptr, "drudge_lane_roster_slot_identity_mismatch");
            target = nullptr;
            state.TargetGuid.Clear();
            return true;
        }
        bool const laneA = std::find(Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
            Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), oneBasedSlot)
            != Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
        bool const laneB = std::find(Cohort().Config.ValidationRouteSplitLaneBRosterSlots.begin(),
            Cohort().Config.ValidationRouteSplitLaneBRosterSlots.end(), oneBasedSlot)
            != Cohort().Config.ValidationRouteSplitLaneBRosterSlots.end();
        if (laneA == laneB)
        {
            holdOffense();
            record(nullptr, "drudge_lane_slot_not_exactly_once");
            target = nullptr;
            state.TargetGuid.Clear();
            return true;
        }
        uint32 const laneIndex = laneA ? 0 : 1;
        bool const assignedTank = oneBasedSlot
            == Cohort().Config.ValidationRouteSplitLaneTankSlots[laneIndex];
        if (assignedTank != (roster->second.Role == "tank"))
        {
            holdOffense();
            record(nullptr, "drudge_lane_tank_role_mismatch");
            target = nullptr;
            state.TargetGuid.Clear();
            return true;
        }
        auto declaredAnchorFor = [&](uint32 slot) -> ValidationRouteMemberAnchor const*
        {
            auto anchor = std::find_if(
                Cohort().Config.ValidationRouteSplitMemberAnchors.begin(),
                Cohort().Config.ValidationRouteSplitMemberAnchors.end(),
                [slot](ValidationRouteMemberAnchor const& candidate)
                {
                    return candidate.RosterSlot == slot;
                });
            return anchor == Cohort().Config.ValidationRouteSplitMemberAnchors.end()
                ? nullptr : &*anchor;
        };
        auto declaredNavigationTankAnchorFor = [&](uint32 slot) -> ValidationRouteMemberAnchor const*
        {
            auto anchor = std::find_if(
                Cohort().Config.ValidationRouteSplitTankNavigationAnchors.begin(),
                Cohort().Config.ValidationRouteSplitTankNavigationAnchors.end(),
                [slot](ValidationRouteMemberAnchor const& candidate)
                {
                    return candidate.RosterSlot == slot;
                });
            return anchor == Cohort().Config.ValidationRouteSplitTankNavigationAnchors.end()
                ? nullptr : &*anchor;
        };
        auto declaredRecoveryTankAnchorFor = [&](uint32 slot) -> ValidationRouteMemberAnchor const*
        {
            auto anchor = std::find_if(
                Cohort().Config.ValidationRouteSplitTankRecoveryAnchors.begin(),
                Cohort().Config.ValidationRouteSplitTankRecoveryAnchors.end(),
                [slot](ValidationRouteMemberAnchor const& candidate)
                {
                    return candidate.RosterSlot == slot;
                });
            return anchor == Cohort().Config.ValidationRouteSplitTankRecoveryAnchors.end()
                ? nullptr : &*anchor;
        };
        ValidationRouteMemberAnchor const* const prepullAnchor = declaredAnchorFor(oneBasedSlot);
        if (!prepullAnchor || (assignedTank
            && (!declaredNavigationTankAnchorFor(oneBasedSlot)
                || !declaredRecoveryTankAnchorFor(oneBasedSlot))))
        {
            holdOffense();
            record(nullptr, "drudge_lane_declared_anchor_missing");
            target = nullptr;
            state.TargetGuid.Clear();
            return true;
        }

        std::vector<Creature*> sources;
        for (uint32 spawnId : Cohort().Config.ValidationRouteSplitSourceGuids)
        {
            Creature* source = bot->GetMap()->GetCreatureBySpawnId(spawnId);
            if (!source || source->GetEntry() != Cohort().Config.ValidationRouteMinimumDistanceSourceEntry
                || source->GetMap() != bot->GetMap())
            {
                if (!Party().ValidationRoutePackObservedEngagement
                    && canonicalRouteDistance > routeArrivalRadius)
                    return false;
                holdOffense();
                record(source, "drudge_lane_exact_source_missing", 0.0f, spawnId);
                target = nullptr;
                state.TargetGuid.Clear();
                return true;
            }
            sources.push_back(source);
        }
        if (sources[0] == sources[1])
        {
            holdOffense();
            record(sources[0], "drudge_lane_duplicate_source");
            target = nullptr;
            state.TargetGuid.Clear();
            return true;
        }
        if (!sources[0]->IsAlive() && !sources[1]->IsAlive())
            return false;
        bool const sourceCombatStarted = sources[0]->IsInCombat()
            || sources[1]->IsInCombat() || sources[0]->GetVictim()
            || sources[1]->GetVictim();
        auto combatTankStagingActive = [&]()
        {
            return sourceCombatStarted
                || (Party().ValidationRouteDrudgePrepullStaged
                    && Party().ValidationRouteDrudgePrepullAttemptId == Cohort().AttemptId
                    && Party().ValidationRouteDrudgePrepullWipeGeneration
                        == Cohort().Raid.WipeGeneration
                    && Party().ValidationRouteDrudgePrepullRouteGeneration
                        == Party().ValidationRouteGeneration);
        };

        Position const& homeA = sources[0]->GetHomePosition();
        Position const& homeB = sources[1]->GetHomePosition();
        float axisX = homeB.GetPositionX() - homeA.GetPositionX();
        float axisY = homeB.GetPositionY() - homeA.GetPositionY();
        float axisLength = std::hypot(axisX, axisY);
        if (axisLength <= 0.001f)
        {
            holdOffense();
            record(nullptr, "drudge_lane_source_axis_unresolved");
            target = nullptr;
            state.TargetGuid.Clear();
            return true;
        }
        axisX /= axisLength;
        axisY /= axisLength;
        float const midpointX = (homeA.GetPositionX() + homeB.GetPositionX()) * 0.5f;
        float const midpointY = (homeA.GetPositionY() + homeB.GetPositionY()) * 0.5f;
        float const midpointZ = (homeA.GetPositionZ() + homeB.GetPositionZ()) * 0.5f;
        float const laneSeparation = Cohort().Config.ValidationRouteSplitMinimumSeparationYards
            + Cohort().Config.ValidationRouteSplitNavigationMarginYards;
        float const laneSign = laneIndex == 0 ? -1.0f : 1.0f;
        // The route manifest binds source index to lane.  Never infer this
        // from a moving creature position: a delivered Rush can move a source
        // across the midpoint and poison both ownership and target validation.
        Creature* laneSource = sources[laneIndex];
        Creature* otherSource = sources[1 - laneIndex];

        auto observeDrudgeDeath = [&]()
        {
            bool const source0Alive = sources[0]->IsAlive();
            bool const source1Alive = sources[1]->IsAlive();
            if (source0Alive == source1Alive)
                return;
            if (Party().ValidationRouteDrudgeDeathAttemptId != Cohort().AttemptId
                || Party().ValidationRouteDrudgeDeathWipeGeneration != Cohort().Raid.WipeGeneration
                || Party().ValidationRouteDrudgeDeathRouteGeneration != Party().ValidationRouteGeneration)
            {
                Party().ValidationRouteDrudgeDeathAttemptId = Cohort().AttemptId;
                Party().ValidationRouteDrudgeDeathWipeGeneration = Cohort().Raid.WipeGeneration;
                Party().ValidationRouteDrudgeDeathRouteGeneration = Party().ValidationRouteGeneration;
                Party().ValidationRouteDrudgeDeathSourceSpawnId = 0;
                Party().ValidationRouteDrudgeDeathSourceGuid = 0;
                Party().ValidationRouteDrudgeSurvivorSourceSpawnId = 0;
                Party().ValidationRouteDrudgeSurvivorSourceGuid = 0;
                Party().ValidationRouteDrudgeDeathEvidenceSequence = 0;
                Party().ValidationRouteDrudgeRageWaitEvidenceSequence = 0;
                Party().ValidationRouteDrudgeRageAuraEvidenceSequence = 0;
            }
            if (Party().ValidationRouteDrudgeDeathEvidenceSequence != 0)
                return;
            Creature* const deadSource = source0Alive ? sources[1] : sources[0];
            Creature* const survivorSource = source0Alive ? sources[0] : sources[1];
            Party().ValidationRouteDrudgeDeathSourceSpawnId = source0Alive ? 250141 : 250140;
            Party().ValidationRouteDrudgeDeathSourceGuid = deadSource->GetGUID().GetCounter();
            Party().ValidationRouteDrudgeSurvivorSourceSpawnId = source0Alive ? 250140 : 250141;
            Party().ValidationRouteDrudgeSurvivorSourceGuid = survivorSource->GetGUID().GetCounter();
            Party().ValidationRouteDrudgeDeathEvidenceSequence = ++Cohort().Raid.EvidenceSequence;
            record(deadSource, "drudge_first_source_death_observed",
                sources[0]->GetExactDist2d(sources[1]));
        };
        observeDrudgeDeath();

        // Bind ownership to the frozen lane tank, not to whichever tank
        // happens to be present in the native threat table.  The Drudge Rush
        // selector is native and chooses the farthest threat-list player;
        // keeping both tanks on their own source and both four-player groups
        // on the opposite side is what makes that selector safe without
        // rewriting or filtering the encounter spell.
        Player* laneTank = nullptr;
        Player* otherTank = nullptr;
        uint32 const laneTankSlot = Cohort().Config.ValidationRouteSplitLaneTankSlots[laneIndex];
        uint32 const otherTankSlot = Cohort().Config.ValidationRouteSplitLaneTankSlots[1 - laneIndex];
        for (WorldBotState const& cohortState : Party().Bots)
        {
            Player* member = GetLoadedBot(cohortState);
            if (!member || !member->IsInWorld() || member->GetMap() != bot->GetMap())
                continue;
            auto memberRoster = Cohort().Raid.RosterByGuid.find(member->GetGUID().GetCounter());
            if (memberRoster == Cohort().Raid.RosterByGuid.end()
                || !memberRoster->second.Active || !memberRoster->second.LeaseOwned)
                continue;
            uint32 memberSlot = memberRoster->second.SlotIndex + 1;
            if (memberSlot == laneTankSlot && memberRoster->second.Role == "tank")
                laneTank = member;
            else if (memberSlot == otherTankSlot && memberRoster->second.Role == "tank")
                otherTank = member;
        }

        auto strictNativePath = [bot](float x, float y, float z,
            bool requireExactEnd = false,
            std::string* rejectionOut = nullptr) -> bool
        {
            auto reject = [rejectionOut](std::string reason)
            {
                if (rejectionOut)
                    *rejectionOut = std::move(reason);
                return false;
            };
            if (!bot || !bot->GetMap())
                return reject("drudge_anchor_map_unavailable");
            float floorZ = bot->GetMap()->GetHeight(bot->GetPhaseShift(), x, y, z + 2.0f, true, 8.0f);
            if (floorZ <= INVALID_HEIGHT || std::fabs(floorZ - z) > 4.0f)
                return reject("drudge_anchor_floor_rejected");
            PathGenerator path(bot);
            bool pathOk = path.CalculatePath(x, y, z, false);
            PathType pathType = path.GetPathType();
            bool const pathValid = pathOk
                && !(pathType & PATHFIND_NOPATH)
                && !(pathType & PATHFIND_NOT_USING_PATH)
                && !(pathType & PATHFIND_INCOMPLETE)
                && !(pathType & PATHFIND_SHORTCUT)
                && !(pathType & PATHFIND_FARFROMPOLY);
            if (!pathValid)
                return reject("drudge_anchor_native_path_rejected:path_type="
                    + std::to_string(uint32(pathType)));
            if (!requireExactEnd)
            {
                if (rejectionOut)
                    rejectionOut->clear();
                return true;
            }
            G3D::Vector3 const& actualEnd = path.GetActualEndPosition();
            float const end2d = std::hypot(actualEnd.x - x, actualEnd.y - y);
            float const endZ = std::fabs(actualEnd.z - z);
            if (end2d > 0.25f || endZ > 1.0f)
                return reject("drudge_anchor_native_end_rejected:end2d="
                    + std::to_string(end2d) + ":endz=" + std::to_string(endZ));
            if (rejectionOut)
                rejectionOut->clear();
            return true;
        };
        auto strictTankRecoveryPath = [&](float x, float y, float z) -> bool
        {
            if (!assignedTank || !otherTank || !bot->GetMap())
                return false;
            float const floorZ = bot->GetMap()->GetHeight(
                bot->GetPhaseShift(), x, y, z + 2.0f, true, 8.0f);
            if (floorZ <= INVALID_HEIGHT || std::fabs(floorZ - z) > 4.0f)
                return false;
            PathGenerator path(bot);
            bool const pathCalculated = path.CalculatePath(x, y, z, false);
            PathType const pathType = pathCalculated
                ? path.GetPathType() : PATHFIND_NOPATH;
            if (!pathCalculated || (pathType & PATHFIND_NOPATH)
                || (pathType & PATHFIND_NOT_USING_PATH)
                || (pathType & PATHFIND_INCOMPLETE)
                || (pathType & PATHFIND_SHORTCUT)
                || (pathType & PATHFIND_FARFROMPOLY))
                return false;
            G3D::Vector3 const& actualEnd = path.GetActualEndPosition();
            if (std::hypot(actualEnd.x - x, actualEnd.y - y) > 0.25f
                || std::fabs(actualEnd.z - z) > 1.0f)
                return false;

            std::vector<BotRaidDrudgeGeometry::Point2d> points;
            points.push_back({ bot->GetPositionX(), bot->GetPositionY() });
            for (G3D::Vector3 const& point : path.GetPath())
                points.push_back({ point.x, point.y });
            points.push_back({ actualEnd.x, actualEnd.y });
            float const tankLaneSign = laneIndex == 0 ? -1.0f : 1.0f;
            float const otherTankProjection =
                (otherTank->GetPositionX() - midpointX) * axisX
                + (otherTank->GetPositionY() - midpointY) * axisY;
            return BotRaidDrudgeGeometry::RecoveryPathPreservesTankSeparation(
                points, midpointX, midpointY, axisX, axisY, tankLaneSign,
                -tankLaneSign * otherTankProjection,
                Cohort().Config.ValidationRouteSplitMinimumSeparationYards);
        };

        // Every non-tank owns a stable, slot-derived point.  A shared
        // groupAnchor is only a coarse lane reference; accepting it directly
        // lets four members stack on one polygon and makes the native
        // farthest-player selector non-deterministic.  Keep the spacing small
        // enough for the corridor, but larger than the configured navigation
        // tolerance so the points are collision-distinct.
        float const sameLaneMemberMinimum = std::max(3.0f,
            Cohort().Config.ValidationRouteSplitNavigationMarginYards
                + Cohort().Config.ValidationRouteSplitArrivalToleranceYards * 0.5f);
        auto uniqueGroupAnchor = [&](uint32 slot) -> std::pair<float, float>
        {
            bool const tankSlot = std::find(
                Cohort().Config.ValidationRouteSplitLaneTankSlots.begin(),
                Cohort().Config.ValidationRouteSplitLaneTankSlots.end(), slot)
                != Cohort().Config.ValidationRouteSplitLaneTankSlots.end();
            bool const recoveryFormation = tankSlot
                && drudgeRecoveryFormationActive();
            ValidationRouteMemberAnchor const* anchor = recoveryFormation
                ? declaredRecoveryTankAnchorFor(slot)
                : (tankSlot && combatTankStagingActive()
                    ? declaredNavigationTankAnchorFor(slot) : declaredAnchorFor(slot));
            if (anchor)
                return { anchor->X, anchor->Y };
            return { 0.0f, 0.0f };
        };
        auto anchorCandidatesFor = [&](uint32 slot) -> std::vector<std::pair<float, float>>
        {
            auto const [primaryX, primaryY] = uniqueGroupAnchor(slot);
            return { { primaryX, primaryY } };
        };

        auto anchorCacheMatchesGeneration = [&]()
        {
            return state.ValidationRouteDrudgeAnchorValid
                && state.ValidationRouteDrudgeAnchorAttemptId == Cohort().AttemptId
                && state.ValidationRouteDrudgeAnchorWipeGeneration == Cohort().Raid.WipeGeneration
                && state.ValidationRouteDrudgeAnchorRouteGeneration == Party().ValidationRouteGeneration
                && state.ValidationRouteDrudgeAnchorMapId == bot->GetMapId()
                && state.ValidationRouteDrudgeAnchorInstanceId == bot->GetInstanceId()
                && bot->GetInstanceId() != 0
                && state.ValidationRouteDrudgeAnchorSource0Identity
                    == sources[0]->GetGUID().GetRawValue()
                && state.ValidationRouteDrudgeAnchorSource1Identity
                    == sources[1]->GetGUID().GetRawValue();
        };

        // AnchorValid is a strict-native-path cache, not a proximity bit.  A
        // member can legitimately begin on the old declarative candidate K
        // while the selector has already chosen pathable candidate J.  Only
        // the exact scoped cache may certify that member; proximity to any
        // manifest candidate would let runtime accept K while capture later
        // reconstructs J (or no path at all).
        auto cachedAnchorSafe = [&](WorldBotState const& anchorState,
                                    Player const* member) -> bool
        {
            if (!member || anchorState.Guid != member->GetGUID()
                || !anchorState.ValidationRouteDrudgeAnchorValid
                || anchorState.ValidationRouteDrudgeAnchorAttemptId != Cohort().AttemptId
                || anchorState.ValidationRouteDrudgeAnchorWipeGeneration != Cohort().Raid.WipeGeneration
                || anchorState.ValidationRouteDrudgeAnchorRouteGeneration != Party().ValidationRouteGeneration
                || anchorState.ValidationRouteDrudgeAnchorMapId != bot->GetMapId()
                || anchorState.ValidationRouteDrudgeAnchorInstanceId != bot->GetInstanceId()
                || bot->GetInstanceId() == 0
                || anchorState.ValidationRouteDrudgeAnchorSource0Identity
                    != sources[0]->GetGUID().GetRawValue()
                || anchorState.ValidationRouteDrudgeAnchorSource1Identity
                    != sources[1]->GetGUID().GetRawValue())
                return false;
            auto memberRoster = Cohort().Raid.RosterByGuid.find(member->GetGUID().GetCounter());
            if (memberRoster == Cohort().Raid.RosterByGuid.end())
                return false;
            uint32 const memberSlot = memberRoster->second.SlotIndex + 1;
            bool const memberLaneA = std::find(
                Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(),
                memberSlot) != Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
            float const memberLaneSign = memberLaneA ? -1.0f : 1.0f;
            auto const candidates = anchorCandidatesFor(memberSlot);
            if (anchorState.ValidationRouteDrudgeAnchorCandidateIndex >= candidates.size()
                || Distance2d(anchorState.ValidationRouteDrudgeAnchorX,
                    anchorState.ValidationRouteDrudgeAnchorY,
                    candidates[anchorState.ValidationRouteDrudgeAnchorCandidateIndex].first,
                    candidates[anchorState.ValidationRouteDrudgeAnchorCandidateIndex].second)
                    > 0.01f)
                return false;
            float const projection = (anchorState.ValidationRouteDrudgeAnchorX - midpointX) * axisX
                + (anchorState.ValidationRouteDrudgeAnchorY - midpointY) * axisY;
            if (memberLaneSign * projection < laneSeparation * 0.25f)
                return false;
            if (memberRoster->second.Role == "tank")
            {
                uint32 const sourceIndex = memberSlot ==
                    Cohort().Config.ValidationRouteSplitLaneTankSlots[0] ? 0 : 1;
                if (memberSlot != Cohort().Config.ValidationRouteSplitLaneTankSlots[sourceIndex])
                    return false;
            }
            else if (Distance2d(anchorState.ValidationRouteDrudgeAnchorX,
                         anchorState.ValidationRouteDrudgeAnchorY, sources[0]->GetPositionX(),
                         sources[0]->GetPositionY()) < Cohort().Config.ValidationRouteMinimumDistanceYards
                || Distance2d(anchorState.ValidationRouteDrudgeAnchorX,
                         anchorState.ValidationRouteDrudgeAnchorY, sources[1]->GetPositionX(),
                         sources[1]->GetPositionY()) < Cohort().Config.ValidationRouteMinimumDistanceYards)
                return false;
            float const arrivalTolerance = memberRoster->second.Role == "tank"
                ? Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards
                : Cohort().Config.ValidationRouteSplitArrivalToleranceYards;
            return member->GetExactDist(anchorState.ValidationRouteDrudgeAnchorX,
                anchorState.ValidationRouteDrudgeAnchorY, anchorState.ValidationRouteDrudgeAnchorZ)
                <= arrivalTolerance;
        };

        auto groupPositionSafe = [&](Player const* member) -> bool
        {
            if (!member)
                return false;
            auto memberRoster = Cohort().Raid.RosterByGuid.find(member->GetGUID().GetCounter());
            if (memberRoster == Cohort().Raid.RosterByGuid.end())
                return false;
            uint32 const memberSlot = memberRoster->second.SlotIndex + 1;
            bool const memberLaneA = std::find(
                Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), memberSlot)
                != Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
            bool const memberLaneB = std::find(
                Cohort().Config.ValidationRouteSplitLaneBRosterSlots.begin(),
                Cohort().Config.ValidationRouteSplitLaneBRosterSlots.end(), memberSlot)
                != Cohort().Config.ValidationRouteSplitLaneBRosterSlots.end();
            if (memberLaneA == memberLaneB || memberRoster->second.Role == "tank")
                return false;
            float const memberLaneSign = memberLaneA ? -1.0f : 1.0f;
            float const minimumSafeDistance = Cohort().Config.ValidationRouteMinimumDistanceYards;
            if (Distance2d(member->GetPositionX(), member->GetPositionY(),
                    sources[0]->GetPositionX(), sources[0]->GetPositionY()) < minimumSafeDistance
                || Distance2d(member->GetPositionX(), member->GetPositionY(),
                    sources[1]->GetPositionX(), sources[1]->GetPositionY()) < minimumSafeDistance)
                return false;
            float const memberProjection =
                (member->GetPositionX() - midpointX) * axisX
                + (member->GetPositionY() - midpointY) * axisY;
            if (memberLaneSign * memberProjection < laneSeparation * 0.25f)
                return false;
            auto memberState = std::find_if(Party().Bots.begin(), Party().Bots.end(),
                [member](WorldBotState const& candidate)
                {
                    return candidate.Guid == member->GetGUID();
                });
            // Never certify a member from the declarative candidate list.  A
            // strict path search must first select and cache the exact
            // candidate for this member, scoped to attempt/wipe/route.
            if (memberState == Party().Bots.end()
                || !cachedAnchorSafe(*memberState, member))
                return false;
            for (WorldBotState const& cohortState : Party().Bots)
            {
                Player* other = GetLoadedBot(cohortState);
                if (!other || other == member || !other->IsInWorld()
                    || !other->IsAlive() || other->GetMap() != bot->GetMap())
                    continue;
                auto otherRoster = Cohort().Raid.RosterByGuid.find(other->GetGUID().GetCounter());
                if (otherRoster == Cohort().Raid.RosterByGuid.end()
                    || otherRoster->second.Role == "tank")
                    continue;
                uint32 const otherSlot = otherRoster->second.SlotIndex + 1;
                bool const otherLaneA = std::find(
                    Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                    Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), otherSlot)
                    != Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
                if (otherLaneA == memberLaneA
                    && member->GetExactDist2d(other) < sameLaneMemberMinimum)
                    return false;
            }
            return true;
        };

        auto exactRosterPrepullStaged = [&]() -> bool
        {
            std::set<uint32> stagedGuids;
            for (WorldBotState const& cohortState : Party().Bots)
            {
                Player* member = GetLoadedBot(cohortState);
                if (!member || !member->IsInWorld() || !member->IsAlive()
                    || member->GetMap() != bot->GetMap())
                    return false;
                auto memberRoster = Cohort().Raid.RosterByGuid.find(
                    member->GetGUID().GetCounter());
                if (memberRoster == Cohort().Raid.RosterByGuid.end()
                    || !memberRoster->second.Active || !memberRoster->second.LeaseOwned)
                    return false;
                bool const memberSafe = memberRoster->second.Role == "tank"
                    ? cachedAnchorSafe(cohortState, member)
                    : groupPositionSafe(member);
                if (!memberSafe)
                    return false;
                stagedGuids.insert(member->GetGUID().GetCounter());
            }
            return stagedGuids.size() == exactRosterSlots.size();
        };

        auto sourceOnFrozenLane = [&](Creature const* source, uint32 sourceIndex,
            float* projectionOut = nullptr) -> bool
        {
            if (!source)
                return false;
            float const sourceLaneSign = sourceIndex == 0 ? -1.0f : 1.0f;
            float const projection = (source->GetPositionX() - midpointX) * axisX
                + (source->GetPositionY() - midpointY) * axisY;
            if (projectionOut)
                *projectionOut = projection;
            return sourceLaneSign * projection >= laneSeparation * 0.25f;
        };

        auto selectPathableDrudgeAnchor = [&](bool tank) -> bool
        {
            std::vector<std::pair<float, float>> const candidates =
                anchorCandidatesFor(oneBasedSlot);

            auto candidateSpacingSafe = [&](float x, float y)
            {
                if (tank)
                    return true;
                bool const memberLaneA = laneA;
                for (WorldBotState const& cohortState : Party().Bots)
                {
                    Player* other = GetLoadedBot(cohortState);
                    if (!other || other == bot || !other->IsInWorld() || !other->IsAlive()
                        || other->GetMap() != bot->GetMap())
                        continue;
                    auto otherRoster = Cohort().Raid.RosterByGuid.find(
                        other->GetGUID().GetCounter());
                    if (otherRoster == Cohort().Raid.RosterByGuid.end()
                        || otherRoster->second.Role == "tank")
                        continue;
                    uint32 const otherSlot = otherRoster->second.SlotIndex + 1;
                    bool const otherLaneA = std::find(
                        Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                        Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), otherSlot)
                        != Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
                    if (otherLaneA != memberLaneA)
                        continue;
                    float otherX = other->GetPositionX();
                    float otherY = other->GetPositionY();
                    if (cohortState.ValidationRouteDrudgeAnchorValid
                        && cohortState.ValidationRouteDrudgeAnchorAttemptId == Cohort().AttemptId
                        && cohortState.ValidationRouteDrudgeAnchorWipeGeneration == Cohort().Raid.WipeGeneration
                        && cohortState.ValidationRouteDrudgeAnchorRouteGeneration == Party().ValidationRouteGeneration)
                    {
                        otherX = cohortState.ValidationRouteDrudgeAnchorX;
                        otherY = cohortState.ValidationRouteDrudgeAnchorY;
                    }
                    if (Distance2d(x, y, otherX, otherY) < sameLaneMemberMinimum)
                        return false;
                }
                return true;
            };

            auto cacheUsable = [&]()
            {
                if (!anchorCacheMatchesGeneration())
                    return false;
                if (state.ValidationRouteDrudgeAnchorCandidateIndex >= candidates.size()
                    || Distance2d(state.ValidationRouteDrudgeAnchorX,
                        state.ValidationRouteDrudgeAnchorY,
                        candidates[state.ValidationRouteDrudgeAnchorCandidateIndex].first,
                        candidates[state.ValidationRouteDrudgeAnchorCandidateIndex].second)
                        > 0.01f)
                    return false;
                float const projection =
                    (state.ValidationRouteDrudgeAnchorX - midpointX) * axisX
                    + (state.ValidationRouteDrudgeAnchorY - midpointY) * axisY;
                if (laneSign * projection < laneSeparation * 0.25f)
                    return false;
                if (tank)
                    return true;
                return Distance2d(state.ValidationRouteDrudgeAnchorX,
                        state.ValidationRouteDrudgeAnchorY, sources[0]->GetPositionX(),
                        sources[0]->GetPositionY())
                        >= Cohort().Config.ValidationRouteMinimumDistanceYards
                    && Distance2d(state.ValidationRouteDrudgeAnchorX,
                        state.ValidationRouteDrudgeAnchorY, sources[1]->GetPositionX(),
                        sources[1]->GetPositionY())
                        >= Cohort().Config.ValidationRouteMinimumDistanceYards;
            };
            if (cacheUsable())
                return true;

            bool const priorScopeMatches = state.ValidationRouteDrudgeAnchorPathProven
                && state.ValidationRouteDrudgeAnchorAttemptId == Cohort().AttemptId
                && state.ValidationRouteDrudgeAnchorWipeGeneration == Cohort().Raid.WipeGeneration
                && state.ValidationRouteDrudgeAnchorRouteGeneration
                    == Party().ValidationRouteGeneration
                && state.ValidationRouteDrudgeAnchorMapId == bot->GetMapId()
                && state.ValidationRouteDrudgeAnchorInstanceId == bot->GetInstanceId()
                && bot->GetInstanceId() != 0
                && state.ValidationRouteDrudgeAnchorSource0Identity
                    == sources[0]->GetGUID().GetRawValue()
                && state.ValidationRouteDrudgeAnchorSource1Identity
                    == sources[1]->GetGUID().GetRawValue();
            bool const priorCandidateMatches = priorScopeMatches
                && state.ValidationRouteDrudgeAnchorCandidateIndex < candidates.size()
                && Distance2d(state.ValidationRouteDrudgeAnchorX,
                    state.ValidationRouteDrudgeAnchorY,
                    candidates[state.ValidationRouteDrudgeAnchorCandidateIndex].first,
                    candidates[state.ValidationRouteDrudgeAnchorCandidateIndex].second) <= 0.01f;
            float const priorProjection = (state.ValidationRouteDrudgeAnchorX - midpointX) * axisX
                + (state.ValidationRouteDrudgeAnchorY - midpointY) * axisY;
            bool const priorLaneSafe = priorCandidateMatches
                && laneSign * priorProjection >= laneSeparation * 0.25f;
            bool const sourcesSeparated = sources[0]->GetExactDist2d(sources[1])
                >= laneSeparation;
            bool const recoveryFormationActiveForProof =
                drudgeRecoveryFormationActive();
            bool const priorSourceSafe = tank
                ? (priorCandidateMatches && (recoveryFormationActiveForProof
                    || (sourcesSeparated
                        && sourceOnFrozenLane(sources[0], 0)
                        && sourceOnFrozenLane(sources[1], 1)
                        && Distance2d(state.ValidationRouteDrudgeAnchorX,
                            state.ValidationRouteDrudgeAnchorY,
                            sources[laneIndex]->GetPositionX(),
                            sources[laneIndex]->GetPositionY())
                            <= Cohort().Config.ValidationRouteSplitMinimumSeparationYards)))
                : (priorCandidateMatches
                    && Distance2d(state.ValidationRouteDrudgeAnchorX,
                        state.ValidationRouteDrudgeAnchorY, sources[0]->GetPositionX(),
                        sources[0]->GetPositionY())
                        >= Cohort().Config.ValidationRouteMinimumDistanceYards
                    && Distance2d(state.ValidationRouteDrudgeAnchorX,
                        state.ValidationRouteDrudgeAnchorY, sources[1]->GetPositionX(),
                        sources[1]->GetPositionY())
                        >= Cohort().Config.ValidationRouteMinimumDistanceYards);
            bool const memberAtPriorAnchor = priorCandidateMatches
                && bot->GetExactDist(state.ValidationRouteDrudgeAnchorX,
                    state.ValidationRouteDrudgeAnchorY,
                    state.ValidationRouteDrudgeAnchorZ)
                    <= (tank
                        ? Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards
                        : Cohort().Config.ValidationRouteSplitArrivalToleranceYards);
            BotRaidDrudgeGeometry::Scope const proofScope{
                Cohort().AttemptId,
                Cohort().Raid.WipeGeneration,
                Party().ValidationRouteGeneration,
                bot->GetMapId(),
                bot->GetInstanceId(),
                sources[0]->GetGUID().GetRawValue(),
                sources[1]->GetGUID().GetRawValue()
            };
            BotRaidDrudgeGeometry::State proofState;
            proofState.Identity = proofScope;
            proofState.PriorPathProofAvailable =
                state.ValidationRouteDrudgeAnchorPathProven;
            BotRaidDrudgeGeometry::Input proofInput;
            proofInput.Identity = proofScope;
            proofInput.EvaluatePriorPathProof = true;
            proofInput.PriorProofScopeMatches = priorScopeMatches;
            proofInput.PriorProofCandidateMatches = priorCandidateMatches;
            proofInput.MemberAtProvenAnchor = memberAtPriorAnchor;
            proofInput.DynamicLaneSafe = priorLaneSafe;
            proofInput.DynamicSourceSafe = priorSourceSafe;
            proofInput.DynamicSpacingSafe = priorCandidateMatches
                && candidateSpacingSafe(state.ValidationRouteDrudgeAnchorX,
                    state.ValidationRouteDrudgeAnchorY);
            BotRaidDrudgeGeometry::Result const proofTransition =
                BotRaidDrudgeGeometry::Advance(proofState, proofInput);
            state.ValidationRouteDrudgeAnchorPathProven =
                proofTransition.Next.PriorPathProofAvailable;
            if (proofTransition.ReactivatePriorPathProof)
            {
                state.ValidationRouteDrudgeAnchorValid = true;
                return true;
            }

            state.ValidationRouteDrudgeAnchorValid = false;
            uint64 const nowMs = NowMs();

            for (size_t candidateIndex = 0; candidateIndex < candidates.size(); ++candidateIndex)
            {
                ValidationRouteMemberAnchor const* candidateAnchor = tank
                    && drudgeRecoveryFormationActive()
                    ? declaredRecoveryTankAnchorFor(oneBasedSlot)
                    : (tank && combatTankStagingActive()
                        ? declaredNavigationTankAnchorFor(oneBasedSlot)
                        : declaredAnchorFor(oneBasedSlot));
                if (!candidateAnchor)
                {
                    state.LastPathRejectReason = "drudge_anchor_missing";
                    state.LastRecoveryResult = state.LastPathRejectReason;
                    continue;
                }
                float const candidateZ = candidateAnchor->Z;
                float const projection = (candidates[candidateIndex].first - midpointX) * axisX
                    + (candidates[candidateIndex].second - midpointY) * axisY;
                if (laneSign * projection < laneSeparation * 0.25f)
                {
                    state.LastPathRejectReason = "drudge_anchor_lane_unsafe";
                    state.LastRecoveryResult = state.LastPathRejectReason;
                    continue;
                }
                bool const dynamicSourceSafe = tank
                    || (Distance2d(candidates[candidateIndex].first,
                            candidates[candidateIndex].second, sources[0]->GetPositionX(),
                            sources[0]->GetPositionY()) >= Cohort().Config.ValidationRouteMinimumDistanceYards
                        && Distance2d(candidates[candidateIndex].first,
                            candidates[candidateIndex].second, sources[1]->GetPositionX(),
                            sources[1]->GetPositionY()) >= Cohort().Config.ValidationRouteMinimumDistanceYards);
                bool const dynamicSpacingSafe = tank
                    || candidateSpacingSafe(candidates[candidateIndex].first,
                        candidates[candidateIndex].second);
                BotRaidDrudgeGeometry::AnchorPathSearchDecision const pathSearch =
                    BotRaidDrudgeGeometry::SelectAnchorPathSearch(
                        state.ValidationRouteDrudgeAnchorSearchCooldownUntilMs,
                        nowMs, dynamicSourceSafe, dynamicSpacingSafe);
                state.ValidationRouteDrudgeAnchorSearchCooldownUntilMs =
                    pathSearch.RetryAfterMs;
                if (pathSearch.SourceBlocked)
                {
                    // Dynamic source proximity is expected immediately after
                    // a Rush lands on the sealed anchor.  Do not arm the
                    // expensive-path heartbeat here: the assigned tank can
                    // pull the source clear on the next tick, and that exact
                    // source-safe edge must receive an immediate return-path
                    // attempt.
                    state.LastPathRejectReason = "drudge_anchor_source_unsafe";
                    state.LastRecoveryResult = state.LastPathRejectReason;
                    continue;
                }
                if (pathSearch.SpacingBlocked)
                {
                    // A transient member crossing must not preserve an older
                    // native-path retry delay after spacing becomes safe.
                    state.LastPathRejectReason = "drudge_anchor_spacing_unsafe";
                    state.LastRecoveryResult = state.LastPathRejectReason;
                    continue;
                }
                if (!pathSearch.NativePathSearchDue)
                {
                    state.LastPathRejectReason = "drudge_anchor_path_retry_cooldown";
                    state.LastRecoveryResult = state.LastPathRejectReason;
                    continue;
                }
                std::string nativePathRejection;
                if (!strictNativePath(candidates[candidateIndex].first,
                        candidates[candidateIndex].second, candidateZ, tank,
                        &nativePathRejection))
                {
                    // Only a real floor/native-path rejection is rate-limited.
                    // Dynamic source and spacing predicates above remain
                    // edge-responsive so they cannot consume the native
                    // 20-second Rush interval before the first retry.
                    state.ValidationRouteDrudgeAnchorSearchCooldownUntilMs = nowMs
                        + RepeatableDiagnosticEventHeartbeatMs;
                    state.LastPathRejectReason = nativePathRejection.empty()
                        ? "drudge_anchor_native_path_rejected" : nativePathRejection;
                    state.LastRecoveryResult = state.LastPathRejectReason;
                    continue;
                }
                state.ValidationRouteDrudgeAnchorValid = true;
                state.ValidationRouteDrudgeAnchorPathProven = true;
                state.ValidationRouteDrudgeAnchorAttemptId = Cohort().AttemptId;
                state.ValidationRouteDrudgeAnchorWipeGeneration = Cohort().Raid.WipeGeneration;
                state.ValidationRouteDrudgeAnchorRouteGeneration = Party().ValidationRouteGeneration;
                state.ValidationRouteDrudgeAnchorMapId = bot->GetMapId();
                state.ValidationRouteDrudgeAnchorInstanceId = bot->GetInstanceId();
                state.ValidationRouteDrudgeAnchorSource0Identity =
                    sources[0]->GetGUID().GetRawValue();
                state.ValidationRouteDrudgeAnchorSource1Identity =
                    sources[1]->GetGUID().GetRawValue();
                state.ValidationRouteDrudgeAnchorCandidateIndex = uint32(candidateIndex);
                state.ValidationRouteDrudgeAnchorX = candidates[candidateIndex].first;
                state.ValidationRouteDrudgeAnchorY = candidates[candidateIndex].second;
                state.ValidationRouteDrudgeAnchorZ = candidateZ;
                state.LastPathRejectReason.clear();
                state.LastRecoveryResult.clear();
                return true;
            }
            return false;
        };

        auto exactRosterReSeparated = [&]() -> bool
        {
            if (!laneTank || !otherTank)
                return false;
            if (laneTank->GetMap() != bot->GetMap() || otherTank->GetMap() != bot->GetMap()
                || laneTank->GetExactDist2d(otherTank) < Cohort().Config.ValidationRouteSplitMinimumSeparationYards)
                return false;
            if (sources[0]->GetExactDist2d(sources[1])
                < laneSeparation)
                return false;
            if (!sourceOnFrozenLane(sources[0], 0)
                || !sourceOnFrozenLane(sources[1], 1))
                return false;
            auto tankOnLaneSide = [&](Player const* tank, uint32 slot) -> bool
            {
                if (!tank || !tank->IsAlive())
                    return false;
                bool const tankLaneA = std::find(
                    Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                    Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), slot)
                    != Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
                float const tankLaneSign = tankLaneA ? -1.0f : 1.0f;
                float const projection = (tank->GetPositionX() - midpointX) * axisX
                    + (tank->GetPositionY() - midpointY) * axisY;
                return tankLaneSign * projection >= laneSeparation * 0.25f;
            };
            if (!tankOnLaneSide(laneTank, laneTankSlot)
                || !tankOnLaneSide(otherTank, otherTankSlot))
                return false;
            if (laneTank->GetExactDist2d(laneSource)
                    > Cohort().Config.ValidationRouteSplitMinimumSeparationYards
                || otherTank->GetExactDist2d(otherSource)
                    > Cohort().Config.ValidationRouteSplitMinimumSeparationYards)
                return false;
            if (laneSource->IsAlive() && laneSource->GetVictim() != laneTank)
                return false;
            if (otherSource->IsAlive() && otherSource->GetVictim() != otherTank)
                return false;
            for (WorldBotState const& cohortState : Party().Bots)
            {
                Player* member = GetLoadedBot(cohortState);
                if (!member || !member->IsInWorld() || !member->IsAlive()
                    || member->GetMap() != bot->GetMap())
                    return false;
                auto memberRoster = Cohort().Raid.RosterByGuid.find(member->GetGUID().GetCounter());
                if (memberRoster == Cohort().Raid.RosterByGuid.end()
                    || !memberRoster->second.Active || !memberRoster->second.LeaseOwned)
                    return false;
                if (memberRoster->second.Role == "tank")
                {
                    uint32 memberSlot = memberRoster->second.SlotIndex + 1;
                    Player* expectedTank = memberSlot == laneTankSlot ? laneTank
                        : (memberSlot == otherTankSlot ? otherTank : nullptr);
                    if (member != expectedTank)
                        return false;
                    continue;
                }
                if (!groupPositionSafe(member))
                    return false;
            }
            return true;
        };

        auto markAllRosterReseparated = [&](ValidationRouteDrudgeChargeObservation& observation)
        {
            std::set<uint32> exactGuids;
            for (WorldBotState const& cohortState : Party().Bots)
                if (!cohortState.Guid.IsEmpty())
                    exactGuids.insert(cohortState.Guid.GetCounter());
            observation.ReseparatedRosterGuids = exactGuids;
            observation.ReseparationRecorded = true;
            observation.Home0X = homeA.GetPositionX();
            observation.Home0Y = homeA.GetPositionY();
            observation.Home1X = homeB.GetPositionX();
            observation.Home1Y = homeB.GetPositionY();
            observation.MidpointX = midpointX;
            observation.MidpointY = midpointY;
            observation.AxisX = axisX;
            observation.AxisY = axisY;
            observation.LaneSeparation = laneSeparation;
            observation.MinimumDistance = Cohort().Config.ValidationRouteMinimumDistanceYards;
            observation.NavigationMargin = Cohort().Config.ValidationRouteSplitNavigationMarginYards;
            float const laneSignA = -1.0f;
            float const tankAnchorAX = midpointX + laneSignA * axisX * laneSeparation * 0.5f;
            float const tankAnchorAY = midpointY + laneSignA * axisY * laneSeparation * 0.5f;
            float const groupOffset = observation.MinimumDistance + observation.NavigationMargin;
            observation.GroupAnchorBaseX = tankAnchorAX + laneSignA * axisX * groupOffset;
            observation.GroupAnchorBaseY = tankAnchorAY + laneSignA * axisY * groupOffset;
            observation.Source0X = sources[0]->GetPositionX();
            observation.Source0Y = sources[0]->GetPositionY();
            observation.Source0LaneSideValid = sourceOnFrozenLane(
                sources[0], 0, &observation.Source0Projection);
            observation.Source0HealthPct = UnitHealthPct(sources[0]);
            observation.Source1X = sources[1]->GetPositionX();
            observation.Source1Y = sources[1]->GetPositionY();
            observation.Source1LaneSideValid = sourceOnFrozenLane(
                sources[1], 1, &observation.Source1Projection);
            observation.Source1HealthPct = UnitHealthPct(sources[1]);
            observation.Source0VictimGuid = sources[0]->GetVictim()
                ? sources[0]->GetVictim()->GetGUID().GetCounter() : 0;
            observation.Source1VictimGuid = sources[1]->GetVictim()
                ? sources[1]->GetVictim()->GetGUID().GetCounter() : 0;
            observation.Source0Alive = sources[0]->IsAlive();
            observation.Source1Alive = sources[1]->IsAlive();
            Player* const tank0 = laneIndex == 0 ? laneTank : otherTank;
            Player* const tank1 = laneIndex == 0 ? otherTank : laneTank;
            if (tank0)
            {
                observation.Tank0X = tank0->GetPositionX();
                observation.Tank0Y = tank0->GetPositionY();
                observation.Tank0Guid = tank0->GetGUID().GetCounter();
                observation.Tank0Slot = Cohort().Config.ValidationRouteSplitLaneTankSlots[0];
                observation.Tank0Projection = (observation.Tank0X - midpointX) * axisX
                    + (observation.Tank0Y - midpointY) * axisY;
                observation.Tank0SourceDistance = tank0->GetExactDist2d(sources[0]);
            }
            if (tank1)
            {
                observation.Tank1X = tank1->GetPositionX();
                observation.Tank1Y = tank1->GetPositionY();
                observation.Tank1Guid = tank1->GetGUID().GetCounter();
                observation.Tank1Slot = Cohort().Config.ValidationRouteSplitLaneTankSlots[1];
                observation.Tank1Projection = (observation.Tank1X - midpointX) * axisX
                    + (observation.Tank1Y - midpointY) * axisY;
                observation.Tank1SourceDistance = tank1->GetExactDist2d(sources[1]);
            }
            observation.SourceSeparation = sources[0]->GetExactDist2d(sources[1]);
            observation.MinimumSourceSeparation =
                Cohort().Config.ValidationRouteSplitMinimumSeparationYards;
            observation.LaneTankX = laneTank->GetPositionX();
            observation.LaneTankY = laneTank->GetPositionY();
            observation.LaneTankGuid = laneTank->GetGUID().GetCounter();
            observation.LaneTankSlot = laneTankSlot;
            observation.LaneTankProjection =
                (laneTank->GetPositionX() - midpointX) * axisX
                + (laneTank->GetPositionY() - midpointY) * axisY;
            observation.LaneTankSourceDistance = laneTank->GetExactDist2d(laneSource);
            observation.OtherTankX = otherTank->GetPositionX();
            observation.OtherTankY = otherTank->GetPositionY();
            observation.OtherTankGuid = otherTank->GetGUID().GetCounter();
            observation.OtherTankSlot = otherTankSlot;
            observation.OtherTankProjection =
                (otherTank->GetPositionX() - midpointX) * axisX
                + (otherTank->GetPositionY() - midpointY) * axisY;
            observation.OtherTankSourceDistance = otherTank->GetExactDist2d(otherSource);
            observation.MinimumMemberSpacing = sameLaneMemberMinimum;
            observation.ArrivalTolerance =
                Cohort().Config.ValidationRouteSplitArrivalToleranceYards;
            observation.TankArrivalTolerance =
                Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards;
            observation.MemberGeometry.clear();
            for (WorldBotState const& cohortState : Party().Bots)
            {
                Player* member = GetLoadedBot(cohortState);
                if (!member)
                    continue;
                auto memberRoster = Cohort().Raid.RosterByGuid.find(
                    member->GetGUID().GetCounter());
                if (memberRoster == Cohort().Raid.RosterByGuid.end())
                    continue;
                ValidationRouteDrudgeMemberGeometry geometry;
                geometry.Guid = member->GetGUID().GetCounter();
                geometry.RosterSlot = memberRoster->second.SlotIndex + 1;
                geometry.X = member->GetPositionX();
                geometry.Y = member->GetPositionY();
                geometry.Projection = (geometry.X - midpointX) * axisX
                    + (geometry.Y - midpointY) * axisY;
                bool const memberLaneA = std::find(
                    Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                    Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), geometry.RosterSlot)
                    != Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
                float const memberLaneSign = memberLaneA ? -1.0f : 1.0f;
                geometry.LaneSideValid = memberLaneSign * geometry.Projection
                    >= laneSeparation * 0.25f;
                if (memberRoster->second.Role != "tank")
                {
                    auto candidates = anchorCandidatesFor(geometry.RosterSlot);
                    geometry.GroupAnchorBaseX = candidates.empty() ? 0.0f : candidates[0].first;
                    geometry.GroupAnchorBaseY = candidates.empty() ? 0.0f : candidates[0].second;
                    for (WorldBotState const& memberState : Party().Bots)
                        if (memberState.Guid.GetCounter() == geometry.Guid
                            && memberState.ValidationRouteDrudgeAnchorValid
                            && memberState.ValidationRouteDrudgeAnchorAttemptId == Cohort().AttemptId
                            && memberState.ValidationRouteDrudgeAnchorWipeGeneration == Cohort().Raid.WipeGeneration
                            && memberState.ValidationRouteDrudgeAnchorRouteGeneration == Party().ValidationRouteGeneration
                            && memberState.ValidationRouteDrudgeAnchorCandidateIndex < candidates.size()
                            && Distance2d(memberState.ValidationRouteDrudgeAnchorX,
                                memberState.ValidationRouteDrudgeAnchorY,
                                candidates[memberState.ValidationRouteDrudgeAnchorCandidateIndex].first,
                                candidates[memberState.ValidationRouteDrudgeAnchorCandidateIndex].second)
                                <= 0.01f)
                        {
                            geometry.AnchorCandidateIndex =
                                memberState.ValidationRouteDrudgeAnchorCandidateIndex;
                            geometry.AnchorX = memberState.ValidationRouteDrudgeAnchorX;
                            geometry.AnchorY = memberState.ValidationRouteDrudgeAnchorY;
                            geometry.AnchorDistance = Distance2d(geometry.X, geometry.Y,
                                geometry.AnchorX, geometry.AnchorY);
                            geometry.AnchorSelected = geometry.AnchorDistance <= observation.ArrivalTolerance;
                            // The cache is populated only after the strict
                            // native path validator succeeds.  Do not let a
                            // member that merely occupies legacy candidate K
                            // serialize as path-valid when selector/cache chose
                            // candidate J.
                            geometry.AnchorPathValid = geometry.AnchorSelected;
                            break;
                        }
                    float nearest = std::numeric_limits<float>::max();
                    for (size_t candidateIndex = 0; candidateIndex < candidates.size(); ++candidateIndex)
                    {
                        if (geometry.AnchorPathValid)
                            break;
                        float const distance = Distance2d(geometry.X, geometry.Y,
                            candidates[candidateIndex].first, candidates[candidateIndex].second);
                        if (distance < nearest)
                        {
                            nearest = distance;
                            if (!geometry.AnchorSelected)
                            {
                                geometry.AnchorCandidateIndex = uint32(candidateIndex);
                                geometry.AnchorX = candidates[candidateIndex].first;
                                geometry.AnchorY = candidates[candidateIndex].second;
                            }
                        }
                    }
                    if (!geometry.AnchorSelected)
                        geometry.AnchorDistance = nearest;
                    float nearestSameLane = std::numeric_limits<float>::max();
                    for (WorldBotState const& otherState : Party().Bots)
                    {
                        Player* other = GetLoadedBot(otherState);
                        if (!other || other == member)
                            continue;
                        auto otherRoster = Cohort().Raid.RosterByGuid.find(
                            other->GetGUID().GetCounter());
                        if (otherRoster == Cohort().Raid.RosterByGuid.end()
                            || otherRoster->second.Role == "tank")
                            continue;
                        uint32 const otherSlot = otherRoster->second.SlotIndex + 1;
                        bool const otherLaneA = std::find(
                            Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                            Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), otherSlot)
                            != Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
                        if (otherLaneA == memberLaneA)
                            nearestSameLane = std::min(nearestSameLane,
                                member->GetExactDist2d(other));
                    }
                    geometry.NearestSameLaneDistance = nearestSameLane == std::numeric_limits<float>::max()
                        ? 0.0f : nearestSameLane;
                    geometry.SameLaneSpacingValid = nearestSameLane == std::numeric_limits<float>::max()
                        || nearestSameLane >= observation.MinimumMemberSpacing;
                }
                observation.MemberGeometry.push_back(geometry);
            }
            Party().ValidationRouteDrudgeReseparatedRosterGuids.insert(
                exactGuids.begin(), exactGuids.end());
            for (WorldBotState& cohortState : Party().Bots)
                cohortState.LastValidationRouteDrudgeChargeGenerationHandled = observation.Sequence;
        };

        float const sourceSeparation = sources[0]->GetExactDist2d(sources[1]);
        auto chargeObservation = std::find_if(
            Party().ValidationRouteDrudgeChargeObservations.begin(),
            Party().ValidationRouteDrudgeChargeObservations.end(),
            [this](ValidationRouteDrudgeChargeObservation const& observation)
            {
                // The deque is the authoritative start order.  Do not use a
                // per-bot cursor here: a later landed Rush must not advance
                // past an earlier unlanded/undelivered observation for the
                // rest of the frozen roster.
                return !observation.ReseparationRecorded
                    && observation.AttemptId == Cohort().AttemptId
                    && observation.WipeGeneration == Cohort().Raid.WipeGeneration
                    && observation.RouteGeneration == Party().ValidationRouteGeneration;
            });
        bool const chargeAwaitingLanding = chargeObservation
            != Party().ValidationRouteDrudgeChargeObservations.end()
            && !chargeObservation->Landed;
        bool const nativeChargePending = chargeObservation
            != Party().ValidationRouteDrudgeChargeObservations.end()
            && chargeObservation->Landed;
        BotRaidDrudgeGeometry::Scope const geometryScope{
            Cohort().AttemptId,
            Cohort().Raid.WipeGeneration,
            Party().ValidationRouteGeneration,
            bot->GetMapId(),
            bot->GetInstanceId(),
            sources[0]->GetGUID().GetRawValue(),
            sources[1]->GetGUID().GetRawValue()
        };
        BotRaidDrudgeGeometry::State geometryState;
        geometryState.Identity = geometryScope;
        geometryState.LastChargeSequenceObserved =
            state.LastValidationRouteDrudgeChargeGenerationObserved;
        geometryState.PriorPathProofAvailable =
            state.ValidationRouteDrudgeAnchorPathProven;
        BotRaidDrudgeGeometry::Input rushGeometryInput;
        rushGeometryInput.Identity = geometryScope;
        rushGeometryInput.ChargePending = chargeObservation
            != Party().ValidationRouteDrudgeChargeObservations.end();
        rushGeometryInput.ChargeSequence = rushGeometryInput.ChargePending
            ? chargeObservation->Sequence : 0;
        rushGeometryInput.SourceCombatStarted = sourceCombatStarted;
        BotRaidDrudgeGeometry::Result const rushGeometry =
            BotRaidDrudgeGeometry::Advance(geometryState, rushGeometryInput);
        state.LastValidationRouteDrudgeChargeGenerationObserved =
            rushGeometry.Next.LastChargeSequenceObserved;
        state.ValidationRouteDrudgeAnchorPathProven =
            rushGeometry.Next.PriorPathProofAvailable;
        if (rushGeometry.InvalidateAnchor)
            state.ValidationRouteDrudgeAnchorValid = false;
        Creature* nativeChargeSource = nativeChargePending
            ? ObjectAccessor::GetCreature(*bot, chargeObservation->SourceGuid) : nullptr;
        Unit* nativeChargeTarget = nativeChargePending
            ? ObjectAccessor::GetUnit(*bot, chargeObservation->TargetGuid) : nullptr;
        bool nativeChargeTargetRoleViolation = false;
        bool nativeChargeContractViolation = nativeChargePending
            && (chargeObservation->AttemptId != Cohort().AttemptId
                || chargeObservation->WipeGeneration != Cohort().Raid.WipeGeneration
                || chargeObservation->RouteGeneration != Party().ValidationRouteGeneration
                || !chargeObservation->RangeValid
                || (chargeObservation->ObservedIntervalMs > 0
                    && !chargeObservation->IntervalValid)
                || !nativeChargeSource || !nativeChargeTarget);

        bool nativeChargeTargetLaneViolation = false;
        if (nativeChargeSource && nativeChargeTarget)
            if (Player* chargePlayer = nativeChargeTarget->ToPlayer())
            {
                auto targetRoster = Cohort().Raid.RosterByGuid.find(chargePlayer->GetGUID().GetCounter());
                if (targetRoster == Cohort().Raid.RosterByGuid.end())
                    nativeChargeTargetLaneViolation = true;
                else
                {
                    nativeChargeTargetRoleViolation = targetRoster->second.Role == "tank";
                    uint32 const targetSlot = targetRoster->second.SlotIndex + 1;
                    bool const targetInLaneA = std::find(
                        Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                        Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), targetSlot)
                        != Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
                    // Source order is the frozen lane binding.  A native Rush
                    // can move its caster after delivery; current position is
                    // not evidence of which lane selected the target.
                    bool const sourceInLaneA = nativeChargeSource == sources[0];
                    nativeChargeTargetLaneViolation = sourceInLaneA == targetInLaneA;
                }
            }
        nativeChargeContractViolation = nativeChargeContractViolation
            || nativeChargeTargetRoleViolation;

        // groupPositionSafe includes the selected native-path fallback.  The
        // formation gate must use that same predicate or a bot that reached a
        // valid fallback will repeatedly chase the unreachable primary point.
        bool const formationRequired = assignedTank
            ? !cachedAnchorSafe(state, bot)
            : !groupPositionSafe(bot);
        bool formationRequiredMutable = formationRequired;
        if (!assignedTank && !formationRequiredMutable && !anchorCacheMatchesGeneration())
        {
            // A bot may spawn directly on a legacy candidate.  Still prove
            // that point through the native path validator before certifying
            // the roster; otherwise the first clean snapshot has no
            // reconstructable path evidence.
            if (selectPathableDrudgeAnchor(false))
                formationRequiredMutable = !groupPositionSafe(bot);
        }
        bool const pairTooClose = sources[0]->IsAlive() && sources[1]->IsAlive()
            && sourceSeparation < laneSeparation;
        bool const nativeChargeTargetViolation = nativeChargePending
            && (nativeChargeContractViolation || nativeChargeTargetLaneViolation);
        if (nativeChargeTargetViolation)
            holdOffense();

        bool prepullStaged = Party().ValidationRouteDrudgePrepullStaged
            && Party().ValidationRouteDrudgePrepullAttemptId == Cohort().AttemptId
            && Party().ValidationRouteDrudgePrepullWipeGeneration == Cohort().Raid.WipeGeneration
            && Party().ValidationRouteDrudgePrepullRouteGeneration == Party().ValidationRouteGeneration;
        if (!prepullStaged
            && exactRosterPrepullStaged())
        {
            Party().ValidationRouteDrudgePrepullStaged = true;
            Party().ValidationRouteDrudgePrepullAttemptId = Cohort().AttemptId;
            Party().ValidationRouteDrudgePrepullWipeGeneration = Cohort().Raid.WipeGeneration;
            Party().ValidationRouteDrudgePrepullRouteGeneration = Party().ValidationRouteGeneration;
            prepullStaged = true;
            record(nullptr, "drudge_prepull_exact_roster_staged");
        }

        auto exactCombatTankPathsProven = [&]()
        {
            if (!laneTank || !otherTank || bot->GetInstanceId() == 0)
                return false;
            std::array<std::pair<float, float>, 2> navigationPoints{};
            std::array<bool, 2> navigationPointSeen{ false, false };
            for (Player const* tank : { laneTank, otherTank })
            {
                auto tankState = std::find_if(Party().Bots.begin(), Party().Bots.end(),
                    [tank](WorldBotState const& candidate)
                    {
                        return candidate.Guid == tank->GetGUID();
                    });
                auto tankRoster = Cohort().Raid.RosterByGuid.find(
                    tank->GetGUID().GetCounter());
                if (tankState == Party().Bots.end()
                    || tankRoster == Cohort().Raid.RosterByGuid.end())
                    return false;
                uint32 const tankSlot = tankRoster->second.SlotIndex + 1;
                ValidationRouteMemberAnchor const* combatAnchor =
                    declaredNavigationTankAnchorFor(tankSlot);
                if (!combatAnchor || !tankState->ValidationRouteDrudgeAnchorValid
                    || !tankState->ValidationRouteDrudgeAnchorPathProven
                    || tankState->ValidationRouteDrudgeAnchorAttemptId != Cohort().AttemptId
                    || tankState->ValidationRouteDrudgeAnchorWipeGeneration
                        != Cohort().Raid.WipeGeneration
                    || tankState->ValidationRouteDrudgeAnchorRouteGeneration
                        != Party().ValidationRouteGeneration
                    || tankState->ValidationRouteDrudgeAnchorMapId != bot->GetMapId()
                    || tankState->ValidationRouteDrudgeAnchorInstanceId != bot->GetInstanceId()
                    || tankState->ValidationRouteDrudgeAnchorSource0Identity
                        != sources[0]->GetGUID().GetRawValue()
                    || tankState->ValidationRouteDrudgeAnchorSource1Identity
                        != sources[1]->GetGUID().GetRawValue()
                    || tankState->ValidationRouteDrudgeAnchorCandidateIndex != 0
                    || Distance2d(tankState->ValidationRouteDrudgeAnchorX,
                        tankState->ValidationRouteDrudgeAnchorY,
                        combatAnchor->X, combatAnchor->Y) > 0.01f
                    || std::fabs(tankState->ValidationRouteDrudgeAnchorZ
                        - combatAnchor->Z) > 0.01f)
                    return false;
                uint32 const sourceIndex = tankSlot
                    == Cohort().Config.ValidationRouteSplitLaneTankSlots[0] ? 0 : 1;
                Position const& sourceHome = sourceIndex == 0 ? homeA : homeB;
                if (Distance2d(combatAnchor->X, combatAnchor->Y,
                        sourceHome.GetPositionX(), sourceHome.GetPositionY())
                    > Cohort().Config.ValidationRouteSplitMinimumSeparationYards)
                    return false;
                navigationPoints[sourceIndex] = {
                    combatAnchor->X, combatAnchor->Y
                };
                navigationPointSeen[sourceIndex] = true;
            }
            if (!navigationPointSeen[0] || !navigationPointSeen[1])
                return false;
            float const tankArrivalTolerance =
                Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards;
            // The accepted tank position is a disk around each sealed
            // navigation endpoint, not the endpoint itself.  Native radial
            // chase (subtracting the melee-stop radius) is 1-Lipschitz, so a
            // tank displaced by at most the arrival tolerance can displace
            // its predicted source by at most the same amount.  Prove the
            // complete arrival envelope before either tank is allowed to
            // move; exact-end geometry alone can authorize an unrecoverable
            // body pull at the inward edge of the tolerance disks.
            if (Distance2d(navigationPoints[0].first, navigationPoints[0].second,
                    navigationPoints[1].first, navigationPoints[1].second)
                < Cohort().Config.ValidationRouteSplitMinimumSeparationYards
                    + 2.0f * tankArrivalTolerance)
                return false;

            std::array<std::pair<float, float>, 2> predictedSources{};
            for (uint32 sourceIndex = 0; sourceIndex < 2; ++sourceIndex)
            {
                Position const& sourceHome = sourceIndex == 0 ? homeA : homeB;
                float const dx = navigationPoints[sourceIndex].first
                    - sourceHome.GetPositionX();
                float const dy = navigationPoints[sourceIndex].second
                    - sourceHome.GetPositionY();
                float const distance = std::hypot(dx, dy);
                if (distance <= 0.001f)
                    return false;
                float const travel = std::max(0.0f,
                    distance - Cohort().Config.ValidationRouteSplitNativeMeleeStopYards);
                predictedSources[sourceIndex] = {
                    sourceHome.GetPositionX() + dx * travel / distance,
                    sourceHome.GetPositionY() + dy * travel / distance
                };
                float const projection =
                    (predictedSources[sourceIndex].first - midpointX) * axisX
                    + (predictedSources[sourceIndex].second - midpointY) * axisY;
                float const sourceLaneSign = sourceIndex == 0 ? -1.0f : 1.0f;
                if (sourceLaneSign * projection
                    < laneSeparation * 0.25f + tankArrivalTolerance)
                    return false;
            }
            if (Distance2d(predictedSources[0].first, predictedSources[0].second,
                    predictedSources[1].first, predictedSources[1].second)
                < laneSeparation + 2.0f * tankArrivalTolerance)
                return false;
            for (ValidationRouteMemberAnchor const& memberAnchor :
                Cohort().Config.ValidationRouteSplitMemberAnchors)
            {
                if (std::find(Cohort().Config.ValidationRouteSplitLaneTankSlots.begin(),
                        Cohort().Config.ValidationRouteSplitLaneTankSlots.end(),
                        memberAnchor.RosterSlot)
                    != Cohort().Config.ValidationRouteSplitLaneTankSlots.end())
                    continue;
                if (Distance2d(memberAnchor.X, memberAnchor.Y,
                        predictedSources[0].first, predictedSources[0].second)
                        < Cohort().Config.ValidationRouteMinimumDistanceYards
                            + tankArrivalTolerance
                    || Distance2d(memberAnchor.X, memberAnchor.Y,
                        predictedSources[1].first, predictedSources[1].second)
                        < Cohort().Config.ValidationRouteMinimumDistanceYards
                            + tankArrivalTolerance)
                    return false;
            }
            return true;
        };

        auto exactRecoveryTankPathsProven = [&]()
        {
            if (!laneTank || !otherTank || bot->GetInstanceId() == 0)
                return false;
            std::array<std::pair<float, float>, 2> recoveryPoints{};
            std::array<bool, 2> recoveryPointSeen{ false, false };
            for (Player const* tank : { laneTank, otherTank })
            {
                auto tankState = std::find_if(Party().Bots.begin(), Party().Bots.end(),
                    [tank](WorldBotState const& candidate)
                    {
                        return candidate.Guid == tank->GetGUID();
                    });
                auto tankRoster = Cohort().Raid.RosterByGuid.find(
                    tank->GetGUID().GetCounter());
                if (tankState == Party().Bots.end()
                    || tankRoster == Cohort().Raid.RosterByGuid.end())
                    return false;
                uint32 const tankSlot = tankRoster->second.SlotIndex + 1;
                ValidationRouteMemberAnchor const* recoveryAnchor =
                    declaredRecoveryTankAnchorFor(tankSlot);
                if (!recoveryAnchor || !tankState->ValidationRouteDrudgeAnchorValid
                    || !tankState->ValidationRouteDrudgeAnchorPathProven
                    || tankState->ValidationRouteDrudgeAnchorAttemptId != Cohort().AttemptId
                    || tankState->ValidationRouteDrudgeAnchorWipeGeneration
                        != Cohort().Raid.WipeGeneration
                    || tankState->ValidationRouteDrudgeAnchorRouteGeneration
                        != Party().ValidationRouteGeneration
                    || tankState->ValidationRouteDrudgeAnchorMapId != bot->GetMapId()
                    || tankState->ValidationRouteDrudgeAnchorInstanceId != bot->GetInstanceId()
                    || tankState->ValidationRouteDrudgeAnchorSource0Identity
                        != sources[0]->GetGUID().GetRawValue()
                    || tankState->ValidationRouteDrudgeAnchorSource1Identity
                        != sources[1]->GetGUID().GetRawValue()
                    || tankState->ValidationRouteDrudgeAnchorCandidateIndex != 0
                    || Distance2d(tankState->ValidationRouteDrudgeAnchorX,
                        tankState->ValidationRouteDrudgeAnchorY,
                        recoveryAnchor->X, recoveryAnchor->Y) > 0.01f
                    || std::fabs(tankState->ValidationRouteDrudgeAnchorZ
                        - recoveryAnchor->Z) > 0.01f)
                    return false;
                uint32 const sourceIndex = tankSlot
                    == Cohort().Config.ValidationRouteSplitLaneTankSlots[0] ? 0 : 1;
                float const recoveryProjection =
                    (recoveryAnchor->X - midpointX) * axisX
                    + (recoveryAnchor->Y - midpointY) * axisY;
                float const sourceLaneSign = sourceIndex == 0 ? -1.0f : 1.0f;
                float const worstSourceLaneInset =
                    Cohort().Config.ValidationRouteSplitNativeMeleeStopYards
                    + Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards;
                if (sourceLaneSign * recoveryProjection
                    < laneSeparation * 0.25f + worstSourceLaneInset)
                    return false;
                recoveryPoints[sourceIndex] = {
                    recoveryAnchor->X, recoveryAnchor->Y
                };
                recoveryPointSeen[sourceIndex] = true;
            }
            if (!recoveryPointSeen[0] || !recoveryPointSeen[1])
                return false;
            float const tankArrivalTolerance =
                Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards;
            float const meleeStop =
                Cohort().Config.ValidationRouteSplitNativeMeleeStopYards;
            if (Distance2d(recoveryPoints[0].first, recoveryPoints[0].second,
                    recoveryPoints[1].first, recoveryPoints[1].second)
                < laneSeparation + 2.0f * (meleeStop + tankArrivalTolerance))
                return false;
            float const memberClearance =
                Cohort().Config.ValidationRouteMinimumDistanceYards
                + meleeStop
                + Cohort().Config.ValidationRouteSplitArrivalToleranceYards
                + tankArrivalTolerance;
            for (ValidationRouteMemberAnchor const& memberAnchor :
                Cohort().Config.ValidationRouteSplitMemberAnchors)
            {
                if (std::find(Cohort().Config.ValidationRouteSplitLaneTankSlots.begin(),
                        Cohort().Config.ValidationRouteSplitLaneTankSlots.end(),
                        memberAnchor.RosterSlot)
                    != Cohort().Config.ValidationRouteSplitLaneTankSlots.end())
                    continue;
                if (Distance2d(memberAnchor.X, memberAnchor.Y,
                        recoveryPoints[0].first, recoveryPoints[0].second)
                        < memberClearance
                    || Distance2d(memberAnchor.X, memberAnchor.Y,
                        recoveryPoints[1].first, recoveryPoints[1].second)
                        < memberClearance)
                    return false;
            }
            return true;
        };

        // Phase one discovers and freezes both strict native paths without
        // moving either tank.  Even the tick that establishes the second
        // proof returns through this barrier; movement can begin only on a
        // later tick that observes the already-complete shared proof set.
        bool const recoveryFormationActive = drudgeRecoveryFormationActive();
        bool const combatTankPathsProvenBeforeTick = prepullStaged
            && !recoveryFormationActive && exactCombatTankPathsProven();
        bool const recoveryTankPathsProvenBeforeTick = prepullStaged
            && recoveryFormationActive && exactRecoveryTankPathsProven();
        bool const activeTankPathsProvenBeforeTick = recoveryFormationActive
            ? recoveryTankPathsProvenBeforeTick : combatTankPathsProvenBeforeTick;
        if (prepullStaged && !nativeChargePending
            && !activeTankPathsProvenBeforeTick)
        {
            bool pathSearchDue = false;
            bool currentTankPathProven = false;
            if (assignedTank)
            {
                pathSearchDue = NowMs()
                    >= state.ValidationRouteDrudgeAnchorSearchCooldownUntilMs;
                currentTankPathProven = selectPathableDrudgeAnchor(true);
            }
            holdOffense();
            if (sourceCombatStarted && !nativeChargePending
                && roster->second.Role == "healer"
                && tryRouteGroupHeal(bot, laneSource, false))
            {
                record(laneSource, "drudge_anchor_preflight_support", sourceSeparation);
                target = laneSource;
                state.TargetGuid = laneSource->GetGUID();
                return true;
            }
            char const* result = assignedTank && pathSearchDue && !currentTankPathProven
                ? "drudge_tank_anchor_strict_path_rejected"
                : "drudge_tank_anchor_preflight_wait";
            record(laneSource, result, sourceSeparation);
            target = laneSource;
            state.TargetGuid = laneSource->GetGUID();
            action = result;
            return true;
        }
        if (nativeChargePending && !recoveryTankPathsProvenBeforeTick)
        {
            bool currentTankPathProven = false;
            if (assignedTank)
                currentTankPathProven = selectPathableDrudgeAnchor(true);
            holdOffense();
            record(laneSource, currentTankPathProven
                ? "drudge_tank_recovery_anchor_preflight_wait"
                : "drudge_tank_recovery_anchor_strict_path_rejected",
                sourceSeparation);
            target = laneSource;
            state.TargetGuid = laneSource->GetGUID();
            return true;
        }

        auto exactCombatTankAnchorsSafe = [&]()
        {
            if (!laneTank || !otherTank)
                return false;
            for (Player const* tank : { laneTank, otherTank })
            {
                auto tankState = std::find_if(Party().Bots.begin(), Party().Bots.end(),
                    [tank](WorldBotState const& candidate)
                    {
                        return candidate.Guid == tank->GetGUID();
                    });
                if (tankState == Party().Bots.end() || !cachedAnchorSafe(*tankState, tank))
                    return false;
            }
            return true;
        };
        auto exactLiveRecoveryTankPathsPreflighted = [&]()
        {
            if (!laneTank || !otherTank || bot->GetInstanceId() == 0)
                return false;
            for (Player const* tank : { laneTank, otherTank })
            {
                auto tankState = std::find_if(Party().Bots.begin(), Party().Bots.end(),
                    [tank](WorldBotState const& candidate)
                    {
                        return candidate.Guid == tank->GetGUID();
                    });
                auto tankRoster = Cohort().Raid.RosterByGuid.find(
                    tank->GetGUID().GetCounter());
                if (tankState == Party().Bots.end()
                    || tankRoster == Cohort().Raid.RosterByGuid.end())
                    return false;
                ValidationRouteMemberAnchor const* recoveryAnchor =
                    declaredRecoveryTankAnchorFor(tankRoster->second.SlotIndex + 1);
                if (!recoveryAnchor
                    || !tankState->ValidationRouteDrudgeRecoveryAnchorPathProven
                    || tankState->ValidationRouteDrudgeAnchorAttemptId != Cohort().AttemptId
                    || tankState->ValidationRouteDrudgeAnchorWipeGeneration
                        != Cohort().Raid.WipeGeneration
                    || tankState->ValidationRouteDrudgeAnchorRouteGeneration
                        != Party().ValidationRouteGeneration
                    || tankState->ValidationRouteDrudgeAnchorMapId != bot->GetMapId()
                    || tankState->ValidationRouteDrudgeAnchorInstanceId != bot->GetInstanceId()
                    || tankState->ValidationRouteDrudgeAnchorSource0Identity
                        != sources[0]->GetGUID().GetRawValue()
                    || tankState->ValidationRouteDrudgeAnchorSource1Identity
                        != sources[1]->GetGUID().GetRawValue()
                    || Distance2d(tankState->ValidationRouteDrudgeRecoveryAnchorX,
                        tankState->ValidationRouteDrudgeRecoveryAnchorY,
                        recoveryAnchor->X, recoveryAnchor->Y) > 0.01f
                    || std::fabs(tankState->ValidationRouteDrudgeRecoveryAnchorZ
                        - recoveryAnchor->Z) > 0.01f)
                    return false;
            }
            return true;
        };
        // Detour-only probes cannot reproduce Map::GetHeight and the exact
        // PathGenerator terminal Z used by the live server.  Once both tanks
        // occupy their sealed combat anchors, prove both recovery legs with
        // the live PathGenerator before taunt, threat seed, or ordinary
        // offense can begin.  A bad sealed Z therefore ends the diagnostic at
        // preflight instead of spending a native Rush cycle validating a path
        // that the production server will reject.
        bool const liveRecoveryPreflightedBeforeTick =
            exactLiveRecoveryTankPathsPreflighted();
        if (prepullStaged && !nativeChargePending
            && exactCombatTankAnchorsSafe()
            && !liveRecoveryPreflightedBeforeTick)
        {
            bool currentTankPathProven = false;
            std::string nativePathRejection;
            if (assignedTank)
            {
                ValidationRouteMemberAnchor const* recoveryAnchor =
                    declaredRecoveryTankAnchorFor(oneBasedSlot);
                currentTankPathProven = recoveryAnchor
                    && strictNativePath(recoveryAnchor->X, recoveryAnchor->Y,
                        recoveryAnchor->Z, true, &nativePathRejection);
                if (currentTankPathProven)
                {
                    state.ValidationRouteDrudgeRecoveryAnchorPathProven = true;
                    state.ValidationRouteDrudgeRecoveryAnchorX = recoveryAnchor->X;
                    state.ValidationRouteDrudgeRecoveryAnchorY = recoveryAnchor->Y;
                    state.ValidationRouteDrudgeRecoveryAnchorZ = recoveryAnchor->Z;
                    state.LastPathRejectReason.clear();
                    state.LastRecoveryResult.clear();
                }
                else
                {
                    state.ValidationRouteDrudgeRecoveryAnchorPathProven = false;
                    state.LastPathRejectReason = nativePathRejection.empty()
                        ? "drudge_recovery_anchor_live_preflight_rejected"
                        : nativePathRejection;
                    state.LastRecoveryResult = state.LastPathRejectReason;
                    if (Cohort().ValidationAttemptFailureReason.empty())
                        Cohort().ValidationAttemptFailureReason =
                            "drudge_recovery_anchor_live_preflight_failed";
                }
            }
            holdOffense();
            char const* result = assignedTank && !currentTankPathProven
                ? "drudge_recovery_anchor_live_preflight_failed"
                : "drudge_recovery_anchor_live_preflight_wait";
            record(laneSource, result, sourceSeparation);
            target = laneSource;
            state.TargetGuid = laneSource->GetGUID();
            action = result;
            return true;
        }
        auto tankOnFrozenLane = [&](Player const* tank, uint32 slot)
        {
            if (!tank)
                return false;
            bool const tankLaneA = std::find(
                Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), slot)
                != Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
            float const tankLaneSign = tankLaneA ? -1.0f : 1.0f;
            float const projection = (tank->GetPositionX() - midpointX) * axisX
                + (tank->GetPositionY() - midpointY) * axisY;
            return tankLaneSign * projection >= laneSeparation * 0.25f;
        };
        auto tanksOnFrozenLanes = [&]()
        {
            return laneTank && otherTank && laneTank->IsAlive() && otherTank->IsAlive()
                && laneTank->GetMap() == bot->GetMap()
                && otherTank->GetMap() == bot->GetMap()
                && laneTank->GetExactDist2d(otherTank)
                    >= Cohort().Config.ValidationRouteSplitMinimumSeparationYards
                && tankOnFrozenLane(laneTank, laneTankSlot)
                && tankOnFrozenLane(otherTank, otherTankSlot);
        };
        auto boundTankSourceGeometrySafe = [&]()
        {
            if (!tanksOnFrozenLanes())
                return false;
            return laneTank->GetExactDist2d(laneSource)
                    <= Cohort().Config.ValidationRouteSplitMinimumSeparationYards
                && otherTank->GetExactDist2d(otherSource)
                    <= Cohort().Config.ValidationRouteSplitMinimumSeparationYards;
        };
        geometryState.LastChargeSequenceObserved =
            state.LastValidationRouteDrudgeChargeGenerationObserved;
        geometryState.PriorPathProofAvailable =
            state.ValidationRouteDrudgeAnchorPathProven;
        BotRaidDrudgeGeometry::Input tankStageInput = rushGeometryInput;
        tankStageInput.ExactPrepullStaged = prepullStaged;
        tankStageInput.BothCombatTankPathsProven =
            activeTankPathsProvenBeforeTick;
        tankStageInput.BothCombatTankAnchorsSafe = exactCombatTankAnchorsSafe();
        tankStageInput.ChargeQueueIdle = chargeObservation
            == Party().ValidationRouteDrudgeChargeObservations.end();
        tankStageInput.ChargeLanded = nativeChargePending;
        tankStageInput.SourcesAlive = sources[0]->IsAlive()
            && sources[1]->IsAlive();
        tankStageInput.SourcesSeparated = sourceSeparation
            >= laneSeparation;
        tankStageInput.SourcesOnFrozenLanes = sourceOnFrozenLane(sources[0], 0)
            && sourceOnFrozenLane(sources[1], 1);
        tankStageInput.TanksOnFrozenLanes = tanksOnFrozenLanes();
        tankStageInput.BoundTankSourceGeometrySafe = boundTankSourceGeometrySafe();
        tankStageInput.NativeMeleeStopBounded = laneTank && otherTank
            && laneSource->GetMeleeRange(laneTank)
                <= Cohort().Config.ValidationRouteSplitNativeMeleeStopYards
            && otherSource->GetMeleeRange(otherTank)
                <= Cohort().Config.ValidationRouteSplitNativeMeleeStopYards;
        BotRaidDrudgeGeometry::Result const tankStage =
            BotRaidDrudgeGeometry::Advance(geometryState, tankStageInput);
        state.LastValidationRouteDrudgeChargeGenerationObserved =
            tankStage.Next.LastChargeSequenceObserved;
        state.ValidationRouteDrudgeAnchorPathProven =
            tankStage.Next.PriorPathProofAvailable;
        if (sourceCombatStarted && !prepullStaged)
        {
            holdOffense();
            record(laneSource, "drudge_prepull_combat_before_exact_roster_staged");
            target = laneSource;
            state.TargetGuid = laneSource->GetGUID();
            return true;
        }
        if (assignedTank && tankStage.NativeOwnershipAllowed
            && laneSource->GetVictim() == bot)
        {
            // Native threat ownership is already the exact frozen lane
            // assignment.  Keep it separate from the actual successful
            // taunt-cast evidence below.
            auto const ownershipInsert =
                Party().ValidationRouteDrudgeOwnershipRosterGuids.insert(
                    bot->GetGUID().GetCounter());
            if (ownershipInsert.second)
                record(laneSource, "drudge_lane_native_ownership", sourceSeparation);
        }
        if (assignedTank && tankStage.NativeOwnershipAllowed
            && laneSource->GetVictim() != bot)
        {
            BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, "tank");
            for (BotActionCandidate const& candidate :
                BotClassSpecActionProfileStore::BuildCandidates(bot, laneSource, profile))
                if (candidate.Category == BotCombatActionCategory::Taunt)
                {
                    if (candidate.RejectReason.empty())
                    {
                        BotRaidAreaAuthority::SetAllOffenseSuppressed(bot->GetGUID().GetRawValue(), false);
                        bool const taunted = TryCastCombatSpell(bot, laneSource, candidate.SpellId);
                        BotRaidAreaAuthority::SetAllOffenseSuppressed(bot->GetGUID().GetRawValue(), true);
                        if (taunted)
                        {
                            BotRaidAreaAuthority::Set(bot->GetGUID().GetRawValue(), true);
                            Party().ValidationRouteDrudgeTauntRosterGuids.insert(
                                bot->GetGUID().GetCounter());
                            record(laneSource, "drudge_lane_native_taunt", sourceSeparation, candidate.SpellId);
                            target = laneSource;
                            state.TargetGuid = laneSource->GetGUID();
                            return true;
                        }
                    }
                    else if (nativeChargePending && candidate.RejectReason == "out_of_range")
                    {
                        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.SpellId);
                        float const maxRange = spellInfo
                            ? bot->GetSpellMaxRangeForTarget(laneSource, spellInfo) : 0.0f;
                        float const distance = bot->GetExactDist2d(laneSource);
                        float const travel = distance - std::max(5.0f, maxRange - 1.0f);
                        if (maxRange > 5.0f && travel > 0.0f && distance > 0.001f)
                        {
                            float const recoveryX = bot->GetPositionX()
                                + (laneSource->GetPositionX() - bot->GetPositionX())
                                    * travel / distance;
                            float const recoveryY = bot->GetPositionY()
                                + (laneSource->GetPositionY() - bot->GetPositionY())
                                    * travel / distance;
                            float const recoveryZ = bot->GetPositionZ()
                                + (laneSource->GetPositionZ() - bot->GetPositionZ())
                                    * travel / distance;
                            float const recoveryProjection = (recoveryX - midpointX) * axisX
                                + (recoveryY - midpointY) * axisY;
                            float const tankLaneSign = laneIndex == 0 ? -1.0f : 1.0f;
                            if (tankLaneSign * recoveryProjection
                                    >= Cohort().Config.ValidationRouteSplitMinimumSeparationYards
                                        * 0.5f
                                && strictTankRecoveryPath(
                                    recoveryX, recoveryY, recoveryZ)
                                && MoveBotToPoint(state, bot, recoveryX, recoveryY, recoveryZ))
                            {
                                record(laneSource, "drudge_lane_native_taunt_approach",
                                    distance, candidate.SpellId);
                                target = laneSource;
                                state.TargetGuid = laneSource->GetGUID();
                                return true;
                            }
                        }
                    }
                }
        }
        if (nativeChargePending && exactRosterReSeparated())
        {
            markAllRosterReseparated(*chargeObservation);
            char const* result = nativeChargeTargetViolation
                ? (nativeChargeTargetRoleViolation
                    ? "drudge_native_charge_target_tank_reseparated"
                    : (nativeChargeTargetLaneViolation
                        ? "drudge_native_charge_target_lane_violation_reseparated"
                        : "drudge_native_charge_contract_violation_reseparated"))
                : "drudge_native_charge_reseparation_complete";
            record(nativeChargeSource, result, sourceSeparation,
                nativeChargeTarget ? nativeChargeTarget->GetGUID().GetCounter() : 0);
            state.LastValidationRouteDrudgeChargeGenerationHandled = chargeObservation->Sequence;
            target = laneSource;
            state.TargetGuid = laneSource ? laneSource->GetGUID() : ObjectGuid::Empty;
            return true;
        }

        if (!prepullStaged || !tankStage.TankMovementAllowed
            || !tankStage.NativeEngagementAllowed || formationRequiredMutable
            || pairTooClose || nativeChargePending || chargeAwaitingLanding)
        {
            holdOffense();
            bool moved = false;
            bool alreadySafe = assignedTank
                ? cachedAnchorSafe(state, bot) : groupPositionSafe(bot);
            bool const friendlySupportAvailable = tankStage.SupportAllowed
                && roster->second.Role == "healer";
            BotRaidDrudgeGeometry::MemberRecoveryAction const recoveryAction =
                BotRaidDrudgeGeometry::SelectMemberRecoveryAction(
                    nativeChargePending, alreadySafe, friendlySupportAvailable);

            auto tryFormationRecovery = [&]()
            {
                if (bot->IsFalling() || alreadySafe)
                    return;
                // The primary point is a contract reference, not a promise
                // that this bot's current polygon can reach it.  Select one
                // native-pathable collision-safe fallback and persist it for
                // this exact attempt/wipe/route generation.  The native spell
                // remains untouched; only member movement is recovered.
                if (selectPathableDrudgeAnchor(assignedTank))
                {
                    alreadySafe = assignedTank
                        ? cachedAnchorSafe(state, bot) : groupPositionSafe(bot);
                    if (!alreadySafe
                        && (!assignedTank || !nativeChargePending
                            || strictTankRecoveryPath(
                                state.ValidationRouteDrudgeAnchorX,
                                state.ValidationRouteDrudgeAnchorY,
                                state.ValidationRouteDrudgeAnchorZ)))
                        moved = MoveBotToPoint(state, bot,
                            state.ValidationRouteDrudgeAnchorX,
                            state.ValidationRouteDrudgeAnchorY,
                            state.ValidationRouteDrudgeAnchorZ);
                }
            };

            if (recoveryAction
                == BotRaidDrudgeGeometry::MemberRecoveryAction::RecoverFormation)
                tryFormationRecovery();

            // A body pull can begin while the tanks are still proving the
            // declared combat geometry. Preserve the hostile-offense gate,
            // but permit ordinary movement-free friendly actions. A landed
            // Rush is different: an unsafe healer must first recover the
            // sealed formation, or repeated heals can consume the complete
            // native 20-second reseparation window.
            if (recoveryAction
                    == BotRaidDrudgeGeometry::MemberRecoveryAction::PreferFriendlySupport
                && tryRouteGroupHeal(bot, laneSource, false))
            {
                record(laneSource, "drudge_staging_support", sourceSeparation);
                target = laneSource;
                state.TargetGuid = laneSource->GetGUID();
                return true;
            }

            if (recoveryAction
                != BotRaidDrudgeGeometry::MemberRecoveryAction::RecoverFormation)
                tryFormationRecovery();
            char const* result = nativeChargePending
                ? (nativeChargeTargetViolation
                    ? (nativeChargeTargetRoleViolation
                        ? "drudge_native_charge_target_tank_reseparate"
                        : (nativeChargeTargetLaneViolation
                            ? "drudge_native_charge_target_lane_violation_reseparate"
                            : "drudge_native_charge_contract_violation_reseparate"))
                    : "drudge_native_charge_lane_reseparate")
                : (!prepullStaged
                    ? "drudge_prepull_member_stage" :
                    (assignedTank ? "drudge_tank_lane_position" :
                    (alreadySafe ? "drudge_group_lane_position_already_safe" : "drudge_group_lane_position")));
            record(laneSource, result, sourceSeparation,
                nativeChargeTarget ? nativeChargeTarget->GetGUID().GetCounter() : 0);
            target = laneSource;
            state.TargetGuid = laneSource ? laneSource->GetGUID() : ObjectGuid::Empty;
            action = moved || alreadySafe ? action : "drudge_lane_native_path_rejected";
            return true;
        }

        if (nativeChargePending)
        {
            holdOffense();
            state.LastValidationRouteDrudgeChargeGenerationHandled =
                chargeObservation->Sequence;
            chargeObservation->ReseparatedRosterGuids.insert(bot->GetGUID().GetCounter());
            Party().ValidationRouteDrudgeReseparatedRosterGuids.insert(
                bot->GetGUID().GetCounter());
            record(nativeChargeSource, "drudge_native_charge_reseparation_complete",
                sourceSeparation, nativeChargeTarget->GetGUID().GetCounter());
            target = laneSource;
            state.TargetGuid = laneSource->GetGUID();
            return true;
        }

        if (roster->second.Role == "healer")
        {
            if (tryRouteGroupHeal(bot, laneSource))
                return true;
            holdOffense();
            record(laneSource, "drudge_lane_healer_hold", sourceSeparation);
            target = laneSource;
            state.TargetGuid = laneSource->GetGUID();
            return true;
        }

        auto resetHealthSyncEvidenceScope = [&]()
        {
            if (Party().ValidationRouteDrudgeHealthSyncEvidenceAttemptId != Cohort().AttemptId
                || Party().ValidationRouteDrudgeHealthSyncEvidenceWipeGeneration != Cohort().Raid.WipeGeneration
                || Party().ValidationRouteDrudgeHealthSyncEvidenceRouteGeneration != Party().ValidationRouteGeneration)
            {
                Party().ValidationRouteDrudgeHealthSyncRosterGuids.clear();
                Party().ValidationRouteDrudgeHealthSyncEvaluatedRosterGuids.clear();
                Party().ValidationRouteDrudgeHealthSyncHoldSourceSpawnId = 0;
                Party().ValidationRouteDrudgeHealthSyncHoldTankGuid = 0;
                Party().ValidationRouteDrudgeHealthSyncHoldLowerPct = 0.0f;
                Party().ValidationRouteDrudgeHealthSyncHoldPeerPct = 0.0f;
                Party().ValidationRouteDrudgeHealthSyncEvidenceAttemptId = Cohort().AttemptId;
                Party().ValidationRouteDrudgeHealthSyncEvidenceWipeGeneration = Cohort().Raid.WipeGeneration;
                Party().ValidationRouteDrudgeHealthSyncEvidenceRouteGeneration = Party().ValidationRouteGeneration;
            }
        };
        auto recordHealthSyncEvaluation = [&]()
        {
            resetHealthSyncEvidenceScope();
            Party().ValidationRouteDrudgeHealthSyncEvaluatedRosterGuids.insert(
                bot->GetGUID().GetCounter());
        };
        auto recordHealthSyncHold = [&]()
        {
            recordHealthSyncEvaluation();
            Party().ValidationRouteDrudgeHealthSyncRosterGuids.insert(
                bot->GetGUID().GetCounter());
            Party().ValidationRouteDrudgeHealthSyncHoldSourceSpawnId =
                laneSource == sources[0] ? 250140 : 250141;
            Party().ValidationRouteDrudgeHealthSyncHoldTankGuid = laneTank
                ? laneTank->GetGUID().GetCounter() : 0;
            Party().ValidationRouteDrudgeHealthSyncHoldLowerPct = UnitHealthPct(laneSource);
            Party().ValidationRouteDrudgeHealthSyncHoldPeerPct = UnitHealthPct(otherSource);
            Party().ValidationRouteDrudgeHealthSyncHoldLowerAlive = laneSource->IsAlive();
            Party().ValidationRouteDrudgeHealthSyncHoldPeerAlive = otherSource->IsAlive();
        };

        if (!otherSource->IsAlive())
        {
            // The native death spell can apply Vengeful Rage before the next
            // bot decision.  Record that this guard was evaluated before any
            // post-death offense; only record a wait edge when the aura is
            // genuinely absent.
            if (Party().ValidationRouteDrudgeDeathEvidenceSequence != 0
                && Party().ValidationRouteDrudgeRageWaitEvidenceSequence == 0
                && laneSource->GetGUID().GetCounter()
                    == Party().ValidationRouteDrudgeSurvivorSourceGuid)
                Party().ValidationRouteDrudgeRageWaitEvidenceSequence =
                    ++Cohort().Raid.EvidenceSequence;
            if (!laneSource->HasAura(Cohort().Config.ValidationRouteVengefulRageSpellId))
            {
                holdOffense();
                record(laneSource, "drudge_wait_native_vengeful_rage", sourceSeparation);
                target = laneSource;
                state.TargetGuid = laneSource->GetGUID();
                return true;
            }
            if (Party().ValidationRouteDrudgeDeathEvidenceSequence != 0
                && Party().ValidationRouteDrudgeRageWaitEvidenceSequence != 0
                && Party().ValidationRouteDrudgeRageAuraEvidenceSequence == 0
                && laneSource->GetGUID().GetCounter()
                    == Party().ValidationRouteDrudgeSurvivorSourceGuid)
            {
                Party().ValidationRouteDrudgeRageAuraEvidenceSequence =
                    ++Cohort().Raid.EvidenceSequence;
                record(laneSource, "drudge_native_vengeful_rage_observed", sourceSeparation);
            }
        }
        // Formation and ownership are prerequisites for the trained single
        // target profiles.  A stale native threat assignment must not be
        // hidden by a DPS cast, and a partial roster must never be certified as
        // a clean lane generation.
        bool const laneOwnershipSafe = laneSource->IsAlive()
            && laneSource->GetVictim() == laneTank
            && (!otherSource->IsAlive() || otherSource->GetVictim() == otherTank);
        if (!laneOwnershipSafe)
        {
            holdOffense();
            record(laneSource, "drudge_lane_wait_lane_ownership", sourceSeparation);
            target = laneSource;
            state.TargetGuid = laneSource ? laneSource->GetGUID() : ObjectGuid::Empty;
            return true;
        }
        auto tryPreFirstRushThreatSeed = [&]() -> bool
        {
            using namespace BotRaidDrudgeThreatSeed;
            Scope const seedScope = {
                Cohort().AttemptId,
                Cohort().Raid.WipeGeneration,
                Party().ValidationRouteGeneration
            };
            auto loadSeedState = [&]()
            {
                State seedState;
                seedState.Identity = {
                    Party().ValidationRouteDrudgeThreatSeedAttemptId,
                    Party().ValidationRouteDrudgeThreatSeedWipeGeneration,
                    Party().ValidationRouteDrudgeThreatSeedRouteGeneration
                };
                seedState.Closed = Party().ValidationRouteDrudgeThreatSeedClosed;
                seedState.Complete = Party().ValidationRouteDrudgeThreatSeedComplete;
                seedState.Failure = Party().ValidationRouteDrudgeThreatSeedFailure;
                for (ValidationRouteDrudgeThreatSeedEvidence const& evidence :
                    Party().ValidationRouteDrudgeThreatSeedEvidenceRows)
                    if (evidence.ActionSucceeded && evidence.ProfileActionValid
                        && evidence.AttemptId == seedScope.AttemptId
                        && evidence.WipeGeneration == seedScope.WipeGeneration
                        && evidence.RouteGeneration == seedScope.RouteGeneration
                        && evidence.SourceLane < seedState.SeededLanes.size())
                        seedState.SeededLanes[evidence.SourceLane] = true;
                return seedState;
            };
            auto applySeedResult = [&](Result const& result)
            {
                if (result.ScopeReset)
                {
                    Party().ValidationRouteDrudgeThreatSeedRosterGuids.clear();
                    Party().ValidationRouteDrudgeThreatSeedEvidenceRows.clear();
                }
                Party().ValidationRouteDrudgeThreatSeedAttemptId = result.Next.Identity.AttemptId;
                Party().ValidationRouteDrudgeThreatSeedWipeGeneration = result.Next.Identity.WipeGeneration;
                Party().ValidationRouteDrudgeThreatSeedRouteGeneration = result.Next.Identity.RouteGeneration;
                Party().ValidationRouteDrudgeThreatSeedClosed = result.Next.Closed;
                Party().ValidationRouteDrudgeThreatSeedComplete = result.Next.Complete;
                Party().ValidationRouteDrudgeThreatSeedFailure = result.Next.Failure;
            };

            bool const currentScopeHasChargeObservation = std::any_of(
                Party().ValidationRouteDrudgeChargeObservations.begin(),
                Party().ValidationRouteDrudgeChargeObservations.end(),
                [this](ValidationRouteDrudgeChargeObservation const& observation)
                {
                    return observation.AttemptId == Cohort().AttemptId
                        && observation.WipeGeneration == Cohort().Raid.WipeGeneration
                        && observation.RouteGeneration == Party().ValidationRouteGeneration;
                });
            Input seedInput;
            seedInput.Type = Event::DecisionTick;
            seedInput.Identity = seedScope;
            seedInput.SourceLane = laneIndex;
            seedInput.PrepullStaged = prepullStaged;
            seedInput.SourcesAlive = sources[0]->IsAlive() && sources[1]->IsAlive();
            seedInput.OwnershipSafe = laneOwnershipSafe;
            seedInput.SeparationSafe = sourceSeparation
                >= laneSeparation;
            seedInput.FrozenLanesSafe = sourceOnFrozenLane(sources[0], 0)
                && sourceOnFrozenLane(sources[1], 1);
            seedInput.ChargeObserved = currentScopeHasChargeObservation;
            // The first transition evaluates only the native window. Candidate
            // and authority facts are filled below before any action executes.
            seedInput.CandidateAvailable = true;
            seedInput.AuthoritySafe = true;
            Result seedTransition = Advance(loadSeedState(), seedInput);
            applySeedResult(seedTransition);
            if (seedTransition.NextDecision == Decision::Continue
                || seedTransition.NextDecision == Decision::Complete)
                return false;
            if (seedTransition.NextDecision == Decision::HoldWindow)
            {
                holdOffense();
                record(laneSource, "drudge_pre_first_rush_seed_window_wait",
                    sourceSeparation, laneIndex);
                target = laneSource;
                state.TargetGuid = laneSource->GetGUID();
                return true;
            }
            if (seedTransition.NextDecision == Decision::HoldSeededLane)
            {
                // A successful cross-lane action is one seed for this source;
                // do not let every member decision in the same lane submit a
                // second action before the native selector observes it.
                holdOffense();
                record(laneSource, "drudge_pre_first_rush_seed_source_already_seeded",
                    sourceSeparation, laneIndex);
                target = laneSource;
                state.TargetGuid = laneSource->GetGUID();
                return true;
            }
            if (seedTransition.NextDecision == Decision::HoldClosed)
            {
                holdOffense();
                record(laneSource, "drudge_pre_first_rush_seed_closed", sourceSeparation,
                    laneIndex);
                target = laneSource;
                state.TargetGuid = laneSource->GetGUID();
                return true;
            }

            Player* selectedMember = nullptr;
            WorldBotState* selectedState = nullptr;
            ResolvedCombatAction selectedAction;
            bool selectedPositionSafe = false;
            bool selectedLineOfSight = false;
            bool selectedInRange = false;
            uint32 selectedSlot = std::numeric_limits<uint32>::max();
            uint32 const selectedLaneIndex = 1 - laneIndex;
            uint32 const requiredSeedSlot =
                Cohort().Config.ValidationRouteSplitSeedRosterSlots[laneIndex];
            for (WorldBotState& candidateState : Party().Bots)
            {
                Player* candidate = GetLoadedBot(candidateState);
                if (!candidate || !candidate->IsInWorld() || !candidate->IsAlive()
                    || candidate->GetMap() != bot->GetMap())
                    continue;
                auto candidateRoster = Cohort().Raid.RosterByGuid.find(
                    candidate->GetGUID().GetCounter());
                if (candidateRoster == Cohort().Raid.RosterByGuid.end()
                    || !candidateRoster->second.Active || !candidateRoster->second.LeaseOwned
                    || candidateRoster->second.Role != "dps")
                    continue;
                uint32 const candidateSlot = candidateRoster->second.SlotIndex + 1;
                bool const candidateLaneA = std::find(
                    Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                    Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), candidateSlot)
                    != Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
                uint32 const candidateLaneIndex = candidateLaneA ? 0 : 1;
                if (candidateSlot != requiredSeedSlot
                    || candidateLaneIndex != selectedLaneIndex
                    || Party().ValidationRouteDrudgeThreatSeedRosterGuids.count(
                        candidate->GetGUID().GetCounter()))
                    continue;
                if (!groupPositionSafe(candidate))
                    continue;

                ResolvedCombatAction candidateAction = ResolveProfileCombatAction(
                    candidate, laneSource, 1, false, 0, false, false, true, false, true);
                bool const profileValid = candidateAction.Valid
                    && candidateAction.Type == "cast"
                    && candidateAction.SpellId
                    && candidateAction.TargetGuid == laneSource->GetGUID()
                    && candidateAction.MovementDirective == "ranged"
                    && candidateAction.MaxRange > 5.0f;
                bool const lineOfSight = candidate->IsWithinLOSInMap(laneSource);
                float const distance = candidate->GetExactDist(laneSource);
                bool const inRange = profileValid
                    && lineOfSight
                    && distance <= Cohort().Config.ValidationRouteSplitSeedMaxRangeYards
                    && (!candidateAction.MinRange || distance >= candidateAction.MinRange)
                    && (!candidateAction.MaxRange || distance <= candidateAction.MaxRange);
                if (!profileValid || !lineOfSight || !inRange)
                    continue;

                if (candidateSlot < selectedSlot)
                {
                    selectedMember = candidate;
                    selectedState = &candidateState;
                    selectedAction = candidateAction;
                    selectedPositionSafe = true;
                    selectedLineOfSight = lineOfSight;
                    selectedInRange = inRange;
                    selectedSlot = candidateSlot;
                }
            }

            if (!selectedMember || !selectedState)
            {
                // Profile availability is transient (GCD, cooldown, range,
                // LOS, setup). Keep the native pre-Rush window open and retry
                // on later decisions. Only the Rush clock edge or a genuine
                // authority/scope violation may make the seed permanently
                // fail.
                seedInput.CandidateAvailable = false;
                seedTransition = Advance(seedTransition.Next, seedInput);
                applySeedResult(seedTransition);
                holdOffense();
                record(laneSource, "drudge_pre_first_rush_seed_profile_unavailable",
                    sourceSeparation, laneIndex);
                target = laneSource;
                state.TargetGuid = laneSource->GetGUID();
                return true;
            }

            // Reconstruct the entire immutable roster before changing shared
            // authority. PrepullStaged is sticky for the scope, so a member
            // disappearing after staging must hold rather than letting the
            // remaining nine certify an action.
            std::set<uint32> authorityRosterGuids;
            bool exactAuthorityRoster = Party().Bots.size() == Cohort().Raid.RosterByGuid.size()
                && Party().Bots.size() == Cohort().Config.TargetPopulation;
            for (WorldBotState const& memberState : Party().Bots)
            {
                Player* member = GetLoadedBot(memberState);
                if (!member || !member->IsInWorld() || !member->IsAlive()
                    || member->GetMap() != bot->GetMap())
                {
                    exactAuthorityRoster = false;
                    continue;
                }
                uint32 const memberGuid = member->GetGUID().GetCounter();
                auto const memberRoster = Cohort().Raid.RosterByGuid.find(memberGuid);
                if (memberRoster == Cohort().Raid.RosterByGuid.end()
                    || !memberRoster->second.Active || !memberRoster->second.LeaseOwned
                    || !authorityRosterGuids.insert(memberGuid).second)
                    exactAuthorityRoster = false;
            }
            if (authorityRosterGuids.size() != Cohort().Raid.RosterByGuid.size())
                exactAuthorityRoster = false;
            if (!exactAuthorityRoster)
            {
                seedInput.SourcesAlive = false;
                seedTransition = Advance(seedTransition.Next, seedInput);
                applySeedResult(seedTransition);
                holdOffense();
                record(laneSource, "drudge_pre_first_rush_seed_roster_wait",
                    sourceSeparation, uint32(authorityRosterGuids.size()));
                target = laneSource;
                state.TargetGuid = laneSource->GetGUID();
                return true;
            }

            // Install the exact shared authority synchronously. Decisions are
            // asynchronous across bots, so waiting for each member's next
            // holdOffense() tick creates a false failure race.
            for (WorldBotState const& memberState : Party().Bots)
                if (Player* member = GetLoadedBot(memberState))
                {
                    uint64 const memberGuid = member->GetGUID().GetRawValue();
                    BotRaidAreaAuthority::SetAllOffenseSuppressed(memberGuid, true);
                    BotRaidAreaAuthority::Set(memberGuid, true);
                }

            uint64 const selectedOwnerGuid = selectedMember->GetGUID().GetRawValue();
            bool otherOffenseSuppressed = true;
            for (WorldBotState const& memberState : Party().Bots)
                if (Player* member = GetLoadedBot(memberState))
                    if (member != selectedMember
                        && !BotRaidAreaAuthority::IsAllOffenseSuppressed(
                            member->GetGUID().GetRawValue()))
                        otherOffenseSuppressed = false;
            if (!otherOffenseSuppressed)
            {
                seedInput.CandidateAvailable = true;
                seedInput.AuthoritySafe = false;
                seedTransition = Advance(seedTransition.Next, seedInput);
                applySeedResult(seedTransition);
                holdOffense();
                record(laneSource, "drudge_pre_first_rush_seed_offense_scope_invalid",
                    sourceSeparation, laneIndex);
                target = laneSource;
                state.TargetGuid = laneSource->GetGUID();
                return true;
            }

            // Existing route authority keeps every other member from
            // starting offense.  Release exactly the selected member for one
            // ordinary profile submission; no cast or attack is interrupted.
            BotRaidAreaAuthority::SetAllOffenseSuppressed(selectedOwnerGuid, false);
            BotRaidAreaAuthority::Set(selectedOwnerGuid, true);
            BotActionResult const profileResult = ExecuteProfileCombatAction(
                selectedState, selectedMember, laneSource, &selectedAction,
                1, false, 0, false, false, true, false, true);
            bool const actionSucceeded = profileResult == BotActionResult::Ok
                && selectedAction.Valid && selectedAction.Type == "cast"
                && selectedAction.SpellId
                && selectedAction.TargetGuid == laneSource->GetGUID();
            bool const selectedOffenseUnsuppressed =
                !BotRaidAreaAuthority::IsAllOffenseSuppressed(selectedOwnerGuid);
            // Restore suppression immediately after submission.  This is
            // deliberately authority-only: support casts and active heals are
            // not interrupted or force-stopped.
            BotRaidAreaAuthority::SetAllOffenseSuppressed(selectedOwnerGuid, true);
            BotRaidAreaAuthority::Set(selectedOwnerGuid, true);

            seedInput.Type = Event::ActionResult;
            seedInput.CandidateAvailable = true;
            seedInput.AuthoritySafe = otherOffenseSuppressed;
            seedInput.ActionSucceeded = actionSucceeded;
            seedTransition = Advance(seedTransition.Next, seedInput);
            applySeedResult(seedTransition);

            ValidationRouteDrudgeThreatSeedEvidence seedEvidence;
            seedEvidence.Sequence = ++Cohort().Raid.EvidenceSequence;
            seedEvidence.AttemptId = Cohort().AttemptId;
            seedEvidence.WipeGeneration = Cohort().Raid.WipeGeneration;
            seedEvidence.RouteGeneration = Party().ValidationRouteGeneration;
            seedEvidence.ObservedAtMs = NowMs();
            seedEvidence.MemberGuid = selectedMember->GetGUID().GetCounter();
            seedEvidence.MemberSlot = Cohort().Raid.RosterByGuid[
                selectedMember->GetGUID().GetCounter()].SlotIndex + 1;
            seedEvidence.MemberLane = selectedLaneIndex;
            seedEvidence.SourceSpawnId = laneSource == sources[0] ? 250140 : 250141;
            seedEvidence.SourceGuid = laneSource->GetGUID().GetCounter();
            seedEvidence.SourceLane = laneIndex;
            seedEvidence.SpellId = selectedAction.SpellId;
            seedEvidence.SelectedDistance = selectedMember->GetExactDist(laneSource);
            seedEvidence.MinRange = selectedAction.MinRange;
            seedEvidence.MaxRange = selectedAction.MaxRange;
            seedEvidence.PositionSafe = selectedPositionSafe;
            seedEvidence.LineOfSight = selectedLineOfSight;
            seedEvidence.InRange = selectedInRange;
            seedEvidence.ProfileActionValid = selectedAction.Valid;
            seedEvidence.ActionSucceeded = actionSucceeded;
            seedEvidence.SelectedOffenseUnsuppressed = selectedOffenseUnsuppressed;
            seedEvidence.OtherOffenseSuppressed = otherOffenseSuppressed;
            seedEvidence.ActionDebugName = selectedAction.DebugName;
            seedEvidence.ActionResult = ToString(profileResult);
            auto existingEvidence = std::find_if(
                Party().ValidationRouteDrudgeThreatSeedEvidenceRows.begin(),
                Party().ValidationRouteDrudgeThreatSeedEvidenceRows.end(),
                [&seedEvidence](ValidationRouteDrudgeThreatSeedEvidence const& existing)
                {
                    return existing.MemberGuid == seedEvidence.MemberGuid
                        && existing.SourceSpawnId == seedEvidence.SourceSpawnId;
                });
            if (existingEvidence == Party().ValidationRouteDrudgeThreatSeedEvidenceRows.end()
                || actionSucceeded)
                Party().ValidationRouteDrudgeThreatSeedEvidenceRows.push_back(seedEvidence);

            if (actionSucceeded)
            {
                Party().ValidationRouteDrudgeThreatSeedRosterGuids.insert(
                    selectedMember->GetGUID().GetCounter());
                selectedState->TargetGuid = sources[selectedLaneIndex]->GetGUID();
                record(laneSource, "drudge_pre_first_rush_threat_seed", sourceSeparation,
                    selectedAction.SpellId);
            }
            else
            {
                record(laneSource, "drudge_pre_first_rush_seed_profile_hold",
                    sourceSeparation, selectedAction.SpellId);
            }
            target = laneSource;
            state.TargetGuid = laneSource->GetGUID();
            action = actionSucceeded
                ? "drudge_pre_first_rush_seed_return_lane_focus"
                : "drudge_pre_first_rush_seed_profile_hold";
            return true;
        };

        if (sources[0]->IsAlive() && sources[1]->IsAlive()
            && !Party().ValidationRouteDrudgeThreatSeedComplete)
            if (tryPreFirstRushThreatSeed())
                return true;

        using NativeRushSourceReadiness = BotRaidDrudgeNativeRush::SourceResult;
        auto rosterMemberForSlot = [this](uint32 oneBasedSlot) -> Player*
        {
            for (auto const& [guid, rosterEntry] : Cohort().Raid.RosterByGuid)
                if (rosterEntry.Active && rosterEntry.LeaseOwned
                    && rosterEntry.SlotIndex + 1 == oneBasedSlot)
                    for (WorldBotState const& memberState : Party().Bots)
                        if (memberState.Guid.GetCounter() == guid)
                            return GetLoadedBot(memberState);
            return nullptr;
        };
        auto nativeRushSourceReadiness = [&](uint32 sourceIndex)
        {
            BotRaidDrudgeNativeRush::SourceInput input;
            if (sourceIndex >= sources.size()
                || Cohort().Config.ValidationRouteSplitLaneTankSlots.size() != 2
                || Cohort().Config.ValidationRouteSplitSeedRosterSlots.size() != 2)
                return BotRaidDrudgeNativeRush::Evaluate(input);
            Creature* source = sources[sourceIndex];
            Player* assignedSourceTank = rosterMemberForSlot(
                Cohort().Config.ValidationRouteSplitLaneTankSlots[sourceIndex]);
            Player* intendedSeed = rosterMemberForSlot(
                Cohort().Config.ValidationRouteSplitSeedRosterSlots[sourceIndex]);
            if (!source || !source->IsAlive() || !assignedSourceTank
                || !assignedSourceTank->IsAlive() || !intendedSeed
                || !intendedSeed->IsAlive() || source->GetMap() != assignedSourceTank->GetMap()
                || source->GetMap() != intendedSeed->GetMap())
                return BotRaidDrudgeNativeRush::Evaluate(input);

            input.ExactTankVictim = source->GetVictim() == assignedSourceTank;
            input.TankThreat = source->GetThreatManager().GetThreat(
                assignedSourceTank, true);
            Unit* farthest = nullptr;
            float farthestDistance = -1.0f;
            float secondFarthestDistance = -1.0f;
            for (ThreatReference const* reference :
                source->GetThreatManager().GetUnsortedThreatList())
            {
                Unit* candidate = reference ? reference->GetVictim() : nullptr;
                if (!candidate)
                    continue;
                if (candidate != assignedSourceTank && reference->IsAvailable()
                    && candidate->IsAlive() && source->IsInMap(candidate)
                    && source->IsInPhase(candidate))
                    input.HighestOtherThreat = std::max(
                        input.HighestOtherThreat, reference->GetThreat());
                if (!candidate->ToPlayer() || !reference->IsAvailable()
                    || !source->IsWithinLOSInMap(candidate)
                    || !source->IsWithinCombatRange(
                        candidate, Cohort().Config.ValidationRouteChargeRangeYards))
                    continue;
                float const distance = source->GetExactDist(candidate);
                if (candidate == intendedSeed)
                {
                    input.IntendedSeedPresent = true;
                    input.SeedDistance = distance;
                }
                if (distance > farthestDistance)
                {
                    secondFarthestDistance = farthestDistance;
                    farthestDistance = distance;
                    farthest = candidate;
                }
                else if (distance > secondFarthestDistance)
                    secondFarthestDistance = distance;
            }
            input.FarthestIsIntendedSeed = farthest == intendedSeed;
            input.SecondFarthestDistance = std::max(0.0f, secondFarthestDistance);
            input.FarthestGuid = farthest ? farthest->GetGUID().GetCounter() : 0;
            input.ThreatHeadroomMultiplier =
                Cohort().Config.ValidationRouteSplitTankThreatHeadroomMultiplier;
            input.FarthestDistanceMargin = secondFarthestDistance < 0.0f
                ? 0.0f
                : 2.0f * Cohort().Config.ValidationRouteSplitArrivalToleranceYards;
            return BotRaidDrudgeNativeRush::Evaluate(input);
        };
        std::array<NativeRushSourceReadiness, 2> const nativeRushReadiness = {
            nativeRushSourceReadiness(0), nativeRushSourceReadiness(1)
        };
        bool const currentScopeHasNativeRush = std::any_of(
            Party().ValidationRouteDrudgeChargeObservations.begin(),
            Party().ValidationRouteDrudgeChargeObservations.end(),
            [this](ValidationRouteDrudgeChargeObservation const& observation)
            {
                return observation.AttemptId == Cohort().AttemptId
                    && observation.WipeGeneration == Cohort().Raid.WipeGeneration
                    && observation.RouteGeneration == Party().ValidationRouteGeneration;
            });
        bool const nativeRushAuthorityReady = std::all_of(
            nativeRushReadiness.begin(), nativeRushReadiness.end(),
            [](NativeRushSourceReadiness const& readiness)
            {
                return readiness.Ready;
            });
        auto tryBuildNativeTankThreat = [&]()
        {
            if (!assignedTank || !laneSource->IsAlive()
                || laneSource->GetVictim() != bot
                || !BotRaidDrudgeNativeRush::ShouldBuildTankThreat(
                    currentScopeHasNativeRush, nativeRushReadiness[laneIndex]))
                return false;
            BotRaidAreaAuthority::SetAllOffenseSuppressed(
                bot->GetGUID().GetRawValue(), false);
            BotRaidAreaAuthority::Set(bot->GetGUID().GetRawValue(), true);
            ResolvedCombatAction tankAction = ResolveProfileCombatAction(
                bot, laneSource, 1, false, 0, false, false, true, false, true);
            BotActionResult const tankResult = ExecuteProfileCombatAction(
                &state, bot, laneSource, &tankAction,
                1, false, 0, false, false, true, false, true);
            bool const succeeded = tankResult == BotActionResult::Ok
                && tankAction.Valid && tankAction.Type == "cast"
                && tankAction.SpellId && tankAction.TargetGuid == laneSource->GetGUID();
            BotRaidAreaAuthority::SetAllOffenseSuppressed(
                bot->GetGUID().GetRawValue(), true);
            BotRaidAreaAuthority::Set(bot->GetGUID().GetRawValue(), true);
            if (succeeded)
                record(laneSource, currentScopeHasNativeRush
                    ? "drudge_native_tank_threat_build"
                    : "drudge_native_tank_threat_sustain",
                    nativeRushReadiness[laneIndex].TankThreat, tankAction.SpellId);
            return succeeded;
        };

        // The two seed casts establish native threat references; they are not
        // permission to start the full damage rotation. Keep every non-tank
        // hostile action suppressed until both assigned tanks own their source
        // with conservative native threat headroom and the real live threat
        // list names the configured seed as the unique farthest eligible
        // player. This mirrors SMART_TARGET_FARTHEST without rewriting its
        // target or manufacturing threat. The same gate remains active after
        // reseparation so ordinary maximum-DPS profiles cannot pull a source
        // away from its tank or change the next Rush target.
        if (sources[0]->IsAlive() && sources[1]->IsAlive()
            && Party().ValidationRouteDrudgeThreatSeedComplete
            && (!currentScopeHasNativeRush || !nativeRushAuthorityReady))
        {
            holdOffense();
            if (tryBuildNativeTankThreat())
            {
                target = laneSource;
                state.TargetGuid = laneSource->GetGUID();
                return true;
            }
            char const* result = nativeRushAuthorityReady
                ? "drudge_pre_first_rush_ready_hold"
                : (!nativeRushReadiness[laneIndex].ExactTankVictim
                    ? "drudge_native_tank_ownership_wait"
                    : (!nativeRushReadiness[laneIndex].TankThreatSecure
                        ? "drudge_native_tank_threat_wait"
                        : "drudge_native_farthest_seed_wait"));
            record(laneSource, result,
                nativeRushReadiness[laneIndex].SeedDistance,
                nativeRushReadiness[laneIndex].FarthestGuid);
            target = laneSource;
            state.TargetGuid = laneSource->GetGUID();
            return true;
        }

        // The two native threat seeds must be submitted after both sources
        // have exact tank ownership but before the first 20-second Rush.  Do
        // not make those ordinary, cross-lane profile casts wait for the
        // post-pull/reseparation geometry: live evidence showed that doing so
        // lets the first native Rush fire with only tanks/healers in its
        // threat list.  All regular DPS and kill synchronization still remain
        // fail-closed behind the complete exact-roster geometry below.
        if (sources[0]->IsAlive() && sources[1]->IsAlive() && !exactRosterReSeparated())
        {
            holdOffense();
            record(laneSource, "drudge_lane_profile_hold_contract_unsafe", sourceSeparation);
            target = laneSource;
            state.TargetGuid = laneSource->GetGUID();
            return true;
        }

        if (sources[0]->IsAlive() && sources[1]->IsAlive() && assignedTank)
            recordHealthSyncEvaluation();

        if (sources[0]->IsAlive() && sources[1]->IsAlive()
            && UnitHealthPct(laneSource) < UnitHealthPct(otherSource))
        {
            holdOffense();
            if (assignedTank)
                recordHealthSyncHold();
            record(laneSource, assignedTank
                ? "drudge_tank_health_sync_hold" : "drudge_kill_sync_hold_lower_health_lane",
                sourceSeparation);
            target = laneSource;
            state.TargetGuid = laneSource->GetGUID();
            return true;
        }

        if (sources[0]->IsAlive() && sources[1]->IsAlive()
            && roster->second.Role == "dps")
        {
            Player* intendedSeed = rosterMemberForSlot(
                Cohort().Config.ValidationRouteSplitSeedRosterSlots[laneIndex]);
            float const prospectiveDistance = laneSource->GetExactDist(bot);
            float const intendedSeedDistance = intendedSeed
                ? laneSource->GetExactDist(intendedSeed) : 0.0f;
            if (!intendedSeed || intendedSeed->GetMap() != laneSource->GetMap()
                || intendedSeedDistance < prospectiveDistance
                    + 2.0f * Cohort().Config.ValidationRouteSplitArrivalToleranceYards)
            {
                holdOffense();
                record(laneSource, "drudge_native_farthest_profile_hold",
                    intendedSeedDistance, bot->GetGUID().GetCounter());
                target = laneSource;
                state.TargetGuid = laneSource->GetGUID();
                return true;
            }
        }

        if (bot->GetVictim() && bot->GetVictim() != laneSource)
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Threat,
                BotActionArbitration::Priority::ThreatControl,
                "split_lane_target_switch");
        if (Pet* pet = bot->GetPet(); pet && pet->GetVictim() && pet->GetVictim() != laneSource)
            pet->AttackStop();
        for (Unit* controlled : bot->m_Controlled)
            if (controlled && controlled->GetVictim() && controlled->GetVictim() != laneSource)
                controlled->AttackStop();
        BotRaidAreaAuthority::SetAllOffenseSuppressed(bot->GetGUID().GetRawValue(), false);
        BotRaidAreaAuthority::Set(bot->GetGUID().GetRawValue(), true);
        ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, laneSource,
            1, false, 0, false, false, true, false, true);
        bool profileActionHostileValid = false;
        BotActionResult result = ExecuteProfileCombatAction(&state, bot, laneSource,
            &profileAction, 1, false, 0, false, false, true, false, true);
        profileActionHostileValid = profileAction.Valid
            && profileAction.Type == "cast" && profileAction.SpellId
            && profileAction.TargetGuid == laneSource->GetGUID();
        bool const profileActionSucceeded = profileActionHostileValid
            && result == BotActionResult::Ok;
        if (profileActionSucceeded)
            Party().ValidationRouteDrudgeProfileActionRosterGuids.insert(
                bot->GetGUID().GetCounter());
        record(laneSource, profileActionSucceeded
            ? "drudge_lane_single_target_action" : "drudge_lane_single_target_hold",
            sourceSeparation, profileAction.SpellId);
        target = laneSource;
        state.TargetGuid = laneSource->GetGUID();
        state.WasInCombat = laneSource->IsInCombat();
        return true;
    };
    auto tryValidationRoutePatrolPull = [&]() -> bool
    {
        return TryValidationRoutePatrolPull(state, bot, power, stage, activity,
            situation, action, target, tryRouteGroupHeal,
            currentValidationRouteTargetSpawnId, isValidationCohortCombatLinked,
            enrollValidationRoutePackMember);
    };
    auto tryValidationRouteAdds = [this, &state, bot, &power, stage, activity,
        &situation, &action, &target, &routeEngageRange, &tryRouteGroupHeal,
        &canonicalRouteDistance, &routeArrivalRadius]() -> bool
    {
        if (Cohort().Config.ValidationRouteKind != "boss"
            || Cohort().Config.ValidationRouteMechanicProfile.find("adds") == std::string::npos
            || Cohort().Config.ValidationRouteAddTargetEntries.empty())
            return false;

        // Declared add bosses can assign a full spawn wave to the healer before
        // the tank's next decision.  Establish pickup positioning while the
        // group is healthy instead of waiting for healing threat to exist, then
        // let the ordinary reactive stack logic handle any wave already active.
        // Exact hazard movement runs before this add handler and remains the
        // higher movement authority.
        if (std::string(GetDungeonRole(bot)) == "healer"
            && !Party().ValidationRouteBossProgressTargetGuid.IsEmpty())
        {
            Unit* routeBoss = ObjectAccessor::GetUnit(
                *bot, Party().ValidationRouteBossProgressTargetGuid);
            Player* routeTank = nullptr;
            for (WorldBotState const& cohortState : Party().Bots)
            {
                Player* member = GetLoadedBot(cohortState);
                if (member && member->IsAlive() && member->GetMap() == bot->GetMap()
                    && std::string(GetDungeonRole(member)) == "tank")
                {
                    routeTank = member;
                    break;
                }
            }

            if (routeBoss && routeBoss->IsAlive() && routeBoss->IsInCombat()
                && routeTank && routeTank->IsInCombat()
                && bot->GetExactDist2d(routeTank) > 5.0f
                && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
            {
                // Rerun122 proved the native attacker container can lag the
                // explicit listed-victim view during an Azil activation: the
                // authoritative trace observed nineteen followers targeting
                // the healer while this early branch kept classifying the
                // pickup as non-urgent and preempted the later Fade resolver.
                // Reconstruct the same bounded 45-yard listed-add view here so
                // preposition and threat-drop decisions agree with the add
                // resolver and identity-scoped retention evidence.
                size_t explicitListedHealerAttackers = 0;
                std::vector<WorldObject*> pickupObjects;
                Trinity::AllWorldObjectsInRange pickupCheck(bot, 45.0f);
                Trinity::WorldObjectListSearcher<
                    Trinity::AllWorldObjectsInRange> pickupSearcher(
                        bot, pickupObjects, pickupCheck);
                Cell::VisitAllObjects(bot, pickupSearcher, 45.0f);
                for (WorldObject* object : pickupObjects)
                {
                    Creature* creature = object ? object->ToCreature() : nullptr;
                    if (!creature || !creature->IsAlive() || !creature->GetHealth()
                        || creature->GetMap() != bot->GetMap()
                        || creature->GetVictim() != bot
                        || !bot->IsValidAttackTarget(creature)
                        || !bot->IsWithinLOSInMap(creature)
                        || std::find(
                            Cohort().Config.ValidationRouteAddTargetEntries.begin(),
                            Cohort().Config.ValidationRouteAddTargetEntries.end(),
                            creature->GetEntry())
                            == Cohort().Config.ValidationRouteAddTargetEntries.end())
                        continue;
                    ++explicitListedHealerAttackers;
                }
                size_t observedHealerAttackers = std::max(
                    bot->getAttackers().size(), explicitListedHealerAttackers);
                // Rerun71 showed the healer repeatedly selecting ordinary
                // group heals while 15+ followers retained it and the Feral
                // crossed the platform. Preserve emergency healing, but when
                // both healer and tank have safe health, begin the existing
                // bounded stack movement before another heal can keep the
                // remote swarm split from the tank.
                bool urgentPickupStack = observedHealerAttackers >= 3
                    && UnitHealthPct(bot) > 0.45f
                    && UnitHealthPct(routeTank) > 0.40f;
                // Rerun115 showed this early preposition branch returning for
                // seven seconds while 9--20 Azil followers targeted the
                // healer. It precedes the general boss-wave Fade resolver, so
                // submit the same ready native threat drop before movement
                // when the urgent exact-attacker gate is already satisfied.
                if (urgentPickupStack && bot->HasSpell(586)
                    && !bot->HasAura(586))
                {
                    std::string fadeFailureReason;
                    if (TryCastFriendlySpell(
                            bot, bot, 586, &fadeFailureReason))
                    {
                        std::string raw = BuildRawJson(bot, routeBoss);
                        std::string semantic = BuildSemanticJson(
                            bot, routeBoss, "dungeon_boss",
                            &power, stage, activity);
                        RecordEvent(state, bot, "boss_adds", bot,
                            "fade_before_urgent_add_pickup_preposition",
                            raw.c_str(), semantic.c_str(),
                            float(observedHealerAttackers),
                            Cohort().Config.ValidationRouteTargetEntry, 586);
                        state.TargetGuid = routeBoss->GetGUID();
                        target = routeBoss;
                        situation = "dungeon_boss";
                        action = "fade_before_urgent_add_pickup_preposition";
                        return true;
                    }
                    // The first rerun122 attempt occurred one second after a
                    // legal instant heal. Keep movement bounded and retry only
                    // that GCD-blocked urgent Fade at the established lower
                    // decision cadence; native cooldown failures do not pin
                    // healer movement or healing.
                    if (fadeFailureReason == "global_cooldown")
                        state.DecisionTimer = std::min<uint32>(
                            state.DecisionTimer, 500);
                }
                if (!urgentPickupStack && tryRouteGroupHeal(bot, routeBoss))
                    return true;

                Position pickup = routeTank->GetFirstCollisionPosition(4.0f,
                    routeBoss->GetAngle(routeTank) - routeTank->GetOrientation());
                if (MoveBotToPoint(state, bot,
                        pickup.GetPositionX(), pickup.GetPositionY(), pickup.GetPositionZ()))
                {
                    std::string raw = BuildRawJson(bot, routeBoss);
                    std::string semantic = BuildSemanticJson(
                        bot, routeBoss, "dungeon_boss", &power, stage, activity);
                    RecordEvent(state, bot, "boss_adds", routeTank,
                        "healer_preposition_for_add_pickup", raw.c_str(), semantic.c_str(),
                        bot->GetExactDist2d(routeTank), Cohort().Config.ValidationRouteTargetEntry);
                    state.TargetGuid = routeBoss->GetGUID();
                    target = routeBoss;
                    situation = "dungeon_boss";
                    action = "healer_preposition_for_add_pickup";
                    return true;
                }
            }
        }

        Unit* add = nullptr;
        bool sharedFocusValid = false;
        uint32 addCount = 0;
        uint32 engagedAddCount = 0;
        uint32 nearbyAddCount = 0;
        float addX = 0.0f;
        float addY = 0.0f;
        uint8 bestPriority = 0;
        float bestHealthPct = 1.0f;
        uint32 bestGuid = 0;
        std::vector<Creature*> localAdds;
        auto isUsableListedAdd = [this](Player* observer, Unit* candidate) -> bool
        {
            Creature* creature = candidate ? candidate->ToCreature() : nullptr;
            return observer && creature && creature->IsAlive() && creature->GetHealth()
                && creature->GetMap() == observer->GetMap()
                && std::find(Cohort().Config.ValidationRouteAddTargetEntries.begin(), Cohort().Config.ValidationRouteAddTargetEntries.end(), creature->GetEntry()) != Cohort().Config.ValidationRouteAddTargetEntries.end()
                && observer->IsValidAttackTarget(creature);
        };
        auto isUsableUnexpectedPartyHostile = [this](Player* observer, Unit* candidate) -> bool
        {
            Creature* creature = candidate ? candidate->ToCreature() : nullptr;
            if (!observer || !creature || !creature->IsAlive() || !creature->GetHealth()
                || creature->GetMap() != observer->GetMap()
                || !observer->IsValidAttackTarget(creature))
                return false;

            uint32 entry = creature->GetEntry();
            if (entry == Cohort().Config.ValidationRouteTargetEntry
                || std::find(Cohort().Config.ValidationRouteAlternateTargetEntries.begin(),
                    Cohort().Config.ValidationRouteAlternateTargetEntries.end(), entry)
                    != Cohort().Config.ValidationRouteAlternateTargetEntries.end()
                || std::find(Cohort().Config.ValidationRoutePackTargetEntries.begin(),
                    Cohort().Config.ValidationRoutePackTargetEntries.end(), entry)
                    != Cohort().Config.ValidationRoutePackTargetEntries.end())
                return false;

            Player* victim = creature->GetVictim() ? creature->GetVictim()->ToPlayer() : nullptr;
            return victim && (observer->GetGroup()
                ? victim->GetGroup() == observer->GetGroup()
                : victim == observer);
        };
        if (Party().ValidationRouteAddFocusGeneration != Party().ValidationRouteGeneration)
        {
            Party().ValidationRouteAddFocusGuid.Clear();
            Party().ValidationRouteAddFocusGeneration = 0;
        }
        if (!Party().ValidationRouteAddFocusGuid.IsEmpty())
        {
            add = ObjectAccessor::GetUnit(*bot, Party().ValidationRouteAddFocusGuid);
            if (!add)
            {
                Party().ValidationRouteAddFocusGuid.Clear();
            }
            else if (!add->IsAlive() || !add->GetHealth())
            {
                std::string raw = BuildRawJson(bot, add);
                std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
                RecordEvent(state, bot, "boss_add_killed", add, "observed_dead", raw.c_str(), semantic.c_str());
                Party().ValidationRouteAddFocusGuid.Clear();
                add = nullptr;
            }
            else if (!isUsableListedAdd(bot, add))
            {
                Party().ValidationRouteAddFocusGuid.Clear();
                add = nullptr;
            }
            else
                sharedFocusValid = true;
        }

        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, 45.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, 45.0f);
        GuidSet cohortAddGuids;
        auto considerLocalAdd = [&](Creature* creature)
        {
            cohortAddGuids.insert(creature->GetGUID());
            localAdds.push_back(creature);
            ++addCount;
            if (creature->GetVictim())
                ++engagedAddCount;
            addX += creature->GetPositionX();
            addY += creature->GetPositionY();
            if (bot->GetExactDist2d(creature) <= 12.0f)
                ++nearbyAddCount;
            if (sharedFocusValid)
                return;
            uint8 priority = 1;
            if (Player* victim = creature->GetVictim() ? creature->GetVictim()->ToPlayer() : nullptr)
            {
                std::string victimRole = GetDungeonRole(victim);
                priority = victimRole == "healer" ? 3 : (victimRole == "tank" ? 2 : 1);
            }
            float healthPct = UnitHealthPct(creature);
            uint32 guid = creature->GetGUID().GetCounter();
            if (!add
                || priority > bestPriority
                || (priority == bestPriority && healthPct < bestHealthPct)
                || (priority == bestPriority && healthPct == bestHealthPct && guid < bestGuid))
            {
                add = creature;
                bestPriority = priority;
                bestHealthPct = healthPct;
                bestGuid = guid;
            }
        };
        std::vector<Creature*> unexpectedPartyHostiles;
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            bool listedAdd = isUsableListedAdd(bot, creature);
            bool unexpectedPartyHostile = !listedAdd
                && isUsableUnexpectedPartyHostile(bot, creature);
            if ((!listedAdd && !unexpectedPartyHostile)
                || !bot->IsWithinLOSInMap(creature))
                continue;
            if (unexpectedPartyHostile)
            {
                unexpectedPartyHostiles.push_back(creature);
                continue;
            }
            considerLocalAdd(creature);
        }
        // The authoritative retention audit includes every hostile creature
        // attacking this exact party. Admit a real unexpected swarm here, while
        // ordinary route targets remain owned by the route-pack logic.
        //
        // Rerun211's final generation retained one Stonecore Bruiser beside the
        // tank and healer after three Azil recoveries. The shared density phase
        // was still active, but the three-hostile admission floor discarded that
        // exact healer attacker. It therefore remained visible to the strict
        // threat audit while the add handler returned no_compatible_density_anchor
        // and never exposed it to the Warrior's native Taunt. During an already
        // active generation-scoped density recovery, admit every real party-
        // targeting unexpected hostile; initial natural overlap still requires
        // the unchanged three-hostile proof.
        bool sharedDensityRecoveryActive =
            Party().ValidationRouteBossAddDensityPhase
            && Party().ValidationRouteBossAddDensityGeneration
                == Party().ValidationRouteGeneration;
        if (unexpectedPartyHostiles.size() >= 3
            || sharedDensityRecoveryActive)
            for (Creature* creature : unexpectedPartyHostiles)
                considerLocalAdd(creature);
        if (Party().ValidationRouteBossAddDensityPhase && addCount < 3)
        {
            for (WorldBotState const& cohortState : Party().Bots)
            {
                Player* observer = GetLoadedBot(cohortState);
                if (!observer || !observer->IsAlive() || observer->GetMap() != bot->GetMap())
                    continue;

                std::vector<WorldObject*> cohortObjects;
                Trinity::AllWorldObjectsInRange cohortCheck(observer, 45.0f);
                Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> cohortSearcher(observer, cohortObjects, cohortCheck);
                Cell::VisitAllObjects(observer, cohortSearcher, 45.0f);
                for (WorldObject* object : cohortObjects)
                {
                    Creature* creature = object ? object->ToCreature() : nullptr;
                    if (isUsableListedAdd(observer, creature) && observer->IsWithinLOSInMap(creature))
                        cohortAddGuids.insert(creature->GetGUID());
                }
                if (cohortAddGuids.size() >= 3)
                    break;
            }
        }
        bool cohortSwarmActive = cohortAddGuids.size() >= 3;
        // Rerun170 reached Azil's route generation roughly 80-115 yards from
        // the navigation anchor. Passive followers were already visible there,
        // so the add handler repeatedly diverted the tank among followers at
        // y=1062-1100 while the boss anchor remained at y=985. No boss focus or
        // activation was ever established. A passive, unengaged declared wave
        // before arrival is not encounter evidence; let the unchanged route
        // movement reach the boss anchor first. Any engaged follower or observed
        // boss preserves the existing immediate party-protection path.
        bool sharedLargePassiveSwarmStaging =
            Party().ValidationRouteLargePassiveSwarmStaging
            && Party().ValidationRouteLargePassiveSwarmStagingGeneration
                == Party().ValidationRouteGeneration;
        // Rerun196 proved the same pre-arrival diversion survives when an
        // observer sees only one or two passive followers: cohortSwarmActive is
        // false, so the original guard does not run and the selected add keeps
        // replacing route movement.  Local addCount is the exact cardinality
        // authority for this passive-only bypass.  Any engaged local follower,
        // observed boss, route arrival, or shared large-wave staging proof
        // preserves the existing immediate add-defense behavior.
        if (addCount > 0 && engagedAddCount == 0
            && Party().ValidationRouteBossProgressTargetGuid.IsEmpty()
            && canonicalRouteDistance > routeArrivalRadius
            && !sharedLargePassiveSwarmStaging)
            return false;
        if (Party().ValidationRouteBossAddDensityPhase
            && (Party().ValidationRouteBossAddDensityGeneration != Party().ValidationRouteGeneration || !cohortSwarmActive))
        {
            ResetValidationRouteBossAddDensityState();
        }

        bool observedBossEngagement = Cohort().Config.ValidationRouteKind == "boss"
            && !Party().ValidationRouteBossProgressTargetGuid.IsEmpty();
        Unit* routeBoss = observedBossEngagement
            ? ObjectAccessor::GetUnit(*bot, Party().ValidationRouteBossProgressTargetGuid)
            : nullptr;
        bool routeBossAttackable = routeBoss
            && routeBoss->IsAlive()
            && bot->IsValidAttackTarget(routeBoss);
        if (Party().ValidationRouteBossAddDensityPhase && routeBossAttackable)
        {
            ResetValidationRouteBossAddDensityState();
        }
        bool routeBossUnavailable = !routeBoss
            || (routeBoss->IsAlive() && !bot->IsValidAttackTarget(routeBoss));
        if (!Party().ValidationRouteBossAddDensityPhase
            && addCount >= 3
            && observedBossEngagement
            && routeBossUnavailable)
        {
            Party().ValidationRouteBossAddDensityPhase = true;
            Party().ValidationRouteBossAddDensityGeneration = Party().ValidationRouteGeneration;
        }

        bool highDensityPhase = Party().ValidationRouteBossAddDensityPhase
            && Party().ValidationRouteBossAddDensityGeneration == Party().ValidationRouteGeneration;
        auto explicitListedAttackerCount = [&localAdds](Player const* member) -> size_t
        {
            size_t count = 0;
            for (Creature const* candidate : localAdds)
                if (candidate && candidate->GetVictim() == member)
                    ++count;
            return count;
        };
        auto observedListedAttackerCount = [&explicitListedAttackerCount](Player const* member) -> size_t
        {
            return member
                ? std::max(member->getAttackers().size(), explicitListedAttackerCount(member))
                : 0;
        };
        // A listed swarm needs party-protection rules as soon as it engages,
        // even while the boss remains attackable.  Waiting for the scripted
        // shield/unavailable phase let Azil followers build lethal healer/DPS
        // threat before the tank's density handler existed.
        // Rerun195 proved that the shared large-passive-swarm fact could remain
        // true while a remote damage role's local 45-yard add view flickered
        // below swarm density. That made densityTank null for that role, so it
        // alternated the existing tank-follow staging with add/route movement
        // and could never satisfy the unchanged all-participant 18-yard gate.
        // The shared proof is already generation-scoped and published only by
        // the living tank's 24-plus unengaged observation. Use it to resolve
        // the same loaded tank/healer participants even when this observer has
        // no local swarm view; all staging movement and tank-only activation
        // conditions below remain unchanged.
        bool swarmDefenseActive = highDensityPhase || cohortSwarmActive
            || sharedLargePassiveSwarmStaging;
        std::string role = GetDungeonRole(bot);
        BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, role.c_str());
        // Preserve Blood's 30-second ground threat for a real follower wave.
        // Small precursor sets still receive Blood Boil and ordinary pickup,
        // while non-boss trash keeps Death and Decay available at two targets.
        uint32 reservedAreaSpellId = role == "tank"
            && profile.SpecTag == "blood_death_knight" && addCount < 5 ? 43265 : 0;
        Creature* densityApproachAnchor = nullptr;
        if (highDensityPhase && role != "healer")
        {
            Creature* densityAnchor = nullptr;
            float bestDistance = std::numeric_limits<float>::max();
            float nearestDistance = std::numeric_limits<float>::max();
            uint32 bestAnchorGuid = 0;
            uint32 nearestAnchorGuid = 0;
            bool meleeProfile = profile.MovementDirective == "melee" || (profile.MaxRange > 0.0f && profile.MaxRange <= 5.0f);
            float minRange = meleeProfile ? 0.0f : profile.MinRange;
            float maxRange = meleeProfile ? 5.0f : profile.MaxRange;
            for (Creature* candidate : localAdds)
            {
                float distance = bot->GetExactDist(candidate);
                uint32 guid = candidate->GetGUID().GetCounter();
                if (!densityApproachAnchor || distance < nearestDistance || (distance == nearestDistance && guid < nearestAnchorGuid))
                {
                    densityApproachAnchor = candidate;
                    nearestDistance = distance;
                    nearestAnchorGuid = guid;
                }
                if ((minRange > 0.0f && distance < minRange) || (maxRange > 0.0f && distance > maxRange))
                    continue;

                if (!densityAnchor || distance < bestDistance || (distance == bestDistance && guid < bestAnchorGuid))
                {
                    densityAnchor = candidate;
                    bestDistance = distance;
                    bestAnchorGuid = guid;
                }
            }
            if (role == "tank")
            {
                Creature* looseAdd = nullptr;
                uint8 loosePriority = 0;
                float looseDistance = std::numeric_limits<float>::max();
                uint32 looseGuid = std::numeric_limits<uint32>::max();
                for (Creature* candidate : localAdds)
                {
                    Player* victim = candidate->GetVictim() ? candidate->GetVictim()->ToPlayer() : nullptr;
                    std::string victimRole = victim ? GetDungeonRole(victim) : "";
                    if (!victim || victim == bot || victimRole == "tank")
                        continue;
                    uint8 priority = victimRole == "healer" ? 3 : 2;
                    float distance = bot->GetExactDist(candidate);
                    uint32 guid = candidate->GetGUID().GetCounter();
                    bool nearerSamePriority = priority == loosePriority
                        && (distance < looseDistance || (distance == looseDistance && guid < looseGuid));
                    if (!looseAdd || priority > loosePriority || nearerSamePriority)
                    {
                        looseAdd = candidate;
                        loosePriority = priority;
                        looseDistance = distance;
                        looseGuid = guid;
                    }
                }
                add = looseAdd ? looseAdd : densityAnchor;
            }
            else
                add = densityAnchor;
            sharedFocusValid = false;
        }

        Player* densityTank = nullptr;
        Player* densityHealer = nullptr;
        Player* densityDefenseTarget = nullptr;
        uint32 densityTankOwnedAddCount = 0;
        uint32 densityTankSecureAddCount = 0;
        size_t densityDefenseScore = 0;
        uint8 densityDefenseRolePriority = 0;
        size_t densityDefenseAttackerCount = 0;
        uint32 densityDefenseGuid = std::numeric_limits<uint32>::max();
        if (swarmDefenseActive)
        {
            for (WorldBotState const& cohortState : Party().Bots)
            {
                Player* member = GetLoadedBot(cohortState);
                if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap())
                    continue;
                std::string memberRole = GetDungeonRole(member);
                if (!densityTank && memberRole == "tank")
                    densityTank = member;
                if (!densityHealer && memberRole == "healer")
                    densityHealer = member;
                size_t attackerCount = observedListedAttackerCount(member);
                if (memberRole == "tank" || !attackerCount)
                    continue;

                uint8 rolePriority = memberRole == "healer" ? 2 : 1;
                // Preserve a healer bias without allowing a single healer
                // attacker to hide a lethal swarm on a damage dealer.
                size_t defenseScore = attackerCount + (memberRole == "healer" ? 3 : 0);
                // Three attackers can erase a healer in one decision interval.
                // Once that threshold is reached, protect the healer before a
                // larger DPS swarm; damage dealers already stop attacks and
                // stack for pickup while the healer must remain able to cast.
                if (memberRole == "healer" && attackerCount >= 3)
                    defenseScore += 1000;
                uint32 guid = member->GetGUID().GetCounter();
                if (!densityDefenseTarget || defenseScore > densityDefenseScore
                    || (defenseScore == densityDefenseScore && rolePriority > densityDefenseRolePriority)
                    || (defenseScore == densityDefenseScore && rolePriority == densityDefenseRolePriority
                        && attackerCount > densityDefenseAttackerCount)
                    || (defenseScore == densityDefenseScore && rolePriority == densityDefenseRolePriority
                        && attackerCount == densityDefenseAttackerCount && guid < densityDefenseGuid))
                {
                    densityDefenseTarget = member;
                    densityDefenseScore = defenseScore;
                    densityDefenseRolePriority = rolePriority;
                    densityDefenseAttackerCount = attackerCount;
                    densityDefenseGuid = guid;
                }
            }
        }

        if (densityTank)
            for (Creature* candidate : localAdds)
                if (candidate && candidate->GetVictim() == densityTank)
                {
                    ++densityTankOwnedAddCount;
                    float tankThreat = candidate->GetThreatManager().GetThreat(densityTank, true);
                    float highestPartyThreat = 0.0f;
                    for (WorldBotState const& cohortState : Party().Bots)
                    {
                        Player* member = GetLoadedBot(cohortState);
                        if (!member || member == densityTank || !member->IsAlive()
                            || member->GetMap() != candidate->GetMap())
                            continue;
                        highestPartyThreat = std::max(highestPartyThreat,
                            candidate->GetThreatManager().GetThreat(member, true));
                    }
                    // Victim ownership alone is not enough to safely release
                    // party AoE: a taunt can put the tank only barely ahead,
                    // allowing one area tick to flip the entire swarm.  Wait
                    // for both an absolute floor and substantial headroom over
                    // the highest party member before treating an add as secure.
                    if (tankThreat >= 2000.0f && tankThreat >= highestPartyThreat * 2.5f)
                        ++densityTankSecureAddCount;
                }
        bool densityTankOwnsSecureMajority = addCount > 0
            && densityTankSecureAddCount * 10 >= addCount * 9;
        bool densityTankOwnsVictimMajority = addCount > 0
            && densityTankOwnedAddCount * 10 >= addCount * 8;
        // A very large wave must be burned before its incoming damage exceeds
        // tank cooldown and healer throughput. At that point, 80% current
        // victim ownership is sufficient to release party AoE; demanding 90%
        // of adds at 2.5x threat caused DPS to wait while Corborus grew from 30
        // to 57 adds. Rerun157 proved that treating a 16-20-add burst as that
        // emergency released AoE on taunt ownership without secure headroom and
        // immediately flipped most of the wave. Keep those bounded bursts on
        // the existing strict headroom gate while retaining the emergency below
        // the proven 30-add runaway boundary.
        bool urgentSwarmDamageRelease = cohortSwarmActive && addCount >= 24
            && densityTankOwnsVictimMajority;
        bool dpsSwarmDamageRelease = densityTankOwnsSecureMajority || urgentSwarmDamageRelease;
        bool botInsideTankPickup = densityTank && bot->GetExactDist2d(densityTank) <= 8.0f;

        // A passive follower cluster can flicker across the local visibility
        // boundary while the tank is prepositioning at its spawn. Preserve the
        // accepted move for a short bounded interval so ordinary route movement
        // cannot pull the tank away between observations. Rerun68 proved that
        // clearing it immediately on engagement loses a prepositioned large
        // wave, so hand the same anchor through one 2.5-second engaged interval.
        uint64 pendingSwarmPickupNowMs = NowMs();
        bool tankPendingSwarmPickup = role == "tank"
            && state.TankPendingSwarmPickupUntilMs > pendingSwarmPickupNowMs
            && !state.TankPendingSwarmPickupAnchorGuid.IsEmpty();
        Unit* pendingSwarmPickupAnchor = nullptr;
        if (tankPendingSwarmPickup)
        {
            pendingSwarmPickupAnchor = ObjectAccessor::GetUnit(
                *bot, state.TankPendingSwarmPickupAnchorGuid);
            if (!pendingSwarmPickupAnchor || !pendingSwarmPickupAnchor->IsAlive()
                || pendingSwarmPickupAnchor->GetMap() != bot->GetMap())
            {
                state.TankPendingSwarmPickupAnchorGuid.Clear();
                state.TankPendingSwarmPickupUntilMs = 0;
                state.TankPendingSwarmPickupEngagedHandoff = false;
                tankPendingSwarmPickup = false;
                pendingSwarmPickupAnchor = nullptr;
            }
            else if (engagedAddCount >= 3
                && !state.TankPendingSwarmPickupEngagedHandoff)
            {
                state.TankPendingSwarmPickupEngagedHandoff = true;
                state.TankPendingSwarmPickupUntilMs =
                    pendingSwarmPickupNowMs + 2500;
            }
        }
        else if (!state.TankPendingSwarmPickupAnchorGuid.IsEmpty()
            || state.TankPendingSwarmPickupUntilMs)
        {
            state.TankPendingSwarmPickupAnchorGuid.Clear();
            state.TankPendingSwarmPickupUntilMs = 0;
            state.TankPendingSwarmPickupEngagedHandoff = false;
        }
        // Rerun156 exposed a declared 60-follower Feral wave whose first
        // actionable decision was consumed by the older passive preposition
        // reservation. Once that wave is active and still has no healer
        // attackers, release only the stale movement ownership so this same
        // decision reaches the existing native Charge, Roar, and area paths.
        bool feralActiveWavePreemptsPendingSwarmPickup =
            tankPendingSwarmPickup && role == "tank"
            && profile.SpecTag == "feral_druid_tank"
            && engagedAddCount >= 12 && densityHealer
            && observedListedAttackerCount(densityHealer) == 0;
        if (feralActiveWavePreemptsPendingSwarmPickup)
        {
            state.TankPendingSwarmPickupAnchorGuid.Clear();
            state.TankPendingSwarmPickupUntilMs = 0;
            state.TankPendingSwarmPickupEngagedHandoff = false;
            tankPendingSwarmPickup = false;
            pendingSwarmPickupAnchor = nullptr;
        }
        if (tankPendingSwarmPickup && pendingSwarmPickupAnchor
            && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
        {
            bool engagedHandoff =
                state.TankPendingSwarmPickupEngagedHandoff;
            bool insidePickup = bot->GetExactDist2d(pendingSwarmPickupAnchor)
                <= (engagedHandoff ? 10.0f : 6.0f);
            if (insidePickup)
            {
                bot->StopMoving();
                if (engagedHandoff)
                {
                    state.TankPendingSwarmPickupAnchorGuid.Clear();
                    state.TankPendingSwarmPickupUntilMs = 0;
                    state.TankPendingSwarmPickupEngagedHandoff = false;
                }
                // Reaching the anchor completes movement ownership. Continue
                // through the ordinary encounter resolver on this decision so
                // a passive precursor cannot turn a bounded reservation into
                // an unbounded boss-progress hold.
            }
            else
            {
                bool moved = MoveBotToPoint(state, bot,
                    pendingSwarmPickupAnchor->GetPositionX(),
                    pendingSwarmPickupAnchor->GetPositionY(),
                    pendingSwarmPickupAnchor->GetPositionZ());
                std::string raw = BuildRawJson(bot, pendingSwarmPickupAnchor);
                std::string semantic = BuildSemanticJson(
                    bot, pendingSwarmPickupAnchor, "dungeon_boss",
                    &power, stage, activity);
                RecordEvent(state, bot, "boss_add_density",
                    pendingSwarmPickupAnchor,
                    moved ? "tank_continue_pending_swarm_pickup_preposition"
                          : "tank_pending_swarm_pickup_path_rejected",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist2d(pendingSwarmPickupAnchor), addCount);
                state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
                target = add;
                situation = "dungeon_boss";
                action = moved ? "continue_pending_swarm_pickup_preposition"
                               : "hold_pending_swarm_pickup_path_rejected";
                return true;
            }
        }

        // Fade before the first healing tick after a newly activated wave
        // reaches the priest.  Do not spend the native cooldown while the
        // healer has no listed attackers: rerun80 showed that an early
        // zero-exposure cast left Fade unavailable for the actual Azil wave.
        // Keep the ordinary reactive Fade in tryRouteGroupHeal for smaller
        // pulls, but use it here while a listed swarm is not yet securely
        // owned by the tank.
        bool healerWaveFadeReady = role == "healer" && cohortSwarmActive
            && observedListedAttackerCount(bot) > 0
            && !densityTankOwnsSecureMajority
            && bot->HasSpell(586) && !bot->HasAura(586);
        // Rerun104's first 60-follower wave reached the healer while Smite was
        // still in flight. The existing preemptive Fade could not submit until
        // the following healer decision, which left eight identities beyond
        // the hard dwell gate. Interrupt only a harmful cast for this declared
        // wave; a positive healing cast remains authoritative.
        if (healerWaveFadeReady)
            if (Spell* currentSpell = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL))
                if (!currentSpell->IsPositive())
                    bot->InterruptNonMeleeSpells(false);
        if (healerWaveFadeReady && !bot->HasUnitState(UNIT_STATE_CASTING)
            && TryCastFriendlySpell(bot, bot, 586))
        {
            std::string raw = BuildRawJson(bot, add);
            std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_adds", bot, "fade_preemptive_add_wave_threat_drop",
                raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(bot)), addCount, 586);
            state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
            target = add;
            situation = "dungeon_boss";
            action = "fade_preemptive_add_wave_threat_drop";
            return true;
        }

        // Aim area threat at a representative of the densest listed attacker
        // cluster. Selecting only the closest healer attacker could place a
        // ground effect on the edge of an Azil wave and move self-centered AoE
        // away from most of the swarm. Distance and GUID remain deterministic
        // tie-breakers after local cluster coverage.
        static constexpr float TankDensityClusterRadius = 10.0f;
        if (role == "tank" && densityDefenseTarget)
        {
            std::vector<Unit*> densityDefenseAttackers;
            for (Creature* candidate : localAdds)
                if (candidate && candidate->GetVictim() == densityDefenseTarget
                    && bot->IsWithinLOSInMap(candidate))
                    densityDefenseAttackers.push_back(candidate);
            if (densityDefenseAttackers.empty())
                for (Unit* attacker : densityDefenseTarget->getAttackers())
                    if (isUsableListedAdd(bot, attacker) && bot->IsWithinLOSInMap(attacker))
                        densityDefenseAttackers.push_back(attacker);

            Unit* densityClusterAttacker = nullptr;
            uint32 densityClusterCount = 0;
            float densityClusterDistance = std::numeric_limits<float>::max();
            uint32 densityClusterGuid = std::numeric_limits<uint32>::max();
            for (Unit* attacker : densityDefenseAttackers)
            {
                uint32 localClusterCount = 0;
                for (Unit* neighbor : densityDefenseAttackers)
                    if (attacker->GetExactDist2d(neighbor) <= TankDensityClusterRadius)
                        ++localClusterCount;

                float distance = bot->GetExactDist(attacker);
                uint32 guid = attacker->GetGUID().GetCounter();
                if (!densityClusterAttacker || localClusterCount > densityClusterCount
                    || (localClusterCount == densityClusterCount
                        && (distance < densityClusterDistance
                            || (distance == densityClusterDistance && guid < densityClusterGuid))))
                {
                    densityClusterAttacker = attacker;
                    densityClusterCount = localClusterCount;
                    densityClusterDistance = distance;
                    densityClusterGuid = guid;
                }
            }
            if (densityClusterAttacker)
            {
                add = densityClusterAttacker;
                sharedFocusValid = false;
            }
        }

        // Rerun64 proved that passive-cluster preposition can hand a large wave
        // to the Feral quickly enough to expose an ordering gap: pickup actions
        // continued while native defensives were suppressed by healer ownership,
        // and the tank died after acquiring most of a 60-follower wave. Feral
        // defensives are off the global cooldown, so submit one at the existing
        // health/add thresholds and continue through the same decision to native
        // threat pickup. Exact hazard movement has already run before this block.
        if (role == "tank" && profile.SpecTag == "feral_druid_tank"
            && cohortSwarmActive && addCount >= 12
            && UnitHealthPct(bot) <= 0.90f
            && !bot->HasAura(61336) && !bot->HasAura(22812))
        {
            std::array<uint32, 2> defensiveSpells = { 61336, 22812 };
            for (uint32 defensiveSpellId : defensiveSpells)
                if (bot->HasSpell(defensiveSpellId)
                    && TryCastFriendlySpell(bot, bot, defensiveSpellId))
                {
                    std::string raw = BuildRawJson(bot, add);
                    std::string semantic = BuildSemanticJson(
                        bot, add, "dungeon_boss", &power, stage, activity);
                    RecordEvent(state, bot, "defensive", bot,
                        "tank_swarm_defensive", raw.c_str(), semantic.c_str(),
                        UnitHealthPct(bot), addCount, defensiveSpellId);
                    break;
                }
        }

        // Build native Roar pickup as a deferred action. Charge ownership and
        // arrival proof run first below; otherwise a legal edge Roar can preempt
        // the bounded charge one decision after launch. Cast only once the tank
        // is centered on the stationary healer's melee ring or already covers a
        // deterministic majority of the healer-owned wave. This preserves the
        // passive split-cluster pickup while avoiding low-coverage edge casts.
        // Rerun98 passed both Feral retention gates, but two Azil waves cleared
        // at 3018 ms and 3012 ms. Rerun100 then began 60/60 tank-owned and lost
        // 29 followers to the healer exactly 3013 ms after activation; waiting
        // for healer ownership before lowering the cadence was already too
        // late for the first acquisition-eligible snapshot. Sample any real
        // active three-or-more-add Feral swarm at the established lower bound.
        if (role == "tank" && profile.SpecTag == "feral_druid_tank"
            && cohortSwarmActive)
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 500);

        // Rerun148 observed twenty already-engaged Azil followers remain in a
        // pre-victim state for four decisions while the Feral preserved an
        // ordinary stable melee approach. The wave was older than the strict
        // acquisition grace when healing threat assigned nineteen followers
        // at once. Poll only that declared high-density, zero-healer-attacker
        // window at the established specialized pickup cadence so the existing
        // native area resolver can submit as soon as two followers enter range.
        // No target, victim, path, spell, or threat semantics change here.
        if (role == "tank" && profile.SpecTag == "feral_druid_tank"
            && engagedAddCount >= 12 && densityHealer
            && observedListedAttackerCount(densityHealer) == 0)
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);

        // Rerun162 proved the same bounded Protection pickup cadence is needed
        // for a declared healer-density handoff even when the encounter has not
        // classified the wave as a cohort swarm. The density healer plus two
        // listed attackers (or twelve engaged adds) remains the narrow gate.
        // Spell order, movement, victims, cooldowns, legality, and threat remain
        // unchanged below.
        if (role == "tank" && profile.SpecTag == "protection"
            && densityHealer
            && (engagedAddCount >= 12
                || observedListedAttackerCount(densityHealer) >= 2))
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);

        auto tryFeralRoarPickup = [&](bool activeClusterArrived = false) -> bool
        {
            return TryValidationFeralRoarPickup(state, bot, power, stage,
                activity, situation, action, target, role, profile,
                densityHealer, localAdds, observedListedAttackerCount,
                activeClusterArrived);
        };

        // A successful Feral Charge owns its movement briefly. Issuing MovePoint
        // on the next decision clears MOTION_SLOT_ACTIVE and can cancel the charge
        // before the tank reaches a newly activated follower wave. Preserve the
        // charged target until that target and nearby adds prove arrival, then
        // hand control back to the existing strict self-centered area resolver.
        uint64 feralChargeNowMs = NowMs();
        bool feralChargePickupInFlight = role == "tank"
            && profile.SpecTag == "feral_druid_tank"
            && state.FeralChargePickupUntilMs > feralChargeNowMs
            && !state.FeralChargePickupTargetGuid.IsEmpty();
        Unit* feralChargePickupTarget = nullptr;
        bool feralChargePickupArrived = false;
        if (feralChargePickupInFlight)
        {
            // Rerun148 accepted Charge on the final healer-owned follower, but
            // the next changing local-add snapshot omitted that GUID and
            // cleared the reservation while the same live unit remained in the
            // identity-scoped threat trace. Resolve the exact accepted identity
            // independently of the density snapshot; the original bounded
            // lifetime and native alive/map/attackable gates remain unchanged.
            feralChargePickupTarget = ObjectAccessor::GetUnit(
                *bot, state.FeralChargePickupTargetGuid);
            if (feralChargePickupTarget
                && (!feralChargePickupTarget->IsAlive()
                    || feralChargePickupTarget->GetMap() != bot->GetMap()
                    || !bot->IsValidAttackTarget(feralChargePickupTarget)))
                feralChargePickupTarget = nullptr;
            if (feralChargePickupTarget)
            {
                add = feralChargePickupTarget;
                sharedFocusValid = false;
            }
            else
            {
                // Rerun126 charged the first Azil follower in 508 ms, but the
                // anchor died on arrival and discarded the accepted movement.
                // Preserve arrival only when a live healer-owned follower is
                // already inside native Roar range; no victim is reassigned.
                Unit* nearbyHealerFollower = nullptr;
                float nearbyHealerFollowerDistance =
                    std::numeric_limits<float>::max();
                uint32 nearbyHealerFollowerGuid =
                    std::numeric_limits<uint32>::max();
                for (Creature* candidate : localAdds)
                    if (candidate && densityHealer
                        && candidate->GetVictim() == densityHealer
                        && bot->GetExactDist2d(candidate) <= 10.0f)
                    {
                        float distance = bot->GetExactDist(candidate);
                        uint32 guid = candidate->GetGUID().GetCounter();
                        if (!nearbyHealerFollower
                            || distance < nearbyHealerFollowerDistance
                            || (distance == nearbyHealerFollowerDistance
                                && guid < nearbyHealerFollowerGuid))
                        {
                            nearbyHealerFollower = candidate;
                            nearbyHealerFollowerDistance = distance;
                            nearbyHealerFollowerGuid = guid;
                        }
                    }
                if (nearbyHealerFollower)
                {
                    add = nearbyHealerFollower;
                    sharedFocusValid = false;
                    feralChargePickupArrived = true;
                }
                state.FeralChargePickupTargetGuid.Clear();
                state.FeralChargePickupUntilMs = 0;
                feralChargePickupInFlight = false;
            }
        }
        else if (!state.FeralChargePickupTargetGuid.IsEmpty()
            || state.FeralChargePickupUntilMs)
        {
            state.FeralChargePickupTargetGuid.Clear();
            state.FeralChargePickupUntilMs = 0;
        }

        if (feralChargePickupInFlight && feralChargePickupTarget)
        {
            Unit* nearbyPickupAdd = nullptr;
            float nearbyPickupDistance = std::numeric_limits<float>::max();
            uint32 nearbyPickupAddCount = 0;
            for (Creature* candidate : localAdds)
                if (candidate && bot->GetExactDist2d(candidate) <= 10.0f)
                {
                    ++nearbyPickupAddCount;
                    float distance = bot->GetExactDist(candidate);
                    if (!nearbyPickupAdd || distance < nearbyPickupDistance
                        || (distance == nearbyPickupDistance
                            && candidate->GetGUID().GetCounter()
                                < nearbyPickupAdd->GetGUID().GetCounter()))
                    {
                        nearbyPickupAdd = candidate;
                        nearbyPickupDistance = distance;
                    }
                }

            if (bot->GetExactDist2d(feralChargePickupTarget) <= 10.0f
                && nearbyPickupAddCount >= 2 && nearbyPickupAdd)
            {
                add = nearbyPickupAdd;
                sharedFocusValid = false;
                feralChargePickupArrived = true;
            }
            else if (bot->GetExactDist2d(feralChargePickupTarget) > 10.0f)
            {
                std::string raw = BuildRawJson(bot, feralChargePickupTarget);
                std::string semantic = BuildSemanticJson(
                    bot, feralChargePickupTarget, "dungeon_boss", &power, stage, activity);
                RecordEvent(state, bot, "boss_add_density", feralChargePickupTarget,
                    "feral_charge_swarm_pickup_in_flight",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist2d(feralChargePickupTarget), addCount, 16979);
                state.TargetGuid = feralChargePickupTarget->GetGUID();
                target = feralChargePickupTarget;
                situation = "dungeon_boss";
                action = "feral_charge_swarm_pickup_in_flight";
                return true;
            }
        }

        // Preserve the bounded post-Roar movement for 2.5 seconds while exact
        // hazard movement above remains authoritative. Rerun103 proved the
        // stationary-healer form must not replace an already accepted path to
        // the remaining remote follower cluster. On arrival, hold through the
        // native Roar GCD instead of walking back to another cluster.
        uint64 feralHealerHandoffNowMs = NowMs();
        Unit* feralHealerHandoffAnchor = nullptr;
        if (!state.FeralHealerThreatHandoffAnchorGuid.IsEmpty())
            feralHealerHandoffAnchor = ObjectAccessor::GetUnit(
                *bot, state.FeralHealerThreatHandoffAnchorGuid);
        // Rerun156 proved the boss handoff discarded a still-valid Azil
        // cluster when Roar transferred the exact anchor but neighboring
        // followers remained healer-owned. Match the proven ordinary-trash
        // behavior: rebind within the original anchor's ten-yard cluster,
        // without changing the existing bounded handoff lifetime.
        if (state.FeralHealerThreatHandoffRemoteCluster && densityHealer
            && feralHealerHandoffAnchor
            && feralHealerHandoffAnchor->IsAlive()
            && feralHealerHandoffAnchor->GetMap() == bot->GetMap()
            && feralHealerHandoffAnchor->GetVictim() != densityHealer
            && state.FeralHealerThreatHandoffUntilMs
                > feralHealerHandoffNowMs)
        {
            Creature* reboundAnchor = nullptr;
            uint32 reboundGuid = std::numeric_limits<uint32>::max();
            for (Creature* candidate : localAdds)
                if (candidate && candidate->IsAlive()
                    && candidate->GetMap() == bot->GetMap()
                    && candidate->GetVictim() == densityHealer
                    && bot->IsValidAttackTarget(candidate)
                    && feralHealerHandoffAnchor->GetExactDist2d(candidate)
                        <= 10.0f
                    && candidate->GetGUID().GetCounter() < reboundGuid)
                {
                    reboundAnchor = candidate;
                    reboundGuid = candidate->GetGUID().GetCounter();
                }
            // Rerun186's first Roar started a bounded split-cluster handoff,
            // then a newly listed healer-owned follower appeared outside the
            // original remote anchor's ten-yard cluster. The second Roar
            // transferred that original cluster and invalidated its anchor,
            // leaving the newcomer behind until generic Thrash exceeded the
            // strict dwell bound by 77 ms. Preserve the original-cluster
            // preference above; only when it is empty, rebind the same active,
            // healer-identity-bound handoff to the nearest remaining follower.
            // The original 2.5-second lifetime, native Charge/Roar/area casts,
            // movement, hazard, victim, and threat rules remain unchanged.
            if (!reboundAnchor)
            {
                float reboundDistance = std::numeric_limits<float>::max();
                for (Creature* candidate : localAdds)
                    if (candidate && candidate->IsAlive()
                        && candidate->GetMap() == bot->GetMap()
                        && candidate->GetVictim() == densityHealer
                        && bot->IsValidAttackTarget(candidate))
                    {
                        float distance = bot->GetExactDist(candidate);
                        uint32 guid = candidate->GetGUID().GetCounter();
                        if (!reboundAnchor || distance < reboundDistance
                            || (distance == reboundDistance
                                && guid < reboundGuid))
                        {
                            reboundAnchor = candidate;
                            reboundDistance = distance;
                            reboundGuid = guid;
                        }
                    }
            }
            if (reboundAnchor)
            {
                state.FeralHealerThreatHandoffAnchorGuid =
                    reboundAnchor->GetGUID();
                feralHealerHandoffAnchor = reboundAnchor;
            }
        }
        bool feralHealerRemoteHandoffValid =
            !state.FeralHealerThreatHandoffRemoteCluster
            || (feralHealerHandoffAnchor
                && feralHealerHandoffAnchor->IsAlive()
                && feralHealerHandoffAnchor->GetMap() == bot->GetMap()
                && feralHealerHandoffAnchor->GetVictim() == densityHealer
                && bot->IsValidAttackTarget(feralHealerHandoffAnchor));
        bool feralHealerHandoffActive = role == "tank"
            && profile.SpecTag == "feral_druid_tank"
            && densityHealer
            && state.FeralHealerThreatHandoffUntilMs
                > feralHealerHandoffNowMs
            && state.FeralHealerThreatHandoffTargetGuid
                == densityHealer->GetGUID()
            && feralHealerRemoteHandoffValid
            && observedListedAttackerCount(densityHealer) >= 2;
        if (!feralHealerHandoffActive
            && (!state.FeralHealerThreatHandoffTargetGuid.IsEmpty()
                || !state.FeralHealerThreatHandoffAnchorGuid.IsEmpty()
                || state.FeralHealerThreatHandoffUntilMs
                || state.FeralHealerThreatHandoffRemoteCluster))
        {
            state.FeralHealerThreatHandoffTargetGuid.Clear();
            state.FeralHealerThreatHandoffAnchorGuid.Clear();
            state.FeralHealerThreatHandoffUntilMs = 0;
            state.FeralHealerThreatHandoffRemoteCluster = false;
        }

        bool feralHealerHandoffArrived = false;
        if (feralHealerHandoffActive)
        {
            // Rerun109's Azil episode repeatedly waited on one moving anchor
            // although two other still-unaffected healer followers were
            // already inside native Roar range. Match the corrected ordinary
            // handoff: an unaffected local majority proves bounded arrival,
            // without accepting a minority edge cast for a large wave.
            uint32 localMissingRoarDuringHandoff = 0;
            for (Creature* candidate : localAdds)
                if (candidate && candidate->GetVictim() == densityHealer
                    && bot->GetExactDist2d(candidate) <= 10.0f
                    && !candidate->HasAura(99, bot->GetGUID()))
                    ++localMissingRoarDuringHandoff;
            uint32 healerOwnedDuringHandoff =
                uint32(observedListedAttackerCount(densityHealer));
            bool localMissingRoarCoversMajority =
                localMissingRoarDuringHandoff >= 2
                && localMissingRoarDuringHandoff * 2
                    >= healerOwnedDuringHandoff;
            feralHealerHandoffArrived =
                localMissingRoarCoversMajority
                || (state.FeralHealerThreatHandoffRemoteCluster
                    ? bot->GetExactDist2d(feralHealerHandoffAnchor) <= 10.0f
                    : bot->GetExactDist2d(densityHealer) <= 3.0f);
        }

        // Rerun171 completed all fourteen route nodes and all four bosses, but
        // Azil follower waves remained on the healer for up to 4108 ms while
        // this arrived handoff waited for another non-damaging Roar. Match the
        // already-proved ordinary-trash recovery: when the local healer-owned
        // set covers a majority of the current wave, submit one native Swipe
        // before retrying Roar. Rerun190 then proved the same damaging pickup
        // was still restricted to an already-active, arrived handoff: fresh
        // local waves instead spent the first legal GCD on Roar, and partial
        // pickup left six generation-14 identities beyond the strict dwell
        // ceiling. Admit the same majority proof before a handoff starts while
        // preserving remote handoff movement until arrival. A rejected cast
        // changes no state and falls through; native GCD, power, range, LOS,
        // target, and threat semantics remain authoritative.
        Creature* localHealerOwnedSwipeTarget = nullptr;
        uint32 localHealerOwnedSwipeCount = 0;
        float localHealerOwnedSwipeDistance =
            std::numeric_limits<float>::max();
        uint32 localHealerOwnedSwipeGuid =
            std::numeric_limits<uint32>::max();
        bool localHealerOwnedSwipeWindow = role == "tank"
            && profile.SpecTag == "feral_druid_tank" && densityHealer
            && (!feralHealerHandoffActive || feralHealerHandoffArrived);
        if (localHealerOwnedSwipeWindow)
            for (Creature* candidate : localAdds)
                if (candidate && candidate->GetVictim() == densityHealer
                    && bot->GetExactDist2d(candidate) <= 10.0f)
                {
                    ++localHealerOwnedSwipeCount;
                    float distance = bot->GetExactDist(candidate);
                    uint32 guid = candidate->GetGUID().GetCounter();
                    if (!localHealerOwnedSwipeTarget
                        || distance < localHealerOwnedSwipeDistance
                        || (distance == localHealerOwnedSwipeDistance
                            && guid < localHealerOwnedSwipeGuid))
                    {
                        localHealerOwnedSwipeTarget = candidate;
                        localHealerOwnedSwipeDistance = distance;
                        localHealerOwnedSwipeGuid = guid;
                    }
                }
        uint32 healerOwnedBeforeHandoffSwipe = densityHealer
            ? uint32(observedListedAttackerCount(densityHealer)) : 0;
        bool localHealerOwnedMajority = localHealerOwnedSwipeCount >= 2
            && localHealerOwnedSwipeCount * 2
                >= healerOwnedBeforeHandoffSwipe;
        // Rerun204 proved that the fresh local-majority Thrash gate preserves
        // retention and exposure, but its final Azil wave first exposed a
        // useful local minority: twelve followers still owned the healer and
        // at least two were inside the native area envelope. The existing
        // large-wave Roar gate accepted that exact topology, then its global
        // cooldown occupied the arrived handoff until only GUID 744 remained;
        // the lingering Swipe cleared it after 3338 ms. Give persistent native
        // Thrash the same already-proved fresh large-wave local-cluster scope
        // before Roar. Smaller fresh minorities, remote clusters, and every
        // native cooldown, GCD, power, range, LOS, target, threat, movement,
        // and hazard gate retain their existing behavior.
        bool freshLargeLocalHealerCluster = !feralHealerHandoffActive
            && healerOwnedBeforeHandoffSwipe >= 12
            && localHealerOwnedSwipeCount >= 2;
        // Rerun198's second failing Azil subwave reached its identity-bound,
        // arrived handoff in 766 ms, but the first damaging GCD used Swipe.
        // Seven followers still owned the healer until the handoff expired;
        // the later native Thrash completed pickup only after 3324 ms. Prefer
        // that same persistent native area threat on an already-arrived
        // handoff, retaining Swipe below whenever Thrash is unavailable.
        // Rerun199 then reached the same arrived handoff with a real local
        // healer-owned target that was not a majority. The majority guard
        // skipped Thrash, a second non-damaging Roar consumed the GCD, and four
        // continuous identities remained on the healer for 3335 ms. An active,
        // arrived, healer-identity-bound handoff already proves the narrow
        // scope; allow its exact local target to receive native Thrash while
        // fresh waves and the Swipe fallback retain the majority guard.
        // Rerun203 proved the ordinary-trash Thrash correction was effective:
        // generation 13 retained every eligible hostile and the run-wide
        // healer exposure fell to 3/1766. Its only remaining failure was a
        // fresh Azil local-majority wave. Native Swipe recovered five of seven
        // healer-owned followers, but the remaining pair moved outside the
        // melee-area envelope; repeated out-of-range density selections then
        // delayed Growl and a second Swipe until GUID 719 reached 3603 ms.
        // The last accepted Thrash was 27 seconds earlier, yet this fresh-wave
        // gate offered only Swipe. Match the now-proved ordinary recovery by
        // preferring persistent native Thrash for this same exact local-
        // majority proof, while retaining the existing arrived-handoff scope
        // and unchanged Swipe fallback. Native spell, cooldown, GCD, power,
        // range, LOS, target, threat, movement, and hazard gates remain final.
        if (localHealerOwnedSwipeTarget
            && ((feralHealerHandoffActive && feralHealerHandoffArrived)
                || localHealerOwnedMajority
                || freshLargeLocalHealerCluster)
            && healerOwnedBeforeHandoffSwipe >= 2
            && bot->HasSpell(77758)
            && TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758))
        {
            std::string raw = BuildRawJson(bot, localHealerOwnedSwipeTarget);
            std::string semantic = BuildSemanticJson(
                bot, localHealerOwnedSwipeTarget, "dungeon_boss",
                &power, stage, activity);
            RecordEvent(state, bot, "boss_add_density",
                localHealerOwnedSwipeTarget,
                "feral_thrash_healer_swarm_retention_before_roar",
                raw.c_str(), semantic.c_str(),
                float(localHealerOwnedSwipeCount),
                float(healerOwnedBeforeHandoffSwipe), 77758);
            state.TargetGuid = localHealerOwnedSwipeTarget->GetGUID();
            target = localHealerOwnedSwipeTarget;
            situation = "dungeon_boss";
            action = "feral_thrash_healer_swarm_retention_before_roar";
            state.WasInCombat = true;
            state.DecisionTimer = std::min<uint32>(state.DecisionTimer, 250);
            return true;
        }
        if (localHealerOwnedSwipeTarget && bot->HasSpell(779)
            && localHealerOwnedMajority
            && TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779))
        {
            std::string raw = BuildRawJson(bot, localHealerOwnedSwipeTarget);
            std::string semantic = BuildSemanticJson(
                bot, localHealerOwnedSwipeTarget, "dungeon_boss",
                &power, stage, activity);
            RecordEvent(state, bot, "boss_add_density",
                localHealerOwnedSwipeTarget,
                "feral_swipe_healer_swarm_retention_before_roar",
                raw.c_str(), semantic.c_str(),
                float(localHealerOwnedSwipeCount),
                float(healerOwnedBeforeHandoffSwipe), 779);
            state.TargetGuid = localHealerOwnedSwipeTarget->GetGUID();
            target = localHealerOwnedSwipeTarget;
            situation = "dungeon_boss";
            action = "feral_swipe_healer_swarm_retention_before_roar";
            state.WasInCombat = true;
            state.DecisionTimer = std::min<uint32>(state.DecisionTimer, 250);
            return true;
        }

        // Rerun163 reached its identity-bound remote handoff after the first
        // native Roar, but the post-Roar damage resolver consumed the first
        // available global cooldown before the existing second-Roar resolver.
        // Retry that unchanged native pickup first only after the same bounded
        // handoff has arrived. If the cast is unavailable or illegal, fall
        // through to the established damage-retention and movement paths.
        if (feralHealerHandoffActive && feralHealerHandoffArrived
            && tryFeralRoarPickup(true))
            return true;

        // Rerun144 proved that a successful local Roar can cover a useful
        // healer-owned majority, then return into the specialized handoff and
        // Roar paths for longer than the strict dwell budget without landing
        // damaging area threat. Once that exact local coverage is visible,
        // give the existing strict area-only profile resolver one decision
        // before any further handoff movement or Roar. Native GCD, cooldown,
        // power, range, LOS, target, and threat semantics remain authoritative.
        // Rerun147 proved the original coverage scan was contradictory: a
        // follower affected by Roar normally stops targeting the healer, so
        // requiring both states rejected every successful local cast. The
        // identity-bound active handoff and remaining healer attackers keep
        // this correction limited to the intended post-Roar window.
        uint32 localRoarCoveredCount = 0;
        Creature* postRoarAreaTarget = nullptr;
        float postRoarAreaDistance = std::numeric_limits<float>::max();
        uint32 postRoarAreaGuid = std::numeric_limits<uint32>::max();
        if (role == "tank" && profile.SpecTag == "feral_druid_tank"
            && densityHealer)
            for (Creature* candidate : localAdds)
                if (candidate && bot->GetExactDist2d(candidate) <= 10.0f
                    && candidate->HasAura(99, bot->GetGUID()))
                {
                    ++localRoarCoveredCount;
                    float distance = bot->GetExactDist(candidate);
                    uint32 guid = candidate->GetGUID().GetCounter();
                    if (!postRoarAreaTarget || distance < postRoarAreaDistance
                        || (distance == postRoarAreaDistance
                            && guid < postRoarAreaGuid))
                    {
                        postRoarAreaTarget = candidate;
                        postRoarAreaDistance = distance;
                        postRoarAreaGuid = guid;
                    }
                }
        uint32 healerOwnedAfterRoar = densityHealer
            ? uint32(observedListedAttackerCount(densityHealer)) : 0;
        // Rerun181 showed this resolver could spend native Swipe and its GCD
        // on already-owned local followers while the remaining healer-owned
        // cluster was still remote. Preserve its post-arrival retention role,
        // but leave pre-arrival movement and Charge authoritative so the
        // healer-owned Swipe-before-Roar path can own the first arrived GCD.
        bool postRoarAreaThreatReady = feralHealerHandoffActive
            && feralHealerHandoffArrived
            && healerOwnedAfterRoar >= 2 && postRoarAreaTarget
            && localRoarCoveredCount >= 2
            && localRoarCoveredCount * 2 >= healerOwnedAfterRoar;
        if (postRoarAreaThreatReady)
        {
            ResolvedCombatAction postRoarAreaThreat =
                ResolveProfileCombatAction(
                    bot, postRoarAreaTarget, addCount, true, 0, true);
            if (postRoarAreaThreat.Valid)
            {
                BotActionResult postRoarAreaResult = ExecuteProfileCombatAction(
                    &state, bot, postRoarAreaTarget, &postRoarAreaThreat,
                    addCount, true, 0, true);
                if (postRoarAreaResult == BotActionResult::Ok
                    || postRoarAreaResult == BotActionResult::Casting
                    || postRoarAreaResult == BotActionResult::GlobalCooldown)
                {
                    char const* postRoarAction =
                        postRoarAreaResult == BotActionResult::Ok
                            ? "feral_post_roar_area_threat_retention"
                            : "feral_hold_post_roar_area_threat_retention";
                    std::string raw = BuildRawJson(bot, postRoarAreaTarget);
                    std::string semantic = BuildSemanticJson(
                        bot, postRoarAreaTarget, "dungeon_boss",
                        &power, stage, activity);
                    RecordEvent(state, bot, "boss_add_density",
                        postRoarAreaTarget, postRoarAction,
                        raw.c_str(), semantic.c_str(),
                        float(localRoarCoveredCount),
                        float(healerOwnedAfterRoar),
                        postRoarAreaResult == BotActionResult::Ok
                            ? postRoarAreaThreat.SpellId : 0);
                    state.DecisionTimer = std::min<uint32>(
                        state.DecisionTimer, 250);
                    state.TargetGuid = postRoarAreaTarget->GetGUID();
                    state.WasInCombat = true;
                    target = postRoarAreaTarget;
                    situation = "dungeon_boss";
                    action = postRoarAction;
                    return true;
                }
            }
        }

        if (feralHealerHandoffActive)
        {
            // Rerun106 isolated two Azil split waves whose successful local
            // Roar was followed by 3.5-4.6 seconds of ground movement. The
            // ordinary Charge branch below was suppressed solely because this
            // identity-bound post-Roar handoff was active. Reuse native Charge
            // against that same validated remote anchor before continuing the
            // ground path. Exact hazard handling has already run and remains
            // authoritative; cooldown, range, casting, falling, target, and
            // the existing 2.5-second Charge reservation stay unchanged.
            if (!feralHealerHandoffArrived
                && state.FeralHealerThreatHandoffRemoteCluster
                && bot->GetExactDist(feralHealerHandoffAnchor) > 8.0f
                && bot->HasSpell(16979)
                && !bot->HasUnitState(UNIT_STATE_CASTING)
                && !bot->IsFalling()
                && TryCastCombatSpell(bot, feralHealerHandoffAnchor, 16979))
            {
                std::string raw = BuildRawJson(bot, feralHealerHandoffAnchor);
                std::string semantic = BuildSemanticJson(
                    bot, feralHealerHandoffAnchor, "dungeon_boss",
                    &power, stage, activity);
                RecordEvent(state, bot, "boss_add_density",
                    feralHealerHandoffAnchor,
                    "feral_charge_remote_cluster_swarm_handoff",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist(feralHealerHandoffAnchor),
                    float(observedListedAttackerCount(densityHealer)), 16979);
                state.FeralChargePickupTargetGuid =
                    feralHealerHandoffAnchor->GetGUID();
                state.FeralChargePickupUntilMs = NowMs() + 2500;
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 500);
                state.TargetGuid = feralHealerHandoffAnchor->GetGUID();
                state.WasInCombat = true;
                target = feralHealerHandoffAnchor;
                situation = "dungeon_boss";
                action = "feral_charge_remote_cluster_swarm_handoff";
                return true;
            }
            if (!feralHealerHandoffArrived
                && !bot->HasUnitState(UNIT_STATE_CASTING)
                && !bot->IsFalling())
            {
                Unit* movementAnchor =
                    state.FeralHealerThreatHandoffRemoteCluster
                        ? feralHealerHandoffAnchor : densityHealer;
                // Rerun141 left one generation-14 boss-handoff attacker on the
                // healer for 3579 ms. Match the ordinary-trash handoff's proven
                // collision-safe native-Roar range instead of spending the dwell
                // budget walking to the hostile's exact point.
                Position remoteRoarIntercept;
                if (state.FeralHealerThreatHandoffRemoteCluster)
                    remoteRoarIntercept =
                        movementAnchor->GetFirstCollisionPosition(
                            8.0f,
                            movementAnchor->GetAngle(bot)
                                - movementAnchor->GetOrientation());
                float movementX =
                    state.FeralHealerThreatHandoffRemoteCluster
                        ? remoteRoarIntercept.GetPositionX()
                        : movementAnchor->GetPositionX();
                float movementY =
                    state.FeralHealerThreatHandoffRemoteCluster
                        ? remoteRoarIntercept.GetPositionY()
                        : movementAnchor->GetPositionY();
                float movementZ =
                    state.FeralHealerThreatHandoffRemoteCluster
                        ? remoteRoarIntercept.GetPositionZ()
                        : movementAnchor->GetPositionZ();
                bool continuingRemotePath =
                    state.FeralHealerThreatHandoffRemoteCluster
                    && state.ActivePathValid && state.IsMoving
                    && movementAnchor->GetExactDist2d(
                        state.ActivePathToX, state.ActivePathToY) <= 10.0f;
                bool moved = continuingRemotePath || MoveBotToPoint(state, bot,
                    movementX, movementY, movementZ);
                std::string raw = BuildRawJson(bot, movementAnchor);
                std::string semantic = BuildSemanticJson(
                    bot, movementAnchor, "dungeon_boss",
                    &power, stage, activity);
                RecordEvent(state, bot, "boss_add_density", movementAnchor,
                    moved
                        ? (state.FeralHealerThreatHandoffRemoteCluster
                            ? "feral_continue_remote_cluster_swarm_handoff"
                            : "feral_continue_healer_swarm_handoff")
                        : "feral_healer_swarm_handoff_path_rejected",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist2d(movementAnchor),
                    float(observedListedAttackerCount(densityHealer)));
                state.TargetGuid = add
                    ? add->GetGUID() : ObjectGuid::Empty;
                target = add;
                situation = "dungeon_boss";
                action = moved
                    ? (state.FeralHealerThreatHandoffRemoteCluster
                        ? "feral_continue_remote_cluster_swarm_handoff"
                        : "feral_continue_healer_swarm_handoff")
                    : "feral_hold_healer_swarm_handoff_path_rejected";
                return true;
            }
            if (feralHealerHandoffArrived)
                bot->StopMoving();
        }

        // A remote Charge must not abandon a useful local healer-owned cluster.
        // Rerun94 had ten established followers already inside the Feral's Roar
        // radius when a newer remote cluster appeared; charging first turned
        // those already-eligible followers into the entire exposure failure.
        // Resolve only the currently local native area pickup here. If fewer
        // than two are local, fall through to Charge exactly as before.
        uint32 localHealerOwnedBeforeCharge = 0;
        if (!feralChargePickupInFlight && role == "tank"
            && profile.SpecTag == "feral_druid_tank" && densityHealer)
            for (Creature* candidate : localAdds)
                if (candidate && candidate->GetVictim() == densityHealer
                    && bot->GetExactDist2d(candidate) <= 10.0f)
                    ++localHealerOwnedBeforeCharge;

        // Rerun193 completed every strict route objective, but two moderate
        // Azil waves first exposed the healer while only a minority of their
        // followers were inside native Roar range. The useful local Roar then
        // consumed the first global cooldown and its bounded ground handoff
        // needed another global cooldown to reach the remote majority. Give
        // native Charge one attempt against the densest deterministic remote
        // healer-owned cluster before that minority Roar. If Charge is not
        // ready, legal, or reachable, preserve the existing Roar and movement
        // fallthrough without changing victims or threat.
        uint32 healerOwnedBeforeCharge = densityHealer
            ? uint32(observedListedAttackerCount(densityHealer)) : 0;
        Creature* remoteHealerWaveChargeTarget = nullptr;
        uint32 remoteHealerWaveClusterCount = 0;
        float remoteHealerWaveDistance =
            std::numeric_limits<float>::max();
        uint32 remoteHealerWaveGuid = std::numeric_limits<uint32>::max();
        if (!feralChargePickupInFlight && !feralHealerHandoffActive
            && role == "tank" && profile.SpecTag == "feral_druid_tank"
            && densityHealer && healerOwnedBeforeCharge >= 1
            && localHealerOwnedBeforeCharge * 2 < healerOwnedBeforeCharge)
            for (Creature* candidate : localAdds)
            {
                if (!candidate || candidate->GetVictim() != densityHealer
                    || bot->GetExactDist(candidate) <= 8.0f)
                    continue;
                uint32 clusterCount = 0;
                for (Creature* neighbor : localAdds)
                    if (neighbor && neighbor->GetVictim() == densityHealer
                        && candidate->GetExactDist2d(neighbor) <= 10.0f)
                        ++clusterCount;
                float distance = bot->GetExactDist(candidate);
                uint32 guid = candidate->GetGUID().GetCounter();
                if (!remoteHealerWaveChargeTarget
                    || clusterCount > remoteHealerWaveClusterCount
                    || (clusterCount == remoteHealerWaveClusterCount
                        && (distance < remoteHealerWaveDistance
                            || (distance == remoteHealerWaveDistance
                                && guid < remoteHealerWaveGuid))))
                {
                    remoteHealerWaveChargeTarget = candidate;
                    remoteHealerWaveClusterCount = clusterCount;
                    remoteHealerWaveDistance = distance;
                    remoteHealerWaveGuid = guid;
                }
            }
        if (remoteHealerWaveChargeTarget && bot->HasSpell(16979)
            && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling()
            && TryCastCombatSpell(bot, remoteHealerWaveChargeTarget, 16979))
        {
            std::string raw = BuildRawJson(bot, remoteHealerWaveChargeTarget);
            std::string semantic = BuildSemanticJson(
                bot, remoteHealerWaveChargeTarget, "dungeon_boss",
                &power, stage, activity);
            RecordEvent(state, bot, "boss_add_density",
                remoteHealerWaveChargeTarget,
                "feral_charge_remote_healer_wave_before_roar",
                raw.c_str(), semantic.c_str(), remoteHealerWaveDistance,
                float(healerOwnedBeforeCharge), 16979);
            state.FeralChargePickupTargetGuid =
                remoteHealerWaveChargeTarget->GetGUID();
            state.FeralChargePickupUntilMs = NowMs() + 2500;
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
            state.TargetGuid = remoteHealerWaveChargeTarget->GetGUID();
            state.WasInCombat = true;
            target = remoteHealerWaveChargeTarget;
            situation = "dungeon_boss";
            action = "feral_charge_remote_healer_wave_before_roar";
            return true;
        }
        if (localHealerOwnedBeforeCharge >= 2
            && tryFeralRoarPickup(feralHealerHandoffArrived))
            return true;

        // Feral Charge closes the gap before healing threat can retain a newly
        // activated follower wave beyond the acquisition grace. Reserve it for
        // a healer-owned listed add: rerun76 spent the charge on a non-healer
        // precursor, then overlapping Azil waves retained the healer for 5-7
        // seconds while the cooldown recovered.
        Player* feralChargeVictim = add && add->GetVictim()
            ? add->GetVictim()->ToPlayer() : nullptr;
        bool feralChargeProtectsHealer = feralChargeVictim
            && std::string(GetDungeonRole(feralChargeVictim)) == "healer";
        // Keep Charge reserved from low-density non-healer precursors, but do
        // not force a real party-owned follower wave through a three-second
        // melee approach. Rerun101 observed 16-18 engaged Azil followers on a
        // damage dealer with zero healer attackers; ten identities became
        // acquisition-eligible before the unchanged strict area action reached
        // range. Twelve engaged listed adds prove this is the active wave.
        // Rerun125 observed an activated Azil wave grow from 14 to 17 listed
        // adds with no victim, then assign all 19 to the healer in one tick.
        // The existing high-density reservation rejected Charge solely because
        // the selected add did not have a victim yet.  Treat that pre-victim
        // state as the earliest form of the same declared wave; native Charge
        // still owns range, line-of-sight, cooldown, and target legality.
        bool feralChargeProtectsHighDensityParty = engagedAddCount >= 12
            && densityHealer
            && observedListedAttackerCount(densityHealer) == 0;
        // Rerun154 exposed a declared 20-follower wave whose selected density
        // representative was already inside the eight-yard Charge exclusion.
        // The remaining remote cluster therefore never reached the existing
        // proactive Charge path and nineteen followers selected the healer.
        // Keep the unchanged wave and native cast gates, but select the nearest
        // deterministic remote non-tank-owned follower when the representative
        // itself cannot close that gap. If none exists, preserve the original
        // representative and fallthrough exactly as before.
        Unit* feralChargeTarget = add;
        if (feralChargeProtectsHighDensityParty
            && (!feralChargeTarget
                || bot->GetExactDist(feralChargeTarget) <= 8.0f))
        {
            Creature* remoteChargeTarget = nullptr;
            float remoteChargeDistance = std::numeric_limits<float>::max();
            uint32 remoteChargeGuid = std::numeric_limits<uint32>::max();
            for (Creature* candidate : localAdds)
            {
                if (!candidate || candidate->GetVictim() == bot
                    || bot->GetExactDist(candidate) <= 8.0f)
                    continue;
                Player* candidateVictim = candidate->GetVictim()
                    ? candidate->GetVictim()->ToPlayer() : nullptr;
                if (candidateVictim
                    && std::string(GetDungeonRole(candidateVictim)) == "tank")
                    continue;
                float distance = bot->GetExactDist(candidate);
                uint32 guid = candidate->GetGUID().GetCounter();
                if (!remoteChargeTarget || distance < remoteChargeDistance
                    || (distance == remoteChargeDistance
                        && guid < remoteChargeGuid))
                {
                    remoteChargeTarget = candidate;
                    remoteChargeDistance = distance;
                    remoteChargeGuid = guid;
                }
            }
            if (remoteChargeTarget)
                feralChargeTarget = remoteChargeTarget;
        }
        if (role == "tank" && profile.SpecTag == "feral_druid_tank"
            && engagedAddCount >= 3 && feralChargeTarget
            && (feralChargeProtectsHealer
                || feralChargeProtectsHighDensityParty)
            && !feralHealerHandoffActive
            && feralChargeTarget->GetVictim() != bot
            && bot->GetExactDist(feralChargeTarget) > 8.0f
            && bot->HasSpell(16979)
            && TryCastCombatSpell(bot, feralChargeTarget, 16979))
        {
            std::string raw = BuildRawJson(bot, feralChargeTarget);
            std::string semantic = BuildSemanticJson(
                bot, feralChargeTarget, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_add_density", feralChargeTarget,
                "feral_charge_swarm_pickup", raw.c_str(), semantic.c_str(),
                bot->GetExactDist(feralChargeTarget), addCount, 16979);
            state.FeralChargePickupTargetGuid = feralChargeTarget->GetGUID();
            state.FeralChargePickupUntilMs = NowMs() + 2500;
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
            state.TargetGuid = feralChargeTarget->GetGUID();
            state.WasInCombat = true;
            target = feralChargeTarget;
            situation = "dungeon_boss";
            action = "feral_charge_swarm_pickup";
            return true;
        }

        // Charge either proved arrival above or was unavailable/illegal. Only
        // now may the self-centered native pickup consume this decision.
        if (tryFeralRoarPickup(
                feralHealerHandoffArrived || feralChargePickupArrived))
        {
            if (feralChargePickupArrived)
            {
                state.FeralChargePickupTargetGuid.Clear();
                state.FeralChargePickupUntilMs = 0;
            }
            return true;
        }
        // Rerun93 proved that Charge can reach a healer-owned wave while its
        // global cooldown still prevents the native Roar in that exact arrival
        // decision. Clearing the charged GUID here returned the Feral to generic
        // density movement and let a 19-follower wave retain the healer for
        // 4031 ms. Preserve only the original 2.5-second Charge reservation and
        // retry the existing legal Roar at the established lower cadence.
        if (feralChargePickupArrived && densityHealer
            && observedListedAttackerCount(densityHealer) >= 3)
        {
            bot->StopMoving();
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 500);
            std::string raw = BuildRawJson(bot, feralChargePickupTarget);
            std::string semantic = BuildSemanticJson(
                bot, feralChargePickupTarget, "dungeon_boss",
                &power, stage, activity);
            RecordEvent(state, bot, "boss_add_density",
                feralChargePickupTarget,
                "feral_hold_charge_swarm_arrival_for_roar",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(feralChargePickupTarget), addCount);
            state.TargetGuid = feralChargePickupTarget->GetGUID();
            target = feralChargePickupTarget;
            situation = "dungeon_boss";
            action = "feral_hold_charge_swarm_arrival_for_roar";
            return true;
        }
        if (feralHealerHandoffActive && feralHealerHandoffArrived)
        {
            // Rerun86's correct Azil two-cluster handoff missed the hard dwell
            // gate by 19 ms because the ordinary one-second cadence observed
            // the second Roar only after 3019 ms. Retry only this already-bound
            // handoff at the runtime's established 500 ms lower decision bound
            // so the next native GCD boundary can be observed without changing
            // movement, target selection, or spell legality.
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 500);
            std::string raw = BuildRawJson(bot, densityHealer);
            std::string semantic = BuildSemanticJson(
                bot, densityHealer, "dungeon_boss",
                &power, stage, activity);
            RecordEvent(state, bot, "boss_add_density", densityHealer,
                "feral_hold_healer_swarm_handoff_for_roar",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(densityHealer),
                float(observedListedAttackerCount(densityHealer)));
            state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
            target = add;
            situation = "dungeon_boss";
            action = "feral_hold_healer_swarm_handoff_for_roar";
            return true;
        }

        // Once a split wave is down to one healer-owned follower, the Roar
        // resolver is intentionally inactive. Rerun85 let that final follower
        // survive another full decision behind the generic density cycle.
        // Reuse native Growl immediately, matching the existing ordinary-trash
        // single-follower rule.
        if (role == "tank" && profile.SpecTag == "feral_druid_tank"
            && densityHealer
            && observedListedAttackerCount(densityHealer) == 1
            && bot->HasSpell(6795))
        {
            Creature* healerOwnedAdd = nullptr;
            for (Creature* candidate : localAdds)
                if (candidate && candidate->GetVictim() == densityHealer
                    && (!healerOwnedAdd
                        || bot->GetExactDist(candidate)
                            < bot->GetExactDist(healerOwnedAdd)
                        || (bot->GetExactDist(candidate)
                                == bot->GetExactDist(healerOwnedAdd)
                            && candidate->GetGUID().GetCounter()
                                < healerOwnedAdd->GetGUID().GetCounter())))
                    healerOwnedAdd = candidate;
            if (healerOwnedAdd
                && TryCastCombatSpell(bot, healerOwnedAdd, 6795))
            {
                std::string raw = BuildRawJson(bot, healerOwnedAdd);
                std::string semantic = BuildSemanticJson(
                    bot, healerOwnedAdd, "dungeon_boss",
                    &power, stage, activity);
                RecordEvent(state, bot, "boss_add_density", healerOwnedAdd,
                    "feral_growl_lingering_healer_swarm_attacker",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist(healerOwnedAdd), addCount, 6795);
                state.TargetGuid = healerOwnedAdd->GetGUID();
                target = healerOwnedAdd;
                situation = "dungeon_boss";
                action = "feral_growl_lingering_healer_swarm_attacker";
                return true;
            }
            // Rerun188 reduced Azil's final healer-owned wave to one follower,
            // but native Growl was still on cooldown. The unchanged generic
            // area resolver then selected periodic Thrash at 2842 ms; the
            // follower remained healer-owned at the 3094-ms observation and
            // transferred on the next tick. Try one native instant Swipe on
            // that same deterministic follower before preserving the existing
            // movement/profile fallback. Failed range, GCD, power, cooldown,
            // LOS, or target legality changes no state and falls through.
            if (healerOwnedAdd && bot->HasSpell(779)
                && TryCastCombatSpell(bot, healerOwnedAdd, 779))
            {
                std::string raw = BuildRawJson(bot, healerOwnedAdd);
                std::string semantic = BuildSemanticJson(
                    bot, healerOwnedAdd, "dungeon_boss",
                    &power, stage, activity);
                RecordEvent(state, bot, "boss_add_density", healerOwnedAdd,
                    "feral_swipe_lingering_healer_swarm_attacker",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist(healerOwnedAdd), addCount, 779);
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                state.TargetGuid = healerOwnedAdd->GetGUID();
                state.WasInCombat = true;
                target = healerOwnedAdd;
                situation = "dungeon_boss";
                action = "feral_swipe_lingering_healer_swarm_attacker";
                return true;
            }
            // Rerun164 recovered the first of two Azil followers with Growl,
            // then left the generic density fallback bound to that already
            // tank-owned follower while the sole remaining healer attacker
            // aged past the dwell ceiling. On native Growl rejection, bind
            // only the unchanged fallback target to the same deterministic
            // healer-owned follower. Generic movement, profile resolution,
            // spell legality, and threat semantics remain authoritative.
            if (healerOwnedAdd)
            {
                add = healerOwnedAdd;
                sharedFocusValid = false;
            }
        }

        // Rerun66 rejected tightening the stable healer anchor: scripted
        // followers were not centered on the healer, so the Feral spent five
        // decisions moving there and still reached only two followers. For a
        // moderate active wave, reserve one deterministic density representative
        // for at most 2.5 seconds. Rerun67 proved that its first accepted point
        // becomes stale as the healer-owned hostile moves, so revalidate the
        // same GUID's current endpoint on each reserved tick. Larger split waves
        // retain passive preposition/Charge, and hazard movement remains
        // authoritative because it runs before this resolver.
        uint64 activeSwarmPickupNowMs = NowMs();
        bool activeSwarmPickupEligible = role == "tank"
            && profile.SpecTag == "feral_druid_tank"
            && densityHealer
            && observedListedAttackerCount(densityHealer) >= 3
            && observedListedAttackerCount(densityHealer) < 12
            && engagedAddCount >= 3 && addCount <= 24;
        if (!activeSwarmPickupEligible)
        {
            state.FeralActiveSwarmPickupAttempted = false;
            state.FeralActiveSwarmPickupArrived = false;
        }
        bool activeSwarmPickupReserved = activeSwarmPickupEligible
            && state.FeralActiveSwarmPickupUntilMs > activeSwarmPickupNowMs
            && !state.FeralActiveSwarmPickupAnchorGuid.IsEmpty();
        Unit* activeSwarmPickupAnchor = nullptr;
        if (activeSwarmPickupReserved)
        {
            activeSwarmPickupAnchor = ObjectAccessor::GetUnit(
                *bot, state.FeralActiveSwarmPickupAnchorGuid);
            if (!activeSwarmPickupAnchor || !activeSwarmPickupAnchor->IsAlive()
                || activeSwarmPickupAnchor->GetMap() != bot->GetMap()
                || activeSwarmPickupAnchor->GetVictim() != densityHealer)
            {
                state.FeralActiveSwarmPickupAnchorGuid.Clear();
                state.FeralActiveSwarmPickupUntilMs = 0;
                state.FeralActiveSwarmPickupArrived = false;
                activeSwarmPickupReserved = false;
                activeSwarmPickupAnchor = nullptr;
            }
        }
        else if (!state.FeralActiveSwarmPickupAnchorGuid.IsEmpty()
            || state.FeralActiveSwarmPickupUntilMs)
        {
            state.FeralActiveSwarmPickupAnchorGuid.Clear();
            state.FeralActiveSwarmPickupUntilMs = 0;
            state.FeralActiveSwarmPickupArrived = false;
        }

        bool startingActiveSwarmPickup = !activeSwarmPickupReserved
            && activeSwarmPickupEligible
            && !state.FeralActiveSwarmPickupAttempted && add
            && add->GetVictim() == densityHealer
            && !bot->HasUnitState(UNIT_STATE_CASTING)
            && !bot->IsFalling();
        if (startingActiveSwarmPickup)
            activeSwarmPickupAnchor = add;
        if (activeSwarmPickupAnchor
            && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
        {
            if (bot->GetExactDist2d(activeSwarmPickupAnchor)
                <= TankDensityClusterRadius)
            {
                if (startingActiveSwarmPickup)
                {
                    state.FeralActiveSwarmPickupAttempted = true;
                    state.FeralActiveSwarmPickupAnchorGuid =
                        activeSwarmPickupAnchor->GetGUID();
                }
                if (!state.FeralActiveSwarmPickupArrived)
                {
                    state.FeralActiveSwarmPickupArrived = true;
                    state.FeralActiveSwarmPickupUntilMs =
                        activeSwarmPickupNowMs + 1500;
                }
                bot->StopMoving();
                if (tryFeralRoarPickup(true))
                {
                    state.FeralActiveSwarmPickupAnchorGuid.Clear();
                    state.FeralActiveSwarmPickupUntilMs = 0;
                    state.FeralActiveSwarmPickupArrived = false;
                    return true;
                }
                if (state.FeralActiveSwarmPickupUntilMs
                    > activeSwarmPickupNowMs)
                {
                    std::string raw = BuildRawJson(
                        bot, activeSwarmPickupAnchor);
                    std::string semantic = BuildSemanticJson(
                        bot, activeSwarmPickupAnchor, "dungeon_boss",
                        &power, stage, activity);
                    RecordEvent(state, bot, "boss_add_density",
                        activeSwarmPickupAnchor,
                        "feral_hold_bounded_active_swarm_cluster_for_roar",
                        raw.c_str(), semantic.c_str(),
                        bot->GetExactDist2d(activeSwarmPickupAnchor),
                        addCount);
                    state.TargetGuid =
                        activeSwarmPickupAnchor->GetGUID();
                    target = activeSwarmPickupAnchor;
                    situation = "dungeon_boss";
                    action =
                        "hold_bounded_active_swarm_cluster_for_roar";
                    return true;
                }
                state.FeralActiveSwarmPickupAnchorGuid.Clear();
                state.FeralActiveSwarmPickupUntilMs = 0;
                state.FeralActiveSwarmPickupArrived = false;
            }
            else
            {
                bool continuingReservedPickup = activeSwarmPickupReserved;
                bool moved = MoveBotToPoint(state, bot,
                    activeSwarmPickupAnchor->GetPositionX(),
                    activeSwarmPickupAnchor->GetPositionY(),
                    activeSwarmPickupAnchor->GetPositionZ());
                if (moved)
                {
                    if (startingActiveSwarmPickup)
                    {
                        state.FeralActiveSwarmPickupAttempted = true;
                        state.FeralActiveSwarmPickupArrived = false;
                        state.FeralActiveSwarmPickupAnchorGuid =
                            activeSwarmPickupAnchor->GetGUID();
                        state.FeralActiveSwarmPickupUntilMs =
                            activeSwarmPickupNowMs + 2500;
                    }
                    std::string raw = BuildRawJson(bot, activeSwarmPickupAnchor);
                    std::string semantic = BuildSemanticJson(
                        bot, activeSwarmPickupAnchor, "dungeon_boss",
                        &power, stage, activity);
                    RecordEvent(state, bot, "boss_add_density",
                        activeSwarmPickupAnchor,
                        continuingReservedPickup
                            ? "feral_continue_bounded_active_swarm_cluster"
                            : "feral_move_to_bounded_active_swarm_cluster",
                        raw.c_str(), semantic.c_str(),
                        bot->GetExactDist2d(activeSwarmPickupAnchor), addCount);
                    state.TargetGuid = activeSwarmPickupAnchor->GetGUID();
                    target = activeSwarmPickupAnchor;
                    situation = "dungeon_boss";
                    action = continuingReservedPickup
                        ? "continue_bounded_active_swarm_cluster"
                        : "move_to_bounded_active_swarm_cluster";
                    return true;
                }

                state.FeralActiveSwarmPickupAnchorGuid.Clear();
                state.FeralActiveSwarmPickupUntilMs = 0;
                state.FeralActiveSwarmPickupArrived = false;
            }
        }

        // Keep the healer stationary while the Feral closes to its stable
        // pickup anchor. Rerun58 rejected pursuing successive remote clusters:
        // it did not clear the role gates and lost the prior death-free result.
        if (role == "tank" && profile.SpecTag == "feral_druid_tank"
            && !feralChargePickupArrived && densityDefenseTarget
            && std::string(GetDungeonRole(densityDefenseTarget)) == "healer"
            && observedListedAttackerCount(densityDefenseTarget) >= 3
            && bot->GetExactDist2d(densityDefenseTarget) > 6.0f
            && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
        {
            constexpr float anchorDestinationEpsilon = 0.1f;
            bool continuingAnchorPath = state.ActivePathValid && state.IsMoving
                && std::fabs(state.ActivePathToX - densityDefenseTarget->GetPositionX())
                    <= anchorDestinationEpsilon
                && std::fabs(state.ActivePathToY - densityDefenseTarget->GetPositionY())
                    <= anchorDestinationEpsilon
                && std::fabs(state.ActivePathToZ - densityDefenseTarget->GetPositionZ())
                    <= anchorDestinationEpsilon;
            bool moved = MoveBotToPoint(state, bot,
                densityDefenseTarget->GetPositionX(),
                densityDefenseTarget->GetPositionY(),
                densityDefenseTarget->GetPositionZ());
            std::string raw = BuildRawJson(bot, densityDefenseTarget);
            std::string semantic = BuildSemanticJson(
                bot, densityDefenseTarget, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_add_density", densityDefenseTarget,
                continuingAnchorPath
                    ? "feral_continue_to_stationary_healer_swarm_pickup"
                    : (moved ? "feral_move_to_stationary_healer_swarm_pickup"
                             : "feral_stationary_healer_swarm_pickup_path_rejected"),
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(densityDefenseTarget),
                float(observedListedAttackerCount(densityDefenseTarget)));
            state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
            target = add;
            situation = "dungeon_boss";
            action = continuingAnchorPath
                ? "continue_to_stationary_healer_swarm_pickup"
                : (moved ? "move_to_stationary_healer_swarm_pickup"
                         : "hold_stationary_healer_swarm_pickup");
            return true;
        }

        bool hunterAoeTransferReady = true;
        bool hunterAoeResourceReady = true;
        float hunterAoeMinRange = 5.0f;
        static constexpr float HunterAoeMinRangeSafety = 3.0f;
        static constexpr float HunterAoeMaxRange = 35.0f;
        if (bot->getClass() == CLASS_HUNTER && addCount >= 2)
        {
            // Cataclysm Multi-Shot costs 40 focus. CalcPowerCost can report
            // zero here because the spell's focus cost is supplied through a
            // secondary effect in this client data, while candidate building
            // correctly rejects it as insufficient_resource. Use the actual
            // gameplay threshold so the gate agrees with the cast validator.
            hunterAoeResourceReady = add && bot->HasSpell(2643)
                && bot->GetPower(POWER_FOCUS) >= 40;
            if (add)
                if (SpellInfo const* multiShot = sSpellMgr->GetSpellInfo(2643))
                {
                    float spellMinRange = bot->GetSpellMinRangeForTarget(add, multiShot);
                    if (multiShot->RangeEntry && (multiShot->RangeEntry->Flags & SPELL_RANGE_RANGED))
                        spellMinRange += bot->GetMeleeRange(add);
                    hunterAoeMinRange = std::max(hunterAoeMinRange, spellMinRange);
                }
            // Keep a bounded buffer above the strict minimum. The selected add
            // can close distance between movement completion and CastSpell.
            hunterAoeMinRange = std::min(HunterAoeMaxRange - 1.0f,
                hunterAoeMinRange + HunterAoeMinRangeSafety);
            hunterAoeTransferReady = hunterAoeResourceReady
                && bot->GetExactDist(add) >= hunterAoeMinRange
                && bot->GetExactDist(add) <= HunterAoeMaxRange
                && bot->IsWithinLOSInMap(add);
        }

        if (bot->getClass() == CLASS_HUNTER && densityTank && densityTank != bot
            && addCount >= 2 && hunterAoeResourceReady && !hunterAoeTransferReady
            && !bot->HasAura(34477))
        {
            ResolvedCombatAction rangeAction;
            rangeAction.MovementDirective = "ranged";
            rangeAction.AutoAttackMode = "ranged";
            rangeAction.MinRange = hunterAoeMinRange;
            rangeAction.MaxRange = HunterAoeMaxRange;
            bool moved = MoveBotToProfileRange(state, bot, add, &rangeAction);
            state.TargetGuid = add->GetGUID();
            target = add;
            situation = "dungeon_boss";
            action = moved ? "move_to_misdirection_aoe_range" : "hold_misdirection_aoe_range";
            return true;
        }

        // Rerun60 proved that an in-range Multi-Shot transfers a fresh wave
        // inside the acquisition grace, but an overlapping wave can activate
        // after the short Misdirection aura ends while its ordinary cooldown
        // remains. Marksmanship already provisions native Readiness; select it
        // only for an active healer-owned swarm and let the registered spell
        // script perform its normal Hunter cooldown reset.
        bool hunterMisdirectionActive = bot->getClass() == CLASS_HUNTER
            && (bot->HasAura(34477) || bot->HasAura(35079));
        SpellInfo const* misdirectionInfo = sSpellMgr->GetSpellInfo(34477);
        if (bot->getClass() == CLASS_HUNTER && densityTank && densityTank != bot
            && densityHealer && observedListedAttackerCount(densityHealer) >= 3
            && addCount >= 3 && !hunterMisdirectionActive
            && misdirectionInfo
            && !bot->GetSpellHistory()->IsReady(misdirectionInfo)
            && bot->HasSpell(23989)
            && TryCastFriendlySpell(bot, bot, 23989))
        {
            std::string raw = BuildRawJson(bot, add);
            std::string semantic = BuildSemanticJson(
                bot, add, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_adds", add,
                "readiness_for_misdirection_swarm_pickup",
                raw.c_str(), semantic.c_str(),
                float(observedListedAttackerCount(densityHealer)), addCount, 23989);
            state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
            target = add;
            situation = "dungeon_boss";
            action = "readiness_for_misdirection_swarm_pickup";
            return true;
        }

        // Do not start the short Misdirection window until the hunter can pay
        // for its transfer shot. Previously a low-focus hunter activated the
        // aura, then spent most of the window returning no_valid_profile_action
        // while a fresh wave accumulated healing threat.
        if (bot->getClass() == CLASS_HUNTER && densityTank && densityTank != bot
            && hunterAoeTransferReady
            && bot->HasSpell(34477) && !bot->HasAura(34477) && TryCastFriendlySpell(bot, densityTank, 34477))
        {
            std::string raw = BuildRawJson(bot, add);
            std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_adds", add, "misdirection_to_tank", raw.c_str(), semantic.c_str(), float(addCount), 0, 34477);
            state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
            target = add;
            situation = "dungeon_boss";
            action = "misdirection_boss_adds";
            return true;
        }

        // Misdirection is useful for every pull size.  Once it is active, make
        // the transfer attack explicit: use a single-target priority action
        // for one hostile and an area-profile action for two or more.  This
        // prevents an active Misdirection window from being consumed by a
        // low-value single-target filler during an add wave.
        if (hunterMisdirectionActive && addCount >= 2)
        {
            Creature* legalTransferTarget = nullptr;
            uint32 legalTransferCoverage = 0;
            float legalTransferDistance = std::numeric_limits<float>::max();
            uint32 legalTransferGuid = std::numeric_limits<uint32>::max();
            for (Creature* candidate : localAdds)
            {
                if (!candidate)
                    continue;
                float distance = bot->GetExactDist(candidate);
                if (distance < hunterAoeMinRange || distance > HunterAoeMaxRange
                    || !bot->IsWithinLOSInMap(candidate))
                    continue;
                uint32 coverage = 0;
                for (Creature* neighbor : localAdds)
                    if (neighbor && candidate->GetExactDist2d(neighbor)
                        <= TankDensityClusterRadius)
                        ++coverage;
                uint32 guid = candidate->GetGUID().GetCounter();
                if (!legalTransferTarget || coverage > legalTransferCoverage
                    || (coverage == legalTransferCoverage
                        && (distance < legalTransferDistance
                            || (distance == legalTransferDistance
                                && guid < legalTransferGuid))))
                {
                    legalTransferTarget = candidate;
                    legalTransferCoverage = coverage;
                    legalTransferDistance = distance;
                    legalTransferGuid = guid;
                }
            }
            if (legalTransferTarget)
            {
                add = legalTransferTarget;
                sharedFocusValid = false;
            }
        }
        if (hunterMisdirectionActive && densityTank && add)
        {
            bool useAreaTransfer = addCount >= 2;
            if (useAreaTransfer && bot->GetPower(POWER_FOCUS) < 40)
            {
                std::string raw = BuildRawJson(bot, add);
                std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
                RecordEvent(state, bot, "boss_adds", add, "misdirection_aoe_wait_for_focus",
                    raw.c_str(), semantic.c_str(), float(bot->GetPower(POWER_FOCUS)), addCount, 2643);
                state.TargetGuid = add->GetGUID();
                target = add;
                situation = "dungeon_boss";
                action = "misdirection_aoe_wait_for_focus";
                return true;
            }
            if (useAreaTransfer && (bot->GetExactDist(add) < hunterAoeMinRange
                || bot->GetExactDist(add) > HunterAoeMaxRange
                || !bot->IsWithinLOSInMap(add)))
            {
                ResolvedCombatAction rangeAction;
                rangeAction.MovementDirective = "ranged";
                rangeAction.AutoAttackMode = "ranged";
                rangeAction.MinRange = hunterAoeMinRange;
                rangeAction.MaxRange = HunterAoeMaxRange;
                bool moved = MoveBotToProfileRange(state, bot, add, &rangeAction);
                state.TargetGuid = add->GetGUID();
                target = add;
                situation = "dungeon_boss";
                action = moved ? "move_to_misdirection_aoe_range" : "hold_misdirection_aoe_range";
                return true;
            }
            // Cobra Shot and the configured ground-target AoE require the bot
            // to be stationary. Clear residual route movement once it is in a
            // legal ranged band so the active transfer window produces an
            // attack instead of repeated movement-gate rejections.
            if (useAreaTransfer && bot->isMoving()
                && bot->GetExactDist(add) >= hunterAoeMinRange
                && bot->GetExactDist(add) <= HunterAoeMaxRange
                && bot->IsWithinLOSInMap(add))
                bot->StopMoving();
            ResolvedCombatAction transferAction;
            BotActionResult result = BotActionResult::NoAction;
            if (useAreaTransfer)
            {
                // Do not allow the density resolver to fall back to Cobra Shot
                // during an active AoE Misdirection window. The transfer cast
                // must itself be an area attack.
                transferAction.Valid = true;
                transferAction.Type = "cast";
                transferAction.SpellId = 2643;
                transferAction.TargetGuid = add->GetGUID();
                transferAction.DebugName = "cleave";
                transferAction.MovementDirective = "ranged";
                transferAction.AutoAttackMode = "ranged";
                transferAction.MinRange = hunterAoeMinRange;
                transferAction.MaxRange = HunterAoeMaxRange;
                BotActionExecutor executor;
                result = executor.ExecuteCombat(bot, bot, transferAction);
                std::string castFailureReason;
                if (result == BotActionResult::CastFailed)
                    castFailureReason = "spell_cast_result_" + std::to_string(executor.LastSpellCastResult());
                RecordCombatAttempt(state, bot, add, "misdirection_aoe_transfer", &transferAction,
                    result, castFailureReason.empty() ? nullptr : castFailureReason.c_str());
            }
            else
            {
                transferAction = ResolveProfileCombatAction(bot, add, 1, false);
                result = ExecuteProfileCombatAction(&state, bot, add, &transferAction, 1, false);
            }
            std::string raw = BuildRawJson(bot, add);
            std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_adds", add,
                useAreaTransfer ? "misdirection_aoe_transfer" : "misdirection_single_target_transfer",
                raw.c_str(), semantic.c_str(), float(addCount), 0,
                result == BotActionResult::Ok ? transferAction.SpellId : 0);
            state.TargetGuid = add->GetGUID();
            state.WasInCombat = true;
            target = add;
            situation = "dungeon_boss";
            action = useAreaTransfer ? "misdirection_aoe_transfer" : "misdirection_single_target_transfer";
            return true;
        }

        // The strict area-only resolver intentionally filters defensives,
        // so protect the tank here before selecting the next area-threat cast.
        // This is proactive at 12+ adds and escalates as health falls without
        // overlapping major native tank cooldowns.
        bool feralDruidTank = profile.SpecTag == "feral_druid_tank";
        bool majorTankDefensiveActive = bot->HasAura(498) || bot->HasAura(31850)
            || bot->HasAura(86150) || bot->HasAura(86659)
            || (feralDruidTank && (bot->HasAura(61336) || bot->HasAura(22812)));
        if (role == "tank" && cohortSwarmActive && addCount >= 12
            && UnitHealthPct(bot) <= 0.90f && !majorTankDefensiveActive
            && (!densityHealer || !observedListedAttackerCount(densityHealer)))
        {
            std::array<uint32, 3> defensiveSpells = feralDruidTank
                ? std::array<uint32, 3>{ 61336, 22812, 0 }
                : (UnitHealthPct(bot) <= 0.50f
                    ? std::array<uint32, 3>{ 86150, 31850, 498 }
                    : (UnitHealthPct(bot) <= 0.75f
                        ? std::array<uint32, 3>{ 31850, 498, 86150 }
                        : std::array<uint32, 3>{ 498, 31850, 86150 }));
            for (uint32 defensiveSpellId : defensiveSpells)
                if (defensiveSpellId && bot->HasSpell(defensiveSpellId)
                    && TryCastFriendlySpell(bot, bot, defensiveSpellId))
                {
                    std::string raw = BuildRawJson(bot, add);
                    std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
                    RecordEvent(state, bot, "defensive", bot, "tank_swarm_defensive",
                        raw.c_str(), semantic.c_str(), UnitHealthPct(bot), addCount, defensiveSpellId);
                    target = add;
                    situation = "dungeon_boss";
                    action = "tank_swarm_defensive";
                    return true;
                }
        }

        // Preserve the next native area-threat cast once the current swarm has
        // secure tank ownership. Also hold while a listed wave is visible but has
        // not activated at swarm density yet. Azil can leave one precursor engaged
        // shortly before activating a full follower wave; spending Death and Decay
        // on that precursor leaves only self-centered threat while the tank crosses
        // the platform. Auto-attacks remain active while this hold is in effect,
        // and any party target or three engaged adds resumes the strict area path.
        bool pendingSwarmActivation = cohortSwarmActive && engagedAddCount < 3;
        // Rerun91 showed that a non-Feral tank can hold indefinitely outside a
        // passive follower cluster while DPS waits for ownership. Select the
        // deterministic ten-yard medoid of the visible listed followers instead,
        // so each tank reaches its existing native area-threat pickup radius on
        // the first active decision. A rejected bounded path falls through to
        // the unchanged resource hold below.
        Creature* passiveSwarmClusterAnchor = nullptr;
        uint32 pendingSwarmPickupCoverage = 0;
        float pendingSwarmPickupDistance = std::numeric_limits<float>::max();
        uint32 pendingSwarmPickupGuid = std::numeric_limits<uint32>::max();
        if (pendingSwarmActivation)
            for (Creature* candidate : localAdds)
            {
                if (!candidate)
                    continue;
                uint32 coverage = 0;
                for (Creature* neighbor : localAdds)
                    if (neighbor && candidate->GetExactDist2d(neighbor)
                        <= TankDensityClusterRadius)
                        ++coverage;
                float distance = bot->GetExactDist(candidate);
                uint32 guid = candidate->GetGUID().GetCounter();
                if (!passiveSwarmClusterAnchor
                    || coverage > pendingSwarmPickupCoverage
                    || (coverage == pendingSwarmPickupCoverage
                        && (distance < pendingSwarmPickupDistance
                            || (distance == pendingSwarmPickupDistance
                                && guid < pendingSwarmPickupGuid))))
                {
                    passiveSwarmClusterAnchor = candidate;
                    pendingSwarmPickupCoverage = coverage;
                    pendingSwarmPickupDistance = distance;
                    pendingSwarmPickupGuid = guid;
                }
            }
        // Rerun174 reached this passive 60-follower wave immediately after a
        // generation-13 tank resurrection. The tank completed its existing
        // medoid preposition alone while the damage roles still alternated
        // between remote add paths and tactical-path rejection. Its native
        // white swing therefore activated all 60 before the party could burn
        // them: one heal flipped 59 followers, Feral recovered ownership, then
        // died after 31 secure-threat holds with only one add dead. Stage only
        // a proven very-large passive wave around the living tank before that
        // unchanged native activation. Smaller waves and every active-wave,
        // threat, spell-legality, hazard, and boss rule remain unchanged.
        // Rerun176 proved the original staging decision was observer-local.
        // The tank and healer saw the passive 60-follower cluster and held for
        // the party, while every damage role remained outside that local view
        // and alternated route/add movement for 192 tank decisions. Reconstruct
        // the same declared-wave cardinality from the living tank's view so all
        // party members agree on the staging gate. This changes neither the
        // listed-add contract nor activation: only the tank still selects the
        // medoid and submits the native white swing after all members arrive.
        uint32 tankVisiblePassiveSwarmAddCount = 0;
        uint32 tankVisiblePassiveSwarmEngagedCount = 0;
        if (densityTank)
        {
            std::vector<WorldObject*> tankVisibleObjects;
            Trinity::AllWorldObjectsInRange tankVisibleCheck(
                densityTank, 45.0f);
            Trinity::WorldObjectListSearcher<
                Trinity::AllWorldObjectsInRange> tankVisibleSearcher(
                    densityTank, tankVisibleObjects, tankVisibleCheck);
            Cell::VisitAllObjects(
                densityTank, tankVisibleSearcher, 45.0f);
            for (WorldObject* object : tankVisibleObjects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                if (!isUsableListedAdd(densityTank, creature)
                    || !densityTank->IsWithinLOSInMap(creature))
                    continue;
                ++tankVisiblePassiveSwarmAddCount;
                if (creature->GetVictim())
                    ++tankVisiblePassiveSwarmEngagedCount;
            }
        }
        bool tankViewProvesLargePassiveSwarm = cohortSwarmActive && densityTank
            && tankVisiblePassiveSwarmEngagedCount == 0
            && tankVisiblePassiveSwarmAddCount >= 24;
        // Rerun178 proved that recomputing the tank-visible staging fact in
        // every bot's handler was still observer-dependent. The tank held the
        // passive 60-follower wave for 192 decisions, while all three damage
        // roles remained 69-87 yards from the route anchor and alternated
        // remote add/route paths behind the rerun170 pre-anchor bypass. Publish
        // only the living tank's proven passive-wave observation as a
        // generation-scoped party fact. The bypass remains unchanged until
        // that proof exists, and native activation remains tank-only below.
        if (role == "tank" && tankViewProvesLargePassiveSwarm)
        {
            Party().ValidationRouteLargePassiveSwarmStaging = true;
            Party().ValidationRouteLargePassiveSwarmStagingGeneration =
                Party().ValidationRouteGeneration;
        }
        else if (!densityTank && sharedLargePassiveSwarmStaging)
        {
            Party().ValidationRouteLargePassiveSwarmStaging = false;
            Party().ValidationRouteLargePassiveSwarmStagingGeneration = 0;
        }
        sharedLargePassiveSwarmStaging =
            Party().ValidationRouteLargePassiveSwarmStaging
            && Party().ValidationRouteLargePassiveSwarmStagingGeneration
                == Party().ValidationRouteGeneration;
        // Rerun182 proved the generation-scoped tank observation was not yet
        // fully authoritative. Remote damage roles still required their own
        // local cohortSwarmActive view, so they alternated staging with passive
        // add or route movement as that view changed. Once the living tank has
        // published the existing 24-plus proof, use that shared fact as the
        // cardinality authority for every member. The proof is still created
        // only from the tank's unchanged unengaged 45-yard observation and is
        // reset with the route generation below.
        bool largePassiveSwarm = densityTank
            && sharedLargePassiveSwarmStaging;
        Unit* largePassiveSwarmEvidenceTarget = passiveSwarmClusterAnchor
            ? static_cast<Unit*>(passiveSwarmClusterAnchor)
            : static_cast<Unit*>(densityTank);
        bool largePassiveSwarmPartyStaged = !largePassiveSwarm;
        uint32 largePassiveSwarmLoadedParticipants = 0;
        uint32 largePassiveSwarmStagedParticipants = 0;
        if (largePassiveSwarm)
        {
            for (WorldBotState const& cohortState : Party().Bots)
            {
                Player* member = GetLoadedBot(cohortState);
                if (!member)
                    continue;
                if (!member->IsAlive() || member->GetMap() != bot->GetMap()
                    || member->GetGroup() != bot->GetGroup()
                    || !IsValidationCohortMemberInOriginalInstance(
                        cohortState, member))
                    continue;
                ++largePassiveSwarmLoadedParticipants;
                if (member->GetExactDist2d(densityTank) <= 18.0f)
                    ++largePassiveSwarmStagedParticipants;
            }
            largePassiveSwarmPartyStaged =
                largePassiveSwarmLoadedParticipants > 0
                && largePassiveSwarmStagedParticipants
                    == largePassiveSwarmLoadedParticipants
                && (!Cohort().Config.TargetPopulation
                    || largePassiveSwarmLoadedParticipants
                        >= Cohort().Config.TargetPopulation);
        }
        if (largePassiveSwarm && role != "tank"
            && !largePassiveSwarmPartyStaged)
        {
            bool alreadyStaged = bot->IsAlive()
                && bot->GetExactDist2d(densityTank) <= 18.0f;
            bool moved = false;
            if (!alreadyStaged && !bot->HasUnitState(UNIT_STATE_CASTING)
                && !bot->IsFalling())
            {
                bool meleeProfile = profile.MovementDirective == "melee"
                    || (profile.MaxRange > 0.0f && profile.MaxRange <= 5.0f);
                float stagingRadius = role == "healer"
                    ? 4.0f : (meleeProfile ? 6.0f : 12.0f);
                float stagingOffset =
                    (bot->GetGUID().GetCounter() % 5) * 0.30f;
                Unit* stagingReference = passiveSwarmClusterAnchor
                    ? static_cast<Unit*>(passiveSwarmClusterAnchor)
                    : static_cast<Unit*>(bot);
                float stagingAngle = stagingReference->GetAngle(densityTank)
                    - densityTank->GetOrientation() + stagingOffset;
                // Rerun182's remote Hunter terminalized after both fixed
                // staging points rejected, while Retribution repeatedly reset
                // an accepted point path and alternated back to passive adds.
                // Maintain one native follow generator at the same role-specific
                // radius instead. This neither teleports nor forces placement;
                // the ordinary movement generator remains responsible for
                // terrain traversal and the unchanged 18-yard check remains the
                // only staging authority.
                bool followingStagingTank =
                    bot->GetMotionMaster()->GetCurrentMovementGeneratorType()
                        == FOLLOW_MOTION_TYPE
                    && state.ActivePathValid
                    && std::fabs(state.ActivePathToX
                        - densityTank->GetPositionX()) <= 0.1f
                    && std::fabs(state.ActivePathToY
                        - densityTank->GetPositionY()) <= 0.1f
                    && std::fabs(state.ActivePathToZ
                        - densityTank->GetPositionZ()) <= 0.1f;
                if (!followingStagingTank)
                {
                    state.ActivePathFromX = bot->GetPositionX();
                    state.ActivePathFromY = bot->GetPositionY();
                    state.ActivePathFromZ = bot->GetPositionZ();
                    state.ActivePathToX = densityTank->GetPositionX();
                    state.ActivePathToY = densityTank->GetPositionY();
                    state.ActivePathToZ = densityTank->GetPositionZ();
                    state.ActivePathValid = true;
                    state.LastPathRejectReason.clear();
                    state.LastPathChangeMs = NowMs();
                    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                    bot->GetMotionMaster()->MoveFollow(
                        densityTank, stagingRadius, stagingAngle);
                }
                moved = true;
            }
            else if (alreadyStaged && bot->isMoving())
                bot->StopMoving();

            std::string raw = BuildRawJson(
                bot, largePassiveSwarmEvidenceTarget);
            std::string semantic = BuildSemanticJson(
                bot, largePassiveSwarmEvidenceTarget, "dungeon_boss",
                &power, stage, activity);
            char const* stagingAction = moved
                ? "stage_for_large_passive_swarm_activation"
                : "hold_for_large_passive_swarm_activation";
            RecordEvent(state, bot, "boss_add_density",
                largePassiveSwarmEvidenceTarget, stagingAction,
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(densityTank),
                largePassiveSwarmStagedParticipants);
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
            state.TargetGuid = largePassiveSwarmEvidenceTarget->GetGUID();
            target = largePassiveSwarmEvidenceTarget;
            situation = "dungeon_boss";
            action = stagingAction;
            return true;
        }
        if (role == "tank" && pendingSwarmActivation && passiveSwarmClusterAnchor
            && !bot->IsWithinMeleeRange(passiveSwarmClusterAnchor)
            && (bot->GetExactDist2d(passiveSwarmClusterAnchor) > 6.0f
                || bot->IsWithinLOSInMap(passiveSwarmClusterAnchor))
            && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
        {
            bool moved = MoveBotToPoint(state, bot,
                passiveSwarmClusterAnchor->GetPositionX(),
                passiveSwarmClusterAnchor->GetPositionY(),
                passiveSwarmClusterAnchor->GetPositionZ());
            if (moved)
            {
                state.TankPendingSwarmPickupAnchorGuid =
                    passiveSwarmClusterAnchor->GetGUID();
                state.TankPendingSwarmPickupUntilMs = NowMs() + 4000;
                state.TankPendingSwarmPickupEngagedHandoff = false;
                std::string raw = BuildRawJson(bot, passiveSwarmClusterAnchor);
                std::string semantic = BuildSemanticJson(
                    bot, passiveSwarmClusterAnchor, "dungeon_boss",
                    &power, stage, activity);
                RecordEvent(state, bot, "boss_add_density",
                    passiveSwarmClusterAnchor,
                    "tank_preposition_for_pending_swarm_pickup",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist2d(passiveSwarmClusterAnchor),
                    pendingSwarmPickupCoverage);
                state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
                target = add;
                situation = "dungeon_boss";
                action = "tank_preposition_for_pending_swarm_pickup";
                return true;
            }
        }
        // Rerun184 activated all 59 staged followers onto the Feral, but the
        // first post-activation density decision still had to enter Bear Form.
        // That spent the opening native GCD, so the healer's first shield
        // overtook the zero-margin white-swing threat before Swipe or Thrash
        // could run. Prepare the unchanged persistent form while the passive
        // wave and party are already staged, then wait only for that form's
        // native GCD before allowing the existing tank-only activation.
        bool feralPassiveSwarmBearFormMissing = role == "tank"
            && profile.SpecTag == "feral_druid_tank"
            && largePassiveSwarm && passiveSwarmClusterAnchor
            && !bot->HasAura(5487);
        if (feralPassiveSwarmBearFormMissing)
            TryEnsurePersistentCombatSetup(
                state, bot, passiveSwarmClusterAnchor);
        SpellInfo const* passiveSwarmBearFormInfo =
            sSpellMgr->GetSpellInfo(5487);
        bool feralPassiveSwarmBearFormGcdPending = role == "tank"
            && profile.SpecTag == "feral_druid_tank"
            && largePassiveSwarm && passiveSwarmClusterAnchor
            && passiveSwarmBearFormInfo
            && bot->GetSpellHistory()->HasGlobalCooldown(
                passiveSwarmBearFormInfo);
        if (feralPassiveSwarmBearFormMissing
            || feralPassiveSwarmBearFormGcdPending)
        {
            char const* preparationAction =
                feralPassiveSwarmBearFormMissing
                    ? "feral_prepare_bear_form_before_passive_swarm_activation"
                    : "feral_hold_bear_form_gcd_before_passive_swarm_activation";
            std::string raw = BuildRawJson(
                bot, passiveSwarmClusterAnchor);
            std::string semantic = BuildSemanticJson(
                bot, passiveSwarmClusterAnchor, "dungeon_boss",
                &power, stage, activity);
            RecordEvent(state, bot, "boss_add_density",
                passiveSwarmClusterAnchor, preparationAction,
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(passiveSwarmClusterAnchor),
                largePassiveSwarmStagedParticipants, 5487);
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
            state.TargetGuid = passiveSwarmClusterAnchor->GetGUID();
            target = passiveSwarmClusterAnchor;
            situation = "dungeon_boss";
            action = preparationAction;
            return true;
        }
        if (role == "tank" && largePassiveSwarm
            && !largePassiveSwarmPartyStaged
            && bot->IsWithinMeleeRange(passiveSwarmClusterAnchor)
            && bot->IsWithinLOSInMap(passiveSwarmClusterAnchor))
        {
            if (bot->isMoving())
                bot->StopMoving();
            std::string raw = BuildRawJson(
                bot, passiveSwarmClusterAnchor);
            std::string semantic = BuildSemanticJson(
                bot, passiveSwarmClusterAnchor, "dungeon_boss",
                &power, stage, activity);
            RecordEvent(state, bot, "boss_add_density",
                passiveSwarmClusterAnchor,
                "hold_large_passive_swarm_for_party_staging",
                raw.c_str(), semantic.c_str(),
                float(largePassiveSwarmStagedParticipants),
                largePassiveSwarmLoadedParticipants);
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
            state.TargetGuid = passiveSwarmClusterAnchor->GetGUID();
            target = passiveSwarmClusterAnchor;
            situation = "dungeon_boss";
            action = "hold_large_passive_swarm_for_party_staging";
            return true;
        }
        // A fully passive Azil follower set can remain visible after the tank
        // reaches its reserved pickup anchor. Visibility keeps the swarm gate
        // active, but with no engaged follower the tank resource hold and DPS
        // ownership wait otherwise have no actor capable of starting the wave.
        // Initiate only the tank's native white swing; the existing area spell
        // remains reserved for the activated wave and every DPS threat gate is
        // unchanged.
        if (role == "tank" && pendingSwarmActivation
            && engagedAddCount == 0 && passiveSwarmClusterAnchor
            && largePassiveSwarmPartyStaged
            && bot->IsWithinMeleeRange(passiveSwarmClusterAnchor)
            && bot->IsWithinLOSInMap(passiveSwarmClusterAnchor))
        {
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::StartOrSwitch,
                passiveSwarmClusterAnchor->GetGUID(),
                BotMeleeAutoAttack::Owner::Threat,
                BotActionArbitration::Priority::ThreatControl,
                "tank_activate_passive_swarm");
            BotActionResult activationResult =
                bot->GetVictim() == passiveSwarmClusterAnchor
                ? BotActionResult::Ok : BotActionResult::NoAction;
            if (activationResult == BotActionResult::Ok)
            {
                std::string raw = BuildRawJson(bot, passiveSwarmClusterAnchor);
                std::string semantic = BuildSemanticJson(
                    bot, passiveSwarmClusterAnchor, "dungeon_boss",
                    &power, stage, activity);
                RecordEvent(state, bot, "boss_add_density",
                    passiveSwarmClusterAnchor,
                    "tank_activate_passive_swarm",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist2d(passiveSwarmClusterAnchor),
                    pendingSwarmPickupCoverage);
                state.TargetGuid = passiveSwarmClusterAnchor->GetGUID();
                state.WasInCombat = true;
                target = passiveSwarmClusterAnchor;
                situation = "dungeon_boss";
                action = "tank_activate_passive_swarm";
                return true;
            }
        }
        // Rerun153 reached the passive anchor but had no line of sight. The
        // native Attack request returned Ok without establishing a victim,
        // then this resource hold suppressed the existing boss/route fallback
        // for 71 consecutive decisions. A non-visible anchor is not actionable
        // activation evidence; fall through without spending the reserved area
        // spell so ordinary route control can reacquire a reachable target.
        // Rerun158 proved that the six-yard approximation can still be outside
        // the engine's actual melee envelope: ExecuteCombat returned Ok for 150
        // white-swing submissions without combat, a victim, or melee-auto
        // uptime. Only an anchor in native melee range and line of sight may
        // suppress the existing route fallback after bounded prepositioning.
        bool passiveSwarmActivationNotActionable = pendingSwarmActivation
            && passiveSwarmClusterAnchor
            && (!bot->IsWithinMeleeRange(passiveSwarmClusterAnchor)
                || !bot->IsWithinLOSInMap(passiveSwarmClusterAnchor));
        if (role == "tank" && cohortSwarmActive && !densityDefenseTarget
            && (densityTankOwnsSecureMajority
                || (pendingSwarmActivation
                    && !passiveSwarmActivationNotActionable)))
        {
            char const* holdAction = pendingSwarmActivation
                ? "hold_pending_swarm_area_threat_resources"
                : "hold_secure_area_threat_resources";
            std::string raw = BuildRawJson(bot, add);
            std::string semantic = BuildSemanticJson(
                bot, add, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_add_density", add,
                holdAction, raw.c_str(), semantic.c_str(),
                float(engagedAddCount), addCount);
            state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
            target = add;
            situation = "dungeon_boss";
            action = holdAction;
            return true;
        }

        // A moving swarm can select a different representative attacker every
        // decision tick. Replacing the path for each target change prevented a
        // melee tank from reaching an otherwise stable density cluster.
        // Keep one destination briefly, then repath to the current explicit
        // victim cluster so a stale but still nearby endpoint cannot own an
        // unbounded approach.
        auto continueStableTankSwarmApproach = [&](Unit* selectedAdd) -> bool
        {
            return ContinueStableTankSwarmApproach(state, selectedAdd,
                densityHealer, role, profile, cohortSwarmActive,
                TankDensityClusterRadius);
        };

        // Rerun210's maximum-dwell identity was the one survivor after
        // Thunder Clap acquired the rest of an eleven-follower healer wave.
        // A newer, larger damage-role cluster then won density selection for
        // the next nine seconds, so the Warrior never submitted its ready
        // single-target Taunt against that residual healer threat.  Preserve
        // density priority for the larger damage-role swarm, but peel only a
        // bounded one- or two-attacker healer remainder first with the
        // Warrior's existing native Taunt. Rerun211 proved the same remainder
        // can itself be the selected defense target after a recovery; it must
        // receive the identical Taunt instead of falling through to density
        // holds. Lowest GUID is the deterministic oldest-spawn tie-breaker;
        // all cooldown, range, LOS, target, stance, and spell-legality gates
        // remain native.
        size_t warriorHealerAttackerCount = densityHealer
            ? observedListedAttackerCount(densityHealer) : 0;
        Creature* warriorResidualHealerAdd = nullptr;
        uint32 warriorResidualHealerGuid =
            std::numeric_limits<uint32>::max();
        if (role == "tank" && profile.SpecTag == "protection_warrior"
            && densityHealer && warriorHealerAttackerCount > 0
            && warriorHealerAttackerCount < 3)
        {
            for (Creature* candidate : localAdds)
            {
                if (!candidate || candidate->GetVictim() != densityHealer)
                    continue;
                uint32 guid = candidate->GetGUID().GetCounter();
                if (!warriorResidualHealerAdd
                    || guid < warriorResidualHealerGuid)
                {
                    warriorResidualHealerAdd = candidate;
                    warriorResidualHealerGuid = guid;
                }
            }
            if (warriorResidualHealerAdd && bot->HasSpell(355)
                && TryCastCombatSpell(bot, warriorResidualHealerAdd, 355))
            {
                std::string raw = BuildRawJson(
                    bot, warriorResidualHealerAdd);
                std::string semantic = BuildSemanticJson(
                    bot, warriorResidualHealerAdd, "dungeon_boss", &power,
                    stage, activity);
                RecordEvent(state, bot, "boss_adds",
                    warriorResidualHealerAdd,
                    "warrior_taunt_residual_healer_threat", raw.c_str(),
                    semantic.c_str(),
                    bot->GetExactDist(warriorResidualHealerAdd),
                    float(warriorHealerAttackerCount), 355);
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                state.TargetGuid = warriorResidualHealerAdd->GetGUID();
                state.WasInCombat = true;
                target = warriorResidualHealerAdd;
                situation = "dungeon_boss";
                action = "warrior_taunt_residual_healer_threat";
                return true;
            }
        }

        // Rerun209's generation-14 maximum dwell began with fifteen Azil
        // followers on the Restoration Druid while Protection Warrior was
        // outside Thunder Clap range.  The tank spent six seconds on ordinary
        // ground approach and one single-target Taunt; the first native Thunder
        // Clap then acquired almost the complete wave immediately.  Use the
        // Warrior's already-known native Charge against the deterministic
        // healer-owned density representative before area-profile movement.
        // A successful Charge keeps the ordinary one-second decision interval
        // so its native movement can finish before Thunder Clap resolution.
        // Native range, LOS, cooldown, stance, combat, GCD, power, and spell
        // legality remain authoritative.  Rejection falls through unchanged,
        // but polls this exact urgent healer handoff at the established 250 ms
        // pickup cadence.
        if (role == "tank" && profile.SpecTag == "protection_warrior"
            && densityHealer && densityDefenseTarget == densityHealer
            && add && add->GetVictim() == densityHealer
            && warriorHealerAttackerCount >= 3
            && bot->GetExactDist(add) > 8.0f && bot->HasSpell(100))
        {
            if (TryCastCombatSpell(bot, add, 100))
            {
                std::string raw = BuildRawJson(bot, add);
                std::string semantic = BuildSemanticJson(
                    bot, add, "dungeon_boss", &power, stage, activity);
                RecordEvent(state, bot, "boss_add_density", add,
                    "warrior_charge_healer_swarm_pickup", raw.c_str(),
                    semantic.c_str(), bot->GetExactDist(add), addCount, 100);
                state.TargetGuid = add->GetGUID();
                state.WasInCombat = true;
                target = add;
                situation = "dungeon_boss";
                action = "warrior_charge_healer_swarm_pickup";
                return true;
            }
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
        }

        // Rerun210 proved the complementary native dead zone.  The densest
        // healer-owned representative could already be below Charge's
        // eight-yard minimum while still outside the melee range required by
        // the Thunder Clap profile.  That path spent up to 3.322 seconds
        // approaching before the first area cast, and new waves could extend
        // the same identity beyond the dwell ceiling.  Shockwave is already
        // known by the provisioned Warrior; the prior 771/771 out-of-range
        // result came from unbounded remote submissions.  Permit it only in
        // this explicit greater-than-five and at-most-ten-yard gap, after the
        // native Charge attempt and before generic area movement.  Native
        // facing, range, LOS, cooldown, GCD, power, and cast legality remain
        // authoritative, and rejection preserves the existing chain.
        if (role == "tank" && profile.SpecTag == "protection_warrior"
            && densityHealer && densityDefenseTarget == densityHealer
            && add && add->GetVictim() == densityHealer
            && warriorHealerAttackerCount >= 3
            && bot->GetExactDist(add) > 5.0f
            && bot->GetExactDist(add) <= 10.0f
            && bot->HasSpell(46968)
            && TryCastCombatSpell(bot, add, 46968))
        {
            std::string raw = BuildRawJson(bot, add);
            std::string semantic = BuildSemanticJson(
                bot, add, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_add_density", add,
                "warrior_shockwave_healer_swarm_gap", raw.c_str(),
                semantic.c_str(), bot->GetExactDist(add),
                float(warriorHealerAttackerCount), 46968);
            state.TargetGuid = add->GetGUID();
            state.WasInCombat = true;
            target = add;
            situation = "dungeon_boss";
            action = "warrior_shockwave_healer_swarm_gap";
            return true;
        }

        // On a multi-target wave, establish area threat before spending
        // decision ticks on individual taunts.  Corborus and Azil can assign
        // a complete spawn burst to healing threat in one tick; alternating
        // Righteous Defense, Hand of Reckoning, and movement allowed the
        // oldest adds to remain on the healer for several seconds.  Use the
        // configured Protection AoE profile immediately and fall through to
        // the rescue tools only while every legal area action is unavailable.
        if (role == "tank" && add && addCount >= 2)
        {
            size_t protectionHealerAttackerCount = densityHealer
                ? observedListedAttackerCount(densityHealer) : 0;
            // Rerun192 showed two distinct Protection starvation paths.  A
            // ready multi-target Righteous Defense acquired a prior nine-add
            // Azil wave within one telemetry tick, but a later wave spent its
            // opening GCD on Consecration first and then could not submit the
            // same native rescue until 3063 ms.  Prefer only that existing
            // multi-target rescue before area-GCD spending while two or more
            // exact hostiles own the healer; every native cooldown, range,
            // target, and spell-legality gate remains authoritative.
            if (profile.SpecTag == "protection" && densityHealer
                && protectionHealerAttackerCount >= 2
                && bot->HasSpell(31789)
                && TryCastFriendlySpell(bot, densityHealer, 31789))
            {
                std::string raw = BuildRawJson(bot, densityHealer);
                std::string semantic = BuildSemanticJson(
                    bot, densityHealer, "dungeon_boss", &power, stage,
                    activity);
                RecordEvent(state, bot, "boss_adds", densityHealer,
                    "righteous_defense_healer_before_area_gcd",
                    raw.c_str(), semantic.c_str(),
                    float(protectionHealerAttackerCount), addCount, 31789);
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                state.TargetGuid = add->GetGUID();
                target = add;
                situation = "dungeon_boss";
                action = "righteous_defense_healer_before_area_gcd";
                return true;
            }
            // Rerun197 captured the complementary native-rescue starvation
            // path. Righteous Defense was unavailable or rejected against a
            // twelve-follower healer wave, Hammer acquired only half of it,
            // and valid area movement then returned on every decision until
            // the existing Hand of Protection emergency below became
            // reachable 6646 ms later. Try that same native defensive before
            // area-GCD work only for the already-established five-attacker
            // emergency. Native aura, target, cooldown, range, and spell
            // legality remain authoritative; rejection falls through to the
            // unchanged area and rescue chain.
            if (profile.SpecTag == "protection" && densityHealer
                && protectionHealerAttackerCount >= 5
                && bot->HasSpell(1022) && !densityHealer->HasAura(1022)
                && TryCastFriendlySpell(bot, densityHealer, 1022))
            {
                std::string raw = BuildRawJson(bot, densityHealer);
                std::string semantic = BuildSemanticJson(
                    bot, densityHealer, "dungeon_boss", &power, stage,
                    activity);
                RecordEvent(state, bot, "external_defensive", densityHealer,
                    "hand_of_protection_healer_before_area_gcd",
                    raw.c_str(), semantic.c_str(),
                    float(protectionHealerAttackerCount), addCount, 1022);
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                state.TargetGuid = add->GetGUID();
                target = add;
                situation = "dungeon_boss";
                action = "hand_of_protection_healer_before_area_gcd";
                return true;
            }
            // Rerun191 captured fifteen Azil followers on the healer while
            // Protection repeatedly preferred remote Hammer/Avenger targets.
            // Holy Wrath was natively ready, but the first local wave spent
            // 7.899 seconds cycling representatives before pickup. When a
            // majority of the healer-owned wave is already inside the tank's
            // ten-yard native area, prefer only configured self-centered area
            // actions. If none passes the unchanged profile and native gates,
            // preserve the ordinary area, rescue, and movement chain.
            uint32 localProtectionHealerOwnedCount = 0;
            if (profile.SpecTag == "protection" && densityHealer)
                for (Creature* candidate : localAdds)
                    if (candidate && candidate->GetVictim() == densityHealer
                        && bot->GetExactDist2d(candidate) <= 10.0f)
                        ++localProtectionHealerOwnedCount;
            bool preferSelfCenteredProtectionArea = profile.SpecTag == "protection"
                && localProtectionHealerOwnedCount >= 2
                && localProtectionHealerOwnedCount * 2
                    >= protectionHealerAttackerCount;
            ResolvedCombatAction immediateAreaThreat = ResolveProfileCombatAction(
                bot, add, addCount, true, reservedAreaSpellId, true,
                preferSelfCenteredProtectionArea);
            if (!immediateAreaThreat.Valid && preferSelfCenteredProtectionArea)
            {
                preferSelfCenteredProtectionArea = false;
                immediateAreaThreat = ResolveProfileCombatAction(
                    bot, add, addCount, true, reservedAreaSpellId, true);
            }
            if (immediateAreaThreat.Valid)
            {
                float engageRange = immediateAreaThreat.MaxRange > 0.0f
                    ? immediateAreaThreat.MaxRange
                    : routeEngageRange(bot, add, immediateAreaThreat.SpellId);
                uint32 selfCenteredTargets = 0;
                if (immediateAreaThreat.TargetGuid == bot->GetGUID())
                    for (Creature* candidate : localAdds)
                        if (candidate && bot->GetExactDist2d(candidate) <= 10.0f)
                            ++selfCenteredTargets;
                // Local adds make self-centered AoE immediately useful only when
                // the selected urgent pickup is also inside its radius. Otherwise
                // move into the loose healer/DPS cluster before casting instead of
                // repeatedly hitting adds the tank already owns.
                //
                // Rerun201 proved one exception already encoded by the resolver:
                // a local majority of the healer-owned Azil wave selected ready
                // self-centered Holy Wrath, but the remote representative add
                // kept this final proximity conjunct false. Righteous Defense and
                // Hand of Reckoning made partial native pickups, Avenger's Shield
                // was on cooldown, and eight movement returns displaced the ready
                // area cast. When the bounded Protection local-majority preference
                // selected a self-centered action, honor that exact topology even
                // if the deterministic representative remains remote. All native
                // action, target-count, cooldown, GCD, power, and spell gates stay
                // inside the existing resolver and executor.
                bool preferredLocalProtectionAreaReady =
                    preferSelfCenteredProtectionArea
                    && immediateAreaThreat.TargetGuid == bot->GetGUID()
                    && selfCenteredTargets >= 2;
                bool selfCenteredAreaReady = immediateAreaThreat.TargetGuid == bot->GetGUID()
                    && selfCenteredTargets >= 2
                    && (preferredLocalProtectionAreaReady
                        || !densityDefenseTarget
                        || bot->GetExactDist2d(add) <= 10.0f);
                bool approach = !selfCenteredAreaReady
                    && (bot->GetExactDist(add) > std::max(5.0f, engageRange - 1.0f)
                        || !bot->IsWithinLOSInMap(add));
                if (approach)
                {
                    // Rerun185 completed Azil but localized 554 healer-target
                    // samples to repeated remote Protection add waves. The
                    // configured self-centered area action was valid, so its
                    // approach returned before the native ranged rescue chain
                    // below could run; the longest wave spent 4617 ms moving
                    // before Consecration and reached 6158 ms of healer dwell.
                    // Only when the selected remote density add is currently
                    // attacking the healer, try the same native Protection
                    // rescue order already established for ordinary trash.
                    // Failed or unavailable casts preserve the existing area
                    // approach exactly, and no threat or victim is assigned.
                    if (profile.SpecTag == "protection" && densityHealer
                        && densityDefenseTarget == densityHealer
                        && add->GetVictim() == densityHealer)
                    {
                        uint32 healerAttackerCount =
                            observedListedAttackerCount(densityHealer);
                        if (bot->HasSpell(31789)
                            && TryCastFriendlySpell(bot, densityHealer, 31789))
                        {
                            std::string raw = BuildRawJson(bot, densityHealer);
                            std::string semantic = BuildSemanticJson(
                                bot, densityHealer, "dungeon_boss", &power,
                                stage, activity);
                            RecordEvent(state, bot, "boss_adds", densityHealer,
                                "righteous_defense_healer_before_area_approach",
                                raw.c_str(), semantic.c_str(),
                                float(healerAttackerCount), addCount, 31789);
                            state.DecisionTimer = std::min<uint32>(
                                state.DecisionTimer, 250);
                            state.TargetGuid = add->GetGUID();
                            target = add;
                            situation = "dungeon_boss";
                            action = "righteous_defense_healer_before_area_approach";
                            return true;
                        }
                        if (bot->HasSpell(62124)
                            && TryCastCombatSpell(bot, add, 62124))
                        {
                            std::string raw = BuildRawJson(bot, add);
                            std::string semantic = BuildSemanticJson(
                                bot, add, "dungeon_boss", &power, stage,
                                activity);
                            RecordEvent(state, bot, "boss_adds", add,
                                "hand_of_reckoning_healer_before_area_approach",
                                raw.c_str(), semantic.c_str(),
                                bot->GetExactDist(add),
                                float(healerAttackerCount), 62124);
                            state.DecisionTimer = std::min<uint32>(
                                state.DecisionTimer, 250);
                            state.TargetGuid = add->GetGUID();
                            state.WasInCombat = true;
                            target = add;
                            situation = "dungeon_boss";
                            action = "hand_of_reckoning_healer_before_area_approach";
                            return true;
                        }
                        if (healerAttackerCount >= 2 && bot->HasSpell(31935)
                            && TryCastCombatSpell(bot, add, 31935))
                        {
                            std::string raw = BuildRawJson(bot, add);
                            std::string semantic = BuildSemanticJson(
                                bot, add, "dungeon_boss", &power, stage,
                                activity);
                            RecordEvent(state, bot, "boss_adds", add,
                                "avengers_shield_healer_before_area_approach",
                                raw.c_str(), semantic.c_str(),
                                bot->GetExactDist(add),
                                float(healerAttackerCount), 31935);
                            state.DecisionTimer = std::min<uint32>(
                                state.DecisionTimer, 250);
                            state.TargetGuid = add->GetGUID();
                            state.WasInCombat = true;
                            target = add;
                            situation = "dungeon_boss";
                            action = "avengers_shield_healer_before_area_approach";
                            return true;
                        }
                    }
                    bool continuingStableApproach = continueStableTankSwarmApproach(add);
                    bool moved = continuingStableApproach
                        || MoveBotToProfileRange(state, bot, add, &immediateAreaThreat);
                    char const* moveAction = continuingStableApproach
                        ? "tank_continue_stable_swarm_approach"
                        : (moved ? "tank_move_to_immediate_aoe_threat_range"
                                 : "tank_immediate_aoe_threat_path_rejected");
                    std::string raw = BuildRawJson(bot, add);
                    std::string semantic = BuildSemanticJson(
                        bot, add, "dungeon_boss", &power, stage, activity);
                    RecordEvent(state, bot, "boss_add_density", add,
                        moveAction, raw.c_str(), semantic.c_str(),
                        bot->GetExactDist(add), addCount, immediateAreaThreat.SpellId);
                    state.TargetGuid = add->GetGUID();
                    target = add;
                    situation = "dungeon_boss";
                    action = continuingStableApproach
                        ? "continue_stable_swarm_approach"
                        : (moved ? "move_to_immediate_aoe_threat_range"
                                 : "hold_immediate_aoe_threat_range");
                    return true;
                }

                BotActionResult areaResult = ExecuteProfileCombatAction(
                    &state, bot, add, &immediateAreaThreat, addCount, true,
                    reservedAreaSpellId, true,
                    preferSelfCenteredProtectionArea);
                if (areaResult == BotActionResult::Ok)
                {
                    std::string raw = BuildRawJson(bot, add);
                    std::string semantic = BuildSemanticJson(
                        bot, add, "dungeon_boss", &power, stage, activity);
                    RecordEvent(state, bot, "boss_add_density", add,
                        "tank_immediate_aoe_threat", raw.c_str(), semantic.c_str(),
                        float(addCount), densityHealer
                            ? float(observedListedAttackerCount(densityHealer)) : 0.0f,
                        immediateAreaThreat.SpellId);
                    state.TargetGuid = add->GetGUID();
                    state.WasInCombat = true;
                    target = add;
                    situation = "dungeon_boss";
                    action = "tank_immediate_aoe_threat";
                    return true;
                }
            }
        }

        if (role == "tank" && densityHealer
            && observedListedAttackerCount(densityHealer) >= 5
            && bot->HasSpell(1022) && !densityHealer->HasAura(1022)
            && TryCastFriendlySpell(bot, densityHealer, 1022))
        {
            std::string raw = BuildRawJson(bot, densityHealer);
            std::string semantic = BuildSemanticJson(bot, densityHealer, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "external_defensive", densityHealer, "hand_of_protection_healer_emergency",
                raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(densityHealer)), addCount, 1022);
            target = add;
            situation = "dungeon_boss";
            action = "hand_of_protection_healer_emergency";
            return true;
        }

        if (role == "tank" && densityDefenseTarget
            && bot->HasSpell(31789) && TryCastFriendlySpell(bot, densityDefenseTarget, 31789))
        {
            bool healerPickup = densityDefenseTarget == densityHealer;
            char const* pickupAction = healerPickup ? "righteous_defense_healer_pickup" : "righteous_defense_party_pickup";
            std::string raw = BuildRawJson(bot, densityDefenseTarget);
            std::string semantic = BuildSemanticJson(bot, densityDefenseTarget, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_adds", densityDefenseTarget, pickupAction,
                raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(densityDefenseTarget)), addCount, 31789);
            target = add;
            situation = "dungeon_boss";
            action = pickupAction;
            return true;
        }

        Player* addVictim = add && add->GetVictim() ? add->GetVictim()->ToPlayer() : nullptr;
        if (role == "tank" && addVictim && addVictim != bot
            && std::string(GetDungeonRole(addVictim)) != "tank"
            && bot->HasSpell(62124) && TryCastCombatSpell(bot, add, 62124))
        {
            std::string raw = BuildRawJson(bot, add);
            std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_adds", add, "hand_of_reckoning_add_pickup",
                raw.c_str(), semantic.c_str(), bot->GetExactDist(add), addCount, 62124);
            state.TargetGuid = add->GetGUID();
            target = add;
            situation = "dungeon_boss";
            action = "hand_of_reckoning_add_pickup";
            return true;
        }

        // Rerun200's only strict role failure was a remote two-follower Azil
        // handoff. No area action resolved while the tank was remote, so the
        // generic profile approached for self-centered Holy Wrath. Once Hand
        // of Reckoning entered range, the native engine rejected three legal
        // submissions with SPELL_FAILED_CANT_DO_THAT_RIGHT_NOW; Righteous
        // Defense recovered the pair at 3576 ms. Reuse the already-configured
        // ranged multi-target rescue immediately after that direct-taunt
        // fallback. Native range, line-of-sight, cooldown, GCD, power, target,
        // and spell-legality checks remain authoritative, and rejection falls
        // through to the unchanged Consecration and profile movement chain.
        if (role == "tank" && profile.SpecTag == "protection"
            && densityHealer && densityDefenseTarget == densityHealer
            && addVictim == densityHealer
            && observedListedAttackerCount(densityHealer) >= 2
            && bot->HasSpell(31935)
            && TryCastCombatSpell(bot, add, 31935))
        {
            std::string raw = BuildRawJson(bot, add);
            std::string semantic = BuildSemanticJson(
                bot, add, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_adds", add,
                "avengers_shield_healer_add_pickup", raw.c_str(),
                semantic.c_str(), bot->GetExactDist(add),
                float(observedListedAttackerCount(densityHealer)), 31935);
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
            state.TargetGuid = add->GetGUID();
            state.WasInCombat = true;
            target = add;
            situation = "dungeon_boss";
            action = "avengers_shield_healer_add_pickup";
            return true;
        }

        if (role == "tank" && densityDefenseTarget
            && bot->GetExactDist2d(densityDefenseTarget) <= 8.0f
            && bot->HasSpell(26573) && TryCastFriendlySpell(bot, bot, 26573))
        {
            bool healerPickup = densityDefenseTarget == densityHealer;
            char const* pickupAction = healerPickup ? "consecration_healer_pickup" : "consecration_party_pickup";
            std::string raw = BuildRawJson(bot, densityDefenseTarget);
            std::string semantic = BuildSemanticJson(bot, densityDefenseTarget, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_adds", densityDefenseTarget, pickupAction,
                raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(densityDefenseTarget)), addCount, 26573);
            target = add;
            situation = "dungeon_boss";
            action = pickupAction;
            return true;
        }

        // Azil can activate an entire follower wave on one damage dealer in a
        // single server tick. The tank normally owns the wave on its next
        // decision, but that interval is enough to kill a cloth or mail DPS.
        // Use each spec's native emergency defensive immediately while normal
        // tank pickup completes; Enhancement needs the earlier threshold
        // because Shamanistic Rage mitigates rather than immunizes.
        size_t swarmDefensiveThreshold = bot->getClass() == CLASS_SHAMAN ? 3 : 5;
        uint32 swarmDefensiveSpellId = bot->getClass() == CLASS_MAGE ? 45438
            : (bot->getClass() == CLASS_HUNTER ? 19263
                : (bot->getClass() == CLASS_SHAMAN ? 30823 : 0));
        if (role == "dps" && cohortSwarmActive
            && observedListedAttackerCount(bot) >= swarmDefensiveThreshold
            && swarmDefensiveSpellId && bot->HasSpell(swarmDefensiveSpellId)
            && !bot->HasAura(swarmDefensiveSpellId)
            && TryCastFriendlySpell(bot, bot, swarmDefensiveSpellId))
        {
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Threat,
                BotActionArbitration::Priority::ThreatControl,
                "swarm_pickup_emergency_defensive");
            std::string raw = BuildRawJson(bot, add);
            std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "defensive", bot, "swarm_pickup_emergency_defensive",
                raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(bot)), addCount,
                swarmDefensiveSpellId);
            state.TargetGuid = densityTank && densityTank->GetVictim()
                ? densityTank->GetVictim()->GetGUID() : (add ? add->GetGUID() : ObjectGuid::Empty);
            target = densityTank && densityTank->GetVictim() ? densityTank->GetVictim() : add;
            situation = "dungeon_boss";
            action = "swarm_pickup_emergency_defensive";
            return true;
        }

        // Do not let the first ranged AoE tick assign an entire newly spawned
        // swarm to a DPS before the tank can act.  Stack an unowned focus into
        // the pickup radius and suppress new threat until that focus transfers.
        if (role == "dps" && densityTank && cohortSwarmActive && add
            && !hunterMisdirectionActive
            && (!dpsSwarmDamageRelease
                || (observedListedAttackerCount(bot) && !botInsideTankPickup)))
        {
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Threat,
                BotActionArbitration::Priority::ThreatControl,
                "dps_wait_for_swarm_tank_ownership");
            if (Pet* pet = bot->GetPet())
                pet->AttackStop();

            if (!bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
            {
                Position pickup = densityTank->GetFirstCollisionPosition(4.0f,
                    add->GetAngle(densityTank) - densityTank->GetOrientation());
                if (bot->GetExactDist2d(pickup.GetPositionX(), pickup.GetPositionY()) > 2.0f
                    && MoveBotToPoint(state, bot, pickup.GetPositionX(), pickup.GetPositionY(), pickup.GetPositionZ()))
                {
                    std::string raw = BuildRawJson(bot, add);
                    std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
                    RecordEvent(state, bot, "boss_adds", add, "dps_stack_for_swarm_pickup",
                        raw.c_str(), semantic.c_str(), bot->GetExactDist2d(densityTank), addCount);
                    state.TargetGuid = densityTank->GetVictim() ? densityTank->GetVictim()->GetGUID() : add->GetGUID();
                    target = densityTank->GetVictim() ? densityTank->GetVictim() : add;
                    situation = "dungeon_boss";
                    action = "dps_stack_for_swarm_pickup";
                    return true;
                }
            }

            Unit* pickupFocus = densityTank->GetVictim() ? densityTank->GetVictim() : add;
            state.TargetGuid = pickupFocus ? pickupFocus->GetGUID() : ObjectGuid::Empty;
            target = pickupFocus;
            std::string raw = BuildRawJson(bot, add);
            std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_adds", add, "dps_wait_for_swarm_tank_ownership",
                raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(bot)), addCount);
            situation = "dungeon_boss";
            action = "dps_wait_for_swarm_tank_ownership";
            return true;
        }

        if (role == "dps" && densityTank && !dpsSwarmDamageRelease && observedListedAttackerCount(bot)
            && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
        {
            Unit* nearestAttacker = nullptr;
            float nearestDistance = std::numeric_limits<float>::max();
            auto considerPickupAttacker = [&](Unit* attacker)
            {
                if (!attacker || !attacker->IsAlive() || attacker->GetMap() != bot->GetMap())
                    return;
                float distance = bot->GetExactDist2d(attacker);
                if (!nearestAttacker || distance < nearestDistance)
                {
                    nearestAttacker = attacker;
                    nearestDistance = distance;
                }
            };
            for (Creature* candidate : localAdds)
                if (candidate && candidate->GetVictim() == bot)
                    considerPickupAttacker(candidate);
            if (!nearestAttacker)
                for (Unit* attacker : bot->getAttackers())
                    considerPickupAttacker(attacker);
            if (nearestAttacker)
            {
                Position pickup = densityTank->GetFirstCollisionPosition(4.0f,
                    nearestAttacker->GetAngle(densityTank) - densityTank->GetOrientation());
                if (bot->GetExactDist2d(pickup.GetPositionX(), pickup.GetPositionY()) > 2.0f
                    && MoveBotToPoint(state, bot, pickup.GetPositionX(), pickup.GetPositionY(), pickup.GetPositionZ()))
                {
                    SubmitMeleeAutoAttackIntent(state,
                        BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                        BotMeleeAutoAttack::Owner::Threat,
                        BotActionArbitration::Priority::ThreatControl,
                        "dps_stack_for_add_pickup");
                    if (Pet* pet = bot->GetPet())
                        pet->AttackStop();
                    std::string raw = BuildRawJson(bot, nearestAttacker);
                    std::string semantic = BuildSemanticJson(bot, nearestAttacker, "dungeon_boss", &power, stage, activity);
                    RecordEvent(state, bot, "boss_adds", nearestAttacker, "dps_stack_for_add_pickup",
                        raw.c_str(), semantic.c_str(), nearestDistance, addCount);
                    Unit* pickupFocus = densityTank->GetVictim() ? densityTank->GetVictim() : add;
                    state.TargetGuid = pickupFocus ? pickupFocus->GetGUID() : ObjectGuid::Empty;
                    target = pickupFocus;
                    situation = "dungeon_boss";
                    action = "dps_stack_for_add_pickup";
                    return true;
                }
            }
        }

        // If the bot is already in pickup range, or its legal path to the tank
        // was rejected above, stop adding threat until ownership transfers.
        if (role == "dps" && densityTank && !dpsSwarmDamageRelease && observedListedAttackerCount(bot))
        {
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Threat,
                BotActionArbitration::Priority::ThreatControl,
                "dps_hold_for_nearby_add_pickup");
            if (Pet* pet = bot->GetPet())
                pet->AttackStop();
            Unit* pickupFocus = densityTank->GetVictim() ? densityTank->GetVictim() : add;
            state.TargetGuid = pickupFocus ? pickupFocus->GetGUID() : ObjectGuid::Empty;
            target = pickupFocus;
            std::string raw = BuildRawJson(bot, add);
            std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_adds", add, "dps_hold_for_nearby_add_pickup",
                raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(bot)), addCount);
            situation = "dungeon_boss";
            action = "dps_hold_for_nearby_add_pickup";
            return true;
        }

        if (role == "tank" && densityHealer
            && observedListedAttackerCount(densityHealer)
            && bot->HasSpell(1038) && !densityHealer->HasAura(1038)
            && TryCastFriendlySpell(bot, densityHealer, 1038))
        {
            std::string raw = BuildRawJson(bot, densityHealer);
            std::string semantic = BuildSemanticJson(bot, densityHealer, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_adds", densityHealer, "hand_of_salvation_healer_threat_drop",
                raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(densityHealer)), addCount, 1038);
            target = add;
            situation = "dungeon_boss";
            action = "hand_of_salvation_healer_threat_drop";
            return true;
        }

        float densityHealerRange = 0.0f;
        if (densityHealer)
        {
            BotClassSpecActionProfile healerProfile = BotClassSpecActionProfileStore::Build(densityHealer, "healer");
            for (BotActionProfileSpell const& spell : healerProfile.Spells)
            {
                if (!spell.SpellId || !densityHealer->HasSpell(spell.SpellId)
                    || (spell.Category != BotCombatActionCategory::HealFast
                        && spell.Category != BotCombatActionCategory::HealEfficient
                        && spell.Category != BotCombatActionCategory::HealAoe))
                    continue;
                float spellRange = spell.MaxRange;
                if (spellRange <= 0.0f)
                    if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spell.SpellId))
                        spellRange = spellInfo->GetMaxRange(true);
                densityHealerRange = std::max(densityHealerRange, spellRange);
            }
        }

        bool escapeCohortValid = densityTank && densityHealer && densityHealerRange > 3.0f;
        if (Party().ValidationRouteBossAddEscapeActive && escapeCohortValid)
        {
            escapeCohortValid = densityTank->GetExactDist(Party().ValidationRouteBossAddEscapeX,
                    Party().ValidationRouteBossAddEscapeY, Party().ValidationRouteBossAddEscapeZ) <= densityHealerRange - 1.0f
                && densityHealer->GetExactDist(Party().ValidationRouteBossAddEscapeX,
                    Party().ValidationRouteBossAddEscapeY, Party().ValidationRouteBossAddEscapeZ) <= densityHealerRange - 1.0f
                && densityTank->IsWithinLOS(Party().ValidationRouteBossAddEscapeX, Party().ValidationRouteBossAddEscapeY, Party().ValidationRouteBossAddEscapeZ)
                && densityHealer->IsWithinLOS(Party().ValidationRouteBossAddEscapeX, Party().ValidationRouteBossAddEscapeY, Party().ValidationRouteBossAddEscapeZ);
        }
        if (Party().ValidationRouteBossAddEscapeActive && !escapeCohortValid)
            ResetValidationRouteBossAddEscapeState();

        if (highDensityPhase && bot == densityTank && addCount >= 3 && !densityDefenseTarget)
        {
            float centroidX = addX / float(addCount);
            float centroidY = addY / float(addCount);
            float centroidDistance = densityTank->GetExactDist2d(centroidX, centroidY);
            if (centroidDistance > 4.0f && !densityTank->HasUnitState(UNIT_STATE_CASTING) && !densityTank->IsFalling())
            {
                Map* map = densityTank->GetMap();
                float centroidZ = densityTank->GetPositionZ();
                if (map)
                {
                    float floorZ = map->GetHeight(densityTank->GetPhaseShift(), centroidX, centroidY, centroidZ + 4.0f, true, 10.0f);
                    if (floorZ > INVALID_HEIGHT && std::fabs(floorZ - centroidZ) <= 10.0f)
                        centroidZ = floorZ;
                }
                bool moved = densityTank->IsWithinLOS(centroidX, centroidY, centroidZ)
                    && MoveBotToPoint(state, densityTank, centroidX, centroidY, centroidZ);
                std::string raw = BuildRawJson(bot, add);
                std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
                RecordEvent(state, bot, "boss_add_density", add,
                    moved ? "tank_move_to_add_centroid" : "tank_add_centroid_path_rejected",
                    raw.c_str(), semantic.c_str(), centroidDistance, addCount);
                state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
                target = add;
                situation = "dungeon_boss";
                action = moved ? "tank_move_to_add_centroid" : "hold_tank_add_centroid";
                return true;
            }
        }

        // Healing at maximum range makes newly spawned adds run away from the
        // tank's Consecration/Hammer radius. Issue one pickup-stack movement,
        // then allow normal instant healing while that path remains active.
        // Exact hazard exits run before this branch and remain authoritative.
        if (highDensityPhase && role == "healer" && densityTank
            && observedListedAttackerCount(bot)
            && UnitHealthPct(bot) > 0.45f && UnitHealthPct(densityTank) > 0.40f
            && bot->GetExactDist2d(densityTank) > 6.0f
            && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling()
            && !(state.ActivePathValid && state.IsMoving))
        {
            Unit* approachFrom = add ? add : densityTank;
            Position pickup = densityTank->GetFirstCollisionPosition(4.0f,
                approachFrom->GetAngle(densityTank) - densityTank->GetOrientation());
            if (MoveBotToPoint(state, bot, pickup.GetPositionX(), pickup.GetPositionY(), pickup.GetPositionZ()))
            {
                std::string raw = BuildRawJson(bot, add);
                std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
                RecordEvent(state, bot, "boss_adds", add, "healer_stack_for_swarm_pickup",
                    raw.c_str(), semantic.c_str(), bot->GetExactDist2d(densityTank), addCount);
                state.TargetGuid = densityTank->GetVictim()
                    ? densityTank->GetVictim()->GetGUID() : (add ? add->GetGUID() : ObjectGuid::Empty);
                target = densityTank->GetVictim() ? densityTank->GetVictim() : add;
                situation = "dungeon_boss";
                action = "healer_stack_for_swarm_pickup";
                return true;
            }
        }

        if (highDensityPhase && role == "healer" && tryRouteGroupHeal(bot, add))
            return true;

        if (highDensityPhase
            && nearbyAddCount >= 3
            && !profile.MissingProfile
            && profile.MovementDirective != "melee"
            && Party().ValidationRouteBossAddEscapeActive
            && Party().ValidationRouteBossAddEscapeGeneration == Party().ValidationRouteGeneration
            && !bot->HasUnitState(UNIT_STATE_CASTING)
            && !bot->IsFalling())
        {
            bool reachedEscape = bot->GetExactDist2d(Party().ValidationRouteBossAddEscapeX, Party().ValidationRouteBossAddEscapeY) <= 2.5f;
            bool escapeIssued = Party().ValidationRouteBossAddEscapeIssuedGuids.find(bot->GetGUID()) != Party().ValidationRouteBossAddEscapeIssuedGuids.end();
            constexpr float escapePathEpsilon = 0.5f;
            bool escapePathPending = state.ActivePathValid
                && state.IsMoving
                && std::fabs(state.ActivePathToX - Party().ValidationRouteBossAddEscapeX) <= escapePathEpsilon
                && std::fabs(state.ActivePathToY - Party().ValidationRouteBossAddEscapeY) <= escapePathEpsilon
                && std::fabs(state.ActivePathToZ - Party().ValidationRouteBossAddEscapeZ) <= escapePathEpsilon;
            bool shouldIssueEscape = !reachedEscape && !escapePathPending;
            if (!reachedEscape && shouldIssueEscape
                && MoveBotToPoint(state, bot, Party().ValidationRouteBossAddEscapeX, Party().ValidationRouteBossAddEscapeY, Party().ValidationRouteBossAddEscapeZ))
            {
                std::string raw = BuildRawJson(bot, add);
                std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
                RecordEvent(state, bot, "boss_add_density", add, escapeIssued ? "reissue_shared_escape_unreached" : "move_to_shared_escape", raw.c_str(), semantic.c_str(), float(nearbyAddCount), addCount);
                Party().ValidationRouteBossAddEscapeIssuedGuids.insert(bot->GetGUID());
                state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
                target = add;
                situation = "dungeon_boss";
                action = "move_to_boss_add_density_escape";
                return true;
            }
            if (!reachedEscape && escapePathPending)
            {
                state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
                target = add;
                situation = "dungeon_boss";
                action = "continue_to_boss_add_density_escape";
                return true;
            }
        }
        if (role == "healer")
            return false;
        if (highDensityPhase && !add && densityApproachAnchor)
        {
            ResolvedCombatAction approachAction;
            approachAction.MovementDirective = profile.MovementDirective;
            approachAction.AutoAttackMode = profile.AutoAttackMode;
            approachAction.MinRange = profile.MinRange;
            approachAction.MaxRange = profile.MaxRange;
            bool moved = MoveBotToProfileRange(state, bot, densityApproachAnchor, &approachAction);
            std::string raw = BuildRawJson(bot, densityApproachAnchor);
            std::string semantic = BuildSemanticJson(bot, densityApproachAnchor, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_add_density", densityApproachAnchor, "approach_density_anchor", raw.c_str(), semantic.c_str(),
                bot->GetExactDist(densityApproachAnchor), addCount);
            state.TargetGuid = densityApproachAnchor->GetGUID();
            target = densityApproachAnchor;
            situation = "dungeon_boss";
            action = moved ? "move_to_density_anchor_range" : "hold_density_anchor_range";
            return true;
        }
        if (!add)
        {
            if (!highDensityPhase)
                return false;

            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_add_density", nullptr, "no_compatible_density_anchor", raw.c_str(), semantic.c_str(), float(addCount));
            state.TargetGuid.Clear();
            target = nullptr;
            situation = "dungeon_boss";
            action = "hold_boss_add_density";
            return true;
        }
        if (!highDensityPhase && !sharedFocusValid)
        {
            Party().ValidationRouteAddFocusGuid = add->GetGUID();
            Party().ValidationRouteAddFocusGeneration = Party().ValidationRouteGeneration;
        }
        if (!bot->IsValidAttackTarget(add))
        {
            std::string raw = BuildRawJson(bot, add);
            std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_adds", add, "hold_unattackable_focus", raw.c_str(), semantic.c_str(), float(addCount));
            state.TargetGuid = add->GetGUID();
            target = add;
            situation = "dungeon_boss";
            action = "hold_boss_add_focus";
            return true;
        }

        // The boss can remain attackable while a complete add wave activates.
        // Tanks must enter their area-threat profile immediately in that case;
        // otherwise they alternate single-target taunts while healing threat
        // assigns most of an Azil follower wave to the healer.  DPS still wait
        // for secure ownership before using their own area profiles.
        bool tankSwarmAreaPhase = role == "tank" && cohortSwarmActive;
        bool secureSwarmAreaPhase = role == "dps" && cohortSwarmActive
            && (dpsSwarmDamageRelease || hunterMisdirectionActive);
        bool densityAreaPhase = highDensityPhase || tankSwarmAreaPhase || secureSwarmAreaPhase;
        ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, add,
            densityAreaPhase ? addCount : 0, densityAreaPhase);
        // A tank with an active scripted swarm must not spend native area
        // resources through the ordinary single-target fallback. In particular,
        // Heart Strike can consume the Blood rune needed by the next Blood Boil
        // after the strict area resolver reports only cooldown/resource gates.
        // The invalid-area branch below preserves auto-attack uptime without
        // consuming that resource, while non-swarm and non-tank fallbacks retain
        // their existing behavior.
        bool preserveTankSwarmAreaResources = role == "tank" && cohortSwarmActive;
        bool densitySingleTargetFallback = densityAreaPhase && !profileAction.Valid
            && !preserveTankSwarmAreaResources;
        if (densitySingleTargetFallback)
            profileAction = ResolveProfileCombatAction(bot, add);
        if (densityAreaPhase && !profileAction.Valid)
        {
            if (role == "tank")
            {
                BotActionResult pull = SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::StartOrSwitch,
                    add->GetGUID(), BotMeleeAutoAttack::Owner::Threat,
                    BotActionArbitration::Priority::ThreatControl,
                    "tank_density_autoattack_fallback")
                        ? BotActionResult::Ok : BotActionResult::NoAction;
                if (pull == BotActionResult::Ok)
                {
                    std::string raw = BuildRawJson(bot, add);
                    std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
                    RecordEvent(state, bot, "boss_add_density", add, "tank_auto_attack_density_fallback",
                        raw.c_str(), semantic.c_str(), float(addCount));
                    state.TargetGuid = add->GetGUID();
                    state.WasInCombat = true;
                    target = add;
                    situation = "dungeon_boss";
                    action = "tank_auto_attack_density_fallback";
                    return true;
                }
            }
            std::string raw = BuildRawJson(bot, add);
            std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
            RecordEvent(state, bot, "boss_add_density", add, "no_legal_density_action", raw.c_str(), semantic.c_str(), float(addCount));
            state.TargetGuid = add->GetGUID();
            target = add;
            situation = "dungeon_boss";
            action = "hold_boss_add_density";
            return true;
        }
        bool densityGenerator = densityAreaPhase && profileAction.DebugName == "resource_generator";
        if (densityAreaPhase)
        {
            std::string raw = BuildRawJson(bot, add);
            std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
            char const* densityActionReason = densitySingleTargetFallback
                ? "single_target_fallback_selected"
                : (densityGenerator ? "resource_generator_selected" : "area_action_selected");
            RecordEvent(state, bot, "boss_add_density", add, densityActionReason, raw.c_str(), semantic.c_str(), float(addCount), 0, profileAction.SpellId);
        }
        uint32 spellId = profileAction.SpellId;
        float engageRange = profileAction.MaxRange > 0.0f ? profileAction.MaxRange : routeEngageRange(bot, add, spellId);
        bool approach = bot->GetExactDist(add) > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(add);
        bool continuingStableApproach = approach && continueStableTankSwarmApproach(add);
        BotActionResult result = BotActionResult::NoAction;
        if (approach && !continuingStableApproach)
            MoveBotToProfileRange(state, bot, add, &profileAction);
        else if (!approach)
        {
            if (densityAreaPhase)
                result = ExecuteProfileCombatAction(&state, bot, add, &profileAction, addCount, true);
            else
            {
                BotActionResult pull = profileAction.AutoAttackMode == "melee"
                    && SubmitMeleeAutoAttackIntent(state,
                        BotMeleeAutoAttack::Kind::StartOrSwitch,
                        add->GetGUID(), BotMeleeAutoAttack::Owner::Profile,
                        BotActionArbitration::Priority::TrainedDamage,
                        "boss_add_melee_engagement")
                            ? BotActionResult::Ok : BotActionResult::NoAction;
                result = ExecuteProfileCombatAction(&state, bot, add, &profileAction);
                if (result == BotActionResult::NoAction)
                    result = pull;
            }
        }

        std::string raw = BuildRawJson(bot, add);
        std::string semantic = BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
        RecordEvent(state, bot, "boss_adds", add,
            continuingStableApproach ? "continue_stable_swarm_approach"
                : (approach ? "approach_target" : ToString(result)),
            raw.c_str(), semantic.c_str(), float(addCount), 0,
            result == BotActionResult::Ok ? spellId : 0);
        state.TargetGuid = add->GetGUID();
        state.WasInCombat = true;
        target = add;
        situation = "dungeon_boss";
        action = continuingStableApproach ? "continue_stable_tank_swarm_approach"
            : (approach ? "move_to_boss_add"
                : (densitySingleTargetFallback ? "focused_attack_boss_add_density"
                    : (densityGenerator ? "generate_resource_boss_add_density"
                        : (densityAreaPhase ? "area_attack_boss_add_density" : "switch_to_boss_add"))));
        return true;
    };
    auto markValidationRouteTerminalAfterProgress = [&](char const* reason) -> void
    {
        MarkValidationRouteTerminalAfterProgress(reason, state, bot, power,
            stage, activity, situation, action, target, routeDistance);
    };
    // A current-generation declared trash pack remains authoritative while
    // its native target is alive, attackable, combat-linked, and the living
    // roster still has a tank plus raid members who can continue.  This gate
    // must precede the generic critical-role/majority-death retreat: that
    // fallback is for a genuinely non-viable composition and must not bypass
    // a live pack or manufacture any recovery state.
    auto currentLiveValidationRoutePackCanContinue = [&]() -> bool
    {
        return CurrentLiveValidationRoutePackCanContinue(
            persistedValidationRoutePackHasLiveMembers,
            isValidationRoutePackEntry, resolvedScriptedTransitionAuraId);
    };
    bool currentLivePackCanContinue = currentLiveValidationRoutePackCanContinue();
    // Refresh discovery-pack membership before any recovery/terminal branch.
    // Active target selection can bypass findTrashClusterThreatTarget once a
    // persisted member exists, so relying on that resolver alone leaves a
    // newly engaged adjacent creature outside the shared pack ledger.
    if (discoveryLeg)
        enrollEngagedValidationRoutePackMembers();
    // If most of the party or a critical role is dead and no living class can
    // legally resurrect in combat, continuing at the abandoned pack cannot
    // recover the group. Retreat through ordinary movement so the hostile
    // exceeds its home leash, then end the survivors' combat references together
    // at the fallback anchor so native out-of-combat resurrection can run.
    if (bot->IsAlive() && bot->GetGroup())
    {
        uint32 aliveMembers = 0;
        uint32 deadMembers = 0;
        bool criticalRoleDead = false;
        bool groupCombatActive = false;
        bool livingCombatResurrectionCaster = false;
        Unit* retreatThreat = nullptr;
        for (GroupReference* itr = bot->GetGroup()->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || member->GetMap() != bot->GetMap())
                continue;
            if (member->IsAlive())
            {
                ++aliveMembers;
                groupCombatActive = groupCombatActive || member->IsInCombat() || member->GetVictim() || !member->getAttackers().empty();
                if (!retreatThreat && std::string(GetDungeonRole(member)) == "tank")
                    retreatThreat = member->GetVictim();
                for (auto const& [spellId, playerSpell] : member->GetSpellMap())
                {
                    if (playerSpell.state == PLAYERSPELL_REMOVED || playerSpell.disabled || !playerSpell.active || !member->HasSpell(spellId))
                        continue;
                    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
                    if (IsNativeCombatResSpell(spellInfo)
                        && member->GetSpellHistory()->IsReady(spellInfo) && HasPowerForSpell(member, spellInfo))
                    {
                        livingCombatResurrectionCaster = true;
                        break;
                    }
                }
            }
            else
            {
                ++deadMembers;
                std::string role = GetDungeonRole(member);
                criticalRoleDead = criticalRoleDead || role == "tank" || role == "healer";
            }
        }
        bool majorityDead = aliveMembers <= 2 && deadMembers >= 3;
        // The Drudge lane contract is a native-mechanics observation, not a
        // recoverable trash route.  Once any exact roster member dies while
        // the pack is active, hold only newly issued bot offense and leave
        // threat, movement, corpses, and reset authority to the encounter.
        // This keeps a four-death tactical retreat from masquerading as a
        // clean lane generation; the native wipe gate will terminate it.
        if (Cohort().Config.ValidationRouteMechanicProfile == "trash_two_tank_charge_lanes"
            && Cohort().Config.ValidationRouteBossRecovery
                == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly
            && deadMembers > 0)
        {
            bool const threatSeedCompleteForCurrentScope =
                Party().ValidationRouteDrudgeThreatSeedComplete
                && !Party().ValidationRouteDrudgeThreatSeedFailure
                && Party().ValidationRouteDrudgeThreatSeedAttemptId == Cohort().AttemptId
                && Party().ValidationRouteDrudgeThreatSeedWipeGeneration
                    == Cohort().Raid.WipeGeneration
                && Party().ValidationRouteDrudgeThreatSeedRouteGeneration
                    == Party().ValidationRouteGeneration;
            if (!threatSeedCompleteForCurrentScope)
            {
                for (WorldBotState const& cohortState : Party().Bots)
                    if (Player* cohortBot = GetLoadedBot(cohortState))
                        BotRaidAreaAuthority::SetAllOffenseSuppressed(
                            cohortBot->GetGUID().GetRawValue(), true);
                Cohort().ValidationAttemptFailureReason =
                    "drudge_partial_death_before_threat_seed";
                Cohort().ValidationAttemptFailureAttemptId = Cohort().AttemptId;
                Cohort().ValidationAttemptFailureRouteGeneration =
                    Party().ValidationRouteGeneration;
                markValidationRouteTrashFailed(retreatThreat,
                    "drudge_partial_death_before_threat_seed",
                    "validation_route_recovery", float(aliveMembers), deadMembers);
                state.LastRecoveryMode = "terminal_restart_required";
                state.LastRecoveryResult = "drudge_partial_death_before_threat_seed";
                state.LastRecoveryMs = NowMs();
                situation = "validation_route_recovery";
                action = "validation_route_failed";
                target = retreatThreat;
                return true;
            }
            if (groupCombatActive)
            {
                for (WorldBotState const& cohortState : Party().Bots)
                    if (Player* cohortBot = GetLoadedBot(cohortState))
                        BotRaidAreaAuthority::SetAllOffenseSuppressed(
                            cohortBot->GetGUID().GetRawValue(), true);
                std::string raw = BuildRawJson(bot, retreatThreat);
                std::ostringstream gateRaw;
                gateRaw << "{\"base\":" << raw
                        << ",\"drudge_native_recovery_gate\":{\"policy\":\"native_full_wipe_only\""
                        << ",\"authority\":\"native_encounter\""
                        << ",\"assistance\":\"none\""
                        << ",\"direct_respawn\":false"
                        << ",\"direct_state_manufacture\":false"
                        << ",\"alive_members\":" << aliveMembers
                        << ",\"dead_members\":" << deadMembers << "}}";
                std::string semantic = BuildSemanticJson(bot, retreatThreat, "validation_route_recovery", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_recovery", retreatThreat,
                    "drudge_native_full_wipe_hold_partial_death", gateRaw.str().c_str(), semantic.c_str(),
                    float(aliveMembers), deadMembers);
                state.LastRecoveryMode = "native_full_wipe_only";
                state.LastRecoveryResult = "drudge_native_full_wipe_hold_partial_death";
                state.LastRecoveryMs = NowMs();
                state.LastNoProgressReason = "drudge_native_full_wipe_hold_partial_death";
                situation = "validation_route_recovery";
                action = "native_full_wipe_hold";
                target = retreatThreat;
                return true;
            }
        }
        if ((majorityDead || criticalRoleDead) && groupCombatActive && !livingCombatResurrectionCaster
            && !currentLivePackCanContinue)
        {
            if (Cohort().Config.ValidationRouteBossRecovery == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly)
            {
                std::string raw = BuildRawJson(bot, retreatThreat);
                std::ostringstream gateRaw;
                gateRaw << "{\"base\":" << raw
                        << ",\"native_recovery_gate\":{\"policy\":\"native_full_wipe_only\""
                        << ",\"authority\":\"native_encounter\""
                        << ",\"assistance\":\"none\""
                        << ",\"direct_respawn\":false"
                        << ",\"direct_state_manufacture\":false"
                        << ",\"alive_members\":" << aliveMembers
                        << ",\"dead_members\":" << deadMembers
                        << ",\"critical_role_dead\":" << (criticalRoleDead ? "true" : "false") << "}}";
                std::string semantic = BuildSemanticJson(bot, retreatThreat, "validation_route_recovery", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_recovery", retreatThreat,
                    "native_full_wipe_hold_partial_death", gateRaw.str().c_str(), semantic.c_str(),
                    float(aliveMembers), deadMembers);
                state.LastRecoveryMode = "native_full_wipe_only";
                state.LastRecoveryResult = "native_full_wipe_hold_partial_death";
                state.LastRecoveryMs = NowMs();
                state.LastNoProgressReason = "native_full_wipe_hold_partial_death";
                situation = "validation_route_recovery";
                action = "native_full_wipe_hold";
                target = retreatThreat;
                return true;
            }

            if (!retreatThreat)
                retreatThreat = bot->GetVictim();
            float retreatX = Cohort().Config.ValidationRouteX;
            float retreatY = Cohort().Config.ValidationRouteY;
            float retreatZ = Cohort().Config.ValidationRouteZ;
            char const* retreatDestination = "route_anchor";
            if (Party().ValidationRouteManifestIndex > 0
                && Party().ValidationRouteManifestIndex < Party().ValidationRouteManifest.size())
            {
                ValidationRouteManifestNode const& previousNode = Party().ValidationRouteManifest[Party().ValidationRouteManifestIndex - 1];
                if ((!previousNode.MapId || previousNode.MapId == bot->GetMapId())
                    && Distance2d(previousNode.NavigationAnchorX, previousNode.NavigationAnchorY,
                        Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY) > 20.0f)
                {
                    // The manifest anchor is a previously traversed, accepted
                    // route point. A straight-line inset toward the next node
                    // can cross disconnected terrain and synthesize an invalid
                    // Z before pathfinding gets a chance to validate the route.
                    retreatX = previousNode.NavigationAnchorX;
                    retreatY = previousNode.NavigationAnchorY;
                    retreatZ = previousNode.NavigationAnchorZ;
                    retreatDestination = "previous_route_anchor";
                }
            }

            bool livingMembersAtRetreatAnchor = true;
            for (GroupReference* itr = bot->GetGroup()->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* member = itr->GetSource();
                if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap())
                    continue;
                if (member->GetExactDist(retreatX, retreatY, retreatZ) > 5.0f)
                {
                    livingMembersAtRetreatAnchor = false;
                    break;
                }
            }

            uint64 nowMs = NowMs();
            if (livingMembersAtRetreatAnchor)
            {
                for (WorldBotState& cohortState : Party().Bots)
                {
                    // Bind every living cohort member to the same ordinary
                    // movement rendezvous. Native combat/evade and corpse
                    // recovery remain authoritative.
                    cohortState.ValidationRouteAnchorOverrideValid = true;
                    cohortState.ValidationRouteAnchorOverrideUntilMs = nowMs + 120000;
                    cohortState.ValidationRouteAnchorOverrideX = retreatX;
                    cohortState.ValidationRouteAnchorOverrideY = retreatY;
                    cohortState.ValidationRouteAnchorOverrideZ = retreatZ;
                    cohortState.ValidationRouteAnchorOverrideReason = "validation_route_partial_wipe_retreat_rendezvous";

                    Player* cohortBot = GetLoadedBot(cohortState);
                    if (!cohortBot || !cohortBot->IsAlive() || cohortBot->GetMap() != bot->GetMap())
                        continue;
                    SubmitMeleeAutoAttackIntent(cohortState,
                        BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                        BotMeleeAutoAttack::Owner::Recovery,
                        BotActionArbitration::Priority::Survival,
                        "partial_wipe_retreat_rendezvous");
                    cohortState.TargetGuid.Clear();
                    cohortBot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                    cohortState.WasInCombat = cohortBot->IsInCombat();
                    cohortState.ActivePathValid = false;
                    cohortState.IsMoving = false;
                }

                std::string raw = BuildRawJson(bot, retreatThreat);
                std::string semantic = BuildSemanticJson(bot, retreatThreat, "validation_route_recovery", &power, stage, activity);
                std::string retreatReason = std::string("partial_wipe_retreat_arrived_") + retreatDestination;
                RecordEvent(state, bot, "validation_route_recovery", retreatThreat,
                    retreatReason.c_str(), raw.c_str(), semantic.c_str(), 0.0f, deadMembers);
                state.LastRecoveryMode = "tactical_retreat_no_combat_res";
                state.LastRecoveryResult = std::string("retreat_arrived_") + retreatDestination;
                state.LastRecoveryMs = nowMs;
                ++state.RecoveryAttemptCount;
                situation = "validation_route_recovery";
                action = "validation_route_retreat_arrived";
                target = nullptr;
                return true;
            }

            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Recovery,
                BotActionArbitration::Priority::Survival,
                "tactical_retreat_no_combat_res");
            state.TargetGuid.Clear();
            bool moved = MoveBotToPoint(state, bot, retreatX, retreatY, retreatZ);
            if (state.LastRecoveryMode != "tactical_retreat_no_combat_res" || nowMs - state.LastRecoveryMs >= 5000)
            {
                std::string raw = BuildRawJson(bot, retreatThreat);
                std::string semantic = BuildSemanticJson(bot, retreatThreat, "validation_route_recovery", &power, stage, activity);
                std::string retreatReason = std::string(moved ? "tactical_retreat_no_combat_res_" : "hold_tactical_retreat_no_combat_res_") + retreatDestination;
                RecordEvent(state, bot, "validation_route_recovery", retreatThreat,
                    retreatReason.c_str(), raw.c_str(), semantic.c_str(), bot->GetExactDist(retreatX, retreatY, retreatZ), deadMembers);
                state.LastRecoveryMode = "tactical_retreat_no_combat_res";
                state.LastRecoveryResult = std::string(moved ? "moving_" : "holding_") + retreatDestination;
                state.LastRecoveryMs = nowMs;
                ++state.RecoveryAttemptCount;
            }
            situation = "validation_route_recovery";
            action = moved ? "validation_route_tactical_retreat" : "validation_route_hold_retreat";
            target = nullptr;
            return true;
        }
    }
    retireStaleValidationRoutePackMembers();
    bool failedTrashPackComplete = !persistedValidationRoutePackHasLiveMembers();
    Unit* retryableFailedTrashTarget = failedTrashPackComplete ? nullptr : activeValidationRoutePackTarget();
    bool failedTrashPackCanRetry = retryableFailedTrashTarget
        && isEligibleTrashClusterMob(retryableFailedTrashTarget->ToCreature());
    bool failedTrashPartyCombatActive = validationPartyHasActiveCombat();
    bool failedTrashRetryDue = state.ValidationRouteTerminalAtMs
        && NowMs() - state.ValidationRouteTerminalAtMs >= 5000;
    if (state.ValidationRouteTerminalState
        && state.ValidationRouteGeneration == Party().ValidationRouteGeneration
        && state.ValidationRouteTerminalGeneration == Party().ValidationRouteGeneration
        && Cohort().Config.ValidationRouteKind != "boss"
        && state.ValidationRouteTerminalReason == "validation_trash_no_progress"
        && Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
        && Party().ValidationRoutePackObservedEngagement
        && (failedTrashPackComplete || failedTrashPackCanRetry)
        && (!failedTrashPartyCombatActive || (failedTrashPackCanRetry && failedTrashRetryDue)))
    {
        uint64 retryNowMs = NowMs();
        for (WorldBotState& cohortState : Party().Bots)
        {
            if (Player* cohortBot = GetLoadedBot(cohortState))
                cohortBot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
            cohortState.TargetGuid.Clear();
            cohortState.ValidationRouteCombatProgressTargetGuid.Clear();
            cohortState.ValidationRoutePackProgressTargetGuid.Clear();
            cohortState.ValidationRouteCombatNoProgressCount = 0;
            cohortState.ValidationRouteCombatNoProgressSinceMs = 0;
            cohortState.ValidationRoutePackNoProgressCount = 0;
            cohortState.ValidationRoutePackNoProgressSinceMs = 0;
            cohortState.ValidationRouteTerminalState = false;
            cohortState.ValidationRouteTerminalAtMs = 0;
            cohortState.ValidationRouteTerminalGeneration = 0;
            cohortState.ValidationRouteTerminalReason.clear();
            cohortState.ActivePathValid = false;
            cohortState.IsMoving = false;
            cohortState.LoopRecoveryCooldownUntilMs = retryNowMs + 1000;
            if (failedTrashPackCanRetry)
            {
                // Reopen onto the actual surviving pack member rather than
                // the already-cleared lower anchor. This also recovers a live
                // engaged pack after the bounded terminal hold instead of
                // waiting forever for hostile combat state to disappear.
                cohortState.ValidationRouteAnchorOverrideValid = true;
                cohortState.ValidationRouteAnchorOverrideUntilMs = retryNowMs + 30000;
                cohortState.ValidationRouteAnchorOverrideX = retryableFailedTrashTarget->GetPositionX();
                cohortState.ValidationRouteAnchorOverrideY = retryableFailedTrashTarget->GetPositionY();
                cohortState.ValidationRouteAnchorOverrideZ = retryableFailedTrashTarget->GetPositionZ();
                cohortState.ValidationRouteAnchorOverrideReason = "validation_route_live_pack_reapproach";
            }
        }
        Unit* retryEvidenceTarget = failedTrashPackCanRetry ? retryableFailedTrashTarget : nullptr;
        // Leave combat focus empty for one decision so the route override
        // stays authoritative and all roles reapproach with the tank.
        target = nullptr;
        std::string raw = BuildRawJson(bot, retryEvidenceTarget);
        std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_recovery", &power, stage, activity);
        char const* recoveryReason = failedTrashPackCanRetry
            ? "failed_terminal_reopened_for_live_pack_reapproach"
            : "failed_terminal_reopened_after_pack_death";
        RecordEvent(state, bot, "validation_route_recovery", retryEvidenceTarget, recoveryReason,
            raw.c_str(), semantic.c_str(), float(Party().ValidationRoutePackDeathGuids.size()), uint32(Party().ValidationRoutePackMemberGuids.size()));
        situation = "validation_route_recovery";
        action = "validation_route_recovery";
        return true;
    }
    bool routePartyCombatActive = validationPartyHasActiveCombat();
    bool arrivalCombatActive = arrivalRoute && routePartyCombatActive;
    bool allRouteParticipantsAlive = true;
    uint32 loadedRouteParticipants = 0;
    for (WorldBotState const& cohortState : Party().Bots)
    {
        Player* cohortBot = GetLoadedBot(cohortState);
        if (!cohortBot)
            continue;
        ++loadedRouteParticipants;
        if (!cohortBot->IsAlive() || !IsValidationCohortMemberInOriginalInstance(cohortState, cohortBot))
        {
            allRouteParticipantsAlive = false;
            break;
        }
    }
    if (Cohort().Config.TargetPopulation && loadedRouteParticipants < Cohort().Config.TargetPopulation)
        allRouteParticipantsAlive = false;

    bool releasedRetreatRendezvous = !routePartyCombatActive && allRouteParticipantsAlive
        && state.ValidationRouteAnchorOverrideValid
        && state.ValidationRouteAnchorOverrideReason == "validation_route_partial_wipe_retreat_rendezvous";
    if (releasedRetreatRendezvous)
    {
        for (WorldBotState& cohortState : Party().Bots)
        {
            if (cohortState.ValidationRouteAnchorOverrideReason != "validation_route_partial_wipe_retreat_rendezvous")
                continue;
            cohortState.ValidationRouteAnchorOverrideValid = false;
            cohortState.ValidationRouteAnchorOverrideUntilMs = 0;
            cohortState.ValidationRouteAnchorOverrideReason.clear();
        }
        routeAnchorX = Cohort().Config.ValidationRouteX;
        routeAnchorY = Cohort().Config.ValidationRouteY;
        routeAnchorZ = Cohort().Config.ValidationRouteZ;
        routeAnchorReason = "validation_route_anchor";
        routeDistance = canonicalRouteDistance;
        state.QuestRouteDestination.X = routeAnchorX;
        state.QuestRouteDestination.Y = routeAnchorY;
        state.QuestRouteDestination.Z = routeAnchorZ;
        state.QuestRouteDestination.Reason = routeAnchorReason;
    }

    bool invalidArrivalTerminal = arrivalRoute
        && state.ValidationRouteTerminalState
        && state.ValidationRouteGeneration == Party().ValidationRouteGeneration
        && state.ValidationRouteTerminalGeneration == Party().ValidationRouteGeneration
        && state.ValidationRouteTerminalReason == "arrival"
        && (canonicalRouteDistance > routeArrivalRadius
            || std::fabs(bot->GetPositionZ() - Cohort().Config.ValidationRouteZ) > 4.0f
            || arrivalCombatActive);
    if (invalidArrivalTerminal)
    {
        state.ValidationRouteTerminalState = false;
        state.ValidationRouteTerminalAtMs = 0;
        state.ValidationRouteTerminalGeneration = 0;
        state.ValidationRouteTerminalReason.clear();
        state.LoopRecoveryCooldownUntilMs = 0;
    }

    if (state.ValidationRouteTerminalState
        && state.ValidationRouteGeneration == Party().ValidationRouteGeneration
        && state.ValidationRouteTerminalGeneration == Party().ValidationRouteGeneration)
    {
        float terminalCohortRadius = Cohort().Config.ValidationRouteClusterRadiusYards > 1.0f
            ? std::min(Cohort().Config.ValidationRouteClusterRadiusYards, 90.0f)
            : 90.0f;
        if (!arrivalRoute
            && !Party().ValidationRouteManifest.empty()
            && !Party().ValidationRouteManifestComplete
            && Cohort().Config.ValidationRouteAdvanceMode == "terminal"
            && routeDistance > terminalCohortRadius)
        {
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Safety,
                BotActionArbitration::Priority::Terminal,
                "terminal_cohort_catchup");
            target = nullptr;
            state.TargetGuid.Clear();
            if (moveToRouteAnchor())
            {
                std::string raw = BuildRawJson(bot, nullptr);
                std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_regroup", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_regroup", nullptr, "terminal_cohort_catchup", raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry);
                situation = "validation_route_regroup";
                action = "move_to_validation_route_anchor";
                return true;
            }
        }

        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Safety,
            BotActionArbitration::Priority::Terminal,
            "validation_route_terminal_hold");
        state.TargetGuid.Clear();
        state.WasInCombat = false;
        state.LoopRecoveryCooldownUntilMs = NowMs() + 60000;
        situation = Cohort().Config.ValidationRouteKind == "boss"
            ? "validation_route_manifest"
            : "normal_dungeon_trash";
        action = state.ValidationRouteTerminalReason == "trash_cluster_cleared"
            || state.ValidationRouteTerminalReason == "boss_killed"
            || state.ValidationRouteTerminalReason == "arrival"
            ? "validation_route_complete"
            : "validation_route_failed";
        if (!state.ValidationRouteTerminalAtMs || NowMs() - state.ValidationRouteTerminalAtMs <= 5000)
        {
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, situation.c_str(), &power, stage, activity);
            RecordEvent(state, bot, "validation_route_recovery", nullptr, state.ValidationRouteTerminalReason.empty() ? "route_terminal_hold" : state.ValidationRouteTerminalReason.c_str(), raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry);
        }
        return true;
    }
    // Regroup and descent nodes must not suppress a natural pull merely because
    // the cohort reached the navigation anchor. Finish every active attacker
    // before marking arrival; otherwise mobs can evade back across a one-way
    // descent and poison the following trash ledger with unreachable survivors.
    if (arrivalCombatActive)
        enrollEngagedValidationRoutePackMembers();
    if (arrivalRoute && !arrivalCombatActive)
    {
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Route,
            BotActionArbitration::Priority::Mechanic,
            "validation_route_arrival_hold");
        target = nullptr;
        state.TargetGuid.Clear();
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_regroup", &power, stage, activity);
        if (Cohort().Config.ValidationRouteKind == "descent"
            && !Cohort().Config.ValidationRouteDescentAction.empty())
        {
            if (Cohort().Config.ValidationRouteDescentAction
                != "native_walkable_descent")
            {
                // A manifest may name a player input that the server-side bot
                // cannot safely express (for example a client jump). Keep it
                // fail-closed instead of substituting a spline or position
                // mutation.
                state.ActivePathValid = false;
                state.ValidationRouteDescentPhase =
                    WorldBotState::ValidationDescentPhase::Blocked;
                state.ValidationRouteDescentRejectReason =
                    "native_descent_semantics_unavailable";
                state.LastPathRejectReason =
                    state.ValidationRouteDescentRejectReason;
                state.LastNoProgressReason =
                    state.ValidationRouteDescentRejectReason;
                state.LastDecisionResult = "native_descent_unavailable";
                FailValidationAttemptOnce(state, bot,
                    "native_descent_semantics_unavailable",
                    Party().ValidationRouteGeneration);
                situation = "validation_route_descent";
                action = "validation_route_descent_blocked";
                target = nullptr;
                return true;
            }

            size_t const nextIndex = Party().ValidationRouteManifestIndex + 1;
            bool const hasNextGoal = nextIndex
                < Party().ValidationRouteManifest.size();
            ValidationRouteManifestNode const* nextNode = hasNextGoal
                ? &Party().ValidationRouteManifest[nextIndex] : nullptr;
            WorldBotState::ValidationDescentPhase const previousPhase =
                state.ValidationRouteDescentPhase;
            BotActionArbitration::Outcome const descentOutcome =
                ExecuteNativeActionIntent(state, bot,
                    BotNativeAction::NativeDescent{
                        Cohort().Config.ValidationRouteX,
                        Cohort().Config.ValidationRouteY,
                        Cohort().Config.ValidationRouteZ,
                        nextNode ? nextNode->NavigationAnchorX : 0.0f,
                        nextNode ? nextNode->NavigationAnchorY : 0.0f,
                        nextNode ? nextNode->NavigationAnchorZ : 0.0f,
                        Party().ValidationRouteGeneration,
                        hasNextGoal },
                    BotMovementArbitration::Owner::Route,
                    BotMovementArbitration::Priority::Route);

            char const* const descentPhase = ValidationDescentPhaseName(
                state.ValidationRouteDescentPhase);
            bool const phaseChanged = previousPhase
                != state.ValidationRouteDescentPhase;
            bool const descentReady = state.ValidationRouteDescentPhase
                    == WorldBotState::ValidationDescentPhase::Ready
                && state.ValidationRouteDescentDepartureObserved
                && state.ValidationRouteDescentLandingObserved
                && state.ValidationRouteDescentHealthMarginSatisfied
                && state.ValidationRouteDescentLandingPathProven
                && state.ValidationRouteDescentMonotonicProgressObserved
                && !bot->IsFalling();
            if (phaseChanged || descentReady
                || descentOutcome.Result
                    != BotActionArbitration::Disposition::Committed)
                RecordEvent(state, bot, "validation_route_descent", nullptr,
                    state.ValidationRouteDescentRejectReason.empty()
                        ? descentPhase
                        : state.ValidationRouteDescentRejectReason.c_str(),
                    raw.c_str(), semantic.c_str(), canonicalRouteDistance,
                    uint32(std::round(
                        state.ValidationRouteDescentLandingHealthPct * 100.0f)));

            situation = "validation_route_descent";
            if (descentReady)
            {
                state.ValidationRouteTerminalState = true;
                state.ValidationRouteTerminalAtMs = NowMs();
                state.ValidationRouteTerminalGeneration =
                    Party().ValidationRouteGeneration;
                state.ValidationRouteTerminalReason =
                    "native_descent_landed_path_proven";
                state.LoopRecoveryCooldownUntilMs = NowMs() + 60000;
                RecordEvent(state, bot, "validation_route_terminal", nullptr,
                    state.ValidationRouteTerminalReason.c_str(), raw.c_str(),
                    semantic.c_str(), canonicalRouteDistance,
                    Cohort().Config.ValidationRouteTargetEntry);
                action = "validation_route_descent_complete";
                MaybeAdvanceValidationRouteManifest();
            }
            else if (state.ValidationRouteDescentPhase
                == WorldBotState::ValidationDescentPhase::Falling)
                action = "validation_route_descent_falling";
            else if (state.ValidationRouteDescentPhase
                == WorldBotState::ValidationDescentPhase::Landed)
                action = "validation_route_descent_landing_pending";
            else if (descentOutcome.Result
                == BotActionArbitration::Disposition::Committed)
                action = "validation_route_descent_walk_segment";
            else
                action = "validation_route_descent_blocked";
            target = nullptr;
            return true;
        }
        if (canonicalRouteDistance <= routeArrivalRadius
            && std::fabs(bot->GetPositionZ() - Cohort().Config.ValidationRouteZ) <= 4.0f)
        {
            state.ValidationRouteTerminalState = true;
            state.ValidationRouteTerminalAtMs = NowMs();
            state.ValidationRouteTerminalGeneration = Party().ValidationRouteGeneration;
            state.ValidationRouteTerminalReason = "arrival";
            state.LoopRecoveryCooldownUntilMs = NowMs() + 60000;
            RecordEvent(state, bot, "validation_route_regroup", nullptr, "arrival", raw.c_str(), semantic.c_str(), canonicalRouteDistance, Cohort().Config.ValidationRouteTargetEntry);
            RecordEvent(state, bot, "validation_route_terminal", nullptr, "arrival", raw.c_str(), semantic.c_str(), canonicalRouteDistance, Cohort().Config.ValidationRouteTargetEntry);
            situation = "validation_route_regroup";
            action = "validation_route_complete";
            MaybeAdvanceValidationRouteManifest();
            return true;
        }

        bool const moved = moveToRouteAnchor();
        char const* movementResult = moved
            ? (Cohort().Config.ValidationRouteLabel.empty()
                ? "move_to_arrival" : Cohort().Config.ValidationRouteLabel.c_str())
            : (state.LastPathRejectReason.empty()
                ? "route_anchor_retryable" : state.LastPathRejectReason.c_str());
        RecordEvent(state, bot, "validation_route_regroup", nullptr,
            movementResult, raw.c_str(), semantic.c_str(), routeDistance,
            Cohort().Config.ValidationRouteTargetEntry);
        situation = "validation_route_regroup";
        action = moved ? "move_to_validation_route_anchor" : "validation_route_hold_anchor";
        return true;
    }
    if (Cohort().Config.ValidationRouteKind != "boss"
        && std::string(GetDungeonRole(bot)) != "tank"
        && routeDistance > routeArrivalRadius
        && (Party().ValidationRoutePackObservedEngagement || Party().ValidationRouteCompletedPackCount > 0)
        && !routeFocusMemoryFresh()
        && routeTankFocusGuid().IsEmpty()
        && !trashClusterHasLiveMobs()
        && !validationPartyHasActiveCombat())
    {
        if (tryValidationRouteMovementCheck(target))
            return true;
        bool moved = MoveBotToPoint(state, bot, Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ, true);
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_regroup", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_regroup", nullptr, moved ? "move_to_terminal_route_endpoint" : "terminal_route_endpoint_path_rejected", raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry);
        situation = "validation_route_regroup";
        action = moved ? "move_to_validation_route_endpoint" : "validation_route_hold_anchor";
        return true;
    }
    {
        DungeonTrashActionResult readinessResult;
        if (TryValidationRouteReadiness(state, bot, target, power, stage, activity, readinessResult))
        {
            situation = "validation_route_readiness";
            action = readinessResult.Action.empty() ? "validation_route_readiness_audit" : readinessResult.Action;
            target = readinessResult.Target;
            return true;
        }
    }
    if (tryValidationRouteMovementCheck(target))
        return true;
    if (tryValidationRoutePatrolPull())
        return true;
    if (tryValidationRouteMinimumDistance())
        return true;
    if (tryValidationRouteDrudgeChargeLanes())
        return true;

    struct TrashThreatControl
    {
        Player* Tank = nullptr;
        Player* HealerTarget = nullptr;
        Unit* AreaTarget = nullptr;
        std::vector<Unit*> HealerOwnedTargets;
        std::vector<Unit*> TankOwnedTargets;
        std::vector<Unit*> InsecureTankOwnedTargets;
        uint32 EngagedCount = 0;
        uint32 HealerTargetCount = 0;
        uint32 TankOwnedCount = 0;
        uint32 SecureTankCount = 0;
    } trashThreatControl;
    // Boss nodes can still contain ordinary prerequisite packs. Apply the
    // same secure-threat and Misdirection policy to those mobs, while leaving
    // the configured boss and declared boss adds to their specialized logic.
    {
        for (WorldBotState const& cohortState : Party().Bots)
        {
            Player* member = GetLoadedBot(cohortState);
            if (member && member->IsAlive() && member->GetMap() == bot->GetMap()
                && member->GetGroup() == bot->GetGroup()
                && std::string(GetDungeonRole(member)) == "tank")
            {
                trashThreatControl.Tank = member;
                break;
            }
        }

        std::vector<WorldObject*> threatObjects;
        Trinity::AllWorldObjectsInRange threatCheck(bot, 80.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> threatSearcher(bot, threatObjects, threatCheck);
        Cell::VisitAllObjects(bot, threatSearcher, 80.0f);
        uint8 areaTargetPriority = 0;
        float areaTargetDistance = std::numeric_limits<float>::max();
        uint32 areaTargetGuid = std::numeric_limits<uint32>::max();
        for (WorldObject* object : threatObjects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!creature || !creature->IsAlive() || !creature->GetHealth()
                || !bot->IsValidAttackTarget(creature) || (!creature->IsInCombat() && !creature->GetVictim())
                || isImmediateNextValidationRouteEncounterMember(creature))
                continue;
            // A configured scripted actor (Millhouse in the opening
            // Corborus node) is a future route event, not ordinary trash.  It
            // may already be attackable/in combat due to native script
            // preparation, but it must not enter the generic threat scan until
            // the discovery handoff has enrolled its current-generation GUID.
            bool currentDiscoveryScriptedMember = discoveryLeg
                && Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
                && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID())
                    != Party().ValidationRoutePackMemberGuids.end();
            if (isPendingScriptedEventEntry(creature) && !currentDiscoveryScriptedMember)
                continue;
            bool declaredBossAdd = Cohort().Config.ValidationRouteKind == "boss"
                && std::find(Cohort().Config.ValidationRouteAddTargetEntries.begin(),
                    Cohort().Config.ValidationRouteAddTargetEntries.end(), creature->GetEntry())
                    != Cohort().Config.ValidationRouteAddTargetEntries.end();
            if (Cohort().Config.ValidationRouteKind == "boss"
                && (isValidationRouteScriptTarget(creature) || declaredBossAdd))
                continue;
            Player* victim = creature->GetVictim() ? creature->GetVictim()->ToPlayer() : nullptr;
            if (!victim || victim->GetGroup() != bot->GetGroup())
                continue;

            ++trashThreatControl.EngagedCount;
            std::string victimRole = GetDungeonRole(victim);
            if (victimRole == "healer")
            {
                ++trashThreatControl.HealerTargetCount;
                trashThreatControl.HealerOwnedTargets.push_back(creature);
                if (!trashThreatControl.HealerTarget
                    || victim->GetGUID().GetCounter()
                        < trashThreatControl.HealerTarget->GetGUID().GetCounter())
                    trashThreatControl.HealerTarget = victim;
            }
            uint8 priority = victimRole == "healer" ? 3 : (victimRole == "tank" ? 1 : 2);
            float distance = bot->GetExactDist(creature);
            uint32 guid = creature->GetGUID().GetCounter();
            if (!trashThreatControl.AreaTarget || priority > areaTargetPriority
                || (priority == areaTargetPriority && (distance < areaTargetDistance
                    || (distance == areaTargetDistance && guid < areaTargetGuid))))
            {
                trashThreatControl.AreaTarget = creature;
                areaTargetPriority = priority;
                areaTargetDistance = distance;
                areaTargetGuid = guid;
            }

            if (!trashThreatControl.Tank || victim != trashThreatControl.Tank)
                continue;
            trashThreatControl.TankOwnedTargets.push_back(creature);
            ++trashThreatControl.TankOwnedCount;
            float tankThreat = creature->GetThreatManager().GetThreat(trashThreatControl.Tank, true);
            float highestPartyThreat = 0.0f;
            for (WorldBotState const& cohortState : Party().Bots)
            {
                Player* member = GetLoadedBot(cohortState);
                if (!member || member == trashThreatControl.Tank || !member->IsAlive()
                    || member->GetMap() != creature->GetMap())
                    continue;
                highestPartyThreat = std::max(highestPartyThreat,
                    creature->GetThreatManager().GetThreat(member, true));
            }
            // In a raid trash node, the native ThreatManager's ranged victim
            // switch threshold (130%) is the observable safety boundary.  The
            // old dungeon-tuning floor of 2000 threat and 2.5x headroom starved
            // all five BWD damage slots while both tanks already owned every
            // declared Drakonid.  Keep that legacy tuning outside raid trash;
            // here require current native victim ownership plus positive 1.3x
            // headroom, recomputed on every decision.
            bool secureThreat = bot->GetMap() && bot->GetMap()->IsRaid()
                && Cohort().Config.ValidationRouteKind != "boss"
                ? tankThreat > 0.0f && tankThreat >= highestPartyThreat * 1.3f
                : tankThreat >= 2000.0f && tankThreat >= highestPartyThreat * 2.5f;
            if (secureThreat)
                ++trashThreatControl.SecureTankCount;
            else
                trashThreatControl.InsecureTankOwnedTargets.push_back(creature);
        }
    }
    // A boss node has no authority to finish ordinary corridor trash.  The
    // manifest must place that pack in an explicit preceding trash node.  Run
    // this rejection immediately after observation and before any of the
    // shared trash threat, movement, Misdirection, defensive, or profile-action
    // branches below; a downstream check is too late because many of those
    // branches return after acting on AreaTarget.
    if (Cohort().Config.ValidationRouteKind == "boss"
        && trashThreatControl.EngagedCount > 0
        && trashThreatControl.AreaTarget)
    {
        Unit* rejected = trashThreatControl.AreaTarget;
        bot->InterruptNonMeleeSpells(false);
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Threat,
            BotActionArbitration::Priority::ThreatControl,
            "trash_threat_hold");
        if (Pet* pet = bot->GetPet())
            pet->AttackStop();
        for (Unit* controlled : bot->m_Controlled)
            if (controlled)
                controlled->AttackStop();
        std::string raw = BuildRawJson(bot, rejected);
        std::string semantic = BuildSemanticJson(
            bot, rejected, "validation_route_prerequisite", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_prerequisite_rejected",
            rejected, "boss_route_target_not_declared", raw.c_str(),
            semantic.c_str(), bot->GetExactDist(rejected),
            Cohort().Config.ValidationRouteTargetEntry);
        state.TargetGuid.Clear();
        target = nullptr;
        situation = "validation_route_prerequisite";
        action = "boss_route_prerequisite_blocked";
        return true;
    }
    bool insecureTrashSwarm = trashThreatControl.EngagedCount >= 3
        && trashThreatControl.SecureTankCount * 10 < trashThreatControl.EngagedCount * 9;
    bool tankOwnsTrashMajority = trashThreatControl.EngagedCount > 0
        && trashThreatControl.TankOwnedCount * 10 >= trashThreatControl.EngagedCount * 9;
    bool hunterTrashMisdirectionActive = bot->getClass() == CLASS_HUNTER
        && (bot->HasAura(34477) || bot->HasAura(35079));
    // Ordinary route movement repeatedly preempted Discipline's existing Fade
    // while 11-13 Flayers retained the healer in rerun104. Put the same native
    // gate ahead of those movement/hold decisions. Rerun115 showed that a
    // two-attacker transient can consume Fade before a later 15-hostile wave,
    // rerun116 found the same pattern at three, and rerun117 at a precursor
    // peaking at eight, so use the shared nine-attacker reservation. Never
    // cancel a positive
    // heal; if one is active, this branch is retried on the next tick.
    // Rerun173's Protection/Holy composition fully owned the opening corridor
    // pack before one successful heal flipped four already-eligible hostiles.
    // The healer was outside every immediate native Paladin rescue range, so
    // six bounded tank movement ticks still produced 28 strict exposure
    // samples before Hand of Protection and Righteous Defense recovered them.
    // Use the existing native Fade at that exact four-hostile threshold only
    // with a Protection Paladin tank. Rerun196 then captured a distinct Feral
    // handoff where four of five already-eligible hostiles flipped together
    // after one successful heal. Native Swipe recovered all four in 773 ms,
    // but four 250-ms identity snapshots exceeded the unchanged exposure-ratio
    // ceiling. Admit the same native Fade only when at least four hostiles and
    // at least 80% of the current pack already target the healer with a Druid
    // tank. Smaller Feral precursors and Blood/Warrior tanks retain the
    // established nine-hostile reservation for a later large wave; a rejected
    // cast changes only observation cadence while native legality stays final.
    bool protectionPaladinHealerThreat =
        trashThreatControl.Tank
        && trashThreatControl.Tank->getClass() == CLASS_PALADIN
        && trashThreatControl.HealerTargetCount >= 4;
    bool feralDruidMajorityHealerThreat =
        trashThreatControl.Tank
        && trashThreatControl.Tank->getClass() == CLASS_DRUID
        && trashThreatControl.HealerTargetCount >= 4
        && trashThreatControl.HealerTargetCount * 5
            >= trashThreatControl.EngagedCount * 4;
    if (std::string(GetDungeonRole(bot)) == "healer"
        && (trashThreatControl.HealerTargetCount >= 9
            || protectionPaladinHealerThreat
            || feralDruidMajorityHealerThreat)
        && bot->HasSpell(586) && !bot->HasAura(586))
    {
        if (protectionPaladinHealerThreat
            || feralDruidMajorityHealerThreat)
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
        if (Spell* currentSpell = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL))
            if (!currentSpell->IsPositive())
                bot->InterruptNonMeleeSpells(false);
        if (!bot->HasUnitState(UNIT_STATE_CASTING)
            && TryCastFriendlySpell(bot, bot, 586))
        {
            std::string raw = BuildRawJson(bot, trashThreatControl.AreaTarget);
            std::string semantic = BuildSemanticJson(bot,
                trashThreatControl.AreaTarget, "normal_dungeon_trash",
                &power, stage, activity);
            RecordEvent(state, bot, "healer_assignment", bot,
                "fade_early_trash_swarm_threat_drop",
                raw.c_str(), semantic.c_str(),
                float(trashThreatControl.HealerTargetCount),
                trashThreatControl.EngagedCount, 586);
            situation = "validation_route_group_heal";
            action = "fade_early_trash_swarm_threat_drop";
            return true;
        }
    }
    // The group-heal helper already converges a healer with a Feral tank, but
    // rerun110 proved ordinary route/combat movement can win first and preserve
    // a split Flayer topology for several Roar cycles.  Reuse that same
    // collision-safe four-yard pickup before route movement when a large wave
    // is forming or the healer already owns at least three hostiles.  Exact
    // hazard movement ran earlier and remains authoritative; urgent health and
    // active positive casts still prevent this positioning action.
    if (std::string(GetDungeonRole(bot)) == "healer"
        && trashThreatControl.Tank
        && trashThreatControl.Tank->getClass() == CLASS_DRUID
        && bot->GetExactDist2d(trashThreatControl.Tank) > 6.0f
        && !bot->HasUnitState(UNIT_STATE_CASTING)
        && !bot->IsFalling())
    {
        bool proactiveLargeWaveStack =
            trashThreatControl.EngagedCount >= 12
            && trashThreatControl.HealerTargetCount == 0
            && UnitHealthPct(bot) > 0.88f
            && UnitHealthPct(trashThreatControl.Tank) > 0.88f;
        bool reactiveHealerStack =
            trashThreatControl.HealerTargetCount >= 3
            && UnitHealthPct(bot) > 0.45f
            && UnitHealthPct(trashThreatControl.Tank) > 0.40f;
        if (proactiveLargeWaveStack || reactiveHealerStack)
        {
            Unit* nearestAttacker = nullptr;
            float nearestAttackerDistance =
                std::numeric_limits<float>::max();
            for (Unit* attacker : bot->getAttackers())
                if (attacker && attacker->IsAlive()
                    && attacker->GetMap() == bot->GetMap()
                    && attacker->GetVictim() == bot
                    && bot->IsValidAttackTarget(attacker)
                    && bot->GetExactDist2d(attacker)
                        < nearestAttackerDistance)
                {
                    nearestAttacker = attacker;
                    nearestAttackerDistance =
                        bot->GetExactDist2d(attacker);
                }
            Unit* approachFrom = nearestAttacker
                ? nearestAttacker : trashThreatControl.AreaTarget;
            float pickupAngle = approachFrom
                ? approachFrom->GetAngle(trashThreatControl.Tank)
                    - trashThreatControl.Tank->GetOrientation()
                : trashThreatControl.Tank->GetAngle(bot)
                    - trashThreatControl.Tank->GetOrientation();
            Position pickup =
                trashThreatControl.Tank->GetFirstCollisionPosition(
                    4.0f, pickupAngle);
            if (MoveBotToPoint(state, bot,
                    pickup.GetPositionX(), pickup.GetPositionY(),
                    pickup.GetPositionZ()))
            {
                std::string raw = BuildRawJson(
                    bot, trashThreatControl.AreaTarget);
                std::string semantic = BuildSemanticJson(
                    bot, trashThreatControl.AreaTarget,
                    "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot, "healer_assignment",
                    trashThreatControl.Tank,
                    reactiveHealerStack
                        ? "healer_converge_early_for_feral_trash_pickup"
                        : "healer_preposition_early_for_feral_trash_pickup",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist2d(trashThreatControl.Tank),
                    trashThreatControl.HealerTargetCount);
                situation = "validation_route_group_heal";
                action = reactiveHealerStack
                    ? "healer_converge_early_for_feral_trash_pickup"
                    : "healer_preposition_early_for_feral_trash_pickup";
                return true;
            }
        }
    }
    bool hunterTrashAoeTransferReady = true;
    float hunterTrashAoeMinRange = 5.0f;
    static constexpr float HunterTrashAoeMinRangeSafety = 3.0f;
    static constexpr float HunterTrashMaxRange = 35.0f;
    if (bot->getClass() == CLASS_HUNTER && trashThreatControl.EngagedCount >= 2)
    {
        Unit* areaTarget = trashThreatControl.AreaTarget;
        if (areaTarget)
            if (SpellInfo const* multiShot = sSpellMgr->GetSpellInfo(2643))
            {
                float spellMinRange = bot->GetSpellMinRangeForTarget(areaTarget, multiShot);
                if (multiShot->RangeEntry && (multiShot->RangeEntry->Flags & SPELL_RANGE_RANGED))
                    spellMinRange += bot->GetMeleeRange(areaTarget);
                hunterTrashAoeMinRange = std::max(hunterTrashAoeMinRange, spellMinRange);
            }
        hunterTrashAoeMinRange = std::min(HunterTrashMaxRange - 1.0f,
            hunterTrashAoeMinRange + HunterTrashAoeMinRangeSafety);
        hunterTrashAoeTransferReady = areaTarget && bot->HasSpell(2643)
            && bot->GetPower(POWER_FOCUS) >= 40
            && bot->GetExactDist(areaTarget) >= hunterTrashAoeMinRange
            && bot->GetExactDist(areaTarget) <= HunterTrashMaxRange
            && bot->IsWithinLOSInMap(areaTarget);
    }
    if (std::string(GetDungeonRole(bot)) == "dps"
        && trashThreatControl.EngagedCount >= 3
        && UnitHealthPct(bot) <= (bot->getClass() == CLASS_SHAMAN ? 0.45f : 0.35f))
    {
        uint32 emergencySpellId = bot->getClass() == CLASS_MAGE ? 45438
            : (bot->getClass() == CLASS_HUNTER ? 19263
                : (bot->getClass() == CLASS_SHAMAN ? 30823 : 0));
        if (emergencySpellId && bot->HasSpell(emergencySpellId)
            && !bot->HasAura(emergencySpellId)
            && TryCastFriendlySpell(bot, bot, emergencySpellId))
        {
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Threat,
                BotActionArbitration::Priority::ThreatControl,
                "prerequisite_swarm_emergency_defensive");
            if (Pet* pet = bot->GetPet())
                pet->AttackStop();
            std::string raw = BuildRawJson(bot, trashThreatControl.AreaTarget);
            std::string semantic = BuildSemanticJson(bot, trashThreatControl.AreaTarget,
                "normal_dungeon_trash", &power, stage, activity);
            RecordEvent(state, bot, "defensive", bot, "prerequisite_swarm_emergency_defensive",
                raw.c_str(), semantic.c_str(), UnitHealthPct(bot), trashThreatControl.EngagedCount,
                emergencySpellId);
            target = trashThreatControl.Tank && trashThreatControl.Tank->GetVictim()
                ? trashThreatControl.Tank->GetVictim() : trashThreatControl.AreaTarget;
            state.TargetGuid = target ? target->GetGUID() : ObjectGuid::Empty;
            situation = "normal_dungeon_trash";
            action = "prerequisite_swarm_emergency_defensive";
            return true;
        }
    }
    if (bot->getClass() == CLASS_HUNTER
        && trashThreatControl.Tank
        && trashThreatControl.EngagedCount > 0
        && bot->HasSpell(34477)
        && !hunterTrashMisdirectionActive
        && hunterTrashAoeTransferReady
        && TryCastFriendlySpell(bot, trashThreatControl.Tank, 34477))
    {
        std::string raw = BuildRawJson(bot, trashThreatControl.AreaTarget);
        std::string semantic = BuildSemanticJson(bot, trashThreatControl.AreaTarget,
            "normal_dungeon_trash", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_threat_transfer", trashThreatControl.AreaTarget,
            "misdirection_to_tank", raw.c_str(), semantic.c_str(),
            float(trashThreatControl.EngagedCount), Cohort().Config.ValidationRouteTargetEntry, 34477);
        target = trashThreatControl.AreaTarget;
        state.TargetGuid = target ? target->GetGUID() : ObjectGuid::Empty;
        situation = "normal_dungeon_trash";
        action = "misdirection_to_tank";
        return true;
    }
    if (hunterTrashMisdirectionActive
        && trashThreatControl.Tank
        && trashThreatControl.AreaTarget)
    {
        target = trashThreatControl.AreaTarget;
        state.TargetGuid = target->GetGUID();
        bool useAreaTransfer = trashThreatControl.EngagedCount >= 2;
        if (useAreaTransfer && bot->GetPower(POWER_FOCUS) < 40)
        {
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target,
                "normal_dungeon_trash", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_transfer", target,
                "misdirection_aoe_wait_for_focus", raw.c_str(), semantic.c_str(),
                float(bot->GetPower(POWER_FOCUS)), trashThreatControl.EngagedCount, 2643);
            situation = "normal_dungeon_trash";
            action = "misdirection_aoe_wait_for_focus";
            return true;
        }
        float transferMinRange = useAreaTransfer ? hunterTrashAoeMinRange : 5.0f;
        if (bot->GetExactDist(target) < transferMinRange
            || bot->GetExactDist(target) > HunterTrashMaxRange
            || !bot->IsWithinLOSInMap(target))
        {
            ResolvedCombatAction rangeAction;
            rangeAction.MovementDirective = "ranged";
            rangeAction.AutoAttackMode = "ranged";
            rangeAction.MinRange = transferMinRange;
            rangeAction.MaxRange = HunterTrashMaxRange;
            bool moved = MoveBotToProfileRange(state, bot, target, &rangeAction);
            situation = "normal_dungeon_trash";
            action = moved
                ? (useAreaTransfer ? "move_to_misdirection_aoe_range" : "move_to_misdirection_single_range")
                : (useAreaTransfer ? "hold_misdirection_aoe_range" : "hold_misdirection_single_range");
            return true;
        }
        if (bot->isMoving())
            bot->StopMoving();
        ResolvedCombatAction transferAction;
        BotActionResult result = BotActionResult::NoAction;
        if (useAreaTransfer)
        {
            transferAction.Valid = true;
            transferAction.Type = "cast";
            transferAction.SpellId = 2643;
            transferAction.TargetGuid = target->GetGUID();
            transferAction.DebugName = "cleave";
            transferAction.MovementDirective = "ranged";
            transferAction.AutoAttackMode = "ranged";
            transferAction.MinRange = hunterTrashAoeMinRange;
            transferAction.MaxRange = HunterTrashMaxRange;
            BotActionExecutor executor;
            result = executor.ExecuteCombat(bot, bot, transferAction);
            std::string castFailureReason;
            if (result == BotActionResult::CastFailed)
                castFailureReason = "spell_cast_result_" + std::to_string(executor.LastSpellCastResult());
            RecordCombatAttempt(state, bot, target, "misdirection_aoe_transfer", &transferAction,
                result, castFailureReason.empty() ? nullptr : castFailureReason.c_str());
        }
        else
        {
            transferAction = ResolveProfileCombatAction(bot, target, 1, false);
            result = ExecuteProfileCombatAction(&state, bot, target, &transferAction, 1, false);
        }
        std::string raw = BuildRawJson(bot, target);
        std::string semantic = BuildSemanticJson(bot, target, "normal_dungeon_trash", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_threat_transfer", target,
            useAreaTransfer ? "misdirection_aoe_transfer" : "misdirection_single_target_transfer",
            raw.c_str(), semantic.c_str(), float(trashThreatControl.EngagedCount),
            Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? transferAction.SpellId : 0);
        situation = "normal_dungeon_trash";
        action = useAreaTransfer ? "misdirection_aoe_transfer" : "misdirection_single_target_transfer";
        state.WasInCombat = true;
        return true;
    }
    if (std::string(GetDungeonRole(bot)) == "dps"
        && trashThreatControl.Tank
        && insecureTrashSwarm
        && !hunterTrashMisdirectionActive)
    {
        Unit* tankFocus = trashThreatControl.Tank->GetVictim();
        if (tankOwnsTrashMajority && tankFocus && tankFocus->IsAlive() && bot->IsValidAttackTarget(tankFocus))
        {
            bool rangedDps = bot->getClass() == CLASS_MAGE || bot->getClass() == CLASS_HUNTER;
            if (rangedDps && trashThreatControl.EngagedCount >= 3
                && bot->GetExactDist2d(trashThreatControl.Tank) < 8.0f
                && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
            {
                Unit* approachFrom = trashThreatControl.AreaTarget
                    ? trashThreatControl.AreaTarget : tankFocus;
                float spreadOffset = bot->GetGUID().GetCounter() % 2 ? 0.35f : -0.35f;
                Position safeRange = trashThreatControl.Tank->GetFirstCollisionPosition(10.0f,
                    approachFrom->GetAngle(trashThreatControl.Tank)
                        - trashThreatControl.Tank->GetOrientation() + spreadOffset);
                if (MoveBotToPoint(state, bot, safeRange.GetPositionX(), safeRange.GetPositionY(), safeRange.GetPositionZ()))
                {
                    SubmitMeleeAutoAttackIntent(state,
                        BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                        BotMeleeAutoAttack::Owner::Threat,
                        BotActionArbitration::Priority::ThreatControl,
                        "trash_threat_spread_hold");
                    if (Pet* pet = bot->GetPet())
                        pet->AttackStop();
                    std::string raw = BuildRawJson(bot, tankFocus);
                    std::string semantic = BuildSemanticJson(bot, tankFocus,
                        "normal_dungeon_trash", &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_threat_gate", tankFocus,
                        "spread_after_secure_prerequisite_threat", raw.c_str(), semantic.c_str(),
                        bot->GetExactDist2d(trashThreatControl.Tank), trashThreatControl.EngagedCount);
                    target = tankFocus;
                    state.TargetGuid = tankFocus->GetGUID();
                    situation = "validation_route_regroup";
                    action = "spread_after_secure_prerequisite_threat";
                    return true;
                }
            }
            if (bot->GetVictim() && bot->GetVictim() != tankFocus)
                SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                    BotMeleeAutoAttack::Owner::Threat,
                    BotActionArbitration::Priority::ThreatControl,
                    "trash_threat_focus_switch");
            if (Pet* pet = bot->GetPet(); pet && pet->GetVictim() && pet->GetVictim() != tankFocus)
                pet->AttackStop();
            target = tankFocus;
            state.TargetGuid = tankFocus->GetGUID();
            ResolvedCombatAction focusedAction = ResolveProfileCombatAction(bot, tankFocus, 1, false);
            float engageRange = focusedAction.MaxRange > 0.0f
                ? focusedAction.MaxRange : routeEngageRange(bot, tankFocus, focusedAction.SpellId);
            float targetDistance = bot->GetExactDist(tankFocus);
            if (focusedAction.Valid && focusedAction.MinRange > 0.0f && targetDistance < focusedAction.MinRange)
            {
                bool moved = moveOutOfProfileDeadZone(bot, tankFocus, focusedAction);
                situation = "normal_dungeon_trash";
                action = moved ? "move_to_profile_min_range" : "hold_tactical_path_rejected";
                return true;
            }
            if (targetDistance > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(tankFocus))
            {
                bool moved = MoveBotToProfileRange(state, bot, tankFocus,
                    focusedAction.Valid ? &focusedAction : nullptr);
                situation = "normal_dungeon_trash";
                action = moved ? "move_to_focused_trash_target" : "hold_tactical_path_rejected";
                return true;
            }

            BotActionResult result = focusedAction.AutoAttackMode == "melee"
                && SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::StartOrSwitch,
                    tankFocus->GetGUID(), BotMeleeAutoAttack::Owner::Threat,
                    BotActionArbitration::Priority::ThreatControl,
                    "trash_focused_melee_engagement")
                        ? BotActionResult::Ok : BotActionResult::NoAction;
            if (focusedAction.Valid)
            {
                BotActionResult focusedResult = ExecuteProfileCombatAction(&state, bot, tankFocus, &focusedAction, 1, false);
                if (focusedResult != BotActionResult::NoAction)
                    result = focusedResult;
            }
            std::string raw = BuildRawJson(bot, tankFocus);
            std::string semantic = BuildSemanticJson(bot, tankFocus, "normal_dungeon_trash", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_gate", tankFocus,
                "focused_damage_during_trash_threat_build", raw.c_str(), semantic.c_str(),
                float(trashThreatControl.SecureTankCount), trashThreatControl.EngagedCount,
                result == BotActionResult::Ok && focusedAction.Valid ? focusedAction.SpellId : 0);
            situation = "normal_dungeon_trash";
            action = "focused_damage_during_trash_threat_build";
            state.WasInCombat = true;
            return true;
        }

        bot->InterruptNonMeleeSpells(false);
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Threat,
            BotActionArbitration::Priority::ThreatControl,
            "trash_threat_pickup_hold");
        if (Pet* pet = bot->GetPet())
            pet->AttackStop();
        bool moved = false;
        if (bot->GetExactDist2d(trashThreatControl.Tank) > 6.0f && !bot->IsFalling())
        {
            Unit* approachFrom = trashThreatControl.AreaTarget ? trashThreatControl.AreaTarget : trashThreatControl.Tank;
            Position pickup = trashThreatControl.Tank->GetFirstCollisionPosition(4.0f,
                approachFrom->GetAngle(trashThreatControl.Tank) - trashThreatControl.Tank->GetOrientation());
            moved = MoveBotToPoint(state, bot, pickup.GetPositionX(), pickup.GetPositionY(), pickup.GetPositionZ());
        }
        std::string raw = BuildRawJson(bot, trashThreatControl.AreaTarget);
        std::string semantic = BuildSemanticJson(bot, trashThreatControl.AreaTarget, "normal_dungeon_trash", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_threat_gate", trashThreatControl.AreaTarget,
            moved ? "stack_for_secure_trash_threat" : "hold_for_secure_trash_threat",
            raw.c_str(), semantic.c_str(), float(trashThreatControl.TankOwnedCount), trashThreatControl.EngagedCount);
        state.TargetGuid = trashThreatControl.Tank->GetVictim()
            ? trashThreatControl.Tank->GetVictim()->GetGUID() : ObjectGuid::Empty;
        target = trashThreatControl.Tank->GetVictim();
        situation = "validation_route_regroup";
        action = moved ? "stack_for_secure_trash_threat" : "hold_for_secure_trash_threat";
        return true;
    }
    if (tryValidationRouteAdds())
        return true;
    if (recordDefeatedValidationRoutePackMembers()
        || recordDefeatedValidationRouteTarget(target, "stale_target_seen_dead")
        || recordDefeatedValidationRouteTarget(bot->GetVictim(), "stale_victim_seen_dead"))
    {
        situation = "validation_route_recovery";
        action = "validation_route_recovery";
        target = nullptr;
        state.TargetGuid.Clear();
        return true;
    }
    uint32 completedPackCount = Party().ValidationRouteCompletedPackCount;
    if (completeDiscoveredPackIfReady())
    {
        situation = "normal_dungeon_trash";
        action = Party().ValidationRouteCompletedPackCount > completedPackCount
            ? "validation_route_pack_complete"
            : "validation_route_pack_terminal_wait";
        target = nullptr;
        return true;
    }
    if ((Cohort().Config.ValidationRouteKind != "boss" || trashThreatControl.EngagedCount > 0)
        && std::string(GetDungeonRole(bot)) == "dps"
        && !bot->getAttackers().empty()
        && !bot->HasUnitState(UNIT_STATE_CASTING)
        && !bot->IsFalling())
    {
        Player* tank = nullptr;
        for (WorldBotState const& cohortState : Party().Bots)
        {
            Player* member = GetLoadedBot(cohortState);
            if (member && member->IsAlive() && member->GetMap() == bot->GetMap()
                && member->GetGroup() == bot->GetGroup()
                && std::string(GetDungeonRole(member)) == "tank")
            {
                tank = member;
                break;
            }
        }
        Unit* nearestAttacker = nullptr;
        float nearestDistance = std::numeric_limits<float>::max();
        for (Unit* attacker : bot->getAttackers())
        {
            if (!attacker || !attacker->IsAlive() || attacker->GetMap() != bot->GetMap())
                continue;
            float distance = bot->GetExactDist2d(attacker);
            if (!nearestAttacker || distance < nearestDistance)
            {
                nearestAttacker = attacker;
                nearestDistance = distance;
            }
        }
        if (tank && nearestAttacker && bot->GetExactDist2d(tank) > 8.0f)
        {
            Position pickup = tank->GetFirstCollisionPosition(4.0f,
                nearestAttacker->GetAngle(tank) - tank->GetOrientation());
            if (bot->GetExactDist2d(pickup.GetPositionX(), pickup.GetPositionY()) > 2.0f
                && MoveBotToPoint(state, bot, pickup.GetPositionX(), pickup.GetPositionY(), pickup.GetPositionZ()))
            {
                SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                    BotMeleeAutoAttack::Owner::Threat,
                    BotActionArbitration::Priority::ThreatControl,
                    "trash_pickup_stack_hold");
                if (Pet* pet = bot->GetPet())
                    pet->AttackStop();
                std::string raw = BuildRawJson(bot, nearestAttacker);
                std::string semantic = BuildSemanticJson(bot, nearestAttacker, "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup", nearestAttacker, "dps_stack_for_trash_pickup",
                    raw.c_str(), semantic.c_str(), nearestDistance, Cohort().Config.ValidationRouteTargetEntry);
                Unit* pickupFocus = tank->GetVictim() ? tank->GetVictim() : nearestAttacker;
                state.TargetGuid = pickupFocus->GetGUID();
                target = pickupFocus;
                situation = "validation_route_regroup";
                action = "dps_stack_for_trash_pickup";
                return true;
            }
        }
    }
    // Threat rescue is route-kind agnostic. A boss can activate while a
    // prerequisite target is still alive (Ozruk does this during the approach
    // handoff), and suppressing this block on boss nodes left the new boss on
    // the healer while the tank continued the prerequisite rotation.
    if (std::string(GetDungeonRole(bot)) == "tank")
    {
        Player* defenseTarget = nullptr;
        uint8 defensePriority = 0;
        size_t defenseAttackerCount = 0;
        uint32 defenseGuid = std::numeric_limits<uint32>::max();
        for (WorldBotState const& cohortState : Party().Bots)
        {
            Player* member = GetLoadedBot(cohortState);
            if (!member || member == bot || !member->IsAlive() || member->GetMap() != bot->GetMap()
                || member->GetGroup() != bot->GetGroup())
                continue;
            std::string memberRole = GetDungeonRole(member);
            if (memberRole == "tank")
                continue;
            // Rerun124's terminal Flayer wave was explicitly visible in the
            // 80-yard victim scan for four decisions while the healer's native
            // attacker container remained empty. Carry that authoritative
            // listed-victim observation into the existing deterministic target
            // selector so the bounded Charge/Roar handoff starts immediately.
            size_t explicitAttackerCount =
                member == trashThreatControl.HealerTarget
                    ? trashThreatControl.HealerTargetCount : 0;
            size_t attackerCount = std::max(
                member->getAttackers().size(), explicitAttackerCount);
            if (!attackerCount)
                continue;
            uint8 priority = memberRole == "healer" ? 2 : 1;
            uint32 guid = member->GetGUID().GetCounter();
            if (!defenseTarget || priority > defensePriority
                || (priority == defensePriority && attackerCount > defenseAttackerCount)
                || (priority == defensePriority && attackerCount == defenseAttackerCount && guid < defenseGuid))
            {
                defenseTarget = member;
                defensePriority = priority;
                defenseAttackerCount = attackerCount;
                defenseGuid = guid;
            }
        }
        // Rerun153 proved the reactive cadence from rerun152 bounded every
        // healer-target episode below three seconds, but already-owned packs
        // could still flip during ordinary one-second area-threat fallbacks.
        // Keep the existing native Consecration, Righteous Defense, Avenger's
        // Shield, Salvation, and density ordering intact; start the same
        // bounded cadence while Protection still owns a three-hostile pack,
        // and preserve it through an observed multi-hostile healer handoff.
        bool protectionMultiHostileRetention = bot->getClass() == CLASS_PALADIN
            && trashThreatControl.EngagedCount >= 3
            && tankOwnsTrashMajority;
        bool protectionMultiHostileHealerPickup = bot->getClass() == CLASS_PALADIN
            && defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && defenseAttackerCount >= 2;
        if (protectionMultiHostileRetention
            || protectionMultiHostileHealerPickup)
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
        // Rerun95 reached an ordinary-trash Azil follower overlap with 52
        // engaged hostiles. The boss-add resolver's native Feral defensive
        // submission did not apply because this manifest node is trash, and
        // the tank died while still owning 36 followers. Rerun96 then showed
        // that a 90-percent health sample is still too late for a 49-follower
        // simultaneous swing: the tank was above the threshold in the final
        // decision and dead before the next one. Reuse the native off-GCD rule
        // proactively before bounded pickup movement consumes the decision.
        // Rerun123 proved twelve is too early: the Feral survived the 12-14
        // precursor after spending its defensive, then died when the sustained
        // 30-40-hostile Flayer wave arrived about twenty seconds later. Reserve
        // the same native action until 24 engaged hostiles, above that observed
        // precursor and below the failing wave's first 28-30-hostile samples.
        if (bot->getClass() == CLASS_DRUID
            && trashThreatControl.EngagedCount >= 24
            && !bot->HasAura(61336) && !bot->HasAura(22812))
        {
            std::array<uint32, 2> defensiveSpells = { 61336, 22812 };
            for (uint32 defensiveSpellId : defensiveSpells)
                if (bot->HasSpell(defensiveSpellId)
                    && TryCastFriendlySpell(bot, bot, defensiveSpellId))
                {
                    std::string raw = BuildRawJson(
                        bot, trashThreatControl.AreaTarget);
                    std::string semantic = BuildSemanticJson(
                        bot, trashThreatControl.AreaTarget,
                        "normal_dungeon_trash", &power, stage, activity);
                    RecordEvent(state, bot, "defensive", bot,
                        "tank_trash_swarm_defensive",
                        raw.c_str(), semantic.c_str(), UnitHealthPct(bot),
                        trashThreatControl.EngagedCount, defensiveSpellId);
                    break;
                }
        }
        // Rerun105 passed the all-hostile retention floor, but both remaining
        // generation-13 exposure bursts flipped already-eligible identities
        // immediately after a healer cast. In the preceding samples the Feral
        // owned the whole large wave while fewer than ninety percent had the
        // existing 2.5x secure-threat margin; the ordinary resolver then moved
        // toward density instead of submitting its ready native Swipe cycle.
        // Reinforce that margin before movement when a legal local Swipe is
        // available. Remote or cooldown cases still fall through unchanged.
        Unit* feralSecureMarginTarget = nullptr;
        uint32 feralSecureMarginClusterCount = 0;
        float feralSecureMarginDistance =
            std::numeric_limits<float>::max();
        uint32 feralSecureMarginGuid =
            std::numeric_limits<uint32>::max();
        if (bot->getClass() == CLASS_DRUID)
            for (Unit* candidate :
                trashThreatControl.InsecureTankOwnedTargets)
            {
                if (!candidate || !candidate->IsAlive()
                    || candidate->GetMap() != bot->GetMap()
                    || candidate->GetVictim() != bot
                    || !bot->IsValidAttackTarget(candidate))
                    continue;
                uint32 clusterCount = 0;
                for (Unit* neighbor :
                    trashThreatControl.InsecureTankOwnedTargets)
                    if (neighbor && neighbor->IsAlive()
                        && neighbor->GetMap() == bot->GetMap()
                        && neighbor->GetVictim() == bot
                        && bot->IsValidAttackTarget(neighbor)
                        && candidate->GetExactDist2d(neighbor) <= 10.0f)
                        ++clusterCount;
                float distance = bot->GetExactDist(candidate);
                uint32 guid = candidate->GetGUID().GetCounter();
                if (!feralSecureMarginTarget
                    || clusterCount > feralSecureMarginClusterCount
                    || (clusterCount == feralSecureMarginClusterCount
                        && (distance < feralSecureMarginDistance
                            || (distance == feralSecureMarginDistance
                                && guid < feralSecureMarginGuid))))
                {
                    feralSecureMarginTarget = candidate;
                    feralSecureMarginClusterCount = clusterCount;
                    feralSecureMarginDistance = distance;
                    feralSecureMarginGuid = guid;
                }
            }
        bool feralCurrentHealerThreat = defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && defenseAttackerCount >= 1;
        bool feralHealerHandoffPending = feralCurrentHealerThreat
            && state.FeralHealerThreatHandoffTargetGuid
                == defenseTarget->GetGUID()
            && state.FeralHealerThreatHandoffUntilMs > NowMs();
        // Rerun149 proved the global insecure predicate could submit Swipe at
        // the nearest generic area target while a different, already-aged
        // remote Flayer cluster remained below the same 2.5x secure margin.
        // Select that vulnerable cluster deterministically and establish native
        // Swipe range before spending its GCD. If a healer handoff is already
        // active, preserve the existing Roar recovery's first legal GCD.
        // Rerun155 recovered one of three healer-owned Flayers with Growl, then
        // spent seven decisions approaching an insecure tank-owned cluster
        // while the other two crossed the dwell limit. Current healer ownership
        // is higher authority even when no handoff reservation exists yet; let
        // the identity-scoped rescue controller below own that same decision.
        // Rerun176 then recorded 45 of generation 13's 53 healer-exposure
        // samples when fully tank-owned packs of seven and eleven Flayers were
        // below this branch's redundant twelve-hostile floor. One later heal
        // flipped those already-aged insecure identities before reactive pickup.
        // The insecure-swarm predicate already proves at least three engaged
        // hostiles, so apply this unchanged native secure-margin action across
        // that complete predicate instead of only its largest subsets.
        if (bot->getClass() == CLASS_DRUID
            && trashThreatControl.EngagedCount >= 3
            && tankOwnsTrashMajority && insecureTrashSwarm
            && feralSecureMarginTarget && bot->HasSpell(779)
            && !feralHealerHandoffPending
            && !feralCurrentHealerThreat)
        {
            if ((feralSecureMarginDistance > 8.0f
                    || !bot->IsWithinLOSInMap(feralSecureMarginTarget))
                && !bot->HasUnitState(UNIT_STATE_CASTING)
                && !bot->IsFalling()
                && MoveBotToProfileRange(
                    state, bot, feralSecureMarginTarget))
            {
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                std::string raw = BuildRawJson(
                    bot, feralSecureMarginTarget);
                std::string semantic = BuildSemanticJson(
                    bot, feralSecureMarginTarget,
                    "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot,
                    "validation_route_threat_pickup",
                    feralSecureMarginTarget,
                    "feral_approach_insecure_trash_threat_cluster",
                    raw.c_str(), semantic.c_str(),
                    float(feralSecureMarginClusterCount),
                    trashThreatControl.EngagedCount, 779);
                state.TargetGuid = feralSecureMarginTarget->GetGUID();
                state.WasInCombat = true;
                target = feralSecureMarginTarget;
                situation = "normal_dungeon_trash";
                action =
                    "feral_approach_insecure_trash_threat_cluster";
                return true;
            }
            if (TryCastCombatSpell(bot, feralSecureMarginTarget, 779))
            {
                std::string raw = BuildRawJson(
                    bot, feralSecureMarginTarget);
                std::string semantic = BuildSemanticJson(
                    bot, feralSecureMarginTarget,
                    "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    feralSecureMarginTarget,
                    "feral_swipe_secure_trash_threat_margin",
                    raw.c_str(), semantic.c_str(),
                    float(trashThreatControl.SecureTankCount),
                    trashThreatControl.EngagedCount, 779);
                state.TargetGuid = feralSecureMarginTarget->GetGUID();
                state.WasInCombat = true;
                target = feralSecureMarginTarget;
                situation = "normal_dungeon_trash";
                action = "feral_swipe_secure_trash_threat_margin";
                return true;
            }
        }
        // Rerun112 localized the all-hostile retention failure to ordinary
        // opening packs on DPS: five eligible identities remained loose while
        // the healer-only Feral rescue was inapplicable and the generic area
        // cycle recovered them one at a time. Rerun113 then showed that an
        // unbounded rescue chased remote DPS attackers while 21--42 hostiles
        // were engaged, preempting the established density/healer controller.
        // Keep the targeted rescue inside the existing tactical radius and
        // small-pack envelope. This does not assign victims or change threat.
        if (defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) != "healer"
            && bot->getClass() == CLASS_DRUID
            && trashThreatControl.EngagedCount >= 1
            && trashThreatControl.EngagedCount <= 8)
        {
            std::vector<Unit*> partyAttackers;
            for (Unit* attacker : defenseTarget->getAttackers())
                if (attacker && attacker->IsAlive()
                    && attacker->GetMap() == bot->GetMap()
                    && attacker->GetVictim() == defenseTarget
                    && bot->IsValidAttackTarget(attacker)
                    && bot->IsWithinDistInMap(attacker, 45.0f))
                    partyAttackers.push_back(attacker);

            if (partyAttackers.size() == 1 && bot->HasSpell(6795)
                && TryCastCombatSpell(bot, partyAttackers.front(), 6795))
            {
                Unit* attacker = partyAttackers.front();
                std::string raw = BuildRawJson(bot, attacker);
                std::string semantic = BuildSemanticJson(
                    bot, attacker, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    attacker, "feral_growl_lingering_party_trash_attacker",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist(attacker), 1.0f, 6795);
                state.TargetGuid = attacker->GetGUID();
                state.WasInCombat = true;
                target = attacker;
                situation = "normal_dungeon_trash";
                action = "feral_growl_lingering_party_trash_attacker";
                return true;
            }

            Unit* nearbyMissingRoarAttacker = nullptr;
            uint32 nearbyMissingRoarCount = 0;
            float nearbyDistance = std::numeric_limits<float>::max();
            uint32 nearbyGuid = std::numeric_limits<uint32>::max();
            for (Unit* attacker : partyAttackers)
            {
                float distance = bot->GetExactDist(attacker);
                uint32 guid = attacker->GetGUID().GetCounter();
                if (bot->GetExactDist2d(attacker) <= 10.0f
                    && !attacker->HasAura(99, bot->GetGUID()))
                {
                    ++nearbyMissingRoarCount;
                    if (!nearbyMissingRoarAttacker
                        || distance < nearbyDistance
                        || (distance == nearbyDistance && guid < nearbyGuid))
                    {
                        nearbyMissingRoarAttacker = attacker;
                        nearbyDistance = distance;
                        nearbyGuid = guid;
                    }
                }
            }
            if (nearbyMissingRoarCount >= 2 && bot->HasSpell(99)
                && TryCastFriendlySpell(bot, bot, 99))
            {
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 500);
                std::string raw = BuildRawJson(
                    bot, nearbyMissingRoarAttacker);
                std::string semantic = BuildSemanticJson(
                    bot, nearbyMissingRoarAttacker,
                    "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    nearbyMissingRoarAttacker,
                    "feral_demoralizing_roar_party_trash_pickup",
                    raw.c_str(), semantic.c_str(),
                    float(nearbyMissingRoarCount),
                    float(partyAttackers.size()), 99);
                state.TargetGuid = nearbyMissingRoarAttacker->GetGUID();
                state.WasInCombat = true;
                target = nearbyMissingRoarAttacker;
                situation = "normal_dungeon_trash";
                action = "feral_demoralizing_roar_party_trash_pickup";
                return true;
            }

            Unit* remoteClusterAnchor = nullptr;
            uint32 remoteClusterCount = 0;
            float remoteDistance = std::numeric_limits<float>::max();
            uint32 remoteGuid = std::numeric_limits<uint32>::max();
            for (Unit* candidate : partyAttackers)
            {
                float distance = bot->GetExactDist(candidate);
                if (distance <= 8.0f)
                    continue;
                uint32 clusterCount = 0;
                for (Unit* neighbor : partyAttackers)
                    if (candidate->GetExactDist2d(neighbor) <= 10.0f)
                        ++clusterCount;
                uint32 guid = candidate->GetGUID().GetCounter();
                if (!remoteClusterAnchor
                    || clusterCount > remoteClusterCount
                    || (clusterCount == remoteClusterCount
                        && (distance < remoteDistance
                            || (distance == remoteDistance
                                && guid < remoteGuid))))
                {
                    remoteClusterAnchor = candidate;
                    remoteClusterCount = clusterCount;
                    remoteDistance = distance;
                    remoteGuid = guid;
                }
            }
            if (remoteClusterAnchor && bot->HasSpell(16979)
                && TryCastCombatSpell(bot, remoteClusterAnchor, 16979))
            {
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 500);
                std::string raw = BuildRawJson(bot, remoteClusterAnchor);
                std::string semantic = BuildSemanticJson(
                    bot, remoteClusterAnchor, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    remoteClusterAnchor,
                    "feral_charge_remote_party_trash_cluster_pickup",
                    raw.c_str(), semantic.c_str(), remoteDistance,
                    float(partyAttackers.size()), 16979);
                state.TargetGuid = remoteClusterAnchor->GetGUID();
                state.WasInCombat = true;
                target = remoteClusterAnchor;
                situation = "normal_dungeon_trash";
                action = "feral_charge_remote_party_trash_cluster_pickup";
                return true;
            }
            if (remoteClusterAnchor
                && !bot->HasUnitState(UNIT_STATE_CASTING)
                && !bot->IsFalling()
                && MoveBotToPoint(state, bot,
                    remoteClusterAnchor->GetPositionX(),
                    remoteClusterAnchor->GetPositionY(),
                    remoteClusterAnchor->GetPositionZ()))
            {
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 500);
                std::string raw = BuildRawJson(bot, remoteClusterAnchor);
                std::string semantic = BuildSemanticJson(
                    bot, remoteClusterAnchor, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    remoteClusterAnchor,
                    "feral_move_remote_party_trash_cluster_pickup",
                    raw.c_str(), semantic.c_str(), remoteDistance,
                    float(partyAttackers.size()));
                state.TargetGuid = remoteClusterAnchor->GetGUID();
                state.WasInCombat = true;
                target = remoteClusterAnchor;
                situation = "normal_dungeon_trash";
                action = "feral_move_remote_party_trash_cluster_pickup";
                return true;
            }
        }
        uint64 feralTrashHandoffNowMs = NowMs();
        bool feralTrashHandoffExpired =
            state.FeralHealerThreatHandoffUntilMs
            && state.FeralHealerThreatHandoffUntilMs <= feralTrashHandoffNowMs;
        Unit* feralTrashHandoffAnchor = nullptr;
        if (!state.FeralHealerThreatHandoffAnchorGuid.IsEmpty())
            feralTrashHandoffAnchor = ObjectAccessor::GetUnit(
                *bot, state.FeralHealerThreatHandoffAnchorGuid);
        Unit* feralTrashExpiredHandoffAnchor =
            feralTrashHandoffExpired && feralTrashHandoffAnchor
                && feralTrashHandoffAnchor->IsAlive()
                && feralTrashHandoffAnchor->GetMap() == bot->GetMap()
            ? feralTrashHandoffAnchor : nullptr;
        bool feralTrashExpiredClusterUnresolved = false;
        if (feralTrashExpiredHandoffAnchor && defenseTarget)
            for (Unit* attacker : defenseTarget->getAttackers())
                if (attacker && attacker->IsAlive()
                    && attacker->GetMap() == bot->GetMap()
                    && attacker->GetVictim() == defenseTarget
                    && bot->IsValidAttackTarget(attacker)
                    && feralTrashExpiredHandoffAnchor->GetExactDist2d(attacker)
                        <= 10.0f)
                {
                    feralTrashExpiredClusterUnresolved = true;
                    break;
                }
        bool feralTrashChargeInFlight = defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && bot->getClass() == CLASS_DRUID
            && state.FeralChargePickupUntilMs > feralTrashHandoffNowMs
            && !state.FeralChargePickupTargetGuid.IsEmpty();
        Unit* feralTrashChargeTarget = feralTrashChargeInFlight
            ? ObjectAccessor::GetUnit(*bot, state.FeralChargePickupTargetGuid)
            : nullptr;
        bool feralTrashChargeArrived = false;
        if (feralTrashChargeInFlight
            && (!feralTrashChargeTarget || !feralTrashChargeTarget->IsAlive()
                || feralTrashChargeTarget->GetMap() != bot->GetMap()
                || !bot->IsValidAttackTarget(feralTrashChargeTarget)))
        {
            state.FeralChargePickupTargetGuid.Clear();
            state.FeralChargePickupUntilMs = 0;
            feralTrashChargeInFlight = false;
            feralTrashChargeTarget = nullptr;
        }
        else if (feralTrashChargeInFlight
            && bot->GetExactDist2d(feralTrashChargeTarget) > 10.0f)
        {
            std::string raw = BuildRawJson(bot, feralTrashChargeTarget);
            std::string semantic = BuildSemanticJson(
                bot, feralTrashChargeTarget, "normal_dungeon_trash",
                &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup",
                feralTrashChargeTarget,
                "feral_charge_remote_healer_trash_cluster_in_flight",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(feralTrashChargeTarget),
                float(defenseAttackerCount), 16979);
            state.TargetGuid = feralTrashChargeTarget->GetGUID();
            target = feralTrashChargeTarget;
            situation = "normal_dungeon_trash";
            action = "feral_charge_remote_healer_trash_cluster_in_flight";
            state.DecisionTimer = std::min<uint32>(state.DecisionTimer, 250);
            return true;
        }
        else if (feralTrashChargeInFlight)
            feralTrashChargeArrived = true;
        else if (!state.FeralChargePickupTargetGuid.IsEmpty()
            || state.FeralChargePickupUntilMs)
        {
            state.FeralChargePickupTargetGuid.Clear();
            state.FeralChargePickupUntilMs = 0;
        }
        // Rerun95 also proved that always preserving the densest remote
        // cluster can starve older ranged stragglers behind each new spawn
        // burst. Once the Feral has secured an 80 percent victim majority,
        // keep the same bounded handoff but rebind it deterministically to the
        // lowest-GUID healer-owned follower. This targets the oldest remaining
        // identity without assigning a victim or extending the reservation.
        bool feralTrashOwnsSecureVictimMajority =
            trashThreatControl.EngagedCount > 0
            && trashThreatControl.TankOwnedCount * 10
                >= trashThreatControl.EngagedCount * 8;
        if (feralTrashOwnsSecureVictimMajority && defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && bot->getClass() == CLASS_DRUID
            && state.FeralHealerThreatHandoffUntilMs > feralTrashHandoffNowMs)
        {
            Unit* oldestHealerAttacker = nullptr;
            uint32 oldestHealerAttackerGuid =
                std::numeric_limits<uint32>::max();
            for (Unit* attacker : defenseTarget->getAttackers())
                if (attacker && attacker->IsAlive()
                    && attacker->GetMap() == bot->GetMap()
                    && attacker->GetVictim() == defenseTarget
                    && bot->IsValidAttackTarget(attacker)
                    && attacker->GetGUID().GetCounter()
                        < oldestHealerAttackerGuid)
                {
                    oldestHealerAttacker = attacker;
                    oldestHealerAttackerGuid =
                        attacker->GetGUID().GetCounter();
                }
            if (oldestHealerAttacker)
            {
                state.FeralHealerThreatHandoffAnchorGuid =
                    oldestHealerAttacker->GetGUID();
                feralTrashHandoffAnchor = oldestHealerAttacker;
            }
        }
        if (defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && feralTrashHandoffAnchor
            && feralTrashHandoffAnchor->IsAlive()
            && feralTrashHandoffAnchor->GetMap() == bot->GetMap()
            && feralTrashHandoffAnchor->GetVictim() != defenseTarget
            && state.FeralHealerThreatHandoffUntilMs > feralTrashHandoffNowMs)
        {
            // A transfer can flip the selected hostile while neighboring
            // members of the same remote cluster still own the healer. Keep
            // the bounded cluster rendezvous stable by rebinding only within
            // the original anchor's ten-yard neighborhood.
            Unit* reboundAnchor = nullptr;
            uint32 reboundGuid = std::numeric_limits<uint32>::max();
            for (Unit* attacker : defenseTarget->getAttackers())
                if (attacker && attacker->IsAlive()
                    && attacker->GetMap() == bot->GetMap()
                    && attacker->GetVictim() == defenseTarget
                    && bot->IsValidAttackTarget(attacker)
                    && feralTrashHandoffAnchor->GetExactDist2d(attacker)
                        <= 10.0f
                    && attacker->GetGUID().GetCounter() < reboundGuid)
                {
                    reboundAnchor = attacker;
                    reboundGuid = attacker->GetGUID().GetCounter();
                }
            if (reboundAnchor)
            {
                state.FeralHealerThreatHandoffAnchorGuid =
                    reboundAnchor->GetGUID();
                feralTrashHandoffAnchor = reboundAnchor;
            }
        }
        bool feralTrashHandoffActive = defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && bot->getClass() == CLASS_DRUID
            && state.FeralHealerThreatHandoffUntilMs > feralTrashHandoffNowMs
            && state.FeralHealerThreatHandoffTargetGuid
                == defenseTarget->GetGUID()
            && feralTrashHandoffAnchor
            && feralTrashHandoffAnchor->IsAlive()
            && feralTrashHandoffAnchor->GetMap() == bot->GetMap()
            && feralTrashHandoffAnchor->GetVictim() == defenseTarget
            && bot->IsValidAttackTarget(feralTrashHandoffAnchor)
            && defenseAttackerCount >= 1;
        if (!feralTrashHandoffActive && !feralTrashExpiredClusterUnresolved
            && (!state.FeralHealerThreatHandoffTargetGuid.IsEmpty()
                || !state.FeralHealerThreatHandoffAnchorGuid.IsEmpty()
                || state.FeralHealerThreatHandoffUntilMs
                || state.FeralHealerThreatHandoffRemoteCluster))
        {
            state.FeralHealerThreatHandoffTargetGuid.Clear();
            state.FeralHealerThreatHandoffAnchorGuid.Clear();
            state.FeralHealerThreatHandoffUntilMs = 0;
            state.FeralHealerThreatHandoffRemoteCluster = false;
            feralTrashHandoffAnchor = nullptr;
        }
        bool feralTrashHandoffArrived = false;
        if (feralTrashHandoffActive)
        {
            // Movement ownership was changed to the collision-safe stationary
            // healer ring after rerun100, but arrival still measured only the
            // remote hostile GUID. Rerun102 accepted sixteen consecutive ring
            // movements without reaching that moving hostile. Complete the
            // same bounded pre-Roar handoff at its actual eight-yard destination
            // while retaining hostile proximity as alternate arrival proof.
            // A post-Roar remote-cluster phase instead owns the hostile anchor;
            // rerun103 proved healer-ring arrival would cancel that accepted
            // path immediately after the cast.
            // Rerun109 proved that the one-local arrival exception fragmented
            // large Flayer packs into 42 small Roars and regressed retention.
            // Do not require the selected moving anchor itself, but require an
            // identity-valid nearby majority still missing this Feral's Roar
            // aura before yielding the accepted handoff to area threat.
            uint32 currentHealerOwnedDuringHandoff = 0;
            uint32 localMissingRoarDuringHandoff = 0;
            for (Unit* attacker : defenseTarget->getAttackers())
                if (attacker && attacker->IsAlive()
                    && attacker->GetMap() == bot->GetMap()
                    && attacker->GetVictim() == defenseTarget
                    && bot->IsValidAttackTarget(attacker))
                {
                    ++currentHealerOwnedDuringHandoff;
                    if (bot->GetExactDist2d(attacker) <= 10.0f
                        && !attacker->HasAura(99, bot->GetGUID()))
                        ++localMissingRoarDuringHandoff;
                }
            bool localMissingRoarCoversMajority =
                localMissingRoarDuringHandoff >= 2
                && localMissingRoarDuringHandoff * 2
                    >= currentHealerOwnedDuringHandoff;
            // Rerun123's opening corridor reached one isolated remote anchor
            // while all eight hostiles still owned the healer. Anchor distance
            // alone entered six Roar-hold decisions without a useful local
            // cast. A remote handoff now uses the already-proven missing-Roar
            // majority as its sole arrival proof; only the stationary-healer
            // form retains ring/anchor proximity as an alternate proof.
            feralTrashHandoffArrived = localMissingRoarCoversMajority
                || (!state.FeralHealerThreatHandoffRemoteCluster
                    && (bot->GetExactDist2d(defenseTarget) <= 9.0f
                        || bot->GetExactDist2d(feralTrashHandoffAnchor)
                            <= 10.0f));
            if (!feralTrashHandoffArrived
                && !bot->HasUnitState(UNIT_STATE_CASTING)
                && !bot->IsFalling())
            {
                // Rerun109 used only eight Charges through a six-minute Flayer
                // node because an active post-Roar handoff returned ground
                // movement before the ordinary Charge branch below.  Reuse
                // native Charge against the already-validated remote anchor;
                // the strict hazard resolver has already run and the existing
                // bounded reservation remains unchanged.
                if (state.FeralHealerThreatHandoffRemoteCluster
                    && bot->GetExactDist(feralTrashHandoffAnchor) > 8.0f
                    && bot->HasSpell(16979)
                    && TryCastCombatSpell(
                        bot, feralTrashHandoffAnchor, 16979))
                {
                    std::string raw = BuildRawJson(
                        bot, feralTrashHandoffAnchor);
                    std::string semantic = BuildSemanticJson(
                        bot, feralTrashHandoffAnchor,
                        "normal_dungeon_trash", &power, stage, activity);
                    RecordEvent(state, bot,
                        "validation_route_threat_pickup",
                        feralTrashHandoffAnchor,
                        "feral_charge_remote_healer_trash_cluster_active_handoff",
                        raw.c_str(), semantic.c_str(),
                        bot->GetExactDist(feralTrashHandoffAnchor),
                        float(defenseAttackerCount), 16979);
                    state.FeralChargePickupTargetGuid =
                        feralTrashHandoffAnchor->GetGUID();
                    state.FeralChargePickupUntilMs = NowMs() + 2500;
                    state.DecisionTimer = std::min<uint32>(
                        state.DecisionTimer, 250);
                    state.TargetGuid = feralTrashHandoffAnchor->GetGUID();
                    state.WasInCombat = true;
                    target = feralTrashHandoffAnchor;
                    situation = "normal_dungeon_trash";
                    action =
                        "feral_charge_remote_healer_trash_cluster_active_handoff";
                    return true;
                }
                // Rerun120 passed the Feral retention floor after the Swipe
                // threat-margin correction, but the exact remote-anchor path
                // still consumed about 3.5 seconds before the first legal
                // Roar. Preserve the proven hostile identity and stable path
                // reservation while stopping inside Roar's collision-safe
                // range. Rerun122 localized its entire remaining exposure to
                // Azil and observed zero healer exposure at the ordinary-trash
                // Flayer node, so retain the original eight-yard stand-off for
                // both rendezvous forms.
                Position roarIntercept;
                if (state.FeralHealerThreatHandoffRemoteCluster)
                    roarIntercept =
                        feralTrashHandoffAnchor->GetFirstCollisionPosition(
                            8.0f,
                            feralTrashHandoffAnchor->GetAngle(bot)
                                - feralTrashHandoffAnchor->GetOrientation());
                else
                    roarIntercept = defenseTarget->GetFirstCollisionPosition(
                        8.0f,
                        defenseTarget->GetAngle(bot)
                            - defenseTarget->GetOrientation());
                bool continuingRemotePath =
                    state.FeralHealerThreatHandoffRemoteCluster
                    && state.ActivePathValid && state.IsMoving
                    && feralTrashHandoffAnchor->GetExactDist2d(
                        state.ActivePathToX, state.ActivePathToY) <= 10.0f;
                bool moved = continuingRemotePath || MoveBotToPoint(state, bot,
                    roarIntercept.GetPositionX(),
                    roarIntercept.GetPositionY(),
                    roarIntercept.GetPositionZ());
                if (moved)
                    state.DecisionTimer = std::min<uint32>(
                        state.DecisionTimer, 250);
                std::string raw = BuildRawJson(bot, feralTrashHandoffAnchor);
                std::string semantic = BuildSemanticJson(
                    bot, feralTrashHandoffAnchor, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    feralTrashHandoffAnchor,
                    moved
                        ? "feral_continue_remote_healer_trash_cluster_handoff"
                        : "feral_remote_healer_trash_cluster_path_rejected",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist2d(feralTrashHandoffAnchor),
                    float(defenseAttackerCount));
                if (!moved)
                {
                    // Keep path rejection fail-closed: end only this bounded
                    // handoff and let the existing legal local threat recovery
                    // below own the same decision. Rerun130 proved that a stale
                    // LastRecoveryResult alone cannot establish this condition.
                    state.FeralHealerThreatHandoffTargetGuid.Clear();
                    state.FeralHealerThreatHandoffAnchorGuid.Clear();
                    state.FeralHealerThreatHandoffUntilMs = 0;
                    state.FeralHealerThreatHandoffRemoteCluster = false;
                }
                else
                {
                    state.TargetGuid = feralTrashHandoffAnchor->GetGUID();
                    target = feralTrashHandoffAnchor;
                    situation = "normal_dungeon_trash";
                    action =
                        "feral_continue_remote_healer_trash_cluster_handoff";
                    return true;
                }
            }
            if (feralTrashHandoffArrived)
                bot->StopMoving();
        }
        // Rerun92 exposed 11-45-hostile split Flayer waves where ordinary
        // ground movement needed three or four decisions before the first
        // remote-cluster Roar. Reuse native Feral Charge before that movement,
        // selecting the deterministic densest healer-owned cluster and
        // preserving the charged target above until arrival. Exact hazard
        // movement already ran and remains the higher authority. Rerun105 also
        // isolated one remote surviving attacker for 4032 ms: out-of-range
        // Growl fell through to ordinary route movement because this bounded
        // Charge path required two attackers. The same identity-safe handoff
        // is valid for that single remote healer attacker.
        // Rerun127 showed that selecting another remote anchor immediately
        // after Charge can bypass the nearby Roar/arrival hold below.
        // Rerun130 then showed that reacquiring the just-expired cluster can
        // join nominally bounded handoffs into one longer ownership interval.
        // Rerun131 proved that blocking every selector on expiry instead hands
        // large Flayer waves to fragmenting local Roar/density recovery.
        // Rerun133 proved distinct anchors can still chain while the previously
        // reserved cluster remains healer-owned. Yield only while that exact
        // expired cluster is unresolved; genuinely distinct clusters become
        // eligible again as soon as its current-victim identities clear.
        if (!feralTrashHandoffActive && !feralTrashChargeArrived
            && !feralTrashExpiredClusterUnresolved && defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && bot->getClass() == CLASS_DRUID
            && defenseAttackerCount >= 1 && bot->HasSpell(16979))
        {
            Unit* chargeAnchor = nullptr;
            uint32 chargeClusterCount = 0;
            float chargeDistance = std::numeric_limits<float>::max();
            uint32 chargeGuid = std::numeric_limits<uint32>::max();
            bool chargeAnchorInNativeBand = false;
            for (Unit* candidate : defenseTarget->getAttackers())
            {
                if (!candidate || !candidate->IsAlive()
                    || candidate->GetMap() != bot->GetMap()
                    || candidate->GetVictim() != defenseTarget
                    || !bot->IsValidAttackTarget(candidate))
                    continue;
                if (feralTrashExpiredHandoffAnchor
                    && feralTrashExpiredHandoffAnchor->GetExactDist2d(candidate)
                        <= 10.0f)
                    continue;
                float distance = bot->GetExactDist(candidate);
                if (distance <= 8.0f)
                    continue;
                uint32 clusterCount = 0;
                for (Unit* neighbor : defenseTarget->getAttackers())
                    if (neighbor && neighbor->IsAlive()
                        && neighbor->GetMap() == bot->GetMap()
                        && neighbor->GetVictim() == defenseTarget
                        && bot->IsValidAttackTarget(neighbor)
                        && candidate->GetExactDist2d(neighbor) <= 10.0f)
                        ++clusterCount;
                bool candidateInNativeChargeBand = false;
                if (SpellInfo const* chargeInfo =
                        sSpellMgr->GetSpellInfo(16979))
                    candidateInNativeChargeBand =
                        bot->IsWithinLOSInMap(candidate)
                        && distance <= bot->GetSpellMaxRangeForTarget(
                            candidate, chargeInfo);
                uint32 guid = candidate->GetGUID().GetCounter();
                bool sameChargeBand = candidateInNativeChargeBand
                    == chargeAnchorInNativeBand;
                bool betterClusterCandidate =
                    clusterCount > chargeClusterCount
                    || (clusterCount == chargeClusterCount
                        && (distance < chargeDistance
                            || (distance == chargeDistance
                                && guid < chargeGuid)));
                if (!chargeAnchor
                    || (candidateInNativeChargeBand
                        && !chargeAnchorInNativeBand)
                    || (sameChargeBand && betterClusterCandidate))
                {
                    chargeAnchor = candidate;
                    chargeClusterCount = clusterCount;
                    chargeDistance = distance;
                    chargeGuid = guid;
                    chargeAnchorInNativeBand =
                        candidateInNativeChargeBand;
                }
            }
            if (chargeAnchor
                && TryCastCombatSpell(bot, chargeAnchor, 16979))
            {
                std::string raw = BuildRawJson(bot, chargeAnchor);
                std::string semantic = BuildSemanticJson(
                    bot, chargeAnchor, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    chargeAnchor,
                    "feral_charge_remote_healer_trash_cluster_handoff",
                    raw.c_str(), semantic.c_str(), chargeDistance,
                    float(defenseAttackerCount), 16979);
                state.FeralChargePickupTargetGuid = chargeAnchor->GetGUID();
                state.FeralChargePickupUntilMs = NowMs() + 2500;
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                state.TargetGuid = chargeAnchor->GetGUID();
                state.WasInCombat = true;
                target = chargeAnchor;
                situation = "normal_dungeon_trash";
                action = "feral_charge_remote_healer_trash_cluster_handoff";
                return true;
            }
            // Rerun96 first observed ten healer-owned followers immediately
            // after strict hazard movement, while Charge was on cooldown and
            // fewer than two followers were inside Roar range. Falling through
            // to generic density movement delayed the first legal Roar to 3014
            // ms. Rerun132 then showed that hazard handling can consume 1522 ms
            // before this fallback, after which a fresh 2.5-second reservation
            // delays the first Roar beyond the per-hostile dwell ceiling. Bind
            // the already-selected deterministic cluster for one second at the
            // existing 250-ms arrival cadence; strict hazard movement has already
            // run and path rejection still falls through without changing victims
            // or extending the reservation.
            if (chargeAnchor
                && !bot->HasUnitState(UNIT_STATE_CASTING)
                && !bot->IsFalling())
            {
                // Rerun104 proved the healer-ring fallback can declare arrival
                // with only two of thirteen attackers in Roar range. The
                // post-Roar remote phase now preserves an accepted endpoint;
                // use that same proven contract before the first Roar so the
                // selected densest cluster, rather than the healer ring, owns
                // the bounded rendezvous. Rerun120 proved that walking to the
                // anchor's exact point spends the dwell budget unnecessarily;
                // the native Roar needs only this collision-safe stand-off.
                // Rerun121 reduced the global dwell maximum to 3026 ms at
                // eight yards; use nine yards to remove only that final yard
                // of travel while remaining inside Roar's ten-yard range.
                Position roarIntercept =
                    chargeAnchor->GetFirstCollisionPosition(
                        9.0f,
                        chargeAnchor->GetAngle(bot)
                            - chargeAnchor->GetOrientation());
                bool movedToRemoteCluster = MoveBotToPoint(state, bot,
                        roarIntercept.GetPositionX(),
                        roarIntercept.GetPositionY(),
                        roarIntercept.GetPositionZ());
                if (movedToRemoteCluster)
                {
                    state.FeralHealerThreatHandoffTargetGuid =
                        defenseTarget->GetGUID();
                    state.FeralHealerThreatHandoffAnchorGuid =
                        chargeAnchor->GetGUID();
                    state.FeralHealerThreatHandoffUntilMs =
                        feralTrashHandoffNowMs + 1000;
                    state.FeralHealerThreatHandoffRemoteCluster = true;
                    state.DecisionTimer = std::min<uint32>(
                        state.DecisionTimer, 250);
                    std::string raw = BuildRawJson(bot, chargeAnchor);
                    std::string semantic = BuildSemanticJson(
                        bot, chargeAnchor, "normal_dungeon_trash",
                        &power, stage, activity);
                    RecordEvent(state, bot,
                        "validation_route_threat_pickup", chargeAnchor,
                        "feral_move_remote_healer_trash_cluster_pre_roar",
                        raw.c_str(), semantic.c_str(), chargeDistance,
                        float(defenseAttackerCount));
                    state.TargetGuid = chargeAnchor->GetGUID();
                    target = chargeAnchor;
                    situation = "normal_dungeon_trash";
                    action =
                        "feral_move_remote_healer_trash_cluster_pre_roar";
                    return true;
                }
            }
        }
        // Rerun54 proved the boss-add Roar pickup but also isolated the global
        // healer-dwell maximum to ordinary crystalspawn trash, where that
        // specialized resolver never runs. Reuse the same native ten-yard,
        // healer-owned, aura-bounded action here before the ordinary profile
        // area cycle. This does not assign victims or move the healer; it only
        // submits the explicit spell-99 rule after the Feral has reached at
        // least two of the healer's listed attackers.
        if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && bot->getClass() == CLASS_DRUID
            && defenseAttackerCount >= 2 && bot->HasSpell(99))
        {
            uint32 nearbyHealerOwnedCount = 0;
            bool missingOwnedRoar = false;
            Unit* nearbyHealerOwnedAttacker = nullptr;
            float nearbyHealerOwnedDistance = std::numeric_limits<float>::max();
            uint32 nearbyHealerOwnedGuid = std::numeric_limits<uint32>::max();
            std::vector<Unit*> currentHealerOwnedAttackers;
            for (Unit* attacker : defenseTarget->getAttackers())
                if (attacker && attacker->IsAlive()
                    && bot->IsValidAttackTarget(attacker)
                    && attacker->GetVictim() == defenseTarget)
                {
                    currentHealerOwnedAttackers.push_back(attacker);
                    if (bot->GetExactDist2d(attacker) > 10.0f)
                        continue;

                    ++nearbyHealerOwnedCount;
                    missingOwnedRoar = missingOwnedRoar
                        || !attacker->HasAura(99, bot->GetGUID());
                    float distance = bot->GetExactDist(attacker);
                    uint32 guid = attacker->GetGUID().GetCounter();
                    if (!nearbyHealerOwnedAttacker
                        || distance < nearbyHealerOwnedDistance
                        || (distance == nearbyHealerOwnedDistance
                            && guid < nearbyHealerOwnedGuid))
                    {
                        nearbyHealerOwnedAttacker = attacker;
                        nearbyHealerOwnedDistance = distance;
                        nearbyHealerOwnedGuid = guid;
                    }
            }
            // Rerun160's maximum 6025-ms exposure reached all ten
            // healer-owned followers inside the Feral's local area envelope,
            // but three GCD-separated Demoralizing Roars were needed to
            // recover them. The existing Thrash aura was ticking on the prior
            // cluster and covered none of these identities, while no Swipe was
            // submitted during the episode. At this already-validated local
            // recovery point, prefer one native damaging area-threat attempt
            // when the nearby set covers a majority of current healer threat.
            // A rejected Swipe changes no state and falls through to the
            // unchanged Roar and handoff chain below.
            bool nearbyHealerOwnedCoversMajority =
                nearbyHealerOwnedCount >= 2
                && nearbyHealerOwnedCount * 2
                    >= currentHealerOwnedAttackers.size();
            // Rerun202's generation-13 Flayer swarm entered this proven
            // local-majority recovery with ten healer-owned identities.
            // Native Swipe and Growl reduced that set to two within 1543 ms,
            // but the ordinary-trash path then spent three decisions moving
            // to density and four selecting an out-of-range representative.
            // Unlike the arrived boss handoff above, this gate never offered
            // native Thrash; the last observed Thrash attempt was more than
            // twenty seconds old and the two identities reached 4395/4915 ms
            // of continuous healer ownership. Prefer the same persistent
            // native area threat at this already-established local-majority
            // recovery point, retaining Swipe below whenever Thrash is
            // unavailable. Every native spell, target, cooldown, GCD, power,
            // range, movement, hazard, victim, and threat gate is unchanged.
            if (nearbyHealerOwnedCoversMajority
                && nearbyHealerOwnedAttacker && bot->HasSpell(77758)
                && TryCastCombatSpell(bot, nearbyHealerOwnedAttacker, 77758))
            {
                if (feralTrashChargeArrived)
                {
                    state.FeralChargePickupTargetGuid.Clear();
                    state.FeralChargePickupUntilMs = 0;
                }
                std::string raw = BuildRawJson(
                    bot, nearbyHealerOwnedAttacker);
                std::string semantic = BuildSemanticJson(
                    bot, nearbyHealerOwnedAttacker,
                    "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    nearbyHealerOwnedAttacker,
                    "feral_thrash_healer_swarm_retention_before_roar",
                    raw.c_str(), semantic.c_str(),
                    float(nearbyHealerOwnedCount),
                    float(currentHealerOwnedAttackers.size()), 77758);
                state.TargetGuid = nearbyHealerOwnedAttacker->GetGUID();
                target = nearbyHealerOwnedAttacker;
                situation = "normal_dungeon_trash";
                action =
                    "feral_thrash_healer_swarm_retention_before_roar";
                state.WasInCombat = true;
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                return true;
            }
            if (nearbyHealerOwnedCoversMajority
                && nearbyHealerOwnedAttacker && bot->HasSpell(779)
                && TryCastCombatSpell(bot, nearbyHealerOwnedAttacker, 779))
            {
                if (feralTrashChargeArrived)
                {
                    state.FeralChargePickupTargetGuid.Clear();
                    state.FeralChargePickupUntilMs = 0;
                }
                std::string raw = BuildRawJson(
                    bot, nearbyHealerOwnedAttacker);
                std::string semantic = BuildSemanticJson(
                    bot, nearbyHealerOwnedAttacker,
                    "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    nearbyHealerOwnedAttacker,
                    "feral_swipe_healer_swarm_retention_before_roar",
                    raw.c_str(), semantic.c_str(),
                    float(nearbyHealerOwnedCount),
                    float(currentHealerOwnedAttackers.size()), 779);
                state.TargetGuid = nearbyHealerOwnedAttacker->GetGUID();
                target = nearbyHealerOwnedAttacker;
                situation = "normal_dungeon_trash";
                action =
                    "feral_swipe_healer_swarm_retention_before_roar";
                state.WasInCombat = true;
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                return true;
            }
            if (nearbyHealerOwnedCount >= 2 && missingOwnedRoar
                && TryCastFriendlySpell(bot, bot, 99))
            {
                if (feralTrashChargeArrived)
                {
                    state.FeralChargePickupTargetGuid.Clear();
                    state.FeralChargePickupUntilMs = 0;
                }
                // Rerun87 proved the stationary-healer handoff could submit
                // Roar at the 500 ms GCD boundary yet acquire only four or five
                // followers per cycle from a 27-47-hostile split topology.
                // Bind the bounded handoff to the densest currently remote
                // healer-owned cluster instead. Revalidate this moving GUID on
                // every tick above, matching the already-proved moving-endpoint
                // active-swarm pickup without permitting generic target churn.
                Unit* remoteClusterAnchor = nullptr;
                uint32 remoteClusterCount = 0;
                float remoteClusterDistance =
                    std::numeric_limits<float>::max();
                uint32 remoteClusterGuid =
                    std::numeric_limits<uint32>::max();
                for (Unit* candidate : currentHealerOwnedAttackers)
                {
                    float candidateDistance = bot->GetExactDist(candidate);
                    if (candidateDistance <= 10.0f)
                        continue;
                    uint32 clusterCount = 0;
                    for (Unit* neighbor : currentHealerOwnedAttackers)
                        if (candidate->GetExactDist2d(neighbor) <= 10.0f)
                            ++clusterCount;
                    uint32 guid = candidate->GetGUID().GetCounter();
                    if (!remoteClusterAnchor
                        || clusterCount > remoteClusterCount
                        || (clusterCount == remoteClusterCount
                            && (candidateDistance < remoteClusterDistance
                                || (candidateDistance == remoteClusterDistance
                                    && guid < remoteClusterGuid))))
                    {
                        remoteClusterAnchor = candidate;
                        remoteClusterCount = clusterCount;
                        remoteClusterDistance = candidateDistance;
                        remoteClusterGuid = guid;
                    }
                }
                bool remoteClusterRemains = remoteClusterAnchor != nullptr;
                Position remoteRoarIntercept;
                if (remoteClusterAnchor)
                    remoteRoarIntercept =
                        remoteClusterAnchor->GetFirstCollisionPosition(
                            8.0f,
                            remoteClusterAnchor->GetAngle(bot)
                                - remoteClusterAnchor->GetOrientation());
                // The post-Roar reservation needs only to preserve legal Roar
                // range. Walking to the hostile's exact point spends the same
                // strict dwell budget that the pre-Roar intercept avoids.
                bool splitClusterHandoff = remoteClusterAnchor
                    && !bot->HasUnitState(UNIT_STATE_CASTING)
                    && !bot->IsFalling()
                    && MoveBotToPoint(state, bot,
                        remoteRoarIntercept.GetPositionX(),
                        remoteRoarIntercept.GetPositionY(),
                        remoteRoarIntercept.GetPositionZ());
                if (splitClusterHandoff)
                    state.DecisionTimer = std::min<uint32>(
                        state.DecisionTimer, 500);
                if (remoteClusterRemains)
                {
                    state.FeralHealerThreatHandoffTargetGuid =
                        defenseTarget->GetGUID();
                    state.FeralHealerThreatHandoffAnchorGuid =
                        remoteClusterAnchor->GetGUID();
                    state.FeralHealerThreatHandoffUntilMs = NowMs() + 2500;
                    state.FeralHealerThreatHandoffRemoteCluster = true;
                }
                else
                {
                    state.FeralHealerThreatHandoffTargetGuid.Clear();
                    state.FeralHealerThreatHandoffAnchorGuid.Clear();
                    state.FeralHealerThreatHandoffUntilMs = 0;
                    state.FeralHealerThreatHandoffRemoteCluster = false;
                }
                std::string raw = BuildRawJson(bot, nearbyHealerOwnedAttacker);
                std::string semantic = BuildSemanticJson(
                    bot, nearbyHealerOwnedAttacker, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    nearbyHealerOwnedAttacker,
                    splitClusterHandoff
                        ? "feral_demoralizing_roar_remote_healer_trash_cluster_handoff"
                        : "feral_demoralizing_roar_healer_trash_pickup",
                    raw.c_str(), semantic.c_str(),
                    float(nearbyHealerOwnedCount),
                    float(currentHealerOwnedAttackers.size()), 99);
                state.TargetGuid = nearbyHealerOwnedAttacker
                    ? nearbyHealerOwnedAttacker->GetGUID() : ObjectGuid::Empty;
                target = nearbyHealerOwnedAttacker;
                situation = "normal_dungeon_trash";
                action = splitClusterHandoff
                    ? "feral_demoralizing_roar_remote_healer_trash_cluster_handoff"
                    : "feral_demoralizing_roar_healer_trash_pickup";
                state.WasInCombat = true;
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                return true;
            }
        }
        if (feralTrashChargeArrived && defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && defenseAttackerCount >= 2)
        {
            bot->StopMoving();
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
            std::string raw = BuildRawJson(bot, feralTrashChargeTarget);
            std::string semantic = BuildSemanticJson(
                bot, feralTrashChargeTarget, "normal_dungeon_trash",
                &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup",
                feralTrashChargeTarget,
                "feral_hold_charge_trash_arrival_for_roar",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(feralTrashChargeTarget),
                float(defenseAttackerCount));
            state.TargetGuid = feralTrashChargeTarget->GetGUID();
            target = feralTrashChargeTarget;
            situation = "normal_dungeon_trash";
            action = "feral_hold_charge_trash_arrival_for_roar";
            return true;
        }
        if (feralTrashHandoffActive && feralTrashHandoffArrived
            && defenseAttackerCount >= 2)
        {
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 500);
            std::string raw = BuildRawJson(bot, feralTrashHandoffAnchor);
            std::string semantic = BuildSemanticJson(
                bot, feralTrashHandoffAnchor, "normal_dungeon_trash",
                &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup",
                feralTrashHandoffAnchor,
                "feral_hold_remote_healer_trash_cluster_for_roar",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(feralTrashHandoffAnchor),
                float(defenseAttackerCount));
            state.TargetGuid = feralTrashHandoffAnchor->GetGUID();
            target = feralTrashHandoffAnchor;
            situation = "normal_dungeon_trash";
            action = "feral_hold_remote_healer_trash_cluster_for_roar";
            return true;
        }
        // A single Flayer follower survived rerun81's completed area pickup for
        // 6041 ms because the two-attacker Roar gate no longer applied and the
        // strict area resolver kept selecting density movement. Use the
        // explicit native Growl profile for exactly one healer-owned attacker;
        // this neither assigns a victim nor replaces multi-target pickup.
        if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && bot->getClass() == CLASS_DRUID
            && defenseAttackerCount == 1 && bot->HasSpell(6795))
        {
            Unit* healerAttacker = nullptr;
            for (Unit* attacker : defenseTarget->getAttackers())
                if (attacker && attacker->IsAlive()
                    && bot->IsValidAttackTarget(attacker)
                    && (!healerAttacker
                        || bot->GetExactDist(attacker)
                            < bot->GetExactDist(healerAttacker)
                        || (bot->GetExactDist(attacker)
                                == bot->GetExactDist(healerAttacker)
                            && attacker->GetGUID().GetCounter()
                                < healerAttacker->GetGUID().GetCounter())))
                    healerAttacker = attacker;
            if (healerAttacker
                && TryCastCombatSpell(bot, healerAttacker, 6795))
            {
                std::string raw = BuildRawJson(bot, healerAttacker);
                std::string semantic = BuildSemanticJson(
                    bot, healerAttacker, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    healerAttacker,
                    "feral_growl_lingering_healer_trash_attacker",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist(healerAttacker),
                    float(defenseAttackerCount), 6795);
                state.TargetGuid = healerAttacker->GetGUID();
                target = healerAttacker;
                situation = "normal_dungeon_trash";
                action = "feral_growl_lingering_healer_trash_attacker";
                state.WasInCombat = true;
                return true;
            }
        }
        // Rerun157 localized 28 of 37 Protection healer-target samples to four
        // corridor attackers that remained on the healer while the native
        // pickup chain ran serially. Boss waves already use Hand of Protection
        // as an emergency victim break. Apply the same native protection before
        // ordinary-trash recovery only at three or more healer attackers; the
        // unchanged threat controller still has to acquire and retain the pack.
        // Rerun158 then observed the first exposed sample one decision before
        // that threshold, followed by successful protection and full recovery
        // within 1012 ms. Protect on the first healer attacker so the same
        // native recovery chain starts before the strict exposure ratio fails.
        // Blood/warrior tanks use a single-target native taunt instead of the
        // Protection-specific pickup chain below.  The first Stonecore 5H
        // trace exposed exactly this gap: Dark Command was learned and legal,
        // but no dungeon threat branch submitted it when Millhouse remained on
        // the healer, so the tank died with nine other hostiles already owned.
        if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && defenseAttackerCount >= 1
            && (bot->getClass() == CLASS_DEATH_KNIGHT
                || bot->getClass() == CLASS_WARRIOR))
        {
            uint32 tauntSpell = bot->getClass() == CLASS_DEATH_KNIGHT ? 56222 : 355;
            Unit* healerTauntTarget = nullptr;
            float healerTauntDistance = std::numeric_limits<float>::max();
            uint32 healerTauntGuid = std::numeric_limits<uint32>::max();
            auto considerHealerTauntTarget = [&](Unit* attacker)
            {
                if (!attacker || !attacker->IsAlive()
                    || attacker->GetVictim() != defenseTarget
                    || !bot->IsValidAttackTarget(attacker))
                    return;
                float distance = bot->GetExactDist(attacker);
                uint32 guid = attacker->GetGUID().GetCounter();
                if (!healerTauntTarget || distance < healerTauntDistance
                    || (distance == healerTauntDistance && guid < healerTauntGuid))
                {
                    healerTauntTarget = attacker;
                    healerTauntDistance = distance;
                    healerTauntGuid = guid;
                }
            };
            for (Unit* attacker : trashThreatControl.HealerOwnedTargets)
                considerHealerTauntTarget(attacker);
            if (!healerTauntTarget)
                for (Unit* attacker : defenseTarget->getAttackers())
                    considerHealerTauntTarget(attacker);

            if (healerTauntTarget && bot->HasSpell(tauntSpell)
                && TryCastCombatSpell(bot, healerTauntTarget, tauntSpell))
            {
                std::string raw = BuildRawJson(bot, healerTauntTarget);
                std::string semantic = BuildSemanticJson(
                    bot, healerTauntTarget, "normal_dungeon_trash",
                    &power, stage, activity);
                char const* tauntAction = bot->getClass() == CLASS_DEATH_KNIGHT
                    ? "dark_command_healer_trash_pickup"
                    : "taunt_healer_trash_pickup";
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    healerTauntTarget, tauntAction, raw.c_str(),
                    semantic.c_str(), healerTauntDistance,
                    float(defenseAttackerCount), tauntSpell);
                state.DecisionTimer = std::min<uint32>(state.DecisionTimer, 250);
                state.TargetGuid = healerTauntTarget->GetGUID();
                target = healerTauntTarget;
                situation = "normal_dungeon_trash";
                action = tauntAction;
                state.WasInCombat = true;
                return true;
            }
        }

        // The route threat controller intentionally owns the tank decision, so
        // the ordinary class-profile survival rows are otherwise never reached
        // during a dense opening pack.  Preserve the native defensive lane for
        // a Blood DK before another area-threat retry: Icebound Fortitude buys
        // time at critical health and Death Strike uses the current hostile to
        // convert the recent damage window into a native self-heal.  No health,
        // aura, threat, or cooldown state is manufactured here.
        if (bot->getClass() == CLASS_DEATH_KNIGHT)
        {
            Unit* deathStrikeTarget = trashThreatControl.AreaTarget;
            if (!deathStrikeTarget || !deathStrikeTarget->IsAlive()
                || !bot->IsValidAttackTarget(deathStrikeTarget))
                deathStrikeTarget = bot->GetVictim();

            if (UnitHealthPct(bot) <= 0.75f && deathStrikeTarget
                && deathStrikeTarget->IsAlive()
                && bot->IsValidAttackTarget(deathStrikeTarget)
                && bot->HasSpell(49998)
                && TryCastCombatSpell(bot, deathStrikeTarget, 49998))
            {
                std::string raw = BuildRawJson(bot, deathStrikeTarget);
                std::string semantic = BuildSemanticJson(
                    bot, deathStrikeTarget, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "defensive",
                    deathStrikeTarget, "tank_trash_death_strike",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist(deathStrikeTarget),
                    trashThreatControl.EngagedCount, 49998);
                state.TargetGuid = deathStrikeTarget->GetGUID();
                target = deathStrikeTarget;
                situation = "normal_dungeon_trash";
                action = "tank_trash_death_strike";
                state.WasInCombat = true;
                return true;
            }

            // Death Strike is the only immediate native self-heal in this
            // emergency lane.  Give it first refusal so a low-health tank
            // does not spend the decision/GCD on Icebound Fortitude and die
            // before the heal can land.  Icebound remains the bounded
            // fallback mitigation when Death Strike is unavailable or fails.
            if (UnitHealthPct(bot) <= 0.55f && bot->HasSpell(48792)
                && !bot->HasAura(48792)
                && TryCastFriendlySpell(bot, bot, 48792))
            {
                std::string raw = BuildRawJson(bot, deathStrikeTarget);
                std::string semantic = BuildSemanticJson(
                    bot, deathStrikeTarget, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "defensive",
                    bot, "tank_trash_icebound_fortitude",
                    raw.c_str(), semantic.c_str(), UnitHealthPct(bot),
                    trashThreatControl.EngagedCount, 48792);
                situation = "normal_dungeon_trash";
                action = "tank_trash_icebound_fortitude";
                return true;
            }
        }
        if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && defenseAttackerCount >= 1
            && bot->HasSpell(1022) && !defenseTarget->HasAura(1022)
            && TryCastFriendlySpell(bot, defenseTarget, 1022))
        {
            std::string raw = BuildRawJson(bot, defenseTarget);
            std::string semantic = BuildSemanticJson(bot, defenseTarget,
                "normal_dungeon_trash", &power, stage,
                activity);
            RecordEvent(state, bot, "external_defensive", defenseTarget,
                "hand_of_protection_healer_trash_emergency", raw.c_str(),
                semantic.c_str(), float(defenseAttackerCount),
                Cohort().Config.ValidationRouteTargetEntry, 1022);
            situation = "normal_dungeon_trash";
            action = "hand_of_protection_healer_trash_emergency";
            return true;
        }
        // Rerun145 localized Protection's only healer exposure to a two-add
        // corridor handoff: targeted Righteous Defense returned first, then
        // route movement displaced the adjacent native area pickup beyond the
        // strict dwell ceiling. When both adds are already inside the unchanged
        // Consecration radius, submit that existing native area threat first.
        // Righteous Defense remains the immediate fallback if the cast is not
        // legal, ready, or successful.
        if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && defenseAttackerCount >= 2
            && bot->GetExactDist2d(defenseTarget) <= 8.0f
            && bot->HasSpell(26573) && TryCastFriendlySpell(bot, bot, 26573))
        {
            std::string raw = BuildRawJson(bot, defenseTarget);
            std::string semantic = BuildSemanticJson(bot, defenseTarget,
                "normal_dungeon_trash", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup",
                defenseTarget, "consecration_healer_multi_trash_pickup",
                raw.c_str(), semantic.c_str(), float(defenseAttackerCount),
                Cohort().Config.ValidationRouteTargetEntry, 26573);
            situation = "normal_dungeon_trash";
            action = "consecration_healer_multi_trash_pickup";
            return true;
        }
        if (defenseTarget && bot->HasSpell(31789) && TryCastFriendlySpell(bot, defenseTarget, 31789))
        {
            Unit* pickupTarget = nullptr;
            uint32 pickupGuid = std::numeric_limits<uint32>::max();
            for (Unit* attacker : defenseTarget->getAttackers())
            {
                if (!attacker || !attacker->IsAlive() || !bot->IsValidAttackTarget(attacker))
                    continue;
                uint32 guid = attacker->GetGUID().GetCounter();
                if (!pickupTarget || guid < pickupGuid)
                {
                    pickupTarget = attacker;
                    pickupGuid = guid;
                }
            }
            if (pickupTarget)
            {
                target = pickupTarget;
                state.TargetGuid = pickupTarget->GetGUID();
            }
            bool healerPickup = std::string(GetDungeonRole(defenseTarget)) == "healer";
            char const* pickupAction = healerPickup ? "righteous_defense_healer_pickup" : "righteous_defense_party_pickup";
            std::string raw = BuildRawJson(bot, defenseTarget);
            std::string semantic = BuildSemanticJson(bot, defenseTarget, "normal_dungeon_trash", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup", defenseTarget, pickupAction,
                raw.c_str(), semantic.c_str(), float(defenseAttackerCount), Cohort().Config.ValidationRouteTargetEntry, 31789);
            situation = "normal_dungeon_trash";
            action = pickupAction;
            return true;
        }
        // Rerun170 retained 17 eligible healer-target samples after every
        // multi-target Protection pickup remained native and successful. Twelve
        // samples came from three continuously engaged hostiles reacquiring the
        // healer together while Righteous Defense was unavailable; Avenger's
        // Shield and the next area action needed several telemetry ticks to
        // recover all three. Use the otherwise configured native single taunt
        // against one deterministic healer attacker before the multi-target
        // fallbacks, then poll the remaining exact exposure at 250 ms. This does
        // not assign threat directly and leaves every spell legality gate native.
        if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && defenseAttackerCount >= 1
            && cadenceProfile.SpecTag == "protection"
            && bot->HasSpell(62124))
        {
            Unit* healerTauntTarget = nullptr;
            float healerTauntDistance = std::numeric_limits<float>::max();
            uint32 healerTauntGuid = std::numeric_limits<uint32>::max();
            bool healerTauntRepeatsCurrentTarget = true;
            for (Unit* attacker : defenseTarget->getAttackers())
            {
                if (!attacker || !attacker->IsAlive()
                    || !bot->IsValidAttackTarget(attacker))
                    continue;
                float distance = bot->GetExactDist(attacker);
                uint32 guid = attacker->GetGUID().GetCounter();
                bool repeatsCurrentTarget =
                    attacker->GetGUID() == state.TargetGuid;
                if (!healerTauntTarget
                    || (healerTauntRepeatsCurrentTarget
                        && !repeatsCurrentTarget)
                    || (healerTauntRepeatsCurrentTarget
                            == repeatsCurrentTarget
                        && (distance < healerTauntDistance
                            || (distance == healerTauntDistance
                                && guid < healerTauntGuid))))
                {
                    healerTauntTarget = attacker;
                    healerTauntDistance = distance;
                    healerTauntGuid = guid;
                    healerTauntRepeatsCurrentTarget =
                        repeatsCurrentTarget;
                }
            }
            if (healerTauntTarget
                && TryCastCombatSpell(bot, healerTauntTarget, 62124))
            {
                std::string raw = BuildRawJson(bot, healerTauntTarget);
                std::string semantic = BuildSemanticJson(bot,
                    healerTauntTarget, "normal_dungeon_trash", &power,
                    stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    healerTauntTarget,
                    "hand_of_reckoning_healer_trash_pickup",
                    raw.c_str(), semantic.c_str(), healerTauntDistance,
                    float(defenseAttackerCount), 62124);
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                state.TargetGuid = healerTauntTarget->GetGUID();
                target = healerTauntTarget;
                situation = "normal_dungeon_trash";
                action = "hand_of_reckoning_healer_trash_pickup";
                state.WasInCombat = true;
                return true;
            }
        }
        // Rerun151 localized Protection's remaining healer exposure to a
        // remote two-hostile corridor handoff. Righteous Defense had just been
        // consumed on another party member, while the generic density resolver
        // selected ranged Hand of Reckoning through its melee movement
        // envelope and did not submit it until after the strict dwell ceiling.
        // Use the existing native ranged multi-target pickup directly when the
        // healer owns at least two attackers; every normal spell legality gate
        // remains inside TryCastCombatSpell and all established fallbacks stay
        // below this branch.
        if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && defenseAttackerCount >= 2 && bot->HasSpell(31935))
        {
            Unit* healerClusterTarget = nullptr;
            float healerClusterDistance = std::numeric_limits<float>::max();
            uint32 healerClusterGuid = std::numeric_limits<uint32>::max();
            for (Unit* attacker : defenseTarget->getAttackers())
            {
                if (!attacker || !attacker->IsAlive()
                    || !bot->IsValidAttackTarget(attacker))
                    continue;
                float distance = bot->GetExactDist(attacker);
                uint32 guid = attacker->GetGUID().GetCounter();
                if (!healerClusterTarget || distance < healerClusterDistance
                    || (distance == healerClusterDistance
                        && guid < healerClusterGuid))
                {
                    healerClusterTarget = attacker;
                    healerClusterDistance = distance;
                    healerClusterGuid = guid;
                }
            }
            if (healerClusterTarget
                && TryCastCombatSpell(bot, healerClusterTarget, 31935))
            {
                std::string raw = BuildRawJson(bot, healerClusterTarget);
                std::string semantic = BuildSemanticJson(bot,
                    healerClusterTarget, "normal_dungeon_trash", &power,
                    stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    healerClusterTarget,
                    "avengers_shield_healer_multi_trash_pickup",
                    raw.c_str(), semantic.c_str(), healerClusterDistance,
                    float(defenseAttackerCount), 31935);
                state.TargetGuid = healerClusterTarget->GetGUID();
                target = healerClusterTarget;
                situation = "normal_dungeon_trash";
                action = "avengers_shield_healer_multi_trash_pickup";
                state.WasInCombat = true;
                return true;
            }
        }
        if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && bot->HasSpell(1038) && !defenseTarget->HasAura(1038)
            && TryCastFriendlySpell(bot, defenseTarget, 1038))
        {
            std::string raw = BuildRawJson(bot, defenseTarget);
            std::string semantic = BuildSemanticJson(bot, defenseTarget, "normal_dungeon_trash", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup", defenseTarget,
                "hand_of_salvation_healer_trash_threat_drop", raw.c_str(), semantic.c_str(),
                float(defenseAttackerCount), Cohort().Config.ValidationRouteTargetEntry, 1038);
            situation = "normal_dungeon_trash";
            action = "hand_of_salvation_healer_trash_threat_drop";
            return true;
        }
        if (defenseTarget && bot->GetExactDist2d(defenseTarget) <= 8.0f
            && bot->HasSpell(26573) && TryCastFriendlySpell(bot, bot, 26573))
        {
            bool healerPickup = std::string(GetDungeonRole(defenseTarget)) == "healer";
            char const* pickupAction = healerPickup ? "consecration_healer_trash_pickup" : "consecration_party_trash_pickup";
            std::string raw = BuildRawJson(bot, defenseTarget);
            std::string semantic = BuildSemanticJson(bot, defenseTarget, "normal_dungeon_trash", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup", defenseTarget, pickupAction,
                raw.c_str(), semantic.c_str(), float(defenseAttackerCount), Cohort().Config.ValidationRouteTargetEntry, 26573);
            situation = "normal_dungeon_trash";
            action = pickupAction;
            return true;
        }

        if (trashThreatControl.EngagedCount >= 3 && trashThreatControl.AreaTarget)
        {
            // Rerun142 proved continuous aura-fresh next-encounter adds could
            // outrank the actual dense wave and churn this target. Retain the
            // current tank-owned set and select its largest ten-yard cluster
            // first. Within equal-density clusters prefer a target missing this
            // Feral's Thrash aura, then preserve deterministic distance and GUID
            // ordering. This changes only the target passed to the native profile
            // resolver; cooldowns, victims, and threat remain intact.
            bool feralTankOwnedDensitySelected = false;
            // Rerun175's only 14 eligible healer-exposure samples all belonged
            // to one generation-13 Flayer. The existing remote-handoff path was
            // unavailable, then this proactive tank-owned cluster selector
            // repeatedly displaced the already-established healer-owned area
            // fallback. Four 250-ms movements toward that exact Flayer began
            // only when the tank briefly lost its victim majority; once the
            // majority recovered, density retook priority and dwell reached
            // 6421 ms. Keep the established healer-owned fallback authoritative
            // while any exact current healer threat exists. Its native profile
            // action, range, LOS, path, cooldown, GCD, and threat gates remain
            // unchanged, as does proactive density whenever the healer is clear.
            if (bot->getClass() == CLASS_DRUID
                && trashThreatControl.EngagedCount >= 12
                && tankOwnsTrashMajority
                && !feralCurrentHealerThreat)
            {
                Unit* densestTankOwnedClusterTarget = nullptr;
                bool densestTankOwnedClusterMissingThrash = false;
                uint32 densestTankOwnedClusterCount = 0;
                float densestTankOwnedClusterDistance =
                    std::numeric_limits<float>::max();
                uint32 densestTankOwnedClusterGuid =
                    std::numeric_limits<uint32>::max();
                for (Unit* candidate : trashThreatControl.TankOwnedTargets)
                {
                    if (!candidate || !candidate->IsAlive()
                        || candidate->GetMap() != bot->GetMap()
                        || candidate->GetVictim() != trashThreatControl.Tank
                        || !bot->IsValidAttackTarget(candidate))
                        continue;
                    uint32 clusterCount = 0;
                    for (Unit* neighbor : trashThreatControl.TankOwnedTargets)
                        if (neighbor && neighbor->IsAlive()
                            && neighbor->GetMap() == bot->GetMap()
                            && neighbor->GetVictim() == trashThreatControl.Tank
                            && bot->IsValidAttackTarget(neighbor)
                            && candidate->GetExactDist2d(neighbor) <= 10.0f)
                            ++clusterCount;
                    bool missingThrash =
                        !candidate->HasAura(77758, bot->GetGUID());
                    float distance = bot->GetExactDist(candidate);
                    uint32 guid = candidate->GetGUID().GetCounter();
                    if (!densestTankOwnedClusterTarget
                        || clusterCount > densestTankOwnedClusterCount
                        || (clusterCount == densestTankOwnedClusterCount
                            && (missingThrash
                                && !densestTankOwnedClusterMissingThrash))
                        || (clusterCount == densestTankOwnedClusterCount
                            && missingThrash
                                == densestTankOwnedClusterMissingThrash
                            && (distance < densestTankOwnedClusterDistance
                                || (distance == densestTankOwnedClusterDistance
                                    && guid < densestTankOwnedClusterGuid))))
                    {
                        densestTankOwnedClusterTarget = candidate;
                        densestTankOwnedClusterMissingThrash = missingThrash;
                        densestTankOwnedClusterCount = clusterCount;
                        densestTankOwnedClusterDistance = distance;
                        densestTankOwnedClusterGuid = guid;
                    }
                }
                if (densestTankOwnedClusterTarget)
                {
                    trashThreatControl.AreaTarget =
                        densestTankOwnedClusterTarget;
                    feralTankOwnedDensitySelected = true;
                }
            }
            // Rerun140 proved the specialized Feral handoffs selected the
            // densest healer-owned cluster, but their generic area fallback
            // reverted to the nearest healer-owned hostile. Preserve that
            // established ten-yard cluster contract after every higher-priority
            // pickup branch has fallen through when the proactive tank-owned
            // large-wave selector above does not apply.
            if (!feralTankOwnedDensitySelected
                && bot->getClass() == CLASS_DRUID && defenseTarget
                && std::string(GetDungeonRole(defenseTarget)) == "healer")
            {
                Unit* densestHealerClusterTarget = nullptr;
                uint32 densestHealerClusterCount = 0;
                float densestHealerClusterDistance =
                    std::numeric_limits<float>::max();
                uint32 densestHealerClusterGuid =
                    std::numeric_limits<uint32>::max();
                for (Unit* candidate : trashThreatControl.HealerOwnedTargets)
                {
                    if (!candidate || !candidate->IsAlive()
                        || candidate->GetMap() != bot->GetMap()
                        || candidate->GetVictim() != defenseTarget
                        || !bot->IsValidAttackTarget(candidate))
                        continue;
                    uint32 clusterCount = 0;
                    for (Unit* neighbor : trashThreatControl.HealerOwnedTargets)
                        if (neighbor && neighbor->IsAlive()
                            && neighbor->GetMap() == bot->GetMap()
                            && neighbor->GetVictim() == defenseTarget
                            && bot->IsValidAttackTarget(neighbor)
                            && candidate->GetExactDist2d(neighbor) <= 10.0f)
                            ++clusterCount;
                    float distance = bot->GetExactDist(candidate);
                    uint32 guid = candidate->GetGUID().GetCounter();
                    if (!densestHealerClusterTarget
                        || clusterCount > densestHealerClusterCount
                        || (clusterCount == densestHealerClusterCount
                            && (distance < densestHealerClusterDistance
                                || (distance == densestHealerClusterDistance
                                    && guid < densestHealerClusterGuid))))
                    {
                        densestHealerClusterTarget = candidate;
                        densestHealerClusterCount = clusterCount;
                        densestHealerClusterDistance = distance;
                        densestHealerClusterGuid = guid;
                    }
                }
                if (densestHealerClusterTarget)
                    trashThreatControl.AreaTarget =
                        densestHealerClusterTarget;
            }
            target = trashThreatControl.AreaTarget;
            state.TargetGuid = target->GetGUID();
            Creature const* areaCreature = target->ToCreature();
            // Rerun143 proved that restricting shared focus to the declared
            // current pack can strand every follower while the tank is in
            // legitimate party-linked combat with adjacent trash. Preserve
            // rerun142's isolation boundary only for the manifest-classified
            // immediate-next encounter; all other tactical area targets remain
            // valid party assist focus.
            if (areaCreature
                && !isImmediateNextValidationRouteEncounterMember(areaCreature))
                rememberValidationRouteFocus(target);
            ResolvedCombatAction areaAction = ResolveProfileCombatAction(bot, target,
                trashThreatControl.EngagedCount, true);
            if (areaAction.Valid)
            {
                float engageRange = areaAction.MaxRange > 0.0f
                    ? areaAction.MaxRange : routeEngageRange(bot, target, areaAction.SpellId);
                float targetDistance = bot->GetExactDist(target);
                if (targetDistance > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(target))
                {
                    bool moved = MoveBotToProfileRange(state, bot, target, &areaAction);
                    // Rerun170's longest Protection exposure began with three
                    // one-second movement decisions toward healer-owned hostile
                    // 9 and ended at 3017 ms. The native pickup succeeded on the
                    // next decision, but only after the unchanged 3000-ms strict
                    // dwell ceiling. Retry only this healer-protection approach
                    // at the existing urgent pickup cadence; ordinary density
                    // movement and every native spell/range gate stay unchanged.
                    Player* areaVictim = target->GetVictim()
                        ? target->GetVictim()->ToPlayer() : nullptr;
                    if (moved && cadenceProfile.SpecTag == "protection"
                        && areaVictim
                        && std::string(GetDungeonRole(areaVictim)) == "healer")
                        state.DecisionTimer = std::min<uint32>(
                            state.DecisionTimer, 250);
                    situation = "normal_dungeon_trash";
                    action = moved ? "move_to_trash_density" : "hold_tactical_path_rejected";
                    return true;
                }

                BotActionResult result = ExecuteProfileCombatAction(&state, bot, target, &areaAction,
                    trashThreatControl.EngagedCount, true);
                std::string raw = BuildRawJson(bot, target);
                std::string semantic = BuildSemanticJson(bot, target, "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup", target, "trash_density_area_threat",
                    raw.c_str(), semantic.c_str(), float(trashThreatControl.SecureTankCount),
                    trashThreatControl.EngagedCount, result == BotActionResult::Ok ? areaAction.SpellId : 0);
                situation = "normal_dungeon_trash";
                action = "trash_density_area_threat";
                state.WasInCombat = true;
                return true;
            }
        }

        Unit* threatFocus = findTrashClusterThreatTarget();
        Player* threatVictim = threatFocus && threatFocus->GetVictim() ? threatFocus->GetVictim()->ToPlayer() : nullptr;
        bool loosePartyThreat = threatVictim && threatVictim->GetGroup() == bot->GetGroup()
            && std::string(GetDungeonRole(threatVictim)) != "tank";
        Unit* rememberedFocus = loosePartyThreat ? threatFocus : findLastKnownFocusTarget();
        if (!rememberedFocus)
            rememberedFocus = threatFocus;
        if (rememberedFocus && target != rememberedFocus && (rememberedFocus->GetVictim() != bot || !bot->GetVictim()))
        {
            target = rememberedFocus;
            state.TargetGuid = target->GetGUID();
        }
    }
    if (std::string(GetDungeonRole(bot)) == "tank")
    {
        if (Unit* tankTarget = routeUsableCombatTarget(target))
            rememberValidationRouteFocus(tankTarget);
    }
    if (Cohort().Config.ValidationRouteKind == "boss" && std::string(GetDungeonRole(bot)) != "tank")
    {
        ObjectGuid tankFocusGuid = routeTankFocusGuid();
        Unit* tankFocusTarget = routeTankFocusTarget(tankFocusGuid);
        if (!tankFocusTarget && !tankFocusGuid.IsEmpty())
            tankFocusTarget = routeUsableCombatTarget(ObjectAccessor::GetUnit(*bot, tankFocusGuid));
        if (!tankFocusTarget)
            tankFocusTarget = findLastKnownFocusTarget();
        if (tankFocusTarget)
        {
            Creature* tankFocusCreature = tankFocusTarget->ToCreature();
            bool tankFocusIsRouteTarget = isValidationRouteObjectiveTarget(tankFocusCreature);
            bool tankFocusIsBossRoute = tankFocusIsRouteTarget && Cohort().Config.ValidationRouteKind == "boss";
            char const* tankFocusSituation = tankFocusIsRouteTarget
                ? (tankFocusIsBossRoute ? (bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss") : "normal_dungeon_trash")
                : "validation_route_prerequisite";

            if (!tankFocusIsRouteTarget)
            {
                // Boss nodes own only their declared objective contract.  An
                // undeclared corridor hostile must be completed by an explicit
                // preceding trash node, never by a generic boss prerequisite
                // assist that bypasses target/area/multidot authority.
                bot->InterruptNonMeleeSpells(false);
                SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                    BotMeleeAutoAttack::Owner::Safety,
                    BotActionArbitration::Priority::Terminal,
                    "shared_focus_not_declared");
                if (Pet* pet = bot->GetPet())
                    pet->AttackStop();
                for (Unit* controlled : bot->m_Controlled)
                    if (controlled)
                        controlled->AttackStop();
                std::string raw = BuildRawJson(bot, tankFocusTarget);
                std::string semantic = BuildSemanticJson(
                    bot, tankFocusTarget, "validation_route_prerequisite", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_prerequisite_rejected",
                    tankFocusTarget, "boss_route_target_not_declared", raw.c_str(),
                    semantic.c_str(), bot->GetExactDist(tankFocusTarget),
                    Cohort().Config.ValidationRouteTargetEntry);
                state.TargetGuid.Clear();
                target = nullptr;
                situation = "validation_route_prerequisite";
                action = "boss_route_prerequisite_blocked";
                return true;
            }

            state.ValidationRouteUnresolvedFocusHoldCount = 0;
            Unit* staleTarget = target && target != tankFocusTarget ? target : nullptr;
            Unit* staleVictim = bot->GetVictim() && bot->GetVictim() != tankFocusTarget ? bot->GetVictim() : nullptr;
            if (staleTarget || staleVictim)
            {
                Unit* rejected = staleVictim ? staleVictim : staleTarget;
                std::string raw = BuildRawJson(bot, rejected);
                std::string semantic = BuildSemanticJson(bot, rejected, "validation_route_regroup", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_prerequisite_rejected", rejected, "force_tank_focus", raw.c_str(), semantic.c_str(), rejected ? bot->GetExactDist(rejected) : 0.0f, Cohort().Config.ValidationRouteTargetEntry);
            }

            target = tankFocusTarget;
            state.TargetGuid = target->GetGUID();
            // Route-directed boss assistance must pass through the same typed
            // mechanic authority as the ordinary boss path. In particular,
            // this keeps a non-tank's initial profile action from bypassing
            // focus target selection, the area/multidot policy, or unresolved
            // contract fail-closed handling.
            if (tankFocusIsBossRoute)
            {
                BossMechanicActionResult mechanic = TryBossMechanics(state, bot, power, stage, activity, target);
                if (mechanic.Handled)
                {
                    situation = mechanic.Situation;
                    action = mechanic.Action;
                    target = mechanic.Target;
                    return true;
                }

                // The route classified this as its boss objective, so do not
                // fall through to the generic assist action if the authority
                // cannot establish a boss context. That would reintroduce the
                // exact pre-engagement bypass this dispatch closes.
                bot->InterruptNonMeleeSpells(false);
                SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                    BotMeleeAutoAttack::Owner::Safety,
                    BotActionArbitration::Priority::Terminal,
                    "shared_boss_mechanic_fail_closed");
                if (Pet* pet = bot->GetPet())
                    pet->AttackStop();
                for (Unit* controlled : bot->m_Controlled)
                    if (controlled)
                        controlled->AttackStop();
                situation = tankFocusSituation;
                action = "raid_mechanic_contract_fail_closed";
                return true;
            }
            if (tryRouteGroupHeal(bot, target))
                return true;
            if (tankFocusIsBossRoute && tryValidationRouteInterrupt(target, "assist_tank_focus_interrupt"))
                return true;

            ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);
            uint32 spellId = profileAction.SpellId;
            float engageRange = profileAction.MaxRange > 0.0f ? profileAction.MaxRange : routeEngageRange(bot, target, spellId);
            {
                std::string raw = BuildRawJson(bot, target);
                std::string semantic = BuildSemanticJson(bot, target, tankFocusSituation, &power, stage, activity);
                RecordEvent(state, bot, "validation_target_priority", target, tankFocusIsRouteTarget ? "assist_tank_focus" : "force_tank_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, spellId);
            }
            float targetDistance = bot->GetExactDist(target);
            if (profileAction.MinRange > 0.0f && targetDistance < profileAction.MinRange)
            {
                bool moved = moveOutOfProfileDeadZone(bot, target, profileAction);
                action = moved ? "move_to_profile_min_range" : "hold_tactical_path_rejected";
                situation = tankFocusSituation;
                return true;
            }
            if (!bot->IsValidAttackTarget(target) || targetDistance > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(target))
            {
                bool moved = MoveBotToProfileRange(state, bot, target, &profileAction);
                action = moved ? "move_to_validation_route_assist_target" : "hold_tactical_path_rejected";
                situation = tankFocusSituation;
                std::string raw = BuildRawJson(bot, target);
                std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
                RecordEvent(state, bot, tankFocusIsRouteTarget ? "validation_route_target_search" : "validation_route_prerequisite", target,
                    moved ? (tankFocusIsRouteTarget ? "assist_tank_focus" : "force_tank_focus") : "tactical_path_rejected", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry);
                if (!moved)
                    maybeValidationPrerequisiteNoProgressAssist(target, tankFocusIsRouteTarget ? "route_target_path_no_progress" : "force_tank_focus_path_no_progress");
                return true;
            }

            BotActionResult result = ExecuteProfileCombatAction(&state, bot, target, &profileAction);
            action = tankFocusIsRouteTarget
                ? (tankFocusIsBossRoute ? "validation_route_boss_action" : "validation_route_trash_action")
                : "validation_route_prerequisite_assist";
            situation = tankFocusSituation;
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
            RecordEvent(state, bot, tankFocusIsRouteTarget ? (tankFocusIsBossRoute ? "boss_action" : "trash_action") : "validation_route_prerequisite",
                target, ToString(result), raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
            if (tankFocusIsBossRoute)
                RecordEvent(state, bot, "boss_started", target, Cohort().Config.ValidationRouteMechanicProfile.c_str(), raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
            maybeValidationPrerequisiteNoProgressAssist(target, tankFocusIsRouteTarget ? "route_target_no_health_progress" : "force_tank_focus_no_health_progress");
            state.WasInCombat = true;
            return true;
        }

        if (routeFocusMemoryActive())
        {
            Unit* staleTarget = target && target->GetGUID() != Party().ValidationRouteFocusGuid ? target : nullptr;
            Unit* staleVictim = bot->GetVictim() && bot->GetVictim()->GetGUID() != Party().ValidationRouteFocusGuid ? bot->GetVictim() : nullptr;
            if (staleTarget || staleVictim)
            {
                Unit* rejected = staleVictim ? staleVictim : staleTarget;
                std::string raw = BuildRawJson(bot, rejected);
                std::string semantic = BuildSemanticJson(bot, rejected, "validation_route_regroup", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_prerequisite_rejected", rejected, "force_last_known_tank_focus", raw.c_str(), semantic.c_str(), rejected ? bot->GetExactDist(rejected) : 0.0f, Cohort().Config.ValidationRouteTargetEntry);
                state.TargetGuid.Clear();
                target = nullptr;
            }

            if (tryRouteGroupHeal(bot, nullptr))
                return true;

            float focusDistance = bot->GetExactDist(Party().ValidationRouteFocusX, Party().ValidationRouteFocusY, Party().ValidationRouteFocusZ);
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_regroup", &power, stage, activity);
            if (focusDistance > 10.0f)
            {
                if (++state.ValidationRouteUnresolvedFocusHoldCount >= 2)
                {
                    if (recoverAuthoritativeFocus("unresolved_authoritative_focus_recovery"))
                    {
                        situation = "validation_route_recovery";
                        action = "validation_route_recovery";
                        state.ValidationRouteUnresolvedFocusHoldCount = 0;
                        return true;
                    }

                    RecordEvent(state, bot, "validation_route_recovery", nullptr, "unresolved_authoritative_focus_unavailable", raw.c_str(), semantic.c_str(), focusDistance, Cohort().Config.ValidationRouteTargetEntry);
                    Party().ValidationRouteFocusGuid.Clear();
                    Party().ValidationRouteFocusEntry = 0;
                    Party().ValidationRouteFocusMapId = 0;
                    Party().ValidationRouteFocusX = 0.0f;
                    Party().ValidationRouteFocusY = 0.0f;
                    Party().ValidationRouteFocusZ = 0.0f;
                    Party().ValidationRouteFocusSeenMs = 0;
                    state.ValidationRouteUnresolvedFocusHoldCount = 0;
                    situation = "validation_route_regroup";
                    action = "validation_route_recover_unresolved_focus";
                    return true;
                }

                RecordEvent(state, bot, "validation_route_regroup", nullptr, "hold_unresolved_authoritative_focus", raw.c_str(), semantic.c_str(), focusDistance, Cohort().Config.ValidationRouteTargetEntry);
                situation = "validation_route_regroup";
                action = "validation_route_hold_focus";
                return true;
            }

            if (++state.ValidationRouteUnresolvedFocusHoldCount >= 3)
            {
                RecordEvent(state, bot, "validation_route_recovery", nullptr, "stale_focus_expired", raw.c_str(), semantic.c_str(), focusDistance, Cohort().Config.ValidationRouteTargetEntry);
                Party().ValidationRouteFocusGuid.Clear();
                Party().ValidationRouteFocusEntry = 0;
                Party().ValidationRouteFocusMapId = 0;
                Party().ValidationRouteFocusX = 0.0f;
                Party().ValidationRouteFocusY = 0.0f;
                Party().ValidationRouteFocusZ = 0.0f;
                Party().ValidationRouteFocusSeenMs = 0;
                state.ValidationRouteUnresolvedFocusHoldCount = 0;
            }
            else
            {
                RecordEvent(state, bot, "validation_route_regroup", nullptr, "hold_last_known_tank_focus", raw.c_str(), semantic.c_str(), focusDistance, Cohort().Config.ValidationRouteTargetEntry);
                situation = "validation_route_regroup";
                action = "validation_route_hold_focus";
                return true;
            }

            situation = "validation_route_regroup";
            action = "validation_route_recover_stale_focus";
        }
    }
    if (std::string(GetDungeonRole(bot)) != "tank")
    {
        ObjectGuid tankFocusGuid = routeTankFocusGuid();
        Unit* currentVictim = bot->GetVictim();
        if (currentVictim && currentVictim->IsAlive() && !tankFocusGuid.IsEmpty() && currentVictim->GetGUID() != tankFocusGuid)
        {
            std::string raw = BuildRawJson(bot, currentVictim);
            std::string semantic = BuildSemanticJson(bot, currentVictim, "validation_route_regroup", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_prerequisite_rejected", currentVictim, "regroup_tank_focus_mismatch", raw.c_str(), semantic.c_str(), bot->GetExactDist(currentVictim), Cohort().Config.ValidationRouteTargetEntry);
            state.TargetGuid.Clear();
            target = nullptr;

            if (Player* anchor = FindDungeonAnchor(bot))
            {
                if (anchor != bot && anchor->IsAlive() && anchor->GetMap() == bot->GetMap() && bot->GetExactDist(anchor) > 8.0f)
                {
                    MoveBotToProfileRange(state, bot, anchor);
                    RecordEvent(state, bot, "validation_route_regroup", anchor, "follow_anchor_tank_focus_mismatch", raw.c_str(), semantic.c_str(), bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                    situation = "validation_route_regroup";
                    action = "move_to_validation_route_anchor";
                    return true;
                }

                RecordEvent(state, bot, "validation_route_regroup", anchor, "hold_anchor_tank_focus_mismatch", raw.c_str(), semantic.c_str(), anchor == bot ? 0.0f : bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                situation = "validation_route_regroup";
                action = "validation_route_hold_anchor";
                return true;
            }

            situation = "validation_route_regroup";
            action = "validation_route_hold_anchor";
            return true;
        }
    }
    if (Unit* focusTarget = routeGroupFocusTarget())
    {
        state.ValidationRouteUnresolvedFocusHoldCount = 0;
        focusTarget = teacherAssistAuthoritativeFocus(focusTarget);
        if (!focusTarget)
        {
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_regroup", &power, stage, activity);
            std::string reason = "assist_target_search_authoritative_focus_" + authoritativeFocusFailure;
            RecordEvent(state, bot, "validation_route_prerequisite_rejected", nullptr, reason.c_str(), raw.c_str(), semantic.c_str(), 0.0f, Cohort().Config.ValidationRouteTargetEntry);
            situation = "validation_route_regroup";
            action = "validation_route_hold_anchor";
            return true;
        }

        if (authoritativeRouteFocusActive() && focusTarget->GetGUID() != Party().ValidationRouteFocusGuid)
        {
            std::string raw = BuildRawJson(bot, focusTarget);
            std::string semantic = BuildSemanticJson(bot, focusTarget, "validation_route_regroup", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_prerequisite_rejected", focusTarget, "reject_non_authoritative_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(focusTarget), Cohort().Config.ValidationRouteTargetEntry);
            state.TargetGuid.Clear();
            target = nullptr;

            if (Player* anchor = FindDungeonAnchor(bot))
            {
                if (anchor != bot && anchor->IsAlive() && anchor->GetMap() == bot->GetMap() && bot->GetExactDist(anchor) > 8.0f)
                {
                    MoveBotToProfileRange(state, bot, anchor);
                    RecordEvent(state, bot, "validation_route_regroup", anchor, "follow_anchor_non_authoritative_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                    situation = "validation_route_regroup";
                    action = "move_to_validation_route_anchor";
                    return true;
                }
            }

            situation = "validation_route_regroup";
            action = "validation_route_hold_anchor";
            return true;
        }

        target = focusTarget;
        state.TargetGuid = target->GetGUID();
        if (tryRouteGroupHeal(bot, target))
            return true;

        bool routeTrashFocus = Cohort().Config.ValidationRouteKind != "boss";
        if (!routeTrashFocus)
        {
            // A shared boss-route focus is hostile authority only when the
            // current route contract declares it.  Never let a stale or
            // prerequisite focus fall through to an unrestricted profile
            // action merely because another group member selected it.
            Creature const* focusCreature = target->ToCreature();
            if (!isValidationRouteObjectiveTarget(focusCreature))
            {
                bot->InterruptNonMeleeSpells(false);
                SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                    BotMeleeAutoAttack::Owner::Safety,
                    BotActionArbitration::Priority::Terminal,
                    "shared_boss_target_not_declared");
                if (Pet* pet = bot->GetPet())
                    pet->AttackStop();
                for (Unit* controlled : bot->m_Controlled)
                    if (controlled)
                        controlled->AttackStop();
                situation = "validation_route_prerequisite";
                action = "raid_target_not_declared_hold";
                return true;
            }

            // The typed authority owns target selection plus the contract's
            // allow_area_damage and allow_multidot policy.  A declared shared
            // focus that cannot establish that authority must remain closed.
            BossMechanicActionResult mechanic = TryBossMechanics(state, bot, power, stage, activity, target);
            if (mechanic.Handled)
            {
                situation = mechanic.Situation;
                action = mechanic.Action;
                target = mechanic.Target;
                return true;
            }

            bot->InterruptNonMeleeSpells(false);
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Safety,
                BotActionArbitration::Priority::Terminal,
                "shared_focus_mechanic_fail_closed");
            if (Pet* pet = bot->GetPet())
                pet->AttackStop();
            for (Unit* controlled : bot->m_Controlled)
                if (controlled)
                    controlled->AttackStop();
            situation = bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss";
            action = "raid_mechanic_contract_fail_closed";
            return true;
        }

        char const* focusSituation = routeTrashFocus ? "validation_route" : "validation_route_prerequisite";
        bool botIsTank = std::string(GetDungeonRole(bot)) == "tank";
        ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);
        uint32 spellId = profileAction.SpellId;
        float engageRange = profileAction.MaxRange > 0.0f ? profileAction.MaxRange : routeEngageRange(bot, target, spellId);
        {
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, focusSituation, &power, stage, activity);
            RecordEvent(state, bot, "validation_target_priority", target, routeTrashFocus ? "route_trash_focus" : "assist_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, spellId);
        }
        float targetDistance = bot->GetExactDist(target);
        if (profileAction.MinRange > 0.0f && targetDistance < profileAction.MinRange)
        {
            bool moved = moveOutOfProfileDeadZone(bot, target, profileAction);
            action = moved ? "move_to_profile_min_range" : "hold_tactical_path_rejected";
            situation = focusSituation;
            return true;
        }
        if (!bot->IsValidAttackTarget(target) || targetDistance > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(target))
        {
            bool moved = MoveBotToProfileRange(state, bot, target, &profileAction);
            action = moved
                ? (routeTrashFocus ? "move_to_validation_route_target" : "move_to_validation_route_assist_target")
                : "hold_tactical_path_rejected";
            situation = focusSituation;
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
            RecordEvent(state, bot, routeTrashFocus ? "validation_route_target_search" : "validation_route_prerequisite", target,
                moved ? (routeTrashFocus ? "approach_target" : "assist_focus") : "tactical_path_rejected", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry);
            if (!moved)
                maybeValidationPrerequisiteNoProgressAssist(target, routeTrashFocus ? "route_target_path_no_progress" : "assist_focus_path_no_progress");
            return true;
        }

        BotActionResult result = ExecuteProfileCombatAction(&state, bot, target, &profileAction);
        action = routeTrashFocus ? "validation_route_trash_action" : "validation_route_prerequisite_assist";
        situation = focusSituation;
        if (routeTrashFocus)
        {
            float healthPct = UnitHealthPct(target);
            RecordRouteProgress(state, bot, target, "route_target_combat_progress", healthPct, healthPct, 0, 20);
        }
        std::string raw = BuildRawJson(bot, target);
        std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
        RecordEvent(state, bot, routeTrashFocus ? "trash_action" : "validation_route_prerequisite", target, ToString(result), raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
        if (routeTrashFocus && botIsTank)
            RecordEvent(state, bot, "tank_positioning", target, "route_trash_tank_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
        maybeValidationPrerequisiteNoProgressAssist(target, routeTrashFocus ? "route_target_no_health_progress" : "assist_focus_no_health_progress");
        state.WasInCombat = true;
        return true;
    }
    if (std::string(GetDungeonRole(bot)) != "tank"
        && (Cohort().Config.ValidationRouteKind != "boss" || routeDistance <= routeArrivalRadius))
    {
        if (Player* anchor = FindDungeonAnchor(bot))
        {
            if (anchor != bot && anchor->IsAlive() && anchor->GetMap() == bot->GetMap())
            {
                if (target && target->IsAlive() && bot->IsValidAttackTarget(target))
                {
                    std::string raw = BuildRawJson(bot, target);
                    std::string semantic = BuildSemanticJson(bot, target, "validation_route_regroup", &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_prerequisite_rejected", target, "regroup_anchor_no_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                    state.TargetGuid.Clear();
                    target = nullptr;
                }

                if (bot->GetExactDist(anchor) > 8.0f
                    && !(Cohort().Config.ValidationRouteKind == "boss" && Party().ValidationRouteActivationApplied))
                {
                    MoveBotToPoint(state, bot, anchor->GetPositionX(), anchor->GetPositionY(), anchor->GetPositionZ());
                    std::string raw = BuildRawJson(bot, nullptr);
                    std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_regroup", &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_regroup", anchor, "follow_anchor_no_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                    situation = "validation_route_regroup";
                    action = "move_to_validation_route_anchor";
                    return true;
                }

                std::string raw = BuildRawJson(bot, nullptr);
                std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_regroup", &power, stage, activity);
                if (Cohort().Config.ValidationRouteKind == "boss"
                    && hasValidationRouteActivation)
                {
                    if (Party().ValidationRouteActivationApplied)
                    {
                        state.ValidationRouteActivationApplied = true;
                        state.ValidationRouteActivationAttempts = Party().ValidationRouteActivationAttempts;
                        RecordEvent(state, bot, "validation_route_recovery", nullptr, "boss_route_no_focus_activation_already_applied", raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry);
                    }
                    else
                        RecordEvent(state, bot, "validation_route_recovery", nullptr, "boss_route_wait_for_tank_activation", raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry);
                    situation = "validation_route_regroup";
                    action = "validation_route_hold_anchor";
                    return true;
                }

                RecordEvent(state, bot, "validation_route_regroup", anchor, "hold_anchor_no_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                situation = "validation_route_regroup";
                action = "validation_route_hold_anchor";
                return true;
            }
        }
    }
    if (bot->IsInCombat() && target && target->IsAlive() && bot->IsValidAttackTarget(target))
    {
        Creature const* creature = target->ToCreature();
        if (Cohort().Config.ValidationRouteKind != "boss" && creature && isValidationCohortCombatLinked(creature))
            enrollValidationRoutePackMember(creature, true);
        bool routeBossTarget = isValidationRouteObjectiveTarget(creature);
        float targetRouteDistance = target->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ);
        bool ineligibleTrashTarget = Cohort().Config.ValidationRouteKind != "boss" && creature && !isEligibleTrashClusterMob(creature);
        if (!routeBossTarget && creature && targetRouteDistance > 120.0f)
        {
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, "validation_route_prerequisite_rejected", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_prerequisite_rejected", target, "off_route_target", raw.c_str(), semantic.c_str(), targetRouteDistance, Cohort().Config.ValidationRouteTargetEntry);
        }
        else if (ineligibleTrashTarget)
        {
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, "validation_route_prerequisite_rejected", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_prerequisite_rejected", target, "ineligible_trash_target", raw.c_str(), semantic.c_str(), targetRouteDistance, Cohort().Config.ValidationRouteTargetEntry);
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Safety,
                BotActionArbitration::Priority::Terminal,
                "ineligible_trash_target");
            state.TargetGuid.Clear();
            target = nullptr;
        }
    }
    if (bot->IsInCombat() && target && target->IsAlive() && bot->IsValidAttackTarget(target))
    {
        Creature const* creature = target->ToCreature();
        bool routeBossTarget = isValidationRouteObjectiveTarget(creature);
        if (routeBossTarget && Cohort().Config.ValidationRouteKind != "boss")
            enrollValidationRoutePackMember(creature, isValidationCohortCombatLinked(creature));
        if (routeBossTarget)
            rememberValidationRouteFocus(target);
        if (routeBossTarget && Cohort().Config.ValidationRouteKind == "boss")
        {
            BossMechanicActionResult mechanic = TryBossMechanics(state, bot, power, stage, activity, target);
            if (mechanic.Handled)
            {
                situation = mechanic.Situation;
                action = mechanic.Action;
                target = mechanic.Target;
                return true;
            }

            bot->InterruptNonMeleeSpells(false);
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Safety,
                BotActionArbitration::Priority::Terminal,
                "raid_mechanic_contract_fail_closed");
            if (Pet* pet = bot->GetPet())
                pet->AttackStop();
            for (Unit* controlled : bot->m_Controlled)
                if (controlled)
                    controlled->AttackStop();
            situation = bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss";
            action = "raid_mechanic_contract_fail_closed";
            return true;
        }
        if (tryRouteGroupHeal(bot, target))
            return true;
        if (routeBossTarget && Cohort().Config.ValidationRouteKind == "boss" && tryValidationRouteInterrupt(target, "route_boss_focus_interrupt"))
            return true;

        if (routeBossTarget && Cohort().Config.ValidationRouteKind == "boss" && bot->getClass() == CLASS_HUNTER)
        {
            Player* tank = FindDungeonAnchor(bot);
            if (tank && tank != bot && std::string(GetDungeonRole(tank)) == "tank")
            {
                if (bot->HasSpell(34477) && !bot->HasAura(34477)
                    && TryCastFriendlySpell(bot, tank, 34477))
                {
                    std::string raw = BuildRawJson(bot, target);
                    std::string semantic = BuildSemanticJson(bot, target, "dungeon_boss", &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_threat_transfer", target,
                        "misdirection_to_tank", raw.c_str(), semantic.c_str(), 1.0f,
                        Cohort().Config.ValidationRouteTargetEntry, 34477);
                    situation = "dungeon_boss";
                    action = "misdirection_to_tank";
                    return true;
                }
                if (bot->HasAura(34477))
                {
                    ResolvedCombatAction transferAction = ResolveProfileCombatAction(bot, target, 1, false);
                    BotActionResult result = ExecuteProfileCombatAction(&state, bot, target, &transferAction, 1, false);
                    std::string raw = BuildRawJson(bot, target);
                    std::string semantic = BuildSemanticJson(bot, target, "dungeon_boss", &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_threat_transfer", target,
                        "misdirection_single_target_transfer", raw.c_str(), semantic.c_str(), 1.0f,
                        Cohort().Config.ValidationRouteTargetEntry,
                        result == BotActionResult::Ok ? transferAction.SpellId : 0);
                    situation = "dungeon_boss";
                    action = "misdirection_single_target_transfer";
                    state.WasInCombat = true;
                    return true;
                }
            }
        }

        ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);
        uint32 spellId = profileAction.SpellId;
        float engageRange = profileAction.MaxRange > 0.0f ? profileAction.MaxRange : routeEngageRange(bot, target, spellId);
        bool botIsTank = std::string(GetDungeonRole(bot)) == "tank";
        bool routeTrashPackTarget = Cohort().Config.ValidationRouteKind != "boss"
            && creature && isEligibleTrashClusterMob(creature);
        if (routeTrashPackTarget && !botIsTank
            && validationRouteHasLivingTank() && !routeFocusTankOwned(target))
        {
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, "validation_route_regroup", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_prerequisite_rejected", target, "wait_for_tank_threat", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry);
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Threat,
                BotActionArbitration::Priority::ThreatControl,
                "wait_for_tank_threat");
            if (Pet* pet = bot->GetPet())
                pet->AttackStop();
            state.TargetGuid.Clear();
            situation = "validation_route_regroup";
            action = "validation_route_hold_anchor";
            return true;
        }
        if (routeBossTarget)
        {
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
            RecordEvent(state, bot, "validation_target_priority", target, Cohort().Config.ValidationRouteKind == "boss" ? "route_boss_focus" : "route_trash_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, spellId);
        }
        float targetDistance = bot->GetExactDist(target);
        if (profileAction.MinRange > 0.0f && targetDistance < profileAction.MinRange)
        {
            bool moved = moveOutOfProfileDeadZone(bot, target, profileAction);
            action = moved ? "move_to_profile_min_range" : "hold_tactical_path_rejected";
            situation = routeBossTarget ? situation : "validation_route_prerequisite";
            return true;
        }
        if (targetDistance > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(target))
        {
            bool moved = MoveBotToProfileRange(state, bot, target, &profileAction);
            action = moved
                ? (routeBossTarget ? "move_to_validation_route_target" : "move_to_validation_route_prerequisite")
                : "hold_tactical_path_rejected";
            situation = routeBossTarget ? situation : "validation_route_prerequisite";
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
            RecordEvent(state, bot, routeBossTarget ? "validation_route_target_search" : "validation_route_prerequisite", target,
                moved ? "approach_target" : "tactical_path_rejected", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry);
            if (!moved && !routeBossTarget)
                maybeValidationPrerequisiteNoProgressAssist(target, "current_combat_path_no_progress");
            return true;
        }

        BotActionResult result = ExecuteProfileCombatAction(&state, bot, target, &profileAction);
        action = routeBossTarget
            ? (Cohort().Config.ValidationRouteKind == "boss" ? (std::string(GetDungeonRole(bot)) == "tank" ? "validation_route_tank_boss" : "validation_route_boss_action") : "validation_route_trash_action")
            : "validation_route_prerequisite_action";
        situation = routeBossTarget ? situation : "validation_route_prerequisite";
        if (routeBossTarget && Cohort().Config.ValidationRouteKind != "boss")
        {
            float healthPct = UnitHealthPct(target);
            RecordRouteProgress(state, bot, target, "route_target_combat_progress", healthPct, healthPct, 0, 20);
        }
        std::string raw = BuildRawJson(bot, target);
        std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
        RecordEvent(state, bot, routeBossTarget ? (Cohort().Config.ValidationRouteKind == "boss" ? "boss_action" : "trash_action") : "validation_route_prerequisite", target, ToString(result), raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
        if (routeBossTarget && Cohort().Config.ValidationRouteKind != "boss" && botIsTank)
            RecordEvent(state, bot, "tank_positioning", target, "route_trash_tank_focus", raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
        if (!routeBossTarget)
            maybeValidationPrerequisiteNoProgressAssist(target, "current_combat_no_health_progress");
        if (routeBossTarget && Cohort().Config.ValidationRouteKind == "boss")
        {
            RecordEvent(state, bot, "boss_started", target, Cohort().Config.ValidationRouteMechanicProfile.c_str(), raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
            maybeValidationPrerequisiteNoProgressAssist(target, "boss_route_no_health_progress");
        }
        state.WasInCombat = true;
        return true;
    }

    if (Cohort().Config.ValidationRouteKind == "boss"
        && hasValidationRouteActivation
        && !Party().ValidationRouteActivationApplied
        && (Cohort().Config.ValidationRouteActivationAreaTriggerId
            || routeDistance <= routeArrivalRadius)
        && tryValidationRouteActivation(nullptr, "boss_route_early_activation"))
    {
        action = "validation_route_activate_target";
        return true;
    }

    Unit* preAnchorTrashTarget = nullptr;
    if (Cohort().Config.ValidationRouteKind != "boss" && std::string(GetDungeonRole(bot)) == "tank")
    {
        preAnchorTrashTarget = findTrashClusterThreatTarget();
        if (!preAnchorTrashTarget)
        {
            ObjectGuid::LowType canonicalSpawnId = currentValidationRouteTargetSpawnId();
            Creature* canonicalSource = canonicalSpawnId && bot->GetMap()
                ? bot->GetMap()->GetCreatureBySpawnId(canonicalSpawnId) : nullptr;
            if (isEligibleTrashClusterMob(canonicalSource))
            {
                preAnchorTrashTarget = canonicalSource;
                enrollValidationRoutePackMember(canonicalSource,
                    isValidationCohortCombatLinked(canonicalSource));
            }
        }
        float clusterApproachRadius = std::max(
            routeArrivalRadius,
            Cohort().Config.ValidationRouteClusterRadiusYards > 1.0f
                ? Cohort().Config.ValidationRouteClusterRadiusYards
                : 90.0f);
        if (preAnchorTrashTarget && routeDistance > clusterApproachRadius)
        {
            Creature* threatCreature = preAnchorTrashTarget->ToCreature();
            if (!threatCreature
                || (!isValidationCohortCombatLinked(threatCreature)
                    && !isCurrentDiscoveryScriptedEventTarget(threatCreature)))
                preAnchorTrashTarget = nullptr;
        }
        // Rerun74 proved that the canonical source can seed and complete its
        // pack while another declared current-node patrol remains live beyond
        // the static arrival radius. Keep that strictly pathable candidate as
        // pre-anchor movement authority; the existing cluster-approach bound
        // below still prevents pulling a distant pack before reaching the node.
        if (!preAnchorTrashTarget)
            preAnchorTrashTarget = findNearestTrashClusterMob();
    }

    if (routeDistance > routeArrivalRadius && !preAnchorTrashTarget)
    {
        moveToRouteAnchor();
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_move", nullptr, routeAnchorReason == "validation_route" ? Cohort().Config.ValidationRouteLabel.c_str() : routeAnchorReason.c_str(), raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry);
        action = "move_to_validation_route";
        return true;
    }

    Unit* routeTarget = preAnchorTrashTarget;
    Unit* seenRouteTarget = preAnchorTrashTarget;
    std::string targetSearchResult = "target_not_found";
    float seenRouteTargetDistance = preAnchorTrashTarget ? bot->GetExactDist(preAnchorTrashTarget) : 0.0f;
    if (preAnchorTrashTarget)
        targetSearchResult = "target_ready_before_route_anchor";
    if (Cohort().Config.ValidationRouteTargetEntry && !routeTarget)
    {
        float routeTargetSearchRange = Cohort().Config.ValidationRouteKind == "boss" ? 220.0f : 140.0f;
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, routeTargetSearchRange);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, routeTargetSearchRange);

        float bestDistance = 0.0f;
        float bestSeenDistance = 0.0f;
        for (WorldObject* object : objects)
        {
            Unit* unit = object ? object->ToUnit() : nullptr;
            Creature* creature = unit ? unit->ToCreature() : nullptr;
            if (!isValidationRouteScriptTarget(creature))
                continue;

            bool recordedCurrentDead = Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
                && (!creature->IsAlive() || !creature->GetHealth())
                && (Party().ValidationRoutePackDeathGuids.find(creature->GetGUID()) != Party().ValidationRoutePackDeathGuids.end()
                    || Party().ValidationRouteRecordedKillGuids.find(creature->GetGUID()) != Party().ValidationRouteRecordedKillGuids.end());
            if (recordedCurrentDead)
                continue;

            float distance = bot->GetExactDist(creature);
            if (!seenRouteTarget || distance < bestSeenDistance)
            {
                seenRouteTarget = creature;
                bestSeenDistance = distance;
                seenRouteTargetDistance = distance;
            }

            if (!creature->IsAlive() || !creature->GetHealth())
            {
                targetSearchResult = "target_seen_dead";
                continue;
            }

            if (!isValidationRouteCombatTarget(creature))
            {
                if (targetSearchResult == "target_not_found")
                    targetSearchResult = "target_seen_activation_target";
                continue;
            }

            if (!bot->IsWithinLOSInMap(creature))
            {
                targetSearchResult = "target_seen_no_los";
                continue;
            }

            if (!bot->IsValidAttackTarget(creature))
            {
                if (Unit* readied = makeExistingValidationRouteCombatReady(creature))
                {
                    routeTarget = readied;
                    bestDistance = distance;
                    targetSearchResult = "target_ready_after_activation";
                    continue;
                }

                targetSearchResult = "target_seen_not_attackable";
                continue;
            }

            Creature const* currentRouteCreature = routeTarget ? routeTarget->ToCreature() : nullptr;
            bool candidateOpener = Cohort().Config.ValidationRouteOpenerTargetEntry && creature->GetEntry() == Cohort().Config.ValidationRouteOpenerTargetEntry;
            bool currentOpener = currentRouteCreature && Cohort().Config.ValidationRouteOpenerTargetEntry && currentRouteCreature->GetEntry() == Cohort().Config.ValidationRouteOpenerTargetEntry;
            if (!routeTarget || (candidateOpener && !currentOpener) || (candidateOpener == currentOpener && distance < bestDistance))
            {
                routeTarget = creature;
                bestDistance = distance;
                targetSearchResult = "target_ready";
            }
        }
    }
    // Azil can survive an evade as a visible but unreachable canonical spawn.
    // Other bosses, notably Corborus while burrowed, use transient LOS states
    // that must remain under their native encounter controller.
    if (!routeTarget
        && seenRouteTarget
        && Cohort().Config.ValidationRouteKind == "boss"
        && Cohort().Config.ValidationRouteTargetEntry == 42333
        && (targetSearchResult == "target_seen_not_attackable" || targetSearchResult == "target_seen_no_los"))
    {
        bool tankOwnsBossRecovery = std::string(GetDungeonRole(bot)) == "tank";
        if (tankOwnsBossRecovery)
            ++state.ValidationRouteTargetSearchMissCount;

        if (tankOwnsBossRecovery && state.ValidationRouteTargetSearchMissCount >= 3)
        {
            std::string recoveryResult;
            bool recoveryInitiated = false;
            if (tryCanonicalValidationRouteBossRecovery(recoveryResult, recoveryInitiated))
            {
                situation = recoveryInitiated ? "validation_route_recovery" : "validation_route_blocked";
                action = recoveryInitiated ? "recover_canonical_validation_route_boss" : "blocked_no_fallback";
                return true;
            }
        }

        if (tankOwnsBossRecovery
            && Party().ValidationRouteCanonicalBossRecoveryAttempts >= 2
            && state.ValidationRouteTargetSearchMissCount >= 6)
        {
            std::string raw = BuildRawJson(bot, seenRouteTarget);
            std::string semantic = BuildSemanticJson(bot, seenRouteTarget, "validation_route_canonical_boss_recovery_no_reachable_target", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_recovery", seenRouteTarget, "canonical_boss_recovery_no_reachable_target", raw.c_str(), semantic.c_str(), seenRouteTargetDistance, Cohort().Config.ValidationRouteTargetEntry);
            MarkBotBlocked(state, bot, "canonical_boss_recovery_no_reachable_target");
            situation = "validation_route_blocked";
            action = "blocked_no_fallback";
            return true;
        }

        std::string raw = BuildRawJson(bot, seenRouteTarget);
        std::string semantic = BuildSemanticJson(bot, seenRouteTarget, "validation_route_script_target_blocked", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_target_search", seenRouteTarget, targetSearchResult.c_str(), raw.c_str(), semantic.c_str(), seenRouteTargetDistance, Cohort().Config.ValidationRouteTargetEntry);
        state.LastNoProgressReason = targetSearchResult;
        action = "validation_route_recovery";
        return true;
    }
    if (!routeTarget
        && seenRouteTarget
        && Cohort().Config.ValidationRouteKind == "boss"
        && targetSearchResult == "target_seen_dead")
    {
        std::string raw = BuildRawJson(bot, seenRouteTarget);
        std::string semantic = BuildSemanticJson(bot, seenRouteTarget, "validation_route_script_target_dead", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_target_search", seenRouteTarget, targetSearchResult.c_str(), raw.c_str(), semantic.c_str(), seenRouteTargetDistance, Cohort().Config.ValidationRouteTargetEntry);
        clearValidationRouteKilledFocus(seenRouteTarget->GetGUID());
        state.LastNoProgressReason = targetSearchResult;
        action = "validation_route_recovery";
        return true;
    }
    if (!routeTarget
        && seenRouteTarget
        && Cohort().Config.ValidationRouteKind != "boss"
        && targetSearchResult == "target_seen_dead")
    {
        Party().ValidationRouteObservedDeadScriptTarget = true;
        recordValidationRouteTrashKill(seenRouteTarget, "target_seen_dead");
        clearValidationRouteKilledFocus(seenRouteTarget->GetGUID());
        seenRouteTarget = nullptr;
    }
    if (!routeTarget && seenRouteTarget && seenRouteTargetDistance > 8.0f)
    {
        if (Cohort().Config.ValidationRouteKind == "boss"
            && !isValidationRouteObjectiveTarget(seenRouteTarget->ToCreature()))
        {
            bot->InterruptNonMeleeSpells(false);
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Safety,
                BotActionArbitration::Priority::Terminal,
                "seen_boss_target_not_declared");
            if (Pet* pet = bot->GetPet())
                pet->AttackStop();
            for (Unit* controlled : bot->m_Controlled)
                if (controlled)
                    controlled->AttackStop();
            std::string raw = BuildRawJson(bot, seenRouteTarget);
            std::string semantic = BuildSemanticJson(
                bot, seenRouteTarget, "validation_route_prerequisite", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_prerequisite_rejected",
                seenRouteTarget, "boss_route_undeclared_prerequisite_blocked",
                raw.c_str(), semantic.c_str(), seenRouteTargetDistance,
                Cohort().Config.ValidationRouteTargetEntry);
            state.TargetGuid.Clear();
            target = nullptr;
            situation = "validation_route_prerequisite";
            action = "boss_route_prerequisite_blocked";
            return true;
        }
        tryValidationRouteActivation(seenRouteTarget, targetSearchResult.c_str());
        MoveBotToProfileRange(state, bot, seenRouteTarget);
        std::string raw = BuildRawJson(bot, seenRouteTarget);
        std::string semantic = BuildSemanticJson(bot, seenRouteTarget, "validation_route_target_approach", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_target_search", seenRouteTarget, targetSearchResult.c_str(), raw.c_str(), semantic.c_str(), seenRouteTargetDistance, Cohort().Config.ValidationRouteTargetEntry);
        action = "move_to_validation_route_target";
        return true;
    }
    if (!routeTarget && seenRouteTarget)
    {
        if (tryValidationRouteActivation(seenRouteTarget, targetSearchResult.c_str()))
        {
            std::string raw = BuildRawJson(bot, seenRouteTarget);
            std::string semantic = BuildSemanticJson(bot, seenRouteTarget, "validation_route_activation", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_target_search", seenRouteTarget, "activation_applied", raw.c_str(), semantic.c_str(), seenRouteTargetDistance, Cohort().Config.ValidationRouteTargetEntry);
            action = "validation_route_activate_target";
            return true;
        }

        if (Cohort().Config.ValidationRouteKind == "boss")
        {
            bot->InterruptNonMeleeSpells(false);
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Safety,
                BotActionArbitration::Priority::Terminal,
                "boss_activation_fail_closed");
            if (Pet* pet = bot->GetPet())
                pet->AttackStop();
            for (Unit* controlled : bot->m_Controlled)
                if (controlled)
                    controlled->AttackStop();
            std::string raw = BuildRawJson(bot, seenRouteTarget);
            std::string semantic = BuildSemanticJson(
                bot, seenRouteTarget, "validation_route_prerequisite", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_prerequisite_rejected",
                seenRouteTarget, "boss_route_undeclared_prerequisite_blocked",
                raw.c_str(), semantic.c_str(), seenRouteTargetDistance,
                Cohort().Config.ValidationRouteTargetEntry);
            state.TargetGuid.Clear();
            target = nullptr;
            situation = "validation_route_prerequisite";
            action = "boss_route_prerequisite_blocked";
            return true;
        }

        Creature* prerequisiteTarget = nullptr;
        float prerequisiteScore = -100000.0f;
        float prerequisiteDistance = 0.0f;
        if (Unit* focusTarget = routeGroupFocusTarget())
        {
            prerequisiteTarget = focusTarget->ToCreature();
            prerequisiteScore = 100000.0f;
            prerequisiteDistance = bot->GetExactDist(focusTarget);
        }
        if (!prerequisiteTarget && std::string(GetDungeonRole(bot)) != "tank")
        {
            if (Player* anchor = FindDungeonAnchor(bot))
            {
                std::string raw = BuildRawJson(bot, nullptr);
                std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_regroup", &power, stage, activity);
                if (anchor != bot && anchor->IsAlive() && anchor->GetMap() == bot->GetMap() && bot->GetExactDist(anchor) > 8.0f)
                {
                    MoveBotToProfileRange(state, bot, anchor);
                    RecordEvent(state, bot, "validation_route_regroup", anchor, "follow_anchor_before_prerequisite", raw.c_str(), semantic.c_str(), bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                    situation = "validation_route_regroup";
                    action = "move_to_validation_route_anchor";
                    return true;
                }

                if (Cohort().Config.ValidationRouteKind == "boss")
                {
                    RecordEvent(state, bot, "validation_route_regroup", anchor, "hold_anchor_before_prerequisite", raw.c_str(), semantic.c_str(), anchor == bot ? 0.0f : bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                    situation = "validation_route_regroup";
                    action = "validation_route_hold_anchor";
                    return true;
                }
            }
        }
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, 320.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, 320.0f);
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!creature || creature == seenRouteTarget || !creature->IsAlive() || !bot->IsValidAttackTarget(creature))
                continue;
            if (Cohort().Config.ValidationRouteKind != "boss" && !isEligibleTrashClusterMob(creature))
                continue;
            if (creature->IsDungeonBoss() || creature->isWorldBoss())
                continue;
            if (creature->IsCritter() || creature->IsPet() || creature->IsTotem() || creature->IsSummon() || creature->IsGuardian() || !creature->GetOwnerGUID().IsEmpty())
                continue;
            if (Cohort().Config.ValidationRouteKind == "boss" && Party().ValidationRouteActivationApplied
                && !isValidationRouteScriptTarget(creature) && !creature->IsInCombat() && !creature->GetVictim()
                && !isValidationCohortCombatLinked(creature))
                continue;

            float distance = bot->GetExactDist(creature);
            float routeProximity = creature->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ);
            std::string scriptName = creature->GetScriptName();
            if (routeProximity > 120.0f)
                continue;

            float score = 320.0f - distance;
            if (!scriptName.empty())
                score += 700.0f;
            if (creature->isElite())
                score += 35.0f;
            if (scriptName.empty() && routeProximity < 120.0f)
                score += 60.0f;
            if (creature->GetVictim() == bot)
                score += 80.0f;

            if (score > prerequisiteScore)
            {
                prerequisiteTarget = creature;
                prerequisiteScore = score;
                prerequisiteDistance = distance;
            }
        }

        if (prerequisiteTarget)
        {
            target = prerequisiteTarget;
            prerequisiteDistance = bot->GetExactDist(target);
            state.TargetGuid = target->GetGUID();
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, "validation_route_prerequisite", &power, stage, activity);
            if (tryRouteGroupHeal(bot, target))
                return true;

            if (prerequisiteDistance > 35.0f || !bot->IsWithinLOSInMap(target))
            {
                bool moved = MoveBotToProfileRange(state, bot, target);
                RecordEvent(state, bot, "validation_route_prerequisite", target, moved ? "move_to_blocker" : "tactical_path_rejected", raw.c_str(), semantic.c_str(), prerequisiteDistance, Cohort().Config.ValidationRouteTargetEntry);
                if (!moved)
                    maybeValidationPrerequisiteNoProgressAssist(target, "blocker_path_no_progress");
                situation = "validation_route_prerequisite";
                action = moved ? "move_to_validation_route_prerequisite" : "hold_tactical_path_rejected";
                return true;
            }

            ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);
            uint32 spellId = profileAction.SpellId;
            float engageRange = profileAction.MaxRange > 0.0f ? profileAction.MaxRange : routeEngageRange(bot, target, spellId);
            float targetDistance = bot->GetExactDist(target);
            if (profileAction.MinRange > 0.0f && targetDistance < profileAction.MinRange)
            {
                bool moved = moveOutOfProfileDeadZone(bot, target, profileAction);
                action = moved ? "move_to_profile_min_range" : "hold_tactical_path_rejected";
                situation = "validation_route_prerequisite";
                return true;
            }
            if (targetDistance > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(target))
            {
                bool moved = MoveBotToProfileRange(state, bot, target, &profileAction);
                RecordEvent(state, bot, "validation_route_prerequisite", target, moved ? "approach_target" : "tactical_path_rejected", raw.c_str(), semantic.c_str(), prerequisiteDistance, Cohort().Config.ValidationRouteTargetEntry);
                if (!moved)
                    maybeValidationPrerequisiteNoProgressAssist(target, "blocker_path_no_progress");
                situation = "validation_route_prerequisite";
                action = moved ? "move_to_validation_route_prerequisite" : "hold_tactical_path_rejected";
                return true;
            }

            BotActionResult result = ExecuteProfileCombatAction(&state, bot, target, &profileAction);
            RecordEvent(state, bot, "validation_route_prerequisite", target, ToString(result), raw.c_str(), semantic.c_str(), prerequisiteDistance, Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
            maybeValidationPrerequisiteNoProgressAssist(target, "blocker_no_health_progress");
            situation = "validation_route_prerequisite";
            action = "validation_route_prerequisite_action";
            state.WasInCombat = true;
            return true;
        }

        state.LastNoProgressReason = targetSearchResult;
        std::string raw = BuildRawJson(bot, seenRouteTarget);
        std::string semantic = BuildSemanticJson(bot, seenRouteTarget, "validation_route_blocked", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_failed", seenRouteTarget, targetSearchResult.c_str(), raw.c_str(), semantic.c_str(), seenRouteTargetDistance, Cohort().Config.ValidationRouteTargetEntry);
        action = "validation_route_target_blocked";
        return true;
    }
    if (!routeTarget && Cohort().Config.ValidationRouteKind != "boss" && routeDistance <= routeArrivalRadius && std::string(GetDungeonRole(bot)) == "tank")
    {
        Unit* anchorTarget = findTrashClusterThreatTarget();
        if (!anchorTarget)
            anchorTarget = findNearestTrashClusterMob();
        if (anchorTarget)
        {
            routeTarget = anchorTarget;
            targetSearchResult = isValidationRouteScriptTarget(anchorTarget->ToCreature()) ? "target_ready" : "anchor_reacquired_reachable_target";
            state.ValidationRouteTargetSearchMissCount = 0;
        }
        else if ((discoveryLeg ? (Party().ValidationRouteCompletedPackCount > 0 || Party().ValidationRouteObservedDeadScriptTarget)
                : Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
                    && (Party().ValidationRoutePackObservedEngagement || Party().ValidationRouteObservedDeadScriptTarget))
            && ++state.ValidationRouteTargetSearchMissCount >= 2)
        {
            bool packHasLiveMobs = trashClusterHasLiveMobs();
            bool partyHasActiveCombatUnit =
                validationPartyHasActiveCombat(!packHasLiveMobs);
            Unit* terminalCombatTarget = !packHasLiveMobs && partyHasActiveCombatUnit
                ? findBoundedTerminalPartyCombatTarget() : nullptr;
            bool fullCohortAtEndpoint = true;
            uint32 loadedParticipants = 0;
            for (WorldBotState const& cohortState : Party().Bots)
                if (Player* member = GetLoadedBot(cohortState))
                {
                    ++loadedParticipants;
                    if (!member->IsInWorld() || !member->IsAlive() || !IsValidationCohortMemberInOriginalInstance(cohortState, member)
                        || member->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ) > routeArrivalRadius)
                        fullCohortAtEndpoint = false;
                }
            if ((Cohort().Config.TargetPopulation && loadedParticipants < Cohort().Config.TargetPopulation) || !loadedParticipants)
                fullCohortAtEndpoint = false;
            uint64 nowMs = NowMs();
            uint64& clearCandidateSinceMs = discoveryLeg ? Party().ValidationRouteNodeClearCandidateSinceMs : Party().ValidationRoutePackClearCandidateSinceMs;
            if (packHasLiveMobs || partyHasActiveCombatUnit || !fullCohortAtEndpoint)
                clearCandidateSinceMs = 0;
            else if (!clearCandidateSinceMs)
                clearCandidateSinceMs = nowMs;
            uint64 quietElapsedMs = clearCandidateSinceMs ? nowMs - clearCandidateSinceMs : 0;
            uint64 quietRemainingMs = quietElapsedMs >= 2000 ? 0 : 2000 - quietElapsedMs;

            if (terminalCombatTarget)
            {
                routeTarget = terminalCombatTarget;
                targetSearchResult = "terminal_party_combat_focus";
                state.ValidationRouteTargetSearchMissCount = 0;
                std::string raw = BuildRawJson(bot, terminalCombatTarget);
                std::string semantic = BuildSemanticJson(bot, terminalCombatTarget, "validation_route_prerequisite", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_recovery", terminalCombatTarget,
                    "terminal_party_combat_focus_acquired", raw.c_str(), semantic.c_str(),
                    bot->GetExactDist(terminalCombatTarget), terminalCombatTarget->GetEntry());
            }
            else if (Cohort().Config.ValidationRouteAdvanceMode == "terminal"
                && (discoveryLeg ? (Party().ValidationRouteCompletedPackCount > 0 || Party().ValidationRouteObservedDeadScriptTarget)
                    : (Party().ValidationRoutePackObservedEngagement || Party().ValidationRouteObservedDeadScriptTarget))
                && !packHasLiveMobs
                && !partyHasActiveCombatUnit
                && fullCohortAtEndpoint
                && nowMs - clearCandidateSinceMs >= 2000)
            {
                if (discoveryLeg)
                {
                    Party().ValidationRouteFinalTransitionGuids.insert(Party().ValidationRoutePendingFinalTransitionGuids.begin(), Party().ValidationRoutePendingFinalTransitionGuids.end());
                    Party().ValidationRoutePendingFinalTransitionGuids.clear();
                }
                std::string raw = BuildRawJson(bot, nullptr);
                std::string semantic = BuildSemanticJson(bot, nullptr, "normal_dungeon_trash", &power, stage, activity);
                markTrashClusterCleared("trash_cluster_cleared");
                RecordEvent(state, bot, "dungeon_trash_cleared", nullptr, "trash_cluster_cleared", raw.c_str(), semantic.c_str(), float(Cohort().Metrics.Kills), Cohort().Config.ValidationRouteTargetEntry);
                MaybeAdvanceValidationRouteManifest();
            }
            else
            {
                char const* holdReason = packHasLiveMobs ? "dynamic_pack_members_live_or_unobserved"
                    : partyHasActiveCombatUnit ? "trash_cluster_party_combat_active"
                    : !fullCohortAtEndpoint ? "trash_cluster_cohort_not_at_endpoint"
                    : Cohort().Config.ValidationRouteAdvanceMode != "terminal" ? "trash_cluster_terminal_mode_required"
                    : "trash_cluster_clear_stability_pending";
                std::ostringstream raw;
                raw << "{\"base\":" << BuildRawJson(bot, nullptr)
                    << ",\"terminal_hold\":{\"pack_has_live_mobs\":" << (packHasLiveMobs ? "true" : "false")
                    << ",\"party_has_active_combat\":" << (partyHasActiveCombatUnit ? "true" : "false")
                    << ",\"full_cohort_at_endpoint\":" << (fullCohortAtEndpoint ? "true" : "false")
                    << ",\"quiet_elapsed_ms\":" << quietElapsedMs
                    << ",\"quiet_remaining_ms\":" << quietRemainingMs << "}"
                    << ",\"terminal_blocker\":";
                if (packHasLiveMobs)
                    raw << "{\"guid\":" << trashClusterTerminalBlocker.Guid.GetCounter()
                        << ",\"entry\":" << trashClusterTerminalBlocker.Entry
                        << ",\"spawn_id\":" << trashClusterTerminalBlocker.SpawnId
                        << ",\"formation_id\":" << trashClusterTerminalBlocker.FormationId
                        << ",\"formation_leader_guid\":" << trashClusterTerminalBlocker.FormationLeaderGuid.GetCounter()
                        << ",\"distance\":" << trashClusterTerminalBlocker.Distance
                        << ",\"position\":{\"x\":" << trashClusterTerminalBlocker.PositionX
                        << ",\"y\":" << trashClusterTerminalBlocker.PositionY
                        << ",\"z\":" << trashClusterTerminalBlocker.PositionZ << "}"
                        << ",\"home\":{\"x\":" << trashClusterTerminalBlocker.HomeX
                        << ",\"y\":" << trashClusterTerminalBlocker.HomeY
                        << ",\"z\":" << trashClusterTerminalBlocker.HomeZ
                        << ",\"distance\":" << trashClusterTerminalBlocker.HomeDistance << "}"
                        << ",\"current_motion_type\":" << trashClusterTerminalBlocker.CurrentMotionType
                        << ",\"active_motion_type\":" << trashClusterTerminalBlocker.ActiveMotionType
                        << ",\"observed\":" << (trashClusterTerminalBlocker.Observed ? "true" : "false")
                        << ",\"alive\":" << (trashClusterTerminalBlocker.Alive ? "true" : "false")
                        << ",\"attackable\":" << (trashClusterTerminalBlocker.Attackable ? "true" : "false")
                        << ",\"evade\":" << (trashClusterTerminalBlocker.Evade ? "true" : "false")
                        << ",\"path\":" << (trashClusterTerminalBlocker.Path ? "true" : "false")
                        << ",\"member\":" << (trashClusterTerminalBlocker.Member ? "true" : "false")
                        << ",\"returning_home\":" << (trashClusterTerminalBlocker.ReturningHome ? "true" : "false")
                        << ",\"formation_member\":" << (trashClusterTerminalBlocker.FormationMember ? "true" : "false")
                        << ",\"formation_leader\":" << (trashClusterTerminalBlocker.FormationLeader ? "true" : "false")
                        << ",\"formation_formed\":" << (trashClusterTerminalBlocker.FormationFormed ? "true" : "false") << "}";
                else
                    raw << "null";
                raw << "}";
                std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_pack_hold", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_recovery", nullptr, holdReason, raw.str().c_str(), semantic.c_str(), float(Party().ValidationRoutePackMemberGuids.size()), uint32(Party().ValidationRoutePackDeathGuids.size()));
            }
            if (!routeTarget)
                return true;
        }
    }

    if (!routeTarget)
    {
        bool bossTargetMissing = Cohort().Config.ValidationRouteKind == "boss"
            && targetSearchResult == "target_not_found";
        bool tankOwnsBossRecovery = bossTargetMissing && std::string(GetDungeonRole(bot)) == "tank";
        if (tankOwnsBossRecovery)
            ++state.ValidationRouteTargetSearchMissCount;

        if (tankOwnsBossRecovery && state.ValidationRouteTargetSearchMissCount >= 3)
        {
            std::string recoveryResult;
            bool recoveryInitiated = false;
            if (tryCanonicalValidationRouteBossRecovery(recoveryResult, recoveryInitiated))
            {
                situation = recoveryInitiated ? "validation_route_recovery" : "validation_route_blocked";
                action = recoveryInitiated ? "recover_canonical_validation_route_boss" : "blocked_no_fallback";
                return true;
            }
        }

        if (tankOwnsBossRecovery
            && Party().ValidationRouteActivationApplied
            && !Party().ValidationRouteCanonicalBossRecoveryAttempts
            && state.ValidationRouteTargetSearchMissCount >= 3)
        {
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_activation_no_visible_target", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_recovery", nullptr, "boss_route_activation_no_visible_target", raw.c_str(), semantic.c_str(), 0.0f, Cohort().Config.ValidationRouteTargetEntry);
            MarkBotBlocked(state, bot, "boss_route_activation_no_visible_target");
            situation = "validation_route_blocked";
            action = "blocked_no_fallback";
            return true;
        }

        if (tankOwnsBossRecovery
            && Party().ValidationRouteCanonicalBossRecoveryAttempts >= 2
            && state.ValidationRouteTargetSearchMissCount >= 6)
        {
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_canonical_boss_recovery_no_visible_target", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_recovery", nullptr, "canonical_boss_recovery_no_visible_target", raw.c_str(), semantic.c_str(), 0.0f, Cohort().Config.ValidationRouteTargetEntry);
            MarkBotBlocked(state, bot, "canonical_boss_recovery_no_visible_target");
            situation = "validation_route_blocked";
            action = "blocked_no_fallback";
            return true;
        }

        if (Cohort().Config.ValidationRouteKind == "boss"
            && std::string(GetDungeonRole(bot)) != "tank"
            && !Party().ValidationRouteFocusGuid.IsEmpty()
            && recoverAuthoritativeFocus("target_search_authoritative_focus_recovery"))
        {
            situation = "validation_route_recovery";
            action = "validation_route_recovery";
            return true;
        }

        if (tryValidationRouteActivation(nullptr, targetSearchResult.c_str()))
        {
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_activation", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_target_search", nullptr, "activation_applied_no_visible_target", raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry);
            action = "validation_route_activate_target";
            return true;
        }

        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_target_search", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_target_search", nullptr, targetSearchResult.c_str(), raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry);
        action = "search_validation_route_target";
        return true;
    }

    if (Cohort().Config.ValidationRouteKind == "boss"
        && !isValidationRouteObjectiveTarget(routeTarget->ToCreature()))
    {
        bot->InterruptNonMeleeSpells(false);
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Safety,
            BotActionArbitration::Priority::Terminal,
            "route_target_not_declared");
        if (Pet* pet = bot->GetPet())
            pet->AttackStop();
        for (Unit* controlled : bot->m_Controlled)
            if (controlled)
                controlled->AttackStop();
        situation = bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss";
        action = "raid_target_not_declared_hold";
        return true;
    }

    target = routeTarget;
    state.ValidationRouteUnresolvedFocusHoldCount = 0;
    state.ValidationRouteTargetSearchMissCount = 0;
    state.TargetGuid = target->GetGUID();
    if (Cohort().Config.ValidationRouteKind != "boss")
        enrollValidationRoutePackMember(target->ToCreature(), isValidationCohortCombatLinked(target->ToCreature()));
    rememberValidationRouteFocus(target);
    if (Cohort().Config.ValidationRouteKind == "boss")
    {
        BossMechanicActionResult mechanic = TryBossMechanics(state, bot, power, stage, activity, target);
        if (mechanic.Handled)
        {
            situation = mechanic.Situation;
            action = mechanic.Action;
            target = mechanic.Target;
            return true;
        }

        bot->InterruptNonMeleeSpells(false);
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Safety,
            BotActionArbitration::Priority::Terminal,
            "route_mechanic_fail_closed");
        if (Pet* pet = bot->GetPet())
            pet->AttackStop();
        for (Unit* controlled : bot->m_Controlled)
            if (controlled)
                controlled->AttackStop();
        situation = bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss";
        action = "raid_mechanic_contract_fail_closed";
        return true;
    }
    if (tryRouteGroupHeal(bot, target))
        return true;
    if (Cohort().Config.ValidationRouteKind == "boss" && tryValidationRouteInterrupt(target, "route_target_interrupt"))
        return true;
    ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);
    uint32 spellId = profileAction.SpellId;
    float engageRange = routeEngageRange(bot, target, spellId);
    if (profileAction.MaxRange > 0.0f)
        engageRange = profileAction.MaxRange;
    float targetDistance = bot->GetExactDist(target);
    if (profileAction.MinRange > 0.0f && targetDistance < profileAction.MinRange)
    {
        bool moved = moveOutOfProfileDeadZone(bot, target, profileAction);
        action = moved ? "move_to_profile_min_range" : "hold_tactical_path_rejected";
        return true;
    }
    if (targetDistance > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(target))
    {
        bool moved = MoveBotToProfileRange(state, bot, target, &profileAction);
        action = moved ? "move_to_validation_route_target" : "hold_tactical_path_rejected";
        std::string raw = BuildRawJson(bot, target);
        std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
        RecordEvent(state, bot, "validation_route_target_search", target, moved ? "approach_target" : "tactical_path_rejected", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry);
        if (!moved && Cohort().Config.ValidationRouteKind != "boss")
            maybeValidationPrerequisiteNoProgressAssist(target, "route_target_path_no_progress");
        return true;
    }

    BotActionResult pull = profileAction.AutoAttackMode == "melee"
        && SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::StartOrSwitch,
            target->GetGUID(), BotMeleeAutoAttack::Owner::Route,
            BotActionArbitration::Priority::TrainedDamage,
            "validation_route_melee_engagement")
                ? BotActionResult::Ok : BotActionResult::NoAction;
    BotActionResult result = ExecuteProfileCombatAction(&state, bot, target, &profileAction);
    if (result == BotActionResult::NoAction)
        result = pull;
    action = Cohort().Config.ValidationRouteKind == "boss"
        ? (std::string(GetDungeonRole(bot)) == "tank" ? "validation_route_tank_boss" : "validation_route_boss_action")
        : "validation_route_trash_action";
    state.WasInCombat = true;
    if (Cohort().Config.ValidationRouteKind != "boss")
    {
        float healthPct = UnitHealthPct(target);
        RecordRouteProgress(state, bot, target, "route_target_combat_progress", healthPct, healthPct, 0, 20);
    }

    std::string raw = BuildRawJson(bot, target);
    std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
    RecordEvent(state, bot, Cohort().Config.ValidationRouteKind == "boss" ? "boss_action" : "trash_action", target, ToString(result), raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
    if (Cohort().Config.ValidationRouteKind == "boss")
    {
        RecordEvent(state, bot, "boss_started", target, Cohort().Config.ValidationRouteMechanicProfile.c_str(), raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
        maybeValidationPrerequisiteNoProgressAssist(target, "boss_route_no_health_progress");
    }
    else
        maybeValidationPrerequisiteNoProgressAssist(target, "route_target_no_health_progress");
    return true;
}
