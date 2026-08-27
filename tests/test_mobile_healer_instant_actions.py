from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_08_27_00_mobile_healer_instant_actions.sql"
BASE_PROFILE = ROOT / "sql/custom/world/2026_06_21_00_bot_rotation_profiles.sql"


def _split_values(fragment: str) -> list[str]:
    values: list[str] = []
    current: list[str] = []
    quoted = False
    for char in fragment:
        if char == "'":
            quoted = not quoted
        if char == "," and not quoted:
            value = "".join(current).strip().rstrip(",); ").strip("'")
            if value:
                values.append(value)
            current = []
        else:
            current.append(char)
    value = "".join(current).strip().rstrip(",); ").strip("'")
    if value:
        values.append(value)
    return values


def _insert_rows(sql: str) -> dict[int, list[str]]:
    rows: dict[int, list[str]] = {}
    for line in sql.splitlines():
        if not line.startswith("((SELECT `id` FROM `bot_rotation_profile`"):
            continue
        values = _split_values(line.split("),", 1)[1])
        rows[int(values[1])] = values
    return rows


def test_mobile_healer_rows_are_exact_instant_single_target_actions() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    rows = _insert_rows(sql)

    assert set(rows) == {17, 20473}
    assert "`requires_instant_cast`" in sql
    assert "`profile`.`class_id`, `profile`.`spec_tag`, `profile`.`role`, `action`.`spell_id`" in sql

    assert rows[20473] == [
        "15", "20473", "heal_fast", "holy_shock,triage,instant", "1.00",
        "0.85", "0", "0.94", "0", "lowest_ally", "healer_support", "none",
        "40", "1", "0", "1", "0.94",
    ]
    assert rows[17] == [
        "5", "17", "heal_fast", "power_word_shield,absorb,instant,triage", "1.35",
        "1.00", "0", "0.94", "6788", "lowest_ally", "healer_support", "none",
        "40", "1", "17", "1", "0.94",
    ]


def test_mobile_healer_migration_is_repeatable_and_does_not_change_other_actions() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    base = BASE_PROFILE.read_text(encoding="utf-8")
    rows = _insert_rows(sql)

    assert "(2, 'holy_paladin', 'healer', 20473)" in sql
    assert "(5, 'discipline_priest', 'healer', 17)" in sql
    assert sql.index("DELETE `action`") < sql.index("INSERT INTO `bot_rotation_action`")
    assert ", 20473," not in base
    assert ", 17," not in base

    # Model the migration's targeted delete plus fixed inserts.  A second run
    # must replace the same two spell keys, while unrelated profile actions
    # survive unchanged.
    snapshot = {
        ("holy_paladin", 20473): ("stale",),
        ("discipline_priest", 17): ("stale",),
        ("holy_paladin", 19750): ("keep",),
    }

    def apply(state: dict[tuple[str, int], tuple[str, ...]]) -> dict[tuple[str, int], tuple[str, ...]]:
        next_state = {
            key: value
            for key, value in state.items()
            if key not in {("holy_paladin", 20473), ("discipline_priest", 17)}
        }
        next_state[("holy_paladin", 20473)] = tuple(rows[20473])
        next_state[("discipline_priest", 17)] = tuple(rows[17])
        return next_state

    once = apply(snapshot)
    assert apply(once) == once
    assert once[("holy_paladin", 19750)] == ("keep",)
