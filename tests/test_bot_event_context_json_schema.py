from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/updates/characters/4.3.4/2026_08_24_00_characters_bot_event_context_json_mediumtext.sql"
EVENT_SCHEMA = ROOT / "sql/updates/characters/4.3.4/2026_06_05_00_characters_bot_experiments.sql"
CANONICAL_SCHEMA = ROOT / "sql/updates/characters/4.3.4/2026_06_15_01_characters_bot_dataset_event_schema.sql"
TELEMETRY = ROOT / "src/server/game/Bots/BotWorldPopulationMgrProgressionTelemetry.cpp"


def test_context_json_migration_is_repeatable_and_widens_only_the_evidence_column() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    statement = re.sub(r"--[^\n]*\n", "", migration).strip()

    assert re.fullmatch(
        r"ALTER TABLE `experiment_bot_events`\s+"
        r"MODIFY COLUMN `context_json` mediumtext NULL;",
        statement,
        flags=re.IGNORECASE,
    )
    assert "`context_json` text NULL" in EVENT_SCHEMA.read_text(encoding="utf-8")
    assert "`canonical_event_json` mediumtext" in CANONICAL_SCHEMA.read_text(encoding="utf-8")


def test_raid_telemetry_keeps_the_complete_context_without_truncation() -> None:
    telemetry = TELEMETRY.read_text(encoding="utf-8")
    insert = telemetry[telemetry.index("CharacterDatabase.DirectPExecute(\"INSERT INTO experiment_bot_events"):]

    assert ", context_json," in insert
    assert "CharacterDatabase.EscapeString(contextJson);" in telemetry
    assert not re.search(r"(?:LEFT|SUBSTRING|TRUNCATE)\s*\([^)]*context", telemetry, re.IGNORECASE)
