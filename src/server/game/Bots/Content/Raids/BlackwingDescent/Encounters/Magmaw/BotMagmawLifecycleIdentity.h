#ifndef TRINITY_BOT_MAGMAW_LIFECYCLE_IDENTITY_H
#define TRINITY_BOT_MAGMAW_LIFECYCLE_IDENTITY_H

#include "Define.h"

#include <string_view>

namespace BotMagmawLifecycleIdentity
{
constexpr uint32 MapId = 669;
constexpr uint32 BossId = 0;
constexpr uint32 BossEntry = 41570;
constexpr std::string_view RouteNode = "bwd.magmaw.encounter";
constexpr std::string_view EncounterId = "blackwing_descent.magmaw";

inline bool OwnsRoute(uint32 mapId, std::string_view routeNode)
{
    return mapId == MapId && routeNode == RouteNode;
}
}

#endif
