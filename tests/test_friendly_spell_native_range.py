from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatSupport.cpp"


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


def test_actual_try_cast_friendly_spell_defers_range_to_native_cast(
    tmp_path: Path,
) -> None:
    """Compile the production member body with minimal native seams.

    The member body is extracted verbatim from the production translation
    unit.  The harness stubs target/assist/LOS/state/power/cast services and
    records the native CastSpell call; it deliberately contains no range
    calculation, so range acceptance and rejection belong to that stubbed
    native result just as they do in the server.
    """

    support = SUPPORT.read_text(encoding="utf-8")
    caller_body = _function_body(
        support, "bool BotWorldPopulationMgr::TryCastFriendlySpell("
    )
    source = tmp_path / "try_cast_friendly_spell.cpp"
    binary = tmp_path / "try_cast_friendly_spell"
    source.write_text(
        """
#include <cstdint>
#include <string>

using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
using SpellCastResult = int;

constexpr uint32 UNIT_STATE_CASTING = 1;
constexpr int MOTION_SLOT_ACTIVE = 2;
constexpr SpellCastResult SPELL_CAST_OK = 0;

struct ObjectGuid
{
    uint64 RawValue = 0;

    uint64 GetRawValue() const
    {
        return RawValue;
    }
};

struct Creature;

struct Unit
{
    bool Alive = true;
    bool Hostile = false;
    bool LineOfSight = true;
    float Distance = 0.0f;
    ObjectGuid Guid{ 30009 };

    bool IsAlive() const
    {
        return Alive;
    }

    bool IsValidAssistTarget(Unit const* target) const
    {
        return target && !target->Hostile;
    }

    Creature const* ToCreature() const
    {
        return nullptr;
    }

    ObjectGuid GetGUID() const
    {
        return Guid;
    }

    bool IsWithinLOSInMap(Unit const*) const
    {
        return LineOfSight;
    }
};

struct SpellInfo
{
    uint32 Id = 0;
    bool Positive = true;
    uint32 CastTimeMs = 0;

    bool IsPositive() const
    {
        return Positive;
    }

    uint32 CalcCastTime(uint8) const
    {
        return CastTimeMs;
    }
};

struct Creature : Unit
{
    uint32 GetEntry() const
    {
        return 0;
    }

    uint32 GetSpawnId() const
    {
        return 0;
    }
};

struct SpellHistory
{
    bool GlobalCooldown = false;
    bool Ready = true;

    bool HasGlobalCooldown(SpellInfo const*) const
    {
        return GlobalCooldown;
    }

    bool IsReady(SpellInfo const*) const
    {
        return Ready;
    }
};

struct MotionMaster
{
    uint32 ClearCalls = 0;
    uint32 MoveIdleCalls = 0;

    void Clear(int)
    {
        ++ClearCalls;
    }

    void MoveIdle()
    {
        ++MoveIdleCalls;
    }
};

struct Player : Unit
{
    SpellHistory* History = nullptr;
    MotionMaster* Motion = nullptr;
    uint32 UnitStateMask = 0;
    bool PowerAvailable = true;
    uint32 StopMovingCalls = 0;
    uint32 CastAttempts = 0;
    uint32 LastSpellId = 0;
    float LastTargetDistance = 0.0f;
    SpellCastResult NativeCastResult = SPELL_CAST_OK;

    bool HasUnitState(uint32 state) const
    {
        return (UnitStateMask & state) != 0;
    }

    SpellHistory* GetSpellHistory() const
    {
        return History;
    }

    uint8 getLevel() const
    {
        return 85;
    }

    void StopMoving()
    {
        ++StopMovingCalls;
    }

    MotionMaster* GetMotionMaster() const
    {
        return Motion;
    }

    SpellCastResult CastSpell(Unit* target, uint32 spellId, bool)
    {
        ++CastAttempts;
        LastSpellId = spellId;
        LastTargetDistance = target ? target->Distance : 0.0f;
        return NativeCastResult;
    }
};

struct SpellMgr
{
    SpellInfo const* ActiveSpell = nullptr;

    SpellInfo const* GetSpellInfo(uint32 spellId) const
    {
        return ActiveSpell && ActiveSpell->Id == spellId ? ActiveSpell : nullptr;
    }
};

SpellMgr SpellManager;
SpellMgr* sSpellMgr = &SpellManager;

bool HasPowerForSpell(Player const* bot, SpellInfo const*)
{
    return bot && bot->PowerAvailable;
}

namespace BotRaidAreaAuthority
{
bool IsAllOffenseSuppressed(uint64)
{
    return false;
}

bool IsProtectedEncounterTarget(uint64, uint32, uint32, uint64)
{
    return false;
}
}

bool HasNearbyProtectedEncounterTarget(Player*, Unit*)
{
    return false;
}

bool SpellHasHostileMultiTargetSemantics(SpellInfo const*)
{
    return false;
}

uint64 NextPendingCastId = 500;
uint32 BeginPendingCalls = 0;
uint32 CancelPendingCalls = 0;
std::string LastCancelReason;

uint64 BeginPendingHealCast(Player*, Unit*, uint32)
{
    ++BeginPendingCalls;
    return ++NextPendingCastId;
}

void CancelBotSpellStart(uint64, Player*, char const* reason)
{
    ++CancelPendingCalls;
    LastCancelReason = reason ? reason : "";
}

class BotWorldPopulationMgr
{
public:
    bool TryCastFriendlySpell(Player* bot, Unit* target, uint32 spellId,
        std::string* failureReason = nullptr);
};

bool BotWorldPopulationMgr::TryCastFriendlySpell(Player* bot, Unit* target,
    uint32 spellId, std::string* failureReason)
{
"""
        + caller_body
        + """
}

void Reset(Player& bot, SpellHistory& history, MotionMaster& motion,
    Unit& target)
{
    bot = Player{};
    history = SpellHistory{};
    motion = MotionMaster{};
    target = Unit{};
    bot.History = &history;
    bot.Motion = &motion;
}

int main()
{
    SpellInfo holyShock{ 20473, true, 0 };
    SpellManager.ActiveSpell = &holyShock;
    BotWorldPopulationMgr manager;
    Player bot;
    SpellHistory history;
    MotionMaster motion;
    Unit friendly;
    std::string reason;

    // The two observed friendly Holy Shock distances reach native CastSpell,
    // and the instant spell never enters the hard-cast movement block.
    Reset(bot, history, motion, friendly);
    friendly.Distance = 23.247f;
    if (!manager.TryCastFriendlySpell(&bot, &friendly, 20473, &reason)
        || bot.CastAttempts != 1 || bot.LastSpellId != 20473
        || bot.LastTargetDistance != 23.247f || bot.StopMovingCalls != 0
        || motion.ClearCalls != 0 || motion.MoveIdleCalls != 0
        || !reason.empty())
        return 1;

    Reset(bot, history, motion, friendly);
    friendly.Distance = 32.592f;
    if (!manager.TryCastFriendlySpell(&bot, &friendly, 20473, &reason)
        || bot.CastAttempts != 1 || bot.LastTargetDistance != 32.592f
        || bot.StopMovingCalls != 0 || !reason.empty())
        return 2;

    // A native range failure is surfaced unchanged through the existing
    // spell_cast_result_* receipt and cancels the pending identity.
    Reset(bot, history, motion, friendly);
    friendly.Distance = 42.1f;
    bot.NativeCastResult = 150;
    if (manager.TryCastFriendlySpell(&bot, &friendly, 20473, &reason)
        || bot.CastAttempts != 1 || BeginPendingCalls != 3
        || CancelPendingCalls != 1 || LastCancelReason != "cast_submission_failed"
        || reason != "spell_cast_result_150")
        return 3;

    Reset(bot, history, motion, friendly);
    Unit hostile;
    hostile.Hostile = true;
    bot.NativeCastResult = SPELL_CAST_OK;
    if (manager.TryCastFriendlySpell(&bot, &hostile, 20473, &reason)
        || bot.CastAttempts != 0 || reason != "invalid_assist_target")
        return 4;

    Reset(bot, history, motion, friendly);
    bot.LineOfSight = false;
    if (manager.TryCastFriendlySpell(&bot, &friendly, 20473, &reason)
        || bot.CastAttempts != 0 || reason != "line_of_sight")
        return 5;

    Reset(bot, history, motion, friendly);
    history.GlobalCooldown = true;
    if (manager.TryCastFriendlySpell(&bot, &friendly, 20473, &reason)
        || bot.CastAttempts != 0 || reason != "global_cooldown")
        return 6;

    Reset(bot, history, motion, friendly);
    history.Ready = false;
    if (manager.TryCastFriendlySpell(&bot, &friendly, 20473, &reason)
        || bot.CastAttempts != 0 || reason != "spell_not_ready")
        return 7;

    Reset(bot, history, motion, friendly);
    bot.PowerAvailable = false;
    if (manager.TryCastFriendlySpell(&bot, &friendly, 20473, &reason)
        || bot.CastAttempts != 0 || reason != "insufficient_power")
        return 8;

    Reset(bot, history, motion, friendly);
    bot.UnitStateMask = UNIT_STATE_CASTING;
    if (manager.TryCastFriendlySpell(&bot, &friendly, 20473, &reason)
        || bot.CastAttempts != 0 || reason != "already_casting")
        return 9;

    // A real hard-cast still uses the existing stop/idle transition before a
    // native rejection; this fixture does not generalize that movement rule.
    Reset(bot, history, motion, friendly);
    holyShock.CastTimeMs = 2500;
    bot.NativeCastResult = 150;
    if (manager.TryCastFriendlySpell(&bot, &friendly, 20473, &reason)
        || bot.CastAttempts != 1 || bot.StopMovingCalls != 1
        || motion.ClearCalls != 1 || motion.MoveIdleCalls != 1
        || CancelPendingCalls != 2 || reason != "spell_cast_result_150")
        return 10;

    return 0;
}
""",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++",
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


def test_try_cast_friendly_spell_has_no_bot_range_gate() -> None:
    support = SUPPORT.read_text(encoding="utf-8")
    caller = _function_body(
        support, "bool BotWorldPopulationMgr::TryCastFriendlySpell("
    )

    assert "GetMaxRange" not in caller
    assert "GetSpellMaxRangeForTarget" not in caller
    assert "IsWithinDistInMap" not in caller
    for marker in (
        'fail("invalid_assist_target")',
        'fail("line_of_sight")',
        'fail("already_casting")',
        'fail("global_cooldown")',
        'fail("spell_not_ready")',
        'fail("insufficient_power")',
        "StopMoving()",
        "BeginPendingHealCast",
        "CancelBotSpellStart",
        "spell_cast_result_",
    ):
        assert marker in caller
