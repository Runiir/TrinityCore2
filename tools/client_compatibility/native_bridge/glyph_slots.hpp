#pragma once
#include <cstdint>
#include <stdexcept>

namespace bridge
{
// The pinned GlyphSlot rows have the same IDs, types and tiers. Do not
// rotate them using GetGlyphInfo's catalog type numbers: GetGlyphSocketInfo
// uses Major=1/Minor=2/Prime=3 while the catalog uses Prime=1/Major=2/Minor=3.
// Actual pending Battle glyphs match socket type 2, and the stock tooltip
// labels that socket Minor. Preserve the DBC identity and unlock tier.
inline std::uint32_t modern_glyph_slot(std::uint32_t native)
{
    switch(native)
    {
        case 0:case 21:case 22:case 23:case 24:case 25:case 26:
        case 41:case 42:case 43:return native;
        default:throw std::runtime_error("unsupported native glyph slot identity");
    }
}
}
