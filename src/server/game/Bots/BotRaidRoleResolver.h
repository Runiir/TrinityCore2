#ifndef TRINITY_BOT_RAID_ROLE_RESOLVER_H
#define TRINITY_BOT_RAID_ROLE_RESOLVER_H

#include "Define.h"

#include <array>
#include <string>

// Role and spec tag of an external (human) raid member. The raid-UI role
// (CMSG_SET_ROLE -> Group::SetLfgRoles) wins; otherwise the primary talent
// tree decides. Never the legacy class fallback, which calls every Warrior
// or Death Knight a tank.
namespace BotRaidRole
{
// Shared by LFG roles (lfg::LfgRoles) and TalentTab.dbc RoleMask.
inline constexpr uint8 TankMask = 2;
inline constexpr uint8 HealerMask = 4;
inline constexpr uint8 DamageMask = 8;

struct TalentTree
{
    uint32 TreeId;
    uint32 ClassMask;
    uint8 RolesMask;
    char const* ClassSpec;
};

// TalentTab.dbc (4.3.4 build 15595) player trees; RolesMask is column 8,
// which the core does not load. tests/test_bot_raid_role_resolver.py
// checks every row against data/dbc/enUS/TalentTab.dbc when present.
// Feral Combat (tank|damage) resolves its tag from the role.
inline constexpr std::array<TalentTree, 30> TalentTrees{ {
    { 746, 1, DamageMask, "arms_warrior" },
    { 815, 1, DamageMask, "fury_warrior" },
    { 845, 1, TankMask, "protection_warrior" },
    { 831, 2, HealerMask, "holy_paladin" },
    { 839, 2, TankMask, "protection_paladin" },
    { 855, 2, DamageMask, "retribution_paladin" },
    { 811, 4, DamageMask, "beast_mastery_hunter" },
    { 807, 4, DamageMask, "marksmanship_hunter" },
    { 809, 4, DamageMask, "survival_hunter" },
    { 182, 8, DamageMask, "assassination_rogue" },
    { 181, 8, DamageMask, "combat_rogue" },
    { 183, 8, DamageMask, "subtlety_rogue" },
    { 760, 16, HealerMask, "discipline_priest" },
    { 813, 16, HealerMask, "holy_priest" },
    { 795, 16, DamageMask, "shadow_priest" },
    { 398, 32, TankMask, "blood_death_knight" },
    { 399, 32, DamageMask, "frost_death_knight" },
    { 400, 32, DamageMask, "unholy_death_knight" },
    { 261, 64, DamageMask, "elemental_shaman" },
    { 263, 64, DamageMask, "enhancement_shaman" },
    { 262, 64, HealerMask, "restoration_shaman" },
    { 799, 128, DamageMask, "arcane_mage" },
    { 851, 128, DamageMask, "fire_mage" },
    { 823, 128, DamageMask, "frost_mage" },
    { 871, 256, DamageMask, "affliction_warlock" },
    { 867, 256, DamageMask, "demonology_warlock" },
    { 865, 256, DamageMask, "destruction_warlock" },
    { 752, 1024, DamageMask, "balance_druid" },
    { 750, 1024, TankMask | DamageMask, "feral_druid" },
    { 748, 1024, HealerMask, "restoration_druid" },
} };

inline TalentTree const* FindTalentTree(uint32 treeId)
{
    for (TalentTree const& tree : TalentTrees)
        if (tree.TreeId == treeId)
            return &tree;
    return nullptr;
}

inline char const* RoleName(uint8 singleRoleMask)
{
    switch (singleRoleMask)
    {
        case TankMask: return "tank";
        case HealerMask: return "healer";
        case DamageMask: return "dps";
        default: return "";
    }
}

inline uint8 SingleRole(uint8 mask)
{
    uint8 const roles = mask & (TankMask | HealerMask | DamageMask);
    return (roles == TankMask || roles == HealerMask || roles == DamageMask)
        ? roles : 0;
}

struct Resolution
{
    std::string Role;       // "tank", "healer", "dps", or "" when unknown
    std::string ClassSpec;  // bot spec tag, or "" for an unknown tree
    std::string Source;     // declared_role | talent_tree | assumed_dps | unknown
    bool Ambiguous = false; // the human should set a raid role
};

inline Resolution Resolve(uint8 declaredLfgRoles, uint32 primaryTalentTreeId)
{
    Resolution resolution;
    TalentTree const* tree = FindTalentTree(primaryTalentTreeId);
    uint8 role = SingleRole(declaredLfgRoles);
    if (role)
        resolution.Source = "declared_role";
    else if (tree && (role = SingleRole(tree->RolesMask)))
        resolution.Source = "talent_tree";
    else if (tree)
    {
        // Feral Combat without a raid role: damage until the human says.
        role = DamageMask;
        resolution.Source = "assumed_dps";
        resolution.Ambiguous = true;
    }
    else
    {
        resolution.Source = "unknown";
        resolution.Ambiguous = true;
    }
    resolution.Role = RoleName(role);
    if (tree)
    {
        resolution.ClassSpec = tree->ClassSpec;
        if (tree->TreeId == 750)
            resolution.ClassSpec = role == TankMask
                ? "feral_druid_tank" : "feral_druid_dps";
    }
    return resolution;
}
}

#endif
