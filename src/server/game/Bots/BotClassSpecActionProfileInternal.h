#ifndef TRINITY_BOT_CLASS_SPEC_ACTION_PROFILE_INTERNAL_H
#define TRINITY_BOT_CLASS_SPEC_ACTION_PROFILE_INTERNAL_H

#include "Bots/BotClassSpecActionProfile.h"
#include "SharedDefines.h"
#include <algorithm>
#include <cctype>
#include <map>
#include <sstream>
#include <string>

namespace BotClassSpecActionProfileDetail
{
inline std::string ClassSpecProfileEscape(std::string const& value)
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

inline char const* PowerName(Powers power)
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

inline std::string CanonicalSpecTag(std::string specTag)
{
    std::transform(specTag.begin(), specTag.end(), specTag.begin(), [](unsigned char c) { return std::tolower(c); });
    std::replace(specTag.begin(), specTag.end(), '-', '_');
    std::replace(specTag.begin(), specTag.end(), ' ', '_');
    static std::map<std::string, std::string> const aliases = {
        { "protection_paladin", "protection" },
        { "marksmanship_hunter", "marksmanship" },
        { "survival_hunter", "survival" },
        { "enhancement_shaman", "enhancement" },
        { "fire_mage", "fire" }
    };
    auto itr = aliases.find(specTag);
    return itr == aliases.end() ? specTag : itr->second;
}

inline std::string DbRotationKey(uint8 classId, std::string const& specTag, std::string const& role)
{
    std::ostringstream key;
    key << uint32(classId) << ":" << specTag << ":" << role;
    return key.str();
}

bool EnsureDbSnapshotLoaded();
bool FindActiveDbProfile(uint8 classId, std::string const& specTag, std::string const& role,
    BotClassSpecActionProfile& profile);
}

#endif
