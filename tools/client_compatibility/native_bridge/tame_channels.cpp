// Native Spell::SendChannelStart/Update to pinned WPP 4.4.2 SpellHandler.
#include "tame_channels.hpp"

namespace bridge
{
void arm_tame_channel(State &owner,unsigned counter)
{
    for(auto &[id,cast]:owner.casts)
    {
        if(signed_integer(get(cast,"spell"))!=1515)continue;
        cast.as_object()["tame_channel_pending"]=id==counter;
        cast.as_object()["tame_channel_started"]=false;
    }
}
Reply tame_channel_response(State &owner,std::string const &name,View body)
{
    if(name!="MSG_CHANNEL_START" && name!="MSG_CHANNEL_UPDATE")return {};
    Reader r(body);auto caster=native_guid(r);std::uint32_t duration;int spell=1515;
    if(name=="MSG_CHANNEL_START")
    {
        spell=r.take<std::int32_t>();duration=r.take<std::uint32_t>();
        // Native SpellPackets writes byte booleans. Pinned modern WPP reads
        // bits instead. UI153 retained only the 12-byte length, not this body.
        if(r.take<std::uint8_t>() || r.take<std::uint8_t>())
            throw std::runtime_error("unsupported tame channel optional payload");
    }
    else duration=r.take<std::uint32_t>();
    r.end();
    if(!owner.created || owner.guid()!=caster || integer(get(owner.character,"class"))!=3 || spell!=1515)return {};
    if(duration>60000 || (name=="MSG_CHANNEL_START" && !duration))
        throw std::runtime_error("invalid native tame channel duration");
    Value *pending=nullptr;
    for(auto &[id,cast]:owner.casts)
        if(signed_integer(get(cast,"spell"))==1515 && truth(get(cast,"tame_channel_pending")))
        {
            if(pending)throw std::runtime_error("ambiguous native tame channel");
            pending=&cast;
        }
    if(!pending)return {};
    bool started=truth(get(*pending,"tame_channel_started"));
    if(name=="MSG_CHANNEL_START")
    {
        if(started)throw std::runtime_error("duplicate native tame channel start");
        auto packet=Writer().guid(caster,player_high()).pack("iII",{1515,get(*pending,"visual"),duration})
            .bits(0,1).bits(0,1).flush().finish();
        pending->as_object()["tame_channel_started"]=true;
        return Packet{"SMSG_SPELL_CHANNEL_START",std::move(packet)};
    }
    if(!started)return {};
    auto packet=Writer().guid(caster,player_high()).put<std::uint32_t>(duration).finish();
    if(!duration)
    {
        pending->as_object()["tame_channel_started"]=false;
        pending->as_object()["tame_channel_pending"]=false;
    }
    return Packet{"SMSG_SPELL_CHANNEL_UPDATE",std::move(packet)};
}

bool owned_tame_probe(std::filesystem::path const &root,std::string const &direction,
    std::string const &name,View body,std::string const &session,double now)
{
    bool start=name=="MSG_CHANNEL_START" && direction=="from_native";
    bool update=name=="MSG_CHANNEL_UPDATE" && direction=="from_native";
    bool added=name=="SMSG_PET_ADDED" && direction=="from_native";
    bool delivered=(name=="SMSG_SPELL_CHANNEL_START" || name=="SMSG_SPELL_CHANNEL_UPDATE") && direction=="to_client";
    if(!start && !update && !added && !delivered)return false;
    try
    {
        auto path=root/"run/owned_tame_request_probe.json";
        if(!std::filesystem::is_regular_file(path) || std::filesystem::file_size(path)>4096)return false;
        auto c=load_json(path);auto created=number(get(c,"created_at")),expires=number(get(c,"expires_at"));
        if(str(get(c,"schema"))!="client442_owned_tame_request_probe_v1" || integer(get(c,"owner"))!=6 ||
            str(get(c,"session"))!=session || created>now || expires<=now || expires<=created || expires-created>120)return false;
        Reader r(body);
        if(added)
        {
            if(r.take<std::int32_t>()!=1 || r.take<std::int32_t>()!=0 || r.take<std::uint8_t>()!=1 ||
                r.take<std::int32_t>()!=299 || r.take<std::int32_t>()<=4)return false;
            auto size=r.bits(8);if(size!=4)return false;
            auto text=r.raw(size);if(std::string_view(reinterpret_cast<char const *>(text.data()),text.size())!="Wolf")return false;
            // PetPackets::PetAdded::Write uses ByteBuffer's string insertion,
            // which includes a terminal NUL after the separately written length.
            if(r.take<std::uint8_t>()!=0)return false;
        }
        else if(delivered)
        {
            if(r.guid()!=Array{6,player_high()})return false;
            if(name=="SMSG_SPELL_CHANNEL_START")
            {
                if(r.take<std::int32_t>()!=1515)return false;
                r.take<std::uint32_t>();auto duration=r.take<std::uint32_t>();
                if(!duration || duration>60000 || r.bits(1) || r.bits(1))return false;
            }
            else if(r.take<std::uint32_t>()>60000)return false;
        }
        else
        {
            if(native_guid(r)!=6)return false;
            if(start && r.take<std::int32_t>()!=1515)return false;
            auto duration=r.take<std::uint32_t>();if(duration>60000 || (start && !duration))return false;
            if(start && (r.take<std::uint8_t>() || r.take<std::uint8_t>()))return false;
        }
        r.end();return true;
    }
    catch(std::exception const &){return false;}
}
}
