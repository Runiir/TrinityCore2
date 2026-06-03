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
#include <iomanip>
#include <sstream>
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

    static std::string JsonEscape(std::string const& value)
    {
        std::ostringstream escaped;
        for (char c : value)
        {
            switch (c)
            {
                case '\\': escaped << "\\\\"; break;
                case '"': escaped << "\\\""; break;
                case '\b': escaped << "\\b"; break;
                case '\f': escaped << "\\f"; break;
                case '\n': escaped << "\\n"; break;
                case '\r': escaped << "\\r"; break;
                case '\t': escaped << "\\t"; break;
                default:
                    if (static_cast<unsigned char>(c) < 0x20)
                        escaped << "\\u" << std::hex << std::setw(4) << std::setfill('0') << uint32(static_cast<unsigned char>(c)) << std::dec;
                    else
                        escaped << c;
                    break;
            }
        }

        return escaped.str();
    }

    static void SendResult(ChatHandler* handler, bool ok, char const* action, char const* failureReason, ObjectGuid botGuid = ObjectGuid::Empty, std::string const& name = "", char const* role = "", char const* state = "", uint32 count = 0, std::string const& selector = "", char const* mode = "")
    {
        if (!handler)
            return;

        std::ostringstream json;
        json << "{\"ok\":" << (ok ? "true" : "false")
             << ",\"action\":\"" << JsonEscape(action ? action : "")
             << "\",\"bot_guid\":" << (botGuid.IsEmpty() ? 0 : botGuid.GetCounter())
             << ",\"name\":\"" << JsonEscape(name)
             << "\",\"role\":\"" << JsonEscape(role ? role : "")
             << "\",\"class_spec_tag\":\"" << JsonEscape(role ? role : "")
             << "\",\"state\":\"" << JsonEscape(state ? state : "")
             << "\",\"count\":" << count
             << ",\"selector\":\"" << JsonEscape(selector)
             << "\",\"mode\":\"" << JsonEscape(mode ? mode : "")
             << "\",\"failure_reason\":";
        if (failureReason)
            json << "\"" << JsonEscape(failureReason) << "\"";
        else
            json << "null";
        json << "}";
        handler->PSendSysMessage("%s", json.str().c_str());
    }

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
            SendResult(handler, false, "", "owner_required");
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
            SendResult(handler, false, "spawn", "invalid_usage");
            handler->SetSentErrorMessage(true);
            return false;
        }

        std::string role = NormalizeBotRole(parsed.positional[0]);
        if (!IsKnownBotRole(role) && !IsMixedBotRoleSelector(role))
        {
            SendResult(handler, false, "spawn", "unknown_role", ObjectGuid::Empty, "", role.c_str());
            handler->SetSentErrorMessage(true);
            return false;
        }

        std::string selector;
        if (parsed.positional.size() > 1)
            selector = parsed.positional[1];

        if (Player* bot = sBotMgr->Spawn(owner, role, selector))
        {
            SendResult(handler, true, "spawn", nullptr, bot->GetGUID(), bot->GetName(), sBotMgr->GetBotRoleName(bot->GetGUID()), "spawned", 1, selector);
            return true;
        }

        SendResult(handler, false, "spawn", "no_enabled_available_pool_character_or_load_failed", ObjectGuid::Empty, "", role.c_str());
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
            SendResult(handler, true, "remove", nullptr, ObjectGuid::Empty, "", "", "removed", removed, selector);
        else
            SendResult(handler, true, "remove", "no_matching_bot", ObjectGuid::Empty, "", "", "none", 0, selector);

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
        if (status.find("\"count\":0") != std::string::npos)
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
        {
            SendResult(handler, false, "record", "invalid_usage");
            handler->SetSentErrorMessage(true);
            return false;
        }

        bool enabled;
        if (stricmp(parsed.positional[0].c_str(), "on") == 0)
            enabled = true;
        else if (stricmp(parsed.positional[0].c_str(), "off") == 0)
            enabled = false;
        else
        {
            SendResult(handler, false, "record", "invalid_usage");
            handler->SetSentErrorMessage(true);
            return false;
        }

        if (!sBotMgr->SetRecording(owner, enabled))
        {
            SendResult(handler, false, "record", "no_active_bot");
            handler->SetSentErrorMessage(true);
            return false;
        }

        SendResult(handler, true, "record", nullptr, ObjectGuid::Empty, "", "", enabled ? "on" : "off");
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
            SendResult(handler, false, "partyfill", "invalid_usage");
            handler->SetSentErrorMessage(true);
            return false;
        }

        std::string role = NormalizeBotRole(parsed.positional[1]);
        if (!IsKnownBotRole(role) && !IsMixedBotRoleSelector(role))
        {
            SendResult(handler, false, "partyfill", "unknown_role", ObjectGuid::Empty, "", role.c_str());
            handler->SetSentErrorMessage(true);
            return false;
        }

        std::vector<Player*> bots = sBotMgr->PartyFill(owner, parsed.positional[0], role);
        SendResult(handler, !bots.empty(), "partyfill", bots.empty() ? "no_enabled_available_pool_character_or_load_failed" : nullptr, ObjectGuid::Empty, "", role.c_str(), bots.empty() ? "none" : "spawned", uint32(bots.size()), parsed.positional[0]);
        for (Player* bot : bots)
            SendResult(handler, true, "partyfill", nullptr, bot->GetGUID(), bot->GetName(), sBotMgr->GetBotRoleName(bot->GetGUID()), "spawned", 1, parsed.positional[0]);

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
            SendResult(handler, false, "movement", "no_matching_bot", ObjectGuid::Empty, "", "", "", 0, selector, ToString(mode));
            handler->SetSentErrorMessage(true);
            return false;
        }

        SendResult(handler, true, "movement", nullptr, ObjectGuid::Empty, "", "", "", changed, selector, ToString(mode));
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
