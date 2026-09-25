"""Round 3 raid class rotations: enemy ceilings, self-cast rows, Vendetta, Drain Life.

Evidence is the BWD 10N round 2 runs (Magmaw smoke and the r02-b1 six-shard
batch). Each migration is replayed against native-shaped sqlite rows: it must
change exactly the intended rows and columns, be idempotent, and its commented
reverse block must restore the pre-migration table exactly.
"""
from __future__ import annotations

import sqlite3
import struct
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "sql/custom/world"
BOTS = ROOT / "src/server/game/Bots"
DBC = ROOT / "data/dbc/enUS"

BM = WORLD / "2026_09_26_10_beast_mastery_raid_enemy_ceilings.sql"
RET = WORLD / "2026_09_26_11_retribution_raid_holy_power_generators.sql"
DEMO = WORLD / "2026_09_26_12_demonology_raid_doomguard_and_targets.sql"
VENDETTA = WORLD / "2026_09_26_13_assassination_vendetta_native_range.sql"

COLUMNS = ("id", "profile_id", "sort_order", "spell_id", "category", "mechanic_tags",
           "damage_weight", "priority_bucket", "min_enemies", "max_enemies",
           "requires_melee_range", "requires_ranged_range", "target_selector",
           "min_range", "max_range", "enabled")

PROFILES = [
    # id, class_id, spec_tag, role, enabled
    (1, 3, "beast_mastery_hunter", "dps", 1),
    (2, 3, "marksmanship", "dps", 1),
    (3, 2, "retribution_paladin", "dps", 1),
    (4, 2, "protection", "tank", 1),
    (5, 9, "demonology_warlock", "dps", 1),
    (6, 9, "affliction_warlock", "dps", 1),
    (7, 4, "assassination_rogue", "dps", 1),
    (8, 4, "combat_rogue", "dps", 1),
]

# Pre-migration rows as produced by the earlier migrations (2026_07_18_00
# coverage, 2026_07_20_05/2026_07_27_01/2026_08_17_10 Retribution,
# 2026_07_25_0x Demonology, 2026_08_17_01 rogue alignment), plus scope probes.
ACTIONS = [
    # Beast Mastery.
    (101, 1, 10, 1978, "dot", "serpent_sting,dot", 0.86, 1, 1, 1, 0, 1, "enemy", 5, 35, 1),
    (102, 1, 20, 34026, "spender", "kill_command,pet_primary", 1.00, 1, 1, 1, 0, 1, "enemy", 5, 35, 1),
    (103, 1, 30, 53351, "execute", "kill_shot,execute", 1.00, 1, 1, 1, 0, 1, "enemy", 5, 35, 1),
    (104, 1, 40, 3044, "spender", "arcane_shot,focus_dump", 0.82, 3, 1, 1, 0, 1, "enemy", 5, 35, 1),
    (105, 1, 50, 77767, "resource_generator", "cobra_shot,focus_builder", 0.74, 4, 1, 1, 0, 1, "enemy", 5, 35, 1),
    (106, 1, 60, 2643, "aoe", "multi_shot,aoe", 0.88, 2, 3, 0, 0, 1, "enemy", 5, 35, 1),
    (107, 1, 70, 19577, "stun_cc", "intimidation,pet_control", 0.30, 3, 1, 1, 0, 1, "enemy", 5, 35, 1),
    (201, 2, 40, 3044, "spender", "arcane_shot,focus_dump", 0.82, 3, 1, 1, 0, 1, "enemy", 5, 35, 1),
    # Retribution.
    (301, 3, 10, 96231, "interrupt", "rebuke,interrupt", 0.15, 1, 1, 1, 1, 0, "enemy", 0, 5, 1),
    (302, 3, 20, 35395, "resource_generator", "crusader_strike,holy_power", 0.94, 1, 1, 1, 1, 0, "enemy", 0, 5, 1),
    (303, 3, 30, 85256, "spender", "templars_verdict,holy_power,holy_power_3", 1.05, 0, 1, 1, 1, 0, "enemy", 0, 5, 1),
    (304, 3, 40, 20271, "builder", "judgement,ranged_filler", 0.82, 2, 1, 1, 0, 0, "enemy", 0, 30, 1),
    (305, 3, 50, 879, "spender", "exorcism,proc", 0.88, 2, 1, 1, 0, 0, "enemy", 0, 30, 1),
    (306, 3, 60, 24275, "execute", "hammer_of_wrath,execute", 1.00, 1, 1, 1, 0, 0, "enemy", 0, 30, 1),
    (307, 3, 70, 53385, "aoe", "divine_storm,aoe", 0.90, 2, 4, 0, 1, 0, "enemy", 0, 5, 1),
    (308, 3, 2, 84963, "offensive_cooldown", "inquisition,self,buff,holy_power_3", 1.08, 0, 1, 0, 0, 0, "self", 0, 0, 1),
    (401, 4, 20, 35395, "threat_build", "crusader_strike,holy_power", 0.94, 1, 1, 1, 1, 0, "enemy", 0, 5, 1),
    # Demonology.
    (501, 5, 15, 18540, "offensive_cooldown", "summon_doomguard,guardian,pinned_apl", 1.20, 0, 1, 1, 0, 1, "enemy", 5, 18, 1),
    (502, 5, 55, 47897, "spender", "shadowflame,short_range,pinned_apl", 1.05, 1, 1, 0, 0, 0, "enemy", 0, 8, 1),
    (503, 5, 30, 348, "dot", "immolate,dot", 0.90, 1, 1, 1, 0, 1, "enemy", 0, 18, 1),
    (504, 5, 40, 172, "dot", "corruption,dot", 0.86, 2, 1, 1, 0, 1, "enemy", 0, 18, 1),
    (505, 5, 25, 603, "dot", "bane_of_doom,dot,pinned_apl", 0.98, 1, 1, 1, 0, 1, "enemy", 5, 18, 1),
    (506, 5, 50, 71521, "spender", "hand_of_guldan,primary", 1.00, 1, 1, 1, 0, 1, "enemy", 0, 18, 1),
    (507, 5, 17, 74434, "offensive_cooldown", "soulburn,soul_fire_setup,pinned_apl", 1.05, 1, 1, 1, 0, 0, "self", 0, 0, 1),
    (508, 5, 18, 6353, "offensive_cooldown", "soul_fire,soulburn_consumer,improved_soul_fire,pinned_apl", 1.10, 1, 1, 1, 0, 1, "enemy", 5, 18, 1),
    (509, 5, 60, 6353, "execute", "soul_fire,decimation", 0.94, 2, 1, 1, 0, 1, "enemy", 0, 18, 1),
    (510, 5, 66, 689, "resource_generator", "drain_life,health_recovery,resource_fallback,pinned_apl", 0.20, 0, 1, 0, 0, 1, "enemy", 5, 18, 1),
    (511, 5, 80, 1949, "aoe", "hellfire,aoe", 0.86, 2, 3, 0, 0, 0, "self", 0, 10, 1),
    (512, 5, 75, 29722, "builder", "incinerate,filler,pinned_apl", 0.82, 4, 1, 0, 0, 1, "enemy", 5, 18, 1),
    (601, 6, 5, 18540, "offensive_cooldown", "summon_doomguard,guardian,pinned_apl", 1.20, 0, 1, 0, 0, 0, "self", 0, 0, 1),
    (602, 6, 30, 348, "dot", "immolate,dot", 0.90, 1, 1, 1, 0, 1, "enemy", 0, 35, 1),
    # Assassination.
    (701, 7, 20, 79140, "offensive_cooldown", "vendetta,target,burst", 1.05, 1, 1, 0, 1, 0, "enemy", 0, 5, 1),
    (702, 7, 80, 1329, "builder", "mutilate,primary_builder,combo_builder", 1.00, 5, 1, 0, 1, 0, "enemy", 0, 5, 1),
    (801, 8, 20, 79140, "offensive_cooldown", "vendetta,target,burst", 1.05, 1, 1, 0, 1, 0, "enemy", 0, 5, 1),
]


def _database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE bot_rotation_profile (id INTEGER PRIMARY KEY, class_id INTEGER,"
               " spec_tag TEXT, role TEXT, enabled INTEGER)")
    db.execute("CREATE TABLE bot_rotation_action (" + ", ".join(
        f"`{name}` " + ("TEXT" if name in ("category", "mechanic_tags", "target_selector") else "NUMERIC")
        for name in COLUMNS) + ")")
    db.executemany("INSERT INTO bot_rotation_profile VALUES (?, ?, ?, ?, ?)", PROFILES)
    db.executemany("INSERT INTO bot_rotation_action VALUES (" + ",".join("?" * len(COLUMNS)) + ")",
                   ACTIONS)
    return db


def _rows(db: sqlite3.Connection) -> dict[int, dict]:
    db.row_factory = sqlite3.Row
    rows = {row["id"]: dict(row) for row in db.execute("SELECT * FROM bot_rotation_action")}
    db.row_factory = None
    return rows


def _forward(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("-- BEGIN REVERSE MIGRATION")[0]


def _reverse(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    body = lines[lines.index("-- BEGIN REVERSE MIGRATION") + 1:lines.index("-- END REVERSE MIGRATION")]
    assert body and all(line == "--" or line.startswith("-- ") for line in body)
    return "\n".join(line[3:] for line in body)


def _changes(before: dict[int, dict], after: dict[int, dict]) -> dict[int, dict]:
    return {
        row_id: {column: (before[row_id][column], after[row_id][column])
                 for column in COLUMNS
                 if before[row_id][column] != after[row_id][column] and column != "mechanic_tags"}
        for row_id in before if before[row_id] != after[row_id]
    }


def _replay(path: Path, tag: str) -> dict[int, dict]:
    db = _database()
    before = _rows(db)
    db.executescript(_forward(path))
    after = _rows(db)
    changes = _changes(before, after)
    for row_id in changes:
        assert after[row_id]["mechanic_tags"] == before[row_id]["mechanic_tags"] + "," + tag
    db.executescript(_forward(path))
    assert _rows(db) == after, "forward migration must be idempotent"
    db.executescript(_reverse(path))
    assert _rows(db) == before, "reverse block must restore the table exactly"
    return changes


def test_beast_mastery_generator_and_single_target_rows_have_no_one_enemy_ceiling() -> None:
    changes = _replay(BM, "bm_raid_enemy_ceiling_20260926")
    # Multi-Shot (min 3), Intimidation and the Marksmanship row are untouched.
    assert changes == {
        101: {"max_enemies": (1, 0)},
        102: {"max_enemies": (1, 0)},
        103: {"max_enemies": (1, 0)},
        104: {"max_enemies": (1, 2)},
        105: {"max_enemies": (1, 0)},
    }


def test_retribution_generators_admitted_and_divine_storm_leads_at_four() -> None:
    changes = _replay(RET, "ret_raid_holy_power_20260926")
    # Rebuke and the Protection Crusader Strike row are untouched.
    assert changes == {
        302: {"max_enemies": (1, 0)},
        303: {"max_enemies": (1, 0)},
        304: {"max_enemies": (1, 0)},
        305: {"max_enemies": (1, 0)},
        306: {"max_enemies": (1, 0)},
        307: {"sort_order": (70, 19), "damage_weight": (0.90, 1.00), "priority_bucket": (2, 1),
              "target_selector": ("enemy", "self"), "max_range": (5, 8)},
        308: {"category": ("offensive_cooldown", "buff")},
    }
    # Inquisition is a Holy Power buff, not a cooldown: as 'buff' it leaves the
    # raid trash/pre-pull offensive-cooldown reservation (Avenging Wrath and
    # Zealotry stay 'offensive_cooldown').
    # At four or more enemies Divine Storm and Crusader Strike share bucket 1.
    # The resolver scores weights (+ damage weight in every balance mode), so
    # Divine Storm's 1.00 ranks it ahead of Crusader Strike's 0.94, and
    # Templar's Verdict stays the bucket-0 spender.
    base = {row[0]: row for row in ACTIONS}
    assert base[302][6] < 1.00 and base[302][7] == 1
    assert base[303][7] == 0


def test_demonology_self_cast_doomguard_shadowflame_and_two_target_ceiling() -> None:
    changes = _replay(DEMO, "demo_raid_targets_20260926")
    assert changes == {
        501: {"max_enemies": (1, 0), "requires_ranged_range": (1, 0),
              "target_selector": ("enemy", "self"), "min_range": (5, 0), "max_range": (18, 0)},
        502: {"target_selector": ("enemy", "self")},
        503: {"max_enemies": (1, 2)},
        504: {"max_enemies": (1, 2)},
        505: {"max_enemies": (1, 2)},
        506: {"max_enemies": (1, 2)},
        507: {"max_enemies": (1, 2)},
        508: {"max_enemies": (1, 2)},
        509: {"max_enemies": (1, 2)},
    }
    # The Demonology Doomguard row now matches Affliction DPS-053 on every
    # targeting column; Drain Life, Hellfire and Incinerate are untouched.
    db = _database()
    db.executescript(_forward(DEMO))
    rows = _rows(db)
    for column in ("target_selector", "min_range", "max_range", "requires_ranged_range", "max_enemies"):
        assert rows[501][column] == rows[601][column], column
    assert rows[502]["max_range"] == 8 and rows[502]["min_range"] == 0


def test_vendetta_drops_only_its_five_yard_cap() -> None:
    # requires_melee_range = 1 keeps the melee hold; Combat's row is untouched.
    assert _replay(VENDETTA, "vendetta_native_range_20260926") == {701: {"max_range": (5, 0)}}


def test_prior_migrations_produced_the_replayed_pre_state() -> None:
    coverage = (WORLD / "2026_07_18_00_all_spec_rotation_profile_coverage.sql").read_text()
    bm = [line for line in coverage.splitlines() if "'beast_mastery_hunter' AND `role`='dps'), " in line]
    # Column order: ..., priority_bucket, min_enemies, max_enemies, max_target_health_pct, ...
    for spell in (1978, 34026, 53351, 3044, 77767):
        row = next(line for line in bm if f", {spell}, " in line)
        assert ", 1, 1, 1.00, 0, 0, 1, 'enemy'" in row or ", 1, 1, 0.20, 0, 0, 1, 'enemy'" in row, spell
    ret = [line for line in coverage.splitlines() if "'retribution_paladin' AND `role`='dps'), " in line]
    for spell in (35395, 85256, 20271, 879, 24275):
        row = next(line for line in ret if f", {spell}, " in line)
        assert ", 1, 1, 1.00, " in row or ", 1, 1, 0.20, " in row, spell
    alignment = (WORLD / "2026_08_17_10_phase8_melee_apl_alignment.sql").read_text()
    assert "SET a.`min_enemies` = 4" in alignment and "a.`spell_id` = 53385" in alignment
    burst = (WORLD / "2026_07_25_12_phase8_demonology_melee_burst.sql").read_text()
    assert "`action`.`max_range` = 18.0" in burst
    affliction = (WORLD / "2026_09_13_02_affliction_doomguard.sql").read_text()
    assert "`target_selector` = 'self'" in affliction and "`requires_ranged_range` = 0" in affliction


def _spell_ranges(spell_ids: set[int]) -> dict[int, tuple[int, float, int]]:
    def load(name: str):
        blob = (DBC / name).read_bytes()
        count, _fields, size, _strings = struct.unpack_from("<4I", blob, 4)
        return count, size, blob[20:20 + count * size]

    count, size, records = load("SpellRange.dbc")
    ranges = {}
    for index in range(count):
        record = records[index * size:(index + 1) * size]
        range_id, _min_hostile, _min_friendly, max_hostile, _max_friendly, flags = struct.unpack_from(
            "<IffffI", record, 0)
        ranges[range_id] = (max_hostile, flags)
    count, size, records = load("Spell.dbc")
    found = {}
    for index in range(count):
        record = records[index * size:(index + 1) * size]
        spell_id = struct.unpack_from("<I", record, 0)[0]
        if spell_id in spell_ids:
            range_index = struct.unpack_from("<I", record, 15 * 4)[0]
            found[spell_id] = (range_index, *ranges[range_index])
    return found


def test_native_range_facts_behind_the_row_changes() -> None:
    if not (DBC / "Spell.dbc").is_file():
        pytest.skip("client DBCs not hydrated")
    facts = _spell_ranges({18540, 47897, 53385, 79140, 1329})
    # Self-cast (SpellRange 1, 0 yd): Summon Doomguard, Shadowflame, Divine Storm.
    for spell in (18540, 47897, 53385):
        assert facts[spell][:2] == (1, 0.0), spell
    # Vendetta is a 30 yd non-melee spell; Mutilate is SPELL_RANGE_MELEE.
    assert facts[79140][:2] == (4, 30.0) and not facts[79140][2] & 1
    assert facts[1329][0] == 2 and facts[1329][2] & 1


def test_raid_health_recovery_gate_is_healer_owned_and_emergency_only(tmp_path: Path) -> None:
    source = tmp_path / "gate.cpp"
    source.write_text(r'''
#include "BotRaidHealthRecoveryGate.h"
#include <cassert>
#include <string>
int main() {
    using namespace BotRaidHealthRecoveryGate;
    int probes = 0;
    auto healer = [&probes]() { ++probes; return true; };
    auto noHealer = [&probes]() { ++probes; return false; };
    // Raid, tagged Drain Life, 60% health, a living healer: held.
    assert(Holds(true, true, 0.60f, healer));
    // Emergency health, no healer, a solo lane or an untagged row: released.
    assert(!Holds(true, true, 0.35f, healer));
    assert(!Holds(true, true, 0.20f, healer));
    assert(!Holds(true, true, 0.60f, noHealer));
    assert(!Holds(false, true, 0.60f, healer));
    assert(!Holds(true, false, 0.60f, healer));
    // The group walk only happens for a tagged raid row above the floor.
    assert(probes == 2);
    assert(std::string(HealthRecoveryTag) == "health_recovery");
    assert(std::string(RejectReason) == "raid_healer_owned_health_recovery");
}
''')
    binary = tmp_path / "gate"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(BOTS),
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def test_resolver_applies_the_health_recovery_gate_after_the_profile_health_gate() -> None:
    resolver = (BOTS / "BotWorldPopulationMgrCombatResolver.cpp").read_text()
    assert '#include "Bots/BotRaidHealthRecoveryGate.h"' in resolver
    profile_gate = resolver.index('candidate.RejectReason = "self_health_gate";')
    raid_gate = resolver.index("BotRaidHealthRecoveryGate::Holds(Cohort().Raid.RaidInstance,")
    assert profile_gate < raid_gate < resolver.index("float distance = selfCenteredHostileAction")
    gate = resolver[raid_gate:resolver.index("continue;", raid_gate)]
    assert "BotRaidHealthRecoveryGate::HealthRecoveryTag" in gate
    assert "selfHealthPct, livingGroupHealer" in gate
    assert "candidate.RejectReason = BotRaidHealthRecoveryGate::RejectReason;" in gate
    probe = resolver[resolver.index("auto livingGroupHealer"):resolver.index("auto effectiveSpellMinRange")]
    assert 'std::string(GetDungeonRole(member)) == "healer"' in probe
    assert "member != bot" in probe and "member->IsAlive()" in probe and "member->IsInMap(bot)" in probe
    # The Demonology Drain Life row is the only DPS health_recovery row.
    rows = [statement for path in WORLD.glob("*.sql")
            for statement in path.read_text().split(";") if "health_recovery" in statement]
    assert rows and all("demonology_warlock" in statement for statement in rows)
