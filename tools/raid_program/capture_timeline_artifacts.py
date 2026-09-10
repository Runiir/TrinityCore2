"""Generate the primary diagnostic view from the canonical capture's bound rows."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any, Iterable


def attach_capture_timeline(
    rows: Iterable[dict[str, Any]], report: dict[str, Any], output: Path,
    *, raw_sha256: str,
) -> bool:
    """Attach artifacts or record diagnostic failure without erasing a native kill."""
    try:
        report["diagnostic_timeline"] = write_capture_timeline(
            rows, report, output, raw_sha256=raw_sha256,
        )
        report["artifact_inventory"].extend(report["diagnostic_timeline"]["artifacts"])
        return True
    except Exception as error:
        report["diagnostic_timeline"] = {
            "generated": False, "error": f"{type(error).__name__}: {error}",
        }
        if report.get("classification") == "success":
            report["classification"] = "incomplete_evidence"
        report["optimization_acceptance"]["state"] = "diagnostic_timeline_failed"
        report["capture_success"] = False
        return False


def write_capture_timeline(
    rows: Iterable[dict[str, Any]], report: dict[str, Any], output: Path,
    *, raw_sha256: str,
) -> dict[str, Any]:
    from tools.raid_program.bot_timeline import build_timeline_from_rows
    from tools.raid_program.bot_timeline_html import render_timeline_html

    started = time.perf_counter()
    model, summary = build_timeline_from_rows(rows, report, raw_sha256=raw_sha256)
    payloads = (
        ("bot_timeline", output.with_suffix(".timeline.json"),
         json.dumps(model, sort_keys=True, separators=(",", ":"))),
        ("bot_timeline_summary", output.with_suffix(".timeline-summary.json"),
         json.dumps(summary, indent=2, sort_keys=True)),
        ("bot_timeline_html", output.with_suffix(".timeline.html"),
         render_timeline_html(model)),
    )
    artifacts = []
    for kind, path, text in payloads:
        data = (text + "\n").encode("utf-8")
        path.write_bytes(data)
        artifacts.append({"kind": kind, "path": str(path), "bytes": len(data),
                          "sha256": hashlib.sha256(data).hexdigest(), "immutable": True})
    return {
        "generated": True, "artifacts": artifacts,
        "generation_seconds": time.perf_counter() - started,
        "raw_sha256": raw_sha256,
        "completeness": summary.get("completeness"),
        "acceptance_scope": "Generation is not evidence completeness, repair acceptance, "
        "or performance acceptance. Missing observations remain explicit in the timeline.",
    }
