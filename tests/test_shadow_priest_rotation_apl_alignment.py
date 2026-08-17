from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_08_17_04_shadow_priest_apl_sequence.sql"


def _action_updates(sql: str) -> dict[int, str]:
    blocks = re.findall(
        r"UPDATE `bot_rotation_action`\s+SET .*?;",
        sql,
        flags=re.DOTALL,
    )
    updates: dict[int, str] = {}
    for block in blocks:
        match = re.search(r"AND `spell_id` = (\d+)", block)
        assert match, f"action update has no spell selector: {block}"
        spell_id = int(match.group(1))
        assert spell_id not in updates, f"duplicate update for spell {spell_id}"
        updates[spell_id] = block
    return updates


def test_shadow_burst_migration_encodes_the_fiend_first_apl_gate():
    sql = MIGRATION.read_text(encoding="utf-8")
    updates = _action_updates(sql)

    assert set(updates) == {34433}
    fiend = updates[34433]
    assert "`required_self_aura` = 87118" in fiend
    assert "`required_self_aura_stacks` = 5" in fiend
    assert "`mechanic_tags` = 'shadowfiend,pet,burst'" in fiend


def test_shadow_burst_migration_preserves_the_native_archangel_gate_until_live_proven():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "auraIsActive(34433)" in sql
    assert "existing 87118x5 gate" in sql
    assert "spell_id` = 87153" not in sql


def test_shadow_burst_migration_does_not_reintroduce_the_mind_blast_orb_gate():
    sql = MIGRATION.read_text(encoding="utf-8")

    # The previous blanket 8092 orb gate measurably starved the rotation.  A
    # sequence-only migration must remain scoped to the two burst actions.
    assert "spell_id` = 8092" not in sql
    assert "required_self_aura` = 87118" in sql
    assert "APL SHA256: 5899b39fdedfc369cafc3bb44b938eb22ab9964e71acd827178ce15812aac0b5" in sql
