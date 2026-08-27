#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Group.h"
#include "Instances/InstanceScript.h"
#include "Map.h"
#include "PathGenerator.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <string>
#include <vector>

namespace
{
bool IsNativeCombatResSpell(SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;

    if (spellInfo->Id == 20484)
        return true;

    bool const isResurrect = spellInfo->HasEffect(SPELL_EFFECT_RESURRECT)
        || spellInfo->HasEffect(SPELL_EFFECT_RESURRECT_NEW)
        || spellInfo->HasEffect(SPELL_EFFECT_RESURRECT_WITH_AURA);
    return isResurrect && spellInfo->HasAttribute(SPELL_ATTR8_ENFORCE_IN_COMBAT_RESSURECTION_LIMIT);
}

bool HasPowerForSpell(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return false;

    int32 powerCost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (powerCost <= 0)
        return true;
    if (spellInfo->PowerType >= MAX_POWERS)
        return true;
    if (spellInfo->PowerType == POWER_HEALTH)
        return int64(bot->GetHealth()) > powerCost;
    return bot->GetPower(Powers(spellInfo->PowerType)) >= uint32(powerCost);
}
}

bool BotWorldPopulationMgr::CurrentCombatResOwnerUsable(WorldBotState const& targetState,
    Player const* target, uint64 nowMs, std::string& declineReason) const
{
    declineReason.clear();
    bool const approachReservation = targetState.NativeBattleResDecision == "reserved_approach";
    bool const submittedCastPending = targetState.NativeBattleResDecision == "reserved_cast_submitted";
    if (!approachReservation && !submittedCastPending)
    {
        declineReason = "declined_reservation_missing";
        return false;
    }
    if (!targetState.NativeBattleResDecisionAtMs
        || targetState.NativeBattleResDecisionAtMs > nowMs
        || targetState.NativeBattleResDecisionUntilMs <= nowMs)
    {
        declineReason = submittedCastPending
            ? "declined_submitted_cast_expired" : "declined_approach_reservation_expired";
        return false;
    }
    if (!IsNativeCombatResTarget(targetState, target))
    {
        declineReason = "declined_target_ineligible";
        return false;
    }
    if (targetState.NativeBattleResOwnerGuid.IsEmpty() || !targetState.NativeBattleResSpellId)
    {
        declineReason = "declined_owner_or_spell_missing";
        return false;
    }

    WorldBotState const* ownerState = nullptr;
    Player* owner = nullptr;
    for (WorldBotState const& candidate : Party().Bots)
        if (candidate.Guid == targetState.NativeBattleResOwnerGuid)
        {
            ownerState = &candidate;
            owner = GetLoadedBot(candidate);
            break;
        }
    if (!ownerState || !owner)
    {
        declineReason = "declined_owner_unloaded";
        return false;
    }
    if (!owner->IsInWorld())
    {
        declineReason = "declined_owner_not_in_world";
        return false;
    }
    if (!owner->IsAlive())
    {
        declineReason = "declined_owner_dead";
        return false;
    }
    if (!ownerState->ValidationCohortLocked)
    {
        declineReason = "declined_owner_identity_unlocked";
        return false;
    }
    if (owner->GetMap() != target->GetMap() || owner->GetMapId() != target->GetMapId())
    {
        declineReason = "declined_owner_wrong_map";
        return false;
    }
    if (owner->GetInstanceId() != target->GetInstanceId())
    {
        declineReason = "declined_owner_wrong_instance";
        return false;
    }
    Group const* targetGroup = target->GetGroup();
    Group const* ownerGroup = owner->GetGroup();
    if (!targetGroup || !ownerGroup || ownerGroup != targetGroup
        || !owner->IsInSameGroupWith(target)
        || targetGroup->GetGUID() != targetState.ValidationCohortGroupGuid
        || targetGroup->GetLeaderGUID() != targetState.ValidationCohortLeaderGuid
        || ownerGroup->GetGUID() != ownerState->ValidationCohortGroupGuid
        || ownerGroup->GetLeaderGUID() != ownerState->ValidationCohortLeaderGuid)
    {
        declineReason = "declined_owner_wrong_group";
        return false;
    }

    uint32 const spellId = targetState.NativeBattleResSpellId;
    auto const playerSpell = owner->GetSpellMap().find(spellId);
    if (playerSpell == owner->GetSpellMap().end()
        || playerSpell->second.state == PLAYERSPELL_REMOVED
        || playerSpell->second.disabled || !playerSpell->second.active
        || !owner->HasSpell(spellId))
    {
        declineReason = "declined_combat_res_not_learned";
        return false;
    }
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    if (!IsNativeCombatResSpell(spellInfo))
    {
        declineReason = "declined_spell_not_combat_res";
        return false;
    }

    float const resurrectionRange = std::max(5.0f,
        owner->GetSpellMaxRangeForTarget(target, spellInfo));
    bool const inCastEnvelope = owner->IsWithinLOSInMap(target)
        && owner->IsWithinDistInMap(target, resurrectionRange);
    if (!inCastEnvelope)
    {
        PathGenerator path(owner);
        bool const pathOk = path.CalculatePath(target->GetPositionX(),
            target->GetPositionY(), target->GetPositionZ(), false);
        PathType const pathType = path.GetPathType();
        bool const validApproachPath = pathOk
            && !(pathType & PATHFIND_NOPATH)
            && !(pathType & PATHFIND_NOT_USING_PATH)
            && !(pathType & PATHFIND_INCOMPLETE)
            && !(pathType & PATHFIND_SHORTCUT)
            && !(pathType & PATHFIND_FARFROMPOLY);
        if (!validApproachPath)
        {
            declineReason = "declined_no_los_or_valid_path";
            return false;
        }
    }

    if (submittedCastPending)
    {
        bool const submittedIdentityCurrent = targetState.NativeResurrectionPendingUntilMs > nowMs
            && targetState.NativeResurrectionCasterGuid == owner->GetGUID()
            && targetState.NativeResurrectionSpellId == spellId;
        bool const exactCastInProgress = owner->FindCurrentSpellBySpellId(spellId) != nullptr;
        bool const exactNativeRequestPending = target->IsResurrectRequestedBy(owner->GetGUID());
        if (!submittedIdentityCurrent || (!exactCastInProgress && !exactNativeRequestPending))
        {
            declineReason = "declined_submitted_cast_identity_drift";
            return false;
        }
        if (owner->HasUnitState(UNIT_STATE_CASTING) && !exactCastInProgress)
        {
            declineReason = "declined_owner_casting_other_spell";
            return false;
        }

        // A cast already accepted by the native spell system owns its normal
        // cast/GCD/cooldown lifecycle.  Requiring those pre-submit resources
        // again would invalidate every legitimate in-flight resurrection.
        return true;
    }

    if (!owner->GetSpellHistory()->IsReady(spellInfo))
    {
        declineReason = "declined_combat_res_cooldown";
        return false;
    }
    if (!HasPowerForSpell(owner, spellInfo))
    {
        declineReason = "declined_insufficient_power";
        return false;
    }
    if (target->IsResurrectRequested()
        || targetState.NativeResurrectionPendingUntilMs > nowMs)
    {
        declineReason = "declined_approach_reservation_state_drift";
        return false;
    }

    // The planner still requires an idle owner before it creates a promise.
    // Once the typed movement-only approach has actually been selected, a
    // short, matching acceptance receipt permits normal damage casts/GCDs to
    // coexist with that movement.  It cannot hold a dead target indefinitely:
    // the receipt is refreshed only when arbitration accepts the exact current
    // approach, and both it and the reservation remain bounded.
    bool const acceptedApproachIntentCurrent =
        targetState.NativeBattleResApproachIntentDecisionAtMs
            == targetState.NativeBattleResDecisionAtMs
        && targetState.NativeBattleResApproachIntentAcceptedUntilMs > nowMs;
    if (owner->HasUnitState(UNIT_STATE_CASTING)
        && !acceptedApproachIntentCurrent)
    {
        declineReason = "declined_owner_casting";
        return false;
    }
    if (owner->GetSpellHistory()->HasGlobalCooldown(spellInfo)
        && !acceptedApproachIntentCurrent)
    {
        declineReason = "declined_owner_global_cooldown";
        return false;
    }
    return true;
}

void BotWorldPopulationMgr::PublishNativeBattleResDecision(WorldBotState& targetState,
    Player* target, std::string const& decision, ObjectGuid ownerGuid, uint32 spellId,
    uint64 nowMs, uint64 decisionUntilMs)
{
    bool const declined = decision.rfind("declined_", 0) == 0;
    ObjectGuid const observedOwnerGuid = ownerGuid;
    uint32 const observedSpellId = spellId;
    if (declined)
    {
        ownerGuid.Clear();
        spellId = 0;
        targetState.NativeResurrectionPendingUntilMs = 0;
        targetState.NativeResurrectionCasterGuid.Clear();
        targetState.NativeResurrectionSpellId = 0;
    }

    bool const changed = targetState.NativeBattleResDecision != decision
        || targetState.NativeBattleResOwnerGuid != ownerGuid
        || targetState.NativeBattleResSpellId != spellId;
    if (!changed)
        return;

    targetState.NativeBattleResApproachIntentDecisionAtMs = 0;
    targetState.NativeBattleResApproachIntentAcceptedUntilMs = 0;
    targetState.NativeBattleResDecision = decision;
    targetState.NativeBattleResOwnerGuid = ownerGuid;
    targetState.NativeBattleResSpellId = spellId;
    targetState.NativeBattleResDecisionAtMs = nowMs;
    targetState.NativeBattleResDecisionUntilMs = decisionUntilMs;
    if (!target)
        return;

    std::string raw = BuildRawJson(target, nullptr);
    std::string semantic = BuildSemanticJson(target, nullptr, "battle_res_decision");
    RecordEvent(targetState, target, "battle_res_decision", nullptr, decision.c_str(),
        raw.c_str(), semantic.c_str(), 0.0f, observedOwnerGuid.GetCounter(), observedSpellId);
}

void BotWorldPopulationMgr::ReconcileNativeBattleResDecisions(uint64 nowMs)
{
    if (!Cohort().Config.ValidationRouteEnable || Party().Bots.empty())
        return;

    struct Member
    {
        WorldBotState* State = nullptr;
        Player* Bot = nullptr;
    };
    std::vector<Member> living;
    std::vector<Member> dead;
    bool groupCombatActive = false;
    for (WorldBotState& state : Party().Bots)
    {
        Player* bot = GetLoadedBot(state);
        if (!bot || !bot->IsInWorld() || !state.ValidationCohortLocked
            || !bot->GetGroup() || !IsValidationCohortMemberInOriginalInstance(state, bot))
            continue;
        if (bot->IsAlive())
        {
            living.push_back({ &state, bot });
            groupCombatActive = groupCombatActive || bot->IsInCombat()
                || bot->GetVictim() || !bot->getAttackers().empty();
        }
        else
            dead.push_back({ &state, bot });
    }
    if (dead.empty())
        return;

    if (!groupCombatActive)
        if (Player* observer = living.empty() ? nullptr : living.front().Bot)
            if (InstanceScript* instance = observer->GetInstanceScript())
                groupCombatActive = instance->IsEncounterInProgress();

    RaidRuntime const& raid = Cohort().Raid;
    // A cleared trash pack is no longer an encounter, but a live druid may
    // still submit its ordinary native Rebirth to an unreleased corpse.  Keep
    // this exception bound to the current observed route/attempt/node and to
    // a real hostile inactivity/reset edge.  CurrentCombatResOwnerUsable()
    // still enforces spell, cooldown, power, range, LOS, and path validity.
    bool const nativeTrashRecoveryWindow = Cohort().Config.ValidationRouteKind == "trash"
        && Cohort().Config.ValidationRouteBossRecovery
            != ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly
        && raid.NativeHostileObservationAttemptId == raid.AttemptId
        && raid.NativeHostileObservationRouteGeneration == Party().ValidationRouteGeneration
        && raid.NativeHostileObservationNodeId == Cohort().Config.ValidationRouteNodeId
        && raid.NativeHostileInactivityObserved
        && !raid.NativeHostileActivityActive
        && raid.NativeHostileResetGeneration > raid.NativeHostileResetGenerationAtWipe;

    static constexpr uint64 CombatResReservationLifetimeMs = 8000;
    static constexpr uint64 CombatResDeclineObservationMs = 5000;
    auto applyDecision = [&](Member const& member, char const* decision,
        ObjectGuid ownerGuid = ObjectGuid::Empty, uint32 spellId = 0,
        uint64 decisionUntilMs = 0)
    {
        if (!decisionUntilMs)
            decisionUntilMs = nowMs + CombatResDeclineObservationMs;
        PublishNativeBattleResDecision(*member.State, member.Bot, decision,
            ownerGuid, spellId, nowMs, decisionUntilMs);
    };

    // A reservation is a continuously reconciled promise, not a timer-only
    // latch.  Any owner, target, spell, path, power, cooldown, or cast-state
    // drift becomes an explicit decline before the dead member is updated.
    for (Member const& member : dead)
        if (member.State->NativeBattleResDecision == "reserved_approach"
            || member.State->NativeBattleResDecision == "reserved_cast_submitted")
        {
            std::string declineReason;
            if (!CurrentCombatResOwnerUsable(*member.State, member.Bot, nowMs, declineReason))
                applyDecision(member, declineReason.c_str(),
                    member.State->NativeBattleResOwnerGuid,
                    member.State->NativeBattleResSpellId);
        }

    if (!groupCombatActive && !nativeTrashRecoveryWindow)
    {
        for (Member const& member : dead)
            if (member.State->NativeBattleResDecision != "reserved_cast_submitted")
                applyDecision(member, "declined_out_of_combat");
        return;
    }

    std::vector<Member> eligibleDead;
    eligibleDead.reserve(dead.size());
    for (Member const& member : dead)
    {
        if (member.State->NativeBattleResDecision == "reserved_approach"
            || member.State->NativeBattleResDecision == "reserved_cast_submitted")
            continue;

        bool const terminalDecisionHeld = member.State->NativeBattleResDecisionUntilMs > nowMs
            && member.State->NativeBattleResDecision.rfind("declined_", 0) == 0;
        if (terminalDecisionHeld)
            continue;

        // A combat resurrection targets the native, unreleased dead Player.
        // TrinityCore creates the Corpse object only when Release Spirit is
        // accepted, so requiring a Corpse here would make pre-release combat
        // resurrection impossible.
        if (!IsNativeCombatResTarget(*member.State, member.Bot))
        {
            applyDecision(member, "declined_target_ineligible");
            continue;
        }
        eligibleDead.push_back(member);
    }

    if (eligibleDead.empty())
        return;

    bool const bossCommitment = Cohort().Config.ValidationRouteKind == "boss";
    auto utility = [&](Member const& member) -> uint32
    {
        std::string const role = GetDungeonRole(member.Bot);
        uint32 score = role == "tank" ? 300 : role == "healer" ? 250 : 100;
        if (bossCommitment)
            score += 60;
        if (living.size() <= 2)
            score += 100;
        return score;
    };
    auto selected = std::max_element(eligibleDead.begin(), eligibleDead.end(), [&](Member const& left, Member const& right)
    {
        uint32 const leftUtility = utility(left);
        uint32 const rightUtility = utility(right);
        if (leftUtility != rightUtility)
            return leftUtility < rightUtility;
        return left.Bot->GetGUID() > right.Bot->GetGUID();
    });
    // Utility is a priority ordering, not an eligibility floor.  A DPS corpse
    // still has a valid native combat-res target in a five-player group; the
    // old 140 cutoff made every DPS death permanently unrecoverable (DPS
    // scores 100) even when a live druid owner and a valid native cast existed.
    if (selected == eligibleDead.end())
    {
        for (Member const& member : eligibleDead)
            applyDecision(member, "declined_low_recovery_utility");
        return;
    }

    struct OwnerCandidate
    {
        Member Owner;
        uint32 SpellId = 0;
        uint32 RecoveryMs = 0;
    };
    std::vector<OwnerCandidate> owners;
    for (Member const& member : living)
        for (auto const& [spellId, playerSpell] : member.Bot->GetSpellMap())
        {
            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
            if (!IsNativeCombatResSpell(spellInfo))
                continue;
            owners.push_back({ member, spellId,
                std::max(spellInfo->RecoveryTime, spellInfo->CategoryRecoveryTime) });
        }

    if (owners.empty())
    {
        for (Member const& member : eligibleDead)
            applyDecision(member, "declined_no_combat_res_spell");
        return;
    }
    std::sort(owners.begin(), owners.end(), [](OwnerCandidate const& left, OwnerCandidate const& right)
    {
        if (left.RecoveryMs != right.RecoveryMs)
            return left.RecoveryMs < right.RecoveryMs;
        if (left.Owner.Bot->GetGUID() != right.Owner.Bot->GetGUID())
            return left.Owner.Bot->GetGUID() < right.Owner.Bot->GetGUID();
        return left.SpellId < right.SpellId;
    });

    OwnerCandidate const* owner = nullptr;
    for (OwnerCandidate const& candidate : owners)
    {
        // Stage the exact bounded approach reservation so the same predicate
        // used by re-reconciliation, execution, and dead-member waiting also
        // decides whether the planner may publish it.
        std::string const previousDecision = selected->State->NativeBattleResDecision;
        ObjectGuid const previousOwner = selected->State->NativeBattleResOwnerGuid;
        uint32 const previousSpell = selected->State->NativeBattleResSpellId;
        uint64 const previousAt = selected->State->NativeBattleResDecisionAtMs;
        uint64 const previousUntil = selected->State->NativeBattleResDecisionUntilMs;
        uint64 const previousApproachDecisionAt =
            selected->State->NativeBattleResApproachIntentDecisionAtMs;
        uint64 const previousApproachAcceptedUntil =
            selected->State->NativeBattleResApproachIntentAcceptedUntilMs;
        selected->State->NativeBattleResDecision = "reserved_approach";
        selected->State->NativeBattleResOwnerGuid = candidate.Owner.Bot->GetGUID();
        selected->State->NativeBattleResSpellId = candidate.SpellId;
        selected->State->NativeBattleResDecisionAtMs = nowMs;
        selected->State->NativeBattleResDecisionUntilMs = nowMs + CombatResReservationLifetimeMs;
        // A staged planner proposal has not passed typed arbitration yet and
        // must never inherit a prior approach's transient cast/GCD tolerance.
        selected->State->NativeBattleResApproachIntentDecisionAtMs = 0;
        selected->State->NativeBattleResApproachIntentAcceptedUntilMs = 0;
        std::string declineReason;
        bool const usable = CurrentCombatResOwnerUsable(*selected->State,
            selected->Bot, nowMs, declineReason);
        selected->State->NativeBattleResDecision = previousDecision;
        selected->State->NativeBattleResOwnerGuid = previousOwner;
        selected->State->NativeBattleResSpellId = previousSpell;
        selected->State->NativeBattleResDecisionAtMs = previousAt;
        selected->State->NativeBattleResDecisionUntilMs = previousUntil;
        selected->State->NativeBattleResApproachIntentDecisionAtMs =
            previousApproachDecisionAt;
        selected->State->NativeBattleResApproachIntentAcceptedUntilMs =
            previousApproachAcceptedUntil;
        if (usable)
        {
            owner = &candidate;
            break;
        }
    }
    if (!owner)
    {
        for (Member const& member : eligibleDead)
            applyDecision(member, "declined_no_usable_combat_res");
        return;
    }

    for (Member const& member : eligibleDead)
    {
        if (member.Bot == selected->Bot)
            applyDecision(member, "reserved_approach", owner->Owner.Bot->GetGUID(), owner->SpellId,
                nowMs + CombatResReservationLifetimeMs);
        else
            applyDecision(member, "declined_lower_priority");
    }
}

std::optional<BotNativeAction::Candidate>
BotWorldPopulationMgr::BuildCombatResNativeActionCandidate(
    WorldBotState& ownerState, Player* owner, uint64 nowMs)
{
    if (!Cohort().Config.ValidationRouteEnable || !owner || !owner->IsInWorld()
        || !owner->IsAlive() || !ownerState.ValidationCohortLocked
        || Cohort().Config.ValidationRouteBossRecovery
            == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly)
        return std::nullopt;

    WorldBotState* targetState = nullptr;
    Player* target = nullptr;
    for (WorldBotState& candidate : Party().Bots)
    {
        if (candidate.NativeBattleResOwnerGuid != owner->GetGUID()
            || (candidate.NativeBattleResDecision != "reserved_approach"
                && candidate.NativeBattleResDecision != "reserved_cast_submitted"))
            continue;
        Player* candidateTarget = GetLoadedBot(candidate);
        if (!candidateTarget || (target
                && candidateTarget->GetGUID() > target->GetGUID()))
            continue;
        targetState = &candidate;
        target = candidateTarget;
    }
    if (!targetState || !target)
        return std::nullopt;

    std::string declineReason;
    if (!CurrentCombatResOwnerUsable(*targetState, target, nowMs,
            declineReason))
    {
        ObjectGuid const declinedOwner = targetState->NativeBattleResOwnerGuid;
        uint32 const declinedSpell = targetState->NativeBattleResSpellId;
        PublishNativeBattleResDecision(*targetState, target,
            declineReason.empty() ? "declined_owner_unusable" : declineReason,
            declinedOwner, declinedSpell, nowMs, nowMs + 5000);
        return std::nullopt;
    }

    BotNativeAction::Candidate candidate;
    candidate.Id.ScopeKey = Cohort().Config.ValidationRouteScenarioId + ":"
        + Cohort().Config.ValidationRouteNodeId;
    candidate.Id.Strategy = "typed_combat_res";
    candidate.Id.Actor = target->GetGUID();
    candidate.Id.EventGeneration = targetState->NativeBattleResDecisionAtMs;
    // Beat the broad legacy route adapter (Mechanic/utility 3) without ever
    // outranking a Survival hazard exit. This prevents the route candidate's
    // wide resource mask from starving a current combat-res intent.
    candidate.ActionPriority = BotActionArbitration::Priority::Mechanic;
    std::string const targetRole = GetDungeonRole(target);
    candidate.Utility = targetRole == "tank" ? 9.0f
        : targetRole == "healer" ? 8.0f : 6.0f;
    candidate.ExpiresAtMs = targetState->NativeBattleResDecisionUntilMs;

    uint32 const spellId = targetState->NativeBattleResSpellId;
    uint64 const reservationAtMs = targetState->NativeBattleResDecisionAtMs;
    uint64 const reservationUntilMs =
        targetState->NativeBattleResDecisionUntilMs;
    if (targetState->NativeBattleResDecision == "reserved_cast_submitted")
    {
        if (target->IsResurrectRequestedBy(owner->GetGUID()))
        {
            candidate.Id.Mechanic = "accept_submitted_combat_res";
            candidate.Action = BotNativeAction::CombatResAccept{
                target->GetGUID(), spellId, reservationAtMs,
                reservationUntilMs };
        }
        else
        {
            candidate.Id.Mechanic = "reconcile_submitted_combat_res_cast";
            candidate.Action = BotNativeAction::CombatResCast{
                target->GetGUID(), spellId, reservationAtMs,
                reservationUntilMs };
        }
        return candidate;
    }

    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    float const resurrectionRange = spellInfo
        ? std::max(5.0f, owner->GetSpellMaxRangeForTarget(target, spellInfo))
        : 5.0f;
    bool const inCastEnvelope = owner->IsWithinLOSInMap(target)
        && owner->IsWithinDistInMap(target, resurrectionRange);
    bool const castResourcesFree = spellInfo
        && !owner->HasUnitState(UNIT_STATE_CASTING)
        && !owner->GetSpellHistory()->HasGlobalCooldown(spellInfo);
    if (inCastEnvelope && castResourcesFree)
    {
        candidate.Id.Mechanic = "submit_combat_res_cast";
        candidate.Action = BotNativeAction::CombatResCast{
            target->GetGUID(), spellId, reservationAtMs,
            reservationUntilMs };
    }
    else
    {
        candidate.Id.Mechanic = "approach_combat_res_target";
        candidate.Action = BotNativeAction::CombatResApproach{
            target->GetGUID(), spellId, reservationAtMs,
            reservationUntilMs };
    }
    return candidate;
}
