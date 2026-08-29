#ifndef TRINITY_BOT_VALIDATION_ROUTE_COMBAT_AUTHORITY_H
#define TRINITY_BOT_VALIDATION_ROUTE_COMBAT_AUTHORITY_H

namespace BotValidationRouteCombatAuthority
{
enum class TargetDecision
{
    AllowRegroup,
    PreserveProposed,
    RecoverActivePack,
};

// Current-node combat authority is resolved before generic regroup.  The
// caller proves target eligibility; this table only owns precedence.
constexpr TargetDecision Resolve(bool trashRoute,
    bool proposedCurrentTarget, bool activeCurrentPackTarget)
{
    if (!trashRoute)
        return TargetDecision::AllowRegroup;
    if (proposedCurrentTarget)
        return TargetDecision::PreserveProposed;
    if (activeCurrentPackTarget)
        return TargetDecision::RecoverActivePack;
    return TargetDecision::AllowRegroup;
}
}

#endif
