#include "Bots/BotClassSpecActionProfile.h"
#include "Cryptography/CryptoHash.h"
#include "DataStores/DBCStores.h"
#include "DatabaseEnv.h"
#include "Bag.h"
#include "Item.h"
#include "Pet.h"
#include "Player.h"
#include "SpellAuras.h"
#include "Spell.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "Util.h"
#include "Creature.h"
#include "Group.h"
#include "DataStores/DBCEnums.h"
#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>

#include "Bots/BotClassSpecActionProfileInternal.h"

namespace
{
struct CanonicalRotationKey
{
    uint8 ClassId;
    char const* SpecTag;
    char const* Role;
};

std::array<CanonicalRotationKey, 31> const CanonicalRotationKeys = {{
    { 1, "protection_warrior", "tank" },
    { 2, "protection", "tank" },
    { 6, "blood_death_knight", "tank" },
    { 11, "feral_druid_tank", "tank" },
    { 2, "holy_paladin", "healer" },
    { 5, "discipline_priest", "healer" },
    { 5, "holy_priest", "healer" },
    { 7, "restoration_shaman", "healer" },
    { 11, "restoration_druid", "healer" },
    { 1, "arms_warrior", "dps" },
    { 1, "fury_warrior", "dps" },
    { 2, "retribution_paladin", "dps" },
    { 3, "beast_mastery_hunter", "dps" },
    { 3, "marksmanship", "dps" },
    { 3, "survival", "dps" },
    { 4, "assassination_rogue", "dps" },
    { 4, "combat_rogue", "dps" },
    { 4, "subtlety_rogue", "dps" },
    { 6, "frost_death_knight", "dps" },
    { 6, "unholy_death_knight", "dps" },
    { 7, "elemental_shaman", "dps" },
    { 7, "enhancement", "dps" },
    { 8, "arcane_mage", "dps" },
    { 8, "fire", "dps" },
    { 8, "frost_mage", "dps" },
    { 9, "affliction_warlock", "dps" },
    { 9, "demonology_warlock", "dps" },
    { 9, "destruction_warlock", "dps" },
    { 5, "shadow_priest", "dps" },
    { 11, "balance_druid", "dps" },
    { 11, "feral_druid_dps", "dps" }
}};

struct DbRotationSnapshot
{
    std::map<std::string, BotClassSpecActionProfile> Profiles;
    std::vector<std::string> Order;
    uint64 Generation = 0;
    std::string ContentHash;
};

std::mutex g_dbRotationMutex;
std::shared_ptr<DbRotationSnapshot const> g_activeDbRotationSnapshot;
std::shared_ptr<DbRotationSnapshot const> g_previousDbRotationSnapshot;
std::string g_dbRotationLastError;

std::set<std::string> CanonicalKeySet()
{
    std::set<std::string> keys;
    for (CanonicalRotationKey const& key : CanonicalRotationKeys)
        keys.insert(BotClassSpecActionProfileDetail::DbRotationKey(key.ClassId, key.SpecTag, key.Role));
    return keys;
}

std::string SnapshotPayload(DbRotationSnapshot const& snapshot)
{
    std::ostringstream payload;
    payload.precision(9);
    for (std::string const& key : snapshot.Order)
    {
        BotClassSpecActionProfile const& profile = snapshot.Profiles.at(key);
        payload << key << '|' << profile.ResourceType << '|' << profile.RangeBand << '|'
                << profile.MovementDirective << '|' << profile.AutoAttackMode << '|'
                << profile.MinRange << '|' << profile.MaxRange << '\n';
        for (BotActionProfileSpell const& spell : profile.Spells)
            payload << spell.SortOrder << '|' << spell.SpellId << '|'
                    << BotCombatActionCatalog::ToString(spell.Category) << '|' << spell.MechanicTags << '|'
                    << spell.DamageWeight << '|' << spell.HealingWeight << '|' << spell.ThreatWeight << '|'
                    << spell.MitigationWeight << '|' << spell.SurvivalWeight << '|' << spell.MovementWeight << '|'
                    << spell.ProgressionWeight << '|' << spell.ProfessionWeight << '|'
                    << uint32(spell.PriorityBucket) << '|' << uint32(spell.MinEnemies) << '|'
                    << uint32(spell.MaxEnemies) << '|' << spell.MinTargetHealthPct << '|'
                    << spell.MaxTargetHealthPct << '|' << spell.MinSelfHealthPct << '|'
                    << spell.MaxSelfHealthPct << '|' << spell.RequiredSelfAura << '|'
                    << spell.ForbiddenSelfAura << '|' << spell.RequiredTargetAura << '|'
                    << spell.ForbiddenTargetAura << '|' << spell.RequiresInterruptibleTarget << '|'
                    << spell.RequiresTargetNotVictim << '|' << spell.RequiresTargetVictim << '|'
                    << spell.RequiresMeleeRange << '|' << spell.RequiresRangedRange << '|'
                    << spell.TargetSelector << '|' << spell.MovementDirective << '|'
                    << spell.AutoAttackMode << '|' << spell.MinRange << '|' << spell.MaxRange << '|'
                    << spell.RequiresInstantCast << '|' << spell.MaxCastTimeMs << '|'
                    << spell.MaintainAuraId << '|' << spell.RefreshAuraBelowMs << '|'
                    << uint32(spell.MinInjuredPlayers) << '|' << uint32(spell.MaxInjuredPlayers) << '|'
                    << spell.InjuredHealthPct << '|' << spell.MinManaPct << '|' << spell.MaxManaPct << '|'
                    << uint32(spell.MinAttackers) << '|' << uint32(spell.MaxAttackers) << '|'
                    << spell.RequiresStationary << '|' << spell.RequiresMoving << '|'
                    << uint32(spell.RequiredSelfAuraStacks) << '|' << spell.MinPrimaryPowerPct << '|'
                    << spell.MaxPrimaryPowerPct << '|' << uint32(spell.MaxSelfAuraStacks) << '|'
                    << spell.MinSelfAuraRemainingMs << '|' << spell.MaxSelfAuraRemainingMs << '|'
                    << spell.RequiredOwnedTargetAura << '|' << spell.ForbiddenOwnedTargetAura << '|'
                    << uint32(spell.MinComboPoints) << '|' << uint32(spell.MaxComboPoints) << '|'
                    << uint32(spell.MinReadyRunes) << '|' << uint32(spell.RequiredShapeshiftForm) << '|'
                    << spell.RequiresPet << '|' << spell.ForbidsPet << '|'
                    << spell.RequiredMainHandEnchant << '|' << spell.RequiredOffHandEnchant << '|'
                    << spell.CooldownGroup << '|' << spell.TargetCreatureTypeMask << '|'
                    << spell.RequiresGroundTarget << '\n';
    }
    return payload.str();
}

std::string SnapshotHash(DbRotationSnapshot const& snapshot)
{
    return ByteArrayToHexStr(Trinity::Crypto::SHA256::GetDigestOf(SnapshotPayload(snapshot)));
}

std::shared_ptr<DbRotationSnapshot> LoadDbSnapshot(std::string& failureReason)
{
    std::set<std::string> const expectedKeys = CanonicalKeySet();
    std::shared_ptr<DbRotationSnapshot> snapshot = std::make_shared<DbRotationSnapshot>();
    QueryResult result = WorldDatabase.Query(
        "SELECT p.id, p.class_id, p.spec_tag, p.role, p.resource_type, p.range_band, p.version, "
        "p.movement_directive, p.auto_attack_mode, p.min_range, p.max_range, "
        "a.sort_order, a.spell_id, a.category, a.mechanic_tags, a.damage_weight, a.healing_weight, a.threat_weight, "
        "a.mitigation_weight, a.survival_weight, a.movement_weight, a.progression_weight, "
        "a.profession_weight, a.priority_bucket, a.min_enemies, a.max_enemies, "
        "a.min_target_health_pct, a.max_target_health_pct, a.min_self_health_pct, a.max_self_health_pct, "
        "a.required_self_aura, a.forbidden_self_aura, a.required_target_aura, a.forbidden_target_aura, "
        "a.requires_interruptible_target, a.requires_target_not_victim, a.requires_target_victim, "
        "a.requires_melee_range, a.requires_ranged_range, a.target_selector, a.movement_directive, "
        "a.auto_attack_mode, a.min_range, a.max_range, a.requires_instant_cast, a.max_cast_time_ms, "
        "a.maintain_aura_id, a.refresh_aura_below_ms, a.min_injured_players, a.max_injured_players, "
        "a.injured_health_pct, a.min_mana_pct, a.max_mana_pct, a.min_attackers, a.max_attackers, "
        "a.requires_stationary, a.requires_moving, a.required_self_aura_stacks, "
        "a.min_primary_power_pct, a.max_primary_power_pct, a.max_self_aura_stacks, "
        "a.min_self_aura_remaining_ms, a.max_self_aura_remaining_ms, "
        "a.required_owned_target_aura, a.forbidden_owned_target_aura, "
        "a.min_combo_points, a.max_combo_points, a.min_ready_runes, a.required_shapeshift_form, "
        "a.requires_pet, a.forbids_pet, a.required_main_hand_enchant, a.required_off_hand_enchant, "
        "a.cooldown_group, a.target_creature_type_mask, a.requires_ground_target "
        "FROM bot_rotation_profile p "
        "JOIN bot_rotation_action a ON a.profile_id = p.id "
        "WHERE p.enabled = 1 AND a.enabled = 1 "
        "ORDER BY p.class_id, p.spec_tag, p.role, a.priority_bucket, a.sort_order, a.id");
    if (!result)
    {
        failureReason = "no_enabled_rotation_profiles";
        return nullptr;
    }

    std::set<std::string> invalidReasons;
    std::map<std::string, uint32> profileIds;
    do
    {
        Field* fields = result->Fetch();
        uint32 profileId = fields[0].GetUInt32();
        uint8 classId = fields[1].GetUInt8();
        std::string specTag = BotClassSpecActionProfileDetail::CanonicalSpecTag(fields[2].GetString());
        std::string role = fields[3].GetString();
        std::string key = BotClassSpecActionProfileDetail::DbRotationKey(classId, specTag, role);
        if (!expectedKeys.count(key))
            continue;
        auto profileIdItr = profileIds.find(key);
        if (profileIdItr != profileIds.end() && profileIdItr->second != profileId)
        {
            invalidReasons.insert("duplicate_profile_" + key);
            continue;
        }
        profileIds[key] = profileId;

        auto [profileItr, inserted] = snapshot->Profiles.emplace(key, BotClassSpecActionProfile());
        BotClassSpecActionProfile& profile = profileItr->second;
        if (inserted)
        {
            profile.ClassId = classId;
            profile.SpecTag = specTag;
            profile.Role = role;
            profile.ResourceType = fields[4].GetString();
            profile.RangeBand = fields[5].GetString();
            profile.ProfileSource = "world_db_bot_rotation_profile_" + std::to_string(profileId) + "_v" + fields[6].GetString();
            profile.MovementDirective = fields[7].GetString();
            profile.AutoAttackMode = fields[8].GetString();
            profile.MinRange = fields[9].GetFloat();
            profile.MaxRange = fields[10].GetFloat();
            profile.MissingProfile = false;
            snapshot->Order.push_back(key);
            if (profile.MovementDirective.empty() || profile.AutoAttackMode.empty())
                invalidReasons.insert("missing_movement_directives_" + key);
        }

        uint32 spellId = fields[12].GetUInt32();
        SpellInfo const* spellInfo = spellId ? sSpellMgr->GetSpellInfo(spellId) : nullptr;
        if (spellId && !spellInfo)
        {
            invalidReasons.insert("invalid_spell_id_" + std::to_string(spellId));
            continue;
        }
        std::string categoryName = fields[13].GetString();
        BotCombatActionCategory category = BotCombatActionCatalog::CategoryFromString(categoryName);
        if (category == BotCombatActionCategory::Wait && categoryName != "wait")
        {
            invalidReasons.insert("invalid_category_" + categoryName);
            continue;
        }

        BotActionProfileSpell spell;
        spell.SortOrder = fields[11].GetUInt16();
        spell.SpellId = spellId;
        spell.Category = category;
        spell.MechanicTags = fields[14].GetString();
        spell.DamageWeight = fields[15].GetFloat();
        spell.HealingWeight = fields[16].GetFloat();
        spell.ThreatWeight = fields[17].GetFloat();
        spell.MitigationWeight = fields[18].GetFloat();
        spell.SurvivalWeight = fields[19].GetFloat();
        spell.MovementWeight = fields[20].GetFloat();
        spell.ProgressionWeight = fields[21].GetFloat();
        spell.ProfessionWeight = fields[22].GetFloat();
        spell.PriorityBucket = fields[23].GetUInt8();
        spell.MinEnemies = fields[24].GetUInt8();
        spell.MaxEnemies = fields[25].GetUInt8();
        spell.MinTargetHealthPct = fields[26].GetFloat();
        spell.MaxTargetHealthPct = fields[27].GetFloat();
        spell.MinSelfHealthPct = fields[28].GetFloat();
        spell.MaxSelfHealthPct = fields[29].GetFloat();
        spell.RequiredSelfAura = fields[30].GetUInt32();
        spell.ForbiddenSelfAura = fields[31].GetUInt32();
        spell.RequiredTargetAura = fields[32].GetUInt32();
        spell.ForbiddenTargetAura = fields[33].GetUInt32();
        spell.RequiresInterruptibleTarget = fields[34].GetBool();
        spell.RequiresTargetNotVictim = fields[35].GetBool();
        spell.RequiresTargetVictim = fields[36].GetBool();
        spell.RequiresMeleeRange = fields[37].GetBool();
        spell.RequiresRangedRange = fields[38].GetBool();
        spell.TargetSelector = fields[39].GetString();
        spell.MovementDirective = fields[40].GetString();
        spell.AutoAttackMode = fields[41].GetString();
        spell.MinRange = fields[42].GetFloat();
        spell.MaxRange = fields[43].GetFloat();
        spell.RequiresInstantCast = fields[44].GetBool();
        spell.MaxCastTimeMs = fields[45].GetUInt32();
        spell.MaintainAuraId = fields[46].GetUInt32();
        spell.RefreshAuraBelowMs = fields[47].GetUInt32();
        spell.MinInjuredPlayers = fields[48].GetUInt8();
        spell.MaxInjuredPlayers = fields[49].GetUInt8();
        spell.InjuredHealthPct = fields[50].GetFloat();
        spell.MinManaPct = fields[51].GetFloat();
        spell.MaxManaPct = fields[52].GetFloat();
        spell.MinAttackers = fields[53].GetUInt8();
        spell.MaxAttackers = fields[54].GetUInt8();
        spell.RequiresStationary = fields[55].GetBool();
        spell.RequiresMoving = fields[56].GetBool();
        spell.RequiredSelfAuraStacks = fields[57].GetUInt8();
        spell.MinPrimaryPowerPct = fields[58].GetFloat();
        spell.MaxPrimaryPowerPct = fields[59].GetFloat();
        spell.MaxSelfAuraStacks = fields[60].GetUInt8();
        spell.MinSelfAuraRemainingMs = fields[61].GetUInt32();
        spell.MaxSelfAuraRemainingMs = fields[62].GetUInt32();
        spell.RequiredOwnedTargetAura = fields[63].GetUInt32();
        spell.ForbiddenOwnedTargetAura = fields[64].GetUInt32();
        spell.MinComboPoints = fields[65].GetUInt8();
        spell.MaxComboPoints = fields[66].GetUInt8();
        spell.MinReadyRunes = fields[67].GetUInt8();
        spell.RequiredShapeshiftForm = fields[68].GetUInt8();
        spell.RequiresPet = fields[69].GetBool();
        spell.ForbidsPet = fields[70].GetBool();
        spell.RequiredMainHandEnchant = fields[71].GetUInt32();
        spell.RequiredOffHandEnchant = fields[72].GetUInt32();
        spell.CooldownGroup = fields[73].GetString();
        spell.TargetCreatureTypeMask = fields[74].GetUInt32();
        spell.RequiresGroundTarget = fields[75].GetBool();

        static std::set<std::string> const targetSelectors = {
            "enemy", "self", "party", "lowest_ally", "tank", "ground_enemy"
        };
        if (!targetSelectors.count(spell.TargetSelector))
            invalidReasons.insert("invalid_target_selector_" + spell.TargetSelector);
        if (spell.MinEnemies > spell.MaxEnemies && spell.MaxEnemies)
            invalidReasons.insert("invalid_enemy_range_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.MinTargetHealthPct > spell.MaxTargetHealthPct || spell.MinSelfHealthPct > spell.MaxSelfHealthPct)
            invalidReasons.insert("invalid_health_range_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.MinComboPoints > spell.MaxComboPoints && spell.MaxComboPoints)
            invalidReasons.insert("invalid_combo_range_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.MinManaPct > spell.MaxManaPct || spell.MinPrimaryPowerPct > spell.MaxPrimaryPowerPct)
            invalidReasons.insert("invalid_power_range_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.MinSelfAuraRemainingMs > spell.MaxSelfAuraRemainingMs && spell.MaxSelfAuraRemainingMs)
            invalidReasons.insert("invalid_aura_duration_range_" + key + "_" + std::to_string(spell.SortOrder));
        if ((spell.RequiredSelfAuraStacks || spell.MaxSelfAuraStacks || spell.MinSelfAuraRemainingMs || spell.MaxSelfAuraRemainingMs)
            && !spell.RequiredSelfAura)
            invalidReasons.insert("self_aura_gate_without_aura_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.RequiresPet && spell.ForbidsPet)
            invalidReasons.insert("contradictory_pet_gate_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.RequiresStationary && spell.RequiresMoving)
            invalidReasons.insert("contradictory_movement_gate_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.RequiresGroundTarget && (!spellInfo || !(spellInfo->GetExplicitTargetMask() & TARGET_FLAG_DEST_LOCATION)))
            invalidReasons.insert("invalid_ground_target_spell_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.TargetSelector == "ground_enemy" && !spell.RequiresGroundTarget)
            invalidReasons.insert("ground_selector_without_ground_gate_" + key + "_" + std::to_string(spell.SortOrder));
        std::array<uint32, 7> const predicateSpellIds = {{
            spell.RequiredSelfAura, spell.ForbiddenSelfAura, spell.RequiredTargetAura,
            spell.ForbiddenTargetAura, spell.MaintainAuraId, spell.RequiredOwnedTargetAura,
            spell.ForbiddenOwnedTargetAura
        }};
        for (uint32 predicateSpellId : predicateSpellIds)
            if (predicateSpellId && !sSpellMgr->GetSpellInfo(predicateSpellId))
                invalidReasons.insert("invalid_predicate_spell_id_" + std::to_string(predicateSpellId));
        profile.Spells.push_back(spell);
    } while (result->NextRow());

    for (CanonicalRotationKey const& expected : CanonicalRotationKeys)
    {
        std::string key = BotClassSpecActionProfileDetail::DbRotationKey(expected.ClassId, expected.SpecTag, expected.Role);
        auto itr = snapshot->Profiles.find(key);
        if (itr == snapshot->Profiles.end())
            invalidReasons.insert("missing_profile_" + key);
        else if (itr->second.Spells.empty())
            invalidReasons.insert("profile_without_actions_" + key);
    }
    if (!invalidReasons.empty() || snapshot->Profiles.size() != CanonicalRotationKeys.size())
    {
        std::ostringstream failure;
        bool first = true;
        for (std::string const& reason : invalidReasons)
        {
            if (!first)
                failure << ',';
            first = false;
            failure << reason;
        }
        failureReason = failure.str();
        return nullptr;
    }

    snapshot->ContentHash = SnapshotHash(*snapshot);
    return snapshot;
}

bool PublishDbSnapshot(std::shared_ptr<DbRotationSnapshot> snapshot, std::string& failureReason)
{
    if (!snapshot || snapshot->Profiles.size() != CanonicalRotationKeys.size() || snapshot->ContentHash.empty())
    {
        if (failureReason.empty())
            failureReason = "candidate_snapshot_incomplete";
        return false;
    }
    std::lock_guard<std::mutex> guard(g_dbRotationMutex);
    snapshot->Generation = g_activeDbRotationSnapshot ? g_activeDbRotationSnapshot->Generation + 1 : 1;
    for (auto& [key, profile] : snapshot->Profiles)
    {
        profile.SnapshotGeneration = snapshot->Generation;
        profile.SnapshotContentHash = snapshot->ContentHash;
    }
    g_previousDbRotationSnapshot = g_activeDbRotationSnapshot;
    g_activeDbRotationSnapshot = snapshot;
    g_dbRotationLastError.clear();
    return true;
}

bool EnsureDbSnapshotLoaded()
{
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        if (g_activeDbRotationSnapshot)
            return true;
    }
    std::string failureReason;
    std::shared_ptr<DbRotationSnapshot> snapshot = LoadDbSnapshot(failureReason);
    if (!PublishDbSnapshot(snapshot, failureReason))
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        g_dbRotationLastError = failureReason;
        return false;
    }
    return true;
}
}

namespace BotClassSpecActionProfileDetail
{
bool EnsureDbSnapshotLoaded()
{
    return ::EnsureDbSnapshotLoaded();
}

bool FindActiveDbProfile(uint8 classId, std::string const& specTag, std::string const& role,
    BotClassSpecActionProfile& profile)
{
    if (!EnsureDbSnapshotLoaded())
        return false;

    std::lock_guard<std::mutex> guard(g_dbRotationMutex);
    if (!g_activeDbRotationSnapshot)
        return false;

    auto itr = g_activeDbRotationSnapshot->Profiles.find(
        BotClassSpecActionProfileDetail::DbRotationKey(
            classId, BotClassSpecActionProfileDetail::CanonicalSpecTag(specTag), role));
    if (itr == g_activeDbRotationSnapshot->Profiles.end())
        return false;

    profile = itr->second;
    return true;
}
}

uint64 BotClassSpecActionProfileStore::ActiveDbGeneration()
{
    BotClassSpecActionProfileDetail::EnsureDbSnapshotLoaded();
    std::lock_guard<std::mutex> guard(g_dbRotationMutex);
    return g_activeDbRotationSnapshot ? g_activeDbRotationSnapshot->Generation : 0;
}

std::string BotClassSpecActionProfileStore::ActiveDbContentHash()
{
    BotClassSpecActionProfileDetail::EnsureDbSnapshotLoaded();
    std::lock_guard<std::mutex> guard(g_dbRotationMutex);
    return g_activeDbRotationSnapshot ? g_activeDbRotationSnapshot->ContentHash : "";
}

std::string BotClassSpecActionProfileStore::ReloadDbProfiles()
{
    std::string failureReason;
    std::shared_ptr<DbRotationSnapshot> candidate = LoadDbSnapshot(failureReason);
    bool ok = PublishDbSnapshot(candidate, failureReason);
    std::shared_ptr<DbRotationSnapshot const> active;
    if (!ok)
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        g_dbRotationLastError = failureReason;
        active = g_activeDbRotationSnapshot;
    }
    else
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        active = g_activeDbRotationSnapshot;
    }

    std::ostringstream json;
    json << "{\"ok\":" << (ok ? "true" : "false")
         << ",\"action\":\"botauto_rotations_reload\""
         << ",\"expected_profile_count\":" << CanonicalRotationKeys.size()
         << ",\"profile_count\":" << (active ? active->Profiles.size() : 0)
         << ",\"active_generation\":" << (active ? active->Generation : 0)
         << ",\"active_content_hash\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(active ? active->ContentHash : "") << "\""
         << ",\"failure_reason\":" << (failureReason.empty() ? "null" : ("\"" + BotClassSpecActionProfileDetail::ClassSpecProfileEscape(failureReason) + "\""))
         << "}";
    return json.str();
}

std::string BotClassSpecActionProfileStore::RollbackDbProfiles()
{
    std::shared_ptr<DbRotationSnapshot const> active;
    std::shared_ptr<DbRotationSnapshot const> previous;
    std::string failureReason;
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        if (!g_previousDbRotationSnapshot)
            failureReason = "previous_snapshot_unavailable";
        else
        {
            std::shared_ptr<DbRotationSnapshot> rollback = std::make_shared<DbRotationSnapshot>(*g_previousDbRotationSnapshot);
            rollback->Generation = g_activeDbRotationSnapshot ? g_activeDbRotationSnapshot->Generation + 1 : 1;
            for (auto& [key, profile] : rollback->Profiles)
            {
                profile.SnapshotGeneration = rollback->Generation;
                profile.SnapshotContentHash = rollback->ContentHash;
            }
            g_previousDbRotationSnapshot = g_activeDbRotationSnapshot;
            g_activeDbRotationSnapshot = rollback;
            g_dbRotationLastError.clear();
        }
        active = g_activeDbRotationSnapshot;
        previous = g_previousDbRotationSnapshot;
    }

    bool ok = failureReason.empty();
    std::ostringstream json;
    json << "{\"ok\":" << (ok ? "true" : "false")
         << ",\"action\":\"botauto_rotations_rollback\""
         << ",\"profile_count\":" << (active ? active->Profiles.size() : 0)
         << ",\"active_generation\":" << (active ? active->Generation : 0)
         << ",\"active_content_hash\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(active ? active->ContentHash : "") << "\""
         << ",\"previous_generation\":" << (previous ? previous->Generation : 0)
         << ",\"previous_content_hash\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(previous ? previous->ContentHash : "") << "\""
         << ",\"failure_reason\":" << (failureReason.empty() ? "null" : ("\"" + BotClassSpecActionProfileDetail::ClassSpecProfileEscape(failureReason) + "\""))
         << "}";
    return json.str();
}

std::string BotClassSpecActionProfileStore::DbProfilesJson()
{
    BotClassSpecActionProfileDetail::EnsureDbSnapshotLoaded();
    std::shared_ptr<DbRotationSnapshot const> active;
    std::shared_ptr<DbRotationSnapshot const> previous;
    std::string failureReason;
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        active = g_activeDbRotationSnapshot;
        previous = g_previousDbRotationSnapshot;
        failureReason = g_dbRotationLastError;
    }

    std::set<std::string> loaded;
    if (active)
        for (auto const& [key, profile] : active->Profiles)
            loaded.insert(key);

    std::ostringstream json;
    bool ok = active && active->Profiles.size() == CanonicalRotationKeys.size();
    json << "{\"ok\":" << (ok ? "true" : "false")
         << ",\"action\":\"botauto_rotations_list\""
         << ",\"load_mode\":\"immutable_full_catalog_snapshot\""
         << ",\"expected_profile_count\":" << CanonicalRotationKeys.size()
         << ",\"profile_count\":" << loaded.size()
         << ",\"active_generation\":" << (active ? active->Generation : 0)
         << ",\"active_content_hash\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(active ? active->ContentHash : "") << "\""
         << ",\"previous_generation\":" << (previous ? previous->Generation : 0)
         << ",\"previous_content_hash\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(previous ? previous->ContentHash : "") << "\""
         << ",\"failure_reason\":" << (failureReason.empty() ? "null" : ("\"" + BotClassSpecActionProfileDetail::ClassSpecProfileEscape(failureReason) + "\""))
         << ",\"missing_keys\":[";
    bool first = true;
    for (CanonicalRotationKey const& expected : CanonicalRotationKeys)
    {
        std::string key = BotClassSpecActionProfileDetail::DbRotationKey(expected.ClassId, expected.SpecTag, expected.Role);
        if (loaded.count(key))
            continue;
        if (!first)
            json << ',';
        first = false;
        json << '"' << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(key) << '"';
    }
    json << "],\"profiles\":[";
    first = true;
    if (active)
        for (std::string const& key : active->Order)
        {
            auto itr = active->Profiles.find(key);
            if (itr == active->Profiles.end())
                continue;
            if (!first)
                json << ',';
            first = false;
            BotClassSpecActionProfile const& profile = itr->second;
            json << "{\"class_id\":" << uint32(profile.ClassId)
                 << ",\"spec_tag\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(profile.SpecTag) << "\""
                 << ",\"role\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(profile.Role) << "\""
                 << ",\"range_band\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(profile.RangeBand) << "\""
                 << ",\"movement_directive\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(profile.MovementDirective) << "\""
                 << ",\"auto_attack_mode\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(profile.AutoAttackMode) << "\""
                 << ",\"profile_source\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(profile.ProfileSource) << "\""
                 << ",\"snapshot_generation\":" << profile.SnapshotGeneration
                 << ",\"snapshot_content_hash\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(profile.SnapshotContentHash) << "\""
                 << ",\"action_count\":" << profile.Spells.size() << "}";
        }
    json << "]}";
    return json.str();
}

std::string BotClassSpecActionProfileStore::DbProfileDumpJson(uint8 classId, std::string const& specTag, std::string const& role)
{
    BotClassSpecActionProfileDetail::EnsureDbSnapshotLoaded();
    std::shared_ptr<DbRotationSnapshot const> snapshot;
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        snapshot = g_activeDbRotationSnapshot;
    }

    std::string canonicalSpecTag = BotClassSpecActionProfileDetail::CanonicalSpecTag(specTag);
    auto itr = snapshot ? snapshot->Profiles.find(BotClassSpecActionProfileDetail::DbRotationKey(classId, canonicalSpecTag, role)) : std::map<std::string, BotClassSpecActionProfile>::const_iterator();
    if (!snapshot || itr == snapshot->Profiles.end())
    {
        std::ostringstream missing;
        missing << "{\"ok\":false,\"action\":\"botauto_rotations_dump\",\"failure_reason\":\"profile_not_found\""
                << ",\"class_id\":" << uint32(classId)
                << ",\"spec_tag\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(canonicalSpecTag) << "\""
                << ",\"role\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(role) << "\"}";
        return missing.str();
    }

    BotClassSpecActionProfile const& profile = itr->second;
    std::ostringstream json;
    json << "{\"ok\":true,\"action\":\"botauto_rotations_dump\""
         << ",\"dump_schema\":\"bot_db_rotation_profile_dump_v2\""
         << ",\"snapshot_generation\":" << snapshot->Generation
         << ",\"snapshot_content_hash\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(snapshot->ContentHash) << "\""
         << ",\"profile\":" << profile.EmbeddingJson()
         << ",\"actions\":[";
    bool first = true;
    for (BotActionProfileSpell const& spell : profile.Spells)
    {
        if (!first)
            json << ',';
        first = false;
        json << "{\"sort_order\":" << spell.SortOrder
             << ",\"spell_id\":" << spell.SpellId
             << ",\"category\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(BotCombatActionCatalog::ToString(spell.Category)) << "\""
             << ",\"tags\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(spell.MechanicTags) << "\""
             << ",\"target_selector\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(spell.TargetSelector) << "\""
             << ",\"movement_directive\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(spell.MovementDirective) << "\""
             << ",\"auto_attack_mode\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(spell.AutoAttackMode) << "\""
             << ",\"priority_bucket\":" << uint32(spell.PriorityBucket)
             << ",\"weights\":{\"damage\":" << spell.DamageWeight
             << ",\"healing\":" << spell.HealingWeight
             << ",\"threat\":" << spell.ThreatWeight
             << ",\"mitigation\":" << spell.MitigationWeight
             << ",\"survival\":" << spell.SurvivalWeight
             << ",\"movement\":" << spell.MovementWeight
             << ",\"progression\":" << spell.ProgressionWeight
             << ",\"profession\":" << spell.ProfessionWeight << "}"
             << ",\"gates\":{\"min_enemies\":" << uint32(spell.MinEnemies)
             << ",\"max_enemies\":" << uint32(spell.MaxEnemies)
             << ",\"min_target_health_pct\":" << spell.MinTargetHealthPct
             << ",\"max_target_health_pct\":" << spell.MaxTargetHealthPct
             << ",\"min_self_health_pct\":" << spell.MinSelfHealthPct
             << ",\"max_self_health_pct\":" << spell.MaxSelfHealthPct
             << ",\"required_self_aura\":" << spell.RequiredSelfAura
             << ",\"forbidden_self_aura\":" << spell.ForbiddenSelfAura
             << ",\"required_target_aura\":" << spell.RequiredTargetAura
             << ",\"forbidden_target_aura\":" << spell.ForbiddenTargetAura
             << ",\"requires_interruptible_target\":" << (spell.RequiresInterruptibleTarget ? "true" : "false")
             << ",\"requires_target_not_victim\":" << (spell.RequiresTargetNotVictim ? "true" : "false")
             << ",\"requires_target_victim\":" << (spell.RequiresTargetVictim ? "true" : "false")
             << ",\"requires_melee_range\":" << (spell.RequiresMeleeRange ? "true" : "false")
             << ",\"requires_ranged_range\":" << (spell.RequiresRangedRange ? "true" : "false")
             << ",\"min_range\":" << spell.MinRange
             << ",\"max_range\":" << spell.MaxRange
             << ",\"requires_instant_cast\":" << (spell.RequiresInstantCast ? "true" : "false")
             << ",\"max_cast_time_ms\":" << spell.MaxCastTimeMs
             << ",\"maintain_aura_id\":" << spell.MaintainAuraId
             << ",\"refresh_aura_below_ms\":" << spell.RefreshAuraBelowMs
             << ",\"min_injured_players\":" << uint32(spell.MinInjuredPlayers)
             << ",\"max_injured_players\":" << uint32(spell.MaxInjuredPlayers)
             << ",\"injured_health_pct\":" << spell.InjuredHealthPct
             << ",\"min_mana_pct\":" << spell.MinManaPct
             << ",\"max_mana_pct\":" << spell.MaxManaPct
             << ",\"min_primary_power_pct\":" << spell.MinPrimaryPowerPct
             << ",\"max_primary_power_pct\":" << spell.MaxPrimaryPowerPct
             << ",\"min_attackers\":" << uint32(spell.MinAttackers)
             << ",\"max_attackers\":" << uint32(spell.MaxAttackers)
             << ",\"requires_stationary\":" << (spell.RequiresStationary ? "true" : "false")
             << ",\"requires_moving\":" << (spell.RequiresMoving ? "true" : "false")
             << ",\"required_owned_target_aura\":" << spell.RequiredOwnedTargetAura
             << ",\"forbidden_owned_target_aura\":" << spell.ForbiddenOwnedTargetAura
             << ",\"required_self_aura_stacks\":" << uint32(spell.RequiredSelfAuraStacks)
             << ",\"max_self_aura_stacks\":" << uint32(spell.MaxSelfAuraStacks)
             << ",\"min_self_aura_remaining_ms\":" << spell.MinSelfAuraRemainingMs
             << ",\"max_self_aura_remaining_ms\":" << spell.MaxSelfAuraRemainingMs
             << ",\"min_combo_points\":" << uint32(spell.MinComboPoints)
             << ",\"max_combo_points\":" << uint32(spell.MaxComboPoints)
             << ",\"min_ready_runes\":" << uint32(spell.MinReadyRunes)
             << ",\"required_shapeshift_form\":" << uint32(spell.RequiredShapeshiftForm)
             << ",\"requires_pet\":" << (spell.RequiresPet ? "true" : "false")
             << ",\"forbids_pet\":" << (spell.ForbidsPet ? "true" : "false")
             << ",\"required_main_hand_enchant\":" << spell.RequiredMainHandEnchant
             << ",\"required_off_hand_enchant\":" << spell.RequiredOffHandEnchant
             << ",\"cooldown_group\":\"" << BotClassSpecActionProfileDetail::ClassSpecProfileEscape(spell.CooldownGroup) << "\""
             << ",\"target_creature_type_mask\":" << spell.TargetCreatureTypeMask
             << ",\"requires_ground_target\":" << (spell.RequiresGroundTarget ? "true" : "false")
             << "}}";
    }
    json << "]}";
    return json.str();
}
