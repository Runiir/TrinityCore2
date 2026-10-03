#include "appearance.hpp"

namespace bridge
{
void appearance_fields(std::uint32_t native_flags, Object &player)
{
    // Classic PlayerFlagsEx uses 0x80/0x100 for hidden helm/cloak. Pinned
    // HermesProxy 841a26f PlayerDefines/UpdateHandler documents this split.
    // The legacy bits occupy the modern warmode positions; do not copy them.
    player["PlayerFlags"]=native_flags&~0xc00u;
    player["PlayerFlagsEx"]=(native_flags&0x400u ? 0x80u : 0u)|
        (native_flags&0x800u ? 0x100u : 0u);
}
Reply appearance_request(std::string const &name, View body)
{
    if(name!="CMSG_SHOWING_HELM" && name!="CMSG_SHOWING_CLOAK")return {};
    // Live60895 encodes true as 0x80. Native ByteBuffer::operator>>(bool&)
    // reads signed char >0, so canonicalize the one byte boolean to 0/1.
    Reader r(body);auto shown=r.take<std::uint8_t>()!=0;r.end();
    return Packet{name,Bytes{static_cast<std::uint8_t>(shown)}};
}
}
