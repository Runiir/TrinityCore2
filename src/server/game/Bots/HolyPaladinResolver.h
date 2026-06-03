#ifndef TRINITY_HOLY_PALADIN_RESOLVER_H
#define TRINITY_HOLY_PALADIN_RESOLVER_H

#include "Bots/BotTypes.h"

class HolyPaladinResolver
{
public:
    std::vector<ResolvedBotAction> Resolve(HealerDecision const& decision) const;
};

#endif
