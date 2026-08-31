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
#include <limits>
#include <string>

using namespace BotEncounter;
using Outcome = MagmawTransferLaneIntentComparisonOutcome;
using Divergence = MagmawTransferLaneIntentDivergence;
using State = BotDecision::PersistentTaskState;
constexpr uint64 LegacyGeneration = 77;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

static ObjectGuid PlayerGuid(uint32 counter)
{
    return ObjectGuid(HighGuid::Player, counter);
}

static MagmawTransferLaneTask RunningTask(uint32 actor = 300,
    uint64 generation = 44)
{
    MagmawTransferLaneTask task;
    task.Id.Episode.Lifecycle = { "cohort", 7, 2, 5, "magmaw", 669,
        23, "blackwing_descent.magmaw", 91, 4 };
    task.Id.ActorGuid = PlayerGuid(actor);
    task.Id.TaskGeneration = generation;
    task.Destination = { 11.0f, -22.0f, 210.0f };
    task.State = State::Running;
    task.LastObservedAtMs = 1000;
    return task;
}

static BotNativeAction::Candidate Emitted(
    MagmawTransferLaneTask const& task)
{
    BotDecision::BotIntentSink sink;
    EmitMagmawTransferLaneTaskIntent(task, sink);
    assert(sink.Proposals().size() == 1);
    return sink.Proposals().front();
}

static MagmawTransferLaneIntentComparison Compare(
    BotNativeAction::Candidate const& shadow,
    BotNativeAction::Candidate const& legacy,
    MagmawTransferLaneTask const& task)
{
    return CompareMagmawTransferLaneIntents({ shadow }, legacy,
        MagmawTransferLaneContract(task, LegacyGeneration));
}

int main()
{
    MagmawTransferLaneTask task = RunningTask();
    BotNativeAction::Candidate shadow = Emitted(task);
    auto const* move = std::get_if<BotNativeAction::Move>(&shadow.Action);
    assert(shadow.Id.ScopeKey == task.Id.Episode.Lifecycle.Key());
    assert(shadow.Id.Strategy == "adaptive_magmaw");
    assert(shadow.Id.Mechanic == "pillar_bait_switch");
    assert(shadow.Id.Actor == task.Id.ActorGuid);
    assert(shadow.Id.EventGeneration == task.Id.TaskGeneration);
    assert(shadow.ActionPriority == BotActionArbitration::Priority::Survival);
    assert(shadow.Utility == MagmawTransferLaneIntentUtility);
    assert(shadow.ExpiresAtMs == task.LastObservedAtMs
        + MagmawTransferLaneIntentFreshnessMs);
    assert(shadow.Resources() == BotActionArbitration::Uses(
        BotActionArbitration::Resource::Movement));
    assert(move && move->X == task.Destination.X
        && move->Y == task.Destination.Y && move->Z == task.Destination.Z
        && move->IntentReason == "pillar_bait_switch"
        && !move->PreemptCasting);

    // Stable keys distinguish both actors and replacement generations.
    BotNativeAction::Candidate otherActor = Emitted(RunningTask(400, 45));
    BotNativeAction::Candidate replacement = Emitted(RunningTask(300, 46));
    assert(shadow.Id.Key() != otherActor.Id.Key());
    assert(shadow.Id.Key() != replacement.Id.Key());

    for (State state : { State::Suspended, State::Succeeded, State::Failed,
        State::Aborted })
    {
        task.State = state;
        BotDecision::BotIntentSink suppressed;
        EmitMagmawTransferLaneTaskIntent(task, suppressed);
        assert(suppressed.Proposals().empty());
    }
    task = RunningTask();

    std::vector<BotNativeAction::Candidate> none;
    auto comparison = CompareMagmawTransferLaneIntents(none, std::nullopt,
        std::nullopt);
    assert(comparison.Outcome == Outcome::NeitherPresent);
    comparison = CompareMagmawTransferLaneIntents({ shadow }, std::nullopt,
        MagmawTransferLaneContract(task, LegacyGeneration));
    assert(comparison.Outcome == Outcome::ShadowOnly);
    comparison = CompareMagmawTransferLaneIntents(none, shadow,
        MagmawTransferLaneContract(task, LegacyGeneration));
    assert(comparison.Outcome == Outcome::LegacyOnly);

    BotNativeAction::Candidate legacy = shadow;
    // The legacy TransitionId and persistent TaskGeneration are separate
    // identity domains. An authoritative correlation validates each against
    // its own domain; numeric equality is neither required nor manufactured.
    legacy.Id.EventGeneration = LegacyGeneration;
    comparison = Compare(shadow, legacy, task);
    assert(comparison.Outcome == Outcome::Equivalent);
    assert(comparison.Divergences == 0);
    assert(comparison.ShadowTaskGeneration == 44);
    assert(comparison.LegacyEventGeneration == LegacyGeneration);
    assert(comparison.ExpectedLegacyTransitionGeneration == LegacyGeneration);

    comparison = CompareMagmawTransferLaneIntents({ shadow }, legacy,
        std::nullopt);
    assert(comparison.Has(Divergence::MissingExecutionContract));

    auto expect = [&](BotNativeAction::Candidate changed,
        Divergence divergence)
    {
        auto result = Compare(shadow, changed, task);
        assert(result.Outcome == Outcome::Divergent);
        assert(result.Has(divergence));
    };
    BotNativeAction::Candidate changed = legacy;
    changed.Id.Strategy = "other";
    expect(changed, Divergence::StrategyIdentity);
    changed = legacy;
    changed.Id.Mechanic = "other";
    expect(changed, Divergence::MechanicIdentity);
    changed = legacy;
    changed.Id.ScopeKey = "other";
    expect(changed, Divergence::LifecycleScope);
    changed = legacy;
    changed.Action = BotNativeAction::DirectionalMobility{ 11.0f, -22.0f,
        210.0f, 1953, BotNativeAction::DirectionalMobilityFacing::Forward,
        "pillar_bait_switch" };
    expect(changed, Divergence::ActionKind);
    changed = legacy;
    changed.Id.Actor = PlayerGuid(400);
    expect(changed, Divergence::Actor);
    changed = legacy;
    changed.Id.EventGeneration = 999;
    expect(changed, Divergence::GenerationCorrelation);
    changed = legacy;
    std::get<BotNativeAction::Move>(changed.Action).PreemptCasting = true;
    expect(changed, Divergence::MovementResource);
    expect(changed, Divergence::PreemptCasting);
    changed = legacy;
    std::get<BotNativeAction::Move>(changed.Action).X =
        std::numeric_limits<float>::quiet_NaN();
    expect(changed, Divergence::DestinationNonFinite);
    changed = legacy;
    std::get<BotNativeAction::Move>(changed.Action).X +=
        MagmawTransferLaneIntentDestinationTolerance2d + 0.01f;
    expect(changed, Divergence::Destination2d);
    changed = legacy;
    std::get<BotNativeAction::Move>(changed.Action).Z +=
        MagmawTransferLaneIntentDestinationToleranceZ + 0.01f;
    expect(changed, Divergence::DestinationZ);
    changed = legacy;
    changed.ActionPriority = BotActionArbitration::Priority::Mechanic;
    expect(changed, Divergence::ActionPriority);
    changed = legacy;
    changed.Utility = 499.0f;
    expect(changed, Divergence::Utility);
    changed = legacy;
    --changed.ExpiresAtMs;
    expect(changed, Divergence::Expiry);

    // Shadow identity itself is checked against the persistent task contract.
    changed = shadow;
    changed.Id.EventGeneration = 900;
    comparison = Compare(changed, legacy, task);
    assert(comparison.Has(Divergence::GenerationCorrelation));

    std::vector<BotNativeAction::Candidate> ambiguous{ shadow, replacement };
    comparison = CompareMagmawTransferLaneIntents(ambiguous, legacy,
        MagmawTransferLaneContract(task, LegacyGeneration));
    assert(comparison.Outcome == Outcome::Divergent);
    assert(comparison.ProposalCount == 2);
    assert(comparison.MovementProposalCount == 2);
    assert(comparison.Has(Divergence::AmbiguousShadowMovement));

    // Production emits all matching tasks instead of selecting by order.
    std::vector<MagmawTransferLaneTask> productionTasks{ task };
    comparison = ObserveMagmawTransferLaneIntents(productionTasks,
        task.Id.ActorGuid, legacy, LegacyGeneration);
    assert(comparison.Outcome == Outcome::Equivalent);
    MagmawTransferLaneTask duplicate = task;
    duplicate.Id.TaskGeneration = 45;
    productionTasks.push_back(duplicate);
    comparison = ObserveMagmawTransferLaneIntents(productionTasks,
        task.Id.ActorGuid, legacy, LegacyGeneration);
    assert(comparison.Outcome == Outcome::Divergent);
    assert(comparison.Has(Divergence::AmbiguousShadowMovement));

    comparison.Observed = true;
    comparison.LegacyEventGeneration = 88;
    ResetMagmawTransferLaneIntentComparison(comparison);
    assert(!comparison.Observed);
    assert(comparison.Outcome == Outcome::NeitherPresent);
    assert(comparison.ProposalCount == 0);
    assert(comparison.MovementProposalCount == 0);
    assert(comparison.Divergences == 0);
    assert(comparison.ShadowActor.IsEmpty());
    assert(comparison.LegacyActor.IsEmpty());
    assert(comparison.ShadowTaskGeneration == 0);
    assert(comparison.LegacyEventGeneration == 0);
    assert(comparison.ExpectedLegacyTransitionGeneration == 0);
}
''', encoding="utf-8")
    subprocess.run([
        "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES,
        str(source),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawTransferLaneIntent.cpp"),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_production_shadow_comparison_is_post_plan_and_non_executing() -> None:
    bots = ROOT / "src/server/game/Bots"
    preparation = (bots /
        "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp").read_text()
    adapter = (bots / "BotWorldPopulationMgrMagmawTaskShadow.cpp").read_text()
    intent_header = (bots /
        "Content/Raids/BlackwingDescent/Encounters/Magmaw/"
        "BotMagmawTransferLaneIntent.h").read_text()
    intent_source = (bots /
        "Content/Raids/BlackwingDescent/Encounters/Magmaw/"
        "BotMagmawTransferLaneIntent.cpp").read_text()
    sink = (bots / "Decision/BotIntentSink.h").read_text()
    intent = intent_header + intent_source

    plan = "BotEncounter::AdaptiveMagmawPlan magmawPlan = magmawStrategy.Propose("
    observe = "ObserveMagmawTransferLaneIntentComparison(context.State,"
    move = "context.AdaptiveMagmawMovement = std::move(magmawPlan.Movement);"
    reset = "BotEncounter::ResetMagmawTransferLaneIntentComparison("
    snapshot = "if (Cohort().EncounterSnapshot)"
    assert preparation.index(reset) < preparation.index(snapshot)
    assert preparation.index(plan) < preparation.index(observe)
    assert preparation.index(observe) < preparation.index(move)
    assert "magmawLaneOwner->MagmawLaneTransition.TransitionId" in preparation
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
    assert "Propose(std::move(candidate))" in intent_source
    assert "state.MagmawTransferLaneIntentComparison" in adapter
    for diagnostic in (
        "generation_correlation", "destination_non_finite", "destination_z",
        "preempt_casting", "action_priority", "utility", "expiry",
    ):
        assert f'"{diagnostic}"' in adapter
