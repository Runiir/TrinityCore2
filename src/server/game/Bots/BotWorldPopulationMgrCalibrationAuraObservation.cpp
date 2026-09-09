#include "Common.h"
#include "Bots/BotWorldPopulationMgr.h"

#include "Pet.h"
#include "Player.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"

#include <algorithm>
#include <array>
#include <sstream>

namespace
{
constexpr std::array<uint32, 2> OwnerAuraSpellIds = {24604, 76659};
}

void BotWorldPopulationMgr::ObserveCalibrationOwnerAuras(
    CalibrationMetrics& metrics, Player* bot, uint64 observedAtMs, bool scoringStart)
{
    if (!bot)
        return;
    for (size_t index = 0; index < OwnerAuraSpellIds.size(); ++index)
    {
        auto& row = metrics.OwnerAuraObservations[index];
        row.SpellId = OwnerAuraSpellIds[index];
        if (row.SampleCount && observedAtMs <= row.LastSampleAtMs)
        {
            ++row.NonIncreasingTimestampSamples;
            continue;
        }
        AuraApplication const* application = bot->GetAuraApplication(row.SpellId);
        Aura const* aura = application ? application->GetBase() : nullptr;
        bool const active = aura != nullptr;
        uint8 const mask = application ? application->GetEffectMask() : 0;
        AuraEffect const* effect = aura && (mask & 1) ? aura->GetEffect(0) : nullptr;
        uint64 const caster = aura ? aura->GetCasterGUID().GetRawValue() : 0;
        if (row.SampleCount)
        {
            row.MaximumSampleGapMs = std::max(row.MaximumSampleGapMs, observedAtMs - row.LastSampleAtMs);
            if (active && !row.LastActive)
                ++row.ActivationTransitionCount;
            if (!active && row.LastActive)
                ++row.DeactivationTransitionCount;
        }
        else
            row.FirstSampleAtMs = observedAtMs;
        ++row.SampleCount;
        row.LastSampleAtMs = observedAtMs;
        row.LastActive = active;
        if (scoringStart)
        {
            row.ScoringStartObserved = true;
            row.ScoringStartActive = active;
            row.ScoringStartCasterGuid = caster;
            row.ScoringStartEffect0Present = effect != nullptr;
            row.ScoringStartAuraType = effect ? uint32(effect->GetAuraType()) : 0;
            row.ScoringStartAmount = effect ? effect->GetAmount() : 0;
            row.ScoringStartActiveEffectMask = mask;
        }
        if (!active)
        {
            ++row.InactiveSamples;
            continue;
        }
        if (!row.ActiveSamples)
        {
            row.FirstActiveAtMs = observedAtMs;
            row.FirstCasterGuid = caster;
            if (scoringStart)
                row.FirstActivePlayerStats = metrics.ScoringStartPlayerStats;
            else
                ObserveCalibrationEffectiveStats(bot, observedAtMs, row.FirstActivePlayerStats);
        }
        ++row.ActiveSamples;
        row.LastActiveAtMs = observedAtMs;
        row.LastCasterGuid = caster;
        row.LastActiveEffectMask = mask;
        if (caster && caster == bot->GetGUID().GetRawValue())
            ++row.OwnerCasterSamples;
        else if (caster && bot->GetPet() && caster == bot->GetPet()->GetGUID().GetRawValue())
            ++row.PrimaryPetCasterSamples;
        else
            ++row.OtherOrMissingCasterSamples;
        if (!effect)
            ++row.MissingEffect0Samples;
        else
        {
            uint32 const type = uint32(effect->GetAuraType());
            int32 const amount = effect->GetAmount();
            if (!row.Effect0Samples)
            {
                row.MinimumAuraType = row.MaximumAuraType = type;
                row.MinimumAmount = row.MaximumAmount = amount;
            }
            ++row.Effect0Samples;
            row.MinimumAuraType = std::min(row.MinimumAuraType, type);
            row.MaximumAuraType = std::max(row.MaximumAuraType, type);
            row.MinimumAmount = std::min(row.MinimumAmount, amount);
            row.MaximumAmount = std::max(row.MaximumAmount, amount);
        }
    }
}

void BotWorldPopulationMgr::AppendCalibrationOwnerAurasJson(
    std::ostringstream& json, CalibrationMetrics const* metrics)
{
    json << ",\"owner_aura_observation\":{\"scoring_start_stats_path\":\"scoring_start_stats.player\",\"auras\":[";
    for (size_t index = 0; index < OwnerAuraSpellIds.size(); ++index)
    {
        if (index)
            json << ',';
        CalibrationMetrics::OwnerAuraObservation const empty;
        auto const& row = metrics ? metrics->OwnerAuraObservations[index] : empty;
        json << "{\"spell_id\":" << OwnerAuraSpellIds[index]
             << ",\"sample_count\":" << row.SampleCount
             << ",\"active_samples\":" << row.ActiveSamples
             << ",\"inactive_samples\":" << row.InactiveSamples
             << ",\"non_increasing_timestamp_samples\":" << row.NonIncreasingTimestampSamples
             << ",\"first_sample_at_ms\":" << row.FirstSampleAtMs
             << ",\"last_sample_at_ms\":" << row.LastSampleAtMs
             << ",\"maximum_sample_gap_ms\":" << row.MaximumSampleGapMs
             << ",\"scoring_start_observed\":" << (row.ScoringStartObserved ? "true" : "false")
             << ",\"scoring_start_active\":" << (row.ScoringStartActive ? "true" : "false")
             << ",\"scoring_start_caster_guid\":" << row.ScoringStartCasterGuid
             << ",\"scoring_start_effect0_present\":" << (row.ScoringStartEffect0Present ? "true" : "false")
             << ",\"effect_index\":0,\"scoring_start_aura_type\":" << row.ScoringStartAuraType
             << ",\"scoring_start_amount\":" << row.ScoringStartAmount
             << ",\"scoring_start_active_effect_mask\":" << uint32(row.ScoringStartActiveEffectMask)
             << ",\"last_active_effect_mask\":" << uint32(row.LastActiveEffectMask)
             << ",\"first_active_at_ms\":" << row.FirstActiveAtMs
             << ",\"last_active_at_ms\":" << row.LastActiveAtMs
             << ",\"activation_transition_count\":" << row.ActivationTransitionCount
             << ",\"deactivation_transition_count\":" << row.DeactivationTransitionCount
             << ",\"owner_caster_samples\":" << row.OwnerCasterSamples
             << ",\"primary_pet_caster_samples\":" << row.PrimaryPetCasterSamples
             << ",\"other_or_missing_caster_samples\":" << row.OtherOrMissingCasterSamples
             << ",\"first_caster_guid\":" << row.FirstCasterGuid
             << ",\"last_caster_guid\":" << row.LastCasterGuid
             << ",\"effect0_samples\":" << row.Effect0Samples
             << ",\"missing_effect0_samples\":" << row.MissingEffect0Samples
             << ",\"minimum_aura_type\":" << row.MinimumAuraType
             << ",\"maximum_aura_type\":" << row.MaximumAuraType
             << ",\"minimum_amount\":" << row.MinimumAmount
             << ",\"maximum_amount\":" << row.MaximumAmount
             << ",\"first_active_stats\":";
        AppendCalibrationEffectiveStatsJson(json, row.FirstActivePlayerStats);
        json << '}';
    }
    json << "]}";
}
