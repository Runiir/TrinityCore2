#ifndef TRINITY_BOT_RAID_LOCKOUT_COHORT_CONTEXT_H
#define TRINITY_BOT_RAID_LOCKOUT_COHORT_CONTEXT_H

#include "Define.h"

#include <string>

class BotWorldPopulationMgr;

// Seeded raid lockouts on cohorts (docs/bot_raids/full_raid_parallel_shards.md,
// package A). A friend of BotWorldPopulationMgr, like
// BotWorldPopulationMgrPlay::Context. Every admission hook returns early for a
// cohort without a `.botauto lockout seed` record, so a fresh-instance cohort
// (the accepted Magmaw 10N scenario) keeps its code path and bytes unchanged.
namespace BotRaidLockout
{
struct CohortContext
{
    // `.botauto lockout seed|status|clear <cohort> ...`; one JSON line each.
    static std::string Seed(BotWorldPopulationMgr& mgr, std::string const& cohortId,
        std::string const& raid, std::string const& difficulty, std::string const& bosses);
    static std::string Status(BotWorldPopulationMgr& mgr, std::string const& cohortId);
    static std::string Clear(BotWorldPopulationMgr& mgr, std::string const& cohortId);

    // Admission hooks (BotWorldPopulationMgrValidationAdmission.cpp), called
    // while the admitting cohort is scoped. Each returns "" or a failure.
    // Arm: before the first spawn, readback of the idle lockout and arming
    // of the planned leader, whose seed group then binds to it.
    static std::string ArmAdmission(BotWorldPopulationMgr& mgr, uint32 routeMapId, uint32 leaderGuid);
    // Verify: after every member entered and before the batch is sealed
    // (before any bot acts), instance id, group bind and live boss states.
    static std::string VerifyAdmission(BotWorldPopulationMgr& mgr);
    // Admission rollback: releases the seed group's bind (in memory, and a
    // synchronous delete of its group_instance row) before the bots leave,
    // then disarms the leader.
    static void DisarmAdmission(BotWorldPopulationMgr& mgr);

    // The instance whose binds ResetValidationBotPool keeps; 0 without one.
    static uint32 ResetKeepInstanceId(BotWorldPopulationMgr const& mgr);

    // `,"seeded_lockout":{...}` for the cohort status JSON; "" without one.
    static std::string StatusFieldsJson(BotWorldPopulationMgr const& mgr);
};
}

#endif
