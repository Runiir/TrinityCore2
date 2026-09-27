#ifndef TRINITY_BOT_CHIMAERON_DUTY_PLAN_H
#define TRINITY_BOT_CHIMAERON_DUTY_PLAN_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronFacts.h"

#include <algorithm>
#include <optional>
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
    // Double Attack soaker: the next living tank in BreakTankRank order. He
    // taunts before each doubled swing and is healed toward full (in the
    // canonical roster this is the Feral druid, the larger health pool).
    ObjectGuid DoubleAttackTank;
    // Capability order: Healers.front() is the tank healer.
    std::vector<ObjectGuid> Healers;
    std::vector<ObjectGuid> Melee;
    // Ranged damage and healers (GUID order); RangedHealers is the healer
    // subset, dead members included so slots never reshuffle on a death.
    std::vector<ObjectGuid> Ranged;
    std::vector<ObjectGuid> RangedHealers;
    // Ranged members whose attacks have a minimum range (hunters): against
    // Chimaeron's 20 yd combat reach they must stand beyond ~27.8 yd (GUID
    // order, dead included like Ranged). A subset of Ranged.
    std::vector<ObjectGuid> Standoff;
    // Raid lust: a mage (Time Warp) first, then a shaman (Bloodlust; the
    // runtime casts Heroism instead when only that variant is known).
    ObjectGuid LustOwner;
    uint32 LustSpell = 0;
    ObjectGuid BarrierOwner;
    ObjectGuid SpiritLinkOwner;
};

constexpr uint32 TimeWarpSpell = 80353;
constexpr uint32 BloodlustSpell = 2825;
constexpr uint32 HeroismSpell = 32182;

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

// Hunter shots and Auto Shot carry a 5 yd minimum range that the spell system
// extends by the melee range (Spell::GetMinMaxRange: 5 + 1.5 + 20 + 4/3 yd
// against Chimaeron). Round 1: the Survival Hunter on the 22 yd arc and in the
// 8 yd outage stack was rejected with min_range_required and meleed instead.
inline bool IsStandoffSpec(std::string_view spec)
{
    return spec == "beast_mastery_hunter" || spec == "marksmanship_hunter"
        || spec == "survival_hunter";
}

inline bool IsMageSpec(std::string_view spec)
{
    return spec == "fire_mage" || spec == "arcane_mage" || spec == "frost_mage";
}

inline bool IsShamanSpec(std::string_view spec)
{
    return spec == "elemental_shaman" || spec == "enhancement_shaman"
        || spec == "restoration_shaman";
}

// Lust preference: 0 mage (Time Warp), 1 shaman (Bloodlust/Heroism), -1 none.
inline int LustRank(std::string_view spec)
{
    if (IsMageSpec(spec))
        return 0;
    if (IsShamanSpec(spec))
        return 1;
    return -1;
}

inline bool IsLustSpell(uint32 spellId)
{
    return spellId == TimeWarpSpell || spellId == BloodlustSpell || spellId == HeroismSpell;
}

// The raid haste the lust owner can actually cast, from its own spell book
// (Player::HasSpell, observed by the runtime): the proposed spell when known,
// otherwise the shaman's other faction variant (Bloodlust is Horde-only,
// Heroism Alliance-only). Empty when the owner knows none: the runtime skips
// the cast with the typed reason LustSpellUnknownReason instead of asking the
// executor for a spell it would refuse on every tick. The owner is chosen from
// the shared snapshot, which carries no spell book, so every bot agrees on it;
// the next owner in the mage-then-shaman order is not taken over locally.
constexpr char const* LustSpellUnknownReason = "chimaeron_lust_spell_unknown";

inline std::optional<uint32> KnownLustSpell(uint32 proposed, bool knowsTimeWarp,
    bool knowsBloodlust, bool knowsHeroism)
{
    auto knows = [&](uint32 spellId)
    {
        return (spellId == TimeWarpSpell && knowsTimeWarp)
            || (spellId == BloodlustSpell && knowsBloodlust)
            || (spellId == HeroismSpell && knowsHeroism);
    };
    if (!IsLustSpell(proposed))
        return std::nullopt;
    if (knows(proposed))
        return proposed;
    if (proposed != TimeWarpSpell)
        for (uint32 variant : { BloodlustSpell, HeroismSpell })
            if (knows(variant))
                return variant;
    return std::nullopt;
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
            duties.RangedHealers.push_back(player.Guid);
            continue;
        }
        if (IsMeleeSpec(player))
            duties.Melee.push_back(player.Guid);
        else
        {
            duties.Ranged.push_back(player.Guid);
            if (IsStandoffSpec(player.ClassSpec))
                duties.Standoff.push_back(player.Guid);
        }
    }

    auto byGuid = [](ObjectGuid left, ObjectGuid right)
    {
        return left.GetRawValue() < right.GetRawValue();
    };
    std::sort(duties.Melee.begin(), duties.Melee.end(), byGuid);
    std::sort(duties.Ranged.begin(), duties.Ranged.end(), byGuid);
    std::sort(duties.RangedHealers.begin(), duties.RangedHealers.end(), byGuid);
    std::sort(duties.Standoff.begin(), duties.Standoff.end(), byGuid);

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

    ActorSnapshot const* lust = nullptr;
    for (ActorSnapshot const& player : board.Players)
    {
        int const rank = LustRank(player.ClassSpec);
        if (!player.Alive || rank < 0)
            continue;
        int const best = lust ? LustRank(lust->ClassSpec) : 99;
        if (rank < best
            || (rank == best && player.Guid.GetRawValue() < lust->Guid.GetRawValue()))
            lust = &player;
    }
    if (lust)
    {
        duties.LustOwner = lust->Guid;
        duties.LustSpell = IsMageSpec(lust->ClassSpec) ? TimeWarpSpell : BloodlustSpell;
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
    list("standoff", duties.Standoff);
    json << ",\"lust_owner\":" << duties.LustOwner.GetCounter()
         << ",\"barrier_owner\":" << duties.BarrierOwner.GetCounter()
         << ",\"spirit_link_owner\":" << duties.SpiritLinkOwner.GetCounter() << '}';
    return json.str();
}
}

#endif
