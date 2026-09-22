#include "Bots/BotSpellQueue.h"

#include "Player.h"
#include "Spell.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

namespace BotSpellQueue
{
NativeLock ObserveNativeLock(Player const* bot, uint32 gcdProbeSpellId,
    uint64 nowMs)
{
    NativeLock lock;
    if (!bot)
        return lock;

    // Native timers are truncated to whole milliseconds.  Wake one
    // millisecond later so the released decision never observes a lock that
    // is still active by a fraction of a millisecond.
    if (SpellInfo const* probe = gcdProbeSpellId
            ? sSpellMgr->GetSpellInfo(gcdProbeSpellId) : nullptr)
        if (uint32 const remaining =
                bot->GetSpellHistory()->GetRemainingGlobalCooldown(probe))
            lock.GlobalCooldownEndsAtMs = nowMs + remaining + 1;

    if (Spell const* cast = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL))
        if (cast->getState() == SPELL_STATE_PREPARING
            && cast->GetRemainingCastTime() > 0)
            lock.CastEndsAtMs = nowMs + uint32(cast->GetRemainingCastTime()) + 1;

    if (Spell const* channel = bot->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
        if (channel->getState() == SPELL_STATE_CHANNELING
            && channel->GetRemainingCastTime() > 0)
            lock.ChannelEndsAtMs = nowMs
                + uint32(channel->GetRemainingCastTime()) + 1;
    return lock;
}

bool IsGlobalCooldownProbe(uint32 spellId)
{
    SpellInfo const* spellInfo = spellId ? sSpellMgr->GetSpellInfo(spellId) : nullptr;
    return spellInfo && spellInfo->StartRecoveryCategory
        && spellInfo->StartRecoveryTime;
}
}
