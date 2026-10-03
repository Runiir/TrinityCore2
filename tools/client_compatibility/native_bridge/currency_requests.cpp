#include "currency.hpp"

namespace bridge
{
Reply currency_request(std::string const &name, View body)
{
    if (name != "CMSG_SET_CURRENCY_FLAGS") return {};
    Reader r(body);
    // Installed 60895 capture: uint32 ID then uint32 flags. The newer
    // reference parser's uint8 flags do not describe this client build.
    // Native MiscPackets reads uint32 flags then uint32 ID.
    auto id = r.take<std::uint32_t>();
    auto flags = r.take<std::uint32_t>();
    r.end();
    if (!id || id > 65535 || id == 392)
        throw std::runtime_error("currency has no active native identifier");
    if (flags & ~0x0f)
        throw std::runtime_error("currency flags have no native representation");
    return Packet{name, Writer().pack("II", {flags, native_currency(id)}).finish()};
}
}
