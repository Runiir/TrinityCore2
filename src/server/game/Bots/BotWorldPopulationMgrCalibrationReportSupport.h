#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_CALIBRATION_REPORT_SUPPORT_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_CALIBRATION_REPORT_SUPPORT_H

#include "Bots/BotWorldPopulationMgrConfig.h"

#include <string>
#include <unordered_set>

namespace BotWorldPopulationMgrCalibrationReport
{
inline char const* RuntimeModeName(BotWorldRuntimeMode mode)
{
    switch (mode)
    {
        case BotWorldRuntimeMode::AlwaysOnAutonomy: return "always_on_autonomy";
        case BotWorldRuntimeMode::CalibrationFixture: return "calibration_fixture";
        case BotWorldRuntimeMode::ReplayFixture: return "replay_fixture";
        case BotWorldRuntimeMode::ManualExperiment: return "manual_experiment";
    }
    return "unknown";
}

inline bool CalibrationSpecUsesMana(std::string const& targetSpec)
{
    static std::unordered_set<std::string> const ManaSpecs = {
        "affliction_warlock", "arcane_mage", "balance_druid",
        "demonology_warlock", "destruction_warlock", "discipline_priest",
        "elemental_shaman", "enhancement_shaman", "fire_mage", "frost_mage",
        "holy_paladin", "holy_priest", "protection_paladin",
        "restoration_druid", "restoration_shaman", "retribution_paladin",
        "shadow_priest",
    };
    return ManaSpecs.find(targetSpec) != ManaSpecs.end();
}
}

#endif
