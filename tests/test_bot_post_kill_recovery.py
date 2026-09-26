"""The post-kill recovery window (round 10) and its fallback.

Round 8 killed Nefarian (blackwing_descent_10n_nefarian_c0) with six members
dead in the lava; node completion needs every member alive at the node, and
nothing raised them: the combat-res reconciler (BotWorldPopulationMgrCombatRes.cpp)
is combat-only, admits only combat resurrections, and its candidate builder
is closed under native_full_wipe_only. Released members come back to life at
the instance entrance (MovementHandler.cpp: a ghost entering a dungeon with
its corpse there is resurrected at the entrance, no corpse reclaim), and
their return was blocked by the boarding-only descent.

Now, on a canonical-composition raid boss node, once the boss is recorded
killed, the encounter is not in progress and no hostile activity remains
(BotPostKillRecovery.h):
- the out-of-combat resurrections (Redemption 7328, Resurrection 2006,
  Ancestral Spirit 2008, Revive 50769) count, and Rebirth when ready; any
  living member that knows one casts, one body each, healers raised first;
- an approach that would touch liquid before it sees the body in range is
  refused (a body in the lava is raised only from where a caster sees it);
- a dead member holds its release at most 90 s from the window's opening
  while a caster could reach it; a body nobody can reach releases at once;
- the fallback: the return walks past the descent after the kill, and the
  descent is ridden again as a post-kill arrival (recovery_transport entry
  "post_kill_only": true), among its riders only.
"""

from __future__ import annotations

import json
import re
import struct
import subprocess
from pathlib import Path

import pytest

from tools.bot_ml import build_validation_scenario_manifests as builder


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
INCLUDES = ["src/server/game", "src/common"]
CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
DBC = ROOT / "data/dbc/enUS"
DESCENT_ID = "bwd.nefarian.descent"
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


def _source(name: str) -> str:
    return (BOTS / name).read_text(encoding="utf-8")


def _code(text: str) -> str:
    text = re.sub(r"//.*", "", text)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _function(text: str, signature: str) -> str:
    start = text.index(signature)
    depth = 0
    for index in range(text.index("{", start), len(text)):
        depth += {"{": 1, "}": -1}.get(text[index], 0)
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def _config_contract(node_id: str) -> dict:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    for group in ("scenarios", "diagnostic_scenarios"):
        for scenario in config[group]:
            for row in scenario.get("route") or []:
                if row.get("node_id") == node_id and row.get("transport_contract"):
                    return row["transport_contract"]
    raise AssertionError(node_id)


PRELUDE = r'''
#include "Bots/BotPostKillRecovery.h"
#include <cstdio>
#include <string>
#include <vector>

using namespace BotPostKillRecovery;

static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

// Round 8 Nefarian c0 at the kill: the boss node, generation 8.
[[maybe_unused]] static WindowObservation AfterKill(std::uint64_t nowMs)
{
    WindowObservation observation;
    observation.Current = { 1, 8, "bwd.nefarian.encounter" };
    observation.CanonicalRaid = true;
    observation.BossNode = true;
    observation.BossKillRecorded = true;
    observation.EncounterInProgress = false;
    observation.HostileActivityActive = false;
    observation.HostileObservationCurrent = true;
    observation.NowMs = nowMs;
    return observation;
}
'''


def test_window_opens_only_after_a_recorded_kill_with_nothing_hostile(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    CHECK(std::string(ClosedReason(AfterKill(0))).empty());
    auto closed = [](auto mutate)
    {
        WindowObservation observation = AfterKill(0);
        mutate(observation);
        return std::string(ClosedReason(observation));
    };
    // Legacy and accepted scenarios (Stonecore, calibration, the legacy
    // Magmaw diagnostic) are not canonical raids: never open.
    CHECK(closed([](WindowObservation& o) { o.CanonicalRaid = false; }) == "not_canonical_raid");
    CHECK(closed([](WindowObservation& o) { o.BossNode = false; }) == "not_boss_node");
    CHECK(closed([](WindowObservation& o) { o.BossKillRecorded = false; }) == "boss_not_killed");
    CHECK(closed([](WindowObservation& o) { o.EncounterInProgress = true; }) == "encounter_in_progress");
    CHECK(closed([](WindowObservation& o) { o.HostileObservationCurrent = false; }) == "hostile_observation_stale");
    // Round 8: the Lightning Machine stayed active for 8m40s after the kill.
    CHECK(closed([](WindowObservation& o) { o.HostileActivityActive = true; }) == "hostile_activity");

    // The latch: the kill at 700 s, the machine still active until 705 s.
    Latch latch;
    WindowObservation machine = AfterKill(700000);
    machine.HostileActivityActive = true;
    CHECK(Observe(latch, machine) == Edge::None && !latch.Open && latch.Reason == "hostile_activity");
    CHECK(Observe(latch, AfterKill(705000)) == Edge::Opened && latch.Open && latch.OpenedAtMs == 705000);
    CHECK(Observe(latch, AfterKill(706000)) == Edge::None && latch.OpenedAtMs == 705000);
    Scope const current{ 1, 8, "bwd.nefarian.encounter" };
    CHECK(WindowOpen(latch, current));
    // A hostile returning closes it; reopening keeps the first opening (the
    // release hold's bound never restarts in the scope).
    machine.NowMs = 720000;
    CHECK(Observe(latch, machine) == Edge::Closed && !WindowOpen(latch, current));
    CHECK(Observe(latch, AfterKill(730000)) == Edge::Opened && latch.OpenedAtMs == 705000);
    // Another scope (next node, attempt or generation) starts afresh.
    CHECK(!WindowOpen(latch, Scope{ 1, 9, "bwd.nefarian.encounter" }));
    WindowObservation next = AfterKill(800000);
    next.Current = { 1, 9, "bwd.full.next" };
    next.BossKillRecorded = false;
    CHECK(Observe(latch, next) == Edge::Closed && latch.OpenedAtMs == 0 && latch.Of == next.Current);
    return failures ? 1 : 0;
}
''')


def test_spell_selection_is_the_four_out_of_combat_resurrections(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    for (std::uint32_t spell : { 7328u, 2006u, 2008u, 50769u })
        CHECK(IsOutOfCombatResurrection(spell));
    // Rebirth and Raise Ally stay combat resurrections (the reconciler's own
    // predicate admits them); Reincarnation, Soulstone and heals are not.
    for (std::uint32_t spell : { 20484u, 61999u, 20608u, 20707u, 2061u, 0u })
        CHECK(!IsOutOfCombatResurrection(spell));
    // Raise order: healers, then tanks, then the rest.
    CHECK(TargetPriority("healer") > TargetPriority("tank"));
    CHECK(TargetPriority("tank") > TargetPriority("dps") && TargetPriority("") == TargetPriority("dps"));
    return failures ? 1 : 0;
}
''')


def test_spell_ids_are_the_client_resurrections() -> None:
    """4.3.4 client data: each is SPELL_EFFECT_RESURRECT (18) at 35%, peaceful
    only (SPELL_ATTR0_NOT_IN_COMBAT_ONLY_PEACEFUL, so the owner must be out of
    combat), and without the in-combat resurrection limit (ATTR8 0x00800000)
    that the combat-res predicate requires; Rebirth has the limit."""
    if not (DBC / "Spell.dbc").exists() or not (DBC / "SpellEffect.dbc").exists():
        pytest.skip("client DBC files are not materialized locally")

    def rows(name: str):
        data = (DBC / name).read_bytes()
        _, count, fields, size, _ = struct.unpack("<4s4I", data[:20])
        return [struct.unpack(f"<{fields}I", data[20 + i * size:20 + i * size + fields * 4])
                for i in range(count)]

    effects = {}
    for row in rows("SpellEffect.dbc"):
        effects.setdefault(row[24], {})[row[25]] = (row[1], struct.unpack("<i", struct.pack("<I", row[5]))[0])
    spells = {row[0]: row for row in rows("Spell.dbc")}
    for spell in (7328, 2006, 2008, 50769):
        assert effects[spell][0] == (18, 35), spell
        assert spells[spell][1] & 0x10000000, spell  # peaceful only
        assert not spells[spell][9] & 0x00800000, spell  # no in-combat limit
    assert spells[20484][9] & 0x00800000 and not spells[20484][1] & 0x10000000


def test_one_body_per_caster_pending_and_unreachable(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    // Three bodies (raise order) and three caster rows: the holy paladin
    // (Redemption), the disc priest (Resurrection), the feral druid's Rebirth
    // (cooldown row last). The paladin already reserves another body.
    std::vector<std::uint64_t> const keys = { 11, 12, 13 };
    auto usable = [](std::size_t target, std::size_t owner, std::string& reason)
    {
        if (target == 2)
        {
            reason = "declined_no_los_or_valid_path"; // under the platform
            return false;
        }
        if (owner == 2)
        {
            reason = "declined_combat_res_cooldown";
            return false;
        }
        return true;
    };
    std::vector<Assignment> result = Assign(3, keys, { 11 }, usable);
    // Body 0 to the priest; body 1 has no free caster but the busy paladin
    // could serve it: pending; body 2 nobody can reach: unreachable.
    CHECK(result[0].Result == Outcome::Assigned && result[0].Owner == 1);
    CHECK(result[1].Result == Outcome::Pending);
    CHECK(result[2].Result == Outcome::Unreachable);
    // Nobody busy: two bodies raised in parallel by two casters.
    result = Assign(3, keys, {}, usable);
    CHECK(result[0].Result == Outcome::Assigned && result[0].Owner == 0);
    CHECK(result[1].Result == Outcome::Assigned && result[1].Owner == 1);
    CHECK(result[2].Result == Outcome::Unreachable);
    // One caster row per spell: the druid (keys 13, 13) takes one body only.
    result = Assign(2, { 13, 13 }, {}, [](std::size_t, std::size_t, std::string&) { return true; });
    CHECK(result[0].Result == Outcome::Assigned && result[1].Result == Outcome::Pending);
    // A transient refusal (still in combat, casting, mana) keeps it pending.
    result = Assign(1, { 11 }, {}, [](std::size_t, std::size_t, std::string& reason)
    {
        reason = OwnerInCombat;
        return false;
    });
    CHECK(result[0].Result == Outcome::Pending);
    // No caster knows a resurrection: unreachable at once.
    result = Assign(1, {}, {}, [](std::size_t, std::size_t, std::string&) { return true; });
    CHECK(result[0].Result == Outcome::Unreachable);
    for (char const* transient : { "declined_owner_casting", "declined_owner_global_cooldown",
            "declined_insufficient_power", "declined_owner_in_combat",
            "declined_approach_reservation_state_drift" })
        CHECK(DeclineIsTransient(transient));
    for (char const* final : { "declined_no_los_or_valid_path", "declined_combat_res_cooldown",
            "declined_post_kill_approach_through_liquid", "declined_owner_wrong_map",
            "declined_combat_res_not_learned", "declined_owner_dead" })
        CHECK(!DeclineIsTransient(final));
    return failures ? 1 : 0;
}
''')


def test_release_hold_is_bounded_and_ends_for_unreachable_bodies(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    Scope const current{ 1, 8, "bwd.nefarian.encounter" };
    Latch latch;
    // Before the window: no hold (the ordinary native_full_wipe_only gate).
    CHECK(!HoldsRelease(latch, current, "declined_out_of_combat", 700000));
    CHECK(Observe(latch, AfterKill(705000)) == Edge::Opened);
    // Replay, one tick a second: a reserved body, a pending one and one no
    // caster can reach.
    std::uint64_t pendingReleasedAt = 0;
    for (std::uint64_t now = 705000; now <= 900000; now += 1000)
    {
        Observe(latch, AfterKill(now));
        CHECK(HoldsRelease(latch, current, "reserved_approach", now) == (now < 795000));
        CHECK(!HoldsRelease(latch, current, NoReachableCaster, now));
        if (!pendingReleasedAt && !HoldsRelease(latch, current, CasterPending, now))
            pendingReleasedAt = now;
    }
    // About 90 s, then the ordinary release and the post-kill return.
    CHECK(pendingReleasedAt == 705000 + ReleaseHoldMs);
    // The bound belongs to the scope and the window: closed, or another
    // node, no hold.
    CHECK(!HoldsRelease(latch, Scope{ 1, 9, "bwd.nefarian.encounter" }, "reserved_approach", 710000));
    WindowObservation machine = AfterKill(710000);
    machine.HostileActivityActive = true;
    Observe(latch, machine);
    CHECK(!HoldsRelease(latch, current, "reserved_approach", 710000));
    return failures ? 1 : 0;
}
''')


def test_an_approach_walks_to_a_dry_point_in_range_never_to_the_body(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    // Samples every 2 yd from the caster: L = liquid, E = in the envelope
    // (in range with line of sight), . = dry and out of range. The returned
    // index is the destination the executor walks to; path.size() = refused.
    auto destination = [](std::string const& path)
    {
        return ApproachDestination(path.size(),
            [&](std::size_t i) { return path[i] == 'L'; },
            [&](std::size_t i) { return path[i] == 'E'; });
    };
    CHECK(destination("...E") == 3);
    CHECK(destination("E") == 0);             // already in range: no step at all
    // Round 8: a body in the lava, a dry rim in range first. The caster
    // walks to the rim sample (index 2), never on to the body at the end.
    std::string const rim = "..EELLLL";
    CHECK(destination(rim) == 2 && rim[destination(rim)] == 'E');
    CHECK(destination("..LE") == 4);          // the lava first: refused
    CHECK(destination("...LLL") == 6);        // never seen from dry ground
    CHECK(destination("....") == 4);          // never reaches the envelope
    CHECK(destination("L..E") == 4);          // the caster stands in liquid
    return failures ? 1 : 0;
}
''')


def test_deadline_binds_reservations_approach_and_cast_alike(tmp_path: Path) -> None:
    """The dead member's handler in order (BotWorldPopulationMgrUpdateDeath.cpp):
    the window's release hold, then the wait on its reservation, then the
    ordinary release. Replayed each second around the 90 s deadline with a
    post-kill approach reserved at 85 s, a Redemption cast submitted at 89 s
    (10 s cast, pending to 104 s), and an in-combat Rebirth reservation made
    before the window opened, which the deadline never binds."""
    _compile_and_run(tmp_path, PRELUDE + r'''
enum class Step { HoldWindow, WaitReservation, Release };

struct Body
{
    std::string Decision;
    std::uint32_t Spell = 0;
    std::uint64_t ReservedAtMs = 0;
    std::uint64_t ReservedUntilMs = 0;
};

// HoldsRelease first, then DecideReservationWait with the deadline, as the
// handler runs them; the owner stays otherwise usable while its reservation
// lasts (the intent is current, the cast in progress).
static Step Handle(Latch const& latch, Scope const& scope, Body const& body, std::uint64_t now)
{
    if (HoldsRelease(latch, scope, body.Decision, now))
        return Step::HoldWindow;
    bool const present = body.Decision == "reserved_approach"
        || body.Decision == "reserved_cast_submitted";
    bool const expired = ReservationPastDeadline(latch, scope, body.Spell, body.ReservedAtMs, now);
    ReservationVerdict const verdict = DecideReservationWait(present, true, expired,
        present && !expired && now < body.ReservedUntilMs);
    if (verdict.Step == ReservationStep::Wait)
        return Step::WaitReservation;
    if (verdict.Step == ReservationStep::Decline && expired)
        CHECK(std::string(verdict.Reason) == Deadline);
    return Step::Release;
}

int main()
{
    Scope const scope{ 1, 8, "bwd.nefarian.encounter" };
    Latch latch;
    Observe(latch, AfterKill(0));
    CHECK(latch.OpenedAtMs == 0);
    // OpenedAtMs 0 is "never opened": open the window at 1 s instead.
    latch = Latch();
    CHECK(Observe(latch, AfterKill(1000)) == Edge::Opened);
    std::uint64_t const deadline = 1000 + ReleaseHoldMs;
    CHECK(!PastDeadline(latch, scope, deadline - 1) && PastDeadline(latch, scope, deadline));

    Body approach{ "reserved_approach", Redemption, 86000, 94000 };
    Body cast{ "reserved_cast_submitted", Redemption, 90000, 105000 };
    Body inCombat{ "reserved_cast_submitted", 20484, 500, 400000 };
    for (std::uint64_t now = 80000; now <= 110000; now += 1000)
    {
        Observe(latch, AfterKill(now));
        Step const a = Handle(latch, scope, approach, now);
        Step const c = Handle(latch, scope, cast, now);
        if (now < deadline)
        {
            CHECK(a == Step::HoldWindow && c == Step::HoldWindow);
        }
        else
        {
            // Both straddle the deadline: released at once, not held to the
            // end of the approach (94 s) or the cast (105 s).
            CHECK(a == Step::Release);
            CHECK(c == Step::Release);
        }
        // The pre-window in-combat reservation waits as before.
        CHECK(now < deadline ? Handle(latch, scope, inCombat, now) == Step::HoldWindow
            : Handle(latch, scope, inCombat, now) == Step::WaitReservation);
        CHECK(!ReservationPastDeadline(latch, scope, inCombat.Spell, inCombat.ReservedAtMs, now));
    }
    // No reservation, no window: the ordinary release.
    CHECK(DecideReservationWait(false, true, false, false).Step == ReservationStep::None);
    CHECK(std::string(DecideReservationWait(true, false, true, true).Reason)
        == "declined_typed_intent_not_current");
    CHECK(DecideReservationWait(true, true, false, false).Step == ReservationStep::Decline
        && *DecideReservationWait(true, true, false, false).Reason == 0);
    // Another scope is never bound; a closed window binds only the
    // out-of-combat spells (Rebirth there is an in-combat reservation).
    CHECK(!ReservationPastDeadline(latch, Scope{ 1, 9, "x" }, Redemption, 90000, 200000));
    WindowObservation machine = AfterKill(200000);
    machine.HostileActivityActive = true;
    Observe(latch, machine);
    CHECK(ReservationPastDeadline(latch, scope, Redemption, 150000, 200000));
    CHECK(!ReservationPastDeadline(latch, scope, 20484, 150000, 200000));
    return failures ? 1 : 0;
}
''')


def test_boss_kill_is_the_nodes_boss_killed_terminal(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
struct State
{
    bool ValidationRouteTerminalState = false;
    std::uint64_t ValidationRouteTerminalGeneration = 0;
    std::string ValidationRouteTerminalReason;
};

int main()
{
    std::vector<State> states(3);
    CHECK(!BossKillRecorded(states, 8));
    states[1] = { true, 8, "native_postcondition" };
    CHECK(!BossKillRecorded(states, 8));
    states[2] = { true, 7, "boss_killed" };
    CHECK(!BossKillRecorded(states, 8));
    states[0] = { true, 8, "boss_killed" };
    CHECK(BossKillRecorded(states, 8));
    states[0].ValidationRouteTerminalState = false;
    CHECK(!BossKillRecorded(states, 8));
    return failures ? 1 : 0;
}
''')


TRANSIT_PRELUDE = r'''
#include "Bots/BotValidationRouteNativeContract.h"
#include "Bots/BotValidationRouteNativeLogic.h"
#include "Bots/BotValidationRouteNativeRecovery.h"
#include "Bots/BotValidationRouteRecoveryReturn.h"
#include <cstdio>
#include <string>
#include <vector>

using namespace BotValidationRouteNative;

static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

static ParseError Recovery(std::string const& text, std::vector<RecoveryTransit>& out)
{
    Json value;
    if (ParseError error = ParseArrayText(text, value))
        return error;
    return ParseRecoveryTransports(value, out);
}
'''


def _transit_program(body: str) -> str:
    descent = json.dumps(_config_contract(DESCENT_ID))
    elevator = json.dumps(_config_contract(ELEVATOR_ID))
    return (TRANSIT_PRELUDE
            + 'static std::string const Descent = R"J(' + descent + ')J";\n'
            + 'static std::string const Elevator = R"J(' + elevator + ')J";\n'
            + body)


def test_the_descent_parses_as_a_post_kill_arrival(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, _transit_program(r'''
static std::string Row(char const* id, std::string const& contract, char const* extra = "")
{
    return std::string("{\"node_id\": \"") + id + "\", \"contract\": " + contract + extra + "}";
}

int main()
{
    std::vector<RecoveryTransit> transits;
    CHECK(!Recovery("[" + Row("bwd.transit.lower_wing_elevator", Elevator) + ", "
        + Row("bwd.nefarian.descent", Descent, ", \"post_kill_only\": true") + "]", transits));
    CHECK(transits.size() == 2 && !transits[0].PostKillOnly && transits[1].PostKillOnly);
    TransportContract const& descent = transits[1].Transport;
    CHECK(ArrivalOnly(descent) && !ArrivalOnly(transits[0].Transport));
    float boardZ = 0.0f, exitZ = 0.0f;
    CHECK(RecoveryLevels(descent, boardZ, exitZ));
    CHECK(std::fabs(boardZ - 41.3544f) < 1e-3f && std::fabs(exitZ - 7.1075f) < 1e-3f);
    // The Nefarian node's anchor is on the raised platform: it applies.
    CHECK(RecoveryApplies(descent, 7.1075f));
    // The elevator's levels are unchanged.
    CHECK(RecoveryLevels(transits[0].Transport, boardZ, exitZ));
    CHECK(std::fabs(boardZ - 190.163f) < 1e-3f && std::fabs(exitZ - 76.8211f) < 1e-3f);

    auto invalid = [&](std::string const& text, char const* detail)
    {
        ParseError const error = Recovery(text, transits);
        CHECK(error.Kind == ParseError::Code::Invalid && error.Detail == detail);
        if (error.Detail != detail)
            std::fprintf(stderr, "detail %s\n", error.Detail.c_str());
    };
    // Without the flag the descent is still no ride; a ride is no arrival.
    invalid("[" + Row("bwd.nefarian.descent", Descent) + "]", "recovery_transport_requires_exit");
    invalid("[" + Row("bwd.nefarian.descent", Descent, ", \"post_kill_only\": false") + "]",
        "recovery_transport_requires_exit");
    invalid("[" + Row("bwd.transit.lower_wing_elevator", Elevator, ", \"post_kill_only\": true") + "]",
        "recovery_transport_post_kill_requires_arrival");
    invalid("[" + Row("bwd.nefarian.descent", Descent, ", \"post_kill_only\": 1") + "]",
        "recovery_transport_post_kill_only");
    return failures ? 1 : 0;
}
'''))


def test_arrival_riders_the_survivors_and_the_return(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, _transit_program(r'''
int main()
{
    std::vector<RecoveryTransit> transits;
    CHECK(!Recovery("[{\"node_id\": \"bwd.nefarian.descent\", \"contract\": " + Descent
        + ", \"post_kill_only\": true}]", transits));
    TransportContract const& descent = transits[0].Transport;
    float boardZ = 0.0f, exitZ = 0.0f;
    CHECK(RecoveryLevels(descent, boardZ, exitZ));

    RecoveryMemberView rider;
    rider.Alive = true; rider.OnRouteInstance = true; rider.Released = true;
    rider.Arrival = true; rider.AtExit = true;
    // Resurrected at the entrance (-345.87, -224.34, 193.13), back at the
    // orb (63.3) or the lip (41.1): the board side. The elevator (earlier in
    // route order) runs first while it is needed there.
    for (float z : { 193.127f, 76.8211f, 63.30268f, 41.104f })
    {
        rider.Z = z;
        CHECK(MemberNeedsRide(rider, boardZ, exitZ));
    }
    // Stepping, falling or landed and boarding: still riding.
    rider.Z = 20.0f;
    rider.InFlight = true;
    CHECK(MemberNeedsRide(rider, boardZ, exitZ));
    // Aboard the platform: arrived (a ride's passenger would still ride).
    rider.InFlight = false;
    rider.Aboard = true;
    rider.Z = 8.5f;
    CHECK(!MemberNeedsRide(rider, boardZ, exitZ));
    RecoveryMemberView ridePassenger = rider;
    ridePassenger.Arrival = false;
    CHECK(MemberNeedsRide(ridePassenger, boardZ, exitZ));
    // A survivor on the ring (passenger or not) never needs it, never
    // released; so it is never a rider and never holds the drop barrier.
    RecoveryMemberView survivor;
    survivor.Alive = true; survivor.OnRouteInstance = true; survivor.Arrival = true;
    survivor.AtExit = true; survivor.Z = 8.6f;
    CHECK(!MemberNeedsRide(survivor, boardZ, exitZ));
    survivor.Released = true;
    CHECK(!MemberNeedsRide(survivor, boardZ, exitZ));
    // An engaged arrival pauses its riders' return clock until they board.
    CHECK(RecoveryRideHoldsMember(true, descent, 41.104f, false));
    CHECK(!RecoveryRideHoldsMember(true, descent, 8.5f, true));
    CHECK(!RecoveryRideHoldsMember(false, descent, 41.104f, false));

    // The return: blocked by the descent, it walks after the kill only.
    namespace Return = BotValidationRouteRecoveryReturn;
    Return::Input input;
    input.AttemptId = 1; input.RouteGeneration = 8; input.Eligible = true;
    input.Alive = true; input.InRouteInstance = true; input.DistanceToAnchor = 250.0f;
    input.Blocked = true; input.NowMs = 1000;
    Return::Memory memory;
    Return::Arm(memory, 1, 8);
    CHECK(Return::Decide(memory, input).Step == Return::Verdict::Idle && !memory.Pending);
    Return::Arm(memory, 1, 8);
    input.WipedHere = true;
    CHECK(std::string(Return::Decide(memory, input).Reason) == "boarding_without_recovery");
    Return::Arm(memory, 1, 8);
    input.WipedHere = false;
    input.PostKillReturn = true;
    CHECK(Return::Decide(memory, input).Step == Return::Verdict::Returning && memory.Pending);
    input.NowMs = 2000;
    input.DistanceToAnchor = 20.0f;
    CHECK(Return::Decide(memory, input).Step == Return::Verdict::Arrived);
    return failures ? 1 : 0;
}
'''))


def _scenarios() -> dict[str, dict]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    rows = list(config.get("scenarios") or []) + list(config.get("diagnostic_scenarios") or [])
    return {str(row["id"]): row for row in rows if isinstance(row, dict) and row.get("id")}


def test_builder_emits_the_arrival_on_composition_boss_rows_beyond_it() -> None:
    scenarios = _scenarios()
    for scenario_id, scenario in scenarios.items():
        parent = scenarios.get(str(scenario.get("diagnostic_parent_scenario_id") or ""), {})
        arrivals = builder.post_kill_arrivals(scenario.get("route") or [], parent.get("route") or [])
        if DESCENT_ID in [str(step.get("node_id")) for step in (scenario.get("route") or [])
                          + (parent.get("route") or [])]:
            assert list(arrivals) == [DESCENT_ID], scenario_id
            assert arrivals[DESCENT_ID] == _config_contract(DESCENT_ID)
        else:
            assert arrivals == {}, scenario_id
    # The elevator is a ride, never an arrival.
    assert builder.ride_levels(_config_contract(ELEVATOR_ID)) is not None

    source = (ROOT / "tools/bot_ml/build_validation_scenario_manifests.py").read_text(encoding="utf-8")
    assert ('                arrival = arrivals.get(blocked_by or "")\n'
            '                if arrival and step.get("kind") == "boss":\n'
            '                    route["recovery_transport"] = list(route.get("recovery_transport") or []) + [\n'
            '                        {"node_id": blocked_by, "contract": copy.deepcopy(arrival), '
            '"post_kill_only": True}]\n') in source
    # Only inside the composition opt-in (legacy rows, Stonecore, calibration
    # and the accepted Magmaw diagnostic never carry it).
    block = source[source.index("            if composition_recovery(scenario):"):]
    block = block[:block.index("            patrol_combat_anchor")]
    assert "arrival = arrivals.get(blocked_by" in block


def test_manifests_carry_the_arrival_on_the_canonical_nefarian_rows() -> None:
    manifests = builder.build_manifests(
        json.loads(CONFIG.read_text(encoding="utf-8")),
        {"all_ready": True, "scenarios": []},
        {"all_passed": True},
        json.loads((ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json")
                   .read_text(encoding="utf-8")),
    )
    carried = []
    for row in manifests["validation_routes"]:
        entries = row.get("recovery_transport") or []
        arrivals = [entry for entry in entries if entry.get("post_kill_only")]
        if not arrivals:
            continue
        carried.append((row["scenario_id"], row["route_node_id"]))
        assert row.get("kind") == "boss" and row.get("composition_recovery") is True, carried[-1]
        assert row.get("recovery_return_blocked_by") == DESCENT_ID, carried[-1]
        assert [entry["node_id"] for entry in entries] == [ELEVATOR_ID, DESCENT_ID], carried[-1]
        assert arrivals[0]["contract"] == _config_contract(DESCENT_ID)
    # The canonical composition's Nefarian boss rows (shard and full route).
    assert carried and all(node == "bwd.nefarian.encounter" for _, node in carried), carried
    assert {"blackwing_descent_10n_full_c0"} <= {scenario for scenario, _ in carried}, carried
    # Legacy rows (no composition_id) never carry it.
    for row in manifests["validation_routes"]:
        if not row.get("composition_recovery"):
            assert not any(entry.get("post_kill_only") for entry in row.get("recovery_transport") or [])


def test_server_wiring() -> None:
    combat = _code(_source("BotWorldPopulationMgrCombatRes.cpp"))
    usable = _function(combat, "bool BotWorldPopulationMgr::CurrentCombatResOwnerUsable(")
    # Out-of-combat resurrections only while the window is open.
    assert ("if (!IsNativeCombatResSpell(spellInfo)\n"
            "        && !(spellInfo && postKillWindow && BotPostKillRecovery::IsOutOfCombatResurrection(spellId)))") in usable
    assert "if (!spellInfo->CanBeUsedInCombat() && owner->IsInCombat())" in usable
    assert usable.index("CanBeUsedInCombat()") < usable.index("declined_combat_res_cooldown")
    reconcile = _function(combat, "void BotWorldPopulationMgr::ReconcileNativeBattleResDecisions(")
    # Observed every update before the dead-member return; canonical only.
    assert reconcile.index("BotPostKillRecovery::Observe(runtime.PostKillRecovery, observation)") \
        < reconcile.index("if (dead.empty())")
    assert ("observation.CanonicalRaid = BotCanonicalRaidScope::IsCanonicalRaid(\n"
            "            runtime.RaidInstance, Cohort().Config.ValidationRouteScenarioId);") in reconcile
    assert reconcile.index("reconcilePostKill();") < reconcile.index('applyDecision(member, "declined_out_of_combat")')
    # The in-combat path keeps its single-target reservation and owner rule.
    assert "if (stagedOwnerUsable(*selected, candidate.Owner.Bot, candidate.SpellId, declineReason))" in reconcile
    assert "BotCombatResEligibility::RoleMayCast(canonicalRaid," in reconcile
    build = _function(combat, "BotWorldPopulationMgr::BuildCombatResNativeActionCandidate(")
    assert ("        || (Cohort().Config.ValidationRouteBossRecovery\n"
            "                == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly\n"
            "            && !PostKillRecoveryWindowOpen()))") in build

    # Validation and execution share one destination; the deadline binds the
    # owner check (approach, submitted cast, reconciler) and the reconciler
    # reserves nothing after it.
    assert ("if (postKillWindow && !PostKillApproachDestination(owner, target, resurrectionRange,\n"
            "                destinationX, destinationY, destinationZ))") in usable
    deadline = usable.index("BotPostKillRecovery::ReservationPastDeadline(Cohort().Raid.PostKillRecovery,")
    assert deadline < usable.index("if (submittedCastPending)") < usable.index("return true;")
    assert "if (pastDeadline)\n            {\n                applyDecision(member, BotPostKillRecovery::Deadline);" \
        in reconcile
    native = _code(_source("BotWorldPopulationMgrNativeAction.cpp"))
    approach = native[native.index("BotNativeAction::CombatResApproach>)"):]
    approach = approach[:approach.index("BotNativeAction::CombatResCast>)")]
    stop = approach.index("bot->StopMoving();")
    assert approach.index("if (postKillWindow && inEnvelope") < stop \
        < approach.index("if (bot->HasUnitState(UNIT_STATE_CASTING))") < approach.index("if (inEnvelope)")
    assert ("if (postKillWindow && !PostKillApproachDestination(bot, target, resurrectionRange,\n"
            "                    destinationX, destinationY, destinationZ))") in approach
    assert ("bool const moved = MoveBotToPoint(state, bot,\n"
            "                destinationX, destinationY, destinationZ, false,") in approach
    assert "postKillWindow ? nullptr : target);" in approach
    # Outside the window the approach is unchanged: the body, followed.
    assert "float destinationX = target->GetPositionX();" in approach

    death = _code(_source("BotWorldPopulationMgrUpdateDeath.cpp"))
    wait = death.index("BotPostKillRecovery::DecideReservationWait(combatResReservationPresent,")
    assert death.index("BotPostKillRecovery::HoldsRelease(Cohort().Raid.PostKillRecovery,") < wait \
        < death.index("RecoverDeadBot(state, bot)")
    assert ("&& acceptedCombatResIntentCurrent && !postKillReservationExpired\n"
            "                && CurrentCombatResOwnerUsable(state, bot, recoveryNowMs, combatResDeclineReason);") in death
    assert ("bool const battleResReserved =\n"
            "                reservation.Step == BotPostKillRecovery::ReservationStep::Wait;") in death
    assert ": postKillReservationExpired\n                            ? std::string(BotPostKillRecovery::Deadline)" in death
    hold = death.index("BotPostKillRecovery::HoldsRelease(Cohort().Raid.PostKillRecovery,")
    assert death.index("if (deathRecoveryReady)") < hold \
        < death.index("native_full_wipe_wait_partial_death") < death.index("RecoverDeadBot(state, bot)")
    assert "&& IsNativeCombatResTarget(state, bot))" in death[hold:hold + 400]

    recovery = _code(_source("BotWorldPopulationMgrValidationRouteNativeRecovery.cpp"))
    assert "if (transit.PostKillOnly && !(input.PostKillReturn && input.CompositionRecovery))" in recovery
    assert "view.Arrival = ArrivalOnly(ride);" in recovery
    kernel = _code(_source("BotWorldPopulationMgrUpdateBotKernelPreparation.cpp"))
    assert "nativeInput.PostKillReturn = Cohort().Config.ValidationRouteKind == \"boss\"" in kernel
    returns = _code(_source("BotWorldPopulationMgrValidationRouteRecoveryReturn.cpp"))
    assert "input.PostKillReturn = BotPostKillRecovery::BossKillRecorded(manager.Party().Bots," in returns
    # Only native player actions: no teleport, resurrection or state write
    # is issued by the window itself.
    header = _code(_source("BotPostKillRecovery.h"))
    for forbidden in ("TeleportTo", "ResurrectPlayer", "SetHealth", "NearTeleportTo", "Relocate"):
        assert forbidden not in header
        assert forbidden not in _function(combat, "void BotWorldPopulationMgr::ReconcileNativeBattleResDecisions(")


def test_modules_stay_small() -> None:
    for name in ("BotPostKillRecovery.h", "BotWorldPopulationMgrCombatRes.cpp",
                 "BotWorldPopulationMgrUpdateDeath.cpp", "BotValidationRouteNativeRecovery.h",
                 "BotValidationRouteNativeContract.h", "BotValidationRouteRecoveryReturn.h",
                 "BotWorldPopulationMgrValidationRouteNativeRecovery.cpp",
                 "BotWorldPopulationMgrValidationRouteNativeRuntime.cpp",
                 "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp", "BotWorldPopulationMgr.h",
                 "BotWorldPopulationMgrRuntimeContracts.h", "BotWorldPopulationMgrNativeAction.cpp"):
        assert len(_source(name).splitlines()) < 1000, name
    assert len(_source("BotValidationRouteNativeTypes.h").splitlines()) < 300
    includes = re.findall(r'#include [<"]([^>"]+)[>"]', _source("BotPostKillRecovery.h"))
    assert all("/" not in name and not name.endswith(".h") for name in includes), includes
