#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_CALIBRATION_LIFECYCLE_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_CALIBRATION_LIFECYCLE_H

#include <string>

namespace BotWorldPopulationMgrCalibrationLifecycle
{
inline bool IsCalibrationCloneSpawnSource(std::string const& spawnSource)
{
    return spawnSource == "combat_calibration";
}

inline bool ShouldSuppressMeleeAutoAttack(std::string const& spawnSource,
    bool calibrationStopping, bool calibrationActive,
    bool calibrationWindowComplete)
{
    return IsCalibrationCloneSpawnSource(spawnSource)
        && (calibrationStopping
            || (calibrationActive && calibrationWindowComplete));
}

template <typename GuidSet>
inline bool IsRetainedStoppingCalibrationClone(
    typename GuidSet::value_type const& guid, GuidSet const& retainedGuids)
{
    return retainedGuids.find(guid) != retainedGuids.end();
}

template <typename Guid, typename StateRange>
inline bool IsLiveCalibrationClone(Guid const& guid, StateRange const& states)
{
    for (auto const& state : states)
        if (state.Guid == guid
            && IsCalibrationCloneSpawnSource(state.SpawnSource))
            return true;
    return false;
}

template <typename Guid, typename GuidSet, typename StateRange>
inline bool IsIdentifiedCalibrationClone(Guid const& guid,
    GuidSet const& retainedGuids, StateRange const& liveStates)
{
    return IsRetainedStoppingCalibrationClone(guid, retainedGuids)
        || IsLiveCalibrationClone(guid, liveStates);
}
}

#endif
