#ifndef TRINITY_WORLD_OBJECT_MOVEMENT_H
#define TRINITY_WORLD_OBJECT_MOVEMENT_H

#include "Define.h"

class WorldObject;
struct Position;

namespace WorldObjectMovement
{
// Explicit straight mode skips only navmesh projection; native collision and
// allowed-Z finalization remain shared with the ordinary member API.
TC_GAME_API void MovePositionToFirstCollision(WorldObject& object, Position& pos,
    float dist, float angle, bool usePathfinding);
}

#endif
