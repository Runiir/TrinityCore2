#include "Bots/BotFireCombustionObservation.h"
#include "Player.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Util.h"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <sstream>
#include <tuple>

namespace BotFireCombustionObservation
{
Snapshot Capture(Player const* actor, Unit const* target, uint64 evaluationStartedAtMs, uint64 observedAtMs)
{
    Snapshot s;
    s.EvaluationStartedAtMs = evaluationStartedAtMs;
    s.ObservedAtMs = observedAtMs;
    s.ActorAvailable = actor != nullptr;
    s.TargetAvailable = target != nullptr;
    if (target)
    {
        s.TargetGuid = target->GetGUID().GetCounter();
        s.TargetEntry = target->GetEntry();
    }
    if (!actor)
        return s;
    s.ActorGuid = actor->GetGUID().GetCounter();
    s.Race = actor->getRace();
    s.BerserkingKnown = actor->HasSpell(26297);
    uint32 const buffs[] = {2825, 32182, 80353, 26297};
    for (uint32 i = 0; i < s.Buffs.size(); ++i)
        if (Aura const* aura = actor->GetAura(buffs[i]))
            s.Buffs[i] = {true, aura->GetDuration()};
    if (!target)
        return s;
    s.IgnitePresent = target->HasAura(12654, actor->GetGUID());
    if (AuraEffect const* ignite = target->GetAuraEffect(12654, EFFECT_0, actor->GetGUID()))
    {
        s.IgniteEffect0Present = true;
        s.IgniteAmount = ignite->GetAmount();
    }
    s.LivingBomb = target->HasAura(44457, actor->GetGUID());
    s.Pyro92315 = target->HasAura(92315, actor->GetGUID());
    s.Pyro11366 = target->HasAura(11366, actor->GetGUID());
    SpellInfo const* combustion = sSpellMgr->GetSpellInfo(11129);
    SpellInfo const* periodic = sSpellMgr->GetSpellInfo(83853);
    s.CombustionAvailable = combustion != nullptr;
    s.PeriodicAvailable = periodic != nullptr;
    if (!combustion || !periodic)
        return s;
    // CalculateSpellDamage/CalcValue transitively apply spell modifiers to a
    // prepared spell. Telemetry must never enter those paths. Only a static
    // script-effect base is supported here; the sum is NOT native-exact.
    SpellEffectInfo const& scaling = combustion->Effects[EFFECT_0];
    s.RawScalingAvailable = scaling.Effect == SPELL_EFFECT_SCRIPT_EFFECT && scaling.DieSides == 0
        && scaling.RealPointsPerLevel == 0 && scaling.PointsPerComboPoint == 0
        && scaling.Scaling.Coefficient == 0 && scaling.Scaling.Variance == 0
        && scaling.Scaling.ComboPointsCoefficient == 0
        && !combustion->HasAttribute(SPELL_ATTR8_MASTERY_AFFECTS_POINTS)
        && !combustion->HasAttribute(SPELL_ATTR1_FINISHING_MOVE_DAMAGE);
    if (s.RawScalingAvailable)
        s.ScalingPercent = static_cast<float>(scaling.BasePoints);
    for (AuraEffect const* effect : target->GetAuraEffectsByType(SPELL_AURA_PERIODIC_DAMAGE))
    {
        SpellInfo const* info = effect->GetSpellInfo();
        if (effect->GetCasterGUID() != actor->GetGUID()
            || !(info->GetSchoolMask() & SPELL_SCHOOL_MASK_FIRE)
            || info->SpellFamilyName != SPELLFAMILY_MAGE
            || !info->IsAffected(SPELLFAMILY_MAGE, combustion->Effects[EFFECT_0].SpellClassMask))
            continue;
        int32 const contribution = CalculatePct(effect->GetAmount(), s.ScalingPercent);
        ++s.EligibleComponentCount;
        s.SummedBasePoints += contribution;
        s.Components.push_back({info->Id, effect->GetEffIndex(), effect->GetAmount(), contribution});
        std::sort(s.Components.begin(), s.Components.end(), [](Component const& a, Component const& b)
        {
            return std::tie(a.SpellId, a.EffectIndex, a.Amount, a.Contribution)
                < std::tie(b.SpellId, b.EffectIndex, b.Amount, b.Contribution);
        });
        if (s.Components.size() > 8)
            s.Components.pop_back();
    }
    s.DurationMs = periodic->GetDuration();
    s.HasteMod = periodic->CalcPeriodicHasteMod(actor);
    for (uint32 i = 0; i < MAX_SPELL_EFFECTS; ++i)
        if (periodic->Effects[i].ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE)
        {
            s.PeriodicEffectIndex = int32(i);
            s.PeriodMs = periodic->Effects[i].AuraPeriod;
            break;
        }
    s.FireCritPct = actor->GetFloatValue(PLAYER_SPELL_CRIT_PERCENTAGE1 + SPELL_SCHOOL_FIRE);
    s.TargetSpellCritPct = target->GetTotalAuraModifierByMiscMask(SPELL_AURA_MOD_ATTACKER_SPELL_CRIT_CHANCE, SPELL_SCHOOL_MASK_FIRE);
    s.TargetAllCritPct = target->GetTotalAuraModifier(SPELL_AURA_MOD_ATTACKER_SPELL_AND_WEAPON_CRIT_CHANCE);
    s.SpellCritMultiplier = periodic->CritDamageMultiplier;
    s.FireCritDamageMultiplier = actor->GetTotalAuraMultiplierByMiscMask(SPELL_AURA_MOD_CRIT_DAMAGE_BONUS, SPELL_SCHOOL_MASK_FIRE);
    // Raw-input approximation: deliberately do not call spell-modifying preview APIs.
    double const period = double(s.PeriodMs) * s.HasteMod;
    if (!s.RawScalingAvailable || observedAtMs < evaluationStartedAtMs || !evaluationStartedAtMs || s.PeriodicEffectIndex < 0
        || s.DurationMs <= 0 || !std::isfinite(period) || period < 1 || period > std::numeric_limits<int32>::max()
        || !std::isfinite(s.FireCritPct) || !std::isfinite(s.TargetSpellCritPct) || !std::isfinite(s.TargetAllCritPct)
        || !std::isfinite(s.SpellCritMultiplier) || !std::isfinite(s.FireCritDamageMultiplier)
        || s.SummedBasePoints > std::numeric_limits<int32>::max() || s.SummedBasePoints < 0)
        return s;
    s.HastedPeriodMs = int32(period);
    s.TickCount = s.DurationMs / s.HastedPeriodMs;
    double const crit = std::clamp(double(s.FireCritPct + s.TargetSpellCritPct + s.TargetAllCritPct), 0.0, 100.0) / 100;
    s.EstimatedTotal = double(s.SummedBasePoints) * s.TickCount
        * (1 + crit * (double(s.SpellCritMultiplier) * s.FireCritDamageMultiplier - 1));
    s.EstimateAvailable = std::isfinite(s.EstimatedTotal);
    return s;
}

std::string ToJson(Snapshot const& s)
{
    std::ostringstream o;
    o << std::boolalpha << std::setprecision(std::numeric_limits<float>::max_digits10);
    auto number = [&o](double value) { if (std::isfinite(value)) o << value; else o << "null"; };
    o << "{\"schema\":\"fire_combustion_candidate_observation_v1\",\"evaluation_started_at_ms\":" << s.EvaluationStartedAtMs
      << ",\"observed_at_ms\":" << s.ObservedAtMs << ",\"actor_guid\":" << s.ActorGuid << ",\"target_guid\":" << s.TargetGuid
      << ",\"target_entry\":" << s.TargetEntry << ",\"combustion_spell_id\":11129,\"periodic_spell_id\":83853"
      << ",\"available\":{\"actor\":" << s.ActorAvailable << ",\"target\":" << s.TargetAvailable
      << ",\"combustion\":" << s.CombustionAvailable << ",\"periodic\":" << s.PeriodicAvailable
      << ",\"raw_scale\":" << s.RawScalingAvailable << "}"
      << ",\"clock_valid\":" << (s.EvaluationStartedAtMs != 0 && s.ObservedAtMs >= s.EvaluationStartedAtMs)
      << ",\"owned_auras\":{\"ignite_present\":" << s.IgnitePresent << ",\"ignite_effect0_present\":" << s.IgniteEffect0Present << ",\"ignite_effect0_amount\":";
    if (s.IgniteEffect0Present) o << s.IgniteAmount; else o << "null";
    o << ",\"living_bomb\":" << s.LivingBomb << ",\"pyro92315\":" << s.Pyro92315 << ",\"pyro11366\":" << s.Pyro11366
      << "},\"gate\":{\"missing_ignite_effect0\":" << !s.IgniteEffect0Present
      << ",\"ignite_below_10000\":" << (s.IgniteEffect0Present && s.IgniteAmount < 10000)
      << ",\"missing_living_bomb\":" << !s.LivingBomb << ",\"missing_pyro\":" << (!s.Pyro92315 && !s.Pyro11366)
      << ",\"current_gate_ready\":" << (s.ActorAvailable && s.TargetAvailable && s.IgniteEffect0Present && s.IgniteAmount >= 10000 && s.LivingBomb && (s.Pyro92315 || s.Pyro11366))
      << "},\"race_id\":" << s.Race << ",\"berserking_known\":" << s.BerserkingKnown
      << ",\"buff_columns\":[\"spell_id\",\"present\",\"remaining_ms\"],\"buffs\":[";
    uint32 const buffs[] = {2825, 32182, 80353, 26297};
    for (uint32 i = 0; i < s.Buffs.size(); ++i)
    {
        if (i) o << ',';
        o << '[' << buffs[i] << ',' << s.Buffs[i].Present << ',';
        if (s.Buffs[i].Present) o << s.Buffs[i].RemainingMs; else o << "null";
        o << ']';
    }
    o << "],\"scaling_kind\":\"raw_effect0_excluding_spellmods\",\"scaling_percent\":";
    if (s.RawScalingAvailable) number(s.ScalingPercent); else o << "null";
    o << ",\"eligible_component_count\":" << s.EligibleComponentCount << ",\"summed_base_points\":";
    if (s.RawScalingAvailable) o << s.SummedBasePoints; else o << "null";
    o << ",\"components_truncated\":" << (s.EligibleComponentCount > s.Components.size())
      << ",\"component_columns\":[\"spell_id\",\"effect_index\",\"amount\",\"contribution\"],\"components\":[";
    for (size_t i = 0; i < s.Components.size(); ++i)
    {
        if (i) o << ',';
        Component const& c = s.Components[i];
        o << '[' << c.SpellId << ',' << c.EffectIndex << ',' << c.Amount << ',';
        if (s.RawScalingAvailable) o << c.Contribution; else o << "null";
        o << ']';
    }
    o << "],\"periodic\":{\"effect_index\":" << s.PeriodicEffectIndex << ",\"duration_ms\":" << s.DurationMs << ",\"period_ms\":" << s.PeriodMs
      << ",\"haste_mod\":"; number(s.HasteMod);
    o << ",\"hasted_period_ms\":" << s.HastedPeriodMs << ",\"ticks\":" << s.TickCount << "},\"crit\":[";
    number(s.FireCritPct); o << ','; number(s.TargetSpellCritPct); o << ','; number(s.TargetAllCritPct); o << ',';
    number(s.SpellCritMultiplier); o << ','; number(s.FireCritDamageMultiplier);
    o << "],\"crit_columns\":[\"fire_pct\",\"target_spell_pct\",\"target_all_pct\",\"spell_multiplier\",\"fire_damage_multiplier\"]"
      << ",\"native_exact\":false,\"estimate_kind\":\"derived_candidate_state_not_observed_outcome\",\"formula\":\"v1:sum*ticks*(1+clamp((fire+targetSpell+targetAll)/100,0,1)*(spellCrit*fireCrit-1))\""
      << ",\"excluded\":\"spellmods,absorbs,resistance,later_aura_changes,landed_RNG\",\"estimated_total\":";
    if (s.EstimateAvailable) number(s.EstimatedTotal); else o << "null";
    o << '}';
    std::string const json = o.str();
    // Numeric extremes can consume more bytes than ordinary native observations.
    // Preserve every scalar and uncapped aggregate; reduce only the disclosed list.
    if (json.size() > 2048 && !s.Components.empty())
    {
        Snapshot bounded = s;
        bounded.Components.pop_back();
        return ToJson(bounded);
    }
    return json;
}
}
