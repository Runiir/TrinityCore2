#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotCalibrationFixtureContractGenerated.h"

#include <algorithm>
#include <set>
#include <sstream>
#include <vector>

void BotWorldPopulationMgr::AppendCalibrationReferenceConditionJson(
    std::ostringstream& json, WorldBotState const& state,
    CalibrationMetrics const* metrics,
    BotCalibrationFixtureContractGenerated::SpecContract const* fixtureSpecContract) const
{
    json << ",\"reference_condition_observation\":{\"schema\":\"phase8_reference_condition_observation_v1\""
                 << ",\"fixture_contract_sha256\":\""
                 << BotCalibrationFixtureContractGenerated::ContentSha256
                 << "\",\"player_guid\":" << state.Guid.GetCounter()
                 << ",\"fixture_target_guid\":"
                 << Cohort().CalibrationFixtureTargetGuid.GetCounter()
                 << ",\"window_started_at_ms\":"
                 << (metrics ? metrics->WindowStartedMs : 0)
                 << ",\"window_ended_at_ms\":"
                 << (metrics ? metrics->WindowEndedMs : 0)
                 << ",\"first_sample_at_ms\":"
                 << (metrics ? metrics->FirstReferenceConditionObservedAtMs : 0)
                 << ",\"last_sample_at_ms\":"
                 << (metrics ? metrics->LastReferenceConditionObservedAtMs : 0)
                 << ",\"maximum_sample_gap_ms\":"
                 << (metrics ? metrics->MaximumReferenceConditionObservationGapMs : 0)
                 << ",\"sample_count\":"
                 << (metrics ? metrics->ReferenceConditionSampleCount : 0)
                 << ",\"configured\":{\"flask_item_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->FlaskItemId : 0)
                 << ",\"flask_aura_spell_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->FlaskAuraSpellId : 0)
                 << ",\"food_item_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->FoodItemId : 0)
                 << ",\"food_aura_spell_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->FoodAuraSpellId : 0)
                 << ",\"required_setup_aura_spell_ids\":[";
            std::vector<uint32> configuredSetupAuraSpellIds;
            if (fixtureSpecContract
                && fixtureSpecContract->SetupAuraOffset
                        + fixtureSpecContract->SetupAuraCount
                    <= BotCalibrationFixtureContractGenerated::RequiredSetupAuraSpellIds.size())
                for (uint32 index = 0;
                    index < fixtureSpecContract->SetupAuraCount; ++index)
                    configuredSetupAuraSpellIds.push_back(
                        BotCalibrationFixtureContractGenerated::RequiredSetupAuraSpellIds[
                            fixtureSpecContract->SetupAuraOffset + index]);
            std::sort(configuredSetupAuraSpellIds.begin(),
                configuredSetupAuraSpellIds.end());
            for (size_t index = 0;
                index < configuredSetupAuraSpellIds.size(); ++index)
            {
                if (index)
                    json << ',';
                json << configuredSetupAuraSpellIds[index];
            }
            json << "]},\"player_auras\":[";
            std::set<uint32> observedPlayerAuraSpellIds;
            if (metrics)
            {
                for (auto const& [spellId, _] :
                    metrics->ReferencePlayerAuraActiveSamples)
                    observedPlayerAuraSpellIds.insert(spellId);
                for (auto const& [spellId, _] :
                    metrics->ReferencePlayerAuraInactiveSamples)
                    observedPlayerAuraSpellIds.insert(spellId);
            }
            bool firstReferenceAura = true;
            for (uint32 spellId : observedPlayerAuraSpellIds)
            {
                if (!firstReferenceAura)
                    json << ',';
                firstReferenceAura = false;
                auto sampleCount = [metrics, spellId](auto member)
                {
                    if (!metrics)
                        return uint32(0);
                    auto const& rows = metrics->*member;
                    auto const itr = rows.find(spellId);
                    return itr == rows.end() ? uint32(0) : itr->second;
                };
                json << "{\"spell_id\":" << spellId
                     << ",\"active_samples\":"
                     << sampleCount(&CalibrationMetrics::ReferencePlayerAuraActiveSamples)
                     << ",\"inactive_samples\":"
                     << sampleCount(&CalibrationMetrics::ReferencePlayerAuraInactiveSamples)
                     << '}';
            }
            json << "],\"target_auras\":[";
            std::set<uint32> observedTargetAuraSpellIds;
            if (metrics)
            {
                for (auto const& [spellId, _] :
                    metrics->ReferenceTargetAuraActiveSamples)
                    observedTargetAuraSpellIds.insert(spellId);
                for (auto const& [spellId, _] :
                    metrics->ReferenceTargetAuraInactiveSamples)
                    observedTargetAuraSpellIds.insert(spellId);
            }
            firstReferenceAura = true;
            for (uint32 spellId : observedTargetAuraSpellIds)
            {
                if (!firstReferenceAura)
                    json << ',';
                firstReferenceAura = false;
                auto sampleCount = [metrics, spellId](auto member)
                {
                    if (!metrics)
                        return uint32(0);
                    auto const& rows = metrics->*member;
                    auto const itr = rows.find(spellId);
                    return itr == rows.end() ? uint32(0) : itr->second;
                };
                uint32 const ownerMatch = sampleCount(
                    &CalibrationMetrics::ReferenceTargetAuraOwnerMatchSamples);
                json << "{\"spell_id\":" << spellId
                     << ",\"caster_guid\":"
                     << (ownerMatch ? state.Guid.GetCounter() : 0)
                     << ",\"active_samples\":"
                     << sampleCount(&CalibrationMetrics::ReferenceTargetAuraActiveSamples)
                     << ",\"inactive_samples\":"
                     << sampleCount(&CalibrationMetrics::ReferenceTargetAuraInactiveSamples)
                     << ",\"owner_match_samples\":" << ownerMatch
                     << ",\"owner_mismatch_samples\":"
                     << sampleCount(&CalibrationMetrics::ReferenceTargetAuraOwnerMismatchSamples)
                     << '}';
            }
            json << "],\"target_stacked_auras\":[{\"spell_id\":58567"
                 << ",\"caster_guid\":"
                 << (metrics && metrics->ReferenceSunderMatchingStackSamples
                        ? state.Guid.GetCounter() : 0)
                 << ",\"required_stacks\":3,\"matching_samples\":"
                 << (metrics ? metrics->ReferenceSunderMatchingStackSamples : 0)
                 << ",\"mismatch_samples\":"
                 << (metrics ? metrics->ReferenceSunderMismatchStackSamples : 0)
                 << ",\"owner_match_samples\":";
            auto referenceTargetCount = [metrics](auto member,
                uint32 spellId)
            {
                if (!metrics)
                    return uint32(0);
                auto const& rows = metrics->*member;
                auto const itr = rows.find(spellId);
                return itr == rows.end() ? uint32(0) : itr->second;
            };
            json << referenceTargetCount(
                        &CalibrationMetrics::ReferenceTargetAuraOwnerMatchSamples,
                        58567)
                 << ",\"owner_mismatch_samples\":"
                 << referenceTargetCount(
                        &CalibrationMetrics::ReferenceTargetAuraOwnerMismatchSamples,
                        58567)
                 << ",\"minimum_observed_stacks\":"
                 << (metrics && metrics->ReferenceConditionSampleCount
                        ? uint32(metrics->ReferenceSunderMinimumObservedStacks) : 0)
                 << ",\"maximum_observed_stacks\":"
                 << (metrics ? uint32(metrics->ReferenceSunderMaximumObservedStacks) : 0)
                 << "}],\"external_bleed_aura_spell_ids\":[16511,33876,46857]"
                 << ",\"unexpected_external_bleed_active_samples\":"
                 << (metrics ? metrics->UnexpectedExternalBleedActiveSamples : 0)
                 << ",\"dynamic_disabled\":{\"prepot_item_id\":0,\"prepot_use_count\":"
                 << (metrics && metrics->PreScoreLastPotionItemId ? 1 : 0)
                 << ",\"combat_potion_item_id\":0,\"combat_potion_use_count\":"
                 << (metrics ? metrics->ScoredPotionUseCount : 0)
                 << ",\"tinker_item_id\":0,\"tinker_spell_id\":0,\"tinker_use_count\":"
                 << (metrics ? metrics->ScoredTinkerOrOtherItemUseCount
                        + metrics->ScoredTinkerSpellUseCount : 0)
                 << ",\"racial_spell_id\":0,\"racial_use_count\":"
                 << (metrics ? metrics->ScoredRacialUseCount : 0)
                 << ",\"last_potion_id_nonzero_samples\":"
                 << (metrics ? metrics->LastPotionIdNonzeroSampleCount : 0)
                 << ",\"unexpected_dynamic_aura_active_samples\":"
                 << (metrics ? metrics->UnexpectedDynamicAuraActiveSamples : 0)
                 << "}}"
}

