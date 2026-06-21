#include "Bots/BotClassSpecActionProfile.h"
#include "DatabaseEnv.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "Creature.h"
#include "DataStores/DBCEnums.h"
#include <algorithm>
#include <cstdlib>
#include <map>
#include <mutex>
#include <set>
#include <sstream>

namespace
{
std::string ClassSpecProfileEscape(std::string const& value)
{
    std::ostringstream out;
    for (char c : value)
    {
        if (c == '\\' || c == '"')
            out << '\\';
        out << c;
    }
    return out.str();
}

char const* PowerName(Powers power)
{
    switch (power)
    {
        case POWER_RAGE: return "rage";
        case POWER_FOCUS: return "focus";
        case POWER_ENERGY: return "energy";
        case POWER_RUNIC_POWER: return "runic_power";
        default: return "mana";
    }
}

struct DbRotationCache
{
    std::map<std::string, BotClassSpecActionProfile> Profiles;
    std::vector<std::string> Order;
    std::set<std::string> RequestedKeys;
    std::string LastError;
};

std::mutex g_dbRotationMutex;
DbRotationCache g_dbRotationCache;

std::string DbRotationKey(uint8 classId, std::string const& specTag, std::string const& role)
{
    std::ostringstream key;
    key << uint32(classId) << ":" << specTag << ":" << role;
    return key.str();
}

bool HasAny(Player const* bot, std::vector<uint32> const& ids)
{
    if (!bot)
        return false;
    for (uint32 id : ids)
        if (bot->HasSpell(id))
            return true;
    return false;
}

std::string InferSpecTag(Player const* bot, std::string const& role)
{
    if (!bot)
        return "generic";

    switch (bot->getClass())
    {
        case CLASS_MAGE:
            return HasAny(bot, {44457, 11366, 31661}) ? "fire" : "mage_generic";
        case CLASS_PRIEST:
            return role == "healer" ? "holy_priest" : "priest_generic";
        case CLASS_SHAMAN:
            return role == "healer" ? "restoration_shaman" : (HasAny(bot, {17364, 60103}) ? "enhancement" : "shaman_generic");
        case CLASS_PALADIN:
            return role == "tank" ? "protection" : (role == "healer" ? "holy_paladin" : "paladin_generic");
        case CLASS_HUNTER:
            return HasAny(bot, {53209, 19434}) ? "marksmanship" : "hunter_generic";
        case CLASS_DEATH_KNIGHT:
            return role == "tank" ? "blood" : "death_knight_generic";
        case CLASS_WARRIOR:
            return role == "tank" ? "protection" : "warrior_generic";
        case CLASS_DRUID:
            return role == "healer" ? "restoration_druid" : "druid_generic";
        case CLASS_ROGUE:
            return "rogue_generic";
        case CLASS_WARLOCK:
            return "warlock_generic";
        default:
            return "generic";
    }
}

bool HasEnoughPowerForProfileSpell(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return false;

    int32 cost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (cost <= 0)
        return true;
    if (spellInfo->PowerType >= MAX_POWERS)
        return true;
    if (spellInfo->PowerType == POWER_HEALTH)
        return int64(bot->GetHealth()) > cost;
    return bot->GetPower(Powers(spellInfo->PowerType)) >= uint32(cost);
}

uint32 ProfileSpellCastTimeMs(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return 0;
    return uint32(std::max<int32>(0, spellInfo->CalcCastTime(bot->getLevel())));
}

bool LoadDbProfileLocked(uint8 classId, std::string const& specTag, std::string const& role, std::string* failureReason)
{
    std::string key = DbRotationKey(classId, specTag, role);
    g_dbRotationCache.RequestedKeys.insert(key);
    g_dbRotationCache.LastError.clear();
    std::string escapedSpecTag = specTag;
    std::string escapedRole = role;
    WorldDatabase.EscapeString(escapedSpecTag);
    WorldDatabase.EscapeString(escapedRole);

    QueryResult result = WorldDatabase.PQuery(
        "SELECT p.id, p.class_id, p.spec_tag, p.role, p.resource_type, p.range_band, p.version, "
        "p.movement_directive, p.auto_attack_mode, p.min_range, p.max_range, "
        "a.spell_id, a.category, a.mechanic_tags, a.damage_weight, a.healing_weight, a.threat_weight, "
        "a.mitigation_weight, a.survival_weight, a.movement_weight, a.progression_weight, "
        "a.profession_weight, a.priority_bucket, a.min_enemies, a.max_enemies, "
        "a.min_target_health_pct, a.max_target_health_pct, a.min_self_health_pct, a.max_self_health_pct, "
        "a.required_self_aura, a.forbidden_self_aura, a.required_target_aura, a.forbidden_target_aura, "
        "a.requires_interruptible_target, a.requires_target_not_victim, a.requires_target_victim, "
        "a.requires_melee_range, a.requires_ranged_range, a.target_selector, a.movement_directive, "
        "a.auto_attack_mode, a.min_range, a.max_range, a.requires_instant_cast, a.max_cast_time_ms, "
        "a.maintain_aura_id, a.refresh_aura_below_ms "
        "FROM bot_rotation_profile p "
        "JOIN bot_rotation_action a ON a.profile_id = p.id "
        "WHERE p.enabled = 1 AND a.enabled = 1 AND p.class_id = %u AND p.spec_tag = '%s' AND p.role = '%s' "
        "ORDER BY a.priority_bucket, a.sort_order, a.id",
        uint32(classId), escapedSpecTag.c_str(), escapedRole.c_str());

    if (!result)
    {
        g_dbRotationCache.Profiles.erase(key);
        g_dbRotationCache.LastError = "profile_not_found_" + key;
        if (failureReason)
            *failureReason = g_dbRotationCache.LastError;
        return false;
    }

    BotClassSpecActionProfile profile;
    do
    {
        Field* fields = result->Fetch();
        uint32 profileId = fields[0].GetUInt32();
        if (profile.Spells.empty())
        {
            profile.ClassId = fields[1].GetUInt8();
            profile.SpecTag = fields[2].GetString();
            profile.Role = fields[3].GetString();
            profile.ResourceType = fields[4].GetString();
            profile.RangeBand = fields[5].GetString();
            profile.ProfileSource = "world_db_bot_rotation_profile_" + std::to_string(profileId) + "_v" + fields[6].GetString();
            profile.MovementDirective = fields[7].GetString();
            profile.AutoAttackMode = fields[8].GetString();
            profile.MinRange = fields[9].GetFloat();
            profile.MaxRange = fields[10].GetFloat();
            profile.MissingProfile = false;
        }

        uint32 spellId = fields[11].GetUInt32();
        if (spellId && !sSpellMgr->GetSpellInfo(spellId))
        {
            g_dbRotationCache.LastError = "invalid_spell_id_" + std::to_string(spellId);
            continue;
        }

        std::string categoryName = fields[12].GetString();
        BotCombatActionCategory category = BotCombatActionCatalog::CategoryFromString(categoryName);
        if (category == BotCombatActionCategory::Wait && categoryName != "wait")
        {
            g_dbRotationCache.LastError = "invalid_category_" + categoryName;
            continue;
        }

        BotActionProfileSpell spell;
        spell.SpellId = spellId;
        spell.Category = category;
        spell.MechanicTags = fields[13].GetString();
        spell.DamageWeight = fields[14].GetFloat();
        spell.HealingWeight = fields[15].GetFloat();
        spell.ThreatWeight = fields[16].GetFloat();
        spell.MitigationWeight = fields[17].GetFloat();
        spell.SurvivalWeight = fields[18].GetFloat();
        spell.MovementWeight = fields[19].GetFloat();
        spell.ProgressionWeight = fields[20].GetFloat();
        spell.ProfessionWeight = fields[21].GetFloat();
        spell.PriorityBucket = fields[22].GetUInt8();
        spell.MinEnemies = fields[23].GetUInt8();
        spell.MaxEnemies = fields[24].GetUInt8();
        spell.MinTargetHealthPct = fields[25].GetFloat();
        spell.MaxTargetHealthPct = fields[26].GetFloat();
        spell.MinSelfHealthPct = fields[27].GetFloat();
        spell.MaxSelfHealthPct = fields[28].GetFloat();
        spell.RequiredSelfAura = fields[29].GetUInt32();
        spell.ForbiddenSelfAura = fields[30].GetUInt32();
        spell.RequiredTargetAura = fields[31].GetUInt32();
        spell.ForbiddenTargetAura = fields[32].GetUInt32();
        spell.RequiresInterruptibleTarget = fields[33].GetBool();
        spell.RequiresTargetNotVictim = fields[34].GetBool();
        spell.RequiresTargetVictim = fields[35].GetBool();
        spell.RequiresMeleeRange = fields[36].GetBool();
        spell.RequiresRangedRange = fields[37].GetBool();
        spell.TargetSelector = fields[38].GetString();
        spell.MovementDirective = fields[39].GetString();
        spell.AutoAttackMode = fields[40].GetString();
        spell.MinRange = fields[41].GetFloat();
        spell.MaxRange = fields[42].GetFloat();
        spell.RequiresInstantCast = fields[43].GetBool();
        spell.MaxCastTimeMs = fields[44].GetUInt32();
        spell.MaintainAuraId = fields[45].GetUInt32();
        spell.RefreshAuraBelowMs = fields[46].GetUInt32();
        profile.Spells.push_back(spell);
    } while (result->NextRow());

    if (profile.Spells.empty())
    {
        g_dbRotationCache.Profiles.erase(key);
        g_dbRotationCache.LastError = g_dbRotationCache.LastError.empty() ? "no_valid_db_rotation_actions_" + key : g_dbRotationCache.LastError;
        if (failureReason)
            *failureReason = g_dbRotationCache.LastError;
        return false;
    }

    if (!g_dbRotationCache.Profiles.count(key))
        g_dbRotationCache.Order.push_back(key);
    g_dbRotationCache.Profiles[key] = profile;
    if (failureReason)
        *failureReason = g_dbRotationCache.LastError;
    return true;
}

bool EnsureDbProfileLoaded(uint8 classId, std::string const& specTag, std::string const& role)
{
    std::lock_guard<std::mutex> guard(g_dbRotationMutex);
    std::string key = DbRotationKey(classId, specTag, role);
    if (g_dbRotationCache.Profiles.count(key))
        return true;
    std::string ignored;
    return LoadDbProfileLocked(classId, specTag, role, &ignored);
}
}

std::string BotClassSpecActionProfile::EmbeddingJson() const
{
    std::ostringstream json;
    json << "{\"class_id\":" << uint32(ClassId)
         << ",\"spec_tag\":\"" << ClassSpecProfileEscape(SpecTag) << "\""
         << ",\"role\":\"" << ClassSpecProfileEscape(Role) << "\""
         << ",\"resource_type\":\"" << ClassSpecProfileEscape(ResourceType) << "\""
         << ",\"range_band\":\"" << ClassSpecProfileEscape(RangeBand) << "\""
         << ",\"movement_directive\":\"" << ClassSpecProfileEscape(MovementDirective) << "\""
         << ",\"auto_attack_mode\":\"" << ClassSpecProfileEscape(AutoAttackMode) << "\""
         << ",\"min_range\":" << MinRange
         << ",\"max_range\":" << MaxRange
         << ",\"profile_source\":\"" << ClassSpecProfileEscape(ProfileSource) << "\""
         << ",\"missing_profile\":" << (MissingProfile ? "true" : "false")
         << ",\"known_spell_count\":" << Spells.size() << "}";
    return json.str();
}

std::string BotClassSpecActionProfile::QualityFlagsJson() const
{
    std::ostringstream json;
    json << "{\"missing_profile\":" << (MissingProfile ? "true" : "false")
         << ",\"profile_source\":\"" << ClassSpecProfileEscape(ProfileSource) << "\"}";
    return json.str();
}

BotClassSpecActionProfile BotClassSpecActionProfileStore::Build(Player const* bot, char const* roleHint)
{
    BotClassSpecActionProfile profile;
    if (!bot)
        return profile;

    profile.ClassId = bot->getClass();
    profile.ResourceType = PowerName(bot->GetPowerType());
    profile.Role = roleHint && *roleHint ? roleHint : "dps";
    profile.SpecTag = InferSpecTag(bot, profile.Role);
    profile.RangeBand = "mixed";
    profile.ProfileSource = "missing_db_rotation_profile";
    profile.MissingProfile = true;

    EnsureDbProfileLoaded(profile.ClassId, profile.SpecTag, profile.Role);
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        auto itr = g_dbRotationCache.Profiles.find(DbRotationKey(profile.ClassId, profile.SpecTag, profile.Role));
        if (itr != g_dbRotationCache.Profiles.end())
            profile = itr->second;
    }

    if (!profile.MissingProfile)
    {
        profile.Spells.erase(std::remove_if(profile.Spells.begin(), profile.Spells.end(), [bot](BotActionProfileSpell const& spell)
        {
            return spell.SpellId && !bot->HasSpell(spell.SpellId);
        }), profile.Spells.end());
        if (profile.Spells.empty())
        {
            profile.MissingProfile = true;
            profile.ProfileSource = "db_rotation_profile_has_no_known_spells";
        }
        else if (profile.MovementDirective.empty() || profile.AutoAttackMode.empty())
        {
            profile.MissingProfile = true;
            profile.ProfileSource = "db_rotation_profile_missing_movement_directives";
            profile.Spells.clear();
        }
    }
    return profile;
}

std::vector<BotActionCandidate> BotClassSpecActionProfileStore::BuildCandidates(Player const* bot, Unit const* target, BotClassSpecActionProfile const& profile)
{
    std::vector<BotActionCandidate> candidates;
    if (!bot)
        return candidates;

    uint64 targetGuid = target ? target->GetGUID().GetCounter() : 0;
    uint32 targetEntry = 0;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        targetEntry = creature->GetEntry();

    for (BotActionProfileSpell const& spell : profile.Spells)
    {
        BotActionCandidate candidate;
        candidate.ActionId = BotCombatActionCatalog::StableActionId(spell.Category, spell.SpellId);
        candidate.SpellId = spell.SpellId;
        candidate.Category = spell.Category;
        candidate.TargetGuid = targetGuid;
        candidate.TargetEntry = targetEntry;
        candidate.Profile = spell;
        candidate.Score = spell.DamageWeight + spell.HealingWeight + spell.ThreatWeight + spell.MitigationWeight + spell.SurvivalWeight + spell.ProgressionWeight - float(spell.PriorityBucket) * 0.03f;
        candidate.Reason = "profile_weight";

        if (spell.SpellId)
        {
            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spell.SpellId);
            if (!spellInfo)
                candidate.RejectReason = "missing_spell_info";
            else if (bot->HasUnitState(UNIT_STATE_CASTING))
                candidate.RejectReason.clear();
            else if (bot->GetSpellHistory()->HasGlobalCooldown(spellInfo))
                candidate.RejectReason.clear();
            else if (!bot->GetSpellHistory()->IsReady(spellInfo))
                candidate.RejectReason = "cooldown_not_ready";
            else if (spell.RequiresInstantCast && ProfileSpellCastTimeMs(bot, spellInfo) > 0)
                candidate.RejectReason = "instant_cast_required";
            else if (spell.MaxCastTimeMs && ProfileSpellCastTimeMs(bot, spellInfo) > spell.MaxCastTimeMs)
                candidate.RejectReason = "cast_time_too_long";
            else if (target && (spell.Category == BotCombatActionCategory::HealFast || spell.Category == BotCombatActionCategory::HealEfficient || spell.Category == BotCombatActionCategory::HealAoe))
                candidate.TargetType = "ally";
            else if (target && !bot->IsWithinDistInMap(target, std::max(5.0f, spellInfo->GetMaxRange(false))))
                candidate.RejectReason = "out_of_range";
            else
            {
                if (!HasEnoughPowerForProfileSpell(bot, spellInfo))
                    candidate.RejectReason = "insufficient_resource";
            }
        }
        candidates.push_back(candidate);
    }
    return candidates;
}

std::string BotClassSpecActionProfileStore::CandidateMaskJson(std::vector<BotActionCandidate> const& candidates, BotClassSpecActionProfile const& profile, char const* roleGoal, char const* saturationJson, char const* profileSourceOverride)
{
    std::ostringstream json;
    json << "{\"schema\":\"bot_valid_action_mask_v2\""
         << ",\"profile\":" << profile.EmbeddingJson()
         << ",\"profile_source\":\"" << ClassSpecProfileEscape(profileSourceOverride ? profileSourceOverride : profile.ProfileSource) << "\""
         << ",\"role_goal\":\"" << ClassSpecProfileEscape(roleGoal ? roleGoal : profile.Role) << "\""
         << ",\"role_saturation_state\":" << (saturationJson && *saturationJson ? saturationJson : "{}")
         << ",\"actions\":[";
    bool first = true;
    for (BotActionCandidate const& candidate : candidates)
    {
        if (!first)
            json << ",";
        first = false;
        json << "{\"action_id\":" << candidate.ActionId
             << ",\"spell_id\":" << candidate.SpellId
             << ",\"action_category\":\"" << ClassSpecProfileEscape(BotCombatActionCatalog::ToString(candidate.Category)) << "\""
             << ",\"target_guid\":" << candidate.TargetGuid
             << ",\"target_entry\":" << candidate.TargetEntry
             << ",\"score\":" << candidate.Score
             << ",\"score_inputs\":{\"damage_weight\":" << candidate.Profile.DamageWeight
             << ",\"healing_weight\":" << candidate.Profile.HealingWeight
             << ",\"threat_weight\":" << candidate.Profile.ThreatWeight
             << ",\"mitigation_weight\":" << candidate.Profile.MitigationWeight
             << ",\"survival_weight\":" << candidate.Profile.SurvivalWeight
             << ",\"movement_weight\":" << candidate.Profile.MovementWeight
             << ",\"progression_weight\":" << candidate.Profile.ProgressionWeight
             << ",\"profession_weight\":" << candidate.Profile.ProfessionWeight << "}"
             << ",\"mechanic_tags\":\"" << ClassSpecProfileEscape(candidate.Profile.MechanicTags) << "\""
             << ",\"target_selector\":\"" << ClassSpecProfileEscape(candidate.Profile.TargetSelector) << "\""
             << ",\"movement_directive\":\"" << ClassSpecProfileEscape(candidate.Profile.MovementDirective) << "\""
             << ",\"auto_attack_mode\":\"" << ClassSpecProfileEscape(candidate.Profile.AutoAttackMode) << "\""
             << ",\"reject_reason\":\"" << ClassSpecProfileEscape(candidate.RejectReason) << "\""
             << ",\"role_goal\":\"" << ClassSpecProfileEscape(roleGoal ? roleGoal : profile.Role) << "\"}";
    }
    json << "]}";
    return json.str();
}

std::string BotClassSpecActionProfileStore::ChosenActionJson(BotActionCandidate const* candidate, BotClassSpecActionProfile const& profile, char const* roleGoal, char const* balanceMode, float confidence)
{
    std::ostringstream json;
    json << "{\"action\":\"" << (candidate && candidate->SpellId ? "cast_combat_spell" : "attack") << "\""
         << ",\"action_id\":" << (candidate ? candidate->ActionId : BotCombatActionCatalog::StableActionId(BotCombatActionCategory::Wait))
         << ",\"spell_id\":" << (candidate ? candidate->SpellId : 0)
         << ",\"action_category\":\"" << ClassSpecProfileEscape(candidate ? BotCombatActionCatalog::ToString(candidate->Category) : "wait") << "\""
         << ",\"target_guid\":" << (candidate ? candidate->TargetGuid : 0)
         << ",\"target_entry\":" << (candidate ? candidate->TargetEntry : 0)
         << ",\"class_spec_profile\":" << profile.EmbeddingJson()
         << ",\"role_goal\":\"" << ClassSpecProfileEscape(roleGoal ? roleGoal : profile.Role) << "\""
         << ",\"adaptive_balance_mode\":\"" << ClassSpecProfileEscape(balanceMode ? balanceMode : "role_first") << "\""
         << ",\"experiment_confidence\":" << confidence
         << ",\"reason\":\"" << ClassSpecProfileEscape(candidate ? candidate->Reason : "no_valid_action") << "\""
         << ",\"expected_damage\":" << (candidate ? candidate->Profile.DamageWeight : 0.0f)
         << ",\"expected_heal\":" << (candidate ? candidate->Profile.HealingWeight : 0.0f)
         << ",\"expected_threat\":" << (candidate ? candidate->Profile.ThreatWeight : 0.0f)
         << ",\"expected_mitigation\":" << (candidate ? candidate->Profile.MitigationWeight : 0.0f)
         << ",\"reject_reason\":\"" << ClassSpecProfileEscape(candidate ? candidate->RejectReason : "no_valid_action") << "\"}";
    return json.str();
}

std::string BotClassSpecActionProfileStore::ReloadDbProfiles()
{
    std::lock_guard<std::mutex> guard(g_dbRotationMutex);
    std::set<std::string> requested = g_dbRotationCache.RequestedKeys;
    g_dbRotationCache.Profiles.clear();
    g_dbRotationCache.Order.clear();
    g_dbRotationCache.LastError.clear();

    std::string failureReason;
    bool ok = true;
    for (std::string const& key : requested)
    {
        size_t first = key.find(':');
        size_t second = key.find(':', first == std::string::npos ? first : first + 1);
        if (first == std::string::npos || second == std::string::npos)
            continue;
        uint8 classId = uint8(std::atoi(key.substr(0, first).c_str()));
        std::string specTag = key.substr(first + 1, second - first - 1);
        std::string role = key.substr(second + 1);
        ok = LoadDbProfileLocked(classId, specTag, role, &failureReason) && ok;
    }

    std::ostringstream json;
    json << "{\"ok\":" << (ok ? "true" : "false")
         << ",\"action\":\"botauto_rotations_reload\""
         << ",\"requested_profile_count\":" << requested.size()
         << ",\"profile_count\":" << g_dbRotationCache.Profiles.size()
         << ",\"failure_reason\":" << (failureReason.empty() ? "null" : ("\"" + ClassSpecProfileEscape(failureReason) + "\""))
         << "}";
    return json.str();
}

std::string BotClassSpecActionProfileStore::DbProfilesJson()
{
    std::lock_guard<std::mutex> guard(g_dbRotationMutex);

    std::ostringstream json;
    json << "{\"ok\":true"
         << ",\"action\":\"botauto_rotations_list\""
         << ",\"load_mode\":\"lazy_per_spec\""
         << ",\"requested_profile_count\":" << g_dbRotationCache.RequestedKeys.size()
         << ",\"profile_count\":" << g_dbRotationCache.Profiles.size()
         << ",\"failure_reason\":" << (g_dbRotationCache.LastError.empty() ? "null" : ("\"" + ClassSpecProfileEscape(g_dbRotationCache.LastError) + "\""))
         << ",\"profiles\":[";
    bool first = true;
    for (std::string const& key : g_dbRotationCache.Order)
    {
        auto itr = g_dbRotationCache.Profiles.find(key);
        if (itr == g_dbRotationCache.Profiles.end())
            continue;
        if (!first)
            json << ",";
        first = false;
        BotClassSpecActionProfile const& profile = itr->second;
        json << "{\"class_id\":" << uint32(profile.ClassId)
             << ",\"spec_tag\":\"" << ClassSpecProfileEscape(profile.SpecTag) << "\""
             << ",\"role\":\"" << ClassSpecProfileEscape(profile.Role) << "\""
             << ",\"range_band\":\"" << ClassSpecProfileEscape(profile.RangeBand) << "\""
             << ",\"movement_directive\":\"" << ClassSpecProfileEscape(profile.MovementDirective) << "\""
             << ",\"auto_attack_mode\":\"" << ClassSpecProfileEscape(profile.AutoAttackMode) << "\""
             << ",\"profile_source\":\"" << ClassSpecProfileEscape(profile.ProfileSource) << "\""
             << ",\"action_count\":" << profile.Spells.size() << "}";
    }
    json << "]}";
    return json.str();
}

std::string BotClassSpecActionProfileStore::DbProfileDumpJson(uint8 classId, std::string const& specTag, std::string const& role)
{
    EnsureDbProfileLoaded(classId, specTag, role);
    std::lock_guard<std::mutex> guard(g_dbRotationMutex);

    auto itr = g_dbRotationCache.Profiles.find(DbRotationKey(classId, specTag, role));
    if (itr == g_dbRotationCache.Profiles.end())
    {
        std::ostringstream missing;
        missing << "{\"ok\":false,\"action\":\"botauto_rotations_dump\",\"failure_reason\":\"profile_not_found\""
                << ",\"class_id\":" << uint32(classId)
                << ",\"spec_tag\":\"" << ClassSpecProfileEscape(specTag) << "\""
                << ",\"role\":\"" << ClassSpecProfileEscape(role) << "\"}";
        return missing.str();
    }

    BotClassSpecActionProfile const& profile = itr->second;
    std::ostringstream json;
    json << "{\"ok\":true,\"action\":\"botauto_rotations_dump\""
         << ",\"profile\":" << profile.EmbeddingJson()
         << ",\"actions\":[";
    bool first = true;
    for (BotActionProfileSpell const& spell : profile.Spells)
    {
        if (!first)
            json << ",";
        first = false;
        json << "{\"spell_id\":" << spell.SpellId
             << ",\"category\":\"" << ClassSpecProfileEscape(BotCombatActionCatalog::ToString(spell.Category)) << "\""
             << ",\"tags\":\"" << ClassSpecProfileEscape(spell.MechanicTags) << "\""
             << ",\"target_selector\":\"" << ClassSpecProfileEscape(spell.TargetSelector) << "\""
             << ",\"movement_directive\":\"" << ClassSpecProfileEscape(spell.MovementDirective) << "\""
             << ",\"auto_attack_mode\":\"" << ClassSpecProfileEscape(spell.AutoAttackMode) << "\""
             << ",\"priority_bucket\":" << uint32(spell.PriorityBucket)
             << ",\"weights\":{\"damage\":" << spell.DamageWeight
             << ",\"healing\":" << spell.HealingWeight
             << ",\"threat\":" << spell.ThreatWeight
             << ",\"mitigation\":" << spell.MitigationWeight
             << ",\"survival\":" << spell.SurvivalWeight << "}"
             << ",\"gates\":{\"min_enemies\":" << uint32(spell.MinEnemies)
             << ",\"max_enemies\":" << uint32(spell.MaxEnemies)
             << ",\"max_target_health_pct\":" << spell.MaxTargetHealthPct
             << ",\"max_self_health_pct\":" << spell.MaxSelfHealthPct
             << ",\"required_self_aura\":" << spell.RequiredSelfAura
             << ",\"forbidden_target_aura\":" << spell.ForbiddenTargetAura
             << ",\"interrupt\":" << (spell.RequiresInterruptibleTarget ? "true" : "false")
             << ",\"target_not_victim\":" << (spell.RequiresTargetNotVictim ? "true" : "false")
             << ",\"requires_instant_cast\":" << (spell.RequiresInstantCast ? "true" : "false")
             << ",\"max_cast_time_ms\":" << spell.MaxCastTimeMs
             << ",\"min_range\":" << spell.MinRange
             << ",\"max_range\":" << spell.MaxRange
             << "}}";
    }
    json << "]}";
    return json.str();
}
