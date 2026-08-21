#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotProgressionGoalPolicy.h"
#include "Bots/BotRoleSaturationPolicy.h"
#include "BotDatasetEvent.h"
#include "Config.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "Bag.h"
#include "GameTime.h"
#include "Item.h"
#include "Log.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

std::string BoundedResultLabel(char const* result)
{
    std::string label = result && *result ? result : "ok";
    if (label.size() <= 63)
        return label;
    return label.substr(0, 63);
}

std::string BoundedResultLabel(std::string const& result)
{
    return BoundedResultLabel(result.c_str());
}

uint32 CountInventoryItem(Player* player, uint32 itemId)
{
    if (!player || !itemId)
        return 0;
    uint32 count = 0;
    auto add = [&count, itemId](Item* item)
    {
        if (item && item->GetEntry() == itemId)
            count += item->GetCount();
    };
    for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
        add(player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot));
    for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
        if (Bag* bag = player->GetBagByPos(bagSlot))
            for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
                add(bag->GetItemByPos(slot));
    return count;
}

uint32 SemanticMechanicKey(char const* eventType, char const* result)
{
    std::string event = eventType ? eventType : "";
    std::string res = BoundedResultLabel(result);
    if (event == "interrupt_success" || event == "interrupt_failed")
        return 2;
    if (event == "boss_mechanic" || res == "move_out")
        return 1;
    if (event == "boss_adds" || event == "boss_add_killed")
        return 5;
    if (event == "boss_heal")
        return 4;
    if (event == "boss_action" || event == "boss_started")
        return 11;
    if (event == "trash_action" || event == "trash_heal")
        return 10;
    if (event == "death")
        return 99;
    return 0;
}

char const* SemanticMechanicFamily(uint32 key)
{
    switch (key)
    {
        case 1: return "ground_danger";
        case 2: return "must_interrupt";
        case 4: return "raid_damage";
        case 5: return "adds";
        case 10: return "trash_pack";
        case 11: return "boss_pressure";
        case 99: return "death_failure";
        default: return "unknown";
    }
}

bool EventLooksSuccessful(char const* eventType, char const* result)
{
    std::string event = eventType ? eventType : "";
    std::string res = BoundedResultLabel(result);
    return res == "ok"
        || event == "mob_killed"
        || event == "boss_killed"
        || event == "quest_completed"
        || event == "objective_progress"
        || event == "gear_upgrade"
        || event == "gear_evaluated"
        || event == "interrupt_success";
}

bool EventLooksFailure(char const* eventType, char const* result)
{
    std::string event = eventType ? eventType : "";
    std::string res = BoundedResultLabel(result);
    return event == "death"
        || event == "repeated_death"
        || event == "stuck_detected"
        || event == "objective_failed"
        || event == "death_recovery_failed"
        || event == "interrupt_failed"
        || event == "teleport_fallback_used"
        || res == "failed"
        || res.find("failed") != std::string::npos
        || res.find("blocked") != std::string::npos;
}

}

void BotWorldPopulationMgr::NotifyBotSpellFinished(Player* caster, uint32 spellId, bool success)
{
    if (!caster || !spellId)
        return;

    if (success && Cohort().CalibrationActive
        && Cohort().CalibrationScoredStartedMs
        && !Cohort().CalibrationWindowComplete)
        if (auto metricsItr = Cohort().CalibrationMetricsByGuid.find(
                caster->GetGUID().GetCounter());
            metricsItr != Cohort().CalibrationMetricsByGuid.end())
        {
            static constexpr std::array<uint32, 7> DisabledRacialSpells = {
                20572, 26297, 28730, 33697, 33702, 58984, 69041,
            };
            if (std::find(DisabledRacialSpells.begin(),
                    DisabledRacialSpells.end(), spellId)
                != DisabledRacialSpells.end())
                ++metricsItr->second.ScoredRacialUseCount;
            if (spellId == 82174)
                ++metricsItr->second.ScoredTinkerSpellUseCount;
        }

    // Spell::finish is the native completion authority for the ordinary pet
    // summon submitted by TryEnsurePersistentCombatSetup. Bind it to the exact
    // pending spell/bot receipt; a later update still has to observe the
    // complete live permanent-pet identity before setup is ready.
    bool petSetupReceiptRecorded = false;
    auto recordPetSetupFinish = [&](std::vector<WorldBotState>& states)
    {
        if (petSetupReceiptRecorded)
            return;
        for (WorldBotState& state : states)
        {
            WorldBotState::NativePersistentPetSetupReceipt& petSetup =
                state.PersistentPetSetup;
            if (state.Guid != caster->GetGUID()
                || petSetup.RequiredSummonSpellId != spellId
                || !petSetup.NativeCastSubmittedAtMs)
                continue;
            petSetup.NativeCastFinishedAtMs = NowMs();
            petSetup.NativeCastFinishedSuccessfully = success;
            petSetup.NativeCastObservedAtMs = 0;
            petSetupReceiptRecorded = true;
            break;
        }
    };
    recordPetSetupFinish(Party().CalibrationBots);
    recordPetSetupFinish(Party().Bots);

    auto found = Party().PendingHealCasts.end();
    for (auto itr = Party().PendingHealCasts.begin(); itr != Party().PendingHealCasts.end(); ++itr)
        if (itr->second.BotGuid == caster->GetGUID() && itr->second.SpellId == spellId && (found == Party().PendingHealCasts.end() || itr->second.StartedAtMs > found->second.StartedAtMs))
            found = itr;
    if (found == Party().PendingHealCasts.end())
        return;
    if (!success)
    {
        PendingHealCast cast = found->second;
        Party().PendingHealCasts.erase(found);
        FlushPendingHealCast(cast, caster, "interrupted", "spell_finish_failed");
        return;
    }
    found->second.SpellFinished = true;
    found->second.FinishedAtMs = NowMs();
    found->second.ManaAfterCast = caster->GetPower(POWER_MANA);
    found->second.AttackersAfterCast = uint32(caster->GetThreatManager().GetThreatenedByMeList().size());
    for (auto const& [guid, ref] : caster->GetThreatManager().GetThreatenedByMeList())
        if (ref)
            found->second.ThreatAfterCast += ref->GetThreat();
    found->second.DeadlineMs = found->second.FinishedAtMs + 2500; // collection only; outcome snapshots are fixed above
}

void BotWorldPopulationMgr::NotifyBotItemSpellFinished(Player* caster,
    uint32 spellId, bool success, ObjectGuid castItemGuid,
    ObjectGuid itemTargetGuid, uint32 castItemEntry,
    bool castItemIsPotion)
{
    if (!caster || !spellId || !castItemGuid)
        return;

    bool expectedSelfConsumableReceipt = false;
    if (IsSelfProvidedCalibrationBaseline() && Cohort().CalibrationActive)
        if (auto metricsItr = Cohort().CalibrationMetricsByGuid.find(
                caster->GetGUID().GetCounter());
            metricsItr != Cohort().CalibrationMetricsByGuid.end())
        {
            CalibrationMetrics& metrics = metricsItr->second;
            std::array<CalibrationMetrics::NativeConsumableReceipt*, 4> receipts = {{
                &metrics.FlaskConsumable, &metrics.FoodConsumable,
                &metrics.PrepotConsumable, &metrics.CombatPotionConsumable,
            }};
            for (CalibrationMetrics::NativeConsumableReceipt* receipt : receipts)
                if (receipt
                    && receipt->SubmittedAtMs > receipt->FinishedAtMs
                    && receipt->SubmittedItemGuid == castItemGuid
                    && receipt->SpellId == spellId
                    && receipt->ItemId == castItemEntry)
                {
                    expectedSelfConsumableReceipt = true;
                    receipt->FinishedAtMs = NowMs();
                    receipt->FinishedItemGuid = castItemGuid;
                    receipt->PostUseItemCount = CountInventoryItem(caster,
                        receipt->ItemId);
                    receipt->NativeUseFinishedSuccessfully = success;
                    receipt->NextRetryAtMs = receipt->FinishedAtMs + 1000;
                    if (success)
                        ++receipt->SuccessfulUseCount;
                    if (success && receipt == &metrics.CombatPotionConsumable
                        && Cohort().CalibrationScoredStartedMs
                        && !Cohort().CalibrationWindowComplete)
                        ++metrics.ScoredPotionUseCount;
                    break;
                }
        }

    // A completed native item spell is the only accepted dynamic-item-use
    // receipt.  Self-provided mode counts only its expected combat potion as a
    // permitted scored potion; all other native item completions remain
    // visible as unexpected dynamic actions.
    if (success && !expectedSelfConsumableReceipt && Cohort().CalibrationActive
        && Cohort().CalibrationScoredStartedMs
        && !Cohort().CalibrationWindowComplete)
        if (auto metricsItr = Cohort().CalibrationMetricsByGuid.find(
                caster->GetGUID().GetCounter());
            metricsItr != Cohort().CalibrationMetricsByGuid.end())
        {
            CalibrationMetrics& metrics = metricsItr->second;
            if (castItemIsPotion)
                ++metrics.ScoredPotionUseCount;
            else if (castItemEntry != 43231 && castItemEntry != 43233)
            {
                ++metrics.ScoredTinkerOrOtherItemUseCount;
                ++metrics.ScoredOtherItemUseCount;
                CalibrationMetrics::ScoredOtherItemUse* reuseSlot = nullptr;
                for (CalibrationMetrics::ScoredOtherItemUse& use :
                    metrics.ScoredOtherItemUses)
                {
                    if (use.SpellId == spellId && use.ItemEntry == castItemEntry)
                    {
                        reuseSlot = &use;
                        break;
                    }
                    if (!reuseSlot && !use.SpellId && !use.ItemEntry)
                        reuseSlot = &use;
                }
                if (reuseSlot)
                {
                    reuseSlot->SpellId = spellId;
                    reuseSlot->ItemEntry = castItemEntry;
                    ++reuseSlot->UseCount;
                }
            }
        }

    if (!itemTargetGuid)
        return;

    // Item-use submission is not completion. Spell owns the immutable cast
    // item and explicit item-target GUIDs even if ordinary resource
    // consumption removes the source item before finish. Bind both exact
    // identities before a later autonomy tick observes the live enchant.
    bool poisonSetupReceiptRecorded = false;
    auto recordPoisonSetupFinish = [&](std::vector<WorldBotState>& states)
    {
        if (poisonSetupReceiptRecorded)
            return;
        for (WorldBotState& state : states)
        {
            if (state.Guid != caster->GetGUID()
                || !state.RoguePoisonSetupRequired)
                continue;
            std::array<WorldBotState::NativePoisonSetupReceipt*, 2>
                receipts = {{ &state.RogueMainhandPoisonSetup,
                    &state.RogueOffhandPoisonSetup }};
            for (WorldBotState::NativePoisonSetupReceipt* receipt : receipts)
            {
                if (!receipt || receipt->RequiredSpellId != spellId
                    || !receipt->NativeUseSubmittedAtMs
                    || receipt->SubmittedItemGuid != castItemGuid
                    || receipt->SubmittedWeaponGuid != itemTargetGuid
                    || (receipt->NativeUseFinishedAtMs
                        >= receipt->NativeUseSubmittedAtMs))
                    continue;
                receipt->NativeUseFinishedAtMs = NowMs();
                receipt->NativeUseFinishedSuccessfully = success;
                receipt->NativeUseFinishedItemGuid = castItemGuid;
                receipt->NativeUseFinishedWeaponGuid = itemTargetGuid;
                receipt->EnchantObservedAtMs = 0;
                poisonSetupReceiptRecorded = true;
                break;
            }
            if (poisonSetupReceiptRecorded)
                break;
        }
    };
    recordPoisonSetupFinish(Party().CalibrationBots);
    recordPoisonSetupFinish(Party().Bots);
}

void BotWorldPopulationMgr::FlushPendingHealCast(PendingHealCast const& cast, Player* bot, char const* outcome, char const* reason)
{
    if (!bot)
        return;
    uint32 attackersAfter = uint32(bot->GetThreatManager().GetThreatenedByMeList().size());
    float threatAfter = 0.0f;
    for (auto const& [guid, ref] : bot->GetThreatManager().GetThreatenedByMeList())
        if (ref)
            threatAfter += ref->GetThreat();
    uint32 manaAfter = cast.SpellFinished ? cast.ManaAfterCast : bot->GetPower(POWER_MANA);
    if (cast.SpellFinished)
    {
        attackersAfter = cast.AttackersAfterCast;
        threatAfter = cast.ThreatAfterCast;
    }
    std::ostringstream guids;
    bool first = true;
    for (uint64 guid : cast.AffectedAllyGuids)
    {
        if (!first) guids << ',';
        first = false;
        guids << guid;
    }
    std::ostringstream raw;
    raw << "{\"schema\":\"bot_healing_lifecycle_v1\",\"cast_id\":" << cast.CastId
        << ",\"bot_guid\":" << cast.BotGuid.GetCounter() << ",\"spell_id\":" << cast.SpellId
        << ",\"chosen_target_guid\":" << cast.ChosenTargetGuid.GetCounter()
        << ",\"outcome\":\"" << JsonEscape(outcome ? outcome : "unknown") << "\""
        << ",\"reason\":\"" << JsonEscape(reason ? reason : "") << "\""
        << ",\"attempted_heal\":" << cast.AttemptedHeal << ",\"effective_heal\":" << cast.EffectiveHeal
        << ",\"absorbed_heal\":" << cast.AbsorbedHeal
        << ",\"overheal\":" << (cast.AttemptedHeal - std::min(cast.AttemptedHeal, cast.EffectiveHeal))
        << ",\"mana_before\":" << cast.ManaBefore << ",\"mana_after\":" << manaAfter
        << ",\"mana_delta\":" << (int64(manaAfter) - int64(cast.ManaBefore))
        << ",\"affected_ally_count\":" << cast.AffectedAllyGuids.size() << ",\"affected_ally_guids\":[" << guids.str() << ']'
        << ",\"attackers_before\":" << cast.AttackersBefore << ",\"attackers_after\":" << attackersAfter
        << ",\"threat_before\":" << cast.ThreatBefore << ",\"threat_after\":" << threatAfter
        << ",\"candidate_mask\":" << (cast.CandidateMaskJson.empty() ? "{}" : cast.CandidateMaskJson)
        << ",\"chosen_action\":" << (cast.ChosenActionJson.empty() ? "{}" : cast.ChosenActionJson) << '}';
    BotDatasetEvent dataset;
    dataset.run_id = Cohort().RunId;
    dataset.experiment_id = std::to_string(Cohort().ExperimentId);
    dataset.episode_id = Cohort().RunId;
    dataset.bot_guid = bot->GetGUID();
    dataset.bot_role = GetDungeonRole(bot);
    dataset.bot_level = uint32(bot->getLevel());
    dataset.policy_source = BotPolicySource::Rule;
    dataset.policy_version = Cohort().Config.BrainVersion;
    dataset.timestamp_ms = NowMs();
    dataset.tick_id = cast.CastId;
    dataset.domain = "party_healing";
    dataset.situation = "healing_lifecycle";
    dataset.observation_json = raw.str();
    dataset.semantic_json = raw.str();
    dataset.valid_action_mask_json = cast.CandidateMaskJson.empty() ? "{}" : cast.CandidateMaskJson;
    dataset.chosen_action_json = cast.ChosenActionJson.empty() ? "{}" : cast.ChosenActionJson;
    dataset.action_result = outcome ? outcome : "unknown";
    dataset.outcome_json = raw.str();
    dataset.quality_flags_json = "{\"source\":\"heal_info_lifecycle\",\"hot_attribution\":\"bounded_bot_spell_target_window\"}";
    std::string canonical = dataset.Validate() ? dataset.ToJson() : "";
    std::string escapedRaw = raw.str();
    std::string escapedOutcome = outcome ? outcome : "unknown";
    std::string escapedCanonical = canonical;
    CharacterDatabase.EscapeString(escapedRaw);
    CharacterDatabase.EscapeString(escapedOutcome);
    CharacterDatabase.EscapeString(escapedCanonical);
    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events (schema_version, feature_schema_version, experiment_id, run_id, bot_guid, brain_version, map_id, zone_id, area_id, x, y, z, level, event_type, spell_id, result, value_float, value_int, raw_json, semantic_json, canonical_event_json) VALUES ('%s','%s'," UI64FMTD "," UI64FMTD ",%u,'%s',%u,%u,%u,%f,%f,%f,%u,'healing_lifecycle',%u,'%s',%f,%u,'%s','%s','%s')",
        BotDatasetEvent::SchemaVersion, BotDatasetEvent::DefaultFeatureSchemaVersion, Cohort().ExperimentId, Cohort().RunId, bot->GetGUID().GetCounter(), Cohort().Config.BrainVersion.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), cast.SpellId, escapedOutcome.c_str(), float(cast.EffectiveHeal), uint32(cast.AffectedAllyGuids.size()), escapedRaw.c_str(), escapedRaw.c_str(), escapedCanonical.c_str());

    for (WorldBotState& state : Party().Bots)
        if (state.Guid == bot->GetGUID())
        {
            RecordEvent(state, bot, "healing_lifecycle", nullptr, outcome, raw.str().c_str(), raw.str().c_str(), float(cast.EffectiveHeal), uint32(cast.AffectedAllyGuids.size()), cast.SpellId);
            break;
        }
}

void BotWorldPopulationMgr::ClearPendingHealCasts(char const* reason)
{
    for (auto const& [id, cast] : Party().PendingHealCasts)
        if (Player* bot = ObjectAccessor::FindConnectedPlayer(cast.BotGuid))
            FlushPendingHealCast(cast, bot, "cancelled", reason);
    Party().PendingHealCasts.clear();
}

void BotWorldPopulationMgr::UpdatePendingHealCasts()
{
    uint64 now = NowMs();
    for (auto itr = Party().PendingHealCasts.begin(); itr != Party().PendingHealCasts.end();)
    {
        if (now < itr->second.DeadlineMs)
        {
            ++itr;
            continue;
        }
        PendingHealCast cast = itr->second;
        itr = Party().PendingHealCasts.erase(itr);
        if (Player* bot = ObjectAccessor::FindConnectedPlayer(cast.BotGuid))
            FlushPendingHealCast(cast, bot, cast.SpellFinished ? "completed" : "timeout", cast.SpellFinished ? "collection_window_closed" : "cast_deadline_exceeded");
    }
}

void BotWorldPopulationMgr::UpdateSemanticOutcomeStats(Player* bot, char const* entityType, uint32 entityKey, char const* eventType, char const* result, float reward, float powerDelta, bool failure, char const* featuresJson)
{
    if (!Cohort().RunId || !Cohort().Config.UpdateSemanticOutcomeStats || !bot || !entityType || !entityKey)
        return;

    auto clampMetric = [](float value, float low, float high)
    {
        if (!std::isfinite(value))
            return 0.0f;
        return std::max(low, std::min(high, value));
    };
    reward = clampMetric(reward, -25.0f, 25.0f);
    powerDelta = clampMetric(powerDelta, -25.0f, 25.0f);

    bool failed = failure || EventLooksFailure(eventType, result);
    bool death = eventType && std::string(eventType) == "death";
    bool success = !failed && EventLooksSuccessful(eventType, result);

    std::string type = entityType;
    std::string event = eventType ? eventType : "";
    std::string res = BoundedResultLabel(result);
    std::string features = featuresJson ? featuresJson : "{}";
    std::ostringstream embedding;
    embedding << "{\"entity_type\":\"" << JsonEscape(type)
              << "\",\"entity_key\":" << entityKey
              << ",\"feature_schema\":\"bot_semantic_phase6_v1\""
              << ",\"features\":" << features << "}";
    std::string embeddingJson = embedding.str();
    CharacterDatabase.EscapeString(type);
    CharacterDatabase.EscapeString(event);
    CharacterDatabase.EscapeString(res);
    CharacterDatabase.EscapeString(features);
    CharacterDatabase.EscapeString(embeddingJson);

    CharacterDatabase.DirectPExecute(
        "INSERT INTO bot_semantic_outcome_stats "
        "(entity_type, entity_key, samples, successes, failures, deaths, total_reward, total_power_delta, avg_reward, avg_power_delta, danger_score, progression_value, last_experiment_id, last_run_id, last_event_type, last_result, features_json, embedding_json, updated_at) "
        "VALUES ('%s', %u, 1, %u, %u, %u, %f, %f, %f, %f, %f, %f, " UI64FMTD ", " UI64FMTD ", '%s', '%s', '%s', '%s', NOW()) "
        "ON DUPLICATE KEY UPDATE "
        "danger_score = LEAST(1.0, (failures + VALUES(failures) + ((deaths + VALUES(deaths)) * 2.0)) / GREATEST(1, samples + VALUES(samples))), "
        "progression_value = GREATEST(0.0, (total_power_delta + VALUES(total_power_delta)) / GREATEST(1, samples + VALUES(samples))) + GREATEST(0.0, (total_reward + VALUES(total_reward)) / GREATEST(1, samples + VALUES(samples))), "
        "avg_reward = (total_reward + VALUES(total_reward)) / GREATEST(1, samples + VALUES(samples)), "
        "avg_power_delta = (total_power_delta + VALUES(total_power_delta)) / GREATEST(1, samples + VALUES(samples)), "
        "samples = samples + VALUES(samples), successes = successes + VALUES(successes), failures = failures + VALUES(failures), deaths = deaths + VALUES(deaths), "
        "total_reward = total_reward + VALUES(total_reward), total_power_delta = total_power_delta + VALUES(total_power_delta), "
        "last_experiment_id = VALUES(last_experiment_id), last_run_id = VALUES(last_run_id), last_event_type = VALUES(last_event_type), last_result = VALUES(last_result), "
        "features_json = VALUES(features_json), embedding_json = VALUES(embedding_json), updated_at = NOW()",
        type.c_str(), entityKey, success ? 1 : 0, failed ? 1 : 0, death ? 1 : 0, reward, powerDelta, reward, powerDelta,
        failed ? 1.0f : 0.0f, std::max(0.0f, reward) + std::max(0.0f, powerDelta), Cohort().ExperimentId, Cohort().RunId, event.c_str(), res.c_str(), features.c_str(), embeddingJson.c_str());
}

void BotWorldPopulationMgr::UpdateSemanticStatsFromEvent(Player* bot, Unit const* target, char const* eventType, char const* result, float valueFloat, uint32 valueInt, uint32 spellId, char const* /*semanticJson*/)
{
    if (!Cohort().Config.UpdateSemanticOutcomeStats || !bot)
        return;

    bool failed = EventLooksFailure(eventType, result);
    std::string areaFeatures = BuildEmbeddingFeaturesJson(bot, target, "area", bot->GetAreaId(), eventType ? eventType : "event");
    UpdateSemanticOutcomeStats(bot, "area", bot->GetAreaId(), eventType, result, valueFloat, 0.0f, failed, areaFeatures.c_str());

    if (Creature const* creature = target ? target->ToCreature() : nullptr)
    {
        std::string mobFeatures = BuildEmbeddingFeaturesJson(bot, target, "mob", creature->GetEntry(), eventType ? eventType : "event");
        UpdateSemanticOutcomeStats(bot, "mob", creature->GetEntry(), eventType, result, valueFloat, 0.0f, failed, mobFeatures.c_str());
    }

    if (spellId)
    {
        std::string spellFeatures = BuildEmbeddingFeaturesJson(bot, target, "spell", spellId, eventType ? eventType : "spell");
        UpdateSemanticOutcomeStats(bot, "spell", spellId, eventType, result, valueFloat, 0.0f, failed, spellFeatures.c_str());
    }

    uint32 mechanicKey = SemanticMechanicKey(eventType, result);
    if (mechanicKey)
    {
        std::string mechanicFeatures = BuildEmbeddingFeaturesJson(bot, target, "mechanic", mechanicKey, SemanticMechanicFamily(mechanicKey));
        UpdateSemanticOutcomeStats(bot, "mechanic", mechanicKey, eventType, result, valueFloat, 0.0f, failed, mechanicFeatures.c_str());
    }

    if ((eventType && (std::string(eventType) == "gear_upgrade" || std::string(eventType) == "gear_evaluated" || std::string(eventType) == "smart_loot_decision")) && valueInt)
    {
        std::string itemFeatures = BuildEmbeddingFeaturesJson(bot, target, "item", valueInt, eventType);
        UpdateSemanticOutcomeStats(bot, "item", valueInt, eventType, result, valueFloat, valueFloat, failed, itemFeatures.c_str());
    }
}

BotWorldPopulationMgr::SemanticOutcomeStats BotWorldPopulationMgr::GetSemanticOutcomeStats(char const* entityType, uint32 entityKey) const
{
    SemanticOutcomeStats stats;
    if (!sConfigMgr->GetBoolDefault("BotSemantic.Enable", true) || !entityType || !entityKey)
        return stats;

    std::string type = entityType;
    CharacterDatabase.EscapeString(type);
    if (QueryResult result = CharacterDatabase.PQuery("SELECT samples, successes, failures, deaths, avg_reward, avg_power_delta, danger_score, progression_value FROM bot_semantic_outcome_stats WHERE entity_type = '%s' AND entity_key = %u", type.c_str(), entityKey))
    {
        Field* fields = result->Fetch();
        stats.Known = true;
        stats.Samples = fields[0].GetUInt32();
        stats.Successes = fields[1].GetUInt32();
        stats.Failures = fields[2].GetUInt32();
        stats.Deaths = fields[3].GetUInt32();
        stats.AvgReward = fields[4].GetFloat();
        stats.AvgPowerDelta = fields[5].GetFloat();
        stats.DangerScore = fields[6].GetFloat();
        stats.ProgressionValue = fields[7].GetFloat();
    }
    return stats;
}

std::string BotWorldPopulationMgr::BuildOutcomeStatsJson(SemanticOutcomeStats const& stats) const
{
    std::ostringstream json;
    json << "{\"known\":" << (stats.Known ? "true" : "false")
         << ",\"samples\":" << stats.Samples
         << ",\"successes\":" << stats.Successes
         << ",\"failures\":" << stats.Failures
         << ",\"deaths\":" << stats.Deaths
         << ",\"avg_reward\":" << stats.AvgReward
         << ",\"avg_power_delta\":" << stats.AvgPowerDelta
         << ",\"danger_score\":" << stats.DangerScore
         << ",\"progression_value\":" << stats.ProgressionValue << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildEmbeddingFeaturesJson(Player const* bot, Unit const* target, char const* entityType, uint32 entityKey, char const* semanticFamily) const
{
    uint32 targetEntry = 0;
    bool elite = false;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
    {
        targetEntry = creature->GetEntry();
        elite = creature->isElite();
    }

    std::ostringstream json;
    std::string role = bot ? GetDungeonRole(const_cast<Player*>(bot)) : "dps";
    BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, role.c_str());
    RoleSaturationState saturation = BuildRoleSaturationState(bot, target, role.c_str());
    json << "{\"entity_type\":\"" << JsonEscape(entityType ? entityType : "unknown")
         << "\",\"entity_key\":" << entityKey
         << ",\"semantic_family\":\"" << JsonEscape(semanticFamily ? semanticFamily : "unknown") << "\""
         << ",\"map_id\":" << (bot ? bot->GetMapId() : 0)
         << ",\"zone_id\":" << (bot ? bot->GetZoneId() : 0)
         << ",\"area_id\":" << (bot ? bot->GetAreaId() : 0)
         << ",\"bot_level\":" << (bot ? uint32(bot->getLevel()) : 0)
         << ",\"bot_class\":" << (bot ? uint32(bot->getClass()) : 0)
         << ",\"target_entry\":" << targetEntry
         << ",\"target_level\":" << (target ? uint32(target->getLevel()) : 0)
         << ",\"target_elite\":" << (elite ? "true" : "false")
         << ",\"class_spec_profile\":" << profile.EmbeddingJson()
         << ",\"role_goal\":\"" << JsonEscape(BotProgressionGoalPolicy::RoleGoal(role)) << "\""
         << ",\"role_saturation_state_json\":" << saturation.ToJson()
         << ",\"recommended_balance_mode\":\"" << JsonEscape(BotRoleSaturationPolicy::ToString(saturation.RecommendedBalanceMode)) << "\""
         << ",\"saturation_reason\":\"" << JsonEscape(saturation.SaturationReason) << "\""
         << ",\"profession_goal\":" << BotProgressionGoalPolicy::ProfessionGoalJson(bot, role, semanticFamily)
         << ",\"feature_schema\":\"bot_semantic_phase6_v1\"}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildNativeRecoveryEpisodeJson(
    WorldBotState const* state) const
{
    std::ostringstream json;
    json << "{\"attempt_id\":"
         << (state ? state->NativeRecoveryEpisodeAttemptId : 0)
         << ",\"route_generation\":"
         << (state ? state->NativeRecoveryEpisodeRouteGeneration : 0)
         << ",\"wipe_generation\":"
         << (state ? state->NativeRecoveryEpisodeWipeGeneration : 0)
         << ",\"death_ordinal\":"
         << (state ? state->NativeRecoveryEpisodeDeathOrdinal : 0)
         << ",\"phase\":\""
         << JsonEscape(state ? state->NativeRecoveryEpisodePhase : "none")
         << "\",\"started_ms\":"
         << (state ? state->NativeRecoveryEpisodeStartedMs : 0)
         << ",\"last_progress_ms\":"
         << (state ? state->NativeRecoveryEpisodeLastProgressMs : 0)
         << ",\"distance_target\":\""
         << JsonEscape(state ? state->NativeRecoveryEpisodeDistanceTarget
                             : "none")
         << "\",\"best_distance\":";
    if (state && std::isfinite(state->NativeRecoveryEpisodeBestDistance)
        && state->NativeRecoveryEpisodeBestDistance
            < std::numeric_limits<float>::max())
        json << state->NativeRecoveryEpisodeBestDistance;
    else
        json << "null";
    json << ",\"movement_retry_count\":"
         << (state ? state->NativeRecoveryMovementRetryCount : 0)
         << ",\"release_rejection_count\":"
         << (state ? state->NativeRecoveryReleaseRejectionCount : 0)
         << ",\"entrance_unavailable_count\":"
         << (state ? state->NativeRecoveryEntranceUnavailableCount : 0)
         << ",\"entrance_rejection_count\":"
         << (state ? state->NativeRecoveryEntranceRejectionCount : 0)
         << ",\"reclaim_rejection_count\":"
         << (state ? state->NativeRecoveryReclaimRejectionCount : 0)
         << ",\"entrance_required\":"
         << (state && state->NativeRecoveryEntranceRequired ? "true" : "false")
         << ",\"entrance_observed\":"
         << (state && state->NativeRecoveryEntranceObserved ? "true" : "false")
         << ",\"entrance_available\":"
         << (state && state->NativeRecoveryEntranceAvailable ? "true" : "false")
         << "}";
    return json.str();
}
