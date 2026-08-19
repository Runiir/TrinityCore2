#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrValidationRouteActiveCombat.h"
#include "Bots/BotWorldPopulationMgrValidationRouteFeralTrashHandoff.h"
#include "Bots/BotWorldPopulationMgrValidationRouteSharedFocusAction.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTankFocusAssist.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTankTrashRecovery.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTrashThreatControl.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTargetEngagement.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTrashIntervention.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilAddWaveOrchestration.h"
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

    BotWorldPopulationMgrValidationRoute::TrashClusterTerminalBlockerSnapshot
        trashClusterTerminalBlocker;
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

        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveOrchestrationRequest request;
        request.Manager = this;
        request.State = &state;
        request.Bot = bot;
        request.Power = &power;
        request.Stage = stage;
        request.Activity = activity;
        request.Situation = &situation;
        request.Action = &action;
        request.Target = &target;
        request.TryRouteGroupHeal.Function =
            [&tryRouteGroupHeal](Player* healer, Unit* combatTarget,
                bool allowMovement, bool allowStationaryCastTime)
            {
                return tryRouteGroupHeal(healer, combatTarget,
                    allowMovement, allowStationaryCastTime);
            };
        request.RouteEngageRange = routeEngageRange;
        request.CanonicalRouteDistance = canonicalRouteDistance;
        request.RouteArrivalRadius = routeArrivalRadius;
        return BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryAddWaveOrchestration(
            request);
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
    BotWorldPopulationMgrValidationRoute::TrashInterventionCallbacks
        trashInterventionCallbacks;
    trashInterventionCallbacks.IsProtectionProfile =
        [&cadenceProfile]()
        {
            return cadenceProfile.SpecTag == "protection";
        };
    trashInterventionCallbacks.RouteEngageRange = routeEngageRange;
    trashInterventionCallbacks.IsImmediateNextValidationRouteEncounterMember =
        isImmediateNextValidationRouteEncounterMember;
    trashInterventionCallbacks.FindTrashClusterThreatTarget =
        findTrashClusterThreatTarget;
    trashInterventionCallbacks.FindLastKnownFocusTarget =
        findLastKnownFocusTarget;
    trashInterventionCallbacks.RouteUsableCombatTarget =
        routeUsableCombatTarget;
    trashInterventionCallbacks.RememberValidationRouteFocus =
        rememberValidationRouteFocus;
    if (terminalArrivalContext.RunTrashIntervention(
            trashThreatControl, trashInterventionCallbacks))
        return true;
    BotWorldPopulationMgrValidationRoute::TankFocusAssistCallbacks
        tankFocusAssistCallbacks;
    tankFocusAssistCallbacks.GetDungeonRole =
        [this](Player* member) { return GetDungeonRole(member); };
    tankFocusAssistCallbacks.RouteUsableCombatTarget =
        routeUsableCombatTarget;
    tankFocusAssistCallbacks.RememberValidationRouteFocus =
        rememberValidationRouteFocus;
    tankFocusAssistCallbacks.RouteTankFocusGuid = routeTankFocusGuid;
    tankFocusAssistCallbacks.RouteTankFocusTarget = routeTankFocusTarget;
    tankFocusAssistCallbacks.FindLastKnownFocusTarget =
        findLastKnownFocusTarget;
    tankFocusAssistCallbacks.IsValidationRouteObjectiveTarget =
        isValidationRouteObjectiveTarget;
    tankFocusAssistCallbacks.RouteFocusMemoryActive =
        routeFocusMemoryActive;
    tankFocusAssistCallbacks.AuthoritativeRouteFocusActive =
        authoritativeRouteFocusActive;
    tankFocusAssistCallbacks.RecoverAuthoritativeFocus =
        recoverAuthoritativeFocus;
    tankFocusAssistCallbacks.TeacherAssistAuthoritativeFocus =
        teacherAssistAuthoritativeFocus;
    tankFocusAssistCallbacks.RouteEngageRange = routeEngageRange;
    tankFocusAssistCallbacks.MoveOutOfProfileDeadZone =
        moveOutOfProfileDeadZone;
    tankFocusAssistCallbacks.TryRouteGroupHeal =
        tryRouteGroupHeal;
    tankFocusAssistCallbacks.TryValidationRouteInterrupt =
        tryValidationRouteInterrupt;
    tankFocusAssistCallbacks.MaybeValidationPrerequisiteNoProgressAssist =
        maybeValidationPrerequisiteNoProgressAssist;
    if (terminalArrivalContext.RunTankFocusAssist(
            tankFocusAssistCallbacks))
        return true;
    BotWorldPopulationMgrValidationRoute::SharedFocusActionCallbacks
        sharedFocusActionCallbacks;
    sharedFocusActionCallbacks.RouteGroupFocusTarget =
        routeGroupFocusTarget;
    sharedFocusActionCallbacks.TeacherAssistAuthoritativeFocus =
        teacherAssistAuthoritativeFocus;
    sharedFocusActionCallbacks.AuthoritativeRouteFocusActive =
        authoritativeRouteFocusActive;
    sharedFocusActionCallbacks.AuthoritativeFocusFailure =
        [&authoritativeFocusFailure]() -> std::string const&
    {
        return authoritativeFocusFailure;
    };
    sharedFocusActionCallbacks.IsValidationRouteObjectiveTarget =
        isValidationRouteObjectiveTarget;
    sharedFocusActionCallbacks.GetDungeonRole =
        [this](Player* member) { return GetDungeonRole(member); };
    sharedFocusActionCallbacks.RouteEngageRange = routeEngageRange;
    sharedFocusActionCallbacks.MoveOutOfProfileDeadZone =
        moveOutOfProfileDeadZone;
    sharedFocusActionCallbacks.TryRouteGroupHeal = tryRouteGroupHeal;
    sharedFocusActionCallbacks.MaybeValidationPrerequisiteNoProgressAssist =
        maybeValidationPrerequisiteNoProgressAssist;
    if (terminalArrivalContext.RunSharedFocusAction(
            sharedFocusActionCallbacks))
        return true;
    BotWorldPopulationMgrValidationRoute::ActiveCombatCallbacks
        activeCombatCallbacks;
    activeCombatCallbacks.GetDungeonRole =
        [this](Player* member) { return GetDungeonRole(member); };
    activeCombatCallbacks.FindDungeonAnchor =
        [this](Player* member) { return FindDungeonAnchor(member); };
    activeCombatCallbacks.RouteEngageRange = routeEngageRange;
    activeCombatCallbacks.IsValidationCohortCombatLinked =
        isValidationCohortCombatLinked;
    activeCombatCallbacks.EnrollValidationRoutePackMember =
        enrollValidationRoutePackMember;
    activeCombatCallbacks.IsValidationRouteObjectiveTarget =
        isValidationRouteObjectiveTarget;
    activeCombatCallbacks.IsEligibleTrashClusterMob =
        isEligibleTrashClusterMob;
    activeCombatCallbacks.RememberValidationRouteFocus =
        rememberValidationRouteFocus;
    activeCombatCallbacks.HasValidationRouteActivation =
        [hasValidationRouteActivation]() { return hasValidationRouteActivation; };
    activeCombatCallbacks.ValidationRouteHasLivingTank =
        validationRouteHasLivingTank;
    activeCombatCallbacks.RouteFocusTankOwned = routeFocusTankOwned;
    activeCombatCallbacks.MoveOutOfProfileDeadZone =
        moveOutOfProfileDeadZone;
    activeCombatCallbacks.TryRouteGroupHeal = tryRouteGroupHeal;
    activeCombatCallbacks.TryValidationRouteInterrupt =
        tryValidationRouteInterrupt;
    activeCombatCallbacks.MaybeValidationPrerequisiteNoProgressAssist =
        maybeValidationPrerequisiteNoProgressAssist;
    if (terminalArrivalContext.RunActiveCombat(activeCombatCallbacks))
        return true;
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
    BotWorldPopulationMgrValidationRoute::TargetEngagementCallbacks
        targetEngagementCallbacks;
    targetEngagementCallbacks.DiscoveryLeg =
        [discoveryLeg]() { return discoveryLeg; };
    targetEngagementCallbacks.RouteEngageRange = routeEngageRange;
    targetEngagementCallbacks.CurrentValidationRouteTargetSpawnId =
        currentValidationRouteTargetSpawnId;
    targetEngagementCallbacks.IsEligibleTrashClusterMob =
        isEligibleTrashClusterMob;
    targetEngagementCallbacks.EnrollValidationRoutePackMember =
        enrollValidationRoutePackMember;
    targetEngagementCallbacks.IsValidationCohortCombatLinked =
        isValidationCohortCombatLinked;
    targetEngagementCallbacks.IsCurrentDiscoveryScriptedEventTarget =
        isCurrentDiscoveryScriptedEventTarget;
    targetEngagementCallbacks.FindTrashClusterThreatTarget =
        findTrashClusterThreatTarget;
    targetEngagementCallbacks.FindNearestTrashClusterMob =
        findNearestTrashClusterMob;
    targetEngagementCallbacks.MoveToRouteAnchor = moveToRouteAnchor;
    targetEngagementCallbacks.IsValidationRouteScriptTarget =
        isValidationRouteScriptTarget;
    targetEngagementCallbacks.IsValidationRouteCombatTarget =
        isValidationRouteCombatTarget;
    targetEngagementCallbacks.MakeExistingValidationRouteCombatReady =
        makeExistingValidationRouteCombatReady;
    targetEngagementCallbacks.IsValidationRouteObjectiveTarget =
        isValidationRouteObjectiveTarget;
    targetEngagementCallbacks.TryCanonicalValidationRouteBossRecovery =
        tryCanonicalValidationRouteBossRecovery;
    targetEngagementCallbacks.ClearValidationRouteKilledFocus =
        clearValidationRouteKilledFocus;
    targetEngagementCallbacks.RecordValidationRouteTrashKill =
        recordValidationRouteTrashKill;
    targetEngagementCallbacks.TryValidationRouteActivation =
        tryValidationRouteActivation;
    targetEngagementCallbacks.RouteGroupFocusTarget =
        routeGroupFocusTarget;
    targetEngagementCallbacks.MoveOutOfProfileDeadZone =
        moveOutOfProfileDeadZone;
    targetEngagementCallbacks.TryRouteGroupHeal = tryRouteGroupHeal;
    targetEngagementCallbacks.TryValidationRouteInterrupt =
        tryValidationRouteInterrupt;
    targetEngagementCallbacks.MaybeValidationPrerequisiteNoProgressAssist =
        maybeValidationPrerequisiteNoProgressAssist;
    targetEngagementCallbacks.RecoverAuthoritativeFocus =
        recoverAuthoritativeFocus;
    targetEngagementCallbacks.RememberValidationRouteFocus =
        rememberValidationRouteFocus;
    targetEngagementCallbacks.TrashClusterHasLiveMobs =
        trashClusterHasLiveMobs;
    targetEngagementCallbacks.TrashClusterTerminalBlockerResult =
        [&trashClusterTerminalBlocker]()
            -> BotWorldPopulationMgrValidationRoute::TrashClusterTerminalBlockerSnapshot const&
        {
            return trashClusterTerminalBlocker;
        };
    targetEngagementCallbacks.ValidationPartyHasActiveCombat =
        validationPartyHasActiveCombat;
    targetEngagementCallbacks.FindBoundedTerminalPartyCombatTarget =
        findBoundedTerminalPartyCombatTarget;
    targetEngagementCallbacks.MarkTrashClusterCleared =
        markTrashClusterCleared;
    return terminalArrivalContext.RunTargetEngagement(
        targetEngagementCallbacks);
}
