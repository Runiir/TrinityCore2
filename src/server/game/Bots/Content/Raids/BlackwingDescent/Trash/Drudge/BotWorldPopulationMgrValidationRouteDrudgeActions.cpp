#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/BotActionArbiter.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeMovementLease.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeNativeRushState.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeObservationBacklog.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeSeed.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"

#include "Creature.h"
#include "GameTime.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <string>
#include <vector>

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
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;
using BotWorldPopulationMgrNativeHelpers::Distance2d;
void DrudgeLaneContext::HoldOffense()
{
    uint64 const ownerGuid = Bot->GetGUID().GetRawValue();
    BotRaidAreaAuthority::SetAllOffenseSuppressed(ownerGuid, true);
    BotRaidAreaAuthority::Set(ownerGuid, true);
    for (CurrentSpellTypes spellType : { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL })
        if (Spell* current = Bot->GetCurrentSpell(spellType))
            if (Unit* castTarget = current->m_targets.GetUnitTarget();
                castTarget && Bot->IsValidAttackTarget(castTarget))
                Bot->InterruptSpell(spellType, false);
    Manager.SubmitMeleeAutoAttackIntent(State,
        BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
        BotMeleeAutoAttack::Owner::Safety,
        BotActionArbitration::Priority::Terminal,
        "mechanic_all_offense_suppressed");
    if (Pet* pet = Bot->GetPet())
    {
        for (CurrentSpellTypes spellType : { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL })
            if (Spell* current = pet->GetCurrentSpell(spellType))
                if (Unit* castTarget = current->m_targets.GetUnitTarget();
                    castTarget && pet->IsValidAttackTarget(castTarget))
                    pet->InterruptSpell(spellType, false);
        pet->AttackStop();
    }
    for (Unit* controlled : Bot->m_Controlled)
        if (controlled)
        {
            for (CurrentSpellTypes spellType : { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL })
                if (Spell* current = controlled->GetCurrentSpell(spellType))
                    if (Unit* castTarget = current->m_targets.GetUnitTarget();
                        castTarget && controlled->IsValidAttackTarget(castTarget))
                        controlled->InterruptSpell(spellType, false);
            controlled->AttackStop();
        }
}

void DrudgeLaneContext::Record(Creature* source, char const* result,
    float value, uint32 value2)
{
    RecordNativeTransition(source, result, value2);
    std::string raw = Manager.BuildRawJson(Bot, source);
    std::string semantic = Manager.BuildSemanticJson(Bot, source,
        "validation_route_mechanic", &Power, Stage, Activity);
    Manager.RecordEvent(State, Bot, "validation_route_drudge_lanes", source, result,
        raw.c_str(), semantic.c_str(), value, value2,
        Manager.Cohort().Config.ValidationRouteChargeSpellId);
    Situation = "validation_route_mechanic";
    Action = result;
}

DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunFormationActions()
{
    SourceSeparation = Sources[0]->GetExactDist2d(Sources[1]);
    bool const source0Alive = Sources[0]->IsAlive();
    bool const source1Alive = Sources[1]->IsAlive();
    if (source0Alive != source1Alive)
    {
        auto& party = Manager.Party();
        if (party.ValidationRouteDrudgeDeathAttemptId != Manager.Cohort().AttemptId
            || party.ValidationRouteDrudgeDeathWipeGeneration
                != Manager.Cohort().Raid.WipeGeneration
            || party.ValidationRouteDrudgeDeathRouteGeneration
                != party.ValidationRouteGeneration)
        {
            party.ValidationRouteDrudgeDeathAttemptId = Manager.Cohort().AttemptId;
            party.ValidationRouteDrudgeDeathWipeGeneration = Manager.Cohort().Raid.WipeGeneration;
            party.ValidationRouteDrudgeDeathRouteGeneration = party.ValidationRouteGeneration;
            party.ValidationRouteDrudgeDeathSourceSpawnId = 0;
            party.ValidationRouteDrudgeDeathSourceGuid = 0;
            party.ValidationRouteDrudgeSurvivorSourceSpawnId = 0;
            party.ValidationRouteDrudgeSurvivorSourceGuid = 0;
            party.ValidationRouteDrudgeDeathEvidenceSequence = 0;
            party.ValidationRouteDrudgeRageWaitEvidenceSequence = 0;
            party.ValidationRouteDrudgeRageAuraEvidenceSequence = 0;
        }
        if (!party.ValidationRouteDrudgeDeathEvidenceSequence)
        {
            Creature* dead = source0Alive ? Sources[1] : Sources[0];
            Creature* survivor = source0Alive ? Sources[0] : Sources[1];
            party.ValidationRouteDrudgeDeathSourceSpawnId = source0Alive ? 250141 : 250140;
            party.ValidationRouteDrudgeDeathSourceGuid = dead->GetGUID().GetCounter();
            party.ValidationRouteDrudgeSurvivorSourceSpawnId = source0Alive ? 250140 : 250141;
            party.ValidationRouteDrudgeSurvivorSourceGuid = survivor->GetGUID().GetCounter();
            party.ValidationRouteDrudgeDeathEvidenceSequence = ++Manager.Cohort().Raid.EvidenceSequence;
            Record(dead, "drudge_first_source_death_observed", SourceSeparation);
        }
    }
    auto observation = std::find_if(
        Manager.Party().ValidationRouteDrudgeChargeObservations.begin(),
        Manager.Party().ValidationRouteDrudgeChargeObservations.end(),
        [this](ChargeObservation const& candidate)
        {
            return !candidate.ReseparationRecorded
                && candidate.AttemptId == Manager.Cohort().AttemptId
                && candidate.WipeGeneration == Manager.Cohort().Raid.WipeGeneration
                && candidate.RouteGeneration == Manager.Party().ValidationRouteGeneration;
        });
    Charge = observation == Manager.Party().ValidationRouteDrudgeChargeObservations.end()
        ? nullptr : &*observation;
    ChargeAwaitingLanding = Charge && !Charge->Landed;
    NativeChargePending = Charge && Charge->Landed;
    auto receiptScope = [&]()
    {
        return BotRaidDrudgeGeometry::Scope{
            Manager.Cohort().AttemptId,
            Manager.Cohort().Raid.WipeGeneration,
            Manager.Party().ValidationRouteGeneration,
            Bot->GetMapId(), Bot->GetInstanceId(),
            Sources[0]->GetGUID().GetRawValue(),
            Sources[1]->GetGUID().GetRawValue() };
    };
    auto observeReceiptProgress = [&](uint64 nowMs)
    {
        if (!Charge)
            return;
        BotRaidDrudgeGeometry::Scope const scope = receiptScope();
        MotionMaster* motion = Bot->GetMotionMaster();
        uint32 const motionType = motion
            ? uint32(motion->GetMotionSlotType(MOTION_SLOT_ACTIVE))
            : uint32(MAX_MOTION_TYPE);
        bool const pathScopeMatches = State.ActivePathAttemptId
                == Manager.Cohort().AttemptId
            && State.ActivePathWipeGeneration
                == Manager.Cohort().Raid.WipeGeneration
            && State.ActivePathRouteGeneration
                == Manager.Party().ValidationRouteGeneration
            && State.ActivePathRouteNodeId
                == Manager.Cohort().Config.ValidationRouteNodeId;
        for (BotRaidDrudgeSpacing::ReseparationReceipt& receipt :
            Charge->ReseparationReceipts)
        {
            if (receipt.Scope != scope || receipt.MemberGuid
                != Bot->GetGUID().GetCounter() || !receipt.MovementSubmitted)
                continue;
            if (!receipt.ActivePathCaptured)
            {
                receipt.ActivePathCaptured = true;
                receipt.ActivePathValid = State.ActivePathValid;
                receipt.ActivePathScopeMatches = pathScopeMatches;
                receipt.ActivePathDestinationX = State.ActivePathToX;
                receipt.ActivePathDestinationY = State.ActivePathToY;
                receipt.ActivePathDestinationZ = State.ActivePathToZ;
                receipt.NativeActiveMotionType = motionType;
            }
            if (!receipt.ProgressObserved && State.LastMovementProgressMs
                > receipt.SubmissionAtMs)
            {
                receipt.ProgressObserved = true;
                receipt.ProgressAtMs = State.LastMovementProgressMs;
                receipt.ProgressOutcome = "native_progress_observed";
            }
            float const tolerance = AssignedTank
                ? Manager.Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards
                : Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards;
            if (!receipt.ArrivalObserved
                && Bot->GetExactDist(receipt.CandidateX, receipt.CandidateY,
                    receipt.CandidateZ) <= tolerance)
            {
                receipt.ArrivalObserved = true;
                receipt.ArrivalAtMs = nowMs;
                receipt.ArrivalOutcome = "candidate_arrival_observed";
            }
        }
    };
    auto recordMovementReceipt = [&](bool moved, uint64 nowMs)
    {
        if (!Charge)
            return;
        BotRaidDrudgeGeometry::Scope const scope = receiptScope();
        BotRaidDrudgeSpacing::ReseparationReceipt* receipt =
            BotRaidDrudgeSpacing::FindSelectedReseparationReceipt(
                Charge->ReseparationReceipts, scope,
                Bot->GetGUID().GetCounter(),
                State.ValidationRouteDrudgeAnchorCandidateIndex,
                State.ValidationRouteDrudgeAnchorX,
                State.ValidationRouteDrudgeAnchorY);
        if (!receipt)
        {
            BotRaidDrudgeSpacing::PeerResult const peer =
                EvaluateRecoveryCandidateSpacing(
                    State.ValidationRouteDrudgeAnchorX,
                    State.ValidationRouteDrudgeAnchorY, AssignedTank);
            float const projection =
                (State.ValidationRouteDrudgeAnchorX - MidpointX) * AxisX
                + (State.ValidationRouteDrudgeAnchorY - MidpointY) * AxisY;
            bool const source0Safe = Distance2d(
                State.ValidationRouteDrudgeAnchorX,
                State.ValidationRouteDrudgeAnchorY,
                Sources[0]->GetPositionX(), Sources[0]->GetPositionY())
                >= Manager.Cohort().Config.ValidationRouteMinimumDistanceYards;
            bool const source1Safe = Distance2d(
                State.ValidationRouteDrudgeAnchorX,
                State.ValidationRouteDrudgeAnchorY,
                Sources[1]->GetPositionX(), Sources[1]->GetPositionY())
                >= Manager.Cohort().Config.ValidationRouteMinimumDistanceYards;
            bool const laneSafe = LaneSign * projection >= LaneSeparation * 0.25f;
            BotRaidDrudgeSpacing::ObserveReseparationCandidate(
                Charge->ReseparationReceipts, scope,
                Bot->GetGUID().GetCounter(),
                State.ValidationRouteDrudgeAnchorCandidateIndex,
                State.ValidationRouteDrudgeAnchorX,
                State.ValidationRouteDrudgeAnchorY,
                State.ValidationRouteDrudgeAnchorZ, source0Safe, source1Safe,
                laneSafe, peer.Safe,
                BotRaidDrudgeGeometry::DynamicGroupPositionSafe(
                    source0Safe, source1Safe, laneSafe, peer.Safe), true,
                "cached_selected", "none", nowMs);
            receipt = BotRaidDrudgeSpacing::FindSelectedReseparationReceipt(
                Charge->ReseparationReceipts, scope,
                Bot->GetGUID().GetCounter(),
                State.ValidationRouteDrudgeAnchorCandidateIndex,
                State.ValidationRouteDrudgeAnchorX,
                State.ValidationRouteDrudgeAnchorY);
        }
        receipt = BotRaidDrudgeSpacing::BeginReseparationSubmission(
            Charge->ReseparationReceipts, scope,
            Bot->GetGUID().GetCounter(),
            State.ValidationRouteDrudgeAnchorCandidateIndex,
            State.ValidationRouteDrudgeAnchorX,
            State.ValidationRouteDrudgeAnchorY,
            Charge->NextReseparationReceiptId, nowMs);
        if (!receipt)
            return;
        receipt->MoveAttempted = true;
        receipt->ArbitrationAccepted = moved;
        receipt->MovementSubmitted = moved;
        receipt->ArbitrationOutcome = moved ? "accepted"
            : (State.LastRecoveryResult.empty()
                ? "rejected" : State.LastRecoveryResult);
        receipt->MovementSubmissionOutcome = moved
            ? "native_movement_submitted"
            : (State.LastPathRejectReason.empty()
                ? receipt->ArbitrationOutcome : State.LastPathRejectReason);
        observeReceiptProgress(nowMs);
    };
    observeReceiptProgress(NowMs());
    if (Charge)
    {
        NativeChargeSource = NativeChargePending
            ? ObjectAccessor::GetCreature(*Bot, Charge->SourceGuid) : nullptr;
        NativeChargeTarget = NativeChargePending
            ? ObjectAccessor::GetUnit(*Bot, Charge->TargetGuid) : nullptr;
        NativeChargeContractViolation = NativeChargePending
            && (!NativeChargeSource || !NativeChargeTarget
                || Charge->SourceSpawnId == 0 || !Charge->SameMap || !Charge->SamePhase
                || !Charge->RangeValid
                || (Charge->ObservedIntervalMs > 0 && !Charge->IntervalValid));
        if (NativeChargeTarget)
            if (Player* chargePlayer = NativeChargeTarget->ToPlayer())
            {
                auto targetRoster = Manager.Cohort().Raid.RosterByGuid.find(
                    chargePlayer->GetGUID().GetCounter());
                if (targetRoster == Manager.Cohort().Raid.RosterByGuid.end())
                    NativeChargeTargetLaneViolation = true;
                else
                {
                    uint32 const targetSlot = targetRoster->second.SlotIndex + 1;
                    bool const targetInLaneA = std::find(
                        Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                        Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(),
                        targetSlot)
                        != Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
                    bool const sourceInLaneA = NativeChargeSource == Sources[0];
                    NativeChargeTargetLaneViolation = targetInLaneA == sourceInLaneA;
                    NativeChargeTargetRoleViolation = targetRoster->second.Role == "tank";
                }
            }
        NativeChargeContractViolation = NativeChargeContractViolation
            || NativeChargeTargetRoleViolation;
    }
    NativeChargeTarget = NativeChargeTarget ? NativeChargeTarget : nullptr;
    PrepullStaged = Manager.Party().ValidationRouteDrudgePrepullStaged
        && Manager.Party().ValidationRouteDrudgePrepullAttemptId == Manager.Cohort().AttemptId
        && Manager.Party().ValidationRouteDrudgePrepullWipeGeneration
            == Manager.Cohort().Raid.WipeGeneration
        && Manager.Party().ValidationRouteDrudgePrepullRouteGeneration
            == Manager.Party().ValidationRouteGeneration;
    if (!PrepullStaged && ExactRosterPrepullStaged())
    {
        auto& party = Manager.Party();
        party.ValidationRouteDrudgePrepullStaged = true;
        party.ValidationRouteDrudgePrepullAttemptId = Manager.Cohort().AttemptId;
        party.ValidationRouteDrudgePrepullWipeGeneration = Manager.Cohort().Raid.WipeGeneration;
        party.ValidationRouteDrudgePrepullRouteGeneration = party.ValidationRouteGeneration;
        PrepullStaged = true;
        Record(nullptr, "drudge_prepull_exact_roster_staged");
    }
    // A closed landed observation is durable evidence, not a new recovery
    // obligation.  Keep the recovery predicate tied to the current head so
    // the post-closure tick can validate the ordinary combat anchors instead
    // of reopening the already-finished recovery preflight.
    RecoveryFormationActive = NativeChargePending && IsRecoveryFormationActive();
    FormationRequired = AssignedTank
        ? !CachedAnchorSafe(State, Bot) : !GroupPositionSafe(Bot);
    FormationRequiredMutable = FormationRequired;
    if (!AssignedTank && !FormationRequiredMutable && !AnchorCacheMatchesGeneration())
        if (SelectPathableDrudgeAnchor(false))
            FormationRequiredMutable = !GroupPositionSafe(Bot);
    PairTooClose = Sources[0]->IsAlive() && Sources[1]->IsAlive()
        && SourceSeparation < LaneSeparation;

    BotRaidDrudgeGeometry::State geometryState;
    geometryState.Identity = {
        Manager.Cohort().AttemptId, Manager.Cohort().Raid.WipeGeneration,
        Manager.Party().ValidationRouteGeneration, Bot->GetMapId(),
        Bot->GetInstanceId(), Sources[0]->GetGUID().GetRawValue(),
        Sources[1]->GetGUID().GetRawValue() };
    geometryState.LastChargeSequenceObserved =
        State.LastValidationRouteDrudgeChargeGenerationObserved;
    geometryState.PriorPathProofAvailable = State.ValidationRouteDrudgeAnchorPathProven;
    BotRaidDrudgeGeometry::Input input;
    input.Identity = geometryState.Identity;
    input.ChargeSequence = Charge ? Charge->Sequence : 0;
    input.ChargePending = Charge != nullptr;
    input.ExactPrepullStaged = PrepullStaged;
    input.BothCombatTankPathsProven = ExactCombatTankPathsProven();
    input.BothCombatTankAnchorsSafe = ExactCombatTankAnchorsSafe();
    input.SourceCombatStarted = SourceCombatStarted;
    input.ChargeQueueIdle = Charge == nullptr;
    input.ChargeLanded = NativeChargePending;
    input.SourcesAlive = Sources[0]->IsAlive() && Sources[1]->IsAlive();
    input.SourcesSeparated = SourceSeparation >= LaneSeparation;
    input.SourcesOnFrozenLanes = SourceOnFrozenLane(Sources[0], 0, nullptr)
        && SourceOnFrozenLane(Sources[1], 1, nullptr);
    input.TanksOnFrozenLanes = TanksOnFrozenLanes();
    input.BoundTankSourceGeometrySafe = BoundTankSourceGeometrySafe();
    input.NativeMeleeStopBounded = LaneTank && OtherTank
        && Sources[LaneIndex]->GetMeleeRange(LaneTank)
            <= Manager.Cohort().Config.ValidationRouteSplitNativeMeleeStopYards
        && Sources[1 - LaneIndex]->GetMeleeRange(OtherTank)
            <= Manager.Cohort().Config.ValidationRouteSplitNativeMeleeStopYards;
    BotRaidDrudgeGeometry::Result const tankStage =
        BotRaidDrudgeGeometry::Advance(geometryState, input);
    State.LastValidationRouteDrudgeChargeGenerationObserved =
        tankStage.Next.LastChargeSequenceObserved;
    State.ValidationRouteDrudgeAnchorPathProven =
        tankStage.Next.PriorPathProofAvailable;
    if (tankStage.InvalidateAnchor)
    {
        State.ValidationRouteDrudgeAnchorValid = false;
        State.ValidationRouteDrudgeRecoveryAnchorReached = false;
        BotMovementArbitration::Scope const drudgeScope{
            Manager.Cohort().AttemptId,
            uint32(Manager.Cohort().Raid.WipeGeneration),
            Manager.Party().ValidationRouteGeneration,
            Bot->GetMapId(), Bot->GetInstanceId() };
        if (BotRaidDrudgeMovement::ReleaseInvalidatedMechanicLease(
                State.MovementLease, drudgeScope))
            Record(LaneSource, "drudge_rush_mechanic_lease_released",
                SourceSeparation);
    }

    auto markRecoveryAnchorReached = [&]()
    {
        if (!AssignedTank || !NativeChargePending
            || State.ValidationRouteDrudgeRecoveryAnchorReached
            || !State.ValidationRouteDrudgeRecoveryAnchorPathProven
            || !State.ValidationRouteDrudgeAnchorValid
            || !State.ValidationRouteDrudgeAnchorPathProven)
            return;
        MemberAnchor const* recovery = DeclaredRecoveryTankAnchorFor(OneBasedSlot);
        if (!recovery
            || !State.ValidationRouteDrudgeRecoveryAnchorPathProven
            || Distance2d(State.ValidationRouteDrudgeAnchorX,
                State.ValidationRouteDrudgeAnchorY,
                State.ValidationRouteDrudgeRecoveryAnchorX,
                State.ValidationRouteDrudgeRecoveryAnchorY) > 0.01f
            || std::fabs(State.ValidationRouteDrudgeAnchorZ
                - State.ValidationRouteDrudgeRecoveryAnchorZ) > 0.01f
            || Bot->GetExactDist(State.ValidationRouteDrudgeRecoveryAnchorX,
                State.ValidationRouteDrudgeRecoveryAnchorY,
                State.ValidationRouteDrudgeRecoveryAnchorZ)
                > Manager.Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards)
            return;
        State.ValidationRouteDrudgeRecoveryAnchorReached = true;
        Record(LaneSource, "drudge_tank_recovery_anchor_reached", SourceSeparation);
    };
    markRecoveryAnchorReached();
    bool const combatPathsProvenBeforeTick = PrepullStaged
        && !RecoveryFormationActive && ExactCombatTankPathsProven();
    bool const recoveryPathsProvenBeforeTick = PrepullStaged
        && RecoveryFormationActive && ExactRecoveryTankPathsProven();
    bool const recoveryAnchorsReachedBeforeTick = PrepullStaged
        && RecoveryFormationActive && RecoveryTankReturnBarrierOpen();
    bool const combatPathsProvenForDiagnostic = ExactCombatTankPathsProven();
    bool const combatAnchorsReachedForDiagnostic = PrepullStaged && NativeChargePending
        && ExactCombatTankAnchorsReached();
    bool const exactRosterReseparatedForDiagnostic = ExactRosterReSeparated();
    RecordRecoveryDiagnosticTick(NowMs(), recoveryAnchorsReachedBeforeTick, recoveryPathsProvenBeforeTick,
        combatPathsProvenForDiagnostic, combatAnchorsReachedForDiagnostic, exactRosterReseparatedForDiagnostic);
    bool const activePathsProvenBeforeTick = RecoveryFormationActive
        ? recoveryPathsProvenBeforeTick : combatPathsProvenBeforeTick;
    if (PrepullStaged && !NativeChargePending && !activePathsProvenBeforeTick)
    {
        bool due = false, pathProven = false;
        if (AssignedTank)
        {
            due = NowMs() >= State.ValidationRouteDrudgeAnchorSearchCooldownUntilMs;
            pathProven = SelectPathableDrudgeAnchor(true);
        }
        HoldOffense();
        if (SourceCombatStarted && Role == "healer"
            && Callbacks.TryGroupHeal(Bot, LaneSource, false, false))
        {
            Record(LaneSource, "drudge_anchor_preflight_support", SourceSeparation);
            Target = LaneSource;
            State.TargetGuid = LaneSource->GetGUID();
            return PhaseResult::Handled;
        }
        char const* result = AssignedTank && due && !pathProven
            ? "drudge_tank_anchor_strict_path_rejected"
            : "drudge_tank_anchor_preflight_wait";
        Record(LaneSource, result, SourceSeparation);
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        Action = result;
        return PhaseResult::Handled;
    }
    if (NativeChargePending && !recoveryAnchorsReachedBeforeTick
        && !recoveryPathsProvenBeforeTick)
    {
        bool pathProven = AssignedTank && SelectPathableDrudgeAnchor(true);
        HoldOffense();
        Record(LaneSource, pathProven ? "drudge_tank_recovery_anchor_preflight_wait"
            : "drudge_tank_recovery_anchor_strict_path_rejected", SourceSeparation);
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        return PhaseResult::Handled;
    }
    if (PrepullStaged && !NativeChargePending && ExactCombatTankAnchorsSafe()
        && !ExactLiveRecoveryTankPathsPreflighted())
    {
        bool pathProven = false;
        std::string rejection;
        if (AssignedTank)
        {
            MemberAnchor const* anchor = DeclaredRecoveryTankAnchorFor(OneBasedSlot);
            pathProven = anchor && StrictNativePath(anchor->X, anchor->Y, anchor->Z,
                true, &rejection);
            if (pathProven)
            {
                State.ValidationRouteDrudgeRecoveryAnchorPathProven = true;
                State.ValidationRouteDrudgeRecoveryAnchorX = anchor->X;
                State.ValidationRouteDrudgeRecoveryAnchorY = anchor->Y;
                State.ValidationRouteDrudgeRecoveryAnchorZ = anchor->Z;
                State.LastPathRejectReason.clear();
                State.LastRecoveryResult.clear();
            }
            else
            {
                State.ValidationRouteDrudgeRecoveryAnchorPathProven = false;
                State.LastPathRejectReason = rejection.empty()
                    ? "drudge_recovery_anchor_live_preflight_rejected" : rejection;
                State.LastRecoveryResult = State.LastPathRejectReason;
            }
        }
        HoldOffense();
        char const* result = AssignedTank && !pathProven
            ? "drudge_recovery_anchor_live_preflight_failed"
            : "drudge_recovery_anchor_live_preflight_wait";
        Record(LaneSource, result, SourceSeparation);
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        Action = result;
        return PhaseResult::Handled;
    }

    if (SourceCombatStarted && !PrepullStaged)
    {
        HoldOffense();
        Record(LaneSource, "drudge_prepull_combat_before_exact_roster_staged");
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        return PhaseResult::Handled;
    }
    bool const combatTankAnchorsReachedBeforeTick = PrepullStaged
        && NativeChargePending && ExactCombatTankAnchorsReached();
    if (AssignedTank && tankStage.NativeOwnershipAllowed
        && (!NativeChargePending
            || (recoveryAnchorsReachedBeforeTick && combatTankAnchorsReachedBeforeTick))
        && LaneSource->GetVictim() == Bot)
    {
        auto const insert = Manager.Party().ValidationRouteDrudgeOwnershipRosterGuids.insert(
            Bot->GetGUID().GetCounter());
        if (insert.second)
            Record(LaneSource, "drudge_lane_native_ownership", SourceSeparation);
    }
    if (AssignedTank && tankStage.NativeOwnershipAllowed
        && (!NativeChargePending
            || (recoveryAnchorsReachedBeforeTick && combatTankAnchorsReachedBeforeTick))
        && LaneSource->GetVictim() != Bot)
    {
        BotClassSpecActionProfile profile =
            BotClassSpecActionProfileStore::Build(Bot, "tank");
        for (BotActionCandidate const& candidate :
            BotClassSpecActionProfileStore::BuildCandidates(Bot, LaneSource, profile))
            if (candidate.Category == BotCombatActionCategory::Taunt)
            {
                if (candidate.RejectReason.empty())
                {
                    BotRaidAreaAuthority::SetAllOffenseSuppressed(
                        Bot->GetGUID().GetRawValue(), false);
                    bool const taunted = Manager.TryCastCombatSpell(
                        Bot, LaneSource, candidate.SpellId);
                    BotRaidAreaAuthority::SetAllOffenseSuppressed(
                        Bot->GetGUID().GetRawValue(), true);
                    if (taunted)
                    {
                        BotRaidAreaAuthority::Set(Bot->GetGUID().GetRawValue(), true);
                        Manager.Party().ValidationRouteDrudgeTauntRosterGuids.insert(
                            Bot->GetGUID().GetCounter());
                        Record(LaneSource, "drudge_lane_native_taunt",
                            SourceSeparation, candidate.SpellId);
                        Target = LaneSource;
                        State.TargetGuid = LaneSource->GetGUID();
                        return PhaseResult::Handled;
                    }
                }
                else if (NativeChargePending && candidate.RejectReason == "out_of_range")
                {
                    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.SpellId);
                    float const maxRange = spellInfo
                        ? Bot->GetSpellMaxRangeForTarget(LaneSource, spellInfo) : 0.0f;
                    float const distance = Bot->GetExactDist2d(LaneSource);
                    float const travel = distance - std::max(5.0f, maxRange - 1.0f);
                    if (maxRange > 5.0f && travel > 0.0f && distance > 0.001f)
                    {
                        float const recoveryX = Bot->GetPositionX()
                            + (LaneSource->GetPositionX() - Bot->GetPositionX()) * travel / distance;
                        float const recoveryY = Bot->GetPositionY()
                            + (LaneSource->GetPositionY() - Bot->GetPositionY()) * travel / distance;
                        float const recoveryZ = Bot->GetPositionZ()
                            + (LaneSource->GetPositionZ() - Bot->GetPositionZ()) * travel / distance;
                        float const projection = (recoveryX - MidpointX) * AxisX
                            + (recoveryY - MidpointY) * AxisY;
                        if (LaneSign * projection >= Manager.Cohort().Config.ValidationRouteSplitMinimumSeparationYards * 0.5f
                            && StrictTankRecoveryPath(recoveryX, recoveryY, recoveryZ)
                            && Manager.MoveBotToPoint(State, Bot, recoveryX, recoveryY,
                                recoveryZ, false,
                                BotMovementArbitration::Owner::Mechanic,
                                BotMovementArbitration::Priority::Mechanic))
                        {
                            Record(LaneSource, "drudge_lane_native_taunt_approach",
                                distance, candidate.SpellId);
                            Target = LaneSource;
                            State.TargetGuid = LaneSource->GetGUID();
                            return PhaseResult::Handled;
                        }
                    }
                }
            }
    }
    if (BotRaidDrudgeGeometry::LandedRushRecoveryComplete(
        NativeChargePending, recoveryAnchorsReachedBeforeTick,
        ExactCombatTankPathsProven(), combatTankAnchorsReachedBeforeTick,
        ExactRosterReSeparated()))
    {
        uint64 const proofAtMs = NowMs();
        BotRaidDrudgeSpacing::MarkReseparationClosure(
            Charge->ReseparationReceipts, receiptScope(), proofAtMs,
            "reseparation_closed");
        BotRaidDrudgeObservationBacklog::CloseLandedThroughProof(
            Manager.Party().ValidationRouteDrudgeChargeObservations,
            Manager.Cohort().AttemptId, Manager.Cohort().Raid.WipeGeneration,
            Manager.Party().ValidationRouteGeneration, proofAtMs,
            [this](ChargeObservation& observation)
            {
                MarkAllRosterReseparated(observation);
            });
        char const* result = NativeChargeTargetRoleViolation
            ? "drudge_native_charge_target_tank_reseparated"
            : (NativeChargeTargetLaneViolation
                ? "drudge_native_charge_target_lane_violation_reseparated"
                : (NativeChargeContractViolation
                    ? "drudge_native_charge_contract_violation_reseparated"
                    : "drudge_native_charge_reseparation_complete"));
        Record(NativeChargeSource, result, SourceSeparation,
            NativeChargeTarget ? NativeChargeTarget->GetGUID().GetCounter() : 0);
        State.LastValidationRouteDrudgeChargeGenerationHandled = Charge->Sequence;
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        return PhaseResult::Handled;
    }

    bool const recoveryNeeded = !PrepullStaged || !tankStage.TankMovementAllowed
        || !tankStage.NativeEngagementAllowed || FormationRequiredMutable
        || PairTooClose || NativeChargePending || ChargeAwaitingLanding;
    if (recoveryNeeded)
    {
        HoldOffense();
        bool moved = false;
        bool alreadySafe = AssignedTank ? CachedAnchorSafe(State, Bot)
                                        : GroupPositionSafe(Bot);
        bool const supportAvailable = tankStage.SupportAllowed && Role == "healer";
        BotRaidDrudgeGeometry::MemberRecoveryAction const recoveryAction =
            BotRaidDrudgeGeometry::SelectMemberRecoveryAction(
                NativeChargePending, alreadySafe, supportAvailable);
        auto tryFormationRecovery = [&]()
        {
            if (Bot->IsFalling() || alreadySafe)
                return;
            if (SelectPathableDrudgeAnchor(AssignedTank))
            {
                alreadySafe = AssignedTank ? CachedAnchorSafe(State, Bot)
                                            : GroupPositionSafe(Bot);
                markRecoveryAnchorReached();
                if (!alreadySafe && (!AssignedTank || !NativeChargePending
                    || StrictTankRecoveryPath(State.ValidationRouteDrudgeAnchorX,
                        State.ValidationRouteDrudgeAnchorY,
                        State.ValidationRouteDrudgeAnchorZ)))
                {
                    moved = Manager.MoveBotToPoint(State, Bot,
                        State.ValidationRouteDrudgeAnchorX,
                        State.ValidationRouteDrudgeAnchorY,
                        State.ValidationRouteDrudgeAnchorZ, false,
                        BotMovementArbitration::Owner::Mechanic,
                        BotMovementArbitration::Priority::Mechanic);
                    recordMovementReceipt(moved, NowMs());
                    if (!moved
                        && BotRaidDrudgeGeometry::ShouldInvalidateAnchorAfterPathRejection(
                            State.LastPathRejectReason,
                            State.LastRecoveryResult))
                    {
                        State.ValidationRouteDrudgeAnchorValid = false;
                        State.ValidationRouteDrudgeAnchorPathProven = false;
                    }
                    if (moved && AssignedTank && NativeChargePending
                        && State.ValidationRouteDrudgeRecoveryAnchorReached)
                        Record(LaneSource,
                            "drudge_tank_combat_anchor_return_started", SourceSeparation);
                }
            }
        };
        if (recoveryAction == BotRaidDrudgeGeometry::MemberRecoveryAction::RecoverFormation)
            tryFormationRecovery();
        if (recoveryAction == BotRaidDrudgeGeometry::MemberRecoveryAction::PreferFriendlySupport
            && Callbacks.TryGroupHeal(Bot, LaneSource, false, false))
        {
            Record(LaneSource, "drudge_staging_support", SourceSeparation);
            Target = LaneSource;
            State.TargetGuid = LaneSource->GetGUID();
            return PhaseResult::Handled;
        }
        if (recoveryAction != BotRaidDrudgeGeometry::MemberRecoveryAction::RecoverFormation)
            tryFormationRecovery();
        char const* result = NativeChargePending
            ? (NativeChargeTargetRoleViolation
                ? "drudge_native_charge_target_tank_reseparate"
                : (NativeChargeTargetLaneViolation
                    ? "drudge_native_charge_target_lane_violation_reseparate"
                    : (NativeChargeContractViolation
                        ? "drudge_native_charge_contract_violation_reseparate"
                        : "drudge_native_charge_lane_reseparate")))
            : (!PrepullStaged ? "drudge_prepull_member_stage"
                : (AssignedTank ? "drudge_tank_lane_position"
                    : (alreadySafe ? "drudge_group_lane_position_already_safe"
                                   : "drudge_group_lane_position")));
        Record(LaneSource, result, SourceSeparation,
            NativeChargeTarget ? NativeChargeTarget->GetGUID().GetCounter() : 0);
        Target = LaneSource;
        State.TargetGuid = LaneSource ? LaneSource->GetGUID() : ObjectGuid::Empty;
        if (!moved && !alreadySafe)
            Action = State.LastPathRejectReason.empty()
                ? "drudge_lane_native_path_rejected" : State.LastPathRejectReason;
        return PhaseResult::Handled;
    }
    if (NativeChargePending)
    {
        HoldOffense();
        Record(NativeChargeSource, "drudge_native_charge_reseparation_wait",
            SourceSeparation, NativeChargeTarget ? NativeChargeTarget->GetGUID().GetCounter() : 0);
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        return PhaseResult::Handled;
    }
    if (Role == "healer")
    {
        if (Callbacks.TryGroupHeal(Bot, LaneSource, true, false))
            return PhaseResult::Handled;
        HoldOffense();
        Record(LaneSource, "drudge_lane_healer_hold", SourceSeparation);
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        return PhaseResult::Handled;
    }
    return PhaseResult::Continue;
}

DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunThreatAndEvidenceActions()
{
    if (!OtherSource->IsAlive())
    {
        auto& party = Manager.Party();
        if (party.ValidationRouteDrudgeDeathEvidenceSequence
            && !party.ValidationRouteDrudgeRageWaitEvidenceSequence
            && LaneSource->GetGUID().GetCounter()
                == party.ValidationRouteDrudgeSurvivorSourceGuid)
            party.ValidationRouteDrudgeRageWaitEvidenceSequence =
                ++Manager.Cohort().Raid.EvidenceSequence;
        if (!LaneSource->HasAura(Manager.Cohort().Config.ValidationRouteVengefulRageSpellId))
        {
            HoldOffense();
            Record(LaneSource, "drudge_wait_native_vengeful_rage", SourceSeparation);
            Target = LaneSource;
            State.TargetGuid = LaneSource->GetGUID();
            return PhaseResult::Handled;
        }
        if (party.ValidationRouteDrudgeDeathEvidenceSequence
            && party.ValidationRouteDrudgeRageWaitEvidenceSequence
            && !party.ValidationRouteDrudgeRageAuraEvidenceSequence
            && LaneSource->GetGUID().GetCounter()
                == party.ValidationRouteDrudgeSurvivorSourceGuid)
        {
            party.ValidationRouteDrudgeRageAuraEvidenceSequence =
                ++Manager.Cohort().Raid.EvidenceSequence;
            Record(LaneSource, "drudge_native_vengeful_rage_observed", SourceSeparation);
        }
    }
    bool const laneOwnershipSafe = LaneSource->IsAlive()
        && LaneSource->GetVictim() == LaneTank
        && (!OtherSource->IsAlive() || OtherSource->GetVictim() == OtherTank);
    if (!laneOwnershipSafe)
    {
        HoldOffense();
        Record(LaneSource, "drudge_lane_wait_lane_ownership", SourceSeparation);
        Target = LaneSource;
        State.TargetGuid = LaneSource ? LaneSource->GetGUID() : ObjectGuid::Empty;
        return PhaseResult::Handled;
    }

    if (RunDrudgeSeedCoordinator() == PhaseResult::Handled)
        return PhaseResult::Handled;

    auto rosterMemberForSlot = [this](uint32 slot) -> Player*
    {
        for (auto const& [guid, roster] : Manager.Cohort().Raid.RosterByGuid)
            if (roster.Active && roster.LeaseOwned && roster.SlotIndex + 1 == slot)
                for (WorldBotState const& memberState : Manager.Party().Bots)
                    if (memberState.Guid.GetCounter() == guid)
                        return Manager.GetLoadedBot(memberState);
        return nullptr;
    };
    auto rushReadiness = [&](uint32 sourceIndex)
    {
        BotRaidDrudgeNativeRush::SourceInput input;
        if (sourceIndex >= Sources.size()
            || Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.size() != 2
            || Manager.Cohort().Config.ValidationRouteSplitSeedRosterSlots.size() != 2)
            return BotRaidDrudgeNativeRush::Evaluate(input);
        Creature* source = Sources[sourceIndex];
        Player* tank = rosterMemberForSlot(
            Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots[sourceIndex]);
        Player* seed = rosterMemberForSlot(
            Manager.Cohort().Config.ValidationRouteSplitSeedRosterSlots[sourceIndex]);
        if (!source || !source->IsAlive() || !tank || !tank->IsAlive()
            || !seed || !seed->IsAlive() || source->GetMap() != tank->GetMap()
            || source->GetMap() != seed->GetMap())
            return BotRaidDrudgeNativeRush::Evaluate(input);
        input.ExactTankVictim = source->GetVictim() == tank;
        input.TankThreat = source->GetThreatManager().GetThreat(tank, true);
        float farthest = -1.0f, second = -1.0f;
        for (auto const* reference : source->GetThreatManager().GetUnsortedThreatList())
        {
            Unit* candidate = reference ? reference->GetVictim() : nullptr;
            if (!candidate)
                continue;
            if (candidate != tank && reference->IsAvailable() && candidate->IsAlive()
                && source->IsInMap(candidate) && source->IsInPhase(candidate))
                input.HighestOtherThreat = std::max(input.HighestOtherThreat,
                    reference->GetThreat());
            if (!candidate->ToPlayer() || !reference->IsAvailable()
                || !source->IsWithinLOSInMap(candidate)
                || !source->IsWithinCombatRange(candidate,
                    Manager.Cohort().Config.ValidationRouteChargeRangeYards))
                continue;
            float const distance = source->GetExactDist(candidate);
            if (candidate == seed)
            {
                input.IntendedSeedPresent = true;
                input.SeedDistance = distance;
            }
            if (distance > farthest)
            {
                second = farthest;
                farthest = distance;
                input.FarthestGuid = candidate->GetGUID().GetCounter();
            }
            else if (distance > second)
                second = distance;
        }
        input.FarthestIsIntendedSeed = input.FarthestGuid == (seed
            ? seed->GetGUID().GetCounter() : 0);
        input.SecondFarthestDistance = std::max(0.0f, second);
        input.ThreatHeadroomMultiplier =
            Manager.Cohort().Config.ValidationRouteSplitTankThreatHeadroomMultiplier;
        input.FarthestDistanceMargin = second < 0.0f ? 0.0f
            : 2.0f * Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards;
        return BotRaidDrudgeNativeRush::Evaluate(input);
    };
    auto const laneReadiness = rushReadiness(LaneIndex);
    auto const otherReadiness = rushReadiness(1 - LaneIndex);
    bool const currentScopeHasNativeRush = std::any_of(
        Manager.Party().ValidationRouteDrudgeChargeObservations.begin(),
        Manager.Party().ValidationRouteDrudgeChargeObservations.end(),
        [this](ChargeObservation const& candidate)
        {
            return candidate.AttemptId == Manager.Cohort().AttemptId
                && candidate.WipeGeneration == Manager.Cohort().Raid.WipeGeneration
                && candidate.RouteGeneration == Manager.Party().ValidationRouteGeneration;
        });
    bool const nativeRushAuthorityReady =
        BotRaidDrudgeNativeRush::AuthorityReady(
            currentScopeHasNativeRush, laneReadiness)
        && BotRaidDrudgeNativeRush::AuthorityReady(
            currentScopeHasNativeRush, otherReadiness);
    if (Sources[0]->IsAlive() && Sources[1]->IsAlive()
        && Manager.Party().ValidationRouteDrudgeThreatSeedComplete
        && (!currentScopeHasNativeRush || !nativeRushAuthorityReady))
    {
        bool built = false;
        if (AssignedTank && LaneSource->GetVictim() == Bot
            && BotRaidDrudgeNativeRush::ShouldBuildTankThreat(
                currentScopeHasNativeRush, laneReadiness))
        {
            BotRaidAreaAuthority::SetAllOffenseSuppressed(Bot->GetGUID().GetRawValue(), false);
            BotRaidAreaAuthority::Set(Bot->GetGUID().GetRawValue(), true);
            ResolvedCombatAction tankAction = Manager.ResolveProfileCombatAction(
                Bot, LaneSource, 1, false, 0, false, false, true, false, true);
            BotActionResult const tankResult = Manager.ExecuteProfileCombatAction(
                &State, Bot, LaneSource, &tankAction, 1, false, 0, false, false, true, false, true);
            built = tankResult == BotActionResult::Ok && tankAction.Valid
                && tankAction.Type == "cast" && tankAction.SpellId
                && tankAction.TargetGuid == LaneSource->GetGUID();
            BotRaidAreaAuthority::SetAllOffenseSuppressed(Bot->GetGUID().GetRawValue(), true);
            BotRaidAreaAuthority::Set(Bot->GetGUID().GetRawValue(), true);
            if (built)
                Record(LaneSource, currentScopeHasNativeRush
                    ? "drudge_native_tank_threat_build" : "drudge_native_tank_threat_sustain",
                    laneReadiness.TankThreat, tankAction.SpellId);
        }
        if (built)
        {
            Target = LaneSource;
            State.TargetGuid = LaneSource->GetGUID();
            return PhaseResult::Handled;
        }
        HoldOffense();
        char const* result = nativeRushAuthorityReady ? "drudge_pre_first_rush_ready_hold"
            : (!laneReadiness.ExactTankVictim ? "drudge_native_tank_ownership_wait"
                : (!laneReadiness.TankThreatSecure ? "drudge_native_tank_threat_wait"
                    : "drudge_native_farthest_seed_wait"));
        Record(LaneSource, result, laneReadiness.SeedDistance, laneReadiness.FarthestGuid);
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        return PhaseResult::Handled;
    }

    if (Sources[0]->IsAlive() && Sources[1]->IsAlive()
        && !ExactRosterReSeparated())
    {
        HoldOffense();
        Record(LaneSource, "drudge_lane_profile_hold_contract_unsafe", SourceSeparation);
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        return PhaseResult::Handled;
    }
    if (Sources[0]->IsAlive() && Sources[1]->IsAlive() && AssignedTank)
    {
        auto& party = Manager.Party();
        if (party.ValidationRouteDrudgeHealthSyncEvidenceAttemptId
                != Manager.Cohort().AttemptId
            || party.ValidationRouteDrudgeHealthSyncEvidenceWipeGeneration
                != Manager.Cohort().Raid.WipeGeneration
            || party.ValidationRouteDrudgeHealthSyncEvidenceRouteGeneration
                != party.ValidationRouteGeneration)
        {
            party.ValidationRouteDrudgeHealthSyncRosterGuids.clear();
            party.ValidationRouteDrudgeHealthSyncEvaluatedRosterGuids.clear();
            party.ValidationRouteDrudgeHealthSyncEvidenceAttemptId = Manager.Cohort().AttemptId;
            party.ValidationRouteDrudgeHealthSyncEvidenceWipeGeneration = Manager.Cohort().Raid.WipeGeneration;
            party.ValidationRouteDrudgeHealthSyncEvidenceRouteGeneration = party.ValidationRouteGeneration;
        }
        party.ValidationRouteDrudgeHealthSyncEvaluatedRosterGuids.insert(
            Bot->GetGUID().GetCounter());
        if (UnitHealthPct(LaneSource) < UnitHealthPct(OtherSource))
        {
            party.ValidationRouteDrudgeHealthSyncRosterGuids.insert(
                Bot->GetGUID().GetCounter());
            party.ValidationRouteDrudgeHealthSyncHoldSourceSpawnId =
                LaneSource == Sources[0] ? 250140 : 250141;
            party.ValidationRouteDrudgeHealthSyncHoldTankGuid = LaneTank
                ? LaneTank->GetGUID().GetCounter() : 0;
            party.ValidationRouteDrudgeHealthSyncHoldLowerPct = UnitHealthPct(LaneSource);
            party.ValidationRouteDrudgeHealthSyncHoldPeerPct = UnitHealthPct(OtherSource);
            party.ValidationRouteDrudgeHealthSyncHoldLowerAlive = LaneSource->IsAlive();
            party.ValidationRouteDrudgeHealthSyncHoldPeerAlive = OtherSource->IsAlive();
        }
    }
    if (Sources[0]->IsAlive() && Sources[1]->IsAlive()
        && UnitHealthPct(LaneSource) < UnitHealthPct(OtherSource))
    {
        HoldOffense();
        Record(LaneSource, AssignedTank ? "drudge_tank_health_sync_hold"
            : "drudge_kill_sync_hold_lower_health_lane", SourceSeparation);
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        return PhaseResult::Handled;
    }
    if (Sources[0]->IsAlive() && Sources[1]->IsAlive() && Role != "tank")
    {
        Player* intendedSeed = rosterMemberForSlot(
            Manager.Cohort().Config.ValidationRouteSplitSeedRosterSlots[LaneIndex]);
        float const intendedDistance = intendedSeed
            ? LaneSource->GetExactDist(intendedSeed) : 0.0f;
        if (!intendedSeed || intendedSeed->GetMap() != LaneSource->GetMap()
            || intendedDistance < Bot->GetExactDist(LaneSource)
                + 2.0f * Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards)
        {
            HoldOffense();
            Record(LaneSource, "drudge_native_farthest_profile_hold",
                intendedDistance, Bot->GetGUID().GetCounter());
            Target = LaneSource;
            State.TargetGuid = LaneSource->GetGUID();
            return PhaseResult::Handled;
        }
    }
    if (Bot->GetVictim() && Bot->GetVictim() != LaneSource)
        Manager.SubmitMeleeAutoAttackIntent(State, BotMeleeAutoAttack::Kind::Suppress,
            ObjectGuid::Empty, BotMeleeAutoAttack::Owner::Threat,
            BotActionArbitration::Priority::ThreatControl, "split_lane_target_switch");
    if (Pet* pet = Bot->GetPet(); pet && pet->GetVictim() && pet->GetVictim() != LaneSource)
        pet->AttackStop();
    for (Unit* controlled : Bot->m_Controlled)
        if (controlled && controlled->GetVictim() && controlled->GetVictim() != LaneSource)
            controlled->AttackStop();
    BotRaidAreaAuthority::SetAllOffenseSuppressed(Bot->GetGUID().GetRawValue(), false);
    BotRaidAreaAuthority::Set(Bot->GetGUID().GetRawValue(), true);
    ResolvedCombatAction profileAction = Manager.ResolveProfileCombatAction(
        Bot, LaneSource, 1, false, 0, false, false, true, false, true);
    BotActionResult const result = Manager.ExecuteProfileCombatAction(&State, Bot,
        LaneSource, &profileAction, 1, false, 0, false, false, true, false, true);
    bool const valid = profileAction.Valid && profileAction.Type == "cast"
        && profileAction.SpellId && profileAction.TargetGuid == LaneSource->GetGUID();
    bool const succeeded = valid && result == BotActionResult::Ok;
    if (succeeded)
        Manager.Party().ValidationRouteDrudgeProfileActionRosterGuids.insert(
            Bot->GetGUID().GetCounter());
    Record(LaneSource, succeeded ? "drudge_lane_single_target_action"
        : "drudge_lane_single_target_hold", SourceSeparation, profileAction.SpellId);
    Target = LaneSource;
    State.TargetGuid = LaneSource->GetGUID();
    State.WasInCombat = LaneSource->IsInCombat();
    return PhaseResult::Handled;
}
}
