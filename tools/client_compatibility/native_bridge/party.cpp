// Wire contracts: pinned cata_classic PartyPackets and native PartyPackets.
#include "protocol.hpp"
#include <array>

namespace bridge
{
namespace
{
Value decode_update(View body)
{
    Reader r(body);Object data;
    data["flags"] = r.take<std::uint8_t>();data["subgroup"] = r.take<std::uint8_t>();
    data["member_flags"] = r.take<std::uint8_t>();data["role"] = r.take<std::uint8_t>();
    if (integer(data["flags"]) & 8) throw std::runtime_error("LFG party update requires its own contract");
    data["group"] = r.take<std::uint64_t>();data["sequence"] = r.take<std::uint32_t>();
    auto count = r.take<std::uint32_t>();
    if (count > 39) throw std::runtime_error("native group roster exceeds bound");
    Array members;
    for (unsigned i=0; i<count; ++i)
    {
        auto raw = native_text(r);std::string name(raw.begin(),raw.end());
        auto guid = r.take<std::uint64_t>();auto connected = r.take<std::uint8_t>();
        auto subgroup = r.take<std::uint8_t>(), flags = r.take<std::uint8_t>(), role = r.take<std::uint8_t>();
        if (!guid || guid > 0xffffffff || name.empty() || name.size() > 63 || subgroup > 7)
            throw std::runtime_error("invalid native group member");
        members.push_back(Object{{"guid",guid},{"name",name},{"connected",connected & 1},
            {"subgroup",subgroup},{"flags",flags},{"role",role}});
    }
    data["members"] = members;data["leader"] = r.take<std::uint64_t>();
    if (count)
    {
        data["loot_method"] = r.take<std::uint8_t>();data["loot_master"] = r.take<std::uint64_t>();
        data["loot_threshold"] = r.take<std::uint8_t>();data["dungeon"] = r.take<std::uint8_t>();
        data["raid"] = r.take<std::uint8_t>();
    }
    r.end();return data;
}
Writer &player(Writer &w, std::uint64_t guid)
{
    return w.guid(guid, guid ? player_high() : 0);
}
}
Array Protocol::party_members(View body)
{
    Array result;auto data = decode_update(body);
    for (auto const &member : get(data,"members").as_array()) result.push_back(get(member,"guid"));
    return result;
}
Reply Protocol::party_response(State &owner, std::string const &name, View body, Array const &identities)
{
    Reader r(body);Writer w;
    if (name == "SMSG_PARTY_UPDATE")
    {
        auto data = decode_update(body);auto flags = integer(get(data,"flags"));
        auto group = integer(get(data,"group"));auto members = get(data,"members").as_array();
        bool destroyed = flags & 16;
        if (!destroyed)
            members.insert(members.begin(),Object{{"guid",owner.guid()},{"name",get(owner.character,"name")},
                {"connected",1},{"subgroup",get(data,"subgroup")},{"flags",get(data,"member_flags")},{"role",get(data,"role")}});
        std::unordered_set<std::uint64_t> roster;
        for (auto const &m : members) roster.insert(integer(get(m,"guid")));
        std::erase_if(owner.party_states,[&](auto const &item){return !roster.contains(item.first);});
        owner.party_guid = Array{group & 0xffffffff, group ? 27ull<<58 : 0};
        w.pack("HBBi",{flags,0,destroyed ? 0 : 1,destroyed ? -1 : 0}).guid(owner.party_guid)
            .pack("I",{get(data,"sequence")});
        player(w,integer(get(data,"leader"))).pack("BiI",{1,0,members.size()})
            .bits(0,1).bits(!destroyed && members.size()>1,1).bits(!destroyed && members.size()>1,1).flush();
        std::unordered_map<std::uint64_t,Value> metadata;
        for (auto const &v : identities) metadata[integer(get(v,"guid"))] = v;
        for (auto const &m : members)
        {
            auto guid = integer(get(m,"guid"));auto pos = metadata.find(guid);
            if (pos == metadata.end()) throw std::runtime_error("group member metadata is absent");
            auto race = integer(get(pos->second,"race"));
            auto faction = (race==2 || race==5 || race==6 || race==8 || race==9 || race==10) ? 0 : 1;
            auto text = str(get(m,"name"));
            w.bits(text.size(),6).bits(1,6).bits(integer(get(m,"connected")),1).bits(0,1).bits(0,1);
            player(w,guid).pack("5B",{get(m,"subgroup"),get(m,"flags"),get(m,"role"),get(pos->second,"class"),faction}).raw(text);
        }
        if (!destroyed && members.size()>1)
        {
            w.pack("B",{get(data,"loot_method")});player(w,integer(get(data,"loot_master")));
            auto raid = integer(get(data,"raid"));
            // Native raid values 0..3 become modern difficulty IDs 3..6.
            if (raid > 3) throw std::runtime_error("unsupported native raid difficulty");
            w.pack("BIII",{get(data,"loot_threshold"),integer(get(data,"dungeon"))+1,raid+3,raid+3});
        }
        if (destroyed) owner.party_guid = Array{0,0};
        return Packet{name,w.finish()};
    }
    if (name == "SMSG_PARTY_INVITE")
    {
        std::array<std::uint8_t,8> guid{};
        bool must_bnet = r.bits(1);guid[0] = r.bits(1);guid[3] = r.bits(1);guid[2] = r.bits(1);
        bool accept = r.bits(1);guid[6] = r.bits(1);guid[5] = r.bits(1);auto realm_length = r.bits(9);
        guid[4] = r.bits(1);auto name_length = r.bits(7), slots = r.bits(24);bool cross = r.bits(1);
        guid[1] = r.bits(1);guid[7] = r.bits(1);
        if (slots > 128 || name_length > 63) throw std::runtime_error("invalid native invitation lengths");
        auto byte = [&](unsigned i){if(guid[i]) guid[i] = r.take<std::uint8_t>() ^ 1;};
        byte(1);byte(4);r.take<std::uint32_t>();auto roles = r.take<std::uint32_t>(), completed = r.take<std::uint32_t>();
        for(auto i:{6,0,2,3})byte(i);
        auto lfg=r.unpack(std::string(slots,'I'));byte(5);auto realm=r.raw(realm_length);byte(7);
        auto inviter=r.raw(name_length);auto realm_id=r.take<std::uint32_t>();r.end();
        std::uint64_t low=0;for(unsigned i=0;i<8;++i)low|=static_cast<std::uint64_t>(guid[i])<<(8*i);
        if (!low || low>0xffffffff || realm_id!=1 || cross || roles>15) throw std::runtime_error("unsupported invitation identity");
        std::string actual(realm.begin(),realm.end()), normalized;
        for(char c:actual) if(c!=' ') normalized+=c;
        w.bits(accept,1).bits(0,1).bits(cross,1).bits(must_bnet,1).bits(0,1).bits(0,1).bits(name_length,6).bits(0,1)
            .put(realm_id).bits(1,1).bits(0,1).bits(actual.size(),8).bits(normalized.size(),8).raw(actual).raw(normalized);
        player(w,low).guid().pack("HBII",{0,roles,slots,completed}).raw(inviter).pack(std::string(slots,'I'),lfg);
        return Packet{name,w.finish()};
    }
    if (name == "SMSG_PARTY_COMMAND_RESULT")
    {
        auto command=r.take<std::uint32_t>();auto text=native_text(r);auto result=r.take<std::uint32_t>();
        auto result_data=r.take<std::uint32_t>();auto guid=r.take<std::uint64_t>();r.end();
        if(command>15 || result>63 || text.size()>511 || guid>0xffffffff)throw std::runtime_error("invalid native party result");
        w.bits(text.size(),9).bits(command,4).bits(result,6).put(result_data);player(w,guid).raw(text);
        return Packet{name,w.finish()};
    }
    if (name == "SMSG_GROUP_DECLINE" || name == "SMSG_GROUP_SET_LEADER")
    {
        auto text=native_text(r);r.end();
        if(name=="SMSG_GROUP_SET_LEADER")w.put<std::uint8_t>(0);
        w.bits(text.size(),9).raw(text);
        return Packet{name=="SMSG_GROUP_SET_LEADER" ? "SMSG_GROUP_NEW_LEADER" : name,w.finish()};
    }
    if (name == "SMSG_GROUP_DESTROYED")
    {
        r.end();return Packet{name,{}};
    }
    if (name == "MSG_RAID_READY_CHECK")
    {
        auto starter = r.take<std::uint64_t>();r.end();
        w.put<std::uint8_t>(0).guid(owner.party_guid);player(w,starter).put<std::uint32_t>(30000);
        return Packet{"SMSG_READY_CHECK_STARTED",w.finish()};
    }
    if (name == "MSG_RAID_READY_CHECK_CONFIRM")
    {
        auto guid=r.take<std::uint64_t>();auto ready=r.take<std::uint8_t>();r.end();
        if(ready>1)throw std::runtime_error("invalid native ready answer");
        w.guid(owner.party_guid);player(w,guid).bits(ready,1);
        return Packet{"SMSG_READY_CHECK_RESPONSE",w.finish()};
    }
    if (name == "MSG_RAID_READY_CHECK_FINISHED")
    {
        r.end();w.put<std::uint8_t>(0).guid(owner.party_guid);
        return Packet{"SMSG_READY_CHECK_COMPLETED",w.finish()};
    }
    return {};
}
} // namespace bridge
