#ifndef TRINITY_BOT_CHIMAERON_SUPPORT_ACTIONS_H
#define TRINITY_BOT_CHIMAERON_SUPPORT_ACTIONS_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronBurn.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronFormation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronHealingPlan.h"

#include <array>
#include <optional>
#include <string_view>

// Raid cooldowns, absorbs and the burn lust. Every action is an ordinary
// native cast of a spell the bot already knows; the executor rejects unknown
// spells, cooldowns and illegal targets.
//
// - Outage: after the knockout the raid has ~15 s before Caustic Slime
//   resumes (native reschedule +19 s from the Massacre event, 4 s cast), then
//   two stacked Slime volleys (Feud at ~15 s and ~9 s left; 6 s repeat, WCL)
//   until the Bile-O-Tron returns. The Discipline Priest drops Power Word:
//   Barrier on the stack for the first volley and the Restoration Shaman
//   follows with Spirit Link Totem for the second. A second outage within
//   their 3 minute cooldowns gets neither: the executor rejects the cast and
//   the healers keep healing by health percentage.
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

// Feud remaining-time windows (Feud starts with the knockout). WCL 10N: the
// volleys land 17.2-17.7 s and 23.0-23.8 s after the Massacre completion,
// i.e. at 12.3-12.8 s and 6.2-7.0 s of Feud left. Barrier lasts 10 s, so it
// is cast at 15.5-12.5 s left to cover both volleys (the round-2 window
// opened at 16.5 s, which could expire just before the second volley).
constexpr uint32 BarrierWindowMaxMs = 15500;
constexpr uint32 BarrierWindowMinMs = 12500;
constexpr uint32 SpiritLinkWindowMaxMs = 11000;
constexpr uint32 SpiritLinkWindowMinMs = 7000;
constexpr float StackPresenceYards = 4.0f;

// Healer mana cooldowns, cast by the healer who knows them while the mixture
// is up and nothing is at the floor, so the healers reach the predictable
// late outage (10N: never after the first Massacre of a cycle, always by the
// third) with mana. Divine Plea halves healing done for 9 s, so it must end
// before the next Massacre lands (cast start + 4 s): the timer must show at
// least ManaCooldownMassacreClearMs. The runtime casts one only below its
// own mana line (ManaCooldownWanted; the snapshot carries no mana).
constexpr uint32 DivinePleaSpell = 54428;
constexpr uint32 ManaTideTotemSpell = 16190;
constexpr uint32 ManaCooldownMassacreClearMs = 10000;
constexpr float DivinePleaManaPct = 85.0f;
constexpr float ManaTideManaPct = 75.0f;

inline bool IsManaCooldownSpell(uint32 spellId)
{
    return spellId == DivinePleaSpell || spellId == ManaTideTotemSpell;
}

inline bool ManaCooldownWanted(uint32 spellId, float manaPct)
{
    if (spellId == DivinePleaSpell)
        return manaPct < DivinePleaManaPct;
    if (spellId == ManaTideTotemSpell)
        return manaPct < ManaTideManaPct;
    return false;
}

constexpr char const* ManaCooldownNotNeededReason = "chimaeron_mana_cooldown_not_needed";

inline uint32 OwnManaCooldown(std::string_view spec)
{
    if (spec == "holy_paladin")
        return DivinePleaSpell;
    if (spec == "restoration_shaman")
        return ManaTideTotemSpell;
    return 0;
}

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

    if (phase == Phase::Mixture && !observation.MassacreCasting
        && observation.MassacreInMs && *observation.MassacreInMs >= ManaCooldownMassacreClearMs
        && boss.HealthPct > BurnHoldMaxPct)
        if (uint32 const spell = OwnManaCooldown(observation.Bot->ClassSpec))
            if (NoUrgentHealing(board, observation, duties))
                return CastDecision{ botGuid, spell, spell == DivinePleaSpell
                    ? "mixture_divine_plea" : "mixture_mana_tide_totem" };
    return std::nullopt;
}
}

#endif
