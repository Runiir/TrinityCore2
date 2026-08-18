#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotMovementArbiter.h"
#include "Bots/BotRaidAreaAuthority.h"

#include "Corpse.h"
#include "Creature.h"
#include "DataStores/DBCStores.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "Log.h"
#include "Map.h"
#include "MapManager.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "WorldSession.h"

#include <chrono>
#include <cmath>
#include <sstream>
#include <string>
#include <unordered_map>

namespace
{
constexpr uint32 BlackwingDescentMapId = 669;
constexpr uint32 BlackwingDescentEntranceMapId = 0;
constexpr uint32 BlackwingDescentEntranceTriggerId = 6581;

uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

struct NativeRaidHostileActivityVisitor
{
    explicit NativeRaidHostileActivityVisitor(WorldObject const* observer) : Observer(observer) { }

    void Visit(std::unordered_map<ObjectGuid, Creature*>& creatures)
    {
        if (Active || !Observer)
            return;

        for (auto const& pair : creatures)
        {
            Creature* creature = pair.second;
            if (!creature || !creature->IsInWorld() || !creature->IsAlive()
                || !creature->IsHostileTo(Observer))
                continue;

            bool const active = creature->IsInCombat() || creature->GetVictim()
                || !creature->getAttackers().empty()
                || creature->IsInEvadeMode();
            if (!active)
                continue;

            Active = true;
            ActiveGuid = creature->GetGUID();
            ActiveEntry = creature->GetEntry();
            return;
        }
    }

    template<class T>
    void Visit(std::unordered_map<ObjectGuid, T*>&) { }

    WorldObject const* Observer = nullptr;
    bool Active = false;
    ObjectGuid ActiveGuid;
    uint32 ActiveEntry = 0;
};
}

bool BotWorldPopulationMgr::TryReattachValidationBot(WorldBotState& state, Player* bot, char const* context)
{
    bool const nativeReleasedGhostWorldport = IsNativeReleasedGhostWorldport(state, bot);
    bool const nativeValidationRunbackWorldport = IsNativeValidationRunbackWorldport(state, bot);
    bool const nativeRecoveryWorldport = nativeReleasedGhostWorldport || nativeValidationRunbackWorldport;

    if (!Cohort().Config.ValidationRouteEnable || !bot)
        return false;

    if (!state.ValidationCohortLocked
        || bot->IsInWorld()
        || !bot->GetMap()
        || (!nativeRecoveryWorldport
            && (bot->GetMapId() != state.ValidationCohortMapId
                || bot->GetInstanceId() != state.ValidationCohortInstanceId)))
        return false;

    // Once a native release/runback is pending, a different far-teleport is
    // not recoverable by cancelling it or reattaching to the frozen map.  The
    // immutable corpse contract is the only authority for this exception.
    if (state.NativeReleaseRequested && !nativeRecoveryWorldport
        && !bot->IsAlive() && bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST)
        && HasNativeRaidCorpseAuthority(state, bot))
        return false;

    if (bot->IsBeingTeleportedFar())
    {
        if (nativeRecoveryWorldport)
        {
            // ReleaseSpirit and the area-trigger entrance both use the
            // server's native far-worldport protocol.  A validation bot is
            // allowed to acknowledge only a corpse-authorized native release
            // or the exact configured-instance entrance return destination;
            // arbitrary outside teleports still fail closed below.
            if (WorldSession* session = bot->GetSession())
            {
                session->HandleMoveWorldportAck();
                bool nativeWorldportComplete = false;
                if (nativeReleasedGhostWorldport)
                {
                    AreaTriggerEntry const* entranceEntry = nullptr;
                    AreaTriggerStruct const* entranceDestination = nullptr;
                    nativeWorldportComplete = bot->IsInWorld() && !bot->IsAlive()
                        && bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST)
                        && HasNativeRaidCorpseAuthority(state, bot)
                        && ResolveNativeValidationEntrance(state.ValidationCohortMapId,
                            bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(),
                            entranceEntry, entranceDestination)
                        && bot->GetMapId() == entranceEntry->ContinentID;
                }
                else
                {
                    // HandleMoveWorldportAck performs the core's native
                    // dungeon-corpse resurrection after adding the player to
                    // the exact destination map.  Accept that postcondition,
                    // not a still-ghost state, and independently retain the
                    // frozen native group/leader identity.
                    Group const* group = bot->GetGroup();
                    nativeWorldportComplete = bot->IsInWorld() && bot->IsAlive()
                        && !bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST)
                        && !bot->HasCorpse()
                        && bot->GetMapId() == state.ValidationCohortMapId
                        && bot->GetInstanceId() == state.ValidationCohortInstanceId
                        && group && group->GetGUID() == state.ValidationCohortGroupGuid
                        && group->GetLeaderGUID() == state.ValidationCohortLeaderGuid;
                }

                if (nativeWorldportComplete)
                {
                    if (nativeReleasedGhostWorldport)
                    {
                        // Preserve the exact native graveyard landing after
                        // the release worldport completes.  The following
                        // runback edge must be proven by movement from this
                        // identity-bound landing, never by the release
                        // worldport itself.
                        state.NativeReleaseLandingObserved = true;
                        state.NativeReleaseLandingMapId = bot->GetMapId();
                        state.NativeReleaseLandingInstanceId = bot->GetInstanceId();
                        state.NativeReleaseLandingWipeGeneration = Cohort().Raid.WipeGeneration;
                        state.NativeReleaseLandingX = bot->GetPositionX();
                        state.NativeReleaseLandingY = bot->GetPositionY();
                        state.NativeReleaseLandingZ = bot->GetPositionZ();
                    }
                    else if (nativeValidationRunbackWorldport)
                    {
                        state.NativeReleaseRequested = false;
                        state.NativeRunbackAreaTriggerId = 0;
                    }
                    TC_LOG_INFO("server", "BotWorld native validation worldport complete bot=%s context=%s map=%u instance=%u release=%u runback=%u",
                        bot->GetGUID().ToString().c_str(), context ? context : "", bot->GetMapId(), bot->GetInstanceId(),
                        nativeReleasedGhostWorldport ? 1u : 0u, nativeValidationRunbackWorldport ? 1u : 0u);
                    return true;
                }
            }

            // Never cancel or reattach a native recovery worldport.  The
            // caller will mark the validation member invalid if its ACK did
            // not land in the exact corpse-authorized state.
            return false;
        }

        // An active validation bot may acknowledge only a typed native
        // release or the exact area-trigger worldport recorded by the corpse
        // run coordinator above. Map/instance coincidence is not authority,
        // and an unexpected teleport must be observed as an attempt failure
        // rather than cancelled or repaired by bot code.
        return false;
    }

    // There is no client-equivalent acknowledgement to reconcile. Runtime
    // must never repair an active bot by directly adding it back to a map.
    return false;
}

bool BotWorldPopulationMgr::IsNativeCombatResTarget(WorldBotState const& state, Player const* bot) const
{
    // Native combat resurrection is legal during the short JUST_DIED window,
    // before Trinity creates a Corpse on release.  Waiting for CORPSE here
    // makes the coordinator publish a target-ineligible decline on the first
    // death tick; the ordinary corpse-run path then releases the player before
    // a real owner can submit the resurrection spell.  Keep the target bound
    // to the original map/instance and reject DEAD/ghost/released players.
    bool const nativeDeathWindow = bot
        && (bot->getDeathState() == JUST_DIED || bot->getDeathState() == CORPSE);
    if (!Cohort().Config.ValidationRouteEnable || !state.ValidationCohortLocked || !bot
        || !bot->IsInWorld() || bot->IsAlive() || !nativeDeathWindow
        || bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST) || state.NativeReleaseRequested
        || bot->GetMapId() != state.ValidationCohortMapId
        || bot->GetInstanceId() != state.ValidationCohortInstanceId)
        return false;

    Group const* group = bot->GetGroup();
    return group
        && group->GetGUID() == state.ValidationCohortGroupGuid
        && group->GetLeaderGUID() == state.ValidationCohortLeaderGuid;
}

bool BotWorldPopulationMgr::HasNativeRaidCorpseAuthority(WorldBotState const& state, Player const* bot) const
{
    if (!Cohort().Config.ValidationRouteEnable || !state.ValidationCohortLocked || !bot
        || !state.ValidationCohortMapId || !state.ValidationCohortInstanceId
        || !bot->HasCorpse()
        || bot->GetCorpseLocation().GetMapId() != state.ValidationCohortMapId)
        return false;

    Group const* group = bot->GetGroup();
    if (!group || group->GetGUID() != state.ValidationCohortGroupGuid
        || group->GetLeaderGUID() != state.ValidationCohortLeaderGuid)
        return false;

    // Player::GetCorpse() follows the current map, which is deliberately the
    // outdoor graveyard after native release.  Resolve the corpse from the
    // frozen raid map/instance instead and require ownership plus exact
    // instance identity before authorizing any native worldport.
    Map* originalMap = sMapMgr->FindMap(state.ValidationCohortMapId, state.ValidationCohortInstanceId);
    Corpse* originalCorpse = originalMap ? originalMap->GetCorpseByPlayer(bot->GetGUID()) : nullptr;
    return originalCorpse
        && originalCorpse->GetOwnerGUID() == bot->GetGUID()
        && originalCorpse->GetMapId() == state.ValidationCohortMapId
        && originalCorpse->GetInstanceId() == state.ValidationCohortInstanceId;
}

bool BotWorldPopulationMgr::ObserveNativeRaidHostileActivity(Map* raidMap, WorldObject const* observer,
    bool& active, std::string& reason, uint32& entry, ObjectGuid& guid) const
{
    active = false;
    reason.clear();
    entry = 0;
    guid.Clear();

    if (!raidMap || !observer)
    {
        // An unavailable map is not an observed reset. The caller must keep
        // the recovery gate closed instead of interpreting missing state as
        // an empty, safe encounter.
        reason = !raidMap ? "native_raid_map_unavailable" : "native_raid_hostility_observer_unavailable";
        return false;
    }

    NativeRaidHostileActivityVisitor visitor(observer);
    TypeContainerVisitor<NativeRaidHostileActivityVisitor, MapStoredObjectTypesContainer> containerVisitor(visitor);
    containerVisitor.Visit(raidMap->GetObjectsStore());
    active = visitor.Active;
    entry = visitor.ActiveEntry;
    guid = visitor.ActiveGuid;
    if (active)
    {
        std::ostringstream detail;
        detail << "native_hostile_activity_guid=" << guid.GetRawValue()
               << ":entry=" << entry;
        reason = detail.str();
    }
    else
        reason = "native_hostiles_inactive";
    return true;
}

bool BotWorldPopulationMgr::ResolveNativeValidationEntrance(uint32 targetMapId, uint32 sourceMapId,
    float /*sourceX*/, float /*sourceY*/, AreaTriggerEntry const*& entry, AreaTriggerStruct const*& destination) const
{
    entry = nullptr;
    destination = nullptr;
    RaidRuntime const& admission = Cohort().Raid;
    bool const certifiedAttempt = !Party().ValidationRouteManifest.empty();
    if (certifiedAttempt && (!admission.ServerProvisioningComplete
        || admission.AdmissionAttemptId != Cohort().AttemptId))
        return false;

    // Once admission commits, native corpse recovery is bound to the same
    // immutable entrance receipt as initial provisioning.  A profile/config
    // reload must never be able to redirect an active ghost run.
    uint32 triggerId = certifiedAttempt
        ? admission.AdmissionRecoveryEntranceAreaTriggerId
        : Cohort().Config.ValidationRecoveryEntranceAreaTriggerId;
    uint32 expectedSourceMapId = certifiedAttempt
        ? admission.AdmissionRecoveryEntranceSourceMapId
        : Cohort().Config.ValidationRecoveryEntranceSourceMapId;
    uint32 expectedTargetMapId = certifiedAttempt
        ? admission.AdmissionRecoveryEntranceTargetMapId
        : Cohort().Config.ValidationRecoveryEntranceTargetMapId;
    if (!triggerId && targetMapId == BlackwingDescentMapId)
    {
        triggerId = BlackwingDescentEntranceTriggerId;
        expectedSourceMapId = BlackwingDescentEntranceMapId;
        expectedTargetMapId = BlackwingDescentMapId;
    }
    if (!triggerId || expectedSourceMapId != sourceMapId
        || expectedTargetMapId != targetMapId)
        return false;

    entry = sAreaTriggerStore.LookupEntry(triggerId);
    destination = entry ? sObjectMgr->GetAreaTrigger(triggerId) : nullptr;
    return entry && destination
        && entry->ID == triggerId
        && entry->ContinentID == expectedSourceMapId
        && destination->target_mapId == expectedTargetMapId
        && sMapStore.LookupEntry(expectedSourceMapId)
        && sMapStore.LookupEntry(expectedTargetMapId);
}

bool BotWorldPopulationMgr::IsNativeReleasedGhostWorldport(WorldBotState const& state, Player* bot) const
{
    if (!state.NativeReleaseRequested || state.NativeRunbackAreaTriggerId
        || !state.ValidationCohortMapId || !bot
        || bot->IsInWorld() || !bot->IsBeingTeleportedFar()
        || bot->IsAlive() || !bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST)
        || bot->GetMapId() != state.ValidationCohortMapId
        || !HasNativeRaidCorpseAuthority(state, bot))
        return false;

    // Bind the pending worldport to the exact graveyard that native
    // RepopAtGraveyard resolves from this dead player.  Map identity alone is
    // insufficient because unrelated far teleports can also target map 0.
    WorldSafeLocsEntry const* graveyard = sObjectMgr->GetClosestGraveyard(*bot, bot->GetTeam(), bot);
    AreaTriggerEntry const* entranceEntry = nullptr;
    AreaTriggerStruct const* entranceDestination = nullptr;
    if (!graveyard || !ResolveNativeValidationEntrance(state.ValidationCohortMapId,
            graveyard->Continent, graveyard->Loc.X, graveyard->Loc.Y,
            entranceEntry, entranceDestination))
        return false;

    WorldLocation const& destination = bot->GetTeleportDest();
    float const* graveyardOrientation = sObjectMgr->GetGraveyardOrientation(graveyard->ID);
    float expectedOrientation = graveyardOrientation ? *graveyardOrientation : bot->GetOrientation();
    return destination.GetMapId() == graveyard->Continent
        && !bot->GetTeleportDestInstanceId()
        && bot->GetTeleportDestOptions() == TELE_TO_NONE
        && std::fabs(destination.GetPositionX() - graveyard->Loc.X) <= 0.01f
        && std::fabs(destination.GetPositionY() - graveyard->Loc.Y) <= 0.01f
        && std::fabs(destination.GetPositionZ() - graveyard->Loc.Z) <= 0.01f
        && std::fabs(destination.GetOrientation() - expectedOrientation) <= 0.01f;
}

bool BotWorldPopulationMgr::IsNativeValidationRunbackWorldport(WorldBotState const& state, Player* bot) const
{
    if (!state.NativeReleaseRequested || !state.NativeRunbackAreaTriggerId
        || !state.ValidationCohortMapId || !bot
        || bot->IsInWorld() || !bot->IsBeingTeleportedFar()
        || bot->IsAlive() || !bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST)
        || !HasNativeRaidCorpseAuthority(state, bot))
        return false;

    AreaTriggerEntry const* entranceEntry = sAreaTriggerStore.LookupEntry(state.NativeRunbackAreaTriggerId);
    AreaTriggerStruct const* entranceDestination = entranceEntry
        ? sObjectMgr->GetAreaTrigger(state.NativeRunbackAreaTriggerId) : nullptr;
    if (!entranceEntry || !entranceDestination
        || entranceDestination->target_mapId != state.ValidationCohortMapId)
        return false;

    WorldLocation const& worldport = bot->GetTeleportDest();
    return bot->GetMapId() == entranceEntry->ContinentID
        && worldport.GetMapId() == entranceDestination->target_mapId
        && !bot->GetTeleportDestInstanceId()
        && bot->GetTeleportDestOptions() == TELE_TO_NOT_LEAVE_TRANSPORT
        && std::fabs(worldport.GetPositionX() - entranceDestination->target_X) <= 0.01f
        && std::fabs(worldport.GetPositionY() - entranceDestination->target_Y) <= 0.01f
        && std::fabs(worldport.GetPositionZ() - entranceDestination->target_Z) <= 0.01f
        && std::fabs(worldport.GetOrientation() - entranceDestination->target_Orientation) <= 0.01f;
}

bool BotWorldPopulationMgr::IsValidationCohortMemberInOriginalInstance(WorldBotState const& state, Player const* bot) const
{
    if (!Cohort().Config.ValidationRouteEnable || !state.ValidationCohortLocked || !bot)
        return true;

    Group const* group = bot->GetGroup();
    if (!group || group->GetGUID() != state.ValidationCohortGroupGuid
        || group->GetLeaderGUID() != state.ValidationCohortLeaderGuid)
        return false;

    // A released ghost must leave an instance to run from the native
    // graveyard back to its entrance.  The corpse remains the immutable
    // authority for the exact original map and instance; alive players never
    // receive this exception.
    if (!bot->IsAlive() && bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST)
        && bot->HasCorpse()
        && bot->GetCorpseLocation().GetMapId() == state.ValidationCohortMapId)
    {
        // Released ghosts are normally on the graveyard map, so Player::GetCorpse
        // would query that current map and can legitimately return null. Resolve
        // the corpse from the frozen raid instance instead; missing or foreign
        // corpse authority is never an exemption.
        Map* originalMap = sMapMgr->FindMap(state.ValidationCohortMapId, state.ValidationCohortInstanceId);
        Corpse* originalCorpse = originalMap ? originalMap->GetCorpseByPlayer(bot->GetGUID()) : nullptr;
        if (originalCorpse
            && originalCorpse->GetOwnerGUID() == bot->GetGUID()
            && originalCorpse->GetMapId() == state.ValidationCohortMapId
            && originalCorpse->GetInstanceId() == state.ValidationCohortInstanceId)
            return true;
    }

    return bot->IsInWorld()
        && bot->GetMapId() == state.ValidationCohortMapId
        && bot->GetInstanceId() == state.ValidationCohortInstanceId;
}

void BotWorldPopulationMgr::MarkValidationCohortViolation(WorldBotState& state, Player const* bot, char const* reason)
{
    if (!Cohort().Config.ValidationRouteEnable)
        return;

    std::string const violationReason = reason && *reason
        ? reason : "validation_cohort_instance_violation";
    Cohort().ValidationAdmission = ValidationAdmissionPhase::Terminal;
    Cohort().ValidationAdmissionBatchSealed = false;
    Cohort().Raid.ServerProvisioningComplete = false;
    Cohort().Raid.BotActionsEnabled = false;
    for (WorldBotState const& member : Party().Bots)
        BotRaidAreaAuthority::SetAllOffenseSuppressed(
            member.Guid.GetRawValue(), true);
    Cohort().LastPopulationFailureReason = violationReason;
    if (Cohort().ValidationAttemptFailureReason.empty()
        || Cohort().ValidationAttemptFailureAttemptId != Cohort().AttemptId)
    {
        Cohort().ValidationAttemptFailureReason = violationReason;
        Cohort().ValidationAttemptFailureAttemptId = Cohort().AttemptId;
        Cohort().ValidationAttemptFailureRouteGeneration = Party().ValidationRouteGeneration;
    }

    if (state.ValidationCohortViolation)
        return;

    state.ValidationCohortViolation = true;
    state.ValidationCohortViolationReason = violationReason;
    state.ValidationRouteTerminalState = true;
    state.ValidationRouteTerminalAtMs = NowMs();
    state.ValidationRouteTerminalGeneration = Party().ValidationRouteGeneration;
    state.ValidationRouteTerminalReason = "validation_cohort_instance_violation";
    state.LastDecisionResult = "validation_cohort_instance_violation";
    state.LastDecisionReason = state.ValidationCohortViolationReason;
    if (bot)
    {
        TC_LOG_ERROR("server", "BotWorld validation_cohort_instance_violation bot=%s map=%u instance=%u expected_map=%u expected_instance=%u reason=%s",
            bot->GetGUID().ToString().c_str(), bot->GetMapId(), bot->GetInstanceId(),
            state.ValidationCohortMapId, state.ValidationCohortInstanceId, state.ValidationCohortViolationReason.c_str());
    }
}

bool BotWorldPopulationMgr::FailValidationAttemptOnce(
    WorldBotState& reporterState, Player* reporter,
    std::string const& reason, uint64 routeGeneration)
{
    if (!Cohort().Config.ValidationRouteEnable || reason.empty()
        || !routeGeneration
        || routeGeneration != Party().ValidationRouteGeneration)
        return false;

    // A validation attempt has one terminal edge. Later members observe the
    // latched cohort result and hold; they must not emit one terminal event
    // each or replace the first attributable cause with a secondary symptom.
    if (!Cohort().ValidationAttemptFailureReason.empty()
        && Cohort().ValidationAttemptFailureAttemptId == Cohort().AttemptId)
        return false;

    uint64 const nowMs = NowMs();
    Cohort().ValidationAttemptFailureReason = reason;
    Cohort().ValidationAttemptFailureAttemptId = Cohort().AttemptId;
    Cohort().ValidationAttemptFailureRouteGeneration = routeGeneration;
    Cohort().LastPopulationFailureReason = reason;
    // Preserve the immutable admission receipt for evidence, but move its
    // lifecycle out of Active before closing the gates. EnsurePopulation then
    // returns at the terminal guard and cannot re-enter cohort validation or
    // provisioning for this failed attempt.
    Cohort().ValidationAdmission = ValidationAdmissionPhase::Terminal;
    Cohort().Raid.BotActionsEnabled = false;
    Cohort().Raid.AdmissionActionGateEnabled = false;

    // Close every continuous action owner at cohort scope. Offense is masked
    // immediately; the typed melee reconciler observes that mask on scope exit
    // (and on every later closed-gate tick). Grounded route movement is
    // cancelled without manufacturing a fall or changing player position.
    for (WorldBotState& member : Party().Bots)
    {
        BotRaidAreaAuthority::SetAllOffenseSuppressed(
            member.Guid.GetRawValue(), true);
        BotMovementArbitration::Clear(member.MovementLease);
        member.ActivePathValid = false;
        member.TargetGuid.Clear();
        member.DecisionTimer = 0;
        member.ValidationRouteTerminalState = true;
        member.ValidationRouteTerminalAtMs = nowMs;
        member.ValidationRouteTerminalGeneration = routeGeneration;
        member.ValidationRouteTerminalReason = reason;
        member.LastDecisionSituation = "validation_route_terminal";
        member.LastDecisionAction = "validation_route_terminal_hold";
        member.LastDecisionResult = reason;
        member.LastDecisionReason = reason;
        member.LastNoProgressReason = reason;

        if (Player* loaded = GetLoadedBot(member);
            loaded && loaded->IsInWorld() && !loaded->IsFalling())
            loaded->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    }

    if (reporter)
    {
        std::ostringstream raw;
        raw << "{\"attempt_id\":" << Cohort().AttemptId
            << ",\"route_generation\":" << routeGeneration
            << ",\"failure_reason\":\"" << JsonEscape(reason) << "\""
            << ",\"native_recovery_episode\":"
            << BuildNativeRecoveryEpisodeJson(&reporterState) << "}";
        std::ostringstream semantic;
        semantic << "{\"terminal\":true,\"scope\":\"validation_cohort\""
                 << ",\"failure_reason\":\"" << JsonEscape(reason) << "\"}";
        RecordEvent(reporterState, reporter, "validation_route_terminal",
            nullptr, reason.c_str(), raw.str().c_str(),
            semantic.str().c_str(), 0.0f, uint32(routeGeneration));
    }

    return true;
}

