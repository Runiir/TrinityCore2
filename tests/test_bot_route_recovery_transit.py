"""Recovery rides: a route node across a ride between two levels.

Round 2 evidence (blackwing_descent_10n_atramedes_c0, request in
.git/round3_patches/atramedes/lower_wing_recovery_request.md): after a full
wipe the native runback left every bot at the upper lip of the lower-wing
elevator (-250.97, -217.81, 190.10) while the active node lay in the lower
wing (z 63-77). No walkable link leads down; every move was rejected as
route_destination_partial_path until the 180 s plateau watchdog.

A lower-wing row now declares the ride it lies across (recovery_transport,
the full route's unchanged bwd.transit.lower_wing_elevator contract under
"contract"). When living members are back at the ride's boarding end, the
ride runs again before the node's own contracts; a ride that cannot run
fails the attempt at once (route_recovery_requires_transport:<node>:<why>).
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
INCLUDES = ["src/server/game", "src/common"]

# The full route's lower-wing elevator row contract (composition node set
# lower_wing_transit), verbatim.
ELEVATOR = (
    '{"entry": 203716, "spawn_id": 235178, "board_transport_z": 186.551, '
    '"exit_transport_z": 73.8806, "level_tolerance_yards": 0.75, '
    '"approach": {"mode": "surface_walk", "start_point": [-251.0, -224.605, 190.163]}, '
    '"board_point": [-247.349, -224.605, 190.028], '
    '"disembark_point": [-241.349, -224.605, 77.087], '
    '"exit_point": [-224.0, -224.605, 76.8211], "arrival_tolerance_yards": 1.5, '
    '"floor_tolerance_yards": 0.5, "timeout_ms": 240000}'
)
# The Nefarian descent contract: a boarding with no exit, not a ride.
DESCENT = (
    '{"entry": 207834, "spawn_id": 235179, "board_stop_frame": 0, '
    '"board_point": [-132.2132, -224.6203, 7.1075], "arrival_tolerance_yards": 3.0, '
    '"floor_tolerance_yards": 0.5, "timeout_ms": 180000}'
)
ELEVATOR_ID = "bwd.transit.lower_wing_elevator"


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


def _cpp_string(text: str) -> str:
    return 'R"J(' + text + ')J"'


PRELUDE = r'''
#include "Bots/BotValidationRouteNativeContract.h"
#include "Bots/BotValidationRouteNativeLogic.h"
#include "Bots/BotValidationRouteNativeRecovery.h"
#include <cstdio>
#include <string>
#include <vector>

using namespace BotValidationRouteNative;

static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

[[maybe_unused]] static ParseError Recovery(std::string const& text, std::vector<RecoveryTransit>& out)
{
    Json value;
    if (ParseError error = ParseArrayText(text, value))
        return error;
    return ParseRecoveryTransports(value, out);
}

[[maybe_unused]] static std::string Row(std::string const& id, std::string const& contract,
    char const* contractKey = "contract")
{
    return "{\"node_id\": \"" + id + "\", \"" + contractKey + "\": " + contract + "}";
}
''' + "static std::string const Elevator = " + _cpp_string(ELEVATOR) + ";\n" \
    + "static std::string const Descent = " + _cpp_string(DESCENT) + ";\n" \
    + 'static std::string const ElevatorId = "' + ELEVATOR_ID + '";\n'


def test_recovery_transport_rows_parse_fail_closed(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    std::vector<RecoveryTransit> rides;
    CHECK(!Recovery("[" + Row(ElevatorId, Elevator) + "]", rides));
    CHECK(rides.size() == 1 && rides[0].NodeId == ElevatorId);
    TransportContract const& ride = rides[0].Transport;
    CHECK(ride.Declared && ride.Entry == 203716 && ride.SpawnId == 235178 && ride.HasExit());
    CHECK(ride.Approach.Mode == ApproachMode::SurfaceWalk && ride.DisembarkPoint.Valid);
    float boardZ = 0.0f, exitZ = 0.0f;
    CHECK(RecoveryLevels(ride, boardZ, exitZ));
    CHECK(std::fabs(boardZ - 190.163f) < 1e-3f && std::fabs(exitZ - 76.8211f) < 1e-3f);

    auto invalid = [&](std::string const& text, char const* detail)
    {
        ParseError const error = Recovery(text, rides);
        CHECK(error.Kind == ParseError::Code::Invalid);
        if (error.Detail != detail)
            std::fprintf(stderr, "detail %s != %s\n", error.Detail.c_str(), detail);
        CHECK(error.Detail == detail);
    };
    invalid("{}", "not_array");
    invalid("[]", "recovery_transport_count");
    std::string five = "[";
    for (int i = 0; i < 5; ++i)
        five += (i ? ", " : "") + Row("bwd.transit.ride" + std::to_string(i), Elevator);
    invalid(five + "]", "recovery_transport_count");
    invalid("[1]", "recovery_transport_not_object");
    invalid("[{\"contract\": " + Elevator + "}]", "recovery_transport_node_id");
    invalid("[" + Row("Bwd Elevator", Elevator) + "]", "recovery_transport_node_id");
    invalid("[{\"node_id\": \"bwd.transit.x\"}]", "recovery_transport_contract_missing");
    invalid("[" + Row(ElevatorId, Elevator) + ", " + Row(ElevatorId, Elevator) + "]",
        "recovery_transport_duplicate:bwd.transit.lower_wing_elevator");
    // A boarding without an exit (the Nefarian descent) is not a ride.
    invalid("[" + Row("bwd.nefarian.descent", Descent) + "]", "recovery_transport_requires_exit");
    // Its two ends must be unambiguous levels.
    std::string flat = Elevator;
    flat.replace(flat.find("76.8211"), 7, "186.500");
    invalid("[" + Row(ElevatorId, flat) + "]", "recovery_transport_levels_not_separated");
    // The ride contract's own errors keep their detail.
    std::string untimed = Elevator;
    untimed.replace(untimed.find(", \"timeout_ms\": 240000"), 22, "");
    invalid("[" + Row(ElevatorId, untimed) + "]", "recovery_transport:timeout_required");

    // Unknown keys fail closed. The contract never sits under
    // "transport_contract": the row reader finds that key by text and must
    // never mistake a recovery ride for the row's own transport.
    ParseError error = Recovery("[" + Row(ElevatorId, Elevator, "transport_contract") + "]", rides);
    CHECK(error.Kind == ParseError::Code::UnknownField
        && error.Detail == "recovery_transport.transport_contract");
    std::string extra = Elevator;
    extra.insert(1, "\"bogus\": 1, ");
    error = Recovery("[" + Row(ElevatorId, extra) + "]", rides);
    CHECK(error.Kind == ParseError::Code::UnknownField && error.Detail == "recovery_transport.bogus");
    CHECK(rides.empty() || rides.size() <= MaxRecoveryTransits);
    return failures ? 1 : 0;
}
''')


def test_elevator_levels_split_the_bwd_route_by_wing(tmp_path: Path) -> None:
    """The full route's node anchors: the upper wing is at the elevator's
    boarding end (the ride never applies there), every lower-wing node and
    the Nefarian platform at its exit end; the post-wipe runback spot is at
    the boarding end."""
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    std::vector<RecoveryTransit> rides;
    CHECK(!Recovery("[" + Row(ElevatorId, Elevator) + "]", rides));
    TransportContract const& ride = rides[0].Transport;
    float boardZ = 0.0f, exitZ = 0.0f;
    CHECK(RecoveryLevels(ride, boardZ, exitZ));
    // bwd.entry.regroup .. bwd.omnotron.encounter (steps 1-7).
    for (float z : { 193.127f, 214.154f, 212.2803f, 210.8483f, 206.88f, 214.159f, 213.825f })
        CHECK(!RecoveryApplies(ride, z));
    // bwd.maloriak.* .. bwd.nefarian.encounter (steps 9-27).
    for (float z : { 67.73f, 63.6568f, 73.53668f, 74.9906f, 75.0054f, 75.0f, 74.8731f,
             74.7668f, 74.88777f, 72.14094f, 73.94759f, 63.30268f, 7.1075f })
        CHECK(RecoveryApplies(ride, z));
    // Where the round 2 runback left every bot, and the instance entrance.
    CHECK(SideOf(190.10f, boardZ, exitZ) == RecoverySide::Board);
    CHECK(SideOf(193.127f, boardZ, exitZ) == RecoverySide::Board);
    // The car's top at the bottom rest, the pit floor and the exit point.
    for (float z : { 77.087f, 76.65f, 76.8211f })
        CHECK(SideOf(z, boardZ, exitZ) == RecoverySide::Exit);
    CHECK(RecoveryFailure(ElevatorId, "transport_missing")
        == "route_recovery_requires_transport:bwd.transit.lower_wing_elevator:transport_missing");
    CHECK(RecoveryFailure(ElevatorId, "") == "route_recovery_requires_transport:bwd.transit.lower_wing_elevator");
    return failures ? 1 : 0;
}
''')


def test_post_wipe_runback_rides_down_then_hands_back_the_node(tmp_path: Path) -> None:
    """Replay of the runtime's per-tick decision for bwd.atramedes.north_spirits
    (anchor z 74.99) after a wipe: ghosts do not engage it; the living party
    at the upper lip does; riders stay in it until they walk to the exit
    point; members already below hold; nobody needing it hands the node back."""
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    std::vector<RecoveryTransit> rides;
    CHECK(!Recovery("[" + Row(ElevatorId, Elevator) + "]", rides));
    TransportContract const& ride = rides[0].Transport;
    float boardZ = 0.0f, exitZ = 0.0f;
    CHECK(RecoveryLevels(ride, boardZ, exitZ));
    bool const applies = RecoveryApplies(ride, 74.9906f);
    CHECK(applies);

    std::vector<RecoveryMemberView> party(10);
    for (std::size_t i = 0; i < party.size(); ++i)
    {
        party[i].Guid = 11003001 + i;
        party[i].OnRouteInstance = true;
        party[i].Z = 75.0f; // corpses in the lower wing
    }
    // Wiped: ghosts do not engage a ride; the native death recovery owns them.
    CHECK(!RideNeeded(party, boardZ, exitZ));
    CHECK(DecideRecoveryRide(applies, false, false) == RecoveryStep::Idle);

    // Runback: all alive at the elevator's upper lip.
    for (RecoveryMemberView& member : party)
    {
        member.Alive = true;
        member.Z = 190.10f;
    }
    CHECK(RideNeeded(party, boardZ, exitZ));
    CHECK(DecideRecoveryRide(applies, false, true) == RecoveryStep::Engage);
    CHECK(DecideRecoveryRide(applies, true, true) == RecoveryStep::Ride);

    // Each rider runs the unchanged contract: from the runback spot it walks
    // to the approach start on the navmesh, then the ordinary surface walk.
    TransportMemberState rider;
    TransportMemberObservation o;
    o.Alive = true; o.TransportPresent = true; o.StaticFloorUnderfoot = true;
    o.DistanceToApproachStart = 6.8f; // (-250.97, -217.81) to (-251.0, -224.605)
    CHECK(DecideTransportStep(ride, o, rider).Step == TransportStep::MoveToApproachStart);

    // Four ride down, six wait at the lip: still needed.
    for (int i = 0; i < 4; ++i)
        party[i].Aboard = true;
    CHECK(RideNeeded(party, boardZ, exitZ));
    // The four left the car at the bottom; walking to the exit point.
    for (int i = 0; i < 4; ++i)
    {
        party[i].Aboard = false;
        party[i].Boarded = true;
        party[i].Z = 77.087f;
    }
    for (int i = 4; i < 10; ++i)
        party[i].Aboard = true;
    CHECK(MemberNeedsRide(party[0], boardZ, exitZ));
    // At the exit point the four no longer need it (they hold while the
    // others finish).
    for (int i = 0; i < 4; ++i)
    {
        party[i].AtExit = true;
        party[i].Z = 76.8211f;
    }
    CHECK(!MemberNeedsRide(party[0], boardZ, exitZ));
    CHECK(RideNeeded(party, boardZ, exitZ));
    // Everyone down at the exit point: the ride ends, the node resumes.
    for (int i = 4; i < 10; ++i)
        party[i] = party[0];
    CHECK(!RideNeeded(party, boardZ, exitZ));
    CHECK(DecideRecoveryRide(applies, true, false) == RecoveryStep::Complete);

    // A member that never died below, and one alive outside the instance,
    // never need the ride.
    RecoveryMemberView below;
    below.Alive = true; below.OnRouteInstance = true; below.Z = 74.99f;
    CHECK(!MemberNeedsRide(below, boardZ, exitZ));
    RecoveryMemberView outside;
    outside.Alive = true; outside.OnRouteInstance = false; outside.Z = 193.0f;
    CHECK(!MemberNeedsRide(outside, boardZ, exitZ));
    // A partial death: one member ran back while the others fight below.
    // The ride waits for the fight to end, then engages; a rider in combat at
    // the top does not hold it back, and an engaged ride continues in combat.
    std::vector<RecoveryMemberView> partial(10, below);
    for (RecoveryMemberView& member : partial)
        member.InCombat = true;
    partial[0].Z = 190.10f;
    partial[0].InCombat = false;
    CHECK(RideNeeded(partial, boardZ, exitZ) && !RecoveryMayEngage(partial, boardZ, exitZ));
    CHECK(DecideRecoveryRide(applies, false, true, false) == RecoveryStep::Idle);
    CHECK(DecideRecoveryRide(applies, true, true, false) == RecoveryStep::Ride);
    for (RecoveryMemberView& member : partial)
        member.InCombat = false;
    partial[0].InCombat = true;
    CHECK(RecoveryMayEngage(partial, boardZ, exitZ));
    CHECK(DecideRecoveryRide(applies, false, true, true) == RecoveryStep::Engage);
    // An upper-wing node never engages it, and an engaged ride whose node no
    // longer applies ends.
    CHECK(DecideRecoveryRide(RecoveryApplies(ride, 214.154f), false, true) == RecoveryStep::Idle);
    CHECK(DecideRecoveryRide(false, true, true) == RecoveryStep::Complete);
    return failures ? 1 : 0;
}
''')


def test_rider_state_from_an_earlier_ride_is_reset_and_chains_run_in_order(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    std::vector<RecoveryTransit> rides;
    CHECK(!Recovery("[" + Row(ElevatorId, Elevator) + "]", rides));
    float boardZ = 0.0f, exitZ = 0.0f;
    CHECK(RecoveryLevels(rides[0].Transport, boardZ, exitZ));
    // Rode down, died below, ran back: back at the lip with its old state.
    TransportMemberState old;
    old.Boarded = true;
    old.Left = true;
    RecoveryMemberView back;
    back.Alive = true; back.OnRouteInstance = true; back.Z = 190.10f;
    CHECK(StaleRiderState(back, old, boardZ, exitZ));
    // Not while aboard or in flight, nor below, nor without an earlier ride.
    RecoveryMemberView aboard = back;
    aboard.Aboard = true;
    CHECK(!StaleRiderState(aboard, old, boardZ, exitZ));
    RecoveryMemberView walking = back;
    walking.InFlight = true;
    CHECK(!StaleRiderState(walking, old, boardZ, exitZ));
    RecoveryMemberView down = back;
    down.Z = 76.8211f;
    CHECK(!StaleRiderState(down, old, boardZ, exitZ));
    CHECK(!StaleRiderState(back, TransportMemberState(), boardZ, exitZ));

    // Two rides in route order (the elevator, then a hypothetical lift from
    // the lower wing down to z 8): the runtime runs the first one some
    // member needs, then the next.
    std::string lift = Elevator;
    lift.replace(lift.find("-251.0, -224.605, 190.163"), 25, "-251.0, -224.605, 76.9000");
    lift.replace(lift.find("-247.349, -224.605, 190.028"), 27, "-247.349, -224.605, 76.7650");
    lift.replace(lift.find("-224.0, -224.605, 76.8211"), 25, "-224.0, -224.605, 8.51000");
    CHECK(!Recovery("[" + Row(ElevatorId, Elevator) + ", " + Row("bwd.transit.lift", lift) + "]", rides));
    float liftBoard = 0.0f, liftExit = 0.0f;
    CHECK(RecoveryLevels(rides[1].Transport, liftBoard, liftExit));
    float const anchorZ = 8.51f;
    CHECK(RecoveryApplies(rides[0].Transport, anchorZ) && RecoveryApplies(rides[1].Transport, anchorZ));
    std::vector<RecoveryMemberView> party(1, back);
    auto firstNeeded = [&]() -> int
    {
        if (RideNeeded(party, boardZ, exitZ))
            return 0;
        if (RideNeeded(party, liftBoard, liftExit))
            return 1;
        return -1;
    };
    CHECK(firstNeeded() == 0);         // at the top: the elevator first
    party[0].Z = 76.8211f;
    party[0].Boarded = false;
    CHECK(firstNeeded() == 1);         // below the elevator: the lift
    party[0].Z = 8.51f;
    CHECK(firstNeeded() == -1);        // at the node's level: none
    return failures ? 1 : 0;
}
''')


def _code(text: str) -> str:
    import re

    text = re.sub(r"//.*", "", text)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _source(name: str) -> str:
    return (BOTS / name).read_text(encoding="utf-8")


def test_runtime_runs_recovery_rides_before_the_node_and_fails_typed() -> None:
    runtime = _code(_source("BotWorldPopulationMgrValidationRouteNativeRuntime.cpp"))
    run = runtime[runtime.index("Result Run(Input const& input, Callbacks const& callbacks)"):]
    # The ride owns the node first; the node's own runtime (and timeouts)
    # starts only once no ride is needed.
    assert run.index("RunRecovery(input, callbacks, node, ops)") < run.index("runtime.Enter(input.Scope, input.NowMs);")
    assert "if (!node.Interaction.Declared && !node.Completion.Declared && !node.Transport.Declared)\n        return result;" in run
    assert "RunTransport(input, ridden, ride, rideRuntime, platform);" in run
    assert "ops.Hold = [&input](std::string const& reason) { SubmitHold(input, reason); };" in run
    # The transport step takes its contract and runtime explicitly.
    assert "TransportContract const& contract, NodeRuntime& runtime,\n    Facts::TransportTarget const& transport)" in runtime

    recovery = _code(_source("BotWorldPopulationMgrValidationRouteNativeRecovery.cpp"))
    for marker in (
        'RecoveryFailure(transit.NodeId,\n                transport.Fact.Ambiguous ? "transport_ambiguous" : "transport_missing")',
        'RecoveryFailure(transit.NodeId,\n                "native_transport_timeout")',
        "fail(RecoveryFailure(id, reason));",
        'record("route_recovery:" + id + ":" + result, target, value, entry);',
        '"route_recovery_engaged:" + transit.NodeId',
        '"route_recovery_complete:" + transit.NodeId',
        'ops.Hold("route_recovery_waiting_for_party");',
        "ops.Ride(ridden, ride, runtime, transport);",
        "ridden.Complete = nullptr;",
        "runtime.Enter(input.Scope, input.NowMs);",
        "StaleRiderState(view, state->second, boardZ, exitZ)",
        "RecoveryApplies(ride, input.AnchorZ)",
        "RecoveryMayEngage(views, boardZ, exitZ)",
        "view.InCombat = bot->IsInCombat();",
    ):
        assert marker in recovery, marker
    for forbidden in ("TeleportTo(", "NearTeleportTo(", "Relocate(", "UpdatePosition(",
                      "MoveFall(", "MovePoint(", "SetFall(", "HandleMovementOpcode("):
        assert forbidden not in recovery, forbidden

    manifest = _code(_source("BotWorldPopulationMgrValidationRouteManifest.cpp"))
    for marker in (
        'ExtractJsonArrayField(routeJson, "recovery_transport")',
        "NativeRoute::ParseRecoveryTransports(recovery, node.NativeContract.Recovery)",
        'transit.NodeId == node.NodeId ? "self_reference"',
        ": transportTemplateError(transit.Transport);",
        '"native_recovery_transport_unknown_field:"',
        '"native_recovery_transport_invalid:"',
    ):
        assert marker in manifest, marker

    contract = _code(_source("BotValidationRouteNativeContract.h"))
    assert 'KnownField(key, { "node_id", "contract" })' in contract
    types = _source("BotValidationRouteNativeTypes.h")
    assert "|| !Recovery.empty();" in types
    assert "std::vector<RecoveryTransit> Recovery;" in types
    cmake = (ROOT / "src/server/game/CMakeLists.txt").read_text(encoding="utf-8")
    assert "Bots/BotWorldPopulationMgrValidationRouteNativeRecovery.cpp" in cmake


def test_recovery_modules_stay_small_and_the_decisions_pure() -> None:
    for name in (
        "BotValidationRouteNativeRecovery.h",
        "BotWorldPopulationMgrValidationRouteNativeRecovery.h",
        "BotWorldPopulationMgrValidationRouteNativeRecovery.cpp",
        "BotWorldPopulationMgrValidationRouteNativeRuntime.cpp",
        "BotWorldPopulationMgrValidationRouteManifest.cpp",
        "BotValidationRouteNativeContract.h",
    ):
        assert len(_source(name).splitlines()) < 1000, name
    assert len(_source("BotValidationRouteNativeTypes.h").splitlines()) < 300
    pure = _source("BotValidationRouteNativeRecovery.h")
    includes = [line for line in pure.splitlines() if line.startswith("#include")]
    assert includes[0] == '#include "Bots/BotValidationRouteNativeTypes.h"'
    assert all(line.startswith("#include <") for line in includes[1:])
