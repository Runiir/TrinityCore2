#pragma once
#include "fields.hpp"
#include "party_state.hpp"
#include "raid_markers.hpp"
#include <deque>
#include <array>
#include <functional>
#include <optional>
#include <unordered_map>
#include <unordered_set>

namespace bridge
{
using Packet = std::pair<std::string, Bytes>;
using Reply = std::optional<Packet>;
struct State
{
    Value character;
    Value self_snapshot;
    std::unordered_map<std::uint64_t, Value> visible_gameobjects, visible_units, inventory_items;
    std::unordered_map<unsigned, Value> casts, visible_auras, pending_movement;
    std::unordered_map<unsigned, std::deque<Array>> gameobject_queries;
    std::unordered_set<unsigned> creature_queries, npc_text_queries;
    Value loot, taxi_menu, gossip_menu, pending_near, pending_far;
    Array party_guid{0,0};
    std::unordered_map<std::uint64_t, PartyState> party_states;
    std::unordered_set<std::uint64_t> party_members;
    std::uint64_t party_leader=0;
    unsigned party_flags=0, party_member_flags=0;
    std::array<std::uint32_t,17> account_times{};
    Array action_buttons;
    unsigned cast_counter = 0;
    std::uint64_t cast_serial = 0, aura_serial = 0;
    bool created = false;
    std::uint64_t last_logout_guid = 0; // Final character-cache writes, never gameplay authority.
    std::uint64_t inspect_target = 0;
    Array latest_movement;
    std::function<void(std::string const &, View)> native_send;
    std::uint64_t guid() const
    {
        return integer(get(character, "guid"));
    }
    std::uint32_t map() const
    {
        return integer(get(character, "map"));
    }
};
struct Protocol
{
    std::filesystem::path directory;
    Value index, sequences, opcodes, inventory_results;
    std::unordered_map<unsigned, std::string> modern_names, legacy_names;
    Fields fields;
    explicit Protocol(std::filesystem::path const &directory);
    std::uint32_t field(Value const &snapshot, std::string_view name, unsigned offset = 0) const;
    float float_field(Value const &snapshot, std::string_view name, unsigned offset = 0) const;
    unsigned field_index(std::string_view name) const
    {
        return integer(get(index, name));
    }
    static Array modern_guid(std::uint64_t native, unsigned map);
    static Array inventory_guid(std::uint64_t native);
    void validate_standing(State const &owner, Value const &movement) const;
    Packet movement_encode(std::string name, std::uint64_t guid, Value const &movement,
                           bool ack = false) const;
    Reply movement_control(State &owner, std::string const &name, View body) const;
    Packet movement_ack(State &owner, std::string const &name, View body) const;
    Value field_values(Value const &snapshot, Value const &character) const;
    Bytes player_block(Value const &snapshot, Value const &character, Array const *buttons = nullptr) const;
    Bytes public_player_block(Value const &snapshot, Value const &character) const;
    Bytes item_block(Value const &snapshot) const;
    Bytes gameobject_block(Value const &snapshot) const;
    Bytes unit_block(Value const &snapshot, Value const &character) const;
    Bytes create(Value const &snapshot, Value const &character, std::vector<Value> const &items,
                 Array const *buttons) const;
    Bytes scalar_block(Value const &snapshot, Value const &character, Value const &changed,
                       unsigned visibility = 0) const;
    Bytes rest_block(Value const &snapshot, Value const &changed) const;
    Bytes guild_block(Value const &snapshot,Value const &character,Value const &changed,unsigned visibility=1) const;
    static Reply inventory_request(State const &owner,std::string const &name,View body);
    Reply inventory_response(std::string const &name,View body) const;
    Bytes inventory_block(Value const &snapshot,Value const &changed,unsigned visibility=1) const;
    Bytes item_update(Value const &snapshot,Value const &changed) const;
    Reply object_updates(State &owner, View body,Array const &players={}) const;
    Packet cast_request(State &owner, View body) const;
    Reply cast_response(State &owner, std::string const &name, View body) const;
    static Reply cast_prepare(State &owner, View body);
    static Bytes cast_rejected(View body);
    static Bytes cast_cancel(State const &owner, View body);
    static Reply aura_response(State &owner, std::string const &name, View body);
    static Bytes aura_cancel(State const &owner, View body);
    static Reply initialize_response(State &owner, std::string const &name, View body);
    static Reply currency_response(std::string const &name, View body);
    static Reply reputation_response(std::string const &name, View body, Array const &factions);
    static Reply social_request(std::string const &name, View body);
    static Reply social_response(std::string const &name, View body);
    static Bytes player_names_response(Array const &requested, Array const &rows);
    static Bytes realm_name(View body);
    static Reply party_request(std::string const &name, View body);
    static bool late_party_query(bool active, std::string const &name, View body);
    static Reply party_response(State &owner, std::string const &name, View body, Array const &identities);
    static Array party_members(View body);
    static Reply party_state(State &owner, std::string const &name, View body);
    static Reply party_profiles(std::string const &name, View body);
    static Reply party_roles(std::string const &name, View body);
    static std::vector<Packet> marker_clear(View body);
    Array marker_objects(State const &owner, View body) const;
    static void marker_permission(State const &owner);
    static Value const *extra_marker(State const &owner);
    Reply extra_marker_go(State &owner) const;
    static Reply account_request(State const &owner, std::string const &name, View body);
    static Reply account_response(State &owner, std::string const &name, View body);
    static Reply achievement_response(State const &owner, std::string const &name, View body);
    static Reply reputation_request(std::string const &name, View body);
    static Reply loot_response(State &owner, std::string const &name, View body);
    static std::vector<Packet> loot_request(State const &owner, std::string const &name, View body);
    static Reply transfer_response(State &owner, std::string const &name, View body);
    static Packet transfer_request(State &owner, std::string const &name, View body);
    static Reply transfer_resume(State &owner);
    static Reply gossip_response(State &owner, std::string const &name, View body);
    static Packet gossip_request(State &owner, std::string const &name, View body);
    static Reply taxi_response(State &owner, std::string const &name, View body);
    static Packet taxi_request(State &owner, std::string const &name, View body, Value const &paths);
    static Reply combat_response(State const &owner, std::string const &name, View body);
    static Reply combat_request(State const &owner, std::string const &name, View body);
    static Bytes gameobject_query(State &owner, View body);
    static Reply gameobject_reply(State &owner, View body);
    static std::optional<Bytes> creature_query(State &owner, View body);
    static Reply creature_reply(State &owner, View body);
    static Bytes npc_query(State &owner, View body);
    static Reply npc_reply(State &owner, View body, Array const *broadcasts);
    static Reply destroy_object(State &owner, View body);
    static std::vector<Packet> creature_movement(State &owner, View body);
    Reply public_player_movement(State &owner, View body) const;
    static Reply inspect_request(State &owner,std::string const &name,View body);
    Reply inspect_response(State &owner,std::string const &name,View body) const;
    static Reply trade_request(State const &owner,std::string const &name,View body);
    Reply trade_response(std::string const &name,View body) const;
    static std::pair<std::uint8_t,std::uint8_t> inventory_position(std::uint8_t bag,std::uint8_t slot);
};
Bytes native_text(Reader &reader);
Value movement_parse(View body, std::uint64_t wanted);
bool movement_supported(std::string const &name);
std::uint32_t modern_flags2(std::uint32_t native);
std::uint64_t native_guid(Reader &reader);
Writer &packed(Writer &writer, std::uint64_t guid);
std::vector<Value> native_records(View body);
Bytes object_packet(unsigned map, std::vector<Bytes> const &blocks = {},
                    std::vector<std::uint64_t> const &removed = {},
                    std::vector<std::uint64_t> const &destroyed = {});
std::uint64_t owned_gameobject(State const &owner, Array const &identity);
std::uint64_t owned_unit(State const &owner, Array const &identity);
} // namespace bridge
