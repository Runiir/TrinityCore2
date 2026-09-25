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
    // Mid-walk over the corridor lip, even as the rest shrinks: never
    // retreated, stopped or re-planned.
    o.Moving = true; o.RestRemainingMs = 200; o.DistanceToBoard = 2.9f;
    d = DecideTransportStep(ride, o, state);
    CHECK(d.Step == TransportStep::Hold && d.Reason == "transport_approach_walking" && ApproachWantsFollowUp(ride, d, state));
    // Across the seam for one sample: still walking, never a stranding.
    o.StaticFloorUnderfoot = false;
    CHECK(DecideTransportStep(ride, o, state).Reason == "transport_approach_walking");
    // On the platform's own surface the proven walk finishes at its board
    // point (inside the admitted window), then boards there (D's proof).
    o.TransportFloorUnderfoot = true;
    CHECK(DecideTransportStep(ride, o, state).Reason == "transport_approach_walking");
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


def apply_approach_patch(row: dict) -> dict:
    contract = dict(row["transport_contract"])
    if row["node_id"] == "bwd.transit.lower_wing_elevator":
        contract.pop("wait_point", None)
        contract["approach"] = ELEVATOR_APPROACH
        contract["disembark_point"] = [-241.349, -224.605, 77.087]
    elif row["node_id"] == "bwd.nefarian.descent":
        contract.pop("wait_point", None)
        contract["approach"] = NEFARIAN_APPROACH
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
                body.append("{ TransportContract t; CHECK(!Transport(" + literal + ", t)); "
                            f"CHECK(t.Approach.Mode == {mode}); CHECK(!t.WaitPoint.Valid); }}")
    assert len(body) >= 3
    _compile_and_run(tmp_path, PRELUDE + "int main()\n{\n" + "\n".join(body)
                     + "\n    return failures ? 1 : 0;\n}\n")
