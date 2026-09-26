#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotValidationRouteNativeRecovery.h"
#include "Bots/BotValidationRouteRecoveryReturn.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"

#include "Player.h"

#include <cmath>
#include <string>

// Server adapter for the post-wipe return to the boss node (decisions in
// BotValidationRouteRecoveryReturn.h). The member's memory is armed when its
// release episode closes on a resurrection at an eligible node
// (PrepareBotUpdate); each decision tick then observes whether it is still
// returning. While it is, the encounter's adaptive plans yield the member to
// the route: the recovery ride (the native route runtime) and the ordinary
// route anchor walk bring it back, and the plans take over at the hand-off.
// The active route node, and whether its return is in scope: a composition
// raid row's boss node with an anchor to walk to.
BotWorldPopulationMgr::ValidationRouteManifestNode*
BotWorldPopulationMgr::BotUpdateContext::RecoveryReturnNode(bool& eligible) const
{
    BotWorldPopulationMgr& manager = Manager;
    PartyRuntime& party = manager.Party();
    CohortRuntime const& cohort = manager.Cohort();
    eligible = false;
    if (party.ValidationRouteManifestIndex >= party.ValidationRouteManifest.size())
        return nullptr;
    ValidationRouteManifestNode& node =
        party.ValidationRouteManifest[party.ValidationRouteManifestIndex];
    if (node.NodeId != cohort.Config.ValidationRouteNodeId)
        return nullptr;
    bool const anchorValid = std::isfinite(node.NavigationAnchorX)
        && std::isfinite(node.NavigationAnchorY) && std::isfinite(node.NavigationAnchorZ)
        && (node.NavigationAnchorX != 0.0f || node.NavigationAnchorY != 0.0f
            || node.NavigationAnchorZ != 0.0f);
    eligible = BotValidationRouteRecoveryReturn::Eligible(cohort.Config.ValidationRouteEnable,
        cohort.Raid.RaidInstance, node.CompositionRecovery,
        cohort.Config.ValidationRouteKind == "boss", anchorValid);
    return &node;
}

void BotWorldPopulationMgr::BotUpdateContext::ArmValidationRecoveryReturn()
{
    BotWorldPopulationMgr& manager = Manager;
    bool eligible = false;
    RecoveryReturnNode(eligible);
    if (eligible)
        BotValidationRouteRecoveryReturn::Arm(State.ValidationRecoveryReturn,
            manager.Cohort().AttemptId, manager.Party().ValidationRouteGeneration);
}

bool BotWorldPopulationMgr::BotUpdateContext::ObserveValidationRecoveryReturn()
{
    namespace Return = BotValidationRouteRecoveryReturn;
    BotWorldPopulationMgr& manager = Manager;
    bool eligible = false;
    ValidationRouteManifestNode* node = RecoveryReturnNode(eligible);
    BotValidationRouteNative::RuntimeScope const scope{ manager.Cohort().AttemptId,
        uint64(manager.Cohort().Raid.WipeGeneration),
        manager.Party().ValidationRouteGeneration };
    // Every living member's tick at the node keeps its baseline, so a wipe
    // here is told from one on an earlier node.
    bool const wipedHere = eligible && !node->RecoveryReturnBlockedBy.empty()
        && BotValidationRouteNative::WipedSinceBaseline(node->RecoveryReturnBaseline, scope);
    Return::Memory& memory = State.ValidationRecoveryReturn;
    if (!memory.Pending || !Bot)
        return false;

    Return::Input input;
    input.AttemptId = manager.Cohort().AttemptId;
    input.RouteGeneration = manager.Party().ValidationRouteGeneration;
    input.Eligible = eligible;
    input.Alive = Bot->IsAlive();
    input.InRouteInstance = node && Bot->IsInWorld() && Bot->GetMapId() == node->MapId
        && manager.IsValidationCohortMemberInOriginalInstance(State, Bot);
    input.DistanceToAnchor = node ? Bot->GetExactDist(node->NavigationAnchorX,
        node->NavigationAnchorY, node->NavigationAnchorZ) : 0.0f;
    input.Blocked = node && !node->RecoveryReturnBlockedBy.empty();
    input.WipedHere = wipedHere;
    // An engaged recovery ride holding the member at its exit for the last
    // living rider pauses the return clock (the ride's timeout bounds it).
    if (node)
        for (BotValidationRouteNative::RecoveryTransit const& transit
            : node->NativeContract.Recovery)
            input.RideHolds = input.RideHolds || BotValidationRouteNative::RecoveryRideHoldsMember(
                transit.Runtime.Started && transit.Runtime.Scope == scope, transit.Transport,
                Bot->GetPositionZ(), Bot->GetTransport() != nullptr);
    input.NowMs = DecisionNowMs;

    std::string const nodeId = node ? node->NodeId : std::string();
    bool const announced = memory.Announced;
    Return::Decision const decision = Return::Decide(memory, input);
    std::string reason;
    if (decision.Step == Return::Verdict::Returning && !announced)
    {
        memory.Announced = true;
        reason = "route_recovery_return:" + nodeId;
    }
    else if (decision.Step == Return::Verdict::Arrived)
        reason = "route_recovery_returned:" + nodeId;
    else if (decision.Step == Return::Verdict::Unreachable)
        reason = std::string(Return::UnreachablePrefix) + nodeId + ":"
            + std::to_string(Bot->GetGUID().GetCounter()) + ":" + decision.Reason
            + (input.Blocked ? ":" + node->RecoveryReturnBlockedBy : std::string());
    if (!reason.empty())
    {
        std::string const raw = manager.BuildRawJson(Bot, nullptr);
        std::string const semantic = manager.BuildSemanticJson(Bot, nullptr,
            "validation_route_manifest");
        manager.RecordEvent(State, Bot, "validation_route_recovery", nullptr,
            reason.c_str(), raw.c_str(), semantic.c_str(), input.DistanceToAnchor,
            manager.Cohort().Config.ValidationRouteTargetEntry);
    }
    // A return that cannot complete fails the attempt, typed.
    if (decision.Step == Return::Verdict::Unreachable)
        manager.FailValidationAttemptOnce(State, Bot, reason,
            manager.Party().ValidationRouteGeneration);
    return decision.Step == Return::Verdict::Returning;
}

// The boss encounter's adaptive plans do not own a returning member: for it
// the plans are as if the boss were not observed (no ownership, movement,
// action, assigned target or priority heal), so the ordinary route adapters
// and the native route runtime's recovery ride walk it back. Shared hazard
// exits and support healing still run, and the Drudge trash owner keeps its
// own typed recovery.
void BotWorldPopulationMgr::BotUpdateContext::YieldEncounterOwnershipForRecoveryReturn()
{
    BotUpdateContext& context = *this;
    context.AdaptiveMagmawOwnsNode = false;
    context.AdaptiveMagmawSuppressOffense = false;
    context.AdaptiveMagmawMovements = {};
    context.AdaptiveMagmawTransferLaneBinding.reset();
    context.AdaptiveMagmawDirectionalMobility.reset();
    context.AdaptiveMagmawInteraction.reset();
    context.AdaptiveMagmawPriorityHealTargetGuid.Clear();
    context.State.MagmawParasiteCombat = {};
    context.AdaptiveOmnotronOwnsNode = false;
    context.AdaptiveOmnotronSuppressOffense = false;
    context.AdaptiveOmnotronInterruptTargetGuid.Clear();
    context.AdaptiveOmnotronTankTargetGuid.Clear();
    context.AdaptiveOmnotronDispelTargetGuid.Clear();
    context.AdaptiveOmnotronOffenseAllowedGuids.clear();
    context.AdaptiveOmnotronMovement.reset();
    context.AdaptiveMaloriakOwnsNode = false;
    context.AdaptiveMaloriak.reset();
    context.AdaptiveMaloriakPriorityHealTargetGuid.Clear();
    context.AdaptiveChimaeronOwnsNode = false;
    context.AdaptiveChimaeronHealingDisabled = false;
    context.AdaptiveChimaeronSuppressOffense = false;
    context.AdaptiveChimaeronPriorityHealTargetGuid.Clear();
    context.AdaptiveChimaeronMovement.reset();
    context.AdaptiveChimaeronAction.reset();
    context.AdaptiveAtramedesOwnsNode = false;
    context.AdaptiveAtramedesSuppressOffense = false;
    context.AdaptiveAtramedesMovement.reset();
    context.AdaptiveAtramedesInteraction.reset();
    context.AdaptiveNefarianOwnsNode = false;
    context.AdaptiveNefarianSuppressOffense = false;
    context.AdaptiveNefarianInterruptTargetGuid.Clear();
    context.AdaptiveNefarianMovement.reset();
    context.AdaptiveNefarianActions.clear();
    // Out of combat a returning member has nothing to attack; a plan's damage
    // target must not start a pull from the edge of the room.
    if (!context.Bot->IsInCombat())
    {
        context.Target = nullptr;
        context.State.TargetGuid.Clear();
    }
}
