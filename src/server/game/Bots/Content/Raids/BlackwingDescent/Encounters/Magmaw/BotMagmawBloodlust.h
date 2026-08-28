#ifndef TRINITY_BOT_MAGMAW_BLOODLUST_H
#define TRINITY_BOT_MAGMAW_BLOODLUST_H

#include "Bots/BotEncounterBlackboard.h"

#include <algorithm>
#include <array>
#include <optional>
#include <string_view>
#include <vector>

namespace BotEncounter::MagmawBloodlust
{
constexpr uint32 BossEntry = 41570;
constexpr uint32 ExposedHeadEntry = 42347;
constexpr uint32 BloodlustSpell = 2825;
constexpr uint32 HeroismSpell = 32182;
constexpr uint32 TimeWarpSpell = 80353;
constexpr uint32 AncientHysteriaSpell = 90355;
constexpr uint32 ExhaustionSpell = 57723;
constexpr uint32 SatedSpell = 57724;
constexpr uint32 TemporalDisplacementSpell = 80354;
constexpr uint32 InsanitySpell = 95809;

constexpr std::string_view EncounterNode = "bwd.magmaw.encounter";
constexpr std::string_view DiagnosticScenario =
    "blackwing_descent_10n_magmaw_diagnostic";
constexpr std::string_view ElementalShamanSpec = "elemental_shaman";

// The WCL gear/event API is unavailable for this work unit.  The trigger is
// therefore deliberately tied to the source-backed Cataclysm tactic: burn the
// first native, exposed head window after the encounter is in progress.
constexpr std::string_view TimingEvidence =
    "source_backed_exposed_head_burn_no_wcl_verification";

struct HeadWindow
{
    ObjectGuid BossGuid;
    ObjectGuid HeadGuid;
};

inline ActorSnapshot const* FindBoss(Blackboard const& board)
{
    auto find = [](std::vector<ActorSnapshot> const& actors)
        -> ActorSnapshot const*
    {
        for (ActorSnapshot const& actor : actors)
            if (actor.Alive && actor.Entry == BossEntry)
                return &actor;
        return nullptr;
    };

    if (ActorSnapshot const* boss = find(board.Hostiles))
        return boss;
    return find(board.Summons);
}

inline ActorSnapshot const* FindExposedHead(Blackboard const& board)
{
    std::vector<ActorSnapshot const*> candidates;
    auto collect = [&candidates](std::vector<ActorSnapshot> const& actors)
    {
        for (ActorSnapshot const& actor : actors)
            if (actor.Alive && actor.Entry == ExposedHeadEntry
                && actor.Selectable && actor.Attackable)
                candidates.push_back(&actor);
    };
    collect(board.Hostiles);
    collect(board.Summons);
    if (candidates.empty())
        return nullptr;

    std::sort(candidates.begin(), candidates.end(),
        [](ActorSnapshot const* left, ActorSnapshot const* right)
        {
            return left->Guid.GetRawValue() < right->Guid.GetRawValue();
        });
    return candidates.front();
}

inline std::optional<HeadWindow> ObserveFirstHeadWindow(Blackboard const& board)
{
    if (board.Route.NodeId != EncounterNode
        || board.NativeBossState != "in_progress")
        return std::nullopt;

    ActorSnapshot const* boss = FindBoss(board);
    ActorSnapshot const* head = FindExposedHead(board);
    if (!boss || !head)
        return std::nullopt;
    return HeadWindow{ boss->Guid, head->Guid };
}

inline bool IsRaidLockoutSpell(uint32 spellId)
{
    return spellId == BloodlustSpell || spellId == HeroismSpell
        || spellId == TimeWarpSpell || spellId == AncientHysteriaSpell
        || spellId == ExhaustionSpell || spellId == SatedSpell
        || spellId == TemporalDisplacementSpell || spellId == InsanitySpell;
}

inline char const* RaidLockoutReason(uint32 spellId)
{
    switch (spellId)
    {
        case BloodlustSpell: return "bloodlust_active";
        case HeroismSpell: return "heroism_active";
        case TimeWarpSpell: return "time_warp_active";
        case AncientHysteriaSpell: return "ancient_hysteria_active";
        case ExhaustionSpell: return "exhaustion_lockout";
        case SatedSpell: return "sated_lockout";
        case TemporalDisplacementSpell:
            return "temporal_displacement_lockout";
        case InsanitySpell: return "insanity_lockout";
        default: return "unknown_raid_lockout";
    }
}

inline std::optional<uint32> FindRaidLockout(Blackboard const& board)
{
    // Prefer an active cast aura over an exhaustion-style lockout so blocked
    // telemetry has a stable, human-readable reason when several are visible.
    constexpr std::array<uint32, 8> LockoutOrder = {
        BloodlustSpell, HeroismSpell, TimeWarpSpell, AncientHysteriaSpell,
        ExhaustionSpell, SatedSpell, TemporalDisplacementSpell, InsanitySpell,
    };
    for (uint32 spellId : LockoutOrder)
        for (ActorSnapshot const& member : board.Players)
            for (AuraSnapshot const& aura : member.Auras)
                if (aura.SpellId == spellId)
                    return spellId;
    return std::nullopt;
}

inline bool ObservedBloodlustAura(Blackboard const& board,
    ObjectGuid ownerGuid)
{
    for (ActorSnapshot const& member : board.Players)
        if (member.Guid == ownerGuid)
            for (AuraSnapshot const& aura : member.Auras)
                if (aura.SpellId == BloodlustSpell
                    && (aura.CasterGuid.IsEmpty()
                        || aura.CasterGuid == ownerGuid))
                    return true;
    return false;
}

inline std::optional<ObjectGuid> FindSingleElementalShaman(
    Blackboard const& board)
{
    if (board.Players.size() != 10)
        return std::nullopt;

    ObjectGuid owner;
    for (ActorSnapshot const& member : board.Players)
        if (member.Role == "dps" && member.ClassSpec == ElementalShamanSpec)
        {
            if (!owner.IsEmpty())
                return std::nullopt;
            owner = member.Guid;
        }
    return owner.IsEmpty() ? std::nullopt
        : std::optional<ObjectGuid>(owner);
}
}

#endif
