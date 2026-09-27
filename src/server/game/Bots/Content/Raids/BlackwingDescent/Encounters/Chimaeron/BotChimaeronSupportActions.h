#ifndef TRINITY_BOT_CHIMAERON_SUPPORT_ACTIONS_H
#define TRINITY_BOT_CHIMAERON_SUPPORT_ACTIONS_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronBurn.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronFormation.h"

#include <array>
#include <optional>

// Raid cooldowns, absorbs and the burn lust. Every action is an ordinary
// native cast of a spell the bot already knows; the executor rejects unknown
// spells, cooldowns and illegal targets.
//
// - Outage: after the knockout the raid has ~15 s before Caustic Slime
//   resumes (native reschedule +19 s from the Massacre event, 4 s cast), then
//   ~11 s of stacked Slimes until the Bile-O-Tron returns. The Discipline
//   Priest drops Power Word: Barrier on the stack as Slimes resume and the
//   Restoration Shaman follows with Spirit Link Totem for the second half.
// - Burn (BotChimaeronBurn.h): the lust owner lusts when the push starts
//   (release plus a settled handoff), the moment the non-tanks are released.
// - Mortality: absorbs still work, so the Discipline Priest shields the boss
//   victim whenever Weakened Soul allows and uses Pain Suppression on a failing
//   tank unless it was used within its 3 minute cooldown.
namespace BotEncounter::Chimaeron
{
constexpr uint32 PowerWordBarrierSpell = 62618;
constexpr uint32 PowerWordBarrierAura = 81782;
constexpr uint32 SpiritLinkTotemSpell = 98008;
constexpr uint32 PowerWordShieldSpell = 17;
constexpr uint32 WeakenedSoulAura = 6788;

// Feud remaining-time windows (Feud starts with the knockout).
constexpr uint32 BarrierWindowMaxMs = 16500;
constexpr uint32 BarrierWindowMinMs = 12000;
constexpr uint32 SpiritLinkWindowMaxMs = 11000;
constexpr uint32 SpiritLinkWindowMinMs = 7000;
constexpr float StackPresenceYards = 4.0f;

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

inline bool RaidLustLocked(Blackboard const& board)
{
    for (ActorSnapshot const& player : board.Players)
        for (uint32 spell : RaidHasteAndLockouts)
            if (HasAura(player, spell))
                return true;
    return false;
}

inline std::optional<CastDecision> DecideSupportCast(Blackboard const& board,
    Observation const& observation, Duties const& duties, ObjectGuid botGuid,
    BurnState const& burn, EncounterLatchView const* latches = nullptr)
{
    if (!observation.Boss || !observation.Bot)
        return std::nullopt;
    ActorSnapshot const& boss = *observation.Boss;
    Phase const phase = observation.CurrentPhase;

    if (botGuid == duties.LustOwner && duties.LustSpell && !RaidLustLocked(board))
    {
        if (phase == Phase::Mortality || burn.PushStarts())
            return CastDecision{ botGuid, duties.LustSpell, "burn_bloodlust" };
    }

    if (phase == Phase::Outage && observation.FeudRemainingMs)
    {
        uint32 const remaining = *observation.FeudRemainingMs;
        float const fromStack = Distance(ToPoint(observation.Bot->Position),
            StackCentre(FormationCentre(board, boss), UseStandoffColumn(board, duties)));
        if (botGuid == duties.BarrierOwner && fromStack <= StackPresenceYards
            && remaining <= BarrierWindowMaxMs && remaining >= BarrierWindowMinMs
            && !AnyAlivePlayerHasAura(board, PowerWordBarrierAura))
            return CastDecision{ botGuid, PowerWordBarrierSpell, "outage_power_word_barrier" };
        if (botGuid == duties.SpiritLinkOwner && fromStack <= StackPresenceYards
            && remaining <= SpiritLinkWindowMaxMs && remaining >= SpiritLinkWindowMinMs)
            return CastDecision{ botGuid, SpiritLinkTotemSpell, "outage_spirit_link_totem" };
    }

    if (phase == Phase::Mortality && botGuid == duties.BarrierOwner)
        if (ActorSnapshot const* victim = FindPlayer(board, boss.VictimGuid))
            if (victim->Alive)
            {
                // Shield whenever Weakened Soul allows; Pain Suppression only
                // outside its cooldown (the cohort latch remembers the cast).
                if (!HasAura(*victim, PowerWordShieldSpell)
                    && !HasAura(*victim, WeakenedSoulAura))
                    return CastDecision{ victim->Guid, PowerWordShieldSpell,
                        "mortality_victim_shield" };
                if (IsTank(duties, victim->Guid) && victim->HealthPct < 70.0f
                    && !PainSuppressionUsed(board, boss, latches))
                    return CastDecision{ victim->Guid, PainSuppressionSpell,
                        "mortality_pain_suppression" };
            }
    return std::nullopt;
}
}

#endif
