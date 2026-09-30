"""A refused native fall leaves no falling state and no stale movement generator.

Round-3 v4 review (P2, packet movement_v4): MotionMaster::MoveFall and the
executor's LaunchFallOnto set MOVEMENTFLAG_FALLING and reset the fall time
before the falling spline is launched, and MoveSplineInit::Launch then
refuses a passenger's fall whose body meets its transport model
(ProvePassengerEffectSpline). StopMoving clears neither the flag nor the fall
time and the GenericMovementGenerator of the refused launch only expires at
the next update with no cleanup, so the bot stood motionless with FALLING set:
the swim and walk code saw it airborne and a landing was owed for a fall that
never started.

Now both launches capture the falling state first and, when they started no
fall spline, roll it back (Bots/BotFallAdmission.h): the flag and the fall
time as they were (a fall continued after a landing without floor keeps its
flag and time) and the stale effect generator gone.

The transaction runs here with the REAL Movement::MoveSpline and the real
BotValidationRouteNativeFall predicates; the bot and its motion master are
stand-ins that mirror MotionMaster::MoveFall's order of effects, which the
source checks below pin against MotionMaster.cpp and MoveSplineInit.cpp.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from tests.test_bot_native_fall_spline_state import STUB_CREATURE, STUB_LOG


ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "src/server/game"
BOTS = GAME / "Bots"
ADMISSION = BOTS / "BotFallAdmission.h"
EXECUTOR = BOTS / "BotWorldPopulationMgrNativePathTransportSurface.cpp"
MOTION_MASTER = GAME / "Movement/MotionMaster.cpp"
LAUNCH = GAME / "Movement/Spline/MoveSplineInit.cpp"

PROGRAM = r'''
#include "Bots/BotFallAdmission.h"
#include "Bots/BotValidationRouteNativeFallSpline.h"
#include "Errors.h"
#include <G3D/Matrix4.h>
#include <G3D/Vector4.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <memory>

namespace Trinity
{
void Assert(char const*, int, char const*, char const*) { std::abort(); }
void Assert(char const*, int, char const*, char const*, char const*, ...) { std::abort(); }
void Abort(char const*, int, char const*) { std::abort(); }
void Abort(char const*, int, char const*, char const*, ...) { std::abort(); }
}
G3D::Matrix4::Matrix4(float, float, float, float, float, float, float, float,
    float, float, float, float, float, float, float, float) { }
G3D::Vector4 G3D::Vector4::operator*(const G3D::Matrix4&) const { return G3D::Vector4(); }

namespace Fall = BotValidationRouteNativeFall;
static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL %d %s\n", __LINE__, #c); ++failures; } } while (0)

// The enumerators of the real headers (UnitDefines.h, MotionMaster.h).
enum MovementSlot : std::uint8_t { MOTION_SLOT_IDLE = 0, MOTION_SLOT_ACTIVE, MOTION_SLOT_CONTROLLED, MAX_MOTION_SLOT };
enum MovementGeneratorType : std::uint8_t { POINT_MOTION_TYPE = 8, EFFECT_MOTION_TYPE = 16, MAX_MOTION_TYPE = 19 };
constexpr std::uint32_t MOVEMENTFLAG_FALLING = 0x00000800;

struct Traits
{
    static constexpr std::uint32_t Falling = MOVEMENTFLAG_FALLING;
    static constexpr MovementSlot Controlled = MOTION_SLOT_CONTROLLED;
    static constexpr MovementGeneratorType Effect = EFFECT_MOTION_TYPE;
};

struct MotionMaster
{
    MovementGeneratorType Slot[MAX_MOTION_SLOT] = { MAX_MOTION_TYPE, MAX_MOTION_TYPE, MAX_MOTION_TYPE };
    int Clears = 0;
    MovementGeneratorType GetMotionSlotType(MovementSlot slot) const { return Slot[slot]; }
    void Clear(MovementSlot slot) { Slot[slot] = MAX_MOTION_TYPE; ++Clears; }
    void Mutate(MovementSlot slot, MovementGeneratorType type) { Slot[slot] = type; }
};

struct MovementInfo
{
    std::uint32_t Fall = 0;
    std::uint32_t GetFallTime() const { return Fall; }
    void SetFallTime(std::uint32_t time) { Fall = time; }
};

struct Bot
{
    std::uint32_t Flags = 0;
    MovementInfo m_movementInfo;
    std::unique_ptr<Movement::MoveSpline> movespline = std::make_unique<Movement::MoveSpline>();
    MotionMaster Motion;
    bool HasUnitMovementFlag(std::uint32_t flag) const { return (Flags & flag) != 0; }
    void AddUnitMovementFlag(std::uint32_t flag) { Flags |= flag; }
    void RemoveUnitMovementFlag(std::uint32_t flag) { Flags &= ~flag; }
    MotionMaster* GetMotionMaster() { return &Motion; }
};

static void StartFallSpline(Bot& bot)
{
    Movement::MoveSplineInitArgs fall;
    fall.path.push_back(G3D::Vector3(-14.0f, -32.0f, 9.3f));
    fall.path.push_back(G3D::Vector3(-14.0f, -32.0f, 1.44f));
    fall.velocity = 7.0f;
    fall.flags.Falling = true;
    bot.movespline->Initialize(fall);
}

// MotionMaster::MoveFall and LaunchFallOnto, in their order of effects: the
// falling flag and the fall time first, then the generator (Mutate), which
// launches the spline, and MoveSplineInit::Launch may emit nothing (a refused
// passenger fall: StopMoving, no spline, no state touched). `declined`: MoveFall
// returns before changing anything (ground near, root, stun).
enum class Launch { Accepted, Refused, Declined };

static void LaunchFall(Bot& bot, Launch launch)
{
    if (launch == Launch::Declined)
        return;
    bot.AddUnitMovementFlag(MOVEMENTFLAG_FALLING);
    bot.m_movementInfo.SetFallTime(0);
    bot.Motion.Mutate(MOTION_SLOT_CONTROLLED, EFFECT_MOTION_TYPE);
    if (launch == Launch::Accepted)
        StartFallSpline(bot);
}

// The executor's LaunchNativeFall / LaunchFallOnto: the launch is a success
// only with a running fall spline and its generator in the controlled slot.
static bool Attempt(Bot& bot, Launch launch, bool transactional)
{
    BotFallAdmission::Saved const before = BotFallAdmission::Capture<Traits>(bot);
    LaunchFall(bot, launch);
    if (Fall::SplineActive(*bot.movespline)
        && bot.GetMotionMaster()->GetMotionSlotType(MOTION_SLOT_CONTROLLED) == EFFECT_MOTION_TYPE)
        return true;
    if (transactional)
        BotFallAdmission::RollBack<Traits>(bot, before);
    return false;
}

// The state the swim and walk code and the landing step read.
static bool Airborne(Bot const& bot) { return bot.HasUnitMovementFlag(MOVEMENTFLAG_FALLING) || Fall::SplineActive(*bot.movespline); }

int main()
{
    // 1. The bug: an untransactional refused fall leaves FALLING set, the fall
    // time reset and the launch's generator in the slot, with no spline.
    {
        Bot bot;
        bot.m_movementInfo.SetFallTime(777);
        CHECK(!Attempt(bot, Launch::Refused, false));
        std::printf("untransactional flag=%d time=%u slot=%d spline=%d airborne=%d\n", bot.HasUnitMovementFlag(MOVEMENTFLAG_FALLING),
            bot.m_movementInfo.GetFallTime(), int(bot.Motion.Slot[MOTION_SLOT_CONTROLLED]),
            Fall::SplineActive(*bot.movespline), Airborne(bot));
        CHECK(bot.HasUnitMovementFlag(MOVEMENTFLAG_FALLING) && bot.m_movementInfo.GetFallTime() == 0);
        CHECK(bot.Motion.Slot[MOTION_SLOT_CONTROLLED] == EFFECT_MOTION_TYPE && Airborne(bot));
    }
    // 2. A refused fall from standing: no flag, the old fall time, no
    // generator, nothing airborne.
    {
        Bot bot;
        bot.m_movementInfo.SetFallTime(777);
        CHECK(!Attempt(bot, Launch::Refused, true));
        std::printf("refused flag=%d time=%u slot=%d spline=%d airborne=%d clears=%d\n", bot.HasUnitMovementFlag(MOVEMENTFLAG_FALLING),
            bot.m_movementInfo.GetFallTime(), int(bot.Motion.Slot[MOTION_SLOT_CONTROLLED]),
            Fall::SplineActive(*bot.movespline), Airborne(bot), bot.Motion.Clears);
        CHECK(!bot.HasUnitMovementFlag(MOVEMENTFLAG_FALLING) && bot.m_movementInfo.GetFallTime() == 777);
        CHECK(bot.Motion.Slot[MOTION_SLOT_CONTROLLED] == MAX_MOTION_TYPE && !Airborne(bot));
        // Another unrelated flag is untouched.
        Bot other;
        other.Flags = 0x1 | 0x4000;
        CHECK(!Attempt(other, Launch::Refused, true));
        CHECK(other.Flags == (0x1 | 0x4000));
    }
    // 3. A fall continued after a landing without floor keeps its flag and
    // fall time when the continuation is refused: the landing is still owed.
    {
        Bot bot;
        bot.AddUnitMovementFlag(MOVEMENTFLAG_FALLING);
        bot.m_movementInfo.SetFallTime(1234);
        bot.Motion.Mutate(MOTION_SLOT_CONTROLLED, EFFECT_MOTION_TYPE);   // the finished fall's generator
        CHECK(!Attempt(bot, Launch::Refused, true));
        std::printf("refall flag=%d time=%u slot=%d clears=%d\n", bot.HasUnitMovementFlag(MOVEMENTFLAG_FALLING),
            bot.m_movementInfo.GetFallTime(), int(bot.Motion.Slot[MOTION_SLOT_CONTROLLED]), bot.Motion.Clears);
        CHECK(bot.HasUnitMovementFlag(MOVEMENTFLAG_FALLING) && bot.m_movementInfo.GetFallTime() == 1234);
        CHECK(bot.Motion.Slot[MOTION_SLOT_CONTROLLED] == MAX_MOTION_TYPE);
    }
    // 4. An accepted fall is what it was: flag, reset fall time, generator
    // and spline stay, nothing is cleared.
    {
        Bot bot;
        bot.m_movementInfo.SetFallTime(777);
        CHECK(Attempt(bot, Launch::Accepted, true));
        std::printf("accepted flag=%d time=%u slot=%d spline=%d clears=%d\n", bot.HasUnitMovementFlag(MOVEMENTFLAG_FALLING),
            bot.m_movementInfo.GetFallTime(), int(bot.Motion.Slot[MOTION_SLOT_CONTROLLED]),
            Fall::SplineActive(*bot.movespline), bot.Motion.Clears);
        CHECK(bot.HasUnitMovementFlag(MOVEMENTFLAG_FALLING) && bot.m_movementInfo.GetFallTime() == 0);
        CHECK(bot.Motion.Slot[MOTION_SLOT_CONTROLLED] == EFFECT_MOTION_TYPE && Fall::SplineActive(*bot.movespline));
        CHECK(bot.Motion.Clears == 0);
    }
    // 5. A launch MoveFall declined changed nothing and rolls back nothing: a
    // generator of another type in the controlled slot stays, and so does the
    // generator of a spline that is still running.
    {
        Bot bot;
        bot.Motion.Mutate(MOTION_SLOT_CONTROLLED, POINT_MOTION_TYPE);
        bot.m_movementInfo.SetFallTime(55);
        CHECK(!Attempt(bot, Launch::Declined, true));
        CHECK(bot.Motion.Slot[MOTION_SLOT_CONTROLLED] == POINT_MOTION_TYPE && bot.Motion.Clears == 0);
        CHECK(!bot.HasUnitMovementFlag(MOVEMENTFLAG_FALLING) && bot.m_movementInfo.GetFallTime() == 55);
        Bot moving;
        StartFallSpline(moving);
        moving.AddUnitMovementFlag(MOVEMENTFLAG_FALLING);
        moving.Motion.Mutate(MOTION_SLOT_CONTROLLED, EFFECT_MOTION_TYPE);
        BotFallAdmission::Saved const before = BotFallAdmission::Capture<Traits>(moving);
        BotFallAdmission::RollBack<Traits>(moving, before);
        CHECK(moving.Motion.Slot[MOTION_SLOT_CONTROLLED] == EFFECT_MOTION_TYPE && moving.Motion.Clears == 0);
        CHECK(Fall::SplineActive(*moving.movespline) && moving.HasUnitMovementFlag(MOVEMENTFLAG_FALLING));
    }
    std::printf("failures=%d\n", failures);
    return failures ? 1 : 0;
}
'''


def _compile_and_run(tmp_path: Path, program: str = PROGRAM) -> str:
    stub = tmp_path / "stub"
    stub.mkdir(exist_ok=True)
    (stub / "Log.h").write_text(STUB_LOG)
    (stub / "Creature.h").write_text(STUB_CREATURE)
    source = tmp_path / "program.cpp"
    source.write_text(program)
    binary = tmp_path / "program"
    includes = [stub, GAME, GAME / "Movement/Spline", GAME / "Entities/Object",
                GAME / "Entities/Object/Updates", ROOT / "src/common", ROOT / "src/common/Utilities",
                ROOT / "src/common/Debugging", ROOT / "src/common/Logging",
                ROOT / "dep/g3dlite/include", ROOT / "dep/fmt/include"]
    command = ["g++", "-std=c++20", "-O1", "-Wall", "-Wextra", "-ffunction-sections", "-fdata-sections"]
    for include in includes:
        command += ["-I", str(include)]
    command += [str(source)] + [str(GAME / "Movement/Spline" / name)
                                for name in ("MoveSpline.cpp", "Spline.cpp", "MovementUtil.cpp")]
    subprocess.run(command + ["-Wl,--gc-sections", "-o", str(binary)], check=True, cwd=ROOT)
    run = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    return run.stdout


def test_a_refused_fall_leaves_no_falling_state_and_no_stale_generator(tmp_path: Path) -> None:
    out = _compile_and_run(tmp_path)
    # The bug, untransactional: airborne flag, reset time, generator, no spline.
    assert re.search(r"untransactional flag=1 time=0 slot=16 spline=0 airborne=1", out), out
    # A refused fall from standing: nothing left; the old fall time is back.
    assert re.search(r"refused flag=0 time=777 slot=19 spline=0 airborne=0 clears=1", out), out
    # A refused continuation of a fall still owes its landing: flag and time stay.
    assert re.search(r"refall flag=1 time=1234 slot=19 clears=1", out), out
    # An accepted fall is untouched by the transaction.
    assert re.search(r"accepted flag=1 time=0 slot=16 spline=1 clears=0", out), out
    assert "failures=0" in out, out


def _code(path: Path) -> str:
    text = re.sub(r"//[^\n]*", "", path.read_text(encoding="utf-8"))
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_the_model_mirrors_the_real_launch_order_and_the_launch_leaves_the_flags_alone() -> None:
    # MoveFall sets the flag and the fall time before it mutates the generator
    # (whose Initialize launches the spline).
    motion = _code(MOTION_MASTER)
    fall = motion[motion.index("void MotionMaster::MoveFall("):]
    fall = fall[:fall.index("\n}\n")]
    order = [fall.index("_owner->AddUnitMovementFlag(MOVEMENTFLAG_FALLING);"),
             fall.index("_owner->m_movementInfo.SetFallTime(0);"),
             fall.index("Mutate(new GenericMovementGenerator(std::move(init), EFFECT_MOTION_TYPE, id), MOTION_SLOT_CONTROLLED);")]
    assert order == sorted(order)
    # The generator launches in Initialize and expires with no state cleanup.
    generic = _code(GAME / "Movement/MovementGenerators/GenericMovementGenerator.cpp")
    assert "_duration.Reset(_splineInit.Launch());" in generic
    finalize = generic[generic.index("void GenericMovementGenerator::Finalize("):generic.index("void GenericMovementGenerator::MovementInform(")]
    assert "MOVEMENTFLAG_FALLING" not in finalize and "SetFall" not in finalize
    # A refused launch (MoveSplineInit::Launch) stops and records the failure;
    # it does not touch the falling state, which is the caller's to roll back.
    launch = _code(LAUNCH)
    body = launch[launch.index("int32 MoveSplineInit::Launch()"):launch.index("void MoveSplineInit::Stop()")]
    refused = body[body.index("if (transport && ProvePassengerEffectSpline(unit, args) == PassengerClip::Refused)"):]
    refused = refused[:refused.index("return 0;")]
    assert "unit->StopMoving();" in refused and "recordLaunch(false);" in refused
    assert "MOVEMENTFLAG_FALLING" not in refused and "SetFall" not in refused


def test_both_fall_launches_capture_first_and_roll_back_a_launch_that_started_no_spline() -> None:
    code = _code(EXECUTOR)
    native = code[code.index("Outcome LaunchNativeFall("):code.index("Outcome LaunchFallOnto(")]
    order = [native.index("BotFallAdmission::Capture<NativeFallTraits>(*bot);"),
             native.index("bot->GetMotionMaster()->MoveFall();"),
             native.index("return fallingOn ? Outcome::Progressed"),
             native.index("BotFallAdmission::RollBack<NativeFallTraits>(*bot, before);"),
             native.index("native_ledge_drop_fall_held_by_root"),
             native.index("native_ledge_drop_fall_not_launched")]
    assert order == sorted(order)
    onto = code[code.index("Outcome LaunchFallOnto("):code.index("Outcome ExecuteFall(")]
    order = [onto.index("native_ledge_drop_fall_held_by_root"),
             onto.index("BotFallAdmission::Capture<NativeFallTraits>(*bot);"),
             onto.index("bot->AddUnitMovementFlag(MOVEMENTFLAG_FALLING);"),
             onto.index("bot->m_movementInfo.SetFallTime(0);"),
             onto.index("LaunchMoveSpline(std::move(init), 0, MOTION_SLOT_CONTROLLED,"),
             onto.index("return Outcome::Submitted(\"native_ledge_drop_fall_submitted\");"),
             onto.index("BotFallAdmission::RollBack<NativeFallTraits>(*bot, before);"),
             onto.index("native_ledge_drop_fall_not_launched")]
    assert order == sorted(order)
    # These are the only two places the executor starts a fall; the traits name
    # the real enumerators.
    assert code.count("AddUnitMovementFlag(MOVEMENTFLAG_FALLING)") == 1 and code.count("MoveFall()") == 1
    assert code.count("BotFallAdmission::Capture<") == 2 and code.count("BotFallAdmission::RollBack<") == 2
    traits = code[code.index("struct NativeFallTraits"):]
    traits = traits[:traits.index("};")]
    for needle in ("uint32 Falling = MOVEMENTFLAG_FALLING;", "MovementSlot Controlled = MOTION_SLOT_CONTROLLED;",
                   "MovementGeneratorType Effect = EFFECT_MOTION_TYPE;"):
        assert needle in traits, needle
    header = ADMISSION.read_text(encoding="utf-8")
    assert re.findall(r'#include [<"]([^>"]+)[>"]', header) == ["cstdint"]
    for path in (ADMISSION, EXECUTOR):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000
