/*
 * Seeded raid lockout commands (docs/bot_raids/full_raid_parallel_shards.md,
 * package A):
 *   .botauto lockout seed <cohort> <raid> <difficulty> <boss-key,...|none>
 *   .botauto lockout status <cohort>
 *   .botauto lockout clear <cohort>
 * Each prints one JSON line with ok, instance_id, map_id, bosses_done and
 * failure_reason. `.botauto start <cohort> <profile>` then admits the cohort
 * into the seeded instance. Seeding is diagnostic assistance and never
 * certifies a natural clear.
 */

#include "Bots/BotRaidLockoutCohortContext.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Chat.h"
#include "RBAC.h"

#include <sstream>
#include <string>
#include <vector>

namespace
{
std::vector<std::string> Tokens(char const* args)
{
    std::vector<std::string> tokens;
    std::istringstream stream(args ? args : "");
    std::string token;
    while (stream >> token)
        tokens.push_back(token);
    return tokens;
}

bool Send(ChatHandler* handler, std::string const& result)
{
    bool const ok = result.find("\"ok\":true") != std::string::npos;
    if (handler)
    {
        handler->PSendSysMessage("%s", result.c_str());
        if (!ok)
            handler->SetSentErrorMessage(true);
    }
    return ok;
}

bool Usage(ChatHandler* handler, char const* action, char const* usage)
{
    return Send(handler, std::string("{\"ok\":false,\"action\":\"botauto_lockout_") + action
        + "\",\"instance_id\":0,\"map_id\":0,\"bosses_done\":[],\"failure_reason\":\"usage: " + usage + "\"}");
}

bool HandleLockoutSeed(ChatHandler* handler, char const* args)
{
    std::vector<std::string> const tokens = Tokens(args);
    if (tokens.size() != 4)
        return Usage(handler, "seed",
            ".botauto lockout seed <cohort> <raid> <10n|25n|10h|25h> <boss-key,...|none>");
    return Send(handler, BotRaidLockout::CohortContext::Seed(*sBotWorldPopulationMgr,
        tokens[0], tokens[1], tokens[2], tokens[3]));
}

bool HandleLockoutStatus(ChatHandler* handler, char const* args)
{
    std::vector<std::string> const tokens = Tokens(args);
    if (tokens.size() != 1)
        return Usage(handler, "status", ".botauto lockout status <cohort>");
    return Send(handler, BotRaidLockout::CohortContext::Status(*sBotWorldPopulationMgr, tokens[0]));
}

bool HandleLockoutClear(ChatHandler* handler, char const* args)
{
    std::vector<std::string> const tokens = Tokens(args);
    if (tokens.size() != 1)
        return Usage(handler, "clear", ".botauto lockout clear <cohort>");
    return Send(handler, BotRaidLockout::CohortContext::Clear(*sBotWorldPopulationMgr, tokens[0]));
}
}

std::vector<ChatCommand> BotAutoLockoutCommandTable()
{
    return {
        { "seed", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleLockoutSeed, "" },
        { "status", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleLockoutStatus, "" },
        { "clear", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleLockoutClear, "" },
    };
}
