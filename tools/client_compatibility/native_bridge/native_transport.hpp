#pragma once
#include "protocol.hpp"

namespace bridge
{
// Native Object::BuildMovementUpdate has separate unit and GO transport orders.
struct NativeTransport
{
    std::array<bool,8> present{};
    std::uint64_t guid=0;
    bool previous=false,vehicle=false;
    void bits(Reader &r,bool gameobject=false);
    Value read(Reader &r,bool gameobject=false);
};
Writer &transport_info(Writer &w,Value const &transport,unsigned map);
}
