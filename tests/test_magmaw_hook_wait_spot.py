from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TDB_WORLD = ROOT / ("data/TDB_full_434.22011_2022_01_09/"
                    "TDB_full_world_434.22011_2022_01_09.sql")
MAGMAW_DISPLAY_ID = 32679


def _compile_and_run(source: Path, binary: Path) -> None:
    subprocess.run(
        [
            "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "src/server/game"),
            "-I", str(ROOT / "src/server/game/Entities/Object"),
            "-I", str(ROOT / "src/common"),
            "-I", str(ROOT / "src/common/Utilities"),
            "-I", str(ROOT / "src/common/Logging"),
            "-I", str(ROOT / "src/common/Debugging"),
            str(source), "-o", str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_riders_wait_outside_magmaw_melee_reach(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_hook_wait_spot.cpp"
    binary = tmp_path / "magmaw_hook_wait_spot"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "ObjectDefines.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <iterator>
#include <string>
#include <vector>

using namespace BotEncounter;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

// Live geometry: Magmaw's spawn and the encounter node's navigation anchor
// from the validation route manifest (bwd.magmaw.encounter).
static Vector3 const MagmawCentre{ -302.467f, -31.7101f, 210.8483f };
static Vector3 const NavigationAnchor{ -307.531f, -35.4375f, 211.815f };

// Engine rules, from the engine's own constants. Magmaw's combat reach is
// creature_model_info 32679 CombatReach 15 x scale 1 (checked separately).
static float const MagmawReach = 15.0f;
static float const MeleeReach = std::max(MagmawReach
    + DEFAULT_PLAYER_COMBAT_REACH + 1.3333334f, NOMINAL_MELEE_RANGE);
static float const ClickReach = INTERACTION_DISTANCE
    + DEFAULT_PLAYER_COMBAT_REACH + MagmawReach;
// Player base run speed (baseMoveSpeed[MOVE_RUN]).
static float const RunSpeed = 7.0f;

static float SpatialDistance(Vector3 const& a, Vector3 const& b)
{
    return std::sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y)
        + (a.Z - b.Z) * (a.Z - b.Z));
}

static float PlanarDistance(Vector3 const& a, Vector3 const& b)
{
    return std::hypot(a.X - b.X, a.Y - b.Y);
}

static ActorSnapshot Player(uint32 guid, char const* role, char const* spec,
    Vector3 position)
{
    ActorSnapshot player;
    player.Guid = ObjectGuid(HighGuid::Player, guid);
    player.Kind = ActorKind::Player;
    player.Role = role;
    player.ClassSpec = spec;
    player.Position = position;
    player.HealthPct = 100.0f;
    player.Alive = true;
    return player;
}

// The 10N roster at its recorded pre-Mangle spots (bundle1 kill 1, 86 s):
// Fire B 13.8 yd and Affliction 8.0 yd from Magmaw's centre, both inside
// his melee reach. Riders are Fire B (30007) and Affliction (30008).
static Blackboard LiveBoard()
{
    Blackboard board;
    board.CurrentScope = Scope{
        "hook-wait", 7, 0, 4, "bwd.magmaw.encounter", 669, 1, "magmaw" };
    board.Revision = 41;
    board.ObservedAtMs = 1788793560680;
    board.NativeBossState = "in_progress";
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { NavigationAnchor };
    Vector3 const support{ -308.9f, -36.5f, 211.6f };
    board.Players = {
        Player(30001, "dps", "balance_druid", { -309.4f, -33.6f, 211.5f }),
        Player(30002, "tank", "blood_death_knight", { -304.0f, -48.0f, 212.1f }),
        Player(30003, "healer", "restoration_druid", support),
        Player(30004, "healer", "holy_paladin", support),
        Player(30005, "healer", "discipline_priest", support),
        Player(30006, "dps", "fire_mage", { -326.6f, -49.5f, 211.8f }),
        Player(30007, "dps", "fire_mage", { -314.6f, -25.1f, 211.1f }),
        Player(30008, "dps", "affliction_warlock", support),
        Player(30009, "dps", "survival_hunter", { -326.6f, -49.5f, 211.8f }),
        Player(30010, "dps", "elemental_shaman", { -313.7f, -30.0f, 211.4f }) };
    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit, AdaptiveMagmawStrategy::BossEntry,
        uint32(39));
    boss.Entry = AdaptiveMagmawStrategy::BossEntry;
    boss.Alive = boss.Attackable = boss.Selectable = boss.InCombat = true;
    boss.Position = MagmawCentre;
    boss.VictimGuid = board.Players[1].Guid;
    board.Hostiles = { boss };
    return board;
}

static ActorSnapshot& Member(Blackboard& board, uint32 guid)
{
    for (ActorSnapshot& player : board.Players)
        if (player.Guid.GetCounter() == guid)
            return player;
    assert(false);
    return board.Players.front();
}

// The Mangle seize: the tank carries Mangle, Magmaw is not clickable yet.
static void Seize(Blackboard& board)
{
    board.Hostiles.front().Interactable = false;
    board.Summons.clear();
    Member(board, 30002).Auras = {
        AuraSnapshot{ 89773u, board.Hostiles.front().Guid, 1, 0 } };
}

// Massive Crash has landed: the mount window is open.
static void OpenWindow(Blackboard& board)
{
    board.Hostiles.front().Interactable = true;
    ActorSnapshot left = board.Hostiles.front();
    left.Interactable = false;
    left.Guid = ObjectGuid(HighGuid::Unit,
        AdaptiveMagmawStrategy::PincerLeftEntry, uint32(700));
    left.Entry = AdaptiveMagmawStrategy::PincerLeftEntry;
    ActorSnapshot right = left;
    right.Guid = ObjectGuid(HighGuid::Unit,
        AdaptiveMagmawStrategy::PincerRightEntry, uint32(702));
    right.Entry = AdaptiveMagmawStrategy::PincerRightEntry;
    ActorSnapshot spike = left;
    spike.Guid = ObjectGuid(HighGuid::Unit, AdaptiveMagmawStrategy::SpikeEntry,
        uint32(701));
    spike.Entry = AdaptiveMagmawStrategy::SpikeEntry;
    board.Summons = { left, right, spike };
}

// Magmaw's native Mangle timer as the blackboard publishes it.
static void MangleTimer(Blackboard& board, uint32 remainingMs,
    bool sequenceActive = false)
{
    board.Hostiles.front().MechanicTimers = { MechanicTimerSnapshot{ 88253u,
        remainingMs, sequenceActive, FactSource::NativeInstanceState } };
}

static AdaptiveMagmawPlan PlanFor(Blackboard const& board, uint32 guid)
{
    AdaptiveMagmawStrategy strategy;
    ActorSnapshot const& bot = Member(const_cast<Blackboard&>(board), guid);
    return strategy.Propose(board, bot.Guid, bot.Role);
}

static BotNativeAction::Candidate const* Find(AdaptiveMagmawPlan const& plan,
    char const* mechanic)
{
    for (BotNativeAction::Candidate const& candidate : plan.Movement.Proposals())
        if (candidate.Id.Mechanic == mechanic)
            return &candidate;
    if (plan.Interaction && plan.Interaction->Id.Mechanic == mechanic)
        return &*plan.Interaction;
    return nullptr;
}

static Vector3 MoveTarget(BotNativeAction::Candidate const& candidate)
{
    auto const& move = std::get<BotNativeAction::Move>(candidate.Action);
    return { move.X, move.Y, move.Z };
}

int main()
{
    assert(std::fabs(MeleeReach - 17.8333f) < 0.001f);
    assert(std::fabs(ClickReach - 21.5f) < 0.001f);

    // After the seize both riders leave their spots inside the reach for
    // one wait point beyond it, on the room ray.
    Blackboard seized = LiveBoard();
    Seize(seized);
    AdaptiveMagmawPlan const firePlan = PlanFor(seized, 30007);
    AdaptiveMagmawPlan const warlockPlan = PlanFor(seized, 30008);
    BotNativeAction::Candidate const* fire = Find(firePlan,
        "pincer_preposition");
    BotNativeAction::Candidate const* warlock = Find(warlockPlan,
        "pincer_preposition");
    assert(fire && warlock);
    Vector3 const wait = MoveTarget(*fire);
    Vector3 const warlockWait = MoveTarget(*warlock);
    assert(SpatialDistance(wait, warlockWait) < 0.001f);
    assert(wait.Z == NavigationAnchor.Z);
    float const waitReach = SpatialDistance(wait, MagmawCentre);
    assert(std::fabs(waitReach - (MeleeReach + 2.5f)) < 0.01f);
    float const rayX = NavigationAnchor.X - MagmawCentre.X;
    float const rayY = NavigationAnchor.Y - MagmawCentre.Y;
    float const along = ((wait.X - MagmawCentre.X) * rayX
        + (wait.Y - MagmawCentre.Y) * rayY) / std::hypot(rayX, rayY);
    assert(std::fabs(along - PlanarDistance(wait, MagmawCentre)) < 0.01f);

    // Anywhere a rider can stop (within the 1 yd arrival tolerance, at
    // floor heights seen there) is at least 1.5 yd outside the melee reach
    // and inside the click reach, and draws no further preposition.
    for (int step = 0; step < 16; ++step)
        for (float z : { 211.6f, 211.815f, 212.1f })
        {
            float const angle = float(step) * 3.14159265f / 8.0f;
            Vector3 stop{ wait.X + 0.99f * std::cos(angle),
                wait.Y + 0.99f * std::sin(angle), z };
            assert(SpatialDistance(stop, MagmawCentre) >= MeleeReach + 1.5f);
            assert(SpatialDistance(stop, MagmawCentre) <= ClickReach);
            Blackboard arrived = seized;
            Member(arrived, 30007).Position = stop;
            assert(!Find(PlanFor(arrived, 30007), "pincer_preposition"));
        }

    // A rider standing at the old 4 yd pincer point is sent out as well.
    Blackboard underMagmaw = seized;
    Member(underMagmaw, 30007).Position = { -305.69f, -34.08f, 211.815f };
    AdaptiveMagmawPlan const underPlan = PlanFor(underMagmaw, 30007);
    BotNativeAction::Candidate const* out = Find(underPlan,
        "pincer_preposition");
    assert(out && SpatialDistance(MoveTarget(*out), wait) < 0.001f);

    // Non-riders keep their own Mangle behaviour.
    for (uint32 guid : { 30001u, 30003u, 30004u, 30005u, 30010u })
        assert(!Find(PlanFor(seized, guid), "pincer_preposition"));

    // Line of sight: Magmaw's LOS point is his hit sphere, combat reach 15 yd
    // out on the same ray, so the sight line is a short run of open floor.
    // A live Scorch landed from 0.8 yd of the wait point (base-0891a99 kill
    // 3, 112.5 s, Mgwdpsb at -318.17, -43.23, 211.89).
    Vector3 const recordedCast{ -318.17f, -43.23f, 211.89f };
    assert(PlanarDistance(wait, recordedCast) < 1.0f);
    assert(waitReach - MagmawReach < 6.0f);

    // The window opens. From the wait point both riders click at once: they
    // are inside the executor's 3D click reach, so no walk is needed. The
    // approach toward the pincer runs only now, as a fallback; walking all
    // of it takes under 2.5 s of the 6 s window (Massive Crash aura 88253).
    Blackboard open = LiveBoard();
    Member(open, 30007).Position = wait;
    Member(open, 30008).Position = wait;
    OpenWindow(open);
    // The native timer still reports the running sequence (0) in the window;
    // the lead must not hold riders back from mounting.
    MangleTimer(open, 0, true);
    for (uint32 guid : { 30007u, 30008u })
    {
        AdaptiveMagmawPlan const plan = PlanFor(open, guid);
        assert(Find(plan, "mount_free_pincer"));
        BotNativeAction::Candidate const* approach = Find(plan,
            "pincer_approach");
        assert(approach);
        float const walk = PlanarDistance(wait, MoveTarget(*approach));
        assert(walk / RunSpeed < 2.5f);
        assert(!Find(plan, "pincer_preposition"));
    }
    assert(SpatialDistance(wait, MagmawCentre) <= ClickReach - 1.0f);

    // Seated on distinct pincers inside the window, the pair launches.
    Blackboard seated = open;
    Member(seated, 30007).VehicleGuid = seated.Summons[0].Guid;
    Member(seated, 30008).VehicleGuid = seated.Summons[1].Guid;
    for (uint32 guid : { 30007u, 30008u })
        assert(Find(PlanFor(seated, guid), "launch_native_hook"));

    // Before the seize: riders leave on Magmaw's native Mangle timer, 6 s
    // ahead, with no Mangle aura yet. One millisecond earlier nothing moves.
    Blackboard early = LiveBoard();
    MangleTimer(early, 6001);
    for (uint32 guid : { 30007u, 30008u })
        assert(!Find(PlanFor(early, guid), "pincer_preposition"));
    Blackboard lead = LiveBoard();
    MangleTimer(lead, 6000);
    // fid16-8586fdd's riders at their last sample before each seize
    // (kills 1-5, Fire B then Affliction): 7.7-20.8 yd from Magmaw.
    Vector3 const fid16Spots[] = {
        { -321.04f, -25.94f, 211.09f }, { -322.63f, -26.72f, 211.69f },
        { -312.52f, -32.81f, 211.41f }, { -317.23f, -29.24f, 211.25f },
        { -316.54f, -32.69f, 211.41f }, { -308.91f, -36.45f, 211.58f },
        { -309.45f, -28.53f, 210.12f } };
    for (Vector3 const& spot : fid16Spots)
    {
        Blackboard fid16 = lead;
        Member(fid16, 30007).Position = spot;
        AdaptiveMagmawPlan const plan = PlanFor(fid16, 30007);
        BotNativeAction::Candidate const* move = Find(plan,
            "pincer_preposition");
        assert(move && SpatialDistance(MoveTarget(*move), wait) < 0.001f);
    }
    for (uint32 guid : { 30007u, 30008u })
    {
        AdaptiveMagmawPlan const plan = PlanFor(lead, guid);
        BotNativeAction::Candidate const* move = Find(plan,
            "pincer_preposition");
        assert(move && SpatialDistance(MoveTarget(*move), wait) < 0.001f);
    }
    for (uint32 guid : { 30001u, 30003u, 30004u, 30005u, 30006u, 30009u,
             30010u })
        assert(!Find(PlanFor(lead, guid), "pincer_preposition"));
    // The published sequence (0) and a wrapped overdue value both mean due
    // now; no timer, or a boss out of combat, opens nothing.
    Blackboard sequence = LiveBoard();
    MangleTimer(sequence, 0, true);
    assert(Find(PlanFor(sequence, 30007), "pincer_preposition"));
    Blackboard overdue = LiveBoard();
    MangleTimer(overdue, 4294000000u);
    assert(Find(PlanFor(overdue, 30007), "pincer_preposition"));
    assert(!Find(PlanFor(LiveBoard(), 30007), "pincer_preposition"));
    Blackboard resetBoss = lead;
    resetBoss.Hostiles.front().InCombat = false;
    assert(!Find(PlanFor(resetBoss, 30007), "pincer_preposition"));
    // A rider already at the wait point stays put through the lead.
    Blackboard leadArrived = lead;
    Member(leadArrived, 30007).Position = wait;
    assert(!Find(PlanFor(leadArrived, 30007), "pincer_preposition"));

    // The seize tick. From every recorded start spot the rider reaches the
    // wait point inside the 6 s lead with at least 0.8 s to spare: fid16's
    // longest start latency (seize to first moving sample, 2.4 s) plus the
    // walk at run speed. So when Mangle lands it stands outside the reach.
    float const longestStartLatency = 2.44f;
    std::vector<Vector3> starts(std::begin(fid16Spots), std::end(fid16Spots));
    starts.push_back(LiveBoard().Players[6].Position);
    starts.push_back(LiveBoard().Players[7].Position);
    for (Vector3 const& start : starts)
    {
        float const arrive = longestStartLatency
            + PlanarDistance(start, wait) / RunSpeed;
        assert(arrive + 0.8f <= 6.0f);
    }
    Blackboard seizeTick = seized;
    MangleTimer(seizeTick, 0, true);
    for (uint32 guid : { 30007u, 30008u })
    {
        Member(seizeTick, guid).Position = wait;
        assert(SpatialDistance(Member(seizeTick, guid).Position, MagmawCentre)
            >= MeleeReach + 2.0f);
        assert(!Find(PlanFor(seizeTick, guid), "pincer_preposition"));
    }

    // Timing: the seize-to-window gap is 3.5 s (Prepare Massive Crash) +
    // 5 s (Massive Crash) + 1 s cast; the longest walk out to the wait point
    // from a recorded spot inside the reach takes far less.
    float const walkOut = std::max(PlanarDistance(LiveBoard().Players[6].Position,
        wait), PlanarDistance(LiveBoard().Players[7].Position, wait)) / RunSpeed;
    assert(walkOut < 3.5f);
}
''',
        encoding="utf-8",
    )
    _compile_and_run(source, binary)


@pytest.mark.skipif(not TDB_WORLD.exists(), reason="TDB world dump not present")
def test_magmaw_model_combat_reach_is_fifteen() -> None:
    # Magmaw (41570) uses display 32679 at scale 1; the wait radius assumes
    # that model's CombatReach of 15 yd.
    pattern = re.compile(rf"\({MAGMAW_DISPLAY_ID},([0-9.]+),([0-9.]+),")
    with TDB_WORLD.open(encoding="utf-8", errors="replace") as dump:
        for line in dump:
            if not line.startswith("INSERT INTO `creature_model_info`"):
                continue
            match = pattern.search(line)
            assert match, "display 32679 missing from creature_model_info"
            bounding_radius, combat_reach = map(float, match.groups())
            assert combat_reach == 15.0
            assert bounding_radius == 7.5
            return
    pytest.fail("creature_model_info insert not found")
