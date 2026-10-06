#include "cast_packets.hpp"

namespace bridge
{
Bytes cast_packet(CastPacket const &d,bool completed)
{
    Writer w;
    w.guid(d.caster).guid(d.unit).guid(d.cast).guid();
    w.pack("iIIII",{d.spell,d.visual,d.flags,d.extra,d.duration})
        .pack("IfBii",{0,0,d.dest_index,d.immunity[0],d.immunity[1]});
    w.pack("iB",{0,0}).guid()
        .bits(d.hits.size(),16).bits(0,16).bits(0,16)
        .bits(!d.remaining.is_null(),9).bits(0,1).bits(0,16).bits(0,2).flush();
    auto targets=(d.target_flags&~0x20000u) | ((d.target_flags&0x20000u) ? 0x08000000u : 0u);
    w.bits(targets,28).bits(!d.source.is_null(),1).bits(!d.dest.is_null(),1)
        .bits(0,2).bits(0,7).guid(Protocol::modern_guid(d.target,d.map)).guid();
    if(!d.source.is_null())w.guid().pack("3f",d.source.as_array());
    if(!d.dest.is_null())w.guid().pack("3f",d.dest.as_array());
    for(auto hit:d.hits)w.guid(Protocol::modern_guid(hit,d.map));
    if(!d.remaining.is_null())w.pack("bi",{d.remaining_type,d.remaining});
    if(completed)w.bits(0,1).flush();
    return w.finish();
}
}
