#include "Bots/BotWorldPopulationMgr.h"

#include <sstream>

void BotWorldPopulationMgr::AppendRaidPrepullConsumablesJson(
    std::ostringstream& json) const
{
    RaidRuntime const& raid = Cohort().Raid;
    auto writeReceipt = [this, &json](RaidPrepullConsumableReceipt const& receipt)
    {
        json << "{\"item_id\":" << receipt.ItemId
             << ",\"spell_id\":" << receipt.SpellId
             << ",\"aura_spell_id\":" << receipt.AuraSpellId
             << ",\"phase\":\"" << JsonEscape(receipt.Phase) << "\""
             << ",\"required_uses\":" << receipt.RequiredUses
             << ",\"submission_count\":" << receipt.SubmissionCount
             << ",\"successful_use_count\":" << receipt.SuccessfulUseCount
             << ",\"pre_use_item_count\":" << receipt.PreUseItemCount
             << ",\"post_use_item_count\":" << receipt.PostUseItemCount
             << ",\"submitted_at_ms\":" << receipt.SubmittedAtMs
             << ",\"finished_at_ms\":" << receipt.FinishedAtMs
             << ",\"next_retry_at_ms\":" << receipt.NextRetryAtMs
             << ",\"aura_deadline_at_ms\":" << receipt.AuraDeadlineAtMs
             << ",\"aura_observed_at_ms\":" << receipt.AuraObservedAtMs
             << ",\"aura_timed_out_at_ms\":" << receipt.AuraTimedOutAtMs
             << ",\"cooldown_observed_at_ms\":"
             << receipt.CooldownObservedAtMs
             << ",\"cooldown_remaining_ms\":"
             << receipt.CooldownRemainingMs
             << ",\"global_cooldown_remaining_ms\":"
             << receipt.GlobalCooldownRemainingMs
             << ",\"submitted_item_guid\":"
             << receipt.SubmittedItemGuid.GetRawValue()
             << ",\"finished_item_guid\":"
             << receipt.FinishedItemGuid.GetRawValue()
             << ",\"native_use_finished_successfully\":"
             << (receipt.NativeUseFinishedSuccessfully ? "true" : "false")
             << ",\"native_use_awaiting_aura\":"
             << (receipt.NativeUseAwaitingAura ? "true" : "false")
             << ",\"cooldown_observed\":"
             << (receipt.CooldownObserved ? "true" : "false")
             << ",\"failure_reason\":\""
             << JsonEscape(receipt.FailureReason) << "\"}";
    };

    bool allReserved = raid.PrepullConsumablesRequired
        && !raid.PrepullConsumablesByGuid.empty();
    for (auto const& [guid, member] : raid.PrepullConsumablesByGuid)
        if (member.CombatPotionReservedCount < 1)
            allReserved = false;

    json << ",\"prepull_consumables\":{\"schema\":\"raid_prepull_consumables_v1\""
         << ",\"required\":"
         << (raid.PrepullConsumablesRequired ? "true" : "false")
         << ",\"ready\":"
         << (raid.PrepullConsumablesReady ? "true" : "false")
         << ",\"failed\":"
         << (raid.PrepullConsumablesFailed ? "true" : "false")
         << ",\"second_potion_reserved\":"
         << (allReserved ? "true" : "false")
         << ",\"attempt_id\":" << raid.PrepullConsumablesAttemptId
         << ",\"wipe_generation\":"
         << raid.PrepullConsumablesWipeGeneration
         << ",\"route_generation\":"
         << raid.PrepullConsumablesRouteGeneration
         << ",\"ready_at_ms\":" << raid.PrepullConsumablesReadyAtMs
         << ",\"failure_reason\":\""
         << JsonEscape(raid.PrepullConsumablesFailureReason)
         << "\",\"members\":[";
    bool first = true;
    for (auto const& [guid, member] : raid.PrepullConsumablesByGuid)
    {
        if (!first)
            json << ',';
        first = false;
        json << "{\"guid\":" << guid
             << ",\"roster_slot_id\":\"" << JsonEscape(member.RosterSlotId)
             << "\",\"role\":\"" << JsonEscape(member.Role)
             << "\",\"class_spec\":\"" << JsonEscape(member.ClassSpec)
             << "\",\"attempt_id\":" << member.AttemptId
             << ",\"wipe_generation\":" << member.WipeGeneration
             << ",\"route_generation\":" << member.RouteGeneration
             << ",\"alive_and_healed\":"
             << (member.AliveAndHealed ? "true" : "false")
             << ",\"failed\":" << (member.Failed ? "true" : "false")
             << ",\"failure_reason\":\""
             << JsonEscape(member.FailureReason)
             << "\",\"setup_ready_at_ms\":" << member.SetupReadyAtMs
             << ",\"prepot_eligible_at_ms\":"
             << member.PrepotEligibleAtMs
             << ",\"combat_potion_reserved_count\":"
             << member.CombatPotionReservedCount
             << ",\"flask\":";
        writeReceipt(member.Flask);
        json << ",\"food\":";
        writeReceipt(member.Food);
        json << ",\"prepot\":";
        writeReceipt(member.Prepot);
        json << '}';
    }
    json << "]}";
}
