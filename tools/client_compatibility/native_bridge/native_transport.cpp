#include "native_transport.hpp"
#include <cmath>

namespace bridge
{
void NativeTransport::bits(Reader &r,bool gameobject)
{
    if(gameobject)
    {
        present[5]=r.bits(1);vehicle=r.bits(1);
        for(unsigned i:{0,3,6,1,4,2})present[i]=r.bits(1);
        previous=r.bits(1);present[7]=r.bits(1);
    }
    else
    {
        present[1]=r.bits(1);previous=r.bits(1);
        for(unsigned i:{4,0,6})present[i]=r.bits(1);
        vehicle=r.bits(1);
        for(unsigned i:{7,5,3,2})present[i]=r.bits(1);
    }
}
Value NativeTransport::read(Reader &r,bool gameobject)
{
    auto octet=[&](unsigned i){if(present[i])guid|=std::uint64_t(r.take<std::uint8_t>()^1)<<(i*8);};
    float x,y,z,o;std::uint32_t time,prev=0,rec=0;std::int8_t seat;
    if(gameobject)
    {
        octet(0);octet(5);if(vehicle)rec=r.take<std::uint32_t>();
        octet(3);x=r.take<float>();for(unsigned i:{4,6,1})octet(i);
        time=r.take<std::uint32_t>();y=r.take<float>();octet(2);octet(7);
        z=r.take<float>();seat=r.take<std::int8_t>();o=r.take<float>();
        if(previous)prev=r.take<std::uint32_t>();
    }
    else
    {
        octet(5);octet(7);time=r.take<std::uint32_t>();o=r.take<float>();
        if(previous)prev=r.take<std::uint32_t>();
        y=r.take<float>();x=r.take<float>();octet(3);z=r.take<float>();octet(0);
        if(vehicle)rec=r.take<std::uint32_t>();
        seat=r.take<std::int8_t>();for(unsigned i:{1,6,2,4})octet(i);
    }
    if(!guid)throw std::runtime_error("native transport has an empty identity");
    for(float value:{x,y,z,o})if(!std::isfinite(value))throw std::runtime_error("invalid native transport coordinate");
    return Object{{"guid",guid},{"position",Array{x,y,z,o}},{"seat",seat},
        {"time",time},{"previous_time",prev},{"vehicle_id",rec}};
}
Writer &transport_info(Writer &w,Value const &transport,unsigned map)
{
    auto prev=integer(get(transport,"previous_time")),vehicle=integer(get(transport,"vehicle_id"));
    w.guid(Protocol::modern_guid(integer(get(transport,"guid")),map))
        .pack("4fbI",{get(transport,"position").as_array()[0],get(transport,"position").as_array()[1],
            get(transport,"position").as_array()[2],get(transport,"position").as_array()[3],
            get(transport,"seat"),get(transport,"time")}).bits(prev!=0,1).bits(vehicle!=0,1).flush();
    if(prev)w.put<std::uint32_t>(prev);
    if(vehicle)w.put<std::uint32_t>(vehicle);
    return w;
}
}
