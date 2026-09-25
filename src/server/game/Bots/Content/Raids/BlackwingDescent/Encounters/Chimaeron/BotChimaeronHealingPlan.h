#ifndef TRINITY_BOT_CHIMAERON_HEALING_PLAN_H
#define TRINITY_BOT_CHIMAERON_HEALING_PLAN_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronDutyPlan.h"

#include <algorithm>
#include <cstdint>
#include <vector>

// Healing assignments.
//
// While the mixture is up every lethal hit leaves a protected player at 1
// health, so the job is a floor: nobody may sit at or below 10,000 health when
// the next Caustic Slime, boss swing or Massacre lands. The Double Attack tank
// is the exception: both halves of a doubled swing land back to back, so he is
// kept near full. During an outage there is no floor and the raid is healed by
// health percentage. Under Mortality healing is 99% reduced and no heal target
// is published.
//
// Healers split the urgency list instead of all casting on its head: the tank
// healer (best single-target healer) takes the first tank entry, raid healers
// take the next entries in order. The boss victim at the floor gets two
// healers because his next swing is at most one attack interval away.
namespace BotEncounter::Chimaeron
{
struct HealUrgency
{
    ObjectGuid Target;
    uint8 Tier = 0;
    float Key = 0.0f;
    bool Tank = false;
};

inline std::vector<HealUrgency> BuildHealUrgency(Blackboard const& board,
    Observation const& observation, Duties const& duties)
{
    std::vector<HealUrgency> urgency;
    if (!observation.Boss)
        return urgency;
    Phase const phase = observation.CurrentPhase;
    if (phase != Phase::Mixture && phase != Phase::Outage)
        return urgency;
    ObjectGuid const victim = observation.Boss->VictimGuid;
    // In the burn window the Break tank must reach the readiness bar (80%)
    // that releases the push; before it he only needs a buffer (60%).
    float const breakTankTopUpPct = observation.Boss->HealthPct <= BurnHoldMaxPct
        ? BurnReadyTankPct : 60.0f;

    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive)
            continue;
        bool const isVictim = player.Guid == victim;
        bool const tank = IsTank(duties, player.Guid) || isVictim;
        bool const atFloor = player.Health <= FloorTargetHealth;
        // Tier 0: boss victim at the floor (next swing within one interval).
        // Tier 1: Double Attack tank below full while a doubled swing is due.
        // Tier 2: mixture-protected member at the floor (absolute health).
        // Tier 3: outage, by health percentage.
        // Tier 4: tank top-ups while the mixture is up.
        HealUrgency entry{ player.Guid, 255, 0.0f, tank };
        if (isVictim && atFloor)
            entry = { player.Guid, 0, float(player.Health), tank };
        else if (player.Guid == duties.DoubleAttackTank
            && (observation.DoubleAttackPending || isVictim)
            && player.HealthPct < 95.0f)
            entry = { player.Guid, 1, player.HealthPct, tank };
        else if (atFloor && HasAura(player, FinklesMixtureSpell))
            entry = { player.Guid, 2, float(player.Health), tank };
        else if (phase == Phase::Outage && player.HealthPct < 90.0f)
            entry = { player.Guid, 3, player.HealthPct, tank };
        else if (phase == Phase::Mixture && player.Guid == duties.DoubleAttackTank
            && player.HealthPct < 90.0f)
            entry = { player.Guid, 4, player.HealthPct, tank };
        else if (phase == Phase::Mixture && player.Guid == duties.BreakTank
            && player.HealthPct < breakTankTopUpPct)
            entry = { player.Guid, 4, player.HealthPct, tank };
        if (entry.Tier != 255)
            urgency.push_back(entry);
    }
    std::stable_sort(urgency.begin(), urgency.end(),
        [](HealUrgency const& left, HealUrgency const& right)
        {
            if (left.Tier != right.Tier)
                return left.Tier < right.Tier;
            if (left.Key != right.Key)
                return left.Key < right.Key;
            return left.Target.GetRawValue() < right.Target.GetRawValue();
        });
    return urgency;
}

// Healer order for this bot: capability order from the duties; the acting
// bot is appended when the runtime role says healer but the roster does not.
inline std::vector<ObjectGuid> HealerOrder(Duties const& duties, ObjectGuid botGuid)
{
    std::vector<ObjectGuid> healers = duties.Healers;
    if (std::find(healers.begin(), healers.end(), botGuid) == healers.end())
        healers.push_back(botGuid);
    return healers;
}

inline ObjectGuid SelectPriorityHealTarget(Blackboard const& board,
    Observation const& observation, Duties const& duties, ObjectGuid botGuid)
{
    std::vector<HealUrgency> const urgency = BuildHealUrgency(board, observation, duties);
    if (urgency.empty())
        return ObjectGuid();
    std::vector<ObjectGuid> const healers = HealerOrder(duties, botGuid);
    std::size_t const rank = std::size_t(
        std::find(healers.begin(), healers.end(), botGuid) - healers.begin());

    auto tankEntry = std::find_if(urgency.begin(), urgency.end(),
        [](HealUrgency const& entry) { return entry.Tank; });
    HealUrgency const& tankPick = tankEntry != urgency.end() ? *tankEntry : urgency.front();
    if (rank == 0)
        return tankPick.Target;
    // The boss victim at the floor is covered by the tank healer and the
    // first raid healer.
    if (rank == 1 && urgency.front().Tier == 0)
        return urgency.front().Target;

    std::vector<ObjectGuid> remaining;
    for (HealUrgency const& entry : urgency)
        if (entry.Target != tankPick.Target)
            remaining.push_back(entry.Target);
    if (remaining.empty())
        return tankPick.Target;
    return remaining[(rank - 1) % remaining.size()];
}
}

#endif
