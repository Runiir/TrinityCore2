#ifndef TRINITY_BOT_CHIMAERON_TANK_SWAP_H
#define TRINITY_BOT_CHIMAERON_TANK_SWAP_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronBurn.h"

#include <optional>
#include <string_view>

// Taunt exchange for Break and Double Attack.
//
// The Break tank holds the boss. Double Attack (88826) is a one-charge boss
// buff consumed by his next auto attack, which then strikes twice. While it is
// up and the Break tank is the victim, the Double Attack tank taunts so both
// halves land on a tank without Break stacks. Once the charge is gone the
// Break tank taunts back so Break never lands on the Double Attack tank.
// During Feud the boss is pacified: no exchange until the last 2.5 s of the
// aura, so the right tank is the victim when his melee resumes. Just before
// 20% the fresh Double Attack tank takes the boss into Mortality (Icy Veins
// 2024-07-29); under Mortality the boss is immune to taunt (client 82934).
// The handoff is the first step of the burn release (BotChimaeronBurn.h):
// before it the ordinary exchange continues whatever the boss health, so Break
// never piles onto the tank that must enter Mortality; after it the Break tank
// never taunts back.
namespace BotEncounter::Chimaeron
{
constexpr uint32 FeudTauntLeadMs = 2500;

inline uint32 TauntSpellFor(std::string_view spec)
{
    if (spec == "blood_death_knight" || spec == "frost_death_knight"
        || spec == "unholy_death_knight")
        return 56222;  // Dark Command
    if (spec == "feral_druid_tank" || spec == "feral_druid_dps")
        return 6795;   // Growl
    if (spec == "protection_paladin" || spec == "retribution_paladin"
        || spec == "holy_paladin")
        return 62124;  // Hand of Reckoning
    if (spec == "protection_warrior" || spec == "arms_warrior"
        || spec == "fury_warrior")
        return 355;    // Taunt
    return 0;
}

struct TauntDecision
{
    uint32 SpellId = 0;
    char const* Reason = "";
};

inline std::optional<TauntDecision> DecideTaunt(Blackboard const& board,
    Observation const& observation, Duties const& duties, ObjectGuid botGuid,
    BurnState const& burn)
{
    if (!observation.Boss || !observation.Bot
        || (observation.CurrentPhase != Phase::Mixture
            && observation.CurrentPhase != Phase::Outage))
        return std::nullopt;
    if (!IsTank(duties, botGuid))
        return std::nullopt;
    ActorSnapshot const& boss = *observation.Boss;
    ObjectGuid const victim = boss.VictimGuid;
    if (victim.IsEmpty() || victim == botGuid)
        return std::nullopt;
    uint32 const spell = TauntSpellFor(observation.Bot->ClassSpec);
    if (!spell)
        return std::nullopt;

    // Once the handoff arms (release, last chance, hold cap or healers down)
    // the Double Attack tank owns the boss until Mortality: he takes it (the
    // first armed action) and retakes it from anyone, even during Feud.
    // Taunting the pacified boss is harmless and sets exactly the victim his
    // melee must resume on; Feud follows a Systems Failure, which is when an
    // unready raid arms by last chance or a bounded hold. The Break tank never
    // taunts him back; after a failed handoff (timeout) he only recovers a
    // non-tank victim, and the retry shows as its own mechanic in the trace.
    bool const feudHold = observation.FeudActive
        && (!observation.FeudRemainingMs || *observation.FeudRemainingMs > FeudTauntLeadMs);
    if (burn.Armed() && IsAlivePlayer(board, duties.DoubleAttackTank))
    {
        if (botGuid == duties.DoubleAttackTank)
            return TauntDecision{ spell, burn.HandoffFailed()
                ? "taunt_mortality_handoff_retry" : "taunt_mortality_handoff" };
        if (!feudHold && burn.HandoffFailed() && !IsTank(duties, victim))
            return TauntDecision{ spell, "taunt_recover_non_tank_victim" };
        return std::nullopt;
    }

    // Unarmed, Feud pacifies the boss: no exchange until its last 2.5 s.
    if (feudHold)
        return std::nullopt;

    // Anyone but a tank holding the boss (a wake-up pick, a pet growl, a dead
    // tank's replacement) is taken back by the first living tank in order.
    if (!IsTank(duties, victim))
    {
        ObjectGuid const owner = IsAlivePlayer(board, duties.BreakTank)
            ? duties.BreakTank : duties.DoubleAttackTank;
        if (owner == botGuid)
            return TauntDecision{ spell, "taunt_recover_non_tank_victim" };
        return std::nullopt;
    }

    if (botGuid == duties.DoubleAttackTank && victim == duties.BreakTank)
    {
        if (observation.DoubleAttackPending)
            return TauntDecision{ spell, "taunt_double_attack_soak" };
        return std::nullopt;
    }
    if (botGuid == duties.BreakTank && victim == duties.DoubleAttackTank
        && !observation.DoubleAttackPending && !burn.Armed())
        return TauntDecision{ spell, "taunt_back_break_holder" };
    return std::nullopt;
}
}

#endif
