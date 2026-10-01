#ifndef TRINITY_BOT_CHIMAERON_HEALING_PLAN_H
#define TRINITY_BOT_CHIMAERON_HEALING_PLAN_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronDutyPlan.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <functional>
#include <cstdint>
#include <vector>

// Healing assignments.
//
// While the mixture is up every lethal hit leaves a protected player at 1
// health, so the job is a floor: nobody may sit at or below 10,000 health when
// the next Caustic Slime, boss swing or Massacre lands. The Double Attack tank
// is the exception: both halves of a doubled swing land back to back, so he is
// kept near full. Nothing else is healed while the mixture is up: every
// Massacre sets the raid back to 1 health, so health above the floor is lost
// mana (Wowhead: "heal everyone above 10,000"; Icy Veins: the Break tank to
// 10,000, the Double Attack tank to full). Round 3 spent 1.2 M healing between
// the first two Massacres topping the raid, and the healers reached the
// late outage dry (MixtureHealingHeld below). During an outage there is no
// floor: the raid is raised above the slime line first, then healed by health
// percentage. Under Mortality healing is 99% reduced and no heal target is
// published.
//
// Healers split the urgency list instead of all casting on its head: the tank
// healer (best single-target healer) takes the first tank entry, raid healers
// take the next entries in order. The boss victim at the floor gets two
// healers because his next swing is at most one attack interval away.
//
// After a Massacre everyone sits at 1 health and the next doubled swing lands
// about 9.5 s after it (13.5 s after the cast start). Both halves strike back
// to back, so the soaker must hold more than one hit plus the 10,000 floor;
// round 1 lost both tanks exactly there (the Feral at 34% and the Blood DK at
// 65% with Break stacks, healers busy on DPS at 1 health). No Caustic Slime
// lands before 19 s after the cast start, so in that window the first raid
// healer joins the tank healer on the soaker once the victim is off the floor.
namespace BotEncounter::Chimaeron
{
struct HealUrgency
{
    ObjectGuid Target;
    uint8 Tier = 0;
    float Key = 0.0f;
    bool Tank = false;
};

constexpr float SoakerTopUpPct = 95.0f;

// Outage slime line. Two Caustic Slimes land together (10N: 2 x 235,200
// Nature, 25N: 4 x 270,480) on different players. Each is split among the
// players whose centre is within 6 yd of its target (boss_chimaeron.cpp
// spell_chimaeron_caustic_slime; TARGET_UNIT_DEST_AREA_ENEMY, a 6 yd cylinder
// with no hitbox expansion for a generic spell). Round 3 (tier-11 gear)
// measured up to ~43k per member for one volley (batch 3: 133k over 10 plus
// 181k over 6, 0.3 s apart) and lost 7-8 members at 1-25k. Nothing protects a
// member without the mixture, so every living member is first raised above
// the most he can take plus a margin, lowest absolute health first; only then
// are members topped up by health percentage.
//
// The most a member can take is read from where the raid stands, not from a
// full stack: every living player whose splash reaches him is a possible
// slime target, each sharing its slime with the players inside its splash,
// and the volley's slimes land on his worst targets. A stack still forming or
// a displaced player therefore keeps a higher line. Positions move between
// the snapshot and the landing, so a member is reached a margin beyond the
// splash and a slime is shared only by players a margin inside it.
constexpr uint64 CausticSlimeDamage10 = 235200;
constexpr uint64 CausticSlimeDamage25 = 270480;
constexpr std::size_t CausticSlimeVolley10 = 2;
constexpr std::size_t CausticSlimeVolley25 = 4;
constexpr float CausticSlimeSplashYards = 6.0f;
constexpr float CausticSlimeSplashMarginYards = 1.0f;
constexpr uint64 OutageSlimeMarginHealth = 10000;
constexpr float OutageTopUpPct = 90.0f;

// Inside a Caustic Slime splash of this radius centred on a slime target: the
// native area check (planar distance and height difference, centre to centre).
inline bool WithinSlimeSplash(Vector3 const& target, Vector3 const& member, float radius)
{
    float const dx = target.X - member.X;
    float const dy = target.Y - member.Y;
    float const dz = target.Z - member.Z;
    return dx * dx + dy * dy <= radius * radius && std::abs(dz) <= radius;
}

inline uint64 OutageSlimeSafeHealth(Blackboard const& board, ActorSnapshot const& member)
{
    bool const raid25 = board.Players.size() > 10;
    uint64 const slime = raid25 ? CausticSlimeDamage25 : CausticSlimeDamage10;
    std::size_t const volley = raid25 ? CausticSlimeVolley25 : CausticSlimeVolley10;
    std::vector<uint64> shares;
    for (ActorSnapshot const& target : board.Players)
    {
        if (!target.Alive || !WithinSlimeSplash(target.Position, member.Position,
                CausticSlimeSplashYards + CausticSlimeSplashMarginYards))
            continue;
        uint64 sharing = 0;
        for (ActorSnapshot const& other : board.Players)
            if (other.Alive && WithinSlimeSplash(target.Position, other.Position,
                    CausticSlimeSplashYards - CausticSlimeSplashMarginYards))
                ++sharing;
        shares.push_back(slime / std::max<uint64>(sharing, 1));
    }
    // A living member always reaches himself; a member not alive on the
    // board is lined as a lone target.
    if (shares.empty())
        shares.push_back(slime);
    std::sort(shares.begin(), shares.end(), std::greater<uint64>());
    uint64 worst = 0;
    for (std::size_t index = 0; index < shares.size() && index < volley; ++index)
        worst += shares[index];
    return worst + OutageSlimeMarginHealth;
}

// The player who takes the next doubled swing: the Double Attack tank, or the
// boss victim once no second tank is left to taunt it.
inline ObjectGuid DoubleAttackSoaker(Blackboard const& board, Observation const& observation,
    Duties const& duties)
{
    if (IsAlivePlayer(board, duties.DoubleAttackTank))
        return duties.DoubleAttackTank;
    return observation.Boss ? observation.Boss->VictimGuid : ObjectGuid();
}

// The window in which healers pre-heal the soaker ahead of the raid floor.
inline bool SoakWindow(Observation const& observation)
{
    return observation.CurrentPhase == Phase::Mixture && observation.PostMassacreSoak;
}

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
    ObjectGuid const soaker = DoubleAttackSoaker(board, observation, duties);
    bool const soakDue = observation.DoubleAttackPending || SoakWindow(observation);
    // In the burn window the Break tank must reach the readiness bar (80%)
    // that releases the push; before it he only needs a buffer (60%).
    float const breakTankTopUpPct = observation.Boss->HealthPct <= BurnHoldMaxPct
        ? BurnReadyTankPct : 60.0f;
    // Feud pacifies his melee for the whole outage (the mixture returns 4 s
    // before Feud ends), so no swing is due: tanks are ordinary members of
    // the stack and the tank healer works the slime line with the others.
    bool const pacified = phase == Phase::Outage && observation.FeudActive;

    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive)
            continue;
        bool const isVictim = player.Guid == victim;
        bool const tank = !pacified && (IsTank(duties, player.Guid) || isVictim);
        bool const atFloor = player.Health <= FloorTargetHealth;
        // Tier 0: boss victim at the floor (next swing within one interval).
        // Tier 1: the soaker below full while a doubled swing is due (the
        //         charge is up, or a Massacre just rescheduled it).
        // Tier 2: mixture-protected member at the floor (absolute health).
        // Tier 3: outage, below the slime line (absolute health).
        // Tier 4: tank top-ups while the mixture is up.
        // Tier 5: outage top-up by health percentage.
        HealUrgency entry{ player.Guid, 255, 0.0f, tank };
        if (isVictim && atFloor && !pacified)
            entry = { player.Guid, 0, float(player.Health), tank };
        else if (!pacified && player.Guid == soaker
            && (soakDue || (isVictim && player.Guid == duties.DoubleAttackTank))
            && player.HealthPct < SoakerTopUpPct)
            entry = { player.Guid, 1, player.HealthPct, tank };
        else if (atFloor && HasAura(player, FinklesMixtureSpell))
            entry = { player.Guid, 2, float(player.Health), tank };
        else if (phase == Phase::Outage && player.Health < OutageSlimeSafeHealth(board, player))
            entry = { player.Guid, 3, float(player.Health), tank };
        else if (phase == Phase::Outage && player.HealthPct < OutageTopUpPct)
            entry = { player.Guid, 5, player.HealthPct, tank };
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
    // first raid healer; so is the soaker in the post-Massacre window, where
    // the later raid healers then start at the head of the raid floor.
    bool const soakCover = urgency.front().Tier == 1 && SoakWindow(observation);
    if (rank == 1 && (urgency.front().Tier == 0 || soakCover))
        return urgency.front().Target;

    std::vector<ObjectGuid> remaining;
    for (HealUrgency const& entry : urgency)
        if (entry.Target != tankPick.Target)
            remaining.push_back(entry.Target);
    if (remaining.empty())
        return tankPick.Target;
    std::size_t const slot = rank - 1 - (soakCover && tankPick.Target == urgency.front().Target
        ? 1 : 0);
    return remaining[slot % remaining.size()];
}

// The runtime heals the lowest member below 94% whenever no target is
// published. While the mixture is up that is the top-up the tactic rules
// out, so a healer with no published target holds for this revision (the
// plan sets HealingDisabled) and regenerates mana. A hostile other than the
// boss fighting the raid (a patrol on the composed route) lifts the hold.
inline bool MixtureHealingHeld(Blackboard const& board, Observation const& observation,
    ObjectGuid priorityTarget)
{
    return observation.Boss && observation.CurrentPhase == Phase::Mixture
        && priorityTarget.IsEmpty() && !OtherHostileEngaged(board, *observation.Boss);
}

// No floor, soak or slime-line entry: nothing is at risk right now (tank
// top-ups may remain). Raid mana cooldowns wait for this.
inline bool NoUrgentHealing(Blackboard const& board, Observation const& observation,
    Duties const& duties)
{
    for (HealUrgency const& entry : BuildHealUrgency(board, observation, duties))
        if (entry.Tier <= 3)
            return false;
    return true;
}
}

#endif
