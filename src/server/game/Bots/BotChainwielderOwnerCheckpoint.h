#ifndef TRINITY_BOT_CHAINWIELDER_OWNER_CHECKPOINT_H
#define TRINITY_BOT_CHAINWIELDER_OWNER_CHECKPOINT_H

#include "Bots/BotMovementArbiter.h"
#include "Bots/BotActionArbiter.h"
#include "Define.h"

#include <cctype>
#include <string>
#include <string_view>
#include <utility>

namespace BotControllerRouteHold
{
enum class Phase : uint8
{
    Disabled,
    Acquiring,
    Held,
    Armed,
    CheckpointTerminal,
    Released,
    Failed
};

enum class Admission : uint8
{
    Ordinary,
    FormationMovement,
    FriendlyHealing,
    BagConsumable,
    OffenseSuppression,
    DefensiveSurvival,
    CheckpointObservation
};

inline char const* PhaseName(Phase phase)
{
    switch (phase)
    {
        case Phase::Disabled: return "disabled";
        case Phase::Acquiring: return "acquiring";
        case Phase::Held: return "held";
        case Phase::Armed: return "armed";
        case Phase::CheckpointTerminal: return "checkpoint_terminal";
        case Phase::Released: return "released";
        case Phase::Failed: return "failed";
    }
    return "unknown";
}

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

struct SourceIdentityComparison
{
    bool Accepted = false;
    bool ConfiguredPresent = false;
    bool RequestedPresent = false;
    bool ConfiguredFormatValid = false;
    bool RequestedFormatValid = false;
    bool AuthoritiesMatch = false;
    bool BinaryRevisionPresent = false;
    bool BinaryRevisionFormatValid = false;
    bool BinaryRevisionMatchesSource = false;
    std::size_t ConfiguredLength = 0;
    std::size_t RequestedLength = 0;
    std::size_t BinaryRevisionLength = 0;
};

inline SourceIdentityComparison CompareSourceIdentity(
    std::string_view configuredSource, std::string_view requestedSource,
    std::string_view binaryRevision)
{
    SourceIdentityComparison result;
    result.ConfiguredPresent = !configuredSource.empty();
    result.RequestedPresent = !requestedSource.empty();
    result.ConfiguredFormatValid = IsLowerHex(configuredSource, 40);
    result.RequestedFormatValid = IsLowerHex(requestedSource, 40);
    result.AuthoritiesMatch = configuredSource == requestedSource;
    result.BinaryRevisionPresent = !binaryRevision.empty();
    result.BinaryRevisionFormatValid = IsLowerHex(binaryRevision, 12)
        || IsLowerHex(binaryRevision, 40);
    result.BinaryRevisionMatchesSource = result.BinaryRevisionFormatValid
        && result.ConfiguredFormatValid
        && configuredSource.substr(0, binaryRevision.size()) == binaryRevision;
    result.ConfiguredLength = configuredSource.size();
    result.RequestedLength = requestedSource.size();
    result.BinaryRevisionLength = binaryRevision.size();
    result.Accepted = result.ConfiguredPresent && result.RequestedPresent
        && result.ConfiguredFormatValid && result.RequestedFormatValid
        && result.AuthoritiesMatch && result.BinaryRevisionPresent
        && result.BinaryRevisionFormatValid
        && result.BinaryRevisionMatchesSource;
    return result;
}

struct Identity
{
    std::string CohortId;
    uint64 ServerEpoch = 0;
    uint64 AttemptId = 0;
    std::string ScenarioId;
    std::string RuntimeProfile;
    std::string RouteManifestSha256;
    uint64 RouteGeneration = 0;
    std::string RouteNodeId;
    uint32 ActorGuid = 0;
    std::string FixtureId;
    std::string SealSha256;
    std::string SourceCommit;

    bool SameCore(Identity const& other) const
    {
        return CohortId == other.CohortId
            && ServerEpoch == other.ServerEpoch
            && AttemptId == other.AttemptId
            && ActorGuid == other.ActorGuid
            && FixtureId == other.FixtureId
            && SealSha256 == other.SealSha256
            && SourceCommit == other.SourceCommit;
    }

    bool operator==(Identity const& other) const
    {
        return SameCore(other)
            && ScenarioId == other.ScenarioId
            && RuntimeProfile == other.RuntimeProfile
            && RouteManifestSha256 == other.RouteManifestSha256
            && RouteGeneration == other.RouteGeneration
            && RouteNodeId == other.RouteNodeId;
    }

    bool ValidBootstrap() const
    {
        return !CohortId.empty() && ServerEpoch && AttemptId && ActorGuid
            && !FixtureId.empty() && IsLowerHex(SealSha256, 64)
            && IsLowerHex(SourceCommit, 40);
    }

    bool ValidComplete() const
    {
        return ValidBootstrap() && !ScenarioId.empty()
            && !RuntimeProfile.empty()
            && IsLowerHex(RouteManifestSha256, 64)
            && RouteGeneration && !RouteNodeId.empty();
    }

    std::string ScopeKey() const
    {
        return CohortId + ":" + std::to_string(ServerEpoch) + ":"
            + std::to_string(AttemptId) + ":"
            + std::to_string(RouteGeneration) + ":"
            + std::to_string(ActorGuid);
    }
};

struct TransitionResult
{
    bool Accepted = false;
    std::string Reason;
};

struct State
{
    Phase CurrentPhase = Phase::Disabled;
    Identity Scope;
    uint32 AcquireCount = 0;
    uint32 ArmAckCount = 0;
    uint32 ReleaseCount = 0;
    uint64 SuppressedRouteActionCount = 0;
    uint64 SuppressedRouteAdvanceCount = 0;
    uint64 AcquiredAtMs = 0;
    uint64 ArmedAtMs = 0;
    uint64 TerminalAtMs = 0;
    uint64 ReleasedAtMs = 0;
    std::string CheckpointStage = "disabled";
    bool CheckpointTerminal = false;
    bool CheckpointIdentityPreserved = false;
    std::string FailureReason;

    bool Holding() const
    {
        return CurrentPhase == Phase::Acquiring
            || CurrentPhase == Phase::Held
            || CurrentPhase == Phase::Armed
            || CurrentPhase == Phase::CheckpointTerminal
            || CurrentPhase == Phase::Failed;
    }

    TransitionResult Reject(std::string reason, bool retainReleased = false)
    {
        if (FailureReason.empty())
            FailureReason = reason;
        if (!retainReleased)
            CurrentPhase = Phase::Failed;
        return { false, std::move(reason) };
    }

    TransitionResult BeginAcquire(Identity const& bootstrap, uint64 nowMs)
    {
        if (Holding() && Scope.AttemptId == bootstrap.AttemptId)
            return Reject("controller_route_hold_duplicate_acquire");
        if (!bootstrap.ValidBootstrap())
        {
            *this = {};
            return Reject("controller_route_hold_bootstrap_identity_invalid");
        }
        *this = {};
        Scope = bootstrap;
        CurrentPhase = Phase::Acquiring;
        AcquiredAtMs = nowMs;
        return { true, "controller_route_hold_acquire_started" };
    }

    TransitionResult CompleteAcquire(Identity const& identity, uint64 nowMs)
    {
        if (CurrentPhase != Phase::Acquiring)
            return Reject("controller_route_hold_acquire_not_pending");
        if (!identity.ValidComplete() || !Scope.SameCore(identity))
            return Reject("controller_route_hold_acquire_identity_drift");
        Scope = identity;
        CurrentPhase = Phase::Held;
        AcquireCount = 1;
        AcquiredAtMs = nowMs;
        return { true, "controller_route_hold_acquired" };
    }

    bool ValidateIdentity(Identity const& identity)
    {
        if (CurrentPhase == Phase::Disabled
            || CurrentPhase == Phase::Released)
            return true;
        if (Scope == identity)
            return true;
        Reject("controller_route_hold_identity_drift");
        return false;
    }

    TransitionResult AcknowledgeArm(Identity const& identity, uint64 nowMs)
    {
        if (CurrentPhase == Phase::Armed || ArmAckCount)
            return Reject("controller_route_hold_duplicate_arm");
        if (CurrentPhase != Phase::Held)
            return Reject("controller_route_hold_arm_before_acquire");
        if (!ValidateIdentity(identity))
            return { false, FailureReason };
        CurrentPhase = Phase::Armed;
        ArmAckCount = 1;
        ArmedAtMs = nowMs;
        return { true, "controller_route_hold_arm_acknowledged" };
    }

    TransitionResult ObserveCheckpointTerminal(Identity const& identity,
        std::string stage, bool terminal, bool identityPreserved,
        uint64 nowMs)
    {
        if (CurrentPhase != Phase::Armed)
            return Reject("controller_route_hold_checkpoint_terminal_stale");
        if (!ValidateIdentity(identity))
            return { false, FailureReason };
        CheckpointStage = std::move(stage);
        CheckpointTerminal = terminal;
        CheckpointIdentityPreserved = identityPreserved;
        TerminalAtMs = nowMs;
        if (!terminal)
            return Reject("controller_route_hold_checkpoint_terminal_missing");
        if (!identityPreserved)
            return Reject("controller_route_hold_checkpoint_identity_not_preserved");
        CurrentPhase = Phase::CheckpointTerminal;
        return { true, "controller_route_hold_checkpoint_terminal" };
    }

    TransitionResult Release(Identity const& identity, uint64 nowMs)
    {
        if (CurrentPhase == Phase::Released || ReleaseCount)
            return Reject("controller_route_hold_duplicate_release", true);
        if (CurrentPhase != Phase::CheckpointTerminal)
            return Reject("controller_route_hold_release_before_terminal");
        if (!ValidateIdentity(identity))
            return { false, FailureReason };
        CurrentPhase = Phase::Released;
        ReleaseCount = 1;
        ReleasedAtMs = nowMs;
        return { true, "controller_route_hold_released" };
    }

    bool AdmitCandidate(Identity const& identity, uint32 actingActorGuid,
        Admission classification, bool survival)
    {
        if (!Holding())
            return true;
        ValidateIdentity(identity);
        bool const safe = classification == Admission::FormationMovement
            || classification == Admission::FriendlyHealing
            || classification == Admission::BagConsumable
            || classification == Admission::OffenseSuppression
            || classification == Admission::DefensiveSurvival
            || survival;
        bool const checkpointObservation =
            classification == Admission::CheckpointObservation
            && CurrentPhase == Phase::Armed
            && actingActorGuid == Scope.ActorGuid;
        if (safe || checkpointObservation)
            return true;
        ++SuppressedRouteActionCount;
        return false;
    }

    bool PermitRouteAdvance(Identity const& identity,
        uint64 prospectiveGeneration)
    {
        if (CurrentPhase == Phase::Disabled
            || CurrentPhase == Phase::Released)
            return true;
        if (CurrentPhase == Phase::Acquiring)
        {
            bool const initialBootstrap = identity.SameCore(Scope)
                && identity.RouteGeneration == 0
                && prospectiveGeneration == 1;
            if (initialBootstrap)
                return true;
            Reject("controller_route_hold_bootstrap_route_drift");
        }
        else
            ValidateIdentity(identity);
        ++SuppressedRouteAdvanceCount;
        return false;
    }
};

inline Admission ClassifyCandidate(
    BotActionArbitration::Candidate const& candidate,
    BotActionArbitration::AdmissionMetadata const* metadata,
    State const& hold)
{
    using BotActionArbitration::AdmissionClass;
    AdmissionClass classification = metadata
        ? metadata->Classification : AdmissionClass::Unknown;
    if (classification == AdmissionClass::Unknown)
    {
        if (candidate.Source == "raid_prepull_consumables")
            classification = AdmissionClass::BagConsumable;
        else if (candidate.Source == "adaptive_raid_support")
            classification = AdmissionClass::FriendlyHealing;
        else if (candidate.Key.find("formation") != std::string::npos)
            classification = AdmissionClass::FormationMovement;
        else if (candidate.Key.find("suppress") != std::string::npos)
            classification = AdmissionClass::OffenseSuppression;
    }
    if (classification == AdmissionClass::ControllerCheckpointObservation
        && (!metadata || metadata->ScopeKey != hold.Scope.ScopeKey()))
        classification = AdmissionClass::Unknown;
    switch (classification)
    {
        case AdmissionClass::FormationMovement:
            return Admission::FormationMovement;
        case AdmissionClass::FriendlyHealing:
            return Admission::FriendlyHealing;
        case AdmissionClass::BagConsumable:
            return Admission::BagConsumable;
        case AdmissionClass::OffenseSuppression:
            return Admission::OffenseSuppression;
        case AdmissionClass::DefensiveSurvival:
            return Admission::DefensiveSurvival;
        case AdmissionClass::ControllerCheckpointObservation:
            return Admission::CheckpointObservation;
        case AdmissionClass::Unknown:
            return Admission::Ordinary;
    }
    return Admission::Ordinary;
}

inline void InstallAdmissionPolicy(BotActionArbitration::Kernel& kernel,
    State& hold, Identity identity, uint32 actingActorGuid)
{
    using namespace BotActionArbitration;
    kernel.SetAdmissionPolicy(
        [state = &hold, identity = std::move(identity), actingActorGuid](
            Candidate const& candidate, AdmissionMetadata const* metadata)
        {
            Admission const classification = ClassifyCandidate(
                candidate, metadata, *state);
            return state->AdmitCandidate(identity, actingActorGuid,
                    classification,
                    candidate.ActionPriority == Priority::Survival)
                ? std::string()
                : std::string("controller_route_hold_suppressed");
        });
}

inline bool MarkCheckpointObservationCandidate(
    BotActionArbitration::Kernel& kernel, std::string const& candidateKey,
    State const& hold, uint32 actingActorGuid)
{
    if (hold.CurrentPhase != Phase::Armed
        || actingActorGuid != hold.Scope.ActorGuid)
        return false;
    kernel.SetCandidateAdmission(candidateKey,
        BotActionArbitration::AdmissionClass::ControllerCheckpointObservation,
        hold.Scope.ScopeKey());
    return true;
}

inline bool GateRouteMutation(State& hold, Identity const& identity,
    uint64 prospectiveGeneration)
{
    return hold.PermitRouteAdvance(identity, prospectiveGeneration);
}
}

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
    std::string_view AdmittedRuntimeProfile;
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
    std::string_view ConfigSealSha256;
    std::string_view RequestedSealSha256;
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
    if (input.SelectedProfile != ProfileId
        || input.AdmittedRuntimeProfile != ProfileId
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
    if (!IsLowerHex(input.ConfigSealSha256, 64)
        || input.ConfigSealSha256 != input.RequestedSealSha256)
        return "chainwielder_checkpoint_seal_mismatch";
    BotControllerRouteHold::SourceIdentityComparison const sourceIdentity =
        BotControllerRouteHold::CompareSourceIdentity(
            input.ConfigSourceCommit, input.RequestedSourceCommit,
            input.BinarySourceCommit);
    if (!sourceIdentity.ConfiguredPresent || !sourceIdentity.RequestedPresent)
        return "chainwielder_checkpoint_source_identity_missing";
    if (!sourceIdentity.ConfiguredFormatValid
        || !sourceIdentity.RequestedFormatValid)
        return "chainwielder_checkpoint_source_identity_invalid";
    if (!sourceIdentity.AuthoritiesMatch)
        return "chainwielder_checkpoint_source_authority_mismatch";
    if (!sourceIdentity.BinaryRevisionPresent)
        return "chainwielder_checkpoint_git_revision_missing";
    if (!sourceIdentity.BinaryRevisionFormatValid)
        return "chainwielder_checkpoint_git_revision_invalid";
    if (!sourceIdentity.BinaryRevisionMatchesSource)
        return "chainwielder_checkpoint_git_revision_mismatch";
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
    BotControllerRouteHold::State ControllerRouteHold;
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
