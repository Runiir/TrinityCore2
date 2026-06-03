/*
 * Local player bot commands.
 */

#include "ScriptMgr.h"
#include "Bots/BotMgr.h"
#include "Bots/BotTypes.h"
#include "Chat.h"
#include "Player.h"
#include "RBAC.h"
#include "WorldSession.h"
#include <string>
#include <vector>

class playerbot_commandscript : public CommandScript
{
public:
    playerbot_commandscript() : CommandScript("playerbot_commandscript") { }

    std::vector<ChatCommand> GetCommands() const override
    {
        static std::vector<ChatCommand> playerBotCommandTable =
        {
            { "spawn",  rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleSpawnCommand,  "" },
            { "add",    rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAddCommand,    "" },
            { "remove", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleRemoveCommand, "" },
            { "follow", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleFollowCommand, "" },
            { "stay",   rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleStayCommand,   "" },
            { "stop",   rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleStopCommand,   "" },
            { "status", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleStatusCommand, "" },
            { "record", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleRecordCommand, "" },
            { "partyfill", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandlePartyFillCommand, "" },
        };

        static std::vector<ChatCommand> commandTable =
        {
            { "playerbot", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, nullptr, "", playerBotCommandTable },
        };

        return commandTable;
    }

private:
    struct CommandArgs
    {
        std::vector<std::string> positional;
        std::string ownerSelector;
    };

    static CommandArgs ParseCommandArgs(char const* args)
    {
        CommandArgs parsed;
        std::string input = args ? args : "";
        std::vector<char> buffer(input.begin(), input.end());
        buffer.push_back('\0');

        for (char* token = strtok(buffer.data(), " "); token; token = strtok(nullptr, " "))
        {
            if (stricmp(token, "owner") == 0)
            {
                if (char* owner = strtok(nullptr, " "))
                    parsed.ownerSelector = owner;
                continue;
            }

            parsed.positional.emplace_back(token);
        }

        return parsed;
    }

    static Player* GetOwner(ChatHandler* handler)
    {
        if (!handler || !handler->GetSession() || !handler->GetSession()->GetPlayer())
            return nullptr;

        return handler->GetSession()->GetPlayer();
    }

    static Player* GetOwner(ChatHandler* handler, std::string const& ownerSelector)
    {
        if (!ownerSelector.empty())
            return sBotMgr->GetOrLoadHeadlessOwner(ownerSelector);

        return GetOwner(handler);
    }

    static bool RequireOwner(ChatHandler* handler, std::string const& ownerSelector = "")
    {
        if (GetOwner(handler, ownerSelector))
            return true;

        if (handler)
        {
            handler->PSendSysMessage("playerbot result=fail reason=owner_required usage=\"playerbot <command> ... owner <name|guid>\"");
            handler->SetSentErrorMessage(true);
        }

        return false;
    }

    static bool HandleSpawnCommand(ChatHandler* handler, char const* args)
    {
        CommandArgs parsed = ParseCommandArgs(args);
        Player* owner = GetOwner(handler, parsed.ownerSelector);
        if (!owner)
            return RequireOwner(handler, parsed.ownerSelector);

        if (parsed.positional.empty())
        {
            handler->PSendSysMessage("Usage: .playerbot spawn <role> [name|guid] [owner name|guid]");
            return false;
        }

        std::string role = NormalizeBotRole(parsed.positional[0]);
        if (!IsKnownBotRole(role) && !IsMixedBotRoleSelector(role))
        {
            handler->PSendSysMessage("Usage: .playerbot spawn <holy_paladin|warrior|hunter|rogue|priest|death_knight|shaman|mage|warlock|druid|mixed> [name|guid] [owner name|guid]");
            return false;
        }

        std::string selector;
        if (parsed.positional.size() > 1)
            selector = parsed.positional[1];

        if (Player* bot = sBotMgr->Spawn(owner, role, selector))
        {
            handler->PSendSysMessage("playerbot result=ok action=spawn guid=%u name=%s role=%s state=online", bot->GetGUID().GetCounter(), bot->GetName().c_str(), sBotMgr->GetBotRoleName(bot->GetGUID()));
            return true;
        }

        handler->PSendSysMessage("playerbot result=fail action=spawn role=%s reason=no_enabled_available_pool_character_or_load_failed", role.c_str());
        handler->SetSentErrorMessage(true);
        return false;
    }

    static bool HandleAddCommand(ChatHandler* handler, char const* args)
    {
        std::string spawnArgs = "holy_paladin";
        if (args && *args)
        {
            spawnArgs += " ";
            spawnArgs += args;
        }

        return HandleSpawnCommand(handler, spawnArgs.c_str());
    }

    static bool HandleRemoveCommand(ChatHandler* handler, char const* args)
    {
        CommandArgs parsed = ParseCommandArgs(args);
        Player* owner = GetOwner(handler, parsed.ownerSelector);
        if (!owner)
            return RequireOwner(handler, parsed.ownerSelector);

        std::string selector = parsed.positional.empty() ? "all" : parsed.positional[0];
        uint32 removed = sBotMgr->Remove(owner, selector);
        if (removed)
            handler->PSendSysMessage("playerbot result=ok action=remove selector=%s count=%u", selector.c_str(), removed);
        else
            handler->PSendSysMessage("playerbot result=ok action=remove selector=%s count=0 reason=no_matching_bot", selector.c_str());

        sBotMgr->ReleaseHeadlessOwnerIfIdle(owner);
        return true;
    }

    static bool HandleFollowCommand(ChatHandler* handler, char const* args)
    {
        return SetMovement(handler, BotMovementMode::Follow, args);
    }

    static bool HandleStayCommand(ChatHandler* handler, char const* args)
    {
        return SetMovement(handler, BotMovementMode::Stay, args);
    }

    static bool HandleStopCommand(ChatHandler* handler, char const* args)
    {
        return SetMovement(handler, BotMovementMode::Stop, args);
    }

    static bool HandleStatusCommand(ChatHandler* handler, char const* args)
    {
        CommandArgs parsed = ParseCommandArgs(args);
        Player* owner = GetOwner(handler, parsed.ownerSelector);
        if (!owner)
            return RequireOwner(handler, parsed.ownerSelector);

        std::string status = sBotMgr->GetStatus(owner);
        handler->PSendSysMessage("%s", status.c_str());
        if (status.find("state=none") != std::string::npos)
            sBotMgr->ReleaseHeadlessOwnerIfIdle(owner);
        return true;
    }

    static bool HandleRecordCommand(ChatHandler* handler, char const* args)
    {
        CommandArgs parsed = ParseCommandArgs(args);
        Player* owner = GetOwner(handler, parsed.ownerSelector);
        if (!owner)
            return RequireOwner(handler, parsed.ownerSelector);

        if (parsed.positional.empty())
            return false;

        bool enabled;
        if (stricmp(parsed.positional[0].c_str(), "on") == 0)
            enabled = true;
        else if (stricmp(parsed.positional[0].c_str(), "off") == 0)
            enabled = false;
        else
            return false;

        if (!sBotMgr->SetRecording(owner, enabled))
        {
            handler->PSendSysMessage("playerbot result=fail action=record reason=no_active_bot");
            handler->SetSentErrorMessage(true);
            return false;
        }

        handler->PSendSysMessage("playerbot result=ok action=record state=%s", enabled ? "on" : "off");
        return true;
    }

    static bool HandlePartyFillCommand(ChatHandler* handler, char const* args)
    {
        CommandArgs parsed = ParseCommandArgs(args);
        Player* owner = GetOwner(handler, parsed.ownerSelector);
        if (!owner)
            return RequireOwner(handler, parsed.ownerSelector);

        if (parsed.positional.size() < 2)
        {
            handler->PSendSysMessage("Usage: .playerbot partyfill dungeon5 <holy_paladin|warrior|hunter|rogue|priest|death_knight|shaman|mage|warlock|druid|mixed> [owner name|guid]");
            return false;
        }

        std::string role = NormalizeBotRole(parsed.positional[1]);
        if (!IsKnownBotRole(role) && !IsMixedBotRoleSelector(role))
        {
            handler->PSendSysMessage("Usage: .playerbot partyfill dungeon5 <holy_paladin|warrior|hunter|rogue|priest|death_knight|shaman|mage|warlock|druid|mixed> [owner name|guid]");
            return false;
        }

        std::vector<Player*> bots = sBotMgr->PartyFill(owner, parsed.positional[0], role);
        handler->PSendSysMessage("playerbot result=%s action=partyfill party=%s role=%s count=%u", bots.empty() ? "fail" : "ok", parsed.positional[0].c_str(), role.c_str(), uint32(bots.size()));
        for (Player* bot : bots)
            handler->PSendSysMessage("playerbot result=ok action=partyfill guid=%u name=%s role=%s state=online", bot->GetGUID().GetCounter(), bot->GetName().c_str(), sBotMgr->GetBotRoleName(bot->GetGUID()));

        if (bots.empty())
            handler->SetSentErrorMessage(true);

        return !bots.empty();
    }

    static bool SetMovement(ChatHandler* handler, BotMovementMode mode, char const* args)
    {
        CommandArgs parsed = ParseCommandArgs(args);
        Player* owner = GetOwner(handler, parsed.ownerSelector);
        if (!owner)
            return RequireOwner(handler, parsed.ownerSelector);

        std::string selector = parsed.positional.empty() ? "all" : parsed.positional[0];
        uint32 changed = sBotMgr->SetMovement(owner, mode, selector);
        if (!changed)
        {
            handler->PSendSysMessage("playerbot result=fail action=movement selector=%s reason=no_matching_bot", selector.c_str());
            handler->SetSentErrorMessage(true);
            return false;
        }

        handler->PSendSysMessage("playerbot result=ok action=movement selector=%s mode=%s count=%u", selector.c_str(), ToString(mode), changed);
        return true;
    }
};

class playerbot_playerscript : public PlayerScript
{
public:
    playerbot_playerscript() : PlayerScript("playerbot_playerscript") { }

    void OnLogout(Player* player) override
    {
        sBotMgr->OnOwnerLogout(player);
    }
};

class playerbot_unitscript : public UnitScript
{
public:
    playerbot_unitscript() : UnitScript("playerbot_unitscript") { }

    void OnDamage(Unit* attacker, Unit* victim, uint32& damage) override
    {
        sBotMgr->OnDamage(attacker, victim, damage);
    }

    void OnHeal(Unit* healer, Unit* receiver, uint32& gain) override
    {
        sBotMgr->OnHeal(healer, receiver, gain);
    }
};

class playerbot_groupscript : public GroupScript
{
public:
    playerbot_groupscript() : GroupScript("playerbot_groupscript") { }

    void OnRemoveMember(Group* group, ObjectGuid guid, RemoveMethod /*method*/, ObjectGuid /*kicker*/, char const* /*reason*/) override
    {
        sBotMgr->OnGroupRemoveMember(group, guid);
    }

    void OnDisband(Group* group) override
    {
        sBotMgr->OnGroupDisband(group);
    }
};

class playerbot_worldscript : public WorldScript
{
public:
    playerbot_worldscript() : WorldScript("playerbot_worldscript") { }

    void OnStartup() override
    {
        sBotMgr->ResetPoolUseState();
    }

    void OnShutdown() override
    {
        sBotMgr->RemoveAll();
    }
};

void AddSC_healerbot_commandscript()
{
    new playerbot_commandscript();
    new playerbot_playerscript();
    new playerbot_unitscript();
    new playerbot_groupscript();
    new playerbot_worldscript();
}
