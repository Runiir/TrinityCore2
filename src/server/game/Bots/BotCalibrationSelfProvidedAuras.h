#ifndef TRINITY_BOT_CALIBRATION_SELF_PROVIDED_AURAS_H
#define TRINITY_BOT_CALIBRATION_SELF_PROVIDED_AURAS_H

#include "Bots/BotPersistentSelfBuffContract.h"
#include "UpdateFields.h"
#include <array>

namespace BotCalibrationSelfProvidedAuras
{
inline constexpr std::array<uint32, 11> PlayerAuraIds = {
    53646, 79058, 24932, 2895, 8515, 8076, 82930, 57669, 20217, 79063, 79102,
};
inline constexpr std::array<uint32, 4> TargetAuraIds = { 1490, 22959, 81326, 58567 };
enum class Source { Own, Foreign, Unknown };
struct Result
{
    bool Compatible = true;
    uint32 SpellId = 0;
    char const* SourceClassification = "absent_or_own_class_setup";
};

template<class PlayerT>
Source WrathOfAirSource(PlayerT* bot)
{
    bool observed = false, unknown = false, foreign = false;
    auto const range = bot->GetAppliedAuras().equal_range(2895);
    for (auto itr = range.first; itr != range.second; ++itr)
    {
        auto const* aura = itr->second ? itr->second->GetBase() : nullptr;
        auto* caster = aura ? aura->GetCaster() : nullptr;
        auto* owner = caster && caster->IsTotem() ? caster->ToTotem()->GetOwner() : nullptr;
        observed = true;
        if (!caster || (caster->IsTotem() && (!owner
                || !caster->GetUInt32Value(UNIT_CREATED_BY_SPELL))))
            unknown = true;
        else if (!caster->IsTotem() || owner->GetGUID() != bot->GetGUID()
            || caster->GetUInt32Value(UNIT_CREATED_BY_SPELL) != 3738)
            foreign = true;
    }
    return !observed || unknown ? Source::Unknown : foreign ? Source::Foreign : Source::Own;
}

template<class PlayerT>
Result PlayerAuras(PlayerT* bot, std::string const& role, std::string const& spec)
{
    if (!bot)
        return { false, 0, "actor_unavailable" };
    for (uint32 spellId : PlayerAuraIds)
    {
        if (!bot->HasAura(spellId))
            continue;
        if (spellId == 2895)
        {
            Source source = WrathOfAirSource(bot);
            if (source != Source::Own)
                return { false, spellId, source == Source::Unknown ? "unknown_source" : "foreign_source" };
            if (bot->getClass() == CLASS_SHAMAN
                && bot->GetPrimaryTalentTree(bot->GetActiveSpec()) == 261 && spec == "elemental_shaman")
                continue;
            return { false, spellId, "not_class_setup" };
        }
        bool selected = false;
        for (auto const& buff : BotPersistentSelfBuffContract::Buffs)
            if ((buff.AuraId == spellId || buff.AlternateAuraId == spellId)
                && BotPersistentSelfBuffContract::Matches(buff, bot->getClass(), role, spec)
                && bot->HasSpell(buff.SpellId))
                selected = true;
        if (!selected)
            return { false, spellId, "not_class_setup" };
        // Observe current native applications, not ExecuteCombat::Ok or an
        // invented per-attempt cast receipt. Already-active own buffs remain valid.
        bool observed = false;
        auto const range = bot->GetAppliedAuras().equal_range(spellId);
        for (auto itr = range.first; itr != range.second; ++itr)
        {
            auto const* aura = itr->second ? itr->second->GetBase() : nullptr;
            auto* caster = aura ? aura->GetCaster() : nullptr;
            if (!caster || aura->GetCasterGUID().IsEmpty())
                return { false, spellId, "unknown_source" };
            if (caster != bot || aura->GetCasterGUID() != bot->GetGUID())
                return { false, spellId, "foreign_source" };
            observed = true;
        }
        if (!observed)
            return { false, spellId, "unknown_source" };
    }
    return {};
}

template<class UnitT>
Result TargetAuras(UnitT* target)
{
    if (!target)
        return { false, 0, "target_unavailable" };
    for (uint32 spellId : TargetAuraIds)
        if (target->HasAura(spellId))
            return { false, spellId, "forbidden_target_aura" };
    return { true, 0, "absent" };
}
}
#endif
