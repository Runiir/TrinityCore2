#include "events.hpp"
#include "chat_channels.hpp"
#include "chat_probe.hpp"
#include "pet_rename_probe.hpp"
#include "stable_probe.hpp"
#include <chrono>
#include <fstream>
#include <sys/stat.h>
#include <unordered_set>

namespace bridge
{
namespace
{
double now()
{
    return std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
}
bool capture(std::string const &name)
{
    // Explicitly exclude secrets regardless of any later allowlist expansion.
    if (name.find("AUTH") != std::string::npos || name.find("ENCRYPT") != std::string::npos ||
        name == "SMSG_CONNECT_TO")
        return false;
    if (name == "SMSG_MOVE_UPDATE") return false; // Opt-in public movement probe below.
    for (auto token : {"TAXI", "GOSSIP", "TELEPORT", "TRANSFER", "NEW_WORLD", "TOKEN", "WORLD_PORT",
                       "WORLDPORT", "AREA_TRIGGER", "NPC_TEXT", "MAIL", "AUCTION", "QUEST", "TALENT", "GLYPH", "EQUIPMENT_SET"})
        if (name.find(token) != std::string::npos)
            return true;
    if (name.starts_with("CMSG_MOVE_") || name.starts_with("MSG_MOVE_") || name.starts_with("SMSG_MOVE_"))
        return true;
    static std::unordered_set<std::string> const names = {"CMSG_SET_ACTION_BAR_TOGGLES", "CMSG_SET_ACTIONBAR_TOGGLES",
                                                          "CMSG_PET_ACTION", "CMSG_PET_SPELL_AUTOCAST", "CMSG_PET_SET_ACTION",
                                                          "CMSG_REQUEST_PET_INFO", "CMSG_QUERY_PET_NAME", "CMSG_PET_NAME_QUERY",
                                                          "SMSG_PET_NAME_QUERY_RESPONSE", "SMSG_QUERY_PET_NAME_RESPONSE",
                                                          "SMSG_PET_SPELLS", "SMSG_PET_SPELLS_MESSAGE",
                                                          "CMSG_STAND_STATE_CHANGE", "CMSG_STANDSTATECHANGE", "SMSG_STAND_STATE_UPDATE", "CMSG_SET_SHEATHED",
                                                          "CMSG_SEND_CONTACT_LIST", "CMSG_CONTACT_LIST", "CMSG_WHO", "SMSG_WHO",
                                                          "CMSG_SHOWING_HELM", "CMSG_SHOWING_CLOAK",
                                                          "CMSG_BANKER_ACTIVATE", "SMSG_SHOW_BANK", "SMSG_NPC_INTERACTION_OPEN_RESULT",
                                                          "CMSG_LIST_INVENTORY", "SMSG_VENDOR_INVENTORY",
                                                          "CMSG_REPAIR_ITEM", "CMSG_TRAINER_LIST", "CMSG_TRAINER_BUY_SPELL",
                                                          "SMSG_TRAINER_LIST", "SMSG_TRAINER_BUY_FAILED", "SMSG_TRAINER_BUY_SUCCEEDED",
                                                          "SMSG_LEARNED_SPELL", "SMSG_LEARNED_SPELLS",
                                                          "CMSG_QUERY_QUEST_INFO", "SMSG_QUERY_QUEST_INFO_RESPONSE",
                                                          "SMSG_QUEST_QUERY_RESPONSE",
                                                          "CMSG_QUEST_GIVER_HELLO", "CMSG_QUEST_GIVER_QUERY_QUEST",
                                                          "CMSG_QUEST_GIVER_ACCEPT_QUEST", "CMSG_QUEST_LOG_REMOVE_QUEST",
                                                          "SMSG_QUEST_GIVER_QUEST_DETAILS", "SMSG_QUEST_GIVER_QUEST_LIST_MESSAGE",
                                                          "CMSG_BUY_ITEM", "SMSG_BUY_ITEM", "SMSG_BUY_SUCCEEDED", "SMSG_BUY_FAILED", "SMSG_ITEM_PUSH_RESULT",
                                                          "CMSG_SELL_ITEM", "SMSG_SELL_ITEM", "SMSG_SELL_RESPONSE", "CMSG_BUY_BACK_ITEM", "CMSG_BUYBACK_ITEM",
                                                          "CMSG_AUTOBANK_ITEM", "CMSG_AUTOSTORE_BANK_ITEM", "CMSG_CLOSE_INTERACTION",
                                                          "CMSG_INSPECT", "SMSG_INSPECT_TALENT", "SMSG_INSPECT_RESULT",
                                                          "CMSG_INITIATE_TRADE", "CMSG_BEGIN_TRADE", "CMSG_CANCEL_TRADE", "CMSG_ACCEPT_TRADE",
                                                          "CMSG_BUSY_TRADE", "CMSG_IGNORE_TRADE", "CMSG_UNACCEPT_TRADE", "CMSG_SET_TRADE_GOLD",
                                                          "CMSG_SET_TRADE_ITEM", "CMSG_CLEAR_TRADE_ITEM", "SMSG_TRADE_STATUS", "SMSG_TRADE_UPDATED",
                                                          "CMSG_QUERY_GUILD_INFO", "CMSG_GUILD_QUERY", "CMSG_GUILD_GET_ROSTER",
                                                          "CMSG_GUILD_INVITE_BY_NAME", "CMSG_GUILD_INVITE", "SMSG_GUILD_INVITE",
                                                          "CMSG_ACCEPT_GUILD_INVITE", "CMSG_GUILD_ACCEPT", "CMSG_GUILD_DECLINE_INVITATION", "CMSG_GUILD_DECLINE",
                                                          "CMSG_SWAP_INV_ITEM", "CMSG_SWAP_ITEM", "CMSG_SPLIT_ITEM",
                                                          "CMSG_AUTO_EQUIP_ITEM", "CMSG_AUTOEQUIP_ITEM", "CMSG_AUTO_EQUIP_ITEM_SLOT", "CMSG_AUTOEQUIP_ITEM_SLOT",
                                                          "CMSG_AUTO_STORE_BAG_ITEM", "CMSG_AUTOSTORE_BAG_ITEM", "SMSG_INVENTORY_CHANGE_FAILURE",
                                                          "CMSG_ADD_FRIEND", "CMSG_DEL_FRIEND", "CMSG_SET_CONTACT_NOTES",
                                                          "CMSG_ADD_IGNORE", "CMSG_DEL_IGNORE", "SMSG_CONTACT_LIST", "SMSG_FRIEND_STATUS",
                                                          "CMSG_QUERY_PLAYER_NAMES", "SMSG_QUERY_PLAYER_NAMES_RESPONSE",
                                                          "CMSG_QUERY_REALM_NAME", "SMSG_REALM_QUERY_RESPONSE",
                                                          "CMSG_PARTY_INVITE", "CMSG_PARTY_INVITE_RESPONSE", "CMSG_PARTY_UNINVITE",
                                                          "CMSG_LEAVE_GROUP", "CMSG_GROUP_DISBAND", "CMSG_CONVERT_RAID", "CMSG_GROUP_RAID_CONVERT",
                                                          "CMSG_SET_PARTY_LEADER", "CMSG_GROUP_SET_LEADER", "CMSG_GROUP_UNINVITE_GUID",
                                                          "SMSG_PARTY_UPDATE", "SMSG_PARTY_INVITE", "SMSG_PARTY_COMMAND_RESULT", "SMSG_GROUP_DECLINE",
                                                          "CMSG_REQUEST_PARTY_MEMBER_STATS", "SMSG_PARTY_MEMBER_FULL_STATE", "SMSG_PARTY_MEMBER_STATE",
                                                          "CMSG_SAVE_CUF_PROFILES", "SMSG_LOAD_CUF_PROFILES",
                                                          "CMSG_SET_EVERYONE_IS_ASSISTANT", "CMSG_SET_ASSISTANT_LEADER", "CMSG_GROUP_ASSISTANT_LEADER",
                                                          "CMSG_INITIATE_ROLE_POLL", "CMSG_ROLE_POLL_BEGIN", "CMSG_SET_ROLE", "SMSG_ROLE_POLL_BEGIN", "SMSG_ROLE_POLL_INFORM", "SMSG_ROLE_CHANGED_INFORM",
                                                          "CMSG_DO_READY_CHECK", "CMSG_READY_CHECK_RESPONSE", "MSG_RAID_READY_CHECK", "MSG_RAID_READY_CHECK_CONFIRM",
                                                          "SMSG_READY_CHECK_STARTED", "SMSG_READY_CHECK_RESPONSE", "SMSG_READY_CHECK_COMPLETED",
                                                          "SMSG_INITIALIZE_FACTIONS", "SMSG_SET_FACTION_STANDING",
                                                          "SMSG_SET_FACTION_VISIBLE", "SMSG_SET_FACTION_NOT_VISIBLE",
                                                          "CMSG_SET_FACTION_AT_WAR", "CMSG_SET_FACTION_NOT_AT_WAR", "CMSG_SET_FACTION_ATWAR",
                                                          "CMSG_SET_FACTION_INACTIVE", "CMSG_SET_WATCHED_FACTION",
                                                          "CMSG_DB_QUERY_BULK",
                                                          "SMSG_DB_REPLY",
                                                          "SMSG_AVAILABLE_HOTFIXES",
                                                          "CMSG_HOTFIX_REQUEST",
                                                          "SMSG_HOTFIX_MESSAGE",
                                                          "SMSG_HOTFIX_CONNECT",
                                                          "CMSG_SET_SELECTION",
                                                          "CMSG_ATTACK_SWING",
                                                          "CMSG_ATTACK_STOP",
                                                          "SMSG_ATTACK_START",
                                                          "SMSG_ATTACK_STOP",
                                                          "SMSG_ATTACKSWING_NOTINRANGE", "SMSG_ATTACKSWING_BADFACING",
                                                          "SMSG_ATTACKSWING_CANT_ATTACK", "SMSG_ATTACKSWING_DEADTARGET",
                                                          "SMSG_ATTACK_SWING_ERROR", "SMSG_ATTACKER_STATE_UPDATE",
                                                          "SMSG_SPELLNONMELEEDAMAGELOG", "SMSG_SPELL_NON_MELEE_DAMAGE_LOG",
                                                          "SMSG_ON_MONSTER_MOVE",
                                                          "SMSG_ON_MONSTER_MOVE_TRANSPORT",
                                                          "CMSG_GAME_OBJ_USE",
                                                          "CMSG_GAME_OBJ_REPORT_USE",
                                                          "CMSG_GAMEOBJ_USE",
                                                          "CMSG_GAMEOBJ_REPORT_USE",
                                                          "CMSG_LOOT_ITEM",
                                                          "CMSG_LOOT_CURRENCY",
                                                          "CMSG_AUTOSTORE_LOOT_ITEM",
                                                          "CMSG_LOOT_RELEASE",
                                                          "SMSG_LOOT_RESPONSE",
                                                          "SMSG_LOOT_REMOVED",
                                                          "SMSG_CURRENCY_LOOT_REMOVED",
                                                          "SMSG_LOOT_RELEASE",
                                                          "SMSG_SETUP_CURRENCY",
                                                          "SMSG_SET_CURRENCY",
                                                          "CMSG_SET_CURRENCY_FLAGS",
                                                          "CMSG_REQUEST_RESEARCH_HISTORY",
                                                          "SMSG_SETUP_RESEARCH_HISTORY",
                                                          "SMSG_RESEARCH_COMPLETE",
                                                          "SMSG_AURA_UPDATE",
                                                          "SMSG_AURA_UPDATE_ALL",
                                                          "CMSG_CANCEL_AURA",
                                                          "CMSG_PET_CANCEL_AURA",
                                                          "CMSG_CANCEL_MOUNT_AURA",
                                                          "CMSG_QUERY_GAME_OBJECT",
                                                          "SMSG_QUERY_GAME_OBJECT_RESPONSE",
                                                          "CMSG_GAMEOBJECT_QUERY",
                                                          "SMSG_GAMEOBJECT_QUERY_RESPONSE",
                                                          "CMSG_QUERY_CREATURE",
                                                          "CMSG_CREATURE_QUERY",
                                                          "SMSG_CREATURE_QUERY_RESPONSE",
                                                          "SMSG_QUERY_CREATURE_RESPONSE",
                                                          "SMSG_SEND_KNOWN_SPELLS",
                                                          "SMSG_UPDATE_ACTION_BUTTONS",
                                                          "SMSG_SET_PROFICIENCY",
                                                          "SMSG_SEND_UNLEARN_SPELLS",
                                                          "CMSG_CAST_SPELL",
                                                          "CMSG_USE_ITEM",
                                                          "CMSG_READ_ITEM", "SMSG_READ_ITEM_OK", "SMSG_READ_ITEM_FAILED",
                                                          "SMSG_READ_ITEM_RESULT_OK", "SMSG_READ_ITEM_RESULT_FAILED",
                                                          "CMSG_QUERY_PAGE_TEXT", "CMSG_PAGE_TEXT_QUERY",
                                                          "SMSG_QUERY_PAGE_TEXT_RESPONSE", "SMSG_PAGE_TEXT_QUERY_RESPONSE",
                                                          "CMSG_REMOVE_GLYPH",
                                                          "CMSG_CLEAR_RAID_MARKER",
                                                          "SMSG_RAID_MARKERS_CHANGED",
                                                          "SMSG_SPELL_PREPARE",
                                                          "SMSG_SPELL_START",
                                                          "SMSG_SPELL_GO",
                                                          "SMSG_CAST_FAILED",
                                                          "SMSG_SPELL_FAILURE",
                                                          "SMSG_SPELL_FAILED_OTHER",
                                                          "CMSG_CANCEL_CAST",
                                                          "CMSG_SET_ACTION_BUTTON",
                                                          "CMSG_SET_ACTIVE_MOVER",
                                                          "CMSG_ENUM_CHARACTERS",
                                                          "SMSG_ENUM_CHARACTERS_RESULT",
                                                          "CMSG_PLAYER_LOGIN",
                                                          "SMSG_UPDATE_OBJECT",
                                                          "SMSG_DESTROY_OBJECT",
                                                          "SMSG_LOGIN_VERIFY_WORLD",
                                                          "SMSG_BIND_POINT_UPDATE",
                                                          "SMSG_CONTROL_UPDATE",
                                                          "CMSG_TIME_SYNC_RESP",
                                                          "CMSG_TIME_SYNC_RESPONSE",
                                                          "SMSG_TIME_SYNC_REQ",
                                                          "SMSG_TIME_SYNC_REQUEST",
                                                          "CMSG_LOG_DISCONNECT",
                                                          "CMSG_LOGOUT_REQUEST",
                                                          "CMSG_LOGOUT_CANCEL",
                                                          "SMSG_LOGOUT_RESPONSE",
                                                          "SMSG_LOGOUT_COMPLETE",
                                                          "SMSG_LOGOUT_CANCEL_ACK"};
    return names.contains(name);
}
} // namespace
void Events::append(std::filesystem::path const &path, Object const &record)
{
    std::lock_guard lock(mutex_);
    if (std::filesystem::exists(path) && std::filesystem::file_size(path) >= 8 * 1024 * 1024)
    {
        auto stamp = std::chrono::system_clock::now().time_since_epoch().count();
        std::filesystem::rename(path, path.string() + ".part-" + std::to_string(stamp));
    }
    std::ofstream output(path, std::ios::app);
    if (!output)
        throw std::runtime_error("diagnostic journal unavailable");
    chmod(path.c_str(), 0600);
    output << json::serialize(record) << '\n';
    if (!output)
        throw std::runtime_error("diagnostic journal write failed");
}
void Events::event(std::string kind, Object fields)
{
    static std::unordered_set<std::string> const allowed = {"session",   "opcode",     "name",  "bytes",
                                                            "status",    "account_id", "error", "port",
                                                            "direction", "guid",       "map",   "position",
                                                            "group", "starter", "member", "ready", "duration_ms", "reason"};
    for (auto const &[key, value] : fields)
        if (!allowed.contains(std::string(key)))
            throw std::runtime_error("unreviewed world diagnostic fields");
    fields["time"] = now();
    fields["event"] = kind;
    append(root_ / "logs/modern_world.jsonl", fields);
}
void Events::marker_placed(std::string const &session,Value const &location)
{
    event("compatibility_marker_placed",{{"session",session},{"map",get(location,"map")},
        {"position",get(location,"position")},{"status",get(location,"slot")}});
}
void Events::packet(std::string const &direction, std::string const &name, View body,
                    std::string const &session)
{
    if(owned_stable_request_probe(root_,direction,name,body,session,now()))
    {
        append(root_/"evidence/owned_stable_request_packets.jsonl",Object{{"time",now()},
            {"session",session},{"direction",direction},{"name",name},{"body",hex(body)}});
        return;
    }
    if(owned_pet_rename_probe(root_,direction,name,body,session,now()))
    {
        append(root_/"evidence/owned_pet_rename_packets.jsonl",Object{{"time",now()},
            {"session",session},{"direction",direction},{"name",name},{"body",hex(body)}});
        return;
    }
    bool movement_probe=name=="SMSG_MOVE_UPDATE" &&
        std::filesystem::is_regular_file(root_/"run/capture_public_movement");
    if (!capture(name) && !public_chat_probe(name,body) && !public_channel_probe(name,body) && !movement_probe)
        return;
    append(root_ / "evidence/world_packets.jsonl", Object{{"time", now()},
                                                          {"session", session},
                                                          {"direction", direction},
                                                          {"name", name},
                                                          {"body", hex(body)}});
}
} // namespace bridge
