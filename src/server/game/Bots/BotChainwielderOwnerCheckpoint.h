#ifndef TRINITY_BOT_CHAINWIELDER_OWNER_CHECKPOINT_H
#define TRINITY_BOT_CHAINWIELDER_OWNER_CHECKPOINT_H

#include "Bots/BotMovementArbiter.h"
#include "Define.h"

#include <cctype>
#include <string>
#include <string_view>

namespace BotChainwielderOwnerCheckpoint
{
constexpr char FixtureId[] =
    "chainwielder_pre_admission_rejection_isolation_v1";
constexpr char ProfileId[] = "blackwing_descent_10n_magmaw_diagnostic";
constexpr char PoolTag[] = "blackwing_descent_10n_magmaw_diagnostic";
constexpr char NodeId[] = "bwd.magmaw.chainwielder";
constexpr char Authority[] =
    "chainwielder_fixture_observation_only_not_gameplay";
constexpr uint32 MapId = 669;
constexpr uint32 TargetEntry = 42649;
constexpr uint32 ActorCount = 10;
constexpr uint32 MaximumAwaitTicks = 240;

enum class Stage : uint8
{
    Disabled,
    Armed,
    RejectionObserved,
    AfterObserved,
    Completed,
    Failed
};

struct GateInput
{
    bool Enabled = false;
    bool CohortActive = false;
    std::string_view SelectedProfile;
    std::string_view ConfigName;
    std::string_view PoolTagFilter;
    std::string_view ScenarioId;
    std::string_view RouteNodeId;
    uint32 RuntimeMapId = 0;
    uint32 TargetPopulation = 0;
    uint32 ActiveActorCount = 0;
    uint32 TargetEntry = 0;
    bool ValidationRouteEnabled = false;
    bool AllowRaids = false;
    uint64 AttemptId = 0;
    std::string_view ConfigFixtureId;
    std::string_view ConfigAdmissionSha256;
    std::string_view RequestedAdmissionSha256;
    std::string_view ConfigSourceCommit;
    std::string_view RequestedSourceCommit;
    std::string_view BinarySourceCommit;
};

inline bool IsLowerHex(std::string_view value, std::size_t length)
{
    if (value.size() != length)
        return false;
    for (unsigned char character : value)
        if (!std::isdigit(character)
            && !(character >= 'a' && character <= 'f'))
            return false;
    return true;
}

inline char const* RejectionReason(GateInput const& input)
{
    if (!input.Enabled)
        return "chainwielder_checkpoint_disabled";
    if (!input.CohortActive)
        return "chainwielder_checkpoint_runtime_inactive";
    if (input.SelectedProfile != ProfileId || input.ConfigName != ProfileId
        || input.PoolTagFilter != PoolTag || input.ScenarioId != ProfileId)
        return "chainwielder_checkpoint_profile_identity_mismatch";
    if (!input.ValidationRouteEnabled || !input.AllowRaids
        || input.RuntimeMapId != MapId || input.TargetEntry != TargetEntry
        || input.RouteNodeId != NodeId)
        return "chainwielder_checkpoint_route_identity_mismatch";
    if (input.TargetPopulation != ActorCount
        || input.ActiveActorCount != ActorCount)
        return "chainwielder_checkpoint_actor_contract_mismatch";
    if (!input.AttemptId)
        return "chainwielder_checkpoint_attempt_identity_missing";
    if (input.ConfigFixtureId != FixtureId)
        return "chainwielder_checkpoint_fixture_identity_mismatch";
    if (!IsLowerHex(input.ConfigAdmissionSha256, 64)
        || input.ConfigAdmissionSha256 != input.RequestedAdmissionSha256)
        return "chainwielder_checkpoint_admission_mismatch";
    if (!IsLowerHex(input.ConfigSourceCommit, 40)
        || input.ConfigSourceCommit != input.RequestedSourceCommit
        || input.ConfigSourceCommit != input.BinarySourceCommit)
        return "chainwielder_checkpoint_source_identity_mismatch";
    return nullptr;
}

struct OwnerSnapshot
{
    BotMovementArbitration::Owner MovementOwner =
        BotMovementArbitration::Owner::None;
    bool ActivePathValid = false;
    bool ActivePathSegmentValid = false;
    std::string ActivePathTraversalMode;
    uint64 ActivePathTargetGuid = 0;
    uint64 ActivePathAttemptId = 0;
    uint32 ActivePathWipeGeneration = 0;
    uint64 ActivePathRouteGeneration = 0;
    std::string ActivePathRouteNodeId;
    float ActivePathToX = 0.0f;
    float ActivePathToY = 0.0f;
    float ActivePathToZ = 0.0f;
    uint64 DodgeCasterGuid = 0;
    uint32 DodgeSpellId = 0;
    uint64 DodgeUntilMs = 0;
    uint8 DodgeBearingAttempt = 0;
    std::string LastPathRejectReason;
};

inline bool SameRouteIdentity(
    OwnerSnapshot const& before, OwnerSnapshot const& after)
{
    return before.MovementOwner == after.MovementOwner
        && before.ActivePathValid == after.ActivePathValid
        && before.ActivePathSegmentValid == after.ActivePathSegmentValid
        && before.ActivePathTraversalMode == after.ActivePathTraversalMode
        && before.ActivePathTargetGuid == after.ActivePathTargetGuid
        && before.ActivePathAttemptId == after.ActivePathAttemptId
        && before.ActivePathWipeGeneration == after.ActivePathWipeGeneration
        && before.ActivePathRouteGeneration == after.ActivePathRouteGeneration
        && before.ActivePathRouteNodeId == after.ActivePathRouteNodeId
        && before.ActivePathToX == after.ActivePathToX
        && before.ActivePathToY == after.ActivePathToY
        && before.ActivePathToZ == after.ActivePathToZ
        && before.DodgeCasterGuid == after.DodgeCasterGuid
        && before.DodgeSpellId == after.DodgeSpellId
        && before.DodgeUntilMs == after.DodgeUntilMs
        && before.DodgeBearingAttempt == after.DodgeBearingAttempt
        && before.LastPathRejectReason == after.LastPathRejectReason;
}

struct State
{
    Stage CurrentStage = Stage::Disabled;
    uint64 AttemptId = 0;
    uint32 ActorGuid = 0;
    uint32 AwaitTicks = 0;
    uint32 InjectionCount = 0;
    uint64 ArmedAtMs = 0;
    uint64 RejectionObservedAtMs = 0;
    uint64 AfterObservedAtMs = 0;
    uint64 OutcomeObservedAtMs = 0;
    bool TriggeredByActiveRoutePath = false;
    bool TriggeredByArmedRouteHazardRetry = false;
    bool BeforeAfterIdentityPreserved = false;
    uint64 RejectionReceiptId = 0;
    std::string RejectionGate;
    std::string RejectionReason;
    std::string Outcome;
    OwnerSnapshot Before;
    OwnerSnapshot After;
};
}

#endif
