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
#include <cstddef>

// SpellInfo::CalcCastTime returns the base (level-scaled) cast time; the
// caster's modifiers are applied separately, exactly as Spell::prepare does.
class SpellInfo
{
public:
    uint32 Id = 0;
    uint32 BaseCastTime = 0;

    uint32 CalcCastTime(uint8 /*level*/) const { return BaseCastTime; }
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
    // One ChangeCastTime percent spell mod (e.g. Shooting Stars -100% on
    // Starsurge) and the unit cast-speed multiplier (haste).
    uint32 ModSpellId = 0;
    int32 ModPct = 0;
    float CastSpeed = 1.0f;
    int Previews = 0;

    bool HasAuraTypeWithAffectMask(AuraType auraType,
        SpellInfo const* spellInfo) const
    {
        return Aura == AuraState::Active && AffectsSpell && spellInfo
            && auraType == SPELL_AURA_CAST_WHILE_WALKING;
    }

    uint8 getLevel() const { return 85; }

    // Mirrors WorldObject::ModSpellCastTime's order (spell mods, then cast
    // speed).  The std::nullptr_t parameter proves the preview passes no
    // Spell, so no charge can be registered against a live cast.
    void ModSpellCastTime(SpellInfo const* spellInfo, int32& castTime,
        std::nullptr_t)
    {
        ++Previews;
        if (spellInfo->Id == ModSpellId)
            castTime = int32(double(castTime) * (100 + ModPct) / 100.0);
        castTime = int32(float(castTime) * CastSpeed);
    }
};

// Production resolver: the movement gate sees the effective cast time.
bool CandidateGate(NativeCaster& caster, SpellInfo const* spellInfo,
    bool movementCompatibleOnly, bool channeled)
{
    return BotCastWhileMoving::RejectMovingCandidate(&caster, spellInfo,
        movementCompatibleOnly,
        BotCastWhileMoving::HasEffectiveCastTime(&caster, spellInfo),
        channeled);
}

bool CandidateGate(NativeCaster const& caster, SpellInfo const* spellInfo,
    bool movementCompatibleOnly, bool castTime, bool channeled)
{
    return BotCastWhileMoving::RejectMovingCandidate(&caster, spellInfo,
        movementCompatibleOnly, castTime, channeled);
}

// Production executor: a base cast-time spell on a moving bot reaches the
// shared stop gate, which yields only for an effective cast-time spell.
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
    SpellInfo lightningBolt{ 403, 2500 };
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

    // A Shooting Stars proc (-100% cast time on Starsurge) makes the native
    // cast instant, so a moving Balance bot may submit it without stopping.
    SpellInfo starsurge{ 78674, 2000 };
    SpellInfo wrath{ 5176, 2500 };
    NativeCaster balance;
    balance.ModSpellId = 78674;
    balance.ModPct = -100;
    balance.CastSpeed = 0.8f;
    assert(!BotCastWhileMoving::HasEffectiveCastTime(&balance, &starsurge));
    assert(!CandidateGate(balance, &starsurge, true, false));
    stopped = false;
    assert(!ExecutorGate(balance, &starsurge, true, true, stopped));
    assert(!stopped);

    // The proc covers only its own spell: hasted Wrath keeps a cast time and
    // is still rejected and stopped while moving.
    assert(BotCastWhileMoving::HasEffectiveCastTime(&balance, &wrath));
    assert(CandidateGate(balance, &wrath, true, false));
    stopped = false;
    assert(ExecutorGate(balance, &wrath, true, true, stopped));
    assert(stopped);

    // Without the proc, or with only a partial reduction, Starsurge keeps a
    // cast time: no modifier short of the client's instant cast passes.
    for (int32 pct : { 0, -50, -99 })
    {
        NativeCaster noProc;
        noProc.ModSpellId = 78674;
        noProc.ModPct = pct;
        noProc.CastSpeed = 0.5f;
        assert(BotCastWhileMoving::HasEffectiveCastTime(&noProc, &starsurge));
        assert(CandidateGate(noProc, &starsurge, true, false));
        stopped = false;
        assert(ExecutorGate(noProc, &starsurge, true, true, stopped));
        assert(stopped);
    }

    // A stationary bot is never movement-gated, proc or not.
    assert(!CandidateGate(balance, &wrath, false, false));

    // A base-instant spell stays instant and needs no modifier preview; a
    // missing caster falls back to the base cast time.
    SpellInfo moonfire{ 8921, 0 };
    NativeCaster preview;
    assert(!BotCastWhileMoving::HasEffectiveCastTime(&preview, &moonfire));
    assert(preview.Previews == 0);
    assert(BotCastWhileMoving::HasEffectiveCastTime(&preview, &wrath));
    assert(preview.Previews == 1);
    assert(BotCastWhileMoving::HasEffectiveCastTime(
        static_cast<NativeCaster const*>(nullptr), &wrath));
    assert(!BotCastWhileMoving::HasEffectiveCastTime(&preview,
        static_cast<SpellInfo const*>(nullptr)));

    // Channels stay gated by the channel flag even when instant to start.
    SpellInfo hurricane{ 16914, 0 };
    assert(CandidateGate(balance, &hurricane, true, true));
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
    # DPS-065: the resolver's moving check uses the caster's effective cast
    # time (Spell::prepare's CalcCastTime + ModSpellCastTime), not the base
    # SpellInfo cast time, so a proc-instant cast is admissible while moving.
    assert (
        "bool const candidateHasCastTime =\n"
        "            BotCastWhileMoving::HasEffectiveCastTime(bot, candidateSpellInfo);"
    ) in resolver
    assert "candidateSpellInfo->CalcCastTime(bot->getLevel()) > 0" not in resolver
    assert "ModSpellCastTime(spellInfo, castTime, nullptr)" in helper
    stop = helper[helper.index("bool StopUncoveredMovingCast("):]
    assert "!HasEffectiveCastTime(caster, spellInfo)" in stop[: stop.index("stopMoving();")]
    assert "BotCastWhileMoving::StopUncoveredMovingCast" in executor
    assert "bot->StopMoving();" in executor
    assert "bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);" in executor
    assert "bot->GetMotionMaster()->MoveIdle();" in executor
