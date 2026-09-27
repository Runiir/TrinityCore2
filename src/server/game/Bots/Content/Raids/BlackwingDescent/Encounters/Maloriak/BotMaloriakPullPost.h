#ifndef TRINITY_BOT_MALORIAK_PULL_POST_H
#define TRINITY_BOT_MALORIAK_PULL_POST_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFormation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakGeometry.h"

#include <cmath>
#include <optional>
#include <vector>

// The off-tank takes an add off Maloriak's side from range. Growth Catalyst
// (77987) is a 10-yard area aura on every Aberration and Prime Subject, and
// Maloriak is inside it when they stand at him. In r01 kill 6bf522 the Feral
// walked to the boss for the adds on the Blood DK (the pickup chases its
// target into melee) and its whole pack followed: from 140 to 165 s eight or
// nine adds stood within 10 yards of him, and the Felguard's and the Blood
// DK's melee on him fell from about 4,000 and 9,000 to 360-800 and
// 1,000-2,700 per hit (the Felguard's recovered to 4,138 at 175 s, once the
// Feral had walked the pack to its add spot). So an add near the boss is
// taunted from a post 15 yards out on the add-spot side (Growl, Dark Command,
// Hand of Reckoning and Taunt reach 30 yards), and the pack stays there.
namespace BotEncounter::Maloriak
{
// Growth Catalyst radius plus a margin: an add this close to Maloriak is
// taken from the post.
constexpr float CatalystPickupYards = 12.0f;
// The post: 15 yards from the boss, so the held pack (in melee of the
// off-tank) stays outside the 10-yard aura.
constexpr float CatalystPostYards = 15.0f;
// Taunt reach with a margin (SpellRange 30 yards).
constexpr float TauntReachYards = 28.0f;
constexpr float PullPostTolerance = 3.0f;

// The post for a pickup standing within CatalystPickupYards of the boss:
// on the line from the boss toward the add anchor, rotated up to 60 degrees
// when that point lies in a hazard clearance or outside the room, and
// within taunt reach of the pickup. nullopt when the pickup is not near the
// boss or no such point exists (the ordinary chase then applies).
inline std::optional<Vector3> CatalystPullPost(Observation const& observation,
    Vector3 const& anchor, Vector3 const& pickup)
{
    Vector3 const boss = observation.Boss->Position;
    if (Distance2d(pickup, boss) >= CatalystPickupYards)
        return std::nullopt;
    float const base = std::atan2(anchor.Y - boss.Y, anchor.X - boss.X);
    std::vector<FormationHazard> const hazards = CollectFormationHazards(observation);
    static constexpr float Rotations[] = { 0.0f, 30.0f, -30.0f, 60.0f, -60.0f };
    for (float degrees : Rotations)
    {
        float const angle = base + degrees * Pi / 180.0f;
        Vector3 const post{ boss.X + std::cos(angle) * CatalystPostYards,
            boss.Y + std::sin(angle) * CatalystPostYards, RoomFloorZ };
        if (!InRoom(post) || !ClearOfHazards(post, hazards)
            || Distance2d(post, pickup) > TauntReachYards)
            continue;
        return post;
    }
    return std::nullopt;
}
}

#endif
