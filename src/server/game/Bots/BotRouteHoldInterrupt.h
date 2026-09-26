#ifndef TRINITY_BOT_ROUTE_HOLD_INTERRUPT_H
#define TRINITY_BOT_ROUTE_HOLD_INTERRUPT_H

// Which current casts a route hold interrupts (pure decisions; the server
// side is BotRouteHoldInterruptServer.h).
//
// Round 4 r04 traces (113,713 entries, all 102 replies): the route's hold and
// reject branches called InterruptNonMeleeSpells(false) at the start of every
// tick. The route candidate claims only movement, so the Support heal
// candidate started a new heal the same tick, and the next tick killed it:
// the Atramedes healers prepared 953 cast-time heals and 860 failed
// (SPELL_FAILED_INTERRUPTED, never moving); after the wipe the paladin landed
// 1 of 415 and the priest 0 of 353. The boss-node rejection of undeclared
// trash (boss_route_target_not_declared) caused 771 of the 778 post-wipe
// failures.
//
// On composition raid rows (the round-4 recovery-return scope: a raid
// instance, row field composition_recovery) a hold interrupts only offensive
// casts: a spell whose unit target is attackable by the caster, a non-positive
// spell without a unit target, and any auto-repeat shot. A heal or a buff
// survives. Every other scenario (Stonecore, legacy Magmaw, calibration)
// keeps the blanket interrupt.
namespace BotRouteHoldInterrupt
{
inline bool IsOffensiveCast(bool hasUnitTarget, bool unitTargetAttackable, bool positive)
{
    return hasUnitTarget ? unitTargetAttackable : !positive;
}

// The active route node is a composition row in a raid instance.
template <typename CohortRuntime, typename PartyRuntime>
inline bool OffensiveOnlyScope(CohortRuntime const& cohort, PartyRuntime const& party)
{
    if (!cohort.Config.ValidationRouteEnable || !cohort.Raid.RaidInstance
        || party.ValidationRouteManifestIndex >= party.ValidationRouteManifest.size())
        return false;
    auto const& node = party.ValidationRouteManifest[party.ValidationRouteManifestIndex];
    return node.NodeId == cohort.Config.ValidationRouteNodeId && node.CompositionRecovery;
}
}

#endif
