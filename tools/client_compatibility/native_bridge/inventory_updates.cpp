// Sparse masks follow the pinned UpdateFields::{WriteUpdate}, not create layouts.
#include "protocol.hpp"
#include <map>

namespace bridge
{
namespace
{
template<std::size_t N> void set(std::array<std::uint32_t,N> &mask,unsigned bit)
{mask.at(bit/32)|=1u<<(bit%32);}
template<std::size_t N> void write_mask(Writer &w,std::array<std::uint32_t,N> const &mask,unsigned width)
{
    std::uint64_t presence=0;
    for(unsigned i=0;i<N;++i)if(mask[i])presence|=1ull<<i;
    if(N>32){w.put<std::uint32_t>(presence);w.bits(presence>>32,width-32);}
    else w.bits(presence,width);
    for(auto part:mask)if(part)w.bits(part,32);
}
unsigned modern_slot(unsigned old)
{return old<19 ? old : old<23 ? old+11 : old<39 ? old+12 : old+20;}
Bytes block(Array const &guid,Writer &data)
{
    return Writer().put<std::uint8_t>(0).guid(guid)
        .put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
}
}
Bytes Protocol::inventory_block(Value const &snapshot,Value const &changed,unsigned visibility) const
{
    auto has=[&](char const *name,unsigned offset=0)
    {return changed.as_object().contains(std::to_string(field_index(name)+offset));};
    auto pair=[&](char const *name,unsigned offset)
    {return inventory_guid(static_cast<std::uint64_t>(field(snapshot,name,offset))|
        (static_cast<std::uint64_t>(field(snapshot,name,offset+1))<<32));};
    std::map<unsigned,Array> slots;std::map<unsigned,std::uint32_t> visible;
    std::map<unsigned,std::pair<bool,bool>> buyback;
    std::map<unsigned,unsigned> damage;
    bool flags=has("PLAYER_FLAGS");
    bool coinage=(visibility&1) && (has("PLAYER_FIELD_COINAGE") || has("PLAYER_FIELD_COINAGE",1));
    if(visibility&1)for(unsigned i=0;i<12;++i)
    {
        bool price=has("PLAYER_FIELD_BUYBACK_PRICE_1",i),stamp=has("PLAYER_FIELD_BUYBACK_TIMESTAMP_1",i);
        if(price || stamp)buyback[i]={price,stamp};
    }
    if(visibility&1)for(unsigned i=0;i<7;++i)
    {
        unsigned parts=(has("PLAYER_FIELD_MOD_DAMAGE_DONE_POS",i)?1:0)|
            (has("PLAYER_FIELD_MOD_DAMAGE_DONE_NEG",i)?2:0)|(has("PLAYER_FIELD_MOD_DAMAGE_DONE_PCT",i)?4:0);
        if(parts)damage[i]=parts;
    }
    for(unsigned old=0;old<86;++old)
        if((visibility&1) && (has("PLAYER_FIELD_INV_SLOT_HEAD",old*2) || has("PLAYER_FIELD_INV_SLOT_HEAD",old*2+1)))
            slots.emplace(modern_slot(old),pair("PLAYER_FIELD_INV_SLOT_HEAD",old*2));
    for(unsigned i=0;i<19;++i)
        if(has("PLAYER_VISIBLE_ITEM_1_ENTRYID",i*2))
            visible.emplace(i,field(snapshot,"PLAYER_VISIBLE_ITEM_1_ENTRYID",i*2));
    bool active=!slots.empty() || coinage || !buyback.empty() || !damage.empty();
    bool player=flags || !visible.empty();
    if(!active && !player)return {};
    Writer data;data.pack("BBBI",{visibility,0,3,(active?1u<<7:0u)|(player?1u<<6:0u)});
    if(player)
    {
        std::array<std::uint32_t,5> mask{};
        if(flags){set(mask,0);set(mask,9);}
        if(!visible.empty())set(mask,68);
        for(auto const &[i,id]:visible)set(mask,69+i);
        write_mask(data,mask,5);data.bits(0,1).flush(); // No quest-log skipped mask.
        if(flags)data.put(field(snapshot,"PLAYER_FLAGS"));
        for(auto const &[i,id]:visible)data.bits(3,4).flush().put<std::int32_t>(id);
    }
    if(active)
    {
        std::array<std::uint32_t,46> mask{};
        if(coinage){set(mask,0);set(mask,31);}
        if(!slots.empty())set(mask,131);
        for(auto const &[i,guid]:slots)set(mask,132+i);
        if(!damage.empty())set(mask,288);
        for(auto const &[i,parts]:damage)
        {
            if(parts&1)set(mask,289+i);
            if(parts&2)set(mask,296+i);
            if(parts&4)set(mask,303+i);
        }
        if(!buyback.empty())set(mask,320);
        for(auto const &[i,changed]:buyback)
        {if(changed.first)set(mask,321+i);if(changed.second)set(mask,333+i);}
        write_mask(data,mask,46);data.flush();
        if(coinage)data.put<std::uint64_t>(static_cast<std::uint64_t>(field(snapshot,"PLAYER_FIELD_COINAGE"))|
            (static_cast<std::uint64_t>(field(snapshot,"PLAYER_FIELD_COINAGE",1))<<32));
        for(auto const &[i,guid]:slots)data.guid(guid);
        // The pinned update contract interleaves positive, negative and percent
        // within each school, rather than sorting all child mask indices.
        for(auto const &[i,parts]:damage)
        {
            if(parts&1)data.put<std::int32_t>(field(snapshot,"PLAYER_FIELD_MOD_DAMAGE_DONE_POS",i));
            if(parts&2)data.put<std::int32_t>(field(snapshot,"PLAYER_FIELD_MOD_DAMAGE_DONE_NEG",i));
            if(parts&4)data.put<float>(float_field(snapshot,"PLAYER_FIELD_MOD_DAMAGE_DONE_PCT",i));
        }
        for(auto const &[i,changed]:buyback)
        {
            if(changed.first)data.put(field(snapshot,"PLAYER_FIELD_BUYBACK_PRICE_1",i));
            if(changed.second)data.put<std::int64_t>(field(snapshot,"PLAYER_FIELD_BUYBACK_TIMESTAMP_1",i));
        }
    }
    return block({integer(get(snapshot,"guid")),player_high()},data);
}
Bytes Protocol::item_update(Value const &snapshot,Value const &changed) const
{
    auto has=[&](char const *name,unsigned offset=0)
    {return changed.as_object().contains(std::to_string(field_index(name)+offset));};
    std::map<unsigned,Array> pairs,slots;
    std::map<unsigned,std::pair<char,Value>> scalars;
    std::map<unsigned,std::uint32_t> enchants;
    std::array<std::uint32_t,2> itemmask{},containermask{};
    for(auto const &[name,index]:std::initializer_list<std::pair<char const*,unsigned>>{
        {"ITEM_FIELD_OWNER",3},{"ITEM_FIELD_CONTAINED",4},{"ITEM_FIELD_CREATOR",5},{"ITEM_FIELD_GIFTCREATOR",6}})
        if(has(name) || has(name,1))
        {
            pairs[index]=inventory_guid(static_cast<std::uint64_t>(field(snapshot,name))|
                (static_cast<std::uint64_t>(field(snapshot,name,1))<<32));set(itemmask,0);set(itemmask,index);
        }
    struct Scalar {char const *name;unsigned index;char format;};
    for(auto const &spec:std::initializer_list<Scalar>{{"ITEM_FIELD_STACK_COUNT",7,'I'},
        {"ITEM_FIELD_DURATION",8,'I'},{"ITEM_FIELD_FLAGS",9,'I'},{"ITEM_FIELD_PROPERTY_SEED",10,'i'},
        {"ITEM_FIELD_RANDOM_PROPERTIES_ID",11,'i'},{"ITEM_FIELD_DURABILITY",12,'I'},
        {"ITEM_FIELD_MAXDURABILITY",13,'I'},{"ITEM_FIELD_CREATE_PLAYED_TIME",14,'I'}})
        if(has(spec.name))
        {
            auto value=field(snapshot,spec.name);
            scalars[spec.index]={spec.format,spec.format=='i' ? Value(static_cast<std::int32_t>(value)) : Value(value)};
            set(itemmask,0);set(itemmask,spec.index);
        }
    for(unsigned i=0;i<5;++i)if(has("ITEM_FIELD_SPELL_CHARGES",i))
    {set(itemmask,23);set(itemmask,24+i);scalars[24+i]={'i',static_cast<std::int32_t>(field(snapshot,"ITEM_FIELD_SPELL_CHARGES",i))};}
    for(unsigned i=0;i<13;++i)
    {
        unsigned bits=1;
        for(unsigned p=0;p<3;++p)if(has("ITEM_FIELD_ENCHANTMENT_1_1",i*3+p))bits|=1u<<(p+1);
        if(bits!=1){enchants[i]=bits;set(itemmask,29);set(itemmask,30+i);}
    }
    bool count=integer(get(snapshot,"kind"))==2 && has("CONTAINER_FIELD_NUM_SLOTS");
    if(count){set(containermask,0);set(containermask,1);}
    if(integer(get(snapshot,"kind"))==2)for(unsigned i=0;i<36;++i)
        if(has("CONTAINER_FIELD_SLOT_1",i*2) || has("CONTAINER_FIELD_SLOT_1",i*2+1))
        {
            slots[i]=inventory_guid(static_cast<std::uint64_t>(field(snapshot,"CONTAINER_FIELD_SLOT_1",i*2))|
                (static_cast<std::uint64_t>(field(snapshot,"CONTAINER_FIELD_SLOT_1",i*2+1))<<32));
            set(containermask,2);set(containermask,3+i);
        }
    bool item=itemmask[0] || itemmask[1],container=containermask[0] || containermask[1];
    if(!item && !container)return {};
    Writer data;data.pack("BBBI",{1,0,3,(item?1u<<1:0u)|(container?1u<<2:0u)});
    if(item)
    {
        write_mask(data,itemmask,2);data.flush();
        for(auto const &[i,guid]:pairs)data.guid(guid);
        for(auto const &[i,spec]:scalars)data.pack(std::string(1,spec.first),{spec.second});
        for(auto const &[i,bits]:enchants)
        {
            data.bits(bits,5).flush();
            if(bits&2)data.put<std::int32_t>(field(snapshot,"ITEM_FIELD_ENCHANTMENT_1_1",i*3));
            if(bits&4)data.put(field(snapshot,"ITEM_FIELD_ENCHANTMENT_1_1",i*3+1));
            if(bits&8)data.put<std::int16_t>(field(snapshot,"ITEM_FIELD_ENCHANTMENT_1_1",i*3+2)&65535);
        }
    }
    if(container)
    {
        write_mask(data,containermask,2);data.flush();
        if(count)data.put(field(snapshot,"CONTAINER_FIELD_NUM_SLOTS"));
        for(auto const &[i,guid]:slots)data.guid(guid);
    }
    return block(inventory_guid(integer(get(snapshot,"guid"))),data);
}
}
