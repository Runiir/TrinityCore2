/*
 * Local player bot commands.
 */

#include "ScriptMgr.h"
#include "Bots/BotMgr.h"
#include "Bots/BotTypes.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Chat.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Quests/QuestDef.h"
#include "RBAC.h"
#include "WorldSession.h"
#include <algorithm>
#include <cstdlib>
#include <iomanip>
#include <map>
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
            { "move_to", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleMoveToCommand, "" },
            { "return_to_group", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleReturnToGroupCommand, "" },
            { "move_safe", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleMoveSafeCommand, "" },
            { "unstuck", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleUnstuckCommand, "" },
            { "combat_target", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleCombatTargetCommand, "" },
            { "combat_clear", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleCombatClearCommand, "" },
            { "loot", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleLootCommand, "" },
            { "quest", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleQuestCommand, "" },
            { "profession_score", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleProfessionScoreCommand, "" },
            { "craft", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleCraftCommand, "" },
            { "vendor_trash", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleVendorTrashCommand, "" },
            { "repair", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleRepairCommand, "" },
            { "gear_eval", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleGearEvalCommand, "" },
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

    static bool HandleReturnToGroupCommand(ChatHandler* handler, char const* args)
    {
        return SetMovement(handler, BotMovementMode::ReturnToGroup, args);
    }

    static bool HandleMoveSafeCommand(ChatHandler* handler, char const* args)
    {
        return SetMovement(handler, BotMovementMode::MoveSafe, args);
    }

    static bool HandleUnstuckCommand(ChatHandler* handler, char const* args)
    {
        return SetMovement(handler, BotMovementMode::Unstuck, args);
    }

    static bool HandleCombatTargetCommand(ChatHandler* handler, char const* args)
    {
        CommandArgs parsed = ParseCommandArgs(args);
        Player* owner = GetOwner(handler, parsed.ownerSelector);
        if (!owner)
            return RequireOwner(handler, parsed.ownerSelector);

        std::string targetSelector = parsed.positional.empty() ? "nearest" : parsed.positional[0];
        std::string botSelector = parsed.positional.size() > 1 ? parsed.positional[1] : "all";
        uint32 changed = sBotMgr->SetCombatTarget(owner, targetSelector, botSelector);
        if (!changed)
        {
            SendResult(handler, false, "combat_target", "no_hostile_target_or_matching_bot", ObjectGuid::Empty, "", "", "", 0, botSelector, targetSelector.c_str());
            handler->SetSentErrorMessage(true);
            return false;
        }

        SendResult(handler, true, "combat_target", nullptr, ObjectGuid::Empty, "", "", "targeted", changed, botSelector, targetSelector.c_str());
        return true;
    }

    static bool HandleCombatClearCommand(ChatHandler* handler, char const* args)
    {
        CommandArgs parsed = ParseCommandArgs(args);
        Player* owner = GetOwner(handler, parsed.ownerSelector);
        if (!owner)
            return RequireOwner(handler, parsed.ownerSelector);

        std::string selector = parsed.positional.empty() ? "all" : parsed.positional[0];
        uint32 changed = sBotMgr->ClearCombatTarget(owner, selector);
        SendResult(handler, changed > 0, "combat_clear", changed ? nullptr : "no_matching_bot", ObjectGuid::Empty, "", "", "cleared", changed, selector);
        if (!changed)
            handler->SetSentErrorMessage(true);
        return changed > 0;
    }

    static bool HandleLootCommand(ChatHandler* handler, char const* args)
    {
        return HandleCombatTargetCommand(handler, args && *args ? args : "selected");
    }

    static std::string QuestStatusName(QuestStatus status)
    {
        switch (status)
        {
            case QUEST_STATUS_NONE: return "none";
            case QUEST_STATUS_COMPLETE: return "complete";
            case QUEST_STATUS_INCOMPLETE: return "incomplete";
            case QUEST_STATUS_FAILED: return "failed";
            case QUEST_STATUS_REWARDED: return "rewarded";
            default: return "unknown";
        }
    }

    static void SendQuestResult(ChatHandler* handler, bool ok, char const* action, uint32 questId, Quest const* quest, Player* player, char const* failureReason = nullptr)
    {
        if (!handler)
            return;

        QuestStatus status = player ? player->GetQuestStatus(questId) : QUEST_STATUS_NONE;
        uint16 slot = player ? player->FindQuestSlot(questId) : MAX_QUEST_LOG_SIZE;
        uint32 objectiveIndex = 0;
        std::string objectiveType = "none";
        int32 targetEntry = 0;
        uint32 progressCurrent = 0;
        uint32 progressRequired = 1;
        if (quest)
        {
            for (uint32 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
            {
                if (quest->RequiredNpcOrGoCount[i])
                {
                    objectiveIndex = i;
                    targetEntry = quest->RequiredNpcOrGo[i] < 0 ? -quest->RequiredNpcOrGo[i] : quest->RequiredNpcOrGo[i];
                    objectiveType = quest->RequiredNpcOrGo[i] < 0 ? "interact_gameobject" : "kill";
                    progressRequired = quest->RequiredNpcOrGoCount[i];
                    progressCurrent = slot < MAX_QUEST_LOG_SIZE ? player->GetQuestSlotCounter(slot, i) : 0;
                    break;
                }
            }
            if (objectiveType == "none")
            {
                for (uint32 i = 0; i < QUEST_ITEM_OBJECTIVES_COUNT; ++i)
                {
                    if (quest->RequiredItemCount[i])
                    {
                        objectiveIndex = i;
                        targetEntry = quest->RequiredItemId[i];
                        objectiveType = "collect";
                        progressRequired = quest->RequiredItemCount[i];
                        progressCurrent = player ? std::min<uint32>(player->GetItemCount(quest->RequiredItemId[i], true), progressRequired) : 0;
                        break;
                    }
                }
            }
        }

        std::ostringstream json;
        json << "{\"ok\":" << (ok ? "true" : "false")
             << ",\"action\":\"" << JsonEscape(action ? action : "")
             << "\",\"quest\":{\"quest_id\":" << questId
             << ",\"objective_index\":" << objectiveIndex
             << ",\"objective_type\":\"" << objectiveType
             << "\",\"target_entry\":" << targetEntry
             << ",\"progress_current\":" << progressCurrent
             << ",\"progress_required\":" << progressRequired
             << ",\"status\":\"" << QuestStatusName(status)
             << "\",\"objective_area\":{\"map_id\":" << (player ? player->GetMapId() : 0)
             << ",\"zone_id\":" << (player ? player->GetZoneId() : 0)
             << ",\"center\":[" << (player ? player->GetPositionX() : 0.0f)
             << "," << (player ? player->GetPositionY() : 0.0f)
             << "," << (player ? player->GetPositionZ() : 0.0f)
             << "],\"radius\":80.0}}"
             << ",\"failure_reason\":";
        if (failureReason)
            json << "\"" << JsonEscape(failureReason) << "\"";
        else
            json << "null";
        json << "}";
        handler->PSendSysMessage("%s", json.str().c_str());
    }

    static bool HandleQuestCommand(ChatHandler* handler, char const* args)
    {
        CommandArgs parsed = ParseCommandArgs(args);
        Player* owner = GetOwner(handler, parsed.ownerSelector);
        if (!owner)
            return RequireOwner(handler, parsed.ownerSelector);

        if (parsed.positional.size() < 2)
        {
            SendResult(handler, false, "quest", "invalid_usage");
            handler->SetSentErrorMessage(true);
            return false;
        }

        std::string action = parsed.positional[0];
        uint32 questId = uint32(std::strtoul(parsed.positional[1].c_str(), nullptr, 10));
        Quest const* quest = sObjectMgr->GetQuestTemplate(questId);
        if (!quest)
        {
            SendQuestResult(handler, false, action.c_str(), questId, nullptr, owner, "unknown_quest");
            handler->SetSentErrorMessage(true);
            return false;
        }

        if (stricmp(action.c_str(), "accept") == 0)
        {
            if (owner->GetQuestStatus(questId) == QUEST_STATUS_NONE && owner->CanAddQuest(quest, false) && owner->CanTakeQuest(quest, false))
                owner->AddQuestAndCheckCompletion(quest, owner);
            bool ok = owner->GetQuestStatus(questId) != QUEST_STATUS_NONE;
            SendQuestResult(handler, ok, "quest_accept", questId, quest, owner, ok ? nullptr : "cannot_accept");
            if (!ok)
                handler->SetSentErrorMessage(true);
            return ok;
        }

        if (stricmp(action.c_str(), "turn_in") == 0)
        {
            bool ok = owner->CanRewardQuest(quest, false);
            if (ok)
                owner->RewardQuest(quest, 0, owner);
            SendQuestResult(handler, ok, "quest_turn_in", questId, quest, owner, ok ? nullptr : "quest_incomplete");
            if (!ok)
                handler->SetSentErrorMessage(true);
            return ok;
        }

        if (stricmp(action.c_str(), "interact") == 0)
        {
            if (parsed.positional.size() > 2)
            {
                uint32 entry = uint32(std::strtoul(parsed.positional[2].c_str(), nullptr, 10));
                owner->KilledMonsterCredit(entry);
            }
            SendQuestResult(handler, true, "quest_interact", questId, quest, owner);
            return true;
        }

        if (stricmp(action.c_str(), "use_item") == 0)
        {
            if (parsed.positional.size() > 2)
            {
                uint32 entry = uint32(std::strtoul(parsed.positional[2].c_str(), nullptr, 10));
                owner->ItemAddedQuestCheck(entry, 1);
            }
            SendQuestResult(handler, true, "quest_use_item", questId, quest, owner);
            return true;
        }

        if (stricmp(action.c_str(), "objective") == 0 || stricmp(action.c_str(), "status") == 0)
        {
            SendQuestResult(handler, true, "quest_objective", questId, quest, owner);
            return true;
        }

        SendQuestResult(handler, false, action.c_str(), questId, quest, owner, "unknown_quest_action");
        handler->SetSentErrorMessage(true);
        return false;
    }

    static bool HandleMoveToCommand(ChatHandler* handler, char const* args)
    {
        CommandArgs parsed = ParseCommandArgs(args);
        Player* owner = GetOwner(handler, parsed.ownerSelector);
        if (!owner)
            return RequireOwner(handler, parsed.ownerSelector);

        if (parsed.positional.size() < 3)
        {
            SendResult(handler, false, "movement", "invalid_usage", ObjectGuid::Empty, "", "", "", 0, "", "move_to");
            handler->SetSentErrorMessage(true);
            return false;
        }

        float x = float(std::atof(parsed.positional[0].c_str()));
        float y = float(std::atof(parsed.positional[1].c_str()));
        float z = float(std::atof(parsed.positional[2].c_str()));
        std::string selector = parsed.positional.size() > 3 ? parsed.positional[3] : "all";
        uint32 changed = sBotMgr->SetMoveTarget(owner, x, y, z, selector);
        if (!changed)
        {
            SendResult(handler, false, "movement", "no_matching_bot", ObjectGuid::Empty, "", "", "", 0, selector, "move_to");
            handler->SetSentErrorMessage(true);
            return false;
        }

        SendResult(handler, true, "movement", nullptr, ObjectGuid::Empty, "", "", "", changed, selector, "move_to");
        return true;
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

    static bool HandleProfessionScoreCommand(ChatHandler* handler, char const* args)
    {
        CommandArgs parsed = ParseCommandArgs(args);
        Player* owner = GetOwner(handler, parsed.ownerSelector);
        if (!owner)
            return RequireOwner(handler, parsed.ownerSelector);

        std::string selector = parsed.positional.empty() ? "all" : parsed.positional[0];
        std::vector<BotRecipeScore> scores = sBotMgr->ScoreCookingRecipes(owner, selector);

        std::ostringstream json;
        json << "{\"ok\":true,\"action\":\"profession_score\",\"profession_id\":\"cooking\",\"selector\":\"" << JsonEscape(selector) << "\",\"recipes\":[";
        for (std::size_t i = 0; i < scores.size(); ++i)
        {
            BotRecipeScore const& score = scores[i];
            if (i)
                json << ',';
            json << "{\"recipe_id\":" << score.RecipeSpellId
                 << ",\"score\":" << score.Score
                 << ",\"expected_skillup_value\":" << score.ExpectedSkillupValue
                 << ",\"material_cost\":" << score.MaterialCost
                 << ",\"travel_cost\":" << score.TravelCost
                 << ",\"recipe_acquisition_cost\":" << score.RecipeAcquisitionCost
                 << ",\"known\":" << (score.Known ? "true" : "false")
                 << ",\"materials_available\":" << (score.MaterialsAvailable ? "true" : "false") << "}";
        }
        json << "],\"failure_reason\":null}";
        handler->PSendSysMessage("%s", json.str().c_str());
        return true;
    }

    static bool HandleCraftCommand(ChatHandler* handler, char const* args)
    {
        CommandArgs parsed = ParseCommandArgs(args);
        Player* owner = GetOwner(handler, parsed.ownerSelector);
        if (!owner)
            return RequireOwner(handler, parsed.ownerSelector);

        if (parsed.positional.empty())
        {
            SendResult(handler, false, "craft", "invalid_usage");
            handler->SetSentErrorMessage(true);
            return false;
        }

        uint32 recipeSpellId = uint32(std::strtoul(parsed.positional[0].c_str(), nullptr, 10));
        uint32 count = parsed.positional.size() > 1 ? std::max<uint32>(1, uint32(std::strtoul(parsed.positional[1].c_str(), nullptr, 10))) : 1;
        std::string selector = parsed.positional.size() > 2 ? parsed.positional[2] : "all";
        std::map<ObjectGuid, BotActionResult> results = sBotMgr->CraftCookingRecipe(owner, recipeSpellId, count, selector);

        std::ostringstream json;
        json << "{\"ok\":" << (!results.empty() ? "true" : "false")
             << ",\"action\":\"craft\",\"recipe_id\":" << recipeSpellId
             << ",\"count\":" << count
             << ",\"selector\":\"" << JsonEscape(selector)
             << "\",\"results\":[";
        bool first = true;
        for (auto const& result : results)
        {
            if (!first)
                json << ',';
            json << "{\"bot_guid\":" << result.first.GetCounter()
                 << ",\"result\":\"" << ToString(result.second) << "\"}";
            first = false;
        }
        json << "],\"failure_reason\":";
        if (results.empty())
            json << "\"no_matching_bot\"";
        else
            json << "null";
        json << "}";
        handler->PSendSysMessage("%s", json.str().c_str());
        if (results.empty())
            handler->SetSentErrorMessage(true);
        return !results.empty();
    }

    static bool HandleVendorTrashCommand(ChatHandler* handler, char const* args)
    {
        return HandleEconomyActionCommand(handler, args, "vendor_trash");
    }

    static bool HandleRepairCommand(ChatHandler* handler, char const* args)
    {
        return HandleEconomyActionCommand(handler, args, "repair");
    }

    static bool HandleEconomyActionCommand(ChatHandler* handler, char const* args, char const* action)
    {
        CommandArgs parsed = ParseCommandArgs(args);
        Player* owner = GetOwner(handler, parsed.ownerSelector);
        if (!owner)
            return RequireOwner(handler, parsed.ownerSelector);

        std::string selector = parsed.positional.empty() ? "all" : parsed.positional[0];
        std::map<ObjectGuid, BotEconomyActionResult> results = stricmp(action, "repair") == 0
            ? sBotMgr->Repair(owner, selector)
            : sBotMgr->VendorTrash(owner, selector);

        std::ostringstream json;
        json << "{\"ok\":" << (!results.empty() ? "true" : "false")
             << ",\"action\":\"" << JsonEscape(action)
             << "\",\"selector\":\"" << JsonEscape(selector)
             << "\",\"results\":[";
        bool first = true;
        for (auto const& result : results)
        {
            if (!first)
                json << ',';
            json << "{\"bot_guid\":" << result.first.GetCounter()
                 << ",\"result\":\"" << ToString(result.second.Result)
                 << "\",\"item_count\":" << result.second.ItemCount
                 << ",\"money\":" << result.second.Money << "}";
            first = false;
        }
        json << "],\"failure_reason\":";
        if (results.empty())
            json << "\"no_matching_bot\"";
        else
            json << "null";
        json << "}";
        handler->PSendSysMessage("%s", json.str().c_str());
        if (results.empty())
            handler->SetSentErrorMessage(true);
        return !results.empty();
    }

    static bool HandleGearEvalCommand(ChatHandler* handler, char const* args)
    {
        CommandArgs parsed = ParseCommandArgs(args);
        Player* owner = GetOwner(handler, parsed.ownerSelector);
        if (!owner)
            return RequireOwner(handler, parsed.ownerSelector);

        std::string selector = parsed.positional.empty() ? "all" : parsed.positional[0];
        std::map<ObjectGuid, std::vector<BotGearEvaluation>> results = sBotMgr->EvaluateGear(owner, selector);

        std::ostringstream json;
        json << "{\"ok\":" << (!results.empty() ? "true" : "false")
             << ",\"action\":\"gear_eval\",\"selector\":\"" << JsonEscape(selector)
             << "\",\"bots\":[";
        bool firstBot = true;
        for (auto const& botResult : results)
        {
            if (!firstBot)
                json << ',';
            json << "{\"bot_guid\":" << botResult.first.GetCounter()
                 << ",\"items\":[";
            for (std::size_t i = 0; i < botResult.second.size(); ++i)
            {
                BotGearEvaluation const& item = botResult.second[i];
                if (i)
                    json << ',';
                json << "{\"item_id\":" << item.ItemId
                     << ",\"bag\":" << uint32(item.Bag)
                     << ",\"slot\":" << uint32(item.Slot)
                     << ",\"quality\":" << uint32(item.Quality)
                     << ",\"inventory_type\":" << uint32(item.InventoryType)
                     << ",\"score\":" << item.Score
                     << ",\"equipped_score\":" << item.EquippedScore
                     << ",\"decision\":\"" << JsonEscape(item.Decision) << "\"}";
            }
            json << "]}";
            firstBot = false;
        }
        json << "],\"failure_reason\":";
        if (results.empty())
            json << "\"no_matching_bot\"";
        else
            json << "null";
        json << "}";
        handler->PSendSysMessage("%s", json.str().c_str());
        if (results.empty())
            handler->SetSentErrorMessage(true);
        return !results.empty();
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

class botexp_commandscript : public CommandScript
{
public:
    botexp_commandscript() : CommandScript("botexp_commandscript") { }

    std::vector<ChatCommand> GetCommands() const override
    {
        static std::vector<ChatCommand> botExpCommandTable =
        {
            { "start",  rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleStartCommand,  "" },
            { "stop",   rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleStopCommand,   "" },
            { "status", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleStatusCommand, "" },
            { "summary", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleSummaryCommand, "" },
            { "export", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleExportCommand, "" },
        };

        static std::vector<ChatCommand> commandTable =
        {
            { "botexp", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, nullptr, "", botExpCommandTable },
        };

        return commandTable;
    }

private:
    static std::string FirstArg(char const* args)
    {
        if (!args)
            return "";

        std::string input = args;
        std::vector<char> buffer(input.begin(), input.end());
        buffer.push_back('\0');
        if (char* token = strtok(buffer.data(), " "))
            return token;

        return "";
    }

    static bool HandleStartCommand(ChatHandler* handler, char const* args)
    {
        std::string name = FirstArg(args);
        if (name.empty())
            name = "autonomous_zone_10";

        if (!sBotWorldPopulationMgr->Start(name))
        {
            if (handler)
            {
                handler->PSendSysMessage("{\"ok\":false,\"action\":\"botexp_start\",\"failure_reason\":\"botworld_or_playerbot_disabled_or_no_pool_character\"}");
                handler->SetSentErrorMessage(true);
            }
            return false;
        }

        if (handler)
            handler->PSendSysMessage("%s", sBotWorldPopulationMgr->GetStatusJson().c_str());
        return true;
    }

    static bool HandleStopCommand(ChatHandler* handler, char const* /*args*/)
    {
        sBotWorldPopulationMgr->Stop();
        if (handler)
            handler->PSendSysMessage("{\"ok\":true,\"action\":\"botexp_stop\",\"failure_reason\":null}");
        return true;
    }

    static bool HandleStatusCommand(ChatHandler* handler, char const* /*args*/)
    {
        if (handler)
            handler->PSendSysMessage("%s", sBotWorldPopulationMgr->GetStatusJson().c_str());
        return true;
    }

    static bool HandleSummaryCommand(ChatHandler* handler, char const* /*args*/)
    {
        if (handler)
            handler->PSendSysMessage("%s", sBotWorldPopulationMgr->GetSummaryJson().c_str());
        return true;
    }

    static bool HandleExportCommand(ChatHandler* handler, char const* /*args*/)
    {
        if (handler)
            handler->PSendSysMessage("{\"ok\":true,\"action\":\"botexp_export\",\"storage\":\"character_database_tables\",\"tables\":[\"experiment_bot_runs\",\"experiment_bot_events\",\"experiment_bot_decisions\",\"experiment_bot_activities\",\"experiment_bot_replay_records\"],\"failure_reason\":null}");
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
    new botexp_commandscript();
    new playerbot_playerscript();
    new playerbot_unitscript();
    new playerbot_groupscript();
    new playerbot_worldscript();
}
