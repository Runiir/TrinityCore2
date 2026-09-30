"""Raid-shard gear starts at its live native maximum durability.

The loadout writer stored an absolute 100 for every equipped and bagged item.
Item::LoadFromDB clamps a larger stored value to ItemTemplate::MaxDurability
but never raises a smaller one, so a raid chest (max 160) or two-hander (120)
entered the raid partly worn. MaxDurability is FillMaxDurability over the
item's DB2 entry after the live hotfix tables overwrote it (item 55064,
hotfixed to epic: 75), so no value computed from the client files is safe.
The writer now stores DURABILITY_CLAMPED_TO_NATIVE_MAXIMUM, above every
possible maximum, and the core's own load clamp sets each item to its live
maximum: min_durability_fraction reads 1.0 at the start.
"""

from __future__ import annotations

import copy
import re
import subprocess
from pathlib import Path

import pytest

from tests.test_raid_shard_plan import _plan
from tools.bot_ml.build_validation_provisioning import gem_item_enchant_map
from tools.raid_program.raid_loadout import DURABILITY_CLAMPED_TO_NATIVE_MAXIMUM, expected_inventory
from tools.raid_program.raid_loadout_sql import build_raid_shard_character_sql, prepare_config

ROOT = Path(__file__).resolve().parents[1]
DBC = ROOT / "data/dbc/enUS"
GEAR = ROOT / "dataset/validation_gear_profiles/profiles.json"
OBJECT_MGR = ROOT / "src/server/game/Globals/ObjectMgr.cpp"
ITEM = ROOT / "src/server/game/Entities/Item/Item.cpp"
WORLD = ROOT / "src/server/game/World/World.cpp"
SCHEMA = ROOT / "sql/base/characters_database.sql"
MAGMAW = "blackwing_descent_10n_magmaw_c0_diagnostic"
CHIMAERON = "blackwing_descent_10n_chimaeron_c0_diagnostic"

hydrated = pytest.mark.skipif(not GEAR.is_file() or not (DBC / "Item-sparse.db2").is_file(),
                              reason="DVC gear profiles or client DBCs not hydrated")


def _compile_and_run(tmp_path: Path, program: str) -> str:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    subprocess.run(["g++", "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common"),
                    str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return result.stdout


def _fill_max_durability() -> str:
    text = OBJECT_MGR.read_text(encoding="utf-8")
    start = text.index("uint32 FillMaxDurability(uint32 itemClass")
    function = text[start:re.compile(r"\n\};?\n").search(text, start).end()]
    assert "FillDisenchantFields" not in function
    return function


def _load_clamp() -> str:
    """Item::LoadFromDB's durability block, verbatim."""
    text = ITEM.read_text(encoding="utf-8")
    load = text[text.index("bool Item::LoadFromDB("):]
    start = load.index("    uint32 durability = fields[9].GetUInt16();")
    end = load.index("        need_save = true;\n    }\n", start) + len("        need_save = true;\n    }\n")
    block = load[start:end]
    assert "SetUInt32Value(ITEM_FIELD_MAXDURABILITY, proto->MaxDurability);" in block
    assert "if (durability > proto->MaxDurability && !HasFlag(ITEM_FIELD_FLAGS, ITEM_FIELD_FLAG_WRAPPED))" in block
    return block


def test_the_sentinel_exceeds_every_native_maximum_and_fits_the_column(tmp_path: Path) -> None:
    # The whole domain FillMaxDurability indexes: its largest result.
    program = r'''
#include <cstdint>
#include <cstdio>
typedef std::uint32_t uint32;
enum { ITEM_CLASS_WEAPON = 2, ITEM_CLASS_ARMOR = 4 };
#define MAX_ITEM_QUALITY 8
#define MAX_INVTYPE 29
#define MAX_ITEM_SUBCLASS_WEAPON 21
enum { INVTYPE_ROBE = 20 };
''' + _fill_max_durability() + r'''
int main()
{
    uint32 largest = 0;
    for (uint32 itemClass = 0; itemClass < 32; ++itemClass)
        for (uint32 quality = 0; quality < MAX_ITEM_QUALITY; ++quality)
            for (uint32 level = 0; level <= 1000; ++level)
            {
                uint32 const kinds = itemClass == ITEM_CLASS_WEAPON ? MAX_ITEM_SUBCLASS_WEAPON : MAX_INVTYPE;
                for (uint32 kind = 0; kind < kinds; ++kind)
                {
                    uint32 const value = itemClass == ITEM_CLASS_WEAPON
                        ? FillMaxDurability(itemClass, kind, 0, quality, level)
                        : FillMaxDurability(itemClass, 0, kind, quality, level);
                    largest = value > largest ? value : largest;
                }
            }
    std::printf("%u\n", largest);
    return 0;
}
'''
    largest = int(_compile_and_run(tmp_path, program).strip())
    assert largest == 195
    assert largest < DURABILITY_CLAMPED_TO_NATIVE_MAXIMUM == 65535
    schema = SCHEMA.read_text(encoding="utf-8")
    table = schema[schema.index("CREATE TABLE `item_instance`"):]
    assert "`durability` smallint unsigned NOT NULL" in table[:table.index(") ENGINE")]
    # MaxDurability has exactly one writer, over the hotfixed DB2 entry, and
    # item templates are built after the hotfix tables are applied.
    writers = [path for path in (ROOT / "src/server/game").rglob("*.cpp")
               if re.search(r"\bMaxDurability\s*=\s*FillMaxDurability", path.read_text(errors="replace"))]
    assert writers == [OBJECT_MGR]
    world = WORLD.read_text(encoding="utf-8")
    assert world.index("sDB2Manager.LoadHotfixData();") < world.index("sObjectMgr->LoadItemTemplates();")


def test_the_core_load_clamp_starts_every_item_at_its_live_maximum(tmp_path: Path) -> None:
    program = r'''
#include "Bots/BotMemberInstanceState.h"
#include <cstdio>
#include <vector>

enum { ITEM_FIELD_DURABILITY, ITEM_FIELD_MAXDURABILITY, ITEM_FIELD_FLAGS, ITEM_FIELD_COUNT };
enum : uint32 { ITEM_FIELD_FLAG_WRAPPED = 0x00000008 };
struct Field { uint32 Value = 0; uint16 GetUInt16() const { return uint16(Value); } };
struct Proto { uint32 MaxDurability = 0; };

static int failures = 0;
#define CHECK(condition, message) do { if (!(condition)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, message); ++failures; } } while (0)

struct LoadedItem
{
    uint32 Values[ITEM_FIELD_COUNT] = {};
    void SetUInt32Value(int index, uint32 value) { Values[index] = value; }
    uint32 GetUInt32Value(int index) const { return Values[index]; }
    bool HasFlag(int index, uint32 flag) const { return (Values[index] & flag) != 0; }

    // The stored item_instance row as Item::LoadFromDB reads it.
    bool Load(uint32 stored, uint32 maxDurability)
    {
        Field fields[10];
        fields[9].Value = stored;
        Proto template_;
        template_.MaxDurability = maxDurability;
        Proto const* proto = &template_;
        bool need_save = false;
''' + _load_clamp() + r'''
        return need_save;
    }
};

static float StartFraction(uint32 stored, std::vector<uint32> const& maxima, bool& saved)
{
    std::vector<BotMemberInstanceState::Durability> worn;
    saved = true;
    for (uint32 maximum : maxima)
    {
        LoadedItem item;
        bool const needSave = item.Load(stored, maximum);
        saved = saved && (needSave || stored <= maximum);
        worn.push_back({ item.GetUInt32Value(ITEM_FIELD_DURABILITY),
            item.GetUInt32Value(ITEM_FIELD_MAXDURABILITY) });
    }
    float fraction = -1.0f;
    CHECK(BotMemberInstanceState::MinDurabilityFraction(worn, fraction), "a worn item exists");
    return fraction;
}

int main()
{
    // A raid set: ring and trinket (0), bracers (55), a hotfixed epic (75;
    // its client entry gives 65), helm (95), one-hander (105), legs and
    // two-hander (120), chest and shield (160), the largest possible (195).
    std::vector<uint32> const maxima = { 0, 55, 65, 75, 95, 105, 120, 160, 195 };
    bool saved = false;
    float const start = StartFraction(''' + str(DURABILITY_CLAMPED_TO_NATIVE_MAXIMUM) + r''', maxima, saved);
    CHECK(start == 1.0f, "every item starts at its live maximum");
    CHECK(saved, "the clamp persists the maximum (CHAR_UPD_ITEM_INSTANCE_ON_LOAD)");
    for (uint32 maximum : maxima)
    {
        LoadedItem item;
        item.Load(''' + str(DURABILITY_CLAMPED_TO_NATIVE_MAXIMUM) + r''', maximum);
        CHECK(item.GetUInt32Value(ITEM_FIELD_DURABILITY) == maximum, "clamped to exactly the maximum");
    }
    // Negative controls: the old absolute 100, and a value computed from the
    // client entry of the hotfixed item, both start worn.
    float const old = StartFraction(100, maxima, saved);
    CHECK(old == 100.0f / 195.0f, "100 of the largest maximum");
    CHECK(StartFraction(100, { 160 }, saved) == 0.625f, "a raid chest started at 100 of 160");
    float const client = StartFraction(65, { 75 }, saved);
    CHECK(client < 1.0f, "65 of the hotfixed 75");
    std::printf("%.4f %.4f %.4f\n", start, old, client);
    return failures ? 1 : 0;
}
'''
    start, old, client = map(float, _compile_and_run(tmp_path, program).split())
    assert start == 1.0 and old < 1.0 and client < 1.0


@pytest.fixture(scope="module")
def config() -> dict:
    return prepare_config(_plan(), GEAR, DBC, [MAGMAW, CHIMAERON])


@hydrated
def test_every_gear_row_stores_the_clamp_sentinel(config) -> None:
    gems = gem_item_enchant_map(DBC)
    gear = 0
    for scenario in config["scenarios"]:
        for bot in scenario["bots"]:
            for row in expected_inventory(bot, config.get("default_consumables", []), gems, DBC):
                if row["kind"] in ("equipped", "bagged"):
                    assert row["durability"] == DURABILITY_CLAMPED_TO_NATIVE_MAXIMUM, row
                    gear += 1
                elif row["kind"] == "bag":
                    assert row["durability"] == 0
                else:
                    assert row["kind"] == "consumable" and row["durability"] == 1
    assert gear > 100


@hydrated
def test_sql_writes_the_sentinel_unwrapped_and_honours_an_explicit_value(config) -> None:
    sql = build_raid_shard_character_sql(config, DBC, _plan())
    scenario = next(row for row in config["scenarios"] if row["id"] == MAGMAW)
    bot = scenario["bots"][0]
    item = bot["equipment"][0]
    rows = [line for line in sql.splitlines()
            if line.startswith("INSERT INTO `characters`.`item_instance`")
            and re.search(rf"SELECT \d+, {int(item['item_id'])}, c\.`guid`", line)
            and f"c.`name` = '{bot['name']}'" in line]
    assert rows
    columns = rows[0][rows[0].index("(") + 1:rows[0].index(")")].replace("`", "").split(", ")
    values = rows[0][rows[0].index("SELECT ") + len("SELECT "):].split(", ")
    stored = dict(zip(columns, values))
    assert int(stored["durability"]) == DURABILITY_CLAMPED_TO_NATIVE_MAXIMUM
    # Not wrapped: the core clamps only unwrapped items.
    assert int(stored["flags"]) == 0
    # A profile that states a durability keeps it (a deliberate worn-gear test).
    worn = copy.deepcopy(bot)
    for row in worn["equipment"]:
        row["durability"] = 7
    for physical in worn["loadout"]["physical_items"]:
        physical["item"]["durability"] = 7
    rows = expected_inventory(worn, [], gem_item_enchant_map(DBC), DBC)
    assert {row["durability"] for row in rows if row["kind"] in ("equipped", "bagged")} == {7}
