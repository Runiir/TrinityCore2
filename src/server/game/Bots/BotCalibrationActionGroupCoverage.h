#ifndef TRINITY_BOT_CALIBRATION_ACTION_GROUP_COVERAGE_H
#define TRINITY_BOT_CALIBRATION_ACTION_GROUP_COVERAGE_H

#include <set>
#include <string>

namespace BotCalibrationActionGroupCoverage
{
inline std::string const& SelectedActionGroup(
    std::string const& actionGroup, std::string const& actionType)
{
    return actionGroup.empty() ? actionType : actionGroup;
}

inline void RecordExpectedActionGroup(
    std::set<std::string>& expectedActionGroups,
    bool scored,
    bool actionValid,
    std::string const& actionGroup,
    std::string const& actionType)
{
    if (!scored || !actionValid)
        return;

    std::string const& selectedGroup = SelectedActionGroup(actionGroup, actionType);
    if (!selectedGroup.empty())
        expectedActionGroups.insert(selectedGroup);
}

inline void RecordObservedActionGroup(
    std::set<std::string>& actionGroups,
    bool scored,
    bool actionValid,
    bool actionSucceeded,
    std::string const& actionGroup,
    std::string const& actionType)
{
    if (!scored || !actionValid || !actionSucceeded)
        return;

    std::string const& selectedGroup = SelectedActionGroup(actionGroup, actionType);
    if (!selectedGroup.empty())
        actionGroups.insert(selectedGroup);
}
}

#endif
