#include "auction_data.hpp"
#include <algorithm>
#include <fstream>

namespace bridge
{
namespace
{
Bytes table_file(std::filesystem::path const &path)
{
    if(std::filesystem::file_size(path)>128*1024*1024)throw std::runtime_error("auction item table exceeds bound");
    std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("auction item table is absent");
    return Bytes(std::istreambuf_iterator<char>(f),{});
}
struct Table
{
    View records,strings;unsigned count,width;
    Table(View data,unsigned fields)
    {
        Reader r(data);if(hex(r.raw(4))!="57444232")throw std::runtime_error("unexpected auction item DB2 signature");
        auto h=r.unpack("11I");count=integer(h[0]);width=integer(h[2]);auto min=integer(h[7]),max=integer(h[8]);
        if(integer(h[1])!=fields || width!=fields*4 || integer(h[5])!=15595 || count>1000000 || (max && max<min))
            throw std::runtime_error("unexpected auction item DB2 layout");
        if(max)r.raw((max-min+1)*6);
        records=r.raw(std::uint64_t(count)*width);strings=r.raw(integer(h[3]));
        if(integer(h[10]))throw std::runtime_error("auction item DB2 copy table is unsupported");
        r.end();
    }
};
}
AuctionItems auction_sparse(View data)
{
    Table table(data,133);Reader r(table.records);AuctionItems items;
    for(unsigned i=0;i<table.count;++i)
    {
        auto row=r.unpack("133I");auto id=integer(row[0]),offset=integer(row[99]);
        if(!id || id>0xfffff || offset>=table.strings.size())throw std::runtime_error("invalid auction item table row");
        auto rest=table.strings.subspan(offset);auto end=std::find(rest.begin(),rest.end(),0);
        if(end==rest.end() || end-rest.begin()>4096)throw std::runtime_error("invalid auction item name");
        std::string name(rest.begin(),end);
        items.emplace(id,Object{{"name",name},{"level",row[12]},{"required_level",row[13]},
            {"quality",row[1]},{"stackable",row[22]},{"inventory_type",row[9]}});
    }
    r.end();return items;
}
AuctionItems load_auction_items(std::filesystem::path const &root)
{
    auto directory=root/"data/dbc/enUS";auto sparse=table_file(directory/"Item-sparse.db2");
    auto items=auction_sparse(sparse);auto basic=table_file(directory/"Item.db2");Table table(basic,8);Reader r(table.records);
    for(unsigned i=0;i<table.count;++i)
    {
        auto row=r.unpack("8I");auto found=items.find(integer(row[0]));if(found==items.end())continue;
        found->second.as_object()["class"]=row[1];found->second.as_object()["subclass"]=row[2];
    }
    Database db(root);
    for(auto const &row:db.query("SELECT ID,Display,ItemLevel,RequiredLevel,Quality,Stackable,InventoryType FROM client442_hotfixes.item_sparse"))
    {
        auto &item=items[integer(get(row,"ID"))];if(!item.is_object())item=Object{};
        for(auto const &[to,from]:std::initializer_list<std::pair<char const*,char const*>>{
            {"name","Display"},{"level","ItemLevel"},{"required_level","RequiredLevel"},{"quality","Quality"},
            {"stackable","Stackable"},{"inventory_type","InventoryType"}})item.as_object()[to]=get(row,from);
    }
    for(auto const &row:db.query("SELECT ID,ClassID,SubclassID FROM client442_hotfixes.item"))
    {
        auto found=items.find(integer(get(row,"ID")));if(found==items.end())continue;
        found->second.as_object()["class"]=get(row,"ClassID");found->second.as_object()["subclass"]=get(row,"SubclassID");
    }
    return items;
}
}
