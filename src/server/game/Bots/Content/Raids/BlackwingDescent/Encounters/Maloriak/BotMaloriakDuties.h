#ifndef TRINITY_BOT_MALORIAK_DUTIES_H
#define TRINITY_BOT_MALORIAK_DUTIES_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFacts.h"

#include <algorithm>
#include <string_view>
#include <tuple>
#include <vector>

// Maloriak duty owners picked by capability from the observed roster, never
// by fixed roster slot. Every selector is a pure function of one blackboard,
// so all bots of a cohort agree on the owner of each duty in a snapshot.
namespace BotEncounter::Maloriak
{
inline bool EndsWith(std::string_view text, std::string_view suffix)
{
    return text.size() >= suffix.size()
        && text.compare(text.size() - suffix.size(), suffix.size(), suffix) == 0;
}

// Interrupt tiers. Short tiers (<= 15 s native cooldown) share the Arcane
// Storm rotation; long cooldowns only back it up.
enum class InterruptTier : uint8
{
    MeleeShort = 0,
    RangedShort = 1,
    TankShort = 2,
    Long = 3,
    None = 255
};

struct InterruptCapability
{
    InterruptTier Tier = InterruptTier::None;
    float RangeYards = 0.0f;
};

// Client rows (4.4.2): Kick/Rebuke/Pummel/Mind Freeze 5 yd 10 s, Wind Shear
// 25 yd 15 s, Counterspell 40 yd 24 s, Skull Bash 13 yd 60 s (talents
// shorten it), Silence 30 yd, Silencing Shot 35 yd 20 s. Healers keep their
// global cooldowns for healing.
inline InterruptCapability InterruptCapabilityFor(std::string_view classSpec,
    std::string_view role)
{
    if (role == "healer")
        return {};
    if (EndsWith(classSpec, "_rogue") || classSpec == "retribution_paladin"
        || classSpec == "arms_warrior" || classSpec == "fury_warrior"
        || classSpec == "frost_death_knight" || classSpec == "unholy_death_knight")
        return { InterruptTier::MeleeShort, 5.0f };
    if (classSpec == "enhancement_shaman")
        return { InterruptTier::MeleeShort, 25.0f };
    if (classSpec == "elemental_shaman")
        return { InterruptTier::RangedShort, 25.0f };
    if (classSpec == "protection_paladin" || classSpec == "protection_warrior"
        || classSpec == "blood_death_knight")
        return { InterruptTier::TankShort, 5.0f };
    if (EndsWith(classSpec, "_mage"))
        return { InterruptTier::Long, 40.0f };
    if (classSpec == "feral_druid_tank" || classSpec == "feral_druid_dps")
        return { InterruptTier::Long, 13.0f };
    if (classSpec == "shadow_priest")
        return { InterruptTier::Long, 30.0f };
    if (classSpec == "marksmanship_hunter")
        return { InterruptTier::Long, 35.0f };
    return {};
}

// Offensive magic dispel of Remedy: Spellsteal (40 yd, the mage also gains
// the buff), Purge (30 yd), Tranquilizing Shot (35 yd), priest Dispel Magic
// (30 yd, healers last). Rank 255 = no capability.
inline std::pair<uint8, float> DispelCapabilityFor(std::string_view classSpec,
    std::string_view role)
{
    if (EndsWith(classSpec, "_mage"))
        return { 0, 40.0f };
    if (EndsWith(classSpec, "_shaman"))
        return { uint8(role == "healer" ? 3 : 1), 30.0f };
    if (EndsWith(classSpec, "_hunter"))
        return { 2, 35.0f };
    if (EndsWith(classSpec, "_priest"))
        return { uint8(role == "healer" ? 4 : 2), 30.0f };
    return { 255, 0.0f };
}

// Raid haste owner: a shaman (Bloodlust/Heroism) first, then a mage (Time
// Warp). Rank 255 = no capability.
inline uint8 LustRankFor(std::string_view classSpec)
{
    if (EndsWith(classSpec, "_shaman"))
        return 0;
    if (EndsWith(classSpec, "_mage"))
        return 1;
    return 255;
}

inline bool IsMeleeSpec(std::string_view classSpec)
{
    return EndsWith(classSpec, "_rogue") || classSpec == "retribution_paladin"
        || classSpec == "arms_warrior" || classSpec == "fury_warrior"
        || classSpec == "frost_death_knight" || classSpec == "unholy_death_knight"
        || classSpec == "enhancement_shaman" || classSpec == "feral_druid_dps";
}

inline bool IsRangedDamageSpec(std::string_view classSpec, std::string_view role)
{
    return role == "dps" && !IsMeleeSpec(classSpec);
}

inline uint8 MainTankPreference(std::string_view classSpec)
{
    if (classSpec == "blood_death_knight")
        return 0;
    if (classSpec == "protection_paladin")
        return 1;
    if (classSpec == "protection_warrior")
        return 2;
    if (classSpec == "feral_druid_tank")
        return 3;
    return 4;
}

struct TankDuties
{
    ObjectGuid MainTank;
    ObjectGuid OffTank;
};

inline ActorSnapshot const* FindPlayer(Blackboard const& board, ObjectGuid guid)
{
    for (ActorSnapshot const& player : board.Players)
        if (player.Guid == guid)
            return &player;
    return nullptr;
}

// The configured main-tank lease wins while its assignee is an alive tank;
// otherwise the alive tanks are ordered by boss-tank preference. A dead main
// tank hands the boss to the surviving tank.
inline TankDuties ResolveTanks(Blackboard const& board)
{
    std::vector<ActorSnapshot const*> tanks;
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && player.Role == "tank")
            tanks.push_back(&player);
    std::sort(tanks.begin(), tanks.end(), [](ActorSnapshot const* left,
        ActorSnapshot const* right)
    {
        return std::make_tuple(MainTankPreference(left->ClassSpec), left->Guid.GetRawValue())
            < std::make_tuple(MainTankPreference(right->ClassSpec), right->Guid.GetRawValue());
    });
    auto aliveTank = [&tanks](ObjectGuid guid)
    {
        return !guid.IsEmpty() && std::any_of(tanks.begin(), tanks.end(),
            [guid](ActorSnapshot const* tank) { return tank->Guid == guid; });
    };

    TankDuties duties;
    for (AssignmentLease const& lease : board.Assignments)
        if (lease.Kind == AssignmentKind::Tank && lease.Slot == "main_tank"
            && aliveTank(lease.AssigneeGuid))
        {
            duties.MainTank = lease.AssigneeGuid;
            if (aliveTank(lease.BackupGuid) && lease.BackupGuid != lease.AssigneeGuid)
                duties.OffTank = lease.BackupGuid;
            break;
        }
    for (ActorSnapshot const* tank : tanks)
    {
        if (duties.MainTank.IsEmpty())
            duties.MainTank = tank->Guid;
        else if (duties.OffTank.IsEmpty() && tank->Guid != duties.MainTank)
            duties.OffTank = tank->Guid;
    }
    return duties;
}

struct InterruptPools
{
    // Short cooldowns ordered by tier then GUID; Long cooldowns back them up.
    std::vector<ObjectGuid> Short;
    std::vector<ObjectGuid> Long;
};

// Alive, unfrozen interrupters that can reach the boss now. Melee reach is
// measured centre to centre with Maloriak's combat reach allowance.
inline InterruptPools ResolveInterruptPools(Blackboard const& board,
    ActorSnapshot const& boss)
{
    struct Entry { InterruptTier Tier; uint64 Guid; ObjectGuid Actor; };
    std::vector<Entry> entries;
    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive || IsFrozen(player))
            continue;
        InterruptCapability const capability =
            InterruptCapabilityFor(player.ClassSpec, player.Role);
        if (capability.Tier == InterruptTier::None)
            continue;
        float const reach = capability.RangeYards <= 5.0f ? 8.0f
            : capability.RangeYards - 1.0f;
        if (Distance2d(player.Position, boss.Position) > reach)
            continue;
        entries.push_back({ capability.Tier, player.Guid.GetRawValue(), player.Guid });
    }
    std::sort(entries.begin(), entries.end(), [](Entry const& left, Entry const& right)
    {
        return std::tie(left.Tier, left.Guid) < std::tie(right.Tier, right.Guid);
    });
    InterruptPools pools;
    for (Entry const& entry : entries)
        (entry.Tier == InterruptTier::Long ? pools.Long : pools.Short)
            .push_back(entry.Actor);
    return pools;
}

// Arcane Storm must be interrupted every cast (both guides). The first
// short-cooldown interrupter owns it; the next joins after 0.8 s of channel
// and everyone capable after 2 s, so a cooldown or range miss costs at most
// one or two 1 s ticks. With no short interrupter the long pool takes over.
constexpr uint32 ArcaneStormBackupAfterMs = 800;
constexpr uint32 ArcaneStormEveryoneAfterMs = 2000;

inline std::vector<ObjectGuid> ArcaneStormInterrupters(
    InterruptPools const& pools, uint32 elapsedMs)
{
    std::vector<ObjectGuid> assigned;
    std::vector<ObjectGuid> const& primary = pools.Short.empty() ? pools.Long : pools.Short;
    std::size_t count = 1;
    if (elapsedMs >= ArcaneStormBackupAfterMs)
        count = 2;
    for (std::size_t index = 0; index < primary.size() && index < count; ++index)
        assigned.push_back(primary[index]);
    if (elapsedMs >= ArcaneStormEveryoneAfterMs)
    {
        assigned = pools.Short;
        assigned.insert(assigned.end(), pools.Long.begin(), pools.Long.end());
    }
    return assigned;
}

// User tactic (user raid experience 2026-09-26, authoritative): Release
// Aberrations is never interrupted. Every release goes through and each pack
// of 3 is killed as it comes (ideally in the Green slime window), so the
// chambers are empty before 25%. The dispatch vetoes generic rotation
// interrupts of every release in phase one. This replaces Icy Veins' advice
// to interrupt releases when enough adds are up and the 2012 guide's
// "interrupt the first Release" (ledger: guide conflict).
inline bool ReleaseAdmitted(Observation const& observation)
{
    return observation.CurrentPhase != Phase::PhaseTwo;
}

// The switch at 30% (same source): if Aberrations are left at 30%, in the
// chambers (counted from the native sleeping, unselectable chamber creatures)
// or loose, every damage dealer stops damaging Maloriak and kills them one
// at a time until none is left, so phase two starts with only the two Prime
// Subjects. The Blood DK main tank keeps full damage (Death Strike), and
// Remedy is left on the boss so his self-heal offsets the tank's damage.
// The switch is a cohort latch (BotMaloriakLatches.h).
constexpr float AddSwitchHealthPct = 30.0f;

// Threat onto the Feral off-tank for each release (same source): the
// hunter's Misdirection and the rogue's Tricks of the Trade. Frost Shock is
// the shaman's slow on a loose Aberration (no slow totem: Earthbind would
// replace the earth-slot buff totem).
constexpr uint32 MisdirectionSpell = 34477;
constexpr uint32 TricksOfTheTradeSpell = 57934;
constexpr uint32 FrostShockSpell = 8056;

inline uint32 ThreatRedirectSpellFor(std::string_view classSpec)
{
    if (EndsWith(classSpec, "_hunter"))
        return MisdirectionSpell;
    if (EndsWith(classSpec, "_rogue"))
        return TricksOfTheTradeSpell;
    return 0;
}

// Hunter traps for the off-tank's kite, placed at the hunter's feet as a
// player without Trap Launcher does, for an Aberration running at the
// hunter: Freeze Trap only on one nobody is damaging (damage breaks it),
// Ice Trap (a slowing ground effect) otherwise.
constexpr uint32 FreezeTrapSpell = 1499;
constexpr uint32 IceTrapSpell = 13809;
constexpr float TrapTriggerYards = 15.0f;

inline bool LaysTraps(std::string_view classSpec)
{
    return EndsWith(classSpec, "_hunter");
}

inline bool SlowsAberrations(std::string_view classSpec)
{
    return EndsWith(classSpec, "_shaman");
}

// Remedy (10 s self heal, magic) is removed at once: the first dispeller
// owns it, the second joins after 1.5 s and all capable after 3 s.
constexpr uint32 RemedyBackupAfterMs = 1500;
constexpr uint32 RemedyEveryoneAfterMs = 3000;

inline std::vector<ObjectGuid> RemedyDispellers(Blackboard const& board,
    ActorSnapshot const& boss, uint32 elapsedMs)
{
    struct Entry { uint8 Rank; uint64 Guid; ObjectGuid Actor; };
    std::vector<Entry> entries;
    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive || IsFrozen(player))
            continue;
        std::pair<uint8, float> const capability =
            DispelCapabilityFor(player.ClassSpec, player.Role);
        if (capability.first == 255
            || Distance2d(player.Position, boss.Position) > capability.second - 1.0f)
            continue;
        entries.push_back({ capability.first, player.Guid.GetRawValue(), player.Guid });
    }
    std::sort(entries.begin(), entries.end(), [](Entry const& left, Entry const& right)
    {
        return std::tie(left.Rank, left.Guid) < std::tie(right.Rank, right.Guid);
    });
    std::size_t count = 1;
    if (elapsedMs >= RemedyBackupAfterMs)
        count = 2;
    if (elapsedMs >= RemedyEveryoneAfterMs)
        count = entries.size();
    std::vector<ObjectGuid> assigned;
    for (std::size_t index = 0; index < entries.size() && index < count; ++index)
        assigned.push_back(entries[index].Actor);
    return assigned;
}

inline ObjectGuid ResolveLustOwner(Blackboard const& board)
{
    ObjectGuid owner;
    uint8 bestRank = 255;
    uint64 bestGuid = 0;
    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive)
            continue;
        uint8 const rank = LustRankFor(player.ClassSpec);
        if (rank == 255)
            continue;
        uint64 const guid = player.Guid.GetRawValue();
        if (owner.IsEmpty() || rank < bestRank
            || (rank == bestRank && guid < bestGuid))
        {
            owner = player.Guid;
            bestRank = rank;
            bestGuid = guid;
        }
    }
    return owner;
}

// A healer assigned a purge or interrupt drops the heal it is casting only
// while nobody in the raid is below this health (the Disc Priest joins
// Remedy after 3 s).
constexpr float HealerKeepsHealBelowPct = 50.0f;

inline bool OwnCastYieldsToDuty(bool healer, bool castIsHelpful,
    float lowestAllyHealthPct)
{
    return !healer || !castIsHelpful
        || lowestAllyHealthPct >= HealerKeepsHealBelowPct;
}

// Bound on the add switch. It normally ends when the chambers are empty and
// the loose Aberrations are dead (six releases 17-18 s apart, about 110 s
// from the first); if the reserve stops draining, the cap leaves the
// phase-two burn well inside the guides' 6-7 minute enrage (the native
// script has none). The dispatch logs it when it fires.
constexpr uint64 AddSwitchCapMs = 180000;

inline bool Contains(std::vector<ObjectGuid> const& guids, ObjectGuid guid)
{
    return std::find(guids.begin(), guids.end(), guid) != guids.end();
}
}

#endif
