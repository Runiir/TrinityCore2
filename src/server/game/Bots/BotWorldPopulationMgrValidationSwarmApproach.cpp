#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Creature.h"
#include "GameTime.h"
#include "Player.h"
#include "Unit.h"

#include <chrono>
#include <limits>
#include <string>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

bool BotWorldPopulationMgr::ContinueStableTankSwarmApproach(
    WorldBotState& state, Unit* selectedAdd, Player* densityHealer,
    std::string const& role, BotClassSpecActionProfile const& profile,
    bool cohortSwarmActive, float tankDensityClusterRadius) const
{
    uint64 currentMs = NowMs();
    uint64 pathAgeMs = state.LastPathChangeMs && currentMs >= state.LastPathChangeMs
        ? currentMs - state.LastPathChangeMs
        : std::numeric_limits<uint64>::max();
    // Rerun183 exposed one identity-stable healer-owned follower that
    // remained behind the generic two-second moving-swarm endpoint for
    // nine decisions and exceeded the hard dwell gate. That stability
    // window protects ordinary representative churn; it is too long
    // once the selected identity is itself current healer threat.
    // Revalidate only that urgent native path after three 250-ms
    // decisions. All movement legality and the ordinary two-second
    // swarm fallback remain unchanged.
    bool selectedHealerOwned = densityHealer && selectedAdd
        && selectedAdd->GetVictim() == densityHealer;
    // Rerun213 found the equivalent topology gap for Protection: its
    // selected Azil follower changed every 250 ms while a valid path
    // was already converging on the same healer-owned cluster. Keep
    // that Protection path for six decisions, still below the hard
    // 3000-ms dwell ceiling; preserve Feral's proven three-decision
    // healer-threat bound and the ordinary two-second swarm window.
    bool feralTank = profile.SpecTag == "feral_druid_tank";
    bool protectionPaladin = profile.SpecTag == "protection";
    uint64 stableApproachLimitMs = selectedHealerOwned
        ? (protectionPaladin ? 1500 : 750)
        : 2000;
    return role == "tank" && (feralTank || protectionPaladin)
        && cohortSwarmActive && selectedAdd && state.ActivePathValid
        && state.IsMoving && pathAgeMs <= stableApproachLimitMs
        && selectedAdd->GetExactDist2d(state.ActivePathToX, state.ActivePathToY)
            <= tankDensityClusterRadius;
}
