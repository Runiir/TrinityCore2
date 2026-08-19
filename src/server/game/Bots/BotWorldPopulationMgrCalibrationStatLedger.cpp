#include "Bots/BotWorldPopulationMgr.h"

#include "Pet.h"
#include "Player.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "Unit.h"
#include "Util.h"

#include <algorithm>
#include <array>
#include <sstream>
#include <tuple>

namespace
{
char const* PrimaryStatName(uint8 statIndex)
{
    static constexpr std::array<char const*, 5> Names = {
        "strength", "agility", "stamina", "intellect", "spirit"
    };
    return statIndex < Names.size() ? Names[statIndex] : "unknown";
}

bool AuraAffectsStat(AuraEffect const* effect, Stats stat)
{
    if (!effect)
        return false;
    if (effect->GetAuraType() == SPELL_AURA_MOD_TOTAL_STAT_PERCENTAGE)
        return !effect->GetMiscValueB()
            || (effect->GetMiscValueB() & (1 << AsUnderlyingType(stat)));
    return effect->GetMiscValue() < 0
        || effect->GetMiscValue() == AsUnderlyingType(stat);
}
}

void BotWorldPopulationMgr::ObserveCalibrationEffectiveStats(
    Unit* unit, uint64 observedAtMs,
    CalibrationMetrics::EffectiveStatVector& stats)
{
    if (!unit)
        return;

    stats.Observed = true;
    stats.ObservedAtMs = observedAtMs;
    stats.Guid = unit->GetGUID().GetCounter();
    stats.Entry = unit->GetEntry();
    stats.Strength = unit->GetStat(STAT_STRENGTH);
    stats.Agility = unit->GetStat(STAT_AGILITY);
    stats.Stamina = unit->GetStat(STAT_STAMINA);
    stats.Intellect = unit->GetStat(STAT_INTELLECT);
    stats.Spirit = unit->GetStat(STAT_SPIRIT);
    stats.AttackPower = unit->GetTotalAttackPowerValue(BASE_ATTACK);
    stats.RangedAttackPower = unit->GetTotalAttackPowerValue(RANGED_ATTACK);
    stats.SpellPower = unit->SpellBaseDamageBonusDone(
        SPELL_SCHOOL_MASK_SPELL, true);
    stats.Armor = unit->GetArmor();
    stats.Health = unit->GetMaxHealth();
    stats.Mana = unit->GetMaxPower(POWER_MANA);

    float const meleeTime = unit->GetFloatValue(UNIT_FIELD_BASEATTACKTIME);
    float const rangedTime = unit->GetFloatValue(UNIT_FIELD_RANGEDATTACKTIME);
    float const spellTime = unit->GetFloatValue(UNIT_MOD_CAST_HASTE);
    stats.MeleeSpeedMultiplier = meleeTime > 0.0f
        ? float(unit->GetBaseAttackTime(BASE_ATTACK)) / meleeTime : 1.0f;
    stats.RangedSpeedMultiplier = rangedTime > 0.0f
        ? float(unit->GetBaseAttackTime(RANGED_ATTACK)) / rangedTime : 1.0f;
    stats.SpellSpeedMultiplier = spellTime > 0.0f ? 1.0f / spellTime : 1.0f;
    stats.PhysicalHitPct = unit->GetTotalAuraModifier(
        SPELL_AURA_MOD_HIT_CHANCE);
    stats.SpellHitPct = unit->GetTotalAuraModifier(
        SPELL_AURA_MOD_SPELL_HIT_CHANCE);
    stats.MeleeCritPct = unit->GetUnitCriticalChanceDone(BASE_ATTACK);

    if (Player* player = unit->ToPlayer())
    {
        auto rating = [player](CombatRating type)
        {
            return player->GetUInt32Value(
                PLAYER_FIELD_COMBAT_RATING_1 + AsUnderlyingType(type));
        };
        stats.HitRating = rating(CR_HIT_SPELL);
        stats.CritRating = rating(CR_CRIT_SPELL);
        stats.HasteRating = rating(CR_HASTE_SPELL);
        stats.ExpertiseRating = rating(CR_EXPERTISE);
        stats.MasteryRating = rating(CR_MASTERY);
        stats.PhysicalHitPct = player->GetRatingBonusValue(CR_HIT_MELEE);
        stats.SpellHitPct = player->GetRatingBonusValue(CR_HIT_SPELL);
        stats.MeleeCritPct = player->GetFloatValue(PLAYER_CRIT_PERCENTAGE);
        stats.RangedCritPct = player->GetFloatValue(
            PLAYER_RANGED_CRIT_PERCENTAGE);
        stats.SpellCritPct = player->GetFloatValue(
            PLAYER_SPELL_CRIT_PERCENTAGE1 + SPELL_SCHOOL_SHADOW);
        stats.MasteryPoints = player->GetRatingBonusValue(CR_MASTERY);
    }
    if (Pet* pet = unit->ToPet())
    {
        stats.BonusDamage = pet->GetBonusDamage();
        stats.SpellPower = stats.BonusDamage;
    }

    static constexpr std::array<AuraType, 3> AuraTypes = {
        SPELL_AURA_MOD_STAT,
        SPELL_AURA_MOD_PERCENT_STAT,
        SPELL_AURA_MOD_TOTAL_STAT_PERCENTAGE,
    };
    for (uint8 statIndex = STAT_STRENGTH; statIndex < MAX_STATS; ++statIndex)
    {
        Stats const stat = Stats(statIndex);
        UnitMods const unitMod = UnitMods(UNIT_MOD_STAT_START + statIndex);
        CalibrationMetrics::EffectiveStatVector::PrimaryStatLedger& ledger =
            stats.PrimaryStatLedgerEntries[statIndex];
        ledger.StatIndex = statIndex;
        ledger.CreateStat = unit->GetCreateStat(stat);
        ledger.BaseValue = unit->GetFlatModifierValue(unitMod, BASE_VALUE);
        ledger.BasePct = unit->GetPctModifierValue(unitMod, BASE_PCT);
        ledger.TotalValue = unit->GetFlatModifierValue(unitMod, TOTAL_VALUE);
        ledger.TotalPct = unit->GetPctModifierValue(unitMod, TOTAL_PCT);
        ledger.RecomputedTotal = unit->GetTotalStatValue(stat);
        ledger.PublishedStat = unit->GetStat(stat);
        ledger.AuraContributions.clear();
        for (AuraType auraType : AuraTypes)
            for (AuraEffect const* effect : unit->GetAuraEffectsByType(auraType))
            {
                if (!AuraAffectsStat(effect, stat))
                    continue;
                CalibrationMetrics::EffectiveStatVector::AuraContribution row;
                row.AuraType = uint16(auraType);
                row.SpellId = effect->GetId();
                row.EffectIndex = effect->GetEffIndex();
                row.Amount = effect->GetAmount();
                row.MiscValue = effect->GetMiscValue();
                row.MiscValueB = effect->GetMiscValueB();
                row.CasterGuid = effect->GetCasterGUID().GetRawValue();
                ledger.AuraContributions.push_back(row);
            }
        std::sort(ledger.AuraContributions.begin(),
            ledger.AuraContributions.end(), [](auto const& left,
                auto const& right)
            {
                return std::tie(left.AuraType, left.SpellId, left.EffectIndex,
                           left.CasterGuid)
                    < std::tie(right.AuraType, right.SpellId,
                           right.EffectIndex, right.CasterGuid);
            });
    }
}

void BotWorldPopulationMgr::AppendCalibrationEffectiveStatsJson(
    std::ostringstream& json,
    CalibrationMetrics::EffectiveStatVector const& stats)
{
    json << "{\"observed\":" << (stats.Observed ? "true" : "false")
         << ",\"observed_at_ms\":" << stats.ObservedAtMs
         << ",\"guid\":" << stats.Guid
         << ",\"entry\":" << stats.Entry
         << ",\"strength\":" << stats.Strength
         << ",\"agility\":" << stats.Agility
         << ",\"stamina\":" << stats.Stamina
         << ",\"intellect\":" << stats.Intellect
         << ",\"spirit\":" << stats.Spirit
         << ",\"attack_power\":" << stats.AttackPower
         << ",\"ranged_attack_power\":" << stats.RangedAttackPower
         << ",\"spell_power\":" << stats.SpellPower
         << ",\"bonus_damage\":" << stats.BonusDamage
         << ",\"armor\":" << stats.Armor
         << ",\"health\":" << stats.Health
         << ",\"mana\":" << stats.Mana
         << ",\"hit_rating\":" << stats.HitRating
         << ",\"crit_rating\":" << stats.CritRating
         << ",\"haste_rating\":" << stats.HasteRating
         << ",\"expertise_rating\":" << stats.ExpertiseRating
         << ",\"mastery_rating\":" << stats.MasteryRating
         << ",\"physical_hit_pct\":" << stats.PhysicalHitPct
         << ",\"spell_hit_pct\":" << stats.SpellHitPct
         << ",\"melee_crit_pct\":" << stats.MeleeCritPct
         << ",\"ranged_crit_pct\":" << stats.RangedCritPct
         << ",\"spell_crit_pct\":" << stats.SpellCritPct
         << ",\"mastery_points\":" << stats.MasteryPoints
         << ",\"melee_speed_multiplier\":"
         << stats.MeleeSpeedMultiplier
         << ",\"ranged_speed_multiplier\":"
         << stats.RangedSpeedMultiplier
         << ",\"spell_speed_multiplier\":"
         << stats.SpellSpeedMultiplier
         << ",\"modifier_ledger\":{\"schema\":"
            "\"trinity_scoring_start_stat_modifier_ledger_v1\","
            "\"primary_stats\":[";
    bool firstStat = true;
    for (uint8 statIndex = STAT_STRENGTH; statIndex < MAX_STATS; ++statIndex)
    {
        auto const& ledger = stats.PrimaryStatLedgerEntries[statIndex];
        if (!firstStat)
            json << ',';
        firstStat = false;
        json << "{\"stat_index\":" << uint32(statIndex)
             << ",\"stat\":\"" << PrimaryStatName(statIndex) << '"'
             << ",\"create_stat\":" << ledger.CreateStat
             << ",\"base_value\":" << ledger.BaseValue
             << ",\"base_pct\":" << ledger.BasePct
             << ",\"total_value\":" << ledger.TotalValue
             << ",\"total_pct\":" << ledger.TotalPct
             << ",\"recomputed_total\":" << ledger.RecomputedTotal
             << ",\"published_stat\":" << ledger.PublishedStat
             << ",\"aura_effects\":[";
        bool firstAura = true;
        for (auto const& aura : ledger.AuraContributions)
        {
            if (!firstAura)
                json << ',';
            firstAura = false;
            json << "{\"aura_type\":" << aura.AuraType
                 << ",\"spell_id\":" << aura.SpellId
                 << ",\"effect_index\":" << uint32(aura.EffectIndex)
                 << ",\"amount\":" << aura.Amount
                 << ",\"misc_value\":" << aura.MiscValue
                 << ",\"misc_value_b\":" << aura.MiscValueB
                 << ",\"caster_guid\":" << aura.CasterGuid << '}';
        }
        json << "]}";
    }
    json << "]}}";
}
