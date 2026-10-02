// Translate the native static quest cache reply; modern-only systems default empty.
#include "quests.hpp"

namespace bridge
{
Reply quest_query_response(std::string const &name,View body)
{
    if(name!="SMSG_QUEST_QUERY_RESPONSE")return {};
    Reader r(body);auto id=r.take<std::uint32_t>();Writer w;
    if(id&0x80000000)
    {
        r.end();return Packet{"SMSG_QUERY_QUEST_INFO_RESPONSE",w.pack("I",{id&0x7fffffff}).bits(0,1).flush().finish()};
    }
    if(!id || id>0x3ffffff)throw std::runtime_error("unsupported native quest identity");
    auto type=r.take<std::int32_t>(),level=r.take<std::int32_t>(),minLevel=r.take<std::int32_t>();
    auto sort=r.take<std::int32_t>(),info=r.take<std::int32_t>();auto group=r.take<std::uint32_t>();
    auto requiredFactions=r.unpack("IiIi");auto next=r.take<std::int32_t>();auto xp=r.take<std::uint32_t>();
    auto money=r.take<std::int32_t>();auto bonus=r.take<std::uint32_t>();auto displaySpell=r.take<std::int32_t>();
    auto spell=r.take<std::int32_t>(),honor=r.take<std::int32_t>();auto killHonor=r.take<float>();
    auto start=r.take<std::uint32_t>(),flags=r.take<std::uint32_t>();r.take<std::uint32_t>();
    auto title=r.take<std::uint32_t>(),playerKills=r.take<std::uint32_t>();auto talents=r.take<std::uint32_t>();
    auto arena=r.take<std::uint32_t>(),skill=r.take<std::uint32_t>(),skillUps=r.take<std::uint32_t>();
    auto factionFlags=r.take<std::uint32_t>(),giverPortrait=r.take<std::uint32_t>(),turnPortrait=r.take<std::uint32_t>();
    auto items=r.unpack("8I"),choices=r.unpack("12I");auto factions=r.unpack("5I"),values=r.unpack("5i"),overrides=r.unpack("5I");
    auto continent=r.take<std::uint32_t>();auto x=r.take<float>(),y=r.take<float>();auto priority=r.take<std::uint32_t>();
    auto logTitle=native_text(r),summary=native_text(r),description=native_text(r),area=native_text(r),completion=native_text(r);
    auto creatures=r.unpack("16I"),requiredItems=r.unpack("12I");auto requiredSpell=r.take<std::uint32_t>();
    std::array<Bytes,4> objectiveText;for(auto &text:objectiveText)text=native_text(r);
    auto currencies=r.unpack("8I"),requiredCurrencies=r.unpack("8I");
    auto giverText=native_text(r),giverName=native_text(r),turnText=native_text(r),turnName=native_text(r);
    auto acceptedSound=r.take<std::uint32_t>(),completeSound=r.take<std::uint32_t>();r.end();
    if(talents || requiredSpell || logTitle.size()>511 || summary.size()>4095 || description.size()>4095 ||
        area.size()>511 || completion.size()>2047 || giverText.size()>1023 || turnText.size()>1023 ||
        giverName.size()>255 || turnName.size()>255)
        throw std::runtime_error("unsupported native quest query fields");
    struct Objective {unsigned index,type,object,amount;int storage;Bytes text;};
    std::vector<Objective> objectives;
    auto add=[&](unsigned index,unsigned objectiveType,Value const &object,Value const &amount,int storage,Bytes text={})
    {
        auto objectID=integer(object),quantity=integer(amount);
        if(!objectID && !quantity)return;
        if(!objectID || !quantity || objectID>0x7fffffff || quantity>0x7fffffff || text.size()>255)
            throw std::runtime_error("invalid native quest objective");
        objectives.push_back({index,objectiveType,static_cast<unsigned>(objectID),static_cast<unsigned>(quantity),storage,std::move(text)});
    };
    for(unsigned i=0;i<4;++i)
    {
        auto object=integer(creatures[i*4]);
        add(i,object&0x80000000 ? 2:0,object&0x7fffffff,creatures[i*4+1],i,objectiveText[i]);
    }
    for(unsigned i=0;i<6;++i)add(4+i,1,requiredItems[i*2],requiredItems[i*2+1],-1);
    for(unsigned i=0;i<4;++i)add(10+i,4,requiredCurrencies[i*2],requiredCurrencies[i*2+1],-1);
    for(unsigned i=0;i<2;++i)add(14+i,6,requiredFactions[i*2],requiredFactions[i*2+1],-1);
    if(playerKills)objectives.push_back({16,9,0,playerKills,-1,{}});
    if(money<0)objectives.push_back({17,8,0,static_cast<unsigned>(-static_cast<std::int64_t>(money)),-1,{}});
    w.pack("I",{id}).bits(1,1).flush()
        .pack("12if",{id,type,level,0,0,0,minLevel,sort,info,group,next,xp,1})
        .pack("iif",{money,0,1}).pack("i3i",{bonus,displaySpell,0,0})
        .pack("iif",{spell,honor,killHonor}).pack("ifi",{0,0,0}).pack("i3I",{start,flags,0,0});
    for(unsigned i=0;i<4;++i)w.pack("4I",{items[i*2],items[i*2+1],creatures[i*4+2],creatures[i*4+3]});
    for(unsigned i=0;i<6;++i)w.pack("3I",{choices[i*2],choices[i*2+1],0});
    w.pack("IffI8I",{continent,x,y,priority,title,arena,skill,skillUps,giverPortrait,0,0,turnPortrait});
    for(unsigned i=0;i<5;++i)w.pack("IiII",{factions[i],values[i],overrides[i],0});
    w.pack("I",{factionFlags}).pack("8I",currencies)
        .pack("3IqIQ6I",{acceptedSound,completeSound,0,0,objectives.size(),std::uint64_t(-1),0,0,0,0,0,0});
    w.bits(logTitle.size(),9).bits(summary.size(),12).bits(description.size(),12).bits(area.size(),9)
        .bits(giverText.size(),10).bits(giverName.size(),8).bits(turnText.size(),10).bits(turnName.size(),8)
        .bits(completion.size(),11).bits(0,1).flush();
    for(auto const &o:objectives)
    {
        // Native objectives have a quest/slot identity, not a separate DB row ID.
        // The bridge uses a stable, collision-free ID and retains native kill storage.
        w.pack("IibiIIIfi",{id*32+o.index+1,o.type,o.storage,o.object,o.amount,0,0,0,0})
            .bits(o.text.size(),8).flush().raw(o.text);
    }
    w.raw(logTitle).raw(summary).raw(description).raw(area).raw(giverText).raw(giverName).raw(turnText).raw(turnName).raw(completion);
    return Packet{"SMSG_QUERY_QUEST_INFO_RESPONSE",w.finish()};
}
}
