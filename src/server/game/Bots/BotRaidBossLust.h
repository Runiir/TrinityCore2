#ifndef TRINITY_BOT_RAID_BOSS_LUST_H
#define TRINITY_BOT_RAID_BOSS_LUST_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotRaidBossLustLatch.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronDutyPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlust.h"

#include <algorithm>
#include <optional>
#include <string_view>
#include <vector>

// Round 5, canonical-composition raids (BotCanonicalRaidScope.h): the raid
// lust on a boss whose encounter strategy declares no lust timing. The
// composition's duty notes left Atramedes "unassigned" and Omnotron "none";
// Nefarian's strategy has no lust either. Coordinator decision: the lust
// owner casts it once the boss is engaged and the main tank has held it for
// TankHoldMs. The strategies with their own timing keep it: Magmaw (the
// head burn or pre-Mangle lead in its Bloodlust scenarios), Chimaeron (the
// burn) and Maloriak (phase two).
//
// Nothing is duplicated: the owner and its spell come from Chimaeron's duty
// rule (a living mage with Time Warp first, then a shaman with Bloodlust,
// GUID order; BuildDuties), the castable variant from KnownLustSpell (the
// owner's own spell book; an owner that knows none casts nothing and no other
// member takes over), and the raid lockouts (active lust, Sated, Exhaustion,
// Temporal Displacement, Insanity) from Magmaw's FindRaidLockout.
namespace BotRaidBossLust
{
// BotMaloriakFacts.h EncounterNode (the Maloriak headers are not included:
// the lust needs only the node id).
constexpr std::string_view MaloriakEncounterNode = "bwd.maloriak.encounter";

inline bool StrategyOwnsLust(std::string_view nodeId, std::string_view scenarioId)
{
    if (nodeId == BotEncounter::Chimaeron::EncounterNode || nodeId == MaloriakEncounterNode)
        return true;
    return nodeId == BotEncounter::MagmawBloodlust::EncounterNode
        && BotEncounter::MagmawBloodlust::IsMagmawBloodlustScenario(scenarioId);
}

struct Owner
{
    ObjectGuid Guid;
    uint32 ProposedSpell = 0;
};

inline std::optional<Owner> SelectOwner(BotEncounter::Blackboard const& board)
{
    BotEncounter::Chimaeron::Duties const duties =
        BotEncounter::Chimaeron::BuildDuties(board);
    if (duties.LustOwner.IsEmpty() || !duties.LustSpell)
        return std::nullopt;
    return Owner{ duties.LustOwner, duties.LustSpell };
}

struct TankHold
{
    ObjectGuid Boss;
    ObjectGuid Tank;
};

// The first (GUID order) living, in-combat hostile that the caller's native
// probe calls a boss and whose victim is a living tank-role raid bot.
template <typename BossProbe>
TankHold FindTankHold(BotEncounter::Blackboard const& board, BossProbe&& isBoss)
{
    std::vector<BotEncounter::ActorSnapshot const*> engaged;
    for (auto const* actors : { &board.Hostiles, &board.Summons })
        for (BotEncounter::ActorSnapshot const& actor : *actors)
            if (actor.Alive && actor.InCombat && !actor.VictimGuid.IsEmpty())
                engaged.push_back(&actor);
    std::sort(engaged.begin(), engaged.end(),
        [](BotEncounter::ActorSnapshot const* left, BotEncounter::ActorSnapshot const* right)
        {
            return left->Guid.GetRawValue() < right->Guid.GetRawValue();
        });
    for (BotEncounter::ActorSnapshot const* hostile : engaged)
    {
        auto tank = std::find_if(board.Players.begin(), board.Players.end(),
            [hostile](BotEncounter::ActorSnapshot const& player)
            {
                return player.Guid == hostile->VictimGuid && player.Alive
                    && player.Role == "tank";
            });
        if (tank != board.Players.end() && isBoss(hostile->Guid))
            return TankHold{ hostile->Guid, tank->Guid };
    }
    return TankHold{};
}

// The owner's own lust cooldown (300 s) outlives a wipe: Sated, Exhaustion,
// Temporal Displacement and Insanity lack SPELL_ATTR3_ALLOW_AURA_WHILE_DEAD
// and are stripped by death, so after a quick re-pull only the cooldown gates
// the cast. The runtime publishes this typed reason instead of submitting a
// cast the core refuses, and still casts if the cooldown returns mid-fight
// (the latch keeps it to once per attempt).
constexpr char const* OwnerLustCooldownReason = "raid_boss_lust_owner_lust_cooldown";

// Why the owner may not cast now (nullptr: cast). The lust spell is resolved
// separately from the owner's spell book (KnownLustSpell) and its cooldown
// from the owner's spell history (OwnerLustCooldownReason).
inline char const* BlockedReason(BotEncounter::Blackboard const& board,
    Latch const& latch, uint64 nowMs)
{
    if (latch.Submitted)
        return "raid_boss_lust_already_submitted";
    if (!TankHeld(latch, nowMs))
        return "raid_boss_lust_tank_hold_pending";
    if (std::optional<uint32> const lockout =
            BotEncounter::MagmawBloodlust::FindRaidLockout(board))
        return BotEncounter::MagmawBloodlust::RaidLockoutReason(*lockout);
    return nullptr;
}
}

#endif
