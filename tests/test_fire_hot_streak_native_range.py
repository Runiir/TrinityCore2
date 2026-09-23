"""DPS-064/DPS-044: native 40 yd caps for Pyroblast!, Flame Orb and Scorch.

The fixed Magmaw parasite baiter holds a lane anchor 35.043 yd from Magmaw.
The stale 35 yd action caps silently dropped Hot Streak Pyroblast!, Flame Orb
and Scorch there while 40 yd Fireball kept resolving.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import struct
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_23_60_fire_hot_streak_native_range.sql"
RESOLVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
TAG = ",fire_native_range_20260923"
SAFETY = ",magmaw_ranged_safety_20260918"
BAITER_ANCHOR_DISTANCE = 35.043

PYROBLAST_PROC = 92315
FLAME_ORB = 82731
SCORCH = 2948
FIRE_BLAST = 2136
BLAST_WAVE = 11113
FLAMESTRIKE = 2120
COUNTERSPELL = 2139
CHANGED_SPELLS = (PYROBLAST_PROC, FLAME_ORB, SCORCH)

# Pinned 4.3.4 client data: spell -> (RangeIndex, native maximum yards).
SPELL_DBC_SHA256 = "088a14963d3f81a10963702c760215f49ff73132bea751306c57aae0dae9f39f"
SPELL_RANGE_DBC_SHA256 = "46fc3e766ff03f621a7641e2e440886475714f1304721c41e1e767d15ba87efd"
NATIVE_RANGE = {
    133: (5, 40.0),
    44457: (5, 40.0),
    11129: (5, 40.0),
    PYROBLAST_PROC: (5, 40.0),
    FLAME_ORB: (5, 40.0),
    SCORCH: (5, 40.0),
    BLAST_WAVE: (5, 40.0),
    FLAMESTRIKE: (5, 40.0),
    COUNTERSPELL: (5, 40.0),
    FIRE_BLAST: (4, 30.0),
}

PROFILES = [
    # id, class_id, spec_tag, role, min_range, max_range, enabled, version
    (263, 8, "fire", "dps", 9, 40, 1, 3),
    (264, 8, "fire", "dps", 0, 35, 0, 3),  # disabled Fire profile
    (285, 8, "arcane_mage", "dps", 0, 35, 1, 3),
    (286, 8, "frost_mage", "dps", 0, 35, 1, 2),
    (300, 3, "marksmanship", "dps", 5, 35, 1, 17),
    (302, 8, "fire", "tank", 0, 35, 1, 4),
]

ACTIONS = [
    # id, profile_id, sort_order, spell_id, category, mechanic_tags,
    # min_range, max_range, enabled.  Production profile 263 rows first.
    (2010, 263, 10, COUNTERSPELL, "interrupt", "counterspell,interrupt" + SAFETY, 9, 35, 1),
    (2168, 263, 15, BLAST_WAVE, "aoe", "blast_wave,aoe,on_cooldown" + SAFETY, 9, 35, 1),
    (2159, 263, 18, FLAME_ORB, "offensive_cooldown", "flame_orb,on_cooldown" + SAFETY, 9, 35, 1),
    (2011, 263, 20, 44457, "dot", "living_bomb,maintain_debuff" + SAFETY, 9, 40, 1),
    (2014, 263, 25, 11129, "spender", "combustion,ignite_dot_window" + SAFETY, 9, 40, 1),
    (2012, 263, 30, PYROBLAST_PROC, "spender", "pyroblast,hot_streak_only,instant_proc" + SAFETY, 9, 35, 1),
    (2013, 263, 40, FLAMESTRIKE, "aoe", "flamestrike,aoe" + SAFETY, 9, 35, 1),
    (2016, 263, 50, 133, "builder", "fireball,filler" + SAFETY, 9, 40, 1),
    (2132, 263, 55, SCORCH, "resource_generator",
     "scorch,firestarter,moving_filler,resource_fallback" + SAFETY, 9, 35, 1),
    (3607, 263, 56, SCORCH, "resource_generator",
     "scorch,firestarter,moving_filler,movement_only" + SAFETY, 9, 35, 1),
    (2015, 263, 60, FIRE_BLAST, "aoe", "fire_blast,impact,dot_spread,aoe" + SAFETY, 9, 35, 1),
    (3597, 263, 61, FIRE_BLAST, "spender", "fire_blast,single_target_fallback,instant" + SAFETY, 9, 35, 1),
    # A disabled duplicate action in the enabled profile follows DPS-052.
    (9001, 263, 31, PYROBLAST_PROC, "spender", "pyroblast,disabled_duplicate", 0, 35, 0),
    # Rows that already carry a different explicit cap stay untouched.
    (9002, 263, 32, PYROBLAST_PROC, "spender", "pyroblast,explicit_forty", 9, 40, 1),
    (9003, 263, 57, SCORCH, "resource_generator", "scorch,explicit_thirty", 9, 30, 1),
    # Same spells outside enabled Fire DPS profiles stay untouched.
    (9101, 264, 30, PYROBLAST_PROC, "spender", "pyroblast", 0, 35, 1),
    (2501, 285, 10, COUNTERSPELL, "interrupt", "counterspell,interrupt", 0, 35, 1),
    (9201, 285, 55, SCORCH, "resource_generator", "scorch", 0, 35, 1),
    (9301, 286, 30, PYROBLAST_PROC, "spender", "pyroblast", 0, 35, 1),
    (9401, 302, 30, PYROBLAST_PROC, "spender", "pyroblast", 0, 35, 1),
    (9402, 302, 18, FLAME_ORB, "offensive_cooldown", "flame_orb", 0, 35, 1),
    (9501, 300, 55, SCORCH, "resource_generator", "scorch", 5, 35, 1),
]
EXPECTED_CHANGED = {2159, 2012, 2132, 3607, 9001}


def _database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript(
        """
        CREATE TABLE bot_rotation_profile (
            id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL,
            spec_tag TEXT NOT NULL, role TEXT NOT NULL,
            min_range REAL NOT NULL, max_range REAL NOT NULL,
            enabled INTEGER NOT NULL, version INTEGER NOT NULL);
        CREATE TABLE bot_rotation_action (
            id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL,
            sort_order INTEGER NOT NULL, spell_id INTEGER NOT NULL,
            category TEXT NOT NULL, mechanic_tags TEXT NOT NULL,
            min_range REAL NOT NULL, max_range REAL NOT NULL,
            enabled INTEGER NOT NULL);
        """
    )
    db.executemany("INSERT INTO bot_rotation_profile VALUES (?, ?, ?, ?, ?, ?, ?, ?)", PROFILES)
    db.executemany("INSERT INTO bot_rotation_action VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", ACTIONS)
    return db


def _state(db: sqlite3.Connection) -> tuple[list[tuple], list[tuple]]:
    return (
        db.execute("SELECT * FROM bot_rotation_profile ORDER BY id").fetchall(),
        db.execute("SELECT * FROM bot_rotation_action ORDER BY id").fetchall(),
    )


def _forward() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _reverse() -> str:
    lines = _forward().splitlines()
    start = lines.index("-- BEGIN REVERSE MIGRATION")
    end = lines.index("-- END REVERSE MIGRATION")
    body = lines[start + 1:end]
    assert body and all(line.startswith("-- ") for line in body)
    return "\n".join(line[3:] for line in body)


def test_forward_lifts_only_stale_native_forty_caps_in_enabled_fire_profiles() -> None:
    db = _database()
    before_profiles, before_actions = _state(db)
    db.executescript(_forward())
    after_profiles, after_actions = _state(db)

    assert after_profiles == before_profiles
    changed = set()
    for old, new in zip(before_actions, after_actions):
        if old == new:
            continue
        changed.add(old[0])
        assert old[3] in CHANGED_SPELLS and old[7] == 35.0
        assert new[7] == 40.0
        assert new[5] == old[5] + TAG
        assert new[:5] + new[6:7] + new[8:] == old[:5] + old[6:7] + old[8:]
        assert struct.unpack("<f", struct.pack("<f", new[7]))[0] == new[7]
    assert changed == EXPECTED_CHANGED
    # Every changed spell is a native 40 yd spell; the cap never exceeds it.
    for row in after_actions:
        if row[0] in EXPECTED_CHANGED:
            assert row[7] == NATIVE_RANGE[row[3]][1]
    # Intentionally unchanged: native 30 yd Fire Blast and the three native
    # 40 yd rows without evidence (Blast Wave, Flamestrike, Counterspell).
    unchanged = {row[0]: row[7] for row in after_actions if row[1] == 263}
    assert [unchanged[i] for i in (2010, 2168, 2013, 2015, 3597)] == [35.0] * 5


def test_forward_replays_idempotently() -> None:
    db = _database()
    db.executescript(_forward())
    once = _state(db)
    changes = db.total_changes
    db.executescript(_forward())
    assert db.total_changes == changes
    assert _state(db) == once


def test_reverse_block_restores_the_exact_prior_state_and_replays() -> None:
    db = _database()
    original = _state(db)
    db.executescript(_forward())
    assert _state(db) != original
    db.executescript(_reverse())
    assert _state(db) == original
    changes = db.total_changes
    db.executescript(_reverse())
    assert db.total_changes == changes and _state(db) == original
    # Forward after reverse returns to the migrated state.
    db.executescript(_forward())
    migrated = _database()
    migrated.executescript(_forward())
    assert _state(db) == _state(migrated)


def test_reverse_without_forward_is_a_no_op() -> None:
    db = _database()
    original = _state(db)
    db.executescript(_reverse())
    assert db.total_changes == len(PROFILES) + len(ACTIONS)
    assert _state(db) == original


def _dbc(path: Path) -> tuple[list[bytes], int, str]:
    data = path.read_bytes()
    _, records, fields, size, _ = struct.unpack("<4s4I", data[:20])
    rows = [data[20 + i * size:20 + (i + 1) * size] for i in range(records)]
    return rows, fields, hashlib.sha256(data).hexdigest()


def test_pinned_dbc_native_ranges() -> None:
    spell_path = ROOT / "data/dbc/enUS/Spell.dbc"
    range_path = ROOT / "data/dbc/enUS/SpellRange.dbc"
    if not spell_path.exists() or not range_path.exists():
        pytest.skip("local 4.3.4 DBC extraction is not present")
    spells, fields, spell_sha = _dbc(spell_path)
    ranges, _, range_sha = _dbc(range_path)
    assert spell_sha == SPELL_DBC_SHA256
    assert range_sha == SPELL_RANGE_DBC_SHA256
    range_max = {}
    for row in ranges:
        range_id, _, _, maximum, friendly_max, flags = struct.unpack("<I4fI", row[:24])
        range_max[range_id] = (maximum, friendly_max, flags)
    range_index = {}
    for row in spells:
        values = struct.unpack(f"<{fields}I", row[:fields * 4])
        if values[0] in NATIVE_RANGE:
            range_index[values[0]] = values[15]  # SpellEntry::RangeIndex
    for spell_id, (index, maximum) in NATIVE_RANGE.items():
        assert range_index[spell_id] == index
        assert range_max[index] == (maximum, maximum, 0)


def _resolver_segment(source: str, start: str, end: str, tail: int = 0) -> str:
    begin = source.index(start)
    return source[begin:source.index(end, begin) + tail]


def test_migrated_rows_through_actual_resolver_range_envelope(tmp_path: Path) -> None:
    db = _database()
    before = {row[0]: row for row in _state(db)[1]}
    db.executescript(_forward())
    after = {row[0]: row for row in _state(db)[1]}
    source = RESOLVER.read_text(encoding="utf-8")
    native = _resolver_segment(source, "    auto effectiveSpellMaxRange =", "\n    };", 7)
    configured = _resolver_segment(source, "        float maxRange = candidate.Profile.MaxRange",
                                   "        if (candidate.Profile.RequiresMeleeRange")
    maximum = _resolver_segment(source, "        if (maxRange > 0.0f && distance > maxRange)",
                                "        if (deferLavaBurstMovementRejection)")

    cases = []
    for row_id in sorted(after):
        old, new = before[row_id], after[row_id]
        if new[1] != 263 or not new[8]:
            continue
        spell, native_max = new[3], NATIVE_RANGE[new[3]][1]
        rejected = '=="max_range_exceeded"'
        admitted = ".empty()"
        # The baiter anchor, 35.043 yd from Magmaw.
        # Two 1.5 yd combat reaches extend only the native envelope.
        before_admits = min(old[7], native_max + 3.0) >= BAITER_ANCHOR_DISTANCE
        after_admits = min(new[7], native_max + 3.0) >= BAITER_ANCHOR_DISTANCE
        cases.append(f"assert(check({old[7]:.1f}f,{native_max:.1f}f,{BAITER_ANCHOR_DISTANCE}f)"
                     f"{admitted if before_admits else rejected}); // {row_id} before")
        cases.append(f"assert(check({new[7]:.1f}f,{native_max:.1f}f,{BAITER_ANCHOR_DISTANCE}f)"
                     f"{admitted if after_admits else rejected}); // {row_id} after")
        if row_id in EXPECTED_CHANGED:
            assert spell in CHANGED_SPELLS and after_admits and not before_admits
            cases.append(f"assert(check({new[7]:.1f}f,{native_max:.1f}f,40.0f).empty());")
            cases.append(f'assert(check({new[7]:.1f}f,{native_max:.1f}f,40.01f)=="max_range_exceeded");')
    cpp = r'''
#include <algorithm>
#include <cassert>
#include <string>
constexpr unsigned SPELL_RANGE_MELEE=1;
struct Range {unsigned Flags=0;};
struct SpellInfo {Range range;Range* RangeEntry=&range;float maximum=40;float GetMaxRange(bool)const{return maximum;}};
struct SpellMgr {SpellInfo info;SpellInfo const* GetSpellInfo(unsigned){return &info;}}mgr;
auto* sSpellMgr=&mgr;
struct Actor {
 float GetSpellMaxRangeForTarget(Actor*,SpellInfo const* info){return info->maximum;}
 float GetMeleeRange(Actor*)const{return 5;}float GetCombatReach()const{return 1.5f;}
};
struct Profile {float MaxRange=40;std::string TargetSelector="enemy";};
struct ResolvedCombatAction {float MinRange=0,MaxRange=0;bool RangeRecoveryRequired=false;};
struct BotActionCandidate {struct Profile Profile;unsigned SpellId=0,ResolvedSpellId=0;std::string RejectReason;};
std::string check(float cap,float nativeMax,float distance){
 Actor actor,targetUnit;auto* bot=&actor;auto* target=&targetUnit;
 mgr.info.maximum=nativeMax;Profile profile;BotActionCandidate candidate;candidate.Profile.MaxRange=cap;
 bool selfTarget=false,densityOnly=false;float minRange=0;ResolvedCombatAction action;
''' + native + "\nfor(int once=0;once<1;++once){\n" + configured + maximum + r'''
}
 (void)minRange;
 return candidate.RejectReason;
}
int main(){
''' + "\n".join(cases) + r'''
 // Fire Blast stays bound by its native 30 yd plus two 1.5 yd reaches.
 assert(check(35,30,33).empty());
 assert(check(35,30,33.01f)=="max_range_exceeded");
}
'''
    path = tmp_path / "hot_streak_range.cpp"
    path.write_text(cpp)
    binary = tmp_path / "hot_streak_range"
    result = subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(path), "-o", str(binary)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    subprocess.run([str(binary)], check=True)
