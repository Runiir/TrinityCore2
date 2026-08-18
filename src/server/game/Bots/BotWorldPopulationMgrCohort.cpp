#include "Bots/BotWorldPopulationMgr.h"

#include "Group.h"
#include "GroupMgr.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "WorldPacket.h"
#include "WorldSession.h"

#include <algorithm>
#include <chrono>
#include <limits>
#include <mutex>
#include <sstream>
#include <vector>

#if defined(_WIN32)
#include <process.h>
#else
#include <unistd.h>
#endif

namespace
{
uint64 CurrentProcessId()
{
#if defined(_WIN32)
    return static_cast<uint64>(::_getpid());
#else
    return static_cast<uint64>(::getpid());
#endif
}

uint64 BuildServerEpoch()
{
    uint64 const startedAtUs = static_cast<uint64>(std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count());
    return startedAtUs ^ (CurrentProcessId() << 32);
}

}

BotWorldPopulationMgr::BotWorldPopulationMgr() : _serverEpoch(BuildServerEpoch())
{
    auto runtime = std::make_unique<CohortRuntime>();
    runtime->Id = "default";
    _cohorts.emplace(runtime->Id, std::move(runtime));
}

BotWorldPopulationMgr::CohortRuntime& BotWorldPopulationMgr::Cohort()
{
    return *_cohorts.at(_selectedCohortId);
}

BotWorldPopulationMgr::CohortRuntime const& BotWorldPopulationMgr::Cohort() const
{
    return *_cohorts.at(_selectedCohortId);
}

BotWorldPopulationMgr::PartyRuntime& BotWorldPopulationMgr::Party()
{
    return Cohort().Party;
}

BotWorldPopulationMgr::PartyRuntime const& BotWorldPopulationMgr::Party() const
{
    return Cohort().Party;
}

BotWorldPopulationMgr::CohortRuntime* BotWorldPopulationMgr::FindCohort(std::string const& cohortId)
{
    auto itr = _cohorts.find(cohortId);
    return itr == _cohorts.end() ? nullptr : itr->second.get();
}

BotWorldPopulationMgr::CohortRuntime const* BotWorldPopulationMgr::FindCohort(std::string const& cohortId) const
{
    auto itr = _cohorts.find(cohortId);
    return itr == _cohorts.end() ? nullptr : itr->second.get();
}

bool BotWorldPopulationMgr::SelectCohort(std::string const& cohortId)
{
    if (!FindCohort(cohortId))
        return false;

    _selectedCohortId = cohortId;
    return true;
}

uint32 BotWorldPopulationMgr::ActiveCohortCount() const
{
    uint32 count = 0;
    for (auto const& [id, runtime] : _cohorts)
        if (runtime && runtime->Active)
            ++count;
    return count;
}

std::string BotWorldPopulationMgr::CreateCohort(std::string const& cohortId)
{
    if (cohortId.empty() || cohortId.size() > 64
        || cohortId.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-") != std::string::npos)
        return "{\"ok\":false,\"action\":\"botauto_create\",\"failure_reason\":\"invalid_cohort_id\"}";

    if (HasCohort(cohortId))
        return "{\"ok\":true,\"action\":\"botauto_create\",\"cohort_id\":\"" + JsonEscape(cohortId) + "\",\"created\":false,\"failure_reason\":null}";

    auto runtime = std::make_unique<CohortRuntime>();
    runtime->Id = cohortId;
    _cohorts.emplace(cohortId, std::move(runtime));
    return "{\"ok\":true,\"action\":\"botauto_create\",\"cohort_id\":\"" + JsonEscape(cohortId) + "\",\"created\":true,\"failure_reason\":null}";
}

bool BotWorldPopulationMgr::HasCohort(std::string const& cohortId) const
{
    return FindCohort(cohortId) != nullptr;
}

size_t BotWorldPopulationMgr::GetCohortCount() const
{
    return _cohorts.size();
}

std::string BotWorldPopulationMgr::ResolveGlobalCohortId() const
{
    return _cohorts.size() == 1 ? _cohorts.begin()->first : "";
}

std::string BotWorldPopulationMgr::UnknownCohortJson(char const* action, std::string const& cohortId) const
{
    return "{\"ok\":false,\"action\":\"" + JsonEscape(action ? action : "botauto_cohort")
        + "\",\"cohort_id\":\"" + JsonEscape(cohortId) + "\",\"failure_reason\":\"unknown_cohort\"}";
}

std::string BotWorldPopulationMgr::GetCohortRegistryJson() const
{
    std::ostringstream json;
    json << "{\"ok\":true,\"action\":\"botauto_cohorts\",\"server_epoch\":" << _serverEpoch
         << ",\"server_process_id\":" << CurrentProcessId()
         << ",\"max_active_cohorts\":" << MaxActiveCohorts
         << ",\"active_cohort_count\":" << ActiveCohortCount()
         << ",\"cohort_count\":" << _cohorts.size() << ",\"cohorts\":[";
    bool first = true;
    for (auto const& [id, runtime] : _cohorts)
    {
        if (!first)
            json << ',';
        first = false;
        json << "{\"cohort_id\":\"" << JsonEscape(id) << "\",\"active\":" << (runtime->Active ? "true" : "false")
             << ",\"attempt_id\":" << runtime->AttemptId << ",\"lease_count\":" << runtime->RosterLeases.size()
             << ",\"party_bot_count\":" << runtime->Party.Bots.size() << "}";
    }
    json << "],\"failure_reason\":null}";
    return json.str();
}

std::string BotWorldPopulationMgr::GetCohortIsolationContractJson()
{
    static constexpr char ProbeA[] = "phase5_probe_a";
    static constexpr char ProbeB[] = "phase5_probe_b";
    CreateCohort(ProbeA);
    CreateCohort(ProbeB);

    CohortRuntime& first = *FindCohort(ProbeA);
    CohortRuntime& second = *FindCohort(ProbeB);
    first.AttemptId = 1;
    second.AttemptId = 1;
    first.ElapsedMs = 111;
    second.ElapsedMs = 222;
    first.CalibrationStartedMs = 333;
    second.CalibrationStartedMs = 444;
    first.RecordingWindowElapsedMs = 555;
    second.RecordingWindowElapsedMs = 666;
    first.Party.GroupGuid = ObjectGuid(HighGuid::Group, uint32(1001));
    second.Party.GroupGuid = ObjectGuid(HighGuid::Group, uint32(1002));
    first.Party.MapId = 725;
    second.Party.MapId = 0;
    first.Party.InstanceId = 101;
    second.Party.InstanceId = 202;
    first.Party.ValidationRouteGeneration = 7;
    second.Party.ValidationRouteGeneration = 9;
    first.Party.PendingHealCasts.clear();
    second.Party.PendingHealCasts.clear();
    PendingHealCast pendingHeal;
    pendingHeal.ThreatBefore = 17.0f;
    pendingHeal.EffectiveHeal = 99;
    first.Party.PendingHealCasts.emplace(1, pendingHeal);
    first.Party.LastSaturationByBot.emplace(1, RoleSaturationState());
    second.Party.LastSaturationByBot.clear();
    WorldBotState traced;
    traced.DecisionTrace.push_back(WorldBotState::DecisionTraceEntry());
    first.Party.Bots.assign(1, traced);
    second.Party.Bots.clear();
    first.Party.CombatLogEventCount = 3;
    second.Party.CombatLogEventCount = 5;
    first.TelemetryBuffer.Configure(BotTelemetryBufferConfig{ false });
    second.TelemetryBuffer.Configure(BotTelemetryBufferConfig{ true });
    first.Party.ValidationRouteTerminalEvidence.assign(1, ValidationRouteEvidence());
    second.Party.ValidationRouteTerminalEvidence.clear();
    first.Party.RoleByGuid[1] = "tank";
    second.Party.RoleByGuid[1] = "healer";

    std::string previous = _selectedCohortId;
    uint32 syntheticGuid = std::numeric_limits<uint32>::max() - 1;
    {
        std::lock_guard<std::mutex> guard(_leaseMutex);
        _guidLeases.erase(syntheticGuid);
    }
    first.RosterLeases.erase(syntheticGuid);
    second.RosterLeases.erase(syntheticGuid);
    _selectedCohortId = ProbeA;
    bool firstClaim = ClaimBotGuid(syntheticGuid, "tank");
    _selectedCohortId = ProbeB;
    bool secondClaimRejected = !ClaimBotGuid(syntheticGuid, "healer");
    bool foreignReleaseRejected = !ReleaseBotGuid(syntheticGuid);
    _selectedCohortId = ProbeA;
    bool ownerReleaseAccepted = ReleaseBotGuid(syntheticGuid);
    _selectedCohortId = previous;

    std::map<std::string, bool> checks = {
        { "atomic_guid_lease_conflict_rejected", firstClaim && secondClaimRejected },
        { "owner_scoped_release", foreignReleaseRejected && ownerReleaseAccepted },
        { "group_and_roles_isolated", first.Party.GroupGuid != second.Party.GroupGuid
            && first.Party.RoleByGuid[1] == "tank" && second.Party.RoleByGuid[1] == "healer" },
        { "instance_isolated", first.Party.MapId == 725 && second.Party.MapId == 0 && first.Party.InstanceId != second.Party.InstanceId },
        { "route_isolated", first.Party.ValidationRouteGeneration == 7 && second.Party.ValidationRouteGeneration == 9 },
        { "calibration_clocks_isolated", first.ElapsedMs == 111 && second.ElapsedMs == 222
            && first.CalibrationStartedMs == 333 && second.CalibrationStartedMs == 444 },
        { "recording_windows_isolated", first.RecordingWindowElapsedMs == 555 && second.RecordingWindowElapsedMs == 666 },
        { "pending_heals_isolated", first.Party.PendingHealCasts.size() == 1 && second.Party.PendingHealCasts.empty() },
        { "threat_healing_metrics_isolated", first.Party.PendingHealCasts.at(1).ThreatBefore == 17.0f
            && first.Party.PendingHealCasts.at(1).EffectiveHeal == 99
            && first.Party.LastSaturationByBot.size() == 1 && second.Party.LastSaturationByBot.empty() },
        { "trace_isolated", first.Party.Bots.size() == 1 && first.Party.Bots[0].DecisionTrace.size() == 1 && second.Party.Bots.empty() },
        { "combat_log_isolated", first.Party.CombatLogEventCount == 3 && second.Party.CombatLogEventCount == 5 },
        { "telemetry_isolated", !first.TelemetryBuffer.IsEnabled() && second.TelemetryBuffer.IsEnabled() },
        { "evidence_isolated", first.Party.ValidationRouteTerminalEvidence.size() == 1 && second.Party.ValidationRouteTerminalEvidence.empty() },
        { "serial_execution_limit", MaxActiveCohorts == 1 },
    };
    bool passed = std::all_of(checks.begin(), checks.end(), [](auto const& check) { return check.second; });
    first.ElapsedMs = 0;
    second.ElapsedMs = 0;
    first.CalibrationStartedMs = 0;
    second.CalibrationStartedMs = 0;
    first.RecordingWindowElapsedMs = 0;
    second.RecordingWindowElapsedMs = 0;
    first.Party = PartyRuntime();
    second.Party = PartyRuntime();
    first.TelemetryBuffer.Clear();
    second.TelemetryBuffer.Clear();
    first.TelemetryBuffer.Configure(BotTelemetryBufferConfig());
    second.TelemetryBuffer.Configure(BotTelemetryBufferConfig());

    std::ostringstream json;
    json << "{\"ok\":" << (passed ? "true" : "false")
         << ",\"action\":\"botauto_ownership\",\"schema\":\"botauto_cohort_isolation_v1\""
         << ",\"server_epoch\":" << _serverEpoch << ",\"max_active_cohorts\":" << MaxActiveCohorts
         << ",\"cohorts\":[\"" << ProbeA << "\",\"" << ProbeB << "\"],\"checks\":{";
    bool firstCheck = true;
    for (auto const& [name, value] : checks)
    {
        if (!firstCheck)
            json << ',';
        firstCheck = false;
        json << '\"' << name << "\":" << (value ? "true" : "false");
    }
    json << "},\"failure_reason\":" << (passed ? "null" : "\"cohort_isolation_gate_failed\"") << "}";
    return json.str();
}

bool BotWorldPopulationMgr::ClaimBotGuid(uint32 guid, std::string const& roleSlot)
{
    if (!guid || roleSlot.empty())
        return false;

    std::lock_guard<std::mutex> guard(_leaseMutex);
    auto itr = _guidLeases.find(guid);
    if (itr != _guidLeases.end())
        return itr->second.ServerEpoch == _serverEpoch
            && itr->second.CohortId == Cohort().Id
            && itr->second.AttemptId == Cohort().AttemptId
            && itr->second.RoleSlot == roleSlot;

    // A lease is unique in both dimensions: a GUID cannot occupy two
    // permanent roster slots, and a slot cannot silently change GUID during
    // an attempt.  This scan is intentionally owner-scoped so independent
    // cohorts may use the same slot names without sharing runtime state.
    for (auto const& [leasedGuid, lease] : _guidLeases)
        if (leasedGuid != guid && lease.ServerEpoch == _serverEpoch
            && lease.CohortId == Cohort().Id
            && lease.AttemptId == Cohort().AttemptId
            && lease.RoleSlot == roleSlot)
            return false;

    _guidLeases.emplace(guid, BotGuidLease{ _serverEpoch, Cohort().Id, Cohort().AttemptId, roleSlot });
    Cohort().RosterLeases.insert(guid);
    return true;
}

bool BotWorldPopulationMgr::ReleaseBotGuid(uint32 guid)
{
    std::lock_guard<std::mutex> guard(_leaseMutex);
    auto itr = _guidLeases.find(guid);
    if (itr == _guidLeases.end()
        || itr->second.ServerEpoch != _serverEpoch
        || itr->second.CohortId != Cohort().Id
        || itr->second.AttemptId != Cohort().AttemptId)
        return false;

    _guidLeases.erase(itr);
    Cohort().RosterLeases.erase(guid);
    return true;
}

void BotWorldPopulationMgr::ReleaseCohortLeases()
{
    std::vector<uint32> owned(Cohort().RosterLeases.begin(), Cohort().RosterLeases.end());
    for (uint32 guid : owned)
        ReleaseBotGuid(guid);
    // Preserve the terminal raid identity until the next attempt is
    // initialized.  Canonical cleanup status is emitted after lease release
    // and must remain bound to the server epoch and attempt just stopped.
    // EnsureValidationCohortGroup resets this runtime for a new identity.
}

bool BotWorldPopulationMgr::LeaseOwnedByCurrentCohort(uint32 guid) const
{
    std::lock_guard<std::mutex> guard(_leaseMutex);
    auto itr = _guidLeases.find(guid);
    return itr != _guidLeases.end()
        && itr->second.ServerEpoch == _serverEpoch
        && itr->second.CohortId == Cohort().Id
        && itr->second.AttemptId == Cohort().AttemptId;
}

bool BotWorldPopulationMgr::LeaseOwnedByCurrentCohort(uint32 guid, std::string const& roleSlot) const
{
    std::lock_guard<std::mutex> guard(_leaseMutex);
    auto itr = _guidLeases.find(guid);
    return itr != _guidLeases.end()
        && itr->second.ServerEpoch == _serverEpoch
        && itr->second.CohortId == Cohort().Id
        && itr->second.AttemptId == Cohort().AttemptId
        && itr->second.RoleSlot == roleSlot;
}

BotWorldPopulationMgr* BotWorldPopulationMgr::instance()
{
    static BotWorldPopulationMgr instance;
    return &instance;
}

bool BotWorldPopulationMgr::StartAutonomyForCohort(std::string const& cohortId, BotWorldExperimentConfig const* overrideConfig)
{
    CohortRuntime* runtime = FindCohort(cohortId);
    if (!runtime)
        return false;
    if (!runtime->Active && ActiveCohortCount() >= MaxActiveCohorts)
    {
        runtime->RuntimeProfileSelectionPending = false;
        return false;
    }

    std::string previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    bool reuseActiveAttempt = Cohort().Active
        && Cohort().RuntimeMode == BotWorldRuntimeMode::AlwaysOnAutonomy
        && !overrideConfig && !Cohort().RuntimeProfileDirty;
    if (!reuseActiveAttempt)
    {
        if (Cohort().Active)
        {
            if (Cohort().RuntimeMode == BotWorldRuntimeMode::AlwaysOnAutonomy)
                StopAutonomy();
            else
                Stop();
        }
        ++Cohort().AttemptId;
    }

    bool started = StartAutonomy(overrideConfig);
    if (started)
        _runningCohortId = cohortId;
    else
    {
        ReleaseCohortLeases();
        _selectedCohortId = previous;
    }
    return started;
}

std::string BotWorldPopulationMgr::StopAutonomyForCohort(std::string const& cohortId)
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_stop", cohortId);

    std::string previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    uint64 const serverEpoch = Cohort().Raid.ServerEpoch;
    uint64 const attemptId = Cohort().Raid.AttemptId;
    std::string const raidBeforeCleanup = BuildRaidRuntimeJson();
    if (Cohort().RuntimeMode == BotWorldRuntimeMode::AlwaysOnAutonomy)
        StopAutonomy();
    else
        Stop();
    ReleaseCohortLeases();
    Cohort().Raid.Active = false;
    Cohort().Raid.ActiveSize = 0;
    Cohort().Raid.AliveSize = 0;
    Cohort().Raid.RosterComplete = false;
    Cohort().Raid.UniqueLeases = false;
    if (_runningCohortId == cohortId)
        _runningCohortId.clear();
    std::ostringstream json;
    json << "{\"ok\":true,\"action\":\"botauto_stop\",\"cohort_id\":\"" << JsonEscape(cohortId)
         << "\",\"server_epoch\":" << serverEpoch << ",\"attempt_id\":" << attemptId
         << ",\"raid_runtime_before_cleanup\":" << raidBeforeCleanup
         << ",\"post_cleanup\":{\"active\":false,\"bots\":0,\"lease_count\":0}"
         << ",\"failure_reason\":null}";
    _selectedCohortId = previous;
    return json.str();
}

std::string BotWorldPopulationMgr::SelectRuntimeProfileForCohort(std::string const& cohortId, std::string const& name)
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_profile", cohortId);

    std::string previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    std::string result = SelectRuntimeProfile(name);
    _selectedCohortId = previous;
    return result;
}

std::string BotWorldPopulationMgr::PrepareValidationProfileForCohort(std::string const& cohortId, std::string const& name,
    std::string const& poolTag, std::vector<std::string> const& classSpecs)
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_prepare", cohortId);

    std::string previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    std::string result = PrepareValidationProfile(name, poolTag, classSpecs);
    _selectedCohortId = previous;
    return result;
}

std::string BotWorldPopulationMgr::GetStatusJsonForCohort(std::string const& cohortId) const
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_status", cohortId);

    std::string previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    std::string result = GetStatusJson();
    _selectedCohortId = previous;
    return result;
}

std::string BotWorldPopulationMgr::RequestNativeRaidReadyCheckForCohort(std::string const& cohortId)
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_readycheck", cohortId);

    std::string previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    RaidRuntime const& raid = Cohort().Raid;
    auto fail = [this, &cohortId](char const* reason)
    {
        std::ostringstream json;
        json << "{\"ok\":false,\"action\":\"botauto_readycheck\",\"cohort_id\":\""
             << JsonEscape(cohortId) << "\",\"failure_reason\":\"" << JsonEscape(reason)
             << "\",\"ready_check_action_generation\":" << Cohort().Raid.NativeReadyCheckActionGeneration
             << ",\"raid_runtime\":" << BuildRaidRuntimeJson()
             << "}";
        return json.str();
    };

    if (!Cohort().Active || !raid.Active)
    {
        std::string result = fail("raid_runtime_inactive");
        _selectedCohortId = previous;
        return result;
    }
    if (raid.ServerEpoch != _serverEpoch || raid.AttemptId == 0 || raid.AttemptId != Cohort().AttemptId)
    {
        std::string result = fail("raid_attempt_identity_mismatch");
        _selectedCohortId = previous;
        return result;
    }
    if (!raid.RosterComplete || raid.ExpectedSize == 0 || raid.ActiveSize != raid.ExpectedSize)
    {
        std::string result = fail("exact_active_raid_roster_required");
        _selectedCohortId = previous;
        return result;
    }
    if (raid.AliveSize != raid.ActiveSize)
    {
        std::string result = fail("all_raid_members_must_be_alive");
        _selectedCohortId = previous;
        return result;
    }
    if (!raid.UniqueLeases)
    {
        std::string result = fail("all_raid_leases_must_be_owned");
        _selectedCohortId = previous;
        return result;
    }
    if (!raid.RosterCompositionValid)
    {
        std::string result = fail("exact_raid_composition_required");
        _selectedCohortId = previous;
        return result;
    }
    if (!raid.DifficultyMatches)
    {
        std::string result = fail("live_raid_difficulty_mismatch");
        _selectedCohortId = previous;
        return result;
    }
    if (raid.EncounterInProgress)
    {
        std::string result = fail("encounter_in_progress");
        _selectedCohortId = previous;
        return result;
    }
    if (Cohort().Config.ValidationRouteBossRecovery == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly
        && raid.NativeRecoveryHoldActive
        && raid.NativeRecoveryRouteGeneration == Party().ValidationRouteGeneration
        && raid.NativeRecoveryNodeId == Cohort().Config.ValidationRouteNodeId
        && raid.WipeGeneration)
    {
        bool const nativeHostileResetObserved = raid.NativeHostileInactivityObserved
            && raid.NativeHostileResetGeneration > raid.NativeHostileResetGenerationAtWipe;
        bool const nativeResetObserved = raid.BossResetGeneration > raid.BossResetGenerationAtWipe
            || nativeHostileResetObserved;
        if (raid.NativeHostileActivityActive || !nativeResetObserved)
        {
            std::string result = fail(raid.NativeHostileActivityActive
                ? "native_recovery_hostile_activity"
                : "native_recovery_reset_not_observed");
            _selectedCohortId = previous;
            return result;
        }
    }

    Group* group = sGroupMgr->GetGroupByGUID(raid.GroupGuid.GetCounter());
    Player* leader = ObjectAccessor::FindPlayer(raid.LeaderGuid);
    if (!group || !leader || leader->GetGroup() != group || !group->IsLeader(leader->GetGUID()))
    {
        std::string result = fail("actual_raid_leader_group_unavailable");
        _selectedCohortId = previous;
        return result;
    }
    if (!group->isRaidGroup() || group->GetMembersCount() != raid.ExpectedSize)
    {
        std::string result = fail("native_raid_group_shape_mismatch");
        _selectedCohortId = previous;
        return result;
    }

    for (auto const& [guid, slot] : raid.RosterByGuid)
    {
        Player* member = ObjectAccessor::FindPlayer(slot.Guid);
        if (!member || !member->IsInWorld() || !member->IsAlive() || member->GetGroup() != group
            || member->GetMapId() != raid.MapId || member->GetInstanceId() != raid.InstanceId
            || !slot.Active || !slot.LeaseOwned || !LeaseOwnedByCurrentCohort(guid, slot.LeaseRoleSlot))
        {
            std::string result = fail("live_exact_raid_roster_revalidation_failed");
            _selectedCohortId = previous;
            return result;
        }
    }

    RaidRuntime& mutableRaid = Cohort().Raid;
    bool const samePendingRequest = mutableRaid.NativeReadyCheckPending
        && mutableRaid.NativeReadyCheckActionAttemptId == mutableRaid.AttemptId
        && mutableRaid.NativeReadyCheckActionWipeGeneration == mutableRaid.WipeGeneration
        && mutableRaid.NativeReadyCheckAssignmentGeneration == mutableRaid.AssignmentGeneration;
    if (!samePendingRequest && !mutableRaid.NativeReadyCheckActionObserved)
    {
        // Only the leader initiates the native ready check here.  Individual
        // bot update loops make their own stable/readiness decision and submit
        // their response through the native response opcode later.
        WorldPacket request(MSG_RAID_READY_CHECK, 0);
        leader->GetSession()->HandleRaidReadyCheckOpcode(request);
        ++mutableRaid.EvidenceSequence;
        ++mutableRaid.NativeReadyCheckActionGeneration;
        mutableRaid.NativeReadyCheckActionAttemptId = mutableRaid.AttemptId;
        mutableRaid.NativeReadyCheckActionWipeGeneration = mutableRaid.WipeGeneration;
        mutableRaid.NativeReadyCheckAssignmentGeneration = mutableRaid.AssignmentGeneration;
        mutableRaid.NativeReadyCheckActionEvidenceSequence = mutableRaid.EvidenceSequence;
        mutableRaid.NativeReadyCheckResponseCount = 0;
        mutableRaid.NativeReadyCheckResponders.clear();
        mutableRaid.NativeReadyCheckActionObserved = false;
        mutableRaid.NativeReadyCheckPending = true;
    }

    std::ostringstream json;
    json << "{\"ok\":true,\"action\":\"botauto_readycheck\",\"cohort_id\":\""
         << JsonEscape(cohortId) << "\",\"group_guid\":" << mutableRaid.GroupGuid.GetRawValue()
         << ",\"leader_guid\":" << mutableRaid.LeaderGuid.GetRawValue()
         << ",\"attempt_id\":" << mutableRaid.NativeReadyCheckActionAttemptId
         << ",\"wipe_generation\":" << mutableRaid.NativeReadyCheckActionWipeGeneration
         << ",\"ready_check_action_generation\":" << mutableRaid.NativeReadyCheckActionGeneration
         << ",\"ready_check_assignment_generation\":" << mutableRaid.NativeReadyCheckAssignmentGeneration
         << ",\"ready_check_response_count\":" << mutableRaid.NativeReadyCheckResponseCount
         << ",\"ready_check_pending\":" << (mutableRaid.NativeReadyCheckPending ? "true" : "false")
         << ",\"ready_check_complete\":" << (mutableRaid.NativeReadyCheckActionObserved ? "true" : "false")
         << ",\"raid_runtime\":" << BuildRaidRuntimeJson()
         << "}";
    _selectedCohortId = previous;
    return json.str();
}

std::string BotWorldPopulationMgr::GetBotDiagnosisJsonForCohort(std::string const& cohortId, std::string const& selector)
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_diagnose", cohortId);

    std::string previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    std::string result = GetBotDiagnosisJson(selector);
    _selectedCohortId = previous;
    return result;
}

std::string BotWorldPopulationMgr::GetBotTraceJsonForCohort(std::string const& cohortId, std::string const& selector, uint32 limit, bool delta) const
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_trace", cohortId);

    std::string previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    std::string result = GetBotTraceJson(selector, limit, delta);
    _selectedCohortId = previous;
    return result;
}

std::string BotWorldPopulationMgr::GetCombatLogJsonForCohort(std::string const& cohortId) const
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_combatlog", cohortId);

    std::string previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    std::string result = GetCombatLogJson();
    _selectedCohortId = previous;
    return result;
}

std::string BotWorldPopulationMgr::StartCombatCalibrationForCohort(std::string const& cohortId,
    std::string const& mode, std::string const& targetSpec, uint32 seed)
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_calibrate_start", cohortId);

    std::string previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    std::string result = StartCombatCalibration(mode, targetSpec, seed);
    _selectedCohortId = previous;
    return result;
}

std::string BotWorldPopulationMgr::StopCombatCalibrationForCohort(std::string const& cohortId)
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_calibrate_stop", cohortId);

    std::string previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    std::string result = StopCombatCalibration();
    _selectedCohortId = previous;
    return result;
}

std::string BotWorldPopulationMgr::GetCombatCalibrationJsonForCohort(std::string const& cohortId) const
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_calibrate_status", cohortId);

    std::string previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    std::string result = GetCombatCalibrationJson();
    _selectedCohortId = previous;
    return result;
}
