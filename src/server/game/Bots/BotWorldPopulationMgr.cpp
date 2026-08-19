#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilHealerAddWavePreposition.h"
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
