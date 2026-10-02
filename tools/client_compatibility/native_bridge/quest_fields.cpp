// Native 25-slot quest log -> owned modern player creation and sparse updates.
#include "protocol.hpp"

namespace bridge
{
Array Protocol::quest_fields(Value const &snapshot) const
{
    Array slots;
    for(unsigned slot=0;slot<25;++slot)
    {
        unsigned offset=slot*5;Array progress;
        for(unsigned i=0;i<24;++i)
            progress.push_back(i<4 ? (field(snapshot,"PLAYER_QUEST_LOG_1_1",offset+2+i/2)>>((i%2)*16))&65535 : 0);
        slots.push_back(Object{{"EndTime",field(snapshot,"PLAYER_QUEST_LOG_1_1",offset+4)},
            {"QuestID",field(snapshot,"PLAYER_QUEST_LOG_1_1",offset)},
            {"StateFlags",field(snapshot,"PLAYER_QUEST_LOG_1_1",offset+1)},
            {"ObjectiveProgress",progress}});
    }
    return slots;
}
Bytes Protocol::quest_block(Value const &snapshot,Value const &changed) const
{
    std::array<std::uint32_t,5> masks{};bool any=false;
    for(unsigned slot=0;slot<25;++slot)
    {
        bool has=false;
        for(unsigned part=0;part<5;++part)
            has|=changed.as_object().contains(std::to_string(field_index("PLAYER_QUEST_LOG_1_1")+slot*5+part));
        if(has){unsigned bit=43+slot;masks[bit/32]|=1u<<(bit%32);any=true;}
    }
    if(!any)return {};
    masks[42/32]|=1u<<(42%32);
    Writer data;data.pack("BBBI",{3,0,3,1u<<6});
    unsigned blocks=0;for(unsigned i=0;i<5;++i)if(masks[i])blocks|=1u<<i;
    data.bits(blocks,5);for(auto mask:masks)if(mask)data.bits(mask,32);
    // Modern explicitly supports complete slot payloads without nested masks.
    data.bits(1,1).flush();auto slots=quest_fields(snapshot);
    for(unsigned slot=0;slot<25;++slot)
        if(masks[(43+slot)/32]&(1u<<((43+slot)%32)))fields.serialize(data,"QuestLog",slots[slot],3);
    return Writer().pack("B",{0}).guid(integer(get(snapshot,"guid")),player_high())
        .put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
}
}
