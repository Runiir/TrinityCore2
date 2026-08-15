from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_action_and_movement_arbiters_compile_and_replay(tmp_path: Path) -> None:
    source = tmp_path / "arbiter_replay.cpp"
    binary = tmp_path / "arbiter_replay"
    source.write_text(
        r'''
#include "Bots/BotActionArbiter.h"
#include "Bots/BotMovementArbiter.h"
#include <cassert>
#include <string>

int main()
{
    using namespace BotActionArbitration;
    Tick tick;
    Outcome hazard = tick.Try(Priority::Survival, "hazard", []
    {
        return Outcome::Retryable("path_temporarily_blocked");
    });
    assert(hazard.Result == Disposition::Retryable);
    Outcome heal = tick.Try(Priority::Support, "heal", []
    {
        return FromBotActionResult(BotActionResult::Cooldown);
    });
    assert(heal.Result == Disposition::Retryable);
    Outcome damage = tick.Try(Priority::TrainedDamage, "trained_damage", []
    {
        return FromBotActionResult(BotActionResult::Ok);
    });
    assert(damage.Result == Disposition::Committed);
    assert(tick.Resolved());
    assert(tick.AttemptCount() == 3);

    Tick inversion;
    inversion.Try(Priority::Support, "heal", []
    {
        return Outcome::Retryable("cooldown");
    });
    Outcome bad = inversion.Try(Priority::Survival, "late_hazard", []
    {
        return Outcome::Committed("should_not_run");
    });
    assert(bad.Result == Disposition::Terminal);
    assert(!inversion.OrderingValid());

    using namespace BotMovementArbitration;
    Scope scope{ 7, 2, 9, 669, 41 };
    Lease lease;
    Request route{ Owner::Route, BotMovementArbitration::Priority::Route,
        1100, scope, 1.0f, 2.0f, 3.0f };
    assert(Evaluate(lease, route, 1000) == Decision::Acquire);
    Apply(lease, route);

    Request combat{ Owner::CombatRange, BotMovementArbitration::Priority::Combat,
        1200, scope, 4.0f, 5.0f, 6.0f };
    assert(Evaluate(lease, combat, 1001) == Decision::Preempt);
    Apply(lease, combat);

    Request lower{ Owner::Formation, BotMovementArbitration::Priority::Formation,
        1300, scope, 7.0f, 8.0f, 9.0f };
    assert(Evaluate(lease, lower, 1002) == Decision::PreserveExisting);

    Scope newInstance = scope;
    newInstance.InstanceId = 42;
    Request formationNewInstance{ Owner::Formation,
        BotMovementArbitration::Priority::Formation, 1300, newInstance,
        7.0f, 8.0f, 9.0f };
    assert(Evaluate(lease, formationNewInstance, 1002) == Decision::Acquire);

    // Producers submit in arbitrary order. The kernel applies the hard mask,
    // then ranks by priority and utility/model score. A failed high-priority
    // candidate does not monopolize the tick and conflicting lower-priority
    // movement cannot override the committed combat movement lane.
    Kernel kernel;
    kernel.Begin(2000);
    bool lowRan = false;
    bool hazardRan = false;
    bool damageRan = false;
    bool maskedRan = false;
    bool duplicateRan = false;
    kernel.Submit(Candidate{
        "route", "legacy_route", BotActionArbitration::Priority::RouteMovement, 1.0f, 0.0f, 0.0f,
        Uses(Resource::Movement), 0, 100, 3000, 5, true, "", [&]
        {
            lowRan = true;
            return Outcome::Committed("route_move");
        }
    });
    kernel.Submit(Candidate{
        "unsafe_cheat", "test", BotActionArbitration::Priority::Terminal, 100.0f, 0.0f, 0.0f,
        Uses(Resource::Movement), 0, 100, 3000, 5, false,
        "native_only", [&]
        {
            maskedRan = true;
            return Outcome::Committed("must_not_run");
        }
    });
    kernel.Submit(Candidate{
        "hazard", "encounter", BotActionArbitration::Priority::Survival, 2.0f, 0.0f, 0.0f,
        Uses(Resource::Movement), 0, 100, 3000, 5, true, "", [&]
        {
            hazardRan = true;
            return Outcome::Retryable("path_temporarily_blocked");
        }
    });
    kernel.Submit(Candidate{
        "damage", "profile", BotActionArbitration::Priority::TrainedDamage, 5.0f, 1.0f, 2.0f,
        Uses(Resource::GlobalCooldown, Resource::Cast, Resource::Movement, Resource::Target),
        0, 100, 3000, 5, true, "", [&]
        {
            damageRan = true;
            return Outcome::Committed("cast_submitted");
        }
    });
    kernel.Submit(Candidate{
        "damage", "worse_duplicate", BotActionArbitration::Priority::TrainedDamage, 1.0f, 0.0f, 0.0f,
        Uses(Resource::Cast), 0, 100, 3000, 5, true, "", [&]
        {
            duplicateRan = true;
            return Outcome::Committed("wrong_duplicate");
        }
    });
    Resolution const& resolution = kernel.Resolve();
    assert(resolution.AnyCommitted);
    assert(!resolution.Terminal);
    assert(hazardRan);
    assert(damageRan);
    assert(!lowRan);
    assert(!maskedRan);
    assert(!duplicateRan);
    assert(resolution.CommittedCandidates.size() == 1);
    assert(resolution.CommittedCandidates.front() == "damage");
    assert(kernel.LastResolutionJson().find("resource_conflict") != std::string::npos);
    assert(kernel.LastResolutionJson().find("hard_masked") != std::string::npos);

    // Retry backoff belongs to the failing candidate, not the bot. The
    // alternative remains eligible and progress clears escalation state.
    kernel.Begin(2050);
    bool backedOffCandidateRan = false;
    bool alternativeRan = false;
    kernel.Submit(Candidate{
        "hazard", "encounter", BotActionArbitration::Priority::Survival, 2.0f, 0.0f, 0.0f,
        Uses(Resource::Movement), 0, 100, 3000, 2, true, "", [&]
        {
            backedOffCandidateRan = true;
            return Outcome::Retryable("still_blocked");
        }
    });
    kernel.Submit(Candidate{
        "alternative", "recovery", BotActionArbitration::Priority::Mechanic, 1.0f, 0.0f, 0.0f,
        Uses(Resource::Movement), 0, 100, 3000, 2, true, "", [&]
        {
            alternativeRan = true;
            return Outcome::Progressed("alternate_path");
        }
    });
    kernel.Resolve();
    assert(!backedOffCandidateRan);
    assert(alternativeRan);
    kernel.Observe("hazard", Outcome::Retryable("still_blocked"), 7100, 100, 3000, 2);
    assert(kernel.ShouldEscalate("hazard", 7100, 5000));
    kernel.MarkProgress("hazard", 7101, "movement_progress");
    assert(!kernel.ShouldEscalate("hazard", 7101, 0));

    // Resolution must own callback-local reason text for later replay/export.
    kernel.Begin(8000);
    kernel.Submit(Candidate{
        "owned_reason", "test", BotActionArbitration::Priority::TrainedDamage,
        1.0f, 0.0f, 0.0f, Uses(Resource::Cast), 0, 100, 3000, 5, true, "", []
        {
            std::string transient = "callback_local_reason";
            return Outcome::Retryable(transient);
        }
    });
    kernel.Resolve();
    assert(kernel.LastResolutionJson().find("callback_local_reason") != std::string::npos);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "src/common/Utilities"),
            "-I",
            str(ROOT / "src/common/Logging"),
            "-I",
            str(ROOT / "src/common/Debugging"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_live_route_function_does_not_reintroduce_direct_cheat_actions() -> None:
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    start = source.index("bool BotWorldPopulationMgr::TryValidationRouteObjective(")
    end = source.index("\nbool BotWorldPopulationMgr::IsBossContext", start)
    route = source[start:end]
    for forbidden in (
        "ResurrectPlayer(",
        "NearTeleportTo(",
        "TeleportTo(",
        "SetHealth(",
        "SetPower(",
        "AddThreat(",
    ):
        assert forbidden not in route
