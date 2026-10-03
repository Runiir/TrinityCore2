#pragma once
#include <cstdint>
#include <stdexcept>

namespace bridge
{
// GlyphSlot.dbc (15595) and GlyphSlot.db2 (60895) reuse IDs with different
// types. Preserve the native socket index and its unlock tier; translate the
// referenced row to the modern row with the same semantic type and tier.
inline std::uint32_t modern_glyph_slot(std::uint32_t native)
{
    switch(native)
    {
        case 0:return 0;
        case 21:return 22;
        case 22:return 41;
        case 23:return 42;
        case 24:return 23;
        case 25:return 43;
        case 26:return 25;
        case 41:return 21;
        case 42:return 24;
        case 43:return 26;
        default:throw std::runtime_error("unsupported native glyph slot identity");
    }
}
}
