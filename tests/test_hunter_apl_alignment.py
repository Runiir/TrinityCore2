from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_08_17_01_hunter_apl_alignment.sql"


def read_migration() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_marksmanship_pinned_apl_gates_are_typed_and_idempotent() -> None:
    migration = read_migration()

    assert "70d87383a9b92f30fb9e370c4676d3ce33b6e6b6" in migration
    assert "60aedd1aba0b508a4eedaf1a741fb568af1d508213804b1f675511b2c4f92ec6" in migration
    assert "`action`.`spell_id` = 1978" in migration
    assert "`action`.`max_target_health_pct` = 0.90" in migration
    assert "`action`.`min_primary_power_pct` = 0.66" in migration
    assert "`action`.`spell_id` = 19434" in migration
    assert "`action`.`min_target_health_pct` = 0.90" in migration
    assert "`max_cast_time_ms`)" in migration  # cast gate is insert-only
    assert "apl_fast_cast_below_e90" in migration
    assert "`action`.`spell_id` = 53209" in migration
    assert "chimera_shot,focus,sting_refresh,apl_not_e90" in migration
    assert "`action`.`forbidden_self_aura` = 53221" in migration
    assert "apl_steady_focus_expiring" in migration


def test_marksmanship_restores_the_missing_readiness_sequence_action() -> None:
    migration = read_migration()

    assert "`action`.`spell_id` = 23989" in migration
    assert "readiness,apl_strict_sequence" in migration
    assert " 25, 23989, 'offensive_cooldown'" in migration
    assert "0.95, 1, 1, 0.90, 'self'" in migration


def test_survival_execute_order_keeps_kill_shot_before_black_arrow() -> None:
    migration = read_migration()

    assert "66f2fa1560095697af336afdd7fa2c68d9f712bf96c76ade722a3270aa12f9ec" in migration
    assert "`action`.`spell_id` = 53351" in migration
    assert "`action`.`priority_bucket` = 2" in migration
    assert "before_black_arrow" in migration
    assert "GREATEST(`version`, 17)" in migration


def test_survival_multishot_is_only_a_sting_setup_when_needed() -> None:
    migration = read_migration()

    assert "`action`.`forbidden_owned_target_aura` = 1978" in migration
    assert "multi_shot,aoe,misdirection_transfer,apl_sting_missing" in migration
