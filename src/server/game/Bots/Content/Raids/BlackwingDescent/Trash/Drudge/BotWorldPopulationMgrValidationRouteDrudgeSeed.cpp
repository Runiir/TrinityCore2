#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeSeed.h"

#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotActionExecutor.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotCombatActionCatalog.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeSeedApproach.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeThreatSeedState.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativePathValidation.h"

#include "Creature.h"
#include "GameTime.h"
#include "Map.h"
#include "PathGenerator.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <limits>
#include <set>
#include <string>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

}

namespace BotWorldPopulationMgrValidationRoute
{
using SeedGate = BotRaidDrudgeThreatSeed::RejectionGate;

struct DrudgeSeedCandidate
{
    Player* Bot = nullptr;
    DrudgeLaneContext::WorldBotState* State = nullptr;
    ResolvedCombatAction Action;
    uint32 MemberSlot = 0;
    float Distance = 0.0f;
    SeedGate Gate = SeedGate::CandidateUnavailable;
    std::string Reason = "candidate_unavailable";
    BotActionResult NativeResult = BotActionResult::NoAction;
    bool Available = false;
    bool ActionAttempted = false;
    bool ActionSucceeded = false;
    bool ApproachSubmitted = false;
    bool PositionSafe = false;
    bool LineOfSight = false;
};

using Context = BotWorldPopulationMgrValidationRoute::DrudgeLaneContext;
using WorldBotState = Context::WorldBotState;
using SeedCandidate = BotWorldPopulationMgrValidationRoute::DrudgeSeedCandidate;

bool IsSeedThreatCategory(BotCombatActionCategory category)
{
    return category == BotCombatActionCategory::ThreatBuild
        || category == BotCombatActionCategory::Builder
        || category == BotCombatActionCategory::Spender
        || category == BotCombatActionCategory::Dot
        || category == BotCombatActionCategory::Debuff
        || category == BotCombatActionCategory::Execute;
}

float EffectiveSeedMaxRange(Player* bot, Unit* target,
    BotActionCandidate const& candidate)
{
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.SpellId);
    if (!spellInfo)
        return 0.0f;
    float nativeRange = bot->GetSpellMaxRangeForTarget(target, spellInfo);
    if (spellInfo->RangeEntry
        && !(spellInfo->RangeEntry->Flags & SPELL_RANGE_MELEE))
        nativeRange += bot->GetCombatReach() + target->GetCombatReach();
    return candidate.Profile.MaxRange > 0.0f
        ? std::min(candidate.Profile.MaxRange, nativeRange) : nativeRange;
}

float EffectiveSeedMinRange(Player* bot, Unit* target, SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return 0.0f;
    float nativeRange = bot->GetSpellMinRangeForTarget(target, spellInfo);
    if (spellInfo->RangeEntry
        && (spellInfo->RangeEntry->Flags & SPELL_RANGE_RANGED))
        nativeRange += bot->GetMeleeRange(target);
    return nativeRange;
}

bool PlanSeedApproach(Context& context, SeedCandidate& candidate,
    Creature* source, bool laneA, float minimumDistance, float arrivalTolerance,
    float seedMaxRange, float minimumSeparation,
    float& destinationX, float& destinationY, float& destinationZ)
{
    if (!candidate.Bot || !candidate.State || !source || !candidate.Action.Valid
        || candidate.Action.MaxRange <= 0.0f || !candidate.Bot->GetMap())
        return false;
    float const laneSign = laneA ? -1.0f : 1.0f;
    BotRaidDrudgeSeedApproach::Input input;
    input.Actor = { candidate.Bot->GetPositionX(), candidate.Bot->GetPositionY(),
        candidate.Bot->GetPositionZ() };
    input.Source = { source->GetPositionX(), source->GetPositionY(),
        source->GetPositionZ() };
    input.MidpointX = context.MidpointX;
    input.MidpointY = context.MidpointY;
    input.AxisX = context.AxisX;
    input.AxisY = context.AxisY;
    input.LaneSign = laneSign;
    input.MinimumLaneProjection = context.LaneSeparation * 0.25f;
    input.MinimumSourceDistance = minimumDistance + arrivalTolerance;
    input.ActionMaxRange = std::min(candidate.Action.MaxRange, seedMaxRange);
    input.LineOfSightBlocked = !candidate.LineOfSight;
    BotRaidDrudgeSeedApproach::Result const plan =
        BotRaidDrudgeSeedApproach::Plan(input);
    if (!plan.Needed || !plan.Safe)
        return false;

    destinationZ = plan.Destination.Z;
    float const floorZ = candidate.Bot->GetMap()->GetHeight(
        candidate.Bot->GetPhaseShift(), plan.Destination.X,
        plan.Destination.Y, destinationZ + 2.0f, true, 8.0f);
    if (floorZ <= INVALID_HEIGHT || std::fabs(floorZ - destinationZ) > 4.0f)
        return false;
    destinationZ = floorZ;
    PathGenerator path(candidate.Bot);
    bool const pathOk = path.CalculatePath(plan.Destination.X,
        plan.Destination.Y, destinationZ, false);
    if (!BotWorldMovement::NativePathIsComplete(pathOk, path)
        || !BotWorldMovement::NativePathFloorsValid(candidate.Bot, path))
        return false;
    G3D::Vector3 const& actualEnd = path.GetActualEndPosition();
    if (std::hypot(actualEnd.x - plan.Destination.X,
            actualEnd.y - plan.Destination.Y) > 0.25f
        || std::fabs(actualEnd.z - destinationZ) > 1.0f)
        return false;

    Player* otherTank = candidate.Bot == context.LaneTank
        ? context.OtherTank : context.LaneTank;
    if (!otherTank)
        return false;
    std::vector<BotRaidDrudgeGeometry::Point2d> points;
    points.push_back({ candidate.Bot->GetPositionX(), candidate.Bot->GetPositionY() });
    for (G3D::Vector3 const& point : path.GetPath())
        points.push_back({ point.x, point.y });
    points.push_back({ actualEnd.x, actualEnd.y });
    float const otherProjection =
        (otherTank->GetPositionX() - context.MidpointX) * context.AxisX
        + (otherTank->GetPositionY() - context.MidpointY) * context.AxisY;
    if (!BotRaidDrudgeGeometry::RecoveryPathPreservesTankSeparation(
            points, context.MidpointX, context.MidpointY,
            context.AxisX, context.AxisY, laneSign,
            -laneSign * otherProjection,
            minimumSeparation))
        return false;
    destinationX = plan.Destination.X;
    destinationY = plan.Destination.Y;
    return true;
}

BotRaidDrudgeThreatSeed::Scope DrudgeLaneContext::CurrentDrudgeSeedScope(
    Context const& context)
{
    return {
        context.Manager.Cohort().AttemptId,
        context.Manager.Cohort().Raid.WipeGeneration,
        context.Manager.Party().ValidationRouteGeneration
    };
}

BotRaidDrudgeThreatSeed::State DrudgeLaneContext::ReadDrudgeSeedState(
    Context const& context,
    BotRaidDrudgeThreatSeed::Scope scope)
{
    auto const& party = context.Manager.Party();
    BotRaidDrudgeThreatSeed::State state;
    state.Identity = {
        party.ValidationRouteDrudgeThreatSeedAttemptId,
        party.ValidationRouteDrudgeThreatSeedWipeGeneration,
        party.ValidationRouteDrudgeThreatSeedRouteGeneration
    };
    state.Closed = party.ValidationRouteDrudgeThreatSeedClosed;
    state.Complete = party.ValidationRouteDrudgeThreatSeedComplete;
    state.Failure = party.ValidationRouteDrudgeThreatSeedFailure;
    for (auto const& evidence : party.ValidationRouteDrudgeThreatSeedEvidenceRows)
        if (evidence.ActionSucceeded && evidence.ProfileActionValid
            && evidence.AttemptId == scope.AttemptId
            && evidence.WipeGeneration == scope.WipeGeneration
            && evidence.RouteGeneration == scope.RouteGeneration
            && evidence.SourceLane < state.SeededLanes.size())
            state.SeededLanes[evidence.SourceLane] = true;
    return state;
}

void DrudgeLaneContext::ApplyDrudgeSeedState(Context& context,
    BotRaidDrudgeThreatSeed::CoordinatorResult const& result)
{
    auto& party = context.Manager.Party();
    if (result.ScopeReset)
    {
        party.ValidationRouteDrudgeThreatSeedRosterGuids.clear();
        party.ValidationRouteDrudgeThreatSeedEvidenceRows.clear();
    }
    party.ValidationRouteDrudgeThreatSeedAttemptId = result.Next.Identity.AttemptId;
    party.ValidationRouteDrudgeThreatSeedWipeGeneration = result.Next.Identity.WipeGeneration;
    party.ValidationRouteDrudgeThreatSeedRouteGeneration = result.Next.Identity.RouteGeneration;
    party.ValidationRouteDrudgeThreatSeedClosed = result.Next.Closed;
    party.ValidationRouteDrudgeThreatSeedComplete = result.Next.Complete;
    party.ValidationRouteDrudgeThreatSeedFailure = result.Next.Failure;
}

bool DrudgeLaneContext::ExactDrudgeAuthorityRoster(Context const& context)
{
    auto const& manager = context.Manager;
    std::set<uint32> authorityRosterGuids;
    bool exact = manager.Party().Bots.size() == manager.Cohort().Raid.RosterByGuid.size();
    for (WorldBotState const& memberState : manager.Party().Bots)
    {
        Player* member = manager.GetLoadedBot(memberState);
        auto roster = member ? manager.Cohort().Raid.RosterByGuid.find(
            member->GetGUID().GetCounter()) : manager.Cohort().Raid.RosterByGuid.end();
        if (!member || !member->IsInWorld() || !member->IsAlive()
            || member->GetMap() != context.Bot->GetMap()
            || roster == manager.Cohort().Raid.RosterByGuid.end()
            || !roster->second.Active || !roster->second.LeaseOwned
            || !authorityRosterGuids.insert(member->GetGUID().GetCounter()).second)
            exact = false;
    }
    return exact && authorityRosterGuids.size() == manager.Cohort().Raid.RosterByGuid.size();
}

void DrudgeLaneContext::SuppressAllDrudgeOffense(Context const& context)
{
    auto& manager = context.Manager;
    for (WorldBotState const& memberState : manager.Party().Bots)
        if (Player* member = manager.GetLoadedBot(memberState))
        {
            BotRaidAreaAuthority::SetAllOffenseSuppressed(
                member->GetGUID().GetRawValue(), true);
            BotRaidAreaAuthority::Set(member->GetGUID().GetRawValue(), true);
        }
}

SeedCandidate DrudgeLaneContext::ResolveDrudgeSeedCandidate(
    Context& context, uint32 lane,
    BotRaidDrudgeThreatSeed::State const& seedState)
{
    using namespace BotRaidDrudgeThreatSeed;
    SeedCandidate selected;
    if (lane >= context.Sources.size()
        || context.Manager.Cohort().Config.ValidationRouteSplitSeedRosterSlots.size() != 2)
    {
        selected.Gate = SeedGate::CandidateUnavailable;
        selected.Reason = "seed_slot_contract";
        return selected;
    }

    uint32 const seedSlot = context.Manager.Cohort().Config
        .ValidationRouteSplitSeedRosterSlots[lane];
    Creature* source = context.Sources[lane];
    auto& manager = context.Manager;
    for (WorldBotState& candidateState : manager.Party().Bots)
    {
        Player* candidate = manager.GetLoadedBot(candidateState);
        if (!candidate || !candidate->IsInWorld() || !candidate->IsAlive()
            || candidate->GetMap() != context.Bot->GetMap())
            continue;
        auto roster = manager.Cohort().Raid.RosterByGuid.find(
            candidate->GetGUID().GetCounter());
        if (roster == manager.Cohort().Raid.RosterByGuid.end()
            || roster->second.Role != "tank"
            || roster->second.SlotIndex + 1 != seedSlot)
            continue;

        selected.Bot = candidate;
        selected.State = &candidateState;
        selected.MemberSlot = roster->second.SlotIndex + 1;
        selected.Distance = candidate->GetExactDist(source);
        selected.PositionSafe = context.TanksOnFrozenLanes();
        if (!selected.PositionSafe)
        {
            selected.Gate = SeedGate::PositionUnsafe;
            selected.Reason = "group_position_unsafe";
            continue;
        }

        BotClassSpecActionProfile const profile =
            BotClassSpecActionProfileStore::Build(candidate, "tank");
        BotActionCandidate best;
        bool bestFound = false;
        float bestRange = 0.0f;
        uint32 bestRank = std::numeric_limits<uint32>::max();
        for (BotActionCandidate const& actionCandidate :
            BotClassSpecActionProfileStore::BuildCandidates(candidate, source, profile))
        {
            if (!IsSeedThreatCategory(actionCandidate.Category)
                || actionCandidate.TargetGuid != source->GetGUID().GetCounter()
                || (!actionCandidate.RejectReason.empty()
                    && actionCandidate.RejectReason != "out_of_range"))
                continue;
            float const maxRange = EffectiveSeedMaxRange(
                candidate, source, actionCandidate);
            float const minimumSafeRange = manager.Cohort().Config
                .ValidationRouteMinimumDistanceYards
                + manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards;
            if (maxRange <= minimumSafeRange)
                continue;
            uint32 const rank = actionCandidate.Category
                == BotCombatActionCategory::ThreatBuild ? 0 : 1;
            if (!bestFound || maxRange > bestRange
                || (maxRange == bestRange && rank < bestRank)
                || (rank == bestRank && maxRange == bestRange
                    && actionCandidate.Profile.SortOrder < best.Profile.SortOrder))
            {
                best = actionCandidate;
                bestFound = true;
                bestRange = maxRange;
                bestRank = rank;
            }
        }
        if (bestFound)
        {
            selected.Action.Valid = true;
            selected.Action.Type = "cast";
            selected.Action.SpellId = best.SpellId;
            selected.Action.TargetGuid = source->GetGUID();
            selected.Action.DebugName = BotCombatActionCatalog::ToString(best.Category);
            selected.Action.MovementDirective = best.Profile.MovementDirective;
            selected.Action.AutoAttackMode = best.Profile.AutoAttackMode;
            selected.Action.MeleeAutoAttackExternallyReconciled = true;
            selected.Action.SuppressAreaDamage = true;
            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(best.SpellId);
            selected.Action.MinRange = EffectiveSeedMinRange(
                candidate, source, spellInfo);
            selected.Action.MaxRange = bestRange;
        }
        selected.LineOfSight = candidate->IsWithinLOSInMap(source);
        if (!selected.Action.Valid || selected.Action.Type != "cast"
            || !selected.Action.SpellId)
        {
            selected.Gate = SeedGate::ProfileActionUnavailable;
            selected.Reason = "resolved_profile_action_unavailable";
            continue;
        }
        if (selected.Action.TargetGuid != source->GetGUID())
        {
            selected.Gate = SeedGate::TargetContract;
            selected.Reason = "resolved_profile_target_mismatch";
            continue;
        }
        if (selected.Action.MaxRange <= 5.0f
            || !selected.LineOfSight
            || selected.Distance > manager.Cohort().Config.ValidationRouteSplitSeedMaxRangeYards
            || (selected.Action.MinRange > 0.0f
                && selected.Distance < selected.Action.MinRange)
            || (selected.Action.MaxRange > 0.0f
                && selected.Distance > selected.Action.MaxRange))
        {
            selected.Gate = !selected.LineOfSight ? SeedGate::LineOfSight
                : SeedGate::RangeContract;
            selected.Reason = !selected.LineOfSight ? "native_line_of_sight_unavailable"
                : "native_seed_range_contract";
            auto const& config = manager.Cohort().Config;
            float destinationX = 0.0f;
            float destinationY = 0.0f;
            float destinationZ = 0.0f;
            bool const laneA = std::find(
                config.ValidationRouteSplitLaneARosterSlots.begin(),
                config.ValidationRouteSplitLaneARosterSlots.end(),
                selected.MemberSlot)
                != config.ValidationRouteSplitLaneARosterSlots.end();
            if (PlanSeedApproach(context, selected, source, laneA,
                    config.ValidationRouteMinimumDistanceYards,
                    config.ValidationRouteSplitArrivalToleranceYards,
                    config.ValidationRouteSplitSeedMaxRangeYards,
                    config.ValidationRouteSplitMinimumSeparationYards,
                    destinationX, destinationY, destinationZ)
                && manager.MoveBotToPoint(*selected.State, selected.Bot,
                    destinationX, destinationY, destinationZ, false,
                    BotMovementArbitration::Owner::Mechanic,
                    BotMovementArbitration::Priority::Mechanic))
            {
                selected.ApproachSubmitted = true;
                selected.Gate = SeedGate::MovementContract;
                selected.Reason = "native_seed_approach_submitted";
            }
            continue;
        }

        if (seedState.SeededLanes[lane]
            || manager.Party().ValidationRouteDrudgeThreatSeedRosterGuids.count(
                candidate->GetGUID().GetCounter()))
        {
            selected.Gate = SeedGate::CandidateUnavailable;
            selected.Reason = "candidate_already_seeded";
            continue;
        }
        selected.Available = true;
        selected.Gate = SeedGate::None;
        selected.Reason = "native_action_pending";
    }

    if (!selected.Bot)
    {
        selected.Gate = SeedGate::CandidateUnavailable;
        selected.Reason = "configured_seed_actor_unavailable";
    }
    return selected;
}

void DrudgeLaneContext::AppendDrudgeSeedEvidence(Context& context, uint32 lane,
    SeedCandidate const& candidate,
    BotRaidDrudgeThreatSeed::Scope scope, uint64 observedAtMs)
{
    if (lane >= context.Sources.size())
        return;
    auto& manager = context.Manager;
    auto& evidence = manager.Party().ValidationRouteDrudgeThreatSeedEvidenceRows.emplace_back();
    Creature* source = context.Sources[lane];
    evidence.Sequence = ++manager.Cohort().Raid.EvidenceSequence;
    evidence.AttemptId = scope.AttemptId;
    evidence.WipeGeneration = scope.WipeGeneration;
    evidence.RouteGeneration = scope.RouteGeneration;
    evidence.ObservedAtMs = observedAtMs;
    evidence.MemberGuid = candidate.Bot ? candidate.Bot->GetGUID().GetCounter() : 0;
    evidence.MemberSlot = candidate.MemberSlot;
    evidence.MemberLane = 1 - lane;
    evidence.SourceSpawnId = lane == 0 ? 250140 : 250141;
    evidence.SourceGuid = source->GetGUID().GetCounter();
    evidence.SourceLane = lane;
    evidence.SpellId = candidate.Action.SpellId;
    evidence.SelectedDistance = candidate.Distance;
    evidence.MinRange = candidate.Action.MinRange;
    evidence.MaxRange = candidate.Action.MaxRange;
    evidence.PositionSafe = candidate.PositionSafe;
    evidence.LineOfSight = candidate.LineOfSight;
    evidence.InRange = candidate.LineOfSight
        && candidate.Distance >= candidate.Action.MinRange
        && candidate.Distance <= candidate.Action.MaxRange;
    evidence.ProfileActionValid = candidate.Action.Valid;
    evidence.ActionSucceeded = candidate.ActionSucceeded;
    evidence.SelectedOffenseUnsuppressed = candidate.ActionAttempted;
    evidence.OtherOffenseSuppressed = true;
    evidence.ActionDebugName = candidate.Action.DebugName;
    evidence.ActionResult = candidate.Reason;
    if (candidate.ActionAttempted && !candidate.ActionSucceeded)
        evidence.ActionResult += ":" + std::string(ToString(candidate.NativeResult));
}
DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunDrudgeSeedCoordinator()
{
    Context& context = *this;
    auto& manager = context.Manager;
    auto& party = manager.Party();
    if (context.Sources.size() != 2 || !context.Sources[0] || !context.Sources[1]
        || !context.Sources[0]->IsAlive() || !context.Sources[1]->IsAlive()
        || party.ValidationRouteDrudgeThreatSeedComplete
        || party.ValidationRouteDrudgeThreatSeedClosed
        || party.ValidationRouteDrudgeThreatSeedFailure)
        return DrudgeLaneContext::PhaseResult::Continue;

    // Exactly one stable roster owner invokes the coordinator. Every other
    // lane remains held until this same route tick has evaluated both lanes.
    if (context.LaneIndex != 0
        || context.OneBasedSlot != manager.Cohort().Config
            .ValidationRouteSplitLaneTankSlots[0])
    {
        context.HoldOffense();
        context.Record(context.LaneSource,
            "drudge_pre_first_rush_seed_coordinator_wait", context.SourceSeparation);
        context.Target = context.LaneSource;
        context.State.TargetGuid = context.LaneSource->GetGUID();
        return DrudgeLaneContext::PhaseResult::Handled;
    }

    BotRaidDrudgeThreatSeed::Scope const scope = CurrentDrudgeSeedScope(*this);
    BotRaidDrudgeThreatSeed::State const seedState = ReadDrudgeSeedState(*this, scope);
    bool const bothVictimsOwned = context.LaneTank && context.OtherTank
        && context.Sources[0]->GetVictim() == (context.LaneIndex == 0
            ? context.LaneTank : context.OtherTank)
        && context.Sources[1]->GetVictim() == (context.LaneIndex == 0
            ? context.OtherTank : context.LaneTank);
    bool const frozenLanesSafe = context.SourceOnFrozenLane(
            context.Sources[0], 0, nullptr)
        && context.SourceOnFrozenLane(context.Sources[1], 1, nullptr);
    bool const chargeObserved = std::any_of(
        party.ValidationRouteDrudgeChargeObservations.begin(),
        party.ValidationRouteDrudgeChargeObservations.end(),
        [&manager](auto const& candidate)
        {
            return candidate.AttemptId == manager.Cohort().AttemptId
                && candidate.WipeGeneration == manager.Cohort().Raid.WipeGeneration
                && candidate.RouteGeneration == manager.Party().ValidationRouteGeneration;
        });
    bool const initialSeedOpportunity = (context.PrepullStaged
        || context.EarlyPullRecoveryActive)
        && !seedState.SeededLanes[0] && !seedState.SeededLanes[1]
        && !chargeObserved;

    BotRaidDrudgeThreatSeed::CoordinatorInput input;
    input.Identity = scope;
    input.PrepullStaged = context.PrepullStaged;
    input.RecoveryAuthorityReady = context.EarlyPullRecoveryActive;
    input.SourcesAlive = true;
    input.OwnershipSafe = bothVictimsOwned || initialSeedOpportunity;
    input.SeparationSafe = context.SourceSeparation >= context.LaneSeparation;
    input.FrozenLanesSafe = frozenLanesSafe;
    input.ChargeObserved = chargeObserved;
    input.InitialSeedOpportunity = initialSeedOpportunity;

    bool const setupAuthorityReady = input.PrepullStaged
        || input.RecoveryAuthorityReady;
    bool const seedGeometryReady = BotRaidDrudgeThreatSeed::InitialSeedGeometryReady(
        input.InitialSeedOpportunity, input.SeparationSafe, input.FrozenLanesSafe);
    if (!setupAuthorityReady || !input.OwnershipSafe || !seedGeometryReady
        || input.ChargeObserved)
    {
        BotRaidDrudgeThreatSeed::CoordinatorResult const transition =
            BotRaidDrudgeThreatSeed::AdvanceCoordinator(seedState, input);
        ApplyDrudgeSeedState(*this, transition);
        context.HoldOffense();
        char const* reason = !setupAuthorityReady ? "setup_authority"
            : !input.OwnershipSafe ? "tank_victim_ownership"
            : !input.SeparationSafe ? "lane_separation"
            : !input.FrozenLanesSafe ? "frozen_lane_geometry"
            : "native_charge_observed";
        std::string const result = std::string("drudge_pre_first_rush_seed_window_wait:")
            + reason;
        context.Record(context.LaneSource, result.c_str(), context.SourceSeparation);
        context.Target = context.LaneSource;
        context.State.TargetGuid = context.LaneSource->GetGUID();
        return DrudgeLaneContext::PhaseResult::Handled;
    }

    bool const exactAuthorityRoster = ExactDrudgeAuthorityRoster(*this);
    std::array<SeedCandidate, 2> candidates;
    for (uint32 lane = 0; lane < candidates.size(); ++lane)
    {
        candidates[lane] = ResolveDrudgeSeedCandidate(*this, lane, seedState);
        if (candidates[lane].ApproachSubmitted)
            context.Record(context.Sources[lane],
                "drudge_pre_first_rush_seed_approach",
                candidates[lane].Distance, candidates[lane].Action.SpellId);
    }

    for (uint32 lane = 0; lane < candidates.size(); ++lane)
        if (!exactAuthorityRoster)
        {
            candidates[lane].Gate = SeedGate::AuthorityRoster;
            candidates[lane].Reason = "exact_authority_roster_incomplete";
            candidates[lane].Available = false;
        }

    std::array<bool, 2> candidateAvailability;
    for (uint32 lane = 0; lane < candidateAvailability.size(); ++lane)
        candidateAvailability[lane] = candidates[lane].Available;
    bool const allPendingCandidatesReady = exactAuthorityRoster
        && BotRaidDrudgeThreatSeed::AllPendingLanesReady(
            seedState, candidateAvailability);
    if (!allPendingCandidatesReady)
        for (uint32 lane = 0; lane < candidates.size(); ++lane)
            if (!seedState.SeededLanes[lane] && candidates[lane].Available)
            {
                candidates[lane].Gate = SeedGate::PendingLaneBarrier;
                candidates[lane].Reason = "pending_lane_barrier";
            }

    SuppressAllDrudgeOffense(*this);
    if (allPendingCandidatesReady)
        for (uint32 lane = 0; lane < candidates.size(); ++lane)
            if (!seedState.SeededLanes[lane] && candidates[lane].Available
                && candidates[lane].Bot
                && candidates[lane].State)
            {
                uint64 const guid = candidates[lane].Bot->GetGUID().GetRawValue();
                BotRaidAreaAuthority::SetAllOffenseSuppressed(guid, false);
                BotRaidAreaAuthority::Set(guid, true);
                candidates[lane].ActionAttempted = true;
                BotActionExecutor executor;
                candidates[lane].NativeResult = executor.ExecuteCombat(
                    candidates[lane].Bot, candidates[lane].Bot,
                    candidates[lane].Action);
                candidates[lane].ActionSucceeded =
                    candidates[lane].NativeResult == BotActionResult::Ok
                    && candidates[lane].Action.Valid
                    && candidates[lane].Action.Type == "cast"
                    && candidates[lane].Action.SpellId
                    && candidates[lane].Action.TargetGuid
                        == context.Sources[lane]->GetGUID();
                if (!candidates[lane].ActionSucceeded)
                {
                    candidates[lane].Gate = SeedGate::NativeAction;
                    candidates[lane].Reason = "native_action_rejected";
                }
                else
                    candidates[lane].Reason = "native_action_ok";
                BotRaidAreaAuthority::SetAllOffenseSuppressed(guid, true);
                BotRaidAreaAuthority::Set(guid, true);
            }

    for (uint32 lane = 0; lane < candidates.size(); ++lane)
    {
        input.Lanes[lane].CandidateAvailable = exactAuthorityRoster
            ? candidates[lane].Available : true;
        input.Lanes[lane].ActionAttempted = candidates[lane].ActionAttempted;
        input.Lanes[lane].ActionSucceeded = candidates[lane].ActionSucceeded;
        input.Lanes[lane].AuthoritySafe = exactAuthorityRoster;
        input.Lanes[lane].Rejection = candidates[lane].Gate;
    }
    BotRaidDrudgeThreatSeed::CoordinatorResult const transition =
        BotRaidDrudgeThreatSeed::AdvanceCoordinator(seedState, input);
    ApplyDrudgeSeedState(*this, transition);
    uint64 const observedAtMs = NowMs();
    for (uint32 lane = 0; lane < candidates.size(); ++lane)
    {
        if (candidates[lane].ActionSucceeded)
            party.ValidationRouteDrudgeThreatSeedRosterGuids.insert(
                candidates[lane].Bot->GetGUID().GetCounter());
        if (!seedState.SeededLanes[lane])
            AppendDrudgeSeedEvidence(*this, lane, candidates[lane], scope, observedAtMs);
        if (candidates[lane].ActionSucceeded)
            context.Record(context.Sources[lane],
                "drudge_pre_first_rush_threat_seed", context.SourceSeparation, lane);
        else
        {
            std::string const result = std::string("drudge_pre_first_rush_seed_rejected:")
                + candidates[lane].Reason;
            context.Record(context.Sources[lane], result.c_str(),
                context.SourceSeparation, lane);
        }
    }
    context.Target = context.LaneSource;
    context.State.TargetGuid = context.LaneSource->GetGUID();
    return DrudgeLaneContext::PhaseResult::Handled;
}

DrudgeLaneContext::PhaseResult RunDrudgeSeedCoordinator(DrudgeLaneContext& context)
{
    return context.RunDrudgeSeedCoordinator();
}
}
