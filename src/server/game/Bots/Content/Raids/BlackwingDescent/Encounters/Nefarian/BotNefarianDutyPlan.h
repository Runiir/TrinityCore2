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
    // Two healers (user raid experience 2026-09-26: 2 tanks, 2 healers,
    // 6 DPS): pillars are 70 yards apart, so the third pillar has no healer.
    // It gets the Nefarian tank, the member best able to sustain itself (a
    // Blood death knight's Death Strike) through the magma swim.
    // The roster's Nefarian tank, dead or alive: teams never reshuffle when a
    // tank dies and another takes over the live duty.
    ActorSnapshot const* rosterTank = nullptr;
    for (ActorSnapshot const* member : members)
        if (member->Role == "tank" && (!rosterTank
                || NefarianTankRank(member->ClassSpec) < NefarianTankRank(rosterTank->ClassSpec)))
            rosterTank = member;
    if (healers < plan.Pillars.size() && rosterTank)
    {
        auto tank = std::find_if(rest.begin(), rest.end(),
            [rosterTank](ActorSnapshot const* member)
            {
                return member == rosterTank;
            });
        if (tank != rest.end())
        {
            place(*tank, healers);
            rest.erase(tank);
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
        json << "],\"warrior_handler\":" << plan.WarriorHandler.GetCounter();
    }
    json << '}';
    return json.str();
}
}

#endif
