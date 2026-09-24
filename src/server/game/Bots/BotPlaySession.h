#ifndef TRINITY_BOT_PLAY_SESSION_H
#define TRINITY_BOT_PLAY_SESSION_H

#include "ObjectGuid.h"

#include <algorithm>
#include <map>
#include <set>
#include <string>
#include <vector>

// State of one human play session (docs/bot_raids/human_play_mode.md): a
// trained bot roster minus the slots humans take, inside a raid a human
// leads. Only a Play cohort carries an active session.
struct BotPlayExternal
{
    ObjectGuid Guid;
    std::string Name;
    std::string Role;
    std::string ClassSpec;
    std::string RoleSource;
    bool RoleAmbiguous = false;
    // Trained roster slot this human replaces ("" when they joined later
    // without displacing a bot).
    std::string SlotId;
    uint64 RegisteredAtMs = 0;
};

struct BotPlaySession
{
    bool Active = false;
    std::string SessionId;
    ObjectGuid LeaderGuid;
    ObjectGuid GroupGuid;
    std::string Scenario;
    std::set<std::string> ExternalSlotIds;
    std::map<uint64, BotPlayExternal> Externals;
    // Highest route generation the bots may advance to. Generation 1 is the
    // entrance regroup. Humans moving toward (or fighting at) the next node
    // advance it; `.botauto play go` is a manual override.
    uint64 PermittedGeneration = 1;
    // Boss pull timer: bots hold the boss pull until it expires or anyone
    // engages. A wipe consumes the timer.
    uint64 PullAtMs = 0;
    uint32 PullWipeGeneration = 0;
    std::string PullSource;
    uint64 StartedAtMs = 0;
    std::string LastEvent;
};

namespace BotPlayRoster
{
struct TemplateSlot
{
    std::string SlotId;
    std::string Role;
    std::string ClassSpec;
};

// Slots listed first lose the fewest bot duties when a human takes them.
// Magmaw 10N: the Elemental Shaman only owns Bloodlust; the Affliction
// Warlock rides a pincer; the Fire Mages bait; the Survival Hunter baits
// and pulls the Chainwielder; Balance places mushrooms; the Blood DK is
// the only tank.
inline std::vector<std::string> DisruptionOrder(std::string const& scenario)
{
    if (scenario == "blackwing_descent_10n_magmaw_diagnostic")
        return { "raid_dps_5", "raid_dps_3", "raid_dps_1", "raid_dps_2",
            "raid_dps_4", "raid_tank_1", "raid_healer_3", "raid_healer_1",
            "raid_healer_2", "raid_tank_2" };
    return {};
}

// Picks the trained slot each human replaces: the least disruptive free slot
// of the human's role, else the least disruptive free dps slot, else any
// free slot in disruption order (then roster order). At least one bot must
// remain. Returns one slot id per human role, in input order, or {} with
// *failure set.
inline std::vector<std::string> ChooseExternalSlots(
    std::vector<TemplateSlot> const& roster,
    std::vector<std::string> const& humanRoles,
    std::vector<std::string> const& disruptionOrder, std::string* failure)
{
    if (humanRoles.empty())
        return {};
    if (humanRoles.size() >= roster.size())
    {
        if (failure)
            *failure = "play_requires_at_least_one_bot";
        return {};
    }
    std::vector<TemplateSlot const*> ordered;
    for (std::string const& slotId : disruptionOrder)
        for (TemplateSlot const& slot : roster)
            if (slot.SlotId == slotId)
                ordered.push_back(&slot);
    for (TemplateSlot const& slot : roster)
        if (std::find(ordered.begin(), ordered.end(), &slot) == ordered.end())
            ordered.push_back(&slot);

    std::set<std::string> taken;
    auto pick = [&](auto predicate) -> std::string
    {
        for (TemplateSlot const* slot : ordered)
            if (!taken.count(slot->SlotId) && predicate(*slot))
                return slot->SlotId;
        return {};
    };
    std::vector<std::string> chosen;
    for (std::string const& role : humanRoles)
    {
        std::string slotId = pick([&role](TemplateSlot const& slot) { return slot.Role == role; });
        if (slotId.empty())
            slotId = pick([](TemplateSlot const& slot) { return slot.Role == "dps"; });
        if (slotId.empty())
            slotId = pick([](TemplateSlot const&) { return true; });
        if (slotId.empty())
        {
            if (failure)
                *failure = "play_no_free_roster_slot";
            return {};
        }
        taken.insert(slotId);
        chosen.push_back(slotId);
    }
    return chosen;
}
}

#endif
