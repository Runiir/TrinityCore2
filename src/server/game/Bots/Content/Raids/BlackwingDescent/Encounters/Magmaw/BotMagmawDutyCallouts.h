#ifndef TRINITY_BOT_MAGMAW_DUTY_CALLOUTS_H
#define TRINITY_BOT_MAGMAW_DUTY_CALLOUTS_H

#include "Bots/BotRaidDutyClaims.h"

#include <string_view>
#include <vector>

// Raid-chat vocabulary for the Magmaw duties a human can claim in a play
// cohort ("I do chains", "bots do bait"). Duty ids are the keys of
// BotRaidDuty::Claims.
namespace BotEncounter::MagmawDutyCallouts
{
// Pincer riders that chain the head after Mangle.
inline constexpr std::string_view Chains = "magmaw.chains";
// Pillar of Flame / Lava Parasite baiting.
inline constexpr std::string_view Bait = "magmaw.bait";
inline constexpr std::string_view Mushrooms = "magmaw.mushrooms";

inline std::vector<BotRaidDuty::DutyKeywords> const& Table()
{
    static std::vector<BotRaidDuty::DutyKeywords> const table = []
    {
        std::vector<BotRaidDuty::DutyKeywords> duties{
            { Chains, { "chain", "chains", "pincer", "pincers", "hook",
                "hooks" } },
            { Bait, { "bait", "baits", "baiting", "parasite", "parasites",
                "pillar", "pillars" } },
            { Mushrooms, { "mushroom", "mushrooms", "shroom", "shrooms" } },
        };
        for (BotRaidDuty::DutyKeywords const& shared :
                BotRaidDuty::SharedDutyKeywords())
            duties.push_back(shared);
        return duties;
    }();
    return table;
}
}

#endif
