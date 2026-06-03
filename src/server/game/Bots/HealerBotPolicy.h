#ifndef TRINITY_HEALER_BOT_POLICY_H
#define TRINITY_HEALER_BOT_POLICY_H

#include "Bots/BotTypes.h"

class HealerBotPolicy
{
public:
    virtual ~HealerBotPolicy() = default;
    virtual HealerDecision Decide(HealerFrame const& frame) const = 0;
};

class RuleHealerBotPolicy : public HealerBotPolicy
{
public:
    HealerDecision Decide(HealerFrame const& frame) const override;
};

#endif
