from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_08_17_01_druid_dot_refresh_windows.sql"


def test_druid_refresh_migration_restores_balance_dot_windows() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "profile`.`spec_tag` = 'balance_druid'" in sql
    assert "action`.`spell_id` IN (8921, 5570, 93402)" in sql
    assert "action`.`forbidden_owned_target_aura` = 0" in sql
    assert "action`.`refresh_aura_below_ms` = 3000" in sql


def test_druid_refresh_migration_restores_feral_bleed_and_roar_windows() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "profile`.`spec_tag` = 'feral_druid_dps'" in sql
    assert "action`.`spell_id` IN (1822, 1079, 33876, 52610)" in sql
    assert sql.count("action`.`forbidden_owned_target_aura` = 0") == 2
    assert sql.count("action`.`refresh_aura_below_ms` = 3000") == 2
