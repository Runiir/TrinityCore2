#ifndef TRINITY_BOT_ROLE_SATURATION_POLICY_H
#define TRINITY_BOT_ROLE_SATURATION_POLICY_H

#include "Define.h"
#include <string>

class Player;
class Unit;

enum class BotRoleBalanceMode : uint8
{
    PureSurvival,
    RoleFirst,
    BalancedRoleDps,
    DpsPush,
    Recovery,
    NoValidSafeAction
};

struct BotRoleSaturationInputs
{
    std::string Role = "dps";
    float SelfHpPct = 1.0f;
    float GroupAverageHpPct = 1.0f;
    float LowestAllyHpPct = 1.0f;
    float HealerManaPct = 1.0f;
    float TankHpPct = 1.0f;
    float EncounterDangerScore = 0.0f;
    float InterruptPressure = 0.0f;
    float ThreatStability = 1.0f;
    float DamageOpportunity = 0.5f;
    float LearnedReward = 0.0f;
    float LearnedDanger = 0.0f;
    float LearnedConfidence = 0.0f;
    bool RecentDeath = false;
    bool TankBuster = false;
    bool AddPressure = false;
    bool MovementPressure = false;
    bool DangerousDebuff = false;
    bool NoValidActions = false;
};

struct RoleSaturationState
{
    float PrimaryRoleSatisfiedScore = 0.0f;
    float SafetyMarginScore = 0.0f;
    float GroupStabilityScore = 0.0f;
    float EncounterPressureScore = 0.0f;
    float ResourceMarginScore = 0.0f;
    float ThreatMarginScore = 0.0f;
    float HealingMarginScore = 0.0f;
    float DamageOpportunityScore = 0.0f;
    float ExperimentConfidence = 0.0f;
    BotRoleBalanceMode RecommendedBalanceMode = BotRoleBalanceMode::RoleFirst;
    std::string SaturationReason = "role_first";

    std::string ToJson() const;
};

class BotRoleSaturationPolicy
{
public:
    static char const* ToString(BotRoleBalanceMode mode);
    static BotRoleSaturationInputs BuildInputs(Player const* bot, Unit const* target, std::string const& role, float encounterDanger, float interruptPressure, bool tankBuster, bool adds, float learnedReward, float learnedDanger, float learnedConfidence, bool noValidActions = false);
    static RoleSaturationState Evaluate(BotRoleSaturationInputs const& inputs);
};

#endif
