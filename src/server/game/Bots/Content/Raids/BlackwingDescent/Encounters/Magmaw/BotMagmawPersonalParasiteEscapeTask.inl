#include <algorithm>
#include <cmath>
#include <limits>

namespace BotEncounter
{
namespace
{
float Distance2d(Vector3 const& left, Vector3 const& right)
{
    return std::hypot(left.X - right.X, left.Y - right.Y);
}

float ParasiteClearance(MagmawFacts const& facts, Vector3 const& position)
{
    float clearance = std::numeric_limits<float>::max();
    for (MagmawActorFact const& parasite : facts.Parasites.Sources)
        clearance = std::min(clearance,
            Distance2d(position, parasite.Position));
    return clearance;
}

MagmawActorFact const* NearestParasite(MagmawFacts const& facts,
    Vector3 const& position)
{
    MagmawActorFact const* nearest = nullptr;
    float best = std::numeric_limits<float>::max();
    for (MagmawActorFact const& parasite : facts.Parasites.Sources)
    {
        float const distance = Distance2d(position, parasite.Position);
        if (distance < best)
        {
            nearest = &parasite;
            best = distance;
        }
    }
    return nearest;
}

uint32 AuthorityGapMask(Blackboard const& board, MagmawFacts const& facts)
{
    using Gap = MagmawPersonalParasiteAuthorityGap;
    uint32 mask = 0;
    auto add = [&mask](Gap gap) { mask |= uint32(gap); };
    if (facts.ObservationRevision != board.Revision)
        add(Gap::ObservationRevision);
    if (!(facts.Lifecycle == board.CurrentScope))
        add(Gap::LifecycleScope);
    if (!facts.LifecycleAuthoritative)
        add(Gap::LifecycleAuthority);
    if (!facts.ProjectionAuthoritative)
        add(Gap::ProjectionAuthority);
    if (!facts.Parasites.Authoritative)
        add(Gap::ParasiteAuthority);
    if (facts.Parasites.Active == MagmawTruth::True
        && facts.Parasites.Sources.empty())
        add(Gap::ParasiteSource);
    return mask;
}

uint32 LifecycleBit(MagmawPersonalParasiteEscapeLifecycle lifecycle)
{
    return uint32{1} << uint32(lifecycle);
}

}

inline void MagmawParasiteWaveTask::ObserveScope(Blackboard const& board)
{
    if (ScopeKey == board.CurrentScope.Key()
        && AttemptId == board.CurrentScope.AttemptId
        && WipeGeneration == board.CurrentScope.WipeGeneration
        && RouteGeneration == board.CurrentScope.RouteGeneration
        && MapId == board.CurrentScope.MapId
        && InstanceId == board.CurrentScope.InstanceId)
        return;

    uint64 const nextGeneration = NextGeneration;
    *this = {};
    NextGeneration = nextGeneration;
    ScopeKey = board.CurrentScope.Key();
    AttemptId = board.CurrentScope.AttemptId;
    WipeGeneration = board.CurrentScope.WipeGeneration;
    RouteGeneration = board.CurrentScope.RouteGeneration;
    MapId = board.CurrentScope.MapId;
    InstanceId = board.CurrentScope.InstanceId;
}

inline void MagmawParasiteWaveTask::Reconcile(Blackboard const& board,
    MagmawFacts const& facts, bool personalThreatObserved)
{
    ObserveScope(board);
    LastObservedAtMs = board.ObservedAtMs;
    uint32 const authorityGaps = AuthorityGapMask(board, facts);
    if (!authorityGaps)
    {
        AwaitingAuthoritativeFacts = false;
        if (facts.Parasites.Active != MagmawTruth::True)
        {
            Active = false;
            return;
        }
        if (Active)
            return;

        Active = true;
        GenerationAuthoritative =
            facts.Parasites.Generation.Authoritative();
        Generation = GenerationAuthoritative
            ? facts.Parasites.Generation.Value
            : (uint64{1} << 63) | ++NextGeneration;
        if (!Generation)
            Generation = (uint64{1} << 63) | ++NextGeneration;
        CreatedAtMs = board.ObservedAtMs;
        return;
    }

    if (personalThreatObserved && !Active)
    {
        Active = true;
        GenerationAuthoritative = false;
        Generation = (uint64{1} << 63) | ++NextGeneration;
        CreatedAtMs = board.ObservedAtMs;
    }
    if (Active)
        AwaitingAuthoritativeFacts = true;
}

inline void MagmawPersonalParasiteEscapeTask::ObserveScope(
    Blackboard const& board, ObjectGuid actor)
{
    if (ScopeKey == board.CurrentScope.Key()
        && AttemptId == board.CurrentScope.AttemptId
        && WipeGeneration == board.CurrentScope.WipeGeneration
        && RouteGeneration == board.CurrentScope.RouteGeneration
        && MapId == board.CurrentScope.MapId
        && InstanceId == board.CurrentScope.InstanceId
        && ActorGuid == actor)
        return;

    uint64 const nextLocalWaveGeneration = LocalWave.NextGeneration;
    uint64 const nextTaskGeneration = NextTaskGeneration;
    uint64 const nextCandidateGeneration = NextCandidateGeneration;
    *this = {};
    LocalWave.NextGeneration = nextLocalWaveGeneration;
    NextTaskGeneration = nextTaskGeneration;
    NextCandidateGeneration = nextCandidateGeneration;
    ScopeKey = board.CurrentScope.Key();
    AttemptId = board.CurrentScope.AttemptId;
    WipeGeneration = board.CurrentScope.WipeGeneration;
    RouteGeneration = board.CurrentScope.RouteGeneration;
    MapId = board.CurrentScope.MapId;
    InstanceId = board.CurrentScope.InstanceId;
    ActorGuid = actor;
}

inline void MagmawPersonalParasiteEscapeTask::ObserveActorLife(
    Blackboard const& board, ObjectGuid actor, bool alive)
{
    ObserveScope(board, actor);
    if (!ActorLifeObserved)
    {
        ActorLifeObserved = true;
        ActorAlive = alive;
        return;
    }
    if (ActorAlive == alive)
        return;

    ActorAlive = alive;
    ++ActorLifeGeneration;
    if (!alive && Started && !BotDecision::IsTerminal(State))
    {
        State = BotDecision::PersistentTaskState::Aborted;
        AlternatePending = false;
    }
}

inline void MagmawPersonalParasiteEscapeTask::MarkLifecycle(
    MagmawPersonalParasiteEscapeLifecycle lifecycle, uint64 observedAtMs)
{
    Diagnostics.Lifecycle = lifecycle;
    Diagnostics.ObservedLifecycleMask |= LifecycleBit(lifecycle);
    switch (lifecycle)
    {
        case MagmawPersonalParasiteEscapeLifecycle::TaskCreated:
            if (!Diagnostics.CreatedAtMs)
                Diagnostics.CreatedAtMs = observedAtMs;
            break;
        case MagmawPersonalParasiteEscapeLifecycle::
            AwaitingAuthoritativeFacts:
            if (!Diagnostics.AwaitingFactsAtMs)
                Diagnostics.AwaitingFactsAtMs = observedAtMs;
            break;
        case MagmawPersonalParasiteEscapeLifecycle::CandidateBuilt:
            Diagnostics.CandidateBuiltAtMs = observedAtMs;
            break;
        case MagmawPersonalParasiteEscapeLifecycle::Submitted:
            if (!Diagnostics.SubmittedAtMs)
                Diagnostics.SubmittedAtMs = observedAtMs;
            break;
        case MagmawPersonalParasiteEscapeLifecycle::NativeProgress:
            Diagnostics.NativeProgressAtMs = observedAtMs;
            break;
        case MagmawPersonalParasiteEscapeLifecycle::SafeClearance:
        case MagmawPersonalParasiteEscapeLifecycle::Infected:
        case MagmawPersonalParasiteEscapeLifecycle::Failed:
            Diagnostics.TerminalAtMs = observedAtMs;
            break;
        case MagmawPersonalParasiteEscapeLifecycle::Inactive:
            break;
    }
}

inline void MagmawPersonalParasiteEscapeTask::RecordEpisodeTransition(
    Blackboard const& board, MagmawFacts const& facts,
    MagmawParasiteWaveTask const& wave,
    ActorSnapshot const* personalThreat, bool priorEpisodeOpen,
    bool newEpisodeOpen, std::string_view edge,
    uint64 priorTaskGeneration, uint64 priorCandidateGeneration)
{
    MagmawPersonalThreatEpisodeTransition transition;
    transition.Valid = true;
    transition.ActorGuid = ActorGuid.GetCounter();
    transition.ScopeKey = board.CurrentScope.Key();
    transition.RouteNodeId = board.Route.NodeId;
    transition.RouteGeneration = board.CurrentScope.RouteGeneration;
    transition.BoardRevision = board.Revision;
    transition.ObservedAtMs = board.ObservedAtMs;
    transition.AuthorityGapMask = AuthorityGapMask(board, facts);
    transition.FactsAuthoritative = !transition.AuthorityGapMask;
    transition.PersonalThreatPresent = personalThreat != nullptr;
    transition.PersonalThreatGuid = personalThreat
        ? personalThreat->Guid.GetCounter() : 0;
    transition.PriorEpisodeOpen = priorEpisodeOpen;
    transition.NewEpisodeOpen = newEpisodeOpen;
    transition.Edge = edge;
    transition.ParentWaveGeneration = wave.Generation;
    transition.ParentGenerationAuthoritative =
        wave.GenerationAuthoritative;
    transition.PriorTaskGeneration = priorTaskGeneration;
    transition.NewTaskGeneration = TaskGeneration;
    transition.PriorCandidateGeneration = priorCandidateGeneration;
    transition.NewCandidateGeneration = CandidateGeneration;
    if (edge == "falling")
        FallingEpisodeTransition = transition;
    else
        RisingEpisodeTransition = transition;
}

inline std::optional<BotNativeAction::Candidate>
MagmawPersonalParasiteEscapeTask::Tick(
    Blackboard const& board, MagmawFacts const& facts,
    ActorSnapshot const& bot, ActorSnapshot const* personalThreat,
    float safeClearance, float arrivalTolerance, bool preemptCasting,
    MagmawParasiteWaveTask* sharedWave)
{
    ObserveActorLife(board, bot.Guid, bot.Alive);
    if (!bot.Alive)
        return std::nullopt;

    MagmawParasiteWaveTask& wave = sharedWave ? *sharedWave : LocalWave;
    wave.Reconcile(board, facts, personalThreat != nullptr);
    WaveEnded = !wave.Active;

    auto beginTask = [&]()
    {
        Started = true;
        WaveEnded = false;
        WaveGeneration = wave.Generation;
        WaveGenerationAuthoritative = wave.GenerationAuthoritative;
        TaskGeneration = ++NextTaskGeneration;
        if (!TaskGeneration)
            TaskGeneration = ++NextTaskGeneration;
        CandidateGeneration = 0;
        CandidateExpiresAtMs = 0;
        AlternateUsed = false;
        AlternatePending = false;
        Failure = MagmawPersonalParasiteEscapeFailure::None;
        State = BotDecision::PersistentTaskState::Suspended;
        PersonalThreatEpisodeOpen = true;
        DangerGuid = personalThreat->Guid;
        DangerPosition = personalThreat->Position;
        Diagnostics = {};
        Diagnostics.TaskGeneration = TaskGeneration;
        MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle::TaskCreated,
            board.ObservedAtMs);
    };

    if (Started && WaveGeneration != wave.Generation)
    {
        Started = false;
        CandidateGeneration = 0;
        CandidateExpiresAtMs = 0;
        AlternateUsed = false;
        AlternatePending = false;
        Failure = MagmawPersonalParasiteEscapeFailure::None;
        State = BotDecision::PersistentTaskState::Aborted;
        FallingEpisodeTransition = {};
        RisingEpisodeTransition = {};
        RisingEpisodeTransitionPending = false;
    }
    if (!Started)
    {
        WaveGeneration = wave.Generation;
        WaveGenerationAuthoritative = wave.GenerationAuthoritative;
    }
    if (!Started && personalThreat && wave.Active)
        beginTask();
    if (Started && HasParasiticInfection(bot)
        && !BotDecision::IsTerminal(State))
    {
        State = BotDecision::PersistentTaskState::Failed;
        Failure = MagmawPersonalParasiteEscapeFailure::
            InfectedBeforeClearance;
        AlternatePending = false;
        RisingEpisodeTransitionPending = false;
        MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle::Infected,
            board.ObservedAtMs);
        return std::nullopt;
    }

    uint32 const authorityGaps = AuthorityGapMask(board, facts);
    if (authorityGaps)
    {
        if (Started && !BotDecision::IsTerminal(State))
        {
            State = BotDecision::PersistentTaskState::Suspended;
            Diagnostics.AuthorityGapMask = authorityGaps;
            MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle::
                AwaitingAuthoritativeFacts, board.ObservedAtMs);
        }
        return std::nullopt;
    }
    Diagnostics.AuthorityGapMask = 0;
    if (facts.Parasites.Active != MagmawTruth::True)
    {
        WaveEnded = true;
        if (Started && !BotDecision::IsTerminal(State))
        {
            State = BotDecision::PersistentTaskState::Succeeded;
            MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle::
                SafeClearance, board.ObservedAtMs);
        }
        return std::nullopt;
    }

    // A terminal child is a tombstone for its current personal-threat
    // episode. Only an authoritative absence closes that episode; the next
    // presence can then create one new child even if the shared wave remains
    // on its provisional generation. Continuous presence and hazard GUID
    // churn cannot rearm it.
    if (Started && BotDecision::IsTerminal(State))
    {
        if (!personalThreat && PersonalThreatEpisodeOpen)
        {
            uint64 const priorTaskGeneration = TaskGeneration;
            uint64 const priorCandidateGeneration = CandidateGeneration;
            PersonalThreatEpisodeOpen = false;
            RecordEpisodeTransition(board, facts, wave, nullptr, true,
                false, "falling", priorTaskGeneration,
                priorCandidateGeneration);
            RisingEpisodeTransition = {};
        }
        else if (personalThreat && !PersonalThreatEpisodeOpen && wave.Active)
        {
            RisingPriorTaskGeneration = TaskGeneration;
            RisingPriorCandidateGeneration = CandidateGeneration;
            RisingEpisodeTransitionPending = true;
            beginTask();
        }
    }
    if (!Started || BotDecision::IsTerminal(State))
        return std::nullopt;

    if (State == BotDecision::PersistentTaskState::Suspended)
        State = BotDecision::PersistentTaskState::Running;

    float const clearance = ParasiteClearance(facts, bot.Position);
    if (CandidateGeneration
        && State == BotDecision::PersistentTaskState::Running)
    {
        float const distance = Distance2d(bot.Position, Destination);
        if (clearance > BestClearance + 0.5f)
        {
            BestClearance = clearance;
            LastProgressAtMs = board.ObservedAtMs;
            LastProgressRevision = board.Revision;
            if (Diagnostics.SubmittedAtMs)
                MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle::
                    NativeProgress, board.ObservedAtMs);
        }
        if (distance + 0.5f < BestDistance)
        {
            BestDistance = distance;
            LastProgressAtMs = board.ObservedAtMs;
            LastProgressRevision = board.Revision;
            if (Diagnostics.SubmittedAtMs)
                MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle::
                    NativeProgress, board.ObservedAtMs);
        }
        if (clearance >= safeClearance
            || distance <= arrivalTolerance)
        {
            State = BotDecision::PersistentTaskState::Succeeded;
            AlternatePending = false;
            if (!personalThreat && PersonalThreatEpisodeOpen)
            {
                uint64 const priorTaskGeneration = TaskGeneration;
                uint64 const priorCandidateGeneration = CandidateGeneration;
                PersonalThreatEpisodeOpen = false;
                RecordEpisodeTransition(board, facts, wave, nullptr, true,
                    false, "falling", priorTaskGeneration,
                    priorCandidateGeneration);
                RisingEpisodeTransition = {};
            }
            MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle::
                SafeClearance, board.ObservedAtMs);
            return std::nullopt;
        }
        if (board.ObservedAtMs > LastProgressAtMs
            && board.ObservedAtMs - LastProgressAtMs >= 5000)
        {
            State = BotDecision::PersistentTaskState::Failed;
            Failure = MagmawPersonalParasiteEscapeFailure::NoSemanticProgress;
            AlternatePending = false;
            MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle::Failed,
                board.ObservedAtMs);
            return std::nullopt;
        }
    }

    MagmawActorFact const* nearest = NearestParasite(facts, bot.Position);
    if (!CandidateGeneration)
    {
        if (!nearest)
        {
            State = BotDecision::PersistentTaskState::Suspended;
            Diagnostics.AuthorityGapMask = uint32(
                MagmawPersonalParasiteAuthorityGap::ParasiteSource);
            MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle::
                AwaitingAuthoritativeFacts, board.ObservedAtMs);
            return std::nullopt;
        }
        Destination = MagmawMoveAwayDestination(bot.Position, bot.Facing,
            DangerPosition, safeClearance);
        PrimaryDestination = Destination;
        CandidateGeneration = ++NextCandidateGeneration;
        if (!CandidateGeneration)
            CandidateGeneration = ++NextCandidateGeneration;
        CandidateExpiresAtMs = board.ObservedAtMs + 750;
        BestClearance = clearance;
        BestDistance = Distance2d(bot.Position, Destination);
        StartedAtMs = board.ObservedAtMs;
        LastProgressAtMs = board.ObservedAtMs;
        LastProgressRevision = board.Revision;
        MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle::CandidateBuilt,
            board.ObservedAtMs);
        if (RisingEpisodeTransitionPending)
        {
            RecordEpisodeTransition(board, facts, wave, personalThreat,
                false, true, "rising", RisingPriorTaskGeneration,
                RisingPriorCandidateGeneration);
            RisingEpisodeTransitionPending = false;
        }
    }
    else if (AlternatePending)
    {
        if (!nearest)
        {
            State = BotDecision::PersistentTaskState::Succeeded;
            AlternatePending = false;
            return std::nullopt;
        }
        DangerGuid = nearest->Guid;
        DangerPosition = nearest->Position;
        Destination = MagmawMoveAwayDestination(bot.Position, bot.Facing,
            DangerPosition, safeClearance);
        if (SamePoint(Destination, PrimaryDestination))
        {
            State = BotDecision::PersistentTaskState::Failed;
            Failure = MagmawPersonalParasiteEscapeFailure::NoDistinctAlternate;
            AlternatePending = false;
            MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle::Failed,
                board.ObservedAtMs);
            return std::nullopt;
        }
        AlternateUsed = true;
        AlternatePending = false;
        CandidateGeneration = ++NextCandidateGeneration;
        if (!CandidateGeneration)
            CandidateGeneration = ++NextCandidateGeneration;
        CandidateExpiresAtMs = board.ObservedAtMs + 750;
        Diagnostics.CandidateKey.clear();
        BestDistance = Distance2d(bot.Position, Destination);
        LastProgressAtMs = board.ObservedAtMs;
        MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle::CandidateBuilt,
            board.ObservedAtMs);
    }

    if (State != BotDecision::PersistentTaskState::Running
        || AlternatePending)
        return std::nullopt;

    // The candidate lease is frame-local; the running child and its progress
    // clock are semantic state. Refresh only this same authoritative child
    // after all terminal/progress checks have passed, so a live native path
    // can be retained without inventing a new route or rearming the task.
    if (CandidateGeneration)
        CandidateExpiresAtMs = board.ObservedAtMs + 750;

    BotNativeAction::Candidate candidate;
    candidate.Id.ScopeKey = board.CurrentScope.Key();
    candidate.Id.Strategy = "adaptive_magmaw";
    candidate.Id.Mechanic = "parasite_contact_evade";
    candidate.Id.Actor = bot.Guid;
    candidate.Id.EventGeneration = CandidateGeneration;
    candidate.ActionPriority = BotActionArbitration::Priority::Survival;
    candidate.Utility = 450.0f;
    candidate.ExpiresAtMs = CandidateExpiresAtMs;
    candidate.Action = BotNativeAction::Move{ Destination.X, Destination.Y,
        Destination.Z, "parasite_contact_evade", preemptCasting };
    if (BotNativeAction::Move* move =
            std::get_if<BotNativeAction::Move>(&candidate.Action))
        move->HazardEscape = BotWorldMovement::HazardEscapeBasis{
            DangerGuid.GetRawValue(), DangerPosition.X, DangerPosition.Y,
            DangerPosition.Z };
    return candidate;
}

inline bool MagmawPersonalParasiteEscapeTask::ObserveNativeOutcome(
    ObjectGuid actor, uint64 candidateGeneration,
    Vector3 const& destination, std::string_view candidateKey,
    BotActionArbitration::Phase phase, std::string_view reason,
    uint64 observedAtMs)
{
    if (!Started || State != BotDecision::PersistentTaskState::Running
        || ActorGuid != actor || CandidateGeneration != candidateGeneration
        || !SamePoint(Destination, destination))
        return false;
    Diagnostics.CandidateKey = candidateKey;
    Diagnostics.LastNativeReason = reason;
    ++Diagnostics.NativeOutcomeCount;
    if (phase == BotActionArbitration::Phase::Submitted
        || phase == BotActionArbitration::Phase::Started
        || phase == BotActionArbitration::Phase::Progressed
        || phase == BotActionArbitration::Phase::Completed)
        MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle::Submitted,
            observedAtMs);
    if (!IsPermanentNativeRejection(reason))
        return false;
    if (!AlternateUsed)
    {
        AlternatePending = true;
        return true;
    }
    State = BotDecision::PersistentTaskState::Failed;
    Failure = MagmawPersonalParasiteEscapeFailure::
        AlternateNativeRouteRejected;
    MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle::Failed,
        observedAtMs);
    return true;
}

inline bool MagmawPersonalParasiteEscapeTask::IsPermanentNativeRejection(
    std::string_view reason)
{
    return reason == "route_destination_endpoint_mismatch"
        || reason == "route_destination_unreachable"
        || reason == "route_destination_partial_path"
        || reason == "route_destination_missing_mmap";
}

inline bool MagmawPersonalParasiteEscapeTask::SamePoint(
    Vector3 const& left, Vector3 const& right)
{
    return std::fabs(left.X - right.X) <= 0.001f
        && std::fabs(left.Y - right.Y) <= 0.001f
        && std::fabs(left.Z - right.Z) <= 0.001f;
}

inline bool MagmawPersonalParasiteEscapeTask::HasParasiticInfection(
    ActorSnapshot const& actor)
{
    for (AuraSnapshot const& aura : actor.Auras)
        if (aura.SpellId == 78097 || aura.SpellId == 78941
            || aura.SpellId == 91913 || aura.SpellId == 94678
            || aura.SpellId == 94679)
            return true;
    return false;
}

inline char const* ToString(
    MagmawPersonalParasiteEscapeLifecycle value)
{
    switch (value)
    {
        case MagmawPersonalParasiteEscapeLifecycle::Inactive:
            return "inactive";
        case MagmawPersonalParasiteEscapeLifecycle::TaskCreated:
            return "task_created";
        case MagmawPersonalParasiteEscapeLifecycle::
            AwaitingAuthoritativeFacts:
            return "awaiting_facts";
        case MagmawPersonalParasiteEscapeLifecycle::CandidateBuilt:
            return "candidate_built";
        case MagmawPersonalParasiteEscapeLifecycle::Submitted:
            return "submitted";
        case MagmawPersonalParasiteEscapeLifecycle::NativeProgress:
            return "native_progress";
        case MagmawPersonalParasiteEscapeLifecycle::SafeClearance:
            return "safe_clearance";
        case MagmawPersonalParasiteEscapeLifecycle::Infected:
            return "infected";
        case MagmawPersonalParasiteEscapeLifecycle::Failed:
            return "failed";
    }
    return "unknown";
}

inline char const* ToString(MagmawPersonalParasiteEscapeFailure value)
{
    switch (value)
    {
        case MagmawPersonalParasiteEscapeFailure::None:
            return "none";
        case MagmawPersonalParasiteEscapeFailure::InfectedBeforeClearance:
            return "infected_before_clearance";
        case MagmawPersonalParasiteEscapeFailure::NoDistinctAlternate:
            return "no_distinct_alternate";
        case MagmawPersonalParasiteEscapeFailure::NoSemanticProgress:
            return "no_semantic_progress";
        case MagmawPersonalParasiteEscapeFailure::
            AlternateNativeRouteRejected:
            return "alternate_native_route_rejected";
    }
    return "unknown";
}
}
