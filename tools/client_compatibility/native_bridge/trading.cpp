// Pinned native/modern TradePackets and SharedDefines. Native handlers retain authority.
#include "peer_identity.hpp"

namespace bridge
{
namespace
{
using Guid=std::array<std::uint8_t,8>;
void masks(Reader &r,Guid &guid,std::initializer_list<unsigned> order)
{for(auto i:order)guid[i]=r.bits(1);}
void octets(Reader &r,Guid &guid,std::initializer_list<unsigned> order)
{for(auto i:order)if(guid[i])guid[i]=r.take<std::uint8_t>()^1;}
std::uint64_t value(Guid const &guid)
{std::uint64_t n=0;for(unsigned i=0;i<8;++i)n|=std::uint64_t(guid[i])<<(i*8);return n;}
Array creator(Guid const &guid)
{
    auto n=value(guid);if(n>0xffffffff)throw std::runtime_error("invalid native trade creator");
    return {n,n?player_high():0};
}
void instance(Writer &w,int entry,int seed,int property,int reforge)
{
    w.pack("iii",{entry,seed,property}).bits(0,1).flush().bits(reforge?1:0,6).flush();
    if(reforge)w.pack("Bi",{58,reforge}); // Pinned ITEM_MODIFIER_REFORGE.
}
}
Reply Protocol::trade_request(State const &owner,std::string const &name,View body)
{
    if(!name.ends_with("_TRADE") && name!="CMSG_SET_TRADE_ITEM" && name!="CMSG_CLEAR_TRADE_ITEM" &&
        name!="CMSG_SET_TRADE_GOLD")return {};
    Reader r(body);Writer w;
    if(name=="CMSG_INITIATE_TRADE")
    {
        auto guid=visible_player(owner,r.guid());r.end();if(!guid)return {};
        auto raw=Writer().put(guid).finish();
        for(auto i:{0,3,5,1,4,6,7,2})w.bits(raw[i]!=0,1);
        for(auto i:{7,4,3,5,1,2,6,0})if(raw[i])w.put<std::uint8_t>(raw[i]^1);
    }
    else if(name=="CMSG_BEGIN_TRADE" || name=="CMSG_CANCEL_TRADE" || name=="CMSG_BUSY_TRADE" ||
        name=="CMSG_IGNORE_TRADE" || name=="CMSG_UNACCEPT_TRADE")r.end();
    else if(name=="CMSG_ACCEPT_TRADE")w.put(r.take<std::uint32_t>()),r.end();
    else if(name=="CMSG_SET_TRADE_GOLD")w.put(r.take<std::uint64_t>()),r.end();
    else if(name=="CMSG_CLEAR_TRADE_ITEM")
    {
        auto slot=r.take<std::uint8_t>();r.end();if(slot>6)throw std::runtime_error("invalid trade slot");w.put(slot);
    }
    else if(name=="CMSG_SET_TRADE_ITEM")
    {
        auto slot=r.take<std::uint8_t>(),bag=r.take<std::uint8_t>(),item=r.take<std::uint8_t>();r.end();
        if(slot>6)throw std::runtime_error("invalid trade slot");
        auto [native_bag,native_slot]=inventory_position(bag,item);
        w.pack("BBB",{native_slot,slot,native_bag});
    }
    else return {};
    return Packet{name,w.finish()};
}
Reply Protocol::trade_response(std::string const &name,View body) const
{
    Reader r(body);Writer w;
    if(name=="SMSG_TRADE_STATUS")
    {
        auto same=r.bits(1),native=r.bits(5);
        static std::unordered_map<unsigned,unsigned> const statuses={{0,2},{2,23},{3,19},{4,14},{5,18},
            {6,4},{7,20},{9,8},{10,21},{12,1},{13,17},{16,10},{17,6},{18,5},{19,24},{20,11},
            {21,0},{22,9},{23,3},{24,25},{25,7},{26,22},{27,15},{29,16},{31,12}};
        auto mapped=statuses.find(native);
        if(mapped==statuses.end())throw std::runtime_error("unmapped native trade status");
        w.bits(same,1).bits(mapped->second,5);
        if(native==12)
        {
            Guid guid{};masks(r,guid,{2,4,6,0,1,3,7,5});r.align();octets(r,guid,{4,1,2,3,0,7,6,5});
            auto n=value(guid);if(!n || n>0xffffffff)throw std::runtime_error("invalid native trade partner");
            w.guid(n,player_high()).guid(); // Legacy has no linked Battle.net partner account.
        }
        else if(native==0)w.put(r.take<std::uint32_t>());
        else if(native==31)
        {
            w.bits(r.bits(1),1).flush();auto result=r.take<std::int32_t>();
            auto mapped_result=inventory_results.as_object().if_contains(std::to_string(result));
            if(!mapped_result)throw std::runtime_error("unmapped native trade inventory result");
            w.pack("i",{*mapped_result}).put(r.take<std::int32_t>());
        }
        else if(native==2 || native==26)w.put(r.take<std::uint8_t>());
        else if(native==19 || native==24)w.put(r.take<std::int32_t>()).put(r.take<std::int32_t>());
        r.end();return Packet{name,w.finish()};
    }
    if(name!="SMSG_TRADE_UPDATED")return {};
    auto id=r.take<std::uint32_t>();auto currency=r.take<std::int32_t>();auto gold=r.take<std::uint64_t>();
    auto enchant=r.take<std::int32_t>();auto client=r.take<std::uint32_t>();auto quantity=r.take<std::int32_t>();
    auto who=r.take<std::uint8_t>();auto current=r.take<std::uint32_t>();auto count=r.bits(22);
    if(who>1 || count>7)throw std::runtime_error("invalid native trade update bounds");
    struct Item {Guid gift{},author{};bool unwrapped=false,locked=false;};std::vector<Item> items(count);
    for(auto &item:items)
    {
        masks(r,item.gift,{7,1});item.unwrapped=r.bits(1);masks(r,item.gift,{3});
        if(item.unwrapped)
        {
            masks(r,item.author,{7,1,4,6,2,3,5});item.locked=r.bits(1);masks(r,item.author,{0});
        }
        masks(r,item.gift,{6,4,2,0,5});
    }
    r.align();w.pack("BIIIQiiiI",{who,id,client,current,gold,currency,quantity,enchant,count});
    bool unsupported_gems=false;std::unordered_set<unsigned> slots;
    for(auto &item:items)
    {
        int enchant_id=0,reforge=0,property=0,seed=0,charges=0;unsigned maximum=0,durability=0;
        if(item.unwrapped)
        {
            octets(r,item.author,{1});enchant_id=r.take<std::int32_t>();
            for(unsigned i=0;i<3;++i)unsupported_gems|=r.take<std::int32_t>()!=0;
            maximum=r.take<std::uint32_t>();octets(r,item.author,{6,2,7,4});reforge=r.take<std::int32_t>();
            durability=r.take<std::uint32_t>();property=r.take<std::int32_t>();octets(r,item.author,{3});
            auto unknown=r.take<std::int32_t>();if(unknown)throw std::runtime_error("unknown native trade item extension");
            octets(r,item.author,{0});charges=r.take<std::int32_t>();seed=r.take<std::int32_t>();octets(r,item.author,{5});
        }
        octets(r,item.gift,{6,1,7,4});auto entry=r.take<std::int32_t>();octets(r,item.gift,{0});
        auto stack=r.take<std::int32_t>();octets(r,item.gift,{5});auto slot=r.take<std::uint8_t>();octets(r,item.gift,{2,3});
        if(entry<=0 || stack<=0 || slot>6 || !slots.insert(slot).second || durability>maximum)
            throw std::runtime_error("invalid native trade item");
        w.pack("BI",{slot,stack}).guid(creator(item.gift));instance(w,entry,seed,property,reforge);
        w.bits(item.unwrapped,1).flush();
        if(item.unwrapped)
            w.pack("ii",{enchant_id,0}).guid(creator(item.author)).pack("iII",{charges,maximum,durability})
                .bits(0,2).bits(item.locked,1).flush();
    }
    r.end();if(unsupported_gems)return {}; // Gem item-ID resolution remains a separate requirement.
    return Packet{name,w.finish()};
}
} // namespace bridge
