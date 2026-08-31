from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
DIAGNOSTICS = BOT_DIR / "BotWorldPopulationMgrMovementPlannerDiagnostics.cpp"
PROGRESS_DIAGNOSTICS = (
    BOT_DIR / "BotWorldPopulationMgrMovementProgressDiagnostics.cpp"
)
RETENTION_DIAGNOSTICS = (
    BOT_DIR / "BotWorldPopulationMgrMovementReceiptRetention.cpp"
)
EXECUTOR = BOT_DIR / "BotWorldPopulationMgrMovementExecutor.cpp"
ROUTE_MOVEMENT = BOT_DIR / "BotWorldPopulationMgrValidationRouteMovementCheck.cpp"


def test_receiptless_rejection_preserves_foreign_movement_state(tmp_path: Path) -> None:
    source = tmp_path / "movement_pre_admission_rejection_state.cpp"
    binary = tmp_path / "movement_pre_admission_rejection_state"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrBotState.h"
#include "Bots/BotWorldPopulationMgrMovement.h"
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"

#include <cassert>
#include <string>

using BotWorldPopulationMgrBotState::WorldBotState;
using namespace BotWorldPopulationMgrBotState::MovementRejectionIsolation;

int main()
{
    using BotMovementArbitration::Owner;
    using BotMovementArbitration::Priority;

    BotWorldMovement::Intent rejectedHazard;
    rejectedHazard.X = -326.503906f;
    rejectedHazard.Y = -84.8530731f;
    rejectedHazard.Z = 214.090668f;
    rejectedHazard.Owner = Owner::Hazard;
    rejectedHazard.Priority = Priority::Hazard;

    BotWorldMovement::MovementPlannerDiagnosticSidecar diagnostics;
    // This is the production executor's typed observation boundary from the
    // retained trace. It remains independent of control-state ownership.
    diagnostics.FinalizeExecutor(30008, 669, rejectedHazard,
        "future_pack_destination", "rejected",
        "route_destination_future_pack_unsafe", 0);

    // Recorded owner collision: a receiptless adaptive Hazard proposal must
    // not invalidate the already-admitted Route path, even after its short
    // arbitration lease expired.
    WorldBotState activeRoute;
    activeRoute.ActivePathValid = true;
    activeRoute.ActivePathSegmentValid = true;
    activeRoute.ActivePathTraversalMode = "native_long_path";
    activeRoute.ActivePathToX = -333.0f;
    activeRoute.ActivePathToY = -99.0f;
    activeRoute.ActivePathToZ = 214.154007f;
    activeRoute.MovementLease.MovementOwner = Owner::Route;
    activeRoute.MovementLease.MovementPriority = Priority::Route;
    activeRoute.MovementLease.ExpiresAtMs = 900;
    activeRoute.LastPathRejectReason = "route_owner_previous_reason";
    activeRoute.LastNoProgressReason = "route_owner_previous_progress";
    activeRoute.LastRecoveryResult = "native_movement_retained";
    activeRoute.LastPathChangeMs = 700;

    assert(BotWorldPopulationMgrBotState::
        ApplyPreAdmissionMovementPathRejection(
            activeRoute, rejectedHazard.Owner,
            "route_destination_future_pack_unsafe", 1000, false)
        == Disposition::ObserveOnlyPreserveExistingOwner);
    assert(activeRoute.ActivePathValid);
    assert(activeRoute.ActivePathSegmentValid);
    assert(activeRoute.ActivePathTraversalMode == "native_long_path");
    assert(activeRoute.MovementLease.MovementOwner == Owner::Route);
    assert(activeRoute.LastPathRejectReason == "route_owner_previous_reason");
    assert(activeRoute.LastNoProgressReason
        == "route_owner_previous_progress");
    assert(activeRoute.LastRecoveryResult == "native_movement_retained");
    assert(activeRoute.LastPathChangeMs == 700);

    BotWorldMovement::MovementPlannerObservation observed =
        diagnostics.Latest(30008);
    assert(observed.Available);
    assert(observed.MovementOwner == Owner::Hazard);
    assert(observed.Gate == "future_pack_destination");
    assert(observed.Result == "rejected");
    assert(observed.Reason == "route_destination_future_pack_unsafe");
    assert(observed.LaunchReceipt.Id == 0);
    std::string const observedJson =
        BotWorldMovement::MovementPlannerObservationJson(observed);
    assert(observedJson.find("\"owner\":\"hazard\"")
        != std::string::npos);
    assert(observedJson.find("\"id\":0") != std::string::npos);

    // A route-owned configured-hazard retry is a separate lifecycle token.
    // The unrelated receiptless rejection remains visible but cannot replace
    // the reason consumed by the next route tick.
    WorldBotState routeRetry;
    routeRetry.ActivePathValid = false;
    routeRetry.MovementLease.MovementOwner = Owner::Route;
    routeRetry.ValidationRouteDodgeCasterGuid = ObjectGuid(std::uint64_t(27));
    routeRetry.ValidationRouteDodgeSpellId = 79580;
    routeRetry.ValidationRouteDodgeUntilMs = 1500;
    routeRetry.ValidationRouteDodgeBearingAttempt = 3;
    routeRetry.LastPathRejectReason =
        "hazard_exit_no_union_safe_native_path";
    routeRetry.LastNoProgressReason = "route_hazard_retry_armed";
    routeRetry.LastRecoveryResult =
        "hazard_exit_no_union_safe_native_path";
    routeRetry.LastPathChangeMs = 800;

    bool const retryArmed = HasArmedRouteHazardRetry(
        true,
        !routeRetry.ValidationRouteDodgeCasterGuid.IsEmpty()
            && routeRetry.ValidationRouteDodgeSpellId != 0,
        routeRetry.ValidationRouteDodgeUntilMs, 1000,
        routeRetry.ActivePathValid, routeRetry.LastPathRejectReason);
    assert(BotWorldPopulationMgrBotState::
        ApplyPreAdmissionMovementPathRejection(
            routeRetry, rejectedHazard.Owner,
            "route_destination_future_pack_unsafe", 1000, retryArmed)
        == Disposition::ObserveOnlyPreserveExistingOwner);
    assert(routeRetry.LastPathRejectReason
        == "hazard_exit_no_union_safe_native_path");
    assert(routeRetry.LastNoProgressReason == "route_hazard_retry_armed");
    assert(routeRetry.LastRecoveryResult
        == "hazard_exit_no_union_safe_native_path");
    assert(routeRetry.ValidationRouteDodgeUntilMs == 1500);
    assert(routeRetry.ValidationRouteDodgeBearingAttempt == 3);
    assert(routeRetry.LastPathChangeMs == 800);
    assert(HasArmedRouteHazardRetry(
        true, true, routeRetry.ValidationRouteDodgeUntilMs, 1100,
        routeRetry.ActivePathValid, routeRetry.LastPathRejectReason));
    assert(!HasArmedRouteHazardRetry(
        true, true, routeRetry.ValidationRouteDodgeUntilMs, 1500,
        routeRetry.ActivePathValid, routeRetry.LastPathRejectReason));

    // The same owner has no foreign identity to preserve. Its rejected
    // replacement fails closed instead of retaining a path it no longer owns.
    WorldBotState sameOwner;
    sameOwner.ActivePathValid = true;
    sameOwner.ActivePathSegmentValid = true;
    sameOwner.ActivePathTraversalMode = "native_walkable_step";
    sameOwner.MovementLease.MovementOwner = Owner::Hazard;
    assert(BotWorldPopulationMgrBotState::
        ApplyPreAdmissionMovementPathRejection(
            sameOwner, rejectedHazard.Owner,
            "route_destination_future_pack_unsafe", 1000, false)
        == Disposition::RejectAndClear);
    assert(!sameOwner.ActivePathValid);
    assert(!sameOwner.ActivePathSegmentValid);
    assert(sameOwner.LastPathRejectReason
        == "route_destination_future_pack_unsafe");

    // A receiptless rejection with no active path has nothing to preserve,
    // even when the stale lease names the same producer.
    WorldBotState sameOwnerNoPath;
    sameOwnerNoPath.MovementLease.MovementOwner = Owner::Hazard;
    sameOwnerNoPath.LastPathRejectReason = "old_same_owner_reason";
    sameOwnerNoPath.LastNoProgressReason = "old_same_owner_progress";
    sameOwnerNoPath.LastRecoveryResult = "old_same_owner_recovery";
    assert(BotWorldPopulationMgrBotState::
        ApplyPreAdmissionMovementPathRejection(
            sameOwnerNoPath, rejectedHazard.Owner,
            "route_destination_future_pack_unsafe", 1000, false)
        == Disposition::RejectAndClear);
    assert(!sameOwnerNoPath.ActivePathValid);
    assert(sameOwnerNoPath.LastPathRejectReason
        == "route_destination_future_pack_unsafe");
    assert(sameOwnerNoPath.LastNoProgressReason
        == "route_destination_future_pack_unsafe");
    assert(sameOwnerNoPath.LastRecoveryResult
        == "route_destination_future_pack_unsafe");

    // With no admitted path and no retry owner, the same central rejection
    // still fails closed through the production destructive state transition.
    WorldBotState unowned;
    unowned.ActivePathSegmentValid = true;
    unowned.ActivePathTraversalMode = "stale";
    unowned.LastPathRejectReason = "old";
    unowned.LastNoProgressReason = "old";
    unowned.LastRecoveryResult = "old";
    assert(BotWorldPopulationMgrBotState::
        ApplyPreAdmissionMovementPathRejection(
            unowned, rejectedHazard.Owner,
            "route_destination_future_pack_unsafe", 1000, false)
        == Disposition::RejectAndClear);
    assert(!unowned.ActivePathValid);
    assert(!unowned.ActivePathSegmentValid);
    assert(unowned.ActivePathTraversalMode.empty());
    assert(unowned.LastPathRejectReason
        == "route_destination_future_pack_unsafe");
    assert(unowned.LastNoProgressReason
        == "route_destination_future_pack_unsafe");
    assert(unowned.LastRecoveryResult
        == "route_destination_future_pack_unsafe");
    assert(unowned.LastPathChangeMs == 1000);

    // Native corpse recovery remains outside the future-pack gate entirely.
    assert(!BotWorldMovement::
        AppliesValidationRoutePatrolFutureDestinationGuard(Owner::Recovery));
    return 0;
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "dep/g3dlite/include"),
            str(source),
            str(DIAGNOSTICS),
            str(RETENTION_DIAGNOSTICS),
            str(PROGRESS_DIAGNOSTICS),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_executor_and_route_owner_call_the_compiled_isolation_contract() -> None:
    executor = EXECUTOR.read_text(encoding="utf-8")
    route_movement = ROUTE_MOVEMENT.read_text(encoding="utf-8")

    gate = executor.index('"future_pack_destination"')
    observation = executor.index("RecordMovementPlannerExecutorOutcome", gate - 200)
    isolation = executor.index(
        "ApplyPreAdmissionMovementPathRejection", observation
    )
    destructive = executor.index("RejectMovementPath", isolation)
    receipt = executor.index("BeginMovementPlannerReceipt", destructive)
    assert observation < isolation < destructive < receipt
    assert "HasArmedRouteHazardRetry" in executor[observation:destructive]
    assert "HasArmedRouteHazardRetry" in route_movement
