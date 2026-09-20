from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotClassSpecActionProfileCandidates.cpp"
MIGRATION = ROOT / "sql/custom/world/2026_09_20_00_balance_starsurge_neutral_opener.sql"


def test_balance_starsurge_neutral_gate_is_a_typed_native_predicate() -> None:
    source = " ".join(SOURCE.read_text(encoding="utf-8").split())

    predicate = (
        'HasMechanicTag(spell.MechanicTags, "balance_starsurge_neutral_gate")'
        ' and !bot->HasAura(48517) && !bot->HasAura(48518)'
        ' and bot->GetPower(POWER_ECLIPSE) == 0'
    )
    assert predicate.replace(" and ", " && ") in source
    assert 'return "balance_neutral_opener";' in source
    assert "SetPower(POWER_ECLIPSE" not in source


def test_balance_migration_tags_only_starsurge_and_is_idempotent() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "`spec_tag` = 'balance_druid'" in sql
    assert "`spell_id` = 78674" in sql
    assert "balance_starsurge_neutral_gate" in sql
    assert "FIND_IN_SET('balance_starsurge_neutral_gate', `mechanic_tags`) = 0" in sql
    assert "`spell_id` IN (8921, 5570, 93402)" not in sql
