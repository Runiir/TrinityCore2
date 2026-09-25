"""Header-only tests for the lawful final approach onto a transport surface.

Covers the approach contract parser, the native fall physics mirrors, the
straight-walk and ledge-drop admission predicates, and multi-tick replays of
the member phases for the BWD lower-wing elevator (surface walk inside a
~1.8 s rest window) and the Nefarian platform (ledge drop onto the raised
stop frame). Compiled with g++ exactly like the other header-only bot tests.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = ["src/server/game", "src/common"]


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


PRELUDE = r'''
#include "Bots/BotValidationRouteNativeContract.h"
#include "Bots/BotValidationRouteNativeLogic.h"
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

using namespace BotValidationRouteNative;

static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

[[maybe_unused]] static ParseError Transport(char const* text, TransportContract& out)
{
    Json value;
    if (ParseError error = ParseObjectText(text, value))
    {
        std::fprintf(stderr, "json error %s\n", error.Detail.c_str());
        ++failures;
        return error;
    }
    return ParseTransport(value, out);
}

// The proposed route rows (patch requests to the scenario config).
[[maybe_unused]] static char const* const Elevator = R"({"entry": 203716, "spawn_id": 235178, "board_transport_z": 186.551, "exit_transport_z": 73.8806, "level_tolerance_yards": 0.75, "approach": {"mode": "surface_walk", "start_point": [-251.0, -224.605, 190.163]}, "board_point": [-247.349, -224.605, 190.028], "disembark_point": [-241.349, -224.605, 77.087], "exit_point": [-224.0, -224.605, 76.8211], "arrival_tolerance_yards": 1.5, "floor_tolerance_yards": 0.5, "timeout_ms": 240000})";
[[maybe_unused]] static char const* const Nefarian = R"({"entry": 207834, "spawn_id": 235179, "board_stop_frame": 0, "approach": {"mode": "ledge_drop", "start_point": [-158.8, -224.62, 41.3544], "step_off_point": [-156.4, -224.62, 41.3544], "landing_z": 8.51, "landing_tolerance_yards": 1.0, "landing_surface": "transport", "min_health_after_fall_pct": 0.2}, "board_point": [-132.2132, -224.6203, 6.5714], "arrival_tolerance_yards": 3.0, "floor_tolerance_yards": 0.5, "timeout_ms": 180000})";

[[maybe_unused]] static std::vector<SurfaceSample> Samples(std::vector<char> const& floors)
{
    // 's' static, 't' transport, 'b' both, '-' none; 0.25 yd apart.
    std::vector<SurfaceSample> out;
    for (std::size_t i = 0; i < floors.size(); ++i)
    {
        SurfaceSample sample;
        sample.Along = 0.25f * float(i);
        sample.StaticFloor = floors[i] == 's' || floors[i] == 'b';
        sample.TransportFloor = floors[i] == 't' || floors[i] == 'b';
        out.push_back(sample);
    }
    return out;
}
'''


def test_approach_contract_parses_both_modes_fail_closed(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    TransportContract elevator;
    CHECK(!Transport(Elevator, elevator));
    CHECK(elevator.Approach.Mode == ApproachMode::SurfaceWalk);
    CHECK(elevator.Approach.StartPoint.Valid && !elevator.WaitPoint.Valid);
    CHECK(std::fabs(elevator.Approach.StartPoint.X + 251.0f) < 1e-3f);

    TransportContract nefarian;
    CHECK(!Transport(Nefarian, nefarian));
    CHECK(nefarian.Approach.Mode == ApproachMode::LedgeDrop);
    CHECK(nefarian.Approach.LandOnTransport && nefarian.Approach.StepOffPoint.Valid);
    CHECK(std::fabs(nefarian.Approach.LandingZ - 8.51f) < 1e-3f);
    CHECK(std::fabs(nefarian.Approach.MinHealthAfterFallPct - 0.2f) < 1e-6f);

    // Without an approach nothing changes (round-1 rows).
    TransportContract legacy;
    CHECK(!Transport(R"({"entry": 207834, "board_stop_frame": 0, "wait_point": [-158.4, -223.467, 41.3544], "board_point": [-132.2132, -224.6203, 6.5714], "arrival_tolerance_yards": 3.0, "timeout_ms": 180000})", legacy));
    CHECK(legacy.Approach.Mode == ApproachMode::None);

    auto reject = [](char const* approach) -> std::string
    {
        std::string text = std::string(R"({"entry": 207834, "board_stop_frame": 0, "board_point": [-132.2132, -224.6203, 6.5714], "timeout_ms": 180000, "approach": )") + approach + "}";
        TransportContract out;
        Json value;
        ParseObjectText(text, value);
        ParseError error = ParseTransport(value, out);
        return error ? error.Detail : std::string("accepted");
    };
    CHECK(reject(R"({"start_point": [-158.8, -224.62, 41.3544]})") == "approach_mode_unknown");
    CHECK(reject(R"({"mode": "jump", "start_point": [-158.8, -224.62, 41.3544]})") == "approach_mode_unknown");
    CHECK(reject(R"({"mode": "ledge_drop"})") == "approach_start_point_missing");
    CHECK(reject(R"({"mode": "ledge_drop", "start_point": [1, 2, 3], "teleport": true})") == "approach.teleport");
    CHECK(reject(R"({"mode": "ledge_drop", "start_point": [-158.8, -224.62, 41.3544], "landing_z": 8.47})") == "approach_ledge_drop_shape");
    CHECK(reject(R"({"mode": "ledge_drop", "start_point": [-158.8, -224.62, 41.3544], "step_off_point": [-150.0, -224.62, 41.3544], "landing_z": 8.47})") == "approach_step_off_distance_invalid");
    CHECK(reject(R"({"mode": "ledge_drop", "start_point": [-158.8, -224.62, 41.3544], "step_off_point": [-156.4, -224.62, 40.0], "landing_z": 8.47})") == "approach_step_off_not_level");
    CHECK(reject(R"({"mode": "ledge_drop", "start_point": [-158.8, -224.62, 41.3544], "step_off_point": [-156.4, -224.62, 41.3544], "landing_z": 39.0})") == "approach_ledge_drop_too_shallow");
    // 70 yd: native fall damage 1.0 of max health: lethal for anyone.
    CHECK(reject(R"({"mode": "ledge_drop", "start_point": [-158.8, -224.62, 41.3544], "step_off_point": [-156.4, -224.62, 41.3544], "landing_z": -30.0})") == "approach_ledge_drop_lethal");
    CHECK(reject(R"({"mode": "ledge_drop", "start_point": [-158.8, -224.62, 41.3544], "step_off_point": [-156.4, -224.62, 41.3544], "landing_z": 8.47, "landing_surface": "lava"})") == "approach_landing_surface_unknown");
    CHECK(reject(R"({"mode": "ledge_drop", "start_point": [-158.8, -224.62, 41.3544], "step_off_point": [-156.4, -224.62, 41.3544], "landing_z": 8.47, "min_health_after_fall_pct": 1.5})") == "approach_min_health_invalid");
    CHECK(reject(R"({"mode": "ledge_drop", "start_point": [-158.8, -224.62, 41.3544], "step_off_point": [-156.4, -224.62, 41.3544], "landing_z": 8.47, "landing_tolerance_yards": 0})") == "approach_landing_tolerance_invalid");
    CHECK(reject(R"({"mode": "ledge_drop", "start_point": [-158.8, -224.62, 41.3544], "step_off_point": [-156.4, -224.62, 41.3544], "landing_z": 8.47, "landing_surface": "static"})") == "accepted");
    // Surface walks: flush floors, a bounded straight walk, no drop fields.
    CHECK(reject(R"({"mode": "surface_walk", "start_point": [-133.0, -224.62, 6.5714], "landing_z": 1})") == "approach_field_unexpected:landing_z");
    CHECK(reject(R"({"mode": "surface_walk", "start_point": [-150.0, -224.62, 6.5714]})") == "approach_surface_walk_length_invalid");
    CHECK(reject(R"({"mode": "surface_walk", "start_point": [-135.0, -224.62, 8.5]})") == "approach_surface_walk_not_level");
    CHECK(reject(R"({"mode": "surface_walk", "start_point": [-135.0, -224.62, 6.7]})") == "accepted");
    // One unambiguous waiting spot.
    TransportContract both;
    CHECK(Transport(R"({"entry": 207834, "board_stop_frame": 0, "wait_point": [-158.4, -223.467, 41.3544], "board_point": [-132.2132, -224.6203, 6.5714], "timeout_ms": 180000, "approach": {"mode": "ledge_drop", "start_point": [-158.8, -224.62, 41.3544], "step_off_point": [-156.4, -224.62, 41.3544], "landing_z": 8.47}})", both).Detail == "approach_with_wait_point");
    return failures ? 1 : 0;
}
''')


def test_native_fall_physics_mirrors_the_core(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    // Movement::computeFallTime: sqrt(2h/g) below the terminal length.
    CHECK(NativeFallTimeMs(0.0f) == 0);
    std::uint64_t const drop = NativeFallTimeMs(41.3544f - 8.51f);
    CHECK(drop >= 1840 && drop <= 1850);
    // Past the terminal length (~93.8 yd) the fall continues at 60.148 yd/s.
    std::uint64_t const deep = NativeFallTimeMs(193.8f);
    CHECK(deep > 4750 && deep < 4800);

    // Player::HandleFall: 0.018 * (dz - safe fall) - 0.2426 of max health.
    CHECK(NativeFallDamageFraction(14.56f, 0.0f, 1.0f, false) == 0.0f);
    float const nefarian = NativeFallDamageFraction(41.3544f - 8.51f, 0.0f, 1.0f, false);
    CHECK(std::fabs(nefarian - (0.018f * 32.8444f - 0.2426f)) < 1e-4f);
    CHECK(nefarian > 0.34f && nefarian < 0.36f);
    // Safe fall shortens the counted height; feather fall negates it.
    CHECK(NativeFallDamageFraction(32.88f, 10.0f, 1.0f, false) < nefarian);
    CHECK(NativeFallDamageFraction(32.88f, 0.0f, 1.0f, true) == 0.0f);
    // Rate.Damage.Fall scales it; the core caps the damage at max health.
    CHECK(std::fabs(NativeFallDamageFraction(41.3544f - 8.51f, 0.0f, 2.0f, false) - 2.0f * nefarian) < 1e-4f);
    CHECK(NativeFallDamageFraction(200.0f, 0.0f, 1.0f, false) == 1.0f);
    CHECK(WalkTimeMs(3.653f, 7.0f) == 521);
    return failures ? 1 : 0;
}
''')


def test_surface_walk_admission_needs_floor_everywhere_and_a_clear_way(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    // Elevator top: corridor floor, the platform tucked under the lip, then
    // the platform's own surface alone.
    std::vector<SurfaceSample> const elevator = Samples({ 'b', 'b', 'b', 's', 't', 't', 't', 't', 't', 't', 't', 't', 't', 't', 't' });
    CHECK(ValidateSurfaceWalk(elevator, 3.5f, true, true).Ok);
    // A seam no wider than the player's collision radius is walkable...
    CHECK(ValidateSurfaceWalk(Samples({ 's', 's', '-', 't', 't' }), 1.0f, true, true).Ok);
    // ...a wider gap is not.
    CHECK(ValidateSurfaceWalk(Samples({ 's', 's', '-', '-', 't', 't' }), 1.25f, true, true).Reason
        == "surface_walk_unsupported_span");
    CHECK(ValidateSurfaceWalk(Samples({ '-', 's', 't' }), 0.5f, true, true).Reason == "surface_walk_start_unsupported");
    CHECK(ValidateSurfaceWalk(Samples({ 's', 't', '-' }), 0.5f, true, true).Reason == "surface_walk_end_unsupported");
    // Boarding walks end on the platform's own surface, not over a closer
    // static floor inside its bounding box.
    CHECK(ValidateSurfaceWalk(Samples({ 's', 'b', 'b' }), 0.5f, true, true).Reason == "surface_walk_end_not_on_transport");
    CHECK(ValidateSurfaceWalk(Samples({ 't', 'b', 's' }), 0.5f, true, false).Ok);
    // The seam never makes a static-to-static walk off the navmesh: a walk
    // that does not end on the transport starts on it (or is a passenger's).
    CHECK(ValidateSurfaceWalk(Samples({ 's', 's', 's' }), 0.5f, true, false).Reason == "surface_walk_not_on_transport");
    CHECK(ValidateSurfaceWalk(Samples({ 's', 's', 's' }), 0.5f, true, false, true).Ok);
    CHECK(ValidateSurfaceWalk(elevator, 3.5f, false, true).Reason == "surface_walk_blocked");
    CHECK(ValidateSurfaceWalk(elevator, 12.5f, true, true).Reason == "surface_walk_length_invalid");
    CHECK(ValidateSurfaceWalk(Samples({ 't' }), 0.1f, true, true).Reason == "surface_walk_unsampled");
    return failures ? 1 : 0;
}
''')


def test_ledge_drop_admission_proves_the_lip_the_landing_and_the_health(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
static LedgeDropProbe NefarianProbe()
{
    LedgeDropProbe probe;
    probe.Step = Samples({ 's', 's', 's', 's', 's', '-', '-', '-', '-', '-' });
    probe.StepLengthYards = 2.4f;
    probe.StepZ = 41.3544f;
    probe.StepCollisionFree = true;
    probe.FootprintSupported = 0;
    probe.LandingFound = true;
    probe.LandingZ = 8.47f;
    probe.LandingOnTransport = true;
    probe.HealthPct = 1.0f;
    probe.PredictedDamagePct = 0.349f;
    return probe;
}

int main()
{
    TransportContract nefarian;
    CHECK(!Transport(Nefarian, nefarian));
    ApproachContract const& drop = nefarian.Approach;
    CHECK(ValidateLedgeDrop(drop, NefarianProbe()).Ok);

    auto reason = [&drop](auto mutate)
    {
        LedgeDropProbe probe = NefarianProbe();
        mutate(probe);
        return ValidateLedgeDrop(drop, probe).Reason;
    };
    // The body must clear the lip before gravity takes over; a short
    // declared point advances along its heading instead of failing.
    std::string const footprint = reason([](LedgeDropProbe& p) { p.FootprintSupported = 3; });
    CHECK(footprint == "ledge_drop_step_off_footprint_supported" && StepOffCandidateAdvances(footprint));
    std::string const overFloor = reason([](LedgeDropProbe& p) { p.Step = Samples({ 's', 's', 's', 's' }); });
    CHECK(overFloor == "ledge_drop_step_off_over_floor" && StepOffCandidateAdvances(overFloor));
    // Everything else is final.
    CHECK(reason([](LedgeDropProbe& p) { p.Step = Samples({ 's', '-', 's', '-' }); }) == "ledge_drop_step_profile_not_a_ledge");
    CHECK(reason([](LedgeDropProbe& p) { p.Step = Samples({ '-', '-', '-' }); }) == "ledge_drop_edge_unsupported");
    CHECK(reason([](LedgeDropProbe& p) { p.StepCollisionFree = false; }) == "ledge_drop_step_blocked");
    CHECK(reason([](LedgeDropProbe& p) { p.StepLengthYards = 4.5f; }) == "ledge_drop_step_length_invalid");
    CHECK(reason([](LedgeDropProbe& p) { p.LandingFound = false; }) == "ledge_drop_landing_missing");
    // Lowered platform: the fall would miss the declared floor (and land in the lava).
    CHECK(reason([](LedgeDropProbe& p) { p.LandingZ = -5.4f; }) == "ledge_drop_landing_height_mismatch");
    CHECK(reason([](LedgeDropProbe& p) { p.LandingInLiquid = true; }) == "ledge_drop_lands_in_liquid");
    CHECK(reason([](LedgeDropProbe& p) { p.LandingOnTransport = false; }) == "ledge_drop_landing_surface_mismatch");
    // A sloped or stepped lip is native pathing's, never a level walk in the
    // air above it (final, not a reason to walk further out).
    std::string const slope = reason([](LedgeDropProbe& p) { p.Step[6].ShallowFloorBelow = true; });
    CHECK(slope == "ledge_drop_lip_not_a_clean_drop" && !StepOffCandidateAdvances(slope));
    // A static landing is static ground within the landing tolerance, never
    // another gameobject's floor.
    ApproachContract onGround = drop;
    onGround.LandOnTransport = false;
    LedgeDropProbe ground = NefarianProbe();
    ground.LandingOnTransport = false;
    CHECK(ValidateLedgeDrop(onGround, ground).Reason == "ledge_drop_landing_surface_mismatch");
    ground.LandingOnStatic = true;
    CHECK(ValidateLedgeDrop(onGround, ground).Ok);
    CHECK(reason([](LedgeDropProbe& p) { p.LandingZ = 39.0f; }) == "ledge_drop_too_shallow");
    // Health after the native fall damage must keep the declared margin.
    CHECK(reason([](LedgeDropProbe& p) { p.HealthPct = 0.54f; }) == "ledge_drop_health_margin_low");
    CHECK(reason([](LedgeDropProbe& p) { p.HealthPct = 0.56f; }) == "ledge_drop_verified");
    CHECK(!StepOffCandidateAdvances("ledge_drop_landing_height_mismatch"));
    return failures ? 1 : 0;
}
''')


def test_elevator_surface_walk_replay_waits_for_the_rest_window(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    TransportContract ride;
    CHECK(!Transport(Elevator, ride));
    TransportMemberState state;
    TransportMemberObservation o;
    o.Alive = true; o.TransportPresent = true; o.StaticFloorUnderfoot = true;

    // Far from the approach start: walk there on the static navmesh.
    o.DistanceToApproachStart = 20.0f; o.DistanceToBoard = 24.0f;
    TransportDecision d = DecideTransportStep(ride, o, state);
    CHECK(d.Step == TransportStep::MoveToApproachStart && d.Reason == "transport_approach_start_path");
    CHECK(!ApproachWantsFollowUp(ride, d, state));
    // Within the start tolerance but still running: settle there.
    o.DistanceToApproachStart = 0.8f; o.Moving = true;
    CHECK(DecideTransportStep(ride, o, state).Reason == "transport_approach_start_settle");
    // 1.2 yd is inside the contract's 1.5 yd arrival tolerance but outside
    // the approach start tolerance.
    o.Moving = false; o.DistanceToApproachStart = 1.2f;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::MoveToApproachStart);
    o.DistanceToApproachStart = 0.3f; o.DistanceToBoard = 3.653f;
    // Platform away (cycling): wait at the lip and watch it closely.
    d = DecideTransportStep(ride, o, state);
    CHECK(d.Step == TransportStep::Hold && d.Reason == "transport_waiting");
    CHECK(ApproachWantsFollowUp(ride, d, state));
    // Arrived with 900 ms of rest left: 521 ms walk + 250 + 300 do not fit.
    o.ReadyToBoard = true; o.RestRemainingMs = 900; o.ApproachTravelMs = 521;
    d = DecideTransportStep(ride, o, state);
    CHECK(d.Reason == "transport_rest_window_too_short" && ApproachWantsFollowUp(ride, d, state));
    CHECK(!RestWindowCovers(1070, 521) && RestWindowCovers(1071, 521) && RestWindowCovers(UnboundedRestMs, 99999));
    // Fresh rest (~1.97 s): walk across the platform's surface.
    o.RestRemainingMs = 1970;
    d = DecideTransportStep(ride, o, state);
    CHECK(d.Step == TransportStep::SurfaceWalk && d.Reason == "transport_approach_surface_walk");
    state.Approach = ApproachPhaseAfter(d.Step, false);
    CHECK(state.Approach == ApproachPhase::Walking);
    // Mid-walk over the corridor lip while the rest still covers the rest of
    // the walk and the boarding report: keep walking.
    o.Moving = true; o.RestRemainingMs = 1600; o.ApproachTravelMs = 400; o.DistanceToBoard = 2.9f;
    d = DecideTransportStep(ride, o, state);
    CHECK(d.Step == TransportStep::Hold && d.Reason == "transport_approach_walking" && ApproachWantsFollowUp(ride, d, state));
    // Across the seam for one sample: still walking, never a stranding.
    o.StaticFloorUnderfoot = false;
    CHECK(DecideTransportStep(ride, o, state).Reason == "transport_approach_walking");
    // First contact with the platform's own surface: stop there and board at
    // once (D's proof), so the member is unboarded on it as briefly as possible.
    o.TransportFloorUnderfoot = true;
    CHECK(DecideTransportStep(ride, o, state).Reason == "transport_board_stop_on_platform");
    CHECK(state.PlatformFloorSeen);
    o.Moving = false;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::Board);
    // Aboard: the approach is over; ride to the exit level, watching for it.
    o.OnThisTransport = true;
    d = DecideTransportStep(ride, o, state);
    CHECK(d.Step == TransportStep::HoldAboard && ApproachWantsFollowUp(ride, d, state));
    CHECK(state.Approach == ApproachPhase::Idle && state.Boarded);

    // Bottom rest: the car's surface sits 0.67 yd above the pit floor at the
    // board spot, so the passenger crosses the car to the disembark point in
    // one proven straight walk (no navmesh path across the car) and leaves
    // over static ground there.
    o.AtExit = true; o.ReadyToBoard = false; o.DistanceToDisembark = 6.0f;
    o.StaticFloorUnderfoot = false;
    d = DecideTransportStep(ride, o, state);
    CHECK(d.Step == TransportStep::DisembarkWalk && d.Reason == "transport_disembark_surface_walk");
    CHECK(ApproachWantsFollowUp(ride, d, state));
    o.Moving = true;
    CHECK(DecideTransportStep(ride, o, state).Reason == "transport_exit_settling");
    o.Moving = false; o.DistanceToDisembark = 0.2f; o.StaticFloorUnderfoot = true;
    d = DecideTransportStep(ride, o, state);
    CHECK(d.Step == TransportStep::Leave && ApproachWantsFollowUp(ride, d, state));
    o.OnThisTransport = false; o.TransportFloorUnderfoot = false; o.DistanceToExit = 17.0f;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::MoveToExit);
    o.DistanceToExit = 1.0f;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::Done);

    // Without an approach the round-1 disembark path stays unchanged.
    TransportContract legacy;
    CHECK(!Transport(R"({"entry": 203716, "board_transport_z": 186.551, "exit_transport_z": 73.8806, "wait_point": [-256.35, -224.605, 190.163], "board_point": [-247.349, -224.605, 190.028], "disembark_point": [-241.349, -224.605, 77.358], "exit_point": [-224.0, -224.605, 76.8211], "timeout_ms": 240000})", legacy));
    TransportMemberState legacyState;
    TransportMemberObservation r;
    r.Alive = true; r.TransportPresent = true; r.OnThisTransport = true; r.AtExit = true;
    r.TransportFloorUnderfoot = true; r.DistanceToDisembark = 6.0f;
    CHECK(DecideTransportStep(legacy, r, legacyState).Step == TransportStep::MoveToDisembark);

    // A walk that ended short, back on the corridor floor, launches again
    // (a new counted submission) when the window still covers it.
    TransportMemberState shortWalk;
    shortWalk.Approach = ApproachPhase::Walking;
    TransportMemberObservation s;
    s.Alive = true; s.TransportPresent = true; s.StaticFloorUnderfoot = true;
    s.ReadyToBoard = true; s.RestRemainingMs = 1970; s.ApproachTravelMs = 400;
    s.DistanceToApproachStart = 0.6f;
    CHECK(DecideTransportStep(ride, s, shortWalk).Step == TransportStep::SurfaceWalk);
    CHECK(shortWalk.Approach == ApproachPhase::Idle);
    // Stranded if the platform left under a member that stood on it.
    TransportMemberState left;
    left.Approach = ApproachPhase::Walking;
    left.PlatformFloorSeen = true;
    TransportMemberObservation l;
    l.Alive = true; l.TransportPresent = true;
    for (std::uint64_t now : { 1000u, 1200u, 1450u })
    {
        l.NowMs = now;
        DecideTransportStep(ride, l, left);
    }
    CHECK(DecideTransportStep(ride, l, left).Reason == "transport_member_stranded_without_floor");
    return failures ? 1 : 0;
}
''')


def test_nefarian_ledge_drop_replay_hands_the_member_to_gravity_then_boarding(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    TransportContract platform;
    CHECK(!Transport(Nefarian, platform));
    TransportMemberState state;
    TransportMemberObservation o;
    o.Alive = true; o.TransportPresent = true; o.StaticFloorUnderfoot = true;
    o.DistanceToApproachStart = 40.0f;
    CHECK(DecideTransportStep(platform, o, state).Step == TransportStep::MoveToApproachStart);
    // At the ledge while the intro still raises the platform: wait at the
    // ordinary cadence (a script-held stop frame rests unbounded).
    o.DistanceToApproachStart = 0.4f;
    TransportDecision d = DecideTransportStep(platform, o, state);
    CHECK(d.Reason == "transport_waiting" && !ApproachWantsFollowUp(platform, d, state));
    o.ReadyToBoard = true; o.RestRemainingMs = UnboundedRestMs; o.ApproachTravelMs = 2190;
    // Not healthy enough for ~35% native fall damage with a 20% margin.
    o.HealthPct = 0.5f; o.PredictedFallDamagePct = 0.349f;
    CHECK(DecideTransportStep(platform, o, state).Reason == "transport_drop_health_low");
    o.HealthPct = 1.0f;
    // The cohort drops together: wait (watching closely) until every living
    // member is at the lip, dropping, landed or aboard.
    d = DecideTransportStep(platform, o, state);
    CHECK(d.Step == TransportStep::Hold && d.Reason == "transport_drop_waiting_for_cohort");
    CHECK(ApproachWantsFollowUp(platform, d, state));
    o.CohortAtApproachStart = true;
    d = DecideTransportStep(platform, o, state);
    CHECK(d.Step == TransportStep::DropStepOff && ApproachWantsFollowUp(platform, d, state));
    state.Approach = ApproachPhaseAfter(d.Step, false);
    CHECK(state.Approach == ApproachPhase::SteppingOff);

    // Walking off the lip.
    o.Moving = true;
    CHECK(DecideTransportStep(platform, o, state).Reason == "transport_drop_stepping_off");
    // Stationary over the void after the step: fall now. Never a re-snap,
    // an airborne failure or a stranding.
    o.Moving = false; o.StaticFloorUnderfoot = false; o.FloorNear = false;
    for (std::uint64_t now : { 100u, 200u, 300u, 700u })
    {
        o.NowMs = now;
        d = DecideTransportStep(platform, o, state);
        CHECK(d.Step == TransportStep::DropFall && d.Reason == "transport_drop_fall");
    }
    state.Approach = ApproachPhaseAfter(d.Step, false);
    CHECK(state.Approach == ApproachPhase::Falling);
    // Native gravity owns the member while the fall spline runs.
    o.Falling = true; o.Moving = true; o.FallSplineActive = true;
    CHECK(DecideTransportStep(platform, o, state).Reason == "transport_drop_falling");
    // Finalized on the platform with the falling flag still set: the client's
    // landing report (fall damage) comes next.
    o.FallSplineActive = false; o.LandingPending = true; o.TransportFloorUnderfoot = true;
    d = DecideTransportStep(platform, o, state);
    CHECK(d.Step == TransportStep::DropLand && ApproachWantsFollowUp(platform, d, state));
    state.Approach = ApproachPhaseAfter(d.Step, false);
    CHECK(state.Approach == ApproachPhase::Landed);
    // Landed and reported: board from the platform's own surface.
    o.Falling = false; o.Moving = false; o.LandingPending = false;
    CHECK(DecideTransportStep(platform, o, state).Step == TransportStep::Board);
    o.OnThisTransport = true;
    CHECK(DecideTransportStep(platform, o, state).Step == TransportStep::Done);
    CHECK(MemberTransportDone(platform, true, true, 0.0f));

    // An interrupted step that never left the ledge simply launches again.
    TransportMemberState interrupted;
    interrupted.Approach = ApproachPhase::SteppingOff;
    TransportMemberObservation i;
    i.Alive = true; i.TransportPresent = true; i.StaticFloorUnderfoot = true;
    i.DistanceToApproachStart = 0.5f; i.ReadyToBoard = true; i.RestRemainingMs = UnboundedRestMs;
    i.CohortAtApproachStart = true;
    CHECK(DecideTransportStep(platform, i, interrupted).Step == TransportStep::DropStepOff);
    CHECK(interrupted.Approach == ApproachPhase::Idle);
    // A fall MoveFall found already grounded (Completed) counts as landed.
    CHECK(ApproachPhaseAfter(TransportStep::DropFall, true) == ApproachPhase::Landed);
    // Landed anywhere but this platform's surface is a typed failure.
    TransportMemberState stray;
    stray.Approach = ApproachPhase::Landed;
    TransportMemberObservation s;
    s.Alive = true; s.TransportPresent = true; s.StaticFloorUnderfoot = true; s.ReadyToBoard = true;
    CHECK(DecideTransportStep(platform, s, stray).Reason == "transport_drop_landed_off_platform");
    // Rejected submissions stay bounded.
    stray.FailedSubmissions = platform.MaxSubmissions;
    CHECK(DecideTransportStep(platform, s, stray).Reason == "transport_submissions_exhausted");
    return failures ? 1 : 0;
}
''')


def test_floor_unverified_resnaps_toward_the_approach_start(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    TransportContract platform;
    CHECK(!Transport(Nefarian, platform));
    TransportMemberState state;
    TransportMemberObservation o;
    o.Alive = true; o.TransportPresent = true; o.FloorNear = true;
    for (std::uint32_t move = 0; move < MaxResnapMoves; ++move)
    {
        TransportDecision d = DecideTransportStep(platform, o, state);
        CHECK(d.Step == TransportStep::MoveToApproachStart && d.Reason == "transport_member_floor_unverified_resnap");
    }
    CHECK(DecideTransportStep(platform, o, state).Reason == "transport_member_floor_unverified");
    // Contracts without an approach or wait point re-snap toward the board point.
    TransportContract bare;
    CHECK(!Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2, 3], "timeout_ms": 1})", bare));
    TransportMemberState bareState;
    CHECK(DecideTransportStep(bare, o, bareState).Step == TransportStep::MoveToBoard);
    // Walking members are never re-snapped.
    TransportMemberState walking;
    o.Moving = true;
    CHECK(DecideTransportStep(platform, o, walking).Step != TransportStep::Fail);
    CHECK(walking.ResnapMoves == 0);
    return failures ? 1 : 0;
}
''')


def test_step_names_and_follow_up_are_approach_only(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    CHECK(std::string(TransportStepName(TransportStep::MoveToApproachStart)) == "move_to_approach_start");
    CHECK(std::string(TransportStepName(TransportStep::SurfaceWalk)) == "surface_walk");
    CHECK(std::string(TransportStepName(TransportStep::DropStepOff)) == "drop_step_off");
    CHECK(std::string(TransportStepName(TransportStep::DropFall)) == "drop_fall");
    CHECK(std::string(TransportStepName(TransportStep::DropLand)) == "drop_land");
    CHECK(std::string(TransportStepName(TransportStep::DisembarkWalk)) == "disembark_walk");
    // Contracts without an approach never shorten the decision cadence.
    TransportContract legacy;
    CHECK(!Transport(R"({"entry": 203716, "board_transport_z": 186.551, "wait_point": [-256.35, -224.605, 190.163], "board_point": [-247.349, -224.605, 190.028], "timeout_ms": 240000})", legacy));
    TransportMemberState state;
    for (TransportStep step : { TransportStep::Hold, TransportStep::Stop, TransportStep::Board, TransportStep::MoveToBoard })
        CHECK(!ApproachWantsFollowUp(legacy, { step, "transport_waiting" }, state));
    state.Approach = ApproachPhase::Walking;
    CHECK(!ApproachWantsFollowUp(legacy, { TransportStep::Hold, "x" }, state));
    CHECK(ApproachPhaseAfter(TransportStep::Board, false) == ApproachPhase::Idle);
    return failures ? 1 : 0;
}
''')



def test_interrupted_or_displaced_walk_is_stopped_and_replanned(tmp_path: Path) -> None:
    """Review blocker: a stun, root or knockback must never let a generator
    resume an unchecked straight line (the cyclic elevator leaves meanwhile)."""
    _compile_and_run(tmp_path, PRELUDE + r"""
static TransportMemberObservation Walking()
{
    TransportMemberObservation o;
    o.Alive = true; o.TransportPresent = true; o.StaticFloorUnderfoot = true;
    o.ReadyToBoard = true; o.RestRemainingMs = 1100; o.ApproachTravelMs = 300;
    o.DistanceToApproachStart = 1.5f; o.DistanceToBoard = 2.1f; o.Moving = true;
    return o;
}

int main()
{
    TransportContract ride;
    CHECK(!Transport(Elevator, ride));

    // Launched with ~1.1 s of rest left, then stunned: a generator that kept
    // UNIT_STATE_ROAMING_MOVE with no spline (Moving stays true) would resume
    // the line into the empty shaft. Stop it (clearing the active slot) and
    // re-plan from scratch.
    TransportMemberState stunned;
    stunned.Approach = ApproachPhase::Walking;
    TransportMemberObservation o = Walking();
    o.MotionSuspended = true;
    TransportDecision d = DecideTransportStep(ride, o, stunned);
    CHECK(d.Step == TransportStep::Stop && d.Reason == "transport_approach_motion_lost");
    CHECK(stunned.Approach == ApproachPhase::Idle);
    // Stun over, the car gone: back to the approach start, never the old line.
    o = Walking(); o.Moving = false; o.ReadyToBoard = false; o.RestRemainingMs = 0;
    CHECK(DecideTransportStep(ride, o, stunned).Step == TransportStep::MoveToApproachStart);

    // Knocked out of the walk's corridor while still moving: stop, re-plan.
    TransportMemberState knocked;
    knocked.Approach = ApproachPhase::Walking;
    o = Walking(); o.OffApproachCorridor = true;
    CHECK(DecideTransportStep(ride, o, knocked).Reason == "transport_approach_motion_lost");

    // A delay spent the launch margin: the rest no longer covers what is
    // left of the walk plus the boarding report. Stop on the corridor floor.
    TransportMemberState delayed;
    delayed.Approach = ApproachPhase::Walking;
    o = Walking(); o.RestRemainingMs = 540;
    CHECK(DecideTransportStep(ride, o, delayed).Reason == "transport_approach_rest_lost");
    CHECK(!RestStillCoversWalk(549, 300) && RestStillCoversWalk(550, 300));
    // The car already left: no rest at all.
    TransportMemberState gone;
    gone.Approach = ApproachPhase::Walking;
    o = Walking(); o.ReadyToBoard = false; o.RestRemainingMs = 0;
    CHECK(DecideTransportStep(ride, o, gone).Reason == "transport_approach_rest_lost");
    // Intact and covered: keep walking.
    TransportMemberState fine;
    fine.Approach = ApproachPhase::Walking;
    o = Walking();
    CHECK(DecideTransportStep(ride, o, fine).Reason == "transport_approach_walking");
    // Already on the car's own surface when it goes wrong: stop and board at
    // once instead of leaving the member unboarded on it.
    TransportMemberState onCar;
    onCar.Approach = ApproachPhase::Walking;
    o = Walking(); o.MotionSuspended = true; o.StaticFloorUnderfoot = false; o.TransportFloorUnderfoot = true;
    CHECK(DecideTransportStep(ride, o, onCar).Reason == "transport_board_stop_on_platform");

    // Ledge drop: a step interrupted or displaced over the ledge floor is
    // stopped and re-planned; over the void, gravity takes over whatever
    // became of the step (the fall clears the active slot first).
    TransportContract platform;
    CHECK(!Transport(Nefarian, platform));
    TransportMemberState step;
    step.Approach = ApproachPhase::SteppingOff;
    TransportMemberObservation l;
    l.Alive = true; l.TransportPresent = true; l.StaticFloorUnderfoot = true; l.Moving = true;
    l.MotionSuspended = true;
    d = DecideTransportStep(platform, l, step);
    CHECK(d.Step == TransportStep::Stop && d.Reason == "transport_drop_step_motion_lost");
    CHECK(step.Approach == ApproachPhase::Idle);
    TransportMemberState overVoid;
    overVoid.Approach = ApproachPhase::SteppingOff;
    l.StaticFloorUnderfoot = false; l.OffApproachCorridor = true; l.MotionSuspended = false;
    CHECK(DecideTransportStep(platform, l, overVoid).Step == TransportStep::DropFall);
    return failures ? 1 : 0;
}
""")


def test_landing_without_floor_falls_again_uncounted(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r"""
int main()
{
    TransportContract platform;
    CHECK(!Transport(Nefarian, platform));
    TransportMemberState state;
    state.Approach = ApproachPhase::Falling;
    TransportMemberObservation o;
    o.Alive = true; o.TransportPresent = true; o.Falling = true; o.Moving = true;
    o.LandingPending = true;
    // The fall spline ended but its floor moved away: the landing stage runs
    // MoveFall again (Progressed); the member is falling again, not landed,
    // and nothing counts toward max_submissions (only Retryable/Unsafe do).
    CHECK(DecideTransportStep(platform, o, state).Step == TransportStep::DropLand);
    CHECK(ApproachPhaseAfter(TransportStep::DropLand, false, true) == ApproachPhase::Falling);
    CHECK(ApproachPhaseAfter(TransportStep::DropLand, false, false) == ApproachPhase::Landed);
    state.Approach = ApproachPhaseAfter(TransportStep::DropLand, false, true);
    o.LandingPending = false; o.FallSplineActive = true;
    CHECK(DecideTransportStep(platform, o, state).Reason == "transport_drop_falling");
    CHECK(state.FailedSubmissions == 0);
    return failures ? 1 : 0;
}
""")


def test_completion_override_accepts_only_boss_states(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r"""
static std::string Parse(char const* early)
{
    std::string text = std::string(R"({"entry": 207834, "board_stop_frame": 0, "board_point": [-132.2132, -224.6203, 6.5714], "timeout_ms": 180000, "completion_override": )") + early + "}";
    TransportContract out;
    Json value;
    ParseObjectText(text, value);
    ParseError error = ParseTransport(value, out);
    return error ? error.Detail : std::string("accepted");
}

int main()
{
    CHECK(Parse(R"({"kind": "instance_boss_state", "boss_index": 5, "boss_state": "in_progress"})") == "accepted");
    CHECK(Parse(R"({"kind": "any_of", "contracts": [{"kind": "instance_boss_state", "boss_index": 5, "boss_state": "in_progress"}, {"kind": "instance_boss_state", "boss_index": 5, "boss_state": "done"}]})") == "accepted");
    CHECK(Parse(R"({"kind": "creature_summoned", "entry": 41376})") == "completion_override_kind_unsupported");
    CHECK(Parse(R"({"kind": "any_of", "contracts": [{"kind": "instance_boss_state", "boss_index": 5, "boss_state": "in_progress"}, {"kind": "on_transport", "transport_entry": 207834}]})") == "completion_override_kind_unsupported");
    CHECK(Parse(R"({"kind": "instance_boss_state", "boss_index": 5, "boss_state": "in_progress", "timeout_ms": 1000})") == "completion_override_timeout_unsupported");
    CHECK(Parse(R"({"kind": "instance_boss_state", "boss_index": 5, "boss_state": "engaged"})") == "completion_override:boss_state_shape");
    CHECK(Parse(R"({"kind": "instance_boss_state", "boss_index": 5, "boss_state": "in_progress", "extra": 1})") == "extra");

    TransportContract nefarian;
    CHECK(!Transport(R"({"entry": 207834, "board_stop_frame": 0, "board_point": [-132.2132, -224.6203, 6.5714], "timeout_ms": 180000, "completion_override": {"kind": "instance_boss_state", "boss_index": 5, "boss_state": "in_progress"}})", nefarian));
    CHECK(nefarian.CompletionOverride.Declared && nefarian.CompletionOverride.Kind == CompletionKind::InstanceBossState);
    CHECK(nefarian.CompletionOverride.BossIndex == 5 && nefarian.CompletionOverride.BossState == 1);

    // The override is evaluated from native boss state only...
    struct Boss final : FactSource
    {
        std::uint32_t State = 0;
        std::vector<ActorFact> Creatures(std::uint32_t, std::uint64_t) const override { return {}; }
        ObjectQuery GameObjects(std::uint32_t, std::uint64_t) const override { return {}; }
        bool BossState(std::uint32_t index, std::uint32_t& state) const override { state = State; return index == 5; }
        std::vector<MemberFact> Members() const override { return {}; }
        TransportFact Transport(std::uint32_t, std::uint64_t) const override { return {}; }
    } boss;
    CompletionMemory memory;
    CHECK(!EvaluateCompletion(nefarian.CompletionOverride, boss, memory).Satisfied);
    boss.State = 1;
    CHECK(EvaluateCompletion(nefarian.CompletionOverride, boss, memory).Satisfied);
    // ...and never hands over a member mid-walk, mid-step, mid-fall or landed
    // but not yet boarded (the runtime also checks the falling flags).
    TransportMemberState member;
    CHECK(!ApproachInFlight(member));
    for (ApproachPhase phase : { ApproachPhase::Walking, ApproachPhase::SteppingOff,
             ApproachPhase::Falling, ApproachPhase::Landed })
    {
        member.Approach = phase;
        CHECK(ApproachInFlight(member));
    }
    return failures ? 1 : 0;
}
""")


def test_body_sweep_heights_and_approach_corridor(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r"""
int main()
{
    // A 2.03 yd tall body: rays at 0.5, 0.85, 1.2, 1.55 and 1.827 yd (three
    // lines each: centre and both sides at the collision radius), so a rail
    // at 0.8-1.1 yd cannot slip between them.
    std::vector<float> const lifts = BodySweepLifts(2.03128f);
    CHECK(lifts.size() == 5 && std::fabs(lifts.front() - 0.5f) < 1e-4f);
    CHECK(std::fabs(lifts.back() - 0.9f * 2.03128f) < 1e-4f);
    for (std::size_t i = 1; i < lifts.size(); ++i)
        CHECK(lifts[i] - lifts[i - 1] <= BodySweepLiftStepYards + 1e-4f);
    bool railCovered = false;
    for (float lift : lifts)
        railCovered = railCovered || (lift >= 0.8f && lift <= 1.1f);
    CHECK(railCovered);
    // Tiny or unknown models still sweep from the knee up.
    CHECK(BodySweepLifts(0.0f).front() == 0.5f);
    // Five lines: the centre and half and full collision radius per side.
    CHECK(sizeof(BodySweepSideFractions) / sizeof(BodySweepSideFractions[0]) == 5);
    CHECK(BodySweepSideFractions[0] == 0.0f && BodySweepSideFractions[3] == 1.0f
        && BodySweepSideFractions[4] == -1.0f);

    // Elevator walk corridor: start (-251, -224.605) -> board (-247.349, -224.605).
    Point3 const start{ -251.0f, -224.605f, 190.163f, true };
    Point3 const board{ -247.349f, -224.605f, 190.028f, true };
    CHECK(OnApproachCorridor(start, board, -249.0f, -224.605f, ApproachCorridorYards));
    CHECK(OnApproachCorridor(start, board, -249.0f, -225.8f, ApproachCorridorYards));
    CHECK(!OnApproachCorridor(start, board, -249.0f, -226.0f, ApproachCorridorYards));
    CHECK(!OnApproachCorridor(start, board, -245.9f, -224.605f, ApproachCorridorYards));
    CHECK(!OnApproachCorridor(start, board, -252.4f, -224.605f, ApproachCorridorYards));
    // A ledge drop's corridor reaches MaxStepOffYards + start tolerance out.
    Point3 const lip{ -158.8f, -224.62f, 41.3544f, true };
    Point3 const stepOff{ -156.4f, -224.62f, 41.3544f, true };
    CHECK(OnApproachCorridor(lip, stepOff, -154.2f, -224.62f, ApproachCorridorYards,
        MaxStepOffYards + ApproachStartToleranceYards));
    CHECK(!OnApproachCorridor(lip, stepOff, -152.4f, -224.62f, ApproachCorridorYards,
        MaxStepOffYards + ApproachStartToleranceYards));
    return failures ? 1 : 0;
}
""")


def test_completion_override_never_strands_a_member_on_the_ledge(tmp_path: Path) -> None:
    """Review major: the override held (Onyxia engaged) while one member was
    still Idle at the lip (health too low to drop); nine had boarded."""
    _compile_and_run(tmp_path, PRELUDE + r"""
static std::vector<ApproachMemberView> Raid()
{
    std::vector<ApproachMemberView> members;
    for (std::uint64_t guid = 1; guid <= 10; ++guid)
    {
        ApproachMemberView member;
        member.Guid = guid; member.Alive = true; member.OnRouteInstance = true;
        member.Aboard = true; member.FallMarginOk = true;
        members.push_back(member);
    }
    // Member 7 is still at the lip, Idle, at 50% health (needs 54.9%).
    members[6].Aboard = false; members[6].AtStart = true; members[6].FallMarginOk = false;
    return members;
}

int main()
{
    std::vector<ApproachMemberView> members = Raid();
    // The guard arms when the override holds with someone aboard (t = 10 s):
    // wait for the member for the grace...
    std::uint64_t armed = 0;
    OverrideGuardDecision d = DecideOverrideGuard(members, true, armed, 10000);
    CHECK(armed == 10000 && d.Step == OverrideGuardStep::Wait && d.Member == 7);
    CHECK(d.Reason == "transport_completion_override_waiting_for_member");
    d = DecideOverrideGuard(members, true, armed, 10000 + ApproachHandoverGraceMs - 1);
    CHECK(d.Step == OverrideGuardStep::Wait && armed == 10000);
    // ...then fail typed instead of leaving the member on the ledge.
    d = DecideOverrideGuard(members, true, armed, 10000 + ApproachHandoverGraceMs);
    CHECK(d.Step == OverrideGuardStep::Fail && d.Member == 7);
    CHECK(d.Reason == "transport_completion_override_member_not_aboard");
    // A member already dropping is waited for, past the grace too.
    members[6].Phase = ApproachPhase::SteppingOff;
    d = DecideOverrideGuard(members, true, armed, 60000);
    CHECK(d.Step == OverrideGuardStep::Wait && d.Reason == "transport_completion_override_waiting_in_flight");
    members[6].Phase = ApproachPhase::Falling; members[6].Falling = true;
    CHECK(DecideOverrideGuard(members, true, armed, 60000).Step == OverrideGuardStep::Wait);
    // Landed but not yet boarded: still in flight.
    members[6].Phase = ApproachPhase::Landed; members[6].Falling = false;
    CHECK(DecideOverrideGuard(members, true, armed, 60000).Step == OverrideGuardStep::Wait);
    // Everyone aboard: nothing to guard. The guard never completes the node;
    // the ordinary everyone-aboard completion does.
    members[6].Aboard = true; members[6].Phase = ApproachPhase::Idle;
    d = DecideOverrideGuard(members, true, armed, 10000);
    CHECK(d.Step == OverrideGuardStep::AllAboard && d.Member == 0);
    // Dead members never hold it; a living member off the route instance does.
    members[2].Alive = false; members[2].Aboard = false;
    CHECK(DecideOverrideGuard(members, true, armed, 10000).Step == OverrideGuardStep::AllAboard);
    members[3].Aboard = false; members[3].OnRouteInstance = false;
    CHECK(DecideOverrideGuard(members, true, armed, 10000 + ApproachHandoverGraceMs).Step
        == OverrideGuardStep::Fail);

    // (a) The override stops holding (the fight reset): the guard disarms and
    // the grace restarts from the next time it holds.
    std::vector<ApproachMemberView> reset = Raid();
    std::uint64_t since = 0;
    DecideOverrideGuard(reset, true, since, 5000);
    CHECK(since == 5000);
    CHECK(DecideOverrideGuard(reset, false, since, 6000).Step == OverrideGuardStep::Off && since == 0);
    CHECK(DecideOverrideGuard(reset, true, since, 9000).Step == OverrideGuardStep::Wait && since == 9000);
    CHECK(DecideOverrideGuard(reset, true, since, 9000 + ApproachHandoverGraceMs - 1).Step
        == OverrideGuardStep::Wait);
    // A stale boss state at node entry with nobody aboard yet (everyone still
    // walking to the lip) does not arm the guard or start its grace.
    std::vector<ApproachMemberView> walking = Raid();
    for (ApproachMemberView& member : walking)
    {
        member.Aboard = false; member.AtStart = false;
    }
    std::uint64_t stale = 0;
    for (std::uint64_t now : { 1000u, 30000u, 90000u })
        CHECK(DecideOverrideGuard(walking, true, stale, now).Step == OverrideGuardStep::Off);
    CHECK(stale == 0);

    // Root cause: with the cohort barrier the low-health member holds the
    // whole cohort at the lip (out of combat: it regenerates and the healers
    // beside it can top it up), so nobody boards and engages before it can
    // drop too.
    std::vector<ApproachMemberView> lip = Raid();
    for (ApproachMemberView& member : lip)
    {
        member.Aboard = false; member.AtStart = true;
    }
    CHECK(CohortBarrierHolder(lip) == 7);
    lip[6].FallMarginOk = true;
    CHECK(CohortBarrierHolder(lip) == 0);
    // Still walking to the lip, or outside the route instance: holds it.
    lip[1].AtStart = false;
    CHECK(CohortBarrierHolder(lip) == 2);
    lip[1].AtStart = true; lip[4].OnRouteInstance = false;
    CHECK(CohortBarrierHolder(lip) == 5);
    // Aboard, already dropping, falling or dead: never holds it.
    lip[4].OnRouteInstance = true; lip[4].AtStart = false; lip[4].Aboard = true;
    lip[5].AtStart = false; lip[5].Phase = ApproachPhase::SteppingOff;
    lip[8].AtStart = false; lip[8].Falling = true;
    lip[9].AtStart = false; lip[9].Alive = false;
    CHECK(CohortBarrierHolder(lip) == 0);

    // The override only completes boarding nodes: a ride to an exit is never
    // cut short.
    TransportContract ride;
    CHECK(Transport(R"({"entry": 203716, "board_transport_z": 186.551, "exit_transport_z": 73.8806, "board_point": [-247.349, -224.605, 190.028], "exit_point": [-224.0, -224.605, 76.8211], "timeout_ms": 240000, "completion_override": {"kind": "instance_boss_state", "boss_index": 5, "boss_state": "in_progress"}})", ride).Detail
        == "completion_override_with_exit");
    return failures ? 1 : 0;
}
""")


def test_floor_probe_miss_at_the_lip_holds_the_cohort_while_it_resnaps(tmp_path: Path) -> None:
    """Review (c): a member within the start tolerance but with no verified
    floor there must hold the barrier and re-snap before the others drop."""
    _compile_and_run(tmp_path, PRELUDE + r"""
int main()
{
    // The view: at the start only within the tolerance and on a verified floor.
    CHECK(AtApproachStart(0.4f, 1.0f, true));
    CHECK(!AtApproachStart(0.4f, 1.0f, false));
    CHECK(!AtApproachStart(1.2f, 1.0f, true));

    std::vector<ApproachMemberView> lip;
    for (std::uint64_t guid = 1; guid <= 10; ++guid)
    {
        ApproachMemberView member;
        member.Guid = guid; member.Alive = true; member.OnRouteInstance = true;
        member.FallMarginOk = true;
        member.AtStart = AtApproachStart(0.4f, 1.0f, guid != 4);
        lip.push_back(member);
    }
    CHECK(CohortBarrierHolder(lip) == 4);

    TransportContract platform;
    CHECK(!Transport(Nefarian, platform));
    // Everyone else waits at the lip, watching closely.
    TransportMemberState other;
    TransportMemberObservation o;
    o.Alive = true; o.TransportPresent = true; o.StaticFloorUnderfoot = true;
    o.DistanceToApproachStart = 0.4f; o.ReadyToBoard = true; o.RestRemainingMs = UnboundedRestMs;
    o.CohortAtApproachStart = CohortBarrierHolder(lip) == 0;
    TransportDecision d = DecideTransportStep(platform, o, other);
    CHECK(d.Reason == "transport_drop_waiting_for_cohort" && ApproachWantsFollowUp(platform, d, other));
    // Member 4 (settled, no floor verified, a floor near) re-snaps with an
    // ordinary navmesh move to the approach start...
    TransportMemberState miss;
    TransportMemberObservation m = o;
    m.StaticFloorUnderfoot = false; m.FloorNear = true;
    d = DecideTransportStep(platform, m, miss);
    CHECK(d.Step == TransportStep::MoveToApproachStart
        && d.Reason == "transport_member_floor_unverified_resnap");
    // ...and once its floor is verified the barrier releases everyone.
    lip[3].AtStart = AtApproachStart(0.3f, 1.0f, true);
    CHECK(CohortBarrierHolder(lip) == 0);
    o.CohortAtApproachStart = true;
    CHECK(DecideTransportStep(platform, o, other).Step == TransportStep::DropStepOff);
    return failures ? 1 : 0;
}
""")

def test_nefarian_round2_healer_step_cut_short_steps_off_again_from_the_lip(tmp_path: Path) -> None:
    """Round 2 live evidence (blackwing_descent_10n_nefarian_c0, bot
    11005005, holy paladin): its step toward the lip (from -158.973,
    -224.837) stopped at (-157.653, -224.726, 41.065), still over the ledge
    floor 41.108, when its own heal stopped it to cast Holy Light (landed at
    49.182 s from that point). 1.188 yd from the start point, it walked back
    around to the start, and the others had boarded and engaged before it
    could drop. On the declared line it now counts as at the start."""
    _compile_and_run(tmp_path, PRELUDE + r"""
int main()
{
    TransportContract platform;
    CHECK(!Transport(Nefarian, platform));
    Point3 const& start = platform.Approach.StartPoint;
    Point3 const& stepOff = platform.Approach.StepOffPoint;
    // Where the heal stopped it: 1.19 yd from the start point, 0.31 yd from
    // the declared line; where the walk back settled: 0.51 yd from the start.
    Point3 const cut{ -157.653f, -224.726f, 41.065f, true };
    float const pointDistance = std::sqrt(std::pow(cut.X - start.X, 2.0f)
        + std::pow(cut.Y - start.Y, 2.0f) + std::pow(cut.Z - start.Z, 2.0f));
    CHECK(pointDistance > ApproachStartToleranceYards);
    float const lineDistance = DistanceToApproachLine(start, stepOff, cut.X, cut.Y, cut.Z);
    CHECK(std::fabs(lineDistance - 0.308f) < 0.01f);
    CHECK(std::fabs(DistanceToApproachLine(start, stepOff, -159.174f, -224.543f, 41.01f)
        - 0.514f) < 0.01f);
    // Beyond either end the line is as far as its end point; off it, laterally.
    CHECK(std::fabs(DistanceToApproachLine(start, stepOff, -160.8f, -224.62f, 41.3544f) - 2.0f) < 1e-3f);
    CHECK(std::fabs(DistanceToApproachLine(start, stepOff, -157.6f, -222.62f, 41.3544f) - 2.0f) < 1e-3f);
    Point3 invalid = stepOff;
    invalid.Valid = false;
    CHECK(std::fabs(DistanceToApproachLine(start, invalid, cut.X, cut.Y, cut.Z) - pointDistance) < 1e-3f);

    // The replay: stepping off, then stopped over the floor by the cast.
    TransportMemberState healer;
    healer.Approach = ApproachPhase::SteppingOff;
    TransportMemberObservation o;
    o.Alive = true; o.TransportPresent = true; o.ReadyToBoard = true;
    o.RestRemainingMs = UnboundedRestMs; o.StaticFloorUnderfoot = true;
    o.HealthPct = 0.84f; o.PredictedFallDamagePct = 0.343f;
    o.CohortAtApproachStart = true;
    o.DistanceToApproachStart = pointDistance;
    // Measured from the start point (round 2) it walked back around...
    TransportMemberState before = healer;
    CHECK(DecideTransportStep(platform, o, before).Step == TransportStep::MoveToApproachStart);
    // ...measured from the declared line it steps off again from the lip.
    o.DistanceToApproachStart = lineDistance;
    TransportDecision d = DecideTransportStep(platform, o, healer);
    CHECK(d.Step == TransportStep::DropStepOff && healer.Approach == ApproachPhase::Idle);
    CHECK(ApproachWantsFollowUp(platform, d, healer));
    return failures ? 1 : 0;
}
""")


def test_in_flight_holds_own_casting_and_refusals_count_once_per_window(tmp_path: Path) -> None:
    """A walk, step or fall in flight also owns the cast lanes (a cast-time
    heal stops the member first); a member the executor does not control
    waits instead of spending submissions; refusals at the 100 ms approach
    cadence count once per SubmissionRejectionWindowMs, so exhaustion takes
    seconds of persistent refusal and names the last one."""
    _compile_and_run(tmp_path, PRELUDE + r"""
int main()
{
    TransportContract platform;
    CHECK(!Transport(Nefarian, platform));
    for (char const* reason : { "transport_drop_stepping_off", "transport_drop_falling",
             "transport_approach_walking" })
        CHECK(ApproachHoldOwnsCasting({ TransportStep::Hold, reason }));
    for (char const* reason : { "transport_drop_waiting_for_cohort", "transport_waiting",
             "transport_approach_member_not_free" })
        CHECK(!ApproachHoldOwnsCasting({ TransportStep::Hold, reason }));
    CHECK(!ApproachHoldOwnsCasting({ TransportStep::HoldAboard, "transport_riding" }));
    CHECK(!ApproachHoldOwnsCasting({ TransportStep::Done, "transport_boarded" }));

    // Stepping off with the step intact: the hold that owns casting.
    TransportMemberState stepping;
    stepping.Approach = ApproachPhase::SteppingOff;
    TransportMemberObservation o;
    o.Alive = true; o.TransportPresent = true; o.ReadyToBoard = true;
    o.RestRemainingMs = UnboundedRestMs; o.StaticFloorUnderfoot = true;
    o.HealthPct = 0.95f; o.PredictedFallDamagePct = 0.343f;
    o.CohortAtApproachStart = true; o.DistanceToApproachStart = 0.3f;
    TransportMemberObservation moving = o;
    moving.Moving = true;
    CHECK(ApproachHoldOwnsCasting(DecideTransportStep(platform, moving, stepping)));
    // Falling: the fall spline running is a hold that owns casting too.
    TransportMemberState falling;
    falling.Approach = ApproachPhase::Falling;
    TransportMemberObservation air = o;
    air.StaticFloorUnderfoot = false; air.Falling = true; air.FallSplineActive = true;
    CHECK(ApproachHoldOwnsCasting(DecideTransportStep(platform, air, falling)));
    // A fall a stop cut short mid-air: the falling flags remain, no spline
    // runs, so the landing is owed; the landing step falls on from there.
    air.FallSplineActive = false; air.LandingPending = true;
    TransportDecision d = DecideTransportStep(platform, air, falling);
    CHECK(d.Step == TransportStep::DropLand && falling.Approach == ApproachPhase::Falling);

    // Stunned, rooted or effect-moved at the lip: wait, promptly, uncounted.
    TransportMemberState held;
    TransportMemberObservation stunned = o;
    stunned.MemberNotFree = true;
    d = DecideTransportStep(platform, stunned, held);
    CHECK(d.Step == TransportStep::Hold && d.Reason == "transport_approach_member_not_free");
    CHECK(ApproachWantsFollowUp(platform, d, held) && held.FailedSubmissions == 0);
    CHECK(DecideTransportStep(platform, o, held).Step == TransportStep::DropStepOff);
    // A fear or knockback is neither pathed against nor stopped: far from the
    // start, mid-step over the floor, or mid-walk, the effect runs its course.
    TransportMemberObservation feared = stunned;
    feared.Moving = true; feared.DistanceToApproachStart = 5.0f;
    d = DecideTransportStep(platform, feared, held);
    CHECK(d.Step == TransportStep::Hold && d.Reason == "transport_approach_member_not_free");
    TransportMemberState knocked;
    knocked.Approach = ApproachPhase::SteppingOff;
    feared.OffApproachCorridor = true; feared.DistanceToApproachStart = 0.8f;
    d = DecideTransportStep(platform, feared, knocked);
    CHECK(d.Step == TransportStep::Hold && knocked.Approach == ApproachPhase::Idle);
    TransportContract elevator;
    CHECK(!Transport(Elevator, elevator));
    TransportMemberState walker;
    walker.Approach = ApproachPhase::Walking;
    d = DecideTransportStep(elevator, feared, walker);
    CHECK(d.Step == TransportStep::Hold && d.Reason == "transport_approach_member_not_free"
        && walker.Approach == ApproachPhase::Idle);

    // Five refusals within 0.8 s (the round 2 exhaustion) count once...
    TransportMemberState member;
    std::uint64_t now = 50450;
    for (int i = 0; i < 5; ++i, now += 100)
        CountRejectedSubmission(member, now, i < 4 ? "native_ledge_drop_moving"
            : "native_ledge_drop_immobilized");
    CHECK(member.FailedSubmissions == 1);
    CHECK(member.LastRejection == "native_ledge_drop_immobilized");
    CHECK(DecideTransportStep(platform, o, member).Step == TransportStep::DropStepOff);
    // ...persistent refusal still exhausts, after seconds, not half a second.
    std::uint64_t const first = 50450;
    for (std::uint64_t t = first + 100; t <= first + 3900; t += 100)
        CountRejectedSubmission(member, t, "native_ledge_drop_moving");
    CHECK(member.FailedSubmissions == 4);
    CHECK(CountRejectedSubmission(member, first + 4000, "native_ledge_drop_moving"));
    CHECK(member.FailedSubmissions == platform.MaxSubmissions);
    CHECK(DecideTransportStep(platform, o, member).Reason == "transport_submissions_exhausted");
    CHECK(member.LastRejection == "native_ledge_drop_moving");
    return failures ? 1 : 0;
}
""")


# Patch request to agent M (validation_scenarios_cata_001.json), applied here
# in memory so the exact rows it produces are proven to parse: every
# bwd.transit.lower_wing_elevator and bwd.nefarian.descent row, in every
# scenario copy.
ELEVATOR_APPROACH = {"mode": "surface_walk", "start_point": [-251.0, -224.605, 190.163]}
NEFARIAN_APPROACH = {
    "mode": "ledge_drop", "start_point": [-158.8, -224.62, 41.3544],
    "step_off_point": [-156.4, -224.62, 41.3544], "landing_z": 8.51,
    "landing_tolerance_yards": 1.0, "landing_surface": "transport",
    "min_health_after_fall_pct": 0.2,
}


# Round-2 fix pass: the descent hands over to the encounter once Nefarian's
# End (boss index 5) is in progress and no member is mid-approach.
NEFARIAN_COMPLETION_OVERRIDE = {"kind": "instance_boss_state", "boss_index": 5, "boss_state": "in_progress"}


def apply_approach_patch(row: dict) -> dict:
    contract = dict(row["transport_contract"])
    if row["node_id"] == "bwd.transit.lower_wing_elevator":
        contract.pop("wait_point", None)
        contract["approach"] = ELEVATOR_APPROACH
        contract["disembark_point"] = [-241.349, -224.605, 77.087]
    elif row["node_id"] == "bwd.nefarian.descent":
        contract.pop("wait_point", None)
        contract["approach"] = NEFARIAN_APPROACH
        contract["completion_override"] = NEFARIAN_COMPLETION_OVERRIDE
    return dict(row, transport_contract=contract)


def test_patched_scenario_rows_parse_as_approach_contracts(tmp_path: Path) -> None:
    import json

    config = json.loads((ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text())
    body = []
    for group in ("scenarios", "diagnostic_scenarios"):
        for scenario in config[group]:
            for row in scenario["route"]:
                if "transport_contract" not in row:
                    continue
                patched = apply_approach_patch(row)["transport_contract"]
                literal = json.dumps(json.dumps(patched))
                mode = ("ApproachMode::SurfaceWalk" if row["node_id"] == "bwd.transit.lower_wing_elevator"
                        else "ApproachMode::LedgeDrop")
                override_check = ("CHECK(t.CompletionOverride.Declared && t.CompletionOverride.BossIndex == 5);"
                                  if row["node_id"] == "bwd.nefarian.descent"
                                  else "CHECK(!t.CompletionOverride.Declared);")
                body.append("{ TransportContract t; CHECK(!Transport(" + literal + ", t)); "
                            f"CHECK(t.Approach.Mode == {mode}); CHECK(!t.WaitPoint.Valid); "
                            + override_check + " }")
    assert len(body) >= 3
    _compile_and_run(tmp_path, PRELUDE + "int main()\n{\n" + "\n".join(body)
                     + "\n    return failures ? 1 : 0;\n}\n")
