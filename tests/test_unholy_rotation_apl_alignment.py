from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "sql/custom/world/2026_08_17_02_unholy_death_knight_apl_alignment.sql"
)
APL = Path("/tmp/wowsims-unholy-default.apl.json")


def _spell_ids(node: object) -> list[int]:
    found: list[int] = []
    if isinstance(node, dict):
        spell_id = node.get("spellId")
        if isinstance(spell_id, dict) and isinstance(spell_id.get("spellId"), int):
            found.append(int(spell_id["spellId"]))
        for value in node.values():
            found.extend(_spell_ids(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_spell_ids(value))
    return found


def test_unholy_outbreak_is_not_profile_blocked_by_runes() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    outbreak = sql[sql.index("SET `action`.`min_ready_runes` = 0") :]

    assert "profile`.`spec_tag` = 'unholy_death_knight'" in outbreak
    assert "action`.`spell_id` = 77575" in outbreak
    assert "action`.`mechanic_tags` = 'outbreak,diseases,pinned_apl,no_rune_gate'" in outbreak


def test_unholy_raise_dead_is_setup_only_when_ghoul_is_present() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    raise_dead = sql[sql.index("SET `action`.`forbids_pet` = 1") :]

    assert "profile`.`spec_tag` = 'unholy_death_knight'" in raise_dead
    assert "action`.`spell_id` = 46584" in raise_dead
    assert "action`.`mechanic_tags` = 'raise_dead,permanent_ghoul,persistent_setup_only'" in raise_dead


def test_pinned_unholy_apl_has_outbreak_but_no_combat_raise_dead() -> None:
    if not APL.exists():
        # The pinned source is an external review input; keep this test useful
        # in the normal checkout while allowing source-only CI without /tmp.
        return

    apl = json.loads(APL.read_text(encoding="utf-8"))
    priority = apl["priorityList"]
    assert 77575 in _spell_ids(priority)
    assert 46584 not in _spell_ids(priority)
    assert 46584 not in _spell_ids(apl["prepullActions"])
