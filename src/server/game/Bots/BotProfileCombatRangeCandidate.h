#ifndef TRINITY_BOT_PROFILE_COMBAT_RANGE_CANDIDATE_H
#define TRINITY_BOT_PROFILE_COMBAT_RANGE_CANDIDATE_H

#include "Bots/BotActionArbiter.h"

#include <functional>
#include <string>

// This adapter owns only the value-level admission contract for the generic
// profile range lane.  The manager supplies observations and the existing
// native range mover; the adapter does not inspect or mutate world state.
namespace BotProfileCombatRangeCandidate
{
constexpr char Key[] = "world.profile_combat_range";
constexpr char Source[] = "db_class_spec_profile";

struct Decision
{
    bool TypedDrudgeValidationRoute = false;
    bool AdaptiveDrudgeOwnsNode = false;
    bool DrudgeCombatAuthorityAllowed = true;
    bool TargetPresent = false;
    bool TargetInWorld = false;
    bool TargetAlive = false;
    bool TargetAttackable = false;
    bool SameMap = false;
    bool SameInstance = false;
    bool OwnedDrudge = false;
    float Distance = 0.0f;
    float MinRange = 0.0f;
    float MaxRange = 0.0f;
    bool NoLineOfSight = false;
    std::function<bool()> Move;
};

struct Request
{
    float UtilityScore = 0.0f;
    std::function<Decision()> Observe;
};

inline BotActionArbitration::Outcome Evaluate(Decision decision)
{
    if (decision.TypedDrudgeValidationRoute
        && decision.AdaptiveDrudgeOwnsNode
        && !decision.DrudgeCombatAuthorityAllowed)
        return BotActionArbitration::Outcome::NotApplicable(
            "drudge_activation_latch_closed");

    if (!decision.TargetPresent || !decision.TargetInWorld
        || !decision.TargetAlive || !decision.TargetAttackable
        || !decision.SameMap || !decision.SameInstance)
        return BotActionArbitration::Outcome::NotApplicable(
            "profile_combat_target_invalid");

    bool const insideLegalMinRange = decision.MinRange > 0.0f
        && decision.Distance < decision.MinRange;
    bool const outsideLegalMaxRange = decision.MaxRange > 0.0f
        && decision.Distance > decision.MaxRange;
    if (decision.OwnedDrudge)
    {
        if (!outsideLegalMaxRange && !decision.NoLineOfSight)
            return BotActionArbitration::Outcome::NotApplicable(
                "drudge_profile_range_satisfied");
    }
    else if (!insideLegalMinRange)
        return BotActionArbitration::Outcome::NotApplicable(
            "profile_min_range_satisfied");

    if (!decision.Move || !decision.Move())
        return BotActionArbitration::Outcome::Retryable(
            decision.OwnedDrudge
                ? (decision.NoLineOfSight
                    ? "drudge_profile_los_path_rejected"
                    : "drudge_profile_range_path_rejected")
                : "profile_min_range_path_rejected");

    return BotActionArbitration::Outcome::Started(
        decision.OwnedDrudge
            ? (decision.NoLineOfSight ? "profile_combat_los_reconciled"
                : "profile_combat_range_reconciled")
            : "profile_combat_min_range_reconciled");
}

inline BotActionArbitration::Candidate Build(Request request)
{
    BotActionArbitration::Candidate candidate;
    candidate.Key = Key;
    candidate.Source = Source;
    candidate.ActionPriority = BotActionArbitration::Priority::CombatMovement;
    candidate.UtilityScore = request.UtilityScore;
    candidate.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::Movement);
    std::function<Decision()> observe = std::move(request.Observe);
    candidate.Attempt = [observe = std::move(observe)]() mutable
    {
        return Evaluate(observe ? observe() : Decision{});
    };
    return candidate;
}
}

#endif
