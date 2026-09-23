"""Static checks for the Blood tank Outbreak disease-upkeep migration.

The migration is replayed against an in-memory SQLite copy of the current
Blood tank rows (read from the world DB on 2026-09-23, profile 267 v25), so the
forward SQL, its idempotence and the documented reverse block are exercised
without a MySQL server. Score arithmetic mirrors the production candidate
builder and resolver formulas, whose source text is also pinned here.
"""

from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/staged/world/2026_09_23_10_blood_outbreak_disease_upkeep.sql"
CANDIDATES = ROOT / "src/server/game/Bots/BotClassSpecActionProfileCandidates.cpp"
RESOLVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
ACTION_PROFILES = ROOT / "experiments/configs/cata_434_action_profiles.json"
DBC = ROOT / "data/dbc/enUS"

OUTBREAK, BLOOD_PLAGUE, FROST_FEVER = 77575, 55078, 55095
BLOOD, FROST, BLOOD_DPS = 267, 283, 900
OLD_NOTES = (
    25,
    "phase9_blood_death_strike_priority_2026_09_19",
    "Keep Death Strike and Heart Strike in the same bucket so the higher-scoring valid action wins",
)
TAGS = "outbreak,diseases,blood_plague,frost_fever,maintain_owned_aura,no_rune_cost"

COLUMNS = (
    "id", "profile_id", "sort_order", "spell_id", "category", "mechanic_tags",
    "damage_weight", "healing_weight", "threat_weight", "mitigation_weight",
    "survival_weight", "priority_bucket", "min_enemies", "max_enemies",
    "max_self_health_pct", "requires_melee_range", "target_selector",
    "movement_directive", "auto_attack_mode", "min_range", "max_range",
    "maintain_aura_id", "refresh_aura_below_ms", "min_ready_runes", "enabled",
)
# (id, sort, spell, category, D, H, T, M, S, bucket, min_en, max_hp, melee,
#  selector, max_range, maintain, refresh, runes); tags are irrelevant here.
BLOOD_ROWS = (
    (2042, 10, 57330, "buff", 0.15, 0, 0.2, 0, 0.4, 0, 1, 1.0, 0, "self", 0, 57330, 0, 0),
    (2043, 12, 48263, "buff", 0, 0, 0.3, 0.9, 0.9, 0, 1, 1.0, 0, "self", 0, 48263, 0, 0),
    (3560, 31, 43265, "aoe", 1, 0, 5, 0, 0, 0, 2, 1.0, 0, "ground_enemy", 30, 0, 0, 1),
    (2875, 32, 48721, "aoe", 1.2, 0, 4, 0, 0, 0, 2, 1.0, 0, "self", 0, 0, 0, 1),
    (2876, 15, 49028, "offensive_cooldown", 2, 0, 2, 0.15, 0.1, 1, 1, 1.0, 0, "enemy", 0, 0, 0, 0),
    (2044, 20, 49222, "defensive", 0, 0, 0.2, 0.85, 0.85, 1, 1, 0.9, 0, "self", 0, 49222, 0, 0),
    (2045, 25, 48792, "defensive", 0, 0, 0.1, 1, 1, 1, 1, 0.65, 0, "self", 0, 48792, 0, 0),
    (2046, 28, 55233, "defensive", 0, 0.3, 0.1, 0.85, 1, 1, 1, 0.7, 0, "self", 0, 55233, 0, 0),
    (2047, 30, 47528, "interrupt", 0.15, 0, 0, 0, 0.2, 1, 1, 1.0, 1, "enemy", 0, 0, 0, 0),
    (2048, 35, 56222, "taunt", 0, 0, 4, 0, 0.3, 1, 1, 1.0, 0, "enemy", 0, 0, 0, 0),
    (2049, 40, 49998, "mitigation", 0.76, 0.8, 0.75, 0.65, 0.85, 1, 1, 1.0, 1, "enemy", 0, 0, 0, 2),
    (2874, 42, 55050, "builder", 1.5, 0, 1.5, 0, 0, 1, 1, 1.0, 1, "enemy", 0, 0, 0, 1),
    (2884, 44, 56815, "spender", 1.45, 0, 1.55, 0, 0, 1, 1, 1.0, 1, "enemy", 0, 0, 0, 0),
    (2050, 45, 45477, "threat_build", 1.05, 0, 1.2, 0, 0, 1, 1, 1.0, 0, "enemy", 0, FROST_FEVER, 3000, 1),
    (2051, 50, 45462, "builder", 1.05, 0, 1.15, 0, 0, 1, 1, 1.0, 1, "enemy", 0, BLOOD_PLAGUE, 3000, 1),
    (2052, 60, 47541, "spender", 0.68, 0, 0.45, 0, 0, 4, 1, 1.0, 0, "enemy", 0, 0, 0, 0),
)


def _database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript(
        """
        CREATE TABLE bot_rotation_profile (
            id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL, spec_tag TEXT NOT NULL,
            role TEXT NOT NULL, version INTEGER NOT NULL, source_note TEXT NOT NULL,
            scope_note TEXT NOT NULL);
        CREATE TABLE bot_rotation_action (
            id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0, spell_id INTEGER NOT NULL DEFAULT 0,
            category TEXT NOT NULL, mechanic_tags TEXT NOT NULL DEFAULT '',
            damage_weight REAL NOT NULL DEFAULT 0, healing_weight REAL NOT NULL DEFAULT 0,
            threat_weight REAL NOT NULL DEFAULT 0, mitigation_weight REAL NOT NULL DEFAULT 0,
            survival_weight REAL NOT NULL DEFAULT 0, priority_bucket INTEGER NOT NULL DEFAULT 5,
            min_enemies INTEGER NOT NULL DEFAULT 1, max_enemies INTEGER NOT NULL DEFAULT 0,
            max_self_health_pct REAL NOT NULL DEFAULT 1, requires_melee_range INTEGER NOT NULL DEFAULT 0,
            target_selector TEXT NOT NULL DEFAULT 'enemy', movement_directive TEXT NOT NULL DEFAULT '',
            auto_attack_mode TEXT NOT NULL DEFAULT '', min_range REAL NOT NULL DEFAULT 0,
            max_range REAL NOT NULL DEFAULT 0, maintain_aura_id INTEGER NOT NULL DEFAULT 0,
            refresh_aura_below_ms INTEGER NOT NULL DEFAULT 0, min_ready_runes INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1);
        """
    )
    db.executemany(
        "INSERT INTO bot_rotation_profile VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (BLOOD, 6, "blood_death_knight", "tank", *OLD_NOTES),
            (FROST, 6, "frost_death_knight", "dps", 11, "frost", "frost scope"),
            (BLOOD_DPS, 6, "blood_death_knight", "dps", 3, "blood dps", "dps scope"),
        ],
    )
    for row in BLOOD_ROWS:
        (rid, sort, spell, cat, d, h, t, m, s, bucket, min_en, max_hp, melee,
         selector, max_range, maintain, refresh, runes) = row
        db.execute(
            f"INSERT INTO bot_rotation_action ({', '.join(COLUMNS)}) "
            f"VALUES ({', '.join('?' * len(COLUMNS))})",
            (rid, BLOOD, sort, spell, cat, "", d, h, t, m, s, bucket, min_en, 0,
             max_hp, melee, selector, "melee", "melee", 0, max_range, maintain,
             refresh, runes, 1),
        )
    # Frost already owns an Outbreak row; it must neither block nor receive ours.
    db.execute(
        "INSERT INTO bot_rotation_action (id, profile_id, sort_order, spell_id, category, "
        "damage_weight, priority_bucket, maintain_aura_id, refresh_aura_below_ms) "
        "VALUES (5000, ?, 45, ?, 'debuff', 0.9, 1, ?, 3000)",
        (FROST, OUTBREAK, BLOOD_PLAGUE),
    )
    return db


def _state(db: sqlite3.Connection) -> tuple[list[tuple], list[tuple]]:
    return (
        db.execute("SELECT * FROM bot_rotation_profile ORDER BY id").fetchall(),
        db.execute(f"SELECT {', '.join(COLUMNS)} FROM bot_rotation_action ORDER BY id").fetchall(),
    )


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _reverse_block() -> list[str]:
    lines = _sql().splitlines()
    start = lines.index("-- BEGIN REVERSE MIGRATION")
    end = lines.index("-- END REVERSE MIGRATION")
    return lines[start + 1 : end]


def _outbreak_rows(db: sqlite3.Connection, profile: int) -> list[dict]:
    db.row_factory = sqlite3.Row
    rows = db.execute(
        f"SELECT {', '.join(COLUMNS)} FROM bot_rotation_action WHERE profile_id = ? AND spell_id = ?",
        (profile, OUTBREAK),
    ).fetchall()
    db.row_factory = None
    return [dict(row) for row in rows]


def test_forward_adds_one_scoped_outbreak_row_and_replays_idempotently():
    db = _database()
    before_profiles, before_actions = _state(db)
    db.executescript(_sql())
    first = _state(db)
    db.executescript(_sql())
    assert _state(db) == first

    rows = _outbreak_rows(db, BLOOD)
    assert len(rows) == 1
    row = rows[0]
    assert {k: row[k] for k in (
        "sort_order", "category", "mechanic_tags", "priority_bucket", "min_enemies",
        "max_enemies", "requires_melee_range", "target_selector", "min_range", "max_range",
        "maintain_aura_id", "refresh_aura_below_ms", "min_ready_runes", "enabled",
        "healing_weight", "mitigation_weight", "survival_weight",
    )} == {
        "sort_order": 38, "category": "debuff", "mechanic_tags": TAGS,
        "priority_bucket": 1, "min_enemies": 1, "max_enemies": 0,
        "requires_melee_range": 0, "target_selector": "enemy", "min_range": 0,
        "max_range": 0, "maintain_aura_id": BLOOD_PLAGUE, "refresh_aura_below_ms": 3000,
        "min_ready_runes": 0, "enabled": 1, "healing_weight": 0,
        "mitigation_weight": 0, "survival_weight": 0,
    }
    assert (row["damage_weight"], row["threat_weight"]) == pytest.approx((1.8, 1.7))
    assert row["sort_order"] not in {r[1] for r in BLOOD_ROWS}

    # Every pre-existing action, including Icy Touch/Plague Strike fallbacks and
    # Frost's own Outbreak, is byte-for-byte unchanged; only one row is added.
    after_profiles, after_actions = first
    assert [a for a in after_actions if a[0] != row["id"]] == before_actions
    assert _outbreak_rows(db, BLOOD_DPS) == []
    assert after_profiles[0][4:] == (
        26,
        "phase9_blood_outbreak_disease_upkeep_2026_09_23",
        "Maintain Blood Plague and Frost Fever with native Outbreak, "
        "keeping Icy Touch and Plague Strike as cooldown fallbacks",
    )
    assert after_profiles[1:] == before_profiles[1:]


def test_reverse_block_is_inert_on_autoapply_and_restores_exact_state():
    reverse = _reverse_block()
    assert reverse and all(line.startswith("-- ") for line in reverse)
    executable = "\n".join(l for l in _sql().splitlines() if not l.lstrip().startswith("--"))
    assert "DELETE" not in executable.upper()
    # Exactly two executable statements, each safe for a naive ';' splitter.
    assert [s.split(None, 2)[:2] for s in executable.split(";") if s.strip()] == [
        ["INSERT", "INTO"], ["UPDATE", "`bot_rotation_profile`"]]

    db = _database()
    before = _state(db)
    db.executescript(_sql())
    db.executescript("\n".join(line[3:] for line in reverse))
    assert _state(db) == before
    # Replaying the reverse is harmless.
    db.executescript("\n".join(line[3:] for line in reverse))
    assert _state(db) == before

    # A later profile migration's identity is not clobbered by the reverse.
    db.executescript(_sql())
    db.execute("UPDATE bot_rotation_profile SET version = 27, source_note = 'later' WHERE id = ?", (BLOOD,))
    db.executescript("\n".join(line[3:] for line in reverse))
    assert db.execute("SELECT version, source_note FROM bot_rotation_profile WHERE id = ?", (BLOOD,)).fetchone() == (27, "later")
    assert _outbreak_rows(db, BLOOD) == []


def _scores(d: float, h: float, t: float, m: float, s: float, bucket: int) -> dict[str, float]:
    base = d + h + t + m + s - bucket * 0.03
    return {
        "balanced_role_dps": base + d * 0.55 + h * 0.25 + t * 0.25,
        "role_first_tank": base + t + m + s * 0.45,
        "dps_push": base + d,
        "pure_survival": base + s * 1.5 + m + h - d * 0.25,
    }


def test_outbreak_priority_is_above_strikes_but_yields_to_survival():
    source = CANDIDATES.read_text(encoding="utf-8")
    assert "candidate.Score = spell.DamageWeight + spell.HealingWeight + spell.ThreatWeight" in source
    assert "- float(spell.PriorityBucket) * 0.03f;" in source
    resolver = RESOLVER.read_text(encoding="utf-8")
    for formula in (
        "roleScore += candidate.Profile.DamageWeight * 0.55f + candidate.Profile.HealingWeight * 0.25f + candidate.Profile.ThreatWeight * 0.25f;",
        "roleScore += candidate.Profile.ThreatWeight + candidate.Profile.MitigationWeight + candidate.Profile.SurvivalWeight * 0.45f;",
        "roleScore += candidate.Profile.DamageWeight + candidate.Profile.ProgressionWeight * 0.35f;",
        "roleScore += candidate.Profile.SurvivalWeight * 1.5f + candidate.Profile.MitigationWeight + candidate.Profile.HealingWeight;",
    ):
        assert formula in resolver

    by_spell = {r[2]: _scores(*r[4:10]) for r in BLOOD_ROWS}  # (D, H, T, M, S, bucket)
    outbreak = _scores(1.8, 0, 1.7, 0, 0, 1)
    ds, hs, rs, it, ps, drw, taunt = (by_spell[s] for s in (49998, 55050, 56815, 45477, 45462, 49028, 56222))

    bal = "balanced_role_dps"
    assert outbreak[bal] == pytest.approx(4.885)
    assert max(ds[bal], hs[bal], rs[bal], it[bal], ps[bal]) < outbreak[bal] < min(taunt[bal], drw[bal])
    assert max(ds["dps_push"], hs["dps_push"], rs["dps_push"]) < outbreak["dps_push"] < drw["dps_push"]
    # Survival-oriented modes keep Death Strike first.
    assert outbreak["role_first_tank"] < ds["role_first_tank"]
    assert outbreak["pure_survival"] < ds["pure_survival"]
    # In every mode Outbreak outranks the rune-costing disease fallbacks.
    for mode in outbreak:
        assert outbreak[mode] > max(it[mode], ps[mode])


def test_provisioning_dependency_is_explicit():
    profiles = json.loads(ACTION_PROFILES.read_text(encoding="utf-8"))["action_profile_spells_by_spec"]
    assert OUTBREAK in profiles["frost_death_knight"] and OUTBREAK in profiles["unholy_death_knight"]
    if OUTBREAK not in profiles["blood_death_knight"]:
        header = _sql().split("INSERT INTO", 1)[0]
        assert "cata_434_action_profiles.json" in header
        assert "unknown_requested_spell" in header


def _wdbc(name: str) -> tuple[list[tuple[int, ...]], bytes]:
    data = (DBC / name).read_bytes()
    magic, count, fields, size, _strings = struct.unpack_from("<4s4i", data)
    assert magic == b"WDBC" and size == fields * 4
    body = data[20 : 20 + count * size]
    return list(struct.iter_unpack(f"<{fields}i", body)), data[20 + count * size :]


@pytest.mark.skipif(not (DBC / "Spell.dbc").exists(), reason="pinned DBC not extracted")
def test_native_outbreak_is_free_single_target_and_blood_cooldown_is_30s():
    spells, _ = _wdbc("Spell.dbc")
    spell = {r[0]: r for r in spells if r[0] in (OUTBREAK, 50029, 81334, BLOOD_PLAGUE, FROST_FEVER)}
    effects, _ = _wdbc("SpellEffect.dbc")
    effect = {}
    for r in effects:
        if r[24] in spell:
            effect.setdefault(r[24], []).append(r)
    cooldowns = {r[0]: r for r in _wdbc("SpellCooldowns.dbc")[0]}
    options = {r[0]: r for r in _wdbc("SpellClassOptions.dbc")[0]}
    durations = {r[0]: r for r in _wdbc("SpellDuration.dbc")[0]}

    outbreak = spell[OUTBREAK]
    assert outbreak[26] == 0  # RuneCostID: no rune cost
    assert cooldowns[outbreak[37]][2] == 60000
    # Only two TRIGGER_SPELL effects on the selected enemy, no chain or area.
    assert sorted((e[1], e[21], e[22], e[8], e[15]) for e in effect[OUTBREAK]) == [
        (64, BLOOD_PLAGUE, 6, 0, 0), (64, FROST_FEVER, 6, 0, 0)]

    def mask(spell_id: int) -> tuple[int, int, int]:
        row = options[spell[spell_id][36]]
        return row[2] & 0xFFFFFFFF, row[3] & 0xFFFFFFFF, row[4] & 0xFFFFFFFF

    def modifies(modifier: tuple, target: int) -> bool:
        return any(a & b for a, b in zip((x & 0xFFFFFFFF for x in modifier[18:21]), mask(target)))

    veteran = [e for e in effect[50029] if e[3] == 107 and e[12] == 11]  # flat cooldown mod
    assert veteran and veteran[0][5] == -30000 and modifies(veteran[0], OUTBREAK)
    epidemic = [e for e in effect[81334] if e[3] == 107 and e[12] == 1]  # flat duration mod
    assert epidemic and epidemic[0][5] == 12000
    for disease in (BLOOD_PLAGUE, FROST_FEVER):
        assert durations[spell[disease][13]][1] == 21000
        assert modifies(epidemic[0], disease)
    # Both talents are provisioned for the Blood bot.
    blood = json.loads(ACTION_PROFILES.read_text(encoding="utf-8"))["action_profile_spells_by_spec"]["blood_death_knight"]
    assert 50029 in blood and 81334 in blood
