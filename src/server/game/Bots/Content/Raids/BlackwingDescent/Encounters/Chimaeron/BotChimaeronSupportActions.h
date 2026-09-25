#ifndef TRINITY_BOT_CHIMAERON_SUPPORT_ACTIONS_H
#define TRINITY_BOT_CHIMAERON_SUPPORT_ACTIONS_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronFormation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronMemory.h"

#include <array>
#include <optional>

// Raid cooldowns, absorbs and the burn window. Every action is an ordinary
// native cast of a spell the bot already knows; the executor rejects unknown
// spells, cooldowns and illegal targets.
//
// - Outage: after the knockout the raid has ~15 s before Caustic Slime
//   resumes (native reschedule +19 s from the Massacre event, 4 s cast), then
//   ~11 s of stacked Slimes until the Bile-O-Tron returns. The Discipline
//   Priest drops Power Word: Barrier on the stack as Slimes resume and the
//   Restoration Shaman follows with Spirit Link Totem for the second half.
// - Burn window: both guides hold damage around 22-25% until the raid is safe
//   (no Massacre in flight, tanks healthy, mixture up), then Bloodlust and push
//   through 20%. Mortality (-99% healing) makes the entry state final. Once
//   released (ready raid, lust, damage-over-time creep past the floor, or
//   Mortality) the hold is latched off for the scope: a swing on a tank
//   mid-burn cannot stop the push while the lust runs.
// - Mortality: absorbs still work, so the Discipline Priest shields the boss
//   victim (Power Word: Shield whenever Weakened Soul allows) and uses Pain
//   Suppression once on a failing tank.
namespace BotEncounter::Chimaeron
{
constexpr uint32 PowerWordBarrierSpell = 62618;
constexpr uint32 PowerWordBarrierAura = 81782;
constexpr uint32 SpiritLinkTotemSpell = 98008;
constexpr uint32 PowerWordShieldSpell = 17;
constexpr uint32 WeakenedSoulAura = 6788;
constexpr uint32 PainSuppressionSpell = 33206;

// Feud remaining-time windows (Feud starts with the knockout).
constexpr uint32 BarrierWindowMaxMs = 16500;
constexpr uint32 BarrierWindowMinMs = 12000;
constexpr uint32 SpiritLinkWindowMaxMs = 11000;
constexpr uint32 SpiritLinkWindowMinMs = 7000;
constexpr float StackPresenceYards = 4.0f;

constexpr uint32 BurnHoldMassacreLeadMs = 8000;

constexpr std::array<uint32, 4> RaidHasteAuras = { 2825, 32182, 80353, 90355 };
constexpr std::array<uint32, 8> RaidHasteAndLockouts = {
    2825, 32182, 80353, 90355,      // active Bloodlust/Heroism/Time Warp/Ancient Hysteria
    57723, 57724, 80354, 95809,     // Exhaustion/Sated/Temporal Displacement/Insanity
};

struct CastDecision
{
    ObjectGuid Target;
    uint32 SpellId = 0;
    char const* Reason = "";
};

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

inline bool RaidLustLocked(Blackboard const& board)
{
    for (ActorSnapshot const& player : board.Players)
        for (uint32 spell : RaidHasteAndLockouts)
            if (HasAura(player, spell))
                return true;
    return false;
}

inline bool AnyPlayerHasAura(Blackboard const& board, uint32 spellId)
{
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && HasAura(player, spellId))
            return true;
    return false;
}

inline bool RaidHasteActive(Blackboard const& board)
{
    for (uint32 spell : RaidHasteAuras)
        if (AnyPlayerHasAura(board, spell))
            return true;
    return false;
}

// This revision releases the burn: Mortality already started, damage over
// time pushed the boss past the hold floor, a raid lust is running inside the
// window, or the raid is ready inside the window.
inline bool BurnReleaseObserved(Blackboard const& board, Observation const& observation,
    Duties const& duties)
{
    if (!observation.Boss)
        return false;
    if (observation.CurrentPhase == Phase::Mortality)
        return true;
    float const pct = observation.Boss->HealthPct;
    if (pct > BurnHoldMaxPct)
        return false;
    return pct <= BurnHoldFloorPct || RaidHasteActive(board)
        || BurnReady(board, observation, duties);
}

// The burn is released now or was released earlier in this scope. Without
// memory (replays) only the current revision counts.
inline bool BurnReleased(Blackboard const& board, Observation const& observation,
    Duties const& duties, ChimaeronEncounterMemory const* memory)
{
    return (memory && memory->BurnReleased)
        || BurnReleaseObserved(board, observation, duties);
}

inline bool BurnHold(Blackboard const& board, Observation const& observation,
    Duties const& duties, ChimaeronEncounterMemory const* memory = nullptr)
{
    if (!observation.Boss || (observation.CurrentPhase != Phase::Mixture
            && observation.CurrentPhase != Phase::Outage))
        return false;
    float const pct = observation.Boss->HealthPct;
    return pct <= BurnHoldMaxPct && pct > BurnHoldFloorPct
        && !BurnReleased(board, observation, duties, memory);
}

inline std::optional<CastDecision> DecideSupportCast(Blackboard const& board,
    Observation const& observation, Duties const& duties, ObjectGuid botGuid,
    ChimaeronEncounterMemory const* memory = nullptr)
{
    if (!observation.Boss || !observation.Bot)
        return std::nullopt;
    ActorSnapshot const& boss = *observation.Boss;
    Phase const phase = observation.CurrentPhase;

    if (botGuid == duties.LustOwner && duties.LustSpell && !RaidLustLocked(board))
    {
        bool const burnEntry = phase == Phase::Mixture
            && boss.HealthPct <= BurnHoldMaxPct
            && BurnReleased(board, observation, duties, memory);
        if (phase == Phase::Mortality || burnEntry)
            return CastDecision{ botGuid, duties.LustSpell, "burn_bloodlust" };
    }

    if (phase == Phase::Outage && observation.FeudRemainingMs)
    {
        uint32 const remaining = *observation.FeudRemainingMs;
        float const fromStack = Distance(ToPoint(observation.Bot->Position),
            StackCentre(FormationCentre(board, boss)));
        if (botGuid == duties.BarrierOwner && fromStack <= StackPresenceYards
            && remaining <= BarrierWindowMaxMs && remaining >= BarrierWindowMinMs
            && !AnyPlayerHasAura(board, PowerWordBarrierAura))
            return CastDecision{ botGuid, PowerWordBarrierSpell, "outage_power_word_barrier" };
        if (botGuid == duties.SpiritLinkOwner && fromStack <= StackPresenceYards
            && remaining <= SpiritLinkWindowMaxMs && remaining >= SpiritLinkWindowMinMs)
            return CastDecision{ botGuid, SpiritLinkTotemSpell, "outage_spirit_link_totem" };
    }

    if (phase == Phase::Mortality && botGuid == duties.BarrierOwner)
        if (ActorSnapshot const* victim = FindPlayer(board, boss.VictimGuid))
            if (victim->Alive)
            {
                // Shield whenever Weakened Soul allows; Pain Suppression (3 min
                // cooldown, invisible on the blackboard) only once per scope.
                if (!HasAura(*victim, PowerWordShieldSpell)
                    && !HasAura(*victim, WeakenedSoulAura))
                    return CastDecision{ victim->Guid, PowerWordShieldSpell,
                        "mortality_victim_shield" };
                bool const suppressionUsed = (memory && memory->PainSuppressionObserved)
                    || AnyPlayerHasAura(board, PainSuppressionSpell);
                if (IsTank(duties, victim->Guid) && victim->HealthPct < 70.0f
                    && !suppressionUsed)
                    return CastDecision{ victim->Guid, PainSuppressionSpell,
                        "mortality_pain_suppression" };
            }
    return std::nullopt;
}
}

#endif
