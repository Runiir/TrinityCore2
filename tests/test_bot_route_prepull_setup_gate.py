"""Prepull setup gate: a raid route's staging node waits for persistent setup.

Round 2 evidence (classes handoff P3_shard_prepull_readiness): shards pulled
0.3-0.6 s after spawning (maloriak_c0 advanced from its regroup to lab_trash
270 ms after spawn); the warlock's Fel Armor and Felguard, rogue poisons, the
hunter aspect and seals then went up in combat or never. The staging node
(the first regroup or travel node before any pull) now completes only once
every living member's own TryEnsurePersistentCombatSetup has nothing left to
do, out of combat, bounded by 45 s (route_prepull_setup_timeout:<guid>:<what>).

Only composition/canonical scenarios opt in (row field prepull_setup_gate,
emitted by the scenario builder for scenarios with a composition_id): accepted
results must stay exactly reproducible, and with the gate the legacy Magmaw
roster's Affliction Felhunter would be up at the pull.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from tools.bot_ml import build_validation_scenario_manifests as builder


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"


def _compile_and_run(tmp_path: Path, program: str) -> str:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src/server/game")]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    return subprocess.run([str(binary)], check=True, cwd=ROOT, capture_output=True, text=True).stdout


def _scenarios() -> dict[str, dict]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    rows = list(config.get("scenarios") or []) + list(config.get("diagnostic_scenarios") or [])
    return {str(row["id"]): row for row in rows if isinstance(row, dict) and row.get("id")}


def _gated(kinds: list[str], tmp_path: Path, opted_in: bool = True) -> list[int]:
    """Indices the C++ gate applies to, for one route's node kinds, with every
    row's prepull_setup_gate flag as the scenario builder emits it."""
    flag = "true" if opted_in else "false"
    literal = ", ".join('Node{"' + kind + '", ' + flag + '}' for kind in kinds)
    out = _compile_and_run(tmp_path, r'''
#include "Bots/BotValidationRoutePrepull.h"
#include <cstdio>
#include <string>
#include <vector>
struct Node { std::string Kind; bool PrepullSetupGate; };
int main()
{
    std::vector<Node> const nodes = { ''' + literal + r''' };
    for (std::size_t i = 0; i <= nodes.size(); ++i)
        if (BotValidationRoutePrepull::GateApplies(nodes, i))
            std::printf("%zu\n", i);
    return 0;
}
''')
    return [int(line) for line in out.split()]


def test_only_the_staging_nodes_before_the_first_pull_are_gated(tmp_path: Path) -> None:
    # Shapes: Magmaw shard, Nefarian and Chimaeron shards, a trash-first
    # shard (its first pull is the trash node's own readiness barrier), and
    # travel legs before a regroup.
    assert _gated(["regroup", "trash", "trash", "boss"], tmp_path) == [0]
    assert _gated(["regroup", "interaction", "interaction", "transport", "boss"], tmp_path) == [0]
    assert _gated(["trash", "trash", "regroup", "interaction", "boss"], tmp_path) == []
    assert _gated(["travel", "travel", "regroup", "trash", "regroup", "boss"], tmp_path) == [0, 1, 2]
    assert _gated(["descent", "regroup", "trash"], tmp_path) == [1]
    assert _gated(["descent", "trash", "regroup"], tmp_path) == []
    assert _gated([], tmp_path) == []
    # A scenario that did not opt in is never gated.
    assert _gated(["regroup", "trash", "trash", "boss"], tmp_path, opted_in=False) == []


def test_canonical_bwd_routes_gate_their_first_regroup_only(tmp_path: Path) -> None:
    scenarios = _scenarios()
    for scenario_id in ("blackwing_descent_10n_full_c0",
                        "blackwing_descent_10n_magmaw_c0_diagnostic",
                        "blackwing_descent_10n_maloriak_c0_diagnostic",
                        "blackwing_descent_10n_nefarian_c0_diagnostic",
                        "blackwing_descent_10n_chimaeron_c0_diagnostic"):
        scenario = scenarios[scenario_id]
        kinds = [str(step.get("kind") or "") for step in scenario["route"]]
        assert kinds[0] == "regroup", scenario_id
        assert builder.prepull_setup_gate(scenario), scenario_id
        # Round 10: the full raid starts with its first spec-switch regroup at the route start, then the entrance
        # regroup at the same spot; both stand before the first pull. Later spec-switch nodes gate through their
        # contract (ObjectiveContext::HoldForPrepullSetup), not through this staging rule.
        expected = [0, 1] if scenario_id == "blackwing_descent_10n_full_c0" else [0]
        assert _gated(kinds, tmp_path, builder.prepull_setup_gate(scenario)) == expected, scenario_id


def test_accepted_magmaw_and_legacy_scenarios_are_not_gated(tmp_path: Path) -> None:
    # Accepted results stay exactly reproducible: the accepted Magmaw
    # diagnostic, the legacy shards and full route, and every dungeon keep
    # their rows without the opt-in flag, so the runtime never gates them.
    scenarios = _scenarios()
    magmaw = scenarios["blackwing_descent_10n_magmaw_diagnostic"]
    assert not builder.prepull_setup_gate(magmaw)
    kinds = [str(step.get("kind") or "") for step in magmaw["route"]]
    assert kinds[0] == "regroup"
    assert _gated(kinds, tmp_path, builder.prepull_setup_gate(magmaw)) == []
    for scenario_id, scenario in scenarios.items():
        if not scenario.get("composition_id"):
            assert not builder.prepull_setup_gate(scenario), scenario_id
    source = (ROOT / "tools/bot_ml/build_validation_scenario_manifests.py").read_text(encoding="utf-8")
    assert 'if prepull_setup_gate(scenario):\n                route["prepull_setup_gate"] = True' in source
    assert 'return bool(scenario.get("composition_id"))' in source


def test_setup_wait_replays_the_round2_warlock_and_times_out_typed(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, r'''
#include "Bots/BotValidationRoutePrepull.h"
#include <cstdio>
using namespace BotValidationRoutePrepull;
static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL %d %s\n", __LINE__, #c); ++failures; } } while (0)
int main()
{
    // Nothing to set up: the member counts as arrived at once (no delay).
    CHECK(DecideSetup(false, 0, 1000) == SetupStep::Ready);
    // Round 2 atramedes_c0 warlock, out of combat this time: Fel Armor, then
    // Summon Felguard (two unsuccessful native finishes), ready at +18.6 s.
    std::uint64_t const since = 1790356873391ull;
    CHECK(DecideSetup(true, since, since) == SetupStep::Wait);
    CHECK(DecideSetup(true, since, since + 13700) == SetupStep::Wait);
    CHECK(DecideSetup(true, since, since + 15500) == SetupStep::Wait);
    CHECK(DecideSetup(false, since, since + 18600) == SetupStep::Ready);
    // Still pending after 45 s of out-of-combat waiting: typed failure.
    CHECK(DecideSetup(true, since, since + SetupTimeoutMs - 1) == SetupStep::Wait);
    CHECK(DecideSetup(true, since, since + SetupTimeoutMs) == SetupStep::Timeout);
    // The clock only runs once waiting began (a fight resets it to 0).
    CHECK(DecideSetup(true, 0, since + 10 * SetupTimeoutMs) == SetupStep::Wait);
    CHECK(TimeoutReason(11003010, "pet:30146") == "route_prepull_setup_timeout:11003010:pet:30146");
    CHECK(TimeoutReason(11003008, "") == "route_prepull_setup_timeout:11003008:persistent_setup");
    // A member dead at the gated node is named after the grace, only while
    // someone lives, nobody fights and no native wipe recovery is pending.
    std::uint64_t const died = 1790356900000ull;
    CHECK(!DeadMemberBlocks(true, false, false, died, died + DeadMemberGraceMs - 1));
    CHECK(DeadMemberBlocks(true, false, false, died, died + DeadMemberGraceMs));
    CHECK(!DeadMemberBlocks(false, false, false, died, died + 10 * DeadMemberGraceMs));
    CHECK(!DeadMemberBlocks(true, true, false, died, died + 10 * DeadMemberGraceMs));
    CHECK(!DeadMemberBlocks(true, false, true, died, died + 10 * DeadMemberGraceMs));
    CHECK(!DeadMemberBlocks(true, false, false, 0, died));
    CHECK(DeadMemberReason(11003005) == "route_prepull_member_dead:11003005");
    return failures ? 1 : 0;
}
''')


def test_dead_clock_never_counts_a_released_ghost_runback(tmp_path: Path) -> None:
    """A patrol kills one member at a gated staging node and the others win.
    The member releases and runs back from the graveyard for 150 s: that known
    recovery episode stops the clock, so the attempt is not failed while it
    recovers. A member that stays dead without recovering is named 120 s after
    the recovery stops (or after death, when none starts)."""
    _compile_and_run(tmp_path, r'''
#include "Bots/BotValidationRoutePrepull.h"
#include <cstdio>
using namespace BotValidationRoutePrepull;
static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL %d %s\n", __LINE__, #c); ++failures; } } while (0)
int main()
{
    std::uint64_t const died = 1790357000000ull;
    std::uint64_t clock = 0;
    auto observe = [&](bool recovering, std::uint64_t now)
    {
        clock = DeadMemberClock(recovering, clock, now);
        return DeadMemberBlocks(true, false, false, clock, now);
    };
    // Dead, not yet released (the bot releases after its native death window).
    CHECK(!observe(false, died));
    CHECK(clock == died);
    // Released: a ghost with a recovery episode; the 150 s runback never counts.
    for (std::uint64_t t = died + 3000; t <= died + 153000; t += 1000)
        CHECK(!observe(true, t));
    CHECK(clock == 0);
    // Resurrected at the portal: the runtime resets the clock for the living.
    clock = 0;
    CHECK(!DeadMemberBlocks(true, false, false, clock, died + 160000));

    // A member that never releases (no recovery episode) is named after 120 s.
    clock = 0;
    CHECK(!observe(false, died));
    CHECK(!observe(false, died + DeadMemberGraceMs - 1));
    CHECK(observe(false, died + DeadMemberGraceMs));
    // A recovery that ends without resurrection (episode terminal): the clock
    // starts when the recovery stops and names it 120 s later.
    clock = 0;
    CHECK(!observe(false, died));
    CHECK(!observe(true, died + 5000));
    std::uint64_t const stopped = died + 200000;
    CHECK(!observe(false, stopped));
    CHECK(!observe(false, stopped + DeadMemberGraceMs - 1));
    CHECK(observe(false, stopped + DeadMemberGraceMs));
    return failures ? 1 : 0;
}
''')
    runtime = _code((BOTS / "BotWorldPopulationMgrValidationRouteRuntime.cpp").read_text(encoding="utf-8"))
    advance = runtime[runtime.index("bool BotWorldPopulationMgr::MaybeAdvanceValidationRouteManifest()"):]
    for marker in (
        "recovery.Ghost = loaded->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST);",
        "recovery.ReleaseRequested = member.NativeReleaseRequested;",
        "recovery.NativeCorpseAuthority = HasNativeRaidCorpseAuthority(member, loaded);",
        "member.ValidationPrepullDeadSinceMs = BotValidationRoutePrepull::DeadMemberClock(\n"
        "                    BotWorldPopulationMgrValidationRoute::IsKnownValidationRecovery(recovery),",
    ):
        assert marker in advance, marker
    assert advance.index("DeadMemberClock(") < advance.index("DeadMemberBlocks(")


def _code(text: str) -> str:
    text = re.sub(r"//.*", "", text)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_gate_runs_only_out_of_combat_at_the_anchor_and_blocks_the_advance() -> None:
    arrival = _code((BOTS / "BotWorldPopulationMgrValidationRouteTerminalArrival.cpp").read_text(encoding="utf-8"))
    hold = arrival[arrival.index("bool ObjectiveContext::HoldForPrepullSetup()"):arrival.index("bool ObjectiveContext::Run()")]
    for marker in (
        "!Manager.Cohort().Raid.RaidInstance",
        "Prepull::GateApplies(party.ValidationRouteManifest, party.ValidationRouteManifestIndex)",
        "!= Manager.Cohort().Config.ValidationRouteNodeId",
        "Manager.TryEnsurePersistentCombatSetup(State, Bot, nullptr)",
        "Prepull::TimeoutReason(Bot->GetGUID().GetRawValue(), PrepullMissingSetup())",
        '"persistent_setup_pending"',
        '"persistent_setup_ready"',
        'Action = "validation_route_prepull_setup";',
    ):
        assert marker in hold, marker
    run = arrival[arrival.index("bool ObjectiveContext::Run()"):]
    # Checked only in the arrival branch, which runs only out of combat, and
    # before the member is marked arrived.
    branch = run[run.index("if (ArrivalRoute && !arrivalCombatActive)"):]
    # Round 10: a canonical full raid's spec-switch node switches the talent group first.
    assert branch.index("if (HoldForSpecSwitch() || HoldForPrepullSetup())\n                return true;") < branch.index(
        'State.ValidationRouteTerminalReason = "arrival";')
    assert "Callbacks.EnrollEngagedPackMembers();\n        \n        State.ValidationPrepullSetupSinceMs = 0;" in run
    for forbidden in ("TeleportTo(", "NearTeleportTo(", "Relocate(", "AddAura(", "CastSpell("):
        assert forbidden not in hold, forbidden

    runtime = _code((BOTS / "BotWorldPopulationMgrValidationRouteRuntime.cpp").read_text(encoding="utf-8"))
    advance = runtime[runtime.index("bool BotWorldPopulationMgr::MaybeAdvanceValidationRouteManifest()"):]
    assert "bool const prepullGate = Cohort().Raid.RaidInstance\n            && BotValidationRoutePrepull::GateApplies(Party().ValidationRouteManifest," in advance
    for marker in (
        "bool const recoveryPending = IsNativeRaidRecoveryEvidencePending();",
        "BotValidationRoutePrepull::DeadMemberReason(loaded->GetGUID().GetRawValue()),",
        "member.ValidationPrepullDeadSinceMs = 0;",
    ):
        assert marker in advance, marker
    manifest = _code((BOTS / "BotWorldPopulationMgrValidationRouteManifest.cpp").read_text(encoding="utf-8"))
    assert 'ExtractJsonBoolField(routeJson, "prepull_setup_gate", node.PrepullSetupGate);' in manifest
    route_state = (BOTS / "BotWorldPopulationMgrRouteState.h").read_text(encoding="utf-8")
    assert "bool PrepullSetupGate = false;" in route_state
    assert 'if (prepullGate && !(state.ValidationRouteTerminalState\n                    && state.ValidationRouteTerminalGeneration == Party().ValidationRouteGeneration\n                    && state.ValidationRouteTerminalReason == "arrival"))' in advance

    state = (BOTS / "BotWorldPopulationMgrBotState.h").read_text(encoding="utf-8")
    assert "uint64 ValidationPrepullSetupSinceMs = 0;" in state
    assert "uint64 ValidationPrepullSetupGeneration = 0;" in state
    assert "uint64 ValidationPrepullDeadSinceMs = 0;" in state
    for name in ("BotWorldPopulationMgrValidationRouteTerminalArrival.cpp",
                 "BotWorldPopulationMgrValidationRouteRuntime.cpp",
                 "BotWorldPopulationMgrBotState.h", "BotValidationRoutePrepull.h"):
        assert len((BOTS / name).read_text(encoding="utf-8").splitlines()) < 1000, name
