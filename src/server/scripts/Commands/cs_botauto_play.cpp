/*
 * Human play mode commands: `.botauto play fill|go|stop|status`
 * (docs/bot_raids/human_play_mode.md). In game they act for the invoking
 * player; from the console `fill` names the raid leader.
 */

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrPlay.h"
#include "Chat.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "RBAC.h"
#include "WorldSession.h"

#include <string>
#include <vector>

namespace
{
Player* InvokerOrNamed(ChatHandler* handler, char const* args)
{
    std::string name = args ? args : "";
    name.erase(0, name.find_first_not_of(' '));
    name.erase(name.find_last_not_of(' ') + 1);
    if (!name.empty())
    {
        if (!normalizePlayerName(name))
            return nullptr;
        return ObjectAccessor::FindConnectedPlayerByName(name);
    }
    WorldSession* session = handler ? handler->GetSession() : nullptr;
    return session ? session->GetPlayer() : nullptr;
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

bool HandlePlayFill(ChatHandler* handler, char const* args)
{
    return Send(handler, BotWorldPopulationMgrPlay::Context::Fill(
        *sBotWorldPopulationMgr, InvokerOrNamed(handler, args)));
}

bool HandlePlayGo(ChatHandler* handler, char const* /*args*/)
{
    return Send(handler, BotWorldPopulationMgrPlay::Context::Go(
        *sBotWorldPopulationMgr, InvokerOrNamed(handler, nullptr)));
}

bool HandlePlayStop(ChatHandler* handler, char const* /*args*/)
{
    return Send(handler, BotWorldPopulationMgrPlay::Context::Stop(
        *sBotWorldPopulationMgr, InvokerOrNamed(handler, nullptr)));
}

bool HandlePlayStatus(ChatHandler* handler, char const* /*args*/)
{
    return Send(handler, BotWorldPopulationMgrPlay::Context::Status(*sBotWorldPopulationMgr));
}
}

std::vector<ChatCommand> BotAutoPlayCommandTable()
{
    return {
        { "fill", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandlePlayFill, "" },
        { "go", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandlePlayGo, "" },
        { "stop", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandlePlayStop, "" },
        { "status", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandlePlayStatus, "" },
    };
}
