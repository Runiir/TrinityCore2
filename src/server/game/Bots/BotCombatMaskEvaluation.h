#ifndef TRINITY_BOT_COMBAT_MASK_EVALUATION_H
#define TRINITY_BOT_COMBAT_MASK_EVALUATION_H

#include <cstdint>
#include <iomanip>
#include <sstream>
#include <string>

// Passive cache provenance. Absence means evaluation time is unavailable, not now.
namespace BotCombatMaskEvaluation
{
inline std::string Quote(std::string const& value)
{
    std::ostringstream out;
    out << '"';
    for (unsigned char c : value)
        if (c < 0x20)
            out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << unsigned(c);
        else
        {
            if (c == '"' || c == '\\')
                out << '\\';
            out << c;
        }
    out << '"';
    return out.str();
}

template<class Actor, class Target, class Cohort, class Party>
std::string Context(std::uint64_t evaluatedAtMs, Actor const* actor,
    Target const* target, Cohort const& cohort, Party const& party,
    char const* selector)
{
    std::ostringstream out;
    out << "{\"started_at_ms\":" << evaluatedAtMs
        << ",\"selector\":" << Quote(selector)
        << ",\"actor_guid\":" << actor->GetGUID().GetCounter()
        << ",\"target_guid\":" << target->GetGUID().GetCounter()
        << ",\"target_entry\":" << target->GetEntry()
        << ",\"scope\":{\"cohort_id\":" << Quote(cohort.Id)
        << ",\"attempt_id\":" << cohort.AttemptId
        << ",\"wipe_generation\":" << cohort.Raid.WipeGeneration
        << ",\"route_generation\":" << party.ValidationRouteGeneration
        << ",\"node_id\":" << Quote(cohort.Config.ValidationRouteNodeId)
        << ",\"map_id\":" << actor->GetMapId()
        << ",\"instance_id\":" << actor->GetInstanceId() << "}}";
    return out.str();
}

inline std::string Append(std::string mask, std::string context,
    std::string const& filters)
{
    // Both objects are produced locally; retain every original mask field byte.
    if (mask.empty() || mask.back() != '}' || context.empty() || context.back() != '}')
        return mask;
    context.pop_back();
    context += ",\"selector_filters\":" + filters + "}";
    mask.pop_back();
    return mask + ",\"evaluation\":" + context + "}";
}
}
#endif
