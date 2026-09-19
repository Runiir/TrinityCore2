"""Read the canonical capture's existing records without a second export format."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def is_canonical_capture(report: Any) -> bool:
    return isinstance(report, dict) and str(report.get("capture_id", "")).startswith("cata_raid_phase1_")


def load_canonical_capture(directory: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Require the report-bound raw bytes; never substitute an old derived timeline."""
    if not is_canonical_capture(report):
        raise ValueError("not a canonical raid capture")
    binding = report.get("raw_normalized_batch") or {}
    filename = Path(str(binding.get("path") or "raw.jsonl")).name
    path = directory / filename
    if not path.is_file():
        raise ValueError(f"canonical raw capture unavailable: {path}")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding.get("sha256"):
        raise ValueError("canonical raw capture hash mismatch")
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if len(rows) != binding.get("row_count") or any(not isinstance(row, dict) for row in rows):
        raise ValueError("canonical raw capture row count/type mismatch")
    payloads = [row["payload"] for row in rows if isinstance(row.get("payload"), dict)]
    from tools.bot_ml.run_live_bot_validation import combined_combat_log

    # The stream decoder checks cohort/epoch/attempt identity and delta completeness.
    # Use the recorded active status, never desired configuration.
    active = [row for row in payloads if row.get("action") == "botauto_status"
              and isinstance(row.get("raid_runtime"), dict)
              and row["raid_runtime"].get("active") is True]
    combat = [row for row in payloads if row.get("action") in {
        "botauto_combatlog", "botauto_combatlog_delta",
        "botauto_combatlog_chunk", "botauto_combatlog_complete"}]
    return {"rows": rows, "payloads": payloads,
            "combat_log": combined_combat_log(combat, expected_status=active[0] if active else None),
            "combat_analysis": report.get("combat_analysis") or {}}
