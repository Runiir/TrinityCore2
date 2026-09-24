"""Static checks for the Rune of the Fallen Crusader rate (2026_09_24_11).

The migration raises ``spell_enchant_proc_data`` ProcsPerMinute for enchant
3368 from the upstream 1.0 to the 2.0 used by the pinned WoWSims reference.
It is replayed forward and in reverse against an in-memory SQLite copy of the
live rows (world DB, read 2026-09-24). The evidence values in its header are
pinned, the client data is checked to leave the rate to the server row, and
the native per-hit chance arithmetic is taken from the pinned source text.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path

import pytest

from tools.bot_ml.build_validation_provisioning import SPELL_ITEM_ENCHANTMENT_FMT
from tools.bot_ml.wowsims_gear_binding import load_wdbc


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_24_11_fallen_crusader_ppm.sql"
REFERENCES = ROOT / "experiments/configs/all_spec_references_cata_p4_v1.json"
ENCHANT_DBC = ROOT / "data/dbc/enUS/SpellItemEnchantment.dbc"
PLAYER = ROOT / "src/server/game/Entities/Player/Player.cpp"
UNIT = ROOT / "src/server/game/Entities/Unit/Unit.cpp"

FALLEN_CRUSADER = 3368
UNHOLY_STRENGTH = 53365
ITEM_ENCHANTMENT_TYPE_COMBAT_SPELL = 1
WOWSIMS_REVISION = "70d87383a9b92f30fb9e370c4676d3ce33b6e6b6"
WOWSIMS_RUNEFORGING_SHA256 = "92c20622bfde48fb2e099cc0bfd1a2af5b9d2f33b3080cc7aeeb4b93e2853bad"
WOWSIMS_CALL = "NewDynamicProcManagerForEnchant(3368, 2.0, 0)"
UPSTREAM_SQL = "sql/old/ancient/3.1.3/05445_world_spell_enchant_proc_data.sql"
BLOOD_WEAPON_DELAY_MS = 3600  # item 78478, Item-sparse.db2 Delay
OLD_PPM, NEW_PPM = 1.0, 2.0

# Live rows (EnchantID, Chance, ProcsPerMinute, HitMask, AttributesMask).
LIVE_ROWS = (
    (803, 0.0, 6.0, 0, 0),
    (1894, 0.0, 3.0, 0, 0),
    (1900, 0.0, 1.0, 0, 0),
    (FALLEN_CRUSADER, 0.0, OLD_PPM, 0, 0),
    (3369, 0.0, 1.0, 0, 0),
    (3789, 0.0, 1.0, 0, 0),
    (4098, 0.0, 1.0, 0, 0),
    (4099, 0.0, 1.0, 0, 0),
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _executable(path: Path) -> str:
    return "\n".join(l for l in _text(path).splitlines() if not l.lstrip().startswith("--"))


def _header(path: Path) -> str:
    return "\n".join(l[3:] if l.startswith("-- ") else l[2:]
                     for l in _text(path).split("-- BEGIN REVERSE MIGRATION")[0].splitlines()
                     if l.startswith("--"))


def _reverse(path: Path) -> str:
    lines = _text(path).splitlines()
    block = lines[lines.index("-- BEGIN REVERSE MIGRATION") + 1 : lines.index("-- END REVERSE MIGRATION")]
    assert block and all(line.startswith("-- ") for line in block)
    return "\n".join(line[3:] for line in block)


def _statements(sql: str) -> list[str]:
    return [" ".join(s.split()) for s in sql.split(";") if s.strip()]


def _database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE spell_enchant_proc_data (EnchantID INTEGER PRIMARY KEY, "
        "Chance REAL NOT NULL DEFAULT 0, ProcsPerMinute REAL NOT NULL DEFAULT 0, "
        "HitMask INTEGER NOT NULL DEFAULT 0, AttributesMask INTEGER NOT NULL DEFAULT 0)"
    )
    db.executemany("INSERT INTO spell_enchant_proc_data VALUES (?, ?, ?, ?, ?)", LIVE_ROWS)
    return db


def _state(db: sqlite3.Connection) -> list[tuple]:
    return db.execute("SELECT * FROM spell_enchant_proc_data ORDER BY EnchantID").fetchall()


def test_statements_touch_only_the_fallen_crusader_rate():
    assert _statements(_executable(MIGRATION)) == [
        "UPDATE `spell_enchant_proc_data` SET `ProcsPerMinute` = 2 WHERE `EnchantID` = 3368"
    ]
    assert _statements(_reverse(MIGRATION)) == [
        "UPDATE `spell_enchant_proc_data` SET `ProcsPerMinute` = 1 "
        "WHERE `EnchantID` = 3368 AND `ProcsPerMinute` = 2"
    ]
    # No other enchant id appears in either statement.
    for sql in (_executable(MIGRATION), _reverse(MIGRATION)):
        assert {int(n) for n in re.findall(r"`EnchantID` = (\d+)", sql)} == {FALLEN_CRUSADER}


def test_forward_changes_only_enchant_3368_and_is_idempotent():
    db = _database()
    before = _state(db)
    db.executescript(_text(MIGRATION))
    after = _state(db)
    db.executescript(_text(MIGRATION))
    assert _state(db) == after

    changed = [(old, new) for old, new in zip(before, after) if old != new]
    assert changed == [(
        (FALLEN_CRUSADER, 0.0, OLD_PPM, 0, 0),
        (FALLEN_CRUSADER, 0.0, NEW_PPM, 0, 0),
    )]
    # Rune of Cinderglacier and the other 1 PPM rows keep their rate.
    assert [r for r in after if r[0] != FALLEN_CRUSADER] == [r for r in before if r[0] != FALLEN_CRUSADER]


def test_reverse_restores_the_live_row_and_leaves_a_later_rate_alone():
    db = _database()
    before = _state(db)
    db.executescript(_text(MIGRATION))
    db.executescript(_reverse(MIGRATION))
    assert _state(db) == before
    db.executescript(_reverse(MIGRATION))  # replaying the reverse is harmless
    assert _state(db) == before

    # A later migration's value is not clobbered by this reverse block.
    db.executescript(_text(MIGRATION))
    db.execute("UPDATE spell_enchant_proc_data SET ProcsPerMinute = 3 WHERE EnchantID = ?", (FALLEN_CRUSADER,))
    db.executescript(_reverse(MIGRATION))
    assert db.execute(
        "SELECT ProcsPerMinute FROM spell_enchant_proc_data WHERE EnchantID = ?", (FALLEN_CRUSADER,)
    ).fetchone() == (3.0,)


def test_header_pins_the_evidence_values():
    header = " ".join(_header(MIGRATION).split())
    for token in (
        WOWSIMS_REVISION,
        "sim/death_knight/runeforging.go line 95",
        WOWSIMS_RUNEFORGING_SHA256,
        WOWSIMS_CALL,
        "EnchantID 3368, Chance 0, ProcsPerMinute 1, HitMask 0, AttributesMask 0",
        UPSTREAM_SQL,
        "(3368, 0, 1.0, 0)",
        '"Chance to proc doubled"',
        "EffectPointsMin[0] 0, EffectArg[0] 53365",
        "floor(weapon delay ms * ProcsPerMinute / 600)",
        "78478 has delay 3600",
        "from 6% to 12%",
        "TANK-002",
    ):
        assert token in header, token
    # The WoWSims revision is the one the Blood reference is bound to.
    references = json.loads(_text(REFERENCES))["references"]
    blood = next(r for r in references if r["spec_target_id"] == "blood_death_knight")
    assert blood["provider"] == "WoWSims"
    assert blood["provider_revision"] == WOWSIMS_REVISION
    # The upstream TrinityCore row being replaced is the 1.0 quoted above.
    upstream = _text(ROOT / UPSTREAM_SQL)
    assert re.search(r"-- Rune of the Fallen Crusader\s*\(3368, 0, 1\.0,0\),", upstream)


def test_client_data_leaves_the_rate_to_the_server_row():
    values = next(
        row["values"]
        for row in load_wdbc(ENCHANT_DBC, SPELL_ITEM_ENCHANTMENT_FMT)
        if int(row["values"][0]) == FALLEN_CRUSADER
    )
    # Effect[0], EffectPointsMin[0], EffectArg[0]: a combat-spell enchant with
    # no fixed chance, so the spell_enchant_proc_data row sets the rate.
    assert int(values[2]) == ITEM_ENCHANTMENT_TYPE_COMBAT_SPELL
    assert int(values[5]) == 0
    assert int(values[11]) == UNHOLY_STRENGTH


def test_native_chance_per_hit_doubles_for_the_blood_tank_weapon():
    player = _text(PLAYER)
    assert "chance = GetPPMProcChance(proto->GetDelay(), entry->ProcsPerMinute, spellInfo);" in player
    unit = _text(UNIT)
    assert "return std::floor((WeaponSpeed * PPM) / 600.0f);" in unit

    def chance(ppm: float) -> float:
        return math.floor(BLOOD_WEAPON_DELAY_MS * ppm / 600.0)

    assert chance(OLD_PPM) == 6
    assert chance(NEW_PPM) == 12
    # WoWSims uses the same per-hit form: PPM * weapon speed / 60 s.
    assert NEW_PPM * (BLOOD_WEAPON_DELAY_MS / 1000.0) / 60.0 == pytest.approx(chance(NEW_PPM) / 100.0)
