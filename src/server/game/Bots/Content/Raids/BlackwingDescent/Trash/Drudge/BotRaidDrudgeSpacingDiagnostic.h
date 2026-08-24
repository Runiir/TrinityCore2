#ifndef TRINITY_BOT_RAID_DRUDGE_SPACING_DIAGNOSTIC_H
#define TRINITY_BOT_RAID_DRUDGE_SPACING_DIAGNOSTIC_H

#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"

#include <cstdint>
#include <string>

namespace BotRaidDrudgeSpacing
{
struct PeerResult
{
    bool Safe = true;
    std::uint32_t PeerGuid = 0;
    float PeerDistance = 0.0f;
    std::string PeerCoordinateSource = "none";
};

struct CandidateResult
{
    PeerResult Spacing;
    bool Source0Safe = false;
    bool Source1Safe = false;
    bool LaneSafe = false;
    bool GroupPositionSafe = false;
};

struct PredicateEvidence
{
    std::uint32_t MemberGuid = 0;
    std::uint32_t CandidateIndex = 0;
    float CandidateX = 0.0f;
    float CandidateY = 0.0f;
    std::uint32_t SameLanePeerGuid = 0;
    float SameLanePeerDistance = 0.0f;
    std::string PeerCoordinateSource = "none";
    bool Source0Safe = false;
    bool Source1Safe = false;
    bool LaneSafe = false;
    bool SameLaneSpacingSafe = false;
    bool GroupPositionSafe = false;

    bool HasFailure() const
    {
        return !GroupPositionSafe;
    }

    char const* FirstFailedPredicate() const
    {
        if (!Source0Safe)
            return "source0_safe";
        if (!Source1Safe)
            return "source1_safe";
        if (!LaneSafe)
            return "lane_safe";
        if (!SameLaneSpacingSafe)
            return "same_lane_spacing_safe";
        return "group_position_safe";
    }
};

struct Failure
{
    bool Recorded = false;
    std::uint64_t RecordedAtMs = 0;
    BotRaidDrudgeGeometry::Scope Scope;
    std::uint32_t MemberGuid = 0;
    std::uint32_t CandidateIndex = 0;
    float CandidateX = 0.0f;
    float CandidateY = 0.0f;
    std::uint32_t SameLanePeerGuid = 0;
    float SameLanePeerDistance = 0.0f;
    std::string PeerCoordinateSource = "none";
    bool Source0Safe = false;
    bool Source1Safe = false;
    bool LaneSafe = false;
    bool SameLaneSpacingSafe = false;
    bool GroupPositionSafe = false;
    std::string FirstFailedPredicate;
    std::uint32_t SuppressedCount = 0;
};

inline bool RecordFirstFailure(Failure& failure,
    BotRaidDrudgeGeometry::Scope const& scope,
    PredicateEvidence const& evidence, std::uint64_t nowMs)
{
    if (!evidence.HasFailure())
        return false;
    if (failure.Recorded && failure.Scope != scope)
        failure = Failure{};
    if (failure.Recorded)
    {
        ++failure.SuppressedCount;
        return false;
    }
    failure.Recorded = true;
    failure.RecordedAtMs = nowMs;
    failure.Scope = scope;
    failure.MemberGuid = evidence.MemberGuid;
    failure.CandidateIndex = evidence.CandidateIndex;
    failure.CandidateX = evidence.CandidateX;
    failure.CandidateY = evidence.CandidateY;
    failure.SameLanePeerGuid = evidence.SameLanePeerGuid;
    failure.SameLanePeerDistance = evidence.SameLanePeerDistance;
    failure.PeerCoordinateSource = evidence.PeerCoordinateSource;
    failure.Source0Safe = evidence.Source0Safe;
    failure.Source1Safe = evidence.Source1Safe;
    failure.LaneSafe = evidence.LaneSafe;
    failure.SameLaneSpacingSafe = evidence.SameLaneSpacingSafe;
    failure.GroupPositionSafe = evidence.GroupPositionSafe;
    failure.FirstFailedPredicate = evidence.FirstFailedPredicate();
    return true;
}
}

#endif
