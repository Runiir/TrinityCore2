#ifndef TRINITY_BOT_MALORIAK_LATCHES_H
#define TRINITY_BOT_MALORIAK_LATCHES_H

#include "Bots/BotEncounterLatches.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakDuties.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFacts.h"

#include <string_view>

// The 30% add switch as a cohort latch (BotEncounterLatches.h), so every bot
// reads one effective state for targeting, Remedy, the native restriction and
// the cooldown hold.
//
// User tactic (user raid experience 2026-09-26): kill the Aberrations as they
// come; if any are left at 30% (in the chambers or loose), stop damaging
// Maloriak and kill them one at a time; once they are all dead, kill him and
// dispel Remedy again. With nothing left at 30% there is no pause.
//
// Remedy is deliberately left on him during the switch, so his health can
// climb back above 30%: the switch is therefore latched the first time he is
// at 30% or lower with adds left, and it ends only when the chambers are
// empty and every released Aberration is dead, when phase two starts, or
// when Maloriak::AddSwitchCapMs has passed since the entry. A disengage
// (wipe, evade) or a new attempt clears it (module reset, new scope).
namespace BotEncounter::Maloriak
{
constexpr std::string_view LatchModule = "maloriak";
constexpr std::string_view AddSwitchEnteredLatch = "add_switch_entered";
constexpr std::string_view AddSwitchReleasedLatch = "add_switch_released";

enum class AddSwitchRelease : uint64
{
    None = 0,
    AddsCleared = 1,   // the chambers are empty and every Aberration is dead
    PhaseTwo = 2,
    Cap = 3,
    NothingLeft = 4    // 30% reached with no Aberration left: no pause at all
};

inline bool AddsRemain(Observation const& observation)
{
    return observation.ReserveAberrations > 0 || !observation.ActiveAberrations.empty();
}

inline bool AtSwitchHealth(Observation const& observation)
{
    return observation.Boss && observation.Engaged
        && observation.CurrentPhase != Phase::PhaseTwo
        && observation.Boss->HealthPct <= AddSwitchHealthPct;
}

// Publisher side: once per blackboard publication for the Maloriak node,
// from the published snapshot only.
inline void UpdateEncounterLatches(Blackboard const& board, EncounterLatchModule module)
{
    if (board.Route.NodeId != EncounterNode)
        return;
    Observation const observation = Observe(board);
    if (!observation.Boss)
        return;
    if (!observation.Engaged)
    {
        module.Reset();
        return;
    }
    module.BindSubject(observation.Boss->Guid);
    if (module.Find(AddSwitchReleasedLatch))
        return;
    EncounterLatch const* entered = module.Find(AddSwitchEnteredLatch);
    if (!entered)
    {
        if (!AtSwitchHealth(observation))
            return;
        if (AddsRemain(observation))
            module.Latch(AddSwitchEnteredLatch);
        else
            module.Latch(AddSwitchReleasedLatch, uint64(AddSwitchRelease::NothingLeft));
        return;
    }
    if (observation.CurrentPhase == Phase::PhaseTwo)
        module.Latch(AddSwitchReleasedLatch, uint64(AddSwitchRelease::PhaseTwo));
    else if (!AddsRemain(observation))
        module.Latch(AddSwitchReleasedLatch, uint64(AddSwitchRelease::AddsCleared));
    else if (module.NowMs() >= entered->SetAtMs + AddSwitchCapMs)
        module.Latch(AddSwitchReleasedLatch, uint64(AddSwitchRelease::Cap));
}

// The Maloriak module of the published view, if it belongs to this revision
// and this boss object.
inline EncounterLatchModuleView const* CurrentLatches(Blackboard const& board,
    ActorSnapshot const& boss, EncounterLatchView const* view)
{
    if (!view || view->Revision != board.Revision)
        return nullptr;
    EncounterLatchModuleView const* module = view->Module(LatchModule);
    return module && module->Subject == boss.Guid ? module : nullptr;
}

struct AddSwitchState
{
    bool Active = false;
    // The switch ended on its cap (the dispatch logs it once).
    bool CapReleased = false;
};

// The effective switch. Without a published view (a replay without the
// store, or the first tick before a publication) it falls back to the
// unlatched condition of this snapshot.
inline AddSwitchState ResolveAddSwitch(Blackboard const& board,
    Observation const& observation, EncounterLatchView const* view)
{
    AddSwitchState state;
    if (!observation.Boss)
        return state;
    EncounterLatchModuleView const* module =
        CurrentLatches(board, *observation.Boss, view);
    if (!module)
    {
        state.Active = AtSwitchHealth(observation) && AddsRemain(observation);
        return state;
    }
    EncounterLatch const* released = module->Find(AddSwitchReleasedLatch);
    state.CapReleased = released
        && released->Value == uint64(AddSwitchRelease::Cap);
    state.Active = !released && module->Find(AddSwitchEnteredLatch)
        && observation.CurrentPhase != Phase::PhaseTwo;
    return state;
}
}

#endif
