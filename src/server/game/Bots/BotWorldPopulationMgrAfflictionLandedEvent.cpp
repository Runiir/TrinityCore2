#include "Bots/BotWorldPopulationMgr.h"

#include "Player.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <sstream>
#include <utility>

namespace
{
constexpr size_t MaxAfflictionLandedEvents = 2048;
constexpr size_t MaxAfflictionSoulburnDecisions = 2048;

bool IsAfflictionLandedEventSpell(uint32 spellId)
{
    switch (spellId)
    {
        case 172:   // Corruption.
        case 30108: // Unstable Affliction.
        case 48181: // Haunt.
        case 47897: // Shadowflame direct hit.
        case 47960: // Shadowflame periodic child.
        case 1120:  // Drain Soul.
        case 686:   // Shadow Bolt.
        case 54049: // Felhunter Shadow Bite.
            return true;
        default:
            return false;
    }
}

AuraEffect const* FindAffectingEffect(Aura const* aura,
    SpellInfo const* spellInfo)
{
    if (!aura || !spellInfo)
        return nullptr;
    for (uint8 effectIndex = 0; effectIndex < MAX_SPELL_EFFECTS; ++effectIndex)
        if (AuraEffect const* effect = aura->GetEffect(effectIndex))
            if (effect->IsAffectingSpell(spellInfo))
                return effect;
    return nullptr;
}

char const* BoolJson(bool value)
{
    return value ? "true" : "false";
}
}

void BotWorldPopulationMgr::ObserveAfflictionLandedEvent(
    CalibrationMetrics& metrics, Unit* attacker, Player* owner, Unit* victim,
    uint32 spellId, uint32 damage, uint32 unmitigatedDamage, uint32 damageType,
    bool critical, bool criticalOutcomeAvailable, float critChancePct,
    uint64 elapsedMs)
{
    if (!attacker || !owner || !victim || owner->getClass() != CLASS_WARLOCK
        || !IsAfflictionLandedEventSpell(spellId)
        || metrics.AfflictionLandedEvents.size() >= MaxAfflictionLandedEvents)
        return;

    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    if (!spellInfo)
        return;

    bool const periodic = damageType == uint32(DOT);
    CalibrationMetrics::AfflictionLandedEvent event;
    event.ElapsedMs = elapsedMs;
    event.ElapsedAvailable = true;
    event.EventSpellId = spellId;
    event.ActorGuid = attacker->GetGUID().GetCounter();
    event.ActorEntry = attacker->GetEntry();
    event.ActorTypeId = uint8(attacker->GetTypeId());
    event.OwnerGuid = owner->GetGUID().GetCounter();
    event.OwnerEntry = owner->GetEntry();
    event.OwnerTypeId = uint8(owner->GetTypeId());
    event.TargetGuid = victim->GetGUID().GetCounter();
    event.TargetEntry = victim->GetEntry();
    event.TargetTypeId = uint8(victim->GetTypeId());
    event.IsPeriodic = periodic;
    // The callback proves EventSpellId, but it carries no relationship to a
    // triggering root or child spell. Keep both attribution dimensions
    // unavailable instead of treating the current spell as a root/child.
    event.RawDamage = unmitigatedDamage;
    event.RawDamageAvailable = true;
    event.FinalDamage = damage;
    event.FinalDamageAvailable = true;
    event.MeasuredDamage = damage ? damage : unmitigatedDamage;
    event.MeasuredDamageAvailable = true;
    event.Critical = critical;
    event.CriticalOutcomeAvailable = criticalOutcomeAvailable;
    event.CritChancePct = critChancePct;
    event.CritChanceAvailable = criticalOutcomeAvailable;
    event.ScoringStartPlayerStatsAvailable =
        metrics.ScoringStartPlayerStats.Observed;

    DamageEffectType const effectType = periodic ? DOT : SPELL_DIRECT_DAMAGE;
    event.ActorSpellPower = attacker->SpellBaseDamageBonusDone(
        spellInfo->GetSchoolMask(), true);
    event.ActorSpellCritPct = attacker->SpellCritChanceDone(
        spellInfo, spellInfo->GetSchoolMask(), spellInfo->GetAttackType(),
        periodic);
    event.ActorStatSnapshotAvailable = true;
    event.ActorDamagePctDonePpm = int32(std::max(0.0f,
        attacker->SpellDamagePctDone(victim, spellInfo, effectType))
        * 1000000.0f);
    event.TargetTakenMultiplierPpm = std::max(0,
        victim->SpellDamageBonusTaken(attacker, spellInfo, 1000000,
            effectType));
    event.ModifierSnapshotAvailable = true;

    Aura const* shadowMastery = owner->GetAura(87339);
    Aura const* potentAfflictions = owner->GetAura(77215);
    Aura const* haunt = victim->GetAura(48181, owner->GetGUID());
    Aura const* shadowEmbrace = victim->GetAura(32389, owner->GetGUID());
    Aura const* shadowEmbraceCaster = owner->GetAura(32392, owner->GetGUID());
    event.AuraSnapshotAvailable = true;
    event.ShadowMasteryActive = shadowMastery != nullptr;
    event.PotentAfflictionsActive = potentAfflictions != nullptr;
    event.HauntActive = haunt != nullptr;
    event.ShadowEmbraceActive = shadowEmbrace != nullptr;
    event.ShadowEmbraceCasterActive = shadowEmbraceCaster != nullptr;
    event.ShadowEmbraceStacks = shadowEmbrace
        ? shadowEmbrace->GetStackAmount() : 0;
    event.ShadowEmbraceCasterStacks = shadowEmbraceCaster
        ? shadowEmbraceCaster->GetStackAmount() : 0;
    if (AuraEffect const* effect = FindAffectingEffect(haunt, spellInfo))
        event.HauntModifierAmount = effect->GetAmount();
    if (AuraEffect const* effect = FindAffectingEffect(shadowEmbrace,
        spellInfo))
    {
        event.ShadowEmbraceModifierAmount = effect->GetAmount();
        if (shadowEmbrace->GetStackAmount())
            event.ShadowEmbraceStacks = shadowEmbrace->GetStackAmount();
    }

    // NotifyCombatDamage has no proc-owner/event argument. Do not infer a
    // proc from a live aura or from a damage amount.
    event.ProcSnapshotAvailable = false;
    metrics.AfflictionLandedEvents.push_back(event);
}

void BotWorldPopulationMgr::ObserveAfflictionSoulburnDecision(
    CalibrationMetrics& metrics, Player* bot, uint32 chosenSpellId,
    uint32 soulburnPowerBefore, uint32 soulburnPowerAfter, char const* result,
    std::string const& candidateRejectionsJson, uint64 elapsedMs)
{
    if (!bot || bot->getClass() != CLASS_WARLOCK
        || metrics.AfflictionSoulburnDecisions.size()
            >= MaxAfflictionSoulburnDecisions)
        return;

    bool const soulburnSelected = chosenSpellId == 74434;
    bool const soulFireSelected = chosenSpellId == 6353;
    bool const soulburnCandidateObserved = candidateRejectionsJson.find(
        "\"spell_id\":74434") != std::string::npos;
    bool const soulFireCandidateObserved = candidateRejectionsJson.find(
        "\"spell_id\":6353") != std::string::npos;
    if (!soulburnSelected && !soulFireSelected
        && !soulburnCandidateObserved && !soulFireCandidateObserved)
        return;

    CalibrationMetrics::AfflictionSoulburnDecision event;
    event.ElapsedMs = elapsedMs;
    event.ChosenSpellId = chosenSpellId;
    event.SoulburnPowerBefore = soulburnPowerBefore;
    event.SoulburnPowerAfter = soulburnPowerAfter;
    event.SoulburnPowerAvailable = bot->GetMaxPower(POWER_SOUL_SHARDS) > 0;
    event.SoulburnPowerChanged = soulburnPowerBefore != soulburnPowerAfter;
    event.CandidateObservationAvailable = !candidateRejectionsJson.empty();
    event.Result = result ? result : "unknown";
    event.CandidateRejectionsJson = candidateRejectionsJson.empty()
        ? "[]" : candidateRejectionsJson;
    metrics.AfflictionSoulburnDecisions.push_back(std::move(event));
}

std::string BotWorldPopulationMgr::AppendAfflictionLandedEventJson(
    CalibrationMetrics const* metrics)
{
    std::ostringstream json;
    json << ",\"affliction_landed_events\":[";
    bool first = true;
    if (metrics)
        for (CalibrationMetrics::AfflictionLandedEvent const& event
            : metrics->AfflictionLandedEvents)
        {
            if (!first)
                json << ',';
            first = false;
            json << "{\"elapsed_ms\":" << event.ElapsedMs
                 << ",\"elapsed_available\":" << BoolJson(event.ElapsedAvailable)
                 << ",\"event_spell_id\":" << event.EventSpellId
                 << ",\"actor_guid\":" << event.ActorGuid
                 << ",\"actor_entry\":" << event.ActorEntry
                 << ",\"actor_type_id\":" << uint32(event.ActorTypeId)
                 << ",\"owner_guid\":" << event.OwnerGuid
                 << ",\"owner_entry\":" << event.OwnerEntry
                 << ",\"owner_type_id\":" << uint32(event.OwnerTypeId)
                 << ",\"target_guid\":" << event.TargetGuid
                 << ",\"target_entry\":" << event.TargetEntry
                 << ",\"target_type_id\":" << uint32(event.TargetTypeId)
                 << ",\"root_spell_id\":" << event.RootSpellId
                 << ",\"root_spell_identity_available\":"
                 << BoolJson(event.RootSpellIdentityAvailable)
                 << ",\"child_spell_id\":" << event.ChildSpellId
                 << ",\"child_spell_identity_available\":"
                 << BoolJson(event.ChildSpellIdentityAvailable)
                 << ",\"is_periodic\":" << BoolJson(event.IsPeriodic)
                 << ",\"raw_damage\":" << event.RawDamage
                 << ",\"raw_damage_available\":"
                 << BoolJson(event.RawDamageAvailable)
                 << ",\"final_damage\":" << event.FinalDamage
                 << ",\"final_damage_available\":"
                 << BoolJson(event.FinalDamageAvailable)
                 << ",\"measured_damage\":" << event.MeasuredDamage
                 << ",\"measured_damage_available\":"
                 << BoolJson(event.MeasuredDamageAvailable)
                 << ",\"critical\":" << BoolJson(event.Critical)
                 << ",\"critical_outcome_available\":"
                 << BoolJson(event.CriticalOutcomeAvailable)
                 << ",\"crit_chance_pct\":" << event.CritChancePct
                 << ",\"crit_chance_available\":"
                 << BoolJson(event.CritChanceAvailable)
                 << ",\"actor_spell_power\":" << event.ActorSpellPower
                 << ",\"actor_spell_crit_pct\":" << event.ActorSpellCritPct
                 << ",\"actor_stat_snapshot_available\":"
                 << BoolJson(event.ActorStatSnapshotAvailable)
                 << ",\"scoring_start_player_stats_available\":"
                 << BoolJson(event.ScoringStartPlayerStatsAvailable)
                 << ",\"actor_damage_pct_done_ppm\":"
                 << event.ActorDamagePctDonePpm
                 << ",\"target_taken_multiplier_ppm\":"
                 << event.TargetTakenMultiplierPpm
                 << ",\"modifier_snapshot_available\":"
                 << BoolJson(event.ModifierSnapshotAvailable)
                 << ",\"aura_snapshot_available\":"
                 << BoolJson(event.AuraSnapshotAvailable)
                 << ",\"shadow_mastery_active\":"
                 << BoolJson(event.ShadowMasteryActive)
                 << ",\"potent_afflictions_active\":"
                 << BoolJson(event.PotentAfflictionsActive)
                 << ",\"haunt_active\":" << BoolJson(event.HauntActive)
                 << ",\"haunt_modifier_amount\":"
                 << event.HauntModifierAmount
                 << ",\"shadow_embrace_active\":"
                 << BoolJson(event.ShadowEmbraceActive)
                 << ",\"shadow_embrace_stacks\":"
                 << uint32(event.ShadowEmbraceStacks)
                 << ",\"shadow_embrace_modifier_amount\":"
                 << event.ShadowEmbraceModifierAmount
                 << ",\"shadow_embrace_caster_active\":"
                 << BoolJson(event.ShadowEmbraceCasterActive)
                 << ",\"shadow_embrace_caster_stacks\":"
                 << uint32(event.ShadowEmbraceCasterStacks)
                 << ",\"proc_snapshot_available\":"
                 << BoolJson(event.ProcSnapshotAvailable) << '}';
        }
    json << "],\"affliction_landed_event_telemetry\":{"
         << "\"schema\":\"trinity_affliction_landed_event_v1\""
         << ",\"max_records\":" << MaxAfflictionLandedEvents
         << ",\"identity_limitation\":"
            "\"native_damage_callback_proves_only_the_current_event_spell\""
         << ",\"direct_critical_outcome_available\":false"
         << ",\"periodic_critical_outcome_basis\":"
            "\"matched_pending_periodic_outcome\""
         << ",\"proc_snapshot_available\":false"
         << ",\"proc_snapshot_limitation\":"
            "\"native_damage_callback_has_no_attributable_proc_context\""
         << "},\"affliction_soulburn_decisions\":[";
    first = true;
    if (metrics)
        for (CalibrationMetrics::AfflictionSoulburnDecision const& event
            : metrics->AfflictionSoulburnDecisions)
        {
            if (!first)
                json << ',';
            first = false;
            json << "{\"elapsed_ms\":" << event.ElapsedMs
                 << ",\"chosen_spell_id\":" << event.ChosenSpellId
                 << ",\"soulburn_power_before\":"
                 << event.SoulburnPowerBefore
                 << ",\"soulburn_power_after\":"
                 << event.SoulburnPowerAfter
                 << ",\"soulburn_power_available\":"
                 << BoolJson(event.SoulburnPowerAvailable)
                 << ",\"soulburn_power_changed\":"
                 << BoolJson(event.SoulburnPowerChanged)
                 << ",\"candidate_observation_available\":"
                 << BoolJson(event.CandidateObservationAvailable)
                 << ",\"result\":\"" << JsonEscape(event.Result)
                 << "\",\"candidate_rejections\":"
                 << event.CandidateRejectionsJson << '}';
        }
    json << ']';
    return json.str();
}
