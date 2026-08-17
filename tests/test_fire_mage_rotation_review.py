from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_08_17_03_fire_mage_apl_alignment.sql"


def test_fire_mage_apl_alignment_is_scoped_and_preserves_evidence_identity():
    sql = MIGRATION.read_text()

    assert "a33d85ae38cca571a13a6f53065b137b915972c6f54e39fdbd021c60acf0fd33" in sql
    assert "7a46a27109876072d848f9728fcbd990053a99c9b80f53536d19cbbd2800a6b5" in sql
    assert sql.count("`profile`.`class_id` = 8") >= 6
    assert sql.count("`profile`.`spec_tag` = 'fire'") >= 6
    assert sql.count("`profile`.`role` = 'dps'") >= 6


def test_fire_mage_apl_alignment_covers_priority_gates_and_single_target_fallback():
    sql = MIGRATION.read_text()

    assert "`action`.`spell_id` = 11129" in sql
    assert "`action`.`priority_bucket` = 1" in sql
    assert "`action`.`required_target_aura` = 0" in sql
    assert "`action`.`required_owned_target_aura` = 12654" in sql
    assert "`action`.`spell_id` = 92315" in sql
    assert "`action`.`spell_id` = 82731" in sql
    assert "`action`.`sort_order` = 18" in sql
    assert "`action`.`forbidden_target_aura` = 0" in sql
    assert "`action`.`forbidden_owned_target_aura` = 44457" in sql
    assert "`action`.`spell_id` = 133" in sql
    assert "`action`.`min_mana_pct` = 0.10" in sql
    assert "'fire_blast,single_target_fallback,instant'" in sql
    assert "61, 2136, 'spender'" in sql
    assert "6, 1, 'enemy'" in sql
    assert "NOT EXISTS" in sql
