#include "Bots/HealerBotPolicy.h"

HealerDecision RuleHealerBotPolicy::Decide(HealerFrame const& frame) const
{
    HealerDecision decision;
    decision.Fallbacks = { HealerIntent::InstantSingleHeal, HealerIntent::FastSingleHeal, HealerIntent::EfficientSingleHeal, HealerIntent::MoveSafe, HealerIntent::Wait };

    HealerUnitFrame const* lowest = nullptr;
    uint8 lowCount = 0;
    for (HealerUnitFrame const& unit : frame.Party)
    {
        if (!unit.Alive || !unit.Friendly)
            continue;

        if (!lowest || unit.HealthPct < lowest->HealthPct || (unit.IsOwner && unit.HealthPct == lowest->HealthPct))
            lowest = &unit;

        if (unit.HealthPct <= 70)
            ++lowCount;
    }

    if (!lowest)
        return decision;

    decision.TargetGuid = lowest->Guid;

    if (lowest->HealthPct <= 18)
    {
        decision.Mode = HealerMode::Emergency;
        decision.Intent = HealerIntent::ExternalDefensive;
        decision.Confidence = 0.95f;
        return decision;
    }

    if (lowest->HealthPct <= 32)
    {
        decision.Mode = HealerMode::Emergency;
        decision.Intent = HealerIntent::InstantSingleHeal;
        decision.Confidence = 0.90f;
        return decision;
    }

    if (lowCount >= 3)
    {
        decision.Mode = HealerMode::RecoverAfterDamage;
        decision.Intent = HealerIntent::AoeHeal;
        decision.Confidence = 0.75f;
        return decision;
    }

    if (lowest->HealthPct <= 55)
    {
        decision.Mode = HealerMode::RecoverAfterDamage;
        decision.Intent = HealerIntent::FastSingleHeal;
        decision.Confidence = 0.80f;
        return decision;
    }

    if (lowest->HealthPct <= 78 && frame.BotManaPct > 20)
    {
        decision.Mode = HealerMode::Conserve;
        decision.Intent = HealerIntent::EfficientSingleHeal;
        decision.Confidence = 0.70f;
        return decision;
    }

    decision.TargetGuid.Clear();
    decision.Intent = HealerIntent::Wait;
    decision.Fallbacks.clear();
    return decision;
}
