#ifndef TRINITY_BOT_CHIMAERON_BURN_H
#define TRINITY_BOT_CHIMAERON_BURN_H

#include "Bots/BotEncounterLatches.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronDutyPlan.h"

#include <algorithm>
#include <string_view>

// Burn window before Mortality as one cohort-wide sequence:
//
//   held -> armed (release or last chance) -> Mortality handoff -> push
//
// Both guides pause damage around 22-25% until the raid is safe, then lust and
// push through 20% with the fresh Double Attack tank holding the boss (Icy
// Veins 2024-07-29).
//
// - Held: from 23% non-tanks hold; tanks hold below 21.5% too.
// - Release: readiness (mixture up, no Massacre near, both tanks at 80%+), or
//   a bounded hold (two Massacre cycles, or fewer than two living healers).
// - Last chance: damage the hold cannot stop (damage over time, pets) carries
//   the boss to 20.5% unreleased. The handoff arms anyway; non-tanks keep
//   waiting for the release.
// - Armed: the Double Attack tank taunts first and holds the boss into
//   Mortality; the Break tank stops taunting and stands down. Non-tanks are
//   released once the handoff lands, or after one taunt cooldown. If that
//   timeout fires with the handoff still missing, the Break tank resumes
//   attacking (he keeps his threat) and the Double Attack tank keeps retrying.
//
// Every state is a cohort latch (BotEncounterLatches.h) set by the blackboard
// publisher from the published snapshot, so every bot reads the same state on
// the same revision whatever its decision cadence.
namespace BotEncounter::Chimaeron
{
constexpr std::string_view LatchModule = "chimaeron";
constexpr std::string_view HoldStartedLatch = "burn_hold_started";
// Value: BurnReleaseReason.
constexpr std::string_view BurnReleasedLatch = "burn_released";
constexpr std::string_view LastChanceLatch = "burn_last_chance";
constexpr std::string_view HandoffDoneLatch = "mortality_handoff_done";
constexpr std::string_view HandoffTimedOutLatch = "mortality_handoff_timed_out";
constexpr std::string_view PainSuppressionActiveLatch = "pain_suppression_active";
// Value: time of the latest observed Pain Suppression application.
constexpr std::string_view PainSuppressionCastLatch = "pain_suppression_cast";

enum class BurnReleaseReason : uint64
{
    None = 0,
    Ready = 1,
    HoldCap = 2,
    HealersDown = 3,
    Mortality = 4
};

// Below this line a held raid also holds its tanks: their damage alone would
// carry the boss into Mortality before the handoff.
constexpr float MortalityHandoffPct = 21.5f;
// Last-chance handoff line: unreleased at or below it, the handoff arms.
constexpr float LastChanceHandoffPct = 20.5f;
// One taunt cooldown (Dark Command, Growl, Hand of Reckoning, Taunt: 8 s).
constexpr uint64 HandoffTimeoutMs = 8000;
// Two Massacre cycles (30 s repeat): a hold that long means readiness is out
// of reach (healers out of mana, a tank kept under 80%).
constexpr uint64 BurnHoldCapMs = 60000;
constexpr std::size_t MinimumHealersForHold = 2;
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

// The Chimaeron module of the published view, if it belongs to this revision
// and this boss object.
inline EncounterLatchModuleView const* CurrentLatches(Blackboard const& board,
    ActorSnapshot const& boss, EncounterLatchView const* view)
{
    if (!view || view->Revision != board.Revision)
        return nullptr;
    EncounterLatchModuleView const* module = view->Module(LatchModule);
    return module && module->Subject == boss.Guid ? module : nullptr;
}

struct BurnState
{
    bool InWindow = false;
    bool Released = false;
    bool LastChance = false;
    bool HandoffDone = false;
    bool HandoffTimedOut = false;

    // The Double Attack tank takes the boss; the Break tank stops taunting.
    bool Armed() const { return Released || LastChance; }
    bool HandoffSettled() const { return HandoffDone || HandoffTimedOut; }
    bool HandoffFailed() const { return HandoffTimedOut && !HandoffDone; }
    bool HandoffPending() const { return Armed() && !HandoffDone; }
    // Non-tanks hold from 23% until the release and a settled handoff.
    bool HoldNonTanks() const { return InWindow && !(Released && HandoffSettled()); }
    // The push starts: release plus settled handoff inside the window.
    bool PushStarts() const { return InWindow && Released && HandoffSettled(); }
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
    if (EncounterLatchModuleView const* latches = CurrentLatches(board, boss, view))
    {
        state.Released = mortality || latches->Find(BurnReleasedLatch);
        state.LastChance = latches->Find(LastChanceLatch) != nullptr;
        state.HandoffDone = mortality || latches->Find(HandoffDoneLatch);
        state.HandoffTimedOut = latches->Find(HandoffTimedOutLatch) != nullptr;
        return state;
    }
    state.Released = mortality || (state.InWindow && BurnReady(board, observation, duties));
    state.LastChance = state.InWindow && boss.HealthPct <= LastChanceHandoffPct;
    state.HandoffDone = mortality || (state.Armed()
        && (!IsAlivePlayer(board, duties.DoubleAttackTank)
            || boss.VictimGuid == duties.DoubleAttackTank));
    return state;
}

// A held tank at or below the handoff line stops attacking. Once the handoff
// arms, the Break tank stands down while the Double Attack tank lives, so his
// threat never pulls the boss back onto his Break stacks; a failed handoff
// (timeout, the boss still on him) lets him attack again to keep his threat
// once the raid is released (before that the hold still applies).
inline bool HoldTank(Blackboard const& board, BurnState const& burn,
    Observation const& observation, Duties const& duties, ObjectGuid botGuid)
{
    if (!observation.Boss)
        return false;
    if (botGuid == duties.BreakTank && burn.Armed() && !burn.HandoffFailed()
        && IsAlivePlayer(board, duties.DoubleAttackTank))
        return true;
    return burn.HoldNonTanks() && observation.Boss->HealthPct <= MortalityHandoffPct;
}

inline bool PainSuppressionUsed(Blackboard const& board, ActorSnapshot const& boss,
    EncounterLatchView const* view)
{
    if (AnyAlivePlayerHasAura(board, PainSuppressionSpell))
        return true;
    EncounterLatchModuleView const* latches = CurrentLatches(board, boss, view);
    if (!latches)
        return false;
    EncounterLatch const* cast = latches->Find(PainSuppressionCastLatch);
    return cast && board.ObservedAtMs < cast->Value + PainSuppressionCooldownMs;
}

inline BurnReleaseReason ReleaseReason(Blackboard const& board, Observation const& observation,
    Duties const& duties, EncounterLatchModule const& module)
{
    if (observation.CurrentPhase == Phase::Mortality)
        return BurnReleaseReason::Mortality;
    if (!InBurnWindow(observation))
        return BurnReleaseReason::None;
    if (BurnReady(board, observation, duties))
        return BurnReleaseReason::Ready;
    if (duties.Healers.size() < MinimumHealersForHold)
        return BurnReleaseReason::HealersDown;
    if (EncounterLatch const* started = module.Find(HoldStartedLatch);
        started && module.NowMs() >= started->SetAtMs + BurnHoldCapMs)
        return BurnReleaseReason::HoldCap;
    return BurnReleaseReason::None;
}

// Publisher side: dispatched for the Chimaeron encounter node once per
// blackboard publication and evaluated from the published snapshot only.
inline void UpdateEncounterLatches(Blackboard const& board, EncounterLatchModule module)
{
    if (board.Route.NodeId != EncounterNode)
        return;
    Observation const observation = ObserveEncounter(board);
    if (!observation.Boss)
        return;
    ActorSnapshot const& boss = *observation.Boss;
    // Disengaged (evade with survivors, compatibility respawn keeping the
    // GUID): nothing carries into the next pull. The native encounter epoch
    // is not published for Chimaeron, so this is the pull boundary.
    if (!IsEngaged(boss))
    {
        module.Reset();
        return;
    }
    module.BindSubject(boss.Guid);
    Duties const duties = BuildDuties(board);
    bool const inWindow = InBurnWindow(observation);
    bool const mortality = observation.CurrentPhase == Phase::Mortality;

    if (inWindow)
        module.Latch(HoldStartedLatch);
    if (!module.Find(BurnReleasedLatch))
        if (BurnReleaseReason const reason = ReleaseReason(board, observation, duties, module);
            reason != BurnReleaseReason::None)
            module.Latch(BurnReleasedLatch, uint64(reason));
    if (!module.Find(BurnReleasedLatch) && inWindow && boss.HealthPct <= LastChanceHandoffPct)
        module.Latch(LastChanceLatch);

    EncounterLatch const* released = module.Find(BurnReleasedLatch);
    EncounterLatch const* lastChance = module.Find(LastChanceLatch);
    if ((released || lastChance) && !module.Find(HandoffDoneLatch))
    {
        uint64 const armedAt = released && lastChance
            ? std::min(released->SetAtMs, lastChance->SetAtMs)
            : (released ? released->SetAtMs : lastChance->SetAtMs);
        if (mortality || !IsAlivePlayer(board, duties.DoubleAttackTank)
            || boss.VictimGuid == duties.DoubleAttackTank)
            module.Latch(HandoffDoneLatch);
        else if (module.NowMs() >= armedAt + HandoffTimeoutMs)
            module.Latch(HandoffTimedOutLatch);
    }

    if (AnyAlivePlayerHasAura(board, PainSuppressionSpell))
    {
        if (!module.Find(PainSuppressionActiveLatch))
        {
            module.Latch(PainSuppressionActiveLatch);
            module.Clear(PainSuppressionCastLatch);
            module.Latch(PainSuppressionCastLatch, board.ObservedAtMs);
        }
    }
    else
        module.Clear(PainSuppressionActiveLatch);
}
}

#endif
