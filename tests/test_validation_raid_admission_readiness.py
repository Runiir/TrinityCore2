from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "src/server/game"
HELPER = GAME / "Bots/BotValidationRaidAdmissionReadiness.cpp"
GROUP = GAME / "Bots/BotWorldPopulationMgrValidationCohortGroup.cpp"
ADMISSION = GAME / "Bots/BotWorldPopulationMgrValidationAdmission.cpp"
RUNTIME = GAME / "Bots/BotWorldPopulationMgrValidationCohortRuntime.cpp"


def test_validation_raid_admission_readiness_is_compiled_and_typed() -> None:
    harness = r'''
#include "Bots/BotValidationRaidAdmissionReadiness.h"

#include <cassert>
#include <string>

using namespace BotValidationRaidAdmissionReadiness;

Facts passingFacts()
{
    Facts facts;
    facts.ExpectedMemberCount = 10;
    facts.ProvisionedMemberCount = 10;
    facts.RosterComplete = true;
    facts.UniqueLeases = true;
    facts.RosterCompositionValid = true;
    facts.DifficultyMatches = true;
    facts.NativeGroupExact = true;
    facts.EntrancePlacementExact = true;
    facts.InitialAliveStateExact = true;
    facts.ReceiptCheckEnabled = true;
    facts.ReceiptSize = 10;
    facts.ReceiptExpectedSize = 10;
    return facts;
}

void expectFailure(Facts facts, Failure expected, char const* reason)
{
    Result const result = Evaluate(facts);
    assert(!result.Ready());
    assert(result.FirstFailure == expected);
    assert(std::string(FailureReason(expected)) == reason);
    std::string const receipt = ToJson(result);
    assert(receipt.find(reason) != std::string::npos);
    assert(receipt.find("\"ready\":false") != std::string::npos);
}

int main()
{
    Facts facts = passingFacts();
    Result result = Evaluate(facts);
    assert(result.Ready());
    assert(result.FirstFailure == Failure::None);
    std::string receipt = ToJson(result);
    for (char const* field : {
        "expected_member_count", "provisioned_member_count",
        "roster_complete", "unique_leases", "roster_composition_valid",
        "difficulty_matches", "native_group_exact",
        "entrance_placement_exact", "initial_alive_state_exact",
        "receipt_size", "receipt_expected_size"})
        assert(receipt.find(field) != std::string::npos);
    MemberReceipt member;
    member.Guid = 30009;
    member.RosterSlotId = "raid_dps_4";
    member.ClassSpec = "marksmanship_hunter";
    member.PlannedSlotPresent = true;
    member.PlannedRoleMatches = true;
    member.PlannedClassSpecMatches = true;
    member.DeclaredSpecMatches = true;
    member.RuntimeHunterObserverApplicable = true;
    member.RuntimeHunterObserverMatches = false;
    member.RuntimeHunterObserverReason = "identity_invalid";
    member.SharedHunterObserverStatus = 3;
    member.SharedHunterObserverReason = "identity_observed";
    receipt = ToJson(result, {member});
    for (char const* value : {
        "\"guid\":30009", "raid_dps_4", "marksmanship_hunter",
        "planned_slot_present", "planned_role_matches",
        "planned_class_spec_matches", "declared_spec_matches",
        "runtime_hunter_observer_matches",
        "runtime_hunter_observer_reason",
        "shared_hunter_observer_status",
        "shared_hunter_observer_reason", "identity_invalid",
        "identity_observed"})
        assert(receipt.find(value) != std::string::npos);
    assert(receipt.find("\"planned_slot_present\":true") != std::string::npos);
    assert(receipt.find("\"planned_role_matches\":true") != std::string::npos);
    assert(receipt.find("\"declared_spec_matches\":true") != std::string::npos);
    assert(receipt.find("\"runtime_hunter_observer_matches\":false")
        != std::string::npos);
    assert(receipt.find("\"shared_hunter_observer_status\":3")
        != std::string::npos);

    facts = passingFacts(); facts.ExpectedMemberCount = 0;
    expectFailure(facts, Failure::ExpectedMemberCountZero,
        "validation_raid_admission_expected_member_count_zero");
    facts = passingFacts(); facts.ProvisionedMemberCount = 9;
    expectFailure(facts, Failure::ProvisionedMemberCountMismatch,
        "validation_raid_admission_provisioned_member_count_mismatch");
    facts = passingFacts(); facts.RosterComplete = false;
    expectFailure(facts, Failure::RosterIncomplete,
        "validation_raid_admission_roster_incomplete");
    facts = passingFacts(); facts.UniqueLeases = false;
    expectFailure(facts, Failure::LeasesNotUnique,
        "validation_raid_admission_leases_not_unique");
    facts = passingFacts(); facts.RosterCompositionValid = false;
    expectFailure(facts, Failure::RosterCompositionInvalid,
        "validation_raid_admission_roster_composition_invalid");
    facts = passingFacts(); facts.DifficultyMatches = false;
    expectFailure(facts, Failure::DifficultyMismatch,
        "validation_raid_admission_difficulty_mismatch");
    facts = passingFacts(); facts.NativeGroupExact = false;
    expectFailure(facts, Failure::NativeGroupMismatch,
        "validation_raid_admission_native_group_mismatch");
    facts = passingFacts(); facts.EntrancePlacementExact = false;
    expectFailure(facts, Failure::EntrancePlacementMismatch,
        "validation_raid_admission_entrance_placement_mismatch");
    facts = passingFacts(); facts.InitialAliveStateExact = false;
    expectFailure(facts, Failure::InitialAliveStateMismatch,
        "validation_raid_admission_initial_alive_state_mismatch");
    facts = passingFacts(); facts.ReceiptSize = 9;
    expectFailure(facts, Failure::ReceiptSizeMismatch,
        "validation_raid_admission_receipt_size_mismatch");

    // The pre-receipt pass deliberately ignores only receipt size; every
    // already-observed admission prerequisite remains decisive.
    facts = passingFacts();
    facts.ReceiptCheckEnabled = false;
    facts.ReceiptSize = 0;
    assert(Evaluate(facts).Ready());
    facts.RosterComplete = false;
    assert(Evaluate(facts).FirstFailure == Failure::RosterIncomplete);
}
'''
    with tempfile.TemporaryDirectory() as directory:
        directory_path = Path(directory)
        source = directory_path / "validation_raid_admission_readiness_test.cpp"
        binary = directory_path / "validation_raid_admission_readiness_test"
        source.write_text(harness, encoding="utf-8")
        subprocess.run(
            [
                "g++",
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(GAME),
                str(source),
                str(HELPER),
                "-o",
                str(binary),
            ],
            check=True,
        )
        subprocess.run([str(binary)], check=True)


def test_live_admission_wires_actual_values_and_preserves_typed_failure() -> None:
    group = GROUP.read_text(encoding="utf-8")
    admission = ADMISSION.read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")

    for assignment in (
        "readinessFacts.ExpectedMemberCount = raid.ExpectedSize",
        "readinessFacts.ProvisionedMemberCount = raid.ProvisionedMemberCount",
        "readinessFacts.RosterComplete = raid.RosterComplete",
        "readinessFacts.UniqueLeases = raid.UniqueLeases",
        "readinessFacts.RosterCompositionValid = raid.RosterCompositionValid",
        "readinessFacts.DifficultyMatches = raid.DifficultyMatches",
        "readinessFacts.NativeGroupExact = nativeGroupMembershipExact",
        "readinessFacts.EntrancePlacementExact = exactEntrancePlacement",
        "readinessFacts.InitialAliveStateExact = exactInitialAliveState",
        "readinessFacts.ReceiptSize = uint32(receipt.size())",
        "readinessFacts.ReceiptExpectedSize = raid.ExpectedSize",
    ):
        assert assignment in group
    assert "raid.ServerProvisioningComplete = readiness.Ready()" in group
    assert "ToJson(readiness, memberReceipts).c_str()" in group
    for field in (
        "member.Guid = guid",
        "member.RosterSlotId = slot.RosterSlotId",
        "member.ClassSpec = slot.ClassSpec",
        "member.PlannedSlotPresent = slot.AdmissionPlannedSlotPresent",
        "member.PlannedRoleMatches = slot.AdmissionPlannedRoleMatches",
        "member.DeclaredSpecMatches = slot.AdmissionDeclaredSpecMatches",
        "member.RuntimeHunterObserverMatches = slot.AdmissionRuntimeHunterObserverMatches",
        "member.RuntimeHunterObserverReason = slot.AdmissionRuntimeHunterObserverReason",
        "member.SharedHunterObserverStatus = slot.AdmissionSharedHunterObserverStatus",
        "member.SharedHunterObserverReason = slot.AdmissionSharedHunterObserverReason",
    ):
        assert field in group
    assert "sealedAdmissionReadinessFailure = FailureReason(" in group
    assert "Cohort().LastPopulationFailureReason =\n            sealedAdmissionReadinessFailure" in group

    assert "Cohort().LastPopulationFailureReason" in admission[
        admission.index("Cohort().ValidationAdmissionBatchSealed = true") :
    ]
    assert "rollbackAdmission(readinessFailure.empty()" in admission
    assert '"validation_raid_admission_activation_failed"' in admission

    for field in (
        "slot.AdmissionPlannedSlotPresent = plannedSlot != nullptr",
        "slot.AdmissionPlannedRoleMatches = plannedSlot",
        "slot.AdmissionPlannedClassSpecMatches = plannedSlot",
        "slot.AdmissionDeclaredSpecMatches =",
        "LoadedBotMatchesDeclaredSpec(bot, slot.ClassSpec)",
        "slot.AdmissionRuntimeHunterObserverMatches =",
        "LoadedBotMatchesPinnedHunterPet(bot, slot.ClassSpec)",
        "ObserveActiveOrdinaryHunterPetStatus(",
        "slot.AdmissionSharedHunterObserverReason =",
    ):
        assert field in runtime
    runtime_gate = runtime[
        runtime.index("if (Cohort().Config.ValidationRouteEnable") :
        runtime.index("RaidNativeSignalState currentSignal")
    ]
    for field in (
        "AdmissionPlannedSlotPresent",
        "AdmissionPlannedRoleMatches",
        "AdmissionPlannedClassSpecMatches",
        "AdmissionDeclaredSpecMatches",
        "AdmissionRuntimeHunterObserverMatches",
    ):
        assert field in runtime_gate
