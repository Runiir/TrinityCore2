"""Blood tank Rune Tap row (2026_09_24_10, error ledger TANK-003).

The migration is replayed against an in-memory SQLite copy of the live Blood
tank rows (world DB profile 267 v31, read 2026-09-24; no Rune Tap row exists in
any profile). The score arithmetic mirrors the candidate builder and resolver
formulas, whose source text is pinned. The native Rune Tap and Will of the
Necropolis facts are read from the pinned 4.3.4 DBC.
"""
from __future__ import annotations

import json
import re
import sqlite3
import struct
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "src/server/game/Bots"
SQL = ROOT / "sql/custom/world/2026_09_24_10_blood_rune_tap.sql"
CANDIDATES = BOT / "BotClassSpecActionProfileCandidates.cpp"
RESOLVER = BOT / "BotWorldPopulationMgrCombatResolver.cpp"
RESERVATION = BOT / "BotWorldPopulationMgrRaidCooldownReservation.h"
ACTION_PROFILES = ROOT / "experiments/configs/cata_434_action_profiles.json"
WCL_TIMELINES = (ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/"
                 "magmaw_wcl_cast_timelines_v1.json")
DBC = ROOT / "data/dbc/enUS"

RUNE_TAP, WILL_OF_THE_NECROPOLIS, WOTN_FREE_RUNE_TAP = 48982, 52284, 96171
DEATH_STRIKE, HEART_STRIKE, RUNE_STRIKE = 49998, 55050, 56815
BLOOD_TAP, ERW, VAMPIRIC_BLOOD, ICEBOUND = 45529, 47568, 55233, 48792
BLOOD, FROST, UNHOLY, BLOOD_DPS = 267, 283, 284, 900
TAGS = "rune_tap,self_heal,blood_rune,off_gcd"

V31 = (
    31,
    "phase9_blood_empower_rune_weapon_rune_recovery_2026_09_23",
    "Cast native Empower Rune Weapon only while at most one rune is ready, "
    "above Blood Tap and below Death Strike",
)
V32 = (
    32,
    "phase9_blood_rune_tap_2026_09_24",
    "Cast native Rune Tap below 60% health, above Heart Strike and below Death Strike",
)

COLUMNS = (
    "id", "profile_id", "sort_order", "spell_id", "category", "mechanic_tags",
    "damage_weight", "healing_weight", "threat_weight", "mitigation_weight",
    "survival_weight", "priority_bucket", "min_enemies", "max_enemies",
    "max_self_health_pct", "requires_melee_range", "target_selector",
    "movement_directive", "auto_attack_mode", "min_range", "max_range",
    "maintain_aura_id", "refresh_aura_below_ms", "min_ready_runes",
    "max_ready_runes", "forbidden_self_aura", "enabled",
)
# Live profile 267 v31: (id, sort, spell, category, D, H, T, M, S, bucket,
# min_enemies, max_self_hp, melee, selector, max_range, maintain, refresh,
# min_ready_runes, max_ready_runes, forbidden_self_aura).
BLOOD_ROWS = (
    (2042, 10, 57330, "buff", 0.15, 0, 0.2, 0, 0.4, 0, 1, 1.0, 0, "self", 0, 57330, 0, 0, 0, 0),
    (2043, 12, 48263, "buff", 0, 0, 0.3, 0.9, 0.9, 0, 1, 1.0, 0, "self", 0, 48263, 0, 0, 0, 0),
    (2876, 15, 49028, "offensive_cooldown", 2, 0, 2, 0.15, 0.1, 1, 1, 1.0, 0, "enemy", 0, 0, 0, 0, 0, 0),
    (2044, 20, 49222, "defensive", 0, 0, 0.2, 0.85, 0.85, 1, 1, 0.9, 0, "self", 0, 49222, 0, 0, 0, 0),
    (2045, 25, ICEBOUND, "defensive", 0, 0, 0.1, 1, 1, 1, 1, 0.65, 0, "self", 0, ICEBOUND, 0, 0, 0, 0),
    (2046, 28, VAMPIRIC_BLOOD, "defensive", 0, 0.3, 0.1, 0.85, 1, 1, 1, 0.7, 0, "self", 0, VAMPIRIC_BLOOD, 0, 0, 0, 0),
    (2047, 30, 47528, "interrupt", 0.15, 0, 0, 0, 0.2, 1, 1, 1.0, 1, "enemy", 0, 0, 0, 0, 0, 0),
    (3560, 31, 43265, "aoe", 1, 0, 5, 0, 0, 0, 2, 1.0, 0, "ground_enemy", 30, 0, 0, 1, 0, 0),
    (2875, 32, 48721, "aoe", 1.2, 0, 4, 0, 0, 0, 2, 1.0, 0, "self", 0, 0, 0, 1, 0, 0),
    (2048, 35, 56222, "taunt", 0, 0, 4, 0, 0.3, 1, 1, 1.0, 0, "enemy", 0, 0, 0, 0, 0, 0),
    (3620, 36, ERW, "offensive_cooldown", 1.1, 0, 2.2, 0, 0, 1, 1, 1.0, 0, "self", 0, 0, 0, 0, 1, 0),
    (3619, 37, BLOOD_TAP, "resource_generator", 1.2, 0, 1.9, 0, 0, 1, 1, 1.0, 0, "self", 0, 0, 0, 0, 1, 0),
    (3616, 38, 77575, "debuff", 1.8, 0, 1.7, 0, 0, 1, 1, 1.0, 0, "enemy", 0, 55078, 3000, 0, 0, 0),
    (2049, 40, DEATH_STRIKE, "mitigation", 0.76, 0.8, 0.75, 0.65, 0.85, 1, 1, 1.0, 1, "enemy", 0, 0, 0, 2, 0, 0),
    (2874, 42, HEART_STRIKE, "builder", 1.5, 0, 1.5, 0, 0, 1, 1, 1.0, 1, "enemy", 0, 0, 0, 1, 0, 78412),
    (2884, 44, RUNE_STRIKE, "spender", 1.45, 0, 1.55, 0, 0, 1, 1, 1.0, 1, "enemy", 0, 0, 0, 0, 0, 0),
    (2050, 45, 45477, "threat_build", 1.05, 0, 1.2, 0, 0, 1, 1, 1.0, 0, "enemy", 0, 55095, 3000, 1, 0, 78412),
    (2051, 50, 45462, "builder", 1.05, 0, 1.15, 0, 0, 1, 1, 1.0, 1, "enemy", 0, 55078, 3000, 1, 0, 78412),
    (2052, 60, 47541, "spender", 0.68, 0, 0.45, 0, 0, 4, 1, 1.0, 0, "enemy", 0, 0, 0, 0, 0, 0),
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
            max_ready_runes INTEGER NOT NULL DEFAULT 0,
            forbidden_self_aura INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1);
        """
    )
    db.executemany(
        "INSERT INTO bot_rotation_profile VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (BLOOD, 6, "blood_death_knight", "tank", *V31),
            (FROST, 6, "frost_death_knight", "dps", 11, "frost", "frost scope"),
            (UNHOLY, 6, "unholy_death_knight", "dps", 2, "unholy", "unholy scope"),
            (BLOOD_DPS, 6, "blood_death_knight", "dps", 3, "blood dps", "dps scope"),
        ],
    )
    for (rid, sort, spell, cat, d, h, t, m, s, bucket, min_en, max_hp, melee, selector,
         max_range, maintain, refresh, min_runes, max_runes, forbidden) in BLOOD_ROWS:
        values = dict(zip(COLUMNS, (
            rid, BLOOD, sort, spell, cat, "", d, h, t, m, s, bucket, min_en, 0, max_hp, melee,
            selector, "melee", "melee", 0, max_range, maintain, refresh, min_runes, max_runes,
            forbidden, 1)))
        db.execute(
            f"INSERT INTO bot_rotation_action ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
            [values[c] for c in COLUMNS],
        )
    # A Blood dps profile row: untouched, and the dps profile neither blocks
    # nor receives the Blood tank Rune Tap.
    db.execute(
        "INSERT INTO bot_rotation_action (id, profile_id, sort_order, spell_id, category, "
        "damage_weight, priority_bucket, target_selector) VALUES (9001, ?, 40, ?, 'builder', 1, 1, 'enemy')",
        (BLOOD_DPS, HEART_STRIKE),
    )
    return db


def _state(db: sqlite3.Connection) -> tuple[list[tuple], list[tuple]]:
    return (
        db.execute("SELECT * FROM bot_rotation_profile ORDER BY id").fetchall(),
        db.execute(f"SELECT {', '.join(COLUMNS)} FROM bot_rotation_action ORDER BY id").fetchall(),
    )


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _executable(path: Path) -> str:
    return "\n".join(l for l in _text(path).splitlines() if not l.lstrip().startswith("--"))


def _reverse(path: Path) -> str:
    lines = _text(path).splitlines()
    block = lines[lines.index("-- BEGIN REVERSE MIGRATION") + 1 : lines.index("-- END REVERSE MIGRATION")]
    assert block and all(line.startswith("-- ") for line in block)
    return "\n".join(line[3:] for line in block)


def _rows(db: sqlite3.Connection, profile: int, spell: int) -> list[dict]:
    db.row_factory = sqlite3.Row
    rows = db.execute(
        f"SELECT {', '.join(COLUMNS)} FROM bot_rotation_action WHERE profile_id = ? AND spell_id = ?",
        (profile, spell),
    ).fetchall()
    db.row_factory = None
    return [dict(row) for row in rows]


def _profile(db: sqlite3.Connection, profile: int = BLOOD) -> tuple:
    return db.execute(
        "SELECT version, source_note, scope_note FROM bot_rotation_profile WHERE id = ?", (profile,)
    ).fetchone()


def test_forward_inserts_one_scoped_row_idempotently():
    executable = _executable(SQL)
    assert "DELETE" not in executable.upper()
    assert [s.split(None, 2)[:2] for s in executable.split(";") if s.strip()] == [
        ["INSERT", "INTO"], ["UPDATE", "`bot_rotation_profile`"]]

    db = _database()
    before_profiles, before_actions = _state(db)
    db.executescript(_text(SQL))
    first = _state(db)
    db.executescript(_text(SQL))
    assert _state(db) == first

    (row,) = _rows(db, BLOOD, RUNE_TAP)
    assert row == {
        "id": row["id"], "profile_id": BLOOD, "sort_order": 29, "spell_id": RUNE_TAP,
        "category": "defensive", "mechanic_tags": TAGS,
        "damage_weight": 0, "healing_weight": 2.0, "threat_weight": 1.2,
        "mitigation_weight": 0, "survival_weight": 0.35, "priority_bucket": 1,
        "min_enemies": 1, "max_enemies": 0, "max_self_health_pct": 0.6,
        "requires_melee_range": 0, "target_selector": "self",
        "movement_directive": "melee", "auto_attack_mode": "melee",
        "min_range": 0, "max_range": 0, "maintain_aura_id": 0, "refresh_aura_below_ms": 0,
        # No ready-rune floor: a Will of the Necropolis Rune Tap costs no rune.
        "min_ready_runes": 0, "max_ready_runes": 0, "forbidden_self_aura": 0, "enabled": 1,
    }
    assert 29 not in [r[1] for r in BLOOD_ROWS]

    # Only the Blood tank gets the row and the version bump.
    after_profiles, after_actions = first
    assert [a for a in after_actions if a[0] != row["id"]] == before_actions
    for profile in (FROST, UNHOLY, BLOOD_DPS):
        assert _rows(db, profile, RUNE_TAP) == []
    assert _profile(db) == V32
    assert after_profiles[1:] == before_profiles[1:]

    # The version bump never lowers a later profile version.
    db.execute("UPDATE bot_rotation_profile SET version = 40 WHERE id = ?", (BLOOD,))
    db.executescript(_text(SQL))
    assert _profile(db)[0] == 40 and len(_rows(db, BLOOD, RUNE_TAP)) == 1


def test_existing_rune_tap_row_blocks_the_insert():
    db = _database()
    db.execute(
        "INSERT INTO bot_rotation_action (profile_id, sort_order, spell_id, category, max_self_health_pct) "
        "VALUES (?, 77, ?, 'defensive', 0.5)", (BLOOD, RUNE_TAP))
    db.executescript(_text(SQL))
    (row,) = _rows(db, BLOOD, RUNE_TAP)
    assert (row["sort_order"], row["max_self_health_pct"]) == (77, 0.5)


def test_reverse_restores_the_prior_state_and_is_harmless_to_replay():
    db = _database()
    before = _state(db)
    db.executescript(_text(SQL))
    db.executescript(_reverse(SQL))
    assert _state(db) == before
    db.executescript(_reverse(SQL))
    assert _state(db) == before

    # A later migration that already moved the profile note on is not
    # rolled back by this reverse; only its own row is removed.
    db.executescript(_text(SQL))
    db.execute("UPDATE bot_rotation_profile SET version = 33, source_note = 'later' WHERE id = ?", (BLOOD,))
    db.executescript(_reverse(SQL))
    assert _rows(db, BLOOD, RUNE_TAP) == []
    assert _profile(db)[:2] == (33, "later")


# --- Scores ------------------------------------------------------------------


def _scores(d: float, h: float, t: float, m: float, s: float, bucket: int) -> dict[str, float]:
    base = d + h + t + m + s - bucket * 0.03
    return {
        "balanced_role_dps": base + d * 0.55 + h * 0.25 + t * 0.25,
        "role_first_tank": base + t + m + s * 0.45,
        "dps_push": base + d,
        "pure_survival": base + s * 1.5 + m + h - d * 0.25,
    }


def _row_scores(row: dict) -> dict[str, float]:
    return _scores(row["damage_weight"], row["healing_weight"], row["threat_weight"],
                   row["mitigation_weight"], row["survival_weight"], row["priority_bucket"])


def test_rune_tap_ranks_above_heart_strike_and_below_death_strike():
    candidates = _text(CANDIDATES)
    assert "candidate.Score = spell.DamageWeight + spell.HealingWeight + spell.ThreatWeight" in candidates
    assert "- float(spell.PriorityBucket) * 0.03f;" in candidates
    resolver = _text(RESOLVER)
    for formula in (
        "roleScore += candidate.Profile.DamageWeight * 0.55f + candidate.Profile.HealingWeight * 0.25f + candidate.Profile.ThreatWeight * 0.25f;",
        "roleScore += candidate.Profile.ThreatWeight + candidate.Profile.MitigationWeight + candidate.Profile.SurvivalWeight * 0.45f;",
        "roleScore += candidate.Profile.DamageWeight + candidate.Profile.ProgressionWeight * 0.35f;",
        "roleScore += candidate.Profile.SurvivalWeight * 1.5f + candidate.Profile.MitigationWeight + candidate.Profile.HealingWeight;",
        "roleScore -= candidate.Profile.DamageWeight * 0.25f;",
        "return !current || candidate.Profile.PriorityBucket < current->Profile.PriorityBucket",
    ):
        assert formula in resolver

    db = _database()
    db.executescript(_text(SQL))
    spells = (RUNE_TAP, DEATH_STRIKE, HEART_STRIKE, RUNE_STRIKE, BLOOD_TAP, ERW, VAMPIRIC_BLOOD, ICEBOUND)
    rows = {spell: _rows(db, BLOOD, spell)[0] for spell in spells}
    assert {row["priority_bucket"] for row in rows.values()} == {1}
    rt, ds, hs, rs, bt, erw, vb, ibf = (_row_scores(rows[s]) for s in spells)

    # The numbers documented in the migration header.
    assert rt == pytest.approx({"balanced_role_dps": 4.32, "role_first_tank": 4.8775,
                                "dps_push": 3.52, "pure_survival": 6.045})
    header = _text(SQL).split("INSERT INTO", 1)[0]
    for number in ("3.52", "4.32", "4.8775", "6.045", "4.17", "4.155", "4.205", "4.425",
                   "4.5855", "5.5625", "4.54", "6.315", "4.87", "4.57", "4.47", "4.52"):
        assert number in header, number
    assert ds == pytest.approx({"balanced_role_dps": 4.5855, "role_first_tank": 5.5625,
                                "dps_push": 4.54, "pure_survival": 6.315})
    assert vb["pure_survival"] == pytest.approx(4.87) and ibf["pure_survival"] == pytest.approx(4.57)

    for mode in ds:
        # Never above Death Strike: a castable Death Strike always goes first.
        assert rt[mode] < ds[mode], mode
        assert ds[mode] - rt[mode] > 0.05, mode
    bal = "balanced_role_dps"
    # The tank's observed mode: above the strikes and Blood Tap, below ERW.
    assert max(hs[bal], rs[bal], bt[bal]) + 0.05 < rt[bal] < erw[bal] - 0.05
    assert max(hs["role_first_tank"], rs["role_first_tank"]) < rt["role_first_tank"]
    # First defensive when survival dominates.
    assert rt["pure_survival"] > max(vb["pure_survival"], ibf["pure_survival"])
    for mode in ds:
        assert round(rt[mode], 6) not in {round(x[mode], 6) for x in (hs, rs, bt, erw, vb, ibf)}


def test_raid_reservation_never_holds_rune_tap():
    reservation = _text(RESERVATION)
    # Defensive rows are exempt from the trash / pre-pull offensive reservation.
    assert "case BotCombatActionCategory::Defensive:" in reservation
    # The boss-hit rules hold only a cooldown longer than the 90 s hit.
    assert "|| cooldownMs <= nextBossOpeningHitMs)" in reservation
    assert "|| cooldownMs <= bigHitSpacingMs)" in reservation
    assert '{ "bwd.magmaw.encounter", 90000, 88253 },' in reservation
    assert "'defensive'" in _executable(SQL)


# --- Provisioning, evidence and native facts ----------------------------------


def test_rune_tap_is_provisioned_and_used_by_the_wcl_reference_tank():
    blood = json.loads(_text(ACTION_PROFILES))["action_profile_spells_by_spec"]["blood_death_knight"]
    assert RUNE_TAP in blood and WILL_OF_THE_NECROPOLIS in blood
    header = _text(SQL).split("INSERT INTO", 1)[0]
    assert "cata_434_action_profiles.json" in header and "unknown_requested_spell" in header
    timelines = json.loads(_text(WCL_TIMELINES))
    assert timelines["reference_id"] == "Y8ajQ7dbmKMG1RZy-fight22"
    (tank,) = [a for a in timelines["actors"] if a.get("class_spec") == "blood_death_knight"]
    casts = [(c["ability"], c["t"]) for c in tank["casts"]]
    assert ("Rune Tap", 97.204) in casts and ("Vampiric Blood", 96.307) in casts
    assert "97.2 s" in header


def _wdbc(name: str) -> list[tuple[int, ...]]:
    data = (DBC / name).read_bytes()
    magic, count, fields, size, _strings = struct.unpack_from("<4s4i", data)
    assert magic == b"WDBC" and size == fields * 4
    return list(struct.iter_unpack(f"<{fields}i", data[20 : 20 + count * size]))


@pytest.mark.skipif(not (DBC / "Spell.dbc").exists(), reason="pinned DBC not extracted")
def test_native_rune_tap_and_will_of_the_necropolis_facts():
    wanted = (RUNE_TAP, WOTN_FREE_RUNE_TAP, WILL_OF_THE_NECROPOLIS)
    spell = {r[0]: r for r in _wdbc("Spell.dbc") if r[0] in wanted}
    effects: dict[int, list[tuple]] = {}
    for r in _wdbc("SpellEffect.dbc"):
        if r[24] in spell:
            effects.setdefault(r[24], []).append(r)
    cooldowns = {r[0]: r for r in _wdbc("SpellCooldowns.dbc")}
    categories = {r[0]: r for r in _wdbc("SpellCategories.dbc")}
    rune_cost = {r[0]: r for r in _wdbc("SpellRuneCost.dbc")}
    options = {r[0]: r for r in _wdbc("SpellClassOptions.dbc")}
    durations = {r[0]: r for r in _wdbc("SpellDuration.dbc")}

    rt = spell[RUNE_TAP]
    # Power type runes; 1 Blood, 0 Unholy, 0 Frost, no runic power gain.
    assert rt[14] == 5 and rune_cost[rt[26]][1:] == (1, 0, 0, 0)
    # HEAL_PCT 10: 10% of maximum health; no aura.
    assert [(e[1], e[3], e[5]) for e in effects[RUNE_TAP]] == [(136, 0, 10)]
    # 30 s cooldown, no GCD, no GCD category.
    assert (cooldowns[rt[37]][2], cooldowns[rt[37]][3], categories[rt[35]][6]) == (30000, 0, 0)

    # Will of the Necropolis 96171: 8 s, -100% PowerCost0 on Rune Tap's
    # family flag -> the next Rune Tap costs no rune.
    free = spell[WOTN_FREE_RUNE_TAP]
    assert durations[free[13]][1] == 8000
    (mod,) = effects[WOTN_FREE_RUNE_TAP]
    assert (mod[1], mod[3], mod[5], mod[12]) == (6, 108, -100, 14)
    rune_tap_mask = tuple(x & 0xFFFFFFFF for x in options[rt[36]][2:5])
    assert any(a & (b & 0xFFFFFFFF) for a, b in zip(rune_tap_mask, mod[18:21]))
    # The server script resets Rune Tap's cooldown and applies 96171.
    dk = _text(ROOT / "src/server/scripts/Spells/spell_dk.cpp")
    wotn = dk[dk.index("class spell_dk_will_of_the_necropolis"):]
    wotn = wotn[:wotn.index("};")]
    assert "GetTarget()->HealthBelowPctDamaged(30," in wotn
    assert "target->CastSpell(target, SPELL_DK_WILL_OF_THE_NECROPOLIS" in wotn
    assert "target->GetSpellHistory()->ResetCooldown(SPELL_DK_RUNE_TAP, true);" in wotn
    assert re.search(r"SPELL_DK_WILL_OF_THE_NECROPOLIS\s*= 96171\b", dk)
    # The candidate builder applies the same PowerCost0 modifier to rune costs,
    # so min_ready_runes 0 lets the free cast through.
    candidates = _text(CANDIDATES)
    power = candidates[candidates.index("bool HasEnoughPowerForProfileSpell"):]
    power = power[:power.index("\n}\n")]
    assert "modOwner->ApplySpellMod(spellInfo, SpellModOp::PowerCost0, runeRequirement);" in power
    assert re.search(r"SpellModOp::PowerCost0", _text(ROOT / "src/server/game/Spells/Spell.cpp"))
