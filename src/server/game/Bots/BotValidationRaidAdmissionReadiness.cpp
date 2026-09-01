#include "Bots/BotValidationRaidAdmissionReadiness.h"

#include <sstream>

namespace BotValidationRaidAdmissionReadiness
{
Result Evaluate(Facts const& facts)
{
    Result result;
    result.Receipt = facts;
    if (!facts.ExpectedMemberCount)
        result.FirstFailure = Failure::ExpectedMemberCountZero;
    else if (facts.ProvisionedMemberCount != facts.ExpectedMemberCount)
        result.FirstFailure = Failure::ProvisionedMemberCountMismatch;
    else if (!facts.RosterComplete)
        result.FirstFailure = Failure::RosterIncomplete;
    else if (!facts.UniqueLeases)
        result.FirstFailure = Failure::LeasesNotUnique;
    else if (!facts.RosterCompositionValid)
        result.FirstFailure = Failure::RosterCompositionInvalid;
    else if (!facts.DifficultyMatches)
        result.FirstFailure = Failure::DifficultyMismatch;
    else if (!facts.NativeGroupExact)
        result.FirstFailure = Failure::NativeGroupMismatch;
    else if (!facts.EntrancePlacementExact)
        result.FirstFailure = Failure::EntrancePlacementMismatch;
    else if (!facts.InitialAliveStateExact)
        result.FirstFailure = Failure::InitialAliveStateMismatch;
    else if (facts.ReceiptCheckEnabled
        && facts.ReceiptSize != facts.ReceiptExpectedSize)
        result.FirstFailure = Failure::ReceiptSizeMismatch;
    return result;
}

char const* FailureReason(Failure failure)
{
    switch (failure)
    {
        case Failure::ExpectedMemberCountZero:
            return "validation_raid_admission_expected_member_count_zero";
        case Failure::ProvisionedMemberCountMismatch:
            return "validation_raid_admission_provisioned_member_count_mismatch";
        case Failure::RosterIncomplete:
            return "validation_raid_admission_roster_incomplete";
        case Failure::LeasesNotUnique:
            return "validation_raid_admission_leases_not_unique";
        case Failure::RosterCompositionInvalid:
            return "validation_raid_admission_roster_composition_invalid";
        case Failure::DifficultyMismatch:
            return "validation_raid_admission_difficulty_mismatch";
        case Failure::NativeGroupMismatch:
            return "validation_raid_admission_native_group_mismatch";
        case Failure::EntrancePlacementMismatch:
            return "validation_raid_admission_entrance_placement_mismatch";
        case Failure::InitialAliveStateMismatch:
            return "validation_raid_admission_initial_alive_state_mismatch";
        case Failure::ReceiptSizeMismatch:
            return "validation_raid_admission_receipt_size_mismatch";
        case Failure::None:
            return "";
    }
    return "validation_raid_admission_readiness_status_unknown";
}

std::string ToJson(Result const& result)
{
    Facts const& facts = result.Receipt;
    std::ostringstream json;
    json << "{\"ready\":" << (result.Ready() ? "true" : "false")
         << ",\"failure_reason\":\"" << FailureReason(result.FirstFailure) << "\""
         << ",\"expected_member_count\":" << facts.ExpectedMemberCount
         << ",\"provisioned_member_count\":" << facts.ProvisionedMemberCount
         << ",\"roster_complete\":" << (facts.RosterComplete ? "true" : "false")
         << ",\"unique_leases\":" << (facts.UniqueLeases ? "true" : "false")
         << ",\"roster_composition_valid\":" << (facts.RosterCompositionValid ? "true" : "false")
         << ",\"difficulty_matches\":" << (facts.DifficultyMatches ? "true" : "false")
         << ",\"native_group_exact\":" << (facts.NativeGroupExact ? "true" : "false")
         << ",\"entrance_placement_exact\":" << (facts.EntrancePlacementExact ? "true" : "false")
         << ",\"initial_alive_state_exact\":" << (facts.InitialAliveStateExact ? "true" : "false")
         << ",\"receipt_check_enabled\":" << (facts.ReceiptCheckEnabled ? "true" : "false")
         << ",\"receipt_size\":" << facts.ReceiptSize
         << ",\"receipt_expected_size\":" << facts.ReceiptExpectedSize
         << '}';
    return json.str();
}
}
