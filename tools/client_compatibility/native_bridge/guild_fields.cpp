#include "guild_fields.hpp"

namespace bridge
{
Array guild_identity(std::uint64_t native)
{
    if(!native)return {0,0};
    if(native>>52!=0x1ff || !(native&0xffffffff) || (native>>32&0xfffff))
        throw std::runtime_error("invalid native guild identity");
    return {native&0xffffffff,guild_high()};
}
void guild_fields(Protocol const &protocol,Value const &snapshot,Object &unit,Object &player)
{
    auto low=protocol.field(snapshot,"OBJECT_FIELD_DATA"),high=protocol.field(snapshot,"OBJECT_FIELD_DATA",1);
    unit["GuildGUID"]=integer(get(snapshot,"kind"))==4 ? guild_identity(low|(std::uint64_t(high)<<32)) : Array{0,0};
    for(auto const &[modern,native]:std::initializer_list<std::pair<char const *,char const *>>{
        {"GuildRankID","PLAYER_GUILDRANK"},{"GuildDeleteDate","PLAYER_GUILDDELETE_DATE"},
        {"GuildLevel","PLAYER_GUILDLEVEL"},{"GuildTimeStamp","PLAYER_GUILD_TIMESTAMP"}})
        player[modern]=protocol.field(snapshot,native);
}
Bytes Protocol::guild_block(Value const &snapshot,Value const &character,Value const &changed,unsigned visibility) const
{
    auto has=[&](char const *name,unsigned offset=0)
    {return changed.as_object().contains(std::to_string(field_index(name)+offset));};
    bool guild=has("OBJECT_FIELD_DATA") || has("OBJECT_FIELD_DATA",1);
    struct Scalar {char const *name;char const *native;unsigned index;char format;};
    Scalar const scalars[]={{"PlayerFlags","PLAYER_FLAGS",9,'I'},
        {"PlayerFlagsEx","PLAYER_FLAGS",10,'I'},
        {"GuildRankID","PLAYER_GUILDRANK",11,'I'},{"GuildDeleteDate","PLAYER_GUILDDELETE_DATE",12,'I'},
        {"GuildLevel","PLAYER_GUILDLEVEL",13,'i'},{"GuildTimeStamp","PLAYER_GUILD_TIMESTAMP",22,'i'}};
    unsigned mask=0;for(auto const &field:scalars)if(has(field.native))mask|=1u<<field.index;
    if(!guild && !mask)return {};
    auto values=field_values(snapshot,character);
    Writer data;data.pack("BBBI",{visibility,0,3,(guild ? 1u<<5 : 0)|(mask ? 1u<<6 : 0)});
    if(guild)
    {
        // UnitData group 96 and GuildGUID 108, eight mask blocks.
        data.bits(1u<<3,8).bits(1u|(1u<<12),32).flush();
        data.guid(get(get(values,"UnitData"),"GuildGUID"));
    }
    if(mask)
    {
        // PlayerData has five blocks and the quest-log-skip bit after them.
        data.bits(1,5).bits(mask|1u,32).bits(0,1).flush();
        for(auto const &field:scalars)if(mask&(1u<<field.index))
            data.pack(std::string(1,field.format),{get(get(values,"PlayerData"),field.name)});
    }
    return Writer().pack("B",{0}).guid(integer(get(snapshot,"guid")),player_high())
        .put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
}
}
