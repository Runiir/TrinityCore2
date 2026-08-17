from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_08_17_02_elemental_apl_alignment.sql"
BASE_PROFILE = ROOT / "sql/custom/world/2026_06_21_00_bot_rotation_profiles.sql"


def _insert_rows(sql: str) -> dict[int, list[str]]:
    """Parse the two elemental INSERT rows without needing a SQL client."""

    def split_values(fragment: str) -> list[str]:
        values: list[str] = []
        current: list[str] = []
        quoted = False
        for char in fragment:
            if char == "'":
                quoted = not quoted
            if char == "," and not quoted:
                values.append("".join(current).strip().strip("'"))
                current = []
            else:
                current.append(char)
        values.append("".join(current).strip().rstrip(",); ").strip("'"))
        return values

    rows: dict[int, list[str]] = {}
    for line in sql.splitlines():
        if not line.startswith("((SELECT `id` FROM `bot_rotation_profile`"):
            continue
        values = split_values(line.split("),", 1)[1])
        rows[int(values[1])] = values
    return rows


def test_elemental_migration_adds_apl_fire_elemental_and_lava_burst_rows():
    sql = MIGRATION.read_text(encoding="utf-8")
    rows = _insert_rows(sql)

    assert set(rows) == {2894, 51505}

    fire_elemental = rows[2894]
    assert fire_elemental[0] == "5"
    assert fire_elemental[2] == "offensive_cooldown"
    assert "wowsims_66843" in fire_elemental[3]
    assert fire_elemental[5:9] == ["0", "1", "1", "0"]
    assert fire_elemental[9:12] == ["self", "ranged", "none"]

    lava_burst = rows[51505]
    assert lava_burst[0] == "15"
    assert lava_burst[2] == "builder"
    assert "flame_shock_required" in lava_burst[3]
    assert lava_burst[5:9] == ["1", "1", "2", "8050"]
    assert lava_burst[9:12] == ["enemy", "ranged", "none"]
    assert lava_burst[12:14] == ["12", "35"]


def test_elemental_migration_preserves_native_totem_setup_and_existing_rotation():
    migration = MIGRATION.read_text(encoding="utf-8")
    base = BASE_PROFILE.read_text(encoding="utf-8")

    # TryEnsureCombatTotems owns Searing Totem; adding a second profile row
    # would submit a duplicate setup cast and diverge from the native path.
    inserted_rows = _insert_rows(migration)
    assert 3599 not in inserted_rows
    assert "native combat-totem setup already owns Searing Totem" in migration

    # The alignment migration is additive: Flame Shock, Earth Shock, and the
    # single-target Lightning Bolt gate remain in the canonical profile.
    elemental_lines = [
        line
        for line in base.splitlines()
        if "spec_tag`='elemental_shaman'" in line and line.lstrip().startswith("((SELECT")
    ]
    assert any(", 8050," in line for line in elemental_lines)
    assert any(", 8042," in line for line in elemental_lines)
    assert any(", 403," in line for line in elemental_lines)


def test_elemental_rows_match_pinned_apl_priority_and_representable_gates():
    migration = MIGRATION.read_text(encoding="utf-8")
    rows = _insert_rows(migration)

    # WoWSims revision 70d87383 (APL SHA256
    # cdc73e0dac1a773a252ccb9eaadb35452e721a210af7b81e38d7b2c7d55d19a9)
    # orders Fire Elemental, Searing Totem, Lava Burst, Flame Shock, Earth
    # Shock, then Lightning Bolt.  Searing is native setup, while these two
    # rows fill the profile's missing actionable entries.
    assert "70d87383a9b92f30fb9e370c4676d3ce33b6e6b6" in migration
    assert "cdc73e0dac1a773a252ccb9eaadb35452e721a210af7b81e38d7b2c7d55d19a9" in migration
    assert int(rows[2894][0]) < int(rows[51505][0])
    assert "required Flame Shock aura" in migration
    assert "<=2-target gate" in migration
