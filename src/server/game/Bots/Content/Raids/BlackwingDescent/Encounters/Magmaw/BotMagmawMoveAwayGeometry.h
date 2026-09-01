#ifndef TRINITY_BOT_MAGMAW_MOVE_AWAY_GEOMETRY_H
#define TRINITY_BOT_MAGMAW_MOVE_AWAY_GEOMETRY_H

#include "Bots/BotEncounterBlackboard.h"

#include <cmath>

namespace BotEncounter
{
inline Vector3 MagmawMoveAwayDestination(Vector3 const& actor,
    float actorFacing, Vector3 const& danger, float exitDistance)
{
    float dx = actor.X - danger.X;
    float dy = actor.Y - danger.Y;
    float length = std::hypot(dx, dy);
    if (length < 0.01f)
    {
        dx = std::cos(actorFacing);
        dy = std::sin(actorFacing);
        length = 1.0f;
    }
    return { danger.X + dx / length * exitDistance,
        danger.Y + dy / length * exitDistance, actor.Z };
}
}

#endif
