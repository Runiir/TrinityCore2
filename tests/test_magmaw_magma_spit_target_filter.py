from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAGMAW = ROOT / (
    "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/"
    "boss_magmaw.cpp"
)
SPELL_MODULE = ROOT / (
    "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/"
    "spell_magmaw_magma_spit.cpp"
)
LOADER = ROOT / "src/server/scripts/EasternKingdoms/eastern_kingdoms_script_loader.cpp"
SQL = ROOT / "sql/custom/world/2026_08_28_00_bwd_magmaw_magma_spit_target_filter.sql"


def test_missile_filter_keeps_only_the_explicit_unit_and_does_not_reimplement_damage():
    source = SPELL_MODULE.read_text(encoding="utf-8")

    assert len(source.splitlines()) < 1000
    assert "SPELL_MAGMA_SPIT_MISSILE = 78359" in source
    assert '#include "Unit.h"' in source
    assert "WorldObject* explicitTarget = GetExplTargetUnit();" in source
    assert "if (!explicitTarget)" in source
    assert "targets.clear();" in source
    assert "targets.remove_if([explicitTarget](WorldObject* target)" in source
    assert "return target != explicitTarget;" in source
    assert "EFFECT_0, TARGET_UNIT_DEST_AREA_ENEMY" in source
    assert "using namespace BlackwingDescent::Magmaw;" in source
    assert "SetHitDamage" not in source
    assert "SetEffectValue" not in source
    assert "CastSpell" not in source


def test_native_targeting_selection_and_loader_are_separate_from_missile_filter():
    magmaw_source = MAGMAW.read_text(encoding="utf-8")
    loader_source = LOADER.read_text(encoding="utf-8")

    # 95280 remains the native source-area selector: 3 players in 10-player
    # raids and 8 players in 25-player raids. The new module only owns 78359.
    assert "SPELL_MAGMA_SPIT_TARGETING                  = 95280" in magmaw_source
    assert "SPELL_MAGMA_SPIT_MISSILE                    = 78359" in magmaw_source
    assert "RandomResize(targets, GetCaster()->GetMap()->Is25ManRaid() ? 8 : 3);" in magmaw_source
    assert "TARGET_UNIT_SRC_AREA_ENEMY" in magmaw_source[magmaw_source.index("class spell_magmaw_magma_spit") :]

    assert "void AddSC_boss_magmaw_spells();" in loader_source
    assert "AddSC_boss_magmaw_spells();" in loader_source
    assert loader_source.index("void AddSC_boss_magmaw_spells();") < loader_source.index(
        "void AddSC_boss_omnotron_defense_system();"
    )


def test_custom_world_migration_binds_only_the_missile_script_idempotently():
    sql = SQL.read_text(encoding="utf-8")

    assert "DELETE FROM `spell_script_names`" in sql
    assert "`spell_id` = 78359" in sql
    assert "ScriptName` <> 'spell_magmaw_magma_spit_missile'" in sql
    assert "VALUES (78359, 'spell_magmaw_magma_spit_missile')" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert "95280" not in sql
