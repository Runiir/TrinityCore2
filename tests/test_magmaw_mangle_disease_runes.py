"""Blood tank holds Icy Touch and Plague Strike while seized by Mangle.

With Heart Strike held (2026_09_23_40), fid16-8586fdd showed Icy Touch and
Plague Strike taking the Frost and Unholy runes during the Mangle holds (kill 1:
no Death Strike in a 16 s hold). The staged migration is replayed on an
in-memory SQLite copy of the current rows (world DB, profile 267 v27,
2026-09-23); the native facts it relies on are pinned in source and the
4.3.4 client rune costs.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_23_41_blood_mangle_disease_runes.sql"
HEART_STRIKE_MIGRATION = ROOT / "sql/custom/world/2026_09_23_40_blood_mangle_death_strike_runes.sql"
BOSS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_magmaw.cpp"
SHARED = BOSS.parent / "boss_magmaw_shared.h"
CANDIDATES = ROOT / "src/server/game/Bots/BotClassSpecActionProfileCandidates.cpp"
DBC = ROOT / "data/dbc/enUS"

BLOOD, FROST, UNHOLY = 267, 283, 284
ICY_TOUCH, PLAGUE_STRIKE, HEART_STRIKE, DEATH_STRIKE, OUTBREAK = 45477, 45462, 55050, 49998, 77575
MANGLE_SEAT = 78412


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
        (BLOOD, 6, "blood_death_knight", "tank", 27,
         "phase9_blood_mangle_death_strike_runes_2026_09_23", "blood_scope"),
        (FROST, 6, "frost_death_knight", "dps", 11, "frost_note", "frost_scope"),
        (UNHOLY, 6, "unholy_death_knight", "dps", 2, "unholy_note", "unholy_scope"),
    ])
    db.executemany("INSERT INTO bot_rotation_action VALUES (?,?,?,?,?,?,?,?)", [
        (2049, BLOOD, 40, DEATH_STRIKE, "mitigation", 2, 0, 0),
        (2874, BLOOD, 42, HEART_STRIKE, "builder", 1, 0, MANGLE_SEAT),
        (2050, BLOOD, 45, ICY_TOUCH, "threat_build", 1, 0, 0),
        (2051, BLOOD, 50, PLAGUE_STRIKE, "builder", 1, 0, 0),
        (2991, FROST, 45, OUTBREAK, "debuff", 0, 0, 0),
        (2492, FROST, 47, PLAGUE_STRIKE, "dot", 1, 0, 0),
        (2496, UNHOLY, 40, OUTBREAK, "debuff", 0, 0, 0),
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
    assert after == [
        (2049, 0, 0, 2),               # Death Strike untouched
        (2050, MANGLE_SEAT, 0, 1),     # Icy Touch held while seized
        (2051, MANGLE_SEAT, 0, 1),     # Plague Strike held while seized
        (2492, 0, 0, 1),               # Frost DK Plague Strike untouched
        (2496, 0, 0, 0),
        (2874, MANGLE_SEAT, 0, 1),     # Heart Strike hold already present
        (2991, 0, 0, 0),
    ]
    profile = db.execute("SELECT version, source_note FROM bot_rotation_profile WHERE id=?", (BLOOD,)).fetchone()
    assert profile == (28, "phase9_blood_mangle_disease_runes_2026_09_23")
    others = db.execute("SELECT id, version FROM bot_rotation_profile WHERE id<>? ORDER BY id", (BLOOD,)).fetchall()
    assert others == [(FROST, 11), (UNHOLY, 2)]

    db.executescript(_forward_sql())
    assert _rows(db) == after
    db.execute("UPDATE bot_rotation_profile SET version = 31 WHERE id = ?", (BLOOD,))
    db.executescript(_forward_sql())
    assert db.execute("SELECT version FROM bot_rotation_profile WHERE id=?", (BLOOD,)).fetchone() == (31,)

    # The reverse only lifts this migration's two rows; the Heart Strike hold
    # from 2026_09_23_40 stays.
    db.executescript(_reverse_sql())
    assert _rows(db) == before


def test_follows_the_heart_strike_hold_on_the_same_native_seat_aura() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    assert "SET `forbidden_self_aura` = 78412" in migration
    assert "AND `spell_id` IN (45477, 45462)" in migration
    assert "AND `spell_id` = 55050" in HEART_STRIKE_MIGRATION.read_text(encoding="utf-8")
    assert f"SPELL_MANGLE_2                              = {MANGLE_SEAT}," in SHARED.read_text(encoding="utf-8")
    boss = BOSS.read_text(encoding="utf-8")
    start = boss.index("void PassengerBoarded(Unit* passenger, int8 seatId, bool apply) override")
    boarded = boss[start:boss.index("void EnterEvadeMode", start)]
    assert "passenger->CastSpell(passenger, SPELL_MANGLE_2, true);" in boarded[:boarded.index("else")]
    assert "passenger->RemoveAurasDueToSpell(SPELL_MANGLE_2);" in boarded[boarded.index("else"):]
    candidates = CANDIDATES.read_text(encoding="utf-8")
    assert re.search(r"if \(spell\.ForbiddenSelfAura && bot->HasAura\(spell\.ForbiddenSelfAura\)\)", candidates)


@pytest.mark.skipif(not (DBC / "Spell.dbc").exists(), reason="pinned DBC not extracted")
def test_each_disease_spends_half_of_a_death_strike() -> None:
    sys.path.insert(0, str(ROOT))
    from tools.bot_ml.build_validation_provisioning import load_wdbc_values

    spells = {r[0]: r for r in load_wdbc_values(
        DBC / "Spell.dbc", "niiiiiiiiiiiiiiifiiiissxxiixxifiiiiiiixiiiiiiiii")}
    costs = {r[0]: r for r in load_wdbc_values(DBC / "SpellRuneCost.dbc", "niiii")}

    def runes(spell_id: int) -> tuple[int, int, int]:
        row = costs[spells[spell_id][26]]
        return row[1], row[2], row[3]   # blood, unholy, frost

    assert runes(ICY_TOUCH) == (0, 0, 1)
    assert runes(PLAGUE_STRIKE) == (0, 1, 0)
    assert runes(DEATH_STRIKE) == (0, 1, 1)
    assert runes(HEART_STRIKE) == (1, 0, 0)
