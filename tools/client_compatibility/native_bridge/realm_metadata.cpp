// Local realm-name query contract: pinned 4.4.2 Query/AuthenticationPackets.
#include "protocol.hpp"

namespace bridge
{
Bytes Protocol::realm_name(View body)
{
    Reader r(body);auto realm = r.take<std::uint32_t>();r.end();
    Writer w;w.put(realm).put<std::uint8_t>(realm == 1 ? 0 : 1);
    if (realm == 1)
    {
        std::string actual = "Client442 Lab", normalized = "Client442Lab";
        w.bits(1, 1).bits(0, 1).bits(actual.size(), 8).bits(normalized.size(), 8)
            .flush().raw(actual).raw(normalized);
    }
    return w.finish();
}
} // namespace bridge
