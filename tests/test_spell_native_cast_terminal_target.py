"""A finishing cast never dereferences its cached target after that target was deleted.

Round-4 six-shard batch (blackwing_descent_10n-r04-b1-20260926T052011Z, build
e2d0568e6960): `.botauto stop blackwing_descent_10n_atramedes_c0` killed the
worldserver with SIGSEGV 22 ms after the command was sent. Kernel:
`ip 000070dfc7a90b00 ... error 15 in libstdc++.so.6.0.35[290b00,...]`, i.e. an
instruction fetch at libstdc++'s `vtable for __cxxabiv1::__si_class_type_info`
+ 16, on the main (world) thread. In that build `_ZTV6Object` + 16 + 0x138 is
`_ZTI3Pet` (whose first word is exactly that address), and 0x138 is the slot
`WorldObject::CanSeeOrDetect` calls first, `obj->IsNeverVisible()`: a virtual
call on a WorldObject whose destructors had run down to `Object`.

StopAutonomy logs the cohort out in roster order (tank 11003001, holy paladin
11003005, disc priest 11003007, ...). The priest's open cast was Heal (2050)
on the paladin (cast instance 68656, prepared at 1790401025713, the last trace
before the stop). The paladin was deleted first; the priest's CombatStop then cancelled the heal, and
Spell::finish -> NotifyNativeSpellFinishing -> Spell::ObserveNativeCastFinishing
read `m_targets.GetUnitTarget()` (refreshed only by Spell::UpdatePointers) and
called `IsValidAttackTarget` -> `CanSeeOrDetect` on the deleted paladin.

This replays that teardown against the real ObserveNativeCastFinishing body,
with value stubs for the entities, under AddressSanitizer (freed players) and
with poisoned-but-retained players (no sanitizer needed).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Spells/SpellNativeCastObservationSpell.cpp"


def _block(source: str, start: int) -> str:
    """source[start:] through the brace that closes its first opening brace."""
    depth = 0
    for index in range(source.index("{", start), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError("unterminated block")


def _function(source: str, signature: str) -> str:
    return _block(source, source.index(signature))


def _anonymous_namespace(source: str) -> str:
    match = re.search(r"^namespace\n\{\n", source, re.M)
    return _block(source, match.start()) if match else ""


STUBS = r'''
#include <cstdint>
#include <cstdio>
#include <map>
#include <string>
#include <utility>
#include <vector>
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;

struct ObjectGuid
{
    uint64 raw = 0;
    bool IsEmpty() const { return raw == 0; }
    bool operator==(ObjectGuid const& other) const { return raw == other.raw; }
    bool operator!=(ObjectGuid const& other) const { return raw != other.raw; }
};
struct SpellInfo { uint32 Id = 0; };

int g_poisonedAccess = 0;
struct Unit;
struct WorldObject
{
    ObjectGuid guid;
    bool inWorld = true;
    bool isUnit = true;
    bool destroyed = false;  // retained-memory variant: the destructors "ran"
    virtual ~WorldObject() = default;
    void Touch() const { if (destroyed) ++g_poisonedAccess; }
    // Object::IsNeverVisible() is the first virtual CanSeeOrDetect calls on obj.
    virtual bool IsNeverVisible() const { Touch(); return !inWorld; }
    ObjectGuid GetGUID() const { Touch(); return guid; }
    bool IsInWorld() const { Touch(); return inWorld; }
    Unit* ToUnit();
    // WorldObject::IsValidAttackTarget -> CanSeeOrDetect(target) -> target->IsNeverVisible().
    bool IsValidAttackTarget(WorldObject const* target, SpellInfo const*) const
    {
        return !target->IsNeverVisible();
    }
};
struct Unit : WorldObject
{
    uint32 health = 100;
    bool IsAlive() const { Touch(); return health != 0; }
};
Unit* WorldObject::ToUnit() { Touch(); return isUnit ? static_cast<Unit*>(this) : nullptr; }

// The caster's map: a logged-out player is removed before it is deleted.
std::map<uint64, Unit*> g_live;
namespace ObjectAccessor
{
Unit* GetUnit(WorldObject const& u, ObjectGuid const& guid)
{
    if (!u.IsInWorld())
        return nullptr;
    auto itr = g_live.find(guid.raw);
    return itr == g_live.end() ? nullptr : itr->second;
}
}

struct SpellCastTargets
{
    WorldObject* m_objectTarget = nullptr;  // refreshed only by Spell::UpdatePointers()
    ObjectGuid m_objectTargetGUID;
    Unit* GetUnitTarget() const { return m_objectTarget ? m_objectTarget->ToUnit() : nullptr; }
    ObjectGuid GetUnitTargetGUID() const { return m_objectTargetGUID; }
};

struct SpellNativeCastObservation
{
    ObjectGuid TerminalTargetGuid;
    bool Present = false;
    bool AliveAvailable = false;
    bool Alive = false;
    bool AttackabilityAvailable = false;
    bool Attackable = false;
    bool Finished = false;
};
namespace SpellNativeCastObservationOps
{
void SetSubmittedTarget(SpellNativeCastObservation&, ObjectGuid) { }
void MarkFinishing(SpellNativeCastObservation& o, bool, ObjectGuid terminalTargetGuid,
    bool present, bool aliveAvailable, bool alive, bool attackabilityAvailable,
    bool attackable, uint32, std::string, uint64)
{
    o.TerminalTargetGuid = terminalTargetGuid;
    o.Present = present;
    o.AliveAvailable = aliveAvailable;
    o.Alive = alive;
    o.AttackabilityAvailable = attackabilityAvailable;
    o.Attackable = attackable;
    o.Finished = true;
}
}

struct Spell
{
    Spell(WorldObject* caster, SpellInfo const* info) : m_caster(caster), m_spellInfo(info) { }
    WorldObject* const m_caster;
    SpellInfo const* m_spellInfo;
    SpellCastTargets m_targets;
    uint32 m_spellState = 1;  // SPELL_STATE_PREPARING
    SpellNativeCastObservation m_nativeCastObservation;
    void ObserveNativeCastFinishing(bool success, std::string terminalScopeJson, uint64 observedAtMs);
};
'''

REPLAY = r'''
struct Bot { uint64 Guid; Unit* Player; Spell* Current; };

int main()
{
    SpellInfo heal{2050};
    SpellInfo powerWordShield{17};
    SpellInfo flashOfLight{19750};
    SpellInfo runeTap{48982};
    // StopAutonomy's roster order in the crashed Atramedes cohort.
    std::vector<Bot> bots;
    for (uint64 guid : {11003001ULL, 11003005ULL, 11003007ULL})
    {
        Unit* player = new Unit();
        player->guid.raw = guid;
        g_live[guid] = player;
        bots.push_back({guid, player, nullptr});
    }
    auto cast = [](Bot& caster, Bot const& target, SpellInfo const* info)
    {
        caster.Current = new Spell(caster.Player, info);
        caster.Current->m_targets.m_objectTarget = target.Player;
        caster.Current->m_targets.m_objectTargetGUID = target.Player->GetGUID();
    };
    auto finish = [](Bot& bot, bool success)
    {
        bot.Current->ObserveNativeCastFinishing(success, "{}", 1);
        SpellNativeCastObservation const& o = bot.Current->m_nativeCastObservation;
        std::printf("{\"caster\":%llu,\"target\":%llu,\"finished\":%s,\"present\":%s,\"alive\":%s,\"attackable\":%s}\n",
            (unsigned long long)bot.Guid, (unsigned long long)o.TerminalTargetGuid.raw,
            o.Finished ? "true" : "false", o.Present ? "true" : "false",
            o.Alive ? "true" : "false", o.Attackable ? "true" : "false");
        delete bot.Current;
        bot.Current = nullptr;
    };
    // A live cross-bot cast before the stop: the priest's shield on the tank.
    cast(bots[2], bots[0], &powerWordShield);
    finish(bots[2], true);

    cast(bots[0], bots[0], &runeTap);       // the tank on itself
    cast(bots[1], bots[1], &flashOfLight);  // the paladin on itself
    cast(bots[2], bots[1], &heal);          // the priest on the paladin, deleted one bot earlier

    for (Bot& bot : bots)
    {
        // BotMgr::CleanupBot: CombatStop(true)/CastStop() cancel the current
        // cast (Spell::cancel -> finish -> NotifyNativeSpellFinishing)...
        if (bot.Current)
            finish(bot, false);
        // ...then LogoutPlayer removes the player from its map and deletes it.
        bot.Player->inWorld = false;
        g_live.erase(bot.Guid);
#ifdef REPLAY_FREE_PLAYERS
        delete bot.Player;
#else
        bot.Player->destroyed = true;
#endif
    }
    return g_poisonedAccess ? 3 : 0;
}
'''


def _program() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    finishing = _function(source, "void Spell::ObserveNativeCastFinishing(")
    return STUBS + _anonymous_namespace(source) + "\n" + finishing + "\n" + REPLAY


def _build(tmp_path: Path, name: str, flags: list[str]) -> subprocess.CompletedProcess[str]:
    source = tmp_path / f"{name}.cpp"
    source.write_text(_program(), encoding="utf-8")
    return subprocess.run(["c++", "-std=c++17", "-O0", "-g", "-Wall", "-Wextra", "-Werror", *flags,
                           str(source), "-o", str(tmp_path / name)],
                          capture_output=True, text=True)


EXPECTED = [
    # A live cross-bot target, resolved while every bot is in the world.
    {"caster": 11003007, "target": 11003001, "finished": True, "present": True, "alive": True,
     "attackable": True},
    {"caster": 11003001, "target": 11003001, "finished": True, "present": True, "alive": True,
     "attackable": True},
    {"caster": 11003005, "target": 11003005, "finished": True, "present": True, "alive": True,
     "attackable": True},
    # The paladin was logged out and deleted: absent, never dereferenced.
    {"caster": 11003007, "target": 11003005, "finished": True, "present": False, "alive": False,
     "attackable": False},
]


def test_finishing_never_touches_a_retained_deleted_target(tmp_path):
    built = _build(tmp_path, "poisoned", [])
    assert built.returncode == 0, built.stderr
    run = subprocess.run([str(tmp_path / "poisoned")], capture_output=True, text=True)
    assert run.returncode == 0, "a finishing cast read its deleted target: " + run.stdout + run.stderr
    assert [json.loads(line) for line in run.stdout.splitlines()] == EXPECTED


def test_finishing_after_the_target_was_freed_is_clean_under_asan(tmp_path):
    flags = ["-DREPLAY_FREE_PLAYERS", "-fsanitize=address", "-fno-omit-frame-pointer"]
    built = _build(tmp_path, "freed", flags)
    if built.returncode != 0 and "asan" in built.stderr.lower():
        pytest.skip("AddressSanitizer runtime unavailable")
    assert built.returncode == 0, built.stderr
    run = subprocess.run([str(tmp_path / "freed")], capture_output=True, text=True,
                         env={"ASAN_OPTIONS": "detect_leaks=0:abort_on_error=0"})
    assert "heap-use-after-free" not in run.stderr, run.stderr
    assert run.returncode == 0, run.stderr
    assert [json.loads(line) for line in run.stdout.splitlines()] == EXPECTED


def test_source_resolves_the_terminal_target_by_guid():
    source = SOURCE.read_text(encoding="utf-8")
    finishing = _function(source, "void Spell::ObserveNativeCastFinishing(")
    assert "GetUnitTarget()" not in finishing.replace("// Never m_targets.GetUnitTarget()", "")
    assert "ObjectAccessor::GetUnit(*caster, targetGuid)" in _anonymous_namespace(source)
    assert len(source.splitlines()) < 1000
