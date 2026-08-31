from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotNativeActionIntent.h"
EXECUTOR = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativeAction.cpp"


def _visitor_branch(source: str) -> str:
    start = source.index(
        "else if constexpr (std::is_same_v<T,\n"
        "            BotNativeAction::DirectionalMobility>)"
    )
    end = source.index(
        "else if constexpr (std::is_same_v<T, BotNativeAction::NativeDescent>)",
        start,
    )
    return source[start:end]


def test_directional_mobility_facing_and_resources_compile(tmp_path: Path) -> None:
    source = tmp_path / "directional_mobility.cpp"
    binary = tmp_path / "directional_mobility"
    source.write_text(
        r'''
#include "Bots/BotNativeActionIntent.h"
#include <cassert>
#include <cmath>

namespace
{
bool Near(float left, float right)
{
    return std::fabs(left - right) < 0.0001f;
}
}

int main()
{
    using namespace BotActionArbitration;
    using namespace BotNativeAction;
    constexpr float Pi = 3.14159265358979323846f;

    DirectionalMobility forward{ 8.0f, 11.0f, 0.0f, 1953,
        DirectionalMobilityFacing::Forward, "bait_escape" };
    Intent forwardIntent = forward;
    assert(RequiredResources(forwardIntent)
        == Uses(Resource::Movement, Resource::GlobalCooldown, Resource::Cast));
    assert(Near(DirectionalMobilityFacingAngle(5.0f, 7.0f, forward),
        std::atan2(4.0f, 3.0f)));

    DirectionalMobility backward = forward;
    backward.Facing = DirectionalMobilityFacing::Backward;
    float expectedBackward = std::fmod(std::atan2(4.0f, 3.0f) + Pi,
        2.0f * Pi);
    assert(Near(DirectionalMobilityFacingAngle(5.0f, 7.0f, backward),
        expectedBackward));

    forward.X = 4.0f;
    forward.Y = 7.0f;
    assert(Near(DirectionalMobilityFacingAngle(5.0f, 7.0f, forward), Pi));
    backward = forward;
    backward.Facing = DirectionalMobilityFacing::Backward;
    assert(Near(DirectionalMobilityFacingAngle(5.0f, 7.0f, backward), 0.0f));
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "src/common/Utilities"),
            "-I",
            str(ROOT / "src/common/Logging"),
            "-I",
            str(ROOT / "src/common/Debugging"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_native_executor_faces_then_uses_an_ordinary_self_cast() -> None:
    branch = _visitor_branch(EXECUTOR.read_text(encoding="utf-8"))

    assert "std::isfinite(action.X)" in branch
    assert "std::isfinite(action.Y)" in branch
    assert "bot->HasSpell(spellId)" in branch
    assert "sSpellMgr->GetSpellInfo(spellId)" in branch
    assert "spellInfo->IsPassive()" in branch
    assert "BotNativeAction::DirectionalMobilityFacingAngle(" in branch
    assert "bot->SetFacingTo(facing);" in branch
    assert "bot->CastSpell(bot, spellId, false)" in branch
    assert "native_directional_mobility_cast_rejected_result_" in branch
    assert branch.count("BotActionArbitration::Outcome::Retryable") == 5
    assert branch.index("bot->SetFacingTo(facing);") < branch.index(
        "bot->CastSpell(bot, spellId, false)"
    )


def test_native_executor_does_not_manufacture_directional_travel() -> None:
    branch = _visitor_branch(EXECUTOR.read_text(encoding="utf-8"))

    for forbidden in (
        "TeleportTo",
        "NearTeleportTo",
        "SetPosition",
        "Relocate",
        "MoveBotToPoint",
        "MovePoint",
        "CastSpell(bot, spellId, true)",
    ):
        assert forbidden not in branch

    header = HEADER.read_text(encoding="utf-8")
    assert "std::variant<CastSpell, Move, DirectionalMobility," in header
