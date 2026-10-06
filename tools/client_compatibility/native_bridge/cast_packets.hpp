#pragma once
#include "protocol.hpp"

namespace bridge
{
struct CastPacket
{
    Array caster,unit,cast;
    std::int32_t spell=0;
    std::uint32_t visual=0,flags=0,extra=0,duration=0,target_flags=0,dest_index=0,map=0;
    std::uint64_t target=0;
    std::int8_t remaining_type=1;
    std::vector<std::uint64_t> hits;
    Value source,dest,remaining;
    Array immunity{0,0};
};
Bytes cast_packet(CastPacket const &data,bool completed);
}
