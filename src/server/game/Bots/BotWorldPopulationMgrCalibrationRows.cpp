#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotWorldPopulationMgrCalibrationIdentity.h"
#include "Bots/BotWorldPopulationMgrCalibrationReportSupport.h"
#include "Creature.h"
#include "DataStores/DBCStores.h"
#include "Entities/Item/Item.h"
#include "Entities/Item/ItemTemplate.h"
#include "Group.h"
#include "Map.h"
#include "Pet.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Totem.h"
#include "TotemAI.h"
#include "Unit.h"
#include <algorithm>
#include <iomanip>
#include <sstream>
using BotWorldPopulationMgrCalibrationReport::CalibrationSpecUsesMana;
using BotWorldPopulationMgrCalibrationReport::RuntimeModeName;
void BotWorldPopulationMgr::AppendCombatCalibrationBotRowsJson(
    std::ostringstream& json,
    std::map<uint32, CalibrationMetrics> const& metricsByGuid,
    uint64 nowMs,
    BotCalibrationFixtureContractGenerated::SpecContract const* fixtureSpecContract,
    bool completedWindow) const
{
    json << '[';
    bool firstBot = true;
    for (WorldBotState const& state : Party().CalibrationBots)
    {
        if (!firstBot)
            json << ',';
        firstBot = false;
        Player* bot = GetLoadedBot(state);
        auto itr = metricsByGuid.find(state.Guid.GetCounter());
        CalibrationMetrics const* metrics = itr == metricsByGuid.end() ? nullptr : &itr->second;
        auto actionAttemptCount = [metrics](uint32 spellId)
        {
            if (!metrics)
                return uint32(0);
            auto const attempt = metrics->ActionAttempts.find(spellId);
            return attempt == metrics->ActionAttempts.end()
                ? uint32(0) : attempt->second;
        };
        uint64 startedMs = metrics && metrics->WindowStartedMs ? metrics->WindowStartedMs : Cohort().CalibrationStartedMs;
        uint64 endedMs = metrics && metrics->WindowEndedMs ? metrics->WindowEndedMs : nowMs;
        double elapsedSec = startedMs && endedMs > startedMs
            ? double(endedMs - startedMs) / 1000.0 : 0.0;
        double dps = metrics && elapsedSec > 0.0 ? double(metrics->Damage) / elapsedSec : 0.0;
        double tps = metrics && metrics->ThreatBaseline >= 0.0f && elapsedSec > 0.0
            ? std::max(0.0, double(metrics->ThreatCurrent - metrics->ThreatBaseline) / elapsedSec) : 0.0;
        uint64 castFailures = 0;
        if (metrics)
            for (auto const& [result, count] : metrics->ResultCounts)
                if (result.rfind("cast_failed", 0) == 0)
                    castFailures += count;
        double castFailureRatio = metrics && metrics->Attempts
            ? double(castFailures) / double(metrics->Attempts) : 0.0;
        double activeUptimeRatio = metrics && metrics->TickCount
            ? double(metrics->ActiveTicks) / double(metrics->TickCount) : 0.0;
        double resourceCappedRatio = metrics && metrics->TickCount
            ? double(metrics->ResourceCappedTicks) / double(metrics->TickCount) : 0.0;
        double resourceStarvedRatio = metrics && metrics->TickCount
            ? double(metrics->ResourceStarvedTicks) / double(metrics->TickCount) : 0.0;
        double shadowOrbPowerUptimeRatio = metrics && metrics->TickCount
            ? double(metrics->ShadowOrbPowerActiveTicks) / double(metrics->TickCount) : 0.0;
        double shadowOrbUptimeRatio = metrics && metrics->TickCount
            ? double(metrics->ShadowOrbActiveTicks) / double(metrics->TickCount) : 0.0;
        double empoweredShadowUptimeRatio = metrics && metrics->TickCount
            ? double(metrics->EmpoweredShadowActiveTicks) / double(metrics->TickCount) : 0.0;
        double movementRangeLossRatio = metrics && metrics->TickCount
            ? double(metrics->MovementRangeLossTicks) / double(metrics->TickCount) : 0.0;
        double petDamageRatio = metrics && metrics->Damage
            ? double(metrics->PetDamage) / double(metrics->Damage) : 0.0;
        double requiredPetUptimeRatio = metrics
                && metrics->PetSetupObservationSampleCount
            ? double(metrics->PetSetupReadySampleCount)
                / double(metrics->PetSetupObservationSampleCount) : 0.0;
        uint32 petExecutionSamples = 0;
        uint32 petAliveSamples = 0;
        uint32 petAttackingSamples = 0;
        uint32 petTargetMatchSamples = 0;
        uint32 petCommandAttackSamples = 0;
        if (metrics)
            for (CalibrationMetrics::DecisionTimelineEntry const& entry
                : metrics->DecisionTimeline)
            {
                ++petExecutionSamples;
                if (entry.PetAlive)
                    ++petAliveSamples;
                if (entry.PetAttacking)
                    ++petAttackingSamples;
                if (entry.PetVictimGuid
                    && entry.PetVictimGuid
                        == Cohort().CalibrationFixtureTargetGuid.GetCounter())
                    ++petTargetMatchSamples;
                if (entry.PetCommandAttack)
                    ++petCommandAttackSamples;
            }
        uint32 observedExpectedGroups = 0;
        if (metrics)
            for (std::string const& group : metrics->ExpectedActionGroups)
                if (metrics->ActionGroups.count(group))
                    ++observedExpectedGroups;
        double rotationGroupCoverage = metrics && !metrics->ExpectedActionGroups.empty()
            ? double(observedExpectedGroups) / double(metrics->ExpectedActionGroups.size()) : 0.0;
        double overhealRatio = metrics && metrics->AttemptedHealing
            ? double(metrics->AttemptedHealing > metrics->EffectiveHealing + metrics->AbsorbedHealing
                ? metrics->AttemptedHealing - metrics->EffectiveHealing - metrics->AbsorbedHealing : 0)
                / double(metrics->AttemptedHealing) : 0.0;
        double targetSelectionAccuracy = metrics && metrics->HealSelectionAttempts
            ? double(metrics->HealSelectionSuccesses) / double(metrics->HealSelectionAttempts) : 0.0;
        double idleUnderDemandRatio = metrics && metrics->DemandTicks
            ? double(metrics->IdleUnderDemandTicks) / double(metrics->DemandTicks) : 0.0;
        uint32 responseLatencyP95 = 0;
        if (metrics && !metrics->HealResponseLatenciesMs.empty())
        {
            std::vector<uint32> latencies = metrics->HealResponseLatenciesMs;
            std::sort(latencies.begin(), latencies.end());
            size_t const p95Index = (latencies.size() * 95 + 99) / 100 - 1;
            responseLatencyP95 = latencies[p95Index];
        }
        uint32 mainhandTempEnchant = 0;
        uint32 offhandTempEnchant = 0;
        uint32 mainhandItemEntry = 0;
        uint32 fireTotemSpell = 0;
        uint32 fireTotemCreatedBySpell = 0;
        uint32 fireTotemEntry = 0;
        bool fireTotemAlive = false;
        bool fireTotemActive = false;
        uint64 fireTotemCastAttempts = 0;
        uint64 fireTotemCastSuccesses = 0;
        uint64 fireTotemUpdateCalls = 0;
        uint32 fireTotemLastCastResult = SPELL_FAILED_DONT_REPORT;
        bool fireTotemUsesTotemAI = false;
        uint32 fireTotemGenericSpell = 0;
        uint32 fireTotemChanneledSpell = 0;
        uint32 fireTotemAutorepeatSpell = 0;
        bool fireTotemTargetValid = false;
        bool fireTotemOwnerTargetValid = false;
        uint64 fireTotemCastingSkips = 0;
        uint64 fireTotemMissingSpellSkips = 0;
        uint64 fireTotemNoTargetSkips = 0;
        BotWorldPopulationMgrCalibrationIdentity::OrdinaryPetSetupSnapshot const ordinaryPet =
            BotWorldPopulationMgrCalibrationIdentity::ObserveOrdinaryPetSetup(bot);
        BotWorldPopulationMgrCalibrationIdentity::HunterPetIdentitySnapshot hunterPetIdentity;
        bool const hunterPetIdentityObserved =
            BotWorldPopulationMgrCalibrationIdentity::ObserveActiveOrdinaryHunterPet(bot, hunterPetIdentity);
        WorldBotState::NativePersistentPetSetupReceipt const& petSetup =
            state.PersistentPetSetup;
        bool const nativePersistentPetReady = bot
            && petSetup.RequiredSummonSpellId
            && petSetup.RequiredCreatedBySpellId
            && petSetup.RequiredEntry
            && petSetup.SummonSpellKnown
            && bot->HasSpell(petSetup.RequiredSummonSpellId)
            && petSetup.NativeCastSubmittedAtMs
            && petSetup.NativeCastFinishedSuccessfully
            && petSetup.NativeCastFinishedAtMs
                >= petSetup.NativeCastSubmittedAtMs
            && petSetup.NativeCastObservedAtMs
                >= petSetup.NativeCastFinishedAtMs
            && BotWorldPopulationMgrCalibrationIdentity::OrdinaryPersistentPetMatches(ordinaryPet,
                petSetup.RequiredEntry, petSetup.RequiredFamilyId,
                petSetup.RequiredPetType, petSetup.RequiredPowerType,
                petSetup.RequiredCreatedBySpellId);
        bool const preexistingAfflictionPetReady = bot
            && Cohort().CalibrationTargetSpec == "affliction_warlock"
            && petSetup.RequiredSummonSpellId == 691
            && petSetup.RequiredCreatedBySpellId == 691
            && petSetup.RequiredEntry == ENTRY_FELHUNTER
            && petSetup.SummonSpellKnown
            && bot->HasSpell(petSetup.RequiredSummonSpellId)
            && !petSetup.NativeCastSubmittedAtMs
            && BotWorldPopulationMgrCalibrationIdentity::OrdinaryPersistentPetMatches(ordinaryPet,
                petSetup.RequiredEntry, petSetup.RequiredFamilyId,
                petSetup.RequiredPetType, petSetup.RequiredPowerType,
                petSetup.RequiredCreatedBySpellId);
        if (bot)
        {
            if (Item* item = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_MAINHAND))
            {
                mainhandItemEntry = item->GetEntry();
                mainhandTempEnchant = item->GetEnchantmentId(TEMP_ENCHANTMENT_SLOT);
            }
            if (Item* item = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, EQUIPMENT_SLOT_OFFHAND))
                offhandTempEnchant = item->GetEnchantmentId(TEMP_ENCHANTMENT_SLOT);
            if (bot->getClass() == CLASS_SHAMAN && bot->m_SummonSlot[SUMMON_SLOT_TOTEM_FIRE] && bot->GetMap())
                if (Creature* creature = bot->GetMap()->GetCreature(bot->m_SummonSlot[SUMMON_SLOT_TOTEM_FIRE]))
                    if (Totem* totem = creature->ToTotem())
                    {
                        fireTotemSpell = totem->GetSpell();
                        fireTotemCreatedBySpell = totem->GetUInt32Value(UNIT_CREATED_BY_SPELL);
                        fireTotemEntry = totem->GetEntry();
                        fireTotemAlive = totem->IsAlive();
                        fireTotemActive = totem->GetTotemType() == TOTEM_ACTIVE;
                        if (Spell* spell = totem->GetCurrentSpell(CURRENT_GENERIC_SPELL))
                            fireTotemGenericSpell = spell->GetSpellInfo()->Id;
                        if (Spell* spell = totem->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
                            fireTotemChanneledSpell = spell->GetSpellInfo()->Id;
                        if (Spell* spell = totem->GetCurrentSpell(CURRENT_AUTOREPEAT_SPELL))
                            fireTotemAutorepeatSpell = spell->GetSpellInfo()->Id;
                        if (TotemAI* ai = dynamic_cast<TotemAI*>(totem->AI()))
                        {
                            fireTotemUsesTotemAI = true;
                            fireTotemUpdateCalls = ai->GetUpdateCalls();
                            fireTotemCastAttempts = ai->GetCastAttempts();
                            fireTotemCastSuccesses = ai->GetCastSuccesses();
                            fireTotemLastCastResult = uint32(ai->GetLastCastResult());
                            fireTotemTargetValid = ai->WasLastTargetValidForTotem();
                            fireTotemOwnerTargetValid = ai->WasLastTargetValidForOwner();
                            fireTotemCastingSkips = ai->GetCastingSkips();
                            fireTotemMissingSpellSkips = ai->GetMissingSpellSkips();
                            fireTotemNoTargetSkips = ai->GetNoTargetSkips();
                        }
                    }
        }
        bool persistentSetupReady = false;
        bool manaGemReady = true;
        if (bot)
        {
            switch (bot->getClass())
            {
                case CLASS_PALADIN:
                {
                    bool const tank = std::string(GetDungeonRole(bot)) == "tank";
                    persistentSetupReady = (bot->HasAura(20217) || bot->HasAura(79063))
                        && (!tank || (bot->HasAura(25780) && bot->HasAura(31801) && bot->HasAura(465)));
                    break;
                }
                case CLASS_MAGE:
                {
                    BotClassSpecActionProfile const profile = BotClassSpecActionProfileStore::BuildForSpec(
                        bot, GetDungeonRole(bot), Cohort().CalibrationTargetSpec.c_str());
                    bool const manaGemEnabled = std::any_of(
                        profile.Spells.begin(), profile.Spells.end(), [](BotActionProfileSpell const& spell)
                        {
                            return spell.Category == BotCombatActionCategory::UseItem && spell.SpellId == 5405;
                        });
                    manaGemReady = !manaGemEnabled || bot->GetItemByEntry(36799);
                    persistentSetupReady = (bot->HasAura(1459) || bot->HasAura(79058))
                        && (bot->HasAura(30482) || bot->HasAura(6117)) && manaGemReady;
                    break;
                }
                case CLASS_HUNTER:
                    persistentSetupReady = bot->HasAura(13165) && bot->GetPet() && bot->GetPet()->IsAlive();
                    break;
                case CLASS_DEATH_KNIGHT:
                {
                    BotClassSpecActionProfile const profile = BotClassSpecActionProfileStore::BuildForSpec(
                        bot, GetDungeonRole(bot), Cohort().CalibrationTargetSpec.c_str());
                    bool const presenceRequired =
                        profile.SpecTag == "frost_death_knight"
                        || profile.SpecTag == "unholy_death_knight";
                    if (!presenceRequired)
                    {
                        persistentSetupReady = true;
                        break;
                    }
                    bool const presenceReady = state.RequiredPresenceSetupSpellId == 48265
                        && state.RequiredPresenceSetupAuraId == 48265
                        && state.RequiredPresenceSetupSpellKnown
                        && bot->HasSpell(48265) && bot->HasAura(48265)
                        && state.PresenceSetupNativeCastSubmittedAtMs
                        && state.PresenceSetupAuraObservedAtMs
                            >= state.PresenceSetupNativeCastSubmittedAtMs;
                    persistentSetupReady = presenceReady
                        && (profile.SpecTag != "unholy_death_knight"
                            || nativePersistentPetReady);
                    break;
                }
                case CLASS_WARLOCK:
                {
                    BotClassSpecActionProfile const profile =
                        BotClassSpecActionProfileStore::BuildForSpec(
                            bot, GetDungeonRole(bot), Cohort().CalibrationTargetSpec.c_str());
                    bool const petRequired =
                        profile.SpecTag == "affliction_warlock"
                        || profile.SpecTag == "demonology_warlock";
                    persistentSetupReady = !petRequired
                        || nativePersistentPetReady
                        || preexistingAfflictionPetReady;
                    break;
                }
                case CLASS_ROGUE:
                {
                    BotClassSpecActionProfile const profile =
                        BotClassSpecActionProfileStore::BuildForSpec(
                            bot, GetDungeonRole(bot), Cohort().CalibrationTargetSpec.c_str());
                    bool const poisonRequired =
                        profile.SpecTag == "assassination_rogue"
                        || profile.SpecTag == "combat_rogue";
                    persistentSetupReady = !poisonRequired
                        || (state.RoguePoisonSetupRequired
                            && IsNativePoisonSetupReady(bot,
                                state.RogueMainhandPoisonSetup)
                            && IsNativePoisonSetupReady(bot,
                                state.RogueOffhandPoisonSetup));
                    break;
                }
                case CLASS_SHAMAN:
                {
                    BotClassSpecActionProfile const profile = BotClassSpecActionProfileStore::BuildForSpec(
                        bot, GetDungeonRole(bot), Cohort().CalibrationTargetSpec.c_str());
                    bool const enhancement = profile.SpecTag == "enhancement"
                        || profile.SpecTag == "enhancement_shaman";
                    auto weaponEnchantReady = [bot](uint8 slot, uint32 enchantId, bool weaponRequired)
                    {
                        Item const* item = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot);
                        ItemTemplate const* itemTemplate = item ? item->GetTemplate() : nullptr;
                        if (!itemTemplate || itemTemplate->GetClass() != ITEM_CLASS_WEAPON)
                            return !weaponRequired;
                        return item->GetEnchantmentId(TEMP_ENCHANTMENT_SLOT) == enchantId;
                    };
                    bool const healer = std::string(GetDungeonRole(bot)) == "healer";
                    persistentSetupReady = bot->HasAura(healer ? 52127 : 324)
                        && weaponEnchantReady(EQUIPMENT_SLOT_MAINHAND, enhancement ? 283 : 5, true)
                        && weaponEnchantReady(EQUIPMENT_SLOT_OFFHAND, 5, enhancement);
                    break;
                }
                default:
                    persistentSetupReady = true;
                    break;
            }
        }
        bool const presenceSpellKnown = bot && state.RequiredPresenceSetupSpellId
            && state.RequiredPresenceSetupSpellKnown
            && bot->HasSpell(state.RequiredPresenceSetupSpellId);
        bool const presenceAuraActive = bot && state.RequiredPresenceSetupAuraId
            && bot->HasAura(state.RequiredPresenceSetupAuraId);
        bool const presenceNativeCastSubmitted = state.PresenceSetupNativeCastSubmittedAtMs != 0;
        bool const presenceNativeCastObserved = presenceNativeCastSubmitted
            && state.PresenceSetupAuraObservedAtMs >= state.PresenceSetupNativeCastSubmittedAtMs;
        std::vector<uint32> activeTalentSpellIds;
        std::vector<uint32> glyphPropertyIds;
        std::vector<uint32> glyphAuraSpellIds;
        if (bot)
        {
            for (auto const& [spellId, talent] :
                bot->GetTalentMap(bot->GetActiveSpec()))
                if (talent.State != PLAYERSPELL_REMOVED)
                    activeTalentSpellIds.push_back(spellId);
            std::sort(activeTalentSpellIds.begin(), activeTalentSpellIds.end());
            for (uint8 glyphSlot = 0; glyphSlot < MAX_GLYPH_SLOT_INDEX;
                ++glyphSlot)
                if (uint32 const glyphPropertyId =
                    bot->GetGlyph(bot->GetActiveSpec(), glyphSlot))
                {
                    glyphPropertyIds.push_back(glyphPropertyId);
                    if (GlyphPropertiesEntry const* glyph =
                        sGlyphPropertiesStore.LookupEntry(glyphPropertyId))
                        glyphAuraSpellIds.push_back(glyph->SpellID);
                }
            std::sort(glyphPropertyIds.begin(), glyphPropertyIds.end());
            std::sort(glyphAuraSpellIds.begin(), glyphAuraSpellIds.end());
        }
        json << "{\"guid\":" << state.Guid.GetCounter()
             << ",\"name\":\"" << JsonEscape(bot ? bot->GetName() : "loading") << "\""
             << ",\"class_id\":" << (bot ? uint32(bot->getClass()) : 0)
             << ",\"race_id\":" << (bot ? uint32(bot->getRace()) : 0)
             << ",\"role\":\"" << (bot ? JsonEscape(GetDungeonRole(bot)) : "unknown") << "\""
             << ",\"level\":" << (bot ? uint32(bot->getLevel()) : 0)
             << ",\"average_item_level\":" << std::fixed << std::setprecision(3)
             << (bot ? bot->GetAverageItemLevel() : 0.0f)
             << ",\"grouped\":" << (bot && bot->GetGroup() ? "true" : "false")
             << ",\"group_size\":" << (bot && bot->GetGroup() ? bot->GetGroup()->GetMembersCount() : 0)
             << ",\"active_talent_spell_ids\":[";
        for (size_t index = 0; index < activeTalentSpellIds.size(); ++index)
        {
            if (index)
                json << ',';
            json << activeTalentSpellIds[index];
        }
        json << "],\"glyph_property_ids\":[";
        for (size_t index = 0; index < glyphPropertyIds.size(); ++index)
        {
            if (index)
                json << ',';
            json << glyphPropertyIds[index];
        }
        json << "],\"glyph_aura_spell_ids\":[";
        for (size_t index = 0; index < glyphAuraSpellIds.size(); ++index)
        {
            if (index)
                json << ',';
            json << glyphAuraSpellIds[index];
        }
        json << "],\"gear_profile_observation\":{\"items\":[";
        bool firstGearItem = true;
        if (bot)
            for (uint8 equipmentSlot = EQUIPMENT_SLOT_START;
                equipmentSlot < EQUIPMENT_SLOT_END; ++equipmentSlot)
                if (Item const* item = bot->GetItemByPos(
                    INVENTORY_SLOT_BAG_0, equipmentSlot))
                {
                    if (!firstGearItem)
                        json << ',';
                    firstGearItem = false;
                    json << "{\"slot\":" << uint32(equipmentSlot)
                         << ",\"item_id\":" << item->GetEntry()
                         << ",\"enchant_id\":"
                         << item->GetEnchantmentId(PERM_ENCHANTMENT_SLOT)
                         << ",\"reforge_id\":"
                         << item->GetEnchantmentId(REFORGE_ENCHANTMENT_SLOT)
                         << ",\"gem_item_ids\":[";
                    bool firstGem = true;
                    for (uint8 gemSlot = 0; gemSlot < MAX_GEM_SOCKETS; ++gemSlot)
                    {
                        uint32 const gemEnchantId = item->GetEnchantmentId(
                            EnchantmentSlot(SOCK_ENCHANTMENT_SLOT + gemSlot));
                        uint32 gemItemId = 0;
                        if (SpellItemEnchantmentEntry const* enchant =
                            sSpellItemEnchantmentStore.LookupEntry(gemEnchantId))
                            gemItemId = enchant->Src_itemID;
                        if (!firstGem)
                            json << ',';
                        firstGem = false;
                        json << gemItemId;
                    }
                    json << "]}";
                }
        json << "]}"
             << ",\"fixture_contract\":{\"schema\":\""
             << BotCalibrationFixtureContractGenerated::Schema
             << "\",\"content_sha256\":\""
             << BotCalibrationFixtureContractGenerated::ContentSha256
             << "\",\"upstream_revision\":\""
             << BotCalibrationFixtureContractGenerated::UpstreamRevision
             << "\"}"
             << ",\"dynamic_action_observation\":{\"schema\":\"phase8_disabled_dynamic_actions_v1\""
             << ",\"expected_disabled\":true,\"attempt_counts\":{\"79476\":"
             << actionAttemptCount(79476)
             << ",\"82174\":" << actionAttemptCount(82174)
             << ",\"20572\":" << actionAttemptCount(20572)
             << ",\"26297\":" << actionAttemptCount(26297)
             << ",\"28730\":" << actionAttemptCount(28730)
             << ",\"33697\":" << actionAttemptCount(33697)
             << ",\"33702\":" << actionAttemptCount(33702)
             << ",\"69041\":" << actionAttemptCount(69041) << "}"
             << ",\"all_zero\":"
             << (actionAttemptCount(79476) + actionAttemptCount(82174)
                    + actionAttemptCount(20572) + actionAttemptCount(26297)
                    + actionAttemptCount(28730) + actionAttemptCount(33697)
                    + actionAttemptCount(33702) + actionAttemptCount(69041)
                    == 0 ? "true" : "false") << '}'
             << ",\"initial_resources\":{\"schema\":\"phase8_initial_resources_observation_v1\""
             << ",\"source_contract_sha256\":\""
             << JsonEscape(metrics ? metrics->InitialResourceSourceContract : "") << "\""
             << ",\"reset_applied\":"
             << (metrics && metrics->InitialResourcesApplied ? "true" : "false")
             << ",\"matches_contract\":"
             << (metrics && metrics->InitialResourcesMatchContract ? "true" : "false")
             << ",\"observed_at_ms\":"
             << (metrics ? metrics->InitialResourcesObservedAtMs : 0)
             << ",\"observed_before_scoring\":"
             << (metrics && metrics->InitialResourcesObservedAtMs
                    && metrics->WindowStartedMs
                    && metrics->InitialResourcesObservedAtMs
                        <= metrics->WindowStartedMs ? "true" : "false")
             << ",\"powers\":[";
        bool firstInitialPower = true;
        if (metrics)
            for (CalibrationMetrics::InitialPowerObservation const& power :
                metrics->InitialPowerObservations)
            {
                if (!firstInitialPower)
                    json << ',';
                firstInitialPower = false;
                json << "{\"unit_kind\":\"" << JsonEscape(power.UnitKind)
                     << "\",\"unit_guid\":" << power.UnitGuid
                     << ",\"name\":\"" << JsonEscape(power.PowerName)
                     << "\",\"power_type\":" << uint32(power.PowerType)
                     << ",\"expected_mode\":\""
                     << (power.ExpectedMaximum ? "maximum" : "exact")
                     << "\",\"expected_native_value\":"
                     << power.ExpectedNativeValue
                     << ",\"expected_display_value\":"
                     << power.ExpectedDisplayValue
                     << ",\"observed_native_value\":"
                     << power.ObservedNativeValue
                     << ",\"observed_display_value\":"
                     << power.ObservedDisplayValue
                     << ",\"observed_maximum_native_value\":"
                     << power.ObservedMaximumNativeValue
                     << ",\"matches_contract\":"
                     << (power.MatchesContract ? "true" : "false") << '}';
            }
        json << "],\"runes\":{\"required\":"
             << (metrics && metrics->InitialRunesRequired ? "true" : "false")
             << ",\"expected_ready_mask\":"
             << (metrics ? uint32(metrics->InitialExpectedRuneReadyMask) : 0)
             << ",\"observed_ready_mask\":"
             << (metrics ? uint32(metrics->InitialObservedRuneReadyMask) : 0) << '}'
             << ",\"combo_points\":{\"required\":"
             << (metrics && metrics->InitialComboPointsRequired ? "true" : "false")
             << ",\"expected\":"
             << (metrics ? uint32(metrics->InitialExpectedComboPoints) : 0)
             << ",\"observed\":"
             << (metrics ? uint32(metrics->InitialObservedComboPoints) : 0) << '}'
             << ",\"neutral_eclipse\":{\"required\":"
             << (metrics && metrics->InitialNeutralEclipseRequired ? "true" : "false")
             << ",\"observed\":"
             << (metrics && metrics->InitialNeutralEclipseObserved ? "true" : "false") << '}'
             << ",\"pet_resource\":{\"required\":"
             << (metrics && metrics->InitialPetResourceRequired ? "true" : "false")
             << ",\"observed\":"
             << (metrics && metrics->InitialPetResourceObserved ? "true" : "false") << "}}"
             << ",\"item_swap_observation\":{\"schema\":\"phase8_no_item_swap_observation_v1\""
             << ",\"enabled\":false,\"initial_gear_manifest_sha256\":\""
             << JsonEscape(metrics ? metrics->InitialGearManifestSha256 : "")
             << "\",\"target_guid\":" << state.Guid.GetCounter()
             << ",\"window_started_at_ms\":"
             << (metrics ? metrics->WindowStartedMs : 0)
             << ",\"window_ended_at_ms\":"
             << (metrics ? metrics->WindowEndedMs : 0)
             << ",\"first_sample_at_ms\":"
             << (metrics ? metrics->FirstGearIdentityObservedAtMs : 0)
             << ",\"last_sample_at_ms\":"
             << (metrics ? metrics->LastGearIdentityObservedAtMs : 0)
             << ",\"maximum_sample_gap_ms\":"
             << (metrics ? metrics->MaximumGearIdentityObservationGapMs : 0)
             << ",\"current_gear_manifest_sha256\":\""
             << JsonEscape(metrics ? metrics->LastObservedGearManifestSha256 : "")
             << "\",\"sample_count\":"
             << (metrics ? metrics->GearIdentitySampleCount : 0)
             << ",\"mismatch_sample_count\":"
             << (metrics ? metrics->GearIdentityMismatchSampleCount : 0)
             << ",\"no_drift\":"
             << (metrics && metrics->GearIdentitySampleCount
                    && !metrics->InitialGearManifestSha256.empty()
                    && metrics->InitialGearManifestSha256
                        == metrics->LastObservedGearManifestSha256
                    && !metrics->GearIdentityMismatchSampleCount
                    ? "true" : "false") << '}'
             << ",\"pre_score_state\":{\"schema\":\"phase8_pre_score_state_observation_v1\""
             << ",\"observed_at_ms\":"
             << (metrics ? metrics->PreScoreStateObservedAtMs : 0)
             << ",\"observed_before_scoring\":"
             << (metrics && metrics->PreScoreStateObservedAtMs
                    && metrics->WindowStartedMs
                    && metrics->PreScoreStateObservedAtMs
                        <= metrics->WindowStartedMs ? "true" : "false")
             << ",\"persistent_setup_ready\":"
             << (metrics && metrics->PreScorePersistentSetupReady ? "true" : "false")
             << ",\"reference_buffs_ready\":"
             << (metrics && metrics->PreScoreReferenceBuffsReady ? "true" : "false")
             << ",\"reference_target_debuffs_ready\":"
             << (metrics && metrics->PreScoreReferenceTargetDebuffsReady ? "true" : "false")
             << ",\"heroism_ready\":"
             << (metrics && metrics->PreScoreHeroismReady ? "true" : "false")
             << ",\"temporal_external_auras_absent\":"
             << (metrics && metrics->PreScoreTemporalExternalsAbsent ? "true" : "false")
             << ",\"external_bleed_auras_absent\":"
             << (metrics && metrics->PreScoreExternalBleedAbsent ? "true" : "false")
             << ",\"last_potion_item_id\":"
             << (metrics ? metrics->PreScoreLastPotionItemId : 0)
             << ",\"no_active_cast\":"
             << (metrics && metrics->PreScoreNoActiveCast ? "true" : "false")
             << ",\"no_combat\":"
             << (metrics && metrics->PreScoreNoCombat ? "true" : "false")
             << ",\"global_cooldown_clear\":"
             << (metrics && metrics->PreScoreGlobalCooldownClear ? "true" : "false")
             << ",\"cooldown_reset_applied\":"
             << (metrics && metrics->PreScoreCooldownResetApplied ? "true" : "false")
             << ",\"warmup_profile_actions_suppressed\":"
             << (metrics && metrics->WarmupProfileActionsSuppressed ? "true" : "false") << '}'
             << ",\"external_window_observation\":{\"schema\":\"phase8_external_windows_observation_v1\""
             << ",\"target_guid\":" << state.Guid.GetCounter()
             << ",\"window_started_at_ms\":"
             << (metrics ? metrics->WindowStartedMs : 0)
             << ",\"window_ended_at_ms\":"
             << (metrics ? metrics->WindowEndedMs : 0)
             << ",\"first_sample_at_ms\":"
             << (metrics ? metrics->FirstExternalWindowObservedAtMs : 0)
             << ",\"last_sample_at_ms\":"
             << (metrics ? metrics->LastExternalWindowObservedAtMs : 0)
             << ",\"maximum_sample_gap_ms\":"
             << (metrics ? metrics->MaximumExternalWindowObservationGapMs : 0)
             << ",\"sample_count\":"
             << (metrics ? metrics->ExternalWindowSampleCount : 0)
             << ",\"heroism\":{\"source_count\":0,\"spell_id\":2825,\"windows_ms\":[],\"expected_active_samples\":"
             << (metrics ? metrics->HeroismExpectedActiveSamples : 0)
             << ",\"observed_active_samples\":"
             << (metrics ? metrics->HeroismObservedActiveSamples : 0)
             << ",\"mismatch_samples\":"
             << (metrics ? metrics->HeroismMismatchSamples : 0) << '}'
             << ",\"power_infusion\":{\"source_count\":"
             << 0
             << ",\"spell_id\":10060,\"windows_ms\":[]"
             << ",\"expected_active_samples\":"
             << (metrics ? metrics->PowerInfusionExpectedActiveSamples : 0)
             << ",\"observed_active_samples\":"
             << (metrics ? metrics->PowerInfusionObservedActiveSamples : 0)
             << ",\"mismatch_samples\":"
             << (metrics ? metrics->PowerInfusionMismatchSamples : 0) << '}'
             << ",\"dark_intent_proc\":{\"base_spell_id\":85767,\"base_enabled\":false,\"unexpected_base_active_samples\":"
             << (metrics ? metrics->UnexpectedDarkIntentBaseSamples : 0)
             << ",\"proc_spell_id\":85759,\"uptime_pct\":0,\"expected_uptime_pct\":0,\"unexpected_active_samples\":"
             << (metrics ? metrics->UnexpectedDarkIntentProcSamples : 0) << '}'
             << ",\"synapse_springs\":{\"spell_id\":96230,\"windows_ms\":[],\"expected_windows_ms\":[],\"unexpected_active_samples\":"
             << (metrics ? metrics->UnexpectedSynapseSpringsSamples : 0) << "}}";
        AppendCalibrationReferenceConditionJson(json, state, metrics, fixtureSpecContract);
        json << ",\"persistent_setup\":{\"ready\":" << (persistentSetupReady ? "true" : "false")
             << ",\"required_presence_spell_id\":" << state.RequiredPresenceSetupSpellId
             << ",\"required_presence_aura_id\":" << state.RequiredPresenceSetupAuraId
             << ",\"presence_spell_known\":" << (presenceSpellKnown ? "true" : "false")
             << ",\"presence_aura_active\":" << (presenceAuraActive ? "true" : "false")
             << ",\"presence_native_cast_submitted\":" << (presenceNativeCastSubmitted ? "true" : "false")
             << ",\"presence_native_cast_observed\":" << (presenceNativeCastObserved ? "true" : "false")
             << ",\"presence_native_cast_submitted_at_ms\":" << state.PresenceSetupNativeCastSubmittedAtMs
             << ",\"presence_native_cast_observed_at_ms\":" << state.PresenceSetupAuraObservedAtMs
             << ",\"required_pet_spell_id\":" << petSetup.RequiredSummonSpellId
             << ",\"required_pet_created_by_spell_id\":" << petSetup.RequiredCreatedBySpellId
             << ",\"required_pet_entry\":" << petSetup.RequiredEntry
             << ",\"required_pet_family_id\":" << petSetup.RequiredFamilyId
             << ",\"required_pet_type\":" << petSetup.RequiredPetType
             << ",\"required_pet_power_type\":" << petSetup.RequiredPowerType
             << ",\"pet_spell_known\":" << (petSetup.SummonSpellKnown ? "true" : "false")
             << ",\"pet_native_cast_submitted\":" << (petSetup.NativeCastSubmittedAtMs ? "true" : "false")
             << ",\"pet_native_cast_finished\":" << (petSetup.NativeCastFinishedSuccessfully ? "true" : "false")
             << ",\"pet_native_cast_observed\":" << (petSetup.NativeCastObservedAtMs ? "true" : "false")
             << ",\"pet_native_cast_submitted_at_ms\":" << petSetup.NativeCastSubmittedAtMs
             << ",\"pet_native_cast_finished_at_ms\":" << petSetup.NativeCastFinishedAtMs
             << ",\"pet_native_cast_observed_at_ms\":" << petSetup.NativeCastObservedAtMs
             << ",\"pet_guid\":" << ordinaryPet.Guid.GetCounter()
             << ",\"pet_id\":"
             << (hunterPetIdentityObserved
                    ? hunterPetIdentity.PetId : 0)
             << ",\"pet_entry\":" << ordinaryPet.Entry
             << ",\"pet_family_id\":" << ordinaryPet.FamilyId
             << ",\"pet_type\":" << ordinaryPet.PetType
             << ",\"pet_created_by_spell_id\":" << ordinaryPet.CreatedBySpellId
             << ",\"pet_present\":" << (ordinaryPet.Present ? "true" : "false")
             << ",\"pet_in_world\":" << (ordinaryPet.InWorld ? "true" : "false")
             << ",\"pet_alive\":" << (ordinaryPet.Alive ? "true" : "false")
             << ",\"pet_owned\":" << (ordinaryPet.Owned ? "true" : "false")
             << ",\"pet_permanent\":" << (ordinaryPet.Permanent ? "true" : "false")
             << ",\"pet_health\":" << ordinaryPet.Health
             << ",\"pet_max_health\":" << ordinaryPet.MaxHealth
             << ",\"pet_power_type\":" << ordinaryPet.PowerType
             << ",\"pet_power\":" << ordinaryPet.Power
             << ",\"pet_max_power\":" << ordinaryPet.MaxPower
             << ",\"pet_observed_owner_guid\":" << state.Guid.GetCounter()
             << ",\"pet_observation_window_started_at_ms\":"
             << (metrics ? metrics->WindowStartedMs : 0)
             << ",\"pet_observation_window_ended_at_ms\":"
             << (metrics ? metrics->WindowEndedMs : 0)
             << ",\"pet_first_observation_at_ms\":"
             << (metrics ? metrics->FirstPetSetupObservedAtMs : 0)
             << ",\"pet_last_observation_at_ms\":"
             << (metrics ? metrics->LastPetSetupObservedAtMs : 0)
             << ",\"pet_maximum_observation_gap_ms\":"
             << (metrics ? metrics->MaximumPetSetupObservationGapMs : 0)
             << ",\"pet_first_observed_guid\":"
             << (metrics ? metrics->FirstPetSetupObservedGuid : 0)
             << ",\"pet_last_observed_guid\":"
             << (metrics ? metrics->LastPetSetupObservedGuid : 0)
             << ",\"pet_guid_mismatch_sample_count\":"
             << (metrics ? metrics->PetSetupGuidMismatchSampleCount : 0)
             << ",\"pet_identity_mismatch_sample_count\":"
             << (metrics ? metrics->PetSetupIdentityMismatchSampleCount : 0)
             << ",\"pet_ready_ticks\":"
             << (metrics ? metrics->PetSetupReadySampleCount : 0)
             << ",\"pet_observation_ticks\":"
             << (metrics ? metrics->PetSetupObservationSampleCount : 0)
             << ",\"pet_uptime_ratio\":" << requiredPetUptimeRatio
             << ",\"pet_spellbook_sha256\":\"" << JsonEscape(ordinaryPet.SpellbookSha256) << "\""
             << ",\"pet_spellbook\":[";
        for (size_t index = 0; index < ordinaryPet.Spellbook.size(); ++index)
        {
            if (index)
                json << ',';
            BotWorldPopulationMgrCalibrationIdentity::OrdinaryPetSpellIdentity const& spell = ordinaryPet.Spellbook[index];
            json << "{\"spell_id\":" << spell.SpellId
                 << ",\"active\":" << uint32(spell.Active)
                 << ",\"type\":" << uint32(spell.Type) << '}';
        }
        json << "],\"pet_admission_spellbook_sha256\":\""
             << JsonEscape(hunterPetIdentityObserved
                    ? hunterPetIdentity.SpellbookSha256 : "") << "\""
             << ",\"pet_admission_spellbook\":[";
        if (hunterPetIdentityObserved)
            for (size_t index = 0;
                index < hunterPetIdentity.Spellbook.size(); ++index)
            {
                if (index)
                    json << ',';
                json << "{\"spell_id\":"
                     << hunterPetIdentity.Spellbook[index].first
                     << ",\"active\":"
                     << uint32(hunterPetIdentity.Spellbook[index].second)
                     << '}';
            }
        json << "],\"pet_autocast_spell_ids\":[";
        for (size_t index = 0; index < ordinaryPet.AutocastSpellIds.size(); ++index)
        {
            if (index)
                json << ',';
            json << ordinaryPet.AutocastSpellIds[index];
        }
        json << ']'
             << ",\"pet_execution_observation\":{\"sample_count\":"
             << petExecutionSamples
             << ",\"alive_samples\":" << petAliveSamples
             << ",\"alive_ratio\":"
             << (petExecutionSamples
                     ? double(petAliveSamples) / petExecutionSamples : 0.0)
             << ",\"attacking_samples\":" << petAttackingSamples
             << ",\"attacking_ratio\":"
             << (petExecutionSamples
                     ? double(petAttackingSamples) / petExecutionSamples : 0.0)
             << ",\"target_match_samples\":" << petTargetMatchSamples
             << ",\"target_match_ratio\":"
             << (petExecutionSamples
                     ? double(petTargetMatchSamples) / petExecutionSamples : 0.0)
             << ",\"command_attack_samples\":"
             << petCommandAttackSamples
             << ",\"command_attack_ratio\":"
             << (petExecutionSamples
                     ? double(petCommandAttackSamples) / petExecutionSamples : 0.0)
             << ",\"last_victim_guid\":"
             << (metrics && !metrics->DecisionTimeline.empty()
                     ? metrics->DecisionTimeline.back().PetVictimGuid : 0)
             << ",\"diagnostic_basis\":\"decision_timeline_pet_state\"}"
             << ",\"arcane_brilliance\":" << (bot && (bot->HasAura(1459) || bot->HasAura(79058)) ? "true" : "false")
             << ",\"molten_armor\":" << (bot && bot->HasAura(30482) ? "true" : "false")
             << ",\"mage_armor\":" << (bot && bot->HasAura(6117) ? "true" : "false")
             << ",\"mana_gem_ready\":" << (manaGemReady ? "true" : "false")
             << ",\"aspect_of_the_hawk\":" << (bot && bot->HasAura(13165) ? "true" : "false")
             << ",\"lightning_shield\":" << (bot && bot->HasAura(324) ? "true" : "false")
             << ",\"water_shield\":" << (bot && bot->HasAura(52127) ? "true" : "false")
             << ",\"mainhand_item_entry\":" << mainhandItemEntry
             << ",\"dragonwrath_proc_aura\":" << (bot && bot->HasAura(101056) ? "true" : "false")
             << ",\"mainhand_temp_enchant\":" << mainhandTempEnchant
             << ",\"offhand_temp_enchant\":" << offhandTempEnchant
             << ",\"poison_setup_required\":"
             << (state.RoguePoisonSetupRequired ? "true" : "false")
             << ",\"poisons\":{\"mainhand\":";
        auto writePoisonReceipt = [&json](
            WorldBotState::NativePoisonSetupReceipt const& receipt)
        {
            bool const submitted = receipt.NativeUseSubmittedAtMs != 0;
            bool const observed = submitted
                && receipt.NativeUseFinishedSuccessfully
                && receipt.NativeUseFinishedAtMs
                    >= receipt.NativeUseSubmittedAtMs
                && receipt.NativeUseFinishedItemGuid
                    == receipt.SubmittedItemGuid
                && receipt.NativeUseFinishedWeaponGuid
                    == receipt.SubmittedWeaponGuid
                && receipt.ObservedWeaponGuid
                    == receipt.SubmittedWeaponGuid
                && receipt.EnchantObservedAtMs
                    >= receipt.NativeUseFinishedAtMs
                && receipt.ObservedEnchantId
                    == receipt.RequiredEnchantId
                && receipt.ObservedEnchantDurationMs >= 900000;
            json << "{\"equipment_slot\":"
                 << uint32(receipt.EquipmentSlot)
                 << ",\"required_item_entry\":"
                 << receipt.RequiredItemEntry
                 << ",\"required_spell_id\":"
                 << receipt.RequiredSpellId
                 << ",\"required_enchant_id\":"
                 << receipt.RequiredEnchantId
                 << ",\"item_available\":"
                 << (receipt.ItemAvailable ? "true" : "false")
                 << ",\"spell_available\":"
                 << (receipt.SpellAvailable ? "true" : "false")
                 << ",\"native_use_submitted\":"
                 << (submitted ? "true" : "false")
                 << ",\"native_use_submitted_at_ms\":"
                 << receipt.NativeUseSubmittedAtMs
                 << ",\"native_use_finished\":"
                 << (receipt.NativeUseFinishedSuccessfully
                        ? "true" : "false")
                 << ",\"native_use_finished_at_ms\":"
                 << receipt.NativeUseFinishedAtMs
                 << ",\"native_use_finished_item_guid\":"
                 << receipt.NativeUseFinishedItemGuid.GetCounter()
                 << ",\"native_use_finished_weapon_guid\":"
                 << receipt.NativeUseFinishedWeaponGuid.GetCounter()
                 << ",\"submitted_item_guid\":"
                 << receipt.SubmittedItemGuid.GetCounter()
                 << ",\"submitted_weapon_guid\":"
                 << receipt.SubmittedWeaponGuid.GetCounter()
                 << ",\"observed_weapon_guid\":"
                 << receipt.ObservedWeaponGuid.GetCounter()
                 << ",\"enchant_observed\":"
                 << (observed ? "true" : "false")
                 << ",\"enchant_observed_at_ms\":"
                 << receipt.EnchantObservedAtMs
                 << ",\"observed_weapon_item_entry\":"
                 << receipt.ObservedWeaponItemEntry
                 << ",\"observed_enchant_id\":"
                 << receipt.ObservedEnchantId
                 << ",\"observed_enchant_duration_ms\":"
                 << receipt.ObservedEnchantDurationMs << '}';
        };
        writePoisonReceipt(state.RogueMainhandPoisonSetup);
        json << ",\"offhand\":";
        writePoisonReceipt(state.RogueOffhandPoisonSetup);
        auto writeEffectiveStats = [&json](
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
                 << stats.SpellSpeedMultiplier << '}';
        };
        json << "}"
             << ",\"fire_totem\":{\"entry\":" << fireTotemEntry
             << ",\"created_by_spell\":" << fireTotemCreatedBySpell
             << ",\"attack_spell\":" << fireTotemSpell
             << ",\"alive\":" << (fireTotemAlive ? "true" : "false")
             << ",\"active\":" << (fireTotemActive ? "true" : "false")
             << ",\"uses_totem_ai\":" << (fireTotemUsesTotemAI ? "true" : "false")
             << ",\"update_calls\":" << fireTotemUpdateCalls
             << ",\"generic_spell\":" << fireTotemGenericSpell
             << ",\"channeled_spell\":" << fireTotemChanneledSpell
             << ",\"autorepeat_spell\":" << fireTotemAutorepeatSpell
             << ",\"cast_attempts\":" << fireTotemCastAttempts
             << ",\"cast_successes\":" << fireTotemCastSuccesses
             << ",\"last_cast_result\":" << fireTotemLastCastResult
             << ",\"totem_target_valid\":" << (fireTotemTargetValid ? "true" : "false")
             << ",\"owner_target_valid\":" << (fireTotemOwnerTargetValid ? "true" : "false")
             << ",\"casting_skips\":" << fireTotemCastingSkips
             << ",\"missing_spell_skips\":" << fireTotemMissingSpellSkips
             << ",\"no_target_skips\":" << fireTotemNoTargetSkips << "}}"
             << ",\"scoring_start_stats\":{\"schema\":\"trinity_scoring_start_effective_stats_v1\",\"player\":";
        if (metrics)
            writeEffectiveStats(metrics->ScoringStartPlayerStats);
        else
            writeEffectiveStats(CalibrationMetrics::EffectiveStatVector());
        json << ",\"pet\":";
        if (metrics)
            writeEffectiveStats(metrics->ScoringStartPetStats);
        else
            writeEffectiveStats(CalibrationMetrics::EffectiveStatVector());
        json << "}"
             << ",\"stats\":{\"strength\":" << (bot ? bot->GetStat(STAT_STRENGTH) : 0.0f)
             << ",\"agility\":" << (bot ? bot->GetStat(STAT_AGILITY) : 0.0f)
             << ",\"intellect\":" << (bot ? bot->GetStat(STAT_INTELLECT) : 0.0f)
             << ",\"melee_attack_power\":" << (bot ? bot->GetTotalAttackPowerValue(BASE_ATTACK) : 0.0f)
             << ",\"ranged_attack_power\":" << (bot ? bot->GetTotalAttackPowerValue(RANGED_ATTACK) : 0.0f)
             << ",\"spell_power\":" << (bot ? bot->SpellBaseDamageBonusDone(SPELL_SCHOOL_MASK_SPELL, true) : 0)
             << ",\"melee_hit_pct\":" << (bot ? bot->GetRatingBonusValue(CR_HIT_MELEE) : 0.0f)
             << ",\"ranged_hit_pct\":" << (bot ? bot->GetRatingBonusValue(CR_HIT_RANGED) : 0.0f)
             << ",\"spell_hit_pct\":" << (bot ? bot->GetRatingBonusValue(CR_HIT_SPELL) : 0.0f)
             << ",\"mastery_points\":" << (bot ? bot->GetRatingBonusValue(CR_MASTERY) : 0.0f)
             << ",\"eclipse_power\":" << (bot ? bot->GetPower(POWER_ECLIPSE) : 0)
             << ",\"solar_eclipse_active\":" << (bot && bot->HasAura(48517) ? "true" : "false")
             << ",\"lunar_eclipse_active\":" << (bot && bot->HasAura(48518) ? "true" : "false") << '}'
             << ",\"reference_setup\":{\"enabled\":" << (Cohort().Config.CombatCalibrationReferenceConditions ? "true" : "false")
             << ",\"buffs_ready\":" << (metrics && metrics->ReferenceBuffsReady ? "true" : "false")
             << ",\"replenishment_required\":" << (CalibrationSpecUsesMana(Cohort().CalibrationTargetSpec) ? "true" : "false")
             << ",\"buff_auras\":{\"53646\":" << (bot && bot->HasAura(53646) ? "true" : "false")
             << ",\"79058\":" << (bot && bot->HasAura(79058) ? "true" : "false")
             << ",\"24932\":" << (bot && bot->HasAura(24932) ? "true" : "false")
             << ",\"2895\":" << (bot && bot->HasAura(2895) ? "true" : "false")
             << ",\"8515\":" << (bot && bot->HasAura(8515) ? "true" : "false")
             << ",\"8076\":" << (bot && bot->HasAura(8076) ? "true" : "false")
             << ",\"82930\":" << (bot && bot->HasAura(82930) ? "true" : "false")
             << ",\"57669\":" << (metrics && metrics->ReferenceReplenishmentObserved ? "true" : "false")
             << ",\"kings_or_mark\":" << (bot && (bot->HasAura(20217) || bot->HasAura(79063)
                || bot->HasAura(1126) || bot->HasAura(79061)) ? "true" : "false")
             << ",\"79102\":" << (bot && bot->HasAura(79102) ? "true" : "false")
             << ",\"79470\":" << (bot && bot->HasAura(79470) ? "true" : "false")
             << ",\"79471\":" << (bot && bot->HasAura(79471) ? "true" : "false")
             << ",\"79472\":" << (bot && bot->HasAura(79472) ? "true" : "false")
             << ",\"85767\":" << (bot && bot->HasAura(85767) ? "true" : "false")
             << ",\"87547\":" << (bot && bot->HasAura(87547) ? "true" : "false") << '}'
             << ",\"balance_mushrooms_preplanted\":" << (metrics && metrics->BalanceMushroomsPreplanted ? "true" : "false")
             << ",\"balance_mushroom_preplant_count\":" << (metrics ? uint32(metrics->BalanceMushroomPreplantCount) : 0)
             << ",\"target_debuffs_ready\":" << (metrics && metrics->ReferenceTargetDebuffsReady ? "true" : "false")
             << ",\"heroism_window_observed\":" << (metrics && metrics->ReferenceHeroismWindowObserved ? "true" : "false") << '}'
             << ",\"elapsed_seconds\":" << std::fixed << std::setprecision(3) << elapsedSec
             << ",\"damage\":" << (metrics ? metrics->Damage : 0)
             << ",\"pet_damage\":" << (metrics ? metrics->PetDamage : 0)
             << ",\"primary_target_guid\":"
             << Cohort().CalibrationFixtureTargetGuid.GetCounter()
             << ",\"primary_target_damage\":"
             << (metrics ? metrics->PrimaryTargetDamage : 0)
             << ",\"off_target_damage\":"
             << (metrics ? metrics->OffTargetDamage : 0)
             << ",\"observed_distinct_damage_targets\":"
             << (metrics ? metrics->LastDamageMsByTarget.size() : 0)
             << ",\"dps\":" << std::fixed << std::setprecision(2) << dps
             << ",\"threat_per_second\":" << std::fixed << std::setprecision(2) << tps
             << ",\"threat_observable\":" << (metrics && metrics->ThreatBaseline >= 0.0f && metrics->ThreatCurrent > metrics->ThreatBaseline ? "true" : "false")
             << ",\"target_count\":" << (metrics ? metrics->TargetCount : 0)
             << ",\"attempts\":" << (metrics ? metrics->Attempts : 0)
             << ",\"successes\":" << (metrics ? metrics->Successes : 0)
             << ",\"quality_metrics\":{\"active_uptime_ratio\":" << activeUptimeRatio
             << ",\"cast_failure_ratio\":" << castFailureRatio
             << ",\"resource_capped_ratio\":" << resourceCappedRatio
             << ",\"resource_starved_ratio\":" << resourceStarvedRatio
             << ",\"movement_range_loss_ratio\":" << movementRangeLossRatio
             << ",\"pet_damage_ratio\":" << petDamageRatio
             << ",\"illegal_action_count\":" << (metrics ? metrics->IllegalActionCount : 0)
             << ",\"action_group_count\":" << (metrics ? metrics->ActionGroups.size() : 0)
             << ",\"expected_action_group_count\":" << (metrics ? metrics->ExpectedActionGroups.size() : 0)
             << ",\"rotation_group_coverage\":" << rotationGroupCoverage << '}'
             << ",\"shadow_priest_metrics\":{\"shadow_orb_power_uptime_ratio\":" << shadowOrbPowerUptimeRatio
             << ",\"shadow_orb_uptime_ratio\":" << shadowOrbUptimeRatio
             << ",\"empowered_shadow_uptime_ratio\":" << empoweredShadowUptimeRatio
             << ",\"maximum_shadow_orb_stacks\":" << (metrics ? uint32(metrics->MaximumShadowOrbStacks) : 0) << '}'
             << AppendAfflictionCalibrationJson(metrics)
             << ",\"tank_metrics\":{\"stance_form_uptime_ratio\":"
             << (metrics && metrics->TickCount ? double(metrics->StanceFormActiveTicks) / double(metrics->TickCount) : 0.0)
             << ",\"mitigation_uptime_ratio\":"
             << (metrics && metrics->TickCount ? double(metrics->MitigationCoveredTicks) / double(metrics->TickCount) : 0.0)
             << ",\"all_hostile_retention_ratio\":"
             << (metrics && metrics->ThreatSampleCount ? double(metrics->AllHostilesRetainedSamples) / double(metrics->ThreatSampleCount) : 0.0)
             << ",\"snap_threat_success_ratio\":"
             << (metrics && metrics->SnapThreatChecks ? double(metrics->SnapThreatSuccesses) / double(metrics->SnapThreatChecks) : 0.0)
             << ",\"add_threat_success_ratio\":"
             << (metrics && metrics->AddThreatChecks ? double(metrics->AddThreatSuccesses) / double(metrics->AddThreatChecks) : 0.0)
             << ",\"threat_aura_uptime_ratio\":"
             << (metrics && metrics->TickCount ? double(metrics->ThreatAuraActiveTicks) / double(metrics->TickCount) : 0.0)
             << ",\"healer_exposure_ratio\":"
             << (metrics && metrics->ThreatSampleCount ? double(metrics->HealerExposureTicks) / double(metrics->ThreatSampleCount) : 0.0)
             << ",\"interrupt_success_ratio\":"
             << (metrics && metrics->InterruptChecks ? double(metrics->InterruptSuccesses) / double(metrics->InterruptChecks) : 0.0)
             << ",\"defensive_action_count\":" << (metrics ? metrics->DefensiveActionCount : 0)
             << ",\"health_floor_ratio\":" << (metrics ? metrics->MinimumHealthRatio : 0.0f)
             << ",\"maximum_controlled_damage\":" << (metrics ? metrics->MaximumControlledDamage : 0)
             << ",\"maximum_controlled_damage_ratio\":" << (metrics ? metrics->MaximumControlledDamageRatio : 0.0f)
             << ",\"death_count\":" << (metrics ? metrics->DeathCount : 0) << '}'
             << ",\"healer_metrics\":{\"attempted_healing\":" << (metrics ? metrics->AttemptedHealing : 0)
             << ",\"effective_healing\":" << (metrics ? metrics->EffectiveHealing : 0)
             << ",\"absorbed_healing\":" << (metrics ? metrics->AbsorbedHealing : 0)
             << ",\"effective_hps\":" << (metrics && elapsedSec > 0.0 ? double(metrics->EffectiveHealing) / elapsedSec : 0.0)
             << ",\"scheduled_event_count\":" << (metrics ? metrics->ScheduledDamageEvents : 0)
             << ",\"delivered_event_count\":" << (metrics ? metrics->DeliveredDamageEvents : 0)
             << ",\"dispel_attempts\":" << (metrics ? metrics->DispelAttempts : 0)
             << ",\"dispel_successes\":" << (metrics ? metrics->DispelSuccesses : 0)
             << ",\"cooldown_attempts\":" << (metrics ? metrics->CooldownAttempts : 0)
             << ",\"cooldown_successes\":" << (metrics ? metrics->CooldownSuccesses : 0)
             << ",\"response_latency_p95_ms\":" << responseLatencyP95
             << ",\"target_selection_accuracy\":" << targetSelectionAccuracy
             << ",\"idle_ratio_under_demand\":" << idleUnderDemandRatio
             << ",\"overheal_ratio\":" << overhealRatio
             << ",\"health_floor_ratio\":" << (metrics ? metrics->MinimumHealthRatio : 0.0f)
             << ",\"remaining_mana_ratio\":" << (bot && bot->GetMaxPower(POWER_MANA)
                ? double(bot->GetPower(POWER_MANA)) / double(bot->GetMaxPower(POWER_MANA)) : 0.0)
             << ",\"time_to_oom_seconds\":" << (bot && bot->GetPower(POWER_MANA) ? elapsedSec : 0.0)
             << ",\"controlled_damage\":" << (metrics ? metrics->ControlledDamage : 0) << '}';
        AppendCalibrationBotActionJson(json, metrics);
        uint32 botKey = state.Guid.GetCounter();
        auto rejectsItr = Party().LastCombatRejectsByBot.find(botKey);
        auto chosenItr = Party().LastChosenCombatByBot.find(botKey);
        json << "],\"last_action_rejections\":"
             << (!completedWindow && rejectsItr != Party().LastCombatRejectsByBot.end() ? rejectsItr->second : "null")
             << ",\"last_chosen_action\":"
             << (!completedWindow && chosenItr != Party().LastChosenCombatByBot.end() ? chosenItr->second : "null")
             << ",\"movement_diagnostic\":{\"last_path_reject_reason\":\""
             << JsonEscape(state.LastPathRejectReason)
             << "\",\"last_recovery_mode\":\"" << JsonEscape(state.LastRecoveryMode)
             << "\",\"last_recovery_result\":\"" << JsonEscape(state.LastRecoveryResult)
             << "\",\"active_path_valid\":" << (state.ActivePathValid ? "true" : "false")
             << ",\"active_path_traversal_mode\":\""
             << JsonEscape(state.ActivePathTraversalMode) << "\"}"
             << '}';
    }
    json << ']';
}
