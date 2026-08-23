#include "Bots/BotWorldPopulationMgr.h"

#include "SpellInfo.h"
#include "SpellMgr.h"

#include <algorithm>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

void BotWorldPopulationMgr::AppendCalibrationBotActionJson(
    std::ostringstream& json, CalibrationMetrics const* metrics) const
{
    json << ",\"action_groups\":[";
            bool firstGroup = true;
            if (metrics)
                for (std::string const& group : metrics->ActionGroups)
                {
                    if (!firstGroup)
                        json << ',';
                    firstGroup = false;
                    json << '\"' << JsonEscape(group) << '\"';
                }
            json << "],\"expected_action_groups\":[";
            bool firstExpectedGroup = true;
            if (metrics)
                for (std::string const& group : metrics->ExpectedActionGroups)
                {
                    if (!firstExpectedGroup)
                        json << ',';
                    firstExpectedGroup = false;
                    json << '\"' << JsonEscape(group) << '\"';
                }
            json << "],\"scheduled_damage_phases\":[";
            bool firstScheduledPhase = true;
            if (metrics)
                for (std::string const& phase : metrics->ScheduledDamagePhases)
                {
                    if (!firstScheduledPhase)
                        json << ',';
                    firstScheduledPhase = false;
                    json << '\"' << JsonEscape(phase) << '\"';
                }
            json << "],\"delivered_damage_phases\":[";
            bool firstDeliveredPhase = true;
            if (metrics)
                for (std::string const& phase : metrics->DeliveredDamagePhases)
                {
                    if (!firstDeliveredPhase)
                        json << ',';
                    firstDeliveredPhase = false;
                    json << '\"' << JsonEscape(phase) << '\"';
                }
            json << "],\"heal_target_counts\":{";
            bool firstHealTarget = true;
            if (metrics)
                for (auto const& [guid, count] : metrics->HealTargetCounts)
                {
                    if (!firstHealTarget)
                        json << ',';
                    firstHealTarget = false;
                    json << '\"' << guid << "\":" << count;
                }
            json << "},\"result_counts\":{";
            bool firstResult = true;
            if (metrics)
                for (auto const& [result, count] : metrics->ResultCounts)
                {
                    if (!firstResult)
                        json << ',';
                    firstResult = false;
                    json << '\"' << JsonEscape(result) << "\":" << count;
                }
            json << "},\"action_attempts\":[";
            bool firstAction = true;
            if (metrics)
                for (auto const& [spellId, count] : metrics->ActionAttempts)
                {
                    if (!firstAction)
                        json << ',';
                    firstAction = false;
                    SpellInfo const* info = spellId ? sSpellMgr->GetSpellInfo(spellId) : nullptr;
                    json << "{\"spell_id\":" << spellId
                         << ",\"spell_name\":\"" << JsonEscape(info ? info->SpellName : "None") << "\""
                         << ",\"count\":" << count << '}';
                }
            json << "],\"spell_damage\":[";
            bool firstSpell = true;
            if (metrics)
            {
                std::vector<std::pair<uint32, uint64>> spells(metrics->SpellDamage.begin(), metrics->SpellDamage.end());
                std::sort(spells.begin(), spells.end(), [](auto const& left, auto const& right) { return left.second > right.second; });
                for (auto const& [spellId, amount] : spells)
                {
                    if (!firstSpell)
                        json << ',';
                    firstSpell = false;
                    SpellInfo const* info = spellId ? sSpellMgr->GetSpellInfo(spellId) : nullptr;
                    json << "{\"spell_id\":" << spellId
                         << ",\"spell_name\":\"" << JsonEscape(info ? info->SpellName : "Melee") << "\""
                         << ",\"damage\":" << amount
                         << ",\"event_count\":" << metrics->SpellDamageEvents.at(spellId) << '}';
                }
            }
            json << "],\"primary_pet_spell_damage\":[";
            bool firstPetSpell = true;
            if (metrics)
            {
                std::vector<std::pair<uint32, uint64>> petSpells(
                    metrics->PrimaryPetSpellDamage.begin(), metrics->PrimaryPetSpellDamage.end());
                std::sort(petSpells.begin(), petSpells.end(),
                    [](auto const& left, auto const& right)
                    {
                        return left.second > right.second;
                    });
                for (auto const& [spellId, amount] : petSpells)
                {
                    if (!firstPetSpell)
                        json << ',';
                    firstPetSpell = false;
                    SpellInfo const* info = spellId
                        ? sSpellMgr->GetSpellInfo(spellId) : nullptr;
                    json << "{\"spell_id\":" << spellId
                         << ",\"spell_name\":\""
                         << JsonEscape(info ? info->SpellName : "Melee") << "\""
                         << ",\"damage\":" << amount
                         << ",\"event_count\":"
                         << metrics->PrimaryPetSpellDamageEvents.at(spellId) << '}';
                }
            }
            json << "],\"primary_pet_shadow_bite_events\":[";
            bool firstShadowBiteEvent = true;
            if (metrics)
                for (CalibrationMetrics::PrimaryPetShadowBiteEvent const& event
                    : metrics->PrimaryPetShadowBiteEvents)
                {
                    if (!firstShadowBiteEvent)
                        json << ',';
                    firstShadowBiteEvent = false;
                    json << "{\"elapsed_ms\":" << event.ElapsedMs
                         << ",\"measured_damage\":" << event.MeasuredDamage
                         << ",\"unmitigated_damage\":" << event.UnmitigatedDamage
                         << ",\"pet_spell_power\":" << event.PetSpellPower
                         << ",\"pet_spell_crit_pct\":" << event.PetSpellCritPct
                         << ",\"owner_cast_warlock_periodic_damage_aura_spell_ids\":[";
                    for (size_t index = 0;
                        index < event.OwnerCastWarlockPeriodicDamageAuraSpellIds.size();
                        ++index)
                    {
                        if (index)
                            json << ',';
                        json << event.OwnerCastWarlockPeriodicDamageAuraSpellIds[index];
                    }
                    json << "],\"owner_cast_warlock_periodic_damage_aura_count\":"
                         << event.OwnerCastWarlockPeriodicDamageAuraSpellIds.size() << '}';
                }
            json << "],\"decision_timeline\":[";
            bool firstTimeline = true;
            if (metrics)
                for (CalibrationMetrics::DecisionTimelineEntry const& entry : metrics->DecisionTimeline)
                {
                    if (!firstTimeline)
                        json << ',';
                    firstTimeline = false;
                    json << "{\"elapsed_ms\":" << entry.ElapsedMs
                         << ",\"spell_id\":" << entry.SpellId
                         << ",\"result\":\"" << JsonEscape(entry.Result) << "\""
                         << ",\"health\":" << entry.Health
                         << ",\"max_health\":" << entry.MaxHealth
                         << ",\"mana\":" << entry.Mana
                         << ",\"max_mana\":" << entry.MaxMana
                         << ",\"current_generic_spell_id\":" << entry.CurrentGenericSpellId
                         << ",\"current_channeled_spell_id\":" << entry.CurrentChanneledSpellId
                         << ",\"pet_health\":" << entry.PetHealth
                         << ",\"pet_max_health\":" << entry.PetMaxHealth
                         << ",\"pet_alive\":" << (entry.PetAlive ? "true" : "false")
                         << ",\"pet_victim_guid\":" << entry.PetVictimGuid
                         << ",\"pet_attacking\":" << (entry.PetAttacking ? "true" : "false")
                         << ",\"pet_command_state\":" << uint32(entry.PetCommandState)
                         << ",\"pet_command_attack\":"
                         << (entry.PetCommandAttack ? "true" : "false")
                         << ",\"pet_current_generic_spell_id\":"
                         << entry.PetCurrentGenericSpellId
                         << ",\"pet_current_channeled_spell_id\":"
                         << entry.PetCurrentChanneledSpellId
                         << ",\"pet_current_autorepeat_spell_id\":"
                         << entry.PetCurrentAutorepeatSpellId
                         << ",\"target_distance\":" << std::fixed << std::setprecision(3)
                         << entry.TargetDistance
                         << ",\"alive\":" << (entry.Alive ? "true" : "false") << '}';
                }
            json << "],\"off_target_damage_events\":[";
            bool firstOffTarget = true;
            if (metrics)
                for (CalibrationMetrics::OffTargetDamageEvent const& event : metrics->OffTargetDamageEvents)
                {
                    if (!firstOffTarget)
                        json << ',';
                    firstOffTarget = false;
                    json << "{\"elapsed_ms\":" << event.ElapsedMs
                         << ",\"attacker_guid\":" << event.AttackerGuid
                         << ",\"victim_guid\":" << event.VictimGuid
                         << ",\"victim_entry\":" << event.VictimEntry
                         << ",\"victim_type_id\":" << uint32(event.VictimTypeId)
                         << ",\"victim_is_owner\":" << (event.VictimIsOwner ? "true" : "false")
                         << ",\"spell_id\":" << event.SpellId
                         << ",\"current_generic_spell_id\":" << event.CurrentGenericSpellId
                         << ",\"current_channeled_spell_id\":" << event.CurrentChanneledSpellId
                         << ",\"damage\":" << event.Damage
                         << ",\"periodic_health_aura_candidates\":[";
                    bool firstAuraCandidate = true;
                    for (CalibrationMetrics::OffTargetDamageEvent::PeriodicHealthAuraCandidate const& candidate
                        : event.PeriodicHealthAuraCandidates)
                    {
                        if (!firstAuraCandidate)
                            json << ',';
                        firstAuraCandidate = false;
                        json << "{\"spell_id\":" << candidate.SpellId
                             << ",\"holder_guid\":" << candidate.HolderGuid
                             << ",\"caster_guid\":" << candidate.CasterGuid
                             << ",\"effect_index\":" << uint32(candidate.EffectIndex)
                             << ",\"aura_type\":" << candidate.AuraType << '}';
                    }
                    json << "]}";
                }
}
