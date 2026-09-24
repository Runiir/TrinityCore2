/*
 * Human play mode commands: `.botauto play fill|pull|go|stop|status`
 * (docs/bot_raids/human_play_mode.md). In game they act for the invoking
 * player; from the console `fill` names the raid leader. The player script
 * turns the leader's raid-chat pull calls ("pull 10") into pull timers.
 */

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrPlay.h"
#include "Chat.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "RBAC.h"
#include "ScriptMgr.h"
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

// `.botauto play pull` (10 s), `.botauto play pull 5`, `.botauto play pull cancel`.
bool HandlePlayPull(ChatHandler* handler, char const* args)
{
    std::string argument = args ? args : "";
    argument.erase(0, argument.find_first_not_of(' '));
    argument.erase(argument.find_last_not_of(' ') + 1);
    bool const cancel = argument == "cancel";
    uint32 seconds = 10;
    if (!argument.empty() && !cancel)
    {
        if (argument.find_first_not_of("0123456789") != std::string::npos || argument.size() > 4)
            return Send(handler, "{\"ok\":false,\"action\":\"botauto_play_pull\","
                "\"failure_reason\":\"usage: .botauto play pull [seconds|cancel]\"}");
        seconds = uint32(std::stoul(argument));
    }
    return Send(handler, BotWorldPopulationMgrPlay::Context::Pull(*sBotWorldPopulationMgr,
        InvokerOrNamed(handler, nullptr), cancel, seconds, "command"));
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
        { "pull", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandlePlayPull, "" },
        { "go", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandlePlayGo, "" },
        { "stop", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandlePlayStop, "" },
        { "status", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandlePlayStatus, "" },
    };
}

class botauto_play_playerscript : public PlayerScript
{
public:
    botauto_play_playerscript() : PlayerScript("botauto_play_playerscript") { }

    using PlayerScript::OnChat;
    void OnChat(Player* player, uint32 type, uint32 /*lang*/, std::string& msg, Group* group) override
    {
        BotWorldPopulationMgrPlay::OnGroupChat(player, type, msg, group);
    }
};

void RegisterBotAutoPlayScripts()
{
    new botauto_play_playerscript();
}
