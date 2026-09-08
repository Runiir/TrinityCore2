from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = ROOT / "src/server/game/Bots/BotActionExecutor.cpp"


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
