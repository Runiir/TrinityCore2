// Stock modern sale/buy item searches use the same complete native catalog scan.
#include "auctions.hpp"
#include <algorithm>

namespace bridge
{
Reply auction_item_request(Protocol const &p,State &s,std::string const &name,View body,AuctionItems const &items)
{
    Reader r(body);auto guid=owned_unit(s,r.guid());unsigned id,level=0,suffix=0,pet=0,offset,sort_count,taint;
    bool bucket=name=="CMSG_AUCTION_LIST_ITEMS_BY_BUCKET_KEY";
    if(bucket)
    {
        offset=r.take<std::uint32_t>();r.take<std::uint8_t>();taint=r.bits(1);sort_count=r.bits(2);r.align();
        id=r.bits(20);auto has_pet=r.bits(1);level=r.bits(11);auto has_suffix=r.bits(1);r.align();
        if(has_pet)pet=r.take<std::uint16_t>();
        if(has_suffix)suffix=r.take<std::uint16_t>();
    }
    else
    {id=r.take<std::uint32_t>();suffix=r.take<std::uint32_t>();offset=r.take<std::uint32_t>();taint=r.bits(1);sort_count=r.bits(2);r.align();}
    if(!id || id>0xfffff)throw std::runtime_error("invalid auction search item ID");
    if(taint)return {};
    Array sorts;bool supported=true;
    for(unsigned i=0;i<sort_count;++i)
    {auto order=r.take<std::uint8_t>();auto reverse=r.bits(1);r.align();supported&=order<=4;sorts.push_back(Array{order,reverse});}
    r.end();auto found=s.visible_units.find(guid);
    if(guid!=s.auction_target || found==s.visible_units.end() || integer(get(found->second,"kind"))!=3 ||
        !(p.field(found->second,"UNIT_NPC_FLAGS")&2097152))throw std::runtime_error("auction item search requires native opening authority");
    auto item=items.find(id);
    // Native whole-stack auctions cannot supply modern partial commodities.
    // Random suffix keys also require a real native-to-modern suffix mapping.
    if(!supported || pet || suffix || item==items.end() || integer(get(item->second,"stackable"))>1)return {};
    if(s.auction_browse.is_object())return {};
    auto text=str(get(item->second,"name"));if(text.empty() || text.size()>255 || text.find('\0')!=std::string::npos)
        throw std::runtime_error("invalid native auction search item name");
    Writer w;w.put(guid).put<std::uint32_t>(0).raw(text).put<std::uint8_t>(0)
        .pack("BB4IBBBB",{0,0,0xffffffffu,0xffffffffu,0xffffffffu,0xffffffffu,0,0,0,0});
    auto native=w.finish();s.auction_browse=Object{{"kind","items"},{"item",id},{"level",level},{"bucket",bucket},
        {"offset",offset},{"sorts",sorts},{"native_body",hex(native)},{"native_offset",0},{"total",nullptr},
        {"rows",Array{}},{"ids",Object{}}};
    return Packet{"CMSG_AUCTION_LIST_ITEMS",native};
}

Reply auction_item_result(State &s,AuctionItems const &items,unsigned delay)
{
    auto const &q=s.auction_browse;auto id=integer(get(q,"item"));auto item=items.find(id);
    if(item==items.end())throw std::runtime_error("native auction search metadata disappeared");
    auto level=integer(get(item->second,"level"));std::vector<Value const*> rows;
    if(level>2047)throw std::runtime_error("native auction search item level exceeds modern bounds");
    for(auto const &row:get(q,"rows").as_array())
    {
        if(integer(get(row,"entry"))!=id)continue;
        if(integer(get(row,"property")))throw std::runtime_error("native random auction suffix is not mapped");
        if(truth(get(q,"bucket")) && integer(get(q,"level"))!=level)continue;
        rows.push_back(&row);
    }
    auto const &sorts=get(q,"sorts").as_array();
    std::sort(rows.begin(),rows.end(),[&](Value const* a,Value const* b)
    {
        auto price=[](Value const &v,unsigned kind)
        {
            auto buy=integer(get(v,"buyout")),bid=integer(get(v,"bid")),minimum=integer(get(v,"minimum"));
            if(kind==4)return buy;
            if(kind==3)return bid;
            return buy?buy:(bid?bid:minimum);
        };
        for(auto const &sort:sorts)
        {
            auto kind=integer(sort.as_array()[0]);if(kind==1 || kind==2)continue; // Same item/name/base level.
            auto left=price(*a,kind),right=price(*b,kind);
            if(left!=right)return truth(sort.as_array()[1])?left>right:left<right;
        }
        return integer(get(*a,"id"))>integer(get(*b,"id"));
    });
    auto start=std::min<std::uint64_t>(integer(get(q,"offset")),rows.size()),end=std::min<std::uint64_t>(start+50,rows.size());
    Writer w;w.pack("3I",{end-start,0,delay});for(auto i=start;i<end;++i)w.raw(unhex(str(get(*rows[i],"encoded"))));
    // Correlate with the request key. Item-ID queries intentionally cover all
    // levels and therefore use level zero, while a bucket query echoes its key.
    auto response_level=truth(get(q,"bucket"))?integer(get(q,"level")):0;
    w.bits(2,2).bits(end<rows.size(),1).flush().bits(id,20).bits(0,1).bits(response_level,11).bits(0,1).flush()
        .put<std::uint32_t>(rows.size());
    s.auction_browse=nullptr;return Packet{"SMSG_AUCTION_LIST_ITEMS_RESULT",w.finish()};
}
}
