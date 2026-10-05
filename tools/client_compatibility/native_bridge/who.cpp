// Modern layout pinned to TrinityCore 6426c2bd/WhoPackets and QueryPackets.
// Visibility and search results come exclusively from the native Who handler.
#include "who.hpp"
#include "public_identity.hpp"
#include "guild_packets.hpp"
#include <cctype>

namespace bridge
{
namespace
{
std::string text(Reader &r,unsigned size)
{
    auto raw=r.raw(size);std::string value(raw.begin(),raw.end());
    if(value.find('\0')!=std::string::npos)throw std::runtime_error("Who text contains a native terminator");
    return value;
}
std::string folded(std::string value)
{
    for(auto &c:value)
    {
        if(static_cast<unsigned char>(c)>127)throw std::runtime_error("exact Who name requires ASCII case folding");
        c=std::tolower(static_cast<unsigned char>(c));
    }
    return value;
}
}
Reply who_request(State &owner,std::string const &opcode,View body)
{
    if(opcode!="CMSG_WHO")return {};
    if(!owner.created || !owner.guid())throw std::runtime_error("Who request outside owned active character");
    Reader r(body);auto areas=r.bits(4),addon=r.bits(1);
    auto min=r.take<std::int32_t>(),max=r.take<std::int32_t>();
    auto race=r.take<std::int64_t>();auto klass=r.take<std::int32_t>();
    auto nl=r.bits(6),rl=r.bits(9),gl=r.bits(7),grl=r.bits(9),wc=r.bits(3);
    auto enemies=r.bits(1),arena=r.bits(1),exact=r.bits(1),server=r.bits(1);r.align();
    if(areas>10 || wc>4 || min<0 || max>255 || min>max || addon || enemies || arena ||
       (race!=-1 && race!=0) || klass<-1)
        throw std::runtime_error("unsupported Who filters or counts");
    std::vector<std::string> words;std::vector<std::int32_t> zones;
    for(unsigned i=0;i<wc;++i){auto length=r.bits(7);words.push_back(text(r,length));r.align();}
    auto name=text(r,nl),realm=text(r,rl),guild=text(r,gl),guild_realm=text(r,grl);
    if((!realm.empty() && realm!="Client442Lab") || (!guild_realm.empty() && guild_realm!="Client442Lab"))
        throw std::runtime_error("Who request outside local realm");
    if(server)
    {
        r.take<std::int32_t>();auto locale=r.take<std::int32_t>();auto address=r.take<std::uint32_t>();
        if(locale!=0 || address!=1)throw std::runtime_error("unsupported Who server metadata");
    }
    auto id=r.take<std::uint32_t>();auto origin=r.take<std::uint8_t>();
    if(origin<1 || origin>3)throw std::runtime_error("invalid Who origin");
    for(unsigned i=0;i<areas;++i)
    {auto area=r.take<std::int32_t>();if(area<0)throw std::runtime_error("invalid Who area");zones.push_back(area);}
    r.end();if(exact)folded(name);
    Writer w;w.put(min).put(max).raw(name).put<std::uint8_t>(0).raw(guild).put<std::uint8_t>(0)
        .put<std::int32_t>(-1).put(klass).put<std::uint32_t>(areas);
    for(auto zone:zones)w.put(zone);
    w.put<std::uint32_t>(wc);for(auto const &word:words)w.raw(word).put<std::uint8_t>(0);
    if(!owner.who_state)owner.who_state=std::make_shared<WhoState>();
    auto &state=*owner.who_state;
    // Native replies have no request ID. Never replace an unanswered query,
    // even after a timeout, because its late reply could be misattributed.
    if(state.pending)throw std::runtime_error("Who query already awaiting native reply");
    state.pending=true;state.request_id=id;state.exact=exact;state.name=name;++state.serial;
    return Packet{opcode,w.finish()};
}
Array native_who(View body)
{
    Reader r(body);auto count=r.take<std::uint32_t>(),total=r.take<std::uint32_t>();
    if(count>50 || total!=count)throw std::runtime_error("native Who counts exceed supported contract");
    Array rows;std::unordered_set<std::string> names;
    for(unsigned i=0;i<count;++i)
    {
        auto name_bytes=native_text(r),guild_bytes=native_text(r);
        std::string name(name_bytes.begin(),name_bytes.end()),guild(guild_bytes.begin(),guild_bytes.end());
        auto level=r.take<std::uint32_t>(),klass=r.take<std::uint32_t>(),race=r.take<std::uint32_t>();
        auto gender=r.take<std::uint8_t>();auto area=r.take<std::uint32_t>();
        if(name.empty() || name.size()>63 || guild.size()>127 || !names.insert(name).second ||
           !level || level>255 || !klass || klass>11 || !race || race>22 || gender>1 || area>0x7fffffff)
            throw std::runtime_error("invalid native Who public entry");
        rows.push_back(Object{{"name",name},{"guild_name",guild},{"level",level},{"class",klass},
            {"race",race},{"gender",gender},{"area",area}});
    }
    r.end();return rows;
}
Bytes who_response(WhoState const &request,Array const &rows,Array const &identities)
{
    if(!request.pending)throw std::runtime_error("Who reply has no pending request");
    if(rows.size()>50)throw std::runtime_error("Who response exceeds native count bound");
    std::unordered_map<std::string,Value const *> names;
    for(auto const &identity:identities)
        if(!names.emplace(str(get(identity,"name")),&identity).second)
            throw std::runtime_error("ambiguous Who public identity");
    std::unordered_set<std::uint64_t> guids;
    Array selected;
    for(auto const &row:rows)
    {
        auto name=str(get(row,"name"));auto found=names.find(name);
        if(found==names.end())throw std::runtime_error("native Who name has no authoritative identity");
        auto const &identity=*found->second;auto guid=integer(get(identity,"guid"));
        auto guild=integer(get(identity,"guild_id"));
        if(!guid || guid>0xffffffff || !guids.insert(guid).second || guild>0xffffffff ||
           str(get(identity,"guild_name"))!=str(get(row,"guild_name")) ||
           (guild==0)!=str(get(row,"guild_name")).empty())
            throw std::runtime_error("native Who player or guild identity differs");
        for(auto key:{"race","gender","class","level"})
            if(get(identity,key)!=get(row,key))throw std::runtime_error("native Who public attributes differ");
        if(request.exact && folded(name)!=folded(request.name))continue;
        auto enriched=row.as_object();enriched["guid"]=guid;enriched["guild_id"]=guild;selected.push_back(enriched);
    }
    Writer w;w.put(request.request_id).bits(selected.size(),6).flush();
    for(auto const &row:selected)
    {
        public_player_lookup(w,row,Array{get(row,"guid"),player_high()});
        auto guild=integer(get(row,"guild_id"));auto name=str(get(row,"guild_name"));
        w.guid(guild,guild?guild_high():0).put<std::uint32_t>(guild?1:0)
            .put<std::int32_t>(integer(get(row,"area"))).bits(name.size(),7).bits(0,1).flush().raw(name);
    }
    return w.finish();
}
Reply who_complete(State &owner,View body,Array const &identities)
{
    auto rows=native_who(body);
    if(!owner.created || !owner.who_state || !owner.who_state->pending)return {};
    auto reply=who_response(*owner.who_state,rows,identities);owner.who_state->pending=false;
    return Packet{"SMSG_WHO",std::move(reply)};
}
}
