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
                 << "\",\"reference_class\":\""
                 << (IsSelfProvidedCalibrationBaseline()
                        ? "self_provided_baseline" : "controlled_live_parity")
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
                 << ",\"flask_item_spell_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->FlaskItemSpellId : 0)
                 << ",\"flask_aura_spell_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->FlaskAuraSpellId : 0)
                 << ",\"food_item_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->FoodItemId : 0)
                 << ",\"food_item_spell_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->FoodItemSpellId : 0)
                 << ",\"food_aura_spell_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->FoodAuraSpellId : 0)
                 << ",\"prepot_item_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->PrepotItemId : 0)
                 << ",\"prepot_item_spell_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->PrepotItemSpellId : 0)
                 << ",\"prepot_aura_spell_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->PrepotAuraSpellId : 0)
                 << ",\"combat_potion_item_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->CombatPotionItemId : 0)
                 << ",\"combat_potion_item_spell_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->CombatPotionItemSpellId : 0)
                 << ",\"combat_potion_aura_spell_id\":"
                 << (fixtureSpecContract ? fixtureSpecContract->CombatPotionAuraSpellId : 0)
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
                 << ",\"dynamic_disabled\":{\"prepot_item_id\":"
                 << (IsSelfProvidedCalibrationBaseline() && fixtureSpecContract
                        ? fixtureSpecContract->PrepotItemId : 0)
                 << ",\"prepot_use_count\":"
                 << (IsSelfProvidedCalibrationBaseline() && metrics
                        ? metrics->PrepotConsumable.SuccessfulUseCount : 0)
                 << ",\"combat_potion_item_id\":"
                 << (IsSelfProvidedCalibrationBaseline() && fixtureSpecContract
                        ? fixtureSpecContract->CombatPotionItemId : 0)
                 << ",\"combat_potion_use_count\":"
                 << (metrics ? metrics->ScoredPotionUseCount : 0)
                 << ",\"tinker_item_id\":0,\"tinker_spell_id\":0,\"tinker_use_count\":"
                 << (metrics ? metrics->ScoredTinkerOrOtherItemUseCount
                        + metrics->ScoredTinkerSpellUseCount : 0)
                 << ",\"other_item_use_count\":"
                 << (metrics ? metrics->ScoredOtherItemUseCount : 0)
                 << ",\"other_item_uses\":[";
            bool firstOtherItemUse = true;
            if (metrics)
                for (CalibrationMetrics::ScoredOtherItemUse const& otherUse :
                    metrics->ScoredOtherItemUses)
                {
                    if (!otherUse.SpellId && !otherUse.ItemEntry)
                        continue;
                    if (!firstOtherItemUse)
                        json << ',';
                    firstOtherItemUse = false;
                    json << "{\"spell_id\":" << otherUse.SpellId
                         << ",\"item_entry\":" << otherUse.ItemEntry
                         << ",\"count\":" << otherUse.UseCount << '}';
                }
            json << "],\"racial_spell_id\":0,\"racial_use_count\":"
                 << (metrics ? metrics->ScoredRacialUseCount : 0)
                 << ",\"last_potion_id_nonzero_samples\":"
                 << (metrics ? metrics->LastPotionIdNonzeroSampleCount : 0)
                 << ",\"unexpected_dynamic_aura_active_samples\":"
                 << (metrics ? metrics->UnexpectedDynamicAuraActiveSamples : 0)
                 << "},\"native_consumables\":{\"enabled\":"
                 << (IsSelfProvidedCalibrationBaseline() ? "true" : "false")
                 << ",\"receipts\":[";
            auto appendReceipt = [&json](
                CalibrationMetrics::NativeConsumableReceipt const& receipt,
                uint32 itemId, char const* phase, bool first)
            {
                if (!first)
                    json << ',';
                json << "{\"phase\":\"" << phase
                     << "\",\"item_id\":" << itemId
                     << ",\"spell_id\":" << receipt.SpellId
                     << ",\"required_uses\":" << receipt.RequiredUses
                     << ",\"submission_count\":" << receipt.SubmissionCount
                     << ",\"successful_use_count\":" << receipt.SuccessfulUseCount
                     << ",\"pre_use_item_count\":" << receipt.PreUseItemCount
                     << ",\"post_use_item_count\":" << receipt.PostUseItemCount
                     << ",\"submitted_at_ms\":" << receipt.SubmittedAtMs
                     << ",\"finished_at_ms\":" << receipt.FinishedAtMs
                     << ",\"native_use_finished_successfully\":"
                     << (receipt.NativeUseFinishedSuccessfully ? "true" : "false")
                     << ",\"timing_gate_passed\":"
                     << (receipt.TimingGatePassed ? "true" : "false")
                     << ",\"timing_gate_prepot_aura_clear_at_submission\":"
                     << (receipt.TimingGatePrepotAuraClearAtSubmission
                             ? "true" : "false")
                     << ",\"timing_gate_blocked_sample_count\":"
                     << receipt.TimingGateBlockedSampleCount
                     << ",\"timing_gate_prepot_aura_blocked_sample_count\":"
                     << receipt.TimingGatePrepotAuraBlockedSampleCount
                     << ",\"timing_gate_first_eligible_at_ms\":"
                     << receipt.TimingGateFirstEligibleAtMs
                     << ",\"timing_gate_last_blocked_at_ms\":"
                     << receipt.TimingGateLastBlockedAtMs
                     << ",\"timing_gate_last_prepot_aura_blocked_at_ms\":"
                     << receipt.TimingGateLastPrepotAuraBlockedAtMs
                     << ",\"timing_gate_target_health_pct_at_submission\":"
                     << receipt.TimingGateTargetHealthPctAtSubmission
                     << ",\"timing_gate_remaining_ms_at_submission\":"
                     << receipt.TimingGateRemainingMsAtSubmission
                     << ",\"submitted_item_guid\":"
                     << receipt.SubmittedItemGuid.GetCounter()
                     << ",\"finished_item_guid\":"
                     << receipt.FinishedItemGuid.GetCounter() << '}';
            };
            CalibrationMetrics const emptyMetrics;
            CalibrationMetrics const& receiptMetrics = metrics ? *metrics : emptyMetrics;
            appendReceipt(receiptMetrics.FlaskConsumable,
                fixtureSpecContract ? fixtureSpecContract->FlaskItemId : 0,
                "flask_before_scoring", true);
            appendReceipt(receiptMetrics.FoodConsumable,
                fixtureSpecContract ? fixtureSpecContract->FoodItemId : 0,
                "food_before_scoring", false);
            appendReceipt(receiptMetrics.PrepotConsumable,
                fixtureSpecContract ? fixtureSpecContract->PrepotItemId : 0,
                "prepot_before_combat", false);
            appendReceipt(receiptMetrics.CombatPotionConsumable,
                fixtureSpecContract ? fixtureSpecContract->CombatPotionItemId : 0,
                "combat_potion_during_combat", false);
            json << "]},\"unexpected_player_aura_active_samples\":"
                 << (metrics ? metrics->UnexpectedSelfProvidedPlayerAuraActiveSamples : 0)
                 << ",\"unexpected_target_aura_active_samples\":"
                 << (metrics ? metrics->UnexpectedSelfProvidedTargetAuraActiveSamples : 0)
                 << "}";
}

void BotWorldPopulationMgr::AppendCalibrationConsumableExecutionJson(
    std::ostringstream& json, CalibrationMetrics const* metrics,
    BotCalibrationFixtureContractGenerated::SpecContract const* fixtureSpecContract) const
{
    CalibrationMetrics const emptyMetrics;
    CalibrationMetrics const& observed = metrics ? *metrics : emptyMetrics;
    auto auraObserved = [&observed](uint32 spellId)
    {
        auto itr = observed.ReferencePlayerAuraActiveSamples.find(spellId);
        return itr != observed.ReferencePlayerAuraActiveSamples.end()
            && itr->second > 0;
    };
    json << ",\"consumable_execution_observation\":{\"schema\":\"phase8_native_consumable_execution_v1\""
         << ",\"inventory_backed\":true"
         << ",\"static_aura_is_use_receipt\":false"
         << ",\"enabled\":" << (IsSelfProvidedCalibrationBaseline() ? "true" : "false")
         << ",\"flask\":{\"item_id\":"
         << (fixtureSpecContract ? fixtureSpecContract->FlaskItemId : 0)
         << ",\"native_use_count\":" << observed.FlaskConsumable.SuccessfulUseCount
         << ",\"native_use_finished_successfully\":"
         << (observed.FlaskConsumable.NativeUseFinishedSuccessfully ? "true" : "false")
         << ",\"inventory_count_before\":" << observed.FlaskConsumable.PreUseItemCount
         << ",\"inventory_count_after\":" << observed.FlaskConsumable.PostUseItemCount
         << ",\"expected_aura_observed\":"
         << (auraObserved(fixtureSpecContract ? fixtureSpecContract->FlaskAuraSpellId : 0) ? "true" : "false")
         << ",\"submitted_at_ms\":" << observed.FlaskConsumable.SubmittedAtMs
         << ",\"finished_at_ms\":" << observed.FlaskConsumable.FinishedAtMs << '}'
         << ",\"food\":{\"item_id\":"
         << (fixtureSpecContract ? fixtureSpecContract->FoodItemId : 0)
         << ",\"native_use_count\":" << observed.FoodConsumable.SuccessfulUseCount
         << ",\"native_use_finished_successfully\":"
         << (observed.FoodConsumable.NativeUseFinishedSuccessfully ? "true" : "false")
         << ",\"inventory_count_before\":" << observed.FoodConsumable.PreUseItemCount
         << ",\"inventory_count_after\":" << observed.FoodConsumable.PostUseItemCount
         << ",\"expected_aura_observed\":"
         << (auraObserved(fixtureSpecContract ? fixtureSpecContract->FoodAuraSpellId : 0) ? "true" : "false")
         << ",\"submitted_at_ms\":" << observed.FoodConsumable.SubmittedAtMs
         << ",\"finished_at_ms\":" << observed.FoodConsumable.FinishedAtMs << '}'
         << ",\"prepot\":{\"item_id\":"
         << (fixtureSpecContract ? fixtureSpecContract->PrepotItemId : 0)
         << ",\"native_use_count\":" << observed.PrepotConsumable.SuccessfulUseCount
         << ",\"native_use_finished_successfully\":"
         << (observed.PrepotConsumable.NativeUseFinishedSuccessfully ? "true" : "false")
         << ",\"inventory_count_before\":" << observed.PrepotConsumable.PreUseItemCount
         << ",\"inventory_count_after\":" << observed.PrepotConsumable.PostUseItemCount
         << ",\"expected_aura_observed\":"
         << (auraObserved(fixtureSpecContract ? fixtureSpecContract->PrepotAuraSpellId : 0) ? "true" : "false")
         << ",\"submitted_at_ms\":" << observed.PrepotConsumable.SubmittedAtMs
         << ",\"finished_at_ms\":" << observed.PrepotConsumable.FinishedAtMs << '}'
         << ",\"combat_potion\":{\"item_id\":"
         << (fixtureSpecContract ? fixtureSpecContract->CombatPotionItemId : 0)
         << ",\"native_use_count\":" << observed.CombatPotionConsumable.SuccessfulUseCount
         << ",\"native_use_finished_successfully\":"
         << (observed.CombatPotionConsumable.NativeUseFinishedSuccessfully ? "true" : "false")
         << ",\"inventory_count_before\":" << observed.CombatPotionConsumable.PreUseItemCount
         << ",\"inventory_count_after\":" << observed.CombatPotionConsumable.PostUseItemCount
         << ",\"expected_aura_observed\":"
         << (auraObserved(fixtureSpecContract ? fixtureSpecContract->CombatPotionAuraSpellId : 0) ? "true" : "false")
         << ",\"submitted_at_ms\":" << observed.CombatPotionConsumable.SubmittedAtMs
         << ",\"finished_at_ms\":" << observed.CombatPotionConsumable.FinishedAtMs
         << ",\"timing_gate\":{\"policy\":\""
         << (Cohort().CalibrationTargetSpec == "affliction_warlock"
                 ? "execute_e25_or_remaining_le_26s_no_prepot_overlap"
                 : "not_required")
         << "\",\"required_execute_health_pct\":"
         << (Cohort().CalibrationTargetSpec == "affliction_warlock" ? 25 : 0)
         << ",\"required_remaining_ms\":"
         << (Cohort().CalibrationTargetSpec == "affliction_warlock" ? 26000 : 0)
         << ",\"scoring_started_at_ms\":"
         << Cohort().CalibrationScoredStartedMs
         << ",\"gate_passed\":"
         << (observed.CombatPotionConsumable.TimingGatePassed ? "true" : "false")
         << ",\"prepot_aura_active_at_submission\":"
         << (Cohort().CalibrationTargetSpec == "affliction_warlock"
                 && !observed.CombatPotionConsumable.TimingGatePrepotAuraClearAtSubmission
                 ? "true" : "false")
         << ",\"blocked_sample_count\":"
         << observed.CombatPotionConsumable.TimingGateBlockedSampleCount
         << ",\"prepot_aura_blocked_sample_count\":"
         << observed.CombatPotionConsumable.TimingGatePrepotAuraBlockedSampleCount
         << ",\"first_eligible_at_ms\":"
         << observed.CombatPotionConsumable.TimingGateFirstEligibleAtMs
         << ",\"last_blocked_at_ms\":"
         << observed.CombatPotionConsumable.TimingGateLastBlockedAtMs
         << ",\"last_prepot_aura_blocked_at_ms\":"
         << observed.CombatPotionConsumable.TimingGateLastPrepotAuraBlockedAtMs
         << ",\"target_health_pct_at_submission\":"
         << observed.CombatPotionConsumable.TimingGateTargetHealthPctAtSubmission
         << ",\"remaining_ms_at_submission\":"
         << observed.CombatPotionConsumable.TimingGateRemainingMsAtSubmission
         << "}"
         << '}'
         << '}';
}
