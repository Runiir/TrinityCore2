#include "Bots/BotClassSpecActionProfile.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "Creature.h"
#include "DataStores/DBCEnums.h"
#include <algorithm>
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

void Add(BotClassSpecActionProfile& profile, uint32 spellId, BotCombatActionCategory category, char const* tags, float damage, float healing, float threat, float mitigation, float survival, uint8 priority)
{
    BotActionProfileSpell spell;
    spell.SpellId = spellId;
    spell.Category = category;
    spell.MechanicTags = tags ? tags : "";
    spell.DamageWeight = damage;
    spell.HealingWeight = healing;
    spell.ThreatWeight = threat;
    spell.MitigationWeight = mitigation;
    spell.SurvivalWeight = survival;
    spell.ProgressionWeight = std::max(damage, std::max(healing, std::max(threat, mitigation)));
    spell.PriorityBucket = priority;
    profile.Spells.push_back(spell);
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
}

std::string BotClassSpecActionProfile::EmbeddingJson() const
{
    std::ostringstream json;
    json << "{\"class_id\":" << uint32(ClassId)
         << ",\"spec_tag\":\"" << ClassSpecProfileEscape(SpecTag) << "\""
         << ",\"role\":\"" << ClassSpecProfileEscape(Role) << "\""
         << ",\"resource_type\":\"" << ClassSpecProfileEscape(ResourceType) << "\""
         << ",\"range_band\":\"" << ClassSpecProfileEscape(RangeBand) << "\""
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
    profile.RangeBand = "melee";

    switch (profile.ClassId)
    {
        case CLASS_MAGE:
            profile.SpecTag = HasAny(bot, {11366, 44457, 31661}) ? "fire" : (HasAny(bot, {44425, 12042}) ? "arcane" : "frost_or_generic");
            profile.RangeBand = "ranged";
            profile.Role = "dps";
            profile.MissingProfile = false;
            profile.ProfileSource = "cata_434_static_mage";
            Add(profile, 133, BotCombatActionCategory::Builder, "filler,cast", 0.70f, 0, 0, 0, 0, 5);
            Add(profile, 44614, BotCombatActionCategory::Builder, "filler,cast", 0.75f, 0, 0, 0, 0, 5);
            Add(profile, 11366, BotCombatActionCategory::Spender, "nuke,fire", 1.00f, 0, 0, 0, 0, 3);
            Add(profile, 2136, BotCombatActionCategory::Spender, "instant,fire", 0.85f, 0, 0, 0, 0, 3);
            Add(profile, 2139, BotCombatActionCategory::Interrupt, "interrupt", 0.15f, 0, 0, 0, 0.2f, 1);
            Add(profile, 45438, BotCombatActionCategory::Defensive, "immunity", 0, 0, 0, 0, 1.0f, 1);
            break;
        case CLASS_PRIEST:
            profile.SpecTag = profile.Role == "healer" || HasAny(bot, {2061, 2050, 596}) ? "holy_disc_generic" : "shadow_or_generic";
            profile.RangeBand = "ranged";
            profile.MissingProfile = false;
            profile.ProfileSource = "cata_434_static_priest";
            Add(profile, 585, BotCombatActionCategory::Builder, "filler,holy", 0.55f, 0, 0, 0, 0, 6);
            Add(profile, 589, BotCombatActionCategory::Dot, "dot,shadow", 0.65f, 0, 0, 0, 0, 4);
            Add(profile, 2061, BotCombatActionCategory::HealFast, "triage,heal", 0, 1.0f, 0, 0, 0.8f, 1);
            Add(profile, 2050, BotCombatActionCategory::HealEfficient, "efficient,heal", 0, 0.75f, 0, 0, 0.6f, 2);
            Add(profile, 596, BotCombatActionCategory::HealAoe, "aoe,heal", 0, 0.90f, 0, 0, 0.7f, 2);
            Add(profile, 527, BotCombatActionCategory::DispelCleanse, "dispel,cleanse", 0, 0.25f, 0, 0, 0.7f, 1);
            break;
        case CLASS_WARLOCK:
            profile.SpecTag = "affliction_destro_generic";
            profile.RangeBand = "ranged";
            profile.Role = "dps";
            profile.MissingProfile = false;
            profile.ProfileSource = "cata_434_static_warlock";
            Add(profile, 686, BotCombatActionCategory::Builder, "filler,shadow", 0.70f, 0, 0, 0, 0, 5);
            Add(profile, 172, BotCombatActionCategory::Dot, "dot,shadow", 0.80f, 0, 0, 0, 0, 3);
            Add(profile, 348, BotCombatActionCategory::Dot, "dot,fire", 0.65f, 0, 0, 0, 0, 4);
            Add(profile, 17962, BotCombatActionCategory::Spender, "instant,fire", 0.90f, 0, 0, 0, 0, 3);
            break;
        case CLASS_DRUID:
            profile.SpecTag = profile.Role == "healer" || HasAny(bot, {8936, 5185, 774}) ? "restoration_or_balance_generic" : "feral_or_balance_generic";
            profile.RangeBand = HasAny(bot, {5176, 8921}) ? "ranged" : "melee";
            profile.MissingProfile = false;
            profile.ProfileSource = "cata_434_static_druid";
            Add(profile, 5176, BotCombatActionCategory::Builder, "filler,nature", 0.65f, 0, 0, 0, 0, 5);
            Add(profile, 8921, BotCombatActionCategory::Dot, "dot,arcane", 0.70f, 0, 0, 0, 0, 4);
            Add(profile, 8936, BotCombatActionCategory::HealFast, "hot,heal", 0, 0.85f, 0, 0, 0.7f, 1);
            Add(profile, 5185, BotCombatActionCategory::HealEfficient, "heal", 0, 0.75f, 0, 0, 0.6f, 2);
            Add(profile, 80965, BotCombatActionCategory::Interrupt, "interrupt", 0.2f, 0, 0, 0, 0.2f, 1);
            break;
        case CLASS_SHAMAN:
            profile.SpecTag = profile.Role == "healer" || HasAny(bot, {331, 8004, 1064}) ? "restoration_or_elemental_generic" : "enhancement_or_elemental_generic";
            profile.RangeBand = "ranged";
            profile.MissingProfile = false;
            profile.ProfileSource = "cata_434_static_shaman";
            Add(profile, 403, BotCombatActionCategory::Builder, "filler,nature", 0.70f, 0, 0, 0, 0, 5);
            Add(profile, 8050, BotCombatActionCategory::Dot, "dot,fire", 0.70f, 0, 0, 0, 0, 4);
            Add(profile, 331, BotCombatActionCategory::HealEfficient, "heal", 0, 0.75f, 0, 0, 0.6f, 2);
            Add(profile, 8004, BotCombatActionCategory::HealFast, "triage,heal", 0, 1.0f, 0, 0, 0.8f, 1);
            Add(profile, 57994, BotCombatActionCategory::Interrupt, "interrupt", 0.15f, 0, 0, 0, 0.2f, 1);
            break;
        case CLASS_PALADIN:
            profile.SpecTag = profile.Role == "tank" ? "protection" : (profile.Role == "healer" ? "holy" : "retribution_or_generic");
            profile.MissingProfile = false;
            profile.ProfileSource = "cata_434_static_paladin";
            Add(profile, 20271, BotCombatActionCategory::Builder, "judgement", 0.65f, 0, 0.3f, 0, 0, 4);
            Add(profile, 35395, BotCombatActionCategory::Builder, "crusader", 0.75f, 0, 0.5f, 0, 0, 4);
            Add(profile, 635, BotCombatActionCategory::HealEfficient, "heal", 0, 0.75f, 0, 0, 0.6f, 2);
            Add(profile, 19750, BotCombatActionCategory::HealFast, "triage,heal", 0, 1.0f, 0, 0, 0.8f, 1);
            Add(profile, 62124, BotCombatActionCategory::Taunt, "taunt", 0, 0, 1.0f, 0, 0.3f, 1);
            Add(profile, 96231, BotCombatActionCategory::Interrupt, "interrupt", 0.15f, 0, 0, 0, 0.2f, 1);
            break;
        case CLASS_HUNTER:
            profile.SpecTag = "hunter_generic";
            profile.RangeBand = "ranged";
            profile.Role = "dps";
            profile.MissingProfile = false;
            profile.ProfileSource = "cata_434_static_hunter";
            Add(profile, 75, BotCombatActionCategory::AutoAttack, "ranged,auto", 0.45f, 0, 0, 0, 0, 7);
            Add(profile, 1978, BotCombatActionCategory::Dot, "dot,sting", 0.70f, 0, 0, 0, 0, 4);
            Add(profile, 3044, BotCombatActionCategory::Spender, "focus,instant", 0.85f, 0, 0, 0, 0, 3);
            break;
        case CLASS_DEATH_KNIGHT:
            profile.SpecTag = profile.Role == "tank" ? "blood" : "frost_unholy_generic";
            profile.MissingProfile = false;
            profile.ProfileSource = "cata_434_static_death_knight";
            Add(profile, 45477, BotCombatActionCategory::Debuff, "disease,frost", 0.65f, 0, 0.3f, 0, 0, 4);
            Add(profile, 45462, BotCombatActionCategory::Dot, "disease,shadow", 0.65f, 0, 0.3f, 0, 0, 4);
            Add(profile, 47541, BotCombatActionCategory::Spender, "runic_power", 0.85f, 0, 0.4f, 0, 0, 3);
            Add(profile, 47528, BotCombatActionCategory::Interrupt, "interrupt", 0.15f, 0, 0, 0, 0.2f, 1);
            Add(profile, 56222, BotCombatActionCategory::Taunt, "taunt", 0, 0, 1.0f, 0, 0.3f, 1);
            break;
        case CLASS_WARRIOR:
            profile.SpecTag = profile.Role == "tank" ? "protection" : "arms_fury_generic";
            profile.MissingProfile = false;
            profile.ProfileSource = "cata_434_static_warrior";
            Add(profile, 78, BotCombatActionCategory::Spender, "rage", 0.70f, 0, 0.3f, 0, 0, 4);
            Add(profile, 100, BotCombatActionCategory::Movement, "charge", 0.35f, 0, 0.2f, 0, 0.2f, 3);
            Add(profile, 355, BotCombatActionCategory::Taunt, "taunt", 0, 0, 1.0f, 0, 0.3f, 1);
            Add(profile, 2565, BotCombatActionCategory::Mitigation, "block,mitigation", 0, 0, 0.2f, 0.8f, 0.7f, 1);
            Add(profile, 6552, BotCombatActionCategory::Interrupt, "interrupt", 0.15f, 0, 0, 0, 0.2f, 1);
            break;
        case CLASS_ROGUE:
            profile.SpecTag = "rogue_generic";
            profile.ResourceType = "energy";
            profile.Role = "dps";
            profile.MissingProfile = false;
            profile.ProfileSource = "cata_434_static_rogue";
            Add(profile, 1752, BotCombatActionCategory::Builder, "combo,energy", 0.70f, 0, 0, 0, 0, 4);
            Add(profile, 2098, BotCombatActionCategory::Spender, "combo,finisher", 0.95f, 0, 0, 0, 0, 3);
            Add(profile, 1766, BotCombatActionCategory::Interrupt, "interrupt", 0.15f, 0, 0, 0, 0.2f, 1);
            Add(profile, 408, BotCombatActionCategory::StunCc, "stun,cc", 0.2f, 0, 0, 0, 0.3f, 2);
            break;
        default:
            Add(profile, 0, BotCombatActionCategory::AutoAttack, "generic", 0.35f, 0, 0, 0, 0, 9);
            break;
    }

    profile.Spells.erase(std::remove_if(profile.Spells.begin(), profile.Spells.end(), [bot](BotActionProfileSpell const& spell)
    {
        return spell.SpellId && !bot->HasSpell(spell.SpellId);
    }), profile.Spells.end());
    if (profile.Spells.empty())
        Add(profile, 0, BotCombatActionCategory::AutoAttack, "generic,no_known_spell", 0.35f, 0, 0, 0, 0, 9);
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
                candidate.RejectReason = "bot_casting";
            else if (bot->GetSpellHistory()->HasGlobalCooldown(spellInfo))
                candidate.RejectReason = "gcd_not_ready";
            else if (!bot->GetSpellHistory()->IsReady(spellInfo))
                candidate.RejectReason = "cooldown_not_ready";
            else if (target && (spell.Category == BotCombatActionCategory::HealFast || spell.Category == BotCombatActionCategory::HealEfficient || spell.Category == BotCombatActionCategory::HealAoe))
                candidate.TargetType = "ally";
            else if (target && !bot->IsWithinDistInMap(target, std::max(5.0f, spellInfo->GetMaxRange(false))))
                candidate.RejectReason = "out_of_range";
            else
            {
                int32 cost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
                if (cost > 0 && bot->GetPower(bot->GetPowerType()) < uint32(cost))
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
