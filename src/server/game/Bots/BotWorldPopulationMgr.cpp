#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilAddWaveDiscovery.h"
#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilAddWaveDensity.h"
#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilAddWaveOpeningActions.h"
#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilAddWaveTankPreparation.h"
#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilFeralHandoffState.h"
#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilFeralLocalRetention.h"
#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilFeralRemoteActions.h"
#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilFeralActiveSwarmMovement.h"
#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilHunterThreatTransfer.h"
#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilPassiveSwarmStaging.h"
#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilTankThreatRecovery.h"
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
    static constexpr float PassiveTankDensityClusterRadius = 10.0f;
    bool arrivalRoute = false;
    if (!TryValidationRouteObjectiveGate(state, bot, power, stage,
            activity, situation, action, target, arrivalRoute))
        return false;
    uint64 const raidAuthorityOwner = bot->GetGUID().GetRawValue();
    BotClassSpecActionProfile cadenceProfile =
        BotClassSpecActionProfileStore::Build(bot, GetDungeonRole(bot));
    bool discoveryLeg = Cohort().Config.ValidationRouteNodeKind == "discovery_leg";

    ValidationRouteTargetingContext targeting =
        BuildValidationRouteTargetingContext(state, bot, power, stage,
            activity, discoveryLeg);
    auto const& routeEngageRange = targeting.RouteEngageRange;
    auto const& currentValidationRouteTargetSpawnId = targeting.CurrentTargetSpawnId;
    auto const& isFutureCanonicalValidationRouteSource = targeting.IsFutureCanonicalSource;
    auto const& wouldPullProtectedFutureValidationRouteSource =
        targeting.WouldPullProtectedFutureSource;
    auto const& isValidationRouteEntry = targeting.IsRouteEntry;
    auto const& isValidationRouteAlternateTargetEntry =
        targeting.IsRouteAlternateEntry;
    auto const& isValidationRouteCombatEntry = targeting.IsRouteCombatEntry;
    auto const& isValidationRoutePackEntry = targeting.IsRoutePackEntry;
    auto const& isValidationRouteScriptTarget = targeting.IsScriptTarget;
    auto const& isValidationRouteCombatTarget = targeting.IsCombatTarget;
    auto const& hasStrictPathToValidationRouteTarget = targeting.HasStrictPath;
    auto const& resolvedScriptedTransitionAuraId = targeting.ResolvedTransitionAura;
    auto const& isPendingScriptedEventEntry = targeting.IsPendingScripted;
    auto const& isCurrentDiscoveryScriptedEventTarget =
        targeting.IsCurrentDiscoveryScripted;
    auto const& isEligibleTrashClusterMob = targeting.IsEligibleTrash;
    auto const& forEachActiveValidationCohortCombatCreature =
        targeting.ForEachActiveCombat;
    auto const& isValidationCohortCombatLinked = targeting.IsCombatLinked;
    auto const& isImmediateNextValidationRouteBossTarget =
        targeting.IsImmediateNextBoss;
    auto const& isImmediateNextValidationRouteEncounterMember =
        targeting.IsImmediateNextEncounter;
    auto validationPartyHasActiveCombat =
        [&targeting](bool transferImmediateNextEncounter = false) -> bool
    {
        return targeting.PartyHasActiveCombat(transferImmediateNextEncounter);
    };
    auto const& isBoundedTerminalPartyCombatTarget =
        targeting.IsBoundedTerminalCombat;
    auto const& findBoundedTerminalPartyCombatTarget =
        targeting.FindBoundedTerminalCombat;
    auto const& tryCanonicalValidationRouteBossRecovery =
        targeting.TryCanonicalBossRecovery;
    auto const& isNaturalForwardHostile = targeting.IsNaturalForwardHostile;
    auto const& findForwardDiscoveryTarget = targeting.FindForwardDiscovery;
    auto const& isValidationRouteObjectiveTarget = targeting.IsObjectiveTarget;
    auto const& findCurrentDiscoveryScriptedEventTarget =
        targeting.FindCurrentDiscoveryScripted;
    auto moveOutOfProfileDeadZone = [this, &state](Player* rangeBot,
        Unit* rangeTarget, ResolvedCombatAction const& rangeAction) -> bool
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
    auto tryRouteGroupHeal = [this, &state, &bot, &power, &stage, &activity,
        &situation, &action](Player* healer, Unit* combatTarget,
        bool allowMovement = true, bool allowStationaryCastTime = false) -> bool
    {
        return TryValidationRouteGroupHeal(state, bot, healer, combatTarget,
            power, stage, activity, situation, action, allowMovement,
            allowStationaryCastTime);
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


    ValidationRoutePackContext pack = BuildValidationRoutePackContext(
        state, bot, power, stage, activity, discoveryLeg, targeting);
    auto const& isNaturalValidationRoutePackMember = pack.IsNaturalMember;
    auto const& enrollValidationRoutePackMember = pack.EnrollMember;
    auto const& recordValidationRouteScriptedTransition =
        pack.RecordScriptedTransition;
    auto const& retireStaleValidationRoutePackMembers =
        pack.RetireStaleMembers;
    auto const& enrollEngagedValidationRoutePackMembers =
        pack.EnrollEngagedMembers;
    auto const& persistedValidationRoutePackHasLiveMembers =
        pack.HasLiveMembers;
    auto const& activeValidationRoutePackTarget = pack.ActiveTarget;
    auto const& findNearestTrashClusterMob = pack.FindNearestTrash;
    auto const& findTrashClusterThreatTarget = pack.FindTrashThreat;

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

    auto maybeValidationPrerequisiteNoProgressAssist = [this, &state, bot, &power, stage, activity, &isValidationRouteScriptTarget, &isValidationRoutePackEntry, &recordValidationRouteTrashKill](Unit* prerequisiteTarget, char const* context) -> bool
    {
        return MaybeValidationPrerequisiteNoProgressAssist(state, bot, power,
            stage, activity, isValidationRouteScriptTarget,
            isValidationRoutePackEntry, recordValidationRouteTrashKill,
            prerequisiteTarget, context);
    };

    std::string authoritativeFocusFailure = "authoritative_focus_not_checked";
    ValidationRouteFocusContext focus = BuildValidationRouteFocusContext(
        state, bot, power, stage, activity, discoveryLeg, targeting, pack,
        authoritativeFocusFailure);
    auto const& routeUsableCombatTarget = focus.UsableCombatTarget;
    auto const& routeFocusMemoryFresh = focus.FocusMemoryFresh;
    auto const& routeUsableValidationFocus = focus.UsableValidationFocus;
    auto const& routeGroupFocusTarget = focus.GroupFocusTarget;
    auto const& routeTankFocusGuid = focus.TankFocusGuid;
    auto const& rememberValidationRouteFocus = focus.RememberFocus;
    auto const& makeExistingValidationRouteCombatReady =
        focus.MakeExistingCombatReady;
    auto const& tryValidationRouteActivation = focus.TryActivation;
    auto const& routeTankFocusTarget = focus.TankFocusTarget;
    auto const& routeFocusMemoryActive = focus.FocusMemoryFresh;
    auto const& authoritativeRouteFocusActive = focus.AuthoritativeFocusActive;
    auto const& findLastKnownFocusTarget = focus.LastKnownFocusTarget;
    auto const& findAuthoritativeRouteFocusTarget =
        focus.AuthoritativeFocusTarget;
    auto const& recoverAuthoritativeFocus = focus.RecoverAuthoritativeFocus;
    auto const& teacherAssistAuthoritativeFocus = focus.TeacherAssistFocus;

    ValidationRouteAnchorContext routeAnchor = ResolveValidationRouteAnchor(
        state, bot, power, stage, activity, target,
        routeUsableCombatTarget, routeTankFocusGuid,
        persistedValidationRoutePackHasLiveMembers);
    uint32 routeAnchorMapId = routeAnchor.MapId;
    float routeAnchorX = routeAnchor.X;
    float routeAnchorY = routeAnchor.Y;
    float routeAnchorZ = routeAnchor.Z;
    std::string routeAnchorReason = routeAnchor.Reason;
    float routeDistance = routeAnchor.Distance;
    float canonicalRouteDistance = routeAnchor.CanonicalDistance;
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
    ValidationRouteMovementCheckCallbacks movementCheckCallbacks{
        isValidationCohortCombatLinked, tryRouteGroupHeal};

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

        // High Priestess Azil's healer-side add-wave handoff is kept in its
        // encounter-owned module. The generic add resolver follows this
        // early branch in the original decision order.
        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::HealerAddWavePrepositionRequest healerAddWaveRequest;
        healerAddWaveRequest.Manager = this;
        healerAddWaveRequest.State = &state;
        healerAddWaveRequest.Bot = bot;
        healerAddWaveRequest.Power = &power;
        healerAddWaveRequest.Stage = stage;
        healerAddWaveRequest.Activity = activity;
        healerAddWaveRequest.Situation = &situation;
        healerAddWaveRequest.Action = &action;
        healerAddWaveRequest.Target = &target;
        healerAddWaveRequest.TryRouteGroupHeal.Function =
            [&tryRouteGroupHeal](Player* healer, Unit* combatTarget,
                bool allowMovement, bool allowStationaryCastTime)
            {
                return tryRouteGroupHeal(healer, combatTarget,
                    allowMovement, allowStationaryCastTime);
            };
        if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryHealerAddWavePreposition(
                healerAddWaveRequest))
            return true;

        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveDiscoveryRequest addWaveDiscoveryRequest;
        addWaveDiscoveryRequest.Manager = this;
        addWaveDiscoveryRequest.State = &state;
        addWaveDiscoveryRequest.Bot = bot;
        addWaveDiscoveryRequest.Power = &power;
        addWaveDiscoveryRequest.Stage = stage;
        addWaveDiscoveryRequest.Activity = activity;
        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveDiscoveryResult addWaveDiscovery =
            BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::DiscoverAddWave(
                addWaveDiscoveryRequest);
        Unit* add = nullptr;
        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveDensityRequest addWaveDensityRequest;
        addWaveDensityRequest.Manager = this;
        addWaveDensityRequest.State = &state;
        addWaveDensityRequest.Bot = bot;
        addWaveDensityRequest.Power = &power;
        addWaveDensityRequest.Stage = stage;
        addWaveDensityRequest.Activity = activity;
        addWaveDensityRequest.Discovery = &addWaveDiscovery;
        addWaveDensityRequest.CanonicalRouteDistance = canonicalRouteDistance;
        addWaveDensityRequest.RouteArrivalRadius = routeArrivalRadius;
        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveDensityResult addWaveDensity =
            BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::ResolveAddWaveDensity(
                addWaveDensityRequest);
        if (addWaveDensity.BypassPreArrival)
            return false;

        add = addWaveDensity.Add;
        bool sharedFocusValid = addWaveDensity.SharedFocusValid;
        uint32 addCount = addWaveDiscovery.AddCount;
        uint32 engagedAddCount = addWaveDiscovery.EngagedAddCount;
        uint32 nearbyAddCount = addWaveDiscovery.NearbyAddCount;
        float addX = addWaveDiscovery.AddX;
        float addY = addWaveDiscovery.AddY;
        std::vector<Creature*>& localAdds = addWaveDiscovery.LocalAdds;
        bool cohortSwarmActive = addWaveDiscovery.CohortSwarmActive;
        std::function<bool(Player*, Unit*)> isUsableListedAdd =
            addWaveDiscovery.IsUsableListedAdd;
        bool sharedLargePassiveSwarmStaging =
            addWaveDensity.SharedLargePassiveSwarmStaging;
        bool highDensityPhase = addWaveDensity.HighDensityPhase;
        bool swarmDefenseActive = addWaveDensity.SwarmDefenseActive;
        std::string const& role = addWaveDensity.Role;
        BotClassSpecActionProfile const& profile = addWaveDensity.Profile;
        uint32 reservedAreaSpellId = addWaveDensity.ReservedAreaSpellId;
        Creature* densityApproachAnchor = addWaveDensity.DensityApproachAnchor;
        Player* densityTank = addWaveDensity.DensityTank;
        Player* densityHealer = addWaveDensity.DensityHealer;
        Player* densityDefenseTarget = addWaveDensity.DensityDefenseTarget;
        uint32 densityTankOwnedAddCount = addWaveDensity.DensityTankOwnedAddCount;
        uint32 densityTankSecureAddCount = addWaveDensity.DensityTankSecureAddCount;
        bool densityTankOwnsSecureMajority =
            addWaveDensity.DensityTankOwnsSecureMajority;
        bool densityTankOwnsVictimMajority =
            addWaveDensity.DensityTankOwnsVictimMajority;
        bool urgentSwarmDamageRelease =
            addWaveDensity.UrgentSwarmDamageRelease;
        bool dpsSwarmDamageRelease = addWaveDensity.DpsSwarmDamageRelease;
        bool botInsideTankPickup = addWaveDensity.BotInsideTankPickup;
        std::function<size_t(Player const*)> observedListedAttackerCount =
            addWaveDensity.ObservedListedAttackerCount;
        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveOpeningActionsRequest openingActionsRequest;
        openingActionsRequest.Manager = this;
        openingActionsRequest.State = &state;
        openingActionsRequest.Bot = bot;
        openingActionsRequest.Power = &power;
        openingActionsRequest.Stage = stage;
        openingActionsRequest.Activity = activity;
        openingActionsRequest.Discovery = &addWaveDiscovery;
        openingActionsRequest.Density = &addWaveDensity;
        openingActionsRequest.Situation = &situation;
        openingActionsRequest.Action = &action;
        openingActionsRequest.Target = &target;
        if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryAddWaveOpeningActions(
                openingActionsRequest))
            return true;

        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveTankPreparationRequest tankPreparationRequest;
        tankPreparationRequest.Manager = this;
        tankPreparationRequest.State = &state;
        tankPreparationRequest.Bot = bot;
        tankPreparationRequest.Power = &power;
        tankPreparationRequest.Stage = stage;
        tankPreparationRequest.Activity = activity;
        tankPreparationRequest.Discovery = &addWaveDiscovery;
        tankPreparationRequest.Density = &addWaveDensity;
        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveTankPreparationResult tankPreparation =
            BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::PrepareAddWaveTank(
                tankPreparationRequest);
        add = tankPreparation.Add;
        sharedFocusValid = tankPreparation.SharedFocusValid;
        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::FeralHandoffStateRequest feralHandoffRequest;
        feralHandoffRequest.Manager = this;
        feralHandoffRequest.State = &state;
        feralHandoffRequest.Bot = bot;
        feralHandoffRequest.Power = &power;
        feralHandoffRequest.Stage = stage;
        feralHandoffRequest.Activity = activity;
        feralHandoffRequest.Discovery = &addWaveDiscovery;
        feralHandoffRequest.Density = &addWaveDensity;
        feralHandoffRequest.Add = &add;
        feralHandoffRequest.SharedFocusValid = &sharedFocusValid;
        feralHandoffRequest.Situation = &situation;
        feralHandoffRequest.Action = &action;
        feralHandoffRequest.Target = &target;
        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::FeralHandoffStateResult feralHandoff =
            BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::ResolveFeralHandoffState(
                feralHandoffRequest);
        if (feralHandoff.Handled)
            return true;

        auto const& tryFeralRoarPickup = feralHandoff.TryFeralRoarPickup;
        bool feralChargePickupArrived =
            feralHandoff.FeralChargePickupArrived;


        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::FeralLocalRetentionRequest localRetentionRequest;
        localRetentionRequest.Manager = this;
        localRetentionRequest.State = &state;
        localRetentionRequest.Bot = bot;
        localRetentionRequest.Power = &power;
        localRetentionRequest.Stage = stage;
        localRetentionRequest.Activity = activity;
        localRetentionRequest.Discovery = &addWaveDiscovery;
        localRetentionRequest.Density = &addWaveDensity;
        localRetentionRequest.FeralHandoff = &feralHandoff;
        localRetentionRequest.Add = add;
        localRetentionRequest.Situation = &situation;
        localRetentionRequest.Action = &action;
        localRetentionRequest.Target = &target;
        if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryFeralLocalRetention(
                localRetentionRequest))
            return true;

        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::FeralRemoteActionsRequest remoteActionsRequest;
        remoteActionsRequest.Manager = this;
        remoteActionsRequest.State = &state;
        remoteActionsRequest.Bot = bot;
        remoteActionsRequest.Power = &power;
        remoteActionsRequest.Stage = stage;
        remoteActionsRequest.Activity = activity;
        remoteActionsRequest.Discovery = &addWaveDiscovery;
        remoteActionsRequest.Density = &addWaveDensity;
        remoteActionsRequest.FeralHandoff = &feralHandoff;
        remoteActionsRequest.Add = &add;
        remoteActionsRequest.SharedFocusValid = &sharedFocusValid;
        remoteActionsRequest.Situation = &situation;
        remoteActionsRequest.Action = &action;
        remoteActionsRequest.Target = &target;
        if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryFeralRemoteActions(
                remoteActionsRequest))
            return true;

        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::FeralActiveSwarmMovementRequest activeSwarmMovementRequest;
        activeSwarmMovementRequest.Manager = this;
        activeSwarmMovementRequest.State = &state;
        activeSwarmMovementRequest.Bot = bot;
        activeSwarmMovementRequest.Power = &power;
        activeSwarmMovementRequest.Stage = stage;
        activeSwarmMovementRequest.Activity = activity;
        activeSwarmMovementRequest.Discovery = &addWaveDiscovery;
        activeSwarmMovementRequest.Density = &addWaveDensity;
        activeSwarmMovementRequest.FeralHandoff = &feralHandoff;
        activeSwarmMovementRequest.Add = add;
        activeSwarmMovementRequest.Situation = &situation;
        activeSwarmMovementRequest.Action = &action;
        activeSwarmMovementRequest.Target = &target;
        if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryFeralActiveSwarmMovement(
                activeSwarmMovementRequest))
            return true;

        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::HunterThreatTransferRequest hunterThreatTransferRequest;
        hunterThreatTransferRequest.Manager = this;
        hunterThreatTransferRequest.State = &state;
        hunterThreatTransferRequest.Bot = bot;
        hunterThreatTransferRequest.Power = &power;
        hunterThreatTransferRequest.Stage = stage;
        hunterThreatTransferRequest.Activity = activity;
        hunterThreatTransferRequest.Discovery = &addWaveDiscovery;
        hunterThreatTransferRequest.Density = &addWaveDensity;
        hunterThreatTransferRequest.Add = &add;
        hunterThreatTransferRequest.SharedFocusValid = &sharedFocusValid;
        hunterThreatTransferRequest.Situation = &situation;
        hunterThreatTransferRequest.Action = &action;
        hunterThreatTransferRequest.Target = &target;
        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::HunterThreatTransferResult hunterThreatTransfer =
            BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryHunterThreatTransfer(
                hunterThreatTransferRequest);
        bool hunterMisdirectionActive =
            hunterThreatTransfer.HunterMisdirectionActive;
        if (hunterThreatTransfer.Handled)
            return true;

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

        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::PassiveSwarmStagingRequest passiveSwarmStagingRequest;
        passiveSwarmStagingRequest.Manager = this;
        passiveSwarmStagingRequest.State = &state;
        passiveSwarmStagingRequest.Bot = bot;
        passiveSwarmStagingRequest.Power = &power;
        passiveSwarmStagingRequest.Stage = stage;
        passiveSwarmStagingRequest.Activity = activity;
        passiveSwarmStagingRequest.Discovery = &addWaveDiscovery;
        passiveSwarmStagingRequest.Density = &addWaveDensity;
        passiveSwarmStagingRequest.Add = add;
        passiveSwarmStagingRequest.Situation = &situation;
        passiveSwarmStagingRequest.Action = &action;
        passiveSwarmStagingRequest.Target = &target;
        if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryPassiveSwarmStaging(
                passiveSwarmStagingRequest))
            return true;

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
                PassiveTankDensityClusterRadius);
        };

        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TankThreatRecoveryRequest tankThreatRecoveryRequest;
        tankThreatRecoveryRequest.Manager = this;
        tankThreatRecoveryRequest.State = &state;
        tankThreatRecoveryRequest.Bot = bot;
        tankThreatRecoveryRequest.Power = &power;
        tankThreatRecoveryRequest.Stage = stage;
        tankThreatRecoveryRequest.Activity = activity;
        tankThreatRecoveryRequest.Discovery = &addWaveDiscovery;
        tankThreatRecoveryRequest.Density = &addWaveDensity;
        tankThreatRecoveryRequest.Add = add;
        tankThreatRecoveryRequest.ContinueStableTankSwarmApproach =
            continueStableTankSwarmApproach;
        tankThreatRecoveryRequest.RouteEngageRange = routeEngageRange;
        tankThreatRecoveryRequest.Situation = &situation;
        tankThreatRecoveryRequest.Action = &action;
        tankThreatRecoveryRequest.Target = &target;
        if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryTankThreatRecovery(
                tankThreatRecoveryRequest))
            return true;
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
        if (TryValidationRouteMovementCheck(state, bot, power, stage, activity,
                situation, action, target, movementCheckCallbacks))
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
    if (TryValidationRouteMovementCheck(state, bot, power, stage, activity,
            situation, action, target, movementCheckCallbacks))
        return true;
    if (tryValidationRoutePatrolPull())
        return true;
    if (TryValidationRouteDrudgeMinimumDistance(state, bot, power, stage,
            activity, situation, action, target,
            isValidationCohortCombatLinked))
        return true;
    if (TryValidationRouteDrudgeChargeLanes(state, bot, power, stage,
            activity, situation, action, target, tryRouteGroupHeal,
            isValidationCohortCombatLinked,
            [&canonicalRouteDistance]() { return canonicalRouteDistance; },
            routeArrivalRadius))
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
