#ifndef TRINITY_SPELL_COMBUSTION_H
#define TRINITY_SPELL_COMBUSTION_H

#include "Define.h"
#include <algorithm>
#include <cmath>
#include <limits>

namespace SpellCombustion
{
// The supported Fire DoTs have no pre-haste period modifier. Their DBC
// AuraPeriod is the source-rate divisor; the child applies haste independently.
inline double SourceRate(int32 tickAmount, int32 basePeriodMs)
{
    return basePeriodMs > 0 ? double(tickAmount) * 1000.0 / basePeriodMs : 0.0;
}

// Preserve fractional source rates until after summing and applying effect 0.
// Truncate once toward zero for native BP0, bounded to its positive int32 range.
inline int32 ScaledBasePoints(double sourceRate, float scalingPercent)
{
    double const scaled = sourceRate * double(scalingPercent) / 100.0;
    if (!std::isfinite(scaled) || scaled <= 0)
        return 0;
    return int32(std::min(scaled, double(std::numeric_limits<int32>::max())));
}
}

#endif
