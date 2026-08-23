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

    if (QueryResult result = CharacterDatabase.PQuery("SELECT class_spec FROM character_bot_pool WHERE guid = %u LIMIT 1", bot->GetGUID().GetCounter()))
    {
        std::string classSpec = BotClassSpecActionProfileDetail::CanonicalSpecTag(result->Fetch()[0].GetString());
        if (!classSpec.empty())
            return classSpec;
    }

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
            return HasAny(bot, {53301, 3674}) ? "survival"
                : (HasAny(bot, {53209, 19434}) ? "marksmanship" : "hunter_generic");
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
         << ",\"snapshot_generation\":" << SnapshotGeneration
         << ",\"snapshot_content_hash\":\"" << ClassSpecProfileEscape(SnapshotContentHash) << "\""
         << ",\"missing_profile\":" << (MissingProfile ? "true" : "false")
         << ",\"known_spell_count\":" << Spells.size() << "}";
    return json.str();
}

std::string BotClassSpecActionProfile::QualityFlagsJson() const
{
    std::ostringstream json;
    json << "{\"missing_profile\":" << (MissingProfile ? "true" : "false")
         << ",\"profile_source\":\"" << ClassSpecProfileEscape(ProfileSource) << "\""
         << ",\"coverage_tags\":\"proc_or_opener\""
         << ",\"coverage_spell_ids\":\"53595,31935,26573,53600,56641,2643,8042,17364,60103,421,2120,1449\"}";
    return json.str();
}

BotClassSpecActionProfile BotClassSpecActionProfileStore::Build(Player const* bot, char const* roleHint)
{
    return BuildForSpec(bot, roleHint, nullptr);
}

uint32 BotClassSpecActionProfileStore::ReactionTimeMsForSpec(char const* specTag)
{
    std::string const canonicalSpecTag = BotClassSpecActionProfileDetail::CanonicalSpecTag(specTag ? specTag : "");
    return canonicalSpecTag == "affliction_warlock"
        || canonicalSpecTag == "shadow_priest"
        || canonicalSpecTag == "balance_druid" ? 100 : 500;
}

BotClassSpecActionProfile BotClassSpecActionProfileStore::BuildForSpec(
    Player const* bot, char const* roleHint, char const* specTag)
{
    BotClassSpecActionProfile profile;
    if (!bot)
        return profile;

    profile.ClassId = bot->getClass();
    profile.ResourceType = PowerName(bot->GetPowerType());
    profile.Role = roleHint && *roleHint ? roleHint : "dps";
    profile.SpecTag = specTag && *specTag
        ? BotClassSpecActionProfileDetail::CanonicalSpecTag(specTag) : InferSpecTag(bot, profile.Role);
    profile.RangeBand = "mixed";
    profile.ProfileSource = "missing_db_rotation_profile";
    profile.MissingProfile = true;

    BotClassSpecActionProfile dbProfile;
    if (BotClassSpecActionProfileDetail::FindActiveDbProfile(profile.ClassId,
            profile.SpecTag, profile.Role, dbProfile))
        profile = dbProfile;

    if (!profile.MissingProfile)
    {
        profile.Spells.erase(std::remove_if(profile.Spells.begin(), profile.Spells.end(), [bot](BotActionProfileSpell const& spell)
        {
            return spell.SpellId && spell.Category != BotCombatActionCategory::UseItem
                && !bot->HasSpell(spell.SpellId);
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
    if (profile.MissingProfile && profile.ClassId == CLASS_SHAMAN)
        profile.SpecTag = profile.Role == "healer" ? "restoration_or_elemental_generic" : "enhancement_or_elemental_generic";
    if (profile.MissingProfile && profile.ClassId == CLASS_PRIEST)
        profile.SpecTag = profile.Role == "healer" ? "holy_disc_generic" : "shadow_or_generic";
    return profile;
}
