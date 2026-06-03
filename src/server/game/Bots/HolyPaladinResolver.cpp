#include "Bots/HolyPaladinResolver.h"

namespace
{
enum HolyPaladinSpells : uint32
{
    SPELL_HOLY_LIGHT = 635,
    SPELL_LAY_ON_HANDS = 633,
    SPELL_CLEANSE = 4987,
    SPELL_FLASH_OF_LIGHT = 19750,
    SPELL_HOLY_SHOCK = 20473,
    SPELL_AVENGING_WRATH = 31884,
    SPELL_DIVINE_FAVOR = 31842,
    SPELL_HAND_OF_SACRIFICE = 6940,
    SPELL_DIVINE_LIGHT = 82326,
    SPELL_LIGHT_OF_DAWN = 85222,
    SPELL_WORD_OF_GLORY = 85673
};

void Add(std::vector<ResolvedBotAction>& actions, HealerIntent intent, ObjectGuid targetGuid, uint32 spellId, char const* name)
{
    actions.push_back({ intent, targetGuid, spellId, name });
}
}

std::vector<ResolvedBotAction> HolyPaladinResolver::Resolve(HealerDecision const& decision) const
{
    std::vector<ResolvedBotAction> actions;

    auto appendForIntent = [&](HealerIntent intent)
    {
        switch (intent)
        {
            case HealerIntent::Wait:
                actions.push_back({ intent, ObjectGuid::Empty, 0, "wait" });
                break;
            case HealerIntent::EfficientSingleHeal:
                Add(actions, intent, decision.TargetGuid, SPELL_HOLY_LIGHT, "Holy Light");
                break;
            case HealerIntent::FastSingleHeal:
                Add(actions, intent, decision.TargetGuid, SPELL_FLASH_OF_LIGHT, "Flash of Light");
                Add(actions, intent, decision.TargetGuid, SPELL_HOLY_SHOCK, "Holy Shock");
                break;
            case HealerIntent::BigSingleHeal:
                Add(actions, intent, decision.TargetGuid, SPELL_DIVINE_LIGHT, "Divine Light");
                Add(actions, intent, decision.TargetGuid, SPELL_FLASH_OF_LIGHT, "Flash of Light");
                break;
            case HealerIntent::InstantSingleHeal:
                Add(actions, intent, decision.TargetGuid, SPELL_HOLY_SHOCK, "Holy Shock");
                Add(actions, intent, decision.TargetGuid, SPELL_WORD_OF_GLORY, "Word of Glory");
                Add(actions, intent, decision.TargetGuid, SPELL_FLASH_OF_LIGHT, "Flash of Light");
                break;
            case HealerIntent::AoeHeal:
                Add(actions, intent, decision.TargetGuid, SPELL_LIGHT_OF_DAWN, "Light of Dawn");
                Add(actions, HealerIntent::FastSingleHeal, decision.TargetGuid, SPELL_FLASH_OF_LIGHT, "Flash of Light");
                break;
            case HealerIntent::Dispel:
                Add(actions, intent, decision.TargetGuid, SPELL_CLEANSE, "Cleanse");
                break;
            case HealerIntent::ThroughputCooldown:
                Add(actions, intent, ObjectGuid::Empty, SPELL_AVENGING_WRATH, "Avenging Wrath");
                Add(actions, intent, ObjectGuid::Empty, SPELL_DIVINE_FAVOR, "Divine Favor");
                break;
            case HealerIntent::ExternalDefensive:
                Add(actions, intent, decision.TargetGuid, SPELL_LAY_ON_HANDS, "Lay on Hands");
                Add(actions, intent, decision.TargetGuid, SPELL_HAND_OF_SACRIFICE, "Hand of Sacrifice");
                Add(actions, HealerIntent::InstantSingleHeal, decision.TargetGuid, SPELL_HOLY_SHOCK, "Holy Shock");
                break;
            case HealerIntent::MoveSafe:
                actions.push_back({ intent, decision.TargetGuid, 0, "move_safe" });
                break;
        }
    };

    appendForIntent(decision.Intent);
    for (HealerIntent fallback : decision.Fallbacks)
        appendForIntent(fallback);

    return actions;
}
