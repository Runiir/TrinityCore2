from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = ROOT / "src/server/game/Bots/BotActionExecutor.cpp"
UNIT = ROOT / "src/server/game/Entities/Unit/Unit.cpp"
SPLINE_POSITION = ROOT / "src/server/game/Entities/Unit/UnitSplinePosition.cpp"


def _function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : index]
    raise AssertionError(f"unterminated function: {signature}")


def test_face_uses_the_shared_native_callers() -> None:
    source = EXECUTOR.read_text(encoding="utf-8")
    execute_combat = _function_body(
        source, "BotActionResult BotActionExecutor::ExecuteCombat"
    )
    melee_auto_attack = _function_body(
        source, "BotActionResult BotActionExecutor::SubmitMeleeAutoAttack"
    )
    face = _function_body(source, "void BotActionExecutor::Face")

    assert execute_combat.count("Face(bot, target);") >= 1
    assert melee_auto_attack.count("Face(bot, target);") == 1
    assert "SetOrientationTowards(target);" in face
    assert "SetFacingToObject(target);" in face
    assert "!bot->movespline->Finalized()" in face
    assert "bot->isMoving()" in face
    assert "bot->HasUnitState(UNIT_STATE_MOVING)" in face


def test_production_face_branch_preserves_modeled_spline_identity(
    tmp_path: Path,
) -> None:
    face = _function_body(
        EXECUTOR.read_text(encoding="utf-8"), "void BotActionExecutor::Face"
    )
    source = tmp_path / "bot_combat_facing.cpp"
    binary = tmp_path / "bot_combat_facing"
    source.write_text(
        f'''
#include <cassert>
#include <cmath>
#include <cstdint>

constexpr std::uint32_t UNIT_STATE_MOVING = 1u;

struct NativeSpline
{{
    bool finalized = true;
    std::uint32_t id = 0;
    float destinationX = 0.0f;
    float destinationY = 0.0f;
    float destinationZ = 0.0f;
    int activeGenerator = 0;

    bool Finalized() const {{ return finalized; }}
}};

struct Unit
{{
    NativeSpline* movespline = nullptr;
    float x = 0.0f;
    float y = 0.0f;
    float orientation = 0.0f;
    bool movementFlags = false;
    std::uint32_t unitState = 0;
    unsigned orientationUpdates = 0;
    unsigned forcedFacingUpdates = 0;

    bool isMoving() const {{ return movementFlags; }}
    bool HasUnitState(std::uint32_t state) const {{ return (unitState & state) != 0; }}

    void SetOrientationTowards(Unit const* target)
    {{
        ++orientationUpdates;
        orientation = std::atan2(target->y - y, target->x - x);
    }}

    void SetFacingToObject(Unit const* target)
    {{
        ++forcedFacingUpdates;
        orientation = std::atan2(target->y - y, target->x - x);
        ++movespline->id;
        movespline->activeGenerator = 0;
        movespline->finalized = true;
    }}
}};

struct Player : Unit
{{
}};

class BotActionExecutor
{{
public:
    void Face(Player* bot, Unit* target);
}};

void BotActionExecutor::Face(Player* bot, Unit* target)
{{
{face}
}}

void ExecuteHostileAction(BotActionExecutor& executor, Player* bot, Unit* target)
{{
    executor.Face(bot, target);
}}

void SubmitMeleeAutoAttack(BotActionExecutor& executor, Player* bot, Unit* target)
{{
    executor.Face(bot, target);
}}

int main()
{{
    BotActionExecutor executor;
    Player bot;
    Unit target;
    target.x = 3.0f;
    target.y = 4.0f;

    // A hazard MovePoint has claimed this spline.  The same tick's hostile
    // instant action and melee auto-attack must both face through the shared
    // production branch without replacing the movement identity.
    NativeSpline hazard{{false, 13977, -308.522278f, -54.332466f, 212.402481f, 8}};
    bot.movespline = &hazard;
    bot.movementFlags = true;
    const std::uint32_t originalId = hazard.id;
    const float originalX = hazard.destinationX;
    const float originalY = hazard.destinationY;
    const float originalZ = hazard.destinationZ;
    const int originalGenerator = hazard.activeGenerator;

    ExecuteHostileAction(executor, &bot, &target);
    SubmitMeleeAutoAttack(executor, &bot, &target);
    assert(bot.orientationUpdates == 2);
    assert(bot.forcedFacingUpdates == 0);
    assert(bot.orientation > 0.9f && bot.orientation < 1.0f);
    assert(hazard.id == originalId);
    assert(hazard.destinationX == originalX);
    assert(hazard.destinationY == originalY);
    assert(hazard.destinationZ == originalZ);
    assert(hazard.activeGenerator == originalGenerator);
    assert(!hazard.Finalized());

    // A finalized spline does not by itself clear a stale movement flag.  It
    // remains in the immediate branch until the native movement state settles.
    hazard.finalized = true;
    bot.movementFlags = true;
    bot.unitState = 0;
    ExecuteHostileAction(executor, &bot, &target);
    assert(bot.orientationUpdates == 3);
    assert(bot.forcedFacingUpdates == 0);
    assert(hazard.id == originalId);

    // UNIT_STATE_MOVING is an independent native signal and must also retain
    // the current spline when the movement flags have already settled.
    bot.movementFlags = false;
    bot.unitState = UNIT_STATE_MOVING;
    SubmitMeleeAutoAttack(executor, &bot, &target);
    assert(bot.orientationUpdates == 4);
    assert(bot.forcedFacingUpdates == 0);
    assert(hazard.id == originalId);

    // Once every movement signal is idle, retain the core's normal facing
    // legality path.  Its forced-facing spline is expected here.
    bot.unitState = 0;
    SubmitMeleeAutoAttack(executor, &bot, &target);
    assert(bot.orientationUpdates == 4);
    assert(bot.forcedFacingUpdates == 1);
    assert(hazard.id == originalId + 1);

    // A non-finalized spline alone must preserve its identity even when both
    // movement flags are clear. Native vehicle/transport relocation is not
    // modeled by these stubs and remains a live verification boundary.
    NativeSpline flaglessSpline{{false, 42, 10.0f, 20.0f, 30.0f, 8}};
    bot.movespline = &flaglessSpline;
    bot.movementFlags = false;
    bot.unitState = 0;
    ExecuteHostileAction(executor, &bot, &target);
    assert(bot.orientationUpdates == 5);
    assert(bot.forcedFacingUpdates == 1);
    assert(flaglessSpline.id == 42);
    assert(flaglessSpline.activeGenerator == 8);
    assert(!flaglessSpline.Finalized());

    // A self target keeps the existing native zero-angle behavior while still
    // avoiding a spline replacement.
    ExecuteHostileAction(executor, &bot, &bot);
    assert(bot.orientationUpdates == 6);
    assert(bot.forcedFacingUpdates == 1);
    assert(bot.orientation == 0.0f);
    assert(flaglessSpline.id == 42);

    // Null bot/target calls remain no-ops and do not manufacture facing state.
    ExecuteHostileAction(executor, nullptr, &target);
    ExecuteHostileAction(executor, &bot, nullptr);
    assert(bot.orientationUpdates == 6);
    assert(bot.forcedFacingUpdates == 1);
    assert(flaglessSpline.id == 42);
    return 0;
}}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_production_spline_position_preserves_cast_facing_and_trajectory(
    tmp_path: Path,
) -> None:
    unit_source = UNIT.read_text(encoding="utf-8")
    spline_source = SPLINE_POSITION.read_text(encoding="utf-8")
    face_source = EXECUTOR.read_text(encoding="utf-8")
    update_spline_movement = _function_body(
        unit_source, "void Unit::UpdateSplineMovement"
    )
    update_spline_position = _function_body(
        spline_source, "void Unit::UpdateSplinePosition"
    )
    cast_facing_guard = _function_body(
        spline_source, "bool TryGetBotCastFacing(Unit const& caster"
    )
    face_body = _function_body(face_source, "void BotActionExecutor::Face")
    source = tmp_path / "bot_spline_facing.cpp"
    binary = tmp_path / "bot_spline_facing"
    source.write_text(
        r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <optional>
#include <vector>

using uint32 = std::uint32_t;
using int32 = std::int32_t;
template <class T> using Optional = std::optional<T>;

constexpr uint32 UNIT_FIELD_FLAGS_2 = 2;
constexpr uint32 UNIT_FLAG2_CANNOT_TURN = 4;
constexpr uint32 UNIT_STATE_CANNOT_TURN = 8;
constexpr uint32 UNIT_STATE_MOVING = 16;
constexpr uint32 CURRENT_GENERIC_SPELL = 0;

enum SpellState { SPELL_STATE_NULL = 0, SPELL_STATE_PREPARING = 1,
    SPELL_STATE_LAUNCHED = 2, SPELL_STATE_FINISHED = 4 };
enum SpellCastResult { SPELL_CAST_OK = 0, SPELL_FAILED_MOVING = 1 };
enum class SpellFacingCasterFlags : uint32 { None = 0, Infront = 1 };

struct FacingFlags
{
    bool Infront = false;
    bool HasFlag(SpellFacingCasterFlags flag) const
    {
        return Infront && flag == SpellFacingCasterFlags::Infront;
    }
};

struct ObjectGuid
{
    uint32 value = 0;
    explicit operator bool() const { return value != 0; }
    bool operator==(ObjectGuid const& other) const { return value == other.value; }
    bool operator!=(ObjectGuid const& other) const { return !(*this == other); }
};

struct Map {};

struct Position
{
    float m_positionX = 0.0f, m_positionY = 0.0f;
    float m_positionZ = 0.0f, m_orientation = 0.0f;
    Position() = default;
    Position(float x, float y, float z, float orientation)
        : m_positionX(x), m_positionY(y), m_positionZ(z),
          m_orientation(orientation) {}
    float GetPositionX() const { return m_positionX; }
    float GetPositionY() const { return m_positionY; }
    float GetPositionZ() const { return m_positionZ; }
    float GetOrientation() const { return m_orientation; }
    float GetAngle(float x, float y) const
    {
        float angle = std::atan2(y - m_positionY, x - m_positionX);
        return angle >= 0.0f ? angle : 6.28318530717958647692f + angle;
    }
    float GetAngle(Position const* other) const
    { return other ? GetAngle(other->GetPositionX(), other->GetPositionY()) : 0.0f; }
    void SetOrientation(float value) { m_orientation = value; }
    bool HasInArc(float arc, Position const* object, float border = 2.0f) const;
    static float NormalizeOrientation(float value)
    {
        constexpr float twoPi = 6.28318530717958647692f;
        while (value < 0.0f) value += twoPi;
        while (value >= twoPi) value -= twoPi;
        return value;
    }
};

namespace Movement
{
struct Location { float x = 0.0f, y = 0.0f, z = 0.0f, orientation = 0.0f; };
struct AnimTier {};
class MoveSpline
{
public:
    bool onTransport = false, finalized = false, disabled = false;
    uint32 tick = 0, timePassedValue = 0, duration = 3000;
    uint32 id = 3946, pathId = 3968, activeGenerator = 8;
    float destinationX = -311.0f, destinationY = -29.0f,
        destinationZ = 212.4f;
    std::vector<Location> samples;
    Location ComputePosition() const
    {
        return samples[std::min<std::size_t>(tick, samples.size() - 1)];
    }
    void updateState(uint32 diff)
    {
        timePassedValue += diff;
        if (tick + 1 < samples.size()) ++tick;
        if (tick + 1 >= samples.size()) finalized = true;
    }
    bool Finalized() const { return finalized; }
    Optional<AnimTier> GetAnimation() const { return {}; }
};
}
using AnimTier = Movement::AnimTier;

struct TransportBase
{
    void CalculatePassengerPosition(float&, float&, float&, float*) const {}
};
struct Vehicle {};
class WorldSession
{
public:
    bool botSession = true;
    bool IsBotSession() const { return botSession; }
};

class Unit;
class Player;
struct SpellInfo { FacingFlags FacingCasterFlags; };
struct SpellCastTargets
{
    ObjectGuid targetGuid;
    ObjectGuid GetUnitTargetGUID() const { return targetGuid; }
};
class Spell
{
public:
    SpellInfo info;
    SpellCastTargets m_targets;
    Unit* caster = nullptr;
    SpellState state = SPELL_STATE_PREPARING;
    int32 castTime = 1500;
    bool triggered = false;
    SpellCastResult movementResult = SPELL_CAST_OK;
    mutable uint32 movementChecks = 0;
    SpellInfo const* GetSpellInfo() const { return &info; }
    Unit* GetCaster() const { return caster; }
    SpellState getState() const { return state; }
    int32 GetCastTime() const { return castTime; }
    bool IsTriggered() const { return triggered; }
    SpellCastResult CheckMovement() const
    {
        ++movementChecks;
        return movementResult;
    }
};

struct MovementInfo { struct { Position pos; } transport; };
class Unit
{
public:
    Movement::MoveSpline* movespline = nullptr;
    MovementInfo m_movementInfo;
    Player const* player = nullptr;
    Spell* genericSpell = nullptr;
    ObjectGuid guid{1};
    Map* map = nullptr;
    TransportBase* transport = nullptr;
    Vehicle* vehicle = nullptr;
    uint32 unitState = 0, flags2 = 0;
    bool alive = true, inWorld = true, attackable = true;
    bool movementFlags = false;
    float x = 0.0f, y = 0.0f, z = 0.0f, orientation = 0.0f;
    float updatedX = 0.0f, updatedY = 0.0f, updatedZ = 0.0f;
    float updatedOrientation = 0.0f;
    uint32 updates = 0, disabledSplines = 0;
    uint32 orientationUpdates = 0, forcedFacingUpdates = 0;
    Player const* ToPlayer() const;
    bool IsAlive() const { return alive; }
    bool IsInWorld() const { return inWorld; }
    TransportBase* GetTransport() const { return transport; }
    Vehicle* GetVehicle() const { return vehicle; }
    bool HasUnitState(uint32 state) const { return (unitState & state) != 0; }
    bool HasFlag(uint32, uint32 flag) const { return (flags2 & flag) != 0; }
    Spell* GetCurrentSpell(uint32) const { return genericSpell; }
    ObjectGuid GetGUID() const { return guid; }
    Map* GetMap() const { return map; }
    float GetPositionX() const { return x; }
    float GetPositionY() const { return y; }
    float GetOrientation() const { return orientation; }
    bool IsValidAttackTarget(Unit const* target, SpellInfo const*) const
    { return target && attackable; }
    bool isMoving() const { return movementFlags; }
    TransportBase* GetDirectTransport() const { return transport; }
    void DisableSpline() { ++disabledSplines; }
    void SetAnimTier(AnimTier const&) {}
    void SetOrientationTowards(Unit const* target)
    {
        ++orientationUpdates;
        orientation = Position::NormalizeOrientation(std::atan2(
            target->GetPositionY() - y, target->GetPositionX() - x));
    }
    void SetFacingToObject(Unit const*)
    {
        ++forcedFacingUpdates;
        ++movespline->id;
        movespline->pathId = movespline->id;
        movespline->finalized = true;
    }
    Position CurrentPosition() const
    { return Position(x, y, z, orientation); }
    void UpdatePosition(float newX, float newY, float newZ, float newOrientation)
    {
        updatedX = x = newX; updatedY = y = newY; updatedZ = z = newZ;
        updatedOrientation = orientation = newOrientation; ++updates;
    }
    void UpdateSplineMovement(uint32 t_diff);
    void UpdateSplinePosition();
};
class Player : public Unit
{
public:
    WorldSession session;
    Player() { player = this; }
    WorldSession* GetSession() const
    { return const_cast<WorldSession*>(&session); }
};
Player const* Unit::ToPlayer() const { return player; }

namespace ObjectAccessor
{
Unit* target = nullptr;
Unit* GetUnit(Unit const&, ObjectGuid const& guid)
{ return target && target->GetGUID() == guid ? target : nullptr; }
}

'''
        + "bool Position::HasInArc(float arc, const Position* obj, float border) const\n{"
        + _function_body(
            (ROOT / "src/server/game/Entities/Object/Position.cpp").read_text(
                encoding="utf-8"
            ),
            "bool Position::HasInArc",
        )
        + "}\n\n"
        + "bool TryGetBotCastFacing(Unit const& caster, Movement::Location const& loc,\n"
        + "    float& orientation)\n{"
        + cast_facing_guard
        + "}\n\n"
        + "void Unit::UpdateSplineMovement(uint32 t_diff)\n{"
        + update_spline_movement
        + "}\n\n"
        + "void Unit::UpdateSplinePosition()\n{"
        + update_spline_position
        + "}\n\n"
        + "class BotActionExecutor { public: void Face(Player* bot, Unit* target); };\n"
        + "void BotActionExecutor::Face(Player* bot, Unit* target)\n{"
        + face_body
        + "}\n\n"
        + r'''
int main()
{
    Map map;
    Player bot;
    Unit target;
    target.guid.value = 41570;
    bot.map = &map; target.map = &map;
    target.x = -302.467f; target.y = -31.7101f;
    ObjectAccessor::target = &target;

    Spell movingCast;
    movingCast.caster = &bot;
    movingCast.m_targets.targetGuid = target.guid;
    movingCast.info.FacingCasterFlags.Infront = true;
    bot.genericSpell = &movingCast;

    Movement::MoveSpline spline;
    spline.samples = {
        { -314.137f, -32.481f, 212.402f, 2.03f },
        { -314.481f, -31.784f, 212.402f, 2.03f },
        { -313.920f, -30.920f, 212.402f, 2.03f },
        { -311.000f, -29.000f, 212.402f, 2.03f },
    };
    Movement::MoveSpline control = spline;
    bot.movespline = &spline;
    bot.x = spline.samples.front().x;
    bot.y = spline.samples.front().y;
    bot.z = spline.samples.front().z;
    target.z = 210.948f;
    Position targetPosition(target.x, target.y, target.z, 0.0f);
    Position baselinePosition(spline.samples.front().x,
        spline.samples.front().y, spline.samples.front().z,
        spline.samples.front().orientation);
    assert(!baselinePosition.HasInArc(float(M_PI), &targetPosition));

    // Execute the production facing caller before movement commits. It must
    // retain the active owner spline; UpdateSplinePosition supplies the
    // target bearing for the position that the spline actually computes.
    BotActionExecutor executor;
    bot.movementFlags = true;
    bot.unitState = UNIT_STATE_MOVING;
    uint32 originalSplineId = spline.id;
    executor.Face(&bot, &target);
    assert(bot.orientationUpdates == 1 && bot.forcedFacingUpdates == 0);
    assert(spline.id == originalSplineId && !spline.Finalized());
    bot.movementFlags = false;
    bot.unitState = 0;

    for (uint32 diff : { 1000u, 1000u, 1000u })
    {
        bot.UpdateSplineMovement(diff);
        control.updateState(diff);
        Movement::Location expected = control.ComputePosition();
        assert(bot.updatedX == expected.x && bot.updatedY == expected.y);
        assert(bot.updatedZ == expected.z);
        assert(spline.id == control.id && spline.pathId == control.pathId);
        assert(spline.destinationX == control.destinationX);
        assert(spline.destinationY == control.destinationY);
        assert(spline.destinationZ == control.destinationZ);
        assert(spline.duration == control.duration);
        assert(spline.timePassedValue == control.timePassedValue);
        assert(spline.activeGenerator == control.activeGenerator);
        Position committed(bot.updatedX, bot.updatedY, bot.updatedZ,
            bot.updatedOrientation);
        assert(committed.HasInArc(float(M_PI), &targetPosition));
    }
    assert(spline.Finalized() && bot.disabledSplines == 1);
    assert(movingCast.movementChecks == 3);

    // Completion stops correction on the next position commit.
    movingCast.state = SPELL_STATE_FINISHED;
    bot.UpdateSplinePosition();
    assert(bot.updatedOrientation == spline.samples.back().orientation);

    auto reset = [&]()
    {
        spline.finalized = true; spline.tick = 0; spline.onTransport = false;
        bot.transport = nullptr; bot.vehicle = nullptr; bot.unitState = 0;
        bot.flags2 = 0; bot.alive = true; bot.inWorld = true;
        bot.attackable = true; bot.session.botSession = true;
        bot.orientationUpdates = 0; bot.forcedFacingUpdates = 0;
        bot.x = spline.samples.front().x; bot.y = spline.samples.front().y;
        bot.z = spline.samples.front().z;
        bot.orientation = spline.samples.front().orientation;
        bot.genericSpell = &movingCast; movingCast.caster = &bot;
        movingCast.state = SPELL_STATE_PREPARING; movingCast.castTime = 1500;
        movingCast.triggered = false; movingCast.info.FacingCasterFlags.Infront = true;
        movingCast.movementResult = SPELL_CAST_OK;
        movingCast.m_targets.targetGuid = target.guid;
        target.map = &map; target.alive = true; target.inWorld = true;
        ObjectAccessor::target = &target;
    };
    auto assertNativeTangent = [&]()
    {
        bot.UpdateSplinePosition();
        assert(bot.updatedOrientation == spline.samples.front().orientation);
    };

    reset(); bot.session.botSession = false; assertNativeTangent();
    reset(); bot.genericSpell = nullptr; assertNativeTangent();
    reset(); movingCast.state = SPELL_STATE_LAUNCHED; assertNativeTangent();
    reset(); Spell replacement = movingCast; replacement.caster = nullptr;
    bot.genericSpell = &replacement; assertNativeTangent();
    reset(); movingCast.movementResult = SPELL_FAILED_MOVING; assertNativeTangent();

    reset(); bot.unitState = UNIT_STATE_CANNOT_TURN; bot.orientation = 1.234f;
    bot.UpdateSplinePosition(); assert(bot.updatedOrientation == 1.234f);
    reset(); bot.flags2 = UNIT_FLAG2_CANNOT_TURN; assertNativeTangent();
    TransportBase transport; reset(); bot.transport = &transport;
    spline.onTransport = true; assertNativeTangent(); spline.onTransport = false;
    Vehicle vehicle; reset(); bot.vehicle = &vehicle; assertNativeTangent();

    reset(); bot.alive = false; assertNativeTangent();
    reset(); bot.inWorld = false; assertNativeTangent();
    reset(); ObjectAccessor::target = nullptr; assertNativeTangent();
    reset(); target.alive = false; assertNativeTangent();
    Map foreignMap; reset(); target.map = &foreignMap; assertNativeTangent();
    reset(); ObjectAccessor::target = &bot; movingCast.m_targets.targetGuid = bot.guid;
    assertNativeTangent();
    reset(); bot.attackable = false; assertNativeTangent();

    // Owner launch itself is represented by a bounded deterministic native
    // spline input. The same preparing cast must follow this replacement
    // through the production movement consumer without mutating its identity.
    reset();
    Movement::MoveSpline ownerReplacement;
    ownerReplacement.id = 3968;
    ownerReplacement.pathId = 3968;
    ownerReplacement.destinationX = -300.0f;
    ownerReplacement.destinationY = -31.0f;
    ownerReplacement.destinationZ = 212.402f;
    ownerReplacement.activeGenerator = 9;
    ownerReplacement.samples = {
        { -314.137f, -32.481f, 212.402f, 2.03f },
        { -314.481f, -31.784f, 212.402f, 2.03f },
        { -313.920f, -30.920f, 212.402f, 2.03f },
        { -300.000f, -31.000f, 212.402f, 2.03f },
    };
    Movement::MoveSpline ownerControl = ownerReplacement;
    bot.movespline = &ownerReplacement;
    for (uint32 diff : { 1000u, 1000u, 1000u })
    {
        bot.UpdateSplineMovement(diff);
        ownerControl.updateState(diff);
        Movement::Location expected = ownerControl.ComputePosition();
        assert(bot.updatedX == expected.x && bot.updatedY == expected.y);
        assert(bot.updatedZ == expected.z);
        assert(ownerReplacement.id == ownerControl.id);
        assert(ownerReplacement.pathId == ownerControl.pathId);
        assert(ownerReplacement.destinationX == ownerControl.destinationX);
        assert(ownerReplacement.destinationY == ownerControl.destinationY);
        assert(ownerReplacement.destinationZ == ownerControl.destinationZ);
        assert(ownerReplacement.duration == ownerControl.duration);
        assert(ownerReplacement.timePassedValue == ownerControl.timePassedValue);
        assert(ownerReplacement.activeGenerator == ownerControl.activeGenerator);
        Position committed(bot.updatedX, bot.updatedY, bot.updatedZ,
            bot.updatedOrientation);
        assert(committed.HasInArc(float(M_PI), &targetPosition));
    }
    assert(ownerReplacement.Finalized());
    assert(ownerReplacement.id == 3968 && ownerReplacement.pathId == 3968);
    return 0;
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         str(source), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)
