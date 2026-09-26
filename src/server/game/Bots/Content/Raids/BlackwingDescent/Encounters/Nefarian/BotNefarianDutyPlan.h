#ifndef TRINITY_BOT_NEFARIAN_DUTY_PLAN_H
#define TRINITY_BOT_NEFARIAN_DUTY_PLAN_H

// Capability-based duty plan for Nefarian's End. Duties come from the roster's
// role and class/spec, never from fixed roster slots, so any composition with
// two tanks and interrupt-capable members resolves. The plan is a pure
// function of the blackboard's bot list (external humans never receive a
// duty), stable across ticks: pillar teams are built from the whole roster,
// dead members included, so a death never reshuffles the platforms; only the
// live duties (tanks, the warrior handler, the per-team interrupter and
// off-healer, the shackler) skip the dead.

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianCapabilities.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <sstream>
#include <string>
#include <vector>

namespace BotEncounter::Nefarian
{
struct PillarTeam
{
    std::vector<ObjectGuid> Members; // slot order
    ObjectGuid Healer;
    ObjectGuid PrimaryInterrupter;
    ObjectGuid BackupInterrupter;
    // A team without a healer: the living hybrid that off-heals it.
    ObjectGuid OffHealer;
    uint8 DamageDealers = 0;
};

struct DutyPlan
{
    bool Applies = false;
    ObjectGuid NefarianTank;
    ObjectGuid OnyxiaTank;
    std::array<PillarTeam, 3> Pillars;
    ObjectGuid Shackler;
    // Kites the bone warriors and roots them with Nature's Grasp once its
    // dragon is dead (user raid experience 2026-09-26): the Onyxia tank.
    ObjectGuid WarriorHandler;
    // The pillar without a healer, where both tanks stand and heal themselves
    // (user raid experience 2026-09-26, round 8); -1 with three healers.
    int TankPillar = -1;

    int PillarOf(ObjectGuid guid) const
    {
        for (std::size_t index = 0; index < Pillars.size(); ++index)
            for (ObjectGuid member : Pillars[index].Members)
                if (member == guid)
                    return int(index);
        return -1;
    }

    uint8 SlotOf(ObjectGuid guid) const
    {
        int const pillar = PillarOf(guid);
        if (pillar < 0)
            return 0;
        auto const& members = Pillars[pillar].Members;
        return uint8(std::find(members.begin(), members.end(), guid)
            - members.begin());
    }

    bool IsTank(ObjectGuid guid) const
    {
        return !guid.IsEmpty() && (guid == NefarianTank || guid == OnyxiaTank);
    }
};

inline bool DutyGuidLess(ActorSnapshot const* left, ActorSnapshot const* right)
{
    return left->Guid.GetCounter() < right->Guid.GetCounter();
}

inline DutyPlan BuildNefarianDutyPlan(Blackboard const& board)
{
    DutyPlan plan;
    std::vector<ActorSnapshot const*> members;
    for (ActorSnapshot const& player : board.Players)
        members.push_back(&player);
    std::sort(members.begin(), members.end(), DutyGuidLess);
    if (members.empty())
        return plan;
    plan.Applies = true;

    // Tanks: the best living Nefarian tank by capability, then the next
    // living tank for Onyxia.
    std::vector<ActorSnapshot const*> tanks;
    for (ActorSnapshot const* member : members)
        if (member->Role == "tank" && member->Alive)
            tanks.push_back(member);
    std::stable_sort(tanks.begin(), tanks.end(), [](auto left, auto right)
    {
        return NefarianTankRank(left->ClassSpec)
            < NefarianTankRank(right->ClassSpec);
    });
    if (!tanks.empty())
        plan.NefarianTank = tanks[0]->Guid;
    if (tanks.size() > 1)
        plan.OnyxiaTank = tanks[1]->Guid;
    plan.WarriorHandler = plan.OnyxiaTank;

    // Pillar teams (round 8, user raid experience 2026-09-26, followed
    // literally): with two healers the tanks - and only the tanks - take the
    // healerless pillar and heal themselves (the Blood DK's Death Strike, the
    // Feral's Frenzied Regeneration); each other pillar gets one healer. Then
    // a 13-second interrupter wherever the team lacks one (the tank pillar
    // has Mind Freeze), and the rest balance the healer pillars' prototype
    // damage.
    // Teams come from the whole roster, dead members included, so a death
    // never reshuffles the platforms.
    std::array<uint32, 3> bestCooldown{ 0, 0, 0 };
    std::array<float, 3> damage{ 0.0f, 0.0f, 0.0f };
    auto place = [&plan, &bestCooldown, &damage](ActorSnapshot const* member,
        std::size_t pillar)
    {
        PillarTeam& team = plan.Pillars[pillar];
        team.Members.push_back(member->Guid);
        InterruptCapability const interrupt = InterruptFor(member->ClassSpec);
        if (interrupt.Known() && (!bestCooldown[pillar]
                || interrupt.CooldownMs < bestCooldown[pillar]))
            bestCooldown[pillar] = interrupt.CooldownMs;
        if (member->Role == "dps")
            ++team.DamageDealers;
        damage[pillar] += PillarDamageWeight(member->ClassSpec, member->Role);
    };

    std::vector<ActorSnapshot const*> rest;
    std::size_t healers = 0;
    for (ActorSnapshot const* member : members)
    {
        if (healers < plan.Pillars.size()
            && IsHealerSpec(member->ClassSpec, member->Role))
        {
            plan.Pillars[healers].Healer = member->Guid;
            place(member, healers++);
        }
        else
            rest.push_back(member);
    }
    if (healers < plan.Pillars.size())
    {
        plan.TankPillar = int(healers);
        // Both roster tanks (dead or alive), the Nefarian tank first.
        std::vector<ActorSnapshot const*> rosterTanks;
        for (ActorSnapshot const* member : rest)
            if (member->Role == "tank")
                rosterTanks.push_back(member);
        std::stable_sort(rosterTanks.begin(), rosterTanks.end(), [](auto left, auto right)
        {
            return NefarianTankRank(left->ClassSpec) < NefarianTankRank(right->ClassSpec);
        });
        for (ActorSnapshot const* tank : rosterTanks)
        {
            place(tank, std::size_t(plan.TankPillar));
            rest.erase(std::find(rest.begin(), rest.end(), tank));
        }
    }

    std::stable_sort(rest.begin(), rest.end(), [](auto left, auto right)
    {
        InterruptCapability const a = InterruptFor(left->ClassSpec);
        InterruptCapability const b = InterruptFor(right->ClassSpec);
        uint32 const aCooldown = a.Known() ? a.CooldownMs : 1000000u;
        uint32 const bCooldown = b.Known() ? b.CooldownMs : 1000000u;
        if (aCooldown != bCooldown)
            return aCooldown < bCooldown;
        return IsMeleeInterrupt(a) && !IsMeleeInterrupt(b);
    });

    constexpr uint32 BlastNovaRepeatMs = 13000;
    for (ActorSnapshot const* member : rest)
    {
        InterruptCapability const interrupt = InterruptFor(member->ClassSpec);
        std::size_t target = plan.Pillars.size();
        if (interrupt.Known() && interrupt.CooldownMs <= BlastNovaRepeatMs)
        {
            // Cover the pillar whose best interrupt is worst.
            uint32 worst = BlastNovaRepeatMs;
            for (std::size_t pillar = 0; pillar < plan.Pillars.size(); ++pillar)
            {
                uint32 const cooldown = bestCooldown[pillar]
                    ? bestCooldown[pillar] : 0xFFFFFFFFu;
                if (cooldown > worst)
                {
                    worst = cooldown;
                    target = pillar;
                }
            }
        }
        if (target == plan.Pillars.size())
        {
            // The healer pillar whose prototype would die last (least damage),
            // the smaller team on a tie. The tank pillar is the tanks' alone
            // (the user's tactic); the healer pillars finish first and send
            // help.
            target = plan.Pillars.size();
            for (std::size_t pillar = 0; pillar < plan.Pillars.size(); ++pillar)
            {
                if (int(pillar) == plan.TankPillar)
                    continue;
                if (target == plan.Pillars.size())
                {
                    target = pillar;
                    continue;
                }
                PillarTeam const& candidate = plan.Pillars[pillar];
                PillarTeam const& best = plan.Pillars[target];
                if (damage[pillar] < damage[target] - 0.01f
                    || (std::fabs(damage[pillar] - damage[target]) <= 0.01f
                        && candidate.Members.size() < best.Members.size()))
                    target = pillar;
            }
            if (target == plan.Pillars.size())
                target = 0;
        }
        place(member, target);
    }

    // Interrupters: a living non-healer with the shortest cooldown, melee
    // first; the backup is the next living interrupter on the same pillar.
    for (std::size_t index = 0; index < plan.Pillars.size(); ++index)
    {
        PillarTeam& team = plan.Pillars[index];
        // The tank pillar interrupts with its tanks (user raid experience
        // 2026-09-26: Mind Freeze and Skull Bash); the Blood DK's 10-second
        // Mind Freeze keeps it within the 13-second Blast Nova repeat.
        bool const tankPillar = int(index) == plan.TankPillar;
        std::vector<ActorSnapshot const*> capable;
        for (ObjectGuid guid : team.Members)
            if (ActorSnapshot const* member = board.FindActor(guid))
                if (member->Alive && InterruptFor(member->ClassSpec).Known())
                    capable.push_back(member);
        std::stable_sort(capable.begin(), capable.end(),
            [&team, tankPillar](auto left, auto right)
        {
            if (tankPillar && (left->Role == "tank") != (right->Role == "tank"))
                return left->Role == "tank";
            InterruptCapability const a = InterruptFor(left->ClassSpec);
            InterruptCapability const b = InterruptFor(right->ClassSpec);
            if (a.CooldownMs != b.CooldownMs)
                return a.CooldownMs < b.CooldownMs;
            bool const aHealer = left->Guid == team.Healer;
            bool const bHealer = right->Guid == team.Healer;
            if (aHealer != bHealer)
                return !aHealer;
            return IsMeleeInterrupt(a) && !IsMeleeInterrupt(b);
        });
        if (!capable.empty())
            team.PrimaryInterrupter = capable[0]->Guid;
        if (capable.size() > 1)
            team.BackupInterrupter = capable[1]->Guid;
        if (team.Healer.IsEmpty())
            for (ObjectGuid guid : team.Members)
                if (ActorSnapshot const* member = board.FindActor(guid))
                    if (member->Alive && !plan.IsTank(guid) && OffHealFor(member->ClassSpec))
                    {
                        team.OffHealer = guid;
                        break;
                    }
    }

    // Shackle Undead backup: the first living member whose spec has it.
    for (ActorSnapshot const* member : members)
        if (member->Alive && !plan.IsTank(member->Guid)
            && ControlFor(member->ClassSpec).Kind == ControlKind::Shackle)
        {
            plan.Shackler = member->Guid;
            break;
        }
    return plan;
}

inline std::string NefarianDutyPlanJson(DutyPlan const& plan)
{
    std::ostringstream json;
    json << "{\"applies\":" << (plan.Applies ? "true" : "false");
    if (plan.Applies)
    {
        json << ",\"nefarian_tank\":" << plan.NefarianTank.GetCounter()
             << ",\"onyxia_tank\":" << plan.OnyxiaTank.GetCounter()
             << ",\"shackler\":" << plan.Shackler.GetCounter()
             << ",\"pillars\":[";
        for (std::size_t index = 0; index < plan.Pillars.size(); ++index)
        {
            PillarTeam const& team = plan.Pillars[index];
            json << (index ? "," : "") << "{\"members\":[";
            for (std::size_t member = 0; member < team.Members.size(); ++member)
                json << (member ? "," : "") << team.Members[member].GetCounter();
            json << "],\"healer\":" << team.Healer.GetCounter()
                 << ",\"interrupt\":" << team.PrimaryInterrupter.GetCounter()
                 << ",\"backup\":" << team.BackupInterrupter.GetCounter()
                 << ",\"off_healer\":" << team.OffHealer.GetCounter() << '}';
        }
        json << "],\"warrior_handler\":" << plan.WarriorHandler.GetCounter()
             << ",\"tank_pillar\":" << plan.TankPillar;
    }
    json << '}';
    return json.str();
}
}

#endif
