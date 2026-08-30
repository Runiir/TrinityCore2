#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotChainwielderOwnerCheckpoint.h"
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"

#include "Creature.h"
#include "GameTime.h"
#include "GitRevision.h"
#include "Map.h"
#include "MotionMaster.h"
#include "ObjectMgr.h"
#include "Player.h"

#include <algorithm>
#include <chrono>
#include <sstream>
#include <vector>

namespace
{
using BotChainwielderOwnerCheckpoint::OwnerSnapshot;
using BotChainwielderOwnerCheckpoint::Stage;

uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

char const* StageName(Stage stage)
{
    switch (stage)
    {
        case Stage::Disabled: return "disabled";
        case Stage::Armed: return "armed";
        case Stage::RejectionObserved: return "rejection_observed";
        case Stage::AfterObserved: return "after_observed";
        case Stage::Completed: return "completed";
        case Stage::Failed: return "failed";
    }
    return "unknown";
}

char const* OwnerName(BotMovementArbitration::Owner owner)
{
    switch (owner)
    {
        case BotMovementArbitration::Owner::Route: return "route";
        case BotMovementArbitration::Owner::Hazard: return "hazard";
        case BotMovementArbitration::Owner::CombatRange: return "combat_range";
        case BotMovementArbitration::Owner::Formation: return "formation";
        case BotMovementArbitration::Owner::Mechanic: return "mechanic";
        case BotMovementArbitration::Owner::Recovery: return "recovery";
        case BotMovementArbitration::Owner::None: return "none";
    }
    return "unknown";
}

std::string EscapeJson(std::string const& value)
{
    std::string escaped;
    escaped.reserve(value.size());
    for (char character : value)
    {
        switch (character)
        {
            case '\\': escaped += "\\\\"; break;
            case '"': escaped += "\\\""; break;
            case '\n': escaped += "\\n"; break;
            case '\r': escaped += "\\r"; break;
            case '\t': escaped += "\\t"; break;
            default: escaped += character; break;
        }
    }
    return escaped;
}

OwnerSnapshot CaptureOwnerSnapshot(
    BotWorldPopulationMgrBotState::WorldBotState const& state)
{
    OwnerSnapshot snapshot;
    snapshot.MovementOwner = state.MovementLease.MovementOwner;
    snapshot.ActivePathValid = state.ActivePathValid;
    snapshot.ActivePathSegmentValid = state.ActivePathSegmentValid;
    snapshot.ActivePathTraversalMode = state.ActivePathTraversalMode;
    snapshot.ActivePathTargetGuid = state.ActivePathTargetGuid.GetRawValue();
    snapshot.ActivePathAttemptId = state.ActivePathAttemptId;
    snapshot.ActivePathWipeGeneration = state.ActivePathWipeGeneration;
    snapshot.ActivePathRouteGeneration = state.ActivePathRouteGeneration;
    snapshot.ActivePathRouteNodeId = state.ActivePathRouteNodeId;
    snapshot.ActivePathToX = state.ActivePathToX;
    snapshot.ActivePathToY = state.ActivePathToY;
    snapshot.ActivePathToZ = state.ActivePathToZ;
    snapshot.DodgeCasterGuid =
        state.ValidationRouteDodgeCasterGuid.GetRawValue();
    snapshot.DodgeSpellId = state.ValidationRouteDodgeSpellId;
    snapshot.DodgeUntilMs = state.ValidationRouteDodgeUntilMs;
    snapshot.DodgeBearingAttempt = state.ValidationRouteDodgeBearingAttempt;
    snapshot.LastPathRejectReason = state.LastPathRejectReason;
    return snapshot;
}

void WriteSnapshot(std::ostringstream& json, OwnerSnapshot const& snapshot)
{
    json << "{\"movement_owner\":\"" << OwnerName(snapshot.MovementOwner)
         << "\",\"active_path_valid\":"
         << (snapshot.ActivePathValid ? "true" : "false")
         << ",\"active_path_segment_valid\":"
         << (snapshot.ActivePathSegmentValid ? "true" : "false")
         << ",\"active_path_traversal_mode\":\""
         << EscapeJson(snapshot.ActivePathTraversalMode)
         << "\",\"active_path_target_guid\":" << snapshot.ActivePathTargetGuid
         << ",\"active_path_attempt_id\":" << snapshot.ActivePathAttemptId
         << ",\"active_path_wipe_generation\":"
         << snapshot.ActivePathWipeGeneration
         << ",\"active_path_route_generation\":"
         << snapshot.ActivePathRouteGeneration
         << ",\"active_path_route_node_id\":\""
         << EscapeJson(snapshot.ActivePathRouteNodeId)
         << "\",\"active_path_destination\":{\"x\":"
         << snapshot.ActivePathToX << ",\"y\":" << snapshot.ActivePathToY
         << ",\"z\":" << snapshot.ActivePathToZ << "}"
         << ",\"dodge_caster_guid\":" << snapshot.DodgeCasterGuid
         << ",\"dodge_spell_id\":" << snapshot.DodgeSpellId
         << ",\"dodge_until_ms\":" << snapshot.DodgeUntilMs
         << ",\"dodge_bearing_attempt\":"
         << uint32(snapshot.DodgeBearingAttempt)
         << ",\"last_path_reject_reason\":\""
         << EscapeJson(snapshot.LastPathRejectReason)
         << "\"}";
}
}

std::string BotWorldPopulationMgr::ArmChainwielderOwnerCheckpointForCohort(
    std::string const& cohortId, uint32 actorGuid,
    std::string const& sealSha256, std::string const& sourceCommit)
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_chainwielder_checkpoint", cohortId);
    std::string previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    std::string result = ArmChainwielderOwnerCheckpoint(
        actorGuid, sealSha256, sourceCommit);
    _selectedCohortId = previous;
    return result;
}

std::string BotWorldPopulationMgr::GetChainwielderOwnerCheckpointJsonForCohort(
    std::string const& cohortId) const
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_chainwielder_checkpoint", cohortId);
    std::string previous = _selectedCohortId;
    const_cast<BotWorldPopulationMgr*>(this)->_selectedCohortId = cohortId;
    std::string result = BuildChainwielderOwnerCheckpointJson();
    const_cast<BotWorldPopulationMgr*>(this)->_selectedCohortId = previous;
    return result;
}

std::string BotWorldPopulationMgr::ArmChainwielderOwnerCheckpoint(
    uint32 actorGuid, std::string const& sealSha256,
    std::string const& sourceCommit)
{
    using namespace BotChainwielderOwnerCheckpoint;
    auto actor = std::find_if(Party().Bots.begin(), Party().Bots.end(),
        [actorGuid](WorldBotState const& state)
        {
            return state.Guid.GetCounter() == actorGuid;
        });
    Player* actorPlayer = actor == Party().Bots.end()
        ? nullptr : GetLoadedBot(*actor);
    GateInput const gate{
        Cohort().Config.ChainwielderOwnerCheckpointEnable,
        Cohort().Active,
        Cohort().SelectedProfileName,
        Cohort().Config.Name,
        Cohort().Config.PoolTagFilter,
        Cohort().Config.ValidationRouteScenarioId,
        Cohort().Config.ValidationRouteNodeId,
        actorPlayer ? actorPlayer->GetMapId() : 0,
        Cohort().Config.TargetPopulation,
        uint32(Party().Bots.size()),
        Cohort().Config.ValidationRouteTargetEntry,
        Cohort().Config.ValidationRouteEnable,
        Cohort().Config.AllowRaids,
        Cohort().AttemptId,
        Cohort().Config.ChainwielderOwnerCheckpointFixtureId,
        Cohort().Config.ChainwielderOwnerCheckpointSealSha256,
        sealSha256,
        Cohort().Config.ChainwielderOwnerCheckpointSourceCommit,
        sourceCommit,
        GitRevision::GetHash(),
    };
    if (char const* reason = RejectionReason(gate))
    {
        Cohort().ChainwielderOwnerCheckpoint.Outcome = reason;
        return BuildChainwielderOwnerCheckpointJson();
    }

    if (!actorGuid || actor == Party().Bots.end() || !actorPlayer
        || !actorPlayer->IsInWorld())
    {
        Cohort().ChainwielderOwnerCheckpoint.Outcome =
            "chainwielder_checkpoint_actor_not_in_cohort";
        return BuildChainwielderOwnerCheckpointJson();
    }

    State& checkpoint = Cohort().ChainwielderOwnerCheckpoint;
    if (checkpoint.AttemptId == Cohort().AttemptId
        && checkpoint.CurrentStage != Stage::Disabled)
    {
        checkpoint.Outcome = "chainwielder_checkpoint_already_armed";
        return BuildChainwielderOwnerCheckpointJson();
    }

    checkpoint = {};
    checkpoint.CurrentStage = Stage::Armed;
    checkpoint.AttemptId = Cohort().AttemptId;
    checkpoint.ActorGuid = actorGuid;
    checkpoint.ArmedAtMs = NowMs();
    checkpoint.Outcome = "awaiting_real_route_owner";
    RecordDecisionTrace(*actor, "fixture_observation",
        "chainwielder_owner_checkpoint_armed", nullptr, 0, "ok",
        Authority, false);
    return BuildChainwielderOwnerCheckpointJson();
}

void BotWorldPopulationMgr::MaybeInjectChainwielderOwnerCheckpointAfterUpdate(
    WorldBotState& state, Player* bot)
{
    using namespace BotChainwielderOwnerCheckpoint;
    using namespace BotWorldPopulationMgrBotState::MovementRejectionIsolation;
    State& checkpoint = Cohort().ChainwielderOwnerCheckpoint;
    if (checkpoint.CurrentStage != Stage::Armed || !bot
        || state.Guid.GetCounter() != checkpoint.ActorGuid)
        return;

    ++checkpoint.AwaitTicks;
    if (checkpoint.AwaitTicks > MaximumAwaitTicks)
    {
        checkpoint.CurrentStage = Stage::Failed;
        checkpoint.Outcome = "real_route_owner_not_observed";
        RecordDecisionTrace(state, "fixture_observation",
            "chainwielder_owner_checkpoint_failed", nullptr, 0, "failed",
            checkpoint.Outcome.c_str(), false);
        return;
    }
    if (bot->GetMapId() != MapId
        || Cohort().Config.ValidationRouteNodeId != NodeId
        || Cohort().AttemptId != checkpoint.AttemptId)
        return;

    bool const matchingHazardIdentity =
        !state.ValidationRouteDodgeCasterGuid.IsEmpty()
        && state.ValidationRouteDodgeSpellId
            == Cohort().Config.ValidationRouteHazardDetectionSpellId;
    bool const routeRetryArmed = state.MovementLease.MovementOwner
            == BotMovementArbitration::Owner::Route
        && HasArmedRouteHazardRetry(
            Cohort().Config.ValidationRouteHazardSourceEntry != 0,
            matchingHazardIdentity, state.ValidationRouteDodgeUntilMs, NowMs(),
            state.ActivePathValid, state.LastPathRejectReason);
    MotionMaster* motion = bot->GetMotionMaster();
    MovementGeneratorType motionType = motion
        ? motion->GetMotionSlotType(MOTION_SLOT_ACTIVE) : MAX_MOTION_TYPE;
    bool const activeRoutePath = state.ActivePathValid
        && state.MovementLease.MovementOwner
            == BotMovementArbitration::Owner::Route
        && state.ActivePathAttemptId == Cohort().AttemptId
        && state.ActivePathWipeGeneration == Cohort().Raid.WipeGeneration
        && state.ActivePathRouteGeneration == Party().ValidationRouteGeneration
        && state.ActivePathRouteNodeId == NodeId
        && (motionType == POINT_MOTION_TYPE || motionType == CHASE_MOTION_TYPE)
        && matchingHazardIdentity;
    if (!activeRoutePath && !routeRetryArmed)
        return;

    float unsafeX = 0.0f;
    float unsafeY = 0.0f;
    float unsafeZ = 0.0f;
    bool foundUnsafeFuturePack = false;
    for (size_t routeIndex = Party().ValidationRouteManifestIndex + 1;
        routeIndex < Party().ValidationRouteManifest.size()
            && !foundUnsafeFuturePack; ++routeIndex)
    {
        ValidationRouteManifestNode const& futureNode =
            Party().ValidationRouteManifest[routeIndex];
        if (futureNode.Kind != "trash" || futureNode.MapId != MapId)
            continue;
        std::vector<ObjectGuid::LowType> sources{futureNode.TargetSpawnId};
        sources.insert(sources.end(), futureNode.SplitSourceGuids.begin(),
            futureNode.SplitSourceGuids.end());
        for (ObjectGuid::LowType sourceId : sources)
        {
            if (!sourceId)
                continue;
            CreatureData const* data = sObjectMgr->GetCreatureData(sourceId);
            if (!data || data->mapId != MapId)
                continue;
            unsafeX = data->spawnPoint.GetPositionX();
            unsafeY = data->spawnPoint.GetPositionY();
            unsafeZ = data->spawnPoint.GetPositionZ();
            if (!IsValidationRoutePatrolCombatPointSafe(
                    bot, unsafeX, unsafeY, unsafeZ))
            {
                foundUnsafeFuturePack = true;
                break;
            }
        }
    }
    if (!foundUnsafeFuturePack)
    {
        checkpoint.CurrentStage = Stage::Failed;
        checkpoint.Outcome = "future_pack_destination_not_resolved";
        RecordDecisionTrace(state, "fixture_observation",
            "chainwielder_owner_checkpoint_failed", nullptr, 0, "failed",
            checkpoint.Outcome.c_str(), false);
        return;
    }

    checkpoint.Before = CaptureOwnerSnapshot(state);
    checkpoint.TriggeredByActiveRoutePath = activeRoutePath;
    checkpoint.TriggeredByArmedRouteHazardRetry = routeRetryArmed;
    RecordDecisionTrace(state, "fixture_observation",
        "chainwielder_owner_checkpoint_before", nullptr, 0, "ok",
        Authority, false);

    BotWorldMovement::Intent rejected;
    rejected.X = unsafeX;
    rejected.Y = unsafeY;
    rejected.Z = unsafeZ;
    rejected.Owner = BotMovementArbitration::Owner::Hazard;
    rejected.Priority = BotMovementArbitration::Priority::Hazard;
    rejected.IntentReason = FixtureId;
    bool const submitted = ExecuteMovementIntent(state, bot, rejected);
    BotWorldMovement::MovementPlannerObservation observation =
        BotWorldMovement::MovementPlannerDiagnostics().Latest(
            state.Guid.GetCounter());
    ++checkpoint.InjectionCount;
    checkpoint.RejectionObservedAtMs = NowMs();
    checkpoint.RejectionReceiptId = observation.LaunchReceipt.Id;
    checkpoint.RejectionGate = observation.Gate;
    checkpoint.RejectionReason = observation.Reason;
    OwnerSnapshot const immediateAfter = CaptureOwnerSnapshot(state);
    bool const exactRejection = !submitted && observation.Available
        && observation.MovementOwner == BotMovementArbitration::Owner::Hazard
        && observation.Gate == "future_pack_destination"
        && observation.Result == "rejected"
        && observation.Reason == "route_destination_future_pack_unsafe"
        && observation.LaunchReceipt.Id == 0;
    bool const immediatePreserved = SameRouteIdentity(
        checkpoint.Before, immediateAfter);
    if (!exactRejection || !immediatePreserved
        || checkpoint.InjectionCount != 1)
    {
        checkpoint.CurrentStage = Stage::Failed;
        checkpoint.Outcome = exactRejection
            ? "foreign_route_identity_changed_during_rejection"
            : "exact_receiptless_hazard_rejection_not_observed";
        RecordDecisionTrace(state, "fixture_observation",
            "chainwielder_owner_checkpoint_failed", nullptr, 0, "failed",
            checkpoint.Outcome.c_str(), false);
        return;
    }

    checkpoint.CurrentStage = Stage::RejectionObserved;
    checkpoint.Outcome = "awaiting_subsequent_tick";
    RecordDecisionTrace(state, "fixture_observation",
        "chainwielder_owner_checkpoint_rejection", nullptr, 0, "rejected",
        "route_destination_future_pack_unsafe", false);
}

void BotWorldPopulationMgr::ObserveChainwielderOwnerCheckpointBeforeUpdate(
    WorldBotState& state, Player* bot)
{
    using namespace BotChainwielderOwnerCheckpoint;
    State& checkpoint = Cohort().ChainwielderOwnerCheckpoint;
    if (!bot || state.Guid.GetCounter() != checkpoint.ActorGuid
        || checkpoint.AttemptId != Cohort().AttemptId)
        return;

    if (checkpoint.CurrentStage == Stage::RejectionObserved)
    {
        checkpoint.After = CaptureOwnerSnapshot(state);
        checkpoint.AfterObservedAtMs = NowMs();
        checkpoint.BeforeAfterIdentityPreserved = SameRouteIdentity(
            checkpoint.Before, checkpoint.After);
        if (!checkpoint.BeforeAfterIdentityPreserved)
        {
            checkpoint.CurrentStage = Stage::Failed;
            checkpoint.Outcome =
                "foreign_route_identity_changed_before_subsequent_tick";
            RecordDecisionTrace(state, "fixture_observation",
                "chainwielder_owner_checkpoint_after", nullptr, 0, "failed",
                checkpoint.Outcome.c_str(), false);
            return;
        }
        checkpoint.CurrentStage = Stage::AfterObserved;
        checkpoint.Outcome = "foreign_route_identity_preserved";
        RecordDecisionTrace(state, "fixture_observation",
            "chainwielder_owner_checkpoint_after", nullptr, 0, "ok",
            checkpoint.Outcome.c_str(), false);
        return;
    }
    if (checkpoint.CurrentStage != Stage::AfterObserved)
        return;

    ++checkpoint.AwaitTicks;
    if (state.ValidationRouteDodgeCasterGuid.IsEmpty()
        && state.ValidationRouteDodgeSpellId == 0)
    {
        checkpoint.CurrentStage = Stage::Completed;
        checkpoint.Outcome = "hazard_exit_completed";
    }
    else if (!bot->IsAlive())
    {
        checkpoint.CurrentStage = Stage::Failed;
        checkpoint.Outcome = "actor_died_before_hazard_exit_completion";
    }
    else if (state.ValidationRouteTerminalState)
    {
        checkpoint.CurrentStage = Stage::Failed;
        checkpoint.Outcome = state.ValidationRouteTerminalReason.empty()
            ? "route_terminal_before_hazard_exit_completion"
            : state.ValidationRouteTerminalReason;
    }
    else if (Cohort().Config.ValidationRouteNodeId != NodeId
        || checkpoint.AwaitTicks > MaximumAwaitTicks)
    {
        checkpoint.CurrentStage = Stage::Failed;
        checkpoint.Outcome = Cohort().Config.ValidationRouteNodeId != NodeId
            ? "route_advanced_before_hazard_exit_completion"
            : "hazard_exit_completion_timeout";
    }
    else
        return;

    checkpoint.OutcomeObservedAtMs = NowMs();
    RecordDecisionTrace(state, "fixture_observation",
        "chainwielder_owner_checkpoint_outcome", nullptr, 0,
        checkpoint.CurrentStage == Stage::Completed ? "ok" : "failed",
        checkpoint.Outcome.c_str(), false);
}

std::string BotWorldPopulationMgr::BuildChainwielderOwnerCheckpointJson() const
{
    using namespace BotChainwielderOwnerCheckpoint;
    State const& checkpoint = Cohort().ChainwielderOwnerCheckpoint;
    std::ostringstream json;
    bool const gatePassed = checkpoint.CurrentStage != Stage::Disabled;
    bool const terminal = checkpoint.CurrentStage == Stage::Completed
        || checkpoint.CurrentStage == Stage::Failed;
    bool const commandOk = gatePassed
        && checkpoint.CurrentStage != Stage::Failed;
    json << "{\"ok\":" << (commandOk ? "true" : "false")
         << ",\"action\":\"botauto_chainwielder_checkpoint\"";
    AppendGenericRuntimeIdentityJson(json);
    json << ",\"authority\":\"" << Authority << "\""
         << ",\"fixture_id\":\"" << FixtureId << "\""
         << ",\"scenario_id\":\""
         << JsonEscape(Cohort().Config.ValidationRouteScenarioId) << "\""
         << ",\"route_node_id\":\""
         << JsonEscape(Cohort().Config.ValidationRouteNodeId) << "\""
         << ",\"map_id\":" << Cohort().Config.ValidationRouteMapId
         << ",\"configured_seal_sha256\":\""
         << JsonEscape(Cohort().Config
                .ChainwielderOwnerCheckpointSealSha256) << "\""
         << ",\"configured_source_commit\":\""
         << JsonEscape(Cohort().Config
                .ChainwielderOwnerCheckpointSourceCommit) << "\""
         << ",\"gate_passed\":" << (gatePassed ? "true" : "false")
         << ",\"terminal\":" << (terminal ? "true" : "false")
         << ",\"stage\":\"" << StageName(checkpoint.CurrentStage) << "\""
         << ",\"actor_guid\":" << checkpoint.ActorGuid
         << ",\"await_ticks\":" << checkpoint.AwaitTicks
         << ",\"injection_count\":" << checkpoint.InjectionCount
         << ",\"triggered_by_active_route_path\":"
         << (checkpoint.TriggeredByActiveRoutePath ? "true" : "false")
         << ",\"triggered_by_armed_route_hazard_retry\":"
         << (checkpoint.TriggeredByArmedRouteHazardRetry ? "true" : "false")
         << ",\"rejection\":{\"owner\":\"hazard\",\"gate\":\""
         << JsonEscape(checkpoint.RejectionGate)
         << "\",\"reason\":\"" << JsonEscape(checkpoint.RejectionReason)
         << "\",\"planner_receipt_id\":"
         << checkpoint.RejectionReceiptId << "}"
         << ",\"before_after_identity_preserved\":"
         << (checkpoint.BeforeAfterIdentityPreserved ? "true" : "false")
         << ",\"before\":";
    WriteSnapshot(json, checkpoint.Before);
    json << ",\"after\":";
    WriteSnapshot(json, checkpoint.After);
    json << ",\"outcome\":\"" << JsonEscape(checkpoint.Outcome) << "\""
         << ",\"timestamps_ms\":{\"armed\":" << checkpoint.ArmedAtMs
         << ",\"rejection\":" << checkpoint.RejectionObservedAtMs
         << ",\"after\":" << checkpoint.AfterObservedAtMs
         << ",\"outcome\":" << checkpoint.OutcomeObservedAtMs << "}}";
    return json.str();
}
