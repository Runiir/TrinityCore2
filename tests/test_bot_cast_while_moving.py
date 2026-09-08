from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "src/server/game/Bots/BotCastWhileMoving.h"
RESOLVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
EXECUTOR = ROOT / "src/server/game/Bots/BotActionExecutor.cpp"


def test_native_cast_while_moving_gates_compile_and_replay(tmp_path: Path) -> None:
    source = tmp_path / "bot_cast_while_moving.cpp"
    binary = tmp_path / "bot_cast_while_moving"
    source.write_text(
        r'''
#include "Bots/BotCastWhileMoving.h"

#include <cassert>

class SpellInfo
{
};

enum class AuraState
{
    None,
    Active,
    Expired,
};

struct NativeCaster
{
    AuraState Aura = AuraState::None;
    bool AffectsSpell = false;

    bool HasAuraTypeWithAffectMask(AuraType auraType,
        SpellInfo const* spellInfo) const
    {
        return Aura == AuraState::Active && AffectsSpell && spellInfo
            && auraType == SPELL_AURA_CAST_WHILE_WALKING;
    }
};

bool CandidateGate(NativeCaster const& caster, SpellInfo const* spellInfo,
    bool movementCompatibleOnly, bool castTime, bool channeled)
{
    return BotCastWhileMoving::RejectMovingCandidate(&caster, spellInfo,
        movementCompatibleOnly, castTime, channeled);
}

bool ExecutorGate(NativeCaster const& caster, SpellInfo const* spellInfo,
    bool moving, bool castTime, bool& stopped)
{
    if (!moving || !castTime)
        return false;
    return BotCastWhileMoving::StopUncoveredMovingCast(&caster, spellInfo,
        [&stopped]() { stopped = true; });
}

int main()
{
    SpellInfo lightningBolt;
    NativeCaster elemental{ AuraState::Active, true };
    assert(!CandidateGate(elemental, &lightningBolt, true, true, false));

    bool stopped = false;
    assert(!ExecutorGate(elemental, &lightningBolt, true, true, stopped));
    assert(!stopped);

    for (NativeCaster uncovered : {
            NativeCaster{ AuraState::Active, false }, // wrong spell mask
            NativeCaster{ AuraState::None, true }, // no aura
            NativeCaster{ AuraState::Expired, true } // expired aura
        })
    {
        assert(CandidateGate(uncovered, &lightningBolt, true, true, false));
        stopped = false;
        assert(ExecutorGate(uncovered, &lightningBolt, true, true, stopped));
        assert(stopped);
    }

    // The candidate gate continues to cover channels, while the executor's
    // existing cast-time stop/yield branch leaves channel legality to Spell.
    NativeCaster noCapability{ AuraState::None, false };
    assert(CandidateGate(noCapability, &lightningBolt, true, true, false));
    assert(CandidateGate(noCapability, &lightningBolt, true, false, true));
    stopped = false;
    assert(!ExecutorGate(noCapability, &lightningBolt, true, false, stopped));
    assert(!stopped);

    // Instant actions never enter either cast-time/channel movement gate.
    assert(!CandidateGate(noCapability, &lightningBolt, true, false, false));
    assert(!ExecutorGate(noCapability, &lightningBolt, true, false, stopped));
    assert(!stopped);
}
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
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/server/game/Spells/Auras"),
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "src/common/Utilities"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_production_callers_use_the_shared_native_predicate() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    resolver = RESOLVER.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")

    assert "HasAuraTypeWithAffectMask" in helper
    assert '#include "Bots/BotCastWhileMoving.h"' in resolver
    assert '#include "Bots/BotCastWhileMoving.h"' in executor
    assert "BotCastWhileMoving::RejectMovingCandidate" in resolver
    assert "BotCastWhileMoving::StopUncoveredMovingCast" in executor
    assert "bot->StopMoving();" in executor
    assert "bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);" in executor
    assert "bot->GetMotionMaster()->MoveIdle();" in executor
