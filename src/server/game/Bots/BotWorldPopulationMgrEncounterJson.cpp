#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotEncounterMechanicCatalog.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

#include <algorithm>
#include <sstream>

namespace
{
bool SpellLooksLikeHeal(SpellInfo const* spellInfo)
{
    return spellInfo && (spellInfo->HasEffect(SPELL_EFFECT_HEAL)
        || spellInfo->HasEffect(SPELL_EFFECT_HEAL_PCT)
        || spellInfo->HasEffect(SPELL_EFFECT_HEAL_MECHANICAL));
}

bool SpellLooksDangerous(SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;

    return spellInfo->HasEffect(SPELL_EFFECT_SCHOOL_DAMAGE)
        || spellInfo->HasEffect(SPELL_EFFECT_WEAPON_DAMAGE)
        || spellInfo->HasEffect(SPELL_EFFECT_WEAPON_DAMAGE_NOSCHOOL)
        || spellInfo->HasEffect(SPELL_EFFECT_NORMALIZED_WEAPON_DMG)
        || spellInfo->HasEffect(SPELL_EFFECT_WEAPON_PERCENT_DAMAGE)
        || spellInfo->HasEffect(SPELL_EFFECT_POWER_DRAIN)
        || spellInfo->HasEffect(SPELL_EFFECT_HEALTH_LEECH);
}

std::string BuildSpellTagJson(SpellInfo const* spellInfo, bool mustInterrupt, bool groundDanger, bool tankSpike, bool raidDamage, bool adds)
{
    std::ostringstream tags;
    tags << "[";
    bool first = true;
    auto addTag = [&tags, &first](char const* tag)
    {
        if (!first)
            tags << ",";
        tags << "\"" << tag << "\"";
        first = false;
    };

    if (SpellLooksDangerous(spellInfo))
        addTag("direct_damage");
    if (groundDanger)
    {
        addTag("ground_effect");
        addTag("move_out");
    }
    if (mustInterrupt)
        addTag("must_interrupt");
    if (tankSpike)
        addTag("tank_spike");
    if (raidDamage)
        addTag("raid_damage");
    if (adds)
        addTag("add_wave");
    if (SpellLooksLikeHeal(spellInfo))
        addTag("boss_heal");

    tags << "]";
    return tags.str();
}
}

std::string BotWorldPopulationMgr::BuildDungeonTrashPackJson(DungeonTrashPackFeatures const& pack) const
{
    std::ostringstream json;
    json << "{\"pack_size\":" << pack.PackSize
         << ",\"mechanic_families\":[\"trash_pack\""
         << (pack.CasterCount ? ",\"caster_pack\"" : "")
         << (pack.HealerCount ? ",\"healer_mob\"" : "")
         << (pack.PatrolNearby ? ",\"patrol_risk\"" : "")
         << (pack.InterruptPriority > 0.0f ? ",\"interrupt_required\"" : "")
         << (pack.AoeValue > 0.5f ? ",\"cleave_risk\"" : "") << "]"
         << ",\"elite_count\":" << pack.EliteCount
         << ",\"caster_count\":" << pack.CasterCount
         << ",\"healer_count\":" << pack.HealerCount
         << ",\"active_casts\":" << pack.ActiveCasts
         << ",\"dangerous_casts\":" << pack.DangerousCasts
         << ",\"interrupt_priority\":" << pack.InterruptPriority
         << ",\"aoe_value\":" << pack.AoeValue
         << ",\"cc_value\":" << pack.CcValue
         << ",\"pull_risk\":" << pack.PullRisk
         << ",\"patrol_nearby\":" << (pack.PatrolNearby ? "true" : "false")
         << ",\"tank_threat\":" << pack.TankThreat
         << ",\"party_average_hp_pct\":" << pack.PartyAverageHpPct
         << ",\"lowest_ally_hp_pct\":" << pack.LowestAllyHpPct
         << ",\"healer_mana_pct\":" << pack.HealerManaPct
         << ",\"priority_target_guid\":" << pack.PriorityTargetGuid.GetCounter()
         << ",\"priority_target_entry\":" << pack.PriorityTargetEntry
         << ",\"priority_spell_id\":" << pack.PrioritySpellId << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildBossMechanicsJson(BossMechanicFeatures const& features) const
{
    SpellInfo const* spellInfo = features.CastSpellId ? sSpellMgr->GetSpellInfo(features.CastSpellId) : nullptr;
    BotEncounterMechanicEmbedding mechanic = BotEncounterMechanicCatalog::Classify(nullptr, nullptr, spellInfo, features.DangerScore, features.MustInterrupt, features.GroundDanger, features.TankSpike, features.RaidDamage, features.AddsActive);
    mechanic.SourceEntry = features.BossEntry;
    std::ostringstream json;
    json << "{\"encounter_type\":\"" << (features.RaidEncounter ? "raid_boss" : "dungeon_boss") << "\""
         << ",\"mechanic_embedding\":" << mechanic.ToJson()
         << ",\"mechanic_family\":\"" << JsonEscape(BotEncounterMechanicCatalog::ToString(mechanic.Family)) << "\""
         << ",\"boss_present\":" << (features.BossPresent ? "true" : "false")
         << ",\"boss_guid\":" << features.BossGuid.GetCounter()
         << ",\"boss_entry\":" << features.BossEntry
         << ",\"phase\":0"
         << ",\"boss_casting\":" << (features.BossCasting ? "true" : "false")
         << ",\"cast_spell_id\":" << features.CastSpellId
         << ",\"cast_remaining_ms\":" << features.CastRemainingMs
         << ",\"spell_tags\":" << BuildSpellTagJson(spellInfo, features.MustInterrupt, features.GroundDanger, features.TankSpike, features.RaidDamage, features.AddsActive)
         << ",\"dangerous_cast\":" << (features.DangerousCast ? "true" : "false")
         << ",\"requires_interrupt\":" << (features.MustInterrupt ? "true" : "false")
         << ",\"interrupt_priority\":" << features.InterruptPriority
         << ",\"ground_danger_near_me\":" << (features.GroundDanger ? features.DangerScore : 0.0f)
         << ",\"safe_position_available\":true"
         << ",\"move_out\":" << (features.MoveOut ? "true" : "false")
         << ",\"tank_spike\":" << (features.TankSpike ? "true" : "false")
         << ",\"raid_damage\":" << (features.RaidDamage ? "true" : "false")
         << ",\"adds_active\":" << (features.AddsActive ? "true" : "false")
         << ",\"add_count\":" << features.AddCount
         << ",\"priority_add_guid\":" << features.PriorityAddGuid.GetCounter()
         << ",\"interactable_observed\":" << (features.InteractableObserved ? "true" : "false")
         << ",\"interactable_count\":" << features.InteractableCount
         << ",\"interactable_guid\":" << features.InteractableGuid.GetCounter()
         << ",\"vehicle_observed\":" << (features.VehicleObserved ? "true" : "false")
         << ",\"vehicle_count\":" << features.VehicleCount
         << ",\"vehicle_guid\":" << features.VehicleGuid.GetCounter()
         << ",\"transport_observed\":" << (features.TransportObserved ? "true" : "false")
         << ",\"transport_guid\":" << features.TransportGuid.GetCounter()
         << ",\"platform_transfer_observed\":" << (features.PlatformTransferObserved ? "true" : "false")
         << ",\"requires_stack\":" << (features.StackPlaceholder ? "true" : "false")
         << ",\"requires_spread\":" << (features.SpreadPlaceholder ? "true" : "false")
         << ",\"tank_swap_pressure\":" << (features.TankSpike ? std::max(0.0f, 1.0f - features.TankHpPct) : 0.0f)
         << ",\"party\":{\"tank_hp_pct\":" << features.TankHpPct
         << ",\"party_average_hp_pct\":" << features.PartyAverageHpPct
         << ",\"lowest_ally_hp_pct\":" << features.LowestAllyHpPct
         << ",\"healer_mana_pct\":" << features.HealerManaPct << "}"
         << ",\"danger_score\":" << features.DangerScore << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildRaidRoleAssignmentJson(RaidRoleAssignment const& assignment) const
{
    std::ostringstream json;
    json << "{\"role\":\"" << JsonEscape(assignment.Role) << "\""
         << ",\"roster_slot_id\":\"" << JsonEscape(assignment.RosterSlotId) << "\""
         << ",\"lease_role_slot\":\"" << JsonEscape(assignment.LeaseRoleSlot) << "\""
         << ",\"class_spec\":\"" << JsonEscape(assignment.ClassSpec) << "\""
         << ",\"average_item_level\":" << assignment.AverageItemLevel
         << ",\"subgroup\":" << uint32(assignment.SubGroup)
         << ",\"raid_size\":" << assignment.RaidSize
         << ",\"tank_count\":" << assignment.TankCount
         << ",\"healer_count\":" << assignment.HealerCount
         << ",\"dps_count\":" << assignment.DpsCount
         << ",\"role_index\":" << assignment.RoleIndex
         << ",\"main_tank_guid\":" << assignment.MainTankGuid.GetCounter()
         << ",\"off_tank_guid\":" << assignment.OffTankGuid.GetCounter()
         << ",\"raid_leader_guid\":" << assignment.RaidLeaderGuid.GetCounter() << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildRaidPositioningAnchorsJson(RaidPositioningAnchors const& anchors) const
{
    std::ostringstream json;
    json << "{\"active\":" << (anchors.Active ? "true" : "false")
         << ",\"anchor_type\":\"" << JsonEscape(anchors.AnchorType) << "\""
         << ",\"anchor_guid\":" << anchors.AnchorGuid.GetCounter()
         << ",\"anchor\":{\"x\":" << anchors.AnchorX << ",\"y\":" << anchors.AnchorY << ",\"z\":" << anchors.AnchorZ << "}"
         << ",\"stack_anchor\":{\"x\":" << anchors.StackX << ",\"y\":" << anchors.StackY << ",\"z\":" << anchors.StackZ << "}"
         << ",\"spread_anchor\":{\"x\":" << anchors.SpreadX << ",\"y\":" << anchors.SpreadY << ",\"z\":" << anchors.SpreadZ << "}"
         << ",\"formation_family\":\"" << JsonEscape(anchors.FormationFamily) << "\""
         << ",\"resolved_anchor\":{\"x\":" << anchors.ResolvedX << ",\"y\":" << anchors.ResolvedY << ",\"z\":" << anchors.ResolvedZ << "}"
         << ",\"arrival_tolerance_yards\":" << anchors.ArrivalToleranceYards
         << ",\"distance_to_anchor\":" << anchors.DistanceToAnchor << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildRaidMechanicAdapterJson(RaidMechanicAdapter const& adapter) const
{
    std::ostringstream json;
    json << "{\"mechanic_family\":\"" << JsonEscape(adapter.MechanicFamily) << "\""
         << ",\"assignment_type\":\"" << JsonEscape(adapter.AssignmentType) << "\""
         << ",\"recommended_action\":\"" << JsonEscape(adapter.RecommendedAction) << "\""
         << ",\"contract_id\":\"" << JsonEscape(adapter.ContractId) << "\""
         << ",\"contract_resolved\":" << (adapter.ContractResolved ? "true" : "false")
         << ",\"formation_family\":\"" << JsonEscape(adapter.FormationFamily) << "\""
         << ",\"swap_trigger\":\"" << JsonEscape(adapter.SwapTrigger) << "\""
         << ",\"target_control\":\"" << JsonEscape(adapter.TargetControl) << "\""
         << ",\"allow_area_damage\":" << (adapter.AllowAreaDamage ? "true" : "false")
         << ",\"controlled_aoe_minimum_targets\":" << adapter.ControlledAoeMinimumTargets
         << ",\"kill_sync_tolerance_pct\":" << adapter.KillSyncTolerancePct
         << ",\"kill_sync_execution_floor_pct\":" << adapter.KillSyncExecutionFloorPct
         << ",\"rotation_directive\":\"" << JsonEscape(adapter.RotationDirective) << "\""
         << ",\"heal_directive\":\"" << JsonEscape(adapter.HealDirective) << "\""
         << ",\"soak_directive\":\"" << JsonEscape(adapter.SoakDirective) << "\""
         << ",\"cooldown_directive\":\"" << JsonEscape(adapter.CooldownDirective) << "\""
         << ",\"battle_res_directive\":\"" << JsonEscape(adapter.BattleResDirective) << "\""
         << ",\"interactable_directive\":\"" << JsonEscape(adapter.InteractableDirective) << "\""
         << ",\"vehicle_directive\":\"" << JsonEscape(adapter.VehicleDirective) << "\""
         << ",\"transport_directive\":\"" << JsonEscape(adapter.TransportDirective) << "\""
         << ",\"platform_transfer_directive\":\"" << JsonEscape(adapter.PlatformTransferDirective) << "\""
         << ",\"assigned_target_guid\":" << adapter.AssignedTargetGuid.GetCounter()
         << ",\"evidence_guid\":" << adapter.EvidenceGuid.GetCounter()
         << ",\"trigger_spell_id\":" << adapter.TriggerSpellId
         << ",\"priority\":" << adapter.Priority
         << ",\"heroic_only\":" << (adapter.HeroicOnly ? "true" : "false")
         << ",\"assignment_observed\":" << (adapter.AssignmentObserved ? "true" : "false")
         << ",\"evidence_observed\":" << (adapter.EvidenceObserved ? "true" : "false") << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildRaidGearTargetPlanJson(RaidGearTargetPlan const& plan) const
{
    std::ostringstream json;
    json << "{\"current_item_level\":" << plan.CurrentItemLevel
         << ",\"target_item_level\":" << plan.TargetItemLevel
         << ",\"needed_item_level\":" << plan.NeededItemLevel
         << ",\"recommended_activity\":\"" << JsonEscape(plan.RecommendedActivity) << "\""
         << ",\"ready_for_raid\":" << (plan.ReadyForRaid ? "true" : "false")
         << ",\"ready_for_heroic_raid\":" << (plan.ReadyForHeroicRaid ? "true" : "false") << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildHeroicRaidProgressionJson(HeroicRaidProgression const& progression) const
{
    std::ostringstream json;
    json << "{\"tracking_enabled\":" << (progression.TrackingEnabled ? "true" : "false")
         << ",\"heroic_eligible\":" << (progression.HeroicEligible ? "true" : "false")
         << ",\"stage\":\"" << JsonEscape(progression.Stage) << "\""
         << ",\"raid_attempts\":" << progression.RaidAttempts
         << ",\"raid_boss_kills\":" << progression.RaidBossKills
         << ",\"heroic_raid_boss_kills\":" << progression.HeroicRaidBossKills
         << ",\"wipes\":" << progression.Wipes
         << ",\"role_power_score\":" << progression.RolePowerScore
         << ",\"target_item_level\":" << progression.TargetItemLevel << "}";
    return json.str();
}

