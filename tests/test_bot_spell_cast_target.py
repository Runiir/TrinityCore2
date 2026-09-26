"""Bot decisions read a spell's unit target only through BotSpellCastTarget.

SpellCastTargets caches its target as a raw pointer that only
Spell::UpdatePointers() refreshes. Bot decisions run before the tick's map
update, so the cache can name a unit deleted since (patch 0001's `.botauto
stop` SIGSEGV went through the same cache). BotSpellCastTarget::UnitTarget
returns the cached pointer exactly when it proves the object alive, without
dereferencing the cache, and nullptr otherwise.

The replays compile the real helper (and one real decision site) against value
stubs: every live-target case returns the legacy GetUnitTarget() pointer and
the decision site decides identically; deleted targets are never read (poisoned
retained objects, and freed objects under AddressSanitizer).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "src/server/game/Bots/BotSpellCastTarget.h"
CONTAMINATION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteContamination.cpp"
BOT_SOURCES = [ROOT / "src/server/game/Bots", *sorted((ROOT / "src/server/scripts/Commands").glob("cs_*bot*.cpp"))]
CACHED_TARGET_READ = re.compile(r"(?:\b(\w+)\s*(?:\.|->)\s*)?"
                               r"\b(?:GetUnitTarget|GetObjectTarget|GetGOTarget|GetCorpseTarget|GetOrigUnitTarget)"
                               r"\s*\(\s*\)")
# A SpellCastTargets the file constructs itself holds pointers it just set.
LOCAL_TARGETS = re.compile(r"\bSpellCastTargets\s+(\w+)\s*[;({=]")
MIGRATED_SITES = {
    "src/server/game/Bots/BotWorldPopulationMgrBossMechanics.cpp": 5,
    "src/server/game/Bots/BotWorldPopulationMgrCalibrationHealer.cpp": 1,
    "src/server/game/Bots/BotWorldPopulationMgrCombatDiagnostics.cpp": 1,
    "src/server/game/Bots/BotWorldPopulationMgrValidationRouteContamination.cpp": 2,
    "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
    "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp": 3,
    "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
    "BotWorldPopulationMgrValidationRouteDrudgeFutureBossBoundary.cpp": 1,
    "src/server/game/Bots/BotActionExecutor.cpp": 1,
}


def _bot_files() -> list[Path]:
    files: list[Path] = []
    for source in BOT_SOURCES:
        files += sorted(source.rglob("*")) if source.is_dir() else [source]
    return [path for path in files if path.suffix in {".h", ".hpp", ".cpp"}]


def _cached_reads(text: str, helper: bool = False) -> list[tuple[int, str]]:
    local = set(LOCAL_TARGETS.findall(text))
    reads = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("//"):
            continue
        for match in CACHED_TARGET_READ.finditer(line):
            if match.group(1) in local:
                continue
            if helper and match.group(0).replace(" ", "") == "m_targets.GetObjectTarget()":
                continue  # the helper compares the cached pointer, never dereferences it
            reads.append((number, line.strip()))
    return reads


def test_no_bot_file_reads_a_cached_spell_target():
    offenders = [f"{path.relative_to(ROOT)}:{number}: {line}"
                 for path in _bot_files()
                 for number, line in _cached_reads(path.read_text(encoding="utf-8", errors="replace"),
                                                   helper=path == HELPER)]
    assert not offenders, "read spell targets through BotSpellCastTarget::UnitTarget:\n" + "\n".join(offenders)


def test_grep_guard_allows_only_locally_constructed_targets():
    text = """SpellCastTargets targets;
targets.SetUnitTarget(unit);
Unit* mine = targets.GetUnitTarget();
Unit* theirs = current->m_targets.GetUnitTarget();
Unit* other = spell->m_targets . GetObjectTarget();
// current->m_targets.GetUnitTarget() in a comment
"""
    assert [number for number, _ in _cached_reads(text)] == [4, 5]
    assert _cached_reads("WorldObject* const cached = spell->m_targets.GetObjectTarget();", helper=True) == []


def test_every_listed_site_uses_the_helper_and_stays_small():
    for relative, count in MIGRATED_SITES.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert text.count("BotSpellCastTarget::UnitTarget(") == count, relative
        assert '#include "Bots/BotSpellCastTarget.h"' in text, relative
        assert len(text.splitlines()) < 1000, relative
    assert len(HELPER.read_text(encoding="utf-8").splitlines()) < 1000


def _block(source: str, start: int) -> str:
    depth = 0
    for index in range(source.index("{", start), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError("unterminated block")


def _helper_namespace() -> str:
    source = HELPER.read_text(encoding="utf-8")
    return _block(source, source.index("namespace BotSpellCastTarget\n{"))


STUBS = r'''
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <map>
#include <string>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;

struct ObjectGuid
{
    uint64 raw = 0;
    bool player = false;
    bool unit = true;  // high GUID type: player, creature, pet or vehicle
    bool IsEmpty() const { return raw == 0; }
    bool IsUnit() const { return unit; }
    bool IsPlayer() const { return player; }
    uint64 GetRawValue() const { return raw; }
    bool operator==(ObjectGuid const& other) const { return raw == other.raw; }
    bool operator!=(ObjectGuid const& other) const { return raw != other.raw; }
};

int g_poisoned = 0;
struct Map { float visibility = 100.0f; };
struct Unit;
struct Creature;
struct WorldObject
{
    ObjectGuid guid;
    Map* map = nullptr;
    bool isUnit = true;
    bool destroyed = false;  // retained-memory variant: the object was deleted
    virtual ~WorldObject() = default;
    void Touch() const { if (destroyed) ++g_poisoned; }
    ObjectGuid GetGUID() const { Touch(); return guid; }
    Map* FindMap() const { Touch(); return map; }
    float GetVisibilityRange() const { Touch(); return map->visibility; }
    Unit* ToUnit();
};
struct SpellInfo { uint32 Id = 0; bool multiTarget = false; };
enum CurrentSpellTypes { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL, CURRENT_AUTOREPEAT_SPELL, CURRENT_MAX_SPELL };
struct Spell;
struct Unit : WorldObject
{
    bool alive = true;
    uint32 entry = 0;
    uint32 spawnId = 0;
    Unit* victim = nullptr;
    Spell* current[CURRENT_MAX_SPELL] = {};
    std::vector<int> interrupted;
    bool IsAlive() const { Touch(); return alive; }
    uint32 GetEntry() const { Touch(); return entry; }
    uint32 GetSpawnId() const { Touch(); return spawnId; }
    Unit* GetVictim() const { Touch(); return victim; }
    Spell* GetCurrentSpell(CurrentSpellTypes type) const { Touch(); return current[type]; }
    void InterruptSpell(CurrentSpellTypes type, bool) { Touch(); interrupted.push_back(type); current[type] = nullptr; }
    Creature* ToCreature();
};
struct Creature : Unit { };
struct Player : Unit { };
Unit* WorldObject::ToUnit() { Touch(); return isUnit ? static_cast<Unit*>(this) : nullptr; }
Creature* Unit::ToCreature() { Touch(); return guid.player ? nullptr : static_cast<Creature*>(this); }

// The caster's map: in-world units by GUID (Map::_objectsStore / player map check).
Map g_map;
std::map<uint64, Unit*> g_store;
// ObjectAccessor's players: login to deletion, any map, in transit included.
std::map<uint64, Player*> g_connected;
namespace ObjectAccessor
{
Unit* GetUnit(WorldObject const& u, ObjectGuid const& guid)
{
    if (u.FindMap() != &g_map)
        return nullptr;
    auto itr = g_store.find(guid.raw);
    return itr == g_store.end() ? nullptr : itr->second;
}
Player* FindConnectedPlayer(ObjectGuid const& guid)
{
    auto itr = g_connected.find(guid.raw);
    return itr == g_connected.end() ? nullptr : itr->second;
}
}

template <class T> struct GridReference { T* source; T* GetSource() const { return source; } };
template <class T> struct GridRefManager
{
    std::vector<GridReference<T>> refs;
    using iterator = typename std::vector<GridReference<T>>::iterator;
    iterator begin() { return refs.begin(); }
    iterator end() { return refs.end(); }
};
// Grid residents around the caster: in world, or removed from it and still on
// the map's remove list.
GridRefManager<Creature> g_gridCreatures;
GridRefManager<Player> g_gridPlayers;
float g_searchRadius = 0.0f;
struct Cell
{
    template <class Visitor>
    static void VisitAllObjects(WorldObject const*, Visitor& visitor, float radius)
    {
        g_searchRadius = radius;
        visitor.Visit(g_gridPlayers);
        visitor.Visit(g_gridCreatures);
    }
};

struct SpellCastTargets
{
    WorldObject* m_objectTarget = nullptr;
    ObjectGuid m_objectTargetGUID;
    WorldObject* GetObjectTarget() const { return m_objectTarget; }
    ObjectGuid GetUnitTargetGUID() const { return m_objectTargetGUID.IsUnit() ? m_objectTargetGUID : ObjectGuid{}; }
    Unit* GetUnitTarget() const { return m_objectTarget ? m_objectTarget->ToUnit() : nullptr; }
};
struct Spell
{
    WorldObject* caster = nullptr;
    SpellInfo const* info = nullptr;
    SpellCastTargets m_targets;
    WorldObject* GetCaster() const { return caster; }
    SpellInfo const* GetSpellInfo() const { return info; }
};
'''

HELPER_REPLAY = r'''
Creature* NewCreature(uint64 raw)
{
    Creature* creature = new Creature();
    creature->guid.raw = raw;
    creature->map = &g_map;
    return creature;
}
Player* NewPlayer(uint64 raw)
{
    Player* player = new Player();
    player->guid.raw = raw;
    player->guid.player = true;
    player->map = &g_map;
    return player;
}
void InWorld(Unit* unit) { g_store[unit->guid.raw] = unit; }
void InGrid(Creature* creature) { g_gridCreatures.refs.push_back({creature}); }
void Delete(WorldObject* object)
{
    g_store.erase(object->guid.raw);
    g_connected.erase(object->guid.raw);
    auto& refs = g_gridCreatures.refs;
    refs.erase(std::remove_if(refs.begin(), refs.end(),
        [object](GridReference<Creature> const& ref) { return ref.source == object; }), refs.end());
#ifdef REPLAY_FREE_TARGETS
    delete object;
#else
    object->destroyed = true;
#endif
}
Spell* Aim(WorldObject* caster, WorldObject* target, ObjectGuid guid)
{
    Spell* spell = new Spell();
    spell->caster = caster;
    spell->m_targets.m_objectTarget = target;
    spell->m_targets.m_objectTargetGUID = guid;
    return spell;
}
void Report(char const* name, Spell* spell, Unit* legacy, bool live)
{
    Unit* resolved = BotSpellCastTarget::UnitTarget(spell);
    std::printf("{\"case\":\"%s\",\"live\":%s,\"same_as_legacy\":%s,\"null\":%s}\n", name,
        live ? "true" : "false", resolved == legacy ? "true" : "false", resolved ? "false" : "true");
}

int main()
{
    Player* bot = NewPlayer(11003007);
    InWorld(bot);
    g_connected[bot->guid.raw] = bot;

    Creature* boss = NewCreature(0xF13000A1);  // in world in the bot's map
    InWorld(boss); InGrid(boss);
    Spell* spell = Aim(bot, boss, boss->guid);
    Report("creature_in_world", spell, spell->m_targets.GetUnitTarget(), true);

    Creature* pet = NewCreature(0xF14000B2);  // removed from world, still on the remove list
    InGrid(pet);
    spell = Aim(bot, pet, pet->guid);
    Report("creature_on_remove_list", spell, spell->m_targets.GetUnitTarget(), true);
    std::printf("{\"case\":\"search_radius\",\"yards\":%.1f}\n", g_searchRadius);

    Player* paladin = NewPlayer(11003005);  // same map, in world
    InWorld(paladin); g_connected[paladin->guid.raw] = paladin;
    spell = Aim(bot, paladin, paladin->guid);
    Report("player_in_world", spell, spell->m_targets.GetUnitTarget(), true);

    Player* ghost = NewPlayer(11003002);  // released: far-teleport transit / another map
    g_connected[ghost->guid.raw] = ghost;
    spell = Aim(bot, ghost, ghost->guid);
    Report("player_in_transit", spell, spell->m_targets.GetUnitTarget(), true);

    spell = Aim(bot, bot, bot->guid);
    Report("self", spell, spell->m_targets.GetUnitTarget(), true);

    Creature* chest = NewCreature(0xF11000C3);  // a game object target
    chest->isUnit = false;
    chest->guid.unit = false;
    spell = Aim(bot, chest, chest->guid);
    Report("object_target", spell, spell->m_targets.GetUnitTarget(), true);

    spell = Aim(bot, nullptr, boss->guid);  // pointer refresh found nothing
    Report("no_cached_target", spell, nullptr, true);

    // The documented residual: a live creature is not proven for a caster
    // without a map. No bot decision site reads a spell of such a caster.
    Unit* mapless = NewCreature(0xF14000D4);
    mapless->map = nullptr;
    spell = Aim(mapless, pet, pet->guid);
    Report("mapless_caster_creature", spell, spell->m_targets.GetUnitTarget(), true);
    spell = Aim(mapless, ghost, ghost->guid);
    Report("mapless_caster_player", spell, ghost, true);

    // Deleted targets: never read, always absent.
    Creature* despawned = NewCreature(0xF13000E5);
    InWorld(despawned); InGrid(despawned);
    spell = Aim(bot, despawned, despawned->guid);
    Delete(despawned);
    Report("creature_deleted", spell, nullptr, false);

    Player* loggedOut = NewPlayer(11003001);
    InWorld(loggedOut); g_connected[loggedOut->guid.raw] = loggedOut;
    spell = Aim(bot, loggedOut, loggedOut->guid);
    Delete(loggedOut);
    Report("player_deleted", spell, nullptr, false);

    // The same character logged in again: a new object with the old GUID.
    Player* relogged = NewPlayer(11003001);
    InWorld(relogged); g_connected[relogged->guid.raw] = relogged;
    Report("player_deleted_and_relogged", spell, nullptr, false);

    // A new creature at a deleted target's address (another GUID).
    Creature* reused = NewCreature(0xF13000F6);
    InWorld(reused); InGrid(reused);
    spell = Aim(bot, reused, ObjectGuid{0xF13000E5, false});
    Report("address_reused_by_another_guid", spell, nullptr, false);
    return g_poisoned ? 3 : 0;
}
'''

EXPECTED_HELPER = [
    {"case": "creature_in_world", "live": True, "same_as_legacy": True, "null": False},
    {"case": "creature_on_remove_list", "live": True, "same_as_legacy": True, "null": False},
    {"case": "search_radius", "yards": 105.0},
    {"case": "player_in_world", "live": True, "same_as_legacy": True, "null": False},
    {"case": "player_in_transit", "live": True, "same_as_legacy": True, "null": False},
    {"case": "self", "live": True, "same_as_legacy": True, "null": False},
    {"case": "object_target", "live": True, "same_as_legacy": True, "null": True},
    {"case": "no_cached_target", "live": True, "same_as_legacy": True, "null": True},
    {"case": "mapless_caster_creature", "live": True, "same_as_legacy": False, "null": True},
    {"case": "mapless_caster_player", "live": True, "same_as_legacy": True, "null": False},
    {"case": "creature_deleted", "live": False, "same_as_legacy": True, "null": True},
    {"case": "player_deleted", "live": False, "same_as_legacy": True, "null": True},
    {"case": "player_deleted_and_relogged", "live": False, "same_as_legacy": True, "null": True},
    {"case": "address_reused_by_another_guid", "live": False, "same_as_legacy": True, "null": True},
]


def _compile(tmp_path: Path, name: str, program: str, flags: list[str]) -> subprocess.CompletedProcess[str]:
    source = tmp_path / f"{name}.cpp"
    source.write_text(program, encoding="utf-8")
    return subprocess.run(["c++", "-std=c++17", "-O0", "-g", "-Wall", "-Wextra", "-Werror", *flags,
                           str(source), "-o", str(tmp_path / name)], capture_output=True, text=True)


def _run(tmp_path: Path, name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(tmp_path / name)], capture_output=True, text=True,
                          env={"ASAN_OPTIONS": "detect_leaks=0"})


def _asan_flags(built: subprocess.CompletedProcess[str]) -> None:
    if built.returncode != 0 and "asan" in built.stderr.lower():
        pytest.skip("AddressSanitizer runtime unavailable")


def test_helper_returns_the_legacy_pointer_for_live_targets_only(tmp_path):
    program = STUBS + _helper_namespace() + HELPER_REPLAY
    built = _compile(tmp_path, "poisoned", program, [])
    assert built.returncode == 0, built.stderr
    run = _run(tmp_path, "poisoned")
    assert run.returncode == 0, "a deleted target was read: " + run.stdout + run.stderr
    assert [json.loads(line) for line in run.stdout.splitlines()] == EXPECTED_HELPER


def test_helper_never_reads_freed_targets_under_asan(tmp_path):
    program = STUBS + _helper_namespace() + HELPER_REPLAY
    built = _compile(tmp_path, "freed", program,
                     ["-DREPLAY_FREE_TARGETS", "-fsanitize=address", "-fno-omit-frame-pointer"])
    _asan_flags(built)
    assert built.returncode == 0, built.stderr
    run = _run(tmp_path, "freed")
    assert "AddressSanitizer" not in run.stderr, run.stderr
    assert run.returncode == 0, run.stderr
    assert [json.loads(line) for line in run.stdout.splitlines()] == EXPECTED_HELPER


def _contamination_guards(legacy: bool) -> str:
    source = CONTAMINATION.read_text(encoding="utf-8")
    guards = _block(source, re.search(r"^namespace\n\{\n", source, re.M).start())
    if legacy:
        guards = guards.replace("BotSpellCastTarget::UnitTarget(current)", "current->m_targets.GetUnitTarget()")
    return guards


SITE_STUBS = r'''
namespace BotRaidAreaAuthority
{
bool IsProtectedEncounterTarget(uint64, uint32 entry, uint32, uint64) { return entry == 43296; }
}
bool SpellHasHostileMultiTargetSemantics(SpellInfo const* info) { return info && info->multiTarget; }
Unit const* g_nearbyCenter = nullptr;
bool HasNearbyProtectedEncounterTarget(Player*, Unit const* center)
{
    g_nearbyCenter = center;
    return center && !center->guid.player && center->entry == 41378;
}
'''

SITE_REPLAY = r'''
struct Case { char const* name; bool multiTarget; bool autoRepeat; uint32 entry; bool player; bool onRemoveList; bool deleted; };

int main()
{
    Player* bot = new Player();
    bot->guid = ObjectGuid{11003003, true};
    bot->map = &g_map;
    g_store[bot->guid.raw] = bot;
    g_connected[bot->guid.raw] = bot;
    Case const cases[] = {
        {"protected_in_world", false, false, 43296, false, false, false},
        {"protected_on_remove_list", false, false, 43296, false, true, false},
        {"protected_autorepeat", false, true, 43296, false, false, false},
        {"area_spell_near_protected", true, false, 41378, false, false, false},
        {"area_spell_on_remove_list", true, false, 41378, false, true, false},
        {"area_spell_clear", true, false, 42764, false, false, false},
        {"friendly_player_heal", false, false, 0, true, false, false},
#ifndef REPLAY_LEGACY
        {"protected_deleted", false, false, 43296, false, false, true},
        {"area_spell_target_deleted", true, false, 41378, false, false, true},
#endif
    };
    uint64 next = 0xF1300100;
    SpellInfo single{1, false};
    SpellInfo area{2, true};
    std::function<bool(Creature const*)> immediateNextEncounter = [](Creature const*) { return false; };
    for (Case const& c : cases)
    {
        Unit* target = c.player ? static_cast<Unit*>(new Player()) : static_cast<Unit*>(new Creature());
        target->guid = ObjectGuid{c.player ? 11003005 : next++, c.player};
        uint64 const raw = target->guid.raw;
        target->entry = c.entry;
        target->map = &g_map;
        if (c.player)
            g_connected[target->guid.raw] = static_cast<Player*>(target);
        if (!c.onRemoveList)
            g_store[target->guid.raw] = target;
        if (!c.player)
            g_gridCreatures.refs.push_back({static_cast<Creature*>(target)});
        Spell spell;
        spell.caster = bot;
        spell.info = c.multiTarget ? &area : &single;
        spell.m_targets.m_objectTarget = target;
        spell.m_targets.m_objectTargetGUID = target->guid;
        CurrentSpellTypes const type = c.autoRepeat ? CURRENT_AUTOREPEAT_SPELL : CURRENT_GENERIC_SPELL;
        bot->current[type] = &spell;
        bot->interrupted.clear();
        g_nearbyCenter = nullptr;
        if (c.deleted)
        {
            g_store.erase(raw);
            g_gridCreatures.refs.clear();
#ifdef REPLAY_FREE_TARGETS
            delete target;
#else
            target->destroyed = true;
#endif
        }
        BotWorldPopulationMgrValidationRoute::GuardCurrentOffense(bot, bot, immediateNextEncounter);
        char const* center = !g_nearbyCenter ? "none" : g_nearbyCenter == bot ? "caster" : "target";
        std::printf("{\"case\":\"%s\",\"interrupted\":%s,\"nearby_center\":\"%s\"}\n", c.name,
            bot->interrupted.empty() ? "false" : "true", center);
        bot->current[type] = nullptr;
        g_store.erase(raw);
        g_gridCreatures.refs.clear();
    }
    return g_poisoned ? 3 : 0;
}
'''

EXPECTED_SITE = [
    {"case": "protected_in_world", "interrupted": True, "nearby_center": "none"},
    {"case": "protected_on_remove_list", "interrupted": True, "nearby_center": "none"},
    {"case": "protected_autorepeat", "interrupted": True, "nearby_center": "none"},
    {"case": "area_spell_near_protected", "interrupted": True, "nearby_center": "target"},
    {"case": "area_spell_on_remove_list", "interrupted": True, "nearby_center": "target"},
    {"case": "area_spell_clear", "interrupted": False, "nearby_center": "target"},
    {"case": "friendly_player_heal", "interrupted": False, "nearby_center": "none"},
]


def _site_program(legacy: bool) -> str:
    return (STUBS + _helper_namespace() + SITE_STUBS
            + "namespace BotWorldPopulationMgrValidationRoute\n{\n" + _contamination_guards(legacy) + "\n}\n"
            + SITE_REPLAY)


def test_contamination_guard_decides_exactly_as_before_for_live_targets(tmp_path):
    rows = {}
    for name, legacy in (("legacy", True), ("patched", False)):
        flags = ["-DREPLAY_LEGACY"] if legacy else []
        built = _compile(tmp_path, name, _site_program(legacy), flags)
        assert built.returncode == 0, built.stderr
        run = _run(tmp_path, name)
        assert run.returncode == 0, run.stdout + run.stderr
        rows[name] = [json.loads(line) for line in run.stdout.splitlines()]
    assert rows["legacy"] == EXPECTED_SITE
    assert rows["patched"][:len(EXPECTED_SITE)] == rows["legacy"]
    # A deleted target is absent: the single-target guard has nothing to
    # protect and the area probe falls back to the caster, as for no target.
    assert rows["patched"][len(EXPECTED_SITE):] == [
        {"case": "protected_deleted", "interrupted": False, "nearby_center": "none"},
        {"case": "area_spell_target_deleted", "interrupted": False, "nearby_center": "caster"},
    ]


def test_contamination_guard_never_reads_a_freed_target_under_asan(tmp_path):
    built = _compile(tmp_path, "site_freed", _site_program(False),
                     ["-DREPLAY_FREE_TARGETS", "-fsanitize=address", "-fno-omit-frame-pointer"])
    _asan_flags(built)
    assert built.returncode == 0, built.stderr
    run = _run(tmp_path, "site_freed")
    assert "AddressSanitizer" not in run.stderr, run.stderr
    assert run.returncode == 0, run.stderr
