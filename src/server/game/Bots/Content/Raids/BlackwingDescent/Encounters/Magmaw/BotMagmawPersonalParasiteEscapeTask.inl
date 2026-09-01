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

Vector3 EscapeDestination(Vector3 const& actor, Vector3 const& danger,
    float distance)
{
    float dx = actor.X - danger.X;
    float dy = actor.Y - danger.Y;
    float length = std::hypot(dx, dy);
    if (length < 0.01f)
    {
        dx = 1.0f;
        dy = 0.0f;
        length = 1.0f;
    }
    dx /= length;
    dy /= length;
    return { danger.X + dx * distance, danger.Y + dy * distance, actor.Z };
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

    uint64 const nextLocalWaveToken = NextLocalWaveToken;
    uint64 const nextCandidateGeneration = NextCandidateGeneration;
    *this = {};
    NextLocalWaveToken = nextLocalWaveToken;
    NextCandidateGeneration = nextCandidateGeneration;
    ScopeKey = board.CurrentScope.Key();
    AttemptId = board.CurrentScope.AttemptId;
    WipeGeneration = board.CurrentScope.WipeGeneration;
    RouteGeneration = board.CurrentScope.RouteGeneration;
    MapId = board.CurrentScope.MapId;
    InstanceId = board.CurrentScope.InstanceId;
    ActorGuid = actor;
}

inline std::optional<BotNativeAction::Candidate>
MagmawPersonalParasiteEscapeTask::Tick(
    Blackboard const& board, MagmawFacts const& facts,
    ActorSnapshot const& bot, ActorSnapshot const* personalThreat,
    float safeClearance, float arrivalTolerance, bool preemptCasting)
{
    ObserveScope(board, bot.Guid);
    if (facts.Parasites.Active != MagmawTruth::True)
    {
        if (facts.Parasites.Authoritative)
        {
            WaveEnded = true;
            if (Started && State == BotDecision::PersistentTaskState::Running)
                State = BotDecision::PersistentTaskState::Succeeded;
        }
        return std::nullopt;
    }

    bool const observedGenerationAuthoritative =
        facts.Parasites.Generation.Authoritative();
    uint64 observedWave = facts.Parasites.Generation.Value;
    if (!observedGenerationAuthoritative)
        observedWave = WaveGeneration && !WaveEnded
            ? WaveGeneration
            : (uint64{1} << 63) | ++NextLocalWaveToken;
    bool const newWave = !WaveGeneration || WaveEnded;
    if (newWave)
    {
        if (Started)
        {
            Started = false;
            AlternateUsed = false;
            AlternatePending = false;
            Failure = MagmawPersonalParasiteEscapeFailure::None;
            State = BotDecision::PersistentTaskState::Aborted;
        }
        WaveGeneration = observedWave;
        WaveGenerationAuthoritative = observedGenerationAuthoritative;
        WaveEnded = false;
    }
    uint64 const wave = WaveGeneration;

    if (Started && WaveGeneration == wave
        && BotDecision::IsTerminal(State))
        return std::nullopt;

    float const clearance = ParasiteClearance(facts, bot.Position);
    if (Started && State == BotDecision::PersistentTaskState::Running)
    {
        float const distance = Distance2d(bot.Position, Destination);
        if (clearance > BestClearance + 0.5f)
        {
            BestClearance = clearance;
            LastProgressAtMs = board.ObservedAtMs;
            LastProgressRevision = board.Revision;
        }
        if (distance + 0.5f < BestDistance)
        {
            BestDistance = distance;
            LastProgressAtMs = board.ObservedAtMs;
            LastProgressRevision = board.Revision;
        }
        if (clearance >= safeClearance
            || distance <= arrivalTolerance)
        {
            State = BotDecision::PersistentTaskState::Succeeded;
            AlternatePending = false;
            return std::nullopt;
        }
        if (board.ObservedAtMs > LastProgressAtMs
            && board.ObservedAtMs - LastProgressAtMs >= 5000)
        {
            State = BotDecision::PersistentTaskState::Failed;
            Failure = MagmawPersonalParasiteEscapeFailure::NoSemanticProgress;
            AlternatePending = false;
            return std::nullopt;
        }
    }

    MagmawActorFact const* nearest = NearestParasite(facts, bot.Position);
    if (!Started)
    {
        if (!personalThreat || !nearest)
            return std::nullopt;
        Started = true;
        WaveEnded = false;
        WaveGeneration = wave;
        State = BotDecision::PersistentTaskState::Running;
        Failure = MagmawPersonalParasiteEscapeFailure::None;
        DangerGuid = personalThreat->Guid;
        DangerPosition = personalThreat->Position;
        Destination = EscapeDestination(bot.Position, DangerPosition,
            safeClearance);
        PrimaryDestination = Destination;
        CandidateGeneration = ++NextCandidateGeneration;
        if (!CandidateGeneration)
            CandidateGeneration = ++NextCandidateGeneration;
        BestClearance = clearance;
        BestDistance = Distance2d(bot.Position, Destination);
        StartedAtMs = board.ObservedAtMs;
        LastProgressAtMs = board.ObservedAtMs;
        LastProgressRevision = board.Revision;
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
        Destination = EscapeDestination(bot.Position, DangerPosition,
            safeClearance);
        if (SamePoint(Destination, PrimaryDestination))
        {
            State = BotDecision::PersistentTaskState::Failed;
            Failure = MagmawPersonalParasiteEscapeFailure::NoDistinctAlternate;
            AlternatePending = false;
            return std::nullopt;
        }
        AlternateUsed = true;
        AlternatePending = false;
        CandidateGeneration = ++NextCandidateGeneration;
        if (!CandidateGeneration)
            CandidateGeneration = ++NextCandidateGeneration;
        BestDistance = Distance2d(bot.Position, Destination);
        LastProgressAtMs = board.ObservedAtMs;
    }

    if (State != BotDecision::PersistentTaskState::Running
        || AlternatePending)
        return std::nullopt;

    BotNativeAction::Candidate candidate;
    candidate.Id.ScopeKey = board.CurrentScope.Key();
    candidate.Id.Strategy = "adaptive_magmaw";
    candidate.Id.Mechanic = "parasite_contact_evade";
    candidate.Id.Actor = bot.Guid;
    candidate.Id.EventGeneration = CandidateGeneration;
    candidate.ActionPriority = BotActionArbitration::Priority::Survival;
    candidate.Utility = 450.0f;
    candidate.ExpiresAtMs = board.ObservedAtMs + 750;
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
    Vector3 const& destination, std::string_view reason)
{
    if (!IsPermanentNativeRejection(reason) || !Started
        || State != BotDecision::PersistentTaskState::Running
        || ActorGuid != actor || CandidateGeneration != candidateGeneration
        || !SamePoint(Destination, destination))
        return false;
    if (!AlternateUsed)
    {
        AlternatePending = true;
        return true;
    }
    State = BotDecision::PersistentTaskState::Failed;
    Failure = MagmawPersonalParasiteEscapeFailure::
        AlternateNativeRouteRejected;
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
}
