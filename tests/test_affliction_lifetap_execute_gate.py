from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE_HEADER = ROOT / "src/server/game/Bots/BotClassSpecActionProfile.h"
PROFILE_DB = ROOT / "src/server/game/Bots/BotClassSpecActionProfileDb.cpp"
PROFILE_CANDIDATES = ROOT / "src/server/game/Bots/BotClassSpecActionProfileCandidates.cpp"
CONTROLLER = ROOT / "src/server/game/Bots/BotControllerCombat.cpp"
COMBAT_RESOLVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
COMBAT_SPELL = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatSpell.cpp"
CALIBRATION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationBot.cpp"
ROTATION_CONTRACT = ROOT / "tools/bot_ml/build_phase4_rotation_contract.py"
ROTATION_REVIEW = ROOT / "tools/bot_ml/review_rotation_mechanics.py"
MIGRATION = ROOT / "sql/custom/world/2026_08_23_05_affliction_lifetap_hostile_health_gate.sql"


def hostile_target_gate_allows(target_health_pct: float, threshold: float) -> bool:
    return target_health_pct > threshold


def test_execute_boundary_is_strict_and_above_execute_remains_eligible() -> None:
    assert not hostile_target_gate_allows(0.25, 0.25)
    assert not hostile_target_gate_allows(0.20, 0.25)
    assert hostile_target_gate_allows(0.250001, 0.25)
    assert hostile_target_gate_allows(1.0, 0.25)


def test_gate_is_typed_and_reusable_not_spell_hardcoded() -> None:
    header = PROFILE_HEADER.read_text(encoding="utf-8")
    for source in (
        PROFILE_CANDIDATES,
        CONTROLLER,
        COMBAT_RESOLVER,
        COMBAT_SPELL,
        CALIBRATION,
    ):
        text = source.read_text(encoding="utf-8")
        assert "MeetsHostileTargetHealthGate" in text
        assert "1454" not in text
    assert "float MinHostileTargetHealthPct = 0.0f;" in header
    assert "hostileTargetHealthPct > spell.MinHostileTargetHealthPct" in header


def test_profile_loader_and_review_export_the_new_gate() -> None:
    db = PROFILE_DB.read_text(encoding="utf-8")
    assert "a.min_hostile_target_health_pct" in db
    assert "spell.MinHostileTargetHealthPct = fields[76].GetFloat();" in db
    assert "min_hostile_target_health_pct" in db
    assert "min_hostile_target_health_pct" in ROTATION_CONTRACT.read_text(
        encoding="utf-8"
    )
    assert "min_hostile_target_health_pct" in ROTATION_REVIEW.read_text(
        encoding="utf-8"
    )


def test_life_tap_migration_preserves_self_target_and_sets_only_affliction() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS `min_hostile_target_health_pct`" in migration
    assert "`action`.`min_hostile_target_health_pct` = 0.25" in migration
    assert "`profile`.`class_id` = 9" in migration
    assert "`profile`.`spec_tag` = 'affliction_warlock'" in migration
    assert "`profile`.`role` = 'dps'" in migration
    assert re.findall(r"`action`\.`spell_id`\s*=\s*(\d+)", migration) == ["1454"]
    assert "target_selector" not in migration


def test_all_modified_bot_sources_remain_below_line_limit() -> None:
    for source in (
        PROFILE_HEADER,
        PROFILE_DB,
        PROFILE_CANDIDATES,
        CONTROLLER,
        COMBAT_RESOLVER,
        COMBAT_SPELL,
        CALIBRATION,
    ):
        assert len(source.read_text(encoding="utf-8").splitlines()) < 1000
