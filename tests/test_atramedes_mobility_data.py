"""Pins the Atramedes air-phase mobility table to the 4.3.4 client data.

BotAtramedesMobility.h models the canonical roster's kite extensions (Sprint,
Dash, Stampeding Roar, Aspect of the Cheetah, Blink, Disengage) and Ice
Block. Every speed, displacement, duration and cooldown there must be the
client row (Spell.dbc, SpellEffect.dbc, SpellDuration.dbc, SpellCooldowns.dbc,
SpellRadius.dbc), not an invented number.
"""
from __future__ import annotations

import re
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DBC = ROOT / "data/dbc/enUS"
HEADER = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/"
          "Atramedes/BotAtramedesMobility.h")
FACTS = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/"
         "Atramedes/BotAtramedesFacts.h")

# Spell.dbc (4.3.4) columns used here.
SPELL_DURATION = 13
SPELL_COOLDOWNS = 37
# SpellEffect.dbc columns.
EFFECT_TYPE, EFFECT_AURA, EFFECT_BASE, EFFECT_MISC = 1, 3, 5, 12
EFFECT_RADIUS, EFFECT_SPELL, EFFECT_INDEX = 15, 24, 25
AURA_MOD_INCREASE_SPEED = 31
EFFECT_LEAP, EFFECT_LEAP_BACK = 29, 138
# Server gravity (MotionMaster / JumpTo): Movement::gravity.
GRAVITY = 19.29110527038574


def _wdbc(name: str) -> list[bytes]:
    data = (DBC / name).read_bytes()
    magic, count, fields, size, _ = struct.unpack_from("<4s4i", data)
    assert magic == b"WDBC" and size == fields * 4
    return [data[20 + i * size:20 + (i + 1) * size] for i in range(count)]


def _u32(row: bytes, index: int) -> int:
    return struct.unpack_from("<I", row, index * 4)[0]


def _i32(row: bytes, index: int) -> int:
    return struct.unpack_from("<i", row, index * 4)[0]


def _f32(row: bytes, index: int) -> float:
    return struct.unpack_from("<f", row, index * 4)[0]


@pytest.fixture(scope="module")
def client() -> dict:
    if not (DBC / "Spell.dbc").is_file():
        pytest.skip("4.3.4 client DBC files are not extracted in this checkout")
    spells = {_u32(row, 0): row for row in _wdbc("Spell.dbc")}
    effects: dict[int, list[bytes]] = {}
    for row in _wdbc("SpellEffect.dbc"):
        effects.setdefault(_u32(row, EFFECT_SPELL), []).append(row)
    durations = {_u32(row, 0): _i32(row, 1) for row in _wdbc("SpellDuration.dbc")}
    cooldowns = {_u32(row, 0): (_u32(row, 1), _u32(row, 2)) for row in _wdbc("SpellCooldowns.dbc")}
    radii = {_u32(row, 0): _f32(row, 1) for row in _wdbc("SpellRadius.dbc")}
    return {"spells": spells, "effects": effects, "durations": durations,
            "cooldowns": cooldowns, "radii": radii}


def _abilities() -> list[dict]:
    text = HEADER.read_text(encoding="utf-8")
    constants = {name: int(value) for name, value in
                 re.findall(r"inline constexpr uint32 (\w+) = (\d+);", text)}
    rows = re.findall(
        r"\{ (\w+), Kind::(\w+), ([\d.]+)f, ([\d.]+)f, (\d+), (\d+), (\w+), (true|false),",
        text)
    assert len(rows) == 6
    return [{"id": constants[spell], "kind": kind, "pct": float(pct), "yards": float(yards),
             "duration": int(duration), "cooldown": int(cooldown),
             "form": 0 if form == "0" else constants[form]}
            for spell, kind, pct, yards, duration, cooldown, form, _ in rows]


def _duration_ms(client: dict, spell: int) -> int:
    duration = client["durations"].get(_u32(client["spells"][spell], SPELL_DURATION), 0)
    return max(duration, 0)


def _cooldown_ms(client: dict, spell: int) -> int:
    return max(client["cooldowns"].get(_u32(client["spells"][spell], SPELL_COOLDOWNS), (0, 0)))


def test_mobility_table_matches_client_rows(client: dict) -> None:
    for ability in _abilities():
        spell = ability["id"]
        assert spell in client["spells"], spell
        effects = client["effects"][spell]
        assert ability["cooldown"] == _cooldown_ms(client, spell), spell
        if ability["kind"] == "Speed":
            speed = [row for row in effects if _u32(row, EFFECT_AURA) == AURA_MOD_INCREASE_SPEED]
            assert speed and ability["pct"] == _i32(speed[0], EFFECT_BASE), spell
            assert ability["duration"] == _duration_ms(client, spell), spell
        elif ability["kind"] == "LeapForward":
            leap = [row for row in effects if _u32(row, EFFECT_TYPE) == EFFECT_LEAP]
            assert leap and ability["yards"] == client["radii"][_u32(leap[0], EFFECT_RADIUS)], spell
        else:
            leap = [row for row in effects if _u32(row, EFFECT_TYPE) == EFFECT_LEAP_BACK]
            assert leap, spell
            horizontal = _i32(leap[0], EFFECT_MISC) / 10.0
            vertical = _i32(leap[0], EFFECT_BASE) / 10.0
            assert ability["yards"] == pytest.approx(horizontal * 2.0 * vertical / GRAVITY, abs=0.01)


def test_ice_block_and_hypothermia_rows(client: dict) -> None:
    facts = FACTS.read_text(encoding="utf-8")
    assert "IceBlockAura = 45438" in facts and "HypothermiaAura = 41425" in facts
    assert _duration_ms(client, 45438) == 10000
    assert _cooldown_ms(client, 45438) == 300000
    assert _duration_ms(client, 41425) == 30000
    # Immunity to every school (39 SCHOOL_IMMUNITY, misc 1 physical and
    # 126 the magic schools) and SPELL_ATTR1_DISPEL_AURAS_ON_IMMUNITY
    # (0x8000): it strips the physical Tracking aura 78092.
    effects = client["effects"][45438]
    schools = sorted(_i32(row, EFFECT_MISC) for row in effects if _u32(row, EFFECT_AURA) == 39)
    assert schools == [1, 126]
    assert _u32(client["spells"][45438], 2) & 0x8000
    tracking = client["spells"][78092]
    assert _u32(tracking, 25) == 1  # physical school
    assert not _u32(tracking, 1) & 0x20000000  # not unaffected by invulnerability
    # The breath hit (78353, fire) is not unaffected by invulnerability.
    assert not _u32(client["spells"][78353], 1) & 0x20000000


def test_ghost_wolf_has_a_cast_time_and_is_left_out(client: dict) -> None:
    ghost_wolf = client["spells"][2645]
    cast_times = {_u32(row, 0): _i32(row, 1) for row in _wdbc("SpellCastTimes.dbc")}
    assert cast_times[_u32(ghost_wolf, 12)] == 2000
    assert all(ability["id"] != 2645 for ability in _abilities())
