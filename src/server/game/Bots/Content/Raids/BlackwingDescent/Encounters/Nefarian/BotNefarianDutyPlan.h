#ifndef TRINITY_BOT_NEFARIAN_DUTY_PLAN_H
#define TRINITY_BOT_NEFARIAN_DUTY_PLAN_H

// Capability-based duty plan for Nefarian's End. Duties come from the roster's
// role and class/spec, never from fixed roster slots, so any composition with
// two tanks and interrupt-capable members resolves. The plan is a pure
// function of the blackboard's bot list (external humans never receive a
// duty), stable across ticks: pillar teams include dead members so a death
// never reshuffles the platforms, and only the per-team interrupter and the
// bone warrior controllers skip the dead.

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianCapabilities.h"
#include <algorithm>
#include <array>
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
    uint8 DamageDealers = 0;
};

struct DutyPlan
{
    bool Applies = false;
    ObjectGuid NefarianTank;
    ObjectGuid OnyxiaTank;
    std::array<PillarTeam, 3> Pillars;
    ObjectGuid Shackler;
    std::vector<ObjectGuid> Controllers; // capability order

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

    // Pillar teams: one healer each, then a 13-second interrupter where the
    // healer cannot provide one, then balance head count and damage dealers.
    std::array<uint32, 3> bestCooldown{ 0, 0, 0 };
    auto place = [&plan, &bestCooldown](ActorSnapshot const* member,
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
            target = 0;
            for (std::size_t pillar = 1; pillar < plan.Pillars.size(); ++pillar)
            {
                PillarTeam const& candidate = plan.Pillars[pillar];
                PillarTeam const& best = plan.Pillars[target];
                if (candidate.Members.size() < best.Members.size()
                    || (candidate.Members.size() == best.Members.size()
                        && candidate.DamageDealers < best.DamageDealers))
                    target = pillar;
            }
        }
        place(member, target);
    }

    // Interrupters: a living non-healer with the shortest cooldown, melee
    // first; the backup is the next living interrupter on the same pillar.
    for (PillarTeam& team : plan.Pillars)
    {
        std::vector<ActorSnapshot const*> capable;
        for (ObjectGuid guid : team.Members)
            if (ActorSnapshot const* member = board.FindActor(guid))
                if (member->Alive && InterruptFor(member->ClassSpec).Known())
                    capable.push_back(member);
        std::stable_sort(capable.begin(), capable.end(),
            [&team](auto left, auto right)
        {
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
    }

    // Bone warrior control: one living shackler, then every other living
    // non-tank with a stun, snare or root, in ControlPreference order (stuns,
    // roots, cooldown-free snares, then snares with a cooldown).
    for (ActorSnapshot const* member : members)
    {
        if (!member->Alive || plan.IsTank(member->Guid))
            continue;
        ControlCapability const control = ControlFor(member->ClassSpec);
        if (!control.Known())
            continue;
        if (control.Kind == ControlKind::Shackle)
        {
            if (plan.Shackler.IsEmpty())
                plan.Shackler = member->Guid;
            continue;
        }
        plan.Controllers.push_back(member->Guid);
    }
    auto controlRank = [&board](ObjectGuid guid)
    {
        ActorSnapshot const* actor = board.FindActor(guid);
        return actor ? ControlPreference(ControlFor(actor->ClassSpec)) : 9;
    };
    std::stable_sort(plan.Controllers.begin(), plan.Controllers.end(),
        [&controlRank](ObjectGuid left, ObjectGuid right)
    {
        return controlRank(left) < controlRank(right);
    });
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
                 << ",\"backup\":" << team.BackupInterrupter.GetCounter() << '}';
        }
        json << "],\"controllers\":[";
        for (std::size_t index = 0; index < plan.Controllers.size(); ++index)
            json << (index ? "," : "") << plan.Controllers[index].GetCounter();
        json << ']';
    }
    json << '}';
    return json.str();
}
}

#endif
