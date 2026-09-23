#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotCombatActionCatalog.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <map>
#include <string>
#include <vector>

// Outcome of a profile resolution that selected no valid action: the
// per-route rejection aggregates and the wait / melee fallback action.
// ResolveProfileCombatAction owns candidate selection; this module only
// reports and describes the no-action result.

void BotWorldPopulationMgr::RecordNoProfileActionRejections(Player* bot,
    std::vector<BotActionCandidate> const& candidates) const
{
    // A generic no_valid_profile_action is not actionable by itself. Preserve
    // the full-window native reasons that made every candidate in this
    // resolution invalid, so a canary can distinguish a bad DB gate from a
    // shared arbitration or movement problem without replaying the tail trace.
    if (bot
        && Cohort().Active && Cohort().Config.ValidationRouteEnable
        && Cohort().Config.ValidationRouteKind == "boss"
        && Party().ValidationRouteGeneration)
    {
        uint32 const botKey = bot->GetGUID().GetCounter();
        uint64 const recordedAtMs = BotWorldPopulationMgrSpellSemantics::NowMs();
        for (BotActionCandidate const& candidate : candidates)
        {
            if (!candidate.SpellId || candidate.RejectReason.empty())
                continue;

            CombatCandidateRejectKey key;
            key.RouteGeneration = Party().ValidationRouteGeneration;
            key.RouteNodeId = Cohort().Config.ValidationRouteNodeId;
            key.ActorGuid = botKey;
            key.Phase = "profile_resolve";
            key.SpellId = candidate.SpellId;
            key.ActionCategory = BotCombatActionCatalog::ToString(candidate.Category);
            key.Reason = candidate.RejectReason;

            CombatCandidateRejectAggregate& aggregate =
                Party().CombatCandidateRejections[key];
            if (!aggregate.Count)
            {
                aggregate.ActorName = bot->GetName();
                aggregate.ActorRole = GetDungeonRole(bot);
                aggregate.ActorClassId = bot->getClass();
                aggregate.FirstAtMs = recordedAtMs;
            }
            aggregate.LastAtMs = recordedAtMs;
            ++aggregate.Count;
        }
    }
}

ResolvedCombatAction BotWorldPopulationMgr::ResolveNoProfileAction(Player* bot,
    Unit* target, BotClassSpecActionProfile const& profile,
    std::vector<BotActionCandidate> const& candidates, bool areaOnly,
    ResolvedCombatAction action) const
{
    bool globalCooldownSchedulingWait = std::any_of(
        candidates.begin(), candidates.end(), [](BotActionCandidate const& candidate)
        {
            return candidate.RejectReason == "global_cooldown";
        });
    std::map<std::string, uint32> rejectionCounts;
    for (BotActionCandidate const& candidate : candidates)
        if (!candidate.RejectReason.empty())
            ++rejectionCounts[candidate.RejectReason];
    auto dominantRejection = std::max_element(
        rejectionCounts.begin(), rejectionCounts.end(),
        [](auto const& left, auto const& right)
        {
            return left.second < right.second;
        });
    action.ResolutionReason = dominantRejection != rejectionCounts.end()
        ? dominantRejection->first : "no_valid_profile_action";
    // Rerun157 showed that a legal Fire filler rejected only by the native
    // GCD lost its spell identity here, so the diagnostic layer could not
    // observe HasGlobalCooldown and mislabeled the scheduling wait as an
    // inactive no_action. Preserve the resolver cause without changing any
    // candidate, cooldown, or role-quality threshold.
    action.DebugName = profile.MissingProfile ? profile.ProfileSource
        : (globalCooldownSchedulingWait ? "global_cooldown"
                                        : (action.ResolutionReason == "already_casting"
                                            ? "already_casting"
                                            : "no_valid_profile_action"));
    if (!profile.MissingProfile && !areaOnly && profile.AutoAttackMode == "melee"
        && bot->IsValidAttackTarget(target))
    {
        // Rerun169 canary 3 reached a remote healer-owned cluster after every
        // native Protection pickup was temporarily unavailable. The fallback
        // retained the profile's ranged maximum, so ordinary trash considered
        // it in range and repeatedly submitted a remote melee fallback without
        // closing range across the eligible exposure interval. Describe its actual
        // native reach so the existing caller movement gate closes range
        // before retrying it.
        action.Valid = true;
        action.Type = "auto_attack";
        action.TargetGuid = target->GetGUID();
        action.DebugName = "melee_auto_attack_fallback";
        action.MinRange = 0.0f;
        action.MaxRange = std::max(5.0f, bot->GetMeleeRange(target));
    }
    return action;
}
