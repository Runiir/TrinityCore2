#ifndef TRINITY_BOT_PROGRESSION_GOAL_POLICY_H
#define TRINITY_BOT_PROGRESSION_GOAL_POLICY_H

#include "Define.h"
#include <string>

class Player;

class BotProgressionGoalPolicy
{
public:
    static std::string RoleGoal(std::string const& role);
    static std::string ProgressionReason(Player const* bot, char const* activity, char const* situation);
    static std::string ProfessionGoalJson(Player const* bot, std::string const& role, char const* activity);
    static std::string QuestPortfolioSummaryJson(uint32 activeQuestCount, uint32 clusterId, char const* phase, char const* unsupportedReason);
};

#endif
