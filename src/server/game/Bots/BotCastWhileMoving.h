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

// Spell::prepare tests movement against CalcCastTime after the caster's
// WorldObject::ModSpellCastTime (class spell mods and cast speed), so a
// proc-instant cast such as a Shooting Stars Starsurge is instant there.
// Preview that same value at decision time.  No Spell is passed, so no mod
// charge is registered.  A base-instant spell stays instant, and a spell
// reads as instant only when the client would also cast it instantly.
template <typename Caster, typename Info>
bool HasEffectiveCastTime(Caster const* caster, Info const* spellInfo)
{
    if (!spellInfo)
        return false;
    int32 castTime = int32(spellInfo->CalcCastTime(caster ? caster->getLevel() : uint8(0)));
    if (castTime > 0 && caster)
        const_cast<Caster*>(caster)->ModSpellCastTime(spellInfo, castTime, nullptr);
    return castTime > 0;
}

template <typename Caster>
bool RejectMovingCandidate(Caster const* caster, SpellInfo const* spellInfo,
    bool movementCompatibleOnly, bool castTime, bool channeled)
{
    return movementCompatibleOnly && spellInfo && (castTime || channeled)
        && !HasNativeCapability(caster, spellInfo);
}

// A protected movement (a Mechanic, Hazard or Recovery priority lease, e.g.
// a Drudge minimum-distance exit) must never be stopped to submit an
// uncovered cast-time spell.  Return true when the caller should yield the
// decision without casting and without stopping the move.
template <typename Caster>
bool YieldsToProtectedMovement(Caster const* caster, SpellInfo const* spellInfo,
    bool castTime, bool moving, bool protectedMovement)
{
    return protectedMovement && moving && castTime && caster && spellInfo
        && !HasNativeCapability(caster, spellInfo);
}

// Return true only when an uncovered moving cast should yield before native
// submission.  The callback is the executor's existing stop/clear/idle path;
// it is deliberately never invoked for a spell covered by the native aura or
// one the caster's spell mods make instant.
template <typename Caster, typename StopMovingCallback>
bool StopUncoveredMovingCast(Caster const* caster, SpellInfo const* spellInfo,
    StopMovingCallback stopMoving)
{
    if (!caster || !spellInfo || HasNativeCapability(caster, spellInfo)
        || !HasEffectiveCastTime(caster, spellInfo))
        return false;

    stopMoving();
    return true;
}
}

#endif
