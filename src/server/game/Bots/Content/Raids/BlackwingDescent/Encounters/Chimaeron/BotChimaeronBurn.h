#ifndef TRINITY_BOT_CHIMAERON_BURN_H
#define TRINITY_BOT_CHIMAERON_BURN_H

#include "Bots/BotEncounterLatches.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronDutyPlan.h"

#include <string_view>

// Burn window before Mortality as one cohort-wide sequence:
//
//   held -> released -> Mortality handoff -> push -> Mortality
//
// Both guides pause damage around 22-25% until the raid is safe, then lust and
// push through 20% with the fresh Double Attack tank holding the boss (Icy
// Veins 2024-07-29). Release and handoff are one step: after the release the
// Double Attack tank taunts first, and non-tanks stay held until he is the
// victim, bounded by one taunt cooldown. Nothing but readiness releases the
// hold: damage over time or tank damage that drifts the boss down waits for the
// same handoff, and below the handoff line the tanks are held too.
//
// The release and handoff are cohort latches (BotEncounterLatches.h), set by
// the blackboard publisher from the published snapshot, so every bot reads the
// same state on the same revision whatever its decision cadence.
namespace BotEncounter::Chimaeron
{
constexpr std::string_view BurnReleasedLatch = "chimaeron.burn_released";
constexpr std::string_view HandoffDoneLatch = "chimaeron.mortality_handoff_done";
constexpr std::string_view PainSuppressionActiveLatch = "chimaeron.pain_suppression_active";
// Value: time of the latest observed Pain Suppression application.
constexpr std::string_view PainSuppressionCastLatch = "chimaeron.pain_suppression_cast";

// Below this line a held raid also holds its tanks: their damage alone would
// carry the boss into Mortality before the handoff.
constexpr float MortalityHandoffPct = 21.5f;
// One taunt cooldown (Dark Command, Growl, Hand of Reckoning, Taunt: 8 s).
constexpr uint64 HandoffTimeoutMs = 8000;
constexpr uint32 BurnHoldMassacreLeadMs = 8000;
constexpr uint32 PainSuppressionSpell = 33206;
constexpr uint64 PainSuppressionCooldownMs = 180000;

inline bool TanksReady(Blackboard const& board, Duties const& duties)
{
    for (ObjectGuid tank : { duties.BreakTank, duties.DoubleAttackTank })
        if (ActorSnapshot const* actor = FindPlayer(board, tank))
            if (actor->Alive && actor->HealthPct < BurnReadyTankPct)
                return false;
    return true;
}

// The raid may enter Mortality: mixture up, no Massacre casting or about to
// cast, and both tanks healthy (they absorb the first unhealable swings).
inline bool BurnReady(Blackboard const& board, Observation const& observation,
    Duties const& duties)
{
    if (observation.CurrentPhase != Phase::Mixture || observation.MassacreCasting)
        return false;
    if (observation.MassacreInMs && *observation.MassacreInMs <= BurnHoldMassacreLeadMs)
        return false;
    return TanksReady(board, duties);
}

inline bool InBurnWindow(Observation const& observation)
{
    return observation.Boss && (observation.CurrentPhase == Phase::Mixture
            || observation.CurrentPhase == Phase::Outage)
        && observation.Boss->HealthPct <= BurnHoldMaxPct;
}

inline bool AnyAlivePlayerHasAura(Blackboard const& board, uint32 spellId)
{
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && HasAura(player, spellId))
            return true;
    return false;
}

// The published view belongs to this revision and this boss object.
inline EncounterLatchView const* CurrentLatches(Blackboard const& board,
    ActorSnapshot const& boss, EncounterLatchView const* view)
{
    return view && view->Revision == board.Revision && view->Subject == boss.Guid
        ? view : nullptr;
}

struct BurnState
{
    bool InWindow = false;
    bool Released = false;
    bool HandoffDone = false;

    bool HandoffPending() const { return Released && !HandoffDone; }
    // Non-tanks hold from 23% until release and handoff are both done.
    bool HoldNonTanks() const { return InWindow && !HandoffDone; }
};

// Without a published view (replays, a missing store) only this revision
// counts: conservative, never releases on a transient that is already gone.
inline BurnState ReadBurnState(Blackboard const& board, Observation const& observation,
    Duties const& duties, EncounterLatchView const* view)
{
    BurnState state;
    if (!observation.Boss)
        return state;
    ActorSnapshot const& boss = *observation.Boss;
    bool const mortality = observation.CurrentPhase == Phase::Mortality;
    state.InWindow = InBurnWindow(observation);
    if (EncounterLatchView const* latches = CurrentLatches(board, boss, view))
    {
        state.Released = mortality || latches->Find(BurnReleasedLatch);
        state.HandoffDone = mortality || latches->Find(HandoffDoneLatch);
        return state;
    }
    state.Released = mortality || (state.InWindow && BurnReady(board, observation, duties));
    state.HandoffDone = mortality || (state.Released
        && (!IsAlivePlayer(board, duties.DoubleAttackTank)
            || boss.VictimGuid == duties.DoubleAttackTank));
    return state;
}

// A held tank at or below the handoff line stops attacking; after the release
// the Break tank stands down for good while the Double Attack tank lives, so
// his threat never pulls the boss back onto his Break stacks.
inline bool HoldTank(BurnState const& burn, Observation const& observation,
    Duties const& duties, ObjectGuid botGuid)
{
    if (!observation.Boss)
        return false;
    if (botGuid == duties.BreakTank && burn.Released
        && !duties.DoubleAttackTank.IsEmpty())
        return true;
    return burn.HoldNonTanks() && observation.Boss->HealthPct <= MortalityHandoffPct;
}

inline bool PainSuppressionUsed(Blackboard const& board, ActorSnapshot const& boss,
    EncounterLatchView const* view)
{
    if (AnyAlivePlayerHasAura(board, PainSuppressionSpell))
        return true;
    EncounterLatchView const* latches = CurrentLatches(board, boss, view);
    if (!latches)
        return false;
    EncounterLatch const* cast = latches->Find(PainSuppressionCastLatch);
    return cast && board.ObservedAtMs < cast->Value + PainSuppressionCooldownMs;
}

// Publisher side: evaluated once per blackboard publication, from the
// published snapshot only.
inline void UpdateEncounterLatches(Blackboard const& board, EncounterLatchStore& store)
{
    if (board.Route.NodeId != EncounterNode)
        return;
    Observation const observation = ObserveEncounter(board);
    if (!observation.Boss)
        return;
    ActorSnapshot const& boss = *observation.Boss;
    // Disengaged (evade with survivors, compatibility respawn keeping the
    // GUID): nothing carries into the next pull.
    if (!IsEngaged(boss))
    {
        store.Reset();
        return;
    }
    store.BindSubject(boss.Guid);
    Duties const duties = BuildDuties(board);

    bool const mortality = observation.CurrentPhase == Phase::Mortality;
    if (!store.Find(BurnReleasedLatch)
        && (mortality || (InBurnWindow(observation) && BurnReady(board, observation, duties))))
        store.Latch(BurnReleasedLatch);
    if (EncounterLatch const* released = store.Find(BurnReleasedLatch);
        released && !store.Find(HandoffDoneLatch))
    {
        bool const handedOff = !IsAlivePlayer(board, duties.DoubleAttackTank)
            || boss.VictimGuid == duties.DoubleAttackTank;
        if (mortality || handedOff
            || board.ObservedAtMs >= released->SetAtMs + HandoffTimeoutMs)
            store.Latch(HandoffDoneLatch);
    }

    if (AnyAlivePlayerHasAura(board, PainSuppressionSpell))
    {
        if (!store.Find(PainSuppressionActiveLatch))
        {
            store.Latch(PainSuppressionActiveLatch);
            store.Clear(PainSuppressionCastLatch);
            store.Latch(PainSuppressionCastLatch, board.ObservedAtMs);
        }
    }
    else
        store.Clear(PainSuppressionActiveLatch);
}
}

#endif
