#ifndef TRINITY_BOT_VALIDATION_RAID_ADMISSION_READINESS_H
#define TRINITY_BOT_VALIDATION_RAID_ADMISSION_READINESS_H

#include <cstdint>
#include <string>
#include <vector>

namespace BotValidationRaidAdmissionReadiness
{
enum class Failure : std::uint8_t
{
    None = 0,
    ExpectedMemberCountZero,
    ProvisionedMemberCountMismatch,
    RosterIncomplete,
    LeasesNotUnique,
    RosterCompositionInvalid,
    DifficultyMismatch,
    NativeGroupMismatch,
    EntrancePlacementMismatch,
    InitialAliveStateMismatch,
    ReceiptSizeMismatch
};

struct Facts
{
    std::uint32_t ExpectedMemberCount = 0;
    std::uint32_t ProvisionedMemberCount = 0;
    bool RosterComplete = false;
    bool UniqueLeases = false;
    bool RosterCompositionValid = false;
    bool DifficultyMatches = false;
    bool NativeGroupExact = false;
    bool EntrancePlacementExact = false;
    bool InitialAliveStateExact = false;
    bool ReceiptCheckEnabled = false;
    std::uint32_t ReceiptSize = 0;
    std::uint32_t ReceiptExpectedSize = 0;
};

struct Result
{
    Facts Receipt;
    Failure FirstFailure = Failure::None;

    bool Ready() const { return FirstFailure == Failure::None; }
};

struct MemberReceipt
{
    std::uint32_t Guid = 0;
    std::string RosterSlotId;
    std::string ClassSpec;
    bool PlannedSlotPresent = false;
    bool PlannedRoleMatches = false;
    bool PlannedClassSpecMatches = false;
    bool DeclaredSpecMatches = false;
    bool RuntimeHunterObserverApplicable = false;
    bool RuntimeHunterObserverMatches = false;
    std::string RuntimeHunterObserverReason;
    std::uint8_t SharedHunterObserverStatus = 0;
    std::string SharedHunterObserverReason;
};

Result Evaluate(Facts const& facts);
char const* FailureReason(Failure failure);
std::string ToJson(Result const& result);
std::string ToJson(Result const& result,
    std::vector<MemberReceipt> const& members);
}

#endif
