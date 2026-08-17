from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_08_17_10_phase8_melee_apl_alignment.sql"


def read_migration() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_migration_records_the_pinned_apl_identities() -> None:
    migration = read_migration()

    assert "70d87383a9b92f30fb9e370c4676d3ce33b6e6b6" in migration
    assert "9fbce00181b66b79cc305264bd38bd4b0d8ab83089b4002c14eae98dadcd288c" in migration
    assert "8a4f711ca6c1165dca340488c44f9b87f33f833932bfdc2b24cc6d46a971b65f" in migration
    assert "6a92bb6d87a28ce394c9a2f4038eca04977400a0f8f39de066e04c754dc5f7f0" in migration


def test_arms_updates_only_the_pinned_target_and_proc_gates() -> None:
    migration = read_migration()

    arms = migration[: migration.index("-- Fury:")]
    assert "p.`class_id` = 1" in arms
    assert "p.`spec_tag` = 'arms_warrior'" in arms
    assert "p.`role` = 'dps'" in arms
    assert "a.`spell_id` = 46924" in arms
    assert "SET a.`min_enemies` = 2" in arms
    assert "a.`spell_id` = 7384" in arms
    assert "SET a.`required_self_aura` = 60503" in arms


def test_fury_updates_preserve_native_spells_and_align_apl_gates() -> None:
    migration = read_migration()

    fury = migration[migration.index("-- Fury:") : migration.index("-- Retribution:")]
    assert "p.`class_id` = 1" in fury
    assert "p.`spec_tag` = 'fury_warrior'" in fury
    assert "p.`role` = 'dps'" in fury
    assert "a.`spell_id` = 1134" in fury
    assert "SET a.`min_primary_power_pct` = 0.75" in fury
    assert "SET a.`priority_bucket` = 1" in fury
    assert "a.`sort_order` = 25" in fury
    assert "a.`spell_id` = 5308" in fury
    assert "SET a.`priority_bucket` = 4" in fury
    assert "a.`sort_order` = 80" in fury
    assert "a.`spell_id` = 18499" in fury
    assert "SET a.`required_self_aura` = 46916" in fury
    assert "a.`spell_id` = 1464" in fury


def test_retribution_spends_holy_power_before_crusader_strike_and_keeps_st() -> None:
    migration = read_migration()

    ret = migration[migration.index("-- Retribution:") : migration.index("UPDATE `bot_rotation_profile`")]
    assert "p.`class_id` = 2" in ret
    assert "p.`spec_tag` = 'retribution_paladin'" in ret
    assert "p.`role` = 'dps'" in ret
    assert "SET a.`priority_bucket` = 0" in ret
    assert "a.`spell_id` = 85256" in ret
    assert "SET a.`min_enemies` = 4" in ret
    assert "a.`spell_id` = 53385" in ret


def test_profile_provenance_is_monotonic_and_spec_scoped() -> None:
    migration = read_migration()

    assert "GREATEST(`version`, 8)" in migration
    assert "phase8_melee_apl_alignment_2026_08_17" in migration
    assert "arms_warrior', 'fury_warrior'" in migration
    assert "retribution_paladin" in migration
