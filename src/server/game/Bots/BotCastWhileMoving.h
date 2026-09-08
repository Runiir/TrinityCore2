#ifndef TRINITY_BOT_CAST_WHILE_MOVING_H
#define TRINITY_BOT_CAST_WHILE_MOVING_H

#include "SpellAuraDefines.h"

class SpellInfo;

namespace BotCastWhileMoving
{
// Use Spell::CheckMovement's native aura permission without changing the
// bot's existing uncovered-channel policy. An absent or expired aura and an
// aura whose affect mask does not include this spell grant no exemption.
template <typename Caster>
bool HasNativeCapability(Caster const* caster, SpellInfo const* spellInfo)
{
    return caster && spellInfo
        && caster->HasAuraTypeWithAffectMask(
            SPELL_AURA_CAST_WHILE_WALKING, spellInfo);
}

template <typename Caster>
bool RejectMovingCandidate(Caster const* caster, SpellInfo const* spellInfo,
    bool movementCompatibleOnly, bool castTime, bool channeled)
{
    return movementCompatibleOnly && spellInfo && (castTime || channeled)
        && !HasNativeCapability(caster, spellInfo);
}

// Return true only when an uncovered moving cast should yield before native
// submission.  The callback is the executor's existing stop/clear/idle path;
// it is deliberately never invoked for a spell covered by the native aura.
template <typename Caster, typename StopMovingCallback>
bool StopUncoveredMovingCast(Caster const* caster, SpellInfo const* spellInfo,
    StopMovingCallback stopMoving)
{
    if (!caster || !spellInfo || HasNativeCapability(caster, spellInfo))
        return false;

    stopMoving();
    return true;
}
}

#endif
