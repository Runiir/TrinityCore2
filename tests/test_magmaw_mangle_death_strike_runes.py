"""Blood tank holds Heart Strike while seized by Mangle so Death Strike gets runes.

The staged migration is replayed on an in-memory SQLite copy of the current
Blood tank Heart Strike / Death Strike rows (world DB, profile 267 v25,
2026-09-23). The native facts it relies on are pinned in source.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_23_40_blood_mangle_death_strike_runes.sql"
BOSS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_magmaw.cpp"
SHARED = BOSS.parent / "boss_magmaw_shared.h"
CANDIDATES = ROOT / "src/server/game/Bots/BotClassSpecActionProfileCandidates.cpp"

BLOOD, FROST = 267, 283
HEART_STRIKE, DEATH_STRIKE, MANGLE_SEAT = 55050, 49998, 78412


def _database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE bot_rotation_profile (
            id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL, spec_tag TEXT NOT NULL,
            role TEXT NOT NULL, version INTEGER NOT NULL, source_note TEXT NOT NULL,
            scope_note TEXT NOT NULL);
        CREATE TABLE bot_rotation_action (
            id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL,
            sort_order INTEGER NOT NULL, spell_id INTEGER NOT NULL,
            category TEXT NOT NULL, min_ready_runes INTEGER NOT NULL,
            required_self_aura INTEGER NOT NULL DEFAULT 0,
            forbidden_self_aura INTEGER NOT NULL DEFAULT 0);
    """)
    db.executemany("INSERT INTO bot_rotation_profile VALUES (?,?,?,?,?,?,?)", [
        (BLOOD, 6, "blood_death_knight", "tank", 25, "blood_note", "blood_scope"),
        (FROST, 6, "frost_death_knight", "dps", 11, "frost_note", "frost_scope"),
    ])
    db.executemany("INSERT INTO bot_rotation_action VALUES (?,?,?,?,?,?,?,?)", [
        (2049, BLOOD, 40, DEATH_STRIKE, "mitigation", 2, 0, 0),
        (2874, BLOOD, 42, HEART_STRIKE, "builder", 1, 0, 0),
        (9001, FROST, 42, HEART_STRIKE, "builder", 1, 0, 0),
    ])
    return db


def _forward_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").split("-- BEGIN REVERSE MIGRATION")[0]


def _reverse_sql() -> str:
    block = MIGRATION.read_text(encoding="utf-8").split("-- BEGIN REVERSE MIGRATION")[1]
    block = block.split("-- END REVERSE MIGRATION")[0]
    return "\n".join(line[3:] for line in block.splitlines() if line.startswith("-- "))


def _rows(db: sqlite3.Connection):
    return db.execute(
        "SELECT id, forbidden_self_aura, required_self_aura, min_ready_runes "
        "FROM bot_rotation_action ORDER BY id").fetchall()


def test_forward_is_scoped_idempotent_and_reversible() -> None:
    db = _database()
    before = _rows(db)
    db.executescript(_forward_sql())
    after = _rows(db)
    assert after == [(2049, 0, 0, 2), (2874, MANGLE_SEAT, 0, 1), (9001, 0, 0, 1)]
    profile = db.execute("SELECT version, source_note FROM bot_rotation_profile WHERE id=?", (BLOOD,)).fetchone()
    assert profile == (27, "phase9_blood_mangle_death_strike_runes_2026_09_23")
    assert db.execute("SELECT version FROM bot_rotation_profile WHERE id=?", (FROST,)).fetchone() == (11,)

    db.executescript(_forward_sql())
    assert _rows(db) == after
    db.execute("UPDATE bot_rotation_profile SET version = 30 WHERE id = ?", (BLOOD,))
    db.executescript(_forward_sql())
    assert db.execute("SELECT version FROM bot_rotation_profile WHERE id=?", (BLOOD,)).fetchone() == (30,)

    db.executescript(_reverse_sql())
    assert _rows(db) == before


def test_seat_aura_is_native_for_the_whole_seizure_in_every_mode() -> None:
    assert f"SPELL_MANGLE_2                              = {MANGLE_SEAT}," in SHARED.read_text(encoding="utf-8")
    boss = BOSS.read_text(encoding="utf-8")
    start = boss.index("void PassengerBoarded(Unit* passenger, int8 seatId, bool apply) override")
    boarded = boss[start:boss.index("void EnterEvadeMode", start)]
    apply_branch = boarded[boarded.index("if (apply)"):boarded.index("else")]
    release_branch = boarded[boarded.index("else"):]
    # Applied on boarding seat 2 (all difficulties), removed on release.
    assert "passenger->CastSpell(passenger, SPELL_MANGLE_2, true);" in apply_branch
    assert "passenger->RemoveAurasDueToSpell(SPELL_MANGLE_2);" in release_branch


def test_candidate_builder_honours_forbidden_self_aura_for_every_path() -> None:
    source = CANDIDATES.read_text(encoding="utf-8")
    assert re.search(r"if \(spell\.ForbiddenSelfAura && bot->HasAura\(spell\.ForbiddenSelfAura\)\)", source)
    header = MIGRATION.read_text(encoding="utf-8")
    assert "AND `spell_id` = 55050" in header and "SET `forbidden_self_aura` = 78412" in header
