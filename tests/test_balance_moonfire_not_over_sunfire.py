"""DPS-066 part 3: the maintained Balance Moonfire must not overwrite Sunfire.

When Solar Eclipse ends, the Moonfire `dot` row (maintain aura 8921) saw no
Moonfire on Magmaw and recast it over the still-ticking Sunfire 93402. The two
spells are exclusive from the same caster (spell_group 1123, stack rule 2), so
the recast replaced the Sunfire: two wasted GCDs per kill, about 0.3k DPS.
"""
from __future__ import annotations

import hashlib
import sqlite3
import struct
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_24_00_balance_moonfire_not_over_sunfire.sql"
MOVING_MIGRATION = ROOT / "sql/custom/world/2026_09_23_20_balance_moving_moonfire.sql"
CANDIDATES = ROOT / "src/server/game/Bots/BotClassSpecActionProfileCandidates.cpp"
RESOLVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
TAG = ",moonfire_not_over_sunfire_20260924"

MOONFIRE = 8921
SUNFIRE = 93402

PROFILES = [
    # id, class_id, spec_tag, role, enabled
    (290, 11, "balance_druid", "dps", 1),
    (291, 11, "balance_druid", "dps", 0),  # disabled duplicate profile
    (292, 11, "balance_druid", "healer", 1),
    (250, 11, "restoration_druid", "healer", 1),
    (263, 8, "fire", "dps", 1),
]

ACTIONS = [
    # id, profile_id, sort_order, spell_id, category, mechanic_tags,
    # forbidden_target_aura, forbidden_owned_target_aura, maintain_aura_id,
    # refresh_aura_below_ms, requires_moving, enabled.
    # Production profile 290 rows first (world DB, 2026-09-24).
    (2540, 290, 10, MOONFIRE, "dot", "moonfire,dot", 0, 0, MOONFIRE, 3000, 0, 1),
    (3556, 290, 15, SUNFIRE, "dot", "sunfire,dot,solar_eclipse,pinned_apl", 0, 0, SUNFIRE, 3000, 0, 1),
    (3617, 290, 140, MOONFIRE, "builder", "moonfire,moving_filler_20260923", 0, 0, 0, 0, 1, 1),
    (3618, 290, 141, SUNFIRE, "builder", "sunfire,moving_filler_20260923", 0, 0, 0, 0, 1, 1),
    (2056, 250, 40, MOONFIRE, "dot", "moonfire,healer_dps", 0, 0, MOONFIRE, 3000, 0, 1),
    # Synthetic scope probes.
    (9001, 290, 11, MOONFIRE, "dot", "moonfire,dot,disabled_duplicate", 0, 0, MOONFIRE, 3000, 0, 0),
    (9002, 290, 12, MOONFIRE, "dot", "moonfire,explicit_gate", 12345, 0, MOONFIRE, 3000, 0, 1),
    (9003, 290, 13, MOONFIRE, "dot", "moonfire,moving_dot", 0, 0, MOONFIRE, 3000, 1, 1),
    (9101, 291, 10, MOONFIRE, "dot", "moonfire,dot", 0, 0, MOONFIRE, 3000, 0, 1),
    (9201, 292, 10, MOONFIRE, "dot", "moonfire,dot", 0, 0, MOONFIRE, 3000, 0, 1),
    (9301, 263, 10, MOONFIRE, "dot", "moonfire,dot", 0, 0, MOONFIRE, 3000, 0, 1),
]
# The production Moonfire dot row, and the disabled duplicate action inside the
# same enabled profile (the DPS-052/DPS-064 precedent).
EXPECTED_CHANGED = {2540, 9001}


def _database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript(
        """
        CREATE TABLE bot_rotation_profile (
            id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL,
            spec_tag TEXT NOT NULL, role TEXT NOT NULL, enabled INTEGER NOT NULL);
        CREATE TABLE bot_rotation_action (
            id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL,
            sort_order INTEGER NOT NULL, spell_id INTEGER NOT NULL,
            category TEXT NOT NULL, mechanic_tags TEXT NOT NULL,
            forbidden_target_aura INTEGER NOT NULL,
            forbidden_owned_target_aura INTEGER NOT NULL,
            maintain_aura_id INTEGER NOT NULL,
            refresh_aura_below_ms INTEGER NOT NULL,
            requires_moving INTEGER NOT NULL, enabled INTEGER NOT NULL);
        """
    )
    db.executemany("INSERT INTO bot_rotation_profile VALUES (?, ?, ?, ?, ?)", PROFILES)
    db.executemany("INSERT INTO bot_rotation_action VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   ACTIONS)
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


def test_forward_gates_only_the_balance_moonfire_dot_row() -> None:
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
        assert old[3] == MOONFIRE and old[4] == "dot" and old[6] == 0
        assert new[6] == SUNFIRE
        assert new[5] == old[5] + TAG
        # Only forbidden_target_aura and the reversal tag change: the owned
        # gate stays zero, so the maintain/refresh branch keeps running.
        assert new[:5] + new[7:] == old[:5] + old[7:]
        assert new[7] == 0 and new[8] == MOONFIRE and new[9] == 3000
    assert changed == EXPECTED_CHANGED
    rows = {row[0]: row for row in after_actions}
    # Sunfire on Solar entry and both moving-only filler rows are untouched.
    for row_id in (3556, 3617, 3618):
        assert rows[row_id] == next(a for a in before_actions if a[0] == row_id)
    assert "moving_filler_20260923" not in rows[2540][5]


def test_moving_filler_row_is_the_one_from_the_previous_migration() -> None:
    moving = MOVING_MIGRATION.read_text(encoding="utf-8")
    assert "'builder', 'moonfire,moving_filler_20260923'" in moving
    forward = _forward().split("-- BEGIN REVERSE MIGRATION")[0]
    assert "AND `category` = 'dot'" in forward
    assert "AND `requires_moving` = 0" in forward
    assert "forbidden_owned_target_aura` =" not in forward
    assert "`forbidden_target_aura` = 93402" in forward


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


def test_pinned_dbc_moonfire_and_sunfire_facts() -> None:
    folder = ROOT / "data/dbc/enUS"
    paths = [folder / name for name in ("Spell.dbc", "SpellEffect.dbc", "SpellDuration.dbc")]
    if not all(path.exists() for path in paths):
        pytest.skip("local 4.3.4 DBC extraction is not present")
    spells, spell_fields, spell_sha = _dbc(paths[0])
    effects, effect_fields, effect_sha = _dbc(paths[1])
    durations, _, duration_sha = _dbc(paths[2])
    assert spell_sha == "088a14963d3f81a10963702c760215f49ff73132bea751306c57aae0dae9f39f"
    assert effect_sha == "e3d9a470bbcb5cea4e3f2947911a908b816cc60e6ffeb9f70b4cfb123bad6252"
    assert duration_sha == "284e22a843ce4cb85604cd037d228f55a757ea3a608e59e3a5f30cbba02bc727"
    duration = {}
    for row in durations:
        entry, base, _, _ = struct.unpack("<Iiii", row[:16])
        duration[entry] = base
    spell = {}
    for row in spells:
        values = struct.unpack(f"<{spell_fields}I", row[:spell_fields * 4])
        if values[0] in (MOONFIRE, SUNFIRE):
            spell[values[0]] = (values[13], values[15])  # DurationIndex, RangeIndex
    effect = {}
    for row in effects:
        values = struct.unpack(f"<{effect_fields}I", row[:effect_fields * 4])
        if values[24] in (MOONFIRE, SUNFIRE):
            # Effect, EffectAura, EffectAuraPeriod by EffectIndex.
            effect[(values[24], values[25])] = (values[1], values[3], values[4])
    for spell_id in (MOONFIRE, SUNFIRE):
        assert spell[spell_id] == (29, 5)
        assert duration[29] == 12000
        assert effect[(spell_id, 0)] == (6, 3, 2000)  # APPLY_AURA, PERIODIC_DAMAGE
        assert effect[(spell_id, 1)][0] == 2  # SCHOOL_DAMAGE


def _segment(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    return source[begin:source.index(end, begin)]


def _gate_replay(tmp_path: Path, rows: dict[int, tuple]) -> None:
    source = CANDIDATES.read_text(encoding="utf-8")
    maintain_helper = _segment(source, "bool MaintainedAuraBlocksRefresh(", "\nbool HasMechanicTag(")
    tag_helper = _segment(source, "bool HasMechanicTag(", "\nbool IsPostPeriodicTickInterruptWindow(")
    gates = _segment(source, "    if (spell.RequiredTargetAura && (!target",
                     "\n\n    uint8 comboPoints")
    assert "forbidden_target_aura_active" in gates
    assert "spell.MaintainAuraId && !spell.RequiredOwnedTargetAura\n        && !spell.ForbiddenOwnedTargetAura" in gates

    def spell(row: tuple, owned_gate: int | None = None) -> str:
        forbidden_owned = row[7] if owned_gate is None else owned_gate
        return (f"Spell{{0,{row[6]}u,\"{row[5]}\",0,0,{forbidden_owned}u,"
                f"{row[8]}u,{row[9]}u}}")

    moonfire_before = next(a for a in ACTIONS if a[0] == 2540)
    moonfire_after, sunfire_row, moving_row = rows[2540], rows[3556], rows[3617]
    cpp = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <map>
#include <string>
typedef uint32_t uint32; typedef int32_t int32; typedef uint8_t uint8;
enum Powers { POWER_HOLY_POWER = 9, POWER_SOUL_SHARDS = 7 };
struct Guid { uint64_t raw = 0; bool operator==(Guid o) const { return raw == o.raw; } };
struct Aura { int32 duration = 0; uint8 stacks = 1; Guid caster;
  int32 GetDuration() const { return duration; } uint8 GetStackAmount() const { return stacks; } };
struct Unit {
  std::map<uint32, Aura> auras;
  bool HasAura(uint32 id) const { return auras.count(id) != 0; }
  bool HasAura(uint32 id, Guid caster) const { auto a = GetAura(id, caster); return a != nullptr; }
  Aura const* GetAura(uint32 id) const { auto it = auras.find(id); return it == auras.end() ? nullptr : &it->second; }
  Aura const* GetAura(uint32 id, Guid caster) const { auto a = GetAura(id); return a && a->caster == caster ? a : nullptr; }
};
struct Player : Unit { Guid guid{7}; Guid GetGUID() const { return guid; } uint32 GetPower(Powers) const { return 0; } };
struct Spell { uint32 RequiredTargetAura; uint32 ForbiddenTargetAura; std::string MechanicTags;
  uint32 RequiredOwnedTargetAura; uint32 MinOwnedTargetAuraRemainingMs; uint32 ForbiddenOwnedTargetAura;
  uint32 MaintainAuraId; uint32 RefreshAuraBelowMs; };
''' + maintain_helper + "\n" + tag_helper + r'''
char const* Gate(Spell const& spell, Unit const* target, Player const* bot) {
''' + gates + r'''
  return nullptr;
}
static bool Is(char const* got, char const* want) { return want ? got && !std::strcmp(got, want) : !got; }
int main() {
  Player bot;
  Unit sunfireLive; sunfireLive.auras[93402] = Aura{9000, 1, bot.GetGUID()};
  Unit bare;
  Unit moonfireLive; moonfireLive.auras[8921] = Aura{9000, 1, bot.GetGUID()};
  Unit moonfireFading; moonfireFading.auras[8921] = Aura{2000, 1, bot.GetGUID()};
  Spell const before = ''' + spell(moonfire_before) + r''';
  Spell const after = ''' + spell(moonfire_after) + r''';
  // Before: Solar ended, Sunfire still ticking, no Moonfire -> Moonfire recast
  // (the overwrite this migration removes).
  assert(Is(Gate(before, &sunfireLive, &bot), nullptr));
  // After: held while Sunfire is live, cast once it expires.
  assert(Is(Gate(after, &sunfireLive, &bot), "forbidden_target_aura_active"));
  assert(Is(Gate(after, &bare, &bot), nullptr));
  // The maintain/refresh branch is unchanged.
  assert(Is(Gate(after, &moonfireLive, &bot), "maintain_aura_active"));
  assert(Is(Gate(after, &moonfireFading, &bot), nullptr));
  // Counterfactual: the owned column would disable the maintain branch, so a
  // live 9 s Moonfire would be recast every GCD.
  Spell const owned = ''' + spell(moonfire_before, SUNFIRE) + r''';
  assert(Is(Gate(owned, &moonfireLive, &bot), nullptr));
  // Sunfire on Solar entry and the moving-only Moonfire row are unchanged.
  Spell const sunfire = ''' + spell(sunfire_row) + r''';
  assert(Is(Gate(sunfire, &sunfireLive, &bot), "maintain_aura_active"));
  assert(Is(Gate(sunfire, &bare, &bot), nullptr));
  Spell const moving = ''' + spell(moving_row) + r''';
  assert(Is(Gate(moving, &sunfireLive, &bot), nullptr));
}
'''
    path = tmp_path / "moonfire_not_over_sunfire.cpp"
    path.write_text(cpp, encoding="utf-8")
    binary = tmp_path / "moonfire_not_over_sunfire"
    result = subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                             "-Wno-unused-parameter", str(path), "-o", str(binary)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr


def test_migrated_rows_through_the_actual_candidate_gates(tmp_path: Path) -> None:
    db = _database()
    db.executescript(_forward())
    rows = {row[0]: row for row in _state(db)[1]}
    _gate_replay(tmp_path, rows)
    # The resolver repeats the same plain gate on the action target, and the
    # Eclipse gate still owns Solar Moonfire/Sunfire direction.
    resolver = RESOLVER.read_text(encoding="utf-8")
    assert ("if (candidate.Profile.ForbiddenTargetAura && "
            "actionTarget->HasAura(candidate.Profile.ForbiddenTargetAura))") in resolver
    assert "(candidate.SpellId == 8921 && solarEclipse)" in resolver
