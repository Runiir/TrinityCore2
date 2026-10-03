// Native QuestRewards -> pinned 60895 rewards and plain choice ItemInstances.
#include "quest_rewards.hpp"

namespace bridge
{
Bytes quest_rewards(Reader &r,Value *offered_choices)
{
    auto choiceCount=r.take<std::uint32_t>();auto choices=r.unpack("6I"),choiceQty=r.unpack("6I");r.unpack("6I");
    auto itemCount=r.take<std::uint32_t>();auto items=r.unpack("4I"),itemQty=r.unpack("4I");r.unpack("4I");
    auto money=r.take<std::uint32_t>(),xp=r.take<std::uint32_t>(),title=r.take<std::uint32_t>();
    auto reserved=r.take<std::uint32_t>();auto reservedFloat=r.take<float>();r.take<std::uint32_t>();auto reserved2=r.take<std::uint32_t>();
    auto flags=r.take<std::uint32_t>();auto factions=r.unpack("5I"),values=r.unpack("5i"),overrides=r.unpack("5I");
    auto displaySpell=r.take<std::uint32_t>(),spell=r.take<std::uint32_t>();auto currencies=r.unpack("4I"),currencyQty=r.unpack("4I");
    auto skill=r.take<std::uint32_t>(),skillUps=r.take<std::uint32_t>();
    if(choiceCount>6 || itemCount>4 || reserved || reserved2 || reservedFloat!=0 || money>0x7fffffff || xp>0x7fffffff)
        throw std::runtime_error("invalid native quest rewards");
    auto validate=[](Array const &ids,Array const &quantities)
    {
        for(unsigned i=0;i<ids.size();++i)
            if(integer(ids[i])>0x7fffffff || integer(quantities[i])>0x7fffffff || (!integer(ids[i]) && integer(quantities[i])))
                throw std::runtime_error("invalid native quest reward item");
    };
    validate(choices,choiceQty);validate(items,itemQty);validate(currencies,currencyQty);
    if(offered_choices)
    {
        Array offered;
        for(unsigned i=0;i<choiceCount;++i)
        {
            if(!integer(choices[i]) || !integer(choiceQty[i]))throw std::runtime_error("missing native quest choice item");
            offered.push_back(Object{{"index",i},{"id",choices[i]},{"quantity",choiceQty[i]}});
        }
        *offered_choices=offered;
    }
    Writer w;
    for(unsigned i=0;i<4;++i)w.pack("2i",{items[i],itemQty[i]});
    for(unsigned i=0;i<4;++i)w.pack("3i",{currencies[i],currencyQty[i],0});
    w.pack("4iQi3i",{choiceCount,itemCount,money,xp,0,0,0,title,flags});
    for(unsigned i=0;i<5;++i)w.pack("4i",{factions[i],values[i],overrides[i],0});
    w.pack("7i",{displaySpell,0,0,spell,skill,skillUps,0});
    for(unsigned i=0;i<6;++i)
        w.bits(0,2).flush().pack("i2I",{choices[i],0,0}).bits(0,1).flush().bits(0,6).flush().pack("i",{choiceQty[i]});
    return w.bits(0,1).flush().finish();
}
}
