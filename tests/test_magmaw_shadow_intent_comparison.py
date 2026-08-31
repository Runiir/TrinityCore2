from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = [
    "-I", str(ROOT / "src/server/game"),
    "-I", str(ROOT / "src/server/game/Entities/Object"),
    "-I", str(ROOT / "src/common"),
    "-I", str(ROOT / "src/common/Utilities"),
    "-I", str(ROOT / "src/common/Logging"),
    "-I", str(ROOT / "src/common/Debugging"),
]


def test_magmaw_shadow_intent_comparison_fixture(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_shadow_intent_comparison.cpp"
    binary = tmp_path / "magmaw_shadow_intent_comparison"
    source.write_text(r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneIntent.h"

#include <cassert>
#include <string>

using namespace BotEncounter;
using Outcome = MagmawTransferLaneIntentComparisonOutcome;
using Divergence = MagmawTransferLaneIntentDivergence;
using State = BotDecision::PersistentTaskState;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

static ObjectGuid PlayerGuid(uint32 counter)
{
    return ObjectGuid(HighGuid::Player, counter);
}

static BotNativeAction::Candidate MoveCandidate(uint32 actor, float x,
    float y, bool preemptCasting = false)
{
    BotNativeAction::Candidate candidate;
    candidate.Id.Actor = PlayerGuid(actor);
    candidate.Action = BotNativeAction::Move{ x, y, 210.0f, "fixture",
        preemptCasting };
    return candidate;
}

static MagmawTransferLaneTask RunningTask()
{
    MagmawTransferLaneTask task;
    task.Id.Episode.Lifecycle = { "cohort", 7, 2, 5, "magmaw", 669,
        23, "blackwing_descent.magmaw", 91, 4 };
    task.Id.ActorGuid = PlayerGuid(300);
    task.Id.TaskGeneration = 44;
    task.Destination = { 11.0f, -22.0f, 210.0f };
    task.State = State::Running;
    return task;
}

int main()
{
    // The sink retains every proposal and performs no selection.
    BotDecision::BotIntentSink sink;
    BotNativeAction::Candidate first = MoveCandidate(1, 1.0f, 2.0f);
    BotNativeAction::Candidate second = MoveCandidate(2, 3.0f, 4.0f);
    sink.Propose(first);
    sink.Propose(second);
    assert(sink.Proposals().size() == 2);
    assert(sink.Proposals()[0].Id.Actor == PlayerGuid(1));
    assert(sink.Proposals()[1].Id.Actor == PlayerGuid(2));

    // Running emits one stable actor/task-generation identity and copies the
    // exact immutable task destination into an ordinary movement candidate.
    MagmawTransferLaneTask task = RunningTask();
    BotDecision::BotIntentSink emitted;
    EmitMagmawTransferLaneTaskIntent(task, emitted);
    assert(emitted.Proposals().size() == 1);
    BotNativeAction::Candidate const candidate = emitted.Proposals().front();
    assert(candidate.Id.Actor == PlayerGuid(300));
    assert(candidate.Id.EventGeneration == 44);
    assert(candidate.Resources() == BotActionArbitration::Uses(
        BotActionArbitration::Resource::Movement));
    auto const* destination = std::get_if<BotNativeAction::Move>(
        &candidate.Action);
    assert(destination && destination->X == 11.0f
        && destination->Y == -22.0f && destination->Z == 210.0f);
    task.Destination = { 99.0f, 98.0f, 97.0f };
    assert(destination->X == 11.0f && destination->Y == -22.0f
        && destination->Z == 210.0f);

    for (State state : { State::Suspended, State::Succeeded, State::Failed,
        State::Aborted })
    {
        task.State = state;
        BotDecision::BotIntentSink suppressed;
        EmitMagmawTransferLaneTaskIntent(task, suppressed);
        assert(suppressed.Proposals().empty());
    }

    std::vector<BotNativeAction::Candidate> none;
    auto comparison = CompareMagmawTransferLaneIntents(none, std::nullopt);
    assert(comparison.Outcome == Outcome::NeitherPresent);

    std::vector<BotNativeAction::Candidate> one{
        MoveCandidate(300, 11.0f, -22.0f) };
    comparison = CompareMagmawTransferLaneIntents(one, std::nullopt);
    assert(comparison.Outcome == Outcome::ShadowOnly);

    std::optional<BotNativeAction::Candidate> legacy =
        MoveCandidate(300, 11.0f, -22.0f);
    comparison = CompareMagmawTransferLaneIntents(none, legacy);
    assert(comparison.Outcome == Outcome::LegacyOnly);

    comparison = CompareMagmawTransferLaneIntents(one, legacy);
    assert(comparison.Outcome == Outcome::Equivalent);
    assert(comparison.Divergences == 0);

    BotNativeAction::Candidate differentAction = *legacy;
    differentAction.Action = BotNativeAction::DirectionalMobility{
        11.0f, -22.0f, 210.0f, 1953,
        BotNativeAction::DirectionalMobilityFacing::Forward, "fixture" };
    comparison = CompareMagmawTransferLaneIntents(one, differentAction);
    assert(comparison.Outcome == Outcome::Divergent);
    assert(comparison.Has(Divergence::ActionKind));

    BotNativeAction::Candidate differentActor = *legacy;
    differentActor.Id.Actor = PlayerGuid(400);
    comparison = CompareMagmawTransferLaneIntents(one, differentActor);
    assert(comparison.Has(Divergence::Actor));

    BotNativeAction::Candidate differentResource =
        MoveCandidate(300, 11.0f, -22.0f, true);
    comparison = CompareMagmawTransferLaneIntents(one, differentResource);
    assert(comparison.Has(Divergence::MovementResource));

    BotNativeAction::Candidate differentDestination =
        MoveCandidate(300,
            11.0f + MagmawTransferLaneIntentDestinationTolerance2d + 0.01f,
            -22.0f);
    comparison = CompareMagmawTransferLaneIntents(one,
        differentDestination);
    assert(comparison.Has(Divergence::Destination2d));
    BotNativeAction::Candidate withinTolerance = MoveCandidate(300,
        11.0f + MagmawTransferLaneIntentDestinationTolerance2d, -22.0f);
    comparison = CompareMagmawTransferLaneIntents(one, withinTolerance);
    assert(comparison.Outcome == Outcome::Equivalent);

    // Movement-resource actions without a supported endpoint projection must
    // never silently compare equivalent. NativeDescent deliberately remains
    // outside this Magmaw point-movement comparator.
    BotNativeAction::Candidate shadowDescent;
    shadowDescent.Id.Actor = PlayerGuid(300);
    shadowDescent.Action = BotNativeAction::NativeDescent{
        1.0f, 2.0f, 210.0f, 3.0f, 4.0f, 210.0f, 7, true };
    BotNativeAction::Candidate legacyDescent = shadowDescent;
    legacyDescent.Action = BotNativeAction::NativeDescent{
        9.0f, 8.0f, 210.0f, 7.0f, 6.0f, 210.0f, 7, true };
    comparison = CompareMagmawTransferLaneIntents({ shadowDescent },
        legacyDescent);
    assert(comparison.Outcome == Outcome::Divergent);
    assert(comparison.Has(Divergence::UnhandledDestination));

    std::vector<BotNativeAction::Candidate> ambiguous{
        MoveCandidate(300, 11.0f, -22.0f),
        MoveCandidate(300, 12.0f, -23.0f) };
    BotNativeAction::Candidate nonMovement;
    ambiguous.push_back(nonMovement);
    comparison = CompareMagmawTransferLaneIntents(ambiguous, legacy);
    assert(comparison.Outcome == Outcome::Divergent);
    assert(comparison.ProposalCount == 3);
    assert(comparison.MovementProposalCount == 2);
    assert(comparison.Ambiguous());
    assert(comparison.Has(Divergence::AmbiguousShadowMovement));

    // This is the exact helper used by production. It emits every matching
    // task, so duplicate same-actor running tasks surface as ambiguity rather
    // than selecting the first task by source order.
    task = RunningTask();
    std::vector<MagmawTransferLaneTask> productionTasks{ task };
    comparison = ObserveMagmawTransferLaneIntents(productionTasks,
        task.Id.ActorGuid, std::nullopt);
    assert(comparison.Outcome == Outcome::ShadowOnly);
    assert(comparison.ShadowActor == task.Id.ActorGuid);
    assert(comparison.ShadowTaskGeneration == task.Id.TaskGeneration);
    MagmawTransferLaneTask duplicate = task;
    duplicate.Id.TaskGeneration = 45;
    productionTasks.push_back(duplicate);
    comparison = ObserveMagmawTransferLaneIntents(productionTasks,
        task.Id.ActorGuid, std::nullopt);
    assert(comparison.Outcome == Outcome::Divergent);
    assert(comparison.ProposalCount == 2);
    assert(comparison.MovementProposalCount == 2);
    assert(comparison.Has(Divergence::AmbiguousShadowMovement));

    // The outer decision tick uses this same value reset before any optional
    // snapshot observation, so a snapshotless tick is explicitly unobserved.
    comparison.Observed = true;
    comparison.Outcome = Outcome::Divergent;
    comparison.ProposalCount = 9;
    comparison.MovementProposalCount = 8;
    comparison.Divergences = DivergenceMask(Divergence::Actor);
    comparison.ShadowActor = PlayerGuid(300);
    comparison.LegacyActor = PlayerGuid(400);
    comparison.ShadowTaskGeneration = 77;
    ResetMagmawTransferLaneIntentComparison(comparison);
    assert(!comparison.Observed);
    assert(comparison.Outcome == Outcome::NeitherPresent);
    assert(comparison.ProposalCount == 0);
    assert(comparison.MovementProposalCount == 0);
    assert(comparison.Divergences == 0);
    assert(comparison.ShadowActor.IsEmpty());
    assert(comparison.LegacyActor.IsEmpty());
    assert(comparison.ShadowTaskGeneration == 0);
}
''', encoding="utf-8")
    subprocess.run([
        "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES,
        str(source), "-o", str(binary),
    ], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_production_shadow_comparison_is_post_plan_and_non_executing() -> None:
    bots = ROOT / "src/server/game/Bots"
    preparation = (bots /
        "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp").read_text()
    adapter = (bots / "BotWorldPopulationMgrMagmawTaskShadow.cpp").read_text()
    intent = (bots / "Content/Raids/BlackwingDescent/Encounters/Magmaw/"
        "BotMagmawTransferLaneIntent.h").read_text()
    sink = (bots / "Decision/BotIntentSink.h").read_text()

    plan = "BotEncounter::AdaptiveMagmawPlan magmawPlan = magmawStrategy.Propose("
    observe = "ObserveMagmawTransferLaneIntentComparison(context.State,"
    move = "context.AdaptiveMagmawMovement = std::move(magmawPlan.Movement);"
    reset = "BotEncounter::ResetMagmawTransferLaneIntentComparison("
    snapshot = "if (Cohort().EncounterSnapshot)"
    assert preparation.index(reset) < preparation.index(snapshot)
    assert preparation.index(plan) < preparation.index(observe)
    assert preparation.index(observe) < preparation.index(move)
    assert "Cohort().MagmawTransferLaneTaskShadow" in adapter
    assert "ObserveMagmawTransferLaneIntents(tasks, actor," in adapter
    assert "find_if(shadow->Tasks()" not in adapter
    assert "BuildMagmawTransferLaneIntentComparisonJson(state)" in adapter
    assert "std::vector<BotNativeAction::Candidate> _proposals" in sink
    assert "Kernel" not in sink + intent + adapter
    assert "BotActionExecutor" not in sink + intent + adapter
    assert "ExecuteNativeAction" not in sink + intent + adapter
    assert "MotionMaster" not in sink + intent + adapter
    assert "PathGenerator" not in sink + intent + adapter
    assert ".Submit(" not in sink + intent + adapter
    assert "Propose(std::move(candidate))" in intent
    assert "state.MagmawTransferLaneIntentComparison" in adapter
    assert '"unhandled_destination"' in adapter
