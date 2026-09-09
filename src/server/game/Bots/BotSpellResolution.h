#ifndef TRINITY_BOT_SPELL_RESOLUTION_H
#define TRINITY_BOT_SPELL_RESOLUTION_H

#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

namespace BotSpellResolution
{
struct Resolved
{
    SpellInfo const* Requested = nullptr;
    SpellInfo const* Effective = nullptr;
    TriggerCastFlags Flags = TRIGGERED_NONE;
};

// Keep the learned/profile identity separate from a native aura replacement.
// No Spell instance is created and no proc charge is registered by resolution.
inline Resolved Resolve(Player const* bot, uint32 requestedId, bool itemSpell = false)
{
    Resolved result;
    result.Requested = sSpellMgr->GetSpellInfo(requestedId);
    if (!bot || !result.Requested)
        return result;
    result.Effective = itemSpell ? result.Requested
        : bot->GetCastSpellInfo(result.Requested, result.Flags);
    return result;
}
}

#endif
