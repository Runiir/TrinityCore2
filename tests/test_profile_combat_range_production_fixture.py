from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "src/server/game/Bots/BotProfileCombatRangeCandidate.h"
CHECKPOINT = ROOT / "src/server/game/Bots/BotProfileCombatRangeCheckpoint.h"
FALLBACK = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp"
DECISION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotDecision.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_production_adapter_value_matrix_and_arbiter_boundary(tmp_path: Path) -> None:
    source = tmp_path / "profile_combat_range_production_fixture.cpp"
    binary = tmp_path / "profile_combat_range_production_fixture"
    source.write_text(
        r'''
#include "Bots/BotProfileCombatRangeCandidate.h"

#include <cassert>

using BotProfileCombatRangeCandidate::Decision;

Decision ValidDecision()
{
    Decision decision;
    decision.TargetPresent = true;
    decision.TargetInWorld = true;
    decision.TargetAlive = true;
    decision.TargetAttackable = true;
    decision.SameMap = true;
    decision.SameInstance = true;
    decision.Distance = 4.0f;
    decision.MinRange = 8.0f;
    return decision;
}

BotActionArbitration::Resolution Run(Decision decision, bool& moved)
{
    decision.Move = [&moved]()
    {
        moved = true;
        return true;
    };
    BotActionArbitration::Kernel kernel;
    kernel.Begin(1000);
    BotProfileCombatRangeCandidate::Request request;
    request.UtilityScore = 0.9f;
    request.Observe = [decision = std::move(decision)]() mutable
    {
        return decision;
    };
    assert(kernel.Submit(BotProfileCombatRangeCandidate::Build(
        std::move(request))));
    kernel.Resolve();
    return kernel.LastResolution();
}

void AssertRejected(Decision decision, char const* reason)
{
    bool moved = false;
    BotActionArbitration::Resolution const resolution = Run(
        std::move(decision), moved);
    assert(!moved);
    assert(!resolution.AnyCommitted);
    assert(resolution.Trace.size() == 1);
    assert(resolution.Trace[0].Key
        == BotProfileCombatRangeCandidate::Key);
    assert(resolution.Trace[0].Reason == reason);
}

int main()
{
    Decision positive = ValidDecision();
    bool moved = false;
    BotActionArbitration::Resolution const positiveResolution = Run(
        std::move(positive), moved);
    assert(moved);
    assert(positiveResolution.AnyCommitted);
    assert(positiveResolution.ClaimedResources
        == BotActionArbitration::Uses(BotActionArbitration::Resource::Movement));
    assert(positiveResolution.Trace[0].Key
        == BotProfileCombatRangeCandidate::Key);
    assert(positiveResolution.Trace[0].Reason
        == "profile_combat_min_range_reconciled");

    for (int field = 0; field != 6; ++field)
    {
        Decision invalid = ValidDecision();
        switch (field)
        {
            case 0: invalid.TargetPresent = false; break;
            case 1: invalid.TargetInWorld = false; break;
            case 2: invalid.TargetAlive = false; break;
            case 3: invalid.TargetAttackable = false; break;
            case 4: invalid.SameMap = false; break;
            case 5: invalid.SameInstance = false; break;
        }
        AssertRejected(std::move(invalid), "profile_combat_target_invalid");
    }

    Decision legalBand = ValidDecision();
    legalBand.Distance = legalBand.MinRange;
    AssertRejected(std::move(legalBand), "profile_min_range_satisfied");

    Decision latchClosed = ValidDecision();
    latchClosed.TypedDrudgeValidationRoute = true;
    latchClosed.AdaptiveDrudgeOwnsNode = true;
    latchClosed.DrudgeCombatAuthorityAllowed = false;
    AssertRejected(std::move(latchClosed), "drudge_activation_latch_closed");

    for (bool noLineOfSight : { false, true })
    {
        Decision drudge = ValidDecision();
        drudge.OwnedDrudge = true;
        drudge.Distance = noLineOfSight ? 10.0f : 40.0f;
        drudge.MaxRange = 30.0f;
        drudge.NoLineOfSight = noLineOfSight;
        bool drudgeMoved = false;
        BotActionArbitration::Resolution const resolution = Run(
            std::move(drudge), drudgeMoved);
        assert(drudgeMoved && resolution.AnyCommitted);
        assert(resolution.Trace[0].Reason
            == (noLineOfSight ? "profile_combat_los_reconciled"
                : "profile_combat_range_reconciled"));
    }

    // The range adapter owns Movement only. An ordinary cast candidate can
    // commit in the same kernel resolution.
    BotActionArbitration::Kernel coexistKernel;
    coexistKernel.Begin(1000);
    bool rangeMoved = false;
    Decision coexistDecision = ValidDecision();
    coexistDecision.Move = [&rangeMoved]()
    {
        rangeMoved = true;
        return true;
    };
    BotProfileCombatRangeCandidate::Request coexistRequest;
    coexistRequest.UtilityScore = 0.9f;
    coexistRequest.Observe = [decision = std::move(coexistDecision)]() mutable
    {
        return decision;
    };
    assert(coexistKernel.Submit(BotProfileCombatRangeCandidate::Build(
        std::move(coexistRequest))));
    bool cast = false;
    BotActionArbitration::Candidate ordinaryCast;
    ordinaryCast.Key = "world.profile_combat";
    ordinaryCast.Source = "db_class_spec_profile";
    ordinaryCast.ActionPriority = BotActionArbitration::Priority::TrainedDamage;
    ordinaryCast.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::GlobalCooldown,
        BotActionArbitration::Resource::Cast,
        BotActionArbitration::Resource::Target);
    ordinaryCast.Attempt = [&cast]()
    {
        cast = true;
        return BotActionArbitration::Outcome::Submitted("cast_submitted");
    };
    assert(coexistKernel.Submit(std::move(ordinaryCast)));
    BotActionArbitration::Resolution const& coexist = coexistKernel.Resolve();
    assert(rangeMoved && cast);
    assert(coexist.CommittedCandidates.size() == 2);

    // This is arbiter-only coverage for a producer-owned higher-priority
    // Movement lane. The production replay must provide the real hazard
    // producer receipt; this test does not certify that live boundary.
    BotActionArbitration::Kernel conflictKernel;
    conflictKernel.Begin(1000);
    bool conflictRangeMoved = false;
    Decision conflictDecision = ValidDecision();
    conflictDecision.Move = [&conflictRangeMoved]()
    {
        conflictRangeMoved = true;
        return true;
    };
    BotProfileCombatRangeCandidate::Request conflictRequest;
    conflictRequest.UtilityScore = 0.9f;
    conflictRequest.Observe = [decision = std::move(conflictDecision)]() mutable
    {
        return decision;
    };
    assert(conflictKernel.Submit(BotProfileCombatRangeCandidate::Build(
        std::move(conflictRequest))));
    bool hazard = false;
    BotActionArbitration::Candidate observedHazard;
    observedHazard.Key = "observed.hazard.movement";
    observedHazard.Source = "observed_hazard_producer";
    observedHazard.ActionPriority = BotActionArbitration::Priority::Survival;
    observedHazard.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::Movement);
    observedHazard.Attempt = [&hazard]()
    {
        hazard = true;
        return BotActionArbitration::Outcome::Started("hazard_started");
    };
    assert(conflictKernel.Submit(std::move(observedHazard)));
    BotActionArbitration::Resolution const& conflict = conflictKernel.Resolve();
    assert(hazard && !conflictRangeMoved);
    assert(conflict.Trace.size() == 2);
    assert(conflict.Trace[1].Key
        == BotProfileCombatRangeCandidate::Key);
    assert(conflict.Trace[1].Status == "resource_conflict");
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)


def test_production_wiring_and_observer_are_default_off() -> None:
    adapter = ADAPTER.read_text(encoding="utf-8")
    checkpoint = CHECKPOINT.read_text(encoding="utf-8")
    fallback = FALLBACK.read_text(encoding="utf-8")
    decision = DECISION.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")

    assert 'constexpr char Key[] = "world.profile_combat_range"' in adapter
    assert "BotProfileCombatRangeCandidate::Build" in fallback
    assert "rangeRequest.Observe" in fallback
    assert "generic_profile_min_range_production_boundary_v1" in checkpoint
    assert "ProfileCombatRangeCheckpointEnable = false" in (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrConfig.h"
    ).read_text(encoding="utf-8")
    assert "ObserveProfileCombatRangeCheckpoint(context);" in decision
    assert "BotWorldPopulationMgrProfileCombatRangeCheckpoint.cpp" in cmake
    assert "MotionMaster" not in checkpoint
    assert "MoveBotToPoint" not in checkpoint
    assert "Teleport" not in checkpoint


def test_source_has_no_replacement_range_candidate() -> None:
    fallback = FALLBACK.read_text(encoding="utf-8")
    assert "BotActionArbitration::Candidate combatRange" not in fallback
    assert "BotProfileCombatRangeCandidate::Build" in fallback
