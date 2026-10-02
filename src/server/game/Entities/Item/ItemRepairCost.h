#ifndef TRINITY_ITEM_REPAIR_COST_H
#define TRINITY_ITEM_REPAIR_COST_H

#include <cmath>
#include <cstdint>

namespace ItemRepairCost
{
// Keep legacy arithmetic by default. Modern clients round the discounted raw
// amount once; rounding before the discount loses copper on some item prices.
inline std::uint32_t Calculate(std::uint32_t lost, std::uint32_t multiplier,
    float quality, float discount, float rate, bool modernRounding)
{
    if (!lost)
        return 0;

    std::uint32_t cost;
    if (modernRounding)
        cost = static_cast<std::uint32_t>(std::round(double(lost) * multiplier * double(quality) * double(discount) * double(rate)));
    else
    {
        cost = static_cast<std::uint32_t>(std::round(lost * multiplier * double(quality)));
        cost = static_cast<std::uint32_t>(cost * discount * rate);
    }

    return cost ? cost : 1; // Damaged artifact-quality items still cost one copper.
}
}

#endif
