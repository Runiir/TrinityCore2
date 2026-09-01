from pathlib import Path
import shutil
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


def test_magmaw_movement_intents_cross_strategy_and_real_kernel(
    tmp_path: Path, request,
) -> None:
    request.addfinalizer(lambda: shutil.rmtree(tmp_path, ignore_errors=True))
    source = tmp_path / "magmaw_movement_intents.cpp"
    binary = tmp_path / "magmaw_movement_intents"
    source.write_text(r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMovementKernelAdapter.h"

#include <algorithm>
#include <cassert>
#include <string>
#include <vector>

using namespace BotEncounter;
using namespace BotActionArbitration;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

static ActorSnapshot Player(uint32 guid, char const* spec, Vector3 position)
{
    ActorSnapshot player;
    player.Guid = ObjectGuid(HighGuid::Player, guid);
    player.Alive = true;
    player.Role = "dps";
    player.ClassSpec = spec;
    player.HealthPct = 100.0f;
    player.Position = position;
    return player;
}

static Blackboard Board()
{
    Blackboard board;
    board.CurrentScope = { "intent_collection", 9, 1, 4,
        "bwd.magmaw.encounter", 669, 31, "magmaw" };
    board.Revision = 88;
    board.ObservedAtMs = 5000;
    board.NativeBossState = "in_progress";
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { { 0.0f, -100.0f, 210.0f } };
    board.Players = {
        Player(30006, "fire_mage", { 0.0f, -30.0f, 210.0f }),
        Player(30009, "marksmanship_hunter", { 2.0f, -30.0f, 210.0f }),
        Player(30008, "affliction_warlock", { 0.0f, -20.0f, 210.0f }) };
    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit,
        AdaptiveMagmawStrategy::BossEntry, uint32(39));
    boss.Entry = AdaptiveMagmawStrategy::BossEntry;
    boss.Alive = true;
    boss.Attackable = true;
    boss.Selectable = true;
    boss.InCombat = true;
    boss.Position = { 0.0f, 0.0f, 210.0f };
    board.Hostiles.push_back(boss);
    return board;
}

static ActorSnapshot Pillar(Vector3 position)
{
    ActorSnapshot pillar;
    pillar.Guid = ObjectGuid(HighGuid::Unit,
        AdaptiveMagmawStrategy::PillarEntry, uint32(700));
    pillar.Entry = AdaptiveMagmawStrategy::PillarEntry;
    pillar.Alive = true;
    pillar.Position = position;
    return pillar;
}

static BotActionArbitration::Resolution Resolve(
    MagmawMovementIntentCollection const& intents, bool reverseSubmission,
    bool retrySafety)
{
    using namespace BotActionArbitration;
    Kernel kernel;
    kernel.Begin(5000);
    MagmawMovementIntentCollection submitted;
    std::vector<size_t> order;
    for (size_t index = 0; index < intents.Size(); ++index)
        order.push_back(index);
    if (reverseSubmission)
        std::reverse(order.begin(), order.end());
    for (size_t index : order)
        submitted.Propose(intents.Origin(index), intents.Proposals()[index]);
    MagmawMovementKernelAdapterContext context;
    context.ObservedAtMs = 5000;
    context.Execute = [retrySafety](BotNativeAction::Intent const& native,
        MagmawMovementNativeLease lease,
        BotWorldMovement::ExecutionObservation* movement)
    {
        assert(!movement);
        auto const* move = std::get_if<BotNativeAction::Move>(&native);
        assert(move);
        bool const safety = move->IntentReason == "pillar_evade";
        assert(lease.Priority == (safety
            ? BotMovementArbitration::Priority::Hazard
            : BotMovementArbitration::Priority::Mechanic));
        return safety && retrySafety
            ? Outcome::Retryable("planner_rejected")
            : Outcome::Committed("submitted");
    };
    assert(SubmitMagmawMovementKernelCandidates(kernel, submitted,
        std::move(context)) == submitted.Size());
    return kernel.Resolve();
}

static CandidateTrace const* TraceFor(Resolution const& resolution,
    std::string const& source)
{
    auto trace = std::find_if(resolution.Trace.begin(), resolution.Trace.end(),
        [&source](CandidateTrace const& value)
        {
            return value.Source == source;
        });
    return trace == resolution.Trace.end() ? nullptr : &*trace;
}

int main()
{
    AdaptiveMagmawStrategy strategy;
    Blackboard hookBoard = Board();
    hookBoard.Hostiles.front().Interactable = true;
    hookBoard.Summons.push_back(Pillar({ 0.5f, -30.0f, 210.0f }));
    ObjectGuid const hookActor = hookBoard.Players.front().Guid;

    AdaptiveMagmawPlan defaultPlan = strategy.Propose(hookBoard, hookActor,
        "dps");
    AdaptiveMagmawStrategy::MovementProducerOrder const reversed{
        MagmawMovementProposalOrigin::FormationRestore,
        MagmawMovementProposalOrigin::HookApproach,
        MagmawMovementProposalOrigin::HookPreposition,
        MagmawMovementProposalOrigin::Hazard };
    AdaptiveMagmawPlan reversedPlan = strategy.Propose(hookBoard, hookActor,
        "dps", nullptr, false, false, nullptr, nullptr, nullptr,
        std::nullopt, reversed);
    assert(defaultPlan.Movement.Size() == 2);
    assert(reversedPlan.Movement.Size() == 2);

    Resolution defaultResolution = Resolve(defaultPlan.Movement, false, false);
    Resolution reversedResolution = Resolve(reversedPlan.Movement, true, false);
    assert(defaultResolution.CommittedCandidates.size() == 1);
    assert(defaultResolution.CommittedCandidates
        == reversedResolution.CommittedCandidates);
    assert(defaultResolution.Trace.size() == reversedResolution.Trace.size());
    for (size_t index = 0; index < defaultResolution.Trace.size(); ++index)
    {
        CandidateTrace const& left = defaultResolution.Trace[index];
        CandidateTrace const& right = reversedResolution.Trace[index];
        assert(left.Key == right.Key);
        assert(left.Source == right.Source);
        assert(left.Status == right.Status);
        assert(left.Reason == right.Reason);
    }
    CandidateTrace const* hookTrace = TraceFor(defaultResolution,
        "adaptive_magmaw.hook_approach");
    assert(hookTrace && hookTrace->Status == "hard_masked");

    // A retryable lethal movement cannot expose the lower-priority hook.
    Resolution retryableSafety = Resolve(defaultPlan.Movement, true, true);
    assert(!retryableSafety.AnyCommitted);
    hookTrace = TraceFor(retryableSafety,
        "adaptive_magmaw.hook_approach");
    assert(hookTrace && hookTrace->Status == "hard_masked");
    assert(hookTrace->Reason == "magmaw_survival_movement_pending");

    // A non-hook actor independently exposes hazard and formation producers.
    Blackboard formationBoard = Board();
    formationBoard.Summons.push_back(Pillar({ 0.5f, -20.0f, 210.0f }));
    AdaptiveMagmawPlan formationPlan = strategy.Propose(formationBoard,
        formationBoard.Players[2].Guid, "dps");
    assert(formationPlan.Movement.Size() == 2);
    Resolution formationResolution = Resolve(formationPlan.Movement, false,
        true);
    CandidateTrace const* formationTrace = TraceFor(formationResolution,
        "adaptive_magmaw.formation_restore");
    assert(formationTrace && formationTrace->Status == "hard_masked");

    // Unknown movement mechanics still enter the real kernel and fail closed.
    Kernel unknownKernel;
    unknownKernel.Begin(5000);
    BotNativeAction::Candidate unknownIntent =
        formationPlan.Movement.Proposals().back();
    unknownIntent.Id.Mechanic = "unknown_movement";
    MagmawMovementIntentCollection unknownMovements;
    unknownMovements.Propose(MagmawMovementProposalOrigin::Hazard,
        unknownIntent);
    MagmawMovementKernelAdapterContext unknownContext;
    unknownContext.ObservedAtMs = 5000;
    unknownContext.Execute = [](BotNativeAction::Intent const&,
        MagmawMovementNativeLease,
        BotWorldMovement::ExecutionObservation*)
    {
        assert(false);
        return Outcome::Committed("unreachable");
    };
    assert(SubmitMagmawMovementKernelCandidates(unknownKernel,
        unknownMovements, std::move(unknownContext)) == 1);
    Resolution const& unknownResolution = unknownKernel.Resolve();
    assert(unknownResolution.Trace.size() == 1);
    assert(unknownResolution.Trace.front().Status == "hard_masked");
    assert(unknownResolution.Trace.front().Reason
        == "magmaw_movement_mechanic_unmapped");

    // A bridge failure keeps the bound transfer proposal observable but can
    // never fall through to the generic native executor.
    Kernel bindingKernel;
    bindingKernel.Begin(5000);
    MagmawMovementIntentCollection rejectedMovements;
    BotNativeAction::Candidate bound =
        formationPlan.Movement.Proposals().front();
    bound.Id.Mechanic = "pillar_bait_switch";
    rejectedMovements.Propose(MagmawMovementProposalOrigin::TransferLaneTask,
        bound);
    MagmawMovementKernelAdapterContext rejectedContext;
    rejectedContext.ObservedAtMs = 5000;
    rejectedContext.TransferBinding.emplace();
    rejectedContext.TransferBinding->ScopeKey = "wrong";
    rejectedContext.Execute = [](BotNativeAction::Intent const&,
        MagmawMovementNativeLease,
        BotWorldMovement::ExecutionObservation*)
    {
        assert(false);
        return Outcome::Committed("unreachable");
    };
    rejectedContext.ObserveTransferOutcome = [](
        MagmawTransferLaneNativeOutcome const&) {};
    assert(SubmitMagmawMovementKernelCandidates(bindingKernel,
        rejectedMovements, std::move(rejectedContext)) == 1);
    Resolution const& bindingResolution = bindingKernel.Resolve();
    assert(bindingResolution.Trace.size() == 1);
    assert(bindingResolution.Trace.front().Status == "hard_masked");
    assert(bindingResolution.Trace.front().Reason
        == "magmaw_transfer_binding_rejected");

    // Expiry is copied to the real kernel, which owns the expiry verdict.
    BotNativeAction::Candidate expiredIntent =
        formationPlan.Movement.Proposals().back();
    expiredIntent.ExpiresAtMs = 5000;
    Kernel expiryKernel;
    expiryKernel.Begin(5000);
    MagmawMovementIntentCollection expiredMovements;
    expiredMovements.Propose(MagmawMovementProposalOrigin::FormationRestore,
        expiredIntent);
    MagmawMovementKernelAdapterContext expiredContext;
    expiredContext.ObservedAtMs = 5000;
    expiredContext.Execute = [](BotNativeAction::Intent const&,
        MagmawMovementNativeLease,
        BotWorldMovement::ExecutionObservation*)
    {
        assert(false);
        return Outcome::Committed("unreachable");
    };
    assert(SubmitMagmawMovementKernelCandidates(expiryKernel,
        expiredMovements, std::move(expiredContext)) == 1);
    Resolution const& expiryResolution = expiryKernel.Resolve();
    assert(expiryResolution.Trace.size() == 1);
    assert(expiryResolution.Trace.front().Status == "expired");
}
''', encoding="utf-8")
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES,
         str(source),
         str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
             "Encounters/Magmaw/BotMagmawMovementKernelAdapter.cpp"),
         str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
             "Encounters/Magmaw/BotMagmawTransferLaneKernelBridge.cpp"),
         str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
             "Encounters/Magmaw/BotMagmawTransferLaneIntent.cpp"),
         str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
             "Encounters/Magmaw/BotMagmawTransferLaneAuthority.cpp"),
         str(ROOT / "src/server/game/Bots/"
             "BotWorldPopulationMgrMovementExecution.cpp"),
         "-o", str(binary)],
        check=True, cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_magmaw_movement_collection_source_contract() -> None:
    bots = ROOT / "src/server/game/Bots"
    encounter = (bots /
        "Content/Raids/BlackwingDescent/Encounters/Magmaw")
    strategy = (encounter / "BotAdaptiveMagmawStrategy.h").read_text()
    context = (bots / "BotWorldPopulationMgrUpdateContext.h").read_text()
    preparation = (bots /
        "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp").read_text()
    candidates = (bots /
        "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp").read_text()
    fallback = (bots /
        "BotWorldPopulationMgrUpdateBotKernelFallback.cpp").read_text()
    authority = (encounter /
        "BotMagmawTransferLaneAuthority.cpp").read_text()
    movement_intents = (encounter /
        "BotMagmawMovementIntents.h").read_text()
    kernel_adapter = (encounter /
        "BotMagmawMovementKernelAdapter.cpp").read_text()
    transfer_bridge = (encounter /
        "BotMagmawTransferLaneKernelBridge.h").read_text()

    assert "MagmawMovementIntentCollection Movement;" in strategy
    assert "std::optional<BotNativeAction::Candidate> Movement;" not in strategy
    assert "for (MagmawMovementProposalOrigin origin : producerOrder)" in strategy
    assert "AdaptiveMagmawMovements" in context
    assert "transferLaneSelection.Movements" in preparation
    assert "AdaptiveMagmawMovements.Size()" in preparation
    assert "HasRetainedMagmawHazardOwnership(" in fallback
    assert "MagmawPersonalParasiteEscape" in fallback
    assert "SubmitMagmawMovementKernelCandidates(" in candidates
    assert "HasPendingMagmawSurvivalMovement(" in kernel_adapter
    assert "magmaw_survival_movement_pending" in movement_intents
    assert "magmaw_movement_mechanic_unmapped" in movement_intents
    assert "magmaw_transfer_binding_rejected" in movement_intents
    assert "BuildMagmawMovementKernelCandidate(intent, origin" in kernel_adapter
    assert "SubmitMagmawTransferLaneKernelCandidate(kernel, intent" in kernel_adapter
    assert "trace-visible hard mask" in transfer_bridge
    assert "must not execute generic movement" in transfer_bridge
    assert "preserve\n// the legacy generic submission path" not in transfer_bridge
    assert "result.Movements.Replace(matchingIndex" in authority
    assert ".Attempt = [&]" not in candidates

    changed_cpp = [
        bots / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp",
        bots / "BotWorldPopulationMgrUpdateBotKernelFallback.cpp",
        bots / "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp",
        bots / "BotWorldPopulationMgrUpdateContext.h",
        encounter / "BotAdaptiveMagmawStrategy.h",
        encounter / "BotAdaptiveMagmawStrategySupport.h",
        encounter / "BotAdaptiveMagmawStrategyHazard.h",
        encounter / "BotAdaptiveMagmawStrategyHook.h",
        encounter / "BotMagmawMovementIntents.h",
        encounter / "BotMagmawMovementKernelCandidate.h",
        encounter / "BotMagmawMovementKernelAdapter.h",
        encounter / "BotMagmawMovementKernelAdapter.cpp",
        encounter / "BotMagmawTransferLaneAuthority.cpp",
        encounter / "BotMagmawTransferLaneAuthority.h",
        encounter / "BotMagmawTransferLaneKernelBridge.h",
    ]
    for path in changed_cpp:
        assert len(path.read_text().splitlines()) < 1000, path
