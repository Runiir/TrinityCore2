#ifndef TRINITY_BOT_ROUTE_HOLD_INTERRUPT_SERVER_H
#define TRINITY_BOT_ROUTE_HOLD_INTERRUPT_SERVER_H

#include "Bots/BotRouteHoldInterrupt.h"
#include "Bots/BotSpellCastTarget.h"

#include "Spell.h"
#include "SpellInfo.h"
#include "Unit.h"

// Server side of BotRouteHoldInterrupt: reads the caster's current spells
// (the unit target through BotSpellCastTarget::UnitTarget, never the cached
// pointer) and interrupts with the same arguments InterruptNonMeleeSpells
// uses per spell slot.
namespace BotRouteHoldInterrupt
{
inline bool IsOffensiveCurrentCast(Unit const* caster, Spell const* spell)
{
    if (!caster || !spell || !spell->GetSpellInfo())
        return false;
    Unit* const target = BotSpellCastTarget::UnitTarget(spell);
    return IsOffensiveCast(target != nullptr, target && caster->IsValidAttackTarget(target),
        spell->GetSpellInfo()->IsPositive());
}

// Interrupts the offensive current casts only; true if any was interrupted.
inline bool InterruptOffensiveCasts(Unit* caster)
{
    if (!caster)
        return false;
    bool interrupted = false;
    if (IsOffensiveCurrentCast(caster, caster->GetCurrentSpell(CURRENT_GENERIC_SPELL)))
    {
        caster->InterruptSpell(CURRENT_GENERIC_SPELL, false, true);
        interrupted = true;
    }
    if (caster->GetCurrentSpell(CURRENT_AUTOREPEAT_SPELL))
    {
        caster->InterruptSpell(CURRENT_AUTOREPEAT_SPELL, false, true);
        interrupted = true;
    }
    if (IsOffensiveCurrentCast(caster, caster->GetCurrentSpell(CURRENT_CHANNELED_SPELL)))
    {
        caster->InterruptSpell(CURRENT_CHANNELED_SPELL, true, true);
        interrupted = true;
    }
    return interrupted;
}

// A route hold's interrupt: offensive casts only in scope
// (OffensiveOnlyScope), every non-melee cast elsewhere, as before.
inline void InterruptForRouteHold(Unit* caster, bool offensiveOnly)
{
    if (!caster)
        return;
    if (offensiveOnly)
        InterruptOffensiveCasts(caster);
    else
        caster->InterruptNonMeleeSpells(false);
}
}

#endif
