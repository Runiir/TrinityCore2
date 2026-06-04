#include "Bots/BotTypes.h"
#include <algorithm>
#include <cctype>

namespace
{
std::string LowerUnderscore(std::string value)
{
    std::replace(value.begin(), value.end(), '-', '_');
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return char(std::tolower(c)); });
    return value;
}
}

char const* ToString(BotMovementMode mode)
{
    switch (mode)
    {
        case BotMovementMode::Follow: return "follow";
        case BotMovementMode::Stay: return "stay";
        case BotMovementMode::Stop: return "stop";
        case BotMovementMode::MoveTo: return "move_to";
        case BotMovementMode::ReturnToGroup: return "return_to_group";
        case BotMovementMode::MoveSafe: return "move_safe";
        case BotMovementMode::Unstuck: return "unstuck";
        default: return "unknown";
    }
}

char const* ToString(BotRole role)
{
    switch (role)
    {
        case BotRole::HolyPaladinHealer: return "holy_paladin";
        case BotRole::Warrior: return "warrior";
        case BotRole::Hunter: return "hunter";
        case BotRole::Rogue: return "rogue";
        case BotRole::Priest: return "priest";
        case BotRole::DeathKnight: return "death_knight";
        case BotRole::Shaman: return "shaman";
        case BotRole::Mage: return "mage";
        case BotRole::Warlock: return "warlock";
        case BotRole::Druid: return "druid";
        case BotRole::Generic: return "generic";
        default: return "unknown";
    }
}

char const* ToString(HealerMode mode)
{
    switch (mode)
    {
        case HealerMode::Conserve: return "conserve";
        case HealerMode::PrepareTankBurst: return "prepare_tank_burst";
        case HealerMode::PrepareGroupAoe: return "prepare_group_aoe";
        case HealerMode::HoldUntilDamage: return "hold_until_damage";
        case HealerMode::Precast: return "precast";
        case HealerMode::RecoverAfterDamage: return "recover_after_damage";
        case HealerMode::Emergency: return "emergency";
        default: return "unknown";
    }
}

char const* ToString(HealerIntent intent)
{
    switch (intent)
    {
        case HealerIntent::Wait: return "wait";
        case HealerIntent::EfficientSingleHeal: return "efficient_single_heal";
        case HealerIntent::FastSingleHeal: return "fast_single_heal";
        case HealerIntent::BigSingleHeal: return "big_single_heal";
        case HealerIntent::InstantSingleHeal: return "instant_single_heal";
        case HealerIntent::AoeHeal: return "aoe_heal";
        case HealerIntent::Dispel: return "dispel";
        case HealerIntent::ThroughputCooldown: return "throughput_cooldown";
        case HealerIntent::ExternalDefensive: return "external_defensive";
        case HealerIntent::MoveSafe: return "move_safe";
        default: return "unknown";
    }
}

std::string NormalizeBotRole(std::string const& role)
{
    std::string normalized = LowerUnderscore(role);
    if (normalized == "holy" || normalized == "holy_pala" || normalized == "holy_paladin_healer")
        return "holy_paladin";
    if (normalized == "dk" || normalized == "deathknight")
        return "death_knight";
    if (normalized == "paladin")
        return "holy_paladin";
    return normalized;
}

BotRole ParseBotRole(std::string const& role)
{
    std::string normalized = NormalizeBotRole(role);
    if (normalized == "holy_paladin") return BotRole::HolyPaladinHealer;
    if (normalized == "warrior") return BotRole::Warrior;
    if (normalized == "hunter") return BotRole::Hunter;
    if (normalized == "rogue") return BotRole::Rogue;
    if (normalized == "priest") return BotRole::Priest;
    if (normalized == "death_knight") return BotRole::DeathKnight;
    if (normalized == "shaman") return BotRole::Shaman;
    if (normalized == "mage") return BotRole::Mage;
    if (normalized == "warlock") return BotRole::Warlock;
    if (normalized == "druid") return BotRole::Druid;
    return BotRole::Generic;
}

BotRoleCategory GetBotRoleCategory(BotRole role)
{
    switch (role)
    {
        case BotRole::HolyPaladinHealer:
        case BotRole::Priest:
        case BotRole::Shaman:
        case BotRole::Druid:
            return BotRoleCategory::Healer;
        case BotRole::Warrior:
        case BotRole::DeathKnight:
            return BotRoleCategory::Tank;
        case BotRole::Hunter:
        case BotRole::Rogue:
        case BotRole::Mage:
        case BotRole::Warlock:
        case BotRole::Generic:
        default:
            return BotRoleCategory::Damage;
    }
}

bool IsKnownBotRole(std::string const& role)
{
    std::string normalized = NormalizeBotRole(role);
    return normalized == "holy_paladin"
        || normalized == "warrior"
        || normalized == "hunter"
        || normalized == "rogue"
        || normalized == "priest"
        || normalized == "death_knight"
        || normalized == "shaman"
        || normalized == "mage"
        || normalized == "warlock"
        || normalized == "druid";
}

bool IsMixedBotRoleSelector(std::string const& role)
{
    std::string normalized = NormalizeBotRole(role);
    return normalized == "mixed" || normalized == "all" || normalized == "any";
}

bool IsHealerBotRole(BotRole role)
{
    return role == BotRole::HolyPaladinHealer;
}

char const* ToString(BotActionResult result)
{
    switch (result)
    {
        case BotActionResult::Ok: return "ok";
        case BotActionResult::Disabled: return "disabled";
        case BotActionResult::NoOwner: return "no_owner";
        case BotActionResult::NoBot: return "no_bot";
        case BotActionResult::InvalidTarget: return "invalid_target";
        case BotActionResult::NotFriendly: return "not_friendly";
        case BotActionResult::DeadTarget: return "dead_target";
        case BotActionResult::OutOfRange: return "out_of_range";
        case BotActionResult::NoLineOfSight: return "no_line_of_sight";
        case BotActionResult::Casting: return "casting";
        case BotActionResult::GlobalCooldown: return "global_cooldown";
        case BotActionResult::Cooldown: return "cooldown";
        case BotActionResult::NoMana: return "no_mana";
        case BotActionResult::BadSpell: return "bad_spell";
        case BotActionResult::CastFailed: return "cast_failed";
        case BotActionResult::Throttled: return "throttled";
        case BotActionResult::NoAction: return "no_action";
        default: return "unknown";
    }
}
