#ifndef TRINITY_BOT_CHIMAERON_DUTY_PLAN_H
#define TRINITY_BOT_CHIMAERON_DUTY_PLAN_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronFacts.h"

#include <algorithm>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

// Chimaeron duties are chosen by capability, never by roster slot, so the
// canonical 10N composition (Blood DK + Feral tank, Holy Paladin / Discipline
// Priest / Restoration Shaman healers) and any other valid roster resolve the
// same way. Every selector is deterministic for one blackboard revision.
namespace BotEncounter::Chimaeron
{
struct Duties
{
    // Break soaker: holds normal melee and Break stacks. Needs only the
    // mixture floor between swings, so self-sustain ranks first.
    ObjectGuid BreakTank;
    // Double Attack soaker: taunts before each doubled swing and must be at
    // full health, so the tank with the largest health pool ranks here.
    ObjectGuid DoubleAttackTank;
    // Capability order: Healers.front() is the tank healer.
    std::vector<ObjectGuid> Healers;
    std::vector<ObjectGuid> Melee;
    // Ranged damage and healers, formation order (GUID order).
    std::vector<ObjectGuid> Ranged;
    ObjectGuid LustOwner;
    uint32 LustSpell = 0;
    ObjectGuid BarrierOwner;
    ObjectGuid SpiritLinkOwner;
};

constexpr uint32 TimeWarpSpell = 80353;

inline int BreakTankRank(std::string_view spec)
{
    if (spec == "blood_death_knight")
        return 0;
    if (spec == "protection_paladin")
        return 1;
    if (spec == "protection_warrior")
        return 2;
    if (spec == "feral_druid_tank")
        return 3;
    return 4;
}

inline int TankHealerRank(std::string_view spec)
{
    if (spec == "holy_paladin")
        return 0;
    if (spec == "discipline_priest")
        return 1;
    if (spec == "holy_priest")
        return 2;
    if (spec == "restoration_druid")
        return 3;
    if (spec == "restoration_shaman")
        return 4;
    return 5;
}

inline bool IsMeleeSpec(ActorSnapshot const& actor)
{
    static constexpr std::string_view Melee[] = {
        "assassination_rogue", "combat_rogue", "subtlety_rogue",
        "retribution_paladin", "arms_warrior", "fury_warrior",
        "frost_death_knight", "unholy_death_knight", "enhancement_shaman",
        "feral_druid_dps",
    };
    for (std::string_view spec : Melee)
        if (actor.ClassSpec == spec)
            return true;
    return actor.PreferredCombatRange
        && actor.PreferredCombatRange->MaxRange > 0.0f
        && actor.PreferredCombatRange->MaxRange <= 8.0f;
}

inline bool IsMageSpec(std::string_view spec)
{
    return spec == "fire_mage" || spec == "arcane_mage" || spec == "frost_mage";
}

// The acting bot's own role comes from the runtime (GetDungeonRole); every
// other member uses its roster role from the snapshot.
inline std::string_view EffectiveRole(ActorSnapshot const& actor,
    ObjectGuid botGuid, std::string_view botRole)
{
    return actor.Guid == botGuid && !botRole.empty()
        ? botRole : std::string_view(actor.Role);
}

inline Duties BuildDuties(Blackboard const& board, ObjectGuid botGuid = ObjectGuid(),
    std::string_view botRole = {})
{
    Duties duties;
    std::vector<ActorSnapshot const*> tanks;
    std::vector<ActorSnapshot const*> healers;
    for (ActorSnapshot const& player : board.Players)
    {
        std::string_view const role = EffectiveRole(player, botGuid, botRole);
        if (role == "tank")
        {
            if (player.Alive)
                tanks.push_back(&player);
            continue;
        }
        if (role == "healer")
        {
            if (player.Alive)
                healers.push_back(&player);
            duties.Ranged.push_back(player.Guid);
            continue;
        }
        if (IsMeleeSpec(player))
            duties.Melee.push_back(player.Guid);
        else
            duties.Ranged.push_back(player.Guid);
    }

    auto byGuid = [](ObjectGuid left, ObjectGuid right)
    {
        return left.GetRawValue() < right.GetRawValue();
    };
    std::sort(duties.Melee.begin(), duties.Melee.end(), byGuid);
    std::sort(duties.Ranged.begin(), duties.Ranged.end(), byGuid);

    std::sort(tanks.begin(), tanks.end(),
        [](ActorSnapshot const* left, ActorSnapshot const* right)
        {
            int const l = BreakTankRank(left->ClassSpec);
            int const r = BreakTankRank(right->ClassSpec);
            return l != r ? l < r
                : left->Guid.GetRawValue() < right->Guid.GetRawValue();
        });
    // A configured route assignment is an explicit decision and wins over
    // the capability ranking when it names a living tank.
    auto lease = std::find_if(board.Assignments.begin(), board.Assignments.end(),
        [](AssignmentLease const& candidate)
        {
            return candidate.Kind == AssignmentKind::Tank && candidate.Slot == "main_tank";
        });
    if (lease != board.Assignments.end())
    {
        auto assignee = std::find_if(tanks.begin(), tanks.end(),
            [&lease](ActorSnapshot const* tank) { return tank->Guid == lease->AssigneeGuid; });
        if (assignee != tanks.end())
            std::rotate(tanks.begin(), assignee, assignee + 1);
    }
    if (!tanks.empty())
        duties.BreakTank = tanks[0]->Guid;
    if (tanks.size() > 1)
        duties.DoubleAttackTank = tanks[1]->Guid;

    std::sort(healers.begin(), healers.end(),
        [](ActorSnapshot const* left, ActorSnapshot const* right)
        {
            int const l = TankHealerRank(left->ClassSpec);
            int const r = TankHealerRank(right->ClassSpec);
            return l != r ? l < r
                : left->Guid.GetRawValue() < right->Guid.GetRawValue();
        });
    for (ActorSnapshot const* healer : healers)
    {
        duties.Healers.push_back(healer->Guid);
        if (duties.BarrierOwner.IsEmpty() && healer->ClassSpec == "discipline_priest")
            duties.BarrierOwner = healer->Guid;
        if (duties.SpiritLinkOwner.IsEmpty() && healer->ClassSpec == "restoration_shaman")
            duties.SpiritLinkOwner = healer->Guid;
    }

    ActorSnapshot const* mage = nullptr;
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && IsMageSpec(player.ClassSpec)
            && (!mage || player.Guid.GetRawValue() < mage->Guid.GetRawValue()))
            mage = &player;
    if (mage)
    {
        duties.LustOwner = mage->Guid;
        duties.LustSpell = TimeWarpSpell;
    }
    return duties;
}

inline bool IsTank(Duties const& duties, ObjectGuid guid)
{
    return !guid.IsEmpty()
        && (guid == duties.BreakTank || guid == duties.DoubleAttackTank);
}

inline char const* DutyName(Duties const& duties, ObjectGuid guid)
{
    if (guid == duties.BreakTank)
        return "break_tank";
    if (guid == duties.DoubleAttackTank)
        return "double_attack_tank";
    if (!duties.Healers.empty() && guid == duties.Healers.front())
        return "tank_healer";
    if (std::find(duties.Healers.begin(), duties.Healers.end(), guid) != duties.Healers.end())
        return "raid_healer";
    if (std::find(duties.Melee.begin(), duties.Melee.end(), guid) != duties.Melee.end())
        return "melee";
    if (std::find(duties.Ranged.begin(), duties.Ranged.end(), guid) != duties.Ranged.end())
        return "ranged";
    return "unassigned";
}

// Diagnostic receipt of the duties, GUID counters only.
inline std::string DutiesJson(Duties const& duties)
{
    std::ostringstream json;
    auto list = [&json](char const* key, std::vector<ObjectGuid> const& guids)
    {
        json << ",\"" << key << "\":[";
        for (std::size_t index = 0; index < guids.size(); ++index)
            json << (index ? "," : "") << guids[index].GetCounter();
        json << ']';
    };
    json << "{\"break_tank\":" << duties.BreakTank.GetCounter()
         << ",\"double_attack_tank\":" << duties.DoubleAttackTank.GetCounter();
    list("healers", duties.Healers);
    list("melee", duties.Melee);
    list("ranged", duties.Ranged);
    json << ",\"lust_owner\":" << duties.LustOwner.GetCounter()
         << ",\"barrier_owner\":" << duties.BarrierOwner.GetCounter()
         << ",\"spirit_link_owner\":" << duties.SpiritLinkOwner.GetCounter() << '}';
    return json.str();
}
}

#endif
