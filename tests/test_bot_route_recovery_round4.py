"""Post-wipe recovery path (round 4, package T).

Round 3 BWD batch (/tmp/blackwing_descent_10n-r03-b1-20260925T200656Z, DVC
artifacts/cata_raid_program/round3_batch1_20260925.tar.gz): three shards
engaged their boss, wiped and plateaued in recovery.

- Chimaeron: the lower-wing recovery ride engaged when the first member was
  alive at the entrance, but at every ~2 s rest window the pre-pull
  consumable candidate (Mechanic, utility 12, GCD/cast/target lanes) beat the
  ride's surface walk (Mechanic, utility 6, movement/GCD/cast): only the three
  healers the candidate skips ever rode; the seven others were cut off by
  transport_rest_window_too_short until the plateau. Transport window stages
  now outrank ordinary candidates (Survival).
- Maloriak: the ride completed (route_recovery_complete); then the encounter's
  plan owned every member at the elevator exit and its entrance-line staging
  moves (mechanic owner, 3 yd above the target, a path through the lab 10 yd
  lower) were refused route_destination_path_control_level_gap ~19 times per
  non-tank. A resurrected member now returns under route ownership until it
  is within 35 yd of the boss node (BotValidationRouteRecoveryReturn.h).
- Omnotron: the native full-wipe recovery hold waited for a ready check the
  shard coordinator never sent (harness patch H by the Omnotron agent). After
  it, the same return walks the members from the entrance.
- Chimaeron also stays asleep after the reset until Finkle's gossip; the
  encounter rows now redo the route's waking interaction after a wipe at that
  node (row field recovery_interaction).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from tools.bot_ml import build_validation_scenario_manifests as builder


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
INCLUDES = ["src/server/game", "src/server/game/Entities/Object", "src/common",
            "src/common/Utilities", "src/common/Logging", "src/common/Debugging"]
CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"

FINKLE_INTERACTION = (
    '{"action": "gossip_select_sequence", "entry": 44202, "menus": [11812, 11834, 11835, '
    '11836, 11837], "option": 0, "owner_role": "dps", "max_attempts": 3, '
    '"retry_interval_ms": 3000, "timeout_ms": 90000}'
)
FINKLE_COMPLETION = '{"kind": "aura_present", "entry": 44418, "spell_id": 82705}'


def _compile_and_run(tmp_path: Path, program: str) -> str:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    return subprocess.run(
        [str(binary)], check=True, cwd=ROOT, capture_output=True, text=True
    ).stdout


def _code(text: str) -> str:
    text = re.sub(r"//.*", "", text)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _source(name: str) -> str:
    return (BOTS / name).read_text(encoding="utf-8")


def _function(text: str, signature: str) -> str:
    start = text.index(signature)
    brace = text.index("{", start)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise AssertionError(signature)


# ---------------------------------------------------------------------------
# Chimaeron: the ride's rest-window stages win the Mechanic priority on utility
# ---------------------------------------------------------------------------
WINDOW_STAGES = ("transport_board_path", "transport_board", "transport_disembark_path",
                 "transport_leave", "transport_surface_walk", "transport_drop_step_off",
                 "transport_disembark_walk")
FALL_STAGES = ("transport_drop_fall", "transport_drop_land")
FREE_STAGES = ("transport_wait", "transport_exit_path", "transport_approach_start")


def test_transport_window_stages_use_the_window_utility() -> None:
    runtime = _code(_source("BotWorldPopulationMgrValidationRouteNativeRuntime.cpp"))
    assert "constexpr float TransportWindowUtility = 20.0f;" in runtime
    assert ("constexpr BotActionArbitration::Priority TransportFallPriority =\n"
            "    BotActionArbitration::Priority::Survival;") in runtime
    assert "constexpr float TransportFallUtility = 6.0f;" in runtime
    transport = _function(runtime, "void RunTransport(")
    for stage in WINDOW_STAGES:
        assert (f'Submit(input, callbacks, "{stage}", transportGuid,\n'
                "                BotActionArbitration::Priority::Mechanic, TransportWindowUtility,") in transport, stage
    # Only the fall and the landing, which cannot pause mid-air, take Survival.
    for stage in FALL_STAGES:
        assert (f'Submit(input, callbacks, "{stage}", transportGuid,\n'
                "                TransportFallPriority, TransportFallUtility,") in transport, stage
    # Walks that are not bound to a rest window keep their ordinary weight.
    for stage in FREE_STAGES:
        assert (f'Submit(input, callbacks, "{stage}", transportGuid,\n'
                "                BotActionArbitration::Priority::Mechanic, 4.0f,") in transport, stage
    hold = _function(runtime, "void SubmitHold(")
    for marker in ('bool const falling = ownsCasting && reason == "transport_drop_falling";',
                   "candidate.ActionPriority = falling ? TransportFallPriority\n        : BotActionArbitration::Priority::Mechanic;",
                   "candidate.UtilityScore = falling ? TransportFallUtility\n        : ownsCasting ? TransportWindowUtility : 1.0f;"):
        assert marker in hold, marker


KERNEL_REPLAY = r"""
#include "Bots/BotActionArbiter.h"
#include <cstdio>
#include <string>

using namespace BotActionArbitration;
static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

static std::string Status(Resolution const& resolution, std::string const& key)
{
    for (CandidateTrace const& trace : resolution.Trace)
        if (trace.Key == key)
            return trace.Status;
    return "missing";
}

static Candidate Make(std::string key, Priority priority, float utility, ResourceMask lanes)
{
    Candidate candidate;
    candidate.Key = std::move(key);
    candidate.Source = "replay";
    candidate.ActionPriority = priority;
    candidate.UtilityScore = utility;
    candidate.RequiredResources = lanes;
    candidate.Attempt = [] { return Outcome::Committed("submitted"); };
    return candidate;
}

// One member's tick (round 3 Chimaeron b1..b10 at the lip): the pre-pull
// consumable hold (SubmitRaidPrepullConsumableCandidate), a transport stage,
// and optionally a Survival defensive (Magmaw Mangle defensive: 400).
static Resolution RestWindowTick(Priority stagePriority, float stageUtility, bool defensive)
{
    Kernel kernel;
    kernel.Begin(1000);
    kernel.Submit(Make("consumable", Priority::Mechanic, 12.0f,
        Uses(Resource::GlobalCooldown, Resource::Cast, Resource::Target)));
    kernel.Submit(Make("stage", stagePriority, stageUtility,
        Uses(Resource::Movement, Resource::GlobalCooldown, Resource::Cast)));
    if (defensive)
        kernel.Submit(Make("defensive", Priority::Survival, 400.0f,
            Uses(Resource::GlobalCooldown, Resource::Cast)));
    return kernel.Resolve();
}

int main()
{
    // Round 3: the walk (Mechanic 6) lost the GCD/cast lanes to the consumable.
    Resolution const before = RestWindowTick(Priority::Mechanic, 6.0f, false);
    CHECK(Status(before, "consumable") == "attempted");
    CHECK(Status(before, "stage") == "resource_conflict");
    // Round 4: a window stage (Mechanic 20) takes its lanes first.
    Resolution const walk = RestWindowTick(Priority::Mechanic, 20.0f, false);
    CHECK(Status(walk, "stage") == "attempted");
    CHECK(Status(walk, "consumable") == "resource_conflict");
    // A boarding member under attack still gets its Survival defensive.
    Resolution const attacked = RestWindowTick(Priority::Mechanic, 20.0f, true);
    CHECK(Status(attacked, "defensive") == "attempted");
    CHECK(Status(attacked, "stage") == "resource_conflict");
    // The fall (Survival 6) beats every Mechanic candidate, and yields to the
    // Survival defensives and hazard exits (200-500) on utility.
    Resolution const fall = RestWindowTick(Priority::Survival, 6.0f, false);
    CHECK(Status(fall, "stage") == "attempted");
    CHECK(Status(fall, "consumable") == "resource_conflict");
    Resolution const fallAttacked = RestWindowTick(Priority::Survival, 6.0f, true);
    CHECK(Status(fallAttacked, "defensive") == "attempted");
    return failures ? 1 : 0;
}
"""


def test_kernel_replay_round3_rest_window(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, KERNEL_REPLAY)


# ---------------------------------------------------------------------------
# Maloriak / Omnotron: the member's return belongs to the route (composition
# raid rows only)
# ---------------------------------------------------------------------------
RETURN_REPLAY = r"""
#include "Bots/BotValidationRouteRecoveryReturn.h"
#include <cmath>
#include <cstdio>
#include <string>

using namespace BotValidationRouteRecoveryReturn;
static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

static float Dist(float ax, float ay, float az, float bx, float by, float bz)
{
    return std::sqrt((ax - bx) * (ax - bx) + (ay - by) * (ay - by) + (az - bz) * (az - bz));
}

static Input At(float distance, std::uint64_t nowMs, bool alive = true, bool inInstance = true)
{
    Input input;
    input.AttemptId = 1;
    input.RouteGeneration = 3;
    input.Eligible = true;
    input.Alive = alive;
    input.InRouteInstance = inInstance;
    input.DistanceToAnchor = distance;
    input.NowMs = nowMs;
    return input;
}

static bool Is(Decision const& decision, Verdict step) { return decision.Step == step; }

int main()
{
    // Scope: a composition raid row's boss node with an anchor, route enabled.
    CHECK(Eligible(true, true, true, true, true));
    CHECK(!Eligible(true, false, true, true, true));   // Stonecore: not a raid instance
    CHECK(!Eligible(true, true, false, true, true));   // accepted Magmaw, legacy rows
    CHECK(!Eligible(true, true, true, false, true));   // trash, regroup, transport nodes
    CHECK(!Eligible(true, true, true, true, false));
    CHECK(!Eligible(false, true, true, true, true));   // calibration: no route

    Memory memory;
    CHECK(Is(Decide(memory, At(10.0f, 0)), Verdict::Idle));   // never armed

    // Omnotron: resurrected at the instance entrance, node anchor 177 yd away.
    float const omnotron = Dist(-345.872f, -224.344f, 193.127f, -324.78f, -399.078f, 213.825f);
    CHECK(omnotron > 170.0f && omnotron < 180.0f);
    Arm(memory, 1, 3);
    CHECK(Is(Decide(memory, At(omnotron, 1000, false)), Verdict::Idle));        // ghost
    CHECK(Is(Decide(memory, At(omnotron, 2000, true, false)), Verdict::Idle));  // mid-teleport
    CHECK(memory.Pending);
    CHECK(Is(Decide(memory, At(omnotron, 3000)), Verdict::Returning));
    CHECK(Is(Decide(memory, At(60.0f, 30000)), Verdict::Returning));
    CHECK(Is(Decide(memory, At(HandOffYards, 31000)), Verdict::Arrived));
    CHECK(!memory.Pending);
    CHECK(Is(Decide(memory, At(omnotron, 32000)), Verdict::Idle));        // once only

    // Out of scope an armed memory is dropped at once (never walks).
    Arm(memory, 1, 3);
    Input legacy = At(omnotron, 1000);
    legacy.Eligible = false;
    CHECK(Is(Decide(memory, legacy), Verdict::Idle) && !memory.Pending);

    // Maloriak: at the lower-wing elevator exit after the ride, 266 yd away;
    // its staging line (-107.5, -434) is 29 yd from the anchor, inside the hand-off.
    float const maloriak = Dist(-224.0f, -224.605f, 76.6462f, -105.7865f, -462.5781f, 73.53668f);
    CHECK(maloriak > 260.0f);
    CHECK(Dist(-107.5f, -434.0f, 73.6f, -105.7865f, -462.5781f, 73.53668f) < HandOffYards);
    Arm(memory, 1, 3);
    CHECK(Is(Decide(memory, At(maloriak, 1000)), Verdict::Returning));
    Input moved = At(maloriak, 2000);
    moved.RouteGeneration = 4;
    CHECK(Is(Decide(memory, moved), Verdict::Idle) && !memory.Pending);
    Arm(memory, 1, 3);
    Input retried = At(maloriak, 2000);
    retried.AttemptId = 2;
    CHECK(Is(Decide(memory, retried), Verdict::Idle) && !memory.Pending);

    // Bounded: NoProgressMs of observed time without coming 5 yd closer.
    Arm(memory, 1, 3);
    std::uint64_t t = 1000;
    CHECK(Is(Decide(memory, At(250.0f, t)), Verdict::Returning));
    for (t = 2000; t < 1000 + NoProgressMs; t += 1000)                // waits at a lip
        CHECK(Is(Decide(memory, At(248.0f, t)), Verdict::Returning));
    Decision const stuck = Decide(memory, At(248.0f, 1000 + NoProgressMs));
    CHECK(Is(stuck, Verdict::Unreachable) && std::string(stuck.Reason) == "no_progress");
    CHECK(!memory.Pending);
    // Progress resets the clock; a pause (a native recovery hold) does not count.
    Arm(memory, 1, 3);
    CHECK(Is(Decide(memory, At(250.0f, 1000)), Verdict::Returning));
    CHECK(Is(Decide(memory, At(240.0f, 100000)), Verdict::Returning));  // 99 s gap: paused
    CHECK(Is(Decide(memory, At(240.0f, 101000)), Verdict::Returning));
    CHECK(Is(Decide(memory, At(230.0f, 110000)), Verdict::Returning));  // 10 yd closer
    for (t = 111000; t < 110000 + NoProgressMs; t += 1000)
        CHECK(Is(Decide(memory, At(229.0f, t)), Verdict::Returning));
    CHECK(Is(Decide(memory, At(229.0f, 110000 + NoProgressMs)), Verdict::Unreachable));

    // An engaged ride holding the member at its exit for the last living
    // rider pauses the clock: a member that reached the elevator 120 s after
    // the others no longer fails the ones below (the ride's 240 s bounds it).
    Arm(memory, 1, 3);
    CHECK(Is(Decide(memory, At(266.0f, 1000)), Verdict::Returning));
    for (t = 2000; t <= 1000 + 2 * NoProgressMs; t += 1000)
    {
        Input held = At(266.0f, t);
        held.RideHolds = true;
        CHECK(Is(Decide(memory, held), Verdict::Returning));
    }
    for (std::uint64_t u = t; u < t + NoProgressMs - 1000; u += 1000)
        CHECK(Is(Decide(memory, At(266.0f, u)), Verdict::Returning));
    CHECK(Is(Decide(memory, At(266.0f, t + NoProgressMs)), Verdict::Unreachable));

    // Nefarian: beyond a boarding-only transport. A wipe there fails at once;
    // a member released while the fight goes on stays out of it.
    Arm(memory, 1, 3);
    Input nefarian = At(300.0f, 1000);
    nefarian.Blocked = true;
    nefarian.WipedHere = true;
    Decision const blocked = Decide(memory, nefarian);
    CHECK(Is(blocked, Verdict::Unreachable)
        && std::string(blocked.Reason) == "boarding_without_recovery");
    Arm(memory, 1, 3);
    nefarian.WipedHere = false;
    CHECK(Is(Decide(memory, nefarian), Verdict::Idle) && !memory.Pending);

    // Resurrected at its corpse beside the boss: arrived at once.
    Arm(memory, 1, 3);
    CHECK(Is(Decide(memory, At(12.0f, 1000)), Verdict::Arrived) && !memory.Pending);
    // The hand-off lies beyond every route arrival radius (8, 18, 30 yd).
    CHECK(HandOffYards > 30.0f);
    CHECK(std::string(UnreachablePrefix) == "route_recovery_return_unreachable:");
    return failures ? 1 : 0;
}
"""


def test_recovery_return_replay(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, RETURN_REPLAY)


def test_return_is_armed_in_scope_by_a_release_and_yields_the_boss_plans() -> None:
    preparation = _code(_source("BotWorldPopulationMgrUpdateBotPreparation.cpp"))
    arm = preparation.index("context.ArmValidationRecoveryReturn();")
    assert preparation.index("if (context.State.NativeReleaseRequested\n            && context.State.NativeRecoveryEpisodeStartedMs)") < arm
    # Armed before the release episode is cleared on resurrection.
    assert arm < preparation.index("context.State.NativeReleaseRequested = false;")

    kernel = _code(_source("BotWorldPopulationMgrUpdateBotKernelPreparation.cpp"))
    assert "nativeInput.BossResetGeneration = Cohort().Raid.BossResetGeneration;" in kernel
    assert ("nativeInput.CompositionRecovery = Cohort().Raid.RaidInstance\n"
            "                        && routeNode.CompositionRecovery;") in kernel
    observe = kernel.index("context.ValidationRecoveryReturning = context.ObserveValidationRecoveryReturn();")
    assert observe < kernel.index("if (!context.ValidationRecoveryReturning)\n            SubmitRaidPrepullConsumableCandidate(context);")

    decision = _code(_source("BotWorldPopulationMgrUpdateBotDecision.cpp"))
    order = [decision.index(marker) for marker in (
        "PrepareValidationKernel(context);",
        "if (context.ValidationRecoveryReturning)\n        context.YieldEncounterOwnershipForRecoveryReturn();",
        "SubmitAdaptiveKernelCandidates(context);",
        "SubmitValidationKernelFallbackCandidates(context);",
    )]
    assert order == sorted(order)

    adapter = _code(_source("BotWorldPopulationMgrValidationRouteRecoveryReturn.cpp"))
    node = _function(adapter, "BotWorldPopulationMgr::BotUpdateContext::RecoveryReturnNode(bool& eligible) const")
    for marker in ("eligible = BotValidationRouteRecoveryReturn::Eligible(cohort.Config.ValidationRouteEnable,\n"
                   "        cohort.Raid.RaidInstance, node.CompositionRecovery,\n"
                   '        cohort.Config.ValidationRouteKind == "boss", anchorValid);',
                   "node.NodeId != cohort.Config.ValidationRouteNodeId"):
        assert marker in node, marker
    arm_fn = _function(adapter, "void BotWorldPopulationMgr::BotUpdateContext::ArmValidationRecoveryReturn()")
    assert "RecoveryReturnNode(eligible);\n    if (eligible)\n        BotValidationRouteRecoveryReturn::Arm(" in arm_fn
    yielded = _function(adapter, "void BotWorldPopulationMgr::BotUpdateContext::YieldEncounterOwnershipForRecoveryReturn(")
    for owner in ("Magmaw", "Omnotron", "Maloriak", "Chimaeron", "Atramedes", "Nefarian"):
        assert f"context.Adaptive{owner}OwnsNode = false;" in yielded, owner
    for cleared in ("context.AdaptiveMagmawMovements = {};", "context.AdaptiveOmnotronMovement.reset();",
                    "context.AdaptiveMaloriak.reset();", "context.AdaptiveChimaeronMovement.reset();",
                    "context.AdaptiveAtramedesMovement.reset();", "context.AdaptiveNefarianMovement.reset();"):
        assert cleared in yielded, cleared
    # The Drudge trash owner keeps its typed recovery.
    assert "AdaptiveDrudge" not in yielded
    observe_fn = _function(adapter, "bool BotWorldPopulationMgr::BotUpdateContext::ObserveValidationRecoveryReturn(")
    for marker in ('"route_recovery_return:"', '"route_recovery_returned:"',
                   "std::string(Return::UnreachablePrefix) + nodeId",
                   "manager.FailValidationAttemptOnce(State, Bot, reason,",
                   "BotValidationRouteNative::WipedSinceBaseline(node->RecoveryReturnBaseline, scope)",
                   "input.Blocked = node && !node->RecoveryReturnBlockedBy.empty();",
                   "input.NowMs = DecisionNowMs;",
                   "input.RideHolds = input.RideHolds || BotValidationRouteNative::RecoveryRideHoldsMember(\n"
                   "                transit.Runtime.Started && transit.Runtime.Scope == scope, transit.Transport,\n"
                   "                Bot->GetPositionZ(), Bot->GetTransport() != nullptr);",
                   "manager.IsValidationCohortMemberInOriginalInstance(State, Bot)"):
        assert marker in observe_fn, marker
    # The manager header (with the cohort API) is at its line budget: the
    # return lives on the update context.
    context = _code(_source("BotWorldPopulationMgrUpdateContext.h"))
    for declaration in ("void ArmValidationRecoveryReturn();", "bool ObserveValidationRecoveryReturn();",
                        "void YieldEncounterOwnershipForRecoveryReturn();",
                        "ValidationRouteManifestNode* RecoveryReturnNode(bool& eligible) const;"):
        assert declaration in context, declaration
    assert "RecoveryReturn" not in _source("BotWorldPopulationMgr.h")
    state = _code(_source("BotWorldPopulationMgrBotState.h"))
    assert "BotValidationRouteRecoveryReturn::Memory ValidationRecoveryReturn;" in state
    route_state = _code(_source("BotWorldPopulationMgrRouteState.h"))
    for field in ("bool CompositionRecovery = false;", "std::string RecoveryReturnBlockedBy;",
                  "BotValidationRouteNative::RuntimeScope RecoveryReturnBaseline;"):
        assert field in route_state, field
    manifest = _code(_source("BotWorldPopulationMgrValidationRouteManifest.cpp"))
    for marker in ('ExtractJsonBoolField(routeJson, "composition_recovery", node.CompositionRecovery);',
                   'ExtractJsonStringField(routeJson, "recovery_return_blocked_by");',
                   '"recovery_return_blocked_by_invalid:"'):
        assert marker in manifest, marker


def _scenarios() -> dict[str, dict]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    rows = list(config.get("scenarios") or []) + list(config.get("diagnostic_scenarios") or [])
    return {str(row["id"]): row for row in rows if isinstance(row, dict) and row.get("id")}


def test_hand_off_stays_beyond_every_boss_route_arrival_radius() -> None:
    # A returning ranged member inside the arrival radius would get the route
    # adapter's boss engagement and could pull a sleeping Chimaeron without
    # Finkle's Mixture (Chimaeron round-4 review).
    header = _source("BotValidationRouteRecoveryReturn.h")
    hand_off = float(re.search(r"constexpr float HandOffYards = ([0-9.]+)f;", header).group(1))
    maximum = float(re.search(r"constexpr float MaxRouteArrivalRadiusYards = ([0-9.]+)f;", header).group(1))
    assert "static_assert(HandOffYards > MaxRouteArrivalRadiusYards," in header
    manager = _source("BotWorldPopulationMgr.cpp")
    radii = [float(value) for value in re.findall(
        r"routeArrivalRadius = (?:routeProfile\.MovementDirective == \"melee\" \? )?([0-9.]+)f(?: : ([0-9.]+)f)?;",
        manager) for value in value if value]
    assert sorted(radii) == [8.0, 18.0, 30.0], radii
    assert max(radii) <= maximum < hand_off


def test_accepted_magmaw_and_legacy_scenarios_are_not_gated() -> None:
    # Accepted results stay exactly reproducible. The accepted Magmaw
    # diagnostic, the legacy shards and full route, and every dungeon carry
    # no composition_recovery row flag, so the runtime never arms a return
    # and never walks corridor legs; Stonecore is not a raid instance either.
    scenarios = _scenarios()
    magmaw = scenarios["blackwing_descent_10n_magmaw_diagnostic"]
    assert not builder.composition_recovery(magmaw)
    for scenario_id, scenario in scenarios.items():
        opted = builder.composition_recovery(scenario)
        assert opted == bool(scenario.get("composition_id")), scenario_id
        if scenario_id.startswith("stonecore") or scenario_id == "blackwing_descent_10n" \
                or scenario_id.endswith("_diagnostic") and "_c0_" not in scenario_id:
            assert not opted, scenario_id
    for scenario_id in ("blackwing_descent_10n_full_c0", "blackwing_descent_10n_omnotron_c0_diagnostic",
                        "blackwing_descent_10n_maloriak_c0_diagnostic",
                        "blackwing_descent_10n_chimaeron_c0_diagnostic"):
        assert builder.composition_recovery(scenarios[scenario_id]), scenario_id
    source = (ROOT / "tools/bot_ml/build_validation_scenario_manifests.py").read_text(encoding="utf-8")
    assert ('            if composition_recovery(scenario):\n'
            '                route["composition_recovery"] = True\n'
            '                blocked_by = blockers.get(str(step.get("node_id") or ""))\n'
            '                if blocked_by:\n'
            '                    route["recovery_return_blocked_by"] = blocked_by\n') in source
    # The runtime reads nothing else: without the row flag (or outside a raid
    # instance) the return never arms and the planner never asks for legs.
    # (Corridor legs read the same row flag: tests/test_bot_native_path_corridor_leg.py.)
    adapter = _code(_source("BotWorldPopulationMgrValidationRouteRecoveryReturn.cpp"))
    assert "cohort.Raid.RaidInstance, node.CompositionRecovery," in adapter
    manifest = _code(_source("BotWorldPopulationMgrValidationRouteManifest.cpp"))
    # A blocker without the opt-in is refused at load.
    assert "(!node.CompositionRecovery\n                || !BotValidationRouteNative::ValidNodeId(" in manifest


def test_builder_blocks_the_return_beyond_the_nefarian_descent_only() -> None:
    scenarios = _scenarios()
    for scenario_id, scenario in scenarios.items():
        parent = scenarios.get(str(scenario.get("diagnostic_parent_scenario_id") or ""), {})
        blockers = builder.recovery_return_blockers(scenario.get("route") or [], parent.get("route") or [])
        nodes = {str(step.get("node_id")) for step in scenario.get("route") or []}
        emitted = {node: blocker for node, blocker in blockers.items()
                   if node in nodes and builder.composition_recovery(scenario)}
        if scenario_id in ("blackwing_descent_10n_full_c0", "blackwing_descent_10n_nefarian_c0_diagnostic"):
            assert emitted == {"bwd.nefarian.encounter": "bwd.nefarian.descent"}, scenario_id
        else:
            assert emitted == {}, scenario_id
    # The lower-wing elevator is a ride (it has a way back): never a blocker.
    full = scenarios["blackwing_descent_10n_full_c0"]["route"]
    blockers = builder.recovery_return_blockers(full)
    assert "bwd.transit.lower_wing_elevator" not in blockers.values()


# ---------------------------------------------------------------------------
# Chimaeron: recovery wakes (row field recovery_interaction)
# ---------------------------------------------------------------------------
WAKE_REPLAY = r'''
#include "Bots/BotValidationRouteNativeContract.h"
#include "Bots/BotValidationRouteNativeLogic.h"
#include "Bots/BotValidationRouteNativeRecovery.h"
#include <algorithm>
#include <cstdio>
#include <string>
#include <vector>

using namespace BotValidationRouteNative;
static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

static std::string const Interaction = INTERACTION;
static std::string const Completion = COMPLETION;

static std::string Row(std::string const& id, std::string const& interaction = Interaction,
    std::string const& completion = Completion, std::string const& extra = "")
{
    return "{\"node_id\": \"" + id + "\", \"interaction\": " + interaction
        + ", \"completion\": " + completion + extra + "}";
}

static ParseError Wakes(std::string const& text, std::vector<RecoveryInteraction>& out)
{
    Json value;
    if (ParseError error = ParseArrayText(text, value))
        return error;
    return ParseRecoveryInteractions(value, out);
}

int main()
{
    std::vector<RecoveryInteraction> wakes;
    CHECK(!Wakes("[" + Row("bwd.chimaeron.finkle") + "]", wakes));
    CHECK(wakes.size() == 1 && wakes[0].NodeId == "bwd.chimaeron.finkle");
    CHECK(wakes[0].Interaction.Declared && wakes[0].Interaction.Entry == 44202);
    CHECK(wakes[0].Interaction.TimeoutMs == 90000 && wakes[0].Interaction.MaxAttempts == 3);
    CHECK(wakes[0].Completion.Kind == CompletionKind::AuraPresent);
    // Fail closed: unknown fields, missing contracts, duplicates, count, shape.
    ParseError error = Wakes("[" + Row("bwd.chimaeron.finkle", Interaction, Completion, ", \"x\": 1") + "]", wakes);
    CHECK(error.Kind == ParseError::Code::UnknownField && error.Detail == "recovery_interaction.x");
    CHECK(Wakes("[{\"node_id\": \"bwd.chimaeron.finkle\", \"interaction\": " + Interaction + "}]", wakes).Detail
        == "recovery_interaction_contract_missing");
    CHECK(Wakes("[" + Row("bwd.chimaeron.finkle") + ", " + Row("bwd.chimaeron.finkle") + "]", wakes).Detail
        == "recovery_interaction_duplicate:bwd.chimaeron.finkle");
    CHECK(Wakes("[" + Row("a.b.c") + ", " + Row("a.b.d") + ", " + Row("a.b.e") + "]", wakes).Detail
        == "recovery_interaction_count");
    CHECK(Wakes("[]", wakes).Detail == "recovery_interaction_count");
    CHECK(Wakes("[" + Row("Bad Id") + "]", wakes).Detail == "recovery_interaction_node_id");
    error = Wakes("[" + Row("bwd.chimaeron.finkle", Interaction, "{\"kind\": \"nope\"}") + "]", wakes);
    CHECK(error && error.Detail.rfind("recovery_interaction:", 0) == 0);

    // The wake's creatures stay observable at the node that redoes it.
    NodeContract node;
    CHECK(!Wakes("[" + Row("bwd.chimaeron.finkle") + "]", node.RecoveryInteractions));
    CHECK(node.Declared());
    std::vector<std::uint32_t> const entries = ObservedCreatureEntries(node);
    CHECK(std::find(entries.begin(), entries.end(), 44202u) != entries.end());
    CHECK(std::find(entries.begin(), entries.end(), 44418u) != entries.end());

    // The return's wipe baseline: the first scope seen at the node in this
    // attempt and route generation.
    RuntimeScope baseline;
    CHECK(!WipedSinceBaseline(baseline, { 1, 0, 4 }));
    CHECK(!WipedSinceBaseline(baseline, { 1, 0, 4 }));
    CHECK(WipedSinceBaseline(baseline, { 1, 1, 4 }));      // wiped at the encounter
    RuntimeScope earlier;                                   // wiped on an earlier node
    CHECK(!WipedSinceBaseline(earlier, { 1, 1, 4 }));
    CHECK(WipedSinceBaseline(earlier, { 1, 2, 4 }));
    CHECK(!WipedSinceBaseline(earlier, { 2, 2, 4 }));       // a new attempt re-baselines
    CHECK(!WipedSinceBaseline(earlier, { 2, 2, 5 }));       // so does the next node

    // A wake triggers on a wipe here, or (composition raid rows) on an observed
    // native reset without a wipe; either counts once it held 45 s.
    using T = RecoveryTrigger;
    RecoveryBaseline wake;
    std::uint64_t const t0 = 1790366000000ull;
    CHECK(ObserveRecoveryTrigger(wake, { 1, 0, 4 }, 0, true, t0) == T::None);
    CHECK(ObserveRecoveryTrigger(wake, { 1, 1, 4 }, 1, true, t0 + 1000) == T::Settling);   // wiped
    CHECK(ObserveRecoveryTrigger(wake, { 1, 1, 4 }, 1, true, t0 + 1000 + RecoveryWakeSettleMs - 1) == T::Settling);
    CHECK(ObserveRecoveryTrigger(wake, { 1, 1, 4 }, 1, true, t0 + 1000 + RecoveryWakeSettleMs) == T::Triggered);
    RecoveryBaseline evade;                                 // Chimaeron evades, nobody dies
    CHECK(ObserveRecoveryTrigger(evade, { 1, 0, 4 }, 0, true, t0) == T::None);
    CHECK(ObserveRecoveryTrigger(evade, { 1, 0, 4 }, 1, true, t0 + 1000) == T::Settling);
    CHECK(ObserveRecoveryTrigger(evade, { 1, 0, 4 }, 1, true, t0 + 1000 + RecoveryWakeSettleMs) == T::Triggered);
    RecoveryBaseline legacy;                                // outside the opt-in: wipes only
    CHECK(ObserveRecoveryTrigger(legacy, { 1, 0, 4 }, 0, false, t0) == T::None);
    CHECK(ObserveRecoveryTrigger(legacy, { 1, 0, 4 }, 1, false, t0 + 1000 + RecoveryWakeSettleMs) == T::None);
    CHECK(ObserveRecoveryTrigger(legacy, { 1, 1, 4 }, 1, false, t0 + 2000) == T::Settling);
    CHECK(ObserveRecoveryTrigger(legacy, { 1, 1, 4 }, 1, false, t0 + 2000 + RecoveryWakeSettleMs) == T::Triggered);
    RecoveryBaseline earlierReset;                          // a reset on an earlier node
    CHECK(ObserveRecoveryTrigger(earlierReset, { 1, 1, 5 }, 3, true, t0) == T::None);
    CHECK(ObserveRecoveryTrigger(earlierReset, { 1, 1, 5 }, 3, true, t0 + 10 * RecoveryWakeSettleMs) == T::None);
    CHECK(RecoveryWakeSettleMs >= 30000 + 10000);           // the 30 s respawns, with margin

    // Every reset settles 45 s of its own (Atramedes replay): he respawns awake
    // 30 s after each evade (EVENT_RESPAWN_ATRAMEDES summons without an
    // existence check), so his bell wake must never run inside that window.
    using S = RecoveryWakeStep;
    RecoveryBaseline bell;
    std::uint64_t now = t0;
    auto tick = [&](std::uint64_t resets, bool bossPresent, bool inCombat)
    {
        RuntimeScope const scope{ 1, 0, 6 };
        T const trigger = ObserveRecoveryTrigger(bell, scope, resets, true, now);
        S const step = DecideRecoveryWake(trigger == T::Triggered, false, inCombat, bossPresent, true);
        RetireRecoveryTrigger(bell, scope, resets, trigger, step, bossPresent, inCombat);
        return step;
    };
    CHECK(tick(0, true, false) == S::Idle);                 // first seen: baseline
    now = t0 + 60000;                                       // reset 1: he despawns
    for (std::uint64_t end = now + 30000; now < end; now += 1000)
        CHECK(tick(1, false, false) == S::Idle);            // settling: the bell stays still
    for (std::uint64_t end = t0 + 60000 + RecoveryWakeSettleMs; now < end; now += 1000)
        CHECK(tick(1, true, false) == S::Idle);             // respawned awake at +30 s
    CHECK(tick(1, true, false) == S::Idle);                 // settled, satisfied: consumed
    CHECK(bell.Resets == 1 && bell.TriggeredAtMs == 0);
    now += 120000;                                          // reset 2, the same node
    for (std::uint64_t end = now + 30000; now < end; now += 1000)
        CHECK(tick(2, false, false) == S::Idle);            // settles again: no second summon
    now += RecoveryWakeSettleMs;
    CHECK(tick(2, true, false) == S::Idle && bell.Resets == 2);

    // Chimaeron: the wake runs after the settle, completes (Mixture observed)
    // and is consumed; a second reset settles again before the next wake.
    RecoveryBaseline finkle;
    now = t0;
    RuntimeScope const room{ 1, 0, 4 };
    CHECK(ObserveRecoveryTrigger(finkle, room, 0, true, now) == T::None);
    now += 1000;
    CHECK(ObserveRecoveryTrigger(finkle, room, 1, true, now) == T::Settling);
    now += RecoveryWakeSettleMs;
    T trigger = ObserveRecoveryTrigger(finkle, room, 1, true, now);
    CHECK(trigger == T::Triggered);
    CHECK(DecideRecoveryWake(true, false, false, false, true) == S::Engage);
    RetireRecoveryTrigger(finkle, room, 1, trigger, S::Engage, false, false);
    CHECK(finkle.TriggeredAtMs != 0);                       // running: not consumed
    RetireRecoveryTrigger(finkle, room, 1, trigger, S::Complete, true, false);
    CHECK(finkle.Resets == 1 && finkle.TriggeredAtMs == 0); // completed: consumed
    now += 60000;
    CHECK(ObserveRecoveryTrigger(finkle, room, 1, true, now) == T::None);
    CHECK(ObserveRecoveryTrigger(finkle, room, 2, true, now + 1000) == T::Settling);
    // A patrol (or the fight) engaging first restarts the settle after it.
    RetireRecoveryTrigger(finkle, room, 2, T::Settling, S::Idle, false, true);
    CHECK(finkle.TriggeredAtMs == 0);
    CHECK(ObserveRecoveryTrigger(finkle, room, 2, true, now + 20000) == T::Settling);
    CHECK(ObserveRecoveryTrigger(finkle, room, 2, true, now + 20000 + RecoveryWakeSettleMs) == T::Triggered);
    // A wipe after a consumed wake settles too (the scope is re-taken).
    RetireRecoveryTrigger(finkle, room, 2, T::Triggered, S::Complete, true, true);
    CHECK(ObserveRecoveryTrigger(finkle, { 1, 1, 4 }, 3, true, now + 200000) == T::Settling);

    // Engage only after a wipe here, out of combat, assembled, not satisfied.
    CHECK(DecideRecoveryWake(true, false, false, false, true) == RecoveryWakeStep::Engage);
    CHECK(DecideRecoveryWake(false, false, false, false, true) == RecoveryWakeStep::Idle);
    CHECK(DecideRecoveryWake(true, false, true, false, true) == RecoveryWakeStep::Idle);
    CHECK(DecideRecoveryWake(true, false, false, true, true) == RecoveryWakeStep::Idle);  // respawned awake
    CHECK(DecideRecoveryWake(true, false, false, false, false) == RecoveryWakeStep::Idle);
    CHECK(DecideRecoveryWake(true, true, false, false, false) == RecoveryWakeStep::Wake);
    CHECK(DecideRecoveryWake(true, true, false, true, true) == RecoveryWakeStep::Complete);
    CHECK(DecideRecoveryWake(true, true, true, false, true) == RecoveryWakeStep::Complete);

    // The whole party, alive in the instance and at the node; the first
    // member holding it is named with why.
    std::vector<RecoveryWakeView> party(10, RecoveryWakeView{ 0, true, true, false, 20.0f });
    for (std::size_t i = 0; i < party.size(); ++i)
        party[i].Guid = 11005001 + i;
    CHECK(RecoveryPartyAssembled(party) && !RecoveryEncounterEngaged(party));
    CHECK(RecoveryAssemblyHolder(party).Guid == 0);
    party[3].DistanceToAnchor = 272.7f;                     // still at the elevator exit
    CHECK(!RecoveryPartyAssembled(party));
    CHECK(RecoveryAssemblyHolder(party).Guid == 11005004
        && std::string(RecoveryAssemblyHolder(party).Reason) == "away");
    party[3].DistanceToAnchor = 20.0f;
    party[5].Alive = false;                                  // still dead
    CHECK(!RecoveryPartyAssembled(party));
    CHECK(RecoveryAssemblyHolder(party).Guid == 11005006
        && std::string(RecoveryAssemblyHolder(party).Reason) == "dead");
    party[5].Alive = true;
    party[6].OnRouteInstance = false;                        // mid-teleport
    CHECK(std::string(RecoveryAssemblyHolder(party).Reason) == "off_route");
    party[6].OnRouteInstance = true;
    party[7].InCombat = true;
    CHECK(RecoveryEncounterEngaged(party));
    CHECK(!RecoveryPartyAssembled({}));

    // The wait for the party is bounded in observed time; pauses (nobody
    // alive to observe, a native hold) do not count; a satisfied or engaged
    // wake stops waiting.
    RecoveryWait wait;
    std::uint64_t t = 1000;
    for (; t < 1000 + RecoveryAssemblyTimeoutMs; t += 1000)             // ticks every second
        CHECK(!RecoveryWaitTimedOut(wait, true, t));
    CHECK(RecoveryWaitTimedOut(wait, true, t));
    RecoveryWait paused;
    CHECK(!RecoveryWaitTimedOut(paused, true, 1000));
    CHECK(!RecoveryWaitTimedOut(paused, true, 200000));                   // 199 s gap: paused
    for (t = 201000; t < 200000 + RecoveryAssemblyTimeoutMs; t += 1000)
        CHECK(!RecoveryWaitTimedOut(paused, true, t));
    CHECK(RecoveryWaitTimedOut(paused, true, t));
    paused.Holder = "away:11005004";
    CHECK(!RecoveryWaitTimedOut(paused, false, 1) && paused.SinceMs == 0 && paused.Holder.empty());
    // The lower-wing elevator holds members at its exit (off the platform)
    // while engaged; at the upper lip or aboard it does not pause them.
    TransportContract elevator;
    elevator.Approach.StartPoint = { -251.0f, -224.605f, 190.163f, true };
    elevator.ExitPoint = { -224.0f, -224.605f, 76.8211f, true };
    CHECK(RecoveryRideHoldsMember(true, elevator, 76.6462f, false));
    CHECK(!RecoveryRideHoldsMember(false, elevator, 76.6462f, false));  // ride not engaged
    CHECK(!RecoveryRideHoldsMember(true, elevator, 190.096f, false));   // at the upper lip
    CHECK(!RecoveryRideHoldsMember(true, elevator, 78.07f, true));      // aboard
    CHECK(RecoveryInteractionFailure("bwd.chimaeron.finkle", "native_interaction_timeout")
        == "route_recovery_requires_interaction:bwd.chimaeron.finkle:native_interaction_timeout");
    return failures ? 1 : 0;
}
'''


def test_recovery_wake_contract_and_decisions(tmp_path: Path) -> None:
    program = WAKE_REPLAY.replace("INTERACTION", f'R"J({FINKLE_INTERACTION})J"').replace(
        "COMPLETION", f'R"J({FINKLE_COMPLETION})J"')
    _compile_and_run(tmp_path, program)


def test_runtime_redoes_wakes_after_the_rides_and_fails_typed() -> None:
    recovery = _code(_source("BotWorldPopulationMgrValidationRouteNativeRecovery.cpp"))
    run = _function(recovery, "bool RunRecovery(Input const& input, Callbacks const& callbacks, NodeContract& node,")
    assert run.rstrip().endswith("return RunRecoveryWakes(input, callbacks, node, ops);\n}")
    wakes = _function(recovery, "bool RunRecoveryWakes(")
    for marker in (
        "RecoveryTrigger const trigger = ObserveRecoveryTrigger(wake.Baseline, input.Scope,\n            input.BossResetGeneration, input.CompositionRecovery, input.NowMs);",
        "bool const triggered = trigger == RecoveryTrigger::Triggered;",
        "RetireRecoveryTrigger(wake.Baseline, input.Scope, input.BossResetGeneration, trigger,\n            step, satisfied, encounterEngaged);",
        "RecoveryPartyAssembled(views)",
        "RecoveryEncounterEngaged(views)",
        "DecideRecoveryWake(triggered, engaged, encounterEngaged, satisfied, assembled);",
        '"route_recovery_interaction_engaged:" + wake.NodeId',
        '"route_recovery_interaction_complete:" + wake.NodeId',
        'RecoveryInteractionFailure(wake.NodeId,\n                "native_interaction_timeout")',
        "ops.Interact(RecoveryCallbacks(callbacks, wake.NodeId, &RecoveryInteractionFailure),",
        "Facts::EvaluateCompletion(wake.Completion,",
        "bool const waiting = !engaged && triggered && !encounterEngaged && !satisfied && !assembled;",
        "if (RecoveryWaitTimedOut(wake.Waiting, waiting, input.NowMs))",
        'std::string("party_unassembled:") + holder.Reason + ":"',
        '"route_recovery_interaction_waiting:" + wake.NodeId + ":"',
        "view.Guid = bot->GetGUID().GetRawValue();",
    ):
        assert marker in (wakes + recovery), marker
    runtime = _code(_source("BotWorldPopulationMgrValidationRouteNativeRuntime.cpp"))
    node_run = runtime[runtime.index("Result Run(Input const& input, Callbacks const& callbacks)"):]
    assert "if (!node.Recovery.empty() || !node.RecoveryInteractions.empty())" in node_run
    assert "RunInteraction(input, woken, wake, wakeRuntime, election);" in node_run
    assert "{ return ElectOwner(wake, MemberViews(input)); };" in node_run
    assert "RunInteraction(input, callbacks, node.Interaction, runtime, election);" in node_run
    assert ("void RunInteraction(Input const& input, Callbacks const& callbacks,\n"
            "    InteractionContract const& contract, NodeRuntime& runtime,\n"
            "    OwnerElection const& election)") in runtime
    manifest = _code(_source("BotWorldPopulationMgrValidationRouteManifest.cpp"))
    for marker in ('ExtractJsonArrayField(routeJson, "recovery_interaction")',
                   "NativeRoute::ParseRecoveryInteractions(wakes,",
                   '"native_recovery_interaction_unknown_field:"',
                   '"native_recovery_interaction_invalid:"',
                   'wake.NodeId + ":self_reference"',
                   "interactions.push_back(&wake.Interaction);"):
        assert marker in manifest, marker


def test_new_recovery_code_stays_lawful() -> None:
    for name in ("BotWorldPopulationMgrValidationRouteNativeRecovery.cpp",
                 "BotWorldPopulationMgrValidationRouteRecoveryReturn.cpp",
                 "BotValidationRouteRecoveryReturn.h", "BotValidationRouteNativeRecovery.h"):
        text = _code(_source(name))
        for forbidden in ("TeleportTo(", "NearTeleportTo(", "Relocate(", "UpdatePosition(",
                          "MoveFall(", "MovePoint(", "SetFall(", "HandleMovementOpcode(",
                          "ResurrectPlayer(", "SetHealth("):
            assert forbidden not in text, (name, forbidden)


def test_line_budgets() -> None:
    assert len(_source("BotValidationRouteNativeTypes.h").splitlines()) < 300
    for name in ("BotWorldPopulationMgrValidationRouteNativeRuntime.cpp",
                 "BotWorldPopulationMgrValidationRouteNativeRecovery.cpp",
                 "BotValidationRouteNativeContract.h", "BotValidationRouteNativeRecovery.h",
                 "BotWorldPopulationMgrValidationRouteRecoveryReturn.cpp",
                 "BotValidationRouteRecoveryReturn.h", "BotWorldPopulationMgrBotState.h",
                 "BotWorldPopulationMgrValidationRouteManifest.cpp",
                 "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp",
                 "BotWorldPopulationMgrRouteState.h"):
        assert len(_source(name).splitlines()) < 1000, name


# ---------------------------------------------------------------------------
# Builder: which rows redo which wake
# ---------------------------------------------------------------------------
def test_builder_derives_the_waking_interaction_for_the_rows_after_it() -> None:
    scenarios = _scenarios()
    expected = {
        "bwd.chimaeron.wake_wait": ["bwd.chimaeron.finkle"],
        "bwd.chimaeron.encounter": ["bwd.chimaeron.finkle"],
        "bwd.atramedes.intro_wait": ["bwd.atramedes.bell"],
        "bwd.atramedes.encounter": ["bwd.atramedes.bell"],
    }
    checked = 0
    for scenario_id, scenario in scenarios.items():
        parent = scenarios.get(str(scenario.get("diagnostic_parent_scenario_id") or ""), {})
        wakes = builder.recovery_wakes(scenario.get("route") or [], parent.get("route") or [])
        route = {str(step.get("node_id")): step for step in scenario.get("route") or []}
        for node_id in route:
            derived = wakes.get(node_id)
            if node_id in expected:
                assert [row["node_id"] for row in derived] == expected[node_id], (scenario_id, node_id)
                source = route.get(derived[0]["node_id"]) or next(
                    step for step in parent.get("route") or [] if step.get("node_id") == derived[0]["node_id"])
                assert derived[0]["interaction"] == source["interaction_contract"]
                assert derived[0]["completion"] == source["completion_contract"]
                checked += 1
            else:
                assert not derived, (scenario_id, node_id)
    assert checked >= 12
    source = (ROOT / "tools/bot_ml/build_validation_scenario_manifests.py").read_text(encoding="utf-8")
    assert 'route["recovery_interaction"] = wake' in source
    assert "RECOVERY_MAX_INTERACTIONS = 2  # MaxRecoveryInteractions" in source
    contract = _source("BotValidationRouteNativeRecovery.h")
    assert "constexpr std::size_t MaxRecoveryInteractions = 2;" in contract
