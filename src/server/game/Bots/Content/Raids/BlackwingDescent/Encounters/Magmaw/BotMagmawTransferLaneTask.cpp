#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneTask.h"

#include <algorithm>
#include <cmath>
#include <initializer_list>

namespace BotEncounter
{
namespace
{
constexpr float RangedStackDistance = 30.0f;
constexpr float RangedStackLateralOffset = 24.0f;

bool AllTrue(std::initializer_list<bool> values)
{
    return std::all_of(values.begin(), values.end(),
        [](bool value) { return value; });
}

bool SameEncounter(NativeEncounterLifecycle const& left,
    NativeEncounterLifecycle const& right)
{
    return left.Id == right.Id && left.BossId == right.BossId
        && left.BossEntry == right.BossEntry
        && left.BossGuid == right.BossGuid && left.State == right.State
        && left.ServerEpoch == right.ServerEpoch
        && left.InstanceLifecycleEpoch == right.InstanceLifecycleEpoch
        && left.AttemptEpoch == right.AttemptEpoch
        && left.EncounterEpoch == right.EncounterEpoch
        && left.Authoritative == right.Authoritative;
}

bool SameEpisodeContract(MagmawTransferLaneEpisode const& left,
    MagmawTransferLaneEpisode const& right)
{
    auto const& a = left.Id;
    auto const& b = right.Id;
    return a.Lifecycle == b.Lifecycle
        && SameEncounter(a.Encounter, b.Encounter)
        && a.RaidPlanGeneration == b.RaidPlanGeneration
        && a.RosterGeneration == b.RosterGeneration
        && a.FireMageAssignmentGeneration
            == b.FireMageAssignmentGeneration
        && a.HunterAssignmentGeneration == b.HunterAssignmentGeneration
        && a.MechanicGeneration == b.MechanicGeneration
        && left.FireMageGuid == right.FireMageGuid
        && left.HunterGuid == right.HunterGuid;
}

float Distance2d(Vector3 const& left, Vector3 const& right)
{
    return std::hypot(left.X - right.X, left.Y - right.Y);
}

MagmawRaidAssignment const* Assignment(MagmawRaidPlan const& plan,
    MagmawRaidAssignmentSlot slot)
{
    MagmawRaidAssignment const* value = plan.FindAssignment(slot);
    return value && !value->AssigneeGuid.IsEmpty() ? value : nullptr;
}

ActorSnapshot const* PlayerObservation(Blackboard const& board,
    ObjectGuid guid)
{
    auto itr = std::find_if(board.Players.begin(), board.Players.end(),
        [guid](ActorSnapshot const& actor)
        {
            return actor.Guid == guid && actor.Kind == ActorKind::Player;
        });
    return itr == board.Players.end() ? nullptr : &*itr;
}

std::optional<MagmawTransferLaneEpisode> DesiredEpisode(
    MagmawFacts const& facts, Blackboard const& board,
    MagmawRaidPlan const& plan)
{
    if (!AllTrue({ plan.Authoritative, facts.LifecycleAuthoritative,
        facts.NativeEncounter.has_value(),
        facts.ObservationRevision == board.Revision,
        plan.Lifecycle == facts.Lifecycle,
        facts.Pillar.Active == MagmawTruth::True,
        facts.Pillar.Authoritative,
        facts.Pillar.Generation.Authoritative(), facts.Bosses.size() == 1,
        !board.Route.NavigationHints.empty() }))
        return std::nullopt;

    MagmawRaidAssignment const* mage = Assignment(plan,
        MagmawRaidAssignmentSlot::FireMageBaiter);
    MagmawRaidAssignment const* hunter = Assignment(plan,
        MagmawRaidAssignmentSlot::MarksmanshipHunterBaiter);
    if (!AllTrue({ mage != nullptr, hunter != nullptr,
            !mage || !hunter || mage->AssigneeGuid != hunter->AssigneeGuid }))
        return std::nullopt;
    ActorSnapshot const* owner = PlayerObservation(board,
        mage->AssigneeGuid);
    if (!owner || !owner->Alive)
        return std::nullopt;

    Vector3 const& boss = facts.Bosses.front().Position;
    Vector3 const& roomSide = board.Route.NavigationHints.front();
    float dx = roomSide.X - boss.X;
    float dy = roomSide.Y - boss.Y;
    float const length = std::hypot(dx, dy);
    if (!std::isfinite(length) || length < 1.0f)
        return std::nullopt;
    dx /= length;
    dy /= length;
    Vector3 const left = { boss.X + dx * RangedStackDistance
            - dy * RangedStackLateralOffset,
        boss.Y + dy * RangedStackDistance
            + dx * RangedStackLateralOffset, roomSide.Z };
    Vector3 const right = { boss.X + dx * RangedStackDistance
            + dy * RangedStackLateralOffset,
        boss.Y + dy * RangedStackDistance
            - dx * RangedStackLateralOffset, roomSide.Z };
    float const leftDistance = Distance2d(owner->Position, left);
    float const rightDistance = Distance2d(owner->Position, right);
    MagmawTransferLaneDirection direction;
    if (leftDistance + MagmawTransferLaneTaskShadow::ArrivalTolerance
        < rightDistance)
        direction = MagmawTransferLaneDirection::Right;
    else if (rightDistance + MagmawTransferLaneTaskShadow::ArrivalTolerance
        < leftDistance)
        direction = MagmawTransferLaneDirection::Left;
    else
        direction = board.CurrentScope.AttemptId % 2
            ? MagmawTransferLaneDirection::Right
            : MagmawTransferLaneDirection::Left;

    MagmawTransferLaneEpisode episode;
    episode.Id.Lifecycle = facts.Lifecycle;
    episode.Id.Encounter = *facts.NativeEncounter;
    episode.Id.RaidPlanGeneration = plan.Generation;
    episode.Id.RosterGeneration = plan.RosterGeneration;
    episode.Id.FireMageAssignmentGeneration = mage->Epoch;
    episode.Id.HunterAssignmentGeneration = hunter->Epoch;
    episode.Id.MechanicGeneration = facts.Pillar.Generation.Value;
    episode.FireMageGuid = mage->AssigneeGuid;
    episode.HunterGuid = hunter->AssigneeGuid;
    episode.Direction = direction;
    episode.Destination = direction == MagmawTransferLaneDirection::Left
        ? left : right;
    episode.CreatedAtRevision = board.Revision;
    return episode;
}

MagmawTransferLaneActorObservation const* FindActor(
    std::vector<MagmawTransferLaneActorObservation> const& actors,
    ObjectGuid guid)
{
    auto itr = std::find_if(actors.begin(), actors.end(),
        [guid](MagmawTransferLaneActorObservation const& actor)
        {
            return actor.Guid == guid;
        });
    return itr == actors.end() ? nullptr : &*itr;
}

MagmawTransferLaneTask* FindTask(
    std::vector<MagmawTransferLaneTask>& tasks, ObjectGuid guid)
{
    auto itr = std::find_if(tasks.begin(), tasks.end(),
        [guid](MagmawTransferLaneTask const& task)
        {
            return task.Id.ActorGuid == guid;
        });
    return itr == tasks.end() ? nullptr : &*itr;
}

void RetireTask(MagmawTransferLaneTask task,
    MagmawTransferLaneRetirement reason, uint64 revision,
    std::vector<MagmawRetiredTransferLaneTask>& retired)
{
    if (!BotDecision::IsTerminal(task.State))
        task.State = BotDecision::PersistentTaskState::Aborted;
    task.Suspension = BotDecision::PersistentTaskSuspension::None;
    retired.push_back({ std::move(task), reason, revision });
    if (retired.size() > 16)
        retired.erase(retired.begin(), retired.begin()
            + (retired.size() - 16));
}

MagmawTransferLaneRetirement EpisodeRetirement(
    MagmawTransferLaneEpisode const& current,
    MagmawTransferLaneEpisode const& desired)
{
    if (!(current.Id.Lifecycle == desired.Id.Lifecycle)
        || !SameEncounter(current.Id.Encounter, desired.Id.Encounter))
        return MagmawTransferLaneRetirement::EncounterLifecycleChanged;
    if (current.FireMageGuid != desired.FireMageGuid
        || current.HunterGuid != desired.HunterGuid
        || current.Id.FireMageAssignmentGeneration
            != desired.Id.FireMageAssignmentGeneration
        || current.Id.HunterAssignmentGeneration
            != desired.Id.HunterAssignmentGeneration)
        return MagmawTransferLaneRetirement::AssignmentChanged;
    if (current.Id.MechanicGeneration != desired.Id.MechanicGeneration)
        return MagmawTransferLaneRetirement::MechanicGenerationAdvanced;
    return MagmawTransferLaneRetirement::RaidPlanChanged;
}

void RetireEpisodeTasks(std::vector<MagmawTransferLaneTask>& tasks,
    std::vector<MagmawRetiredTransferLaneTask>& retired,
    MagmawTransferLaneRetirement reason, uint64 revision)
{
    for (MagmawTransferLaneTask const& task : tasks)
        RetireTask(task, reason, revision, retired);
    tasks.clear();
}

void ReconcileEpisode(
    std::optional<MagmawTransferLaneEpisode>& episode,
    std::vector<MagmawTransferLaneTask>& tasks,
    std::vector<MagmawRetiredTransferLaneTask>& retired,
    uint64& nextEpisodeGeneration,
    std::optional<MagmawTransferLaneEpisode> desired,
    MagmawFacts const& facts, MagmawRaidPlan const& plan,
    Blackboard const& board)
{
    bool const lifecycleChanged = episode
        && (!(episode->Id.Lifecycle == facts.Lifecycle)
            || (facts.LifecycleAuthoritative && facts.NativeEncounter
                && !SameEncounter(episode->Id.Encounter,
                    *facts.NativeEncounter)));
    if (lifecycleChanged)
    {
        RetireEpisodeTasks(tasks, retired,
            MagmawTransferLaneRetirement::EncounterLifecycleChanged,
            board.Revision);
        episode.reset();
    }
    if (episode && desired && !SameEpisodeContract(*episode, *desired))
    {
        RetireEpisodeTasks(tasks, retired,
            EpisodeRetirement(*episode, *desired), board.Revision);
        episode.reset();
    }
    bool const planChanged = episode && !desired
        && (episode->Id.RaidPlanGeneration != plan.Generation
            || episode->Id.RosterGeneration != plan.RosterGeneration);
    if (planChanged)
    {
        RetireEpisodeTasks(tasks, retired,
            MagmawTransferLaneRetirement::RaidPlanChanged, board.Revision);
        episode.reset();
    }
    if (!episode && desired)
    {
        desired->Id.EpisodeGeneration = ++nextEpisodeGeneration;
        episode = *desired;
    }
}

void ReconcileActorTask(ObjectGuid guid,
    MagmawTransferLaneEpisode const& episode,
    std::vector<MagmawTransferLaneTask>& tasks,
    std::vector<MagmawRetiredTransferLaneTask>& retired,
    uint64& nextTaskGeneration,
    MagmawTransferLaneActorObservation const* actor,
    Blackboard const& board)
{
    MagmawTransferLaneTask* task = FindTask(tasks, guid);
    bool const lifeChanged = AllTrue({ task != nullptr, actor != nullptr,
        !actor || actor->Life.Authoritative,
        !task || !actor || !(task->Id.ActorLife == actor->Life) });
    bool const died = AllTrue({ task != nullptr, actor != nullptr,
        !actor || !actor->Alive });
    if (lifeChanged || died)
    {
        RetireTask(*task, died ? MagmawTransferLaneRetirement::ActorDied
            : MagmawTransferLaneRetirement::ActorLifeChanged,
            board.Revision, retired);
        tasks.erase(std::remove_if(tasks.begin(), tasks.end(),
            [guid](MagmawTransferLaneTask const& row)
            {
                return row.Id.ActorGuid == guid;
            }), tasks.end());
        task = nullptr;
    }
    if (AllTrue({ task == nullptr, actor != nullptr,
            !actor || actor->Alive, !actor || actor->Life.Authoritative,
            !actor || actor->PositionObserved }))
    {
        MagmawTransferLaneTask created;
        created.Id.Episode = episode.Id;
        created.Id.ActorGuid = guid;
        created.Id.ActorLife = actor->Life;
        created.Id.TaskGeneration = ++nextTaskGeneration;
        created.Destination = episode.Destination;
        created.InitialDistance = Distance2d(actor->Position,
            created.Destination);
        created.BestDistance = created.InitialDistance;
        created.LastDistance = created.InitialDistance;
        created.StartedAtMs = board.ObservedAtMs;
        created.LastProgressAtMs = board.ObservedAtMs;
        created.LastObservedAtMs = board.ObservedAtMs;
        created.ProgressRevision = board.Revision;
        tasks.push_back(std::move(created));
        task = &tasks.back();
    }
    if (!task)
        return;
    if (actor)
        MagmawTransferLaneTaskRunner::Observe(*task, *actor, board);
    else
    {
        task->State = BotDecision::PersistentTaskState::Suspended;
        task->Suspension = BotDecision::PersistentTaskSuspension::
            ObservationUnavailable;
        if (!task->SuspendedAtMs)
            task->SuspendedAtMs = board.ObservedAtMs;
    }
}
}

std::shared_ptr<MagmawTransferLaneTaskShadow const>
MagmawTransferLaneTaskShadow::Reconcile(
    std::shared_ptr<MagmawTransferLaneTaskShadow const> const& current,
    MagmawFacts const& facts, Blackboard const& board,
    MagmawRaidPlan const& plan,
    std::vector<MagmawTransferLaneActorObservation> const& actors)
{
    if (current && current->_sourceRevision == facts.ObservationRevision)
        return current;
    std::unique_ptr<MagmawTransferLaneTaskShadow> next(
        new MagmawTransferLaneTaskShadow());
    if (current)
        *next = *current;
    next->_sourceRevision = facts.ObservationRevision;

    std::optional<MagmawTransferLaneEpisode> desired = DesiredEpisode(
        facts, board, plan);
    ReconcileEpisode(next->_episode, next->_tasks, next->_retired,
        next->_nextEpisodeGeneration, std::move(desired), facts, plan, board);
    if (!next->_episode)
        return std::shared_ptr<MagmawTransferLaneTaskShadow const>(
            next.release());

    for (ObjectGuid guid : { next->_episode->FireMageGuid,
        next->_episode->HunterGuid })
        ReconcileActorTask(guid, *next->_episode, next->_tasks,
            next->_retired, next->_nextTaskGeneration,
            FindActor(actors, guid), board);
    return std::shared_ptr<MagmawTransferLaneTaskShadow const>(next.release());
}

char const* ToString(MagmawTransferLaneDirection value)
{
    switch (value)
    {
        case MagmawTransferLaneDirection::Left: return "left";
        case MagmawTransferLaneDirection::Right: return "right";
        default: return "none";
    }
}

char const* ToString(MagmawTransferLaneFailure value)
{
    return value == MagmawTransferLaneFailure::NoSemanticProgress
        ? "no_semantic_progress" : "none";
}

char const* ToString(MagmawTransferLaneNativeDisposition value)
{
    switch (value)
    {
        case MagmawTransferLaneNativeDisposition::PlannerRejected:
            return "planner_rejected";
        case MagmawTransferLaneNativeDisposition::Retained:
            return "retained";
        case MagmawTransferLaneNativeDisposition::Submitted:
            return "submitted";
        case MagmawTransferLaneNativeDisposition::
                ReachedRequestedEndpointEvidence:
            return "reached_requested_endpoint_evidence";
        case MagmawTransferLaneNativeDisposition::
                ReachedProjectedEndPolyEvidence:
            return "reached_projected_end_poly_evidence";
        default: return "none";
    }
}

char const* ToString(MagmawTransferLaneRetirement value)
{
    switch (value)
    {
        case MagmawTransferLaneRetirement::EncounterLifecycleChanged:
            return "encounter_lifecycle_changed";
        case MagmawTransferLaneRetirement::RaidPlanChanged:
            return "raid_plan_changed";
        case MagmawTransferLaneRetirement::AssignmentChanged:
            return "assignment_changed";
        case MagmawTransferLaneRetirement::MechanicGenerationAdvanced:
            return "mechanic_generation_advanced";
        case MagmawTransferLaneRetirement::ActorLifeChanged:
            return "actor_life_changed";
        case MagmawTransferLaneRetirement::ActorDied:
            return "actor_died";
        default: return "none";
    }
}

char const* ToString(BotDecision::PersistentTaskState value)
{
    switch (value)
    {
        case BotDecision::PersistentTaskState::Running: return "running";
        case BotDecision::PersistentTaskState::Suspended: return "suspended";
        case BotDecision::PersistentTaskState::Succeeded: return "succeeded";
        case BotDecision::PersistentTaskState::Failed: return "failed";
        case BotDecision::PersistentTaskState::Aborted: return "aborted";
    }
    return "unknown";
}

char const* ToString(BotDecision::PersistentTaskSuspension value)
{
    switch (value)
    {
        case BotDecision::PersistentTaskSuspension::ObservationUnavailable:
            return "observation_unavailable";
        case BotDecision::PersistentTaskSuspension::SafetyPreempted:
            return "safety_preempted";
        case BotDecision::PersistentTaskSuspension::MovementLeaseExpired:
            return "movement_lease_expired";
        default: return "none";
    }
}
}
