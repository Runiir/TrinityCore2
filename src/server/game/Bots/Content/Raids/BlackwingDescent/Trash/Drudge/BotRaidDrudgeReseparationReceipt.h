#ifndef TRINITY_BOT_RAID_DRUDGE_RESEPARATION_RECEIPT_H
#define TRINITY_BOT_RAID_DRUDGE_RESEPARATION_RECEIPT_H

#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace BotRaidDrudgeSpacing
{
// Diagnostic-only evidence for one Drudge member's selected reseparation
// submission. It records native observations without changing admission or
// movement behavior.
struct ReseparationReceipt
{
    bool Recorded = false;
    BotRaidDrudgeGeometry::Scope Scope;
    std::uint64_t RecordedAtMs = 0;
    std::uint64_t SubmissionId = 0;
    std::uint64_t SubmissionAtMs = 0;
    std::uint32_t MemberGuid = 0;
    std::uint32_t CandidateIndex = 0;
    float CandidateX = 0.0f;
    float CandidateY = 0.0f;
    float CandidateZ = 0.0f;
    bool Source0Safe = false;
    bool Source1Safe = false;
    bool LaneSafe = false;
    bool SameLaneSpacingSafe = false;
    bool GroupPositionSafe = false;
    bool CandidateSelected = false;
    std::string CandidateSelectionOutcome = "not_observed";
    std::string PathRejectReason = "none";
    bool MoveAttempted = false;
    bool ArbitrationAccepted = false;
    bool MovementSubmitted = false;
    std::string ArbitrationOutcome = "not_attempted";
    std::string MovementSubmissionOutcome = "not_submitted";
    bool ActivePathCaptured = false;
    bool ActivePathValid = false;
    bool ActivePathScopeMatches = false;
    float ActivePathDestinationX = 0.0f;
    float ActivePathDestinationY = 0.0f;
    float ActivePathDestinationZ = 0.0f;
    std::uint32_t NativeActiveMotionType = 0;
    bool ProgressObserved = false;
    std::uint64_t ProgressAtMs = 0;
    std::string ProgressOutcome = "not_observed";
    bool ArrivalObserved = false;
    std::uint64_t ArrivalAtMs = 0;
    std::string ArrivalOutcome = "not_observed";
    bool ClosureObserved = false;
    std::uint64_t ClosureAtMs = 0;
    std::string ClosureOutcome = "not_observed";
    std::uint32_t SuppressedCount = 0;
};

constexpr std::size_t MaximumReseparationReceipts = 64;

inline void ResetReseparationReceiptsForScope(
    std::vector<ReseparationReceipt>& receipts,
    BotRaidDrudgeGeometry::Scope const& scope)
{
    if (!receipts.empty() && receipts.front().Scope != scope)
        receipts.clear();
}

inline ReseparationReceipt* FindReseparationReceipt(
    std::vector<ReseparationReceipt>& receipts,
    BotRaidDrudgeGeometry::Scope const& scope, std::uint32_t memberGuid,
    std::uint32_t candidateIndex, float candidateX, float candidateY,
    bool submitted)
{
    for (ReseparationReceipt& receipt : receipts)
        if (receipt.Scope == scope && receipt.MemberGuid == memberGuid
            && receipt.CandidateIndex == candidateIndex
            && receipt.CandidateX == candidateX
            && receipt.CandidateY == candidateY
            && receipt.MovementSubmitted == submitted)
            return &receipt;
    return nullptr;
}

inline ReseparationReceipt& ObserveReseparationCandidate(
    std::vector<ReseparationReceipt>& receipts,
    BotRaidDrudgeGeometry::Scope const& scope, std::uint32_t memberGuid,
    std::uint32_t candidateIndex, float candidateX, float candidateY,
    float candidateZ, bool source0Safe, bool source1Safe, bool laneSafe,
    bool sameLaneSpacingSafe, bool groupPositionSafe, bool selected,
    char const* selectionOutcome, char const* pathRejectReason,
    std::uint64_t nowMs)
{
    ResetReseparationReceiptsForScope(receipts, scope);
    ReseparationReceipt* existing = FindReseparationReceipt(receipts, scope,
        memberGuid, candidateIndex, candidateX, candidateY, false);
    if (!existing)
    {
        if (receipts.size() >= MaximumReseparationReceipts)
            receipts.erase(receipts.begin());
        receipts.emplace_back();
        existing = &receipts.back();
        existing->Recorded = true;
        existing->Scope = scope;
        existing->RecordedAtMs = nowMs;
        existing->MemberGuid = memberGuid;
        existing->CandidateIndex = candidateIndex;
        existing->CandidateX = candidateX;
        existing->CandidateY = candidateY;
        existing->CandidateZ = candidateZ;
    }
    else
        ++existing->SuppressedCount;
    existing->CandidateZ = candidateZ;
    existing->Source0Safe = source0Safe;
    existing->Source1Safe = source1Safe;
    existing->LaneSafe = laneSafe;
    existing->SameLaneSpacingSafe = sameLaneSpacingSafe;
    existing->GroupPositionSafe = groupPositionSafe;
    existing->CandidateSelected = existing->CandidateSelected || selected;
    existing->CandidateSelectionOutcome = selectionOutcome
        ? selectionOutcome : "unknown";
    existing->PathRejectReason = pathRejectReason
        ? pathRejectReason : "none";
    return *existing;
}

inline ReseparationReceipt* FindSelectedReseparationReceipt(
    std::vector<ReseparationReceipt>& receipts,
    BotRaidDrudgeGeometry::Scope const& scope, std::uint32_t memberGuid,
    std::uint32_t candidateIndex, float candidateX, float candidateY)
{
    for (ReseparationReceipt& receipt : receipts)
        if (receipt.Scope == scope && receipt.MemberGuid == memberGuid
            && receipt.CandidateIndex == candidateIndex
            && receipt.CandidateX == candidateX
            && receipt.CandidateY == candidateY
            && receipt.CandidateSelected)
            return &receipt;
    return nullptr;
}

inline void MarkReseparationClosure(
    std::vector<ReseparationReceipt>& receipts,
    BotRaidDrudgeGeometry::Scope const& scope, std::uint64_t nowMs,
    char const* outcome)
{
    for (ReseparationReceipt& receipt : receipts)
        if (receipt.Scope == scope && receipt.CandidateSelected)
        {
            receipt.ClosureObserved = true;
            receipt.ClosureAtMs = nowMs;
            receipt.ClosureOutcome = outcome ? outcome : "closed";
        }
}
}

#endif
