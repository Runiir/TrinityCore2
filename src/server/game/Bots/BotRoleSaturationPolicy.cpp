#include "Bots/BotRoleSaturationPolicy.h"
#include "Group.h"
#include "GroupReference.h"
#include "LFG.h"
#include "Player.h"
#include "Unit.h"
#include <algorithm>
#include <sstream>

namespace
{
float Clamp01(float v)
{
    return std::max(0.0f, std::min(1.0f, v));
}

std::string RoleSaturationEscape(std::string const& value)
{
    std::ostringstream out;
    for (char c : value)
    {
        if (c == '\\' || c == '"')
            out << '\\';
        out << c;
    }
    return out.str();
}

float HealthPct(Unit const* unit)
{
    return unit && unit->GetMaxHealth() ? float(unit->GetHealth()) / float(unit->GetMaxHealth()) : 0.0f;
}
}

char const* BotRoleSaturationPolicy::ToString(BotRoleBalanceMode mode)
{
    switch (mode)
    {
        case BotRoleBalanceMode::PureSurvival: return "pure_survival";
        case BotRoleBalanceMode::RoleFirst: return "role_first";
        case BotRoleBalanceMode::BalancedRoleDps: return "balanced_role_dps";
        case BotRoleBalanceMode::DpsPush: return "dps_push";
        case BotRoleBalanceMode::Recovery: return "recovery";
        case BotRoleBalanceMode::NoValidSafeAction: return "no_valid_safe_action";
        default: return "role_first";
    }
}

std::string RoleSaturationState::ToJson() const
{
    std::ostringstream json;
    json << "{\"primary_role_satisfied_score\":" << PrimaryRoleSatisfiedScore
         << ",\"safety_margin_score\":" << SafetyMarginScore
         << ",\"group_stability_score\":" << GroupStabilityScore
         << ",\"encounter_pressure_score\":" << EncounterPressureScore
         << ",\"resource_margin_score\":" << ResourceMarginScore
         << ",\"threat_margin_score\":" << ThreatMarginScore
         << ",\"healing_margin_score\":" << HealingMarginScore
         << ",\"damage_opportunity_score\":" << DamageOpportunityScore
         << ",\"experiment_confidence\":" << ExperimentConfidence
         << ",\"recommended_balance_mode\":\"" << BotRoleSaturationPolicy::ToString(RecommendedBalanceMode) << "\""
         << ",\"saturation_reason\":\"" << RoleSaturationEscape(SaturationReason) << "\"}";
    return json.str();
}

BotRoleSaturationInputs BotRoleSaturationPolicy::BuildInputs(Player const* bot, Unit const* target, std::string const& role, float encounterDanger, float interruptPressure, bool tankBuster, bool adds, float learnedReward, float learnedDanger, float learnedConfidence, bool noValidActions)
{
    BotRoleSaturationInputs inputs;
    inputs.Role = role.empty() ? "dps" : role;
    inputs.SelfHpPct = HealthPct(bot);
    inputs.GroupAverageHpPct = inputs.SelfHpPct > 0.0f ? inputs.SelfHpPct : 1.0f;
    inputs.LowestAllyHpPct = inputs.GroupAverageHpPct;
    inputs.TankHpPct = inputs.GroupAverageHpPct;
    inputs.HealerManaPct = 1.0f;
    inputs.EncounterDangerScore = Clamp01(encounterDanger);
    inputs.InterruptPressure = Clamp01(interruptPressure);
    inputs.TankBuster = tankBuster;
    inputs.AddPressure = adds;
    inputs.NoValidActions = noValidActions;
    inputs.LearnedReward = learnedReward;
    inputs.LearnedDanger = Clamp01(learnedDanger);
    inputs.LearnedConfidence = Clamp01(learnedConfidence);

    if (bot && bot->GetGroup())
    {
        Group* group = const_cast<Group*>(bot->GetGroup());
        float totalHp = 0.0f;
        uint32 members = 0;
        float healerMana = 0.0f;
        uint32 healers = 0;
        bool tankSeen = false;
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap())
                continue;
            float hp = HealthPct(member);
            totalHp += hp;
            inputs.LowestAllyHpPct = members ? std::min(inputs.LowestAllyHpPct, hp) : hp;
            ++members;
            uint8 roles = group->GetLfgRoles(member->GetGUID());
            if (roles & lfg::PLAYER_ROLE_TANK)
            {
                inputs.TankHpPct = hp;
                tankSeen = true;
            }
            if (roles & lfg::PLAYER_ROLE_HEALER)
            {
                uint32 maxPower = member->GetMaxPower(member->GetPowerType());
                healerMana += maxPower ? float(member->GetPower(member->GetPowerType())) / float(maxPower) : 1.0f;
                ++healers;
            }
        }
        if (members)
            inputs.GroupAverageHpPct = totalHp / float(members);
        if (!tankSeen)
            inputs.TankHpPct = inputs.GroupAverageHpPct;
        if (healers)
            inputs.HealerManaPct = healerMana / float(healers);
    }

    if (target && target->GetVictim())
    {
        if (bot && target->GetVictim() == bot)
            inputs.ThreatStability = role == "tank" ? 1.0f : 0.25f;
        else
            inputs.ThreatStability = role == "tank" ? 0.35f : 0.85f;
    }
    inputs.DamageOpportunity = Clamp01((target && target->IsAlive() ? 0.65f : 0.25f) + std::max(0.0f, learnedReward) * 0.05f - inputs.EncounterDangerScore * 0.35f);
    return inputs;
}

RoleSaturationState BotRoleSaturationPolicy::Evaluate(BotRoleSaturationInputs const& inputs)
{
    RoleSaturationState state;
    state.SafetyMarginScore = Clamp01((inputs.SelfHpPct + inputs.LowestAllyHpPct + inputs.GroupAverageHpPct) / 3.0f - inputs.LearnedDanger * 0.35f - (inputs.RecentDeath ? 0.35f : 0.0f));
    state.GroupStabilityScore = Clamp01((inputs.GroupAverageHpPct * 0.45f) + (inputs.LowestAllyHpPct * 0.35f) + (inputs.TankHpPct * 0.20f) - inputs.EncounterDangerScore * 0.45f);
    state.EncounterPressureScore = Clamp01(inputs.EncounterDangerScore + inputs.InterruptPressure * 0.25f + (inputs.TankBuster ? 0.25f : 0.0f) + (inputs.AddPressure ? 0.15f : 0.0f) + (inputs.MovementPressure ? 0.15f : 0.0f));
    state.ResourceMarginScore = Clamp01(inputs.HealerManaPct - inputs.LearnedDanger * 0.20f);
    state.ThreatMarginScore = Clamp01(inputs.ThreatStability - (inputs.AddPressure ? 0.15f : 0.0f));
    state.HealingMarginScore = Clamp01((inputs.GroupAverageHpPct + inputs.LowestAllyHpPct + inputs.HealerManaPct) / 3.0f - state.EncounterPressureScore * 0.35f);
    state.DamageOpportunityScore = Clamp01(inputs.DamageOpportunity + std::max(0.0f, inputs.LearnedReward) * 0.03f - state.EncounterPressureScore * 0.25f);
    state.ExperimentConfidence = Clamp01(inputs.LearnedConfidence * (inputs.LearnedReward >= 0.0f ? 1.0f : 0.35f) - inputs.LearnedDanger * 0.30f);

    if (inputs.NoValidActions)
    {
        state.RecommendedBalanceMode = BotRoleBalanceMode::NoValidSafeAction;
        state.SaturationReason = "no_valid_actions_after_mask";
        return state;
    }

    if (inputs.Role == "healer")
    {
        state.PrimaryRoleSatisfiedScore = Clamp01(state.HealingMarginScore * 0.55f + state.GroupStabilityScore * 0.30f + state.ResourceMarginScore * 0.15f);
        float weaveScore = Clamp01(state.PrimaryRoleSatisfiedScore + state.DamageOpportunityScore * 0.35f + state.ExperimentConfidence * 0.20f - state.EncounterPressureScore * 0.45f);
        if (state.GroupStabilityScore < 0.25f || state.SafetyMarginScore < 0.25f)
        {
            state.RecommendedBalanceMode = BotRoleBalanceMode::Recovery;
            state.SaturationReason = "healing_required_group_or_safety_unstable";
        }
        else if (state.EncounterPressureScore > 0.70f || inputs.DangerousDebuff)
        {
            state.RecommendedBalanceMode = BotRoleBalanceMode::PureSurvival;
            state.SaturationReason = "healing_required_mechanic_or_debuff_pressure";
        }
        else if (weaveScore > 0.65f)
        {
            state.RecommendedBalanceMode = BotRoleBalanceMode::BalancedRoleDps;
            state.SaturationReason = "healing_saturated_safe_dps_weave_from_context_and_outcomes";
        }
        else
        {
            state.RecommendedBalanceMode = BotRoleBalanceMode::RoleFirst;
            state.SaturationReason = "healing_primary_until_context_saturates";
        }
    }
    else if (inputs.Role == "tank")
    {
        state.PrimaryRoleSatisfiedScore = Clamp01(state.SafetyMarginScore * 0.35f + state.ThreatMarginScore * 0.35f + state.GroupStabilityScore * 0.15f + (1.0f - state.EncounterPressureScore) * 0.15f);
        float pushScore = Clamp01(state.PrimaryRoleSatisfiedScore + state.DamageOpportunityScore * 0.40f + state.ExperimentConfidence * 0.20f - (inputs.TankBuster ? 0.35f : 0.0f));
        if (inputs.TankBuster || state.SafetyMarginScore < 0.25f)
        {
            state.RecommendedBalanceMode = BotRoleBalanceMode::PureSurvival;
            state.SaturationReason = "tank_survival_or_buster_pressure";
        }
        else if (state.ThreatMarginScore < 0.35f || inputs.AddPressure)
        {
            state.RecommendedBalanceMode = BotRoleBalanceMode::RoleFirst;
            state.SaturationReason = "tank_threat_positioning_or_add_control_primary";
        }
        else if (pushScore > 0.70f)
        {
            state.RecommendedBalanceMode = BotRoleBalanceMode::BalancedRoleDps;
            state.SaturationReason = "tank_role_saturated_safe_damage_from_context_and_outcomes";
        }
        else
        {
            state.RecommendedBalanceMode = BotRoleBalanceMode::RoleFirst;
            state.SaturationReason = "tank_role_first";
        }
    }
    else
    {
        state.PrimaryRoleSatisfiedScore = Clamp01(state.DamageOpportunityScore * 0.55f + state.SafetyMarginScore * 0.25f + state.GroupStabilityScore * 0.20f);
        if (state.SafetyMarginScore < 0.20f || state.GroupStabilityScore < 0.20f)
        {
            state.RecommendedBalanceMode = BotRoleBalanceMode::Recovery;
            state.SaturationReason = "dps_recovery_over_greed";
        }
        else if (state.EncounterPressureScore > 0.70f)
        {
            state.RecommendedBalanceMode = BotRoleBalanceMode::RoleFirst;
            state.SaturationReason = "dps_mechanics_interrupts_switches_before_damage";
        }
        else if (state.DamageOpportunityScore + state.ExperimentConfidence > 1.15f)
        {
            state.RecommendedBalanceMode = BotRoleBalanceMode::DpsPush;
            state.SaturationReason = "effective_dps_push_safe_from_context_and_outcomes";
        }
        else
        {
            state.RecommendedBalanceMode = BotRoleBalanceMode::RoleFirst;
            state.SaturationReason = "effective_dps_with_mechanic_responsibilities";
        }
    }

    return state;
}
