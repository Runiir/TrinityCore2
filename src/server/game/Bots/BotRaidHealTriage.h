#ifndef TRINITY_BOT_RAID_HEAL_TRIAGE_H
#define TRINITY_BOT_RAID_HEAL_TRIAGE_H

#include "Bots/BotEncounterBlackboard.h"
#include "Define.h"
#include "ObjectGuid.h"

#include <algorithm>
#include <cstddef>
#include <optional>
#include <utility>
#include <vector>

// Canonical-composition raids only (BotCanonicalRaidScope.h): which ally the
// generic raid heal (the kernel's "raid.support.heal" candidate) targets when
// no encounter strategy names a priority heal target.
//
// The legacy rule took the lowest health percentage of every living player
// below 94%, wherever that player stood. A target out of heal range or line
// of sight fails its cast, the per-target key backs off, and the next tick
// picks the same target again, so the healer heals no one. BWD 10N round 3
// (label blackwing_descent_10n-r03-a3864fcf6d, Maloriak batch cd3009): the
// Discipline priest cast no heal from 242.0 to 259.1 s while the Feral
// off-tank, the lowest at 34% then 9%, stood 56 yd away and five allies at
// 45-51% stood within 20 yd; the Holy paladin was idle 14 s from 17.2 s.
// Omnotron cd3009: the Holy paladin cast nothing for 13.6 s while the Feral
// fell from 140k to 0, with 62-78 no_valid_profile_action
// requires_ally_target outcomes per healer and run (the offensive profile
// fallback a healer reaches when its heal candidate did not commit).
//
// Here the healer takes the most endangered ally it can actually heal: in
// heal range, then in line of sight (the LOS raycast only for the ranked
// candidates, cheapest first). A tank under attack counts TankUnderAttackPct
// points lower, because its melee intake is the spikiest. When no injured
// ally is reachable, the legacy lowest target is kept, so the outcome and
// its failure receipt are unchanged for that case.
namespace BotRaidHealTriage
{
// The legacy generic threshold (0-100 health percentage).
inline constexpr float TriageHealthPct = 94.0f;
// Every Cataclysm healer's single-target heal has a 40 yd range.
inline constexpr float HealRangeYards = 40.0f;
inline constexpr float TankUnderAttackPct = 10.0f;

struct Member
{
    uint64 Guid = 0;
    float HealthPct = 100.0f; // 0-100
    bool Alive = false;
    bool Tank = false;
    bool UnderAttack = false;
    bool InRange = false;
};

inline float Urgency(Member const& member)
{
    return member.HealthPct
        - (member.Tank && member.UnderAttack ? TankUnderAttackPct : 0.0f);
}

struct Choice
{
    uint64 Guid = 0;
    float HealthPct = 100.0f;
    bool Reachable = false;
};

// The legacy target: lowest health below the threshold, first in list order
// on a tie (the snapshot's order), no range or LOS test.
inline std::optional<Choice> LegacyLowest(std::vector<Member> const& members)
{
    std::optional<Choice> choice;
    float lowest = TriageHealthPct;
    for (Member const& member : members)
        if (member.Alive && member.HealthPct < lowest)
        {
            lowest = member.HealthPct;
            choice = Choice{ member.Guid, member.HealthPct, false };
        }
    return choice;
}

// hasLineOfSight(guid) is asked only for injured in-range members, in
// urgency order, until one passes.
template <typename LineOfSight>
std::optional<Choice> Select(std::vector<Member> const& members,
    LineOfSight&& hasLineOfSight)
{
    std::vector<Member const*> ranked;
    for (Member const& member : members)
        if (member.Alive && member.HealthPct < TriageHealthPct && member.InRange)
            ranked.push_back(&member);
    std::stable_sort(ranked.begin(), ranked.end(),
        [](Member const* left, Member const* right)
        {
            return Urgency(*left) < Urgency(*right);
        });
    for (Member const* member : ranked)
        if (hasLineOfSight(member->Guid))
            return Choice{ member->Guid, member->HealthPct, true };
    return LegacyLowest(members);
}

// Whether a living hostile currently attacks victim. The encounter snapshot
// publishes a boss and its ordinary adds as Hostiles, but summoned creatures
// as Summons (BotWorldPopulationMgrEncounterBlackboard.cpp): Nefarian's
// animated bone warriors (41918) hit a tank from there. A Summons entry
// counts when it is a hostile summon that can attack: kind Summon (a bot's own
// pets publish as Pet), alive and attackable (selectable and a valid attack
// target for the raid; a collapsed bone warrior is not selectable).
inline bool IsAttackedByHostile(BotEncounter::Blackboard const& board,
    ObjectGuid victim)
{
    for (BotEncounter::ActorSnapshot const& hostile : board.Hostiles)
        if (hostile.Alive && hostile.VictimGuid == victim)
            return true;
    for (BotEncounter::ActorSnapshot const& summon : board.Summons)
        if (summon.Kind == BotEncounter::ActorKind::Summon && summon.Alive
            && summon.Attackable && summon.VictimGuid == victim)
            return true;
    return false;
}

// The triage over the encounter snapshot: every player of it (bots and a play
// cohort's humans, as the legacy rule), the hostiles' and hostile summons'
// victims for the tank weighting. inHealRange(guid) is the native range test
// and hasLineOfSight(rawGuid) the native line of sight (see Select).
template <typename InHealRange, typename LineOfSight>
std::optional<Choice> SelectFromBoard(BotEncounter::Blackboard const& board,
    InHealRange&& inHealRange, LineOfSight&& hasLineOfSight)
{
    std::vector<Member> members;
    for (auto const* actors : { &board.Players, &board.ExternalPlayers })
        for (BotEncounter::ActorSnapshot const& actor : *actors)
        {
            Member member;
            member.Guid = actor.Guid.GetRawValue();
            member.HealthPct = actor.HealthPct;
            member.Alive = actor.Alive;
            member.Tank = actor.Role == "tank";
            if (member.Alive && member.HealthPct < TriageHealthPct)
            {
                member.UnderAttack = IsAttackedByHostile(board, actor.Guid);
                member.InRange = inHealRange(actor.Guid);
            }
            members.push_back(member);
        }
    return Select(members, std::forward<LineOfSight>(hasLineOfSight));
}
}

#endif
