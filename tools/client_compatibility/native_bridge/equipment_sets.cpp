// WPP 28fc3d V4_4_0 equipment parser (4.4.1+ ordering), native Player/CharacterHandler.
#include "equipment_sets.hpp"
#include "protocol.hpp"
#include <algorithm>
#include <array>

namespace bridge
{
namespace
{
constexpr unsigned slots=19,max_sets=10;
std::string text(Reader &r,unsigned bound)
{
    std::string s;
    for(unsigned i=0;i<=bound;++i)
    {
        auto c=r.take<char>();if(!c)return s;s+=c;
    }
    throw std::runtime_error("native equipment-set string exceeds bound");
}
std::string text(Reader &r,unsigned size,unsigned bound)
{
    if(size>bound)throw std::runtime_error("equipment-set string exceeds native bound");
    auto value=r.raw(size);std::string s(value.begin(),value.end());
    if(s.find('\0')!=std::string::npos)throw std::runtime_error("embedded equipment-set terminator");
    return s;
}
std::uint64_t item(State const &owner,Array const &guid)
{
    auto low=integer(guid[0]),high=integer(guid[1]);
    if(!low && !high)return 0;
    if(low==1 && !high)return 1; // Equipment manager's ignored-slot sentinel.
    auto native=(0x4000ull<<48)|low;
    if(!low || low>0xffffffff || high!=((3ull<<58)|(1ull<<42)) || !owner.inventory_items.contains(native))
        throw std::runtime_error("equipment-set item is outside owned native inventory");
    return native;
}
void owned(State const &owner,std::uint64_t guid)
{
    if(!guid || !owner.equipment_sets.owned.contains(guid))
        throw std::runtime_error("equipment set lacks an owned native identity");
}
}
Reply equipment_request(State &owner,std::string const &name,View body)
{
    Reader r(body);Writer w;
    if(name=="CMSG_SAVE_EQUIPMENT_SET")
    {
        auto type=r.take<std::int32_t>();auto guid=r.take<std::uint64_t>();
        auto index=r.take<std::uint32_t>(),ignore=r.take<std::uint32_t>();
        if(type || index>=max_sets || ignore>>slots)throw std::runtime_error("equipment set has no native type/index/mask equivalent");
        if(guid){owned(owner,guid);if(owner.equipment_sets.owned.at(guid)!=index)throw std::runtime_error("equipment set index changed");}
        else if(std::ranges::any_of(owner.equipment_sets.owned,[&](auto const &s){return s.second==index;}) ||
                std::ranges::find(owner.equipment_sets.saving,index)!=owner.equipment_sets.saving.end())
            throw std::runtime_error("new equipment-set index is already occupied");
        std::array<std::uint64_t,slots> pieces{};
        for(unsigned i=0;i<slots;++i)
        {
            pieces[i]=item(owner,r.guid());auto appearance=r.take<std::int32_t>();
            if(appearance!=0 && appearance!=-1)throw std::runtime_error("appearance-set save is not a native equipment set");
            if(ignore&(1u<<i))pieces[i]=1;
        }
        for(unsigned i=0;i<6;++i)
        {
            auto value=r.take<std::int32_t>();
            if(value!=0 && value!=-1)throw std::runtime_error("equipment-set cosmetic field has no native equivalent");
        }
        auto assigned=r.bits(1);auto name_size=r.bits(8),icon_size=r.bits(9);r.align();
        if(assigned)throw std::runtime_error("equipment-set assigned specialization is not persisted natively");
        auto label=text(r,name_size,31),icon=text(r,icon_size,100);r.end();
        if(label.empty())throw std::runtime_error("empty equipment-set name");
        packed(w,guid).put(index).raw(label).put<std::uint8_t>(0).raw(icon).put<std::uint8_t>(0);
        for(auto piece:pieces)packed(w,piece);
        if(!guid)owner.equipment_sets.saving.push_back(index);
        return Packet{"CMSG_EQUIPMENT_SET_SAVE",w.finish()};
    }
    if(name=="CMSG_DELETE_EQUIPMENT_SET")
    {
        auto guid=r.take<std::uint64_t>();r.end();owned(owner,guid);
        packed(w,guid);owner.equipment_sets.owned.erase(guid);
        return Packet{"CMSG_EQUIPMENT_SET_DELETE",w.finish()};
    }
    if(name=="CMSG_USE_EQUIPMENT_SET")
    {
        auto hints=r.bits(2);r.align();
        for(unsigned i=0;i<hints;++i)
        {auto b=r.take<std::uint8_t>(),s=r.take<std::uint8_t>();Protocol::inventory_position(b,s);}
        for(unsigned i=0;i<slots;++i)
        {
            auto piece=item(owner,r.guid());auto b=r.take<std::uint8_t>(),s=r.take<std::uint8_t>();
            if(piece && piece!=1){auto pos=Protocol::inventory_position(b,s);b=pos.first;s=pos.second;}
            packed(w,piece).put(b).put(s);
        }
        auto guid=r.take<std::uint64_t>();r.end();owned(owner,guid);
        if(owner.equipment_sets.using_sets.size()>=16)throw std::runtime_error("too many outstanding equipment-set uses");
        owner.equipment_sets.using_sets.push_back(guid);
        return Packet{"CMSG_EQUIPMENT_SET_USE",w.finish()};
    }
    return {};
}
Reply equipment_response(State &owner,std::string const &name,View body)
{
    Reader r(body);Writer w;
    if(name=="SMSG_EQUIPMENT_SET_LIST")
    {
        auto count=r.take<std::uint32_t>();if(count>max_sets)throw std::runtime_error("native equipment-set count exceeds bound");
        std::unordered_map<std::uint64_t,std::uint32_t> identities;w.put(count);
        for(unsigned n=0;n<count;++n)
        {
            auto guid=native_guid(r);auto index=r.take<std::uint32_t>();
            if(!guid || index>=max_sets || identities.contains(guid) ||
                std::ranges::any_of(identities,[&](auto const &s){return s.second==index;}))
                throw std::runtime_error("invalid native equipment-set identity/index");
            identities[guid]=index;auto label=text(r,31),icon=text(r,100);
            std::array<std::uint64_t,slots> pieces{};std::uint32_t ignore=0;
            for(unsigned i=0;i<slots;++i){pieces[i]=native_guid(r);if(pieces[i]==1){ignore|=1u<<i;pieces[i]=0;}}
            w.put<std::int32_t>(0).put(guid).put(index).put(ignore);
            for(auto piece:pieces)w.guid(Protocol::inventory_guid(piece)).put<std::int32_t>(0);
            w.zeros(24).bits(0,1).bits(label.size(),8).bits(icon.size(),9).flush().raw(label).raw(icon);
        }
        r.end();owner.equipment_sets.owned=std::move(identities);
        return Packet{"SMSG_LOAD_EQUIPMENT_SET",w.finish()};
    }
    if(name=="SMSG_EQUIPMENT_SET_SAVED")
    {
        auto index=r.take<std::uint32_t>();auto guid=native_guid(r);r.end();
        if(!guid || index>=max_sets || owner.equipment_sets.saving.empty() || owner.equipment_sets.saving.front()!=index)
            throw std::runtime_error("unattributed native equipment-set acknowledgement");
        owner.equipment_sets.saving.pop_front();owner.equipment_sets.owned[guid]=index;
        return Packet{"SMSG_EQUIPMENT_SET_ID",w.put<std::int32_t>(0).put(index).put(guid).finish()};
    }
    if(name=="SMSG_EQUIPMENT_SET_USE_RESULT")
    {
        auto reason=r.take<std::uint8_t>();r.end();
        if(owner.equipment_sets.using_sets.empty())throw std::runtime_error("unattributed native equipment-set result");
        auto guid=owner.equipment_sets.using_sets.front();owner.equipment_sets.using_sets.pop_front();
        // Native HandleEquipmentSetUse always emits zero. Item failures arrive
        // separately through the existing inventory-error translator.
        if(reason)throw std::runtime_error("unmapped native equipment-set reason");
        return Packet{"SMSG_USE_EQUIPMENT_SET_RESULT",w.put<std::int32_t>(0).put(guid).finish()};
    }
    return {};
}
}
