#include "protocol.hpp"

namespace bridge
{
Bytes Protocol::public_player_block(Value const &snapshot,Value const &character) const
{
    auto guid=integer(get(snapshot,"guid"));auto name=str(get(character,"name"));
    if(!guid || guid>0xffffffff || integer(get(snapshot,"kind"))!=4 ||
        truth(get(get(snapshot,"flags"),"self")) || integer(get(character,"guid"))!=guid ||
        name.empty() || name.size()>63 || name.find('\0')!=std::string::npos ||
        !character.as_object().contains("gender") || integer(get(character,"gender"))>1)
        throw std::runtime_error("invalid visible player profile");
    auto const &move=get(snapshot,"movement");Writer w;
    // Player, not ActivePlayer: no owner movement extras or private field root.
    w.pack("B",{1}).guid(guid,player_high()).pack("B",{6});
    for(unsigned i=0;i<19;++i)w.bits(i==0 || i==4,1);
    w.guid(guid,player_high()).pack("IIII",{get(move,"flags"),modern_flags2(integer(get(move,"flags2"))),0,get(move,"time")});
    w.pack("4f",get(move,"position").as_array()).pack("ffII",{get(move,"pitch"),0,0,0}).bits(0,8);
    w.pack("9f",get(move,"speeds").as_array())
        .pack("If17f",{0,1,2,65,1,3,10,100,90,140,180,360,90,270,30,80,2.75,7,.4})
        .bits(0,1).pack("I",{0});
    Writer data;data.pack("B",{0}).raw(Bytes{0,5,6,255,1});
    auto values=field_values(snapshot,character);
    for(auto kind:{"ObjectData","UnitData","PlayerData"})
        fields.serialize(data,kind,get(values,kind),0);
    return w.put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
}
}
