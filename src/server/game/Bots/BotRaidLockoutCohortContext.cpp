#include "Bots/BotRaidLockoutCohortContext.h"

#include "Bots/BotRaidLockoutSeeder.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Group.h"
#include "InstanceSaveMgr.h"
#include "Log.h"
#include "Player.h"

#include <sstream>

namespace BotRaidLockout
{
namespace
{
std::string Result(char const* action, std::string const& cohortId, bool ok,
    std::string const& failure, std::string const& fields)
{
    std::ostringstream json;
    json << "{\"ok\":" << (ok ? "true" : "false")
         << ",\"action\":\"botauto_lockout_" << action << "\""
         << ",\"cohort_id\":\"" << JsonEscape(cohortId) << "\"";
    // The contract fields are always present, zero/empty without a lockout.
    if (fields.empty())
        json << ",\"instance_id\":0,\"map_id\":0,\"bosses_done\":[]";
    json << fields
         << ",\"failure_reason\":" << (ok ? std::string("null") : "\"" + JsonEscape(failure) + "\"")
         << "}";
    return json.str();
}

template <typename Cohort>
std::string CohortFields(Cohort const* cohort)
{
    std::ostringstream json;
    json << ",\"cohort_exists\":" << (cohort ? "true" : "false")
         << ",\"cohort_active\":" << (cohort && cohort->Active ? "true" : "false");
    if (cohort && cohort->SeededLockout.Attached)
        json << ",\"cohort_attempt_id\":" << cohort->SeededLockout.AttemptId
             << ",\"cohort_admitted\":" << (cohort->SeededLockout.Admitted ? "true" : "false")
             << ",\"cohort_admitted_instance_id\":" << cohort->SeededLockout.InstanceId
             << ",\"cohort_admission_failure\":\""
             << JsonEscape(cohort->SeededLockout.AdmissionFailure) << "\"";
    return json.str();
}

std::string ReadbackState(Readback const& readback)
{
    if (!readback.Failure.empty())
        return "broken";
    return readback.LockoutIntact ? "intact" : "progressed";
}
}

std::string CohortContext::Seed(BotWorldPopulationMgr& mgr, std::string const& cohortId,
    std::string const& raid, std::string const& difficulty, std::string const& bosses)
{
    BotWorldPopulationMgr::CohortRuntime const* cohort = mgr.FindCohort(cohortId);
    std::string const cohortFields = CohortFields(cohort);
    if (!IsValidCohortId(cohortId))
        return Result("seed", cohortId, false, "invalid_cohort_id", "");
    if (cohort && cohort->Active)
        return Result("seed", cohortId, false, "cohort_active", "");
    LockoutRecord existing;
    if (Registry::Find(cohortId, existing))
        return Result("seed", cohortId, false, "lockout_exists",
            RecordFieldsJson(existing) + cohortFields);

    LockoutRecord record;
    Readback readback;
    std::string const failure = SeedLockout(cohortId, raid, difficulty, bosses, record, readback);
    if (!failure.empty())
    {
        TC_LOG_ERROR("server", "BotRaidLockout seed failed cohort=%s raid=%s difficulty=%s bosses=%s reason=%s",
            cohortId.c_str(), raid.c_str(), difficulty.c_str(), bosses.c_str(), failure.c_str());
        // Everything was rolled back: the contract fields stay zero and the
        // readback (when one ran) explains the refusal.
        std::string fields = ",\"instance_id\":0,\"map_id\":0,\"bosses_done\":[]";
        if (record.InstanceId)
            fields += ",\"rolled_back_instance_id\":" + std::to_string(record.InstanceId)
                + ",\"readback\":" + ReadbackJson(readback);
        return Result("seed", cohortId, false, failure, fields + cohortFields);
    }
    return Result("seed", cohortId, true, "", RecordFieldsJson(record)
        + ",\"lockout_state\":\"" + ReadbackState(readback) + "\""
        + ",\"readback\":" + ReadbackJson(readback) + cohortFields);
}

std::string CohortContext::Status(BotWorldPopulationMgr& mgr, std::string const& cohortId)
{
    BotWorldPopulationMgr::CohortRuntime const* cohort = mgr.FindCohort(cohortId);
    LockoutRecord record;
    if (!Registry::Find(cohortId, record))
        return Result("status", cohortId, false, "no_lockout", "");
    Readback const readback = ReadbackLockout(record);
    return Result("status", cohortId, readback.Failure.empty(), readback.Failure,
        RecordFieldsJson(record)
        + ",\"lockout_state\":\"" + ReadbackState(readback) + "\""
        + ",\"readback\":" + ReadbackJson(readback) + CohortFields(cohort));
}

std::string CohortContext::Clear(BotWorldPopulationMgr& mgr, std::string const& cohortId)
{
    BotWorldPopulationMgr::CohortRuntime* cohort = mgr.FindCohort(cohortId);
    LockoutRecord record;
    if (!Registry::Find(cohortId, record))
        return Result("clear", cohortId, true, "", ",\"instance_id\":0,\"map_id\":0,\"bosses_done\":[],\"cleared\":false");
    if (cohort && cohort->Active)
        return Result("clear", cohortId, false, "cohort_active", RecordFieldsJson(record) + CohortFields(cohort));
    std::string const failure = ClearLockout(record);
    if (!failure.empty())
        return Result("clear", cohortId, false, failure, RecordFieldsJson(record) + CohortFields(cohort));
    Registry::Erase(cohortId);
    if (cohort)
        cohort->SeededLockout = BotWorldPopulationMgr::SeededLockoutRuntime();
    return Result("clear", cohortId, true, "", RecordFieldsJson(record) + ",\"cleared\":true");
}

std::string CohortContext::ArmAdmission(BotWorldPopulationMgr& mgr, uint32 routeMapId, uint32 leaderGuid)
{
    BotWorldPopulationMgr::CohortRuntime& cohort = mgr.Cohort();
    cohort.SeededLockout = BotWorldPopulationMgr::SeededLockoutRuntime();
    LockoutRecord record;
    if (!Registry::Find(cohort.Id, record))
        return "";

    std::string failure;
    if (cohort.Purpose == CohortPurpose::Play)
        failure = "seeded_lockout_play_unsupported";
    else if (record.MapId != routeMapId)
        failure = "seeded_lockout_map_mismatch";
    else if (record.Difficulty != cohort.Config.RaidDifficulty)
        failure = "seeded_lockout_difficulty_mismatch";
    else if (!leaderGuid)
        failure = "seeded_lockout_leader_missing";
    if (failure.empty())
    {
        Readback const readback = ReadbackLockout(record);
        if (!readback.Failure.empty())
            failure = "seeded_lockout_readback:" + readback.Failure;
        else if (!readback.LockoutIntact)
            // A previous attempt killed more bosses: seed a new lockout.
            failure = "seeded_lockout_progressed:" + (readback.ExtraDone.empty()
                ? std::string("state") : readback.ExtraDone.front());
        else if (readback.MapPlayers)
            failure = "seeded_lockout_map_occupied";
        else if (readback.SaveGroupBinds)
            failure = "seeded_lockout_group_already_bound";
        else if (!EnsureSaveLoaded(record))
            failure = "seeded_lockout_save_unavailable";
        else if (!Registry::Arm(cohort.Id, leaderGuid))
            failure = "seeded_lockout_arm_failed";
    }

    BotWorldPopulationMgr::SeededLockoutRuntime& lockout = cohort.SeededLockout;
    lockout.Attached = true;
    lockout.DiagnosticOnlyAssistance = true;
    lockout.Raid = record.Raid;
    lockout.InstanceId = record.InstanceId;
    lockout.MapId = record.MapId;
    lockout.Difficulty = record.Difficulty;
    lockout.BossesDone = record.BossesDone;
    lockout.CompletedEncounterMask = record.CompletedEncounterMask;
    lockout.AttemptId = cohort.AttemptId;
    lockout.AdmissionFailure = failure;
    if (failure.empty())
        TC_LOG_INFO("server", "BotRaidLockout admission armed cohort=%s attempt=%llu leader=%u instance=%u map=%u diagnostic_only_assistance=1",
            cohort.Id.c_str(), static_cast<unsigned long long>(cohort.AttemptId), leaderGuid,
            record.InstanceId, record.MapId);
    else
        TC_LOG_ERROR("server", "BotRaidLockout admission refused cohort=%s instance=%u reason=%s",
            cohort.Id.c_str(), record.InstanceId, failure.c_str());
    return failure;
}

std::string CohortContext::VerifyAdmission(BotWorldPopulationMgr& mgr)
{
    BotWorldPopulationMgr::CohortRuntime& cohort = mgr.Cohort();
    BotWorldPopulationMgr::SeededLockoutRuntime& lockout = cohort.SeededLockout;
    if (!lockout.Attached)
        return "";

    auto fail = [&lockout](std::string const& reason)
    {
        lockout.AdmissionFailure = reason;
        return reason;
    };
    LockoutRecord record;
    if (!Registry::Find(cohort.Id, record) || record.InstanceId != lockout.InstanceId)
        return fail("seeded_lockout_missing_at_admission");
    if (!record.BoundGroupGuid)
        return fail("seeded_lockout_group_not_bound");

    for (auto const& state : mgr.Party().Bots)
    {
        Player* bot = mgr.GetLoadedBot(state);
        std::string const guid = std::to_string(state.Guid.GetCounter());
        if (!bot || bot->GetMapId() != record.MapId || bot->GetInstanceId() != record.InstanceId)
            return fail("seeded_lockout_instance_mismatch:" + guid);
        Group* group = bot->GetGroup();
        if (!group || group->GetGUID().GetCounter() != record.BoundGroupGuid)
            return fail("seeded_lockout_group_mismatch:" + guid);
        InstanceGroupBind* bind = group->GetBoundInstance(Difficulty(record.Difficulty), record.MapId);
        if (!bind || !bind->perm || !bind->save || bind->save->GetInstanceId() != record.InstanceId)
            return fail("seeded_lockout_group_bind_mismatch");
    }

    Readback const readback = ReadbackLockout(record);
    if (readback.Source != "live_instance_script")
        return fail("seeded_lockout_live_readback_missing");
    if (!readback.Failure.empty())
        return fail("seeded_lockout_readback:" + readback.Failure);
    if (!readback.LockoutIntact)
        return fail("seeded_lockout_readback_mismatch");

    Registry::Disarm(cohort.Id);
    lockout.Admitted = true;
    lockout.BoundGroupGuid = record.BoundGroupGuid;
    lockout.AdmittedBossStates = readback.BossStates;
    lockout.AdmissionFailure.clear();
    TC_LOG_INFO("server", "BotRaidLockout admission verified cohort=%s attempt=%llu instance=%u group=%u bots=%zu diagnostic_only_assistance=1",
        cohort.Id.c_str(), static_cast<unsigned long long>(cohort.AttemptId), record.InstanceId,
        record.BoundGroupGuid, mgr.Party().Bots.size());
    return "";
}

void CohortContext::DisarmAdmission(BotWorldPopulationMgr& mgr)
{
    BotWorldPopulationMgr::CohortRuntime& cohort = mgr.Cohort();
    if (!cohort.SeededLockout.Attached)
        return;
    Registry::Disarm(cohort.Id);
    cohort.SeededLockout.Admitted = false;
}

uint32 CohortContext::ResetKeepInstanceId(BotWorldPopulationMgr const& mgr)
{
    LockoutRecord record;
    return Registry::Find(mgr.Cohort().Id, record) ? record.InstanceId : 0;
}

std::string CohortContext::StatusFieldsJson(BotWorldPopulationMgr const& mgr)
{
    BotWorldPopulationMgr::SeededLockoutRuntime const& lockout = mgr.Cohort().SeededLockout;
    if (!lockout.Attached)
        return "";
    std::ostringstream json;
    json << ",\"seeded_lockout\":{\"raid\":\"" << JsonEscape(lockout.Raid) << "\""
         << ",\"instance_id\":" << lockout.InstanceId
         << ",\"map_id\":" << lockout.MapId
         << ",\"difficulty\":\"" << DifficultyToken(lockout.Difficulty) << "\""
         << ",\"bosses_done\":" << JsonStringArray(lockout.BossesDone)
         << ",\"completed_encounters_mask\":" << lockout.CompletedEncounterMask
         << ",\"diagnostic_only_assistance\":" << (lockout.DiagnosticOnlyAssistance ? "true" : "false")
         << ",\"attempt_id\":" << lockout.AttemptId
         << ",\"admitted\":" << (lockout.Admitted ? "true" : "false")
         << ",\"bound_group_guid\":" << lockout.BoundGroupGuid
         << ",\"admitted_boss_states\":" << JsonNumberArray(lockout.AdmittedBossStates)
         << ",\"admission_failure\":\"" << JsonEscape(lockout.AdmissionFailure) << "\"}";
    return json.str();
}
}
