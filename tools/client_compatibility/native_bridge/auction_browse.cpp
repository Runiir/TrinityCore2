// Stock 60895 browse queries backed by every native legacy search page.
#include "auctions.hpp"
#include <algorithm>
#include <cctype>
#include <limits>

namespace bridge
{
namespace
{
bool authority(Protocol const &p,State const &s)
{
    auto found=s.visible_units.find(s.auction_target);
    return s.auction_target && found!=s.visible_units.end() && integer(get(found->second,"kind"))==3 &&
        (p.field(found->second,"UNIT_NPC_FLAGS")&2097152);
}
std::string folded(std::string text)
{
    for(char &c:text)if(static_cast<unsigned char>(c)<128)c=std::tolower(static_cast<unsigned char>(c));
    return text;
}
bool class_matches(Value const &item,Array const &classes)
{
    if(classes.empty())return true;
    for(auto const &c:classes)if(integer(get(c,"class"))==integer(get(item,"class")))
    {
        auto const &subclasses=get(c,"subclasses").as_array();if(subclasses.empty())return true;
        for(auto const &sub:subclasses)
        {
            auto mask=integer(get(sub,"mask")),inventory=integer(get(item,"inventory_type"));
            if(integer(get(sub,"subclass"))==integer(get(item,"subclass")) &&
                (inventory<64 && (mask&(1ull<<inventory))))return true;
        }
    }
    return false;
}
struct Bucket
{
    unsigned id,level,required,quantity=0;
    std::uint64_t price=std::numeric_limits<std::uint64_t>::max();bool own=false;
    std::string name;
};
Reply buckets(State &s,AuctionItems const &items,unsigned delay)
{
    auto const &q=s.auction_browse;std::unordered_map<unsigned,Bucket> grouped;
    auto filter=integer(get(q,"filters")),minimum=integer(get(q,"min")),maximum=integer(get(q,"max"));
    for(auto const &r:get(q,"rows").as_array())
    {
        auto id=integer(get(r,"entry"));auto found=items.find(id);
        if(found==items.end())throw std::runtime_error("native auction item metadata is absent");
        auto const &item=found->second;auto level=integer(get(item,"level")),required=integer(get(item,"required_level"));
        auto quality=integer(get(item,"quality"));
        if((minimum && required<minimum) || (maximum && required>maximum) ||
            (quality>6 || !(filter&(1ull<<(quality+6)))) ||
            !class_matches(item,get(q,"classes").as_array()))continue;
        if(!id || id>0xfffff || level>2047 || required>0x7fffffff || str(get(item,"name")).empty())
            throw std::runtime_error("native auction item exceeds modern bucket bounds");
        auto [pos,inserted]=grouped.try_emplace(id,Bucket{static_cast<unsigned>(id),static_cast<unsigned>(level),
            static_cast<unsigned>(required),0,std::numeric_limits<std::uint64_t>::max(),false,folded(str(get(item,"name")))});
        (void)inserted;auto &b=pos->second;auto count=integer(get(r,"count"));
        if(count>0x7fffffff-b.quantity)throw std::runtime_error("auction bucket quantity overflow");
        b.quantity+=count;b.own|=integer(get(r,"owner"))==s.guid();
        auto price=integer(get(r,"buyout"));if(!price)price=integer(get(r,"bid"));
        // Modern stackable buckets quote unit prices; buying a partial native
        // stack still needs a separate commodity transaction implementation.
        if(integer(get(item,"stackable"))>1 && price)
        {
            if(price%count)throw std::runtime_error("fractional native auction unit price is not representable");
            price/=count;
        }
        if(price<b.price)b.price=price;
    }
    std::vector<Bucket> results;for(auto const &[id,b]:grouped){(void)id;results.push_back(b);}
    auto const &sorts=get(q,"sorts").as_array();
    std::sort(results.begin(),results.end(),[&](Bucket const &a,Bucket const &b)
    {
        for(auto const &sort:sorts)
        {
            auto kind=integer(sort.as_array()[0]);bool reverse=truth(sort.as_array()[1]);int cmp=0;
            if(kind==0)cmp=a.price<b.price?-1:a.price>b.price?1:0;
            if(kind==1)cmp=a.name<b.name?-1:a.name>b.name?1:0;
            if(kind==2)cmp=a.level<b.level?-1:a.level>b.level?1:0;
            if(cmp)return reverse?cmp>0:cmp<0;
        }
        return a.id<b.id;
    });
    auto offset=std::min<std::uint64_t>(integer(get(q,"offset")),results.size());
    auto end=std::min<std::uint64_t>(offset+500,results.size());Writer w;
    w.pack("4I",{end-offset,delay,0,0}).bits(0,1).bits(end<results.size(),1).flush();
    for(auto i=offset;i<end;++i)
    {
        auto const &b=results[i];w.bits(b.id,20).bits(0,1).bits(b.level,11).bits(0,1).flush()
            .pack("iiQI",{b.quantity,b.required,b.price,0})
            .bits(0,4).bits(b.own,1).bits(0,1).flush();
    }
    s.auction_browse=nullptr;return Packet{"SMSG_AUCTION_LIST_BUCKETS_RESULT",w.finish()};
}
}
Reply auction_browse_request(Protocol const &p,State &s,std::string const &name,View body)
{
    if(name!="CMSG_AUCTION_BROWSE_QUERY")return {};
    Reader r(body);auto guid=owned_unit(s,r.guid());auto offset=r.take<std::uint32_t>();
    auto min=r.take<std::uint8_t>(),max=r.take<std::uint8_t>();r.raw(2);auto filter=r.take<std::uint32_t>();
    auto pets=r.take<std::uint32_t>();r.take<std::uint8_t>();r.take<std::uint32_t>();
    if(pets>4096)throw std::runtime_error("auction known-pet mask exceeds bound");
    r.raw(pets);auto taint=r.bits(1),length=r.bits(8),class_count=r.bits(3),sort_count=r.bits(2);r.align();
    if(taint)return {}; // Valid but unsupported addon metadata is not a login failure.
    auto text=r.raw(length);std::string search(text.begin(),text.end());Array classes,sorts;
    if(search.find('\0')!=std::string::npos)throw std::runtime_error("auction search contains embedded terminator");
    for(unsigned i=0;i<class_count;++i)
    {
        auto id=r.take<std::int32_t>();auto count=r.bits(5);r.align();Array subclasses;
        if(id<0 || id>31)throw std::runtime_error("invalid auction class filter");
        for(unsigned j=0;j<count;++j)
        {auto mask=r.take<std::uint64_t>();auto sub=r.take<std::int32_t>();
         if(sub<0 || sub>31)throw std::runtime_error("invalid auction subclass filter");
         subclasses.push_back(Object{{"mask",mask},{"subclass",sub}});}
        classes.push_back(Object{{"class",id},{"subclasses",subclasses}});
    }
    bool supported=!(filter&~0x1fc4u) && !pets;
    for(unsigned i=0;i<sort_count;++i)
    {auto order=r.take<std::uint8_t>();auto reverse=r.bits(1);r.align();supported&=order<=2;sorts.push_back(Array{order,reverse});}
    r.end();
    if(!authority(p,s) || guid!=s.auction_target)throw std::runtime_error("auction browse requires native opening authority");
    if(!supported)return {};
    if(s.auction_browse.is_object())return {}; // Legacy results have no request ID. Do not supersede an in-flight query.
    Writer w;w.put(guid).put<std::uint32_t>(0).raw(search).put<std::uint8_t>(0)
        .pack("BB4IBBBB",{0,0,0xffffffffu,0xffffffffu,0xffffffffu,0xffffffffu,(filter&4)!=0,0,0,0});
    auto native=w.finish();s.auction_browse=Object{{"offset",offset},{"min",min},{"max",max},{"filters",filter},
        {"classes",classes},{"sorts",sorts},{"native_body",hex(native)},{"native_offset",0},{"total",nullptr},
        {"rows",Array{}},{"ids",Object{}}};
    return Packet{"CMSG_AUCTION_LIST_ITEMS",native};
}
Reply auction_browse_response(Protocol const &p,State &s,std::string const &name,View body,AuctionItems const &items)
{
    if(name!="SMSG_AUCTION_LIST_RESULT" || !s.auction_browse.is_object())return {};
    if(!authority(p,s)){s.auction_browse=nullptr;return {};}
    Reader r(body);auto count=r.take<std::uint32_t>();
    if(count>4096 || r.remaining()<8 || count>(r.remaining()-8)/200)throw std::runtime_error("native browse exceeds body bounds");
    auto &q=s.auction_browse.as_object();auto &rows=q["rows"].as_array();auto &ids=q["ids"].as_object();
    for(unsigned i=0;i<count;++i)
    {
        auto row=read_auction_item(r);auto id=std::to_string(row.id);
        if(ids.contains(id))throw std::runtime_error("native browse repeated an auction across pages");
        ids[id]=true;rows.push_back(Object{{"id",row.id},{"entry",row.entry},{"count",row.count},{"owner",row.owner},
            {"buyout",row.buyout},{"bid",row.bid},{"property",row.property}});
    }
    auto total=r.take<std::uint32_t>(),delay=r.take<std::uint32_t>();r.end();auto offset=integer(q["native_offset"]);
    if(total>4096 || offset+count>total || (offset+count<total && !count) ||
        (!q["total"].is_null() && integer(q["total"])!=total))throw std::runtime_error("native browse catalog changed or exceeded bounds");
    q["total"]=total;
    if(offset+count<total)
    {
        auto original=unhex(str(q["native_body"]));auto next=offset+count;q["native_offset"]=next;
        auto request=Writer().put(s.auction_target).put<std::uint32_t>(next).raw(View(original).subspan(12)).finish();
        if(!s.native_send)throw std::runtime_error("native browse page sender is absent");
        s.native_send("CMSG_AUCTION_LIST_ITEMS",request);return {};
    }
    return buckets(s,items,delay);
}
}
