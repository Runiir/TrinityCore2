from __future__ import annotations

import json
from pathlib import Path

from tools.bot_ml.review_rotation_mechanics import find_wowsims_apl, normalize_wowsims_apl


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_08_17_01_rogue_apl_alignment.sql"
REQUESTS = ROOT / "artifacts/all_spec_program/wowsims_exact_reference_bundle_v1/native_requests"


def _request(name: str) -> dict:
    return json.loads((REQUESTS / name).read_text(encoding="utf-8"))


def _apl_actions(request: dict) -> list[dict]:
    return normalize_wowsims_apl(find_wowsims_apl(request, player_index=0))["actions"]


def test_rogue_alignment_migration_is_scoped_and_uses_native_predicates() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    for spec in ("assassination_rogue", "combat_rogue"):
        assert f"`spec_tag` = '{spec}'" in sql
        assert "class_id` = 4" in sql
    assert "SET `enabled` = 0" in sql
    assert "`spell_id` = 1943" in sql
    assert "`min_combo_points` = 5" in sql
    assert "`max_combo_points` = 5" in sql
    assert "`required_self_aura` = 5171" in sql
    assert "`min_self_aura_remaining_ms` = 5000" in sql
    assert "`refresh_aura_below_ms` = 2000" in sql
    assert "maintain_owned_aura" in sql
    for forbidden in ("SetPower", "SetComboPoints", "AddAura", "TeleportTo"):
        assert forbidden not in sql


def test_combat_pinned_apl_has_no_rupture_and_requires_five_point_eviscerate() -> None:
    request = _request(
        "bc4592ecb16a62ce343422a77f0ad9ca748c92b1881fb77f2197960341e71dbf.json"
    )
    actions = _apl_actions(request)
    spell_ids = [action["identity"]["id"] for action in actions]

    assert 1943 not in spell_ids
    eviscerates = [action for action in actions if action["identity"]["id"] == 2098]
    assert len(eviscerates) == 1
    expression = json.dumps(eviscerates[0]["condition_expression"])
    assert '"currentComboPoints"' in expression
    assert '"val": "5"' in expression


def test_combat_revealing_strike_pinned_apl_requires_slice_and_dice_and_at_most_four_points() -> None:
    request = _request(
        "bc4592ecb16a62ce343422a77f0ad9ca748c92b1881fb77f2197960341e71dbf.json"
    )
    actions = _apl_actions(request)
    revealing = [action for action in actions if action["identity"]["id"] == 84617]

    assert len(revealing) == 2
    for action in revealing:
        expression = json.dumps(action["condition_expression"])
        assert '"auraRemainingTime"' in expression
        assert '"spellId": 5171' in expression
        assert '"currentComboPoints"' in expression
        assert '"val": "4"' in expression or '"val": "3"' in expression


def test_assassination_pinned_apl_refreshes_rupture_and_uses_five_point_cold_blood() -> None:
    request = _request(
        "40fe2430cd5094825a62bb92f576bad4022eaf044b800c0fa770d8ac5a971393.json"
    )
    actions = _apl_actions(request)
    rupture = [action for action in actions if action["identity"]["id"] == 1943]
    cold_blood = [action for action in actions if action["identity"]["id"] == 14177]

    assert len(rupture) == 2
    assert any('"dotRemainingTime"' in json.dumps(action["condition_expression"]) for action in rupture)
    assert len(cold_blood) == 1
    cold_blood_expression = json.dumps(cold_blood[0]["condition_expression"])
    assert '"currentComboPoints"' in cold_blood_expression
    assert '"val": "5"' in cold_blood_expression
