from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROL_SQL = ROOT / "sql/custom/rollback/world/2026_09_21_00_balance_starfall_lunar_window_control.sql"
TREATMENT_SQL = ROOT / "sql/custom/world/2026_09_20_02_balance_starfall_lunar_window.sql"


def test_control_variant_removes_only_balance_starfall_lunar_window() -> None:
    sql = CONTROL_SQL.read_text(encoding="utf-8")

    assert "`class_id` = 11" in sql
    assert "`spec_tag` = 'balance_druid'" in sql
    assert "`role` = 'dps'" in sql
    assert "`spell_id` = 48505" in sql
    assert "`enabled` = 1" in sql
    assert "FIND_IN_SET('balance_starfall_lunar_window', `mechanic_tags`) > 0" in sql
    assert "REPLACE(\n    CONCAT(',', `mechanic_tags`, ','),\n    ',balance_starfall_lunar_window,',\n    ','\n)" in sql
    assert "balance_starfall_neutral_gate" not in sql
    assert "`spell_id` IN" not in sql


def test_control_variant_is_reversible_by_reviewed_treatment() -> None:
    control = CONTROL_SQL.read_text(encoding="utf-8")
    treatment = TREATMENT_SQL.read_text(encoding="utf-8")

    assert "balance_starfall_lunar_window" in control
    assert "balance_starfall_lunar_window" in treatment
    assert "FIND_IN_SET('balance_starfall_lunar_window', `mechanic_tags`) = 0" in treatment
    assert "`spell_id` = 48505" in treatment
    assert "`spec_tag` = 'balance_druid'" in treatment
