#include "protocol.hpp"
#include "reputation_fields.hpp"

namespace bridge
{
namespace
{
void merge_fields(Value &snapshot, Value const &record)
{
    for (auto const &[key, value] : get(record, "fields").as_object())
        snapshot.as_object()["fields"].as_object()[key] = value;
}
Bytes research_block(std::uint64_t guid, Value const &sites, Value const &projects)
{
    unsigned mask = 0;
    if (!sites.is_null())
        mask |= (1u << 23) | (1u << 24);
    if (!projects.is_null())
        mask |= (1u << 27) | (1u << 28);
    Writer data;
    data.pack("BBBI", {1, 0, 3, 1u << 7}).pack("I", {1}).bits(0, 14).bits(mask, 32);
    auto complete = [&](Value const &v)
    {
        auto size = v.as_array().size();
        if (size > 32)
            throw std::runtime_error("research array exceeds native bound");
        data.bits(size, 32);
        if (size)
            data.bits((1ull << size) - 1, size);
    };
    if (!sites.is_null())
        complete(sites);
    if (!projects.is_null())
        complete(projects);
    if (!sites.is_null())
        data.pack(std::string(sites.as_array().size(), 'H'), sites.as_array());
    if (!projects.is_null())
        data.pack(std::string(projects.as_array().size(), 'h'), projects.as_array());
    data.flush();
    return Writer()
        .pack("B", {0})
        .guid(guid, player_high())
        .put<std::uint32_t>(data.data().size())
        .raw(data.data())
        .finish();
}
Bytes skill_block(Protocol const &protocol, Value const &snapshot, Value const &changed)
{
    // Pinned ActivePlayerData group0/member36 contains SkillInfo. Its seven
    // arrays have256 slots; native Cata supplies128 packed uint16 slots.
    struct Column {char const *native;unsigned column;unsigned bit;};
    Column const columns[]={{"PLAYER_SKILL_LINEID_0",0,1},{"PLAYER_SKILL_STEP_0",1,257},
        {"PLAYER_SKILL_RANK_0",2,513},{"PLAYER_SKILL_MAX_RANK_0",4,1025},
        {"PLAYER_SKILL_MODIFIER_0",5,1281},{"PLAYER_SKILL_TALENT_0",6,1537}};
    std::array<std::uint32_t,57> masks{};
    std::array<std::array<std::uint16_t,128>,7> values{};
    std::array<std::array<bool,128>,7> selected{};
    bool any=false;
    auto set=[&](unsigned column,unsigned slot,unsigned bit,std::uint16_t value)
    {
        masks[bit/32]|=1u<<(bit%32);values[column][slot]=value;selected[column][slot]=true;any=true;
    };
    for(auto const &column:columns)
        for(unsigned word=0;word<64;++word)
            if(changed.as_object().contains(std::to_string(protocol.field_index(column.native)+word)))
                for(unsigned half=0;half<2;++half)
                {
                    auto slot=word*2+half;
                    auto value=static_cast<std::uint16_t>(protocol.field(snapshot,column.native,word)>>(half*16));
                    set(column.column,slot,column.bit+slot,value);
                    // Match the existing native creation mapping: starting
                    // rank has no independent native field and mirrors rank.
                    if(column.column==2)set(3,slot,769+slot,value);
                }
    if(!any)return {};
    masks[0]|=1u;
    Writer data;data.pack("BBBI",{1,0,3,1u<<7}).pack("I",{3})
        .bits(0,14).bits(1u,32).bits(1u<<4,32).flush();
    std::uint64_t blocks=0;
    for(unsigned i=0;i<masks.size();++i)if(masks[i])blocks|=1ull<<i;
    data.put<std::uint32_t>(static_cast<std::uint32_t>(blocks)).bits(blocks>>32,25);
    for(auto mask:masks)if(mask)data.bits(mask,32);
    data.flush();
    for(unsigned slot=0;slot<128;++slot)
        for(unsigned column=0;column<7;++column)
            if(selected[column][slot])data.put<std::uint16_t>(values[column][slot]);
    return Writer().put<std::uint8_t>(0).guid(integer(get(snapshot,"guid")),player_high())
        .put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
}
} // namespace
Reply Protocol::object_updates(State &owner, View body,Array const &players) const
{
    auto records = native_records(body);
    std::vector<Bytes> blocks;
    std::vector<std::uint64_t> removed;
    unsigned map = owner.map();
    if (!owner.created)
    {
        std::vector<Value> items;
        for (auto const &record : records)
        {
            auto kind = integer(get(record, "kind"));
            if (kind == 1 || kind == 2)
                items.push_back(record);
            if (integer(get(record, "guid")) == owner.guid() && kind == 4 &&
                truth(get(get(record, "flags"), "self")))
            {
                owner.self_snapshot = record;
                for (auto const &item : items)
                {
                    blocks.push_back(item_block(item));
                    owner.inventory_items[integer(get(item,"guid"))]=item;
                }
                blocks.push_back(player_block(
                    record, owner.character, owner.action_buttons.empty() ? nullptr : &owner.action_buttons));
                owner.created = true;
                break;
            }
        }
        if (!owner.created)
            return {};
    }
    for (auto const &record : records)
    {
        map = integer(get(record, "map"));
        auto guid = integer(get(record, "guid")), type = integer(get(record, "update_type"));
        if (type == 3)
        {
            for (auto const &id : get(record, "removed").as_array())
            {
                auto removed_guid = integer(id);
                if (owner.visible_gameobjects.erase(removed_guid) || owner.visible_units.erase(removed_guid) || owner.inventory_items.erase(removed_guid))
                    removed.push_back(removed_guid);
            }
            continue;
        }
        auto kind = integer(get(record, "kind"));
        if((kind==1 || kind==2) && guid>>48==0x4000)
        {
            if(!owner.inventory_items.contains(guid))blocks.push_back(item_block(record));
            owner.inventory_items[guid]=record;
        }
        else if(type==0 && owner.inventory_items.contains(guid))
        {
            auto &snapshot=owner.inventory_items.at(guid);merge_fields(snapshot,record);
            auto item=item_update(snapshot,get(record,"fields"));
            if(!item.empty())blocks.push_back(item);
        }
        else if (kind == 5 && guid >> 52 == 0xf11)
        {
            blocks.push_back(gameobject_block(record));
            owner.visible_gameobjects[guid] = record;
        }
        else if (kind == 3 && (guid >> 52 == 0xf13 || guid >> 52 == 0xf15))
        {
            blocks.push_back(unit_block(record, owner.character));
            owner.visible_units[guid] = record;
        }
        else if(kind==4 && guid!=owner.guid())
        {
            Value profile;
            for(auto const &row:players)if(integer(get(row,"guid"))==guid)
            {
                if(!profile.is_null())throw std::runtime_error("ambiguous visible player profile");
                profile=row;
            }
            blocks.push_back(public_player_block(record,profile));
            auto snapshot=record;snapshot.as_object()["public_character"]=profile;
            owner.visible_units[guid]=std::move(snapshot);
        }
        else if (type == 0 && guid == owner.guid() && !owner.self_snapshot.is_null())
        {
            merge_fields(owner.self_snapshot, record);
            auto s = owner.self_snapshot;
            s.as_object()["map"] = owner.map();
            s.as_object()["guid"] = owner.guid();
            auto scalar = scalar_block(s, owner.character, get(record, "fields"), 1);
            if (!scalar.empty())
                blocks.push_back(scalar);
            auto rest = rest_block(s, get(record, "fields"));
            if (!rest.empty())
                blocks.push_back(rest);
            auto watched=watched_faction_block(*this,s,get(record,"fields"));
            if(!watched.empty())blocks.push_back(watched);
            auto guild=guild_block(s,owner.character,get(record,"fields"));
            if(!guild.empty())blocks.push_back(guild);
            auto quests=quest_block(s,get(record,"fields"));
            if(!quests.empty())blocks.push_back(quests);
            auto glyphs=glyph_block(s,get(record,"fields"));
            if(!glyphs.empty())blocks.push_back(glyphs);
            auto inventory=inventory_block(s,get(record,"fields"));
            if(!inventory.empty())blocks.push_back(inventory);
            auto skills=skill_block(*this,s,get(record,"fields"));
            if(!skills.empty())blocks.push_back(skills);
            bool sites_changed = false, projects_changed = false;
            for (unsigned i = 0; i < 8; ++i)
            {
                auto const &changes = get(record, "fields").as_object();
                sites_changed |=
                    changes.contains(std::to_string(field_index("PLAYER_FIELD_RESEARCH_SITE_1") + i));
                projects_changed |=
                    changes.contains(std::to_string(field_index("PLAYER_FIELD_RESEARCH_PROJECT_1") + i));
            }
            if (sites_changed || projects_changed)
            {
                auto values = field_values(owner.self_snapshot, owner.character);
                auto const &active = get(values, "ActivePlayerData");
                Value sites, projects;
                if (sites_changed)
                    sites = get(active, "ResearchSites").as_array()[0];
                if (projects_changed)
                {
                    Array ids;
                    for (auto const &r : get(active, "Research").as_array()[0].as_array())
                        ids.push_back(get(r, "ResearchProjectID"));
                    projects = ids;
                }
                blocks.push_back(research_block(owner.guid(), sites, projects));
            }
        }
        else if (type == 0 && owner.visible_units.contains(guid))
        {
            auto &snapshot = owner.visible_units.at(guid);
            merge_fields(snapshot, record);
            bool player=integer(get(snapshot,"kind"))==4;
            auto const &character=player ? get(snapshot,"public_character") : owner.character;
            auto scalar = scalar_block(snapshot, character, get(record, "fields"));
            if (!scalar.empty())
                blocks.push_back(scalar);
            if(player)
            {
                auto guild=guild_block(snapshot,character,get(record,"fields"),0);
                if(!guild.empty())blocks.push_back(guild);
                auto equipment=inventory_block(snapshot,get(record,"fields"),0);
                if(!equipment.empty())blocks.push_back(equipment);
            }
        }
    }
    if (blocks.empty() && removed.empty())
        return {};
    return Packet{"SMSG_UPDATE_OBJECT", object_packet(map, blocks, removed)};
}
} // namespace bridge
