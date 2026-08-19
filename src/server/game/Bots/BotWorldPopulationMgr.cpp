#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrValidationRouteFeralTrashHandoff.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTankTrashRecovery.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTrashThreatControl.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilAddWaveDiscovery.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilAddWaveDensity.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilAddWaveOpeningActions.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilAddWaveTankPreparation.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilFeralHandoffState.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilFeralLocalRetention.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilFeralRemoteActions.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilFeralActiveSwarmMovement.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilHunterThreatTransfer.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilHighDensityPositioning.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilDensityCombatResolution.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilPassiveSwarmStaging.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilTankThreatRecovery.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilSwarmThreatSafety.h"
#include "Bots/BotWorldPopulationMgrScopeGuard.h"
#include "Bots/BotCalibrationFixtureContractGenerated.h"
#include "Bots/BotActionExecutor.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotAdaptiveDrudgeStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAdaptiveAtramedesStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotAdaptiveChimaeronStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotAdaptiveMaloriakStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotAdaptiveOmnotronStrategy.h"
#include "Bots/Content/Raids/Shared/Trash/BotAdaptiveRaidTrashStrategy.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotDatasetEvent.h"
#include "Bots/BotEncounterMechanicCatalog.h"
#include "Bots/BotMgr.h"
#include "Bots/BotProgressionGoalPolicy.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotRaidHazardState.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"
#include "Bots/BotWorldPopulationMgrValidationHazards.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrPolicyHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeThreatSeedState.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeNativeRushState.h"
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
        bool swarmDefenseActive = addWaveDensity.SwarmDefenseActive;
        std::string const& role = addWaveDensity.Role;
        BotClassSpecActionProfile const& profile = addWaveDensity.Profile;
        uint32 reservedAreaSpellId = addWaveDensity.ReservedAreaSpellId;
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

        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::SwarmThreatSafetyRequest swarmThreatSafetyRequest;
        swarmThreatSafetyRequest.Manager = this;
        swarmThreatSafetyRequest.State = &state;
        swarmThreatSafetyRequest.Bot = bot;
        swarmThreatSafetyRequest.Power = &power;
        swarmThreatSafetyRequest.Stage = stage;
        swarmThreatSafetyRequest.Activity = activity;
        swarmThreatSafetyRequest.Discovery = &addWaveDiscovery;
        swarmThreatSafetyRequest.Density = &addWaveDensity;
        swarmThreatSafetyRequest.HunterThreatTransfer = &hunterThreatTransfer;
        swarmThreatSafetyRequest.Add = add;
        swarmThreatSafetyRequest.Situation = &situation;
        swarmThreatSafetyRequest.Action = &action;
        swarmThreatSafetyRequest.Target = &target;
        if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TrySwarmThreatSafety(
                swarmThreatSafetyRequest))
            return true;

        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::HighDensityPositioningRequest highDensityPositioningRequest;
        highDensityPositioningRequest.Manager = this;
        highDensityPositioningRequest.State = &state;
        highDensityPositioningRequest.Bot = bot;
        highDensityPositioningRequest.Power = &power;
        highDensityPositioningRequest.Stage = stage;
        highDensityPositioningRequest.Activity = activity;
        highDensityPositioningRequest.Discovery = &addWaveDiscovery;
        highDensityPositioningRequest.Density = &addWaveDensity;
        highDensityPositioningRequest.Add = add;
        highDensityPositioningRequest.Situation = &situation;
        highDensityPositioningRequest.Action = &action;
        highDensityPositioningRequest.Target = &target;
        bool highDensityPositioningReturnFalse = false;
        highDensityPositioningRequest.ReturnFalse =
            &highDensityPositioningReturnFalse;
        highDensityPositioningRequest.TryRouteGroupHeal.Function =
            [&tryRouteGroupHeal](Player* healer, Unit* combatTarget,
                bool allowMovement, bool allowStationaryCastTime)
            {
                return tryRouteGroupHeal(healer, combatTarget,
                    allowMovement, allowStationaryCastTime);
            };
        if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryHighDensityPositioning(
                highDensityPositioningRequest))
            return true;
        if (highDensityPositioningReturnFalse)
            return false;

        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::DensityCombatResolutionRequest densityCombatResolutionRequest;
        densityCombatResolutionRequest.Manager = this;
        densityCombatResolutionRequest.State = &state;
        densityCombatResolutionRequest.Bot = bot;
        densityCombatResolutionRequest.Power = &power;
        densityCombatResolutionRequest.Stage = stage;
        densityCombatResolutionRequest.Activity = activity;
        densityCombatResolutionRequest.Discovery = &addWaveDiscovery;
        densityCombatResolutionRequest.Density = &addWaveDensity;
        densityCombatResolutionRequest.Add = add;
        densityCombatResolutionRequest.SharedFocusValid = sharedFocusValid;
        densityCombatResolutionRequest.HunterMisdirectionActive = hunterMisdirectionActive;
        densityCombatResolutionRequest.ContinueStableTankSwarmApproach =
            continueStableTankSwarmApproach;
        densityCombatResolutionRequest.RouteEngageRange = routeEngageRange;
        densityCombatResolutionRequest.Situation = &situation;
        densityCombatResolutionRequest.Action = &action;
        densityCombatResolutionRequest.Target = &target;
        return BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryDensityCombatResolution(
            densityCombatResolutionRequest);
    };
    ValidationRouteGroupRecoveryCallbacks groupRecoveryCallbacks;
    groupRecoveryCallbacks.RetireStalePackMembers = retireStaleValidationRoutePackMembers;
    groupRecoveryCallbacks.EnrollEngagedPackMembers = enrollEngagedValidationRoutePackMembers;
    groupRecoveryCallbacks.PersistedPackHasLiveMembers = persistedValidationRoutePackHasLiveMembers;
    groupRecoveryCallbacks.MarkTrashFailed = markValidationRouteTrashFailed;
    groupRecoveryCallbacks.IsPackEntry = isValidationRoutePackEntry;
    groupRecoveryCallbacks.ResolvedTransitionAura = resolvedScriptedTransitionAuraId;
    if (TryValidationRouteGroupRecovery(state, bot, power, stage, activity,
            situation, action, target, discoveryLeg, groupRecoveryCallbacks))
        return true;
    BotWorldPopulationMgrValidationRoute::ObjectiveCallbacks terminalArrivalCallbacks;
    terminalArrivalCallbacks.PersistedPackHasLiveMembers =
        persistedValidationRoutePackHasLiveMembers;
    terminalArrivalCallbacks.ActivePackTarget =
        activeValidationRoutePackTarget;
    terminalArrivalCallbacks.IsEligibleTrash =
        isEligibleTrashClusterMob;
    terminalArrivalCallbacks.PartyHasActiveCombat =
        validationPartyHasActiveCombat;
    terminalArrivalCallbacks.IsOriginalInstanceMember =
        [this](WorldBotState const& cohortState, Player const* cohortBot)
        {
            return IsValidationCohortMemberInOriginalInstance(cohortState,
                cohortBot);
        };
    terminalArrivalCallbacks.EnrollEngagedPackMembers =
        enrollEngagedValidationRoutePackMembers;
    terminalArrivalCallbacks.MoveToRouteAnchor = moveToRouteAnchor;
    BotWorldPopulationMgrValidationRoute::ObjectiveContext terminalArrivalContext(
        *this, state, bot, power, stage, activity, situation, action, target,
        arrivalRoute, routeArrivalRadius, canonicalRouteDistance,
        routeAnchorX, routeAnchorY, routeAnchorZ, routeAnchorReason,
        routeDistance, std::move(terminalArrivalCallbacks));
    if (terminalArrivalContext.Run())
        return true;
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

    BotWorldPopulationMgrValidationRoute::TrashThreatControl trashThreatControl;
    BotWorldPopulationMgrValidationRoute::TrashThreatControlCallbacks
        trashThreatControlCallbacks;
    trashThreatControlCallbacks.IsImmediateNextValidationRouteEncounterMember =
        isImmediateNextValidationRouteEncounterMember;
    trashThreatControlCallbacks.IsPendingScriptedEventEntry =
        isPendingScriptedEventEntry;
    trashThreatControlCallbacks.IsValidationRouteScriptTarget =
        isValidationRouteScriptTarget;
    trashThreatControlCallbacks.RouteEngageRange = routeEngageRange;
    trashThreatControlCallbacks.MoveOutOfProfileDeadZone =
        moveOutOfProfileDeadZone;
    trashThreatControlCallbacks.TryValidationRouteAdds =
        tryValidationRouteAdds;
    if (terminalArrivalContext.RunTrashThreatControl(trashThreatControl,
            trashThreatControlCallbacks))
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
            && trashThreatControl.TankOwnsTrashMajority;
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
            && trashThreatControl.TankOwnsTrashMajority
            && trashThreatControl.InsecureTrashSwarm
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
        BotWorldPopulationMgrValidationRoute::FeralTrashHandoffCallbacks
            feralTrashHandoffCallbacks;
        feralTrashHandoffCallbacks.DefenseTarget =
            [&defenseTarget]() { return defenseTarget; };
        feralTrashHandoffCallbacks.DefenseAttackerCount =
            [&defenseAttackerCount]() { return defenseAttackerCount; };
        feralTrashHandoffCallbacks.TrashThreatControlResult =
            [&trashThreatControl]()
                -> BotWorldPopulationMgrValidationRoute::TrashThreatControlResult const&
            {
                return trashThreatControl;
            };
        if (terminalArrivalContext.RunFeralTrashHandoff(
                feralTrashHandoffCallbacks))
            return true;
        BotWorldPopulationMgrValidationRoute::TankTrashRecoveryCallbacks
            tankTrashRecoveryCallbacks;
        tankTrashRecoveryCallbacks.DefenseTarget =
            [&defenseTarget]() { return defenseTarget; };
        tankTrashRecoveryCallbacks.DefenseAttackerCount =
            [&defenseAttackerCount]() { return defenseAttackerCount; };
        tankTrashRecoveryCallbacks.TrashThreatControlResult =
            [&trashThreatControl]()
                -> BotWorldPopulationMgrValidationRoute::TrashThreatControl&
            {
                return trashThreatControl;
            };
        tankTrashRecoveryCallbacks.IsProtectionProfile =
            [&cadenceProfile]()
            {
                return cadenceProfile.SpecTag == "protection";
            };
        tankTrashRecoveryCallbacks.RouteEngageRange = routeEngageRange;
        tankTrashRecoveryCallbacks.IsImmediateNextValidationRouteEncounterMember =
            isImmediateNextValidationRouteEncounterMember;
        tankTrashRecoveryCallbacks.FindTrashClusterThreatTarget =
            findTrashClusterThreatTarget;
        tankTrashRecoveryCallbacks.FindLastKnownFocusTarget =
            findLastKnownFocusTarget;
        tankTrashRecoveryCallbacks.RouteUsableCombatTarget =
            routeUsableCombatTarget;
        tankTrashRecoveryCallbacks.RememberValidationRouteFocus =
            rememberValidationRouteFocus;
        if (terminalArrivalContext.RunTankTrashRecovery(
                tankTrashRecoveryCallbacks))
            return true;
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
