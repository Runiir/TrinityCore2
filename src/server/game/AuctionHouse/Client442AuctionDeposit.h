#ifndef TRINITY_CLIENT442_AUCTION_DEPOSIT_H
#define TRINITY_CLIENT442_AUCTION_DEPOSIT_H

#include <cmath>
#include <cstdint>

namespace Client442AuctionDeposit
{
// Matches the modern client/server deposit arithmetic for plain template prices.
// Each 12-hour period costs 15%, minus the ceiled fractional remainder. Modern
// auctions have no legacy one-silver minimum, including zero-value items.
inline std::uint64_t Calculate(std::uint32_t sellPrice, std::uint32_t seconds, std::uint32_t quantity)
{
    double raw = sellPrice * 0.15;
    std::uint64_t deposit = static_cast<std::uint64_t>(raw);
    std::uint32_t remainder = static_cast<std::uint32_t>(std::ceil(raw - deposit));
    if (deposit >= remainder)
        deposit -= remainder;
    return deposit * quantity * (seconds / (12 * 60 * 60));
}
}

#endif
