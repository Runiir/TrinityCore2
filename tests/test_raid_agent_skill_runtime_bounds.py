from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BABYSITTER = ROOT / ".agents/skills/raid-boss-babysitter/SKILL.md"
PERFORMANCE_LOOP = ROOT / ".agents/skills/raid-performance-loop/SKILL.md"


def test_babysitter_stops_after_owned_terminal_report() -> None:
    skill = BABYSITTER.read_text(encoding="utf-8")

    assert "worldserver is absent and its final `report.json` exists" in skill
    assert "return the compact handoff immediately" in skill
    assert "deduplicate trace events by `(bot_guid, sequence)`" in skill


def test_router_uses_bounded_trace_receipts() -> None:
    skill = PERFORMANCE_LOOP.read_text(encoding="utf-8")

    assert "Do not hand a\nworker a multi-megabyte raw trace" in skill
    assert "deduplicates by `(bot_guid, sequence)`" in skill
    assert "not a reason to\nkeep polling" in skill
